"""界面排版的机器化检查。

为什么要测这个：用户曾经遇到过"Grain 那一组根本没有面板和旋钮"的问题，
而这类问题在编译期和 DSP 测试里都发现不了 —— 代码能跑，声音也对，就是界面上没有。
所以这里直接解析 PluginEditor.cpp，把每个控件的矩形算出来，检查：
  1) 全部控件都在面板范围内（不会跑到窗口外面看不见）
  2) 控件之间不重叠
  3) 每一组标题下面确实有控件（防止"有标题没旋钮"）
  4) 每个参数都真的被界面挂上了（防止"有参数没旋钮"）

这是一条纯静态检查，不需要编译，也不需要开 DAW。

版面改版后（纯黑 + Helvetica Neue + 发丝线），坐标不再写字面数字，
而是由 cell(n) 推导。解析器必须把 cell(n) 解出来，否则会**空转通过** ——
那种"看起来绿了其实什么都没测"的测试比不测更糟。
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
EDITOR = ROOT / "plugin" / "PluginEditor.cpp"
PROC = ROOT / "plugin" / "PluginProcessor.cpp"

def read_editor() -> str:
    return EDITOR.read_text(encoding="utf-8")


def _array(src: str, name: str) -> list[int]:
    m = re.search(rf"constexpr int {name}\[\d+\]\s*=\s*\{{([^}}]*)\}}", src)
    assert m, f"找不到 {name} 定义"
    return [int(v.strip()) for v in m.group(1).split(",") if v.strip()]


def row_ys(src: str) -> list[int]:
    return _array(src, "kRowY")


def label_ys(src: str) -> list[int]:
    return _array(src, "kLabelY")


def margin_x(src: str) -> int:
    m = re.search(r"constexpr int kMarginX\s*=\s*(\d+)", src)
    assert m, "找不到 kMarginX 定义"
    return int(m.group(1))


def cell_w(src: str) -> int:
    m = re.search(r"constexpr int kCellW\s*=\s*(\d+)", src)
    assert m, "找不到 kCellW 定义"
    return int(m.group(1))


def layout_dim(src: str, name: str) -> int:
    """所有控件尺寸都必须从源码的具名常量解出，避免改 UI 后测试还量旧尺寸。"""
    m = re.search(rf"constexpr int {name}\s*=\s*(\d+)", src)
    assert m, f"找不到 {name} 定义"
    return int(m.group(1))


def panel_size(src: str) -> tuple[int, int]:
    """setSize 现在写的是符号常量（kPanelW / kPanelH），必须解析出来。

    直接匹配字面数字会在这里失败 —— 但更糟的写法是"匹配不到就跳过"，
    那样面板尺寸的检查会静默失效。这里坚持 assert，宁可红也不能假绿。
    """
    m = re.search(r"setSize\(\s*(\w+)\s*,\s*(\w+)\s*\)", src)
    assert m, "找不到 setSize"
    vals = []
    for tok in m.groups():
        if tok.isdigit():
            vals.append(int(tok))
        else:
            mm = re.search(rf"constexpr int {tok}\s*=\s*(\d+)", src)
            assert mm, f"找不到常量 {tok} 的定义"
            vals.append(int(mm.group(1)))
    return vals[0], vals[1]


def resolve_x(token: str, src: str) -> int:
    """把 cell(n) 或字面数字解成像素 x。"""
    token = token.strip()
    m = re.match(r"cell\((\d+)\)$", token)
    if m:
        return margin_x(src) + cell_w(src) * int(m.group(1))
    return int(token)


def resolve_y(token: str, ys: list[int]) -> int:
    token = token.strip()
    m = re.match(r"kRowY\[(\d+)\]$", token)
    if m:
        return ys[int(m.group(1))]
    return int(token)


def split_args(s: str) -> list[str]:
    """按顶层逗号切分实参，忽略括号内的逗号（Fmt::X 之类不会出现，但保险）。"""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _strip_str(tok: str) -> str:
    m = re.match(r'^"([^"]*)"$', tok.strip())
    return m.group(1) if m else tok.strip()


def parse_controls(src: str):
    """返回 [(类型, 参数名, x, y, w, h)]。

    控件矩形按实际 setBounds 推：
      knob   → 旋钮(x+2, y, 44, 60) + 标签(x, y+60, 56, 13) → 合并 (x, y, 56, 73)
      toggle → (x, y+11, 44, 22)
      choice → (x, y+11, 44, 22)
    """
    ys = row_ys(src)
    cw = cell_w(src)
    knob = layout_dim(src, "kKnob")
    knob_box = layout_dim(src, "kKnobBox")
    label_h = layout_dim(src, "kLabelH")
    toggle_h = layout_dim(src, "kToggleH")
    out = []
    # 必须锚定在实参的第一个字符串字面量上 —— 否则会连函数定义
    # （void ...::addKnob(const char* paramId, ...)）一起匹配进来，
    # 解析出一堆 "int x" 这种垃圾实参。
    for m in re.finditer(r'add(Knob|Toggle|Choice)\(\s*("[^"]*"(?:[^;]*?))\)\s*;', src, re.S):
        kind = m.group(1).lower()
        args = split_args(m.group(2))
        if kind == "knob":
            assert len(args) == 5, f"addKnob 参数个数不对: {args}"
            param = _strip_str(args[0])
            x = resolve_x(args[2], src)
            y = resolve_y(args[3], ys)
            out.append((kind, param, x, y, cw, knob + knob_box + label_h))
        elif kind == "toggle":
            assert len(args) == 4, f"addToggle 参数个数不对: {args}"
            param = _strip_str(args[0])
            x = resolve_x(args[2], src)
            y = resolve_y(args[3], ys)
            out.append((kind, param, x, y + (knob - toggle_h) // 2, knob, toggle_h))
        else:
            assert len(args) == 3, f"addChoice 参数个数不对: {args}"
            param = _strip_str(args[0])
            x = resolve_x(args[1], src)
            y = resolve_y(args[2], ys)
            out.append((kind, param, x, y + (knob - toggle_h) // 2, knob, toggle_h))
    return out


@pytest.fixture(scope="module")
def src():
    return read_editor()


@pytest.fixture(scope="module")
def controls(src):
    c = parse_controls(src)
    assert len(c) >= 45, f"只解析出 {len(c)} 个控件，解析器可能失效了"
    return c


def test_every_control_is_inside_the_panel(src, controls):
    w, h = panel_size(src)
    for kind, param, x, y, cw, ch in controls:
        assert x >= 0 and y >= 0, f"{param} 坐标为负: ({x},{y})"
        assert x + cw <= w, f"{param} 右边缘 {x + cw} 超出面板宽度 {w}"
        assert y + ch <= h, f"{param} 下边缘 {y + ch} 超出面板高度 {h}"


def test_no_two_controls_overlap(controls):
    rects = [(p, x, y, cw, ch) for _, p, x, y, cw, ch in controls]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            p1, x1, y1, w1, h1 = rects[i]
            p2, x2, y2, w2, h2 = rects[j]
            if x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1:
                pytest.fail(f"控件重叠: {p1} 与 {p2}")


def test_no_horizontal_gaps_inside_a_row(src, controls):
    """同一行里，格子必须严格按 cell 间距落位 —— 错一格会出现肉眼可见的空洞。"""
    cw = cell_w(src)
    xs = sorted({x for _, _, x, _, _, _ in controls})
    assert xs, "没有解析到任何控件"
    for x in xs:
        assert (x - margin_x(src)) % cw == 0, f"x={x} 不在 cell 网格上"


def test_every_group_label_has_controls_under_it(src, controls):
    """防止"有分组标题、下面却没旋钮"—— 正是用户上次遇到的问题。"""
    lys = label_ys(src)
    groups = re.findall(r'addGroup\(\s*"([^"]*)",\s*([^,]+),\s*([^)]+)\)\s*;', src)
    assert len(groups) >= 8, f"只解析出 {len(groups)} 个分组，解析器可能失效了"

    for text, gxtok, gytok in groups:
        if not text:
            continue
        gx = resolve_x(gxtok, src)
        m = re.match(r"kLabelY\[(\d+)\]$", gytok.strip())
        gy = lys[int(m.group(1))] if m else int(gytok)
        below = [c for c in controls
                 if c[2] + 56 > gx and c[2] < gx + 150 and gy - 6 <= c[3] <= gy + 40]
        assert below, f"分组 {text}（x={gx}, y={gy}）下面没有任何控件"


def test_every_parameter_is_exposed_in_the_ui(src, controls):
    """每个 APVTS 参数都必须有对应的界面控件，否则用户根本调不到它。"""
    ids = set(re.findall(r'static constexpr const char\* \w+ = "([^"]+)";',
                         PROC.read_text(encoding="utf-8")))
    assert len(ids) >= 45, f"只从 PluginProcessor.cpp 解析出 {len(ids)} 个参数 ID"
    wired = {p for _, p, *_ in controls}
    missing = sorted(ids - wired)
    assert not missing, f"这些参数没有界面控件，用户调不到: {missing}"


def test_parameter_display_names_are_unique():
    """参数**显示名**必须唯一。

    界面上的短标签（size / rate / feedback）可以重复，因为旁边有分组标题兜着；
    但送进宿主的参数名不行 —— Ableton 的 MIDI 映射列表里只显示这个名字，
    出现三个 "Size"、三个 "Rate" 的话用户根本分不清该映射哪一个。
    这条曾经真的踩到：新加的 stutter/comb/tape 参数沿用了 "Size"/"Rate"/"Feedback"，
    端到端验收里按名字找不到参数，整段解构链验收全部静默跳过。
    """
    src = PROC.read_text(encoding="utf-8")
    names = re.findall(r'pid\(ParamIDs::\w+\),\s*"([^"]+)"', src)
    assert len(names) >= 45, f"只解析出 {len(names)} 个参数显示名"
    dup = sorted({n for n in names if names.count(n) > 1})
    assert not dup, f"参数显示名重复，宿主里没法区分: {dup}"


def test_editor_has_no_decorative_header_or_runtime_status(src):
    """v0.10 的面板不许再显示产品名、功能清单或 frozen/voices/tape 状态。

    这些文字只是装饰，不是可操作的参数；它们抢占首行高度、和 Ableton 原生设备
    "参数优先"的阅读顺序冲突。用精确字符串检查，防止以后改 UI 时悄悄塞回来。
    """
    forbidden = (
        'drawText("träne"',
        'freeze / grain / stutter / comb / tape / ruin / sweep / delay / space',
        '"frozen"',
        '"live"',
        '"voices "',
        '"x" + juce::String(speed',
    )
    leaked = [s for s in forbidden if s in src]
    assert not leaked, f"面板仍有非交互装饰/状态文案: {leaked}"


def test_editor_loads_the_user_installed_ableton_sans(src):
    """字体必须直接取用户已安装 Ableton 12 的 Ableton Sans，不能伪装成 Helvetica。

    插件不复制或打包 Ableton 字体（避免把第三方字体带进产物）；运行时只读取本机
    Ableton.app 自带的 Bold / Medium 字重。找不到 Ableton 时才降级 Helvetica Neue Bold。
    """
    assert 'AbletonSans-Bold.otf' in src, "找不到 Ableton Sans Bold 的加载路径"
    assert 'AbletonSansMedium-Regular.otf' in src, "找不到 Ableton 数据字体的加载路径"
    assert 'Typeface::createSystemTypefaceFor' in src, "字体必须从用户本机 Ableton.app 运行时加载"
    assert 'Helvetica Neue' in src and 'juce::Font::bold' in src, "必须有 Helvetica Neue Bold 降级路径"


def test_rotaries_are_flat_discs_not_lux_style_value_arcs(src):
    """所有旋钮改为 Ableton 式平面盘：实心底盘 + 指针 + 三个刻度，不画值弧。

    旧版 Lux Cache 语言靠外圈和值弧表达；这次用户明确要求改成 Ableton 原生的平面
    版本。检查绘制 API 而不是截图像素，确保以后不会悄悄退回旧形式。
    """
    begin = src.index('void TraneLookAndFeel::drawRotarySlider')
    end = src.index('void TraneLookAndFeel::drawButtonBackground', begin)
    rotary = src[begin:end]
    assert 'fillEllipse' in rotary, "平面旋钮需要可见的实心底盘"
    assert 'for (const float mark' in rotary and rotary.count('drawLine') >= 2, (
        "旋钮需要循环绘制起/中/止三个刻度，并另画高亮指针"
    )
    assert 'addCentredArc' not in rotary, "新旋钮不应再使用 Lux 风格的值弧"


def test_flat_ui_uses_full_white_and_bold_type_roles(src):
    """亮白度要提高，所有标签/数值走加粗字体角色，不保留 0.92 的灰白主文字。"""
    assert 'constexpr float kInkFull = 1.00f' in src
    assert 'kInkDim = 0.84f' in src
    assert 'TraneLookAndFeel::ui(10.0f' in src, "标签要使用加粗 Ableton Sans 字体"
    assert 'data(11.0f)' in src and 'createSliderTextBox' in src, "数值要使用 Ableton 数据字体"
