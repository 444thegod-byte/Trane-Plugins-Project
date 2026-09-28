// Ruin.h — Clear / Ruin 两种人格
//
// Clear: 干净、可辨识
// Ruin:  脏、失真、解构 —— 环形调制 → 饱和 → 波形折叠 → 位深压碎
//
// MODE 是连续量而非开关，所以从 Clear 拧到 Ruin 是一条可听的渐变，不是硬切。
//
// FOLD 单独说明：饱和（tanh）和折叠是两种完全不同的非线性 ——
//   tanh 是"越推越平"，信号被压成方波，谐波增长到一定程度就停了；
//   折叠是"越推越翻"，信号超出 ±1 后被折回来，谐波会持续爆增，
//   听起来是金属的、有棱角的、会自己长出泛音的。
// 解构音乐里那种"硬"主要来自折叠，不是来自失真。
#pragma once

#include <algorithm>
#include <cmath>

namespace trane {

struct RuinParams {
    float mode = 0.0f;     // 0 = Clear, 1 = Ruin（连续）
    float drive = 0.35f;   // 饱和量
    float fold = 0.0f;     // 波形折叠量
    float crush = 0.0f;    // 位深压碎
    float ring = 0.0f;     // 环形调制深度
    float ringHz = 120.0f; // 环形调制频率
};

// 三角波折叠器：周期 4，在 [-1,1] 内是恒等映射，超出部分反复折回来。
// 推导：令 t = x 落在 [-1,3)，则 f = 1 - |t - 1|。
//   t=-1 → -1   t=0 → 0   t=1 → 1   t=2 → 0   t=3 → -1（与 t=-1 接上，连续）
inline double foldTriangle(double x) {
    const double t = x - 4.0 * std::floor((x + 1.0) * 0.25);
    return 1.0 - std::abs(t - 1.0);
}

class Ruin {
public:
    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        reset();
    }

    void reset() {
        phase_ = 0.0;
        holdCount_ = 1;
        hold_[0] = hold_[1] = 0.0f;
    }

    void setParams(const RuinParams& p) { params_ = p; }

    void process(const float* const* in, float* const* out, int numSamples) {
        const double mode = std::clamp(static_cast<double>(params_.mode), 0.0, 1.0);
        // 驱动增益：1x .. 24x。除以 tanh(g) 做归一化，避免一拧就只是变响
        const double g = 1.0 + static_cast<double>(params_.drive) * 23.0;
        const double norm = 1.0 / std::tanh(g);
        // 位深：16 bit .. 3 bit
        const double bits = 16.0 - static_cast<double>(params_.crush) * 13.0;
        const double step = std::pow(2.0, -(bits - 1.0));
        const double ringAmt = std::clamp(static_cast<double>(params_.ring), 0.0, 1.0);
        const double ringInc = 2.0 * 3.14159265358979323846 *
                               static_cast<double>(params_.ringHz) / sr_;
        const double foldAmt = std::clamp(static_cast<double>(params_.fold), 0.0, 1.0);
        // 折叠前的推动增益：1x .. 9x。推到多少就折多少次，泛音随之爆增。
        const double foldGain = 1.0 + foldAmt * 8.0;

        for (int i = 0; i < numSamples; ++i) {
            phase_ += ringInc;
            if (phase_ > 2.0 * 3.14159265358979323846) phase_ -= 2.0 * 3.14159265358979323846;
            const double ringSig = std::sin(phase_);

            // 采样率压碎：每 1..32 个样本保持一次（随 crush 加深）
            const int hold = 1 + static_cast<int>(static_cast<double>(params_.crush) * 31.0);
            if (--holdCount_ <= 0) {
                holdCount_ = hold;
                hold_[0] = in[0][i];
                hold_[1] = in[1][i];
            }

            for (int ch = 0; ch < 2; ++ch) {
                const double dry = in[ch][i];
                double x = hold_[ch];

                // 环形调制
                x *= (1.0 - ringAmt) + ringAmt * ringSig;
                // 饱和
                x = std::tanh(x * g) * norm;
                // 波形折叠（干湿混合，保证 fold=0 时与旧行为逐位一致）
                if (foldAmt > 0.0) {
                    x = x * (1.0 - foldAmt) + foldTriangle(x * foldGain) * foldAmt;
                }
                // 位深压碎
                if (step > 0.0) x = std::round(x / step) * step;

                const double ruined = x;
                out[ch][i] = static_cast<float>(dry * (1.0 - mode) + ruined * mode);
            }
        }
    }

private:
    double sr_ = 48000.0;
    RuinParams params_{};
    double phase_ = 0.0;
    int holdCount_ = 1;
    float hold_[2] = {0.0f, 0.0f};
};

}  // namespace trane
