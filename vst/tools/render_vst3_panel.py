#!/usr/bin/env python3
"""从 PluginEditor.cpp 直接渲染 Träne 的真实面板布局（SVG）。

预览只解析实际 C++ 里的控件坐标和标签，避免出现"图是画好看的、代码是另一回事"。
v0.10 视觉必须对齐 PluginEditor.cpp：Ableton 原生式平面盘、纯黑、高亮白、无顶栏。

用法:
    python tools/render_vst3_panel.py [输出.svg]
"""
from __future__ import annotations

import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EDITOR = ROOT / "plugin" / "PluginEditor.cpp"

BG = "#000000"
INK_FAINT = 0.20
INK_LINE = 0.48
INK_DIM = 0.84
INK_FULL = 1.00
FONT = "Ableton Sans, Helvetica Neue, Helvetica, Arial"


def ink(alpha: float) -> str:
    return f"rgba(255,255,255,{alpha:g})"


def split_args(s: str) -> list[str]:
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


def parse(src: str):
    def arr(name: str) -> list[int]:
        m = re.search(rf"constexpr int {name}\[\d+\]\s*=\s*\{{([^}}]*)\}}", src)
        assert m, f"找不到 {name}"
        return [int(v) for v in m.group(1).split(",") if v.strip()]

    def const(name: str) -> int:
        m = re.search(rf"constexpr int {name}\s*=\s*(\d+)", src)
        assert m, f"找不到 {name}"
        return int(m.group(1))

    ys, lys = arr("kRowY"), arr("kLabelY")
    cellw, marginx = const("kCellW"), const("kMarginX")
    knob, tglh = const("kKnob"), const("kToggleH")

    def rx(tok: str) -> int:
        tok = tok.strip()
        m = re.match(r"cell\((\d+)\)$", tok)
        return marginx + cellw * int(m.group(1)) if m else int(tok)

    def ry(tok: str) -> int:
        tok = tok.strip()
        m = re.match(r"kRowY\[(\d+)\]$", tok)
        return ys[int(m.group(1))] if m else int(tok)

    ctrls = []
    for m in re.finditer(r'add(Knob|Toggle|Choice)\(\s*("[^"]*"(?:[^;]*?))\)\s*;', src, re.S):
        kind = m.group(1).lower()
        args = split_args(m.group(2))
        param = args[0].strip('"')
        label = args[1].strip('"') if kind in ("knob", "toggle") else None
        if kind == "knob":
            x, y = rx(args[2]), ry(args[3])
        else:
            x, y = rx(args[2 if kind == "toggle" else 1]), ry(args[3 if kind == "toggle" else 2])
            y += (knob - tglh) // 2
        ctrls.append({"kind": kind, "param": param, "label": label, "x": x, "y": y})

    groups = []
    for text, gxtok, gytok in re.findall(r'addGroup\(\s*"([^"]*)",\s*([^,]+),\s*([^)]+)\)\s*;', src):
        m = re.match(r"kLabelY\[(\d+)\]$", gytok.strip())
        groups.append((text, rx(gxtok), lys[int(m.group(1))] if m else int(gytok)))
    return const("kPanelW"), const("kPanelH"), ctrls, groups, knob, tglh


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def point(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return cx + radius * math.sin(radians), cy - radius * math.cos(radians)


def knob_svg(x: int, y: int, label: str, pos: float, value: str, knob: int) -> str:
    # 与 C++ 对齐：slider 在 cell 内右移 5px；盘面填充 + 三刻度 + 指针，不画值弧。
    cx, cy = x + 5 + knob / 2, y + knob / 2
    r = knob / 2 - 1.5
    start, end = 225.0, 495.0
    angle = start + pos * (end - start)

    out = [
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{ink(INK_FAINT)}"/>',
        f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="none" stroke="{ink(INK_LINE)}" stroke-width="1"/>',
    ]
    for mark in (start, (start + end) / 2, end):
        ax, ay = point(cx, cy, r - 2.5, mark)
        bx, by = point(cx, cy, r - 6.0, mark)
        out.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" y2="{by:.2f}" '
                   f'stroke="{ink(INK_DIM)}" stroke-width="1"/>')

    px0, py0 = point(cx, cy, r * 0.22, angle)
    px1, py1 = point(cx, cy, r - 8.5, angle)
    out.extend([
        f'<line x1="{px0:.2f}" y1="{py0:.2f}" x2="{px1:.2f}" y2="{py1:.2f}" '
        f'stroke="{ink(INK_FULL)}" stroke-width="1.6"/>',
        f'<circle cx="{px1:.2f}" cy="{py1:.2f}" r="1.8" fill="{ink(INK_FULL)}"/>',
        f'<text x="{cx:.2f}" y="{y + knob + 13}" fill="{ink(INK_FULL)}" font-size="11" '
        f'font-weight="700" text-anchor="middle" font-family="{FONT}">{esc(value)}</text>',
        f'<text x="{x + knob / 2 + 5:.2f}" y="{y + knob + 30}" fill="{ink(INK_DIM)}" '
        f'font-size="10" font-weight="700" text-anchor="middle" font-family="{FONT}" '
        f'letter-spacing="0.045em">{esc(label)}</text>',
    ])
    return "\n".join(out)


def toggle_svg(x: int, y: int, label: str, on: bool, knob: int, height: int) -> str:
    x += 5
    out = []
    if on:
        out.append(f'<rect x="{x + .5}" y="{y + .5}" width="{knob - 1}" height="{height - 1}" '
                   f'fill="{ink(INK_FULL)}"/>')
    out.append(f'<rect x="{x + .5}" y="{y + .5}" width="{knob - 1}" height="{height - 1}" fill="none" '
               f'stroke="{ink(INK_FULL if on else INK_LINE)}" stroke-width="1"/>')
    out.append(f'<text x="{x + knob / 2:.2f}" y="{y + height / 2 + 4:.2f}" '
               f'fill="{BG if on else ink(INK_FULL)}" font-size="10" font-weight="700" '
               f'text-anchor="middle" font-family="{FONT}" letter-spacing="0.035em">{esc(label)}</text>')
    return "\n".join(out)


def choice_svg(x: int, y: int, knob: int, height: int) -> str:
    x += 5
    cy = y + height / 2
    return "\n".join([
        f'<rect x="{x + .5}" y="{y + .5}" width="{knob - 1}" height="{height - 1}" fill="none" '
        f'stroke="{ink(INK_LINE)}" stroke-width="1"/>',
        f'<text x="{x + 7}" y="{cy + 4:.2f}" fill="{ink(INK_FULL)}" font-size="10" font-weight="700" '
        f'font-family="{FONT}">LP</text>',
        f'<path d="M {x + knob - 14:.1f} {cy - 2:.1f} L {x + knob - 10:.1f} {cy + 2:.1f} '
        f'L {x + knob - 6:.1f} {cy - 2:.1f}" fill="none" stroke="{ink(INK_FULL)}" stroke-width="1"/>',
    ])


# 预览用的一组有动作感的数值；不影响插件或任何参数默认值。
ON_PARAMS = {"freeze", "grain_on", "stutter_on", "comb_on", "tape_on", "delay_on"}
POS = {
    "loop_ms": .42, "seam_ms": .28, "grain_size": .35, "grain_density": .48,
    "grain_position": .75, "grain_spray": .22, "grain_rate": .30, "grain_spread": .55,
    "grain_reverse": .25, "grain_mix": .80, "stutter_size": .40, "stutter_rate": .35,
    "stutter_jump": .30, "stutter_mix": .90, "comb_tune": .45, "comb_feedback": .60,
    "comb_mix": .50, "tape_speed": .62, "tape_wobble": .20, "tape_mix": 1.00,
    "ruin_mode": .65, "ruin_drive": .40, "ruin_fold": .55, "ruin_crush": .30,
    "ruin_ring": .15, "sweep_rate": .30, "sweep_depth": .45, "sweep_center": .55,
    "sweep_reso": .35, "delay_time": .45, "delay_feedback": .50, "delay_damp": .35,
    "delay_pingpong": .20, "delay_mix": .35, "space_mix": .60, "space_size": .70,
    "space_tail": .80, "space_damp": .40, "space_diffuse": .70, "output": .50,
}
VALUE = {
    "loop_ms": "250ms", "seam_ms": "10ms", "grain_size": "120ms", "grain_density": "12",
    "grain_position": "0.50", "grain_spray": "0.15", "grain_rate": "1.00x", "grain_spread": "0.60",
    "grain_reverse": "0.25", "grain_mix": "1.00", "stutter_size": "90ms", "stutter_rate": "4.00",
    "stutter_jump": "0.35", "stutter_mix": "1.00", "comb_tune": "220", "comb_feedback": "0.60",
    "comb_mix": "0.50", "tape_speed": "1.00x", "tape_wobble": "0.12", "tape_mix": "1.00",
    "ruin_mode": "0.00", "ruin_drive": "0.35", "ruin_fold": "0.00", "ruin_crush": "0.00",
    "ruin_ring": "0.00", "sweep_rate": "0.80", "sweep_depth": "0.40", "sweep_center": "1.20k",
    "sweep_reso": "0.30", "delay_time": "375ms", "delay_feedback": "0.45", "delay_damp": "0.35",
    "delay_pingpong": "0.00", "delay_mix": "0.35", "space_mix": "0.55", "space_size": "0.70",
    "space_tail": "0.80", "space_damp": "0.40", "space_diffuse": "0.70", "output": "0.0dB",
}


def main() -> int:
    w, h, controls, groups, knob, toggle_h = parse(EDITOR.read_text(encoding="utf-8"))
    assert len(controls) >= 45, f"只解析出 {len(controls)} 个控件"

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
        f'<rect width="{w}" height="{h}" fill="{BG}"/>',
    ]
    for text, gx, gy in groups:
        out.append(f'<text x="{gx}" y="{gy + 10}" fill="{ink(INK_FULL)}" font-size="10" '
                   f'font-weight="700" font-family="{FONT}" letter-spacing=".085em">{esc(text)}</text>')

    for control in controls:
        if control["kind"] == "knob":
            out.append(knob_svg(control["x"], control["y"], control["label"] or control["param"],
                                POS.get(control["param"], .5), VALUE.get(control["param"], "0.50"), knob))
        elif control["kind"] == "toggle":
            out.append(toggle_svg(control["x"], control["y"], control["label"] or control["param"],
                                  control["param"] in ON_PARAMS, knob, toggle_h))
        else:
            out.append(choice_svg(control["x"], control["y"], knob, toggle_h))

    out.append("</svg>")
    dest = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "outputs" / "Trane_vst3_panel.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(out), encoding="utf-8")
    print(f"面板尺寸 {w}x{h}，控件 {len(controls)} 个，分组 {len(groups)} 个")
    print(f"已写出 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
