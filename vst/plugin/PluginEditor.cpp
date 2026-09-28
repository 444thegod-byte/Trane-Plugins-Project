#include "PluginEditor.h"
#include "PluginProcessor.h"

#include <cmath>
#include <initializer_list>

namespace trane {

namespace {

// ---- 版面常量 --------------------------------------------------------------
// v0.10：Ableton 原生设备式平面面板。没有顶栏，首行直接从可操作参数开始。
constexpr int kPanelW = 860;
constexpr int kPanelH = 438;
constexpr int kCellW = 64;
constexpr int kMarginX = 22;
constexpr int kKnob = 50;
constexpr int kKnobBox = 18;
constexpr int kLabelH = 14;
constexpr int kToggleH = 26;

constexpr int kRowY[4] = {32, 136, 240, 344};
constexpr int kLabelY[4] = {14, 118, 222, 326};

constexpr int cell(int n) { return kMarginX + kCellW * n; }

// ---- 颜色：纯黑 + 高亮白 --------------------------------------------------
const juce::Colour kBg{0xff000000};
juce::Colour ink(float alpha) { return juce::Colour(0xffffffff).withAlpha(alpha); }

constexpr float kInkFaint = 0.20f;  // 盘面填充、禁用辅助信息
constexpr float kInkLine = 0.48f;   // 1px 轮廓
constexpr float kInkDim = 0.84f;    // 标签与刻度
constexpr float kInkFull = 1.00f;   // 数值、指针、已启用状态

// Ableton Sans 随用户已安装的 Ableton Live 12 存在。本插件只在运行时读取，
// 不复制、不打包、不分发该字体；无法读取时才降级到系统 Helvetica Neue Bold。
const juce::File findAbletonFont(const juce::String& filename) {
    for (const auto* app : {"/Applications/Ableton Live 12 .app",
                            "/Applications/Ableton Live 12 Suite.app",
                            "/Applications/Ableton Live 12 Standard.app"}) {
        const auto file = juce::File(app)
                              .getChildFile("Contents/App-Resources/Max/Max.app/Contents/Resources/C74/fonts")
                              .getChildFile(filename);
        if (file.existsAsFile()) return file;
    }
    return {};
}

juce::Typeface::Ptr loadInstalledAbletonFont(const juce::String& filename) {
    const auto file = findAbletonFont(filename);
    juce::MemoryBlock data;
    if (!file.existsAsFile() || !file.loadFileAsData(data)) return {};
    return juce::Typeface::createSystemTypefaceFor(data.getData(), data.getSize());
}

juce::Typeface::Ptr abletonBoldTypeface() {
    static const auto typeface = loadInstalledAbletonFont("AbletonSans-Bold.otf");
    return typeface;
}

juce::Typeface::Ptr abletonDataTypeface() {
    static const auto typeface = loadInstalledAbletonFont("AbletonSansMedium-Regular.otf");
    return typeface;
}

juce::Font abletonOrFallback(juce::Typeface::Ptr typeface, float height, float kerning = 0.0f) {
    if (typeface != nullptr)
        return juce::Font(juce::FontOptions(typeface).withHeight(height).withKerningFactor(kerning));

    return juce::Font(juce::FontOptions("Helvetica Neue", height, juce::Font::bold)
                          .withKerningFactor(kerning));
}

juce::Point<float> pointOnKnob(juce::Point<float> centre, float radius, float angle) {
    return {centre.x + radius * std::sin(angle), centre.y - radius * std::cos(angle)};
}

}  // namespace

// ---------------------------------------------------------------------------
// LookAndFeel
// ---------------------------------------------------------------------------

TraneLookAndFeel::TraneLookAndFeel() {
    setColour(juce::Label::textColourId, ink(kInkDim));
    setColour(juce::Slider::textBoxTextColourId, ink(kInkFull));
    setColour(juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
    setColour(juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour(juce::TextButton::buttonColourId, juce::Colours::transparentBlack);
    setColour(juce::TextButton::buttonOnColourId, ink(kInkFull));
    setColour(juce::TextButton::textColourOffId, ink(kInkFull));
    setColour(juce::TextButton::textColourOnId, kBg);
    setColour(juce::ComboBox::backgroundColourId, juce::Colours::transparentBlack);
    setColour(juce::ComboBox::textColourId, ink(kInkFull));
    setColour(juce::ComboBox::outlineColourId, juce::Colours::transparentBlack);
    setColour(juce::ComboBox::arrowColourId, ink(kInkFull));
    setColour(juce::PopupMenu::backgroundColourId, kBg);
    setColour(juce::PopupMenu::textColourId, ink(kInkFull));
    setColour(juce::PopupMenu::highlightedBackgroundColourId, ink(kInkFull));
    setColour(juce::PopupMenu::highlightedTextColourId, kBg);
}

juce::Font TraneLookAndFeel::ui(float height, float kerning) {
    return abletonOrFallback(abletonBoldTypeface(), height, kerning);
}

juce::Font TraneLookAndFeel::data(float height) {
    return abletonOrFallback(abletonDataTypeface(), height, -0.015f);
}

void TraneLookAndFeel::drawRotarySlider(juce::Graphics& g, int x, int y, int width, int height,
                                        float sliderPos, float rotaryStartAngle,
                                        float rotaryEndAngle, juce::Slider&) {
    const auto area = juce::Rectangle<int>(x, y, width, height).toFloat();
    const float size = juce::jmin(area.getWidth(), area.getHeight()) - 2.0f;
    const auto disk = area.withSizeKeepingCentre(size, size).reduced(0.5f);
    const auto centre = disk.getCentre();
    const float radius = disk.getWidth() * 0.5f;
    const float angle = rotaryStartAngle + sliderPos * (rotaryEndAngle - rotaryStartAngle);

    // 平面盘：没有高光、渐变、环形值弧或拟物阴影。只靠实心盘、刻度和指针读值。
    g.setColour(ink(kInkFaint));
    g.fillEllipse(disk);
    g.setColour(ink(kInkLine));
    g.drawEllipse(disk, 1.0f);

    // 起点 / 中点 / 终点是固定量程刻度；读数不依赖会抢注意力的圆弧。
    g.setColour(ink(kInkDim));
    for (const float mark : {rotaryStartAngle, 0.5f * (rotaryStartAngle + rotaryEndAngle), rotaryEndAngle}) {
        const auto a = pointOnKnob(centre, radius - 2.5f, mark);
        const auto b = pointOnKnob(centre, radius - 6.0f, mark);
        g.drawLine(a.x, a.y, b.x, b.y, 1.0f);
    }

    // 高亮指针 + 端点圆：亮白且直观，Ableton 式平面读数。
    const auto pointerFrom = pointOnKnob(centre, radius * 0.22f, angle);
    const auto pointerTo = pointOnKnob(centre, radius - 8.5f, angle);
    g.setColour(ink(kInkFull));
    g.drawLine(pointerFrom.x, pointerFrom.y, pointerTo.x, pointerTo.y, 1.6f);
    g.fillEllipse(pointerTo.x - 1.8f, pointerTo.y - 1.8f, 3.6f, 3.6f);
}

juce::Label* TraneLookAndFeel::createSliderTextBox(juce::Slider& slider) {
    auto* label = juce::LookAndFeel_V4::createSliderTextBox(slider);
    label->setFont(data(11.0f));
    label->setJustificationType(juce::Justification::centred);
    return label;
}

void TraneLookAndFeel::drawButtonBackground(juce::Graphics& g, juce::Button& b,
                                            const juce::Colour&, bool highlighted, bool down) {
    const auto r = b.getLocalBounds().toFloat().reduced(0.5f);
    const bool on = b.getToggleState();

    if (on) {
        g.setColour(ink(down ? kInkDim : kInkFull));
        g.fillRect(r);
        g.setColour(ink(kInkFull));
    } else {
        if (highlighted || down) {
            g.setColour(ink(kInkFaint));
            g.fillRect(r);
        }
        g.setColour(ink(kInkLine));
    }
    g.drawRect(r, 1.0f);
}

void TraneLookAndFeel::drawButtonText(juce::Graphics& g, juce::TextButton& b, bool, bool) {
    g.setFont(ui(10.0f, 0.035f));
    g.setColour(b.getToggleState() ? kBg : ink(kInkFull));
    g.drawText(b.getButtonText(), b.getLocalBounds(), juce::Justification::centred, false);
}

void TraneLookAndFeel::drawComboBox(juce::Graphics& g, int width, int height, bool, int, int, int,
                                    int, juce::ComboBox&) {
    const auto r = juce::Rectangle<int>(0, 0, width, height).toFloat().reduced(0.5f);
    g.setColour(ink(kInkLine));
    g.drawRect(r, 1.0f);

    const float cx = static_cast<float>(width) - 10.0f;
    const float cy = static_cast<float>(height) * 0.5f;
    g.setColour(ink(kInkFull));
    g.drawLine(cx - 3.0f, cy - 1.5f, cx, cy + 1.5f, 1.0f);
    g.drawLine(cx, cy + 1.5f, cx + 3.0f, cy - 1.5f, 1.0f);
}

juce::Font TraneLookAndFeel::getComboBoxFont(juce::ComboBox&) { return ui(10.0f); }

juce::Font TraneLookAndFeel::getPopupMenuFont() { return ui(11.0f); }

void TraneLookAndFeel::positionComboBoxText(juce::ComboBox& box, juce::Label& label) {
    label.setBounds(7, 1, box.getWidth() - 20, box.getHeight() - 2);
    label.setFont(ui(10.0f));
    label.setJustificationType(juce::Justification::centredLeft);
}

// ---------------------------------------------------------------------------
// 编辑器
// ---------------------------------------------------------------------------

TraneAudioProcessorEditor::TraneAudioProcessorEditor(TraneAudioProcessor& p)
    : juce::AudioProcessorEditor(&p), proc_(p) {
    setLookAndFeel(&lnf_);

    // 第 1 行：capture + grain
    addGroup("CAPTURE", cell(0), kLabelY[0]);
    addToggle("freeze", "FREEZE", cell(0), kRowY[0]);
    addKnob("loop_ms", "LOOP", cell(1), kRowY[0], Fmt::Ms);
    addKnob("seam_ms", "SEAM", cell(2), kRowY[0], Fmt::Ms);

    addGroup("GRAIN", cell(3), kLabelY[0]);
    addToggle("grain_on", "GRAIN", cell(3), kRowY[0]);
    addKnob("grain_size", "SIZE", cell(4), kRowY[0], Fmt::Ms);
    addKnob("grain_density", "DENSITY", cell(5), kRowY[0], Fmt::Plain);
    addKnob("grain_position", "POSITION", cell(6), kRowY[0], Fmt::Plain);
    addKnob("grain_spray", "SPRAY", cell(7), kRowY[0], Fmt::Plain);
    addKnob("grain_rate", "RATE", cell(8), kRowY[0], Fmt::X);
    addKnob("grain_spread", "SPREAD", cell(9), kRowY[0], Fmt::Plain);
    addKnob("grain_reverse", "REVERSE", cell(10), kRowY[0], Fmt::Plain);
    addKnob("grain_mix", "MIX", cell(11), kRowY[0], Fmt::Plain);

    // 第 2 行：stutter + comb + tape
    addGroup("STUTTER", cell(0), kLabelY[1]);
    addToggle("stutter_on", "STUTTER", cell(0), kRowY[1]);
    addKnob("stutter_size", "SIZE", cell(1), kRowY[1], Fmt::Ms);
    addKnob("stutter_rate", "RATE", cell(2), kRowY[1], Fmt::Hz);
    addKnob("stutter_jump", "JUMP", cell(3), kRowY[1], Fmt::Plain);
    addKnob("stutter_mix", "MIX", cell(4), kRowY[1], Fmt::Plain);

    addGroup("COMB", cell(5), kLabelY[1]);
    addToggle("comb_on", "COMB", cell(5), kRowY[1]);
    addKnob("comb_tune", "TUNE", cell(6), kRowY[1], Fmt::Hz);
    addKnob("comb_feedback", "FEEDBACK", cell(7), kRowY[1], Fmt::Plain);
    addKnob("comb_mix", "MIX", cell(8), kRowY[1], Fmt::Plain);

    addGroup("TAPE", cell(9), kLabelY[1]);
    addToggle("tape_on", "TAPE", cell(9), kRowY[1]);
    addKnob("tape_speed", "SPEED", cell(10), kRowY[1], Fmt::X);
    addKnob("tape_wobble", "WOBBLE", cell(11), kRowY[1], Fmt::Plain);
    addKnob("tape_mix", "MIX", cell(12), kRowY[1], Fmt::Plain);

    // 第 3 行：ruin + sweep + out
    addGroup("RUIN", cell(0), kLabelY[2]);
    addKnob("ruin_mode", "MODE", cell(0), kRowY[2], Fmt::Plain);
    addKnob("ruin_drive", "DRIVE", cell(1), kRowY[2], Fmt::Plain);
    addKnob("ruin_fold", "FOLD", cell(2), kRowY[2], Fmt::Plain);
    addKnob("ruin_crush", "CRUSH", cell(3), kRowY[2], Fmt::Plain);
    addKnob("ruin_ring", "RING", cell(4), kRowY[2], Fmt::Plain);

    addGroup("SWEEP", cell(5), kLabelY[2]);
    addToggle("sweep_on", "SWEEP", cell(5), kRowY[2]);
    addKnob("sweep_rate", "RATE", cell(6), kRowY[2], Fmt::Hz);
    addKnob("sweep_depth", "DEPTH", cell(7), kRowY[2], Fmt::Plain);
    addKnob("sweep_center", "CENTER", cell(8), kRowY[2], Fmt::Hz);
    addKnob("sweep_reso", "RESO", cell(9), kRowY[2], Fmt::Plain);
    addChoice("sweep_mode", cell(10), kRowY[2]);

    addGroup("OUT", cell(12), kLabelY[2]);
    addKnob("output", "OUTPUT", cell(12), kRowY[2], Fmt::Db);

    // 第 4 行：delay + space
    addGroup("DELAY", cell(0), kLabelY[3]);
    addToggle("delay_on", "DELAY", cell(0), kRowY[3]);
    addKnob("delay_time", "TIME", cell(1), kRowY[3], Fmt::Ms);
    addKnob("delay_feedback", "FEEDBACK", cell(2), kRowY[3], Fmt::Plain);
    addKnob("delay_damp", "DAMP", cell(3), kRowY[3], Fmt::Plain);
    addKnob("delay_pingpong", "PINGPONG", cell(4), kRowY[3], Fmt::Plain);
    addKnob("delay_mix", "MIX", cell(5), kRowY[3], Fmt::Plain);

    addGroup("SPACE", cell(7), kLabelY[3]);
    addKnob("space_mix", "MIX", cell(7), kRowY[3], Fmt::Plain);
    addKnob("space_size", "SIZE", cell(8), kRowY[3], Fmt::Plain);
    addKnob("space_tail", "TAIL", cell(9), kRowY[3], Fmt::Plain);
    addKnob("space_damp", "DAMP", cell(10), kRowY[3], Fmt::Plain);
    addKnob("space_diffuse", "DIFFUSE", cell(11), kRowY[3], Fmt::Plain);

    setSize(kPanelW, kPanelH);
}

TraneAudioProcessorEditor::~TraneAudioProcessorEditor() { setLookAndFeel(nullptr); }

void TraneAudioProcessorEditor::addGroup(const juce::String& text, int x, int y) {
    groups_.push_back({text, x, y});
}

void TraneAudioProcessorEditor::addKnob(const char* paramId, const juce::String& name, int x,
                                        int y, Fmt fmt) {
    auto k = std::make_unique<Knob>();
    k->slider.setSliderStyle(juce::Slider::RotaryVerticalDrag);
    k->slider.setTextBoxStyle(juce::Slider::TextBoxBelow, false, kCellW - 4, kKnobBox);
    k->slider.setRotaryParameters(juce::MathConstants<float>::pi * 1.25f,
                                  juce::MathConstants<float>::pi * 2.75f, true);
    k->slider.setDoubleClickReturnValue(true, 0.0);
    k->slider.setColour(juce::Slider::textBoxTextColourId, ink(kInkFull));

    // 数值沿用 Ableton Sans Medium 的紧凑读数；只删无意义文字，不删任何参数信息。
    k->slider.textFromValueFunction = [fmt](double v) -> juce::String {
        switch (fmt) {
            case Fmt::Ms:
                return v >= 1000.0 ? juce::String(v / 1000.0, 2) + "s"
                                   : juce::String(juce::roundToInt(v)) + "ms";
            case Fmt::Hz:
                return v >= 1000.0 ? juce::String(v / 1000.0, 2) + "k"
                                   : juce::String(v, v < 10.0 ? 2 : 0);
            case Fmt::Db:
                return juce::String(v, 1) + "dB";
            case Fmt::X:
                return juce::String(v, 2) + "x";
            case Fmt::Plain:
            default:
                return juce::String(v, v < 0.1 ? 3 : 2);
        }
    };
    k->slider.valueFromTextFunction = [](const juce::String& t) { return t.getDoubleValue(); };
    addAndMakeVisible(k->slider);

    k->label.setText(name, juce::dontSendNotification);
    k->label.setJustificationType(juce::Justification::centred);
    k->label.setFont(TraneLookAndFeel::ui(10.0f, 0.045f));
    k->label.setColour(juce::Label::textColourId, ink(kInkDim));
    addAndMakeVisible(k->label);

    k->attach = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>(
        proc_.apvts, paramId, k->slider);

    k->slider.setBounds(x + 5, y, kKnob, kKnob + kKnobBox);
    k->label.setBounds(x, y + kKnob + kKnobBox, kCellW, kLabelH);
    knobs_.push_back(std::move(k));
}

void TraneAudioProcessorEditor::addToggle(const char* paramId, const juce::String& name, int x,
                                          int y) {
    auto t = std::make_unique<Toggle>();
    t->button.setButtonText(name);
    t->button.setClickingTogglesState(true);
    t->button.setColour(juce::TextButton::buttonColourId, juce::Colours::transparentBlack);
    addAndMakeVisible(t->button);

    t->attach = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment>(
        proc_.apvts, paramId, t->button);

    t->button.setBounds(x + 5, y + (kKnob - kToggleH) / 2, kKnob, kToggleH);
    toggles_.push_back(std::move(t));
}

void TraneAudioProcessorEditor::addChoice(const char* paramId, int x, int y) {
    auto c = std::make_unique<Choice>();
    c->box.setJustificationType(juce::Justification::centredLeft);
    addAndMakeVisible(c->box);

    c->attach = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment>(
        proc_.apvts, paramId, c->box);

    c->box.setBounds(x + 5, y + (kKnob - kToggleH) / 2, kKnob, kToggleH);
    choices_.push_back(std::move(c));
}

void TraneAudioProcessorEditor::paint(juce::Graphics& g) {
    g.fillAll(kBg);

    // 只有模块标题。标题以下立刻是可操控参数，绝不再留品牌、功能清单或运行状态。
    g.setFont(TraneLookAndFeel::ui(10.0f, 0.085f));
    g.setColour(ink(kInkFull));
    for (const auto& grp : groups_)
        g.drawText(grp.text, grp.x, grp.y, 170, 13, juce::Justification::centredLeft);
}

void TraneAudioProcessorEditor::resized() {}

}  // namespace trane
