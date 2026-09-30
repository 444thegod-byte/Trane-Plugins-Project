#!/usr/bin/env python3
"""⚠️ 历史稿（v0.22 那版），**已过期，别拿它当面板现在的样子**。
当前实现在 `plugin/TranePanel.cpp`，要看实况用 `panel_probe --out`。
留着它只为记录当时的设计 —— 可拖分割窗 / 三种视图 / 世界树 v0.33 已删。

Träne UI v0.22 —— 横屏主界面 / 可调整的右侧检查器。

这版只解决三个用户可见问题：
  1) 移除全局顶栏：画面从世界树和参数开始；
  2) 右侧是可拖动分割窗，三种视图共用同一个位置：
       ALL    = 48 个参数同时可见的三栏总览；
       MODULE = 选中模块的完整参数（默认）；
       FOCUS  = 单个参数的大读数编辑器；
  3) 所有插件 UI 文字都强制大写。

字体
====
pandaijing.com 当前 CSS 的主字体别名 Gla，经 WOFF name table 核验为
"Neue Haas Grotesk Text W01"（Linotype GmbH / Christian Schwartz）。
它是商业字体，不能从网站 CSS 抽取并打包进插件；所以这份设计稿只声明该字体
的**系统已授权版本**，找不到时回退 Helvetica Neue。真正实施时必须由小绪
提供已授权的桌面插件字体许可或确认回退方案。

数据来源
========
圆心/树比例：panel_probe --dump-geometry；参数表：TranePanel.h::kControls。
这份稿子不重复手抄任何 48 参数或世界树坐标。
"""
from __future__ import annotations

import argparse
import math
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_bg_study import PATHS, TRUNK, esc, find_chrome, norm, read_controls, read_geometry

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 冷静、低饱和、低刺激的 "instrument panel" 令牌。
# 强调色不是霓虹，是青灰蓝；警示色只在真的过载时才出现，当前稿不滥用。
PAPER = "#F5F6F6"
SURFACE = "#FBFCFC"
INK = "#161A1C"
TEXT = "#30383D"
# 正常说明文本与辅助强调文本都保持 ≥4.5:1（对 #F5F6F6 实测 4.69 / 4.57）。
MUTED = "#657077"
HAIR = "#DDE2E4"
TRACK = "#E6EAEB"
ACCENT = "#526F7A"
ACCENT_SOFT = "#E6ECEE"
ACCENT_DIM = "#60737C"
# 关闭态不靠低到读不出的灰，而靠关闭开关 + 无填充 + 减轻描边三重表达。
OFF = "#738087"
WARNING = "#B26A53"

# Pandaijing 网站实际主字体；不嵌入，仅在宿主已拥有授权字体时使用。
UI = "'Neue Haas Grotesk Text W01','Neue Haas Grotesk Text Pro','Helvetica Neue',Helvetica,Arial,sans-serif"
DATA = "'Neue Haas Grotesk Text W01','Helvetica Neue',Helvetica,Arial,sans-serif"

LIT = {"freeze", "grain", "ruin", "space", "out"}
SELECTED_MODULE = "grain"
SELECTED_PARAM = "grain_position"

PANEL_W, PANEL_H = 1200.0, 680.0
DIVIDER_X = 412.0


def uppercase(s: str) -> str:
    return s.upper()


def real(c: dict, nv: float) -> float:
    """复刻 TranePanel.cpp::fromNormalised：显示永远用真实值，不用 0..1。"""
    q = nv if c["skew"] == 1.0 else math.pow(max(0.0, nv), 1.0 / c["skew"])
    return c["lo"] + (c["hi"] - c["lo"]) * q


def value_text(c: dict, nv: float | None = None) -> str:
    v = c["def"] if nv is None else real(c, nv)
    f = c["fmt"]
    if f == "Ms": return f"{v:.0f}MS" if v >= 10 else f"{v:.1f}MS"
    if f == "Plain0": return f"{v:.0f}"
    if f == "Plain2": return f"{v:.2f}"
    if f == "Rate1": return f"{v:.1f}"
    if f == "KHz1": return f"{v / 1000.0:.1f}K"
    if f == "Db1": return f"{v:+.1f}DB"
    if f == "Choice": return ["LP", "BP", "HP"][min(2, max(0, round(v * 2)))]
    return f"{v:g}".upper()


def label(c: dict) -> str:
    return uppercase(c["label"] or c["name"])


def module_controls(ctrls: list[dict], module: str) -> list[dict]:
    return [c for c in ctrls if c["module"] == module and c["label"]]


def module_on(module: str) -> bool:
    return module in LIT


def tree_layout(geo: dict, x: float, y: float, w: float, h: float) -> dict:
    # 与 TranePanel.h 里建立过的比例一致：r/col=0.341，r/tree=0.074。
    r = min(w / 7.865, h / 15.514)
    col, tree_h = r / 0.341, r / 0.074
    cx, cy = x + w * .5, y + h * .5
    xs = [n["x"] for n in geo["nodes"]]
    ys = [n["y"] for n in geo["nodes"]]
    xmin, ymin = min(xs), min(ys)
    xr, yr = max(xs) - xmin, max(ys) - ymin
    pts = []
    for n in geo["nodes"]:
        u = 0 if xr == 0 else (n["x"] - xmin) / xr * 2 - 1
        v = 0 if yr == 0 else (n["y"] - ymin) / yr
        pts.append({"module": n["module"], "x": cx + u * col, "y": cy + (v - .5) * tree_h})
    return {"r": r, "pts": pts}


def tree_svg(geo: dict, ctrls: list[dict]) -> str:
    t = tree_layout(geo, 44, 66, 322, 566)
    r, pts = t["r"], t["pts"]
    out: list[str] = []
    on = {p["module"]: module_on(p["module"]) for p in pts}

    for a, b in PATHS:
        pa, pb = pts[a], pts[b]
        dx, dy = pb["x"] - pa["x"], pb["y"] - pa["y"]
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln
        trim = r + 2
        x0, y0 = pa["x"] + ux * trim, pa["y"] + uy * trim
        x1, y1 = pb["x"] - ux * trim, pb["y"] - uy * trim
        hot = on[pa["module"]] and on[pb["module"]]
        trunk = (a, b) in TRUNK
        color = ACCENT if hot else ("#AAB4B8" if trunk else "#D3D9DB")
        width = 1.5 if hot else (1.2 if trunk else 1.0)
        out.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                   f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
                   f'stroke-dasharray="0.01 5.5"/>')

    for p in pts:
        active = on[p["module"]]
        selected = p["module"] == SELECTED_MODULE
        ring = module_controls(ctrls, p["module"])
        primary = value_text(ring[0]) if ring else ""
        if selected:
            out.append(f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{r + 7:.1f}" '
                       f'fill="none" stroke="{ACCENT}" stroke-width="1" stroke-dasharray="2 4"/>')
        out.append(f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{r:.1f}" '
                   f'fill="{ACCENT_SOFT if active else SURFACE}" '
                   f'stroke="{ACCENT if active else HAIR}" stroke-width="{1.4 if active else 1}"/>')
        out.append(f'<text x="{p["x"]:.1f}" y="{p["y"] - 2:.1f}" text-anchor="middle" '
                   f'font-family="{UI}" font-size="10.5" font-weight="600" letter-spacing=".06em" '
                   f'fill="{ACCENT if active else MUTED}">{p["module"].upper()}</text>')
        if primary:
            out.append(f'<text x="{p["x"]:.1f}" y="{p["y"] + 12:.1f}" text-anchor="middle" '
                       f'font-family="{DATA}" font-size="9.5" font-weight="500" letter-spacing=".01em" '
                       f'fill="{ACCENT_DIM if active else OFF}">{primary}</text>')

    # 左侧只留下极轻的两个标签，不做全局顶栏。
    out.append(f'<text x="44" y="34" font-family="{UI}" font-size="11" font-weight="600" '
               f'letter-spacing=".15em" fill="{MUTED}">SIGNAL MAP</text>')
    out.append(f'<text x="44" y="654" font-family="{DATA}" font-size="10" letter-spacing=".02em" '
               f'fill="{MUTED}">10 MODULES · 48 PARAMETERS</text>')
    return "".join(out)


def splitter() -> str:
    x = DIVIDER_X
    return (f'<line x1="{x}" y1="28" x2="{x}" y2="652" stroke="{HAIR}" stroke-width="1"/>'
            f'<rect x="{x - 10}" y="316" width="20" height="48" rx="10" fill="{SURFACE}" stroke="{HAIR}"/>'
            f'<circle cx="{x}" cy="332" r="1.2" fill="{MUTED}"/>'
            f'<circle cx="{x}" cy="340" r="1.2" fill="{MUTED}"/>'
            f'<circle cx="{x}" cy="348" r="1.2" fill="{MUTED}"/>')


def mode_tabs(active: str) -> str:
    modes = [("ALL", "ALL"), ("MODULE", "MODULE"), ("FOCUS", "FOCUS")]
    x, y, w, h = 462, 30, 74, 26
    out = []
    for i, (key, text) in enumerate(modes):
        xx = x + i * (w + 8)
        selected = key == active
        out.append(f'<rect x="{xx}" y="{y}" width="{w}" height="{h}" rx="13" '
                   f'fill="{ACCENT if selected else "none"}" '
                   f'stroke="{ACCENT if selected else HAIR}" stroke-width="1"/>')
        out.append(f'<text x="{xx + w / 2}" y="{y + 17}" text-anchor="middle" font-family="{UI}" '
                   f'font-size="10" font-weight="600" letter-spacing=".08em" '
                   f'fill="{SURFACE if selected else MUTED}">{text}</text>')
    return "".join(out)


def slider(c: dict, x: float, y: float, w: float, value_w: float,
           compact: bool = False, active: bool = True) -> str:
    """轨道填充 + 出厂值刻度 + 实际值。不让颜色单独承担状态。"""
    nv = norm(c)
    # ALL 总览里三栏要容纳 48 条控件；22px 只用于只读定位，不承担精调。
    # 精调回 MODULE / FOCUS，仍保留 44px 的鼠标命中高度。
    h = 22 if compact else 44
    mid = y + h / 2
    label_w = 72 if compact else 112
    track_w = w - label_w - value_w
    fs_l = 10.0 if compact else 12.0
    fs_v = 10.0 if compact else 13.0
    fill = ACCENT if active else OFF
    col = TEXT if active else MUTED
    out: list[str] = []
    out.append(f'<text x="{x}" y="{mid + fs_l * .34:.1f}" font-family="{UI}" font-size="{fs_l}" '
               f'font-weight="500" letter-spacing=".035em" fill="{col}">{label(c)}</text>')
    tx = x + label_w

    if c["fmt"] == "Choice":
        pieces = ["LP", "BP", "HP"]
        cw = track_w / 3
        pos = min(2, max(0, round(c["def"] * 2)))
        out.append(f'<rect x="{tx:.1f}" y="{mid - 8:.1f}" width="{track_w:.1f}" height="16" rx="4" fill="{TRACK}"/>')
        out.append(f'<rect x="{tx + pos * cw + 1:.1f}" y="{mid - 7:.1f}" width="{cw - 2:.1f}" height="14" rx="3" fill="{fill}"/>')
        for i, v in enumerate(pieces):
            tc = SURFACE if i == pos and active else MUTED
            out.append(f'<text x="{tx + cw * (i + .5):.1f}" y="{mid + 3.6:.1f}" text-anchor="middle" '
                       f'font-family="{UI}" font-size="8.5" font-weight="600" letter-spacing=".05em" fill="{tc}">{v}</text>')
    else:
        out.append(f'<rect x="{tx:.1f}" y="{mid - 2:.1f}" width="{track_w:.1f}" height="4" rx="2" fill="{TRACK}"/>')
        default_x = tx + track_w * norm(c)
        out.append(f'<line x1="{default_x:.1f}" y1="{mid - 6:.1f}" x2="{default_x:.1f}" y2="{mid + 6:.1f}" '
                   f'stroke="{ACCENT_DIM}" stroke-width="1"/>')
        out.append(f'<rect x="{tx:.1f}" y="{mid - 2:.1f}" width="{max(4, track_w * nv):.1f}" height="4" rx="2" fill="{fill}"/>')
        hx = tx + track_w * nv
        r = 4 if compact else 5.5
        out.append(f'<circle cx="{hx:.1f}" cy="{mid:.1f}" r="{r}" fill="{SURFACE}" stroke="{fill}" stroke-width="1.4"/>')
    out.append(f'<text x="{x + w:.1f}" y="{mid + fs_v * .34:.1f}" text-anchor="end" '
               f'font-family="{DATA}" font-size="{fs_v}" font-weight="500" letter-spacing=".01em" '
               f'fill="{col}">{value_text(c)}</text>')
    return "".join(out)


def header(title: str, subtitle: str) -> str:
    return (f'<text x="462" y="94" font-family="{UI}" font-size="18" font-weight="600" '
            f'letter-spacing=".10em" fill="{INK}">{title}</text>'
            f'<text x="462" y="116" font-family="{UI}" font-size="10.5" font-weight="500" '
            f'letter-spacing=".065em" fill="{MUTED}">{subtitle}</text>')


def module_view(ctrls: list[dict]) -> str:
    out = [mode_tabs("MODULE"), header("GRAIN", "MODULE · 8 PARAMETERS · ON")]
    out.append(f'<rect x="1102" y="86" width="50" height="26" rx="13" fill="{ACCENT}"/>')
    out.append(f'<circle cx="1139" cy="99" r="9" fill="{SURFACE}"/>')
    rows = module_controls(ctrls, SELECTED_MODULE)
    for i, c in enumerate(rows):
        y = 142 + i * 58
        out.append(slider(c, 462, y, 690, 86))
        if c["id"] == SELECTED_PARAM:
            # 选择态只做面，不需要第二种颜色。
            out.append(f'<rect x="450" y="{y + 3}" width="714" height="38" rx="8" fill="none" stroke="{ACCENT}" stroke-width="1"/>')
    return "".join(out)


def focus_view(ctrls: list[dict]) -> str:
    c = next(c for c in ctrls if c["id"] == SELECTED_PARAM)
    nv = .68
    out = [mode_tabs("FOCUS"), header("GRAIN POSITION", "FOCUS · CONTINUOUS · 0.00 — 1.00")]
    out.append(f'<text x="462" y="220" font-family="{DATA}" font-size="72" font-weight="400" '
               f'letter-spacing="-.03em" fill="{INK}">{value_text(c, nv)}</text>')
    out.append(f'<text x="462" y="250" font-family="{UI}" font-size="10.5" font-weight="600" '
               f'letter-spacing=".09em" fill="{MUTED}">CURRENT VALUE</text>')
    # 大轨道：视觉值域 560px；不是炫技，是让 0.35 的差等于 196px。
    x, y, w = 462, 318, 640
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="8" rx="4" fill="{TRACK}"/>')
    dx = x + w * norm(c)
    out.append(f'<line x1="{dx:.1f}" y1="{y - 14}" x2="{dx:.1f}" y2="{y + 22}" stroke="{ACCENT_DIM}" stroke-width="1.2"/>')
    out.append(f'<rect x="{x}" y="{y}" width="{w * nv:.1f}" height="8" rx="4" fill="{ACCENT}"/>')
    hx = x + w * nv
    out.append(f'<circle cx="{hx:.1f}" cy="{y + 4}" r="10" fill="{SURFACE}" stroke="{ACCENT}" stroke-width="2"/>')
    out.append(f'<text x="{x}" y="{y + 52}" font-family="{DATA}" font-size="11" fill="{MUTED}">0.00</text>')
    out.append(f'<text x="{x + w}" y="{y + 52}" text-anchor="end" font-family="{DATA}" font-size="11" fill="{MUTED}">1.00</text>')
    out.append(f'<text x="{dx:.1f}" y="{y - 28}" text-anchor="middle" font-family="{DATA}" font-size="10.5" fill="{MUTED}">DEFAULT {value_text(c)}</text>')

    cells = [("DEFAULT", value_text(c)), ("RANGE", "0.00 — 1.00"), ("STEP", "0.01"), ("RESET", "DOUBLE CLICK")]
    for i, (k, v) in enumerate(cells):
        xx = 462 + i * 174
        out.append(f'<line x1="{xx}" y1="430" x2="{xx + 142}" y2="430" stroke="{HAIR}"/>')
        out.append(f'<text x="{xx}" y="456" font-family="{UI}" font-size="10" font-weight="600" letter-spacing=".09em" fill="{MUTED}">{k}</text>')
        out.append(f'<text x="{xx}" y="482" font-family="{DATA}" font-size="14" font-weight="500" letter-spacing=".01em" fill="{TEXT}">{v}</text>')
    return "".join(out)


def all_view(ctrls: list[dict]) -> str:
    """三栏 48 参数总览。它用于定位和比值比较，不抢 MODULE / FOCUS 的精调工作。"""
    out = [mode_tabs("ALL"), header("ALL PARAMETERS", "48 PARAMETERS · 3 LANES · CLICK ANY ROW TO FOCUS")]
    columns = [
        ["freeze", "grain", "stutter"],
        ["comb", "tape", "ruin"],
        ["sweep", "delay", "space", "out"],
    ]
    col_w = 220
    for ci, modules in enumerate(columns):
        x = 462 + ci * 232
        y = 142
        for module in modules:
            active = module_on(module)
            state = "ON" if active else "OFF"
            out.append(f'<text x="{x}" y="{y}" font-family="{UI}" font-size="10" font-weight="600" '
                       f'letter-spacing=".10em" fill="{ACCENT if active else MUTED}">{module.upper()}</text>')
            out.append(f'<text x="{x + col_w}" y="{y}" text-anchor="end" font-family="{DATA}" '
                       f'font-size="9" letter-spacing=".08em" fill="{ACCENT_DIM if active else OFF}">{state}</text>')
            y += 8
            # 七个 *_ON 也是参数，ALL 视图必须明确把它们列出来；
            # 组标题右侧的 ON/OFF 只是概览，不能偷偷替代真实可见的开关行。
            has_switch = any(c["module"] == module and not c["label"] for c in ctrls)
            if has_switch:
                pill_x = x + 72
                pill_w, pill_h = 46, 14
                out.append(f'<text x="{x}" y="{y + 8:.1f}" font-family="{UI}" font-size="9.5" '
                           f'font-weight="500" letter-spacing=".04em" fill="{TEXT if active else MUTED}">ENABLE</text>')
                out.append(f'<rect x="{pill_x}" y="{y - 3:.1f}" width="{pill_w}" height="{pill_h}" rx="7" '
                           f'fill="{ACCENT if active else TRACK}"/>')
                out.append(f'<circle cx="{pill_x + (pill_w - 8 if active else 8):.1f}" cy="{y + 4:.1f}" '
                           f'r="4.5" fill="{SURFACE}"/>')
                out.append(f'<text x="{x + col_w}" y="{y + 8:.1f}" text-anchor="end" font-family="{DATA}" '
                           f'font-size="9.5" font-weight="500" fill="{TEXT if active else MUTED}">{state}</text>')
                y += 22
            for c in module_controls(ctrls, module):
                out.append(slider(c, x, y, col_w, 42, compact=True, active=active))
                y += 22
            y += 12
    return "".join(out)


def panel(geo: dict, ctrls: list[dict], mode: str) -> str:
    content = {"MODULE": module_view, "ALL": all_view, "FOCUS": focus_view}[mode](ctrls)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{PANEL_W}" height="{PANEL_H}" '
            f'viewBox="0 0 {PANEL_W} {PANEL_H}">'
            f'<rect width="{PANEL_W}" height="{PANEL_H}" fill="{PAPER}"/>'
            f'{tree_svg(geo, ctrls)}{splitter()}{content}</svg>')


def make_html(geo: dict, ctrls: list[dict], version: str) -> tuple[str, int, int]:
    modes = [("MODULE", "01 · MODULE VIEW · DEFAULT"), ("ALL", "02 · ALL VIEW · 48 PARAMETERS SIMULTANEOUSLY"),
             ("FOCUS", "03 · FOCUS VIEW · ONE PARAMETER")]
    cards = "".join(
        f'<section><h2>{title}</h2><div class="panel">{panel(geo, ctrls, mode)}</div></section>'
        for mode, title in modes)
    w, pad, gap = int(PANEL_W * 2 + 96), 48, 44
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>TRÄNE UI V{version}</title>
<style>
:root{{--paper:{PAPER};--ink:{INK};--muted:{MUTED};--hair:{HAIR};}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{width:{w}px;background:#ECEFF0;color:var(--ink);padding:52px {pad}px 80px;font-family:{UI};}}
h1{{font-size:18px;font-weight:600;letter-spacing:.10em;text-transform:uppercase;}}
p{{margin-top:10px;max-width:980px;font-size:11px;line-height:1.75;letter-spacing:.045em;text-transform:uppercase;color:var(--muted);}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:{gap}px;margin-top:42px;align-items:start;}}
section:last-child{{grid-column:span 2;justify-self:center;}}
h2{{height:34px;font-size:11px;font-weight:600;letter-spacing:.10em;color:#526F7A;text-transform:uppercase;}}
.panel{{width:{PANEL_W}px;height:{PANEL_H}px;box-shadow:0 18px 48px rgba(15,22,26,.10),0 0 0 1px rgba(15,22,26,.08);}}
.panel svg{{display:block;}}
.note{{font-size:10px;line-height:1.65;}}
</style></head><body>
<h1>TRÄNE · V{version} · HORIZONTAL INSTRUMENT PANEL</h1>
<p>NO GLOBAL TOP BAR · PANDAIJING TYPE SYSTEM: NEUE HAAS GROTESK TEXT W01 WHEN LICENSED · COLD GREY-BLUE INSTRUMENT PALETTE · ALL UI LABELS IN UPPERCASE</p>
<div class="grid">{cards}</div>
</body></html>''', w, 3 * int(PANEL_H) + 320


def render(html: str, w: int, h: int, out: pathlib.Path, scale: int) -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_ui22_"))
    page = tmp / "panel.html"
    page.write_text(html, encoding="utf-8")
    subprocess.run([find_chrome(), "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                    f"--force-device-scale-factor={scale}", f"--screenshot={out}",
                    f"--window-size={w},{h}", "--virtual-time-budget=8000", page.as_uri()],
                   capture_output=True, text=True, timeout=180)
    assert out.is_file(), "Chrome did not produce the preview"


def make_single_panel_html(geo: dict, ctrls: list[dict], mode: str, version: str) -> str:
    """单张真实尺寸预览：让用户不用在 contact sheet 里缩放看 1200×680。"""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>TRÄNE UI V{version} · {mode}</title>
<style>
html,body{{margin:0;width:{int(PANEL_W)}px;height:{int(PANEL_H)}px;background:{PAPER};overflow:hidden}}
body{{font-family:{UI}}}
svg{{display:block}}
</style></head><body>{panel(geo, ctrls, mode)}</body></html>'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="0.22")
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--outdir", default=str(ROOT.parent / "outputs"))
    args = ap.parse_args()
    geo, ctrls = read_geometry(), read_controls()
    assert len(ctrls) == 48, "kControls is not 48 entries"
    assert sum(len(module_controls(ctrls, m)) for m in {c["module"] for c in ctrls}) == 41, "ring controls changed"
    html, w, h = make_html(geo, ctrls, args.version)
    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / f"Trane_UI_v{args.version}.png"
    render(html, w, h, png, args.scale)
    print(f"→ {png} · {len(ctrls)} parameters · {w * args.scale}×{h * args.scale}")

    # 三张实际尺寸稿：MODULE 是默认工作态；ALL / FOCUS 证明右窗不是概念图。
    for mode in ("MODULE", "ALL", "FOCUS"):
        dest = outdir / f"Trane_UI_v{args.version}_{mode.lower()}.png"
        render(make_single_panel_html(geo, ctrls, mode, args.version),
               int(PANEL_W), int(PANEL_H), dest, args.scale)
        print(f"→ {dest} · {int(PANEL_W * args.scale)}×{int(PANEL_H * args.scale)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
