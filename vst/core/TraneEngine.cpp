#include "TraneEngine.h"

#include <algorithm>
#include <cmath>

namespace trane {

void TraneEngine::prepare(double sampleRate, int maxBlockSize) {
    sr_ = sampleRate > 0.0 ? sampleRate : 48000.0;

    capture_.prepare(2, sr_, kCaptureSeconds);
    freeze_.prepare(&capture_, sr_);
    grain_.prepare(&capture_, sr_);
    stutter_.prepare(sr_);
    comb_.prepare(sr_);
    tape_.prepare(sr_);
    ruin_.prepare(sr_);
    sweep_.prepare(sr_);
    delay_.prepare(sr_);
    space_.prepare(sr_);

    const int cap = maxBlockSize > 0 ? maxBlockSize : 512;
    scratchL_.assign(static_cast<std::size_t>(cap), 0.0f);
    scratchR_.assign(static_cast<std::size_t>(cap), 0.0f);

    limiter_.prepare(sr_, cap);

    reset();
}

void TraneEngine::reset() {
    capture_.reset();
    freeze_.reset();
    grain_.reset();
    stutter_.reset();
    comb_.reset();
    tape_.reset();
    ruin_.reset();
    sweep_.reset();
    delay_.reset();
    space_.reset();
    limiter_.reset();
}

void TraneEngine::setParams(const TraneParams& p) {
    params_ = p;

    // 顺序有意：先设长度再设冻结状态，这样冻结瞬间取到的是新的 LOOP 长度
    freeze_.setLoopMs(static_cast<double>(p.loopMs));
    freeze_.setSeamMs(static_cast<double>(p.seamMs));
    freeze_.setFrozen(p.freeze);

    ruin_.setParams(p.ruin);
    space_.setParams(p.space);

    GrainParams g = p.grain;
    if (!p.grainOn) g.mix = 0.0f;
    grain_.setParams(g);

    // 三个解构模块同样按 mix 门控：关掉时 mix 归零，
    // 但内部环形缓冲照常写 —— 所以重新打开时立刻就有素材，不会先出一段静音。
    // 模块内部对 mix 做了 15ms 平滑，开关不会爆音。
    StutterParams s = p.stutter;
    if (!p.stutterOn) s.mix = 0.0f;
    stutter_.setParams(s);

    CombParams c = p.comb;
    if (!p.combOn) c.mix = 0.0f;
    comb_.setParams(c);

    TapeParams t = p.tape;
    if (!p.tapeOn) t.mix = 0.0f;
    tape_.setParams(t);
}

void TraneEngine::processBypassed(const float* const* in, float* const* out, int numSamples) {
    if (numSamples <= 0) return;
    for (int i = 0; i < numSamples; ++i) {
        out[0][i] = in[0][i];
        out[1][i] = in[1][i];
    }
    // enabled=false：只延迟、不压缩。延迟量与正常处理时一致，宿主补偿才对得上。
    limiter_.process(out[0], out[1], numSamples, false);
}

void TraneEngine::process(const float* const* in, float* const* out, int numSamples) {
    if (numSamples <= 0) return;

    float* srcL = scratchL_.data();
    float* srcR = scratchR_.data();
    float* src[2] = {srcL, srcR};

    // 1) 冻结：输出干声，或输出被钉住的无限循环
    freeze_.process(in, src, numSamples);

    // 2) 粒子云的取材区间：冻结时限定在冻结窗口内，否则取最近的若干秒
    if (freeze_.isFrozen() && freeze_.loopLengthSamples() > 1) {
        grain_.setReadRange(freeze_.loopStartIndex(), freeze_.loopLengthSamples());
    } else {
        std::int64_t window = static_cast<std::int64_t>(kLiveGrainWindowSeconds * sr_);
        if (window > capture_.capacity()) window = capture_.capacity();
        grain_.setReadRange(capture_.writeHead() - window, window);
    }

    // 3) 粒子（就地处理，干声部分就是冻结的输出）
    grain_.process(src, src, numSamples);

    // 4) 解构链：切片重触发 → 谐振梳状 → 磁带变速/停转
    //    顺序理由见 TraneEngine.h 的注释（TAPE 放最后，让停转把整条谐振一起拽下去）
    stutter_.process(srcL, srcR, numSamples);
    comb_.process(srcL, srcR, numSamples);
    tape_.process(srcL, srcR, numSamples);

    // 5) Clear / Ruin 人格
    ruin_.process(src, src, numSamples);

    // 6) 随机扫频
    sweep_.process(srcL, srcR, numSamples);

    // 7) 延迟
    delay_.process(srcL, srcR, numSamples);

    // 8) HUGE SPACE
    space_.process(src, out, numSamples);

    // 9) 输出增益 + 前瞻限制器
    //
    // 曾经这里是一个"先量峰值再降增益"的反馈式限制器：起控 1ms，
    // 峰值到达那一刻包络才刚开始爬，增益还是 1.0 → 必然过冲。
    // 实测在 +4.8dB 输出增益下峰值冲到 1.0062，端到端验收判失败。
    // 现在换成带 2ms 前瞻的版本，数学上不可能过冲（见 LookaheadLimiter.h）。
    const double outGain = static_cast<double>(params_.outputGain);
    if (outGain != 1.0) {
        for (int ch = 0; ch < 2; ++ch) {
            for (int i = 0; i < numSamples; ++i) {
                out[ch][i] = static_cast<float>(static_cast<double>(out[ch][i]) * outGain);
            }
        }
    }
    limiter_.process(out[0], out[1], numSamples, params_.limiterOn);
}

}  // namespace trane
