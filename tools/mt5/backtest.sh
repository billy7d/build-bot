#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WINEPREFIX="${MT5_WINEPREFIX:-$HOME/Library/Application Support/net.metaquotes.wine.metatrader5}"
WINE64="${MT5_WINE64:-/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine64}"
MT5_HOME="${MT5_HOME:-$WINEPREFIX/drive_c/Program Files/MetaTrader 5}"
TERMINAL="$MT5_HOME/terminal64.exe"

FROM_DATE="2019.01.01"
TO_DATE="2022.12.31"
DEPOSIT="1000"
CURRENCY="USD"
LEVERAGE="1:10"
SYMBOL="BTCUSD"
PERIOD="H1"
MODEL="4"
RUN_NAME=""
SKIP_COMPILE=0
REPLACE=0
PRESET=""

usage() {
  cat <<'EOF'
Cách dùng:
  tools/mt5/backtest.sh PRESET [tùy chọn]

Tùy chọn:
  --from YYYY.MM.DD       Ngày bắt đầu, mặc định 2019.01.01
  --to YYYY.MM.DD         Ngày kết thúc, mặc định 2022.12.31
  --deposit VALUE         Vốn ban đầu, mặc định 1000
  --currency CODE         Tiền tệ, mặc định USD
  --leverage VALUE        Đòn bẩy, mặc định 1:10
  --symbol SYMBOL         Symbol, mặc định BTCUSD
  --period PERIOD         Khung tester, mặc định H1
  --model 0|1|2|4         Mô hình tick, mặc định 4 (real ticks)
  --name NAME             Tên thư mục kết quả
  --skip-compile          Không compile lại EA
  --replace               Ghi đè thư mục kết quả cùng tên
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM_DATE="$2"; shift 2 ;;
    --to) TO_DATE="$2"; shift 2 ;;
    --deposit) DEPOSIT="$2"; shift 2 ;;
    --currency) CURRENCY="$2"; shift 2 ;;
    --leverage) LEVERAGE="$2"; shift 2 ;;
    --symbol) SYMBOL="$2"; shift 2 ;;
    --period) PERIOD="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --name) RUN_NAME="$2"; shift 2 ;;
    --skip-compile) SKIP_COMPILE=1; shift ;;
    --replace) REPLACE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "Tùy chọn không hợp lệ: $1" >&2; usage; exit 2 ;;
    *)
      if [[ -n "$PRESET" ]]; then
        echo "Chỉ được truyền một preset cho mỗi lần chạy." >&2
        exit 2
      fi
      PRESET="$1"
      shift
      ;;
  esac
done

if [[ -z "$PRESET" ]]; then
  usage
  exit 2
fi
if [[ ! -f "$PRESET" ]]; then
  if [[ -f "$PROJECT_ROOT/outputs/presets/$PRESET" ]]; then
    PRESET="$PROJECT_ROOT/outputs/presets/$PRESET"
  else
    echo "Không tìm thấy preset: $PRESET" >&2
    exit 2
  fi
fi
if [[ ! -x "$WINE64" || ! -f "$TERMINAL" ]]; then
  echo "Môi trường MT5/Wine chưa sẵn sàng." >&2
  exit 2
fi

PRESET="$(cd "$(dirname "$PRESET")" && pwd)/$(basename "$PRESET")"
PRESET_BASE="$(basename "$PRESET" .set)"
if [[ -z "$RUN_NAME" ]]; then
  RUN_NAME="${PRESET_BASE}_${FROM_DATE//./}_${TO_DATE//./}_d${DEPOSIT}_$(date +%Y%m%d-%H%M%S)"
fi
if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Tên run chỉ được chứa chữ, số, dấu chấm, gạch dưới và gạch ngang." >&2
  exit 2
fi

RESULT_DIR="$PROJECT_ROOT/backtests/$RUN_NAME"
if [[ -e "$RESULT_DIR" && "$REPLACE" -ne 1 ]]; then
  echo "Thư mục kết quả đã tồn tại: $RESULT_DIR" >&2
  echo "Dùng --replace hoặc chọn --name khác." >&2
  exit 2
fi
mkdir -p "$RESULT_DIR"

if [[ "$SKIP_COMPILE" -ne 1 ]]; then
  "$SCRIPT_DIR/compile.sh"
fi

RUNTIME_PRESET_DIR="$MT5_HOME/MQL5/Profiles/Tester"
RUNTIME_REPORT_DIR="$MT5_HOME/reports/codex"
mkdir -p "$RUNTIME_PRESET_DIR" "$RUNTIME_REPORT_DIR"
cp "$PRESET" "$RUNTIME_PRESET_DIR/$(basename "$PRESET")"
cp "$PRESET" "$RESULT_DIR/$(basename "$PRESET")"

REPORT_RELATIVE="reports\\codex\\$RUN_NAME.html"
RUNTIME_REPORT="$RUNTIME_REPORT_DIR/$RUN_NAME.html"
rm -f "$RUNTIME_REPORT"

CONFIG_READABLE="$RESULT_DIR/tester-config.ini"
CONFIG_UTF16="/private/tmp/mt5-codex-$RUN_NAME.ini"
cat >"$CONFIG_READABLE" <<EOF
[Tester]
Expert=Advisors\\Mentor_RSI_MTF_v1.ex5
ExpertParameters=$(basename "$PRESET")
Symbol=$SYMBOL
Period=$PERIOD
Model=$MODEL
ExecutionMode=0
Optimization=0
OptimizationCriterion=0
FromDate=$FROM_DATE
ToDate=$TO_DATE
ForwardMode=0
Deposit=$DEPOSIT
Currency=$CURRENCY
Leverage=$LEVERAGE
ProfitInPips=0
Visual=0
UseLocal=1
UseRemote=0
UseCloud=0
Report=$REPORT_RELATIVE
ReplaceReport=1
ShutdownTerminal=1
EOF

printf '\377\376' >"$CONFIG_UTF16"
iconv -f UTF-8 -t UTF-16LE "$CONFIG_READABLE" >>"$CONFIG_UTF16"

TODAY="$(date +%Y%m%d)"
TESTER_LOG="$MT5_HOME/Tester/logs/$TODAY.log"
LOG_SIZE_BEFORE=0
if [[ -f "$TESTER_LOG" ]]; then
  LOG_SIZE_BEFORE="$(stat -f%z "$TESTER_LOG")"
fi

if pgrep -f '[t]erminal64.exe' >/dev/null 2>&1; then
  echo "MT5 terminal đang chạy. Hãy đóng terminal trước để tránh cấu hình test bị chuyển vào phiên GUI đang mở." >&2
  exit 5
fi

WINE_LOG="$RESULT_DIR/wine-terminal.log"
set +e
WINEPREFIX="$WINEPREFIX" \
WINEDEBUG=-all \
MVK_CONFIG_LOG_LEVEL=0 \
"$WINE64" "$TERMINAL" "/config:Z:\\private\\tmp\\mt5-codex-$RUN_NAME.ini" \
  >"$WINE_LOG" 2>&1
WINE_STATUS=$?
set -e

if [[ ! -f "$RUNTIME_REPORT" ]]; then
  echo "Strategy Tester không tạo report. Wine status: $WINE_STATUS" >&2
  [[ -s "$WINE_LOG" ]] && tail -60 "$WINE_LOG" >&2
  exit 6
fi

cp "$RUNTIME_REPORT" "$RESULT_DIR/report.html"

JOURNAL="$RESULT_DIR/journal-summary.txt"
if [[ -f "$TESTER_LOG" ]]; then
  CURRENT_SIZE="$(stat -f%z "$TESTER_LOG")"
  if [[ "$CURRENT_SIZE" -gt "$LOG_SIZE_BEFORE" ]]; then
    dd if="$TESTER_LOG" bs=1 skip="$LOG_SIZE_BEFORE" 2>/dev/null \
      | iconv -f UTF-16LE -t UTF-8 2>/dev/null \
      | tr -d '\r' \
      | grep -E 'testing of Experts|DIAG_SUMMARY|final balance|Test passed|test passed|OnTester result|initialization failed|test failed' \
      >"$JOURNAL" || true
  fi
fi
touch "$JOURNAL"

python3 "$SCRIPT_DIR/report_summary.py" "$RESULT_DIR/report.html" >"$RESULT_DIR/summary.txt"
python3 "$SCRIPT_DIR/report_summary.py" --json "$RESULT_DIR/report.html" >"$RESULT_DIR/summary.json"
if grep -q 'DIAG_SUMMARY.*source=OnTester' "$JOURNAL"; then
  printf '\nDIAG_SUMMARY source=OnTester:\n' >>"$RESULT_DIR/summary.txt"
  grep 'DIAG_SUMMARY.*source=OnTester' "$JOURNAL" >>"$RESULT_DIR/summary.txt"
fi

cat "$RESULT_DIR/summary.txt"
echo "BACKTEST_OK result=$RESULT_DIR"
