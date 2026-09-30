# Träne v0.32.1 Bug 修复报告

> 生成时间：2026-09-29  
> 版本：0.32.0 → 0.32.1（patch）  
> 门禁状态：**113 passed / 12 skipped，全绿**

---

## 修复清单

### Bug 1：高频点击 Module 开关失效 / 打不开

**现象**：快速点击模块标题行或圆心时，开关状态不稳定，偶发"打不开"或"一闪就关"。

**根因**：JUCE 双击机制会发送两次 `mouseUp` + 一次 `mouseDoubleClick`。`mouseDoubleClick` 中对标题行执行 `resetToDefault`，把该模块**所有参数**复位到默认值。而开关参数（BoolParam）的默认值是 `false`（关闭）。

高频点击时的时序：
1. 第一次 click：`toggleModule` → 关 → **开**
2. 第二次 click：`toggleModule` → 开 → **关**
3. `mouseDoubleClick`：`resetToDefault` → 开关 = **false（关）**

净效果：开关永远是关闭的。

**修复**：
- `mouseDoubleClick` 中**跳过开关参数**（`Fmt::None`），只复位连续参数和 Choice 参数
- `mouseUp` 中增加 `e.getNumberOfClicks() >= 2` 检测，双击的第二次松手不再执行离散动作（`toggleModule` / `nudgeChoice` / `pickBackdrop`）

**文件**：`vst/plugin/PluginEditor.cpp`

---

### Bug 2：上传背景选择器乱码

**现象**：点击"选择图片"按钮后弹出的系统文件对话框标题显示乱码。

**根因**：`FileChooser` 的标题字符串使用了中文 `"选一张背景图"`，在某些系统区域设置或字体配置下无法正确渲染。

**修复**：标题改为英文 `"Choose Background Image"`。

**文件**：`vst/plugin/PluginEditor.cpp`

---

### Bug 3：hover 参数行时模块圆高亮 / 拖动参数开关闪烁

**现象**：
- 鼠标挪到参数行上时，左侧树上对应的模块圆也会变亮
- 拖动参数值时，如果手抖，模块圆的亮度来回切换，看起来像"开关在闪烁"

**根因**：`hitTest` 中参数行设置了 `h.node = r.node`，导致 `state_.hover.node` 被更新。`drawNode` 中 `hovered = (st.hover.node == node)` 判断为 true，模块圆描边从 `kSep`（0.60）提升到 `kInk.withAlpha(0.42)`，视觉上非常明显。

**修复**：
- `hitTest` 中 `Kind::Control`（参数行）**不再设置 `h.node`**
- 模块圆的高亮只响应真正的圆心/标题行 hover，不再被参数行联动
- 同时降低交互 alpha 值：hover 0.06 → **0.04**，press 0.12 → **0.10**，让行底高亮更 subtle

**文件**：`vst/plugin/TranePanel.cpp`、`vst/plugin/TranePanel.h`

---

## 回归验证

| 检查项 | 结果 |
|---|---|
| pytest 界面测试 | **113 passed / 12 skipped** |
| 面板渲染像素检查 | **通过** |
| 强调色反向对照 | **3/3 抓到** |
| 背景图反向对照 | **5/5 抓到** |
| 设计稿反向对照 | **49/49 抓到** |
| 真实 VST3 端到端 | **通过** |
| 真实 AU 构建 | **通过** |

---

## 安装产物

### 已安装到系统（v0.32.1）

| 格式 | 路径 | 版本号 |
|---|---|---|
| VST3 | `~/Library/Audio/Plug-Ins/VST3/Trane.vst3` | 0.32.1 |
| AU | `~/Library/Audio/Plug-Ins/Components/Trane.component` | 0.32.1 |
| Standalone | `vst/build/.../Standalone/Trane.app` | 0.32.1 |

### 可分发安装包

位于 `outputs/Trane_v0.32.1_Installers/`：

| 文件 | 大小 | 说明 |
|---|---|---|
| `Trane-Plugins-v0.32.1.pkg` | 14 MB | macOS 安装器，双击自动装 VST3 + AU 到系统目录 |
| `Trane-VST3-v0.32.1.zip` | 6.9 MB | VST3 单独打包，手动拖入 `~/Library/Audio/Plug-Ins/VST3/` |
| `Trane-AU-v0.32.1.zip` | 6.7 MB | AU 单独打包，手动拖入 `~/Library/Audio/Plug-Ins/Components/` |
| `Trane-Standalone-v0.32.1.zip` | 7.9 MB | 独立应用，解压后拖入 Applications |

刷新 DAW 插件列表后即可加载使用。
