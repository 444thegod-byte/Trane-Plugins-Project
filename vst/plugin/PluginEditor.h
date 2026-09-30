// PluginEditor.h — Träne 的编辑器（v0.30：左世界树 + 右参数检查器）
//
// ============================================================================
// 这一层刻意做得很薄
// ============================================================================
//
// 所有绘制与几何都在 `TranePanel` 里（那一层不依赖 juce_audio_processors，
// 因此可以离线渲染成 PNG 做机器验证）。编辑器只做四件事：
//
//   1) 把鼠标 / 键盘事件翻译成面板的命中测试，再把结果写进 APVTS；
//   2) 每 1/30 秒把 APVTS 与音频线程的遥测抄进 PanelState，然后重绘
//      （节奏由显示器的 vblank 驱动，不是定时器 —— 见下面 `vblank_`）；
//   3) 管住窗口尺寸（**锁定 1440:720 = 2:1**）；
//   4) 维护交互四态里的三个（hover / press / focus）。
//
// 一个子控件都没有。48 个 Slider/Label 表达不了"一棵会呼吸的树"这种东西，
// 硬套只会两边都别扭。
//
// ============================================================================
// 交互（全部在这里定死，别处不要另立一套）
// ============================================================================
//
//   **顶栏**    左边 ALL / MODULE 切模式；右边 1 / 2 / 3 / 4 切 MODULE 模式的列数
//               （ALL 模式下禁用 —— Apple 的禁用控件是"摊平"的，不是"变暗的"）。
//
//   **分割线**  按住左右拖，范围 300–560。拖动时参数区跟着走：列宽、行距、
//               字号全部重算（`buildInspector` 是**算出来的**，不是常量表）。
//
//   **参数行**  竖直拖 = 改值，全量程 200 逻辑像素。**Shift = 5 倍细**，
//               **Cmd/Ctrl = 20 倍细**。单击档位参数切下一档；双击复位到出厂值。
//               滚轮 = ±1/200 量程（Shift 时 ±1/1000）。
//
//   **模块标题行 / 树上的圆心**  两者是**同一个东西** —— 这个模块的开关。
//               单击切换，双击复位这个模块的全部参数。
//
//   **树上的圆环**  只做指针反馈（悬停提亮圆边框，并同时点亮检查器里
//               对应的标题行，于是"左边那个圆是哪个模块"不用猜）。
//               它**没有单击动作** —— 树上十个圆是**显示**，检查器才是操作面。
//
//   **键盘**    Tab / Shift+Tab / ↑ / ↓ 在参数行之间移动焦点（只走**当前真的
//               显示出来**的行）；← / → 微调（连续参数 ±1/100 量程，档位参数换档）；
//               回车 = 切换焦点所在模块的开关；Esc = 取消焦点。
//               焦点态是**唯一**允许出现强调色 #0A84FF 的地方（Apple 的
//               keyboardFocusIndicator）。
//
//               **空格故意不绑。** Ableton 里空格是播放 / 停止，插件去抢宿主
//               最常用的那个键，用户每按一次都会骂人。回车的语义同样清楚，
//               而且宿主很少占用它。
//
//   **背景图**  顶栏中段那一组三件（v0.31 新增）：
//               ① 「选择图片」格 —— 点一下开系统文件对话框，读进来的图塞进
//                  `state_.backdrop.image`。**读文件是这一层的职责**：面板层
//                  只吃一个 juce::Image，绝不碰 I/O（离线可验证性靠这条活着，
//                  tests/test_editor_layout.py 有断言盯着）。
//               ② [关][树][参数] —— 背景垫在哪儿。关 = 不画（图还留着）。
//               ③ 明暗度轨道 —— 沿轨道拖，位置**直接**映射成倍率
//                  （`panel::trackToBright`，几何级数）。不是相对拖拽：
//                  轨道是可见的，点哪儿就该是哪儿的亮度。
//
// 所有离散动作都放在**松手**时执行，不在按下时执行 —— 但**不是**因为
// "双击的第二个 mouseUp 会被抑制掉"，那是错的。读 juce_Component.cpp:2599-2604
// 可以看到 `internalMouseUp` 是先调 `mouseUp` 再调 `mouseDoubleClick`，
// 一次双击送来的是「松手1 → 松手2 → 双击」三个事件。
//
// 所以真正成立的是另一条：**单击动作自己满足"做两遍等于没做"** ——
// 开关 关→开→复位(默认关) = 关，档位 走两档再复位回 LP，连续参数单击本来就不改值，
// 明暗度轨道是**绝对位置**映射（同一个 x 点两次结果相同）。
// 代价是双击时中间闪一下，换来的是每次点开关都是零延迟。
//
// 唯一不满足这条的是「选择图片」——开两次系统对话框显然不是"等于没做"。
// 所以它带一个 `choosing_` 闸：对话框还开着就不再开第二个。
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
    float pressValue_ = 0.0f;    // 按下那一刻的值，拖拽从它算绝对偏移
    float pressY_ = 0.0f;
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
