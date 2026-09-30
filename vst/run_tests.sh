#!/usr/bin/env bash
# Träne 一键构建 + 验证
#
#   ./run_tests.sh          构建全部并跑测试
#   ./run_tests.sh --quick  只跑测试（跳过构建）
#
# 这个脚本存在的意义：Max for Live 那条路我无法在本机运行，只能靠人肉测试；
# 这里每一条验证都是机器可复现的。
#
# 换机器**不需要改这个文件** —— Python / cmake / ninja 全部自动探测。
# 要强制指定 Python，设环境变量即可：
#   TRANE_PY=/usr/local/bin/python3 ./run_tests.sh
set -euo pipefail

cd "$(dirname "$0")"

die() { echo >&2; echo "错误：$*" >&2; exit 1; }

# ---- 探测 Python ----
# 必须**真的能 import** 这几个库，只看版本号不够：
# 本机的托管版 python3.13 就没装 numpy / soundfile，按版本挑会挑中它，
# 然后一路跑到 pytest 阶段才炸，报错还看不出是解释器选错了。
#
# v0.35 起把 **fontTools** 也加进来：`tests/test_ui_design.py` 在**顶层**
# `from fontTools.ttLib import TTFont` —— 那是故意的，字体那几条断言要拿它
# 直接量 .ttf（family 名 / 有没有 fvar / 竖干宽度 / 数字等不登宽）。
# 缺了它整个文件**收集不了**，报出来是一整页 collection error；
# 在这里挡掉，报错就只有一行"装依赖"。
find_python() {
  local c
  for c in "${TRANE_PY:-}" \
           "$HOME/.workbuddy-ai/binaries/python/envs/default/bin/python" \
           /usr/bin/python3 \
           python3; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 \
       && "$c" -c 'import numpy, soundfile, fontTools' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

PY="$(find_python)" || die "找不到带 numpy、soundfile 和 fontTools 的 Python 3。
  装依赖：  python3 -m pip install numpy soundfile fonttools
  或指定：  TRANE_PY=/path/to/python3 ./run_tests.sh"

PYDIR="$(dirname "$PY")"

# ---- 探测 cmake / ninja ----
# 这两个可能装在别处不在 PATH 上（本机就是装在 Python venv 里），
# 所以顺带在 Python 同目录看一眼。
find_tool() {
  if command -v "$1" >/dev/null 2>&1; then command -v "$1"; return 0; fi
  if [ -x "$PYDIR/$1" ]; then echo "$PYDIR/$1"; return 0; fi
  return 1
}

CMAKE="$(find_tool cmake)" || die "找不到 cmake。
  装法：  brew install cmake
  或指定： PATH=\"\$PATH:/path/to/cmake/bin\" ./run_tests.sh"
NINJA="$(find_tool ninja)" || die "找不到 ninja。
  装法：  brew install ninja
  或指定： PATH=\"\$PATH:/path/to/ninja/bin\" ./run_tests.sh"

# 把找到的工具所在目录加进 PATH。**这一步不能省**：
# JUCE 生成 VST3 manifest helper 时会另起一个 cmake 子进程去配置辅助工程，
# 那个子进程不继承外层的 -DCMAKE_MAKE_PROGRAM，只会去 PATH 上找 ninja。
# ninja 不在 PATH 上就会报 "CMake was unable to find a build program
# corresponding to Ninja"，而且报错出现在子进程里，很不好查。
export PATH="$(dirname "$CMAKE"):$(dirname "$NINJA"):$PATH"

xcode-select -p >/dev/null 2>&1 \
  || die "找不到 Xcode 命令行工具。
  装法：  xcode-select --install"

[ -d external/JUCE/modules ] \
  || die "缺少 JUCE。先跑：./setup_juce.sh"

echo "Python : $PY"
echo "         $("$PY" -V 2>&1)"
echo "cmake  : $CMAKE  [$("$CMAKE" --version | head -1)]"
echo "ninja  : $NINJA  [v$("$NINJA" --version)]"
echo

if [ "${1:-}" != "--quick" ]; then
  echo "=== 配置 ==="
  # 显式把 ninja 路径交给 cmake —— 它不在 PATH 上的话，cmake 自己找不到。
  "$CMAKE" -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_MAKE_PROGRAM="$NINJA" >/dev/null
  echo "=== 构建 ==="
  "$CMAKE" --build build
fi

echo
echo "=== 离线渲染验证 ==="
# pytest 会先删掉已存在的 --basetemp 目录。在沙箱下这个删除动作会被拦下，
# 于是全部测试在 setup 阶段集体报 ERROR —— 看起来像代码崩了，其实是环境问题。
# 所以每次开一个全新的 /tmp 目录：既躲开删除动作，也符合"测试只写 /tmp"的约定。
PYTEST_TMP="$(mktemp -d /tmp/trane_pytest.XXXXXX)"
"$PY" -m pytest tests/ -q --basetemp="$PYTEST_TMP" -p no:cacheprovider

echo
echo "=== 面板渲染 + 像素分析 ==="
# 上一步查的是"参数表和几何对不对"，这一步查的是"**画出来的像素对不对**"：
# 底色、检查器有没有上屏、**排版逐行齐平**（参数名左缘 / 数值右缘 / 四栏首末齐平）、
# 面板是否完全无彩色像素、hover 淡入是不是真的渐入、每帧耗时、背景图的落位与明暗度。
# 渲染出来的是**和插件完全相同的绘制代码**（panel_probe 直接用 TranePanel），
# 不是另画一套 SVG 预览。
#
# v0.33 删掉了这一节里"树的两层 / 两档高亮 / 模式·列数·分割线改变版面"那几组断言 ——
# 世界树、信号线、分割线、MODE/列数控件全都没有住户了。**删断言和删功能是一件事**：
# 留着一条永远为真的"版面切换"断言，读报告的人会以为它还管着什么。
PANEL_PROBE=build/panel_probe_artefacts/Release/panel_probe
[ -x "$PANEL_PROBE" ] || die "找不到 $PANEL_PROBE —— panel_probe 没被构建"
"$PY" tools/check_panel_render.py --outdir ../outputs

# 下面五个脚本都是"改坏源码 → 重编 → 跑检查器 → 还原"的反向对照。
#
# **每个脚本都先把锚点全验一遍再动手。** 锚点唯不唯一是纯静态的事实，读完源文件
# 就能回答；而跑一轮突变要重编好几次、渲染十几张图。原来 `assert n == 1` 写在
# 突变循环里，于是锚点失效（源码形状改了）时要等到**那一处**轮到了才炸 ——
# v0.35 改版面时实测**白跑 8 分钟**才停在一条被 `c.colW → c.innerW` 碰掉的锚点上。
# 现在这一遍排在最前面（连"检查器先绿"都排在它后面），一秒内报出来。
#
# 上面那个检查器的**反向对照**：故意把 hover / press 反馈改成满不透明度的强调色，
# 确认"面板不使用彩色"这条真的报红。
#
# 这条是补出来的：v0.30 第一版检查器只渲染 default / all / demo，
# 而这三者的 hover / press 都是空的 —— 于是"把唯一的彩色当装饰铺上去"
# 一路绿过去。**绿本身不是证据。**
# 注意突变必须**看得见**：上一轮用 kAccent.withAlpha(0.06) 当突变是错的，
# 那个不透明度叠在黑底上只有 (0.6, 7.9, 15.3)，本来就不该算"强调色"。
"$PY" tools/check_accent_mutations.py

# v0.33 加的 hover 淡入（小绪：「鼠标移动到某一个参数上，是会**缓慢发光高亮**的，
# 而不是突然高亮」）同样要证明那 10 条断言不是空转。四处突变，**抓它的断言各不相同**：
#   缓动换成线性 → 只有"亮度"那两条报红，"相位"那几条照样绿（时间确实是线性的）
#   淡入瞬时完成 → t=0 的"与无悬停逐像素相同"报红
#   时间→进度忘了除 kHoverFade → "0.08s 是半程"报红（这条量的正是那个常数）
#   空标记不再早退 → "什么都没指时强度为 0"报红（所有行一起亮，静态图上看不出来）
"$PY" tools/check_hover_mutations.py

# v0.31 加的"用户自己上传背景图"那一节有 25 条像素断言，同样要证明它们不是空转：
# 落位搞反 / 明暗度方向搞反 / 拿掉羽化 / 缓存判据漏项 / 背景盖到骨架上面，五处各一次。
# 注意它是**一条条来**的（每轮改坏 → 重编 → 跑检查器 → 还原），比上面那个慢，
# 因为背景的像素检查本身要渲染十几张图。
"$PY" tools/check_backdrop_mutations.py

# v0.33 加的「数值列宽必须真的量过」那一节（`tests/test_ui_design.py` §6）同样要
# 证明不是空转。v0.33 之前列宽是按**字符数**估的，那个模型的两条前提都不成立、
# 而且**没有任何东西盯着** —— 数值是右对齐 + 不截断画的，串太长只会静静地爬进
# 轨道区，"右缘齐平"那类断言照样绿。现在列宽直接量，五处突变各打一条：
#   列宽只按出厂值算 → "最宽串 ≤ 列宽"报红（= 旧模型那条前提②的坏法）
#   列宽砍两成       → 同一条报红（最钝的坏法）
#   只有中间点更宽   → 还是同一条，但证明的是**测试的 201 个点严于布局的 6 个点**
#   度量恒返回常数   → 正向对照 `ctrl.i != ctrl.M` 报红
#   trackW 少减一道留白 → 换**像素检查器**里的「三段宽 + 两道留白 正好填满一栏」
#                        报红（数值列宽够 ≠ 那道留白还在；这是另一半保证）
"$PY" tools/check_metrics_mutations.py

# v0.35 把控件形态的判据**从"逐参数"改成"按模块"**：五个模块（freeze /
# grain / stutter / comb / tape）整块画成旋钮，其余模块画条形 + 一个分段块；
# 同时每个模块套进一个**框**（块底 + 发丝框线）。判据换了，**检查器的锚点
# 也跟着换**（`kKnobIds` → `kKnobModules`），而"绿本身不是证据"这条不变 ——
# 九处突变各打一层，**四个不同的检查器**：
#   M1 绘图忽略 isKnob()（旋钮全画成条形）→「旋钮行的轨道左端没有墨」报红。
#       清单 / 个数 / 展开**全都照样绿** —— 证明像素断言不是"看清单说话"。
#   M2 绕过模块清单直接给一个条形加旋钮 →「条形行的轨道左端有墨」这条
#       **正向对照**报红。少了它这种坏法一路绿：那一行压根没被归成旋钮，
#       "旋钮行左端没墨"量不到它。
#   M3 拼错一个模块名 → 「清单里的模块名都能在 kNodes 里找到」报红。
#       这是**最阴的坏法**：Release 下那个模块的整块会**静默退回条形**，
#       `knob_modules` 行照样列着拼错的名字，而所有像素断言都是绿的。
#   M4 旋钮画在轨道左端而不是正中 → 同 M1 那条报红（进了分支但画错地方）。
#   M5 画笔里的**半径写死**成一个数 →「旋钮环的外径 == 声明的那一支」报红。
#       这条是**补一个真实的漏检**：`knob_dia` 原来只喂净空算术，"画出来的环
#       有多大"一个住户都没有。它**抓不到"改 kKnobDia"**（那个常量同时喂画笔
#       和 dump，两边一起变，永远自洽）—— 它抓的是**两边分叉**。
#   M6 模块框的框线不画 →「框线真的画了」报红。框线只有 0.11 的墨、压在块底上
#       （luma 37），而"框内是块底 / 框外面板底"是拿**不等于**底色判的，
#       一条线都不画它们照样绿。
#   M7 块底铺满整个参数区 →「框外是面板底」+「行数与自述一致」报红。
#       **只查"框里是不是块底"是不够的** —— 铺满时那条**反而更绿**。
#   M8 把带分段块的模块塞进旋钮清单 →「模块里只要有分段选择就不能是全旋钮」报红。
#       这条禁令防的是**假报红**：检查器会去那一行找环，而那里只有格子。
#   M9 旋钮直径涨到与行距撞车（2.4 → 2.8 倍字号）→「相邻旋钮的净空 ≥ 环粗」报红。
#       直径跟字号走、行距跟栏走，两个独立决定撞车只有放在一起算才看得见。
#       **2.8 是能踩到的那一档里最小的一档**（外径要 ≤ 36.2 − 3.0 = 33.2 才合法）。
#
# 注意 M5 原来写的是「直径调大一档（2.4 → 2.6）」，**实测漏网** ——
# 净空 6.80 → 4.60，仍然 ≥ 环粗 3.0，也就是那处改动**是合法的**。
# 查下去才翻出上面那条真缺的住户（声明 vs 画出来的东西）。
# **一条"应该被抓住"的突变漏了网，先问它是不是真的坏。**
"$PY" tools/check_knobs_mutations.py

# ---- 第六个反向对照：顶栏品牌标（v0.36）----
#
# 顶栏的 `Trane` / `41 CONTROLS` 换成用户上传的 logo 之后，带进来一个**全新的、
# 静默的**失效模式：素材读不到时 `drawBrandMark()` 第一行就 return，
# 顶栏右上角什么都不画 —— 不报错、不崩、界面上只是少一块。
#
#   M1 `kLogoH` 改成 0            →「自述矩形非退化」报红。
#   M2 `kLogoRight` 挪到参数区左缘 →「右缘 == 参数区右缘」报红。
#        **这一处是整组里最要紧的**：它打的正是"判据错了断言照样绿" ——
#        `--dump-geometry` 的 logo 行是从常量算的，品牌标挪到哪儿它报到哪儿，
#        所以"自述矩形里有墨"那条**抓不到它**。抓它的是**像素 vs `pane`**。
#   M3 容器 magic 校验永不通过     →「自述矩形非退化」报红（模拟素材没打进二进制）。
#        M1 与 M3 报同一条断言，但走的是两条完全不同的路径（几何常量 / 数据），
#        两条都要有 —— 否则"资产读不到"只是被 M1 顺带覆盖到的**猜想**。
#   M4 `kLogoCY` 改成 150（压进参数区）→「不侵入参数区」报红。
"$PY" tools/check_logo_mutations.py

# v0.33 起这里**不再有「设计稿自检」这一节**。
#
# `tools/render_ui_dark_panel.py`（v0.32 的 HTML 设计稿）与它的反向对照
# `tools/check_contrast_mutations.py` 已经**退役** —— 见那个文件开头的说明。
# 一句话：v0.33 把世界树完全删掉之后，设计稿画的是一个不存在的设计，
# 它那 63 条自检守的是"树画得对不对"，留在门槛里只会永远红。
#
# 它真正有价值的那套东西（把每处文字的"不透明度 / 基底层 / 墨层强度"登记下来、
# 再独立复算 WCAG 对比度）**已经搬进插件自己身上**，而且比原来更强 ——
# 原来看的是另一份实现，现在看的是插件真正在跑的那段代码：
#   · 登记：`plugin/TranePanel.cpp` 的 `textLog()` / `logText()` / `bdName()`
#   · 导出：`panel_probe --dump-text`（`plugin/../probe/panel_probe.cpp`）
#   · 断言：`tests/test_ui_design.py`（22 个相位逐对复算，含正向对照）
#
# `tests/test_ui_design.py::test_retired_design_draft_is_not_in_the_gate`
# 会盯着这一节不许被加回来，也盯着设计稿开头必须写着"已退役"。

echo
echo "=== 端到端验收（加载真实 .vst3 渲染）==="
# 这一步和上面不同：不是测 DSP 源码，而是把编译出来的 .vst3 真的当插件加载起来，
# 通过 VST3 参数接口设参数、渲染、再分析。它证明的是"这个文件能装进 DAW 干活"。
VST3=build/TranePlugin_artefacts/Release/VST3/Trane.vst3
if [ -d "$VST3" ]; then
  ./build/vst3_host_probe_artefacts/Release/vst3_host_probe "$VST3" /tmp/trane_vst3_out.wav
else
  echo "找不到 $VST3" >&2
  exit 1
fi

echo
echo "=== 产物 ==="
find build -maxdepth 4 -name "*.vst3" -o -maxdepth 4 -name "*.component" 2>/dev/null | sed 's/^/  /' || true
