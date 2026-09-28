// reverb_probe.cpp — 混响离线验证台
//
// 用户要"非常大的那种"混响。所以必须能测出来它到底有多大：
//   * 冲激响应跑到第几秒还在响（RT60）
//   * 会不会失控（自激 / 直流堆积）
//   * 左右是否真的去相关（不是同一条信号复制两遍）
//
// 用法:
//   reverb_probe --tail 0.8 --size 0.7 --seconds 20 --out /tmp/verb.wav
#include "../core/PlateReverb.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

void writeWavF32(const std::string& path, const std::vector<float>& l,
                 const std::vector<float>& r, double sr) {
    std::FILE* f = std::fopen(path.c_str(), "wb");
    if (f == nullptr) {
        std::fprintf(stderr, "错误: 无法写入 %s\n", path.c_str());
        return;
    }
    const std::uint32_t frames = static_cast<std::uint32_t>(l.size());
    const std::uint32_t dataBytes = frames * 2 * 4;
    auto put32 = [&](std::uint32_t v) { std::fwrite(&v, 4, 1, f); };
    auto put16 = [&](std::uint16_t v) { std::fwrite(&v, 2, 1, f); };

    std::fwrite("RIFF", 1, 4, f);
    put32(36 + dataBytes);
    std::fwrite("WAVE", 1, 4, f);
    std::fwrite("fmt ", 1, 4, f);
    put32(16);
    put16(3);
    put16(2);
    put32(static_cast<std::uint32_t>(sr));
    put32(static_cast<std::uint32_t>(sr) * 2 * 4);
    put16(2 * 4);
    put16(32);
    std::fwrite("data", 1, 4, f);
    put32(dataBytes);
    for (std::uint32_t i = 0; i < frames; ++i) {
        const float pair[2] = {l[i], r[i]};
        std::fwrite(pair, 4, 2, f);
    }
    std::fclose(f);
}

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

}  // namespace

int main(int argc, char** argv) {
    const double sr = argOf("--sr", argc, argv, 48000.0);
    const double seconds = argOf("--seconds", argc, argv, 20.0);
    const std::string out = strArg("--out", argc, argv, "/tmp/trane_verb.wav");

    trane::ReverbParams p;
    p.size = static_cast<float>(argOf("--size", argc, argv, 0.7));
    p.tail = static_cast<float>(argOf("--tail", argc, argv, 0.8));
    p.damp = static_cast<float>(argOf("--damp", argc, argv, 0.4));
    p.diffuse = static_cast<float>(argOf("--diffuse", argc, argv, 0.7));
    p.modDepth = static_cast<float>(argOf("--mod", argc, argv, 0.3));
    p.mix = 1.0f;  // 全湿，便于观察纯混响尾音

    trane::PlateReverb verb;
    verb.prepare(sr);
    verb.setParams(p);

    const std::int64_t total = static_cast<std::int64_t>(seconds * sr);
    std::vector<float> inL(static_cast<std::size_t>(total), 0.0f);
    std::vector<float> inR(static_cast<std::size_t>(total), 0.0f);
    // 在 0.1 秒处放一个冲激
    const std::int64_t imp = static_cast<std::int64_t>(0.1 * sr);
    inL[static_cast<std::size_t>(imp)] = 1.0f;
    inR[static_cast<std::size_t>(imp)] = 1.0f;

    std::vector<float> outL(static_cast<std::size_t>(total), 0.0f);
    std::vector<float> outR(static_cast<std::size_t>(total), 0.0f);

    const int block = 256;
    for (std::int64_t pos = 0; pos < total; pos += block) {
        const int n = static_cast<int>(std::min<std::int64_t>(block, total - pos));
        const float* ip[2] = {inL.data() + pos, inR.data() + pos};
        float* op[2] = {outL.data() + pos, outR.data() + pos};
        verb.process(ip, op, n);
    }

    writeWavF32(out, outL, outR, sr);

    // --- 包络（100ms 窗 RMS），用来估算衰减速率 ---
    const std::int64_t win = static_cast<std::int64_t>(0.1 * sr);
    std::vector<double> env;
    for (std::int64_t pos = imp; pos + win <= total; pos += win) {
        double s = 0.0;
        for (std::int64_t i = pos; i < pos + win; ++i) {
            s += static_cast<double>(outL[static_cast<std::size_t>(i)]) *
                 static_cast<double>(outL[static_cast<std::size_t>(i)]);
        }
        env.push_back(std::sqrt(s / static_cast<double>(win)));
    }

    double peak = 0.0;
    for (float v : outL) peak = std::max(peak, static_cast<double>(std::fabs(v)));
    double peakR = 0.0;
    for (float v : outR) peakR = std::max(peakR, static_cast<double>(std::fabs(v)));

    std::printf("=== reverb_probe ===\n");
    std::printf("sr=%.0f  时长=%.1fs  size=%.2f tail=%.2f damp=%.2f diffuse=%.2f\n", sr, seconds,
                p.size, p.tail, p.damp, p.diffuse);
    std::printf("梳状反馈系数 = %.4f\n", verb.combFeedback());
    std::printf("峰值 L=%.6f  R=%.6f\n", peak, peakR);
    std::printf("末段(最后 0.5s) RMS = %.3e\n", env.empty() ? 0.0 : env.back());

    // 衰减斜率：在峰值之后取 -5dB ~ -35dB 的区间做线性拟合（dB vs 秒）
    double mx = 0.0;
    for (double e : env) mx = std::max(mx, e);
    if (mx > 0.0) {
        std::vector<double> xs, ys;
        for (std::size_t i = 0; i < env.size(); ++i) {
            if (env[i] <= 0.0) continue;
            const double db = 20.0 * std::log10(env[i] / mx);
            if (db <= -5.0 && db >= -35.0) {
                xs.push_back(static_cast<double>(i) * 0.1);
                ys.push_back(db);
            }
        }
        if (xs.size() >= 3) {
            const double n = static_cast<double>(xs.size());
            double sx = 0, sy = 0, sxx = 0, sxy = 0;
            for (std::size_t i = 0; i < xs.size(); ++i) {
                sx += xs[i];
                sy += ys[i];
                sxx += xs[i] * xs[i];
                sxy += xs[i] * ys[i];
            }
            const double slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);  // dB/s
            std::printf("衰减斜率 = %.2f dB/s\n", slope);
            if (slope < 0.0) {
                std::printf("推算 RT60 = %.1f 秒\n", -60.0 / slope);
            }
        } else {
            std::printf("衰减区间样本不足，无法拟合\n");
        }
    }

    // 左右去相关：归一化互相关，1.0 = 完全同一条信号
    double num = 0, dl = 0, dr = 0;
    for (std::size_t i = 0; i < outL.size(); ++i) {
        const double a = outL[i], b = outR[i];
        num += a * b;
        dl += a * a;
        dr += b * b;
    }
    const double xcorr = (dl > 0 && dr > 0) ? num / std::sqrt(dl * dr) : 1.0;
    std::printf("左右互相关 = %.4f   (越低越宽，1.0 = 单声道)\n", xcorr);

    // 直流堆积检查
    double dc = 0.0;
    for (float v : outL) dc += v;
    std::printf("输出直流 = %.3e\n", dc / static_cast<double>(outL.size()));
    std::printf("已写出: %s\n", out.c_str());
    return 0;
}
