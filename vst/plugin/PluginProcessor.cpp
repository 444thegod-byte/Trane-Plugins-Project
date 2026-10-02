#include "PluginProcessor.h"
#include "PluginEditor.h"

#include <array>
#include <cmath>

namespace trane {

namespace {
// 参数 ID —— 界面上用 ParamIDs::xxx 取，避免字符串散落
struct ParamIDs {
    static constexpr const char* freeze = "freeze";
    static constexpr const char* loopMs = "loop_ms";
    static constexpr const char* seamMs = "seam_ms";

    static constexpr const char* grainOn = "grain_on";
    static constexpr const char* grainSize = "grain_size";
    static constexpr const char* grainDensity = "grain_density";
    static constexpr const char* grainPosition = "grain_position";
    static constexpr const char* grainSpray = "grain_spray";
    static constexpr const char* grainRate = "grain_rate";
    static constexpr const char* grainSpread = "grain_spread";
    static constexpr const char* grainReverse = "grain_reverse";
    static constexpr const char* grainMix = "grain_mix";

    static constexpr const char* ruinMode = "ruin_mode";
    static constexpr const char* ruinDrive = "ruin_drive";
    static constexpr const char* ruinFold = "ruin_fold";
    static constexpr const char* ruinCrush = "ruin_crush";
    static constexpr const char* ruinRing = "ruin_ring";

    static constexpr const char* stutterOn = "stutter_on";
    static constexpr const char* stutterSize = "stutter_size";
    static constexpr const char* stutterRate = "stutter_rate";
    static constexpr const char* stutterJump = "stutter_jump";
    static constexpr const char* stutterMix = "stutter_mix";

    static constexpr const char* combOn = "comb_on";
    static constexpr const char* combTune = "comb_tune";
    static constexpr const char* combFeedback = "comb_feedback";
    static constexpr const char* combMix = "comb_mix";

    static constexpr const char* tapeOn = "tape_on";
    static constexpr const char* tapeSpeed = "tape_speed";
    static constexpr const char* tapeWobble = "tape_wobble";
    static constexpr const char* tapeMix = "tape_mix";

    static constexpr const char* sweepOn = "sweep_on";
    static constexpr const char* sweepRate = "sweep_rate";
    static constexpr const char* sweepDepth = "sweep_depth";
    static constexpr const char* sweepCenter = "sweep_center";
    static constexpr const char* sweepReso = "sweep_reso";
    static constexpr const char* sweepMode = "sweep_mode";

    static constexpr const char* delayOn = "delay_on";
    static constexpr const char* delayTime = "delay_time";
    static constexpr const char* delayFeedback = "delay_feedback";
    static constexpr const char* delayDamp = "delay_damp";
    static constexpr const char* delayPingPong = "delay_pingpong";
    static constexpr const char* delayMix = "delay_mix";

    static constexpr const char* spaceMix = "space_mix";
    static constexpr const char* spaceSize = "space_size";
    static constexpr const char* spaceTail = "space_tail";
    static constexpr const char* spaceDamp = "space_damp";
    static constexpr const char* spaceDiffuse = "space_diffuse";

    static constexpr const char* output = "output";
};

float getFloat(const juce::AudioProcessorValueTreeState& s, const char* id) {
    if (auto* p = s.getRawParameterValue(id)) return p->load();
    return 0.0f;
}

bool getBool(const juce::AudioProcessorValueTreeState& s, const char* id) {
    if (auto* p = s.getRawParameterValue(id)) return p->load() > 0.5f;
    return false;
}
}  // namespace

juce::AudioProcessorValueTreeState::ParameterLayout TraneAudioProcessor::createLayout() {
    using FloatParam = juce::AudioParameterFloat;
    using BoolParam = juce::AudioParameterBool;
    using NR = juce::NormalisableRange<float>;

    juce::AudioProcessorValueTreeState::ParameterLayout layout;

    const auto pid = [](const char* id) { return juce::ParameterID{id, 1}; };

    // ---- CAPTURE ----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::freeze), "Freeze", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::loopMs), "Loop",
                                            NR(20.0f, 2000.0f, 0.0f, 0.3f), 250.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("ms")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::seamMs), "Seam",
                                            NR(0.0f, 40.0f, 0.1f), 10.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("ms")));

    // ---- GRAIN ----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::grainOn), "Grain", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainSize), "Grain Size",
                                            NR(5.0f, 500.0f, 0.0f, 0.4f), 120.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("ms")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainDensity), "Grain Density",
                                            NR(0.5f, 100.0f, 0.0f, 0.4f), 12.0f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainPosition), "Grain Position",
                                            NR(0.0f, 1.0f, 0.001f), 0.5f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainSpray), "Grain Spray",
                                            NR(0.0f, 1.0f, 0.001f), 0.15f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainRate), "Grain Rate",
                                            NR(0.25f, 4.0f, 0.0f, 0.4f), 1.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("x")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainSpread), "Grain Spread",
                                            NR(0.0f, 1.0f, 0.001f), 0.6f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainReverse), "Grain Reverse",
                                            NR(0.0f, 1.0f, 0.001f), 0.25f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::grainMix), "Grain Mix",
                                            NR(0.0f, 1.0f, 0.001f), 1.0f));

    // ---- RUIN ----
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::ruinMode), "Ruin Mode",
                                            NR(0.0f, 1.0f, 0.001f), 0.0f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::ruinDrive), "Ruin Drive",
                                            NR(0.0f, 1.0f, 0.001f), 0.35f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::ruinFold), "Ruin Fold",
                                            NR(0.0f, 1.0f, 0.001f), 0.0f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::ruinCrush), "Ruin Crush",
                                            NR(0.0f, 1.0f, 0.001f), 0.0f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::ruinRing), "Ruin Ring",
                                            NR(0.0f, 1.0f, 0.001f), 0.0f));

    // ---- STUTTER（切片重触发）----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::stutterOn), "Stutter", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::stutterSize), "Stutter Size",
                                            NR(5.0f, 500.0f, 0.0f, 0.4f), 90.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("ms")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::stutterRate), "Stutter Rate",
                                            NR(0.25f, 30.0f, 0.0f, 0.4f), 4.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("Hz")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::stutterJump), "Stutter Jump",
                                            NR(0.0f, 1.0f, 0.001f), 0.35f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::stutterMix), "Stutter Mix",
                                            NR(0.0f, 1.0f, 0.001f), 1.0f));

    // ---- COMB（谐振梳状）----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::combOn), "Comb", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::combTune), "Comb Tune",
                                            NR(20.0f, 4000.0f, 0.0f, 0.35f), 220.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("Hz")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::combFeedback), "Comb Feedback",
                                            NR(0.0f, 0.95f, 0.001f), 0.6f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::combMix), "Comb Mix",
                                            NR(0.0f, 1.0f, 0.001f), 0.5f));

    // ---- TAPE（变速 / 停转）----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::tapeOn), "Tape", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::tapeSpeed), "Tape Speed",
                                            NR(0.0f, 2.0f, 0.001f), 1.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("x")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::tapeWobble), "Tape Wobble",
                                            NR(0.0f, 1.0f, 0.001f), 0.12f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::tapeMix), "Tape Mix",
                                            NR(0.0f, 1.0f, 0.001f), 1.0f));

    // ---- SWEEP（随机扫频）----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::sweepOn), "Sweep", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::sweepRate), "Sweep Rate",
                                            NR(0.01f, 20.0f, 0.0f, 0.35f), 0.8f,
                                            juce::AudioParameterFloatAttributes().withLabel("Hz")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::sweepDepth), "Sweep Depth",
                                            NR(0.0f, 1.0f, 0.001f), 0.4f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::sweepCenter), "Sweep Center",
                                            NR(60.0f, 12000.0f, 0.0f, 0.4f), 1200.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("Hz")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::sweepReso), "Sweep Reso",
                                            NR(0.0f, 1.0f, 0.001f), 0.3f));
    layout.add(std::make_unique<juce::AudioParameterChoice>(
        pid(ParamIDs::sweepMode), "Sweep Mode", juce::StringArray{"LP", "BP", "HP"}, 0));

    // ---- DELAY ----
    layout.add(std::make_unique<BoolParam>(pid(ParamIDs::delayOn), "Delay", false));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::delayTime), "Delay Time",
                                            NR(20.0f, 2000.0f, 0.0f, 0.4f), 375.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("ms")));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::delayFeedback), "Delay Feedback",
                                            NR(0.0f, 0.92f, 0.001f), 0.45f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::delayDamp), "Delay Damp",
                                            NR(0.0f, 1.0f, 0.001f), 0.35f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::delayPingPong), "Delay PingPong",
                                            NR(0.0f, 1.0f, 0.001f), 0.0f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::delayMix), "Delay Mix",
                                            NR(0.0f, 1.0f, 0.001f), 0.35f));

    // ---- HUGE SPACE ----
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::spaceMix), "Space Mix",
                                            NR(0.0f, 1.0f, 0.001f), 0.55f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::spaceSize), "Space Size",
                                            NR(0.0f, 1.0f, 0.001f), 0.7f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::spaceTail), "Space Tail",
                                            NR(0.0f, 1.0f, 0.001f), 0.8f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::spaceDamp), "Space Damp",
                                            NR(0.0f, 1.0f, 0.001f), 0.4f));
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::spaceDiffuse), "Space Diffuse",
                                            NR(0.0f, 1.0f, 0.001f), 0.7f));

    // ---- OUT ----
    layout.add(std::make_unique<FloatParam>(pid(ParamIDs::output), "Output",
                                            NR(-24.0f, 12.0f, 0.1f), 0.0f,
                                            juce::AudioParameterFloatAttributes().withLabel("dB")));

    return layout;
}

TraneAudioProcessor::TraneAudioProcessor()
    : juce::AudioProcessor(BusesProperties()
                               .withInput("Input", juce::AudioChannelSet::stereo(), true)
                               .withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      apvts(*this, nullptr, "PARAMETERS", createLayout()) {}

void TraneAudioProcessor::prepareToPlay(double sampleRate, int samplesPerBlock) {
    engine_.prepare(sampleRate, samplesPerBlock);
    // 前瞻限制器会引入固定延迟，必须上报，否则干声比别的轨道晚 2ms
    setLatencySamples(engine_.latencySamples());
}

void TraneAudioProcessor::releaseResources() {}

bool TraneAudioProcessor::isBusesLayoutSupported(const BusesLayout& layouts) const {
    return layouts.getMainInputChannelSet() == juce::AudioChannelSet::stereo()
        && layouts.getMainOutputChannelSet() == juce::AudioChannelSet::stereo();
}

void TraneAudioProcessor::processBlock(juce::AudioBuffer<float>& buffer,
                                       juce::MidiBuffer& /*midi*/) {
    juce::ScopedNoDenormals noDenormals;

    const int n = buffer.getNumSamples();
    const int nch = buffer.getNumChannels();
    if (n <= 0) return;
    if (nch != 2) {
        buffer.clear();
        return;
    }

    TraneParams p;
    p.freeze = getBool(apvts, ParamIDs::freeze);
    p.loopMs = getFloat(apvts, ParamIDs::loopMs);
    p.seamMs = getFloat(apvts, ParamIDs::seamMs);

    p.grainOn = getBool(apvts, ParamIDs::grainOn);
    p.grain.sizeMs = getFloat(apvts, ParamIDs::grainSize);
    p.grain.density = getFloat(apvts, ParamIDs::grainDensity);
    p.grain.position = getFloat(apvts, ParamIDs::grainPosition);
    p.grain.spray = getFloat(apvts, ParamIDs::grainSpray);
    p.grain.rate = getFloat(apvts, ParamIDs::grainRate);
    p.grain.panSpread = getFloat(apvts, ParamIDs::grainSpread);
    p.grain.reverseProb = getFloat(apvts, ParamIDs::grainReverse);
    p.grain.mix = getFloat(apvts, ParamIDs::grainMix);
    p.grain.rateSpread = 0.15f;
    p.grain.level = 1.0f;

    p.ruin.mode = getFloat(apvts, ParamIDs::ruinMode);
    p.ruin.drive = getFloat(apvts, ParamIDs::ruinDrive);
    p.ruin.fold = getFloat(apvts, ParamIDs::ruinFold);
    p.ruin.crush = getFloat(apvts, ParamIDs::ruinCrush);
    p.ruin.ring = getFloat(apvts, ParamIDs::ruinRing);

    p.stutterOn = getBool(apvts, ParamIDs::stutterOn);
    p.stutter.sizeMs = getFloat(apvts, ParamIDs::stutterSize);
    p.stutter.rateHz = getFloat(apvts, ParamIDs::stutterRate);
    p.stutter.jump = getFloat(apvts, ParamIDs::stutterJump);
    p.stutter.mix = getFloat(apvts, ParamIDs::stutterMix);

    p.combOn = getBool(apvts, ParamIDs::combOn);
    p.comb.tuneHz = getFloat(apvts, ParamIDs::combTune);
    p.comb.feedback = getFloat(apvts, ParamIDs::combFeedback);
    p.comb.mix = getFloat(apvts, ParamIDs::combMix);

    p.tapeOn = getBool(apvts, ParamIDs::tapeOn);
    p.tape.speed = getFloat(apvts, ParamIDs::tapeSpeed);
    p.tape.wobble = getFloat(apvts, ParamIDs::tapeWobble);
    p.tape.mix = getFloat(apvts, ParamIDs::tapeMix);

    p.sweep.on = getBool(apvts, ParamIDs::sweepOn);
    p.sweep.rateHz = getFloat(apvts, ParamIDs::sweepRate);
    p.sweep.depth = getFloat(apvts, ParamIDs::sweepDepth);
    p.sweep.centerHz = getFloat(apvts, ParamIDs::sweepCenter);
    p.sweep.resonance = getFloat(apvts, ParamIDs::sweepReso);
    // AudioParameterChoice 的原始值就是序号 0/1/2 → 映射成 LP/BP/HP 的连续过渡位置
    p.sweep.mode = getFloat(apvts, ParamIDs::sweepMode) * 0.5f;

    p.delay.on = getBool(apvts, ParamIDs::delayOn);
    p.delay.timeMs = getFloat(apvts, ParamIDs::delayTime);
    p.delay.feedback = getFloat(apvts, ParamIDs::delayFeedback);
    p.delay.damp = getFloat(apvts, ParamIDs::delayDamp);
    p.delay.pingPong = getFloat(apvts, ParamIDs::delayPingPong);
    p.delay.mix = getFloat(apvts, ParamIDs::delayMix);

    p.space.mix = getFloat(apvts, ParamIDs::spaceMix);
    p.space.size = getFloat(apvts, ParamIDs::spaceSize);
    p.space.tail = getFloat(apvts, ParamIDs::spaceTail);
    p.space.damp = getFloat(apvts, ParamIDs::spaceDamp);
    p.space.diffuse = getFloat(apvts, ParamIDs::spaceDiffuse);

    p.outputGain = juce::Decibels::decibelsToGain(getFloat(apvts, ParamIDs::output));
    p.limiterOn = true;

    engine_.setParams(p);

    float* ch[2] = {buffer.getWritePointer(0), buffer.getWritePointer(1)};
    const float* cin[2] = {ch[0], ch[1]};
    engine_.process(cin, ch, n);

    // 界面观察量
    uiFreezeActive.store(engine_.freezeActive() ? 1.0f : 0.0f);
    if (engine_.freezeLoopLength() > 1.0) {
        uiFreezePhase.store(
            static_cast<float>(engine_.freezeLoopStart() / static_cast<double>(engine_.captureCapacity())));
    }
    uiGrainVoices.store(static_cast<float>(engine_.grainVoices()));
    uiGainReduction.store(engine_.lastGainReduction());
    uiTapeSpeed.store(static_cast<float>(engine_.tapeSpeed()));
}

void TraneAudioProcessor::processBlockBypassed(juce::AudioBuffer<float>& buffer,
                                              juce::MidiBuffer& /*midi*/) {
    juce::ScopedNoDenormals noDenormals;

    const int n = buffer.getNumSamples();
    const int nch = buffer.getNumChannels();
    if (n <= 0) return;
    if (nch != 2) {
        buffer.clear();
        return;
    }

    float* ch[2] = {buffer.getWritePointer(0), buffer.getWritePointer(1)};
    const float* cin[2] = {ch[0], ch[1]};
    engine_.processBypassed(cin, ch, n);
}

juce::AudioProcessorEditor* TraneAudioProcessor::createEditor() {
    return new TraneAudioProcessorEditor(*this);
}

// ---------------------------------------------------------------------------
// 背景图的持久化 —— 存在 apvts.state 的根属性上
// ---------------------------------------------------------------------------
// 为什么是根属性而不是另开一棵子树：`copyState()` / `replaceState()` 本来就会
// 带上根节点的全部属性，于是保存与恢复都是白送的，不用再写一遍序列化，
// 也不会出现"参数存了、背景没存"这种半拉子状态。
TraneAudioProcessor::BackdropState TraneAudioProcessor::getBackdropState() const {
    BackdropState b;
    b.path = apvts.state.getProperty("backdropPath", juce::String{});
    b.where = static_cast<int>(apvts.state.getProperty("backdropWhere", 0));
    b.brightness = static_cast<float>(apvts.state.getProperty("backdropBright", 1.0f));
    return b;
}

void TraneAudioProcessor::setBackdropState(const BackdropState& b) {
    apvts.state.setProperty("backdropPath", b.path, nullptr);
    apvts.state.setProperty("backdropWhere", b.where, nullptr);
    apvts.state.setProperty("backdropBright", b.brightness, nullptr);
}

void TraneAudioProcessor::getStateInformation(juce::MemoryBlock& destData) {
    if (auto xml = apvts.copyState().createXml()) {
        copyXmlToBinary(*xml, destData);
    }
}

void TraneAudioProcessor::setStateInformation(const void* data, int sizeInBytes) {
    if (auto xml = getXmlFromBinary(data, sizeInBytes)) {
        if (xml->hasTagName(apvts.state.getType())) {
            apvts.replaceState(juce::ValueTree::fromXml(*xml));
        }
    }
}

}  // namespace trane

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter() {
    return new trane::TraneAudioProcessor();
}
