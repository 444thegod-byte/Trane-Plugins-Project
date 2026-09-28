#!/usr/bin/env python3
"""把 Trane.maxpat 的 Presentation View 渲染成一张 SVG 面板示意图。

设计原则：**完全从源文件读**，不手写任何坐标或文案。
- comment 对象 -> 直接取它的 text 和 presentation_rect 当标签画
- live.toggle  -> 圆角方框 + 圆点，状态取 parameter_initial
- live.dial    -> 圆形 + 指针，指针角度取 parameter_initial 在 [mmin, mmax] 里的归一化位置
- live.tab     -> 分段条，条目取 parameter_enum，选中项取 parameter_initial
- live.menu    -> 下拉条，当前项取 parameter_enum[parameter_initial]

这样只要改 maxpat 再跑一次，图就跟着变，不会和实际设备脱节。

用法:
    python3 tools/render_panel.py                 # 输出到 outputs/Trane_panel_layout.svg
    python3 tools/render_panel.py --out /tmp/x.svg
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "Trane.maxpat"
DEFAULT_OUT = ROOT / "outputs" / "Trane_panel_layout.svg"

DEVICE_W = 650.0
DEVICE_H = 169.0

# 面板配色（深色，接近 Ableton 12 原生）
C_PANEL_FILL = "#232322"
C_PANEL_EDGE = "#B4B2A9"
C_TITLE = "#D3D1C7"
C_GROUP = "#5DCAA5"      # 分组标题用一点青色，便于分区
C_HINT = "#888780"
C_LABEL = "#B4B2A9"
C_CTRL_FILL = "#2C2C2A"
C_DIAL_FILL = "#444441"
C_DIAL_POINTER = "#D3D1C7"
C_KNOB_OFF = "#5F5E5A"
C_KNOB_ON = "#1D9E75"
C_KNOB_ON_TEXT = "#E1F5EE"

# 外框留白与缩放：650 宽的设备放进 680 宽的画布，留出左右呼吸位
MARGIN_X = 41.0
MARGIN_Y = 45.0
SCALE = 0.92

# 旋钮指针：-135°(最小) 扫到 +135°(最大)，0° 指向正上方，顺时针为正
SWEEP = 270.0
START = -135.0


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _valueof(pt: dict) -> dict:
    return (pt.get("saved_attribute_attributes") or {}).get("valueof") or {}


def _scalar(v, default=0.0) -> float:
    """parameter_initial / mmin / mmax 可能是标量也可能是单元素列表。"""
    if isinstance(v, list):
        v = v[0] if v else default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _knob_angle(pt: dict) -> float:
    va = _valueof(pt)
    lo = _scalar(va.get("parameter_mmin"), 0.0)
    hi = _scalar(va.get("parameter_mmax"), 1.0)
    val = _scalar(va.get("parameter_initial"), lo)
    if hi <= lo:
        norm = 0.0
    else:
        norm = max(0.0, min(1.0, (val - lo) / (hi - lo)))
    return START + SWEEP * norm


def _pointer(cx: float, cy: float, angle_deg: float, length: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return cx + length * math.sin(rad), cy - length * math.cos(rad)


def collect_boxes(patcher: dict) -> list[dict]:
    out = []
    for b in patcher.get("patcher", {}).get("boxes", []):
        pt = b.get("box", {})
        if pt.get("presentation") and pt.get("presentation_rect"):
            out.append(pt)
    return out


def render(patcher: dict) -> str:
    boxes = collect_boxes(patcher)

    body: list[str] = []

    for pt in sorted(boxes, key=lambda p: (p["presentation_rect"][1], p["presentation_rect"][0])):
        x, y, w, h = (float(v) for v in pt["presentation_rect"])
        mc = pt.get("maxclass", "")
        va = _valueof(pt)

        if mc == "comment":
            txt = (pt.get("text") or "").strip()
            if not txt:
                continue
            # 分组标题（CAPTURE / GRAIN / ARP / HUGE SPACE）用青色 + 中粗
            is_group = txt.isupper() and len(txt) <= 12 and " " not in txt.strip("-")
            fill = C_GROUP if is_group else (C_TITLE if y < 14 else C_LABEL)
            size = h if h >= 12 else 12.0
            body.append(
                f'<text x="{x:.1f}" y="{y + h - 2:.1f}" font-size="{size:.0f}" '
                f'font-weight="500" fill="{fill}">{_esc(txt)}</text>'
            )
            continue

        if mc == "live.toggle":
            on = _scalar(va.get("parameter_initial"), 0.0) >= 0.5
            fill = C_KNOB_ON if on else C_CTRL_FILL
            dot = C_KNOB_ON_TEXT if on else C_KNOB_OFF
            stroke = C_KNOB_ON_TEXT if on else C_PANEL_EDGE
            body.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{fill}" stroke="{stroke}" stroke-opacity="0.45" stroke-width="1"/>'
                f'<circle cx="{x + w / 2:.1f}" cy="{y + h / 2:.1f}" r="3.5" fill="{dot}"/>'
            )
            continue

        if mc == "live.dial":
            cx, cy, r = x + w / 2, y + h / 2, min(w, h) / 2
            px, py = _pointer(cx, cy, _knob_angle(pt), r * 0.69)
            body.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{C_DIAL_FILL}" '
                f'stroke="{C_PANEL_EDGE}" stroke-opacity="0.5" stroke-width="1"/>'
                f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{px:.2f}" y2="{py:.2f}" '
                f'stroke="{C_DIAL_POINTER}" stroke-width="1.8" stroke-linecap="round"/>'
            )
            continue

        if mc == "live.tab":
            items = va.get("parameter_enum") or []
            sel = int(_scalar(va.get("parameter_initial"), 0.0))
            body.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{C_CTRL_FILL}" stroke="{C_PANEL_EDGE}" stroke-opacity="0.45" stroke-width="1"/>'
            )
            if items:
                seg = (w - 3.0) / len(items)
                for i, name in enumerate(items):
                    sx = x + 1.5 + i * seg
                    if i == sel:
                        body.append(
                            f'<rect x="{sx:.1f}" y="{y + 1.5:.1f}" width="{seg:.1f}" '
                            f'height="{h - 3:.1f}" rx="3" fill="{C_KNOB_ON}"/>'
                        )
                    body.append(
                        f'<text x="{sx + seg / 2:.1f}" y="{y + h / 2:.1f}" font-size="{min(12.0, h - 8):.0f}" '
                        f'text-anchor="middle" dominant-baseline="central" '
                        f'fill="{C_KNOB_ON_TEXT if i == sel else C_LABEL}">{_esc(name)}</text>'
                    )
            continue

        if mc == "live.menu":
            items = va.get("parameter_enum") or []
            sel = int(_scalar(va.get("parameter_initial"), 0.0))
            cur = items[sel] if 0 <= sel < len(items) else ""
            body.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
                f'fill="{C_CTRL_FILL}" stroke="{C_PANEL_EDGE}" stroke-opacity="0.45" stroke-width="1"/>'
                f'<text x="{x + 8:.1f}" y="{y + h / 2:.1f}" font-size="{min(12.0, h - 8):.0f}" '
                f'dominant-baseline="central" fill="{C_TITLE}">{_esc(cur)}</text>'
                f'<path d="M{x + w - 15:.0f} {y + h / 2 - 2.5:.0f} L{x + w - 10.5:.0f} {y + h / 2 + 2:.0f} '
                f'L{x + w - 6:.0f} {y + h / 2 - 2.5:.0f}" fill="none" stroke="{C_HINT}" '
                f'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>'
            )
            continue

        # 其余 maxclass（live.text / live.numbox 等）暂时不画，先保证已用到的都准

    panel_w = DEVICE_W * SCALE
    panel_h = DEVICE_H * SCALE
    total_h = MARGIN_Y + panel_h + 20.0

    return (
        f'<svg viewBox="0 0 680 {total_h:.0f}" width="100%" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" font-family="ui-sans-serif,-apple-system,Helvetica,Arial,sans-serif">\n'
        f"<title>Träne 设备面板布局（{DEVICE_W:.0f} × {DEVICE_H:.0f} 像素）</title>\n"
        f"<desc>Max for Live 音频效果器面板，由 src/Trane.maxpat 的 Presentation View 自动渲染。</desc>\n"
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" '
        f'markerHeight="6" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" '
        f'stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</marker></defs>\n"
        f'<rect x="{MARGIN_X:.0f}" y="{MARGIN_Y:.0f}" width="{panel_w:.1f}" height="{panel_h:.1f}" '
        f'rx="6" fill="{C_PANEL_FILL}" stroke="{C_PANEL_EDGE}" stroke-opacity="0.3" stroke-width="1"/>\n'
        f'<g transform="translate({MARGIN_X:.0f},{MARGIN_Y:.0f}) scale({SCALE})">\n'
        + "\n".join(body)
        + "\n</g>\n</svg>\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    patcher = json.loads(pathlib.Path(args.src).read_text(encoding="utf-8"))
    svg = render(patcher)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8")

    n = len(collect_boxes(patcher))
    print(f"已渲染 {n} 个 Presentation 对象 -> {out}（{len(svg)} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
