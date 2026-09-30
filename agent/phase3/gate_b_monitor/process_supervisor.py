"""Exact-process ownership and bounded stop controller for isolated MT5.

The controller is deliberately generic and is not wired to the shared V26
terminal.  It verifies PID, executable path, creation token, Windows session,
acceptance session and data-root identity before any emergency termination.
Offline tests use harmless dummy processes and injected inspectors.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


class ProcessStopBlocked(RuntimeError):
    """Process ownership or stop authorization cannot be proven."""


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    executable_path: Path
    creation_token: str
    windows_session_id: str
    acceptance_session_id: str
    data_root: Path


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    executable_path: Path
    creation_token: str
    windows_session_id: str
    acceptance_session_id: str | None
    data_root: Path | None
    alive: bool = True
    command_line: str | None = None


@dataclass(frozen=True)
class IdentityCheck:
    status: str
    reasons: tuple[str, ...]
    snapshot: ProcessSnapshot | None


@dataclass(frozen=True)
class StopReceipt:
    status: str
    method: str
    reasons: tuple[str, ...] = ()
    verified_exit: bool = False


@dataclass(frozen=True)
class IndependentSupervisorSpec:
    session_id: str
    soft_stop_seconds: float = 540.0
    hard_deadline_seconds: float = 600.0
    max_heartbeat_gap_seconds: float = 90.0
    grace_seconds: float = 5.0


@dataclass(frozen=True)
class SupervisorTick:
    status: str
    reason: str | None
    elapsed_seconds: float
    stop_receipt: StopReceipt | None = None


class IndependentSupervisorRunner:
    """A standalone supervisor state machine independent of Codex chat."""

    def __init__(
        self,
        spec: IndependentSupervisorSpec,
        controller: "OwnedProcessController",
        *,
        graceful_requester: Callable[[ProcessIdentity], bool],
    ) -> None:
        self.spec = spec
        self.controller = controller
        self.graceful_requester = graceful_requester
        self.started_at: float | None = None
        self.last_heartbeat: float | None = None
        self.stop_reason: str | None = None
        self.events: list[dict[str, Any]] = []
        self.state = "NEW"

    def start(self, *, monotonic_seconds: float) -> None:
        if self.state != "NEW":
            raise ProcessStopBlocked("SUPERVISOR_START_NOT_EXACTLY_ONCE")
        self.started_at = monotonic_seconds
        self.last_heartbeat = monotonic_seconds
        self.state = "RUNNING"
        self.events.append({"event": "INDEPENDENT_SUPERVISOR_STARTED", "monotonic_seconds": monotonic_seconds})

    def heartbeat(self, *, monotonic_seconds: float) -> None:
        if self.state != "RUNNING":
            raise ProcessStopBlocked("HEARTBEAT_OUTSIDE_SUPERVISOR_SESSION")
        if self.last_heartbeat is not None and monotonic_seconds < self.last_heartbeat:
            self.state = "FAILED"
            raise ProcessStopBlocked("SUPERVISOR_MONOTONIC_CLOCK_BACKWARD")
        self.last_heartbeat = monotonic_seconds
        self.events.append({"event": "SUPERVISOR_HEARTBEAT", "monotonic_seconds": monotonic_seconds})

    def _request_graceful(self, reason: str) -> StopReceipt:
        if self.stop_reason is not None:
            return StopReceipt("REQUESTED", "GRACEFUL_REQUEST", (self.stop_reason,), False)
        self.stop_reason = reason
        receipt = self.controller.request_graceful_stop(self.graceful_requester)
        self.events.append({"event": "SUPERVISOR_STOP_DECISION", "reason": reason, "status": receipt.status})
        if receipt.status == "BLOCKED":
            self.state = "FAILED"
        return receipt

    def tick(self, *, monotonic_seconds: float) -> SupervisorTick:
        if self.state != "RUNNING" or self.started_at is None or self.last_heartbeat is None:
            raise ProcessStopBlocked("SUPERVISOR_NOT_RUNNING")
        elapsed = monotonic_seconds - self.started_at
        if elapsed < 0:
            self.state = "FAILED"
            return SupervisorTick("FAILED", "SUPERVISOR_MONOTONIC_CLOCK_BACKWARD", elapsed)
        observed = self.controller.verify_identity()
        if observed.snapshot is None or not observed.snapshot.alive:
            self.controller.state = "TERMINATED"
            self.state = "COMPLETE"
            return SupervisorTick("COMPLETE", "PROCESS_TERMINATED", elapsed)
        if monotonic_seconds - self.last_heartbeat > self.spec.max_heartbeat_gap_seconds:
            receipt = self._request_graceful("HEARTBEAT_GAP_OVER_90_SECONDS")
            return SupervisorTick("STOP_REQUESTED", "HEARTBEAT_GAP_OVER_90_SECONDS", elapsed, receipt)
        if elapsed >= self.spec.hard_deadline_seconds:
            if self.controller.state == "TERMINATED":
                self.state = "COMPLETE"
                return SupervisorTick("COMPLETE", "PROCESS_TERMINATED", elapsed)
            receipt = self.controller.emergency_stop()
            self.state = "COMPLETE" if receipt.status == "REQUESTED" else "FAILED"
            return SupervisorTick("EMERGENCY_STOP" if receipt.status == "REQUESTED" else "FAILED", "HARD_DEADLINE_600_SECONDS", elapsed, receipt)
        if elapsed >= self.spec.soft_stop_seconds:
            receipt = self._request_graceful("SOFT_DEADLINE_540_SECONDS")
            return SupervisorTick("STOP_REQUESTED", "SOFT_DEADLINE_540_SECONDS", elapsed, receipt)
        return SupervisorTick("RUNNING", None, elapsed)

    def run_until_terminated(self, *, start_monotonic: float, tick_monotonic: Callable[[], float], poll_seconds: float = 0.25, max_ticks: int = 4000) -> SupervisorTick:
        """Run as a local process loop; bounded for safety and testability."""

        self.start(monotonic_seconds=start_monotonic)
        for _ in range(max_ticks):
            now = tick_monotonic()
            tick = self.tick(monotonic_seconds=now)
            if self.controller.state == "TERMINATED":
                self.state = "COMPLETE"
                return SupervisorTick("COMPLETE", "PROCESS_TERMINATED", now - start_monotonic, tick.stop_receipt)
            if tick.status in {"FAILED", "EMERGENCY_STOP"}:
                return tick
            time.sleep(poll_seconds)
        self.state = "FAILED"
        return SupervisorTick("FAILED", "SUPERVISOR_LOOP_BOUND_EXCEEDED", tick_monotonic() - start_monotonic)


ProcessInspector = Callable[[int], ProcessSnapshot | None]
ProcessTerminator = Callable[[int], bool]


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _same_path(left: Path, right: Path) -> bool:
    return str(_resolved(left)).casefold() == str(_resolved(right)).casefold()


def _is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        _resolved(path).relative_to(_resolved(parent))
        return True
    except ValueError:
        return False


class OwnedProcessController:
    """Own one process identity and fail closed on every mismatch."""

    def __init__(
        self,
        identity: ProcessIdentity,
        *,
        inspector: ProcessInspector,
        terminator: ProcessTerminator,
        protected_roots: Iterable[Path] = (),
        emergency_authorized: bool = False,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.identity = identity
        self.inspector = inspector
        self.terminator = terminator
        self.protected_roots = tuple(_resolved(item) for item in protected_roots)
        self.emergency_authorized = emergency_authorized
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.events: list[dict[str, Any]] = []
        self.state = "OWNED"
        self._reject_protected_target()

    def _reject_protected_target(self) -> None:
        for protected in self.protected_roots:
            if _is_same_or_child(self.identity.executable_path, protected) or _is_same_or_child(self.identity.data_root, protected):
                raise ProcessStopBlocked("PROTECTED_PROCESS_OR_DATA_ROOT")

    def verify_identity(self) -> IdentityCheck:
        snapshot = self.inspector(self.identity.pid)
        reasons: list[str] = []
        if snapshot is None or not snapshot.alive:
            reasons.append("PROCESS_NOT_ALIVE")
        else:
            if snapshot.pid != self.identity.pid:
                reasons.append("PID_MISMATCH")
            if not _same_path(snapshot.executable_path, self.identity.executable_path):
                reasons.append("EXECUTABLE_PATH_MISMATCH")
            if snapshot.creation_token != self.identity.creation_token:
                reasons.append("PROCESS_CREATION_TOKEN_MISMATCH")
            if snapshot.windows_session_id != self.identity.windows_session_id:
                reasons.append("WINDOWS_SESSION_MISMATCH")
            if snapshot.acceptance_session_id != self.identity.acceptance_session_id:
                reasons.append("ACCEPTANCE_SESSION_MISMATCH")
            if snapshot.data_root is None or not _same_path(snapshot.data_root, self.identity.data_root):
                reasons.append("DATA_ROOT_MISMATCH_OR_UNKNOWN")
        result = IdentityCheck("PASS" if not reasons else "BLOCKED", tuple(reasons), snapshot)
        self.events.append({"event": "PROCESS_IDENTITY_CHECK", "status": result.status, "reasons": list(result.reasons)})
        return result

    def request_graceful_stop(self, requester: Callable[[ProcessIdentity], bool]) -> StopReceipt:
        check = self.verify_identity()
        if not check.status == "PASS":
            self.state = "FAILED"
            return StopReceipt("BLOCKED", "GRACEFUL_REQUEST", check.reasons, False)
        try:
            accepted = bool(requester(self.identity))
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.state = "FAILED"
            return StopReceipt("BLOCKED", "GRACEFUL_REQUEST", (f"REQUESTER_ERROR:{type(exc).__name__}",), False)
        if not accepted:
            self.events.append({"event": "GRACEFUL_STOP_REJECTED"})
            return StopReceipt("REJECTED", "GRACEFUL_REQUEST", ("GRACEFUL_STOP_REJECTED",), False)
        self.state = "GRACEFUL_STOP_REQUESTED"
        self.events.append({"event": "GRACEFUL_STOP_REQUESTED", "pid": self.identity.pid})
        return StopReceipt("REQUESTED", "GRACEFUL_REQUEST", verified_exit=False)

    def wait_for_exit(self, *, timeout_seconds: float, poll_seconds: float = 0.05) -> StopReceipt:
        deadline = self.monotonic() + timeout_seconds
        while self.monotonic() <= deadline:
            check = self.verify_identity()
            if check.snapshot is None or not check.snapshot.alive:
                self.state = "TERMINATED"
                self.events.append({"event": "PROCESS_TERMINATION_CONFIRMED", "method": "OBSERVATION"})
                return StopReceipt("PASS", "OBSERVATION", verified_exit=True)
            self.sleeper(poll_seconds)
        self.events.append({"event": "PROCESS_EXIT_TIMEOUT", "timeout_seconds": timeout_seconds})
        return StopReceipt("TIMEOUT", "OBSERVATION", ("PROCESS_EXIT_TIMEOUT",), False)

    def emergency_stop(self) -> StopReceipt:
        if not self.emergency_authorized:
            self.state = "FAILED"
            return StopReceipt("BLOCKED", "EMERGENCY_TERMINATION", ("EMERGENCY_STOP_NOT_AUTHORIZED",), False)
        check = self.verify_identity()
        if check.status != "PASS":
            self.state = "FAILED"
            return StopReceipt("BLOCKED", "EMERGENCY_TERMINATION", check.reasons, False)
        try:
            accepted = bool(self.terminator(self.identity.pid))
        except Exception as exc:  # pragma: no cover - defensive boundary
            accepted = False
            reason = f"TERMINATOR_ERROR:{type(exc).__name__}"
        else:
            reason = "EMERGENCY_TERMINATION_REQUESTED" if accepted else "EMERGENCY_TERMINATION_REJECTED"
        self.events.append({"event": reason, "pid": self.identity.pid})
        if not accepted:
            self.state = "FAILED"
            return StopReceipt("FAILED", "EMERGENCY_TERMINATION", (reason,), False)
        self.state = "EMERGENCY_STOP_REQUESTED"
        return StopReceipt("REQUESTED", "EMERGENCY_TERMINATION", (reason,), False)

    def stop_with_grace(
        self,
        requester: Callable[[ProcessIdentity], bool],
        *,
        grace_seconds: float,
        poll_seconds: float = 0.05,
    ) -> StopReceipt:
        graceful = self.request_graceful_stop(requester)
        if graceful.status == "BLOCKED":
            return graceful
        observed = self.wait_for_exit(timeout_seconds=grace_seconds, poll_seconds=poll_seconds)
        if observed.status == "PASS":
            return StopReceipt("PASS", "GRACEFUL_REQUEST", observed.reasons, True)
        emergency = self.emergency_stop()
        if emergency.status != "REQUESTED":
            return emergency
        return self.wait_for_exit(timeout_seconds=grace_seconds, poll_seconds=poll_seconds)


def _filetime_token(value: Any) -> str:
    return str((int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime))


def query_windows_process(
    pid: int,
    *,
    acceptance_session_id: str,
    data_root: Path,
    command_line: str | None = None,
) -> ProcessSnapshot | None:
    """Read exact native identity for one PID; never terminates it."""

    if os.name != "nt":
        raise ProcessStopBlocked("WINDOWS_PROCESS_QUERY_REQUIRED")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_query_limited_information = 0x1000
    synchronize = 0x00100000
    handle = kernel32.OpenProcess(process_query_limited_information | synchronize, False, int(pid))
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]

        created = FILETIME()
        exited = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        windows_session = ctypes.c_uint32()
        if not kernel32.ProcessIdToSessionId(int(pid), ctypes.byref(windows_session)):
            return None
        return ProcessSnapshot(
            pid=int(pid),
            executable_path=Path(buffer.value),
            creation_token=_filetime_token(created),
            windows_session_id=str(windows_session.value),
            acceptance_session_id=acceptance_session_id,
            data_root=_resolved(data_root),
            alive=True,
            command_line=command_line,
        )
    finally:
        kernel32.CloseHandle(handle)


def launch_authorized_process(
    command: Iterable[str],
    *,
    executable_path: Path,
    data_root: Path,
    acceptance_session_id: str,
    protected_roots: Iterable[Path] = (),
    authorized: bool = False,
) -> tuple[subprocess.Popen[bytes], ProcessIdentity]:
    """Launch one future process only after explicit authorization.

    This helper is not called by the offline PRD workflow.  It rejects common
    credential/server command-line keys and does not accept shell execution.
    """

    if not authorized:
        raise ProcessStopBlocked("PROCESS_LAUNCH_REQUIRES_APPROVAL_A")
    args = tuple(str(item) for item in command)
    if not args or args[0] != str(executable_path):
        raise ProcessStopBlocked("PROCESS_EXECUTABLE_COMMAND_MISMATCH")
    lowered = " ".join(args).lower()
    if any(token in lowered for token in ("/login", "/password", "/server", "--login", "--password", "--server")):
        raise ProcessStopBlocked("CREDENTIAL_OR_SERVER_COMMAND_ARGUMENT_FORBIDDEN")
    if os.name != "nt":
        raise ProcessStopBlocked("WINDOWS_PROCESS_LAUNCH_REQUIRED")
    process = subprocess.Popen(args, cwd=str(executable_path.parent), shell=False, close_fds=True)
    try:
        snapshot = query_windows_process(
            process.pid,
            acceptance_session_id=acceptance_session_id,
            data_root=data_root,
            command_line=" ".join(args),
        )
        if snapshot is None or not _same_path(snapshot.executable_path, executable_path):
            raise ProcessStopBlocked("NATIVE_PROCESS_IDENTITY_QUERY_FAILED")
        identity = ProcessIdentity(
            pid=snapshot.pid,
            executable_path=snapshot.executable_path,
            creation_token=snapshot.creation_token,
            windows_session_id=snapshot.windows_session_id,
            acceptance_session_id=acceptance_session_id,
            data_root=_resolved(data_root),
        )
        return process, identity
    except Exception:
        try:
            process.terminate()
            process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            process.kill()
        raise


__all__ = [
    "IdentityCheck",
    "IndependentSupervisorRunner",
    "IndependentSupervisorSpec",
    "OwnedProcessController",
    "ProcessIdentity",
    "ProcessSnapshot",
    "ProcessStopBlocked",
    "StopReceipt",
    "SupervisorTick",
    "launch_authorized_process",
    "query_windows_process",
]
