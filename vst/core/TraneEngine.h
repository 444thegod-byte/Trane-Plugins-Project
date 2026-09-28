// TraneEngine.h — Träne 的顶层信号链
//
//   input ──┬─→ CaptureBuffer（8 秒环形，一直写）
//           │        ├─→ FreezeLoop   冻结 = 把最近 LOOP ms 钉成无限无缝循环
//           │        └─→ GrainCloud   粒子云从同一块缓冲区取素材
//           │
//           └─→ Ruin（Clear / Ruin 人格）
//                     └─→ RandomSweep（随机扫频谐振滤波器）
//                               └─→ SpaceDelay（阻尼延迟 / ping-pong）
//                                         └─→ PlateReverb（HUGE SPACE，最长 37 秒尾音）
//                                                   └─→ LookaheadLimiter ─→ output
//
// 解构链（v0.9.0 新增，接在粒子之后、Ruin 之前）：
//
//   freeze → grain → STUTTER → COMB → TAPE → ruin → sweep → delay → space → limiter
//
//   顺序是刻意的，不是随便排的：
//     STUTTER 最先 —— 它切的是"源"，把素材打成硬边切片；
//     COMB 在切片之后 —— 让那些切片获得一个音高网格（噪声被听成音高）；
//     TAPE 在 COMB 之后 —— 于是 tape stop 会把整条谐振一起往下拽，
//       音高一路掉下去。这是三步里最戏剧化的一步，所以放最后。
//   三者都自带环形缓冲、都读"过去"，不向宿主引入额外延迟，
//   所以 latencySamples() 不变（仍然只有前瞻限制器的 2ms）。
//
// 全程不涉及任何 tempo / transport 概念。
#pragma once

#include "CaptureBuffer.h"
#include "Comb.h"
#include "FreezeLoop.h"
#include "GrainCloud.h"
#include "LookaheadLimiter.h"
#include "PlateReverb.h"
#include "RandomSweep.h"
#include "Ruin.h"
#include "SpaceDelay.h"
#include "Stutter.h"
#include "Tape.h"

#include <vector>

namespace trane {

struct TraneParams {
    // CAPTURE
    bool freeze = false;
    float loopMs = 250.0f;
    float seamMs = 10.0f;

    // GRAIN
    bool grainOn = false;
    GrainParams grain{};

    // STUTTER（切片重触发）
    bool stutterOn = false;
    StutterParams stutter{};

    // COMB（谐振梳状）
    bool combOn = false;
    CombParams comb{};

    // TAPE（变速 / 停转）
    bool tapeOn = false;
    TapeParams tape{};

    // RUIN
    RuinParams ruin{};

    // SWEEP
    SweepParams sweep{};

    // DELAY
    DelayParams delay{};

    // HUGE SPACE
    ReverbParams space{};

    // OUT
    float outputGain = 1.0f;
    bool limiterOn = true;
};

class TraneEngine {
public:
    void prepare(double sampleRate, int maxBlockSize);
    void reset();
    void setParams(const TraneParams& p);

    void process(const float* const* in, float* const* out, int numSamples);

    // 旁通：仍然走一遍前瞻限制器的延迟线，保证延迟和正常处理时完全一致。
    // 不能直接用"输入拷到输出" —— 本设备有 2ms 延迟，宿主会按这个值做补偿，
    // 旁通时若不给同样的延迟，干声会被往前推 2ms。
    void processBypassed(const float* const* in, float* const* out, int numSamples);

    // 供界面观察
    bool freezeActive() const { return freeze_.isFrozen(); }
    double freezeLoopStart() const { return static_cast<double>(freeze_.loopStartIndex()); }
    double freezeLoopLength() const { return static_cast<double>(freeze_.loopLengthSamples()); }
    std::int64_t captureWriteHead() const { return capture_.writeHead(); }
    std::int64_t captureCapacity() const { return capture_.capacity(); }
    int grainVoices() const { return grain_.activeVoices(); }
    float lastGainReduction() const { return limiter_.lastGainReduction(); }
    double tapeSpeed() const { return tape_.currentSpeed(); }

    // 前瞻限制器引入的延迟，宿主必须据此做补偿
    int latencySamples() const { return limiter_.latencySamples(); }

    static constexpr double kCaptureSeconds = 8.0;
    static constexpr double kLiveGrainWindowSeconds = 4.0;

private:
    CaptureBuffer capture_;
    FreezeLoop freeze_;
    GrainCloud grain_;
    Stutter stutter_;
    Comb comb_;
    Tape tape_;
    Ruin ruin_;
    RandomSweep sweep_;
    SpaceDelay delay_;
    PlateReverb space_;
    LookaheadLimiter limiter_;

    double sr_ = 48000.0;
    TraneParams params_{};

    // 临时缓冲（prepare 时分配，音频线程不分配）
    std::vector<float> scratchL_;
    std::vector<float> scratchR_;
};

}  // namespace trane
