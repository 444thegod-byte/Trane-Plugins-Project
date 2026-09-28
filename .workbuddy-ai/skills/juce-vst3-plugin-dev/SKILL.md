---
name: juce-vst3-plugin-dev
description: Build, verify, and install a JUCE VST3/AU audio plugin on macOS — the layered core/probe/plugin project layout, CMake setup for a universal arm64+x86_64 binary, the offline-probe → pytest → host-load end-to-end verification loop, and the macOS sandbox gotchas (blocked CodeSignature writes during install, qlmanage unavailable, pytest temp dir). Use when building or iterating on a JUCE/CMake audio plugin, or when a plugin build "fails" only at the install/copy step.
description_zh: "JUCE/VST3 插件的构建、验证与安装工作流（macOS）"
description_en: "Build, verify and install a JUCE VST3 plugin on macOS"
agent_created: true
---

# JUCE / VST3 插件开发工作流（macOS）

## 〇、分层：先定这个，后面全顺

```
core/      DSP 核心，零 JUCE 依赖，编成 STATIC 库
probe/     离线测量台，一个模块一个 main()，链接 core
tests/     pytest：跑 probe、解析输出、断言
plugin/    JUCE 外壳（Processor + Editor），薄，只做接线
tools/     从源码坐标渲染面板预览等辅助脚本
```

**core 不依赖 JUCE 是硬要求。** 只有 DSP 能脱离宿主独立编译渲染，才谈得上毫秒级迭代和自动断言。
一旦 DSP 里 `#include <juce_*>`，验证就只能靠开 DAW 听，这条路就废了。

## 一、环境

```bash
# cmake / ninja 装在 python venv 里，裸命令不在 PATH
export PATH="/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin:$PATH"
PY=/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin/python

cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

一键脚本 `run_tests.sh`：构建 → pytest → 端到端验收；`./run_tests.sh --quick` 跳过构建。

## 二、CMake 关键配置

```cmake
cmake_minimum_required(VERSION 3.22)
project(Trane VERSION 0.9.0 LANGUAGES C CXX)   # ← 用户可见改动必须 bump

set(CMAKE_CXX_STANDARD 17)

# 双机（Apple Silicon + Intel）必须出通用二进制，否则另一台装不上
if(APPLE AND NOT CMAKE_OSX_ARCHITECTURES)
  set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64" CACHE STRING "" FORCE)
endif()

add_library(trane_core STATIC core/*.cpp)
target_compile_options(trane_core PRIVATE -Wall -Wextra -Wpedantic)

juce_add_plugin(TranePlugin
  FORMATS                 AU VST3 Standalone   # Standalone 很有用：不开 DAW 就能听
  COPY_PLUGIN_AFTER_BUILD TRUE                 # ← 会触发沙箱拦截，见第五节
  VST3_CATEGORIES         "Fx"
  AU_MAIN_TYPE            kAudioUnitType_Effect
)
```

**端到端验收台**（这是最有价值的一个 target）：

```cmake
juce_add_console_app(vst3_host_probe PRODUCT_NAME "vst3_host_probe")
target_compile_definitions(vst3_host_probe PRIVATE JUCE_PLUGINHOST_VST3=1)
target_link_libraries(vst3_host_probe PRIVATE juce::juce_audio_processors juce::juce_audio_utils)
```

它把编译出来的 `.vst3` 真的 `createPluginInstance` 加载起来、设参数、渲染、再分析。
证明的是"这个文件能装进 DAW 干活"，而不是"算法写对了"。

## 三、宿主端的参数反解（必踩）

**宿主里拿不到 `NormalisableRange`**，而且参数普遍带 skew（归一化 0.5 ≠ 量程中点）。
想按物理值设参数，只能**二分 + 回读文本**：

```cpp
// 二分 48 次，反解出使 getText() 接近目标字符串的归一化值
float lo = 0.f, hi = 1.f;
for (int i = 0; i < 48; ++i) {
    const float mid = 0.5f * (lo + hi);
    p->setValueNotifyingHost(mid);
    const float got = std::atof(p->getText(p->getValue(), 16).toRawUTF8());
    (got < want) ? lo = mid : hi = mid;
}
```

**参数总数**：框架会自动追加一个 Bypass 参数。断言写 `size() >= 声明数 + 1`，别写等于。

**显示名必须唯一** —— 宿主按名字查参数会拿到第一个同名的。
加一条静态回归测试扫源码里的名字字面量，断言无重复。查找失败要**立即失败**，不许 `continue`。

## 四、验证门槛

```bash
./run_tests.sh    # 构建 + pytest + 端到端验收，必须全过
```

- **pytest 的 `--basetemp` 必须每次开一个全新的 `/tmp` 目录**：
  ```bash
  PYTEST_TMP="$(mktemp -d /tmp/trane_pytest.XXXXXX)"
  "$PY" -m pytest tests/ -q --basetemp="$PYTEST_TMP" -p no:cacheprovider
  ```
  pytest 会**先删掉已存在的 `--basetemp` 目录**。在沙箱下这个删除动作会被拦下，
  于是**全部测试在 setup 阶段集体报 ERROR** —— 看起来像代码全面崩溃，其实是环境问题。
  固定用 `.pytest_tmp` 的写法第一次能过、第二次就全红，非常误导。
- 断言里的阈值必须有实测依据（见 skill `audio-dsp-quantitative-verification`）
- **测试不能空转通过**：解析型测试先 `assert len(items) >= N`

## 五、macOS 沙箱踩过的坑

| 现象 | 真相 | 怎么办 |
|---|---|---|
| 构建报 failed，但 79 个目标全编过、二进制已生成 | 只有 `COPY_PLUGIN_AFTER_BUILD` 那步被拦：写不了 `~/Library/Audio/Plug-Ins/**/_CodeSignature/CodeResources` 与 `PkgInfo` | 逐文件 `sha256` 比对 + `codesign -v` 确认二进制本体已同步，**如实汇报"签名附属文件没写成，二进制已同步"**，别含糊成"构建成功" |
| `qlmanage` 转 PNG 报 `sandbox initialization failed` | 沙箱下不可用 | 把 SVG 包进 HTML（`body{margin:0;background:#000}`），用 headless Chrome 截图：`--headless --disable-gpu --no-sandbox --hide-scrollbars --force-device-scale-factor=2 --window-size=W,H --virtual-time-budget=5000 --screenshot=out.png "file:///tmp/wrap.html"` |
| pytest 第二次运行时全在 setup 阶段 ERROR | pytest 会先删除已存在的固定 `--basetemp`，删除被沙箱拦下 | 每次用 `mktemp -d /tmp/trane_pytest.XXXXXX` 生成新的 `--basetemp`，并带 `-p no:cacheprovider` |
| C 字符串被截断 | 源码里写了中文引号 `""` | 一律改用 `「」` |

## 六、面板预览：从源码坐标渲染，别手画

写一个 `tools/render_panel.py` 直接**解析编辑器源码里的坐标常量**生成 SVG。
图和代码必然一致 —— 不存在"图是画好看的、代码是另一回事"。

顺带的好处：解析器本身要解出符号常量（`kPanelW` / `cell(n)` / `kRowY[]`），
这就强制你把版面参数写成**具名常量**而不是散落的魔数，排版回归测试也才写得出来。

排版回归测试至少覆盖：
- 控件全在面板内、同行控件在网格上（无意外留空）
- 每个分组标题下面确实有控件
- **每个参数都挂了界面控件**（防"某个模块没有面板和旋钮"这类编译期和 DSP 测试都发现不了的问题）

## 七、这条路的由来（为什么不用 Max for Live）

Max/MSP 依赖 iLok + Java，**无法在自动化环境启动**，只能静态验证接线。
结果是一个功能连错两轮都发现不了（把 message 接进了 `record~` 的音频信号入口）。
VST3 能编译、能离线渲染、能用数学方法检验输出 —— 可验证性才是选它的真正理由。
