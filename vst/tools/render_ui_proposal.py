#!/usr/bin/env python3
"""⚠️ 历史稿（v0.16 → v0.17 那版），**已过期，别拿它当面板现在的样子**。
当前实现在 `plugin/TranePanel.cpp`，要看实况用 `panel_probe --out`。
留着它只为记录当时的设计 —— 环形文字 / 生命之树 v0.33 已删。

生成 Träne v0.17 UI 设计稿（HTML）—— 生命之树 · 48 控件全上屏 · 环形文字。

## v0.16 → v0.17：把漏掉的 12 个控件补回来

v0.16 定稿之后去对了一遍 `PluginProcessor.cpp::createLayout()`，发现
**设计稿只画了 36 个控件，插件里实际声明了 48 个**（+1 个 JUCE 自动加的 Bypass）。
漏的 12 个：

    grain_on  stutter_on  comb_on  tape_on  sweep_on  delay_on   ← 6 个模块开关
    grain_position  grain_spray  delay_pingpong                  ← 3 个旋钮
    ruin_mode  sweep_mode                                        ← 2 个档位
    （freeze 的 BoolParam 之前用红环表示，算有）

这是"图与实必须一致"这条规矩下最不能容忍的错 —— 少了 12 个控件，
按这张稿子做出来的界面就没法用。所以这一版**以 `createLayout()` 为唯一依据重排**。

### 怎么塞得下：开关搬到圆的边框上

48 个控件平摊到 10 个圆，最挤的 GRAIN 有 9 个（1 开关 + 8 旋钮）。
环位最多只能舒服地放 8 个，9 个就压了。所以：

  · **7 个模块开关不上环，改成圆的边框** —— 关 = 淡黑细环，开 = 强调色红环。
    点圆心区（模块名）切换。这不只是省地方：生命之树本来就是"光从 Keter
    一级级流到 Malkuth"，**开一个亮一个，整棵树逐级点亮**，隐喻和交互是同一件事。
  · freeze 的红环因此不再是特例，而是这条规则本身。
  · 环位只剩 41 个真正的旋钮 / 档位（`MINI` 表）。

边框亮不亮，取决于"这个模块当前是否真的参与信号"：

    有 on 开关的 7 个 → 看那个开关
    RUIN              → ruin_mode > 0.02（mode=0 就是纯干声，等于没开）
    SPACE             → space_mix > 0.02
    OUT               → 恒亮（它是输出）

**注意：`createLayout()` 里 6 个 `_on` 默认全是 false，`freeze` 也是 false。**
所以真正的初始状态是「只有 SPACE 和 OUT 亮」。本稿为了让你看清开 / 关两种
边框，演示状态设成 **FREEZE 与 GRAIN 已开**（legend 里也标了）。

### 档位参数怎么上环

`sweep_mode` 是 `AudioParameterChoice`（LP / BP / HP），也占一个环位：
**辐条长度 = 档位序号归一化**（0 / 0.5 / 1.0），**值直接写档位名**。
`ruin_mode` 是 0–1 的连续 morph（0 = Clear → 1 = Ruin），当普通旋钮处理。

## 环形文字的三条几何规则（推出来的，不是试出来的）

**规则一：方向按段选，文字上方向 = 径向朝外 或 径向朝内。**

SVG `textPath` 把字符的"上方向"定在**路径行进方向的左手法线**上。在屏幕坐标
（y 向下）里，沿 +θ 方向走一圈，左手法线恒为**径向朝外**；沿 −θ 方向走，
恒为**径向朝内**。两种朝向的倾斜角恰好差 180°，所以每段取绝对值小的那个 ——
**最大倾斜恒 ≤ 90°，永远不会出现倒立**（印章下半圈的字是倒的，我们避开了）。

**规则二：下半圆的路径半径要加半个字号。**

朝外时文字长在基线**外侧**（带 = [r − 降部, r + 帽高]），朝内时长在**内侧**
（带 = [r − 帽高, r + 降部]）。要让两半落在同一条半径带里，朝内的路径半径
必须加大：`r_in = r_out + (帽高 − 降部)/2 ≈ r_out + 0.5 × 字号`。

**规则三：段与段之间的空隙按"弧长"给，不按角度。**

固定角度的话，n 一变空隙就跟着变；固定弧长（`GAP_PX = 4`，按值圈半径折算）
才能让每一段的可用弧长都算得出来。n=8 时值圈弧长 26.2px，
最长的值 "120ms" 在 IBM Plex Mono 7.5px 下约 22.1px —— 放得下。

## 半径预算（从圆心往外）

    0 – 36.9      圆心区：模块名（点它切换开关）
    36.9 – 43.9   值圈   （基线 38.5，字号 7.5，IBM Plex Mono）
    47.5 – 54.0   名圈   （基线 49.0，字号 7.0，Inter Tight 大写 + 字距）
    56.4          内衬   （贴着圆边界的一条细线，让圆像筒不像线）
    58            圆边界 —— 关 = 淡黑 w1.7，开 = 强调色 w2.2
    58 – 78       辐条 + 标尺圆（辐条长度 = 参数值）

比 v0.16 整体外推了一档（值圈 35.5→38.5、名圈 46.0→49.0），
因为 n 从 6 涨到 8，同一段角覆盖的弧长必须补回来。

用法:
    python vst/tools/render_ui_proposal.py
输出:
    outputs/Trane_UI_proposal_v0.17.html   （完整稿，含说明）
    outputs/_panel_bare.html               （纯面板，供截图）
"""
from __future__ import annotations

import math

# ================================================================ 面板尺寸
# 半径先定，其余全部由原图的两条比例反推：
#     r / 柱距 = 0.341        r / (Keter→Malkuth) = 0.074
RING_R = 58.0                     # 圆的半径 —— 原图里十个圆一样大
COL_SPACING = RING_R / 0.341      # 170.09 —— 原图 189.5 / 64.7 的比值
TREE_H = RING_R / 0.0740          # 783.78 —— Keter 到 Malkuth 的距离

SPOKE_BASE = 3.0                  # 辐条起点离圆边界多远
SPOKE_SPAN = 15.0                 # 辐条最长能伸多远（= 值 1.0 时）
SCALE_R = RING_R + SPOKE_BASE + SPOKE_SPAN + 2.0   # 标尺圆半径，也是树的包围半径
PAD = 24.0                        # 面板四周留白

TREE_TOP = PAD + SCALE_R
TREE_Y0 = TREE_TOP                                    # Keter 的圆心 y
PANEL_W = round(2 * (COL_SPACING + SCALE_R + PAD))
PANEL_H = round(TREE_Y0 + TREE_H + SCALE_R + PAD)

COL_X = {"L": PANEL_W / 2 - COL_SPACING,
         "M": PANEL_W / 2,
         "R": PANEL_W / 2 + COL_SPACING}

# ================================================================ 环形文字
# 小绪的原话：「我想要的是环形文字设计，每一个参数的文字就在当前参数刻度下」。
#
# 两圈，都沿弧。**名圈在外、值圈在内** —— 理由不是审美，是读法：
# 刻度在外，所以由外往内读正好是"名字 值"（SIZE 120ms）。
# 反过来会读成"120ms SIZE"，参数名反而成了补注。参数名是识别控件用的，
# 按"功能第一"这条规矩，它必须是先被读到的那一个。
NAME_R, NAME_FS = 49.0, 7.0
VAL_R, VAL_FS = 38.5, 7.5
GAP_PX = 4.0                      # 段间空隙的**弧长**（按值圈半径折算成角度）
BEZEL_R = RING_R - 1.6            # 贴着圆边界的内衬线，让圆像筒不像线

# 圆心区 —— 只有模块名，**正中心**，点它切换模块开关。
# 小绪看过带准星的稿子之后说：「现在这个准星好丑啊，算了不要准星了，
# 我要文字在最中心就好了」。所以准星整个删掉（见 crosshair() 的空壳注释）。
MOD_DY = 0.0                      # 模块名中心相对圆心 —— 0 = 正中
MOD_FS = 12.5

# ================================================================ 十个质点
# 纵向比例 = 原图的八等分。Tiferet 在 Chesed/Gevurah 下方、Yesod 在 Netzach/Hod 下方。
#   (键, 柱, 纵向比例, 模块, 中文名, 对应质点)
SEPHIRA = [
    ("keter",    "M", 0.000, "freeze",  "角冠",   "Keter 王冠"),
    ("chokhmah", "R", 0.125, "grain",   "星尘",   "Chokhmah 智慧"),
    ("binah",    "L", 0.125, "stutter", "尖桩",   "Binah 理解"),
    ("chesed",   "R", 0.375, "comb",    "肋骨",   "Chesed 慈悲"),
    ("gevurah",  "L", 0.375, "tape",    "衔尾蛇", "Gevurah 严厉"),
    ("tiferet",  "M", 0.500, "ruin",    "倒十字", "Tiferet 美"),
    ("netzach",  "R", 0.625, "sweep",   "全视之眼", "Netzach 胜利"),
    ("hod",      "L", 0.625, "delay",   "蛇串",   "Hod 荣耀"),
    ("yesod",    "M", 0.750, "space",   "倒五角星", "Yesod 基础"),
    ("malkuth",  "M", 1.000, "out",     "利维坦十字", "Malkuth 王国"),
]

# 22 条路径 —— 生命之树的标准连线，一条不多一条不少
PATHS = [
    ("keter", "chokhmah"), ("keter", "binah"), ("keter", "tiferet"),
    ("chokhmah", "binah"), ("chokhmah", "tiferet"), ("chokhmah", "chesed"),
    ("binah", "tiferet"), ("binah", "gevurah"),
    ("chesed", "gevurah"), ("chesed", "tiferet"), ("chesed", "netzach"),
    ("gevurah", "tiferet"), ("gevurah", "hod"),
    ("tiferet", "netzach"), ("tiferet", "hod"), ("tiferet", "yesod"),
    ("netzach", "hod"), ("netzach", "yesod"), ("netzach", "malkuth"),
    ("hod", "yesod"), ("hod", "malkuth"),
    ("yesod", "malkuth"),
]


def sph_xy(key: str):
    for k, col, ratio, *_ in SEPHIRA:
        if k == key:
            return COL_X[col], TREE_Y0 + ratio * TREE_H
    raise KeyError(key)


# ================================================================ 参数
# **逐条抄自 `PluginProcessor.cpp::createLayout()`（第 92–210 行），
# 一个不多一个不少。48 个。** 改这里之前先回去读那个函数。
#
# 名字与参数 ID 后缀一致，方便对照。默认值 = createLayout() 里给的默认值。
P = {
    # ---- CAPTURE / FREEZE ----
    "loopMs": 250.0, "seamMs": 10.0,
    # ---- GRAIN ----
    "grainSize": 120.0, "grainDensity": 12.0, "grainPosition": 0.5,
    "grainSpray": 0.15, "grainRate": 1.0, "grainSpread": 0.6,
    "grainReverse": 0.25, "grainMix": 1.0,
    # ---- RUIN ----
    "ruinMode": 0.0, "ruinDrive": 0.35, "ruinFold": 0.0,
    "ruinCrush": 0.0, "ruinRing": 0.0,
    # ---- STUTTER ----
    "stutterSize": 90.0, "stutterRate": 4.0, "stutterJump": 0.35, "stutterMix": 1.0,
    # ---- COMB ----
    "combTune": 220.0, "combFeedback": 0.6, "combMix": 0.5,
    # ---- TAPE ----
    "tapeSpeed": 1.0, "tapeWobble": 0.12, "tapeMix": 1.0,
    # ---- SWEEP ----
    "sweepRate": 0.8, "sweepDepth": 0.4, "sweepCenter": 1200.0,
    "sweepReso": 0.3, "sweepMode": 0.0,
    # ---- DELAY ----
    "delayTime": 375.0, "delayFeedback": 0.45, "delayDamp": 0.35,
    "delayPingPong": 0.0, "delayMix": 0.35,
    # ---- HUGE SPACE ----
    "spaceMix": 0.55, "spaceSize": 0.7, "spaceTail": 0.8,
    "spaceDamp": 0.4, "spaceDiffuse": 0.7,
    # ---- OUT ----
    "output": 0.0,
}

# 归一化范围：(lo, hi, skew)。skew = 1.0 表示线性。
# 逐条抄自 createLayout() 的 `NR(lo, hi, interval, skew)`（interval 不影响 0–1 映射）。
RANGE = {
    "loopMs": (20.0, 2000.0, 0.3),
    "seamMs": (0.0, 40.0, 1.0),
    "grainSize": (5.0, 500.0, 0.4),
    "grainDensity": (0.5, 100.0, 0.4),
    "grainRate": (0.25, 4.0, 0.4),
    "stutterSize": (5.0, 500.0, 0.4),
    "stutterRate": (0.25, 30.0, 0.4),
    "combTune": (20.0, 4000.0, 0.35),
    "combFeedback": (0.0, 0.95, 1.0),
    "tapeSpeed": (0.0, 2.0, 1.0),
    "sweepRate": (0.01, 20.0, 0.35),
    "sweepCenter": (60.0, 12000.0, 0.4),
    "delayTime": (20.0, 2000.0, 0.4),
    "delayFeedback": (0.0, 0.92, 1.0),
    "output": (-24.0, 12.0, 1.0),
}

# 7 个模块开关（BoolParam）。**它们不上环，走圆的边框。**
# 值 = 演示稿里是否设为"开"。真实默认全是 false（见文件头）。
DEMO = {"freeze": True, "grain": True}
BOOL_PARAMS = {
    "freeze": "freeze", "grain": "grainOn", "stutter": "stutterOn",
    "comb": "combOn", "tape": "tapeOn", "sweep": "sweepOn", "delay": "delayOn",
}

SWEEP_MODES = ("LP", "BP", "HP")


def fmt_ms(v: float) -> str:
    return f"{v:.0f}ms" if v >= 10 else f"{v:.1f}ms"


def nrm(v: float, lo: float, hi: float, skew: float = 1.0) -> float:
    """复刻 JUCE `NormalisableRange::convertTo0to1`。

    设计稿上辐条的长度必须**等于**宿主里旋钮的真实位置。写死一个"看起来合适"
    的百分比，等于图上说 1.20k 在 10% 处、实际在 Live 里跑到 56% —— 图与实不符，
    正是这个项目最忌讳的错。

    **这个函数之前是错的，已按源码修正。** v0.14 一直写的是 `p ** (1/skew)`，
    而 JUCE 的源码（`juce_NormalisableRange.h:147`）是：

        auto proportion = clampTo0To1 ((v - start) / (end - start));
        if (! symmetricSkew)
            return std::pow (proportion, skew);        // ← 是 skew，不是 1/skew

    插件里的参数全部走四参构造 `NR(start, end, interval, skew)`，symmetricSkew
    默认 false，所以就是这一支。写反的后果很具体：`grainSize = 120ms`
    （范围 5–500，skew 0.4）本该在 55.8% 处，错公式给出 2.6% —— 辐条短到看不见。
    """
    p = (v - lo) / (hi - lo)
    p = max(0.0, min(1.0, p))
    return p if skew == 1.0 else p ** skew


def pos(key: str) -> float:
    v = P[key]
    if key in RANGE:
        lo, hi, sk = RANGE[key]
        return nrm(v, lo, hi, sk)
    return max(0.0, min(1.0, v))


# ================================================================ 环位内容
# 41 个环位 = 48 个参数 − 7 个模块开关。
# (短名, 显示值, 归一化位置)。**不写死百分比** —— 全部走 nrm()。
# 短名 ↔ 宿主显示名的对照见 legend「简写对照」。
MINI = {
    "freeze": [("loop", fmt_ms(P["loopMs"]), pos("loopMs")),
               ("seam", fmt_ms(P["seamMs"]), pos("seamMs"))],
    "grain": [("size", fmt_ms(P["grainSize"]), pos("grainSize")),
              ("dens", f'{P["grainDensity"]:.0f}', pos("grainDensity")),
              ("pos", f'{P["grainPosition"]:.2f}', pos("grainPosition")),
              ("spry", f'{P["grainSpray"]:.2f}', pos("grainSpray")),
              ("rate", f'{P["grainRate"]:.2f}', pos("grainRate")),
              ("sprd", f'{P["grainSpread"]:.2f}', pos("grainSpread")),
              ("rev", f'{P["grainReverse"]:.2f}', pos("grainReverse")),
              ("mix", f'{P["grainMix"]:.2f}', pos("grainMix"))],
    "ruin": [("mode", f'{P["ruinMode"]:.2f}', pos("ruinMode")),
             ("drive", f'{P["ruinDrive"]:.2f}', pos("ruinDrive")),
             ("fold", f'{P["ruinFold"]:.2f}', pos("ruinFold")),
             ("crush", f'{P["ruinCrush"]:.2f}', pos("ruinCrush")),
             ("ring", f'{P["ruinRing"]:.2f}', pos("ruinRing"))],
    "stutter": [("size", fmt_ms(P["stutterSize"]), pos("stutterSize")),
                ("rate", f'{P["stutterRate"]:.1f}', pos("stutterRate")),
                ("jump", f'{P["stutterJump"]:.2f}', pos("stutterJump")),
                ("mix", f'{P["stutterMix"]:.2f}', pos("stutterMix"))],
    "comb": [("tune", f'{P["combTune"]:.0f}', pos("combTune")),
             ("fb", f'{P["combFeedback"]:.2f}', pos("combFeedback")),
             ("mix", f'{P["combMix"]:.2f}', pos("combMix"))],
    "tape": [("speed", f'{P["tapeSpeed"]:.2f}', pos("tapeSpeed")),
             ("wob", f'{P["tapeWobble"]:.2f}', pos("tapeWobble")),
             ("mix", f'{P["tapeMix"]:.2f}', pos("tapeMix"))],
    "sweep": [("rate", f'{P["sweepRate"]:.2f}', pos("sweepRate")),
              ("depth", f'{P["sweepDepth"]:.2f}', pos("sweepDepth")),
              ("cent", f'{P["sweepCenter"] / 1000:.1f}k', pos("sweepCenter")),
              ("reso", f'{P["sweepReso"]:.2f}', pos("sweepReso")),
              # Choice：辐条长度 = 档位序号归一化，值直接写档位名
              ("mode", SWEEP_MODES[int(P["sweepMode"])], pos("sweepMode") / 2.0)],
    "delay": [("time", fmt_ms(P["delayTime"]), pos("delayTime")),
              ("fb", f'{P["delayFeedback"]:.2f}', pos("delayFeedback")),
              ("damp", f'{P["delayDamp"]:.2f}', pos("delayDamp")),
              ("ping", f'{P["delayPingPong"]:.2f}', pos("delayPingPong")),
              ("mix", f'{P["delayMix"]:.2f}', pos("delayMix"))],
    "space": [("size", f'{P["spaceSize"]:.2f}', pos("spaceSize")),
              ("tail", f'{P["spaceTail"]:.2f}', pos("spaceTail")),
              ("damp", f'{P["spaceDamp"]:.2f}', pos("spaceDamp")),
              ("diff", f'{P["spaceDiffuse"]:.2f}', pos("spaceDiffuse")),
              ("mix", f'{P["spaceMix"]:.2f}', pos("spaceMix"))],
    "out": [("level", f'{P["output"]:+.1f}dB', pos("output"))],
}

# 模块名。**不写插件名** —— 小绪明确要求过。
TITLE = {
    "freeze": "FREEZE", "grain": "GRAIN", "stutter": "STUTTER", "comb": "COMB",
    "tape": "TAPE", "ruin": "RUIN", "sweep": "SWEEP", "delay": "DELAY",
    "space": "SPACE", "out": "OUT",
}

# 边框亮不亮 = "这个模块当前是否真的参与信号"。**由实际值算出，不是手填。**
# 有 on 开关的看开关（演示稿里 FREEZE / GRAIN 打开）；RUIN 看 mode（mode=0 是纯干声）；
# SPACE 看 mix；OUT 恒亮。
ON = {
    "freeze": DEMO.get("freeze", False),
    "grain": DEMO.get("grain", False),
    "stutter": DEMO.get("stutter", False),
    "comb": DEMO.get("comb", False),
    "tape": DEMO.get("tape", False),
    "sweep": DEMO.get("sweep", False),
    "delay": DEMO.get("delay", False),
    "ruin": P["ruinMode"] > 0.02,
    "space": P["spaceMix"] > 0.02,
    "out": True,
}

# ================================================================ 段与朝向
def orient(theta: float):
    """给一个角度，返回 (文字是否朝外, 倾斜角)。

    朝外 = 文字上方向是径向朝外，对应路径沿 +θ 方向走；
    朝内 = 上方向径向朝内，路径沿 −θ 方向走。

    推导（屏幕坐标，y 向下）：
      · 沿 +θ 走时方向向量 = (−sinθ, cosθ)，其左手法线 = (cosθ, sinθ) = 径向朝外；
      · 把"正立"的上方向 (0,−1) 顺时针转 φ 得到 (sinφ, −cosφ)。令其等于上方向，
        就解出 φ。朝外 φ = atan2(cosθ, −sinθ)；朝内 φ = atan2(−cosθ, sinθ)。
    两者恰好差 180°，所以**永远能选到一个 |φ| ≤ 90° 的** —— 这就是
    "环形文字永远不会倒立、最多竖起来"的证明。
    """
    po = math.atan2(math.cos(theta), -math.sin(theta))
    pi_ = math.atan2(-math.cos(theta), math.sin(theta))
    return (True, po) if abs(po) <= abs(pi_) else (False, pi_)


def best_rot(n: int, step: float = 0.25) -> float:
    """给 n 个参数挑一个旋转量，使**最大倾斜角**最小。

    段中点默认在 `-90 + 180/n × (2i+1)`。n=2 / n=6 / n=10 会正好把段摆在
    3 点 / 9 点（倾斜 90°），转一下就没了。平手时取离 0 最近的旋转量，
    保证结果唯一、可复现。
    """
    if n <= 1:
        return 0.0
    base = [-90.0 + (180.0 / n) * (2 * i + 1) for i in range(n)]
    best_key, best_rot = None, 0.0
    j = 0
    while j * step < 360.0:
        rot = j * step
        t = max(abs(math.degrees(orient(math.radians(c + rot))[1])) for c in base)
        key = (round(t, 4), abs(((rot + 180.0) % 360.0) - 180.0))
        if best_key is None or key < best_key:
            best_key, best_rot = key, rot
        j += 1
    return best_rot


_ROT = {}


def rot_of(mod: str) -> float:
    if mod not in _ROT:
        _ROT[mod] = best_rot(len(MINI[mod]))
    return _ROT[mod]


def seg_angles(n: int, rot: float = 0.0):
    """把整圈切成 n 段，返回每段的 (起点角, 终点角, 中点角)。起点在 12 点方向。

    角度是屏幕角：0° = 3 点，+90° = 6 点（y 向下，所以角度增大 = 视觉顺时针）。

    **空隙按弧长给**（`GAP_PX` 折算到值圈半径），不按固定角度 —— 固定角度的话
    n 一变空隙就跟着变，可用弧长算不出来。固定弧长才能让每一段都算得清楚。

    只有 1 个参数时，段心在正 12 点、弧从 −260° 走到 +80°（340°）——
    SVG 的 A 命令画不出整圆（起终点重合），所以留 20° 的口子；文字只占
    弧的中间那一小截，看不出口子在哪。
    """
    if n <= 1:
        sp = math.radians(170.0)
        return [(-math.pi / 2 - sp, -math.pi / 2 + sp, -math.pi / 2)]
    gap = GAP_PX / VAL_R
    seg = (6.2832 - n * gap) / n
    out, a = [], -math.pi / 2 + gap / 2 + math.radians(rot)
    for _ in range(n):
        out.append((a, a + seg, a + seg / 2))
        a += seg + gap
    return out


def arc_d(cx: float, cy: float, r: float,
          a0: float, a1: float, cw: bool) -> str:
    """一段圆弧的 path d。cw=True 走 +θ（视觉顺时针），False 走 −θ。"""
    x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    large = 1 if abs(a1 - a0) > math.pi else 0
    return (f"M {x0:.2f} {y0:.2f} A {r:.2f} {r:.2f} 0 {large} "
            f"{1 if cw else 0} {x1:.2f} {y1:.2f}")


def spoke(cx: float, cy: float, a: float, v: float) -> str:
    """一条辐条 —— **长度就是值**。

    为什么用辐条：弧读的是角度，辐条读的是长度。长度更直观（不用在脑子里
    比角度），而且整圈长短不一的辐条，配上外面那圈极淡的标尺圆，像日晷。
    """
    v = max(0.0, min(1.0, v))
    r0 = RING_R + SPOKE_BASE
    r1 = r0 + 2.0 + SPOKE_SPAN * v
    ca, sa = math.cos(a), math.sin(a)
    o = [line(cx + ca * r0, cy + sa * r0, cx + ca * r1, cy + sa * r1,
              w=1.9, color="var(--ink)", op=0.90)]
    if v > 0.02:
        o.append(dot(cx + ca * r1, cy + sa * r1, 1.25, color="var(--ink)", op=0.90))
    return "".join(o)


# ================================================================ 绘图原语
# 全部精确。v0.14 一开始给线条加"低频手抖"想做出手工感，小绪判断为"太劣质" ——
# 歪的圆加抖的线不是手作，是没对齐。手工感交给排印与构图。

def line(x0: float, y0: float, x1: float, y1: float, w: float = 1.0,
         color: str = "var(--ink)", op: float = 1.0) -> str:
    return (f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
            f'stroke="{color}" stroke-width="{w:.2f}" opacity="{op:.2f}" '
            f'stroke-linecap="round"/>')


def circle(cx: float, cy: float, r: float, w: float = 1.0,
           color: str = "var(--ink)", op: float = 1.0,
           fill: str = "none") -> str:
    return (f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" '
            f'stroke="{color}" stroke-width="{w:.2f}" opacity="{op:.2f}"/>')


def dot(x: float, y: float, r: float, color: str = "var(--ink)",
        op: float = 1.0) -> str:
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" '
            f'fill="{color}" opacity="{op:.2f}"/>')


# ================================================================ 圆与辐条
def node_art(col: str, ratio: float, mod: str) -> str:
    """一个质点的全部图形：圆（= 开关）+ 内衬 + 标尺圆 + 辐条。

    **圆的边框就是模块开关。** 关 = 淡黑细环，开 = 强调色红环（w 2.2）。
    点圆心区切换。理由见文件头"怎么塞得下"。

    **段界的短刺删掉了**（v0.15 有）。文字沿弧占满自己那一段，段与段之间的
    空隙已经把边界说清楚，再画刺只是和辐条抢注意力。
    """
    cx, cy = COL_X[col], TREE_Y0 + ratio * TREE_H
    items = MINI[mod]
    rot = rot_of(mod)
    o = []
    if ON[mod]:
        # 开了：底色实一点 + 强调色红环
        o.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{RING_R:.2f}" '
                 f'fill="var(--fill-on)"/>')
        o.append(circle(cx, cy, RING_R, w=2.2, color="var(--accent)", op=0.95))
    else:
        o.append(circle(cx, cy, RING_R, w=1.7, color="var(--ink)", op=0.42,
                        fill="var(--fill)"))
    o.append(circle(cx, cy, BEZEL_R, w=0.6, color="var(--ink)", op=0.06))
    o.append(circle(cx, cy, SCALE_R, w=0.7, color="var(--ink)", op=0.10))

    for (_lb, _vl, v), (_a0, _a1, am) in zip(items, seg_angles(len(items), rot)):
        o.append(spoke(cx, cy, am, v))
    return "".join(o)


def ein_sof() -> str:
    """（已移除）Keter 之上的"无限光"。

    v0.15 第一稿画过三道同心弧，实际渲染出来是**画在圆里面**的（半径给得太小），
    而且小绪的原话是"我只要生命树/世界树" —— 加装饰是反方向。
    留这个空函数只是为了记住这个判断，不要再加回来。
    """
    return ""


def tree_paths() -> str:
    """22 条路径 —— 直线，和原图一样。

    分两层：**中柱那条竖直主干**（Keter→Tiferet→Yesod→Malkuth）稍深，
    其余 19 条更淡。原图用三种颜色区分三柱，这里不引彩色，用**深浅**做层次。
    """
    trunk = {("keter", "tiferet"), ("tiferet", "yesod"), ("yesod", "malkuth")}
    o = []
    for a, b in PATHS:
        ax, ay = sph_xy(a)
        bx, by = sph_xy(b)
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1.0
        ux, uy = dx / L, dy / L
        deep = (a, b) in trunk or (b, a) in trunk
        o.append(line(ax + ux * (RING_R + 1), ay + uy * (RING_R + 1),
                      bx - ux * (RING_R + 1), by - uy * (RING_R + 1),
                      w=1.1 if deep else 0.9,
                      color="var(--ink)", op=0.30 if deep else 0.15))
    return "".join(o)


# ================================================================ 环形文字
def ring_text(cx: float, cy: float, mod: str) -> str:
    """一个质点的环形文字 —— 名与值各自沿弧排，贴在自己那段刻度下。

    每个环位占圆周上一段（段心就是它辐条的角度）。段内：
      · 名圈在外（NAME_R），值圈在内（VAL_R）；
      · 朝向按段选（`orient()`），朝内的那半圈路径半径 +0.5×字号；
      · `startOffset="50%"` + `text-anchor="middle"` 把文字摆到弧的中点。
    """
    key = mod
    defs, texts = [], []
    n = len(MINI[mod])
    for i, ((k, v, _p), (a0, a1, am)) in enumerate(
            zip(MINI[mod], seg_angles(n, rot_of(mod)))):
        out, _tilt = orient(am)
        if out:
            pf, pt, cw = a0, a1, True
            rn, rv = NAME_R, VAL_R
        else:
            pf, pt, cw = a1, a0, False
            rn, rv = NAME_R + 0.5 * NAME_FS, VAL_R + 0.5 * VAL_FS
        pid_n, pid_v = f"pn-{key}-{i}", f"pv-{key}-{i}"
        defs.append(f'<path id="{pid_n}" fill="none" '
                    f'd="{arc_d(cx, cy, rn, pf, pt, cw)}"/>')
        defs.append(f'<path id="{pid_v}" fill="none" '
                    f'd="{arc_d(cx, cy, rv, pf, pt, cw)}"/>')
        texts.append(f'<text class="t-n"><textPath href="#{pid_n}" '
                     f'startOffset="50%" text-anchor="middle">{k.upper()}</textPath></text>')
        texts.append(f'<text class="t-v"><textPath href="#{pid_v}" '
                     f'startOffset="50%" text-anchor="middle">{v}</textPath></text>')
    return f'<defs>{"".join(defs)}</defs><g>{"".join(texts)}</g>'


def crosshair(cx: float, cy: float, mod: str) -> str:
    """（已移除）瞄准镜准星。

    小绪的原话：「现在这个准星好丑啊，算了不要准星了，我要文字在最中心就好了」。
    试过两版 —— 先小后大（十字臂 14.0、两道密位刻度、中心点、w=1.3），
    两版他都否了。所以**不要再画回来**，包括"淡淡的背景准星"那种折中。
    留这个空壳只是为了记住这个判断。
    """
    return ""


def module_label(cx: float, cy: float, mod: str) -> str:
    """模块名 —— 大写加粗，**摆在圆心正中心**。

    它同时是模块开关的点击区（见 `node_art()` 的边框）。
    y 手动抬 0.35 个字高做视觉垂直居中（不用 dominant-baseline，
    各浏览器对它的解释不完全一致，画设计稿要的是可复现）。
    """
    y = cy + MOD_DY + 0.35 * MOD_FS
    return (f'<text class="t-m" x="{cx:.1f}" y="{y:.1f}" '
            f'text-anchor="middle">{TITLE[mod]}</text>')


def node_text(col: str, ratio: float, mod: str) -> str:
    cx, cy = COL_X[col], TREE_Y0 + ratio * TREE_H
    return ring_text(cx, cy, mod) + crosshair(cx, cy, mod) + module_label(cx, cy, mod)


def tilt_report() -> str:
    """打印每个节点的最大倾斜角与弧长 —— 用于核对，不参与出图。"""
    rows = []
    for _k, _c, _r, mod, _cn, _sp in SEPHIRA:
        n = len(MINI[mod])
        segs = seg_angles(n, rot_of(mod))
        span = segs[0][1] - segs[0][0]
        ts = [abs(math.degrees(orient(am)[1])) for (_a0, _a1, am) in segs]
        rows.append(f"    {TITLE[mod]:<8} n={n}  rot={rot_of(mod):>5.1f}°  "
                    f"最大倾斜 {max(ts):>5.1f}°   "
                    f"值圈弧长 {VAL_R * span:>5.1f}px   名圈弧长 {NAME_R * span:>5.1f}px")
    return "\n".join(rows)


def count_report() -> str:
    """控件对账 —— 环位数 + 边框开关数 必须 = createLayout() 的 48。"""
    ring = sum(len(v) for v in MINI.values())
    switch = len(BOOL_PARAMS)
    total = ring + switch
    ok = "✓" if total == 48 else "★ 对不上 ★"
    return (f"环位 {ring} 个 + 边框开关 {switch} 个 = {total} 个  "
            f"（createLayout 声明 48 个）{ok}")


# ================================================================ 样式
CSS = '''
:root {
  --paper:#FAFAF9;
  --ink:#0E0E0F;
  --ink-2:rgba(14,14,15,.64);
  --ink-3:rgba(14,14,15,.46);
  --ink-4:rgba(14,14,15,.17);
  --hair:rgba(14,14,15,.09);
  --fill:rgba(14,14,15,.048);
  --fill-on:rgba(14,14,15,.075);
  /* v0.17 的强调色。**v0.18 起实际发货的是蒂芙尼蓝 #0ABAB5 + 深青芯 #00938F**，
     本页保留深红是为了让这份"当时为什么这么定"的记录自洽（见页首横幅）。 */
  --accent:#8E1F1F;
  --accent-v018:#0ABAB5;
  --accent-v018-deep:#00938F;
}
* { margin:0; padding:0; box-sizing:border-box; }
body {
  background:#EFEFEC; color:var(--ink);
  font-family:"Inter Tight",-apple-system,"Helvetica Neue",sans-serif;
  display:flex; flex-direction:column; align-items:center;
  padding:56px 24px; gap:40px; min-height:100vh;
}
body.bare { padding:0; gap:0; background:var(--paper); display:block; }
.panel {
  position:relative; width:@@PW@@px; height:@@PH@@px;
  background:var(--paper); overflow:hidden;
  box-shadow:0 0 0 0.5px rgba(14,14,15,.10), 0 24px 70px rgba(14,14,15,.13);
}
body.bare .panel { box-shadow:none; }

/* ---- 生命之树（图形层） ---- */
.tree { position:absolute; left:0; top:0; width:@@PW@@px; height:@@PH@@px; }

/* ---- 环形文字（SVG） ---- */
.t-n {
  font-family:"Inter Tight",-apple-system,"Helvetica Neue",sans-serif;
  font-size:@@NF@@px; font-weight:600; letter-spacing:.06em;
  fill:var(--ink-3);
}
.t-v {
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:@@VF@@px; font-weight:500; letter-spacing:-.01em;
  fill:var(--ink-2);
}
.t-m {
  font-family:"Inter Tight",-apple-system,"Helvetica Neue",sans-serif;
  font-size:@@MF@@px; font-weight:700; letter-spacing:.005em;
  fill:var(--ink);
}

/* ---- 表面颗粒 ---- */
.noise { position:absolute; left:0; top:0; width:100%; height:100%;
         mix-blend-mode:multiply; opacity:0.030; pointer-events:none; }

/* ---- 设计稿说明（不进面板） ---- */
.pg-h { font-size:12px; letter-spacing:.20em; color:rgba(14,14,15,.42);
        text-transform:uppercase; font-weight:500; text-align:center; }
.legend { width:@@PW@@px; display:grid; grid-template-columns:repeat(2,1fr);
          gap:26px 38px; }
.lg { border-top:0.5px solid rgba(14,14,15,.16); padding-top:10px; }
.lg-t { font-size:12.5px; font-weight:600; color:var(--ink);
        margin-bottom:6px; letter-spacing:.01em; }
.lg-d { font-size:11px; line-height:1.75; color:rgba(14,14,15,.55); }
.lg-d b { color:var(--ink); font-weight:600; }
.lg-d code { font-family:"IBM Plex Mono",monospace; font-size:10px;
             background:rgba(14,14,15,.06); padding:1px 3px; border-radius:2px; }
.lg.hot { border-top:0.5px solid var(--accent); }
.lg.hot .lg-t { color:var(--accent); }
'''


def noise_layer() -> str:
    """表面颗粒 —— 一层极淡的噪点。纸不是数学光滑的。"""
    return '''<svg class="noise"><filter id="grain">
<feTurbulence type="fractalNoise" baseFrequency="0.86" numOctaves="4" stitchTiles="stitch"/>
<feColorMatrix type="saturate" values="0"/>
</filter><rect width="100%" height="100%" filter="url(#grain)"/></svg>'''


def superseded_banner() -> str:
    """v0.17 之后视觉改过两处，这个文件不再代表现状。

    不加这条说明的话，读这份设计稿的人会以为强调色是深红、字体是 Inter Tight ——
    而实际发货的插件是蒂芙尼蓝 + Ableton Sans。**设计稿说的和插件做的不一致，
    比没有设计稿更糟**，所以这里把差异明写出来。

    真正的事实来源是 plugin/TranePanel.h（几何 / 颜色 / 控件表全在里面），
    而且有 tests/test_editor_layout.py 盯着它和 PluginProcessor 不分叉。
    """
    return '''<div class="pg-h" style="color:#8E1F1F">
已被 v0.18 取代 —— 本页是 v0.17 的设计论证记录，不是现状。
</div>
<div class="pg-h" style="font-weight:400;line-height:1.7">
v0.18 起已实现并改动了：<b>① 强调色由深红 #8E1F1F 改为蒂芙尼蓝 #0ABAB5
（+ 深青芯 #00938F 保证白底可辨）</b>；<b>② 字体由 Inter Tight / IBM Plex Mono
改为 Ableton Sans Bold / Medium</b>（运行时读用户本机 Ableton Live 12 自带的字体，
不复制、不打包，找不到降级 Helvetica Neue Bold）；
<b>③ 背景加了字符画视频</b>（asciify.mp4 在构建期烤成 75 帧 2-bit 素材，
可读区遮罩烘进档位）；④ 面板层已独立成 TranePanel，界面可离线渲染 + 逐像素验证。
<br>现状的事实来源是 <code>vst/plugin/TranePanel.h</code>；
现行渲染见 <code>outputs/Trane_panel_v0.18_*.png</code>。
</div>'''


def build(bare: bool = False) -> str:
    art = ein_sof() + tree_paths() + "".join(
        node_art(c, r, m) + node_text(c, r, m)
        for _k, c, r, m, _cn, _sp in SEPHIRA)
    head = ("" if bare else
            superseded_banner()
            + '<div class="pg-h">Träne · 界面设计稿 v0.17 · 48 控件全上屏 / 环形文字 / 白底</div>')
    body_cls = ' class="bare"' if bare else ''
    legend = "" if bare else legend_block()
    css = (CSS.replace("@@PW@@", str(PANEL_W))
              .replace("@@PH@@", str(PANEL_H))
              .replace("@@VF@@", f"{VAL_FS}")
              .replace("@@NF@@", f"{NAME_FS}")
              .replace("@@MF@@", f"{MOD_FS}"))
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>Träne UI 设计稿 v0.17 · 48 控件 / 环形文字</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{css}</style></head>
<body{body_cls}>
{head}
<div class="panel">
  <svg class="tree" viewBox="0 0 {PANEL_W} {PANEL_H}">{art}</svg>
  {noise_layer()}
</div>
{legend}
</body></html>'''


def legend_block() -> str:
    on = "、".join(TITLE[m] for m in ON if ON[m])
    rows = [
        ("★ 这一版补齐了 12 个漏掉的控件", True,
         "v0.16 定稿之后去对了一遍 <code>createLayout()</code>，发现"
         "<b>设计稿只画了 36 个，插件里实际声明了 48 个</b>。漏的 12 个是："
         "6 个模块开关（<code>grain_on / stutter_on / comb_on / tape_on / "
         "sweep_on / delay_on</code>）、<code>grain_position</code>、"
         "<code>grain_spray</code>、<code>delay_pingpong</code>、"
         "<code>ruin_mode</code>、<code>sweep_mode</code>。"
         "这一版以那个函数为唯一依据重排。"),
        ("对账", None,
         f"{count_report()}<br>"
         "环位 = 真正的旋钮 / 档位；边框开关 = 模块的开关。"
         "两边的数量都写死在脚本里，改参数表时对账会立刻报错。"),
        ("开关搬到圆的边框上", None,
         "48 个控件平摊到 10 个圆，最挤的 GRAIN 有 9 个 —— 环位最多舒服地放 8 个。"
         "所以<b>7 个模块开关不上环，改成圆的边框</b>：关 = 淡黑细环，"
         "开 = <b>强调色红环</b>。点圆心区（模块名）切换。"
         "这不只是省地方 —— 生命之树本来就是「光从 Keter 一级级流到 Malkuth」，"
         "<b>开一个亮一个，整棵树逐级点亮</b>。"),
        ("边框亮不亮的规则", None,
         "取决于「这个模块当前是否真的参与信号」："
         "有 on 开关的 7 个看开关；<b>RUIN</b> 看 <code>ruin_mode</code>"
         "（mode = 0 就是纯干声，等于没开）；<b>SPACE</b> 看 <code>space_mix</code>；"
         "<b>OUT</b> 恒亮。<br>"
         "<b>注意：<code>createLayout()</code> 里 6 个 <code>_on</code> 默认全是 false，"
         "<code>freeze</code> 也是 false。</b>所以真正的初始状态是「只有 SPACE 和 OUT 亮」。"
         f"本稿的演示状态是：<b>{on}</b>。"),
        ("档位参数怎么上环", None,
         "<code>sweep_mode</code> 是 <code>AudioParameterChoice</code>（LP / BP / HP），"
         "也占一个环位：<b>辐条长度 = 档位序号归一化</b>（0 / 0.5 / 1.0），"
         "<b>值直接写档位名</b>。<code>ruin_mode</code> 是 0–1 的连续 morph"
         "（0 = Clear → 1 = Ruin），当普通旋钮处理。"),
        ("简写对照", None,
         "<code>POS</code> = Grain Position · <code>SPRY</code> = Grain Spray · "
         "<code>PING</code> = Delay PingPong · <code>MODE</code> = Ruin Mode · "
         "<code>FB</code> = Feedback · <code>WOBB</code> = Tape Wobble · "
         "<code>CENT</code> = Sweep Center · <code>RESO</code> = Sweep Reso · "
         "<code>DIFF</code> = Space Diffuse · <code>SPRD</code> = Grain Spread · "
         "<code>DENS</code> = Grain Density。<br>"
         "其余都是原词截断，不另列。宿主里的显示名不变，只是环上写简写。"),
        ("文字改成环形排字", None,
         "每个环位占圆周上一段，<b>名与值都沿弧排、贴在自己那段刻度下</b>"
         "（辐条落在段的中间）。<b>名圈在外</b>（半径 49.0 / 7.0px 大写 + 字距）、"
         "<b>值圈在内</b>（38.5 / 7.5px 等宽）—— 刻度在外，由外往内读正好是"
         "「SIZE 120ms」；反着放会读成「120ms SIZE」，参数名沦为补注。"),
        ("环形文字的两条几何规则", None,
         "<b>① 方向按段选</b>：SVG 里文字上方向 = 路径的左手法线。沿 +θ 走是"
         "<b>径向朝外</b>，沿 −θ 走是<b>径向朝内</b>。两种朝向的倾斜角恰好差 180°，"
         "所以每段取小的那个 —— <b>最大倾斜恒 ≤ 90°，永远不会倒立</b>。"
         "<b>② 下半圈半径 +0.5 字号</b>：朝内时文字长在基线内侧，不补就会上下两半错开半个字。"),
        ("段间空隙按弧长给", None,
         "不按固定角度。固定角度的话 n 一变空隙就跟着变，可用弧长算不出来。"
         f"现在固定 <b>{GAP_PX:.0f}px 弧长</b>（按值圈半径折算），"
         "n=8 时值圈弧长 26.2px，最长的值「120ms」在 7.5px 等宽下约 22.1px —— 放得下。"),
        ("每个节点的转盘都转过一下", None,
         "段心默认从 12 点起算，但 <b>n=2 / n=6 会正好把段摆在 3 点 / 9 点</b>"
         "（那里倾斜 90°）。所以对每个节点搜一个旋转量，让最大倾斜最小"
         "（FREEZE → 0°、GRAIN → 60°）。平手时取离 0 最近的，结果唯一可复现。"),
        ("准星也去掉了", None,
         "红点删掉之后试过两版<b>瞄准镜准星</b>（十字臂 + 中心点 + 密位刻度），"
         "都被否了 —— 「好丑啊，算了不要准星了，我要文字在最中心就好了」。"
         "现在圆心<b>只剩模块名，摆在正中心</b>。"),
        ("旋钮是辐条 · 长度就是值", None,
         "每个环位是圆外的一条径向辐条，<b>长度就是值</b>（<code>SPOKE_SPAN × v</code>），"
         "末端一个小圆点。圆外那圈极淡的圆是标尺 —— 辐条的最大长度正好落在它上面。"
         "长度比角度直观，整圈长短不一，像日晷。"),
        ("辐条长度是宿主里的真实位置", None,
         "<code>nrm()</code> 复刻 JUCE <code>NormalisableRange::convertTo0to1</code>。"
         "<b>这个函数早前是错的，已按源码修好</b>：JUCE 是 "
         "<code>pow(proportion, skew)</code>（<code>juce_NormalisableRange.h:147</code>），"
         "不是 <code>pow(proportion, 1/skew)</code>。写反的后果很具体："
         "<b>grainSize 120ms</b> 本该在 <b>55.8%</b> 处，错公式给出 2.6%。"),
        ("柱距用回原图比例", None,
         "文字在圆内，圆与圆之间<b>不再需要留文字空间</b> —— 柱距就是原图的 "
         "<b>2.932 倍</b>（r/柱距 = 0.341），一点都不放宽。"
         "树宽高比 <b>0.507</b>，和原图一致。"),
        ("十个质点 = 十个模块", None,
         "<b>Keter</b> freeze（源）· <b>Chokhmah</b> grain · <b>Binah</b> stutter · "
         "<b>Chesed</b> comb · <b>Gevurah</b> tape · <b>Tiferet</b> ruin · "
         "<b>Netzach</b> sweep · <b>Hod</b> delay · <b>Yesod</b> space · "
         "<b>Malkuth</b> out（显现）。22 条连线 = 原图的标准路径，中柱主干更深。"),
        ("字体与颜色", None,
         "模块名与参数名 <b>Inter Tight</b>（紧凑，字距小），数值 <b>IBM Plex Mono</b>"
         "（等宽数字，改数值时不会跳）。白底 <b>#FAFAF9</b> + 近黑 <b>#0E0E0F</b>，"
         "四档透明度分层。<b>强调色 #8E1F1F 现在只有一个用途：亮着的模块边框。</b>"),
        ("待你拍板", None,
         f"① 面板 <b>{PANEL_W}×{PANEL_H}</b>（v0.10 是 860×438）；"
         "② <b>开关放边框 + 点圆心切换</b>这个交互接不接受；"
         "③ 字体 <b>Inter Tight + IBM Plex Mono</b>；④ 白底 + 深红 <b>#8E1F1F</b>；"
         "⑤ 环形文字的<b>最大倾斜 90°</b> —— 圆左右两侧的字会竖起来，"
         "这是环形排版的物理极限（倒立已经用方向规则避开了）。"),
    ]
    items = "".join(
        f'<div class="lg{" hot" if hot else ""}">'
        f'<div class="lg-t">{t}</div><div class="lg-d">{d}</div></div>'
        for t, hot, d in rows)
    return f'<div class="legend">{items}</div>'


if __name__ == "__main__":
    import pathlib
    out = pathlib.Path(__file__).resolve().parents[2] / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "Trane_UI_proposal_v0.17.html").write_text(build(False), encoding="utf-8")
    (out / "_panel_bare.html").write_text(build(True), encoding="utf-8")
    print(f"ok  面板 {PANEL_W} x {PANEL_H}   半径 {RING_R}   柱距 {COL_SPACING:.2f}   "
          f"树高 {TREE_H:.2f}   宽高比 {(2 * COL_SPACING + 2 * RING_R) / (TREE_H + 2 * RING_R):.4f}")
    print(count_report())
    print(tilt_report())
