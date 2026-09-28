// Comb.h — 谐振梳状滤波器（tuned comb）
//
// 解构音乐里那种"金属、塑料、有音高"的染色就是它：
// 一条带反馈的短延迟，延迟长度 D = sr / tuneHz，
// 频谱上形成 tuneHz 整数倍处的一排尖峰 —— 于是噪声也能被听成音高。
//
// 和普通滤波器的区别：它不是在"减"东西，而是在"选"出一个音高网格。
// 把 tune 拧到低频（20~60Hz）再加大反馈，声音会变成一坨有基音的轰鸣；
// 拧到 1~4kHz 则是那种尖锐的、像金属片共振的质感。
//
// 分数延迟用线性插值 —— 否则 tune 只能落在整数样本上，低频段根本调不准
// （20Hz 时一个样本的误差就是 4% 的音高偏差）。
//
// 立体声宽度：右声道延迟比左声道长 0.8%，两个梳状网格轻微错开，
// 拍频在声场里来回走。固定错几个样本会随 tune 变化而失效（高频时误差巨大），
// 所以用比例错开。
//
// 反馈路径上有阻尼低通 + 隔直：高反馈时不会因为直流或高频累积而自激。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace trane {

struct CombParams {
    float tuneHz = 220.0f;   // 谐振基频
    float feedback = 0.6f;   // 0..0.95
    float mix = 0.5f;
};

class Comb {
public:
    static constexpr double kMinTuneHz = 20.0;
    static constexpr double kMaxTuneHz = 4000.0;
    static constexpr double kStereoDetune = 1.008;  // 右声道延迟长 0.8%
    static constexpr double kMaxFeedback = 0.95;
    static constexpr double kSmoothMs = 30.0;
    static constexpr double kMixSmoothMs = 15.0;

    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        cap_ = static_cast<int>(sr_ / kMinTuneHz) + 8;
        for (int ch = 0; ch < 2; ++ch) {
            buf_[ch].assign(static_cast<std::size_t>(cap_), 0.0f);
        }
        tuneCoef_ = std::exp(-1.0 / (kSmoothMs * 0.001 * sr_));
        mixCoef_ = std::exp(-1.0 / (kMixSmoothMs * 0.001 * sr_));
        reset();
    }

    void reset() {
        for (int ch = 0; ch < 2; ++ch) {
            std::fill(buf_[ch].begin(), buf_[ch].end(), 0.0f);
            damp_[ch] = 0.0;
            dcX1_[ch] = 0.0;
            dcY1_[ch] = 0.0;
        }
        w_ = 0;
        tuneSm_ = kMinTuneHz;
        mixSm_ = 0.0;
    }

    void setParams(const CombParams& p) { params_ = p; }

    void process(float* l, float* r, int numSamples) {
        if (numSamples <= 0 || buf_[0].empty()) return;
        float* ch_[2] = {l, r};

        const double tuneTarget =
            std::min(kMaxTuneHz, std::max(kMinTuneHz, static_cast<double>(params_.tuneHz)));
        const double mixTarget = std::min(1.0, std::max(0.0, static_cast<double>(params_.mix)));
        const double fb = std::min(kMaxFeedback, std::max(0.0, static_cast<double>(params_.feedback)));
        // 反馈越深，阻尼越重：高反馈时把高频压下去，避免自激啸叫。
        const double dampCoef = 0.30 + 0.45 * (fb / kMaxFeedback);

        for (int i = 0; i < numSamples; ++i) {
            tuneSm_ += (tuneTarget - tuneSm_) * (1.0 - tuneCoef_);
            mixSm_ += (mixTarget - mixSm_) * (1.0 - mixCoef_);

            const double dL = sr_ / tuneSm_;
            const double dR = dL * kStereoDetune;
            const double delays[2] = {dL, dR};

            for (int ch = 0; ch < 2; ++ch) {
                const double d = delays[ch];
                double rp = static_cast<double>(w_) - d;
                while (rp < 0.0) rp += static_cast<double>(cap_);
                const double base = std::floor(rp);
                const double frac = rp - base;
                const int i0 = static_cast<int>(base) % cap_;
                const int i1 = (i0 + 1 >= cap_) ? 0 : i0 + 1;
                const double v = static_cast<double>(buf_[ch][static_cast<std::size_t>(i0)]) * (1.0 - frac) +
                                 static_cast<double>(buf_[ch][static_cast<std::size_t>(i1)]) * frac;

                // 反馈路径：隔直 → 阻尼低通 → 反馈回去
                const double hp = v - dcX1_[ch] + 0.9995 * dcY1_[ch];
                dcX1_[ch] = v;
                dcY1_[ch] = hp;
                damp_[ch] += (hp - damp_[ch]) * dampCoef;

                const double dry = static_cast<double>(ch_[ch][i]);
                buf_[ch][static_cast<std::size_t>(w_)] = static_cast<float>(dry + fb * damp_[ch]);
                ch_[ch][i] = static_cast<float>(dry * (1.0 - mixSm_) + v * mixSm_);
            }
            if (++w_ >= cap_) w_ = 0;
        }
    }

    // 供测试与界面观察
    double delaySamples() const { return sr_ / tuneSm_; }
    double currentTuneHz() const { return tuneSm_; }

private:
    double sr_ = 48000.0;
    CombParams params_{};
    std::vector<float> buf_[2];
    int cap_ = 2408;
    int w_ = 0;
    double tuneSm_ = kMinTuneHz;
    double mixSm_ = 0.0;
    double tuneCoef_ = 0.0;
    double mixCoef_ = 0.0;
    double damp_[2] = {0.0, 0.0};
    double dcX1_[2] = {0.0, 0.0};
    double dcY1_[2] = {0.0, 0.0};
};

}  // namespace trane
