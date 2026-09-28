// FreezeLoop.h — Träne 的冻结引擎：把"最近 N 毫秒"钉成无限无缝循环
//
// 用户要的语义（原话）：
//   "声音开启 freeze 会一直响，不会断，无限循环，不跟随 tempo/bpm，
//    loop 时间就是 loop 的区间声音的长短"
//
// 于是本类只有三件事：
//   1. 冻结瞬间：把循环区间钉在写头前方 loopMs 毫秒处，记下 [S, S+L)
//   2. 冻结期间：以 1 样本/样本 的速率循环读这段，永不停止
//   3. 接缝无缝：在循环末尾的 seam 个样本里，把"循环起点之前"的真实音频
//      淡进来。于是环绕那一瞬的输出是 buf[S-1] -> buf[S]，
//      而这两点在原始录音里本来就是连续的 —— 数学上不存在跳变。
//
// 全程不涉及任何 tempo / BPM / transport 概念。循环长度只由 loopMs 和采样率决定。
#pragma once

#include "CaptureBuffer.h"

#include <cstdint>

namespace trane {

class FreezeLoop {
public:
    static constexpr int kMaxChannels = 8;

    void prepare(CaptureBuffer* buffer, double sampleRate);
    void reset();

    // 点击锁定：true 进入冻结，false 解除
    void setFrozen(bool on);
    // 循环区间长度（毫秒）。冻结中改动会做一次短凹陷，避免咔哒。
    void setLoopMs(double ms);
    // 接缝交叉淡化长度（毫秒）。0 = 不淡化（会有咔哒，Ruin 模式可用）
    void setSeamMs(double ms);
    // dry <-> 循环 的交叉淡化时长（毫秒）
    void setSmoothMs(double ms);

    // in 与 out 可以是同一块内存。in 始终被采集进缓冲区。
    void process(const float* const* in, float* const* out, int numSamples);

    bool isFrozen() const { return frozen_; }
    std::int64_t loopLengthSamples() const { return loopLen_; }
    std::int64_t loopStartIndex() const { return loopStart_; }
    std::int64_t seamSamples() const { return seam_; }
    double playPhase() const { return phase_; }
    double mixGain() const { return mix_; }

private:
    void applySnapshot();
    void beginReseek();

    CaptureBuffer* buf_ = nullptr;
    double sr_ = 48000.0;

    bool frozen_ = false;
    double loopMs_ = 250.0;
    double seamMs_ = 10.0;
    double smoothMs_ = 6.0;

    std::int64_t loopStart_ = 0;
    std::int64_t loopLen_ = 0;
    std::int64_t seam_ = 0;
    double phase_ = 0.0;
    double mix_ = 0.0;

    std::int64_t reseekLeft_ = 0;
    std::int64_t reseekTotal_ = 0;
    std::int64_t reseekHalf_ = 0;
    bool reseekPending_ = false;
};

}  // namespace trane
