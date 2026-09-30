"""Offline tests for the dedicated Gate B implementation components.

These tests never launch MT5 or MetaEditor.  The only process termination is
against a harmless Python dummy process created inside a temporary directory.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.phase3.gate_b_monitor.compiler import CompileBlocked, CompileSpec, build_compile_command, verify_compile_output
from agent.phase3.gate_b_monitor.controller import DedicatedAcceptanceController, DedicatedAcceptancePlan
from agent.phase3.gate_b_monitor.evaluator import DEDICATED_ACCEPTANCE_FIELDS, evaluate_dedicated_acceptance
from agent.phase3.gate_b_monitor.process_supervisor import (
    IndependentSupervisorRunner,
    IndependentSupervisorSpec,
    OwnedProcessController,
    ProcessIdentity,
    ProcessSnapshot,
    ProcessStopBlocked,
)
from agent.phase3.gate_b_monitor.provisioning import (
    DedicatedTerminalSpec,
    ProvisioningBlocked,
    provision_empty_layout,
    validate_provision_target,
)
from agent.phase3.gate_b_monitor.startup import (
    StartupConfigBlocked,
    StartupConfigSpec,
    build_terminal_command,
    render_startup_config,
    validate_startup_config,
    write_startup_config,
)


SOURCE = Path(__file__).parents[1] / "phase3" / "gate_b_monitor" / "PR6_ReadOnlyPermissionMonitor_V2.mq5"
SOURCE_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


class DedicatedGateBComponentTests(unittest.TestCase):
    def _provision_spec(self, root: Path, *, target: Path | None = None, common: Path | None = None) -> DedicatedTerminalSpec:
        shared = root / "shared-v26"
        shared.mkdir(exist_ok=True)
        return DedicatedTerminalSpec(
            install_root=target or root / "dedicated",
            data_root=target or root / "dedicated",
            evidence_root=root / "evidence",
            existing_install_root=shared,
            existing_data_root=shared / "data",
            existing_common_root=root / "shared-common",
            dedicated_common_root=common or root / "dedicated-common",
            repository_root=root / "repo",
            required_free_bytes=1,
        )

    def test_provision_validation_is_read_only_and_existing_target_blocks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spec = self._provision_spec(root)
            result = validate_provision_target(spec)
            self.assertEqual(result.status, "PASS")
            self.assertFalse(spec.install_root.exists())
            spec.install_root.mkdir()
            blocked = validate_provision_target(spec)
            self.assertEqual(blocked.status, "BLOCKED")
            self.assertIn("DEDICATED_INSTALL_DESTINATION_EXISTS_NO_OVERWRITE", blocked.reasons)

    def test_provisioning_rejects_shared_overlap_and_common_collision(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            shared.mkdir()
            overlap = DedicatedTerminalSpec(
                install_root=shared / "child",
                data_root=shared / "child",
                evidence_root=root / "evidence",
                existing_install_root=shared,
                existing_data_root=shared / "data",
                existing_common_root=root / "common",
                dedicated_common_root=root / "common",
                required_free_bytes=1,
            )
            result = validate_provision_target(overlap)
            self.assertIn("DEDICATED_INSTALL_OVERLAPS_SHARED_V26", result.reasons)
            self.assertIn("FILE_COMMON_COLLISION_WITH_SHARED_ROOT", result.reasons)

    def test_provisioning_requires_authorization_and_can_only_create_empty_layout(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spec = self._provision_spec(root)
            with self.assertRaisesRegex(ProvisioningBlocked, "PROVISIONING_REQUIRES_APPROVAL_A"):
                provision_empty_layout(spec)
            result = provision_empty_layout(spec, authorized=True)
            self.assertEqual(result.status, "PASS")
            self.assertTrue(result.checks["layout_created"])
            self.assertTrue(spec.install_root.is_dir())

    def _startup_spec(self, root: Path, *, symbol: str = "BTCUSD") -> StartupConfigSpec:
        data = root / "dedicated"
        ex5 = data / "MQL5" / "Experts" / "Advisors" / "PR6_ReadOnlyPermissionMonitor_V2.ex5"
        ex5.parent.mkdir(parents=True, exist_ok=True)
        ex5.write_bytes(b"offline-ex5")
        return StartupConfigSpec(
            terminal_exe=root / "terminal64.exe",
            install_root=root / "dedicated",
            data_root=data,
            config_path=root / "evidence" / "acceptance.ini",
            monitor_ex5=ex5,
            symbol=symbol,
        )

    def test_startup_config_is_exact_and_credential_free(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spec = self._startup_spec(root)
            text = render_startup_config(spec)
            self.assertIn("AllowLiveTrading=0", text)
            self.assertIn("AllowDllImport=0", text)
            self.assertIn("Expert=Advisors\\PR6_ReadOnlyPermissionMonitor_V2.ex5", text)
            self.assertIn("Symbol=BTCUSD", text)
            self.assertIn("Period=H1", text)
            self.assertNotRegex(text.lower(), r"login|password|server")
            result = write_startup_config(spec)
            self.assertEqual(result.status, "PASS")
            valid = validate_startup_config(spec.config_path, spec)
            self.assertEqual(valid.status, "PASS")
            command = build_terminal_command(spec)
            self.assertIn("/portable", command)
            self.assertTrue(any(item.startswith("/config:") for item in command))

    def test_startup_rejects_wrong_symbol_and_config_overwrite(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bad = self._startup_spec(root, symbol="EURUSD")
            with self.assertRaisesRegex(StartupConfigBlocked, "STARTUP_SYMBOL_MISMATCH"):
                render_startup_config(bad)
            good = self._startup_spec(root)
            write_startup_config(good)
            with self.assertRaisesRegex(StartupConfigBlocked, "STARTUP_CONFIG_EXISTS_NO_OVERWRITE"):
                write_startup_config(good)

    def test_startup_rejects_tampered_credentials_and_production_path(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spec = self._startup_spec(root)
            write_startup_config(spec)
            spec.config_path.write_text("[StartUp]\nExpert=Advisors\\PR6_ReadOnlyPermissionMonitor_V2.ex5\nSymbol=BTCUSD\nPeriod=H1\n[Common]\nPassword=secret\n", encoding="utf-8")
            result = validate_startup_config(spec.config_path, spec)
            self.assertEqual(result.status, "BLOCKED")
            self.assertTrue(any("CREDENTIAL" in reason for reason in result.reasons))
            production = StartupConfigSpec(**{**spec.__dict__, "monitor_expert_relative": r"Advisors\Mentor_RSI_MTF_v1.ex5", "config_path": root / "production.ini"})
            with self.assertRaisesRegex(StartupConfigBlocked, "PRODUCTION_EA_PATH_FORBIDDEN"):
                render_startup_config(production)

    def test_compile_plan_verifies_zero_errors_and_does_not_execute_without_approval(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "PR6_ReadOnlyPermissionMonitor_V2.mq5"
            ex5 = root / "PR6_ReadOnlyPermissionMonitor_V2.ex5"
            log = root / "compile.log"
            source.write_text("source", encoding="utf-8")
            ex5.write_bytes(b"ex5")
            log.write_text("PR6_ReadOnlyPermissionMonitor_V2.mq5 - Compile - 0 errors, 0 warnings\n", encoding="utf-8")
            spec = CompileSpec(root / "metaeditor64.exe", source, ex5, log, hashlib.sha256(source.read_bytes()).hexdigest())
            command = build_compile_command(spec)
            self.assertEqual(command[1], f"/compile:{source}")
            result = verify_compile_output(spec)
            self.assertEqual(result.status, "PASS")
            with self.assertRaisesRegex(CompileBlocked, "COMPILE_REQUIRES_APPROVAL_B"):
                from agent.phase3.gate_b_monitor.compiler import run_compile

                run_compile(spec)

    def test_controller_preflight_is_blocked_without_target_and_metaeditor(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            startup = self._startup_spec(root)
            compile_spec = CompileSpec(root / "missing-metaeditor.exe", SOURCE, root / "future.ex5", root / "compile.log", SOURCE_SHA)
            plan = DedicatedAcceptancePlan(
                provision=self._provision_spec(root),
                startup=startup,
                compile=compile_spec,
                source_path=SOURCE,
                source_sha256=SOURCE_SHA,
                evidence_root=root / "evidence",
                protected_v26_roots=(Path(r"D:\Trading\MT5-V26"),),
            )
            result = DedicatedAcceptanceController(plan).preflight()
            self.assertEqual(result.status, "BLOCKED")
            self.assertEqual(result.statuses["DATA_ROOT_ISOLATION"], "BLOCKED")
            self.assertEqual(result.statuses["FILE_COMMON_ISOLATION"], "BLOCKED")
            self.assertEqual(result.statuses["AUTOMATED_LAUNCH"], "BLOCKED")
            self.assertIn("APPROVAL_A_REQUIRED_BEFORE_RUNTIME", result.reasons)

    def test_dedicated_evaluator_does_not_promote_offline_or_monitor_pass_to_gate_b(self) -> None:
        checks = {field: "PASS" for field in DEDICATED_ACCEPTANCE_FIELDS}
        offline = evaluate_dedicated_acceptance(checks, real_execution=False, gate_b_authorized=True)
        self.assertEqual(offline.statuses["MONITOR_PREFLIGHT"], "NOT_RUN")
        self.assertEqual(offline.statuses["GATE_B_OVERALL"], "BLOCKED")
        live = evaluate_dedicated_acceptance(checks, real_execution=True, gate_b_authorized=True)
        self.assertEqual(live.statuses["MONITOR_PREFLIGHT"], "PASS")
        self.assertEqual(live.statuses["GATE_B_OVERALL"], "BLOCKED")

    def test_dedicated_evaluator_marks_missing_prerequisite_blocked(self) -> None:
        checks = {field: "PASS" for field in DEDICATED_ACCEPTANCE_FIELDS}
        checks["INDEPENDENT_STOP"] = "NOT_RUN"
        result = evaluate_dedicated_acceptance(checks, real_execution=True)
        self.assertEqual(result.statuses["MONITOR_PREFLIGHT"], "BLOCKED")
        self.assertEqual(result.statuses["INDEPENDENT_STOP"], "NOT_RUN")

    def _dummy_controller(self, process: subprocess.Popen[bytes], root: Path, *, creation: str = "created") -> OwnedProcessController:
        executable = Path(sys.executable).resolve()
        data_root = root / "dedicated"
        identity = ProcessIdentity(process.pid, executable, creation, "dummy-window", "session-1", data_root)

        def inspect(pid: int) -> ProcessSnapshot | None:
            if pid != process.pid:
                return None
            return ProcessSnapshot(pid, executable, creation, "dummy-window", "session-1", data_root, process.poll() is None, "dummy")

        def terminate(pid: int) -> bool:
            if pid != process.pid:
                return False
            process.terminate()
            return True

        return OwnedProcessController(
            identity,
            inspector=inspect,
            terminator=terminate,
            protected_roots=(Path(r"D:\Trading\MT5-V26"),),
            emergency_authorized=True,
        )

    def test_dummy_process_graceful_timeout_then_exact_emergency_stop(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                controller = self._dummy_controller(process, root)
                receipt = controller.stop_with_grace(lambda _identity: False, grace_seconds=0.05, poll_seconds=0.01)
                self.assertEqual(receipt.status, "PASS")
                self.assertEqual(controller.state, "TERMINATED")
                self.assertTrue(any(event["event"] == "EMERGENCY_TERMINATION_REQUESTED" for event in controller.events))
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)

    def test_process_creation_mismatch_blocks_termination(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                controller = self._dummy_controller(process, root)
                original = controller.inspector
                controller.inspector = lambda pid: ProcessSnapshot(pid, Path(sys.executable), "pid-reused", "dummy-window", "session-1", root / "dedicated", True)
                receipt = controller.emergency_stop()
                self.assertEqual(receipt.status, "BLOCKED")
                self.assertIn("PROCESS_CREATION_TOKEN_MISMATCH", receipt.reasons)
                self.assertIsNotNone(original)
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_protected_shared_v26_target_is_rejected(self) -> None:
        identity = ProcessIdentity(1, Path(r"D:\Trading\MT5-V26\terminal64.exe"), "created", "1", "session", Path(r"D:\Trading\MT5-V26"))
        with self.assertRaisesRegex(ProcessStopBlocked, "PROTECTED_PROCESS_OR_DATA_ROOT"):
            OwnedProcessController(identity, inspector=lambda _pid: None, terminator=lambda _pid: True, protected_roots=(Path(r"D:\Trading\MT5-V26"),), emergency_authorized=True)

    def test_emergency_stop_requires_explicit_authorization(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                controller = self._dummy_controller(process, root)
                controller.emergency_authorized = False
                receipt = controller.emergency_stop()
                self.assertEqual(receipt.status, "BLOCKED")
                self.assertIn("EMERGENCY_STOP_NOT_AUTHORIZED", receipt.reasons)
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_independent_supervisor_requests_soft_stop_on_its_own_clock(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                controller = self._dummy_controller(process, root)
                runner = IndependentSupervisorRunner(
                    IndependentSupervisorSpec(session_id="session-1", soft_stop_seconds=5, hard_deadline_seconds=10),
                    controller,
                    graceful_requester=lambda _identity: True,
                )
                runner.start(monotonic_seconds=100.0)
                tick = runner.tick(monotonic_seconds=105.0)
                self.assertEqual(tick.status, "STOP_REQUESTED")
                self.assertEqual(tick.reason, "SOFT_DEADLINE_540_SECONDS")
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_independent_supervisor_emergency_stops_exact_dummy_at_hard_deadline(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                controller = self._dummy_controller(process, root)
                runner = IndependentSupervisorRunner(
                    IndependentSupervisorSpec(session_id="session-1", soft_stop_seconds=5, hard_deadline_seconds=10),
                    controller,
                    graceful_requester=lambda _identity: True,
                )
                runner.start(monotonic_seconds=100.0)
                runner.tick(monotonic_seconds=105.0)
                tick = runner.tick(monotonic_seconds=110.0)
                self.assertEqual(tick.status, "EMERGENCY_STOP")
                process.wait(timeout=5)
                self.assertIsNotNone(process.poll())
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
