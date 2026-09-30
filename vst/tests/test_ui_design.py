"""UI 设计约定的机器化检查（v0.35）。

这个文件干六件事：

  1. **文字对比度复算** —— 面板把每一处文字用的 (不透明度, 基底层, 墨层强度)
     登记下来（`panel_probe --dump-text`），这里独立复算 WCAG 2.1 的对比度。
     这是**唯一**一种"画出来看着还行、但已经不合规"的坏法：kInk 的 0.60 档
     压在 #000000 上是 7.4:1，压到 0.45 就掉到 4.1:1 —— 过不了 AA，
     而屏幕上只是"名字暗了一点"。
  2. **令牌对账** —— 颜色必须来自 Apple 的语义色，不是"看着像"；
     而且对比度复算用的令牌**从头文件读**，不是这里另抄一份 hex。
  3. **数值列的排版** —— 列宽够不够（§6）与数字等不等宽。
     这两条量的都是**眼睛看不出来的坏法**：右对齐 + 不截断的数值串太长时
     会静静爬进轨道区，"右缘齐平"照样绿。
  4. **控件形态** —— 哪**五**个模块的参数全画成旋钮（§7）。
     v0.34 是"哪 12 个**参数**"（逐参数判据），v0.35 改成按**模块**分配：
     判据是"这个模块是**调**出来的还是**配**出来的"。于是这里查的是
     模块清单，以及两条硬约束（有分段选择的模块不能全旋钮 / 同一栏不许混形态）。
  5. **面板字体** —— 面板必须用**打包内嵌**的 Trane Sans（§8）。
     换字体只改文字的墨迹，**不改任何一条几何**（列宽是按字体量出来的，
     所以连数值都不动）—— 于是"字体悄悄降级成系统字体"这件事，
     前面所有几何断言一个都抓不到。只能直接问字体叫什么。
  6. **门禁本身的闸门** —— 断言 `run_tests.sh` 里真的还在调用那几个检查器。
     没有这一条的话，谁把某一行删掉，别的测试照样全绿 ——
     那是"闸门被悄悄拆掉"式的假绿。

关于 v0.32 的 HTML 设计稿（`tools/render_ui_dark_panel.py`）
==========================================================
它曾是 v0.19–v0.32 那版面板（带世界树 / 22 条骨架点线 / 9 条信号线 /
MODE·列数切换）的**独立第二实现**，这个文件原本的作用就是把它的自检接进门禁。

**v0.33 把它退役了**（小绪的决定：「树完全删掉，参数铺满整块面板」）。
理由：设计稿画的是一个**已经不存在的设计**，它的 63 条自检与 45 条反向对照
守的是"树画得对不对"。留在门禁里只有两种结局 —— 要么永远红，要么被人一条条
删松。**两者都比没有更坏**：永远红会挡住真回归，删松会伪装成有覆盖。
文件保留（它是那段设计的历史，也是树的视觉身份的唯一记录），但门禁不再调用它。

退役时**没有丢掉它的贡献**：`TEXT_LOG`（对比度逐对复算）这套机制搬进了
真正的实现里（`TranePanel.cpp` 的 `textLog()` + `panel_probe --dump-text`），
而且比原来更强 —— 原来看的是另一份实现，现在看的是**插件真正在跑的那段代码**。

关于"不能空转通过"
==================
沿用 `test_editor_layout.py` 的规矩：解析器一律带条数下限断言，
构建产物缺失时用 `pytest.skip("先跑 cmake --build build")`，**不许静默通过**。
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

# 字体验证要用它从 .ttf 独立复算前进宽度。**故意在模块顶层 import**：
# 缺了它整个文件都收集不了，报错一眼能看见 —— 而不是那几条字体断言
# 悄悄 skip 掉，留一个看起来全绿的报告。
# `run_tests.sh` 的 `find_python()` 也把它列进了必需依赖，所以正常路径上
# 根本走不到这里报错。
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PANEL_H = ROOT / "plugin" / "TranePanel.h"
PANEL_CPP = ROOT / "plugin" / "TranePanel.cpp"
RUN_TESTS = ROOT / "run_tests.sh"
PROBE = ROOT / "build" / "panel_probe_artefacts" / "Release" / "panel_probe"
FONT_DIR = ROOT / "assets" / "fonts"

# 门禁里**必须**真的被调用的那几个检查器。清单写在这里，而不是"看 run_tests.sh
# 里有什么就认为该有什么"—— 那样删一行就自动少一条断言，正是要防的东西。
GATE_TOOLS = ["check_panel_render.py", "check_accent_mutations.py",
              "check_hover_mutations.py", "check_backdrop_mutations.py",
              "check_metrics_mutations.py", "check_knobs_mutations.py"]

# 已退役的 v0.32 设计稿工具：**门禁不许再调用**。
RETIRED_TOOLS = ["render_ui_dark_panel.py", "check_contrast_mutations.py"]

# 与 `test_editor_layout.py` 同一组数 —— 故意的：两个文件各写一遍，
# 分叉了就说明有人只改了一边。
N_CONTROLS = 48
N_NODES = 10
N_PARAM_ROWS = 41        # 带数值的参数行（= 48 − 7 个模块开关）；数值列只服务它们
N_KNOB_MODULES = 5       # 全旋钮的模块个数（v0.35）；其余 5 个模块是条形
N_KNOB_ROWS = 20         # 展开后画成旋钮的**参数行**个数（不含 5 个模块开关）

# 期望的旋钮模块清单。**与头文件 `kKnobModules` 逐条对账**（§7）——
# 这里再写一遍是故意的：两边分叉说明有人只改了一边，而那正是"改了个数、
# 界面没跟着变"最容易发生的时刻。
#
# **栏切分不在这里抄**：`--dump-layout` 的 `col` 行已经带 `nodes …`，
# 从探针读才是"一份事实"。抄一份的话，改了栏切分而这里没改，
# "同一栏不许混形态"会对着**旧的栏**去查 —— 绿得毫无意义。
KNOB_MODULES = ["freeze", "grain", "stutter", "comb", "tape"]


def read(p: pathlib.Path) -> str:
    assert p.is_file(), f"找不到 {p}"
    return p.read_text(encoding="utf-8")


def strip_comments(src: str) -> str:
    """去掉 // 注释（不动字符串字面量）。理由同 test_editor_layout.py。"""
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


# ---------------------------------------------------------------------------
# 色彩数学：WCAG 2.1
# ---------------------------------------------------------------------------
def rgb_of(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def over(a: float, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """把不透明度 a 的 fg 合成到 bg 上。

    **在 sRGB 直值上混合** —— 这正是 JUCE 软件渲染器的做法（`Colour::withAlpha`
    之后直接按目标空间的数值混合）。用线性光混合算出来的底会和实际像素差一截，
    于是对比度断言算的是另一个东西。
    """
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


# ---------------------------------------------------------------------------
# 令牌：**从头文件读**，不在这里另抄一份 hex
# ---------------------------------------------------------------------------
def _eval_float(expr: str) -> float:
    """只 eval 本仓库源码里的算式（`120.0f / 255.0f` 这种）。

    每个数后面的 `f` 都要去掉 —— 不是只去掉整串末尾那一个：
    `120.0f / 255.0f` 的 `rstrip("f")` 只会削成 `120.0f / 255.0`，
    中间那个 f 留着就通不过白名单校验（第一版就是这么错的）。
    """
    e = expr.replace("f", "").strip()
    assert re.fullmatch(r"[\d.\s/]+", e), f"不认识的常量算式: {expr!r}"
    return eval(e, {"__builtins__": {}})          # noqa: S307


def read_tokens() -> dict:
    """把面板的基色与半透明令牌读出来。

    "颜色只有一份事实来源"是硬规矩。手抄一份的代价不是"多写几个 hex"，
    而是改了令牌之后对比度还在按旧值算 —— 于是断言绿着，字已经糊了。
    """
    src = strip_comments(read(PANEL_H))
    tok: dict = {}

    for name in ("kBg", "kInk", "kGray2"):
        m = re.search(rf"const juce::Colour {name}\{{0xff([0-9a-fA-F]{{6}})\}}", src)
        assert m, f"读不到 {name} 的 hex"
        tok[name] = rgb_of(m.group(1))

    # `fromFloatRGBA(120.0f / 255.0f, …, 0.36f)` —— 四个参数：三通道 + alpha。
    # **四个都要**：只取前三个的话 alpha 会悄悄变成 1.0，于是"轨道底"被算成
    # 一块亮灰，对比度全部算高。
    for name in ("kFill", "kSegBg"):
        m = re.search(rf"const juce::Colour {name} =\s*"
                      r"juce::Colour::fromFloatRGBA\(([^)]*)\)", src, re.S)
        assert m, f"读不到 {name} 的 fromFloatRGBA 声明"
        args = [a for a in (s.strip() for s in m.group(1).split(",")) if a]
        assert len(args) == 4, f"{name} 的参数不是 4 个: {args}"
        tok[name] = tuple(round(_eval_float(a)) for a in args[:3])
        tok[name + "_a"] = _eval_float(args[3])

    for k in ("kAText", "kAMuted", "kAOff", "kATick",
              "kHoverA", "kPressA", "kAHoverName",
              # v0.35：模块框的块底不透明度。**必须从这儿读** ——
              # 它是"块底"这一层的唯一来源，抄一份的话改了 alpha
              # 而对比度还在按旧值算，`block` 那一层的字就没人盯着了。
              "kBlockFillA"):
        m = re.search(rf"constexpr float {k} = ([\d.]+)f", src)
        assert m, f"读不到 {k}"
        tok[k] = float(m.group(1))
    return tok


# ---------------------------------------------------------------------------
# 文字登记表：从编译产物读
# ---------------------------------------------------------------------------
def dump_text(state: str, *flags: str) -> list[tuple[float, str, float]]:
    """跑一次 `panel_probe --dump-text`，返回 [(不透明度, 基底层, 墨层强度)]。"""
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")
    cmd = [str(PROBE), "--dump-text", "--state", state, *flags]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{' '.join(cmd)}\n{r.stderr}"

    out: list[tuple[float, str, float]] = []
    count = None
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "text":
            out.append((float(p[1]), p[2], float(p[3])))
        elif p[0] == "text_count":
            count = int(p[1])
    assert count is not None, f"探针没吐 text_count:\n{r.stdout}"
    assert count == len(out), f"自述说 {count} 对，实际解析出 {len(out)} 对"
    assert out, f"--dump-text 一对都没吐:\n{r.stdout}"
    return out


_PAIRS: dict[tuple[float, str, float], str] | None = None


def collect_pairs() -> dict[tuple[float, str, float], str]:
    """把面板上**所有相位**的文字对收集起来（模块级缓存 —— 22 次子进程别跑两遍）。

    为什么要跑这么多相位：hover / press 的墨层强度是**连续**的（160ms 淡入），
    而"字最暗、底最亮"的中间相位恰恰最危险。只在静止态量一次，
    等于把那条曲线上的点全当成 0。
    """
    global _PAIRS
    if _PAIRS is not None:
        return _PAIRS

    pairs: dict[tuple[float, str, float], str] = {}
    cases: list[tuple[str, str, list[str]]] = [
        ("静止（全开）", "all", []),
        ("静止（出厂）", "default", []),
    ]
    for t in (0.0, 0.02, 0.04, 0.08, 0.12, 0.16):
        cases.append((f"hover 参数行 t={t}", "all",
                      ["--hover", "ctl:grain_spray", "--hover-t", str(t)]))
    cases += [
        ("press 参数行", "all", ["--press", "ctl:grain_spray"]),
        ("hover 模块标题", "all", ["--hover", "ctl:grain_on"]),
        ("press 模块标题", "all", ["--press", "ctl:grain_on"]),
        ("hover 落位格", "all", ["--hover", "tab:1"]),
        ("press 落位格", "all", ["--press", "tab:1"]),
        ("hover 选择图片格", "all", ["--hover", "bgslot"]),
        ("press 选择图片格", "all", ["--press", "bgslot"]),
        ("hover 明暗度轨道", "all", ["--hover", "bgbright"]),
        ("press 明暗度轨道", "all", ["--press", "bgbright"]),
    ]
    for tag, state, flags in cases:
        for pair in dump_text(state, *flags):
            pairs.setdefault(pair, tag)
    _PAIRS = pairs
    return pairs


# ---------------------------------------------------------------------------
# 1 · 对比度
# ---------------------------------------------------------------------------
def base_layers() -> dict[str, tuple[int, int, int]]:
    """六个基底层在**静止态**（其上没有墨层）下的实际颜色。

    底不是常量：文字坐在哪块面上决定它跟谁比。六个面各自的来历：
      · `bg`        —— 面板底，`kBg`（systemBackground）。
      · `block`     —— 模块框的块底（v0.35），`kInk @ kBlockFillA` 压在面板底上。
                       参数名 / 数值 / 模块标题都坐在它上面。
      · `track`     —— 轨道底，`kFill`（tertiarySystemFill 以 0.36 合成到面板底）。
                       **压在块底之上** —— 轨道是画在框里的。
      · `seg`       —— 未选中的分段格子（**顶栏那个**，坐在面板底上），
                       `kSegBg`（同上，另一个 fill）。
      · `seg_block` —— 未选中的分段格子，**模块框里的那个**（SWEEP 的 LP/BP/HP），
                       坐在块底之上。
      · `seg_on`    —— 选中的分段格子，`kGray2`（systemGray2，**不透明**）。

    **`seg` 与 `seg_block` 必须分开**：顶栏那个在面板底上，模块里那个在块底上，
    两个合成底差约 10 个 RGB。差得不多 —— 而"差得不多"正是最危险的那种错：
    拿错一个算，对比度只差零点几，断言照样绿。
    """
    tok = read_tokens()
    bg = tok["kBg"]
    block = over(tok["kBlockFillA"], tok["kInk"], bg)
    return {
        "bg":        bg,
        "block":     block,
        "track":     over(tok["kFill_a"], tok["kFill"], block),
        "seg":       over(tok["kSegBg_a"], tok["kSegBg"], bg),
        "seg_block": over(tok["kSegBg_a"], tok["kSegBg"], block),
        "seg_on":    tok["kGray2"],
    }


def declared_base_layers() -> set[str]:
    """登记表**能吐出**的基底层名字 —— 从 `bdName()` 读，不在这里另抄一份。

    这一份清单就是上面那张合成表的对账对象：谁往 `enum class Bd` 里加了第五个
    基底层，`bdName` 就得给它起名，而这里的断言会当场报红（因为合成表没跟着加），
    于是"新底上的字没人算对比度"这条漏不出去。
    """
    src = strip_comments(read(PANEL_CPP))
    names = set(re.findall(r'case Bd::\w+:\s*return "(\w+)";', src))
    assert names, "读不到 bdName() 里的基底层清单"
    return names


def test_every_text_pair_meets_wcag_aa() -> None:
    """面板上**每一处文字**，对它真实的底色都要 ≥ 4.5:1（WCAG 2.1 AA 正文）。

    底不是常量 —— 文字压在"基底层 + 墨层"上，而墨层强度随 hover / press 变。
    所以这里按登记表给的三个数**逐对合成**，而不是查一张预设的底色表。
    """
    tok = read_tokens()
    ink = tok["kInk"]
    bg = tok["kBg"]
    base = base_layers()

    pairs = collect_pairs()

    # **正向对照**：公式必须真的会判红。0.45 压在纯黑上过不了 AA ——
    # 少了这一条，一个"永远返回 99"的 contrast() 也能让下面全绿。
    ctl = contrast(over(0.45, ink, bg), bg)
    assert ctl < 4.5, f"对照失败：0.45 档算出 {ctl:.2f}:1，本该过不了 AA"

    bad = []
    worst = (99.0, (0.0, "?", 0.0, "?"))
    for (a, bd, band), tag in sorted(pairs.items()):
        assert bd in base, f"{tag}: 登记了未知基底层 {bd!r}"
        real_bd = over(band, ink, base[bd]) if band > 0.0 else base[bd]
        fg = over(a, ink, real_bd)
        r = contrast(fg, real_bd)
        if r < worst[0]:
            worst = (r, (a, bd, band, tag))
        if r < 4.5:
            bad.append((a, bd, band, round(r, 2), tag))

    assert not bad, (
        "有文字过不了 WCAG AA 4.5:1：\n  "
        + "\n  ".join(f"α={a:.2f} 底={bd}+墨{band:.2f} → {r}:1  （{tag}）"
                      for a, bd, band, r, tag in bad))
    print(f"\n  最暗一处 {worst[0]:.2f}:1  α={worst[1][0]:.2f} 底={worst[1][1]}"
          f"+墨{worst[1][2]:.2f}  （{worst[1][3]}）  共 {len(pairs)} 对")


def test_contrast_sweep_actually_covers_the_panel() -> None:
    """上面那条不能空转：覆盖必须真的够广。

    一条"每对都过"的断言，在只收到 2 对的时候也是绿的。所以这里钉四件事：
    合成表覆盖了全部声明的基底层、hover 与 press 的墨层都出现过、对数的下限、
    以及**每一个声明过的基底层都被真的用到或明确豁免**。
    """
    pairs = collect_pairs()
    assert len(pairs) >= 12, f"只收到 {len(pairs)} 对文字，覆盖面不够（下限 12）"

    declared = declared_base_layers()
    assert set(base_layers()) == declared, (
        f"合成表与 `bdName()` 分叉了 —— 合成表 {sorted(base_layers())}，"
        f"代码里 {sorted(declared)}；新加的那个底上的字没人算对比度")

    bds = {bd for _, bd, _ in pairs}
    assert bds <= declared, f"登记了未声明的基底层：{sorted(bds - declared)}"
    assert {"bg", "seg", "seg_on"} <= bds, \
        f"基底层只覆盖了 {sorted(bds)} —— 漏掉的那些底上的字没人管"

    bands = sorted({round(band, 4) for _, _, band in pairs})
    assert 0.0 in bands, "没有一对是静止态（墨层 0）—— 静止态的字没人管"
    assert any(0.0 < b < 0.04 for b in bands), \
        f"没有中间相位（0 < 墨层 < 0.04）—— 淡入中间那一段没人管：{bands}"
    assert 0.04 in bands, f"没有 hover 满强度（墨层 0.04）：{bands}"
    assert 0.10 in bands, \
        f"没有 press 满强度（墨层 0.10）—— 按下那一档没人管：{bands}"

    # `track` 是**唯一**一个今天不承载文字的基底层：轨道里没有字，明暗度读数
    # 在轨道右边、坐在面板底上（登记成 `bg`）。所以这里不要求它出现在 `pairs` 里
    # —— 上面那条 `set(base_layers()) == declared` 已经保证它没被忘掉，
    # 而"每对都过"那条也真的会量它：以后谁往轨道上放文字，就会当场被量到。


def test_text_alphas_stay_on_the_documented_ladder() -> None:
    """头文件里写的那几档文字不透明度，必须真的就是面板在用的那几档。

    两半，各抓一种错法：

      · **档位必须真的出现** —— 少了它，一个把 kAMuted 从 0.60 压到 0.45 的
        改动会被对比度那条抓住（0.45 是 4.1:1），但"0.60 这一档还在不在用"
        没人管；如果有人干脆把某处改成硬编码 0.70，档位表就悄悄废了。
      · **不许出现比最暗档还暗的文字** —— 这是硬边界。kATick = 0.30 是
        **非文字**档（出厂刻度），它压在纯黑上只有 2.23:1，是**有意豁免**的；
        一旦它被拿去画字，这条会当场报红。
    """
    tok = read_tokens()
    used = {round(a, 4) for a, _, _ in collect_pairs()}

    for k in ("kAText", "kAMuted", "kAOff"):
        assert round(tok[k], 4) in used, \
            f"{k} = {tok[k]} 在绘制代码里一次都没出现 —— 档位表和代码分叉了"

    floor = tok["kAOff"]
    for a in sorted(used):
        assert a >= floor - 1e-6, (
            f"绘制代码里出现了比最暗文字档（kAOff = {floor}）还暗的不透明度 {a} —— "
            f"要么它是新档位（那就写进头文件的档位表并说明理由），"
            f"要么它是硬编码（那就会绕过档位设计）")

    # kATick 只许画成方块，不许画成字。
    assert tok["kATick"] < floor, \
        f"出厂刻度档 {tok['kATick']} 不再比文字档 {floor} 暗 —— 那它就没有理由豁免"
    assert round(tok["kATick"], 4) not in used, \
        "kATick 被拿去画文字了 —— 它压在纯黑上只有 2.23:1，过不了 AA"


# ---------------------------------------------------------------------------
# 2 · 令牌
# ---------------------------------------------------------------------------
def test_design_tokens_are_apple_semantic_colours() -> None:
    """颜色必须来自 Apple 的深色语义色，不是"看着像"。

    与 `test_editor_layout.py::test_dark_semantic_background_and_label` 是
    **两条不同的断言**，不重复：
      · 那边查的是"源码里有没有这几个 hex"（令牌在不在）；
      · 这边查的是"读出来的数值对不对、排序对不对"（令牌是什么）。
    """
    tok = read_tokens()
    assert tok["kBg"] == (0, 0, 0), f"面板底不是 systemBackground: {tok['kBg']}"
    assert tok["kInk"] == (0xEB, 0xEB, 0xF5), f"文字基色不是 label: {tok['kInk']}"
    assert tok["kGray2"] == (0x63, 0x63, 0x66), f"选中块不是 systemGray2: {tok['kGray2']}"

    # 文字档位必须严格降序，而且主内容档必须是满不透明 ——
    # 否则"主内容"和"次要"就没有层级了。
    assert tok["kAText"] == 1.0, f"主内容档不是满不透明：{tok['kAText']}"
    assert tok["kAText"] > tok["kAMuted"] > tok["kAOff"] > 0.0, \
        f"文字档位没有严格降序：{tok['kAText']} / {tok['kAMuted']} / {tok['kAOff']}"
    assert tok["kPressA"] >= 2.0 * tok["kHoverA"], \
        f"press ({tok['kPressA']}) 没有至少是 hover ({tok['kHoverA']}) 的两倍 —— " \
        "按下的反馈会读不出来"


# ---------------------------------------------------------------------------
# 3 · 已退役的设计稿
# ---------------------------------------------------------------------------
def test_retired_design_draft_is_not_in_the_gate() -> None:
    """v0.32 的 HTML 设计稿必须**明确退役**，不能静默地"留着但没人跑"。

    三条一起才说得清：
      · 文件还在（它是那段设计的历史，不许顺手删掉）；
      · 它开头写着"已退役"（否则下一个人会以为它只是坏了，去修它）；
      · 门禁不再调用它（否则门禁永远红）。
    """
    draft = TOOLS / "render_ui_dark_panel.py"
    assert draft.is_file(), "设计稿文件被删了 —— 它是 v0.32 那版设计的历史记录"
    head = draft.read_text(encoding="utf-8")[:2500]
    assert "v0.32" in head, "设计稿开头没有版本说明"
    assert "退役" in head, "设计稿开头没有「已退役」的说明 —— 下一个人会去修它"

    cmds = _gate_commands(read(RUN_TESTS))
    for tool in RETIRED_TOOLS:
        assert not any(tool in c for c in cmds), (
            f"门禁还在调用 {tool} —— 它守的是已经不存在的 v0.32 设计，"
            f"跑起来只会永远红")


# ---------------------------------------------------------------------------
# 4 · 门禁本身的闸门
# ---------------------------------------------------------------------------
def _gate_commands(sh: str) -> list[str]:
    """`run_tests.sh` 里**真的会被执行**的行 —— 去掉空行与注释。

    为什么要去掉注释：第一版护栏写的是 `assert "--check-only" in sh`，
    而那段注释里恰好写着「--check-only：只跑自检不出图」——
    于是把**命令行上**的 `--check-only` 删掉，护栏照样绿。
    这正是本项目的老毛病（突变锚点落在注释上），在**护栏自己身上**又犯了一次。
    """
    out: list[str] = []
    for line in sh.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def test_gate_runs_every_checker() -> None:
    """`run_tests.sh` 必须**真的**调用每一个检查器与反向对照。

    这一条防的是"闸门被悄悄拆掉"：把 run_tests.sh 里某一行删掉，
    别的测试照样绿，而那一层覆盖从此没人管。**没人见它响过的断言等于没写** ——
    门禁里的那些调用行也是断言，同样要有人盯着。
    """
    cmds = _gate_commands(read(RUN_TESTS))
    for tool in GATE_TOOLS:
        assert any(tool in c for c in cmds), \
            f"run_tests.sh 里没有**真的调用** {tool} —— 那一层覆盖再也不会被跑到"
    assert any("check_panel_render.py" in c and "--outdir" in c for c in cmds), \
        "面板渲染检查没有 --outdir —— 出图是给人看的，别把它悄悄关掉"


def test_gate_sections_are_present() -> None:
    """四个验证阶段一个都不能少，而且顺序是刻意的（先构建、再测、最后端到端）。

    用**前缀**匹配而不是全串相等：阶段标题后面常带括号补充
    （`=== 端到端验收（加载真实 .vst3 渲染）===`），全串比会把"标题改了个括号"
    判成"这一段没了"。前缀是标题的稳定部分。
    """
    sh = read(RUN_TESTS)
    order = ["=== 构建 ===", "=== 离线渲染验证 ===", "=== 面板渲染 + 像素分析 ===",
             "=== 端到端验收"]
    pos = [sh.find(s) for s in order]
    for s, p in zip(order, pos):
        assert p >= 0, f"run_tests.sh 里缺少「{s}」这一段"
    assert pos == sorted(pos), f"run_tests.sh 的验证阶段顺序被打乱了：{list(zip(order, pos))}"


# ---------------------------------------------------------------------------
# 5 · 探针的输入是活的
# ---------------------------------------------------------------------------
def test_panel_probe_reports_48_controls_and_10_modules() -> None:
    """`--dump-geometry` 的输入必须是活的：控件 48、模块 10。

    少了这一条，上面所有断言都可能在一个"探针什么都没吐"的死版本上"通过"
    （解析器返回空表 → 循环体一次都不执行 → 绿）。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    m = re.search(r"^controls (\d+)$", r.stdout, re.M)
    assert m, f"--dump-geometry 没有 controls 行:\n{r.stdout}"
    ctrls = int(m.group(1))
    mods = len(re.findall(r"^mod ", r.stdout, re.M))
    assert ctrls == N_CONTROLS, f"控件 {ctrls} != {N_CONTROLS}"
    assert mods == N_NODES, f"模块 {mods} != {N_NODES}"


def test_ui_version_has_exactly_one_source() -> None:
    """出图文件名里的版本号必须来自**面板自己**，不许在工具里写死。

    实测过的坏法：面板已经做到 v0.33，`check_panel_render.py` 里 `--version`
    的默认值还停在 `0.32` —— 于是 `outputs/` 里躺着一批
    **名字说 v0.32、画的是 v0.33** 的图。它不报错，只是骗人，
    而"不报错的错"正是这一整套自检要防的东西。

    三条一起才说得清（少任何一条，分叉都能悄悄回来）：
      · 编译产物吐 `ui_version`（= 头文件里的 `kUiVersion`，面板版本的单一定义）；
      · 工具里 `--version` **没有默认值**（有默认值就一定会分叉）；
      · 工具真的把 `ui_version` 用上了。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    m = re.search(r"^ui_version (\S+)$", r.stdout, re.M)
    assert m, f"--dump-geometry 没有 ui_version 行（出图文件名就没有来源了）:\n{r.stdout[:400]}"
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", m.group(1)), \
        f"ui_version 长得不像版本号：{m.group(1)!r}"

    # 源码里的单一定义要和探针吐出来的一致 —— 否则"读的是编译产物"也没意义。
    hdr = strip_comments(read(PANEL_H))
    v = re.search(r'constexpr const char\* kUiVersion = "([^"]+)"', hdr)
    assert v, "TranePanel.h 里找不到 kUiVersion"
    assert v.group(1) == m.group(1), \
        f"头文件说 {v.group(1)}，编译产物说 {m.group(1)} —— 构建没跟上，先重编"

    src = strip_comments(read(TOOLS / "check_panel_render.py"))
    assert re.search(r'add_argument\("--version",\s*default=None', src), \
        "--version 又有默认值了 —— 默认值就是那个注定要分叉的写死版本号"
    assert 'geo["ui_version"]' in src, \
        "check_panel_render.py 没有从 geometryDump 取 ui_version"


# ---------------------------------------------------------------------------
# 6 · 数值列：宽度够不够、数字等不等宽
# ---------------------------------------------------------------------------
#
# 这一节盯的是一种**只能靠量**的坏法。数值是右对齐画的，而且走的是
# `drawText(..., useEllipsesIfTooBig = false)` —— 串太长**不截断、不缩字号**，
# 只会静静地往左爬进轨道区。于是"右缘齐平"那类断言永远绿。
#
# v0.33 之前列宽是按**字符数**估的（`最长字符数 × kValueW × 字号`），那个模型
# 两条前提都不成立（`kValueW = 0.60` 是平均值不是上界；41 个控件里有 10 个在
# 量程两端比默认值长）。现在列宽**直接量**，这里就用 201 个点的扫描来对账。
#
# 对应的反向对照是 `tools/check_metrics_mutations.py`（四处突变）。
_METRICS: dict | None = None


def dump_metrics() -> dict:
    """跑一次 `panel_probe --dump-metrics`，解析成 {字体, 字号, 列宽, 字符宽, 控件}。

    **模块级缓存**：201 个点 × 41 个控件 ≈ 0.9 秒，别在每条断言里重跑。

    与 `dump_text()` 同一条规矩：解析器一律带条数下限断言，**不许静默通过**。
    """
    global _METRICS
    if _METRICS is not None:
        return _METRICS
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")

    r = subprocess.run([str(PROBE), "--dump-metrics"],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr

    m: dict = {"glyphs": {}, "ctrl": {}, "vmetrics": {}}
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "font_value":
            m["font"] = p[1]
        elif p[0] in ("fs_value", "value_w"):
            m[p[0]] = float(p[1])
        elif p[0] == "glyph":
            m["glyphs"][p[1]] = float(p[2])
        elif p[0] == "ctrl":
            m["ctrl"][p[1]] = float(p[2])
        elif p[0] == "vmetric":
            # vmetric <id> <默认值字符数> <201 点里最长的字符数> <实测最大宽度> <那个串>
            m["vmetrics"][p[1]] = (int(p[2]), int(p[3]), float(p[4]), p[5])

    for k in ("font", "fs_value", "value_w"):
        assert k in m, f"--dump-metrics 没有 {k} 行（解析器会空转通过）:\n{r.stdout[:400]}"
    assert set(m["ctrl"]) == {"i", "M"}, \
        f"正向对照字符不是 i / M：{sorted(m['ctrl'])}"
    assert len(m["vmetrics"]) == N_PARAM_ROWS, \
        f"数值列收到 {len(m['vmetrics'])} 个控件，应为 {N_PARAM_ROWS}（参数行数）"
    # 下限：10 个数字 + 小数点 / 正号 / 负号 + 8 个单位字母 = 21。
    # （正向对照那两个字符走 `ctrl` 行，**不算**在这张表里。）
    assert len(m["glyphs"]) >= 21, \
        f"只收到 {len(m['glyphs'])} 个字符宽度（下限 21）—— 度量表被截断了"
    # 覆盖面：**数值串里真的出现过的每一个字符，都必须有实测宽度**。
    # 字符集从 vmetrics 的串里收集，不在这里另抄一份清单 —— 另抄一份就会
    # "加了单位字母、这里忘了跟着加"，于是新字符的宽度没人量、列宽漏算它。
    used = {ch for _d, _n, _w, s in m["vmetrics"].values() for ch in s}
    missing = sorted(used - set(m["glyphs"]))
    assert not missing, (
        f"这些字符出现在数值串里，度量表里却没有它们的宽度：{missing} —— "
        f"数值列宽就漏算了它们（补进 `metricsDump()` 的字符表）")
    assert m["value_w"] > 0.0, f"数值列宽是 {m['value_w']}"

    _METRICS = m
    return m


def test_value_column_fits_every_value() -> None:
    """**每个控件在量程里能显示的最长数值串，都必须放得进数值列宽。**

    这是"数值不会爬进轨道区"的**充要条件**：数值右对齐在栏的右缘，轨道右缘在
    `栏右缘 − valueW − kGap`，所以只要 `最宽串 ≤ valueW`，两者之间就还留着
    kGap 那么宽的空档（和"名字 ─ 轨道"那个间隔一样宽）。

    量的是**201 个点**，而布局自己只采 6 个点 —— 于是这条断言**严格强于**
    布局自己的保证：布局漏掉的中间点这里会抓到。
    `check_metrics_mutations.py` 的 M1（只采出厂值）与 M3（只有中间点更宽）
    就是专门证明这一点的。
    """
    m = dump_metrics()
    vw = m["value_w"]

    over = [(cid, w, widest) for cid, (_d, _n, w, widest) in m["vmetrics"].items()
            if w > vw + 1e-6]
    assert not over, (
        f"有 {len(over)} 个控件的数值串比数值列宽（{vw:.3f}px）还宽 —— "
        f"它们会**静静地**爬进轨道区（右对齐 + 不截断，看不出来）：\n  "
        + "\n  ".join(f"{cid}: {w:.3f}px  {widest!r}" for cid, w, widest in over))

    # 非空转（另一半）：列宽必须**正好**由最宽那个串定 —— 宽了是白扔轨道长度，
    # 窄了就是上面那种坏法。而且这个"正好"同时证明了一件事：布局那 6 个采样点
    # 扫到的最宽串，和这 201 个点扫到的是同一个 —— 6 个点够用。
    widest = max(w for _d, _n, w, _ in m["vmetrics"].values())
    assert abs(vw - widest) <= 1e-6, (
        f"数值列宽 {vw:.3f} != 实测最宽串 {widest:.3f} —— "
        f"列宽必须由最宽那个串定；两者不等还说明布局的采样点与这里的扫描点分叉了")

    # 列宽还必须是**布局真的在用的**那个数（不是探针另算一份）。四栏共享同一个值
    # —— 逐栏各算一份的话，轨道起点会跟着栏跳。
    r = subprocess.run([str(PROBE), "--dump-layout"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    cols = [float(x) for x in re.findall(r"^col \d+ .*? valueW ([\d.]+)", r.stdout, re.M)]
    assert len(cols) == 4, f"--dump-layout 里读不到四栏的 valueW:\n{r.stdout[:400]}"
    # **容差是"半格"，不是"零"**：两份 dump 的精度不一样 ——
    # `--dump-metrics` 的 `value_w` 打 4 位小数，`--dump-layout` 的 `valueW` 打 3 位。
    # 于是同一个数会差最多 5e-4（v0.35 实测踩到：39.2899 对 39.290，
    # 差 1e-4，把原来 1e-6 的容差踩红了）。这里量的**不是**精度，
    # 而是"两边是不是同一个数" —— 真分叉的话差的是整数级的量，5e-4 一样抓得住。
    DUMP_EPS = 5e-4
    assert all(abs(c - vw) <= DUMP_EPS for c in cols), (
        f"探针自述的列宽 {vw:.4f} 与 --dump-layout 的四栏 {cols} 对不上 —— "
        f"说明有一边在另算一份（容差 {DUMP_EPS} = 两份 dump 精度里较粗那档的半格）")

    cid, (def_n, max_n, _w, widest_s) = max(m["vmetrics"].items(), key=lambda kv: kv[1][2])
    print(f"\n  数值列宽 {vw:.3f}px = 实测最宽串 {widest:.3f}px"
          f"（{cid} {widest_s!r}，{max_n} 字符）"
          f"，字体 {m['font']} {m['fs_value']:.2f}pt")


def test_value_digits_are_tabular() -> None:
    """数值必须用**等宽数字**（tabular figures）—— 否则右对齐也救不了那列数字。

    比例字体里 `1` 比 `0` 窄，于是

        0.10
        0.31
        0.99

    的小数点不在一条竖线上，右对齐只对齐了最后一个字符 —— 一列数字读起来会"抖"。
    这是**一眼就能看出来**的排版问题（小绪：「所有排版都必须要整齐」）。

    Ableton Sans 是比例字体，但它的十个数字恰好等宽（实测全是 5.6840px）。
    这条断言把这个"恰好"钉住：哪天换了字体、或者有人给某几个数字单独设宽度，
    它会报红。

    配一条**正向对照**（`ctrl.i != ctrl.M`）：证明"量宽度"这件事真的在量。
    少了它，一个恒返回常数的桩也能让上面全绿 —— `check_metrics_mutations.py`
    的 M4 就是这么打的。
    """
    m = dump_metrics()
    g = m["glyphs"]
    ctrl = m["ctrl"]

    by_width: dict[float, list[int]] = {}
    for d in range(10):
        ch = str(d)
        assert ch in g, f"度量表里没有字符 {ch!r}"
        by_width.setdefault(round(g[ch], 4), []).append(d)
    assert len(by_width) == 1, (
        "数字不是等宽的 —— 右对齐的一列数字看起来还是会锯齿状：\n  "
        + "\n  ".join(f"{w}px: {''.join(str(d) for d in ds)}"
                      for w, ds in sorted(by_width.items())))

    # 正向对照：`i` 与 `M` 在任何比例字体里宽度都必然不同。
    assert ctrl["i"] != ctrl["M"], (
        f"`i` 和 `M` 量出了同一个宽度（{ctrl['i']}）—— "
        f"说明这里量的根本不是字宽，上面那条「数字等宽」也就没有意义")

    # 非空转：得真的有数值串用上了数字，否则"数字等宽"量到的样本太少。
    with_digits = [cid for cid, (_d, _n, _w, s) in m["vmetrics"].items()
                   if any(ch.isdigit() for ch in s)]
    assert len(with_digits) >= 30, (
        f"只有 {len(with_digits)} 个控件的数值串里有数字 —— 样本太少，"
        f"「数字等宽」这条断言量不到什么")

    dw = next(iter(by_width))
    print(f"\n  十个数字等宽 {dw}px；`i` {ctrl['i']}px ≠ `M` {ctrl['M']}px"
          f"（{len(with_digits)} 个控件的数值串里含数字）")


# ---------------------------------------------------------------------------
# 7 · 控件形态：哪 12 个参数画成旋钮（v0.34）
# ---------------------------------------------------------------------------
_KNOBS: dict | None = None


def dump_knobs() -> dict:
    """跑一次 `--dump-geometry` + `--dump-layout`，取形态相关的全部事实。

    返回：
        `{"modules": [探针自述的旋钮模块…], "module_count": 探针自述的模块个数,
          "ids": [展开后的参数行 id…], "count": 探针自述的行个数,
          "ctl": {id: (node, slot)},    # slot == -1 = 模块开关
          "rows": {node: 参数行数},
          "names": {node: 模块名},
          "choices": [带分段选择的 id…],
          "cols": [[node…]…]}`          # 四栏各自装了哪些模块

    **模块级缓存**：这些断言都要它，而且它是"编译产物有没有跟上"的判据 ——
    反复跑只会让失败信息更长。
    """
    global _KNOBS
    if _KNOBS is not None:
        return _KNOBS
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")

    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr

    k: dict = {"modules": [], "module_count": -1, "ids": [], "count": -1,
               "ctl": {}, "rows": {}, "names": {}, "choices": [], "cols": []}
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "knob_modules":
            # knob_modules <个数> <模块名…>
            k["module_count"] = int(p[1])
            k["modules"] = p[2:]
        elif p[0] == "knobs":
            # knobs <个数> <id…>
            k["count"] = int(p[1])
            k["ids"] = p[2:]
        elif p[0] == "choices":
            # choices <id…>
            k["choices"] = p[1:]
        elif p[0] == "mod":
            # mod <节点序号> <质点名> <模块名> <参数行数>（v0.35 加了序号）
            assert len(p) == 5 and p[1].isdigit(), (
                f"mod 行的格式变了：{line!r}\n"
                f"  期望 `mod <节点序号> <质点名> <模块名> <参数行数>`。\n"
                f"  **先在这里报**，不要让它掉进下面的 int() 里变成 "
                f"'invalid literal for int()' —— 那个报错看不出是格式问题。")
            node = int(p[1])
            k["names"][node] = p[3]
            k["rows"][node] = int(p[4])
        elif p[0] == "ctl":
            # ctl <id> <node> <slot> [短名]
            k["ctl"][p[1]] = (int(p[2]), int(p[3]))

    # 栏切分从 `--dump-layout` 读（**不在这里抄一份**）。见常量区那段注释。
    rl = subprocess.run([str(PROBE), "--dump-layout"],
                        capture_output=True, text=True, timeout=60)
    assert rl.returncode == 0, rl.stderr
    for line in rl.stdout.splitlines():
        p = line.split()
        if p and p[0] == "col":
            # col <i> x <…> nodes <n…>  —— nodes 是最后一段
            assert "nodes" in p, f"col 行里没有 nodes 段：{line}"
            k["cols"].append([int(x) for x in p[p.index("nodes") + 1:]])

    assert k["module_count"] >= 0, \
        f"--dump-geometry 没有 knob_modules 行（这条检查会空转）:\n{r.stdout[:400]}"
    assert k["count"] >= 0, \
        f"--dump-geometry 没有 knobs 行（这条检查会空转）:\n{r.stdout[:400]}"
    assert len(k["cols"]) == 4, f"col 行收到 {len(k['cols'])} 条，应为 4"
    assert len(k["ctl"]) == N_CONTROLS, \
        f"ctl 行收到 {len(k['ctl'])} 条，应为 {N_CONTROLS}"
    assert len(k["rows"]) == N_NODES, f"mod 行收到 {len(k['rows'])} 条，应为 {N_NODES}"
    assert sum(k["rows"].values()) == N_PARAM_ROWS, \
        f"各模块参数行合计 {sum(k['rows'].values())} != {N_PARAM_ROWS}"

    _KNOBS = k
    return k


def knob_modules_from_header() -> list[str]:
    """头文件 `kKnobModules[]` 里的模块名，按书写顺序。"""
    hdr = strip_comments(read(PANEL_H))
    blk = re.search(r"kKnobModules\[\]\s*=\s*\{(.*?)\};", hdr, re.S)
    assert blk, "TranePanel.h 里找不到 kKnobModules[]"
    # 每一行是 `"freeze",   // 冻多久 —— …`，注释已经被 strip_comments 去掉
    return re.findall(r'"([^"]+)"', blk.group(1))


def test_knob_module_list_matches_the_header_and_every_id_resolves() -> None:
    """旋钮**模块**清单必须与头文件 `kKnobModules` 逐条一致，而且**展开后**的
    每条 id 都真的落在控件上、且不是模块开关。

    三件事，防三种不同的坏法：

      · **对模块清单** —— 防"探针和头文件分叉"（改了头文件没重编）。
        这时别的一切都绿。
      · **查展开对不对** —— 这是 v0.35 新增的一条真闸门。判据从"这个 id 在
        清单里吗"变成"它所属的**模块**在清单里吗"，中间多了一跳。
        这里用 Python **独立重推**一遍展开（`ctl` 的 node → `mod` 的模块名 →
        是否在清单里），和探针吐的 `knobs` 行比对。重推用的是两张原始表，
        不是同一段 C++ 代码 —— 所以 `moduleIsKnob()` 写错（比如拿
        `kNodes[i].module` 去比却用错了下标）会当场露馅。
      · **查 id 能不能解析** —— 拼错一个模块名（`grian`）不会崩：
        `knobModuleFlags()` 里对找不到的模块名只有一个 `jassert`，Release 下
        没有，于是**整个模块的旋钮静默消失** —— 界面上八行从圆环变成长条，
        而 `knob_modules` 行照样把拼错的模块名列出来（它读的是同一张表）。
        **只对清单是抓不到这种错的。**
    """
    k = dump_knobs()
    modules, ids = k["modules"], k["ids"]

    assert len(modules) == k["module_count"], \
        f"knob_modules 行自述 {k['module_count']} 个，实际列出 {len(modules)} 个：{modules}"
    assert k["module_count"] == N_KNOB_MODULES, \
        f"旋钮模块 {k['module_count']} 个，期望 {N_KNOB_MODULES} —— " \
        f"形态分配变了就同步改这里（故意的）"

    in_header = knob_modules_from_header()
    assert in_header == modules, (
        f"头文件 kKnobModules 与编译产物分叉：\n  头文件 {in_header}\n  产物   {modules}\n"
        f"（改了头文件没重编？）")
    assert modules == KNOB_MODULES, (
        f"旋钮模块清单变了：{modules}\n  期望 {KNOB_MODULES}\n"
        f"**这是个设计决定**，不是重构 —— 想清楚「这个模块是调出来的还是"
        f"配出来的」再动它")

    # 模块名必须都能解析到某个 node
    unresolved_mod = [m for m in modules
                      if m not in set(k["names"].values())]
    assert not unresolved_mod, (
        f"这些模块名在 kNodes 里不存在：{unresolved_mod} —— 拼错了。"
        f"Release 下整个模块的旋钮会**静默消失**，别的一切正常")

    # ---- 独立重推展开结果 ----
    knob_mods = set(modules)
    expect = sorted(cid for cid, (node, slot) in k["ctl"].items()
                    if slot >= 0 and k["names"][node] in knob_mods)
    assert sorted(ids) == expect, (
        f"展开后的旋钮行与独立重推不符：\n"
        f"  探针 knobs   {sorted(ids)}\n"
        f"  重推         {expect}\n"
        f"（`isKnob()` 的「控件 → 模块 → 清单」两跳有一跳写错了？）")

    assert len(ids) == k["count"], \
        f"knobs 行自述 {k['count']} 个，实际列出 {len(ids)} 个：{ids}"
    assert k["count"] == N_KNOB_ROWS, \
        f"旋钮参数行 {k['count']} 个，期望 {N_KNOB_ROWS} —— " \
        f"模块的参数个数变了就同步改这里（故意的）"

    unresolved = [i for i in ids if i not in k["ctl"]]
    assert not unresolved, (
        f"这些 id 在展开结果里，却不对应任何控件：{unresolved} —— "
        f"拼错了。Release 下它们会**静默失效**（界面上少一个旋钮，别的一切正常）")
    switches = [i for i in ids if k["ctl"][i][1] == -1]
    assert not switches, \
        f"这些是模块开关，不能当旋钮：{switches}（开关住在标题行，没有轨道）"

    print(f"\n  {k['module_count']} 个旋钮模块 → {k['count']} 个旋钮行，"
          f"全部解析成功：{' '.join(modules)}")


def test_a_choice_parameter_forbids_a_knob_module() -> None:
    """**带分段选择（`Fmt::Choice`）的模块不能是全旋钮模块。**

    这不是审美，是**一致性**：`drawParamRow()` 的分支顺序是

        if (c.fmt == Fmt::Choice)  { …分段块… }
        else if (isKnob(r.control)) { …旋钮… }
        else                        { …条形… }

    于是 `Fmt::Choice` 的行**永远**画成分段块，`isKnob()` 对它说什么都不影响
    画面。但探针的 `knobs` 行是 `isKnob()` 的直接产物 —— 一旦 SWEEP 被列进
    `kKnobModules`，`knobs` 行会多出一个 `sweep_mode`，**而像素上它还是分段块**。

    后果是**检查器与实现在打架**：`check_panel_render.py` 按 `knobs` 分类，
    会把 `sweep_mode` 那一行当旋钮去找环，找不到 → 报一个**假的 ✗**。
    假报红比漏报更坏：它逼着下一个人把阈值调松，把真断言一起废掉。

    现在只有 SWEEP 一个模块带 `Fmt::Choice`，所以它**必须是**条形模块。
    """
    k = dump_knobs()
    knob_mods = set(k["modules"])

    assert k["choices"], "探针没吐 choices 行（这条检查会空转）"

    bad = [cid for cid in k["choices"] if k["names"][k["ctl"][cid][0]] in knob_mods]
    assert not bad, (
        f"这些分段选择控件所属的模块被列进了 kKnobModules：{bad}\n"
        f"  它们画出来是**分段块**（`drawParamRow` 的 `Fmt::Choice` 分支先命中），\n"
        f"  但 `knobs` 行会把它们列成旋钮 —— 检查器会去找一个不存在的环，\n"
        f"  报一个假的 ✗。把这个模块从 kKnobModules 里去掉。")

    for cid in k["choices"]:
        assert cid not in k["ids"], \
            f"{cid} 是分段选择，不该出现在 knobs 行里"

    print(f"\n  {len(k['choices'])} 个分段选择控件都不在旋钮模块里：{' '.join(k['choices'])}")


def test_no_column_mixes_forms() -> None:
    """**同一栏里不许混形态** —— 一栏要么全是"拧的"，要么全是"读的"。

    这条是 v0.35 定形态判据时顺手加上的硬约束。为什么值得一条断言：

    面板四栏并排，人眼是**按栏**扫的。一栏里如果前三个模块是旋钮、第四个是
    条形，那一栏就同时有"环"和"尺"两种形状在竖直方向交替 —— 眼睛会把形状
    当成第二个维度去读，于是它读成"前三个是一类、第四个是另一类"，
    而实际上它们只是碰巧被切到了同一栏。

    现有的四栏切分 `{0,1} {2,3,4} {5,6} {7,8,9}` 正好把五个"调出来的"模块
    （FREEZE / GRAIN / STUTTER / COMB / TAPE）放在左两栏、五个"配出来的"
    放在右两栏 —— 于是面板的阅读顺序是**左边拧、右边读**。

    栏切分从 `--dump-layout` 读，**不在这里抄一份**：抄一份的话，改了切分
    而这里没改，这条断言会对着**旧的栏**去查 —— 绿得毫无意义。
    """
    k = dump_knobs()
    knob_mods = set(k["modules"])

    bad: list[str] = []
    for ci, nodes in enumerate(k["cols"]):
        forms = [k["names"][n] in knob_mods for n in nodes]
        if any(forms) and not all(forms):
            bad.append(f"栏 {ci}: " + " / ".join(
                f"{k['names'][n]}{'*' if f else ''}"
                for n, f in zip(nodes, forms)))

    assert not bad, (
        "这些栏里混了形态（`*` = 全旋钮模块）：\n  " + "\n  ".join(bad)
        + "\n要么把模块挪到另一栏，要么把它整个换成同一种形态 ——"
          "**先想清楚判据为什么变，再动它**")

    n_knob_cols = sum(1 for nodes in k["cols"]
                      if nodes and all(k["names"][n] in knob_mods for n in nodes))
    n_bar_cols = sum(1 for nodes in k["cols"]
                     if nodes and not any(k["names"][n] in knob_mods for n in nodes))
    assert n_knob_cols + n_bar_cols == len(k["cols"]), \
        f"有栏既不是全旋钮也不是全条形（上面的 bad 应该已经报了）"

    print(f"\n  四栏形态：{n_knob_cols} 栏全旋钮 / {n_bar_cols} 栏全条形，没有混的")


# **删掉了一条**：`test_knob_rows_form_one_contiguous_run_per_module`。
#
# 它守的是"同一模块里旋钮行必须连成一段"。v0.34 需要它，因为判据是**逐参数**
# 的（"带单位 → 旋钮"），所以模块内的形态是**碰巧**连成一段的，行序一动就散。
#
# v0.35 把判据改成**按模块**之后，`isKnob(index)` 走
# `control → node → moduleIsKnob(node)` —— **同一模块内形态不可能不一致，
# 这是构造上保证的**。留着那条断言只会留下一条**永远为真**的检查：
# 它不报红不是因为被守护的东西是对的，而是因为它已经不可能错了。
# 那种断言比没有更坏 —— 它让人以为这里还有覆盖。
#
# 替换它的是上面两条：`test_a_choice_parameter_forbids_a_knob_module`（守
# "机器可读的形态声明"与"实际画出来的形状"一致）和 `test_no_column_mixes_forms`
# （守栏级的形态纯度）。




# ---------------------------------------------------------------------------
# §8 面板字体（v0.35）
# ---------------------------------------------------------------------------
# 用户要求"字体也要用 Lux Cache 同款"。取证结果：Lux Cache 自托管的是
# **Suisse Neue / Suisse Int'l**（Swiss Typefaces，商业授权、EULA 禁止再分发），
# 本机也没装。所以打包的是**最接近的开源替代**：Inter（OFL-1.1）在 `opsz=14`
# 下抽的两个静态实例，改名 `Trane Sans`。选型与字重的实测依据见
# `assets/fonts/PROVENANCE.md`。
#
# 这一节守什么、为什么非守不可
# ==========================
# 换字体**只改文字的墨迹，不改任何一条几何** —— 列宽是按字体量出来的，
# 所以连数值都不动。于是"字体悄悄降级成系统字体"这件事，**前面所有断言
# 一个都抓不到**：几何全对、对比度全对、形态全对，字却换了。
#
# 唯一能抓它的办法是**直接量字**：问字体叫什么，再量一个只有这份字体
# 才量得出来的宽度。两条都要 —— 名字证明"是打包那份"，宽度证明"是**对的那份**"
# （两个字面的 family 名都是 `Trane Sans`，光看名字分不出 Regular 和 SemiBold）。

FONT_PROBE = "MIX"            # 与 TranePanel.h 的 `kFontProbeText` 同一串


def parse_font_lines() -> dict[str, tuple[str, float, float]]:
    """从 `--dump-geometry` 读 `font_ui` / `font_data` 两行。

    返回 `{face: (字体名, 字号, 探针串实测宽度)}`。

    **解析要从右往左**：字体名是 `Trane Sans`，**中间有空格** ——
    按位置硬切会把它切成两半（实测踩过：`p[1]` 拿到的是 `Trane`）。
    右边两个字段永远是字号和宽度。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr

    out: dict[str, tuple[str, float, float]] = {}
    for line in r.stdout.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] in ("font_ui", "font_data"):
            out[p[0]] = (" ".join(p[1:-2]), float(p[-2]), float(p[-1]))

    assert set(out) == {"font_ui", "font_data"}, (
        f"`--dump-geometry` 没吐全 font_ui / font_data 两行（收到 {sorted(out)}）"
        f"—— 这一节的断言会空转")
    return out


def test_panel_uses_the_bundled_fonts() -> None:
    """面板两个字面都必须是**打包内嵌**的 `Trane Sans`。

    旧代码是"运行时读 Ableton Live 安装目录里的 AbletonSans-Bold.otf，
    读不到就降级 Helvetica Neue **Bold**"。实测：Ableton Bold 的竖干是 35.68，
    Helvetica Neue Bold 是 43.86 —— **重 23%**。于是"用户装没装 Ableton"
    会整档改变面板标题的字重，而**没有任何断言能发现**（断言量的都是几何）。

    这条断言就是那个"没有"。它检查的是名字：系统字体不会叫 `Trane Sans`，
    所以只要名字对，就一定是打包那份。
    """
    fonts = parse_font_lines()
    for face, (name, _h, _w) in sorted(fonts.items()):
        assert name == "Trane Sans", (
            f"{face} 用的字体是 {name!r}，不是打包的 'Trane Sans' ——\n"
            f"  面板正在用系统字体渲染。**这不会让任何一条几何断言报红**：\n"
            f"  列宽是按字体量的，换了字体排版自动适配，数值一个都不变。\n"
            f"  查 TranePanel.cpp 的 `uiTypeface()` / `dataTypeface()`：\n"
            f"  它们在 Debug 下会 jassert，Release 下会退到 JUCE 默认字体 ——\n"
            f"  退到默认字体**不是**静默的，就是这一条在报。")

    print(f"\n  面板字体：ui={fonts['font_ui'][0]!r} data={fonts['font_data'][0]!r}")


def test_panel_font_metrics_match_the_bundled_files() -> None:
    """面板实测的探针串宽度，必须与打包 .ttf 复算出来的一致（容差 1%）。

    **这条比"名字对"更强**：两个字面的 family 名都是 `Trane Sans`，
    名字对只证明"是打包的那两份之一"。要证明"用的是**对的那一份**"，
    只能量一个随字重变化的数。

    探针串是 `MIX`（`TranePanel.h` 的 `kFontProbeText`）—— 四个模块各有一行
    `MIX`，大写画出来就是它。**选它是因为它信号最强**：实测两个字重的前进
    宽度差 **2.24%**，而 `"GRAIN DENSITY"` 只有 0.94%、
    `"STUTTER FEEDBACK"` 0.74%。

    **第一版探针是 `"0123456789"`，是错的**：面板的数字被改成了**等宽**
    （`build_panel_fonts.py` 的 `make_digits_tabular`，见
    `test_value_digits_are_tabular`），而等宽之后两个字重的数字几乎一样宽
    （SemiBold 1325 vs Regular 1327 单位）—— 偏差只有 0.15%，
    拿它当探针等于没探。这条是实测踩出来的，记在这儿免得有人换回去。

    容差 1% 的两侧余量：复算的**系统性偏差**实测 0.00%（`MIX` 全是大写字母，
    CoreText 不取整），拿错字重的**信号**是 ±2.2% —— 容差是它的 1/2。

    复算用 `hmtx` 的前进宽度之和，除以 `hhea` 的 ascent−descender，再乘字号。
    探针量的时候字距给 0，所以不需要解析 GPOS。
    """
    fonts = parse_font_lines()

    # 面板上哪一支字面对应哪个文件 —— **这是断言的一部分**：
    # 搞反了就是"标题用正文的字重、正文用标题的"，而名字检查抓不到。
    want = {"font_ui": "TraneSans_SemiBold.ttf",
            "font_data": "TraneSans_Regular.ttf"}

    for face, filename in want.items():
        path = FONT_DIR / filename
        assert path.is_file(), f"找不到 {path}"
        t = TTFont(str(path), lazy=True)
        cmap = t.getBestCmap()
        hmtx = t["hmtx"]
        missing = [c for c in FONT_PROBE if cmap.get(ord(c)) is None]
        assert not missing, f"{filename} 缺字形：{missing!r}（子集切过头了？）"
        units = sum(hmtx[cmap[ord(c)]][0] for c in FONT_PROBE)
        ad = t["hhea"].ascender - t["hhea"].descender
        assert ad > 0, f"{filename} 的 hhea ascender/descender 不合理：{ad}"

        _name, height, got = fonts[face]
        expect = units / ad * height
        dev = (got - expect) / expect

        # 正向对照：同一支字面换个字重，偏差必须**超出**容差 ——
        # 少了这一步，一个"容差开得比信号还大"的版本也能一路绿。
        other = ("TraneSans_Regular.ttf" if filename == "TraneSans_SemiBold.ttf"
                 else "TraneSans_SemiBold.ttf")
        t2 = TTFont(str(FONT_DIR / other), lazy=True)
        cm2, hm2 = t2.getBestCmap(), t2["hmtx"]
        u2 = sum(hm2[cm2[ord(c)]][0] for c in FONT_PROBE)
        ad2 = t2["hhea"].ascender - t2["hhea"].descender
        dev_wrong = (u2 / ad2 * height - expect) / expect
        assert abs(dev_wrong) > 0.02, (
            f"正向对照失败：拿错字重只偏 {dev_wrong * 100:+.2f}%，"
            f"压不过 1% 的容差 —— 这条断言对'字重搞反'是瞎的。"
            f"换一个随字重变化更大的探针串。")

        assert abs(dev) <= 0.01, (
            f"{face} 的实测宽度与 {filename} 复算不符：\n"
            f"  面板实测 {got}（字号 {height}）\n"
            f"  文件复算 {expect:.4f}\n"
            f"  偏差     {dev * 100:+.3f}%（容差 ±1%）\n"
            f"  拿错字重会偏 {dev_wrong * 100:+.3f}%\n"
            f"查 `uiTypeface()` / `dataTypeface()` 挂的是哪个二进制块。")

        print(f"\n  {face}: {filename} 实测 {got} vs 复算 {expect:.4f} "
              f"（偏差 {dev * 100:+.3f}%）")


def test_the_bundled_fonts_are_static_instances() -> None:
    """打包的必须是**静态**实例 —— 不能留 `fvar` 可变轴。

    Inter 上游是可变字体（`opsz` / `wght` 两个轴）。JUCE 的
    `Typeface::createSystemTypefaceFor()` 拿到可变字体时只会用**默认实例**，
    而 Inter 的 `wght` 默认值是 **400** —— 于是 SemiBold 那一支会静默变成
    Regular，标题和正文一样重。界面看着"还行"，断言全绿。

    生成脚本 `tools/build_panel_fonts.py` 里已经用 `varLib.instancer` 抽成了
    静态实例，这一条守的是"别把上游那个可变文件直接丢进来"。
    """
    for filename in ("TraneSans_SemiBold.ttf", "TraneSans_Regular.ttf"):
        path = FONT_DIR / filename
        assert path.is_file(), f"找不到 {path}"
        t = TTFont(str(path), lazy=True)
        assert "fvar" not in t, (
            f"{filename} 还是可变字体（有 fvar 轴）——\n"
            f"  JUCE 只会拿默认实例，字重会静默变成默认那个值。\n"
            f"  用 tools/build_panel_fonts.py 重新生成静态实例。")
        assert t["name"].getDebugName(1) == "Trane Sans", (
            f"{filename} 的 family 名是 {t['name'].getDebugName(1)!r}，"
            f"应为 'Trane Sans' —— 名字对不上，`test_panel_uses_the_bundled_fonts` "
            f"那条就没法用名字证明任何事")
        assert t["name"].getDebugName(2) in ("SemiBold", "Regular"), \
            f"{filename} 的 style 名不对：{t['name'].getDebugName(2)!r}"

    print("\n  两个字面都是静态实例，family 名一致，style 名分开")


def test_panel_fonts_cover_the_declared_text_inventory() -> None:
    """面板**自己会写的**每一个字符，打包字体都必须有字形。

    少了就是界面上的一个**豆腐块**（`.notdef`）—— 而那玩意儿不会让任何一条
    断言报红：几何照旧、对比度照旧（豆腐块也是墨）。

    清单（`--dump-geometry` 的 `text_inventory`）是从**控件表 + 固定文案**
    算出来的，不是手抄的字符集。加一个 label / unit 就自动进清单，
    然后这条断言会立刻要求字体覆盖它。

    **范围**：只含面板自己写的字。用户选的图片文件名（`bd.name`）会被画在
    顶栏上，但那是**用户数据**，字体覆盖不了它 —— 所以它不在这份清单里，
    这条断言也就不对它作任何承诺。

    v0.35 写这份清单时**真的抓到过一个**：背景亮度的读数是 `String(...) + "×"`，
    `×` 是 **U+00D7**，不是 ASCII 的 `x` —— 也就是说
    `TranePanel.cpp` 里那句"文案一律 ASCII"一直是**不准确的**。
    它没出过事，只因为换字体之前那款字体恰好有 `×` 这个字形。
    """
    if not PROBE.is_file():
        pytest.skip(f"没找到 {PROBE}（先跑 cmake --build build）")
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr

    inv = None
    for line in r.stdout.splitlines():
        if line.startswith("text_inventory "):
            inv = line[len("text_inventory "):]
    assert inv is not None, "--dump-geometry 没有 text_inventory 行（这条会空转）"
    assert len(inv) >= 40, f"清单只有 {len(inv)} 个字符，太小了（解析错了？）"

    # 非 ASCII 只允许那一个乘号 —— 多出来的必须有人解释
    non_ascii = sorted({c for c in inv if ord(c) > 126})
    assert non_ascii == ["\u00D7"], (
        f"面板文案里出现了非 ASCII 字符：{[ (c, hex(ord(c))) for c in non_ascii ]}\n"
        f"  面板自己写的字只允许一个例外：亮度读数的乘号 U+00D7。\n"
        f"  别的非 ASCII 字符要么换成 ASCII，要么在 `textInventory()` 里\n"
        f"  **显式加进去并说明理由** —— 打包字体没有 CJK 字形，\n"
        f"  写中文会渲染成一串乱码（用户实测截图里有过）。")

    for filename in ("TraneSans_SemiBold.ttf", "TraneSans_Regular.ttf"):
        t = TTFont(str(FONT_DIR / filename), lazy=True)
        cmap = t.getBestCmap()
        missing = [c for c in inv if cmap.get(ord(c)) is None]
        assert not missing, (
            f"{filename} 覆盖不了面板文案里的这些字符：\n"
            f"  {[(c, hex(ord(c))) for c in missing]}\n"
            f"  它们会渲染成豆腐块，而**没有任何一条几何断言会报红**。\n"
            f"  修法：跑 tools/build_panel_fonts.py 重新生成（它会按\n"
            f"  TranePanel.cpp::textInventory() 的口径扩子集）。")

    print(f"\n  {len(inv)} 个字符，两个字面全部覆盖；"
          f"非 ASCII 只有 U+00D7（亮度读数的乘号）")


def test_the_bundled_font_licences_are_shipped() -> None:
    """OFL 要求分发时带上许可与版权声明 —— 这是**合规**，不是文档洁癖。

    `assets/fonts/OFL.txt` 是上游 Inter 的许可原文（SIL Open Font License 1.1），
    `PROVENANCE.md` 记着字体从哪来、怎么再生成、以及为什么改名。
    两个文件都要在，而且 OFL 里必须真的写着 "SIL Open Font License"。
    """
    ofl = FONT_DIR / "OFL.txt"
    prov = FONT_DIR / "PROVENANCE.md"
    assert ofl.is_file(), f"找不到 {ofl} —— OFL 要求随字体一起分发许可原文"
    assert prov.is_file(), f"找不到 {prov} —— 字体来源与再生成方法没有记录"

    text = ofl.read_text(encoding="utf-8")
    assert "SIL Open Font License" in text, "OFL.txt 里没有许可名，拿错文件了？"
    assert "Copyright" in text, "OFL.txt 里没有版权声明"

    ptext = prov.read_text(encoding="utf-8")
    for needle in ("Inter", "Suisse Neue", "build_panel_fonts.py"):
        assert needle in ptext, (
            f"PROVENANCE.md 里没提到 {needle!r} —— 来源说明不完整"
            f"（上游是什么、参照是什么、怎么再生成，三样都要有）")

    print(f"\n  {ofl.name} + {prov.name} 都在")
