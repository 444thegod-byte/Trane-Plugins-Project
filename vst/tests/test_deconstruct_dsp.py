"""解构链（STUTTER / COMB / TAPE / RUIN-FOLD）的离线回归测试。

这四个模块是"更解构的效果"的全部内容，光靠听没法判对错，所以每一条都量化：

  stutter → 输出在 lag=切片长度 处的**自相关**（原地重复才有棱角）
  tape    → 输出**频率**是否精确等于 输入频率 x speed；停转后是否真的安静
  comb    → 梳状周期处的**自相关**（应 ≈ feedback）+ 自相关峰的位置反推基频
  fold    → **总谐波含量**（折叠必须比 tanh 饱和凶得多，而且不得失控）

阈值全部先在 fx_probe 上实测出基准再定，实测值写在断言注释里。
运行:
    cd vst && python -m pytest tests/test_deconstruct_dsp.py -v
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FX = ROOT / "build" / "fx_probe"
SR = 48000

pytestmark = pytest.mark.skipif(not FX.exists(), reason="先跑 cmake --build build")


def run_fx(kind: str, out, **flags) -> str:
    cmd = [str(FX), kind, "--out", str(out)]
    for k, v in flags.items():
        if v is True:
            cmd.append(f"--{k.replace('_', '-')}")
        else:
            cmd += [f"--{k.replace('_', '-')}", str(v)]
    r = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return r.stdout


def kv(stdout: str) -> dict[str, float]:
    """取 "名字 : 数值" 形式的行。名字里禁止出现 ':'，数值用严格形式。"""
    out: dict[str, float] = {}
    for line in stdout.splitlines():
        m = re.match(r"^([^:\n]+?)\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", line)
        if m:
            out[m.group(1).strip()] = float(m.group(2))
    return out


# ================================================================ STUTTER

def test_stutter_actually_repeats_the_slice(tmp_path):
    """切片的本质是"原地重复"，所以 lag=切片长度 处必须有强自相关。

    实测：切片 100ms / 触发 1Hz / 跳位 0 时，
          lag=切片长度 → 0.9223（对照组只喂干声时 → 0.0022）
    这个 0.92 不是 1.0，是因为每次触发会换一段新切片，
    在触发边界上前后就不再相同了 —— 那正是"有断口"的来源。
    """
    out = tmp_path / "st.wav"
    on = kv(run_fx("stutter", out, size=100, rate=1, jump=0, seconds=6))
    off = kv(run_fx("stutter", tmp_path / "off.wav", size=100, rate=1, jump=0, seconds=6,
                    off=True))
    assert on["自相关 @ 切片长度"] > 0.80, f"切片没有真的重复: {on['自相关 @ 切片长度']}"
    assert off["自相关 @ 切片长度"] < 0.05, f"对照组居然也有重复: {off['自相关 @ 切片长度']}"
    assert on["自相关 @ 切片长度"] > off["自相关 @ 切片长度"] * 20, "开与关区分度不足"


def test_stutter_slice_length_follows_the_knob(tmp_path):
    """最强重复周期必须正好是切片长度（1 倍），说明 size 旋钮真的在管切片长短。"""
    for size in (60.0, 100.0, 200.0):
        out = tmp_path / f"s{size}.wav"
        info = kv(run_fx("stutter", out, size=size, rate=1, jump=0, seconds=6))
        want = round(size * 0.001 * SR)
        assert abs(info["切片实际长度"] - want) <= 2, (
            f"size={size}ms 时切片长度 {info['切片实际长度']}，期望 {want}"
        )
        assert abs(info["周期倍数"] - 1.0) < 0.05, f"最强周期不是 1 倍切片长度: {info['周期倍数']}"


def test_stutter_does_not_run_away(tmp_path):
    """切片循环是 1x 重放，绝不能比输入更响。实测峰值 0.3000（输入 0.3）。"""
    out = tmp_path / "st.wav"
    info = kv(run_fx("stutter", out, size=150, rate=12, jump=1.0, seconds=6))
    assert info["整段峰值"] < 0.31, f"切片输出被放大了: {info['整段峰值']}"


# ================================================================ TAPE

@pytest.mark.parametrize("speed,expect", [(0.25, 250.0), (0.5, 500.0), (1.0, 1000.0)])
def test_tape_speed_scales_pitch_exactly(tmp_path, speed, expect):
    """变速的本质：音高精确等于 输入频率 x speed。

    实测：speed=0.25 → 250.00Hz   speed=0.5 → 500.00Hz   speed=1.0 → 1000.00Hz
    全部精确命中（零点计数法的分辨率就是 1/秒）。
    """
    out = tmp_path / f"t{speed}.wav"
    info = kv(run_fx("tape", out, speed=speed, wobble=0, tone=1000, seconds=5))
    assert abs(info["实测输出频率"] - expect) < 1.0, (
        f"speed={speed} 时输出 {info['实测输出频率']}Hz，期望 {expect}Hz"
    )


def test_tape_is_transparent_at_unity_speed(tmp_path):
    """speed=1 必须什么都不做：频率不变，磁带存量只有 10.7ms（磁头间距）。"""
    out = tmp_path / "t1.wav"
    info = kv(run_fx("tape", out, speed=1.0, wobble=0, tone=1000, seconds=5))
    assert abs(info["实测输出频率"] - 1000.0) < 1.0
    assert info["磁带存量"] < 0.02 * SR, f"speed=1 却积了 {info['磁带存量']} 样本的延迟"


def test_tape_stop_goes_silent_not_dc(tmp_path):
    """拧到 0 就是 tape stop：读头停住读到静止磁化 → 隔直滤掉 → 必须安静。

    少了隔直这一步，读头停住会往总线上灌一个恒定直流，
    峰值不为 0、限制器被顶死。实测末段 RMS 精确 0.00000000。
    """
    out = tmp_path / "t0.wav"
    info = kv(run_fx("tape", out, speed=0.0, wobble=0, tone=1000, seconds=5))
    assert info["实测输出频率"] < 1.0, f"停转后还在动: {info['实测输出频率']}Hz"
    assert info["末段 RMS"] < 1e-6, f"停转后仍残留 {info['末段 RMS']}（直流没滤干净）"
    assert info["整段峰值"] > 0.3, "停转前应当是有声音的，峰值不该这么低"


def test_tape_stop_holds_past_the_buffer_length(tmp_path):
    """停转必须能**无限**保持，不能过一会儿自己复活。

    这里踩过一次真实的坑：最初只让读头停住、写头照常跑，
    8 秒后写头绕回来覆盖了读头所在的位置，读头读到新素材，
    软限位又把速率拉回 1x —— 停转在 8 秒后自己复活了。
    端到端验收里表现为"停转末段 RMS 0.174 而不是 0"。
    现在改成"停转 + 带子写满时把写头也停住"，跑 20 秒（远超 8 秒缓冲）必须仍是 0。
    """
    out = tmp_path / "t0long.wav"
    info = kv(run_fx("tape", out, speed=0.0, wobble=0, tone=1000, seconds=20))
    assert info["末段 RMS"] < 1e-6, (
        f"停转 20 秒后复活了，末段 RMS {info['末段 RMS']}（缓冲只有 8 秒）"
    )
    assert info["磁带存量"] > 0.9 * 8.0 * SR, (
        f"停转时磁带存量应停在满值附近，实测 {info['磁带存量']}"
    )


def test_tape_wobble_modulates_pitch_but_does_not_drift(tmp_path):
    """wow/flutter 必须真的在抖，而且抖动位移必须有界（不能把读头漂走）。

    实测：wobble=0.8 时 50ms 窗口频率在 960~1040Hz 之间（±4.00%）；
          wobble=0 时恒为 1000.0Hz（±0.00%）。
    同时磁带存量始终停在 514 样本 —— 说明位移没被积分成漂移。
    """
    quiet = kv(run_fx("tape", tmp_path / "q.wav", speed=1.0, wobble=0.0, seconds=5))
    loud = kv(run_fx("tape", tmp_path / "l.wav", speed=1.0, wobble=0.8, seconds=5))
    assert quiet["音高偏差"] < 0.1, f"wobble=0 却有 {quiet['音高偏差']}% 的抖动"
    assert 2.0 < loud["音高偏差"] < 12.0, f"wobble=0.8 的抖动 {loud['音高偏差']}% 不在合理区间"
    assert loud["磁带存量"] < 0.02 * SR, f"抖动把读头漂走了: 存量 {loud['磁带存量']}"


def test_tape_fast_forward_uses_accumulated_tape(tmp_path):
    """先减速攒带子、再加速 —— 这是有限长度磁带机的物理事实，不是 bug。

    实测：先 0.25x 跑 3 秒（攒下约 2.2 秒存量）再切 2.0x，
          切换后窗口实测 1948.57Hz（期望 2000Hz）；
          而从 1.0x 直接切 2.0x（无存量）时仍是 1000.00Hz。
    """
    a = kv(run_fx("tape", tmp_path / "a.wav", speed=0.25, wobble=0, ramp_at=3.0,
                  ramp_speed=2.0, seconds=6))
    b = kv(run_fx("tape", tmp_path / "b.wav", speed=1.0, wobble=0, ramp_at=3.0,
                  ramp_speed=2.0, seconds=6))
    assert a["切换后实测"] > 1500.0, f"攒了带子却没能加速: {a['切换后实测']}Hz"
    assert abs(b["切换后实测"] - 1000.0) < 1.0, (
        f"没有存量时不该能加速，实测 {b['切换后实测']}Hz"
    )


# ================================================================ COMB

def test_comb_tune_sets_the_resonant_pitch(tmp_path):
    """梳状滤波器的延迟 = sr/tune，所以输出的重复周期必须等于这个值。

    用自相关峰的位置反推基频。实测：110→109.84Hz  220→220.18Hz  440→440.37Hz
    （误差 ≤1 个样本，这是整数 lag 自相关的分辨率极限）
    """
    for tune in (110.0, 220.0, 440.0):
        out = tmp_path / f"c{tune}.wav"
        info = kv(run_fx("comb", out, tune=tune, feedback=0.7, mix=1.0, seconds=5))
        assert abs(info["实测基频"] - tune) < tune * 0.03, (
            f"tune={tune}Hz 实测基频 {info['实测基频']}Hz"
        )


@pytest.mark.parametrize("fb", [0.4, 0.7, 0.9])
def test_comb_feedback_shows_up_as_periodicity(tmp_path, fb):
    """反馈越深，输出在梳状周期处的自相关越强（理想值就是 feedback 本身）。

    实测：fb=0.4 → 0.1935   fb=0.7 → 0.4475   fb=0.9 → 0.6966
    比 feedback 低，是因为分数延迟的线性插值把每个脉冲摊到了相邻两个样本上，
    相关性被稀释了约 0.7 倍 —— 这是插值的代价，不是算错。
    对照组（关掉）→ 0.0013。
    """
    out = tmp_path / f"cf{fb}.wav"
    info = kv(run_fx("comb", out, tune=220, feedback=fb, mix=1.0, seconds=5))
    off = kv(run_fx("comb", tmp_path / f"co{fb}.wav", tune=220, feedback=fb, mix=1.0,
                    seconds=5, off=True))
    assert info["自相关 @ 1 倍梳状周期"] > 0.12, f"fb={fb} 没有形成梳状: {info}"
    assert off["自相关 @ 1 倍梳状周期"] < 0.05, f"对照组也有周期性: {off}"
    assert info["自相关 @ 1 倍梳状周期"] > off["自相关 @ 1 倍梳状周期"] * 5, "区分度不足"


def test_comb_feedback_is_monotonic(tmp_path):
    """反馈量必须单调地加深谐振，不能出现"拧过头反而没效果"。"""
    vals = []
    for fb in (0.2, 0.5, 0.8):
        info = kv(run_fx("comb", tmp_path / f"m{fb}.wav", tune=220, feedback=fb, mix=1.0,
                         seconds=5))
        vals.append(info["自相关 @ 1 倍梳状周期"])
    assert vals[0] < vals[1] < vals[2], f"反馈不单调: {vals}"


def test_comb_never_self_oscillates(tmp_path):
    """反馈上限 0.95 也必须稳定 —— 判据是**稳态性**，不是"末段安静"。

    这里喂的是连续白噪声（不是脉冲），所以输出永远不会安静；
    正确的稳定性判据是"晚段的能量有没有比早段涨上去"。
    实测晚/早 RMS 比：fb=0.5 → 1.0013   fb=0.9 → 0.9817   fb=0.95 → 0.9615
    —— 全部 ≤1，说明一进入稳态就不再增长，没有自激。
    （峰值 fb=0.95 时 1.167，那是梳状谐振对白噪声的正常增益；
      进插件后由前瞻限制器兜住，见 LookaheadLimiter。）
    """
    import soundfile as sf

    out = tmp_path / "c.wav"
    info = kv(run_fx("comb", out, tune=200, feedback=0.95, mix=1.0, seconds=8))
    assert info["整段峰值"] < 3.0, f"峰值 {info['整段峰值']} 过高，可能自激"

    audio, sr = sf.read(out, always_2d=True)
    a = audio[:, 0].astype(np.float64)
    assert np.all(np.isfinite(a)), "梳状输出里有 NaN 或 Inf"

    def rms(v):
        return float(np.sqrt(np.mean(v * v)))

    early = rms(a[int(1.5 * sr):int(2.5 * sr)])
    late = rms(a[int(6.5 * sr):int(7.5 * sr)])
    assert early > 1e-3, "梳状几乎没有输出"
    assert late / early < 1.15, (
        f"晚段比早段响了 {late / early:.3f} 倍，反馈在累积（自激）"
    )


# ================================================================ FOLD

def test_fold_adds_harmonics_far_beyond_saturation(tmp_path):
    """波形折叠和 tanh 饱和是两种非线性，折叠必须凶得多。

    实测（200Hz 正弦 @ 0.3，mode=1 全湿）：
      fold=0.0 → 总谐波含量 0.0073（干净）
      fold=0.3 → 0.1342
      fold=0.6 → 1.3023
      drive=1.0（纯 tanh 饱和，fold=0）→ 0.3754
    即 fold=0.6 的谐波是"饱和拉满"的 3.5 倍 —— 这就是解构里那股"硬"的来源。
    """
    clean = kv(run_fx("ruin", tmp_path / "f0.wav", mode=1, drive=0, fold=0.0,
                      crush=0, ring=0, seconds=3))
    fold = kv(run_fx("ruin", tmp_path / "f6.wav", mode=1, drive=0, fold=0.6,
                     crush=0, ring=0, seconds=3))
    sat = kv(run_fx("ruin", tmp_path / "sd.wav", mode=1, drive=1.0, fold=0.0,
                    crush=0, ring=0, seconds=3))
    assert clean["总谐波含量"] < 0.05, f"fold=0 不干净: {clean['总谐波含量']}"
    assert fold["总谐波含量"] > 0.5, f"fold=0.6 的谐波只有 {fold['总谐波含量']}"
    assert fold["总谐波含量"] > sat["总谐波含量"] * 2.5, (
        f"折叠({fold['总谐波含量']}) 没有明显强过饱和({sat['总谐波含量']})"
    )


def test_fold_stays_bounded(tmp_path):
    """折叠是"越推越翻"，很容易越界 —— 但三角折叠器的输出天然落在 [-1,1]。"""
    for amount in (0.0, 0.25, 0.5, 0.75, 1.0):
        info = kv(run_fx("ruin", tmp_path / f"b{amount}.wav", mode=1, drive=0,
                         fold=amount, crush=0, ring=0, seconds=3))
        assert info["整段峰值"] <= 1.0001, (
            f"fold={amount} 时峰值 {info['整段峰值']} 越界，折叠器没有夹住"
        )


def test_ruin_mode_zero_is_transparent(tmp_path):
    """mode=0 是 Clear 人格：不管 fold/drive 拧到多大，输出都必须是原样。"""
    a = kv(run_fx("ruin", tmp_path / "m0.wav", mode=0, drive=1.0, fold=1.0,
                  crush=1.0, ring=1.0, seconds=3))
    b = kv(run_fx("ruin", tmp_path / "m0b.wav", mode=0, drive=0, fold=0,
                  crush=0, ring=0, seconds=3))
    assert abs(a["总谐波含量"] - b["总谐波含量"]) < 0.02, (
        f"Clear 人格被污染了: {a['总谐波含量']} vs {b['总谐波含量']}"
    )


# ================================================================ 确定性

def test_deconstruct_chain_is_deterministic(tmp_path):
    """固定种子 → 同样参数必须逐样本一致，否则没法做回归。"""
    import soundfile as sf
    outs = []
    for i in (0, 1):
        o = tmp_path / f"d{i}.wav"
        run_fx("stutter", o, size=90, rate=4, jump=0.5, seconds=3)
        outs.append(sf.read(o, always_2d=True)[0])
    assert np.array_equal(outs[0], outs[1]), "两次渲染不一致，随机数没有固定种子"


# ================================================================ 整链

def test_full_chain_with_everything_on_stays_controlled(tmp_path):
    """把解构链全部打开跑一遍真实音乐素材：不许 NaN、不许越界、不许没声。

    这是最接近实际使用的一条：stutter + comb + tape + ruin(fold) + sweep + delay
    同时开、输出 +6dB，看限制器兜不兜得住。
    """
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    ENGINE = ROOT / "build" / "engine_probe"
    if not ENGINE.exists():
        pytest.skip("先跑 cmake --build build")

    import soundfile as sf
    inp = tmp_path / "music.wav"
    sf.write(inp, build(21.0), SR, subtype="FLOAT")
    out = tmp_path / "decon.wav"
    subprocess.run(
        [str(ENGINE), "--input", str(inp), "--out", str(out),
         "--stutter", "--stutter-size", "110", "--stutter-rate", "5", "--stutter-jump", "0.4",
         "--comb", "--comb-tune", "180", "--comb-feedback", "0.7", "--comb-mix", "0.6",
         "--tape", "--tape-speed", "0.85", "--tape-wobble", "0.3",
         "--ruin-mode", "0.8", "--ruin-drive", "0.5", "--ruin-fold", "0.5",
         "--sweep", "--sweep-rate", "3", "--sweep-depth", "0.7",
         "--delay", "--delay-time", "280", "--delay-feedback", "0.55", "--delay-mix", "0.4",
         "--space-mix", "0.4",
         "--output-db", "6"],
        check=True, capture_output=True, text=True,
    )
    audio, _ = sf.read(out, always_2d=True)
    assert np.all(np.isfinite(audio)), "整链输出里有 NaN 或 Inf"
    peak = float(np.max(np.abs(audio)))
    assert peak <= 1.0, f"整链峰值 {peak} 越界（限制器没兜住）"
    body = audio[int(5 * SR):int(14 * SR), 0]
    assert float(np.sqrt(np.mean(np.square(body.astype(np.float64))))) > 3e-3, "整链几乎没有声音"
    # 解构链必须有实际作用，不能只是"原样通过"
    ref = tmp_path / "plain.wav"
    subprocess.run(
        [str(ENGINE), "--input", str(inp), "--out", str(ref), "--space-mix", "0.4"],
        check=True, capture_output=True, text=True,
    )
    plain, _ = sf.read(ref, always_2d=True)
    diff = np.max(np.abs(audio[:len(plain)] - plain))
    assert diff > 0.05, f"开了整条解构链，输出却几乎没变（最大差 {diff}）"


def test_engine_reports_the_same_latency_with_everything_on(tmp_path):
    """解构链三个模块都读"过去"，不向宿主引入额外延迟 —— 报告延迟必须仍是 2ms。"""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from make_test_audio import build

    ENGINE = ROOT / "build" / "engine_probe"
    if not ENGINE.exists():
        pytest.skip("先跑 cmake --build build")

    import soundfile as sf
    inp = tmp_path / "music.wav"
    sf.write(inp, build(6.0), SR, subtype="FLOAT")
    r = subprocess.run(
        [str(ENGINE), "--input", str(inp), "--out", str(tmp_path / "lat.wav"),
         "--stutter", "--comb", "--tape"],
        check=True, capture_output=True, text=True,
    )
    m = re.search(r"报告延迟 = (\d+) 样本", r.stdout)
    assert m, r.stdout
    assert int(m.group(1)) == 96, f"开了 stutter/comb/tape 后延迟变成 {m.group(1)} 样本"
