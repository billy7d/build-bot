"""Fail-closed evaluator for Gate B V2 monitor evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping

from .models import (
    HARD_DEADLINE_SECONDS,
    MAX_WITHIN_SESSION_GAP_SECONDS,
    MONITOR_PROGRAM_TYPE,
    SAMPLE_INTERVAL_SECONDS,
    SOFT_STOP_SECONDS,
    ApprovalScope,
    CapabilityClass,
    CapabilityMatrix,
    PermissionSample,
    parse_utc,
)


DEDICATED_ACCEPTANCE_FIELDS = (
    "INSTALLATION_ISOLATION",
    "DATA_ROOT_ISOLATION",
    "COMMON_DATA_COLLISION_CHECK",
    "SOURCE_IDENTITY",
    "MONITOR_BINARY_IDENTITY",
    "STARTUP_CONFIG_VALID",
    "AUTOMATED_LAUNCH",
    "AUTOMATED_ATTACH",
    "SESSION_UNIQUENESS",
    "INVESTOR_PERMISSIONS",
    "SAMPLING_CONTINUITY",
    "SELF_STOP",
    "INDEPENDENT_STOP",
    "DURATION_COMPLIANCE",
    "EA_REMOVAL",
    "CHART_CLOSURE",
    "PROCESS_TERMINATION",
    "PRODUCTION_UNCHANGED",
    "EVIDENCE_INTEGRITY",
)


@dataclass(frozen=True)
class MonitorEvaluationInput:
    scope: ApprovalScope
    samples: tuple[PermissionSample, ...]
    start_utc: datetime | None
    end_utc: datetime | None
    chart_ids: tuple[int, ...]
    session_ids: tuple[str, ...]
    chart_closed_confirmed: bool | None
    ea_removed_confirmed: bool | None
    stop_requested_seconds: float | None
    compile_errors: int | None
    compile_warnings: int | None
    source_sha256: str | None
    ex5_sha256: str | None
    extra_diagnostic_executions: int = 0
    trade_matches: tuple[str, ...] = ()
    capability: CapabilityMatrix | None = None
    authoritative_account_history: bool = False


@dataclass
class EvaluationResult:
    statuses: dict[str, str]
    reasons: dict[str, list[str]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": "pr6-gate-b-monitor-v2-evaluation/1", "statuses": self.statuses, "reasons": self.reasons, "metrics": self.metrics}


def evaluate_dedicated_acceptance(
    checks: Mapping[str, str],
    *,
    real_execution: bool,
    gate_b_authorized: bool = False,
) -> EvaluationResult:
    """Evaluate the dedicated acceptance checklist without auto-promoting Gate B.

    ``gate_b_authorized`` is intentionally ignored for promotion in this
    function: Monitor preflight evidence and Gate B approval are separate
    boundaries.  The argument is retained only for audit visibility.
    """

    statuses: dict[str, str] = {}
    reasons: dict[str, list[str]] = {}
    allowed = {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE", "NOT_RUN"}
    for field_name in DEDICATED_ACCEPTANCE_FIELDS:
        value = str(checks.get(field_name, "NOT_RUN")).upper()
        if value not in allowed:
            value = "INCONCLUSIVE"
            reasons.setdefault(field_name, []).append("UNKNOWN_STATUS_VALUE")
        statuses[field_name] = value
        if value != "PASS":
            reasons.setdefault(field_name, []).append(f"{field_name}_{value}")

    values = tuple(statuses.values())
    if not real_execution:
        statuses["MONITOR_PREFLIGHT"] = "NOT_RUN"
    elif "FAIL" in values:
        statuses["MONITOR_PREFLIGHT"] = "FAIL"
    elif "BLOCKED" in values or "NOT_RUN" in values:
        statuses["MONITOR_PREFLIGHT"] = "BLOCKED"
    elif "INCONCLUSIVE" in values:
        statuses["MONITOR_PREFLIGHT"] = "INCONCLUSIVE"
    else:
        statuses["MONITOR_PREFLIGHT"] = "PASS"
    # Gate B requires separate policy, production and telemetry approvals.
    statuses["GATE_B_OVERALL"] = "BLOCKED"
    statuses["REAL_TELEMETRY"] = "NOT_RUN"
    metrics = {
        "real_execution": real_execution,
        "gate_b_authorized_input": gate_b_authorized,
        "gate_b_promotion": "NOT_AUTOMATIC",
        "mandatory_field_count": len(DEDICATED_ACCEPTANCE_FIELDS),
    }
    return EvaluationResult(statuses=statuses, reasons=reasons, metrics=metrics)


def _samples(value: Iterable[PermissionSample | Mapping[str, Any]]) -> tuple[PermissionSample, ...]:
    result: list[PermissionSample] = []
    for item in value:
        result.append(item if isinstance(item, PermissionSample) else PermissionSample.from_mapping(item))
    return tuple(result)


def _status_for(reasons: list[str], missing: list[str]) -> str:
    if reasons:
        return "FAIL"
    if missing:
        return "INCONCLUSIVE"
    return "PASS"


def evaluate_monitor(data: MonitorEvaluationInput) -> EvaluationResult:
    samples = tuple(sorted(data.samples, key=lambda item: item.monotonic_ms))
    reasons: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}

    code_reasons: list[str] = []
    code_missing: list[str] = []
    if data.compile_errors is None or data.compile_warnings is None:
        code_missing.append("COMPILE_RESULT_MISSING")
    elif data.compile_errors != 0 or data.compile_warnings != 0:
        code_reasons.append("COMPILE_NOT_ZERO_ERRORS_WARNINGS")
    if not data.source_sha256 or data.source_sha256 != data.scope.source_sha256:
        code_reasons.append("SOURCE_SHA256_MISMATCH_OR_MISSING")
    if not data.ex5_sha256 or data.ex5_sha256 != data.scope.ex5_sha256:
        code_reasons.append("EX5_SHA256_MISMATCH_OR_MISSING")
    reasons["CODE_READY"] = code_reasons
    missing["CODE_READY"] = code_missing

    automation_reasons: list[str] = []
    automation_missing: list[str] = []
    if data.capability is None:
        automation_missing.append("CAPABILITY_MATRIX_MISSING")
    else:
        if data.capability.classification is CapabilityClass.NO_SAFE_RUNTIME:
            automation_reasons.append("AUTHORIZED_MT5_CONTROL_SURFACE_UNAVAILABLE")
        if not data.capability.supervisor_independent_of_chat:
            automation_reasons.append("INDEPENDENT_SUPERVISOR_UNAVAILABLE")
        if not data.capability.independent_stop:
            automation_reasons.append("INDEPENDENT_STOP_CAPABILITY_NOT_AVAILABLE")
    reasons["AUTOMATION_READY"] = automation_reasons
    missing["AUTOMATION_READY"] = automation_missing

    functional_reasons: list[str] = []
    functional_missing: list[str] = []
    if not samples:
        functional_missing.append("NO_SAMPLES")
    for index, sample in enumerate(samples):
        if sample.account != data.scope.account:
            functional_reasons.append(f"ACCOUNT_MISMATCH_SAMPLE_{index}")
        if sample.server != data.scope.server:
            functional_reasons.append(f"SERVER_MISMATCH_SAMPLE_{index}")
        if sample.symbol != data.scope.symbol or sample.timeframe != data.scope.timeframe:
            functional_reasons.append(f"SYMBOL_TIMEFRAME_MISMATCH_SAMPLE_{index}")
        if sample.account_trade_mode != 0:
            functional_reasons.append(f"NOT_DEMO_SAMPLE_{index}")
        if sample.account_trade_allowed != 0 or sample.terminal_trade_allowed != 0:
            functional_reasons.append(f"TRADING_PERMISSION_ENABLED_SAMPLE_{index}")
        if sample.terminal_connected != 1:
            functional_reasons.append(f"TERMINAL_DISCONNECTED_SAMPLE_{index}")
        if sample.mql_program_type != MONITOR_PROGRAM_TYPE:
            functional_reasons.append(f"PROGRAM_TYPE_NOT_EA_SAMPLE_{index}")
        if sample.scope != "monitor_ea":
            functional_reasons.append(f"MQL_SCOPE_INVALID_SAMPLE_{index}")
    reasons["FUNCTIONAL_EVIDENCE"] = functional_reasons
    missing["FUNCTIONAL_EVIDENCE"] = functional_missing

    procedural_reasons: list[str] = []
    procedural_missing: list[str] = []
    if len(data.chart_ids) != 1 or len(set(data.chart_ids)) != 1:
        procedural_reasons.append("EXACTLY_ONE_CHART_REQUIRED")
    if len(data.session_ids) != 1 or len(set(data.session_ids)) != 1:
        procedural_reasons.append("EXACTLY_ONE_SESSION_REQUIRED")
    if data.start_utc is None or data.end_utc is None:
        procedural_missing.append("SESSION_BOUNDARIES_MISSING")
    else:
        duration = (parse_utc(data.end_utc) - parse_utc(data.start_utc)).total_seconds()
        if duration > HARD_DEADLINE_SECONDS:
            procedural_reasons.append("HARD_DEADLINE_EXCEEDED")
    if data.stop_requested_seconds is None:
        procedural_missing.append("STOP_REQUEST_TIME_MISSING")
    elif data.stop_requested_seconds > SOFT_STOP_SECONDS:
        procedural_reasons.append("SOFT_STOP_AFTER_540_SECONDS")
    gaps = [
        (right.monotonic_ms - left.monotonic_ms) / 1000.0
        for left, right in zip(samples, samples[1:])
    ]
    max_gap = max(gaps) if gaps else None
    if max_gap is None and samples:
        procedural_missing.append("INSUFFICIENT_SAMPLES_FOR_GAP_PROOF")
    elif max_gap is not None and max_gap > MAX_WITHIN_SESSION_GAP_SECONDS:
        procedural_reasons.append("WITHIN_SESSION_GAP_OVER_90_SECONDS")
    for gap in gaps:
        if gap < 1 or gap > SAMPLE_INTERVAL_SECONDS + 10:
            procedural_reasons.append("SAMPLE_INTERVAL_OUTSIDE_60_SECOND_TOLERANCE")
            break
    if data.ea_removed_confirmed is not True:
        procedural_missing.append("EA_REMOVAL_NOT_CONFIRMED")
    if data.chart_closed_confirmed is not True:
        procedural_missing.append("CHART_CLOSURE_NOT_CONFIRMED")
    if data.extra_diagnostic_executions:
        procedural_reasons.append("EXTRA_DIAGNOSTIC_EXECUTIONS_PRESENT")
    if data.trade_matches:
        procedural_reasons.append("TRADE_ACTIVITY_IN_EVIDENCE")
    reasons["PROCEDURAL_COMPLIANCE"] = procedural_reasons
    missing["PROCEDURAL_COMPLIANCE"] = procedural_missing

    statuses = {
        "CODE_READY": _status_for(code_reasons, code_missing),
        "AUTOMATION_READY": _status_for(automation_reasons, automation_missing),
        "FUNCTIONAL_EVIDENCE": _status_for(functional_reasons, functional_missing),
        "PROCEDURAL_COMPLIANCE": _status_for(procedural_reasons, procedural_missing),
    }
    if statuses["AUTOMATION_READY"] == "FAIL":
        statuses["AUTOMATION_READY"] = "BLOCKED"
    if all(statuses[key] == "PASS" for key in statuses):
        statuses["MONITOR_PREFLIGHT"] = "PASS"
    elif any(statuses[key] == "FAIL" for key in ("CODE_READY", "FUNCTIONAL_EVIDENCE", "PROCEDURAL_COMPLIANCE")):
        statuses["MONITOR_PREFLIGHT"] = "FAIL"
    else:
        statuses["MONITOR_PREFLIGHT"] = "BLOCKED"
    statuses["GATE_B_OVERALL"] = "PASS" if statuses["MONITOR_PREFLIGHT"] == "PASS" else "BLOCKED"
    reasons.update({key: value for key, value in missing.items() if value})
    metrics = {
        "sample_count": len(samples),
        "max_within_session_gap_seconds": max_gap,
        "continuous_enforcement": statuses["PROCEDURAL_COMPLIANCE"] == "PASS" and data.authoritative_account_history,
        "production_mql_trade_allowed": "NOT_OBSERVED_AND_NOT_INFERRED",
        "authoritative_account_history": data.authoritative_account_history,
    }
    return EvaluationResult(statuses=statuses, reasons=reasons, metrics=metrics)


__all__ = ["DEDICATED_ACCEPTANCE_FIELDS", "EvaluationResult", "MonitorEvaluationInput", "evaluate_dedicated_acceptance", "evaluate_monitor"]
