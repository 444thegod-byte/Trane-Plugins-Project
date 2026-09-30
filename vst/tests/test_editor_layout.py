"""面板与参数表的机器化检查（v0.30：1440×720 横版，左世界树 + 右参数检查器）。

为什么要有这个文件
==================
用户遇到过一次「Grain 那一组根本没有面板和旋钮」—— 代码能跑、声音也对，
就是界面上没有。DSP 测试和编译期都抓不到这类问题。

v0.17 之后面板不再由 juce::Slider 子控件拼成，而是**自绘 + 自己命中测试**，
唯一的数据源是 `TranePanel.h` 里的 `kControls[48]`。于是"界面上有没有"这个问题
变成了"那张表和 `createLayout()` 对不对得上"。这个文件就是那道对账。

**这不是在测 UI 好不好看** —— 好看没法机器判定。它测的是四类会静默坏掉的东西：

  1. 参数表两边分叉（加了参数忘了上屏，或上屏了但宿主里没有）；
  2. 几何漂移（面板尺寸 / 树的比例 / 参数区预算和设计稿不一致）；
  3. 动线断掉（信号链顺序变了、高亮两档分不开了、ALL 模式的阅读顺序乱了）；
  4. 配色退化（深色语义色被换掉、强调色被挪作装饰用）。

关于"不能空转通过"
==================
这个项目吃过亏：正则匹配不到就 assert，别让循环体一次都不执行还显示绿。
所以下面每个解析器都带条数下限断言 —— 解析器失效必须报红，不许静默跳过。
"""
from __future__ import annotations

import math
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PANEL_H = ROOT / "plugin" / "TranePanel.h"
PANEL_CPP = ROOT / "plugin" / "TranePanel.cpp"
EDITOR_CPP = ROOT / "plugin" / "PluginEditor.cpp"
EDITOR_H = ROOT / "plugin" / "PluginEditor.h"
PROC_CPP = ROOT / "plugin" / "PluginProcessor.cpp"
ENGINE_CPP = ROOT / "core" / "TraneEngine.cpp"
PROBE = ROOT / "build" / "panel_probe_artefacts" / "Release" / "panel_probe"

N_CONTROLS = 48
N_NODES = 10
N_SWITCHES = 7                       # 模块开关走标题行（v0.33：树上的圆心没了）
N_PARAM_ROWS = N_CONTROLS - N_SWITCHES   # 41 个参数行
PANEL_W, PANEL_H_PX = 1440, 720

# v0.33 删掉的常量，记一笔免得以后有人以为漏了：
#   N_SIGNAL_EDGES = N_NODES - 1 —— 9 条信号线随世界树一起删了。
#   N_RING_SLOTS 这个名字也过时了（"ring" 指的是树上那圈质点），改叫 N_PARAM_ROWS。


def read(p: pathlib.Path) -> str:
    assert p.is_file(), f"找不到 {p}"
    return p.read_text(encoding="utf-8")


def strip_comments(src: str) -> str:
    """去掉 // 注释，但不动字符串字面量里的内容。

    直接 split("//") 会砍掉 "gr/s" 这类字面量之外的东西 —— 这个文件里暂时没有，
    但注释里写着 `juce_PathStrokeType.h:60` 这种带斜杠的东西，早晚会踩。
    """
    out = []
    for line in src.splitlines():
        in_str = False
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_str = not in_str
            elif not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


def split_top(s: str) -> list[str]:
    """按顶层逗号切分，忽略 () [] {} 内的逗号。"""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def num(tok: str) -> float:
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)f?", tok.strip())
    assert m, f"不是数字字面量: {tok!r}"
    return float(m.group(1))


def unquote(tok: str) -> str:
    m = re.fullmatch(r'"([^"]*)"', tok.strip())
    assert m, f"不是字符串字面量: {tok!r}"
    return m.group(1)


# ============================================================================
# 解析 PluginProcessor.cpp::createLayout()
# ============================================================================
def parse_param_ids(proc: str) -> dict[str, str]:
    ids = dict(re.findall(r'static constexpr const char\*\s+(\w+)\s*=\s*"([^"]+)";', proc))
    assert len(ids) >= N_CONTROLS, f"只解析出 {len(ids)} 个参数 ID 常量"
    return ids


def _make_unique_calls(src: str):
    """产出 (类名, 实参原文)。括号配平，不能用非贪婪正则 —— 实参里
    有 NR(...) 和 withLabel(...)，非贪婪会在第一个 `)` 就断。"""
    marker = "layout.add(std::make_unique<"
    body = src[src.index("createLayout() {"):]
    i = 0
    while True:
        j = body.find(marker, i)
        if j < 0:
            return
        k = j + len(marker)
        e = body.index(">", k)
        cls = body[k:e].strip()
        p = body.index("(", e)
        depth, q = 0, p
        while True:
            if body[q] == "(":
                depth += 1
            elif body[q] == ")":
                depth -= 1
            q += 1
            if depth == 0:
                break
        yield cls, body[p + 1:q - 1]
        i = q


def parse_create_layout(proc: str) -> dict[str, dict]:
    ids = parse_param_ids(proc)
    out: dict[str, dict] = {}
    for cls, raw in _make_unique_calls(proc):
        args = split_top(raw)
        m = re.fullmatch(r"pid\(ParamIDs::(\w+)\)", args[0].strip())
        assert m, f"第一个实参不是 pid(ParamIDs::x): {args[0]!r}"
        pid = ids[m.group(1)]
        name = unquote(args[1])
        rec = {"kind": cls, "name": name}

        if cls == "BoolParam":
            assert len(args) == 3, f"{pid}: BoolParam 参数个数 {len(args)}"
            assert args[2].strip() in ("false", "true"), args[2]
            rec.update(lo=0.0, hi=1.0, skew=1.0,
                       default=1.0 if args[2].strip() == "true" else 0.0)
        elif cls == "FloatParam":
            mm = re.fullmatch(r"NR\(([^)]*)\)", args[2].strip())
            assert mm, f"{pid}: 第三个实参不是 NR(...): {args[2]!r}"
            parts = [p.strip() for p in mm.group(1).split(",")]
            assert len(parts) in (3, 4), f"{pid}: NR 参数个数 {len(parts)}"
            rec.update(lo=num(parts[0]), hi=num(parts[1]),
                       skew=num(parts[3]) if len(parts) == 4 else 1.0,
                       default=num(args[3]))
        elif cls == "juce::AudioParameterChoice":
            # 档位参数：lo/hi/skew 没有意义（宿主给的是 [0, 档数-1]），
            # 只核对默认档位下标。硬塞成 0/1 会变成假断言。
            rec.update(lo=0.0, hi=float(len(re.findall(r'"[^"]*"', args[2])) - 1),
                       skew=1.0, default=num(args[3]))
        else:
            pytest.fail(f"{pid}: 不认识的参数类型 {cls} —— 测试需要跟着更新")

        assert pid not in out, f"参数 ID 重复: {pid}"
        out[pid] = rec

    assert len(out) >= N_CONTROLS, f"只解析出 {len(out)} 个参数"
    return out


# ============================================================================
# 解析 TranePanel.h 的 kControls / geom / kNodes
# ============================================================================
ROW = (r'\{\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,'
       r'\s*Fmt::(\w+)\s*,\s*(-?[\d.]+)f\s*,\s*(-?[\d.]+)f\s*,\s*(-?[\d.]+)f\s*,\s*(-?[\d.]+)f\s*\}')


def parse_kcontrols(panel_h: str) -> list[dict]:
    src = strip_comments(panel_h)
    block = re.search(r"inline constexpr ControlSpec kControls\[\]\s*=\s*\{(.*?)\n\};", src, re.S)
    assert block, "找不到 kControls 表"
    rows = re.findall(ROW, block.group(1))
    assert len(rows) >= N_CONTROLS, f"只解析出 {len(rows)} 条控件，正则可能失效了"
    out = []
    for module, pid, name, label, unit, fmt, lo, hi, skew, default in rows:
        out.append({"module": module, "id": pid, "name": name, "label": label,
                    "unit": unit, "fmt": fmt,
                    "lo": float(lo), "hi": float(hi), "skew": float(skew),
                    "default": float(default)})
    return out


def parse_geom(panel_h: str) -> dict[str, float]:
    """把 namespace geom 里的常量算出来。

    kColSpacing = kRingR / 0.341f 这种是**推导式**，不能只抓字面量 ——
    抓字面量就等于把设计稿的比值抄进测试里，改了比值测试还绿。
    """
    src = strip_comments(panel_h)
    block = re.search(r"namespace geom \{(.*?)\n\}", src, re.S)
    assert block, "找不到 namespace geom"
    ns: dict[str, float] = {"__builtins__": {}}
    found = 0
    # 一行可能声明多个常量，所以先按顶层逗号切开再逐个算 ——
    # 直接 `([^;]+);` 会把两个声明连成算不出来的东西。
    for m in re.finditer(r"inline constexpr (?:float|int)\s+([^;]+);", block.group(1)):
        for decl in split_top(m.group(1)):
            if "=" not in decl:
                continue
            name, _, expr = decl.partition("=")
            name, expr = name.strip(), expr.strip()
            expr = re.sub(r"(\d)f\b", r"\1", expr)   # 0.341f -> 0.341
            # **把换行和续行缩进压成单个空格再 eval。** 一条常量可以写好几行
            # （`kBgGroupW = a + b\n + c + d` 就是），换行留在表达式里会让
            # eval 报 IndentationError —— 而报出来的样子像"源码有语法错"，
            # 实际上源码好好的，是这个解析器不够结实。
            expr = " ".join(expr.split())
            try:
                ns[name] = eval(expr, ns)            # noqa: S307 —— 只 eval 本仓库源码里的算式
            except Exception as e:                    # pragma: no cover
                pytest.fail(f"算不出 geom::{name} = {expr!r}: {e}")
            found += 1
    assert found >= 20, f"只解析出 {found} 个 geom 常量"
    return ns


def parse_nodes(panel_h: str) -> list[dict]:
    """解析 kNodes 表。

    v0.33 把这张表从 5 个字段收到 3 个：`column`（左/中/右柱）与 `ratio`
    （纵向八等分）只服务于世界树的几何，树删了就没有读者了。
    **正则也要跟着收** —— 留着 `[\\d.]+f` 那两段的话，它匹配不到任何一行，
    而 `assert len(rows) == N_NODES` 会报"kNodes 有 0 条"，看起来像表被删了。
    """
    src = strip_comments(panel_h)
    block = re.search(r"inline constexpr NodeSpec kNodes\[\]\s*=\s*\{(.*?)\n\};", src, re.S)
    assert block, "找不到 kNodes 表"
    rows = re.findall(r'\{"(\w+)"\s*,\s*"(\w+)"\s*,\s*"([^"]+)"\}', block.group(1))
    assert len(rows) == N_NODES, f"kNodes 有 {len(rows)} 条，期望 {N_NODES}"
    return [{"sephira": a, "module": b, "title": c} for a, b, c in rows]


# v0.33 删掉了 `parse_index_pairs`（解析 `PathSpec` 表用的）。
# 它唯一的住户是"9 条信号边是 kNodes 的相邻对"——信号线删了，
# `PathSpec` / `kSignalEdges` 两个类型也一起没了，所以这个解析器没有输入了。


# ============================================================================
# 夹具
# ============================================================================
@pytest.fixture(scope="module")
def panel_h() -> str:
    return read(PANEL_H)


@pytest.fixture(scope="module")
def controls(panel_h) -> list[dict]:
    return parse_kcontrols(panel_h)


@pytest.fixture(scope="module")
def params() -> dict[str, dict]:
    return parse_create_layout(read(PROC_CPP))


@pytest.fixture(scope="module")
def geom(panel_h) -> dict[str, float]:
    return parse_geom(panel_h)


@pytest.fixture(scope="module")
def nodes(panel_h) -> list[dict]:
    return parse_nodes(panel_h)


@pytest.fixture(scope="module")
def dump() -> str:
    """面板自述 —— 由**编译出来的** panel_probe 吐出，不是解析源码。"""
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先构建 panel_probe）")
    r = subprocess.run([str(PROBE), "--dump-geometry"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip(), "geometryDump 是空的"
    return r.stdout


# ============================================================================
# 一 · 控制表 ↔ createLayout()
# ============================================================================
def test_control_table_has_exactly_48_rows(controls):
    assert len(controls) == N_CONTROLS, f"kControls 有 {len(controls)} 条，期望 {N_CONTROLS}"


def test_every_control_id_exists_in_the_host_and_vice_versa(controls, params):
    """两边必须**互为子集** —— 少一个方向都会出问题：

      · 表里有、宿主没有  → 界面上有个控件，拖了没反应（用户会以为坏了）；
      · 宿主有、表里没有  → 参数在 Ableton 的映射列表里，但界面上根本调不到。
    """
    in_table = {c["id"] for c in controls}
    in_host = set(params)
    missing_host = sorted(in_table - in_host)
    missing_ui = sorted(in_host - in_table)
    assert not missing_host, f"面板上有、宿主里没有的参数: {missing_host}"
    assert not missing_ui, f"宿主里有、面板上没上屏的参数（用户调不到）: {missing_ui}"


def test_control_ranges_match_create_layout(controls, params):
    """下界/上界/曲线/默认值逐条对账。

    曲线最容易写错 —— JUCE 的 NormalisableRange::convertTo0to1 是
    `pow(proportion, skew)`（juce_NormalisableRange.h:147），不是 1/skew。
    早前把 skew 写反过，结果轨道长度全错但界面看起来"有在动"。
    """
    bad = []
    for c in controls:
        p = params[c["id"]]
        if p["kind"] == "BoolParam":
            continue                      # 开关：只有 0/1，下面单独测
        if p["kind"] == "juce::AudioParameterChoice":
            if abs(c["default"] - p["default"]) > 1e-6:
                bad.append(f'{c["id"]}: 默认档 {c["default"]} != {p["default"]}')
            continue
        for k in ("lo", "hi", "skew", "default"):
            if abs(c[k] - p[k]) > 1e-4:
                bad.append(f'{c["id"]}.{k}: 表里 {c[k]} != createLayout {p[k]}')
    assert not bad, "控制表与 createLayout 分叉:\n  " + "\n  ".join(bad)


def test_switches_are_exactly_the_seven_module_toggles(controls):
    """短名为空串 = 模块开关。v0.30 里它走**模块标题行**（和树上的圆心）。

    必须正好 7 个，而且必须是七个 `*_on` / `freeze` 布尔参数 —— 否则标题行会去读
    一个连续参数，开关永远停在"关"（或者永远"开"）。
    """
    switches = [c["id"] for c in controls if c["label"] == ""]
    assert len(switches) == N_SWITCHES, f"开关有 {len(switches)} 个，期望 {N_SWITCHES}: {switches}"
    assert len(switches) == len(set(switches)), f"开关 ID 重复: {switches}"
    for sid in switches:
        assert sid == "freeze" or sid.endswith("_on"), f"{sid} 看起来不是模块开关"


def test_param_rows_plus_switches_is_48(controls):
    """48 个控件 = 41 个参数行 + 7 个模块开关，一条不重不漏。

    v0.33 之前这条叫 `..._ring_slots_...`（"ring" 指的是树上那圈质点）。
    树删了，名字改掉 —— 留着一个叫 "ring" 的测试会让人以为树还在。
    判据没变：有短名的就是参数行，没短名的就是开关。
    """
    rows = [c for c in controls if c["label"] != ""]
    assert len(rows) == N_PARAM_ROWS, f"参数行 {len(rows)} 个，期望 {N_PARAM_ROWS}"
    assert len(rows) + N_SWITCHES == N_CONTROLS


def test_parameter_display_names_are_unique(params):
    """参数**显示名**必须唯一。

    宿主按名字查找参数只认第一个，出现两个 "Mix" 会让端到端验收静默跳过
    那一段（不是报错，是"没测到"）。这条曾经真的踩到过。
    """
    names = [p["name"] for p in params.values()]
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, f"参数显示名重复，宿主里没法区分: {dup}"


def test_control_table_display_names_match_the_host(controls, params):
    bad = [f'{c["id"]}: 表里 "{c["name"]}" != 宿主 "{params[c["id"]]["name"]}"'
           for c in controls if c["name"] != params[c["id"]]["name"]]
    assert not bad, "显示名分叉:\n  " + "\n  ".join(bad)


def test_table_is_grouped_in_node_order(controls, nodes):
    """kControls 必须严格按 kNodes 的顺序分块 —— 检查器线性走一遍就能把控件
    分配到十个模块上，不需要额外映射表。C++ 里也有 static_assert 盯着，
    这里再独立算一次（static_assert 挂了编译就过不去，测试也就跑不起来，
    所以这条实际是在防"顺序对了但模块名拼错"）。"""
    order = [n["module"] for n in nodes]
    seen: list[str] = []
    for c in controls:
        if not seen or seen[-1] != c["module"]:
            seen.append(c["module"])
    assert seen == order, f"kControls 的模块分块顺序 {seen} != kNodes 的 {order}"


# ============================================================================
# 二 · 几何（源码常量）
# ============================================================================
def test_panel_is_1440_by_720(geom):
    assert geom["kBaseW"] == PANEL_W
    assert geom["kBaseH"] == PANEL_H_PX
    # 宽高比锁死 2:1 —— 自由拉伸会把圆拉成椭圆
    assert abs(PANEL_W / PANEL_H_PX - 2.0) < 1e-9


def test_pane_budget_adds_up(geom):
    """参数区的三笔预算必须由别的常量推导出来，不能是另写的字面量 ——
    另写就会出现"改了内边距、参数区宽度没动"的错位。

    v0.33 之前这条还带着分割线那三项（`kDividerX0 / Min / Max`）与"拖到最右
    每列还剩多少"的推算。分割线删了，参数区的左缘就是 `kPanePad` ——
    **判据本身没变**（还是"预算必须推导出来"），变的是它的住户。
    """
    assert abs(geom["kPaneX0"] - geom["kPanePad"]) < 1e-6, \
        f'kPaneX0 {geom["kPaneX0"]} != kPanePad（左右对称内边距）'
    assert abs(geom["kPaneW"] - (geom["kBaseW"] - 2.0 * geom["kPanePad"])) < 1e-6, \
        f'kPaneW {geom["kPaneW"]} != kBaseW - 2 × kPanePad'
    assert abs(geom["kAvailH"] - (geom["kBaseH"] - geom["kRowsTop"] - geom["kRowsBottomPad"])) < 1e-6, \
        f'kAvailH {geom["kAvailH"]} != kBaseH - kRowsTop - kRowsBottomPad'

    # 四栏里最挤的一栏（3 个模块、14 行）也必须有地方放：
    # 参数区减去三条栏距、再四等分，每列不能窄到放不下名字 + 轨道 + 数值。
    per_col = (geom["kPaneW"] - geom["kColGap"] * 3) / 4.0
    assert per_col >= 150.0, f"每列只剩 {per_col:.0f}px，排版会崩"


# ---------------------------------------------------------------------------
# v0.33 删掉了这一节里的五条**树几何**断言，记一笔免得以后有人以为漏了：
#
#   test_tree_geometry_is_derived_from_two_ratios   —— kRingR / kColSpacing / kTreeH
#   test_node_centres_are_recomputed_from_the_ratios —— 十个质点圆的坐标
#   test_circles_never_overlap                       —— 圆两两不相交
#   test_signal_highlight_tiers_cannot_be_confused    —— 信号两档四端的排序
#   test_the_tree_vertical_axis_is_the_signal_axis    —— 树的纵轴就是信号轴
#
# 小绪的决定是「完全删掉，参数铺满整块面板」：世界树、22 条骨架点线、
# 9 条信号线、十个质点圆一起没了。**这些断言没有住户了，所以删掉而不是改松** ——
# 改松（比如把 kRingR 的推导式换成一句 `assert True`）会让报告里多五条永远绿的
# "树几何"断言，读报告的人会以为树还在被守着。
#
# 它们原来守的东西没有丢：信号顺序现在由「四栏展平 == 模块链顺序」守着
# （`--dump-layout` 的 `nodes` 字段，见 check_panel_render.py），
# 而那比"圆的 y 单调不减"更直接 —— 它量的是**用户真正读到的那张表**。
# ---------------------------------------------------------------------------


# ============================================================================
# 三 · 动线（信号链）
# ============================================================================
#
# v0.33 删掉了这一节原来的四条断言（信号边是 kNodes 的相邻对 / 树的纵轴就是
# 信号轴 / MODULE 候选集是连续切片 / …）—— 信号线、世界树、MODE 全没了。
#
# 但这一节**没有整节删掉**，因为"阅读顺序 = 信号顺序"这条设计意图还活着，
# 而且现在只剩一种版面可以守它 —— 四栏。判据从"某一种版面"升级成
# "**唯一的那种版面**"：以前 MODE 切错了还有 ALL 当对照组，现在没有退路了。
def parse_lanes(panel_cpp: str) -> list[list[int]]:
    """解析 `TranePanel.cpp` 里的 `kAllLanes` —— 四栏各自的模块下标（-1 补齐）。"""
    src = strip_comments(panel_cpp)
    block = re.search(r"constexpr int kAllLanes\[\]\[kMaxNodesPerColumn\]\s*=\s*\{(.*?)\};",
                      src, re.S)
    assert block, "找不到 kAllLanes"
    return [[int(x) for x in re.findall(r"-?\d+", row) if int(x) >= 0]
            for row in re.findall(r"\{([^{}]*)\}", block.group(1))]


def test_four_columns_read_in_signal_order(panel_h, nodes):
    """四栏**展平后必须等于 kNodes 的顺序** —— 于是"从左到右、从上到下"的
    阅读顺序就是信号顺序。

    v0.33 之前这条叫 `test_all_mode_lanes_read_in_signal_order`，量的是
    ALL 模式那 3 列（3+3+4）。MODE 删掉之后只剩一种版面，而它就是四栏。

    常量在 `TranePanel.cpp` 的匿名命名空间里（实现细节，不进头文件），
    所以这里读 .cpp。C++ 侧有 `static_assert(laneFlattensInOrder())` 盯着；
    这里从源码再独立读一遍，防的是"static_assert 和解析器同时看错"。
    """
    lanes = parse_lanes(read(PANEL_CPP))
    assert len(lanes) == 4, f"应为 4 栏，实际 {len(lanes)}"
    flat = [i for lane in lanes for i in lane]
    assert flat == list(range(len(nodes))), \
        f"四栏的展平顺序 {flat} != kNodes 的顺序 {list(range(len(nodes)))}"

    src = strip_comments(read(PANEL_CPP))
    lens = re.search(r"constexpr int kAllLaneLen\[\]\s*=\s*\{([^}]*)\}", src)
    assert lens, "找不到 kAllLaneLen"
    want = [len(lane) for lane in lanes]
    assert [int(x) for x in re.findall(r"\d+", lens.group(1))] == want, \
        f"kAllLaneLen 和 kAllLanes 对不上（{lens.group(1)} vs {want}）"

    # 每栏至少 2 个模块。1 个模块的栏会把整块高度摊给两三行，留出一大片空白 ——
    # 实测 2 模块的栏就已经要靠"每栏各自解行距"才能把底部填满了。
    assert all(n >= 2 for n in want), f"有栏只有 1 个模块: {want}"


def test_every_column_is_a_contiguous_chain_slice(nodes):
    """每栏必须是链上的**一段连续切片**，栏内不许跳号。

    展平相等其实已经蕴含了这一点，但那条断言失败时只会说"顺序不对"，
    说不出**是哪一栏**把链切断了。这条把"连续"单独拎出来 —— 它才是
    "阅读顺序 = 信号顺序"这个设计意图的直接表达。
    """
    for i, lane in enumerate(parse_lanes(read(PANEL_CPP))):
        assert lane == list(range(lane[0], lane[0] + len(lane))), \
            f"栏 {i} 不是连续切片: {lane}"


# ============================================================================
# 四 · 几何（编译出来的面板自述）
# ============================================================================
def test_dump_reports_48_controls_41_params_7_switches(dump):
    """自述里的每一行都要在，而且**计数要自洽**。

    v0.33 把 `ring_slots` 改成了 `param_rows`（"ring" 指的是树上那圈质点，
    树删了），`signal_edges` 整行删了（信号线没了）。**自述行和功能是一件事**：
    留着 `signal_edges 0` 会让读报告的人以为信号线还在、只是暗着。
    """
    assert f"controls {N_CONTROLS}" in dump, dump
    assert f"param_rows {N_PARAM_ROWS}" in dump, dump
    assert f"switches {N_SWITCHES}" in dump, dump
    assert f"panel {PANEL_W} {PANEL_H_PX}" in dump, dump
    assert "signal_edges" not in dump, \
        "自述里还有 signal_edges —— 信号线删了，这行会让检查器以为它在量动线"


def test_dump_module_rows_match_the_source_constants(dump, controls, nodes):
    """自述里每个模块的**参数行数**，必须和源码表独立算出来的一致。

    这条是"图是画对了、代码是另一回事"的防线：dump 来自编译产物，
    期望值来自 Python 重新读 `kControls`，两条路只在设计稿上汇合。

    v0.33 之前这条还比对**圆心坐标**（`node` 行的第 3/4 段）。树删了，
    `node` 行也改名成 `mod`，现在只剩四段：**序号** / 名字 / 模块 / 行数 ——
    所以这条从"圆心对账"变成"行数对账"，判据没松：行数错一位，
    界面上就少一行 / 多一行，而其它检查全是绿的。

    v0.35 把那个**序号**显式吐了出来（原来是靠行序隐含的）。于是下面这段
    `zip(lines, nodes)` 里的顺序只是"顺便" —— 真正对账的是序号本身，
    行序错了也会当场报红。**能吐出来的东西不要靠约定。**
    """
    order = [n["module"] for n in nodes]
    want = {m: sum(1 for c in controls if c["module"] == m and c["label"] != "")
            for m in order}

    lines = [l for l in dump.splitlines() if l.startswith("mod ")]
    assert len(lines) == N_NODES, f"dump 里有 {len(lines)} 个模块，期望 {N_NODES}"

    for i, (line, n) in enumerate(zip(lines, nodes)):
        parts = line.split()
        # **格式前置断言**：`mod` 行的形状变了要在这里报，而不是掉进
        # `int(parts[1])` 抛一个看不出是格式问题的 ValueError。
        assert len(parts) == 5 and parts[1].isdigit(), (
            f"`mod` 行格式变了（期望 `mod <序号> <质点> <模块> <行数>`）：{line!r}")
        assert int(parts[1]) == i, f"第 {i} 行的节点序号写的是 {parts[1]}"
        assert parts[2] == n["sephira"], f"模块顺序不一致: {parts[2]} != {n['sephira']}"
        assert parts[3] == n["module"], f"{n['sephira']} 的模块名 {parts[3]} != {n['module']}"
        assert int(parts[4]) == want[n["module"]], (
            f"{n['module']}: dump 说 {parts[4]} 个参数行，控制表算出来 "
            f"{want[n['module']]} 个")


def test_dump_param_row_counts_match_the_control_table(dump, controls, nodes):
    """每个模块的参数行数 = 它在 kControls 里非空短名的条数（汇总到总数）。

    这条抓的是"加了参数但没给行位"—— 那种情况下控件会被静默丢掉，
    界面上少一行，而所有其他检查都是绿的。
    """
    order = [n["module"] for n in nodes]
    want = {m: sum(1 for c in controls if c["module"] == m and c["label"] != "") for m in order}
    assert sum(want.values()) == N_PARAM_ROWS, \
        f"控制表算出的参数行合计 {sum(want.values())} != {N_PARAM_ROWS}"

    # ctl 行：每个控件都必须被分到某个模块的某个槽位（开关是 -1）
    # 行的格式是 `ctl <id> <node> <slot> <短名>`；短名为空时行尾没有第 5 段，
    # 所以不能直接取 parts[4]。
    ctl = [l for l in dump.splitlines() if l.startswith("ctl ")]
    assert len(ctl) == N_CONTROLS, f"dump 里只有 {len(ctl)} 条 ctl"
    for line in ctl:
        parts = line.split()
        slot = int(parts[3])
        label = parts[4] if len(parts) > 4 else ""
        assert -1 <= slot < max(want.values()), f"{parts[1]} 的槽位号越界: {slot}"
        assert (slot == -1) == (label == ""), f"{parts[1]} 的槽位与短名不自洽: {line!r}"


# ============================================================================
# 五 · 视觉约定（颜色 / 字体 / 窗口 / 底图）
# ============================================================================
def test_accent_is_reserved_but_never_drawn(panel_h):
    """systemBlue token 可以保留作平台语义对照，但面板绘制不得使用它。

    用户反馈调参数时不应出现蓝框；焦点仍用于键盘导航，不再由彩色边框表达。
    旧配色一个字节都不许留：v0.17 深红、v0.18 蒂芙尼蓝 / 深青芯。
    """
    low = strip_comments(panel_h).lower()
    assert "0xff0a84ff" in low, "缺少 systemBlue 对照 token"
    assert low.count("kaccent") == 1, "kAccent 不应被面板绘制调用"
    for old, why in (("8e1f1f", "v0.17 的深红"),
                     ("0xff0abab5", "v0.18 的蒂芙尼蓝"),
                     ("0xff00938f", "v0.18 的深青芯")):
        assert old not in low, f"代码里还留着 {why} {old}"


def test_no_saturated_colour_except_the_accent(panel_h):
    """除强调色之外，所有颜色常量的**彩度必须接近 0**。

    Apple 的深色语义色都不是数学上的纯灰 —— label #EBEBF5 有 10 的蓝偏、
    systemGray2 #636366 有 3 —— 但它们都在 16 以内，是"微冷的中性色"。
    systemBlue #0A84FF 的彩度是 245，是面板上**唯一**的彩色。

    这条挡的是"有人在面板里塞一个彩色常量"—— 那会让面板从"系统的深色"
    变成"某人配的色"，而截图上看只是"哪里怪怪的"。
    """
    src = strip_comments(panel_h).lower()
    hexes = set(re.findall(r"0xff([0-9a-f]{6})", src))
    assert len(hexes) >= 4, f"只找到 {len(hexes)} 个颜色常量"
    coloured = []
    for h in sorted(hexes):
        rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if rgb == (10, 132, 255):      # kAccent = systemBlue(dark)
            continue
        chroma = max(rgb) - min(rgb)
        if chroma > 16:
            coloured.append((("#" + h), chroma))
    assert not coloured, f"除强调色 #0A84FF 之外还有彩色常量：{coloured}"


def test_dark_semantic_background_and_label(panel_h):
    """深色语义色必须留在 Apple 的 token 上，不能变成"某人配的深色"。

    v0.33 去掉了 `secondarySystemBackground #1C1C1E` 这一条 —— 它的住户是
    **灭掉的质点圆**（树删了，圆没了）。**断言跟着住户走**：留一句
    `assert "0xff1c1c1e" in low` 会逼着以后的人在头文件里养一个没人用的颜色，
    而那个颜色只要在，就随时可能被谁抓去当装饰。
    """
    low = strip_comments(panel_h).lower()
    assert "0xff000000" in low, "面板底必须是 systemBackground #000000"
    assert "0xffebebf5" in low, "文字基色必须是 label #EBEBF5"
    assert "0xff636366" in low, "分段控件选中块必须是 systemGray2 #636366"
    assert "0xff1c1c1e" not in low, (
        "还留着 secondarySystemBackground #1C1C1E —— 它的住户（灭掉的质点圆）"
        "随世界树删了，没有住户的颜色常量只会被拿去当装饰")
    for old, why in (("0xfffafaf9", "v0.18 的纸色"), ("0xff0e0e0f", "v0.18 的墨色")):
        assert old not in low, f"还留着 {why} {old}"


def test_panel_fonts_are_bundled_and_no_longer_borrowed_from_ableton():
    """面板字体必须来自**打包文件**，源码里不许再出现 Ableton 的字体路径。

    来路（v0.35 反向改写）：v0.34 及以前是"读用户已装 Ableton 12 的
    `AbletonSans-Bold.otf`，读不到就降级 Helvetica Neue **Bold**"。实测那
    两条路的竖干差 23%（Ableton Bold 35.68 / Helvetica Neue Bold 43.86）——
    于是"用户装没装 Ableton"会**整档改变面板标题的字重**，而当时没有任何
    断言能发现。用户要求"字体用 Lux Cache 同款"，而 Lux Cache 用的
    Suisse Neue 是商业字体（EULA 禁止再分发），所以改成打包最接近的
    OFL 替代（Inter 的静态实例，见 `assets/fonts/PROVENANCE.md`）。

    **这条断言的方向跟着功能一起反了过来。** 它现在钉的是"那条运行时光滑
    降级的老路真的断了" —— 比"正向检查它读了打包字体"更要紧：只要
    `AbletonSans` 又回到源码里，就说明有人把老路接回去了，而老路一旦回来，
    字重就会随用户机器漂移，且没有任何东西会报红。

    检查前**去注释**：注释里大段记录着这段历史（"旧路径是读 AbletonSans…"），
    那是资产，不该被这条断言赶走。它管的是**代码**。

    正向那一半（面板真的在用这两个打包字重、度量对得上 ttf）在
    `test_ui_design.py` 的 §8 —— 那边能拿 fontTools 直接量文件。
    """
    src = strip_comments(read(PANEL_CPP))
    for gone, why in (("AbletonSans", "Ableton Sans 字体文件名"),
                      ("/Applications/Ableton", "Ableton 安装路径"),
                      ("Helvetica Neue", "Helvetica Neue 降级字体"),
                      ("loadInstalledAbletonFont", "运行时读 Ableton 目录的函数")):
        assert gone not in src, (
            f"源码里还有 {why} `{gone}` —— 字体已经改成打包内嵌，"
            f"这条「看用户机器上装了什么」的降级路子必须整条断掉"
            f"（它会让字重随机器漂移，且没有任何断言能发现）")
    assert "BinaryData::TraneSans_SemiBold_ttf" in src, "面板字重必须来自打包数据"
    assert "BinaryData::TraneSans_Regular_ttf" in src, "数据字重必须来自打包数据"
    assert "createSystemTypefaceFor" in src, \
        "打包字体要经 createSystemTypefaceFor 建成 Typeface，不是丢给系统字体名"


def test_editor_locks_the_aspect_ratio_and_has_no_child_widgets():
    """窗口锁死 1440:720 = 2:1，而且编辑器里**一个子控件都没有**。

    子控件会让"自绘 + 自己命中测试"变成两套坐标系，v0.10 的网格版面就是这么乱的。
    锁定宽高比则是因为**排版是按这块画布解出来的**：四栏的列宽、每栏各自的行距、
    三档字号，全都是"给定 1360×574 之后解出来的数"。自由拉伸会把它们全部拉歪 ——
    而歪一点点（比如行距变成 39.7）肉眼根本看不出来。

    v0.33 之前这条的理由写的是"自由拉伸会把圆拉成椭圆"（树上的质点圆）。
    树删了，但**锁定宽高比这条规矩没有跟着删**，所以理由要换成上面那个 ——
    留着旧理由会让人以为"圆没了，那这条可以松了"。
    """
    src = read(EDITOR_CPP)
    assert "setFixedAspectRatio" in src, "没有锁宽高比"
    assert "setResizeLimits" in src, "没有设缩放上下限"
    assert "addAndMakeVisible" not in src, "编辑器里不该有子控件（面板是全自绘的）"
    assert "startTimerHz" in src, "没有定时器就没有呼吸/闪烁"
    assert "cache_.release()" in src, "编辑器不可见时要放掉底图缓存"


def test_editor_wires_every_interactive_region():
    """每一类可交互区域都不能少接。

    "画了但点不着"和"根本没画"在截图上一模一样 —— 只有源码能区分。

    v0.33 把清单从 5 类收到 3 类：`Kind::Divider`（分割线拖拽）、
    `Kind::TabMode`（ALL / MODULE）、`Kind::TabCount`（列数）随树一起删了；
    `Kind::Node`（树上的圆心）改成 `Kind::TabBg`（背景落位段），
    因为模块开关现在只剩**标题行**一条路。
    """
    src = strip_comments(read(EDITOR_CPP))
    for kind, why in (("Kind::TabBg", "背景落位段（关 / 全屏）"),
                      ("Kind::Control", "参数行"),
                      ("Kind::BgSlot", "选择图片格"),
                      ("Kind::BgBright", "明暗度轨道")):
        assert kind in src, f"编辑器里没有处理 {kind}（{why}）"
    # 反向：删掉的那三类不许再出现在编辑器里 —— 留着分支等于留着一片死代码，
    # 而它会让人以为"分割线还能拖，只是没画出来"。
    for gone in ("Kind::Divider", "Kind::TabMode", "Kind::TabCount", "Kind::Node"):
        assert gone not in src, f"编辑器里还有 {gone} 的分支 —— 那个住户已经删了"
    assert "keyPressed" in src, "没有键盘焦点导航，focus 状态就是摆设"
    assert "state_.hoverFade" in src, "没有维护 hover 状态（v0.33 起是淡入结构体）"
    assert "state_.press" in src, "没有维护 press 状态"


# ---------------------------------------------------------------------------
# 点击层：**真的跑一遍命中测试**，不是"源码里出现过这个字符串"
# ---------------------------------------------------------------------------
def hit(spec: str, *flags: str) -> dict:
    """跑一次命中测试自述（`panel_probe --hit`）。

    走的是**编译出来的**探针，和插件用的是同一份 `hitTest` / `mark()`。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先构建 panel_probe）")
    r = subprocess.run([str(PROBE), "--hit", spec, "--state", "default", *flags],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith(("hit_", "mark_")):
            out[parts[0]] = " ".join(parts[1:])
    assert "hit_kind" in out, f"--hit {spec} 没吐出结果:\n{r.stdout}"
    return out


def test_top_bar_hit_test_is_actually_exercised():
    """补一个真踩过的坑：**点击层原先只有文本匹配的"覆盖"。**

    上一版给标签页加了一个「双击闸」，而 JUCE 的 `getNumberOfClicks()` 是
    **累加**的（连点 = 2、3、4…），于是高频点击被整片吃掉 —— 表现就是
    「MODULE 标签点不开」。当时这个文件里唯一的"覆盖"是
    `assert "Kind::TabMode" in src`：那是文本匹配，把逻辑改坏了它照样绿。

    现在改成真的把点算出来、喂给 hitTest、断言结果。
    v0.33 删掉了模式段与列数段，但**这套办法留着** —— 它现在守的是顶栏上
    剩下的三个控件（落位段两格 + 选择图片格 + 明暗度轨道）。
    """
    # 落位段两格各命中各的 —— "半格算错"是最经典的错法。
    assert hit("tab:0")["hit_kind"] == "TabBg"
    assert hit("tab:0")["hit_option"] == "0"
    assert hit("tab:1")["hit_kind"] == "TabBg"
    assert hit("tab:1")["hit_option"] == "1", "全屏那一格命不中 = 点不开"

    # 其余可交互区域一条都不能少。
    assert hit("bgslot")["hit_kind"] == "BgSlot"
    assert hit("bgbright")["hit_kind"] == "BgBright"
    assert hit("ctl:grain_spray")["hit_kind"] == "Control"
    assert hit("outside")["hit_kind"] == "None", "面板外不该命中任何东西"

    # 删掉的旧写法必须**当场失效**，不能静默命中别的格子。
    # `tab:2:1` 是三段写法（老的分组段），`tab:0:0` 是同一个坑的另一种写法 ——
    # 它们现在 parts.size() != 2，必须落到 unknown。
    for gone in ("divider", "node:tape", "tab:2:1", "tab:0:0"):
        assert hit(gone)["hit_kind"] == "unknown", \
            f"{gone} 这个规格已经删了，却还命中了 —— 静默接受会读到错的格子"


def test_parameter_row_mark_carries_only_its_control():
    """参数行的 hover / press 标记**只许带 control**，别的位一个都不许有。

    带上的话，"指针在参数行上"会被顶栏那几格读成"指针在我这儿"，
    于是拖参数时选择图片格 / 明暗度轨道跟着一起亮 —— 看起来就是闪烁。

    坑的难处在**它坏在 `mark()` 里而不是 `hitTest` 里**：只测 hitTest 抓不到，
    所以这里断言的是 `mark_*` 那一组。

    v0.33 之前这条叫 `..._carries_no_node`（那时多出来的是"树上的模块号"）。
    字段换了（`node` → `tab` / `option` / `bgSlot` / `bgBright`），
    **判据没换**：参数行的标记只能有一个维度。
    """
    h = hit("ctl:grain_spray")
    assert h["hit_kind"] == "Control"
    assert h["mark_control"] == h["hit_control"], "参数行的标记没带上控件"
    for field, want, why in (("mark_tab", "-1", "顶栏落位组"),
                             ("mark_option", "-1", "组内格号"),
                             ("mark_bg_slot", "0", "选择图片格"),
                             ("mark_bg_bright", "0", "明暗度轨道")):
        assert h[field] == want, (
            f"参数行的标记带上了 {field}（{why}）—— 拖参数时那个控件会跟着亮")


def test_top_bar_marks_stay_in_their_own_group():
    """顶栏那三个控件的标记不许串台。

    串台的后果是"点明暗度却改了落位"这类错 —— 画面上完全看不出来，
    只有拖下去才发现。

    v0.33 之前这条列的是三组九格（模式 / 列数 / 落位）。前两组删了，
    **剩下的这一组判据不变**，只是格数从 3 收到 2。
    """
    h = hit("tab:0")
    assert h["mark_tab"] == "0" and h["mark_option"] == "0", h
    assert h["mark_bg_slot"] == "0" and h["mark_bg_bright"] == "0", \
        "落位格串到了「选择图片」/ 明暗度的标志位上"
    h = hit("tab:1")
    assert h["mark_tab"] == "0" and h["mark_option"] == "1", h

    # 「选择图片」和明暗度轨道各有自己的标志位，不许混用 tab / option。
    h = hit("bgslot")
    assert h["mark_bg_slot"] == "1" and h["mark_tab"] == "-1" and h["mark_option"] == "-1", h
    h = hit("bgbright")
    assert h["mark_bg_bright"] == "1" and h["mark_tab"] == "-1", h
    assert h["mark_bg_slot"] == "0", "明暗度轨道串到了「选择图片」的标志位上"


# ---------------------------------------------------------------------------
# 点击判定：按下 → 松手 → 到底触发没有
#
# 这一节是**补一个真实事故**的。原先 `hit()` 那批测试只喂 `hitTest` / `mark()`，
# 而"这一下算不算数"的判定住在 PluginEditor::mouseUp 里 —— 离线探针够不着。
# 于是有一个 Bug 在两个会话里都没被抓住：
#
#     按下时把 `option + 1` 存进一个 `pressTab_`，松手时又拿它减 1 当**组号**，
#     一个整数同时当两个维度。点 MODULE（模式段 option 1）算出来的组号是 1，
#     而组号 1 的判据是"必须是列数段" → 条件永远不成立 → **MODULE 标签点不开**。
#     同一根因还废掉了列数段的 1/3/4 格与背景落位段的关/树两格：9 格只有 3 格能点。
#
# 现在判定搬进了面板层（`resolveBarClick`），编辑器与探针跑的是同一份代码，
# 所以下面这些断言绿了，插件里就是对的。
# ---------------------------------------------------------------------------
def click(press: str, release: str | None = None, *flags: str) -> dict:
    """跑一次点击判定自述（`panel_probe --click`）。"""
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先构建 panel_probe）")
    argv = [str(PROBE), "--click", press, "--state", "default", *flags]
    if release is not None:
        argv += ["--release", release]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("click_"):
            out[parts[0]] = " ".join(parts[1:])
    assert "click_fired" in out, f"--click {press} 没吐出结果:\n{r.stdout}"
    return out


def test_every_top_bar_cell_actually_fires():
    """顶栏落位段**每一格都必须点得动**，而且点出来的是它自己那一格。

    这条如果只写"其中一格能点"，是抓不到根因的 —— 原 Bug 下恰好有一格能用，
    只测它会绿。必须把每一格都列出来，才能把"某一格被组判据吃掉"钉死。

    v0.33 之前这里有 9 格（模式 2 + 列数 4 + 落位 3）。前两组删了，
    落位段从 3 格收到 2 格（树区没了）—— **每一格都列出来**这条做法没变。
    """
    for i in range(2):
        c = click(f"tab:{i}")
        assert c["click_fired"] == "1", f"落位段第 {i + 1} 格点不开"
        assert (c["click_group"], c["click_option"]) == ("BgWhere", str(i)), c


def test_click_is_cancelled_when_the_pointer_leaves_the_cell():
    """按下又滑走 = 取消。四条取消路径都要真的取消。

    少了这条，"什么都算触发"的写法也能让上面那条测试全绿。
    """
    # ① 松手落在**别的控件**上
    assert click("tab:0", "bgbright")["click_fired"] == "0"
    # ② 松手落在**同组的别的格**上
    assert click("tab:0", "tab:1")["click_fired"] == "0"
    # ③ 中间拖动过（越过拖拽阈值）
    assert click("tab:1", None, "--click-moved")["click_fired"] == "0"
    # ④ 按的根本不是顶栏（参数行 / 空白处）
    assert click("ctl:grain_spray")["click_fired"] == "0"
    assert click("outside")["click_fired"] == "0"


# ---------------------------------------------------------------------------
# v0.33 删掉了 `test_module_mode_actually_enables_the_count_cells`。
#
# 它守的是"列数段在 ALL 模式下是**禁用**的，不是无条件可点"—— 那是模式与列数
# 两段之间的**边界**。两段都删了，顶栏上剩下的三个控件（选择图片 / 落位两格 /
# 明暗度）**没有禁用态**，都是无条件可交互的。所以这条没有住户了。
#
# 注意不能改成"落位段两格都无条件可点" —— 那和上面那条
# `test_every_top_bar_cell_actually_fires` 是同一件事，写两遍只会让报告里
# 多一条永远和它同生共死的断言。
# ---------------------------------------------------------------------------


def test_panel_layer_does_not_depend_on_juce_audio_processors(panel_h):
    """面板层必须只依赖 juce_gui_basics。

    这条不是洁癖：正因为面板不碰 juce_audio_processors，才能用一个几十行的
    控制台程序（panel_probe）把它离线渲染成 PNG 并做像素检查 —— 界面从此和
    DSP 一样可以机器验证。加一个 AudioProcessor 相关的 include 就会让
    panel_probe 编不过。
    """
    assert "juce_gui_basics" in panel_h
    assert "juce_audio_processors" not in strip_comments(panel_h)
    assert "juce_audio_processors" not in strip_comments(read(PANEL_CPP))


def test_backdrop_bakes_only_the_static_layer():
    """静态底图里只许放**永远不动的那两层**：面板底 + 背景图。

    顶栏会随选中 / hover 变、参数行会随 hover 变 —— 它们进缓存的话，
    淡入就冻住了（而且看起来"只是动画慢"）。这条挡的就是"图省事全烤进去"。

    v0.33 之前这条的正面判据是"必须有 drawGridLines"（22 条骨架点线）。
    骨架删了，**正面判据换成"必须把图贴上去"** —— 少了正面那一半，
    这条会退化成"函数体里什么都没有"也能过（而那时背景功能根本没接上）。
    """
    src = strip_comments(read(PANEL_CPP))
    m = re.search(r"void rebuildBackdrop\(PanelCache&[^)]*\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "找不到 rebuildBackdrop"
    body = m.group(1)
    # 正面：两层都得在
    assert "kBg" in body, "重烤背景时没有铺面板底"
    assert "drawImage(cache.bdScaled" in body, "重烤背景时没有把背景图贴上去"
    # 反面：会动的那几层一件都不许进来
    #
    # v0.36：`drawHeading` 随"删掉 Trane / 41 CONTROLS、顶栏改画 logo"一起没了。
    # 顶上来的 `drawBrandMark` **不随状态变**（品牌标只随设备缩放变），
    # 所以它进底图不会冻住淡入 —— 但它照样不该进来，理由是**底图的定义**：
    # 底图只有"面板底 + 背景图"这两层，而品牌标属于顶栏那一层（和 drawTabs 同层）。
    for fn, why in (("drawTabs", "顶栏会随选中 / hover 变"),
                    ("drawBrandMark", "品牌标属于顶栏层，不是'面板底 + 背景图'"),
                    ("drawInspector", "检查器会随 hover 变"),
                    ("drawParamRow", "参数行会随 hover 变"),
                    ("drawModuleHead", "模块标题行会随 hover 变"),
                    ("drawSegmented", "分段块会随选中变")):
        assert fn not in body, f"{fn} 不该进静态底图（{why}）"


def test_panel_layer_never_touches_the_filesystem():
    """背景图必须**作为数据**传进面板层；面板层自己绝不许读文件。

    这条是"离线渲染的输入 = PanelState"的直接推论：`panel_probe` 把面板渲染成
    PNG 做像素检查，前提是它的输入**完整地**只有一个 `PanelState`。面板层一旦
    自己去读文件，"这一帧画的是什么"就取决于磁盘上的东西 —— 像素检查当场失去
    意义（同一份 PanelState 在另一台机器上会画出别的图）。

    v0.31 加"用户自己上传背景图"的时候，图走的就是
    `PanelState::Backdrop::image` 这个**数据**字段：谁读文件？`PluginEditor`。
    它本来就在宿主进程里，读文件是它的本职。这条断言是那条分界线的护栏。
    """
    for f in (PANEL_H, PANEL_CPP):
        src = strip_comments(read(f))
        for name in ("juce::File", "ImageFileFormat", "loadFrom", "FileChooser",
                     "ImageCache", "FileInputStream"):
            assert name not in src, (
                f"{f.name} 里出现了 {name} —— 面板层不许碰文件系统。"
                "背景图只能从 PanelState::Backdrop::image 传进来")

    # **正向对照**：编辑器那边必须有读文件那几行。
    # 少了这一半，上面那半条断言在一个"谁都没读文件"的死版本上也会通过 ——
    # 那时候背景功能根本没接上，而测试全绿。
    editor = strip_comments(read(EDITOR_CPP))
    for name in ("FileChooser", "ImageFileFormat::loadFrom"):
        assert name in editor, (
            f"PluginEditor.cpp 里没有 {name} —— 读背景图是编辑器的职责，"
            "缺了它上面那条断言就是在给一个死功能背书")


def test_background_region_is_a_compile_time_constant():
    """背景落位区必须是**编译期常量** —— 不许从任何运行时状态推。

    这条是量出来的：落位跟着状态走的话，每变一次都要把源图重新高质量缩放一次，
    3000×3000 的源图在 2× 屏幕上实测 **21.1 ms/帧**（5 次取最小），拖起来必卡；
    而背景四边有 64px 羽化，落位差几十像素根本看不出来。

    v0.33 之前这条叫 `..._do_not_follow_the_divider` —— 当时的变化源是分割线。
    分割线删了，但**判据本身没变**，而且现在更强：`bgRegion()` 必须**无参**。
    带一个参数就意味着将来有人能从调用点把落位算出来。
    """
    src = strip_comments(read(PANEL_CPP))
    m = re.search(r"Rectangle<float> bgRegion\(([^)]*)\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "找不到 bgRegion"
    params, body = m.group(1), m.group(2)
    assert params.strip() == "", (
        f"bgRegion 开始吃参数了（{params.strip()}）—— 落位会跟着运行时状态变")
    for bad in ("st.", "divider", "PanelState"):
        assert bad not in body, (
            f"bgRegion 用到了 {bad} —— 落位不再是常量，改一次就要重烤一次源图")
    for k in ("kPaneX0", "kPaneW", "kBaseH"):
        assert k in body, f"bgRegion 里没有 {k}"


def test_background_peak_keeps_text_above_wcag_aa(geom):
    """背景最亮档的峰值必须让参数文字仍然过 WCAG AA（4.5:1）。

    `kBgPeakBase` 是**量出来的**（世界树骨架点线的 p99 = 22，见 geom 那节的注释），
    上限 4.0× 是**推出来的**：峰值 88 对文字 235 是 5.97:1。这条断言就是那个推导 ——
    以后谁想抬上限，先过这里。
    """
    def rel_lum(v: float) -> float:            # v: 0–255 的 sRGB 灰阶
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    peak = geom["kBgPeakBase"] * geom["kBgBrightMax"]
    text = 235.0                                # kInk #EBEBF5 的绿分量（三通道里最低）
    ratio = (rel_lum(text) + 0.05) / (rel_lum(peak) + 0.05)
    assert ratio >= 4.5, (
        f"背景峰值 {peak:.0f} 对文字 {text:.0f} 只有 {ratio:.2f}:1，过不了 WCAG AA")
    assert ratio >= 5.5, (
        f"余量太小（{ratio:.2f}:1）—— 实测 5.97:1，门槛留 5.5")


def test_background_controls_fit_in_the_top_bar(geom):
    """顶栏那一组背景控件（选择图片 + 落位两格 + 明暗度轨道 + 读数）
    必须整体对齐参数区左缘、而且不越出参数区右缘。

    v0.33 之前这条叫 `..._never_collide_with_the_tabs`，量的是"夹在模式组与
    列数组之间，两边各留 8px"。那两组删了，顶栏上只剩这一组 ——
    判据从"两边都留得下"变成"**它自己的四件必须首尾相接、并且落在参数区之内**"。

    为什么要首尾相接：少算一个 `kBgGap` 就会有两件叠在一起，而叠起来的样子
    看起来只是"这两个控件挨得有点近"，肉眼几乎发现不了。
    """
    gx, gw = geom["kBgGroupX"], geom["kBgGroupW"]
    assert abs(gw - (geom["kBgCellW"] + geom["kBgGap"] + geom["kBgSegW"] + geom["kBgGap"]
                     + geom["kBgTrackW"] + geom["kBgGap"] + geom["kBgReadW"])) < 0.01, \
        "组宽和四件 + 三个间隙对不上"

    # 左缘对齐参数区左缘 —— 于是顶栏第一格和第一栏的第一行左缘在同一条竖线上。
    assert abs(gx - geom["kPaneX0"]) < 0.01, (
        f"背景组左缘 {gx:.0f} 没有对齐参数区左缘 {geom['kPaneX0']:.0f}"
        "（顶栏第一格该和第一栏左对齐）")
    assert gw <= geom["kPaneW"], \
        f"背景组宽 {gw:.0f} 超过了参数区宽 {geom['kPaneW']:.0f}"

    # 四件必须首尾相接 —— 少一个间隙就会有两件叠在一起。
    assert abs(geom["kBgTrackX"] - (gx + geom["kBgCellW"] + geom["kBgGap"]
                                    + geom["kBgSegW"] + geom["kBgGap"])) < 0.01, \
        "明暗度轨道的左缘和前面三件 + 两个间隙对不上"
    assert abs(geom["kBgReadX"] - (geom["kBgTrackX"] + geom["kBgTrackW"] + geom["kBgGap"])) < 0.01, \
        "倍率读数的左缘和轨道 + 一个间隙对不上"


def test_backdrop_is_drawn_under_every_text_layer():
    """背景图必须画在**所有文字之下**，明暗度也必须在那之后乘。

    参数行 / 模块标题 / 顶栏都在 backdrop 之上 —— 图一旦压上去，文字就没了。
    这条用**顺序断言**而不是像素断言：像素上"文字被盖住了"和"文字本来就淡"
    很难干净地分开，而绘制顺序是确定的。

    v0.33 之前这条叫 `..._under_the_skeleton`（骨架点线必须留在图上面，
    小绪 09-29 的原话）。骨架删了，所以这里换了两条**新的**顺序约束，
    它们都是 backdrop 里剩下会静默坏掉的东西：

      · `rebuildBackdrop` 里：`tintRegion` 必须在 `drawImage` **之后** ——
        它是**原地乘**，乘的是"已经贴好背景的那块像素"。
        顺序反了就是"背景亮起来了，但暗部还是原来的"，图看着有点怪，说不出哪儿怪。
      · `paint` 里：贴 backdrop 必须在 `drawTabs` / `drawInspector` **之前** ——
        反了的话文字整片消失。
    """
    src = strip_comments(read(PANEL_CPP))
    m = re.search(r"void rebuildBackdrop\(PanelCache&[^)]*\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "找不到 rebuildBackdrop"
    body = m.group(1)
    bg_at = body.index("drawImage(cache.bdScaled")
    tint_at = body.index("tintRegion(")
    assert bg_at < tint_at, (
        "明暗度在贴图之前就乘了 —— 那一步乘的是一块还没贴图的像素")

    p = re.search(r"void paint\(Graphics&[^)]*\)\s*\{(.*?)\n\}", src, re.S)
    assert p, "找不到 paint"
    pbody = p.group(1)
    blit_at = pbody.index("cache.backdrop")
    tabs_at = pbody.index("drawTabs(")
    insp_at = pbody.index("drawInspector(")
    assert blit_at < tabs_at and blit_at < insp_at, (
        "backdrop 被画到顶栏 / 检查器之后了 —— 文字会整片消失")


def test_bake_tool_reads_geometry_instead_of_hardcoding():
    """烘焙脚本的落位参数必须从 `--dump-geometry` 的 `pane` 行读，不许手抄。

    "几何只有一份事实来源"是硬规矩。手抄一份的代价不是"多写几个数字"，
    而是改了面板宽度之后，背景会**悄悄错位**，而且图看起来还挺正常。
    """
    src = strip_comments(read(ROOT / "tools" / "bake_backdrop.py"))
    assert '"pane"' in src or "'pane'" in src, "烘焙脚本没读 geometryDump 的 pane 行"
    assert "pane_x0" in src and "pane_w" in src, "烘焙脚本没有用参数区区间算落位"
    assert "dump-geometry" in src, "烘焙脚本没有从编译产物取几何"


# ---------------------------------------------------------------------------
# v0.33 删掉了 `test_dotted_skeleton_uses_round_caps`。
#
# 它守的是一个很值得记下来的坑：`PathStrokeType(width)` 的默认端帽是 `butt`
# （juce_PathStrokeType.h:60），而 butt 端帽下一条 0.01 长的 dash 就是一个
# 0.01 × 0.9 的矩形 —— 面积 0.009 px²，**等于什么都没画，而且一句错都不报**。
# 22 条骨架点线就是靠"圆头端帽"才看得见的。
#
# 骨架删了，`strokeDotted` 这个函数也删了，所以这条没有住户。
# **但那个坑还在**：以后任何一次"用 dash 画点线"都要重新踩一遍 ——
# 所以这段话留在测试文件里，而不是跟着函数一起删掉。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 参数条的指针：**真的跟着值走**，不是一根钉死的竖线
#
# 这一节是补一个用户反馈。小绪的原话：「现在的参数条指针是假的」。
#
# 量出来的事实：轨道里唯一"看起来像指针"的东西，是一条 **4.4× 轨道高**的竖线；
# 而它画在 `defaultNormalised()` 上 —— 值怎么变它都不动。真正跟着值走的那根
# 填充条只改颜色、不加把手，反而不显眼。所以用户看到的就是"一根不动的指针"。
#
# 修完之后：会动的那根（指针）伸出轨道，不会动的那根（出厂值刻度）挪到了
# 轨道**下面**、只有 2px 高。两者在高度和位置上都分得开，不再靠猜。
# ---------------------------------------------------------------------------
def _bar_param_off_by_default(dump: str, controls: list[dict]) -> str:
    """挑一个**画成条形**、**量程就是 0..1**、而且**默认关着**的参数。

    这三条都是"指针测试"这个用途逼出来的，缺一不可：

    · **条形** —— 旋钮没有轨道，分段块（`Fmt::Choice`）画的是三段格子，
      两者都没有"轨道 + 指针"这套结构。拿它们测指针等于测空气。
      清单**从探针自述读**（`knobs` / `choices` 两行），不抄常量。

    · **量程 0..1** —— `_render()` 传的是**真值**（`--set <id>=<真值>`），
      而这两条断言拿 0.0 / 0.5 / 1.0 当真值、又默认它等于归一化值。
      量程不是 0..1 的参数（`sweep_rate` 是 0.01..20）在 1.0 处只填了 5%，
      轨道根本凑不出 100px 的填充段 —— 失败的样子是"找不到轨道"。

    · **默认关着** —— `test_pointer_is_drawn_even_when_the_module_is_off`
      要比较 default / all 两张图。出厂就亮着的模块（SPACE / OUT）两张图
      一模一样，"压暗"那条断言会以"关着和亮着一样亮"的形式报红。
      "默认关着"的判据写窄一点：**有开关、且开关默认 0**。RUIN 没有开关
      （它的 on/off 由 `ruin_mode` 决定），SPACE / OUT 恒亮 —— 三者都被
      这条判据自然排除。这里只需要**一个**候选，写窄没有代价。

    ---- 为什么不写死名字（v0.35 踩出来的）----
    v0.34 的形态是**逐参数**判定的，写死 `grain_spray` 就等于顺手写死了
    "它是条"。v0.35 改成**按模块**分配之后，GRAIN 整块变成旋钮，
    `grain_spray` 就不再是条了 —— 而这两条断言失败的样子是「找不到轨道」，
    看上去像布局坏了，**看不出是形态换了**。所以改成按形态挑：
    形态再变，这里跟着变，报错也只在真的挑不出候选时才出现。
    """
    knob_ids: set[str] = set()
    choice_ids: set[str] = set()
    for line in dump.splitlines():
        p = line.split()
        if p[:1] == ["knobs"]:
            # 格式前置断言：`knobs <个数> <id>…`。个数丢了的话，
            # 下面 `set(p[2:])` 会把第一个 id 当成个数吃掉，静默少一个。
            assert len(p) >= 2 and p[1].isdigit(), f"`knobs` 行格式变了：{line!r}"
            knob_ids |= set(p[2:])
        elif p[:1] == ["choices"]:
            choice_ids |= set(p[1:])
    assert knob_ids, "`knobs` 行为空 —— 要么解析失效，要么形态分配真变了"
    assert choice_ids, "`choices` 行为空 —— 要么解析失效，要么没有分段参数了"

    off_modules = {c["module"] for c in controls
                   if c["label"] == "" and c["default"] == 0.0}
    assert off_modules, "没有任何「有开关且默认关着」的模块 —— 出厂状态变了？"

    for c in controls:
        if c["label"] == "":
            continue
        if c["id"] in knob_ids or c["id"] in choice_ids:
            continue
        if not (c["lo"] == 0.0 and c["hi"] == 1.0):
            continue
        if c["module"] in off_modules:
            return c["id"]

    pytest.fail("挑不出「条形 + 量程 0..1 + 默认关着」的参数 —— "
                "形态分配或出厂状态变了，指针测试需要重新找一个落点。")


def _render(tmp_path: pathlib.Path, param: str, value: float,
            state: str = "all") -> pathlib.Path:
    """把面板渲成 PNG，把某个参数设成指定**真值**。scale=1 → 逻辑坐标 == 像素坐标。

    `state=default` 时大部分模块是**关**的（出厂状态只有 SPACE / OUT 亮），
    用来量"模块关着的参数行长什么样"。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先构建 panel_probe）")
    out = tmp_path / f"{param}_{value}_{state}.png"
    r = subprocess.run([str(PROBE), "--out", str(out), "--scale", "1",
                        "--state", state, "--set", f"{param}={value}"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return out


def _row_mid(param: str) -> int:
    return round(float(hit(f"ctl:{param}")["hit_point"].split()[1]))


# v0.35 删掉了 `_longest_run()`（"从一行像素里挑最长的一段连续整数"）。
# 它唯一的用处是挑轨道，而两条指针测试现在都**内联**了自己的 `runs_in()`
# —— 因为除了"最长的那段"，还要拿**全部**墨段做别的事（认指针、量覆盖）。
# 留着它只会让人以为还有人在用：一个没有读者的辅助函数，下一个人会照它的
# 假设去改，而改坏了没有任何东西会报红。


def test_parameter_pointer_is_real(tmp_path, dump, controls):
    """指针必须随值移动、必须伸出轨道；出厂值刻度必须**不动**。"""
    Image = pytest.importorskip("PIL.Image")

    # **按形态挑**，不写死名字 —— 理由见 `_bar_param_off_by_default` 的 docstring。
    param = _bar_param_off_by_default(dump, controls)
    mid = _row_mid(param)
    imgs = {v: Image.open(_render(tmp_path, param, v)).convert("L")
            for v in (0.0, 0.5, 1.0)}
    W = imgs[1.0].size[0]

    def lit(img, y, thr=30):
        return [x for x in range(W) if img.getpixel((x, y)) > thr]

    def runs_in(img, y, thr=30):
        xs = [x for x in range(W) if img.getpixel((x, y)) > thr]
        out: list[list[int]] = []
        for x in xs:
            if out and x - out[-1][1] <= 1:
                out[-1][1] = x
            else:
                out.append([x, x])
        return out

    # ---- 认轨道：**本控件那一列**的那根长条 ----
    #
    # 两次踩坑，都写在这儿：
    #   ① 不能按"这一行有多少亮像素"认 —— 相邻参数行的文字也在同一个 y 带里；
    #   ② 也不能全图找最长段 —— 面板有 3 列，别的列在同一个 y 带里也有轨道。
    # 所以先拿命中点（在参数名上）当锚，往右找第一根 ≥100px 的长条，那就是本行的轨道；
    # 再按"这根长条在哪些 y 上是满的"定轨道的上下沿。
    hx = float(hit(f"ctl:{param}")["hit_point"].split()[0])
    cands = [r for r in runs_in(imgs[1.0], mid) if r[0] > hx and r[1] - r[0] + 1 >= 100]
    assert cands, (f"{param}: 从参数名（x={hx:.1f}）往右没找到 ≥100px 的长条 —— "
                   f"值=1.0 时轨道应当被填充铺满")
    tx, tx1 = cands[0]
    tw = tx1 - tx + 1

    band = range(mid - 10, mid + 11)
    def covered(y):
        return sum(1 for x in range(tx, tx1 + 1) if imgs[1.0].getpixel((x, y)) > 30)

    track_rows = [y for y in band if covered(y) >= 0.9 * tw]
    assert track_rows, (
        f"{param}: 轨道 {tx}..{tx1} 上没有一行是被铺满的（各行的覆盖："
        f"{ {y: covered(y) for y in band} }）")
    top, bot = min(track_rows), max(track_rows)
    assert 2 <= bot - top + 1 <= 12, f"{param}: 轨道高度 {bot - top + 1}px 不像一根条"

    # ---- ① 指针：**伸出轨道**的亮像素（轨道上面一行）----
    ptr = {}
    for v, img in imgs.items():
        cols = [x for x in lit(img, top - 1) if tx - 6 <= x <= tx1 + 6]
        assert cols, (f"{param}: 值={v} 时轨道上方没有指针 —— 指针要么没画，"
                      f"要么缩在轨道里（缩在里面就只是填充的边，不是指针）")
        ptr[v] = sum(cols) / len(cols)

    assert ptr[0.0] < ptr[0.5] < ptr[1.0], (
        f"{param}: 指针没有随值右移：0.0 → {ptr[0.0]:.1f}，0.5 → {ptr[0.5]:.1f}，"
        f"1.0 → {ptr[1.0]:.1f}。不动的指针就是假指针。")

    # ② 位置要对得上真值比例（±3px；1px 线 + 抗锯齿，容差给够）
    want = tx + tw * 0.5
    assert abs(ptr[0.5] - want) <= 3.0, (
        f"{param}: 值=0.5 的指针在 x={ptr[0.5]:.1f}，按轨道 {tx}..{tx1} 算应当在 {want:.1f} 附近")
    assert abs(ptr[0.0] - tx) <= 4.0, f"值=0.0 的指针在 {ptr[0.0]:.1f}，应当贴着轨道左端 {tx}"
    assert abs(ptr[1.0] - tx1) <= 4.0, f"值=1.0 的指针在 {ptr[1.0]:.1f}，应当贴着轨道右端 {tx1}"

    # ---- ③ 轨道**下方**：不许因为值变了而变化 ----
    # 出厂值刻度就住在那里。它会动，就又变回"一根指针"了。
    #
    # **取窗的上界必须实测，不能写死偏移。** 这里原先写的是"指针到 `mid + th`，
    # 所以从 `bot + 4` 起"—— 那句话是错的：指针实际画到 `mid + th*1.3`，
    # 它的下摆本来就在轨道下方。把指针的尾巴算进"轨道下方"，这条断言就变成了
    # "指针不许随值移动"，**正好反了**。（v0.35 换了参数落点后当场报红，
    # 报出来的样子是"轨道下方有 6 列跟着变了"，看不出是取窗算错了。）
    # 所以先量出指针下摆，取窗从它**下面一行**开始。
    ptr_cols = [x for x in range(tx - 6, tx1 + 7)
                if imgs[0.0].getpixel((x, top - 1)) > 25]
    assert ptr_cols, f"{param}: 值=0.0 时轨道上方没有指针"
    ptr_bottom = max(y for y in range(top, bot + 16)
                     if any(imgs[0.0].getpixel((x, y)) > 30 for x in ptr_cols))

    # 刻度住在指针下摆之下、下一行内容之上。取 7 行：够得着刻度（实测在
    # ptr_bottom+3..+5），又够不着下一行（最近的行距 32.9，下一行的文字顶
    # 在 mid+32.9−11 ≈ ptr_bottom+19）。
    below = range(ptr_bottom + 1, ptr_bottom + 8)
    diff = [x for x in range(tx - 6, tx1 + 7)
            if any(imgs[0.0].getpixel((x, y)) != imgs[1.0].getpixel((x, y))
                   for y in below)]
    assert not diff, (
        f"{param}: 轨道下方在值从 0.0 变到 1.0 时有 {len(diff)} 列跟着变了"
        f"（x={diff[:12]}，窗口 y={min(below)}..{max(below)}）—— "
        f"出厂值刻度是参照物，必须钉死。它一动，用户就又看到一根假指针。")

    # 而且刻度必须在轨道**外面**。曾经它是一条 4.4× 轨道高的竖线站在轨道正中，
    # 看起来就是指针 —— 这正是这个 Bug 的来源。
    marks = [x for x in range(tx - 6, tx1 + 7)
             if any(imgs[0.0].getpixel((x, y)) > 12 for y in below)]
    assert marks, (f"{param}: 轨道下方（y={min(below)}..{max(below)}）没有出厂值刻度"
                   f"（它应当在轨道下方约 2px 处）")

    # ④ 刻度与指针**不许黏在一起** —— 黏在一起看起来就是一根被拉长的指针。
    assert min(below) - ptr_bottom >= 1, (
        f"{param}: 指针下摆到 y={ptr_bottom}，刻度从 y={min(below)} 起 —— "
        f"中间没有空隙，两者会黏成一根更长的指针")


def test_pointer_is_drawn_even_when_the_module_is_off(tmp_path, dump, controls):
    """模块**关着**的参数行也要有指针（压暗，但不能没有）。

    这条是**看渲染图看出来的**，不是想出来的 —— 数值测试当时全绿。

    出厂状态下 10 个模块有 8 个是关的。旧代码在关着时走 else 分支，拿轨道底色
    把填充盖一遍，等于什么都没画：一条死灰的条，加上一根永远不动的出厂值刻度。
    而这些行**是可以拖的**（`mouseDown` 不检查模块开关），所以用户一拖就是
    "没反应"，只有右边那串数字在变。小绪那句「参数条指针是假的」就是这儿来的。

    三条断言：
      ① 关着时**有**指针；
      ② 关着时指针**照样随值移动**；
      ③ 关着时指针**比亮着时暗** —— 否则"压暗"就成了"一样亮"，
         面板上一眼看不出哪些模块是开的。
    """
    Image = pytest.importorskip("PIL.Image")
    # **按形态挑**：这条比上一条多一个硬条件 —— 挑出来的模块必须**默认关着**，
    # 否则 default / all 两张图一样，"压暗"那条断言就成了空转。
    param = _bar_param_off_by_default(dump, controls)
    mid = _row_mid(param)

    off = {v: Image.open(_render(tmp_path, param, v, "default")).convert("L")
           for v in (0.0, 1.0)}
    on = {v: Image.open(_render(tmp_path, param, v, "all")).convert("L")
          for v in (0.0, 1.0)}

    # 用"亮着"那张定轨道（填充铺满，最好认）
    W = on[1.0].size[0]
    hx = float(hit(f"ctl:{param}")["hit_point"].split()[0])

    def runs(img, y, thr=30):
        xs = [x for x in range(W) if img.getpixel((x, y)) > thr]
        out: list[list[int]] = []
        for x in xs:
            if out and x - out[-1][1] <= 1:
                out[-1][1] = x
            else:
                out.append([x, x])
        return out

    cands = [r for r in runs(on[1.0], mid) if r[0] > hx and r[1] - r[0] + 1 >= 100]
    assert cands, "亮着的那张里没找到轨道"
    tx, tx1 = cands[0]

    band = range(mid - 10, mid + 11)
    cov = {y: sum(1 for x in range(tx, tx1 + 1) if on[1.0].getpixel((x, y)) > 30)
           for y in band}
    rows = [y for y in band if cov[y] >= 0.9 * (tx1 - tx + 1)]
    top = min(rows)

    def ptr_x(img):
        cols = [x for x in range(tx - 6, tx1 + 7) if img.getpixel((x, top - 1)) > 25]
        return (sum(cols) / len(cols)) if cols else None

    a, b = ptr_x(off[0.0]), ptr_x(off[1.0])
    assert a is not None and b is not None, (
        "模块关着时轨道上方找不到指针 —— 关着就不画指针，用户一拖就是"
        "「没反应」（这些行其实是可以拖的）")
    assert a < b, (
        f"模块关着时指针不随值移动：0.0 → {a}，1.0 → {b}。"
        f"关着也要能看出参数在哪，不然那一行就是一根死条。")

    peak_off = max(off[1.0].getpixel((x, top - 1)) for x in range(tx, tx1 + 1))
    peak_on = max(on[1.0].getpixel((x, top - 1)) for x in range(tx, tx1 + 1))
    assert peak_off < peak_on - 40, (
        f"关着时的指针（峰值 {peak_off}）和亮着时（峰值 {peak_on}）差不多亮 —— "
        f"那就看不出哪些模块是开的了。压暗要真的压下去。")
