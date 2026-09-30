#!/usr/bin/env python3
"""⚠️ 历史稿（v0.18 的"背景与材质四方案"），**已过期，跑不起来了**。
它读的 `ring_r` / `scale_r` / `node` 三行几何在 v0.33 随世界树一起删了
（`geometryDump()` 里已经没有它们）。当前背景的做法见 `plugin/TranePanel.cpp`
的 `bakeBackdrop` / `tintRegion`，以及 `tools/bake_backdrop.py`。
留着它只为记录当时"四个背景方向"的取舍过程。

Träne 面板「背景与材质」方向对照稿 —— 四个方案，同一套真实几何。

为什么要这个文件
================
小绪说 v0.18 的背景"不高级、不舒服"。这不是审美分歧，是可归因的：
背景是一整幅高频字符画（满幅 level 3 = 100% 墨），而信息层（圆、字、辐条）
也是墨 —— 两层抢同一个通道，眼睛没有落点。

但"哪个方向更高级"必须能**看着比**，不能靠嘴说。所以这里把四个方案
并排画出来，**四个方案共用同一份几何与同一份参数值**，
唯一的变量就是「背景 + 材质 + 字阶」这一层。

几何从哪来（不许手抄）
====================
  · 圆心 / 半径 / 环位  → `panel_probe --dump-geometry`（编译产物，唯一真相）
  · 参数表（lo/hi/skew/def/label/fmt）→ 直接解析 `plugin/TranePanel.h` 的 kControls
  · 段心角 → 移植 `bestRot()` / `segmentsFor()` / `orient()`，与 C++ 逐行对应

所以这份稿子里的辐条长度、环形文字位置，和插件里画出来的**是同一组数**。
手抄一份常量就多一个会分叉的地方。

四个方案
========
  V0 现状      —— v0.18 的复刻（满幅字符 + 蒂芙尼蓝光晕），作为基准
  V1 纸·墨     —— 推荐：字符画退到外框带，纸面回归安静；光晕改"墨洇"
  V2 深色硬件  —— 深灰面板 + 凹陷盘 + 单一琥珀强调
  V3 工程图    —— 纸白 + 方格 + 全部等宽 + 工程红

用法
====
    python tools/render_bg_study.py [--outdir ../outputs] [--scale 2]
"""
from __future__ import annotations

import argparse
import base64
import math
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent          # .../vst
PROBE = ROOT / "build" / "panel_probe_artefacts" / "Release" / "panel_probe"
HEADER = ROOT / "plugin" / "TranePanel.h"
VIDEO = pathlib.Path("/Users/444_thegod/Desktop/444site-2/asciify.mp4")

PAPER = (0xFA, 0xFA, 0xF9)
INK = (0x0E, 0x0E, 0x0F)
PAPER_HEX = "#FAFAF9"
INK_HEX = "#0E0E0F"
ACCENT = "#0ABAB5"
ACCENT_DEEP = "#00938F"

# 与 TranePanel.h 的 kPaths 一致 —— 22 条，生命之树的标准连线
PATHS = [(0, 1), (0, 2), (0, 5), (1, 2), (1, 5), (1, 3), (2, 5), (2, 4),
         (3, 4), (3, 5), (3, 6), (4, 5), (4, 7), (5, 6), (5, 7), (5, 8),
         (6, 7), (6, 8), (6, 9), (7, 8), (7, 9), (8, 9)]
TRUNK = {(0, 5), (5, 8), (8, 9)}

# 演示状态：与 check_panel_render.py 的 demo 一致
LIT = {"freeze", "grain", "ruin", "space", "out"}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]


# ---------------------------------------------------------------------------
# 几何：从编译产物读
# ---------------------------------------------------------------------------
def read_geometry() -> dict:
    assert PROBE.is_file(), f"找不到 {PROBE}（先构建 panel_probe）"
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    geo = {"nodes": []}
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "panel":
            geo["w"], geo["h"] = int(p[1]), int(p[2])
        elif p[0] == "ring_r":
            geo["ring_r"] = float(p[1])
        elif p[0] == "scale_r":
            geo["scale_r"] = float(p[1])
        elif p[0] == "node":
            geo["nodes"].append({"sephira": p[1], "module": p[2],
                                 "x": float(p[3]), "y": float(p[4]),
                                 "ring": int(p[5])})
    assert len(geo["nodes"]) == 10, f"质点不是 10 个：{len(geo['nodes'])}"
    return geo


# ---------------------------------------------------------------------------
# 参数表：解析 TranePanel.h 的 kControls（不手抄）
# ---------------------------------------------------------------------------
CTL_RE = re.compile(
    r'^\s*\{"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*"([^"]*)",\s*'
    r'Fmt::(\w+),\s*(-?[\d.]+)f,\s*(-?[\d.]+)f,\s*(-?[\d.]+)f,\s*(-?[\d.]+)f\},')


def read_controls() -> list[dict]:
    txt = HEADER.read_text(encoding="utf-8")
    start = txt.index("inline constexpr ControlSpec kControls[] = {")
    end = txt.index("};", start)
    out = []
    for line in txt[start:end].splitlines():
        m = CTL_RE.match(line)
        if not m:
            continue
        out.append({"module": m.group(1), "id": m.group(2), "name": m.group(3),
                    "label": m.group(4), "unit": m.group(5), "fmt": m.group(6),
                    "lo": float(m.group(7)), "hi": float(m.group(8)),
                    "skew": float(m.group(9)), "def": float(m.group(10))})
    assert len(out) == 48, f"解析到 {len(out)} 条控件，期望 48"
    return out


def norm(c: dict) -> float:
    """复刻 TranePanel.cpp:664 toNormalised —— pow(p, skew)，不是 1/skew。"""
    span = c["hi"] - c["lo"]
    p = 0.0 if span <= 0 else min(1.0, max(0.0, (c["def"] - c["lo"]) / span))
    return p if c["skew"] == 1.0 else math.pow(p, c["skew"])


def short_value(c: dict) -> str:
    v = c["def"]
    f = c["fmt"]
    if f == "None":
        return ""
    if f == "Ms":
        return f"{v:.0f}ms"
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


# ---------------------------------------------------------------------------
# 布局：移植 TranePanel.cpp 的 bestRot / orient / segmentsFor
# ---------------------------------------------------------------------------
def orient(theta: float) -> tuple[bool, float]:
    po = math.atan2(math.cos(theta), -math.sin(theta))
    pin = math.atan2(-math.cos(theta), math.sin(theta))
    return (True, po) if abs(po) <= abs(pin) else (False, pin)


def best_rot(n: int) -> float:
    if n <= 1:
        return 0.0
    base = [-90.0 + (180.0 / n) * (2 * i + 1) for i in range(n)]
    best_tilt, best_dist, best, first = 0.0, 0.0, 0.0, True
    for j in range(1440):
        rot = 0.25 * j
        t = 0.0
        for b in base:
            t = max(t, abs(math.degrees(orient(math.radians(b + rot))[1])))
        tk = round(t * 10000.0) / 10000.0
        d = math.fmod(rot + 180.0, 360.0)
        if d < 0:
            d += 360.0
        d = abs(d - 180.0)
        if first or tk < best_tilt or (tk == best_tilt and d < best_dist):
            first, best_tilt, best_dist, best = False, tk, d, rot
    return best


def segments(n: int, ring_r: float, gap_px: float = 4.0, val_r: float = 38.5) -> list[dict]:
    """返回每段的 (a0, a1, mid)，屏幕角（0 = 3 点，+90° = 6 点）。"""
    if n <= 1:
        sp = math.radians(170.0)
        return [{"a0": -math.pi / 2 - sp, "a1": -math.pi / 2 + sp,
                 "mid": -math.pi / 2}]
    rot = best_rot(n)
    gap = gap_px / val_r
    seg = (2 * math.pi - n * gap) / n
    a = -math.pi / 2 + gap * 0.5 + math.radians(rot)
    out = []
    for _ in range(n):
        out.append({"a0": a, "a1": a + seg, "mid": a + seg * 0.5})
        a += seg + gap
    return out


# ---------------------------------------------------------------------------
# 背景纹理
# ---------------------------------------------------------------------------
def ascii_ink(geo: dict, level_alphas: list[int] | None, border_px: int | None,
              ink_alpha_scale: float = 1.0, grain: float = 0.0) -> "object":
    """把 asciify 的一帧按面板比例裁好，乘上可读区档位，返回 RGBA 数组。

    level_alphas = [0, 26, 76, 255] 时就是 v0.18 的真实做法。
    border_px 给了就只在离面板边 border_px 以内保留墨（V1 的"外框带"）。
    """
    import numpy as np
    from PIL import Image

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_bg_"))
    try:
        frame = tmp / "f.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(VIDEO),
             "-vf", "select=eq(n\\,20)", "-vframes", "1", str(frame)], check=True)
        src = Image.open(frame).convert("L")
        sw, sh = src.size
        W, H = geo["w"], geo["h"]
        want_w = round(sh * (W / H))
        if want_w <= sw:
            src = src.crop(((sw - want_w) // 2, 0, (sw - want_w) // 2 + want_w, sh))
        else:
            want_h = round(sw * (H / W))
            src = src.crop((0, (sh - want_h) // 2, sw, (sh - want_h) // 2 + want_h))
        src = src.resize((W, H), Image.LANCZOS)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    a = np.asarray(src).astype(np.float32)
    ink = np.clip((235.0 - a) / 235.0, 0.0, 1.0) >= 0.42     # 与 build_video_frames 同阈值

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xx += 0.5
    yy += 0.5

    alpha = np.zeros((H, W), np.float32)
    if level_alphas is not None:
        lv = np.full((H, W), 3, np.uint8)
        for n in geo["nodes"]:
            d = np.hypot(xx - n["x"], yy - n["y"])
            lv[d < geo["scale_r"] + 6.0] = 2
            lv[d < geo["ring_r"] - 1.0] = 1
        lut = np.array(level_alphas, np.float32)
        alpha = np.take(lut, lv)
        alpha[~ink] = 0.0
    elif border_px is not None:
        band = ((xx < border_px) | (xx > W - border_px)
                | (yy < border_px) | (yy > H - border_px))
        alpha = np.where(ink & band, 255.0, 0.0)

    alpha = alpha * ink_alpha_scale

    if grain > 0.0:
        rng = np.random.default_rng(20260928)     # 固定种子：可复现
        g = rng.normal(0.0, grain, (H, W))
        alpha = np.clip(alpha + g * 255.0 * (ink | (alpha > 0)), 0.0, 255.0)
        # 纸纤维：整幅极淡的颗粒，不依赖字符
        alpha = np.clip(alpha + rng.normal(0.0, grain * 0.55, (H, W)) * 255.0, 0.0, 255.0)

    rgb = np.zeros((H, W, 4), np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = INK
    rgb[..., 3] = alpha.round().astype(np.uint8)
    return Image.fromarray(rgb, "RGBA")


def data_uri(img) -> str:
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# 主题
# ---------------------------------------------------------------------------
def themes() -> dict:
    return {
        "V0": dict(
            key="V0", title="V0 · 现状（v0.18 复刻）",
            sub="满幅字符画 + 蒂芙尼蓝光晕",
            note="背景与信息层同为墨色、同处一个通道：整幅高频字符把圆、字、"
                 "辐条一起压进噪点里。光晕在白纸上不可能更亮，只能做成一圈"
                 "高饱和的色渍 —— 读起来像荧光笔，不像光。",
            sheet="#EDEDEA", panel_bg=None, tex="full",
            tree_a=f"rgba(14,14,15,.15)", tree_b=f"rgba(14,14,15,.30)",
            tree_wa=0.9, tree_wb=1.1,
            off_fill="rgba(14,14,15,.048)", off_stroke="rgba(14,14,15,.42)",
            off_w=1.7, bezel="rgba(14,14,15,.06)",
            scale_ring="rgba(14,14,15,.10)", scale_w=0.7,
            on_fill="rgba(10,186,181,.05)", on_halo="rgba(10,186,181,.20)",
            on_stroke=ACCENT, on_w=3.0, on_core=ACCENT_DEEP, on_core_w=1.1,
            spoke="rgba(14,14,15,.90)", spoke_w=1.9,
            mod_fill=INK_HEX, mod_fs=12.5, mod_ls=".005em", mod_w=700,
            name_fill="rgba(14,14,15,.46)", name_fs=7.0, name_ls=".06em", name_w=600,
            val_fill="rgba(14,14,15,.64)", val_fs=7.5, val_ls="-0.01em", val_w=500,
            grid=None,
        ),
        "V1": dict(
            key="V1", title="V1 · 纸·墨（推荐）",
            sub="字符退到外框带 · 纸面回归安静 · 光晕改「墨洇」",
            note="只动三件事：① 字符画收进 26px 外框带、降到 6% 墨，面板中部"
                 "回到干净的纸；② 亮着的圆不再上色渍，改成「墨色实边 + 一圈极淡"
                 "墨洇 + 内侧一道 0.9px 强调色」；③ 数值提到 8px/0.92、参数名压到 "
                 "6.5px/0.30 —— 层级靠对比度差，不靠加东西。几何一个像素没动。",
            sheet="#EDEDEA", panel_bg=None, tex="border",
            tree_a="rgba(14,14,15,.055)", tree_b="rgba(14,14,15,.13)",
            tree_wa=1.0, tree_wb=1.4,
            off_fill="none", off_stroke="rgba(14,14,15,.22)",
            off_w=1.2, bezel="rgba(14,14,15,.05)",
            scale_ring="rgba(14,14,15,.08)", scale_w=0.6,
            on_fill="rgba(10,186,181,.055)", on_halo="rgba(14,14,15,.07)",
            on_stroke="rgba(14,14,15,1)", on_w=1.4, on_core=ACCENT_DEEP, on_core_w=0.9,
            spoke="rgba(14,14,15,.95)", spoke_w=1.6,
            mod_fill=INK_HEX, mod_fs=14.0, mod_ls=".10em", mod_w=700,
            name_fill="rgba(14,14,15,.30)", name_fs=6.5, name_ls=".13em", name_w=600,
            val_fill="rgba(14,14,15,.92)", val_fs=8.0, val_ls="0em", val_w=500,
            grid=None,
        ),
        "V2": dict(
            key="V2", title="V2 · 深色硬件",
            sub="深灰面板 · 凹陷盘 · 单一琥珀强调",
            note="走 UAD / Softube 那条路：底色是 135° 的两级灰渐变（左上受光），"
                 "每个圆是一块「凹陷的盘」——外圈一道 1px 亮边（受光）、内圈一道 "
                 "1px 暗边（阴影）。零纹理。强调色只有一个琥珀，只出现在"
                 "「亮着的圆」和辐条端点上。代价：丢掉了纸白这个差异化特征。",
            sheet="#0A0B0C", panel_bg=None, tex="none",
            tree_a="rgba(255,255,255,.055)", tree_b="rgba(255,255,255,.13)",
            tree_wa=1.0, tree_wb=1.2,
            off_fill="rgba(255,255,255,.022)", off_stroke="rgba(255,255,255,.09)",
            off_w=1.2, bezel="rgba(0,0,0,.55)",
            scale_ring="rgba(255,255,255,.07)", scale_w=0.6,
            on_fill="rgba(227,160,60,.055)", on_halo="rgba(227,160,60,.14)",
            on_stroke="rgba(227,160,60,.90)", on_w=1.5,
            on_core="rgba(227,160,60,.55)", on_core_w=0.8,
            spoke="rgba(255,255,255,.55)", spoke_w=1.5,
            mod_fill="#F2F3F5", mod_fs=13.5, mod_ls=".09em", mod_w=700,
            name_fill="rgba(255,255,255,.34)", name_fs=6.5, name_ls=".13em", name_w=600,
            val_fill="#E8E9EB", val_fs=8.0, val_ls="0em", val_w=500,
            grid=None, accent="#E3A03C", dark=True,
        ),
        "V3": dict(
            key="V3", title="V3 · 工程图",
            sub="纸白 · 方格 · 全部等宽 · 工程红",
            note="走 Teenage Engineering / 制图那条路：把「测量」当主题。"
                 "背景换成 8px 细格 + 每 80px 加重一档的方格纸，圆不填充只描边，"
                 "树线用虚线表示「非主干」。强调色是工程红，只用在亮着的圆和数值上。"
                 "全部文字等宽 —— 数值对齐后整块面板像一张图纸。",
            sheet="#EFEFEC", panel_bg=None, tex="none",
            tree_a="rgba(14,14,15,.30)", tree_b="rgba(14,14,15,.62)",
            tree_wa=0.8, tree_wb=1.0,
            off_fill="none", off_stroke="rgba(14,14,15,.34)",
            off_w=1.0, bezel="none",
            scale_ring="rgba(14,14,15,.22)", scale_w=0.6,
            on_fill="none", on_halo="rgba(192,57,43,.10)",
            on_stroke="rgba(192,57,43,.95)", on_w=1.5,
            on_core="rgba(192,57,43,.45)", on_core_w=0.8,
            spoke="rgba(14,14,15,.80)", spoke_w=1.2,
            mod_fill=INK_HEX, mod_fs=13.0, mod_ls=".16em", mod_w=700,
            name_fill="rgba(14,14,15,.42)", name_fs=6.5, name_ls=".13em", name_w=500,
            val_fill="rgba(14,14,15,.95)", val_fs=8.0, val_ls="0em", val_w=500,
            grid="grid", mono=True, accent="#C0392B",
        ),
    }


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------
def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def arc_path(cx, cy, r, a0, a1, sweep_ccw):
    """屏幕角 a0→a1 的圆弧路径。sweep_ccw = 视觉逆时针（θ 递减）。"""
    if sweep_ccw:
        x0, y0 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        x1, y1 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        span = abs(a1 - a0)
    else:
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        span = abs(a1 - a0)
    large = 1 if span > math.pi else 0
    sweep = 0 if sweep_ccw else 1
    return (f"M {x0:.3f} {y0:.3f} A {r:.3f} {r:.3f} 0 {large} {sweep} "
            f"{x1:.3f} {y1:.3f}")


def circle_path(cx, cy, r):
    """整圆子路径 —— 两条子路径 + fill-rule=evenodd 就是一个环带。"""
    return (f"M {cx - r:.3f} {cy:.3f} a {r:.3f} {r:.3f} 0 1 0 {2 * r:.3f} 0 "
            f"a {r:.3f} {r:.3f} 0 1 0 {-2 * r:.3f} 0 ")


def panel_svg(th: dict, geo: dict, ctrls: list[dict], tex_uri: str | None) -> str:
    W, H = geo["w"], geo["h"]
    R, SR = geo["ring_r"], geo["scale_r"]
    fam = "ui-monospace, SFMono-Regular, Menlo, monospace" if th.get("mono") else \
          "'Helvetica Neue', Helvetica, Arial, sans-serif"
    p: list[str] = []
    defs: list[str] = []

    # ---- 背景 ----
    if th["key"] == "V2":
        defs.append(
            '<linearGradient id="v2bg" x1="0" y1="0" x2="0.55" y2="1">'
            '<stop offset="0" stop-color="#16181C"/>'
            '<stop offset="0.55" stop-color="#101114"/>'
            '<stop offset="1" stop-color="#0A0B0D"/></linearGradient>'
            '<radialGradient id="v2top" cx="0.5" cy="-0.12" r="0.85">'
            '<stop offset="0" stop-color="rgba(255,255,255,.075)"/>'
            '<stop offset="1" stop-color="rgba(255,255,255,0)"/></radialGradient>')
        p.append(f'<rect width="{W}" height="{H}" fill="url(#v2bg)"/>')
        p.append(f'<rect width="{W}" height="{H}" fill="url(#v2top)"/>')
    elif th.get("grid"):
        defs.append(
            '<pattern id="g8" width="8" height="8" patternUnits="userSpaceOnUse">'
            '<path d="M8 0H0V8" fill="none" stroke="rgba(14,14,15,.030)" stroke-width="1"/></pattern>'
            '<pattern id="g80" width="80" height="80" patternUnits="userSpaceOnUse">'
            '<path d="M80 0H0V80" fill="none" stroke="rgba(14,14,15,.062)" stroke-width="1"/></pattern>')
        p.append(f'<rect width="{W}" height="{H}" fill="{PAPER_HEX}"/>')
        p.append(f'<rect width="{W}" height="{H}" fill="url(#g8)"/>')
        p.append(f'<rect width="{W}" height="{H}" fill="url(#g80)"/>')
    else:
        p.append(f'<rect width="{W}" height="{H}" fill="{PAPER_HEX}"/>')
        if tex_uri:
            p.append(f'<image href="{tex_uri}" x="0" y="0" width="{W}" height="{H}"/>')

    # ---- 树线 ----
    for a, b in PATHS:
        na, nb = geo["nodes"][a], geo["nodes"][b]
        dx, dy = nb["x"] - na["x"], nb["y"] - na["y"]
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln
        trim = R + 1.0
        x0, y0 = na["x"] + ux * trim, na["y"] + uy * trim
        x1, y1 = nb["x"] - ux * trim, nb["y"] - uy * trim
        trunk = (a, b) in TRUNK
        col = th["tree_b"] if trunk else th["tree_a"]
        w = th["tree_wb"] if trunk else th["tree_wa"]
        dash = ' stroke-dasharray="3 3"' if th.get("grid") and not trunk else ""
        p.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                 f'stroke="{col}" stroke-width="{w}"{dash}/>')

    # ---- 圆 + 辐条 + 环形文字 ----
    for i, n in enumerate(geo["nodes"]):
        cx, cy = n["x"], n["y"]
        on = n["module"] in LIT
        disc = f'<circle cx="{cx}" cy="{cy}" r="{R}"/>'

        if on:
            if th["on_halo"] != "none":
                ro = R + 13.0
                # 环带：中心透明 → 圆边界处最深 → 外缘透明（和 C++ 的三档径向渐变一致）
                defs.append(
                    f'<radialGradient id="halo{i}" gradientUnits="userSpaceOnUse" '
                    f'cx="{cx}" cy="{cy}" r="{ro:.2f}">'
                    f'<stop offset="0" stop-color="{th["on_halo"]}" stop-opacity="0"/>'
                    f'<stop offset="{R / ro:.4f}" stop-color="{th["on_halo"]}"/>'
                    f'<stop offset="1" stop-color="{th["on_halo"]}" stop-opacity="0"/>'
                    f'</radialGradient>')
                p.append(f'<path d="{circle_path(cx, cy, ro)}{circle_path(cx, cy, R)}" '
                         f'fill-rule="evenodd" fill="url(#halo{i})"/>')
            if th["on_fill"] != "none":
                p.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="{th["on_fill"]}"/>')
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" '
                     f'stroke="{th["on_stroke"]}" stroke-width="{th["on_w"]}"/>')
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{R - 4.2}" fill="none" '
                     f'stroke="{th["on_core"]}" stroke-width="{th["on_core_w"]}"/>')
        else:
            if th["off_fill"] != "none":
                p.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="{th["off_fill"]}"/>')
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" '
                     f'stroke="{th["off_stroke"]}" stroke-width="{th["off_w"]}"/>')

        if th["bezel"] != "none":
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{R - 1.6}" fill="none" '
                     f'stroke="{th["bezel"]}" stroke-width="0.6"/>')

        # 标尺圆
        dash = ' stroke-dasharray="2 4"' if th.get("grid") else ""
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{SR}" fill="none" '
                 f'stroke="{th["scale_ring"]}" stroke-width="{th["scale_w"]}"{dash}/>')

        # 辐条
        segs = segments(n["ring"], R)
        acc = th.get("accent", ACCENT_DEEP)
        slots = [c for c in ctrls if c["module"] == n["module"] and c["label"]]
        assert len(slots) == n["ring"] == len(segs), \
            f"{n['module']}: 表 {len(slots)} / dump {n['ring']} / 段 {len(segs)} 对不上"
        for s, c in enumerate(slots):
            v = norm(c)
            a = segs[s]["mid"]
            ux, uy = math.cos(a), math.sin(a)
            r0 = R + 3.0
            r1 = r0 + 2.0 + 15.0 * v
            x0, y0 = cx + ux * r0, cy + uy * r0
            x1, y1 = cx + ux * r1, cy + uy * r1
            p.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" '
                     f'stroke="{th["spoke"]}" stroke-width="{th["spoke_w"]}" '
                     f'stroke-linecap="round"/>')
            if v > 0.02:
                dot = acc if on else th["spoke"]
                p.append(f'<circle cx="{x1:.2f}" cy="{y1:.2f}" r="1.3" fill="{dot}"/>')

        # 环形文字：outward = 视觉逆时针、基线在半径 r；inward = 顺时针、基线在 r+0.5h
        for s, c in enumerate(slots):
            mid = segs[s]["mid"]
            out, _ = orient(mid)
            for text, r_base, fs, col, wt, ls in (
                    (c["label"].upper(), 49.0, th["name_fs"], th["name_fill"], th["name_w"], th["name_ls"]),
                    (short_value(c), 38.5, th["val_fs"], th["val_fill"], th["val_w"], th["val_ls"])):
                if not text:
                    continue
                r_use = r_base if out else r_base + 0.5 * fs
                pid = f"a{i}_{s}_{'n' if text == c['label'].upper() else 'v'}"
                defs.append(f'<path id="{pid}" fill="none" '
                            f'd="{arc_path(cx, cy, r_use, segs[s]["a0"], segs[s]["a1"], out)}"/>')
                p.append(f'<text font-family="{fam}" font-size="{fs}" font-weight="{wt}" '
                         f'letter-spacing="{ls}" fill="{col}">'
                         f'<textPath href="#{pid}" startOffset="50%" '
                         f'text-anchor="middle">{esc(text)}</textPath></text>')

        # 模块名
        p.append(f'<text x="{cx}" y="{cy + th["mod_fs"] * 0.35:.2f}" text-anchor="middle" '
                 f'font-family="{fam}" font-size="{th["mod_fs"]}" font-weight="{th["mod_w"]}" '
                 f'letter-spacing="{th["mod_ls"]}" fill="{th["mod_fill"]}">{n["module"].upper()}</text>')

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}"><defs>{"".join(defs)}</defs>{"".join(p)}</svg>')


# ---------------------------------------------------------------------------
MARGIN, COLGAP, PAD_TOP, CAPROW, ROWGAP, GRID_TOP = 48, 48, 72, 62, 12, 34
# 面板在页面里的 y（逻辑像素）：body 上边距 + .grid 的 margin-top + 标题行 + 行间距
PANEL_TOP = PAD_TOP + GRID_TOP + CAPROW + ROWGAP          # 180


def build_html(ths: list[dict], geo: dict, ctrls: list[dict],
               uris: dict, metrics: dict | None = None) -> str:
    W, H = geo["w"], geo["h"]
    n = len(ths)
    caps = "".join(f'<div class="cap"><b>{esc(t["title"])}</b>'
                   f'<span>{esc(t["sub"])}</span></div>' for t in ths)
    panels = "".join(f'<div class="panel">'
                     f'{panel_svg(t, geo, ctrls, uris.get(t["key"]))}</div>' for t in ths)
    notes = "".join(f'<p class="note">{esc(t["note"])}</p>' for t in ths)
    mets = "".join(f'<div class="met">{metrics[t["key"]]}</div>' for t in ths) if metrics else ""
    total_w = MARGIN * 2 + W * n + COLGAP * (n - 1)
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Träne 面板 · 背景与材质方向对照 v0.19</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#EDEDEA;font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;
     width:{total_w}px;padding:{PAD_TOP}px {MARGIN}px 40px;color:#0E0E0F}}
h1{{font-size:19px;font-weight:700;letter-spacing:.02em}}
h1 small{{display:block;font-size:12px;font-weight:400;letter-spacing:.05em;
          color:rgba(14,14,15,.5);margin-top:7px;line-height:1.75}}
.grid{{display:grid;grid-template-columns:repeat({n},{W}px);column-gap:{COLGAP}px;
      row-gap:{ROWGAP}px;margin-top:{GRID_TOP}px;align-items:start}}
.cap{{height:{CAPROW}px;padding-bottom:9px;border-bottom:1px solid rgba(14,14,15,.22)}}
.cap b{{display:block;font-size:13.5px;font-weight:700;letter-spacing:.01em}}
.cap span{{display:block;font-size:11px;color:rgba(14,14,15,.52);margin-top:4px}}
.panel{{width:{W}px;height:{H}px;overflow:hidden;background:{PAPER_HEX};
       box-shadow:0 0 0 .5px rgba(14,14,15,.14),0 18px 48px rgba(14,14,15,.12)}}
.panel svg{{display:block}}
.note{{font-size:11px;line-height:1.85;color:rgba(14,14,15,.58);text-align:justify}}
.met{{font-size:10.5px;line-height:1.95;color:rgba(14,14,15,.62);
     font-variant-numeric:tabular-nums;border-top:1px solid rgba(14,14,15,.16);
     padding-top:9px;margin-top:2px}}
.met b{{color:#0E0E0F;font-weight:600}}
</style></head><body>
<h1>Träne · 面板背景与材质方向对照
<small>v0.19 · 四个方案共用同一套真实几何与参数值 —— 圆心 / 半径 / 环位来自
panel_probe --dump-geometry，辐条长度与环形文字位置由 TranePanel.h 的参数表算出
（pow(p, skew)，与 C++ 同式）。唯一变量是「背景 + 材质 + 字阶」。</small></h1>
<div class="grid">{caps}{panels}{notes}{mets}</div>
</body></html>'''


def panel_origin(im, geo: dict, scale: int) -> tuple[float, float]:
    """从渲染图上量出第一块面板的左上角（逻辑像素）。

    **别手算 CSS 高度** —— h1 换不换行、字体度量怎么算，都会让手算的 y 差几十像素，
    而裁图是按 y 来的，差一点就裁到隔壁去了。直接在像素上找。

    找法是「整行都变成非纸色」：标题行只有零星文字（占比 ~5%），
    面板行整行都是纸色（占比 ~100%），两者不会混。
    """
    import numpy as np
    a = np.asarray(im).astype(int)
    sheet = np.array([0xED, 0xED, 0xEA])
    x0d, x1d = int(MARGIN * scale), int((MARGIN + geo["w"]) * scale)
    band = a[:, x0d:x1d, :]
    frac = (np.abs(band - sheet).sum(2) > 25).mean(1)
    ys = np.nonzero(frac > 0.90)[0]
    assert len(ys), "找不到面板行 —— 页面是不是没渲染出来"
    y0 = int(ys[0])

    y = y0 + int(40 * scale)
    # 用「像纸」而不是「不像背景」来找左缘 —— 面板外面那圈 48px 的投影
    # 也不像背景，按后者找会往前多认 3–4px。
    paper = np.array([0xFA, 0xFA, 0xF9])
    row = (np.abs(a[y, :, :] - paper).sum(1) < 25).astype(int)
    run = np.convolve(row, np.ones(200 * scale, int), "valid")
    xs = np.nonzero(run == 200 * scale)[0]
    assert len(xs), "找不到面板左缘"
    return xs[0] / scale, y0 / scale


def measure(im, ths: list[dict], geo: dict, scale: int,
            ox: float, oy: float) -> dict:
    """从渲染出来的像素上量两件事：面板亮度 σ（背景安静度）与强调色占比。"""
    import numpy as np
    W, H = geo["w"], geo["h"]
    out = {}
    for i, th in enumerate(ths):
        x0 = int((ox + i * (W + COLGAP)) * scale)
        y0 = int(oy * scale)
        a = np.asarray(im.crop((x0, y0, x0 + W * scale, y0 + H * scale)),
                       dtype=np.float32)
        luma = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        if th.get("dark"):
            acc = (r > b + 40) & (g > b + 15) & (r > 120)
        elif th["key"] == "V3":
            acc = (r > g + 45) & (r > b + 45) & (r > 110)
        else:
            acc = (g > r + 30) & (b > r + 25) & (g > 110)
        out[th["key"]] = (float(luma.std()), float(acc.mean() * 100.0))
    return out


def metrics_html(ths: list[dict], m: dict) -> dict:
    s = {}
    for t in ths:
        sd, acc = m[t["key"]]
        s[t["key"]] = (f'面板亮度 σ <b>{sd:.1f}</b> · 强调色 <b>{acc:.2f}%</b><br>'
                       f'σ 越低 = 背景越安静；强调色越少 = 越不像荧光笔')
    return s


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).is_file():
            return c
    sys.exit("找不到 Chrome/Chromium —— 需要它把 HTML 截成 PNG")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT.parent / "outputs"))
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--version", default="0.19")
    args = ap.parse_args()

    geo = read_geometry()
    ctrls = read_controls()
    print(f"几何：面板 {geo['w']}×{geo['h']}  圆半径 {geo['ring_r']}  标尺 {geo['scale_r']}")
    print(f"参数表：{len(ctrls)} 条（含 {sum(1 for c in ctrls if not c['label'])} 个模块开关）")

    ths = themes()
    order = ("V0", "V1", "V2", "V3")
    ths_list = [ths[k] for k in order]

    uris = {}
    for key, spec in (("V0", dict(level_alphas=[0, 26, 76, 255])),
                      ("V1", dict(border_px=26, ink_alpha_scale=0.24, grain=0.012))):
        img = ascii_ink(geo, spec.get("level_alphas"), spec.get("border_px"),
                        spec.get("ink_alpha_scale", 1.0), spec.get("grain", 0.0))
        uris[key] = data_uri(img)
        print(f"{key} 背景纹理已生成")

    W, H = geo["w"], geo["h"]
    total_w = MARGIN * 2 + W * 4 + COLGAP * 3
    chrome = find_chrome()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="trane_bgstudy_"))
    page, png = tmp / "study.html", tmp / "study.png"

    def render(html: str):
        page.write_text(html, encoding="utf-8")
        # **必须是纯 --headless，不能用 --headless=new** —— 后者在这台 macOS 上
        # 不是报错，是**挂住不返回**（最小用例也挂满 180s 超时）。
        subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox",
                        "--hide-scrollbars",
                        f"--force-device-scale-factor={args.scale}",
                        f"--screenshot={png}", f"--window-size={total_w},1400",
                        "--virtual-time-budget=8000", page.as_uri()],
                       capture_output=True, text=True, timeout=180)
        assert png.is_file(), "Chrome 没截出图"
        return Image.open(png).convert("RGB")

    from PIL import Image
    im = render(build_html(ths_list, geo, ctrls, uris))          # 第一遍：量
    ox, oy = panel_origin(im, geo, args.scale)
    print(f"面板原点（从像素上量的，不是手算 CSS）：x={ox:.1f} y={oy:.1f}")
    m = measure(im, ths_list, geo, args.scale, ox, oy)
    for k in order:
        print(f"  {k}  面板亮度 σ {m[k][0]:5.1f}   强调色 {m[k][1]:5.2f}%")
    im = render(build_html(ths_list, geo, ctrls, uris,
                           metrics_html(ths_list, m)))            # 第二遍：带数

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    dest = outdir / f"Trane_UI_bg_study_v{args.version}.png"
    im.save(dest)
    print(f"→ {dest}  {im.size[0]}×{im.size[1]}")

    # 细节：四个方案的 SPACE 圆（亮着）周围各裁一块 2×
    sp = geo["nodes"][8]
    bx0, by0, bw, bh, pad = sp["x"] - 122, sp["y"] - 150, 244, 300, 24
    s = args.scale
    strip = Image.new("RGB", ((bw * 4 + pad * 3) * s, (bh + 30) * s), (0xED, 0xED, 0xEA))
    for i in range(4):
        px = int((ox + i * (W + COLGAP) + bx0) * s)
        py = int((oy + by0) * s)
        strip.paste(im.crop((px, py, px + bw * s, py + bh * s)), ((bw + pad) * i * s, 15 * s))
    dest2 = outdir / f"Trane_UI_bg_study_v{args.version}_detail.png"
    strip.save(dest2)
    print(f"→ {dest2}  {strip.size[0]}×{strip.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
