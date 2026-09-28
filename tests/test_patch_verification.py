#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_patch_verification.py —— 把「设备能不能跑起来」变成硬性回归门槛

Max 需要 iLok 授权与 Java，无法无界面启动，所以不能真正加载补丁。
但下面这些是可以在静态层面确凿查出来的、也是最常导致「拖进 Live 没反应」的原因：

  · 对象名拼错 / 该对象在 M4L 运行时里不存在
  · poly~ / 抽象的进出口数和它调用的抽象对不上
  · live.* 控件没接任何东西
  · plugin~ 到 plugout~ 的音频链断开
  · Presentation 越出 169px 的设备面板（控件看不见）
  · live.* 控件的进出口数与官方 refpage 不一致
  · live.menu / live.tab 缺 parameter_enum（菜单是空的，选不了）
  · 连线指向不存在的入口/出口
  · record~ 的入口数与声道数不匹配（录音终点静默失效）
  · groove~ 缺 setloop / startloop（Freeze 点了不动）
  · 控件与算式争抢同一个入口

这些断言一旦变红，说明设备会在 Live 里表现异常，必须先修好再打包。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from verify_patch import (  # noqa: E402
    DEVICE_HEIGHT,
    box_index,
    check_abstraction_arity,
    check_control_value_not_clobbered,
    check_controls_are_wired,
    check_groove_has_loop_messages,
    check_lines_within_inlets,
    check_lines_within_outlets,
    check_live_arity,
    check_menu_items_come_from_enum,
    check_objects_exist,
    check_openrect,
    check_parameter_metadata,
    check_poly_arity,
    check_presentation_fits,
    check_presentation_no_overlap,
    check_record_inlet_count,
    check_record_loop_window,
    check_signal_path,
    check_snapshot_bang_inlet,
    check_trigger_order_for_poly_target,
    load_object_db,
    read_patcher,
    verify,
)

SRC = PROJECT_ROOT / "src"
ROOT_PATCH = SRC / "Trane.maxpat"
ABSTRACTS = [SRC / "TraneGrainVoice.maxpat", SRC / "TraneHugeVerb.maxpat"]
ALL_PATCHES = [ROOT_PATCH, *ABSTRACTS]


@pytest.fixture(scope="module")
def object_db() -> set[str]:
    return load_object_db()


@pytest.fixture(scope="module")
def root_patcher() -> dict:
    assert ROOT_PATCH.exists(), f"缺少根补丁：{ROOT_PATCH}"
    return read_patcher(ROOT_PATCH)


@pytest.fixture(scope="module")
def abstract_patchers() -> dict[str, dict]:
    out = {}
    for p in ABSTRACTS:
        assert p.exists(), f"缺少抽象补丁：{p}"
        out[p.stem] = read_patcher(p)
    return out


# ----------------------------------------------------------------------
# 对象存在性
# ----------------------------------------------------------------------


@pytest.mark.parametrize("patch", ALL_PATCHES, ids=lambda p: p.name)
def test_every_object_exists_in_max_runtime(
    patch: Path, object_db: set[str], abstract_patchers: dict[str, dict]
) -> None:
    """每个对象名都必须能在 M4L 运行时里解析到，否则那一块永远是死的。"""
    pt = read_patcher(patch)
    problems = check_objects_exist(pt, object_db, set(abstract_patchers))
    assert not problems, "\n".join(problems)


# ----------------------------------------------------------------------
# 结构正确性
# ----------------------------------------------------------------------


def test_poly_arity_matches_abstraction(
    root_patcher: dict, abstract_patchers: dict[str, dict]
) -> None:
    """poly~ 的进出口数必须等于抽象自身的进出口数，否则部分出口无效。"""
    problems = check_poly_arity(root_patcher, abstract_patchers)
    assert not problems, "\n".join(problems)


def test_abstraction_arity_matches_definition(
    root_patcher: dict, abstract_patchers: dict[str, dict]
) -> None:
    """直接以抽象名实例化的对象（如 TraneHugeVerb）进出口数也要一致。"""
    problems = check_abstraction_arity(root_patcher, abstract_patchers)
    assert not problems, "\n".join(problems)


def test_lines_point_at_existing_inlets_and_outlets(root_patcher: dict) -> None:
    """连线不能指向对象不存在的入口/出口，否则那条线是静默失效的。"""
    problems = check_lines_within_outlets(root_patcher) + check_lines_within_inlets(root_patcher)
    assert not problems, "\n".join(problems)


def test_record_inlet_count_matches_channel_count(root_patcher: dict) -> None:
    """record~ 的入口数 = 声道数 + 2；少一个的话录音终点入口就不存在。"""
    problems = check_record_inlet_count(root_patcher)
    assert not problems, "\n".join(problems)


def test_record_runs_in_loop_mode_with_loop_length_window(root_patcher: dict) -> None:
    """record~ 必须开 loop 模式，且录音终点跟随 Loop 旋钮。"""
    problems = check_record_loop_window(root_patcher)
    assert not problems, "\n".join(problems)


def test_groove_receives_setloop_and_startloop(root_patcher: dict) -> None:
    """groove~ 少了 setloop 循环窗口不对；少了 startloop 就永远不播放。"""
    problems = check_groove_has_loop_messages(root_patcher)
    assert not problems, "\n".join(problems)


def test_control_value_is_not_clobbered_by_a_computation(root_patcher: dict) -> None:
    """live.* 控件不能和算式争抢同一个入口 —— 否则控件一动，算出来的值就没了。"""
    problems = check_control_value_not_clobbered(root_patcher)
    assert not problems, "\n".join(problems)


# ----------------------------------------------------------------------
# 参数元数据
# ----------------------------------------------------------------------


def test_live_object_arity_matches_refpage(root_patcher: dict) -> None:
    """live.* 控件的进出口数必须与官方 refpage 一致。"""
    problems = check_live_arity(root_patcher)
    assert not problems, "\n".join(problems)


def test_live_controls_have_live_parameter_metadata(root_patcher: dict) -> None:
    """没有参数元数据 → Live 参数列表里是「未命名参数」，菜单/标签页是空的。"""
    problems = check_parameter_metadata(root_patcher)
    assert not problems, "\n".join(problems)


def test_menu_and_tab_items_come_from_parameter_enum(root_patcher: dict) -> None:
    """条目必须来自 parameter_enum（真实设备 53/53 都是这么做的）。"""
    problems = check_menu_items_come_from_enum(root_patcher)
    assert not problems, "\n".join(problems)


def test_whole_verifier_is_clean() -> None:
    """总闸：验证器对全部补丁必须 0 问题。"""
    report = verify(ALL_PATCHES, root=ROOT_PATCH)
    flat = [f"{name}: {p}" for name, problems in report.items() for p in problems]
    assert not flat, "\n".join(flat)


def test_snapshot_bang_is_on_left_inlet(root_patcher: dict) -> None:
    """snapshot~ 靠左入口的 bang 才会上报数值；接在右入口则 Freeze 永远不触发。"""
    problems = check_snapshot_bang_inlet(root_patcher)
    assert not problems, "\n".join(problems)


def test_arp_sets_target_before_trigger(root_patcher: dict) -> None:
    """t b b 从右往左触发：target 路径必须挂在更高的出口上，先设声部再发 trigger。"""
    problems = check_trigger_order_for_poly_target(root_patcher)
    assert not problems, "\n".join(problems)


# ----------------------------------------------------------------------
# 可用性
# ----------------------------------------------------------------------


def test_all_live_controls_are_wired(root_patcher: dict) -> None:
    """每个 live.* 控件都要有输出连线，否则用户转它没反应。"""
    problems = check_controls_are_wired(root_patcher)
    assert not problems, "\n".join(problems)


def test_audio_path_reaches_live_output(root_patcher: dict) -> None:
    """plugin~ 必须能走到 plugout~，且没有孤立的信号对象。"""
    problems = check_signal_path(root_patcher)
    assert not problems, "\n".join(problems)


# ----------------------------------------------------------------------
# 设备面板
# ----------------------------------------------------------------------


def test_presentation_fits_device_panel(root_patcher: dict) -> None:
    """M4L 音频效果器面板固定 169px 高，超出部分在 Live 里根本看不见。"""
    problems = check_presentation_fits(root_patcher)
    assert not problems, "\n".join(problems)


def test_openrect_and_devicewidth_are_consistent(root_patcher: dict) -> None:
    """openrect 高度必须是 169；devicewidth 不能小于内容宽度，也不能贴边。"""
    problems = check_openrect(root_patcher)
    assert not problems, "\n".join(problems)


def test_presentation_has_no_overlapping_objects(root_patcher: dict) -> None:
    """comment 在 Presentation 里有底色，压住控件就会把控件遮住。"""
    problems = check_presentation_no_overlap(root_patcher)
    assert not problems, "\n".join(problems)


def test_device_opens_in_presentation_view(root_patcher: dict) -> None:
    """设备必须默认打开 Presentation View，不能把编辑线图暴露给用户。"""
    assert root_patcher["openinpresentation"] == 1


def test_panel_actually_uses_the_full_height(root_patcher: dict) -> None:
    """面板不能被浪费：控件要真正铺满可用高度，而不是挤在顶部一小条。"""
    pres = [b["box"] for b in root_patcher["boxes"] if b["box"].get("presentation")]
    lowest = max(b["presentation_rect"][1] + b["presentation_rect"][3] for b in pres)
    assert lowest > DEVICE_HEIGHT * 0.85, f"Presentation 只用到 y={lowest:.0f}，面板高度被浪费"


def test_every_presentation_control_has_a_label(root_patcher: dict) -> None:
    """每个可见控件都要有文字标签，否则用户不知道旋钮是干什么的。"""
    idx = box_index(root_patcher)
    labels = [
        b["box"]
        for b in root_patcher["boxes"]
        if b["box"].get("presentation") and b["box"].get("maxclass") == "comment"
    ]
    label_rects = [b["presentation_rect"] for b in labels]
    unlabeled = []
    for bid, bo in idx.items():
        if not bo.get("presentation"):
            continue
        if not str(bo.get("maxclass", "")).startswith("live."):
            continue
        r = bo["presentation_rect"]
        # 标签在控件正下方，或在控件右侧（开关类控件用右侧标签更省纵向空间）
        below = lambda lr: (  # noqa: E731
            lr[1] >= r[1] + r[3] - 2
            and lr[1] <= r[1] + r[3] + 26
            and lr[0] < r[0] + r[2]
            and lr[0] + lr[2] > r[0]
        )
        right = lambda lr: (  # noqa: E731
            lr[0] >= r[0] + r[2] - 2
            and lr[0] <= r[0] + r[2] + 60
            and lr[1] < r[1] + r[3]
            and lr[1] + lr[3] > r[1]
        )
        if not any(below(lr) or right(lr) for lr in label_rects):
            unlabeled.append(bo.get("varname") or bo.get("maxclass"))
    assert not unlabeled, f"以下控件没有标签：{unlabeled}"
