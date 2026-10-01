// GrainCloud.h — 从采集缓冲区里撒粒子的粒子云
//
// 参数集借鉴了 Lux Cache 的 petri / concatenative：
//   "shape the grains: grain length, spread, density and how long each one stays,
//    with a dry/wet so the source can sit under its own answer"
//   "per-hit dice: pan, velocity, start, pitch, filter and reverse each take an amount,
//    so no two hits land the same"
//
// 于是每个维度都有独立的随机量：位置、音高、声场、方向。
//
// 关键设计：随机数用固定种子的 xorshift，保证渲染可复现 —— 否则测试无法断言。
#pragma once

#include "CaptureBuffer.h"

#include <cstdint>

namespace trane {

struct GrainParams {
    float sizeMs = 100.0f;        // 粒子长度
    float density = 8.0f;         // 每秒粒子数
    float position = 0.0f;        // Reference-range position 0..1; the end is not necessarily the newest sample.
    float spray = 0.1f;           // 位置随机量 0..1
    float rate = 1.0f;            // Source read rate/pitch; output lifetime remains sizeMs.
    float rateSpread = 0.0f;      // 每个粒子的音高随机量 0..1
    float panSpread = 0.0f;       // 每个粒子的声场随机量 0..1
    float reverseProb = 0.0f;     // 反向播放概率 0..1
    float level = 1.0f;           // 粒子云总电平
    float mix = 1.0f;             // 0 = 全干，1 = 全粒子
};

class GrainCloud {
public:
    static constexpr int kMaxVoices = 64;
    static constexpr int kWindowSize = 2048;

    void prepare(CaptureBuffer* buffer, double sampleRate);
    void reset();

    void setParams(const GrainParams& p) { params_ = p; }

    // 粒子从缓冲区哪个区间里取素材。区间由引擎根据"冻结中/实时"决定。
    void setReadRange(std::int64_t startIndex, std::int64_t length);

    // 返回本块实际触发的粒子数（供测试与 UI 观察）
    int process(const float* const* in, float* const* out, int numSamples);

    int activeVoices() const;
    std::uint32_t spawnCount() const { return spawned_; }

private:
    struct Voice {
        bool active = false;
        double pos = 0.0;
        double inc = 1.0;
        double windowPos = 0.0;   // 窗函数查表位置（累加，避免每样本做除法）
        double windowInc = 1.0;
        std::int64_t age = 0;
        std::int64_t length = 1;
        float gain = 1.0f;
        float panL = 0.70710678f;
        float panR = 0.70710678f;
    };

    void buildWindow();
    void spawn();
    float nextRandom();  // 0..1，确定性

    CaptureBuffer* buf_ = nullptr;
    double sr_ = 48000.0;

    GrainParams params_{};
    Voice voices_[kMaxVoices];
    float window_[kWindowSize];

    double spawnPhase_ = 0.0;
    std::int64_t rangeStart_ = 0;
    std::int64_t rangeLength_ = 0;
    std::uint32_t rngState_ = 0x9E3779B9u;
    std::uint32_t spawned_ = 0;
};

}  // namespace trane
