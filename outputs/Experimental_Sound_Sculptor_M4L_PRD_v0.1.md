# Experimental Sound Sculptor
## 基于 Max/MSP/Jitter 的 Max for Live 实时实验声音效果器

**文档版本：** v0.1（需求草案，供审核）  
**定位：** Ableton Live 内的实时立体声音频效果器，服务于实验电子音乐制作与现场演出。  
**本阶段交付：** 需求与技术方案；**不开始制作补丁、不生成 `.amxd`**。  

---

## 1. 产品结论

这不应做成“把很多效果器堆在一起”的工具，而应做成一个以**实时声音捕捉 → 微粒重组 → 冻结/循环 → 时序解构 → 空间扩散**为主线的演奏型效果器。

核心体验应是：对现场人声、合成器、鼓组或 Live 轨道中的任何音频，随时抓取最近的一小段声音，立即把它切成可控的微粒、定格成极短循环、正放/倒放重排，并用节奏、滤波、延迟和混响把声音推向可演奏的解构质感。

### 必须坚持的原则

1. **实时优先。** 所有核心功能均可在 Live 播放时操作；不是离线采样编辑器。
2. **演奏优先。** Freeze、Reverse、Capture、Scene 等关键操作必须可映射 MIDI / Push，并避免参数突变爆音。
3. **可控的随机。** 随机不是不可预测；必须可设强度、范围、种子/锁定与节拍量化。
4. **声音安全。** 反馈、滤波共振、粒子叠加和增益累积必须有软限幅、平滑和明确的安全阈值。
5. **以 Max 为主体。** Max/MSP 负责路由、状态、控制、界面；`gen~` 承担高频、逐采样的 DSP；Jitter 只做可关闭的可视化，不进入音频信号路径。

---

## 2. 目标用户与典型使用方式

| 场景 | 用户动作 | 预期结果 |
|---|---|---|
| 现场人声定格 | 唱到一个词或呼吸声时按住 Freeze | 立即锁住最近的极短片段并无缝循环，可持续铺底 |
| 合成器粒子化 | 打开 Grain，降低 Grain Size、提高 Density | 连续音色变成带密度与漂移的颗粒云 |
| 节奏解构 | 将 ARP/Grain Sequencer 对齐 1/16，加入概率与反向 | 原始音频被重排成可跟随工程速度的碎片节奏 |
| 空间失真 | 提高反馈、扩散与滤波随机调制 | 声音从延迟过渡到颗粒化、模糊化的巨大空间 |
| 现场回切 | 松开 Freeze 或切换场景 | 平滑回到输入信号，不发生明显爆音或断裂 |

---

## 3. 功能范围与优先级

### P0：首版必须完成

1. 粒子采样 / Granular Engine
2. Freeze / 极短循环停留
3. 正放、倒放与随机方向的实时再合成
4. 节拍同步的 Audio Grain Sequencer（下文简称 **Audio ARP**）
5. 解构型 Delay / Reverb / Filter / Random Modulation
6. Dry/Wet、输出增益、软限幅、旁通与预设/场景
7. MIDI Map / Push 可控制的关键参数

### P1：首版稳定后扩展

1. 频谱冻结（Spectral Freeze）与频带独立重组
2. 音高追踪触发、瞬态触发、侧链包络触发
3. 录制较长 phrase loop、Overdub、Undo
4. 多声道 / MPE 控制扩展
5. 自定义 Jitter 视觉皮肤与外部投影模式

### 明确不纳入 v1

- 完整 DAW 级别采样器、切片编辑器或波形文件管理器。
- 自动“智能作曲”或基于云端模型的声音生成。
- 未经性能验证的高 FFT 尺寸频谱链路默认常开。

---

## 4. 模块规格

### 4.1 输入、捕捉与循环缓冲区（Capture Buffer）

**目标：** 始终保存最近一段输入音频，Freeze/Grain/Reverse 都从此缓冲区读取。

- 立体声输入 / 输出；以 Max for Live Audio Effect 的 `plugin~ → plugout~` 为宿主主链。
- 默认滚动缓冲：10 秒；设置范围建议 1–30 秒。
- 可选 Capture Mode：
  - **Continuous：** 永久写入最近音频，适合现场抓取。
  - **Manual：** 按 Capture 后锁定一个片段。
  - **Transient：** 只在超过阈值的瞬态附近抓取，P1。
- 写入与读取必须分离，Freeze 时停止“读头参考点”移动，不强制停止输入写入。
- 支持与 Live 全局速度同步；节拍单位可用 1/64、1/32、1/16、1/8、1/4、1/2、1 Bar。

**关键参数**

| 参数 | 建议范围 | 说明 |
|---|---:|---|
| Buffer Length | 1–30 s | 输入历史长度 |
| Capture | Trigger / Latch | 手动抓取或持续抓取 |
| Quantize | Off–1 Bar | Capture 和 Freeze 的节拍量化 |
| Input Gate | -∞–0 dB | 防止静音/噪声被误捕捉；P1 可加入 |
| Source | Live Input / Captured | 选择直通源或已锁定缓冲 |

### 4.2 粒子采样器（Granular Engine）

**目标：** 把缓冲区中的声音切成多个短片段，并以重叠、移位、变速和随机方式实时再合成。该模块是产品声音身份的核心。

参考方向：Arturia Efx FRAGMENTS 的“切分、变形、重组”思路；Hologram Microcosm 的重叠 micro-loop、sequenced samples 与粒子化氛围思路。只参考交互与声音类别，**不复制其算法、界面、预设或商业素材**。

**必须具备的粒子参数**

| 参数 | 建议范围 / 取值 | 行为要求 |
|---|---|---|
| Grain Size | 5–500 ms | 5–30 ms 偏颗粒/噪点；100 ms 以上偏可辨识切片 |
| Density | 1–80 grains/s | 密度提高时自动做总增益补偿，避免越叠越响 |
| Position | 0–100% | 在当前 Capture Buffer 中定位读取区域 |
| Position Jitter | 0–100% | 对每粒起点施加受控偏移 |
| Pitch | -24–+24 semitones | 需平滑、可量化到半音/音阶 |
| Pitch Random | 0–24 semitones | 可锁定到 Scale，P1 |
| Direction | Forward / Reverse / Alternate / Random | 每粒或每步决定方向 |
| Spray | 0–100% | 分散粒子起点与触发时间 |
| Shape | Hann / Triangle / Exponential | 粒子窗函数；默认 Hann 防止点击声 |
| Voices | 1–16 | 限制并发粒子数，作为 CPU/质感控制 |
| Stereo Spread | 0–100% | 粒子在 L/R 间分布；单声道兼容须可测 |
| Grain Mix | 0–100% | 粒子层相对直通信号的比例 |

**质量要求**

- 粒子起止点必须应用窗函数，且参数变化需做 5–30 ms 平滑，避免 click/pop。
- 启用 Reverse、改变 Size 或切换 Grain 模式时，不得中断正在播放的粒子；新参数从后续粒子生效。
- 至少提供三种引擎模式：
  1. **Cloud：** 自由密度的粒子云；
  2. **Rhythm：** 严格跟随 Live 节拍的触发；
  3. **Stutter：** 小窗口内快速重复，适合 glitch。

### 4.3 Freeze / Pause / 微循环（Freeze Loop）

**目标：** 复现“播放时点住某一瞬间，声音持续停留在那里”的音乐性效果。实现不是系统暂停，而是将当前读区锁定在极短循环内并持续再合成。

**交互定义**

- **Momentary Freeze：** 按住时冻结，松开时平滑释放回实时输入。
- **Latch Freeze：** 点击切换冻结/释放；适合现场无需长按。
- **Auto Freeze：** 按节拍或阈值自动抓取，P1。
- Freeze 点应以当前时间为中心抓取，而不是简单从固定缓冲起点开始。

**关键参数**

| 参数 | 建议范围 | 说明 |
|---|---:|---|
| Loop Length | 1–2,000 ms / 节拍值 | 最低可到 1 ms；默认建议 30–120 ms，实际最小安全值由采样率校验 |
| Loop Position | 0–100% | 冻结后可扫描缓冲区位置 |
| Crossfade | 0–100 ms | 循环边界交叉淡化，默认 10 ms |
| Hold Mode | Static / Drift / Scan | 固定、缓慢漂移或持续扫描 |
| Release | 5–500 ms | 从冻结回到直通/粒子模式的淡出时间 |
| Quantize | Off–1 Bar | Freeze 开始和释放对齐节拍 |

**重要技术约束**

- “最小值极小”不等于必须使用 1 个采样点硬循环。极短循环会出现明显 DC、aliasing 或高频尖叫；产品应允许 1 ms 的界面值，但内部根据采样率、交叉淡化与保护阈值作安全钳制。
- Freeze 与 Grain 可以串联或并联：默认 **Freeze → Grain**，即先锁住材料，再颗粒化；高级路由可让 Grain 输出进入 Freeze。

### 4.4 再合成、正放与倒放（Resynthesis / Direction）

**目标：** 当声音处于粒子或循环状态时，立即切换正放、倒放或混合方向；这是现场演奏的主要手势。

- Forward：正常读头递增。
- Reverse：读头递减；正常速度为 -1 倍。
- Alternate：每一粒或每一节拍交替方向。
- Random：按 `Direction Probability` 决定每粒方向。
- Rate：-2.0 到 +2.0 倍；0 不作为普通“暂停”，应保留 Freeze 语义。
- Pitch 与 Rate 独立：首版允许其部分耦合，但必须在 UI 写清楚；“时长不变变调”属于 CPU 更高的高质量模式，应列为 P1 或 Quality 开关。

### 4.5 Audio ARP：音频粒子琶音/步进重组

**结论：** 作为 Audio Effect，v1 不应把“Arpeggiator”误做成 Live 原生 MIDI Arpeggiator 的复制品。Ableton 原生 Arpeggiator 是处理 MIDI 音符的 MIDI 效果器；本产品定位是处理**已经进入轨道的音频**。因此 v1 的正确实现是 **Audio ARP / Grain Sequencer**：用 Live transport 驱动粒子/循环窗口的节奏化重触发、音高步进、方向和概率。

**v1 功能**

| 参数 | 建议范围 / 取值 | 行为 |
|---|---|---|
| Rate | 1/64–2 Bars | 跟随 Live 速度的步进速率 |
| Steps | 1–16 | 每个 Scene 的步数 |
| Pattern | Up / Down / Up-Down / Random / Custom | 决定音高、位置或方向的序列 |
| Gate | 5–100% | 每步粒子/循环的发声长度 |
| Swing | 0–75% | 偶数步偏移 |
| Probability | 0–100% | 每步是否触发 |
| Octave / Pitch Range | 0–3 oct / ±24 st | 步进音高范围 |
| Direction Lane | Fwd / Rev / Alt / Random | 独立的方向序列 |
| Position Lane | 0–100% | 每步可读取不同缓冲位置 |
| Reset | Bar / Note / Manual | 重置相位 |

**扩展边界**

- 若用户确实需要“输入和弦 → 输出 MIDI 琶音”，应另做一个独立的 Max for Live MIDI Effect，或配套 Instrument 版本；不要把它混入此 Audio Effect 的核心链路。
- P1 可增加 Sidechain MIDI Trigger：用外部 MIDI 轨道作为 Audio ARP 的节奏/移调控制源，具体可行性需在目标 Live/Max 版本内验证。

### 4.6 解构型空间与调制效果（Deconstruction FX）

这个模块的审美参考是 Fors Kit 中 Box 的“feedback、distortion、filtering 使信号劣化和远离”的方向，以及 Ego 的 grainshifting/diffusing delay；目标不是做传统干净混响，而是实现可从延迟变形到失真的空间团块。

#### A. Diffuse Delay

- 多 Tap / Ping-Pong / Random Tap 三种模式。
- 时间：1–2,000 ms 或节拍同步；反馈：0–95%，超过 85% 必须出现安全提示/自动保护。
- 每个回声可施加轻微粒子移位、Pitch Drift、滤波和扩散。
- 支持 Freeze Feedback：让尾音停留，但受软限幅保护。

#### B. Degraded Reverb

- 算法方向：扩散延迟网络（FDN）或多级 allpass/comb 结构；不要求卷积混响。
- 核心参数：Size、Decay、Diffusion、Tone、Pre-delay、Drive、Freeze。
- 加入“Deteriorate”宏控件：同时推动反馈、失真、低通、扩散与随机漂移，但必须限制最终输出。

#### C. Random Filter / Scan

- 滤波类型：LP / BP / HP / Notch。
- 可对 Cutoff、Resonance、Pan、Rate、Grain Position、Pitch 任选目标施加调制。
- 调制源：Sine、Random Smooth、Random Step、Envelope Follower、Transport LFO。
- 随机变化必须以 Slew/Glide 平滑；禁止直接跳至高共振点。
- 应有 `Amount`、`Rate`、`Range`、`Seed/Lock` 四个最小控制，保证可复现。

### 4.7 路由、宏控件、场景与安全输出

- 默认路由：`Input → Capture → Freeze → Grain → Audio ARP → Delay/Reverb/Filter → Limiter → Output`。
- 高级页允许把 Grain 与 Freeze 互换、让 Delay 进入 Grain、选择效果前/后 Capture；v1 只开放经过测试的有限路由，不提供任意反馈矩阵。
- 全局参数：Input Trim、Dry/Wet、Output Gain、Bypass、Safety、Quality。
- 8 个 Macro，可分配多个目标并设 min/max/curve；适合 Push 和 MIDI 控制器。
- 至少 8 个 Scene 槽位：保存所有参数、可选 0–10 秒插值切换。
- 输出端必须有：DC blocker、soft clipper / limiter、最终音量表与 overload 指示。

---

## 5. 推荐技术架构

### 5.1 分层

```text
Ableton Live Audio Track
  └─ plugin~ (stereo input)
       ├─ Input conditioning / safety
       ├─ Circular Capture Buffer (continuous record)
       ├─ Freeze Loop Engine
       ├─ Granular Engine
       ├─ Audio ARP / transport sequencer
       ├─ Deconstruction FX (delay, reverb, filter, modulation)
       ├─ Dry/Wet + limiter
       └─ plugout~ (stereo output)

Control layer (Max)
  ├─ live.* parameters / pattrstorage / preset scenes
  ├─ transport, tempo, quantize, MIDI mapping
  ├─ state machine and parameter smoothing policy
  └─ diagnostics / CPU-safe voice management

DSP layer (MSP + gen~)
  ├─ buffer~ / data-backed circular recording and reads
  ├─ gen~ for grain scheduling, envelope, interpolation, smoothing
  ├─ MSP objects for stable host-facing routing and utilities
  └─ optional pfft~ spectral module (P1 only)

Visual layer (Jitter, optional)
  ├─ waveform / grain-position / density visualization
  ├─ capped at 20–30 FPS
  └─ never blocks or carries audio processing
```

### 5.2 实现选择

| 子系统 | 首选实现 | 原因 |
|---|---|---|
| 宿主音频 I/O | `plugin~` / `plugout~` | Max for Live Audio Effect 的标准宿主接口 |
| 捕捉/循环 | 环形缓冲区 + 多读头 | 可同时支持最近历史、Freeze、粒子、正放/倒放 |
| 粒子声部 | `gen~` 多 voice 调度或受控 MSP polyphony | 高频触发、包络和插值更适合在 DSP 层执行 |
| 延迟/扩散 | `gen~` 或 MSP delay 网络 | 能保持低延迟与可控反馈 |
| 频谱模块 | `pfft~` + `gen~` | 只在 P1 开启，因 FFT 会带来算法延迟 |
| 控制与预设 | `live.*` + `pattrstorage` | 可自动化、可存 Live Set、可映射 Push/MIDI |
| 可视化 | Jitter | 只承担波形/粒子状态可视化，确保关闭后声音不变 |

### 5.3 状态机

```text
LIVE
  ├─ Capture ──> CAPTURED
  ├─ Freeze Press ──> FREEZE_MOMENTARY ──release──> LIVE
  └─ Freeze Latch ──> FREEZE_LATCHED ──toggle──> LIVE

任一播放状态
  ├─ Grain On/Off
  ├─ Audio ARP On/Off
  ├─ Direction: Fwd / Rev / Alt / Random
  └─ Safety Trigger ──> SAFE_BYPASS / gain ramp-down
```

所有状态切换都必须经过 gain ramp、读头交叉淡化和参数平滑；不允许直接断开 MSP 音频线来实现“暂停”。

---

## 6. 界面与演奏设计

### 6.1 单页工作界面

界面不应塞入所有参数。建议采用四区布局：

1. **Performance Strip（顶部）**：Capture、Freeze（大按钮）、Reverse、ARP、Bypass、Input/Output meter。
2. **Sound Core（中部）**：Grain Size、Density、Position、Pitch、Spray、Loop Length 六个主旋钮。
3. **Motion & Space（下部）**：Rate、Probability、Filter Scan、Delay Feedback、Space、Deteriorate。
4. **Detail Drawer（折叠）**：窗函数、声部数、读头模式、随机种子、路由、质量设置与调试信息。

### 6.2 可视化原则

- 中央 Jitter 视图显示滚动波形、当前冻结区、粒子读头与 ARP 步进位置。
- 可视化是演出反馈，不承担精确剪辑工作；低 CPU 模式可一键关闭。
- 手势含义固定：蓝/紫色不作为唯一信息通道；必须兼容 Live 深/浅色主题及色盲可读性。

### 6.3 硬件控制

- 所有 P0 参数应通过 Live 的参数系统暴露，支持自动化和 MIDI Map。
- Freeze、Reverse、Capture、Scene Next/Prev 必须有离散触发入口。
- Push 映射优先级：第一页为 Performance Strip + Sound Core；第二页为 Motion & Space。

---

## 7. 性能、稳定性与验收标准

### 7.1 兼容性基线

- 目标宿主：Ableton Live Suite 12.x（兼容性向下验证可覆盖 Live 11.x）。
- 目标运行时：与目标 Live 版本匹配的 Max for Live / Max。
- I/O：首版固定双声道；不假设多声道音频效果器支持。
- 测试采样率：44.1 kHz、48 kHz；缓冲区：64、128、256 samples。

### 7.2 必须验收

1. **无静音问题：** 设备启用、旁通、重载预设和切换场景均能持续输出正确的立体声。
2. **无明显爆音：** 在 64/128 samples 下连续快速触发 Freeze、Reverse、Capture、ARP 时，不出现明显 click/pop；允许的异常必须记录波形并修复。
3. **节拍一致：** Quantize=1/16 时，Freeze 与 ARP 触发相对 Live 网格的偏移可重复、可测量。
4. **延迟正确声明：** 纯时域模式不得虚报延迟；若 P1 使用 FFT 或 look-ahead，必须向 Live 声明其算法延迟，以免与其他轨道失对齐。
5. **反馈安全：** Feedback / Reverb Freeze / 高 Resonance 的组合不会无限增益或损坏监听；过载时限幅器可控，屏幕有明确指示。
6. **预设可复现：** 保存/重开 Live Set 后，Scene、随机锁定、缓冲模式、参数值一致；对实时 buffer 内容是否保存需明确标注。
7. **CPU 降级：** 声部数/质量过高时，优先减低新粒子密度或禁用可视化，不得导致整个 Live 音频引擎失稳。

### 7.3 性能门槛的定义方式

不要先写一个无法验证的“CPU 占用百分比”。开发 Agent 必须先在指定基准电脑和 48 kHz / 128 samples 下测出：

- 基础直通；
- 8 声部粒子；
- 16 声部粒子 + Audio ARP；
- 全部 FX + Jitter 开启；
- 5 分钟连续 Freeze/Feedback 压力测试。

然后将测量结果写入 README，并把 v1 的默认 Voice 数和 Quality 设为能稳定通过该测试的档位。

---

## 8. 参考方向与边界

| 参考对象 | 可借鉴点 | 不应复制的内容 |
|---|---|---|
| Arturia Efx FRAGMENTS | 粒子处理作为独立、可演奏的声音塑形模块 | 算法、界面、命名、预设与素材 |
| Hologram Microcosm | micro-loop、Hold、正/倒放、节拍同步、粒子序列化、解构空间的功能组织 | 具体模式、产品视觉、预设与交互细节 |
| Fors Kit：Box / Ego | Box 的 feedback-distortion-filter 劣化空间；Ego 的 grainshifting/diffusing delay 思路 | 具体 DSP 实现、界面与商业资源 |
| Ableton 原生 Arpeggiator | Rate、Gate、Pattern、Swing、同步的控制语言 | 将 MIDI Arpeggiator 误称为音频效果功能 |

---

## 9. 开发 Agent 工作说明（可直接转交）

> 制作一个名为 **Experimental Sound Sculptor** 的 Max for Live Stereo Audio Effect。它不是普通多效果器，而是面向实验电子音乐与现场演出的实时音频捕捉、Freeze、粒子再合成、反向重组和节奏化解构工具。
>
> 使用 `plugin~` / `plugout~` 作为标准立体声宿主 I/O。核心 DSP 用 MSP 与 `gen~` 实现：持续环形 Capture Buffer、多读头 Freeze Loop、可控多声部粒子引擎、正放/倒放、Audio Grain Sequencer、扩散延迟/解构混响/随机滤波调制。Max 负责控制状态、Live 参数、预设/Scene、节拍量化和 MIDI Map；Jitter 只用于可关闭的波形与粒子读头可视化，绝不放在音频链路。
>
> v1 必须完成：
> 1. 1–30 秒实时 Capture Buffer；
> 2. Momentary/Latch Freeze，最小 Loop Length 可到 1 ms，但内部需安全钳制和交叉淡化；
> 3. 5–500 ms、1–80 grains/s、1–16 voices 的粒子引擎，支持 Position、Jitter、Pitch、Spray、窗函数、Stereo Spread；
> 4. Forward/Reverse/Alternate/Random 读向和 -2x–+2x rate；
> 5. 节拍同步的 **Audio ARP**，以 Grain/Loop 重触发实现，不把它伪装为 MIDI Arpeggiator；含 Rate、Steps、Pattern、Gate、Swing、Probability、Pitch/Direction/Position lanes；
> 6. Diffuse Delay、Degraded Reverb、Random Filter/Scan，带 Feedback、Drive、Diffusion、Deteriorate 宏控件；
> 7. 8 宏、8 Scene、Live 自动化/MIDI Map/Push 映射、安全限幅和低 CPU 可视化开关。
>
> 所有状态和参数变化必须使用平滑、窗函数、交叉淡化或增益 ramp，保证连续快速触发 Freeze/Reverse/Scene 时没有明显爆音。先完成可测的 P0 音频链和最小界面，再扩展频谱冻结、侧链/MIDI 触发和 phrase looper。每完成一个模块，提供 `.amxd`、依赖清单、测试工程和验收说明；不得使用未经许可的第三方专有算法、素材或界面资产。

---

## 10. 开发前仍需你确认的 6 个决定

1. **名称：** 使用 Experimental Sound Sculptor 作为工作名，还是你已有正式名称？
2. **Freeze 的主要手势：** 你更常用按住触发，还是点击锁定？首版可都做，但默认行为应定一个。
3. **声音倾向：** 优先“干净、可辨识的微粒节奏”，还是“脏、失真、快速崩解的氛围”？这决定默认窗口、反馈和宏控件曲线。
4. **Audio ARP 之外：** 是否确定后续再单独制作一个真正的 MIDI Arpeggiator companion device？
5. **硬件：** 需要优先适配 Push 3、Push 2、脚踏开关，还是普通 MIDI 控制器？
6. **目标环境：** 你的 Ableton Live 版本、Max 版本、电脑芯片和常用 buffer size，需要在开始制作前锁定，才能真实验收低延迟性能。

---

## 11. 资料来源（用于技术判断与功能参考）

1. Cycling '74, *Creating Audio Effect Devices*：Max for Live Audio Effect 的 `plugin~` / `plugout~` 双声道宿主约束，以及算法延迟需向 Live 声明的原则。  
   https://docs.cycling74.com/max8/vignettes/live_audiodevices
2. Cycling '74, *groove~ Reference*：buffer 读取、循环、负速率倒放、变速与 loop interpolation 的能力参考。  
   https://docs.cycling74.com/max8/refpages/groove~
3. Cycling '74, *Gen*：`gen~` 用于低层、高效音频处理与即时反馈的官方定位。  
   https://docs.cycling74.com/max8/vignettes/gen_topic
4. Ableton, *Live MIDI Effect Reference*：原生 Arpeggiator 属于 MIDI note 效果，作为本报告区分 Audio ARP 与 MIDI ARP 的依据。  
   https://www.ableton.com/en/manual/live-midi-effect-reference/
5. Hologram Electronics, *Microcosm*：micro-loop、Hold、正/倒放、节拍同步、颗粒与延迟/混响的功能方向参考。  
   https://www.hologramelectronics.com/pages/microcosm
6. Fors, *Kit*：Box 的解构混响（feedback、distortion、filtering）与 Ego 的 grainshifting/diffusing delay 方向参考。  
   https://fors.fm/kit
7. Arturia, *Efx FRAGMENTS*：粒子化声音塑形作为产品类别与交互方向的参考。  
   https://www.arturia.com/products/software-effects/efx-fragments/resources
