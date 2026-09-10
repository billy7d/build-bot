#!/usr/bin/env python3
"""Cổng equality cho report execution control/audit của MT5."""

import argparse
import json
import math
import re
from pathlib import Path

try:
    from report_summary import ReportTableParser, collect_closed_cycles, collect_metrics, parse_number, read_report
except ModuleNotFoundError:
    from tools.mt5.report_summary import ReportTableParser, collect_closed_cycles, collect_metrics, parse_number, read_report


COMPARE_FIELDS = (
    "total_net_profit",
    "profit_factor",
    "expected_payoff",
    "total_trades",
    "closed_cycles",
    "long_net_by_deals",
    "long_pf_by_deals",
    "short_net_by_deals",
    "short_pf_by_deals",
)
EXECUTION_DEAL_FIELDS = (
    "time",
    "symbol",
    "type",
    "direction",
    "volume",
    "price",
    "profit",
    "commission",
    "swap",
    "comment",
)
EXECUTION_DEAL_NUMERIC_FIELDS = ("volume", "price", "profit", "commission", "swap")


def report_data(path: Path):
    parser = ReportTableParser()
    parser.feed(read_report(path))
    metrics = collect_metrics(parser.rows)
    deal_header = next(
        (index for index, row in enumerate(parser.rows) if "Deal" in row and "Direction" in row and "Profit" in row),
        None,
    )
    cycles = collect_closed_cycles(parser.rows, deal_header)
    deals = collect_execution_deals(parser.rows, deal_header)
    missing_deal_fields = missing_execution_deal_fields(parser.rows, deal_header)
    return metrics, cycles, deals, missing_deal_fields


def _header_columns(rows, header_index):
    if header_index is None:
        return {}
    return {str(value).strip().lower(): index for index, value in enumerate(rows[header_index])}


def missing_execution_deal_fields(rows, header_index):
    """Kiểm tra schema deal ổn định trước khi so sánh execution."""
    columns = _header_columns(rows, header_index)
    return [field for field in EXECUTION_DEAL_FIELDS if field not in columns]


def _parse_deal_number(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        number = parse_number(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def collect_execution_deals(rows, header_index):
    """Trích chuỗi deal ổn định để equality không chỉ dựa trên summary/cycle."""
    if header_index is None:
        return []

    columns = _header_columns(rows, header_index)
    required = [field for field in EXECUTION_DEAL_FIELDS if field != "comment"]
    if any(field not in columns for field in required):
        return []

    deals = []
    for row in rows[header_index + 1 :]:
        if any(index >= len(row) for index in columns.values()):
            continue
        deal_type = row[columns["type"]].strip().lower()
        direction = row[columns["direction"]].strip().lower()
        if deal_type not in ("buy", "sell") or direction not in ("in", "out", "out by"):
            continue
        deal = {
            "time": row[columns["time"]],
            "symbol": row[columns["symbol"]],
            "type": deal_type,
            "direction": direction,
            "volume": _parse_deal_number(row[columns["volume"]]),
            "price": _parse_deal_number(row[columns["price"]]),
            "profit": _parse_deal_number(row[columns["profit"]]),
            "commission": _parse_deal_number(row[columns["commission"]]),
            "swap": _parse_deal_number(row[columns["swap"]]),
            "comment": row[columns["comment"]] if "comment" in columns else "",
        }
        deals.append(deal)
    return deals


def read_text_auto(path: Path):
    """Đọc journal MT5 UTF-16 hoặc text UTF-8 theo đúng encoding thực tế."""
    data = path.read_bytes()
    utf16_hint = data.startswith((b"\xff\xfe", b"\xfe\xff")) or data[:4096].count(b"\x00") > 8
    encoding = "utf-16" if utf16_hint else "utf-8"
    return data.decode(encoding, errors="replace")


def close_enough(left, right, tolerance):
    if isinstance(left, float) and isinstance(right, float):
        if math.isinf(left) or math.isinf(right):
            return left == right
        return abs(left - right) <= tolerance
    return left == right


def comparable_report_metrics(metrics):
    result = {field: metrics[field] for field in COMPARE_FIELDS}
    result["equity_drawdown_maximal_value"] = parse_number(metrics["equity_drawdown_maximal"])
    result["equity_drawdown_relative_value"] = parse_number(metrics["equity_drawdown_relative"])
    result["long_trades"] = metrics["long_trades"]
    result["short_trades"] = metrics["short_trades"]
    return result


def compare_deal_sequences(control_deals, audit_deals, tolerance):
    """So sánh các thuộc tính execution ổn định theo đúng thứ tự deal."""
    mismatches = []
    if len(control_deals) != len(audit_deals):
        return [{"kind": "deal_count", "control": len(control_deals), "audit": len(audit_deals)}]

    exact_fields = ("time", "symbol", "type", "direction", "comment")
    numeric_fields = EXECUTION_DEAL_NUMERIC_FIELDS
    for index, (control_deal, audit_deal) in enumerate(zip(control_deals, audit_deals), start=1):
        for field in exact_fields:
            if control_deal[field] != audit_deal[field]:
                mismatches.append(
                    {
                        "kind": "deal_sequence",
                        "index": index,
                        "field": field,
                        "control": control_deal[field],
                        "audit": audit_deal[field],
                    }
                )
        for field in numeric_fields:
            if control_deal[field] is None or audit_deal[field] is None:
                mismatches.append(
                    {
                        "kind": "deal_value_unavailable",
                        "index": index,
                        "field": field,
                        "control": control_deal[field],
                        "audit": audit_deal[field],
                    }
                )
            elif not close_enough(control_deal[field], audit_deal[field], tolerance):
                mismatches.append(
                    {
                        "kind": "deal_sequence",
                        "index": index,
                        "field": field,
                        "control": control_deal[field],
                        "audit": audit_deal[field],
                    }
                )
    return mismatches


def compare_reports(control_path: Path, audit_path: Path, tolerance: float):
    control, control_cycles, control_deals, control_missing_fields = report_data(control_path)
    audit, audit_cycles, audit_deals, audit_missing_fields = report_data(audit_path)
    mismatches = []

    control_values = comparable_report_metrics(control)
    audit_values = comparable_report_metrics(audit)
    for field in sorted(control_values):
        if not close_enough(control_values[field], audit_values[field], tolerance):
            mismatches.append({"kind": "report_metric", "field": field, "control": control_values[field], "audit": audit_values[field]})

    if len(control_cycles) != len(audit_cycles):
        mismatches.append({"kind": "cycle_count", "control": len(control_cycles), "audit": len(audit_cycles)})
    else:
        for index, (control_cycle, audit_cycle) in enumerate(zip(control_cycles, audit_cycles), start=1):
            for field in ("side", "open_time", "close_time", "comment"):
                if control_cycle[field] != audit_cycle[field]:
                    mismatches.append(
                        {
                            "kind": "cycle_identity",
                            "index": index,
                            "field": field,
                            "control": control_cycle[field],
                            "audit": audit_cycle[field],
                        }
                    )
            if not close_enough(control_cycle["profit"], audit_cycle["profit"], tolerance):
                mismatches.append(
                    {
                        "kind": "cycle_identity",
                        "index": index,
                        "field": "profit",
                        "control": control_cycle["profit"],
                        "audit": audit_cycle["profit"],
                    }
                )

    deal_sequence_mismatches = compare_deal_sequences(control_deals, audit_deals, tolerance)
    mismatches.extend(deal_sequence_mismatches)
    deal_sequence_available = (
        not control_missing_fields
        and not audit_missing_fields
        and (bool(control_deals or audit_deals) or (control["total_trades"] == 0 and audit["total_trades"] == 0))
    )
    if control_missing_fields or audit_missing_fields:
        mismatches.append(
            {
                "kind": "deal_schema_unavailable",
                "control_missing_fields": control_missing_fields,
                "audit_missing_fields": audit_missing_fields,
            }
        )
    if not deal_sequence_available:
        mismatches.append(
            {
                "kind": "deal_sequence_unavailable",
                "control_total_trades": control["total_trades"],
                "audit_total_trades": audit["total_trades"],
            }
        )

    return {
        "control_report": str(control_path),
        "audit_report": str(audit_path),
        "tolerance": tolerance,
        "equal": not mismatches,
        "control": control_values,
        "audit": audit_values,
        "deal_sequence": {
            "available": deal_sequence_available,
            "control_count": len(control_deals),
            "audit_count": len(audit_deals),
            "mismatches": deal_sequence_mismatches,
        },
        "mismatches": mismatches,
    }


def diagnostic_groups(path: Path):
    """Lấy các nhóm diagnostic OnTester và bỏ prefix ngẫu nhiên của journal MT5."""
    if path is None or not path.exists():
        return None
    groups = []
    current = []
    for raw_line in read_text_auto(path).splitlines():
        line = raw_line.strip()
        if "DIAG_SUMMARY " not in line:
            continue
        match = re.search(r"(DIAG_SUMMARY\s+\S+.*source=OnTester.*)$", line)
        if not match:
            continue
        normalized = match.group(1)
        if normalized.startswith("DIAG_SUMMARY core ") and current:
            groups.append(current)
            current = []
        if normalized.startswith("DIAG_SUMMARY stdDevShadow "):
            continue
        if normalized.startswith("DIAG_SUMMARY blockedSignalShadow "):
            # Telemetry V82 được phép khác control; execution diagnostics vẫn phải bằng nhau.
            continue
        current.append(normalized)
    if current:
        groups.append(current)
    return groups


def diagnostic_lines(path: Path):
    """Lấy nhóm diagnostic OnTester cuối."""
    groups = diagnostic_groups(path)
    if groups is None:
        return None
    return groups[-1] if groups else []


def compare_diagnostics(control_path: Path, audit_path: Path):
    control = diagnostic_lines(control_path)
    audit = diagnostic_lines(audit_path)
    if not control or not audit:
        return {"available": False, "equal": None, "mismatches": []}
    return {
        "available": True,
        "equal": control == audit,
        "control_lines": control,
        "audit_lines": audit,
        "mismatches": [] if control == audit else [{"control": control, "audit": audit}],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control_report", type=Path)
    parser.add_argument("audit_report", type=Path)
    parser.add_argument("--control-journal", type=Path)
    parser.add_argument("--audit-journal", type=Path)
    parser.add_argument("--tolerance", type=float, default=1.0e-6)
    parser.add_argument(
        "--require-diagnostics",
        action="store_true",
        help="Fail nếu không có DIAG_SUMMARY OnTester ở cả hai journal.",
    )
    args = parser.parse_args()

    result = compare_reports(args.control_report, args.audit_report, args.tolerance)
    diagnostics = compare_diagnostics(args.control_journal, args.audit_journal)
    result["execution_diagnostics"] = diagnostics
    if diagnostics["available"] and not diagnostics["equal"]:
        result["equal"] = False
        result["mismatches"].append({"kind": "execution_diagnostics", **diagnostics["mismatches"][0]})
    elif args.require_diagnostics and not diagnostics["available"]:
        result["equal"] = False
        result["mismatches"].append(
            {"kind": "execution_diagnostics_unavailable", "reason": "missing OnTester diagnostic groups"}
        )

    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0 if result["equal"] else 1)


if __name__ == "__main__":
    main()
