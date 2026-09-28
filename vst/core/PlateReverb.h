// PlateReverb.h — 巨大板式混响
//
// 拓扑是经典的 Schroeder/Freeverb 结构（8 个并联梳状滤波器 + 4 级串联全通），
// 但做了两处针对"非常大"的改动：
//   1. 梳状延迟线可放大到 2.5 倍（最长约 92ms），配合高反馈得到十几秒的尾音
//   2. 每条梳状延迟加低频调制 —— 不加的话长尾会变成明显的金属鸣响
//
// 单声道进、立体声出（左右用不同的延迟长度做去相关）。
#pragma once

#include <vector>

namespace trane {

struct ReverbParams {
    float size = 0.7f;       // 0..1 空间尺寸（放大延迟线）
    float tail = 0.8f;       // 0..1 尾音长度（梳状反馈）
    float damp = 0.4f;       // 0..1 高频衰减
    float diffuse = 0.7f;    // 0..1 扩散（全通反馈）
    float modDepth = 0.3f;   // 0..1 调制深度
    float mix = 0.55f;       // 0..1 干湿
};

class PlateReverb {
public:
    static constexpr int kCombs = 8;
    static constexpr int kAllpasses = 4;
    static constexpr double kMaxSizeScale = 2.5;

    void prepare(double sampleRate);
    void reset();
    // 注意：必须在这里重算系数。曾经漏掉这一步，导致 tail/size/damp 全部不生效，
    // 而离线探针一眼就抓到了（四个 tail 值给出完全相同的 RT60）。
    void setParams(const ReverbParams& p) {
        params_ = p;
        updateCoefficients();
    }

    // 输入会被折叠成单声道送进网络，输出是立体声
    void process(const float* const* in, float* const* out, int numSamples);

    // 供测试观察：当前反馈系数
    float combFeedback() const;

private:
    struct Comb {
        std::vector<float> buf;
        int size = 0;
        int writeIdx = 0;
        double delay = 0.0;
        double modPhase = 0.0;
        double modInc = 0.0;
        float filterStore = 0.0f;
        float feedback = 0.0f;
        float damp1 = 0.0f;
        float damp2 = 1.0f;
    };

    struct Allpass {
        std::vector<float> buf;
        int size = 0;
        int writeIdx = 0;
        float feedback = 0.5f;
    };

    void updateCoefficients();

    double sr_ = 48000.0;
    ReverbParams params_{};
    Comb combs_[2][kCombs];
    Allpass allpasses_[2][kAllpasses];
    double baseComb_[2][kCombs]{};
    double baseAllpass_[2][kAllpasses]{};
    double modDepthSamples_ = 0.0;
};

}  // namespace trane
