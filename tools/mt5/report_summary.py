#!/usr/bin/env python3

import argparse
import json
import math
import re
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


def collect_metrics(rows):
    values = {}
    for row in rows:
        for index, cell in enumerate(row[:-1]):
            if cell.endswith(":") and row[index + 1]:
                values[cell[:-1]] = row[index + 1]

    deal_header = None
    for index, row in enumerate(rows):
        if "Deal" in row and "Direction" in row and "Profit" in row:
            deal_header = index
            break

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

    return {
        "expert": values.get("Expert", ""),
        "symbol": values.get("Symbol", ""),
        "period": values.get("Period", ""),
        "deposit": values.get("Initial Deposit", ""),
        "history_quality": values.get("History Quality", ""),
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
        "largest_loss_trade": parse_number(values.get("Largest loss trade", "0")),
        "long_net_by_deals": sides["long"]["net"],
        "long_pf_by_deals": pf(sides["long"]["gross_profit"], sides["long"]["gross_loss"]),
        "short_net_by_deals": sides["short"]["net"],
        "short_pf_by_deals": pf(sides["short"]["gross_profit"], sides["short"]["gross_loss"]),
    }


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
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Tóm tắt báo cáo Strategy Tester của MT5")
    parser.add_argument("report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    html = read_report(args.report)
    table_parser = ReportTableParser()
    table_parser.feed(html)
    metrics = collect_metrics(table_parser.rows)

    if args.json:
        json_metrics = {
            key: ("inf" if isinstance(value, float) and math.isinf(value) else value)
            for key, value in metrics.items()
        }
        print(json.dumps(json_metrics, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(render_text(metrics, args.report))


if __name__ == "__main__":
    main()
