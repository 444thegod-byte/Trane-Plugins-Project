// TranePanel.cpp — Träne 的面板绘制与命中测试（v0.30）
//
// 左边一棵世界之树（十个质点圆 + 22 条骨架点线 + 9 条信号实线），
// 右边一列列参数行，中间一条可拖的分割线。
//
// 五块：
//   1) 字体与表索引 —— 与 v0.18 逐字相同（字体、Layout、static_assert）
//   2) 树的几何     —— 质点坐标由 column/ratio 反推，边段两端各缩 r + 3
//   3) 布局         —— 检查器的行表**是算出来的**（分割线可拖，宽度是运行时的量）
//   4) 绘制         —— 树三层 + 检查器五件（分割线 / 顶栏 / 标题 / 行）
//   5) 命中         —— 反查
//
// **别给这个文件加 juce_audio_processors 的 include。** 加了 panel_probe 就编不过，
// 离线可验证性当场作废（tests/test_editor_layout.py 里有断言盯着）。
//
// 这一版的绘制逻辑与 `tools/render_ui_dark_panel.py`（v0.30 设计稿）**逐条对应**：
// 那边的 SVG 元素在这里是一个个 Graphics 调用，几何常量全部来自 TranePanel.h。
// 改一处必须改两处，`run_tests.sh` 的「设计稿自检」那一段会拿探针吐的几何回来对账。
#include "TranePanel.h"

#include "BinaryData.h"   // 打包的字体（TraneSans_SemiBold / _Regular）

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <vector>

namespace trane::panel {

namespace {

using namespace juce;

// ============================================================================
// 字体（v0.35：从"运行时读 Ableton"改成"**打包内嵌**"）
// ============================================================================
// 用户要求"字体也要用 Lux Cache 同款"。取证结果：Lux Cache 自托管的是
// **Suisse Neue Regular / Suisse Int'l Regular**（Swiss Typefaces，
// `© 2014 / © 2015 Swiss Typefaces Sàrl`）—— 商业授权、EULA 禁止再分发，
// 本机也没装。所以打包的是**最接近的开源替代**：Inter（OFL-1.1）在 `opsz=14`
// 下抽的两个静态实例，改名 `Trane Sans`，按**笔画粗细对齐**定字重。
// 选型（13 款候选的骨架 IoU）与字重的实测依据见 assets/fonts/PROVENANCE.md。
//
// ---- 为什么要打包，而不是继续读 Ableton ----
// 旧路径是"读 Ableton Live 安装目录里的 AbletonSans-Bold.otf，读不到就降级
// Helvetica Neue **Bold**"。实测：Ableton Bold 的竖干是 35.68，而
// Helvetica Neue Bold 是 43.86 —— **重 23%**。于是"用户装没装 Ableton"
// 会整档改变面板标题的字重，而**没有任何断言能发现**：所有断言量的都是几何
// （行距、列宽、框），字重不在其中。渲染出来一眼能看出两种面板，但绿的是绿的。
//
// 内嵌之后这条分支**整个消失**了：面板在任何机器上都是同一份字形。
//
// ---- 不设降级路径 ----
// 字体进了二进制就不存在"读不到"；真读不到只可能是构建坏了。那种情况应该
// **当场炸**（`jassert`），而不是悄悄换一个系统字体 —— 悄悄换字体正是上面
// 那个 bug 的成因。所以这里没有 `if (nullptr) return Font("Helvetica Neue")`。
Typeface::Ptr bundledTypeface(const void* data, std::size_t size) {
    auto t = Typeface::createSystemTypefaceFor(data, size);
    jassert(t != nullptr);   // 构建坏了。**不降级** —— 理由见上面那段。
    return t;
}

Typeface::Ptr uiTypeface() {
    static const auto t = bundledTypeface(BinaryData::TraneSans_SemiBold_ttf,
                                          BinaryData::TraneSans_SemiBold_ttfSize);
    return t;
}

Typeface::Ptr dataTypeface() {
    static const auto t = bundledTypeface(BinaryData::TraneSans_Regular_ttf,
                                          BinaryData::TraneSans_Regular_ttfSize);
    return t;
}

// 字体名给自检读（`--dump-geometry` 的 `font_ui` / `font_data`）。
// **这是"面板真的在用打包字体吗"这条断言唯一的判据** —— 量几何量不出字体，
// 而换字体只改文字、不改任何一条几何。
String typefaceName(const Typeface::Ptr& t) {
    return t != nullptr ? t->getName() : String("<null>");
}

String uiTypefaceName()   { return typefaceName(uiTypeface()); }
String dataTypefaceName() { return typefaceName(dataTypeface()); }

// ============================================================================
// 顶栏品牌标（v0.36）
// ============================================================================
// 替代 v0.35 及以前的 `Trane` 标题 + `41 CONTROLS` 副标题，见 TranePanel.h
// 的 `kLogoH` 注释。用户上传的原始 JPEG 在 `assets/logo/source/` 下，
// 抠底 / 提亮 / 缩放的完整过程与量化自检在 `assets/logo/PROVENANCE.md`。
//
// ---- 为什么读的是自制容器而不是 PNG ----
// 面板层**不许出现 `ImageFileFormat` / `loadFrom`** —— 那条护栏在
// `tests/test_editor_layout.py::test_panel_layer_never_touches_the_filesystem`，
// 它护的是"面板层的输入完整地只有一个 `PanelState`"这条架构约束（`panel_probe`
// 能离线渲图做像素检查，全靠这一条）。
//
// 为一张静态图把护栏改松是不划算的：烤成裸像素之后，运行时只是一次 memcpy，
// 比 PNG 解码还快，护栏一个字都不用动。**和背景动画素材 `backdrop.bin`
// 完全同一条路子**（见 TraneVideo.cpp 的 `clipData()`）。
//
// 容器的坏法一律**当没有素材**处理，不读越界也不崩 —— 与 `clipData()` 同规矩。
struct BrandMark {
    const std::uint8_t* px = nullptr;   // 指向 BGRA 像素（容器内，静态）
    int w = 0, h = 0;
    bool ok = false;
};

const BrandMark& brandMark() {
    static const BrandMark bm = [] {
        BrandMark b;
        const auto* p = reinterpret_cast<const std::uint8_t*>(BinaryData::trane_logo_bin);
        const auto size = static_cast<std::size_t>(BinaryData::trane_logo_binSize);

        constexpr std::size_t kHeader = 16;
        if (size < kHeader || std::memcmp(p, "TRNL", 4) != 0) return b;
        if (ByteOrder::littleEndianInt(p + 4) != 1u) return b;   // 版本对不上就当没有

        const auto w = static_cast<int>(ByteOrder::littleEndianInt(p + 8));
        const auto h = static_cast<int>(ByteOrder::littleEndianInt(p + 12));
        if (w <= 0 || h <= 0 || w > 4096 || h > 4096) return b;

        // 长度必须**正好**对得上。多了说明容器有别的段，少了说明截断 ——
        // 两种都不该猜着读。
        const auto need = kHeader + 4u * static_cast<std::size_t>(w) * static_cast<std::size_t>(h);
        if (size != need) return b;

        b.px = p + kHeader;
        b.w = w;
        b.h = h;
        b.ok = true;
        return b;
    }();
    return bm;
}

// 把容器里的裸像素建成一张 `juce::Image`，必要时缩到指定的设备尺寸。
//
// **容器里存的是 BGRA**（JUCE `PixelARGB` 在小端机上的内存布局），所以这里是
// 逐行 memcpy，没有逐像素循环、没有字节序转换 —— 转换在
// `tools/make_logo_asset.py` 里做了一次（并且每次都自校验解回来一致）。
juce::Image brandMarkImage(int deviceW, int deviceH) {
    const auto& bm = brandMark();
    if (! bm.ok || deviceW <= 0 || deviceH <= 0) return {};

    Image src{Image::ARGB, bm.w, bm.h, false};
    {
        Image::BitmapData d{src, Image::BitmapData::writeOnly};
        const auto rowBytes = 4u * static_cast<std::size_t>(bm.w);
        for (int y = 0; y < bm.h; ++y)
            std::memcpy(d.getLinePointer(y), bm.px + rowBytes * static_cast<std::size_t>(y), rowBytes);
    }

    if (bm.w == deviceW && bm.h == deviceH) return src;
    return src.rescaled(deviceW, deviceH, Graphics::highResamplingQuality);
}

// **没有降级分支。** 字体进了二进制就不可能"读不到"；真读不到只可能是构建坏了，
// 那时 `bundledTypeface()` 的 `jassert` 在 Debug 下当场炸。Release 下 NDEBUG 把
// jassert 编掉了，于是这里退到 JUCE 的默认字体 —— 但它**不是静默的**：
// `uiTypefaceName()` 会吐 `<null>`，而 `font_ui` 那条断言盯着这个名字，
// `run_tests.sh` 当场报红。**"静默降级"才是旧代码的病**，不是"降级"本身。
Font makeFont(const Typeface::Ptr& typeface, float height, float kerning) {
    if (typeface == nullptr) return Font(FontOptions(height).withKerningFactor(kerning));
    return Font(FontOptions(typeface).withHeight(height).withKerningFactor(kerning));
}

// ============================================================================
// 编译期防线
// ============================================================================
constexpr bool sameStr(const char* a, const char* b) {
    while (*a != '\0' && *a == *b) {
        ++a;
        ++b;
    }
    return *a == *b;
}

// 控制表必须严格按 kNodes 的顺序分块。顺序一乱，线性分配就错位，
// 而且错得很难看（参数跑到别的模块底下）—— 所以宁可在编译期红掉。
constexpr bool tableIsGroupedByNode() {
    int cursor = 0;
    for (int i = 0; i < kNumNodes; ++i) {
        int n = 0;
        while (cursor < kNumControls && sameStr(kControls[cursor].module, kNodes[i].module)) {
            ++cursor;
            ++n;
        }
        if (n == 0) return false;
    }
    return cursor == kNumControls;
}

static_assert(kNumControls == kMaxControls, "控制表条数变了，kMaxControls 要跟着改");
static_assert(kNumNodes == kMaxNodes, "模块表条数变了，kMaxNodes 要跟着改");
static_assert(tableIsGroupedByNode(), "kControls 必须严格按 kNodes 的顺序分块");

// v0.33 删掉的两条自检（连同它们的推导函数）：
//   `signalEdgesAreAdjacent` —— 9 条信号边是 kNodes 上的相邻对（信号线删了）
//   `ratiosAreMonotonic`     —— 质点 y 沿信号链单调不减（树的纵轴删了）
// **"阅读顺序 = 信号顺序"这条不变量没有丢**，它换了个住户：
// 四栏的 `laneFlattensInOrder()`（见上面），盯的是分栏而不是几何。

// ============================================================================
// 表索引
// ============================================================================
struct Layout {
    int nodeOf[kMaxControls]{};
    int slotOf[kMaxControls]{};      // 模块内的参数序号（开关 = -1）
    int switchOf[kMaxNodes]{};       // 模块开关在控制表里的下标；-1 = 没有开关
    int firstOf[kMaxNodes]{};
    int countOf[kMaxNodes]{};        // 含开关
    int paramsOf[kMaxNodes]{};       // **参数行数**（不含开关，也不含标题行）
};

const Layout& layout() {
    static const Layout L = [] {
        Layout l;
        for (int i = 0; i < kMaxNodes; ++i) {
            l.switchOf[i] = -1;
            l.firstOf[i] = -1;
        }
        int cursor = 0;
        for (int i = 0; i < kNumNodes; ++i) {
            l.firstOf[i] = cursor;
            int slot = 0;
            while (cursor < kNumControls && sameStr(kControls[cursor].module, kNodes[i].module)) {
                l.nodeOf[cursor] = i;
                if (kControls[cursor].label[0] == '\0') {
                    l.slotOf[cursor] = -1;
                    l.switchOf[i] = cursor;
                } else {
                    l.slotOf[cursor] = slot++;
                    ++l.paramsOf[i];
                }
                ++cursor;
                ++l.countOf[i];
            }
        }
        return l;
    }();
    return L;
}

// ---- 控件形态（v0.34 引入 · v0.35 改成**按模块**）----
//
// 清单在头文件（`kKnobModules`，存的是**模块名**）。这里做两件事：
// 把模块名解析成"这个模块是旋钮模块吗"（**静态一次**，因为要在绘制循环里
// 逐行查 —— 41 行 × 每帧），以及把"拼错的模块名"变成**看得见的失败**。
//
// 拼错一个模块名的后果很轻（那个模块还是画成条形），但很坏：**设计决定
// 悄悄失效**，而画面上本来就有两种形态，少一个模块的旋钮谁也不会去数。
// 所以两道防线：
//   · 这里 `jassert`（debug 构建当场炸）；
//   · `tests/test_ui_design.py` 拿探针吐的两张清单与头文件对账（release 也管）。
// 只有第一道是不够的 —— 门禁跑的是 release。
//
// **注意：这三个函数定义在匿名命名空间里是错的。** 它们与头文件里
// `namespace trane::panel` 的三条声明同名，于是同一个名字有了两个候选
// （`trane::panel::isKnob` 与 `trane::panel::{匿名}::isKnob`），调用点直接
// 报 "call to 'isKnob' is ambiguous"。v0.34 侥幸没炸，只因为当时**没有任何
// 调用点**（`geometryDump` 那时直接遍历 `kKnobIds`，没调 `isKnob`）。
// v0.35 的 `geometryDump` 要展开模块 → id，于是当场撞上。
// 修法是"把它们挪到匿名命名空间之外"（见下面那个 `}  // namespace`）——
// **不是**给调用点加限定名：那只是把两个名字并存这件事藏起来。
//
// 这一段先放在这里不动，是因为它要读 `sameStr`（下面那个匿名命名空间里的）；
// 真正的落点在同一 TU 的后面（`moduleIsKnob` / `isKnob` 两条定义）。
}  // namespace

const std::array<bool, kMaxNodes>& knobModuleFlags() {
    static const auto flags = [] {
        std::array<bool, kMaxNodes> f{};
        for (const char* m : kKnobModules) {
            int hit = -1;
            for (int i = 0; i < kNumNodes; ++i)
                if (sameStr(kNodes[i].module, m)) { hit = i; break; }
            jassert(hit >= 0);          // 拼错的模块名在 debug 下当场炸
            if (hit >= 0) f[static_cast<size_t>(hit)] = true;
        }
        return f;
    }();
    return flags;
}

bool moduleIsKnob(int node) {
    return node >= 0 && node < kNumNodes
        && knobModuleFlags()[static_cast<size_t>(node)];
}

// 控件 → 模块 → 形态。**中间那一跳是关键**：v0.34 是"这个 id 在清单里吗"，
// v0.35 是"它所属的模块在清单里吗" —— 于是**同一模块内形态不可能不一致**，
// 这是构造上保证的，不需要靠行序去维持。
bool isKnob(int index) {
    return index >= 0 && index < kNumControls && moduleIsKnob(controlNode(index));
}

// 匿名命名空间重新打开 —— 上面那三个函数是**对外**的（头文件里有声明），
// 必须住在 `trane::panel` 里，不能住进匿名命名空间（理由见上面那段注释）。
namespace {

// ============================================================================
// 数值
// ============================================================================
const char* const kChoices[] = {"LP", "BP", "HP"};
constexpr int kNumChoices = 3;

float realValue(const ControlSpec& c, float v01) {
    const float p = jlimit(0.0f, 1.0f, v01);
    const float q = c.skew == 1.0f ? p : std::pow(p, 1.0f / c.skew);
    return c.lo + (c.hi - c.lo) * q;
}

String numberFor(Fmt fmt, float v) {
    switch (fmt) {
        case Fmt::Ms:     return v >= 10.0f ? String(roundToInt(v)) : String(v, 1);
        case Fmt::Plain0: return String(roundToInt(v));
        case Fmt::Plain2: return String(v, 2);
        case Fmt::Rate1:  return String(v, 1);
        case Fmt::KHz1:   return String(v, 1);
        case Fmt::Db1:    return (v >= 0.0f ? String("+") : String()) + String(v, 1);
        default:          return String(v, 2);
    }
}

int choiceIndex(float normalised) {
    return jlimit(0, kNumChoices - 1,
                  static_cast<int>(std::lround(jlimit(0.0f, 1.0f, normalised) * 2.0f)));
}

// ============================================================================
// 分栏 —— 检查器固定四栏
// ============================================================================
//
// **展平后必须等于 kNodes 的顺序**（自检断言 `laneFlattensInOrder`），
// 也就是"从左到右、从上到下"的阅读顺序就是信号顺序。
//
// ---- 四栏是怎么分出来的（这是量出来的，不是摆出来的）----
//
// 每模块的显示行数 = 参数行 + 1 个标题行（模块开关不算行，它就是标题行本身）：
//
//     #  0     1     2      3     4    5     6     7     8    9
//     模块 freeze grain stutter comb tape ruin sweep delay space out
//     行    3     9      5     4    4    6     6     6     6    2      合计 51
//
// 三条约束一起解：
//   ① **必须连续切分** —— 保持"阅读顺序 = 信号顺序"这条不变量；
//   ② 尽量**按行数**均分，因为 `columnMetrics` 拿 `pitchMin`（最挤那列）定字号，
//      所以"最挤那列的行数"才是真正要压的那个数，不是"每栏几个模块"；
//   ③ 任何一栏都别只剩一个模块 —— 行数少的列行距会被拉得很开（这是
//      `rowPitch` 的已知行为：末行对齐的代价），历史上量到过
//      `out 2 行 → 542px`，两个参数孤零零挂在 720px 高的面板上，那不是留白是空。
//
// 穷举 4 栏的全部连续切分（C(9,3) = 84 种），最优解是：
//
//     {0,1}  {2,3,4}  {5,6}  {7,8,9}      行数 12 / 13 / 12 / 14
//
// **最挤 14 行**（次优解是 16），极差只有 2。对照：v0.33 之前的 3 栏是
// `{0,1,2}{3,4,5}{6,7,8,9}` → 17 / 14 / 20，**最挤 20**。
// 也就是说"删掉树、多开一栏"之后，最挤那列反而**松了 6 行** ——
// 于是 `pitchMin` 从 18.979 涨到 29.875，而字号本来就被 `jmin(1.0f, …)` 封顶，
// **11 / 12 / 13 三档一个都不变**。这就是"排版大致不变"落成的数字。
constexpr int kAllLanes[][kMaxNodesPerColumn] = {
    {0, 1, -1}, {2, 3, 4}, {5, 6, -1}, {7, 8, 9},
};
constexpr int kAllLaneLen[] = {2, 3, 2, 3};
constexpr int kNumAllLanes = 4;

// 自检：展平必须等于 kNodes 的顺序，而且不能重复 / 漏项。
constexpr bool laneFlattensInOrder() {
    int seen[kMaxNodes] = {};
    int at = 0;
    for (int i = 0; i < kNumAllLanes; ++i)
        for (int j = 0; j < kAllLaneLen[i]; ++j) {
            const int nd = kAllLanes[i][j];
            if (nd < 0 || nd >= kMaxNodes || seen[nd]) return false;
            seen[nd] = 1;
            if (nd != at) return false;      // 必须**恰好**是 0,1,2,… 的顺序
            ++at;
        }
    return at == kNumNodes;
}
static_assert(laneFlattensInOrder(),
              "四栏展平后必须是 kNodes 的完整顺序 —— 阅读顺序 = 信号顺序");

// 呼吸 —— 与 v0.18 同一条曲线，v0.33 起**没有相位偏移**（树删了，
// 十个质点不再各自呼吸；唯一的住户是参数条的填充，它只要一条曲线）。
//
// 闪烁：两条高频正弦相乘。**不能用随机数** —— 每帧不一样的闪烁既不像霓虹灯
// （霓虹是稳定的抖），也让截图回归做不了。
float breathAt(float t) {
    const float breath = 0.5f - 0.5f * std::cos(t / 2.6f * MathConstants<float>::twoPi);
    const float flicker = 0.5f + 0.5f * std::sin(t * 7.3f) * std::sin(t * 11.9f);
    return jlimit(0.0f, 1.0f, breath * (0.90f + 0.10f * flicker));
}

// ============================================================================
// 布局 —— 参数检查器的行表
// ============================================================================
//
// 这一节是 v0.30 里最"算"的部分，全部与设计稿的
// `extents / row_pitch / columns_for / column_block / all_layout / module_layout`
// 逐条对应。行按**文字基线**定位（行框这个概念已经删掉，见 kBlockUp 的注释）。

// 这批模块里**最长的参数名**（字符数）与**最长的数值串**（实测宽度）。
//
// 数值那一半 v0.33 之前存的是"最长数值的**字符数**"，列宽再按
// `字符数 × kValueW × 字号` 算。那个模型的两条前提都不成立（实测见
// `metricsDump()` 上方的注释），现在直接量宽度，两条前提一起消失。
//
// 采 **6 个点**：量程两端 + 三个内点 + 出厂值。为什么 6 个点够：数值串的宽度
// 只随"位数 / 小数点 / 正负号 / 单位"四样变，而这四样都在量程两端取到极值。
//
// **这条"够不够"不靠推理保证** —— `tests/test_ui_design.py` 会拿 201 个点
// 重扫一遍，扫出比这 6 个点更宽的串就报红。推理会过期，扫描不会。
struct Extents {
    int   lmax = 1;       // 最长参数名的字符数
    float vmaxW = 0.0f;   // 最长数值串在 kFsValue 下的实测宽度
};

void extentsOf(int* nodes, int n, Extents& e) {
    // 量宽度要字体。**用 kFsValue 量、不缩放** —— 列宽最后会整体乘 fit，
    // 而"字号缩放时字形宽度线性缩放"这条假设由测试盯着（它按**实际字号**
    // 再量一遍来对账，见 test_value_column_fits_every_value）。
    const Font f = dataFont(geom::kFsValue, geom::kTrackData);
    for (int k = 0; k < n; ++k) {
        const int node = nodes[k];
        for (int i = 0; i < kNumControls; ++i) {
            if (layout().nodeOf[i] != node) continue;
            if (kControls[i].label[0] == '\0') continue;   // 模块开关不进参数行
            e.lmax = jmax(e.lmax, static_cast<int>(String(kControls[i].name).length()));
            const float ts[] = {0.0f, 0.25f, 0.5f, 0.75f, 1.0f, defaultNormalised(i)};
            for (float t : ts)
                e.vmaxW = jmax(e.vmaxW, GlyphArrangement::getStringWidth(f, formatShort(i, t)));
        }
    }
}

// 一列有 rows 行、blocks 个模块框时，**行与行之间的基线距离**。
//
// 两条要求同时成立：组内每行等距；每列的**末行**落在同一条水平线上（于是跨列也对齐）。
// 解方程（v0.35：模块框的上下内缩与框间空档都进等式）：
//     (rows−blocks)·p + blocks·(UP+DOWN) + blocks·(padT+padB) + (blocks−1)·gap = avail_h
//  ⟹ p = [avail_h − blocks·(UP+DOWN+padT+padB) − (blocks−1)·gap] / (rows − blocks)
//
// ---- v0.35 把"倍数"改回"绝对空档"，这是有意的（不是手滑）----
// v0.34 特意从绝对 px 改成"组间 = 行距 × kSectionGapMult"，理由是那时
// **分组感只由留白提供**，而四栏行距不同 → 绝对空档会让"组间/组内"的比值
// 逐栏不同。现在分组感由**框**提供，空档只负责"两张卡别贴在一起" ——
// 那本来就是个绝对量。于是 `kSectionGapMult` 整张表删掉，换成 `kBlockGap`。
//
// 副产物（实测）：框吃掉的空间远大于"组间留白 ×3"，所以行距从
// 29.9…40.8 涨到 32.9…43.1 —— 面板**变松了**，而不是变挤。
float rowPitch(int rows, int blocks) {
    const float perBlock = geom::kBlockUp + geom::kBlockDown
                         + geom::kBlockPadY * 2.0f;
    const float span = geom::kAvailH
                     - static_cast<float>(blocks) * perBlock
                     - static_cast<float>(blocks - 1) * geom::kBlockGap;
    const float den = static_cast<float>(rows - blocks);
    return den > 0.0f ? span / den : span;
}

struct ColMetrics {
    float colW = 0.0f;              // **框**宽
    float innerW = 0.0f;            // 框内内容宽 = colW − 2×padX
    float fsName = 0.0f, fsValue = 0.0f, fsTitle = 0.0f;
    float labelW = 0.0f, valueW = 0.0f, trackW = 0.0f;
};

// N 列并排时的**列宽**与**三档字号**。
//
// 列宽 = 框宽（框边对齐参数区左右缘），列间只留 kColGap；框内再内缩 padX。
// 字号取自 Apple 的 macOS 文字样式阶梯（13 / 12 / 11），只有在
// ①框内内容宽放不下 ②行距放不下 两种情况下才**整体等比缩** ——
// 绝不允许某一档单独变，那会把层级压平（HIG：保持文本元素的相对层级）。
//
// **内缩必须进"放得下吗"这条判据**：v0.35 之前算的是整栏宽，框一加，
// 能用的宽度少了 2×14 = 28px，而字号是按"整栏宽放得下"选的 —— 于是
// 名义上没变、实际上轨道被压短。实测：轨道 167.9 → 142.9px（−15%）。
// 这不是 bug，是内缩的必然代价；把它写进判据，代价才是**量出来的**。
//
// 两段文字宽的量法不一样，**这是有意的**：
//   · 参数名 —— 字符数 × kLabelW × 字号（仍是估算，见头文件里 kLabelW 的注释）；
//   · 数值   —— `Extents::vmaxW`，**实测**（字体降级时也自动正确）。
ColMetrics columnMetrics(int nCols, const Extents& e, float pitch) {
    ColMetrics c;
    c.colW = (geom::kPaneW - geom::kColGap * static_cast<float>(nCols - 1))
           / static_cast<float>(nCols);
    c.innerW = c.colW - 2.0f * geom::kBlockPadX;

    // 两段都折算成"**每单位 kFsName** 要多少像素"，于是 `fit` 就是它俩共同的
    // 缩放系数，`fsFitW / kFsName` 仍然是"允许的最大字号"。
    // （`kLabelW × kFsName` 是 fit = 1 时每个字符的宽度，乘字符数就是名字列宽。）
    const float need = static_cast<float>(e.lmax) * geom::kLabelW * geom::kFsName + e.vmaxW;
    const float den = need / geom::kFsName;
    const float fsFitW = den > 0.0f
                       ? (c.innerW - 2.0f * geom::kGap - geom::kMinTrack) / den : 99.0f;
    const float fsFitH = pitch * 0.72f;   // 字号不许超过行距的 72%，否则上下行贴在一起
    const float fit = jmin(1.0f, fsFitW / geom::kFsName, fsFitH / geom::kFsName);

    c.fsName = geom::kFsName * fit;
    c.fsValue = geom::kFsValue * fit;
    c.fsTitle = geom::kFsTitle * fit;
    c.labelW = static_cast<float>(e.lmax) * geom::kLabelW * c.fsName;
    // 数值列宽 = 实测最宽串 × fit。fit = 1 时它**正好**等于最宽那个串的宽度，
    // 于是最宽的数值离轨道恰好 kGap —— 和"名字 ─ 轨道"那个间隔一样宽。
    // 不额外留余量：余量是"赌还有更长的串"，而更长的串该由测试报红，不该由空白兜住。
    c.valueW = e.vmaxW * fit;
    c.trackW = c.innerW - c.labelW - c.valueW - 2.0f * geom::kGap;
    return c;
}

// 轨道厚度 / 分段块高度 —— **由字号定，不由行高定**。
//
// 行高是按列反推的，如果厚度跟着行高走，行数少的列轨道会明显比行数多的列粗，
// 同一张面板上出现两种粗细。内容尺寸必须与行高解耦：行高只负责留白。
//
// ---- v0.35 把两个系数都调大了（0.30 → 0.45 / 1.45 → 1.75）----
// 理由不是"看着细"，而是**两种形态的重量失衡**：v0.35 的模块框吃掉了
// "组间留白"，行距从 29.9…40.8 涨到 32.9…43.1，旋钮直径跟着涨了 20%
// （22.0 → 26.4），而轨道厚度**纹丝不动** —— 于是左半边（全旋钮）看着是
// 一列实心的环，右半边（全条形）看着是几根头发丝。实测渲染图：
// 4px 的条在 43px 的行里只占 9%，而参照图（petri）里条占行距的 60% 以上。
//
// 系数仍然是**字号的比例**（不是行距的比例）—— 这条规矩没动：
// 四栏的条照样一样粗。变的只是"字号 → 粗细"的换算比例。
float trackHeight(const ColumnLayout& col) { return jmax(2.0f, col.fsName * 0.45f); }
float choiceHeight(const ColumnLayout& col) { return col.fsName * 1.75f; }

}  // namespace

// ============================================================================
// hover 淡入（v0.33）
// ============================================================================
//
// 三个函数，各管一件事。**加起来不到 15 行** —— 这是有意的：
// 交互质感最容易烂在"状态机写复杂了"，所以这里只留"谁在亮 / 亮了多久"。
//
// 缓动只在 `of()` 里施加。`step()` 是纯线性的，于是它不可能错；
// 而缓动曲线可以单独被断言（`panel_probe --hover-t` 那条链就是这么测的）。
//
// **注意这三个定义必须在匿名命名空间之外。** 成员函数的定义只能写在
// "包含这个类"的命名空间里；上面那个匿名命名空间是另一个（无名的）命名空间，
// 在里面定义 `PanelState::HoverFade::of` 会被编译器判为
// "namespace '' does not enclose namespace 'HoverFade'"。

float PanelState::HoverFade::of(const Mark& m) const {
    // **空的标记恒返回 0。** 少了这一句，`cur == {}` 时"什么都没指"
    // 会和"每一个空标记"相等 —— 面板上所有行一起亮起来。
    if (!m.any()) return 0.0f;

    const float e = easeOutCubic(curT);
    if (m == cur)  return e;
    if (m == prev) return 1.0f - e;   // 交叉淡入：两者之和恒为 1
    return 0.0f;
}

void PanelState::HoverFade::retarget(const Mark& m) {
    // 目标没变就**什么都不做**。少了这一句，指针在同一行里每移动一像素都会
    // 把淡入重来一遍 —— 表现是"这一行怎么也亮不起来"，而且很难查
    // （hitTest 每一帧都被调用，日志看起来完全正常）。
    if (m == cur) return;

    prev = cur;
    cur = m;
    curT = 0.0f;                      // 新的那个从 0 开始涨
}

void PanelState::HoverFade::step(float dt) {
    if (dt <= 0.0f) return;
    // 线性推进，**不缓动**。时间上限 1 —— 掉帧 / 卡顿之后不补帧，
    // 直接到位（补帧会让淡入看起来"忽快忽慢"，而且卡顿本身已经很难受了）。
    curT = jlimit(0.0f, 1.0f, curT + dt / kHoverFade);
}

// ============================================================================
// 对外：字体
// ============================================================================
Font uiFont(float height, float kerning) {
    return makeFont(uiTypeface(), height, kerning);
}

Font dataFont(float height, float kerning) {
    return makeFont(dataTypeface(), height, kerning);
}

// ============================================================================
// 对外：表查询
// ============================================================================
int controlCount() { return kNumControls; }
const ControlSpec& controlAt(int index) { return kControls[jlimit(0, kNumControls - 1, index)]; }

int indexOfId(const String& paramId) {
    for (int i = 0; i < kNumControls; ++i)
        if (paramId == kControls[i].id) return i;
    return -1;
}

int controlNode(int index) { return layout().nodeOf[jlimit(0, kNumControls - 1, index)]; }
int controlSlot(int index) { return layout().slotOf[jlimit(0, kNumControls - 1, index)]; }
int nodeControlCount(int node) { return layout().countOf[jlimit(0, kMaxNodes - 1, node)]; }
int nodeRowCount(int node) { return layout().paramsOf[jlimit(0, kMaxNodes - 1, node)]; }
int nodeSwitchControl(int node) { return layout().switchOf[jlimit(0, kMaxNodes - 1, node)]; }
bool nodeHasSwitch(int node) { return layout().switchOf[jlimit(0, kMaxNodes - 1, node)] >= 0; }
String nodeTitle(int node) { return kNodes[jlimit(0, kMaxNodes - 1, node)].title; }
String nodeModule(int node) { return kNodes[jlimit(0, kMaxNodes - 1, node)].module; }

// 模块亮不亮的**唯一判据**。三条规则：
//   有 on 开关的七个 → 看那个开关
//   RUIN            → ruin_mode > 0.02（mode = 0 就是纯干声，等于没开）
//   SPACE           → space_mix > 0.02
//   OUT             → 恒亮（它是输出）
bool moduleIsOn(int node, const PanelState& st) {
    node = jlimit(0, kMaxNodes - 1, node);
    const int sw = layout().switchOf[node];
    if (sw >= 0) return st.value[sw] > 0.5f;

    const auto& mod = kNodes[node].module;
    if (sameStr(mod, "ruin")) {
        const int i = indexOfId("ruin_mode");
        return i >= 0 && st.value[i] > 0.02f;
    }
    if (sameStr(mod, "space")) {
        const int i = indexOfId("space_mix");
        return i >= 0 && st.value[i] > 0.02f;
    }
    if (sameStr(mod, "out")) return true;
    return false;
}

int litModuleCount(const PanelState& st) {
    int n = 0;
    for (int i = 0; i < kNumNodes; ++i)
        if (moduleIsOn(i, st)) ++n;
    return n;
}

// ============================================================================
// 对外：读数
// ============================================================================
// 环上短版 —— 单位**大写**，与设计稿的 value_text() 一致
// （v0.18 写的是小写 ms / dB / k，v0.30 统一成 MS / DB / K）。
String formatShort(int index, float normalised) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];
    const float v = realValue(c, normalised);
    switch (c.fmt) {
        case Fmt::None:   return {};
        case Fmt::Ms:     return numberFor(c.fmt, v) + "MS";
        case Fmt::KHz1:   return String(v / 1000.0f, 1) + "K";
        case Fmt::Db1:    return numberFor(c.fmt, v) + "DB";
        case Fmt::Choice: return kChoices[choiceIndex(normalised)];
        default:          return numberFor(c.fmt, v);
    }
}

// 提示用长版 —— 数字与单位分开写：环上写 1.2K，这里写 1200 Hz
String formatLong(int index, float normalised) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];
    const float v = realValue(c, normalised);
    if (c.fmt == Fmt::None) return c.name;
    if (c.fmt == Fmt::Choice) return kChoices[choiceIndex(normalised)];

    const float shown = (c.fmt == Fmt::KHz1) ? std::round(v) : v;
    const String num = numberFor(c.fmt, shown);
    return c.unit[0] == '\0' ? num : num + " " + c.unit;
}

// ============================================================================
// 对外：真值 ↔ 归一化
// ============================================================================
// **复刻 JUCE `NormalisableRange::convertTo0to1`**（juce_NormalisableRange.h:147）：
//     proportion = clamp0to1((v - start) / (end - start));
//     return symmetricSkew ? ... : std::pow(proportion, skew);
// 参数全部走四参构造 NR(start, end, interval, skew)，symmetricSkew 默认 false，
// 所以就是这一支。**是 skew，不是 1/skew** —— 写反的后果很具体：
// grainSize 120ms（5–500, skew 0.4）本该在 55.8% 处，错公式给出 2.6%。
float toNormalised(int index, float real) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];
    const float span = c.hi - c.lo;
    const float p = span <= 0.0f ? 0.0f : jlimit(0.0f, 1.0f, (real - c.lo) / span);
    return c.skew == 1.0f ? p : std::pow(p, c.skew);
}

float fromNormalised(int index, float normalised) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];
    const float p = jlimit(0.0f, 1.0f, normalised);
    const float q = c.skew == 1.0f ? p : std::pow(p, 1.0f / c.skew);
    return c.lo + (c.hi - c.lo) * q;
}

float defaultNormalised(int index) {
    return toNormalised(index, kControls[jlimit(0, kNumControls - 1, index)].def);
}

float quantise(int index, float normalised) {
    const auto& c = kControls[jlimit(0, kNumControls - 1, index)];
    const float v = jlimit(0.0f, 1.0f, normalised);
    if (c.fmt == Fmt::Choice) return std::round(v * 2.0f) / 2.0f;
    // 2000 步：比显示精度细，又足以让读数稳定不跳
    return std::round(v * 2000.0f) / 2000.0f;
}

// ============================================================================
// 对外：呼吸
// ============================================================================
float breathOf(const PanelState& st) { return breathAt(st.time); }

// 明暗度 ↔ 轨道位置。**几何级数**，理由写在 TranePanel.h。
// 这两个是唯一的换算来源 —— 绘制与编辑器都调它们。
float brightToTrack(float brightness) {
    const float lo = geom::kBgBrightMin, hi = geom::kBgBrightMax;
    return std::log(jlimit(lo, hi, brightness) / lo) / std::log(hi / lo);
}

float trackToBright(float t) {
    const float lo = geom::kBgBrightMin, hi = geom::kBgBrightMax;
    return lo * std::pow(hi / lo, jlimit(0.0f, 1.0f, t));
}

// ============================================================================
// 对外：布局
// ============================================================================
InspectorLayout buildInspector(const PanelState& st) {
    InspectorLayout L;

    // ---- 1. 分栏 ----
    // v0.33：只有一种版面了（小绪：「仍然删掉，只要 ALL」），
    // 所以这里不再有 if/else —— 分栏是常量，不依赖任何状态。
    int laneNodes[kMaxColumns][kMaxNodesPerColumn]{};
    int laneLen[kMaxColumns]{};
    const int nCols = kNumAllLanes;
    for (int i = 0; i < nCols; ++i) {
        laneLen[i] = kAllLaneLen[i];
        for (int j = 0; j < laneLen[i]; ++j) laneNodes[i][j] = kAllLanes[i][j];
    }

    // ---- 2. 最长名 / 最长值（列宽按最长的那个留）----
    // 跨栏取**同一个** Extents —— 于是四栏的三段宽完全一致，轨道起点不会跟着栏跳
    // （`check_panel_render.py` 的「三段宽 · 跨栏一致」盯着这条）。
    Extents e;
    for (int i = 0; i < nCols; ++i) extentsOf(laneNodes[i], laneLen[i], e);

    // ---- 3. 每列的行距（行数不同 → 行距不同，这是"末行对齐"的代价）----
    float pitch[kMaxColumns]{};
    float pitchMin = 1.0e9f;
    for (int i = 0; i < nCols; ++i) {
        int rows = 0;
        for (int j = 0; j < laneLen[i]; ++j) rows += 1 + nodeRowCount(laneNodes[i][j]);
        pitch[i] = rowPitch(rows, laneLen[i]);
        pitchMin = jmin(pitchMin, pitch[i]);
    }

    // ---- 4. 列宽与字号：**各列一致**，按最挤的那列定 ----
    const ColMetrics cm = columnMetrics(nCols, e, pitchMin);

    // 参数区的左缘是**编译期常量**（v0.33：分割线删了）。
    //
    // v0.35：`col.x` / `col.w` 是**框**的几何。框边对齐参数区左右缘 ——
    // 于是"顶栏左缘 / 标题左缘 / 四栏框左缘"共用同一条准线（小绪要的
    // 「一条准线贯穿到底」），而参数名与数值**内缩** `kBlockPadX`。
    // 参数名左缘因此比标题左缘右移 14px —— 这是容器该有的样子（参照图里
    // 卡的标题也在卡边之内），不是错位。检查器量的是**内容**左缘。
    const float x0 = geom::kPaneX0;
    for (int i = 0; i < nCols; ++i) {
        ColumnLayout& col = L.column[i];
        col.nodeCount = laneLen[i];
        for (int j = 0; j < laneLen[i]; ++j) col.node[j] = laneNodes[i][j];
        col.x = x0 + static_cast<float>(i) * (cm.colW + geom::kColGap);
        col.w = cm.colW;
        col.pitch = pitch[i];
        col.fsName = cm.fsName;
        col.fsValue = cm.fsValue;
        col.fsTitle = cm.fsTitle;
        col.labelW = cm.labelW;
        col.valueW = cm.valueW;
        col.trackW = cm.trackW;
    }
    L.columnCount = nCols;

    // ---- 5. 分配行 ----
    // 行按文字基线排：基线_i = 框内内容顶 + kBlockUp + i × pitch。
    // 下一个模块的框顶 = 本框底 + kBlockGap。
    //
    // `top` 是**框内内容顶**（= 框顶 + padY）；框顶另用 `frameTop` 记。
    // 起点取 `kRowsTop + padY`，于是第一个框的**框顶**正好落在 kRowsTop ——
    // 四栏的框上下缘因此齐平（`check_panel_render.py` 的「四栏框顶齐平」）。
    for (int i = 0; i < nCols; ++i) {
        ColumnLayout& col = L.column[i];
        float top = geom::kRowsTop + geom::kBlockPadY;
        for (int j = 0; j < laneLen[i]; ++j) {
            const int node = laneNodes[i][j];
            const float frameTop = top - geom::kBlockPadY;

            // 标题行（同时就是模块开关的命中区）
            if (L.rowCount < kMaxRows) {
                RowLayout& r = L.row[L.rowCount];
                r.column = i;
                r.node = node;
                r.control = -1;
                r.baseline = top + geom::kBlockUp;
                r.mid = r.baseline - col.fsTitle * 0.35f;
                r.top = top;
                L.nodeTitleRow[node] = L.rowCount;
                ++L.rowCount;
                ++col.rowCount;
            }

            // 参数行
            for (int k = 0; k < kNumControls; ++k) {
                if (layout().nodeOf[k] != node) continue;
                if (kControls[k].label[0] == '\0') continue;
                if (L.rowCount >= kMaxRows) break;

                RowLayout& r = L.row[L.rowCount];
                r.column = i;
                r.node = node;
                r.control = k;
                r.baseline = top + geom::kBlockUp
                           + static_cast<float>(1 + layout().slotOf[k]) * col.pitch;
                r.mid = r.baseline - col.fsName * 0.35f;
                r.top = -1.0f;
                L.controlRow[k] = L.rowCount;
                ++L.rowCount;
                ++col.rowCount;
                ++L.shownControls;
            }

            // 本模块的框 —— 记下来给检查器（`--dump-layout` 的 `block` 行）。
            // **框的高度由内容反推**，不是另存一个"块高"常量：
            // 内容高 = kBlockUp + n×pitch + kBlockDown，框高再各加 padY。
            const float contentBottom = top + geom::kBlockUp
                                      + static_cast<float>(nodeRowCount(node)) * col.pitch
                                      + geom::kBlockDown;
            if (L.blockCount < kMaxNodes) {
                BlockLayout& bl = L.block[L.blockCount++];
                bl.column = i;
                bl.node = node;
                bl.top = frameTop;
                bl.bottom = contentBottom + geom::kBlockPadY;
                bl.knobModule = moduleIsKnob(node);
            }

            // 下一个模块的**内容**顶
            top = contentBottom + geom::kBlockPadY + geom::kBlockGap + geom::kBlockPadY;
        }
    }

    return L;
}

// ============================================================================
// 对外：命中
// ============================================================================
namespace {

// 顶栏控件的位置（与绘制共用，避免画与点两处算）。
// v0.33 删掉了 modeTabBox / countTabBox —— 那两段控件本身没了。
struct TabBox { float x, y, w, h; };

// ---- 背景控件（顶栏**唯一**的一组，位置全是常量）----
//   ① 「选择图片」格   ② [关][全屏] 落位组   ③ 明暗度轨道 + 倍率读数
TabBox bgCellBox() {
    return {geom::kBgGroupX, geom::kTabY, geom::kBgCellW, geom::kTabH};
}

TabBox bgSegBox() {
    return {geom::kBgGroupX + geom::kBgCellW + geom::kBgGap,
            geom::kTabY, geom::kBgSegW, geom::kTabH};
}

// 轨道比顶栏矮，竖直居中；**命中区仍然用整格高**（4px 高的东西点不着）。
TabBox bgTrackBox() {
    return {geom::kBgTrackX, geom::kTabY, geom::kBgTrackW, geom::kTabH};
}

TabBox bgReadBox() {
    return {geom::kBgReadX, geom::kTabY, geom::kBgReadW, geom::kTabH};
}

bool inBox(Point<float> p, const TabBox& b) {
    return p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h;
}

}  // namespace

Hit hitTest(Point<float> p, const PanelState& st) {
    Hit h;

    // ① 顶栏（背景那一组，整块面板上唯一的顶栏内容）
    //
    // **顺序要紧**：先格子、再落位组、最后轨道。三者几何上不重叠，顺序只为确定性。
    // v0.33 删掉了两段：分割线（最优先的那一段，因为它能拖）和模式/列数两组。
    {
        if (inBox(p, bgCellBox())) { h.kind = Hit::Kind::BgSlot; return h; }

        const auto bg = bgSegBox();
        if (inBox(p, bg)) {
            const float cw = bg.w / static_cast<float>(geom::kBgSegN);
            h.kind = Hit::Kind::TabBg;
            h.option = jlimit(0, geom::kBgSegN - 1, static_cast<int>((p.x - bg.x) / cw));
            return h;
        }

        // 轨道只有 4px 高，命中区给整格 —— 不然根本点不着。
        if (inBox(p, bgTrackBox()) || inBox(p, bgReadBox())) {
            h.kind = Hit::Kind::BgBright;
            return h;
        }
    }

    // ② 检查器的行。**模块标题行就是那个模块的开关**，所以它走 Control 而不是
    //    另开一种 Kind —— 标题行本来就是控制表里的一条（`_on` 那个开关）。
    {
        const auto L = buildInspector(st);
        for (int i = 0; i < L.rowCount; ++i) {
            const auto& r = L.row[i];
            const auto& col = L.column[r.column];
            const float half = col.pitch * geom::kRowBand * 0.5f;
            if (p.y < r.mid - half || p.y > r.mid + half) continue;
            if (p.x < col.x - geom::kGap * 0.5f
                || p.x > col.x + col.w + geom::kGap * 0.5f) continue;

            h.kind = Hit::Kind::Control;
            h.control = (r.control < 0) ? nodeSwitchControl(r.node) : r.control;
            if (r.control < 0) h.titleNode = r.node;
            if (r.control >= 0 && kControls[r.control].fmt == Fmt::Choice) {
                const float tx = col.x + geom::kBlockPadX + col.labelW + geom::kGap;
                if (p.x >= tx && p.x <= tx + col.trackW
                    && std::abs(p.y - r.mid) <= choiceHeight(col) * 0.5f)
                    h.option = jlimit(0, kNumChoices - 1,
                                      static_cast<int>((p.x - tx) * kNumChoices / col.trackW));
            }
            // 没有开关的模块（ruin / space / out）标题行**不可点** ——
            // 给一个 -1 的 control，调用方一眼能看出"这一下没有目标"。
            return h;
        }
    }

    return h;
}

// 松手判定 —— 三条同时成立才算数（同一组、同一格、中间没拖过）。
// 详细的来龙去脉见 TranePanel.h 里 BarGroup 的注释：这里原先住着一个
// "拿 option 兼作组号"的编码错误，正是「MODULE 标签点不开」的根因。
ClickVerdict resolveBarClick(const Hit& pressed, bool moved,
                             Point<float> releaseAt, const PanelState& st) {
    ClickVerdict v;

    // 组号在这里现算，**不接受调用方传进来的** —— 见头文件里的理由。
    const BarGroup group = barGroupOf(pressed);
    if (group == BarGroup::None) return v;   // 按的根本不是顶栏
    if (moved) return v;                     // 中间拖动过 = 用户改主意了

    const auto h = hitTest(releaseAt, st);
    if (barGroupOf(h) != group) return v;    // 滑到别组了 = 取消
    if (h.option != pressed.option) return v; // 滑到别格了 = 取消

    v.fired = true;
    v.group = group;
    v.option = pressed.option;
    return v;
}

// ============================================================================
// 绘制
// ============================================================================
namespace {

// 一行的**瞬时**交互态。**hover 不在这个枚举里** —— 它是要淡入的，
// 而枚举表达不了"亮了三成"。淡入的强度由 `hoverAmt` 单独带进来。
//
// （v0.33 之前这里是 Idle/Hover/Press/Focus 四态：Focus 从 v0.32 起就不画
//   任何东西了（蓝色聚焦环被小绪否掉），Hover 被 hoverAmt 取代。
//   删掉两个**没有读者的枚举值**比留着它们安全：留着的话，下一个人会以为
//   "Focus 态长什么样"是个已定义的东西。）
//
// **任何一态都只改颜色，不改几何** —— 立这条的理由：
// 状态一变就重排，是"闪一下、跳一下"的根因；而且重排之后"末行对齐"这类
// 排版断言会全部失效，状态就成了排版的一个隐藏输入。
// v0.33 起这条**有机器在盯**：`check_panel_render.py` 把 hover / press / focus
// 三种态各自渲一张，然后跑**同一组排版断言**（四栏行数、逐行左右齐平、
// 首末齐平）。状态一改几何，那几条当场报红。
enum class RowState { Idle, Press };

RowState rowStateOf(const PanelState& st, int control) {
    if (control < 0) return RowState::Idle;
    if (st.press.control == control) return RowState::Press;
    return RowState::Idle;
}

// 某一行此刻的 hover 强度（0..1，含缓动）。
//
// press **不叠加**：按下之前指针一定已经在那一行上，`curT` 本来就是满的；
// 而且 press 是瞬时反馈（见 kMotionFast），不该有淡入。
float hoverAmtOf(const PanelState& st, int control) {
    return control < 0 ? 0.0f : st.hoverFade.of(mkControl(control));
}


// ============================================================================
// 文字对比度登记表（v0.33）
// ============================================================================
//
// 面板上每一处文字，画之前把「不透明度 + 脚下的基底层 + 墨层强度」登记一笔。
// `--dump-text` 把它吐出来，由 tests/test_ui_dark_layout.py **独立复算** WCAG。
//
// 为什么要"登记"而不是"在测试里列一份清单"：列一份就是抄第二份事实 ——
// 改了绘制代码（比如把参数名从 0.60 压到 0.50）而没改那份清单，对比度断言
// 还在按旧值算，于是它绿着、字已经糊了。**登记的必须是绘制代码自己报的数。**
//
// 这套机制是从 v0.32 的 HTML 设计稿（`tools/render_ui_dark_panel.py` 里的
// `TEXT_LOG`）搬过来的。搬的是**机制**，不是数字：数字由这里的绘制代码自己报。
//
// 三个字段的语义：
//   a      —— 文字的不透明度（kInk 的 alpha）
//   bd     —— **基底层**：面板底 / 模块块底 / 轨道底 / 分段底 / 分段选中块
//   bandA  —— 压在这一层之上的**墨层**强度（hover / press 的行底；没有就是 0）
//
// 分成 bd + bandA 而不是一个枚举，是因为 hover / press 的强度是**连续**的
// （160ms 淡入）。写死一个 `Hover` 档就等于把中间那些相位当成满强度算 ——
// 而中间那些恰恰是字最暗、底最亮的地方。
//
// ---- v0.35 从四个基底层加到六个，加的两个都是"底叠在底上" ----
//
// 模块框一加，参数区的文字与控件**全部换了一层底**：它们不再坐在面板底上，
// 而是坐在**块底**上（块底 = kInk @ kBlockFillA 压在面板底上）。而分段块
// （LP/BP/HP）又坐在**块底**之上 —— 于是同一个"分段底"有了两个版本。
//
//   `Block`     块底（参数名 / 数值 / 模块标题）
//   `SegBlock`  分段底，**压在块上**（模块里的 LP / BP / HP）
//
// 为什么不把 `Seg` 直接改成"压在块上"就算了：顶栏那个分段控件（OFF / FULL）
// 在**面板底**上，它俩的合成底差约 10 个 RGB —— 差得不多，但"差得不多"
// 正是最危险的那种错：对比度算错一点点，照样绿，而字已经糊了一点点。
// **一层底一个名字**，合成表才对得上，而 `declared_base_layers()` 会
// 强制两边同步（谁加了 `case Bd::X` 而没加合成，那条当场报红）。
enum class Bd { Bg, Block, Track, Seg, SegBlock, SegOn };

struct TextEntry {
    float a;
    Bd bd;
    float bandA;
};

std::vector<TextEntry>& textLog() {
    static std::vector<TextEntry> v;
    return v;
}

// 同一个 (a, bd, bandA) 只记一次。参数行有 41 行、四栏各画一遍 ——
// 不去重的话输出里全是重复行，真出问题时看不出是"哪一处"变了。
void logText(float a, Bd bd, float bandA) {
    auto& v = textLog();
    for (const auto& e : v)
        if (e.a == a && e.bd == bd && e.bandA == bandA) return;
    v.push_back({a, bd, bandA});
}

const char* bdName(Bd bd) {
    switch (bd) {
        case Bd::Bg:       return "bg";
        case Bd::Block:    return "block";
        case Bd::Track:    return "track";
        case Bd::Seg:      return "seg";
        case Bd::SegBlock: return "seg_block";
        case Bd::SegOn:    return "seg_on";
    }
    return "bg";
}

// 行底那一层墨的**实际强度**。集中在这里算，是因为三处绘制点（分段格 / 标题行 /
// 参数行）都要往登记表里报同一个数 —— 各算一遍就会有人算漏 `> 0.001f` 那个守卫，
// 于是"没画底"却报成"底是满强度"，对比度按一个不存在的底去算。
float bandOf(bool pressed, float hov) {
    if (pressed) return kPressA;
    return hov > 0.001f ? kHoverA * hov : 0.0f;
}

// ============================================================================
// ⑤ 分段控件 —— Apple 的**填充式**表达：底 = tertiarySystemFill，选中 = systemGray2。
//    没有描边、没有圆角、分格之间也没有发丝线 —— 选中块自己的边界已经把分格说清楚了。
void drawSegmented(Graphics& g, const PanelState& st, const TabBox& box, int tabIndex,
                   const String* items, int n, int active, bool enabled, float fs) {
    const float cw = box.w / static_cast<float>(n);

    g.setColour(kSegBg);
    g.fillRect(Rectangle<float>{box.x, box.y, box.w, box.h});

    for (int i = 0; i < n; ++i) {
        const bool sel = (i == active) && enabled;
        // 指针反馈：未选中的格子也参与 hover / press。
        // **选中块用的是不透明的 systemGray2**，所以指针反馈的墨层只压在
        // 没被选中的格子上 —— 压在选中块上等于没画（它不透明）。
        // 强度走淡入（v0.33）：`hov` 是 0..1 的连续量，不是布尔。
        const float hov = (enabled && !sel) ? st.hoverFade.of(mkTabCell(tabIndex, i)) : 0.0f;
        const bool prs = enabled && !sel && st.press.tab == tabIndex && st.press.option == i;
        const float cellX = box.x + cw * static_cast<float>(i);
        const Rectangle<float> cell{cellX, box.y, cw, box.h};

        if (sel) {
            g.setColour(kGray2);
            g.fillRect(cell);
        } else if (prs || hov > 0.001f) {
            g.setColour(kInk.withAlpha(prs ? kPressA : kHoverA * hov));
            g.fillRect(cell);
        }

        // 文字压在自己脚下那块面上：选中的压在 systemGray2 上（主内容色），
        // 其余压在 tertiarySystemFill 上（次要色 / 禁用态）。
        // hover 时从 kAMuted 向 kAHoverName 走 —— **走的是同一个 `hov`**，
        // 所以底和字是同步亮的，不会出现"底亮了字还暗着"。
        const float hot = prs ? 1.0f : hov;
        const float a = sel ? kAText
                            : (enabled ? kAMuted + (kAHoverName - kAMuted) * hot : kAOff);
        // 登记对比度：选中的压在 systemGray2 上（不再叠墨层），其余压在
        // tertiarySystemFill 上，底之上还可能有一层 hover / press 的墨。
        logText(a, sel ? Bd::SegOn : Bd::Seg, sel ? 0.0f : bandOf(prs, hov));
        g.setColour(kInk.withAlpha(a));
        g.setFont(uiFont(fs, geom::kTrackUI));
        g.drawText(items[i], cell, Justification::centred, false);
    }
}

// ⑥ 顶栏 —— v0.33 起**只有背景那一组**（模式段与列数段随「只要 ALL」删了）。
void drawBackdropControls(Graphics& g, const PanelState& st);   // 定义在下面 ⑥b

void drawTabs(Graphics& g, const PanelState& st) {
    drawBackdropControls(g, st);
}

// ⑥b 背景控件 —— 顶栏，三件：选择图片 / 落位 / 明暗度。
//
// 视觉语言全部沿用已有的：格子用 `kSegBg` + 选中 `kGray2`（同分段控件），
// 轨道用 `kFill` + 填充 `kInk`（同参数行），文字用两档不透明度。
// **不引入任何新的图形语汇** —— 这块面板从 v0.10 起就没有一条装饰性边框。
void drawBackdropControls(Graphics& g, const PanelState& st) {
    const auto& bd = st.backdrop;
    const bool hasImg = bd.image.isValid();
    const bool on = bd.active();

    // ---- ① 「选择图片」格：有图就显示文件名，没有就显示提示 ----
    {
        const auto box = bgCellBox();
        const float hov = st.hoverFade.of(mkBgSlot());     // 0..1，含淡入
        const bool prs = st.press.bgSlot;
        // 底：从 kSegBg 向一层墨走。`hov` 是连续量，所以这一格是"慢慢亮起来"的。
        g.setColour(prs ? kGray2 : kSegBg);
        g.fillRect(Rectangle<float>{box.x, box.y, box.w, box.h});
        // 按下时**不叠墨层** —— 理由见下面 logText 那一段（会把对比度压到 4.11:1）。
        if (!prs && hov > 0.001f) {
            g.setColour(kInk.withAlpha(kHoverA * hov));
            g.fillRect(Rectangle<float>{box.x, box.y, box.w, box.h});
        }

        const float base = hasImg ? kAMuted : kAOff;
        const float a = prs ? 1.0f : base + (0.92f - base) * hov;
        // 底色：按下时是 systemGray2（不透明），否则是 tertiarySystemFill + 墨层。
        //
        // **按下时不再叠墨层**（v0.33 修的）。这一格按下时底色换成不透明的
        // systemGray2，本来就已经"亮了"；再叠一层 0.10 的墨，等于把这块底
        // 往**文字色**上推 —— 实测文字对比度从 5.97:1 掉到 4.11:1，过不了
        // WCAG AA。而这一层墨在视觉上几乎看不出来（#636366 → #707073）。
        //
        // 这不是特例：`drawSegmented` 里"选中的格子不叠墨层"是同一条规矩
        // （选中的压在 systemGray2 上，墨层只压在没选中的格子上）。
        logText(a, prs ? Bd::SegOn : Bd::Seg, prs ? 0.0f : bandOf(false, hov));
        g.setColour(kInk.withAlpha(a));
        g.setFont(uiFont(geom::kFsTab, geom::kTrackUI));
        // ---- 面板自己写的文案：ASCII + 一个乘号（U+00D7，见 textInventory）----
        // 打包字体只覆盖 ASCII + Latin-1，没有 CJK 字形，所以面板**自己写**的
        // 文案不许出现中文（用户实测截图里 "选择图片" 曾渲染成 éĊ œ Ġå ³/¢）。
        //
        // **但下面这一行是例外，而且必须说清楚**：`bd.name` 是**用户选的图片
        // 文件名** —— 它是用户数据，可能是任何字符。字体覆盖不了它，也没法覆盖。
        // 所以"面板文案一律 ASCII"这条规矩的范围是**面板自己写的字**，
        // 不含用户数据；`textInventory()` 与它对应的断言同样是这个范围。
        const String label = hasImg ? bd.name : String("CHOOSE IMAGE");
        g.drawText(label, Rectangle<float>{box.x + 10.0f, box.y, box.w - 20.0f, box.h},
                   Justification::centredLeft, true);   // true = 放不下就省略号
    }

    // ---- ② [关][全屏] 落位组 ----
    //
    // 三格变两格：树没了，"TREE" 那一格没有意义。
    // **文案一律 ASCII**（面板自己写的字；范围见上面 `bd.name` 那条注释）。
    {
        const String items[] = {"OFF", "FULL"};
        drawSegmented(g, st, bgSegBox(), 0, items, geom::kBgSegN,
                      static_cast<int>(bd.where), true, geom::kFsTab);
    }

    // ---- ③ 明暗度轨道 + 倍率读数 ----
    {
        const auto box = bgTrackBox();
        const float mid = box.y + box.h * 0.5f;
        const float t = brightToTrack(bd.brightness);
        // **有图没图都要有指针反馈。** 这一条是 `check_panel_render.py` 里
        // 那条正向对照（"交互态真的画出来了 ≥ 200 像素"）抓出来的：
        // v0.33 之前 `lit` 挂着 `on &&`，于是没选图时指针落上去**一个像素都不变**
        // —— 而这一格在没图时**照样能拖**（读数是可见的，用户也可以先调好
        // 明暗度再选图）。"能操作却毫无反应"就是小绪说的"没有质感"。
        const float hov = st.hoverFade.of(mkBgBright());
        const bool prs = st.press.bgBright;

        // 轨道底：没有图时用"关着的"那档墨（和参数行的禁用态一致）
        g.setColour(on ? kFill : kInk.withAlpha(kAOff * 0.5f));
        g.fillRect(Rectangle<float>{box.x, mid - geom::kBgTrackH * 0.5f,
                                    box.w, geom::kBgTrackH});
        if (prs || hov > 0.001f) {
            g.setColour(kInk.withAlpha(prs ? kPressA : kHoverA * hov));
            g.fillRect(Rectangle<float>{box.x, mid - geom::kBgTrackH * 0.5f,
                                        box.w, geom::kBgTrackH});
        }

        // 填充段：有图才有东西可填
        if (on) {
            const float fw = jmax(geom::kBgTrackH, box.w * t);
            g.setColour(kInk.withAlpha(0.80f + 0.20f * jmax(hov, prs ? 1.0f : 0.0f)));
            g.fillRect(Rectangle<float>{box.x, mid - geom::kBgTrackH * 0.5f,
                                        fw, geom::kBgTrackH});
        }

        // 基准刻度（1.0×）—— **与参数行的出厂值刻度同一套画法**：
        // 轨道**下面**的一截短尺，不是站在轨道正中的竖线。
        //
        // 这一处以前是 `kBgTrackH * 4.4` 高的竖线，站在轨道正中 —— 而 1.0×
        // 在几何映射下**正好是轨道的中点**，于是它看起来就是一根"永远不动的指针"，
        // 和参数条那个被小绪点名的假指针是同一个毛病（v0.32.4 修的是参数条）。
        // 既然参数条已经改成"短尺在下、真指针随值动"，这里必须跟着改 ——
        // 否则同一块面板上出现两种"刻度"，而小绪要的是「所有排版都必须要整齐」。
        {
            const float d = brightToTrack(1.0f);
            g.setColour(kInk.withAlpha(kATick));
            g.fillRect(Rectangle<float>{box.x + box.w * d,
                                        mid + geom::kBgTrackH * 1.9f,
                                        1.0f, 2.0f});
        }

        // 读数。没图 / 关着的时候摊平（Apple 的禁用态是"摊平"不是"变暗"）。
        // 小于 1 给两位小数 —— 0.25 显示成 "0.2×" 就看不出来它是最小值了。
        //
        // 读数也吃 hover 强度：轨道和它的读数是**一个控件**，指针落在轨道上
        // 读数却纹丝不动的话，会显得是两件东西。
        const auto rb = bgReadBox();
        const String readout = (bd.brightness < 1.0f ? String(bd.brightness, 2)
                                                     : String(bd.brightness, 1)) + "×";
        const float rbase = on ? kAText : kAOff;
        const float ra = rbase + (1.0f - rbase) * (prs ? 1.0f : hov);
        // 读数坐在面板底上（轨道右边、没有墨层）。
        logText(ra, Bd::Bg, 0.0f);
        g.setColour(kInk.withAlpha(ra));
        g.setFont(dataFont(geom::kFsValue, geom::kTrackData));
        g.drawText(readout, Rectangle<float>{rb.x, rb.y, rb.w, rb.h},
                   Justification::centredRight, false);
    }
}

// ⑦ 顶栏品牌标（v0.36）。
//
// v0.35 及以前这里画的是视图标题 `Trane`（17px 满墨）与副标题
// `<n> CONTROLS`（11px、0.60 墨），左对齐在 `kPaneX0`。
// 2026-09-30 用户要求：**删掉这两行文字，换成上传的金属 logo**，并且
// "放在左边有点怪，**放在右边吧**"。落位常量见 TranePanel.h 的 `kLogoH`。
//
// ---- 删掉的两样东西，以及为什么没有"等价替代" ----
//
//   ① 标题字符串 `"Trane"`。它本来就是**冗余**的 —— 插件名已经写在宿主给的
//      窗口标题栏上，面板上再写一遍不提供任何新信息。
//   ② 副标题 `<n> CONTROLS`。这个是**算出来的**（数一遍四栏里实际画出来的
//      参数行），v0.30–v0.35 期间它是一条真断言：文字说的行数必须等于画出来的
//      行数。删掉它 = **删掉那条断言**（`tests/test_ui_design.py` 里对应的节点
//      一起删，见提交说明）。留着字符串而不留断言才是更坏的选择：
//      那会变成一句没人核对的话。
//
// ---- 为什么不用 `setOpacity` 之类改亮度 ----
// 资产本身已经提过亮（gamma 0.70，见 PROVENANCE.md），因为面板顶栏那块底色
// 是**纯黑**，原始金属在纯黑上平均亮度只有 81 出头、熔滴基本糊掉。
// 亮度烤进资产、不在运行时乘：乘一次要逐像素走一遍，而它每帧都一样。
void drawBrandMark(Graphics& g, PanelCache& cache) {
    const auto& bm = brandMark();
    if (! bm.ok) return;   // 素材坏了就什么都不画（和 TraneVideo 同规矩）

    const float h = geom::kLogoH;
    const float w = h * static_cast<float>(bm.w) / static_cast<float>(bm.h);

    // 设备缩放：用 cache 里那个数（外层 Graphics 上带着的就是它）。
    // `paint()` 之前一定调过 `cache.update()`，而它要求 `ensure()` 先跑过。
    const float s = cache.backdropScale > 0.0f ? cache.backdropScale : 1.0f;

    // 目标矩形吸附到**整数设备像素**再换算回逻辑坐标。
    // 规矩的来路见 TranePanel.h 的 PanelCache 注释：带分数偏移的贴图会退回
    // 重采样路径，实测慢约 70 倍（那条教训当时是给底图的，这里尺寸小得多，
    // 但吸附一次不要钱，没理由不吸）。
    const int dw = jmax(1, roundToInt(w * s));
    const int dh = jmax(1, roundToInt(h * s));
    const int px = roundToInt((geom::kLogoRight - w) * s);
    const int py = roundToInt((geom::kLogoCY - h * 0.5f) * s);

    // 只在设备尺寸变化时重算 —— 面板尺寸锁死，实际上只算一次。
    if (! cache.logoScaled.isValid() || cache.logoW != dw || cache.logoH != dh) {
        cache.logoScaled = brandMarkImage(dw, dh);
        cache.logoW = dw;
        cache.logoH = dh;
    }
    if (! cache.logoScaled.isValid()) return;

    g.drawImage(cache.logoScaled,
                Rectangle<float>{static_cast<float>(px) / s, static_cast<float>(py) / s,
                                 static_cast<float>(dw) / s, static_cast<float>(dh) / s},
                RectanglePlacement::stretchToFit, false);
}

// ⑦b 模块框（v0.35）—— 一个底 + 一条边，**没有投影、没有圆角阴影、没有彩色**。
//
// 参照图（Lux Cache 的 petri）里，每个分组是一张卡：1px 发丝边 + 略亮底 +
// 约 10px 圆角。它跟 VCV Rack 的关系是"取一层"：**模块是独立面板**这件事
// 拿过来，拟物（金属面板、螺丝、彩色丝印）一概不要 —— 小绪要的是
// 「Lux Cache 感觉版本的」模块感。
//
// 三个细节是**想过的**，不是顺手：
//
//  ① **底是半透明的**（kInk @ 0.055），不是不透明的 #1C1C1E。
//     不透明的话，用户上传的背景图会被十块板子切成碎片 —— 图只留在
//     框与框之间的缝里。半透则图从框里透出来、被轻轻提亮，
//     而"这里有一张卡"照样读得出来。
//
//  ② **框线内缩 0.5px 再描**，于是 1px 的线整根落在矩形内、且在 2× 屏上
//     正好压在设备像素网格上。不缩的话线会跨在边界上，两侧各半像素，
//     抗锯齿把它抹成 2px 的灰雾 —— "发丝边"变成"糊边"。
//
//  ③ **先铺满所有框，再画行。** 顺序不能反：行底的 hover / press 墨层
//     要压在块底**之上**（0.04 的墨压在 0.055 的块底上），反过来就看不见了。
//     所以绘制是两遍：`drawInspector` 先走一遍框，再走一遍行。
void drawBlock(Graphics& g, const ColumnLayout& col, const BlockLayout& bl) {
    const Rectangle<float> rect{col.x, bl.top, col.w, bl.bottom - bl.top};

    g.setColour(kInk.withAlpha(kBlockFillA));
    g.fillRoundedRectangle(rect, geom::kBlockR);

    g.setColour(kInk.withAlpha(kBlockEdgeA));
    g.drawRoundedRectangle(rect.reduced(0.5f), geom::kBlockR, 1.0f);
}

// ⑧ 模块标题 —— **有开关参数的模块，标题本身就是开关**：点亮 = 开，点灭 = 关。
//    状态只在一个地方表达（名称亮度 + 紧跟名字的方块），既省一整行，
//    也不会出现"标题说开着、开关说关着"这种自相矛盾。
//
//    但 ruin / space / out 三个模块压根没有开关参数（41 参数 + 7 开关），
//    所以它们只画标题、不画状态方块 —— **不许假装有开关**。
void drawModuleHead(Graphics& g, const PanelState& st, const RowLayout& r,
                    const ColumnLayout& col, bool active, float breath) {
    const String name = String(kNodes[r.node].module).toUpperCase();
    const float fs = col.fsTitle;
    const float mid = r.mid;
    // v0.35：标题在**框内**。`col.x` 是框边，内容从 `col.x + kBlockPadX` 起 ——
    // 于是标题、参数名、数值共用同一条内容准线。
    const float cx = col.x + geom::kBlockPadX;
    const float cw = col.w - 2.0f * geom::kBlockPadX;

    // 指针反馈。v0.33：树删了，**模块名就是唯一的开关落点**，所以这里直接读
    // `Mark::control` —— 不再有"树上那个圆"需要跟标题行对齐。
    //
    // `nodeSwitchControl` 对 ruin / space / out 返回 -1，而 -1 **恰好就是
    // `Mark::control` 表示"什么都没指"的值** —— 于是这三个模块天然不会亮。
    // 这不是巧合，是 `Mark` 用 -1 当空值换来的：`nodeHasSwitch` 那个判断
    // 在这里可以省掉。**但 `>= 0` 的守卫不能省** —— 少了它，"什么都没指"
    // 就等于"指着没有开关的模块"，三个模块会一起亮。
    //
    // 反馈仍然只改颜色：一条与参数行同高的极淡墨层，不动任何几何。
    const int sw = nodeSwitchControl(r.node);
    const float hov = (sw >= 0) ? st.hoverFade.of(mkControl(sw)) : 0.0f;
    const bool pressed = (sw >= 0) && st.press.control == sw;
    if (pressed || hov > 0.001f) {
        const float a = pressed ? kPressA : kHoverA * hov;
        const float bh = col.pitch * geom::kRowBand;
        g.setColour(kInk.withAlpha(a));
        g.fillRect(Rectangle<float>{cx - geom::kGap * 0.5f, mid - bh * 0.5f,
                                    cw + geom::kGap, bh});
    }

    // 模块名**就是开关**，所以关闭态也必须看得清 —— 看不清就点不着。
    float headOp = active ? kAText : kAOff;
    if (pressed) {
        headOp = 1.0f;
    } else if (hov > 0.0f) {
        // 目标亮度：灭的标题要能提亮到 kAHoverName；**已经 1.0 的标题不再变**
        // （往 0.80 走会让亮着的标题在指针移上去时变暗 —— 那就是"越悬停越暗"）。
        const float target = jmax(headOp, kAHoverName);
        headOp += (target - headOp) * hov;
    }

    g.setColour(kInk.withAlpha(headOp));
    g.setFont(uiFont(fs, geom::kTrackHead));
    // v0.35：标题坐在**块底**上，不再坐在面板底上。
    logText(headOp, Bd::Block, bandOf(pressed, hov));
    g.drawText(name,
               Rectangle<float>{cx, mid - fs, col.labelW + fs * 4.0f, fs * 2.0f},
               Justification::centredLeft, false);

    if (!nodeHasSwitch(r.node)) return;

    // 方块**紧跟名字**，不甩到列的最右边 —— 否则在宽列里离名字两百多像素，
    // 读不出"这个名字就是开关"。
    const float side = fs * 0.78f;
    const float bx = cx + static_cast<float>(name.length()) * geom::kLabelW * fs + geom::kGap;
    if (active) {
        g.setColour(kInk.withAlpha(0.80f + 0.20f * breath));
        g.fillRect(Rectangle<float>{bx, mid - side * 0.5f, side, side});
    } else {
        g.setColour(kFill);
        g.fillRect(Rectangle<float>{bx, mid - side * 0.5f, side, side});
    }
}

// ⑨ 参数行：名称 / 轨道 / 数值，三段之间只留一个 kGap。
//
//    名称 = 11pt（次要色）—— 名称是辅助信息，Apple 里辅助信息一律降一级；
//    数值 = 12pt（主内容色）—— 在插件里数值才是用户真正要读的东西，层级反过来。
//    轨道 = systemFill，当前值 = 主内容色填充，**没有圆形把手**（只靠颜色编码）。
// 旋钮（v0.34）。
//
// 画在**轨道那一段的正中**，直径由字号定 —— 于是旋钮行与条形行共用同一条基线、
// 同一个值列，**网格一点没动，只有中间那件东西换了形状**。这是"按需分配形态"
// 能不破坏"整齐"的关键：换的是画笔，不是排版。
//
// 三个元素，一个不多：
//   · 底环 —— 270° 整圈（`kFill`）："这里有一个控件"；
//   · 值弧 —— 起点顺时针到当前值，**不透明度与条形填充同一档**（`0.55 + 0.15×breath`
//     / 关着 0.22）："拧到哪儿了"。用同一档是为了让"亮着 / 关着"在两种形态下
//     读起来是同一种亮；
//   · 末端点 —— 满墨（关着 0.40，与条形指针同档）。值到两端时弧的末端会贴到
//     开口上，光看弧容易含糊，一个点把它钉住。
//
// **不画出厂值刻度。** 条形那边轨道下面有一截 2px 的尺；旋钮上没地方放第二把尺
// —— 弧已经占满 270°，再插一根只会变成"又一个指针"（v0.32 就踩过这个坑，
// 小绪的原话是「参数条指针是假的」）。双击复位仍然可用，只是不常显。
//
// 对照度登记表**不受影响**：旋钮不画字，没有新的文字对要复算。
void drawKnob(Graphics& g, const ColumnLayout& col, float tx, float mid,
              float nv, bool active, float breath) {
    const float r = geom::kKnobDia * 0.5f;
    const Point<float> c{tx + col.trackW * 0.5f, mid};
    const auto deg = [](float d) { return d * MathConstants<float>::pi / 180.0f; };
    const float a = geom::kKnobStart + geom::kKnobSweep * jlimit(0.0f, 1.0f, nv);

    // 底环：整段 270°，恒画（关着的模块也要看得见控件在哪 —— 与条形同一个理由）
    Path ring;
    ring.addCentredArc(c.x, c.y, r, r, 0.0f, deg(geom::kKnobStart),
                       deg(geom::kKnobStart + geom::kKnobSweep), true);
    g.setColour(kFill);
    g.strokePath(ring, PathStrokeType(geom::kKnobStroke, PathStrokeType::curved,
                                      PathStrokeType::rounded));

    // 值弧：0 的时候不画 —— 长度为 0 的路径在两端会被描成一个点，看起来像"值在两端"
    if (nv > 0.001f) {
        Path arc;
        arc.addCentredArc(c.x, c.y, r, r, 0.0f, deg(geom::kKnobStart), deg(a), true);
        g.setColour(kInk.withAlpha(active ? (0.55f + 0.15f * breath) : 0.22f));
        g.strokePath(arc, PathStrokeType(geom::kKnobStroke, PathStrokeType::curved,
                                         PathStrokeType::rounded));
    }

    // 末端点。角度 a 处的方向向量 = (sin a, −cos a)（a 从 12 点起算、顺时针）。
    // 半径取 `r − 半个笔画`，点才落在环的中线上而不是骑在环上。
    const float rad = deg(a);
    const float rr = r - geom::kKnobStroke * 0.5f;
    const Point<float> p{c.x + rr * std::sin(rad), c.y - rr * std::cos(rad)};
    g.setColour(kInk.withAlpha(active ? 1.0f : 0.40f));
    g.fillEllipse(p.x - geom::kKnobDotR, p.y - geom::kKnobDotR,
                  geom::kKnobDotR * 2.0f, geom::kKnobDotR * 2.0f);
}

void drawParamRow(Graphics& g, const PanelState& st, const RowLayout& r,
                  const ColumnLayout& col, bool active, float breath, RowState state,
                  float hoverAmt) {
    const auto& c = kControls[r.control];
    const float nv = jlimit(0.0f, 1.0f, st.value[r.control]);
    const float fsN = col.fsName;
    const float fsV = col.fsValue;
    // v0.35：三段（名 / 轨道 / 数值）全部在**框内**。`col.x` / `col.w` 是框边，
    // 内容从 `col.x + kBlockPadX` 起、宽 `col.w − 2×kBlockPadX`。
    const float cx = col.x + geom::kBlockPadX;
    const float cw = col.w - 2.0f * geom::kBlockPadX;
    const float tx = cx + col.labelW + geom::kGap;
    const float mid = r.mid;

    // ---- 行底（hover / press）----
    // 整行一层极淡的墨，先画，压在文字和轨道下面。
    //
    // hover 的强度是**连续**的（`hoverAmt` 0..1，含 160ms ease-out 的淡入）。
    // press 视作满强度 —— 按下那一刻指针一定还在这一行上，`hoverAmt` 本来就是 1；
    // 而且 press 是瞬时反馈，不走淡入（见 kMotionFast 的注释）。
    const float ha = (state == RowState::Press) ? 1.0f : hoverAmt;
    // 行底那一层墨的**实际强度** —— 绘制与登记共用它，于是"画了多少"和
    // "报了多亮"不可能分叉。`bandOf` 里带着 `> 0.001f` 那个守卫。
    const float bandA = bandOf(state == RowState::Press, ha);
    if (ha > 0.001f) {
        g.setColour(kInk.withAlpha(bandA));
        const float bh = col.pitch * geom::kRowBand;
        g.fillRect(Rectangle<float>{cx - geom::kGap * 0.5f, mid - bh * 0.5f,
                                    cw + geom::kGap, bh});
    }

    // 聚焦只保留输入语义（键盘导航 / 参数微调），不再绘制蓝色聚焦环。
    // 用户 dogfood 反馈：调参数时不应出现蓝框；焦点不是装饰。

    // 参数名随状态提亮：hover 走到 0.80 / press 到 1.00。
    // **不动位置，只动不透明度** —— 而且和行底共用同一个 `ha`，
    // 于是"底亮到三成、字也亮到三成"是同步的，不会一个先到。
    float aName = active ? kAMuted : kAOff;
    if (state == RowState::Press) aName = kAText;
    else if (ha > 0.0f) aName += (kAHoverName - aName) * ha;

    g.setColour(kInk.withAlpha(aName));
    g.setFont(uiFont(fsN, geom::kTrackUI));
    // v0.35：参数名坐在**块底**上（不再是面板底）。
    logText(aName, Bd::Block, bandA);
    g.drawText(String(c.name).toUpperCase(),
               Rectangle<float>{cx, mid - fsN, col.labelW, fsN * 2.0f},
               Justification::centredLeft, false);

    if (c.fmt == Fmt::Choice) {
        // LP / BP / HP 分段块。模块关着时**不画选中块** ——
        // Apple 的禁用控件是"摊平"的，不是"变暗的"。
        const float th = choiceHeight(col);
        const float cw3 = col.trackW / 3.0f;
        const int pos = choiceIndex(nv);

        g.setColour(kSegBg);
        g.fillRect(Rectangle<float>{tx, mid - th * 0.5f, col.trackW, th});
        if (active) {
            g.setColour(kGray2);
            g.fillRect(Rectangle<float>{tx + cw3 * static_cast<float>(pos),
                                        mid - th * 0.5f, cw3, th});
        }
        for (int i = 0; i < 3; ++i) {
            const bool sel = (i == pos && active);
            const float ca = sel ? kAText : aName;
            g.setColour(kInk.withAlpha(ca));
            g.setFont(uiFont(fsV * 0.82f, geom::kTrackUI));
            // 选中的那一格压在 systemGray2 上（不透明），其余压在
            // tertiarySystemFill 上 —— 而那一层下面还可能有行底的墨。
            //
            // v0.35：**未选中的格子坐在块底之上**，所以是 `Bd::SegBlock`，
            // 不是顶栏那个 `Bd::Seg`（那个在面板底上）。见 `enum class Bd`。
            logText(ca, sel ? Bd::SegOn : Bd::SegBlock, sel ? 0.0f : bandA);
            g.drawText(kChoices[i],
                       Rectangle<float>{tx + cw3 * static_cast<float>(i), mid - fsV, cw3, fsV * 2.0f},
                       Justification::centred, false);
        }
    } else if (isKnob(r.control)) {
        // 旋钮：中间那一段换一支画笔，值列与名称列**一格都没动**。
        drawKnob(g, col, tx, mid, nv, active, breath);
    } else {
        const float th = trackHeight(col);

        g.setColour(kFill);
        g.fillRect(Rectangle<float>{tx, mid - th * 0.5f, col.trackW, th});

        // ---- 出厂值刻度：轨道**下面**的一截短尺，不是指针 ----
        //
        // 这里原先是一条 4.4× 轨道高的竖线，站在轨道正中。它比轨道高得多，
        // 看起来就是一根指针 —— 而它画在 `defaultNormalised()` 上，**永远不动**。
        // 小绪的原话是「参数条指针是假的」：他看到的"指针"其实是出厂值参照线；
        // 而真正跟着值走的那根填充条因为只改颜色、不加把手，反而看不出来。
        //
        // 修法不是"再画一根会动的线"，而是**先把误会拆掉**：参照线挪到轨道下面、
        // 只留 2px 高。尺子上的刻度没人会当指针用。
        // 教训：判断"这看起来像什么"要比判断"我打算让它是什么"更用力。
        //
        // 位置是 `mid + th*1.6` 而不是紧贴轨道下沿：指针的下摆到 `mid + th`，
        // 刻度若从 `mid + th*0.5 + 1.5` 起，两者只差 0.45px —— 会**黏在一起**，
        // 看起来像一根被拉长的指针。留出 2px 的空隙，它们才是两件东西。
        const float dx = tx + col.trackW * defaultNormalised(r.control);
        g.setColour(kInk.withAlpha(kATick));
        g.fillRect(Rectangle<float>{dx, mid + th * 1.9f, 1.0f, 2.0f});

        // ---- 当前值：填充条 + **真的指针** ----
        // 填充留 th 的最小宽度：值为 0 时也留一丝颜色，否则"零"和"没数据"分不清。
        // 指针则必须画在**真值位置**上、**不加最小宽度** —— 加了的话指针在 0 处
        // 会离开轨道左端，"零"看起来就不是零了。
        // 内缩 0.5 / 1.5 是为了让这 1px 宽的线**整根都在轨道里**：贴到边上的话
        // 一半在轨道外，值到两端时指针会显得"掉出去"。
        const float fw = jmax(th, col.trackW * nv);
        const float px = tx + jlimit(0.5f, jmax(0.5f, col.trackW - 1.5f), col.trackW * nv);

        // ---- 模块关着时**仍然画**填充和指针，只是压暗 ----
        //
        // 原先关着的模块走的是 `else` 分支：拿 `kFill`（和轨道底色同一个颜色）
        // 盖一遍 —— 等于**什么都没画**。三条理由说明那是错的：
        //
        //   ① 禁用控件也该看得见自己的位置。Apple 的禁用滑块照样显示滑块在哪，
        //      "摊平"是给**分段选择块**用的（那种块不显示位置也不丢信息），
        //      连续参数不一样 —— 不画就等于"这个参数没有值"。
        //   ② 这些行**是可以拖的**（mouseDown 不检查模块开关）。画不出来，
        //      用户一拖就"没反应"，只是数值文字在变。
        //   ③ 出厂状态下 10 个模块有 8 个是关的 —— 不画的话，插件一打开就是
        //      一片死条，而唯一像指针的东西（旧版那条 4.4× 轨道高的出厂值刻度）
        //      永远不动。**这正是小绪说"参数条指针是假的"的来路。**
        //
        // 压暗的分寸：填充 0.22（能看出长度，但明显比亮着的弱）；
        // 指针 0.40（位置读得出，又不抢亮着的那几行的注意力）。
        g.setColour(kInk.withAlpha(active ? (0.55f + 0.15f * breath) : 0.22f));
        g.fillRect(Rectangle<float>{tx, mid - th * 0.5f, fw, th});

        // 指针：**2px 宽、3 倍轨道高、亮着时满墨**。
        //
        // 尺寸是看着渲染图定的，不是拍脑袋：第一版做的是 1px 宽、2 倍高，
        // 数值测试全绿（它确实会动），但**放大看根本找不着** —— 值到两端时
        // 指针压在填充的边缘上，2px 的高差被抗锯齿抹平了。
        // 3 倍高给出上下各约 4px 的突出，满墨又比填充亮一档，两端也认得出。
        g.setColour(kInk.withAlpha(active ? 1.0f : 0.40f));
        g.fillRect(Rectangle<float>{px, mid - th * 1.3f, 2.0f, th * 2.6f});
    }

    const String vt = formatShort(r.control, nv);
    if (vt.isNotEmpty()) {
        const float va = active ? kAText : kAOff;
        g.setColour(kInk.withAlpha(va));
        g.setFont(dataFont(fsV, geom::kTrackData));
        // v0.35：数值也坐在块底上。右对齐到**框内**右缘（`cx + cw`）。
        logText(va, Bd::Block, bandA);
        g.drawText(vt,
                   Rectangle<float>{cx, mid - fsV, cw, fsV * 2.0f},
                   Justification::centredRight, false);
    }
}

// ⑩ 检查器整体
void drawInspector(Graphics& g, const PanelState& st, const InspectorLayout& L,
                   float breath) {
    // ---- 第一遍：所有模块框 ----
    //
    // **必须先走完这一遍再画行**：行底的 hover / press 墨层（kInk @ 0.04）
    // 要压在块底（kInk @ 0.055）**之上**。顺序反过来的话，框会把行底盖掉 ——
    // 而"悬停没反应"正是最容易被忽略的坏法（`check_panel_render.py` 里
    // 那条"交互态真的画出来了 ≥ 200 像素"的正向对照打的就是它）。
    for (int i = 0; i < L.blockCount; ++i) {
        const auto& bl = L.block[i];
        drawBlock(g, L.column[bl.column], bl);
    }

    // ---- 第二遍：行 ----
    for (int i = 0; i < L.rowCount; ++i) {
        const auto& r = L.row[i];
        const auto& col = L.column[r.column];
        const bool active = moduleIsOn(r.node, st);

        if (r.control < 0) {
            drawModuleHead(g, st, r, col, active, breath);
        } else {
            drawParamRow(g, st, r, col, active, breath, rowStateOf(st, r.control),
                         hoverAmtOf(st, r.control));
        }
    }
}

// ---------------------------------------------------------------------------
// 背景图：落位 / 烘焙
// ---------------------------------------------------------------------------
// 落位区。**两个都是编译期常量**（理由见 TranePanel.h：跟着分割线走会让
// 每拖一帧就重做一次源图缩放，实测 30.9 ms/帧，而羽化早就把边缘化开了，
// 换来的视觉精度是零）。
// 背景图的落位区 —— **参数区本身**，而且不含 `where` 参数了。
//
// v0.33：树区那一档删了（`BgWhere` 只剩 Off / Full）。既然只剩一个落位区，
// "落位区"这个概念就退化成了"内容区"，于是这个函数不再需要参数 ——
// 它现在是个常量矩形。**参数删掉是刻意的**：留着 `BgWhere` 入参就等于
// 留着一个"以后可能有两个区"的暗示，而事实是只有一个。
//
// 顺带：v0.31 那版"落位取分割线能拖到的最左位置"的理由（拖分割线不触发重烤）
// 也一并消失了 —— 分割线没了，这条不变量由"没有分割线"本身保证。
Rectangle<float> bgRegion() {
    return { geom::kPaneX0, 0.0f, geom::kPaneW, geom::kBaseH };
}

// 线性斜坡：两端各 n 个像素从 0 爬到 1。**不是可选的美化** ——
// 素材边缘是硬的，直接贴上去就是两条竖切痕（"卡片感"），
// 而这块面板从 v0.10 起就没有一条装饰性边框。
void featherRamp(std::vector<float>& out, int len, int n) {
    out.assign(static_cast<size_t>(len), 1.0f);
    n = jlimit(0, len / 2, n);
    if (n <= 0) return;
    for (int i = 0; i < n; ++i) {
        const float v = static_cast<float>(i) / static_cast<float>(n);
        out[static_cast<size_t>(i)] = v;
        out[static_cast<size_t>(len - 1 - i)] = v;
    }
}

// 把用户选的图烤成一张**和目标区域同尺寸**的成品（物理分辨率）。
//
//   ① 等比放大到**铺满**区域（cover），多余的裁掉 —— 绝不拉伸变形；
//   ② 亮度固定按**上限**（kBgPeakBase × kBgBrightMax）落盘；
//   ③ 四边羽化，融进黑底。
//
// **明暗度不在这里做**，它由调用方在合成时用 `setOpacity` 施加（见 rebuildBackdrop）。
// 因为这一步会被"换图 / 换落位 / 改窗口尺寸"触发，而拖明暗度**不该**触发它 ——
// 源图缩放实测 30.9 ms（3000×3000 → 2.85M 像素），拖起来必卡。
//
// ①用 JUCE 的高质量重采样（只做一次，不在每帧路径上）；
// ②③走**定点整数**逐行直写。而且**不许调 setPixelColour / getPixelColour** ——
// 那是 2M 次虚函数调用。
Image bakeBackdrop(const juce::Image& src, Rectangle<float> region, float scale) {
    const int w = jmax(1, roundToInt(region.getWidth() * scale));
    const int h = jmax(1, roundToInt(region.getHeight() * scale));

    Image out{Image::ARGB, w, h, true};

    const float srcW = static_cast<float>(src.getWidth());
    const float srcH = static_cast<float>(src.getHeight());
    const float dstAr = static_cast<float>(w) / static_cast<float>(h);

    // 从源图里取**居中的最大内接矩形**，比例与目标一致 → 画上去正好铺满且不变形。
    float sw = srcW, sh = srcW / dstAr;
    if (sh > srcH) { sh = srcH; sw = srcH * dstAr; }
    const float sx = (srcW - sw) * 0.5f;
    const float sy = (srcH - sh) * 0.5f;

    {
        Graphics g{out};
        g.setImageResamplingQuality(Graphics::highResamplingQuality);
        g.drawImage(src, 0.0f, 0.0f, static_cast<float>(w), static_cast<float>(h),
                    sx, sy, sw, sh);
    }

    // 亮度：峰值 = 基准 × 上限。8.8 定点（256 = 1.0）。
    const float gain = geom::kBgPeakBase * geom::kBgBrightMax / 255.0f;
    const int nFeather = roundToInt(geom::kBgFeather * scale);

    std::vector<float> rx, ry;
    featherRamp(rx, w, nFeather);
    featherRamp(ry, h, nFeather);

    std::vector<uint32_t> kx(static_cast<size_t>(w));
    for (int x = 0; x < w; ++x)
        kx[static_cast<size_t>(x)] = static_cast<uint32_t>(jlimit(0.0f, 256.0f, gain * rx[static_cast<size_t>(x)] * 256.0f));

    Image::BitmapData d{out, Image::BitmapData::readWrite};
    for (int y = 0; y < h; ++y) {
        auto* px = reinterpret_cast<PixelARGB*>(d.getLinePointer(y));
        const auto ky = static_cast<uint32_t>(jlimit(0.0f, 256.0f, ry[static_cast<size_t>(y)] * 256.0f));
        for (int x = 0; x < w; ++x) {
            const auto k = (ky * kx[static_cast<size_t>(x)]) >> 8;   // ≤ 256
            px[x].setARGB(255,
                          static_cast<uint8_t>((px[x].getRed()   * k) >> 8),
                          static_cast<uint8_t>((px[x].getGreen() * k) >> 8),
                          static_cast<uint8_t>((px[x].getBlue()  * k) >> 8));
        }
    }
    return out;
}

// 明暗度：在**已经贴好的那一块**像素上原地乘一个系数（8.8 定点，256 = 1.0）。
//
// 为什么不用 `setOpacity` + `drawImage` 一步到位：JUCE 的**带 alpha** 图像渲染
// 走的是通用路径（浮点混合），实测 2880×1440 上 10.7 ms；这个整数循环 2.3 ms。
// 而且**不许调 setPixelColour** —— 那是逐像素虚函数调用。
//
// 只碰 region 那一段：区域外的像素是面板底，乘进去会把整块底也变灰。
void tintRegion(Image& img, Rectangle<float> region, float s, float brightness) {
    const uint32_t k = static_cast<uint32_t>(
        jlimit(0.0f, 256.0f, brightness / geom::kBgBrightMax * 256.0f));

    Image::BitmapData d{img, Image::BitmapData::readWrite};
    const int x0 = jlimit(0, d.width,  roundToInt(region.getX() * s));
    const int x1 = jlimit(0, d.width,  x0 + roundToInt(region.getWidth()  * s));
    const int y0 = jlimit(0, d.height, roundToInt(region.getY() * s));
    const int y1 = jlimit(0, d.height, y0 + roundToInt(region.getHeight() * s));

    for (int y = y0; y < y1; ++y) {
        auto* px = reinterpret_cast<PixelARGB*>(d.getLinePointer(y)) + x0;
        for (int x = x0; x < x1; ++x, ++px)
            px->setARGB(255,
                        static_cast<uint8_t>((px->getRed()   * k) >> 8),
                        static_cast<uint8_t>((px->getGreen() * k) >> 8),
                        static_cast<uint8_t>((px->getBlue()  * k) >> 8));
    }
}

// 静态底：面板底 + 背景图 + 22 条骨架点线。**只在尺寸 / 背景规格变化时重烤。**
void rebuildBackdrop(PanelCache& cache, const PanelState& st) {
    const float s = cache.backdropScale;
    const int pw = roundToInt(geom::kBaseW * s);
    const int ph = roundToInt(geom::kBaseH * s);

    if (!cache.backdrop.isValid() || cache.backdrop.getWidth() != pw
        || cache.backdrop.getHeight() != ph)
        cache.backdrop = Image{Image::ARGB, pw, ph, true};

    Graphics g{cache.backdrop};
    g.addTransform(AffineTransform::scale(s));
    g.setImageResamplingQuality(Graphics::lowResamplingQuality);

    g.setColour(kBg);
    g.fillAll();

    // 背景图：**面板底之上、所有文字之下**。参数行 / 模块标题 / 顶栏都在它上面，
    // 所以文字永远压在图上，不会被图盖住。
    // v0.33 之前这里还有一句"骨架点线必须留在图上面"（小绪 09-29 的原话），
    // 骨架删了，这条分层约束自然消失 —— 现在整块 backdrop 上只剩"图"一层。
    const auto region = st.backdrop.active() ? bgRegion() : Rectangle<float>{};
    if (!region.isEmpty()) {
        const void* id = st.backdrop.image.getPixelData().get();
        const int wantW = jmax(1, roundToInt(region.getWidth() * s));
        const int wantH = jmax(1, roundToInt(region.getHeight() * s));

        // ① 缩放 + 羽化 —— 最贵的一步，只在（源图 / 落位 / 尺寸）变化时做。
        //    注意比的是 cache 里**上一次**的规格，所以要在赋值之前比。
        // 注意 `where` **不在**失效条件里 —— 落位区是常量（`bgRegion()` 无参），
        // 所以 Off → Full 时同一张图、同一个尺寸的 bdScaled 可以原样复用。
        // v0.33 之前这里有一项 `bdWhere`，因为那时落位区跟着 where 变；
        // 树删了之后它成了一条永远为真的判据，留着只会让人以为落位还会变。
        if (cache.bdImage != id || cache.bdW != wantW || cache.bdH != wantH) {
            cache.bdScaled = bakeBackdrop(st.backdrop.image, region, s);
            cache.bdImage = id;
            cache.bdW = wantW;
            cache.bdH = wantH;
        }

        // ② 1:1 不透明贴图 —— 尺寸正好相等，走的是快速路径。
        g.drawImage(cache.bdScaled, region);

        // ③ 明暗度 —— 原地乘，不重做①。
        //    bdScaled 是按**上限**烤的，所以这里乘 brightness / 上限。
        tintRegion(cache.backdrop, region, s, st.backdrop.brightness);
    }

    cache.bakedImage = st.backdrop.image.getPixelData().get();
    cache.bakedWhere = static_cast<int>(st.backdrop.where);
    cache.bakedBright = st.backdrop.brightness;
    cache.backdropValid = true;
}

}  // namespace

void PanelCache::ensure(float scale) {
    // 量化到 0.5 的整数倍（**向上**取整），上限 2×。
    // 不量化的话，拖窗口边缘每动一像素就要重建一次底图，拖拽会卡。
    const float want = jlimit(1.0f, 2.0f, std::ceil(scale * 2.0f) * 0.5f);

    // v0.33：`deviceScale` 与光晕精灵一起删了 —— 它唯一的作用是给光晕贴图
    // 做整数像素吸附，树删了就没有住户。
    //
    // 值得记住的是 `want` 与"精确缩放"**为什么曾经是两个数**：
    // `want` 量化到 0.5 的整数倍，为的是别让拖窗口每动一像素就重烤 4.1 Mpx 的
    // 底图；而光晕只有 245² 那么大，烤一次 0.3 ms，不值得为它量化 ——
    // 量化了就吸附不准。现在只剩 `want` 一个数，这段区分没有住户了。

    if (backdrop.isValid() && std::abs(backdropScale - want) <= 0.01f) return;

    backdropScale = want;
    backdropValid = false;
}

void PanelCache::update(const PanelState& st) {
    if (backdropScale <= 0.0f) return;   // 还没 ensure 过
    // 尺寸没变**并且**背景规格没变，才敢复用。少了后面这半句，
    // 换图 / 换落位 / 拖明暗度都会拿着旧底图当成品。
    if (backdropValid
        && bakedImage == st.backdrop.image.getPixelData().get()
        && bakedWhere == static_cast<int>(st.backdrop.where)
        && std::abs(bakedBright - st.backdrop.brightness) < 1.0e-4f)
        return;
    rebuildBackdrop(*this, st);
}

void PanelCache::release() {
    backdrop = {};
    backdropScale = 0.0f;
    backdropValid = false;
    bdScaled = {};
    bdImage = nullptr;
    bdW = bdH = 0;
    bakedImage = nullptr;
    bakedWhere = -1;
    bakedBright = -1.0f;
    // 品牌标也放掉。它是 192×188 那一档，比底图小得多，但"编辑器不可见时
    // 把缓存放掉"是一条**没有例外**的规矩 —— 留一个例外，下次就会有人
    // 觉得留第二个也无所谓。
    logoScaled = {};
    logoW = logoH = 0;
}

// ---- 性能剖析：TRANE_PROF=1 时每 30 帧往 stderr 打一次分项耗时 ----
// 只为定位瓶颈用。正常运行时 on = false，每帧只多一次分支判断。
namespace {
struct PaintProf {
    bool on = false;
    double blit = 0.0, sig = 0.0, node = 0.0, chrome = 0.0, insp = 0.0;
    int n = 0;
    PaintProf() { on = std::getenv("TRANE_PROF") != nullptr; }
    void tick() {
        if (!on) return;
        if (++n < 30) return;
        std::fprintf(stderr,
            "[prof] %d 帧均值 (ms): 底图 %.2f  信号线 %.2f  质点 %.2f  顶栏 %.2f  检查器 %.2f\n",
            n, blit / n, sig / n, node / n, chrome / n, insp / n);
        blit = sig = node = chrome = insp = 0.0;
        n = 0;
    }
};
PaintProf& prof() { static PaintProf p; return p; }
double profNow() { return juce::Time::getMillisecondCounterHiRes(); }
}  // namespace

void paint(Graphics& g, const PanelState& st, PanelCache& cache) {
    auto& P = prof();
    const double t0 = P.on ? profNow() : 0.0;
    cache.update(st);

    // backdrop 是**不透明**的（它自带面板底），所以能贴图时不要再 fillAll 一遍。
    //
    // 注意：这里**不要**加 `useNearestNeighbour=true`。实测过 —— 2880×1440 的
    // 最近邻路径反而比默认的重采样慢（4.77 → 7.02 ms/帧），因为 JUCE 的重采样
    // 走的是 SIMD 优化过的标度器，而最近邻退回了逐像素分支。
    if (cache.backdrop.isValid()) {
        g.drawImage(cache.backdrop, 0, 0, geom::kBaseW, geom::kBaseH,
                    0, 0, cache.backdrop.getWidth(), cache.backdrop.getHeight());
    } else {
        g.setColour(kBg);
        g.fillAll();
    }
    const double t1 = P.on ? profNow() : 0.0;

    const float breath = breathOf(st);

    // v0.33：动态层从"信号线 + 十个质点圆"缩成"顶栏 + 检查器"。
    // 面板现在只有**两层**：底图（缓存，含背景图）与前景（顶栏 + 参数行）。
    // 中间那两层 —— 骨架 / 信号线 / 质点圆 —— 随树一起删了。
    //
    // v0.36：顶栏这一层现在有两件东西 —— 左边的背景控件（`drawTabs`）
    // 与右边的品牌标（`drawBrandMark`）。品牌标放在这里而不是跟着参数行走，
    // 是因为它和分段控件一样**不随任何参数状态变**，只随设备缩放变。
    drawTabs(g, st);
    drawBrandMark(g, cache);
    const double t2 = t1, t3 = t1;    // 树的两层没了，分项归零
    const double t4 = P.on ? profNow() : 0.0;

    const auto L = buildInspector(st);
    drawInspector(g, st, L, breath);
    const double t5 = P.on ? profNow() : 0.0;

    if (P.on) {
        // `sig` / `node` 两格还在（值恒为 0）—— TRANE_PROF 的输出格式没变，
        // 留着它们是为了"树删了之后这两格归零"这件事在剖析输出里看得见。
        P.blit += t1 - t0; P.sig += t2 - t1; P.node += t3 - t2;
        P.chrome += t4 - t3; P.insp += t5 - t4;
        P.tick();
    }
}

// ============================================================================
// 对外：几何自述（供测试与设计稿工具复算）
// ============================================================================
// 面板会渲染到的字符集合。**从控件表算，不手抄** —— 手抄的字符集会在有人
// 改了一个 label / unit 之后和代码分叉，而分叉的方向永远是"漏掉新加的字符"，
// 于是断言照绿、豆腐块照出。
//
// 加一个字符进来只需要改这里一处；测试那边会立刻要求打包字体覆盖它。
String textInventory() {
    String raw;
    const auto add = [&raw](const String& t) { raw << t; };

    for (int i = 0; i < kNumControls; ++i) {
        // 参数名与读数都按 `toUpperCase()` 画，所以两种大小写都要算进来 ——
        // 面板上真正出现的只是大写那份，但 label 表里存的是小写。
        add(String(kControls[i].label));
        add(String(kControls[i].label).toUpperCase());
        add(String(kControls[i].unit));
        add(String(kControls[i].name).toUpperCase());
    }
    for (const char* c : kChoices) add(c);

    // 固定文案：背景分段的两个格子 / 没选图时的占位。
    //
    // v0.36 删掉了 `"Trane"` 与 `" CONTROLS"` —— 顶栏那两行文字换成了 logo
    // （见 `drawBrandMark`）。**这两条必须跟着删**：留着一个面板上不会再画的
    // 字符，会让"打包字体必须覆盖清单里每个字符"那条断言去要求字体覆盖一个
    // 用不到的字形 —— 断言还是绿的，但它护的东西已经不在了。
    add("OFF");
    add("FULL");
    add("CHOOSE IMAGE");

    // 数值串的字符集：`formatShort()` 的所有分支合起来只可能产出这些
    // （数字、小数点、负号、正号、单位字母 —— 单位字母已经在控件表里了）。
    add("0123456789.-+");

    // **背景亮度的乘号。** 这一条是写这份清单时才发现的：亮度读数是
    // `String(...) + "×"` —— `×` 是 **U+00D7**，不是 ASCII 的 `x`。
    //
    // 于是 TranePanel.cpp 里那句"文案一律 ASCII"是**不准确的**：面板文案是
    // "ASCII + 一个乘号"。它一直没出事，只因为换字体之前那款字体恰好有 `×`
    // 这个字形。**换字体的时候这种"恰好"就没了** —— 所以这条要写进清单，
    // 让覆盖性断言去盯着它，而不是靠运气。
    //
    // **注意写法**：用 `charToString(0x00D7)`，**不能**写 `"\u00D7"`。
    // JUCE 的 `String(const char*)` 按 **Latin-1** 解释输入（文档原话："must not
    // contain any characters with a value above 127"），而 `"\u00D7"` 被编译器
    // 编成 UTF-8 的 `C3 97` 两个字节 —— 于是它变成**两个字符** U+00C3 + U+0097。
    // 实测 dump 出来是 `c2 97 c3 83`（排序还把两半调了个个儿），而**编译、运行、
    // 断言全都不报**。要 UTF-8 得显式走 `String::fromUTF8`。
    add(String::charToString(0x00D7));

    // 去重 + 按码位排序（排序只为让 dump 稳定，diff 好看）。
    // 走 `CharPointer_UTF8::getAndAdvance()` 拿**码位**，不拿字节 ——
    // 这里本来可以 range-for，但显式写出来省得下次有人以为拿到的是码位。
    std::vector<juce_wchar> cs;
    {
        auto p = raw.getCharPointer();
        for (auto c = p.getAndAdvance(); c != 0; c = p.getAndAdvance())
            cs.push_back(c);
    }
    std::sort(cs.begin(), cs.end());
    cs.erase(std::unique(cs.begin(), cs.end()), cs.end());

    String out;
    for (auto c : cs) out << String::charToString(c);
    return out;
}

// 格式**必须**让 tools/render_bg_study.py::read_geometry 解析得了 ——
// 那边的 render_ui_dark_panel.py 全靠它拿质点坐标。改格式就两边一起改。
String geometryDump() {
    String s;
    s << "panel " << roundToInt(geom::kBaseW) << " " << roundToInt(geom::kBaseH) << "\n";
    // UI 版本（**面板的版本**，不是插件版本 —— 区别见 TranePanel.h 的 kUiVersion）。
    // 出图脚本从这一行取文件名里的版本号，所以它必须是**机器可读的**：
    // 写死在工具里的那版实测分叉过（面板到 v0.33，文件名还写着 v0.32）。
    s << "ui_version " << kUiVersion << "\n";
    // ---- 字体（v0.35：改成打包内嵌）----
    // 报**字体自己声明的名字 + 一个实测宽度**。
    //
    // 名字证明"用的是打包的那份字体"（系统字体不会叫 Trane Sans）；
    // 宽度证明"用的是**对的那个字重**" —— 两个字面的 family 名是一样的，
    // 光靠名字分不出 Regular 和 SemiBold。
    //
    // 宽度是拿 `kFontProbeText`（十个数字）在**各自字号、字距 0** 下量的，
    // 测试那边用 fontTools 从 .ttf 的 hmtx 独立复算 —— 于是"字体悄悄降级"
    // 与"两个字面搞反了"都能抓。**换字体只改文字墨迹、不改任何一条几何**
    // （列宽是按字体量的，连数值都不动），所以这是唯一能抓到它的判据。
    // 探针串为什么是数字、容差为什么是 1% —— 见 TranePanel.h 的 `kFontProbeText`。
    s << "font_ui " << uiTypefaceName()
      << " " << String(geom::kFsName, 3)
      << " " << String(GlyphArrangement::getStringWidth(uiFont(geom::kFsName, 0.0f),
                                                       geom::kFontProbeText), 4) << "\n";
    s << "font_data " << dataTypefaceName()
      << " " << String(geom::kFsValue, 3)
      << " " << String(GlyphArrangement::getStringWidth(dataFont(geom::kFsValue, 0.0f),
                                                       geom::kFontProbeText), 4) << "\n";
    // 面板**会渲染到的所有字符**。测试拿它做两件事：
    //   ① 逐字符问打包字体有没有这个字形 —— 缺一个就是界面上的一个豆腐块；
    //   ② 断言全是 ASCII（**只有一个例外**：亮度读数的乘号 U+00D7，见下）。
    //
    // **范围**：只含"面板自己写的字"。用户选的图片文件名（`bd.name`）会被画在
    // 顶栏上，但那是**用户数据**，字体覆盖不了它 —— 所以它不在这份清单里，
    // 覆盖性断言也就不对它作任何承诺。
    //
    // 清单是从**控件表 + 固定文案**算出来的，不是手抄的字符集。
    s << "text_inventory " << textInventory() << "\n";
    // v0.33 删掉了 ring_r / scale_r / col_spacing / tree_h 四行 —— 它们是树的几何。
    // `pane` 保留：它现在是**画布内边距推出来的常量**（40 / 1360），
    // 不再是"分割线右边留出 kPaneGap"那个可变量。
    s << "pane " << String(geom::kPaneX0, 3) << " " << String(geom::kPaneW, 3) << "\n";
    // 顶栏品牌标（v0.36）的**实际落位矩形**（逻辑坐标，左上角 + 宽高）。
    //
    // 为什么吐这个而不是只吐 `kLogoH`：像素检查器要拿它去渲染图里**框定** logo
    // 那一片，才能量"这里真的画了东西"以及"它有多亮"。只给高，检查器就得自己
    // 按宽高比推宽度 —— 那就成了"检查器另抄一份事实"，换资产时会分叉。
    //
    // 宽高比来自**资产本身**（容器头里的 w/h），所以这一行会跟着换资产自动变。
    // 顺带吐源尺寸：检查器可以用它验"画出来的宽高比 == 资产的宽高比"。
    {
        const auto& bm = brandMark();
        const float lh = geom::kLogoH;
        const float lw = bm.ok ? lh * static_cast<float>(bm.w) / static_cast<float>(bm.h) : 0.0f;
        s << "logo " << String(geom::kLogoRight - lw, 3) << " "
          << String(geom::kLogoCY - lh * 0.5f, 3) << " "
          << String(lw, 3) << " " << String(lh, 3) << " "
          << bm.w << " " << bm.h << "\n";
    }
    // 背景图的落位区（逻辑坐标）。**只剩一个**，而且就是参数区本身。
    // 名字从 `bg_params` 改成 `bg_region`：旧名字暗示"两个区里选一个"，
    // 而 v0.33 之后没有第二个区了 —— 名字继续叫 params 会让人以为还有 tree 可选。
    s << "bg_region " << String(geom::kPaneX0, 1) << " " << String(geom::kPaneW, 1) << "\n";
    // 背景控件（顶栏中段）：组起点、组宽、以及每件的 x 偏移
    s << "bg_ctrl " << String(geom::kBgGroupX, 1) << " " << String(geom::kBgGroupW, 1)
      << " " << String(geom::kBgCellW, 1) << " " << String(geom::kBgSegW, 1)
      << " " << String(geom::kBgTrackW, 1) << " " << String(geom::kBgReadW, 1)
      << " " << String(geom::kBgGap, 1) << "\n";
    s << "bg_bright " << String(geom::kBgBrightMin, 2) << " " << String(geom::kBgBrightMax, 2)
      << " " << String(geom::kBgPeakBase, 1) << "\n";
    s << "controls " << kNumControls << "\n";
    // 哪些**模块**的参数全画成旋钮（v0.35）。两张清单都吐：
    //
    //   `knob_modules`  模块名 —— 与头文件的 `kKnobModules` 逐条对账，
    //                   拼错一个模块名只会让整个模块少掉旋钮，看不出来；
    //   `knobs`         **展开后的控件 id** —— 像素检查器按行分类要用它
    //                   （"这一行是旋钮还是条形"），而它必须是**编译产物**
    //                   算出来的那份，不能由检查器自己从模块名推 ——
    //                   推的话就是"检查器另抄一份事实"，改了代码它照样绿。
    //
    // 两张清单的一致性由 `tests/test_ui_design.py` 对账（展开对不对）。
    //
    // `knobs` 只列**参数行**（`label` 非空）—— 模块开关虽然也"属于旋钮模块"，
    // 但它不是一行，它是标题行本身。把它列进来会让检查器数出 25 个旋钮
    // （20 个参数行 + 5 个开关），而画面上只有 20 行 —— 于是"每一行都按形态
    // 归了类"那条会报一个**假的 ✗**（缺 5 行）。
    s << "knob_modules " << static_cast<int>(sizeof(kKnobModules) / sizeof(kKnobModules[0]));
    for (const char* m : kKnobModules) s << " " << m;
    s << "\n";
    // `knobs` 的**第一格是自述个数**（与 `knob_modules` 一致）。测试拿它做一条
    // 自洽检查："自述几个" 与 "实际列出几个" 必须相等 —— 写 dump 的那段代码
    // 将来改成先数一遍再列，数错了这里会当场报红，而不是让下游少画几行。
    int knobRows = 0;
    for (int i = 0; i < kNumControls; ++i)
        if (kControls[i].label[0] != '\0' && isKnob(i)) ++knobRows;
    s << "knobs " << knobRows;
    for (int i = 0; i < kNumControls; ++i)
        if (kControls[i].label[0] != '\0' && isKnob(i)) s << " " << kControls[i].id;
    s << "\n";
    // 第三种形态：`Fmt::Choice`（LP / BP / HP 分段块）。**单独吐出来**，
    // 不是给界面看的 —— 是给像素检查器分三类用的。
    //
    // 少了它，检查器只认"旋钮 / 条形"两类，于是 `sweep_mode` 会被当成条形，
    // 而分段块的墨迹从**格子里的文字**起（实测离轨道左端 +23.5px），
    // 于是"条形行左端必须有墨"那条正向对照会报一个**假的 ✗**。
    // 假报红比漏报更坏：它逼着下一个人把阈值调松，把真断言一起废掉。
    s << "choices";
    for (int i = 0; i < kNumControls; ++i)
        if (kControls[i].fmt == Fmt::Choice) s << " " << kControls[i].id;
    s << "\n";
    // 旋钮的几何（直径 / 环粗）。**吐出来**是因为"相邻两个旋钮够不够分开"
    // 要拿它和每栏的行距一起算 —— 而检查器不许自己抄一份常量（抄一份就会分叉）。
    // 净空 = 行距 − (直径 + 环粗)，规则见 TranePanel.h 的 `kKnobDia` 注释。
    s << "knob_dia " << String(geom::kKnobDia, 3) << " "
      << String(geom::kKnobStroke, 3) << "\n";
    // 模块框的两层（v0.35）：不透明度 + **实际画出来的颜色**。
    //
    // 颜色为什么要吐出来：像素检查器要判断"框内是块底、框外是面板底"
    // 以及"框线真的画了"，而它不许自己抄一份合成公式（抄一份就会分叉 ——
    // 改了 alpha 而检查器还在按旧值找，于是它报"框没画"，而框好好地画着）。
    //
    // **"压在什么上"要一层层算对。** 这里第一版把两层都按"压在纯黑上"算，
    // 结果框线报 (26,26,27) 而画出来是 (38,38,39) —— 因为**框线画在块底之上**
    // （`drawBlock` 先 `fillRoundedRectangle` 再 `drawRoundedRectangle`，
    //  而线内缩 0.5px 之后整根落在填充区里），所以它是 0.11 的墨压在 0.055 的
    // 块底上，不是压在面板底上。
    //
    // 报错的形状很值得记：断言是"最暗的左边线峰值 ≥ 框线 − 3"，实测峰值 38.1、
    // 自述 26.1 —— 于是它**绿着**，但它绿的理由是错的（真实阈值其实是
    // 23.1，而线没画时峰值只有 13）。**判据错了，断言照样绿。**
    const auto comp = [](float a, int under) {
        const auto ch = [&](int ink) {
            return String(roundToInt(a * static_cast<float>(ink)
                                     + (1.0f - a) * static_cast<float>(under)));
        };
        return ch(kInk.getRed()) + " " + ch(kInk.getGreen()) + " " + ch(kInk.getBlue());
    };
    const int fillOverPanel = roundToInt(kBlockFillA * static_cast<float>(kInk.getRed()));
    s << "block_fill " << String(kBlockFillA, 4) << " " << comp(kBlockFillA, 0) << "\n";
    s << "block_edge " << String(kBlockEdgeA, 4) << " "
      << comp(kBlockEdgeA, fillOverPanel) << "\n";
    // 框的几何：水平内缩 / 垂直内缩 / 框间空档 / 圆角。
    // 检查器要拿 padX 去算"内容左缘应该在哪"，拿 gap 去算"框与框之间的缝有多宽"。
    s << "block_geom " << String(geom::kBlockPadX, 3) << " " << String(geom::kBlockPadY, 3)
      << " " << String(geom::kBlockGap, 3) << " " << String(geom::kBlockR, 3) << "\n";

    int params = 0, switches = 0;
    for (int i = 0; i < kNumNodes; ++i) {
        params += nodeRowCount(i);
        if (nodeHasSwitch(i)) ++switches;
    }
    // `ring_slots` 改叫 `param_rows` —— 旧名字来自"树上的环上读数"，
    // 环删了，这个名字会让人去找一个不存在的环。
    s << "param_rows " << params << "\n";
    s << "switches " << switches << "\n";
    // v0.33 删掉了 `signal_edges`（9 条信号线）与 `node` 行里的 x / y
    // （质点坐标）—— 都是树的几何。行名也从 `node` 改成 `mod`：
    // 消费者（测试 / 设计稿工具）会**当场解析失败**，而不是静默地拿到 0,0。
    //
    // v0.35 **把节点序号显式吐出来**（原来是靠行序隐含）。理由：`tests/`
    // 那边要把"节点 → 模块名"接起来才能判"这个模块是不是全旋钮"，而按行序
    // 推是个**看不见的约定** —— 谁调整一下 `kNodes` 的顺序，或者把这段循环
    // 改成按别的东西遍历，映射就静默错位，而错位的表现是"某些模块的旋钮
    // 判错了"，看起来像形态判据的问题。**能吐出来的东西不要靠约定。**
    // 两个消费者（`check_panel_render.py` / `test_ui_design.py`）一起改。
    for (int i = 0; i < kNumNodes; ++i)
        s << "mod " << i << " " << kNodes[i].sephira << " " << kNodes[i].module << " "
          << nodeRowCount(i) << "\n";
    for (int i = 0; i < kNumControls; ++i) {
        s << "ctl " << kControls[i].id << " " << controlNode(i) << " " << controlSlot(i)
          << " " << kControls[i].label << "\n";
    }
    return s;
}

// 检查器各栏的几何 —— 列宽、行距、字号、三段宽度（名 / 轨道 / 值）。
//
// 为什么单独开一个而不是塞进 `geometryDump`：`geometryDump()` 不收 `PanelState`，
// 而这几项**恰恰依赖状态**（模式与列数决定分栏，分栏决定最挤那列，最挤那列决定字号）。
// 塞进去只能报一份默认状态的值，换个模式就是错的 —— 而"报一个错的值"比"不报"更坏。
//
// 它是**排版回归**的证据来源：小绪这次的要求里有一条是"排版大致不变"，
// 而"大致不变"必须落成数字（字号 / 行距 / 列宽），不能靠肉眼看两张图说"差不多"。
String layoutDump(const PanelState& st) {
    const auto L = buildInspector(st);
    String s;
    s << "columns " << L.columnCount << "\n";
    s << "shown_controls " << L.shownControls << "\n";
    // 行内留白（名字 ─ 轨道 ─ 数值 之间那道）。**必须吐出来**：三段宽加起来
    // 填不满一栏时，差出来的就是被吞掉的留白，而"填不填得满"是数值列宽之外
    // 的另一半保证 —— 少了它，`trackW` 少减一个 kGap 也照样绿（轨道往右多铺
    // 8px，把留白吃掉，最宽的数值就贴在轨道上了）。
    s << "gap " << String(geom::kGap, 3) << "\n";
    // 框的水平内缩（v0.35）。三段宽算的是**框内**宽，所以检查器必须拿
    // `col.w − 2×padx` 去对账 —— 少了这一行，它会拿栏宽当内容宽，
    // 于是"三段宽正好填满一栏"这条**永远差 28px**，报一个没有信息量的红。
    s << "padx " << String(geom::kBlockPadX, 3) << "\n";
    for (int i = 0; i < L.columnCount; ++i) {
        const auto& c = L.column[i];
        s << "col " << i
          << " x "       << String(c.x, 3)
          << " w "       << String(c.w, 3)
          << " rows "    << c.rowCount
          << " pitch "   << String(c.pitch, 3)
          << " fsName "  << String(c.fsName, 3)
          << " fsValue " << String(c.fsValue, 3)
          << " fsTitle " << String(c.fsTitle, 3)
          << " labelW "  << String(c.labelW, 3)
          << " trackW "  << String(c.trackW, 3)
          << " valueW "  << String(c.valueW, 3)
          << " nodes";
        for (int j = 0; j < c.nodeCount; ++j) s << " " << c.node[j];
        s << "\n";
    }
    // 每个模块框的矩形（v0.35）。**吐出来**的理由与 `knob_dia` 一样：
    // "框画在哪儿"原本只有绘制代码知道，于是"框有没有盖住行""框与框之间
    // 留了多少缝"这两件事只能靠肉眼看图。吐出来之后，检查器可以
    //   ① 拿它去像素上验"框内是块底、框外是面板底"；
    //   ② 验框与框不重叠、缝宽恒定。
    // 末位那个 0/1 是"这个模块全旋钮吗" —— 形态的一致性要跨"框"与"行"两处看。
    for (int i = 0; i < L.blockCount; ++i) {
        const auto& b = L.block[i];
        s << "block " << b.column << " " << b.node
          << " " << String(b.top, 3) << " " << String(b.bottom, 3)
          << " " << (b.knobModule ? 1 : 0) << "\n";
    }
    return s;
}

// ============================================================================
// 对外：规格串 → 逻辑坐标点
// ============================================================================
// `--hover` / `--press` / `--hit` / `--click` 用的是同一套规格写法，所以解析
// 只留这一份 —— 留两份，两处迟早分叉，然后"测试绿着但插件是坏的"。
//
// 认不出来时 `ok` 为假、点落在**面板外**（-1000, -1000）：测试里一眼能看出
// 是规格写错了，而不是命中判错了。
Point<float> specPoint(const String& spec, const PanelState& st, bool& ok) {
    const auto parts = StringArray::fromTokens(spec, ":", "");
    const auto head = parts.isEmpty() ? String{} : parts[0];

    Point<float> p{-1000.0f, -1000.0f};
    ok = (head == "outside");

    const auto centre = [](const TabBox& b) {
        return Point<float>{b.x + b.w * 0.5f, b.y + b.h * 0.5f};
    };

    // v0.33 删掉了 `divider` 与 `node:<module>` 两种规格 —— 分割线和质点圆
    // 都没了。**刻意不保留成"永远返回 ok=false 的兼容写法"**：
    // 那会让一个写错规格的测试静默地变成"这个交互不存在"，而它其实只是名字写错了。
    if (head == "bgslot") {
        p = centre(bgCellBox());
        ok = true;
    } else if (head == "bgbright") {
        p = centre(bgTrackBox());
        ok = true;
    } else if (head == "tab" && parts.size() == 2) {
        // 只剩一组了，所以写法从 `tab:<组>:<格>` 收紧成 `tab:<格>`。
        // **旧的 `tab:2:1` 会解析失败**（parts.size() != 2）—— 这是有意的：
        // 三格变两格之后，"第 2 格"指的是什么已经变了，静默接受会读到错的格子。
        const int opt = parts[1].getIntValue();
        const auto box = bgSegBox();
        const float n2 = static_cast<float>(geom::kBgSegN);
        // 取第 opt 格的**正中**：不贴边，免得被相邻格或边界判据吃掉。
        p = {box.x + box.w * (static_cast<float>(opt) + 0.5f) / n2, box.y + box.h * 0.5f};
        ok = true;
    } else if (head == "ctl" && parts.size() == 2) {
        const int ci = indexOfId(parts[1]);
        if (ci >= 0) {
            const auto L = buildInspector(st);
            const int r = L.controlRow[ci];
            if (r >= 0) {
                const auto& row = L.row[r];
                const auto& col = L.column[row.column];
                // 落在**参数名**那一小段上（行的左端）—— 整行都算这个控件。
                // v0.35：参数名在框内，所以起算点是 `col.x + kBlockPadX`。
                p = {col.x + geom::kBlockPadX + jmax(2.0f, col.labelW * 0.5f), row.mid};
                ok = true;
            }
        }
    }
    return p;
}

const char* kindName(Hit::Kind k) {
    switch (k) {
        case Hit::Kind::None:     return "None";
        case Hit::Kind::Control:  return "Control";
        case Hit::Kind::BgSlot:   return "BgSlot";
        case Hit::Kind::BgBright: return "BgBright";
        case Hit::Kind::TabBg:    return "TabBg";
    }
    return "None";
}

const char* groupName(BarGroup g) {
    switch (g) {
        case BarGroup::None:    return "None";
        case BarGroup::BgWhere: return "BgWhere";
    }
    return "None";
}

// ============================================================================
// 对外：点击自述
// ============================================================================
// 把「按下 → 松手 → 判定」整条链跑一遍，吐出可断言的文本。
//
// **走的是编辑器 mouseDown / mouseUp 用的同一份代码**（`barGroupOf` +
// `resolveBarClick`），所以这里绿了，插件里就是对的 —— 这正是原先缺的那一环：
// 判定住在 PluginEditor 里，离线探针够不着，于是测试只能测 hitTest，
// 测在了缝的另一侧，「MODULE 点不开」摆在眼前照样全绿。
String clickDump(const String& pressSpec, const String& releaseSpec, bool moved,
                 const PanelState& st) {
    bool okP = false;
    const auto pDown = specPoint(pressSpec, st, okP);

    String s;
    s << "click_press " << pressSpec << "\n";
    s << "click_release " << (releaseSpec.isEmpty() ? pressSpec : releaseSpec) << "\n";
    s << "click_moved " << (moved ? 1 : 0) << "\n";
    if (!okP) {
        s << "click_fired 0\nclick_press_group unknown\nclick_group unknown\nclick_option -1\n";
        return s;
    }

    // ① 按下 —— 编辑器在这一步**原样存下这个 Hit**，不做任何翻译
    const auto down = hitTest(pDown, st);
    s << "click_press_kind " << kindName(down.kind) << "\n";
    s << "click_press_group " << groupName(barGroupOf(down)) << "\n";
    s << "click_press_option " << down.option << "\n";

    // ② 松手 —— 判定
    // 注意 `okR` 的初值：release 省略时走的是 pDown 那条路，`specPoint` 根本
    // 不会被调用，`okR` 必须**自己置真**。忘了这一条，省略 --release 的调用
    // 会全部短路成"没触发" —— 自述本身报了个假警，比被测代码还难查。
    bool okR = releaseSpec.isEmpty();
    const auto pUp = releaseSpec.isEmpty() ? pDown : specPoint(releaseSpec, st, okR);
    if (!okR) {
        s << "click_fired 0\nclick_group unknown\nclick_option -1\n";
        return s;
    }

    const auto v = resolveBarClick(down, moved, pUp, st);
    s << "click_fired " << (v.fired ? 1 : 0) << "\n";
    s << "click_group " << groupName(v.group) << "\n";
    s << "click_option " << v.option << "\n";
    return s;
}

// ============================================================================
// 对外：命中测试自述
// ============================================================================
String hitDump(const String& spec, const PanelState& st) {
    bool known = false;
    const auto p = specPoint(spec, st, known);

    String s;
    s << "hit_spec " << spec << "\n";
    s << "hit_point " << String(p.x, 3) << " " << String(p.y, 3) << "\n";
    if (!known) {
        s << "hit_kind unknown\n";
        return s;
    }

    const auto h = hitTest(p, st);
    s << "hit_kind " << kindName(h.kind) << "\n";
    s << "hit_control " << h.control << "\n";
    s << "hit_option " << h.option << "\n";

    // `mark()` 才是**真正写进 hover / press 的那一份**，必须单独吐出来。
    //
    // v0.32.2 的「拖参数时开关跟着闪」就是坏在这里：`hitTest` 是对的，而
    // `mark()` 给参数行多带了一个 `node`，于是树上圆和模块标题行把它读成
    // "指针在这个模块上"。只测 `hitTest` 抓不到这个 Bug。
    //
    // v0.33 把 `node` 字段整个删了，那**一种**错法成了不可能；但**这一类**
    // 错法还在 —— 任何"`mark()` 比 `kind` 多带了东西"都会让某处提前亮起来。
    // 所以 dump 的字段跟着 `Mark` 的实际成员走，一个不多一个不少：
    // 测试拿它做**全集比对**（每一项都要对得上），而不是"挑几个看看"。
    const auto m = h.mark();
    s << "mark_control " << m.control << "\n";
    s << "mark_tab " << m.tab << "\n";
    s << "mark_option " << m.option << "\n";
    s << "mark_bg_slot " << (m.bgSlot ? 1 : 0) << "\n";
    s << "mark_bg_bright " << (m.bgBright ? 1 : 0) << "\n";
    return s;
}

// ============================================================================
// 对外：文字度量自述（供测试复算"数值列宽够不够"）
// ============================================================================
//
// **为什么需要它。** 数值是右对齐画的，而且走的是
//
//     g.drawText(vt, {col.x, mid - fsV, col.w, fsV * 2.0f},
//                Justification::centredRight, false);   // ← 最后那个 false
//
// 最后那个参数是 `useEllipsesIfTooBig = false` —— 串太长**不截断、不缩字号**，
// 只会静静地往左爬进轨道区。于是"右缘齐平"那类断言永远绿，这个坏法只能靠量。
//
// v0.33 之前列宽是按**字符数**估的（`valueW = vmax × kValueW × 字号`），那个模型
// 有两条前提，**两条都不成立、而且两条都没有任何东西盯着**：
//
//   ① `kValueW = 0.60` 必须是最宽那个字符的**上界**。头文件里它的注释写的是
//      "数字 + 单位平均前进宽度" —— "平均"对上界没有任何保证。实测：
//      预算 0.60 × 12 = 7.2px，而最宽的字符 `M`（"2000MS" 里那个）是 8.314px。
//   ② 一个控件能显示的最长数值串，字符数不能超过它在**默认值**处的字符数 ——
//      因为 `extentsOf()` 当时只采样 `formatShort(i, defaultNormalised(i))`
//      **一个点**。实测 41 个控件里有 10 个在量程两端更长：`output` 默认值 6 字符，
//      量程顶端是 `+12.0DB` 7 字符。
//
// 现在列宽**直接量**（见 `extentsOf` / `columnMetrics`），两条前提一起消失；
// 这个 dump 于是成了"量得对不对"的唯一对账口。
//
// 吐六样：
//   font_value  —— 实际用的字体（AbletonSans 还是降级）与字号、字距；
//   fs_value    —— 布局真的在用的数值字号（含 fit，不等于 kFsValue）；
//   value_w     —— 布局真的在用的数值列宽（**从 buildInspector() 读，不另算**）；
//   glyph       —— 数值列里**可能出现的每个字符**的实测宽度（名字就是那个字符）；
//   ctrl        —— 正向对照用的两个字符（`i` / `M`），**不属于上面那张字符表**；
//   vmetric     —— 每个控件：默认值字符数 / 201 点里最长的字符数 / 实测最大宽度 / 那个串。
String metricsDump() {
    // **字号与列宽都从真布局读。** 自己按 kFsValue 另算一份，就会"改了布局、
    // 断言还在按旧值量" —— 那正是这一整套自检要防的东西。
    const InspectorLayout L = buildInspector(PanelState{});
    const ColumnLayout& col = L.column[0];
    const float fs = col.fsValue;
    const Font f = dataFont(fs, geom::kTrackData);

    String s;
    // v0.35：这里原来吐的是"AbletonSansMedium-Regular 还是 HelveticaNeue-fallback"
    // —— 现在字体是打包的，没有分支可报，直接报**字体自己声明的名字**。
    // 于是"面板在用打包字体吗"变成一条可判定的事实，而不是一句注释。
    s << "font_value " << dataTypefaceName()
      << " " << String(fs, 4) << " " << String(geom::kTrackData, 4) << "\n";
    s << "fs_value " << String(fs, 4) << "\n";
    s << "value_w " << String(col.valueW, 4) << "\n";

    auto glyph = [&](const String& name, const String& ch) {
        s << "glyph " << name << " " << String(GlyphArrangement::getStringWidth(f, ch), 4) << "\n";
    };

    // 数值列里可能出现的字符。**从 `formatShort()` 的分支逐条反推**：
    // 数字 / 小数点 / 负号（Ms、Plain2）/ 正号（Db1 的 "+0.0DB"）/ 单位字母
    // （MS / DB / K）/ 选择型的三段标签（LP / BP / HP）。
    //
    // **名字就用字符本身**，不用 `digit0` / `unit_M` 这种代号 —— 测试要拿这张表
    // 和"数值串里真的出现过的字符集"做**集合比对**，而那个集合是原始字符。
    // 用代号就得在测试里再抄一份映射表，那就成了两份事实来源。
    for (int d = 0; d <= 9; ++d) glyph(String(d), String(d));
    glyph(".", ".");
    glyph("-", "-");
    glyph("+", "+");
    for (const char* u : {"M", "S", "D", "B", "K", "L", "P", "H"}) glyph(u, u);

    // 正向对照：`i` 与 `M` 在任何比例字体里宽度都必然不同。测试拿它证明
    // "量宽度"这件事真的在量 —— 否则一个恒返回常数的桩也能让"数字等宽"全绿。
    // **故意不叫 `glyph`**：它们不是数值列字符集的一部分，测试也不该把它们
    // 算进那张表 —— 算进去的话，"表里的字符都能量到宽度"那条断言就白送了。
    s << "ctrl i " << String(GlyphArrangement::getStringWidth(f, "i"), 4) << "\n";
    s << "ctrl M " << String(GlyphArrangement::getStringWidth(f, "M"), 4) << "\n";

    // 采样点：**201 个点**（步长 0.005），而不是布局自己那 6 个。
    // 于是这里算出的最大宽度**严格强于**布局的保证 —— 布局漏掉的中间点这里会抓到。
    // `check_metrics_mutations.py` 的 M3 专门造一个"只有中间点更宽"的格式，
    // 看这一条会不会报红；报红才说明布局那 6 个点真的够用。
    constexpr int kSweep = 200;
    for (int i = 0; i < kNumControls; ++i) {
        const auto& c = kControls[i];
        if (c.label[0] == '\0' || c.fmt == Fmt::None) continue;   // 模块开关不进参数行

        const String def = formatShort(i, defaultNormalised(i));
        int maxChars = def.length();
        float maxW = GlyphArrangement::getStringWidth(f, def);
        String widest = def;

        for (int k = 0; k <= kSweep; ++k) {
            const String v = formatShort(i, static_cast<float>(k) / static_cast<float>(kSweep));
            const float w = GlyphArrangement::getStringWidth(f, v);
            if (v.length() > maxChars) maxChars = v.length();
            if (w > maxW) { maxW = w; widest = v; }
        }

        s << "vmetric " << c.id << " " << def.length() << " " << maxChars
          << " " << String(maxW, 4) << " " << widest << "\n";
    }
    return s;
}

// ============================================================================
// 对外：文字对比度自述
// ============================================================================
//
// 渲一帧（只为触发登记），把登记表吐出来。**不需要出图** —— 所以它可以被测试
// 反复调用（十几个相位）而不必每次写一张 2880×1440 的 PNG。
//
// **必须真的走一遍 `paint()`**：登记表是绘制代码自己报的，不是这里另算一份 ——
// 那正是这套机制的全部意义。谁把这里改成"照着常量表算一遍"，这个工具就废了。
String textDump(const PanelState& st) {
    textLog().clear();

    PanelCache cache;
    cache.ensure(1.0f);
    Image img{Image::ARGB, roundToInt(geom::kBaseW), roundToInt(geom::kBaseH), true};
    {
        Graphics g{img};
        paint(g, st, cache);
    }

    String s;
    for (const auto& e : textLog())
        s << "text " << String(e.a, 4) << " " << bdName(e.bd)
          << " " << String(e.bandA, 4) << "\n";
    s << "text_count " << static_cast<int>(textLog().size()) << "\n";
    return s;
}

}  // namespace trane::panel
