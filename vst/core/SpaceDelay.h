// SpaceDelay.h — 立体声延迟（HUGE SPACE 的延迟那一半）
//
// 原始需求第 5 条要的是「类 Fors Box 的混响/延迟」。混响那半在 PlateReverb.h，
// 这里是延迟那半。
//
// 三个让它听起来不像"数字延迟"的细节：
//   1) 延时时间不是硬切，而是用 50ms 一阶滑过去 —— 拧时间旋钮会像老磁带一样滑音。
//   2) 读位置叠了一层极轻的固定调制（0.15ms @ 0.25Hz）。静态数字延迟在长反馈下
//      会有金属鸣响（因为所有回声的相位关系永远不变），轻微抖动就把它化开了。
//      这个不做成旋钮：它是"消除缺陷"，不是"创作参数"。
//   3) 反馈路径里带阻尼低通 + 隔直。没有隔直的话，反馈环会把直流慢慢堆起来，
//      长尾最后变成一段偏移而不是声音。
//
// 反馈上限锁死在 0.92：再往上在长延时下会失控自激。真想要失控，用 RUIN 那一档。
#pragma once

#include <algorithm>
#include <cmath>
#include <vector>

namespace trane {

struct DelayParams {
    bool on = false;
    float timeMs = 375.0f;
    float feedback = 0.45f;
    float damp = 0.35f;
    float pingPong = 0.0f;  // 0 = 左右独立，1 = 完全交叉（ping-pong）
    float mix = 0.35f;
};

class SpaceDelay {
public:
    static constexpr double kMaxDelayMs = 2500.0;
    static constexpr double kMaxFeedback = 0.92;
    static constexpr double kModMs = 0.15;
    static constexpr double kModHz = 0.25;

    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        const int cap = static_cast<int>(kMaxDelayMs * 0.001 * sr_) + 8;
        bufL_.assign(static_cast<std::size_t>(cap), 0.0f);
        bufR_.assign(static_cast<std::size_t>(cap), 0.0f);
        timeGlide_ = 1.0 - std::exp(-1.0 / (0.050 * sr_));
        modInc_ = 2.0 * kPi * kModHz / sr_;
        reset();
    }

    void reset() {
        std::fill(bufL_.begin(), bufL_.end(), 0.0f);
        std::fill(bufR_.begin(), bufR_.end(), 0.0f);
        writeIdx_ = 0;
        delaySamples_ = 0.375 * sr_;
        modPhase_ = 0.0;
        lpL_ = lpR_ = 0.0;
        dcX1L_ = dcX1R_ = 0.0;
        dcY1L_ = dcY1R_ = 0.0;
    }

    void setParams(const DelayParams& p) { params_ = p; }

    void process(float* l, float* r, int numSamples) {
        if (numSamples <= 0 || bufL_.empty()) return;
        const int cap = static_cast<int>(bufL_.size());

        const double target = std::min(kMaxDelayMs, std::max(1.0, static_cast<double>(params_.timeMs))) *
                              0.001 * sr_;
        // 关掉时不喂反馈：这样重新打开是干净地从当前声音长出来，
        // 而不是把"关闭期间偷偷堆起来的回声"一次性倒出来。
        const double fb = params_.on
                              ? std::min(kMaxFeedback, std::max(0.0, static_cast<double>(params_.feedback)))
                              : 0.0;
        const double pp = std::min(1.0, std::max(0.0, static_cast<double>(params_.pingPong)));
        const double mix = params_.on
                               ? std::min(1.0, std::max(0.0, static_cast<double>(params_.mix)))
                               : 0.0;

        // 阻尼：damp=0 → 18kHz（几乎不滤），damp=1 → 约 540Hz（很暗）
        const double dampHz = 18000.0 * std::pow(0.03, static_cast<double>(params_.damp));
        const double lpCoef = 1.0 - std::exp(-2.0 * kPi * dampHz / sr_);

        const double modSamples = kModMs * 0.001 * sr_;

        for (int i = 0; i < numSamples; ++i) {
            // 延时时间平滑（拧旋钮时的磁带式滑音）
            delaySamples_ += (target - delaySamples_) * timeGlide_;

            modPhase_ += modInc_;
            if (modPhase_ >= 2.0 * kPi) modPhase_ -= 2.0 * kPi;

            double rp = static_cast<double>(writeIdx_) - delaySamples_ -
                        std::sin(modPhase_) * modSamples;
            while (rp < 0.0) rp += static_cast<double>(cap);
            while (rp >= static_cast<double>(cap)) rp -= static_cast<double>(cap);
            const int i0 = static_cast<int>(rp);
            const int i1 = (i0 + 1) % cap;
            const double f = rp - static_cast<double>(i0);
            const double dL = static_cast<double>(bufL_[static_cast<std::size_t>(i0)]) * (1.0 - f) +
                              static_cast<double>(bufL_[static_cast<std::size_t>(i1)]) * f;
            const double dR = static_cast<double>(bufR_[static_cast<std::size_t>(i0)]) * (1.0 - f) +
                              static_cast<double>(bufR_[static_cast<std::size_t>(i1)]) * f;

            // 交叉反馈
            const double fbInL = dL * (1.0 - pp) + dR * pp;
            const double fbInR = dR * (1.0 - pp) + dL * pp;

            // 反馈路径：阻尼低通
            lpL_ += (fbInL - lpL_) * lpCoef;
            lpR_ += (fbInR - lpR_) * lpCoef;

            // 反馈路径：隔直（R=0.9995 → 约 15Hz 以下被削掉）
            const double dcOutL = lpL_ - dcX1L_ + 0.9995 * dcY1L_;
            const double dcOutR = lpR_ - dcX1R_ + 0.9995 * dcY1R_;
            dcX1L_ = lpL_;
            dcX1R_ = lpR_;
            dcY1L_ = dcOutL;
            dcY1R_ = dcOutR;

            const double inL = static_cast<double>(l[i]);
            const double inR = static_cast<double>(r[i]);

            bufL_[static_cast<std::size_t>(writeIdx_)] = static_cast<float>(inL + dcOutL * fb);
            bufR_[static_cast<std::size_t>(writeIdx_)] = static_cast<float>(inR + dcOutR * fb);
            if (++writeIdx_ >= cap) writeIdx_ = 0;

            l[i] = static_cast<float>(inL * (1.0 - mix) + dL * mix);
            r[i] = static_cast<float>(inR * (1.0 - mix) + dR * mix);
        }
    }

private:
    static constexpr double kPi = 3.14159265358979323846;

    double sr_ = 48000.0;
    DelayParams params_{};

    std::vector<float> bufL_, bufR_;
    int writeIdx_ = 0;
    double delaySamples_ = 18000.0;
    double timeGlide_ = 0.0;
    double modPhase_ = 0.0;
    double modInc_ = 0.0;
    double lpL_ = 0.0, lpR_ = 0.0;
    double dcX1L_ = 0.0, dcX1R_ = 0.0, dcY1L_ = 0.0, dcY1R_ = 0.0;
};

}  // namespace trane
