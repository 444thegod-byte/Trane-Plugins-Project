// PluginEditor.h — Träne 的界面
//
// 视觉规范（小绪定的，改之前先问）：
//   底色  纯黑 #000000，不铺任何面板色块
//   字体  全部 Helvetica Neue
//   线条  按键与旋钮一律用**发丝线**（0.5px）描边，没有圆角、没有渐变、没有阴影
//   颜色  只有黑白两色，层次靠不透明度分（0.14 / 0.28 / 0.55 / 0.92 四档）
//   排版  参考 Lux Cache：全小写、极简单词、大量留白、文字本身就是控件
//
// 四行布局，10 组，48 个控件。分组标题写在每组的第一个格子正上方。
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>

#include <memory>
#include <vector>

namespace trane {

class TraneAudioProcessor;

// ---------------------------------------------------------------------------
// 黑白发丝线 LookAndFeel
// ---------------------------------------------------------------------------
class TraneLookAndFeel : public juce::LookAndFeel_V4 {
public:
    TraneLookAndFeel();

    // 字体只从本机已安装 Ableton Live 的资源中按需读取；绝不复制或打包字体文件。
    // ui = 所有标签与开关；data = 数值读数。两者都使用 Ableton Sans 的加粗字重。
    static juce::Font ui(float height, float kerning = 0.0f);
    static juce::Font data(float height);

    void drawRotarySlider(juce::Graphics&, int x, int y, int width, int height,
                          float sliderPos, float rotaryStartAngle, float rotaryEndAngle,
                          juce::Slider&) override;
    juce::Label* createSliderTextBox(juce::Slider&) override;
    void drawButtonBackground(juce::Graphics&, juce::Button&, const juce::Colour& backgroundColour,
                              bool shouldDrawButtonAsHighlighted,
                              bool shouldDrawButtonAsDown) override;
    void drawButtonText(juce::Graphics&, juce::TextButton&, bool shouldDrawButtonAsHighlighted,
                        bool shouldDrawButtonAsDown) override;
    void drawComboBox(juce::Graphics&, int width, int height, bool isButtonDown, int buttonX,
                      int buttonY, int buttonW, int buttonH, juce::ComboBox&) override;
    juce::Font getComboBoxFont(juce::ComboBox&) override;
    juce::Font getPopupMenuFont() override;
    void positionComboBoxText(juce::ComboBox&, juce::Label&) override;
};

// ---------------------------------------------------------------------------
// 编辑器
// ---------------------------------------------------------------------------
class TraneAudioProcessorEditor : public juce::AudioProcessorEditor {
public:
    explicit TraneAudioProcessorEditor(TraneAudioProcessor&);
    ~TraneAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;

private:
    // 数值显示格式：面板窄，必须紧凑，否则一排长数字会把留白吃光
    enum class Fmt { Plain, Ms, Hz, Db, X };

    void addKnob(const char* paramId, const juce::String& name, int x, int y, Fmt fmt);
    void addToggle(const char* paramId, const juce::String& name, int x, int y);
    void addChoice(const char* paramId, int x, int y);
    void addGroup(const juce::String& text, int x, int y);

    TraneAudioProcessor& proc_;

    TraneLookAndFeel lnf_;

    struct Knob {
        juce::Slider slider;
        juce::Label label;
        std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> attach;
    };
    struct Toggle {
        juce::TextButton button;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> attach;
    };
    struct Choice {
        juce::ComboBox box;
        std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> attach;
    };
    std::vector<std::unique_ptr<Knob>> knobs_;
    std::vector<std::unique_ptr<Toggle>> toggles_;
    std::vector<std::unique_ptr<Choice>> choices_;

    struct GroupLabel {
        juce::String text;
        int x = 0;
        int y = 0;
    };
    std::vector<GroupLabel> groups_;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(TraneAudioProcessorEditor)
};

}  // namespace trane
