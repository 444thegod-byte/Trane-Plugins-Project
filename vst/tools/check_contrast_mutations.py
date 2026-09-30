#!/usr/bin/env python3
"""反向对照驱动器 —— 故意改坏对比度与块布局相关的代码，确认自检**真的**报红。

    python3 tools/check_contrast_mutations.py

"绿本身不是证据"：新加的断言必须证明它能抓到错误，否则它只是装饰。
每一处突变都改回**上一版真实的错误值**，不是随便编的数。
v0.25 起也覆盖"块"这一类：块高、块数、块底对齐、块底色、块内文字的底。

它只做三件事：把 render_ui_dark_panel.py 的源码复制到 **/tmp**、按规则改坏一行、
跑一遍它的自检。原文件与仓库全程只读，不留任何产物。
失败原因照抄**最后一行含 Error 的输出**（AssertionError 会把现场、α、底色、比值都带上）；
**没有任何错误行的失败**（超时、被信号杀）标成"非断言失败" ——
不许当成"断言抓住了"糊过去，那种假绿比不测还糟。
"""
from __future__ import annotations

import io
import os
import pathlib
import subprocess
import sys
import tempfile
import tokenize

SRC = pathlib.Path(__file__).resolve().parent / "render_ui_dark_panel.py"
PY = sys.executable
TOOLS = SRC.parent

# (说明, 原文, 改坏后)
MUTATIONS: list[tuple[str, str, str]] = [
    ("关闭态文字退回 Apple 的 tertiaryLabel 0.30（黑底只有 2.23:1）",
     'A_OFF = 0.56', 'A_OFF = 0.30'),
    ("关闭态模块名退回 0.34（上一版的真值）",
     '    op = A_TEXT if active else A_OFF\n', '    op = A_TEXT if active else 0.34\n'),
    ("分段控件的选中块调亮到 systemGray2 浅色（选中标签压不住）",
     'GRAY2 = "#636366"', 'GRAY2 = "#AEAEB2"'),
    ("分段选中标签退回 0.56（压不住 systemGray2）",
     '                log_text(A_TEXT, "seg_on")\n                ta = A_TEXT',
     '                log_text(A_TEXT, "seg_on")\n                ta = A_OFF'),
    ("禁用态分段退回 FAINT 当文字色",
     '            a = A_OFF if disabled else A_MUTED',
     '            a = A_TICK if disabled else A_MUTED'),
    # 这一处专门打**登记表对账**：只改绘制出来的 fill-opacity，不动 log_text。
    # 对比度断言查的是登记表，所以只有"SVG 与登记表必须一致"那一条能抓住它。
    ("只改绘制、不改登记表（0.56 的登记表 vs 0.60 的 SVG）",
     'f\'fill-opacity="{op:.2f}">{module.upper()}</text>\'',
     'f\'fill-opacity="0.60">{module.upper()}</text>\''),
    # 这一处打的是"文字压在哪块面上"那条**几何**断言：alpha 一个没改，
    # 只是把登记表里的底写错。只对 alpha 逐个对账的话它完全抓不到 —— 两边数值一模一样。
    ("分段标签的底写错（登记成 track，其实压在分段控件上）",
     '                log_text(a_name, seg_key)',
     '                log_text(a_name, "track")'),
    ("树上数值退回 0.45（上一版的真值）",
     '        val_op = A_VAL + 0.20 * breath', '        val_op = 0.45 + 0.20 * breath'),
    # ── 缩放这一类 ────────────────────────────────────────────────────────
    ("轨道最细厚度退回绝对值 2.0（上一版的真值，S<0.556 时不再变细）",
     '    return max(2.0 * col["s"], col["fs_label"] * 0.30)',
     '    return max(2.0, col["fs_label"] * 0.30)'),
    ("间距偷偷加 1px 绝对值（不再跟着 S 走）",
     '        "gap": GAP * s,', '        "gap": GAP * s + 1.0,'),
    ("把非基准比例那道闸门放宽到 50%（等于放行）",
     'assert abs(w / h - base_ar) <= base_ar * 1e-3',
     'assert abs(w / h - base_ar) <= base_ar * 5e-1'),
    ("文字坐标正则永远匹配不到 → 循环体一次都不执行（空转）",
     """XY = re.compile(r'<text x="([\\d.\\-]+)" y="([\\d.\\-]+)"')""",
     """XY = re.compile(r'<textx="([\\d.\\-]+)" y="([\\d.\\-]+)"')"""),

    # ── 排版（v0.28：Apple 语义色 + 留白分组 + 按文字基线对齐）────────────────
    ("行距分母忘掉分组（末行不再落在内容区底）",
     '    den = (rows - blocks) + (blocks - 1) * SECTION_GAP_MULT',
     '    den = (rows - 1)'),
    ("行距不再逐列解，所有列共用最宽那列的行距（末行不再对齐）",
     '    pitches = [row_pitch(m, col_rows(ctrls, [mod]), 1) for mod in modules]',
     '    pitches = [row_pitch(m, max(col_rows(ctrls, [x]) for x in modules), 1) for mod in modules]'),
    ("ALL 模式行距不再按各列行数分摊（末行不再对齐）",
     '    pitches = [row_pitch(m, col_rows(ctrls, lane), len(lane)) for lane in lanes]',
     '    pitches = [row_pitch(m, max(col_rows(ctrls, l) for l in lanes), len(lane)) for lane in lanes]'),
    ("分组空档缩到 1.2 × 行距（眼睛读不出分组）",
     'SECTION_GAP_MULT = 2.5', 'SECTION_GAP_MULT = 1.2'),
    ("字号阶梯被压平（数值和名称一样大）",
     'FS_TITLE, FS_VALUE, FS_NAME = 13.0, 12.0, 11.0',
     'FS_TITLE, FS_VALUE, FS_NAME = 13.0, 12.0, 12.0'),
    ("给分段控件加回描边（小绪明确不要边框）",
     'f\'fill="{SEG_BG}"/>\']', 'f\'fill="{SEG_BG}" stroke="{SEP}" stroke-width="1"/>\']'),
    ("模块分组退回按「行框中心」定位（v0.26 的错法 → 末行错开 39px）",
     '        out.append(param_row(c, x, base - col["fs_label"] * .35, col, m, active, breath,\n'
     '                             state=row_state))',
     '        out.append(param_row(c, x, base - col["fs_label"] * .35 '
     '+ col["pitch"] * 0.30, col, m, active, breath,\n'
     '                             state=row_state))'),

    # ── 交互状态（v0.29）──────────────────────────────────────────────────
    # 这一组的核心规则是"**状态只改颜色，不改几何**"。下面三条分别打它的三个面：
    # 真的改了几何、状态根本没画、状态画了但登记表没换。
    ("hover 时把轨道加粗（状态改了**几何** → 鼠标扫过去会跳一下）",
     '        th = track_h(col)',
     '        th = track_h(col) * (1.25 if state != "idle" else 1.0)'),
    ("状态根本没画出来（hover 与 idle 逐字节相同 → 空转）",
     '    if state in ("hover", "press"):\n        a = HOVER_A if state == "hover" else PRESS_A',
     '    if False:\n        a = HOVER_A if state == "hover" else PRESS_A'),
    ("行底画了、登记表没换（文字仍按面板底算对比度 → 虚数）",
     '        bd = state\n    else:\n        bd = "bg"',
     '        bd = "bg"\n    else:\n        bd = "bg"'),
    ("按下只比悬停重一点点（读不出'按住了'）",
     'PRESS_A = 0.12', 'PRESS_A = 0.07'),
    ("按下比悬停还轻（强度不单调）",
     'PRESS_A = 0.12', 'PRESS_A = 0.04'),
    ("聚焦环在常态也画（强调色跑出聚焦态）",
     '    if state == "focus":\n        th0 = choice_h(col) if c["fmt"] == "Choice" else track_h(col)',
     '    if state != "":\n        th0 = choice_h(col) if c["fmt"] == "Choice" else track_h(col)'),
    ("聚焦环不用强调色（改成主内容色 → 和'选中'分不清）",
     'f\'fill="none" stroke="{ACCENT}" stroke-width="{rw:.1f}"/>\')',
     'f\'fill="none" stroke="{INK}" stroke-width="{rw:.1f}"/>\')'),
    ("拖参数也加了动效（HIG：频繁交互不加动效）",
     'MOTION_DRAG = 0.00', 'MOTION_DRAG = 0.10'),
    ("'减弱动态效果'只把时长缩到 0.05 倍（等于没关掉）",
     'REDUCE_MOTION_SCALE = 0.0', 'REDUCE_MOTION_SCALE = 0.05'),
    ("过渡时长拉到 0.6s（超出 HIG 的 brief 区间，变成表演）",
     'MOTION_STD = 0.20', 'MOTION_STD = 0.60'),
    # ── 动线这一类（v0.30）────────────────────────────────────────────────
    # 信号链顺序是**从 DSP 拿的**，不是界面自己定的。把 CHAIN 倒过来，
    # 等于"改了 DSP 顺序却忘了改界面"—— 探针对账那条必须当场报红。
    ("信号链顺序倒过来（DSP 与界面说的不是一回事）",
     'CHAIN = ["freeze", "grain", "stutter", "comb", "tape",\n'
     '         "ruin", "sweep", "delay", "space", "out"]',
     'CHAIN = ["freeze", "grain", "stutter", "comb", "tape",\n'
     '         "ruin", "sweep", "delay", "space", "out"][::-1]'),
    # 树的纵轴必须**就是**信号轴。把 y 取负，等于"信号在链上回头"。
    ("树的纵轴不再是信号轴（信号在链上回头）",
     'node_y = {n["module"]: n["y"] for n in geo["nodes"]}',
     'node_y = {n["module"]: -n["y"] for n in geo["nodes"]}'),
    # 信号层少画一条 —— 9 条变 8 条，"相对骨架恰好多 1 条"会立刻不成立。
    ("信号层少画最后一条（链断在 space 与 out 之间）",
     'SIGNAL_PATH = [(CHAIN[i], CHAIN[i + 1]) for i in range(len(CHAIN) - 1)]',
     'SIGNAL_PATH = [(CHAIN[i], CHAIN[i + 1]) for i in range(len(CHAIN) - 2)]'),
    # 上面那条被"推导"断言先抓住了，于是下游那几条断言没被验过 ——
    # 按本项目的规矩（没人见它响过的断言等于没写），补两条**绕过推导断言**的：
    # ① 从骨架里抽掉一条**恰好也是信号边**的线 → "相对骨架恰好多 1 条"必须响
    ("从骨架里抽掉一条信号边（yesod → malkuth）",
     'from render_bg_study import PATHS, TRUNK, esc, find_chrome, norm, read_controls, read_geometry',
     'from render_bg_study import PATHS, TRUNK, esc, find_chrome, norm, read_controls, read_geometry\n'
     'PATHS = [p for p in PATHS if p != (8, 9)]'),
    # ② 推导正确但**少画一条** → SVG 里数得出来的线数必须报红
    ("推导正确，但只画前 8 条（SVG 里数得出来）",
     '        for k, (na, nb) in enumerate(SIGNAL_PATH):',
     '        for k, (na, nb) in enumerate(SIGNAL_PATH[:8]):'),
    # 信号层偷懒复用骨架 —— 那 22 条不表流向，等于动线没做。
    ("信号层直接复用骨架的 22 条线（等于没做动线）",
     'SIGNAL_PATH = [(CHAIN[i], CHAIN[i + 1]) for i in range(len(CHAIN) - 1)]',
     'SIGNAL_PATH = [(CHAIN[a], CHAIN[b]) for a, b in PATHS]'),
    # 检查器的阅读顺序必须 = 信号顺序。把第二列的两个模块对调。
    ("ALL 模式第二列的两个模块对调（阅读顺序不再等于信号顺序）",
     'ALL_LANES = [["freeze", "grain", "stutter"],\n'
     '             ["comb", "tape", "ruin"],\n'
     '             ["sweep", "delay", "space", "out"]]',
     'ALL_LANES = [["freeze", "grain", "stutter"],\n'
     '             ["tape", "comb", "ruin"],\n'
     '             ["sweep", "delay", "space", "out"]]'),
    # MODULE 的候选集必须是链上**连续**的一截，不许跳着挑。
    ("MODULE 候选集跳着挑（在链上不连续）",
     'SELECTED = CHAIN[1:5]', 'SELECTED = CHAIN[1:9:2]'),
    # 强调必须是**真的**：骨架比信号还亮的话，"信号层"就是个说法。
    ("骨架调得比信号层还亮（强调是假的）",
     'TRUNK_OP = 0.20', 'TRUNK_OP = 0.40'),
    # 上面那条被"阶梯"断言先抓住了，下面四条分别打**四个比值**，
    # 每条都卡在"刚好过得去"和"不够"之间，专门证明那几条断言各自会响。
    ("中柱只比骨架重 1.23 倍（看不出哪条是主干）",
     'TRUNK_OP = 0.20', 'TRUNK_OP = 0.16'),
    ("信号静止档压不住结构层（两种质地也救不回来）",
     'SIG_REST_LO = 0.32', 'SIG_REST_LO = 0.24'),
    ("信号静止档下游不到骨架的 3 倍（层次拉不开）",
     'SIG_REST_HI = 0.55', 'SIG_REST_HI = 0.36'),
    # ── 两档模型自己的漏洞（v0.30 收尾补）──────────────────────────────
    # ① **高亮不够**：把通过档的下限压到刚好等于静止档的上限。
    #    阶梯断言仍然成立（0.55 < 0.55 才断，这里是相等），所以只有
    #    「最暗通过 > 最亮静止」那一条会响 —— 正是它该响。
    ("通过档下限被压到等于静止档上限（高亮糊在一起）",
     'SIG_HOT_LO = 0.78', 'SIG_HOT_LO = 0.64'),
    # ② **静止档也呼吸**：数值全合法、阶梯也没断，但"呼吸 = 活动"这层含义没了。
    #    这条专打 `if hot:` 那个分支 —— 把它拿掉，两档都乘 pulse。
    ("静止档跟着一起呼吸（'有东西在过'这个信号没了）",
     '            if hot:\n'
     '                pulse = SIG_BREATH_MIN + (1.0 - SIG_BREATH_MIN) * breath\n'
     '                lo, hi = SIG_HOT_LO * pulse, SIG_HOT_HI * pulse\n'
     '            else:\n'
     '                lo, hi = SIG_REST_LO, SIG_REST_HI',
     '            pulse = SIG_BREATH_MIN + (1.0 - SIG_BREATH_MIN) * breath\n'
     '            lo, hi = (SIG_HOT_LO, SIG_HOT_HI) if hot else (SIG_REST_LO, SIG_REST_HI)\n'
     '            lo, hi = lo * pulse, hi * pulse'),
    # ③ **通过档不呼吸**：反过来把 hot 分支的 pulse 拿掉，两档都成了静态。
    ("通过档不呼吸（两档只剩下亮度差，活动感没了）",
     '                lo, hi = SIG_HOT_LO * pulse, SIG_HOT_HI * pulse',
     '                lo, hi = SIG_HOT_LO, SIG_HOT_HI'),
    # ④ **判据被绕开**：`is_hot()` 是唯一判据，自检拿它算期望条数。
    #    把画的那一侧改成"只要有一端亮就算"，两端就与自检的期望值分叉。
    ("高亮判据改成'一端亮就算'（与自检的期望值分叉）",
     '            hot = is_hot(na, nb, lit, selected)',
     '            hot = na in lit or nb in lit or na in selected or nb in selected'),
    # 两种质地必须分得开：信号层混进虚线，就分不出"结构 / 功能"了。
    ("信号层混进虚线（两种质地分不开了）",
     'f\'stroke="url(#{gid})" stroke-width="{SIG_W:.1f}" stroke-linecap="round"/>\')',
     'f\'stroke="url(#{gid})" stroke-width="{SIG_W:.1f}" stroke-linecap="round" '
     'stroke-dasharray="1 3"/>\')'),
    # 骨架混进实线 —— 反方向也要挡。
    ("骨架混进实线（点线/实线的区分没了）",
     'f\'stroke-dasharray="0.01 {5.5 * m["s"]:.1f}"/>\')', 'f\'/>\')'),
    # 渐变反着画：常量全对、两个 stop 的数值也全对，只是**端点对调**。
    # 这条专门打"只查数值不查方向"的漏洞。
    ("渐变的两个端点对调（线是正的，渐变反的 → 流向往上走）",
     'f\'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" \'\n'
     '                f\'x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}">\'',
     'f\'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" \'\n'
     '                f\'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x0:.1f}" y2="{y0:.1f}">\''),
    # 线自己反着画 —— 起点画成下游。
    ("信号线反着画（起点画成下游，流向往上走）",
     'f\'<line class="s" x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" \'',
     'f\'<line class="s" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x0:.1f}" y2="{y0:.1f}" \''),
]

# 对照组：把整段对比度断言拆掉，**应该通过** —— 用来证明上面那些突变是被
# 对比度断言抓住的，不是被别的断言顺手抓的。
CONTROLS: list[tuple[str, str, str]] = [
    ("拆掉对比度断言（对照组，应当通过）",
     "    bd = backdrops()", "    bd = backdrops()\n    return  # 对照组：跳过全部对比度断言"),
]

# 数量下限 —— 见 main() 开头那三条自检。
MIN_MUTATIONS = 45
MIN_CONTROLS = 1


def _line_starts(src: str) -> list[int]:
    """每一行首字符在 src 里的偏移。`starts[line-1]` 就是第 line 行的起点。"""
    starts = [0]
    for line in src.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _prose_spans(src: str) -> list[tuple[int, int]]:
    """注释与**文档字符串**覆盖的字符区间 —— 也就是"不是代码"的地方。

    为什么需要它：`.replace(old, new, 1)` 换的是**第一次出现**。只要文件里
    某句注释或 docstring 里恰好写了 `SECTION_GAP_MULT = 2.5`，突变就会落在
    注释里，**常量根本没动、断言一声不响**，然后被记成"漏网"。
    这不是假想：v0.28 改写文件头时就这么中过一次。

    "文档字符串"按标准定义判：独占一个逻辑行、前面只有缩进的字符串。
    写在表达式里的字符串（比如 f-string 片段）**不算** —— 改它就是在改代码，
    反向对照里确实有这种突变，不能一刀切地放过。
    """
    starts = _line_starts(src)
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    # **注意 `NEWLINE` 不能跳过** —— docstring 的判据正是"它前面是换行、后面是换行"。
    # 把 NEWLINE 一起跳过的话，模块 docstring 的"下一个 token"会变成 `from __future__`，
    # 于是永远判不出 docstring（这条自己错过一次：护栏静默放行了一个只写在
    # 文件头 docstring 里的字面量）。
    skip = {tokenize.NL, tokenize.INDENT, tokenize.DEDENT,
            tokenize.ENCODING, tokenize.COMMENT}
    spans: list[tuple[int, int]] = []
    for i, t in enumerate(toks):
        if t.type == tokenize.COMMENT:
            spans.append((starts[t.start[0] - 1] + t.start[1],
                          starts[t.end[0] - 1] + t.end[1]))
            continue
        if t.type != tokenize.STRING:
            continue
        prev = next((x for x in reversed(toks[:i]) if x.type not in skip), None)
        nxt = next((x for x in toks[i + 1:] if x.type not in skip), None)
        is_docstring = ((prev is None or prev.type in (tokenize.NEWLINE, tokenize.INDENT))
                        and (nxt is None or nxt.type == tokenize.NEWLINE))
        if is_docstring:
            spans.append((starts[t.start[0] - 1] + t.start[1],
                          starts[t.end[0] - 1] + t.end[1]))
    return spans


def locate(src: str, old: str) -> int:
    """找到 old 在**代码里**第一次出现的位置，跳过只落在注释/文档字符串里的出现。

    判据是"**整段**都被注释或文档字符串盖住"，不是"碰到注释就算"。
    一开始写成后者，结果一条带行尾注释的代码行（`th = track_h(col)  # …`）
    被整条误判成注释 —— 护栏自己把合法的突变拦下来了。
    只要**开头落在代码上**，替换下去就一定会改到代码，这就够了。
    """
    spans = _prose_spans(src)
    n = len(old)
    i = src.find(old)
    seen_in_prose = False
    while i >= 0:
        if not any(s <= i and i + n <= e for s, e in spans):
            return i
        seen_in_prose = True
        i = src.find(old, i + 1)
    if seen_in_prose:
        raise AssertionError(
            f"突变原文整段都落在注释/文档字符串里：{old!r}\n"
            f"    （那样改下去等于没改，会假装成'漏网'）")
    raise AssertionError(
        f"突变原文在源码里**根本找不到**（锚点过期了？）：{old!r}\n"
        f"    （改动绘制代码后必须同步更新这里的锚点，否则这条突变是空转的）")


def run_one(orig: str, old: str, new: str) -> tuple[bool, str]:
    """返回 (是否漏网, 失败原因)。

    突变副本写在 **/tmp**，不落进仓库；`render_bg_study` 靠 PYTHONPATH 找得到。
    """
    i = locate(orig, old)
    d = pathlib.Path(tempfile.mkdtemp(prefix="trane_mut_"))
    tmp = d / "mut_case.py"
    tmp.write_text(orig[:i] + new + orig[i + len(old):], encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(TOOLS), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        p = subprocess.run([PY, str(tmp), "--outdir", str(d / "out")],
                           capture_output=True, text=True, timeout=900, cwd=str(TOOLS), env=env)
    except subprocess.TimeoutExpired:
        return False, "超时（900s）—— 没跑出结论，不算抓到"
    if p.returncode == 0:
        return True, ""
    lines = (p.stdout + p.stderr).strip().splitlines()
    err = [l for l in lines if "Error" in l]
    if err:
        return False, err[-1].strip()[:170]
    # 报红但没有 AssertionError → 是别的死法（被信号杀、语法错、导入失败）。
    # 单独标出来，**不许当成"断言抓住了"糊过去** —— 那种假绿比不测还糟。
    return False, f"rc={p.returncode} 非断言失败：{(lines[-1] if lines else '无输出')[:130]}"


def selftest_locate(src: str) -> None:
    """先证明**护栏自己**是活的 —— 没人见它响过的断言等于没写。

    这个护栏是 v0.28 补的：文件头 docstring 里写了一句 `SECTION_GAP_MULT = 2.5`，
    于是 `.replace(..., 1)` 换到了注释上，常量纹丝不动，那条突变被记成"漏网"。
    下面四组用例就是那次事故的形状。
    """
    def must_reject(text: str, why: str) -> None:
        try:
            locate(src, text)
        except AssertionError:
            return
        raise AssertionError(f"护栏该拒却放行了（{why}）：{text!r}")

    def must_accept(text: str, why: str) -> None:
        try:
            locate(src, text)
        except AssertionError as e:
            raise AssertionError(f"护栏该放行却拒了（{why}）：{text!r}\n    {e}") from None

    must_reject("# 文字不透明度：三档，全部实测过线", "纯注释")
    must_reject("不要再翻", "文件头 docstring")
    must_reject("解方程（块与块之间的空档", "函数 docstring")
    must_accept("SECTION_GAP_MULT = 2.5", "真常量")
    must_accept('f\'fill-opacity="{op:.2f}">{module.upper()}</text>\'', "f-string 里的代码")

    # 代码 + **行尾注释**：整段只有后半截在注释里，开头落在代码上 → **必须放行**。
    # 判据一开始写成"碰到注释就算"，结果一条带行尾注释的代码行被整条误判，
    # 护栏自己把合法的突变拦了下来（实测：`th = track_h(col)  # 同上…`）。
    trailing = 'y = 2  # 这里也写着 y = 2\n'
    try:
        locate(trailing, "y = 2")
    except AssertionError:
        raise AssertionError("护栏把「代码 + 行尾注释」误判成注释了（开头在代码上就该放行）") from None
    print("  护栏自检通过 · 注释/文档字符串里的字面量会被拒（不许假装成'漏网'）")


def main() -> int:
    orig = SRC.read_text(encoding="utf-8")

    # **闸门自己也要有闸门。** 下面三条挡的是"最便宜的假绿"：
    # 把难啃的突变删掉、留一份复制粘贴充数、或者把 old/new 写成一样（等于没改）。
    # 没有它们的话，这一关的数量只会单向缩水，而报告永远是"N/N 全抓到"。
    assert len(MUTATIONS) >= MIN_MUTATIONS, \
        f"突变只剩 {len(MUTATIONS)} 条（下限 {MIN_MUTATIONS}）—— 有人删了突变，这一关就变松了"
    assert len(CONTROLS) >= MIN_CONTROLS, f"对照组只剩 {len(CONTROLS)} 条（下限 {MIN_CONTROLS}）"
    seen: dict[tuple[str, str], int] = {}
    for i, (what, old, new) in enumerate(MUTATIONS, 1):
        assert old != new, f"第 {i} 条突变的原文和改后文本一模一样（等于没改）：{what}"
        assert (old, new) not in seen, \
            f"第 {i} 条突变与第 {seen[(old, new)]} 条完全重复：{what}"
        seen[(old, new)] = i

    print(f"反向对照 {len(MUTATIONS)} 处 + 对照 {len(CONTROLS)} 处")
    selftest_locate(orig)
    caught = 0
    for i, (what, old, new) in enumerate(MUTATIONS, 1):
        ok, msg = run_one(orig, old, new)
        caught += not ok
        print(f"  [{i}] {'漏网' if ok else '抓到'} · {what}")
        if msg:
            print(f"        {msg}")
        sys.stdout.flush()
    bad = 0
    for j, (what, old, new) in enumerate(CONTROLS, 1):
        ok, msg = run_one(orig, old, new)
        bad += not ok
        print(f"  [对照{j}] {'按预期通过' if ok else '意外报红'} · {what}")
        if msg:
            print(f"        {msg}")
        sys.stdout.flush()
    print(f"→ {caught}/{len(MUTATIONS)} 处被抓住 · 对照组异常 {bad} 处")

    # **失败必须让整个门槛红。** 上一版这里无条件 `return 0` —— 于是"有突变漏网"
    # 也会被当成通过。接进 run_tests.sh 之后那等于没接：脚本照样绿。
    if caught != len(MUTATIONS) or bad:
        print(f"！！ {len(MUTATIONS) - caught} 处漏网、{bad} 处对照异常 —— 这一关不通过",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
