#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
param_meta.py —— 给 live.* 控件补齐 Live 参数元数据

为什么需要这一步（全部由本机 127 个真实 .amxd 实测得出，不是推测）：

  · live.dial   514 个，**全部**带 parameter_shortname / parameter_longname /
                parameter_type / parameter_unitstyle
  · live.toggle  70 个，66 个带完整 valueof（shortname / type / mmax / enum）
  · live.menu    86 个，85 个带 valueof，且 85 个都有 parameter_enum
  · live.tab     49 个，48 个带 valueof，且 48 个都有 parameter_enum

menu / tab 的条目来源统计（已排除本项目自己的产物）：
    仅 parameter_enum : 53
    仅 append 消息    : 0
    两者都有          : 0
→ parameter_enum 是唯一正确做法；append 消息会与它重复，真实设备里一个都没有。

缺这些字段的后果（都是实打实会坏掉的）：
  1. live.menu 没有 parameter_enum → 菜单是空的、选不了 → ARP 看起来是坏的
  2. live.tab  没有 parameter_enum → MODE 选择器没有可见选项
  3. 没有 parameter_shortname → Live 参数列表里全是"未命名参数"，
     无法有意义地映射到 Macro、无法在自动化里辨认

parameter_unitstyle 的取值由实测反推（refpage 不记录这个内部属性）：
    0=整数  1=小数  2=毫秒  3=Hz  4=dB  5=百分比
    6=Pan   7=半音  8=音分  9=索引/MIDI

进出口数取自官方 refpage（docs/refpages/m4l-ref/*.maxref.xml）：
    live.dial   1进 2出 ["", "float"]
    live.toggle 1进 1出 [""]
    live.tab    1进 3出 ["", "", "float"]
    live.menu   1进 3出 ["", "", "float"]

live.tab 的 parameter_mmax 是「项数 - 1」（实测 Whale1.1 的 WetMode：
enum 三项、mmax=2、type=2、unitstyle=9）。
"""

from __future__ import annotations

from typing import Any

# ---- parameter_unitstyle 取值（实测反推）----
U_INT, U_FLOAT, U_MS, U_HZ, U_DB, U_PCT, U_PAN, U_SEMI, U_CENT, U_INDEX = range(10)

# ---- parameter_type ----
T_FLOAT, T_INT, T_ENUM = 0, 1, 2

# ---- 官方进出口规格（refpage 实测）----
ARITY: dict[str, tuple[int, int, list[str]]] = {
    "live.dial":   (1, 2, ["", "float"]),
    "live.toggle": (1, 1, [""]),
    "live.tab":    (1, 3, ["", "", "float"]),
    "live.menu":   (1, 3, ["", "", "float"]),
    "live.numbox": (1, 2, ["", "float"]),
    "live.slider": (1, 2, ["", "float"]),
    "live.text":   (1, 2, ["", ""]),
}

# ---- 每个控件的参数定义 ----
# kind      控件类型（用于取 ARITY）
# short     参数短名（Live 参数列表 / Macro 里显示的名字）
# long      参数长名
# unitstyle parameter_unitstyle
# rng       (mmin, mmax)；None 表示不写范围
# initial   初始值
# enum      离散标签表；有它 = parameter_type 2
# tip       annotation（Live 里悬停提示）
SPECS: dict[str, dict[str, Any]] = {
    # ---------- CAPTURE ----------
    "freeze_toggle": dict(
        kind="live.toggle", short="Freeze", long="Freeze",
        enum=["off", "on"], mmax=1.0, initial=0,
        tip="Latch the capture: stop recording and loop the window that was just recorded.",
    ),
    "reverse_toggle": dict(
        kind="live.toggle", short="Reverse", long="Reverse",
        enum=["off", "on"], mmax=1.0, initial=0,
        tip="Play the frozen window backwards.",
    ),
    "sound_mode": dict(
        kind="live.tab", short="Mode", long="Sound Mode",
        enum=["Clear", "Ruin"], initial=0,
        tip="Clear: clean granular. Ruin: hard-clipped, deconstructed.",
    ),
    "loop_length_ms": dict(
        kind="live.dial", short="Loop", long="Loop Length",
        unitstyle=U_MS, rng=(5.0, 500.0), initial=100.0,
        tip="Length of the frozen loop window, in milliseconds.",
    ),

    # ---------- GRAIN ----------
    "grain_toggle": dict(
        kind="live.toggle", short="Grain", long="Grain Enable",
        enum=["off", "on"], mmax=1.0, initial=0,
        tip="Enable the granular voice pool.",
    ),
    "grain_size_ms": dict(
        kind="live.dial", short="Size", long="Grain Size",
        unitstyle=U_MS, rng=(5.0, 500.0), initial=100.0,
        tip="Length of each grain, in milliseconds.",
    ),
    "grain_density": dict(
        kind="live.dial", short="Density", long="Grain Density",
        unitstyle=U_HZ, rng=(1.0, 20.0), initial=8.0,
        tip="Grains per second.",
    ),
    "grain_position": dict(
        kind="live.dial", short="Position", long="Grain Position",
        unitstyle=U_FLOAT, rng=(0.0, 1.0), initial=0.0,
        tip="Read position inside the capture, 0 = start, 1 = end.",
    ),
    "grain_spray": dict(
        kind="live.dial", short="Spray", long="Grain Spray",
        unitstyle=U_FLOAT, rng=(0.0, 1.0), initial=0.1,
        tip="Random spread around the read position.",
    ),
    "grain_rate": dict(
        kind="live.dial", short="Rate", long="Grain Rate",
        unitstyle=U_FLOAT, rng=(0.5, 2.0), initial=1.0,
        tip="Grain playback rate. 1 = original speed.",
    ),

    # ---------- ARP ----------
    "arp_toggle": dict(
        kind="live.toggle", short="Arp", long="Arpeggiator Enable",
        enum=["off", "on"], mmax=1.0, initial=0,
        tip="Start the audio arpeggiator. Steps retrigger the grain voices.",
    ),
    "arp_rate": dict(
        kind="live.menu", short="Rate", long="Arp Rate",
        enum=["1/16", "1/8", "1/4", "1/2"], initial=0,
        tip="Step rate of the arpeggiator, relative to Live's tempo.",
    ),
    "arp_probability": dict(
        kind="live.dial", short="Prob", long="Arp Probability",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=100.0,
        tip="Chance that a step actually fires, in percent.",
    ),
    "arp_steps": dict(
        kind="live.dial", short="Steps", long="Arp Steps",
        unitstyle=U_INT, type=T_INT, rng=(1.0, 16.0), initial=8.0,
        tip="Number of steps in the arpeggio cycle.",
    ),

    # ---------- HUGE SPACE ----------
    "verb_mix": dict(
        kind="live.dial", short="Mix", long="Space Mix",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=55.0,
        tip="Wet/dry blend of the Huge Space plate.",
    ),
    "verb_size": dict(
        kind="live.dial", short="Space", long="Space Size",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=70.0,
        tip="Size of the plate. Higher = longer early reflections.",
    ),
    "verb_decay": dict(
        kind="live.dial", short="Tail", long="Space Decay",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=80.0,
        tip="Decay time. At the top this tail runs 8 s and beyond.",
    ),
    "verb_damping": dict(
        kind="live.dial", short="Damp", long="Space Damping",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=40.0,
        tip="High-frequency damping inside the plate.",
    ),
    "verb_diffusion": dict(
        kind="live.dial", short="Diffuse", long="Space Diffusion",
        unitstyle=U_PCT, rng=(0.0, 100.0), initial=70.0,
        tip="Diffusion of the plate network. Higher = smoother tail.",
    ),
}


def _build_valueof(spec: dict[str, Any]) -> dict[str, Any]:
    """按 Max 官方原型的字段集构造 saved_attribute_attributes.valueof。"""
    enum = spec.get("enum")
    if enum is not None:
        ptype = T_ENUM
    else:
        ptype = spec.get("type", T_FLOAT)

    # tab 的 mmax 是「项数 - 1」
    if enum is not None and spec["kind"] == "live.tab":
        rng = (spec.get("rng") or (0.0, float(len(enum) - 1)))[0:1] + (float(len(enum) - 1),)
    else:
        rng = spec.get("rng")

    va: dict[str, Any] = {
        "parameter_annotation_name": "",
        "parameter_exponent": 1.0,
        "parameter_info": spec.get("tip", ""),
        "parameter_initial": [spec.get("initial", 0)],
        "parameter_initial_enable": 1,
        "parameter_invisible": 0,
        "parameter_linknames": 1,
        "parameter_longname": spec["long"],
        "parameter_modmax": 127.0,
        "parameter_modmin": 0.0,
        "parameter_modmode": 0,
        "parameter_order": 0,
        "parameter_shortname": spec["short"],
        "parameter_speedlim": 0,
        "parameter_steps": 0,
        "parameter_type": ptype,
        "parameter_units": "",
    }
    if enum is not None:
        va["parameter_enum"] = list(enum)
        if spec["kind"] == "live.toggle":
            va["parameter_mmax"] = 1.0
    if rng is not None:
        va["parameter_mmin"], va["parameter_mmax"] = float(rng[0]), float(rng[1])
    if "unitstyle" in spec:
        va["parameter_unitstyle"] = spec["unitstyle"]
    elif enum is not None and spec["kind"] in ("live.tab",):
        # 实测：带枚举的 live.tab 用 unitstyle 9（索引）
        va["parameter_unitstyle"] = U_INDEX
    return dict(sorted(va.items()))


def apply_parameter_metadata(patcher: dict) -> list[str]:
    """就地补齐主补丁里所有 live.* 控件的参数元数据与进出口数。可重复运行。"""
    fixes: list[str] = []

    for box in patcher.get("boxes", []):
        bo = box.get("box")
        if not isinstance(bo, dict):
            continue
        mc = bo.get("maxclass", "")
        if not mc.startswith("live."):
            continue

        # 1) 进出口数对齐官方 refpage
        arity = ARITY.get(mc)
        if arity is not None:
            ni, no, ot = arity
            cur = (bo.get("numinlets"), bo.get("numoutlets"), bo.get("outlettype"))
            if cur != (ni, no, ot):
                bo["numinlets"] = ni
                bo["numoutlets"] = no
                bo["outlettype"] = list(ot)
                fixes.append(f'{bo["id"]} {mc} 进出口数 → {ni}进{no}出')

        # 2) 参数元数据
        vn = bo.get("varname")
        spec = SPECS.get(vn) if vn else None
        if spec is None:
            continue
        if spec["kind"] != mc:
            fixes.append(f'{bo["id"]} varname={vn} 的类型是 {mc}，但规格写的是 {spec["kind"]}')
            continue

        bo["parameter_enable"] = 1
        bo["annotation"] = spec.get("tip", "")

        want = _build_valueof(spec)
        have = (bo.get("saved_attribute_attributes") or {}).get("valueof") or {}
        if have != want:
            bo["saved_attribute_attributes"] = {"valueof": want}
            fixes.append(f'{bo["id"]} {vn} 参数元数据（{spec["short"]}）')

    return fixes


def missing_metadata(patcher: dict) -> list[str]:
    """返回仍然缺少必要参数元数据的控件描述，供验证器使用。"""
    problems: list[str] = []
    for box in patcher.get("boxes", []):
        bo = box.get("box")
        if not isinstance(bo, dict):
            continue
        mc = bo.get("maxclass", "")
        if mc not in ARITY:
            continue
        vn = bo.get("varname")
        va = (bo.get("saved_attribute_attributes") or {}).get("valueof") or {}
        if not bo.get("parameter_enable"):
            problems.append(f'{bo["id"]} {mc}[{vn}] 未启用 parameter_enable')
        if not va.get("parameter_shortname"):
            problems.append(f'{bo["id"]} {mc}[{vn}] 缺 parameter_shortname')
        if mc in ("live.tab", "live.menu") and not va.get("parameter_enum"):
            problems.append(f'{bo["id"]} {mc}[{vn}] 缺 parameter_enum —— 菜单/标签页会是空的')
        if mc == "live.dial" and "parameter_mmax" not in va:
            problems.append(f'{bo["id"]} live.dial[{vn}] 缺 parameter_mmax')
    return problems


def arity_problems(patcher: dict) -> list[str]:
    """进出口数与官方 refpage 不一致的控件。"""
    problems: list[str] = []
    for box in patcher.get("boxes", []):
        bo = box.get("box")
        if not isinstance(bo, dict):
            continue
        mc = bo.get("maxclass", "")
        arity = ARITY.get(mc)
        if arity is None:
            continue
        ni, no, ot = arity
        if bo.get("numinlets") != ni or bo.get("numoutlets") != no:
            problems.append(
                f'{bo["id"]} {mc} 声明 {bo.get("numinlets")}进{bo.get("numoutlets")}出，'
                f"官方是 {ni}进{no}出"
            )
        elif list(bo.get("outlettype") or []) != ot:
            problems.append(
                f'{bo["id"]} {mc} outlettype={bo.get("outlettype")}，官方是 {ot}'
            )
    return problems
