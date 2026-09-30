# Träne v0.32.2 修复报告

> 生成时间：2026-09-29 16:55
> 版本：0.32.1 → **0.32.2**
> 依据：小绪录屏 `录屏2026-09-29 16.30.33.mov`（34s / 1430×734 / 60fps）
> 门禁：**113 passed / 12 skipped**，渲染检查通过，突变对照 3/3 + 5/5 + 49/49，端到端 VST3 通过，退出码 0

---

## 结论先说

上一轮（v0.32.1）我报的三个修复**全部打偏了** —— 小绪的录屏是对的。这一轮逐帧看视频定位到真正的根因，三处都已修正。

| # | 小绪的描述 | 上一轮我以为的 | **真正的根因** |
|---|---|---|---|
| 1 | 上传背景那块乱码 | 文件对话框标题是中文 | **面板自己画的中文**（`选择图片` / `关` `树` `参数`） |
| 2 | 高频点击无法开关、MODULE 打不开 | 双击复位了开关 | **我上轮加的 `isSecondClick` 闸把连点整片吃掉了** |
| 3 | 用参数时开关跟着闪烁 | 参数行 hover 联动模块圆 | **`Mark` 这条路径仍在给参数行传 node** |

---

## 修复 1：面板里的中文 = 乱码源

**视频证据**：顶栏第一格显示 `éĊ œ Ġå ³/¢`，第二格是几个小符号。

**根因**：整份 `plugin/` 里**只有两处会被绘制的中文**，都在顶栏背景控件：

```cpp
TranePanel.cpp:1036   const String label = hasImg ? bd.name : String("选择图片");
TranePanel.cpp:1043   const String items[] = {"关", "树", "参数"};
```

面板字体是从 Ableton 安装目录加载的 `AbletonSans-Bold.otf` / `AbletonSansMedium-Regular.otf`，**没有中文字形**，中文一律渲染成乱码。

**修复**：改成全 ASCII（小绪原话「选背景我要英文」，本来就要英文）：

```cpp
const String label = hasImg ? bd.name : String("CHOOSE IMAGE");
const String items[] = {"OFF", "TREE", "PARAM"};
```

**新规则**：面板里一个字都不许写非 ASCII。

---

## 修复 2：`isSecondClick` 闸是我上轮亲手引入的回归

**视频证据**：光标停在 MODULE 标签上约 7 秒，ALL 标签全程保持选中，MODULE 始终点不亮。

**根因**：上轮我在 `mouseUp` 里加了：

```cpp
const bool isSecondClick = e.getNumberOfClicks() >= 2;
```

并把它**同时用在标签页和开关上**。但 `getNumberOfClicks()` 是**累加**的 —— 连点就是 2、3、4…，于是「高频点击」整片被吃掉，正好就是「高频点击会无法开关 / MODULE 打不开」。

**修复**：闸**只留给「选择图片」**（连开两次系统对话框确实不是"做两遍等于没做"）：

```cpp
} else if (pressTab_ > 0 && !pressMoved_) {          // 不再挡
} else if (!wasDrag && !pressMoved_) {                // 不再挡
    ...
    } else if (pressBgSlot_ && !isSecondClick) {      // 只有这里挡
        pickBackdrop();
```

开关的"做两遍等于没做"由**动作本身**保证（toggle 两次 = 回到原值），不需要外挂计数闸。

---

## 修复 3：`Mark` 路径仍在给参数行传 node

**根因**：上轮我在 `hitTest` 里堵住了参数行写 `node`，但漏了另一条路径：

```cpp
TranePanel.h:702   case Kind::Control:  m.control = control; m.node = node; break;
```

参数行一旦带上 node，树上的圆和检查器标题行就把「指针在参数行上」读成「指针在这个模块上」→ 拖参数时开关跟着亮/灭 = 闪烁。

**修复**：

```cpp
case Kind::Control:  m.control = control; break;   // 不带 node
```

---

## 性能：实测数据（先量再改）

| 场景 | 每帧 | 30Hz 单核占用 |
|---|---|---|
| 无背景 | 4.77 ms | 14.3% |
| 带背景（参数区） | 4.62 ms | 13.9% |
| 背景冷重烤 | 27.9 ms | （只在换图 / 换落位 / 改尺寸时触发） |

**背景缓存是有效的**：冷 27.9 ms → 热 4.62 ms，热态与无背景几乎相同。所以 4.6 ms 全在**动态层**（9 条渐变信号线、10 个圆的径向光晕、48 行文字）。

**已做：空闲降帧**
- `noteInput()` 记录真实输入时刻；静置 >700 ms 后每两拍才 `repaint()`（30Hz → 15Hz）
- 呼吸周期 2.6 s，15Hz 仍有约 39 个采样/周期，肉眼分不出来
- 指针一进面板立刻回到 30Hz，拖拽 / 悬停的跟手感不打折
- 状态同步（`syncFromHost` / `syncTelemetry` / `pullBackdropState`）**仍然每拍都跑**，宿主自动化不会漏读

**试过并否决**：底图改 `useNearestNeighbour=true` 反而更慢（4.77 → **7.02 ms**）—— JUCE 的重采样走 SIMD 标度器，最近邻退回逐像素分支。已在 `paint()` 里写明「不要加这个参数」。

**尚未做（下一轮方向）**：把检查器的**静态层**（模块名 / 参数名 / 单位 / 轨道底 / 刻度）并进 `backdrop` 缓存 —— 48 行文字是动态层的大头。注意轨道的**填充**在呼吸，所以填充不能进静态层。

---

## 安装：清掉了「两份并存」的坑

发现 **`~/Library` 0.32.2 与 `/Library` 0.32.1 并存**（系统级那份是上一轮 pkg 装的）。两级都会被 DAW 扫描，版本还不一致 —— 这是最容易被误判成「还是旧版本」的情形。

已把系统级两份移入 `~/.Trash/Trane_old_20260929-165054/`，现在**只剩用户级一份 0.32.2**。

**今后 pkg 一律打到用户级**：`pkgbuild --install-location /Users/444_thegod`，免管理员密码，也不会和系统级重复。

---

## 产物

| 文件 | 说明 |
|---|---|
| `Trane-Plugins-v0.32.2.pkg` | 装到**用户级**，免密码，不会重复 |
| `Trane-VST3-v0.32.2.zip` | VST3 单独打包 |
| `Trane-AU-v0.32.2.zip` | AU 单独打包 |
| `Trane-Standalone-v0.32.2.zip` | 独立应用 |

### 已安装位置（唯一一份）

- `~/Library/Audio/Plug-Ins/VST3/Trane.vst3` — **0.32.2**
- `~/Library/Audio/Plug-Ins/Components/Trane.component` — **0.32.2**

---

## 视觉自查

`panel_probe --scale 2 --state all` 渲图后裁顶栏确认：`CHOOSE IMAGE` / `OFF TREE PARAM` 正常显示，无乱码。
