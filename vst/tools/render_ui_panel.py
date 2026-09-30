#!/usr/bin/env python3
"""⚠️ 历史稿（v0.17–v0.19 那版"世界树 = 地图"），**已过期，别拿它当面板现在的样子**。
当前实现在 `plugin/TranePanel.cpp`，要看实况用 `panel_probe --out`。
留着它只为记录当时的设计 —— 它画的那套（环形面板 / 世界树 / 辐条）v0.33 已删。

Träne UI 设计稿生成器 —— 「世界树 = 地图，参数 = 检查器」。

这个文件替代了 v0.17 的环形面板稿。设计依据（都是量出来的，不是感觉）
====================================================================

**① 字号被宽度锁死 —— 7px 不是"选小了"，是这个布局下不可能更大**

    面板 544 宽 → 圆半径 58 → 值圈 r = 38.5 → 周长 242px
    GRAIN 八个参数 → 每段弧长 26.2px
    10px 的 "SPRAY" 要 ≈30px   →   塞不进去

竖屏里"宽"是稀缺轴，而环形排布吃的正是宽度（半径 → 周长 → 弧长）。
所以参数**搬离圆周**：圆只放模块名 + 主参数读数 + 开关状态，
半径于是只服从"名字放得下"这一条约束。

**② 值编码的动态范围差一个量级**

    v0.18 辐条长度：r 从 63 → 78，全幅 15px。判 "0.35 还是 0.70" 要在
    一根 20px 的辐条上读 5px 的差；而且 41 根辐条朝 41 个方向 ——
    跨角度比长度是人眼最不擅长的。
    v0.21 轨道填充：轨道 320px。**15px → 320px，21 倍。**

**③ 交互**：轨道上常显一条极淡的**出厂值刻度**，于是"我现在离出厂多远"是看得见的；
拖拽时整行高亮、把手放大、气泡跟着手走。

几何与参数从哪来
================
  · 圆心 / 半径 → `panel_probe --dump-geometry`（编译产物）
  · 参数表 → 解析 `plugin/TranePanel.h` 的 kControls（含 lo/hi/skew/def/label/fmt）
  · 树的柱距 / 树高 → 由真实圆心反推，再按原图两条比值等比装箱
    （r/柱距 = 0.341、r/树高 = 0.074 —— 这两条比值保证任意缩放下圆都不会互相压到）
  全部复用 `render_bg_study.py`，不另抄一份常量。

用法
====
    python tools/render_ui_panel.py [--outdir ../outputs] [--version 0.21]
                                    [--scale 2] [--portrait]
"""
from __future__ import annotations

import argparse
import math
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_bg_study import (PATHS, TRUNK, esc, find_chrome,  # noqa: E402
                             norm, read_controls, read_geometry)

ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 设计令牌（参考图的语言：暖白底 + 点阵 + 1px 发丝线 + 蓝/琥珀两个数据色）
# ---------------------------------------------------------------------------
PAPER = "#F4F3EF"
INK = "#1A1A1C"
INK2 = "rgba(26,26,28,.58)"
INK3 = "rgba(26,26,28,.34)"
HAIR = "rgba(26,26,28,.10)"
TRACK = "rgba(26,26,28,.08)"
DOTS = "rgba(26,26,28,.055)"
ACCENT = "#4A4ED6"
ACCENT_SOFT = "rgba(74,78,214,.09)"
OFF_FILL = "rgba(26,26,28,.30)"
WARN = "#D97706"

UI = "'Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'SF Mono',SFMono-Regular,Menlo,monospace"

LIT = {"freeze", "grain", "ruin", "space", "out"}      # 与 check_panel_render 的 demo 一致


# ---------------------------------------------------------------------------
# 值格式化
# ---------------------------------------------------------------------------
def fmt(c: dict, v: float) -> str:
    f = c["fmt"]
    if f == "None":
        return ""
    if f == "Ms":
        return f"{v:.0f}ms" if v >= 10 else f"{v:.1f}ms"
    if f == "Plain0":
        return f"{v:.0f}"
    if f == "Plain2":
        return f"{v:.2f}"
    if f == "Rate1":
        return f"{v:.1f}"
    if f == "KHz1":
        return f"{v / 1000.0:.1f}k"
    if f == "Db1":
        return f"{v:+.1f}dB"
    if f == "Choice":
        return ["LP", "BP", "HP"][min(2, max(0, round(v * 2)))]
    return f"{v:g}"


def real(c: dict, nv: float) -> float:
    """归一化 → 真实值。复刻 TranePanel.cpp:671 fromNormalised（pow(p, 1/skew)）。"""
    q = nv if c["skew"] == 1.0 else math.pow(max(0.0, nv), 1.0 / c["skew"])
    return c["lo"] + (c["hi"] - c["lo"]) * q


def ring_controls(ctrls: list[dict], module: str) -> list[dict]:
    return [c for c in ctrls if c["module"] == module and c["label"]]


def switch_of(ctrls: list[dict], module: str):
    return next((c for c in ctrls if c["module"] == module and not c["label"]), None)


# ---------------------------------------------------------------------------
# 世界树
# ---------------------------------------------------------------------------
def tree_layout(geo: dict, bx: float, by: float, bw: float, bh: float) -> dict:
    r = min(bw / 7.865, bh / 15.514)          # 2/0.341+2 · 1/0.074+2
    col, tree_h = r / 0.341, r / 0.074
    cx, cy = bx + bw * 0.5, by + bh * 0.5
    xs = [n["x"] for n in geo["nodes"]]
    ys = [n["y"] for n in geo["nodes"]]
    x0, y0 = min(xs), min(ys)
    span_x, span_y = max(xs) - x0, max(ys) - y0
    pts = []
    for n in geo["nodes"]:
        u = (n["x"] - x0) / span_x * 2.0 - 1.0 if span_x else 0.0
        v = (n["y"] - y0) / span_y if span_y else 0.0
        pts.append({"module": n["module"], "x": cx + u * col, "y": cy + (v - 0.5) * tree_h})
    return {"r": r, "pts": pts}


def tree_svg(geo: dict, ctrls: list[dict], tl: dict,
             fs_name: float, fs_val: float) -> str:
    r, pts = tl["r"], tl["pts"]
    on_of = {p["module"]: p["module"] in LIT for p in pts}
    out: list[str] = []

    # 22 条路径画成点线。两端都亮着的染强调色 —— 于是
    # 「信号从 Keter 流到 Malkuth」是看得见的，不是文案。
    for a, b in PATHS:
        pa, pb = pts[a], pts[b]
        dx, dy = pb["x"] - pa["x"], pb["y"] - pa["y"]
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln
        trim = r + 2.0
        x0, y0 = pa["x"] + ux * trim, pa["y"] + uy * trim
        x1, y1 = pb["x"] - ux * trim, pb["y"] - uy * trim
        hot = on_of[pa["module"]] and on_of[pb["module"]]
        trunk = (a, b) in TRUNK
        col, w = ((ACCENT, 2.6) if hot else
                  ("rgba(26,26,28,.34)", 2.4) if trunk else
                  ("rgba(26,26,28,.21)", 2.0))
        out.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                   f'stroke="{col}" stroke-width="{w}" stroke-linecap="round" '
                   f'stroke-dasharray="0.01 6.2"/>')

    # 十个圆：模块名 + 主参数读数 + 开关状态。**不承担任何参数编辑。**
    for p in pts:
        on = on_of[p["module"]]
        ring = ring_controls(ctrls, p["module"])
        prim = fmt(ring[0], ring[0]["def"]) if ring else ""
        block = fs_name + 0.45 * fs_name + (fs_val if prim else 0.0)
        top = p["y"] - block * 0.5
        base_name = top + fs_name * 0.78
        base_val = base_name + 0.45 * fs_name + fs_val * 0.80

        if on:
            out.append(f'<circle cx="{p["x"]:.2f}" cy="{p["y"]:.2f}" r="{r:.2f}" '
                       f'fill="{ACCENT_SOFT}" stroke="{ACCENT}" stroke-width="1.6"/>')
        else:
            out.append(f'<circle cx="{p["x"]:.2f}" cy="{p["y"]:.2f}" r="{r:.2f}" '
                       f'fill="#FFFFFF" stroke="{HAIR}" stroke-width="1.2"/>')
        out.append(f'<text x="{p["x"]:.2f}" y="{base_name:.2f}" text-anchor="middle" '
                   f'font-family="{UI}" font-size="{fs_name}" font-weight="700" '
                   f'letter-spacing="0.055em" '
                   f'fill="{ACCENT if on else INK2}">{p["module"].upper()}</text>')
        if prim:
            out.append(f'<text x="{p["x"]:.2f}" y="{base_val:.2f}" text-anchor="middle" '
                       f'font-family="{MONO}" font-size="{fs_val}" font-weight="500" '
                       f'fill="{ACCENT if on else INK3}">{esc(prim)}</text>')
    return "".join(out)


def selected_ring(x: float, y: float, r: float) -> str:
    return (f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="none" '
            f'stroke="{ACCENT}" stroke-width="1.2" stroke-dasharray="2.5 4"/>')


# ---------------------------------------------------------------------------
# 控件
# ---------------------------------------------------------------------------
def toggle(x: float, y: float, w: float, h: float, on: bool) -> str:
    k = h * 0.5 - 2.0
    cx = x + (w - h * 0.5 - 2) if on else x + h * 0.5 + 2
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" '
            f'fill="{ACCENT if on else "rgba(26,26,28,.13)"}"/>'
            f'<circle cx="{cx:.2f}" cy="{y + h / 2:.2f}" r="{k:.2f}" fill="#FFFFFF"/>')


def segmented(x: float, y: float, w: float, h: float, items: list[str],
              active: int, on: bool) -> str:
    """枚举参数不用滑杆 —— 三个档位画成三段，按哪段就是哪段。"""
    n = len(items)
    cw = w / n
    fill = ACCENT if on else OFF_FILL
    o: list[str] = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'rx="6" fill="{TRACK}"/>',
                    f'<rect x="{x + cw * active + 1:.1f}" y="{y + 1:.1f}" '
                    f'width="{cw - 2:.1f}" height="{h - 2:.1f}" rx="5" fill="{fill}"/>']
    for i, it in enumerate(items):
        col = "#FFFFFF" if (i == active and on) else (INK2 if i == active else INK3)
        o.append(f'<text x="{x + cw * (i + 0.5):.1f}" y="{y + h / 2 + 4:.1f}" '
                 f'text-anchor="middle" font-family="{UI}" font-size="11" '
                 f'font-weight="600" letter-spacing="0.06em" fill="{col}">{it}</text>')
    return "".join(o)


def slider_row(c: dict, x: float, y: float, label_w: float, track_w: float,
               value_w: float, fs_label: float, fs_value: float, on: bool,
               state: str = "idle", value: float | None = None) -> str:
    """一行参数。state ∈ idle | hover | drag | disabled。"""
    h = 44.0
    mid = y + h * 0.5
    v = norm(c) if value is None else value
    dim = (not on) or state == "disabled"
    fill = OFF_FILL if dim else ACCENT
    o: list[str] = []
    inner = label_w + track_w + value_w

    if state == "drag":
        o.append(f'<rect x="{x - 12:.1f}" y="{y + 2:.1f}" width="{inner + 24:.1f}" '
                 f'height="{h - 4:.1f}" rx="8" fill="{ACCENT_SOFT}"/>')
    elif state == "hover":
        o.append(f'<rect x="{x - 12:.1f}" y="{y + 2:.1f}" width="{inner + 24:.1f}" '
                 f'height="{h - 4:.1f}" rx="8" fill="rgba(26,26,28,.035)"/>')

    tx = x + label_w
    o.append(f'<text x="{x}" y="{mid + fs_label * 0.35:.2f}" font-family="{UI}" '
             f'font-size="{fs_label}" font-weight="500" letter-spacing="0.01em" '
             f'fill="{INK if state == "drag" else INK2}">{esc(c["label"])}</text>')

    if c["fmt"] == "Choice":
        o.append(segmented(tx, mid - 12.0, track_w, 24.0, ["LP", "BP", "HP"],
                           min(2, max(0, round(c["def"] * 2))), on))
    else:
        th = 4.0
        o.append(f'<rect x="{tx:.1f}" y="{mid - th / 2:.1f}" width="{track_w:.1f}" '
                 f'height="{th}" rx="{th / 2}" fill="{TRACK}"/>')
        # 出厂值刻度：常显，"我现在离出厂多远"要看得见
        dx = tx + track_w * norm(c)
        o.append(f'<line x1="{dx:.1f}" y1="{mid - 7:.1f}" x2="{dx:.1f}" y2="{mid + 7:.1f}" '
                 f'stroke="rgba(26,26,28,.24)" stroke-width="1.5" stroke-linecap="round"/>')
        if v > 0.004:
            o.append(f'<rect x="{tx:.1f}" y="{mid - th / 2:.1f}" '
                     f'width="{max(th, track_w * v):.1f}" height="{th}" rx="{th / 2}" '
                     f'fill="{fill}"/>')
        hx = tx + track_w * v
        hr = 7.0 if state == "drag" else (6.5 if state == "hover" else 5.5)
        o.append(f'<circle cx="{hx:.1f}" cy="{mid:.1f}" r="{hr}" fill="#FFFFFF" '
                 f'stroke="{fill}" stroke-width="{2.0 if state == "drag" else 1.5}"/>')
        if state == "drag":
            tip = fmt(c, real(c, v))
            tw = 26 + len(tip) * fs_value * 0.62
            txx, tyy = hx - tw / 2, y - 26.0
            o.append(f'<rect x="{txx:.1f}" y="{tyy:.1f}" width="{tw:.1f}" height="23" rx="6" '
                     f'fill="{INK}"/>'
                     f'<path d="M {hx - 4:.1f} {tyy + 23:.1f} L {hx:.1f} {tyy + 28:.1f} '
                     f'L {hx + 4:.1f} {tyy + 23:.1f} Z" fill="{INK}"/>'
                     f'<text x="{hx:.1f}" y="{tyy + 15.2:.1f}" text-anchor="middle" '
                     f'font-family="{MONO}" font-size="{fs_value - 1.5}" '
                     f'fill="#FFFFFF">{esc(tip)}</text>')

    o.append(f'<text x="{x + inner:.1f}" y="{mid + fs_value * 0.35:.2f}" '
             f'text-anchor="end" font-family="{MONO}" font-size="{fs_value}" '
             f'font-weight="500" fill="{INK if not dim else INK3}">'
             f'{esc(fmt(c, real(c, v)))}</text>')
    return "".join(o)


def params_svg(ctrls: list[dict], module: str, x: float, y: float, w: float,
               row_h: float, label_w: float, value_w: float,
               fs_label: float, fs_value: float, fs_title: float,
               focus_id: str | None = None, focus_state: str = "idle",
               overrides: dict | None = None) -> str:
    rows = ring_controls(ctrls, module)
    sw = switch_of(ctrls, module)
    on = module in LIT
    ov = overrides or {}
    out: list[str] = []

    out.append(f'<text x="{x}" y="{y + fs_title * 0.82:.2f}" font-family="{UI}" '
               f'font-size="{fs_title}" font-weight="700" letter-spacing="0.06em" '
               f'fill="{INK}">{module.upper()}</text>')
    if sw:
        tw, th = 38.0, 21.0
        out.append(toggle(x + w - tw, y + fs_title * 0.82 - th + 3, tw, th, on))
    else:
        out.append(f'<text x="{x + w:.1f}" y="{y + fs_title * 0.72:.2f}" text-anchor="end" '
                   f'font-family="{UI}" font-size="10.5" letter-spacing="0.08em" '
                   f'fill="{INK3}">NO SWITCH</text>')

    track_w = w - label_w - value_w
    y0 = y + fs_title + 22.0
    for i, c in enumerate(rows):
        st = focus_state if c["id"] == focus_id else "idle"
        out.append(slider_row(c, x, y0 + i * row_h, label_w, track_w, value_w,
                              fs_label, fs_value, on, st, ov.get(c["id"])))
    return "".join(out)


# ---------------------------------------------------------------------------
# 面板
# ---------------------------------------------------------------------------
def panel_svg(geo, ctrls, w, h, tree_box, list_box, selected,
              fs_node, fs_node_val, fs_label, fs_value, fs_title,
              focus_id=None, focus_state="idle", overrides=None) -> str:
    W, H, bar = w, h, 48.0
    defs = (f'<pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse">'
            f'<circle cx="1" cy="1" r="0.7" fill="{DOTS}"/></pattern>')
    p = [f'<rect width="{W}" height="{H}" fill="{PAPER}"/>',
         f'<rect width="{W}" height="{H}" fill="url(#dots)"/>']
    p.append(f'<line x1="0" y1="{bar}" x2="{W}" y2="{bar}" stroke="{HAIR}" stroke-width="1"/>')
    p.append(f'<text x="26" y="{bar / 2 + 5:.1f}" font-family="{UI}" font-size="13" '
             f'font-weight="700" letter-spacing="0.20em" fill="{INK}">TRÄNE</text>')
    p.append(f'<text x="{W - 26}" y="{bar / 2 + 4.5:.1f}" text-anchor="end" '
             f'font-family="{MONO}" font-size="12" fill="{INK2}">+0.0 dB</text>')
    mx = W - 26 - 62 - 14
    p.append(f'<rect x="{mx - 96:.1f}" y="{bar / 2 - 2:.1f}" width="96" height="4" rx="2" '
             f'fill="{TRACK}"/>')
    p.append(f'<rect x="{mx - 96:.1f}" y="{bar / 2 - 2:.1f}" width="72" height="4" rx="2" '
             f'fill="{ACCENT}"/>')

    lx = tree_box[0] + tree_box[2] + 26.0
    if lx < W - 40:
        p.append(f'<line x1="{lx:.1f}" y1="{bar + 22:.1f}" x2="{lx:.1f}" y2="{H - 22:.1f}" '
                 f'stroke="{HAIR}" stroke-width="1"/>')
    else:
        ly = tree_box[1] + tree_box[3] + 30.0
        p.append(f'<line x1="26" y1="{ly:.1f}" x2="{W - 26}" y2="{ly:.1f}" '
                 f'stroke="{HAIR}" stroke-width="1"/>')

    tl = tree_layout(geo, *tree_box)
    p.append(tree_svg(geo, ctrls, tl, fs_node, fs_node_val))
    sel = next((q for q in tl["pts"] if q["module"] == selected), None)
    if sel:
        p.append(selected_ring(sel["x"], sel["y"], tl["r"] + 5.5))
    p.append(params_svg(ctrls, selected, *list_box, fs_label=fs_label,
                        fs_value=fs_value, fs_title=fs_title,
                        focus_id=focus_id, focus_state=focus_state,
                        overrides=overrides))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}"><defs>{defs}</defs>{"".join(p)}</svg>')


def interaction_strip(ctrls: list[dict], x0: float, y0: float) -> tuple[str, float]:
    c = next(q for q in ctrls if q["id"] == "grain_position")
    specs = [
        ("idle", "静止", "轨道上是当前值；那道淡刻度是出厂值 —— 离出厂多远一眼看得出。", None),
        ("hover", "悬停", "整行微微抬起，把手变大，数值转深。不改变任何值。", None),
        ("drag", "拖拽", "整行高亮，气泡跟着手走。按住 Shift 走 1/10 步长。", 0.68),
        ("disabled", "模块关闭", "整组降到 30% 对比。看得见结构，但不抢注意力。", None),
    ]
    bw, bh, gap = 480.0, 152.0, 24.0
    out: list[str] = []
    for i, (st, name, desc, val) in enumerate(specs):
        bx = x0 + i * (bw + gap)
        out.append(f'<rect x="{bx}" y="{y0}" width="{bw}" height="{bh}" rx="10" '
                   f'fill="#FFFFFF" stroke="{HAIR}" stroke-width="1"/>')
        out.append(f'<text x="{bx + 20}" y="{y0 + 28}" font-family="{UI}" font-size="12.5" '
                   f'font-weight="700" fill="{INK}">{name}</text>')
        out.append(f'<text x="{bx + 20 + len(name) * 14 + 10}" y="{y0 + 28}" '
                   f'font-family="{MONO}" font-size="10.5" fill="{INK3}">{st}</text>')
        out.append(f'<text x="{bx + 20}" y="{y0 + 47}" font-family="{UI}" font-size="10.5" '
                   f'fill="{INK2}">{esc(desc)}</text>')
        on = st != "disabled"
        out.append(slider_row(c, bx + 20, y0 + 78, 90.0, 250.0, 100.0,
                              12.0, 13.0, on, st, val))
    return "".join(out), 4 * bw + 3 * gap


# ---------------------------------------------------------------------------
# 版面
# ---------------------------------------------------------------------------
A_W, A_H = 980.0, 640.0
TREE_A = (24.0, 74.0, 332.0, 540.0)
LIST_A = (410.0, 74.0, 540.0, 60.0, 100.0, 100.0)

B_W, B_H = 560.0, 1040.0
TREE_B = (28.0, 74.0, 504.0, 500.0)
LIST_B = (28.0, 620.0, 504.0, 44.0, 96.0, 96.0)

HEAD = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>%(title)s</title><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#EDEDEA;font-family:%(ui)s;width:%(w)dpx;padding:%(pt)dpx %(m)dpx 40px;color:#1A1A1C}
h1{font-size:19px;font-weight:700;letter-spacing:.02em}
h1 small{display:block;font-size:12px;font-weight:400;letter-spacing:.04em;
         color:rgba(26,26,28,.52);margin-top:8px;line-height:1.8}
.row{display:flex;gap:%(gap)dpx;align-items:flex-start;margin-top:34px}
.col{width:%(cw)dpx}
.cap{height:56px;border-bottom:1px solid rgba(26,26,28,.20);padding-bottom:10px}
.cap b{display:block;font-size:13.5px;font-weight:700}
.cap span{display:block;font-size:11px;color:rgba(26,26,28,.55);margin-top:5px}
.panel{box-shadow:0 0 0 .5px rgba(26,26,28,.13),0 16px 44px rgba(26,26,28,.11)}
.panel svg{display:block}
.note{font-size:11px;line-height:1.9;color:rgba(26,26,28,.6);margin-top:14px;text-align:justify}
h2{font-size:14px;font-weight:700;margin-top:44px;letter-spacing:.02em}
h2 small{font-size:11px;font-weight:400;color:rgba(26,26,28,.55);margin-left:12px}
.strip{margin-top:18px}
.strip svg{display:block}
</style></head><body>
"""


def sheet_landscape(geo, ctrls, version) -> tuple[str, int, int]:
    a = panel_svg(geo, ctrls, A_W, A_H, TREE_A, LIST_A, "grain",
                  12.0, 9.0, 12.0, 13.0, 17.0,
                  focus_id="grain_position", focus_state="drag",
                  overrides={"grain_position": 0.68})
    b = panel_svg(geo, ctrls, A_W, A_H, TREE_A, LIST_A, "sweep",
                  12.0, 9.0, 12.0, 13.0, 17.0)
    strip, strip_w = interaction_strip(ctrls, 0.0, 0.0)

    M, GAP, TOP = 48, 40, 96
    W = M * 2 + int(A_W) * 2 + GAP
    H = TOP + int(A_H) + 74 + 152 + 300
    head = HEAD % {"title": f"Träne UI v{version} · 世界树 = 地图，参数 = 检查器",
                   "ui": UI, "w": W, "pt": TOP - 34, "m": M, "gap": GAP, "cw": int(A_W)}
    return head + f'''<h1>Träne · UI v{version} —— 世界树 = 地图，参数 = 检查器
<small>几何来自 panel_probe --dump-geometry，参数表解析自 TranePanel.h 的 kControls，
树按原图两条比值（r/柱距 = 0.341、r/树高 = 0.074）等比装箱。整版共用同一份真实数据。</small></h1>
<div class="row">
  <div class="col">
    <div class="cap"><b>① 横屏 980 × 640 · GRAIN 展开（开）</b>
      <span>圆里加了该模块的主参数读数 —— 树既是地图，也是仪表盘</span></div>
    <div class="panel">{a}</div>
    <p class="note">参数名 12px / 数值 13px 等宽 / 轨道 320px。
    轨道上那道淡刻度是出厂值，所以"我现在离出厂多远"是看得见的。
    当前行是拖拽态：值 0.68，气泡跟着手走，出厂刻度 0.50 留在原地。</p>
  </div>
  <div class="col">
    <div class="cap"><b>② 横屏 980 × 640 · SWEEP 展开（关）</b>
      <span>关闭态 · 枚举参数（LP / BP / HP）不再用滑杆</span></div>
    <div class="panel">{b}</div>
    <p class="note">模块关掉时整组降到 30% 对比 —— 结构还在，但不抢注意力。
    sweep_mode 是三档枚举，画成三段：按哪段就是哪段，不存在"0.5 到底算 LP 还是 BP"。
    RUIN / SPACE / OUT 没有开关，标题右侧标 NO SWITCH，边框亮不亮由实际值推出。</p>
  </div>
</div>
<h2>③ 一行参数的四个状态<small>交互规格 —— 覆盖"看不出值大还是小"和"拖的时候读不到数"</small></h2>
<div class="strip"><svg xmlns="http://www.w3.org/2000/svg" width="{strip_w}" height="152">{strip}</svg></div>
</body></html>''', W, H


def sheet_portrait(geo, ctrls, version) -> tuple[str, int, int]:
    b = panel_svg(geo, ctrls, B_W, B_H, TREE_B, LIST_B, "grain",
                  11.0, 8.5, 12.0, 13.0, 16.0,
                  focus_id="grain_position", focus_state="drag",
                  overrides={"grain_position": 0.68})
    M, TOP = 48, 96
    W, H = M * 2 + int(B_W), TOP + int(B_H) + 260
    head = HEAD % {"title": f"Träne UI v{version} · 竖屏", "ui": UI, "w": W,
                   "pt": TOP - 34, "m": M, "gap": 40, "cw": int(B_W)}
    return head + f'''<h1>Träne · UI v{version} —— 竖屏 560 × 1040
<small>保留你现在的面板比例。竖屏里"宽"是稀缺轴，所以树只占上半、参数占满整行宽度 ——
圆不再装参数，半径就不必为弧长让路。</small></h1>
<div class="cap" style="margin-top:26px"><b>竖屏 · GRAIN 展开（开）</b>
  <span>同一套组件，只换排布：树在上，检查器在下</span></div>
<div class="panel">{b}</div>
<p class="note">树在竖屏里只用到约 260px 宽（等比装箱的必然结果），两侧留白正好给"呼吸"。
如果哪天要压到 480 宽以下，先动的应该是树的箱体，不是字号。</p>
</body></html>''', W, H


def render(html: str, w: int, h: int, scale: int, tmp: pathlib.Path, tag: str):
    from PIL import Image
    page, png = tmp / f"{tag}.html", tmp / f"{tag}.png"
    page.write_text(html, encoding="utf-8")
    # **纯 --headless**：--headless=new 在这台机器上是"挂住不返回"，不是报错
    subprocess.run([find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
                    "--hide-scrollbars", f"--force-device-scale-factor={scale}",
                    f"--screenshot={png}", f"--window-size={w},{h}",
                    "--virtual-time-budget=8000", page.as_uri()],
                   capture_output=True, text=True, timeout=180)
    assert png.is_file(), "Chrome 没截出图"
    return Image.open(png).convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT.parent / "outputs"))
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--version", default="0.21")
    ap.add_argument("--portrait", action="store_true", help="同时出一版竖屏")
    args = ap.parse_args()

    geo, ctrls = read_geometry(), read_controls()
    print(f"几何 {geo['w']}×{geo['h']} · 参数 {len(ctrls)} 条"
          f"（{sum(1 for c in ctrls if not c['label'])} 个模块开关）")

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_ui_"))

    html, w, h = sheet_landscape(geo, ctrls, args.version)
    im = render(html, w, h, args.scale, tmp, "land")
    dest = outdir / f"Trane_UI_v{args.version}.png"
    im.save(dest)
    print(f"→ {dest}  {im.size[0]}×{im.size[1]}")

    if args.portrait:
        html, w, h = sheet_portrait(geo, ctrls, args.version)
        im = render(html, w, h, args.scale, tmp, "port")
        dest = outdir / f"Trane_UI_v{args.version}_portrait.png"
        im.save(dest)
        print(f"→ {dest}  {im.size[0]}×{im.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
