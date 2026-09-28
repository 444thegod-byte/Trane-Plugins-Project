#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_root_patch.py —— 修正 src/Trane.maxpat 的结构性缺陷并重排设备面板

每一项修复都有出处：要么是官方 refpage，要么是本机 127 个真实 .amxd 的实测统计。
没有任何一条是"看起来应该这样"。

================================ 一次自我更正 ================================
之前我判断「record~ 没有 loop 消息，那条连线无效」并把它删掉了 —— **这是错的**。
当时的依据是 record~ refpage 的 methodlist 里没有 loop。但 Max 的**属性消息**
（attribute message）不列在 methodlist 里。record~ 的属性表里明确有 loop：

    loop        The word loop, followed by a non-zero number, enables loop
                recording mode. In loop mode, when recording reaches the end
                point of the recording it continues at the start point.
                loop 0 disables loop recording mode.

这个错误反而指出了一个更稳的方案：用 loop 模式把录音窗口钉死在
[0, loop_length_ms]，缓冲区里永远是"最近 N 毫秒"，于是

    Freeze = 停止录音 + groove~ 循环播放

完全不需要读"当前写入位置"。原来那套 snapshot~ 读 record~ sync 出口的做法
依赖一个 refpage 没有描述的出口语义，无法静态验证，已整体移除。

================================ 接线类 ================================

1. `poly~ TraneGrainVoice 6` 进出口数写成了 2进/1出，而 TraneGrainVoice
   实际是 1进/2出 —— 右声道粒子出口因此无效。

2. `snapshot~` 的 bang 接在入口 1（该入口是上报间隔）。bang 必须接入口 0。
   （该对象连同整套位置计算已随新 Freeze 方案移除。）

3. `record~` 的录音窗口改为用 loop 模式固定：
   · 对象框写 `record~ trane_capture 2 @loop 1`（属性在实例化时生效，不依赖 loadbang 顺序）
   · `loop_length_ms` → record~ 入口 3（官方：Recording End Point in ms）
   · `loop_length_ms` → `prepend setloop 0` → groove~ 入口 0（循环点与录音窗口一致）
   · Freeze 开：`sel 1` → 消息 `0` → record~ 入口 0（停止录音）
              → `startloop` → groove~（从循环起点播放）
   · Freeze 关：`sel 1` 出口 1 → 消息 `1` → record~ 入口 0（恢复录音）

4. groove~ 的入口 0 是**播放速率**（refpage: Sample Playback Increment）。
   原来把 `t b l` 的出口 1（输出 "setloop 100 2000" 里的第一个数 100）
   接在这里 —— 会被当成 100 倍播放速率。同时 `t b l` 的出口 0 永远不发 bang，
   `startloop` 一次都没触发过。整套 t b l 链路已移除。

5. `obj-82` 的入口 0 有两个驱动源（obj-80 与 obj-103）。
   对 `*` 的热入口来说后到的覆盖先到的 —— ARP 每走一步算出 rate×比例，
   用户一动 Rate 旋钮又变回 rate×1，ARP 的比例被抹掉。删掉多余的 obj-80 → obj-82。

6. `obj-87` 是 `append 1/16, append 1/8, ...` 消息，由 loadbang 触发。
   实测统计：真实设备里 menu/tab 的条目来源
        仅 parameter_enum : 53
        仅 append 消息    : 0
        两者都有          : 0
   parameter_enum 才是唯一做法；保留 append 会让菜单项重复。删除。

7. `obj-39` 是 `set Clear Ruin`。live.tab 的 `set` 官方定义是
   "Display a menu item without triggering output" —— 参数是**序号**，不是条目名。
   这条消息是无效的。标签项由 parameter_enum 提供，删除 obj-39。

8. `obj-83` 是 `transport`，没有任何连线，是死代码。删除。

9. `metro 16n @quantize 16n` 去掉 @quantize。
   refpage：@quantize 只在 tempo-relative 时生效，把输出对齐到时间网格边界；
   网格依赖 transport 走时，transport 停住时边界永不到达 —— ARP 会静默不响，
   表现就是"ARP 没用"。去掉后 `16n` 仍跟随 Live 的速度，但按下开关立刻就跑。

================================ 参数类 ================================

10. 给全部 live.* 控件补齐参数元数据（交给 tools/param_meta.py）。
    实测：真实设备的 live.menu / live.tab 100% 带 parameter_enum，
    live.dial 514/514 带 parameter_shortname。
    缺了它 → 菜单是空的（ARP 选不了速率）、MODE 没有可见选项、
    Live 参数列表里全是"未命名参数"。

11. 进出口数对齐官方 refpage（live.dial 2出、live.tab/menu 3出）。

================================ 面板类 ================================

12. Presentation 布局整排越界。M4L 音频效果器面板高度固定 169px
    （实测 105 个可解析的真实 .amxd：102 个是 169.0）。
    唯一的例外是 Max 自动插入的隐藏 live.toolbar（y≈700，Live 里不可见），
    验证器已排除它。

13. devicewidth / openrect。实测 devicewidth 才是设备宽度，内容右缘
    一般留 10–18px 边距。这里取 650，内容最右到 630。

14. Huge Space 的 Mix 改成真正的干湿交叉淡化。原拓扑是「干声恒为 1.0
    + 湿声 × mix」，那是 send：Mix 拉到 100 会变成干+湿叠加，比不拉还响。
    标签写着 MIX 就必须真的是 mix —— dry = (1 - mix)，wet = mix。

本脚本可重复运行。
"""

from __future__ import annotations

import json
from pathlib import Path

import param_meta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = PROJECT_ROOT / "src" / "Trane.maxpat"

# M4L 音频效果器设备面板尺寸（实测 105 个真实 .amxd 的高度分布：169.0 × 102）
DEVICE_HEIGHT = 169.0
DEVICE_WIDTH = 650.0

# 录音缓冲：20 s / 立体声。实际只用到前 loop_length_ms，留足余量。
RECORD_OBJECT = "record~ trane_capture 2 @loop 1"

# ---------------------------------------------------------------------------
# Presentation 布局
# 纵向预算（总高 169）：
#   标题      y=2..14
#   分组标题  y=15..26
#   控件行    y=27..49   （开关 22px + 右侧标签 11px）
#   拨轮行1   y=52..90   （38px）
#   标签行1   y=91..102
#   分组标题2 y=104..115
#   拨轮行2   y=116..154 （38px）
#   标签行2   y=155..166
# 内容最右 630，devicewidth 650 → 右边距 20
# ---------------------------------------------------------------------------
LAYOUT: dict[str, tuple[float, float, float, float]] = {
    # ---- 标题 ----
    "obj-1": (8, 2, 596, 12),

    # ---- 分组标题（左缘对齐各自簇）----
    "obj-2": (8, 15, 92, 11),         # CAPTURE
    "obj-51": (104, 15, 236, 11),     # GRAIN
    "obj-85": (440, 15, 150, 11),     # ARP

    # ---- 控件行 y=27（高 22），标签在右侧 y=32（高 11）----
    "obj-11": (8, 27, 22, 22),        # FREEZE toggle
    "obj-12": (33, 32, 62, 11),       # FREEZE
    "obj-16": (104, 27, 22, 22),      # REVERSE toggle
    "obj-17": (129, 32, 62, 11),      # REVERSE
    "obj-24": (200, 27, 90, 22),      # MODE tab
    "obj-25": (293, 32, 40, 11),      # MODE
    "obj-50": (350, 27, 22, 22),      # GRAIN toggle
    "obj-49": (375, 32, 46, 11),      # GRAIN（复用过期占位对象）
    "obj-84": (440, 27, 22, 22),      # ARP toggle
    "obj-37": (466, 32, 34, 11),      # ARP（复用过期占位对象）
    "obj-86": (506, 27, 78, 22),      # ARP rate menu
    "obj-130": (588, 32, 42, 11),     # RATE（新增）

    # ---- 拨轮行 1 y=52（38×38）----
    "obj-20": (8, 52, 38, 38),        # loop_length_ms
    "obj-52": (104, 52, 38, 38),      # grain_size_ms
    "obj-54": (152, 52, 38, 38),      # grain_density
    "obj-56": (200, 52, 38, 38),      # grain_position
    "obj-58": (248, 52, 38, 38),      # grain_spray
    "obj-80": (296, 52, 38, 38),      # grain_rate
    "obj-94": (506, 52, 38, 38),      # arp_probability
    "obj-96": (554, 52, 38, 38),      # arp_steps

    # ---- 标签行 1 y=91（高 11）----
    "obj-21": (8, 91, 46, 11),        # LOOP ms
    "obj-53": (104, 91, 40, 11),      # SIZE
    "obj-55": (152, 91, 46, 11),      # DENSITY
    "obj-57": (200, 91, 46, 11),      # POSITION
    "obj-59": (248, 91, 40, 11),      # SPRAY
    "obj-81": (296, 91, 40, 11),      # RATE
    "obj-95": (506, 91, 40, 11),      # PROB
    "obj-97": (554, 91, 40, 11),      # STEPS

    # ---- 分组标题 2 y=104（高 11）----
    "obj-105": (8, 104, 110, 11),     # HUGE SPACE
    "obj-106": (122, 104, 140, 11),   # 8s+ feedback plate

    # ---- 拨轮行 2 y=116（38×38）：Huge Space ----
    "obj-107": (8, 116, 38, 38),      # verb_mix
    "obj-109": (76, 116, 38, 38),     # verb_size
    "obj-111": (144, 116, 38, 38),    # verb_decay
    "obj-113": (212, 116, 38, 38),    # verb_damping
    "obj-115": (280, 116, 38, 38),    # verb_diffusion

    # ---- 标签行 2 y=155（高 11）----
    "obj-108": (8, 155, 40, 11),      # MIX
    "obj-110": (76, 155, 46, 11),     # SPACE
    "obj-112": (144, 155, 40, 11),    # TAIL
    "obj-114": (212, 155, 44, 11),    # DAMP
    "obj-116": (280, 155, 56, 11),    # DIFFUSE
}

# 新增对象
NEW_BOXES: dict[str, dict] = {
    "obj-130": dict(maxclass="comment", text="RATE"),
    "obj-132": dict(maxclass="message", text="1"),   # Freeze 关 → 恢复录音
    # 干湿交叉淡化：Mix 的标签是 MIX，就必须真的是 mix。
    # 原拓扑是「干声恒为 1.0 + 湿声 × mix」，那是 send —— Mix 拉到 100 会变成
    # 干+湿叠加，比不拉还响，和标签说的不是一回事。
    "obj-133": dict(maxclass="newobj", text="expr 1. - $f1",
                    numinlets=1, numoutlets=1, outlettype=["float"],
                    patching_rect=[2400.0, 560.0, 110.0, 20.0]),
    "obj-134": dict(maxclass="newobj", text="*~",
                    numinlets=2, numoutlets=1, outlettype=["signal"],
                    patching_rect=[2400.0, 590.0, 36.0, 20.0]),
    "obj-135": dict(maxclass="newobj", text="*~",
                    numinlets=2, numoutlets=1, outlettype=["signal"],
                    patching_rect=[2400.0, 620.0, 36.0, 20.0]),
}

# 改写对象的字段（就地复用旧对象，避免无谓增删）
REPURPOSE: dict[str, dict] = {
    # obj-9 原来是 snapshot~（靠 record~ 的 sync 出口读写入位置）。
    # 新方案不需要读位置，改为「停止录音」的消息框。
    "obj-9": dict(maxclass="message", text="0", numinlets=1, numoutlets=1, outlettype=[""]),
    # obj-45 由 "prepend setloop" 改为 "prepend setloop 0"（循环点从 0 开始）
    "obj-45": dict(text="prepend setloop 0"),
    # obj-5：录音窗口用 loop 模式固定，属性写在对象框里。
    # 入口数 = 声道数 + 2（0/1 = 左右声道信号，2 = 录音起点，3 = 录音终点）。
    "obj-5": dict(text=RECORD_OBJECT, numinlets=4),
}

# 改写后的文字
REWRITE_TEXT: dict[str, str] = {
    "obj-1": "Träne  ·  granular freeze · grain · audio arp · huge space",
    "obj-2": "CAPTURE",
    "obj-12": "FREEZE",
    "obj-17": "REVERSE",
    "obj-25": "MODE",
    "obj-51": "GRAIN",
    "obj-85": "ARP",
    "obj-49": "GRAIN",
    "obj-37": "ARP",
    "obj-105": "HUGE SPACE",
    "obj-106": "8s+ feedback plate",
    "obj-21": "LOOP ms",
    # 开发笔记：内容已随新方案更新
    "obj-38": "Freeze: record~ runs in loop mode inside [0, loop_length_ms], so the buffer always holds the most recent window. Freeze stops the recording and loops that window in groove~.",
    "obj-48": "Rolling capture: record~ loops inside [0, loop_length_ms].",
    "obj-104": "Audio ARP: tempo-relative steps (16n/8n/4n/2n) retrigger the grain voices.",
}

# 这些对象原来被放进 Presentation，但内容是纯开发笔记，撤出面板
DROP_FROM_PRESENTATION = {"obj-129"}

# 彻底删除的对象
DELETE_BOXES = {
    "obj-39",   # set Clear Ruin —— live.tab 的 set 接受序号，不接受条目名，无效
    "obj-41",   # expr 位置计算 —— 随旧 Freeze 方案移除
    "obj-42",   # t f f
    "obj-43",   # + 100.
    "obj-44",   # pack f f
    "obj-46",   # t b l —— 出口 1 把 loop 起点当成了播放速率
    "obj-83",   # transport —— 没有任何连线
    "obj-87",   # append 消息 —— 与 parameter_enum 冲突
}

# 需要删除的连线 (源 id, 源出口, 目标 id, 目标入口)
CUT_LINES = {
    ("obj-5", 0, "obj-9", 0),     # record~ sync 出口 → snapshot~（obj-9 已改成消息框）
    ("obj-9", 0, "obj-41", 0),
    ("obj-20", 0, "obj-41", 1),
    ("obj-41", 0, "obj-42", 0),
    ("obj-42", 0, "obj-44", 0),
    ("obj-42", 1, "obj-43", 0),
    ("obj-20", 0, "obj-43", 1),
    ("obj-43", 0, "obj-44", 1),
    ("obj-44", 0, "obj-45", 0),
    ("obj-45", 0, "obj-46", 0),
    ("obj-46", 0, "obj-14", 0),
    ("obj-46", 1, "obj-10", 0),
    ("obj-6", 0, "obj-39", 0),    # loadbang → set Clear Ruin
    ("obj-6", 0, "obj-87", 0),    # loadbang → append
    ("obj-80", 0, "obj-82", 0),   # Rate 旋钮与 ARP 比例争抢 obj-82 入口 0
    ("obj-77", 0, "obj-127", 0),  # 干声直连输出 —— 改成先过干声增益
    ("obj-78", 0, "obj-128", 0),
}

# 需要新增的连线 (源 id, 源出口, 目标 id, 目标入口)
NEW_LINES = [
    ("obj-20", 0, "obj-5", 3),      # loop_length_ms → record~ 录音终点
    ("obj-20", 0, "obj-45", 0),     # loop_length_ms → prepend setloop 0
    ("obj-45", 0, "obj-10", 0),     # prepend setloop 0 → groove~ 循环点
    ("obj-9", 0, "obj-5", 0),       # 停止录音 → record~
    ("obj-13", 0, "obj-14", 0),     # Freeze 开 → startloop
    ("obj-13", 1, "obj-132", 0),    # Freeze 关 → 消息 1
    ("obj-132", 0, "obj-5", 0),     # 恢复录音 → record~
    # 干湿交叉淡化：dry = 1 - mix，wet = mix
    ("obj-77", 0, "obj-134", 0),
    ("obj-134", 0, "obj-127", 0),
    ("obj-78", 0, "obj-135", 0),
    ("obj-135", 0, "obj-128", 0),
    ("obj-120", 0, "obj-133", 0),   # mix → expr 1 - mix
    ("obj-133", 0, "obj-134", 1),
    ("obj-133", 0, "obj-135", 1),
]


def _find_line(lines: list, key: tuple) -> int:
    for i, l in enumerate(lines):
        pl = l["patchline"]
        if (pl["source"][0], pl["source"][1],
                pl["destination"][0], pl["destination"][1]) == key:
            return i
    return -1


def _make_box(bid: str, spec: dict) -> dict:
    """构造一个对象。字段集与文件里已有的同类对象一致。"""
    mc = spec["maxclass"]
    box = {
        "id": bid,
        "maxclass": mc,
        "text": spec["text"],
        "numinlets": spec.get("numinlets", 1),
        "numoutlets": spec.get("numoutlets", 1),
        "outlettype": spec.get("outlettype", [""]),
        "patching_rect": spec.get("patching_rect", [40.0, 940.0, 90.0, 20.0]),
    }
    return {"box": box}


def main() -> None:
    doc = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    pt = doc["patcher"]
    fixes: list[str] = []

    idx = {b["box"]["id"]: b["box"] for b in pt["boxes"]}

    # ---- 1. poly~ 进出口数 ----
    for bo in idx.values():
        if str(bo.get("text", "")).startswith("poly~ TraneGrainVoice"):
            if (bo.get("numinlets"), bo.get("numoutlets")) != (1, 2):
                bo["numinlets"] = 1
                bo["numoutlets"] = 2
                bo["outlettype"] = ["signal", "signal"]
                fixes.append("poly~ TraneGrainVoice 改为 1进/2出")

    # ---- 2. snapshot~ 的 bang 必须在入口 0（若还留着 snapshot~）----
    for line in pt["lines"]:
        pl = line["patchline"]
        dst = pl["destination"]
        bo = idx.get(dst[0], {})
        if str(bo.get("text", "")) == "snapshot~" and dst[1] != 0:
            pl["destination"] = [dst[0], 0]
            fixes.append(f"snapshot~ 控制连线 入口{dst[1]} → 入口0")

    # ---- 3. 删连线 ----
    cut = 0
    for key in CUT_LINES:
        i = _find_line(pt["lines"], key)
        if i >= 0:
            pt["lines"].pop(i)
            cut += 1
    if cut:
        fixes.append(f"删除 {cut} 条错误连线")

    # ---- 4. 删除对象（连同挂在它们身上的连线）----
    gone = DELETE_BOXES & set(idx)
    if gone:
        pt["boxes"] = [b for b in pt["boxes"] if b["box"]["id"] not in gone]
        pt["lines"] = [
            l for l in pt["lines"]
            if l["patchline"]["source"][0] not in gone
            and l["patchline"]["destination"][0] not in gone
        ]
        idx = {b["box"]["id"]: b["box"] for b in pt["boxes"]}
        fixes.append(f"删除 {len(gone)} 个对象：{sorted(gone)}")

    # ---- 5. 就地改写对象 ----
    for bid, spec in REPURPOSE.items():
        bo = idx.get(bid)
        if bo is None:
            continue
        changed = []
        for k, v in spec.items():
            if bo.get(k) != v:
                bo[k] = v
                changed.append(k)
        if changed:
            fixes.append(f"{bid} 改写字段：{changed}")

    # ---- 6. 新增对象 ----
    for bid, spec in NEW_BOXES.items():
        if bid not in idx:
            box = _make_box(bid, spec)
            pt["boxes"].append(box)
            idx[bid] = box["box"]
            fixes.append(f"新增 {bid} = {spec['maxclass']} {spec['text']!r}")

    # ---- 7. 新增连线 ----
    added = 0
    for key in NEW_LINES:
        if _find_line(pt["lines"], key) < 0:
            pt["lines"].append({
                "patchline": {
                    "source": [key[0], key[1]],
                    "destination": [key[2], key[3]],
                }
            })
            added += 1
    if added:
        fixes.append(f"新增 {added} 条连线")

    # ---- 8. metro 去掉 @quantize ----
    bo93 = idx.get("obj-93")
    if bo93 is not None and "@quantize" in str(bo93.get("text", "")):
        bo93["text"] = "metro 16n"
        fixes.append("metro 去掉 @quantize（transport 停住时量化边界不到达，ARP 会静默不响）")

    # ---- 9. 重排 Presentation ----
    for bid, rect in LAYOUT.items():
        bo = idx.get(bid)
        if bo is None:
            continue
        bo["presentation"] = 1
        bo["presentation_rect"] = [float(v) for v in rect]
    fixes.append(f"重排 {len(LAYOUT)} 个 Presentation 对象（169px 面板内）")

    for bid in DROP_FROM_PRESENTATION:
        bo = idx.get(bid)
        if bo is not None and bo.get("presentation"):
            bo.pop("presentation", None)
            bo.pop("presentation_rect", None)
            fixes.append(f"{bid} 撤出 Presentation")

    for bid, text in REWRITE_TEXT.items():
        bo = idx.get(bid)
        if bo is not None and bo.get("text") != text:
            bo["text"] = text

    # ---- 10. 参数元数据（交 param_meta）----
    fixes.extend(param_meta.apply_parameter_metadata(pt))

    # ---- 11. 设备尺寸 ----
    pt["openrect"] = [0.0, 0.0, DEVICE_WIDTH, DEVICE_HEIGHT]
    pt["devicewidth"] = DEVICE_WIDTH
    pt["openinpresentation"] = 1
    fixes.append(
        f"openrect = 0,0,{DEVICE_WIDTH:.0f},{DEVICE_HEIGHT:.0f}；"
        f"devicewidth = {DEVICE_WIDTH:.0f}"
    )

    # ---- 12. 画布留足空间（不影响 Presentation）----
    xs = [b["box"]["patching_rect"][0] + b["box"]["patching_rect"][2] for b in pt["boxes"]]
    ys = [b["box"]["patching_rect"][1] + b["box"]["patching_rect"][3] for b in pt["boxes"]]
    pt["rect"] = [0.0, 0.0, max(1600.0, max(xs) + 40), max(900.0, max(ys) + 40)]

    PATCH_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已修复 {len(fixes)} 项：")
    for f in fixes:
        print(f"  · {f}")


if __name__ == "__main__":
    main()
