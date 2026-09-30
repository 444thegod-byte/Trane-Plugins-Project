#!/usr/bin/env python3
"""⚠️ v0.32 的 HTML 设计稿 —— **已退役（2026-09-29），门禁不再调用它。别去修它。**

为什么留着：这个文件是 v0.19–v0.32 那版面板（世界树 / 22 条骨架点线 /
9 条信号线 / MODE·列数切换）的**独立第二实现**，也是那棵树的视觉身份在
本仓库里唯一的完整记录。删掉它，那段设计就只剩 C++ 里几句注释了。

为什么退役：v0.33 按小绪的决定把树**完全删掉**（「树完全删掉，参数铺满整块
面板」）。于是这个文件画的是一个**已经不存在的设计** —— 它那 63 条自检与
45 条反向对照守的是"树画得对不对"。留在门禁里只有两种结局：要么永远红
（挡住真回归），要么被人一条条删松（伪装成有覆盖）。**两者都比没有更坏。**

它的贡献没有丢：`TEXT_LOG`（把每一处文字的"不透明度 / 基底层 / 墨层强度"
登记下来，再独立复算 WCAG 对比度）这套机制**搬进了真正的实现里** ——
见 `plugin/TranePanel.cpp` 的 `textLog()` / `logText()` / `bdName()` 与
`panel_probe --dump-text`，断言在 `tests/test_ui_design.py`。
搬过去之后它比原来更强：原来看的是**另一份实现**，现在看的是**插件真正在跑的那段代码**。

（下面这段是当初写它时的原始说明，保持原样，作为历史。）

=====================================================================
Träne UI v0.30 —— 暗场、Apple 深色模式语义色、没有边框、留白分组、
**交互状态只改颜色不改几何**、**动线 = 树上的信号流**。

小绪 2026-09-29 09:5x 的一句总纲：
    「我不要模块化的边框了，你做的太丑了，直接按照目前市面上最高级的 UI 来做！
      去找 Apple 的 UI 设计，然后直接学习，然后直接在基础上给我优化，
      不管是**动线**还是**交互效果**，还是**排版**，按照 Apple 做系统/软件的思路来帮我优化」

拆成五条，逐条落地
==================
① **去掉模块化的边框** —— 删掉 v0.25 引入的 `block_frame()`（描边 + 填充）。
   HIG · Layout 说分组有三种手段：`negative space, container shapes, or separator
   lines`。小绪否掉了后两种，只剩**留白** —— 而留白能分组的前提是**组间空档
   明显大于组内**，必须两个量级。所以有了 `SECTION_GAP_MULT`（= 2.5）
   （组间 = 行距 × 2.5）。自检里加了硬断言：**任何 `<rect>` 都不许带 `stroke=`**。

② **去学 Apple 的规范** —— 配色换成 Apple 深色模式**语义色**（值取自 UIKit /
   macOS 文档，不是"看着像"）：`systemBackground #000000` /
   `secondarySystemBackground #1C1C1E` / `systemFill rgba(120,120,128,.36)` /
   `separator rgba(84,84,88,.60)` / `systemGray2 #636366`；文字基色
   `#EBEBF5`（微冷，不是纯白）。**Apple 的层级机制只有两套 —— 面的明度、
   文字的四级不透明度 —— 没有"边框"这一层**，正好接上第 ① 条。
   字号抄 Apple 的 macOS 内置文本样式阶梯：`13 / 12 / 11`（Title3 / Callout /
   Caption 1 的量级），字重 600 / 500 / 400，**没有一个细字重**（HIG 明确"避免
   Light"）。宽度或行距放不下时**整体等比缩**（`scale_fit`），**不许某一档单独变**
   —— 那会把层级压平。

③ **在现有基础上优化排版** —— 行**按文字基线定位**（见下），字号层级反转
   （参数名降为 `secondaryLabel`、数值升为 `label`：插件里数值才是要读的东西）。

④ **交互效果（v0.29）** —— 四个状态 `idle / hover / press / focus`，
   硬规则是 **"状态只改颜色，不改几何"**：四态里所有文字的 x,y 与所有轨道矩形的
   x,y,w,h 必须**逐字节相同**。理由不只是"别跳一下" —— 更要命的是，状态一变就重排
   会让上面那一大段排版断言（末行对齐、列距、分组空档）**全部失效**，
   状态就成了排版的一个隐藏输入。断言直接对四张 SVG 逐元素比对。
   动效按 HIG · Motion 定：反馈 0.12s、低频动作 0.20s、
   **拖参数 0s**（原文 `generally avoid adding motion to UI interactions that
   occur frequently`），并且打开"减弱动态效果"时**全部归零**（不是"变小"）。
   全工程唯一允许出现的彩色是聚焦环的强调色 `ACCENT`，且**只准出现在聚焦态**。

⑤ **动线（v0.30）** —— 先量事实，再动手。量出来的三条：
   a. `core/TraneEngine.cpp::process()` 的顺序是
      `freeze → grain → stutter → comb → tape → ruin → sweep → delay → space → limiter`；
   b. `panel_probe --dump-geometry` 里十个质点的 **y 单调不减，恰好就是这个顺序**
      （102 → 200 → 200 → 396 → 396 → 494 → 592 → 592 → 690 → 886）。
      **也就是说：树在几何上早就是信号流了，只是没画出来。**
   c. `ALL_LANES` 展平后 = 上面这条链，所以检查器的阅读顺序**也**已经对上了。
   → 缺的只有**线**。`PATHS` 那 22 条是生命之树的**标准连线**（相邻质点两两相连），
     它说的是"这是一棵树"，**不表示流向**；而且它相对信号链**恰好命中 8 条、缺 1 条**
     （缺的是 `stutter → comb`）。
   → 所以信号层做成**独立的一层**（`SIGNAL_PATH` 由 `CHAIN` 推导，不手写），
     骨架退到点线、信号走实线 + **沿线渐变**（上游淡、下游亮，代替箭头），
     两种**质地**分两层含义。生命之树"一条不多一条不少"的设定**原样保住**。

   小绪 11:4x 补的一句定调（这一版按它改的）：
      「生命树的所有骨架全部保留，在有信号通过的时候直接高亮表示就可以了」
   → 于是 22 条骨架**一条不动**，信号层分**两档**：
       **静止**（这条链上没有信号）—— 静态、**不呼吸**。它只是"路径在这儿"。
       **通过**（两端模块都亮 / 这条边被选中）—— 抬上去，**并且跟着呼吸脉动**。
     两档必须拉得开，硬断言 **`SIG_HOT_LO × SIG_BREATH_MIN > SIG_REST_HI`** ——
     通信号那条边在**最暗的呼吸相位**下也要比静止那条**最亮处**还亮。
     做不到的话"高亮"就只是"亮了一点点"，等于没做。
   → 自检：节点顺序与探针逐项对账、y 只许向下不许回头、信号层不许自交、
     相对骨架恰好多 1 条、SVG 里数得出来的线数与方向、阅读顺序 = 信号顺序、
     **两档各自呼吸与否（量的是同一段代码在 breath=0 与 breath=1 下的差分）**。
   → 对照稿 `flow_html()` 出**两张**（静止态 / 通过态），唯一的变量是 `lit`：
     方案已经定了，要验的是方案里那个变量到底看不看得出来。

**两处刻意偏离 Apple，有据可查，不是随手改：**
  · Apple 的 `tertiaryLabel(0.30)` / `quaternaryLabel(0.18)` 在黑底上只有
    **2.23:1 / 1.55:1**，**过不了 WCAG AA 正文 4.5:1**。所以文字只借用前两级
    （1.00 / 0.60），关闭态用 `A_OFF`（= 0.56，实测 4.85:1）；Apple 的 0.30
    只给**非文字**（刻度、发丝线）用。
  · 分段控件保留**直角**（Apple 的是圆角）—— 小绪早先明确"不要圆角按钮"。

行按文字基线定位（v0.27 的教训，v0.28 沿用）
==========================================
    基线_i = 分组顶 + BLOCK_UP×S + i·pitch      （i = 0 … 行数−1）
    pitch  = [avail_h − blocks·(BLOCK_UP+BLOCK_DOWN)×S]
             / [rows − blocks + (blocks−1)·SECTION_GAP_MULT]

v0.26 对齐的是**行框的底边**，不是文字。行框不可见，文字是"居中放进行框"的；
行框高逐列差 2.5 倍（GRAIN 53.1px / COMB 132.0px），居中之后文字就差了
(132.0−53.1)/2 ≈ 39.5px —— 小绪一句「这也没对齐啊」点破。
**而自检当时是绿的，因为它量的也是行框底边。**
→ **"取样点盲区"：断言公式写对了，量的却是肉眼看不见的东西。**
→ 规则：**量的东西必须是肉眼能看见的东西。** v0.27 起断言一律直接量 SVG 里
   渲染出来的**文字基线**；**行框这个概念已从代码里删掉**。

小绪 2026-09-28 18:10 的十一条，逐条对应到代码
==============================================
  1. 字距再收紧            → TRACK 常量（按字号的比例给，不写死 px）
  2. 参数名写全称          → full_name()：用 kControls[].name，去掉重复的模块前缀
  3. 黑底白字、白色发光     → 令牌整组换掉；发光用白色径向渐变（黑底上"光"可以真的更亮）
  4. 不要 FOCUS            → 模式只剩 ALL / MODULE
  5. Module 数量可自定义    → 1 / 2 / 3 / 4 四档，列宽、字号、轨道长全部跟着重算
  6. 按数量换排版          → module_layout() 由 N 推出列宽 → 字号 → 标签宽 → 轨道长
  7. 删掉底部 10 MODULES   → 删除
  8. 行列间距完全一致       → **已被 v0.28 取代**：间距按用途分三个
                             （行内 8 / 列间 28 / 组间 = 行距 × 2.5）。
                             共用一个数做不到"留白分组"（组间必须明显大于组内）。
  9. 尺寸变化按比例缩放     → metrics() 里所有尺寸 = 基准值 × S，S = min(w/1440, h/720)
 10. 保留呼吸发光          → breath 参数化，并附一条呼吸相位演示带
 11. 删掉 SIGNAL MAP      → 删除；左上角只留世界树本身。
                             **v0.30 补一句**：删的是"另一张信号图"这个重复表达，
                             **不是**"不表达信号流"。信号流现在画在**树自己身上**
                             （第 ⑤ 条），一份几何、一份表达，不重复。

字体
====
pandaijing.com 的 Gla 经 WOFF name table 核验 = **Neue Haas Grotesk Text W01**
（Linotype GmbH / Christian Schwartz），商业字体。不抽取、不打包；
只在宿主已有该字体时使用，否则回退 Helvetica Neue。

几何与参数
==========
panel_probe --dump-geometry 给圆心与树比例；TranePanel.h::kControls 给 48 条参数。
这份稿子不重复手抄任何一条。
"""
from __future__ import annotations

import argparse
import math
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_bg_study import PATHS, TRUNK, esc, find_chrome, norm, read_controls, read_geometry

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 令牌 —— **Apple 深色模式语义色**（值取自 UIKit / macOS 官方文档，不是"看着像"）
# ---------------------------------------------------------------------------
# HIG · Color 的第一条原则：颜色按**用途**命名，不按外观命名。
# Apple 深色模式的层级只有两套机制，**没有"边框"这一层**：
#   ① 面的明度：systemBackground #000000
#              → secondarySystemBackground #1C1C1E
#              → tertiarySystemBackground #2C2C2E
#   ② 文字的四级不透明度：label 100% / secondaryLabel 60%
#                          / tertiaryLabel 30% / quaternaryLabel 18%
# 小绪 09:5x：「我不要模块化的边框了」→ 分组回到 HIG · Layout 的第一手段：
# **留白**（原文：`Group related items ... you might use negative space,
# container shapes, or separator lines`）。留白能分组的前提是**组间的空档
# 明显大于组内**，所以间距必须有两个量级 —— 见 SECTION_GAP_MULT。
#
# 两处**刻意偏离** Apple，都是有据可查的，不是随手改：
#   1) Apple 的次级文字色是 #EBEBF5（微冷），不是纯白降透明。这里全用 #EBEBF5：
#      1.00 档与纯白在黑底上的亮度差不到 8%，肉眼不可辨；换来的是
#      **文字只有一个令牌**，下面那条 `f == INK` 断言才守得住。
#   2) Apple 的 tertiaryLabel(0.30) / quaternaryLabel(0.18) 在黑底上只有
#      2.23:1 / 1.55:1 —— **过不了 WCAG AA 正文 4.5:1**。所以文字只借用前两级
#      （1.00 / 0.60），"关闭态"降到 0.56（实测 4.85:1）。Apple 的 0.30 只给
#      **非文字**用（刻度、发丝线）—— Apple 自己也把这两级用在装饰上。
BG = "#000000"                 # systemBackground
SURFACE = "#1C1C1E"            # secondarySystemBackground（树上"灭"的圆）
INK = "#EBEBF5"                # Apple 深色模式的文字基色（微冷，不是纯白）
INK_RGB = (235, 235, 245)

FILL = "rgba(120,120,128,.36)"  # systemFill —— 控件底（轨道、分段控件底）
FILL_RGB = (120, 120, 128)
FILL_A = 0.36
SEP = "rgba(84,84,88,.60)"      # separator —— 发丝线（Apple 自己那一条）
SEP_RGB = (84, 84, 88)
SEP_A = 0.60
GRAY2 = "#636366"               # systemGray2 —— 分段控件的选中块
GRAY3 = "#48484A"               # systemGray3

# 文字不透明度：三档，全部实测过线（self_check 逐条复算，改数字就报红）
A_TEXT = 1.00      # **主内容**：数值、选中的分段标签      = Apple label
A_MUTED = 0.60     # 次要：参数名、副标题、未选分段       = Apple secondaryLabel
A_OFF = 0.56       # 关闭态的一切文字（Apple 的 0.30 过不了线，见上）
A_NODE = 0.68      # 树上活动模块名下限（+0.28×呼吸 → 0.96）
A_VAL = 0.60       # 树上活动模块数值下限（+0.20×呼吸 → 0.80）
A_TICK = 0.30      # 出厂值刻度、发丝线：**非文字** = Apple tertiaryLabel


def ink_at(a: float) -> str:
    """文字墨按不透明度合成。文字统一走这里，避免同一档位写两遍对不上。"""
    return f"rgba({INK_RGB[0]},{INK_RGB[1]},{INK_RGB[2]},{a:.2f})"


# 只有 MUTED / FAINT 还需要以"颜色串"的形式用（HTML 外壳的 CSS 与非文字的刻度）。
# 面板里的文字一律写 `fill="{INK}" fill-opacity="{A_*}"` —— 把不透明度摊开成
# 独立属性，断言才能从生成的 SVG 里把真实值读回来核对。
MUTED = ink_at(A_MUTED)
FAINT = ink_at(A_TICK)         # **只给非文字用**，出现在 <text> 上会被断言拦下
HAIR = SEP                     # 发丝线直接用 Apple 的 separator，不另调一个灰

TRACK = FILL                   # 轨道底 = Apple systemFill
TRACK_RGB = FILL_RGB
TRACK_A = FILL_A
CIRC_ON_A = 0.07               # 树上"亮"的圆的填充不透明度
SEG_BG = "rgba(118,118,128,.24)"   # Apple 分段控件底 = tertiarySystemFill
SEG_BG_RGB = (118, 118, 128)
SEG_BG_A = 0.24

# ---------------------------------------------------------------------------
# 交互状态（v0.29）—— 小绪 09:5x「不管是动线还是交互效果，还是排版」
# ---------------------------------------------------------------------------
# 这一节的**唯一硬规则**：**状态只改颜色，不改几何**。
# hover / press / focus 三态里，所有文字的 x,y 与所有轨道矩形的 x,y,w,h 必须与 idle
# **逐字节相同**，只有 fill / fill-opacity / 多出来的那圈聚焦环会变。
# 为什么立这条：状态一变就重排，是"闪一下、跳一下"的根因；而且重排之后
# "末行对齐"这类排版断言全部失效 —— 状态会成为排版的一个隐藏输入。
# 立成断言之后，任何"悬停时把字放大一点"这类想法会被就地拦下。
#
# 状态强度必须**单调**：idle(0) < hover < press。自检复算，改数字就报红。
#   hover = 行底一层极淡的墨 + 数值提亮（"鼠标在这一行上"）
#   press = 更重的一层 + 数值满亮（"你正在按"）
#   focus = 3px 强调色环 + 2px 间隙（键盘走到这一行）
HOVER_A = 0.06                 # 行 hover 的墨层（INK 压在面板底上）
PRESS_A = 0.12                 # 行 press 的墨层 —— 必须是 hover 的 2 倍以上才读得出
ROW_BAND = 0.80                # 行底高度 = 行距 × 这个数（**跟着行距缩放，不写死 px**）
A_HOVER_NAME = 0.80            # hover 时参数名从 0.60 提到 0.80
FOCUS_RING_W = 3.0             # 聚焦环宽度 = macOS 11+ 的 keyboardFocusIndicator
FOCUS_RING_GAP = 2.0           # 环与控件体之间的空隙（Apple 也留）

# **强调色 = macOS 深色模式的 systemBlue，也是 keyboardFocusIndicatorColor 的默认值。**
# 这是本面板上**唯一**允许出现的彩色，而且**只准出现在聚焦态** ——
# HIG · Color 第一条原则就是"颜色按用途命名"：accent 的用途就是"交互强调"。
# 自检里有一条硬断言：idle / hover / press 三张里出现 ACCENT 就报红。
ACCENT = "#0A84FF"
ACCENT_RGB = (10, 132, 255)

# 动效时长 —— HIG · Motion：`Feedback motion ... should be brief and precise`，
# 并且 `generally avoid adding motion to UI interactions that occur frequently`。
# 所以：**拖参数一律不加动效**（MOTION_DRAG = 0），只给低频动作过渡。
MOTION_FAST = 0.12             # s · hover / press 的反馈
MOTION_STD = 0.20              # s · 低频：模块开关、模式切换
MOTION_DRAG = 0.00             # s · **拖参数不加** —— 这条是规则，不是遗漏
MOTION_EASE = "cubic-bezier(0.2,0,0,1)"    # 减速曲线：起步快、收尾稳
MOTION_MAX = 0.30              # s · HIG 的"brief"上限；超过就不是反馈而是表演了
# HIG · Motion：`Make motion optional` / `Let people cancel motion`。
# 系统打开"减弱动态效果"时，所有时长乘这个系数 —— 必须是**精确的 0**，
# 写成 0.05 之类的"小一点"等于没关掉。
REDUCE_MOTION_SCALE = 0.0

STATES = ("idle", "hover", "press", "focus")

# 行**按文字基线**定位（v0.27）。这两个是"墨迹到分组边"的距离 —— 注意是**墨迹**，
# 不是不可见的行框：内边距再加字本身的上下高度。
#     BLOCK_UP   = 内边距 + 模块标题的大写字高   （标题 13px → 大写字高 9.4px）
#     BLOCK_DOWN = 内边距 + 参数数值的降部       （数值 12px → 降部 2.6px）
# 为什么不能直接用内边距：文字有实体高度。若基线只离分组边一个内边距，标题的
# 大写字帽会**穿过**分组边界。加字高之后，肉眼看到的"墨迹到边"才真的等于内边距。
# 上一版对齐的是行框底边（不可见），行框高逐列差 2.5 倍 → 文字差 39px，
# 小绪一眼就看出来了。行框这个概念已经删掉。
BLOCK_UP = 19.4                # 分组顶边 → 首行基线（= 10 + 9.4）
BLOCK_DOWN = 12.6              # 末行基线 → 分组底边（= 10 + 2.6）

# 强调 = 白本身。黑底上"发光"可以真的比底更亮，所以这里能画真光晕，
# 不像白纸版只能做成墨渍。
GLOW_MAX = 0.22

# 文字登记表 —— 画字的那段代码自己登记 (不透明度, 底色名, 是否深字)。
# self_check() 做两件事：① 按登记的底色复算对比度 ② 与 SVG 里**真实出现**的
# alpha 逐个对账。两边必须一致 —— 只查一边挡不住"改了绘制代码没改登记表"。
# 第三个字段标"深字压亮块"那一支（用的是 BG 墨而不是白墨），免得断言按白墨算。
TEXT_LOG: list[tuple[float, str, bool]] = []


def log_text(a: float, backdrop: str, dark: bool = False) -> None:
    TEXT_LOG.append((round(a, 2), backdrop, dark))


# ---------------------------------------------------------------------------
# 色彩算术 —— 对比度断言用，全部按 WCAG 2.1 的定义来
# ---------------------------------------------------------------------------
WHITE = (255, 255, 255)
CONTRAST_MIN = 4.5                 # WCAG 2.1 AA 正文


def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_of(c: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % c


def over(a: float, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """把不透明度 a 的 fg 合成到 bg 上 —— 半透明白压在黑底上到底是个什么灰，
    必须算出来，不能靠眼睛估。"""
    return tuple(round(a * fg[i] + (1 - a) * bg[i]) for i in range(3))


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(c: tuple[int, int, int]) -> float:
    return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """WCAG 对比度 (L_亮 + 0.05) / (L_暗 + 0.05)。"""
    x, y = _lum(a), _lum(b)
    hi, lo = max(x, y), min(x, y)
    return (hi + 0.05) / (lo + 0.05)


def backdrops() -> dict[str, tuple[int, int, int]]:
    """面板里文字会遇到的所有底色 —— **由令牌合成**，不另抄一份 hex。

    这样改令牌（比如把轨道调亮）时，这里的底跟着变，对比度断言就会重算，
    "改了颜色但断言还在按旧颜色算"这个洞就堵上了。

    v0.28 起只有四档，全部对应 Apple 的真实面：
      bg      systemBackground             #000000   面板底、分组之外的一切文字
      track   systemFill 压在 bg 上        #2B2B2E   轨道底（文字会遇到的最亮一层）
      seg     tertiarySystemFill 压在 bg  #1C1C1F   分段控件底（未选中的标签压这层）
      seg_on  systemGray2                  #636366   分段控件选中块（选中的标签压这层）
      hover   墨层压在 bg 上（v0.29）      #0E0E0F   悬停行的底
      press   墨层压在 bg 上（v0.29）      #1D1D1E   按下行的底
      seg_hover / seg_press（v0.29）：`tertiarySystemFill` 是**半透明**的（α=0.24），
        所以 hover/press 的行底会**透上来**。分段控件的标签真实压的是"行底之上的
        那层 fill"，不是 `seg`。登记表必须跟着换，否则对比度是拿错底算的。
    树上还有两档：亮圆 circ_on、灭圆 circ_off。
    """
    bg = rgb(BG)
    hover_bd = over(HOVER_A, INK_RGB, bg)
    press_bd = over(PRESS_A, INK_RGB, bg)
    return {
        "bg": bg,                                        # 面板底
        "track": over(FILL_A, FILL_RGB, bg),             # 轨道底
        "seg": over(SEG_BG_A, SEG_BG_RGB, bg),           # 分段控件底
        "seg_on": rgb(GRAY2),                            # 分段控件选中块（不透明）
        "hover": hover_bd,                               # 悬停行的底（文字压这层）
        "press": press_bd,                               # 按下行的底（文字压这层）
        "seg_hover": over(SEG_BG_A, SEG_BG_RGB, hover_bd),
        "seg_press": over(SEG_BG_A, SEG_BG_RGB, press_bd),
        "circ_on": over(CIRC_ON_A, INK_RGB, bg),         # 树上"亮"的圆
        "circ_off": rgb(SURFACE),                        # 树上"灭"的圆
    }

UI = ("'Neue Haas Grotesk Text W01','Neue Haas Grotesk Text Pro',"
      "'Helvetica Neue',Helvetica,Arial,sans-serif")
DATA = "'Neue Haas Grotesk Text W01','Helvetica Neue',Helvetica,Arial,sans-serif"

# 字距：负数 = 收紧。按字号比例给，换字号时字距跟着走。
TRACK_UI = -0.012
TRACK_HEAD = -0.005
TRACK_DATA = -0.018

# ---------------------------------------------------------------------------
# 动线（v0.30）—— 信号从哪进、经过什么、从哪出
# ---------------------------------------------------------------------------
# **这条链的事实来源是 `core/TraneEngine.cpp::process()`，不是这里。**
# 实测（`grep -n '_\.process' core/TraneEngine.cpp`）：
#     freeze → grain → stutter → comb → tape → ruin → sweep → delay → space → limiter
# 而 `panel_probe --dump-geometry` 吐出的 node 顺序、`TranePanel.h::kNodes` 的顺序、
# 以及这里 CHAIN 的顺序**逐项一致** —— 自检会拿探针的 node 顺序回来对账，
# 对不上就报红（改了 DSP 顺序却忘了改界面，会被当场抓住）。
CHAIN = ["freeze", "grain", "stutter", "comb", "tape",
         "ruin", "sweep", "delay", "space", "out"]

# **信号路径 = CHAIN 的相邻对** —— 推导，不手写。
# 手写一份就多一个会跟 CHAIN 分叉的地方（v0.16 漏掉 12 个控件的教训）。
SIGNAL_PATH = [(CHAIN[i], CHAIN[i + 1]) for i in range(len(CHAIN) - 1)]

# **演示用的"哪些模块在响"。** 真机上是遥测喂进来的（freeze → uiFreezeActive、
# grain → min(1, voices/12)、out → 1 - gainReduction、tape → min(1,|speed-1|×4)，
# 其余模块没有遥测、开着就算 1.0 —— 见 `TranePanel.h::PanelState`）。
# 设计稿这里取**链的前五级**，因为这样"亮着的节点"正好是一段**连续的前缀**，
# 而信号层的高亮也就落在那一段上 —— 演示图自己就能把"有信号通过 → 高亮"说清楚。
# 取别的组合的话，9 条边里可能只有 2 条亮，看不出高亮。
LIT = set(CHAIN[:5])

# **MODULE 模式的候选集 = CHAIN 的一段连续切片。** 这条是动线要求：
# 按 1 列看到的必须是链上某一级，按 4 列看到的必须是**连着**的四级，
# 顺序与信号一致 —— 不许跳着挑。
#
# 为什么从 `grain` 起而不是从链头 `freeze`：**量过**。每列的行距是按该列自己的
# 行数解出来的（"各行均匀 + 末行对齐"的代价），于是行数少的列会被拉得很开：
#     freeze 3 行 → 271.0px      out 2 行 → 542.0px
#     grain 9 行 →  67.8px       comb/tape 4 行 → 180.7px
# 271px 的行距意味着两个参数孤零零挂在 720px 高的面板上，那不是"留白"，是空。
# 所以候选集取 deconstruction 链（grain/stutter/comb/tape）—— 既是连续切片、
# 又都是参数有分量的模块。
SELECTED = CHAIN[1:5]                                # MODULE 模式的候选集

# ALL 模式的分栏 —— **展平后必须等于 CHAIN**（自检断言），也就是
# "从左到右、从上到下"的阅读顺序就是信号顺序。三列的组数 3+3+4，
# 行数 12 / 13 / 12 —— 既是信号顺序，也恰好是均衡的。
ALL_LANES = [["freeze", "grain", "stutter"],
             ["comb", "tape", "ruin"],
             ["sweep", "delay", "space", "out"]]

# 树上三层 —— 三种**质地**，不是一个东西调深浅：
#   ① 骨架 GRID   —— 生命之树的 22 条标准连线，**点线**，最淡。它说的是"这是一棵树"。
#   ② 中柱 TRUNK  —— 骨架里 keter-tiferet-yesod-malkuth 那三条，略重。结构，不是功能。
#   ③ 信号 SIGNAL —— CHAIN 的 9 条相邻对，**实线 + 方向渐变**。它说的是"信号往哪流"。
#
# 为什么信号层**不能复用 PATHS**：`stutter → comb` 这条**不在**那 22 条里
# （22 条是相邻节点两两连线，2→3 恰好缺席 —— 实测 8/9 命中）。所以信号层是
# **独立的一层**，这也顺带保住了"生命之树一条不多一条不少"的原始设定。
#
# 方向怎么表达：不画箭头。**沿线的渐变**（上游淡、下游亮）本身就说明流向，
# 而且不会在暗底上留一个刺眼的形状 —— Apple 的做法是让材质说话，不是加标记。
TREE_LAYERS = ("grid", "signal")     # 可只留其一，用于出对照稿
# **这几个数不是调出来的，是量出来的。** 采样方法：整张面板按 1440×720 渲成 PNG，
# **只在树的那一块里采样**（右半边是检查器，全是亮字，不裁范围 p99 永远是 236），
# 再挖掉每个节点圆盘（半径 r + 46px，连环形文字与模块名一起挖掉），
# 剩下的就是纯线像素，取 p50 / p99 / max（0–255）。
#
# 实测（v0.30 定稿值）：
#     骨架 · 普通连线   p50  12   p99  22   max  46
#     骨架 · 中柱       p50  11   p99  47   max  62
#     信号 · 静止档     p50  84   p99 125   max 128
#     信号 · 通过档     p50  13   p99 189   max 201   ← 最低呼吸相位
#     信号 · 通过档     p50  13   p99 212   max 226   ← 呼吸峰值
# **高亮是真的**：通过档在最暗相位下 p99 = 189，静止档最亮 128 —— 差 1.48 倍。
#
# 历史：第一版写 GRID_OP = 0.07 / TRUNK_OP = 0.12，量出来骨架峰值只有 **25/255** ——
# 眼睛根本看不见，于是"只有骨架"和"只有信号"两张对照稿看起来一模一样，
# 树这个身份等于丢了。原因：点线太省墨 —— 直径 0.9px 的点每 8.8px 才落一个。
# **常量写得再合理，屏幕上的亮度也得量。** α 不是亮度。
#
# **小绪 2026-09-29 11:4x 定的调子：「生命树的所有骨架全部保留，在有信号通过的时候
# 直接高亮表示就可以了」。** 所以信号线分**两档**，不是一个固定亮度：
#     静止（这条链上没有信号）—— 静态、不呼吸。它只是"路径在这儿"。
#     通过（两端模块都亮 / 被选中）—— 整体抬上去，**并且跟着呼吸脉动**。
# 两档必须拉得开：**通信号那条边在最暗的呼吸相位下，也要比静止那条最亮处还亮** ——
# 这条是硬断言（`SIG_HOT_LO × SIG_BREATH_MIN > SIG_REST_HI`），
# 不然"高亮"就只是"亮了一点点"，等于没做。
GRID_OP = 0.13                       # 骨架点线的不透明度（实测峰值 ≈ 30/255）
TRUNK_OP = 0.20                      # 中柱（结构上略重，但**不许压过信号层**）
SIG_REST_LO = 0.32                   # 信号线**静止**：上游端
SIG_REST_HI = 0.55                   # 信号线**静止**：下游端（渐变 = 方向）
SIG_HOT_LO = 0.78                    # 信号线**通过**：上游端
SIG_HOT_HI = 1.00                    # 信号线**通过**：下游端
SIG_W = 1.6                          # 信号层线宽（骨架 0.9–1.0）
SIG_BREATH_MIN = 0.85                # 呼吸最低点 —— **只作用于"在通信号"的那些边**
#                                     静止的边不呼吸：呼吸 = 活动，没信号就没活动


def is_hot(na: str, nb: str, lit: set[str], selected: list[str] | None = None) -> bool:
    """一条信号边算不算"有信号在过"。

    **判据只有这一份** —— `tree_svg()` 拿它画，`self_check()` 拿它算期望条数。
    两份判据的话，自检就在验自己抄的那份，永远绿。
    """
    return (na in lit and nb in lit) or na in (selected or ()) or nb in (selected or ())


def n_hot(lit: set[str], selected: list[str] | None = None) -> int:
    """在通信号的边数 —— 从 `is_hot` 数出来，不另写一份判断。"""
    return sum(1 for na, nb in SIGNAL_PATH if is_hot(na, nb, lit, selected))

REF_W, REF_H = 1440.0, 720.0        # 基准尺寸；其它尺寸全部按 S 缩放
DIVIDER_X = 392.0
PANE_X0 = 422.0
PANE_PAD = 28.0                     # 面板内边距（Apple 窗口边距量级）
ROWS_TOP = 118.0
ROWS_BOTTOM_PAD = 28.0

# 间距阶梯。HIG · Layout 说分组可以用三种手段：`negative space, container
# shapes, or separator lines`。小绪 09:5x 否掉了 container（「我不要模块化的边框了」），
# 所以只剩留白 —— 而**留白能分组的前提是组间空档明显大于组内**，必须两个量级。
#     组内（名称 ─ 轨道 ─ 数值）  GAP = 8       —— Apple 的 8pt 基准
#     组间（模块与模块之间）      2.5 × 行距    —— 行距由列高与行数解出来
#     列间                        COL_GAP = 28
# 三个数不是"随手调"，是三个不同的用途：行内、分组、分栏。
GAP = 8.0                           # 行内三格之间
COL_GAP = 28.0                      # 列与列之间
SECTION_GAP_MULT = 2.5              # 模块之间的空档 = 行距 × 2.5

# 字宽系数（em）—— 用于按最长文本反推列宽，不是拍脑袋的"乘 5.3"
K_LABEL = 0.63                      # 大写字母平均前进宽度
K_VALUE = 0.60                      # 数字 + 单位
MIN_TRACK = 46.0                    # 轨道最短留多长（否则值编码的动态范围就没了）

# 字号阶梯 —— **直接抄 Apple 的 macOS 内置文本样式**（HIG · Typography · Specifications）：
#     Headline   13 / Bold       → 模块标题（这里是 Semibold，见 module_head）
#     Body       13 / Regular    → macOS 正文默认字号，也是本面板的最小可读线
#     Callout    12 / Regular    → 参数数值
#     Caption 1  11 / Regular    → 参数名
# Apple 规定 macOS 最小 10pt、默认 13pt，并且"避免细字重"（Regular–Bold）。
# 所以这里的三档字号是 13 / 12 / 11，字重 600 / 500 / 400，**没有一个细字重**。
FS_TITLE, FS_VALUE, FS_NAME = 13.0, 12.0, 11.0
FS_MIN = 10.0                       # 硬下限 = Apple 的 macOS 最小可读字号（10pt）


# ---------------------------------------------------------------------------
# 度量：一切尺寸 = 基准 × S，另外由 Module 数量推出列宽与字号
# ---------------------------------------------------------------------------
def metrics(w: float, h: float) -> dict:
    """**一切尺寸 = 基准 × S。** 包括可用宽高本身 —— 否则 s=1.5 时宽度会放大 1.73 倍，
    "按比例缩放"就是假的（这条踩过）。

    **画布必须是基准比例。** 以前这里用 `min(w/REF_W, h/REF_H)` 悄悄兜住非基准比例，
    结果是在画布一角画出一份偏移的版面、分割线还戳到内容区外面（实测 1440×900：
    分割线比参数区长了 180px），而且这个分支**从来没被验过**。
    真插件把宽高比锁死了（`PluginEditor.cpp` 的 `setFixedAspectRatio(kBaseW/kBaseH)`，
    自由拉伸会让圆变椭圆、环形文字的倾角全错），所以非基准比例根本不可能出现。
    **宁可报错，不许糊弄** —— 直接把这条路堵死。
    """
    base_ar = REF_W / REF_H
    assert abs(w / h - base_ar) <= base_ar * 1e-3, (
        f"画布 {w:.0f}×{h:.0f} 的比例 {w / h:.4f} ≠ 基准 {base_ar:.4f}；"
        f"插件锁死了宽高比，这里不该出现非基准比例（容差 0.1%）")
    s = min(w / REF_W, h / REF_H)      # 两条比值刚断言过相等，取 min 只是防浮点抖动
    return {
        "w": w, "h": h, "s": s,
        "gap": GAP * s,                 # 行内三格之间
        "col_gap": COL_GAP * s,         # 列与列之间
        "pad": PANE_PAD * s,            # 面板内边距
        "divider": DIVIDER_X * s,
        "pane_x0": PANE_X0 * s,
        "pane_w": (REF_W - PANE_X0 - PANE_PAD) * s,
        "rows_top": ROWS_TOP * s,
        "avail_h": (REF_H - ROWS_TOP - ROWS_BOTTOM_PAD) * s,
        "fs_tab": 11.0 * s,
        "fs_head": 17.0 * s,
        "fs_sub": 11.0 * s,
        "fs_node": 11.0 * s,
        "fs_node_val": 10.0 * s,
        "glow_r": 20.0 * s,
    }


def columns_for(m: dict, n: int, lmax: int, vmax: int, row_span: float) -> dict:
    """N 个 Module 并排时的**列宽**与**三档字号**。

    v0.28 起没有块框了（小绪 09:5x「我不要模块化的边框了」），所以列宽 = 内容宽，
    列与列之间只留 COL_GAP 一个空档 —— 分组靠留白，不靠容器。

    字号直接取自 Apple 的 macOS 文字样式阶梯（13 / 12 / 11），只有在
    ①列宽放不下、②行距放不下 两种情况下才**整体等比缩**（scale_fit）——
    绝不允许某一档单独变，那会把层级压平（HIG：「保持文本元素的相对层级」）。
    字宽按**实测系数**算（大写平均前进宽度 ≈ 0.63em），不是拍脑袋。
    """
    gap, s = m["gap"], m["s"]
    col_w = (m["pane_w"] - m["col_gap"] * (n - 1)) / n
    # 宽度能容下的最大"参数名字号"：把三段（名 / 轨 / 值）的总宽压进列宽
    den = lmax * K_LABEL + (FS_VALUE / FS_NAME) * vmax * K_VALUE
    fs_fit_w = (col_w - 2 * gap - MIN_TRACK * s) / den if den > 0 else 99.0
    # 行距能容下的最大字号：字号不许超过行距的 72%，否则上下行会贴在一起
    fs_fit_h = row_span * 0.72
    scale_fit = min(1.0, fs_fit_w / (FS_NAME * s), fs_fit_h / (FS_NAME * s))
    fs_name = FS_NAME * s * scale_fit
    fs_value = FS_VALUE * s * scale_fit
    fs_title = FS_TITLE * s * scale_fit
    return {"s": s, "n": n, "col_w": col_w, "frame_w": col_w,     # frame_w 仅为兼容旧断言
            "fs_label": fs_name, "fs_value": fs_value, "fs_title": fs_title,
            "label_w": lmax * K_LABEL * fs_name,
            "value_w": vmax * K_VALUE * fs_value,
            "track_w": col_w - lmax * K_LABEL * fs_name - vmax * K_VALUE * fs_value - 2 * gap}


def extents(ctrls: list[dict], modules: list[str]) -> tuple[int, int]:
    """这批模块里最长的参数名与最长的数值各占多少字符 —— 列宽按最长的那个留。"""
    labs = [len(full_name(c)) for mod in modules for c in ring_controls(ctrls, mod)]
    vals = [len(value_text(c)) for mod in modules for c in ring_controls(ctrls, mod)]
    return (max(labs) if labs else 1), (max(vals) if vals else 1)


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
def real(c: dict, nv: float) -> float:
    q = nv if c["skew"] == 1.0 else math.pow(max(0.0, nv), 1.0 / c["skew"])
    return c["lo"] + (c["hi"] - c["lo"]) * q


def value_text(c: dict, nv: float | None = None) -> str:
    v = c["def"] if nv is None else real(c, nv)
    f = c["fmt"]
    if f == "None": return ""
    if f == "Ms": return f"{v:.0f}MS" if v >= 10 else f"{v:.1f}MS"
    if f == "Plain0": return f"{v:.0f}"
    if f == "Plain2": return f"{v:.2f}"
    if f == "Rate1": return f"{v:.1f}"
    if f == "KHz1": return f"{v / 1000.0:.1f}K"
    if f == "Db1": return f"{v:+.1f}DB"
    if f == "Choice": return ["LP", "BP", "HP"][min(2, max(0, round(v * 2)))]
    return f"{v:g}".upper()


def full_name(c: dict) -> str:
    """全称 = 宿主里声明的显示名，**不剥模块前缀**。

    一开始我把前缀剥掉想省宽度，结果 GRAIN MIX / STUTTER MIX / COMB MIX / TAPE MIX /
    DELAY MIX / SPACE MIX 六条全塌成 "MIX"，41 条只剩 29 个唯一名 —— 自检当场报红。
    小绪说的"写全称"就是这个意思：同名参数必须能区分。
    """
    return c["name"].upper()


def ring_controls(ctrls: list[dict], module: str) -> list[dict]:
    return [c for c in ctrls if c["module"] == module and c["label"]]


def switch_of(ctrls: list[dict], module: str):
    return next((c for c in ctrls if c["module"] == module and not c["label"]), None)


def rows_of(ctrls: list[dict], module: str) -> int:
    """一个模块占几行**参数**。

    模块开关**不再是独立一行**（小绪 18:52：把 ENABLE 去掉，直接拿模块名当开关）。
    所以这里只数参数 —— 少了一行，等于每列省出约一个行高的空间。
    """
    return len(ring_controls(ctrls, module))


def block_rows(ctrls: list[dict], module: str) -> int:
    """一个模块占几行：标题（同时就是开关）1 行 + 参数 N 行。"""
    return 1 + rows_of(ctrls, module)


def block_kinds(ctrls: list[dict], module: str) -> list[str]:
    """该模块自上而下的行类型，顺序必须和 column_block() 画的一致。"""
    return ["head"] + ["param"] * rows_of(ctrls, module)


# ---------------------------------------------------------------------------
# 世界树
# ---------------------------------------------------------------------------
def tree_layout(geo: dict, x: float, y: float, w: float, h: float) -> dict:
    r = min(w / 7.865, h / 15.514)          # 2/0.341+2 · 1/0.074+2
    col, tree_h = r / 0.341, r / 0.074
    cx, cy = x + w * .5, y + h * .5
    xs = [n["x"] for n in geo["nodes"]]
    ys = [n["y"] for n in geo["nodes"]]
    xmin, ymin = min(xs), min(ys)
    xr, yr = max(xs) - xmin, max(ys) - ymin
    pts = []
    for n in geo["nodes"]:
        u = 0.0 if xr == 0 else (n["x"] - xmin) / xr * 2 - 1
        v = 0.0 if yr == 0 else (n["y"] - ymin) / yr
        pts.append({"module": n["module"], "x": cx + u * col, "y": cy + (v - .5) * tree_h})
    return {"r": r, "pts": pts}


def glow_ring(cx: float, cy: float, r: float, gr: float, breath: float, idx: int,
              defs: list[str]) -> str:
    """真光晕：黑底上可以让外圈比底更亮，所以用白色径向渐变而不是深色墨渍。"""
    ro = r + gr
    # 下限 0.10 而不是 0：亮着的模块**任何时候都不该看起来是灭的**，
    # 呼吸是"脉动"不是"开关"。实测四相位峰值 0.10 / 0.18 / 0.25 / 0.32。
    peak = 0.10 + GLOW_MAX * breath
    defs.append(
        f'<radialGradient id="gl{idx}" gradientUnits="userSpaceOnUse" '
        f'cx="{cx:.1f}" cy="{cy:.1f}" r="{ro:.1f}">'
        f'<stop offset="0" stop-color="{INK}" stop-opacity="0"/>'
        f'<stop offset="{r / ro:.4f}" stop-color="{INK}" stop-opacity="{peak:.3f}"/>'
        f'<stop offset="1" stop-color="{INK}" stop-opacity="0"/></radialGradient>')
    c = lambda rr: (f"M {cx - rr:.2f} {cy:.2f} a {rr:.2f} {rr:.2f} 0 1 0 {2 * rr:.2f} 0 "
                    f"a {rr:.2f} {rr:.2f} 0 1 0 {-2 * rr:.2f} 0 ")
    return f'<path d="{c(ro)}{c(r)}" fill-rule="evenodd" fill="url(#gl{idx})"/>'


def tree_svg(geo: dict, ctrls: list[dict], m: dict, breath: float,
             selected: list[str],
             layers: tuple[str, ...] = TREE_LAYERS,
             lit: set[str] | None = None) -> tuple[str, list[str]]:
    box = (30.0 * m["s"], 40.0 * m["s"], 332.0 * m["s"], 640.0 * m["s"])
    t = tree_layout(geo, *box)
    r, pts = t["r"], t["pts"]
    # `lit` 是"哪些模块在响"。默认用演示集 `LIT`；动线对照稿要拿它演"没信号 vs 有信号"
    # 这一对，所以必须能换 —— 但**信号层的判据本身不许因此变成参数**（见下面的 hot）。
    lit = LIT if lit is None else lit
    on = {p["module"]: p["module"] in lit for p in pts}
    at = {p["module"]: p for p in pts}          # 按**模块名**取点，不按下标 ——
    # 信号层是拿 CHAIN 的名字推出来的，靠名字才对得上；靠下标就多一份映射会分叉。
    defs: list[str] = []
    out: list[str] = []

    def seg(pa: dict, pb: dict) -> tuple[float, float, float, float]:
        """两端各缩掉 r+3，线不插进圆里。"""
        dx, dy = pb["x"] - pa["x"], pb["y"] - pa["y"]
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln
        trim = r + 3
        return (pa["x"] + ux * trim, pa["y"] + uy * trim,
                pb["x"] - ux * trim, pb["y"] - uy * trim)

    # ① 骨架 —— 生命之树的 22 条标准连线。**点线**，最淡。它只表结构，不表流向。
    if "grid" in layers:
        for a, b in PATHS:
            x0, y0, x1, y1 = seg(pts[a], pts[b])
            trunk = (a, b) in TRUNK
            out.append(f'<line class="g" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                       f'stroke="{INK}" stroke-opacity="{(TRUNK_OP if trunk else GRID_OP):.2f}" '
                       f'stroke-width="{1.0 if trunk else 0.9}" stroke-linecap="round" '
                       f'stroke-dasharray="0.01 {5.5 * m["s"]:.1f}"/>')

    # ② 信号 —— CHAIN 的 9 条相邻对。**实线 + 上游淡/下游亮的方向渐变。**
    #    点线 vs 实线是最省的质地区分：一眼就能分出"哪层是结构、哪层是功能"。
    #    分**两档**（小绪 11:4x：「有信号通过的时候直接高亮」）：
    #      静止 —— 静态不呼吸，只是"路径在这儿"
    #      通过 —— 抬上去 + 跟着呼吸脉动。判据：两端模块都亮，或这条边的某一端被选中。
    if "signal" in layers:
        for k, (na, nb) in enumerate(SIGNAL_PATH):
            x0, y0, x1, y1 = seg(at[na], at[nb])
            hot = is_hot(na, nb, lit, selected)
            if hot:
                pulse = SIG_BREATH_MIN + (1.0 - SIG_BREATH_MIN) * breath
                lo, hi = SIG_HOT_LO * pulse, SIG_HOT_HI * pulse
            else:
                lo, hi = SIG_REST_LO, SIG_REST_HI
            gid = f"sg{k}"
            # 渐变坐标 = **被裁短之后的**那一段，否则方向会和肉眼看到的那截错开。
            defs.append(
                f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                f'x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}">'
                f'<stop offset="0" stop-color="{INK}" stop-opacity="{lo:.3f}"/>'
                f'<stop offset="1" stop-color="{INK}" stop-opacity="{hi:.3f}"/>'
                f'</linearGradient>')
            out.append(f'<line class="s" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                       f'stroke="url(#{gid})" stroke-width="{SIG_W:.1f}" stroke-linecap="round"/>')

    for i, p in enumerate(pts):
        active = on[p["module"]]
        if active:
            out.append(glow_ring(p["x"], p["y"], r, m["glow_r"], breath, i, defs))
        fill = ink_at(CIRC_ON_A) if active else SURFACE
        stroke = INK if active else HAIR
        sw = 1.4 if active else 1.0
        sop = (0.62 + 0.38 * breath) if active else 1.0
        out.append(f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{r:.1f}" fill="{fill}" '
                   f'stroke="{stroke}" stroke-opacity="{sop:.2f}" stroke-width="{sw}"/>')
        if p["module"] in selected:
            out.append(f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{r + 6 * m["s"]:.1f}" '
                       f'fill="none" stroke="{INK}" stroke-opacity=".85" stroke-width="1" '
                       f'stroke-dasharray="2 {3.5 * m["s"]:.1f}"/>')
        ring = ring_controls(ctrls, p["module"])
        primary = value_text(ring[0]) if ring else ""
        # 树上的字同样受对比度约束，底是圆本身（亮 #1B1C1D / 灭 #131517）。
        # 上一版活动名 0.70 起、活动数值 0.45 起 —— 数值在亮圆上只有 4.45:1，不过线。
        # 抬到 0.60 后 6.85:1；"亮/灭"的区分不靠数值这一档，靠光晕环、圆填充、
        # 描边色和模块名四个通道，所以数值档位挨得近不影响可读性。
        name_op = A_NODE + (1.0 - A_NODE) * breath
        val_op = A_VAL + 0.20 * breath
        log_text(name_op if active else A_OFF, "circ_on" if active else "circ_off")
        log_text(val_op if active else A_OFF, "circ_on" if active else "circ_off")
        out.append(f'<text x="{p["x"]:.1f}" y="{p["y"] - 2 * m["s"]:.1f}" text-anchor="middle" '
                   f'font-family="{UI}" font-size="{m["fs_node"]:.1f}" font-weight="600" '
                   f'letter-spacing="{TRACK_UI * m["fs_node"]:.2f}" fill="{INK}" '
                   f'fill-opacity="{name_op if active else A_OFF:.2f}">{p["module"].upper()}</text>')
        if primary:
            out.append(f'<text x="{p["x"]:.1f}" y="{p["y"] + 12 * m["s"]:.1f}" text-anchor="middle" '
                       f'font-family="{DATA}" font-size="{m["fs_node_val"]:.1f}" font-weight="400" '
                       f'letter-spacing="{TRACK_DATA * m["fs_node_val"]:.2f}" fill="{INK}" '
                       f'fill-opacity="{val_op if active else A_OFF:.2f}">{primary}</text>')
    return "".join(out), defs


# ---------------------------------------------------------------------------
# 控件
# ---------------------------------------------------------------------------
def segmented(x: float, y: float, w: float, h: float, items: list[str],
              active: int, m: dict, disabled: bool = False) -> str:
    """分段控件 —— **Apple 的填充式表达**：底 = tertiarySystemFill，选中 = systemGray2。

    Apple 的 NSSegmentedControl 是圆角的，小绪早先明确说过"不要圆角按钮"，
    所以这里保留直角，但把**边框**去掉、换成 Apple 的**填充分层**：
        底     rgba(118,118,128,.24)   压在面板底上 → #1C1C1F
        选中块  systemGray2            #636366
    这正是 HIG 说的"用面表达层级"——不再靠一根 1px 描边把控件框起来。
    分格之间的发丝线也去掉了：选中块自己的边界已经把分格说清楚了。
    """
    n = len(items)
    cw = w / n
    out = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
           f'fill="{SEG_BG}"/>']
    for i, it in enumerate(items):
        sel = (i == active) and not disabled
        if sel:
            out.append(f'<rect x="{x + cw * i:.1f}" y="{y:.1f}" width="{cw:.1f}" '
                       f'height="{h:.1f}" fill="{GRAY2}"/>')
        # 文字压在自己脚下那块面上：
        #   选中的压在 systemGray2 上 → 主内容色（A_TEXT 1.00）
        #   未选的压在 tertiarySystemFill 上 → 次要色（A_MUTED 0.60）/ 禁用（A_OFF）
        if sel:
            log_text(A_TEXT, "seg_on")
            col, op_attr = INK, f' fill-opacity="{A_TEXT:.2f}"'
        else:
            a = A_OFF if disabled else A_MUTED
            log_text(a, "seg")
            col, op_attr = INK, f' fill-opacity="{a:.2f}"'
        fs = m["fs_tab"]
        out.append(f'<text x="{x + cw * (i + .5):.1f}" y="{y + h / 2 + fs * .35:.1f}" '
                   f'text-anchor="middle" font-family="{UI}" font-size="{fs:.1f}" '
                   f'font-weight="500" letter-spacing="{TRACK_UI * fs:.2f}" fill="{col}"'
                   f'{op_attr}>{it}</text>')
    svg = "".join(out)
    assert "rx=" not in svg, "分段控件必须直角 —— 小绪明确不要圆角按钮"
    return svg


def track_h(col: dict) -> float:
    """轨道厚度 —— 由**字号**定，不由行高定。

    行高是按列反推的，如果厚度跟着行高走，行数少的列轨道会明显比行数多的列粗，
    同一张面板上出现两种粗细。内容尺寸必须与行高解耦：行高只负责留白。

    最细 2px 是 **× S** 的：写成绝对的 `max(2.0, …)` 会让轨道在 S<0.556 时卡住不再变细
    （实测 fs_label=12S 时 12S×0.30 < 2.0 ⟺ S < 0.556）。插件把最小缩放卡在 0.70，
    刚好躲开 —— 但"刚好躲开"不是"没问题"，一个看 S 不看常量迟早会咬人。
    """
    return max(2.0 * col["s"], col["fs_label"] * 0.30)


def choice_h(col: dict) -> float:
    """LP/BP/HP 分段块的高度，同样只由字号定。"""
    return col["fs_label"] * 1.45


def module_head(module: str, x: float, mid: float, col: dict, m: dict, fs_h: float,
                active: bool, breath: float, has_switch: bool) -> str:
    """模块标题 —— **有开关参数的模块，标题本身就是开关**：点亮 = 开，点灭 = 关。

    小绪 18:52：去掉 ENABLE 那一行，直接拿 GRAIN / STUTTER 这类模块名当开关。
    状态只在一个地方表达（名称亮度 + 右侧方块的实心/空心），既省一整行，
    也不会出现"标题说开着、开关说关着"这种自相矛盾。
    真机里这一行就是 `*_on` 那个 BoolParam 的命中区。

    **但 ruin / space / out 三个模块压根没有开关参数**（41 参数 + 7 开关），
    所以它们只画标题、不画状态方块 —— 不许假装有开关。
    """
    # 模块名**就是开关**（小绪 18:52），所以关闭态也必须看得清 —— 看不清就点不着。
    # 上一版关闭态用 0.34，实测只有 3.03:1，等于把这个开关藏起来了。
    op = A_TEXT if active else A_OFF
    log_text(op, "bg")
    out = [f'<text x="{x:.1f}" y="{mid + fs_h * .35:.1f}" font-family="{UI}" '
           f'font-size="{fs_h:.1f}" font-weight="600" '
           f'letter-spacing="{TRACK_HEAD * fs_h:.2f}" fill="{INK}" '
           f'fill-opacity="{op:.2f}">{module.upper()}</text>']
    if not has_switch:
        return "".join(out)
    # 状态方块**紧跟名字**，不甩到列的最右边 —— 否则在宽列里离名字两百多像素，
    # 读不出"这个名字就是开关"。方块和名字合成一个整体。
    side = fs_h * 0.78
    bx = x + len(module) * K_LABEL * fs_h + m["gap"]
    # 关 = systemFill 实心块（"这里有个开关，现在是关的"）；开 = 主内容色实心块。
    # 去掉了原来那根描边 —— HIG · Color：层级用"面"表达，不用描边。
    fill, fop = (INK, 0.80 + 0.20 * breath) if active else (FILL, 1.0)
    out.append(f'<rect x="{bx:.1f}" y="{mid - side / 2:.1f}" width="{side:.1f}" '
               f'height="{side:.1f}" fill="{fill}" fill-opacity="{fop:.2f}"/>')
    return "".join(out)


def param_row(c: dict, x: float, mid: float, col: dict, m: dict,
              active: bool, breath: float, state: str = "idle") -> str:
    """一行参数：名称 / 轨道 / 数值。三段之间只留一个 GAP。

    `mid` 是**这一行的光学中线**（由文字基线推回来），不是行框中心 ——
    v0.27 起行是按基线定位的，行框这个概念已经删掉（见 BLOCK_UP 的注释）。

    v0.28 的 Apple 化，四条：
      · 名称 = Caption 1（11pt / Regular），用 secondaryLabel（0.60）——
        名称是**辅助信息**，Apple 里辅助信息一律降一级；
      · 数值 = Callout（12pt / Medium），用 label（1.00）—— 在插件里数值才是
        用户真正要读的东西，所以层级反过来：名字暗、数值亮；
      · 轨道 = systemFill，当前值 = 主内容色填充，**没有圆形把手**（只靠颜色编码）；
      · 关闭态**不靠把字调暗到看不见**来表达 —— 填充退回控件底色、文字降到 A_OFF，
        仍然过 4.5:1。Apple 的 tertiaryLabel(0.30) 在黑底上只有 2.23:1，不能用。

    v0.29 加了交互状态。`state` 是**这一行自己的**状态（不是目标行就传 `"idle"`）：
        idle   常态
        hover  鼠标在这一行上  → 行底一层极淡的墨 + 参数名提到 0.80
        press  正在按          → 墨层加倍 + 参数名满亮
        focus  键盘走到这一行  → 轨道外一圈 3px 强调色环（Apple 的聚焦指示）

    **硬规则：状态只改颜色，不改几何。** 四个态里所有文字的 x,y 与轨道矩形的
    x,y,w,h 必须**逐字节相同**，只有 fill / fill-opacity 与那圈环会变。
    立这条的理由：状态一变就重排，是"闪一下、跳一下"的根因；而且重排之后
    "末行对齐"这类排版断言会全部失效 —— 状态就成了排版的一个隐藏输入。
    self_check 里专门有一节按这条对四张 SVG 逐元素比对。
    """
    gap = m["gap"]
    s = m["s"]
    fs_n, fs_v = col["fs_label"], col["fs_value"]
    tx = x + col["label_w"] + gap
    track_w = col["track_w"]
    nv = norm(c)
    fill, fill_op = (INK, 0.80 + 0.20 * breath) if active else (FILL, 1.0)

    # ── 行底（hover / press）─────────────────────────────────────────────
    # 整行一层极淡的墨，**先画，压在文字和轨道下面**。
    # 注意它会**改变文字的底色**，所以下面登记底色时必须换成 "hover" / "press" ——
    # 否则对比度是拿面板底算出来的，那是个虚数（v0.28 已经在这类事上栽过一次）。
    band = ""
    if state in ("hover", "press"):
        a = HOVER_A if state == "hover" else PRESS_A
        bh = col["pitch"] * ROW_BAND
        band = (f'<rect class="st" x="{x - gap * .5:.1f}" y="{mid - bh / 2:.1f}" '
                f'width="{col["col_w"] + gap:.1f}" height="{bh:.1f}" '
                f'fill="{INK}" fill-opacity="{a:.2f}"/>')
        bd = state
    else:
        bd = "bg"

    # ── 聚焦环（focus）───────────────────────────────────────────────────
    # Apple 的 keyboardFocusIndicator：3px 强调色，与控制体之间留 2px 空隙。
    # **全工程只有这一个地方允许描边矩形。** self_check 里那条"不许有描边矩形"
    # 专门给它开了口子，但要求描边色必须是 ACCENT —— 别的颜色一律拦下。
    ring = ""
    if state == "focus":
        th0 = choice_h(col) if c["fmt"] == "Choice" else track_h(col)
        g, rw = FOCUS_RING_GAP * s, FOCUS_RING_W * s
        ring = (f'<rect class="fr" x="{tx - g - rw / 2:.1f}" '
                f'y="{mid - th0 / 2 - g - rw / 2:.1f}" '
                f'width="{track_w + 2 * g + rw:.1f}" height="{th0 + 2 * g + rw:.1f}" '
                f'fill="none" stroke="{ACCENT}" stroke-width="{rw:.1f}"/>')

    # 参数名随状态提亮：hover 0.80 / press 1.00。**不动位置，只动不透明度。**
    a_name = A_MUTED if active else A_OFF
    if state == "hover":
        a_name = max(a_name, A_HOVER_NAME)
    elif state == "press":
        a_name = A_TEXT
    log_text(a_name, bd)
    out = [band, ring,
           f'<text x="{x:.1f}" y="{mid + fs_n * .35:.1f}" font-family="{UI}" font-size="{fs_n:.1f}" '
           f'font-weight="400" letter-spacing="{TRACK_UI * fs_n:.2f}" fill="{INK}" '
           f'fill-opacity="{a_name:.2f}">{esc(full_name(c))}</text>']

    if c["fmt"] == "Choice":
        cw = track_w / 3
        pos = min(2, max(0, round(c["def"] * 2)))
        th = choice_h(col)               # 由字号定，不跟行距走
        out.append(f'<rect x="{tx:.1f}" y="{mid - th / 2:.1f}" width="{track_w:.1f}" '
                   f'height="{th:.1f}" fill="{SEG_BG}"/>')
        # 模块关着时不画选中块 —— Apple 的禁用控件是"摊平"的，不是"变暗的"。
        # 于是三档标签全部压在 tertiarySystemFill 上，用 A_MUTED，实测 5.91:1。
        if active:
            out.append(f'<rect x="{tx + pos * cw:.1f}" y="{mid - th / 2:.1f}" width="{cw:.1f}" '
                       f'height="{th:.1f}" fill="{GRAY2}"/>')
        # `SEG_BG` 是**半透明**的（α=0.24），所以 hover/press 的行底会透上来，
        # 标签的真实底色变成 `seg` 叠在行底上 —— 登记表必须跟着换，见 backdrops()。
        seg_key = {"hover": "seg_hover", "press": "seg_press"}.get(state, "seg")
        for i, it in enumerate(("LP", "BP", "HP")):
            # 标签压在自己脚下那块面上：
            #   选中块 systemGray2（**不透明**，行底透不上来）→ 主内容色
            #   其余压在 tertiarySystemFill 上 → 次要色 / 关闭态
            if i == pos and active:
                log_text(A_TEXT, "seg_on")
                ta = A_TEXT
            else:
                log_text(a_name, seg_key)
                ta = a_name
            out.append(f'<text x="{tx + cw * (i + .5):.1f}" y="{mid + fs_v * .34:.1f}" '
                       f'text-anchor="middle" font-family="{UI}" font-size="{fs_v * .82:.1f}" '
                       f'font-weight="500" letter-spacing="{TRACK_UI * fs_v:.2f}" fill="{INK}" '
                       f'fill-opacity="{ta:.2f}">{it}</text>')
    else:
        th = track_h(col)                # 同上：由字号定，各列粗细一致
        out.append(f'<rect x="{tx:.1f}" y="{mid - th / 2:.1f}" width="{track_w:.1f}" '
                   f'height="{th:.1f}" fill="{TRACK}"/>')
        # 出厂值刻度：**常显的细刻度**，不表示当前值，只给一个参照。
        dx = tx + track_w * norm(c)
        out.append(f'<line x1="{dx:.1f}" y1="{mid - th * 2.2:.1f}" x2="{dx:.1f}" '
                   f'y2="{mid + th * 2.2:.1f}" stroke="{INK}" stroke-opacity="{A_TICK:.2f}" stroke-width="1"/>')
        # 当前值 = **只有颜色**（填充），没有圆形把手。
        # 留 th 的最小宽度：值为 0 时也留一丝颜色，否则"零"和"没数据"分不清。
        out.append(f'<rect x="{tx:.1f}" y="{mid - th / 2:.1f}" width="{max(th, track_w * nv):.1f}" '
                   f'height="{th:.1f}" fill="{fill}" fill-opacity="{fill_op:.2f}"/>')

    vt = value_text(c)
    if vt:
        a_val = A_TEXT if active else A_OFF
        log_text(a_val, bd)
        out.append(f'<text x="{x + col["col_w"]:.1f}" y="{mid + fs_v * .35:.1f}" text-anchor="end" '
                   f'font-family="{DATA}" font-size="{fs_v:.1f}" font-weight="500" '
                   f'letter-spacing="{TRACK_DATA * fs_v:.2f}" fill="{INK}" '
                   f'fill-opacity="{a_val:.2f}">{vt}</text>')
    return "".join(out)



# ---------------------------------------------------------------------------
# 视图
# ---------------------------------------------------------------------------
# v0.28 删掉了 block_frame() —— 模块**不再是框**。小绪 09:5x：
# 「我不要模块化的边框了，你做的太丑了，直接按照目前市面上最高级的 UI 来做」。
# 分组改回 HIG · Layout 的第一手段：**留白**。
# 于是"模块"这个对象在代码里只剩一个几何量：**行距 pitch**。
# 分组边界不画任何东西，靠"这里空得比别处多 2.5 倍"读出来。
def content_span(m: dict) -> tuple[float, float]:
    """内容区的上下边 —— 也是**第一行墨迹与最后一行墨迹**的约束框。"""
    top = m["rows_top"]
    return top, top + m["avail_h"]


def row_pitch(m: dict, rows: int, blocks: int) -> float:
    """一列有 rows 行、blocks 个分组时，**行与行之间的基线距离**。

    两条要求同时成立（小绪 09:4x）：
      · `其他均匀分布` —— 组内每行等距，间距就是这个 pitch；
      · `我的对齐是 GRAIN MIX 和 STUTTER MIX 这样对齐` —— 每列的**末行**
        落在同一条水平线上，于是**跨列也对齐**。

    解方程（块与块之间的空档 = SECTION_GAP_MULT × pitch）：
        (rows−blocks)·p + blocks·(BLOCK_UP+BLOCK_DOWN)·S
        + (blocks−1)·SECTION_GAP_MULT·p = avail_h
    ⟹  p = [avail_h − blocks·(UP+DOWN)·S] / [rows − blocks + (blocks−1)·M]

    **对齐的必须是文字基线，不是"行框的底边"。** v0.26 对齐的是行框底，
    行框不可见、高度又逐列差 2.5 倍（GRAIN 53px / COMB 132px），
    文字于是差 39px —— 小绪一眼就看出"这也没对齐啊"。行框这个概念已删掉。
    """
    s = m["s"]
    span = m["avail_h"] - blocks * (BLOCK_UP + BLOCK_DOWN) * s
    den = (rows - blocks) + (blocks - 1) * SECTION_GAP_MULT
    return span / den


def section_gap(pitch: float) -> float:
    """模块与模块之间的空档 = 行距 × SECTION_GAP_MULT。

    这是"留白分组"唯一的手段：**组间的空档必须明显大于组内**，
    眼睛才会把它们读成两堆。2.5 倍是实测好读的倍数（HIG 没给数字，
    只说 `use negative space`；2.5 是本项目按面板实测定的）。
    """
    return pitch * SECTION_GAP_MULT


def column_block(ctrls: list[dict], module: str, x: float, top: float, col: dict,
                 m: dict, breath: float, show_head: bool = True,
                 state: str = "idle", target: str | None = None) -> tuple[str, float, float]:
    """画一个模块分组。`top` = 这个分组的**上边界**（不是第一行的位置）。

    行按**文字基线**排：基线_i = top + BLOCK_UP·S + i·pitch。
    返回 (svg, 末行基线, 分组高度) —— 高度由调用方用来接下一段留白。

    `state` + `target`：整张面板只让**一个**控件处在非 idle 态（`target` 是它的
    显示名），其余行一律 idle。这是有意为之 —— 状态接触表要展示的是"鼠标在某一
    行上"，不是"整张面板一起亮"。`target=None` 时全部 idle。
    """
    active = module in LIT
    pitch = col["pitch"]
    fs_h = col["fs_title"]
    out: list[str] = []
    base = top + BLOCK_UP * m["s"]
    if show_head:
        out.append(module_head(module, x, base - fs_h * .35, col, m, fs_h, active, breath,
                               has_switch=switch_of(ctrls, module) is not None))
        base += pitch
    for c in ring_controls(ctrls, module):
        row_state = state if (target is not None and full_name(c) == target) else "idle"
        out.append(param_row(c, x, base - col["fs_label"] * .35, col, m, active, breath,
                             state=row_state))
        base += pitch
    last = base - pitch
    return "".join(out), last, last + BLOCK_DOWN * m["s"] - top


def col_rows(ctrls: list[dict], mods: list[str]) -> int:
    """一列里总共几行（模块标题行 + 参数行）。"""
    return sum(len(block_kinds(ctrls, mod)) for mod in mods)


def module_layout(ctrls: list[dict], m: dict, modules: list[str], breath: float,
                  state: str = "idle", target: str | None = None) -> str:
    """MODULE 模式：**每列一个模块，没有框，靠列与列之间的空档分开**。

    - 列顶（第一行墨迹）与列底（末行墨迹）跨列完全对齐 —— 这就是"上下完全对齐"。
    - 组内行距均匀，末行（GRAIN MIX / STUTTER MIX …）落在同一条水平线上。
    - 列与列之间只留 COL_GAP，不画任何分隔线：分组靠留白。
    """
    lmax, vmax = extents(ctrls, modules)
    pitches = [row_pitch(m, col_rows(ctrls, [mod]), 1) for mod in modules]
    base = columns_for(m, len(modules), lmax, vmax, min(pitches))   # 字号按最挤的列定，各列一致
    top = m["rows_top"]
    out: list[str] = []
    x = m["pane_x0"]
    for mod, pitch in zip(modules, pitches):
        svg, _last, _h = column_block(ctrls, mod, x, top, dict(base, pitch=pitch), m, breath,
                                      state=state, target=target)
        out.append(svg)
        x += base["col_w"] + m["col_gap"]
    return "".join(out)


def all_layout(ctrls: list[dict], m: dict, breath: float,
               state: str = "idle", target: str | None = None) -> str:
    """ALL 模式：每列（lane）若干个模块上下堆叠。

    和 MODULE 模式同一套规则：组内行距均匀、组间空档 = 2.5 × 行距，
    于是每列的**末行**（STUTTER MIX / RUIN RING / OUTPUT）落在同一条水平线上。
    分组之间**什么都不画** —— 只留白。HIG · Layout 说分组可以用
    `negative space, container shapes, or separator lines` 三种手段，
    小绪否掉了后两种，那就把第一种做到位：空档必须是行距的 2.5 倍。
    """
    lanes = ALL_LANES
    shown = [mod for lane in lanes for mod in lane]
    lmax, vmax = extents(ctrls, shown)
    pitches = [row_pitch(m, col_rows(ctrls, lane), len(lane)) for lane in lanes]
    base = columns_for(m, len(lanes), lmax, vmax, min(pitches))
    top = m["rows_top"]
    out: list[str] = []
    x = m["pane_x0"]
    for lane, pitch in zip(lanes, pitches):
        y = top
        parts: list[str] = []
        for mod in lane:
            svg, _last, h = column_block(ctrls, mod, x, y, dict(base, pitch=pitch), m, breath,
                                         state=state, target=target)
            parts.append(svg)              # 每个模块都要收，不能只留最后一个
            y += h + section_gap(pitch)
        out.append("".join(parts))
        x += base["col_w"] + m["col_gap"]
    return "".join(out)


def tabs(m: dict, mode: str, n_modules: int) -> str:
    h = 26.0 * m["s"]
    y = 34.0 * m["s"]
    out = [segmented(m["pane_x0"], y, 168.0 * m["s"], h, ["ALL", "MODULE"],
                     0 if mode == "ALL" else 1, m)]
    # Module 数量只在 MODULE 模式下可用；ALL 是固定全览。
    cx = m["pane_x0"] + m["pane_w"] - 168.0 * m["s"]
    out.append(segmented(cx, y, 168.0 * m["s"], h, ["1", "2", "3", "4"],
                         n_modules - 1, m, disabled=(mode == "ALL")))
    return "".join(out)


def heading(ctrls: list[dict], m: dict, mode: str, modules: list[str]) -> str:
    """副标题是**算出来的**，不是写死的 —— 数字必须和实际画出来的行数一致。

    标题不再重复列出模块名：模块身份由每一列自己的列标题承担，
    列标题在 MODULE 模式下永远都在（n=1 时也保留），所以标题只报"这是什么视图"。
    """
    y = 84.0 * m["s"]
    if mode == "ALL":
        title = "ALL PARAMETERS"
        shown = [mod for lane in ALL_LANES for mod in lane]
    else:
        title = "MODULE PARAMETERS"
        shown = list(modules)
    n_ctrl = sum(rows_of(ctrls, mod) for mod in shown)
    sub = f"{n_ctrl} CONTROLS"
    fs = m["fs_head"]
    log_text(1.0, "bg")            # 视图标题：满白，压在面板底上
    log_text(A_MUTED, "bg")        # 副标题：第二档
    return (f'<text x="{m["pane_x0"]:.1f}" y="{y:.1f}" font-family="{UI}" font-size="{fs:.1f}" '
            f'font-weight="600" letter-spacing="{TRACK_HEAD * fs:.2f}" fill="{INK}">{title}</text>'
            f'<text x="{m["pane_x0"]:.1f}" y="{y + m["fs_sub"] * 2.1:.1f}" font-family="{UI}" '
            f'font-size="{m["fs_sub"]:.1f}" font-weight="400" '
            f'letter-spacing="{TRACK_UI * m["fs_sub"]:.2f}" fill="{INK}" '
            f'fill-opacity="{A_MUTED:.2f}">{sub}</text>')


def divider(m: dict) -> str:
    x, s = m["divider"], m["s"]
    h = m["h"]
    return (f'<line x1="{x:.1f}" y1="{24 * s:.1f}" x2="{x:.1f}" y2="{h - 24 * s:.1f}" '
            f'stroke="{HAIR}" stroke-width="1"/>'
            f'<rect x="{x - 1:.1f}" y="{(h / 2 - 26 * s):.1f}" width="2" height="{52 * s:.1f}" '
            f'fill="{INK}" fill-opacity=".28"/>')


def state_target(ctrls: list[dict], module: str | None = None) -> str:
    """状态接触表里被"指到"的那一行 —— 取**当前 MODULE×1 会显示的那个模块**的
    最后一个环位参数。

    为什么挑最后一个：它在最下面，hover 的行底不会和模块标题的呼吸发光挤在一起，
    截图里一眼就能看出"变的是哪一行"。

    **模块不能写死成 "grain"。** v0.30 把 `SELECTED` 改成 `CHAIN[:4]` 之后，
    MODULE×1 显示的是 FREEZE —— 写死 grain 的话目标行根本不在面板上，
    于是 hover 与 idle 逐字节相同，自检当场报"状态根本没画出来（空转）"。
    让它跟着 `SELECTED[0]` 走，改候选集时不用记得回来改这里。
    """
    module = module or SELECTED[0]
    rows = ring_controls(ctrls, module)
    assert rows, f"{module} 没有环位参数，挑不出状态目标行"
    return full_name(rows[-1])


def panel(geo: dict, ctrls: list[dict], mode: str, n_modules: int, breath: float,
          w: float = REF_W, h: float = REF_H,
          state: str = "idle", target: str | None = None,
          layers: tuple[str, ...] = TREE_LAYERS,
          lit: set[str] | None = None) -> str:
    TEXT_LOG.clear()               # 每次出一张面板就重新登记，self_check 逐张对账
    m = metrics(w, h)
    modules = SELECTED[:n_modules]
    # ALL 视图里"选中"没有区分意义（全都在检查器里），所以不画虚线环。
    selected = modules if mode == "MODULE" else []
    # **必须按文档顺序依次生成**：登记表与 SVG 里的 <text> 要同序，
    # self_check 才能把"这一行字压在哪个底上"逐个对回去（见 check_contrast ③）。
    # 上一版把 body 先算、tabs/heading 在 f-string 里才算，两边顺序就错开了 ——
    # 顺序一对不上，"块内文字用错底色"这类错就查不出来。
    tree, defs = tree_svg(geo, ctrls, m, breath, selected, layers, lit)
    tabs_svg = tabs(m, mode, n_modules)
    head_svg = heading(ctrls, m, mode, modules)
    body = (all_layout(ctrls, m, breath, state=state, target=target) if mode == "ALL"
            else module_layout(ctrls, m, modules, breath, state=state, target=target))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
            f'viewBox="0 0 {w:.0f} {h:.0f}"><defs>{"".join(defs)}</defs>'
            f'<rect width="{w:.0f}" height="{h:.0f}" fill="{BG}"/>'
            f'{tree}{divider(m)}{tabs_svg}{head_svg}{body}</svg>')


def breath_strip(ctrls: list[dict], x0: float, y0: float) -> tuple[str, float, float]:
    """呼吸相位演示：同一组发光，四个相位。证明光晕是动画的，不是静态装饰。"""
    phases = [0.0, 0.35, 0.70, 1.0]
    bw, bh = 200.0, 176.0
    out: list[str] = []
    defs: list[str] = []
    for i, ph in enumerate(phases):
        bx = x0 + i * bw
        out.append(f'<rect x="{bx}" y="{y0}" width="{bw - 8}" height="{bh}" fill="{BG}" '
                   f'stroke="{HAIR}" stroke-width="1"/>')
        cx, cy, r, gr = bx + (bw - 8) / 2, y0 + 74, 30.0, 22.0
        out.append(glow_ring(cx, cy, r, gr, ph, 100 + i, defs))
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{ink_at(CIRC_ON_A)}" '
                   f'stroke="{INK}" stroke-opacity="{0.62 + 0.38 * ph:.2f}" stroke-width="1.4"/>')
        out.append(f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" font-family="{UI}" '
                   f'font-size="10.5" font-weight="600" letter-spacing="-0.13" fill="{INK}" '
                   f'fill-opacity="{A_NODE + (1.0 - A_NODE) * ph:.2f}">GRAIN</text>')
        out.append(f'<text x="{cx:.1f}" y="{cy + 12:.1f}" text-anchor="middle" font-family="{DATA}" '
                   f'font-size="9.5" fill="{INK}" fill-opacity="{A_VAL + 0.20 * ph:.2f}">120MS</text>')
        out.append(f'<text x="{bx + 14:.1f}" y="{y0 + bh - 14:.1f}" font-family="{DATA}" '
                   f'font-size="10" fill="{MUTED}">BREATH {ph:.2f}</text>')
    return "".join(out), 4 * bw, defs


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def single_html(geo, ctrls, mode, n, breath, version) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE V{version} {mode} {n}</title>
<style>html,body{{margin:0;width:{REF_W:.0f}px;height:{REF_H:.0f}px;background:{BG};overflow:hidden}}
svg{{display:block}}</style></head><body>
{panel(geo, ctrls, mode, n, breath)}</body></html>'''


def sheet_html(geo, ctrls, version) -> tuple[str, int, int]:
    cells = [("ALL", 1, "01 · ALL · 3 LANES · 41 CONTROLS"),
             ("MODULE", 1, "02 · MODULE ×1 · FULL-WIDTH EDIT"),
             ("MODULE", 2, "03 · MODULE ×2 · SHARED ROW GRID"),
             ("MODULE", 3, "04 · MODULE ×3"),
             ("MODULE", 4, "05 · MODULE ×4")]
    cards = "".join(f'<section><h2>{cap}</h2><div class="p">{panel(geo, ctrls, md, n, .75)}</div></section>'
                    for md, n, cap in cells)
    strip, sw, _ = breath_strip(ctrls, 0, 0)
    gap, pad = 44, 48
    w = pad * 2 + int(REF_W) * 2 + gap
    h = 300 + 3 * (int(REF_H) + 62)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE UI V{version}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;background:#050506;color:{INK};padding:44px {pad}px 70px;font-family:{UI}}}
h1{{font-size:17px;font-weight:600;letter-spacing:-0.01em}}
p{{margin-top:10px;max-width:1180px;font-size:11px;line-height:1.8;letter-spacing:-0.01em;color:{MUTED}}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:{gap}px;margin-top:40px;align-items:start}}
section:last-child{{grid-column:span 2;justify-self:center}}
h2{{height:32px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{MUTED}}}
.p{{width:{int(REF_W)}px;height:{int(REF_H)}px;box-shadow:0 0 0 1px {HAIR}}}
.p svg{{display:block}}
h3{{margin-top:54px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{MUTED}}}
</style></head><body>
<h1>TRÄNE · V{version} · DARK INSTRUMENT PANEL</h1>
<p>APPLE DARK-MODE SEMANTIC COLOURS · NO BORDERS — GROUPING BY NEGATIVE SPACE ALONE ·
APPLE macOS TYPE SCALE (TITLE 13 / VALUE 12 / NAME 11, NO LIGHT WEIGHTS) ·
ONE ACCENT (THE FOCUS RING), RESERVED FOR THE FOCUS STATE · STATE CHANGES COLOUR ONLY, NEVER GEOMETRY · LAST ROW OF EVERY COLUMN (* MIX) ALIGNS ACROSS COLUMNS, MEASURED ON THE TEXT BASELINE ·
SLIDERS SHOW VALUE BY COLOUR ONLY, NO HANDLE · EVERY SIZE = BASE × SCALE</p>
<div class="grid">{cards}</div>
<h3>06 · BREATHING GLOW · FOUR PHASES OF THE SAME NODE</h3>
<div style="margin-top:14px"><svg xmlns="http://www.w3.org/2000/svg" width="{sw:.0f}" height="176">{strip}</svg></div>
</body></html>''', w, h


def self_check(geo: dict, ctrls: list[dict]) -> None:
    """把十一条逐条变成断言。**绿本身不是证据**，所以每条都断言"必须出现/必须不存在/必须等距"。

    数字类断言全部靠**从生成的 SVG 里读回来量**，不靠"我写的时候是这么写的"。
    """
    cases = [("ALL", 1), ("MODULE", 1), ("MODULE", 2), ("MODULE", 3), ("MODULE", 4)]
    svgs: dict[tuple[str, int], str] = {}
    logs: dict[tuple[str, int], list[tuple[float, str, bool]]] = {}
    for c in cases:
        svgs[c] = panel(geo, ctrls, c[0], c[1], .75)
        logs[c] = list(TEXT_LOG)          # 立刻快照：下一张面板会清空登记表

    names = {full_name(c) for c in ctrls if c["label"]}
    assert len(names) == 41, f"环位参数应为 41 个，实际 {len(names)}（有重名）"

    # 分段控件矩形（底 + 选中块）的提取正则。**命中数必须 ≥ 分段的档数**——
    # 正则匹配不到会让下面的几何断言一次都不执行还显示绿，那是"空转"，不是"通过"。
    SEG = re.compile(r'<rect x="([\d.\-]+)" y="([\d.\-]+)" '
                     r'width="([\d.\-]+)" height="([\d.\-]+)" fill="(?:'
                     + re.escape(SEG_BG) + "|" + re.escape(GRAY2) + r')"/>')

    # ── 对比度 ────────────────────────────────────────────────────────────
    # 面板上**每一处文字**，对它真实的底色都要 ≥ 4.5:1（WCAG 2.1 AA 正文）。
    # 这条以前没有，所以关闭态一路压到 3.03:1 也没人报 —— "报错要报得对"就得连它一起管。
    # 两件事同时成立才算数：
    #   ① 登记表里的每一对 (不透明度, 底色) 复算对比度过线；
    #   ② 登记表与 SVG 里**真实出现**的文字不透明度逐个对账。
    # 只查 ① 挡不住"改了绘制代码没改登记表"，只查 ② 挡不住"两边一起错"。
    bd = backdrops()
    worst = [99.0, ""]

    def check_contrast(svg: str, log: list[tuple[float, str, bool]], tag: str) -> None:
        for a, key, dark in log:
            assert key in bd, f"{tag}: 登记了未知底色 {key!r}"
            # **必须用 INK_RGB 合成，不能用纯白。** 文字实际是 #EBEBF5（Apple 的
            # 次级文字色），用 (255,255,255) 合成会**算高**对比度 —— 这条自己错过一次：
            # 分段选中标签退回 0.56 时，按纯白算是 4.5x，按 #EBEBF5 算只有 2.7:1，
            # 于是那处突变漏网了（反向对照实测）。
            fg = bd["bg"] if dark else over(a, INK_RGB, bd[key])
            r = contrast(fg, bd[key])
            how = "深字" if dark else f"α={a:.2f}"
            assert r >= CONTRAST_MIN, \
                f"{tag}: 文字 {how} 压在 {key} {hex_of(bd[key])} 上只有 {r:.2f}:1（要 ≥ {CONTRAST_MIN}）"
            if r < worst[0]:
                worst[0], worst[1] = r, f"{tag} {how} on {key} {hex_of(bd[key])}"

        found: list[float] = []
        dark_found = 0
        for el in re.findall(r"<text\b[^>]*>", svg):
            mf = re.search(r'fill="([^"]+)"', el)
            assert mf, f"{tag}: 有 <text> 没写 fill —— 那它按默认黑画，等于没管"
            f = mf.group(1)
            if f == BG:
                dark_found += 1
                found.append(1.0)
                continue
            # 文字只允许用两个令牌：满白（再乘 fill-opacity）或深底墨。
            # 出现第三个颜色（比如又拿 FAINT 当文字用）就地报红。
            assert f == INK, f"{tag}: 文字用了非令牌的填充 {f!r}"
            mo = re.search(r'fill-opacity="([\d.]+)"', el)
            found.append(float(mo.group(1)) if mo else 1.0)
        want = sorted(a for a, _k, _d in log)
        assert sorted(found) == want, \
            f"{tag}: SVG 里文字不透明度 {sorted(found)} ≠ 登记表 {want}"
        n_dark = sum(1 for _a, _k, d in log if d)
        assert dark_found == n_dark, \
            f"{tag}: 深字压亮块的有 {dark_found} 处，登记表说 {n_dark} 处"

        # ③ 文字**压在哪块面上**必须和登记的底色对得上 —— 靠**几何**判，不靠数值相等。
        #    只对 alpha 逐个对账挡不住"换了底色但登记表没换"：两边 alpha 一模一样，
        #    算出来的对比度是虚的。这里拿分段控件的矩形当尺子：
        #    登记成 "seg"/"seg_on" 的文字，锚点必须真的落在对应的矩形里。
        segs = [(float(a), float(b), float(c), float(d)) for a, b, c, d in SEG.findall(svg)]
        assert segs, f"{tag}: 一个分段控件矩形都没量到（提取正则空转）"
        pts = re.findall(r'<text x="([\d.\-]+)" y="([\d.\-]+)"', svg)
        assert len(pts) == len(log), \
            f"{tag}: SVG 里文字 {len(pts)} 个 ≠ 登记表 {len(log)} 条（顺序对不上）"
        n_seg_txt = 0
        for (px, py), (_a, key, _d) in zip(pts, log):
            fx, fy = float(px), float(py)
            inside = any(bx - .05 <= fx <= bx + bw + .05 and by - .05 <= fy <= by + bh + .05
                         for bx, by, bw, bh in segs)
            if key in ("seg", "seg_on"):
                n_seg_txt += 1
                assert inside, \
                    f"{tag}: 分段标签 ({fx:.0f},{fy:.0f}) 登记成 {key!r}，却不在任何分段控件矩形里"
            else:
                # **反过来也要查。** 只查一个方向的话，"把 seg 写成 bg"这种错会漏网 ——
                # 登记成 bg 的文字不在 seg 矩形里也不报错，而 bg 比 seg 亮，
                # 对比度还更高。两边一起错就没人管了。
                assert not inside, \
                    f"{tag}: 文字 ({fx:.0f},{fy:.0f}) 明明压在分段控件上，却登记成 {key!r}"
        assert n_seg_txt > 0, f"{tag}: 一段分段标签都没验到（空转）"
        # 非文字用 FAINT 是可以的（出厂值刻度、发丝线）；拿它当文字色会被上面
        # "文字只允许两个令牌"那条就地拦下，不需要再单独断言。

    # **呼吸的最低点必须单独验。** 所有"活动"文字的不透明度都是 breath 的增函数，
    # 所以 breath=0 就是对比度最差的那一相。上一版只在 breath=0.75 出图，
    # 于是"树上数值退回 0.45"这种只在最低点才暴露的错误直接漏网
    # （反向对照实测漏网）—— 这个循环就是那次漏网补上的。
    for ph in (0.0, 0.75, 1.0):
        for mode, n in cases:
            if ph == 0.75:
                check_contrast(svgs[(mode, n)], logs[(mode, n)], f"{mode}/{n}·b0.75")
            else:
                check_contrast(panel(geo, ctrls, mode, n, ph), list(TEXT_LOG),
                               f"{mode}/{n}·b{ph:.2f}")

    # ── 覆盖：Choice 控件的「选中」分支 ────────────────────────────────────
    # `sweep_mode` 是全工程**唯一**的 Choice，而 sweep 既不在 LIT、也不在 SELECTED 里。
    # 于是 `param_row()` 里 `if i == pos and active:` 那条分支**从来没有被执行过** ——
    # "选中标签压在 systemGray2 上"的对比度、以及它登记成 seg_on 这件事，全都没验过。
    # 反向对照实测：把选中标签的 α 从 1.00 改到 0.56，**一个断言都不响**。
    # 这就是"空转"：测试在跑，只是没跑到该跑的地方。绿是假的。
    # 所以这里临时把 sweep 点亮，专门覆盖它，再用**差分**证明这条分支真的走到了。
    saved_lit = set(LIT)
    LIT.add("sweep")
    try:
        svg_ch = panel(geo, ctrls, "ALL", 1, .75)
        log_ch = list(TEXT_LOG)          # 立刻快照：下一张面板会清空登记表
    finally:
        LIT.clear()
        LIT.update(saved_lit)
    base_on = sum(1 for _a, k, _d in logs[("ALL", 1)] if k == "seg_on")
    lit_on = sum(1 for _a, k, _d in log_ch if k == "seg_on")
    assert lit_on > base_on, \
        (f"把 sweep 点亮之后 seg_on 没有变多（{base_on} → {lit_on}）—— "
         f"Choice 控件的选中分支根本没走到，等于没测")
    check_contrast(svg_ch, log_ch, "ALL/1·sweep亮")

    # ── ④ **面板上不许再有框** ────────────────────────────────────────────
    # 小绪 09:5x「我不要模块化的边框了」→ 所有 `<rect>` 一个描边都不许有。
    # （发丝线是 `<line>`，圆是 `<circle>`，都不受影响。）
    #
    # v0.29 唯一开口子的地方是**聚焦环**：键盘焦点必须有可见指示，而 Apple 的
    # keyboardFocusIndicator 就是一圈强调色描边。所以规则收紧成
    # **"描边只准用强调色"** —— 这样"顺手给模块加个描边"照样会被抓到。
    #
    # 写成**共享函数**，常态五张 + 四个状态**各调一次**。上一版把这段写在
    # 循环体里，`state == "focus"` 那一支在只跑 idle 的循环里永远不执行 ——
    # 那是"空转"：断言写得再对，没跑到就是装饰。
    def assert_no_frames(svg: str, tag: str, state: str) -> None:
        rects = re.findall(r"<rect\b[^>]*>", svg)
        assert rects, f"{tag}: 一个矩形都没有（空转）"
        n_ring = 0
        for el in rects:
            if "stroke=" in el:
                assert f'stroke="{ACCENT}"' in el, \
                    f"{tag}: 有非聚焦环的描边矩形（小绪：不要模块化的边框）—— {el[:96]}"
                n_ring += 1
        # 聚焦环只在 focus 态出现，而且**必须**出现 —— 不然"键盘走到这一行"
        # 就没有任何可见反馈，等于不可用。
        want = 1 if state == "focus" else 0
        assert n_ring == want, f"{tag}: {state} 态应有 {want} 圈聚焦环，实际 {n_ring} 圈"
        assert (ACCENT in svg) == (state == "focus"), \
            f"{tag}: 强调色只准出现在聚焦态（{state} 态下 {'有' if ACCENT in svg else '没有'}）"

    for (mode, n), svg in svgs.items():
        tag = f"{mode}/{n}"
        state = "idle"               # 这批是常态面板；状态变体在下面单独验
        # 4 · 11 · 6：不该出现的字样
        for bad in ("FOCUS", "SIGNAL", "MODULES"):
            assert bad not in svg, f"{tag}: 面板上仍有 {bad!r}"
        # 13 · 标题不许用加号拼模块名（小绪 18:32：直接靠模块块表现就够）。
        # 数值里的 "+0.0DB" 没有空格，所以用带空格的 " + " 精确匹配。
        assert " + " not in svg, f"{tag}: 标题还在用加号拼模块名"
        # 12 · 全面板**任何地方**都不许有圆角矩形。
        # 这条写在面板级而不是控件内部 —— 上一版只在 segmented() 里断言，
        # 把那条断言关掉就没人管了（反向对照实测漏网）。
        assert "rx=" not in svg, f"{tag}: 面板上还有圆角矩形"
        # 3 · 底色必须是纯黑档，文字必须白
        assert f'<rect width="{REF_W:.0f}" height="{REF_H:.0f}" fill="{BG}"/>' in svg, \
            f"{tag}: 底色不是 {BG}"
        assert f'fill="{INK}"' in svg, f"{tag}: 没有白色墨"
        # 8 · 强调色不存在 —— 暗场版"强调"就是白本身，不许再出现彩色
        assert "0ABAB5" not in svg and "00938F" not in svg, f"{tag}: 还残留蒂芙尼蓝"

        texts = re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)
        assert texts, f"{tag}: 一个文字都没有（空转）"
        # 2 · 全部大写：文本节点里不许有小写字母
        for t in texts:
            assert t == t.upper(), f"{tag}: 非大写文本 {t!r}"
        # 2 · 参数名必须是全称，且当前视图该显示的参数一个不少、一个不多
        mods_here = ([mod for lane in ALL_LANES for mod in lane] if mode == "ALL"
                     else SELECTED[:n])
        want_names = {full_name(c) for c in ctrls if c["label"] and c["module"] in mods_here}
        shown = {t for t in texts if t in names}
        assert shown == want_names, \
            f"{tag}: 参数名对不上，缺 {sorted(want_names - shown)}，多 {sorted(shown - want_names)}"

        # ── 排版：全部从生成的 SVG 里**量回来**，不信"我写的时候是这么写的" ──────
        m = metrics(REF_W, REF_H)
        lanes = ALL_LANES if mode == "ALL" else [[mod] for mod in SELECTED[:n]]
        lmax, vmax = extents(ctrls, [mod for lane in lanes for mod in lane])
        pitches = [row_pitch(m, col_rows(ctrls, lane), len(lane)) for lane in lanes]
        col = columns_for(m, len(lanes), lmax, vmax, min(pitches))
        top_c, bot_c = content_span(m)

        named = [(float(y), float(x)) for x, y, t in
                 re.findall(r'<text x="([\d.\-]+)" y="([\d.\-]+)"[^>]*>(.*?)</text>', svg, re.S)
                 if t in names]
        assert named, f"{tag}: 量不到任何参数行（空转）"
        by_x: dict[float, list[float]] = {}
        for y, x in named:
            by_x.setdefault(round(x, 1), []).append(y)
        xs = sorted(by_x)
        assert len(xs) == len(lanes), f"{tag}: 参数列数 {len(xs)} ≠ 预期 {len(lanes)}"

        # 列的位置按 **列宽 + COL_GAP** 步进 —— 不再有"框宽"这一层。
        for a, b in zip(xs, xs[1:]):
            assert abs((b - a) - (col["col_w"] + m["col_gap"])) < 0.2, \
                f"{tag}: 列距 {b - a:.1f} ≠ 列宽+列间距 {col['col_w'] + m['col_gap']:.1f}"
        assert col["track_w"] >= MIN_TRACK * m["s"] - 0.05, \
            f"{tag}: 轨道只剩 {col['track_w']:.1f}px"

        # 每一列的所有文字基线（含模块标题）—— 用来量"末行"和"组间空档"。
        all_y: dict[float, list[float]] = {}
        for x2, y2 in ((float(a), float(b)) for a, b in
                       re.findall(r'<text x="([\d.\-]+)" y="([\d.\-]+)"', svg)):
            if round(x2, 1) in by_x:
                all_y.setdefault(round(x2, 1), []).append(y2)
        for x in all_y:
            all_y[x].sort()

        # ① 逐列重建预期基线并核对：画出来的必须和模型一致。
        for x, lane, pitch in zip(xs, lanes, pitches):
            ys = sorted(by_x[x])
            exp_y: list[float] = []
            b = top_c + BLOCK_UP * m["s"]
            for mi, mod in enumerate(lane):
                kinds = block_kinds(ctrls, mod)
                for ri, kind in enumerate(kinds):
                    if kind == "param":                       # 只有参数行进了 by_x
                        exp_y.append(b)
                    if ri == len(kinds) - 1 and mi + 1 < len(lane):
                        # 跨分组：末行 → 下一组首行 = 降部 + 组间空档 + 大写字高
                        b += (BLOCK_UP + BLOCK_DOWN) * m["s"] + section_gap(pitch)
                    else:
                        b += pitch
            assert len(ys) == len(exp_y), f"{tag}/x{x}: 参数行 {len(ys)} ≠ 预期 {len(exp_y)}"
            for got, want in zip(ys, exp_y):
                assert abs(got - want) < 0.07, \
                    f"{tag}/x{x}: 行位 {got:.1f} ≠ 预期 {want:.1f}（偏差 {got - want:+.2f}px）"

        # ② **末行必须跨列对齐** —— 小绪 09:4x「我的对齐是 GRAIN MIX 和 STUTTER MIX
        #    这样对齐」。直接量**渲染出来的文字基线**，不量任何看不见的框。
        #    v0.26 量的是"行框的底边"，行框不可见、高度又逐列差 2.5 倍，
        #    于是自检全绿而文字差 39px —— 小绪一句"这也没对齐啊"就点破了。
        #    **量的东西必须是肉眼能看见的东西。**
        lasts = [all_y[x][-1] for x in xs]
        assert max(lasts) - min(lasts) < 0.12, \
            f"{tag}: 各列末行文字基线不齐 {[round(v, 1) for v in lasts]}"
        for v in lasts:
            assert abs(v - (bot_c - BLOCK_DOWN * m["s"])) < 0.12, \
                f"{tag}: 末行基线 {v:.1f} ≠ 内容区底 − 降部 {bot_c - BLOCK_DOWN * m['s']:.1f}"

        # ③ **分组靠留白**：组间的空档必须**明显大于**组内，否则眼睛读不出"这是两堆"。
        #    设计值就是 SECTION_GAP_MULT，先把它本身卡住（静态、不可能被渲染误差稀释）；
        #    再从渲染出来的基线量一遍实际比值（动态，能抓到"公式解错了"）。
        #    两个都要：只卡静态挡不住公式错，只量动态又会被 UP+DOWN 那 32px 稀释
        #    —— 实测把倍数降到 1.2，动态比值仍有 2.37，看着"通过"其实分组已经散了。
        assert SECTION_GAP_MULT >= 2.0, \
            f"分组空档只有 {SECTION_GAP_MULT}× 行距 —— 低于 2 倍眼睛读不出分组"
        for x, lane, pitch in zip(xs, lanes, pitches):
            if len(lane) < 2:
                continue
            ys = all_y[x]
            diffs = [b2 - a2 for a2, b2 in zip(ys, ys[1:])]
            assert min(diffs) > 0.5, f"{tag}/x{x}: 有两行叠在一起（间距 {min(diffs):.2f}）"
            assert max(diffs) / min(diffs) >= 2.0, \
                (f"{tag}/x{x}: 分组读不出来 —— 组间 {max(diffs):.1f} / 组内 {min(diffs):.1f} "
                 f"只有 {max(diffs) / min(diffs):.2f} 倍")

        # ④ 面板上一个描边矩形都不许有（唯一例外是聚焦环，见 assert_no_frames）
        assert_no_frames(svg, tag, state)

    # ── 交互状态（v0.29）─────────────────────────────────────────────────
    # 硬规则：**状态只改颜色，不改几何。**
    # 四张 SVG 里所有文字的 (x,y) 与所有轨道/分段矩形的 (x,y,w,h) 必须**逐字节相同**。
    # 这条比"好不好看"重要得多：
    #   · 状态一变就重排 → 鼠标扫过去"跳一下"；
    #   · 更要命的是，上面那一大段排版断言会**全部失效** —— 状态成了排版的隐藏输入。
    tgt = state_target(ctrls)
    st_svg: dict[str, str] = {}
    st_log: dict[str, list[tuple[float, str, bool]]] = {}
    for st in STATES:
        st_svg[st] = panel(geo, ctrls, "MODULE", 1, .75, state=st, target=tgt)
        st_log[st] = list(TEXT_LOG)      # 立刻快照

    def geom(svg: str) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, str]]]:
        """抽几何：所有文字的 (x,y) + 所有矩形/轨道的 (x,y,w,h)。

        **排除 `class="st"`（行底）与 `class="fr"`（聚焦环）** —— 那两个是状态
        **新加**的覆盖层，本来就只该在非 idle 态出现，它们不是"布局"。
        排除靠 class，不靠"看起来像"：靠颜色或坐标猜，改一次绘制就失准。
        """
        texts = re.findall(r'<text x="([\d.\-]+)" y="([\d.\-]+)"', svg)
        rects: list[tuple[str, str, str, str]] = []
        for el in re.findall(r"<rect\b[^>]*>", svg):
            if 'class="st"' in el or 'class="fr"' in el:
                continue
            a = re.search(r'x="([\d.\-]+)" y="([\d.\-]+)" '
                          r'width="([\d.\-]+)" height="([\d.\-]+)"', el)
            if a:
                rects.append(a.groups())
        return texts, rects

    g0 = geom(st_svg["idle"])
    assert g0[0], "状态几何比对：一个文字都没量到（空转）"
    assert g0[1], "状态几何比对：一个矩形都没量到（空转）"
    for st in STATES[1:]:
        # 先证明状态**真的改变了输出** —— 否则"几何没变"是因为什么都没发生。
        assert st_svg[st] != st_svg["idle"], \
            f"{st} 态与 idle 逐字节相同 —— 状态根本没画出来（空转）"
        g = geom(st_svg[st])
        if g != g0:
            bad = (next((p for p in zip(g[0], g0[0]) if p[0] != p[1]), None)
                   or next((p for p in zip(g[1], g0[1]) if p[0] != p[1]), None)
                   or ("数量不同", f"{len(g[0])}/{len(g0[0])} 文字 {len(g[1])}/{len(g0[1])} 矩形"))
            raise AssertionError(
                f"状态 {st} 改了**几何**（只准改颜色）—— 第一处不同：{bad}")

    # 行底强度必须**单调**：idle(0) < hover < press，且 press 至少是 hover 的两倍
    # —— 不然"按下"和"悬停"看起来一样，用户不知道点没点上。
    assert 0 < HOVER_A < PRESS_A, f"状态强度不单调：hover {HOVER_A} / press {PRESS_A}"
    assert PRESS_A >= HOVER_A * 2, \
        f"按下只有悬停的 {PRESS_A / HOVER_A:.2f} 倍 —— 读不出'按住了'"

    # 状态下的文字仍要过线：行底换成了 hover / press，**登记表也必须跟着换**。
    # 只改绘制不改登记表的话，对比度是拿面板底算出来的 —— 那是个虚数。
    for st in ("hover", "press"):
        check_contrast(st_svg[st], st_log[st], f"MODULE/1·{st}")
        assert any(k == st for _a, k, _d in st_log[st]), \
            f"{st} 态没有任何文字登记成压在 {st!r} 行底上（行底没画？还是登记表没换？）"
    for st in STATES:
        assert_no_frames(st_svg[st], f"MODULE/1·{st}", st)

    # 动效时长：HIG · Motion 说反馈要 `brief and precise`，并且
    # `generally avoid adding motion to UI interactions that occur frequently`。
    assert 0 < MOTION_FAST <= MOTION_STD <= MOTION_MAX, \
        f"动效时长不在 HIG 的 brief 区间：fast {MOTION_FAST} / std {MOTION_STD} / 上限 {MOTION_MAX}"
    assert MOTION_DRAG == 0.0, \
        (f"拖参数被加了 {MOTION_DRAG}s 动效 —— HIG：频繁交互不加动效。"
         f"拖参数一秒几十次，任何过渡都会变成拖尾")
    # Reduce Motion 必须是**精确的 0**：写成 0.05 之类的"小一点"等于没关掉。
    assert REDUCE_MOTION_SCALE == 0.0, \
        f"减弱动态效果只把时长缩到 {REDUCE_MOTION_SCALE} 倍 —— 必须是 0（真的关掉）"
    assert MOTION_EASE.count(",") == 3, f"缓动曲线不是三次贝塞尔：{MOTION_EASE}"

    # ④ **面板上不许再有框** —— 断言在循环外定义（`assert_no_frames`），
    #    循环里每一张都调一次，四个状态也各调一次。写在循环体里的话，
    #    `state == "focus"` 那一支在只跑 idle 的循环里永远不执行 —— 那是空转。
    #
    # 内容尺寸必须与行距**解耦**：行距变化后行数少的列轨道会变粗
    # （MODULE×4 实测 COMB/TAPE 的轨道比 GRAIN 粗一倍）。这条盯着别再耦合回去。
    ca = {"s": 1.0, "fs_label": 11.0, "fs_value": 12.0, "fs_title": 13.0,
          "track_w": 200.0, "col_w": 300.0, "pitch": 20.0}
    cb = dict(ca, pitch=180.0)
    m2 = metrics(REF_W, REF_H)
    assert track_h(ca) == track_h(cb), "轨道厚度还在跟行距走"
    assert choice_h(ca) == choice_h(cb), "Choice 块高还在跟行距走"
    assert module_head("grain", 0, 0, ca, m2, 13.0, True, .75, True) == \
           module_head("grain", 0, 0, cb, m2, 13.0, True, .75, True), \
        "模块开关尺寸还在跟行距走"

    # **字号必须来自 Apple 的 macOS 文字样式阶梯**（13 / 12 / 11），
    # 而不是随手写三个数。HIG · Typography 的 Specifications 表就是这份清单。
    # 这条盯着"哪天有人把某一档单独改大"——那会把层级压平。
    assert (FS_TITLE, FS_VALUE, FS_NAME) == (13.0, 12.0, 11.0), \
        f"字号阶梯被改动了：{FS_TITLE}/{FS_VALUE}/{FS_NAME}（Apple 是 13/12/11）"
    assert FS_TITLE > FS_VALUE > FS_NAME, "三档字号没有拉开层级"
    assert FS_MIN >= 10.0, \
        f"字号下限 {FS_MIN} 低于 Apple 的 macOS 最小可读字号 10pt"

    # 关闭态用的是**面**（填充退回 systemFill），不是"把字调到看不见"。
    # Apple 的 tertiaryLabel(0.30) 在黑底上只有 2.23:1 —— 不能拿来当文字色。
    assert A_OFF >= 0.50, f"关闭态文字 α={A_OFF} 太低（Apple 的 0.30 过不了 4.5:1）"
    assert A_TICK <= 0.30, f"刻度 α={A_TICK} 高于 Apple 的 tertiaryLabel(0.30)"

    # 18:52 · ENABLE 那一行已并入模块标题 —— 面板上不该再有 ENABLE 字样
    for (mode, n), svg in svgs.items():
        assert "ENABLE" not in svg, f"{mode}/{n}: ENABLE 那一行没删干净"

    # 标题当开关：**只有真的有开关参数的模块**才画状态方块。
    # ruin / space / out 没有 `*_on`，画了就是撒谎。
    mods_all = [mod for lane in ALL_LANES for mod in lane]
    n_sw = sum(1 for mod in mods_all if switch_of(ctrls, mod) is not None)
    assert n_sw == 7, f"带开关的模块应为 7 个，实际 {n_sw}"
    for mod in mods_all:
        want = switch_of(ctrls, mod) is not None
        got = module_head(mod, 0, 0, ca, m2, 15.0, True, .75, want)
        assert ("<rect" in got) == want, \
            f"{mod}: 状态方块画错（有开关={want}，却{'有' if '<rect' in got else '没有'}方块）"

    # 12 · 推子上不许有圆形把手 —— 只用颜色表示值
    m1 = metrics(REF_W, REF_H)
    p1 = row_pitch(m1, col_rows(ctrls, [SELECTED[0]]), 1)
    probe_col = dict(columns_for(m1, 1, 14, 6, p1), pitch=p1)
    for c in ctrls:
        if not c["label"] or c["fmt"] == "Choice":
            continue
        probe = param_row(c, 0, 0, probe_col, m1, True, .75)
        assert "<circle" not in probe, f"{c['name']}: 推子上还有圆形把手"

    # 5 · 6 · Module 数量可自定义且**排版真的跟着变**：列宽必须随 N 单调变窄
    m0 = metrics(REF_W, REF_H)
    def cols(n: int) -> dict:
        mods = SELECTED[:n]
        # 每列只有一个模块，行距按**该模块自己的行数**解出来。
        p = row_pitch(m0, col_rows(ctrls, [mods[-1]]), 1)
        lm, vm = extents(ctrls, mods)
        return columns_for(m0, n, lm, vm, p)
    widths = [cols(n)["col_w"] for n in (1, 2, 3, 4)]
    assert all(a > b for a, b in zip(widths, widths[1:])), f"列宽没随 N 变：{widths}"
    tracks = [cols(n)["track_w"] for n in (1, 2, 3, 4)]
    assert all(a > b for a, b in zip(tracks, tracks[1:])), f"轨道长没随 N 变：{tracks}"
    fonts = [cols(n)["fs_label"] for n in (1, 2, 3, 4)]
    assert all(a >= b for a, b in zip(fonts, fonts[1:])), f"字号没随 N 变：{fonts}"

    # 9 · 按比例缩放。**以前只验了 S=1.0 和 S=1.5 两档** —— 两档都只是"整张等比放大"，
    # 而且都落在同一个形状上，于是"某些尺寸压根不跟 S 走"这类错误一路漏过去
    # （实测：轨道最细 2px 写成绝对值，S<0.556 就卡住不再变细）。
    # 现在铺开验：每一档缩放都要 ① 每条坐标 = 基准 × S ② 内容不越界 ③ 几何量也按 S 走。
    # 坐标必须成对取：SVG 里 y 永远跟在 x 后面（`<text x="…" y="…"`），
    # 写成 `<text y="` 一次都匹配不到 —— 上一版就是这么写的，靠下面那条
    # "量不到文字（空转）"的断言当场抓住，不然整个循环体一次都不执行还显示绿。
    XY = re.compile(r'<text x="([\d.\-]+)" y="([\d.\-]+)"')

    def text_xy(svg: str) -> tuple[list[float], list[float]]:
        hits = XY.findall(svg)
        assert hits, "量不到任何文字坐标（空转）"
        return sorted(float(p[0]) for p in hits), sorted(float(p[1]) for p in hits)

    a = svgs[("MODULE", 2)]
    ax, ay = text_xy(a)
    for sc in (0.5, 0.7, 1.0, 1.33, 1.5, 2.0):
        w, h = REF_W * sc, REF_H * sc
        big = panel(geo, ctrls, "MODULE", 2, .75, w=w, h=h)
        bx, by = text_xy(big)
        assert len(bx) == len(ax) and len(by) == len(ay), f"S={sc}: 文字数量变了（空转）"
        for p, q in zip(ax, bx):
            assert abs(q - p * sc) < 0.25, f"S={sc}: x {p} → {q}（应为 {p * sc:.1f}）"
        for p, q in zip(ay, by):
            assert abs(q - p * sc) < 0.25, f"S={sc}: y {p} → {q}（应为 {p * sc:.1f}）"
        # 内容必须整整齐齐待在画布内（这条同时盯着"非基准比例被悄悄兜住"）
        assert 0 <= min(bx) and max(bx) <= w + 0.05, f"S={sc}: 文字横向越界"
        assert 0 <= min(by) and max(by) <= h + 0.05, f"S={sc}: 文字纵向越界"

    # 9b · 几何量（不只是文字坐标）也必须按 S 走 —— 非缩放的绝对值就藏在这里。
    def geom(sc: float) -> dict:
        mm = metrics(REF_W * sc, REF_H * sc)
        p = row_pitch(mm, col_rows(ctrls, SELECTED[:2]), 1)
        lm, vm = extents(ctrls, SELECTED[:2])
        col = dict(columns_for(mm, 2, lm, vm, p), pitch=p)
        return {"fs": col["fs_label"], "fs_title": col["fs_title"],
                "track_h": track_h(col), "choice_h": choice_h(col),
                "pitch": p, "section_gap": section_gap(p),
                "gap": mm["gap"], "col_gap": mm["col_gap"], "pad": mm["pad"],
                "up": BLOCK_UP * mm["s"], "down": BLOCK_DOWN * mm["s"],
                "col_w": col["col_w"]}
    g1 = geom(1.0)
    for sc in (0.5, 0.7, 1.33, 1.5, 2.0):
        g = geom(sc)
        for k, v in g.items():
            assert abs(v - g1[k] * sc) < 1e-6, \
                f"S={sc}: {k} = {v:.4f} ≠ {g1[k] * sc:.4f}（有非缩放的常量混进去了）"

    # 9c · 非基准比例必须**报错**，不许被悄悄兜住。这条是给上面那道闸门本身做测试 ——
    # 只写 assert 而没人验它会不会响，等于没写。
    for bad in ((1440, 900), (1200, 900), (1440, 600), (900, 720), (2160, 1100)):
        try:
            metrics(*bad)
        except AssertionError:
            pass
        else:
            raise AssertionError(f"画布 {bad[0]}×{bad[1]} 不是基准比例，metrics() 却没报错")
    # 反过来：基准比例的整数倍缩放不许被误伤
    for ok in ((1440, 720), (2160, 1080), (720, 360), (1441, 720)):
        metrics(*ok)

    # 10 · 呼吸：同一节点在不同 breath 下，光晕峰值必须真的不同
    peaks = []
    for ph in (0.0, 0.35, 0.70, 1.0):
        d: list[str] = []
        glow_ring(100, 100, 30, 22, ph, 0, d)
        ops = re.findall(r'stop-opacity="([\d.]+)"', d[0])
        assert len(ops) == 3, f"光晕梯度应为 3 个 stop，实际 {len(ops)}"
        peaks.append(float(ops[1]))          # 中间那档才是峰值，首尾都是 0
    assert len(set(peaks)) == 4 and peaks == sorted(peaks), f"呼吸没有真的在动：{peaks}"

    # ── 动线（v0.30）─────────────────────────────────────────────────────
    # 三件事：① 树的纵轴**就是**信号轴 ② 信号层是独立的一层、只向前、不自交
    #          ③ 检查器的阅读顺序 = 信号顺序
    #
    # ① 探针吐出的 node 顺序 = `TranePanel.h::kNodes` 顺序 = `TraneEngine.cpp::process()`
    #    顺序。先拿探针回来对账 —— 这条盯着"改了 DSP 顺序却忘了改界面"：
    #    DSP 顺序一变，探针输出跟着变，这里立刻报红。**不靠人记得回来改。**
    probe_order = [n["module"] for n in geo["nodes"]]
    assert probe_order == CHAIN, (
        f"树上节点的顺序与信号链对不上：\n  探针 {probe_order}\n  CHAIN {CHAIN}\n"
        f"（改了 core/TraneEngine.cpp 的处理顺序，就要同步 CHAIN 与 kNodes）")
    assert len(set(CHAIN)) == len(CHAIN) == 10, f"CHAIN 不是 10 个互不相同的模块：{CHAIN}"

    node_y = {n["module"]: n["y"] for n in geo["nodes"]}
    node_x = {n["module"]: n["x"] for n in geo["nodes"]}
    ys_chain = [node_y[mod] for mod in CHAIN]
    for ya, yb in zip(ys_chain, ys_chain[1:]):
        assert ya <= yb, (
            f"树上的 y 在信号链里**回头**了：{ya} → {yb}。"
            f"树的纵轴必须就是信号轴（上 = 入，下 = 出），"
            f"否则「信号往下流」这个读法不成立，整条动线就没了依据")
    # 而且必须真的分层：10 个质点落在 7 条水平线上（同层左右成对）
    assert len(set(ys_chain)) == 7, \
        f"质点分成了 {len(set(ys_chain))} 层，应为 7 层（10 个点里 3 对同层）"

    # ② 信号层 = CHAIN 的相邻对。**推导，不手写** —— 手写一份就多一个会分叉的地方。
    assert SIGNAL_PATH == [(CHAIN[i], CHAIN[i + 1]) for i in range(9)], \
        "SIGNAL_PATH 不是 CHAIN 的相邻对 —— 有人手写了一份"
    assert len(set(SIGNAL_PATH)) == 9, f"信号层有重复的边：{SIGNAL_PATH}"

    for na, nb in SIGNAL_PATH:
        assert node_y[nb] >= node_y[na] - 1e-6, \
            f"信号边 {na} → {nb} 在往回走（y {node_y[na]} → {node_y[nb]}）"
    n_horiz = sum(1 for na, nb in SIGNAL_PATH if abs(node_y[nb] - node_y[na]) < 1e-6)
    assert n_horiz == 3, f"同层横跨应为 3 条（树有三对同层质点），实际 {n_horiz}"

    # **信号层必须是真的独立一层，不是 PATHS 换了个名字。**
    # 实测：PATHS 的 22 条里命中 8 条信号边，唯一缺的是 `stutter → comb`
    # （22 条是"相邻节点两两连线"，2→3 恰好不在其中）。所以信号层**不能**复用 PATHS，
    # 而正因为独立，生命之树"一条不多一条不少"的原始设定也保住了。
    # `PATHS` 是**下标**对（指向探针的 node 顺序 = CHAIN），先翻成模块名再比。
    path_pairs = {tuple(sorted((CHAIN[a], CHAIN[b]))) for a, b in PATHS}
    sig_pairs = {tuple(sorted(p)) for p in SIGNAL_PATH}
    assert sig_pairs != path_pairs, "信号层与骨架层是同一份数据（信号层被写成了 PATHS）"
    extra = sig_pairs - path_pairs
    assert len(extra) == 1 and tuple(sorted(("stutter", "comb"))) in extra, \
        (f"信号层相对骨架层应恰好多出 1 条（stutter → comb），实际 {sorted(extra)}。"
         f"多出来的变了说明连线关系变了，得重新想清楚")

    # **信号层不许自交。** serpentine 之所以读得成"一条链"，就因为它不交叉 ——
    # 一旦交叉，眼睛就跟丢了，这一层还不如不画。
    def _cross(p, q, r, s) -> bool:
        def orient(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        d1, d2 = orient(r, s, p), orient(r, s, q)
        d3, d4 = orient(p, q, r), orient(p, q, s)
        return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))

    segs_sig = [((node_x[na], node_y[na]), (node_x[nb], node_y[nb]))
                for na, nb in SIGNAL_PATH]
    n_cross = 0
    for i in range(len(segs_sig)):
        for j in range(i + 1, len(segs_sig)):
            if set(SIGNAL_PATH[i]) & set(SIGNAL_PATH[j]):
                continue                     # 相邻两条共用一个质点，不算交叉
            if _cross(*segs_sig[i], *segs_sig[j]):
                n_cross += 1
    assert n_cross == 0, f"信号层有 {n_cross} 处自交 —— 读不成一条链了"

    # ③ 检查器的阅读顺序 = 信号顺序
    flat = [mod for lane in ALL_LANES for mod in lane]
    assert flat == CHAIN, (
        f"ALL 模式展平后不是信号顺序：\n  {flat}\n  {CHAIN}\n"
        f"（「从左到右、从上到下」必须就是信号顺序，否则树和检查器说的是两件事）")
    assert SELECTED == CHAIN[1:5], \
        (f"MODULE 模式的候选集不是 CHAIN 的连续切片：{SELECTED}。"
         f"跳着挑会让'按 1/2/3/4'看到的模块在链上不连续，动线断掉")
    # 切片必须**连续**（下标逐个 +1）—— 光看"在 CHAIN 里"挡不住 [grain, comb, space] 这种跳选。
    idx_sel = [CHAIN.index(mod) for mod in SELECTED]
    assert idx_sel == list(range(idx_sel[0], idx_sel[0] + len(idx_sel))), \
        f"候选集在链上不连续：下标 {idx_sel}"

    # ④ 强调必须是真的：信号层**静止**的那一档也要亮过骨架。
    #    这条防的是"号称加了信号层，其实画得比骨架还淡"。
    #    **实测屏幕亮度**（PNG，树区采样、挖掉节点圆盘 r+46px，p99/max，0–255）：
    #        骨架 22/46 · 中柱 47/62 · 静止 125/128 · 通过（最暗相位）189/201 · 通过（峰）212/226
    #    下面这几条把那个关系钉住；改数字就报红，改完必须回去重量一遍。
    assert GRID_OP < TRUNK_OP < SIG_REST_LO < SIG_REST_HI < SIG_HOT_LO < SIG_HOT_HI, \
        (f"四层的亮度阶梯断了：骨架 {GRID_OP} / 中柱 {TRUNK_OP} / "
         f"静止 {SIG_REST_LO}→{SIG_REST_HI} / 通过 {SIG_HOT_LO}→{SIG_HOT_HI}")
    assert TRUNK_OP / GRID_OP >= 1.5, \
        f"中柱只有骨架的 {TRUNK_OP / GRID_OP:.2f} 倍重 —— 看不出哪条是主干"
    # 信号层**静止档的最暗处**也要明显压过结构层的最亮处（中柱）。这条卡的是
    # "结构 / 功能"两层的**下限**：信号再淡也得看得出是"另一层东西"。
    assert SIG_REST_LO / TRUNK_OP >= 1.5, \
        (f"信号（静止）上游端只有中柱的 {SIG_REST_LO / TRUNK_OP:.2f} 倍 —— "
         f"信号层和结构层糊在一起，两种质地也救不回来")
    assert SIG_REST_HI / GRID_OP >= 3.0, \
        f"信号（静止）只有骨架的 {SIG_REST_HI / GRID_OP:.1f} 倍 —— 层次拉不开"
    # **这条是"高亮"这件事本身**：通信号那条边，在**最暗的呼吸相位**下，
    # 也必须比静止那条**最亮处**还亮。做不到的话"高亮"就只是"亮了一点点"。
    assert SIG_HOT_LO * SIG_BREATH_MIN > SIG_REST_HI, \
        (f"高亮不够：通过态最暗 {SIG_HOT_LO * SIG_BREATH_MIN:.3f} ≤ "
         f"静止态最亮 {SIG_REST_HI} —— 两者会糊在一起，看不出哪条在通信号")
    assert SIG_HOT_HI / SIG_REST_HI >= 1.5, \
        f"通过态只比静止态亮 {SIG_HOT_HI / SIG_REST_HI:.2f} 倍 —— 差分太小"
    assert 0.0 < SIG_BREATH_MIN < 1.0, \
        f"呼吸最低点 {SIG_BREATH_MIN} 不在 (0,1) —— 要么完全不呼吸，要么会灭掉"
    assert SIG_W > 1.0, f"信号层线宽 {SIG_W} 不比骨架（1.0）粗"

    # ⑤ 从**真的画出来的 SVG** 里把两层量回来 —— 常量对不代表画对了。
    svg_flow = panel(geo, ctrls, "ALL", 1, .75)
    sig_el = re.findall(r'<line class="s"[^>]*>', svg_flow)
    grid_el = re.findall(r'<line class="g"[^>]*>', svg_flow)
    assert len(sig_el) == 9, f"SVG 里信号线 {len(sig_el)} 条，应为 9 条"
    assert len(grid_el) == len(PATHS), f"SVG 里骨架线 {len(grid_el)} 条，应为 {len(PATHS)} 条"
    # **质地**必须分得开：骨架是点线，信号是实线。
    assert all("stroke-dasharray" in el for el in grid_el), "骨架层里混进了实线"
    assert not any("stroke-dasharray" in el for el in sig_el), "信号层里混进了虚线"
    assert all('stroke="url(#sg' in el for el in sig_el), "信号层不是渐变描边"
    grads = re.findall(r'<linearGradient id="sg\d+"[^>]*>'
                       r'<stop offset="0" stop-color="[^"]*" stop-opacity="([\d.]+)"/>'
                       r'<stop offset="1" stop-color="[^"]*" stop-opacity="([\d.]+)"/>', svg_flow)
    assert len(grads) == 9, f"信号层的渐变 {len(grads)} 条，应为 9 条"
    for k, (lo, hi) in enumerate(grads):
        assert float(hi) > float(lo), f"渐变 sg{k} 没有方向（{lo} → {hi}）"
    # **两档必须真的都出现。** 演示用的 LIT 若让 9 条边全亮或全不亮，
    # "高亮"就无从对比 —— 那是空转。而且亮着的条数必须与 LIT 算出来的一致。
    # 注意这里量的是 `panel()` 的默认 `lit`（= LIT），所以期望值直接用 `n_hot(LIT)`。
    n_hot_drawn = sum(1 for lo, _hi in grads if float(lo) >= SIG_HOT_LO * SIG_BREATH_MIN - 1e-6)
    want_hot = n_hot(LIT)
    assert n_hot_drawn == want_hot, \
        (f"高亮的信号线 {n_hot_drawn} 条 ≠ 由 LIT 算出来的 {want_hot} 条 —— "
         f"高亮的判据和 LIT 对不上了（`is_hot()` 是不是被绕开了？）")
    assert 0 < want_hot < len(SIGNAL_PATH), \
        (f"演示用的 LIT 让 {want_hot}/{len(SIGNAL_PATH)} 条边亮着 —— "
         f"全亮或全不亮，高亮无从对比（空转）")
    # 每一档的**两端**都要真的落进那一档，否则会出现"上游静止、下游通过"的混搭。
    for lo, hi in grads:
        both_rest = float(hi) <= SIG_REST_HI + 1e-6
        both_hot = float(lo) >= SIG_HOT_LO * SIG_BREATH_MIN - 1e-6
        assert both_rest or both_hot, \
            f"有一条信号线的两端落在不同档上（上游 {lo} / 下游 {hi}）—— 渐变会看起来断掉"
    # **静止档不许跟着呼吸。** 这条单独盯着"两档"这件事：如果偷懒把两档都乘上 pulse，
    # 数值上完全合法（都在区间内、阶梯也没断），但"呼吸 = 活动"这层含义就没了 ——
    # 没信号的时候线还在脉动，等于告诉用户"这儿有东西在过"。
    # 量法：同一段代码只换 breath，静止档那几条边的不透明度必须**逐字节不变**。
    svg_b0 = panel(geo, ctrls, "ALL", 1, .0, lit=set())
    svg_b1 = panel(geo, ctrls, "ALL", 1, 1.0, lit=set())
    gr0 = re.findall(r'<linearGradient id="sg\d+"[^>]*>.*?</linearGradient>', svg_b0, re.S)
    gr1 = re.findall(r'<linearGradient id="sg\d+"[^>]*>.*?</linearGradient>', svg_b1, re.S)
    assert len(gr0) == len(gr1) == 9, f"无信号时的渐变条数不对：{len(gr0)} / {len(gr1)}"
    assert gr0 == gr1, \
        ("没有信号通过时，信号线居然跟着 breath 变了 —— 静止档必须完全不呼吸。"
         "呼吸是「这儿有东西在过」的信号，没信号就不该动")
    # 反过来：有信号时**必须**呼吸，否则两档白分了。
    # 只比 `sg*` 那几条渐变 —— 拿整张 SVG 比的话，检查器那边本来就有别的呼吸，
    # 断言会被别的东西满足（又一次"被上游先抓住 = 这条没被验过"）。
    gr_h0 = re.findall(r'<linearGradient id="sg\d+"[^>]*>.*?</linearGradient>',
                       panel(geo, ctrls, "ALL", 1, .0, lit=LIT), re.S)
    gr_h1 = re.findall(r'<linearGradient id="sg\d+"[^>]*>.*?</linearGradient>',
                       panel(geo, ctrls, "ALL", 1, 1.0, lit=LIT), re.S)
    assert len(gr_h0) == 9, f"有信号时的渐变条数不对：{len(gr_h0)}"
    n_breathing = sum(1 for x, y in zip(gr_h0, gr_h1) if x != y)
    assert n_breathing == want_hot, \
        (f"有信号时只有 {n_breathing}/{want_hot} 条边跟着呼吸 —— "
         f"通过档没有完整呼吸起来")
    # **渐变的方向必须与线本身一致。** 只查两个 stop 的数值挡不住"把 gradient 的
    # 两个端点对调"：数值一个没变，方向反了，肉眼看到的就是流向往上走。
    for k, (na, nb) in enumerate(SIGNAL_PATH):
        gm = re.search(rf'<linearGradient id="sg{k}"[^>]*x1="([\d.\-]+)" y1="([\d.\-]+)" '
                       rf'x2="([\d.\-]+)" y2="([\d.\-]+)"', svg_flow)
        assert gm, f"取不到 sg{k} 的渐变端点"
        lm = re.search(r'x1="([\d.\-]+)" y1="([\d.\-]+)"', sig_el[k])
        assert (gm.group(1), gm.group(2)) == (lm.group(1), lm.group(2)), \
            (f"信号线 {na} → {nb} 的渐变起点 ({gm.group(1)}, {gm.group(2)}) "
             f"与线自己的起点 ({lm.group(1)}, {lm.group(2)}) 不一致 —— 渐变画反了")
    # **每条线的起点必须离它的上游质点更近** —— 这条盯着"渐变画反了"：
    # 常量全对、渐变也有方向，但线是反着画的，于是流向朝上。横跨的那三条
    # y 相等、光看 y 判不出来，只能这样量。
    for (na, nb), el in zip(SIGNAL_PATH, sig_el):
        g = re.search(r'x1="([\d.\-]+)" y1="([\d.\-]+)" x2="([\d.\-]+)" y2="([\d.\-]+)"', el)
        assert g, f"信号线取不到端点：{el[:80]}"
        x1, y1 = float(g.group(1)), float(g.group(2))
        assert y1 <= float(g.group(4)) + 1e-6, \
            f"信号线 {na} → {nb} 的起点比终点低 —— 流向往上走了"
        d_up = math.hypot(x1 - node_x[na], y1 - node_y[na])
        d_dn = math.hypot(x1 - node_x[nb], y1 - node_y[nb])
        assert d_up < d_dn, \
            f"信号线 {na} → {nb} 的起点离 {nb} 更近（{d_up:.1f} vs {d_dn:.1f}）—— 渐变方向反了"

    # 7 · 底部没有 10 模块介绍：面板最后一个元素必须是参数行，不是清单
    assert "10 MODULE" not in a.upper(), "底部仍在介绍 10 个模块"

    m0 = metrics(REF_W, REF_H)
    pitches = [round(row_pitch(m0, col_rows(ctrls, [mod]), 1), 1) for mod in SELECTED]
    print(f"  自检通过 · 参数名 {len(names)} 个 · 开关 {n_sw} 个（已并入模块标题，不再单独占行）· "
          f"**面板上一个框都没有**\n"
          f"           列宽 1→4 档 {[round(w, 1) for w in widths]} · "
          f"轨道 {[round(t, 1) for t in tracks]} · "
          f"字号 标题/数值/名称 = {FS_TITLE:.0f}/{FS_VALUE:.0f}/{FS_NAME:.0f}（Apple macOS 字阶）\n"
          f"           行距逐列解 MODULE×4 {pitches} · "
          f"ALL 三列 {[round(row_pitch(m0, col_rows(ctrls, l), len(l)), 1) for l in ALL_LANES]}\n"
          f"           分组靠留白：组间 = 行距 × {SECTION_GAP_MULT} · "
          f"列间 {m0['col_gap']:.1f}px · 行内 {m0['gap']:.1f}px · 面板边距 {m0['pad']:.1f}px\n"
          f"           末行（* MIX 那一类）跨列对齐（量的是**文字基线**）· 呼吸峰值 {peaks}\n"
          f"           覆盖：Choice 选中分支（点亮 sweep 后 seg_on {base_on} → {lit_on}，"
          f"差分证明走到了）\n"
          f"           交互状态：{'/'.join(STATES)} 四态**只改颜色不改几何**（文字与矩形逐字节相同）· "
          f"行底 {HOVER_A:.2f}→{PRESS_A:.2f} · 聚焦环 {FOCUS_RING_W:.0f}px {ACCENT}（全工程唯一的彩色）\n"
          f"           动效：反馈 {MOTION_FAST}s / 低频 {MOTION_STD}s / **拖参数 {MOTION_DRAG}s（HIG 不加）** · "
          f"减弱动态效果 ×{REDUCE_MOTION_SCALE:.1f}\n"
          f"           动线：信号链 {' → '.join(CHAIN)}（**与 TraneEngine.cpp 逐项对账**）\n"
          f"                 树上 {len(SIGNAL_PATH)} 条信号线（实线 + 方向渐变）压在 {len(PATHS)} 条"
          f"骨架点线上 · 0 处自交 · 只向下 {n_horiz} 处同层横跨 · 相对骨架**恰好多 1 条**"
          f"（stutter → comb，那 22 条里没有）\n"
          f"                 高亮两档：静止 {SIG_REST_LO:.2f}→{SIG_REST_HI:.2f}（静态不呼吸）· "
          f"通过 {SIG_HOT_LO:.2f}→{SIG_HOT_HI:.2f}（×{SIG_BREATH_MIN:.2f} 呼吸）· "
          f"最暗通过 {SIG_HOT_LO * SIG_BREATH_MIN:.2f} > 最亮静止 {SIG_REST_HI:.2f} · "
          f"演示集 {n_hot(LIT)}/{len(SIGNAL_PATH)} 条在亮\n"
          f"                 检查器阅读顺序 = 信号顺序（ALL 三列 3+3+4）· MODULE 取连续切片（"
          f"{' / '.join(SELECTED)}）\n"
          f"           对比度全部 ≥ {CONTRAST_MIN}:1（WCAG AA 正文）· 最紧的一处 "
          f"{worst[0]:.2f}:1 —— {worst[1]}")


def states_html(geo, ctrls, version) -> tuple[str, int, int]:
    """交互状态接触表 —— **同一行**在四个状态下的样子 + 动效规格。

    只出 MODULE×1：列宽最大，那一行的变化最容易看清。
    四张用的是**同一段绘制代码**（只是 `state` 不同），所以这不是"示意稿"，
    就是插件将来会画出来的东西。
    """
    tgt = state_target(ctrls)
    cells = [
        ("idle", "01 · IDLE · 常态"),
        ("hover", f"02 · HOVER · 鼠标在这一行上 —— 行底 +{HOVER_A:.2f}，参数名 {A_MUTED:.2f} → {A_HOVER_NAME:.2f}"),
        ("press", f"03 · PRESS · 正在按 —— 行底 +{PRESS_A:.2f}（{PRESS_A / HOVER_A:.0f}×），参数名 → {A_TEXT:.2f}"),
        ("focus", f"04 · FOCUS · 键盘走到这一行 —— {FOCUS_RING_W:.0f}px 强调色环，留 {FOCUS_RING_GAP:.0f}px 空隙"),
    ]
    cards = "".join(
        f'<section><h2>{cap}</h2><div class="p">'
        f'{panel(geo, ctrls, "MODULE", 1, .75, state=st, target=tgt)}</div></section>'
        for st, cap in cells)

    spec = [
        ("悬停 / 按下的反馈", f"{MOTION_FAST:.2f} s", MOTION_EASE,
         "HIG · Motion：feedback motion 要 brief and precise"),
        ("模块开关 / 模式切换（低频）", f"{MOTION_STD:.2f} s", MOTION_EASE,
         "低频动作给一点过渡，帮人确认状态真的变了"),
        ("拖参数（高频）", f"{MOTION_DRAG:.2f} s", "—",
         "HIG：generally avoid adding motion to UI interactions that occur frequently"),
        ("打开「减弱动态效果」时", f"× {REDUCE_MOTION_SCALE:.1f}（全部归零）", "—",
         "HIG：make motion optional / let people cancel motion"),
    ]
    rows = "".join(f'<tr><td>{a}</td><td class="n">{b}</td><td class="n">{c}</td><td>{d}</td></tr>'
                   for a, b, c, d in spec)

    gap, pad = 44, 48
    w = pad * 2 + int(REF_W) * 2 + gap
    h = 340 + 2 * (int(REF_H) + 62) + 250
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE V{version} STATES</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;background:#050506;color:{INK};padding:44px {pad}px 70px;font-family:{UI}}}
h1{{font-size:17px;font-weight:600;letter-spacing:-0.01em}}
p{{margin-top:10px;max-width:1180px;font-size:11px;line-height:1.8;letter-spacing:-0.01em;color:{MUTED}}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:{gap}px;margin-top:40px;align-items:start}}
h2{{height:32px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{MUTED}}}
.p{{width:{int(REF_W)}px;height:{int(REF_H)}px;box-shadow:0 0 0 1px {HAIR}}}
.p svg{{display:block}}
h3{{margin-top:54px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{MUTED}}}
table{{margin-top:16px;border-collapse:collapse;font-size:11px;letter-spacing:-0.01em}}
th,td{{text-align:left;padding:10px 22px 10px 0;border-bottom:1px solid {HAIR};color:{MUTED}}}
th{{font-weight:500;color:{INK}}}
td.n{{font-family:{DATA};color:{INK};white-space:nowrap}}
</style></head><body>
<h1>TRÄNE · V{version} · INTERACTION STATES</h1>
<p>ONE ROW, FOUR STATES — SAME DRAWING CODE AS THE PLUGIN. THE HARD RULE: **STATE CHANGES COLOUR ONLY, NEVER GEOMETRY** —
every text coordinate and every track rectangle is byte-identical across all four states (asserted, and the assertion is
mutation-tested). THE ACCENT ({ACCENT}) IS THE ONLY COLOUR ON THIS PANEL AND MAY APPEAR **ONLY** IN THE FOCUS STATE.
TARGET ROW: {tgt}.</p>
<div class="grid">{cards}</div>
<h3>05 · MOTION SPEC · APPLE HIG · MOTION</h3>
<table><tr><th>动作</th><th>时长</th><th>曲线</th><th>依据</th></tr>{rows}</table>
</body></html>''', w, h


def flow_tree(geo, ctrls, layers, sc: float = 1.6, breath: float = .75,
              lit: set[str] | None = None) -> tuple[str, float, float]:
    """把世界树**裁出来**放大 —— 用同一段绘制代码，只把 viewBox 收到树的范围。

    这里不重画：`panel()` 照常画整张面板，然后只改外层 viewBox 把它裁到树上。
    所以这两张对照稿里的树，和插件里将来画出来的**是同一段代码的输出**。
    """
    w, h = REF_W * sc, REF_H * sc
    m = metrics(w, h)
    svg = panel(geo, ctrls, "ALL", 1, breath, w=w, h=h, layers=layers, lit=lit)
    bx, by, bw, bh = (30.0 * m["s"], 40.0 * m["s"], 332.0 * m["s"], 640.0 * m["s"])
    pad = 14.0 * m["s"]
    vx, vy, vw, vh = bx - pad, by - pad, bw + 2 * pad, bh + 2 * pad
    # **宽高属性也要一起换。** 只改 viewBox 的话，SVG 的视口还是整张面板那么大
    # （2304×1152），而 preserveAspectRatio 默认是 xMidYMid meet ——
    # 内容会被缩到能放下为止再**居中**，于是卡片里要么一片黑、要么三张叠在一起。
    # 第一版就是这么错的：三张稿子的节点全糊在一块儿，看着像树本身坏了。
    out = re.sub(r'<svg xmlns="[^"]*" width="[\d.]+" height="[\d.]+" viewBox="0 0 [\d.]+ [\d.]+">',
                 f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw:.1f}" height="{vh:.1f}" '
                 f'viewBox="{vx:.1f} {vy:.1f} {vw:.1f} {vh:.1f}">', svg, count=1)
    assert out != svg, "裁切没生效 —— 外层 svg 的宽高/viewBox 没被替换掉（正则对不上了？）"
    return out, vw, vh


def flow_html(geo, ctrls, version) -> tuple[str, int, int]:
    """**动线对照稿** —— 两张树并排，唯一的变量是「有没有信号在过」。

    小绪 2026-09-29 11:4x 定的调子：
      > 生命树的所有骨架全部保留，在有信号通过的时候直接高亮表示就可以了

    所以对照稿不再是"只骨架 / 骨架+信号 / 只信号"那种**选方案**的三张 ——
    方案已经定了（骨架一条不动 + 信号层叠上去）。现在要验的是**方案里的那个变量**：
    「有信号通过」到底看不看得出来。两张稿用**同一段绘制代码**，只差 `lit`：

      ① 静止态 —— `lit = ∅`，没有模块在响。九条信号线全部落在**静止档**（0.26 → 0.52），
         不呼吸。它回答的是"没信号的时候，这棵树长什么样"。
      ② 通过态 —— `lit = LIT`（链的前五级）。落在亮区里的那 4 条边抬到**通过档**
         （0.72 → 1.00）并跟着呼吸脉动；剩下 5 条仍在静止档。

    两张的差别**只有信号层那 4 条边**（骨架、节点、文字全部逐字节相同）——
    这就是"高亮"这件事本身，也是它可被验证的原因。
    """
    variants = [
        (set(), "01 · 静止态 · 没有信号通过",
         f"`lit = ∅` —— 没有任何模块在响。{len(SIGNAL_PATH)} 条信号线**全部落在静止档**"
         f"（{SIG_REST_LO:.2f} → {SIG_REST_HI:.2f}），静态不呼吸：呼吸 = 活动，"
         f"没信号就没活动。{len(PATHS)} 条骨架点线照常压在底下，一条不少。"),
        (None, "02 · 通过态 · 信号正在过这一段",
         f"`lit = {sorted(LIT)}`（信号链的前五级）。落在这段里的 **{n_hot(LIT)} 条边"
         f"抬到通过档**（{SIG_HOT_LO:.2f} → {SIG_HOT_HI:.2f}）并跟着呼吸脉动"
         f"（最低相位 ×{SIG_BREATH_MIN:.2f}）；剩下 {len(SIGNAL_PATH) - n_hot(LIT)} 条仍在静止档。"
         f"**通过档最暗处 {SIG_HOT_LO * SIG_BREATH_MIN:.2f} > 静止档最亮处 {SIG_REST_HI:.2f}** —— "
         f"这是硬断言，保证「高亮」是能测出来的差分，不是「亮一点点」。"),
    ]
    cards = []
    vw = vh = 0.0
    for lit, cap, note in variants:
        svg, vw, vh = flow_tree(geo, ctrls, ("grid", "signal"), lit=lit)
        cards.append(f'<section><h2>{cap}</h2><div class="p">{svg}</div>'
                     f'<p class="note">{note}</p></section>')
    cards = "".join(cards)

    node_y = {n["module"]: n["y"] for n in geo["nodes"]}
    rows = "".join(
        f'<tr><td class="n">{i + 1:02d}</td><td>{na.upper()}</td>'
        f'<td class="n">→</td><td>{nb.upper()}</td>'
        f'<td class="n">{node_y[na]:.1f}</td><td class="n">{node_y[nb]:.1f}</td>'
        f'<td class="n">{"—" if abs(node_y[nb] - node_y[na]) < 1e-6 else "+%.1f" % (node_y[nb] - node_y[na])}</td></tr>'
        for i, (na, nb) in enumerate(SIGNAL_PATH))

    lane_rows = "".join(
        f'<tr><td class="n">{i + 1}</td><td>{" → ".join(mod.upper() for mod in lane)}</td>'
        f'<td class="n">{col_rows(ctrls, lane)}</td></tr>'
        for i, lane in enumerate(ALL_LANES))

    gap, pad = 40, 48
    w = pad * 2 + 3 * (int(vw) + 26) + 2 * gap
    h = 300 + int(vh) + 620
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE V{version} FLOW</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;background:#050506;color:{INK};padding:44px {pad}px 70px;font-family:{UI}}}
h1{{font-size:17px;font-weight:600;letter-spacing:-0.01em}}
p{{margin-top:10px;max-width:1180px;font-size:11px;line-height:1.8;letter-spacing:-0.01em;color:{MUTED}}}
.grid{{display:flex;gap:{gap}px;margin-top:36px;align-items:flex-start}}
h2{{height:30px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{INK}}}
.p{{width:{int(vw) + 26}px;height:{int(vh) + 26}px;padding:13px;box-shadow:0 0 0 1px {HAIR}}}
.p svg{{display:block}}
p.note{{margin-top:12px;width:{int(vw) + 26}px;font-size:10px;line-height:1.7}}
h3{{margin-top:52px;font-size:11px;font-weight:500;letter-spacing:-0.01em;color:{INK}}}
table{{margin-top:14px;border-collapse:collapse;font-size:11px;letter-spacing:-0.01em}}
th,td{{text-align:left;padding:8px 20px 8px 0;border-bottom:1px solid {HAIR};color:{MUTED}}}
th{{font-weight:500;color:{INK}}}
td.n{{font-family:{DATA};color:{INK};white-space:nowrap}}
</style></head><body>
<h1>TRÄNE · V{version} · 动线 / SIGNAL FLOW</h1>
<p>THE TREE'S VERTICAL AXIS **IS** THE SIGNAL AXIS. `TraneEngine.cpp::process()` runs
{' → '.join(CHAIN)} — and the ten sephiroth are already laid out with a
monotonically increasing y in exactly that order (measured, asserted). What was missing is the
<b>lines</b>: `PATHS` draws the 22 standard Tree-of-Life connections — a generic mesh that says
"this is a tree" but says nothing about flow. The signal layer is a <b>separate</b> layer of
{len(SIGNAL_PATH)} edges, because `STUTTER → COMB` is not among those 22 (8 of 9 signal edges
happen to coincide; the ninth does not). Dotted = structure, solid + directional fade = function.
The signal edges come in <b>two tiers</b>: <b>rest</b> ({SIG_REST_LO:.2f} → {SIG_REST_HI:.2f}, static,
never breathes) and <b>hot</b> ({SIG_HOT_LO:.2f} → {SIG_HOT_HI:.2f}, breathing with the module glow,
lowest phase ×{SIG_BREATH_MIN:.2f}). The hard assertion is
<b>{SIG_HOT_LO:.2f} × {SIG_BREATH_MIN:.2f} = {SIG_HOT_LO * SIG_BREATH_MIN:.2f} &gt; {SIG_REST_HI:.2f}</b> —
a lit edge at its dimmest must still outshine an idle edge at its brightest.</p>
<div class="grid">{cards}</div>
<h3>THE {len(SIGNAL_PATH)} SIGNAL EDGES · y MUST NEVER GO BACK UP</h3>
<table><tr><th>#</th><th>FROM</th><th></th><th>TO</th><th>y from</th><th>y to</th><th>Δy</th></tr>{rows}</table>
<h3>READING ORDER = SIGNAL ORDER · ALL MODE</h3>
<table><tr><th>列</th><th>模块（自上而下）</th><th>行数</th></tr>{lane_rows}</table>
</body></html>''', w, h


def strip_html(ctrls: list[dict], version: str) -> tuple[str, int, int]:
    """呼吸发光单独出一张放大版 —— 接触表里它太小，看不出四个相位到底有没有差。"""
    strip, sw, defs = breath_strip(ctrls, 40, 96)
    w, h = int(sw) + 80, 360
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE V{version} BREATH</title><style>
html,body{{margin:0;width:{w}px;height:{h}px;background:{BG};overflow:hidden}}
</style></head><body>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><defs>{"".join(defs)}</defs>
<rect width="{w}" height="{h}" fill="{BG}"/>
<text x="40" y="48" font-family="{UI}" font-size="17" font-weight="600"
 letter-spacing="{TRACK_HEAD * 17:.2f}" fill="{INK}">BREATHING GLOW</text>
<text x="40" y="70" font-family="{UI}" font-size="9.5" fill="{MUTED}">FOUR PHASES OF THE SAME NODE · SAME DRAWING CODE AS THE PLUGIN</text>
{strip}</svg></body></html>''', w, h


def render(html: str, w: int, h: int, out: pathlib.Path, scale: float) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_ui23_"))
    page = tmp / "p.html"
    page.write_text(html, encoding="utf-8")
    subprocess.run([find_chrome(), "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    f"--force-device-scale-factor={scale}", f"--screenshot={out}",
                    f"--window-size={w},{h}", "--virtual-time-budget=8000", page.as_uri()],
                   capture_output=True, text=True, timeout=180)
    assert out.is_file(), "Chrome did not produce the preview"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.30")
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--outdir", default=str(ROOT.parent / "outputs"))
    ap.add_argument("--check-only", action="store_true",
                    help="只跑自检，不出图（给 run_tests.sh 用 —— 出图要开 headless Chrome，十几秒）")
    args = ap.parse_args()

    geo, ctrls = read_geometry(), read_controls()
    assert len(ctrls) == 48, "kControls is not 48 entries"
    print(f"自检 v{args.version}（十一条逐条对账）")
    self_check(geo, ctrls)
    if args.check_only:
        return 0
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    sheet, w, h = sheet_html(geo, ctrls, args.version)
    dest = outdir / f"Trane_UI_v{args.version}.png"
    render(sheet, w, h, dest, 1)
    print(f"→ {dest}")

    html, bw, bh = strip_html(ctrls, args.version)
    dest = outdir / f"Trane_UI_v{args.version}_breath.png"
    render(html, bw, bh, dest, args.scale)
    print(f"→ {dest}")

    st_html, sw, sh = states_html(geo, ctrls, args.version)
    dest = outdir / f"Trane_UI_v{args.version}_states.png"
    render(st_html, sw, sh, dest, 1)
    print(f"→ {dest}")

    fl_html, fw, fh = flow_html(geo, ctrls, args.version)
    dest = outdir / f"Trane_UI_v{args.version}_flow.png"
    render(fl_html, fw, fh, dest, 1.5)
    print(f"→ {dest}")

    for md, n, _cap in [("ALL", 1, ""), ("MODULE", 1, ""), ("MODULE", 2, ""),
                        ("MODULE", 3, ""), ("MODULE", 4, "")]:
        tag = f"{md.lower()}{'' if md == 'ALL' else n}"
        dest = outdir / f"Trane_UI_v{args.version}_{tag}.png"
        render(single_html(geo, ctrls, md, n, .75, args.version),
               int(REF_W), int(REF_H), dest, args.scale)
        print(f"→ {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
