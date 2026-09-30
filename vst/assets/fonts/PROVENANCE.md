# 面板字体 —— 来源与再生成方法

## 这是什么

`TraneSans_SemiBold.ttf` / `TraneSans_Regular.ttf` 是 **Inter** 的两个静态、子集化实例。

| 文件 | 上游 | 轴位置 | 竖干 / 200 cap | 用途 |
|---|---|---|---|---|
| `TraneSans_SemiBold.ttf` | Inter 4.001 | `wght=600, opsz=14` | 35.73 | 面板 UI 文字（模块标题、参数名、顶栏、视图标题） |
| `TraneSans_Regular.ttf`  | Inter 4.001 | `wght=470, opsz=14` | 29.01 | 数值 / 读数 |

上游：<https://github.com/rsms/inter> · 许可：SIL Open Font License 1.1（见 `OFL.txt`）
版权：`Copyright 2016 The Inter Project Authors`

## 为什么是 Inter，为什么是这两个字重

参照对象 **Lux Cache** 用的是 **Suisse Neue / Suisse Int'l**（Swiss Typefaces，商业授权，
EULA 禁止再分发）—— 本机未安装，也不能打进安装包。所以打包的是"最接近的开源替代"。

选型不是拍脑袋，是量出来的。候选 13 款 OFL 无衬线，在**字重对齐后**（把每款的 `wght`
轴调到竖干 = 29.1）做高斯模糊 IoU 骨架比对：

| 字体 | 软 IoU | 需要的 wght |
|---|---|---|
| Archivo | 0.8865 | 429.7 |
| **Inter** | **0.8845** | **468.8** |
| WorkSans | 0.8777 | 459.4 |
| SchibstedGrotesk | 0.8748 | 485.9 |
| … | … | … |

Archivo 与 Inter 差 0.002，**在噪声内打平**。选 Inter 是因为它是为**小字号屏幕 UI** 设计的
（带 `opsz` 光学尺寸轴，14 端就是"文字号"），而 Archivo 是标题字；本面板最小字号 11px。

两个字重的值同样是对齐出来的：

```
SuisseNeue-Regular（参照）        竖干 29.14  ← TraneSans-Regular 470 = 29.01（Δ0.45%）
AbletonSans-Bold（旧 uiFont）     竖干 35.68  ← TraneSans-SemiBold 600 = 35.73（Δ0.14%）
AbletonSansMedium-Regular（旧值列）竖干 27.86
HelveticaNeue-Bold（旧降级路径）   竖干 43.86  ← 比 Ableton Bold 重 23%
```

值列取 470 而不是"保持现状"的 450：用户要的是 Lux Cache 同款，所以对齐参照而不是对齐旧观感。

## 为什么改名成 Trane Sans

上游 OFL 的版权串里**没有** "with Reserved Font Name" 条款，所以保留 "Inter" 也合法。
改名的理由是**可验证性**：断言"面板渲染用的字体 == 打包字体"要能判定。如果字体仍叫
"Inter" 而用户机器上恰好装了 Inter，字体解析会悄悄命中系统那份，断言照样绿 —— 那就成了
假绿。叫 "Trane Sans" 之后，"面板在用哪份文件"是一个**可判定**的问题。

## 怎么再生成

`tools/build_panel_fonts.py`。它做的事：

1. 从上游可变字体 `Inter[opsz,wght].ttf` 在 `opsz=14` 下实例化 `wght=470` / `wght=600`；
2. 子集到 ASCII + Latin-1 + 常用标点（208 字符）；
3. 改 `name` 表为 `Trane Sans` / `Regular|SemiBold`，版权串保留上游归属；
4. 回读校验（字形数、`fvar` 已消失、竖干落在目标 ±1% 内）。

**上游字体不入库。** 再生成时才需要，脚本自己去下载。

## 覆盖性

面板是 ASCII 文案（`TranePanel.cpp` 里有一条硬约束：面板字体没有中文字形）。
子集覆盖范围由断言 `test_panel_fonts_cover_every_rendered_character` 盯着 ——
它把面板会渲染的每一个字符拿去 `Typeface::getGlyphForCharacter` 查，缺一个就报红。
所以将来谁加了一个新符号（比如 `±`），会当场被抓住，而不是在界面上出现一个豆腐块。
