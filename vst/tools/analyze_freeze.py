#!/usr/bin/env python3
"""analyze_freeze.py — 分析 freeze_probe 渲染出来的 WAV，验证 Freeze 是否真的对。

这是整个 VST3 转向的意义所在：Max for Live 我无法在本机运行，只能静态验证接线，
结果 Freeze 连错两轮都发现不了。这里我可以直接对渲染出来的样本做数学检验。

检验项：
  1. 有声音      —— 冻结段 RMS 与干声段同量级
  2. 周期正确    —— 自相关峰值落在 loop_ms 对应的样本数上（±2 样本）
  3. 内容正确    —— 循环内容 == 冻结瞬间写头前方 loop_ms 毫秒的真实录音
  4. 接缝无缝    —— 接缝处的样本间跳变不是离群值
  5. 不会断      —— 冻结全程无静音窗口
  6. 不跟 tempo  —— 引擎结构上不存在 tempo 参数（由 test_freeze_dsp.py 断言）

用法:
    python3 tools/analyze_freeze.py /tmp/trane_f250.wav --loop-ms 250
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np
import soundfile as sf


@dataclass
class FreezeReport:
    loop_samples_expected: int
    period_estimate: int
    period_error: int
    autocorr_at_loop: float
    rms_dry: float
    rms_frozen: float
    rms_ratio: float
    silent_windows: int
    total_windows: int
    max_delta_dry: float
    max_delta_frozen: float
    max_delta_at_seam: float
    seam_outlier_ratio: float
    content_correlation: float
    passed: bool
    failures: list[str]


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))


def _max_delta(x: np.ndarray) -> float:
    if x.size < 2:
        return 0.0
    return float(np.max(np.abs(np.diff(x))))


def _autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    """归一化自相关，返回 lag 0..max_lag。

    必须做「无偏」归一化：每个 lag 的重叠样本数不同（N-lag），
    不除以重叠数的话，即使信号完全周期，lag=L 处也会得到 1 - L/N，
    从而把一个正确的循环误判成不成立。
    """
    v = x - x.mean()
    n = v.size
    size = 1 << int(np.ceil(np.log2(n + max_lag + 1)))
    spec = np.fft.rfft(v, size)
    ac = np.fft.irfft(spec * np.conj(spec), size)[: max_lag + 1]
    counts = np.maximum(n - np.arange(max_lag + 1), 1)
    ac = ac / counts
    if ac[0] <= 0:
        return ac
    return ac / ac[0]


def analyze(
    wav_path: str,
    loop_ms: float,
    freeze_at: float = 2.0,
    freeze_for: float = 4.0,
    seam_ms: float = 10.0,
    channel: int = 0,
) -> FreezeReport:
    audio, sr = sf.read(wav_path, always_2d=True)
    dry_in, _ = sf.read(wav_path + ".in.wav", always_2d=True)

    if audio.shape[0] != dry_in.shape[0]:
        raise ValueError("输入与输出长度不一致")

    sr = float(sr)
    loop_len = int(round(loop_ms * 0.001 * sr))
    freeze_start = int(round(freeze_at * sr))
    freeze_end = int(round((freeze_at + freeze_for) * sr))

    # 分析窗口：跳过 dry<->loop 的交叉淡化，也避开解冻过渡
    smooth = int(0.006 * sr)
    a = freeze_start + smooth + int(0.02 * sr)
    b = freeze_end - int(0.05 * sr)
    frozen = audio[a:b, channel].astype(np.float64)

    dry_a = int(0.5 * sr)
    dry_b = int(1.5 * sr)
    dry = audio[dry_a:dry_b, channel].astype(np.float64)

    failures: list[str] = []

    # --- 1. 有声音 ---
    r_dry = _rms(dry)
    r_frz = _rms(frozen)
    rms_ratio = r_frz / r_dry if r_dry > 0 else 0.0
    if r_frz < 1e-3:
        failures.append(f"冻结段几乎无声 (rms={r_frz:.2e})")
    if rms_ratio < 0.5:
        failures.append(f"冻结段电平异常偏低 (ratio={rms_ratio:.3f})")

    # --- 2. 周期正确 ---
    max_lag = min(frozen.size - 2, int(loop_len * 1.5) + 4)
    ac = _autocorr(frozen, max_lag)
    lo = max(2, int(loop_len * 0.5))
    hi = min(ac.size - 1, int(loop_len * 1.5))
    if hi > lo:
        period_est = lo + int(np.argmax(ac[lo:hi]))
    else:
        period_est = loop_len
    period_error = period_est - loop_len
    ac_at_loop = float(ac[loop_len]) if loop_len < ac.size else 0.0
    if abs(period_error) > 2:
        failures.append(f"自相关周期 {period_est} 与期望 {loop_len} 相差 {period_error} 样本")
    if ac_at_loop < 0.95:
        failures.append(f"lag={loop_len} 处自相关仅 {ac_at_loop:.4f}，循环不成立")

    # --- 3. 内容正确：循环内容应等于冻结瞬间写头前方 loop_ms 毫秒的真实录音 ---
    # 探针的缓冲区容量 8 秒，冻结发生在 2 秒处 -> 写头 = 2*sr，循环区间 = [2*sr - L, 2*sr)
    cap_samples = int(round(8.0 * sr))
    write_head = freeze_start % cap_samples
    src_start = (write_head - loop_len) % cap_samples
    # 输出第 n 个样本对应循环相位 (n - freeze_start) mod L，源位置 = src_start + 相位
    idx = np.arange(a, b)
    phase = (idx - freeze_start) % loop_len
    # 避开接缝交叉淡化区（相位接近 L 的那一段），那里本来就是混合内容
    seam_samples = int(round(seam_ms * 0.001 * sr))
    safe = phase < max(1, loop_len - seam_samples - 64)
    if np.count_nonzero(safe) > 1000:
        got = audio[idx[safe], channel].astype(np.float64)
        want = dry_in[src_start + phase[safe], channel].astype(np.float64)
        g = got - got.mean()
        w = want - want.mean()
        denom = float(np.sqrt(np.sum(g * g) * np.sum(w * w)))
        content_corr = float(np.sum(g * w) / denom) if denom > 0 else 0.0
    else:
        content_corr = 0.0
    if content_corr < 0.99:
        failures.append(f"循环内容与源录音相关性仅 {content_corr:.4f}，读的不是最近的录音")

    # --- 4. 接缝无缝 ---
    # 接缝出现在相对冻结起点的每个 loop_len 倍数处
    seam_positions = []
    k = 1
    while freeze_start + k * loop_len < b:
        pos = freeze_start + k * loop_len
        if pos >= a:
            seam_positions.append(pos)
        k += 1
    win = 4
    seam_deltas = []
    for pos in seam_positions:
        lo_i = max(a + 1, pos - win)
        hi_i = min(b, pos + win + 1)
        if hi_i > lo_i:
            seam_deltas.append(_max_delta(audio[lo_i:hi_i, channel].astype(np.float64)))
    max_delta_at_seam = max(seam_deltas) if seam_deltas else 0.0
    max_delta_frozen = _max_delta(frozen)
    max_delta_dry = _max_delta(dry)
    # 接缝处的跳变不应超过整段最大跳变（若接缝有咔哒，它必然是离群的最大值）
    seam_outlier_ratio = (max_delta_at_seam / max_delta_frozen) if max_delta_frozen > 0 else 0.0
    if max_delta_frozen > max_delta_dry * 1.5:
        failures.append(
            f"冻结段最大跳变 {max_delta_frozen:.5f} 明显大于干声 {max_delta_dry:.5f}，疑似咔哒"
        )
    if seam_outlier_ratio > 1.0 + 1e-9 and max_delta_at_seam > max_delta_dry * 1.5:
        failures.append(f"接缝处跳变是离群值 (ratio={seam_outlier_ratio:.3f})，接缝不连续")

    # --- 5. 不会断 ---
    win_samples = int(0.010 * sr)
    n_win = len(frozen) // win_samples
    silent = 0
    for i in range(n_win):
        seg = frozen[i * win_samples : (i + 1) * win_samples]
        if _rms(seg) < 1e-4:
            silent += 1
    if silent > 0:
        failures.append(f"冻结段有 {silent}/{n_win} 个静音窗口，会断")

    return FreezeReport(
        loop_samples_expected=loop_len,
        period_estimate=period_est,
        period_error=period_error,
        autocorr_at_loop=ac_at_loop,
        rms_dry=r_dry,
        rms_frozen=r_frz,
        rms_ratio=rms_ratio,
        silent_windows=silent,
        total_windows=n_win,
        max_delta_dry=max_delta_dry,
        max_delta_frozen=max_delta_frozen,
        max_delta_at_seam=max_delta_at_seam,
        seam_outlier_ratio=seam_outlier_ratio,
        content_correlation=content_corr,
        passed=not failures,
        failures=failures,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wav")
    ap.add_argument("--loop-ms", type=float, required=True)
    ap.add_argument("--freeze-at", type=float, default=2.0)
    ap.add_argument("--freeze-for", type=float, default=4.0)
    ap.add_argument("--seam-ms", type=float, default=10.0)
    ap.add_argument("--channel", type=int, default=0)
    args = ap.parse_args()

    r = analyze(args.wav, args.loop_ms, args.freeze_at, args.freeze_for, args.seam_ms, args.channel)

    print(f"=== 分析 {args.wav} (声道 {args.channel}) ===")
    print(f"循环样本   期望={r.loop_samples_expected}  实测周期={r.period_estimate}  误差={r.period_error}")
    print(f"自相关     lag=循环长度处 = {r.autocorr_at_loop:.6f}   (1.0 = 完全周期)")
    print(f"电平       干声 rms={r.rms_dry:.6f}  冻结 rms={r.rms_frozen:.6f}  比值={r.rms_ratio:.4f}")
    print(f"内容相关   与源录音 = {r.content_correlation:.6f}   (1.0 = 就是那段录音)")
    print(f"跳变       干声={r.max_delta_dry:.6f}  冻结={r.max_delta_frozen:.6f}  接缝={r.max_delta_at_seam:.6f}")
    print(f"静音窗口   {r.silent_windows} / {r.total_windows}")
    print()
    if r.passed:
        print("结论: 全部通过")
        return 0
    print("结论: 未通过")
    for f in r.failures:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
