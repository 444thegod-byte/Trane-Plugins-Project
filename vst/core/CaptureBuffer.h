// CaptureBuffer.h — Träne 的持续采集环形缓冲区
//
// 设计要点：
//  * 一直写入，永不停止（除非调用方说"冻结中，别写"）。
//  * 位置用"环上样本序号"表示，支持整数读取（循环播放，快）和线性插值读取（粒子变速，慢但准）。
//  * 容量以秒为单位预先分配，音频线程里绝不做任何内存分配。
#pragma once

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace trane {

class CaptureBuffer {
public:
    void prepare(int numChannels, double sampleRate, double capacitySeconds) {
        nch_ = numChannels > 0 ? numChannels : 1;
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        cap_ = static_cast<std::int64_t>(capacitySeconds * sr_);
        if (cap_ < 2) cap_ = 2;
        data_.assign(static_cast<std::size_t>(nch_) * static_cast<std::size_t>(cap_), 0.0f);
        reset();
    }

    void reset() {
        std::fill(data_.begin(), data_.end(), 0.0f);
        w_ = 0;
        written_ = 0;
    }

    // 写入第 i 帧。advance 为 false 时完全不写（冻结期间保护正在循环的区域）。
    inline void writeFrame(const float* const* in, int i, bool advance) {
        if (!advance) return;
        for (int ch = 0; ch < nch_; ++ch) {
            data_[static_cast<std::size_t>(ch) * static_cast<std::size_t>(cap_) +
                  static_cast<std::size_t>(w_)] = in[ch][i];
        }
        if (++w_ >= cap_) w_ = 0;
        ++written_;
    }

    // 整数读取，自动环绕。用于速率为 1.0 的循环播放。
    inline float readAt(int ch, std::int64_t index) const {
        std::int64_t i = index % cap_;
        if (i < 0) i += cap_;
        return data_[static_cast<std::size_t>(ch) * static_cast<std::size_t>(cap_) +
                     static_cast<std::size_t>(i)];
    }

    // 线性插值读取。pos 可以是任意实数（含负数），会自动环绕。
    inline float readInterp(int ch, double pos) const {
        const double capd = static_cast<double>(cap_);
        double p = std::fmod(pos, capd);
        if (p < 0.0) p += capd;
        const std::int64_t i0 = static_cast<std::int64_t>(p);
        const std::int64_t i1 = (i0 + 1 >= cap_) ? 0 : i0 + 1;
        const float frac = static_cast<float>(p - static_cast<double>(i0));
        const float* base =
            data_.data() + static_cast<std::size_t>(ch) * static_cast<std::size_t>(cap_);
        const float a = base[i0];
        return a + (base[i1] - a) * frac;
    }

    int channels() const { return nch_; }
    std::int64_t capacity() const { return cap_; }
    std::int64_t writeHead() const { return w_; }
    std::int64_t written() const { return written_; }
    double sampleRate() const { return sr_; }

    // 已经采够了 needSamples 个样本吗？（循环接缝的前置素材是否可用）
    bool hasHistory(std::int64_t needSamples) const { return written_ >= needSamples; }

private:
    std::vector<float> data_;
    int nch_ = 0;
    std::int64_t cap_ = 0;
    std::int64_t w_ = 0;
    std::int64_t written_ = 0;
    double sr_ = 48000.0;
};

}  // namespace trane
