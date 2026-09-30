// PluginProcessor.h — VST3 / AU 外壳
//
// 这一层刻意做得很薄：所有 DSP 都在 core/ 里，不依赖 JUCE，因此可以脱离宿主
// 离线编译、离线渲染、离线测试。外壳只负责参数管理与缓冲区转换。
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "../core/TraneEngine.h"

#include <atomic>
#include <cmath>

namespace trane {

class TraneAudioProcessor : public juce::AudioProcessor {
public:
    TraneAudioProcessor();
    ~TraneAudioProcessor() override = default;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
    bool isBusesLayoutSupported(const BusesLayout& layouts) const override;
    void releaseResources() override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    // 必须自己实现：基类版本假定延迟为 0（还会断言 getLatencySamples()==0），
    // 而本设备因为前瞻限制器报了 2ms —— 用基类版本旁通会把干声往前推 2ms。
    void processBlockBypassed(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return "Träne"; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 40.0; }

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}

    void getStateInformation(juce::MemoryBlock& destData) override;
    void setStateInformation(const void* data, int sizeInBytes) override;

    // ------------------------------------------------------------------------
    // 背景图的持久化
    // ------------------------------------------------------------------------
    //
    // **只存路径，不存图。** 把几 MB 的图片塞进宿主工程文件会让每个实例都
    // 膨胀几 MB，而且宿主每次保存 / 加载都要 base64 编解码一遍 —— 为了一个
    // 装饰性的背景，代价太大。存路径的代价是"文件被移走 / 删掉就没了"，
    // 这比塞图片诚实得多，也不会让用户在别处看到一个莫名其妙的巨大工程文件。
    //
    // 三个值存在 `apvts.state` 的**根属性**上 —— 于是 `copyState()` 自动带上它们，
    // `replaceState()` 自动恢复它们，不用另开一套序列化。
    struct BackdropState {
        juce::String path;
        int   where = 0;              // panel::BgWhere 的原始值
        float brightness = 1.0f;
        bool operator==(const BackdropState& o) const {
            return path == o.path && where == o.where
                && std::abs(brightness - o.brightness) < 1.0e-4f;
        }
    };
    BackdropState getBackdropState() const;
    void setBackdropState(const BackdropState&);

    juce::AudioProcessorValueTreeState apvts;

    // 供界面观察
    std::atomic<float> uiFreezePhase{0.0f};
    std::atomic<float> uiFreezeActive{0.0f};
    std::atomic<float> uiGrainVoices{0.0f};
    std::atomic<float> uiGainReduction{1.0f};
    std::atomic<float> uiTapeSpeed{1.0f};

    static juce::AudioProcessorValueTreeState::ParameterLayout createLayout();

private:
    TraneEngine engine_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(TraneAudioProcessor)
};

}  // namespace trane
