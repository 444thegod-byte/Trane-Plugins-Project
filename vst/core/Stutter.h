// Stutter.h — 切片重触发（解构的核心工具）
//
// 这是解构俱乐部音乐里最标志性的一招：抓住刚刚过去的一小段声音，原地反复重放，
// 切得硬、切得碎。和 GrainCloud 完全不同 ——
//   粒子云是**带窗**的重叠颗粒（平滑、成雾）；
//   这里是**硬边**的整段切片反复（有棱角、有断口）。
//   两者叠在一起才是那种"碎但厚"的质感。
//
// 做法：
//   自带一个小环形缓冲（最长 1 秒），一直写。
//   每 1/rate 秒触发一次：从写头往回 `size + 随机跳位` 处**闩住**一段切片，
//   然后以 1x 速率把它循环播放，直到下一次触发。
//   jump=0 时永远闩最新的那一段（最"紧"的重复）；
//   jump=1 时可以跳到缓冲深处任意位置（最"碎"的拼贴）。
//
// 切片两端各加 0.3ms 淡化。这不是为了"好听"——
// 硬切在扬声器上会产生很脏的直流冲击，0.3ms 刚好把那个去掉，
// 但听感上仍然是干脆的断口，不是被窗函数抹圆的。
//
// 与 tempo 无关：rate 是自由频率（Hz），不跟随任何 transport。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace trane {

struct StutterParams {
    float sizeMs = 90.0f;  // 切片长度
    float rateHz = 4.0f;   // 每秒闩住多少次新切片
    float jump = 0.35f;    // 新切片往缓冲深处跳多远（0 = 总取最新）
    float mix = 1.0f;
};

class Stutter {
public:
    static constexpr double kMaxSliceMs = 1000.0;
    static constexpr double kDeclickMs = 0.3;
    static constexpr double kMixSmoothMs = 15.0;

    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        const int cap = static_cast<int>(kMaxSliceMs * 0.001 * sr_) + 8;
        ringL_.assign(static_cast<std::size_t>(cap), 0.0f);
        ringR_.assign(static_cast<std::size_t>(cap), 0.0f);
        declick_ = std::max(1, static_cast<int>(kDeclickMs * 0.001 * sr_));
        mixCoef_ = std::exp(-1.0 / (kMixSmoothMs * 0.001 * sr_));
        reset();
    }

    void reset() {
        std::fill(ringL_.begin(), ringL_.end(), 0.0f);
        std::fill(ringR_.begin(), ringR_.end(), 0.0f);
        w_ = 0;
        phase_ = 0;
        sliceStart_ = 0;
        sliceLen_ = 1;
        triggerCountdown_ = 1;
        mixSm_ = 0.0;
        rng_ = 0x6D2B79F5u;
    }

    void setParams(const StutterParams& p) { params_ = p; }

    void process(float* l, float* r, int numSamples) {
        if (numSamples <= 0 || ringL_.empty()) return;
        const int cap = static_cast<int>(ringL_.size());

        const double mixTarget = std::min(1.0, std::max(0.0, static_cast<double>(params_.mix)));
        const int wantLen = std::min(cap - 8,
                                     std::max(2, static_cast<int>(static_cast<double>(params_.sizeMs) *
                                                                  0.001 * sr_)));
        const double rate = std::max(0.05, static_cast<double>(params_.rateHz));
        const int triggerLen = std::max(1, static_cast<int>(sr_ / rate));
        const double jump = std::min(1.0, std::max(0.0, static_cast<double>(params_.jump)));

        for (int i = 0; i < numSamples; ++i) {
            // 写进自己的小环
            ringL_[static_cast<std::size_t>(w_)] = l[i];
            ringR_[static_cast<std::size_t>(w_)] = r[i];

            // 触发：闩住一段新切片
            if (--triggerCountdown_ <= 0) {
                triggerCountdown_ = triggerLen;
                sliceLen_ = wantLen;
                const int maxBack = cap - sliceLen_ - 4;
                const int back =
                    sliceLen_ + static_cast<int>(nextRand01() * jump * static_cast<double>(maxBack));
                sliceStart_ = w_ - back;
                while (sliceStart_ < 0) sliceStart_ += cap;
                phase_ = 0;
            }
            if (++w_ >= cap) w_ = 0;

            // 读切片
            int idx = sliceStart_ + phase_;
            while (idx >= cap) idx -= cap;
            const float slL = ringL_[static_cast<std::size_t>(idx)];
            const float slR = ringR_[static_cast<std::size_t>(idx)];

            // 切片两端去咔哒。
            // 淡化长度不能超过切片的一半 —— 否则切片比淡化还短时，
            // 两条淡化曲线会互相吃掉，切片变成一条几乎听不见的窄脉冲。
            const int dl = std::min(declick_, std::max(1, sliceLen_ / 2));
            double env = 1.0;
            if (phase_ < dl) {
                env = static_cast<double>(phase_) / static_cast<double>(dl);
            } else if (phase_ > sliceLen_ - dl) {
                env = static_cast<double>(sliceLen_ - phase_) / static_cast<double>(dl);
            }
            env = std::min(1.0, std::max(0.0, env));

            mixSm_ += (mixTarget - mixSm_) * (1.0 - mixCoef_);

            l[i] = static_cast<float>(static_cast<double>(l[i]) * (1.0 - mixSm_) +
                                      static_cast<double>(slL) * env * mixSm_);
            r[i] = static_cast<float>(static_cast<double>(r[i]) * (1.0 - mixSm_) +
                                      static_cast<double>(slR) * env * mixSm_);

            if (++phase_ >= sliceLen_) phase_ = 0;
        }
    }

    int sliceLengthSamples() const { return sliceLen_; }

private:
    // xorshift32：固定种子 → 渲染可复现，否则没法做回归测试
    double nextRand01() {
        rng_ ^= rng_ << 13;
        rng_ ^= rng_ >> 17;
        rng_ ^= rng_ << 5;
        return static_cast<double>(rng_) / 4294967296.0;
    }

    double sr_ = 48000.0;
    StutterParams params_{};
    std::vector<float> ringL_, ringR_;
    int w_ = 0;
    int phase_ = 0;
    int sliceStart_ = 0;
    int sliceLen_ = 1;
    int triggerCountdown_ = 1;
    int declick_ = 14;
    double mixSm_ = 0.0;
    double mixCoef_ = 0.0;
    std::uint32_t rng_ = 0x6D2B79F5u;
};

}  // namespace trane
