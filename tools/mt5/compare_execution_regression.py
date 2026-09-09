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


def report_data(path: Path):
    parser = ReportTableParser()
    parser.feed(read_report(path))
    metrics = collect_metrics(parser.rows)
    deal_header = next(
        (index for index, row in enumerate(parser.rows) if "Deal" in row and "Direction" in row and "Profit" in row),
        None,
    )
    cycles = collect_closed_cycles(parser.rows, deal_header)
    return metrics, cycles


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


def compare_reports(control_path: Path, audit_path: Path, tolerance: float):
    control, control_cycles = report_data(control_path)
    audit, audit_cycles = report_data(audit_path)
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

    return {
        "control_report": str(control_path),
        "audit_report": str(audit_path),
        "tolerance": tolerance,
        "equal": not mismatches,
        "control": control_values,
        "audit": audit_values,
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
            # V82 telemetry is intentionally allowed to differ between the
            # control and audit runs; execution diagnostics remain compared.
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
    if control is None or audit is None:
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
    args = parser.parse_args()

    result = compare_reports(args.control_report, args.audit_report, args.tolerance)
    diagnostics = compare_diagnostics(args.control_journal, args.audit_journal)
    result["execution_diagnostics"] = diagnostics
    if diagnostics["available"] and not diagnostics["equal"]:
        result["equal"] = False
        result["mismatches"].append({"kind": "execution_diagnostics", **diagnostics["mismatches"][0]})

    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0 if result["equal"] else 1)


if __name__ == "__main__":
    main()
