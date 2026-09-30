"""Dedicated Gate B acceptance controller plan.

This composes the existing orchestrator, provisioner, startup and compile
contracts.  It prepares and validates a future run but refuses real launch or
attachment until the explicit approval boundaries are satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .compiler import CompileBlocked, CompileSpec, build_compile_command, sha256_file
from .orchestrator import AutomationBlocked
from .provisioning import DedicatedTerminalSpec, ProvisionValidation, validate_provision_target
from .startup import StartupConfigBlocked, StartupConfigSpec, build_terminal_command, render_startup_config


@dataclass(frozen=True)
class DedicatedAcceptancePlan:
    provision: DedicatedTerminalSpec
    startup: StartupConfigSpec
    compile: CompileSpec
    source_path: Path
    source_sha256: str
    evidence_root: Path
    protected_v26_roots: tuple[Path, ...]


@dataclass(frozen=True)
class ControllerPreflight:
    status: str
    statuses: dict[str, str]
    reasons: tuple[str, ...]
    commands: dict[str, tuple[str, ...] | None]
    provision: ProvisionValidation


class DedicatedAcceptanceController:
    """Prepare one immutable plan; no implicit runtime or fallback exists."""

    def __init__(self, plan: DedicatedAcceptancePlan) -> None:
        self.plan = plan

    def preflight(self, *, process_rows: Iterable[Mapping[str, Any]] = ()) -> ControllerPreflight:
        reasons: list[str] = []
        statuses: dict[str, str] = {}
        commands: dict[str, tuple[str, ...] | None] = {"compile": None, "terminal": None}

        provision = validate_provision_target(self.plan.provision, process_rows=process_rows)
        statuses["INSTALLATION_ISOLATION"] = "BLOCKED"
        statuses["DATA_ROOT_ISOLATION"] = "BLOCKED"
        statuses["FILE_COMMON_ISOLATION"] = "BLOCKED"
        reasons.extend(provision.reasons)
        reasons.append("DEDICATED_INSTALLATION_RUNTIME_PROOF_REQUIRED")
        reasons.append("DEDICATED_DATA_ROOT_RUNTIME_PROOF_REQUIRED")
        reasons.append("FILE_COMMON_RUNTIME_PROOF_REQUIRED")

        if not self.plan.source_path.is_file():
            statuses["SOURCE_IDENTITY"] = "BLOCKED"
            reasons.append("MONITOR_SOURCE_MISSING")
        else:
            actual_source_sha = sha256_file(self.plan.source_path)
            statuses["SOURCE_IDENTITY"] = "PASS" if actual_source_sha == self.plan.source_sha256 else "FAIL"
            if actual_source_sha != self.plan.source_sha256:
                reasons.append("MONITOR_SOURCE_SHA256_MISMATCH")

        try:
            render_startup_config(self.plan.startup)
            commands["terminal"] = build_terminal_command(self.plan.startup)
            statuses["STARTUP_CONFIG_VALID"] = "PASS"
        except StartupConfigBlocked as exc:
            statuses["STARTUP_CONFIG_VALID"] = "BLOCKED"
            reasons.append(str(exc))

        try:
            commands["compile"] = build_compile_command(self.plan.compile)
            if self.plan.compile.metaeditor_exe.is_file():
                statuses["AUTOMATED_COMPILATION"] = "READY_NOT_EXECUTED"
            else:
                statuses["AUTOMATED_COMPILATION"] = "BLOCKED"
                reasons.append("METAEDITOR_EXECUTABLE_NOT_VERIFIED")
        except CompileBlocked as exc:
            statuses["AUTOMATED_COMPILATION"] = "BLOCKED"
            reasons.append(str(exc))

        statuses["AUTOMATED_LAUNCH"] = "BLOCKED"
        statuses["AUTOMATED_ATTACH"] = "BLOCKED"
        statuses["INDEPENDENT_STOP"] = "BLOCKED"
        statuses["REAL_MT5_ACCEPTANCE"] = "NOT_RUN"
        reasons.append("AUTHORIZED_MT5_CONTROL_SURFACE_UNAVAILABLE")
        reasons.append("APPROVAL_A_REQUIRED_BEFORE_RUNTIME")
        overall = "PASS" if not reasons else "BLOCKED"
        return ControllerPreflight(overall, statuses, tuple(dict.fromkeys(reasons)), commands, provision)

    def render_offline_startup_config(self) -> str:
        return render_startup_config(self.plan.startup)

    def launch(self, *, authorized: bool = False) -> None:
        if not authorized:
            raise AutomationBlocked("LAUNCH_REQUIRES_APPROVAL_A")
        raise AutomationBlocked("NATIVE_DEDICATED_MT5_CONTROL_SURFACE_NOT_IMPLEMENTED")

    def attach(self, *, authorized: bool = False) -> None:
        if not authorized:
            raise AutomationBlocked("ATTACH_REQUIRES_APPROVAL_B")
        raise AutomationBlocked("NATIVE_CHART_ATTACH_SURFACE_NOT_IMPLEMENTED")


__all__ = [
    "ControllerPreflight",
    "DedicatedAcceptanceController",
    "DedicatedAcceptancePlan",
]
