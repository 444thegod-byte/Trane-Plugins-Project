"""SpaceDelay 与 RandomSweep 的离线回归测试。

这两个模块光靠听没法判对错，所以每一项都用可量化的指标：
  延迟 → 回声的**位置**（间隔对不对）和**幅度**（反馈比对不对）、换边是否正确
  扫频 → 每 25ms 的**过零率**（亮度指标）：它是否真的在动、动多快、会不会失控

阈值不是拍的，是先在 fx_probe 上实测出基准值再定的（实测值写在断言注释里）。
运行:
    cd vst && python -m pytest tests/ -v
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import numpy as np
import pytest
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
FX = ROOT / "build" / "fx_probe"
SR = 48000

pytestmark = pytest.mark.skipif(not FX.exists(), reason="先跑 cmake --build build")


def run_fx(kind: str, out, **flags) -> str:
    """kind 是探针模式（delay / sweep）。注意不能叫 mode —— 扫频自己也有个 --mode。"""
    cmd = [str(FX), kind, "--out", str(out)]
    for k, v in flags.items():
        if v is True:
            cmd.append(f"--{k.replace('_', '-')}")
        else:
            cmd += [f"--{k.replace('_', '-')}", str(v)]
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def kv(stdout: str) -> dict[str, float]:
    """取 "名字 : 数值" 形式的行。过零率那种 "0.1s  0.0304" 不会被误取。

    名字里禁止出现 ':' 和换行 —— 否则分隔行会被误匹配。
    数值写成严格形式，不用 [\\d.eE+-]+ 那种会把 'e' 单独匹配掉的大杂烩。
    """
    out: dict[str, float] = {}
    for line in stdout.splitlines():
        m = re.match(r"^([^:\n]+?)\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", line)
        if m:
            out[m.group(1).strip()] = float(m.group(2))
    return out


def zcr_series(stdout: str) -> np.ndarray:
    vals = []
    for line in stdout.splitlines():
        m = re.match(r"^\s*([\d.]+)s\s+([\d.]+)\s*$", line)
        if m:
            vals.append(float(m.group(2)))
    return np.array(vals)


def zcr_span(stdout: str) -> float:
    z = zcr_series(stdout)
    assert len(z) > 10, f"过零率序列太短: {len(z)}"
    return float(z.max() - z.min())


def decorrelation_time(z: np.ndarray, win_s: float) -> float:
    """亮度序列的自相关掉到 0.5 以下所需时间 —— 扫得越快，这个值越小。"""
    v = z - z.mean()
    if np.dot(v, v) <= 0:
        return 0.0
    ac = np.correlate(v, v, mode="full")[len(v) - 1:]
    ac = ac / ac[0]
    below = np.where(ac < 0.5)[0]
    return float(below[0] * win_s) if len(below) else float(len(v) * win_s)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


# ================================================================ DELAY

@pytest.mark.parametrize("t_ms", [120.0, 250.0, 500.0])
def test_delay_echo_spacing_matches_the_time_knob(tmp_path, t_ms):
    """回声间隔必须等于 TIME 旋钮。实测误差 0.1~0.4ms。"""
    out = tmp_path / "d.wav"
    info = kv(run_fx("delay", out, time=t_ms, feedback=0.5, damp=0.3, mix=0.5, seconds=6))
    assert "回声间隔" in info, info
    assert abs(info["回声间隔"] - t_ms) < 2.0, (
        f"TIME={t_ms}ms 时实测间隔 {info['回声间隔']}ms"
    )


@pytest.mark.parametrize("fb", [0.3, 0.6])
def test_delay_feedback_ratio_matches_the_knob(tmp_path, fb):
    """相邻回声的幅度比必须等于 FEEDBACK。

    关掉阻尼（damp=0）时实测 0.2982 / 0.5961，比设定值低约 0.6% ——
    那 0.6% 是"读位置带固定调制 + 线性插值"造成的，是刻意的（见 SpaceDelay.h）。
    """
    out = tmp_path / "d.wav"
    info = kv(run_fx("delay", out, time=200, feedback=fb, damp=0.0, mix=0.5, seconds=5))
    measured = info["反馈比"]
    assert abs(measured - fb) < 0.02, f"FEEDBACK={fb} 时实测反馈比 {measured}"


def test_delay_mix_zero_is_pure_dry(tmp_path):
    """MIX=0 时除了干声之外必须彻底安静 —— 否则"关掉的延迟"还在漏声音。"""
    out = tmp_path / "d.wav"
    run_fx("delay", out, time=200, feedback=0.8, damp=0.0, mix=0.0, seconds=3)
    audio, _ = sf.read(out, always_2d=True)
    after = float(np.max(np.abs(audio[int(0.2 * SR):, :])))
    assert after < 1e-6, f"MIX=0 但脉冲之后仍有 {after} 的残留"


def test_delay_pingpong_actually_crosses_the_channels(tmp_path):
    """PINGPONG 必须真的把回声换到另一侧。

    只喂左声道：pp=0 时右声道必须是**精确的** 0；pp=1 时右声道必须有回声。
    实测 0.00000000 / 0.00353。
    """
    a = tmp_path / "pp0.wav"
    b = tmp_path / "pp1.wav"
    i0 = kv(run_fx("delay", a, time=200, feedback=0.7, damp=0.0, pingpong=0.0, mix=0.5,
                   seconds=4, left_only=True))
    i1 = kv(run_fx("delay", b, time=200, feedback=0.7, damp=0.0, pingpong=1.0, mix=0.5,
                   seconds=4, left_only=True))
    assert i0["右声道 RMS"] < 1e-9, f"PINGPONG=0 时右声道却漏了 {i0['右声道 RMS']}"
    assert i1["右声道 RMS"] > 1e-3, f"PINGPONG=1 时右声道没有回声: {i1['右声道 RMS']}"


def test_delay_does_not_run_away_at_max_feedback(tmp_path):
    """反馈拉满（0.92）时也必须衰减，不能自激。"""
    out = tmp_path / "d.wav"
    run_fx("delay", out, time=150, feedback=0.92, damp=0.2, mix=0.5, seconds=20)
    audio, _ = sf.read(out, always_2d=True)
    head = float(np.max(np.abs(audio[:SR, 0])))
    tail = float(np.max(np.abs(audio[int(18 * SR):int(19.5 * SR), 0])))
    assert np.all(np.isfinite(audio)), "延迟输出里有 NaN 或 Inf"
    assert tail < head * 0.01, f"20 秒后仍有 {tail}（开头 {head}），延迟失控"


# ================================================================ SWEEP

def test_sweep_bypass_is_exactly_transparent(tmp_path):
    """旁通时必须完全不动信号。

    输入是固定种子的白噪声（幅度上限 0.25）。旁通输出应当**恰好**还是那个噪声：
    峰值精确 0.25，过零率维持在 ~0.5（未滤波噪声的典型值）。
    实测：峰值 0.249999，过零率 0.4839~0.5214（0.0375 的起伏纯粹是统计噪声）。
    """
    out = tmp_path / "s.wav"
    stdout = run_fx("sweep", out, bypass=True, seconds=6, win_ms=100)
    info = kv(stdout)
    assert abs(info["整段峰值"] - 0.25) < 1e-4, f"旁通峰值 {info['整段峰值']} 不等于输入峰值 0.25"
    z = zcr_series(stdout)
    assert 0.45 < float(z.mean()) < 0.55, f"旁通输出的过零率均值 {z.mean():.4f} 不像未滤波噪声"
    assert zcr_span(stdout) < 0.08, f"旁通输出亮度在变（{zcr_span(stdout):.4f}），说明滤波器没真旁通"


@pytest.mark.parametrize("depth,lo,hi", [(0.0, 0.0, 0.02), (0.5, 0.03, 0.12), (1.0, 0.08, 0.30)])
def test_sweep_depth_controls_how_far_it_swings(tmp_path, depth, lo, hi):
    """DEPTH 必须真的控制扫幅。

    实测：depth=0 → 0.0050（静态滤波，只有噪声统计起伏）
          depth=0.5 → 0.0617
          depth=1.0 → 0.1392
    """
    out = tmp_path / "s.wav"
    stdout = run_fx("sweep", out, rate=2, depth=depth, center=1000, reso=0.5, mode=0,
                    seconds=6, win_ms=100)
    span = zcr_span(stdout)
    assert lo < span < hi, f"DEPTH={depth} 时过零率变化幅度 {span:.4f} 不在 [{lo},{hi}]"


def test_sweep_rate_controls_the_speed(tmp_path):
    """RATE 必须真的控制扫的速度。

    用"亮度序列的自相关掉到 0.5 的时间"来量。实测：
      rate=0.5Hz → 0.925s   rate=1Hz → 0.500s   rate=2Hz → 0.275s
      rate=4Hz → 0.150s     rate=8Hz → 0.075s
    几乎精确的 1/rate 关系。
    """
    def decorr(rate):
        out = tmp_path / f"r{rate}.wav"
        stdout = run_fx("sweep", out, rate=rate, depth=1, center=1000, reso=0.5, mode=0,
                        seconds=8, win_ms=25)
        return decorrelation_time(zcr_series(stdout), 0.025)

    slow = decorr(0.5)
    fast = decorr(8.0)
    assert slow > 0.6, f"rate=0.5Hz 的去相关时间只有 {slow:.3f}s，扫得太快"
    assert fast < 0.25, f"rate=8Hz 的去相关时间高达 {fast:.3f}s，扫得太慢"
    assert slow > fast * 3.0, f"0.5Hz({slow:.3f}s) 与 8Hz({fast:.3f}s) 的速度差不足 3 倍"


def test_sweep_does_not_run_away(tmp_path):
    """高谐振 + 最大扫幅下不能失控。实测峰值 0.66（输入 0.25）。"""
    out = tmp_path / "s.wav"
    info = kv(run_fx("sweep", out, rate=6, depth=1, center=400, reso=1.0, mode=0,
                     seconds=6, win_ms=100))
    assert info["整段峰值"] < 3.0, f"峰值 {info['整段峰值']} 过高，滤波器可能自激"
    audio, _ = sf.read(out, always_2d=True)
    assert np.all(np.isfinite(audio)), "扫频输出里有 NaN 或 Inf"


def test_sweep_is_deterministic(tmp_path):
    """固定种子 → 同样参数必须给出逐样本一致的结果，否则没法回归。"""
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    for o in (a, b):
        run_fx("sweep", o, rate=3, depth=0.8, center=900, reso=0.6, mode=1, seconds=3)
    x, _ = sf.read(a, always_2d=True)
    y, _ = sf.read(b, always_2d=True)
    assert np.array_equal(x, y), "两次渲染不一致，随机数没有固定种子"


# ================================================================ 整链

def test_full_chain_with_sweep_and_delay_still_behaves(tmp_path):
    """把 SWEEP 和 DELAY 一起打开跑整条链：每段都要有声、不越界、无 NaN。"""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    ENGINE = ROOT / "build" / "engine_probe"
    if not ENGINE.exists():
        pytest.skip("先跑 cmake --build build")

    inp = tmp_path / "music.wav"
    sf.write(inp, build(21.0), SR, subtype="FLOAT")
    out = tmp_path / "all_on.wav"
    subprocess.run(
        [str(ENGINE), "--input", str(inp), "--out", str(out),
         "--sweep", "--sweep-rate", "3", "--sweep-depth", "0.7",
         "--delay", "--delay-time", "280", "--delay-feedback", "0.55", "--delay-mix", "0.4",
         "--output-db", "6"],
        check=True, capture_output=True, text=True,
    )
    audio, _ = sf.read(out, always_2d=True)
    assert np.all(np.isfinite(audio)), "整链输出里有 NaN 或 Inf"
    peak = float(np.max(np.abs(audio)))
    assert peak <= 1.0, f"整链峰值 {peak} 越界（限制器没兜住）"
    assert rms(audio[int(5 * SR):int(14 * SR), 0]) > 3e-3, "整链几乎没有声音"
