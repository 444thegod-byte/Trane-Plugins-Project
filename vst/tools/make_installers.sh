#!/usr/bin/env bash
#
# make_installers.sh —— 把构建产物打成可以双击安装的包（macOS）
#
# 用法：  ./tools/make_installers.sh 0.32.3
#         （版本号必须和 CMakeLists.txt 里的 project(Trane VERSION ...) 一致）
#
# 产出到 `outputs/Trane_v<版本>_Installers/`：
#   Trane-Plugins-v<版本>.pkg    VST3 + AU，装到**用户级** ~/Library/Audio/Plug-Ins/
#   Trane-VST3-v<版本>.zip       手动拖拽用
#   Trane-AU-v<版本>.zip
#   Trane-Standalone-v<版本>.zip
#
# ---------------------------------------------------------------------------
# 为什么 pkg 一律打**用户级**（--install-location /Users/<me>）
# ---------------------------------------------------------------------------
# `~/Library/Audio/Plug-Ins/` 与 `/Library/Audio/Plug-Ins/` **两级都会被 DAW 扫描**。
# 两份并存时版本还不一致，是最容易被误判成「我装了新版怎么还是旧界面」的情形
# （2026-09-29 真踩过）。打到用户级还有两个好处：不需要管理员密码，且不会重复。
#
# 校验：打完包会把 pkg 解出来，逐个比对二进制 sha256 与构建产物是否一致 ——
# 「打包成功」不等于「包里是刚才编的那份」。
set -euo pipefail

VER="${1:?用法: ./tools/make_installers.sh <版本号，如 0.32.3>}"

VST_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ART="$VST_DIR/build/TranePlugin_artefacts/Release"
OUT="$VST_DIR/../outputs/Trane_v${VER}_Installers"

VST3="$ART/VST3/Trane.vst3"
AU="$ART/AU/Trane.component"
APP="$ART/Standalone/Trane.app"

for p in "$VST3" "$AU" "$APP"; do
  [ -d "$p" ] || { echo "找不到 $p —— 先跑 ninja -C build" >&2; exit 1; }
done

# CMakeLists 里的版本必须和参数一致，否则包名和包里的版本会分叉
CMVER="$(sed -n 's/^project(Trane VERSION \([0-9.]*\).*/\1/p' "$VST_DIR/CMakeLists.txt")"
[ "$CMVER" = "$VER" ] || { echo "CMakeLists.txt 是 $CMVER，参数是 $VER —— 先改一致" >&2; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"

# ---- pkg：payload 里放 Library/Audio/Plug-Ins/...，装到用户主目录 ----
PAYLOAD="$(mktemp -d)"
trap 'rm -rf "$PAYLOAD"' EXIT
mkdir -p "$PAYLOAD/Library/Audio/Plug-Ins/VST3" "$PAYLOAD/Library/Audio/Plug-Ins/Components"
# ditto 而不是 cp -R：保留符号链接 / 扩展属性 / 代码签名
ditto "$VST3" "$PAYLOAD/Library/Audio/Plug-Ins/VST3/Trane.vst3"
ditto "$AU"   "$PAYLOAD/Library/Audio/Plug-Ins/Components/Trane.component"
# .DS_Store 不进包
find "$PAYLOAD" -name '.DS_Store' -delete

PKG="$OUT/Trane-Plugins-v${VER}.pkg"
pkgbuild --root "$PAYLOAD" \
         --install-location "/Users/$USER" \
         --identifier "com.trane.plugin.v${VER//./}" \
         --version "$VER" \
         --ownership recommended \
         "$PKG"

# ---- zip：手动拖拽用 ----
( cd "$(dirname "$VST3")" && zip -qry "$OUT/Trane-VST3-v${VER}.zip" "Trane.vst3" )
( cd "$(dirname "$AU")"   && zip -qry "$OUT/Trane-AU-v${VER}.zip" "Trane.component" )
( cd "$(dirname "$APP")"  && zip -qry "$OUT/Trane-Standalone-v${VER}.zip" "Trane.app" )

# ---- 校验：包里的二进制必须和刚编出来的一模一样 ----
echo "=== 校验 pkg 内容 ==="
CHK="$(mktemp -d)"
trap 'rm -rf "$PAYLOAD" "$CHK"' EXIT
pkgutil --expand "$PKG" "$CHK/x" >/dev/null
( cd "$CHK/x" && cat Payload | gunzip -dc | cpio -i --quiet 2>/dev/null )

fail=0
for pair in "VST3/Trane.vst3:VST3/Trane.vst3" "AU/Trane.component:Components/Trane.component"; do
  src="$ART/${pair%%:*}"; dst="$CHK/x/Library/Audio/Plug-Ins/${pair##*:}"
  bin_src="$(find "$src" -type f -perm +111 -name Trane | head -1)"
  bin_dst="$(find "$dst" -type f -perm +111 -name Trane | head -1)"
  a="$(shasum -a 256 "$bin_src" | cut -d' ' -f1)"
  b="$(shasum -a 256 "$bin_dst" | cut -d' ' -f1)"
  if [ "$a" = "$b" ]; then
    echo "  ✓ $(basename "$src")  ${a:0:16}…"
  else
    echo "  ✗ $(basename "$src") 构建 ${a:0:16}… ≠ 包内 ${b:0:16}…" >&2
    fail=1
  fi
done
[ "$fail" = 0 ] || { echo "包里的二进制和构建产物不一致，别发布" >&2; exit 1; }

echo
ls -lh "$OUT"
