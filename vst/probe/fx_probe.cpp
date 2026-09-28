// fx_probe.cpp — 离线测量台
//
// 这些模块光靠"听"没法判定对错，必须量：
//   delay   → 喂脉冲，量每次回声的**位置**和**幅度**，看间隔对不对、反馈比对不对
//   sweep   → 喂白噪声，量每 100ms 的**过零率**（亮度指标），看它是否真的在动
//   stutter → 喂白噪声，量输出在 lag = 切片长度 处的**自相关**，看它是否真的在原地重复
//   tape    → 喂 1000Hz 正弦，量输出的**频率**，看 speed=0.5 是否真的掉到 500Hz
//   comb    → 喂白噪声，用 Goertzel 量 tuneHz 整数倍处与其间谷底的**幅度比**
//
// 用法:
//   fx_probe delay   --time 250 --feedback 0.6 --damp 0.3 --pingpong 0 --out x.wav
//   fx_probe sweep   --rate 2 --depth 1 --center 1000 --reso 0.5 --mode 0 --out y.wav
//   fx_probe stutter --size 100 --rate 1 --jump 0 --out z.wav
//   fx_probe tape    --speed 0.5 --wobble 0 --out t.wav
//   fx_probe comb    --tune 220 --feedback 0.7 --out c.wav
#include "../core/Comb.h"
#include "../core/RandomSweep.h"
#include "../core/Ruin.h"
#include "../core/SpaceDelay.h"
#include "../core/Stutter.h"
#include "../core/Tape.h"
#include "wav_io.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

double argOf(const char* key, int argc, char** argv, double fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return std::atof(argv[i + 1]);
    }
    return fallback;
}

std::string strArg(const char* key, int argc, char** argv, const char* fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return std::string(argv[i + 1]);
    }
    return std::string(fallback);
}

bool hasFlag(const char* key, int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], key) == 0) return true;
    }
    return false;
}

std::string fmt1(double v) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%.1f", v);
    return std::string(buf);
}

double rms(const std::vector<float>& v, std::size_t a, std::size_t b) {
    if (b <= a) return 0.0;
    double s = 0.0;
    for (std::size_t i = a; i < b; ++i) s += static_cast<double>(v[i]) * v[i];
    return std::sqrt(s / static_cast<double>(b - a));
}

// 过零率：单位样本里符号翻转的比例。滤波器越暗，过零越少。
double zeroCrossRate(const std::vector<float>& v, std::size_t a, std::size_t b) {
    if (b <= a + 1) return 0.0;
    int n = 0;
    for (std::size_t i = a + 1; i < b; ++i) {
        if ((v[i - 1] < 0.0f) != (v[i] < 0.0f)) ++n;
    }
    return static_cast<double>(n) / static_cast<double>(b - a - 1);
}

// 归一化自相关：lag 处输出与自身平移后的相关系数。原地重复的信号在 lag=周期 处接近 1。
double autocorrAt(const std::vector<float>& v, std::size_t a, std::size_t b, std::size_t lag) {
    if (lag == 0 || b <= a + lag) return 0.0;
    double num = 0.0, e0 = 0.0, e1 = 0.0;
    for (std::size_t i = a; i + lag < b; ++i) {
        const double x = v[i];
        const double y = v[i + lag];
        num += x * y;
        e0 += x * x;
        e1 += y * y;
    }
    const double den = std::sqrt(e0 * e1);
    return den > 1e-12 ? num / den : 0.0;
}

// Goertzel：单频点幅度。用来验证梳状滤波器的谱峰位置。
double goertzel(const std::vector<float>& v, std::size_t a, std::size_t b, double freq, double sr) {
    if (b <= a) return 0.0;
    const double w = 2.0 * 3.14159265358979323846 * freq / sr;
    const double cw = std::cos(w);
    const double sw = std::sin(w);
    const double coeff = 2.0 * cw;
    double s1 = 0.0, s2 = 0.0;
    for (std::size_t i = a; i < b; ++i) {
        const double s0 = static_cast<double>(v[i]) + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    const double re = s1 - s2 * cw;
    const double im = s2 * sw;
    return std::sqrt(re * re + im * im) / static_cast<double>(b - a);
}

// 确定性白噪声（固定种子 → 可回归）
std::vector<float> whiteNoise(std::size_t n, float amp) {
    std::vector<float> v(n, 0.0f);
    std::uint32_t rng = 0x12345678u;
    for (std::size_t i = 0; i < n; ++i) {
        rng ^= rng << 13;
        rng ^= rng >> 17;
        rng ^= rng << 5;
        v[i] = static_cast<float>(static_cast<std::int32_t>(rng)) * (1.0f / 2147483648.0f) * amp;
    }
    return v;
}

double peakOf(const std::vector<float>& v) {
    double p = 0.0;
    for (float x : v) p = std::max(p, static_cast<double>(std::fabs(x)));
    return p;
}

bool writeStereo(const std::string& path, double sr, const std::vector<float>& l,
                 const std::vector<float>& r) {
    wavio::Audio a;
    a.sampleRate = sr;
    a.left = l;
    a.right = r;
    return wavio::writeWavF32(path, a);
}

// ---------------------------------------------------------------- delay

int runDelay(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double timeMs = argOf("--time", argc, argv, 250.0);
    const double feedback = argOf("--feedback", argc, argv, 0.6);
    const double damp = argOf("--damp", argc, argv, 0.3);
    const double pingpong = argOf("--pingpong", argc, argv, 0.0);
    const double mix = argOf("--mix", argc, argv, 0.5);
    const double seconds = argOf("--seconds", argc, argv, 6.0);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_delay.wav");

    trane::SpaceDelay d;
    d.prepare(sr);
    trane::DelayParams p;
    p.on = true;
    p.timeMs = static_cast<float>(timeMs);
    p.feedback = static_cast<float>(feedback);
    p.damp = static_cast<float>(damp);
    p.pingPong = static_cast<float>(pingpong);
    p.mix = static_cast<float>(mix);
    d.setParams(p);

    const std::size_t total = static_cast<std::size_t>(seconds * sr);
    std::vector<float> inL(total, 0.0f), inR(total, 0.0f);
    std::vector<float> outL(total, 0.0f), outR(total, 0.0f);

    // 输入：t=50ms 处一个 40 样本的汉宁脉冲，其余静音
    // --left-only：只喂左声道 —— 用来验证 ping-pong 是否真的把回声换到右声道
    const bool leftOnly = hasFlag("--left-only", argc, argv);
    const std::size_t at = static_cast<std::size_t>(0.050 * sr);
    for (std::size_t i = 0; i < 40 && at + i < total; ++i) {
        const double w = 0.5 - 0.5 * std::cos(2.0 * 3.14159265358979323846 * i / 39.0);
        inL[at + i] = static_cast<float>(w);
        if (!leftOnly) inR[at + i] = static_cast<float>(w);
    }

    const int block = 256;
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        const int n = static_cast<int>(end - pos);
        float* l = outL.data() + pos;
        float* r = outR.data() + pos;
        std::copy(inL.begin() + static_cast<long>(pos), inL.begin() + static_cast<long>(end), l);
        std::copy(inR.begin() + static_cast<long>(pos), inR.begin() + static_cast<long>(end), r);
        d.process(l, r, n);
    }

    std::printf("=== fx_probe / delay ===\n");
    std::printf("采样率=%.0f  时间=%.1fms  反馈=%.3f  阻尼=%.2f  PingPong=%.2f  Mix=%.2f\n", sr,
                timeMs, feedback, damp, pingpong, mix);

    // 包络 + 找峰（间隔至少 30ms，幅度至少 0.005）
    const int smooth = std::max(1, static_cast<int>(0.004 * sr));
    const std::size_t minGap = static_cast<std::size_t>(0.030 * sr);
    std::vector<float> env(total, 0.0f);
    for (std::size_t i = 0; i < total; ++i) {
        const std::size_t a = i > static_cast<std::size_t>(smooth) ? i - static_cast<std::size_t>(smooth) : 0;
        const std::size_t b = std::min(total, i + static_cast<std::size_t>(smooth));
        double m = 0.0;
        for (std::size_t k = a; k < b; ++k) m = std::max(m, static_cast<double>(std::fabs(outL[k])));
        env[i] = static_cast<float>(m);
    }

    std::vector<std::size_t> peaks;
    std::size_t last = 0;
    for (std::size_t i = 1; i + 1 < total; ++i) {
        if (env[i] >= env[i - 1] && env[i] >= env[i + 1] && env[i] > 0.005f) {
            if (peaks.empty() || i - last >= minGap) {
                peaks.push_back(i);
                last = i;
            }
        }
    }

    std::printf("\n检测到的回声（相对脉冲起点 %.0fms）:\n", 50.0);
    std::printf("  %8s %10s %10s\n", "时间(ms)", "幅度", "间隔(ms)");
    double gapSum = 0.0;
    int gapCount = 0;
    for (std::size_t k = 0; k < peaks.size() && k < 12; ++k) {
        const double tMs = static_cast<double>(peaks[k]) / sr * 1000.0 - 50.0;
        const double amp = static_cast<double>(env[peaks[k]]);
        double gap = 0.0;
        if (k > 0) {
            gap = static_cast<double>(peaks[k] - peaks[k - 1]) / sr * 1000.0;
            gapSum += gap;
            ++gapCount;
        }
        std::printf("  %8.1f %10.4f %10s\n", tMs, amp,
                    k == 0 ? "-" : fmt1(gap).c_str());
    }

    // 反馈比要拿"相邻两个回声"来量，不能拿干声比第一回声 ——
    // 干声与第一回声的比值由 mix 决定（mix/(1-mix)），跟反馈没关系。
    double fbMeasured = 0.0;
    int fbCount = 0;
    for (std::size_t k = 1; k + 1 < peaks.size() && k < 8; ++k) {
        const double a0 = static_cast<double>(env[peaks[k]]);
        if (a0 > 1e-4) {
            fbMeasured += static_cast<double>(env[peaks[k + 1]]) / a0;
            ++fbCount;
        }
    }
    if (fbCount > 0) fbMeasured /= static_cast<double>(fbCount);
    const double gapAvg = gapCount > 0 ? gapSum / gapCount : 0.0;

    std::printf("\n回声间隔     : %.1f ms   (期望 %.1f ms)\n", gapAvg, timeMs);
    std::printf("反馈比       : %.4f   (期望 %.4f，阻尼会让它略低于设定值)\n", fbMeasured,
                feedback);
    std::printf("右声道 RMS   : %.8f   (ping-pong=0 且只喂左声道时应为 0)\n",
                rms(outR, static_cast<std::size_t>(0.2 * sr), total));
    std::printf("整段峰值     : %.6f\n", [&] {
        double p = 0.0;
        for (std::size_t i = 0; i < total; ++i) {
            p = std::max(p, static_cast<double>(std::fabs(outL[i])));
            p = std::max(p, static_cast<double>(std::fabs(outR[i])));
        }
        return p;
    }());
    const double tailRms = rms(outL, total - static_cast<std::size_t>(0.5 * sr), total);
    std::printf("末段 RMS     : %.8f   (反馈<1 时必须趋近 0)\n", tailRms);

    wavio::Audio result;
    result.sampleRate = sr;
    result.left = outL;
    result.right = outR;
    if (!wavio::writeWavF32(outPath, result)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

// ---------------------------------------------------------------- sweep

int runSweep(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double rate = argOf("--rate", argc, argv, 2.0);
    const double depth = argOf("--depth", argc, argv, 1.0);
    const double center = argOf("--center", argc, argv, 1000.0);
    const double reso = argOf("--reso", argc, argv, 0.5);
    const double mode = argOf("--mode", argc, argv, 0.0);
    const double seconds = argOf("--seconds", argc, argv, 8.0);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_sweep.wav");

    trane::RandomSweep s;
    s.prepare(sr);
    trane::SweepParams p;
    p.on = !hasFlag("--bypass", argc, argv);
    p.rateHz = static_cast<float>(rate);
    p.depth = static_cast<float>(depth);
    p.centerHz = static_cast<float>(center);
    p.resonance = static_cast<float>(reso);
    p.mode = static_cast<float>(mode);
    s.setParams(p);

    // 输入：固定种子白噪声（确定性 → 可回归）
    std::vector<float> outL(static_cast<std::size_t>(seconds * sr), 0.0f);
    std::vector<float> outR(outL.size(), 0.0f);
    std::uint32_t rng = 0x12345678u;
    auto nextNoise = [&]() {
        rng ^= rng << 13;
        rng ^= rng >> 17;
        rng ^= rng << 5;
        return static_cast<float>(static_cast<std::int32_t>(rng)) * (1.0f / 2147483648.0f) * 0.25f;
    };
    for (std::size_t i = 0; i < outL.size(); ++i) {
        outL[i] = nextNoise();
        outR[i] = nextNoise();
    }

    const int block = 256;
    const std::size_t total = outL.size();
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        s.process(outL.data() + pos, outR.data() + pos, static_cast<int>(end - pos));
    }

    std::printf("=== fx_probe / sweep ===\n");
    std::printf("采样率=%.0f  Rate=%.2fHz  Depth=%.2f  Center=%.0fHz  Reso=%.2f  Mode=%.2f  %s\n",
                sr, rate, depth, center, reso, mode,
                p.on ? "开" : "旁通");

    const std::size_t win = static_cast<std::size_t>(
        std::max(5.0, argOf("--win-ms", argc, argv, 100.0)) * 0.001 * sr);
    std::printf("\n每 %.0fms 的过零率（亮度指标，越低越暗）:\n", 1000.0 * static_cast<double>(win) / sr);
    std::vector<double> zcrs;
    for (std::size_t a = win; a + win <= total; a += win) {
        const double z = zeroCrossRate(outL, a, a + win);
        zcrs.push_back(z);
        std::printf("  %5.1fs  %8.4f\n", static_cast<double>(a) / sr, z);
    }
    double zmin = 1.0, zmax = 0.0;
    for (double z : zcrs) {
        zmin = std::min(zmin, z);
        zmax = std::max(zmax, z);
    }
    std::printf("\n过零率范围   : %.4f .. %.4f   变化幅度 %.4f\n", zmin, zmax, zmax - zmin);
    std::printf("整段峰值     : %.6f   (不得失控)\n", [&] {
        double p = 0.0;
        for (std::size_t i = 0; i < total; ++i) {
            p = std::max(p, static_cast<double>(std::fabs(outL[i])));
        }
        return p;
    }());

    wavio::Audio result;
    result.sampleRate = sr;
    result.left = outL;
    result.right = outR;
    if (!wavio::writeWavF32(outPath, result)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

// ---------------------------------------------------------------- stutter

int runStutter(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double sizeMs = argOf("--size", argc, argv, 100.0);
    const double rate = argOf("--rate", argc, argv, 1.0);
    const double jump = argOf("--jump", argc, argv, 0.0);
    const double seconds = argOf("--seconds", argc, argv, 6.0);
    const bool off = hasFlag("--off", argc, argv);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_stutter.wav");

    trane::Stutter s;
    s.prepare(sr);
    trane::StutterParams p;
    p.sizeMs = static_cast<float>(sizeMs);
    p.rateHz = static_cast<float>(rate);
    p.jump = static_cast<float>(jump);
    p.mix = off ? 0.0f : 1.0f;
    s.setParams(p);

    const std::size_t total = static_cast<std::size_t>(seconds * sr);
    std::vector<float> outL = whiteNoise(total, 0.3f);
    std::vector<float> outR = outL;

    const int block = 256;
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        s.process(outL.data() + pos, outR.data() + pos, static_cast<int>(end - pos));
    }

    const std::size_t sliceLen =
        static_cast<std::size_t>(std::max(2.0, sizeMs * 0.001 * sr));
    const std::size_t a = static_cast<std::size_t>(2.0 * sr);
    const std::size_t b = total;

    std::printf("=== fx_probe / stutter ===\n");
    std::printf("采样率=%.0f  切片=%.1fms(%zu 样本)  触发=%.2fHz  跳位=%.2f  %s\n", sr, sizeMs,
                sliceLen, rate, jump, off ? "关（对照）" : "开");
    std::printf("切片实际长度 : %d\n", s.sliceLengthSamples());

    const double acSelf = autocorrAt(outL, a, b, sliceLen);
    const double acHalf = autocorrAt(outL, a, b, sliceLen / 2);
    std::printf("\n自相关 @ 切片长度 : %.4f   (原地重复时接近 1)\n", acSelf);
    std::printf("自相关 @ 半切片   : %.4f   (对照，应明显更低)\n", acHalf);

    // 扫描找最强的重复周期：真切片重触发应在切片长度的整数倍处出现局部极大
    std::printf("\nlag(样本)  lag(ms)   自相关\n");
    std::size_t bestLag = 0;
    double bestVal = -1.0;
    for (int k = 1; k <= 12; ++k) {
        const std::size_t lag = sliceLen * static_cast<std::size_t>(k);
        if (lag == 0 || b <= a + lag) break;
        const double v = autocorrAt(outL, a, b, lag);
        std::printf("  %7zu  %8.1f   %8.4f\n", lag, static_cast<double>(lag) / sr * 1000.0, v);
        if (v > bestVal) {
            bestVal = v;
            bestLag = lag;
        }
    }
    std::printf("\n最强周期     : %zu\n", bestLag);
    std::printf("最强周期毫秒 : %.1f\n", static_cast<double>(bestLag) / sr * 1000.0);
    std::printf("周期倍数     : %.2f   (相对切片长度，应为整数倍)\n",
                sliceLen > 0 ? static_cast<double>(bestLag) / static_cast<double>(sliceLen) : 0.0);
    std::printf("整段峰值     : %.6f   (不得失控)\n", peakOf(outL));

    if (!writeStereo(outPath, sr, outL, outR)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

// ---------------------------------------------------------------- tape

int runTape(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double speed = argOf("--speed", argc, argv, 0.5);
    const double wobble = argOf("--wobble", argc, argv, 0.0);
    const double toneHz = argOf("--tone", argc, argv, 1000.0);
    const double seconds = argOf("--seconds", argc, argv, 5.0);
    // 变速切换：用来验证"先减速攒带子、再加速"这个机制
    const double rampAt = argOf("--ramp-at", argc, argv, -1.0);
    const double rampSpeed = argOf("--ramp-speed", argc, argv, -1.0);
    const bool off = hasFlag("--off", argc, argv);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_tape.wav");

    trane::Tape t;
    t.prepare(sr);
    trane::TapeParams p;
    p.speed = static_cast<float>(speed);
    p.wobble = static_cast<float>(wobble);
    p.mix = off ? 0.0f : 1.0f;
    t.setParams(p);

    const std::size_t total = static_cast<std::size_t>(seconds * sr);
    std::vector<float> outL(total, 0.0f);
    std::vector<float> outR(total, 0.0f);
    for (std::size_t i = 0; i < total; ++i) {
        const float v = static_cast<float>(
            0.4 * std::sin(2.0 * 3.14159265358979323846 * toneHz * static_cast<double>(i) / sr));
        outL[i] = v;
        outR[i] = v;
    }

    const int block = 256;
    const std::size_t rampSample = rampAt >= 0.0 ? static_cast<std::size_t>(rampAt * sr) : 0;
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        if (rampSpeed >= 0.0 && pos >= rampSample) {
            p.speed = static_cast<float>(rampSpeed);
            t.setParams(p);
        }
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        t.process(outL.data() + pos, outR.data() + pos, static_cast<int>(end - pos));
    }

    // 用上穿零点计数测频率
    auto freqIn = [&](std::size_t a, std::size_t b) {
        if (b <= a + 1) return 0.0;
        int up = 0;
        for (std::size_t i = a + 1; i < b; ++i) {
            if (outL[i - 1] <= 0.0f && outL[i] > 0.0f) ++up;
        }
        return static_cast<double>(up) / (static_cast<double>(b - a) / sr);
    };

    const std::size_t a = static_cast<std::size_t>(2.0 * sr);
    const std::size_t b = std::min(total, static_cast<std::size_t>(3.0 * sr));
    const double freq = freqIn(a, b);

    std::printf("=== fx_probe / tape ===\n");
    std::printf("采样率=%.0f  输入=%.0fHz  Speed=%.3f  Wobble=%.2f  %s\n", sr, toneHz, speed,
                wobble, off ? "关（对照）" : "开");
    if (rampSpeed >= 0.0) {
        std::printf("变速切换     : %.2fs 时 speed → %.3f\n", rampAt, rampSpeed);
    }
    std::printf("\n实测输出频率 : %.2f Hz   (期望 %.2f Hz = 输入 x speed)\n", freq,
                toneHz * speed);
    if (rampSpeed >= 0.0) {
        // 切换后 0.3s ~ 1.0s 的窗口：此时应当真的在按新速率跑
        const std::size_t ra = static_cast<std::size_t>((rampAt + 0.3) * sr);
        const std::size_t rb = std::min(total, static_cast<std::size_t>((rampAt + 1.0) * sr));
        const double f2 = freqIn(ra, rb);
        std::printf("切换后实测   : %.2f Hz   (期望 %.2f Hz)\n", f2, toneHz * rampSpeed);
    }
    std::printf("平滑后速率   : %.4f\n", t.currentSpeed());
    std::printf("实际推进速率 : %.4f\n", t.currentRate());
    std::printf("磁带存量     : %.0f 样本 (%.1f ms)\n", t.tapeReserveSamples(),
                t.tapeReserveSamples() / sr * 1000.0);

    // 瞬时音高偏差：50ms 窗口逐段测频，看抖动是否真的在调制速率
    const std::size_t win = static_cast<std::size_t>(0.05 * sr);
    double fmin = 1e9, fmax = 0.0;
    for (std::size_t s = a; s + win <= b; s += win) {
        const double f = freqIn(s, s + win);
        fmin = std::min(fmin, f);
        fmax = std::max(fmax, f);
    }
    std::printf("\n窗口频率下限 : %.1f\n", fmin);
    std::printf("窗口频率上限 : %.1f\n", fmax);
    std::printf("音高偏差     : %.2f   (百分比，抖动深度 %.2f)\n",
                (fmax - fmin) * 0.5 / std::max(1.0, toneHz) * 100.0, wobble);

    // 停转检查：speed=0 时隔直应把读到的静止值滤掉 → 末段趋近静音
    const std::size_t tailA = total - static_cast<std::size_t>(0.5 * sr);
    std::printf("末段 RMS     : %.8f   (speed=0 时应趋近 0，不许灌直流)\n",
                rms(outL, tailA, total));
    std::printf("整段峰值     : %.6f   (不得失控)\n", peakOf(outL));

    if (!writeStereo(outPath, sr, outL, outR)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

// ---------------------------------------------------------------- comb

int runComb(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double tune = argOf("--tune", argc, argv, 220.0);
    const double feedback = argOf("--feedback", argc, argv, 0.7);
    const double mix = argOf("--mix", argc, argv, 1.0);
    const double seconds = argOf("--seconds", argc, argv, 5.0);
    const bool off = hasFlag("--off", argc, argv);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_comb.wav");

    trane::Comb c;
    c.prepare(sr);
    trane::CombParams p;
    p.tuneHz = static_cast<float>(tune);
    p.feedback = static_cast<float>(feedback);
    p.mix = off ? 0.0f : static_cast<float>(mix);
    c.setParams(p);

    const std::size_t total = static_cast<std::size_t>(seconds * sr);
    std::vector<float> outL = whiteNoise(total, 0.25f);
    std::vector<float> outR = outL;

    const int block = 256;
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        c.process(outL.data() + pos, outR.data() + pos, static_cast<int>(end - pos));
    }

    // 分析窗口取 2s~4s：tune 的 30ms 平滑早已收敛
    const std::size_t a = static_cast<std::size_t>(2.0 * sr);
    const std::size_t b = std::min(total, static_cast<std::size_t>(4.0 * sr));

    std::printf("=== fx_probe / comb ===\n");
    std::printf("采样率=%.0f  Tune=%.1fHz  Feedback=%.3f  Mix=%.2f  %s\n", sr, tune, feedback,
                mix, off ? "关（对照）" : "开");
    std::printf("延迟样本 = %.3f  (sr/tune)\n", c.delaySamples());

    std::printf("\n 谐波  频率(Hz)   峰幅度     谷频率(Hz)  谷幅度     峰/谷\n");
    double ratioSum = 0.0;
    int ratioCount = 0;
    for (int k = 1; k <= 6; ++k) {
        const double fPeak = tune * k;
        const double fValley = tune * (k + 0.5);
        if (fPeak > sr * 0.45 || fValley > sr * 0.45) break;
        const double mPeak = goertzel(outL, a, b, fPeak, sr);
        const double mValley = goertzel(outL, a, b, fValley, sr);
        const double ratio = mValley > 1e-12 ? mPeak / mValley : 0.0;
        ratioSum += ratio;
        ++ratioCount;
        std::printf("  %2d   %8.1f  %8.5f   %8.1f  %8.5f  %6.2f\n", k, fPeak, mPeak, fValley,
                    mValley, ratio);
    }
    std::printf("\n平均峰/谷比  : %.2f   (反馈 %.2f 理论上界约 %.2f)\n",
                ratioCount > 0 ? ratioSum / ratioCount : 0.0, feedback,
                (1.0 + feedback) / std::max(1e-6, 1.0 - feedback));

    // 更稳健的判据：梳状滤波器的冲激响应是间隔 D 的一串脉冲（幅度 fb^k），
    // 所以输出在 lag=D 处的归一化自相关应当 ≈ feedback。
    // 单点 DFT 会被白噪声本身的随机谱影响（对照组也能撞出 2~3 倍），
    // 自相关不受这个影响，是干净的单值判据。
    const std::size_t dSample =
        static_cast<std::size_t>(std::max(1.0, std::round(sr / std::max(1.0, tune))));
    const double acD = autocorrAt(outL, a, b, dSample);
    const double acOff = autocorrAt(outL, a, b, dSample + std::max<std::size_t>(1, dSample / 2));
    std::printf("\n自相关 @ 1 倍梳状周期 : %.4f   (期望 ≈ feedback %.2f)\n", acD, feedback);
    std::printf("自相关 @ 1.5 倍周期  : %.4f   (对照，应明显更低)\n", acOff);

    // 扫描找第一个自相关峰的位置 → 直接验证 tune → 延迟 的映射是否准
    std::size_t bestLag = 0;
    double bestVal = -1.0;
    for (std::size_t lag = 20; lag < 1500; ++lag) {
        const double v = autocorrAt(outL, a, b, lag);
        if (v > bestVal) {
            bestVal = v;
            bestLag = lag;
        }
    }
    std::printf("峰值位置 lag : %zu\n", bestLag);
    std::printf("实测基频     : %.2f\n", bestLag > 0 ? sr / static_cast<double>(bestLag) : 0.0);
    std::printf("设定基频     : %.1f\n", tune);
    std::printf("末段 RMS     : %.8f   (反馈<1 时必须趋近 0)\n",
                rms(outL, total - static_cast<std::size_t>(0.5 * sr), total));
    std::printf("整段峰值     : %.6f   (不得自激)\n", peakOf(outL));

    if (!writeStereo(outPath, sr, outL, outR)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

// ---------------------------------------------------------------- ruin / fold

int runRuin(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double mode = argOf("--mode", argc, argv, 1.0);
    const double drive = argOf("--drive", argc, argv, 0.0);
    const double fold = argOf("--fold", argc, argv, 0.0);
    const double crush = argOf("--crush", argc, argv, 0.0);
    const double ring = argOf("--ring", argc, argv, 0.0);
    const double toneHz = argOf("--tone", argc, argv, 200.0);
    const double amp = argOf("--amp", argc, argv, 0.3);
    const double seconds = argOf("--seconds", argc, argv, 3.0);
    const std::string outPath = strArg("--out", argc, argv, "/tmp/fx_ruin.wav");

    trane::Ruin r;
    r.prepare(sr);
    trane::RuinParams p;
    p.mode = static_cast<float>(mode);
    p.drive = static_cast<float>(drive);
    p.fold = static_cast<float>(fold);
    p.crush = static_cast<float>(crush);
    p.ring = static_cast<float>(ring);
    r.setParams(p);

    const std::size_t total = static_cast<std::size_t>(seconds * sr);
    std::vector<float> outL(total, 0.0f);
    std::vector<float> outR(total, 0.0f);
    for (std::size_t i = 0; i < total; ++i) {
        const float v = static_cast<float>(
            amp * std::sin(2.0 * 3.14159265358979323846 * toneHz * static_cast<double>(i) / sr));
        outL[i] = v;
        outR[i] = v;
    }

    const int block = 256;
    for (std::size_t pos = 0; pos < total; pos += static_cast<std::size_t>(block)) {
        const std::size_t end = std::min(total, pos + static_cast<std::size_t>(block));
        const int n = static_cast<int>(end - pos);
        float* l = outL.data() + pos;
        float* rr = outR.data() + pos;
        const float* cin[2] = {l, rr};
        float* cout[2] = {l, rr};
        r.process(cin, cout, n);  // 就地处理
    }

    const std::size_t a = static_cast<std::size_t>(1.0 * sr);
    const std::size_t b = total;

    std::printf("=== fx_probe / ruin ===\n");
    std::printf("采样率=%.0f  输入=%.0fHz @ %.2f  Mode=%.2f Drive=%.2f Fold=%.2f Crush=%.2f Ring=%.2f\n",
                sr, toneHz, amp, mode, drive, fold, crush, ring);

    const double fund = goertzel(outL, a, b, toneHz, sr);
    double harm = 0.0;
    std::printf("\n 谐波   频率(Hz)   幅度        相对基频\n");
    for (int k = 2; k <= 12; ++k) {
        const double f = toneHz * k;
        if (f > sr * 0.45) break;
        const double m = goertzel(outL, a, b, f, sr);
        harm += m * m;
        std::printf("  %2d   %8.1f  %9.6f   %8.4f\n", k, f, m, fund > 1e-12 ? m / fund : 0.0);
    }
    const double thd = fund > 1e-12 ? std::sqrt(harm) / fund : 0.0;
    std::printf("\n总谐波含量   : %.4f   (基频幅度 %.6f)\n", thd, fund);
    std::printf("整段峰值     : %.6f   (折叠不得失控)\n", peakOf(outL));

    if (!writeStereo(outPath, sr, outL, outR)) return 2;
    std::printf("已写出: %s\n", outPath.c_str());
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::fprintf(stderr,
                     "用法: fx_probe <delay|sweep|stutter|tape|comb|ruin> [选项]\n");
        return 2;
    }
    const std::string mode = argv[1];
    if (mode == "delay") return runDelay(argc, argv);
    if (mode == "sweep") return runSweep(argc, argv);
    if (mode == "stutter") return runStutter(argc, argv);
    if (mode == "tape") return runTape(argc, argv);
    if (mode == "comb") return runComb(argc, argv);
    if (mode == "ruin") return runRuin(argc, argv);
    std::fprintf(stderr, "未知模式: %s\n", mode.c_str());
    return 2;
}
