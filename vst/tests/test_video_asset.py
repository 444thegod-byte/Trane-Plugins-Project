"""视频背景素材（assets/video/backdrop.bin）的机器化检查。

**【已停用 —— 2026-09-29，v0.30】**

v0.30 的面板把视频背景整个拿掉了：面板改成 1440×720 横版、暗场，
背景改成**一张静态图**（小绪正在重做素材，还没交付）。
于是这份针对旧素材（544×988 / 75 帧 / 视频）的检查**当前不成立**：

  · 期望的尺寸 544×988 已经不是面板尺寸；
  · `TranePanel.h` 里 `kPanelW` / `kPanelH` 这两个常量已经不存在，
    依赖它们的用例会直接报 AttributeError 而不是给出有意义的失败；
  · 素材本身也没被任何代码引用（`TranePanel.cpp` 不再 include `TraneVideo.h`）。

**为什么是 skip 而不是删掉**：`plugin/TraneVideo.{h,cpp}` 是 `TRNV` 格式的
唯一规格说明（magic / 版本 / 头布局 / 档位查找表），新的静态背景会复用同一个
解码器（只烤 1 帧，`frameAt()` 恒返回 0，零新增解码代码）。素材到位后，
这个文件要**恢复并更新期望值**，不是重新发明一套检查。

skip 的理由写在下面，`pytest` 会在门禁输出里明确打印"5 skipped" ——
不是静默通过，是**显式停用**。

---

（以下为停用前的原文说明）

背景素材是**构建期生成、提交进仓库**的二进制文件。它一旦和代码分叉，
症状全都是"看起来还能跑"：

  · 版本号对不上 → `TraneVideo::clipData()` 判定素材无效 → 面板只剩纯纸，
    一句错都不报（这条真的发生过）；
  · 面板几何改了、素材没重烤 → 可读区遮罩错位，字符画压到环形文字上，
    字就糊了，而所有 DSP 测试都是绿的；
  · 素材被压成空白 → 背景没了，但帧数、尺寸全对。

所以这里做三件事：核对文件头、核对几何常量两边一致、**真的解一帧出来看**。

关于"不能空转通过"：解帧失败必须报红。如果只是"文件存在且 magic 对"就算过，
那和没测一样。
"""
from __future__ import annotations

import importlib.util
import math
import pathlib
import re
import struct
import zlib

import numpy as np
import pytest

pytestmark = pytest.mark.skip(
    reason="背景素材已随 v0.30 重做（面板 1440×720 静态图，待交付）—— "
           "旧的 544×988 视频素材已停用，素材到位后本文件必须恢复并更新期望值")

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSET = ROOT / "assets" / "video" / "backdrop.bin"
BUILDER = ROOT / "tools" / "build_video_frames.py"
PANEL_H = ROOT / "plugin" / "TranePanel.h"
VIDEO_CPP = ROOT / "plugin" / "TraneVideo.cpp"

MAGIC = b"TRNV"
VERSION = 3
HEADER_FIXED = 36          # magic(4) + 8 个 u32
EXPECT_FRAMES = 75
EXPECT_FPS = 15
EXPECT_W, EXPECT_H = 544, 988
EXPECT_LEVELS = 4
EXPECT_ALPHA = [0, 26, 76, 255]
EXPECT_INK = 0x0E0E0F
EXPECT_PAPER = 0xFAFAF9
MAX_BYTES = 1_600_000      # 0.71 MB 实测；留一倍余量当回归门槛


# ---------------------------------------------------------------------------
# 载入生成工具，取它的常量（不执行 main）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def builder():
    assert BUILDER.is_file(), f"找不到 {BUILDER}"
    spec = importlib.util.spec_from_file_location("build_video_frames", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 解析素材
# ---------------------------------------------------------------------------
def strip_comments(src: str) -> str:
    """去掉 // 注释，但不动字符串字面量里的内容。

    查源码里"有没有某个写法"之前必须先剥注释：这个文件里正当地写着
    「别改成 `ink.withAlpha(a)`」这种反面教材说明，连注释一起查会把它当成违规。

    （test_editor_layout.py 里有一份同样的实现。两处都只有十几行，
    各自自足比跨文件 import 稳 —— 测试文件之间的 import 依赖一旦断了，
    症状是 collect 阶段报错，看起来像环境坏了。）
    """
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


def load_header() -> dict:
    assert ASSET.is_file(), f"找不到素材 {ASSET}（重新生成：python tools/build_video_frames.py）"
    raw = ASSET.read_bytes()
    assert len(raw) >= HEADER_FIXED, f"素材只有 {len(raw)} 字节，连文件头都不够"
    assert raw[:4] == MAGIC, f"magic 不是 {MAGIC!r}，是 {raw[:4]!r}"

    version, count, w, h, fps, levels, ink, paper = struct.unpack_from("<IIIIIIII", raw, 4)
    alpha = list(struct.unpack_from(f"<{levels}I", raw, HEADER_FIXED))
    table_at = HEADER_FIXED + 4 * levels
    offsets = list(struct.unpack_from(f"<{count + 1}I", raw, table_at))
    return {"raw": raw, "version": version, "count": count, "w": w, "h": h, "fps": fps,
            "levels": levels, "ink": ink, "paper": paper, "alpha": alpha,
            "offsets": offsets, "table_at": table_at}


@pytest.fixture(scope="module")
def head() -> dict:
    return load_header()


def decode_frame(head: dict, index: int = 0) -> np.ndarray:
    """把第 index 帧解成 (h, w) 的档位数组（0..levels-1）。"""
    a, b = head["offsets"][index], head["offsets"][index + 1]
    packed = zlib.decompress(head["raw"][a:b])
    want = (head["w"] // 4) * head["h"]
    assert len(packed) == want, f"第 {index} 帧解出 {len(packed)} 字节，期望 {want}"
    arr = np.frombuffer(packed, np.uint8)
    lv = np.empty((arr.size, 4), np.uint8)
    lv[:, 0] = (arr >> 6) & 3
    lv[:, 1] = (arr >> 4) & 3
    lv[:, 2] = (arr >> 2) & 3
    lv[:, 3] = arr & 3
    return lv.reshape(head["h"], head["w"])


# ---------------------------------------------------------------------------
# 一 · 文件头
# ---------------------------------------------------------------------------
def test_asset_exists_and_is_within_the_size_budget(head):
    """素材要提交进仓库、编进二进制，体积是硬约束。

    实测 0.71 MB（9.7 KB/帧）。这条不是为了卡现在的数字，是为了防止有人
    换回 PNG / 提高量化档位而没人发现 —— 那会让插件体积涨 2–4 倍。
    """
    assert len(head["raw"]) <= MAX_BYTES, (
        f"素材 {len(head['raw'])} 字节，超过门槛 {MAX_BYTES}（换回未压缩/PNG 了？）")


def test_header_fields(head):
    assert head["version"] == VERSION, (
        f"素材版本 {head['version']} != {VERSION} —— "
        "TraneVideo.cpp 只认这个版本，对不上会**静默**判定素材无效")
    assert head["count"] == EXPECT_FRAMES
    assert (head["w"], head["h"]) == (EXPECT_W, EXPECT_H)
    assert head["fps"] == EXPECT_FPS
    assert head["levels"] == EXPECT_LEVELS
    assert head["alpha"] == EXPECT_ALPHA
    assert head["ink"] == EXPECT_INK, f"墨色 #{head['ink']:06X} != #{EXPECT_INK:06X}"
    assert head["paper"] == EXPECT_PAPER, f"纸色 #{head['paper']:06X} != #{EXPECT_PAPER:06X}"
    assert head["w"] % 4 == 0, "宽度必须是 4 的倍数（每字节装 4 个像素）"


def test_offset_table_is_monotone_and_inside_the_file(head):
    offs, size = head["offsets"], len(head["raw"])
    assert len(offs) == head["count"] + 1
    assert offs[0] == head["table_at"] + (head["count"] + 1) * 4, "第一帧的起点不对"
    assert offs[-1] == size, f"最后一帧的终点 {offs[-1]} != 文件长度 {size}"
    for i in range(head["count"]):
        assert 0 < offs[i + 1] - offs[i] < 400_000, f"第 {i} 帧的长度不合理"


def test_cpp_agrees_with_the_asset_header(head):
    """C++ 侧的文件头布局必须和素材一致。

    这两个数字分居两个文件，任何一边改了另一边不改，结果都是**一句错都不报、
    直接判定素材无效**（version 那条真的踩过）。所以从 C++ 源码里读出来比。
    """
    src = strip_comments(VIDEO_CPP.read_text(encoding="utf-8"))
    m = re.search(r"constexpr int kFixedHeader\s*=\s*(\d+)\s*;", src)
    assert m, "找不到 kFixedHeader"
    assert int(m.group(1)) == HEADER_FIXED, (
        f"TraneVideo.cpp 的 kFixedHeader={m.group(1)}，素材用的是 {HEADER_FIXED}")

    m = re.search(r"readU32\(p \+ 4\)\s*!=\s*(\d+)", src)
    assert m, "找不到版本校验（是不是被改写了？）"
    assert int(m.group(1)) == head["version"], (
        f"TraneVideo.cpp 校验版本 {m.group(1)}，素材是 {head['version']}")

    # 纸色必须从文件头读，不能在 C++ 里另写一份 —— 另写就会出现
    # "Python 改了纸色、C++ 还是旧的"，而画面只差一点点，肉眼看不出来。
    assert "paperRGB" in src, "C++ 没有从文件头读 paperRGB"
    assert "interpolatedWith" in src, (
        "档位查找表必须是「墨按 alpha 叠在纸上」的不透明像素；"
        "用 withAlpha 会解出半透明图，白纸上发灰、而且多一次合成")
    assert "withAlpha" not in src, "档位查找表不该再用 withAlpha"


# ---------------------------------------------------------------------------
# 二 · 生成工具 ↔ 面板几何
# ---------------------------------------------------------------------------
def test_builder_panel_size_matches_the_panel_header(builder):
    src = PANEL_H.read_text(encoding="utf-8")
    m = re.search(r"inline constexpr int kPanelW\s*=\s*(\d+)\s*;", src)
    n = re.search(r"inline constexpr int kPanelH\s*=\s*(\d+)\s*;", src)
    assert m and n
    assert builder.PANEL_W == int(m.group(1)), (
        f"生成工具 PANEL_W={builder.PANEL_W}，面板 kPanelW={m.group(1)}")
    assert builder.PANEL_H == int(n.group(1)), (
        f"生成工具 PANEL_H={builder.PANEL_H}，面板 kPanelH={n.group(1)}")


def test_builder_radii_match_the_panel_header(builder):
    src = PANEL_H.read_text(encoding="utf-8")
    ring = re.search(r"inline constexpr float kRingR\s*=\s*([\d.]+)f", src)
    scale = re.search(r"inline constexpr float kScaleR\s*=\s*([^;]+);", src)
    assert ring and scale, "找不到 kRingR / kScaleR"
    want_ring = float(ring.group(1))
    # kScaleR 是推导式，直接算
    expr = re.sub(r"(\d)f\b", r"\1", scale.group(1))
    names = dict(re.findall(r"inline constexpr float (k\w+)\s*=\s*([\d.]+)f", src))
    want_scale = eval(expr, {"__builtins__": {}}, {k: float(v) for k, v in names.items()})

    assert builder.RING_R == want_ring, f"生成工具 RING_R={builder.RING_R} != {want_ring}"
    assert builder.SCALE_R == want_scale, f"生成工具 SCALE_R={builder.SCALE_R} != {want_scale}"

    # 遮罩边界写死在生成工具里（RING_R - 1 / SCALE_R + 6），这两个余量是设计的一部分：
    # 圆内退 1px 是让圆描边盖住遮罩边；辐条区多让 6px 是给刻度与辐条留空。
    assert "RING_R - 1.0" in BUILDER.read_text(encoding="utf-8")
    assert "SCALE_R + 6.0" in BUILDER.read_text(encoding="utf-8")


def test_builder_node_centres_match_the_panel_formula(builder):
    """生成工具里那份圆心坐标必须和面板推导出来的一致。

    两份常量是必须的（Python 不能 include C++ 头文件），所以只能靠测试盯着。
    圆心错了 → 可读区遮罩错位 → 字符画压到环形文字上。
    """
    src = PANEL_H.read_text(encoding="utf-8")
    ring_r = float(re.search(r"inline constexpr float kRingR\s*=\s*([\d.]+)f", src).group(1))
    pad = float(re.search(r"inline constexpr float kPad\s*=\s*([\d.]+)f", src).group(1))
    spoke = [float(re.search(rf"inline constexpr float {k}\s*=\s*([\d.]+)f", src).group(1))
             for k in ("kSpokeBase", "kSpokeMin", "kSpokeSpan")]
    col_spacing = ring_r / 0.341
    tree_h = ring_r / 0.0740
    y0 = pad + (ring_r + sum(spoke))

    block = re.search(r"inline constexpr NodeSpec kNodes\[\]\s*=\s*\{(.*?)\n\};", src, re.S)
    assert block, "找不到 kNodes"
    rows = re.findall(r'\{"(\w+)"\s*,\s*"(\w+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*([\d.]+)f\}',
                      block.group(1))
    assert len(rows) == len(builder.NODE_CENTRES) == 10, (
        f"kNodes {len(rows)} 条，生成工具 {len(builder.NODE_CENTRES)} 条")

    for (sephira, _module, _title, column, ratio), (bx, by) in zip(rows, builder.NODE_CENTRES):
        want_x = 272.0 + (int(column) - 1) * col_spacing
        want_y = y0 + float(ratio) * tree_h
        assert math.hypot(bx - want_x, by - want_y) < 0.01, (
            f"{sephira}: 生成工具 ({bx}, {by}) != 面板公式 ({want_x:.3f}, {want_y:.3f})")


# ---------------------------------------------------------------------------
# 三 · 真的解一帧出来看
# ---------------------------------------------------------------------------
def test_every_frame_decompresses_to_the_expected_size(head):
    """全部 75 帧都要能解开、长度正确。

    只抽查第 0 帧是不够的 —— zlib 流是每帧独立的，某一帧生成失败只会影响那一帧。
    """
    for i in range(head["count"]):
        a, b = head["offsets"][i], head["offsets"][i + 1]
        packed = zlib.decompress(head["raw"][a:b])
        assert len(packed) == (head["w"] // 4) * head["h"], f"第 {i} 帧长度不对"


def test_frames_are_not_empty_and_not_solid(head):
    """背景必须"有东西"，而且**不能糊成一片**。

    这两种失败都是"素材在、帧数对、尺寸对"：
      · 阈值调太高 → 全 0 → 背景空白，面板只剩纯纸；
      · 阈值调太低 / 遮罩坏了 → 全 3 → 整幅变黑，界面全废。
    """
    for i in (0, 20, 40, 60, 74):
        lv = decode_frame(head, i)
        ink = float((lv > 0).mean())
        full = float((lv >= 3).mean())
        assert 0.01 < ink < 0.35, f"第 {i} 帧墨覆盖 {ink:.2%} —— 空白或糊死了"
        assert full < 0.30, f"第 {i} 帧满墨比例 {full:.2%} —— 遮罩可能没生效"


def test_readable_zones_are_masked_in_the_baked_frames(head, builder):
    """圆内的档位必须 ≤ LEVEL_IN_RING —— 这是"字符画不许压到环形文字上"的
    唯一保证，而且是**烘进素材**的，运行时不会再有第二次机会。

    直接按每个像素到圆心的距离算，和生成工具用的是同一套几何，
    但代码是这里独立写的（生成工具用 np.where 逐圆覆盖，这里用最小距离）。
    """
    lv = decode_frame(head, 13)
    yy, xx = np.mgrid[0:head["h"], 0:head["w"]].astype(np.float32)
    xx += 0.5
    yy += 0.5
    d = np.full((head["h"], head["w"]), 1e9, np.float32)
    for cx, cy in builder.NODE_CENTRES:
        d = np.minimum(d, np.hypot(xx - cx, yy - cy))

    inside = d < (builder.RING_R - 1.0)
    assert inside.any(), "一个圆内像素都没圈到 —— 几何对不上了"
    worst = int(lv[inside].max())
    assert worst <= builder.LEVEL_IN_RING, (
        f"圆内出现了档位 {worst}（允许的最大是 {builder.LEVEL_IN_RING}）—— "
        "字符画会压到环形文字上")

    spoke = (d >= builder.RING_R - 1.0) & (d < builder.SCALE_R + 6.0)
    assert spoke.any()
    assert int(lv[spoke].max()) <= builder.LEVEL_IN_SCALE, (
        f"辐条区出现了档位 {int(lv[spoke].max())}，会盖住刻度")

    outside = d >= builder.SCALE_R + 6.0
    assert outside.any()
    assert int(lv[outside].max()) == builder.LEVEL_OUTSIDE, "圆外应该保持满强度"


def test_alpha_table_is_monotone_and_starts_at_zero(head):
    """四档 alpha 必须从 0 开始递增。档位 0 = 没墨 = 纸色，
    这是"解出来的图不透明、直接贴"这条设计的地基。"""
    assert head["alpha"][0] == 0, "档位 0 必须完全没墨"
    assert head["alpha"][-1] == 255, "最高档必须是满墨"
    assert head["alpha"] == sorted(head["alpha"]), "alpha 表必须单调递增"


def test_frames_differ_from_each_other(head):
    """帧与帧必须真的不一样 —— 否则就是"抽帧只抽到一张"。
    这类失败帧数、尺寸、墨量全对，但背景是静止的。"""
    a = decode_frame(head, 0)
    diffs = [float((decode_frame(head, i) != a).mean()) for i in (15, 37, 59)]
    assert max(diffs) > 0.002, f"所有帧几乎一样（最大差异 {max(diffs):.4%}）—— 背景是静止的"
