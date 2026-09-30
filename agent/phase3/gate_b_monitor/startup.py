"""Safe startup configuration generation for a future isolated MT5 run.

MetaTrader's official startup contract is `/portable`, `/config:<file>` and a
`[StartUp]` section containing `Expert`, `Symbol`, `Period` and optionally
`ExpertParameters`.  This module generates a credential-free configuration and
never launches the terminal.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


EXPECTED_SYMBOL = "BTCUSD"
EXPECTED_PERIOD = "H1"
_FORBIDDEN_CONFIG_KEYS = {
    "login",
    "password",
    "server",
    "proxylogin",
    "proxypassword",
    "mql5login",
    "mql5password",
}
_PRODUCTION_NAMES = {"mentorrsi", "phase3canonicalcandidate", "mentor_rsi_mtf"}


class StartupConfigBlocked(RuntimeError):
    """Startup configuration is unsafe, ambiguous or not authorized."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_rel(value: str) -> str:
    return value.replace("/", "\\").strip("\\")


@dataclass(frozen=True)
class StartupConfigSpec:
    terminal_exe: Path
    install_root: Path
    data_root: Path
    config_path: Path
    monitor_ex5: Path
    monitor_expert_relative: str = r"Advisors\PR6_ReadOnlyPermissionMonitor_V2.ex5"
    expert_parameters_relative: str | None = None
    symbol: str = EXPECTED_SYMBOL
    period: str = EXPECTED_PERIOD
    portable: bool = True
    allow_live_trading: bool = False
    allow_dll_import: bool = False
    expert_enabled: bool = True


@dataclass(frozen=True)
class StartupConfigResult:
    status: str
    config_path: Path
    config_sha256: str | None
    command: tuple[str, ...] | None
    reasons: tuple[str, ...] = ()
    values: dict[str, str] = field(default_factory=dict)


def _relative_expert_path(spec: StartupConfigSpec) -> str:
    return _normalize_rel(spec.monitor_expert_relative)


def _validate_spec(spec: StartupConfigSpec) -> list[str]:
    reasons: list[str] = []
    if spec.symbol != EXPECTED_SYMBOL:
        reasons.append("STARTUP_SYMBOL_MISMATCH")
    if spec.period != EXPECTED_PERIOD:
        reasons.append("STARTUP_PERIOD_MISMATCH")
    if not spec.portable:
        reasons.append("PORTABLE_MODE_REQUIRED_FOR_DEDICATED_PLAN")
    if spec.allow_live_trading:
        reasons.append("LIVE_TRADING_MUST_BE_DISABLED")
    if spec.allow_dll_import:
        reasons.append("DLL_IMPORT_MUST_BE_DISABLED")
    if not spec.expert_enabled:
        reasons.append("MONITOR_EA_MUST_BE_ENABLED")
    if not spec.terminal_exe.is_absolute() or not spec.install_root.is_absolute() or not spec.data_root.is_absolute():
        reasons.append("STARTUP_PATHS_MUST_BE_ABSOLUTE")
    if spec.monitor_ex5.is_file():
        expert_path = _normalize_rel(spec.monitor_expert_relative).lower()
        if not expert_path.endswith(".ex5"):
            reasons.append("MONITOR_EX5_RELATIVE_PATH_REQUIRED")
    else:
        reasons.append("MONITOR_EX5_MISSING")
    expert_lower = _relative_expert_path(spec).lower().replace("_", "")
    if any(name in expert_lower for name in _PRODUCTION_NAMES):
        reasons.append("PRODUCTION_EA_PATH_FORBIDDEN")
    try:
        spec.monitor_ex5.resolve(strict=False).relative_to(spec.data_root.resolve(strict=False))
    except ValueError:
        reasons.append("MONITOR_EX5_OUTSIDE_DEDICATED_DATA_ROOT")
    return reasons


def render_startup_config(spec: StartupConfigSpec) -> str:
    """Render only non-secret startup values; no account/server is included."""

    reasons = _validate_spec(spec)
    if reasons:
        raise StartupConfigBlocked(";".join(reasons))
    lines = [
        "; PR6 dedicated Gate B acceptance; generated offline; no credentials",
        "[Experts]",
        "AllowLiveTrading=0",
        "AllowDllImport=0",
        "Enabled=1",
        "Account=0",
        "Profile=0",
        "",
        "[StartUp]",
        f"Expert={_relative_expert_path(spec)}",
        f"Symbol={spec.symbol}",
        f"Period={spec.period}",
    ]
    if spec.expert_parameters_relative:
        parameter_path = _normalize_rel(spec.expert_parameters_relative)
        if any(token in parameter_path.lower() for token in ("login", "password", "server")):
            raise StartupConfigBlocked("CREDENTIAL_OR_SERVER_REFERENCE_IN_EXPERT_PARAMETERS")
        lines.append(f"ExpertParameters={parameter_path}")
    return "\n".join(lines) + "\n"


def write_startup_config(spec: StartupConfigSpec, *, overwrite: bool = False) -> StartupConfigResult:
    """Write a new config atomically; never overwrite by default."""

    if spec.config_path.exists() and not overwrite:
        raise StartupConfigBlocked("STARTUP_CONFIG_EXISTS_NO_OVERWRITE")
    content = render_startup_config(spec)
    spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    if spec.config_path.exists() and overwrite:
        raise StartupConfigBlocked("STARTUP_CONFIG_OVERWRITE_REQUIRES_EXPLICIT_NEW_ARTIFACT")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=spec.config_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    os.replace(temporary, spec.config_path)
    return StartupConfigResult(
        status="PASS",
        config_path=spec.config_path,
        config_sha256=sha256_file(spec.config_path),
        command=build_terminal_command(spec),
        values={"Symbol": spec.symbol, "Period": spec.period, "Expert": _relative_expert_path(spec)},
    )


def build_terminal_command(spec: StartupConfigSpec) -> tuple[str, ...]:
    reasons = _validate_spec(spec)
    if reasons:
        raise StartupConfigBlocked(";".join(reasons))
    command: list[str] = [str(spec.terminal_exe)]
    if spec.portable:
        command.append("/portable")
    command.append(f"/config:{spec.config_path}")
    command_text = " ".join(command).lower()
    if any(re.search(rf"(?:^|[/:=]){re.escape(key)}(?:=|:)", command_text) for key in ("login", "password", "server")):
        raise StartupConfigBlocked("CREDENTIAL_OR_SERVER_COMMAND_ARGUMENT_FORBIDDEN")
    return tuple(command)


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            sections.setdefault(section, {})
            continue
        if "=" not in line or not section:
            raise StartupConfigBlocked("STARTUP_CONFIG_PARSE_ERROR")
        key, value = line.split("=", 1)
        sections[section][key.strip().lower()] = value.strip()
    return sections


def validate_startup_config(path: Path, spec: StartupConfigSpec) -> StartupConfigResult:
    if not path.is_file():
        return StartupConfigResult("BLOCKED", path, None, None, ("STARTUP_CONFIG_MISSING",))
    try:
        sections = parse_ini(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, StartupConfigBlocked) as exc:
        return StartupConfigResult("BLOCKED", path, None, None, (f"STARTUP_CONFIG_UNREADABLE:{type(exc).__name__}",))
    reasons: list[str] = []
    for section, key, expected in (
        ("experts", "allowlivetrading", "0"),
        ("experts", "allowdllimport", "0"),
        ("experts", "enabled", "1"),
        ("startup", "expert", _relative_expert_path(spec)),
        ("startup", "symbol", EXPECTED_SYMBOL),
        ("startup", "period", EXPECTED_PERIOD),
    ):
        actual = sections.get(section, {}).get(key)
        if actual != expected:
            reasons.append(f"STARTUP_{section.upper()}_{key.upper()}_MISMATCH")
    if "startup" not in sections:
        reasons.append("STARTUP_SECTION_MISSING")
    for section_values in sections.values():
        for key, value in section_values.items():
            if key in _FORBIDDEN_CONFIG_KEYS or key in {"proxylogin", "proxypassword"}:
                reasons.append(f"CREDENTIAL_KEY_PRESENT:{key}")
            if any(token in value.lower() for token in ("password=", "login=", "server=")):
                reasons.append(f"CREDENTIAL_VALUE_PRESENT:{key}")
    command = None if reasons else build_terminal_command(spec)
    return StartupConfigResult(
        "PASS" if not reasons else "BLOCKED",
        path,
        sha256_file(path),
        command,
        tuple(reasons),
        {section: str(values) for section, values in sections.items()},
    )


__all__ = [
    "EXPECTED_PERIOD",
    "EXPECTED_SYMBOL",
    "StartupConfigBlocked",
    "StartupConfigResult",
    "StartupConfigSpec",
    "build_terminal_command",
    "parse_ini",
    "render_startup_config",
    "sha256_file",
    "validate_startup_config",
    "write_startup_config",
]
