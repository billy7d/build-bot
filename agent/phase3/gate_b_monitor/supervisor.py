"""One-shot independent session supervisor contracts.

The supervisor never kills a terminal and never guesses a chart.  A future
approved adapter must provide a stop callback bound to the exact
terminal/process, chart and session.  Without that capability the supervisor
refuses attachment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from .models import HARD_DEADLINE_SECONDS, MAX_WITHIN_SESSION_GAP_SECONDS, PermissionSample, SOFT_STOP_SECONDS


class SupervisorBlocked(RuntimeError):
    """Supervisor cannot prove the exact stop/identity contract."""


class SupervisorState(str, Enum):
    NEW = "NEW"
    STARTED = "STARTED"
    ATTACHED = "ATTACHED"
    STOP_REQUESTED = "STOP_REQUESTED"
    EA_REMOVED = "EA_REMOVED"
    CHART_CLOSED = "CHART_CLOSED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class StopDecision:
    requested: bool
    reason: str | None
    monotonic_seconds: float
    state: SupervisorState


# The chart id is deliberately part of the callback contract.  A callback
# that only receives a session id cannot prove that it will not stop another
# chart in a shared terminal.
StopCallback = Callable[[str, int, str], bool]


class SessionSupervisor:
    """Monotonic, exactly-once supervisor for one monitor session."""

    def __init__(
        self,
        *,
        session_id: str,
        independent_stop: bool,
        stop_callback: StopCallback | None = None,
        max_seconds: int = HARD_DEADLINE_SECONDS,
        soft_seconds: int = SOFT_STOP_SECONDS,
        max_gap_seconds: int = MAX_WITHIN_SESSION_GAP_SECONDS,
    ) -> None:
        self.session_id = session_id
        self.independent_stop = independent_stop
        self.stop_callback = stop_callback
        self.max_seconds = max_seconds
        self.soft_seconds = soft_seconds
        self.max_gap_seconds = max_gap_seconds
        self.state = SupervisorState.NEW
        self.start_monotonic: float | None = None
        self.start_utc: datetime | None = None
        self.chart_id: int | None = None
        self.stop_requested_at: float | None = None
        self.stop_reason: str | None = None
        self.last_heartbeat_monotonic: float | None = None
        self.last_sample_monotonic: float | None = None
        self.sample_count = 0
        self.events: list[dict[str, object]] = []

    def start(self, *, monotonic_seconds: float, start_utc: datetime) -> None:
        if self.state is not SupervisorState.NEW:
            raise SupervisorBlocked("SUPERVISOR_START_NOT_EXACTLY_ONCE")
        if not self.independent_stop or self.stop_callback is None:
            self.state = SupervisorState.FAILED
            raise SupervisorBlocked("INDEPENDENT_STOP_CAPABILITY_NOT_AVAILABLE")
        self.start_monotonic = monotonic_seconds
        self.start_utc = start_utc
        self.last_heartbeat_monotonic = monotonic_seconds
        self.state = SupervisorState.STARTED
        self.events.extend(
            [
                {
                    "event": "INDEPENDENT_STOP_AVAILABLE",
                    "session_id": self.session_id,
                    "monotonic_seconds": monotonic_seconds,
                },
                {"event": "SUPERVISOR_STARTED", "monotonic_seconds": monotonic_seconds},
            ]
        )

    def attach(self, *, chart_id: int, monotonic_seconds: float) -> None:
        if self.state is not SupervisorState.STARTED:
            raise SupervisorBlocked("SUPERVISOR_NOT_READY_BEFORE_ATTACH")
        if self.start_monotonic is None or monotonic_seconds < self.start_monotonic:
            raise SupervisorBlocked("ATTACH_PRECEDES_SUPERVISOR_START")
        if self.chart_id is not None:
            raise SupervisorBlocked("DUPLICATE_MONITOR_ATTACH")
        self.chart_id = chart_id
        self.state = SupervisorState.ATTACHED
        self.events.append({"event": "MONITOR_ATTACHED", "chart_id": chart_id, "monotonic_seconds": monotonic_seconds})

    def heartbeat(self, *, monotonic_seconds: float) -> None:
        if self.state not in {SupervisorState.ATTACHED, SupervisorState.STOP_REQUESTED}:
            raise SupervisorBlocked("HEARTBEAT_OUTSIDE_ACTIVE_SESSION")
        if self.last_heartbeat_monotonic is not None and monotonic_seconds < self.last_heartbeat_monotonic:
            self._fail("MONOTONIC_CLOCK_ROLLOVER_OR_BACKWARD")
            return
        self.last_heartbeat_monotonic = monotonic_seconds

    def mark_self_stop_requested(self, *, monotonic_seconds: float) -> None:
        """Record the EA's ``ExpertRemove`` request without treating it as proof.

        The event is intentionally separate from ``EA_REMOVAL_CONFIRMED``.
        Only an independently observed removal may advance cleanup state.
        """

        if self.state not in {SupervisorState.ATTACHED, SupervisorState.STOP_REQUESTED}:
            raise SupervisorBlocked("SELF_STOP_REQUEST_OUTSIDE_ACTIVE_SESSION")
        if self.state is SupervisorState.ATTACHED:
            self.stop_requested_at = monotonic_seconds
            self.stop_reason = "EA_SELF_STOP_REQUESTED"
            self.state = SupervisorState.STOP_REQUESTED
        self.events.append(
            {
                "event": "SELF_STOP_REQUESTED",
                "session_id": self.session_id,
                "chart_id": self.chart_id,
                "monotonic_seconds": monotonic_seconds,
            }
        )

    def observe_sample(self, sample: PermissionSample, *, monotonic_seconds: float) -> StopDecision:
        if self.state not in {SupervisorState.ATTACHED, SupervisorState.STOP_REQUESTED}:
            raise SupervisorBlocked("SAMPLE_OUTSIDE_ACTIVE_SESSION")
        if sample.session_id != self.session_id or sample.chart_id != self.chart_id:
            return self._request_stop("SESSION_OR_CHART_IDENTITY_MISMATCH", monotonic_seconds)
        if self.last_sample_monotonic is not None:
            gap = monotonic_seconds - self.last_sample_monotonic
            if gap > self.max_gap_seconds:
                return self._request_stop("WITHIN_SESSION_SAMPLE_GAP_OVER_90_SECONDS", monotonic_seconds)
            if gap < 0:
                return self._request_stop("MONOTONIC_SAMPLE_ORDER_INVALID", monotonic_seconds)
        self.last_sample_monotonic = monotonic_seconds
        self.last_heartbeat_monotonic = monotonic_seconds
        self.sample_count += 1
        if sample.account_trade_allowed != 0 or sample.terminal_trade_allowed != 0:
            return self._request_stop("TRADING_PERMISSION_ENABLED", monotonic_seconds)
        if sample.terminal_connected != 1:
            return self._request_stop("TERMINAL_DISCONNECTED", monotonic_seconds)
        self.events.append({"event": "SAMPLE_ACCEPTED", "monotonic_seconds": monotonic_seconds})
        return self.tick(monotonic_seconds=monotonic_seconds)

    def tick(self, *, monotonic_seconds: float) -> StopDecision:
        if self.state not in {SupervisorState.ATTACHED, SupervisorState.STOP_REQUESTED}:
            raise SupervisorBlocked("TICK_OUTSIDE_ACTIVE_SESSION")
        if self.start_monotonic is None:
            raise SupervisorBlocked("SUPERVISOR_START_MISSING")
        elapsed = monotonic_seconds - self.start_monotonic
        if elapsed < 0:
            return self._request_stop("MONOTONIC_CLOCK_BACKWARD", monotonic_seconds)
        if elapsed >= self.max_seconds:
            if self.state is SupervisorState.STOP_REQUESTED:
                return self._fail("HARD_DEADLINE_600_SECONDS_CLEANUP_NOT_CONFIRMED")
            return self._request_stop("HARD_DEADLINE_600_SECONDS", monotonic_seconds)
        if elapsed >= self.soft_seconds and self.state is SupervisorState.ATTACHED:
            return self._request_stop("SOFT_DEADLINE_540_SECONDS", monotonic_seconds)
        return StopDecision(False, self.stop_reason, elapsed, self.state)

    def mark_ea_removed(self, *, monotonic_seconds: float) -> None:
        if self.state is not SupervisorState.STOP_REQUESTED:
            raise SupervisorBlocked("EA_REMOVAL_BEFORE_STOP_REQUEST")
        self.state = SupervisorState.EA_REMOVED
        self.events.append({"event": "EA_REMOVED_CONFIRMED", "monotonic_seconds": monotonic_seconds})

    def mark_chart_closed(self, *, monotonic_seconds: float) -> None:
        if self.state is not SupervisorState.EA_REMOVED:
            raise SupervisorBlocked("CHART_CLOSE_BEFORE_EA_REMOVAL")
        self.state = SupervisorState.CHART_CLOSED
        self.events.append({"event": "CHART_CLOSED_CONFIRMED", "monotonic_seconds": monotonic_seconds})

    def finish(self, *, monotonic_seconds: float) -> None:
        if self.state is not SupervisorState.CHART_CLOSED:
            raise SupervisorBlocked("FINISH_REQUIRES_EA_REMOVAL_AND_CHART_CLOSE")
        self.state = SupervisorState.COMPLETE
        self.events.append({"event": "SUPERVISOR_EXITED", "monotonic_seconds": monotonic_seconds})

    def _request_stop(self, reason: str, monotonic_seconds: float) -> StopDecision:
        if self.state is SupervisorState.STOP_REQUESTED:
            return StopDecision(True, self.stop_reason, monotonic_seconds - (self.start_monotonic or monotonic_seconds), self.state)
        if self.stop_callback is None or not self.independent_stop:
            return self._fail(f"STOP_CAPABILITY_UNAVAILABLE:{reason}")
        if self.chart_id is None:
            return self._fail(f"STOP_CHART_BINDING_MISSING:{reason}")
        accepted = bool(self.stop_callback(self.session_id, self.chart_id, reason))
        if not accepted:
            return self._fail(f"STOP_REQUEST_REJECTED:{reason}")
        self.stop_requested_at = monotonic_seconds
        self.stop_reason = reason
        self.state = SupervisorState.STOP_REQUESTED
        self.events.append({"event": "STOP_REQUESTED", "reason": reason, "monotonic_seconds": monotonic_seconds})
        return StopDecision(True, reason, monotonic_seconds - (self.start_monotonic or monotonic_seconds), self.state)

    def _fail(self, reason: str) -> StopDecision:
        self.state = SupervisorState.FAILED
        self.stop_reason = reason
        self.events.append({"event": "SUPERVISOR_FAILED", "reason": reason})
        return StopDecision(False, reason, 0.0, self.state)

    @property
    def stop_evidence(self) -> dict[str, bool]:
        """Return the four stop facts without collapsing them into one flag."""

        events = {str(event.get("event")) for event in self.events}
        return {
            "SELF_STOP_REQUESTED": "SELF_STOP_REQUESTED" in events,
            "EA_REMOVAL_CONFIRMED": "EA_REMOVED_CONFIRMED" in events,
            "CHART_CLOSURE_CONFIRMED": "CHART_CLOSED_CONFIRMED" in events,
            "INDEPENDENT_STOP_AVAILABLE": "INDEPENDENT_STOP_AVAILABLE" in events,
        }


__all__ = ["SessionSupervisor", "StopCallback", "StopDecision", "SupervisorBlocked", "SupervisorState"]
