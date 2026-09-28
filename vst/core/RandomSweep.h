// RandomSweep.h — 随机扫频谐振滤波器
//
// 这是原始需求里的第 5 条「类 Fors Box 的混响/延迟 + 随机扫频」中，
// 混响之外的另一半：一个截止频率被随机数驱动的谐振滤波器。
//
// 为什么是"随机"而不是 LFO：
//   LFO 扫频是有周期感的，听两小节就记住了，适合做律动；
//   随机扫频没有周期，适合做"这个东西自己在动、你控制不了它"的实验质感。
//   两者要的东西不一样，这里要的是后者。
//
// 实现要点：
//   1) 每 1/rate 秒从随机数里抽一个新目标（sample & hold），
//      目标在**对数域**上取值（±depth×3 个八度），这样扫起来听感是均匀的。
//   2) 当前截止频率用一阶低通"滑"向目标，时间常数 0.4/rate 秒 ——
//      直接跳变会咔咔响，滑过去才是"扫"。
//   3) 滤波器用 TPT 状态变量结构（Zavalishin / Cytomic 那套）：
//      比双线性变换的直接型稳定得多，高频截止不炸，且 LP/BP/HP 三个输出同源。
//   4) 立体声两声道共用同一个随机目标（否则声像会散），但各自独立的滤波器状态。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace trane {

struct SweepParams {
    bool on = false;
    float rateHz = 0.8f;      // 随机目标多久换一次
    float depth = 0.4f;       // 扫幅：depth=1 时上下各扫 3 个八度
    float centerHz = 1200.0f; // 中心频率
    float resonance = 0.3f;   // 0..1 → Q 0.5..12
    float mode = 0.0f;        // 0=低通 0.5=带通 1=高通（中间连续过渡）
};

class RandomSweep {
public:
    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        reset();
    }

    void reset() {
        ic1_[0] = ic1_[1] = 0.0;
        ic2_[0] = ic2_[1] = 0.0;
        rng_ = 0x2545F491u;
        holdCounter_ = 0;
        target_ = 0.0;
        cur_ = 0.0;
    }

    void setParams(const SweepParams& p) { params_ = p; }

    void process(float* l, float* r, int numSamples) {
        if (numSamples <= 0) return;
        if (!params_.on) return;  // 关掉时完全直通，不引入任何滤波

        // 每 1/rate 秒抽一次新目标
        const double rate = std::max(0.01, static_cast<double>(params_.rateHz));
        const int holdLen = std::max(1, static_cast<int>(sr_ / rate));
        // 滑向目标的时间常数取间隔的 0.4 倍：够慢才像"扫"，够快才跟得上换目标
        const double glide = 1.0 - std::exp(-1.0 / (0.4 / rate * sr_));

        const double q = 0.5 + static_cast<double>(params_.resonance) * 11.5;
        const double k = 1.0 / q;
        const double center = std::max(20.0, static_cast<double>(params_.centerHz));
        const double depth = static_cast<double>(params_.depth);
        const double mode = std::min(1.0, std::max(0.0, static_cast<double>(params_.mode)));
        const double nyq = sr_ * 0.45;

        float* ch[2] = {l, r};

        for (int i = 0; i < numSamples; ++i) {
            if (--holdCounter_ <= 0) {
                holdCounter_ = holdLen;
                target_ = static_cast<double>(nextRand());  // -1..1
            }
            cur_ += (target_ - cur_) * glide;

            // 对数域映射：depth=1 → 上下各 3 个八度
            const double fc = std::min(nyq, std::max(20.0, center * std::pow(2.0, cur_ * depth * 3.0)));

            // TPT 状态变量滤波器系数
            const double g = std::tan(3.14159265358979323846 * fc / sr_);
            const double a1 = 1.0 / (1.0 + g * (g + k));
            const double a2 = g * a1;
            const double a3 = g * a2;

            for (int c = 0; c < 2; ++c) {
                const double x = static_cast<double>(ch[c][i]);
                const double v3 = x - ic2_[c];
                const double v1 = a1 * ic1_[c] + a2 * v3;
                const double v2 = ic2_[c] + a2 * ic1_[c] + a3 * v3;
                ic1_[c] = 2.0 * v1 - ic1_[c];
                ic2_[c] = 2.0 * v2 - ic2_[c];

                const double low = v2;
                const double band = v1;
                const double high = x - k * v1 - v2;

                double out;
                if (mode <= 0.5) {
                    const double t = mode * 2.0;              // 低通 → 带通
                    out = low * (1.0 - t) + band * t;
                } else {
                    const double t = (mode - 0.5) * 2.0;      // 带通 → 高通
                    out = band * (1.0 - t) + high * t;
                }
                ch[c][i] = static_cast<float>(out);
            }
        }
    }

private:
    // xorshift32：固定种子 → 渲染可复现，否则没法做回归测试
    float nextRand() {
        rng_ ^= rng_ << 13;
        rng_ ^= rng_ >> 17;
        rng_ ^= rng_ << 5;
        return static_cast<float>(static_cast<std::int32_t>(rng_)) * (1.0f / 2147483648.0f);
    }

    double sr_ = 48000.0;
    SweepParams params_{};
    double ic1_[2] = {0.0, 0.0};
    double ic2_[2] = {0.0, 0.0};
    std::uint32_t rng_ = 0x2545F491u;
    int holdCounter_ = 0;
    double target_ = 0.0;
    double cur_ = 0.0;
};

}  // namespace trane
