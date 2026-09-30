// PluginEditor.cpp — Träne 的编辑器：一层薄适配（v0.30）
//
// ============================================================================
// 这里**不画任何东西**
// ============================================================================
//
// 所有绘制都在 TranePanel 里。这一层只做四件事：
//
//   1) 鼠标 / 键盘 → panel::hitTest → APVTS（带 beginChangeGesture / endChangeGesture）；
//   2) 每 1/30 秒：APVTS + 音频线程遥测 → PanelState → repaint
//      （节奏由显示器 vblank 驱动，定时器只当看门狗）；
//   3) 窗口尺寸（锁 1440:720 = 2:1，底图按显示器 DPI 预渲染）；
//   4) 维护交互四态里的 hover / press / focus。
//
// 一个子控件都没有 —— 理由写在 TranePanel.h 的开头。
//
// ============================================================================
// 关于双击：**JUCE 是先 mouseUp 再 mouseDoubleClick，不是相反**
// ============================================================================
//
// 读 juce_Component.cpp:2599-2604（`internalMouseUp`）可以看到顺序是：
//
//     target->mouseUp (me);
//     ...
//     if (me.getNumberOfClicks() >= 2) target->mouseDoubleClick (...);
//
// 也就是说一次双击送来的是：
//
//     按下 1 · 松手 1   → 单击动作
//     按下 2 · 松手 2   → 单击动作
//     双击              → 复位
//
// 松手动作**不会**被抑制掉。所以单击动作必须自己满足"做两遍 = 没做"：
//
//     · 模块开关（标题行 / 树上的圆心）  关 → 开 → 复位（默认关）= 关      ✓
//     · 档位参数（LP/BP/HP）             往下一档走两次再复位到 LP         ✓
//     · 连续参数                         单击本来就不改值，只有复位         ✓
//
// 于是双击在三种控件上结果都对，代价只是中间闪一下。这样比"把单击动作延后
// 一个双击间隔（250ms 上下）再执行"好得多 —— 后者会让每次点模块开关都发钝。
#include "PluginEditor.h"
#include "PluginProcessor.h"

#include <cmath>

namespace trane {

namespace {

// 面板的逻辑尺寸就是几何常量本身，这里只给个短名字。
constexpr float kBaseW = panel::geom::kBaseW;   // 1440
constexpr float kBaseH = panel::geom::kBaseH;   // 720

// 呼吸 + 闪烁的刷新率。2.6 秒一个呼吸周期，30Hz 足够平滑。
//
// 实测（v0.32.3，panel_probe --scale 2 --state demo --frames 150，2880×1440 @2x）：
//     底图 0.43 · 信号线 0.27 · 质点 1.08 · 顶栏 0.14 · 检查器 0.69 = **每帧 2.60 ms**
//     30Hz 占单核 7.8%（v0.32.2 是 3.27 ms / 9.8%）
// 换机器后要重测：`TRANE_PROF=1 panel_probe --frames 150 ...`。
constexpr int kFrameHz = 30;

// 缩放下限/上限。
// 下限 0.60：参数名是 11pt，0.60 下是 6.6 逻辑像素 —— 再小就糊成一团了。
// 上限 1.50：1440×720 的 1.5 倍是 2160×1080，再大只是白占屏幕。
constexpr float kMinScale = 0.60f;
constexpr float kMaxScale = 1.50f;

// 竖直拖的全量程像素数。Shift = 5 倍细，Cmd/Ctrl = 20 倍细。
constexpr float kDragSpan = 200.0f;
constexpr float kDragFine = 5.0f;
constexpr float kDragFinest = 20.0f;

// 超过这个像素数才算"拖"，否则算"点" —— 手抖 1px 不该把单击变成拖拽。
constexpr float kDragThreshold = 2.0f;

// 一格滚轮 / 一次方向键走多少量程
constexpr float kWheelStep = 1.0f / 200.0f;
constexpr float kWheelStepFine = 1.0f / 1000.0f;
constexpr float kKeyStep = 1.0f / 100.0f;

// 这个显示器上 物理像素 / 逻辑像素。底图按它预渲染，Retina 上才不糊。
// 注意用的是 userBounds（扣掉菜单栏/Dock）而不是 logicalBounds。
float desktopScaleFor(const juce::Component& c) {
    if (auto* d = juce::Desktop::getInstance().getDisplays().getDisplayForRect(c.getScreenBounds()))
        return static_cast<float>(d->scale);
    return 1.0f;
}

// 默认窗口尺寸：**放得下就用 1:1，放不下才缩**。
//
// 面板 1440×720 是设计稿定的尺寸（宽高比锁死 2:1）。1440 宽在 1440×900 的
// 笔记本上横向会顶到边，所以要**两个方向一起量**：只按高度算会让窗口横向出屏，
// 只按宽度算会在宽屏上留一大堆空白。
// 窗口本身可拉伸（锁死宽高比），想要大就自己拉大。
juce::Rectangle<int> defaultEditorBounds() {
    float availW = kBaseW;
    float availH = kBaseH;
    if (auto* d = juce::Desktop::getInstance().getDisplays().getPrimaryDisplay()) {
        availW = juce::jmax(720.0f, d->userBounds.getWidth() - 60.0f);
        availH = juce::jmax(360.0f, d->userBounds.getHeight() - 90.0f);
    }

    const float s = juce::jlimit(kMinScale, 1.0f,
                                 juce::jmin(availW / kBaseW, availH / kBaseH));
    return {0, 0, juce::roundToInt(kBaseW * s), juce::roundToInt(kBaseH * s)};
}

}  // namespace

// ============================================================================
// 构造 / 析构
// ============================================================================
TraneAudioProcessorEditor::TraneAudioProcessorEditor(TraneAudioProcessor& p)
    : juce::AudioProcessorEditor(&p), proc_(p) {
    setOpaque(true);            // 面板自己铺满整幅，没有透明区域
    setWantsKeyboardFocus(true);

    // 宽高比锁死。允许自由拉伸的话圆会变成椭圆 —— 树的半径、列距、树高
    // 全是按"圆"和固定比例算的，一拉就全错，整套几何废掉。
    setResizable(true, true);
    setResizeLimits(juce::roundToInt(kBaseW * kMinScale),
                    juce::roundToInt(kBaseH * kMinScale),
                    juce::roundToInt(kBaseW * kMaxScale),
                    juce::roundToInt(kBaseH * kMaxScale));
    if (auto* c = getConstrainer())
        c->setFixedAspectRatio(static_cast<double>(kBaseW) / static_cast<double>(kBaseH));

    const auto bounds = defaultEditorBounds();
    setSize(bounds.getWidth(), bounds.getHeight());

    // 先把状态填成出厂值，编辑器一打开就是对的，不用等第一帧定时器。
    for (int i = 0; i < panel::controlCount(); ++i) state_.value[i] = panel::defaultNormalised(i);
    for (int n = 0; n < panel::kMaxNodes; ++n) state_.moduleActivity[n] = 1.0f;
    // v0.33：`mode` / `moduleCount` / `dividerX` 三个字段已删 —— 版面只有一种，
    // 分栏是编译期常量表，参数区边界是常量。出厂状态少填三样东西。

    // 背景图：宿主可能已经把状态塞回来了（宿主先 setStateInformation、
    // 再 createEditor 是常规顺序）。这里读一次，读不到就保持出厂（没有背景）。
    pullBackdropState();

    // 动画挂到显示器的 vblank 上。放在最后 —— attachment 要在组件已经
    // 有了尺寸和 peer 之后才认得出自己在哪块屏上。
    vblank_ = juce::VBlankAttachment{this, [this](double t) { onVBlank(t); }};
}

TraneAudioProcessorEditor::~TraneAudioProcessorEditor() {
    stopTimer();
    vblank_ = {};   // 先摘掉 vblank，再让成员析构 —— 回调里会碰 cache_
}

// ============================================================================
// 尺寸
// ============================================================================
void TraneAudioProcessorEditor::updateScale() {
    scale_ = static_cast<float>(getWidth()) / kBaseW;
    cache_.ensure(scale_ * desktopScaleFor(*this));
}

void TraneAudioProcessorEditor::resized() {
    updateScale();
}

void TraneAudioProcessorEditor::visibilityChanged() {
    if (isVisible()) {
        timeBase_ = 0.0;      // 重新起算，别让停掉的这段时间把呼吸跳一大格
        nextFrameSec_ = 0.0;
        lastVBlankSec_ = -1.0e9;
        updateScale();        // 露出来的时候才知道自己在哪个显示器上
        syncFromHost();
        syncTelemetry();
        startTimerHz(kFrameHz);   // 只是看门狗，vblank 正常时它什么都不做
    } else {
        // 关掉窗口就别再算了 —— 30Hz 的呼吸是实打实的 CPU。
        stopTimer();
        // 顺手把 backdrop（2880×1440 @2x ≈ 16 MB）放掉。宿主里挂十几个实例、
        // 窗口都关着的时候，这十几 MB 乘起来不是小数目；下次露出来
        // visibilityChanged 会重建，用户看不到中间过程。
        cache_.release();
    }
}

// ============================================================================
// 绘制
// ============================================================================
void TraneAudioProcessorEditor::paint(juce::Graphics& g) {
    juce::Graphics::ScopedSaveState save{g};
    // 面板按 1440×720 的逻辑坐标画，窗口多大就整体缩放到多大。
    // 底图是按显示器 DPI 预渲染的，所以这里的缩放不会让底图糊。
    g.addTransform(juce::AffineTransform::scale(scale_));
    panel::paint(g, state_, cache_);
}

// ============================================================================
// 每帧
// ============================================================================
// 动画由**显示器的 vblank** 驱动，不是定时器。
//
// v0.32.2 曾用「空闲时 30Hz → 15Hz 降帧」省 CPU。那是错的：呼吸是连续视觉，
// 降到 15Hz 一顿一顿（小绪 09-29：「生硬、不丝滑」）。省下的 CPU 换不回观感。
//
// 换成 vblank 的理由：
//   · Timer 由消息线程的定时器队列驱动，误差几毫秒是常态 —— 帧间隔不齐就是"卡"。
//   · vblank 回调带一个「这一帧什么时候被呈现」的时间戳，用它推进相位，
//     掉帧不会让动画变慢、也不会攒出一串"补帧"。
void TraneAudioProcessorEditor::onVBlank(double timestampSec) {
    lastVBlankSec_ = timestampSec;

    // 只在跨过 1/30 秒时真的画一帧。**从这一帧的实际呈现时刻重新起算**，
    // 不是累加 —— 累加的话宿主忙一下掉两帧，之后会连补两帧，看着就是一跳一跳。
    if (timestampSec < nextFrameSec_) return;
    nextFrameSec_ = timestampSec + kFramePeriodSec;
    tick(timestampSec);
}

// 看门狗。宿主 / 远程桌面不派发 vblank 时退回定时器驱动 ——
// 宁可抖一点，也不要画面冻住。
void TraneAudioProcessorEditor::timerCallback() {
    const double now = juce::Time::getMillisecondCounterHiRes() * 0.001;
    if (now - lastVBlankSec_ < 0.25) return;   // vblank 正常，这一拍什么都不用做
    if (now < nextFrameSec_) return;
    nextFrameSec_ = now + kFramePeriodSec;
    tick(now);
}

// 真正干活的一拍。**时间用传进来的那一拍**，不在函数内部再读一次时钟 ——
// 相位该落在"这一帧被呈现的时刻"上，不是"我们开始画它的时刻"。
void TraneAudioProcessorEditor::tick(double nowSec) {
    if (timeBase_ <= 0.0) timeBase_ = nowSec;
    state_.time = static_cast<float>(nowSec - timeBase_);

    // hover 淡入的 dt。
    //
    // **两个时钟会混进来**：vblank 给的是"这一帧什么时候被呈现"，看门狗定时器
    // 给的是 `getMillisecondCounterHiRes()` —— 基准不同。两边切换的那一拍
    // dt 会是一个荒唐的数（可能负几十万秒），所以这里**先夹再喂**：
    //
    //   · dt < 0（换了时钟 / 回调乱序）→ 0：不推进，只重新对表。
    //     下一拍就是正常的 1/30 了，最多冻住一帧。
    //   · dt 很大（挂起、远程桌面掉帧）→ 夹到 0.25。0.25 / kHoverFade(0.16) > 1，
    //     于是 `step` 直接推到位 —— 卡顿之后**不补帧**，淡入就当场结束，
    //     而不是用几十帧慢慢爬完（那才是真的"忽快忽慢"）。
    const double rawDt = nowSec - lastTickSec_;
    lastTickSec_ = nowSec;
    state_.hoverFade.step(static_cast<float>(juce::jlimit(0.0, 0.25, rawDt)));

    syncFromHost();
    syncTelemetry();
    pullBackdropState();   // 宿主可能刚把状态换掉（撤销 / 加载预设 / 恢复工程）

    repaint();
}

// APVTS → PanelState。用参数自己的 getValue()（已经是归一化值），
// 而不是 getRawParameterValue()（那是真值，还得自己按 skew 换算一遍，
// 换算写错就是轨道长度全错 —— TranePanel.h 里记着这个坑）。
void TraneAudioProcessorEditor::syncFromHost() {
    const int n = panel::controlCount();
    for (int i = 0; i < n; ++i)
        if (auto* p = paramOf(i))
            state_.value[i] = juce::jlimit(0.0f, 1.0f, p->getValue());
}

// 音频线程的 atomic → 发光强度。
//
// **先把整条数组填成 1.0（"在响"），再用真实遥测覆盖。** 没有遥测的模块保持
// 1.0 是诚实的 —— 界面不知道它忙不忙，只知道它开着。编一个假的脉动出来才是骗人。
void TraneAudioProcessorEditor::syncTelemetry() {
    for (int n = 0; n < panel::kMaxNodes; ++n) state_.moduleActivity[n] = 1.0f;

    const auto put = [this](const char* module, float v) {
        for (int n = 0; n < panel::kMaxNodes; ++n) {
            if (panel::nodeModule(n) == module) {
                state_.moduleActivity[n] = juce::jlimit(0.0f, 1.0f, v);
                return;
            }
        }
    };

    // freeze：真的冻住了才亮到满 —— 开关打开但缓冲还没喂满时它不该装成在响。
    put("freeze", proc_.uiFreezeActive.load());
    // grain：12 个声部算"满"。粒子的密度旋钮最大 100/s，声部数才是实际在响的量。
    put("grain", proc_.uiGrainVoices.load() / 12.0f);
    // tape：偏离 1.0 倍速越远越"忙"，25% 的偏移就算满。
    put("tape", std::abs(proc_.uiTapeSpeed.load() - 1.0f) * 4.0f);
    // out：限制器压下去多少就亮多少（uiGainReduction 是增益，1.0 = 没压）。
    put("out", 1.0f - proc_.uiGainReduction.load());
}

// ============================================================================
// 写参数
// ============================================================================
juce::AudioProcessorParameter* TraneAudioProcessorEditor::paramOf(int index) const {
    if (index < 0 || index >= panel::controlCount()) return nullptr;
    return proc_.apvts.getParameter(panel::controlAt(index).id);
}

juce::Point<float> TraneAudioProcessorEditor::logical(const juce::MouseEvent& e) const {
    return e.position / scale_;
}

void TraneAudioProcessorEditor::setControl(int index, float normalised) {
    auto* p = paramOf(index);
    if (p == nullptr) return;

    const float v = panel::quantise(index, juce::jlimit(0.0f, 1.0f, normalised));
    state_.value[index] = v;          // 先落本地，画面这一帧就跟上
    p->setValueNotifyingHost(v);      // 再通知宿主 —— 拖的时候要能立刻听见
}

void TraneAudioProcessorEditor::nudgeChoice(int index, int delta) {
    auto* p = paramOf(index);
    if (p == nullptr) return;

    // 档位数量问参数自己，不在界面里写死 3 —— 以后 sweep_mode 加一档，
    // 界面不该跟着改。dynamic_cast 失败时退回 3（当前 LP/BP/HP）。
    int count = 3;
    if (auto* choice = dynamic_cast<juce::AudioParameterChoice*>(p))
        count = juce::jmax(2, choice->choices.size());

    const int current = juce::jlimit(0, count - 1,
                                     juce::roundToInt(state_.value[index] * static_cast<float>(count - 1)));
    const int next = ((current + delta) % count + count) % count;
    const float v = static_cast<float>(next) / static_cast<float>(count - 1);

    p->beginChangeGesture();
    p->setValueNotifyingHost(v);
    p->endChangeGesture();
    state_.value[index] = v;
}

void TraneAudioProcessorEditor::resetToDefault(int index) {
    auto* p = paramOf(index);
    if (p == nullptr) return;

    const float v = juce::jlimit(0.0f, 1.0f, p->getDefaultValue());
    p->beginChangeGesture();
    p->setValueNotifyingHost(v);
    p->endChangeGesture();
    state_.value[index] = v;
}

void TraneAudioProcessorEditor::toggleModule(int node) {
    const int ci = panel::nodeSwitchControl(node);
    if (ci < 0) return;   // RUIN / SPACE / OUT 没有开关参数
    auto* p = paramOf(ci);
    if (p == nullptr) return;

    const float v = state_.value[ci] > 0.5f ? 0.0f : 1.0f;
    p->beginChangeGesture();
    p->setValueNotifyingHost(v);
    p->endChangeGesture();
    state_.value[ci] = v;
}

// v0.33：`setMode` / `setModuleCount` 两个函数整段删除。它们做的事
// （换行表、清焦点、清 hover/press）在"只有一种版面"之后没有意义了 ——
// 版面切换是行表的**唯一**住户，行表不动，就没有需要清的东西。
//
// 顺带记一句：这两个函数曾经是「MODULE 标签点不开」那条链路的终点。
// 现在链路整个没了，但**终点之后的判定**（barGroupOf + resolveBarClick）
// 留着 —— 它服务背景落位组，而且它的组号/格号分离是拿一个真 Bug 换的。

// ============================================================================
// 指针状态
// ============================================================================
void TraneAudioProcessorEditor::setHover(juce::Point<float> p) {
    const auto hit = panel::hitTest(p, state_);
    const auto m = hit.mark();
    // v0.33：`hover` 这个字段并进了 `hoverFade.cur` —— 留着两份就会分叉
    // （一份是"指针在哪"、一份是"亮到什么程度"，而后者是从前者推出来的）。
    // 目标没变时 `retarget` 自己会早退，所以这里不需要再比一遍。
    if (m != state_.hoverFade.cur) {
        state_.hoverFade.retarget(m);
        repaint();
    }
    applyCursor(hit);
}

void TraneAudioProcessorEditor::applyCursor(const panel::Hit& hit) {
    using Kind = panel::Hit::Kind;
    switch (hit.kind) {
        // v0.33：`Divider` / `TabMode` / `TabCount` / `Node` 四种已删。
        // `Node` 那一条本来分两种情况（圆心可点、圆环只显示），现在统一成
        // 模块标题行 —— 它**一定**可点（除非这个模块没有开关，那它的
        // `control` 就是 -1，见下）。
        case Kind::BgBright: setMouseCursor(juce::MouseCursor::LeftRightResizeCursor); break;
        case Kind::Control:
            // 参数行 = 上下拖（改值）；模块开关 = 单击（布尔没有"拖"）。
            // 两种光标分开，指针自己就把"这个能拖"和"这个只能点"说清楚了。
            setMouseCursor(hit.control >= 0 && panel::controlSlot(hit.control) < 0
                               ? juce::MouseCursor::PointingHandCursor
                               : juce::MouseCursor::UpDownResizeCursor);
            break;
        case Kind::TabBg:
        case Kind::BgSlot:   setMouseCursor(juce::MouseCursor::PointingHandCursor); break;
        case Kind::None:     setMouseCursor(juce::MouseCursor::NormalCursor); break;
    }
}

// ============================================================================
// 背景图
// ============================================================================
// 这一节是**唯一**碰文件系统的地方。面板层（TranePanel）只吃一个 juce::Image，
// 因为它的可验证性建立在"离线渲染的输入 = PanelState"上 —— 一旦面板自己读文件，
// 离线渲染的输入就不再完整，像素检查也就失去意义了。
// tests/test_editor_layout.py 里有断言盯着：TranePanel 里不许出现
// File / ImageFileFormat / loadFrom。
void TraneAudioProcessorEditor::pickBackdrop() {
    // 双击会送两次 mouseUp —— 不加闸就会开出两个对话框。
    if (choosing_) return;
    choosing_ = true;

    chooser_ = std::make_unique<juce::FileChooser>(
        "Choose Background Image", juce::File{}, "*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp;*.tiff");

    chooser_->launchAsync(juce::FileBrowserComponent::openMode
                              | juce::FileBrowserComponent::canSelectFiles,
                          [this](const juce::FileChooser& fc) {
        choosing_ = false;
        const auto f = fc.getResult();
        if (f.existsAsFile()) adoptBackdrop(f);
    });
}

void TraneAudioProcessorEditor::adoptBackdrop(const juce::File& f) {
    // **先用 ImageFileFormat 解，不用 ImageCache** —— ImageCache 是异步的，
    // 第一次调用拿到的是空图，界面会先闪一下"没图"。这里要的是同步结果。
    auto img = juce::ImageFileFormat::loadFrom(f);
    if (!img.isValid()) return;   // 解不出来就什么都不做（不把原来的图弄丢）

    backdropSource_ = img;
    state_.backdrop.image = img;
    state_.backdrop.name = f.getFileName();
    backdropPath_ = f.getFullPathName();
    if (state_.backdrop.where == panel::BgWhere::Off)
        state_.backdrop.where = panel::BgWhere::Full;   // 选了图就该看得见
    pushBackdropState();
    repaint();
}

void TraneAudioProcessorEditor::setBackdropWhere(panel::BgWhere w) {
    if (state_.backdrop.where == w) return;
    state_.backdrop.where = w;
    pushBackdropState();
    repaint();
}

void TraneAudioProcessorEditor::setBackdropBrightness(float brightness) {
    const float b = juce::jlimit(panel::geom::kBgBrightMin,
                                 panel::geom::kBgBrightMax, brightness);
    if (std::abs(b - state_.backdrop.brightness) < 1.0e-4f) return;
    state_.backdrop.brightness = b;
    pushBackdropState();
    repaint();
}

float TraneAudioProcessorEditor::brightnessAt(float x) const {
    // 换算只有一份实现（面板里的 `trackToBright`）—— 这边不自己写公式，
    // 否则绘制画的位置和点击取的值迟早会分叉。
    return panel::trackToBright((x - panel::geom::kBgTrackX) / panel::geom::kBgTrackW);
}

void TraneAudioProcessorEditor::pushBackdropState() {
    const TraneAudioProcessor::BackdropState s{backdropPath_,
                                               static_cast<int>(state_.backdrop.where),
                                               state_.backdrop.brightness};
    proc_.setBackdropState(s);
    // **自己写进去的那份也要记成"宿主那份"。** 否则下一帧 pull 会把它当成
    // 外部改动，再走一遍读文件 / 重设状态 —— 白白 repaint，还可能把
    // 刚拖到的明暗度弹回去。
    hostPath_ = s.path;
    hostWhere_ = s.where;
    hostBright_ = s.brightness;
}

// 宿主可能在我们打开之后才把状态塞回来（"撤销 / 重做"、加载预设、恢复工程），
// 所以每帧对一下。只比三个值，比不过就按宿主那份走 —— 这时**必须**重新读文件，
// 因为路径变了图就得跟着换。
void TraneAudioProcessorEditor::pullBackdropState() {
    const auto host = proc_.getBackdropState();
    // 宿主那份没动过就什么都不做（自己写进去的值再读回来当然一样）。
    if (host.path == hostPath_ && host.where == hostWhere_
        && std::abs(host.brightness - hostBright_) < 1.0e-4f)
        return;
    hostPath_ = host.path;
    hostWhere_ = host.where;
    hostBright_ = host.brightness;

    if (host.path != backdropPath_) {
        backdropPath_ = host.path;
        if (host.path.isEmpty()) {
            state_.backdrop.image = {};
            state_.backdrop.name = {};
            backdropSource_ = {};
        } else {
            const juce::File f{host.path};
            if (f.existsAsFile()) {
                auto img = juce::ImageFileFormat::loadFrom(f);
                if (img.isValid()) {
                    backdropSource_ = img;
                    state_.backdrop.image = img;
                    state_.backdrop.name = f.getFileName();
                }
            }
            // 文件不在了就保持原样：宁可留着旧图，也不要"打开工程背景没了
            // 还一句都不说"。真没图的时候状态栏那个格子会显示文件名，
            // 用户看得见自己选过什么。
        }
    }
    state_.backdrop.where = static_cast<panel::BgWhere>(
        juce::jlimit(0, 2, host.where));
    state_.backdrop.brightness = juce::jlimit(panel::geom::kBgBrightMin,
                                              panel::geom::kBgBrightMax, host.brightness);
    repaint();
}

// ============================================================================
// 键盘
// ============================================================================
// 焦点只走**当前真的显示出来的**参数行：MODULE 模式下没显示的行不该被走到，
// 否则按 Tab 会"卡住" —— 焦点落在一个画不出来的行上，看不见任何反馈。
void TraneAudioProcessorEditor::moveFocus(int delta) {
    const auto L = panel::buildInspector(state_);

    int shown[panel::kMaxRows];
    int n = 0;
    for (int i = 0; i < L.rowCount && n < panel::kMaxRows; ++i)
        if (L.row[i].control >= 0) shown[n++] = L.row[i].control;
    if (n == 0) return;

    int at = -1;
    for (int i = 0; i < n; ++i)
        if (shown[i] == state_.focus) { at = i; break; }

    // 当前没有焦点：往前进就从第一行开始，往回退就从最后一行开始。
    const int next = at < 0 ? (delta > 0 ? 0 : n - 1)
                            : ((at + delta) % n + n) % n;
    state_.focus = shown[next];
    repaint();
}

bool TraneAudioProcessorEditor::keyPressed(const juce::KeyPress& key) {
    const int code = key.getKeyCode();
    const bool shift = key.getModifiers().isShiftDown();

    if (code == juce::KeyPress::tabKey)   { moveFocus(shift ? -1 : 1); return true; }
    if (code == juce::KeyPress::upKey)    { moveFocus(-1); return true; }
    if (code == juce::KeyPress::downKey)  { moveFocus(1);  return true; }

    if (code == juce::KeyPress::leftKey || code == juce::KeyPress::rightKey) {
        const int delta = (code == juce::KeyPress::rightKey) ? 1 : -1;
        if (state_.focus < 0) { moveFocus(delta); return true; }
        if (panel::controlAt(state_.focus).fmt == panel::Fmt::Choice)
            nudgeChoice(state_.focus, delta);
        else
            setControl(state_.focus, state_.value[state_.focus] + static_cast<float>(delta) * kKeyStep);
        repaint();
        return true;
    }

    // 回车 = 切换焦点所在模块的开关。**空格故意不绑** —— Ableton 里空格是
    // 播放 / 停止，插件抢走它每次都会让用户骂人。
    if (code == juce::KeyPress::returnKey) {
        if (state_.focus >= 0) toggleModule(panel::controlNode(state_.focus));
        return true;
    }

    if (code == juce::KeyPress::escapeKey) {
        state_.focus = -1;
        repaint();
        return true;
    }

    return false;
}

// ============================================================================
// 鼠标
// ============================================================================
void TraneAudioProcessorEditor::mouseDown(const juce::MouseEvent& e) {
    const auto p = logical(e);
    const auto hit = panel::hitTest(p, state_);
    const auto m = hit.mark();

    pressControl_ = hit.control;
    // v0.33：模块标题行**就是**那个模块的开关（`hitTest` 已经这么返回），
    // 于是"点标题行"和"点开关"是同一件事，不再需要一条单独的路径。
    //
    // 但开关必须从参数行里挑出来：参数是**数字**（拖 = 擦洗），开关是**布尔**
    // （只有单击，没有"拖"）。判据 `controlSlot < 0` 是控制表里对"开关"的
    // 既有定义（见 TranePanel.h），不是这里新加的规矩。
    pressSwitch_ = (pressControl_ >= 0 && panel::controlSlot(pressControl_) < 0)
                       ? pressControl_ : -1;
    if (pressSwitch_ >= 0) pressControl_ = -1;   // 开关不进拖拽通道

    // **原样存下这个 Hit**，不做任何翻译 —— 组号与格号的解读全在
    // panel::resolveBarClick 里，只有一处。存成一个整数会让「MODULE」和
    // 「列数第 2 格」撞成同一个数，那正是 MODULE 点不开的根因。
    pressHit_ = hit;
    pressBgSlot_ = (hit.kind == panel::Hit::Kind::BgSlot);
    dragBright_ = (hit.kind == panel::Hit::Kind::BgBright);
    dragControl_ = -1;
    pressY_ = p.y;
    pressMoved_ = false;
    pressValue_ = pressControl_ >= 0 ? state_.value[pressControl_] : 0.0f;

    state_.press = m;
    if (pressControl_ >= 0) state_.focus = pressControl_;   // 点哪儿焦点在哪儿
    else if (pressSwitch_ >= 0) state_.focus = pressSwitch_;
    repaint();

    // 明暗度轨道是**绝对位置**映射（点哪儿就是哪儿），所以按下就生效 ——
    // 单击能直接跳到某一档，不用先按住再拖。同一点两次结果相同，
    // 所以双击依然满足"做两遍等于没做"。
    if (dragBright_) setBackdropBrightness(brightnessAt(p.x));

    // 手势在**按下**时开、**松手**时关。中间拖了多少次宿主都算在同一次
    // 自动化编辑里 —— 这是 JUCE 里 Slider 的标准做法。
    // 注意只对参数行开手势：开关是离散的，它自己成对开关手势。
    if (pressControl_ >= 0)
        if (auto* param = paramOf(pressControl_))
            param->beginChangeGesture();
}

void TraneAudioProcessorEditor::mouseDrag(const juce::MouseEvent& e) {
    const auto p = logical(e);

    // v0.33：拖分割线那一段删了（分割线没了）。留下的顺序仍然有意义 ——
    // 顶栏的横向拖动**必须**排在参数拖拽之前，否则明暗度轨道会被当成参数擦洗。
    // 这个"先横向、再纵向"的分派顺序是 v0.31 定的，跟分割线在不在无关。

    // ---- 拖明暗度轨道 ----
    if (dragBright_) {
        setBackdropBrightness(brightnessAt(p.x));
        pressMoved_ = true;
        return;
    }

    if (pressControl_ < 0) return;   // 模块开关 / 「选择图片」/ 空白处拖拽不做事

    const float dy = pressY_ - p.y;  // 往上拖 = 变大
    if (std::abs(dy) >= kDragThreshold) pressMoved_ = true;
    if (!pressMoved_) return;

    if (dragControl_ < 0) dragControl_ = pressControl_;

    float span = kDragSpan;
    if (e.mods.isShiftDown()) span *= kDragFine;
    if (e.mods.isCommandDown() || e.mods.isCtrlDown()) span *= kDragFinest;

    // 从**按下的那个值**算绝对偏移，不是从上一帧累加 —— 累加会在快速拖动时丢事件。
    setControl(pressControl_, pressValue_ + dy / span);

    state_.focus = pressControl_;
    repaint();
}

void TraneAudioProcessorEditor::mouseUp(const juce::MouseEvent& e) {
    const auto p = logical(e);
    const bool wasDrag = dragControl_ >= 0;

    // 先关拖拽的手势，再做离散动作 —— nudgeChoice / resetToDefault / toggleModule
    // 自己会开一对 begin/end，不能和拖拽的手势叠在一起。
    if (pressControl_ >= 0)
        if (auto* param = paramOf(pressControl_))
            param->endChangeGesture();

    // **只有「选择图片」需要挡双击** —— 连开两次系统对话框显然不是"做两遍等于没做"。
    //
    // 其余动作一律**不挡**。JUCE 的 getNumberOfClicks() 是累加的：连点几下就是
    // 2、3、4…，拿它当闸会把"高频点击"整片吃掉 —— 那正是"开关点不动 / MODULE 打不开"
    // 的根因。开关的"做两遍等于没做"由**动作本身**保证（toggle 两次 = 回到原值），
    // 不需要外挂一层计数闸。
    const bool isSecondClick = e.getNumberOfClicks() >= 2;

    if (panel::barGroupOf(pressHit_) != panel::BarGroup::None) {
        // 判定交给面板层 —— 这样 `panel_probe --click` 能把同一条链跑一遍。
        const auto v = panel::resolveBarClick(pressHit_, pressMoved_, p, state_);
        // v0.33：`BarGroup::Mode` / `Count` 两个分支删了（那两组分段控件没了）。
        // 判定本身**一个字没改** —— 这正是把"组号 + 格号 + 有没有拖动"塞进
        // panel 层的好处：删掉两组控件只需要删分支，不需要动判据。
        if (v.fired && v.group == panel::BarGroup::BgWhere)
            setBackdropWhere(static_cast<panel::BgWhere>(v.option));
    } else if (!wasDrag && !pressMoved_) {
        if (pressControl_ >= 0) {
            // 档位参数：单击切下一档。
            // 连续参数单击**不改值** —— 改值一律靠拖，免得手一抖就把参数碰歪。
            if (panel::controlAt(pressControl_).fmt == panel::Fmt::Choice)
                nudgeChoice(pressControl_, +1);
        } else if (pressSwitch_ >= 0) {
            // 模块标题行 = 那个模块的开关。v0.33 之前这一步只发生在**树上的圆**里，
            // 树删了之后标题行是唯一的落点 —— 所以这不是新加的功能，
            // 是**把原来的落点搬到了新的地方**，不搬的话七个开关就点不着了。
            toggleModule(panel::controlNode(pressSwitch_));
        } else if (pressBgSlot_ && !isSecondClick) {
            pickBackdrop();
        }
    }

    pressControl_ = -1;
    pressSwitch_ = -1;
    pressHit_ = {};
    pressBgSlot_ = false;
    dragBright_ = false;
    dragControl_ = -1;
    pressMoved_ = false;
    state_.press = {};

    // 松手后指针底下的东西可能已经变了（落位切了、参数被 nudge 了）
    setHover(p);
    repaint();
}

void TraneAudioProcessorEditor::mouseMove(const juce::MouseEvent& e) {    setHover(logical(e));
}

void TraneAudioProcessorEditor::mouseExit(const juce::MouseEvent&) {
    if (state_.hoverFade.cur.any()) {
        // **不是直接清空** —— 那会让高亮"啪"一下消失。retarget 到一个空标记，
        // 于是上一个标记进入退场（160ms ease-out），和进场用同一条曲线。
        state_.hoverFade.retarget({});
        repaint();
    }
    setMouseCursor(juce::MouseCursor::NormalCursor);
}

void TraneAudioProcessorEditor::mouseWheelMove(const juce::MouseEvent& e,
                                               const juce::MouseWheelDetails& w) {    const auto hit = panel::hitTest(logical(e), state_);
    // v0.33：模块标题行的 `control` 现在指向那个模块的开关，所以这里必须把
    // 开关排掉 —— 否则"在标题上滚一下"会改 bypass，而这是滚轮在 v0.32 里
    // **没有**的行为（那时标题行不返回 control）。滚轮只服务参数行。
    if (hit.control < 0 || panel::controlSlot(hit.control) < 0) return;

    const float dir = w.deltaY > 0.0f ? 1.0f : -1.0f;

    if (panel::controlAt(hit.control).fmt == panel::Fmt::Choice) {
        nudgeChoice(hit.control, dir > 0.0f ? +1 : -1);
    } else {
        auto* p = paramOf(hit.control);
        if (p == nullptr) return;
        const float step = e.mods.isShiftDown() ? kWheelStepFine : kWheelStep;
        p->beginChangeGesture();
        setControl(hit.control, state_.value[hit.control] + dir * step);
        p->endChangeGesture();
    }

    state_.focus = hit.control;
    repaint();
}

void TraneAudioProcessorEditor::mouseDoubleClick(const juce::MouseEvent& e) {
    const auto hit = panel::hitTest(logical(e), state_);
    if (hit.control < 0) return;

    // 模块标题行（= 那个模块的开关）：双击 = 把该模块的**连续参数**全部复位。
    //
    // 这个能力在 v0.33 之前只挂在**树上的圆**里（`hit.onCore`）。树删了，
    // 它需要一个新家 —— 标题行就是那个家。**不是删掉功能，是搬家。**
    //
    // 开关参数（BoolParam）故意不复位 —— 用户高频点击时，两次单击已经 toggle
    // 了开关（关→开→关），如果 double-click 再把开关复位到默认（false），
    // 净效果就是"开关打不开"，造成明显的可用性故障。
    if (panel::controlSlot(hit.control) < 0) {
        const int node = panel::controlNode(hit.control);
        for (int i = 0; i < panel::controlCount(); ++i)
            if (panel::controlNode(i) == node)
                if (panel::controlAt(i).fmt != panel::Fmt::None)
                    resetToDefault(i);
        return;
    }

    resetToDefault(hit.control);
}

}  // namespace trane
