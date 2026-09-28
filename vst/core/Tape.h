// Tape.h — 磁带变速 / 停转（tape stop）
//
// 解构俱乐部里另一个标志性动作：把声音像磁带一样"拉住"——
// 速率从 1 一路拧到 0，音高掉下去，最后定死在一个点上。
// 反向拧过 1 是快进：加速 + 升调。
//
// 做法：
//   自带 8 秒环形缓冲，一直写。
//   读指针以 speed 样本/样本 推进，线性插值读 —— 所以音高是连续变化的，
//   不是分段跳的（这是"磁带"而不是"采样率压碎"的关键区别）。
//
//   speed 目标值用 150ms 一阶平滑。这一步才是"磁带感"的真正来源：
//   直接把 speed 瞬变过去只会听到跳变；平滑之后才是那种被人用手按住
//   卷轴、转速慢慢掉下去最后停住的滑音。
//
// ---- wow/flutter 为什么是"有界偏移"而不是"乘在速率上" ----
//   最直觉的写法是 readAbs += speed * (1 + wob)。但抖动是随时间变化的，
//   它会被积分成读指针的位置偏移，偏移量随抖动深度无界增长 ——
//   深度一大，读指针就会跑到写头前面去，撞上限位，抖动变成"只往一边摆"。
//   所以这里拆成两件事：
//     匀速位置 posAbs_   += speedSm_           （只有它参与"带子存量"的计算）
//     抖动偏移  wobOffset_ = 有界 LFO 位移      （上限 3ms，永远不累积）
//   读位置 = posAbs_ - wobOffset_。
//   位移的导数就是瞬时速率偏差，所以听感上仍然是完整的 wow/flutter，
//   但位置永远在 ±3ms 内摆动，不会漂走。
//
// ---- 关于"带子会跑完"（这是物理事实，不是 bug）----
//   写头以实时速率前进，读头以 speed 前进。speed<1 时读头必然越来越落后，
//   落后的距离 = 磁带存量。8 秒缓冲就是磁带的总长：
//     speed=0.5 → 约 16 秒后才把带子用完
//     speed=0   → 见下面"停转"一节，可以无限保持
//   带子用完后读头会被迫回到 1x。为了不出现"速率瞬间从 0.5 跳回 1"的咔哒，
//   最后 42ms 做软限位：速率平滑地滑回 1x，听感上是磁带被拉紧、自然回到原速。
//
// ---- 停转为什么必须单独处理（这里踩过一次坑）----
//   最初停转只靠"读头不动"，写头照常跑。结果 8 秒后写头绕回来覆盖了读头所在的
//   位置，读头开始读到新素材，软限位又把速率拉回 1x —— **停转会自己复活**。
//   端到端验收里就是这么暴露的：末段 RMS 0.174 而不是 0。
//   真磁带停住时磁头读到的是一段不变的静态磁化，不会"过一会儿又有声音"。
//   所以这里：**目标速率为 0 且带子写满时，把写头也停住**，读头位置就永远不会被覆盖。
//   停写期间丢掉的输入样本没有任何损失 —— 读头停着，输出本来就是一个恒定值。
//   恢复时读头从停住的那一点继续，重放停转前的一小段再追上实时，
//   这也正是真磁带重新启动时的行为。
//
//   由此得到一个真实的表演技巧：**先减速攒带子，再加速**。
//   先拧到 0.5 停两秒（存量变成 1 秒），再拧到 2.0，就能听到 1 秒的升调冲刺。
//   speed>1 时若无存量，读头立刻贴上写头 → 会平滑地停在 1x（听不出变化）。
//   这不是缺陷 —— 实时输入的磁带机本来就没有"未来的带子"可读。
//
// 与 tempo 无关：speed 是自由量，不跟随任何 transport。
#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace trane {

struct TapeParams {
    float speed = 1.0f;    // 0 = 停转，1 = 原速，>1 = 快进（上限 2）
    float wobble = 0.12f;  // wow/flutter 深度
    float mix = 1.0f;
};

class Tape {
public:
    static constexpr double kMaxTapeMs = 8000.0;
    static constexpr double kSmoothMs = 150.0;
    static constexpr double kMixSmoothMs = 15.0;
    // 起始存量：speed=1 时读的就是当前输入，只多出 10.7ms 的"磁头间距"，听不出来。
    static constexpr double kInitialLagMs = 10.7;
    // 抖动位移上限（深度=1 时）。3ms 对应大约 ±60 音分的瞬时音高偏差。
    static constexpr double kMaxWobbleMs = 3.0;
    // 软限位区间：离带子尽头还有这么多时，把速率平滑滑回 1x。
    static constexpr double kSoftZone = 2000.0;
    static constexpr double kMinPosLag = 200.0;  // 匀速位置与写头的最小距离
    // 目标速率低于这个值就算"停转"（0.002x 已经是完全听不出来的速度）
    static constexpr double kStopThreshold = 0.002;

    void prepare(double sampleRate) {
        sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;
        cap_ = static_cast<int>(kMaxTapeMs * 0.001 * sr_) + 8;
        ringL_.assign(static_cast<std::size_t>(cap_), 0.0f);
        ringR_.assign(static_cast<std::size_t>(cap_), 0.0f);
        maxLag_ = static_cast<double>(cap_ - 8);
        initialLag_ = kInitialLagMs * 0.001 * sr_;
        wobDepth_ = kMaxWobbleMs * 0.001 * sr_;
        speedCoef_ = std::exp(-1.0 / (kSmoothMs * 0.001 * sr_));
        mixCoef_ = std::exp(-1.0 / (kMixSmoothMs * 0.001 * sr_));
        lfoInc_[0] = 2.0 * kPi * 0.9 / sr_;   // wow：慢摆
        lfoInc_[1] = 2.0 * kPi * 6.5 / sr_;   // flutter：快抖
        reset();
    }

    void reset() {
        std::fill(ringL_.begin(), ringL_.end(), 0.0f);
        std::fill(ringR_.begin(), ringR_.end(), 0.0f);
        wAbs_ = 0;
        posAbs_ = -initialLag_;
        speedSm_ = 1.0;
        mixSm_ = 0.0;
        rateNow_ = 1.0;
        lfoPhase_[0] = 0.0;
        lfoPhase_[1] = 0.0;
        dcX_[0] = dcX_[1] = 0.0;
        dcY_[0] = dcY_[1] = 0.0;
    }

    void setParams(const TapeParams& p) { params_ = p; }

    void process(float* l, float* r, int numSamples) {
        if (numSamples <= 0 || ringL_.empty()) return;

        const double target = std::min(2.0, std::max(0.0, static_cast<double>(params_.speed)));
        const double mixTarget = std::min(1.0, std::max(0.0, static_cast<double>(params_.mix)));
        const double wobble = std::min(1.0, std::max(0.0, static_cast<double>(params_.wobble)));

        for (int i = 0; i < numSamples; ++i) {
            // "要停转"看的是**目标值**而不是平滑值：平滑要 1 秒多才落到 0 附近，
            // 那段时间里带子可能已经写满，就又回到"停转自己复活"的老路上。
            const bool stopping = target <= kStopThreshold;

            speedSm_ += (target - speedSm_) * (1.0 - speedCoef_);

            const double lagPos = static_cast<double>(wAbs_) - posAbs_;

            // 写头：以实时速率前进（永远 1x，绝不停 —— 停下就等于丢样本、会混叠），
            // 唯一的例外是"停转 + 带子写满"：这时必须停写，否则会覆盖读头位置。
            const bool tapeFull = lagPos >= maxLag_ - 1.0;
            if (!(stopping && tapeFull)) {
                ringL_[static_cast<std::size_t>(wAbs_ % cap_)] = l[i];
                ringR_[static_cast<std::size_t>(wAbs_ % cap_)] = r[i];
                ++wAbs_;
            }

            // 软限位：只在真正会撞上带子尽头的那一侧生效。
            //   减速（eff<1）→ 只可能撞"带子用完"那侧
            //   加速（eff>1）→ 只可能撞"追上写头"那侧
            // 两侧都无脑限位的话，减速会被误判成"快追上了"，速率被拖回 1 —— 等于变速失效。
            // 停转时整段跳过：限位的目的只是"别硬撞边界"，而停转是刻意要停住的。
            double t = 1.0;
            if (!stopping) {
                if (speedSm_ > 1.0) {
                    t = std::min(1.0, (lagPos - kMinPosLag) / kSoftZone);
                } else if (speedSm_ < 1.0) {
                    t = std::min(1.0, (maxLag_ - lagPos) / kSoftZone);
                }
            }
            t = std::max(0.0, t);
            const double rate = 1.0 + (speedSm_ - 1.0) * t;
            rateNow_ = rate;

            posAbs_ += rate;
            const double maxPos = static_cast<double>(wAbs_) - kMinPosLag;
            const double minPos = static_cast<double>(wAbs_) - maxLag_;
            if (posAbs_ > maxPos) posAbs_ = maxPos;
            if (posAbs_ < minPos) posAbs_ = minPos;

            // wow/flutter：有界位移（不积分、不漂移）
            lfoPhase_[0] += lfoInc_[0];
            if (lfoPhase_[0] > 2.0 * kPi) lfoPhase_[0] -= 2.0 * kPi;
            lfoPhase_[1] += lfoInc_[1];
            if (lfoPhase_[1] > 2.0 * kPi) lfoPhase_[1] -= 2.0 * kPi;
            const double wobOffset =
                wobble * wobDepth_ * (0.7 * std::sin(lfoPhase_[0]) + 0.3 * std::sin(lfoPhase_[1]));

            double readPos = posAbs_ - wobOffset;
            const double hardMax = static_cast<double>(wAbs_) - 2.0;
            const double hardMin = static_cast<double>(wAbs_) - maxLag_;
            if (readPos > hardMax) readPos = hardMax;
            if (readPos < hardMin) readPos = hardMin;

            const double base = std::floor(readPos);
            const double frac = readPos - base;
            const int i0 = wrap(static_cast<std::int64_t>(base));
            const int i1 = (i0 + 1 >= cap_) ? 0 : i0 + 1;
            const double slL =
                static_cast<double>(ringL_[static_cast<std::size_t>(i0)]) * (1.0 - frac) +
                static_cast<double>(ringL_[static_cast<std::size_t>(i1)]) * frac;
            const double slR =
                static_cast<double>(ringR_[static_cast<std::size_t>(i0)]) * (1.0 - frac) +
                static_cast<double>(ringR_[static_cast<std::size_t>(i1)]) * frac;

            // 隔直。停转时读指针不再推进，输出的是一个恒定值（直流）。
            // 真磁带停下时磁头读到的也是一段静态磁化，功放的隔直电容会把它滤掉 ——
            // 听到的是一声闷响然后安静，而不是一个永久偏置。
            // 少了这一步，tape stop 会往总线上灌直流，把限制器顶死。
            const double dcL = slL - dcX_[0] + 0.9995 * dcY_[0];
            dcX_[0] = slL;
            dcY_[0] = dcL;
            const double dcR = slR - dcX_[1] + 0.9995 * dcY_[1];
            dcX_[1] = slR;
            dcY_[1] = dcR;

            mixSm_ += (mixTarget - mixSm_) * (1.0 - mixCoef_);

            l[i] = static_cast<float>(static_cast<double>(l[i]) * (1.0 - mixSm_) + dcL * mixSm_);
            r[i] = static_cast<float>(static_cast<double>(r[i]) * (1.0 - mixSm_) + dcR * mixSm_);
        }
    }

    // 供测试与界面观察
    double currentSpeed() const { return speedSm_; }   // 平滑后的设定速率
    double currentRate() const { return rateNow_; }    // 软限位之后的实际推进速率
    double tapeReserveSamples() const { return static_cast<double>(wAbs_) - posAbs_; }

private:
    static constexpr double kPi = 3.14159265358979323846;

    int wrap(std::int64_t i) const {
        i %= cap_;
        if (i < 0) i += cap_;
        return static_cast<int>(i);
    }

    double sr_ = 48000.0;
    TapeParams params_{};
    std::vector<float> ringL_, ringR_;
    int cap_ = 384008;
    std::int64_t wAbs_ = 0;
    double posAbs_ = 0.0;
    double maxLag_ = 384000.0;
    double initialLag_ = 513.6;
    double wobDepth_ = 144.0;
    double speedSm_ = 1.0;
    double mixSm_ = 0.0;
    double rateNow_ = 1.0;
    double speedCoef_ = 0.0;
    double mixCoef_ = 0.0;
    double lfoPhase_[2] = {0.0, 0.0};
    double lfoInc_[2] = {0.0, 0.0};
    double dcX_[2] = {0.0, 0.0};
    double dcY_[2] = {0.0, 0.0};
};

}  // namespace trane
