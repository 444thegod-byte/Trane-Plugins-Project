#!/usr/bin/env python3
"""把一张美术图烤成 Träne 面板能直接贴的背景素材。

为什么要有这一步（而不是让插件运行时解一张大图）：

  1. **运行时不引入任何外部状态。** 素材必须是构建期烤好的成品 ——
     插件只做一次 1:1 直贴，不做任何逐像素处理（面板层的第一原则）。
  2. **必须压暗。** 背景是"纸"，参数是"字"。素材不压暗就会和检查器的
     文字、分割线、分段控件抢注意力。压暗的目标是**世界树骨架点线那一档**
     （实测 p99 = 22/255）—— 两者都是"存在但不抢戏"的层次。
  3. **必须量化。** 素材存成 **2-bit 档位 + 一张调色板**（levelCount ≤ 4）。
     256 级灰度的 3000×3000 图 PNG 有几百 KB，2-bit 只有零头，而肉眼看不出差别。

关键的顺序问题（踩过一次就会记住）：**先缩放，再量化**。
源图如果是接近 1-bit 的黑白纹样（本项目这张就是：76.4% 纯黑 / 21.7% 纯白 /
只有 1.8% 中间调），先量化再缩放的话，缩放插值出来的灰会全部落进最低档，
纹样直接消失。反过来先 LANCZOS 缩到目标尺寸、拿到连续的灰度，再量化，
细线在缩放里被"稀释"成中灰，正好落在中间两档上 —— 这才是想要的效果。

落位（放哪儿、多大）**不在这里算**：从 `panel_probe --dump-geometry` 的
`pane` 行读参数区区间，和探针用同一对数。工具里绝不手抄第二份。

用法：
    bake_backdrop.py --src 图.png --outdir 输出目录
                     [--peak 22] [--thresh 64,128,192] [--levels 4]
                     [--scale 2] [--name backdrop] [--quiet]

产出：
    <outdir>/<name>.png    烤好的素材（物理分辨率、不透明、灰度）
    <outdir>/<name>.json   落位与调色板自述（供探针 --bg-rect 与测试核对）
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
VST = HERE.parent
PROBE = VST / "build" / "panel_probe_artefacts" / "Release" / "panel_probe"


# ---------------------------------------------------------------------------
# 几何：只从编译产物读
# ---------------------------------------------------------------------------
def read_geometry() -> dict:
    assert PROBE.is_file(), f"找不到 {PROBE}（先构建 panel_probe）"
    r = subprocess.run([str(PROBE), "--dump-geometry"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    geo: dict = {}
    for line in r.stdout.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "panel":
            geo["w"], geo["h"] = int(p[1]), int(p[2])
        elif p[0] == "pane":
            geo["pane_x0"], geo["pane_w"] = float(p[1]), float(p[2])
    for k in ("w", "h", "pane_x0", "pane_w"):
        assert k in geo, f"geometryDump 缺少 {k}（pane 行是背景落位的唯一依据）"
    return geo


def placement(geo: dict, img_w: int, img_h: int, fit: str = "height") -> dict:
    """算出素材的**逻辑坐标**矩形。

    fit = "height"（默认）  高度铺满面板高，宽度按比例，在参数区里水平居中。
                            代价：参数区左右各留一条黑边（正方形素材 ≈ 135px）。
    fit = "pane"            宽度铺满参数区，高度按比例，**上下裁切**（y 可能为负）。
                            代价：图案上下被切掉一截。
    """
    x0, pw, ph = geo["pane_x0"], geo["pane_w"], float(geo["h"])
    ar = img_w / img_h
    if fit == "pane":
        w = float(pw)
        h = w / ar
        return {"x": float(x0), "y": (ph - h) * 0.5, "w": w, "h": h}
    h = ph
    w = h * ar
    return {"x": x0 + (pw - w) * 0.5, "y": 0.0, "w": w, "h": h}


# ---------------------------------------------------------------------------
# 烘焙
# ---------------------------------------------------------------------------
def flatten(src: pathlib.Path) -> np.ndarray:
    """读图 → RGBA → 展平到黑底 → 返回 0..255 的灰度 float。"""
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(np.float32)
    rgb = a[..., :3].mean(axis=2)
    alpha = a[..., 3] / 255.0
    return rgb * alpha          # 黑底合成：out = fg·α + 0·(1-α)


def resample(gray: np.ndarray, w: int, h: int) -> np.ndarray:
    im = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), mode="L")
    im = im.resize((w, h), Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def palette(levels: int, peak: int) -> list[int]:
    """线性爬升的调色板：levels=4 / peak=22 → [0, 7, 15, 22]。"""
    return [int(round(peak * i / (levels - 1))) for i in range(levels)]


def feather(gray: np.ndarray, fx: float, fy: float, scale: float) -> np.ndarray:
    """左右 / 上下边缘各羽化 fx / fy 个**逻辑**像素，乘一条线性斜坡。

    为什么必须羽化：这张纹样横向很均匀（实测每 60 逻辑 px 的亮档占比
    16.7% … 27.0%，**连最边上那 6px 也有 10.6%**）。不羽化的话，图案
    会在 x=557 和 x=1277 两条竖线上**突然开始、突然结束** ——
    那正是小绪明说不要的「卡片 / 边框感」。乘到 0 就等于融进面板底。
    """
    if fx <= 0 and fy <= 0:
        return gray
    h, w = gray.shape
    ramp = np.ones(w, dtype=np.float32)
    if fx > 0:
        n = int(round(fx * scale))
        n = max(1, min(n, w // 2))
        r = np.linspace(0.0, 1.0, n, dtype=np.float32)
        ramp[:n] = r
        ramp[-n:] = r[::-1]
    col = np.ones(h, dtype=np.float32)
    if fy > 0:
        n = int(round(fy * scale))
        n = max(1, min(n, h // 2))
        r = np.linspace(0.0, 1.0, n, dtype=np.float32)
        col[:n] = r
        col[-n:] = r[::-1]
    return gray * col[:, None] * ramp[None, :]


def quantise(gray: np.ndarray, thresh: list[int], pal: list[int]):
    idx = np.digitize(gray, thresh, right=False)      # 0 .. len(thresh)
    idx = np.clip(idx, 0, len(pal) - 1)
    return idx.astype(np.uint8), np.asarray(pal, dtype=np.uint8)[idx]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--peak", type=int, default=22,
                    help="最亮那一档的灰度（0..255）。默认 22 = 世界树骨架点线的实测 p99")
    ap.add_argument("--thresh", default="64,128,192",
                    help="量化阈值（升序，个数 = levels-1）。默认等分 255")
    ap.add_argument("--levels", type=int, default=4)
    ap.add_argument("--scale", type=float, default=2.0,
                    help="物理像素 / 逻辑像素。默认 2 = 面板 @2x 缓存分辨率")
    ap.add_argument("--name", default="backdrop")
    ap.add_argument("--fit", choices=("height", "pane"), default="height")
    ap.add_argument("--fade-x", type=float, default=48.0,
                    help="左右边缘各羽化多少个逻辑像素（0 = 硬边）")
    ap.add_argument("--fade-y", type=float, default=0.0,
                    help="上下边缘各羽化多少个逻辑像素")
    ap.add_argument("--quiet", action="store_true")
    o = ap.parse_args()

    thresh = [int(x) for x in o.thresh.split(",")]
    assert len(thresh) == o.levels - 1, \
        f"阈值要给 {o.levels - 1} 个，收到 {len(thresh)} 个"
    assert thresh == sorted(thresh), "阈值必须升序"
    assert 1 <= o.levels <= 4, "档位 1..4（2-bit 索引的硬上限）"

    src = pathlib.Path(o.src).expanduser()
    assert src.is_file(), f"找不到源图 {src}"
    outdir = pathlib.Path(o.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    geo = read_geometry()
    place = placement(geo, *Image.open(src).size, fit=o.fit)

    # 目标：逻辑尺寸 × scale → 物理像素
    tw = int(round(place["w"] * o.scale))
    th = int(round(place["h"] * o.scale))

    # 顺序是硬规矩：**先缩放 → 再羽化 → 最后量化**。
    # 先量化再缩放会把插值出来的灰全压进最低档（1-bit 源图直接消失）；
    # 先量化再羽化则是把 4 个档位当成连续量去乘，档位之间会长出新的灰。
    gray = flatten(src)
    small = resample(gray, tw, th)
    small = feather(small, o.fade_x, o.fade_y, o.scale)
    idx, out = quantise(small, thresh, palette(o.levels, o.peak))

    dest = outdir / f"{o.name}.png"
    Image.fromarray(out, mode="L").convert("RGBA").save(dest)

    counts = [int((idx == i).sum()) for i in range(o.levels)]
    tot = idx.size
    side = {
        "source": str(src),
        "source_size": list(Image.open(src).size),
        "asset": dest.name,
        "asset_size": [tw, th],
        "scale": o.scale,
        "placement": {k: round(v, 3) for k, v in place.items()},
        "fit": o.fit,
        "fade_x": o.fade_x,
        "fade_y": o.fade_y,
        "levels": o.levels,
        "palette": palette(o.levels, o.peak),
        "thresholds": thresh,
        "level_share": [round(c / tot, 5) for c in counts],
        "geometry": {k: round(float(v), 3) if isinstance(v, float) else v
                     for k, v in geo.items()},
    }
    (outdir / f"{o.name}.json").write_text(
        json.dumps(side, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not o.quiet:
        print(f"源图    {src.name}  {side['source_size'][0]}x{side['source_size'][1]}")
        print(f"素材    {dest}  {tw}x{th}  （逻辑 {place['w']:.1f}x{place['h']:.1f} @ {o.scale}x）")
        print(f"落位    x {place['x']:.1f} .. {place['x'] + place['w']:.1f}   "
              f"y 0 .. {place['h']:.1f}   "
              f"（参数区 {geo['pane_x0']:.0f}..{geo['pane_x0'] + geo['pane_w']:.0f}）")
        print(f"调色板  {palette(o.levels, o.peak)}   阈值 {thresh}")
        for i, c in enumerate(counts):
            print(f"  档 {i}  = {palette(o.levels, o.peak)[i]:3d}/255   "
                  f"{c:9d} px  {100.0 * c / tot:7.3f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
