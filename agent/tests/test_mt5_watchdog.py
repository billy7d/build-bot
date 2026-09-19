"""Safety and recovery contract tests for the telemetry-only MT5 watchdog."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

from agent.phase3.mt5_watchdog import (
    MT5InstanceSpec,
    WatchdogConfig,
    inspect_instance,
    recover_once,
    watchdog_health,
    watchdog_status,
)


class Mt5WatchdogTests(unittest.TestCase):
    def _fixture(self, root: Path, *, now: str = "2026-01-01T00:00:00Z") -> tuple[MT5InstanceSpec, WatchdogConfig, dict[str, object]]:
        install = root / "MT5-V26"
        install.mkdir()
        terminal = install / "terminal64.exe"
        terminal.write_bytes(b"terminal")
        data = install
        ea = install / "MQL5" / "Experts" / "approved.ex5"
        preset = install / "MQL5" / "Presets" / "approved.set"
        ea.parent.mkdir(parents=True)
        preset.parent.mkdir(parents=True)
        ea.write_bytes(b"approved-ex5")
        preset.write_text("Symbol=BTCUSD\n", encoding="utf-8")
        telemetry = root / "common" / "phase3" / "opportunities.jsonl"
        telemetry.parent.mkdir(parents=True)
        telemetry.write_text(
            "".join(json.dumps({"schema_version": "phase3-opportunity-observation/1", "sequence": n, "event_timestamp_utc": now}) + "\n" for n in (1, 2)),
            encoding="utf-8",
        )
        permission = root / "permission.json"
        permission.write_text(json.dumps({
            "auto_trading": False,
            "terminal_trade_allowed": False,
            "mql_trade_allowed": False,
            "live_execution_enabled": False,
            "execution_authority": "NONE",
            "trade_control_authority": "NONE",
        }), encoding="utf-8")
        ea_status = root / "ea-status.json"
        ea_status.write_text(json.dumps({
            "attached": True,
            "ea_name": "ApprovedTelemetryEA",
            "account_identity": "414086321",
            "server_identity": "Exness-MT5Trial6",
            "on_init": "PASS",
            "symbol": "BTCUSD",
            "timeframe": "H1",
        }), encoding="utf-8")
        spec = MT5InstanceSpec(
            name="V26",
            terminal_exe=terminal,
            install_directory=install,
            data_directory=data,
            profile="Profile\\V26",
            ea_name="ApprovedTelemetryEA",
            ea_ex5_path=ea,
            preset_path=preset,
            account_identity="414086321",
            server_identity="Exness-MT5Trial6",
            telemetry_path=telemetry,
            approved_ex5_sha256=hashlib.sha256(ea.read_bytes()).hexdigest(),
            approved_preset_sha256=hashlib.sha256(preset.read_bytes()).hexdigest(),
            trading_permission_evidence_path=permission,
            ea_status_evidence_path=ea_status,
            launch_args=("/profile:Profile\\V26",),
            chart_symbol="BTCUSD",
            timeframe="H1",
        )
        config = WatchdogConfig(instances=(spec,), ops_root=root / "ops")
        process = {"ProcessId": 101, "ExecutablePath": str(terminal), "CommandLine": f'"{terminal}" /profile:Profile\\V26'}
        return spec, config, {"process": process, "now": now, "permission": permission, "ea_status": ea_status}

    @staticmethod
    def _provider(*rows: dict[str, object]):
        return lambda: (list(rows), None)

    def test_running_exact_instance_is_healthy_and_no_action(self) -> None:
        with TemporaryDirectory() as directory:
            spec, config, fx = self._fixture(Path(directory))
            provider = self._provider(fx["process"])
            status = watchdog_status(config, now=fx["now"], process_provider=provider)
            self.assertEqual(status["status"], "PASS")
            self.assertEqual(status["instances"][0]["health_status"], "HEALTHY")
            result = recover_once(config, now=fx["now"], process_provider=provider, dry_run=True)
            self.assertEqual(result["instances"][0]["status"], "NO_ACTION_RUNNING")

    def test_absent_terminal_dry_run_is_eligible_without_starting(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            popen = Mock()
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=True, popen=popen)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["instances"][0]["status"], "DRY_RUN_ELIGIBLE")
            popen.assert_not_called()

    def test_absent_terminal_starts_exact_command_and_persists_attempt(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            process = Mock(pid=4242)
            popen = Mock(return_value=process)
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=False, popen=popen)
            self.assertEqual(result["instances"][0]["status"], "STARTED_PENDING_VERIFICATION")
            popen.assert_called_once()
            command = popen.call_args.args[0]
            self.assertEqual(command[0], str(config.instances[0].terminal_exe))
            self.assertFalse(popen.call_args.kwargs["shell"])
            state = json.loads((config.ops_root / "watchdog" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["instances"]["V26"]["last_pid"], 4242)

    def test_auto_trading_on_is_hard_stop(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            payload = json.loads(fx["permission"].read_text(encoding="utf-8"))
            payload["auto_trading"] = True
            fx["permission"].write_text(json.dumps(payload), encoding="utf-8")
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=True)
            self.assertEqual(result["instances"][0]["status"], "UNSAFE_TO_RESTART")
            self.assertIn("TRADING_PERMISSION_NOT_DISABLED:auto_trading", result["instances"][0]["inspection"]["gate_reasons"])

    def test_wrong_artifact_hash_is_hard_stop(self) -> None:
        with TemporaryDirectory() as directory:
            spec, config, fx = self._fixture(Path(directory))
            bad = MT5InstanceSpec(**{**spec.__dict__, "approved_ex5_sha256": "0" * 64})
            config = WatchdogConfig(instances=(bad,), ops_root=config.ops_root)
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=True)
            self.assertIn("EA_SHA256_MISMATCH", result["instances"][0]["inspection"]["gate_reasons"])

    def test_wrong_account_or_server_evidence_is_hard_stop(self) -> None:
        with TemporaryDirectory() as directory:
            spec, config, fx = self._fixture(Path(directory))
            fx["ea_status"].write_text(json.dumps({"attached": True, "ea_name": spec.ea_name, "account_identity": "wrong", "server_identity": "wrong", "on_init": "PASS"}), encoding="utf-8")
            result = inspect_instance(spec, now=fx["now"], process_records=[])
            self.assertIn("EA_ACCOUNT_MISMATCH", result["gate_reasons"])
            self.assertIn("EA_SERVER_MISMATCH", result["gate_reasons"])

    def test_sequence_gap_and_invalid_line_hard_stop(self) -> None:
        with TemporaryDirectory() as directory:
            spec, _, fx = self._fixture(Path(directory))
            spec.telemetry_path.write_text(
                '{"schema_version":"phase3-opportunity-observation/1","sequence":1,"event_timestamp_utc":"2026-01-01T00:00:00Z"}\n'
                '{"schema_version":"phase3-opportunity-observation/1","sequence":3,"event_timestamp_utc":"2026-01-01T00:00:00Z"}\n'
                '{bad}\n', encoding="utf-8")
            result = inspect_instance(spec, now=fx["now"], process_records=[])
            self.assertEqual(result["telemetry"]["sequence_status"], "GAP")
            self.assertIn("TELEMETRY_SEQUENCE_GAP", result["gate_reasons"])

    def test_circuit_breaker_persists_and_blocks_third_attempt(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            state_path = config.ops_root / "watchdog" / "state.json"
            state_path.parent.mkdir(parents=True)
            epoch = 1767225600.0
            state_path.write_text(json.dumps({"schema": "phase3-mt5-watchdog/1", "instances": {"V26": {"restart_attempts_epoch": [epoch, epoch + 1]}}}), encoding="utf-8")
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=True)
            self.assertEqual(result["instances"][0]["status"], "CIRCUIT_OPEN")

    def test_malformed_state_blocks_without_recovery(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            state_path = config.ops_root / "watchdog" / "state.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("not-json", encoding="utf-8")
            result = recover_once(config, now=fx["now"], process_provider=self._provider(), dry_run=True)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["instances"][0]["status"], "UNSAFE_TO_RESTART")

    def test_duplicate_exact_process_is_blocked(self) -> None:
        with TemporaryDirectory() as directory:
            _, config, fx = self._fixture(Path(directory))
            rows = [fx["process"], {**fx["process"], "ProcessId": 102}]
            result = watchdog_health(config, now=fx["now"], process_provider=lambda: (rows, None))
            self.assertEqual(result["health_status"], "CRITICAL")
            self.assertIn("DUPLICATE_EXACT_TERMINAL_INSTANCE", result["reasons"])


if __name__ == "__main__":
    unittest.main()
