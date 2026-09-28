---
name: deconstructed-club-dsp
description: DSP recipes for deconstructed-club / experimental electronic sound design — hard-edge stutter reslicing, finite-length tape transport with stop, resonant comb filtering, triangle wavefolding, plus the measured reference values and the design principles behind them. Use when implementing or tuning aggressive, glitchy, "deconstructed" audio effects (stutter, tape stop, comb, fold, crush, ring mod) or when asked to make an effect sound like S280F / Fitness / experimental club production.
description_zh: "解构俱乐部音乐的 DSP 配方（切片重触发、磁带变速停转、谐振梳状、波形折叠）"
description_en: "DSP recipes for deconstructed club sound design"
agent_created: true
---

# 解构俱乐部音乐 DSP 配方

**设计纲领：解构感来自「硬边」和「物理约束」，不是来自「更猛的量」。**

- 粒子（grain）是**带窗的重叠颗粒** → 平滑、成雾
- 切片（stutter）是**硬边的整段反复** → 有棱角、有断口

两者**叠加**才是"碎但厚"。只做粒子会糊，只做切片会干。这是最重要的一条审美判断。

## 一、Stutter —— 硬边切片重触发

**要做什么**：把最近 N ms 的音频原地循环，带随机跳变，制造棱角断口。

**关键实现**：
- 自有环形缓冲（1 秒足够），**不要复用粒子的缓冲** —— 粒子带窗，会毁掉硬边
- 触发闩锁：按 `rateHz` 定频捕获新切片
- 切片两端各 0.3ms 淡化 —— **只为去掉直流冲击，不是为了好听**。
  淡化太短会有咔哒，太长会失去硬边，0.3ms 是分界
- 淡化长度**不能超过切片一半**，否则两条淡化曲线互相吃掉：
  ```cpp
  const int dl = std::min(declick_, std::max(1, sliceLen_ / 2));
  ```
- mix 用 15ms 平滑，避免开关爆音
- 随机数**固定种子**（xorshift32），否则渲染不可复现、无法回归

**参数与实测**：
| 参数 | 默认 | 实测证据 |
|---|---|---|
| `sizeMs` | 90 | lag=切片长度自相关 **0.9223**；对照组 0.0022（差 400 倍） |
| `rateHz` | 4 | 60/100/200ms 切片长度与最强周期倍数 **1.00** 全部命中 |
| `jump` | 0.35 | 跳变位置随机但不失控 |
| `mix` | 1.0 | 由引擎按 mix 门控，**缓冲照常写**（重开立刻有素材） |

> ⚠️ 门控开关时不要停掉缓冲写入，否则重新打开的瞬间是空的，前几十毫秒没声音。

## 二、Tape —— 有限长度磁带机

**要做什么**：变速（含到 0 的停转）+ wow/flutter 抖动。

### 物理约束才是这个模块的灵魂

写头以 1x 前进，读头以 speed 前进，**落后距离 = 磁带存量**，8 秒缓冲 = 磁带总长。

- `speed < 1` → 读头必然落后，存量增长
- 带子用完 → **软限位**把速率滑回 1x（不要硬切，会咔哒）
- **由此得到真实的表演技巧：先减速攒带子，再加速。**
  实测：先 0.25x 跑一段再切 2.0x → **1948.57Hz**（2x 的目标是 2000Hz，受存量限制）；
  没有存量直接切 2.0x 则停在 **1000.00Hz**（被限位压住，完全加不上去）。
  这个差异就是"能攒带子"的证据。

### 三个必须做对的细节

1. **抖动必须是有界位移，不能是速率乘法**
   `pos += speed * (1 + wob)` 会把抖动积分成**无界位置漂移**，撞限位后变成"只往一边摆"。
   正确做法：`posAbs`（匀速，参与存量计算）+ `wobOffset`（有界 LFO，上限 3ms）。
   实测：wobble=0.8 → 频率 ±4.00%，而存量**恒定 514 样本**（证明没有漂移）。

2. **软限位必须单侧生效**
   两侧都限位的话，减速时会被误判成"快追上写头"，速率被拖回 1x，变速直接失效。
   按 `speedSm > 1.0 / < 1.0` 分侧判断。
   常量：`kSoftZone = 2000` 样本、`kMinPosLag = 200` 样本。

3. **停转必须同时停住写头**
   只停读头的话，写头 8 秒后绕回来**覆盖读头位置**，停转自己复活
   （端到端实测末段 RMS 0.174，应为 0）。
   真磁带停住读到的是**不变的静态磁化** —— 模拟它就得冻结写头。
   ```cpp
   const bool stopping = target <= kStopThreshold;  // 看目标值，不看平滑值
   const bool tapeFull = lagPos >= maxLag_ - 1.0;   // 平滑值要 1 秒多才收敛
   if (!(stopping && tapeFull)) { ringL_[wAbs_ % cap_] = l[i]; ++wAbs_; }
   ```
   修后：停转 20 秒末段 RMS 精确 **0.00000000**；分段 RMS
   `[0]0.2687 [1]0.0705 [2]0.000085 [3]0.000000`。

**其余常量**：`kMaxTapeMs = 8000`、`kSmoothMs = 150`（一阶平滑才是"磁带感"来源）、
`kInitialLagMs = 10.7`（单位速率下的透明存量）、`kStopThreshold = 0.002`。
停转时接隔直（`y = x - x1 + 0.9995 * y1`）处理静态磁化。

## 三、Comb —— 谐振梳状滤波器

**要做什么**：给声音染上金属/管道的音高感，是解构里最便宜也最有效的"空间扭曲"。

- 延迟 `D = sr / tuneHz`，**必须做分数延迟线性插值** ——
  20Hz 时一个样本的误差就是 4% 音高偏差
- 立体声宽度：**右声道延迟乘 1.008**（比例错开，不是固定样本数偏移），
  这样任何 tune 值下宽度比例都一致
- 反馈路径：**隔直 + 阻尼低通**。阻尼随反馈加深：
  `dampCoef = 0.30 + 0.45 * (fb / kMaxFeedback)`，`kMaxFeedback = 0.95`
- 范围 20–4000Hz，30ms 平滑

**实测**：tune 110/220/440 → **109.84 / 220.18 / 440.37 Hz**（误差 ≤1 样本）；
自相关 @1 倍周期：fb=0.4/0.7/0.9 → **0.1935 / 0.4475 / 0.6966**（严格单调，对照组 0.0013）。

> 稳定性判据注意：喂**连续白噪声**时输出永远不会安静，
> 判据要写"晚段/早段 RMS 比 ≤1.15"，不能写"末段趋近 0"。

## 四、Wavefolder —— 三角波形折叠

**要做什么**：和饱和完全不同的"硬度"。tanh 是**越推越平**，折叠是**越推越翻**。

```cpp
inline double foldTriangle(double x) {
    const double t = x - 4.0 * std::floor((x + 1.0) * 0.25);
    return 1.0 - std::abs(t - 1.0);          // 周期 4，连续，输出恒在 [-1, 1]
}
```

- 驱动增益 `1.0 + foldAmt * 8.0`
- **干湿混合**，保证 `fold = 0` 时与旧行为**逐位一致**（回归测试才不会误报）

**实测总谐波含量**：fold=0.0/0.3/0.6 → **0.0073 / 0.1342 / 1.3023**，
而 drive=1.0 的纯 tanh 饱和只有 **0.3754** —— **折叠是饱和的 3.5 倍**。
全部 fold 值峰值 ≤ 1.0001（有界）。

## 五、信号链位置

```
capture → freeze → grain → STUTTER → COMB → TAPE → ruin(ring→tanh→FOLD→crush)
        → sweep → delay → space → limiter
```

**顺序有理由**：
- STUTTER 在 GRAIN 之后 —— 切的是"已经成雾的东西"，得到碎但厚
- COMB 在 TAPE 之前 —— 让谐振跟着磁带一起被拉慢，音高一起掉才像真的
- FOLD 在 CRUSH 之前 —— 先折叠出谐波，再压位深把谐波糊开
- 一切在 LIMITER 之前 —— 折叠和反馈都会爆电平

## 六、审美红线

- **不做"假效果"**：BPM 对不上就是不对，宁可报错
- **开关不爆音**：所有 mix/开关一律平滑（15ms 级）
- **不给 LFO 用周期感明显的波形** 去做"随机"扫频 —— LFO 有周期感，随机没有
- **极端值必须有界**：折叠输出恒在 [-1,1]，抖动上限 3ms，反馈上限 0.95
