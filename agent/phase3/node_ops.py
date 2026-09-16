"""Công cụ vận hành node Phase 3: bootstrap, handoff, health và recovery.

Module này chỉ quản lý artifact, trạng thái vận hành và bằng chứng recovery.
Nó không tạo authorization, không tạo FORWARD run và không điều khiển terminal.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ..features.fingerprint import fingerprint
from ..memory.database import apply_migrations, connect_database, integrity_status
from ..scoring.train import ModelBundle
from .bundle import validate_bundle
from .forward import (
    AUTHORIZATION_SCHEMA,
    RUNTIME_CONFIG_SCHEMA,
    ForwardAuthorization,
    ForwardControlError,
    ForwardRuntimeConfig,
    current_git_sha,
    load_forward_config,
    load_history_index_artifact,
    read_runtime_status,
    write_forward_config,
)
from .ingestion.file_tail import file_source_identity
from .ingestion.opportunity import CANONICALIZER_FINGERPRINT
from .models import (
    PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
    PHASE3_CANONICALIZER_VERSION,
    PHASE3_OPPORTUNITY_SCHEMA,
    PHASE3_TELEMETRY_SCHEMA,
    format_utc_timestamp,
    utc_now,
)


PACKAGE_SCHEMA = "phase3-forward-node-package/1"
PACKAGE_MANIFEST_SCHEMA = "phase3-forward-node-manifest/1"
HANDOFF_SCHEMA = "phase3-forward-handoff/1"
HEALTH_SCHEMA = "phase3-forward-health/1"
BACKUP_SCHEMA = "phase3-forward-backup/1"
RESTORE_SCHEMA = "phase3-forward-restore/1"
MACHINE_MANIFEST_SCHEMA = "phase3-forward-machine/1"
PREFLIGHT_SCHEMA = "phase3-mt5-preflight/1"


class NodeOpsError(ForwardControlError):
    """Lỗi vận hành phải dừng an toàn, không sửa dữ liệu đang có."""


class ArtifactIntegrityError(NodeOpsError):
    """Artifact thiếu, sai checksum hoặc không khớp frozen contract."""


@dataclass(frozen=True)
class NodePaths:
    """Ba vùng persistence độc lập, không chứa default drive cố định."""

    install_root: Path
    runtime_root: Path
    ops_root: Path

    @classmethod
    def from_values(
        cls,
        install_root: str | Path,
        runtime_root: str | Path,
        ops_root: str | Path,
    ) -> "NodePaths":
        return cls(
            Path(install_root).expanduser().resolve(),
            Path(runtime_root).expanduser().resolve(),
            Path(ops_root).expanduser().resolve(),
        )


def _now() -> str:
    return format_utc_timestamp(datetime.now(UTC))


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise NodeOpsError(f"JSON không đọc được: {Path(path)}") from exc


def atomic_write_text(path: str | Path, value: str) -> None:
    """Ghi file tạm cùng thư mục rồi replace để handoff không bị đọc dở."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            if not value.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Ghi snapshot JSON atomic, giữ format ổn định để dễ diff/audit."""

    atomic_write_text(path, json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


def append_operator_log(ops_root: str | Path, event: Mapping[str, Any]) -> Path:
    """Append một audit event và fsync; không ghi secret hoặc credential."""

    target = Path(ops_root) / "logs" / "operator_log.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {"recorded_at_utc": _now(), **dict(event)}
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return target


def record_incident(
    ops_root: str | Path,
    *,
    severity: str,
    code: str,
    details: Mapping[str, Any] | None = None,
) -> Path:
    """Ghi incident ngoài Git để agent sau tiếp quản được ngay."""

    target = Path(ops_root) / "logs" / "incident_log.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "recorded_at_utc": _now(),
        "severity": str(severity).upper(),
        "code": str(code),
        "details": dict(details or {}),
    }
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return target


def sha256_file(path: str | Path) -> str:
    """Tính SHA-256 theo stream, không giữ artifact lớn trong memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_file(path: str | Path, label: str) -> Path:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ArtifactIntegrityError(f"{label} không tồn tại: {target}")
    return target


def _safe_relative(value: str | Path) -> Path:
    """Chặn absolute path và traversal trong manifest/package."""

    raw = str(value).replace("\\", "/")
    candidate = Path(raw.replace("/", os.sep))
    is_drive_absolute = len(raw) >= 2 and raw[1] == ":"
    if candidate.is_absolute() or is_drive_absolute or raw.startswith("/") or ".." in candidate.parts:
        raise ArtifactIntegrityError(f"package path không an toàn: {value}")
    return Path(*candidate.parts)


def _is_sha256_digest(value: Any) -> bool:
    """Kiểm tra digest detached có đúng dạng SHA-256 hay không."""

    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdefABCDEF" for char in text)


def _copy_if_absent_or_same(source: Path, target: Path, expected_sha256: str | None = None) -> bool:
    """Không ghi đè artifact runtime khác checksum; trả về có copy hay không."""

    if target.exists():
        if not target.is_file():
            raise NodeOpsError(f"runtime artifact target không phải file: {target}")
        actual = sha256_file(target)
        if expected_sha256 and actual != expected_sha256:
            raise NodeOpsError(f"runtime artifact đã tồn tại nhưng khác checksum: {target}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if expected_sha256 and sha256_file(target) != expected_sha256:
        raise ArtifactIntegrityError(f"copy artifact không giữ được checksum: {target}")
    return True


def _artifact_manifest_entry(path: str, source: Path, *, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": path.replace(os.sep, "/"),
        "filename": source.name,
        "sha256": sha256_file(source),
        "size_bytes": source.stat().st_size,
        "last_modified_utc": datetime.fromtimestamp(source.stat().st_mtime, tz=UTC).isoformat().replace("+00:00", "Z"),
    }


def _manifest_artifact(manifest: Mapping[str, Any], key: str) -> Path:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or not isinstance(artifacts.get(key), Mapping):
        raise ArtifactIntegrityError(f"manifest thiếu artifact role: {key}")
    value = artifacts[key].get("path")
    if not isinstance(value, str) or not value:
        raise ArtifactIntegrityError(f"manifest artifact path trống: {key}")
    return _safe_relative(value)


def _render_placeholders(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _render_placeholders(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_placeholders(item, replacements) for item in value]
    if isinstance(value, str):
        if value in replacements:
            return replacements[value]
        rendered = value
        for key, replacement in replacements.items():
            rendered = rendered.replace(key, replacement)
        return rendered
    return value


def _write_checksums(package_root: Path) -> tuple[Path, str]:
    lines: list[str] = []
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or path.name == "CHECKSUMS.sha256":
            continue
        relative = path.relative_to(package_root).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    target = package_root / "CHECKSUMS.sha256"
    atomic_write_text(target, "\n".join(lines))
    return target, sha256_file(target)


def _parse_checksums(package_root: Path) -> dict[str, str]:
    target = _required_file(package_root / "CHECKSUMS.sha256", "CHECKSUMS.sha256")
    result: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as exc:
            raise ArtifactIntegrityError(f"dòng checksum không hợp lệ: {raw_line}") from exc
        relative_path = _safe_relative(relative.strip()).as_posix()
        if relative_path in result:
            raise ArtifactIntegrityError(f"checksum bị lặp: {relative_path}")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ArtifactIntegrityError(f"digest không hợp lệ: {relative_path}")
        result[relative_path] = digest.lower()
    return result


def create_deployment_package(
    output: str | Path,
    *,
    approved_git_sha: str,
    repository_url: str,
    bundle_manifest: str | Path,
    model_bundle: str | Path,
    history_index: str | Path,
    ea_ex5: str | Path,
    ea_preset: str | Path,
    ea_source_revision: str,
    dependency_manifest: str | Path,
    source_mq5: str | Path | None = None,
    phase1_fingerprint: str | None = None,
    trusted_manifest_digest: str | None = None,
    test_only: bool = False,
) -> dict[str, Any]:
    """Đóng gói artifact thật sau khi validate frozen bundle/model/index.

    Hàm không tự tìm artifact theo tên đoán trước. Mọi đường dẫn phải do operator
    truyền vào; vì vậy thiếu model/index sẽ dừng thay vì retrain hay fabricate.
    """

    if len(str(approved_git_sha)) != 40 or any(char not in "0123456789abcdefABCDEF" for char in str(approved_git_sha)):
        raise ArtifactIntegrityError("approved_git_sha phải là full Git SHA")
    if not str(repository_url).strip():
        raise ArtifactIntegrityError("repository_url không được trống")
    if not str(ea_source_revision).strip():
        raise ArtifactIntegrityError("ea_source_revision phải được xác nhận rõ")

    bundle_source = _required_file(bundle_manifest, "bundle manifest")
    model_source = _required_file(model_bundle, "model bundle")
    index_source = _required_file(history_index, "historical similarity index")
    ex5_source = _required_file(ea_ex5, "EA EX5")
    preset_source = _required_file(ea_preset, "EA preset")
    dependency_source = _required_file(dependency_manifest, "dependency manifest")
    source_source = _required_file(source_mq5, "EA source") if source_mq5 else None

    try:
        bundle_payload = _read_json(bundle_source)
        bundle = validate_bundle(bundle_payload)
        model_payload = _read_json(model_source)
        if not isinstance(model_payload, Mapping):
            raise ArtifactIntegrityError("model bundle phải là JSON object")
        model = ModelBundle.from_dict(model_payload)
        model_digest = fingerprint(model.to_dict())
        expected_model_digest = str(bundle.config_json.get("model_payload_fingerprint") or bundle.model_fingerprint)
        if model_digest != expected_model_digest or model_digest != bundle.model_fingerprint:
            raise ArtifactIntegrityError("model bundle không khớp frozen bundle")
        load_history_index_artifact(index_source, bundle)
    except ArtifactIntegrityError:
        raise
    except (ForwardControlError, ValueError, TypeError, KeyError, OSError) as exc:
        if isinstance(exc, ArtifactIntegrityError):
            raise
        raise ArtifactIntegrityError("frozen bundle/model/index không hợp lệ") from exc
    if phase1_fingerprint and str(phase1_fingerprint) != bundle.phase1_fingerprint:
        raise ArtifactIntegrityError("Phase 1 fingerprint không khớp bundle")

    package_root = Path(output).expanduser().resolve()
    if package_root.exists() and any(package_root.iterdir()):
        raise NodeOpsError(f"package output đã có dữ liệu, không overwrite: {package_root}")
    package_root.mkdir(parents=True, exist_ok=True)
    artifacts_root = package_root / "artifacts"
    config_root = package_root / "config"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    sources: list[tuple[str, Path, str]] = [
        ("bundle_manifest", bundle_source, "frozen_bundle"),
        ("model_bundle", model_source, "frozen_model"),
        ("historical_similarity_index", index_source, "frozen_similarity_index"),
        ("ea_ex5", ex5_source, "approved_ea_ex5"),
        ("ea_preset", preset_source, "approved_ea_preset"),
    ]
    if source_source:
        sources.append(("ea_source", source_source, "ea_source"))
    artifact_entries: dict[str, dict[str, Any]] = {}
    for role, source, role_label in sources:
        destination = artifacts_root / source.name
        if destination.name in {entry.get("filename") for entry in artifact_entries.values()}:
            raise NodeOpsError(f"artifact filename bị trùng trong package: {destination.name}")
        shutil.copy2(source, destination)
        artifact_entries[role] = _artifact_manifest_entry(
            str(Path("artifacts") / destination.name),
            destination,
            role=role_label,
        )
    dependency_destination = config_root / "dependency-manifest.json"
    shutil.copy2(dependency_source, dependency_destination)

    artifact_names = {role: entry["path"] for role, entry in artifact_entries.items()}
    template: dict[str, Any] = {
        "schema": RUNTIME_CONFIG_SCHEMA,
        "runtime_root": "${RUNTIME_ROOT}",
        "repo_path": "${INSTALL_ROOT}",
        "python_path": "${PYTHON_PATH}",
        "bundle_manifest": "${RUNTIME_ROOT}/artifacts/" + Path(artifact_names["bundle_manifest"]).name,
        "model_bundle_path": "${RUNTIME_ROOT}/artifacts/" + Path(artifact_names["model_bundle"]).name,
        "history_index_path": "${RUNTIME_ROOT}/artifacts/" + Path(artifact_names["historical_similarity_index"]).name,
        "telemetry_path": "${RUNTIME_ROOT}/telemetry/phase3-diagnostic.jsonl",
        "primary_opportunity_path": "${RUNTIME_ROOT}/telemetry/phase3-opportunity-observation.jsonl",
        "execution_diagnostic_path": "${RUNTIME_ROOT}/telemetry/phase3-diagnostic.jsonl",
        "runtime_db": "${RUNTIME_ROOT}/db/forward.sqlite",
        "telemetry_format": "jsonl",
        "telemetry_source": "mt5-phase3",
        "schema_version": PHASE3_TELEMETRY_SCHEMA,
        "primary_opportunity_schema": PHASE3_OPPORTUNITY_SCHEMA,
        "canonical_schema": PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
        "canonicalizer_version": PHASE3_CANONICALIZER_VERSION,
        "canonicalizer_fingerprint": CANONICALIZER_FINGERPRINT,
        "execution_mode": "NONE",
        "live_execution_enabled": False,
        "execution_authority": "NONE",
        "trade_control_authority": "NONE",
        "position_control_authority": "NONE",
        "risk_control_authority": "NONE",
        "heartbeat_interval_seconds": 30,
        "heartbeat_stale_seconds": 120,
        "poll_interval_seconds": 5.0,
    }
    atomic_write_json(config_root / "forward.template.json", template)
    bootstrap_root = package_root / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    bootstrap_script = f'''[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$RuntimeRoot,
    [Parameter(Mandatory=$true)][string]$OpsRoot,
    [Parameter(Mandatory=$true)][string]$PackagePath,
    [string]$ExpectedGitSha = '{str(approved_git_sha).lower()}',
    [string]$ExpectedTrustedManifestDigest,
    [string]$PythonPath = 'python'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Bootstrap package không chứa credential và không đăng ký Scheduler.
if (-not (Test-Path -LiteralPath $PackagePath -PathType Container)) {{ throw 'PackagePath không tồn tại.' }}
$installParent = Split-Path -Parent $InstallRoot
if ($installParent -and -not (Test-Path -LiteralPath $installParent -PathType Container)) {{
    New-Item -ItemType Directory -Force -Path $installParent | Out-Null
}}
if ((Test-Path -LiteralPath $InstallRoot -PathType Container) -and
    (Test-Path -LiteralPath (Join-Path $InstallRoot '.git'))) {{
    # Source đã có thì Python bootstrap sẽ kiểm tra đúng SHA mà không reset.
}} elseif (Test-Path -LiteralPath $InstallRoot -PathType Container) {{
    if ((Get-ChildItem -LiteralPath $InstallRoot -Force | Measure-Object).Count -gt 0) {{ throw 'InstallRoot không rỗng và chưa phải Git repository.' }}
    & git clone --no-checkout '{str(repository_url)}' $InstallRoot
    if ($LASTEXITCODE -ne 0) {{ throw 'git clone thất bại.' }}
    & git -C $InstallRoot checkout --detach $ExpectedGitSha
    if ($LASTEXITCODE -ne 0) {{ throw 'checkout approved SHA thất bại.' }}
}} else {{
    & git clone --no-checkout '{str(repository_url)}' $InstallRoot
    if ($LASTEXITCODE -ne 0) {{ throw 'git clone thất bại.' }}
    & git -C $InstallRoot checkout --detach $ExpectedGitSha
    if ($LASTEXITCODE -ne 0) {{ throw 'checkout approved SHA thất bại.' }}
}}
if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot '.git'))) {{
    throw 'InstallRoot chưa là checkout Git sau clone.'
}}
Push-Location $InstallRoot
try {{
    $arguments = @(
        '-m', 'agent.phase3', 'bootstrap-forward-node',
        '--package-path', $PackagePath,
        '--install-root', $InstallRoot,
        '--runtime-root', $RuntimeRoot,
        '--ops-root', $OpsRoot,
        '--expected-git-sha', $ExpectedGitSha
    )
    if ($ExpectedTrustedManifestDigest) {{
        $arguments += @('--expected-trusted-manifest-digest', $ExpectedTrustedManifestDigest)
    }}
    & $PythonPath @arguments
    exit $LASTEXITCODE
}} finally {{ Pop-Location }}
'''
    atomic_write_text(bootstrap_root / "bootstrap.ps1", bootstrap_script)

    material = {
        "schema": PACKAGE_SCHEMA,
        "approved_git_sha": str(approved_git_sha).lower(),
        "repository_url": str(repository_url),
        "bundle_id": bundle.bundle_id,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "model_fingerprint": model_digest,
        "index_fingerprint": fingerprint(_read_json(index_source).get("rows", [])),
        "artifact_sha256": {key: value["sha256"] for key, value in artifact_entries.items()},
        "ea_source_revision": str(ea_source_revision),
        "test_only": bool(test_only),
    }
    manifest: dict[str, Any] = {
        "schema": PACKAGE_MANIFEST_SCHEMA,
        "package_schema": PACKAGE_SCHEMA,
        "package_created_at_utc": _now(),
        "package_material_fingerprint": fingerprint(material),
        "test_only": bool(test_only),
        "code": {
            "approved_git_sha": str(approved_git_sha).lower(),
            "repository_url": str(repository_url),
        },
        "phase1": {"dataset_fingerprint": bundle.phase1_fingerprint},
        "phase3": {
            "bundle_id": bundle.bundle_id,
            "bundle_schema": bundle.bundle_version,
            "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
            "model_version": bundle.model_version,
            "similarity_version": bundle.similarity_version,
        },
        "model": {
            "fingerprint": model_digest,
            "sha256": sha256_file(model_source),
            "path": artifact_names["model_bundle"],
        },
        "similarity": {
            "index_fingerprint": fingerprint(_read_json(index_source).get("rows", [])),
            "sha256": sha256_file(index_source),
            "cutoff_utc": bundle.historical_reference_cutoff_utc,
            "path": artifact_names["historical_similarity_index"],
        },
        "telemetry": {
            "raw_schema": PHASE3_OPPORTUNITY_SCHEMA,
            "canonical_schema": PHASE3_CANONICAL_OPPORTUNITY_SCHEMA,
            "canonicalizer_version": PHASE3_CANONICALIZER_VERSION,
            "canonicalizer_fingerprint": CANONICALIZER_FINGERPRINT,
        },
        "ea": {
            "source_revision": str(ea_source_revision),
            "ex5_sha256": sha256_file(ex5_source),
            "ex5_path": artifact_names["ea_ex5"],
            "preset_sha256": sha256_file(preset_source),
            "preset_path": artifact_names["ea_preset"],
            "source_path": artifact_names.get("ea_source"),
        },
        "environment": {
            "python_version": platform.python_version(),
            "dependency_manifest_path": "config/dependency-manifest.json",
            "dependency_manifest_sha256": sha256_file(dependency_destination),
            "dependency_installation": "stdlib_only_or_manifest_defined",
        },
        "integrity": {
            "checksums_file": "CHECKSUMS.sha256",
            "internal_checksum_scope": "package_files_only",
            "trusted_channel_status": "UNVERIFIED_EXTERNAL_ATTESTATION_REQUIRED",
            "trusted_manifest_digest": trusted_manifest_digest,
            "note": "Internal hashes prove package consistency, not provenance of the package source.",
        },
        "artifacts": artifact_entries,
        "config": {"template_path": "config/forward.template.json"},
        "safety": {
            "execution_authority": "NONE",
            "trade_control_authority": "NONE",
            "live_execution_enabled": False,
            "credentials_included": False,
            "authorization_included": False,
            "forward_run_included": False,
            "scheduler_install_requested": False,
        },
    }
    atomic_write_json(package_root / "manifest.json", manifest)
    checksums_path, checksums_digest = _write_checksums(package_root)
    return {
        "status": "PACKAGE_CREATED",
        "package_path": str(package_root),
        "manifest_sha256": sha256_file(package_root / "manifest.json"),
        "checksums_sha256": checksums_digest,
        "checksums_path": str(checksums_path),
        "artifact_integrity_status": "PASS",
        "trusted_package_status": "UNVERIFIED_EXTERNAL_ATTESTATION_REQUIRED",
        "test_only": bool(test_only),
        "safety": manifest["safety"],
    }


def verify_deployment_package(
    package_path: str | Path,
    *,
    expected_git_sha: str | None = None,
    expected_trusted_manifest_digest: str | None = None,
) -> dict[str, Any]:
    """Kiểm tra checksum toàn package và frozen intelligence trước bootstrap."""

    package_root = Path(package_path).expanduser().resolve()
    manifest_path = _required_file(package_root / "manifest.json", "package manifest")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("schema") != PACKAGE_MANIFEST_SCHEMA:
        raise ArtifactIntegrityError("package manifest schema không được hỗ trợ")
    checksums = _parse_checksums(package_root)
    actual_files = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    }
    if set(checksums) != actual_files:
        raise ArtifactIntegrityError("CHECKSUMS.sha256 không bao phủ đúng package files")
    for relative, expected in checksums.items():
        actual = sha256_file(package_root / _safe_relative(relative))
        if actual != expected:
            raise ArtifactIntegrityError(f"package checksum mismatch: {relative}")
    manifest_sha256 = sha256_file(manifest_path)
    test_only = bool(manifest.get("test_only", False))
    if expected_trusted_manifest_digest is not None:
        if not _is_sha256_digest(expected_trusted_manifest_digest):
            raise ArtifactIntegrityError("trusted manifest digest phải là SHA-256")
        if manifest_sha256 != str(expected_trusted_manifest_digest).lower():
            raise ArtifactIntegrityError("detached trusted manifest digest mismatch")
        trusted_package_status = "TRUSTED_EXTERNAL_MANIFEST_DIGEST_MATCH"
    elif test_only:
        # Fixture TEST_ONLY được phép chạy không có attestation production.
        trusted_package_status = "UNVERIFIED_EXTERNAL_ATTESTATION_REQUIRED"
    else:
        # Hash nằm trong package không tự chứng minh package chưa bị thay thế.
        raise ArtifactIntegrityError("PACKAGE_TRUST_ATTESTATION_REQUIRED")
    code = manifest.get("code")
    if not isinstance(code, Mapping) or not str(code.get("approved_git_sha", "")):
        raise ArtifactIntegrityError("package thiếu approved Git SHA")
    approved_sha = str(code["approved_git_sha"]).lower()
    if len(approved_sha) != 40 or any(char not in "0123456789abcdef" for char in approved_sha):
        raise ArtifactIntegrityError("package approved Git SHA không phải full SHA")
    if expected_git_sha and approved_sha != str(expected_git_sha).lower():
        raise ArtifactIntegrityError("package approved Git SHA khác ExpectedGitSha")
    safety = manifest.get("safety")
    if (
        not isinstance(safety, Mapping)
        or safety.get("execution_authority") != "NONE"
        or safety.get("trade_control_authority") != "NONE"
        or safety.get("live_execution_enabled") is not False
        or safety.get("credentials_included") is not False
        or safety.get("authorization_included") is not False
        or safety.get("forward_run_included") is not False
        or safety.get("scheduler_install_requested") is not False
    ):
        raise ArtifactIntegrityError("package safety contract không fail-closed")
    bundle_path = package_root / _manifest_artifact(manifest, "bundle_manifest")
    model_path = package_root / _manifest_artifact(manifest, "model_bundle")
    index_path = package_root / _manifest_artifact(manifest, "historical_similarity_index")
    bundle = validate_bundle(_read_json(bundle_path))
    model_payload = _read_json(model_path)
    if not isinstance(model_payload, Mapping):
        raise ArtifactIntegrityError("package model không phải object")
    model = ModelBundle.from_dict(model_payload)
    model_digest = fingerprint(model.to_dict())
    model_metadata = manifest.get("model")
    if not isinstance(model_metadata, Mapping):
        raise ArtifactIntegrityError("package thiếu model metadata")
    if model_digest != bundle.model_fingerprint or model_digest != str(model_metadata.get("fingerprint")):
        raise ArtifactIntegrityError("package model fingerprint mismatch")
    try:
        load_history_index_artifact(index_path, bundle)
    except ForwardControlError as exc:
        raise ArtifactIntegrityError("package historical index contract mismatch") from exc
    ea = manifest.get("ea")
    if not isinstance(ea, Mapping):
        raise ArtifactIntegrityError("package thiếu EA metadata")
    try:
        ex5_path = package_root / _safe_relative(str(ea.get("ex5_path", "")))
        preset_path = package_root / _safe_relative(str(ea.get("preset_path", "")))
        ex5_digest = sha256_file(ex5_path)
        preset_digest = sha256_file(preset_path)
    except (ArtifactIntegrityError, OSError) as exc:
        raise ArtifactIntegrityError("package EA EX5/preset path không hợp lệ") from exc
    if ex5_digest != str(ea.get("ex5_sha256")) or preset_digest != str(ea.get("preset_sha256")):
        raise ArtifactIntegrityError("EA EX5/preset checksum mismatch")
    return {
        "status": "PACKAGE_VALID",
        "package_path": str(package_root),
        "manifest_sha256": manifest_sha256,
        "checksums_sha256": sha256_file(package_root / "CHECKSUMS.sha256"),
        "approved_git_sha": approved_sha,
        "bundle_id": bundle.bundle_id,
        "phase1_fingerprint": bundle.phase1_fingerprint,
        "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
        "artifact_integrity_status": "PASS",
        "trusted_package_status": trusted_package_status,
        "test_only": test_only,
    }


def _probe_writable(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(directory), prefix=".write-test-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(b"probe")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise NodeOpsError(f"không có quyền ghi: {directory}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _python_for_venv(executable: str | Path, runtime_root: Path) -> Path:
    venv_root = runtime_root / ".venv"
    if os.name == "nt":
        candidate = venv_root / "Scripts" / "python.exe"
    else:
        candidate = venv_root / "bin" / "python"
    if candidate.is_file():
        return candidate.resolve()
    source = Path(executable).expanduser().resolve()
    if not source.is_file():
        found = shutil.which(str(executable))
        if not found:
            raise NodeOpsError(f"Python executable không tồn tại: {executable}")
        source = Path(found).resolve()
    venv.EnvBuilder(with_pip=False, clear=False, symlinks=False).create(venv_root)
    if not candidate.is_file():
        raise NodeOpsError(f"tạo Python virtualenv không thành công: {candidate}")
    return candidate.resolve()


def _command_available(name: str) -> bool:
    return bool(shutil.which(name) or (Path(name).is_file() if Path(name).suffix else False))


def _ensure_source_checkout(paths: NodePaths, package_manifest: Mapping[str, Any], expected_git_sha: str) -> None:
    """Clone/chọn SHA chỉ khi install root chưa có repo; không reset repo cũ."""

    install = paths.install_root
    if install.exists():
        if not install.is_dir():
            raise NodeOpsError(f"InstallRoot không phải thư mục: {install}")
        git_marker = install / ".git"
        if not git_marker.exists():
            if any(install.iterdir()):
                raise NodeOpsError("BOOTSTRAP_STOP_NON_REPOSITORY_INSTALL_ROOT")
            # Git clone vào thư mục rỗng đã tạo không xóa dữ liệu nào.
            repository_url = str(package_manifest.get("code", {}).get("repository_url", ""))
            if not repository_url:
                raise NodeOpsError("package thiếu repository_url để clone")
            result = subprocess.run(
                ["git", "clone", "--no-checkout", repository_url, str(install)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise NodeOpsError(f"git clone thất bại: {result.stderr.strip()}")
            result = subprocess.run(
                ["git", "-C", str(install), "checkout", "--detach", expected_git_sha],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise NodeOpsError(f"checkout approved SHA thất bại: {result.stderr.strip()}")
            return
        actual = current_git_sha(install)
        if actual.lower() != expected_git_sha.lower():
            raise NodeOpsError("BOOTSTRAP_STOP_REPOSITORY_SHA_MISMATCH")
        return
    install.parent.mkdir(parents=True, exist_ok=True)
    repository_url = str(package_manifest.get("code", {}).get("repository_url", ""))
    if not repository_url:
        raise NodeOpsError("package thiếu repository_url để clone")
    result = subprocess.run(
        ["git", "clone", "--no-checkout", repository_url, str(install)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise NodeOpsError(f"git clone thất bại: {result.stderr.strip()}")
    result = subprocess.run(
        ["git", "-C", str(install), "checkout", "--detach", expected_git_sha],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise NodeOpsError(f"checkout approved SHA thất bại: {result.stderr.strip()}")


def _merge_machine_manifest(ops_root: Path, update: Mapping[str, Any]) -> dict[str, Any]:
    target = ops_root / "machine_manifest.json"
    current: dict[str, Any] = {}
    if target.is_file():
        value = _read_json(target)
        if isinstance(value, Mapping):
            current = dict(value)
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(current.get(key), Mapping):
            merged = dict(current[key])
            merged.update(dict(value))
            current[key] = merged
        else:
            current[key] = value
    current.setdefault("schema", MACHINE_MANIFEST_SCHEMA)
    current.setdefault("created_at_utc", _now())
    current["updated_at_utc"] = _now()
    atomic_write_json(target, current)
    return current


def bootstrap_forward_node(
    package_path: str | Path,
    *,
    install_root: str | Path,
    runtime_root: str | Path,
    ops_root: str | Path,
    expected_git_sha: str,
    expected_trusted_manifest_digest: str | None = None,
    python_executable: str | Path | None = None,
    require_windows: bool = True,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Bootstrap idempotent một node, tuyệt đối chưa activation."""

    paths = NodePaths.from_values(install_root, runtime_root, ops_root)
    package_check = verify_deployment_package(
        package_path,
        expected_git_sha=expected_git_sha,
        expected_trusted_manifest_digest=expected_trusted_manifest_digest,
    )
    manifest = _read_json(Path(package_path).expanduser().resolve() / "manifest.json")
    if not isinstance(manifest, Mapping):
        raise ArtifactIntegrityError("package manifest phải là object")
    reported_platform = str(platform_name or platform.system())
    if require_windows and reported_platform.lower() != "windows":
        raise NodeOpsError("BOOTSTRAP_STOP_WINDOWS_REQUIRED")
    if not _command_available("git"):
        raise NodeOpsError("BOOTSTRAP_STOP_GIT_UNAVAILABLE")
    if python_executable is None:
        python_executable = sys.executable
    if not _command_available(str(python_executable)) and not Path(str(python_executable)).is_file():
        raise NodeOpsError("BOOTSTRAP_STOP_PYTHON_UNAVAILABLE")
    if require_windows and not (_command_available("powershell") or _command_available("pwsh")):
        raise NodeOpsError("BOOTSTRAP_STOP_POWERSHELL_UNAVAILABLE")

    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    paths.ops_root.mkdir(parents=True, exist_ok=True)
    _probe_writable(paths.runtime_root)
    _probe_writable(paths.ops_root)
    _ensure_source_checkout(paths, manifest, str(expected_git_sha))
    if current_git_sha(paths.install_root).lower() != str(expected_git_sha).lower():
        raise NodeOpsError("BOOTSTRAP_STOP_REPOSITORY_SHA_MISMATCH")

    authorization_path = paths.runtime_root / "config" / "forward_authorization.json"
    current_run_path = paths.runtime_root / "state" / "current_run.json"
    if authorization_path.exists() or current_run_path.exists():
        raise NodeOpsError("BOOTSTRAP_STOP_EXISTING_AUTHORIZATION_OR_RUN_REQUIRES_REVIEW")

    package_root = Path(package_path).expanduser().resolve()
    package_manifest = _read_json(package_root / "manifest.json")
    artifacts = package_manifest.get("artifacts", {})
    if not isinstance(artifacts, Mapping):
        raise ArtifactIntegrityError("package artifacts metadata không hợp lệ")
    runtime_artifacts = paths.runtime_root / "artifacts"
    runtime_artifacts.mkdir(parents=True, exist_ok=True)
    role_to_runtime: dict[str, Path] = {}
    for role in ("bundle_manifest", "model_bundle", "historical_similarity_index"):
        relative = _manifest_artifact(package_manifest, role)
        source = package_root / relative
        destination = runtime_artifacts / source.name
        _copy_if_absent_or_same(source, destination, sha256_file(source))
        role_to_runtime[role] = destination
    for role in ("ea_ex5", "ea_preset", "ea_source"):
        if role not in artifacts:
            continue
        relative = _manifest_artifact(package_manifest, role)
        source = package_root / relative
        destination = runtime_artifacts / source.name
        _copy_if_absent_or_same(source, destination, sha256_file(source))
        role_to_runtime[role] = destination

    runtime_dirs = (
        paths.runtime_root / "config",
        paths.runtime_root / "db",
        paths.runtime_root / "telemetry",
        paths.runtime_root / "state",
        paths.runtime_root / "control",
        paths.runtime_root / "logs",
        paths.runtime_root / "backup",
    )
    for directory in runtime_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    for directory in (
        paths.ops_root / "logs",
        paths.ops_root / "runs",
        paths.ops_root / "backups",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    venv_python = _python_for_venv(python_executable, paths.runtime_root)
    template_path = package_root / "config" / "forward.template.json"
    template = _read_json(template_path)
    if not isinstance(template, Mapping):
        raise ArtifactIntegrityError("forward.template.json phải là object")
    replacements = {
        "${INSTALL_ROOT}": str(paths.install_root),
        "${RUNTIME_ROOT}": str(paths.runtime_root),
        "${OPS_ROOT}": str(paths.ops_root),
        "${PYTHON_PATH}": str(venv_python),
    }
    rendered = _render_placeholders(template, replacements)
    if not isinstance(rendered, Mapping):
        raise NodeOpsError("render runtime config thất bại")
    rendered = dict(rendered)
    rendered["bundle_manifest"] = str(role_to_runtime["bundle_manifest"])
    rendered["model_bundle_path"] = str(role_to_runtime["model_bundle"])
    rendered["history_index_path"] = str(role_to_runtime["historical_similarity_index"])
    rendered["runtime_root"] = str(paths.runtime_root)
    rendered["repo_path"] = str(paths.install_root)
    rendered["python_path"] = str(venv_python)
    rendered["runtime_db"] = str(paths.runtime_root / "db" / "forward.sqlite")
    rendered["telemetry_path"] = str(paths.runtime_root / "telemetry" / "phase3-diagnostic.jsonl")
    rendered["execution_diagnostic_path"] = str(paths.runtime_root / "telemetry" / "phase3-diagnostic.jsonl")
    rendered["primary_opportunity_path"] = str(paths.runtime_root / "telemetry" / "phase3-opportunity-observation.jsonl")
    rendered["execution_mode"] = "NONE"
    rendered["live_execution_enabled"] = False
    config_path = paths.runtime_root / "config" / "forward.json"
    if config_path.is_file():
        config = load_forward_config(config_path)
        if Path(config.repo_path).resolve() != paths.install_root or Path(config.runtime_root).resolve() != paths.runtime_root:
            raise NodeOpsError("BOOTSTRAP_STOP_EXISTING_RUNTIME_CONFIG_PATH_MISMATCH")
    else:
        config = ForwardRuntimeConfig.from_dict(rendered, config_path=config_path)
        write_forward_config(config, config_path)

    connection = connect_database(config.db)
    try:
        applied_migrations = apply_migrations(connection)
        db_integrity = integrity_status(connection)
    finally:
        connection.close()
    if not db_integrity["integrity_ok"] or not db_integrity["foreign_key_ok"]:
        raise NodeOpsError("BOOTSTRAP_STOP_SQLITE_INTEGRITY")

    machine = _merge_machine_manifest(
        paths.ops_root,
        {
            "bootstrap": {
                "status": "PASS",
                "approved_git_sha": str(expected_git_sha).lower(),
                "package_manifest_sha256": package_check["manifest_sha256"],
                "package_checksums_sha256": package_check["checksums_sha256"],
                "artifact_integrity_status": "PASS",
                "trusted_package_status": package_check["trusted_package_status"],
            },
            "source": {"install_root": str(paths.install_root), "checkout_sha": current_git_sha(paths.install_root)},
            "runtime": {"runtime_root": str(paths.runtime_root), "config_path": str(config_path), "database": str(config.db)},
            "environment": {
                "platform": reported_platform,
                "python": str(venv_python),
                "python_version": platform.python_version(),
                "powershell_status": "NOT_RUN_BY_BOOTSTRAP" if not require_windows else "AVAILABLE",
            },
            "mt5": {"preflight_status": "NOT_RUN", "session_status": "NOT_VERIFIED"},
            "safety": {
                "execution_authority": "NONE",
                "trade_control_authority": "NONE",
                "live_execution_enabled": False,
                "forward_authorization": "NOT_CREATED",
                "forward_run_id": "NOT_CREATED",
                "scheduler": "NOT_INSTALLED_OR_DISABLED",
            },
        },
    )
    handoff = handoff_snapshot(config, paths.ops_root)
    health = ops_health(config, paths.ops_root)
    readiness = {
        "schema": "phase3-forward-bootstrap-readiness/1",
        "generated_at_utc": _now(),
        "bootstrap_status": "PASS",
        "artifact_integrity_status": "PASS",
        "repository_sha_status": "PASS",
        "database_integrity_status": "PASS",
        "migrations_applied": applied_migrations,
        "mt5_source_status": "WAITING_FOR_FIRST_REAL_RECORD",
        "activation_ready": False,
        "forward_authorization": "NOT_CREATED",
        "forward_run_id": "NOT_CREATED",
        "scheduler": "NOT_INSTALLED_OR_DISABLED",
        "live_execution_enabled": False,
        "handoff_status": handoff.get("handoff_status", "PASS"),
        "health_status": health.get("health_status", "UNKNOWN"),
        "machine_manifest": machine,
        "next_manual_requirement": "Cài/login MT5 và chạy mt5-preflight; không tạo synthetic primary JSONL.",
    }
    atomic_write_json(paths.ops_root / "bootstrap_readiness.json", readiness)
    append_operator_log(paths.ops_root, {"event": "BOOTSTRAP_COMPLETED", "status": "PASS", "run_id": "NOT_CREATED"})
    return {
        "status": "BOOTSTRAP_PASS",
        "bootstrap_status": "PASS",
        "install_root": str(paths.install_root),
        "runtime_root": str(paths.runtime_root),
        "ops_root": str(paths.ops_root),
        "config_path": str(config_path),
        "approved_git_sha": str(expected_git_sha).lower(),
        "artifact_integrity_status": "PASS",
        "trusted_package_status": package_check["trusted_package_status"],
        "database_integrity_status": "PASS",
        "mt5_source_status": "WAITING_FOR_FIRST_REAL_RECORD",
        "activation_ready": False,
        "forward_authorization": "NOT_CREATED",
        "forward_run_id": "NOT_CREATED",
        "scheduler": "NOT_INSTALLED_OR_DISABLED",
        "live_execution_enabled": False,
    }


def _runtime_db_counts(config: ForwardRuntimeConfig) -> dict[str, int]:
    result = {
        "predictions": 0,
        "resolved_outcomes": 0,
        "pending_outcomes": 0,
        "raw_observations": 0,
        "canonical_opportunities": 0,
        "duplicate_collapse": 0,
    }
    if not config.db.is_file():
        return result
    connection = connect_database(config.db)
    try:
        queries = {
            "predictions": "SELECT COUNT(*) FROM phase3_predictions",
            "resolved_outcomes": "SELECT COUNT(*) FROM phase3_outcomes WHERE status = 'RESOLVED'",
            "pending_outcomes": "SELECT COUNT(*) FROM phase3_predictions p WHERE NOT EXISTS (SELECT 1 FROM phase3_outcomes o WHERE o.forward_event_id = p.forward_event_id)",
            "raw_observations": "SELECT COUNT(*) FROM phase3_opportunity_observations",
            "canonical_opportunities": "SELECT COUNT(*) FROM phase3_canonical_opportunities",
            "duplicate_collapse": "SELECT COALESCE(SUM(duplicate_observation_count), 0) FROM phase3_canonical_opportunities",
        }
        for key, query in queries.items():
            try:
                result[key] = int(connection.execute(query).fetchone()[0])
            except sqlite3.OperationalError:
                result[key] = 0
    finally:
        connection.close()
    return result


def _source_checkpoint(config: ForwardRuntimeConfig) -> dict[str, Any] | None:
    if not config.db.is_file():
        return None
    connection = connect_database(config.db)
    try:
        row = connection.execute(
            "SELECT * FROM phase3_ingest_offsets WHERE source_key = ?",
            (str(config.primary_opportunity.resolve()),),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def _source_snapshot(config: ForwardRuntimeConfig) -> dict[str, Any]:
    source = config.primary_opportunity
    value: dict[str, Any] = {
        "path": str(source.resolve()),
        "schema": config.primary_opportunity_schema,
        "format": config.telemetry_format,
        "status": "WAITING_FOR_FIRST_REAL_RECORD",
        "exists": source.is_file(),
        "identity": None,
        "size_bytes": 0,
        "offset_bytes": None,
    }
    if source.is_file():
        value["identity"] = file_source_identity(source)
        value["size_bytes"] = source.stat().st_size
        value["status"] = "PRESENT_UNCONFIRMED_REAL_RECORD"
    checkpoint = _source_checkpoint(config)
    if checkpoint:
        value["checkpoint"] = checkpoint
        value["offset_bytes"] = int(checkpoint.get("offset_bytes", 0))
        if value["identity"] and str(checkpoint.get("source_identity")) != str(value["identity"]):
            value["status"] = "IDENTITY_MISMATCH"
        elif value["offset_bytes"] > int(value["size_bytes"]):
            value["status"] = "OFFSET_BEYOND_EOF"
    return value


def _frozen_snapshot(config: ForwardRuntimeConfig) -> dict[str, Any]:
    result: dict[str, Any] = {
        "bundle_id": None,
        "bundle_schema": None,
        "model_fingerprint": None,
        "similarity_index_sha256": None,
        "historical_reference_cutoff_utc": None,
        "code_sha": None,
    }
    try:
        bundle = validate_bundle(_read_json(config.bundle_manifest))
        result.update({
            "bundle_id": bundle.bundle_id,
            "bundle_schema": bundle.bundle_version,
            "historical_reference_cutoff_utc": bundle.historical_reference_cutoff_utc,
        })
        model = ModelBundle.from_dict(_read_json(config.model_bundle_path))
        result["model_fingerprint"] = fingerprint(model.to_dict())
        result["similarity_index_sha256"] = sha256_file(config.history_index_path)
    except (NodeOpsError, ValueError, TypeError, OSError):
        result["status"] = "UNAVAILABLE"
    try:
        result["code_sha"] = current_git_sha(config.repo_path)
    except NodeOpsError:
        result["code_sha"] = None
    return result


def _recent_incidents(ops_root: Path, limit: int = 5) -> list[dict[str, Any]]:
    target = ops_root / "logs" / "incident_log.jsonl"
    if not target.is_file():
        return []
    lines = target.read_text(encoding="utf-8").splitlines()
    result: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, Mapping):
            result.append(dict(value))
    return result


def _latest_backup(ops_root: Path) -> dict[str, Any]:
    target = ops_root / "backup_status.json"
    if not target.is_file():
        return {"status": "NOT_RUN", "last_successful_backup": None}
    value = _read_json(target)
    return dict(value) if isinstance(value, Mapping) else {"status": "UNKNOWN"}


def _render_current_handoff(state: Mapping[str, Any]) -> str:
    runtime = state.get("runtime", {})
    frozen = state.get("frozen", {})
    source = state.get("mt5_source", {})
    checkpoint = source.get("checkpoint") if isinstance(source, Mapping) else None
    counts = state.get("counts", {})
    safety = state.get("safety", {})
    incidents = state.get("unresolved_incidents", [])
    lines = [
        "# Phase 3 CURRENT_HANDOFF",
        "",
        f"Generated: `{state.get('generated_at_utc')}`",
        "",
        "## Current state",
        "",
        f"- Collector: **{runtime.get('status', 'UNKNOWN')}**",
        f"- Run ID: `{runtime.get('run_id') or 'NOT_CREATED'}`",
        f"- PID / heartbeat age: `{runtime.get('pid')}` / `{runtime.get('heartbeat_age')}`",
        f"- Git SHA: `{frozen.get('code_sha') or 'UNKNOWN'}`",
        f"- Bundle: `{frozen.get('bundle_id') or 'UNKNOWN'}`",
        f"- Model fingerprint: `{frozen.get('model_fingerprint') or 'UNKNOWN'}`",
        f"- Similarity index SHA-256: `{frozen.get('similarity_index_sha256') or 'UNKNOWN'}`",
        f"- Historical cutoff: `{frozen.get('historical_reference_cutoff_utc') or 'UNKNOWN'}`",
        "",
        "## MT5 source and checkpoint",
        "",
        f"- Primary source: `{source.get('path')}`",
        f"- Source status: **{source.get('status')}**",
        f"- Source identity: `{source.get('identity') or 'NONE'}`",
        f"- Size / offset: `{source.get('size_bytes')}` / `{source.get('offset_bytes')}` bytes",
        f"- Checkpoint record: `{json.dumps(checkpoint, ensure_ascii=False, sort_keys=True) if checkpoint else 'NONE'}`",
        "",
        "## Evidence counts",
        "",
        f"- Canonical opportunities: `{counts.get('canonical_opportunities', 0)}`",
        f"- Raw observations: `{counts.get('raw_observations', 0)}`",
        f"- Predictions: `{counts.get('predictions', 0)}`",
        f"- Resolved outcomes: `{counts.get('resolved_outcomes', 0)}`",
        f"- Pending outcomes: `{counts.get('pending_outcomes', 0)}`",
        f"- Duplicate collapse count: `{counts.get('duplicate_collapse', 0)}`",
        "",
        "## Backup and incidents",
        "",
        f"- Latest backup: `{state.get('latest_backup', {}).get('last_successful_backup')}`",
        f"- Unresolved incident tail: `{len(incidents)}` record(s)",
    ]
    if incidents:
        lines.extend(f"  - `{item.get('severity')}` `{item.get('code')}`" for item in incidents)
    lines.extend([
        "",
        "## Permissions and next step",
        "",
        f"- Execution authority: `{safety.get('execution_authority', 'NONE')}`",
        f"- Trade-control authority: `{safety.get('trade_control_authority', 'NONE')}`",
        f"- Live execution: `{safety.get('live_execution_enabled', False)}`",
        f"- Authorization: `{safety.get('forward_authorization', 'NOT_CREATED')}`",
        f"- Scheduler: `{safety.get('scheduler', 'NOT_INSTALLED_OR_DISABLED')}`",
        "- Agent được đọc status/health, tạo snapshot, ghi incident và chạy backup không phá hủy.",
        "- Agent không được sửa frozen artifact, đổi SHA, tạo authorization/run, bật Scheduler hay activation.",
        f"- Next step: `{state.get('next_step')}`",
        "",
    ])
    return "\n".join(lines)


def handoff_snapshot(
    config: ForwardRuntimeConfig,
    ops_root: str | Path,
    *,
    run_id: str | None = None,
    next_step: str | None = None,
) -> dict[str, Any]:
    """Sinh state + markdown ngoài Git bằng cùng nguồn truth với status-runtime."""

    ops = Path(ops_root).expanduser().resolve()
    ops.mkdir(parents=True, exist_ok=True)
    generated = _now()
    try:
        runtime_status = read_runtime_status(config, run_id=run_id, now=generated)
    except Exception as exc:
        # Generator hỏng không được kéo collector xuống; ghi stale marker để agent sau biết.
        stale = {
            "schema": HANDOFF_SCHEMA,
            "generated_at_utc": generated,
            "handoff_status": "HANDOFF_STALE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "collector_action": "UNCHANGED",
        }
        atomic_write_json(ops / "handoff_status.json", stale)
        record_incident(ops, severity="CRITICAL", code="HANDOFF_STALE", details={"error_type": type(exc).__name__})
        raise
    source = _source_snapshot(config)
    frozen = _frozen_snapshot(config)
    counts = _runtime_db_counts(config)
    selected_run_id = run_id or runtime_status.get("run_id")
    state: dict[str, Any] = {
        "schema": HANDOFF_SCHEMA,
        "generated_at_utc": generated,
        "handoff_status": "PASS",
        "runtime": {
            "status": runtime_status.get("persistent_runtime_status", "STOPPED"),
            "collector_running": bool(runtime_status.get("collector_running", False)),
            "pid": runtime_status.get("pid"),
            "process_alive": runtime_status.get("process_alive", False),
            "heartbeat_age": runtime_status.get("heartbeat_age"),
            "run_id": selected_run_id,
        },
        "frozen": frozen,
        "mt5_source": source,
        "checkpoint": source.get("checkpoint"),
        "counts": counts,
        "runtime_status": runtime_status,
        "latest_backup": _latest_backup(ops),
        "unresolved_incidents": _recent_incidents(ops),
        "safety": {
            "execution_authority": "NONE",
            "trade_control_authority": "NONE",
            "live_execution_enabled": False,
            "forward_authorization": "NOT_CREATED" if not config.authorization_path.exists() else "EXISTING_REQUIRES_REVIEW",
            "forward_run_id": selected_run_id or "NOT_CREATED",
            "scheduler": "NOT_INSTALLED_OR_DISABLED",
        },
        "next_step": next_step or (
            "Chạy mt5-preflight và chờ first real primary record; chưa tạo authorization."
            if source.get("status") != "PRESENT_UNCONFIRMED_REAL_RECORD"
            else "Tiếp tục giám sát read-only và xác minh backup/heartbeat."
        ),
        "source_of_truth": ["SQLite committed rows", "phase3_ingest_offsets", "primary source identity", "heartbeat/PID"],
    }
    atomic_write_json(ops / "current_state.json", state)
    atomic_write_text(ops / "CURRENT_HANDOFF.md", _render_current_handoff(state))
    if selected_run_id:
        snapshot_root = ops / "runs" / str(selected_run_id) / "handoff-snapshots"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        token = generated.replace(":", "").replace("-", "").replace("Z", "Z")
        atomic_write_json(snapshot_root / f"{token}.json", state)
    append_operator_log(ops, {"event": "HANDOFF_SNAPSHOT", "run_id": selected_run_id, "status": "PASS"})
    return state


def _health_status(reasons: list[str], *, critical: bool, warning: bool, unknown: bool) -> str:
    if critical:
        return "CRITICAL"
    if warning:
        return "WARNING"
    if unknown:
        return "UNKNOWN"
    return "HEALTHY"


def ops_health(
    config: ForwardRuntimeConfig,
    ops_root: str | Path,
    *,
    warning_disk_free_bytes: int = 10 * 1024 * 1024 * 1024,
    critical_disk_free_bytes: int = 2 * 1024 * 1024 * 1024,
    heartbeat_warning_multiplier: float = 1.0,
    heartbeat_critical_multiplier: float = 2.0,
    now: str | None = None,
) -> dict[str, Any]:
    """Health observer read-only với ngưỡng cấu hình được."""

    ops = Path(ops_root).expanduser().resolve()
    generated = format_utc_timestamp(now or _now())
    try:
        status = read_runtime_status(config, now=generated)
    except Exception as exc:
        status = {
            "persistent_runtime_status": "UNKNOWN",
            "collector_running": False,
            "process_alive": False,
            "heartbeat_age": None,
            "heartbeat_fresh": False,
            "run_id": None,
            "last_event": None,
            "last_prediction": None,
            "forward_sample_count": 0,
            "error": type(exc).__name__,
        }
    reasons: list[str] = []
    critical = False
    warning = False
    unknown = False
    heartbeat_age = status.get("heartbeat_age")
    heartbeat_present = heartbeat_age is not None
    if status.get("collector_running"):
        if not heartbeat_present:
            critical = True
            reasons.append("RUNNING_WITHOUT_HEARTBEAT")
        elif heartbeat_age > config.heartbeat_stale_seconds * heartbeat_critical_multiplier:
            critical = True
            reasons.append("HEARTBEAT_CRITICAL_STALE")
        elif heartbeat_age > config.heartbeat_stale_seconds * heartbeat_warning_multiplier:
            warning = True
            reasons.append("HEARTBEAT_WARNING_STALE")
        if not status.get("process_alive"):
            critical = True
            reasons.append("COLLECTOR_PID_NOT_ALIVE")
    elif status.get("run_id"):
        warning = True
        reasons.append("RUN_NOT_REPORTING_HEALTHY")
    else:
        unknown = True
        reasons.append("COLLECTOR_NOT_STARTED")

    source = _source_snapshot(config)
    if source["status"] == "IDENTITY_MISMATCH":
        critical = True
        reasons.append("PRIMARY_SOURCE_IDENTITY_MISMATCH")
    elif source["status"] == "OFFSET_BEYOND_EOF":
        critical = True
        reasons.append("INGEST_OFFSET_BEYOND_EOF")
    elif not source["exists"]:
        warning = True
        reasons.append("PRIMARY_SOURCE_WAITING")

    db_integrity: dict[str, Any] | None = None
    if config.db.is_file():
        connection = connect_database(config.db)
        try:
            db_integrity = integrity_status(connection)
        finally:
            connection.close()
        if not db_integrity["integrity_ok"] or not db_integrity["foreign_key_ok"]:
            critical = True
            reasons.append("SQLITE_INTEGRITY_FAILED")
    else:
        unknown = True
        reasons.append("SQLITE_NOT_INITIALIZED")

    disk_root = config.root if config.root.exists() else config.db.parent
    try:
        disk = shutil.disk_usage(disk_root)
        disk_free = int(disk.free)
        if disk_free <= critical_disk_free_bytes:
            critical = True
            reasons.append("DISK_FREE_CRITICAL")
        elif disk_free <= warning_disk_free_bytes:
            warning = True
            reasons.append("DISK_FREE_WARNING")
    except OSError:
        disk_free = None
        unknown = True
        reasons.append("DISK_USAGE_UNKNOWN")

    backup = _latest_backup(ops)
    if backup.get("status") not in {"VALID", "BACKUP_VALID"}:
        warning = True
        reasons.append("NO_VALID_BACKUP")
    health_status = _health_status(reasons, critical=critical, warning=warning, unknown=unknown)
    counts = _runtime_db_counts(config)
    payload: dict[str, Any] = {
        "schema": HEALTH_SCHEMA,
        "generated_at_utc": generated,
        "health_status": health_status,
        "reasons": reasons,
        "collector": {
            "pid": status.get("pid"),
            "process_alive": status.get("process_alive"),
            "heartbeat_age_seconds": heartbeat_age,
            "heartbeat_fresh": status.get("heartbeat_fresh"),
            "collector_status": status.get("persistent_runtime_status"),
            "run_id": status.get("run_id"),
        },
        "os_lock": {"path": str(config.lock_path), "present": config.lock_path.exists(), "observer_action": "READ_ONLY"},
        "primary_source": {
            "path": source["path"],
            "identity": source.get("identity"),
            "size_bytes": source.get("size_bytes"),
            "offset_bytes": source.get("offset_bytes"),
            "backlog_bytes": max(0, int(source.get("size_bytes", 0)) - int(source.get("offset_bytes") or 0)),
            "status": source.get("status"),
        },
        "progress": {
            "last_event": status.get("last_event"),
            "last_prediction": status.get("last_prediction"),
            "raw_observation_count": counts["raw_observations"],
            "canonical_opportunity_count": counts["canonical_opportunities"],
            "duplicate_collapse_count": counts["duplicate_collapse"],
            "prediction_count": counts["predictions"],
            "resolved_outcome_count": counts["resolved_outcomes"],
            "forward_sample_count": status.get("forward_sample_count", 0),
        },
        "sqlite": db_integrity,
        "disk": {"path": str(disk_root), "free_bytes": disk_free, "warning_threshold_bytes": warning_disk_free_bytes, "critical_threshold_bytes": critical_disk_free_bytes},
        "backup": backup,
        "safety": {"execution_authority": "NONE", "trade_control_authority": "NONE", "live_execution_enabled": False},
    }
    atomic_write_json(ops / "latest_health.json", payload)
    if health_status == "CRITICAL":
        record_incident(ops, severity="CRITICAL", code="HEALTH_CRITICAL", details={"reasons": reasons})
    return payload


def _copy_prefix(source: Path, target: Path, length: int) -> str:
    digest = hashlib.sha256()
    target.parent.mkdir(parents=True, exist_ok=True)
    remaining = length
    with source.open("rb") as input_stream, target.open("wb") as output_stream:
        while remaining:
            chunk = input_stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise NodeOpsError("raw source kết thúc trước checkpoint offset")
            output_stream.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        output_stream.flush()
        os.fsync(output_stream.fileno())
    return digest.hexdigest()


def _backup_file_record(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _online_backup(source_db: Path, destination_db: Path) -> None:
    """Dùng SQLite online backup API để bao gồm trạng thái committed trong WAL."""

    destination_db.parent.mkdir(parents=True, exist_ok=True)
    source = connect_database(source_db)
    destination = sqlite3.connect(str(destination_db))
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()


def _valid_authorization_payload(config: ForwardRuntimeConfig) -> dict[str, Any] | None:
    if not config.authorization_path.is_file():
        return None
    try:
        value = _read_json(config.authorization_path)
        if not isinstance(value, Mapping) or str(value.get("schema")) != AUTHORIZATION_SCHEMA:
            return None
        authorization = ForwardAuthorization.from_dict(value)
    except (NodeOpsError, ForwardControlError, TypeError, ValueError):
        return None
    if authorization.authorization_hash != authorization.computed_hash():
        return None
    if authorization.execution_mode != "NONE" or authorization.live_execution_enabled:
        return None
    return dict(value)


def create_backup(
    config: ForwardRuntimeConfig,
    ops_root: str | Path,
    *,
    backup_root: str | Path | None = None,
    backup_id: str | None = None,
) -> dict[str, Any]:
    """Tạo backup nhất quán DB/raw/artifact và từ chối nếu không chứng minh được."""

    ops = Path(ops_root).expanduser().resolve()
    root = Path(backup_root).expanduser().resolve() if backup_root else ops / "backups"
    token = backup_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = root / token
    if target.exists() and any(target.iterdir()):
        raise NodeOpsError(f"backup target đã có dữ liệu: {target}")
    target.mkdir(parents=True, exist_ok=True)
    source = config.primary_opportunity
    checkpoint = _source_checkpoint(config)
    db_integrity: dict[str, Any] | None = None
    if config.db.is_file():
        connection = connect_database(config.db)
        try:
            db_integrity = integrity_status(connection)
        finally:
            connection.close()
    reasons: list[str] = []
    if not db_integrity or not db_integrity["integrity_ok"] or not db_integrity["foreign_key_ok"]:
        reasons.append("SQLITE_INTEGRITY_NOT_VERIFIED")
    if not source.is_file():
        reasons.append("PRIMARY_SOURCE_NOT_AVAILABLE")
    if not checkpoint:
        reasons.append("INGEST_CHECKPOINT_NOT_AVAILABLE")
    offset = int(checkpoint.get("offset_bytes", 0)) if checkpoint else 0
    before_identity: str | None = None
    before_size = 0
    raw_sha: str | None = None
    if not reasons:
        before_identity = file_source_identity(source)
        before_size = source.stat().st_size
        if str(checkpoint.get("source_identity")) != before_identity:
            reasons.append("CHECKPOINT_SOURCE_IDENTITY_MISMATCH")
        if offset < 0 or offset > before_size:
            reasons.append("CHECKPOINT_OFFSET_BEYOND_EOF")
        elif not reasons:
            raw_sha = _copy_prefix(source, target / "raw" / source.name, offset)
            after_identity = file_source_identity(source)
            after_size = source.stat().st_size
            if before_identity != after_identity:
                reasons.append("SOURCE_CHANGED_DURING_BACKUP")
            if after_size < offset:
                reasons.append("SOURCE_TRUNCATED_DURING_BACKUP")
            if offset and not (target / "raw" / source.name).read_bytes().endswith((b"\n", b"\r")):
                reasons.append("CHECKPOINT_ENDS_IN_PARTIAL_LINE")
    if not reasons:
        _online_backup(config.db, target / "runtime" / config.db.name)
    else:
        # Vẫn giữ manifest chẩn đoán, nhưng không gọi đây là backup hợp lệ.
        (target / "runtime").mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    required_artifacts = (
        config.bundle_manifest,
        config.model_bundle_path,
        config.history_index_path,
        config.root / "config" / "forward.json",
    )
    config_path = required_artifacts[-1]
    for source_path in required_artifacts:
        candidate = Path(source_path)
        if candidate.is_file():
            destination = target / "artifacts" / candidate.name if candidate != config_path else target / "evidence" / "config" / candidate.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            copied.append(destination)
        else:
            reasons.append(f"REQUIRED_RUNTIME_ARTIFACT_MISSING:{candidate.name}")
    if config.authorization_path.is_file():
        authorization = _valid_authorization_payload(config)
        if authorization is not None:
            destination = target / "evidence" / "authorization.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config.authorization_path, destination)
            copied.append(destination)
        else:
            reasons.append("EXISTING_AUTHORIZATION_NOT_VALID_AND_NOT_INCLUDED")
    for directory in (ops / "logs", ops / "runs"):
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file():
                destination = target / "evidence" / directory.name / path.relative_to(directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
                copied.append(destination)

    files = [_backup_file_record(target, path) for path in sorted(target.rglob("*")) if path.is_file()]
    manifest: dict[str, Any] = {
        "schema": BACKUP_SCHEMA,
        "backup_id": token,
        "created_at_utc": _now(),
        "status": "VALID" if not reasons else "INVALID",
        "invalid_reasons": reasons,
        "database": {
            "source_path": str(config.db.resolve()),
            "backup_path": str((target / "runtime" / config.db.name).resolve()),
            "integrity": db_integrity,
            "online_backup_api": True,
        },
        "source": {
            "path": str(source.resolve()),
            "identity": before_identity,
            "size_bytes_at_capture": before_size,
            "checkpoint_offset_bytes": offset,
            "checkpoint_source_identity": checkpoint.get("source_identity") if checkpoint else None,
            "raw_prefix_sha256": raw_sha,
            "captured_at_utc": _now(),
        },
        "files": files,
        "retention": {"policy": "configured_keep_last_valid", "last_valid_must_not_be_deleted": True},
        "off_host_encryption": "NOT_CONFIGURED_MANUAL_REQUIREMENT",
        "safety": {"execution_authority": "NONE", "live_execution_enabled": False},
    }
    atomic_write_json(target / "backup_manifest.json", manifest)
    verification = verify_backup(target)
    backup_status = {
        "schema": "phase3-forward-backup-status/1",
        "updated_at_utc": _now(),
        "status": "VALID" if verification["status"] == "BACKUP_VALID" else "INVALID",
        "last_successful_backup": str(target) if verification["status"] == "BACKUP_VALID" else _latest_backup(ops).get("last_successful_backup"),
        "latest_attempt": {"path": str(target), "status": verification["status"], "reasons": verification.get("reasons", [])},
        "off_host_encryption": "NOT_CONFIGURED_MANUAL_REQUIREMENT",
    }
    atomic_write_json(ops / "backup_status.json", backup_status)
    if verification["status"] != "BACKUP_VALID":
        record_incident(ops, severity="WARNING", code="BACKUP_INVALID", details={"path": str(target), "reasons": verification.get("reasons", [])})
    append_operator_log(ops, {"event": "BACKUP_ATTEMPT", "path": str(target), "status": verification["status"]})
    return {"status": verification["status"], "backup_path": str(target), "manifest": manifest, "verification": verification}


def verify_backup(backup_path: str | Path, *, source_path: str | Path | None = None) -> dict[str, Any]:
    """Xác nhận backup offline; nếu source còn tồn tại có thể kiểm tra identity thêm."""

    root = Path(backup_path).expanduser().resolve()
    manifest_path = _required_file(root / "backup_manifest.json", "backup manifest")
    manifest = _read_json(manifest_path)
    if not isinstance(manifest, Mapping) or manifest.get("schema") != BACKUP_SCHEMA:
        return {"status": "BACKUP_INVALID", "reasons": ["UNKNOWN_BACKUP_SCHEMA"]}
    reasons = list(manifest.get("invalid_reasons", [])) if isinstance(manifest.get("invalid_reasons"), list) else []
    files = manifest.get("files", [])
    if not isinstance(files, list):
        reasons.append("FILES_MANIFEST_INVALID")
        files = []
    for item in files:
        if not isinstance(item, Mapping):
            reasons.append("FILE_RECORD_INVALID")
            continue
        try:
            relative = _safe_relative(str(item.get("path", "")))
            path = root / relative
            if not path.is_file() or sha256_file(path) != str(item.get("sha256")) or path.stat().st_size != int(item.get("size_bytes", -1)):
                reasons.append(f"FILE_CHECKSUM_MISMATCH:{relative.as_posix()}")
        except (OSError, TypeError, ValueError, ArtifactIntegrityError):
            reasons.append(f"FILE_INVALID:{item.get('path')}")
    database = manifest.get("database", {})
    database_path = root / "runtime" / str(Path(str(database.get("backup_path", "forward.sqlite"))).name)
    if not database_path.is_file():
        reasons.append("DATABASE_BACKUP_MISSING")
    else:
        connection = connect_database(database_path)
        try:
            integrity = integrity_status(connection)
        finally:
            connection.close()
        if not integrity["integrity_ok"] or not integrity["foreign_key_ok"]:
            reasons.append("RESTORED_DATABASE_INTEGRITY_FAILED")
    source = manifest.get("source", {})
    raw_name = Path(str(source.get("path", "primary.jsonl"))).name
    raw_path = root / "raw" / raw_name
    offset = int(source.get("checkpoint_offset_bytes", -1))
    if not raw_path.is_file() or raw_path.stat().st_size != offset:
        reasons.append("RAW_PREFIX_MISSING_OR_LENGTH_MISMATCH")
    elif source.get("raw_prefix_sha256") and sha256_file(raw_path) != str(source.get("raw_prefix_sha256")):
        reasons.append("RAW_PREFIX_CHECKSUM_MISMATCH")
    if source_path:
        candidate = Path(source_path).expanduser().resolve()
        if candidate.is_file():
            if file_source_identity(candidate) != str(source.get("identity")):
                reasons.append("CURRENT_SOURCE_IDENTITY_DIFFERS")
            elif candidate.stat().st_size < offset:
                reasons.append("CURRENT_SOURCE_SHORTER_THAN_CHECKPOINT")
    if reasons:
        return {"status": "BACKUP_INVALID", "backup_path": str(root), "reasons": sorted(set(str(item) for item in reasons))}
    return {
        "status": "BACKUP_VALID",
        "backup_path": str(root),
        "reasons": [],
        "checkpoint_offset_bytes": offset,
        "source_identity": source.get("identity"),
        "database_integrity": "PASS",
        "raw_consistency": "PASS",
    }


def restore_backup(
    backup_path: str | Path,
    target_root: str | Path,
    *,
    mode: str = "isolated",
) -> dict[str, Any]:
    """Restore isolated, không đè runtime đang chạy và không reuse authorization."""

    if str(mode).lower() != "isolated":
        raise NodeOpsError("chỉ hỗ trợ isolated restore; same-machine restore cần review riêng")
    root = Path(backup_path).expanduser().resolve()
    target = Path(target_root).expanduser().resolve()
    if target == root:
        raise NodeOpsError("restore target không được là backup source")
    verification = verify_backup(root)
    if verification["status"] != "BACKUP_VALID":
        raise NodeOpsError("RESTORE_REFUSED_INVALID_BACKUP: " + ",".join(verification.get("reasons", [])))
    if target.exists() and any(target.iterdir()):
        raise NodeOpsError("RESTORE_STOP_TARGET_NOT_EMPTY")
    target.mkdir(parents=True, exist_ok=True)
    manifest = _read_json(root / "backup_manifest.json")
    files = manifest.get("files", []) if isinstance(manifest, Mapping) else []
    copied: list[str] = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        relative = _safe_relative(str(item.get("path", "")))
        source = root / relative
        if relative.parts[:2] == ("runtime", "forward.sqlite"):
            destination = target / "db" / "forward.sqlite"
        elif relative.parts and relative.parts[0] == "raw":
            destination = target / "telemetry" / relative.name
        elif relative.parts and relative.parts[0] == "artifacts":
            destination = target / "evidence" / "artifacts" / relative.name
        else:
            destination = target / "evidence" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(destination))
    restore_manifest = {
        "schema": RESTORE_SCHEMA,
        "created_at_utc": _now(),
        "source_backup": str(root),
        "verification": verification,
        "copied_files": copied,
        "old_run": "STOPPED_OR_FAILED",
        "new_run": "REQUIRES_NEW_AUTHORIZATION",
        "cross_run_continuity": "NOT_CLAIMED",
        "authorization_reuse": "NOT_ALLOWED",
        "activation": "NOT_PERFORMED",
    }
    atomic_write_json(target / "restore_manifest.json", restore_manifest)
    connection = connect_database(target / "db" / "forward.sqlite")
    try:
        restored_integrity = integrity_status(connection)
    finally:
        connection.close()
    if not restored_integrity["integrity_ok"] or not restored_integrity["foreign_key_ok"]:
        raise NodeOpsError("RESTORE_STOP_DATABASE_INTEGRITY")
    return {
        "status": "RESTORE_VALIDATED_ISOLATED",
        "target_root": str(target),
        "database_integrity": "PASS",
        "checkpoint_offset_bytes": verification.get("checkpoint_offset_bytes"),
        "old_run": "STOPPED_OR_FAILED",
        "new_run": "REQUIRES_NEW_AUTHORIZATION",
        "cross_run_continuity": "NOT_CLAIMED",
        "authorization_reuse": "NOT_ALLOWED",
        "activation": "NOT_PERFORMED",
    }


def plan_cross_machine_migration(
    backup_path: str | Path,
    *,
    new_install_root: str | Path,
    new_runtime_root: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Tạo migration plan chỉ evidence; không copy auth hay tự tiếp tục run."""

    verification = verify_backup(backup_path)
    plan = {
        "schema": "phase3-forward-cross-machine-plan/1",
        "created_at_utc": _now(),
        "backup_path": str(Path(backup_path).expanduser().resolve()),
        "new_install_root": str(Path(new_install_root).expanduser().resolve()),
        "new_runtime_root": str(Path(new_runtime_root).expanduser().resolve()),
        "backup_verification": verification,
        "old_run": "STOPPED_OR_FAILED",
        "new_run": "REQUIRES_NEW_AUTHORIZATION",
        "cross_run_continuity": "NOT_CLAIMED",
        "source_identity": "MUST_BE_REBOUND_AND_REVIEWED",
        "authorization_reuse": "NOT_ALLOWED",
        "operator_approval": "REQUIRED_BEFORE_MIGRATION",
    }
    if output:
        atomic_write_json(output, plan)
    return plan


def run_mt5_preflight(
    *,
    terminal_path: str | Path,
    data_directory: str | Path,
    ea_path: str | Path,
    preset_path: str | Path,
    primary_source_path: str | Path,
    ops_root: str | Path,
    expected_server: str | None = None,
    expected_account: str | None = None,
    symbol: str = "BTCUSD",
    timeframe: str = "H1",
    common_files_root: str | Path | None = None,
    journal_evidence_path: str | Path | None = None,
    terminal_version: str | None = None,
    market_data_confirmed: bool = False,
    real_record_confirmed: bool = False,
    expected_ea_sha256: str | None = None,
    expected_preset_sha256: str | None = None,
) -> dict[str, Any]:
    """Audit MT5 installation mà không khởi động terminal hoặc tạo record giả."""

    ops = Path(ops_root).expanduser().resolve()
    terminal = Path(terminal_path).expanduser().resolve()
    data = Path(data_directory).expanduser().resolve()
    ea = Path(ea_path).expanduser().resolve()
    preset = Path(preset_path).expanduser().resolve()
    primary = Path(primary_source_path).expanduser().resolve()
    checks: dict[str, Any] = {
        "terminal_path": str(terminal),
        "terminal_exists": terminal.is_file(),
        "terminal_version": terminal_version or "NOT_PROVIDED",
        "data_directory": str(data),
        "data_directory_exists": data.is_dir(),
        "ea_path": str(ea),
        "ea_exists": ea.is_file(),
        "ea_sha256": sha256_file(ea) if ea.is_file() else None,
        "preset_path": str(preset),
        "preset_exists": preset.is_file(),
        "preset_sha256": sha256_file(preset) if preset.is_file() else None,
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "market_data_status": "CONFIRMED_BY_OPERATOR" if market_data_confirmed else "NOT_VERIFIED_MANUAL_MT5_REQUIRED",
        "server": str(expected_server or "NOT_CONFIGURED"),
        "account": str(expected_account or "NOT_CONFIGURED"),
        "session_status": "NOT_VERIFIED",
        "primary_source": {"path": str(primary), "status": "WAITING_FOR_FIRST_REAL_RECORD", "schema": PHASE3_OPPORTUNITY_SCHEMA},
        "file_common_status": "NOT_VERIFIED",
    }
    if expected_ea_sha256 and checks["ea_sha256"] != expected_ea_sha256.lower():
        checks["ea_checksum_status"] = "FAIL"
    else:
        checks["ea_checksum_status"] = "PASS" if ea.is_file() else "FAIL"
    if expected_preset_sha256 and checks["preset_sha256"] != expected_preset_sha256.lower():
        checks["preset_checksum_status"] = "FAIL"
    else:
        checks["preset_checksum_status"] = "PASS" if preset.is_file() else "FAIL"
    if common_files_root:
        common = Path(common_files_root).expanduser().resolve()
        try:
            primary.relative_to(common)
            checks["file_common_status"] = "PATH_UNDER_FILE_COMMON"
        except ValueError:
            checks["file_common_status"] = "FAIL_PRIMARY_NOT_UNDER_FILE_COMMON"
    if journal_evidence_path and Path(journal_evidence_path).is_file():
        journal = Path(journal_evidence_path).read_text(encoding="utf-8", errors="replace").lower()
        has_authorized = "authorized" in journal
        has_synchronized = "synchronized" in journal
        checks["session_status"] = "READY" if has_authorized and has_synchronized else "NOT_VERIFIED"
        checks["journal_evidence"] = {"path": str(Path(journal_evidence_path).resolve()), "authorized_marker": has_authorized, "synchronized_marker": has_synchronized}
    elif journal_evidence_path:
        checks["journal_evidence"] = {"path": str(Path(journal_evidence_path).resolve()), "status": "MISSING"}
    if primary.is_file():
        first_record: Mapping[str, Any] | None = None
        for line in primary.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except ValueError:
                checks["primary_source"]["status"] = "INVALID_JSONL"
                break
            if not isinstance(value, Mapping) or value.get("schema_version") != PHASE3_OPPORTUNITY_SCHEMA:
                checks["primary_source"]["status"] = "LEGACY_OR_WRONG_SCHEMA"
                break
            first_record = value
            break
        else:
            checks["primary_source"]["status"] = "WAITING_FOR_FIRST_REAL_RECORD"
        if first_record is not None:
            checks["primary_source"]["status"] = "REAL_RECORD_PRESENT" if real_record_confirmed else "PRESENT_NOT_OPERATOR_CONFIRMED_REAL"
            checks["primary_source"]["first_record_keys"] = sorted(str(key) for key in first_record)
    all_pass = all(
        (
            checks["terminal_exists"],
            checks["data_directory_exists"],
            checks["ea_exists"],
            checks["preset_exists"],
            checks["ea_checksum_status"] == "PASS",
            checks["preset_checksum_status"] == "PASS",
            checks["session_status"] == "READY",
            checks["file_common_status"] == "PATH_UNDER_FILE_COMMON" if common_files_root else True,
            checks["primary_source"].get("status") == "REAL_RECORD_PRESENT",
            market_data_confirmed,
            bool(expected_server),
            bool(expected_account),
        )
    )
    result: dict[str, Any] = {
        "schema": PREFLIGHT_SCHEMA,
        "generated_at_utc": _now(),
        "preflight_status": "PASS" if all_pass else "BLOCKED",
        "activation_ready": False,
        "mt5_source_status": checks["primary_source"]["status"],
        "checks": checks,
        "safety": {"execution_authority": "NONE", "trade_control_authority": "NONE", "live_execution_enabled": False, "authorization": "NOT_CREATED"},
        "next_requirement": "Chỉ operator xác nhận terminal/broker/history và first real primary record mới có thể mở gate; không tạo synthetic JSONL.",
    }
    atomic_write_json(ops / "mt5_preflight.json", result)
    _merge_machine_manifest(
        ops,
        {
            "mt5": {
                "preflight_status": result["preflight_status"],
                "session_status": checks["session_status"],
                "terminal_path": str(terminal),
                "terminal_version": checks["terminal_version"],
                "data_directory": str(data),
                "server": checks["server"],
                "account": checks["account"],
                "symbol": symbol,
                "timeframe": timeframe,
                "ea_path": str(ea),
                "ea_sha256": checks["ea_sha256"],
                "preset_path": str(preset),
                "preset_sha256": checks["preset_sha256"],
                "primary_source_path": str(primary),
                "file_common_status": checks["file_common_status"],
            }
        },
    )
    append_operator_log(ops, {"event": "MT5_PREFLIGHT", "status": result["preflight_status"], "source_status": checks["primary_source"]["status"]})
    return result


def takeover_check(
    ops_root: str | Path,
    *,
    expected_run_id: str | None = None,
    expected_git_sha: str | None = None,
    expected_source_identity: str | None = None,
) -> dict[str, Any]:
    """Kiểm tra handoff trước khi agent B nhận giám sát."""

    ops = Path(ops_root).expanduser().resolve()
    state_path = ops / "current_state.json"
    if not state_path.is_file():
        result = {"status": "TAKEOVER_BLOCKED", "reasons": ["CURRENT_HANDOFF_MISSING"]}
        record_incident(ops, severity="CRITICAL", code="TAKEOVER_BLOCKED", details=result)
        return result
    state = _read_json(state_path)
    if not isinstance(state, Mapping):
        result = {"status": "TAKEOVER_BLOCKED", "reasons": ["CURRENT_STATE_INVALID"]}
        record_incident(ops, severity="CRITICAL", code="TAKEOVER_BLOCKED", details=result)
        return result
    runtime = state.get("runtime", {})
    frozen = state.get("frozen", {})
    source = state.get("mt5_source", {})
    reasons: list[str] = []
    if expected_run_id is not None and str(runtime.get("run_id") or "") != str(expected_run_id):
        reasons.append("RUN_ID_MISMATCH")
    if expected_git_sha is not None and str(frozen.get("code_sha") or "") != str(expected_git_sha):
        reasons.append("GIT_SHA_MISMATCH")
    if expected_source_identity is not None and str(source.get("identity") or "") != str(expected_source_identity):
        reasons.append("SOURCE_IDENTITY_MISMATCH")
    result = {
        "status": "TAKEOVER_READY" if not reasons else "TAKEOVER_BLOCKED",
        "checked_at_utc": _now(),
        "reasons": reasons,
        "run_id": runtime.get("run_id"),
        "pid": runtime.get("pid"),
        "offset_bytes": source.get("offset_bytes"),
        "source_identity": source.get("identity"),
        "git_sha": frozen.get("code_sha"),
        "collector_action": "UNCHANGED",
        "agent_action": "READ_ONLY" if not reasons else "STOP_AND_ESCALATE",
    }
    if reasons:
        record_incident(ops, severity="CRITICAL", code="TAKEOVER_BLOCKED", details={"reasons": reasons})
    return result


def acknowledge_takeover(
    ops_root: str | Path,
    *,
    agent_id: str,
    expected_run_id: str | None = None,
    expected_git_sha: str | None = None,
    expected_source_identity: str | None = None,
) -> dict[str, Any]:
    """Ghi acknowledgement audit, không restart hoặc chạm collector."""

    if not str(agent_id).strip():
        raise NodeOpsError("agent_id không được trống")
    result = takeover_check(
        ops_root,
        expected_run_id=expected_run_id,
        expected_git_sha=expected_git_sha,
        expected_source_identity=expected_source_identity,
    )
    if result["status"] == "TAKEOVER_READY":
        append_operator_log(ops_root, {"event": "TAKEOVER_ACKNOWLEDGED", "agent_id": str(agent_id), "collector_action": "UNCHANGED"})
    return {**result, "agent_id": str(agent_id)}


__all__ = [
    "ArtifactIntegrityError",
    "BACKUP_SCHEMA",
    "HANDOFF_SCHEMA",
    "HEALTH_SCHEMA",
    "NodeOpsError",
    "NodePaths",
    "acknowledge_takeover",
    "append_operator_log",
    "atomic_write_json",
    "atomic_write_text",
    "bootstrap_forward_node",
    "create_backup",
    "create_deployment_package",
    "handoff_snapshot",
    "ops_health",
    "plan_cross_machine_migration",
    "record_incident",
    "restore_backup",
    "run_mt5_preflight",
    "sha256_file",
    "takeover_check",
    "verify_backup",
    "verify_deployment_package",
]
