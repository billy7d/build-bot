#!/usr/bin/env python3

import argparse
import collections
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


class ReportTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            value = " ".join("".join(self.cell).split())
            self.row.append(value)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def read_report(path):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def parse_number(value):
    cleaned = value.replace("\xa0", " ").replace(" ", "").replace(",", "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else 0.0


def pf(gross_profit, gross_loss):
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / abs(gross_loss)


def deal_header_index(rows):
    for index, row in enumerate(rows):
        if "Deal" in row and "Direction" in row and "Profit" in row:
            return index
    return None


def collect_closed_cycles(rows, header_index):
    if header_index is None:
        return []

    cycles = []
    position_volume = 0.0
    cycle = None
    epsilon = 0.0000001

    for row in rows[header_index + 1 :]:
        if len(row) < 13:
            continue

        deal_type = row[3].lower()
        direction = row[4].lower()
        if deal_type not in ("buy", "sell") or direction not in ("in", "out", "out by"):
            continue

        volume = parse_number(row[5])
        signed_volume = volume if deal_type == "buy" else -volume
        net = parse_number(row[8]) + parse_number(row[9]) + parse_number(row[10])

        if direction == "in":
            if cycle is None or abs(position_volume) <= epsilon:
                cycle = {
                    "side": "long" if signed_volume > 0 else "short",
                    "open_time": row[0],
                    "close_time": "",
                    "profit": 0.0,
                    "comment": row[12],
                }
                position_volume = 0.0
            cycle["profit"] += net
            position_volume += signed_volume
            continue

        if cycle is None:
            continue

        cycle["profit"] += net
        position_volume += signed_volume
        if abs(position_volume) <= epsilon:
            cycle["close_time"] = row[0]
            cycles.append(cycle)
            cycle = None
            position_volume = 0.0

    return cycles


def collect_yearly_side_metrics(cycles):
    yearly = collections.defaultdict(
        lambda: {
            "long": {"gross_profit": 0.0, "gross_loss": 0.0, "net": 0.0, "trades": 0},
            "short": {"gross_profit": 0.0, "gross_loss": 0.0, "net": 0.0, "trades": 0},
        }
    )

    for cycle in cycles:
        close_time = cycle["close_time"]
        if len(close_time) < 4:
            continue
        year = close_time[:4]
        side = cycle["side"]
        value = cycle["profit"]
        target = yearly[year][side]
        target["net"] += value
        target["trades"] += 1
        if value >= 0.0:
            target["gross_profit"] += value
        else:
            target["gross_loss"] += value

    result = {}
    for year in sorted(yearly):
        result[year] = {}
        for side in ("long", "short"):
            target = yearly[year][side]
            result[year][side] = {
                "net": target["net"],
                "profit_factor": pf(target["gross_profit"], target["gross_loss"]),
                "trades": target["trades"],
            }
    return result


def collect_metrics(rows):
    values = {}
    for row in rows:
        for index, cell in enumerate(row[:-1]):
            if cell.endswith(":") and row[index + 1]:
                values[cell[:-1]] = row[index + 1]

    deal_header = deal_header_index(rows)

    sides = {
        "long": {"gross_profit": 0.0, "gross_loss": 0.0, "net": 0.0},
        "short": {"gross_profit": 0.0, "gross_loss": 0.0, "net": 0.0},
    }
    if deal_header is not None:
        for row in rows[deal_header + 1 :]:
            if len(row) < 13 or row[4].lower() not in ("out", "out by"):
                continue
            deal_type = row[3].lower()
            side = "long" if deal_type == "sell" else "short" if deal_type == "buy" else None
            if side is None:
                continue
            net = parse_number(row[8]) + parse_number(row[9]) + parse_number(row[10])
            sides[side]["net"] += net
            if net >= 0:
                sides[side]["gross_profit"] += net
            else:
                sides[side]["gross_loss"] += net

    gross_profit = parse_number(values.get("Gross Profit", "0"))
    largest_profit = parse_number(values.get("Largest profit trade", "0"))
    contribution = largest_profit / gross_profit * 100.0 if gross_profit else 0.0
    cycles = collect_closed_cycles(rows, deal_header)
    top_cycle_profits = sorted((cycle["profit"] for cycle in cycles if cycle["profit"] > 0.0), reverse=True)[:3]
    top3_contribution = sum(top_cycle_profits) / gross_profit * 100.0 if gross_profit else 0.0

    return {
        "expert": values.get("Expert", ""),
        "symbol": values.get("Symbol", ""),
        "period": values.get("Period", ""),
        "deposit": values.get("Initial Deposit", ""),
        "history_quality": values.get("History Quality", ""),
        "bars": int(parse_number(values.get("Bars", "0"))),
        "ticks": int(parse_number(values.get("Ticks", "0"))),
        "symbols": int(parse_number(values.get("Symbols", "0"))),
        "total_net_profit": parse_number(values.get("Total Net Profit", "0")),
        "gross_profit": gross_profit,
        "gross_loss": parse_number(values.get("Gross Loss", "0")),
        "profit_factor": parse_number(values.get("Profit Factor", "0")),
        "expected_payoff": parse_number(values.get("Expected Payoff", "0")),
        "equity_drawdown_maximal": values.get("Equity Drawdown Maximal", ""),
        "equity_drawdown_relative": values.get("Equity Drawdown Relative", ""),
        "total_trades": int(parse_number(values.get("Total Trades", "0"))),
        "short_trades": values.get("Short Trades (won %)", ""),
        "long_trades": values.get("Long Trades (won %)", ""),
        "largest_profit_trade": largest_profit,
        "largest_profit_contribution_pct": contribution,
        "top3_profit_cycles_contribution_pct": top3_contribution,
        "largest_loss_trade": parse_number(values.get("Largest loss trade", "0")),
        "long_net_by_deals": sides["long"]["net"],
        "long_pf_by_deals": pf(sides["long"]["gross_profit"], sides["long"]["gross_loss"]),
        "short_net_by_deals": sides["short"]["net"],
        "short_pf_by_deals": pf(sides["short"]["gross_profit"], sides["short"]["gross_loss"]),
        "closed_cycles": len(cycles),
        "yearly_side_metrics": collect_yearly_side_metrics(cycles),
    }


def validate_report(metrics, args):
    errors = []
    if not metrics["expert"]:
        errors.append("Expert trống")
    if not metrics["symbol"]:
        errors.append("Symbol trống")
    if not metrics["period"] or metrics["period"].startswith("M0") or "1970.01.01" in metrics["period"]:
        errors.append(f"Period không hợp lệ: {metrics['period'] or '(trống)'}")
    if metrics["bars"] <= 0:
        errors.append("Bars bằng 0")
    if metrics["ticks"] <= 0:
        errors.append("Ticks bằng 0")

    if args.expect_expert and metrics["expert"] != args.expect_expert:
        errors.append(f"Expert={metrics['expert']} thay vì {args.expect_expert}")
    if args.expect_symbol and metrics["symbol"] != args.expect_symbol:
        errors.append(f"Symbol={metrics['symbol']} thay vì {args.expect_symbol}")
    if args.expect_period and not metrics["period"].startswith(f"{args.expect_period} ("):
        errors.append(f"Period={metrics['period']} không bắt đầu bằng {args.expect_period}")
    if args.expect_from and args.expect_from not in metrics["period"]:
        errors.append(f"Period không chứa ngày bắt đầu {args.expect_from}")
    if args.expect_to and args.expect_to not in metrics["period"]:
        errors.append(f"Period không chứa ngày kết thúc {args.expect_to}")
    return errors


def fmt(value, digits=2):
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return f"{value:.{digits}f}"


def render_text(metrics, report):
    lines = [
        f"Báo cáo: {report}",
        f"EA: {metrics['expert']}",
        f"Symbol/period: {metrics['symbol']} / {metrics['period']}",
        f"Deposit: {metrics['deposit']}",
        f"History quality: {metrics['history_quality']}",
        f"Bars/Ticks: {metrics['bars']} / {metrics['ticks']}",
        f"Total Net Profit: {fmt(metrics['total_net_profit'])}",
        f"Profit Factor: {fmt(metrics['profit_factor'])}",
        f"Expected Payoff: {fmt(metrics['expected_payoff'])}",
        f"Equity Drawdown Maximal: {metrics['equity_drawdown_maximal']}",
        f"Equity Drawdown Relative: {metrics['equity_drawdown_relative']}",
        f"Total Trades: {metrics['total_trades']}",
        f"Short Trades (won %): {metrics['short_trades']}",
        f"Long Trades (won %): {metrics['long_trades']}",
        f"Short PF theo deals: {fmt(metrics['short_pf_by_deals'])}",
        f"Long PF theo deals: {fmt(metrics['long_pf_by_deals'])}",
        f"Largest profit trade: {fmt(metrics['largest_profit_trade'])}",
        f"Largest profit / Gross Profit: {fmt(metrics['largest_profit_contribution_pct'])}%",
        f"Top 3 chu kỳ profit / Gross Profit: {fmt(metrics['top3_profit_cycles_contribution_pct'])}%",
    ]
    for year, sides in metrics["yearly_side_metrics"].items():
        long_side = sides["long"]
        short_side = sides["short"]
        lines.append(
            f"{year}: Long PF={fmt(long_side['profit_factor'])} net={fmt(long_side['net'])} trades={long_side['trades']} | "
            f"Short PF={fmt(short_side['profit_factor'])} net={fmt(short_side['net'])} trades={short_side['trades']}"
        )
    return "\n".join(lines)


def json_safe(value):
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description="Tóm tắt báo cáo Strategy Tester của MT5")
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--expect-expert")
    parser.add_argument("--expect-symbol")
    parser.add_argument("--expect-period")
    parser.add_argument("--expect-from")
    parser.add_argument("--expect-to")
    args = parser.parse_args()

    html = read_report(args.report)
    table_parser = ReportTableParser()
    table_parser.feed(html)
    metrics = collect_metrics(table_parser.rows)

    if args.validate:
        errors = validate_report(metrics, args)
        if errors:
            for error in errors:
                print(f"REPORT_INVALID: {error}", file=sys.stderr)
            return 3
        print("REPORT_VALID")
        return 0

    if args.json:
        json_metrics = json_safe(metrics)
        print(json.dumps(json_metrics, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(render_text(metrics, args.report))


if __name__ == "__main__":
    raise SystemExit(main() or 0)
