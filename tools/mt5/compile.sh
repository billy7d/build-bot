#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WINEPREFIX="${MT5_WINEPREFIX:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5}"
WINE64="${MT5_WINE64:-/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64}"
MT5_HOME="${MT5_HOME:-$WINEPREFIX/drive_c/Program Files/MetaTrader 5}"
METAEDITOR="$MT5_HOME/MetaEditor64.exe"
RUNTIME_ALIAS="/private/tmp/mt5-codex-runtime"
SOURCE_ALIAS="/private/tmp/mt5-codex-source"
BUILD_DIR="$PROJECT_ROOT/outputs/build"
SOURCE="${1:-$PROJECT_ROOT/outputs/Mentor_RSI_MTF_v1.mq5}"

if [[ ! -x "$WINE64" ]]; then
  echo "Không tìm thấy Wine: $WINE64" >&2
  exit 2
fi
if [[ ! -f "$METAEDITOR" ]]; then
  echo "Không tìm thấy MetaEditor64.exe: $METAEDITOR" >&2
  exit 2
fi
if [[ ! -f "$SOURCE" ]]; then
  echo "Không tìm thấy mã nguồn EA: $SOURCE" >&2
  exit 2
fi

SOURCE="$(cd "$(dirname "$SOURCE")" && pwd)/$(basename "$SOURCE")"

mkdir -p "$BUILD_DIR"
ln -sfn "$MT5_HOME" "$RUNTIME_ALIAS"
ln -sfn "$(dirname "$SOURCE")" "$SOURCE_ALIAS"

SOURCE_NAME="$(basename "$SOURCE")"
EX5_NAME="${SOURCE_NAME%.mq5}.ex5"
SOURCE_EX5="$(dirname "$SOURCE")/$EX5_NAME"
COMPILE_LOG_UTF16="/private/tmp/mt5-codex-compile.log"
COMPILE_LOG="$BUILD_DIR/compile.log"
WINE_LOG="$BUILD_DIR/wine-compile.log"

rm -f "$COMPILE_LOG_UTF16"

set +e
WINEPREFIX="$WINEPREFIX" \
WINEDEBUG=-all \
MVK_CONFIG_LOG_LEVEL=0 \
"$WINE64" "$METAEDITOR" \
  "/compile:Z:\\private\\tmp\\mt5-codex-source\\$SOURCE_NAME" \
  "/log:Z:\\private\\tmp\\mt5-codex-compile.log" \
  "/inc:Z:\\private\\tmp\\mt5-codex-runtime\\MQL5" \
  >"$WINE_LOG" 2>&1
WINE_STATUS=$?
set -e

if [[ ! -f "$COMPILE_LOG_UTF16" ]]; then
  echo "MetaEditor không tạo compile log. Wine status: $WINE_STATUS" >&2
  [[ -s "$WINE_LOG" ]] && tail -40 "$WINE_LOG" >&2
  exit 3
fi

iconv -f UTF-16LE -t UTF-8 "$COMPILE_LOG_UTF16" | tr -d '\r' >"$COMPILE_LOG"
cat "$COMPILE_LOG"

if ! grep -q "Result: 0 errors, 0 warnings" "$COMPILE_LOG"; then
  echo "Compile thất bại. Xem log: $COMPILE_LOG" >&2
  exit 4
fi
if [[ ! -f "$SOURCE_EX5" ]]; then
  echo "Compile báo thành công nhưng không tìm thấy: $SOURCE_EX5" >&2
  exit 4
fi

EA_RUNTIME_DIR="$MT5_HOME/MQL5/Experts/Advisors"
mkdir -p "$EA_RUNTIME_DIR"
cp "$SOURCE" "$EA_RUNTIME_DIR/$SOURCE_NAME"
cp "$SOURCE_EX5" "$EA_RUNTIME_DIR/$EX5_NAME"

echo "COMPILE_OK source=$SOURCE"
echo "COMPILE_OK ex5=$SOURCE_EX5"
echo "COMPILE_OK runtime=$EA_RUNTIME_DIR/$EX5_NAME"
