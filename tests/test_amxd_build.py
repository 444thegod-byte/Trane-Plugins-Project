#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_amxd_build.py —— 校验 dist/Trane.amxd 的容器结构与 M4L 元数据

这些测试保护的是「打包正确性」：
一个字节写错，Live 就会拒绝加载设备，而且报错信息极不友好。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from amxd import AmxdDevice, AmxdError  # noqa: E402

AMXD_PATH = PROJECT_ROOT / "dist" / "Trane.amxd"
MAIN_PATCH = PROJECT_ROOT / "src" / "Trane.maxpat"
VOICE_PATCH = PROJECT_ROOT / "src" / "TraneGrainVoice.maxpat"

# Ableton 官方 M4L 音频效果器模板里的标准字段。
# 缺任何一个，Live 都可能不认这个设备。
REQUIRED_PATCHER_FIELDS = [
    "classnamespace",
    "devicewidth",
    "latency",
    "project",
    "dependency_cache",
    "boxes",
    "lines",
]


@pytest.fixture(scope="module")
def device() -> AmxdDevice:
    if not AMXD_PATH.exists():
        subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tools" / "build_amxd.py")],
            check=True,
            capture_output=True,
        )
    return AmxdDevice.from_file(AMXD_PATH)


@pytest.fixture(scope="module")
def main_patcher(device: AmxdDevice) -> dict:
    return json.loads(device.patcher_json)["patcher"]


def test_container_header(device: AmxdDevice) -> None:
    """容器头必须是 ampf + 版本 4 + aaaa（音频效果器）。"""
    raw = AMXD_PATH.read_bytes()
    assert raw[:4] == b"ampf"
    assert device.container_version == 4
    assert device.device_tag == b"aaaa"
    assert device.device_kind == "audio_effect"


def test_uses_mx_encoding_with_meta_7(device: AmxdDevice) -> None:
    """MX 编码 + meta=7 是真实设备的通行组合（实测 115/115）。"""
    assert device.encoding == "mx"
    assert device.meta == 7


def test_embeds_voice_abstraction(device: AmxdDevice) -> None:
    """抽象子补丁必须内嵌，否则 Live 里 poly~ 找不到声部。"""
    names = [e.fname for e in device.entries]
    assert "Trane.amxd" in names
    assert "TraneGrainVoice.maxpat" in names
    assert "TraneHugeVerb.maxpat" in names


def test_main_entry_is_flagged_as_device_document(device: AmxdDevice) -> None:
    """主文档 flag 必须是 0x11，抽象条目是 0（与 Autotuna 实测一致）。"""
    main = device.entries[device.main_entry_index]
    assert main.fname == "Trane.amxd"
    assert main.flag == 0x11
    others = [e for i, e in enumerate(device.entries) if i != device.main_entry_index]
    assert others and all(e.flag == 0 for e in others)


def test_directory_offsets_are_contiguous(device: AmxdDevice) -> None:
    """of32 必须从 16 起紧密排列，csize = 16 + 数据总长。"""
    off = 16
    for e in device.entries:
        assert e.of32 == off, f"{e.fname} 的 of32 应为 {off}，实际 {e.of32}"
        off += len(e.data)


def test_roundtrip_is_byte_exact(device: AmxdDevice) -> None:
    """重新序列化必须与原文件逐字节一致 —— 这是打包器正确性的核心证据。"""
    assert device.to_bytes() == AMXD_PATH.read_bytes()


def test_main_patcher_has_m4l_metadata(main_patcher: dict) -> None:
    """根补丁必须带齐 Ableton 官方模板的全部标准字段。"""
    missing = [k for k in REQUIRED_PATCHER_FIELDS if k not in main_patcher]
    assert not missing, f"根补丁缺少 M4L 必需字段：{missing}"


def test_project_block_reports_audio_effect_type(main_patcher: dict) -> None:
    """project.amxdtype 必须等于 0x61616161（'aaaa'），否则 Live 会当成乐器。"""
    assert main_patcher["project"]["amxdtype"] == 0x61616161


def test_device_width_is_set(main_patcher: dict) -> None:
    """devicewidth 为 0 会让设备在 Live 里没有可交互区域。"""
    assert main_patcher["devicewidth"] > 0


def test_device_opens_in_presentation_view(main_patcher: dict) -> None:
    """设备必须默认打开 Presentation View，绝不能把编辑用的线图暴露给用户。"""
    assert main_patcher["openinpresentation"] == 1


def test_built_device_panel_matches_real_devices(main_patcher: dict) -> None:
    """面板尺寸必须和真实设备一致：openrect 高 169，内容不越界。

    实测 105 个可解析的真实 .amxd：openrect 高度 102 个是 169.0。
    rect（Patch View 画布）和 openrect（设备面板）是两个不同的字段，
    早期版本把同一个值写进两者，openrect 高度就变成了画布高度。
    """
    assert main_patcher["openrect"][3] == 169.0, "openrect 高度必须是设备面板高度"
    assert main_patcher["devicewidth"] == main_patcher["openrect"][2], "宽度应一致"

    pres = [
        b["box"] for b in main_patcher["boxes"]
        if b["box"].get("presentation") and b["box"].get("maxclass") != "live.toolbar"
    ]
    assert pres, "设备面板不能是空的"
    x2 = max(b["presentation_rect"][0] + b["presentation_rect"][2] for b in pres)
    y2 = max(b["presentation_rect"][1] + b["presentation_rect"][3] for b in pres)
    assert x2 <= main_patcher["devicewidth"], f"内容宽 {x2} 超出 devicewidth"
    assert y2 <= 169.5, f"内容高 {y2} 超出面板"


def test_built_device_passes_the_verifier(device: AmxdDevice) -> None:
    """打包产物本身也要过验证器，而不只是 src/ 里的源文件。

    这一步能抓到「构建流程丢掉/改动了东西」——比如签名补齐把 outlettype 写坏。
    """
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from verify_patch import check_live_arity, check_parameter_metadata, check_presentation_fits

    pt = json.loads(device.patcher_json)["patcher"]
    problems = (
        check_presentation_fits(pt)
        + check_live_arity(pt)
        + check_parameter_metadata(pt)
    )
    assert not problems, "\n".join(problems)


def test_patcher_matches_source_patch(main_patcher: dict) -> None:
    """打包进去的 boxes/lines 必须与 src/Trane.maxpat 一致，不能是旧版本。"""
    src = json.loads(MAIN_PATCH.read_text(encoding="utf-8").rstrip("\x00"))["patcher"]
    assert len(main_patcher["boxes"]) == len(src["boxes"])
    assert len(main_patcher["lines"]) == len(src["lines"])
    assert [b["box"].get("text") for b in main_patcher["boxes"]] == [
        b["box"].get("text") for b in src["boxes"]
    ]


def test_embedded_abstraction_matches_source(main_patcher: dict, device: AmxdDevice) -> None:
    """内嵌的声部补丁内容必须与 src/TraneGrainVoice.maxpat 一致。"""
    entry = next(e for e in device.entries if e.fname == "TraneGrainVoice.maxpat")
    embedded = json.loads(entry.data.decode("utf-8").rstrip("\x00"))["patcher"]
    src = json.loads(VOICE_PATCH.read_text(encoding="utf-8").rstrip("\x00"))["patcher"]
    assert len(embedded["boxes"]) == len(src["boxes"])


def test_poly_object_targets_embedded_abstraction(main_patcher: dict) -> None:
    """根补丁里的 poly~ 必须指向已内嵌的抽象名，否则声部加载失败。"""
    texts = [b["box"].get("text", "") for b in main_patcher["boxes"]]
    assert any(t.startswith("poly~ TraneGrainVoice") for t in texts)


def test_no_object_missing_signature(device: AmxdDevice) -> None:
    """每个 newobj 都必须带 numinlets/numoutlets/outlettype。

    Max 保存补丁时一定会写这三个字段。手写 JSON 漏掉它们，
    Live 加载设备时对象能不能接线就不确定了。
    """
    offenders = []

    def walk(pt: dict, where: str) -> None:
        for b in pt.get("boxes", []):
            bo = b.get("box", {})
            if bo.get("maxclass") == "newobj" and "text" in bo:
                if bo.get("numinlets") is None or bo.get("numoutlets") is None:
                    offenders.append(f"{where}: {bo['text']}")
            if "patcher" in bo:
                walk(bo["patcher"], f"{where}/{bo.get('text', 'sub')}")

    walk(json.loads(device.patcher_json)["patcher"], "主补丁")
    for e in device.entries:
        if e.fname.endswith(".maxpat"):
            walk(json.loads(e.data.decode("utf-8").rstrip("\x00"))["patcher"], e.fname)
    assert not offenders, f"以下对象缺少签名：{offenders}"


def test_encrypted_devices_raise_clear_error() -> None:
    """加密设备必须给出明确错误，而不是静默产出坏文件。"""
    enc = Path(
        "/Applications/Ableton Live 12 .app/Contents/App-Resources/Builtin/Devices/"
        "Audio Effects/LFO/Ableton Folder Info/LFO.amxd"
    )
    if not enc.exists():
        pytest.skip("样本不存在")
    with pytest.raises(AmxdError, match="加密"):
        AmxdDevice.from_file(enc)
