"""Typed contracts for the Gate B V2 monitor.

These models deliberately separate operator scope, runtime observations and
evaluation results.  Nothing in this module starts a process, opens a chart,
logs in, or changes MT5 state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


SAMPLE_INTERVAL_SECONDS = 60
MAX_WITHIN_SESSION_GAP_SECONDS = 90
SOFT_STOP_SECONDS = 540
HARD_DEADLINE_SECONDS = 600
EXPECTED_SYMBOL = "BTCUSD"
EXPECTED_TIMEFRAME = "H1"
MONITOR_PROGRAM_TYPE = 2
MONITOR_SCHEMA = "pr6-read-only-permission-monitor-v2/1"


def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class CapabilityClass(str, Enum):
    FULL_GUI_AUTOMATION = "FULL_GUI_AUTOMATION"
    AUTO_RUNTIME_ONLY = "AUTO_RUNTIME_ONLY"
    NO_SAFE_RUNTIME = "NO_SAFE_RUNTIME"


@dataclass(frozen=True)
class CapabilityMatrix:
    """Evidence-backed capability result; no capability is inferred."""

    native_mt5_surface: bool
    compile_exact_source: bool
    create_chart: bool
    attach_exactly_once: bool
    read_chart_identity: bool
    prove_chart_ownership: bool
    request_monitor_stop: bool
    prove_ea_removed: bool
    close_owned_chart: bool
    prove_chart_closed: bool
    supervisor_independent_of_chat: bool
    independent_stop: bool
    evidence_collection: bool

    @property
    def classification(self) -> CapabilityClass:
        all_gui = all(
            (
                self.native_mt5_surface,
                self.compile_exact_source,
                self.create_chart,
                self.attach_exactly_once,
                self.read_chart_identity,
                self.prove_chart_ownership,
                self.request_monitor_stop,
                self.prove_ea_removed,
                self.close_owned_chart,
                self.prove_chart_closed,
                self.supervisor_independent_of_chat,
                self.independent_stop,
                self.evidence_collection,
            )
        )
        if all_gui:
            return CapabilityClass.FULL_GUI_AUTOMATION
        if self.supervisor_independent_of_chat and self.evidence_collection:
            return CapabilityClass.AUTO_RUNTIME_ONLY
        return CapabilityClass.NO_SAFE_RUNTIME

    def to_dict(self) -> dict[str, Any]:
        payload = {key: value for key, value in self.__dict__.items()}
        payload["classification"] = self.classification.value
        return payload


@dataclass(frozen=True)
class ApprovalScope:
    """Canonical, narrow V2 scope after the requested contract clarification."""

    status: str
    operator_id: str
    source_sha256: str
    ex5_sha256: str
    account: str
    server: str
    symbol: str = EXPECTED_SYMBOL
    timeframe: str = EXPECTED_TIMEFRAME
    max_duration_seconds: int = HARD_DEADLINE_SECONDS
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS
    max_gap_seconds: int = MAX_WITHIN_SESSION_GAP_SECONDS
    one_chart: bool = True
    no_diagnostic: bool = True
    no_production_ea: bool = True
    no_trade: bool = True

    def validate(self) -> list[str]:
        reasons: list[str] = []
        if self.status.upper() != "APPROVED":
            reasons.append("APPROVAL_NOT_APPROVED")
        if not self.operator_id.strip():
            reasons.append("OPERATOR_ID_MISSING")
        if self.symbol != EXPECTED_SYMBOL:
            reasons.append("SYMBOL_MISMATCH")
        if self.timeframe != EXPECTED_TIMEFRAME:
            reasons.append("TIMEFRAME_MISMATCH")
        if self.max_duration_seconds != HARD_DEADLINE_SECONDS:
            reasons.append("MAX_DURATION_MUST_BE_600_SECONDS")
        if self.sample_interval_seconds != SAMPLE_INTERVAL_SECONDS:
            reasons.append("SAMPLE_INTERVAL_MUST_BE_60_SECONDS")
        if self.max_gap_seconds != MAX_WITHIN_SESSION_GAP_SECONDS:
            reasons.append("MAX_GAP_MUST_BE_90_SECONDS")
        if not self.one_chart:
            reasons.append("ONE_CHART_REQUIRED")
        if not self.no_diagnostic:
            reasons.append("DIAGNOSTIC_FORBIDDEN")
        if not self.no_production_ea:
            reasons.append("PRODUCTION_EA_FORBIDDEN")
        if not self.no_trade:
            reasons.append("TRADE_ACTIONS_FORBIDDEN")
        for name, value in (("source_sha256", self.source_sha256), ("ex5_sha256", self.ex5_sha256)):
            if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
                reasons.append(f"{name.upper()}_INVALID")
        return reasons

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ApprovalScope":
        return cls(
            status=str(payload.get("status", "")),
            operator_id=str(payload.get("operator_id", "")),
            source_sha256=str(payload.get("source_sha256", "")),
            ex5_sha256=str(payload.get("ex5_sha256", "")),
            account=str(payload.get("account", "")),
            server=str(payload.get("server", "")),
            symbol=str(payload.get("symbol", EXPECTED_SYMBOL)),
            timeframe=str(payload.get("timeframe", EXPECTED_TIMEFRAME)),
            max_duration_seconds=int(payload.get("max_duration_seconds", HARD_DEADLINE_SECONDS)),
            sample_interval_seconds=int(payload.get("sample_interval_seconds", SAMPLE_INTERVAL_SECONDS)),
            max_gap_seconds=int(payload.get("max_gap_seconds", MAX_WITHIN_SESSION_GAP_SECONDS)),
            one_chart=bool(payload.get("one_chart", True)),
            no_diagnostic=bool(payload.get("no_diagnostic", True)),
            no_production_ea=bool(payload.get("no_production_ea", True)),
            no_trade=bool(payload.get("no_trade", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operator_id": self.operator_id,
            "source_sha256": self.source_sha256,
            "ex5_sha256": self.ex5_sha256,
            "account": self.account,
            "server": self.server,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "max_duration_seconds": self.max_duration_seconds,
            "sample_interval_seconds": self.sample_interval_seconds,
            "max_gap_seconds": self.max_gap_seconds,
            "one_chart": self.one_chart,
            "no_diagnostic": self.no_diagnostic,
            "no_production_ea": self.no_production_ea,
            "no_trade": self.no_trade,
        }


@dataclass(frozen=True)
class PermissionSample:
    session_id: str
    timestamp_utc: datetime
    monotonic_ms: int
    account: str
    server: str
    symbol: str
    timeframe: str
    chart_id: int
    account_trade_mode: int
    account_trade_allowed: int
    account_trade_expert: int
    terminal_connected: int
    terminal_trade_allowed: int
    mql_trade_allowed: int
    mql_program_type: int
    scope: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PermissionSample":
        required = (
            "session_id", "timestamp_utc", "monotonic_ms", "account", "server",
            "symbol", "timeframe", "chart_id", "account_trade_mode",
            "account_trade_allowed", "account_trade_expert", "terminal_connected",
            "terminal_trade_allowed", "mql_trade_allowed", "mql_program_type", "scope",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"sample missing fields: {', '.join(missing)}")
        return cls(
            session_id=str(payload["session_id"]),
            timestamp_utc=parse_utc(str(payload["timestamp_utc"])),
            monotonic_ms=int(payload["monotonic_ms"]),
            account=str(payload["account"]),
            server=str(payload["server"]),
            symbol=str(payload["symbol"]),
            timeframe=str(payload["timeframe"]),
            chart_id=int(payload["chart_id"]),
            account_trade_mode=int(payload["account_trade_mode"]),
            account_trade_allowed=int(payload["account_trade_allowed"]),
            account_trade_expert=int(payload["account_trade_expert"]),
            terminal_connected=int(payload["terminal_connected"]),
            terminal_trade_allowed=int(payload["terminal_trade_allowed"]),
            mql_trade_allowed=int(payload["mql_trade_allowed"]),
            mql_program_type=int(payload["mql_program_type"]),
            scope=str(payload["scope"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MONITOR_SCHEMA,
            "session_id": self.session_id,
            "timestamp_utc": utc_string(self.timestamp_utc),
            "monotonic_ms": self.monotonic_ms,
            "account": self.account,
            "server": self.server,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "chart_id": self.chart_id,
            "account_trade_mode": self.account_trade_mode,
            "account_trade_allowed": self.account_trade_allowed,
            "account_trade_expert": self.account_trade_expert,
            "terminal_connected": self.terminal_connected,
            "terminal_trade_allowed": self.terminal_trade_allowed,
            "mql_trade_allowed": self.mql_trade_allowed,
            "mql_program_type": self.mql_program_type,
            "scope": self.scope,
        }


@dataclass
class SessionRecord:
    session_id: str
    chart_id: int
    symbol: str
    timeframe: str
    start_utc: datetime
    start_monotonic_ms: int
    stop_requested_utc: datetime | None = None
    ea_removed_utc: datetime | None = None
    chart_closed_utc: datetime | None = None
    end_utc: datetime | None = None
    samples: list[PermissionSample] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        if self.end_utc is None:
            return None
        return (self.end_utc - self.start_utc).total_seconds()
