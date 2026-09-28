// freeze_probe.cpp — 离线渲染验证台
//
// 为什么需要它：Max for Live 那条路我无法在本机运行（依赖 iLok + Java），
// 只能静态验证接线，结果 Freeze 连错两轮都发现不了。
// 这个程序把 FreezeLoop 单独跑起来，渲染成 WAV，再交给 analyze_freeze.py 分析：
//   1. 冻结段到底有没有声音（RMS）
//   2. 是不是真的按 loopMs 的周期在循环（自相关）
//   3. 接缝有没有咔哒（最大样本间跳变）
//   4. 有没有中途静音（"不会断"）
//
// 用法:
//   freeze_probe --loop-ms 250 --freeze-at 2 --freeze-for 4 --out /tmp/f.wav
#include "../core/CaptureBuffer.h"
#include "../core/FreezeLoop.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

constexpr double kPi = 3.14159265358979323846;

void writeWavF32(const std::string& path, const std::vector<float>& l,
                 const std::vector<float>& r, double sr) {
    std::FILE* f = std::fopen(path.c_str(), "wb");
    if (f == nullptr) {
        std::fprintf(stderr, "错误: 无法写入 %s\n", path.c_str());
        return;
    }
    const std::uint32_t frames = static_cast<std::uint32_t>(l.size());
    const std::uint16_t ch = 2;
    const std::uint16_t bits = 32;
    const std::uint32_t dataBytes = frames * ch * (bits / 8);

    auto put32 = [&](std::uint32_t v) { std::fwrite(&v, 4, 1, f); };
    auto put16 = [&](std::uint16_t v) { std::fwrite(&v, 2, 1, f); };

    std::fwrite("RIFF", 1, 4, f);
    put32(36 + dataBytes);
    std::fwrite("WAVE", 1, 4, f);
    std::fwrite("fmt ", 1, 4, f);
    put32(16);
    put16(3);  // WAVE_FORMAT_IEEE_FLOAT
    put16(ch);
    put32(static_cast<std::uint32_t>(sr));
    put32(static_cast<std::uint32_t>(sr) * ch * (bits / 8));
    put16(static_cast<std::uint16_t>(ch * (bits / 8)));
    put16(bits);
    std::fwrite("data", 1, 4, f);
    put32(dataBytes);
    for (std::uint32_t i = 0; i < frames; ++i) {
        const float pair[2] = {l[i], r[i]};
        std::fwrite(pair, 4, 2, f);
    }
    std::fclose(f);
}

double rms(const std::vector<float>& v, std::int64_t a, std::int64_t b) {
    if (b <= a) return 0.0;
    double s = 0.0;
    for (std::int64_t i = a; i < b; ++i) s += static_cast<double>(v[i]) * v[i];
    return std::sqrt(s / static_cast<double>(b - a));
}

// 10ms 窗口里有多少个是静音的 —— 用来证明"不会断"
int countSilentWindows(const std::vector<float>& v, std::int64_t a, std::int64_t b, double sr) {
    const std::int64_t win = static_cast<std::int64_t>(0.010 * sr);
    int silent = 0;
    for (std::int64_t p = a; p + win <= b; p += win) {
        if (rms(v, p, p + win) < 1e-4) ++silent;
    }
    return silent;
}

int totalWindows(std::int64_t a, std::int64_t b, double sr) {
    const std::int64_t win = static_cast<std::int64_t>(0.010 * sr);
    if (b <= a) return 0;
    return static_cast<int>((b - a) / win);
}

double maxDelta(const std::vector<float>& v, std::int64_t a, std::int64_t b) {
    double m = 0.0;
    for (std::int64_t i = a + 1; i < b; ++i) {
        const double d = std::fabs(static_cast<double>(v[i]) - static_cast<double>(v[i - 1]));
        if (d > m) m = d;
    }
    return m;
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
    const double loopMs = argOf("--loop-ms", argc, argv, 250.0);
    const double seamMs = argOf("--seam-ms", argc, argv, 10.0);
    const double freezeAt = argOf("--freeze-at", argc, argv, 2.0);
    const double freezeFor = argOf("--freeze-for", argc, argv, 4.0);
    const double totalSec = argOf("--total", argc, argv, 7.0);
    const std::string out = strArg("--out", argc, argv, "/tmp/trane_freeze.wav");

    const int nch = 2;
    const int blockSize = 64;

    const std::int64_t total = static_cast<std::int64_t>(totalSec * sr);
    const std::int64_t freezeStart = static_cast<std::int64_t>(freezeAt * sr);
    const std::int64_t freezeEnd = static_cast<std::int64_t>((freezeAt + freezeFor) * sr);

    // 输入：每个声道三个非谐波正弦叠加。
    // 非谐波 → 自相关只在"真正的循环周期"处出现尖峰，测试才有判别力。
    const double wL[3] = {220.0, 331.7, 487.3};
    const double wR[3] = {277.2, 391.1, 523.3};

    std::vector<float> inL(static_cast<std::size_t>(total), 0.0f);
    std::vector<float> inR(static_cast<std::size_t>(total), 0.0f);
    for (std::int64_t i = 0; i < total; ++i) {
        const double t = static_cast<double>(i) / sr;
        double a = 0.0, b = 0.0;
        for (int k = 0; k < 3; ++k) {
            a += std::sin(2.0 * kPi * wL[k] * t);
            b += std::sin(2.0 * kPi * wR[k] * t);
        }
        inL[static_cast<std::size_t>(i)] = static_cast<float>(a / 3.0 * 0.9);
        inR[static_cast<std::size_t>(i)] = static_cast<float>(b / 3.0 * 0.9);
    }

    trane::CaptureBuffer cap;
    cap.prepare(nch, sr, 8.0);

    trane::FreezeLoop fl;
    fl.prepare(&cap, sr);
    fl.setLoopMs(loopMs);
    fl.setSeamMs(seamMs);

    std::vector<float> outL(static_cast<std::size_t>(total), 0.0f);
    std::vector<float> outR(static_cast<std::size_t>(total), 0.0f);

    const float* inPtrs[2] = {nullptr, nullptr};
    float* outPtrs[2] = {nullptr, nullptr};

    std::int64_t pos = 0;
    std::int64_t engineLoopLen = 0;
    std::int64_t engineSeam = 0;

    while (pos < total) {
        const bool wantFreeze = (pos >= freezeStart && pos < freezeEnd);
        if (wantFreeze != fl.isFrozen()) fl.setFrozen(wantFreeze);

        std::int64_t nextEvent = total;
        if (wantFreeze) {
            nextEvent = freezeEnd;
        } else if (freezeStart > pos) {
            nextEvent = freezeStart;
        }

        const std::int64_t segEnd = std::min({pos + blockSize, total, nextEvent});
        const int n = static_cast<int>(segEnd - pos);
        if (n <= 0) continue;

        inPtrs[0] = inL.data() + pos;
        inPtrs[1] = inR.data() + pos;
        outPtrs[0] = outL.data() + pos;
        outPtrs[1] = outR.data() + pos;

        fl.process(inPtrs, outPtrs, n);

        if (fl.isFrozen() && engineLoopLen == 0) {
            engineLoopLen = fl.loopLengthSamples();
            engineSeam = fl.seamSamples();
        }
        pos = segEnd;
    }

    writeWavF32(out, outL, outR, sr);
    writeWavF32(out + ".in.wav", inL, inR, sr);

    const std::int64_t expected = static_cast<std::int64_t>(loopMs * 0.001 * sr);
    const std::int64_t dryA = static_cast<std::int64_t>(0.5 * sr);
    const std::int64_t dryB = static_cast<std::int64_t>(1.5 * sr);
    const std::int64_t frzA = freezeStart + static_cast<std::int64_t>(0.5 * sr);
    const std::int64_t frzB = freezeEnd - static_cast<std::int64_t>(0.2 * sr);

    std::printf("=== freeze_probe ===\n");
    std::printf("sr=%.0f  loop_ms=%.1f  seam_ms=%.1f  freeze_at=%.2f  freeze_for=%.2f\n", sr,
                loopMs, seamMs, freezeAt, freezeFor);
    std::printf("loop_samples  期望=%lld  引擎=%lld  %s\n", static_cast<long long>(expected),
                static_cast<long long>(engineLoopLen),
                (engineLoopLen == expected) ? "OK" : "不符");
    std::printf("seam_samples  引擎=%lld\n", static_cast<long long>(engineSeam));
    std::printf("\n--- 分段 RMS（左声道）---\n");
    std::printf("干声  [%.2f,%.2f]  rms=%.6f\n", 0.5, 1.5, rms(outL, dryA, dryB));
    std::printf("冻结  [%.2f,%.2f]  rms=%.6f\n", freezeAt + 0.5, freezeAt + freezeFor - 0.2,
                rms(outL, frzA, frzB));
    std::printf("\n--- 冻结段静音窗口（10ms 窗，证明「不会断」）---\n");
    std::printf("静音窗口 = %d / %d\n", countSilentWindows(outL, frzA, frzB, sr),
                totalWindows(frzA, frzB, sr));
    std::printf("\n--- 最大样本间跳变（咔哒检测，左声道）---\n");
    std::printf("干声  = %.6f\n", maxDelta(outL, dryA, dryB));
    std::printf("冻结  = %.6f\n", maxDelta(outL, frzA, frzB));
    std::printf("\n已写出: %s 与 %s.in.wav\n", out.c_str(), out.c_str());
    return 0;
}
