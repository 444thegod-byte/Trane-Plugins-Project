#!/usr/bin/env bash
# 拉取 JUCE 到 vst/external/JUCE
#
# 为什么不把 JUCE 提交进仓库：
#   JUCE 完整源码树约 100MB、5600 多个文件，提交进去会让仓库变得很重，
#   而且它是第三方代码、有独立的上游仓库。按精确版本拉取是标准做法。
#
# 为什么锁定到 commit 而不是只写 tag：
#   tag 可以被移动。锁到具体 commit，才能保证任何机器上编译出来的东西一致。
#
# 用法:
#   ./setup_juce.sh           拉取（已存在则跳过）
#   ./setup_juce.sh --force   删掉重拉
set -euo pipefail

cd "$(dirname "$0")"

JUCE_REPO="https://github.com/juce-framework/JUCE.git"
JUCE_TAG="9.0.2"
JUCE_COMMIT="72782788ce18c2d4d760b28e0921d6ffc6431102"
DEST="external/JUCE"

if [ "${1:-}" = "--force" ] && [ -d "$DEST" ]; then
  echo "移除已有的 $DEST ..."
  rm -rf "$DEST"
fi

if [ -d "$DEST/modules" ]; then
  echo "JUCE 已存在，跳过。要重拉请加 --force"
  git -C "$DEST" describe --tags 2>/dev/null || true
  exit 0
fi

mkdir -p external

echo "拉取 JUCE ${JUCE_TAG} ..."
git clone --branch "$JUCE_TAG" --depth 1 "$JUCE_REPO" "$DEST"

# 校验：拉到的必须正好是锁定的那个 commit。对不上就直接报错退出，
# 不要让一个版本不对的依赖悄悄通过 —— 那会让后面所有验证结果都不可信。
ACTUAL="$(git -C "$DEST" rev-parse HEAD)"
if [ "$ACTUAL" != "$JUCE_COMMIT" ]; then
  echo "错误：JUCE 版本不符。" >&2
  echo "  期望 commit: $JUCE_COMMIT" >&2
  echo "  实际 commit: $ACTUAL" >&2
  echo "上游的 tag 可能被移动过。请人工确认后再继续。" >&2
  exit 1
fi

echo "OK：JUCE $(git -C "$DEST" describe --tags) @ ${ACTUAL:0:7}"
echo "现在可以跑 ./run_tests.sh 了。"
