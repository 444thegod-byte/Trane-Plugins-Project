#include "GrainCloud.h"

#include <algorithm>
#include <cmath>

namespace trane {

namespace {
constexpr double kPi = 3.14159265358979323846;

inline double clampd(double v, double lo, double hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}
}  // namespace

void GrainCloud::prepare(CaptureBuffer* buffer, double sampleRate) {
    buf_ = buffer;
    sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
    buildWindow();
    reset();
}

void GrainCloud::buildWindow() {
    for (int i = 0; i < kWindowSize; ++i) {
        const double t = static_cast<double>(i) / static_cast<double>(kWindowSize - 1);
        window_[i] = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * kPi * t));
    }
}

void GrainCloud::reset() {
    for (int v = 0; v < kMaxVoices; ++v) voices_[v] = Voice{};
    spawnPhase_ = 0.0;
    rangeStart_ = 0;
    rangeLength_ = 0;
    // 固定种子：渲染必须可复现，否则测试无法断言
    rngState_ = 0x9E3779B9u;
    spawned_ = 0;
}

void GrainCloud::setReadRange(std::int64_t startIndex, std::int64_t length) {
    rangeStart_ = startIndex;
    rangeLength_ = length > 0 ? length : 0;
}

float GrainCloud::nextRandom() {
    rngState_ ^= rngState_ << 13;
    rngState_ ^= rngState_ >> 17;
    rngState_ ^= rngState_ << 5;
    return static_cast<float>(rngState_ >> 8) / 16777216.0f;
}

void GrainCloud::spawn() {
    int idx = -1;
    for (int v = 0; v < kMaxVoices; ++v) {
        if (!voices_[v].active) {
            idx = v;
            break;
        }
    }
    if (idx < 0) {
        // 声部用满：抢占进行得最深的那个
        double deepest = -1.0;
        int pick = 0;
        for (int v = 0; v < kMaxVoices; ++v) {
            const double done =
                static_cast<double>(voices_[v].age) / static_cast<double>(voices_[v].length);
            if (done > deepest) {
                deepest = done;
                pick = v;
            }
        }
        idx = pick;
    }

    Voice& vo = voices_[idx];

    const double len = std::max(2.0, static_cast<double>(params_.sizeMs) * 0.001 * sr_);
    vo.length = static_cast<std::int64_t>(len);
    vo.age = 0;
    vo.windowPos = 0.0;
    vo.windowInc = static_cast<double>(kWindowSize) / len;

    // 起始位置：position 给基准，spray 给随机量
    const double base =
        static_cast<double>(rangeStart_) + static_cast<double>(params_.position) *
                                               static_cast<double>(rangeLength_);
    const double spread =
        static_cast<double>(params_.spray) * static_cast<double>(rangeLength_) * 0.5;
    vo.pos = base + (static_cast<double>(nextRandom()) * 2.0 - 1.0) * spread;

    // 速率与方向
    double rate = static_cast<double>(params_.rate);
    if (params_.rateSpread > 0.0f) {
        rate *= 1.0 + (static_cast<double>(nextRandom()) * 2.0 - 1.0) *
                          static_cast<double>(params_.rateSpread);
    }
    if (rate < 0.01) rate = 0.01;
    const double dir = (nextRandom() < params_.reverseProb) ? -1.0 : 1.0;
    vo.inc = rate * dir;

    // 声场
    double pan = 0.5 + (static_cast<double>(nextRandom()) * 2.0 - 1.0) * 0.5 *
                           static_cast<double>(params_.panSpread);
    pan = clampd(pan, 0.0, 1.0);
    vo.panL = static_cast<float>(std::cos(pan * kPi * 0.5));
    vo.panR = static_cast<float>(std::sin(pan * kPi * 0.5));

    // 电平归一化：
    //   1. 补偿汉宁窗的 RMS 损失（sqrt(3/8)）—— 不补的话开粒子会平白掉 4dB
    //   2. 按重叠数的平方根缩放 —— 同时响的粒子越多，单个越轻
    // 于是"满密度 + 居中声场"下，粒子云每声道电平与源一致。
    constexpr double kHannRms = 0.6123724356957945;  // sqrt(3/8)
    const double overlap = std::max(
        1.0, static_cast<double>(params_.density) * static_cast<double>(params_.sizeMs) * 0.001);
    const double norm = 1.0 / (kHannRms * std::sqrt(overlap));
    vo.gain = static_cast<float>(static_cast<double>(params_.level) * norm);

    vo.active = true;
    ++spawned_;
}

int GrainCloud::process(const float* const* in, float* const* out, int numSamples) {
    if (buf_ == nullptr) {
        for (int ch = 0; ch < 2; ++ch)
            for (int i = 0; i < numSamples; ++i) out[ch][i] = in[ch][i];
        return 0;
    }

    const int nch = std::min(buf_->channels(), 2);
    const double mix = clampd(static_cast<double>(params_.mix), 0.0, 1.0);
    const bool canSpawn = params_.density > 0.0f && rangeLength_ > 1;
    int triggered = 0;

    for (int i = 0; i < numSamples; ++i) {
        if (canSpawn) {
            spawnPhase_ += static_cast<double>(params_.density) / sr_;
            while (spawnPhase_ >= 1.0) {
                spawnPhase_ -= 1.0;
                spawn();
                ++triggered;
            }
        }

        float gL = 0.0f;
        float gR = 0.0f;
        for (int v = 0; v < kMaxVoices; ++v) {
            Voice& vo = voices_[v];
            if (!vo.active) continue;

            int wi = static_cast<int>(vo.windowPos);
            if (wi < 0) wi = 0;
            if (wi >= kWindowSize) wi = kWindowSize - 1;
            const float w = window_[wi] * vo.gain;

            const float sL = buf_->readInterp(0, vo.pos) * w;
            const float sR =
                (nch > 1 ? buf_->readInterp(1, vo.pos) : buf_->readInterp(0, vo.pos)) * w;
            gL += sL * vo.panL;
            gR += sR * vo.panR;

            vo.pos += vo.inc;
            vo.windowPos += vo.windowInc;
            if (++vo.age >= vo.length) vo.active = false;
        }

        const float inv = static_cast<float>(1.0 - mix);
        const float m = static_cast<float>(mix);
        out[0][i] = in[0][i] * inv + gL * m;
        if (nch > 1) {
            out[1][i] = in[1][i] * inv + gR * m;
        } else if (numSamples > 0) {
            out[1][i] = in[1][i];
        }
    }

    return triggered;
}

int GrainCloud::activeVoices() const {
    int n = 0;
    for (int v = 0; v < kMaxVoices; ++v) {
        if (voices_[v].active) ++n;
    }
    return n;
}

}  // namespace trane
