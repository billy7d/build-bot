"""Fail-closed, telemetry-only recovery watchdog for isolated MT5 instances.

The watchdog deliberately knows nothing about trading APIs.  It discovers an
exact terminal process, validates immutable artifacts and an operator-provided
trading-disabled attestation, then (only for an absent terminal) can start the
exact executable with pre-approved arguments.  Runtime state and incidents are
append/audit evidence outside the checkout; no telemetry source is truncated,
rewound, repaired or replaced.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .models import format_utc_timestamp, parse_utc_timestamp
from .node_ops import (
    atomic_write_json,
    append_operator_log,
    record_incident,
    sha256_file,
)
from .ingestion.file_tail import file_source_identity


WATCHDOG_SCHEMA = "phase3-mt5-watchdog/1"
DEFAULT_TELEMETRY_SCHEMA = "phase3-opportunity-observation/1"
DEFAULT_WARNING_SECONDS = 120
DEFAULT_CRITICAL_SECONDS = 180
DEFAULT_MAX_RESTARTS = 2
DEFAULT_RESTART_WINDOW_SECONDS = 30 * 60


class WatchdogSafetyError(RuntimeError):
    """A safety gate could not be proven; no process action is permitted."""


def _path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _now_dt(value: str | datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return parse_utc_timestamp(value)


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "enabled", "1"}:
            return True
        if normalized in {"false", "no", "off", "disabled", "0"}:
            return False
    return None


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(str(_path(left))) == os.path.normcase(str(_path(right)))


def _redact_command(command: Sequence[str]) -> list[str]:
    """Keep evidence useful without ever persisting credential-like values."""

    redacted: list[str] = []
    sensitive = {"/login", "/password", "/server", "--login", "--password", "--server"}
    for item in command:
        token = str(item)
        key = token.split("=", 1)[0].lower()
        redacted.append("<REDACTED>" if key in sensitive or key.lstrip("/") in {"login", "password", "server"} else token)
    return redacted


@dataclass(frozen=True)
class MT5InstanceSpec:
    """Identity contract for one terminal; paths are never inferred at launch."""

    name: str
    terminal_exe: Path
    install_directory: Path
    data_directory: Path
    profile: str
    ea_name: str
    ea_ex5_path: Path
    preset_path: Path
    account_identity: str
    server_identity: str
    telemetry_path: Path
    telemetry_schema: str = DEFAULT_TELEMETRY_SCHEMA
    approved_ex5_sha256: str | None = None
    approved_preset_sha256: str | None = None
    trading_permission_evidence_path: Path | None = None
    ea_status_evidence_path: Path | None = None
    launch_args: tuple[str, ...] = ()
    allow_portable: bool = False
    chart_symbol: str | None = None
    timeframe: str | None = None
    telemetry_heartbeat_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("instance name is required")
        if not self.account_identity.strip() or not self.server_identity.strip():
            raise ValueError("account_identity and server_identity are required")
        if any("\n" in str(item) or "\r" in str(item) for item in self.launch_args):
            raise ValueError("launch_args may not contain newlines")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MT5InstanceSpec":
        required = {
            "name", "terminal_exe", "install_directory", "data_directory", "profile",
            "ea_name", "ea_ex5_path", "preset_path", "account_identity", "server_identity",
            "telemetry_path",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"instance config missing required fields: {', '.join(missing)}")
        raw_args = payload.get("launch_args", ())
        if not isinstance(raw_args, (list, tuple)) or not all(isinstance(item, str) for item in raw_args):
            raise ValueError("launch_args must be a list of strings")
        return cls(
            name=str(payload["name"]),
            terminal_exe=_path(payload["terminal_exe"]),
            install_directory=_path(payload["install_directory"]),
            data_directory=_path(payload["data_directory"]),
            profile=str(payload["profile"]),
            ea_name=str(payload["ea_name"]),
            ea_ex5_path=_path(payload["ea_ex5_path"]),
            preset_path=_path(payload["preset_path"]),
            account_identity=str(payload["account_identity"]),
            server_identity=str(payload["server_identity"]),
            telemetry_path=_path(payload["telemetry_path"]),
            telemetry_schema=str(payload.get("telemetry_schema", DEFAULT_TELEMETRY_SCHEMA)),
            approved_ex5_sha256=(str(payload["approved_ex5_sha256"]).lower() if payload.get("approved_ex5_sha256") else None),
            approved_preset_sha256=(str(payload["approved_preset_sha256"]).lower() if payload.get("approved_preset_sha256") else None),
            trading_permission_evidence_path=_path(payload["trading_permission_evidence_path"]) if payload.get("trading_permission_evidence_path") else None,
            ea_status_evidence_path=_path(payload["ea_status_evidence_path"]) if payload.get("ea_status_evidence_path") else None,
            launch_args=tuple(raw_args),
            allow_portable=bool(payload.get("allow_portable", False)),
            chart_symbol=str(payload["chart_symbol"]) if payload.get("chart_symbol") else None,
            timeframe=str(payload["timeframe"]) if payload.get("timeframe") else None,
            telemetry_heartbeat_path=_path(payload["telemetry_heartbeat_path"]) if payload.get("telemetry_heartbeat_path") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "terminal_exe": str(self.terminal_exe),
            "install_directory": str(self.install_directory),
            "data_directory": str(self.data_directory),
            "profile": self.profile,
            "ea_name": self.ea_name,
            "ea_ex5_path": str(self.ea_ex5_path),
            "preset_path": str(self.preset_path),
            "account_identity": self.account_identity,
            "server_identity": self.server_identity,
            "telemetry_path": str(self.telemetry_path),
            "telemetry_schema": self.telemetry_schema,
            "approved_ex5_sha256": self.approved_ex5_sha256,
            "approved_preset_sha256": self.approved_preset_sha256,
            "trading_permission_evidence_path": str(self.trading_permission_evidence_path) if self.trading_permission_evidence_path else None,
            "ea_status_evidence_path": str(self.ea_status_evidence_path) if self.ea_status_evidence_path else None,
            "launch_args": list(_redact_command(self.launch_args)),
            "allow_portable": self.allow_portable,
            "chart_symbol": self.chart_symbol,
            "timeframe": self.timeframe,
            "telemetry_heartbeat_path": str(self.telemetry_heartbeat_path) if self.telemetry_heartbeat_path else None,
        }


@dataclass(frozen=True)
class WatchdogConfig:
    instances: tuple[MT5InstanceSpec, ...]
    ops_root: Path
    warning_seconds: int = DEFAULT_WARNING_SECONDS
    critical_seconds: int = DEFAULT_CRITICAL_SECONDS
    max_restarts: int = DEFAULT_MAX_RESTARTS
    restart_window_seconds: int = DEFAULT_RESTART_WINDOW_SECONDS
    safety_contract: Mapping[str, Any] = field(default_factory=lambda: {
        "live_execution_enabled": False,
        "execution_authority": "NONE",
        "trade_control_authority": "NONE",
        "forward_authorization": "NOT_CREATED",
        "forward_run_id": "NOT_CREATED",
        "auto_trading": False,
    })

    def __post_init__(self) -> None:
        if not self.instances:
            raise ValueError("at least one MT5 instance is required")
        if self.warning_seconds < 1 or self.critical_seconds < self.warning_seconds:
            raise ValueError("invalid telemetry thresholds")
        if self.max_restarts < 0 or self.restart_window_seconds < 1:
            raise ValueError("invalid restart policy")
        expected = {
            "live_execution_enabled": False,
            "execution_authority": "NONE",
            "trade_control_authority": "NONE",
            "forward_authorization": "NOT_CREATED",
            "forward_run_id": "NOT_CREATED",
            "auto_trading": False,
        }
        for key, value in expected.items():
            actual = self.safety_contract.get(key)
            if key in {"live_execution_enabled", "auto_trading"}:
                if _as_bool(actual) is not False:
                    raise ValueError(f"safety contract {key} must be false")
            elif str(actual).upper() != value:
                raise ValueError(f"safety contract {key} must be {value}")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WatchdogConfig":
        raw_instances = payload.get("instances")
        if not isinstance(raw_instances, list):
            raise ValueError("watchdog config instances must be a list")
        instances = tuple(MT5InstanceSpec.from_dict(item) for item in raw_instances if isinstance(item, Mapping))
        if len(instances) != len(raw_instances):
            raise ValueError("each watchdog instance must be an object")
        safety = payload.get("safety_contract")
        if safety is None:
            safety = {
                "live_execution_enabled": False,
                "execution_authority": "NONE",
                "trade_control_authority": "NONE",
                "forward_authorization": "NOT_CREATED",
                "forward_run_id": "NOT_CREATED",
                "auto_trading": False,
            }
        if not isinstance(safety, Mapping):
            raise ValueError("safety_contract must be an object")
        return cls(
            instances=instances,
            ops_root=_path(payload.get("ops_root", "watchdog-ops")),
            warning_seconds=int(payload.get("warning_seconds", DEFAULT_WARNING_SECONDS)),
            critical_seconds=int(payload.get("critical_seconds", DEFAULT_CRITICAL_SECONDS)),
            max_restarts=int(payload.get("max_restarts", DEFAULT_MAX_RESTARTS)),
            restart_window_seconds=int(payload.get("restart_window_seconds", DEFAULT_RESTART_WINDOW_SECONDS)),
            safety_contract=dict(safety),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": WATCHDOG_SCHEMA,
            "instances": [item.to_dict() for item in self.instances],
            "ops_root": str(self.ops_root),
            "warning_seconds": self.warning_seconds,
            "critical_seconds": self.critical_seconds,
            "max_restarts": self.max_restarts,
            "restart_window_seconds": self.restart_window_seconds,
            "safety_contract": dict(self.safety_contract),
        }


def load_watchdog_config(path: str | Path) -> WatchdogConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("watchdog config must be a JSON object")
    return WatchdogConfig.from_dict(payload)


def _query_processes() -> tuple[list[dict[str, Any]], str | None]:
    """Query process identity without killing or modifying any process."""

    if os.name != "nt":
        return [], "WINDOWS_REQUIRED"
    script = (
        "$ErrorActionPreference='Stop'; "
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,ExecutablePath,CommandLine | "
        "ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        if not completed.stdout.strip():
            return [], None
        value = json.loads(completed.stdout)
        rows = value if isinstance(value, list) else [value]
        return [dict(row) for row in rows if isinstance(row, Mapping)], None
    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
        return [], f"PROCESS_QUERY_FAILED:{type(exc).__name__}"


def _read_json_object(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "NOT_CONFIGURED"
    if not path.is_file():
        return None, "MISSING"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None, "INVALID_JSON"
    return (dict(value), None) if isinstance(value, Mapping) else (None, "NOT_OBJECT")


def _permission_gate(spec: MT5InstanceSpec) -> dict[str, Any]:
    payload, error = _read_json_object(spec.trading_permission_evidence_path)
    required = (
        "auto_trading", "terminal_trade_allowed", "mql_trade_allowed",
        "live_execution_enabled", "execution_authority", "trade_control_authority",
    )
    reasons: list[str] = []
    if error:
        reasons.append(f"TRADING_PERMISSION_{error}")
    if payload is not None:
        for key in required:
            if key not in payload:
                reasons.append(f"TRADING_PERMISSION_MISSING:{key}")
        for key in ("auto_trading", "terminal_trade_allowed", "mql_trade_allowed", "live_execution_enabled"):
            if key in payload and _as_bool(payload[key]) is not False:
                reasons.append(f"TRADING_PERMISSION_NOT_DISABLED:{key}")
        for key in ("execution_authority", "trade_control_authority"):
            if key in payload and str(payload[key]).upper() != "NONE":
                reasons.append(f"TRADING_AUTHORITY_NOT_NONE:{key}")
    return {"status": "PASS" if not reasons else "BLOCKED", "reasons": reasons, "evidence_path": str(spec.trading_permission_evidence_path) if spec.trading_permission_evidence_path else None}


def _ea_gate(spec: MT5InstanceSpec) -> dict[str, Any]:
    payload, error = _read_json_object(spec.ea_status_evidence_path)
    reasons: list[str] = []
    if error:
        reasons.append(f"EA_STATUS_EVIDENCE_{error}")
    if payload is not None:
        if _as_bool(payload.get("attached")) is not True:
            reasons.append("EA_NOT_CONFIRMED_ATTACHED")
        if str(payload.get("ea_name", "")) != spec.ea_name:
            reasons.append("EA_NAME_MISMATCH")
        account = payload.get("account_identity", payload.get("account"))
        if str(account or "") != spec.account_identity:
            reasons.append("EA_ACCOUNT_MISMATCH")
        server = payload.get("server_identity", payload.get("server"))
        if str(server or "") != spec.server_identity:
            reasons.append("EA_SERVER_MISMATCH")
        if spec.chart_symbol and str(payload.get("symbol", "")) != spec.chart_symbol:
            reasons.append("EA_SYMBOL_MISMATCH")
        if spec.timeframe and str(payload.get("timeframe", "")) != spec.timeframe:
            reasons.append("EA_TIMEFRAME_MISMATCH")
        if str(payload.get("on_init", "")).upper() not in {"PASS", "SUCCESS", "INIT_SUCCEEDED"}:
            reasons.append("EA_ONINIT_NOT_CONFIRMED")
    return {"status": "PASS" if not reasons else "BLOCKED", "reasons": reasons, "evidence_path": str(spec.ea_status_evidence_path) if spec.ea_status_evidence_path else None}


def _artifact_gate(spec: MT5InstanceSpec) -> dict[str, Any]:
    reasons: list[str] = []
    result: dict[str, Any] = {
        "terminal_exists": spec.terminal_exe.is_file(),
        "install_directory_exists": spec.install_directory.is_dir(),
        "data_directory_exists": spec.data_directory.is_dir(),
        "ea_exists": spec.ea_ex5_path.is_file(),
        "preset_exists": spec.preset_path.is_file(),
        "ea_sha256": sha256_file(spec.ea_ex5_path) if spec.ea_ex5_path.is_file() else None,
        "preset_sha256": sha256_file(spec.preset_path) if spec.preset_path.is_file() else None,
    }
    if not result["terminal_exists"]:
        reasons.append("TERMINAL_EXECUTABLE_MISSING")
    if not result["install_directory_exists"] or not _same_path(spec.terminal_exe.parent, spec.install_directory):
        reasons.append("INSTALL_DIRECTORY_MISMATCH")
    if not result["data_directory_exists"]:
        reasons.append("DATA_DIRECTORY_MISSING")
    if not spec.approved_ex5_sha256:
        reasons.append("APPROVED_EX5_SHA256_REQUIRED")
    elif result["ea_sha256"] != spec.approved_ex5_sha256:
        reasons.append("EA_SHA256_MISMATCH")
    if not result["ea_exists"]:
        reasons.append("APPROVED_EX5_MISSING")
    if not spec.approved_preset_sha256:
        reasons.append("APPROVED_PRESET_SHA256_REQUIRED")
    elif result["preset_sha256"] != spec.approved_preset_sha256:
        reasons.append("PRESET_SHA256_MISMATCH")
    if not result["preset_exists"]:
        reasons.append("APPROVED_PRESET_MISSING")
    result.update({"status": "PASS" if not reasons else "BLOCKED", "reasons": reasons})
    return result


def _process_fields(row: Mapping[str, Any]) -> tuple[int | None, str, str]:
    pid = row.get("ProcessId", row.get("process_id", row.get("pid")))
    try:
        pid = int(pid) if pid is not None else None
    except (ValueError, TypeError):
        pid = None
    executable = str(row.get("ExecutablePath", row.get("executable_path", row.get("executable", ""))) or "")
    command = str(row.get("CommandLine", row.get("command_line", row.get("cmdline", ""))) or "")
    return pid, executable, command


def _process_gate(spec: MT5InstanceSpec, rows: Iterable[Mapping[str, Any]], query_error: str | None) -> dict[str, Any]:
    if query_error:
        return {"status": "BLOCKED", "process_status": "UNKNOWN", "matches": [], "reasons": [query_error]}
    matches: list[dict[str, Any]] = []
    for row in rows:
        pid, executable, command = _process_fields(row)
        if not executable or not _same_path(executable, spec.terminal_exe):
            continue
        command_lower = command.lower()
        data_ok = _same_path(spec.data_directory, spec.terminal_exe.parent) or str(spec.data_directory).lower() in command_lower
        profile_ok = not spec.profile or spec.profile.lower() in command_lower
        matches.append({"pid": pid, "executable_path": executable, "command_line_present": bool(command), "data_directory_verified": data_ok, "profile_verified": profile_ok})
    reasons: list[str] = []
    if len(matches) > 1:
        reasons.append("DUPLICATE_EXACT_TERMINAL_INSTANCE")
    if matches and any(not item["data_directory_verified"] for item in matches):
        reasons.append("PROCESS_DATA_DIRECTORY_UNVERIFIED")
    if matches and any(not item["profile_verified"] for item in matches):
        reasons.append("PROCESS_PROFILE_UNVERIFIED")
    status = "RUNNING" if matches else "ABSENT"
    if reasons:
        status = "BLOCKED"
    return {"status": "PASS" if not reasons else "BLOCKED", "process_status": status, "matches": matches, "reasons": reasons}


def _extract_timestamp(record: Mapping[str, Any]) -> datetime | None:
    for key in ("event_timestamp_utc", "timestamp_utc", "observed_at_utc", "created_at_utc", "heartbeat_at_utc", "event_timestamp"):
        value = record.get(key)
        if value is None:
            continue
        try:
            return parse_utc_timestamp(str(value))
        except (TypeError, ValueError):
            return None
    return None


def _telemetry_check(spec: MT5InstanceSpec, now: datetime, warning: int, critical: int) -> dict[str, Any]:
    path = spec.telemetry_path
    result: dict[str, Any] = {"path": str(path), "exists": path.is_file(), "schema": spec.telemetry_schema, "records": 0, "valid_records": 0, "invalid_records": 0, "last_timestamp_utc": None, "age_seconds": None, "sequence_status": "UNVERIFIED", "source_identity": None, "size_bytes": None, "last_write_time_utc": None}
    if not path.is_file():
        result.update({"status": "MISSING", "reasons": ["TELEMETRY_FILE_MISSING"]})
        return result
    try:
        stat = path.stat()
        result["size_bytes"] = stat.st_size
        result["last_write_time_utc"] = format_utc_timestamp(datetime.fromtimestamp(stat.st_mtime, UTC))
        result["source_identity"] = file_source_identity(path)
        sequence_values: list[int] = []
        last_timestamp: datetime | None = None
        reasons: list[str] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                result["records"] += 1
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    result["invalid_records"] += 1
                    reasons.append(f"INVALID_JSONL_LINE:{line_no}")
                    continue
                if not isinstance(value, Mapping) or value.get("schema_version") != spec.telemetry_schema:
                    result["invalid_records"] += 1
                    reasons.append(f"SCHEMA_MISMATCH_LINE:{line_no}")
                    continue
                result["valid_records"] += 1
                timestamp = _extract_timestamp(value)
                if timestamp is not None:
                    last_timestamp = timestamp
                for key in ("sequence", "seq", "record_sequence", "sequence_number"):
                    if key in value:
                        try:
                            sequence_values.append(int(value[key]))
                        except (ValueError, TypeError):
                            reasons.append(f"SEQUENCE_INVALID_LINE:{line_no}")
                        break
        if sequence_values:
            result["sequence_status"] = "CONTINUOUS" if all(right == left + 1 for left, right in zip(sequence_values, sequence_values[1:])) else "GAP"
            if result["sequence_status"] == "GAP":
                reasons.append("TELEMETRY_SEQUENCE_GAP")
        if last_timestamp is not None:
            result["last_timestamp_utc"] = format_utc_timestamp(last_timestamp)
            age = max(0.0, (now - last_timestamp).total_seconds())
            result["age_seconds"] = round(age, 3)
            if age > critical:
                result["status"] = "TELEMETRY_STALE"
                reasons.append("TELEMETRY_STALE")
            elif age > warning:
                result["status"] = "WARNING"
                reasons.append("TELEMETRY_WARNING")
            else:
                result["status"] = "FRESH"
        elif result["valid_records"]:
            result["status"] = "TIMESTAMP_UNVERIFIED"
            reasons.append("TELEMETRY_TIMESTAMP_UNVERIFIED")
        else:
            result["status"] = "INVALID" if result["invalid_records"] else "EMPTY"
            reasons.append("TELEMETRY_NO_VALID_RECORD")
        if result["invalid_records"]:
            reasons.append("TELEMETRY_SCHEMA_OR_JSON_INVALID")
        result["reasons"] = sorted(set(reasons))
        return result
    except (OSError, UnicodeError) as exc:
        result.update({"status": "READ_ERROR", "reasons": [f"TELEMETRY_READ_ERROR:{type(exc).__name__}"]})
        return result


def _load_state(ops_root: Path) -> dict[str, Any]:
    path = ops_root / "watchdog" / "state.json"
    if not path.exists():
        return {"schema": WATCHDOG_SCHEMA, "instances": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise WatchdogSafetyError(f"WATCHDOG_STATE_INVALID:{type(exc).__name__}") from exc
    if not isinstance(value, Mapping) or value.get("schema") != WATCHDOG_SCHEMA or not isinstance(value.get("instances", {}), Mapping):
        raise WatchdogSafetyError("WATCHDOG_STATE_INVALID_SCHEMA")
    return dict(value)


def _save_state(ops_root: Path, state: Mapping[str, Any]) -> None:
    atomic_write_json(ops_root / "watchdog" / "state.json", dict(state))


def _record_incident_safe(ops_root: Path, code: str, details: Mapping[str, Any]) -> None:
    record_incident(ops_root, severity="CRITICAL", code=code, details=details)


def inspect_instance(
    spec: MT5InstanceSpec,
    *,
    now: str | datetime | None = None,
    process_records: Iterable[Mapping[str, Any]] | None = None,
    process_query_error: str | None = None,
    warning_seconds: int = DEFAULT_WARNING_SECONDS,
    critical_seconds: int = DEFAULT_CRITICAL_SECONDS,
) -> dict[str, Any]:
    """Return a read-only snapshot; no process or telemetry state is changed."""

    rows = list(process_records) if process_records is not None else []
    query_error = process_query_error
    if process_records is None and process_query_error is None:
        rows, query_error = _query_processes()
    artifacts = _artifact_gate(spec)
    permissions = _permission_gate(spec)
    ea = _ea_gate(spec)
    process = _process_gate(spec, rows, query_error)
    telemetry = _telemetry_check(spec, _now_dt(now), warning_seconds, critical_seconds)
    gate_reasons = list(artifacts["reasons"]) + list(permissions["reasons"]) + list(ea["reasons"]) + list(process["reasons"])
    # Corruption, identity/sequence drift and read failure are hard stops; staleness
    # alone is a health signal and never licenses a second terminal.
    telemetry_hard = {"TELEMETRY_SCHEMA_OR_JSON_INVALID", "TELEMETRY_SEQUENCE_GAP", "TELEMETRY_READ_ERROR:OSError", "TELEMETRY_READ_ERROR:UnicodeError"}
    if any(reason in telemetry_hard or reason.startswith("INVALID_JSONL_LINE") or reason.startswith("SCHEMA_MISMATCH_LINE") or reason.startswith("SEQUENCE_") for reason in telemetry["reasons"]):
        gate_reasons.extend(telemetry["reasons"])
    return {
        "schema": WATCHDOG_SCHEMA,
        "instance": spec.name,
        "checked_at_utc": format_utc_timestamp(_now_dt(now)),
        "identity": {"terminal_exe": str(spec.terminal_exe), "install_directory": str(spec.install_directory), "data_directory": str(spec.data_directory), "profile": spec.profile, "ea_name": spec.ea_name, "account_identity": spec.account_identity, "server_identity": spec.server_identity, "telemetry_path": str(spec.telemetry_path)},
        "artifacts": artifacts,
        "trading_permission": permissions,
        "ea": ea,
        "process": process,
        "telemetry": telemetry,
        "gate_status": "PASS" if not gate_reasons else "BLOCKED",
        "gate_reasons": sorted(set(gate_reasons)),
        "health_status": _health_status(process, telemetry, gate_reasons),
        "recovery_candidate": not gate_reasons and process["process_status"] == "ABSENT",
        "trading_action": "NONE",
    }


def _health_status(process: Mapping[str, Any], telemetry: Mapping[str, Any], gate_reasons: Sequence[str]) -> str:
    if gate_reasons:
        return "CRITICAL"
    if process.get("process_status") == "ABSENT":
        return "CRITICAL"
    if telemetry.get("status") in {"TELEMETRY_STALE", "MISSING", "INVALID", "READ_ERROR", "TIMESTAMP_UNVERIFIED", "EMPTY"}:
        return "WARNING" if telemetry.get("status") == "MISSING" else "CRITICAL"
    if telemetry.get("status") == "WARNING":
        return "WARNING"
    return "HEALTHY"


def watchdog_status(config: WatchdogConfig, *, now: str | datetime | None = None, process_provider: Callable[[], tuple[list[dict[str, Any]], str | None]] | None = None) -> dict[str, Any]:
    rows, error = process_provider() if process_provider else _query_processes()
    instances = [inspect_instance(item, now=now, process_records=rows, process_query_error=error, warning_seconds=config.warning_seconds, critical_seconds=config.critical_seconds) for item in config.instances]
    return {"schema": WATCHDOG_SCHEMA, "checked_at_utc": format_utc_timestamp(_now_dt(now)), "status": "PASS" if all(item["health_status"] == "HEALTHY" for item in instances) else "BLOCKED", "instances": instances, "safety_contract": dict(config.safety_contract), "watchdog_install_status": "NOT_INSTALLED_OR_DISABLED"}


def _prelaunch_snapshot(spec: MT5InstanceSpec, ops_root: Path, inspection: Mapping[str, Any]) -> Path:
    stamp = _now_dt().strftime("%Y%m%dT%H%M%SZ")
    target = ops_root / "watchdog" / "recovery-snapshots" / f"{spec.name}-{stamp}.json"
    payload = {"schema": "phase3-mt5-recovery-snapshot/1", "captured_at_utc": format_utc_timestamp(_now_dt()), "instance": spec.name, "inspection": dict(inspection), "action": "METADATA_ONLY_NO_TELEMETRY_MUTATION"}
    atomic_write_json(target, payload)
    return target


def recover_once(
    config: WatchdogConfig,
    *,
    instance_name: str | None = None,
    dry_run: bool = False,
    now: str | datetime | None = None,
    process_provider: Callable[[], tuple[list[dict[str, Any]], str | None]] | None = None,
    popen: Callable[..., Any] = subprocess.Popen,
) -> dict[str, Any]:
    """Recover at most one absent terminal; running/EA-stopped instances are untouched."""

    selected = [item for item in config.instances if instance_name is None or item.name == instance_name]
    if not selected:
        raise ValueError(f"unknown MT5 instance: {instance_name}")
    rows, error = process_provider() if process_provider else _query_processes()
    try:
        state = _load_state(config.ops_root)
    except WatchdogSafetyError as exc:
        _record_incident_safe(config.ops_root, "WATCHDOG_STATE_INVALID", {"error": str(exc)})
        return {
            "schema": WATCHDOG_SCHEMA,
            "checked_at_utc": format_utc_timestamp(_now_dt(now)),
            "status": "BLOCKED",
            "dry_run": dry_run,
            "instances": [{"instance": item.name, "status": "UNSAFE_TO_RESTART", "action": "NONE", "reason": str(exc)} for item in selected],
            "trading_action": "NONE",
            "forward_authorization": "NOT_CREATED",
            "forward_run_id": "NOT_CREATED",
        }
    results: list[dict[str, Any]] = []
    for spec in selected:
        inspection = inspect_instance(spec, now=now, process_records=rows, process_query_error=error, warning_seconds=config.warning_seconds, critical_seconds=config.critical_seconds)
        if inspection["gate_status"] != "PASS":
            result = {"instance": spec.name, "status": "UNSAFE_TO_RESTART", "inspection": inspection, "action": "NONE"}
            _record_incident_safe(config.ops_root, "UNSAFE_TO_RESTART", {"instance": spec.name, "reasons": inspection["gate_reasons"]})
            results.append(result)
            continue
        if inspection["process"]["process_status"] == "RUNNING":
            results.append({"instance": spec.name, "status": "NO_ACTION_RUNNING", "inspection": inspection, "action": "NONE"})
            continue
        if not spec.launch_args:
            result = {"instance": spec.name, "status": "UNSAFE_TO_RESTART", "inspection": inspection, "action": "NONE", "reason": "LAUNCH_ARGUMENTS_NOT_CONFIGURED"}
            _record_incident_safe(config.ops_root, "LAUNCH_ARGUMENTS_NOT_CONFIGURED", {"instance": spec.name})
            results.append(result)
            continue
        if any("portable" in arg.lower() for arg in spec.launch_args) and not spec.allow_portable:
            result = {"instance": spec.name, "status": "UNSAFE_TO_RESTART", "inspection": inspection, "action": "NONE", "reason": "PORTABLE_MODE_NOT_APPROVED"}
            _record_incident_safe(config.ops_root, "PORTABLE_MODE_NOT_APPROVED", {"instance": spec.name})
            results.append(result)
            continue
        if any(arg.lower().split("=", 1)[0] in {"/login", "/password", "/server", "--login", "--password", "--server"} for arg in spec.launch_args):
            result = {"instance": spec.name, "status": "UNSAFE_TO_RESTART", "inspection": inspection, "action": "NONE", "reason": "CREDENTIAL_OR_SERVER_OVERRIDE_FORBIDDEN"}
            _record_incident_safe(config.ops_root, "CREDENTIAL_OR_SERVER_OVERRIDE_FORBIDDEN", {"instance": spec.name})
            results.append(result)
            continue
        instance_state = dict(state.setdefault("instances", {}).get(spec.name, {}))
        attempts = [float(item) for item in instance_state.get("restart_attempts_epoch", []) if isinstance(item, (int, float))]
        now_epoch = _now_dt(now).timestamp()
        attempts = [item for item in attempts if now_epoch - item < config.restart_window_seconds]
        if len(attempts) >= config.max_restarts:
            result = {"instance": spec.name, "status": "CIRCUIT_OPEN", "inspection": inspection, "action": "NONE", "restart_attempts": len(attempts)}
            _record_incident_safe(config.ops_root, "RECOVERY_CIRCUIT_OPEN", {"instance": spec.name, "attempts": len(attempts)})
            results.append(result)
            continue
        snapshot = None if dry_run else _prelaunch_snapshot(spec, config.ops_root, inspection)
        command = [str(spec.terminal_exe), *spec.launch_args]
        if dry_run:
            results.append({"instance": spec.name, "status": "DRY_RUN_ELIGIBLE", "inspection": inspection, "action": "WOULD_START_EXACT_TERMINAL", "command": _redact_command(command), "snapshot": None, "restart_attempts": len(attempts)})
            continue
        try:
            process = popen(command, cwd=str(spec.install_directory), shell=False, close_fds=True)
            pid = getattr(process, "pid", None)
            attempts.append(now_epoch)
            instance_state.update({"restart_attempts_epoch": attempts, "last_started_at_utc": format_utc_timestamp(_now_dt(now)), "last_pid": pid})
            state["instances"][spec.name] = instance_state
            _save_state(config.ops_root, state)
            append_operator_log(config.ops_root, {"event": "MT5_SAFE_START_REQUESTED", "instance": spec.name, "pid": pid, "command": _redact_command(command), "trading_action": "NONE"})
            results.append({"instance": spec.name, "status": "STARTED_PENDING_VERIFICATION", "inspection": inspection, "action": "STARTED_EXACT_TERMINAL", "pid": pid, "snapshot": str(snapshot), "restart_attempts": len(attempts)})
        except (OSError, subprocess.SubprocessError) as exc:
            _record_incident_safe(config.ops_root, "SAFE_START_FAILED", {"instance": spec.name, "error": type(exc).__name__})
            results.append({"instance": spec.name, "status": "START_FAILED", "inspection": inspection, "action": "NONE", "reason": type(exc).__name__, "snapshot": str(snapshot) if snapshot else None})
    overall = "PASS" if all(item["status"] in {"NO_ACTION_RUNNING", "DRY_RUN_ELIGIBLE", "STARTED_PENDING_VERIFICATION"} for item in results) else "BLOCKED"
    return {"schema": WATCHDOG_SCHEMA, "checked_at_utc": format_utc_timestamp(_now_dt(now)), "status": overall, "dry_run": dry_run, "instances": results, "trading_action": "NONE", "forward_authorization": "NOT_CREATED", "forward_run_id": "NOT_CREATED"}


def watchdog_health(config: WatchdogConfig, *, now: str | datetime | None = None, process_provider: Callable[[], tuple[list[dict[str, Any]], str | None]] | None = None) -> dict[str, Any]:
    status = watchdog_status(config, now=now, process_provider=process_provider)
    incidents = []
    for item in status["instances"]:
        incidents.extend(item.get("gate_reasons", []))
        incidents.extend(item.get("telemetry", {}).get("reasons", []))
    return {**status, "health_status": "HEALTHY" if status["status"] == "PASS" else ("CRITICAL" if incidents else "WARNING"), "reasons": sorted(set(incidents))}


__all__ = [
    "DEFAULT_CRITICAL_SECONDS", "DEFAULT_MAX_RESTARTS", "DEFAULT_RESTART_WINDOW_SECONDS", "DEFAULT_TELEMETRY_SCHEMA", "DEFAULT_WARNING_SECONDS", "MT5InstanceSpec", "WATCHDOG_SCHEMA", "WatchdogConfig", "WatchdogSafetyError", "inspect_instance", "load_watchdog_config", "recover_once", "watchdog_health", "watchdog_status",
]
