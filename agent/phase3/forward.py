"""Authorization và collector persistent cho Phase 3 FORWARD shadow-only."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from ..features.fingerprint import fingerprint
from ..memory.database import connect_database, integrity_status
from ..scoring.train import ModelBundle
from ..similarity.index import HistoricalSimilarityIndex
from ..similarity.models import SimilarityConfig
from .bundle import ShadowBundle, validate_bundle
from .config import Phase3Config
from .ingestion.file_tail import file_source_identity
from .ingestion.opportunity import CANONICALIZER_FINGERPRINT
from .models import (
    PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
    PHASE3_CANONICALIZER_VERSION,
    PHASE3_OPPORTUNITY_SCHEMA,
    PHASE3_TELEMETRY_SCHEMA,
    format_utc_timestamp,
    parse_utc_timestamp,
    sha256_json,
    utc_now,
)
from .runtime import Phase3Runtime


RUNTIME_CONFIG_SCHEMA = "phase3-forward-runtime/1"
AUTHORIZATION_SCHEMA = "phase3-forward-authorization/1"
HISTORY_INDEX_SCHEMA = "phase3-historical-similarity-index/1"
HEARTBEAT_SCHEMA = "phase3-forward-heartbeat/1"
DEFAULT_TASK_NAME = "BuildBot-Phase3-Forward"


class ForwardControlError(RuntimeError):
    """Yêu cầu FORWARD bị từ chối hoặc runtime không thể chạy an toàn."""


class AuthorizationError(ForwardControlError):
    """Manifest authorization không khớp contract hiện tại."""


class CollectorAlreadyRunning(ForwardControlError):
    """Đã có collector khác giữ OS lock."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _atomic_json_write(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Ghi state local theo kiểu thay thế nguyên file để heartbeat không dở dang."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(value: str | Path, *, base: Path) -> str:
    path = Path(value)
    return str((base / path).resolve() if not path.is_absolute() else path.resolve())


@dataclass(frozen=True)
class ForwardRuntimeConfig:
    """Các đường dẫn local của collector, không chứa secret hay trading flag."""

    runtime_root: str
    repo_path: str
    python_path: str
    bundle_manifest: str
    model_bundle_path: str
    history_index_path: str
    telemetry_path: str
    runtime_db: str
    primary_opportunity_path: str | None = None
    execution_diagnostic_path: str | None = None
    telemetry_format: str = "jsonl"
    telemetry_source: str = "mt5-phase3"
    schema_version: str = PHASE3_TELEMETRY_SCHEMA
    primary_opportunity_schema: str = PHASE3_OPPORTUNITY_SCHEMA
    canonical_schema: str = PHASE3_CANONICAL_OPPORTUNITY_SCHEMA
    canonicalizer_version: str = PHASE3_CANONICALIZER_VERSION
    canonicalizer_fingerprint: str = CANONICALIZER_FINGERPRINT
    execution_mode: str = "NONE"
    live_execution_enabled: bool = False
    heartbeat_interval_seconds: int = 30
    heartbeat_stale_seconds: int = 120
    poll_interval_seconds: float = 5.0
    task_name: str = DEFAULT_TASK_NAME

    def __post_init__(self) -> None:
        if str(self.execution_mode).upper() != "NONE":
            raise ForwardControlError("runtime execution_mode must be NONE")
        if bool(self.live_execution_enabled):
            raise ForwardControlError("runtime live_execution_enabled must be false")
        if self.schema_version != PHASE3_TELEMETRY_SCHEMA:
            raise ForwardControlError("runtime telemetry schema does not match Phase 3")
        if self.primary_opportunity_schema != PHASE3_OPPORTUNITY_SCHEMA:
            raise ForwardControlError("primary source must use the opportunity observation schema")
        if self.canonical_schema != PHASE3_CANONICAL_OPPORTUNITY_SCHEMA:
            raise ForwardControlError("primary source canonical schema does not match Phase 3")
        if self.canonicalizer_version != PHASE3_CANONICALIZER_VERSION:
            raise ForwardControlError("primary source canonicalizer version does not match Phase 1")
        if self.canonicalizer_fingerprint != CANONICALIZER_FINGERPRINT:
            raise ForwardControlError("primary source canonicalizer fingerprint does not match Phase 1")
        if str(self.telemetry_format).lower() not in {"jsonl", "ndjson", "csv"}:
            raise ForwardControlError("runtime telemetry_format must be jsonl, ndjson or csv")
        if self.heartbeat_interval_seconds < 1 or self.heartbeat_stale_seconds < self.heartbeat_interval_seconds:
            raise ForwardControlError("runtime heartbeat thresholds are invalid")
        if self.poll_interval_seconds <= 0 or self.poll_interval_seconds > 60:
            raise ForwardControlError("runtime poll_interval_seconds must be in (0, 60]")
        for field_name in (
            "runtime_root", "repo_path", "python_path", "bundle_manifest", "model_bundle_path",
            "history_index_path", "telemetry_path", "runtime_db",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ForwardControlError(f"runtime config field is empty: {field_name}")
        if not self.primary_opportunity_path or not str(self.primary_opportunity_path).strip():
            raise ForwardControlError("runtime config requires primary_opportunity_path")

    @property
    def root(self) -> Path:
        return Path(self.runtime_root)

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def control_dir(self) -> Path:
        return self.root / "control"

    @property
    def lock_path(self) -> Path:
        return self.state_dir / "collector.lock"

    @property
    def heartbeat_path(self) -> Path:
        return self.state_dir / "heartbeat.json"

    @property
    def current_run_path(self) -> Path:
        return self.state_dir / "current_run.json"

    @property
    def stop_path(self) -> Path:
        return self.control_dir / "stop_forward.json"

    @property
    def authorization_path(self) -> Path:
        return self.root / "config" / "forward_authorization.json"

    @property
    def telemetry(self) -> Path:
        return Path(self.execution_diagnostic_path or self.telemetry_path)

    @property
    def primary_opportunity(self) -> Path:
        """Đường dẫn raw opportunity primary, tách hẳn khỏi stream diagnostic cũ."""

        return Path(str(self.primary_opportunity_path))

    @property
    def has_explicit_primary_source(self) -> bool:
        return bool(self.primary_opportunity_path and str(self.primary_opportunity_path).strip())

    @property
    def db(self) -> Path:
        return Path(self.runtime_db)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["schema"] = RUNTIME_CONFIG_SCHEMA
        value["execution_mode"] = "NONE"
        value["live_execution_enabled"] = False
        value["execution_authority"] = "NONE"
        value["trade_control_authority"] = "NONE"
        value["position_control_authority"] = "NONE"
        value["risk_control_authority"] = "NONE"
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any], *, config_path: str | Path | None = None) -> "ForwardRuntimeConfig":
        if not isinstance(payload, Mapping):
            raise ForwardControlError("runtime config must be an object")
        if str(payload.get("schema", RUNTIME_CONFIG_SCHEMA)) != RUNTIME_CONFIG_SCHEMA:
            raise ForwardControlError("unknown runtime config schema")
        for key in ("execution_authority", "trade_control_authority", "position_control_authority", "risk_control_authority"):
            if key in payload and str(payload[key]).upper() != "NONE":
                raise ForwardControlError(f"runtime {key} must be NONE")
        if str(payload.get("execution_mode", "NONE")).upper() != "NONE" or payload.get("live_execution_enabled", False) is True:
            raise ForwardControlError("runtime execution flags must remain disabled")
        base = Path(config_path).resolve().parent if config_path is not None else Path.cwd()
        defaults = {
            "runtime_root": str(base),
            "repo_path": str(base),
            "python_path": sys.executable,
            "telemetry_format": "jsonl",
            "telemetry_source": "mt5-phase3",
            "schema_version": PHASE3_TELEMETRY_SCHEMA,
            "primary_opportunity_schema": PHASE3_OPPORTUNITY_SCHEMA,
            "canonical_schema": PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
            "canonicalizer_version": PHASE3_CANONICALIZER_VERSION,
            "canonicalizer_fingerprint": CANONICALIZER_FINGERPRINT,
            "execution_mode": "NONE",
            "live_execution_enabled": False,
            "heartbeat_interval_seconds": 30,
            "heartbeat_stale_seconds": 120,
            "poll_interval_seconds": 5.0,
            "task_name": DEFAULT_TASK_NAME,
        }
        values = dict(defaults)
        values.update({key: payload[key] for key in cls.__dataclass_fields__ if key in payload})
        for key in (
            "runtime_root", "repo_path", "bundle_manifest", "model_bundle_path", "history_index_path",
            "telemetry_path", "primary_opportunity_path", "execution_diagnostic_path", "runtime_db",
        ):
            if key in values and values[key]:
                values[key] = _resolve_path(str(values[key]), base=base)
        required = (
            "bundle_manifest", "model_bundle_path", "history_index_path",
            "telemetry_path", "primary_opportunity_path", "runtime_db",
        )
        missing = [name for name in required if not str(values.get(name, "")).strip()]
        if missing:
            raise ForwardControlError("runtime config fields are missing: " + ", ".join(missing))
        try:
            return cls(**values)
        except (TypeError, ValueError) as exc:
            raise ForwardControlError("runtime config fields are invalid") from exc


def load_forward_config(path: str | Path) -> ForwardRuntimeConfig:
    target = Path(path)
    return ForwardRuntimeConfig.from_dict(_read_json(target), config_path=target)


def write_forward_config(config: ForwardRuntimeConfig, path: str | Path) -> None:
    _atomic_json_write(path, config.to_dict())


def current_git_sha(repo_path: str | Path) -> str:
    """Đọc HEAD hiện tại mà không sửa Git state."""

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise ForwardControlError(f"cannot read git HEAD in {repo_path}")
    return value


def tracked_worktree_clean(repo_path: str | Path) -> bool:
    """Chỉ kiểm tra tracked changes; untracked data local không chặn authorization."""

    for command in (["git", "diff", "--quiet"], ["git", "diff", "--cached", "--quiet"]):
        result = subprocess.run(command, cwd=str(repo_path), capture_output=True, check=False)
        if result.returncode != 0:
            return False
    return True


def execution_api_path_count(repo_path: str | Path) -> int:
    """Đếm surface điều khiển bị cấm trong Phase 3/3.1 bằng closed-world scan."""

    # Ghép chuỗi tại runtime để chính hàm scan không tự tạo hit cho static gate.
    forbidden = (
        "order_" + "send", "order_" + "modify", "order_" + "cancel",
        "position_" + "modify", "trade_" + "request",
    )
    root = Path(repo_path) / "agent" / "phase3"
    return sum(path.read_text(encoding="utf-8").count(token) for path in root.rglob("*.py") for token in forbidden)


def _load_bundle(path: str | Path) -> ShadowBundle:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        raise AuthorizationError("bundle manifest must be an object")
    return validate_bundle(payload)


def _load_model(path: str | Path, bundle: ShadowBundle) -> ModelBundle:
    target = Path(path)
    if not target.is_file():
        raise AuthorizationError(f"model artifact is missing: {target}")
    payload = _read_json(target)
    if not isinstance(payload, Mapping):
        raise AuthorizationError("model artifact must be an object")
    model = ModelBundle.from_dict(payload)
    actual = fingerprint(model.to_dict())
    expected = str(bundle.config_json.get("model_payload_fingerprint") or bundle.model_fingerprint)
    if actual != expected or actual != bundle.model_fingerprint:
        raise AuthorizationError("model artifact fingerprint does not match frozen bundle")
    return model


def _validate_primary_source_contract(source: Path, config: ForwardRuntimeConfig) -> None:
    """Không cho file execution-candidate cũ được bind làm primary source."""

    if not config.has_explicit_primary_source:
        raise AuthorizationError("primary_opportunity_path must be configured")
    if config.telemetry_format.lower() not in {"jsonl", "ndjson"}:
        raise AuthorizationError("primary opportunity source must be JSONL/NDJSON")
    found = False
    try:
        with source.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if not isinstance(payload, Mapping) or payload.get("schema_version") != config.primary_opportunity_schema:
                    raise AuthorizationError("primary source contains a non-opportunity telemetry record")
                found = True
                return
    except AuthorizationError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise AuthorizationError("primary opportunity source is not valid JSONL") from exc
    if not found:
        raise AuthorizationError("primary opportunity source is empty")


def _similarity_config(bundle: ShadowBundle) -> dict[str, Any]:
    value = bundle.config_json.get("similarity_config", {})
    if not isinstance(value, Mapping):
        raise AuthorizationError("frozen similarity config is missing")
    return dict(value)


def load_history_index_artifact(path: str | Path, bundle: ShadowBundle) -> HistoricalSimilarityIndex:
    """Nạp index đã được đóng dấu, không tự động thêm row trong lúc live."""

    target = Path(path)
    if not target.is_file():
        raise AuthorizationError(f"historical similarity index is missing: {target}")
    payload = _read_json(target)
    if not isinstance(payload, Mapping) or payload.get("schema") != HISTORY_INDEX_SCHEMA:
        raise AuthorizationError("unknown historical similarity index schema")
    if str(payload.get("bundle_id")) != bundle.bundle_id:
        raise AuthorizationError("historical index bundle_id mismatch")
    if str(payload.get("phase1_fingerprint")) != bundle.phase1_fingerprint:
        raise AuthorizationError("historical index Phase 1 fingerprint mismatch")
    if str(payload.get("historical_reference_cutoff_utc")) != bundle.historical_reference_cutoff_utc:
        raise AuthorizationError("historical index cutoff mismatch")
    if str(payload.get("similarity_fingerprint")) != bundle.similarity_fingerprint:
        raise AuthorizationError("historical index similarity fingerprint mismatch")
    if dict(payload.get("similarity_config", {})) != _similarity_config(bundle):
        raise AuthorizationError("historical index similarity config mismatch")
    source_dataset = str(payload.get("source_dataset_fingerprint") or "")
    if source_dataset and source_dataset != bundle.phase1_fingerprint:
        raise AuthorizationError("historical index source dataset fingerprint mismatch")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise AuthorizationError("historical similarity index has no rows")
    cutoff = parse_utc_timestamp(bundle.historical_reference_cutoff_utc)
    for row in rows:
        if not isinstance(row, Mapping):
            raise AuthorizationError("historical similarity index row must be an object")
        try:
            timestamp = parse_utc_timestamp(str(row.get("timestamp_utc")))
        except ValueError as exc:
            raise AuthorizationError("historical index row timestamp is invalid") from exc
        if timestamp > cutoff:
            raise AuthorizationError("historical similarity index contains a row after frozen cutoff")
    config = SimilarityConfig.from_dict(_similarity_config(bundle))
    return HistoricalSimilarityIndex(rows, config=config)


def build_historical_index_artifact(
    source_db: str | Path,
    output: str | Path,
    bundle: ShadowBundle,
) -> dict[str, Any]:
    """Rebuild deterministic index từ canonical Phase 1 DB, chỉ tới cutoff frozen."""

    source = Path(source_db).resolve()
    if not source.is_file():
        raise ForwardControlError(f"historical source database is missing: {source}")
    uri = f"file:{source.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    cutoff = bundle.historical_reference_cutoff_utc
    query = """
        SELECT o.canonical_opportunity_id, o.timestamp_utc, o.symbol, o.timeframe,
               o.side, o.strategy_version, o.feature_status, o.features_json,
               o.context_json, o.labels_json, f.normalized_vector_json,
               s.dataset_fingerprint, r.composite_regime
        FROM canonical_opportunities o
        JOIN canonical_features f ON f.canonical_opportunity_id = o.canonical_opportunity_id
        LEFT JOIN phase2_splits s ON s.canonical_opportunity_id = o.canonical_opportunity_id
        LEFT JOIN regime_assignments r ON r.canonical_opportunity_id = o.canonical_opportunity_id
        WHERE o.timestamp_utc <= ?
        ORDER BY o.timestamp_utc, o.canonical_opportunity_id
    """
    rows: list[dict[str, Any]] = []
    datasets: set[str] = set()
    try:
        for source_row in connection.execute(query, (cutoff,)):
            if str(source_row["feature_status"]).upper() == "CONFLICT":
                continue
            features = json.loads(str(source_row["features_json"] or "{}"))
            context = json.loads(str(source_row["context_json"] or "{}"))
            labels = json.loads(str(source_row["labels_json"] or "{}"))
            vector = json.loads(str(source_row["normalized_vector_json"] or "[]"))
            if source_row["dataset_fingerprint"]:
                datasets.add(str(source_row["dataset_fingerprint"]))
            rows.append({
                "canonical_opportunity_id": str(source_row["canonical_opportunity_id"]),
                "timestamp_utc": format_utc_timestamp(str(source_row["timestamp_utc"])),
                "symbol": str(source_row["symbol"]),
                "timeframe": str(source_row["timeframe"]),
                "side": str(source_row["side"]),
                "strategy_version": str(source_row["strategy_version"]),
                "features": dict(features) if isinstance(features, Mapping) else {},
                "context": dict(context) if isinstance(context, Mapping) else {},
                "labels": dict(labels) if isinstance(labels, Mapping) else {},
                "regime": str(source_row["composite_regime"] or "UNKNOWN"),
                "feature_vector": vector,
                "feature_status": str(source_row["feature_status"] or "VALID"),
            })
    finally:
        connection.close()
    if datasets and datasets != {bundle.phase1_fingerprint}:
        raise ForwardControlError("historical source database dataset fingerprint does not match bundle")
    if not rows:
        raise ForwardControlError("historical source database produced no rows before cutoff")
    artifact: dict[str, Any] = {
        "schema": HISTORY_INDEX_SCHEMA,
        "bundle_id": bundle.bundle_id,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "source_dataset_fingerprint": bundle.phase1_fingerprint,
        "source_database_sha256": _file_sha256(source),
        "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
        "similarity_version": bundle.similarity_version,
        "similarity_fingerprint": bundle.similarity_fingerprint,
        "similarity_config": _similarity_config(bundle),
        "row_count": len(rows),
        "rows_fingerprint": fingerprint(rows),
        "rows": rows,
    }
    _atomic_json_write(output, artifact)
    return {
        "status": "HISTORICAL_INDEX_WRITTEN",
        "output": str(Path(output).resolve()),
        "row_count": len(rows),
        "rows_fingerprint": artifact["rows_fingerprint"],
        "historical_reference_cutoff_utc": cutoff,
        "similarity_fingerprint": bundle.similarity_fingerprint,
    }


@dataclass(frozen=True)
class ForwardAuthorization:
    """Bằng chứng gate local dùng để mở một FORWARD run cụ thể."""

    authorization_id: str
    created_at_utc: str
    authorized_git_sha: str
    bundle_id: str
    bundle_version: str
    phase1_fingerprint: str
    historical_reference_cutoff: str
    telemetry_schema: str
    telemetry_source_identity: str
    model_fingerprint: str
    similarity_fingerprint: str
    runtime_db: str
    replay_parity_status: str
    smoke_status: str
    db_integrity_status: str
    one_way_safety_status: str
    execution_api_path_count: int
    execution_mode: str = "NONE"
    live_execution_enabled: bool = False
    authorization_hash: str = ""
    telemetry_observation_schema: str = ""
    canonical_schema: str = ""
    canonicalizer_version: str = ""
    canonicalizer_fingerprint: str = ""
    primary_source_identity: str = ""

    def material(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("authorization_hash", None)
        return value

    def computed_hash(self) -> str:
        return sha256_json(self.material())

    def to_dict(self) -> dict[str, Any]:
        value = self.material()
        value["schema"] = AUTHORIZATION_SCHEMA
        value["authorization_hash"] = self.authorization_hash or self.computed_hash()
        value["execution_mode"] = "NONE"
        value["live_execution_enabled"] = False
        return value

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ForwardAuthorization":
        if str(payload.get("schema", "")) != AUTHORIZATION_SCHEMA:
            raise AuthorizationError("unknown forward authorization schema")
        values = {key: payload[key] for key in cls.__dataclass_fields__ if key in payload}
        try:
            return cls(**values)
        except TypeError as exc:
            raise AuthorizationError("forward authorization fields are incomplete") from exc


def _gate_value(gates: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "replay_parity_status": ("replay_parity_status", "replay_parity", "REPLAY_PARITY_STATUS"),
        "smoke_status": ("smoke_status", "smoke", "SHADOW_SMOKE_STATUS"),
        "db_integrity_status": ("db_integrity_status", "db_integrity", "DB_INTEGRITY_STATUS"),
        "one_way_safety_status": ("one_way_safety_status", "one_way_safety", "ONE_WAY_SAFETY_STATUS"),
    }
    for key in aliases[name]:
        if key in gates:
            return gates[key]
    return None


def prepare_forward_authorization(
    config: ForwardRuntimeConfig,
    *,
    gates: Mapping[str, Any],
    output: str | Path | None = None,
    now: str | None = None,
) -> ForwardAuthorization:
    """Kiểm tra mọi gate rồi tạo manifest local, không tự khởi động collector."""

    bundle = _load_bundle(config.bundle_manifest)
    if not tracked_worktree_clean(config.repo_path):
        raise AuthorizationError("tracked working tree is not clean")
    git_sha = current_git_sha(config.repo_path)
    model = _load_model(config.model_bundle_path, bundle)
    load_history_index_artifact(config.history_index_path, bundle)
    if not config.has_explicit_primary_source:
        raise AuthorizationError("primary_opportunity_path must be configured before authorization")
    source = config.primary_opportunity
    if not source.is_file():
        raise AuthorizationError(f"telemetry source is unavailable: {source}")
    _validate_primary_source_contract(source, config)
    source_identity = file_source_identity(source)
    db = connect_database(config.db)
    try:
        db_status = integrity_status(db)
    finally:
        db.close()
    if not db_status["integrity_ok"] or not db_status["foreign_key_ok"]:
        raise AuthorizationError("runtime database integrity gate failed")
    statuses = {
        name: str(_gate_value(gates, name) or "").upper()
        for name in ("replay_parity_status", "smoke_status", "db_integrity_status", "one_way_safety_status")
    }
    if any(value != "PASS" for value in statuses.values()):
        raise AuthorizationError("all replay, smoke, database and one-way gates must be PASS")
    count = int(gates.get("execution_api_path_count", gates.get("EXECUTION_API_PATH_COUNT", execution_api_path_count(config.repo_path))))
    if count != 0 or execution_api_path_count(config.repo_path) != 0:
        raise AuthorizationError("execution API path count must be zero")
    created = format_utc_timestamp(now or utc_now())
    material = {
        "authorization_id": "pending",
        "created_at_utc": created,
        "authorized_git_sha": git_sha,
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "historical_reference_cutoff": bundle.historical_reference_cutoff_utc,
        "telemetry_schema": config.schema_version,
        "telemetry_source_identity": source_identity,
        "telemetry_observation_schema": config.primary_opportunity_schema,
        "canonical_schema": config.canonical_schema,
        "canonicalizer_version": config.canonicalizer_version,
        "canonicalizer_fingerprint": config.canonicalizer_fingerprint,
        "primary_source_identity": source_identity,
        "model_fingerprint": bundle.model_fingerprint,
        "similarity_fingerprint": bundle.similarity_fingerprint,
        "runtime_db": str(config.db.resolve()),
        **statuses,
        "execution_api_path_count": 0,
        "execution_mode": "NONE",
        "live_execution_enabled": False,
    }
    authorization_id = "p3-auth-" + sha256_json(material)[0:24]
    authorization = ForwardAuthorization(authorization_id=authorization_id, **{key: value for key, value in material.items() if key != "authorization_id"})
    target = Path(output) if output is not None else config.authorization_path
    _atomic_json_write(target, authorization.to_dict())
    return authorization


def validate_forward_authorization(
    path: str | Path,
    config: ForwardRuntimeConfig,
    *,
    check_source_identity: bool = False,
) -> tuple[ForwardAuthorization, ShadowBundle, ModelBundle, HistoricalSimilarityIndex]:
    """Validate auth against current HEAD, frozen assets and runtime paths."""

    try:
        payload = _read_json(path)
    except (OSError, TypeError, ValueError) as exc:
        raise AuthorizationError(f"forward authorization manifest is unavailable or invalid: {path}") from exc
    if not isinstance(payload, Mapping):
        raise AuthorizationError("forward authorization must be an object")
    authorization = ForwardAuthorization.from_dict(payload)
    if authorization.authorization_hash != authorization.computed_hash():
        raise AuthorizationError("authorization hash mismatch")
    bundle = _load_bundle(config.bundle_manifest)
    if not config.has_explicit_primary_source:
        raise AuthorizationError("primary_opportunity_path must be configured before FORWARD validation")
    current_sha = current_git_sha(config.repo_path)
    if current_sha != authorization.authorized_git_sha:
        raise AuthorizationError("current HEAD differs from authorized git SHA")
    if not tracked_worktree_clean(config.repo_path):
        raise AuthorizationError("tracked working tree is not clean")
    expected = {
        "bundle_id": bundle.bundle_id,
        "bundle_version": bundle.bundle_version,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "historical_reference_cutoff": bundle.historical_reference_cutoff_utc,
        "telemetry_schema": config.schema_version,
        "model_fingerprint": bundle.model_fingerprint,
        "similarity_fingerprint": bundle.similarity_fingerprint,
        "runtime_db": str(config.db.resolve()),
    }
    if config.has_explicit_primary_source:
        expected.update(
            {
                "telemetry_observation_schema": config.primary_opportunity_schema,
                "canonical_schema": config.canonical_schema,
                "canonicalizer_version": config.canonicalizer_version,
                "canonicalizer_fingerprint": config.canonicalizer_fingerprint,
                "primary_source_identity": authorization.telemetry_source_identity,
            }
        )
    for key, value in expected.items():
        if str(getattr(authorization, key)) != str(value):
            raise AuthorizationError(f"authorization {key} mismatch")
    if authorization.execution_mode != "NONE" or authorization.live_execution_enabled or authorization.execution_api_path_count != 0:
        raise AuthorizationError("authorization execution flags are unsafe")
    for key in ("replay_parity_status", "smoke_status", "db_integrity_status", "one_way_safety_status"):
        if str(getattr(authorization, key)).upper() != "PASS":
            raise AuthorizationError(f"authorization gate is not PASS: {key}")
    model = _load_model(config.model_bundle_path, bundle)
    index = load_history_index_artifact(config.history_index_path, bundle)
    if check_source_identity:
        source = config.primary_opportunity
        if not source.is_file():
            raise AuthorizationError("telemetry source is unavailable")
        if file_source_identity(source) != authorization.telemetry_source_identity:
            raise AuthorizationError("telemetry source identity differs from authorization")
    return authorization, bundle, model, index


class SingleInstanceLock:
    """OS lock giữ suốt vòng đời collector; stale text không tự chặn restart."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._stream: Any | None = None
        self._locked = False

    def acquire(self, *, owner: Mapping[str, Any] | None = None) -> None:
        if self._locked:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            stream.seek(0)
            stream.write(b"\0")
            stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError) as exc:
            stream.close()
            raise CollectorAlreadyRunning(f"collector lock unavailable: {self.path}") from exc
        self._stream = stream
        self._locked = True
        metadata = dict(owner or {})
        metadata.setdefault("pid", os.getpid())
        metadata.setdefault("acquired_at_utc", utc_now())
        stream.seek(0)
        stream.truncate(0)
        stream.write((_json(metadata) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())

    def release(self) -> None:
        if not self._locked or self._stream is None:
            return
        stream = self._stream
        try:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()
            self._stream = None
            self._locked = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def _pid_alive(pid: Any) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _db_runtime_status(
    config: ForwardRuntimeConfig,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, int, dict[str, int]]:
    if not config.db.exists():
        return None, 0, {
            "raw_observation_count": 0,
            "canonical_opportunity_count": 0,
            "duplicate_collapse_count": 0,
            "scorable_count": 0,
            "no_opinion_count": 0,
        }
    connection = connect_database(config.db)
    try:
        integrity = integrity_status(connection)
        try:
            where = " WHERE run_id = ?" if run_id else ""
            params = (run_id,) if run_id else ()
            raw_count = int(connection.execute("SELECT COUNT(*) FROM phase3_opportunity_observations" + where, params).fetchone()[0])
            canonical = connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(duplicate_observation_count), 0),
                       COALESCE(SUM(CASE WHEN status = 'SCORABLE' THEN 1 ELSE 0 END), 0),
                       COALESCE(SUM(CASE WHEN status = 'NO_OPINION' THEN 1 ELSE 0 END), 0)
                FROM phase3_canonical_opportunities
                """ + where,
                params,
            ).fetchone()
            counters = {
                "raw_observation_count": raw_count,
                "canonical_opportunity_count": int(canonical[0]),
                "duplicate_collapse_count": int(canonical[1]),
                "scorable_count": int(canonical[2]),
                "no_opinion_count": int(canonical[3]),
            }
            return integrity, counters["scorable_count"] + counters["no_opinion_count"], counters
        except sqlite3.OperationalError:
            # Runtime DB cũ trước migration 009 chỉ còn diagnostic count.
            if run_id:
                count = int(connection.execute("SELECT COUNT(*) FROM phase3_predictions WHERE forward_run_id = ?", (run_id,)).fetchone()[0])
            else:
                count = int(connection.execute("SELECT COUNT(*) FROM phase3_predictions WHERE forward_valid = 1").fetchone()[0])
            return integrity, count, {
                "raw_observation_count": 0,
                "canonical_opportunity_count": 0,
                "duplicate_collapse_count": 0,
                "scorable_count": 0,
                "no_opinion_count": 0,
            }
    finally:
        connection.close()


def read_runtime_status(config: ForwardRuntimeConfig, *, run_id: str | None = None, now: str | None = None) -> dict[str, Any]:
    """Trả status machine-readable mà không giành collector lock."""

    heartbeat: dict[str, Any] = {}
    if config.heartbeat_path.is_file():
        try:
            value = _read_json(config.heartbeat_path)
            if isinstance(value, Mapping):
                heartbeat = dict(value)
        except (OSError, TypeError, ValueError):
            heartbeat = {}
    current = parse_utc_timestamp(now or utc_now())
    heartbeat_age: float | None = None
    if heartbeat.get("heartbeat_at_utc"):
        try:
            heartbeat_age = max(0.0, (current - parse_utc_timestamp(str(heartbeat["heartbeat_at_utc"]))).total_seconds())
        except ValueError:
            heartbeat_age = None
    heartbeat_run_id = str(heartbeat.get("run_id") or "") or None
    if heartbeat_run_id is None and config.current_run_path.is_file():
        try:
            current_run = _read_json(config.current_run_path)
            if isinstance(current_run, Mapping):
                heartbeat_run_id = str(current_run.get("run_id") or "") or None
        except (OSError, TypeError, ValueError):
            heartbeat_run_id = None
    selected_run_id = run_id or heartbeat_run_id
    fresh = heartbeat_age is not None and heartbeat_age <= config.heartbeat_stale_seconds
    process_alive = _pid_alive(heartbeat.get("pid"))
    collector_state = str(heartbeat.get("collector_status") or "").upper()
    collector_running = bool(fresh and process_alive and collector_state in {"RUNNING", "WAITING_FOR_SOURCE"})
    db_integrity, sample_count, coverage = _db_runtime_status(config, selected_run_id)
    telemetry_available = config.primary_opportunity.is_file()
    offset = heartbeat.get("current_source_offset")
    if offset is None and config.db.exists():
        connection = connect_database(config.db)
        try:
            row = connection.execute(
                "SELECT offset_bytes FROM phase3_ingest_offsets WHERE source_key = ?",
                (str(config.primary_opportunity.resolve()),),
            ).fetchone()
            if row:
                offset = int(row[0])
        finally:
            connection.close()
    return {
        "schema": HEARTBEAT_SCHEMA,
        "collector_running": collector_running,
        "persistent_runtime_status": "RUNNING" if collector_running else str(heartbeat.get("collector_status") or "STOPPED"),
        "pid": heartbeat.get("pid"),
        "process_alive": process_alive,
        "heartbeat_age": heartbeat_age,
        "heartbeat_fresh": fresh,
        "run_id": selected_run_id,
        "bundle_id": heartbeat.get("bundle_id"),
        "code_sha": heartbeat.get("git_sha"),
        "telemetry_source": str(config.primary_opportunity.resolve()),
        "telemetry_source_identity": heartbeat.get("source_identity"),
        "telemetry_available": telemetry_available,
        "telemetry_status": heartbeat.get("telemetry_status") or ("CONNECTED" if telemetry_available else "WAITING_FOR_SOURCE"),
        "source_offset": offset,
        "last_event": heartbeat.get("last_event"),
        "last_prediction": heartbeat.get("last_prediction"),
        "forward_sample_count": sample_count,
        "raw_observation_count": coverage["raw_observation_count"],
        "canonical_opportunity_count": coverage["canonical_opportunity_count"],
        "duplicate_collapse_count": coverage["duplicate_collapse_count"],
        "scorable_count": coverage["scorable_count"],
        "no_opinion_count": coverage["no_opinion_count"],
        "primary_source_schema": config.primary_opportunity_schema,
        "canonical_schema": config.canonical_schema,
        "canonicalizer_version": config.canonicalizer_version,
        "canonicalizer_fingerprint": config.canonicalizer_fingerprint,
        "db_integrity": db_integrity,
        "live_execution_enabled": False,
        "execution_mode": "NONE",
    }


class PersistentForwardCollector:
    """Vòng lặp tail/validate/score/persist một chiều, sống độc lập với MT5."""

    def __init__(
        self,
        config: ForwardRuntimeConfig,
        authorization: ForwardAuthorization,
        bundle: ShadowBundle,
        model: ModelBundle,
        similarity_index: HistoricalSimilarityIndex,
        *,
        run_id: str,
        clock: Callable[[], str] = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.authorization = authorization
        self.bundle = validate_bundle(bundle)
        self.model = model
        self.similarity_index = similarity_index
        self.run_id = str(run_id)
        self.clock = clock
        self.sleep = sleep
        self._runtime: Phase3Runtime | None = None
        self._lock = SingleInstanceLock(config.lock_path)
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def _open_runtime(self) -> Phase3Runtime:
        if self._runtime is None:
            self._runtime = Phase3Runtime.open(
                self.config.db,
                self.bundle,
                model_bundle=self.model,
                similarity_index=self.similarity_index,
                config=Phase3Config(
                    mode="FORWARD",
                    bundle_id=self.bundle.bundle_id,
                    telemetry_source=self.config.telemetry_source,
                    db_path=str(self.config.db),
                ),
                clock=self.clock,
            )
        return self._runtime

    def _close_runtime(self) -> None:
        if self._runtime is not None:
            self._runtime.close()
            self._runtime = None

    def _heartbeat(
        self,
        *,
        collector_status: str,
        telemetry_status: str,
        source_identity: str | None = None,
        initial_source_offset: int | None = None,
        current_source_offset: int | None = None,
        last_event: Mapping[str, Any] | None = None,
        last_prediction: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "schema": HEARTBEAT_SCHEMA,
            "heartbeat_at_utc": format_utc_timestamp(self.clock()),
            "pid": os.getpid(),
            "run_id": self.run_id,
            "bundle_id": self.bundle.bundle_id,
            "git_sha": self.authorization.authorized_git_sha,
            "source_path": str(self.config.primary_opportunity.resolve()),
            "source_identity": source_identity,
            "initial_source_offset": initial_source_offset,
            "current_source_offset": current_source_offset,
            "last_event": dict(last_event) if last_event else None,
            "last_prediction": dict(last_prediction) if last_prediction else None,
            "collector_status": collector_status,
            "telemetry_status": telemetry_status,
            "execution_mode": "NONE",
            "live_execution_enabled": False,
        }
        if error:
            payload["error"] = str(error)
        _atomic_json_write(self.config.heartbeat_path, payload)

    def _bind_source_boundary(self, runtime: Phase3Runtime) -> tuple[str, int] | None:
        source = self.config.primary_opportunity
        source_key = str(source.resolve())
        offset = runtime.connection.execute(
            "SELECT * FROM phase3_ingest_offsets WHERE source_key = ?", (source_key,)
        ).fetchone()
        if offset is not None:
            try:
                state = json.loads(str(offset["rotation_state_json"] or "{}"))
            except (TypeError, ValueError):
                state = {}
            bound_run_id = state.get("run_id") if isinstance(state, Mapping) else None
            if bound_run_id and str(bound_run_id) != self.run_id:
                previous_run = runtime.connection.execute(
                    "SELECT status FROM phase3_forward_runs WHERE run_id = ?", (str(bound_run_id),)
                ).fetchone()
                if previous_run is None or str(previous_run["status"]).upper() not in {"STOPPED", "FAILED"}:
                    raise ForwardControlError("telemetry source is already bound to another active FORWARD run")
                if not source.is_file():
                    return None
                identity = file_source_identity(source)
                size = source.stat().st_size
                new_state = {
                    "run_id": self.run_id,
                    "initial_source_size": size,
                    "initial_source_offset": size,
                    "activation_at_utc": format_utc_timestamp(self.clock()),
                    "rotated": False,
                    "truncated": False,
                }
                with runtime.connection:
                    runtime.connection.execute(
                        """
                        UPDATE phase3_ingest_offsets
                        SET source_identity = ?, source_path = ?, offset_bytes = ?,
                            last_consumed_event_id = NULL, rotation_state_json = ?, updated_at_utc = ?
                        WHERE source_key = ?
                        """,
                        (identity, source_key, size, _json(new_state), self.clock(), source_key),
                    )
                return identity, size
            if not bound_run_id:
                raise ForwardControlError("telemetry source has an offset without an authorized run boundary")
            if not source.is_file():
                return None
            initial = state.get("initial_source_offset")
            return str(offset["source_identity"]), int(initial if initial is not None else offset["offset_bytes"])
        if not source.is_file():
            return None
        identity = file_source_identity(source)
        size = source.stat().st_size
        state = {
            "run_id": self.run_id,
            "initial_source_size": size,
            "initial_source_offset": size,
            "activation_at_utc": format_utc_timestamp(self.clock()),
            "rotated": False,
            "truncated": False,
        }
        with runtime.connection:
            runtime.connection.execute(
                """
                INSERT INTO phase3_ingest_offsets(
                    source_key, source_identity, source_path, offset_bytes,
                    last_consumed_event_id, rotation_state_json, updated_at_utc
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                (source_key, identity, source_key, size, _json(state), self.clock()),
            )
        return identity, size

    def _cycle(self) -> dict[str, Any]:
        runtime = self._open_runtime()
        boundary = self._bind_source_boundary(runtime)
        if boundary is None:
            self._heartbeat(collector_status="WAITING_FOR_SOURCE", telemetry_status="WAITING_FOR_SOURCE")
            return {"status": "WAITING_FOR_SOURCE", "records_seen": 0}
        identity, initial_offset = boundary
        result = runtime.ingest_file_once(
            self.run_id,
            self.config.primary_opportunity,
            source=self.config.telemetry_source,
            file_format=self.config.telemetry_format,
            expected_schema=self.config.primary_opportunity_schema,
        )
        if result.get("truncated"):
            runtime.set_run_status(self.run_id, "FAILED")
            self._heartbeat(
                collector_status="FAILED",
                telemetry_status="TRUNCATED",
                source_identity=str(result.get("source_identity") or identity),
                initial_source_offset=initial_offset,
                current_source_offset=int(result.get("offset_bytes") or 0),
                error="SOURCE_TRUNCATED",
            )
            return result
        last_event_row = runtime.connection.execute(
            "SELECT source_event_id, event_timestamp_utc FROM phase3_forward_events WHERE run_id = ? ORDER BY event_timestamp_utc DESC, forward_event_id DESC LIMIT 1",
            (self.run_id,),
        ).fetchone()
        last_prediction_row = runtime.connection.execute(
            "SELECT prediction_id, source_event_timestamp_utc, prediction_committed_at_utc FROM phase3_predictions WHERE forward_run_id = ? ORDER BY created_at_utc DESC, prediction_id DESC LIMIT 1",
            (self.run_id,),
        ).fetchone()
        self._heartbeat(
            collector_status="RUNNING",
            telemetry_status="CONNECTED",
            source_identity=str(result.get("source_identity") or identity),
            initial_source_offset=initial_offset,
            current_source_offset=int(result.get("offset_bytes") or 0),
            last_event=dict(last_event_row) if last_event_row else None,
            last_prediction=dict(last_prediction_row) if last_prediction_row else None,
        )
        return result

    def run_once(self) -> dict[str, Any]:
        """Chạy một poll không giành lock, phục vụ smoke/restart test deterministic."""

        return self._cycle()

    def run_forever(self, *, max_iterations: int | None = None) -> dict[str, Any]:
        """Giữ lock và poll tới khi có stop marker, signal stop hoặc lỗi fail-closed."""

        runtime = self._open_runtime()
        self._lock.acquire(owner={"run_id": self.run_id, "bundle_id": self.bundle.bundle_id})
        iterations = 0
        final: dict[str, Any] = {"status": "RUNNING", "run_id": self.run_id}
        try:
            row = runtime._run(self.run_id)
            if str(row["mode"]) != "FORWARD":
                raise ForwardControlError("persistent collector requires a FORWARD run")
            if str(row["git_sha"]) != self.authorization.authorized_git_sha:
                raise AuthorizationError("FORWARD run is bound to another git SHA")
            if str(row["status"]) == "STOPPED":
                raise ForwardControlError("stopped FORWARD run cannot be resumed")
            if str(row["status"]) == "FAILED":
                raise ForwardControlError("failed FORWARD run cannot be resumed")
            runtime.set_run_status(self.run_id, "RUNNING")
            self.config.stop_path.unlink(missing_ok=True)
            while not self._stop_requested:
                if self.config.stop_path.is_file():
                    try:
                        marker = _read_json(self.config.stop_path)
                    except (OSError, TypeError, ValueError):
                        marker = {}
                    if not isinstance(marker, Mapping) or not marker.get("run_id") or str(marker.get("run_id")) == self.run_id:
                        break
                final = self._cycle()
                iterations += 1
                if final.get("truncated") or final.get("status") == "SOURCE_TRUNCATED":
                    return {**final, "iterations": iterations, "collector_status": "FAILED"}
                if max_iterations is not None and iterations >= max_iterations:
                    runtime.set_run_status(self.run_id, "PAUSED")
                    self._heartbeat(
                        collector_status="PAUSED",
                        telemetry_status=str(final.get("status") or "CONNECTED"),
                        current_source_offset=final.get("offset_bytes"),
                    )
                    return {**final, "iterations": iterations, "collector_status": "PAUSED"}
                self.sleep(self.config.poll_interval_seconds)
            runtime.set_run_status(self.run_id, "STOPPED")
            final = {**final, "status": "STOPPED", "collector_status": "STOPPED", "iterations": iterations}
            self._heartbeat(collector_status="STOPPED", telemetry_status="STOPPED")
            return final
        except Exception as exc:
            try:
                runtime.set_run_status(self.run_id, "FAILED")
            except Exception:
                pass
            try:
                self._heartbeat(collector_status="FAILED", telemetry_status="ERROR", error=str(exc))
            except Exception:
                pass
            raise
        finally:
            self._lock.release()
            self._close_runtime()


def create_forward_run(
    config: ForwardRuntimeConfig,
    authorization: ForwardAuthorization,
    bundle: ShadowBundle,
    *,
    run_id: str,
    now: str | None = None,
) -> dict[str, Any]:
    """Tạo run mới gắn với auth SHA và không trộn smoke/replay run."""

    runtime = Phase3Runtime.open(
        config.db,
        bundle,
        config=Phase3Config(mode="FORWARD", bundle_id=bundle.bundle_id, telemetry_source=config.telemetry_source, db_path=str(config.db)),
        clock=utc_now,
    )
    try:
        run = runtime.create_run(
            run_id,
            mode="FORWARD",
            source=config.telemetry_source,
            git_sha=authorization.authorized_git_sha,
        )
        if str(run.get("git_sha")) != authorization.authorized_git_sha:
            raise AuthorizationError("existing FORWARD run is bound to another git SHA")
        _atomic_json_write(
            config.current_run_path,
            {
                "schema": "phase3-forward-current-run/1",
                "run_id": str(run_id),
                "authorization_id": authorization.authorization_id,
                "bundle_id": bundle.bundle_id,
                "created_at_utc": format_utc_timestamp(now or utc_now()),
            },
        )
        return run
    finally:
        runtime.close()


def request_stop_forward(config: ForwardRuntimeConfig, *, run_id: str) -> dict[str, Any]:
    """Ghi stop marker cho collector; không đụng MT5 hay strategy process."""

    payload = {"schema": "phase3-forward-stop/1", "run_id": str(run_id), "requested_at_utc": utc_now()}
    _atomic_json_write(config.stop_path, payload)
    return {"status": "STOP_REQUESTED", "run_id": str(run_id), "path": str(config.stop_path)}


def load_forward_assets(config: ForwardRuntimeConfig) -> tuple[ForwardAuthorization, ShadowBundle, ModelBundle, HistoricalSimilarityIndex]:
    """Nạp trọn bộ asset sau khi auth đã pass; không rebuild hay mutate asset."""

    authorization, bundle, model, index = validate_forward_authorization(
        config.authorization_path,
        config,
        check_source_identity=False,
    )
    return authorization, bundle, model, index


__all__ = [
    "AUTHORIZATION_SCHEMA",
    "DEFAULT_TASK_NAME",
    "ForwardAuthorization",
    "ForwardControlError",
    "ForwardRuntimeConfig",
    "AuthorizationError",
    "CollectorAlreadyRunning",
    "HEARTBEAT_SCHEMA",
    "HISTORY_INDEX_SCHEMA",
    "PersistentForwardCollector",
    "RUNTIME_CONFIG_SCHEMA",
    "SingleInstanceLock",
    "build_historical_index_artifact",
    "create_forward_run",
    "current_git_sha",
    "execution_api_path_count",
    "load_forward_assets",
    "load_forward_config",
    "load_history_index_artifact",
    "prepare_forward_authorization",
    "read_runtime_status",
    "request_stop_forward",
    "tracked_worktree_clean",
    "validate_forward_authorization",
    "write_forward_config",
]
