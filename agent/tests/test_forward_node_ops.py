"""TEST_ONLY contract tests cho fresh-node bootstrap và persistent handoff."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from unittest.mock import patch

from agent.features.fingerprint import fingerprint
from agent.memory.database import connect_database
from agent.phase3.forward import current_git_sha, load_forward_config
from agent.phase3.node_ops import (
    ArtifactIntegrityError,
    NodeOpsError,
    PackageVerificationMode,
    _snapshot_verified_package,
    _validate_repository_url,
    acknowledge_takeover,
    bootstrap_forward_node,
    create_backup,
    create_deployment_package,
    handoff_snapshot,
    ops_health,
    plan_cross_machine_migration,
    restore_backup,
    run_mt5_preflight,
    sha256_file,
    takeover_check,
    atomic_write_json,
    verify_backup,
    verify_deployment_package,
)
from agent.phase3.ingestion.file_tail import TelemetryFileTailer

try:
    from .test_phase3 import _fixture_bundle
except ImportError:
    from test_phase3 import _fixture_bundle


class ForwardNodeOpsTests(unittest.TestCase):
    """Các fixture đều tạm thời và không phải bằng chứng activation thật."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.model, cls.index, cls.rows = _fixture_bundle()
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.repo_sha = current_git_sha(cls.repo_root)

    def _write_assets(self, root: Path) -> dict[str, Path]:
        bundle_path = root / "bundle.json"
        model_path = root / "model.json"
        index_path = root / "history.json"
        ea_path = root / "approved.ex5"
        preset_path = root / "approved.set"
        source_path = root / "Mentor_RSI_MTF_v1.mq5"
        bundle_path.write_text(json.dumps(self.bundle.to_dict(include_model_payload=False)), encoding="utf-8")
        model_path.write_text(json.dumps(self.model.to_dict()), encoding="utf-8")
        index_payload = {
            "schema": "phase3-historical-similarity-index/1",
            "bundle_id": self.bundle.bundle_id,
            "phase1_fingerprint": self.bundle.phase1_fingerprint,
            "source_dataset_fingerprint": self.bundle.phase1_fingerprint,
            "historical_reference_cutoff_utc": self.bundle.historical_reference_cutoff_utc,
            "similarity_version": self.bundle.similarity_version,
            "similarity_fingerprint": self.bundle.similarity_fingerprint,
            "similarity_config": dict(self.bundle.config_json["similarity_config"]),
            "row_count": len(self.index.rows),
            "rows_fingerprint": fingerprint(list(self.index.rows)),
            "rows": list(self.index.rows),
        }
        index_path.write_text(json.dumps(index_payload), encoding="utf-8")
        ea_path.write_bytes(b"TEST_ONLY-compiled-ex5")
        preset_path.write_text("Symbol=BTCUSD\nPeriod=H1\n", encoding="utf-8")
        source_path.write_text("void OnTick() {}\n", encoding="utf-8")
        return {
            "bundle": bundle_path,
            "model": model_path,
            "index": index_path,
            "ea": ea_path,
            "preset": preset_path,
            "source": source_path,
        }

    def _package(self, root: Path, *, output: Path | None = None, test_only: bool = True) -> Path:
        assets = self._write_assets(root)
        package = output or (root / "package")
        create_deployment_package(
            package,
            approved_git_sha=self.repo_sha,
            repository_url="https://github.com/billy7d/build-bot.git",
            bundle_manifest=assets["bundle"],
            model_bundle=assets["model"],
            history_index=assets["index"],
            ea_ex5=assets["ea"],
            ea_preset=assets["preset"],
            ea_source_revision=self.repo_sha,
            dependency_manifest=self.repo_root / "docs/trading_agent/forward_ops/dependency-manifest.json",
            source_mq5=assets["source"],
            test_only=test_only,
        )
        return package

    def _production_package(self, root: Path, *, output: Path | None = None) -> tuple[Path, str]:
        package = self._package(root, output=output, test_only=False)
        return package, sha256_file(package / "manifest.json")

    @contextmanager
    def _environment(self) -> Iterator[tuple[Path, Path, Path, Path]]:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, trusted_digest = self._production_package(root)
            runtime = root / "runtime spaced-đ"
            ops = root / "ops spaced-空"
            result = bootstrap_forward_node(
                package,
                install_root=self.repo_root,
                runtime_root=runtime,
                ops_root=ops,
                expected_git_sha=self.repo_sha,
                expected_trusted_manifest_digest=trusted_digest,
                python_executable=sys.executable,
                require_windows=False,
                platform_name="TEST_ONLY",
            )
            self.assertEqual(result["bootstrap_status"], "PASS")
            config = load_forward_config(result["config_path"])
            yield root, runtime, ops, config

    def _write_checkpointed_source(self, config: object) -> Path:
        source = config.primary_opportunity
        source.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {"schema_version": "phase3-opportunity-observation/1", "source_observation_id": "test-1"},
            {"schema_version": "phase3-opportunity-observation/1", "source_observation_id": "test-2"},
        ]
        raw = "".join(json.dumps(line) + "\n" for line in lines).encode("utf-8")
        source.write_bytes(raw)
        from agent.phase3.ingestion.file_tail import file_source_identity

        identity = file_source_identity(source)
        connection = connect_database(config.db)
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO phase3_ingest_offsets(
                        source_key, source_identity, source_path, offset_bytes,
                        last_consumed_event_id, rotation_state_json, updated_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(source.resolve()), identity, str(source.resolve()), len(raw), "test-2", "{}", "2026-09-16T00:00:00Z"),
                )
        finally:
            connection.close()
        return source

    def test_package_checksum_and_frozen_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            package = self._package(Path(directory))
            verified = verify_deployment_package(
                package,
                expected_git_sha=self.repo_sha,
                mode=PackageVerificationMode.TEST_ONLY,
            )
            self.assertEqual(verified["status"], "PACKAGE_VALID")
            self.assertEqual(verified["artifact_integrity_status"], "PASS")
            self.assertEqual(verified["trusted_package_status"], "TEST_ONLY_ISOLATED_UNATTESTED")
            self.assertTrue((package / "bootstrap/bootstrap.ps1").is_file())

    def test_production_package_requires_detached_trusted_manifest_digest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = self._write_assets(root)
            package = root / "production-package"
            create_deployment_package(
                package,
                approved_git_sha=self.repo_sha,
                repository_url="https://github.com/billy7d/build-bot.git",
                bundle_manifest=assets["bundle"],
                model_bundle=assets["model"],
                history_index=assets["index"],
                ea_ex5=assets["ea"],
                ea_preset=assets["preset"],
                ea_source_revision=self.repo_sha,
                dependency_manifest=self.repo_root / "docs/trading_agent/forward_ops/dependency-manifest.json",
                source_mq5=assets["source"],
            )
            with self.assertRaisesRegex(ArtifactIntegrityError, "PACKAGE_TRUST_ATTESTATION_REQUIRED"):
                verify_deployment_package(package, expected_git_sha=self.repo_sha)
            trusted_digest = sha256_file(package / "manifest.json")
            verified = verify_deployment_package(
                package,
                expected_git_sha=self.repo_sha,
                expected_trusted_manifest_digest=trusted_digest,
            )
            self.assertEqual(verified["trusted_package_status"], "TRUSTED_EXTERNAL_MANIFEST_DIGEST_MATCH")
            with self.assertRaisesRegex(ArtifactIntegrityError, "detached trusted manifest digest mismatch"):
                verify_deployment_package(
                    package,
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest="0" * 64,
                )
            with self.assertRaisesRegex(ArtifactIntegrityError, "package approved Git SHA khác ExpectedGitSha"):
                verify_deployment_package(
                    package,
                    expected_git_sha="0" * 40,
                    expected_trusted_manifest_digest=trusted_digest,
                )

    def test_test_only_package_is_allowed_only_in_isolated_verify_mode(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(root)
            trusted_digest = sha256_file(package / "manifest.json")
            isolated = verify_deployment_package(
                package,
                expected_git_sha=self.repo_sha,
                mode=PackageVerificationMode.TEST_ONLY,
            )
            self.assertEqual(isolated["trusted_package_status"], "TEST_ONLY_ISOLATED_UNATTESTED")
            with self.assertRaisesRegex(ArtifactIntegrityError, "PACKAGE_TEST_ONLY_NOT_ALLOWED_IN_PRODUCTION"):
                verify_deployment_package(
                    package,
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest=trusted_digest,
                )
            with self.assertRaisesRegex(ArtifactIntegrityError, "PACKAGE_TEST_ONLY_NOT_ALLOWED_IN_PRODUCTION"):
                bootstrap_forward_node(
                    package,
                    install_root=self.repo_root,
                    runtime_root=root / "runtime",
                    ops_root=root / "ops",
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest=trusted_digest,
                    python_executable=sys.executable,
                    require_windows=False,
                    platform_name="TEST_ONLY",
                )
            self.assertFalse((root / "runtime").exists())
            self.assertFalse((root / "ops").exists())

    def test_test_only_tamper_and_snapshot_change_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(root)
            verified = verify_deployment_package(
                package,
                expected_git_sha=self.repo_sha,
                mode=PackageVerificationMode.TEST_ONLY,
            )
            (package / "artifacts/approved.set").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIntegrityError, "PACKAGE_CHANGED_AFTER_VERIFICATION"):
                _snapshot_verified_package(package, verified["file_hashes"], verified["checksums_sha256"])
            with self.assertRaises(ArtifactIntegrityError):
                verify_deployment_package(
                    package,
                    expected_git_sha=self.repo_sha,
                    mode=PackageVerificationMode.TEST_ONLY,
                )

    def test_rehashed_test_only_flag_cannot_become_production(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(root)
            original_manifest_digest = sha256_file(package / "manifest.json")
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            manifest["test_only"] = False
            (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            checksum_lines = []
            for line in (package / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines():
                if line.endswith("  manifest.json"):
                    line = f"{sha256_file(package / 'manifest.json')}  manifest.json"
                checksum_lines.append(line)
            (package / "CHECKSUMS.sha256").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ArtifactIntegrityError, "detached trusted manifest digest mismatch"):
                verify_deployment_package(
                    package,
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest=original_manifest_digest,
                )

    def test_repository_url_allowlist_rejects_injection_and_invalid_sha(self) -> None:
        safe_url = "https://github.com/billy7d/build-bot.git"
        self.assertEqual(_validate_repository_url(safe_url), safe_url)
        payloads = (
            "https://github.com/billy7d/build-bot.git' ; Set-Content pwned x",
            'https://github.com/billy7d/build-bot.git"; Set-Content pwned x',
            "https://github.com/billy7d/build-bot.git;Write-Output pwned",
            "https://github.com/billy7d/build-bot.git&Write-Output pwned",
            "https://github.com/billy7d/build-bot.git\nWrite-Output pwned",
            "--upload-pack=Write-Output-pwned",
            "http://github.com/billy7d/build-bot.git",
            "https://evil.example/billy7d/build-bot.git",
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ArtifactIntegrityError, "repository_url"):
                    _validate_repository_url(payload)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = self._write_assets(root)
            with self.assertRaisesRegex(ArtifactIntegrityError, "approved_git_sha"):
                create_deployment_package(
                    root / "invalid-sha-package",
                    approved_git_sha="g" * 40,
                    repository_url=safe_url,
                    bundle_manifest=assets["bundle"],
                    model_bundle=assets["model"],
                    history_index=assets["index"],
                    ea_ex5=assets["ea"],
                    ea_preset=assets["preset"],
                    ea_source_revision=self.repo_sha,
                    dependency_manifest=self.repo_root / "docs/trading_agent/forward_ops/dependency-manifest.json",
                )

    def test_generated_bootstrap_uses_only_argument_arrays(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(root)
            script = (package / "bootstrap/bootstrap.ps1").read_text(encoding="utf-8")
            self.assertNotIn("https://github.com/billy7d/build-bot.git", script)
            self.assertNotIn(self.repo_sha, script)
            self.assertNotIn("git clone", script.lower())
            self.assertNotIn("Invoke-Expression", script)
            self.assertIn("& $PythonPath @arguments", script)

    def test_wrapper_never_executes_unverified_package_bootstrap(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is not installed")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            (package / "bootstrap").mkdir(parents=True)
            marker = root / "package-code-executed.txt"
            (package / "bootstrap/bootstrap.ps1").write_text(
                f"Set-Content -LiteralPath '{marker}' -Value executed\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.repo_root / "scripts/phase3/bootstrap_forward_node.ps1"),
                    "-InstallRoot",
                    str(root / "trusted source spaced-đ"),
                    "-RuntimeRoot",
                    str(root / "runtime spaced-空"),
                    "-OpsRoot",
                    str(root / "ops spaced-空"),
                    "-PackagePath",
                    str(package),
                    "-ExpectedGitSha",
                    self.repo_sha,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("TRUSTED_SOURCE_REQUIRED", completed.stdout + completed.stderr)
            self.assertFalse(marker.exists())

    def test_verified_package_snapshot_is_reused_for_bootstrap_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, trusted_digest = self._production_package(root)
            result = bootstrap_forward_node(
                package,
                install_root=self.repo_root,
                runtime_root=root / "runtime path-đ",
                ops_root=root / "ops path-空",
                expected_git_sha=self.repo_sha,
                expected_trusted_manifest_digest=trusted_digest,
                python_executable=sys.executable,
                require_windows=False,
                platform_name="TEST_ONLY",
            )
            self.assertEqual(result["bootstrap_status"], "PASS")
            self.assertFalse(result["activation_ready"])

    def test_package_tamper_and_missing_index_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = self._package(root)
            target = package / "artifacts/approved.set"
            target.write_text("tampered", encoding="utf-8")
            with self.assertRaises(ArtifactIntegrityError):
                verify_deployment_package(package)
            with self.assertRaises(ArtifactIntegrityError):
                create_deployment_package(
                    root / "bad-package",
                    approved_git_sha=self.repo_sha,
                    repository_url="https://github.com/billy7d/build-bot.git",
                    bundle_manifest=root / "bundle.json",
                    model_bundle=root / "model.json",
                    history_index=root / "not-found.json",
                    ea_ex5=root / "approved.ex5",
                    ea_preset=root / "approved.set",
                    ea_source_revision=self.repo_sha,
                    dependency_manifest=self.repo_root / "docs/trading_agent/forward_ops/dependency-manifest.json",
                )

    def test_package_missing_model_stops_without_fabrication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = self._write_assets(root)
            assets["model"].unlink()
            with self.assertRaises(ArtifactIntegrityError):
                create_deployment_package(
                    root / "package",
                    approved_git_sha=self.repo_sha,
                    repository_url="https://github.com/billy7d/build-bot.git",
                    bundle_manifest=assets["bundle"],
                    model_bundle=assets["model"],
                    history_index=assets["index"],
                    ea_ex5=assets["ea"],
                    ea_preset=assets["preset"],
                    ea_source_revision=self.repo_sha,
                    dependency_manifest=self.repo_root / "docs/trading_agent/forward_ops/dependency-manifest.json",
                )

    def test_bootstrap_is_idempotent_and_never_creates_auth_or_run(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, trusted_digest = self._production_package(root)
            runtime = root / "runtime"
            ops = root / "ops"
            first = bootstrap_forward_node(
                package, install_root=self.repo_root, runtime_root=runtime, ops_root=ops,
                expected_git_sha=self.repo_sha, python_executable=sys.executable,
                expected_trusted_manifest_digest=trusted_digest,
                require_windows=False, platform_name="TEST_ONLY",
            )
            preserved = runtime / "telemetry" / "operator-preserved.txt"
            preserved.write_text("keep", encoding="utf-8")
            second = bootstrap_forward_node(
                package, install_root=self.repo_root, runtime_root=runtime, ops_root=ops,
                expected_git_sha=self.repo_sha, python_executable=sys.executable,
                expected_trusted_manifest_digest=trusted_digest,
                require_windows=False, platform_name="TEST_ONLY",
            )
            self.assertEqual(first["config_path"], second["config_path"])
            self.assertEqual(preserved.read_text(encoding="utf-8"), "keep")
            self.assertFalse((runtime / "config/forward_authorization.json").exists())
            self.assertFalse((runtime / "state/current_run.json").exists())
            self.assertEqual(second["scheduler"], "NOT_INSTALLED_OR_DISABLED")

    def test_bootstrap_existing_authorization_or_wrong_sha_stops(self) -> None:
        with self._environment() as (root, runtime, ops, config):
            config.authorization_path.parent.mkdir(parents=True, exist_ok=True)
            config.authorization_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(NodeOpsError, "EXISTING_AUTHORIZATION"):
                bootstrap_forward_node(
                    root / "package",
                    install_root=self.repo_root,
                    runtime_root=runtime,
                    ops_root=ops,
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest=sha256_file(root / "package/manifest.json"),
                    python_executable=sys.executable,
                    require_windows=False,
                    platform_name="TEST_ONLY",
                )

    def test_handoff_snapshot_is_atomic_and_contains_separate_counts(self) -> None:
        with self._environment() as (_, _, ops, config):
            state = handoff_snapshot(config, ops, next_step="TEST_ONLY inspect")
            self.assertEqual(state["handoff_status"], "PASS")
            self.assertTrue((ops / "CURRENT_HANDOFF.md").is_file())
            self.assertTrue((ops / "current_state.json").is_file())
            self.assertIn("Resolved outcomes", (ops / "CURRENT_HANDOFF.md").read_text(encoding="utf-8"))
            self.assertIn("forward_sample_count", state["runtime_status"])
            self.assertEqual(state["safety"]["execution_authority"], "NONE")

    def test_handoff_failure_does_not_remove_existing_runtime_heartbeat(self) -> None:
        with self._environment() as (_, runtime, ops, config):
            heartbeat = runtime / "state/heartbeat.json"
            heartbeat.parent.mkdir(parents=True, exist_ok=True)
            heartbeat.write_text(json.dumps({"collector_status": "RUNNING", "pid": os.getpid()}), encoding="utf-8")
            with patch("agent.phase3.node_ops.read_runtime_status", side_effect=RuntimeError("TEST_ONLY crash")):
                with self.assertRaises(RuntimeError):
                    handoff_snapshot(config, ops)
            self.assertTrue(heartbeat.is_file())
            self.assertEqual(json.loads(heartbeat.read_text(encoding="utf-8"))["collector_status"], "RUNNING")

    def test_partial_jsonl_line_is_not_ingested(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "primary.jsonl"
            source.write_bytes(b'{"complete":true}\n{"partial":')
            batch = TelemetryFileTailer(source).read_available()
            self.assertEqual(len(batch.records), 1)
            self.assertTrue(batch.partial_final_line)
            self.assertEqual(batch.next_offset, len(b'{"complete":true}\n'))

    def test_health_does_not_call_missing_file_healthy(self) -> None:
        with self._environment() as (_, _, ops, config):
            health = ops_health(config, ops)
            self.assertIn(health["health_status"], {"WARNING", "UNKNOWN", "CRITICAL"})
            self.assertIn("PRIMARY_SOURCE_WAITING", health["reasons"])
            self.assertNotEqual(health["health_status"], "HEALTHY")

    def test_stale_heartbeat_is_not_healthy_even_when_source_file_exists(self) -> None:
        with self._environment() as (_, runtime, ops, config):
            source = config.primary_opportunity
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text('{"schema_version":"phase3-opportunity-observation/1"}\n', encoding="utf-8")
            atomic_write_json(config.heartbeat_path, {
                "schema": "phase3-forward-heartbeat/1",
                "heartbeat_at_utc": "2020-01-01T00:00:00Z",
                "pid": os.getpid(),
                "run_id": "stale-test",
                "collector_status": "RUNNING",
            })
            health = ops_health(config, ops, now="2020-01-01T00:10:00Z")
            self.assertNotEqual(health["health_status"], "HEALTHY")
            self.assertIn("RUN_NOT_REPORTING_HEALTHY", health["reasons"])

    def test_health_reports_disk_or_source_incident_without_fixing_runtime(self) -> None:
        with self._environment() as (_, runtime, ops, config):
            before = (runtime / "config/forward.json").read_bytes()
            health = ops_health(config, ops, warning_disk_free_bytes=10**30, critical_disk_free_bytes=10**30)
            self.assertIn(health["health_status"], {"WARNING", "CRITICAL"})
            self.assertEqual((runtime / "config/forward.json").read_bytes(), before)

    def test_backup_online_restore_and_corruption_rejection(self) -> None:
        with self._environment() as (root, _, ops, config):
            source = self._write_checkpointed_source(config)
            backup = create_backup(config, ops, backup_id="test-valid-backup")
            self.assertEqual(backup["status"], "BACKUP_VALID")
            checked = verify_backup(backup["backup_path"])
            self.assertEqual(checked["status"], "BACKUP_VALID")
            restored = restore_backup(backup["backup_path"], root / "isolated-restore")
            self.assertEqual(restored["status"], "RESTORE_VALIDATED_ISOLATED")
            self.assertEqual(restored["new_run"], "REQUIRES_NEW_AUTHORIZATION")
            raw = Path(backup["backup_path"]) / "raw" / source.name
            raw.write_bytes(raw.read_bytes() + b"corruption")
            self.assertEqual(verify_backup(backup["backup_path"])["status"], "BACKUP_INVALID")

    def test_backup_requires_source_checkpoint(self) -> None:
        with self._environment() as (_, _, ops, config):
            result = create_backup(config, ops, backup_id="test-no-source")
            self.assertEqual(result["status"], "BACKUP_INVALID")
            self.assertIn("PRIMARY_SOURCE_NOT_AVAILABLE", result["verification"]["reasons"])

    def test_backup_requires_frozen_runtime_artifacts(self) -> None:
        with self._environment() as (_, _, ops, config):
            self._write_checkpointed_source(config)
            Path(config.model_bundle_path).unlink()
            result = create_backup(config, ops, backup_id="test-missing-frozen-artifact")
            self.assertEqual(result["status"], "BACKUP_INVALID")
            self.assertIn(
                "REQUIRED_RUNTIME_ARTIFACT_MISSING:model.json",
                result["verification"]["reasons"],
            )

    def test_cross_machine_plan_never_claims_continuity(self) -> None:
        with self._environment() as (root, _, ops, config):
            self._write_checkpointed_source(config)
            backup = create_backup(config, ops, backup_id="test-migration")
            plan = plan_cross_machine_migration(
                backup["backup_path"],
                new_install_root=root / "new-source",
                new_runtime_root=root / "new-runtime",
            )
            self.assertEqual(plan["new_run"], "REQUIRES_NEW_AUTHORIZATION")
            self.assertEqual(plan["cross_run_continuity"], "NOT_CLAIMED")
            self.assertEqual(plan["authorization_reuse"], "NOT_ALLOWED")

    def test_mt5_preflight_requires_real_record_and_journal_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            common = root / "common"
            primary = common / "phase3" / "opportunities.jsonl"
            primary.parent.mkdir(parents=True)
            primary.write_text(json.dumps({"schema_version": "phase3-opportunity-observation/1", "id": "real"}) + "\n", encoding="utf-8")
            terminal = root / "terminal64.exe"
            terminal.write_bytes(b"TEST_ONLY")
            data = root / "data"
            data.mkdir()
            ea = root / "candidate.ex5"
            ea.write_bytes(b"EA")
            preset = root / "candidate.set"
            preset.write_text("Symbol=BTCUSD\n", encoding="utf-8")
            journal = root / "journal.log"
            journal.write_text("authorized on broker\nterminal synchronized\n", encoding="utf-8")
            result = run_mt5_preflight(
                terminal_path=terminal,
                data_directory=data,
                ea_path=ea,
                preset_path=preset,
                primary_source_path=primary,
                ops_root=root / "ops",
                expected_server="TEST-SERVER",
                expected_account="TEST-ACCOUNT",
                common_files_root=common,
                journal_evidence_path=journal,
                market_data_confirmed=True,
                real_record_confirmed=True,
            )
            self.assertEqual(result["preflight_status"], "PASS")
            self.assertEqual(result["checks"]["session_status"], "READY")
            self.assertEqual(result["mt5_source_status"], "REAL_RECORD_PRESENT")

    def test_mt5_preflight_legacy_or_missing_primary_blocks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "EXECUTION_CANDIDATE.jsonl"
            legacy.write_text(json.dumps({"schema_version": "phase3-live-telemetry/1"}) + "\n", encoding="utf-8")
            result = run_mt5_preflight(
                terminal_path=root / "missing-terminal.exe",
                data_directory=root / "missing-data",
                ea_path=root / "missing.ex5",
                preset_path=root / "missing.set",
                primary_source_path=legacy,
                ops_root=root / "ops",
            )
            self.assertEqual(result["preflight_status"], "BLOCKED")
            self.assertEqual(result["mt5_source_status"], "LEGACY_OR_WRONG_SCHEMA")

    def test_takeover_ack_preserves_collector_identity_and_blocks_mismatch(self) -> None:
        with self._environment() as (_, _, ops, config):
            state = handoff_snapshot(config, ops)
            ready = takeover_check(ops, expected_git_sha=state["frozen"]["code_sha"])
            self.assertEqual(ready["status"], "TAKEOVER_READY")
            acknowledged = acknowledge_takeover(ops, agent_id="TEST_ONLY_AGENT", expected_git_sha=state["frozen"]["code_sha"])
            self.assertEqual(acknowledged["status"], "TAKEOVER_READY")
            blocked = takeover_check(ops, expected_run_id="unexpected-run")
            self.assertEqual(blocked["status"], "TAKEOVER_BLOCKED")
            log = (ops / "logs/operator_log.jsonl").read_text(encoding="utf-8")
            self.assertIn("TAKEOVER_ACKNOWLEDGED", log)

    def test_scheduler_duplicate_policy_is_explicit_and_bootstrap_does_not_install_it(self) -> None:
        scheduler_script = (self.repo_root / "scripts/phase3/install_forward_task.ps1").read_text(encoding="utf-8")
        bootstrap_script = (self.repo_root / "scripts/phase3/bootstrap_forward_node.ps1").read_text(encoding="utf-8")
        self.assertIn("-MultipleInstances IgnoreNew", scheduler_script)
        self.assertNotIn("Register-ScheduledTask", bootstrap_script)

    def test_takeover_does_not_depend_on_agent_process(self) -> None:
        with self._environment() as (_, _, ops, config):
            handoff_snapshot(config, ops)
            result = takeover_check(ops)
            self.assertEqual(result["collector_action"], "UNCHANGED")
            self.assertEqual(result["agent_action"], "READ_ONLY")

    def test_source_identity_change_invalidates_backup_source_check(self) -> None:
        with self._environment() as (root, _, ops, config):
            source = self._write_checkpointed_source(config)
            backup = create_backup(config, ops, backup_id="test-source-identity")
            self.assertEqual(backup["status"], "BACKUP_VALID")
            replacement = source.with_suffix(".replacement")
            replacement.write_bytes(source.read_bytes())
            source.unlink()
            replacement.replace(source)
            self.assertEqual(verify_backup(backup["backup_path"], source_path=source)["status"], "BACKUP_INVALID")

    def test_windows_only_bootstrap_is_not_claimed_on_non_windows_host(self) -> None:
        # TEST_ONLY kiểm tra stop gate; không giả danh Windows thật.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, trusted_digest = self._production_package(root)
            with self.assertRaisesRegex(NodeOpsError, "WINDOWS_REQUIRED"):
                bootstrap_forward_node(
                    package,
                    install_root=self.repo_root,
                    runtime_root=root / "runtime",
                    ops_root=root / "ops",
                    expected_git_sha=self.repo_sha,
                    expected_trusted_manifest_digest=trusted_digest,
                    python_executable=sys.executable,
                    require_windows=True,
                    platform_name="Linux",
                )


if __name__ == "__main__":
    unittest.main()
