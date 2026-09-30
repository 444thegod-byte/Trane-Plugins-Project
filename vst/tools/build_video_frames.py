#!/usr/bin/env python3
"""把一段 ASCII 动画视频烤成插件可以直接贴的背景素材。

为什么是"烤"而不是运行时解码 MP4
=================================
在 VST3 里实时解 2920×2838@60fps 的 H.264，代价和风险都不划算：
硬件解码器要经 AVFoundation，插件编辑器里塞原生视频层会和宿主的合成器
打架（z-order、裁剪、编辑器反复开关），而且**离线渲染验证会彻底失效** ——
这个项目的界面之所以能机器验证，就是因为面板层不依赖任何外部状态。

所以改成：构建期把视频抽成帧序列，量化成 4 档（2 bit），打包成一个二进制块
（`assets/video/backdrop.bin`），运行时只做「读一帧 → 贴上去」。
素材提交进仓库，**构建插件不需要装 ffmpeg**。

为什么必须量化（每像素只剩 4 档）
================================
实测（60 帧，544×988）：

    连续灰阶 + RGBA/PNG      100.0 KB/帧   → 5.86 MB
    4 级（2 bit）             25.7 KB/帧   → 1.50 MB
    2 级（1 bit）             16.2 KB/帧   → 0.95 MB

抗锯齿产生的连续灰阶让压缩完全压不动。而这段素材本来就是硬边字符画，
量化成整数档位不但体积掉到 1/6，画面反而更接近参考图那种"字符戳出来的"质感。

四档而不是两档，是为了让"圆内 / 辐条区 / 圆外"三个可读区档位能同时存在
（见下），再留一个 0 = 完全没墨。

为什么不用 PNG
=============
PNG 压得不错，但**解得慢**。实测 JUCE 解一张 544×988 的 RGBA PNG 要
8–14 ms；15fps 就是单核 16–21%，而且每 66 ms 在 UI 线程上卡一下，
呼吸动画会看得见地一顿。

所以改成自己打包：**每像素 2 bit（4 档 alpha）× zlib**。

    2 bit 打包后未压缩      131.2 KB/帧
    2 bit + zlib              9.7 KB/帧 → 75 帧 0.71 MB
    （对照 RGBA/PNG          17.9 KB/帧 → 75 帧 1.31 MB）

比 PNG 小 45%，而解码只是「inflate 131 KB + 一个四路展开的循环」，
实测 **0.62 ms**。**两边都赢，所以没有理由用 PNG。**

**用的是 zlib 流，不是 gzip 流。** JUCE 的
`GZIPDecompressorInputStream(InputStream&)` 这个便利构造函数默认按
`zlibFormat` 解（见 juce_GZIPDecompressorInputStream.cpp:142），传 gzip 数据
进去会一句错都不报、直接解不出来。用 zlib 格式两边都不用额外参数。

可读区遮罩（烘进档位，运行时零成本）
==================================
圆内的环形文字只有 7.0 / 7.5 逻辑像素，背后压一层字符画就没法读了。
所以遮罩在**构建期**就乘进档位：

    圆内   r < kRingR − 1    档位 1（10% 墨）
    辐条区 r < kScaleR + 6   档位 2（30% 墨）
    圆外                     档位 3（100% 墨）

档位是整数，不是浮点乘出来的 —— 运行时拿到的档位一定是 0..3。

**纸色也烘进去，整帧不透明。** 这一步是为了速度：alpha 混合 2.1M 个目标像素
要 4 ms，而不透明直贴只要 0.4 ms。烘进去之后运行时就是「贴一张不透明图」，
不需要底图缓存、不需要 fillAll、也不需要 backdrop 合成。

墨色、纸色、四档 alpha 都写在文件头里，**不是两边各写一份常量** ——
这样 Python 改一个数，C++ 不用跟着改，也不会出现"两边对不上但谁也不报错"。

文件格式（全部小端）
====================
    offset  0   char[4]  magic = "TRNV"
    offset  4   uint32   version   = 3
    offset  8   uint32   frameCount
    offset 12   uint32   width
    offset 16   uint32   height
    offset 20   uint32   fps
    offset 24   uint32   levelCount
    offset 28   uint32   inkRGB
    offset 32   uint32   paperRGB
    offset 36   uint32   alpha[levelCount]
    offset 36+4*levelCount   uint32 offsets[frameCount + 1]
    ...         每帧一段 zlib 流，内容是 width*height 个 2-bit 档位，
                每字节装 4 个像素，高位在前，按行主序

用法
====
    build_video_frames.py [--video <mp4>] [--out <bin>]
                          [--fps 15] [--width 544] [--height 988]
                          [--threshold 0.42] [--keep-frames <dir>]

需要 ffmpeg 在 PATH 上（只在**重新生成素材**时需要，构建插件不需要）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

# ---------------------------------------------------------------------------
# 面板几何 —— 必须与 plugin/TranePanel.h 的 geom 保持一致。
# 有回归测试（tests/test_video_asset.py）逐条比对，改了一边不改另一边会红。
# ---------------------------------------------------------------------------
PANEL_W = 544
PANEL_H = 988
RING_R = 58.0
SCALE_R = 78.0

# 圆心（逻辑坐标），顺序 = kNodes：Keter → Malkuth
NODE_CENTRES = [
    (272.0, 102.0),      # keter   freeze
    (442.088, 199.973),  # chokhmah grain
    (101.912, 199.973),  # binah   stutter
    (442.088, 395.919),  # chesed  comb
    (101.912, 395.919),  # gevurah tape
    (272.0, 493.892),    # tiferet ruin
    (442.088, 591.865),  # netzach sweep
    (101.912, 591.865),  # hod     delay
    (272.0, 689.838),    # yesod   space
    (272.0, 885.784),    # malkuth out
]

# 可读区遮罩的档位（0 = 没墨）。四个 alpha 值写进文件头，运行时照着建查找表，
# 所以这里改了不用去改 C++。
LEVEL_IN_RING = 1    # alpha 26  —— 圆内：只剩一层极淡的底纹
LEVEL_IN_SCALE = 2   # alpha 76  —— 辐条区：让开刻度与辐条
LEVEL_OUTSIDE = 3    # alpha 255 —— 圆外：满强度
LEVEL_ALPHA = [0, 26, 76, 255]

# 墨色 = TranePanel.h 的 kInk；纸色 = kPaper。都写进文件头，运行时照着建查找表。
INK_RGB = 0x0E0E0F
PAPER_RGB = 0xFAFAF9

# 视频背景的亮度。素材是浅灰底上的深色字符，键掉底色只留墨。
VIDEO_BG_LEVEL = 235.0

MAGIC = b"TRNV"
VERSION = 3
HEADER_FIXED = 36   # magic(4) + version/count/w/h/fps/levels/ink/paper 八个 u32


def probe(video: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
         "-of", "default=noprint_wrappers=1", video],
        capture_output=True, text=True, check=True).stdout
    info = {}
    for line in out.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k] = v
    return info


def extract(video: str, dest: str, width: int, height: int, fps: float) -> int:
    """按面板比例居中裁剪，再缩到面板尺寸，抽成灰度 PNG 序列。"""
    info = probe(video)
    sw, sh = int(info["width"]), int(info["height"])

    # 居中裁剪到面板比例（宁可切掉两侧，也不横向压扁 —— 压扁会把字符拉变形）
    want_w = int(round(sh * (width / height)))
    if want_w <= sw:
        crop = f"crop={want_w}:{sh}:{(sw - want_w) // 2}:0,"
    else:
        want_h = int(round(sw * (height / width)))
        crop = f"crop={sw}:{want_h}:0:{(sh - want_h) // 2},"

    vf = f"{crop}scale={width}:{height}:flags=lanczos,fps={fps}"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", video, "-vf", vf,
         os.path.join(dest, "f%04d.png")],
        check=True)

    return len([f for f in os.listdir(dest) if f.endswith(".png")])


def build_level_map():
    """每个像素该用哪一档 alpha（0 = 没墨，1/2/3 见 LEVEL_*）。

    用整数网格算，和 C++ 那边一样是"圆心到像素中心的欧氏距离"，不做任何抗锯齿 ——
    遮罩的边界正好落在圆的描边上，本来就会被盖住。
    """
    import numpy as np

    yy, xx = np.mgrid[0:PANEL_H, 0:PANEL_W].astype(np.float32)
    xx += 0.5
    yy += 0.5

    lv = np.full((PANEL_H, PANEL_W), LEVEL_OUTSIDE, np.uint8)
    for cx, cy in NODE_CENTRES:
        d = np.hypot(xx - cx, yy - cy)
        lv[d < SCALE_R + 6.0] = LEVEL_IN_SCALE
        lv[d < RING_R - 1.0] = LEVEL_IN_RING
    return lv


def bake(frames_dir: str, out_path: str, threshold: float, keep: str | None,
         width: int, height: int):
    import numpy as np
    from PIL import Image

    files = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
    if not files:
        sys.exit("没有抽到任何帧")
    if width % 4 != 0:
        sys.exit(f"宽度必须是 4 的倍数（每字节装 4 个像素），现在是 {width}")

    level_map = build_level_map()
    blobs: list[bytes] = []
    levels = []

    for name in files:
        a = np.asarray(Image.open(os.path.join(frames_dir, name)).convert("L")).astype(np.float32)
        if a.shape != (PANEL_H, PANEL_W):
            sys.exit(f"{name} 尺寸是 {a.shape}，期望 {(PANEL_H, PANEL_W)}")

        # 键掉底色 → 墨的浓度；再二值化；再乘上可读区档位
        ink = np.clip((VIDEO_BG_LEVEL - a) / VIDEO_BG_LEVEL, 0.0, 1.0)
        ink = (ink >= threshold)
        lv = np.where(ink, level_map, 0).astype(np.uint8)
        levels.append(lv)

        # 2 bit 打包：每字节 4 个像素，高位在前
        flat = lv.ravel()
        packed = ((flat[0::4].astype(np.uint16) << 6)
                  | (flat[1::4].astype(np.uint16) << 4)
                  | (flat[2::4].astype(np.uint16) << 2)
                  | flat[3::4].astype(np.uint16)).astype(np.uint8)
        blobs.append(zlib.compress(packed.tobytes(), 9))

        if keep:
            os.makedirs(keep, exist_ok=True)
            # 另存一张肉眼可看的 PNG（不参与打包，只为核对）：
            # 纸色打底，按档位把墨叠上去 —— 和运行时看到的一模一样。
            paper = np.array([(PAPER_RGB >> 16) & 255, (PAPER_RGB >> 8) & 255,
                              PAPER_RGB & 255], np.float32)
            ink = np.array([(INK_RGB >> 16) & 255, (INK_RGB >> 8) & 255,
                            INK_RGB & 255], np.float32)
            a = np.take(np.array(LEVEL_ALPHA, np.float32), lv) / 255.0
            rgb = paper[None, None, :] * (1.0 - a[..., None]) + ink[None, None, :] * a[..., None]
            Image.fromarray(rgb.round().astype(np.uint8), "RGB").save(os.path.join(keep, name))

    # ---- 打包 ----
    count = len(blobs)
    table_at = HEADER_FIXED + 4 * len(LEVEL_ALPHA)
    offsets = []
    cursor = table_at + (count + 1) * 4
    for b in blobs:
        offsets.append(cursor)
        cursor += len(b)
    offsets.append(cursor)

    with open(out_path, "wb") as fh:
        fh.write(MAGIC)
        fh.write(struct.pack("<IIIIIIII", VERSION, count, width, height, 15,
                             len(LEVEL_ALPHA), INK_RGB, PAPER_RGB))
        fh.write(struct.pack(f"<{len(LEVEL_ALPHA)}I", *LEVEL_ALPHA))
        fh.write(struct.pack(f"<{len(offsets)}I", *offsets))
        for b in blobs:
            fh.write(b)

    return count, os.path.getsize(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default="/Users/444_thegod/Desktop/444site-2/asciify.mp4")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__),
                                                  "..", "assets", "video", "backdrop.bin"))
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--width", type=int, default=PANEL_W)
    ap.add_argument("--height", type=int, default=PANEL_H)
    ap.add_argument("--threshold", type=float, default=0.42)
    ap.add_argument("--keep-frames", default=None,
                    help="把每帧另存一张 RGB PNG 到这个目录（纸色打底、按档位叠墨，"
                         "和运行时看到的一致；供人肉眼核对，不参与打包）")
    args = ap.parse_args()

    if not os.path.isfile(args.video):
        sys.exit(f"找不到视频：{args.video}")
    if shutil.which("ffmpeg") is None:
        sys.exit("PATH 上没有 ffmpeg —— 重新生成素材需要它，构建插件不需要")

    tmp = tempfile.mkdtemp(prefix="trane_video_")
    try:
        n = extract(args.video, tmp, args.width, args.height, args.fps)
        print(f"抽出 {n} 帧  {args.width}×{args.height}  {args.fps:g}fps")
        count, size = bake(tmp, os.path.abspath(args.out), args.threshold,
                           args.keep_frames, args.width, args.height)
        print(f"打包 {count} 帧 → {os.path.abspath(args.out)}  {size / 1048576:.2f} MB "
              f"({size / count / 1024:.1f} KB/帧)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
