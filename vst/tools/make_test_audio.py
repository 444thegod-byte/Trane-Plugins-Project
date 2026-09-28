#!/usr/bin/env python3
"""make_test_audio.py — 生成一段音乐测试素材，用来听 Träne 的效果。

刻意做成有明确瞬态 + 明确音高的内容，这样冻结、粒子、混响的差别一耳朵能分出来：
  * 和弦拨奏（每拍重触发，指数衰减）—— 给冻结和粒子提供有音高的素材
  * 底鼓（正弦扫频）—— 给接缝和瞬态提供考验
  * 踩镲（窄噪声脉冲）—— 给高频阻尼提供素材

用法:
    python3 tools/make_test_audio.py /tmp/trane_test.wav --seconds 20
"""
from __future__ import annotations

import argparse

import numpy as np
import soundfile as sf

SR = 48000


def _pluck(freq: float, dur: float, sr: int = SR) -> np.ndarray:
    """一次拨奏：几个泛音 + 指数衰减包络。"""
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * 6.0)
    # 轻微的击弦噪声，让瞬态更明确
    click = np.random.default_rng(int(freq) % 9973).normal(0, 1, n) * np.exp(-t * 300.0) * 0.25
    sig = np.zeros(n)
    for k, amp in ((1.0, 1.0), (2.0, 0.32), (3.0, 0.16), (4.02, 0.08)):
        sig += amp * np.sin(2 * np.pi * freq * k * t)
    return (sig / 2.0 + click) * env


def _kick(dur: float = 0.35, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    freq = 110 * np.exp(-t * 22.0) + 42
    phase = 2 * np.pi * np.cumsum(freq) / sr
    return np.sin(phase) * np.exp(-t * 9.0)


def _hat(dur: float = 0.06, sr: int = SR) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(4242)
    noise = rng.normal(0, 1, n)
    # 一阶高通，去掉低频，得到"嘶"而不是"噗"
    noise = np.diff(np.concatenate([[0.0], noise]))
    return noise * np.exp(-t * 90.0) * 0.35


def build(seconds: float) -> np.ndarray:
    n = int(seconds * SR)
    out = np.zeros((n, 2))

    # Am - F - C - G，每和弦 2 秒（120 BPM，一小节）
    chords = [
        [220.00, 261.63, 329.63],   # Am
        [174.61, 220.00, 261.63],   # F
        [261.63, 329.63, 392.00],   # C
        [196.00, 246.94, 293.66],   # G
    ]
    roots = [110.00, 87.31, 130.81, 98.00]

    beat = 0.5  # 120 BPM
    bar = beat * 4

    kick = _kick()
    hat = _hat()

    pos = 0.0
    bar_idx = 0
    while pos < seconds:
        ch = chords[bar_idx % 4]
        root = roots[bar_idx % 4]
        rng = np.random.default_rng(1000 + bar_idx)

        for b in range(4):
            t0 = pos + b * beat
            i0 = int(t0 * SR)
            if i0 >= n:
                break
            # 和弦拨奏
            for j, f in enumerate(ch):
                seg = _pluck(f * (1.0 + rng.normal(0, 0.0015)), 1.8)
                m = min(len(seg), n - i0)
                pan = 0.5 + (j - 1) * 0.22
                out[i0:i0 + m, 0] += seg[:m] * (1 - pan) * 0.30
                out[i0:i0 + m, 1] += seg[:m] * pan * 0.30
            # 低音
            seg = _pluck(root, 1.4)
            m = min(len(seg), n - i0)
            out[i0:i0 + m, 0] += seg[:m] * 0.34
            out[i0:i0 + m, 1] += seg[:m] * 0.34
            # 底鼓在第 1、3 拍
            if b in (0, 2):
                m = min(len(kick), n - i0)
                out[i0:i0 + m, 0] += kick[:m] * 0.5
                out[i0:i0 + m, 1] += kick[:m] * 0.5
            # 踩镲在八分音符
            for half in (0, 1):
                ih = int((t0 + half * beat / 2) * SR)
                if ih >= n:
                    break
                m = min(len(hat), n - ih)
                out[ih:ih + m, 0] += hat[:m] * 0.8
                out[ih:ih + m, 1] += hat[:m] * 0.9

        pos += bar
        bar_idx += 1

    # 持续铺底 pad：保证任何时刻都有内容可被冻结/粒子抓取。
    # 没有它的话，冻结窗口如果正好落在两个音之间的衰减尾音上，听起来会"没声"。
    fade = int(0.15 * SR)
    nbars = int(np.ceil(seconds / bar))
    for bi in range(nbars):
        ch = chords[bi % 4]
        root = roots[bi % 4]
        i0 = int(bi * bar * SR)
        i1 = min(n, int((bi + 1) * bar * SR))
        if i1 - i0 < 16:
            break
        tt = np.arange(i1 - i0) / SR
        env = np.ones(i1 - i0)
        if (i1 - i0) > 2 * fade:
            env[:fade] = np.linspace(0.0, 1.0, fade)
            env[-fade:] = np.linspace(1.0, 0.0, fade)
        pad = np.zeros(i1 - i0)
        for f in [root * 2.0, *ch]:
            pad += np.sin(2 * np.pi * f * tt + bi * 0.7)
        pad /= 5.0
        out[i0:i1, 0] += pad * env * 0.11
        out[i0:i1, 1] += pad * env * 0.11

    # 收尾：短淡出，避免末尾爆音
    fade = int(0.05 * SR)
    if n > fade:
        out[-fade:] *= np.linspace(1, 0, fade)[:, None]

    peak = np.max(np.abs(out))
    if peak > 0:
        out *= 0.85 / peak
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=20.0)
    args = ap.parse_args()

    audio = build(args.seconds)
    sf.write(args.out, audio, SR, subtype="FLOAT")
    print(f"已生成 {args.out}  {audio.shape[0] / SR:.1f}s  {SR}Hz  "
          f"峰值={np.max(np.abs(audio)):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
