#!/usr/bin/env python3
"""对**编译出来的**面板做定量像素检查 —— 界面版的"离线渲染验证"。

为什么要有这个文件
==================
DSP 那边可以离线渲染 + 用数学方法检验输出；界面这边本来只能靠人肉看截图。
v0.17 之后面板层刻意不依赖 juce_audio_processors，于是可以用 panel_probe
把**和插件完全相同的绘制代码**渲染成 PNG —— 界面从此也能机器验证。

`tests/test_editor_layout.py` 查的是"表和几何对不对"，这里查的是
"**画出来的像素对不对**"。两者互补：一个能抓住"参数没上屏"，
一个能抓住"上屏了但画没了"。

它盯的八件事（每一条都对应一种"看起来还在跑"的静默故障）
========================================================
  1. 面板尺寸 / 底色        —— 底色被改、或被别的图层盖住。v0.35 起面板上有
                                **两种**底（面板底 + 块底），判据是"最多的两种
                                颜色正好是这两层、且合计 ≥ 90%"；
  2. 检查器真的画了          —— 参数行没上屏时面板照样"看起来挺干净"；
  3. 排版横向逐行齐平        —— 参数名左缘 / 数值右缘，**基准是框内缘**（v0.35）；
  4. **控件形态真的分得开**  —— 旋钮 / 条形 / 分段块三种形态在轨道区的墨迹起点
                                各不相同，像素判据是充要的；**正向对照在同一个
                                循环里**（条形行必须左端有墨），否则"全成了旋钮"
                                会让"旋钮行左端没墨"轻松通过；
     **4b. 环有多大就是声明的那一支** —— 形态分对了不等于**画对了**：画笔里
                                写死一个半径，`knob_dia` 照样吐、净空算术照样绿、
                                上面每一条也照样绿。实测环的外径（29.4）对声明；
  5. 排版纵向撑满            —— 首行齐平、末行同高、都撑到底部；
  6. **模块框**（v0.35）     —— 框顶 / 框底齐平、互不重叠、缝宽 == kBlockGap、
                                框内是块底 / 框外是面板底、框线真的画了、
                                框上的"全旋钮"标志 == `knob_modules` 清单；
  7. 面板上**不再出现彩色**  —— 移除聚焦蓝框后，#0A84FF 不应出现在任何状态；
  8. 每帧耗时在预算内        —— 呼吸动画一顿一顿的，源头都在这里。

**v0.33 删掉的**：原来还有"树的两层都画了"（骨架点线 + 信号实线）、
"两档高亮真的分得开"、"模式 / 列数 / 分割线真的改变版面"三条。世界树、信号线、
分割线、MODE / 列数控件全都没有住户了，所以它们连同量法一起删。
**一并记下那套量法**，因为它是这个文件里最好用的一招，以后一定还会用：
  要判断"一条线画了没有、有多亮、是点线还是实线"，别去看整张图 ——
  沿那条线采样，取**峰值**（线只有 1.6px 宽，均值量到的是"线有多细"）
  和**覆盖率**（亮度 ≥ 8 的采样点占比：实线 ≈ 1.000，点线 0.18–0.51）。
  峰值单独用会被"别的线从它上面穿过去"污染（实测有边被抬到 135，而它本身 30）。

几何**从 panel_probe --dump-geometry 读**，状态**从 panel_probe 的状态自述读**，
不在这个文件里再抄一份 —— 抄一份就多一个会分叉的地方。
（唯一的例外是字体：那三行 `font_*` **故意不读**，理由见 `read_geometry`。）

用法
====
    python tools/check_panel_render.py [--outdir <目录>] [--scale 2] [--version 0.35]
"""
from __future__ import annotations

import argparse
import math
import pathlib
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBE = ROOT / "build" / "panel_probe_artefacts" / "Release" / "panel_probe"

BG = (0x00, 0x00, 0x00)          # systemBackground
ACCENT = (0x0A, 0x84, 0xFF)      # systemBlue（dark）

# 模块链 —— 必须和 TranePanel.h::kNodes 的顺序一致。
#
# **v0.33 起它不再用来算"信号边"**（树与 9 条信号线都删了），只用来对账
# 四栏的展平顺序：从左到右、从上到下读下来必须正好是这条链。
CHAIN = ["freeze", "grain", "stutter", "comb", "tape", "ruin", "sweep", "delay", "space", "out"]

# v0.33 删掉了 `SIGNAL_EDGES` / `SKELETON_PATHS` / `SKELETON_ONLY` 三张表，
# 以及配套的 `edge_segment` / `edge_peak` / `edge_coverage` / `_edge_profile`
# 四个"沿一条线采样"的函数。它们量的东西（9 条信号实线 + 22 条骨架点线）
# 已经不存在了。
#
# 一并记下那条**量法**，因为它是这个项目里最好用的一招，以后一定还会用：
#   要判断"一条线画了没有、有多亮、是点线还是实线"，别去看整张图 ——
#   沿那条线采样，取**峰值**（线只有 1.6px 宽，均值量到的是"线有多细"）
#   和**覆盖率**（亮度 ≥ 8 的采样点占比：实线 ≈ 1.000，点线 0.18–0.51）。
#   峰值单独用会被"别的线从它上面穿过去"污染（实测有边被抬到 135，而它本身 30）。

# 每帧耗时上限。**这是回归门槛，不是性能目标** —— 本机空载实测 4.3 ms
# （1440×720 @2×，即 2880×1440）。它挡的是量级变化：界面被别的东西铺满、
# 或者某个绘制环节退化成 O(N²)。
#
# 门槛给到 20 ms 而不是贴着 4.3，是因为这个数**随机器负载漂**，漂得还不少：
# 2026-09-30 做 v0.36（顶栏换 logo）时，同一台机器上实测 9.0–9.3 ms，
# 当时 `uptime` 的 load 是 2.7、WorkBuddy 占 107% 单核、Ableton 占 44%。
# 对照实验（把品牌标整个关掉再量）仍是 8.97 ms —— **漂的是环境，不是面板**。
# 所以量这个数之前先看一眼 `uptime`，别把别人的 CPU 占用记成自己的回归。
FRAME_BUDGET_MS = 20.0

# 背景重烤（面板底）上限。本机实测 0.6–0.8 ms（5 次取最小）。
# 它只在尺寸变化时发生一次，所以门槛给得比每帧松。
REBUILD_BUDGET_MS = 8.0

# 背景图**冷重烤**上限（换图 / 换落位 / 改窗口尺寸才走）。
# 3000×3000 源图、2880×1440、参数区。贵在源图的高质量重采样，一次性动作，
# 所以门槛给得宽 —— 它挡的是"退化成每帧都做一次"，不是挡"慢了 20%"。
#
# ---- 门槛为什么维持 60，以及它到底挡得住什么 ----
#
# 探针报的是 **N 次取最小**（见 panel_probe --cold-reps）。理由与实测数据
# 都写在那边，这里只记结论：
#
#     单次采样（旧）      26.15 / 26.91 / 27.21 / 27.52 / **71.32** ms  → 极差 173%
#     5 次取最小（新）    21.10 … 21.50 ms（正常）                      → 极差 1.9%
#     5 次取最小（新）    30.2 … 58.3 ms（8 个进程同时抢 CPU）           → 极差 93%
#
# 第一行就是这条断言以前**会随机报红**的原因，也是我这次改它的原因。
# 第三行是**已知上限**：取最小把噪声压掉一大截，但压不到零 ——
# 8 份负载下最小值也会被抬到 58，已经贴着 60。所以门槛**不收紧**：
# 拿一台被抢得很凶的机器去卡一条一次性动作的绝对毫秒数，本身就是错的问题。
#
# 真正的回归探测靠**相对判据**（下面那条 热/冷 ≤ 0.5）。同一份 8 份负载下
# 实测比值 0.048–0.119，和空载时一样稳 —— 因为机器快慢在分子分母上约掉了。
BG_REBUILD_BUDGET_MS = 60.0

# 背景图**热重合成**上限（拖明暗度每帧都走这条）。本机实测 1.4 ms（5 次取最小）。
# 这条门槛是 v0.31 拆缓存层的直接理由：不拆的话这里就是 21 ms，
# 30Hz 下一帧要 33 ms，拖起来必卡。
BG_TINT_BUDGET_MS = 8.0

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def luma(rgb: np.ndarray) -> np.ndarray:
    return (rgb.astype(np.float32) @ LUMA)


# ---------------------------------------------------------------------------
# 几何 / 状态：都从编译产物读
# ---------------------------------------------------------------------------
def read_geometry() -> dict:
    assert PROBE.is_file(), f"找不到 {PROBE}（先构建 panel_probe）"
    r = subprocess.run([str(PROBE), "--dump-geometry"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr

    geo = {"nodes": [], "ctl": {}, "knobs": [], "choices": []}
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "panel":
            geo["w"], geo["h"] = int(parts[1]), int(parts[2])
        elif parts[0] == "ui_version":
            # **面板的版本**（不是插件版本）。出图文件名要用它。
            # 从编译产物读，不在这里写死 —— 写死过，实测分叉了：
            # 面板做到 v0.33，这里 `--version` 的默认值还是 `0.32`，
            # 于是 outputs/ 里躺着一批"名字说 v0.32、画的是 v0.33"的图。
            geo["ui_version"] = parts[1]
        elif parts[0] == "pane":
            geo["pane"] = (float(parts[1]), float(parts[2]))
        elif parts[0] == "controls":
            geo["controls"] = int(parts[1])
        elif parts[0] == "knobs":
            # knobs <个数> <id…> —— 哪些参数画成旋钮（v0.34）。
            # **必须从编译产物读**：拼错一个 id 只会静默少一个旋钮，
            # 而下面那条"旋钮行轨道左端没有墨"的像素断言就会去量一个
            # **本来就是条形**的行，然后报一个假的 ✗。
            geo["knobs"] = parts[2:]
        elif parts[0] == "choices":
            # choices <id…> —— 第三种形态（LP / BP / HP 分段块）。
            # 它既不是旋钮也不是条形：墨迹从**格子里的文字**起，
            # 所以"条形行左端必须有墨"那条对照必须把它排除在外。
            geo["choices"] = parts[1:]
        elif parts[0] == "knob_dia":
            # knob_dia <直径> <环粗> —— 旋钮的几何。**从编译产物读**，
            # 检查器不许自己抄一份（抄一份就会分叉，而分叉了照样绿）。
            geo["knob_dia"] = (float(parts[1]), float(parts[2]))
        elif parts[0] == "knob_modules":
            # knob_modules <个数> <模块名…> —— **哪几个模块整块画成旋钮**（v0.35）。
            # 判据从"逐参数"改成"按模块"之后，`knobs` 行是**展开后的结果**，
            # 这一行才是**因**。两条都要读：只读结果的话，"模块名拼错一个字"
            # 这种坏法（那个模块整块静默退回条形、而所有像素断言照样绿）在
            # 这里就看不见 —— 它由 `tests/test_ui_design.py` 那条"清单里的
            # 模块名都能在 kNodes 里找到"报红，这里再交叉验一次"框上的标志
            # 与模块清单一致"。
            geo["knob_modules"] = parts[2:]
            assert int(parts[1]) == len(geo["knob_modules"]), \
                f"knob_modules 自述 {parts[1]} 个、实际列了 {len(geo['knob_modules'])} 个"
        elif parts[0] in ("block_fill", "block_edge"):
            # block_fill / block_edge <不透明度> <r> <g> <b> —— 块底与框线的
            # **合成结果**（已经叠在面板底上）。
            #
            # 必须读**合成值**，不能自己拿不透明度再算一遍：自己算就是第二份
            # 实现，分叉了照样绿。而且下面那些像素断言是拿它当**判据**用的
            # （"这块像素是块底吗"），判据本身错了，整节就变成自说自话。
            geo[parts[0]] = {"alpha": float(parts[1]),
                             "rgb": (int(parts[2]), int(parts[3]), int(parts[4]))}
        elif parts[0] == "block_geom":
            # block_geom <内缩 x> <内缩 y> <框间缝> <圆角>（v0.35）。
            # 框间缝要拿来验"框与框之间的缝宽恒定"，圆角要拿来定采样点
            # （贴着角取样会落到面板底上，看起来像"框没画"）。
            geo["block_geom"] = tuple(float(v) for v in parts[1:])
        # v0.35 的 `font_ui` / `font_data` / `text_inventory` 三行**故意不在这里读**。
        # 字体是**度量级**的事实（family 名 / 字重 / 竖干宽度 / 数字等不等宽），
        # 而它们要在 `tests/test_ui_design.py` §8 里拿 fontTools 直接量 .ttf
        # 才有意义；在这个只做像素的文件里读一遍名字，只是把同一句话说了两遍。
        # **但"面板真的在用打包字体"这件事是有人管的** —— 构建坏了的话
        # `font_ui` 会吐 `<null>`，那条断言当场报红。
        elif parts[0] == "param_rows":
            geo["param_rows"] = int(parts[1])
        elif parts[0] == "switches":
            geo["switches"] = int(parts[1])
        elif parts[0] == "bg_region":
            geo["bg_region"] = (float(parts[1]), float(parts[2]))
        elif parts[0] == "bg_ctrl":
            geo["bg_ctrl"] = [float(v) for v in parts[1:]]
        elif parts[0] == "bg_bright":
            geo["bg_bright"] = (float(parts[1]), float(parts[2]), float(parts[3]))
        elif parts[0] == "logo":
            # logo <x> <y> <宽> <高> <源宽> <源高>（v0.36）—— 顶栏品牌标的落位。
            # **从编译产物读**：宽高比来自资产本身，检查器自己按常量推就会分叉。
            assert len(parts) == 7, f"logo 行格式变了（期望 7 段）：{line!r}"
            geo["logo"] = tuple(float(v) for v in parts[1:])
        elif parts[0] == "mod":
            # v0.33：行名从 `node` 改成 `mod`，而且**不再吐 x / y**
            # （质点坐标是树的几何）。这里如果还按 `node` 找，会一条都找不到 ——
            # 那是故意的：静默拿到 0 个质点比当场报错难查得多。
            # v0.35：**多吐一个节点序号**（原来是靠行序隐含）。见 TranePanel.cpp
            # 那一段注释 —— 能吐出来的东西不要靠约定。
            geo["nodes"].append({"node": int(parts[1]), "sephira": parts[2],
                                 "module": parts[3], "rows": int(parts[4])})
        elif parts[0] == "ctl":
            # ctl <id> <node> <slot> [短名]。槽位是"行序"的唯一来源 ——
            # 一栏里第几行是哪个控件，全靠它推（见 `row_ids`）。
            geo["ctl"][parts[1]] = (int(parts[2]), int(parts[3]))

    assert [n["module"] for n in geo["nodes"]] == CHAIN, \
        f"geometryDump 里的模块顺序 {[n['module'] for n in geo['nodes']]} != 链 {CHAIN}"
    for k in ("pane", "bg_region", "bg_ctrl", "bg_bright", "param_rows", "switches",
              "logo"):
        assert k in geo, f"geometryDump 缺少 {k}（检查没法做）"
    # 形态与行序：少了它们，旋钮那节会退化成"一个都没量到然后全绿"。
    assert geo["knobs"], "geometryDump 没吐 knobs 行 —— 旋钮检查会空转"
    assert "choices" in geo and geo["choices"], \
        "geometryDump 没吐 choices 行 —— 分段块会被当成条形，正向对照会假报红"
    assert not (set(geo["knobs"]) & set(geo["choices"])), \
        f"同一个控件既是旋钮又是分段块：{sorted(set(geo['knobs']) & set(geo['choices']))}"
    assert len(geo["ctl"]) == geo["controls"], \
        f"ctl 行只有 {len(geo['ctl'])} 条，控件有 {geo['controls']} 个"
    assert "knob_dia" in geo, \
        "geometryDump 没吐 knob_dia —— 「相邻旋钮的净空」那条断言会空转"
    # v0.35：模块框的三样东西。少了它们，"框内是块底 / 框外是面板底"
    # 和"框间缝宽恒定"那两条会**空转**（拿不到块底的颜色就无从判断，
    # 而"没判断"在这套写法里很容易退化成"全绿"）。
    assert geo.get("knob_modules"), \
        "geometryDump 没吐 knob_modules —— 「框上的标志与模块清单一致」会空转"
    assert "block_fill" in geo and "block_edge" in geo, \
        "geometryDump 没吐 block_fill / block_edge —— 块底的像素断言没有判据"
    assert "block_geom" in geo and len(geo["block_geom"]) == 4, \
        "geometryDump 没吐 block_geom（内缩 x / 内缩 y / 框间缝 / 圆角）"
    # 版本号也要有：出图文件名靠它。缺了就用不了 `--outdir`，
    # 而"悄悄退回一个写死的旧版本号"正是这次要修的病。
    assert geo.get("ui_version"), \
        "geometryDump 没吐 ui_version —— 出图文件名会退回一个写死的版本号"
    geo["by_module"] = {n["module"]: n for n in geo["nodes"]}
    return geo


def render(state: str, scale: float, dest: pathlib.Path, *extra: str) -> dict:
    """渲染一张，返回探针的状态自述（lit / cols / shown / hover / press / bg …）。"""
    cmd = [str(PROBE), "--out", str(dest), "--scale", str(scale),
           "--state", state, "--time", "0.9", *extra]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{' '.join(cmd)}\n{r.stderr}"

    out = {"lit": [], "raw": r.stdout}
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "lit":
            out["lit_n"] = int(p[1])
            out["lit"] = p[2:]
        elif p[0] == "cols":
            out["cols"] = int(p[1])
        elif p[0] == "shown":
            out["shown"] = int(p[1])
        # v0.33 删了三条自述的解析：`mode` / `divider` / `hot` —— 版面只有一种、
        # 分割线没了、信号线没了。**解析代码一起删**，不是留着读不到就跳过：
        # 留着的话，`st["hot"]` 会 KeyError，但 `st.get("mode")` 那种写法
        # 会静默变成 None，于是"模式切换改变了版面"那条断言在 None 上通过。
        elif p[0] in ("hover", "press"):
            out[p[0]] = p[1] if len(p) > 1 else "none"
        elif p[0] == "hover_t":
            # hover 淡入的相位：第 1 段 = 线性进度，第 2 段 = 过完缓动的亮度。
            out["hover_lin"] = float(p[1])
            out["hover_amt"] = float(p[2])
        elif p[0] == "bg":
            out["bg_on"], out["bg_where"] = p[1], p[2]
            out["bg_bright"] = float(p[3])
            out["bg_size"] = p[4]
        elif p[0] == "背景重烤":
            out["rebuild_ms"] = float(p[1])
        elif p[0] == "明暗度重合成":
            out["tint_ms"] = float(p[1])
    assert "lit_n" in out and "cols" in out, f"探针没吐状态自述:\n{r.stdout}"
    assert "hover" in out and "press" in out, \
        "探针没吐 hover / press 自述 —— 交互态检查会退化成空转（量的是普通态却全绿）"
    # 请求了 `--hover` 就必须自述淡入相位 —— 少了它，"hover 是渐入的"那一节
    # 会退化成 KeyError（或者更坏：有人把断言删了，然后这一节静默空转）。
    if "--hover" in extra:
        assert "hover_lin" in out and "hover_amt" in out, \
            f"探针没吐 hover_t 自述（淡入相位没法验证）:\n{r.stdout}"
    # 请求了交互态就必须自述一致：否则后面那条"交互态没有强调色"是在量一张普通图。
    for flag, want in zip(extra, extra[1:]):
        if flag in ("--hover", "--press"):
            got = out[flag.strip("-")]
            assert got == want, f"{flag} {want} 没生效，探针自述 {got!r}"
    # 同理，`--bg` 没生效的话"背景铺到了参数区"那条断言是在量一张**没有背景**的图。
    if "--bg" in extra:
        assert "bg_on" in out, f"--bg 没生效，探针没吐 bg 自述:\n{r.stdout}"
    return out


def read_layout() -> tuple[list[dict], float, float, list[dict]]:
    """读 `--dump-layout`：检查器各栏的排版数字（列宽 / 行距 / 字号 / 三段宽）。

    **这是"排版整齐"唯一的证据来源。** 肉眼看不出 11pt 变成了 10pt，
    也看不出四栏的轨道起点差了 3px —— 数字能。

    返回 `(各栏, 行内留白, 框内缩, 模块框)`。

    留白（名字 ─ 轨道 ─ 数值 之间那道）也要读回来：三段宽加起来填不满
    **框内宽**时，差出来的就是**被吞掉的留白** —— 那是"数值列宽够不够"
    之外的另一半保证（见 `main()` 里那条断言）。

    框内缩（`padx`）与模块框（`block`）是 v0.35 加的。前者不读的话，
    三段宽会拿**栏宽**当内容宽，那条断言永远差 28px 地报红；后者是
    "框画在哪儿"的唯一机器可读来源 —— 少了它，"框有没有盖住行""框与框
    之间留了多少缝"就只能靠肉眼看图。
    """
    r = subprocess.run([str(PROBE), "--dump-layout"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    cols: list[dict] = []
    blocks: list[dict] = []
    gap = None
    padx = None
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "gap":
            gap = float(p[1])
            continue
        if p[0] == "padx":
            # 框的水平内缩（v0.35）。**三段宽算的是框内宽**：少了这一行，
            # "参数名左缘齐平"会永远差 14px 地报红（实测 14.50 / 15.00），
            # 而报出来的样子像"排版歪了"，看不出是判据少了一项。
            padx = float(p[1])
            continue
        if p[0] == "block":
            # block <栏> <模块下标> <框顶> <框底> <该模块是否全旋钮>（v0.35）。
            # 末位那个 0/1 是"形态的一致性跨框与行两处看"的接口 —— 见 check_state。
            assert len(p) == 6, f"block 行格式变了（期望 6 段）：{line!r}"
            blocks.append({"col": int(p[1]), "node": int(p[2]),
                           "top": float(p[3]), "bottom": float(p[4]),
                           "knob": p[5] == "1"})
            continue
        if p[0] != "col":
            continue
        c = {"index": int(p[1])}
        for i in range(2, len(p) - 1, 2):
            key, val = p[i], p[i + 1]
            if key == "nodes":
                # 行尾是一串**模块下标**（不是名字）：`nodes 0 1`。
                c["nodes"] = [int(x) for x in p[i + 1:]]
                break
            c[key] = float(val)
        c["rows"] = int(c["rows"])
        cols.append(c)
    assert len(cols) >= 4, f"--dump-layout 只吐了 {len(cols)} 栏"
    assert gap is not None, \
        "--dump-layout 没有 gap 行 —— 行内留白读不回来，三段宽就没办法对账"
    assert padx is not None, \
        "--dump-layout 没有 padx 行 —— 三段宽会拿栏宽当内容宽（永远差 2×padx）"
    assert blocks, "--dump-layout 没有 block 行 —— 模块框的几何读不回来"
    assert len(blocks) == sum(len(c["nodes"]) for c in cols), \
        f"block 行 {len(blocks)} 条，四栏一共 {sum(len(c['nodes']) for c in cols)} 个模块"
    return cols, gap, padx, blocks


def render_frames(scale: float, dest: pathlib.Path) -> tuple[float, float]:
    """量一遍每帧耗时和背景重烤耗时，返回 (每帧 ms, 重烤 ms)。"""
    r = subprocess.run([str(PROBE), "--out", str(dest), "--scale", str(scale),
                        "--state", "all", "--frames", "60"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr
    m = re.search(r"每帧\s+([\d.]+)\s+ms", r.stdout)
    assert m, f"没量到每帧耗时:\n{r.stdout}"
    b = re.search(r"背景重烤\s+([\d.]+)\s+ms", r.stdout)
    assert b, f"没量到背景重烤耗时:\n{r.stdout}"
    return float(m.group(1)), float(b.group(1))


# ---------------------------------------------------------------------------
# 检查
# ---------------------------------------------------------------------------
class Report:
    """检查结果的收集器。**每一条当场打印**，不在最后统一 dump。

    为什么改成立刻打印（v0.34）：原先所有结果攒在 `lines` 里、最后 `dump()`
    一次吐出来，于是**后面任何一步抛异常，前面已经报红的那些行一起消失** ——
    屏幕上只剩一条 traceback。实测撞到过：把旋钮直径调大一档，
    「相邻旋钮的净空 ≥ 环粗」已经报红了，但紧接着 `check_state` 因为行数
    对不上抛了异常，那条 ✗ 就再也没印出来。反向对照脚本只认 `✗`，
    于是它判"没抓住" —— 而其实抓住了。**证据被后来的崩溃吃掉了。**

    这和"红得没有信息量 = 没红"是同一条规矩的两面：
    不该让崩溃**伪造**证据，也不该让崩溃**吞掉**证据。
    """

    def __init__(self):
        self.failed = 0

    def ok(self, name: str, detail: str) -> None:
        print(f"  ✓ {name}  {detail}", flush=True)

    def bad(self, name: str, detail: str) -> None:
        self.failed += 1
        print(f"  ✗ {name}  {detail}", flush=True)

    def check(self, cond: bool, name: str, detail: str) -> None:
        (self.ok if cond else self.bad)(name, detail)


def accent_mask(img: np.ndarray) -> np.ndarray:
    """#0A84FF 的判别式。只认蓝远大于红、且绿也明显高于红的像素 ——
    白字（r≈g≈b）与灰线都不会误命中。"""
    r = img[:, :, 0].astype(np.int16)
    g = img[:, :, 1].astype(np.int16)
    b = img[:, :, 2].astype(np.int16)
    return (b > 140) & (b - r > 80) & (g - r > 40) & (g > 60)


def make_test_backdrop(path: pathlib.Path) -> None:
    """造一张**结构已知**的测试图：左半纯白、右半纯黑，中间一条 8px 灰带，
    **最右缘再点一小段白**。

    为什么不用真照片：真照片量不出"背景出现在哪儿" —— 它哪儿都有内容，
    于是"背景铺到了参数区"和"背景漏到了树区"两个断言都退化成
    "图上有点变化"。这张图的白 / 黑分界正好落在落位区正中，
    "图有没有铺到该铺的地方、有没有被拉变形"于是变成一个可以断言的坐标问题。

    **右缘那 16px 白是 v0.33 补的。** 少了它，落位区的**右边界**根本量不到：
    测试图右半是纯黑，而面板底也是黑的 —— 黑压黑，像素上一动不动。
    v0.33 实测：改动范围只到 x=721.5，而落位区实际到 1400，于是
    "像素上的落位 == bg_region"那条断言**永远红**。它红得没有信息量
    （不是落位错了，是那张图上右半边本来就没有可测量的内容）。
    右缘留一小段白之后，落位区的右边界就有了一个能亮的坐标。

    尺寸取 **3000×3000** —— 和用户真会丢进来的照片一个量级。这不是为了好看：
    "冷重烤在预算内"那条门槛量的就是源图的高质量重采样，拿一张 800×800 的
    图去量，量出来的数比真实情况小一个量级，门槛也就形同虚设。
    """
    w = h = 3000
    a = np.zeros((h, w, 3), np.uint8)
    a[:, : w // 2] = 255
    a[:, w // 2 - 4: w // 2 + 4] = 128
    a[:, -16:] = 255
    Image.fromarray(a).save(path)


def column_bands(L: np.ndarray, col: dict, scale: float,
                 y0: float, y1: float,
                 thr: float = 60.0, merge: float = 6.0) -> list[tuple[float, float]]:
    """把一栏里的**墨迹横带**切出来 —— 一条带 = 一行。

    合并间隔小于 `merge` 的相邻带：一个字的上下两半（比如 "=" 的两横、
    带点的字母）本来会被切成两条。

    `y0` / `y1` **没有默认值**，是故意的。这里原来默认 `y0 = 118.0`（v0.33
    的 kRowsTop），v0.35 行区从 118 挪到 138（框顶）之后，那个默认值就成了一句
    **过期的约定** —— 118..138 之间正好是空的，量出来照样对，于是没人会发现
    它已经错了。

    v0.36 之后这个"正好是空的"**不成立了**：顶栏右上角的品牌标纵向跨 38..134、
    横向 1306..1400，而第 4 栏的 x 范围一直伸到 1400。也就是说 118..138 这段
    在第 4 栏里**有东西**（logo 的下缘）。如果哪天有人把默认值加回来，
    第 4 栏会量出一个多出来的横带，而报出来的样子是"行数与自述不一致" ——
    真正的原因（取样窗压到 logo 上了）在报错里一个字都看不出来。

    所以规矩不变、只是更要紧了：**必须由调用方从 `--dump-layout` 的 block 行
    算出来**（block 顶 = 138，正好在 logo 下缘 134 之下）。几何只有一份来源。
    """
    x0, x1 = col["x"] - 6.0, col["x"] + col["w"] + 6.0
    sub = L[int(y0 * scale):int(y1 * scale), int(x0 * scale):int(x1 * scale)]
    rows = (sub > thr).any(axis=1)
    bands: list[list[float]] = []
    cur = None
    for k, v in enumerate(rows):
        y = y0 + k / scale
        if v:
            if cur is None:
                cur = [y, y]
            else:
                cur[1] = y
        elif cur is not None:
            bands.append(cur)
            cur = None
    if cur is not None:
        bands.append(cur)
    merged: list[list[float]] = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < merge:
            merged[-1][1] = b[1]
        else:
            merged.append(b)
    return [(a, b) for a, b in merged]


def band_bbox(L: np.ndarray, col: dict, band: tuple[float, float],
              scale: float, thr: float = 60.0) -> tuple[float, float]:
    """一条横带里的**横向**墨迹范围（逻辑坐标）。"""
    x0, x1 = col["x"] - 6.0, col["x"] + col["w"] + 6.0
    sub = L[int(band[0] * scale):int(band[1] * scale) + 1,
            int(x0 * scale):int(x1 * scale)]
    m = sub > thr
    assert m.any(), f"带 {band} 里一个墨点都没有 —— 分割方式错了"
    xs = np.where(m.any(axis=0))[0]
    return x0 + xs.min() / scale, x0 + xs.max() / scale


def title_row_flags(col: dict, geo: dict) -> list[bool]:
    """一栏里每一行是不是**模块标题行**。

    行序是推导出来的（每个模块 = 1 个标题行 + 它的参数行数），不是猜的 ——
    从 `--dump-geometry` 的 `mod` 行读参数行数。
    """
    flags: list[bool] = []
    for node in col["nodes"]:
        flags.append(True)                                     # 标题行
        flags += [False] * geo["by_module"][CHAIN[node]]["rows"]   # 参数行
    return flags


def row_ids(col: dict, geo: dict) -> list[str | None]:
    """一栏里每一行对应的控件 id；模块标题行 = None。

    与 `title_row_flags` 同源、同序（标题行 + 该模块的参数行），只是这里
    把参数行**按槽位排**，于是每一行具体是哪个控件也知道了 ——
    "这一行画的是旋钮还是条形"要问它。

    参数行按 `ctl` 行的槽位排，不按字典序、也不按 id 猜。
    """
    out: list[str | None] = []
    for node in col["nodes"]:
        out.append(None)                                       # 标题行
        rows = sorted((slot, cid) for cid, (n, slot) in geo["ctl"].items()
                      if n == node and slot >= 0)
        out += [cid for _slot, cid in rows]
    return out


def check_state(tag: str, st: dict, scale: float, png: pathlib.Path,
                geo: dict, rep: Report, layout: list[dict],
                gap: float, padx: float, blocks: list[dict]) -> dict:
    img = np.asarray(Image.open(png).convert("RGB"))
    ph, pw = img.shape[:2]
    want_w = round(geo["w"] * scale)
    want_h = round(geo["h"] * scale)
    rep.check((pw, ph) == (want_w, want_h), f"{tag}: 尺寸",
              f"{pw}×{ph}（期望 {want_w}×{want_h}）")

    # 行区（= 框区）的上下沿。**从 `--dump-layout` 的 block 行算**，不写死 ——
    # 见 `column_bands` 的 docstring：118 那个写死的值就是这么过期的。
    rows_top = min(b["top"] for b in blocks)
    rows_bot = max(b["bottom"] for b in blocks) + 8.0

    # ---- 1 · 底色 ----
    #
    # v0.35 起面板上**不再只有一种底色**：每个模块坐进一个半透明的块里，
    # 块底（kInk @ kBlockFillA 叠在面板底上）的面积比露在外面的面板底还大。
    # 实测 60.9% / 33.3% —— 所以判据从"众数是 #000000"改成"**面板上
    # 95% 的像素只有这两种颜色**，而且它们正好是面板底与块底"。
    #
    # 判据**没松、反而更严**：原来只钉一种颜色，现在钉的是"这两种、按这个
    # 比例、加起来占绝对多数"。任何装饰层（阴影、渐变、彩色）都会同时打掉
    # 两条 —— 而"界面被别的东西铺满"这件事原来要等到占比掉到 0.55 才报红。
    flat = img.reshape(-1, 3)
    packed = (flat[:, 0].astype(np.uint32) << 16) | (flat[:, 1].astype(np.uint32) << 8) | flat[:, 2]
    counts = np.bincount(packed, minlength=1 << 24)
    top2 = sorted(range(len(counts)), key=lambda i: -int(counts[i]))[:2]
    top2_rgb = [((i >> 16) & 255, (i >> 8) & 255, i & 255) for i in top2]
    top2_share = sum(int(counts[i]) for i in top2) / packed.size
    block_rgb = geo["block_fill"]["rgb"]

    def hexs(rgb):
        return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

    # **判据换了，不是放宽了。** v0.34 及以前钉的是"众数是面板底 #000000，占 ≥ 70%"。
    # v0.35 每个模块坐进一个半透明的块里，块底（kInk @ kBlockFillA 叠在面板底上
    # = #0D0D0D）的面积比露出来的面板底还大（实测 60.9% vs 33.3%），于是原来那条
    # 会报红 —— 而它报的是"界面被别的东西铺满了"，其实什么都没坏。
    #
    # 新的判据钉的是**同一件事**：面板上最多的两种颜色**就是这两层底**，
    # 而且它们加起来占绝对多数。实测 94.2%，剩下的 5.8% 是文字、框线（0.11 的墨）
    # 和那个分段块 —— 都是**小面积**。
    #
    # 它挡的坏法一样：任何装饰层（阴影 / 渐变 / 彩色 / 卡片）要么把某一种新颜色
    # 顶进前二，要么把这两种的合计压下去。一条断言管两头。
    rep.check(set(top2_rgb) == {BG, block_rgb},
              f"{tag}: 面板上最多的两种颜色就是这两层底",
              f"{hexs(top2_rgb[0])} {counts[top2[0]] / packed.size:.1%} · "
              f"{hexs(top2_rgb[1])} {counts[top2[1]] / packed.size:.1%}"
              f"（期望 {hexs(block_rgb)} 与面板底 {hexs(BG)}；实测 60.9% / 33.3%）")
    rep.check(top2_share >= 0.90, f"{tag}: 只有这两种底色",
              f"两者合计 {top2_share:.1%}（≥ 90%；实测 94.2%，剩下的 5.8% 是文字、"
              f"框线与分段块。低于这个数说明界面被别的东西铺满了 —— 任何阴影 / "
              f"渐变 / 彩色都会同时打掉这一条和上面那条）")

    L = luma(img)

    # ---- 2 · 检查器真的画了 ----
    # v0.33：参数区的左右边界直接来自 `--dump-geometry` 的 `pane` 行
    # （分割线删了，它就是编译期常量）。**不再写死 30 / 28 这种数** ——
    # 写死的话，改了内边距这条断言就量到别的地方去了，而且照样绿。
    pane_x, pane_w = geo["pane"]
    px0 = int(round(pane_x * scale))
    px1 = int(round((pane_x + pane_w) * scale))
    py0 = int(round(rows_top * scale))       # 框顶（= kRowsTop；从 block 行读）
    pane = L[py0:ph, px0:px1]
    assert pane.size > 0, "参数区一个像素都没圈到 —— 几何对不上了"
    text = float((pane > 140).mean())
    rep.check(0.004 <= text <= 0.25, f"{tag}: 检查器文字画了",
              f"参数区亮像素 {text:.2%}（0.4%–25%；接近 0 = 参数行没上屏）")

    # ---- 3 · 排版：四栏的横向必须**逐行齐平** ----
    #
    # 这一节是小绪「所有排版都必须要整齐」落成的**像素判据**。
    #
    # 为什么必须**逐行**量、不能只量整栏的包围盒：包围盒只取极值，
    # 某一行缩进 3px、某一行的数值没右对齐，极值一点都不会变 ——
    # 而那种错法眼睛看得出来（读起来"有一行歪了"），包围盒看不出来。
    #
    # 判据（实测：四栏全部在 ±0.5px 内）：
    #   · 每个**参数行**的墨迹左缘 == **框内**左缘（参数名左对齐）
    #   · 每个**参数行**的墨迹右缘 == **框内**右缘（数值右对齐）
    # 标题行**不参与** —— 它的墨迹只到名字后面那个开关方块，本来就到不了右缘。
    # 把它算进来的话，这条断言会永远红，然后被人调松到没意义。
    #
    # v0.35：左右缘从"栏缘"改成"**框内缘**"（各内缩一个 `padx`）。
    # `padx` **从 `--dump-layout` 读**，不在这里写死 14 —— 写死的话，
    # 改了内缩这条断言就量到别的地方去了，而且照样绿。
    left_err: list[float] = []
    right_err: list[float] = []
    for ci, col in enumerate(layout):
        flags = title_row_flags(col, geo)
        bands = column_bands(L, col, scale, rows_top, rows_bot)
        rep.check(len(bands) == len(flags), f"{tag}: 栏 {ci} 的行数与自述一致",
                  f"像素上切出 {len(bands)} 行，geometryDump 推出 {len(flags)} 行")
        for band, is_title in zip(bands, flags):
            if is_title:
                continue
            bl, br = band_bbox(L, col, band, scale)
            left_err.append(bl - (col["x"] + padx))
            right_err.append(br - (col["x"] + col["w"] - padx))
    assert len(left_err) >= 30, f"只量到 {len(left_err)} 个参数行，检查会空转"
    rep.check(max(abs(e) for e in left_err) <= 1.5, f"{tag}: 参数名左缘齐平（框内）",
              f"最大偏差 {max(abs(e) for e in left_err):.2f}px（≤ 1.5，共 {len(left_err)} 行；"
              f"基准是框内左缘 = 栏左缘 + padx {padx:.1f}）")
    rep.check(max(abs(e) for e in right_err) <= 1.5, f"{tag}: 数值右缘齐平（框内）",
              f"最大偏差 {max(abs(e) for e in right_err):.2f}px（≤ 1.5，共 {len(right_err)} 行；"
              f"基准是框内右缘 = 栏右缘 − padx {padx:.1f}）")

    # ---- 3b · 控件形态：旋钮行 vs 条形行（v0.34）----
    #
    # 上面那两条量的是"行与行**齐不齐**"。这一条量的是"行与行**像不像**" ——
    # 小绪：「看哪些参数适合旋钮，哪些参数适合推子，按需分配」。
    #
    # 行只有**三种**形态，三种在轨道区的墨迹起点各不相同，所以判据是充要的
    # （下面每个数都是**实测**，v0.35 几何：轨道宽 139.984、旋钮直径 26.4、
    #  环粗 3.0）：
    #
    #   · **条形**  填充从轨道左端开始（`fillRect(tx, …)`，宽度是
    #               `max(th, trackW×值)` —— 值 = 0 时也留一截 `th`）
    #               → 墨迹左缘 == 轨道左端，**实测 +0.98px**（就是采样窗的第一列）；
    #   · **旋钮**  画在轨道**正中**（直径 26.4 + 环粗 3.0）
    #               → 墨迹左缘 = trackW/2 − (直径+环粗)/2 = 69.99 − 14.7
    #               = **实测 +54.98px**（20 个旋钮一个数，无一例外）；
    #   · **分段块**（`Fmt::Choice`，LP / BP / HP）→ 墨迹从**格子里的文字**起，
    #               **实测 +18.48px**。它**不参与**这条断言 —— 硬塞进来就会得到
    #               一个假的 ✗，而假报红比漏报更坏：它逼下一个人把阈值调松，
    #               把真断言一起废掉。（这一条是**实测撞出来的**：
    #               v0.34 第一版只分两类，`sweep_mode` 当场报红。）
    #
    # 两个阈值（24 / 4）都落在"实测的两个数之间"，**离两边都留了余量**：
    # 旋钮那侧 54.98 对 24，余量 31px；条形那侧 0.98 对 4，余量 3px。
    # 不取"实测值 ± 一点点"是因为那样一改几何就会报红，而报出来的样子
    # 是"形态判据失效"—— 其实只是数变了。
    #
    # **正向对照在同一个循环里**，不是另起一节：条形行必须"左端有墨"。
    # 少了它，一个把 `isKnob()` 恒返回 true 的桩会让"旋钮行左端没墨"轻松通过
    # —— 全成了旋钮，自然个个都没墨。`check_knobs_mutations.py` 的 M2 打的就是它。
    #
    # 采样区**严格限定在轨道那一段**（`tx+1 … tx+trackW−1`），于是参数名和数值
    # 都在窗外：数值右对齐，它的左缘最多到 `tx+trackW+kGap`，够不着。
    #
    # v0.35：`tx` 要加上**框内缩** `padx` —— 内容从框内起，不是从栏缘起。
    # 漏了它，所有条形行的墨迹左缘都变成 +14.0px，20 行全报红（实测）。
    #
    # 只在 `all` 态上量：出厂态七个模块全关，条形被压暗到接近底色，
    # 阈值卡在"亮 / 不亮"之间就变成了量不透明度，而不是量形态。
    if tag == "all":
        knob_ids = set(geo["knobs"])
        choice_ids = set(geo["choices"])
        seen: dict[str, list[str]] = {"knob": [], "bar": [], "choice": []}
        bad: dict[str, list[str]] = {"knob": [], "bar": [], "choice": []}
        for ci, col in enumerate(layout):
            ids = row_ids(col, geo)
            bands = column_bands(L, col, scale, rows_top, rows_bot)
            assert len(bands) == len(ids), \
                f"栏 {ci}：像素上切出 {len(bands)} 行，row_ids 推出 {len(ids)} 行"
            tx = col["x"] + padx + col["labelW"] + gap
            x0 = int(round((tx + 1.0) * scale))
            x1 = int(round((tx + col["trackW"] - 1.0) * scale))
            for band, cid in zip(bands, ids):
                if cid is None:
                    continue
                form = ("knob" if cid in knob_ids
                        else "choice" if cid in choice_ids else "bar")
                sub = L[int(band[0] * scale): int(band[1] * scale) + 1, x0:x1]
                assert sub.size > 0, f"栏 {ci} 行 {cid} 的轨道区一个像素都没圈到"
                m = sub > 40
                if not m.any():
                    # 三种形态都至少有一截墨（条形有最小宽度，旋钮有底环，
                    # 分段块有底色 + 文字）。窗外全黑只可能是几何对不上 ——
                    # 那会让下面几条一起空转。
                    bad[form].append(f"{cid}（轨道区一个墨点都没有）")
                    continue
                seen[form].append(cid)
                left = (x0 + int(np.where(m.any(axis=0))[0].min())) / scale
                if form == "knob" and left < tx + 24.0:
                    bad["knob"].append(f"{cid}（墨迹左缘在轨道左端 +{left - tx:.1f}px）")
                elif form == "bar" and left > tx + 4.0:
                    bad["bar"].append(f"{cid}（墨迹左缘在轨道左端 +{left - tx:.1f}px）")

        n_knob = len(geo["knobs"])
        n_bar = geo["param_rows"] - n_knob - len(geo["choices"])
        n_chc = len(geo["choices"])
        assert n_bar >= 20, f"条形只有 {n_bar} 行 —— 这条检查会空转"
        rep.check((len(seen["knob"]), len(seen["bar"]), len(seen["choice"]))
                  == (n_knob, n_bar, n_chc),
                  f"{tag}: 每一行都按形态归了类",
                  f"旋钮 {len(seen['knob'])}/{n_knob} · 条形 {len(seen['bar'])}/{n_bar}"
                  f" · 分段块 {len(seen['choice'])}/{n_chc}")
        rep.check(not bad["knob"], f"{tag}: 旋钮行的轨道左端没有墨",
                  f"{len(seen['knob'])} 行里 {len(bad['knob'])} 行不合格"
                  + ("" if not bad["knob"] else "：" + "，".join(bad["knob"][:4])))
        rep.check(not bad["bar"], f"{tag}: 条形行的轨道左端有墨（正向对照）",
                  f"{len(seen['bar'])} 行里 {len(bad['bar'])} 行不合格"
                  + ("" if not bad["bar"] else "：" + "，".join(bad["bar"][:4])))
        rep.check(not bad["choice"], f"{tag}: 分段块的轨道区画了东西",
                  f"{len(seen['choice'])} 行里 {len(bad['choice'])} 行不合格"
                  + ("" if not bad["choice"] else "：" + "，".join(bad["choice"][:4])))

        # ---- 3c · 旋钮环的**外径**必须就是声明的那一支 ----
        #
        # 上面那三条量的是"哪一行是什么形态"，这一条量的是"**画出来的环有多大**"。
        #
        # 少了它，`knob_dia` 那一行就只是喂给净空算术的一个数：**画笔里写死一个
        # 半径，dump 照样吐 26.4、净空算术照样绿、上面每一条也照样绿** ——
        # 环还是画在轨道正中、还是那么亮、还是被归成"旋钮"。
        # 也就是"声明"与"画出来的东西"之间**一个住户都没有**。
        # （这条是 `check_knobs_mutations.py` 的反向对照逼出来的：
        #  原来 M5「直径调大一档」漏网，查下去发现漏的不是净空，是这一层。）
        #
        # **它抓不到"改 `kKnobDia`"** —— 那个常量同时喂画笔和 dump，两边一起变，
        # 永远自洽。它抓的是**两边分叉**：画笔里写死半径、或者半径算了但没用在
        # `addCentredArc` 上。这两件事必须各有住户。
        #
        # 量法：在**轨道那一段**里逐行横扫，取**最宽的一行**。
        #   · 环是个圆，横跨度在圆心那一行最大 —— 这个最大值**自己就把圆心找到了**，
        #     不需要从别处拿 `mid`（拿的话又是"一份要跟着几何走的约定"）。
        #   · 窗口限定在轨道内，参数名与数值都在窗外；值末端点画在半径
        #     `r − 环粗/2` 上，恒在环内，撑不大跨度。
        #   · 底环是**整段 270°**（`kKnobStart` 225° 起、顺时针 `kKnobSweep`），
        #     缺口落在 4:30 → 7:30（**含正下方**）。所以圆心那一行的**左右两侧
        #     都压在环上**，跨度 = 外径 —— 这一点是实测确认的，不是推的。
        #
        # 实测（`all` 态、scale 2）：20 个旋钮全部落在 **29.00–29.50**，
        # 声明的外径 = 26.4 + 3.0 = **29.4** —— 极差 0.5px，容差给 1.0px。
        # 容差不为 0 是因为阈值（luma > 40）会各削掉半像素的反锯齿。
        dia, stroke = geo["knob_dia"]
        outer = dia + stroke
        ring_off: list[float] = []
        for ci, col in enumerate(layout):
            ids = row_ids(col, geo)
            bands = column_bands(L, col, scale, rows_top, rows_bot)
            tx = col["x"] + padx + col["labelW"] + gap
            rx0 = int(round((tx + 1.0) * scale))
            rx1 = int(round((tx + col["trackW"] - 1.0) * scale))
            for band, cid in zip(bands, ids):
                if cid not in knob_ids:
                    continue
                ry0 = int(band[0] * scale)
                ry1 = int(band[1] * scale) + 1
                widest = 0.0
                for y in range(ry0, ry1):
                    row = L[y, rx0:rx1] > 40
                    if row.any():
                        xs = np.where(row)[0]
                        widest = max(widest, (xs.max() - xs.min()) / scale)
                assert widest > 0.0, \
                    f"栏 {ci} 行 {cid}：旋钮行在轨道区里一个墨点都没有"
                ring_off.append(widest - outer)
        assert len(ring_off) >= 20, f"只量到 {len(ring_off)} 个旋钮，检查会空转"
        rep.check(max(abs(e) for e in ring_off) <= 1.0,
                  f"{tag}: 旋钮环的外径 == 声明的那一支",
                  f"最大偏差 {max(abs(e) for e in ring_off):.2f}px（≤ 1.0，"
                  f"共 {len(ring_off)} 个；声明 {dia:.1f} + 环粗 {stroke:.1f} = "
                  f"{outer:.1f}，实测跨度 "
                  f"{outer + min(ring_off):.2f}–{outer + max(ring_off):.2f}）")

    # ---- 4 · 排版：四栏的纵向必须**首末齐平** ----
    #
    # 四栏的**内容高度必须一样**：每栏各自解一次行距，把内容撑满同一个高度，
    # 于是首行落在同一条线上、末行也落在同一条线上。**这是"每栏各自撑满"
    # 这个方案的唯一目的**（对照：全栏统一行距会让 2 模块的栏底部留 136px 空洞，
    # 实测数据在 outputs/Trane_v0.33_重构方案.md）。
    #
    # 末行的容差是 5px 而不是 1.5px，理由是**量的东西不一样**：
    # 末行可能是文本（下沿到基线以下，含降部），也可能是**选择型方块**
    # （`SWEEP MODE` 那种 LP/BP/HP），方块的底比文字的下沿短约 4.5px。
    # 实测 683.0 / 683.0 / 678.5 / 683.0。这是行型差异，不是错位。
    # ---- 4 · 排版：四栏的纵向必须**末行同高** ----
    #
    # 不变量是**末行的 mid 相同** —— 实测四栏都是 **664.150**，精确相等。
    # 它由「四栏框底齐平」推出来：末行 mid = 框底 − kBlockDown − padY − fsName×0.35，
    # 四栏的框底都是 692、字号都是 11。所以**紧的那条是框底齐平（≤ 0.5px）**，
    # 这一条负责的是"那一行真的画在那里"。
    #
    # **为什么不能拿"墨迹下沿"比**（v0.34 那条就是这么写的，v0.35 当场报红 7.5px）：
    # 下沿取决于**行型**，而四栏的末行恰好是三种不同的行型 ——
    #   · 旋钮行  环的下沿 = mid + 10.4（环在正下方有 90° 缺口，最低的墨在 7:30/4:30）
    #   · 条形行  出厂值刻度的下沿 ≈ mid + 11.4
    #   · 分段块  亮着时 = mid + 9.6；**关着时只剩文字 = mid + 3.6**
    # 拿下沿比就是拿**行型**比，而"末行齐不齐"是**位置**问题。
    # 实测下沿 674.5 / 674.5 / 667.5 / 675.0（极差 7.5），而 mid 四个一模一样。
    #
    # 像素这边量**墨迹带的中心**，它落在 mid 附近且与行型无关地靠得住
    # （实测：旋钮 −2.15、分段块 0.00、条形 +2.10 —— 偏差来自各行的墨迹形状，
    #  不是位置）。容差 5px 是为了容下这三档形状差，**不是为了放过错位**：
    # 真错位（某栏少撑一行、或整栏下移）量出来是 pitch 级的量，最小 32.9px，
    # 比容差大 6 倍以上。
    def band_mid(c: dict) -> float:
        b = column_bands(L, c, scale, rows_top, rows_bot)[-1]
        return (b[0] + b[1]) * 0.5

    # 首行就简单得多：四栏的首行**都是标题行**（同一种行型），所以直接比墨迹顶。
    tops = [column_bands(L, c, scale, rows_top, rows_bot)[0][0] for c in layout]
    rep.check(max(tops) - min(tops) <= 2.0, f"{tag}: 四栏首行齐平",
              "首行顶 " + " / ".join(f"{v:.1f}" for v in tops)
              + f"（极差 {max(tops) - min(tops):.1f}px ≤ 2；四栏首行都是标题行，"
              f"同一种行型，所以这里可以直接比墨迹）")
    mids = [band_mid(c) for c in layout]
    rep.check(max(mids) - min(mids) <= 5.0, f"{tag}: 四栏末行同高",
              "末行中线 " + " / ".join(f"{v:.2f}" for v in mids)
              + f"（极差 {max(mids) - min(mids):.2f}px ≤ 5；"
              f"真实 mid 四栏都是 664.150，偏差来自行型：旋钮 −2.15 / "
              f"分段块 0.00 / 条形 +2.10）")
    bots = [column_bands(L, c, scale, rows_top, rows_bot)[-1][1] for c in layout]
    rep.check(min(bots) >= 660.0, f"{tag}: 四栏都撑到底部",
              f"最矮一栏末行底 {min(bots):.1f}（≥ 660；"
              f"矮了说明那一栏留了一大片空白 —— 2 模块的栏最容易被拉出空洞）")

    # ---- 4b · 模块框（v0.35）----
    #
    # 小绪：「这是一个单独的模块，要做成一部分**框起来**」，参照 VCV Rack /
    # 模块效果器 —— 但只取"模块是独立面板"这一层，拟物一概不要，转译成
    # Lux Cache 的语言：**没有阴影、没有彩色、没有装饰**，块底与框线都只是
    # 一层极淡的墨（kInk @ 0.055 / 0.11）。
    #
    # 这一节分两半，**数字一半 + 像素一半**，和上面排版那两节同一个结构：
    #
    #   数字（`--dump-layout` 的 block 行）：
    #     · 四栏的框顶齐平、框底齐平 —— 框是"每栏各自撑满"那套算法的**外壳**，
    #       框不齐就等于每栏的撑满高度不一样，而**行数那条断言照样绿**
    #       （它只看行，不看行外面那圈东西）；
    #     · 框与框**不重叠**、缝宽 == kBlockGap —— 缝是"模块之间的边界"，
    #       缝宽为 0 时两个框的边线叠在一起，读起来像一个框；
    #     · 框上的"全旋钮"标志 == `knob_modules` 清单 —— 形态的一致性跨
    #       "框"与"行"两处看：框告诉用户"这是一组"，行告诉用户"这一组是旋钮"。
    #
    #   像素：
    #     · 框**内**是块底、框**外**是面板底 —— 上面那条"只有这两种底色"
    #       是全局统计，它证明不了"这两种颜色各自出现在**该出现的地方**"。
    #       一个把块底铺满整个参数区的坏法会让那条断言更绿（占比从 94% 涨到
    #       接近 100%），而面板上所有分组信息都没了。
    blk_fill = geo["block_fill"]["rgb"]
    blk_edge = geo["block_edge"]["rgb"]
    pad_x, pad_y, blk_gap, blk_radius = geo["block_geom"]

    by_col: dict[int, list[dict]] = {}
    for b in blocks:
        by_col.setdefault(b["col"], []).append(b)
    for b in blocks:
        by_col[b["col"]].sort(key=lambda x: x["top"])

    blk_tops = [min(b["top"] for b in by_col[c["index"]]) for c in layout]
    blk_bots = [max(b["bottom"] for b in by_col[c["index"]]) for c in layout]
    rep.check(max(blk_tops) - min(blk_tops) <= 0.5, f"{tag}: 四栏框顶齐平",
              "框顶 " + " / ".join(f"{v:.3f}" for v in blk_tops)
              + f"（极差 {max(blk_tops) - min(blk_tops):.3f}px ≤ 0.5）")
    rep.check(max(blk_bots) - min(blk_bots) <= 0.5, f"{tag}: 四栏框底齐平",
              "框底 " + " / ".join(f"{v:.3f}" for v in blk_bots)
              + f"（极差 {max(blk_bots) - min(blk_bots):.3f}px ≤ 0.5）")

    overlaps: list[str] = []
    seam_errs: list[float] = []
    for ci, bs in by_col.items():
        for a, b in zip(bs, bs[1:]):
            if a["bottom"] > b["top"]:
                overlaps.append(f"栏 {ci} 的 {CHAIN[a['node']]} 与 {CHAIN[b['node']]}"
                                f"（{a['bottom']:.1f} > {b['top']:.1f}）")
            seam_errs.append((b["top"] - a["bottom"]) - blk_gap)
    assert seam_errs, "四栏里没有相邻的两个框 —— 框间缝那条会空转"
    rep.check(not overlaps, f"{tag}: 模块框互不重叠",
              f"{len(overlaps)} 处重叠" + ("" if not overlaps else "：" + "；".join(overlaps[:3])))
    rep.check(max(abs(e) for e in seam_errs) <= 0.5, f"{tag}: 框间缝宽 == kBlockGap",
              f"最大偏差 {max(abs(e) for e in seam_errs):.3f}px"
              f"（缝宽 {blk_gap:.1f}；缝是模块之间的边界，为 0 时两个框的边线"
              f"会叠在一起，读起来像一个框）")

    knob_mods = set(geo["knob_modules"])
    flag_errs = [f"{CHAIN[b['node']]}（标志 {'全旋钮' if b['knob'] else '条形'}，"
                 f"清单里{'在' if CHAIN[b['node']] in knob_mods else '不在'}）"
                 for b in blocks if b["knob"] != (CHAIN[b["node"]] in knob_mods)]
    rep.check(not flag_errs, f"{tag}: 框上的全旋钮标志 == knob_modules 清单",
              f"{len(blocks)} 个框里 {len(flag_errs)} 个不一致"
              + ("" if not flag_errs else "：" + "，".join(flag_errs[:4])))

    # 像素：框内 vs 框外。采样点**必须同时让开两样东西**，否则会落到别的东西上，
    # 看起来像"框没画"：
    #   ① **圆角**（半径 10）—— 贴着角取样会落到框外的面板底上；
    #   ② **行底**（hover / press 时那一层 0.04 的墨）—— 它的 x 范围是
    #      `cx − gap/2 … cx + cw + gap/2`，几乎铺满框内，只在左右各留
    #      `padX − gap/2 = 10px` 的**边沟**。所以取样点放在**左边沟的中间**、
    #      圆角以下。
    #
    # 这两条都是**实测撞出来的**：第一版取"框顶往下 padY+3、横向取中"，
    # 结果在 `interact hover 模块标题行` 那张图上量到 #151516（标题行的行底），
    # 报出来的样子是"grain 的框内不是块底"。
    def rgb_at(x: float, y: float) -> tuple[int, int, int]:
        return tuple(int(v) for v in img[int(round(y * scale)), int(round(x * scale))])

    in_bad: list[str] = []
    for b in blocks:
        col = layout[b["col"]]
        x = col["x"] + pad_x * 0.5
        y = b["top"] + blk_radius + 1.0
        got = rgb_at(x, y)
        if got != blk_fill:
            in_bad.append(f"{CHAIN[b['node']]} 框内 ({x:.0f},{y:.0f}) 是 {hexs(got)}")
    rep.check(not in_bad, f"{tag}: 框内是块底",
              f"{len(blocks)} 个框里 {len(in_bad)} 个不是块底 {hexs(blk_fill)}"
              f"（取样点：左边沟中点、圆角以下 —— 避开行底与圆角）"
              + ("" if not in_bad else "：" + "；".join(in_bad[:3])))

    out_bad: list[str] = []
    n_out = 0
    for ci, bs in by_col.items():
        col = layout[ci]
        x = col["x"] + col["w"] * 0.5
        for a, b in zip(bs, bs[1:]):
            y = (a["bottom"] + b["top"]) * 0.5
            n_out += 1
            got = rgb_at(x, y)
            if got != BG:
                out_bad.append(f"栏 {ci} 的 {CHAIN[a['node']]}/{CHAIN[b['node']]} 缝 "
                               f"({x:.0f},{y:.0f}) 是 {hexs(got)}")
    # 框区**之外**（框顶再往上 8px）也必须是面板底 —— 少了这一点，
    # "框外是面板底"只在框与框之间成立，块底溢到框上面去照样绿。
    y_above = rows_top - 8.0
    for ci, col in enumerate(layout):
        n_out += 1
        got = rgb_at(col["x"] + col["w"] * 0.5, y_above)
        if got != BG:
            out_bad.append(f"栏 {ci} 框区上方 (y={y_above:.0f}) 是 {hexs(got)}")
    rep.check(not out_bad, f"{tag}: 框外是面板底",
              f"{n_out} 个采样点里 {len(out_bad)} 个不是面板底 {hexs(BG)}"
              f"（取样点：框间缝正中 + 框区上方；缝是模块之间的边界，"
              f"那里必须是底，否则框底铺出了框）"
              + ("" if not out_bad else "：" + "；".join(out_bad[:3])))

    # 框线**画了**（它是 0.11 的墨压在**块底**上 = #262627，luma 37 —— 上面那些
    # 断言全用"≠ 块底/面板底"来判，所以一条线都不画也能全绿）。沿框的
    # **左边线**取一列，要求它的峰值落在框线那个颜色上（容差 −3：自述是
    # `roundToInt(0.11×kInk + 0.89×块底)` = 37，而 JUCE 实际合成出来是 38，
    # 差 1 是取整次序不同；没画线时这一列的峰值只有块底的 13）。
    edge_peaks: list[float] = []
    for b in blocks:
        col = layout[b["col"]]
        x = col["x"]
        y0, y1 = int(round((b["top"] + blk_radius + 2.0) * scale)), \
                 int(round((b["bottom"] - blk_radius - 2.0) * scale))
        strip = L[y0:y1 + 1, int(round((x - 1.5) * scale)):int(round((x + 1.5) * scale)) + 1]
        assert strip.size > 0, f"{CHAIN[b['node']]} 的左边线一列像素都没圈到"
        edge_peaks.append(float(strip.max()))
    want_edge = 0.2126 * blk_edge[0] + 0.7152 * blk_edge[1] + 0.0722 * blk_edge[2]
    worst = min(edge_peaks)
    rep.check(worst >= want_edge - 3.0, f"{tag}: 框线真的画了",
              f"最暗的左边线峰值 luma {worst:.1f}（框线 {want_edge:.1f}，容差 −3；"
              f"它只有 0.11 的墨、压在块底上，所以上面那些「≠ 底色」的断言抓不到它）")

    # ---- 5 · 强调色 ----
    acc = accent_mask(img)
    n_acc = int(acc.sum())
    return {"accent": n_acc, "text": text, "acc_mask": acc}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=None,
                    help="把渲染出的 PNG 拷到这个目录（默认不拷，只检查）")
    ap.add_argument("--scale", type=float, default=2.0)
    # 不给默认值：默认值就会分叉。不写就用 `--dump-geometry` 的 `ui_version`
    # （编译产物里的 `kUiVersion`，面板版本的单一定义）。显式给了就以你为准 ——
    # 只在你**故意**要拿旧版本号出图时才该这么做。
    ap.add_argument("--version", default=None,
                    help="出图文件名里的版本标签；不写则取 geometryDump 的 ui_version")
    args = ap.parse_args()

    geo = read_geometry()
    layout, gap, padx, blocks = read_layout()
    print(f"几何（来自编译产物）：面板 {geo['w']}×{geo['h']}  "
          f"参数区 x {geo['pane'][0]:.0f} 宽 {geo['pane'][1]:.0f}  "
          f"控件 {geo['controls']}（参数 {geo['param_rows']} + 开关 {geo['switches']}）  "
          f"模块 {len(geo['nodes'])}")
    assert geo["param_rows"] + geo["switches"] == geo["controls"], "参数 + 开关 != 控件总数"

    # ---- 排版自述：`--dump-layout` 的四栏 ----
    #
    # 这一节是"排版整齐"的**数字**一侧。像素一侧在 check_state 里。
    # 两条一起才立得住：数字说"我打算画成一样宽"，像素说"确实一样宽"。
    print("\n[排版 —— 四栏的列宽 / 行距 / 字号 / 三段宽]")
    rep = Report()
    rep.check(len(layout) == 4, "四栏", f"实际 {len(layout)} 栏")
    rep.check(len({round(c["w"], 3) for c in layout}) == 1, "四栏等宽",
              "列宽 " + " / ".join(f"{c['w']:.3f}" for c in layout))
    gaps = [layout[i + 1]["x"] - layout[i]["x"] for i in range(len(layout) - 1)]
    rep.check(len({round(g, 3) for g in gaps}) == 1, "栏距恒定",
              "栏距 " + " / ".join(f"{g:.3f}" for g in gaps))
    # 栏宽 + 栏距必须正好填满参数区 —— 否则右边会多出一截没用的空白（或溢出）。
    used = layout[-1]["x"] + layout[-1]["w"] - layout[0]["x"]
    rep.check(abs(used - geo["pane"][1]) <= 0.5, "四栏正好填满参数区",
              f"栏占 {used:.3f}，参数区 {geo['pane'][1]:.3f}")
    # 三段宽必须**跨栏一致** —— 它们是按"全表最长的名字/数值"算的，
    # 逐栏各算一份的话，同一列里轨道起点会跟着栏变，读起来就是"不齐"。
    for key, why in (("labelW", "参数名"), ("trackW", "轨道"), ("valueW", "数值")):
        vals = {round(c[key], 3) for c in layout}
        rep.check(len(vals) == 1, f"三段宽 · {why} 跨栏一致",
                  f"{sorted(vals)}（跨栏不同 = 轨道起点会跟着栏跳）")
    # 三段宽 + **两道留白**必须正好填满一栏**框内**。
    #
    # 少了这条，`trackW` 少减一个 kGap 也照样绿 —— 轨道往右多铺 8px，把那道留白
    # 吃掉，而最宽的数值就**贴在轨道上**了（数值右对齐 + 不截断，看不出异常）。
    # 这是"数值列宽够不够"（`tests/test_ui_design.py` §6）之外的**另一半**：
    #   · 那一条保证"最长的串放得进 valueW"；
    #   · 这一条保证"轨道没有侵占 valueW 左边那道留白"。
    # 两条合起来，最宽的数值离轨道才是 kGap。
    #
    # v0.35：对账的基准从**栏宽**改成**框内宽**（栏宽 − 2×padx）。
    # 内容坐在框里，所以三段宽算的是框内那段。不改的话这条**永远差 28px**
    # 地报红，而报出来的样子像"留白被吞了"，看不出是基准取错了。
    inner = {round(c["w"] - 2.0 * padx, 3) for c in layout}
    assert len(inner) == 1, f"四栏的框内宽不一致：{sorted(inner)}"
    inner_w = next(iter(inner))
    leftover = {round(inner_w - c["labelW"] - c["trackW"] - c["valueW"], 3)
                for c in layout}
    rep.check(len(leftover) == 1 and abs(next(iter(leftover)) - 2.0 * gap) <= 1e-3,
              "三段宽 + 两道留白 正好填满一栏（框内）",
              f"框内宽 {inner_w:.3f}（栏宽 {layout[0]['w']:.3f} − 2 × padx {padx:.1f}）"
              f" − 名 {layout[0]['labelW']:.3f}"
              f" − 轨道 {layout[0]['trackW']:.3f} − 数值 {layout[0]['valueW']:.3f}"
              f" = {sorted(leftover)}（应为 2 × kGap = {2.0 * gap:.3f}）")
    # 字号只有三档，而且名字 < 数值 < 标题。
    fss = {(round(c["fsName"], 2), round(c["fsValue"], 2), round(c["fsTitle"], 2))
           for c in layout}
    rep.check(len(fss) == 1, "四栏字号一致", f"{sorted(fss)}")
    fsn, fsv, fst = sorted(fss)[0]
    rep.check(fsn < fsv < fst, "字号阶梯：参数名 < 数值 < 标题",
              f"{fsn} < {fsv} < {fst}（名是辅助信息、数值是主内容、标题是分组）")
    # 行距：每栏各自解，所以栏间**允许**不同 —— 但**必须都不小于字号**，
    # 否则行与行会挤在一起。而最挤那栏的行距就是字号的来源。
    pitches = [c["pitch"] for c in layout]
    rep.check(min(pitches) >= fst * 2.0, "最挤一栏的行距也够松",
              f"最小行距 {min(pitches):.3f} ≥ 标题字号 {fst} × 2")
    rep.check(max(pitches) - min(pitches) <= 12.0, "栏间行距不失控",
              "行距 " + " / ".join(f"{p:.3f}" for p in pitches)
              + f"（极差 {max(pitches) - min(pitches):.3f}；"
              f"「每栏各自撑满高度」的代价，实测最小 32.909 最大 43.100）")
    # 展平顺序必须就是模块链 —— 从左到右、从上到下读下来正好是信号顺序。
    flat = [n for c in layout for n in c["nodes"]]
    rep.check(flat == list(range(len(CHAIN))), "四栏展平 == 模块链顺序",
              f"{flat}")

    # 相邻两个旋钮的**净空 ≥ 环粗**（v0.34 加，v0.35 判据不变、数变了）。
    #
    # 为什么这条要单独量：旋钮直径**不跟行距走**（见 TranePanel.h 的 `kKnobDia`
    # 注释），于是"会不会黏在一起"是**两个各自独立的决定**碰出来的结果 ——
    # 把直径调大一档、或者给某一栏加一行（行距变小），都会踩到它，而**别的断言
    # 全都照样绿**：行距还在合理范围、字号没变、左右缘也齐平、旋钮也还在轨道正中。
    #
    # 实测撞过两次：v0.34 第二稿直径 24.2px，最挤那栏（STUTTER，行距 29.875）
    # 净空只剩 2.675px —— 渲染出来两个环确实几乎黏在一起；v0.35 直径涨到
    # 26.4px（行距也一起涨到 32.909），净空 6.800px，又回到安全区。
    #
    # 判据是"≥ 环粗"而不是"≥ 0"：两个环之间那道缝如果比环本身还细，读起来
    # 不是"两个控件之间的间隙"，而是"环上的一道瑕疵"（两条环线夹一条细缝，
    # 眼睛会当成三根粗细不匀的线）。
    dia, stroke = geo["knob_dia"]
    outer = dia + stroke
    knob_set = set(geo["knobs"])
    tightest: tuple[float, int, float] | None = None
    for c in layout:
        ids = row_ids(c, geo)
        for a, b in zip(ids, ids[1:]):
            if a in knob_set and b in knob_set:
                clr = c["pitch"] - outer
                if tightest is None or clr < tightest[0]:
                    tightest = (clr, c["index"], c["pitch"])
    assert tightest is not None, \
        "四栏里没有相邻的两个旋钮 —— 这条断言会空转（旋钮被挪散了？）"
    clr, ci, pitch = tightest
    rep.check(clr >= stroke, "相邻旋钮的净空 ≥ 环粗",
              f"最挤：栏 {ci} 行距 {pitch:.3f} − 外径 {outer:.3f} = {clr:.3f}px"
              f"（要 ≥ 环粗 {stroke:.3f}）")

    # ---- 顶栏品牌标（v0.36）----
    #
    # 这一段要自己渲一张图来量，所以临时目录在这里就建好
    # （原来它建在下面"三套状态"之前；挪上来只是为了让这一段能用它）。
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_render_"))
    #
    # 这一段盯的是一个**全新的、静默的**失效模式：素材读不到时
    # `drawBrandMark()` 第一行就 return，顶栏右上角什么都不画，面板其余部分
    # 一切正常 —— 没有断言会红、也没有东西会崩，界面上只是少了一块。
    # 反向对照见 `tools/check_logo_mutations.py`（四处突变）。
    #
    # 两条判据分工不同，**不能合并**：
    #
    #   ① 「自述矩形非退化 + 里面有墨」抓"画没画"。
    #      矩形宽高塌到 0（几何常量没了，或素材没读到）→ 红。
    #
    #   ② 「像素右缘 == 参数区右缘」抓"画在哪儿"。
    #      **只写 ① 是不够的**：`logo` 行是从常量算出来的，品牌标挪到哪儿
    #      它就跟着报到哪儿 —— 两边一起动。所以 ① 在"品牌标整个挪到左上角"
    #      时**照样绿**，而渲染出来一眼就看得出不对。
    #      ② 比的是**像素**与 `pane`（另一条独立常量）：一个动一个不动，才会分叉。
    #      这条正是 `check_logo_mutations.py` 的 M2 存在的理由。
    print("\n[顶栏品牌标]")
    lx, ly, lw, lh, srcw, srch = geo["logo"]
    rep.check(lw >= 40.0 and lh >= 40.0, "自述矩形非退化",
              f"{lw:.1f} × {lh:.1f}（塌到 0 = 几何常量没了，或素材没读到）")
    # 宽高比必须**来自资产**（`logo` 行末两格是源尺寸）。写死两个数的话，
    # 换一张资产就有一边对不上，而画出来只是"有点扁"，没有任何东西会红。
    rep.check(abs(lw / lh - srcw / srch) <= 0.01, "logo: 宽高比 == 资产的宽高比",
              f"画出来 {lw:.2f}/{lh:.2f} = {lw / lh:.4f}，"
              f"资产 {int(srcw)}×{int(srch)} = {srcw / srch:.4f}")
    if lw >= 40.0 and lh >= 40.0:
        png = tmp / "logo.png"
        render("default", args.scale, png)
        img = np.asarray(Image.open(png).convert("RGB"))
        S = args.scale
        # 先夹到画布内再取子图：品牌标被挪到左缘外时矩形会带负坐标，
        # 直接切片会切出**空数组**，于是覆盖率算出 `nan%` —— 那条照样报红，
        # 但报出来的是"nan%"而不是"矩形在画布外"，读的人要猜。
        x0p = max(0, int(round(lx * S)))
        x1p = min(img.shape[1], int(round((lx + lw) * S)))
        y0p = max(0, int(round(ly * S)))
        y1p = min(img.shape[0], int(round((ly + lh) * S)))
        sub = img[y0p:y1p, x0p:x1p]
        if sub.size == 0:
            rep.bad("logo: 自述矩形里真的有墨（且左右两半都有）",
                    f"自述矩形 [{lx:.1f},{ly:.1f} {lw:.1f}×{lh:.1f}] "
                    f"整个落在画布外（品牌标被挪出去了）")
        else:
            ink = sub.max(axis=2) > 40
            cov = float(ink.mean())
            half = ink.shape[1] // 2
            left_has, right_has = bool(ink[:, :half].any()), bool(ink[:, half:].any())
            rep.check(cov >= 0.03 and left_has and right_has,
                      "logo: 自述矩形里真的有墨（且左右两半都有）",
                      f"墨迹覆盖 {cov:.1%}（≥ 3%）；左半 {'有' if left_has else '无'} / "
                      f"右半 {'有' if right_has else '无'} —— 覆盖为 0 = 素材读不到，"
                      f"顶栏右上角静默少一块")
        # 纵向不许压到模块框上（基准是 `--dump-layout` 的框顶，独立于 logo 行）。
        block_top = min(b["top"] for b in blocks)
        rep.check(ly + lh <= block_top + 0.5, "logo: 不侵入参数区",
                  f"底边 {ly + lh:.1f} ≤ 模块框顶 {block_top:.1f}"
                  f"（压上去 = 品牌标盖住第一个模块框的框线）")
        # ② 像素右缘 == 参数区右缘。
        # 只在**参数区右半边**找墨 —— 顶栏左边是分段控件，不排掉会量到它们。
        band = img[int(34 * S):int(round(block_top * S)), :]
        xm = int(round((geo["pane"][0] + geo["pane"][1] * 0.5) * S))
        xs = np.where((band[:, xm:].max(axis=2) > 40).any(axis=0))[0]
        if xs.size == 0:
            rep.bad("logo: 右缘 == 参数区右缘", "参数区右半边一个墨点都没有")
        else:
            got = (xm + int(xs.max()) + 1) / S
            want = geo["pane"][0] + geo["pane"][1]
            rep.check(abs(got - want) <= 2.0, "logo: 右缘 == 参数区右缘",
                      f"像素右缘 {got:.1f} vs 参数区右缘 {want:.1f}"
                      f"（偏差 {abs(got - want):.2f}px ≤ 2；基准是 `pane`，"
                      f"不是自述的 logo 行 —— 两边一起动就抓不到挪位）")

    results: dict[str, dict] = {}

    # 三套状态。**default 才是真的出厂状态**（七个开关全 false）。
    for state, desc in (("default", "出厂状态（只有 SPACE / OUT 亮）"),
                        ("all", "全开（七个开关全 true）"),
                        ("demo", "演示状态（链的前两级 + RUIN）")):
        png = tmp / f"{state}.png"
        st = render(state, args.scale, png)
        print(f"\n[{state}] {desc}   亮 {st['lit_n']} 个模块"
              f"（{' '.join(st['lit'])}），{st['cols']} 栏，显示 {st['shown']} 个参数")
        results[state] = check_state(state, st, args.scale, png, geo, rep, layout, gap, padx, blocks)
        if args.outdir:
            out = pathlib.Path(args.outdir)
            out.mkdir(parents=True, exist_ok=True)
            # 版本号取自**编译产物**（`kUiVersion` → geometryDump 的 ui_version），
            # 不写死 —— 写死过，结果是 outputs/ 里那批图的文件名说了谎。
            ver = args.version or geo["ui_version"]
            dest = out / f"Trane_panel_v{ver}_{state}.png"
            Image.open(png).save(dest)
            print(f"  → {dest}")

    print("\n[颜色 —— 所有状态都不允许出现彩色]")
    for state in results:
        n = results[state]["accent"]
        rep.check(n == 0, f"{state}: 没有彩色像素",
                  f"{n} 个像素（面板不再使用彩色；蓝色漏出说明有装饰性绘制）")

    # **交互态也必须没有强调色 —— 这条是补一个真实的漏检。**
    #
    # 上面那个循环只渲染 default / all / demo，而这三者的 hover / press 都是空的。
    # 于是"把 hover 行底改成 kAccent"这种突变一路绿过去 ——
    # 唯一的彩色被当装饰用了，检查器却看不见。**绿本身不是证据。**
    #
    # 这里把每一类可交互区域都悬停 / 按下一次再量。**并且带正向对照**：
    # 先断言"这个交互态真的改到了像素"，再断言"改完还是没有强调色"。
    # 少了正向对照，一个写错的 --hover 会让交互态渲染退化成普通态，
    # 于是强调色断言在**什么都没交互**的图上轻松通过 —— 那是空转。
    #
    # v0.33 把清单从 10 条收到 6 条：模式格 / 列数格 / 分割线三类住户没了。
    # **每一条都同时跑 check_state** —— 于是"hover 不许改几何"这条规矩
    # （小绪：「鼠标移上去要缓慢发光，而不是突然高亮」的另一面：
    # 发光是颜色的事，几何一动就是"跳"）自动被上面那组排版断言盯着：
    # 交互态里四栏的行数、首末齐平、左右齐平一样要成立。
    print("\n[颜色 · 交互态 —— hover / press 同样不许出现]")
    INTERACT = [
        ((), "--hover", "ctl:grain_spray", "hover 参数行"),
        ((), "--hover", "ctl:grain_on",    "hover 模块标题行"),
        ((), "--hover", "tab:1",           "hover 落位格"),
        ((), "--hover", "bgslot",          "hover 选择图片格"),
        ((), "--hover", "bgbright",        "hover 明暗度轨道"),
        ((), "--press", "ctl:grain_spray", "press 参数行"),
        ((), "--press", "ctl:grain_on",    "press 模块标题行"),
        ((), "--press", "tab:1",           "press 落位格"),
    ]
    assert len(INTERACT) >= 6, "交互态覆盖不足，这条检查会空转"

    bases: dict[tuple, np.ndarray] = {}
    for ctx, *_ in INTERACT:
        if ctx in bases:
            continue
        key = "_".join(ctx).replace("-", "") or "all"
        png = tmp / f"i_base_{key}.png"
        render("all", args.scale, png, *ctx)
        bases[ctx] = np.asarray(Image.open(png).convert("L"), np.float32)

    for n, (ctx, flag, spec, desc) in enumerate(INTERACT):
        png = tmp / f"i{n}_{flag.strip('-')}_{spec.replace(':', '_')}.png"
        st = render("all", args.scale, png, *ctx, flag, spec)   # render() 已断言交互态生效
        img = np.asarray(Image.open(png).convert("L"), np.float32)
        moved = int((np.abs(img - bases[ctx]) > 0).sum())
        rep.check(moved >= 200, f"{desc}: 交互态真的画出来了",
                  f"{moved} 个像素与无交互时不同（≥ 200；0 = 这个交互态没生效，"
                  f"下面那条强调色断言是在量一张普通图）")
        r = check_state(f"interact {desc}", st, args.scale, png, geo, rep, layout,
                       gap, padx, blocks)
        n_acc = r["accent"]
        rep.check(n_acc == 0, f"{desc}: 没有强调色",
                  f"{n_acc} 个像素（交互反馈只能用墨色透明度，面板不再使用彩色）")

    # 出厂 / 全开 / 演示三张里，`all` 是"什么都在动"的那张 —— 交互态、淡入、
    # 背景这几节都拿它当**基准图**（`base` = 不带任何交互、不带背景的那张）。
    # v0.33 把它从第 6 节提到这里：淡入那一节要在时间轴上和它逐像素比。
    base = np.asarray(Image.open(tmp / "all.png").convert("L"), np.float32)

    # ---- 5b · hover 是**渐入**的，不是突然亮的（v0.33）----
    #
    # 小绪：「所有交互都要有质感，比如我鼠标移动到某一个参数上，是会**缓慢发光
    # 高亮**的，而不是突然高亮」。
    #
    # 上面那一组交互态断言只能证明「有反馈」，证明不了「反馈是渐入的」——
    # 一条突然亮起的反馈和一条 160ms 淡入的反馈，在**静止图**上完全一样。
    # 要证明渐入，必须在**时间轴上取点**。
    #
    # 三个点，各抓一种错法：
    #   t=0      → 与「什么都没悬停」**逐像素相同**
    #              （抓「进场起点不是 0」—— 比如把 prev 初始化成 cur，
    #                于是指针刚进去就有一半亮度）
    #   t=0.16s  → 与「完全悬停」**逐像素相同**（抓「永远到不了 1」）
    #   t=0.08s  → 亮度**超过一半**（缓动后 0.875）
    #              ← **这一条是本节的核心**：线性缓动在 t=0.5 恰好给 0.5，
    #                ease-in 给得更少 —— 两者都会让「缓慢发光」变成「起步迟钝」。
    #                没有它，把 easeOutCubic 换成 `return t` 也全绿。
    #
    # 三条一起才立得住：任何一条单独都能被「直接返回常量」骗过。
    print("\n[交互质感 —— hover 是渐入的，不是突然亮的]")
    hov_spec = "ctl:grain_spray"

    def hover_shot(t, name):
        png = tmp / f"fade_{name}.png"
        extra = ["--hover", hov_spec] + ([] if t is None else ["--hover-t", str(t)])
        st_ = render("all", args.scale, png, *extra)
        return st_, np.asarray(Image.open(png).convert("L"), np.float32)

    st_t0, img_t0 = hover_shot(0.0, "t0")
    st_t1, img_t1 = hover_shot(0.16, "t1")
    st_th, img_th = hover_shot(0.08, "thalf")
    st_df, img_df = hover_shot(None, "default")

    # ① 自述的相位：时间 → 进度必须是线性的（kHoverFade = 0.16 s）
    rep.check(st_t0["hover_lin"] == 0.0, "fade: t=0 时进度为 0",
              f"自述 {st_t0['hover_lin']:.4f}")
    rep.check(abs(st_th["hover_lin"] - 0.5) <= 1e-4, "fade: t=0.08s 时进度为一半",
              f"自述 {st_th['hover_lin']:.4f}（kHoverFade = 0.16 s，0.08 正好半程；"
              f"偏了就说明时间→进度的换算是错的）")
    rep.check(st_t1["hover_lin"] == 1.0, "fade: t=0.16s 时进度已满",
              f"自述 {st_t1['hover_lin']:.4f}")
    # ② 缓动真的施加了：半程的**亮度**必须显著大于一半
    rep.check(abs(st_th["hover_amt"] - 0.875) <= 1e-3,
              "fade: 半程亮度是 0.875（ease-out，不是线性）",
              f"自述 {st_th['hover_amt']:.4f}（1-(1-0.5)³ = 0.875；"
              f"线性会给 0.5、ease-in 更少 —— 那两种都是「起步迟钝」）")
    rep.check(st_df["hover_lin"] == 1.0 and st_df["hover_amt"] == 1.0,
              "fade: 不给 --hover-t 就是动画已完成",
              f"自述 {st_df['hover_lin']:.4f} / {st_df['hover_amt']:.4f}"
              f"（老命令行不受淡入影响）")

    # ③ 像素：t=0 必须与「完全没悬停」逐像素相同
    d0 = np.abs(img_t0 - base)
    rep.check(d0.max() <= 0, "fade: t=0 时面板与无悬停逐像素相同",
              f"最大差 {d0.max():.0f}（进场起点必须是 0，"
              f"否则指针刚进去就有一截亮度 —— 那就是「突然高亮」）")
    # ④ 像素：t=0.16 必须与「完全悬停」逐像素相同
    d1 = np.abs(img_t1 - img_df)
    rep.check(d1.max() <= 0, "fade: t=0.16s 与完全悬停逐像素相同",
              f"最大差 {d1.max():.0f}（淡入必须真的走到 1，不能停在半路）")

    # ⑤ 像素：半程的**亮度增量**必须是全程的一个可预测比例
    #
    # 用「与无悬停的差」而不是绝对亮度：行的底、参数名、轨道都在同一行里，
    # 绝对亮度量到的是它们混在一起的结果。差值只留下**随 hover 变的那部分**，
    # 掩膜再取「全亮时有明显改变」的像素 —— 于是量的就是那一条发光带本身。
    #
    # **符号**：反馈色是 kInk（0xffebebf5，浅色），铺在近黑的底色上，
    # 所以 hover 是**提亮**不是压暗 —— 差值取 `hover - 无悬停` 才是正的。
    # 反了的话掩膜圈到 0 个像素，这条断言会以"量不出比例"报错（实测踩过）。
    #
    # 判据用**比值**而不是绝对像素差：绝对差会随门槛 / 底色漂移，
    # 而「半程亮度 = 全程的 87.5%」是缓动曲线本身的性质，机器快慢无关。
    d_full_px = img_df - img_t0          # 正 = 全亮时提亮了多少
    d_half_px = img_th - img_t0
    band = d_full_px > 2.0
    n_band = int(band.sum())
    # 这条是下面两条比例断言的**前提**，所以它自己也必须是一条正式断言 ——
    # 写成裸 `assert` 的话，前提不成立时检查器会**崩在异常里**，
    # 报告上只剩一句"退出码非 0"，看不出是哪一条判据守住的。
    # （实测：M2「淡入瞬时完成」就是这么崩的，反向对照拿不到干净证据。）
    rep.check(n_band >= 5000, "fade: 发光带能圈出来（比例断言的前提）",
              f"圈到 {n_band} 个像素（≥ 5000；太少说明 hover 根本没提亮任何东西）")
    if n_band:
        ratio = float(d_half_px[band].sum()) / float(d_full_px[band].sum())
        rep.check(ratio > 0.5, "fade: 半程的亮度超过全程的一半（缓动是 ease-out）",
                  f"半程 / 全程 = {ratio:.3f}（> 0.5；线性会给 0.5，ease-in 更小。"
                  f"理论值 0.875）")
        rep.check(ratio < 0.99, "fade: 半程确实还没到全程（真的是渐入）",
                  f"半程 / 全程 = {ratio:.3f}（< 0.99；接近 1.0 = 淡入被写成了瞬时）")

    # ⑥ 指针什么都没指的时候，反馈强度必须是 **0**
    #
    # 这条守的是 `of()` 开头那个早退（`if (!m.any()) return 0.0f;`）。
    # 少了它，`cur` 为空（= 什么都没指）时会等于"每一个空标记"，
    # 于是**面板上所有行一起亮起来** —— 而且静态图上看起来就像"设计成这样的"，
    # 靠眼睛根本看不出来。上面那几条时间轴断言也全都量不到它
    # （它们都比的是"有悬停"和"没悬停"两张图，两张都一起亮的话差值是 0）。
    st_none = render("all", args.scale, tmp / "fade_none.png")
    rep.check(st_none["hover"] == "none" and st_none["hover_amt"] == 0.0,
              "fade: 什么都没指时反馈强度为 0",
              f"自述 {st_none['hover']!r} / {st_none['hover_amt']:.4f}"
              f"（空的标记必须恒返回 0，否则所有行会一起亮）")

    # 聚焦态：焦点机制仍然保留给键盘导航，但**不再画蓝色聚焦环**。
    # 这正是本次 dogfood 反馈：调参数时不要出现蓝框；焦点是输入语义，不是装饰。
    png = tmp / "focus.png"
    st = render("all", args.scale, png, "--focus", "grain_spray")
    r = check_state("focus", st, args.scale, png, geo, rep, layout, gap, padx, blocks)
    n = int(r["acc_mask"].sum())
    rep.check(n == 0, "focus: 聚焦态没有强调色",
              f"{n} 个像素（聚焦只保留键盘语义，不再绘制蓝框）")

    # ---- 6 · v0.33：这一段（模式 / 列数 / 分割线真的改变版面）整段删除 ----
    #
    # 它量的三件事——`--count` 改列数、`--mode` 换版面、`--divider` 推走参数区——
    # 全都没有住户了。**删掉而不是改成"恒定"**：留一句 `rep.check(True, ...)`
    # 会让报告里多一条永远绿的"版面切换"断言，读报告的人会以为它还管着什么。
    #
    # 版面不变这件事现在由上面那条「四栏正好填满参数区」+ `check_state` 里的
    # 逐行齐平来守 —— 那两条是**在真的图上**量的，比"探针说 4 列"结实。
    #
    # `base`（基准图）在 5b 那节的开头已经取好了。

    # ---- 7 · 性能 ----
    print("\n[性能]")
    ms, rebuild = render_frames(args.scale, tmp / "perf.png")
    rep.check(rebuild <= REBUILD_BUDGET_MS, "背景重烤在预算内",
              f"{rebuild:.2f} ms / 次（门槛 {REBUILD_BUDGET_MS:.0f} ms；实测 0.6–0.8 ms）")
    rep.check(ms <= FRAME_BUDGET_MS, "每帧耗时在预算内",
              f"{ms:.2f} ms / 帧（门槛 {FRAME_BUDGET_MS:.0f} ms，"
              f"30Hz 需要 {ms * 3:.1f}% 单核；实测 4.3 ms）")

    # ---- 8 · 背景图（用户自己上传的那张）----
    #
    # 这一节量的是"用户选的图有没有画到该画的地方、有没有盖住文字、拖起来卡不卡"。
    # 全部走 `--bg`，也就是**和插件完全相同的那条路径**（图作为 PanelState 的
    # 一个字段传进去），不是事后在 PNG 上合成。
    print("\n[背景图 —— 用户自己上传的那张]")
    S = args.scale
    test_bg = tmp / "test_backdrop.png"
    make_test_backdrop(test_bg)

    # v0.33：落位区只剩一个（`bg_region`），它就是参数区本身 ——
    # 树删了，"树区落位"没有意义。**`--bg-where` 的值域也从 off|tree|params
    # 收成 off|full**，写老值会当场报错。
    region_x, region_w = geo["bg_region"]
    pane_x, pane_w = geo["pane"]
    peak = geo["bg_bright"][2] * geo["bg_bright"][1]   # kBgPeakBase × kBgBrightMax

    def render_bg(name: str, where: str, bright: float):
        png = tmp / f"bg_{name}.png"
        st = render("all", S, png, "--bg", str(test_bg),
                    "--bg-where", where, "--bg-bright", str(bright))
        return st, np.asarray(Image.open(png).convert("L"), np.float32)

    ys = slice(int(100 * S), int(640 * S))          # 顶栏之下、底边之上

    # ① 落位 = 关：**画布内容**与完全不带背景逐像素相同。
    #    顶栏那一格会显示文件名（那是有意的 —— 用户得看见自己选了什么），
    #    所以从 y = 70 往下比。
    st_off, img_off = render_bg("off", "off", 1.0)
    rep.check(st_off["bg_on"] == "off", "bg: 落位=关的自述一致",
              f"探针说 bg_on = {st_off['bg_on']}")
    d_off = np.abs(img_off - base)[int(70 * S):, :]
    rep.check(d_off.max() <= 0, "bg: 落位=关时画布上没有任何背景",
              f"最大差 {d_off.max():.0f}（顶栏那格显示文件名是有意的，只比 y≥70）")

    # ② 落位 = 全屏：背景必须铺满落位区，而且**一步都不许迈出去**。
    st_par, img_par = render_bg("full", "full", 1.0)
    rep.check(st_par["bg_where"] == "full", "bg: 全屏落位的自述一致",
              f"探针说 {st_par['bg_where']}")
    # 落位区**就是参数区** —— 两个数来自 `--dump-geometry` 的两个不同字段
    # （`pane` 由 geom::kPaneX0/W 算出，`bg_region` 由 bgRegion() 返回）。
    # 拿它们互相对账：bgRegion() 一旦自己另写一套数（算窄了 / 算宽了）就报红。
    #
    # **少了这一条，下面那两条断言会跟着错的那个区域一起缩水。** 落位区被
    # 算窄一半时："内部有像素被改"照样绿（半块里也有改动）、"外面没漏"照样绿
    # （半块外面本来就没画）—— 三条一起失明，而画面上背景只铺了半块参数区。
    # 这正是 v0.33 补它的原因（v0.31 那版 M1 突变"落位搞反"失效之后发现的）。
    rep.check(region_x == pane_x and region_w == pane_w, "bg: 落位区就是参数区",
              f"bg_region {region_x:.0f}..{region_x + region_w:.0f} vs "
              f"pane {pane_x:.0f}..{pane_x + pane_w:.0f}"
              f"（bgRegion() 不许自己另写一套数）")
    # 落位区内部**必须**有像素被改（70px 往里缩，避开四边羽化）
    ax0 = int(round((region_x + 70) * S))
    ax1 = int(round((region_x + region_w - 70) * S))
    inner = np.abs(img_par - base)[ys, ax0:ax1]
    rep.check(inner.mean() > 3.0, "bg: 背景铺满了落位区",
              f"落位区内部平均改变 {inner.mean():.1f}/255（> 3）")
    # 参数区**外面**一个像素都不许变 —— 左右内边距是留白，铺上背景就等于
    # 把面板撑到了边。这条同时挡住"落位算错"和"图溢出画布"。
    #
    # **切的是参数区，不是落位区。** 用落位区切的话，落位区被算宽时"外面"
    # 也跟着变宽（正好把它错铺出去的那一条算进"里面"），这条断言就失明了。
    # 参数区是独立的参照物。
    pane_r = int(round((pane_x + pane_w) * S))
    out_l = np.abs(img_par - base)[:, : int(round(pane_x * S))]
    out_r = np.abs(img_par - base)[:, pane_r:]
    assert out_l.size and out_r.size, (
        "参数区两侧没有留白可量（pane_x 或画布宽变了）—— 这条断言会退化成空转")
    rep.check(out_l.max() <= 0 and out_r.max() <= 0, "bg: 背景没有漏到左右内边距外",
              f"左 {out_l.max():.0f} / 右 {out_r.max():.0f}（都必须是 0；"
              f"参数区 {pane_x:.0f}..{pane_x + pane_w:.0f} 之外是留白）")

    # ③ 明暗度：单调变亮，且峰值不超过设计上限。
    #
    # **用"与不带背景的差值"而不是绝对亮度** —— 参数区里全是 235 的文字，
    # 绝对值的 max 量到的永远是文字，量不到背景。
    # 差值天然把文字剔掉了：文字是不透明的，盖在背景上时差值≈0。
    imgs = {}
    for b in (0.25, 1.0, 2.0, 4.0):
        st_, img_ = render_bg(f"b{b}", "full", b)
        imgs[b] = img_
        rep.check(abs(st_["bg_bright"] - b) < 1e-3, f"bg: 明暗度 {b}× 的自述一致",
                  f"探针说 {st_['bg_bright']}")
    lx0, lx1 = int(round((pane_x + 90) * S)), int(round((pane_x + 460) * S))
    lv = [float((imgs[b] - base)[ys, lx0:lx1].max()) for b in (0.25, 1.0, 2.0, 4.0)]
    rep.check(all(lv[i] < lv[i + 1] for i in range(len(lv) - 1)),
              "bg: 明暗度单调变亮", "峰值 " + " < ".join(f"{v:.0f}" for v in lv))
    rep.check(lv[-1] <= peak + 3.0, "bg: 背景峰值不超过设计上限",
              f"{lv[-1]:.0f}/255（上限 kBgPeakBase×kBgBrightMax = {peak:.0f}；"
              f"参数文字 235 对它的对比度仍有 5.97:1，过 WCAG AA）")
    # 白 / 黑分界必须**正好落在落位区正中**。
    #
    # 这一条替换了 v0.32 的"图的黑色部分没有渗到亮的一半"。原来那条的判据是
    # "右半必须纹丝不动"，v0.33 之后它**永远红**：测试图右半纯黑、面板底也黑，
    # 黑压黑本来就不动 —— 但落位区的右边界也因此失去了可测量的内容
    # （见 make_test_backdrop 的注释）。一条永远红的断言比没有断言更坏：
    # 它会把真正的落位错误淹掉。
    #
    # 换成量**分界线的位置**。守的是同一件事，而且更强：
    # cover 是等比铺满 + 居中裁剪，所以源图的**中列**必须落在落位区的**中线**上。
    # 图被拉变形（非等比缩放）→ 分界线跑掉；居中裁剪写错 → 分界线跑掉。
    # 实测偏差 0.0px（源图 3000 宽、落位区 1360 宽：中列 1500 → 屏幕 720.0）。
    prof = np.abs(imgs[4.0] - base)[ys, :].mean(axis=0)
    lo = int(round((region_x + 50) * S))
    hi = int(round((region_x + region_w - 100) * S))
    seg = prof[lo:hi]
    plateau = float(np.median(prof[int(round((region_x + 100) * S)):
                                   int(round((region_x + 300) * S))]))
    # **前提也要报红，不能用裸 `assert` 抛异常。**
    # 这里原来写的是 `assert plateau > 5.0` —— 前提不成立时它抛异常，
    # 整份报告被一条 traceback 顶掉，读报告的人只看得出"检查器崩了"，
    # 看不出是哪条断言红了。v0.33 跑 M2 反向对照（明暗度方向搞反）时撞上了：
    # 最亮档变成最暗档 → plateau 掉到 0 → 崩在 assert 上，
    # 于是那个突变是"被抓住"的，但方式是错的。**绿本身不是证据，
    # 红的方式也必须是断言在红。**
    rep.check(plateau > 5.0, "bg: 落位区左侧的改动够量分界线",
              f"左侧中位改变 {plateau:.1f}/255（> 5；太小说明图根本没亮起来，"
              f"下面那条「分界在正中」就没有意义了）")
    if plateau > 5.0:
        above = np.where(seg > 0.90 * plateau)[0]
        below = np.where(seg < 0.10 * plateau)[0]
    else:
        above = below = np.array([], dtype=int)
    rep.check(above.size > 0 and below.size > 0, "bg: 白/黑分界能在取样区间里找出来",
              f"亮侧 {above.size} 列 / 暗侧 {below.size} 列（两侧都要有；"
              f"缺一侧说明分界线不在取样区间里）")
    if above.size and below.size:
        edge_x = (lo + int(above[-1]) + lo + int(below[0])) / 2.0 / S
        mid = region_x + region_w / 2.0
        rep.check(abs(edge_x - mid) <= 1.5, "bg: 白/黑分界落在落位区正中（cover 没拉变形）",
                  f"分界在 {edge_x:.1f}，落位区中线 {mid:.1f}"
                  f"（偏差 {abs(edge_x - mid):.2f}px ≤ 1.5）")

    # ④ 背景**不会盖住文字**：图垫在最底层，参数行与顶栏都画在它上面，
    # 最亮档也不例外。取样从 y=70 起到 y=640 止 ——
    # 顶栏的分段控件（34–60）在带外，因为那几格本来就该随背景规格变
    # （文件名 / 选中项）。
    #
    # v0.36：品牌标纵向跨 38..134，所以它的下缘（70..134）**在带内**。
    # 这不影响这条判据 —— 品牌标画在前景、永远压在图上，所以它在 base 与
    # 各档亮度里都在，比值照样成立（实测 2.40% → 2.69%）。写在这里是因为
    # "带内亮像素"这个数从此不全是参数文字，谁要拿它当"文字覆盖率"用会算错。
    ys2 = slice(int(70 * S), int(640 * S))
    px0, px1 = int(round(pane_x * S)), int(round((pane_x + pane_w) * S))
    t_base = float((base[ys2, px0:px1] > 140).mean())
    t_bg = float((imgs[4.0][ys2, px0:px1] > 140).mean())
    rep.check(t_bg >= t_base * 0.98, "bg: 背景没有盖住文字",
              f"参数区亮像素 {t_base:.2%} → {t_bg:.2%}（4.0× 最亮档；"
              f"跌下去就说明图被画到文字上面去了）")

    # ④b 四边羽化：边缘必须是**渐变**，不是台阶。
    # 小绪明确否掉过"卡片 / 边框感"，硬边就是那个感觉。
    # 测试图左半是纯白，所以左缘的差值剖面就是羽化斜坡本身。
    edge = [(imgs[4.0] - base)[ys, int(round((pane_x + dx) * S))].mean()
            for dx in (8, 64)]
    rep.check(edge[0] < 0.5 * edge[1], "bg: 边缘是羽化的（不是硬切）",
              f"距左缘 8px 处改变 {edge[0]:.1f}，64px 处 {edge[1]:.1f}"
              f"（羽化宽 kBgFeather = 64px；两者相等 = 硬边，就是被否掉的卡片感）")

    # ⑤ 像素上的落位范围必须**就是** `--dump-geometry` 的 `bg_region`。
    #
    # v0.33 之前这一段量的是"拖分割线不动背景"（落位是常量 → 不触发重烤）。
    # 分割线删了，那条判据没有住户了。但**它真正想守的东西还在**：
    # 落位必须是编译期常量、必须和几何自述一致。
    # 换一种量法：把"改动的像素"的横向范围找出来，和 `bg_region` 对账。
    # 这条比原来那条更强 —— 原来只证明"拖分割线不影响"，这条证明
    # **像素上的落位区与自述的落位区是同一个**，任何一边改错都会报红。
    d_full = np.abs(imgs[4.0] - base)
    colmax = d_full[ys, :].max(axis=0)
    hit = np.where(colmax > 2.0)[0]
    # 同 ② 那一段的理由：前提不成立时报红，不抛异常。明暗度方向搞反时
    # 4.0× 那一档会被算成 0（图整个变黑），`hit` 是空的 —— 裸 `assert`
    # 会把报告换成一条 traceback。
    rep.check(hit.size > 0, "bg: 全屏落位下横向有像素被改",
              f"{hit.size} 列（> 0；0 = 背景根本没画上，下面那条对账没有意义）")
    if hit.size:
        got_x0, got_x1 = hit.min() / S, hit.max() / S
        # 容差 4px（v0.33 从 2px 放宽到 4px）。**这不是在放宽门槛**：
        # 量的东西变了。四边羽化 64px 是**从落位区边界往里**渐显，最外侧那两三列
        # 的变化量落在 2/255 的探测阈以下，量不到 —— 实测左缘 43.0（自述 40）。
        # 真正证明"右边界在哪儿"的是上面那条白/黑分界，它量的是**图的内容**，
        # 不受羽化影响。这条只负责守"一个像素都不许漏到落位区外"。
        rep.check(abs(got_x0 - region_x) <= 4.0
                  and abs(got_x1 - (region_x + region_w)) <= 4.0,
                  "bg: 像素上的落位 == geometryDump 的 bg_region",
                  f"像素 [{got_x0:.1f} .. {got_x1:.1f}]，自述 "
                  f"[{region_x:.1f} .. {region_x + region_w:.1f}]"
                  f"（容差 4px = 羽化让最外两三列掉到探测阈以下）")

    # ⑥ 冷 / 热两条路的代价
    rep.check("rebuild_ms" in st_par, "bg: 探针吐了冷重烤耗时", "缺了就没法量换图的代价")
    rep.check("tint_ms" in st_par, "bg: 探针吐了热重合成耗时",
              "缺了就没法量拖明暗度的代价")
    rep.check(st_par["rebuild_ms"] <= BG_REBUILD_BUDGET_MS, "bg: 冷重烤在预算内",
              f"{st_par['rebuild_ms']:.2f} ms（门槛 {BG_REBUILD_BUDGET_MS:.0f}；"
              f"5 次取最小，空载实测 21.1–21.5 ms @2× 参数区、3000×3000 源图）")
    rep.check(st_par["tint_ms"] <= BG_TINT_BUDGET_MS, "bg: 拖明暗度的代价在预算内",
              f"{st_par['tint_ms']:.2f} ms / 帧（门槛 {BG_TINT_BUDGET_MS:.0f}；"
              f"5 次取最小，空载实测 1.4 ms @2× 参数区）")
    # **相对判据**才是这条真正靠得住的形式：热路径必须显著便宜于冷路径。
    # 绝对毫秒数会随机器快慢漂移，而"缓存到底有没有生效"是个比值问题 ——
    # 判据失效的话热路径就等于冷路径（比值 1.0），无论机器多快都跑不掉。
    # 实测：空载 0.07，8 个进程抢 CPU 时 0.048–0.119 —— 比值几乎不动，
    # 因为机器快慢在分子分母上约掉了。**这条才是回归探测器。**
    ratio = st_par["tint_ms"] / max(st_par["rebuild_ms"], 1e-6)
    rep.check(ratio <= 0.5, "bg: 热路径确实比冷路径便宜（缓存生效了）",
              f"热 / 冷 = {st_par['tint_ms']:.2f} / {st_par['rebuild_ms']:.2f} "
              f"= {ratio:.2f}（≤ 0.5；接近 1.0 说明每帧都在重做源图缩放。"
              f"空载 0.07、8 份负载 0.048–0.119 都稳）")

    print()
    if rep.failed:
        print(f"\n面板渲染检查失败：{rep.failed} 项")
        return 1
    print("\n面板渲染检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
