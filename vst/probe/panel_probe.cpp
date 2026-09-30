// panel_probe.cpp — 把 Träne 的面板离线渲染成 PNG，并把几何/状态自述打到标准输出。
//
// 为什么要有这个东西：
//
//   v0.10 之前，"界面对不对"只能靠人肉看截图。而这个项目在 DSP 那边立的规矩是
//   **先量，再改** —— 界面凭什么例外。面板层（TranePanel）刻意不依赖
//   juce_audio_processors，就是为了能在这个几十行的控制台程序里直接渲染出来：
//
//     · 出 PNG，供人看，也供 tools/check_panel_render.py 逐像素量；
//     · --dump-geometry 把面板尺寸、每个模块的标题行数吐出来，
//       由 Python 用独立实现复算一遍再比对 —— 防止"图是画好看的、代码是另一回事"；
//     · --dump-layout 吐**各栏的排版数字**（列宽 / 行距 / 字号 / 名-轨-值三段宽）。
//       这是"排版大致不变"这句话唯一的证据来源 —— 没有它，v0.33 的 3 栏→4 栏
//       就只能靠肉眼看"好像差不多"，而肉眼看不出 11pt 变成 10pt。
//     · --state / --hover / --press / --focus 组合出**任意一种面板状态**，
//       于是"悬停那一行长什么样""指针在数值上那一行长什么样"也能被量到，
//       而不是只能量出厂状态；
//     · --frames N 量一遍每帧耗时，证明 30Hz 的呼吸动画不会把 CPU 吃掉。
//
// 渲染用的是**和插件完全相同的绘制代码**，不是另写一套 SVG 预览。
//
// 用法:
//   panel_probe --out out.png [--scale 2] [--state default|all|demo]
//               [--hover <spec>] [--hover-t <秒>] [--press <spec>] [--focus <paramId>]
//               [--bg <png>] [--bg-where off|full] [--bg-bright 1.0]
//               [--cold-reps 5]
//               [--time 0.9] [--dump-geometry] [--dump-layout] [--dump-metrics]
//
//   <spec> 的写法（v0.33 起只剩这些 —— 分割线 / 树上的圆 / 模式格 / 列数格
//   都随树一起删了，写旧的写法会**当场报错**，不会静默当成 none）：
//       none              什么都不指向（默认）
//       ctl:<paramId>     指向某个参数行（如 ctl:grain_spray）
//                         —— 也用于**模块标题行**：标题行就是那个模块的开关，
//                            所以写 `ctl:<mod>_on`（如 ctl:grain_on）即可
//       tab:<n>           指向背景落位组的第 n 格（0 = 关 / 1 = 全屏）
//       bgslot            指向顶栏的「选择图片」格
//       bgbright          指向顶栏的明暗度轨道
#include "../plugin/TranePanel.h"

#include <iostream>

namespace {

using namespace trane;

struct Options {
    juce::String out;
    float scale = 2.0f;
    juce::String state = "default";
    // v0.33 删了 `mode` / `count` / `divider` 三个开关 —— 版面只有一种，
    // 参数区的边界是编译期常量，没有任何运行时可调的东西了。
    // 删掉它们不是"清理"，是**让旧命令行当场失败**：`--divider 392` 现在会报
    // "未知参数"，而不是被静默忽略、渲出一张和预期不一样的图。
    juce::String hover = "none";
    juce::String press = "none";
    // hover 淡入的相位（秒）。-1 = 不给，表示"动画早就结束了"（= 旧版 `--hover`
    // 那个全亮的样子，老命令行因此不受 v0.33 的淡入影响）。
    // ≥0 = 指针移到它身上之后过了这么多秒，探针按 kHoverFade 换算成线性进度。
    float hoverT = -1.0f;
    float time = 0.0f;
    int frames = 0;
    bool dumpGeometry = false;
    bool dumpLayout = false;         // 打印各栏排版数字（列宽/行距/字号）
    bool dumpText = false;           // 打印文字对比度登记表（不透明度/底色/墨层）
    bool dumpMetrics = false;        // 打印文字度量（每字符宽度 / 每个控件的最长数值串）
    juce::String hit;                 // 命中测试自述的规格串（空 = 不做）
    juce::String click;               // 按下的规格串（空 = 不做）
    juce::String release;             // 松手的规格串（空 = 与按下同一点）
    bool clickMoved = false;          // 按下与松手之间越过拖拽阈值
    juce::String focusId;
    juce::StringArray sets;          // --set <paramId>=<真值>，可多次
    juce::String bg;                 // 背景图（用户上传的那张）
    juce::String bgWhere = "full";   // off | full
    float bgBright = 1.0f;
    int coldReps = 5;                // 冷重烤量几次（取最小）；1 = 只量一次
};

void usage() {
    std::cout << "用法: panel_probe --out <png> [--scale 2] [--state default|all|demo]\n"
                 "       [--hover none|ctl:<id>|tab:<n>|bgslot|bgbright]\n"
                 "       [--hover-t <秒>] hover 淡入的相位：指针移到它身上之后\n"
                 "                        过了这么多秒。不给 = 动画已完成（全亮，\n"
                 "                        和 v0.32 的 --hover 输出一致）。\n"
                 "                        kHoverFade = 0.16 s，所以 0.08 = 半程。\n"
                 "       [--press <同上>] [--focus <paramId>] [--time 0.9]\n"
                 "       [--set <paramId>=<真值>]   改一个参数的值（可多次）——\n"
                 "                       量参数条的指针到底动没动，就靠它\n"
                 "       [--bg <png>] [--bg-where off|full] [--bg-bright 1.0]\n"
                 "       [--cold-reps 5]  冷重烤 / 热重合成各量几次，报**最小**值。\n"
                 "                        默认 5；1 = 只量一次（看噪声用）。\n"
                 "       [--dump-geometry] [--dump-layout] [--dump-metrics]\n"
                 "       [--dump-text]     文字对比度登记表：每一处文字用的\n"
                 "                         (不透明度, 基底层, 墨层强度)。由\n"
                 "                         tests/test_ui_design.py 复算 WCAG。\n"
                 "       [--dump-layout]  各栏排版数字（列宽/行距/字号/三段宽）——\n"
                 "                        '排版大致不变'的证据来源\n"
                 "       [--dump-metrics] 文字度量：数值列里每个字符的实测宽度 +\n"
                 "                        每个控件最长数值串的实测宽度。用来复算\n"
                 "                        '数值列宽够不够'（那个按字符数算的模型）\n"
                 "       [--hit <spec>]   命中测试自述（spec 同 --hover）\n"
                 "       [--click <spec>] 点击判定自述：按下 --click 指定的点，\n"
                 "                        松手在 --release 指定的点（省略则同一点），\n"
                 "                        中间是否拖过由 --click-moved 决定。\n"
                 "                        吐出 fired / group / option 三行。\n"
                 "       [--release <spec>] [--click-moved]\n"
                 "\n"
                 "   --bg 喂的就是用户上传背景那条路径：面板只收一个 juce::Image\n"
                 "   （读文件的是编辑器，不是面板）。所以这里渲出来的背景\n"
                 "   **和插件里画的是同一段代码**，不是事后合成 PNG。\n";
}

bool parse(int argc, char** argv, Options& o) {
    for (int i = 1; i < argc; ++i) {
        // **必须走 fromUTF8**：`juce::String{argv[i]}` 那个构造函数按 **Latin-1**
        // 解释 `char*`（逐字节取低 8 位当码点），中文路径会被解成
        // `U+00E8 U+0083 U+008C …`，于是 `existsAsFile()` 永远为假 ——
        // 而且报错信息里还会打出"看起来差不多"的乱码，很难看出是编码问题。
        // 实测：`vst背景.png` 经 `String{argv[i]}` 后 toRawUTF8() 变成
        // `vst c3a8 c283 c28c …`（双重编码）。
        const juce::String a{juce::String::fromUTF8(argv[i])};
        const auto next = [&]() -> juce::String {
            return (i + 1 < argc) ? juce::String::fromUTF8(argv[++i]) : juce::String{};
        };
        if (a == "--out") o.out = next();
        else if (a == "--scale") o.scale = next().getFloatValue();
        else if (a == "--state") o.state = next();
        // v0.33：`--mode` / `--count` / `--divider` 已删。落到下面的
        // "未知参数" 分支 —— 老命令行会**响**，不会静默渲出一张别的图。
        else if (a == "--hover") o.hover = next();
        else if (a == "--hover-t") o.hoverT = next().getFloatValue();
        else if (a == "--press") o.press = next();
        else if (a == "--time") o.time = next().getFloatValue();
        else if (a == "--focus") o.focusId = next();
        else if (a == "--set") o.sets.add(next());
        else if (a == "--frames") o.frames = next().getIntValue();
        else if (a == "--bg") o.bg = next();
        else if (a == "--bg-where") o.bgWhere = next();
        else if (a == "--bg-bright") o.bgBright = next().getFloatValue();
        else if (a == "--cold-reps") o.coldReps = next().getIntValue();
        else if (a == "--hit") o.hit = next();
        else if (a == "--click") o.click = next();
        else if (a == "--release") o.release = next();
        else if (a == "--click-moved") o.clickMoved = true;
        else if (a == "--dump-geometry") o.dumpGeometry = true;
        else if (a == "--dump-layout") o.dumpLayout = true;
        else if (a == "--dump-text") o.dumpText = true;
        else if (a == "--dump-metrics") o.dumpMetrics = true;
        else if (a == "-h" || a == "--help") { usage(); return false; }
        else { std::cerr << "未知参数: " << a << "\n"; return false; }
    }
    return true;
}

void setReal(panel::PanelState& st, const char* id, float real) {
    const int i = panel::indexOfId(id);
    if (i >= 0) st.value[i] = panel::toNormalised(i, real);
}

// 把 --hover / --press 的写法翻成面板认识的 Mark。
// 认不出来就**直接报错退出** —— 悄悄当成 none 的话，一张"看起来对"的图会
// 让人以为交互状态就是这样，而实际上什么都没画。
bool parseMark(const juce::String& spec, panel::PanelState::Mark& m) {
    m = {};
    if (spec.isEmpty() || spec == "none") return true;

    const auto parts = juce::StringArray::fromTokens(spec, ":", "");
    const auto head = parts[0];

    // 旧写法给一句明确的解释，而不是笼统的"看不懂" —— `divider` 与 `node:`
    // 在 v0.33 之前遍布测试与设计稿工具，报错要能一眼看出"是它没了，
    // 不是我打错了字"。
    if (head == "divider" || head == "node") {
        std::cerr << "v0.33 起没有这个标记了（世界树与分割线已删）: " << spec << "\n";
        return false;
    }

    if (head == "bgslot")   { m.bgSlot   = true; return true; }
    if (head == "bgbright") { m.bgBright = true; return true; }

    if (head == "ctl" && parts.size() == 2) {
        m.control = panel::indexOfId(parts[1]);
        if (m.control < 0) { std::cerr << "没有这个参数: " << parts[1] << "\n"; return false; }
        return true;
    }
    if (head == "tab" && parts.size() == 2) {
        // v0.33：分段控件只剩背景落位那一组，所以**组号恒为 0**，
        // 写法从 `tab:<组>:<格>` 收紧成 `tab:<格>`。
        // `tab:2:1` 这种三段写法会落到下面报错 —— 老写法要响，不能静默取头一段。
        m.tab = 0;
        m.option = parts[1].getIntValue();
        if (m.option < 0 || m.option >= panel::geom::kBgSegN) {
            std::cerr << "落位组只有 " << panel::geom::kBgSegN
                      << " 格（0=关 1=全屏），收到 " << m.option << "\n";
            return false;
        }
        return true;
    }
    std::cerr << "看不懂的标记: " << spec << "\n";
    return false;
}

// 三套演示状态。**default 才是真的出厂状态** —— 七个开关全 false，
// 所以只有 SPACE（space_mix 默认 0.55）和 OUT（恒亮）亮着。
// 另外两套是为了看清"两档信号高亮"的差别：
//   all  —— 十个模块全亮 → 9 条信号边全在"通过"档
//   demo —— 只亮链的前两级（freeze / grain）+ RUIN，通过档只有 2 条
panel::PanelState makeState(const juce::String& which, float time) {
    panel::PanelState st;
    for (int i = 0; i < panel::controlCount(); ++i) st.value[i] = panel::defaultNormalised(i);
    // 无遥测 = 1.0（"在响"）；有真实遥测的模块在编辑器里再覆盖
    for (int n = 0; n < panel::kMaxNodes; ++n) st.moduleActivity[n] = 1.0f;
    st.time = time;

    if (which == "all") {
        for (int i = 0; i < panel::controlCount(); ++i)
            if (panel::controlAt(i).label[0] == '\0') st.value[i] = 1.0f;   // 七个开关全开
        setReal(st, "ruin_mode", 0.62f);
        setReal(st, "grain_size", 260.0f);
        setReal(st, "grain_density", 34.0f);
        setReal(st, "grain_spray", 0.62f);
        setReal(st, "grain_position", 0.78f);
        setReal(st, "grain_rate", 1.85f);
        setReal(st, "grain_spread", 0.44f);
        setReal(st, "grain_reverse", 0.35f);
        setReal(st, "loop_ms", 900.0f);
        setReal(st, "seam_ms", 6.0f);
        setReal(st, "stutter_size", 140.0f);
        setReal(st, "stutter_rate", 11.0f);
        setReal(st, "stutter_jump", 0.58f);
        setReal(st, "comb_tune", 780.0f);
        setReal(st, "comb_feedback", 0.72f);
        setReal(st, "tape_speed", 0.74f);
        setReal(st, "tape_wobble", 0.42f);
        setReal(st, "sweep_rate", 3.4f);
        setReal(st, "sweep_depth", 0.62f);
        setReal(st, "sweep_center", 3400.0f);
        setReal(st, "sweep_reso", 0.55f);
        setReal(st, "sweep_mode", 2.0f);          // HP
        setReal(st, "delay_time", 620.0f);
        setReal(st, "delay_feedback", 0.62f);
        setReal(st, "delay_pingpong", 0.85f);
        setReal(st, "delay_mix", 0.48f);
        setReal(st, "space_size", 0.9f);
        setReal(st, "space_tail", 0.95f);
        setReal(st, "output", 3.5f);
    } else if (which == "demo") {
        setReal(st, "freeze", 1.0f);
        setReal(st, "grain_on", 1.0f);
        setReal(st, "grain_spray", 0.34f);
        setReal(st, "grain_position", 0.72f);
        setReal(st, "ruin_mode", 0.45f);
    }
    return st;
}

// 把 Mark 反着写回 `--hover` / `--press` 的写法。
//
// 为什么要自述：检查器要能证明"**我请求的交互态真的被收到了**"。
// 少了这一条，一个写错的 `--hover` 参数会让交互态渲染退化成普通态，
// 于是"交互态没有强调色"这条断言在**什么都没交互**的图上轻松通过 —— 空转。
juce::String markSpec(const panel::PanelState::Mark& m) {
    if (m.bgSlot)   return "bgslot";
    if (m.bgBright) return "bgbright";
    if (m.control >= 0 && m.control < panel::kNumControls)
        return juce::String{"ctl:"} + panel::kControls[m.control].id;
    if (m.tab >= 0)
        return "tab:" + juce::String(m.option);
    return "none";
}

const char* bgWhereName(panel::BgWhere w) {
    // v0.33 只剩两档：落位区就是参数区，不存在"树区 / 参数区"的区分了。
    return w == panel::BgWhere::Full ? "full" : "off";
}

// 状态自述 —— 机器可读。check_panel_render.py 拿它当期望值，
// 不在那边再抄一份"哪个模块该亮"（抄一份就多一个会分叉的地方）。
void printState(const panel::PanelState& st) {
    juce::String lit;
    for (int i = 0; i < panel::kMaxNodes; ++i)
        if (panel::moduleIsOn(i, st)) lit << panel::nodeModule(i) << " ";

    const auto L = panel::buildInspector(st);
    // v0.33 删了三行自述：`mode`（只有一种版面了）、`count`（列数固定 4）、
    // `divider`（分割线删了，参数区左缘是编译期常量 kPaneX0）。
    // `hot`（信号线条数）也删了 —— 树没了，就没有线。
    // **删自述行和删功能是一件事**：留着 `mode ALL` 这种恒定输出，
    // 会让检查器以为"我验证了版面切换"，而实际上没有版面可切。
    std::cout << "lit " << panel::litModuleCount(st) << " " << lit.trim() << "\n";
    std::cout << "cols " << L.columnCount << "\n";
    std::cout << "shown " << L.shownControls << "\n";
    std::cout << "hover " << markSpec(st.hoverFade.cur) << "\n";
    // hover 淡入的相位。**两段都报**：
    //   第 1 段 = 线性进度 curT（0..1）—— 时间
    //   第 2 段 = 过完 easeOutCubic 之后该有多亮（0..1）—— 亮度
    // 只报 curT 的话，"缓动到底有没有施加"就只能靠像素反推；只报亮度的话，
    // "时间是不是真的线性推进"又测不到。两个都摆出来，两条都能被断言。
    std::cout << "hover_t " << juce::String(st.hoverFade.curT, 4)
              << " " << juce::String(st.hoverFade.of(st.hoverFade.cur), 4) << "\n";
    std::cout << "press " << markSpec(st.press) << "\n";

    // 背景规格自述。**这一行是检查器的锚点** —— 没有它，"背景出现在参数区"
    // 那条断言就只能靠猜图上的亮块在哪儿，而"猜"不是验证。
    //   第 1 段 on/off = backdrop.active()（有图 **且** 落位不是 Off）
    //   第 2 段 落位 off/tree/params
    //   第 3 段 明暗度（两位小数）
    //   第 4 段 原图尺寸，没有图就是 "-"
    std::cout << "bg " << (st.backdrop.active() ? "on" : "off")
              << " " << bgWhereName(st.backdrop.where)
              << " " << juce::String(st.backdrop.brightness, 2)
              << " " << (st.backdrop.image.isValid()
                             ? juce::String(st.backdrop.image.getWidth()) + "x"
                                   + juce::String(st.backdrop.image.getHeight())
                             : juce::String{"-"})
              << "\n";
}

// ---------------------------------------------------------------------------
// 背景图（用户上传的那张）
// ---------------------------------------------------------------------------
// **面板层不读文件** —— 这是"离线渲染的输入 = PanelState"这条底线。
// 读文件是编辑器（或这里的探针）的事，读好之后把 `juce::Image` 塞进
// `st.backdrop`。所以这段代码和 `PluginEditor` 里那段是**同一件事**，
// 落位、压暗、羽化全在面板里算，两边不可能分叉。
bool loadBackdrop(const Options& o, panel::PanelState& st) {
    if (o.bg.isEmpty()) return true;

    const auto f = juce::File::getCurrentWorkingDirectory().getChildFile(o.bg);
    if (!f.existsAsFile()) {
        std::cerr << "找不到背景图: " << f.getFullPathName() << "\n";
        return false;
    }
    st.backdrop.image = juce::ImageFileFormat::loadFrom(f);
    if (!st.backdrop.image.isValid()) {
        std::cerr << "背景图解不出图像: " << f.getFullPathName() << "\n";
        return false;
    }
    st.backdrop.name = f.getFileName();
    st.backdrop.brightness = o.bgBright;

    // v0.33：值域从 `off|tree|params` 收成 `off|full` —— 落位区就是参数区本身。
    if (o.bgWhere == "off")       st.backdrop.where = panel::BgWhere::Off;
    else if (o.bgWhere == "full") st.backdrop.where = panel::BgWhere::Full;
    else { std::cerr << "--bg-where 只能是 off|full，收到 " << o.bgWhere << "\n"; return false; }

    // 不自述 —— 自述统一在 printState 里出（一处出、一处解析，不会分叉）。
    return true;
}

}  // namespace

int main(int argc, char** argv) {
    Options o;
    if (!parse(argc, argv, o)) return 2;

    juce::ScopedJuceInitialiser_GUI juceInit;

    if (o.dumpGeometry) {
        std::cout << panel::geometryDump();
        return 0;
    }

    if (o.out.isEmpty() && o.hit.isEmpty() && o.click.isEmpty()
        && !o.dumpLayout && !o.dumpText && !o.dumpMetrics) {
        usage();
        return 2;
    }

    auto st = makeState(o.state, o.time);
    // v0.33：`--mode` / `--count` / `--divider` 的应用代码删了。
    // 不是"这段没用了"，是**这段能改的东西不存在了** —— 版面只有一种，
    // 分栏是常量表，参数区边界是常量。
    if (o.focusId.isNotEmpty()) st.focus = panel::indexOfId(o.focusId);

    // 排版自述：和 --hit / --click 一样"只要结果、不要图"。
    if (o.dumpLayout) {
        std::cout << panel::layoutDump(st);
        return 0;
    }

    // 文字度量自述：数值列宽那个"按字符数"的模型能不能撑住。
    // 不依赖状态（量的是字体与格式串），但放在这里省一个早退分支。
    if (o.dumpMetrics) {
        std::cout << panel::metricsDump();
        return 0;
    }

    // --set <paramId>=<真值>：按**真值**设（不是归一化值）—— 这样"把 spray 设成
    // 0.5 s"读起来就是它字面的意思，不用先手算一遍归一化。
    for (const auto& kv : o.sets) {
        const int eq = kv.indexOfChar('=');
        if (eq <= 0) { std::cerr << "--set 要写成 <paramId>=<真值>，收到 " << kv << "\n"; return 2; }
        const auto id = kv.substring(0, eq);
        if (panel::indexOfId(id) < 0) { std::cerr << "--set 认不出参数 " << id << "\n"; return 2; }
        setReal(st, id.toRawUTF8(), kv.substring(eq + 1).getFloatValue());
    }
    if (!parseMark(o.press, st.press)) return 2;

    // ---- hover 淡入的相位（v0.33）----
    //
    // 先 retarget，再按 --hover-t 推进时间。**不给 --hover-t 就推满一个
    // kHoverFade** —— 也就是"动画已经结束"，和 v0.32 里 `st.hover = mark`
    // 那个全亮的样子逐像素相同。老命令行因此不会被淡入改掉输出。
    //
    // 给了秒数就交给 `step()` 换算（`curT += dt / kHoverFade`）。
    // **换算住在面板层，探针不自己算** —— 否则这里写一个 curT 塞进去，
    // 测的就只是"我塞进去的那个数"，`kHoverFade` 到底是不是 0.16 秒没人验。
    {
        panel::PanelState::Mark hv{};
        if (!parseMark(o.hover, hv)) return 2;
        st.hoverFade.retarget(hv);
        st.hoverFade.step(o.hoverT >= 0.0f ? o.hoverT : panel::kHoverFade);
    }

    // 背景图要在 printState 之前读进来 —— 这样自述里那些跟背景有关的
    // 字段（落位、明暗度）才反映的是**这一帧真正画出来的东西**。
    // 读文件是探针的职责（面板层不碰 I/O，有测试盯着）。
    if (!loadBackdrop(o, st)) return 1;

    // 文字对比度登记表：**只要结果、不要图**，而且必须排在 printState 之前 ——
    // 这样输出里只有 `text …` 那几行，测试不用过滤（过滤写漏一行就会
    // 把"多出来的一对"当成不存在）。
    //
    // 位置也很讲究：必须在 loadBackdrop **之后**（「选择图片」格的字色取决于
    // 有没有图），在 printState **之前**。
    if (o.dumpText) {
        std::cout << panel::textDump(st);
        return 0;
    }

    printState(st);

    // 命中测试自述：只要 --hit，不需要出图 —— 这条链路要能在测试里
    // 被反复调用，不该逼着每次都渲一张 2880×1440 的 PNG。
    if (o.hit.isNotEmpty()) {
        std::cout << panel::hitDump(o.hit, st);
        return 0;
    }

    // 点击判定自述：同样是"只要结果、不要图"。这是「MODULE 标签点不开」
    // 那条链路的唯一入口 —— 判定住在面板层，编辑器与探针跑的是同一份代码。
    if (o.click.isNotEmpty()) {
        std::cout << panel::clickDump(o.click, o.release, o.clickMoved, st);
        return 0;
    }

    panel::PanelCache cache;
    cache.ensure(o.scale);

    // backdrop 的重烤只在尺寸 / 背景规格变化时发生，所以单独量一次。
    //
    // **量两次，因为这两条路的代价差一个量级：**
    //   冷 —— 含源图的高质量缩放 + 羽化（换图 / 换落位 / 改窗口尺寸才走）
    //   热 —— 只改明暗度（拖滑块每帧都走这条）
    // 只量冷的话，"拖明暗度卡不卡"这个问题根本量不到 —— 而它才是每帧发生的那个。
    //
    // ------------------------------------------------------------------
    // **为什么要量 N 次取最小值**（v0.32.5）
    //
    // 这是整份门禁里**唯一**一条绝对毫秒判据，而绝对毫秒在有别的进程抢 CPU 时
    // 会抖 2–3 倍。同一台机器、同一份二进制、同一条命令，连着跑五次实测：
    //
    //     26.91 / 26.15 / 27.21 / 27.52 / **71.32** ms
    //
    // 第五次连热路径一起膨胀（1.65 → 5.27 ms），是整台机器被抢了，不是代码变慢。
    // 而门禁在 CI / 后台跑，旁边永远有别的东西 —— 于是这条断言**会随机报红**。
    //
    // 取最小值**不是在放宽门槛**，恰恰相反：
    //   · 一次确定的运算，它的成本就是**它能跑到的最快值**，噪声只会让它更慢；
    //   · 真的变慢了（比如缓存失效了），最小值会跟着一起上去，躲不掉；
    //   · 而单次采样会把"机器忙"当成"代码慢"，是最坏的一种判据 ——
    //     既漏报真问题（阈值被噪声逼着往上放），又天天误报。
    // 最大值一并打出来：min 与 max 差得离谱时，日志里一眼能看出是机器在忙。
    //
    // 每次都得是**真冷**：把图在两个内容相同、缓冲不同的 Image 之间来回换，
    // 逼 `bdScaled` 失效。只改明暗度走的是热路径，量不到缩放那一段。
    // ------------------------------------------------------------------
    const int reps = juce::jmax(1, o.coldReps);
    // 每个 rep 都要**真的重烤**，否则量到的是"缓存命中的 0 ms"，判据就废了。
    // 冷路径的失效条件是 bdImage / bdWhere / bdW / bdH 之一变化 ——
    // 注意**明暗度不在其中**（那正是它便宜的原因），所以：
    const juce::Image alt = st.backdrop.image.createCopy();
    const bool haveAlt = alt.isValid();

    auto timed = [&](auto&& setup, const panel::PanelState& base) {
        double lo = 1.0e9, hi = 0.0;
        for (int i = 0; i < reps; ++i) {
            auto s2 = setup(base, i);
            const auto t0 = juce::Time::getHighResolutionTicks();
            cache.update(s2);
            const auto dt = juce::Time::highResolutionTicksToSeconds(
                juce::Time::getHighResolutionTicks() - t0) * 1000.0;
            lo = juce::jmin(lo, dt);
            hi = juce::jmax(hi, dt);
        }
        cache.update(base);          // 收尾：把缓存恢复成这一帧真正要画的那份
        return std::pair<double, double>{lo, hi};
    };

    {
        const auto r = timed([&](const panel::PanelState& b, int i) {
            auto s2 = b;
            if (haveAlt) {
                // 来回换图：内容一模一样，只是缓冲不同。`bdImage` 比的是
                // getPixelData() 指针，于是**每次都能骗过缓存**，缩放 + 羽化
                // 那一整段每次都重做 —— 这才是"冷"的定义。
                if (i % 2 == 1) s2.backdrop.image = alt;
            } else {
                // 没有背景图时 region 为空，缩放那一段本来就不跑（量的是
                // 面板底 + 22 条骨架）。这时用明暗度把 bakedBright 顶开，
                // 保证每次都是真重烤 —— 否则 rep 2 起全是缓存命中，报 0 ms。
                s2.backdrop.brightness = b.backdrop.brightness + 0.001f * (i + 1);
            }
            return s2;
        }, st);
        std::cout << "背景重烤 " << juce::String(r.first, 2)
                  << " ms  (冷：面板底 + 背景图缩放羽化；"
                  << reps << " 次取最小，最大 " << juce::String(r.second, 2) << " ms)\n";
    }
    if (st.backdrop.active()) {
        const auto r = timed([&](const panel::PanelState& b, int i) {
            auto s2 = b;
            // 热路径：只动明暗度（bdScaled 有效 → 不重做缩放）。
            if (i % 2 == 1)
                s2.backdrop.brightness = b.backdrop.brightness >= 2.0f
                                       ? b.backdrop.brightness - 0.5f
                                       : b.backdrop.brightness + 0.5f;
            else
                s2.backdrop.brightness = b.backdrop.brightness + 0.25f;
            return s2;
        }, st);
        std::cout << "明暗度重合成 " << juce::String(r.first, 2)
                  << " ms  (热：只重贴 + 原地乘一个系数，不重做缩放；"
                  << reps << " 次取最小，最大 " << juce::String(r.second, 2) << " ms)\n";
    }

    const int pw = juce::roundToInt(panel::geom::kBaseW * o.scale);
    const int ph = juce::roundToInt(panel::geom::kBaseH * o.scale);
    juce::Image img{juce::Image::ARGB, pw, ph, true};

    const auto render = [&](float t) {
        auto frame = st;
        frame.time = t;
        juce::Graphics g{img};
        g.addTransform(juce::AffineTransform::scale(o.scale));
        panel::paint(g, frame, cache);
    };

    render(st.time);

    if (o.frames > 0) {
        // 按 **30Hz 的真实时间**推进，不是 1ms 一步 —— 后者在 60 帧里
        // 时间只走到 0.059 秒，呼吸相位几乎不动，等于没测到动画。
        const auto t0 = juce::Time::getHighResolutionTicks();
        for (int i = 0; i < o.frames; ++i)
            render(st.time + static_cast<float>(i) / 30.0f);
        const auto dt = juce::Time::highResolutionTicksToSeconds(
            juce::Time::getHighResolutionTicks() - t0);
        const double perFrameMs = 1000.0 * dt / static_cast<double>(o.frames);
        std::cout << "每帧 " << juce::String(perFrameMs, 2) << " ms  ("
                  << pw << "x" << ph << " @ " << juce::String(o.scale, 1) << "x)"
                  << "  30Hz 需要 " << juce::String(perFrameMs * 30.0 / 10.0, 1) << "% 单核\n";
    }

    const auto dest = juce::File::getCurrentWorkingDirectory().getChildFile(o.out);
    dest.getParentDirectory().createDirectory();
    dest.deleteFile();
    juce::FileOutputStream stream{dest};
    if (!stream.openedOk()) {
        std::cerr << "写不了 " << dest.getFullPathName() << "\n";
        return 1;
    }
    juce::PNGImageFormat png;
    if (!png.writeImageToStream(img, stream)) {
        std::cerr << "PNG 编码失败\n";
        return 1;
    }
    stream.flush();

    std::cout << "面板 " << juce::roundToInt(panel::geom::kBaseW) << "x"
              << juce::roundToInt(panel::geom::kBaseH)
              << "  ->  " << dest.getFullPathName() << "  (" << pw << "x" << ph << ")\n";
    return 0;
}
