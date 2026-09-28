#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_amxd.py —— 把 src/*.maxpat 打包成可直接放进 Live 的 dist/Trane.amxd

做法
----
不自己臆造 M4L 的补丁元数据，而是**从 Ableton 官方模板继承骨架**：

    模板：/Applications/Ableton Live 12 .app/Contents/App-Resources/Misc/Max Devices/Max Audio Effect.amxd

把模板 patcher 里的 boxes / lines 换成我们自己的，其余标准字段
（classnamespace / project / latency / dependency_cache / 工具栏可见性 ...）原样保留。
这样 Live 看到的元数据与它自己生成的设备完全一致。

容器用 MX 编码（meta=7），因为 .amxd 里的抽象子补丁必须作为**独立的 JSON 条目**内嵌。
对象名 `TraneGrainVoice` 对应条目文件名 `TraneGrainVoice.maxpat`，
这一约定由 Autotuna 等真实设备实测确认（对象 `M4L.bal2~` ↔ 条目 `M4L.bal2~.maxpat`）。

用法
----
    python3 tools/build_amxd.py            # 输出 dist/Trane.amxd
    python3 tools/build_amxd.py --install  # 同时安装到 User Library/Max Devices
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from amxd import AmxdDevice, DirEntry, FLAG_JSON, now_mac_epoch  # noqa: E402
from patchbuild import ensure_signatures  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
DIST = PROJECT_ROOT / "dist"

TEMPLATE = Path(
    "/Applications/Ableton Live 12 .app/Contents/App-Resources/Misc/Max Devices/Max Audio Effect.amxd"
)
FALLBACK_TEMPLATE = Path(
    "/Applications/Ableton Live 12 .app/Contents/App-Resources/Misc/Max Devices/Max Instrument.amxd"
)

DEVICE_NAME = "Träne"
DEVICE_FILE = "Trane.amxd"
ABSTRACTS = ["TraneGrainVoice", "TraneHugeVerb"]

# M4L 音频效果器的设备面板尺寸。
# 实测 105 个可解析的真实 .amxd：openrect 高度 102 个是 169.0。
# 宽度由 devicewidth 决定（内容右缘一般留 10–18px 边距）。
DEVICE_WIDTH = 650.0
DEVICE_HEIGHT = 169.0


def load_patcher(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8").rstrip("\x00").rstrip("\n")
    return json.loads(text)["patcher"]


def template_skeleton() -> dict:
    """取官方 M4L 音频效果器模板的 patcher 骨架。"""
    tpl = TEMPLATE if TEMPLATE.exists() else FALLBACK_TEMPLATE
    if not tpl.exists():
        raise SystemExit(f"找不到 M4L 模板：{TEMPLATE}")
    dev = AmxdDevice.from_file(tpl)
    return copy.deepcopy(json.loads(dev.patcher_json)["patcher"])


def make_doc(
    skeleton: dict,
    boxes: list,
    lines: list,
    *,
    rect: list[float] | None = None,
    openrect: list[float] | None = None,
    devicewidth: float | None = None,
    description: str = "",
) -> str:
    pt = copy.deepcopy(skeleton)
    pt["boxes"] = boxes
    pt["lines"] = lines
    # 这是设备给用户看的默认界面。官方空模板默认为 0；若不覆盖，
    # Live 会把编辑用的 Patch View（对象和连线）当成设备面板显示。
    pt["openinpresentation"] = 1
    # 补齐对象签名：缺 numinlets/numoutlets 会让 Live 加载时行为不确定
    fixed = ensure_signatures(pt)
    if fixed:
        print(f"  [签名补齐] {len(fixed)} 个对象")
    # rect 是 Patch View 的画布，openrect 是设备面板的尺寸 —— 两者不是一回事。
    # 早期版本把同一个值写进这两个字段，结果 openrect 的高度变成了画布高度（900），
    # 而真实设备 105/105 都是 [0, 0, W, 169]。
    if rect is not None:
        pt["rect"] = rect
    if openrect is not None:
        pt["openrect"] = openrect
    if devicewidth is not None:
        pt["devicewidth"] = devicewidth
    pt["description"] = description
    # 记录本次构建时间（Mac 纪元）
    if isinstance(pt.get("project"), dict):
        pt["project"]["modificationdate"] = now_mac_epoch()
        pt["project"]["creationdate"] = pt["project"].get("creationdate") or now_mac_epoch()
    return json.dumps({"patcher": pt}, ensure_ascii=False, indent=1)


def build(install: bool = False) -> Path:
    skeleton = template_skeleton()
    panel = [0.0, 0.0, DEVICE_WIDTH, DEVICE_HEIGHT]

    main = load_patcher(SRC / "Trane.maxpat")
    main_doc = make_doc(
        skeleton,
        main["boxes"],
        main["lines"],
        rect=main.get("rect", [0.0, 0.0, 1600.0, 900.0]),
        openrect=panel,
        devicewidth=DEVICE_WIDTH,
        description=f"{DEVICE_NAME} — granular / freeze / audio-arp sound sculptor",
    )

    dev = AmxdDevice()
    dev.device_tag = b"aaaa"
    dev.encoding = "mx"
    dev.meta = 7
    dev.patcher_json = main_doc
    dev.entries = [
        DirEntry(
            type="JSON",
            fname=DEVICE_FILE,
            flag=FLAG_JSON,
            mdat=now_mac_epoch(),
            data=b"",
        )
    ]
    dev.main_entry_index = 0

    # 内嵌抽象子补丁：对象名 TraneGrainVoice ↔ 条目 TraneGrainVoice.maxpat
    for name in ABSTRACTS:
        abs_path = SRC / f"{name}.maxpat"
        if not abs_path.exists():
            raise SystemExit(f"缺少抽象补丁：{abs_path}")
        abs_pt = load_patcher(abs_path)
        abs_doc = make_doc(
            skeleton,
            abs_pt["boxes"],
            abs_pt["lines"],
            rect=abs_pt.get("rect", [0.0, 0.0, 820.0, 500.0]),
            description=f"{name} — 单个粒子声部",
        )
        dev.entries.append(
            DirEntry(
                type="JSON",
                fname=f"{name}.maxpat",
                flag=0,
                mdat=now_mac_epoch(),
                data=abs_doc.encode("utf-8").rstrip(b"\n") + b"\n\x00",
            )
        )

    DIST.mkdir(parents=True, exist_ok=True)
    out = dev.write(DIST / DEVICE_FILE)
    print(f"已生成 {out}  ({out.stat().st_size} 字节)")
    print(dev.summary())

    if install:
        target_dir = Path.home() / "Music/Ableton/User Library/Max Devices"
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / DEVICE_FILE
        shutil.copy2(out, dest)
        print(f"已安装到 {dest}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 Träne 为 .amxd")
    ap.add_argument("--install", action="store_true", help="同时安装到 User Library/Max Devices")
    args = ap.parse_args()
    build(install=args.install)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
