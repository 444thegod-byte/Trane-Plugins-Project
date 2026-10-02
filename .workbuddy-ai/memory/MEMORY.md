# Träne 项目长期记忆

> 细节在 `memory/YYYY-MM-DD.md`；完整 UI 规格在 `outputs/Trane_UI_v0.30_实现规格书.md` §1–§21。上限 3000 字符。

## 路线与约定
- 本 repo 的修复通过验证后，必须从 fork 分支提交 PR 到上游 `444thegod-byte/Trane-Plugins-Project`，读回目标与状态；只开 fork 内部 PR 不算完成。不自动合并（2026-09-30 用户要求）。
- 主路线 = VST3（09-24 已推翻 M4L）；`src/*.maxpat` 保留但不是主路线。实用性第一，宁可报错不许糊弄；先量、复现、再改。
- 用户可见改动必须 bump 版本号且可回归、可解释。用户数据只读；测试写 `/tmp`；阈值必须有实测依据，注释写依据。

## 可验证性
- `TranePanel` 不依赖 `juce_audio_processors`、不碰文件系统；只收 `PanelState`，读文件归 `PluginEditor`。`panel_probe` 用同一绘制代码离线渲 PNG。
- 几何/颜色/控件表只有一份事实来源：`vst/plugin/TranePanel.h`；工具一律从 `--dump-geometry` / `--dump-layout` 读，**不许自己抄常量**。
- 反向对照的「红」必须是**断言**在红：崩溃/节点名失效/环境问题对任何输入都非 0，不算证据。五个对照器都有前置检查（干净源码先绿），只认 `✗`/`FAILED`。
- **前置检查按成本排序**：五个对照器现在先验"锚点在源码里唯一"（纯静态，0.00s），再跑"检查器先绿"（要渲染十几张图）。原来锚点断言写在突变循环里，v0.35 实测**白跑 8 分钟**才停在一条被版面改动碰掉的锚点上。
- **检查器输出要逐条立刻打印**，不许攒到最后 dump —— 后面一步抛异常会把已报红的行吃掉，对照器判"没抓住"，其实抓住了。
- **一条突变漏了网，先问它是不是真的坏**：v0.35 的「直径调大一档」漏网，查下去发现那处改动**是合法的**（净空 4.60 仍 ≥ 环粗 3.0）—— 但顺着它翻出一个真缺的住户（见 UI 节）。
- **删功能 = 删断言 = 删锚点 = 改 pytest 节点名**，一起做；锚点可能横跨 `.h` 与 `.cpp`，两边都要备份还原。
- 反向对照的骨架与七条规矩已沉淀成用户级 skill **`reverse-control-harness`**（别的领域做变异对照也用它）。

## UI（VERSION 0.35）
- 1440×720，两层（底图缓存 + 前景）；参数铺满四栏 `{0,1}{2,3,4}{5,6}{7,8,9}`，栏内各自撑满高度。字号 13/12/11；四态只改颜色不改几何；无卡片/渐变/阴影；hover = 160ms ease-out 淡入。**v0.32 起不画蓝色聚焦环**，`#0A84FF` 仅作平台语义/突变对照。**面板不显示 UI 版本号**（2026-09-30 定；对账靠 `ui_version` + 出图文件名）。设计 brief 在仓库根 `.impeccable.md`，**已对齐 v0.35**（字体/旋钮两条与实现一致）。
- **分组靠"框"不靠留白**（v0.34 的 `kSectionGapMult` 已删）：每模块一个容器 = 块底（`kInk @ 0.055`）+ 发丝框线（`@ 0.11`，**压在块底上**，不是面板底上），圆角 10，`kBlockPadX/Y = 14/12`，`kBlockGap = 15`（绝对 px 可以，容器自带边界）。内容从**框内**起：所有"填满一栏"的判据基准是 `栏宽 − 2×padX`。
- **形态按模块分配**（`kKnobIds[]` → `kKnobModules[]`，5 个模块）：前五级（freeze/grain/stutter/comb/tape）整块旋钮，后五级（ruin/sweep/delay/space/out）条形 + 1 个分段块。判据一句话：**这个模块是"调到目标"还是"设个量"**。`isKnob(控件) = 模块在清单里` → 同模块内一致性是**构造保证**，"连续"那条断言已删。**含 `Fmt::Choice` 的模块不许进旋钮清单**（否则检查器找不存在的环 → 假报红）。
- **直径跟字号走、行距跟栏走是两个独立决定**。规则：**相邻旋钮净空 ≥ 环粗**。`kKnobDia = kFsName × 2.4`（26.4px，净空 6.80 ≥ 3.0）；**2.8 会撞车**（净空 2.40）。这条是**常量算术**，抓不到"改 kKnobDia"（两边同源）—— 所以另有一条「**旋钮环外径 == 声明**」（轨道区逐行横扫取最宽行，实测 20 个 29.00–29.50 对声明 29.4），抓的是**画笔与 dump 分叉**。
- **字体 = 打包的 Inter 静态实例**（`assets/fonts/TraneSans_*.ttf`，OFL-1.1），经 `createSystemTypefaceFor` 建成 Typeface。Lux Cache 用的是商业授权的 Suisse Neue，**不可打包**。源码里**不许再出现 Ableton 字体路径**。换字体只改文字墨迹、**不改任何几何** → 唯一判据是 dump 的 `font_ui`/`font_data`（自述名 + 实测探针宽度，测试用 fontTools 从 hmtx 复算）。
- **数值列宽 = 实测最宽串**（`getStringWidth`，201 点扫描），不是 `字符数 × 系数 × 字号`；`kValueW` **已删不许加回来**。
- 工具新增行：`--dump-geometry` 的 `choices` / `knob_dia` / `knob_modules` / `block_fill` / `block_edge`（**逐层合成**，别按"压在纯黑上"算）/ `block_geom`；`--dump-layout` 的 `gap` / `padx` / `block`（末位 = 该模块是否全旋钮）。对照器：`check_knobs_mutations.py`（**9 处 / 4 检查器**）；出对照图 `tools/make_version_sheet.py --new 0.35 --old 0.34`。
- **文字对比度登记表**：`textLog()` → `--dump-text`，测试独立复算 WCAG（最暗 5.06:1）。已按下/已选中的格子**不叠墨层**。**面板上一个字都不许写非 ASCII**（唯一例外：亮度乘号 U+00D7，JUCE 要 `String::charToString(0x00D7)`，`"\u00D7"` 会被按 Latin-1 拆成两个字符）。

## 动画 / 背景图 / 每帧成本
- 动画由 `juce::VBlankAttachment` 驱动（不是 Timer），目标 30Hz；`nextFrameSec_` 从实际呈现时刻重算。**不要再做空闲降帧**（v0.32.2 的 15Hz 就是"生硬"主因）。每帧 ~1.2ms @2880×1440（门槛 20ms）。
- CG 贴图：目标矩形**必须吸附整数设备像素**（否则慢 70 倍）；避开 `setOpacity`，用 `drawImageTransformed(..., true)`，省 55%。
- 背景落位区 = 常量 `bgRegion()` = 参数区（40..1400），`bg_region` 与 `pane` 必须相等；明暗度 0.25–4.0 几何级数（峰值 88，对白字 5.97:1），四边羽化 64px。
- 两级缓存 `bdScaled` + `backdrop`；明暗度用**原地整数乘**（比 `setOpacity` 快 4.6 倍）。冷 21ms / 热 1.5ms；**绝对门槛与相对判据缺一不可**。状态只在 `apvts.state` 根属性存路径/落位/明暗度，不存图。

## VST3 工程
- `core/`（无 JUCE DSP）→ `probe/` → `plugin/`。控件 48（41 参数+7 开关）+ 自动 Bypass=49；显示名唯一，逐条对账 `createLayout()`。
- DSP：有限缓冲停转必须同时停写头；调制拆成匀速位置+有界偏移；前瞻 limiter 自己实现 bypass 与延迟。
- 门禁 `cd vst && ./run_tests.sh`；稳定性用晚段/早段 RMS 比 ≤1.15。打包 `tools/make_installers.sh <版本>`（校验 CMakeLists 版本、pkg 打用户级、比对 sha256）。

## 环境与仓库
- cmake/ninja 在 `/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin`；pytest 每次用新 `/tmp` basetemp。
- `juce::String{char*}` 按 Latin-1，中文命令行路径必须 `String::fromUTF8`；编辑报告成功不等于落盘，改后立刻读回（**同一文件在一个消息里连发多个编辑会丢**，逐个来）。
- 私有仓库 `github.com/444thegod-byte/Trane-Plugins-Project`；JUCE 不入库，按 `setup_juce.sh` 锁 commit `7278278`。
