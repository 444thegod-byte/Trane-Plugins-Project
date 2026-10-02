// PluginEditor.h — JUCE editor and input handling.
// Rendering/geometry live in TranePanel; this layer writes host parameters.
// Bars drag horizontally or accept track clicks. Knobs drag vertically.
// Choices select their clicked segment. Shift is 5x finer, Cmd/Ctrl is 20x finer.
// Double-click resets a parameter or a module's non-switch parameters.
// Tab/up/down select parameters; left/right edit; Return toggles the module.
// Space remains available to the DAW transport.
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>

#include "TranePanel.h"

namespace trane {

class TraneAudioProcessor;

class TraneAudioProcessorEditor : public juce::AudioProcessorEditor,
                                  private juce::Timer {
public:
    explicit TraneAudioProcessorEditor(TraneAudioProcessor&);
    ~TraneAudioProcessorEditor() override;

    void paint(juce::Graphics&) override;
    void resized() override;
    void visibilityChanged() override;

    void mouseDown(const juce::MouseEvent&) override;
    void mouseDrag(const juce::MouseEvent&) override;
    void mouseUp(const juce::MouseEvent&) override;
    void mouseMove(const juce::MouseEvent&) override;
    void mouseExit(const juce::MouseEvent&) override;
    void mouseWheelMove(const juce::MouseEvent&, const juce::MouseWheelDetails&) override;
    void mouseDoubleClick(const juce::MouseEvent&) override;
    bool keyPressed(const juce::KeyPress&) override;

private:
    void timerCallback() override;

    void updateScale();                  // 窗口尺寸 → scale_ + 底图缓存
    void syncFromHost();                 // APVTS → PanelState
    void syncTelemetry();                // 音频线程的 atomic → 发光强度
    void setControl(int index, float normalised);
    void nudgeChoice(int index, int delta);
    void resetToDefault(int index);
    void toggleModule(int node);
    // v0.33 删掉了 `setMode` / `setModuleCount` —— 版面只有一种了（小绪：
    // 「仍然删掉，只要 ALL」）。**函数一起删**，不是留着空转：留着它，
    // 检查器里那句「源码里出现过 setMode」就还能绿，而模式早就没了。
    void setHover(juce::Point<float> logicalPos);
    void applyCursor(const panel::Hit&);

    // 背景图。**I/O 只在这三个函数里发生**，面板层永远只拿到一个 juce::Image。
    void pickBackdrop();                          // 开系统文件对话框
    void adoptBackdrop(const juce::File&);        // 读图 → state_.backdrop
    void setBackdropWhere(panel::BgWhere);        // 关 / 全屏
    void setBackdropBrightness(float brightness); // 由轨道 x 反推
    float brightnessAt(float x) const;            // 轨道 x → 倍率（几何映射）
    void pushBackdropState();                     // 三个值写回 apvts.state
    void pullBackdropState();                     // 从 apvts.state 读回来（宿主改过就跟着改）

    // 焦点在**当前显示出来的**参数行之间走。
    void moveFocus(int delta);

    juce::AudioProcessorParameter* paramOf(int index) const;
    juce::Point<float> logical(const juce::MouseEvent&) const;

    TraneAudioProcessor& proc_;

    panel::PanelState state_;
    panel::PanelCache cache_;
    float scale_ = 1.0f;

    // 呼吸用的时间原点。用真实时钟而不是"每帧 +1/30" ——
    // 定时器被系统拖慢时，呼吸的节奏不该跟着变。
    double timeBase_ = 0.0;

    // ---- 动画驱动：VBlankAttachment ----
    //
    // v0.32.2 曾用「空闲时 30Hz → 15Hz 降帧」来省 CPU。那是错的：呼吸是**连续的**
    // 视觉，降到 15Hz 会肉眼可见地一顿一顿（小绪 09-29：「生硬、不丝滑」）。
    // 省下来的 CPU 换不回观感，这个交易不划算 —— 撤掉。
    //
    // 换成 VBlankAttachment（JUCE 7 起提供）：
    //   · Timer 由消息线程的定时器队列驱动，误差几毫秒是常态 —— 帧间隔不齐，
    //     看起来就是"卡"。VBlank 跟着显示器刷新走，帧间隔天然均匀。
    //   · 回调带一个「这一帧什么时候被呈现」的时间戳，用它推进相位：
    //     掉帧不会让动画变慢或攒出一串"补帧"。
    //   · 回调本身很轻（记一笔 + 没到点就直接返回），120Hz 屏也不会白烧。
    //
    // 保留 Timer **只当看门狗**：宿主 / 远程桌面不给 vblank 时退回定时器驱动，
    // 宁可抖一点也不能让画面冻住。
    juce::VBlankAttachment vblank_;
    double nextFrameSec_ = 0.0;        // 下一帧该呈现的时刻（vblank 时间戳，秒）
    double lastVBlankSec_ = -1.0e9;    // 最近一次 vblank —— 看门狗判据
    static constexpr double kFramePeriodSec = 1.0 / 30.0;

    // 上一拍的时刻 —— 用来给 hover 淡入算 dt（v0.33 新增）。
    // 负值 = 还没有过上一拍，第一拍 dt 取 0。
    double lastTickSec_ = -1.0e9;

    void onVBlank(double timestampSec);   // 跟着显示器刷新
    void tick(double nowSec);             // 真正干活：同步状态 + 重绘

    // 拖参数
    int dragControl_ = -1;       // 已越过阈值、正在拖的参数
    int pressControl_ = -1;      // 按下时命中的参数（可能一直没动，那就是单击）
    // v0.33：模块标题行就是那个模块的开关，于是"点标题行"不再需要单独一条
    // 路径（原来靠 `pressNode_` + `pressOnCore_` 记"点在树上那个圆里"）。
    // 但开关**必须和参数行分开**，因为拖拽语义不同：参数是数字（拖 = 擦洗），
    // 开关是布尔（只有单击）。所以按下时把它挑出来存这儿，`pressControl_`
    // 让开。判据是 `controlSlot < 0` —— 控制表里对"开关"的既有定义。
    int pressSwitch_ = -1;
    float pressX_ = 0.0f;
    float pressY_ = 0.0f;
    juce::Point<float> dragLast_;
    float dragValue_ = 0.0f;
    bool pressMoved_ = false;    // 越过拖拽阈值 —— 松手时不再当单击处理

    // v0.33 删掉了 `dragDivider_` / `dividerGrab_`（分割线拖拽）。
    // 顺带删掉的是它们当年存在的理由：抓取点与分割线的水平距离在整段拖拽里
    // 保持不变，否则一按下去线就"跳"到指针正下方 —— 这条经验对以后的
    // 任何"可拖分隔"仍然成立，但**没有住户了**，所以代码不留。

    // 按下那一刻的命中结果，**原样存着**。松手时的判定（哪一组、哪一格、
    // 算不算数）全部交给 panel::resolveBarClick —— 编辑器不做任何翻译。
    // 曾经把 option 编进一个 `pressTab_` 里当组号用，于是点 MODULE 时组判据
    // 错位成"必须是列数段"，条件永远不成立（详见 TranePanel.h 的 BarGroup）。
    // v0.33：分段控件只剩背景落位一组，这个类型仍然照原样留着 —— 判定逻辑
    // （组 + 格 + 没拖动）是对的，而且**错法的墓志铭比错法本身活得久**。
    panel::Hit pressHit_;

    // ---- 背景图 ----
    // **必须是成员**：`FileChooser` 一旦析构，系统对话框当场消失。
    // 而且它是异步的（`launchAsync`），回调要等用户选完才回来。
    std::unique_ptr<juce::FileChooser> chooser_;
    bool choosing_ = false;        // 对话框开着 —— 双击不该开出第二个来
    juce::Image backdropSource_;   // 原图。换图才重读；改落位 / 明暗度都不碰它
    juce::String backdropPath_;    // 存进工程的那一项。**面板不认这个** —— 它只管画
    // 上次从宿主读到的那三个值。存成三个独立字段而不是处理器那个结构体，
    // 是为了让这个头文件**不必** include PluginProcessor.h（那会让外壳的定义
    // 反向依赖进界面层，正是当初把面板拆出来时要避免的事）。
    juce::String hostPath_;
    int   hostWhere_ = -1;
    float hostBright_ = -1.0f;
    bool  pressBgSlot_ = false;    // 按下的是「选择图片」格
    bool  dragBright_ = false;     // 正在拖明暗度轨道

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(TraneAudioProcessorEditor)
};

}  // namespace trane
