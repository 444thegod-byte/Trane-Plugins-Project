"""粒子 / 混响 / 总装信号链的离线回归测试。

与 test_freeze_dsp.py 同一套思路：渲染成 WAV，再对样本做数学检验。
运行:
    cd vst && python -m pytest tests/ -v
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

ENGINE = ROOT / "build" / "engine_probe"
REVERB = ROOT / "build" / "reverb_probe"
SR = 48000

pytestmark = pytest.mark.skipif(
    not ENGINE.exists() or not REVERB.exists(), reason="先跑 cmake --build build"
)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def make_noise(path, seconds=16.0, level=0.1, seed=7):
    rng = np.random.default_rng(seed)
    sig = rng.normal(0, 1, int(SR * seconds))
    sig *= level / np.sqrt(np.mean(sig ** 2))
    sf.write(path, np.stack([sig, sig], axis=1), SR, subtype="FLOAT")
    return level


def run_engine(inp, out, **flags):
    cmd = [str(ENGINE), "--input", str(inp), "--out", str(out)]
    for k, v in flags.items():
        if v is True:
            cmd.append(f"--{k.replace('_', '-')}")
        else:
            cmd += [f"--{k.replace('_', '-')}", str(v)]
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def parse_segments(stdout: str) -> dict[str, float]:
    """从 engine_probe 的输出里取每个段落的 RMS。"""
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^(\S+)\s+([\d.]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s*$", line)
        if m and not m.group(1).isdigit():
            out[m.group(1)] = float(m.group(3))
    return out


def run_reverb(out, **flags):
    cmd = [str(REVERB), "--out", str(out)]
    for k, v in flags.items():
        cmd += [f"--{k.replace('_', '-')}", str(v)]
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def parse_kv(stdout: str) -> dict[str, float]:
    """解析 "名字 = 数值" 形式的行。

    两个坑，都踩过：
      1) 名字里不能含 '='。否则 "=== engine_probe ===" 这种分隔行会被误匹配 ——
         旧的宽松写法会把 "engine" 开头那个 'e' 当成数值（因为 e 是科学计数法字符）。
      2) 数值要写成严格形式，不能是 [\\d.eE+-]+ 这种大杂烩。
    """
    out = {}
    for line in stdout.splitlines():
        m = re.match(r"^([^=\n]+?)\s*=\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", line)
        if m:
            out[m.group(1).strip()] = float(m.group(2))
    return out


# ---------------------------------------------------------------- 粒子引擎

def test_grain_engine_level_matches_theory(tmp_path):
    """粒子云的电平必须和理论值吻合，否则一开粒子音量就会跳。

    理论：源RMS x 汉宁窗RMS x 单粒子增益 x sqrt(重叠数) x 声场系数 x 插值衰减
    线性插值对白噪声的理论衰减是 sqrt(2/3)。
    """
    inp = tmp_path / "noise.wav"
    src = make_noise(inp, level=0.1)
    out = tmp_path / "grain.wav"
    run_engine(inp, out, only_grain=True, grain_size=120, grain_density=12,
               grain_spray=0, grain_rate=1)

    audio, _ = sf.read(out, always_2d=True)
    seg = audio[int(5 * SR):int(14 * SR), 0]
    measured = rms(seg)

    hann = np.sqrt(3 / 8)
    overlap = 12 * 0.120
    gain = 1.0 / (hann * np.sqrt(max(1.0, overlap)))
    pan = float(np.mean(np.cos(np.linspace(0.2, 0.8, 101) * np.pi / 2)))
    interp = np.sqrt(2 / 3)
    predicted = src * hann * gain * np.sqrt(overlap) * pan * interp

    assert measured > 1e-3, "粒子输出几乎无声"
    assert 0.7 < measured / predicted < 1.3, (
        f"实测 {measured:.6f} 与理论 {predicted:.6f} 相差过大 (比值 {measured / predicted:.3f})"
    )


def test_grain_output_is_deterministic(tmp_path):
    """固定种子的随机数 —— 同样输入同样参数必须给出逐样本一致的结果，否则无法回归。"""
    inp = tmp_path / "noise.wav"
    make_noise(inp)
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    for o in (a, b):
        run_engine(inp, o, only_grain=True, grain_size=90, grain_density=20, grain_spray=0.4)
    x, _ = sf.read(a, always_2d=True)
    y, _ = sf.read(b, always_2d=True)
    assert np.array_equal(x, y), "两次渲染结果不一致，随机数没有固定种子"


def test_higher_density_produces_more_grains(tmp_path):
    """密度必须真的改变粒子数。"""
    inp = tmp_path / "noise.wav"
    make_noise(inp)
    levels = {}
    for d in (4, 40):
        o = tmp_path / f"d{d}.wav"
        run_engine(inp, o, only_grain=True, grain_size=80, grain_density=d, grain_spray=0.2)
        audio, _ = sf.read(o, always_2d=True)
        levels[d] = rms(audio[int(5 * SR):int(14 * SR), 0])
    assert levels[40] > levels[4] * 1.2, f"密度 40 与 4 的输出差异过小: {levels}"


def test_grain_size_changes_the_texture(tmp_path):
    """粒子长度必须真的改变输出，不能是个装饰旋钮。"""
    inp = tmp_path / "noise.wav"
    make_noise(inp)
    outs = {}
    for s in (20, 400):
        o = tmp_path / f"s{s}.wav"
        run_engine(inp, o, only_grain=True, grain_size=s, grain_density=8, grain_spray=0.3)
        audio, _ = sf.read(o, always_2d=True)
        outs[s] = audio[int(5 * SR):int(14 * SR), 0]
    assert not np.array_equal(outs[20], outs[400])
    # 长粒子应该更接近连续信号：自相关更强
    def ac1(x):
        v = x - x.mean()
        return float(np.dot(v[:-1], v[1:]) / np.dot(v, v))
    assert ac1(outs[400]) > ac1(outs[20]), "长粒子的连续性没有比短粒子强，长度参数可能没生效"


# ---------------------------------------------------------------- 混响

@pytest.mark.parametrize("tail,lo,hi", [(0.0, 0.5, 2.5), (0.8, 3.0, 9.0), (1.0, 15.0, 80.0)])
def test_reverb_tail_scales_with_the_parameter(tmp_path, tail, lo, hi):
    """尾音旋钮必须真的改变 RT60，而且要能覆盖到"非常大"的量级。"""
    out = tmp_path / f"v{tail}.wav"
    info = parse_kv(run_reverb(out, tail=tail, size=0.7, damp=0.4, diffuse=0.7, seconds=45))
    key = [k for k in info if "RT60" in k]
    assert key, f"没能从输出里解析出 RT60: {info}"
    rt60 = info[key[0]]
    assert lo < rt60 < hi, f"tail={tail} 的 RT60={rt60} 超出预期区间 [{lo},{hi}]"


def test_reverb_does_not_run_away(tmp_path):
    """反馈接近 1 时最容易自激。必须衰减，且不能有直流堆积。"""
    out = tmp_path / "v.wav"
    info = parse_kv(run_reverb(out, tail=1.0, size=1.0, damp=0.0, diffuse=1.0, seconds=60))
    slope = info.get("衰减斜率")
    assert slope is not None and slope < 0, f"混响没有衰减（斜率 {slope}），可能自激"
    assert abs(info.get("输出直流", 1.0)) < 1e-2, "输出有直流堆积"

    audio, _ = sf.read(out, always_2d=True)
    head = rms(audio[int(0.2 * SR):int(1.0 * SR), 0])
    tail = rms(audio[int(55 * SR):int(59 * SR), 0])
    assert tail < head, "60 秒后仍然比开头响，混响失控"


def test_reverb_is_stereo_decorrelated(tmp_path):
    """左右必须是去相关的，否则"巨大"就只是把单声道复制两遍。"""
    out = tmp_path / "v.wav"
    info = parse_kv(run_reverb(out, tail=0.8, size=0.7, seconds=20))
    xc = info.get("左右互相关")
    assert xc is not None
    assert abs(xc) < 0.6, f"左右互相关 {xc} 过高，立体声没有宽度"


# ---------------------------------------------------------------- 总装信号链

def test_full_chain_every_stage_produces_sound(tmp_path):
    """每个段落都必须有声音 —— 这是"所有功能必须有用"的机器化检查。"""
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    inp = tmp_path / "music.wav"
    sf.write(inp, build(21.0), SR, subtype="FLOAT")
    out = tmp_path / "demo.wav"
    segs = parse_segments(run_engine(inp, out, loop_ms=250))

    assert set(segs) >= {"dry", "freeze", "grain", "freeze+grain", "space"}, segs
    for name, level in segs.items():
        assert level > 3e-3, f"段落 {name} 的 RMS 只有 {level:.5f}，等于没声"


def test_engine_never_clips(tmp_path):
    """限制器必须兜住：整段输出不得越过 1.0。

    必须在**高输出增益**下测。曾经这条测试只跑默认 0dB，于是掩盖了
    "反馈式限制器对瞬态过冲"的缺陷 —— 实测 +4.8dB 时峰值冲到 1.0062。
    现在 +12dB（最大增益）也必须兜得住。
    """
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    inp = tmp_path / "music.wav"
    sf.write(inp, build(21.0), SR, subtype="FLOAT")
    for db in (0.0, 6.0, 12.0):
        out = tmp_path / f"demo_{db:g}db.wav"
        run_engine(inp, out, loop_ms=250, output_db=db)
        audio, _ = sf.read(out, always_2d=True)
        peak = float(np.max(np.abs(audio)))
        assert peak <= 1.0, f"输出增益 {db:+g}dB 时峰值 {peak:.6f} 越界"
        assert np.all(np.isfinite(audio)), f"输出增益 {db:+g}dB 时出现 NaN 或 Inf"


def test_limiter_catches_transients(tmp_path):
    """前瞻限制器的核心保证：尖峰不能漏出去。

    输入是稀疏的大尖峰（最考验起控速度）。反馈式限制器在这种信号上必然过冲，
    因为尖峰到达那一刻包络才刚开始爬。输出峰值必须被压在阈值 0.95 以内。
    """
    n = int(SR * 12.0)
    sig = np.zeros(n)
    for k in range(int(12.0 / 0.4)):
        i = int(k * 0.4 * SR) + 137
        if i + 40 < n:
            sig[i:i + 40] = 0.9 * np.hanning(40)
    rng = np.random.default_rng(11)
    sig += rng.normal(0, 0.002, n)

    inp = tmp_path / "spikes.wav"
    sf.write(inp, np.stack([sig, sig], axis=1), SR, subtype="FLOAT")
    out = tmp_path / "spikes_out.wav"
    run_engine(inp, out, loop_ms=250, space_mix=0.0, output_db=12.0)

    audio, _ = sf.read(out, always_2d=True)
    peak = float(np.max(np.abs(audio)))
    assert peak <= 0.95 + 1e-4, f"尖峰漏出限制器: 峰值 {peak:.6f} > 阈值 0.95"


def test_limiter_reports_latency(tmp_path):
    """前瞻限制器引入固定延迟，必须能被引擎报出来（宿主靠它做补偿）。"""
    src = (ROOT / "core" / "TraneEngine.h").read_text(encoding="utf-8")
    assert "latencySamples()" in src, "引擎没有对外暴露限制器延迟，宿主无法补偿"
    lim = (ROOT / "core" / "LookaheadLimiter.h").read_text(encoding="utf-8")
    assert "int latencySamples() const" in lim, "限制器没有 latencySamples()"


def test_bypass_keeps_the_same_latency(tmp_path):
    """旁通时的延迟必须和正常处理完全一致。

    本设备因为前瞻限制器报了 2ms 延迟，宿主会照这个值做补偿。
    JUCE 基类的 processBlockBypassed 假定延迟为 0（源码里还有
    jassert(getLatencySamples() == 0)），直接用它会让干声被往前推 2ms。
    所以必须自己实现 —— 这条测试验证：旁通输出 == 输入精确延迟 N 个样本。
    """
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    inp = tmp_path / "music.wav"
    sf.write(inp, build(6.0), SR, subtype="FLOAT")
    out = tmp_path / "byp.wav"
    info = parse_kv(run_engine(inp, out, bypass=True))

    lat = int(info["报告延迟"])
    assert lat > 0, f"引擎报告的延迟是 {lat}，限制器没接上？"

    xin, _ = sf.read(inp, always_2d=True)
    yout, _ = sf.read(out, always_2d=True)
    assert yout.shape[0] == xin.shape[0], "旁通改变了长度"

    assert np.array_equal(yout[lat:, 0], xin[:-lat, 0]), "旁通输出不是输入的精确延迟"
    assert np.allclose(yout[:lat, 0], 0.0, atol=0.0), "延迟线开头应该是 0"
    assert np.array_equal(yout[lat:, 1], xin[:-lat, 1]), "右声道旁通不一致"


def test_freeze_in_the_full_chain_is_still_an_exact_loop(tmp_path):
    """总装之后冻结仍必须是精确循环 —— 不能被别的模块破坏。"""
    inp = tmp_path / "noise.wav"
    make_noise(inp, level=0.2)
    out = tmp_path / "f.wav"
    run_engine(inp, out, only_freeze=True, loop_ms=200)

    audio, _ = sf.read(out, always_2d=True)
    loop_len = int(0.200 * SR)
    seg = audio[int(5 * SR):int(14 * SR), 0].astype(np.float64)
    v = seg - seg.mean()
    ac = float(np.dot(v[:-loop_len], v[loop_len:]) / np.dot(v, v))
    assert ac > 0.9, f"总装后 lag={loop_len} 处自相关仅 {ac:.4f}，冻结不再是精确循环"
