#include "FreezeLoop.h"

#include <algorithm>
#include <cmath>

namespace trane {

void FreezeLoop::prepare(CaptureBuffer* buffer, double sampleRate) {
    buf_ = buffer;
    sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
    reset();
}

void FreezeLoop::reset() {
    frozen_ = false;
    loopStart_ = 0;
    loopLen_ = 0;
    seam_ = 0;
    phase_ = 0.0;
    mix_ = 0.0;
    reseekLeft_ = 0;
    reseekTotal_ = 0;
    reseekHalf_ = 0;
    reseekPending_ = false;
}

// 冻结瞬间（以及冻结中改 LOOP 长度时）：重新钉住循环区间。
// 循环终点永远等于当前写头，于是区间内容就是"最近 loopMs 毫秒"。
void FreezeLoop::applySnapshot() {
    if (buf_ == nullptr) return;

    const std::int64_t cap = buf_->capacity();

    std::int64_t want = static_cast<std::int64_t>(loopMs_ * 0.001 * sr_);
    if (want < 2) want = 2;
    if (want > cap - 2) want = cap - 2;
    loopLen_ = want;

    std::int64_t start = buf_->writeHead() - loopLen_;
    while (start < 0) start += cap;
    loopStart_ = start % cap;

    // 接缝淡化长度：不超过循环长度的四分之一（短循环不能被淡化吃掉太多）
    std::int64_t seam = static_cast<std::int64_t>(seamMs_ * 0.001 * sr_);
    if (seam > loopLen_ / 4) seam = loopLen_ / 4;
    if (seam < 2) seam = 0;
    // 前置素材必须真的录过，否则淡进来的是空白，会造成音量凹陷而不是消除咔哒
    if (!buf_->hasHistory(loopLen_ + seam)) seam = 0;
    seam_ = seam;

    phase_ = 0.0;
}

void FreezeLoop::beginReseek() {
    reseekTotal_ = static_cast<std::int64_t>(smoothMs_ * 0.001 * sr_);
    if (reseekTotal_ < 16) reseekTotal_ = 16;
    reseekHalf_ = reseekTotal_ / 2;
    reseekLeft_ = reseekTotal_;
    reseekPending_ = true;
}

void FreezeLoop::setFrozen(bool on) {
    if (on == frozen_) return;
    frozen_ = on;
    if (on) applySnapshot();
}

void FreezeLoop::setLoopMs(double ms) {
    if (ms < 1.0) ms = 1.0;
    if (ms == loopMs_) return;
    loopMs_ = ms;
    // 冻结中改长度：不立刻换内容，交给 process 里的凹陷在静音点切换
    if (frozen_) beginReseek();
}

void FreezeLoop::setSeamMs(double ms) {
    seamMs_ = (ms < 0.0) ? 0.0 : ms;
}

void FreezeLoop::setSmoothMs(double ms) {
    smoothMs_ = (ms < 1.0) ? 1.0 : ms;
}

void FreezeLoop::process(const float* const* in, float* const* out, int numSamples) {
    if (buf_ == nullptr) {
        for (int ch = 0; ch < 2; ++ch)
            for (int i = 0; i < numSamples; ++i) out[ch][i] = in[ch][i];
        return;
    }

    const int nch = std::min(buf_->channels(), kMaxChannels);
    const double target = frozen_ ? 1.0 : 0.0;
    const double step = 1.0 / (smoothMs_ * 0.001 * sr_);

    for (int i = 0; i < numSamples; ++i) {
        // 1) 持续采集。冻结时写头停住，保护正在循环的区域不被覆盖。
        buf_->writeFrame(in, i, !frozen_);

        // 2) 读循环。注意：解除冻结时 mix_ 还在往下走，这段时间必须继续读，
        //    否则交叉淡化会变成"淡出到静音再淡入干声"。
        float loopVal[kMaxChannels] = {0.0f};
        const bool readingLoop = (frozen_ || mix_ > 0.0) && loopLen_ > 0;
        if (readingLoop) {
            const std::int64_t p = static_cast<std::int64_t>(phase_);
            const std::int64_t seamStart = loopLen_ - seam_;
            for (int ch = 0; ch < nch; ++ch) {
                float v = buf_->readAt(ch, loopStart_ + p);
                if (seam_ > 0 && p >= seamStart) {
                    // 把循环起点"之前"的真实音频淡进来，环绕处因此连续
                    const double a =
                        static_cast<double>(p - seamStart) / static_cast<double>(seam_);
                    const float pre = buf_->readAt(ch, loopStart_ + p - loopLen_);
                    v = v * static_cast<float>(1.0 - a) + pre * static_cast<float>(a);
                }
                loopVal[ch] = v;
            }
            phase_ += 1.0;
            if (phase_ >= static_cast<double>(loopLen_)) {
                phase_ -= static_cast<double>(loopLen_);
            }
        }

        // 3) dry <-> 循环 的线性交叉淡化
        if (mix_ < target) {
            mix_ = std::min(target, mix_ + step);
        } else if (mix_ > target) {
            mix_ = std::max(target, mix_ - step);
        }

        // 4) 冻结中改 LOOP 长度：凹陷到静音的中点再换内容
        double dip = 1.0;
        if (frozen_ && reseekLeft_ > 0) {
            --reseekLeft_;
            if (reseekPending_ && reseekLeft_ <= reseekHalf_) {
                reseekPending_ = false;
                applySnapshot();
            }
            dip = std::abs(2.0 * static_cast<double>(reseekLeft_) /
                               static_cast<double>(reseekTotal_) -
                           1.0);
        }

        const float g = static_cast<float>(mix_ * dip);
        const float inv = 1.0f - g;
        for (int ch = 0; ch < nch; ++ch) {
            out[ch][i] = in[ch][i] * inv + loopVal[ch] * g;
        }
    }
}

}  // namespace trane
