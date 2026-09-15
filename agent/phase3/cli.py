"""Command-line interface for the Phase 3 shadow bridge and evidence flow."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from ..scoring.train import ModelBundle
from ..similarity.index import HistoricalSimilarityIndex
from ..similarity.models import SimilarityConfig
from ..memory.database import connect_database
from .bundle import freeze_bundle, validate_bundle, write_bundle_manifest
from .config import Phase3Config
from .evaluation.metrics import evaluate_forward_records
from .evaluation.reporting import write_phase3_reports
from .runtime import Phase3Runtime


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    """Cho phép đặt các đường dẫn chung trước hoặc sau tên command."""

    parser.add_argument("--root", type=Path, default=argparse.SUPPRESS, help="repository root")
    parser.add_argument("--db", type=Path, default=argparse.SUPPRESS, help="SQLite path")
    parser.add_argument("--report-dir", type=Path, default=argparse.SUPPRESS, help="Phase 3 report directory")
    parser.add_argument("--phase1-report-dir", type=Path, default=argparse.SUPPRESS, help="Phase 1 report directory")
    parser.add_argument("--phase2-report-dir", type=Path, default=argparse.SUPPRESS, help="Phase 2 report directory")
    parser.add_argument("--bundle", type=Path, default=argparse.SUPPRESS, help="frozen bundle manifest")
    parser.add_argument("--model-bundle", type=Path, default=argparse.SUPPRESS, help="local Phase 2 model bundle")
    parser.add_argument("--history-json", type=Path, default=argparse.SUPPRESS, help="historical rows with feature vectors")
    parser.add_argument("--run-id", default=argparse.SUPPRESS, help="forward/shadow run identifier")
    parser.add_argument("--mode", choices=("SMOKE", "REPLAY", "FORWARD"), default=argparse.SUPPRESS)
    parser.add_argument("--telemetry", type=Path, default=argparse.SUPPRESS, help="JSONL/NDJSON/CSV telemetry file")
    parser.add_argument("--format", dest="file_format", default=argparse.SUPPRESS, choices=("jsonl", "ndjson", "csv"))
    parser.add_argument("--source", default=argparse.SUPPRESS, help="telemetry source label")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--db", type=Path, default=Path("data/trading_memory.db"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports/trading_agent/phase3"))
    parser.add_argument("--phase1-report-dir", type=Path, default=Path("reports/trading_agent/phase1"))
    parser.add_argument("--phase2-report-dir", type=Path, default=Path("reports/trading_agent/phase2"))
    parser.add_argument("--bundle", type=Path, default=Path("reports/trading_agent/phase3/shadow_bundle_manifest.json"))
    parser.add_argument("--model-bundle", type=Path, default=Path("reports/trading_agent/phase2/model_bundle.json"))
    parser.add_argument("--history-json", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--mode", choices=("SMOKE", "REPLAY", "FORWARD"), default=None)
    parser.add_argument("--telemetry", type=Path, default=None)
    parser.add_argument("--format", dest="file_format", default="jsonl", choices=("jsonl", "ndjson", "csv"))
    parser.add_argument("--source", default="telemetry")
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze-bundle", help="freeze Phase 2 provenance into a Phase 3 manifest")
    _common_arguments(freeze)
    freeze.add_argument("--phase2-base-sha", default=None)
    freeze.add_argument("--cutoff", dest="historical_reference_cutoff", default=None)
    freeze.add_argument("--created-at", default=None)
    freeze.add_argument("--seed", type=int, default=42)
    freeze.add_argument("--output", type=Path, default=argparse.SUPPRESS)

    validate = commands.add_parser("validate-bundle", help="validate frozen bundle integrity")
    _common_arguments(validate)

    replay = commands.add_parser("replay", help="replay recorded telemetry through the frozen bridge")
    _common_arguments(replay)
    replay.add_argument("--tolerance", type=float, default=1e-8)

    shadow = commands.add_parser("start-shadow", help="start a non-executing shadow run")
    _common_arguments(shadow)
    shadow.add_argument("--tolerance", type=float, default=1e-8)

    status = commands.add_parser("status", help="show shadow/forward run status")
    _common_arguments(status)

    outcomes = commands.add_parser("resolve-outcomes", help="resolve delayed outcomes from an explicit evidence file")
    _common_arguments(outcomes)
    outcomes.add_argument("--outcomes", type=Path, required=True, help="JSON object mapping event IDs to future bars")
    outcomes.add_argument("--observed-at", default=None)

    evaluate = commands.add_parser("evaluate", help="evaluate only resolved forward outcomes")
    _common_arguments(evaluate)

    report = commands.add_parser("report", help="write the reviewable Phase 3 report set")
    _common_arguments(report)
    report.add_argument("--parity-report", type=Path, default=None)
    report.add_argument("--forward-validation", type=Path, default=None)

    return parser


def _path(root: Path, value: str | Path) -> Path:
    target = Path(value)
    return target if target.is_absolute() else root / target


def _json_load(path: Path, *, required: bool = True) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if not required:
            return None
        raise SystemExit(f"JSON artifact not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON artifact {path}: {exc}") from exc


def _load_mapping(path: Path, *, required: bool = True) -> Mapping[str, Any]:
    payload = _json_load(path, required=required)
    if payload is None and not required:
        return {}
    if not isinstance(payload, Mapping):
        raise SystemExit(f"JSON artifact must be an object: {path}")
    return payload


def _load_bundle(path: Path):
    return validate_bundle(_load_mapping(path))


def _git_head(root: Path) -> str | None:
    """Lấy SHA checkout hiện tại để ghi provenance, không sửa Git state."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _load_model(path: Path) -> ModelBundle | None:
    payload = _json_load(path, required=False)
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise SystemExit(f"model bundle must be an object: {path}")
    return ModelBundle.from_dict(payload)


def _load_similarity(path: Path | None) -> HistoricalSimilarityIndex | None:
    if path is None:
        return None
    payload = _json_load(path, required=True)
    rows = payload.get("rows", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise SystemExit(f"historical similarity JSON must contain a list of rows: {path}")
    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise SystemExit(f"historical similarity row must be an object: {path}")
        value = dict(row)
        if "feature_vector" not in value and "normalized_vector" in value:
            value["feature_vector"] = value.pop("normalized_vector")
        normalized.append(value)
    return HistoricalSimilarityIndex(normalized)


def _runtime(args: argparse.Namespace, bundle: Any, *, mode: str) -> Phase3Runtime:
    root = Path(args.root).resolve()
    db_path = _path(root, args.db)
    model_path = _path(root, args.model_bundle)
    history_path = _path(root, args.history_json) if args.history_json else None
    config = Phase3Config(mode=mode, bundle_id=bundle.bundle_id, telemetry_source=str(args.source), db_path=str(db_path))
    connection = connect_database(db_path)
    return Phase3Runtime(
        connection,
        bundle,
        model_bundle=_load_model(model_path),
        similarity_index=_load_similarity(history_path),
        config=config,
    )


def _run_id(args: argparse.Namespace, prefix: str, bundle_id: str) -> str:
    value = args.run_id
    return str(value) if value else f"p3-{prefix}-{bundle_id[-16:]}"


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def _command_freeze(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    phase1_dir = _path(root, args.phase1_report_dir)
    phase2_dir = _path(root, args.phase2_report_dir)
    phase1 = _load_mapping(phase1_dir / "dataset_manifest.json")
    feature = _load_mapping(phase2_dir / "feature_manifest.json")
    regime = _load_mapping(phase2_dir / "regime_manifest.json")
    model_manifest = _load_mapping(phase2_dir / "model_manifest.json")
    model_payload = _json_load(phase2_dir / "model_bundle.json", required=False)
    if model_payload is not None and not isinstance(model_payload, Mapping):
        raise SystemExit("Phase 2 model_bundle.json must be an object")
    phase1_fingerprint = str(phase1.get("dataset_fingerprint") or feature.get("dataset_fingerprint") or "")
    phase2_base_sha = str(args.phase2_base_sha or _git_head(root) or model_manifest.get("repository_base_sha") or feature.get("repository_base_sha") or "")
    cutoff = args.historical_reference_cutoff or regime.get("training_cutoff") or feature.get("training_cutoff")
    if not cutoff:
        split = _load_mapping(phase2_dir / "split_manifest.json", required=False)
        cutoff = split.get("train_end")
    bundle = freeze_bundle(
        phase1_fingerprint=phase1_fingerprint,
        phase2_base_sha=phase2_base_sha,
        feature_manifest=feature,
        regime_manifest=regime,
        model_manifest=model_manifest,
        model_bundle=model_payload,
        similarity_config=SimilarityConfig().to_dict(),
        historical_reference_cutoff_utc=str(cutoff) if cutoff else None,
        seed=int(args.seed),
        created_at_utc=args.created_at,
    )
    output = _path(root, args.output) if hasattr(args, "output") and args.output else _path(root, args.report_dir) / "shadow_bundle_manifest.json"
    write_bundle_manifest(bundle, output)
    _print({
        "status": "BUNDLE_FROZEN",
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "output": str(output),
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "phase2_base_sha": bundle.phase2_base_sha,
        "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
        "model_payload_in_manifest": False,
        "execution_mode": "NONE",
        "live_execution_enabled": False,
    })
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    _print({
        "status": "BUNDLE_VALID",
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "phase2_base_sha": bundle.phase2_base_sha,
        "feature_set_version": bundle.feature_set_version,
        "model_version": bundle.model_version,
        "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
        "execution_mode": bundle.config_json.get("execution_mode"),
        "live_execution_enabled": bundle.config_json.get("live_execution_enabled"),
    })
    return 0


def _command_replay_or_shadow(args: argparse.Namespace, *, shadow: bool) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    mode = str(args.mode or ("SMOKE" if shadow else "REPLAY")).upper()
    if not shadow and mode != "REPLAY":
        raise SystemExit("replay command only accepts mode REPLAY")
    if shadow and mode == "FORWARD":
        raise SystemExit("start-shadow cannot activate FORWARD collection")
    runtime = _runtime(args, bundle, mode=mode)
    run_id = _run_id(args, "shadow" if shadow else "replay", bundle.bundle_id)
    try:
        run = runtime.create_run(run_id, mode=mode, source=str(args.source), git_sha=_git_head(root) or bundle.phase2_base_sha)
        result: dict[str, Any] = {"status": "SHADOW_READY" if shadow else "REPLAY_READY", "run": run}
        if args.telemetry:
            result["ingestion"] = runtime.ingest_file_once(run_id, _path(root, args.telemetry), source=str(args.source), file_format=str(args.file_format))
        if shadow:
            result["runtime_status"] = runtime.status(run_id)
        _print(result)
        return 0
    finally:
        runtime.close()


def _command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    runtime = _runtime(args, bundle, mode=str(args.mode or "SMOKE").upper())
    try:
        _print(runtime.status(args.run_id))
        return 0
    finally:
        runtime.close()


def _command_outcomes(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    if not args.run_id:
        raise SystemExit("resolve-outcomes requires --run-id")
    runtime = _runtime(args, bundle, mode=str(args.mode or "FORWARD").upper())
    try:
        payload = _load_mapping(_path(root, args.outcomes))
        result = runtime.resolve_outcomes(str(args.run_id), payload, observed_at_utc=args.observed_at)
        _print(result)
        return 0
    finally:
        runtime.close()


def _command_evaluate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    runtime = _runtime(args, bundle, mode=str(args.mode or "FORWARD").upper())
    try:
        _print(runtime.evaluate(args.run_id))
        return 0
    finally:
        runtime.close()


def _command_report(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    parity_path = _path(root, args.parity_report) if args.parity_report else _path(root, args.report_dir) / "replay_parity_report.json"
    validation_path = _path(root, args.forward_validation) if args.forward_validation else _path(root, args.report_dir) / "forward_validation.json"
    parity = _load_mapping(parity_path, required=False)
    validation = _load_mapping(validation_path, required=False)
    runtime_status: Mapping[str, Any] = {}
    db_path = _path(root, args.db)
    if db_path.exists() and args.run_id:
        runtime = _runtime(args, bundle, mode=str(args.mode or "FORWARD").upper())
        try:
            runtime_status = runtime.status(args.run_id)
            if not validation:
                validation = runtime.evaluate(args.run_id)
        finally:
            runtime.close()
    report = write_phase3_reports(
        _path(root, args.report_dir),
        bundle,
        replay_parity=parity or None,
        forward_validation=validation or evaluate_forward_records([]),
        runtime_status=runtime_status,
    )
    _print({"status": "REPORT_WRITTEN", "report_dir": str(_path(root, args.report_dir)), "statuses": report["statuses"]})
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commands = {
        "freeze-bundle": _command_freeze,
        "validate-bundle": _command_validate,
        "replay": lambda value: _command_replay_or_shadow(value, shadow=False),
        "start-shadow": lambda value: _command_replay_or_shadow(value, shadow=True),
        "status": _command_status,
        "resolve-outcomes": _command_outcomes,
        "evaluate": _command_evaluate,
        "report": _command_report,
    }
    return int(commands[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
