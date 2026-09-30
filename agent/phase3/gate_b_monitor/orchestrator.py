"""Fail-closed, exactly-once acceptance orchestration.

The orchestrator is deliberately an adapter, not an MT5 launcher.  A real
control surface must be supplied by an independently approved integration.  If
the capability is absent, `start_once` refuses before creating a chart.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from .models import ApprovalScope, CapabilityClass, CapabilityMatrix, HARD_DEADLINE_SECONDS, utc_string


class AutomationBlocked(RuntimeError):
    """The requested runtime action is not safe or not authorized."""


class ExistingRunLock(AutomationBlocked):
    """An existing lock must be reviewed; it is never removed automatically."""


class SessionState(str, Enum):
    NEW = "NEW"
    PRECHECKED = "PRECHECKED"
    SUPERVISOR_STARTED = "SUPERVISOR_STARTED"
    CHART_CREATED = "CHART_CREATED"
    ATTACHED = "ATTACHED"
    RUNNING = "RUNNING"
    STOP_REQUESTED = "STOP_REQUESTED"
    EA_REMOVED = "EA_REMOVED"
    CHART_CLOSED = "CHART_CLOSED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ChartHandle:
    chart_id: int
    symbol: str
    timeframe: str
    owner_token: str


class Mt5ControlSurface(Protocol):
    """Explicit adapter boundary for a future approved native control API."""

    def create_chart(self, symbol: str, timeframe: str, owner_token: str) -> ChartHandle: ...

    def attach_monitor(self, chart: ChartHandle, source_sha256: str, ex5_sha256: str, session_id: str) -> None: ...

    def request_monitor_stop(self, chart: ChartHandle, session_id: str) -> bool: ...

    def confirm_monitor_removed(self, chart: ChartHandle, session_id: str) -> bool: ...

    def close_owned_chart(self, chart: ChartHandle, owner_token: str) -> None: ...

    def confirm_chart_closed(self, chart: ChartHandle, owner_token: str) -> bool: ...


class NativeMt5ControlSurface:
    """Placeholder that fails closed until an approved native adapter exists."""

    error = "AUTHORIZED_MT5_CONTROL_SURFACE_UNAVAILABLE"

    def _blocked(self) -> None:
        raise AutomationBlocked(self.error)

    def create_chart(self, symbol: str, timeframe: str, owner_token: str) -> ChartHandle:
        self._blocked()
        raise AssertionError("unreachable")

    def attach_monitor(self, chart: ChartHandle, source_sha256: str, ex5_sha256: str, session_id: str) -> None:
        self._blocked()

    def request_monitor_stop(self, chart: ChartHandle, session_id: str) -> bool:
        self._blocked()
        return False

    def confirm_monitor_removed(self, chart: ChartHandle, session_id: str) -> bool:
        self._blocked()
        return False

    def close_owned_chart(self, chart: ChartHandle, owner_token: str) -> None:
        self._blocked()

    def confirm_chart_closed(self, chart: ChartHandle, owner_token: str) -> bool:
        self._blocked()
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AtomicRunLock:
    """Create-once lock; an existing lock always requires manual review."""

    def __init__(self, path: Path, *, run_id: str, now: datetime | None = None) -> None:
        self.path = path
        self.run_id = run_id
        self.now = now or datetime.now(UTC)
        self.owner_token = secrets.token_hex(16)
        self.acquired = False

    def acquire(self) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "pr6-gate-b-monitor-run-lock/1",
            "run_id": self.run_id,
            "owner_token": self.owner_token,
            "created_at_utc": utc_string(self.now),
            "pid": os.getpid(),
            "action": "ONE_SHOT_MONITOR_ONLY",
        }
        encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ExistingRunLock(f"STALE_OR_ACTIVE_LOCK_REQUIRES_REVIEW:{self.path}") from exc
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)
        self.acquired = True
        return payload

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ExistingRunLock("LOCK_CONTENT_UNREADABLE_REQUIRES_REVIEW")
        if current.get("owner_token") != self.owner_token:
            raise ExistingRunLock("LOCK_OWNER_MISMATCH_REQUIRES_REVIEW")
        self.path.unlink()
        self.acquired = False


@dataclass(frozen=True)
class PrecheckResult:
    status: str
    reasons: tuple[str, ...]
    source_sha256: str | None
    ex5_sha256: str | None


@dataclass
class OrchestratorRun:
    run_id: str
    state: SessionState = SessionState.NEW
    chart: ChartHandle | None = None
    attach_count: int = 0
    stop_count: int = 0
    reasons: list[str] | None = None


class AcceptanceOrchestrator:
    """Coordinates one future run; it has no retry or implicit GUI fallback."""

    def __init__(
        self,
        *,
        scope: ApprovalScope,
        source_path: Path,
        ex5_path: Path,
        evidence_root: Path,
        capabilities: CapabilityMatrix,
        control_surface: Mt5ControlSurface | None = None,
    ) -> None:
        self.scope = scope
        self.source_path = source_path
        self.ex5_path = ex5_path
        self.evidence_root = evidence_root
        self.capabilities = capabilities
        self.control_surface = control_surface or NativeMt5ControlSurface()
        self.run = OrchestratorRun(run_id=secrets.token_hex(12), reasons=[])
        self.lock = AtomicRunLock(evidence_root / "run.lock", run_id=self.run.run_id)

    def precheck(self) -> PrecheckResult:
        reasons = list(self.scope.validate())
        source_hash = sha256_file(self.source_path) if self.source_path.is_file() else None
        ex5_hash = sha256_file(self.ex5_path) if self.ex5_path.is_file() else None
        if source_hash != self.scope.source_sha256:
            reasons.append("MONITOR_SOURCE_SHA256_MISMATCH")
        if ex5_hash != self.scope.ex5_sha256:
            reasons.append("MONITOR_EX5_SHA256_MISMATCH")
        if self.capabilities.classification == CapabilityClass.NO_SAFE_RUNTIME:
            reasons.append("AUTHORIZED_MT5_CONTROL_SURFACE_UNAVAILABLE")
        if not self.capabilities.supervisor_independent_of_chat:
            reasons.append("INDEPENDENT_SUPERVISOR_UNAVAILABLE")
        if not self.capabilities.independent_stop:
            reasons.append("INDEPENDENT_STOP_CAPABILITY_NOT_AVAILABLE")
        self.run.state = SessionState.PRECHECKED if not reasons else SessionState.FAILED
        self.run.reasons = reasons
        return PrecheckResult("PASS" if not reasons else "BLOCKED", tuple(reasons), source_hash, ex5_hash)

    def start_once(self) -> OrchestratorRun:
        """Start exactly once after a separately approved, passing precheck."""

        if self.run.attach_count:
            raise AutomationBlocked("EXACTLY_ONCE_ATTACH_ALREADY_ATTEMPTED_NO_RETRY")
        result = self.precheck()
        if result.status != "PASS":
            raise AutomationBlocked(";".join(result.reasons))
        self.lock.acquire()
        self.run.state = SessionState.SUPERVISOR_STARTED
        owner_token = self.lock.owner_token
        try:
            chart = self.control_surface.create_chart(self.scope.symbol, self.scope.timeframe, owner_token)
            if chart.owner_token != owner_token or chart.symbol != self.scope.symbol or chart.timeframe != self.scope.timeframe:
                raise AutomationBlocked("CHART_OWNERSHIP_OR_IDENTITY_MISMATCH")
            self.run.chart = chart
            self.run.state = SessionState.CHART_CREATED
            self.control_surface.attach_monitor(chart, self.scope.source_sha256, self.scope.ex5_sha256, self.run.run_id)
            self.run.attach_count = 1
            self.run.state = SessionState.ATTACHED
            return self.run
        except Exception as exc:
            self.run.state = SessionState.FAILED
            self.run.reasons = [type(exc).__name__]
            raise

    def request_stop(self) -> None:
        if self.run.state is SessionState.FAILED:
            raise AutomationBlocked("FAILED_RUN_NO_STOP_RETRY")
        if self.run.attach_count != 1 or self.run.chart is None:
            raise AutomationBlocked("STOP_REQUIRES_ONE_ATTACHED_MONITOR")
        if self.run.stop_count:
            return
        if not self.control_surface.request_monitor_stop(self.run.chart, self.run.run_id):
            self.run.state = SessionState.FAILED
            self.run.reasons = ["STOP_REQUEST_REJECTED"]
            raise AutomationBlocked("STOP_REQUEST_REJECTED")
        self.run.stop_count = 1
        self.run.state = SessionState.STOP_REQUESTED

    def confirm_cleanup(self) -> bool:
        if self.run.chart is None or self.run.stop_count != 1:
            raise AutomationBlocked("CLEANUP_REQUIRES_STOP_REQUEST")
        if not self.control_surface.confirm_monitor_removed(self.run.chart, self.run.run_id):
            return False
        self.run.state = SessionState.EA_REMOVED
        self.control_surface.close_owned_chart(self.run.chart, self.lock.owner_token)
        if not self.control_surface.confirm_chart_closed(self.run.chart, self.lock.owner_token):
            return False
        self.run.state = SessionState.CHART_CLOSED
        return True


def capability_matrix_from_cua_state(state: Mapping[str, Any]) -> CapabilityMatrix:
    """Convert an observed CUA state to a conservative capability matrix."""

    apps = state.get("apps")
    native = isinstance(apps, list) and any(
        isinstance(item, Mapping) and str(item.get("name", "")).lower() in {"mt5", "metatrader 5", "metaeditor"}
        for item in apps
    )
    # Browser surfaces never imply MT5 control.  Every capability is explicit.
    return CapabilityMatrix(
        native_mt5_surface=native,
        compile_exact_source=False,
        create_chart=False,
        attach_exactly_once=False,
        read_chart_identity=False,
        prove_chart_ownership=False,
        request_monitor_stop=False,
        prove_ea_removed=False,
        close_owned_chart=False,
        prove_chart_closed=False,
        supervisor_independent_of_chat=False,
        independent_stop=False,
        evidence_collection=True,
    )


__all__ = [
    "AcceptanceOrchestrator",
    "AtomicRunLock",
    "AutomationBlocked",
    "CapabilityClass",
    "ChartHandle",
    "ExistingRunLock",
    "NativeMt5ControlSurface",
    "PrecheckResult",
    "SessionState",
    "capability_matrix_from_cua_state",
]
