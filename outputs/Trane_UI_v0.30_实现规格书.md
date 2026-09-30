# Träne 面板 v0.30 · 实现规格书

> **这份文档是给"另一个 AI"看的。** 它要照着它，把设计稿搬进真正的插件。
> 读完这一份就能动手，**不需要**本仓库的其它上下文。
>
> 目标版本：**UI v0.30**
> 要改的文件：`vst/plugin/TranePanel.h`、`vst/plugin/TranePanel.cpp`、`vst/plugin/PluginEditor.cpp`
> 设计稿的唯一实现：`vst/tools/render_ui_dark_panel.py`（1440×720 横版，暗场）
> 设计稿的渲染产物：`outputs/Trane_UI_v0.30*.png`（9 张）

---

## 0 · 现状与任务

### 0.1 现在插件里画的是什么

`TranePanel.h` / `TranePanel.cpp` 现在实现的是 **v0.18**：

- 画布 **544 × 988**（竖版），`geom::kPanelW` / `geom::kPanelH`
- **浅色**：白底 `#FAFAF9` + 近黑 `#0E0E0F`，蒂芙尼蓝 `#0ABAB5` 作强调
- 10 个模块画成**圆**，圆内**环形文字**（参数名沿弧排），值用**辐条**表示
- 面板上一个参数检查器都没有 —— 参数只能靠圆上的辐条和环形文字读

### 0.2 要改成什么（v0.30）

**不是"微调"，是换一套版面。** v0.30 是：

- 画布 **1440 × 720**（横版，宽高比锁死 2:1）
- **暗场**：`#000000` 底 + Apple 深色模式语义色
- 左边 = **世界树**（10 个质点圆，22 条骨架 + 9 条信号线）
- 右边 = **参数检查器**（全部 48 个控件的可读列表，两种模式 ALL / MODULE×1..4）
- 中间一条**可拖的竖分割线**
- 交互有 **idle / hover / press / focus** 四态
- 树上**有信号通过时高亮**（信号线两档）

### 0.3 三个不许动的既有事实

这三样是**已经验证过的**，改它们会连带弄坏别的东西：

1. **`TranePanel` 不许 `#include <juce_audio_processors>`。**
   面板层刻意不依赖 AudioProcessor，才能让 `panel_probe` 把**和插件完全相同的绘制代码**
   离线渲染成 PNG。加一个 AudioProcessor 相关的 include 就会毁掉离线可验证性，
   `vst/tests/test_editor_layout.py` 里有测试盯着这一条。
   面板只吃 `PanelState`（纯 POD），由 `PluginEditor` 填。

2. **几何 / 颜色 / 控件表只有一份事实来源：`TranePanel.h`。**
   不许在 `TranePanel.cpp` 里再抄一份常量，也不许在别的地方另写一份。
   任何工具要用，就从 `panel_probe --dump-geometry` 读。

3. **48 条控件表（`kControls[]`）一条都不许增删。**
   41 个环位参数 + 7 个模块开关。参数的内部 ID、范围、默认值、格式全部照旧。
   界面只是**换一种方式把它们画出来**，不改 DSP 侧的任何一个参数。

---

## 1 · 不可违反的硬约束（12 条）

每一条都有对应的断言或反向对照撑着。**实现完必须逐条自查。**

| # | 约束 | 为什么 |
|---|---|---|
| 1 | **面板上一个描边矩形都没有** | 小绪原话「我不要模块化的边框了」。分组只靠留白；v0.32 连聚焦蓝框也移除。 |
| 2 | **面板不使用彩色** | 保留 `#0A84FF` token 作平台语义/突变测试对照，但绘制层不得调用；交互反馈只用墨色透明度。 |
| 3 | **交互状态只改颜色，不改几何** —— 四态里所有文字的 `(x,y)` 与所有矩形的 `(x,y,w,h)` **逐字节相同** | 状态一变就重排 = "跳一下"的根因；而且会让排版断言全部失效（状态成了排版的隐藏输入） |
| 4 | **一切尺寸 = 基准值 × S**，`S = w / 1440`。画布宽高比必须锁死 | 插件里 `setFixedAspectRatio(1440.0/720.0)`。非基准比例直接报错，不许"悄悄兜住" |
| 5 | **字号只许三档 13 / 12 / 11，字重 600 / 500 / 400，没有细字重** | Apple 的 macOS 文字样式阶梯（Headline / Body / Callout / Caption 1）。放不下时**整体等比缩**，不许某一档单独变 |
| 6 | **文字只用两档不透明度**：1.00（主）/ 0.60（次）；关闭态 0.56 | Apple 的 `tertiaryLabel(0.30)` 在 `#000000` 上只有 2.23:1，**过不了 WCAG AA 4.5:1**。它只能给**非文字**（刻度、发丝线）用 |
| 7 | **分段控件保留直角** | Apple 的 `NSSegmentedControl` 是圆角，小绪早先明确「不要圆角按钮」。这是**有意偏离**，不是疏忽。断言：SVG 里不许出现 `rx=` |
| 8 | **参数名写全称，全部大写** | 剥掉模块前缀后 `GRAIN MIX / STUTTER MIX / COMB MIX / TAPE MIX / DELAY MIX / SPACE MIX` 六条会全塌成 `MIX`。41 条会只剩 29 个唯一名 |
| 9 | **参数显示名必须全局唯一** | 宿主按名查找只认第一个；撞名会让端到端验收静默跳过。有静态回归测试盯着 |
| 10 | **树的纵轴就是信号轴** —— 10 个质点的 y 在信号链顺序下**单调不减** | 这是"信号往下流"这个读法成立的唯一依据。y 回头 = 整条动线失去依据 |
| 11 | **骨架 22 条一条不少，信号 9 条独立于骨架** | 生命之树"一条不多一条不少"的原始设定。信号链里 `STUTTER → COMB` **不在**那 22 条里（22 条命中 8 条，缺 1 条） |
| 12 | **高亮必须是可测的差分**：通过档在最暗呼吸相位下 > 静止档最亮处 | 否则"高亮"就只是"亮了一点点"，等于没做。硬断言 `SIG_HOT_LO × SIG_BREATH_MIN > SIG_REST_HI` |

---

## 2 · 画布与坐标系

```
基准画布     1440 × 720
宽高比       2.0（锁死）
分割线 x     DIVIDER_X   = 392
参数区起点 x  PANE_X0    = 422
参数区内边距  PANE_PAD   = 28
参数区宽     PANE_W      = 1440 − 422 − 28 = 990
树的包围盒    (30, 40, 332, 640)          ← x, y, w, h
```

**缩放**：所有数值都是"基准值 × S"，`S = w / 1440`（宽高比已锁死，所以 `h/720` 与它相等）。

```cpp
// 在 metrics() 里
const float s = w / 1440.0f;
```

### 2.1 树的几何推导（只有两条比值）

```cpp
// 树的包围盒
const float bx = 30, by = 40, bw = 332, bh = 640;

// 圆的半径：由包围盒反推，两个方向取小
const float r = std::min(bw / 7.865f, bh / 15.514f);   // ≈ 41.25

// 两条比值 —— 这是**唯一的**几何推导
const float col    = r / 0.341f;   // ≈ 120.97  相邻两列质点的 x 距离
const float tree_h = r / 0.074f;   // ≈ 557.46  Keter 到 Malkuth 的 y 跨度

const float cx = bx + bw * 0.5f;   // 196
const float cy = by + bh * 0.5f;   // 360
```

> `7.865 = 2/0.341 + 2`（左右各一个列距 + 左右各一个半径）
> `15.514 = 1/0.074 + 2`（树高 + 上下各一个半径）

### 2.2 十个质点的位置

```
u = column − 1        // column: 0 = 左柱 → u = −1 ；1 = 中柱 → u = 0 ；2 = 右柱 → u = +1
v = ratio             // kNodes[].ratio，0 = Keter，1 = Malkuth

x = cx + u · col
y = cy + (v − 0.5) · tree_h
```

| # | 质点 | 模块 | column | ratio | u | v | x | y |
|---|---|---|---|---|---|---|---|---|
| 0 | Keter | `freeze` | 1 | 0.000 | 0 | 0.000 | 196.0 | 81.3 |
| 1 | Chokhmah | `grain` | 2 | 0.125 | +1 | 0.125 | 317.0 | 151.0 |
| 2 | Binah | `stutter` | 0 | 0.125 | −1 | 0.125 | 75.0 | 151.0 |
| 3 | Chesed | `comb` | 2 | 0.375 | +1 | 0.375 | 317.0 | 290.3 |
| 4 | Gevurah | `tape` | 0 | 0.375 | −1 | 0.375 | 75.0 | 290.3 |
| 5 | Tiferet | `ruin` | 1 | 0.500 | 0 | 0.500 | 196.0 | 360.0 |
| 6 | Netzach | `sweep` | 2 | 0.625 | +1 | 0.625 | 317.0 | 429.7 |
| 7 | Hod | `delay` | 0 | 0.625 | −1 | 0.625 | 75.0 | 429.7 |
| 8 | Yesod | `space` | 1 | 0.750 | 0 | 0.750 | 196.0 | 499.4 |
| 9 | Malkuth | `out` | 1 | 1.000 | 0 | 1.000 | 196.0 | 638.7 |

**10 个点落在 7 层**（1 / 2 / 2 / 1 / 2 / 1 / 1，其中 grain↔stutter、comb↔tape、sweep↔delay 三对同层）。

> 表中 x/y 是 S = 1 时的值。实现时全部 × S。
> `column` 与 `ratio` 直接取 `kNodes[]` 里已有的两个字段，**不要另立一张表**。

---

## 3 · 颜色令牌

**全部取自 Apple 深色模式的语义色**，不是"看着像"。

| 令牌 | 值 | 用途 | Apple 来源 |
|---|---|---|---|
| `BG` | `#000000` | 面板底 | `systemBackground` |
| `SURFACE` | `#1C1C1E` | 树上"灭"的圆的填充 | `secondarySystemBackground` |
| `INK` | `#EBEBF5` | **所有文字与线条的基色**（微冷，不是纯白） | `label`（dark） |
| `FILL` | `rgba(120,120,128,.36)` | 控件底：轨道、关着的开关方块 | `systemFill` |
| `SEG_BG` | `rgba(118,118,128,.24)` | 分段控件的底 | `tertiarySystemFill` |
| `GRAY2` | `#636366` | 分段控件的**选中块** | `systemGray2` |
| `SEP` | `rgba(84,84,88,.60)` | 发丝线、分割线 | `separator` |
| `ACCENT` | `#0A84FF` | **保留但不绘制**，仅作平台语义/突变测试对照 | `systemBlue`（dark）token |

### 3.1 文字不透明度阶梯

| 令牌 | 值 | 用在哪 | 实测对比度 |
|---|---|---|---|
| `A_TEXT` | **1.00** | 数值、选中的分段标签、视图标题 | 高 |
| `A_MUTED` | **0.60** | 参数名、副标题、未选中的分段标签 | ≥ 4.5:1 |
| `A_OFF` | **0.56** | 关闭态的一切文字 | 4.85:1 |
| `A_NODE` | 0.68（+0.28 × 呼吸 → 0.96） | 树上**活动**模块名 | 6.85:1 |
| `A_VAL` | 0.60（+0.20 × 呼吸 → 0.80） | 树上**活动**模块的数值 | 6.85:1 |
| `A_TICK` | **0.30** | **非文字**：出厂值刻度、发丝线 | 不适用（非文字） |

> **`A_TICK = 0.30` 只能用在非文字上。** 用它写文字会掉到 2.23:1，过不了 WCAG AA。
> 这条是有意偏离 Apple —— Apple 的 `tertiaryLabel` 就是这个值，但它当文字用不合格。

### 3.2 树的专属值

| 令牌 | 值 | 说明 |
|---|---|---|
| `CIRC_ON_A` | 0.07 | 树上"亮"的圆的填充（`INK` 压在 `BG` 上） |
| `GLOW_MAX` | 0.22 | 光晕峰值（外圈径向渐变） |
| `GLOW_R` | 20 × S | 光晕往外衰减的宽度 |

---

## 4 · 字体与字号

### 4.1 字体

| 用途 | 字体 | 字距（× 字号） |
|---|---|---|
| UI 文字（标题 / 参数名 / 分段标签） | `UI` | `TRACK_UI = −0.012` |
| 视图标题 | `UI` | `TRACK_HEAD = −0.005` |
| 数值（等宽感） | `DATA` | `TRACK_DATA = −0.018` |

**字体来源**：运行时只读取用户本机已安装的 `Ableton Live 12.app` 里的
`AbletonSans-Bold.otf`（UI）与 `AbletonSansMedium-Regular.otf`（DATA）。
**不复制、不打包、不分发**该字体。找不到时降级 `Helvetica Neue`。

> 这一条在 `TranePanel.h` 里已经实现（`uiFont()` / `dataFont()`），**照旧沿用**。
> 注意：`createSliderTextBox()` 必须覆写，不能只让预览图看起来像。

### 4.2 字号阶梯

```cpp
FS_TITLE = 13.0f;   // 模块标题        weight 600
FS_VALUE = 12.0f;   // 参数数值        weight 500
FS_NAME  = 11.0f;   // 参数名          weight 400
FS_MIN   = 10.0f;   // 硬下限 = Apple 的 macOS 最小可读字号
```

**放不下时整体等比缩**：

```cpp
scale_fit = min(1.0f, fs_fit_w / (FS_NAME * s), fs_fit_h / (FS_NAME * s));
fs_name  = FS_NAME  * s * scale_fit;
fs_value = FS_VALUE * s * scale_fit;
fs_title = FS_TITLE * s * scale_fit;
```

- `fs_fit_w` = 宽度能容下的最大字号（由列宽、最长参数名、最长数值反推）
- `fs_fit_h` = `row_span * 0.72`（字号不许超过行距的 72%，否则上下行贴在一起）

**三档必须一起缩。** 只缩一档会把层级压平（HIG：「保持文本元素的相对层级」）。

### 4.3 树上的字号

```cpp
fs_tab      = 11.0f * s;   // 顶栏分段控件标签
fs_head     = 17.0f * s;   // 视图标题（ALL PARAMETERS / MODULE PARAMETERS）
fs_sub      = 11.0f * s;   // 副标题（48 CONTROLS）
fs_node     = 11.0f * s;   // 树上的模块名
fs_node_val = 10.0f * s;   // 树上的数值
```

---

## 5 · 间距阶梯

```cpp
GAP                =  8.0f;   // 行内三格之间（名称 ─ 轨道 ─ 数值）
COL_GAP            = 28.0f;   // 列与列之间
SECTION_GAP_MULT   =  2.5f;   // 模块与模块之间 = 行距 × 2.5
PANE_PAD           = 28.0f;   // 参数区内边距
ROWS_TOP           = 118.0f;  // 参数区第一行分组顶的 y
ROWS_BOTTOM_PAD    = 28.0f;
```

**三个数是三个不同的用途**：行内 / 分组 / 分栏。

> **留白能分组的前提是「组间空档明显大于组内」**，必须差一个量级。
> 组内 8px vs 组间 = 行距 × 2.5 —— 这是"去边框"之后**唯一**的分组手段。

### 5.1 行定位（按文字基线，不按行框）

```
pitch  = [avail_h − blocks·(BLOCK_UP + BLOCK_DOWN)·S]
         / [rows − blocks + (blocks − 1)·SECTION_GAP_MULT]

基线_i = 分组顶 + BLOCK_UP·S + i·pitch        （i = 0 … 行数−1）
```

```cpp
BLOCK_UP   = 19.4f;   // 分组顶边 → 首行基线
BLOCK_DOWN = 12.6f;   // 末行基线 → 分组底边
ROW_BAND   =  0.80f;  // hover/press 行底高度 = 行距 × 0.80（跟着行距缩放，不写死 px）
```

> **行框这个概念已经从代码里删掉了。** v0.26 对齐的是"行框底边"，而行框不可见；
> 行框高逐列差 2.5 倍（GRAIN 53.1px / COMB 132.0px），居中之后文字差了约 39.5px。
> 规则：**量的东西必须是肉眼能看见的东西。** 一律直接量 SVG 里渲染出来的**文字基线**。
>
> 各列行数不同，"行距共用 + 末行错开"与"各行均匀 + 末行对齐"不可兼得 —— **选后者**。

### 5.2 列宽推导

```
col_w = (PANE_W − COL_GAP·(n−1)) / n                 n = 1..4

label_w = lmax · K_LABEL · fs_name
value_w = vmax · K_VALUE · fs_value
track_w = col_w − label_w − value_w − 2·GAP
```

```cpp
K_LABEL   = 0.63f;    // 大写字母平均前进宽度（em）
K_VALUE   = 0.60f;    // 数字 + 单位（em）
MIN_TRACK = 46.0f;    // 轨道最短留多长（否则值编码的动态范围就没了）
```

- `lmax` / `vmax` = 这批模块里最长的参数名 / 最长数值各占多少字符
- 实测列宽（S = 1）：n = 1 → 990.0 · n = 2 → 481.0 · n = 3 → 311.3 · n = 4 → 226.5

---

## 6 · 世界树

### 6.1 三层结构（靠"质地"分层，不靠深浅）

| 层 | 内容 | 质地 | 线宽 | 不透明度 |
|---|---|---|---|---|
| ① **骨架** | `kPaths` 的 **22 条**标准连线 | **点线** `dasharray = "0.01, 5.5·S"` | 0.9 | `GRID_OP = 0.13` |
| ①' **中柱** | 骨架里的 `{0,5} {5,8} {8,9}` 三条 | 同上，略重 | 1.0 | `TRUNK_OP = 0.20` |
| ② **信号** | `SIGNAL_PATH` 的 **9 条** | **实线 + 沿线渐变** | 1.6 | 见 6.2 两档 |

**线不插进圆里**：每条线两端各沿方向缩掉 `r + 3`。

**不画箭头。** 沿线渐变（上游淡 → 下游亮）本身就是方向，而且不会在暗底上留一个刺眼的形状。

> 点线 vs 实线是最省的质地区分：一眼就能分出"哪层是结构、哪层是功能"。

### 6.2 信号层：两档高亮

小绪 2026-09-29 11:4x 的定调：

> 「生命树的所有骨架全部保留，在有信号通过的时候直接高亮表示就可以了」

所以 **22 条骨架一条不动**，信号线分两档：

| 档 | 触发条件 | 渐变（上游 → 下游） | 呼吸 |
|---|---|---|---|
| **静止** | 这条边不在通信号 | `SIG_REST_LO 0.32` → `SIG_REST_HI 0.55` | **不呼吸**（静态） |
| **通过** | 两端模块都亮 **或** 这条边的某一端被选中 | `SIG_HOT_LO 0.78` → `SIG_HOT_HI 1.00`，再 × `pulse` | **跟着呼吸脉动** |

```cpp
// 唯一判据 —— 画和自检必须共用这一份，不许各写一遍
bool isHot(na, nb, lit, selected) {
    return (lit.count(na) && lit.count(nb)) || selected.count(na) || selected.count(nb);
}

// 呼吸系数
pulse = SIG_BREATH_MIN + (1.0f - SIG_BREATH_MIN) * breath;   // SIG_BREATH_MIN = 0.85
```

**硬断言**：`SIG_HOT_LO × SIG_BREATH_MIN > SIG_REST_HI`
即 `0.78 × 0.85 = 0.663 > 0.55` —— 通信号那条边在**最暗的呼吸相位**下，
也要比静止那条**最亮处**还亮。

**静止档必须完全不呼吸。** 呼吸 = "这儿有东西在过"。没信号的时候线还在脉动，
等于在骗用户。验证方法：同一段绘制代码只换 `breath`，静止档的渐变必须**逐字节不变**。

#### 实测量级（PNG 像素，0–255）

采样方法：整张面板按 1440×720 渲成 PNG，**只在树的那一块里采样**（右半边是检查器，
全是亮字，不裁范围 p99 永远是 236），再挖掉每个节点圆盘（半径 `r + 46px`），
剩下的就是纯线像素。

| 层 | p50 | p99 | max |
|---|---|---|---|
| 骨架 · 普通连线 | 12 | 22 | 46 |
| 骨架 · 中柱 | 11 | 47 | 62 |
| 信号 · 静止档 | 84 | 125 | 128 |
| 信号 · **通过档**（最低呼吸相位） | 13 | **189** | 201 |
| 信号 · **通过档**（呼吸峰值） | 13 | **212** | 226 |

#### 逐边实测（9 条边，静止 vs 通过）

| 边 | 静止 p99 | 通过 p99 | 倍数 | 档 |
|---|---|---|---|---|
| `freeze → grain` | 120.1 | 220.1 | **1.83** | 通过 |
| `grain → stutter` | 119.0 | 217.0 | **1.82** | 通过 |
| `stutter → comb` | 119.0 | 217.0 | **1.82** | 通过 |
| `comb → tape` | 119.0 | 217.0 | **1.82** | 通过 |
| `tape → ruin` | 121.0 | 121.0 | 1.00 | 静止 |
| `ruin → sweep` | 120.1 | 120.1 | 1.00 | 静止 |
| `sweep → delay` | 119.0 | 119.0 | 1.00 | 静止 |
| `delay → space` | 121.0 | 121.0 | 1.00 | 静止 |
| `space → out` | 120.1 | 120.1 | 1.00 | 静止 |

> 演示用的 `lit` = 信号链的**前五级**（`freeze, grain, stutter, comb, tape`），
> 于是恰好 4 条边落在亮区里。**其余 5 条逐字节不变** —— 这就是"高亮"这件事本身。
> 真机上 `lit` 由遥测喂（见 §9.3）。

### 6.3 信号链（事实来源）

```
freeze → grain → stutter → comb → tape → ruin → sweep → delay → space → limiter(out)
```

**这条链的事实来源是 `vst/core/TraneEngine.cpp::process()`，不是界面。**
`SIGNAL_PATH` 由这条链**推导**（相邻对），**不许手写**：

```cpp
// 9 条相邻对，一条不多一条不少
SIGNAL_PATH = {(CHAIN[i], CHAIN[i+1]) for i in 0..8}
```

**为什么信号层必须独立于骨架层**：那 22 条是"相邻节点两两连线"的通用网格，
相对信号链**恰好命中 8 条、缺 1 条** —— 缺的是 **`stutter → comb`**。
信号层独立，才保得住生命之树"一条不多一条不少"。

**信号层不许自交。** 只向下，其中 **3 处是同层横跨**（`grain↔stutter`、`comb↔tape`、`sweep↔delay`，y 相等）。

### 6.4 质点圆的画法

**亮着**（`moduleIsOn(node)` 为真）：

```
光晕   径向渐变，圆心 = 质点，r_outer = r + GLOW_R
       stop 0           : INK, alpha 0
       stop r/r_outer   : INK, alpha (0.10 + GLOW_MAX · breath)   ← 0.10 … 0.32
       stop 1           : INK, alpha 0
       用 evenodd 路径把中间那块挖掉（只留环）
圆     填充 = INK @ CIRC_ON_A (0.07)       → 黑底上 ≈ #1B1C1D
       描边 = INK，宽 1.4，alpha = 0.62 + 0.38 · breath
```

**灭着**：

```
圆     填充 = SURFACE (#1C1C1E)
       描边 = SEP，宽 1.0，alpha = 1.0
```

**被选中**（MODULE 模式）：额外一圈虚线环，半径 `r + 6·S`，`stroke = INK`，
`alpha 0.85`，宽 1，`dasharray = "2, 3.5·S"`。

**圆内文字**：

```
模块名   x = cx, y = cy − 2·S,   anchor = middle, fs = fs_node (11S), weight 600
数值     x = cx, y = cy + 12·S,  anchor = middle, fs = fs_node_val (10S), weight 400（DATA 字体）
```

- 亮着时：名 `alpha = A_NODE + (1−A_NODE)·breath`（0.68 → 0.96）；
  值 `alpha = A_VAL + 0.20·breath`（0.60 → 0.80）
- 灭着时：两者都用 `A_OFF`（0.56）

> **光晕下限是 0.10，不是 0。** 亮着的模块**任何时候都不该看起来是灭的** ——
> 呼吸是"脉动"不是"开关"。实测四相位峰值 0.10 / 0.18 / 0.25 / 0.32。

### 6.5 哪个模块算"亮"

**唯一判据放在面板里**（不是放在调用方），这样编辑器和离线渲染共用同一份：

```cpp
// TranePanel.h 已经有这个函数，照旧用
bool moduleIsOn(int node, const PanelState& st);
```

| 模块 | 判据 |
|---|---|
| 有 `*_on` 开关的七个（freeze / grain / stutter / comb / tape / sweep / delay） | 看那个 BoolParam |
| **RUIN** | `ruin_mode > 0.02`（mode = 0 就是纯干声，等于没开） |
| **SPACE** | `space_mix > 0.02` |
| **OUT** | 恒亮（它是输出） |

> 注意 `freeze` 的开关默认也是 **false**，不要特判。

---

## 7 · 参数检查器

### 7.1 顶栏（y = 34·S，高 26·S）

三组控件，**都是 26·S 高、直角**：

```
左：x = PANE_X0 (422)                        items = ["ALL", "MODULE"]     w = 168
右：x = PANE_X0 + PANE_W − 168 = 1244        items = ["1", "2", "3", "4"]  w = 168
                                              MODULE 模式下可用；ALL 模式下 disabled
中：x = 788（常量，**不跟分割线走**）          背景图那一组，见 §13
```

> 中段那组是 **v0.31 加的**，位置右对齐到列数组左边（1244 − 32 − 424 = 788）而不是
> 左对齐到模式组右边：分割线拖到最右（560）时模式组会长到 758，左对齐就会被压住；
> 而列数组的左缘恒为 1244，与分割线无关。

**视图标题**（y = 84·S）：

```
ALL     →  "ALL PARAMETERS"
MODULE  →  "MODULE PARAMETERS"
副标题   →  "{实际画出来的控件数} CONTROLS"       ← 必须**算出来**，不许写死
```

- 标题：`fs_head` 17S，weight 600，`A_TEXT`
- 副标题：`fs_sub` 11S，weight 400，`A_MUTED`，y = 84S + fs_sub × 2.1

### 7.2 竖分割线（x = 392·S）

```
线   从 y = 24·S 到 y = h − 24·S，stroke = SEP，宽 1
抓手 一个 2×52S 的矩形，居中于 h/2，fill = INK，alpha 0.28   ← 可拖
```

### 7.3 两种模式

| 模式 | 内容 | 列 |
|---|---|---|
| **ALL** | 全部 10 个模块 | **3 列**，3 + 3 + 4 |
| **MODULE×n** | 4 个候选模块里取前 n 个 | n 列（1 / 2 / 3 / 4） |

```cpp
ALL_LANES = { {"freeze", "grain", "stutter"},
              {"comb",   "tape",  "ruin"},
              {"sweep",  "delay", "space", "out"} };
// **展平后必须等于 CHAIN** —— 从左到右、从上到下的阅读顺序就是信号顺序

SELECTED = { "grain", "stutter", "comb", "tape" };   // MODULE 模式的候选集
// **必须是 CHAIN 的一段连续切片** —— 不许跳着挑
```

> **为什么 `SELECTED` 从 `grain` 起、不从链头 `freeze` 起**：量过。
> 行距是按每列自己的行数解出来的，行数少的列会被拉得很开：
> `freeze` 3 行 → 271.0px、`out` 2 行 → 542.0px、`grain` 9 行 → 67.8px。
> 271px 的行距意味着两个参数孤零零挂在 720px 高的面板上 —— 那不是留白，是空。

### 7.4 每一行的结构

一行 = **模块标题行** 或 **参数行**。**列内**按 `kControls[]` 的顺序自上而下。

#### 模块标题行

```
模块名 = 标题**本身就是开关**（有开关的七个模块）
         文字   x = 列左缘, y = mid + fs_h × 0.35, fs = fs_title, weight 600
               亮 = A_TEXT 1.00 ；灭 = A_OFF 0.56
         方块   紧跟名字：x = 列左缘 + len(模块名) × K_LABEL × fs_h + GAP
               边长 = fs_h × 0.78，垂直居中于 mid
               亮 = INK @ (0.80 + 0.20·breath) ；灭 = FILL @ 1.0
               **无描边**
```

> **`ruin` / `space` / `out` 三个模块压根没有开关参数**（41 参数 + 7 开关），
> 所以它们**只画标题、不画状态方块** —— 不许假装有开关。

#### 参数行

三格：**参数名 ─ 轨道 ─ 数值**，格间一个 `GAP`。

```
x_name  = 列左缘
x_track = 列左缘 + label_w + GAP
x_value = x_track + track_w + GAP
```

**参数名**：`full_name(c)` 大写全称，`fs_label` 11S，weight 400，`A_MUTED` 0.60
（关闭态用 `A_OFF` 0.56）。

**轨道**（普通参数）：

```
底     x = x_track, y = mid − th/2, w = track_w, h = th
       fill = FILL (systemFill)
       th = max(2.0·S, fs_label × 0.30)         ← 由**字号**定，不跟行高走
当前值 主内容色填充，从左往右，宽度 = norm(value) × track_w
       **没有圆形把手**（只靠颜色编码）
出厂值 一根**常显的细刻度**（不表示当前值，只给一个参照），fill = INK @ A_TICK (0.30)
```

> `th` 必须由字号定。跟着行高走的话，行数少的列轨道会明显比行数多的列粗，
> 同一张面板上出现两种粗细。

**轨道**（`Fmt::Choice` 类型，只有 `sweep_mode` 一条）：改成 3 段分段块

```
底     h = choice_h = fs_label × 1.45，fill = SEG_BG (tertiarySystemFill)
选中块 宽 = track_w/3，fill = GRAY2 (#636366)，**不透明**
       pos = round(def × 2)，clamp 到 0..2
标签   ["LP", "BP", "HP"]，居中于各自分格，fs = fs_value × 0.82，weight 500
       选中的 = A_TEXT 1.00 ；其余 = 参数名当前的不透明度
模块关着时**不画选中块** —— Apple 的禁用控件是"摊平"的，不是"变暗的"
```

**数值**：`value_text(c)`，`fs_value` 12S，weight 500，`A_TEXT` 1.00，`DATA` 字体。
**右对齐到列的右缘**（`x = 列左缘 + col_w`，`text-anchor = end`），
这样一列里的数值右边是齐的，扫一眼就能比大小。

数值格式（照 `TranePanel.h` 的 `Fmt` 枚举）：

| `Fmt` | 格式 | 例 |
|---|---|---|
| `Ms` | `≥10` 取整 + `MS`，否则 1 位小数 + `MS` | `250MS` / `9.5MS` |
| `Plain0` | 0 位小数 | `220` |
| `Plain2` | 2 位小数 | `0.60` |
| `Rate1` | 1 位小数 | `4.0` |
| `KHz1` | ÷1000，1 位小数 + `K` | `1.2K` |
| `Db1` | 带符号 1 位小数 + `DB` | `+0.0DB` |
| `Choice` | `["LP","BP","HP"][round(v×2)]` | `BP` |

### 7.5 48 条控件表（照抄，一条不许改）

> 这一份**只是对照用的**。唯一事实来源是 `TranePanel.h` 的 `kControls[]` ——
> **改界面时以那个数组为准逐条对账**。

| # | 模块 | 参数 ID | 显示名 | 环位 | 单位 | 格式 | 范围 | 默认 |
|---|---|---|---|---|---|---|---|---|
| 0 | freeze | `freeze` | Freeze | **开关** | | None | | |
| 1 | freeze | `loop_ms` | Loop | 0 | ms | Ms | 20–2000 | 250 |
| 2 | freeze | `seam_ms` | Seam | 1 | ms | Ms | 0–40 | 10 |
| 3 | grain | `grain_on` | Grain | **开关** | | None | | |
| 4 | grain | `grain_size` | Grain Size | 0 | ms | Ms | 5–500 | 120 |
| 5 | grain | `grain_density` | Grain Density | 1 | gr/s | Plain0 | 0.5–100 | 12 |
| 6 | grain | `grain_position` | Grain Position | 2 | | Plain2 | 0–1 | 0.5 |
| 7 | grain | `grain_spray` | Grain Spray | 3 | | Plain2 | 0–1 | 0.15 |
| 8 | grain | `grain_rate` | Grain Rate | 4 | x | Plain2 | 0.25–4 | 1.0 |
| 9 | grain | `grain_spread` | Grain Spread | 5 | | Plain2 | 0–1 | 0.6 |
| 10 | grain | `grain_reverse` | Grain Reverse | 6 | | Plain2 | 0–1 | 0.25 |
| 11 | grain | `grain_mix` | Grain Mix | 7 | | Plain2 | 0–1 | 1.0 |
| 12 | stutter | `stutter_on` | Stutter | **开关** | | None | | |
| 13 | stutter | `stutter_size` | Stutter Size | 0 | ms | Ms | 5–500 | 90 |
| 14 | stutter | `stutter_rate` | Stutter Rate | 1 | Hz | Rate1 | 0.25–30 | 4.0 |
| 15 | stutter | `stutter_jump` | Stutter Jump | 2 | | Plain2 | 0–1 | 0.35 |
| 16 | stutter | `stutter_mix` | Stutter Mix | 3 | | Plain2 | 0–1 | 1.0 |
| 17 | comb | `comb_on` | Comb | **开关** | | None | | |
| 18 | comb | `comb_tune` | Comb Tune | 0 | Hz | Plain0 | 20–4000 | 220 |
| 19 | comb | `comb_feedback` | Comb Feedback | 1 | | Plain2 | 0–0.95 | 0.6 |
| 20 | comb | `comb_mix` | Comb Mix | 2 | | Plain2 | 0–1 | 0.5 |
| 21 | tape | `tape_on` | Tape | **开关** | | None | | |
| 22 | tape | `tape_speed` | Tape Speed | 0 | x | Plain2 | 0–2 | 1.0 |
| 23 | tape | `tape_wobble` | Tape Wobble | 1 | | Plain2 | 0–1 | 0.12 |
| 24 | tape | `tape_mix` | Tape Mix | 2 | | Plain2 | 0–1 | 1.0 |
| 25 | ruin | `ruin_mode` | Ruin Mode | 0 | | Plain2 | 0–1 | 0.0 |
| 26 | ruin | `ruin_drive` | Ruin Drive | 1 | | Plain2 | 0–1 | 0.35 |
| 27 | ruin | `ruin_fold` | Ruin Fold | 2 | | Plain2 | 0–1 | 0.0 |
| 28 | ruin | `ruin_crush` | Ruin Crush | 3 | | Plain2 | 0–1 | 0.0 |
| 29 | ruin | `ruin_ring` | Ruin Ring | 4 | | Plain2 | 0–1 | 0.0 |
| 30 | sweep | `sweep_on` | Sweep | **开关** | | None | | |
| 31 | sweep | `sweep_rate` | Sweep Rate | 0 | Hz | Plain2 | 0.01–20 | 0.8 |
| 32 | sweep | `sweep_depth` | Sweep Depth | 1 | | Plain2 | 0–1 | 0.4 |
| 33 | sweep | `sweep_center` | Sweep Center | 2 | Hz | KHz1 | 60–12000 | 1200 |
| 34 | sweep | `sweep_reso` | Sweep Reso | 3 | | Plain2 | 0–1 | 0.3 |
| 35 | sweep | `sweep_mode` | Sweep Mode | 4 | | **Choice** | 0–1 | 0.0 |
| 36 | delay | `delay_on` | Delay | **开关** | | None | | |
| 37 | delay | `delay_time` | Delay Time | 0 | ms | Ms | 20–2000 | 375 |
| 38 | delay | `delay_feedback` | Delay Feedback | 1 | | Plain2 | 0–0.92 | 0.45 |
| 39 | delay | `delay_damp` | Delay Damp | 2 | | Plain2 | 0–1 | 0.35 |
| 40 | delay | `delay_pingpong` | Delay PingPong | 3 | | Plain2 | 0–1 | 0.0 |
| 41 | delay | `delay_mix` | Delay Mix | 4 | | Plain2 | 0–1 | 0.35 |
| 42 | space | `space_mix` | Space Mix | 0 | | Plain2 | 0–1 | 0.55 |
| 43 | space | `space_size` | Space Size | 1 | | Plain2 | 0–1 | 0.7 |
| 44 | space | `space_tail` | Space Tail | 2 | | Plain2 | 0–1 | 0.8 |
| 45 | space | `space_damp` | Space Damp | 3 | | Plain2 | 0–1 | 0.4 |
| 46 | space | `space_diffuse` | Space Diffuse | 4 | | Plain2 | 0–1 | 0.7 |
| 47 | out | `output` | Output | 0 | dB | Db1 | −24–12 | 0.0 |

**合计 48 条** = 41 个环位参数 + 7 个模块开关。
`+1` 个 JUCE 自动加的 Bypass = 宿主里 49 个参数。

**按模块分的行数**（用于副标题计数与行距求解）：

| 模块 | freeze | grain | stutter | comb | tape | ruin | sweep | delay | space | out |
|---|---|---|---|---|---|---|---|---|---|---|
| 环位参数 | 2 | 8 | 4 | 3 | 3 | 5 | 5 | 5 | 5 | 1 |
| 开关 | 1 | 1 | 1 | 1 | 1 | 0 | 1 | 1 | 0 | 0 |
| **总行数** | 3 | 9 | 5 | 4 | 4 | 5 | 6 | 6 | 5 | 1 |

---

## 8 · 交互四态与动效

### 8.1 四态

**硬规则：状态只改颜色，不改几何。** 四态里所有文字的 `(x,y)` 与所有矩形的
`(x,y,w,h)` 必须**逐字节相同**。

| 状态 | 触发 | 变化 |
|---|---|---|
| `idle` | 常态 | — |
| `hover` | 鼠标在这一行上 | 行底一层 `INK @ HOVER_A (0.06)`；参数名 `0.60 → 0.80` |
| `press` | 正在按 | 行底 `INK @ PRESS_A (0.12)`（**= hover 的 2 倍**）；参数名 → `1.00` |
| `focus` | 键盘走到这一行 | **不绘制额外视觉框**；保留焦点用于键盘导航与参数微调 |

```cpp
HOVER_A       = 0.06f;   // 行底墨层
PRESS_A       = 0.12f;   // 必须是 hover 的 2 倍以上，否则读不出"按住了"
A_HOVER_NAME  = 0.80f;
ROW_BAND      = 0.80f;   // 行底高度 = 行距 × 0.80
```

**行底矩形的几何**：

```
x = 列左缘 − GAP×0.5
y = mid − (pitch × ROW_BAND)/2
w = col_w + GAP
h = pitch × ROW_BAND
```

**聚焦态的视觉规则（v0.32）**：焦点不再有额外几何。`state_.focus` 仍然记录
当前键盘目标，方向键和拖动参数仍照常工作，但 `drawInspector` 不画蓝色描边，也不
改变行的位置、轨道尺寸或布局。这样焦点不会在调参时形成蓝框，同时不牺牲键盘可操作性。

**行底会改变文字的底色**，所以对比度检查必须把 `hover` / `press` 的底也纳入 ——
`SEG_BG` 是半透明的（α = 0.24），行底会透上来。

### 8.2 动效（Apple HIG · Motion）

| 动作 | 时长 | 曲线 |
|---|---|---|
| hover / press 的反馈 | **0.12 s** | `cubic-bezier(0.2, 0, 0, 1)` |
| 模块开关 / 模式切换（低频） | **0.20 s** | 同上 |
| **拖参数** | **0.00 s** | — |
| 上限 | 0.30 s | HIG 的 "brief" 上限；超过就不是反馈而是表演了 |
| **"减弱动态效果"打开时** | **× 0.0** | 精确归零，不是"变小" |

```cpp
MOTION_FAST   = 0.12f;
MOTION_STD    = 0.20f;
MOTION_DRAG   = 0.00f;    // **这条是规则，不是遗漏**
MOTION_EASE   = cubic-bezier(0.2, 0, 0, 1);   // 减速曲线：起步快、收尾稳
MOTION_MAX    = 0.30f;
REDUCE_MOTION_SCALE = 0.0f;
```

> 拖参数**不加动效**，依据是 HIG 原文：
> `generally avoid adding motion to UI interactions that occur frequently`。

### 8.3 呼吸

`PanelState::time`（秒）驱动。`breath` 是 0..1 的相位：

```
breath = 0.5 − 0.5·cos(2π · time / PERIOD)      // 或等效的平滑往复
```

呼吸影响三处：

1. 亮着的质点圆的光晕峰值：`0.10 + 0.22·breath`
2. 亮着的质点圆的描边不透明度：`0.62 + 0.38·breath`
3. 亮着的质点圆内的文字（名 / 值）
4. **只有"通过档"的信号线**：`× (0.85 + 0.15·breath)`

**静止档的信号线绝不参与呼吸。**

---

## 9 · 数据接口

### 9.1 `PanelState`（已存在，照旧）

```cpp
struct PanelState {
    float value[kMaxControls]{};        // 归一化 0..1，下标 = kControls 的下标
    float moduleActivity[kMaxNodes]{};  // 0..1，这个模块"当前有多忙"
    int   focus = -1;                   // 正在拖拽/聚焦的控件下标；-1 = 无
    float time  = 0.0f;                 // 秒，驱动呼吸
};
```

### 9.2 值 → 归一化

```cpp
float norm(const ControlSpec& c, float raw) {
    return (raw - c.min) / (c.max - c.min);
}
```

### 9.3 `lit`（哪些模块在响）怎么来

**界面上只有一份判据**：`moduleIsOn(node, st)`。

`PanelState::moduleActivity` 只调制**发光强度**，不决定"亮不亮"。
调用方应先把整条数组填成 `1.0`（"在响"），再用真实遥测覆盖：

```
freeze → uiFreezeActive
grain  → min(1, voices / 12)
out    → 1 − uiGainReduction
tape   → min(1, |speed − 1| × 4)
其余模块没有遥测，保持 1.0 就是诚实的 ——
界面不知道它忙不忙，只知道它开着。
```

`lit` 就是"`moduleIsOn(node)` 为真的那些模块名"的集合。

### 9.4 `PluginEditor` 要改的

```cpp
constexpr int kBaseW = 1440;   // 原来是 panel::geom::kPanelW = 544
constexpr int kBaseH = 720;    // 原来是 panel::geom::kPanelH = 988

// 宽高比锁死 2:1（原来锁的是 544/988）
if (auto* c = getConstrainer())
    c->setFixedAspectRatio(static_cast<double>(kBaseW) / static_cast<double>(kBaseH));
```

`geom::kPanelW` / `kPanelH` 也要跟着改成 1440 / 720，
否则 `panel_probe` 与编辑器会各说各话。

---

## 10 · 实现完必须能过的自检

写完之后，**逐条跑一遍**。每一条都对应一个真实的、踩过的坑。

### 10.1 结构类

- [ ] 面板上没有任何**描边矩形或彩色像素**（v0.32 起聚焦蓝框也不再绘制）
- [ ] SVG/C++ 里**没有 `rx=` / 圆角**（分段控件必须直角）
- [ ] `ACCENT` 出现 ⟺ 当前状态是 `focus`（其它三态一个像素都不许有它）
- [ ] 四态里所有文字的 `(x,y)` 与所有矩形的 `(x,y,w,h)` **逐字节相同**
- [ ] 参数名**全称大写**；41 条里没有重名
- [ ] 参数**显示名全局唯一**（宿主按名查找只认第一个）
- [ ] `ruin` / `space` / `out` **只画标题，不画开关方块**

### 10.2 排版类

- [ ] 所有尺寸 = 基准 × S；画布比例 ≠ 2:1 时**直接报错**，不许兜住
- [ ] 字号只出现 13 / 12 / 11 三档（× S × scale_fit），字重只出现 600 / 500 / 400
- [ ] 放不下时三档**一起缩**（不许某一档单独变）
- [ ] 组间空档 = 行距 × 2.5（明显大于组内 8px）
- [ ] **末行跨列对齐**（量的是**文字基线**，不是行框底边）
- [ ] 对比度全部 ≥ 4.5:1（含 hover / press 的行底、`SEG_BG` 上的标签）

### 10.3 树 / 动线类

- [ ] 节点顺序 == `TraneEngine.cpp::process()` 的顺序，**逐项对账**
- [ ] 节点 y 在信号链顺序下**单调不减**；落 **7 层**
- [ ] `SIGNAL_PATH` 是 `CHAIN` 的**相邻对推导**，不是手写的
- [ ] 信号层相对骨架层**恰好多 1 条**（`stutter → comb`）
- [ ] 信号层**0 处自交**；只向下；恰好 **3 处同层横跨**
- [ ] 骨架 **22 条**全带 `dasharray`；信号 **9 条**全不带
- [ ] 每条信号线的渐变起点 == 线自己的起点（**方向不许反**）
- [ ] 每条线的起点离**上游**质点更近（横跨的那 3 条 y 相等，只能这样量）
- [ ] `GRID_OP < TRUNK_OP < SIG_REST_LO < SIG_REST_HI < SIG_HOT_LO < SIG_HOT_HI`
- [ ] `TRUNK_OP / GRID_OP ≥ 1.5`
- [ ] `SIG_REST_LO / TRUNK_OP ≥ 1.5`
- [ ] `SIG_REST_HI / GRID_OP ≥ 3.0`
- [ ] **`SIG_HOT_LO × SIG_BREATH_MIN > SIG_REST_HI`** ← 这条就是"高亮"本身
- [ ] `SIG_HOT_HI / SIG_REST_HI ≥ 1.5`
- [ ] **静止档的渐变在 `breath = 0` 与 `breath = 1` 下逐字节相同**（不许呼吸）
- [ ] **通过档的渐变在 `breath = 0` 与 `breath = 1` 下必须不同**（必须呼吸），且条数 == 由 `lit` 算出来的条数
- [ ] `ALL_LANES` 展平 == `CHAIN`；`SELECTED` 是 `CHAIN` 的**连续切片**

### 10.4 反向对照（**这一条最重要**）

**绿本身不是证据。** 每加一条断言，都要**故意改坏一处关键逻辑，确认它真的报红**，再还原。

`vst/tools/check_contrast_mutations.py` 里已经有 **49 条 + 1 个对照组**，
跑法见 §11。新增断言时要顺手加一条对应的突变，并跑一遍确认它被抓到。

**四种"假绿"，都踩过，实现时都要防：**

1. **覆盖漏洞** —— 分支没被执行（`sweep_mode` 是唯一 Choice，而 `sweep` 不在演示用的 `lit` 里，
   于是"选中"那一支从没跑到）
2. **断言写在循环体里** —— 某个 `state` 分支从没跑到，循环体里的断言等于没写
3. **突变原文落在注释 / 文档字符串里** —— `.replace(old, new, 1)` 换的是**第一次出现**，
   锚点落在注释上时，常量根本没动、断言一声不响，然后被记成"漏网"
4. **被上游断言先抓住 = 下游断言没被验过** —— 每条新断言都要配一条"绕开它前面那些"的突变

> **另外两条容易忘的**：
> · **不透明度 ≠ 屏幕亮度。** 判断"看不看得见"必须把图渲染成 PNG 再量像素。
>   `α = 0.07` 的点线渲染出来只有 **25/255** —— 常量写得再合理，也得量。
> · **裁切一张 SVG 时，`width` / `height` / `viewBox` 三个属性要一起换。**
>   只改 `viewBox` 的话，`preserveAspectRatio`（默认 `xMidYMid meet`）
>   会把内容缩小居中。

---

## 11 · 参考产物与验证命令

### 11.1 设计稿的 9 张产物

| 文件 | 内容 |
|---|---|
| `outputs/Trane_UI_v0.30.png` | 总览（把下面几张拼在一起） |
| `outputs/Trane_UI_v0.30_all.png` | ALL 模式整面板 |
| `outputs/Trane_UI_v0.30_module1..4.png` | MODULE×1/2/3/4 |
| `outputs/Trane_UI_v0.30_states.png` | 交互四态接触表 + 动效规格表 |
| `outputs/Trane_UI_v0.30_breath.png` | 呼吸四个相位 |
| `outputs/Trane_UI_v0.30_flow.png` | **动线对照稿：静止态 vs 通过态** |

### 11.2 命令

```bash
export PATH=/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin:$PATH
cd vst

# 设计稿自检（不出图，十几秒）
python tools/render_ui_dark_panel.py --check-only

# 反向对照：故意改坏 49 处，确认自检真的报红
python tools/check_contrast_mutations.py

# 全量重出图
python tools/render_ui_dark_panel.py --version 0.30

# 完整门禁（构建 → pytest → 面板像素分析 → 设计稿自检 → 端到端）
./run_tests.sh
```

### 11.3 设计稿实现的位置

| 内容 | 函数 |
|---|---|
| 全部设计令牌 | `render_ui_dark_panel.py` 第 159–500 行 |
| 度量 / 列宽推导 | `metrics()` · `columns_for()` · `extents()` |
| 树几何 | `tree_layout()` |
| 树的绘制（三层） | `tree_svg()` |
| 控件绘制 | `segmented()` · `track_h()` · `choice_h()` · `module_head()` · `param_row()` |
| 行定位 | `row_pitch()` · `module_layout()` · `all_layout()` |
| 顶栏 | `tabs()` · `heading()` · `divider()` |
| 面板组装 | `panel()` |
| 动线对照稿 | `flow_tree()` · `flow_html()` |
| 自检 | `self_check()` |

**改设计稿时改的是这些函数；改插件时对着它们写 C++ 就行。**
两边的绘制代码应当**逐行对得上** —— 这样离线渲染出来的 PNG 才等于插件里画的东西。

---

## 12 · 落地顺序建议

1. **先改几何常量**：`geom::kPanelW/H` → 1440/720；`PluginEditor` 的 `kBaseW/H`
   与 `setFixedAspectRatio`。
2. **换颜色令牌**：把浅色的一套（`#FAFAF9` / `#0E0E0F` / `#0ABAB5`）整组换成 §3 的表。
3. **改树的绘制**：从"辐条 + 环形文字"换成"质点圆 + 骨架点线 + 信号实线"。
   这一步改动最大，**先只画骨架**，确认 22 条位置对了，再叠信号层。
4. **加参数检查器**：顶栏 → 分割线 → 列 → 行。先只做 ALL 模式，再做 MODULE×n。
5. **加交互四态**：`PanelState::focus` 已经有，接上 hover / press。
6. **接动效**：按 §8.2 的时长表。
7. **跑门禁**：`./run_tests.sh`。`vst/tests/test_editor_layout.py` 里有静态断言，
   改坏了会直接报红。

**每一步都要能单独跑通再往下走。** 一次性全改完再调，出了问题分不清是哪一层的。

---

## 附 · 一句话总结

**左边一棵树，信号从上往下流；右边的检查器读起来也是从上往下、从左往右。
骨架 22 条全留着（点线，最淡），信号 9 条叠上去（实线 + 渐变）。
有信号在过的那几条直接抬起来、跟着呼吸 —— 剩下的原样不动。
没有一个边框，没有第二种彩色，字号只有三档。**

---

# 附篇 · v0.31 背景图（用户自己上传的那张）

> 这一篇是 **v0.31** 加的。v0.30 那部分（§1–§12）**一个字都没改**，
> 只有 §7.1 的顶栏多了一组控件（已就地更新）。

## 13 · 需求

小绪的原话：

> 「给我在里面做个功能可以自己上传自己喜欢的图片作为背景，
> 并且可以选择图片背景在树那里还是参数那里，可以调整图片明暗度来适配」

拆成四件：

1. 用户能选一张本地图片；
2. 能选这张图垫在**树区**还是**参数区**（还能关掉）；
3. 能调**明暗度**适配；
4. 关掉插件再打开，这三件事都还在。

## 14 · 数据模型（这是整个设计的支点）

**背景图是 `PanelState` 的一部分，不是"面板去读的一个文件"。**

```cpp
enum class BgWhere { Off = 0, Tree, Params };

struct Backdrop {
    juce::Image image;                 // 原图（未缩放未压暗）；无效 = 没有图
    BgWhere where = BgWhere::Off;
    float brightness = 1.0f;           // 0.25 … 4.0
    juce::String name;                 // 文件名，只用来显示，不参与绘制
    bool active() const { return where != BgWhere::Off && image.isValid(); }
};
```

为什么必须这样：**面板层的可验证性建立在"离线渲染的输入 = PanelState"上。**
`panel_probe` 用和插件完全相同的绘制代码把面板渲成 PNG 做像素分析，前提是它的
输入**完整地**只有一个 `PanelState`。面板层一旦自己去读文件，"这一帧画的是什么"
就取决于磁盘状态 —— 同一份 PanelState 在另一台机器上会画出别的图，像素检查当场
失去意义。

所以：**读文件是 `PluginEditor` 的职责**（它本来就在宿主进程里），它把读好的
`juce::Image` 塞进 `Backdrop`。有测试盯着这条界线：

- `test_panel_layer_never_touches_the_filesystem`：`TranePanel.{h,cpp}` 里不许出现
  `juce::File` / `ImageFileFormat` / `loadFrom` / `FileChooser` / `ImageCache` /
  `FileInputStream`；**同时**要求 `PluginEditor.cpp` 里必须有
  `FileChooser` 和 `ImageFileFormat::loadFrom` —— 少了后半句，那条断言在
  "谁都没读文件"的死版本上也会通过。

## 15 · 落位区（两个都是编译期常量）

```cpp
kBgTreeX = 30      kBgTreeW = 332      // 树的包围盒
kBgPaneX = 416     kBgPaneW = 996      // 分割线能拖到的最左位置对应的参数区
```

**参数区不跟分割线走。** 一开始是跟的（"垫在参数那里"，线一移参数区就移了），
实测之后推翻了：跟着走的话，每拖一帧就要把源图重新高质量缩放一次 ——
3000×3000 的源图在 2× 屏幕上 **28.7 ms/次**，拖起来必卡。

而换来的视觉精度几乎是零：背景四边有 **64px 的羽化**，边缘本来就在化开，
落位差几十像素根本看不出来。取"分割线能拖到的最左位置"对应的那一段，
于是无论线拖到哪儿，背景都盖得住整个参数区。

代价：分割线拖到最右（560）时，背景会从 416 铺到 590 那一段露在参数区左边。
那段是空白，看起来就是"背景比参数区宽一点"，不刺眼。

**像素证据**（`check_panel_render.py`）：在 y ∈ [10, 18] 这条带子里
（唯一一条既没有文字、也没有顶栏、也没有分割线的横带），
分割线 386 与 560 两张图**逐像素相同**。

## 16 · 明暗度

```
peak = kBgPeakBase × brightness        kBgPeakBase = 22（世界树骨架点线的 p99，实测）
brightness ∈ [0.25, 4.0]               几何级数，1.0× 落在轨道正中
```

上限 4.0× 是**推出来的**，不是拍的：峰值 = 22 × 4 = 88；
参数文字 235 对 88 的对比度是 **5.97:1**，过 WCAG AA（4.5:1）。**不许再抬。**

**映射是几何级数，不是线性**（`brightToTrack` / `trackToBright`，唯一一份实现）：

```
brightToTrack(b) = log(b / 0.25) / log(16)      →  1.0× 正好在 0.5
trackToBright(t) = 0.25 × 16^t
```

线性映射会把 0.25…1.0 挤进轨道左边 20%、1.0…4.0 独占 80% —— 想调暗一点根本点不准。

**交互是绝对位置映射**：点轨道哪儿就是哪儿的亮度，不是相对拖拽。
好处有二：单击能直接跳到某一档；同一个 x 点两次结果相同，
于是双击依然满足"做两遍等于没做"这条既有约定。

## 17 · 绘制管线与性能（v0.31 最花心思的地方）

三层，**顺序是硬规矩**：

```
面板底（纯黑）→ 背景图（缩放 + 羽化 + 压暗）→ 骨架点线 → 信号线 → 圆 → 检查器
```

背景必须在骨架**之下**（小绪：「生命树的所有骨架全部保留」）——
骨架是 alpha 0.13 的点线，压到图下面就是整片消失，而且面板上剩下的东西
看起来照样"像树"。有 `test_backdrop_is_drawn_under_the_skeleton` 盯着顺序。

### 17.1 两级缓存

源图的高质量缩放是整条链上最贵的一步，而它**只在（源图 / 落位 / 尺寸）变化时**
才需要重做。明暗度只是换一个乘数，不该逼它重来。所以 `PanelCache` 里有两层：

| 层 | 内容 | 什么时候作废 |
|---|---|---|
| `bdScaled` | 源图 → 缩放 + 羽化，**峰值固定 = 88** | 源图 / 落位 / 尺寸变了 |
| `backdrop` | 面板底 + `bdScaled` 按明暗度压暗 + 骨架点线 | 上面任一 + 明暗度变了 |

压暗那一步走 `tintRegion()`：**在已经贴好的那块像素上原地乘**一个 8.8 定点系数。
不用 `setOpacity` + `drawImage` 是因为 JUCE 的**带 alpha** 图像渲染走通用路径
（浮点混合），实测 2880×1440 上 10.7 ms，而这个整数循环只要 2.3 ms。

### 17.2 实测（2880×1440、参数区、3000×3000 源图）

| 路径 | 什么时候走 | 耗时 |
|---|---|---|
| 冷：面板底 + 源图缩放羽化 + 骨架 | 换图 / 换落位 / 改窗口尺寸 | **25.9 ms** |
| 热：只重贴 + 原地乘 | 拖明暗度（每帧） | **1.75 ms** |
| 拖分割线 | 拖分割线（每帧） | **0**（落位是常量，缓存不失效） |

拆缓存层之前，拖明暗度每帧 28.7 ms —— 30Hz 一帧只有 33 ms，必卡。

**门槛写在 `check_panel_render.py` 里**，而且用的是**相对判据**：

```
热 / 冷 ≤ 0.5          ← 绝对值会随机器漂移，比值才说明"缓存到底有没有生效"
热 ≤ 8 ms
冷 ≤ 60 ms
```

## 18 · 顶栏那一组控件（x = 788 起，共 424 宽）

```
┌ 选择图片 ─┐   ┌ 关 │ 树 │ 参数 ┐   ────●────   1.0×
   112            120（三格）          112         44
```

| 件 | 宽 | 视觉 |
|---|---|---|
| ① 「选择图片」格 | 112 | 有图显示文件名（放不下就省略号），没图显示「选择图片」 |
| ② 落位三格 | 120 | 与模式组同一套分段控件语言（选中 `kGray2`，未选 `kSegBg`） |
| ③ 明暗度轨道 | 112 | 轨道高 4（与参数行同档），填充 = `kInk` 0.80（hover/press 时 1.00） |
| ④ 倍率读数 | 44 | `< 1.0` 给两位小数（`0.25×`），否则一位（`1.0×` / `4.0×`） |

- 轨道上的 **1.0× 基准刻度**落在正中（几何映射），与参数行的"出厂值刻度"同一套
  （`kInk.withAlpha(kATick)`，非文字）。
- 没有图 / 落位为关时，轨道与读数**摊平**（Apple 的禁用态是"摊平"不是"变暗"）。
- 命中区用**整格高** —— 轨道只有 4px，按 4px 命中的话根本点不着。

**不引入任何新的图形语汇**：这一块面板从 v0.10 起就没有一条装饰性边框，
背景控件也照旧 —— 面用 `kSegBg`/`kGray2`/`kFill`，文字用两档不透明度。

## 19 · 持久化：只存路径，不存图

三个值存在 `apvts.state` 的**根属性**上（`backdropPath` / `backdropWhere` /
`backdropBright`），于是 `copyState()` 自动带上、`replaceState()` 自动恢复，
不用另开一套序列化。

**为什么不存图**：把几 MB 的图片塞进宿主工程文件会让每个实例都膨胀几 MB，
而且宿主每次保存 / 加载都要 base64 编解码一遍。存路径的代价是"文件被移走 /
删掉就没了" —— 这比塞图片诚实得多。

编辑器每帧对一次这三个值（宿主可能在我们打开之后才把状态塞回来：撤销 / 重做、
加载预设、恢复工程）。自己写进去的那份也要记成"宿主那份"，否则下一帧会把它
当成外部改动再走一遍。

## 20 · 这一版的坑（都踩过）

- **`juce::String{argv[i]}` 按 Latin-1 解释 `char*`**，不是 UTF-8。
  中文文件名会被解成 `U+00E8 U+0083 U+008C …`，于是 `existsAsFile()` 永远为假，
  而报错信息里打出来的是"看起来差不多"的乱码。命令行工具里必须
  `juce::String::fromUTF8(argv[i])`。
- **`setOpacity` + `drawImage` 比整数原地乘慢 4.6 倍**（见 §17.1）。
- **明暗度不能靠"绝对亮度"去量** —— 参数区里全是 235 的文字，
  绝对值的 max 量到的永远是文字。要用"与不带背景的差值"。
- **`bake_backdrop.py` 的管线顺序是硬规矩**：先缩放 → 再羽化 → 最后量化。
  1-bit 源图先量化会整片消失。
- **双击会送两次 `mouseUp`** —— 「选择图片」开两次系统对话框显然不满足
  "做两遍等于没做"，所以它带一个 `choosing_` 闸。

## 21 · 验收

`cd vst && ./run_tests.sh`，其中与背景有关的是：

- `check_panel_render.py` 里 25 条背景断言（落位 / 不越界 / 明暗度单调 / 峰值上限 /
  没盖住文字 / 边缘是羽化的 / 拖分割线不动背景 / 冷热两条耗时）；
- `check_backdrop_mutations.py`：**5 处突变 5/5 被抓住**
  （落位搞反 / 明暗度方向搞反 / 拿掉羽化 / 缓存判据漏项 / 背景盖到骨架上面）。

**绿本身不是证据** —— 那 25 条是不是真的在量东西，只有"改坏一处看它报不报"能回答。

## 22 · v0.32 聚焦反馈调整

用户实际打开插件后反馈：调节参数时出现的蓝框干扰操作。复现确认该蓝框来自
`TranePanel.cpp` 中 `RowState::Focus` 的 `kAccent` 描边，聚焦态基线约有 656 个
`#0A84FF` 像素。v0.32 移除该绘制分支，离线渲染复核为 0 个蓝色像素。

这不是删除焦点机制：`state_.focus`、Tab / 方向键导航、回车切换和参数微调全部保留。
变化仅限视觉反馈：focus 与 idle 一样不画额外边框；hover / press 继续使用墨色透明度。
护栏新增“focus 必须 0 个强调色像素”，并把版本号从 0.31.0 bump 到 0.32.0。
