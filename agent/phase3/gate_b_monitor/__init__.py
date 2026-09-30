"""Fail-closed, offline-first Gate B permission-monitor automation.

The package contains only orchestration contracts, the reviewed V2 MQL5 source,
evidence collection/evaluation helpers, and offline tests.  It does not launch
MT5 by itself and has no trading or credential APIs.
"""

from .models import (
    HARD_DEADLINE_SECONDS,
    MAX_WITHIN_SESSION_GAP_SECONDS,
    SAMPLE_INTERVAL_SECONDS,
    SOFT_STOP_SECONDS,
    ApprovalScope,
    CapabilityMatrix,
    PermissionSample,
)
from .compiler import CompileBlocked, CompileResult, CompileSpec
from .controller import ControllerPreflight, DedicatedAcceptanceController, DedicatedAcceptancePlan
from .process_supervisor import (
    IdentityCheck,
    IndependentSupervisorRunner,
    IndependentSupervisorSpec,
    OwnedProcessController,
    ProcessIdentity,
    ProcessSnapshot,
    ProcessStopBlocked,
    StopReceipt,
    SupervisorTick,
)
from .provisioning import DedicatedTerminalSpec, ProvisionValidation, ProvisioningBlocked
from .startup import StartupConfigBlocked, StartupConfigResult, StartupConfigSpec

__all__ = [
    "ApprovalScope",
    "CapabilityMatrix",
    "HARD_DEADLINE_SECONDS",
    "MAX_WITHIN_SESSION_GAP_SECONDS",
    "PermissionSample",
    "SAMPLE_INTERVAL_SECONDS",
    "SOFT_STOP_SECONDS",
    "CompileBlocked",
    "CompileResult",
    "CompileSpec",
    "ControllerPreflight",
    "DedicatedAcceptanceController",
    "DedicatedAcceptancePlan",
    "DedicatedTerminalSpec",
    "IdentityCheck",
    "IndependentSupervisorRunner",
    "IndependentSupervisorSpec",
    "OwnedProcessController",
    "ProcessIdentity",
    "ProcessSnapshot",
    "ProcessStopBlocked",
    "ProvisionValidation",
    "ProvisioningBlocked",
    "StartupConfigBlocked",
    "StartupConfigResult",
    "StartupConfigSpec",
    "StopReceipt",
    "SupervisorTick",
]
