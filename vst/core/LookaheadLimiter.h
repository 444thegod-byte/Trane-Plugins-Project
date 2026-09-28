// LookaheadLimiter.h — 前瞻式峰值限制器
//
// 为什么必须有前瞻：
//   反馈式限制器（先量峰值、再降增益）对瞬态是无能为力的 ——
//   峰值到达那一刻，包络才刚刚开始往上爬，增益还是 1.0，于是必然过冲。
//   实测证据：阈值 0.95、起控 1ms 的反馈式限制器，在 +4.8dB 输出增益下
//   峰值冲到 1.0062（越界 0.6%），端到端验收因此判失败。
//
// 做法：
//   把信号延迟 L 个样本再输出，而增益由「还没延迟的」样本（也就是未来）决定。
//   用单调队列维护最近 L+1 个样本所需的最小增益；于是峰值真正到达输出端时，
//   增益早已降到位 —— 数学上不可能过冲。
//
//   正确性论证：
//     设 x[t] 是峰值样本。它对应的输出位置是 i = t+L。
//     该时刻队列窗口是 [t, t+L]，其中包含 gT[t] = thr/|x[t]|。
//     而 gSmooth ≤ gMin ≤ gT[t]，所以 y[i] = x[t]*gSmooth ≤ thr。∎
//
// 代价：引入 L 个样本的延迟（默认 2ms）。宿主必须被告知（setLatencySamples），
//       否则干声会比其他轨道晚 2ms。
//
// 压降立即生效（保证不过冲），恢复缓慢（150ms，避免抽吸感）。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace trane {

class LookaheadLimiter {
public:
    static constexpr double kThreshold = 0.95;   // 留 0.05 的余量，别贴着 1.0
    static constexpr double kLookaheadMs = 2.0;
    static constexpr double kReleaseMs = 150.0;

    void prepare(double sampleRate, int maxBlockSize) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        look_ = std::max(1, static_cast<int>(kLookaheadMs * 0.001 * sr_));
        releaseCoef_ = 1.0 - std::exp(-1.0 / (kReleaseMs * 0.001 * sr_));

        const std::size_t cap =
            static_cast<std::size_t>(std::max(1, maxBlockSize) + look_ + 8);
        delayL_.assign(cap, 0.0f);
        delayR_.assign(cap, 0.0f);

        // 单调队列：窗口内最多 look_+1 个候选，容量给 look_+2 足够
        qCap_ = look_ + 2;
        qVal_.assign(static_cast<std::size_t>(qCap_), 1.0);
        qTime_.assign(static_cast<std::size_t>(qCap_), 0);
        reset();
    }

    void reset() {
        std::fill(delayL_.begin(), delayL_.end(), 0.0f);
        std::fill(delayR_.begin(), delayR_.end(), 0.0f);
        writeIdx_ = 0;
        qHead_ = 0;
        qCount_ = 0;
        t_ = 0;
        smooth_ = 1.0;
        gainReduction_ = 1.0f;
    }

    // 宿主需要的延迟补偿量
    int latencySamples() const { return look_; }

    // 就地处理。
    // enabled=false 时只延迟、不压缩 —— 延迟保持恒定，宿主不必重新对齐。
    void process(float* l, float* r, int numSamples, bool enabled) {
        if (numSamples <= 0 || delayL_.empty()) return;
        const int cap = static_cast<int>(delayL_.size());

        for (int i = 0; i < numSamples; ++i) {
            const double x0 = static_cast<double>(l[i]);
            const double x1 = static_cast<double>(r[i]);

            // --- 写入延迟线，取出 look_ 个样本之前的那一个 ---
            delayL_[static_cast<std::size_t>(writeIdx_)] = static_cast<float>(x0);
            delayR_[static_cast<std::size_t>(writeIdx_)] = static_cast<float>(x1);
            int rd = writeIdx_ - look_;
            if (rd < 0) rd += cap;
            const double y0 = static_cast<double>(delayL_[static_cast<std::size_t>(rd)]);
            const double y1 = static_cast<double>(delayR_[static_cast<std::size_t>(rd)]);
            if (++writeIdx_ >= cap) writeIdx_ = 0;

            // --- 目标增益：由当前（对输出而言是未来）的样本决定 ---
            // 两声道联动取最大值，避免压缩把声像拉扯歪
            const double a = std::max(std::fabs(x0), std::fabs(x1));
            const double target = (a > kThreshold) ? kThreshold / a : 1.0;

            // --- 单调队列维护前瞻窗口内的最小增益（O(1) 摊还）---
            while (qCount_ > 0 && qVal_[static_cast<std::size_t>(back())] >= target) {
                --qCount_;
            }
            const int ins = (qHead_ + qCount_) % qCap_;
            qVal_[static_cast<std::size_t>(ins)] = target;
            qTime_[static_cast<std::size_t>(ins)] = t_;
            ++qCount_;
            // 超出前瞻窗口的候选出队
            while (qCount_ > 0 && t_ - qTime_[static_cast<std::size_t>(qHead_)] > look_) {
                qHead_ = (qHead_ + 1) % qCap_;
                --qCount_;
            }

            double g = 1.0;
            if (enabled) {
                const double gMin = qVal_[static_cast<std::size_t>(qHead_)];
                if (gMin < smooth_) {
                    smooth_ = gMin;  // 压低立即生效
                } else {
                    smooth_ += (gMin - smooth_) * releaseCoef_;  // 恢复缓慢
                }
                g = smooth_;
            } else {
                smooth_ = 1.0;
            }

            gainReduction_ = static_cast<float>(g);
            l[i] = static_cast<float>(y0 * g);
            r[i] = static_cast<float>(y1 * g);
            ++t_;
        }
    }

    float lastGainReduction() const { return gainReduction_; }

private:
    int back() const { return (qHead_ + qCount_ - 1) % qCap_; }

    double sr_ = 48000.0;
    int look_ = 96;
    double releaseCoef_ = 0.0;

    std::vector<float> delayL_;
    std::vector<float> delayR_;
    int writeIdx_ = 0;

    int qCap_ = 2;
    std::vector<double> qVal_;
    std::vector<long long> qTime_;
    int qHead_ = 0;
    int qCount_ = 0;

    long long t_ = 0;
    double smooth_ = 1.0;
    float gainReduction_ = 1.0f;
};

}  // namespace trane
