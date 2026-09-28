// PluginProcessor.h — VST3 / AU 外壳
//
// 这一层刻意做得很薄：所有 DSP 都在 core/ 里，不依赖 JUCE，因此可以脱离宿主
// 离线编译、离线渲染、离线测试。外壳只负责参数管理与缓冲区转换。
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "../core/TraneEngine.h"

#include <atomic>

namespace trane {

class TraneAudioProcessor : public juce::AudioProcessor {
public:
    TraneAudioProcessor();
    ~TraneAudioProcessor() override = default;

    void prepareToPlay(double sampleRate, int samplesPerBlock) override;
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
