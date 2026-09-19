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
from .forward import (
    ForwardControlError,
    PersistentForwardCollector,
    create_forward_run,
    build_historical_index_artifact,
    current_git_sha,
    load_forward_config,
    prepare_forward_authorization,
    read_runtime_status,
    request_stop_forward,
    validate_forward_authorization,
)
from .node_ops import (
    NodeOpsError,
    acknowledge_takeover,
    bootstrap_forward_node,
    create_backup,
    create_deployment_package,
    handoff_snapshot,
    ops_health,
    plan_cross_machine_migration,
    restore_backup,
    run_mt5_preflight,
    takeover_check,
    verify_backup,
    verify_deployment_package,
)
from .runtime import Phase3Runtime
from .mt5_watchdog import (
    load_watchdog_config,
    recover_once,
    watchdog_health,
    watchdog_status,
)


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
    parser.add_argument("--runtime-config", type=Path, default=argparse.SUPPRESS, help="local persistent runtime config")
    parser.add_argument("--authorization", type=Path, default=argparse.SUPPRESS, help="local FORWARD authorization manifest")


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

    build_index = commands.add_parser("build-history-index", help="build the frozen-cutoff similarity index outside the repository")
    _common_arguments(build_index)
    build_index.add_argument("--source-db", type=Path, required=True, help="read-only canonical Phase 1 SQLite source")
    build_index.add_argument("--output", type=Path, required=True, help="runtime index artifact output")

    prepare = commands.add_parser("prepare-forward", help="validate gates and write local FORWARD authorization")
    _common_arguments(prepare)
    prepare.add_argument("--gates", type=Path, required=True, help="JSON gate evidence with PASS statuses")
    prepare.add_argument("--output", type=Path, default=None)

    start = commands.add_parser("start-forward", help="start an explicitly authorized persistent FORWARD collector")
    _common_arguments(start)
    start.add_argument("--max-iterations", type=int, default=None)

    resume = commands.add_parser("resume-forward", help="resume the same authorized FORWARD run after restart")
    _common_arguments(resume)
    resume.add_argument("--max-iterations", type=int, default=None)

    stop = commands.add_parser("stop-forward", help="request a collector-only stop")
    _common_arguments(stop)

    runtime_status = commands.add_parser("status-runtime", help="show persistent collector machine status")
    _common_arguments(runtime_status)
    runtime_status.add_argument("--json", action="store_true", help="emit JSON output")

    package = commands.add_parser("package-forward-node", help="create an integrity-checked deployment package")
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--approved-git-sha", required=True)
    package.add_argument("--repository-url", required=True)
    package.add_argument("--bundle-manifest", type=Path, required=True)
    package.add_argument("--model-bundle", type=Path, required=True)
    package.add_argument("--history-index", type=Path, required=True)
    package.add_argument("--ea-ex5", type=Path, required=True)
    package.add_argument("--ea-preset", type=Path, required=True)
    package.add_argument("--ea-source-revision", required=True)
    package.add_argument("--dependency-manifest", type=Path, required=True)
    package.add_argument("--source-mq5", type=Path, default=None)
    package.add_argument("--phase1-fingerprint", default=None)
    package.add_argument("--trusted-manifest-digest", default=None)
    package.add_argument("--test-only", action="store_true")

    package_verify = commands.add_parser("verify-forward-package", help="verify deployment package checksums and frozen contract")
    package_verify.add_argument("--package-path", type=Path, required=True)
    package_verify.add_argument("--expected-git-sha", default=None)
    package_verify.add_argument("--expected-trusted-manifest-digest", default=None)

    bootstrap = commands.add_parser("bootstrap-forward-node", help="bootstrap source/runtime/ops without activation")
    bootstrap.add_argument("--package-path", type=Path, required=True)
    bootstrap.add_argument("--install-root", type=Path, required=True)
    bootstrap.add_argument("--runtime-root", type=Path, required=True)
    bootstrap.add_argument("--ops-root", type=Path, required=True)
    bootstrap.add_argument("--expected-git-sha", required=True)
    bootstrap.add_argument("--expected-trusted-manifest-digest", default=None)
    bootstrap.add_argument("--python-executable", type=Path, default=None)
    bootstrap.add_argument("--allow-non-windows-test-only", action="store_true")

    handoff = commands.add_parser("handoff-snapshot", help="write atomic dynamic handoff outside Git")
    handoff.add_argument("--runtime-config", type=Path, required=True)
    handoff.add_argument("--ops-root", type=Path, required=True)
    handoff.add_argument("--run-id", default=None)
    handoff.add_argument("--next-step", default=None)

    health = commands.add_parser("ops-health", help="read-only collector and node health observer")
    health.add_argument("--runtime-config", type=Path, required=True)
    health.add_argument("--ops-root", type=Path, required=True)
    health.add_argument("--warning-disk-free-bytes", type=int, default=10 * 1024 * 1024 * 1024)
    health.add_argument("--critical-disk-free-bytes", type=int, default=2 * 1024 * 1024 * 1024)

    backup = commands.add_parser("backup-forward-runtime", help="create a WAL-safe consistent backup")
    backup.add_argument("--runtime-config", type=Path, required=True)
    backup.add_argument("--ops-root", type=Path, required=True)
    backup.add_argument("--backup-root", type=Path, default=None)
    backup.add_argument("--backup-id", default=None)

    backup_verify = commands.add_parser("verify-forward-backup", help="verify backup without restoring over a runtime")
    backup_verify.add_argument("--backup-path", type=Path, required=True)
    backup_verify.add_argument("--source-path", type=Path, default=None)

    restore = commands.add_parser("restore-forward-backup", help="restore an isolated evidence copy")
    restore.add_argument("--backup-path", type=Path, required=True)
    restore.add_argument("--target-root", type=Path, required=True)
    restore.add_argument("--mode", choices=("isolated",), default="isolated")

    migration = commands.add_parser("plan-forward-migration", help="write cross-machine migration plan; no continuity claim")
    migration.add_argument("--backup-path", type=Path, required=True)
    migration.add_argument("--new-install-root", type=Path, required=True)
    migration.add_argument("--new-runtime-root", type=Path, required=True)
    migration.add_argument("--output", type=Path, default=None)

    mt5 = commands.add_parser("mt5-preflight", help="audit MT5 paths and journal evidence without starting terminal")
    mt5.add_argument("--terminal-path", type=Path, required=True)
    mt5.add_argument("--data-directory", type=Path, required=True)
    mt5.add_argument("--ea-path", type=Path, required=True)
    mt5.add_argument("--preset-path", type=Path, required=True)
    mt5.add_argument("--primary-source-path", type=Path, required=True)
    mt5.add_argument("--ops-root", type=Path, required=True)
    mt5.add_argument("--expected-server", default=None)
    mt5.add_argument("--expected-account", default=None)
    mt5.add_argument("--symbol", default="BTCUSD")
    mt5.add_argument("--timeframe", default="H1")
    mt5.add_argument("--common-files-root", type=Path, default=None)
    mt5.add_argument("--journal-evidence-path", type=Path, default=None)
    mt5.add_argument("--terminal-version", default=None)
    mt5.add_argument("--expected-ea-sha256", default=None)
    mt5.add_argument("--expected-preset-sha256", default=None)
    mt5.add_argument("--market-data-confirmed", action="store_true")
    mt5.add_argument("--real-record-confirmed", action="store_true")

    takeover = commands.add_parser("takeover-check", help="check persistent handoff before agent takeover")
    takeover.add_argument("--ops-root", type=Path, required=True)
    takeover.add_argument("--expected-run-id", default=None)
    takeover.add_argument("--expected-git-sha", default=None)
    takeover.add_argument("--expected-source-identity", default=None)

    takeover_ack = commands.add_parser("takeover-ack", help="append a takeover acknowledgement without restarting collector")
    takeover_ack.add_argument("--ops-root", type=Path, required=True)
    takeover_ack.add_argument("--agent-id", required=True)
    takeover_ack.add_argument("--expected-run-id", default=None)
    takeover_ack.add_argument("--expected-git-sha", default=None)
    takeover_ack.add_argument("--expected-source-identity", default=None)

    watchdog_common = (
        "mt5-watchdog-status", "mt5-watchdog-health", "mt5-watchdog-recover-once",
        "mt5-watchdog-dry-run", "mt5-watchdog-start", "mt5-watchdog-stop",
    )
    for command_name in watchdog_common:
        command_help = {
            "mt5-watchdog-status": "read-only status for isolated MT5 telemetry instances",
            "mt5-watchdog-health": "read-only health classification for isolated MT5 telemetry instances",
            "mt5-watchdog-recover-once": "recover at most one absent terminal after all safety gates pass",
            "mt5-watchdog-dry-run": "show recovery decisions without starting a process",
            "mt5-watchdog-start": "report watchdog service state; installation is operator-approved only",
            "mt5-watchdog-stop": "report watchdog service state; no process is stopped by this command",
        }[command_name]
        watchdog = commands.add_parser(command_name, help=command_help)
        watchdog.add_argument("--config", type=Path, required=True, help="MT5 watchdog JSON config")
        if command_name in {"mt5-watchdog-recover-once", "mt5-watchdog-dry-run"}:
            watchdog.add_argument("--instance", default=None)

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


def _runtime_config(args: argparse.Namespace) -> Any:
    if not getattr(args, "runtime_config", None):
        raise SystemExit("command requires --runtime-config")
    try:
        return load_forward_config(Path(args.runtime_config))
    except ForwardControlError as exc:
        raise SystemExit(str(exc)) from exc


def _command_build_history_index(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    bundle = _load_bundle(_path(root, args.bundle))
    try:
        result = build_historical_index_artifact(_path(root, args.source_db), _path(root, args.output), bundle)
    except ForwardControlError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)
    return 0


def _command_prepare_forward(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    gates = _load_mapping(Path(args.gates))
    try:
        authorization = prepare_forward_authorization(config, gates=gates, output=args.output)
    except ForwardControlError as exc:
        raise SystemExit(f"FORWARD authorization refused: {exc}") from exc
    _print({"status": "FORWARD_AUTHORIZATION_READY", **authorization.to_dict()})
    return 0


def _forward_collector(args: argparse.Namespace, *, resume: bool) -> int:
    config = _runtime_config(args)
    authorization_path = Path(args.authorization) if args.authorization else config.authorization_path
    try:
        authorization, bundle, model, index = validate_forward_authorization(
            authorization_path,
            config,
            check_source_identity=not resume,
        )
        if not resume and not config.telemetry.is_file():
            raise ForwardControlError("telemetry source is unavailable; start-forward refuses waiting activation")
        if resume:
            if not args.run_id:
                raise ForwardControlError("resume-forward requires --run-id")
            run_id = str(args.run_id)
        else:
            short_sha = current_git_sha(config.repo_path)[:12]
            run_id = str(args.run_id or f"P3-FWD-{datetime_now_token()}-{short_sha}")
            create_forward_run(config, authorization, bundle, run_id=run_id)
        collector = PersistentForwardCollector(
            config,
            authorization,
            bundle,
            model,
            index,
            run_id=run_id,
        )
        result = collector.run_forever(max_iterations=args.max_iterations)
    except ForwardControlError as exc:
        raise SystemExit(f"FORWARD start refused: {exc}") from exc
    _print({"status": "FORWARD_COLLECTOR_FINISHED", "run_id": run_id, **result})
    return 0


def datetime_now_token() -> str:
    """Tạo token UTC dễ đọc cho run ID, không dùng làm event identity."""

    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _command_stop_forward(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    if not args.run_id:
        raise SystemExit("stop-forward requires --run-id")
    _print(request_stop_forward(config, run_id=str(args.run_id)))
    return 0


def _command_status_runtime(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    _print(read_runtime_status(config, run_id=args.run_id))
    return 0


def _node_ops_call(function: Any, *args: Any, **kwargs: Any) -> int:
    """Chuẩn hóa lỗi fail-closed thành stderr/exit code cho wrapper PowerShell."""

    try:
        result = function(*args, **kwargs)
    except NodeOpsError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)
    return 0


def _command_package_forward_node(args: argparse.Namespace) -> int:
    return _node_ops_call(
        create_deployment_package,
        args.output,
        approved_git_sha=args.approved_git_sha,
        repository_url=args.repository_url,
        bundle_manifest=args.bundle_manifest,
        model_bundle=args.model_bundle,
        history_index=args.history_index,
        ea_ex5=args.ea_ex5,
        ea_preset=args.ea_preset,
        ea_source_revision=args.ea_source_revision,
        dependency_manifest=args.dependency_manifest,
        source_mq5=args.source_mq5,
        phase1_fingerprint=args.phase1_fingerprint,
        trusted_manifest_digest=args.trusted_manifest_digest,
        test_only=bool(args.test_only),
    )


def _command_verify_forward_package(args: argparse.Namespace) -> int:
    return _node_ops_call(
        verify_deployment_package,
        args.package_path,
        expected_git_sha=args.expected_git_sha,
        expected_trusted_manifest_digest=args.expected_trusted_manifest_digest,
    )


def _command_bootstrap_forward_node(args: argparse.Namespace) -> int:
    return _node_ops_call(
        bootstrap_forward_node,
        args.package_path,
        install_root=args.install_root,
        runtime_root=args.runtime_root,
        ops_root=args.ops_root,
        expected_git_sha=args.expected_git_sha,
        expected_trusted_manifest_digest=args.expected_trusted_manifest_digest,
        python_executable=args.python_executable,
        require_windows=not bool(args.allow_non_windows_test_only),
        platform_name=None,
    )


def _command_handoff_snapshot(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    return _node_ops_call(handoff_snapshot, config, args.ops_root, run_id=args.run_id, next_step=args.next_step)


def _command_ops_health(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    return _node_ops_call(
        ops_health,
        config,
        args.ops_root,
        warning_disk_free_bytes=args.warning_disk_free_bytes,
        critical_disk_free_bytes=args.critical_disk_free_bytes,
    )


def _command_backup_forward_runtime(args: argparse.Namespace) -> int:
    config = _runtime_config(args)
    return _node_ops_call(create_backup, config, args.ops_root, backup_root=args.backup_root, backup_id=args.backup_id)


def _command_verify_forward_backup(args: argparse.Namespace) -> int:
    result = verify_backup(args.backup_path, source_path=args.source_path)
    _print(result)
    return 0 if result.get("status") == "BACKUP_VALID" else 1


def _command_restore_forward_backup(args: argparse.Namespace) -> int:
    return _node_ops_call(restore_backup, args.backup_path, args.target_root, mode=args.mode)


def _command_plan_forward_migration(args: argparse.Namespace) -> int:
    return _node_ops_call(
        plan_cross_machine_migration,
        args.backup_path,
        new_install_root=args.new_install_root,
        new_runtime_root=args.new_runtime_root,
        output=args.output,
    )


def _command_mt5_preflight(args: argparse.Namespace) -> int:
    try:
        result = run_mt5_preflight(
            terminal_path=args.terminal_path,
            data_directory=args.data_directory,
            ea_path=args.ea_path,
            preset_path=args.preset_path,
            primary_source_path=args.primary_source_path,
            ops_root=args.ops_root,
            expected_server=args.expected_server,
            expected_account=args.expected_account,
            symbol=args.symbol,
            timeframe=args.timeframe,
            common_files_root=args.common_files_root,
            journal_evidence_path=args.journal_evidence_path,
            terminal_version=args.terminal_version,
            market_data_confirmed=bool(args.market_data_confirmed),
            real_record_confirmed=bool(args.real_record_confirmed),
            expected_ea_sha256=args.expected_ea_sha256,
            expected_preset_sha256=args.expected_preset_sha256,
        )
    except NodeOpsError as exc:
        raise SystemExit(str(exc)) from exc
    _print(result)
    return 0 if result.get("preflight_status") == "PASS" else 1


def _command_takeover_check(args: argparse.Namespace) -> int:
    return _node_ops_call(
        takeover_check,
        args.ops_root,
        expected_run_id=args.expected_run_id,
        expected_git_sha=args.expected_git_sha,
        expected_source_identity=args.expected_source_identity,
    )


def _command_takeover_ack(args: argparse.Namespace) -> int:
    return _node_ops_call(
        acknowledge_takeover,
        args.ops_root,
        agent_id=args.agent_id,
        expected_run_id=args.expected_run_id,
        expected_git_sha=args.expected_git_sha,
        expected_source_identity=args.expected_source_identity,
    )


def _watchdog_config(args: argparse.Namespace):
    try:
        return load_watchdog_config(args.config)
    except (OSError, ValueError, TypeError) as exc:
        raise SystemExit(f"watchdog config rejected: {exc}") from exc


def _command_watchdog_status(args: argparse.Namespace) -> int:
    _print(watchdog_status(_watchdog_config(args)))
    return 0


def _command_watchdog_health(args: argparse.Namespace) -> int:
    result = watchdog_health(_watchdog_config(args))
    _print(result)
    return 0 if result.get("health_status") == "HEALTHY" else 1


def _command_watchdog_recover(args: argparse.Namespace, *, dry_run: bool) -> int:
    result = recover_once(_watchdog_config(args), instance_name=args.instance, dry_run=dry_run)
    _print(result)
    return 0 if result.get("status") == "PASS" else 1


def _command_watchdog_install_state(args: argparse.Namespace) -> int:
    _print({
        "schema": "phase3-mt5-watchdog-install/1",
        "status": "NOT_INSTALLED_OR_DISABLED",
        "action": "NONE",
        "reason": "Operator approval is required before installing or enabling any persistent Windows task/service.",
        "trading_action": "NONE",
    })
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
        "build-history-index": _command_build_history_index,
        "prepare-forward": _command_prepare_forward,
        "start-forward": lambda value: _forward_collector(value, resume=False),
        "resume-forward": lambda value: _forward_collector(value, resume=True),
        "stop-forward": _command_stop_forward,
        "status-runtime": _command_status_runtime,
        "package-forward-node": _command_package_forward_node,
        "verify-forward-package": _command_verify_forward_package,
        "bootstrap-forward-node": _command_bootstrap_forward_node,
        "handoff-snapshot": _command_handoff_snapshot,
        "ops-health": _command_ops_health,
        "backup-forward-runtime": _command_backup_forward_runtime,
        "verify-forward-backup": _command_verify_forward_backup,
        "restore-forward-backup": _command_restore_forward_backup,
        "plan-forward-migration": _command_plan_forward_migration,
        "mt5-preflight": _command_mt5_preflight,
        "takeover-check": _command_takeover_check,
        "takeover-ack": _command_takeover_ack,
        "mt5-watchdog-status": _command_watchdog_status,
        "mt5-watchdog-health": _command_watchdog_health,
        "mt5-watchdog-recover-once": lambda value: _command_watchdog_recover(value, dry_run=False),
        "mt5-watchdog-dry-run": lambda value: _command_watchdog_recover(value, dry_run=True),
        "mt5-watchdog-start": _command_watchdog_install_state,
        "mt5-watchdog-stop": _command_watchdog_install_state,
    }
    return int(commands[args.command](args))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
