"""Fail-closed planning and validation for a dedicated MT5 acceptance root.

This module deliberately does not install MT5 or create the proposed
installation.  It validates a proposed target without mutating it and keeps
the actual provisioning action behind an explicit authorization boundary.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_DEDICATED_ROOT = Path(r"D:\Trading\MT5-GateB-Acceptance")
DEFAULT_DEDICATED_EVIDENCE_ROOT = Path(r"D:\Trading\MT5-GateB-Acceptance-Evidence")
DEFAULT_SHARED_INSTALL_ROOT = Path(r"D:\Trading\MT5-V26")
DEFAULT_REQUIRED_FREE_BYTES = 512 * 1024 * 1024


class ProvisioningBlocked(RuntimeError):
    """Provisioning is not safe, not authorized, or not proven."""


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_same_or_child(path: Path, parent: Path) -> bool:
    try:
        _resolved(path).relative_to(_resolved(parent))
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class DedicatedTerminalSpec:
    """Identity and separation requirements for one future acceptance root."""

    install_root: Path = DEFAULT_DEDICATED_ROOT
    data_root: Path = DEFAULT_DEDICATED_ROOT
    evidence_root: Path = DEFAULT_DEDICATED_EVIDENCE_ROOT
    existing_install_root: Path = DEFAULT_SHARED_INSTALL_ROOT
    existing_data_root: Path | None = None
    existing_common_root: Path | None = None
    dedicated_common_root: Path | None = None
    repository_root: Path | None = None
    required_free_bytes: int = DEFAULT_REQUIRED_FREE_BYTES


@dataclass(frozen=True)
class ProvisionValidation:
    status: str
    reasons: tuple[str, ...]
    checks: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def _row_path(row: Mapping[str, Any], *keys: str) -> Path | None:
    for key in keys:
        value = row.get(key)
        if value:
            return _resolved(Path(str(value)))
    return None


def validate_provision_target(
    spec: DedicatedTerminalSpec,
    *,
    process_rows: Iterable[Mapping[str, Any]] = (),
) -> ProvisionValidation:
    """Validate a proposed target without creating, deleting or copying files."""

    install_root = _resolved(spec.install_root)
    data_root = _resolved(spec.data_root)
    evidence_root = _resolved(spec.evidence_root)
    shared_install = _resolved(spec.existing_install_root)
    shared_data = _resolved(spec.existing_data_root) if spec.existing_data_root else None
    shared_common = _resolved(spec.existing_common_root) if spec.existing_common_root else None
    dedicated_common = _resolved(spec.dedicated_common_root) if spec.dedicated_common_root else None
    repository_root = _resolved(spec.repository_root) if spec.repository_root else None
    reasons: list[str] = []
    checks: dict[str, Any] = {
        "install_root": str(install_root),
        "data_root": str(data_root),
        "evidence_root": str(evidence_root),
        "existing_install_root": str(shared_install),
        "existing_data_root": str(shared_data) if shared_data else None,
        "existing_common_root": str(shared_common) if shared_common else None,
        "dedicated_common_root": str(dedicated_common) if dedicated_common else None,
        "mutated": False,
    }

    if install_root == shared_install or _is_same_or_child(install_root, shared_install) or _is_same_or_child(shared_install, install_root):
        reasons.append("DEDICATED_INSTALL_OVERLAPS_SHARED_V26")
    if shared_data and (data_root == shared_data or _is_same_or_child(data_root, shared_data) or _is_same_or_child(shared_data, data_root)):
        reasons.append("DEDICATED_DATA_ROOT_OVERLAPS_SHARED_V26")
    if evidence_root == install_root or _is_same_or_child(evidence_root, install_root):
        reasons.append("EVIDENCE_ROOT_INSIDE_DEDICATED_INSTALL")
    if evidence_root == data_root or _is_same_or_child(evidence_root, data_root):
        reasons.append("EVIDENCE_ROOT_INSIDE_DEDICATED_DATA_ROOT")
    if repository_root and (evidence_root == repository_root or _is_same_or_child(evidence_root, repository_root)):
        reasons.append("EVIDENCE_ROOT_INSIDE_SOURCE_CHECKOUT")

    checks["install_destination_exists"] = install_root.exists()
    checks["data_destination_exists"] = data_root.exists()
    if install_root.exists():
        reasons.append("DEDICATED_INSTALL_DESTINATION_EXISTS_NO_OVERWRITE")
    if data_root.exists() and data_root != install_root:
        reasons.append("DEDICATED_DATA_DESTINATION_EXISTS_NO_OVERWRITE")

    parent = install_root.parent
    checks["parent_exists"] = parent.exists()
    checks["parent_writable"] = bool(parent.exists() and os.access(parent, os.W_OK))
    if not parent.exists():
        reasons.append("DEDICATED_PARENT_MISSING")
    elif not os.access(parent, os.W_OK):
        reasons.append("DEDICATED_PARENT_NOT_WRITABLE")
    else:
        try:
            usage = shutil.disk_usage(parent)
            checks["free_bytes"] = usage.free
            checks["required_free_bytes"] = spec.required_free_bytes
            if usage.free < spec.required_free_bytes:
                reasons.append("INSUFFICIENT_FREE_SPACE")
        except OSError:
            checks["free_bytes"] = None
            reasons.append("DISK_SPACE_CHECK_FAILED")

    if dedicated_common is None:
        reasons.append("DEDICATED_COMMON_ROOT_NOT_SPECIFIED")
    elif shared_common and dedicated_common == shared_common:
        reasons.append("FILE_COMMON_COLLISION_WITH_SHARED_ROOT")

    process_conflicts: list[dict[str, Any]] = []
    for row in process_rows:
        executable = _row_path(row, "ExecutablePath", "executable_path", "Path")
        command_line = str(row.get("CommandLine", row.get("command_line", "")))
        if executable and (_is_same_or_child(executable, install_root) or _is_same_or_child(executable, data_root)):
            process_conflicts.append({"pid": row.get("ProcessId", row.get("pid")), "executable": str(executable)})
        elif str(install_root).lower() in command_line.lower() or str(data_root).lower() in command_line.lower():
            process_conflicts.append({"pid": row.get("ProcessId", row.get("pid")), "command_line": command_line})
    checks["process_conflicts"] = process_conflicts
    if process_conflicts:
        reasons.append("DEDICATED_TARGET_ALREADY_HAS_PROCESS")

    return ProvisionValidation("PASS" if not reasons else "BLOCKED", tuple(reasons), checks)


def provision_empty_layout(
    spec: DedicatedTerminalSpec,
    *,
    authorized: bool = False,
    process_rows: Iterable[Mapping[str, Any]] = (),
) -> ProvisionValidation:
    """Create only an empty layout after explicit authorization.

    This does not install MT5 or copy an executable.  It is intentionally not
    called by the offline workflow; Approval A and an official installer are
    required before any real provisioning.
    """

    if not authorized:
        raise ProvisioningBlocked("PROVISIONING_REQUIRES_APPROVAL_A")
    validation = validate_provision_target(spec, process_rows=process_rows)
    if not validation.passed:
        raise ProvisioningBlocked(";".join(validation.reasons))
    try:
        spec.install_root.mkdir(parents=False, exist_ok=False)
        if _resolved(spec.data_root) != _resolved(spec.install_root):
            spec.data_root.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise ProvisioningBlocked(f"LAYOUT_CREATE_FAILED:{type(exc).__name__}") from exc
    return ProvisionValidation(
        "PASS",
        (),
        {**validation.checks, "layout_created": True, "mutated": True},
    )


__all__ = [
    "DEFAULT_DEDICATED_ROOT",
    "DEFAULT_DEDICATED_EVIDENCE_ROOT",
    "DEFAULT_SHARED_INSTALL_ROOT",
    "DedicatedTerminalSpec",
    "ProvisionValidation",
    "ProvisioningBlocked",
    "provision_empty_layout",
    "validate_provision_target",
]
