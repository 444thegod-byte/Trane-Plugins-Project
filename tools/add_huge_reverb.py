#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Huge Space（TraneHugeVerb）接入 Träne 主补丁。"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = PROJECT_ROOT / "src" / "Trane.maxpat"


def dial(obj_id: str, varname: str, x: float, y: float, label: str, initial: float) -> dict:
    """创建 0–100 的 Live 参数旋钮（可以直接 MIDI Map）。"""
    return {
        "box": {
            "id": obj_id,
            "maxclass": "live.dial",
            "varname": varname,
            "numinlets": 1,
            "numoutlets": 1,
            "outlettype": ["float"],
            "patching_rect": [900.0 + x, 90.0 + y, 45.0, 45.0],
            "presentation": 1,
            "presentation_rect": [900.0 + x, 75.0 + y, 45.0, 45.0],
            "parameter_enable": 1,
            "saved_attribute_attributes": {
                "valueof": {
                    "parameter_mmin": 0.0,
                    "parameter_mmax": 100.0,
                    "parameter_initial": [initial],
                    "parameter_initial_enable": 1,
                    "parameter_shortname": label.title(),
                    "parameter_longname": f"Huge Space {label.title()}",
                    "parameter_type": 0,
                    "parameter_unitstyle": 0,
                }
            },
        }
    }


def comment(obj_id: str, text: str, x: float, y: float, width: float) -> dict:
    return {
        "box": {
            "id": obj_id,
            "maxclass": "comment",
            "text": text,
            "patching_rect": [900.0 + x, 55.0 + y, width, 20.0],
            "presentation": 1,
            "presentation_rect": [900.0 + x, 20.0 + y, width, 20.0],
        }
    }


def newobj(obj_id: str, text: str, x: float, y: float, nin: int, nout: int, types: list[str]) -> dict:
    return {
        "box": {
            "id": obj_id,
            "maxclass": "newobj",
            "text": text,
            "numinlets": nin,
            "numoutlets": nout,
            "outlettype": types,
            "patching_rect": [x, y, 120.0, 22.0],
        }
    }


def line(src: str, outlet: int, dst: str, inlet: int) -> dict:
    return {"patchline": {"source": [src, outlet], "destination": [dst, inlet]}}


def main() -> None:
    doc = json.loads(PATCH_PATH.read_text(encoding="utf-8"))
    pt = doc["patcher"]
    boxes = pt["boxes"]
    lines = pt["lines"]

    # 可重复运行：已经插入过则无操作。
    if any(b["box"].get("text") == "TraneHugeVerb" for b in boxes):
        print("Huge Space 已存在，未重复插入。")
        return

    # Presentation 面板：保持 Ableton 原生的灰阶控件，不加拟物化装饰。
    boxes.extend([
        comment("obj-105", "HUGE SPACE", 0.0, 0.0, 160.0),
        comment("obj-106", "8s+ feedback plate", 0.0, 22.0, 180.0),
        dial("obj-107", "verb_mix", 0.0, 35.0, "Mix", 55.0),
        comment("obj-108", "MIX", 0.0, 120.0, 45.0),
        dial("obj-109", "verb_size", 62.0, 35.0, "Space", 100.0),
        comment("obj-110", "SPACE", 58.0, 120.0, 58.0),
        dial("obj-111", "verb_decay", 124.0, 35.0, "Tail", 100.0),
        comment("obj-112", "TAIL", 128.0, 120.0, 45.0),
        dial("obj-113", "verb_damping", 0.0, 138.0, "Damp", 35.0),
        comment("obj-114", "DAMP", 0.0, 223.0, 45.0),
        dial("obj-115", "verb_diffusion", 62.0, 138.0, "Diffuse", 100.0),
        comment("obj-116", "DIFFUSE", 52.0, 223.0, 70.0),

        # DSP，放在普通 Patching View 右侧；不显示在 Live 的 Presentation 面板。
        newobj("obj-117", "+~", 920.0, 500.0, 2, 1, ["signal"]),
        newobj("obj-118", "*~ 0.5", 1040.0, 500.0, 2, 1, ["signal"]),
        newobj("obj-119", "TraneHugeVerb", 1040.0, 550.0, 5, 2, ["signal", "signal"]),
        newobj("obj-120", "* 0.01", 930.0, 410.0, 2, 1, ["float"]),
        newobj("obj-121", "* 1.27", 1020.0, 410.0, 2, 1, ["float"]),
        newobj("obj-122", "* 1.27", 1100.0, 410.0, 2, 1, ["float"]),
        newobj("obj-123", "* 1.27", 1180.0, 410.0, 2, 1, ["float"]),
        newobj("obj-124", "* 1.27", 1260.0, 410.0, 2, 1, ["float"]),
        newobj("obj-125", "*~", 920.0, 610.0, 2, 1, ["signal"]),
        newobj("obj-126", "*~", 1010.0, 610.0, 2, 1, ["signal"]),
        newobj("obj-127", "+~", 920.0, 670.0, 2, 1, ["signal"]),
        newobj("obj-128", "+~", 1010.0, 670.0, 2, 1, ["signal"]),
        comment("obj-129", "Huge Space: mono fold-down → 8s+ plate network → stereo wet return. The dry path stays untouched.", 900.0, 720.0, 680.0),
    ])

    # 1) dry L/R 合成 mono 发给 reverb；原干声仍从 obj-77 / obj-78 直接去后级。
    # 2) 反射返回的 L/R 按 MIX 叠加，最后才进原有双 limiter。
    lines.extend([
        line("obj-77", 0, "obj-117", 0),
        line("obj-78", 0, "obj-117", 1),
        line("obj-117", 0, "obj-118", 0),
        line("obj-118", 0, "obj-119", 0),

        line("obj-107", 0, "obj-120", 0),
        line("obj-120", 0, "obj-125", 1),
        line("obj-120", 0, "obj-126", 1),
        line("obj-109", 0, "obj-121", 0),
        line("obj-121", 0, "obj-119", 1),
        line("obj-111", 0, "obj-122", 0),
        line("obj-122", 0, "obj-119", 2),
        line("obj-113", 0, "obj-123", 0),
        line("obj-123", 0, "obj-119", 3),
        line("obj-115", 0, "obj-124", 0),
        line("obj-124", 0, "obj-119", 4),

        line("obj-119", 0, "obj-125", 0),
        line("obj-119", 1, "obj-126", 0),
        line("obj-77", 0, "obj-127", 0),
        line("obj-125", 0, "obj-127", 1),
        line("obj-78", 0, "obj-128", 0),
        line("obj-126", 0, "obj-128", 1),
    ])

    # 原来 obj-77/78 直接接 limiter；替换成 dry + wet 混合后的总线。
    lines[:] = [
        entry for entry in lines
        if entry["patchline"] not in (
            {"source": ["obj-77", 0], "destination": ["obj-33", 0]},
            {"source": ["obj-78", 0], "destination": ["obj-34", 0]},
        )
    ]
    lines.extend([
        line("obj-127", 0, "obj-33", 0),
        line("obj-128", 0, "obj-34", 0),
    ])

    # 设备画布足够宽，Presentation 不受这个 rect 影响。
    pt["rect"] = [80.0, 80.0, 1560.0, 820.0]
    pt["openinpresentation"] = 1
    PATCH_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Huge Space 已插入 src/Trane.maxpat")


if __name__ == "__main__":
    main()
