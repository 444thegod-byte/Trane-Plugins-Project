"""Freeze DSP 回归测试。

这是 VST3 转向的核心收益：Max for Live 依赖 iLok + Java，我无法在本机运行，
只能静态验证接线 —— Freeze 因此连错两轮都发现不了。
现在引擎是纯 C++，可以离线渲染成 WAV，再对样本做数学检验。

运行:
    cd vst && python -m pytest tests/ -v
前置:
    cmake --build build
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from analyze_freeze import analyze  # noqa: E402

PROBE = ROOT / "build" / "freeze_probe"
HEADER = ROOT / "core" / "FreezeLoop.h"


def run_probe(tmp_path, *, loop_ms, seam_ms=10.0, freeze_at=2.0, freeze_for=4.0,
              sr=48000.0, total=None):
    if total is None:
        total = freeze_at + freeze_for + 1.0
    out = tmp_path / f"f_{loop_ms}_{seam_ms}_{sr}_{freeze_at}.wav"
    subprocess.run(
        [str(PROBE), "--sr", str(sr), "--loop-ms", str(loop_ms), "--seam-ms", str(seam_ms),
         "--freeze-at", str(freeze_at), "--freeze-for", str(freeze_for),
         "--total", str(total), "--out", str(out)],
        check=True, capture_output=True,
    )
    return str(out)


def measure(tmp_path, **kw):
    channel = kw.pop("channel", 0)
    wav = run_probe(tmp_path, **kw)
    return analyze(wav, kw["loop_ms"], kw.get("freeze_at", 2.0), kw.get("freeze_for", 4.0),
                   kw.get("seam_ms", 10.0), channel), wav


pytestmark = pytest.mark.skipif(not PROBE.exists(), reason="先跑 cmake --build build")


@pytest.mark.parametrize("loop_ms", [20, 50, 100, 250, 500, 1000])
def test_loop_period_matches_the_loop_parameter(tmp_path, loop_ms):
    """LOOP ms 就是循环区间的时长 —— 周期必须精确等于 loop_ms 对应的样本数。"""
    r, _ = measure(tmp_path, loop_ms=loop_ms)
    assert r.loop_samples_expected == int(round(loop_ms * 0.001 * 48000.0))
    assert r.period_error == 0, f"自相关实测周期 {r.period_estimate}，期望 {r.loop_samples_expected}"
    assert r.autocorr_at_loop > 0.99, f"lag=循环长度处自相关仅 {r.autocorr_at_loop}"


def test_freeze_loops_the_most_recent_capture(tmp_path):
    """循环的内容必须是冻结瞬间写头前方 LOOP ms 的真实录音，不是垃圾数据。"""
    r, _ = measure(tmp_path, loop_ms=250)
    assert r.content_correlation > 0.99, f"与源录音相关性仅 {r.content_correlation}"


def test_freeze_never_goes_silent(tmp_path):
    """用户要的是「一直响，不会断」—— 冻结全程不允许出现静音窗口。"""
    r, _ = measure(tmp_path, loop_ms=250)
    assert r.total_windows > 300
    assert r.silent_windows == 0, f"{r.silent_windows}/{r.total_windows} 个静音窗口"
    assert r.rms_frozen > 1e-3, "冻结段几乎无声"


def test_freeze_level_is_comparable_to_dry(tmp_path):
    """冻结不该把音量吃掉或炸掉。"""
    r, _ = measure(tmp_path, loop_ms=250)
    assert 0.7 < r.rms_ratio < 1.3, f"冻结/干声电平比 {r.rms_ratio}"


def test_seam_is_click_free(tmp_path):
    """接缝处不能有咔哒：最大样本间跳变不应超过干声的自然跳变。"""
    r, _ = measure(tmp_path, loop_ms=250, seam_ms=10.0)
    assert r.max_delta_frozen < r.max_delta_dry * 1.5, (
        f"冻结跳变 {r.max_delta_frozen} 远大于干声 {r.max_delta_dry}"
    )
    assert r.seam_outlier_ratio <= 1.0, f"接缝处跳变是离群值 (ratio={r.seam_outlier_ratio})"


def test_seam_crossfade_is_actually_necessary(tmp_path):
    """反证：关掉接缝淡化就应该出现咔哒。若没有，说明这套算法是装饰品。"""
    r, _ = measure(tmp_path, loop_ms=250, seam_ms=0.0)
    assert r.max_delta_at_seam > r.max_delta_dry * 2.0, (
        f"接缝淡化关闭后跳变仅 {r.max_delta_at_seam}（干声 {r.max_delta_dry}），"
        "说明测试信号没有真正考验接缝"
    )


def test_freeze_does_not_follow_tempo(tmp_path):
    """不跟随 tempo/bpm：循环时长只由 LOOP ms 与采样率决定。

    同一个 loop_ms 在 44.1k 与 48k 下，样本数不同，但秒数必须一致。
    引擎里不存在任何 tempo / transport 概念，这条断言把它钉住。
    """
    r44, _ = measure(tmp_path, loop_ms=250, sr=44100.0)
    r48, _ = measure(tmp_path, loop_ms=250, sr=48000.0)

    assert r44.period_error == 0 and r48.period_error == 0
    assert r44.loop_samples_expected == 11025  # 250ms @ 44.1k
    assert r48.loop_samples_expected == 12000  # 250ms @ 48k
    assert r44.loop_samples_expected != r48.loop_samples_expected

    # 引擎源码（剥掉注释后）不得出现 tempo / transport / bpm 相关标识
    src = HEADER.read_text(encoding="utf-8")
    code = "\n".join(line.split("//", 1)[0] for line in src.splitlines()).lower()
    for banned in ("tempo", "bpm", "transport", "quantize", "beat"):
        assert banned not in code, f"FreezeLoop.h 的代码里出现了与 tempo 有关的标识: {banned}"


def test_stereo_channels_stay_independent(tmp_path):
    """两个声道各自循环自己的内容，不能串台。"""
    left, wav = measure(tmp_path, loop_ms=250, channel=0)
    right, _ = measure(tmp_path, loop_ms=250, channel=1)
    assert left.content_correlation > 0.99
    assert right.content_correlation > 0.99

    import soundfile as sf
    audio, _ = sf.read(wav, always_2d=True)
    a = audio[int(3.0 * 48000):int(3.2 * 48000), 0]
    b = audio[int(3.0 * 48000):int(3.2 * 48000), 1]
    assert not (abs(a - b) < 1e-6).all(), "左右声道输出完全相同，说明声道没有分开处理"


@pytest.mark.parametrize("seam_ms", [2.0, 5.0, 10.0, 20.0])
def test_all_seam_lengths_are_click_free(tmp_path, seam_ms):
    """只要开了淡化，2ms 起就够用。"""
    r, _ = measure(tmp_path, loop_ms=250, seam_ms=seam_ms)
    assert r.max_delta_frozen < r.max_delta_dry * 1.5


def test_short_loop_still_seamless(tmp_path):
    """极短循环（20ms）也要无缝 —— 此时淡化会被限制在循环长度的四分之一内。"""
    r, _ = measure(tmp_path, loop_ms=20)
    assert r.period_error == 0
    assert r.silent_windows == 0
    assert r.max_delta_frozen < r.max_delta_dry * 1.5
