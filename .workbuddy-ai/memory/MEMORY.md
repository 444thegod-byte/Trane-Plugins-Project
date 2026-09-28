# Träne 项目长期记忆

## 路线（2026-09-24 已定）
**主路线 = VST3，不是 Max for Live。** 小绪已明确授权推翻 M4L。
理由不是性能，是**可验证性**：Max 依赖 iLok + Java，无法在自动化环境启动，
只能静态验证接线 → Freeze 连错两轮都发现不了（根因是把 message 接进了 `record~`
的音频信号入口 0）。VST3 可以编译、离线渲染、用数学方法检验输出。
`src/*.maxpat` 保留但已不是主路线。

## 工作约定（小绪定的）
- **实用性第一**：所有功能必须真的有用、能跑；宁可报错不许糊弄。
- **报错要报得对**：自检说的和实际做的必须一致。"报得不对比不报还糟"。
  推论：**测试不能空转通过**。正则匹配不到就 assert 数量下限，别让循环体一次都不执行还显示绿。
- 改动要**可回归、可解释**；他会 dogfood 好几轮再定稿。
- 改动用户可见的东西**必须 bump 版本号**。
- 他的数据只读；测试一律写 `/tmp`。
- **先量，再改。** 他说"不对/没效果"时不要猜，去采样、去复现、去量出事实。
- 所有阈值都要有实测依据，不能拍脑袋。断言注释里写实测值。

## 仓库（2026-09-28 建立）
`https://github.com/444thegod-byte/Trane-Plugins-Project`（**私有**，账号 `444thegod-byte`）。
仓库名去掉了变音符与空格——GitHub 不允许，`Träne` 的正确写法保留在 description 与 README 标题。
- **JUCE 不进仓库**：用 `vst/setup_juce.sh` 按精确 commit 拉（9.0.2 @ `7278278`）。
  锁 commit 不锁 tag，因为 **tag 可以被移动**；拉到后校验不符即报错退出。
- 不进仓库的还有：`vst/build/`、`vst/.pytest_tmp/`、`outputs/*.wav`、`outputs/*.zip`、`outputs/*/`。
- **这台机器上 GitHub 官方集成没有建仓权限**（403）。要用 `/tmp` 下的 gh 单文件发行版，
  且 `brew install gh` 会被沙箱拦。工具路径与推送命令见 `2026-09-28.md`。
- **推送后必须核对**：比对提交哈希 + 逐文件 blob 哈希 + 二进制独立 sha256。
  光看 `git push` 成功不够。

## VST3 工程（`vst/`）
- 三层：`core/`（DSP，**不依赖 JUCE**，可独立编译与离线渲染）→ `probe/`（离线测量台）
  → `plugin/`（JUCE 外壳，薄）。
- 信号链：`capture → freeze → grain → ruin → sweep → delay → space → limiter`。
- **`LookaheadLimiter` 必须带前瞻**：反馈式限制器对瞬态必然过冲
  （实测 +4.8dB 时峰值 1.0062）。前瞻 2ms + 单调队列最小增益，数学上不可能过冲。
  **代价是 2ms 延迟 → 必须 `setLatencySamples()`，并且必须自己实现 `processBlockBypassed`**
  （JUCE 基类版本假定延迟为 0，会把干声往前推）。
- `FreezeLoop` 的无缝算法：在循环末尾 seam 个样本里把**循环起点之前**的真实音频淡进来，
  于是环绕那瞬是 `buf[S-1] → buf[S]`，原本就连续。**反证成立**：关掉淡化 → 跳变 0.266936。
- 粒子/扫频的随机数必须**固定种子**（xorshift），否则渲染不可复现、无法回归。
- **不要给 `metro` 加 `@quantize`**（M4L 遗留教训：transport 停住时量化边界永不到达）。
- 通用二进制：`CMAKE_OSX_ARCHITECTURES = "arm64;x86_64"`（M4 + Intel i5 双机）。
- 界面面板 **780 × 432**，4 行 10 组 48 控件。**纯黑底 + 全部 Helvetica Neue +
  0.5px 发丝线描边，只有黑白两色**，靠 4 档不透明度分层
  （0.14 轨道 / 0.28 线框 / 0.55 次文字 / 0.92 主文字）。Lux Cache 风：全小写、极简、大量留白。
- 验证门槛：`cd vst && ./run_tests.sh`（构建 → pytest **77 项** → 端到端验收）必须全过。
- **参数显示名必须唯一**（宿主按名查找只认第一个；撞名会让端到端验收静默跳过），
  有静态回归测试盯着。内部 ID 可以随便改，显示名不行。
- **任何"暂停/冻结/停转"功能，只要缓冲有限，就必须同时停住写头** ——
  否则写头绕回来覆盖读头位置，停转自己复活。真磁带停住读到的是不变的静态磁化。
- **调制不许乘在推进速率上**（会被积分成无界漂移，撞限位后变成单侧摆动）；
  一律拆成"匀速位置 + 有界偏移"。
- **v0.10 UI 定稿约定（2026-09-24）**：目标改为 Ableton Live 原生平面设备，不再走 Lux Cache。
  删除所有装饰性标题、功能清单与运行状态文字；只显示模块标题、参数、数值、开关。
  面板 860×438，48 控件/10 组不变；旋钮 = 实心平面盘 + 1px 轮廓 + 三刻度 + 高亮指针，
  禁止值弧、渐变、阴影、圆角卡片。主白 1.00，标签 0.84，线 0.48。
- **字体不能假装**：用户的 Ableton Live 12.app 内实际有 `AbletonSans-Bold.otf` 与
  `AbletonSansMedium-Regular.otf`。运行时只读取本机 App，绝不复制/打包字体；找不到时降级
  Helvetica Neue Bold。`ui()`=Bold 标签/开关，`data()`=Medium 数值，`createSliderTextBox()`
  必须覆写，不能只让预览图看起来像。
- UI 静态防线现在 10 项；总验收 82 项。新预览要从真实 C++ 坐标生成 SVG 后 headless Chrome 2x
  截图，不能手画。
- **稳定性判据不能写"末段安静"**：喂连续白噪声时输出永远不会安静，
  要写"晚段/早段 RMS 比 ≤ 1.15"。

## 环境坑（都踩过）
- **`cmake` / `ninja` 在 python venv 里**，裸命令不在 PATH：
  `export PATH=/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin:$PATH`
- **pytest 的 `--basetemp` 必须每次开新的 `/tmp` 目录**（`mktemp -d /tmp/trane_pytest.XXXXXX`）。
  pytest 会先删掉已存在的 basetemp，沙箱拦下这个删除 → **全部测试在 setup 阶段集体 ERROR**，
  看起来像代码崩了。固定 `.pytest_tmp` 第一次能过、第二次全红。
- **C 字符串里的中文引号必须用 `「」`**，用 `""` 会截断字符串（踩过两次）。
- JUCE 9：`addDefaultFormatsToManager(fm)` 取代 `addDefaultFormats()`；
  `fillRoundedRectangle` 不是 `fillRoundedRect`；`createWriterFor` 改吃 `AudioFormatWriterOptions`。
- `OwnedArray::removeAndReturn(i)` 才真正转移所有权；`add(std::move(a[0]))` 会双重所有权 → 野指针。
- 头文件要同时 include `juce_audio_processors` 与 `juce_gui_basics`，
  否则 `AudioProcessorEditor` 基类未定义，报一堆"未声明标识符"。
- `juce::AudioProcessor` 会**自动加一个 Bypass 参数**，所以参数总数 = 自己声明的 + 1。
- 解析探针输出的正则：名字部分禁止含 `=`，数值别用 `[\d.eE+-]+` 大杂烩
  （`=== engine_probe ===` 里的 'e' 会被当成数值）。

## 已证实的 Max/MSP 对象语义（别凭印象推翻，有证据）
- **`record~`**：入口 = 声道数 + 2（0..ch-1 信号，ch = 录音起点 ms，ch+1 = 录音终点 ms）。有 `loop` 属性消息（**属性消息不列在 refpage methodlist 里，别只看 methodlist 就断定没有**）。
- **`groove~`**：入口 0 = 播放速率（不是别的）；消息 `setloop <起> <终>`、`startloop`、`endloop`、`stop`、`reset`。
- **`snapshot~`**：bang 必须接入口 0（入口 1 是上报间隔）。
- **`metro @quantize`**：transport 停住时量化边界永不到达 → 依赖它的东西会静默不响。
- **`live.tab` / `live.menu` 的条目只能来自 `parameter_enum`**（实测 53/53，`append` 消息 0 例）。
- **`live.tab` 的 `parameter_mmax` = 项数 − 1**；带枚举的 tab 用 `parameter_type: 2` + `parameter_unitstyle: 9`。
- **`live.*` 的 `set` 消息接受序号，不接受条目名**。
- **`live.*` 进出口数（refpage 实测）**：`live.dial` 1进2出 `["", "float"]`；`live.toggle` 1进1出；`live.tab` 1进3出 `["", "", "float"]`；`live.menu` 1进3出；`live.text` 1进2出。
- **`live.dial` 出口 0 = 声明范围（mmin–mmax）内的真实值**，中间不需要换算对象。
- **`parameter_unitstyle` 枚举**：0=整数、1=小数、2=毫秒、3=Hz、4=dB、5=百分比、6=Pan、7=半音、8=音分、9=索引/MIDI。
- **Max `trigger` 从右往左触发**。
- **Max 无法无界面启动**（依赖 iLok + Java）→ 只能静态验证。

## .amxd 格式（已完整逆向，173 个真实文件验证，142 个字节级往返一致）
- 头 12 字节 = `ampf` + LE u32(版本=4) + 4 字节设备标签（`aaaa` 音频效果 / `iiii` 乐器 / `mmmm` MIDI 效果 / `nagg` / `natt`）。
- 之后 = chunk 序列，每个 = 4 字节 tag + LE u32 长度 + 内容。`meta` = LE u32（0=RAW，7=MX；实测 MX 文件 115/115 都是 7）。
- MX 编码 = `mx@c` + BE u32(16) + BE u32(flags) + BE u32(csize) + 数据区 + `dlst` 目录块。
- **一个 .amxd 可含多个 JSON 条目**：主文档 `flag=0x11`，内嵌抽象 `flag=0`；对象名 `X` ↔ 条目文件名 `X.maxpat`。
- `mdat` 是 Mac 纪元（1904）秒数的本地时区修改时间，不是校验和。

## M4L 设备面板规范（实测 105 个可解析的真实 .amxd）
- **音频效果器面板高度固定 169.0**（102/105 符合；越界的是隐藏 `live.toolbar`）。
- **`devicewidth` 才是设备宽度**；内容右缘与 devicewidth 之间留 4–19px 边距。
- **`openinpresentation=1`** 决定设备默认打开 Presentation View（构建器必须强制写，不能被模板骨架覆盖成 0）。
- M4L 版定版尺寸：**650 × 169**（VST3 版是 760 × 350，两码事）。

## 关键文件
**VST3（主路线）**
- `vst/core/`：`CaptureBuffer.h`、`FreezeLoop.{h,cpp}`、`GrainCloud.{h,cpp}`、`PlateReverb.{h,cpp}`、
  `Ruin.h`（含 FOLD）、`RandomSweep.h`、`SpaceDelay.h`、`LookaheadLimiter.h`、
  **`Stutter.h`、`Comb.h`、`Tape.h`**、`TraneEngine.{h,cpp}`
- `vst/probe/`：`freeze_probe`、`reverb_probe`、`engine_probe`、`fx_probe`（6 模式）、
  `vst3_host_probe`（端到端验收）、`wav_io.h`
- `vst/plugin/`：`PluginProcessor.{h,cpp}`（48 个参数）、`PluginEditor.{h,cpp}`（780×432，含 `TraneLookAndFeel`）
- `vst/tests/`：`test_freeze_dsp.py`、`test_engine_dsp.py`、`test_fx_dsp.py`、
  `test_deconstruct_dsp.py`、`test_editor_layout.py`
- `vst/tools/`：`make_test_audio.py`、`analyze_freeze.py`、`render_vst3_panel.py`
- `vst/run_tests.sh`：一键构建 + 77 项测试 + 端到端验收
- 产物安装到 `~/Library/Audio/Plug-Ins/{VST3,Components}/`，通用二进制。

**M4L（已非主路线，保留备查）**
- `src/Trane.maxpat`、`tools/amxd.py`、`tools/patchbuild.py`、`tools/param_meta.py`、
  `tools/verify_patch.py`、`tools/build_amxd.py`、`tools/render_panel.py`
