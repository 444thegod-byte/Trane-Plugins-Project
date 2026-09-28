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
# 必须**真的能 import** numpy 和 soundfile，只看版本号不够：
# 本机的托管版 python3.13 就没装这两个库，按版本挑会挑中它，
# 然后一路跑到 pytest 阶段才炸，报错还看不出是解释器选错了。
find_python() {
  local c
  for c in "${TRANE_PY:-}" \
           "$HOME/.workbuddy-ai/binaries/python/envs/default/bin/python" \
           /usr/bin/python3 \
           python3; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 \
       && "$c" -c 'import numpy, soundfile' >/dev/null 2>&1; then
      command -v "$c"
      return 0
    fi
  done
  return 1
}

PY="$(find_python)" || die "找不到带 numpy 和 soundfile 的 Python 3。
  装依赖：  python3 -m pip install numpy soundfile
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
