// TranePanel.h — Träne 的面板（v0.35）：1440×720，**两层**（底图缓存 + 前景），
// 参数按模块链铺满四栏，**每个模块是一张框起来的块**（v0.35）。
//
// v0.33 把 v0.30 那棵世界树（十个质点圆 + 22 条骨架 + 9 条信号线）、分割线、
// MODE / 列数控件**全部删掉**了（小绪 2026-09-29：「包括左边的树也直接删掉吧，
// 我不要模块化的边框了」）。下面那些段落里凡是拿树当例子的，都是**当时**的
// 设计依据 —— 留着是因为它们解释了这套架构为什么长成这样，不是现状描述。
//
// ============================================================================
// 为什么把面板从 PluginEditor 里拆出来
// ============================================================================
//
// v0.10 的界面是 48 个 juce::Slider / TextButton 子控件铺在网格上，靠
// LookAndFeel 画成平面盘。v0.30 不是网格 —— 它是左边一棵自绘的生命之树
// （十个质点圆 + 22 条骨架 + 9 条信号线），右边一列列参数行，中间一条分割线。
// 这套东西塞不进子控件的模型里：
//
//   · 树的三层连线、方向渐变、呼吸脉动是**跨控件的编舞**；
//   · 参数行的三段（名 / 轨道 / 数值）共享一条基线，且列宽由内容反推；
//   · 高亮判据（哪条信号边在通信号）必须和自检用**同一份**代码。
//
// 所以改成**自绘 + 自己命中测试**，一个子控件都不留。好处不只是画得准：
// 这一层不依赖 juce_audio_processors，于是可以用一个几十行的控制台程序
// （panel_probe）把它离线渲染成 PNG —— 界面从此和 DSP 一样可以**机器验证**，
// 而不是靠肉眼。
//
// **别给这个文件加 juce_audio_processors 的 include。** 加了 panel_probe 就编不过，
// 离线可验证性当场作废（tests/test_editor_layout.py 里有断言盯着）。
//
// ============================================================================
// v0.30 是什么（完整规格见 outputs/Trane_UI_v0.30_实现规格书.md）
// ============================================================================
//
//   画布 1440 × 720，宽高比锁死 2:1。
//   配色 = Apple **深色模式语义色**，不是"看着像"：
//       systemBackground #000000 · secondarySystemBackground #1C1C1E
//       systemFill rgba(120,120,128,.36) · tertiarySystemFill rgba(118,118,128,.24)
//       separator rgba(84,84,88,.60) · systemGray2 #636366 · label #EBEBF5
//   Apple 的层级机制只有两套 —— **面的明度** 与 **文字的不透明度** ——
//   没有"边框"这一层。所以面板上一个描边矩形都没有（唯一例外：聚焦环）。
//
//   树的纵轴**就是信号轴**：十个质点的 y 在信号链顺序下单调不减
//   （keter 81.3 → malkuth 638.7），落 7 层。骨架 22 条是生命之树的
//   标准连线（点线，最淡）；信号 9 条是 `TraneEngine.cpp::process()` 的相邻对
//   （实线 + 沿线渐变，上游淡下游亮 —— 不画箭头）。
//
//   信号线分**两档**（小绪 2026-09-29 11:4x：「生命树的所有骨架全部保留，
//   在有信号通过的时候直接高亮表示就可以了」）：
//       静止 —— 静态、不呼吸。它只是"路径在这儿"。
//       通过 —— 抬上去，**并且跟着呼吸脉动**。
//   硬门槛：通过档在**最暗的呼吸相位**下，也要比静止档的**最亮处**还亮
//   （kSigHotLo × kSigBreathMin = 0.663 > kSigRestHi = 0.55）。做不到的话
//   "高亮"就只是"亮了一点点"，等于没做。
//
//   参数检查器两种模式：ALL（全部 10 个模块，3 列 3+3+4）/
//   MODULE×n（4 个候选模块里取前 n 个，n 列）。列与列之间、模块与模块之间
//   **什么都不画** —— 分组只靠留白，组间空档 = 行距 × 2.5。
#pragma once

#include <juce_gui_basics/juce_gui_basics.h>

namespace trane::panel {

// ============================================================================
// UI 版本 —— **面板的版本，不是插件的版本**
// ============================================================================
//
// 两个版本号是两件事，别混：
//   · **插件版本**（`CMakeLists.txt` 的 `project(... VERSION ...)`）—— 进安装包、
//     进 VST3 元数据、用户升级看的是它；
//   · **UI 版本**（这个）—— 面板长什么样的版本。用户可见的界面改动就要 bump 它。
//
// 为什么它必须在**这里**（而不是在某个出图脚本里写死）：出图的文件名里带版本号
// （`Trane_panel_v0.33_all.png`），而这个文件是要给人看的。写死一处就会分叉 ——
// 实测过：面板已经做到 v0.33，`check_panel_render.py` 里 `--version` 的默认值
// 还停在 `0.32`，于是 `outputs/` 里躺着一批**名字说 v0.32、画的是 v0.33** 的图。
// 它不报错，只是骗人 —— 而"不报错的错"正是这套自检要防的东西。
//
// 所以版本走 `geometryDump()` 的 `ui_version` 行吐出去，出图脚本从**编译产物**读。
// 单一定义，改一处全对。
//
// **面板上不显示版本号**（2026-09-30 定的，不是忘了）。两条理由：
//   ① 小绪的设计原则第一条是"每一个可见像素都应服务于可操作参数或其当前值"——
//      版本号对**使用者**没有任何用，它服务的是开发者对账；
//   ② 对账本来就不需要它上屏：`--dump-geometry` 的 `ui_version` 与出图文件名
//      已经把这件事钉死了，而那两个地方都是**机器读**的、比画在界面上可靠。
// 想加回来之前先看这两条：它现在的唯一读者是出图脚本，别把开发者的便利
// 变成用户的噪声。
inline constexpr const char* kUiVersion = "0.36";

// ============================================================================
// 几何常量
// ============================================================================
//
// 一切尺寸 = 基准值 × S，S = 画布宽 / kBaseW。**画布宽高比锁死 2:1** ——
// 自由拉伸会把圆拉成椭圆、把行距压扁，整套几何失去意义。真插件用
// `setFixedAspectRatio(2.0)` 钉住，所以非基准比例根本不可能出现；
// 离线渲染那边也直接报错，不"悄悄兜住"（宁可报错，不许糊弄）。
namespace geom {

// ---- 画布 ----
inline constexpr float kBaseW = 1440.0f;
inline constexpr float kBaseH = 720.0f;

// ---- 参数区 ----
//
// v0.33：**世界树与分割线都删了**（小绪 2026-09-29：「包括左边的树也直接删掉吧，
// 我只要一个看起来简单的插件」→「完全删掉，参数铺满整块面板」）。于是参数区的
// 左右边界就是画布的左右内边距，**两个编译期常量，没有任何运行时输入**。
//
// 删掉的东西一并记在这儿，免得以后有人问"那根线去哪了"：
//     kTreeBoxX/Y/W/H · kTreeCX/CY/H · kColSpacing · kRingR · kGlowR   —— 树
//     kDividerX0 · kDividerMin · kDividerMax · kPaneGap                —— 分割线
// 历史原因值得留一句：`kDividerMin` 是**从树的包围盒推出来的**（362 + 24 = 386），
// 因为分割线拖进树的范围内会横穿它。树没了，这条推导的立足点也没了 ——
// 整条依赖链跟着一起消失，不是"留个常量以后可能有用"。
//
// `kPanePad` 原来是"只算右边距"（左边由 kPaneGap 管），现在**左右对称**。
inline constexpr float kPanePad = 40.0f;                   // 左右内边距
inline constexpr float kPaneX0 = kPanePad;                 // 40
inline constexpr float kPaneW = kBaseW - 2.0f * kPanePad;   // 1360

// ---- 参数区的纵向 ----
//
// v0.35：`kRowsTop` 的含义**变了** —— 它原来是"第一个分组的**内容**顶边"，
// 现在是"第一个**模块框**的顶边"。这一改是被模块框逼出来的，不是顺手：
//
//   框的顶边 = 内容顶边 − kBlockPadY。第一版直接把 padY 从 118 往上减，
//   于是框顶落到 104 —— 而当时副标题（"41 CONTROLS"，v0.36 已删）的墨迹
//   下沿在 120 附近，**框线横穿副标题**。渲染出来一眼就看到，但没有任何断言
//   会报红（"四栏首行齐平"量的是**行**，不是框）。
//   修法不是"把副标题挪开"（它会跟着标题走），而是把 `kRowsTop` 定义成
//   **框**的顶边：框从 138 起，副标题到 120 为止，净空 18px。
//
// 138 这个数是怎么来的：120（当时副标题墨迹下沿）+ 18（净空，与块间空档同量级）。
//
// **v0.36 换了住户，但 138 没动。** 副标题删了、顶栏右上角改画 logo，
// 而 logo 的纵向落位是**以 `kRowsTop` 为下界**反推的（居中于 `[kTabY, kRowsTop]`，
// 见下面的 `kLogoCY`）。所以这个数现在的作用是"顶栏带的下边界"，
// 改动它会同时挪动 logo —— 不是不能改，是改之前要知道它有两个住户。
inline constexpr float kRowsTop = 138.0f;                  // 第一个模块框的顶边
inline constexpr float kRowsBottomPad = 28.0f;
inline constexpr float kAvailH = kBaseH - kRowsTop - kRowsBottomPad;   // 554

// ---- 背景图（用户自己上传的那张）----
//
// ① **落位区是常量。** v0.33 起树没了，只剩一个落位区 —— 它**就是参数区本身**
//    （`kBgPaneX/W` 不再需要，直接取 `kPaneX0/W`）。于是"背景有没有盖住文字"
//    这件事退化成一个纯粹的包含关系，比 v0.31 那版更好断言。
//    历史：v0.31 时落位取的是"分割线能拖到的最左位置"那一段，为的是拖分割线
//    不触发源图重烤（3000×3000 源图重采样实测 21 ms，拖起来必卡）。分割线删了，
//    这条顾虑连同它的解法一起消失。
//
// ② **基准峰值 = 世界树骨架点线的 p99（实测 22）**，明暗度 1.0× 就是这一档。
//    再往上乘到 4.0× → 峰值 88；参数文字（235）对 88 的对比度仍有 5.97:1，
//    过 WCAG AA（4.5:1）。**上限不许再抬**，抬了就压不住文字了。
//    （骨架点线本身在 v0.33 删掉了，但这个基准值是**当年从它身上量出来的**，
//      换一个基准就是换一套明暗度刻度，所以原样留着并标明出处。）
inline constexpr float kBgPeakBase = 22.0f;
inline constexpr float kBgBrightMin = 0.25f;
inline constexpr float kBgBrightMax = 4.0f;
inline constexpr float kBgFeather = 64.0f;        // 四边羽化（逻辑 px），融进黑底

// ---- 间距阶梯 ----
// HIG · Layout 说分组可以用三种手段：`negative space, container shapes,
// or separator lines`。
//
// **v0.33 用了留白，v0.35 换成容器。** 记一笔，因为这是一次**推翻**：
//   小绪 2026-09-29 09:5x 说「我不要模块化的边框了」，于是 v0.33 把留白
//   加厚到"组间 = 行距 × 3"来切块。而 2026-09-30 他对着一版渲染图说：
//   「这是一个单独的模块，要做成**一部分框起来**，参照 VCV Rack 和模块效果器
//   的感觉，只不过是 Lux Cache 感觉版本的」。
//   两次要求并不矛盾 —— 09:5x 否掉的是**世界树那种"模块化的边框"**（树、
//   分割线、装饰性容器），他要的是**模块本身成为一个可辨认的单元**。
//   参照图给的就是答案：Lux Cache 的卡是"1px 发丝边 + 略亮底 + 圆角"，
//   不是描边框，也不是投影卡片。
//
// 于是留白退回到正常量级，分组由**框**来承担。`kSectionGapMult` 那张
// "组间 = 行距 × 倍数"的表**整张删掉** —— 它存在的前提（"只能靠留白分组，
// 所以组间要远大于组内"）随框一起消失。留下的是一个**绝对**空档：
//
//     框与框之间的空档 = kBlockGap（15px，四栏恒定）
//
// 为什么这里可以从"倍数"改回"绝对 px"（而 v0.34 特意从绝对改成了倍数）：
// 倍数是为了让**四栏的分组感一样**，因为那时分组感**只由空档提供**，
// 而四栏行距不同 → 绝对空档会让"组间/组内"的比值逐栏不同。
// 现在分组感由框提供，空档只负责"两张卡不要贴在一起" —— 那本来就是
// 一个绝对量（跟行距无关），**恒定反而是对的**。
inline constexpr float kGap = 8.0f;              // 行内：名称 ─ 轨道 ─ 数值
inline constexpr float kColGap = 24.0f;          // 列与列之间（框边到框边）
inline constexpr float kMinTrack = 46.0f;        // 轨道最短留多长

// ---- 模块框（v0.35）----
//
// 四个数各管一件事，**都不是随手调的**：
//
//   kBlockPadX  框边 → 内容（参数名左缘 / 数值右缘）的水平内缩。
//               `check_panel_render.py` 的「参数名左缘齐平」量的是**内容**左缘，
//               所以它必须吐出来给检查器（`--dump-layout` 的 `padx` 行）。
//   kBlockPadY  框边 → 内容顶/底的垂直内缩。它与 `kBlockUp/Down` 一起决定
//               "框顶到标题基线"有多远（实测 padY 12 + up 18 = 30）。
//   kBlockGap   框与框之间的空档。**四栏恒定**，见上面那段。
//   kBlockR     圆角半径。取 10 —— 参照图里的卡就是这个量级。
//               再大就变成"胶囊"（内容顶到框边的距离会被圆角吃掉），
//               再小就看不到圆角，白画一道。
inline constexpr float kBlockPadX = 14.0f;
inline constexpr float kBlockPadY = 12.0f;
inline constexpr float kBlockGap = 15.0f;
inline constexpr float kBlockR = 10.0f;

// ---- 行定位（按**文字基线**，不按行框）----
// 基线_i = 分组顶 + kBlockUp + i × pitch
// v0.26 对齐的是"行框底边"—— 行框不可见，高又逐列差 2.5 倍，文字于是差 39px，
// 而自检当时是绿的（它量的也是行框底边）。**量的东西必须是肉眼能看见的东西。**
//
// v0.35：这两个数的**基准**从"分组内容顶"变成"框内内容顶"（= 框顶 + padY）。
// 值本身从 19.4 / 12.6 收到 18.0 / 12.0 —— 框已经提供了外圈留白，
// 内容顶到标题基线再留 19.4 就重复了。
inline constexpr float kBlockUp = 18.0f;         // 框内内容顶边 → 首行基线
inline constexpr float kBlockDown = 12.0f;       // 末行基线 → 框内内容底边
inline constexpr float kRowBand = 0.80f;         // hover/press 行底高 = 行距 × 0.80


// ---- 字号阶梯（抄 Apple 的 macOS 内置文本样式）----
//     Headline 13 / Semibold → 模块标题
//     Body     13 / Regular  → macOS 正文默认字号，也是最小可读线
//     Callout  12 / Medium   → 参数数值
//     Caption1 11 / Regular  → 参数名
// Apple 规定 macOS 最小 10pt，并且"避免细字重"。所以只有 600 / 500 / 400 三档。
inline constexpr float kFsTitle = 13.0f;
inline constexpr float kFsValue = 12.0f;
inline constexpr float kFsName = 11.0f;
inline constexpr float kFsMin = 10.0f;

// ---- 树的字号 ----
inline constexpr float kFsTab = 11.0f;           // 顶栏分段控件标签
// `kFsHead`（17，视图标题）与 `kFsSub`（11，副标题）随 v0.36 的顶栏改动**一起删了** ——
// 它们唯一的住户是 `drawHeading()`，而那个函数现在改画 logo，一个字符都不写了。
// 留着两个没有住户的字号常量，只会让下一个人以为面板上还有标题。

// ---- 字距（按字号的比例给，不写死 px）----
//
// **v0.35 换字体时这三个数没有动，但它们是"按字体手工调的"** ——
// Suisse Neue 的字距是按它自己的宽度定的，我们打包的 Trane Sans（Inter）宽度
// 与之差约 8%（实测 'GRAIN DENSITY' 在 cap 对齐下：Suisse 18.833 em，Inter 17.336 em）。
// 但列宽（`labelW` / `valueW`）是**运行时按字体量的**，所以宽度差不影响排版，
// 只影响"字排得松不松"的观感。留一个待办在这里：
//   **下次改字号或换字体时，这三个数要重新量一遍**（现在没有断言盯着它们 ——
//   因为它们只影响观感，不影响任何一条几何）。
inline constexpr float kTrackUI = -0.012f;
inline constexpr float kTrackHead = -0.005f;
inline constexpr float kTrackData = -0.018f;

// ---- 字体自检的探针串（v0.35）----
//
// 面板要证明"我真的在用打包的那份字体、而且用的是对的那个字重"。
// 光报字体名不够：**两个字面的 family 都叫 `Trane Sans`**，报名字分不出
// Regular 和 SemiBold（CoreText 只给 family 名）。
//
// 所以报一个**实测宽度**：拿这串字在各自字号下量一次，测试那边用 fontTools
// 从 .ttf 的 hmtx 独立复算。
//
// **为什么是 `MIX`**：两个字重的前进宽度差要足够大才判得出来。实测（打包版本、
// 数字已改成等宽之后）：
//     `"WWWW"` 2.252% · `"MIX"` **2.237%** · `"GRAIN DENSITY"` 0.941%
//     · `"STUTTER FEEDBACK"` 0.736% · `"0123456789"` **0.151%**
// `MIX` 是这批里信号最强的**真实面板文案**（grain / stutter / comb / tape
// 四个模块各有一行 `MIX`，大写画出来就是它）。
//
// 数字串被排除了：数字改成等宽之后，两个字重的等宽数字几乎一样宽
// （SemiBold 1325 vs Regular 1327 单位），拿它当探针等于没探。
// **这条是实测踩出来的** —— 第一版探针就是 `"0123456789"`。
//
// 量的时候**字距给 0**，这样 Python 那边只需要 hmtx 的前进宽度，不必解析 GPOS。
inline constexpr const char* kFontProbeText = "MIX";

// ---- 旋钮（v0.34 引入 · v0.35 调大并**按模块**分配）----
//
// 直径**跟字号挂钩，不跟行距挂钩** —— 理由和轨道厚度一模一样（见 `trackHeight`）：
// 行距是每栏各自撑出来的（v0.35 实测 32.9 … 43.1），跟着行距走的话，同一张面板上
// 会出现两种大小的旋钮。字号是四栏共用的，于是四栏的旋钮一样大。
//
// **但字号只是上限的一半。** 直径还受**最挤那一栏的行距**约束，而且约束不是
// "别重叠"（那太松了）而是：
//
//     相邻两个旋钮的**净空 ≥ 环的粗细**（`kKnobStroke`）
//
// 为什么是"≥ 环粗"而不是"≥ 0"：两个环之间那道缝如果比环本身还细，读起来
// 不是"两个控件之间的间隙"，而是"环上的一道瑕疵" —— 两条环线加中间一条细缝，
// 眼睛会把它当成三根粗细不匀的线。**净空和环一样宽，才是三个等距的边。**
//
// 三次实测，把这条不变量的来路记全：
//   v0.34 第二稿 直径 24.2px，最挤一栏行距 29.875 → 净空 2.675 < 3.0 ✗
//                渲染出来 STUTTER SIZE / RATE 两个环确实几乎黏在一起；
//   v0.34 定稿   直径 22.0px（× 2.0），净空 4.875 ✓；
//   v0.35        模块框吃掉了"组间留白"那一大块（原来组间 = 行距 × 3），
//                行距因此涨到 32.9 … 43.1，直径**跟着涨**到 26.4px（× 2.4），
//                最挤一栏净空 32.9 − 29.4 = 3.5 ≥ 3.0 ✓。
//                为什么要涨：行变高了而旋钮不变，环与环之间的空档会比行内
//                其它留白都大，八个旋钮看着像"八颗小豆子撒在一列里"。
//                **直径是行距的从动件，不是独立的美学选择。**
//
// 这条不变量有断言盯着（`check_panel_render.py` 读 `--dump-geometry` 的
// `knob_dia` 逐栏算净空），反向对照是 `check_knobs_mutations.py` 的 M6 ——
// **不改直径、只改行距**（比如给某一栏加一行）同样会把它踩红。
inline constexpr float kKnobDia = kFsName * 2.4f;   // 26.4px
inline constexpr float kKnobStroke = 3.0f;          // 环的粗细（与轨道同量级）
// 弧：从 7:30 顺时针扫 270° 到 4:30 —— **开口在正下方**，这是真实旋钮刻度盘的
// 样子，也让"中点"落在弧的正中（12 点方向的 50% 位置）。
inline constexpr float kKnobStart = 225.0f;         // 起点角（度；12 点起算、顺时针）
inline constexpr float kKnobSweep = 270.0f;         // 总弧长（度）
inline constexpr float kKnobDotR = 1.6f;            // 末端指针点的半径

// ---- 字宽系数（em）—— 按最长文本反推列宽用 ----
//
// **数值列没有系数。** v0.33 之前这里有一个 `kValueW = 0.60f`（注释写的是
// "数字 + 单位平均前进宽度"），数值列宽按 `最长字符数 × kValueW × 字号` 算。
// 那是个"每个字符一样宽"的模型，两条前提**都不成立**，实测数据见
// `TranePanel.cpp` 里 `metricsDump()` 上方的长注释：
//
//   · 最宽的那个字符（`M`，出现在 "MS" / "MS" 这类单位里）实测 8.314px，
//     而模型给每个字符的预算是 7.2px —— 0.60 是**平均值**，不是上界；
//   · 41 个控件里有 10 个在量程两端的数值串比默认值处长（`+12.0DB` 7 字符
//     vs 默认值 6 字符），而列宽是按**默认值**的字符数算的。
//
// 两条都让数值的左缘爬进轨道区。数值是右对齐的，"右缘齐平"那条断言照样绿 ——
// 所以这个坏法**只能靠量**，看不出来。
//
// 现在数值列宽**直接量**（`extentsOf()` 实测最宽串），系数连同它的两条前提
// 一起删掉。**别再把它加回来**：任何"按字符数估宽度"的系数在字体降级时
// （Ableton Sans 读不到 → 退 Helvetica Neue，见 `dataFont`）都会变成错的方向
// 未知的一个数 —— 而"量"在任何字体下自动正确。
//
// `kLabelW` 留着（参数名那一列仍按字符数估），但它的处境是一样的：
// 同样是"平均值"，同样没有上界保证，只是那一列的失败模式不同（名字左对齐，
// 溢出往**右**爬进轨道）。见 `metricsDump()` 注释末尾那条待办。
inline constexpr float kLabelW = 0.63f;          // 大写字母平均前进宽度

// ---- 顶栏 ----
inline constexpr float kTabY = 34.0f;
inline constexpr float kTabH = 26.0f;

// ---- 顶栏品牌标（v0.36）----
//
// v0.35 及以前这里画的是视图标题 `Trane`（17px 满墨）与副标题 `41 CONTROLS`
// （11px、0.60 墨），左对齐在 `kPaneX0`。2026-09-30 用户要求：
// **删掉这两行文字，换成上传的金属 logo（透明底，只要 logo）**，
// 而且"放在左边有点怪，**放在右边吧**"。
//
// 于是顶栏的读法变成：**控件在左、品牌标在右**。
//
//   · 右缘 = 参数区右缘 `kPaneX0 + kPaneW`（= 1400）—— 与最右一栏的框右边界
//     齐平。实测 v0.35 渲染里参数区最右的非黑像素落在逻辑 x = 1399.5，
//     所以这条准线是**量出来的**，不是估的。
//   · 纵向**居中于整条顶栏带** `[kTabY, kRowsTop]`（34..138，中心 86）：
//     上不压分段控件、下不碰第一个模块框。
//   · 高 96 —— 实拍过 64 / 74 / 80 / 90 / 96 / 104 六档：64 太飘、104 顶到
//     模块框上沿，96 是"有分量且上下各留 4px"的那一档。
//
// **只写高**：宽度按资产自身的宽高比算（资产 375×384，近正方）。
// 两个数都写死的话，换一张资产就有一边对不上，而且没人会记得改。
inline constexpr float kLogoH = 96.0f;
inline constexpr float kLogoRight = kPaneX0 + kPaneW;        // 1400
inline constexpr float kLogoCY = (kTabY + kRowsTop) * 0.5f;  // 86

// ---- 背景控件（顶栏唯一的一组）----
//
// v0.33：顶栏原来有三组（模式 / 列数 / 背景），现在**只剩背景这一组** ——
// 前两组随「只要 ALL」一起删了（kTabW = 168 也跟着删，它是那两组的宽度）。
//
// 于是"这一组放在哪儿"有了一个明显更好的答案：**左对齐到参数区左缘**。
// 原来它是右对齐的（挤在模式组和列数组中间），那条约束的来路是
// "分割线拖到最右时模式组会长到 758，左对齐会被它压住" ——
// 分割线删了，约束消失了，剩下的就是"顶栏和它下面的四栏共用同一条左准线"。
// 这同时满足了小绪「所有排版都必须要整齐」里最硬的一条：**一条准线贯穿到底**。
inline constexpr float kBgCellW = 112.0f;         // 「选择图片」格（显示文件名）
inline constexpr float kBgSegW = 120.0f;          // [关][全屏] 两格
// 2 格而不是 3 —— 树没了，"树区落位"没有意义。总宽**故意保持不变**：
// 顶栏的组位置是按 kBgGroupW 反推的，改总宽会牵动整条右对齐链，
// 而这里要的只是"少一个选项"，不是"重新排一遍顶栏"。
inline constexpr int   kBgSegN = 2;
inline constexpr float kBgTrackW = 112.0f;        // 明暗度轨道
inline constexpr float kBgReadW = 44.0f;          // 倍率读数（要放得下 "0.25×"）
inline constexpr float kBgGap = 12.0f;
inline constexpr float kBgTrackH = 4.0f;          // 与参数行轨道同档
inline constexpr float kBgGroupW = kBgCellW + kBgGap + kBgSegW + kBgGap
                                 + kBgTrackW + kBgGap + kBgReadW;        // 424
inline constexpr float kBgGroupX = kPaneX0;                                      // 40

// 组内每件的左缘。**编辑器要用轨道那两个**（拖明暗度是按 x 反推值的），
// 所以它们必须是常量而不是 .cpp 里的局部推导 —— 一份事实来源。
inline constexpr float kBgTrackX = kBgGroupX + kBgCellW + kBgGap + kBgSegW + kBgGap;
inline constexpr float kBgReadX  = kBgTrackX + kBgTrackW + kBgGap;

// ---- 树的三层 · 质点圆 · 世界树几何 —— **v0.33 全部删除** ----
//
// 这里原本住着约 20 个常量：骨架 / 中柱 / 信号三层的不透明度、点线的 dash 节奏、
// 质点圆的光晕与选中环，以及从包围盒反推的 kRingR / kColSpacing / kTreeH /
// kTreeCX / kTreeCY / kLineTrim。
//
// 它们不是"暂时注释掉"，是**删了**。留着注释掉的常量比留着代码更坏：
// 下次有人想加个东西，会以为这些数还有意义。
//
// 一并记下它们当年的**量法**，因为那是这个项目最值得复用的一条方法：
//   整张面板渲成 PNG，**只在树的那一块里采样**（右半边是检查器、全是亮字，
//   不裁范围 p99 永远是 236），再挖掉每个节点圆盘（半径 r + 46px），
//   剩下的就是纯线像素，取 p50/p99/max。量出来：
//       骨架 · 普通连线   p50 12  p99  22  max  46
//       信号 · 静止档     p50 84  p99 125  max 128
//       信号 · 通过档     p50 13  p99 189  max 201   ← 最低呼吸相位
//   于是"通过档在最暗相位下也要比静止档最亮处亮"变成一个可判定的不等式
//   （kSigHotLo × kSigBreathMin = 0.663 > kSigRestHi = 0.55）。
//   **α 不是亮度** —— 第一版写 0.07/0.12，量出来峰值只有 25/255，眼睛根本看不见。

}  // namespace geom

// ============================================================================
// 颜色
// ============================================================================
//
// **全部是 Apple 深色模式的语义色**，不是"看着像"。名字保留 Apple 的叫法，
// 这样对着 HIG 就能查。
inline const juce::Colour kBg{0xff000000};        // systemBackground
inline const juce::Colour kInk{0xffebebf5};       // label —— 所有文字与线条的基色（微冷，不是纯白）
inline const juce::Colour kGray2{0xff636366};     // systemGray2 —— 分段控件的选中块
// 保留 systemBlue token 供平台语义/突变测试对照；面板绘制不使用它，避免任何蓝色装饰。
inline const juce::Colour kAccent{0xff0a84ff};

// 半透明的三个用 fromFloatRGBA 直接给 alpha，别先合成再当不透明色用 ——
// 它们压在**不同的底**上（面板底 / 行底 / 分段底），合成一次就丢了这层信息。
//
// **必须走 fromFloatRGBA**：`Colour{120, 120, 128, 0.36f}` 在 clang 下是
// 有歧义的 —— int 版 `Colour(int,int,int,float)` 与 float 版
// `Colour(float,float,float,float)` 同时可行，直接报
// "call to constructor of 'const juce::Colour' is ambiguous"。
inline const juce::Colour kFill =
    juce::Colour::fromFloatRGBA(120.0f / 255.0f, 120.0f / 255.0f, 128.0f / 255.0f, 0.36f);  // systemFill
inline const juce::Colour kSegBg =
    juce::Colour::fromFloatRGBA(118.0f / 255.0f, 118.0f / 255.0f, 128.0f / 255.0f, 0.24f);  // tertiarySystemFill
inline const juce::Colour kSep =
    juce::Colour::fromFloatRGBA(84.0f / 255.0f, 84.0f / 255.0f, 88.0f / 255.0f, 0.60f);    // separator

// ---- 模块框（v0.35）----
//
// 一个底 + 一条边。**两个都是"墨层"，不是新颜色** —— 都从 `kInk` 出发只改
// 不透明度，于是：
//   · 它们压在**背景图**上也对（用户上传的图会从框里透出来，被轻轻提亮，
//     而不是被一块不透明的板子切掉 —— 参照图里的卡也是半透的）；
//   · 对比度登记表能算（`Bd::Block` 就是"kInk @ kBlockFillA 压在面板底上"，
//     和 `track` / `seg` 同一个套路）。
//
// 为什么是这个量级，而不是"看着差不多"：
//   参照图（Lux Cache 的 petri）里，卡底与页面底的明度差**本来就极小**
//   （浅色主题下是 #FFF 压 #F2F2F4 那种量级）。Apple 深色模式里
//   systemBackground(#000000) → secondarySystemBackground(#1C1C1E) 也才
//   1.22:1。0.055 的墨压在纯黑上得到 #0D0D0D，与 #1C1C1E 同量级 ——
//   **这就是 Apple 的"抬起来的面"该有的样子**：看得见分层，看不见一条边。
//   边取 0.11：它得比底明显一点，否则"框"这件事读不出来。
//
// **"压在什么上"要分清**（这里是实测踩出来的）：
//   块底压在**面板底**上        → 0.055 的墨压纯黑 = **#0D0D0D**（13,13,13）
//   框线压在**块底**上          → 0.11 的墨压 #0D0D0D = **#262627**（38,38,39）
// 框线不是压在面板底上的：`drawBlock` 先铺满圆角矩形、再描那条内缩 0.5px 的线，
// 于是整根线都落在填充区**里面**。第一版把两层都按"压在纯黑上"算（得到 26），
// 而像素检查器的"框线真的画了"因此**绿着** —— 判据比实际低了 12，
// 线不画时峰值只有 13，离那个错阈值 23 还差得远。**判据错了，断言照样绿。**
//
// 两个数都有断言盯着，而且是**两套**：
//   · 像素侧 —— `check_panel_render.py` 量"框内是块底、框外是面板底、
//     框线有墨"，并且钉"面板上最多的两种颜色正好是这两层底"；
//   · 对比度侧 —— `tests/test_ui_design.py` 把 `block` 加进合成表，
//     于是块上每一处文字都重新算一遍 WCAG（v0.36 提亮后块上最暗 7.03:1，
//     仍过 AA 4.5:1；全表最暗的一处是选中分段块上的白字 5.06:1）。
inline constexpr float kBlockFillA = 0.055f;     // 块底：kInk @ 0.055 压面板底 = #0D0D0D
inline constexpr float kBlockEdgeA = 0.11f;      // 框线：kInk @ 0.11 **压块底** = #262627

// 文字的不透明度阶梯。
//
// v0.36 整条**上调了一档**（用户 2026-09-30 原话："所有文字亮度调高"）。
// 主内容档 `kAText` 本来就是满不透明，没有上调余地 —— 能提的就是次要那两档。
//
//   v0.35 → v0.36          压在面板底上      压在块底(#0D0D0D)上
//   kAMuted  0.60 → 0.72        6.4:1 → 9.0:1      6.2:1 → 8.3:1
//   kAOff    0.56 → 0.64        5.2:1 → 7.2:1      5.1:1 → 6.7:1
//
// 两个档之间**仍然留着 0.08 的差**：关闭态要读得出"这一块现在不参与"，
// 两档贴到一起就等于把"关闭"这件事从界面上抹掉了。
//
// Apple 的 tertiaryLabel(0.30) 在 #000000 上只有 2.23:1 —— **过不了 WCAG AA 4.5:1**，
// 所以它只给**非文字**（出厂刻度）用。这是有意偏离，不是疏忽。
inline constexpr float kAText = 1.00f;      // 数值、选中的分段标签（已是上限）
inline constexpr float kAMuted = 0.72f;     // 参数名、未选中的分段标签
inline constexpr float kAOff = 0.64f;       // 关闭态的一切文字
inline constexpr float kATick = 0.30f;      // **非文字**：出厂值刻度

// 交互强度。**单调**且 press ≥ 2 × hover —— 不然读不出"按住了"。
// v0.32 把 hover 从 0.06 降到 0.04：参数行 hover 不再联动模块圆之后，
// 行底本身需要更 subtle，否则黑底上的 0.06 仍然太跳。
inline constexpr float kHoverA = 0.04f;
inline constexpr float kPressA = 0.10f;
inline constexpr float kAHoverName = 0.88f; // hover 时参数名从 kAMuted 提到这里

// 动效（HIG · Motion）
inline constexpr float kMotionFast = 0.12f;   // s · press 的反馈（瞬时，不加缓动）
inline constexpr float kMotionDrag = 0.00f;   // s · **拖参数不加** —— 这条是规则，不是遗漏
                                              //     HIG：generally avoid adding motion to UI
                                              //     interactions that occur frequently
inline constexpr float kMotionMax = 0.30f;    // s · HIG 的 brief 上限

// ---- hover 淡入：**160 ms，ease-out** ----
//
// 小绪的原话是「我鼠标移动到某一个参数上，是会**缓慢发光高亮**的，而不是突然高亮」。
// 诉求（要渐入，不要硬切）完全正确，但"缓慢"要有个数 —— 而那个数不是凭感觉定的：
//
//     NN/g + Material motion 的实测区间：悬停淡入 **150–200 ms，ease-out**
//     （按下/抬起 100–150 · 开关翻转 150–200 · 提示出现 150–200 · 全部 < 400）
//     并且：**同一交互在一个任务里重复 > 10 次要减半，而不是加倍。**
//
// 参数行正是"一个任务里被扫过十几次"的控件。400 ms 在高频扫过时会变成摩擦 ——
// 鼠标已经到下一行了，上一行还在亮。**取 160 ms，落在区间正中偏快的一侧。**
// 这个取舍要跟小绪讲明白：他要的是"不突然"，不是"慢"。
inline constexpr float kHoverFade = 0.16f;

// 缓动：ease-out（进场快、收尾慢）。**进场用 ease-out、退场用 ease-in** 是
// Material motion 的硬规则 —— 反过来的话，元素看起来会"起步迟钝、到点撞墙"。
// 写成函数而不是查表：`easeOutCubic(t) = 1 - (1-t)³`，两次乘法，没有表。
inline float easeOutCubic(float t) {
    const float u = 1.0f - juce::jlimit(0.0f, 1.0f, t);
    return 1.0f - u * u * u;
}

// ============================================================================
// 值格式
// ============================================================================
enum class Fmt {
    None,    // 模块开关，不上检查器
    Ms,      // 250MS / 9.5MS
    Plain0,  // 220
    Plain2,  // 0.35
    Rate1,   // 4.0
    KHz1,    // 1.2K
    Db1,     // +0.0DB
    Choice,  // LP / BP / HP
};

// ============================================================================
// 控制表 —— 48 条，**逐条抄自 PluginProcessor.cpp::createLayout()**
// ============================================================================
//
// 顺序 = 质点顺序（Keter → Malkuth），所以检查器只要线性走一遍就能把控件
// 分配到十个模块上，不需要额外的映射表。
//
// 列：模块 · 参数 ID · 宿主显示名 · 环上短名 · 单位 · 格式 · 下界 · 上界 · 曲线 · 默认值
//
//   · **短名为空串 = 模块开关**。它不进检查器的参数行 —— 模块标题那一行
//     本身就是开关。七个开关：freeze / grain_on / stutter_on / comb_on /
//     tape_on / sweep_on / delay_on。ruin、space、out 没有开关参数，
//     它们只画标题，**不画状态方块**（不许假装有开关）。
//   · 下界/上界/曲线/默认值 与 createLayout() 的
//     `NR(lo, hi, interval, skew), 默认值` 一一对应。
//     **曲线是 skew 本身**，不是 1/skew —— JUCE 的
//     `NormalisableRange::convertTo0to1` 是 `std::pow(proportion, skew)`
//     （juce_NormalisableRange.h:147），早前写反过，辐条长度全错。
//
// 这张表是面板的**唯一数据源**：行分配、读数格式、双击复位、轨道长度全从它来。
// 它同时也是测试的锚点 —— 会拿它和 createLayout() 逐条对账（含显示名唯一性）。
//
// ---- 模块内的行序 ----
//
// 模块之间按信号顺序排（有 static_assert 盯着）；**模块内部**的规矩只有一条：
//
//     **先"尺度"后"关系"。** 一个模块的前几个参数是"这个引擎的刻度"
//     （多长 / 多密 / 多快 / 什么音高），后面几个是"它怎么和输入混"
//     （位置 / 喷射 / 扩散 / 反向 / 混合）。刻度在前，因为它们是这个模块
//     的**身份**；混合类在后，因为它们是所有模块共有的尾巴。
//
// v0.34 曾把 `grain_rate` 提到第 3 位、`sweep_center` 提到第 2 位，理由
// 是"让同一模块内的**旋钮**连成一段"。**那条理由随 v0.35 的"按模块定形态"
// 一起消失了** —— 现在一个模块要么全旋钮要么全条形，穿插不可能发生。
// 但**行序保留**：它顺带把语义理顺了，而新规矩（先尺度后关系）给出的
// 正是同一个顺序。**理由是换过的，结论没变** —— 记一笔，免得下一个人
// 看到"这条注释说的理由已经不存在了"就顺手把行序改回去。
//
//   · GRAIN：size / density / rate 是"一个粒子在**时间上的尺度**"
//     （见 core/GrainCloud.h:25「播放速率，同时决定音高与时长」），
//     然后 position / spray / spread / reverse / mix 是"粒子从哪来、往哪去"。
//   · SWEEP：rate / center 是"扫描的目标"（多久换一次 · 围绕哪个频率），
//     然后 depth / reso 是滤波器本身，最后 mode。语义依据是
//     core/RandomSweep.h:29–33 的字段注释。
//
// **改行序是安全的**：`kControls` 是界面顺序，宿主参数是按 id 建/按 id 存的
// （`createLayout()` 与测试都是逐 id 对账，不比对顺序）。已核。
inline constexpr int kMaxControls = 48;
inline constexpr int kMaxNodes = 10;
inline constexpr int kMaxColumns = 4;                        // 检查器固定 4 栏
inline constexpr int kMaxNodesPerColumn = 3;                 // v0.33 四栏里最挤的一栏有 3 个模块
inline constexpr int kMaxRows = kMaxControls + kMaxNodes;    // 48 个参数行 + 10 个标题行

struct ControlSpec {
    const char* module;
    const char* id;
    const char* name;   // 宿主里的显示名（必须全局唯一，测试盯着）
    const char* label;  // 环上的短名；空串 = 模块开关
    const char* unit;   // 读数用的单位；空串 = 无量纲
    Fmt fmt;
    float lo, hi, skew;
    float def;          // 出厂默认（真值，不是归一化值）
};

inline constexpr ControlSpec kControls[] = {
    // ── 0 · KETER · FREEZE ──────────────────────────────────────────────────
    {"freeze", "freeze", "Freeze", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"freeze", "loop_ms", "Loop", "loop", "ms", Fmt::Ms, 20.0f, 2000.0f, 0.3f, 250.0f},
    {"freeze", "seam_ms", "Seam", "seam", "ms", Fmt::Ms, 0.0f, 40.0f, 1.0f, 10.0f},

    // ── 1 · CHOKHMAH · GRAIN ────────────────────────────────────────────────
    {"grain", "grain_on", "Grain", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"grain", "grain_size", "Grain Size", "size", "ms", Fmt::Ms, 5.0f, 500.0f, 0.4f, 120.0f},
    {"grain", "grain_density", "Grain Density", "dens", "gr/s", Fmt::Plain0, 0.5f, 100.0f, 0.4f, 12.0f},
    {"grain", "grain_rate", "Grain Rate", "rate", "x", Fmt::Plain2, 0.25f, 4.0f, 0.4f, 1.0f},
    {"grain", "grain_position", "Grain Position", "pos", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.5f},
    {"grain", "grain_spray", "Grain Spray", "spry", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.15f},
    {"grain", "grain_spread", "Grain Spread", "sprd", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.6f},
    {"grain", "grain_reverse", "Grain Reverse", "rev", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.25f},
    {"grain", "grain_mix", "Grain Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 1.0f},

    // ── 2 · BINAH · STUTTER ─────────────────────────────────────────────────
    {"stutter", "stutter_on", "Stutter", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"stutter", "stutter_size", "Stutter Size", "size", "ms", Fmt::Ms, 5.0f, 500.0f, 0.4f, 90.0f},
    {"stutter", "stutter_rate", "Stutter Rate", "rate", "Hz", Fmt::Rate1, 0.25f, 30.0f, 0.4f, 4.0f},
    {"stutter", "stutter_jump", "Stutter Jump", "jump", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.35f},
    {"stutter", "stutter_mix", "Stutter Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 1.0f},

    // ── 3 · CHESED · COMB ───────────────────────────────────────────────────
    {"comb", "comb_on", "Comb", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"comb", "comb_tune", "Comb Tune", "tune", "Hz", Fmt::Plain0, 20.0f, 4000.0f, 0.35f, 220.0f},
    {"comb", "comb_feedback", "Comb Feedback", "fb", "", Fmt::Plain2, 0.0f, 0.95f, 1.0f, 0.6f},
    {"comb", "comb_mix", "Comb Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.5f},

    // ── 4 · GEVURAH · TAPE ──────────────────────────────────────────────────
    {"tape", "tape_on", "Tape", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"tape", "tape_speed", "Tape Speed", "speed", "x", Fmt::Plain2, 0.0f, 2.0f, 1.0f, 1.0f},
    {"tape", "tape_wobble", "Tape Wobble", "wob", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.12f},
    {"tape", "tape_mix", "Tape Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 1.0f},

    // ── 5 · TIFERET · RUIN（没有开关参数）──────────────────────────────────
    {"ruin", "ruin_mode", "Ruin Mode", "mode", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.0f},
    {"ruin", "ruin_drive", "Ruin Drive", "drive", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.35f},
    {"ruin", "ruin_fold", "Ruin Fold", "fold", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.0f},
    {"ruin", "ruin_crush", "Ruin Crush", "crush", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.0f},
    {"ruin", "ruin_ring", "Ruin Ring", "ring", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.0f},

    // ── 6 · NETZACH · SWEEP ─────────────────────────────────────────────────
    {"sweep", "sweep_on", "Sweep", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"sweep", "sweep_rate", "Sweep Rate", "rate", "Hz", Fmt::Plain2, 0.01f, 20.0f, 0.35f, 0.8f},
    {"sweep", "sweep_center", "Sweep Center", "cent", "Hz", Fmt::KHz1, 60.0f, 12000.0f, 0.4f, 1200.0f},
    {"sweep", "sweep_depth", "Sweep Depth", "depth", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.4f},
    {"sweep", "sweep_reso", "Sweep Reso", "reso", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.3f},
    {"sweep", "sweep_mode", "Sweep Mode", "mode", "", Fmt::Choice, 0.0f, 1.0f, 1.0f, 0.0f},

    // ── 7 · HOD · DELAY ─────────────────────────────────────────────────────
    {"delay", "delay_on", "Delay", "", "on", Fmt::None, 0.0f, 1.0f, 1.0f, 0.0f},
    {"delay", "delay_time", "Delay Time", "time", "ms", Fmt::Ms, 20.0f, 2000.0f, 0.4f, 375.0f},
    {"delay", "delay_feedback", "Delay Feedback", "fb", "", Fmt::Plain2, 0.0f, 0.92f, 1.0f, 0.45f},
    {"delay", "delay_damp", "Delay Damp", "damp", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.35f},
    {"delay", "delay_pingpong", "Delay PingPong", "ping", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.0f},
    {"delay", "delay_mix", "Delay Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.35f},

    // ── 8 · YESOD · SPACE（没有开关参数）───────────────────────────────────
    {"space", "space_mix", "Space Mix", "mix", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.55f},
    {"space", "space_size", "Space Size", "size", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.7f},
    {"space", "space_tail", "Space Tail", "tail", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.8f},
    {"space", "space_damp", "Space Damp", "damp", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.4f},
    {"space", "space_diffuse", "Space Diffuse", "diff", "", Fmt::Plain2, 0.0f, 1.0f, 1.0f, 0.7f},

    // ── 9 · MALKUTH · OUT（恒亮）───────────────────────────────────────────
    {"out", "output", "Output", "level", "dB", Fmt::Db1, -24.0f, 12.0f, 1.0f, 0.0f},
};

inline constexpr int kNumControls = static_cast<int>(sizeof(kControls) / sizeof(kControls[0]));

// ============================================================================
// 控件形态 —— **按模块**分配：哪五个模块全用旋钮（v0.35）
// ============================================================================
//
// 小绪（2026-09-30）：
//     「我说的旋钮不是把某一参数变为旋钮，而是**一整个模块里的参数**。
//      比如 GRAIN 适合旋钮表示的话，那就 GRAIN 的参数全部都用旋钮来表示，
//      同时这是一个单独的模块，要做成一部分框起来。具体的感觉/参照可以去
//      参考 VCV Rack 和模块效果器的感觉，我要的是这样的，只不过是变为
//      Lux Cache 感觉版本的。」
//
// ---- 这一条**推翻了 v0.34 的判据**，把来路记全 ----
//
// v0.34 的判据是逐参数的、一句话说完的：
//     「带物理单位（ms / Hz / x / gr·s⁻¹）→ 旋钮；无量纲 0..1 与 dB → 条形」
// 它可判、可查，而且自洽 —— 但它**把形态变成了参数的属性**，于是同一列里
// 出现「旋钮 / 条形 / 旋钮 / 条形」。我当时的补丁是"让同一模块内的旋钮连成
// 一段"，还在控制表里前移了两行来配合。**那个补丁治的是症状。**
//
// 小绪要的是：形态是**模块**的属性。GRAIN 是旋钮模块，那它就是八颗旋钮；
// 不是"三颗旋钮加五根条"。理由也站得住 —— 一个模块在 Eurorack 上就是一块
// 面板，面板上的控件形态是**这块面板的设计语言**，不是逐个参数挑出来的。
//
// ---- 判据（一句话，所以能查）----
//
//     这个模块是**调**出来的还是**配**出来的。
//     调出来的 —— 你要反复拧、听、再拧，参数之间**不可比**（冻多久 / 粒子多细 /
//                 切多快 / 音高多少 / 带速多少）→ **全旋钮**。
//     配出来的 —— 你要看几个份量的**比例**，参数在同一把 0..1 尺上、互相可比
//                 （毁多少 / 扫多少 / 延多少 / 空多少 / 出多少）→ **全条形**。
//
// 落到十个模块上（前五个 = 信号链的**形**，后五个 = 信号链的**量**）：
//
//     旋钮  FREEZE   冻多久     loop / seam
//           GRAIN    粒子多细   size / density / rate / position / spray / spread / reverse / mix
//           STUTTER  切多快     size / rate / jump / mix
//           COMB     音高多少   tune / feedback / mix
//           TAPE     带速多少   speed / wobble / mix
//     条形  RUIN     毁多少     mode / drive / fold / crush / ring
//           SWEEP    扫多少     rate / center / depth / reso / mode
//           DELAY    延多少     time / feedback / damp / pingpong / mix
//           SPACE    空多少     mix / size / tail / damp / diffuse
//           OUT      出多少     output
//
// ---- 两条**硬约束**落在这张表上，不是感觉 ----
//
// ① **模块里只要有分段选择（`Fmt::Choice`）就不能是全旋钮。**
//    三档选择器（LP / BP / HP）画不成旋钮 —— 它不是连续量。十个模块里只有
//    SWEEP 有，所以 SWEEP **必须是**条形模块。这条有测试盯着
//    （`test_a_choice_parameter_forbids_a_knob_module`），而且它是这条判据里
//    唯一**结构性**的一条：别的模块的取舍可以讨论，SWEEP 的不能。
//
// ② **同一栏不许混形态。** 现有的四栏切分
//    `{0,1}{2,3,4}{5,6}{7,8,9}` 正好把"形"的五个放在左两栏、"量"的五个放在
//    右两栏 —— 于是面板的阅读顺序是"左边拧、右边读"。
//    这条**有断言**（`test_no_column_mixes_forms`）：它是面板的可读性主张，
//    不是巧合；将来谁重排四栏，踩到它就该看到一句解释而不是一个神秘的报红。
//
// Interaction follows the drawn shape: knobs drag vertically, bars horizontally,
// and choices select the clicked segment. PluginEditor owns gestures/precision.
// Rendering and interaction both use isKnob(), so their shape cannot diverge.
//
// 拼错一个模块名不会崩，只会**整个模块少掉旋钮**（`moduleIsKnob()` 里有守卫）——
// 所以 `tests/test_ui_design.py` 拿探针吐出来的两张清单（模块名 + 展开后的
// 控件 id）与这张表对账，不许静默失效。
inline constexpr const char* kKnobModules[] = {
    "freeze",   // 冻多久 —— 循环 / 接缝时长（ms）
    "grain",    // 粒子多细 —— 尺度 / 密度 / 速率 / 位置 / 喷射 / 扩散 / 反向 / 混合
    "stutter",  // 切多快 —— 切片时长（ms）/ 速率（Hz）/ 跳变 / 混合
    "comb",     // 音高多少 —— 音高（20…4000 Hz 的对数刻度，横条上根本放不下）
    "tape",     // 带速多少 —— 0…2×，中心 1.0 = 原速
};
static_assert(sizeof(kKnobModules) / sizeof(kKnobModules[0]) == 5,
              "旋钮模块个数变了 —— 这是个设计决定，改这里的同时改那条对账测试");

// 这个模块的参数全画成旋钮吗。**模块名 → 布尔的表在静态初始化时算一次**，
// 因为 `isKnob()` 要在绘制循环里逐行查（41 行 × 每帧）。
bool moduleIsKnob(int node);
// 这个控件画成旋钮吗 = 它所属的模块是旋钮模块。
bool isKnob(int index);

// ============================================================================
// 模块表 —— 十个模块
// ============================================================================
//
// **这个顺序同时也是信号顺序** —— 事实来源是 `core/TraneEngine.cpp::process()`：
//     freeze → grain → stutter → comb → tape → ruin → sweep → delay → space → limiter
// 检查器的四栏是这张表上的**连续切片**，所以"从左到右、从上到下"的阅读顺序
// 就是信号顺序。这条不变量有 static_assert 盯着（见 .cpp 的 laneFlattensInOrder）。
//
// v0.33 删掉了两个字段，记一笔免得以后有人以为漏了：
//   `column`（0 左柱 / 1 中柱 / 2 右柱）与 `ratio`（纵向八等分）——
//   它们只服务于世界树的几何（画质点圆的坐标、以及"树的纵轴就是信号轴"
//   那条单调性断言）。树删了，这两个字段没有任何读者。
//   `sephira` 留着：它是模块的名字来源，也出现在 `--dump-geometry` 与测试里。
struct NodeSpec {
    const char* sephira;
    const char* module;
    const char* title;
};

inline constexpr NodeSpec kNodes[] = {
    {"keter",    "freeze",  "FREEZE"},
    {"chokhmah", "grain",   "GRAIN"},
    {"binah",    "stutter", "STUTTER"},
    {"chesed",   "comb",    "COMB"},
    {"gevurah",  "tape",    "TAPE"},
    {"tiferet",  "ruin",    "RUIN"},
    {"netzach",  "sweep",   "SWEEP"},
    {"hod",      "delay",   "DELAY"},
    {"yesod",    "space",   "SPACE"},
    {"malkuth",  "out",     "OUT"},
};

inline constexpr int kNumNodes = static_cast<int>(sizeof(kNodes) / sizeof(kNodes[0]));

// ============================================================================
// 面板状态
// ============================================================================
// v0.33 删掉了 `Mode { All, Modules }` 与 `moduleCount` ——
// 小绪的选择是「仍然删掉，只要 ALL」。于是检查器只有一种版面，
// 顶栏的模式段与列数段一起消失（原来那 3+3+4 的三栏也换成了四栏）。
//
// 用户自己上传的背景图放在哪儿。
//   Off    不画（出厂状态）
//   Full   垫在**参数区**（也就是整块面板的内容区）下面
//
// 原来是 `Off / Tree / Params` 三档 —— 树没了，"树区落位"没有意义，
// 所以砍成两档。**参数区现在就是整块内容区**，所以 `Full` 这个名字比
// `Params` 更准：它铺的是整块面板。
enum class BgWhere { Off = 0, Full };

// 背景图的完整规格。**它是 PanelState 的一部分**，这一点很关键：
// 面板层的可验证性建立在"离线渲染的输入 = PanelState"上，所以背景图
// 必须作为**数据**传进来，绝不能在面板层里读文件。
// （谁读文件：`PluginEditor`。它把读好的 `juce::Image` 塞进这里。
//   有测试盯着 TranePanel 里不许出现 File / ImageFileFormat / loadFrom。）
struct Backdrop {
    juce::Image image;                 // 原图（未缩放未压暗）；无效 = 没有图
    BgWhere where = BgWhere::Off;
    float brightness = 1.0f;           // kBgBrightMin … kBgBrightMax，线性乘在 kBgPeakBase 上
    juce::String name;                 // 文件名，只用来显示与自述，不参与绘制

    bool active() const { return where != BgWhere::Off && image.isValid(); }
};

struct PanelState {
    float value[kMaxControls]{};        // 归一化 0..1，下标 = kControls 的下标

    // 0..1，这个模块"当前有多忙"，只用来调制发光强度。
    // **调用方应先把整条数组填成 1.0**（"在响"），再用真实遥测覆盖：
    //   freeze → uiFreezeActive        grain → min(1, voices/12)
    //   out    → 1 - uiGainReduction   tape  → min(1, |speed-1| × 4)
    // 其余模块没有遥测，保持 1.0 就是诚实的 —— 界面不知道它忙不忙，
    // 只知道它开着。
    float moduleActivity[kMaxNodes]{};

    int focus = -1;                     // 正在拖拽 / 键盘聚焦的控件下标；-1 = 无
    float time = 0.0f;                  // 秒，驱动呼吸

    Backdrop backdrop;

    // 交互三态。**存的是命中结果而不是"哪一个控件"**，因为顶栏的格子也要
    // 参与 hover / press，用下标表达不了。
    // v0.33：删掉了 `node` 与 `divider` —— 树和分割线都没了，
    // 而**模块标题行的 hover 走的是 `control`**（标题行就是那个模块的开关，
    // 它是控制表里的一条），所以 `node` 没有剩下的读者。
    struct Mark {
        int control = -1;
        int tab = -1;      // v0.33 只剩一组：0 = 背景落位组
        int option = -1;   // 组内第几项
        bool bgSlot = false;     // 顶栏的「选择图片」格
        bool bgBright = false;   // 顶栏的明暗度轨道
        bool any() const {
            return control >= 0 || tab >= 0 || bgSlot || bgBright;
        }
        bool operator==(const Mark& o) const {
            return control == o.control && tab == o.tab && option == o.option
                && bgSlot == o.bgSlot && bgBright == o.bgBright;
        }
        bool operator!=(const Mark& o) const { return !(*this == o); }
    };

    // ---- hover 淡入（v0.33）----
    //
    // 小绪：「所有交互都要有质感，比如我鼠标移动到某一个参数上，是会**缓慢发光
    // 高亮**的，而不是突然高亮」。
    //
    // 做法：把"指针在谁身上"和"谁已经亮了多久"**分开**：
    //     cur   = 指针现在真正指着谁（瞬时，等于旧版的 `hover`）
    //     curT  = 这个进场动画的**线性进度** 0..1（时间，不是亮度）
    //     prev  = 上一个（正在退场）
    // 于是"离开"也是一段渐变 —— 只做进场的话，进得柔和、出去却是啪一下没了，
    // 那比两头都硬还怪。
    //
    // **缓动在读取时才施加**（`of()` 里过一遍 easeOutCubic），存的是线性时间。
    // 这样拆有两个好处：`step()` 简单到不可能错；缓动曲线单独可测。
    //
    // **进场与退场共用同一个 `curT`**，于是 `of(cur) + of(prev) == 1` 恒成立
    // —— 这是一次真正的交叉淡入，而不是"两个都亮着"的叠加。
    // （第一版打算让 prevT 自己从 1 衰减，结果两者会同时接近 1，
    //   中间那一瞬间比常态还亮。共用一个进度就没有这个缝。）
    struct HoverFade {
        Mark cur{};         // 指针现在指着谁
        Mark prev{};        // 上一个（正在退场）
        float curT = 1.0f;  // 进场进度（线性，0..1）；1 = 动画结束

        // 某个标记此刻该有多强的反馈（0 = 没亮，1 = 全亮）。
        // **空的标记恒返回 0** —— 少了这一句，"什么都没指"就等于"指着每一个"，
        // 面板上所有行会一起亮起来。
        float of(const Mark& m) const;

        // 指针动了。目标没变就什么都不做 —— 否则指针在同一行里每移动一像素
        // 都会把淡入重来一遍，看起来就是"怎么点不亮"。
        void retarget(const Mark& m);

        // 推进 dt 秒。线性，不缓动。
        void step(float dt);
    };
    HoverFade hoverFade{};

    Mark press{};
};

// ---- 造 Mark 的小工厂 ----
// 绘制代码里到处要"这一行 / 这一格 / 这个轨道"的 Mark，直接写结构体初始化
// 太啰嗦，而且容易漏字段（漏了 `tab` 就会和别的组撞上）。
inline PanelState::Mark mkControl(int c) {
    PanelState::Mark m; m.control = c; return m;
}
inline PanelState::Mark mkTabCell(int tab, int option) {
    PanelState::Mark m; m.tab = tab; m.option = option; return m;
}
inline PanelState::Mark mkBgSlot() {
    PanelState::Mark m; m.bgSlot = true; return m;
}
inline PanelState::Mark mkBgBright() {
    PanelState::Mark m; m.bgBright = true; return m;
}

// 圆边框 / 标题行亮不亮的**唯一判据**。放在面板里而不是调用方里，是为了让
// 编辑器和离线渲染用同一份代码 —— 两边各写一遍就一定会分叉。
//
//   有 on 开关的七个 → 看那个开关
//   RUIN            → ruin_mode > 0.02（mode = 0 就是纯干声，等于没开）
//   SPACE           → space_mix > 0.02
//   OUT             → 恒亮（它是输出）
bool moduleIsOn(int node, const PanelState&);

// 当前有几个模块"亮着"（moduleIsOn 为真）—— 供自检用。
int litModuleCount(const PanelState&);
// v0.33 删掉了 `hotEdgeCount`（"有几条信号边在通信号"）—— 世界树与信号线一起没了。
// **声明也一起删**，不是留着让它返回 0：一个恒为 0 的读数会被检查器当成
// "信号线全都暗着"而通过 —— 那是一条**永远为真**的断言，比没有断言更坏。

// ============================================================================
// 字体
// ============================================================================
//
// Ableton Sans 随用户已安装的 Ableton Live 12 存在。本插件只在运行时读取，
// **不复制、不打包、不分发**该字体；读不到时降级 Helvetica Neue。
juce::Font uiFont(float height, float kerning = 0.0f);
juce::Font dataFont(float height, float kerning = 0.0f);

// ============================================================================
// 表查询
// ============================================================================
int controlCount();
const ControlSpec& controlAt(int index);
int indexOfId(const juce::String& paramId);   // 参数 ID → 控制表下标；找不到返回 -1
int controlNode(int index);        // 这个控件属于哪个质点
int controlSlot(int index);        // 在这个质点里是第几个参数行（-1 = 模块开关）
int nodeControlCount(int node);    // 这个质点一共几个控件
int nodeRowCount(int node);        // 这个质点有几个参数行（不含标题行）
int nodeSwitchControl(int node);   // 模块开关在控制表里的下标；-1 = 没有开关
juce::String nodeTitle(int node);
juce::String nodeModule(int node);
bool nodeHasSwitch(int node);

// 归一化值 → 读数。短版给树上的质点圆用，长版给提示用。
juce::String formatShort(int index, float normalised);
juce::String formatLong(int index, float normalised);

// 出厂默认的**归一化**值。编辑器运行时用 APVTS 自己的 getDefaultValue()（更权威），
// 这个给离线渲染用；测试会核对两者一致。
float defaultNormalised(int index);

// 真值 ↔ 归一化（复刻 JUCE NormalisableRange::convertTo0to1 / convertFrom0to1）
float toNormalised(int index, float real);
float fromNormalised(int index, float normalised);

// ============================================================================
// 布局
// ============================================================================
//
// 参数检查器的行表。**它不是常量，是算出来的** —— 因为分割线可拖，
// 参数区宽度是运行时的量。每次绘制 / 命中测试各算一次（几十次浮点，可以忽略）。
//
// ---- v0.35：`x/w` 的含义变了 ----
// 它们是**模块框**的左缘与宽度（框边对齐参数区左右缘），内容再内缩 `padX`。
// 三段宽（名 / 轨道 / 数值）算的是**内容宽**，不是栏宽 —— 于是
// `w = padX + labelW + kGap + trackW + kGap + valueW + padX`。
// 这条等式有断言盯着（`check_panel_render.py` 的「三段宽 + 两道留白
// 正好填满一栏」），而它量的是**框内**。
struct ColumnLayout {
    int   nodeCount = 0;
    int   node[kMaxNodesPerColumn]{};
    int   rowCount = 0;             // 视觉行数（含每个模块的标题行）
    float x = 0.0f, w = 0.0f;       // **框**的左缘 / 宽
    float pitch = 0.0f;             // 行距（列内统一）
    float fsName = 0.0f, fsValue = 0.0f, fsTitle = 0.0f;
    float labelW = 0.0f, valueW = 0.0f, trackW = 0.0f;
};

// 一个模块框。**吐出来给检查器**（`--dump-layout` 的 `block` 行），
// 于是"框画在哪儿"从一个只有绘制代码知道的事，变成一件可以断言的事。
struct BlockLayout {
    int   column = -1;
    int   node = -1;
    float top = 0.0f, bottom = 0.0f;   // 框的上/下边（x / w 取所属栏）
    bool  knobModule = false;          // 这个模块全旋钮吗 —— 见 kKnobModules
};

struct RowLayout {
    int   column = -1;
    int   node = -1;
    int   control = -1;             // -1 = 模块标题行
    float baseline = 0.0f;          // 文字基线
    float mid = 0.0f;               // 光学中线（行底、控件都居中于它）
    float top = 0.0f;               // 这一行的分组顶边（只有标题行有意义）
};

struct InspectorLayout {
    int columnCount = 0;
    ColumnLayout column[kMaxColumns]{};
    int rowCount = 0;
    RowLayout row[kMaxRows]{};
    int blockCount = 0;
    BlockLayout block[kMaxNodes]{};
    int controlRow[kMaxControls]{}; // 控件下标 → 行下标；-1 = 这一版没显示
    int nodeTitleRow[kMaxNodes]{};  // 质点 → 标题行下标；-1 = 没显示
    int shownControls = 0;          // 副标题里的那个数
};


InspectorLayout buildInspector(const PanelState&);

// 呼吸相位 0..1 —— 由 PanelState::time 推出来，绘制与自检共用。
//
// v0.33：原来还有 `breathOfNode`（各质点相位错开，树不会齐步走），
// 树删了之后只剩参数条的填充用它，一个相位就够。
float breathOf(const PanelState&);

// ============================================================================
// 明暗度 ↔ 顶栏轨道位置
// ============================================================================
//
// **几何级数，不是线性。** 亮度是乘性的量：线性映射会把 0.25…1.0 挤进轨道
// 左边 20%，而 1.0…4.0 独占 80% —— 想调暗一点根本点不准。
// 取几何之后 1.0× 正好落在轨道正中（brightToTrack(1) = 0.5），两端对称。
//
// 这两个函数是**唯一**的换算来源：绘制（画填充段、画 1.0× 刻度）与
// 编辑器（拖轨道反推值）都调它们，谁都不许自己再写一遍公式。
float brightToTrack(float brightness);
float trackToBright(float t);

// ============================================================================
// 交互
// ============================================================================
struct Hit {
    // v0.33 删掉了 Node / TabMode / TabCount / Divider 四种 —— 树、模式段、
    // 列数段、分割线一起没了。剩下的五种全部住在**参数区或顶栏背景组**里。
    enum class Kind { None, Control, BgSlot, BgBright, TabBg };

    Kind kind = Kind::None;
    int control = -1;
    int titleNode = -1;     // Module header, including modules without a toggle.
    int option = -1;        // TabBg: 0=关 / 1=全屏

    PanelState::Mark mark() const {
        PanelState::Mark m;
        switch (kind) {
            case Kind::Control:  m.control = control; break;
            case Kind::TabBg:    m.tab = 0; m.option = option; break;
            case Kind::BgSlot:   m.bgSlot = true; break;
            case Kind::BgBright: m.bgBright = true; break;
            case Kind::None:     break;
        }
        return m;
    }
};

Hit hitTest(juce::Point<float> logicalPos, const PanelState&);

// ============================================================================
// 顶栏点击的判定 —— 从 PluginEditor 里搬回来的
// ============================================================================
// v0.33 起顶栏**只剩一组**分段控件：背景落位（关 / 全屏）。
// 模式段与列数段随「只要 ALL」一起删了，所以 BarGroup 现在只有一个成员 ——
// 但**这个类型留着**，因为判定逻辑（组 + 格 + 没拖动）是对的，
// 而且以后再加一组分段控件时不该重新发明一遍。
//
// 一次点击要成立，必须同时满足三件事：**按下的那一组 == 松手的那一组**、
// **按下的那一格 == 松手的那一格**、**中间没拖动过**。
//
// ---- 为什么要有 BarGroup 这个类型（这是一个真 Bug 的墓志铭）----
//
// v0.32.3 及以前，按下时把 `option + 1` 存进一个叫 `pressTab_` 的 int，
// 松手时又拿 `pressTab_ - 1` 当**组号**去判 —— 一个整数同时当两个维度用。
// 于是「模式段第 2 格（MODULE，option = 1）」和「列数段第 2 格（option = 1）」
// 撞成同一个数 2，松手时的组判据错位成"必须是列数段"：
//
//     点 ALL    → option 0 → 组判据要求 TabMode  ✓ 生效
//     点 MODULE → option 1 → 组判据要求 TabCount ✗ **永远不生效**
//
// 这就是小绪反馈了两轮的「MODULE 标签点不开」。同一根因还顺带废掉了
// 列数段的 1 / 3 / 4 格，以及背景落位段的 关 / 树 两格 —— 凡是 option ≠ 0
// 且组号对不上的格子，全都点不动。
//
// **为什么判定要住在面板层**：它原先住在 PluginEditor 里，而离线探针
// （panel_probe）够不着 PluginEditor —— 于是 tests 只能测到 hitTest，
// 测在了缝的另一侧，Bug 摆在眼前照样全绿。搬进来之后
// `panel_probe --click` 就能把「按下 → 松手 → 判定」整条链跑一遍。
enum class BarGroup { None = -1, BgWhere = 0 };

// 命中结果 → 组号。与 `Hit::mark()` 里的 `m.tab = 0` 是同一个编号，
// 两处必须一致 —— 渲染态和点击态说的是同一件事。
inline BarGroup barGroupOf(const Hit& h) {
    return h.kind == Hit::Kind::TabBg ? BarGroup::BgWhere : BarGroup::None;
}

// 松手时的判定结果。`fired == false` 就是"这一下不算数"（滑走了 / 拖过了 / 按的不是顶栏）。
struct ClickVerdict {
    bool fired = false;
    BarGroup group = BarGroup::None;
    int option = -1;
};

// 判定一次点击。
//
// **入参是"按下那一刻的 Hit 本身"，不是拆开的组号 + 格号。** 这一点是有讲究的：
// 只要调用方有机会自己算组号，就又会冒出"两处算法不一致"的缝 —— 编辑器算一套、
// 探针算一套，然后探针绿着、插件坏着。组号在函数内部由 `barGroupOf` 现算，
// 只有一处。编辑器要做的就是**原样存下按下的那个 Hit**，别做任何翻译。
ClickVerdict resolveBarClick(const Hit& pressed, bool moved,
                             juce::Point<float> releaseAt, const PanelState&);

// 命中测试的**自述**：给一个规格串，内部解析成点、跑一遍 hitTest，把结果
// 打成可断言的文本。规格写法与 `panel_probe --hover/--press` 相同：
//     ctl:<paramId>   tab:<0|1>   bgslot   bgbright
//     outside（面板外，应当什么都不命中）
//
// v0.33 从这张清单里删掉了 `divider` / `node:<module>` / `tab:<组>:<n>` 三行：
// 分割线、树上的圆心、模式段与列数段都没有住户了。**清单也要跟着删** ——
// 留着的话，写 `--hit node:tape` 的人会以为自己在测一个还在的东西。
//
// 存在的理由：**"MODULE 标签点不开"这条链路上原先一条真测试都没有** ——
// 当时 tests/test_editor_layout.py 里只有一句「源码里出现过 Kind::TabMode 这个
// 字符串」，那是文本匹配，把逻辑改坏了照样绿。这里把
// 「规格 → 点 → hitTest → 文本」整条打通，点击层才谈得上可验证。
// （v0.33 起 MODULE 这个住户本身也没了，但那套打通的办法留了下来，
//   现在守的是背景落位段的两格。）
juce::String hitDump(const juce::String& spec, const PanelState&);

// 规格串 → 逻辑坐标点。`--hover` / `--press` / `--hit` / `--click` 共用这一份
// 解析（留两份迟早分叉）。认不出来时 `ok` 为假、点落在面板外。
juce::Point<float> specPoint(const juce::String& spec, const PanelState&, bool& ok);

// 点击自述：把「按下 → 松手 → 判定」整条链跑一遍。走的是编辑器
// mouseDown / mouseUp 用的**同一份代码**（barGroupOf + resolveBarClick）。
juce::String clickDump(const juce::String& pressSpec, const juce::String& releaseSpec,
                       bool moved, const PanelState&);

// 文字对比度自述（v0.33）。
//
// 渲一帧，把「面板上每一处文字用的 (不透明度, 基底层, 墨层强度)」吐出来，
// 由 tests/test_ui_dark_layout.py 独立复算 WCAG 2.1 对比度。
//
// 为什么要这套东西：对比度是**唯一**一种"画出来看着还行、但已经不合规"的坏法。
// kInk 的 0.60 档压在 #000000 上是 7.4:1，压到 0.45 就掉到 4.1:1 —— 过不了 AA，
// 而屏幕上只是"名字暗了一点点"。**阈值必须有实测依据，而且要有东西盯着它。**
//
// 这套机制是从 v0.32 的 HTML 设计稿（`tools/render_ui_dark_panel.py` 的
// `TEXT_LOG`）搬过来的。搬的是**机制**：登记表由绘制代码自己填，不是测试里
// 另抄一份常量 —— 抄一份就会"改了绘制代码、断言还在按旧值算"。
juce::String textDump(const PanelState&);

// 文字度量自述：数值列里每个字符的实测宽度、每个控件能显示的最长数值串的实测宽度。
//
// **它是"数值列宽够不够"的唯一证据。** 数值是右对齐画的，而且走的是
// `drawText(..., useEllipsesIfTooBig = false)` —— 串太长不会截断，只会**静静地**
// 往左爬进轨道区。于是"右缘齐平"那类断言永远绿，这个坏法只能靠量。
//
// 吐出来的 `value_w` 是**布局真的在用**的那个列宽（`buildInspector()` 算出来的），
// 不是这里另算一份 —— 另算一份就会"改了布局、断言还在按旧值量"。
//
// 每个控件的最大宽度按 **201 个点**扫（布局自己只采 6 个点，图快）。
// 于是测试拿到的数**严格强于**布局自己的保证：布局漏掉的中间点这里会抓到。
// `check_metrics_mutations.py` 的 M3 就是专门靠这一点被抓住的。
juce::String metricsDump();

// 把归一化值量化到参数自己的最小步进，避免 0.30000000000000004
float quantise(int index, float normalised);

// ============================================================================
// 绘制
// ============================================================================
//
// 静态底图（面板底 + 22 条骨架点线 + 9 条静止信号线）**缓存到物理分辨率**。
// 理由和 v0.18 一样：`drawImage` 一旦要缩放就贵（juce_RenderingHelpers.h:1247
// 起的双线性路径），1:1 不透明贴图走的是 renderImageUntransformed 快速路径。
// 1440×720 @2x = 2880×1440 = 4.1M 像素，每帧重画 31 条线不划算。
//
// 但**亮的那些东西不进缓存**：通过档的信号线会呼吸、质点圆会呼吸、
// 行底会随 hover 变 —— 它们每帧都要重画。缓存里只放"永远不动的那一层"。
//
// 缓存**由调用方持有**，不用函数内 static：一个宿主里可能同时开两个编辑器，
// 共享一个 static 就是在两个线程上同时写同一张 Image。
struct PanelCache {
    juce::Image backdrop;        // 底 + 背景图 + 骨架 + 静止信号线，物理分辨率，不透明
    float backdropScale = 0.0f;  // backdrop 的物理像素 / 逻辑像素
    bool  backdropValid = false;

    // ---- 背景图的「缩放 + 羽化」中间结果（峰值固定 = kBgPeakBase × kBgBrightMax）----
    //
    // **单独缓存这一层，是为了让明暗度便宜。** 源图的高质量缩放是整条链上最贵的
    // 一步（3000×3000 的源图、2× 屏幕、参数区，实测 **21.1 ms** —— `panel_probe`
    // 5 次取最小；单次采样会抖到 26–71 ms，见 panel_probe 里那段注释），
    // 而拖明暗度只改一个乘数 —— 不该逼它重做。所以：
    //     缩放 + 羽化  → 只在（源图 / 落位 / 尺寸）变化时做，存进 bdScaled
    //     明暗度       → 合成时在贴好的那块像素上**原地乘**（tintRegion）
    // 实测（2880×1440，参数区）：拖明暗度 21.1 ms → **1.4 ms**（≈ 1/15）；
    // 而且因为落位是常量，**拖分割线完全不触发重烤**（之前是每帧 21 ms）。
    juce::Image bdScaled;
    // 它是在哪份规格下烤的。**只比前三项**（明暗度不算）—— 这正是单独缓存的意义。
    const void* bdImage = nullptr;
    int   bdWhere = -1;
    int   bdW = 0, bdH = 0;      // bdScaled 的物理尺寸（尺寸变了要重烤）

    // ---- v0.33：光晕精灵整块删除 ----
    //
    // 这里原来住着 `glow` / `glowScale` / `glowR` / `deviceScale`：十个质点圆的
    // 光晕形状完全一样，所以烤一张精灵图、每个圆贴一次 + `setOpacity(peak)`。
    // 配套还有一条**量出来的**教训，值得单独留在这里（它跟树没关系）：
    //
    //     CG 的 `CGContextDrawImage` 在目标矩形带分数偏移时必须重采样，
    //     实测约 **136 Mpx/s**；整数对齐的 1:1 贴图走的是接近 memcpy 的路 ——
    //     底图 4.1 Mpx 只要 0.43 ms（≈ 9.5 Gpx/s），**相差约 70 倍**。
    //     所以"精灵图反而比直接填渐变慢"（4.42 vs 3.00 ms）不是精灵图的错，
    //     是贴图坐标没吸附到整数设备像素。
    //
    // 树删了，这条教训暂时没有住户。**留着是因为它还会回来** ——
    // 下一批要加的光晕 / 阴影 / 圆角块，只要带分数坐标贴图就会踩同一脚。

    // 上次烤的是哪一份背景规格。**必须逐项比对**：图换了、落位换了、
    // 明暗度变了、尺寸变了，底图都得重烤，否则界面上会出现"图换了但背景
    // 还是旧的"这种最难查的错。
    // 图用 `getPixelData()` 的指针比身份 —— 换一张同尺寸的图也能认出来。
    const void* bakedImage = nullptr;
    int   bakedWhere = -1;
    float bakedBright = -1.0f;

    // ---- 顶栏品牌标（v0.36）----
    //
    // 资产是 375×384 的裸像素，面板上只画 96 逻辑 px 高 —— 2× 屏上是 192
    // 设备 px，直接贴等于 2:1 降采样。JUCE 的**中等**重采样质量只取 4 个纹素，
    // 准星的十字线、环这些 1–2px 的细笔画会闪；所以先按**设备像素尺寸**用
    // `highResamplingQuality` 缩一次、缓存住，之后每帧是 1:1 贴图。
    //
    // 只在设备尺寸变化时重算。面板尺寸是锁死的（`kBaseW/kBaseH`），
    // 所以实际上只算一次 —— 唯一能触发重算的是 DPI 变化。
    juce::Image logoScaled;
    int logoW = 0, logoH = 0;    // logoScaled 的设备像素尺寸

    // 尺寸变了（或第一次）就准备缓存。pixelScale 上限 2× —— 再大只是白占内存。
    void ensure(float pixelScale);
    // 每帧调一次：尺寸与背景规格都没变就直接返回。
    void update(const PanelState&);
    // 编辑器不可见时调，把缓存放掉。
    void release();
};

// 面板全部内容。调用前请先 cache.ensure(...)。
void paint(juce::Graphics&, const PanelState&, PanelCache&);

// 供测试与预览工具核对 —— 打印面板尺寸、树几何、每个质点的位置、行表。
juce::String geometryDump();

// 供测试与预览工具核对 —— 打印检查器**各栏的排版数字**：列宽 / 行距 / 字号 /
// 名-轨道-值三段宽度。`geometryDump()` 不收 `PanelState`，而这几项依赖状态
// （模式与列数 → 分栏 → 最挤那列 → 字号），所以必须单独一个入口。
// "排版大致不变"要靠它落成数字来证明，不能靠肉眼看两张图。
juce::String layoutDump(const PanelState&);

}  // namespace trane::panel
