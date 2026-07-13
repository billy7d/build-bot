#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FROM_DATE="2019.01.01"
TO_DATE="2022.12.31"
DEPOSIT="1000"
CURRENCY="USD"
LEVERAGE="1:10"
SYMBOL="BTCUSD"
PERIOD="H1"
MODEL="4"
PRESETS=()

usage() {
  cat <<'EOF'
Cách dùng:
  tools/mt5/run_batch.sh [tùy chọn] PRESET1.set PRESET2.set ...

Các tùy chọn giống backtest.sh: --from, --to, --deposit, --currency,
--leverage, --symbol, --period và --model.
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
    -h|--help) usage; exit 0 ;;
    -*) echo "Tùy chọn không hợp lệ: $1" >&2; usage; exit 2 ;;
    *) PRESETS+=("$1"); shift ;;
  esac
done

if [[ ${#PRESETS[@]} -eq 0 ]]; then
  usage
  exit 2
fi

"$SCRIPT_DIR/compile.sh"

FAILED=0
for preset in "${PRESETS[@]}"; do
  if ! "$SCRIPT_DIR/backtest.sh" "$preset" \
    --from "$FROM_DATE" \
    --to "$TO_DATE" \
    --deposit "$DEPOSIT" \
    --currency "$CURRENCY" \
    --leverage "$LEVERAGE" \
    --symbol "$SYMBOL" \
    --period "$PERIOD" \
    --model "$MODEL" \
    --skip-compile; then
    FAILED=1
  fi
done

exit "$FAILED"
