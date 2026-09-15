"""CLI for the offline Trading Agent Phase 2 pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .pipeline import Phase2Pipeline


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repository root")
    parser.add_argument("--db", type=Path, default=argparse.SUPPRESS, help="Phase 1 SQLite path")
    parser.add_argument("--report-dir", type=Path, default=argparse.SUPPRESS, help="Phase 2 report directory")
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="Phase 2 JSON config")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/trading_agent/phase2"))
    parser.add_argument("--config", type=Path, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build-features", "build-regimes", "validate-similarity", "train", "evaluate", "report", "run-all"):
        command = commands.add_parser(name)
        _common_arguments(command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pipeline = Phase2Pipeline(
        root=args.root,
        db_path=args.db,
        report_dir=args.report_dir,
        config_path=args.config,
    )
    method = {
        "build-features": pipeline.build_features,
        "build-regimes": pipeline.build_regimes,
        "validate-similarity": pipeline.validate_similarity,
        "train": pipeline.train,
        "evaluate": pipeline.evaluate,
        "report": pipeline.report,
        "run-all": pipeline.run_all,
    }[args.command]
    result = method()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    if args.command == "run-all":
        return 0 if result.get("PHASE2_ENGINEERING_STATUS") == "PASS" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
