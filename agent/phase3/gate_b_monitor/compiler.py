"""Credential-free MetaEditor compile planning and result verification.

The command follows the documented MetaEditor external-compiler interface:
``metaeditor64.exe /compile:<source> /log``.  Execution is guarded by an
explicit authorization argument and is never invoked by offline validation.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CompileBlocked(RuntimeError):
    """Compilation is not authorized or its identity contract is unsafe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CompileSpec:
    metaeditor_exe: Path
    source_path: Path
    expected_ex5_path: Path
    compile_log_path: Path
    source_sha256: str
    include_root: Path | None = None
    timeout_seconds: int = 120


@dataclass(frozen=True)
class CompileResult:
    status: str
    source_sha256: str | None
    ex5_sha256: str | None
    errors: int | None
    warnings: int | None
    command: tuple[str, ...] | None
    reasons: tuple[str, ...] = ()
    return_code: int | None = None


def build_compile_command(spec: CompileSpec) -> tuple[str, ...]:
    if not spec.metaeditor_exe.is_absolute() or not spec.source_path.is_absolute() or not spec.expected_ex5_path.is_absolute():
        raise CompileBlocked("COMPILE_PATHS_MUST_BE_ABSOLUTE")
    command: list[str] = [str(spec.metaeditor_exe), f"/compile:{spec.source_path}", "/log"]
    if spec.include_root is not None:
        command.append(f"/include:{spec.include_root}")
    return tuple(command)


def parse_compile_log(path: Path, source_name: str) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "MISSING", "errors": None, "warnings": None, "line": None}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    matches = [line for line in lines if source_name in line and "Compile" in line]
    if not matches:
        return {"status": "INCONCLUSIVE", "errors": None, "warnings": None, "line": None}
    line = matches[-1]
    match = re.search(r"-\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?", line, flags=re.IGNORECASE)
    if not match:
        return {"status": "INCONCLUSIVE", "errors": None, "warnings": None, "line": line}
    errors = int(match.group(1))
    warnings = int(match.group(2))
    return {
        "status": "PASS" if errors == 0 and warnings == 0 else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "line": line,
    }


def verify_compile_output(spec: CompileSpec) -> CompileResult:
    reasons: list[str] = []
    source_hash = sha256_file(spec.source_path) if spec.source_path.is_file() else None
    if source_hash != spec.source_sha256:
        reasons.append("SOURCE_SHA256_MISMATCH")
    parsed = parse_compile_log(spec.compile_log_path, spec.source_path.name)
    if parsed["status"] != "PASS":
        reasons.append(f"COMPILE_LOG_{parsed['status']}")
    ex5_hash = sha256_file(spec.expected_ex5_path) if spec.expected_ex5_path.is_file() else None
    if ex5_hash is None:
        reasons.append("COMPILED_EX5_MISSING")
    return CompileResult(
        "PASS" if not reasons else "BLOCKED",
        source_hash,
        ex5_hash,
        parsed["errors"],
        parsed["warnings"],
        build_compile_command(spec),
        tuple(reasons),
    )


def run_compile(spec: CompileSpec, *, authorized: bool = False) -> CompileResult:
    """Run MetaEditor only after a future explicit execution authorization."""

    if not authorized:
        raise CompileBlocked("COMPILE_REQUIRES_APPROVAL_B")
    if not spec.metaeditor_exe.is_file():
        raise CompileBlocked("METAEDITOR_EXECUTABLE_MISSING")
    if not spec.source_path.is_file():
        raise CompileBlocked("MONITOR_SOURCE_MISSING")
    if sha256_file(spec.source_path) != spec.source_sha256:
        raise CompileBlocked("SOURCE_SHA256_MISMATCH")
    command = build_compile_command(spec)
    try:
        completed = subprocess.run(command, cwd=str(spec.metaeditor_exe.parent), shell=False, timeout=spec.timeout_seconds, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CompileBlocked(f"METAEDITOR_EXECUTION_FAILED:{type(exc).__name__}") from exc
    result = verify_compile_output(spec)
    return CompileResult(
        result.status if completed.returncode == 0 else "BLOCKED",
        result.source_sha256,
        result.ex5_sha256,
        result.errors,
        result.warnings,
        command,
        result.reasons + (() if completed.returncode == 0 else (f"METAEDITOR_EXIT_{completed.returncode}",)),
        completed.returncode,
    )


__all__ = [
    "CompileBlocked",
    "CompileResult",
    "CompileSpec",
    "build_compile_command",
    "parse_compile_log",
    "run_compile",
    "sha256_file",
    "verify_compile_output",
]
