#!/usr/bin/env python3
"""把用户给的金属 logo 抠成**透明底**的素材，供面板顶栏使用。

    python3 tools/make_logo_asset.py                  # 生成 assets/logo/trane_logo.bin
    python3 tools/make_logo_asset.py --check          # 校验磁盘上的 .bin 与重建结果一致
    python3 tools/make_logo_asset.py --preview p.png  # 另外导一张 PNG 供人看

--------------------------------------------------------------------------
为什么落盘的是**自制容器**（`TRNL`）而不是 PNG
--------------------------------------------------------------------------
和背景动画素材（`assets/video/backdrop.bin`）同一条理由：**面板层不许出现
`ImageFileFormat` / `loadFrom`** —— `tests/test_editor_layout.py` 的
`test_panel_layer_never_touches_the_filesystem` 盯着这一条，它是"面板层的输入
完整地只有一个 PanelState"那条架构约束的护栏。

为了一张静态图去把那条护栏改松是不划算的：烤成裸像素之后运行时只是一次
memcpy，比 PNG 解码还快，护栏一个字都不用动。

容器格式（小端）：

    偏移 0   4 字节   magic  "TRNL"
    偏移 4   u32      版本号，当前 1
    偏移 8   u32      宽
    偏移 12  u32      高
    偏移 16  w*h*4     像素，逐行，**BGRA** 字节序

**BGRA 不是 RGBA** —— 这是 JUCE `PixelARGB` 在小端机上的内存布局，直接 memcpy
进 `juce::Image` 就是这个顺序。转换放在这里做一次，运行时不做逐像素循环。
（本工程只出 arm64 / x86_64 两种小端目标，见 CMakeLists 里的通用二进制说明。）

--------------------------------------------------------------------------
为什么要"按亮度映射 alpha"，而不是"从四边洪水填充"
--------------------------------------------------------------------------
洪水填充只能吃掉**从边界连通得到**的背景。这个 logo 有两块封闭白区：

  · 中心圆环**内部**（环 + 十字线围出来的四块扇形）
  · 左下熔滴**内部**

它们从四边都走不到，洪水填充会原样留下 —— 合到黑底上就是一圈白盘。
（v1 实测："不透明但接近纯白"的像素占 5.0%，可视化后正是这两块。）

改用亮度映射后，判据从"连不连通"变成"这个像素白不白"，封闭与否无关。
实测同一指标降到 0.00%。

--------------------------------------------------------------------------
为什么按 min(R,G,B) 而不是灰度
--------------------------------------------------------------------------
背景是**纯白**（四角 20×20 均值 = 255,255,255；min>=252 的像素占 84.78%），
而金属是**冷灰**（有轻微偏色）。用 min 通道判"白"最保守：只要有一个通道
没到白，就说明这里不是背景，宁可多留。

--------------------------------------------------------------------------
为什么还要做一次色调提升（gamma 0.70）
--------------------------------------------------------------------------
面板顶栏那块底色是**纯黑 (0,0,0)**（实测 v0.35 渲染的 (30,30)/(95,20) 都是黑）。
原图金属在纯黑上的实测平均亮度只有 81.2 —— 熔滴那一片基本糊掉。
用户同一轮的要求里就有"所有文字亮度调高"，所以这里做一次**保细节的**提升：
按 gamma 曲线（而不是简单乘系数），暗部抬得多、亮部抬得少，高光不爆。

  id   平均亮度  81.2   90 分位 124.5
  gm70 平均亮度 112.7   90 分位 154.3   ← 采用

--------------------------------------------------------------------------
许可 / 来源
--------------------------------------------------------------------------
源图是**用户自己的品牌素材**（用户 2026-09-30 上传），不是第三方素材。
源文件随仓库提交在 assets/logo/source/ 下，sha256 记在 PROVENANCE.md 里。
"""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "logo" / "source" / "trane_logo_source.jpg"
OUT = ROOT / "assets" / "logo" / "trane_logo.bin"

MAGIC = b"TRNL"
VERSION = 1
HEADER = 16

# 落盘尺寸：只存**高**，宽按源图宽高比算。
#
# 面板上画 96 逻辑 px（2× 屏 = 192 设备 px），这里留 2 倍余量到 384 ——
# 再高只是让 4 MB 的裸像素白占二进制，肉眼看不出差别。
# 384 恰好是 192 的整数倍，2:1 降采样是最干净的一档。
OUT_H = 384

# ---- 抠图参数（都来自实测，见模块 docstring）----------------------------
T_WHITE = 248.0   # min(R,G,B) >= 这里 → 完全是背景，alpha = 0
T_SOLID = 214.0   # min(R,G,B) <= 这里 → 完全是金属，alpha = 1
BLUR = 0.6        # alpha 边缘的一次轻高斯，纯为反锯齿
GAMMA = 0.70      # 色调提升（见上）


def build(src_path: Path = SRC) -> tuple[np.ndarray, dict]:
    """返回 (RGBA uint8 数组 (h,w,4), 量化自检字典)。"""
    im = Image.open(src_path).convert("RGB")
    rgb = np.asarray(im).astype(np.float32)
    mn = rgb.min(axis=2)

    alpha = np.clip((T_WHITE - mn) / (T_WHITE - T_SOLID), 0.0, 1.0)

    # 反锯齿：alpha 上做一次极轻的高斯（不碰 RGB，避免把背景色抹进边缘）
    ai = Image.fromarray((alpha * 255.0 + 0.5).astype(np.uint8), "L")
    alpha = np.asarray(ai.filter(ImageFilter.GaussianBlur(BLUR))).astype(np.float32) / 255.0

    # 色调提升：gamma 曲线，逐通道
    lit = 255.0 * np.power(rgb / 255.0, GAMMA)

    # 裁到内容包围盒（alpha 有意义的范围），免得顶栏里留一圈看不见的空白
    ys, xs = np.where(alpha > 0.02)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1

    out = np.dstack([lit[y0:y1, x0:x1], alpha[y0:y1, x0:x1] * 255.0 + 0.5]).astype(np.uint8)

    # 缩到落盘尺寸。用 LANCZOS（预乘之后再缩，避免透明边的黑边晕）。
    full = Image.fromarray(out, "RGBA")
    w = max(1, int(round(OUT_H * full.width / full.height)))
    img = full.resize((w, OUT_H), Image.LANCZOS)
    out = np.asarray(img).astype(np.uint8)

    # ---- 量化自检 ---------------------------------------------------------
    al = out[:, :, 3].astype(np.float32)
    solid = al > 230
    lum = (0.2126 * out[:, :, 0] + 0.7152 * out[:, :, 1] + 0.0722 * out[:, :, 2])[solid]
    stats = {
        "size": img.size,
        "alpha_zero_pct": 100.0 * float((al == 0).mean()),
        "alpha_mid_pct": 100.0 * float(((al > 0) & (al < 255)).mean()),
        "alpha_full_pct": 100.0 * float((al == 255).mean()),
        # 上一版（洪水填充）这里是 5.0% —— 就是那两块白盘
        "opaque_near_white_pct": 100.0 * float(((al > 200) & (out[:, :, :3].min(axis=2) >= 232)).mean()),
        "solid_mean_lum": float(lum.mean()),
        "solid_p90_lum": float(np.percentile(lum, 90)),
    }
    return out, stats


def pack(rgba: np.ndarray) -> bytes:
    """RGBA (h,w,4) → TRNL 容器（像素存 BGRA）。"""
    h, w = rgba.shape[0], rgba.shape[1]
    bgra = rgba[:, :, [2, 1, 0, 3]]          # RGB → BGR，alpha 不动
    return MAGIC + struct.pack("<III", VERSION, w, h) + bgra.tobytes()


def unpack(blob: bytes) -> np.ndarray | None:
    if len(blob) < HEADER or blob[:4] != MAGIC:
        return None
    ver, w, h = struct.unpack("<III", blob[4:16])
    if ver != VERSION or w <= 0 or h <= 0 or len(blob) != HEADER + 4 * w * h:
        return None
    bgra = np.frombuffer(blob, np.uint8, count=4 * w * h, offset=HEADER).reshape(h, w, 4)
    return bgra[:, :, [2, 1, 0, 3]]          # BGRA → RGBA



def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    ap.add_argument("--preview", metavar="PATH", help="另外导一张 PNG 供人看")
    args = ap.parse_args()

    if not SRC.exists():
        print(f"找不到源图：{SRC}", file=sys.stderr)
        return 1

    rgba, st = build()
    blob = pack(rgba)

    # 容器自校验：解回来必须和放进去的**逐字节相同**。
    # 少了这一步，"字节序写反了"要等到插件里看出来才知道。
    back = unpack(blob)
    if back is None or not np.array_equal(back, rgba):
        print("✗ TRNL 容器自校验失败（解回来与原始像素不一致）", file=sys.stderr)
        return 1

    print(f"源图 {SRC.name}  sha256 {sha256(SRC)[:16]}…")
    print(f"输出 {st['size'][0]}x{st['size'][1]}  RGBA（容器内存 BGRA）")
    print(f"  alpha =0      {st['alpha_zero_pct']:5.1f}%")
    print(f"  alpha 中间    {st['alpha_mid_pct']:5.1f}%   （反锯齿边）")
    print(f"  alpha =255    {st['alpha_full_pct']:5.1f}%")
    print(f"  不透明但接近纯白 {st['opaque_near_white_pct']:5.2f}%   （洪水填充那版是 5.0%）")
    print(f"  金属实体 平均亮度 {st['solid_mean_lum']:.1f}   90 分位 {st['solid_p90_lum']:.1f}")

    # 硬判据：白盘必须真的没了
    if st["opaque_near_white_pct"] > 0.5:
        print("✗ 不透明但接近纯白的像素还太多 —— 白盘没除干净", file=sys.stderr)
        return 1
    if st["alpha_full_pct"] < 5.0:
        print("✗ 不透明像素太少 —— 抠过头了，金属被削掉", file=sys.stderr)
        return 1

    if args.preview:
        Image.fromarray(rgba, "RGBA").save(args.preview)
        print(f"  预览图 → {args.preview}")

    if args.check:
        if not OUT.exists():
            print(f"✗ 资产不存在：{OUT}", file=sys.stderr)
            return 1
        on_disk = unpack(OUT.read_bytes())
        same = on_disk is not None and np.array_equal(on_disk, rgba)
        print("✓ 磁盘上的资产与本次重建一致" if same else "✗ 磁盘上的资产与重建结果不一致")
        return 0 if same else 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(blob)
    print(f"✓ 写出 {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
