#!/usr/bin/env bash
# Träne 一键构建 + 验证
#
#   ./run_tests.sh          构建全部并跑测试
#   ./run_tests.sh --quick  只跑测试（跳过构建）
#
# 这个脚本存在的意义：Max for Live 那条路我无法在本机运行，只能靠人肉测试；
# 这里每一条验证都是机器可复现的。
set -euo pipefail

cd "$(dirname "$0")"

PY=/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin/python
export PATH="/Users/444_thegod/.workbuddy-ai/binaries/python/envs/default/bin:$PATH"

if [ "${1:-}" != "--quick" ]; then
  echo "=== 配置 ==="
  cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release >/dev/null
  echo "=== 构建 ==="
  cmake --build build
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
