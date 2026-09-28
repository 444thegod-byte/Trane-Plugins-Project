#include "PlateReverb.h"

#include <algorithm>
#include <cmath>

namespace trane {

namespace {
constexpr double kPi = 3.14159265358979323846;

// Freeverb 在 44100Hz 下的原始延迟长度
const int kCombTuning[PlateReverb::kCombs] = {1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617};
const int kAllpassTuning[PlateReverb::kAllpasses] = {556, 441, 341, 225};
const int kStereoSpread = 23;

constexpr float kFixedGain = 0.015f;
constexpr float kWetGain = 1.0f;
constexpr double kMaxModSeconds = 0.0008;  // 调制深度上限 0.8ms
}  // namespace

void PlateReverb::prepare(double sampleRate) {
    sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
    const double scale = sr_ / 44100.0;
    const double maxMod = kMaxModSeconds * sr_;

    for (int ch = 0; ch < 2; ++ch) {
        for (int i = 0; i < kCombs; ++i) {
            baseComb_[ch][i] = (kCombTuning[i] + (ch == 1 ? kStereoSpread : 0)) * scale;
            const int len =
                static_cast<int>(baseComb_[ch][i] * kMaxSizeScale + maxMod) + 8;
            combs_[ch][i].buf.assign(static_cast<std::size_t>(len), 0.0f);
            combs_[ch][i].size = len;
            combs_[ch][i].writeIdx = 0;
            combs_[ch][i].filterStore = 0.0f;
            // 每条梳状的调制相位错开，避免所有延迟线同步摆动（那样会变成明显的颤音）
            combs_[ch][i].modPhase = static_cast<double>(i) * 0.7 + static_cast<double>(ch) * 0.31;
        }
        for (int i = 0; i < kAllpasses; ++i) {
            baseAllpass_[ch][i] = (kAllpassTuning[i] + (ch == 1 ? kStereoSpread : 0)) * scale;
            const int len = static_cast<int>(baseAllpass_[ch][i]) + 8;
            allpasses_[ch][i].buf.assign(static_cast<std::size_t>(len), 0.0f);
            allpasses_[ch][i].size = len;
            allpasses_[ch][i].writeIdx = 0;
        }
    }

    updateCoefficients();
    reset();
}

void PlateReverb::reset() {
    for (int ch = 0; ch < 2; ++ch) {
        for (int i = 0; i < kCombs; ++i) {
            std::fill(combs_[ch][i].buf.begin(), combs_[ch][i].buf.end(), 0.0f);
            combs_[ch][i].writeIdx = 0;
            combs_[ch][i].filterStore = 0.0f;
        }
        for (int i = 0; i < kAllpasses; ++i) {
            std::fill(allpasses_[ch][i].buf.begin(), allpasses_[ch][i].buf.end(), 0.0f);
            allpasses_[ch][i].writeIdx = 0;
        }
    }
}

void PlateReverb::updateCoefficients() {
    const double sizeScale = 0.5 + static_cast<double>(params_.size) * (kMaxSizeScale - 0.5);
    // 反馈 0.70 .. 0.99 —— 上限配合放大后的延迟线可得到十几秒的尾音
    const float fb = static_cast<float>(0.70 + static_cast<double>(params_.tail) * 0.29);
    const float damp = static_cast<float>(static_cast<double>(params_.damp) * 0.4);
    const float apFb = static_cast<float>(0.5 + static_cast<double>(params_.diffuse) * 0.3);

    for (int ch = 0; ch < 2; ++ch) {
        for (int i = 0; i < kCombs; ++i) {
            combs_[ch][i].delay = baseComb_[ch][i] * sizeScale;
            combs_[ch][i].feedback = fb;
            combs_[ch][i].damp1 = damp;
            combs_[ch][i].damp2 = 1.0f - damp;
            // 调制速率 0.3 .. 0.8 Hz，每条不同
            combs_[ch][i].modInc =
                2.0 * kPi * (0.3 + 0.06 * static_cast<double>(i) + 0.02 * static_cast<double>(ch)) /
                sr_;
        }
        for (int i = 0; i < kAllpasses; ++i) {
            allpasses_[ch][i].feedback = apFb;
        }
    }

    modDepthSamples_ = static_cast<double>(params_.modDepth) * kMaxModSeconds * sr_;
}

float PlateReverb::combFeedback() const {
    return combs_[0][0].feedback;
}

void PlateReverb::process(const float* const* in, float* const* out, int numSamples) {
    const float mix = params_.mix < 0.0f ? 0.0f : (params_.mix > 1.0f ? 1.0f : params_.mix);

    auto combProcess = [this](Comb& c, float x) -> float {
        c.modPhase += c.modInc;
        if (c.modPhase > 2.0 * kPi) c.modPhase -= 2.0 * kPi;
        const double d = c.delay + modDepthSamples_ * std::sin(c.modPhase);

        double rp = static_cast<double>(c.writeIdx) - d;
        if (rp < 0.0) rp += static_cast<double>(c.size);
        int i0 = static_cast<int>(rp);
        if (i0 < 0) i0 = 0;
        if (i0 >= c.size) i0 -= c.size;
        int i1 = i0 + 1;
        if (i1 >= c.size) i1 = 0;
        const float frac = static_cast<float>(rp - static_cast<double>(i0));
        const float y = c.buf[i0] + (c.buf[i1] - c.buf[i0]) * frac;

        c.filterStore = y * c.damp2 + c.filterStore * c.damp1;
        c.buf[c.writeIdx] = x + c.filterStore * c.feedback;
        if (++c.writeIdx >= c.size) c.writeIdx = 0;
        return y;
    };

    auto allpassProcess = [](Allpass& a, float x) -> float {
        const float bufout = a.buf[a.writeIdx];
        const float y = -x + bufout;
        a.buf[a.writeIdx] = x + bufout * a.feedback;
        if (++a.writeIdx >= a.size) a.writeIdx = 0;
        return y;
    };

    for (int i = 0; i < numSamples; ++i) {
        const float mono = (in[0][i] + in[1][i]) * 0.5f;
        const float x = mono * kFixedGain;

        float wet[2] = {0.0f, 0.0f};
        for (int ch = 0; ch < 2; ++ch) {
            float acc = 0.0f;
            for (int c = 0; c < kCombs; ++c) {
                acc += combProcess(combs_[ch][c], x);
            }
            for (int a = 0; a < kAllpasses; ++a) {
                acc = allpassProcess(allpasses_[ch][a], acc);
            }
            wet[ch] = acc * kWetGain;
        }

        const float dry = 1.0f - mix;
        out[0][i] = in[0][i] * dry + wet[0] * mix;
        out[1][i] = in[1][i] * dry + wet[1] * mix;
    }
}

}  // namespace trane
