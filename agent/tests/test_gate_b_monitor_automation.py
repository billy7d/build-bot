"""Offline tests for PR #6 Gate B monitor V2 automation.

These tests use temporary files, simulated monotonic time and fake adapters.
They never launch MT5, MetaEditor, a second terminal, a chart, or a trade API.
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from agent.phase3.gate_b_monitor.collector import EvidenceCollector, EvidenceCollectionError, parse_monitor_line
from agent.phase3.gate_b_monitor.evaluator import MonitorEvaluationInput, evaluate_monitor
from agent.phase3.gate_b_monitor.models import ApprovalScope, CapabilityMatrix, PermissionSample
from agent.phase3.gate_b_monitor.orchestrator import (
    AcceptanceOrchestrator,
    AtomicRunLock,
    AutomationBlocked,
    ChartHandle,
    ExistingRunLock,
    capability_matrix_from_cua_state,
)
from agent.phase3.gate_b_monitor.supervisor import SessionSupervisor, SupervisorBlocked, SupervisorState


SOURCE = Path(__file__).parents[1] / "phase3" / "gate_b_monitor" / "PR6_ReadOnlyPermissionMonitor_V2.mq5"
SOURCE_SHA = "a" * 64
EX5_SHA = "b" * 64


def full_capability() -> CapabilityMatrix:
    return CapabilityMatrix(
        native_mt5_surface=True,
        compile_exact_source=True,
        create_chart=True,
        attach_exactly_once=True,
        read_chart_identity=True,
        prove_chart_ownership=True,
        request_monitor_stop=True,
        prove_ea_removed=True,
        close_owned_chart=True,
        prove_chart_closed=True,
        supervisor_independent_of_chat=True,
        independent_stop=True,
        evidence_collection=True,
    )


def scope(**overrides: object) -> ApprovalScope:
    values: dict[str, object] = {
        "status": "APPROVED",
        "operator_id": "billy7d",
        "source_sha256": SOURCE_SHA,
        "ex5_sha256": EX5_SHA,
        "account": "414060440",
        "server": "Exness-MT5Trial6",
    }
    values.update(overrides)
    return ApprovalScope.from_mapping(values)


def sample(
    *,
    session_id: str = "session-1",
    chart_id: int = 101,
    seconds: int = 0,
    monotonic_ms: int | None = None,
) -> PermissionSample:
    return PermissionSample(
        session_id=session_id,
        timestamp_utc=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds),
        monotonic_ms=seconds * 1000 if monotonic_ms is None else monotonic_ms,
        account="414060440",
        server="Exness-MT5Trial6",
        symbol="BTCUSD",
        timeframe="H1",
        chart_id=chart_id,
        account_trade_mode=0,
        account_trade_allowed=0,
        account_trade_expert=1,
        terminal_connected=1,
        terminal_trade_allowed=0,
        mql_trade_allowed=0,
        mql_program_type=2,
        scope="monitor_ea",
    )


class GateBMonitorAutomationTests(unittest.TestCase):
    def test_v2_source_is_timer_ea_and_read_only(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        commentless = re.sub(r"//.*", "", text)
        self.assertNotRegex(commentless, r"(?m)^\s*#include")
        for forbidden in ("OrderSend", "OrderSendAsync", "CTrade", "FileOpen", "FileWrite", "WebRequest", "ChartClose", "AccountLogin", "SocketCreate"):
            self.assertNotIn(forbidden, commentless)
        self.assertIn("int OnInit()", text)
        self.assertIn("EventSetTimer(1)", text)
        self.assertIn("void OnTimer()", text)
        self.assertIn("EventKillTimer()", text)
        self.assertIn("GetTickCount64()", text)
        self.assertIn("ExpertRemove()", text)
        self.assertNotIn("void OnStart()", text)

    def test_v2_python_dependencies_are_stdlib_or_local_only(self) -> None:
        allowed_external = {"__future__", "ctypes", "dataclasses", "datetime", "enum", "hashlib", "json", "os", "pathlib", "re", "secrets", "shutil", "subprocess", "tempfile", "time", "typing"}
        for path in SOURCE.parent.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?m)^\s*(?:import|from)\s+(?:requests|pyautogui|selenium|MetaTrader|win32)\b")
            for module in re.findall(r"(?m)^\s*import\s+([A-Za-z_][A-Za-z0-9_]*)|^\s*from\s+([A-Za-z_][A-Za-z0-9_]*)", text):
                name = module[0] or module[1]
                self.assertTrue(name in allowed_external or name == "agent", f"unexpected dependency: {name}")

    def test_empty_native_surface_blocks_without_lock_or_attach(self) -> None:
        capabilities = capability_matrix_from_cua_state({"apps": []})
        self.assertEqual(capabilities.classification.value, "NO_SAFE_RUNTIME")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "monitor.mq5"
            ex5 = root / "monitor.ex5"
            source.write_text("source", encoding="utf-8")
            ex5.write_bytes(b"binary")
            monitor = AcceptanceOrchestrator(
                scope=scope(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), ex5_sha256=hashlib.sha256(ex5.read_bytes()).hexdigest()),
                source_path=source,
                ex5_path=ex5,
                evidence_root=root / "evidence",
                capabilities=capabilities,
            )
            result = monitor.precheck()
            self.assertEqual(result.status, "BLOCKED")
            self.assertIn("AUTHORIZED_MT5_CONTROL_SURFACE_UNAVAILABLE", result.reasons)
            with self.assertRaises(AutomationBlocked):
                monitor.start_once()
            self.assertFalse((root / "evidence" / "run.lock").exists())

    def test_atomic_lock_refuses_existing_lock(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.lock"
            first = AtomicRunLock(path, run_id="one")
            first.acquire()
            second = AtomicRunLock(path, run_id="two")
            with self.assertRaises(ExistingRunLock):
                second.acquire()
            first.release()

    def test_orchestrator_never_retries_after_attach(self) -> None:
        class FakeSurface:
            def create_chart(self, symbol: str, timeframe: str, owner_token: str) -> ChartHandle:
                return ChartHandle(101, symbol, timeframe, owner_token)

            def attach_monitor(self, chart: ChartHandle, source_sha256: str, ex5_sha256: str, session_id: str) -> None:
                return None

            def request_monitor_stop(self, chart: ChartHandle, session_id: str) -> bool:
                return True

            def confirm_monitor_removed(self, chart: ChartHandle, session_id: str) -> bool:
                return True

            def close_owned_chart(self, chart: ChartHandle, owner_token: str) -> None:
                return None

            def confirm_chart_closed(self, chart: ChartHandle, owner_token: str) -> bool:
                return True

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "monitor.mq5"
            ex5 = root / "monitor.ex5"
            source.write_text("source", encoding="utf-8")
            ex5.write_bytes(b"binary")
            orchestrator = AcceptanceOrchestrator(
                scope=scope(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), ex5_sha256=hashlib.sha256(ex5.read_bytes()).hexdigest()),
                source_path=source,
                ex5_path=ex5,
                evidence_root=root / "evidence",
                capabilities=full_capability(),
                control_surface=FakeSurface(),
            )
            orchestrator.start_once()
            with self.assertRaises(AutomationBlocked):
                orchestrator.start_once()
            self.assertEqual(orchestrator.run.attach_count, 1)

    def test_orchestrator_does_not_promote_rejected_stop_request(self) -> None:
        class RejectingSurface:
            def create_chart(self, symbol: str, timeframe: str, owner_token: str) -> ChartHandle:
                return ChartHandle(101, symbol, timeframe, owner_token)

            def attach_monitor(self, chart: ChartHandle, source_sha256: str, ex5_sha256: str, session_id: str) -> None:
                return None

            def request_monitor_stop(self, chart: ChartHandle, session_id: str) -> bool:
                return False

            def confirm_monitor_removed(self, chart: ChartHandle, session_id: str) -> bool:
                return False

            def close_owned_chart(self, chart: ChartHandle, owner_token: str) -> None:
                return None

            def confirm_chart_closed(self, chart: ChartHandle, owner_token: str) -> bool:
                return False

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "monitor.mq5"
            ex5 = root / "monitor.ex5"
            source.write_text("source", encoding="utf-8")
            ex5.write_bytes(b"binary")
            orchestrator = AcceptanceOrchestrator(
                scope=scope(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), ex5_sha256=hashlib.sha256(ex5.read_bytes()).hexdigest()),
                source_path=source,
                ex5_path=ex5,
                evidence_root=root / "evidence",
                capabilities=full_capability(),
                control_surface=RejectingSurface(),
            )
            orchestrator.start_once()
            with self.assertRaisesRegex(AutomationBlocked, "STOP_REQUEST_REJECTED"):
                orchestrator.request_stop()
            self.assertEqual(orchestrator.run.stop_count, 0)
            with self.assertRaisesRegex(AutomationBlocked, "FAILED_RUN_NO_STOP_RETRY"):
                orchestrator.request_stop()

    def test_orchestrator_keeps_chart_closure_unconfirmed_when_adapter_cannot_prove_it(self) -> None:
        class NoChartCloseProofSurface:
            def create_chart(self, symbol: str, timeframe: str, owner_token: str) -> ChartHandle:
                return ChartHandle(101, symbol, timeframe, owner_token)

            def attach_monitor(self, chart: ChartHandle, source_sha256: str, ex5_sha256: str, session_id: str) -> None:
                return None

            def request_monitor_stop(self, chart: ChartHandle, session_id: str) -> bool:
                return True

            def confirm_monitor_removed(self, chart: ChartHandle, session_id: str) -> bool:
                return True

            def close_owned_chart(self, chart: ChartHandle, owner_token: str) -> None:
                return None

            def confirm_chart_closed(self, chart: ChartHandle, owner_token: str) -> bool:
                return False

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "monitor.mq5"
            ex5 = root / "monitor.ex5"
            source.write_text("source", encoding="utf-8")
            ex5.write_bytes(b"binary")
            orchestrator = AcceptanceOrchestrator(
                scope=scope(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), ex5_sha256=hashlib.sha256(ex5.read_bytes()).hexdigest()),
                source_path=source,
                ex5_path=ex5,
                evidence_root=root / "evidence",
                capabilities=full_capability(),
                control_surface=NoChartCloseProofSurface(),
            )
            orchestrator.start_once()
            orchestrator.request_stop()
            self.assertFalse(orchestrator.confirm_cleanup())
            self.assertEqual(orchestrator.run.state.value, "EA_REMOVED")

    def test_supervisor_requires_independent_stop_before_attach(self) -> None:
        supervisor = SessionSupervisor(session_id="session-1", independent_stop=False)
        with self.assertRaises(SupervisorBlocked):
            supervisor.start(monotonic_seconds=10.0, start_utc=datetime.now(UTC))
        self.assertEqual(supervisor.state, SupervisorState.FAILED)

    def test_supervisor_requests_exact_stop_at_soft_deadline_with_chart_binding(self) -> None:
        calls: list[tuple[str, int, str]] = []

        def stop(session_id: str, chart_id: int, reason: str) -> bool:
            calls.append((session_id, chart_id, reason))
            return True

        supervisor = SessionSupervisor(session_id="session-1", independent_stop=True, stop_callback=stop)
        supervisor.start(monotonic_seconds=100.0, start_utc=datetime.now(UTC))
        supervisor.attach(chart_id=101, monotonic_seconds=100.0)
        decision = supervisor.observe_sample(sample(), monotonic_seconds=100.0)
        self.assertFalse(decision.requested)
        decision = supervisor.tick(monotonic_seconds=640.0)
        self.assertTrue(decision.requested)
        self.assertEqual(decision.reason, "SOFT_DEADLINE_540_SECONDS")
        self.assertEqual(calls, [("session-1", 101, "SOFT_DEADLINE_540_SECONDS")])

    def test_supervisor_separates_self_stop_from_removal_and_chart_close(self) -> None:
        supervisor = SessionSupervisor(session_id="session-1", independent_stop=True, stop_callback=lambda *_args: True)
        supervisor.start(monotonic_seconds=0.0, start_utc=datetime.now(UTC))
        supervisor.attach(chart_id=101, monotonic_seconds=0.0)
        supervisor.mark_self_stop_requested(monotonic_seconds=10.0)
        self.assertEqual(
            supervisor.stop_evidence,
            {
                "SELF_STOP_REQUESTED": True,
                "EA_REMOVAL_CONFIRMED": False,
                "CHART_CLOSURE_CONFIRMED": False,
                "INDEPENDENT_STOP_AVAILABLE": True,
            },
        )
        with self.assertRaises(SupervisorBlocked):
            supervisor.finish(monotonic_seconds=11.0)
        supervisor.mark_ea_removed(monotonic_seconds=12.0)
        supervisor.mark_chart_closed(monotonic_seconds=13.0)
        supervisor.finish(monotonic_seconds=14.0)
        self.assertTrue(supervisor.stop_evidence["EA_REMOVAL_CONFIRMED"])
        self.assertTrue(supervisor.stop_evidence["CHART_CLOSURE_CONFIRMED"])

    def test_supervisor_fails_closed_when_cleanup_misses_hard_deadline(self) -> None:
        supervisor = SessionSupervisor(session_id="session-1", independent_stop=True, stop_callback=lambda *_args: True)
        supervisor.start(monotonic_seconds=0.0, start_utc=datetime.now(UTC))
        supervisor.attach(chart_id=101, monotonic_seconds=0.0)
        supervisor.tick(monotonic_seconds=540.0)
        decision = supervisor.tick(monotonic_seconds=600.0)
        self.assertFalse(decision.requested)
        self.assertEqual(decision.reason, "HARD_DEADLINE_600_SECONDS_CLEANUP_NOT_CONFIRMED")
        self.assertEqual(supervisor.state, SupervisorState.FAILED)

    def test_supervisor_stops_on_within_session_gap(self) -> None:
        calls: list[str] = []
        supervisor = SessionSupervisor(session_id="session-1", independent_stop=True, stop_callback=lambda _sid, _chart, reason: calls.append(reason) or True)
        supervisor.start(monotonic_seconds=0.0, start_utc=datetime.now(UTC))
        supervisor.attach(chart_id=101, monotonic_seconds=0.0)
        supervisor.observe_sample(sample(), monotonic_seconds=0.0)
        decision = supervisor.observe_sample(sample(seconds=91), monotonic_seconds=91.0)
        self.assertTrue(decision.requested)
        self.assertEqual(decision.reason, "WITHIN_SESSION_SAMPLE_GAP_OVER_90_SECONDS")
        self.assertEqual(calls, ["WITHIN_SESSION_SAMPLE_GAP_OVER_90_SECONDS"])

    def _evaluation(self, *, samples: tuple[PermissionSample, ...], **overrides: object):
        values: dict[str, object] = {
            "scope": scope(),
            "samples": samples,
            "start_utc": datetime(2026, 1, 1, tzinfo=UTC),
            "end_utc": datetime(2026, 1, 1, 0, 9, 59, tzinfo=UTC),
            "chart_ids": (101,),
            "session_ids": ("session-1",),
            "chart_closed_confirmed": True,
            "ea_removed_confirmed": True,
            "stop_requested_seconds": 540.0,
            "compile_errors": 0,
            "compile_warnings": 0,
            "source_sha256": SOURCE_SHA,
            "ex5_sha256": EX5_SHA,
            "capability": full_capability(),
            "authoritative_account_history": False,
        }
        values.update(overrides)
        return evaluate_monitor(MonitorEvaluationInput(**values))

    def test_evaluator_separates_functional_pass_from_procedural_fail(self) -> None:
        result = self._evaluation(samples=(sample(), sample(seconds=60)), chart_ids=(101, 202), session_ids=("session-1", "session-2"), extra_diagnostic_executions=2)
        self.assertEqual(result.statuses["FUNCTIONAL_EVIDENCE"], "PASS")
        self.assertEqual(result.statuses["PROCEDURAL_COMPLIANCE"], "FAIL")
        self.assertEqual(result.statuses["MONITOR_PREFLIGHT"], "FAIL")
        self.assertEqual(result.statuses["GATE_B_OVERALL"], "BLOCKED")

    def test_evaluator_rejects_permission_transition_deadline_and_trade_line(self) -> None:
        bad = replace(sample(), account_trade_allowed=1)
        result = self._evaluation(
            samples=(bad, sample(seconds=60)),
            end_utc=datetime(2026, 1, 1, 0, 11, tzinfo=UTC),
            trade_matches=("trade request",),
        )
        self.assertEqual(result.statuses["FUNCTIONAL_EVIDENCE"], "FAIL")
        self.assertEqual(result.statuses["PROCEDURAL_COMPLIANCE"], "FAIL")
        self.assertIn("HARD_DEADLINE_EXCEEDED", result.reasons["PROCEDURAL_COMPLIANCE"])
        self.assertIn("TRADE_ACTIVITY_IN_EVIDENCE", result.reasons["PROCEDURAL_COMPLIANCE"])

    def test_evaluator_requires_cleanup_for_preflight_pass(self) -> None:
        result = self._evaluation(samples=(sample(), sample(seconds=60)), chart_closed_confirmed=False)
        self.assertEqual(result.statuses["PROCEDURAL_COMPLIANCE"], "INCONCLUSIVE")
        self.assertEqual(result.statuses["MONITOR_PREFLIGHT"], "BLOCKED")

    def test_collector_hashes_raw_journal_and_rejects_missing_window(self) -> None:
        line = (
            "MO 0 00:00:00.000 PR6_READ_ONLY_PERMISSION_MONITOR_V2/1 "
            "session_id=session-1 timestamp_utc=2026-01-01T00:00:00Z "
            "monotonic_ms=0 account=414060440 server=Exness-MT5Trial6 "
            "symbol=BTCUSD timeframe=H1 chart_id=101 account_trade_mode=0 "
            "account_trade_allowed=0 account_trade_expert=1 terminal_connected=1 "
            "terminal_trade_allowed=0 mql_trade_allowed=0 mql_program_type=2 "
            "scope=monitor_ea reason=INITIAL\n"
        )
        self.assertIsNotNone(parse_monitor_line(line, 1))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            journal = root / "20260101.log"
            journal.write_text(line, encoding="utf-8")
            collector = EvidenceCollector(root / "evidence")
            payload = collector.collect(
                journal_path=journal,
                session_id="session-1",
                chart_id=101,
                start_utc=datetime(2026, 1, 1, tzinfo=UTC),
                end_utc=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
                source_sha256=SOURCE_SHA,
                ex5_sha256=EX5_SHA,
                ea_removed_confirmed=True,
                chart_closed_confirmed=True,
            )
            self.assertEqual(payload["raw_journal"]["source_sha256"], hashlib.sha256(journal.read_bytes()).hexdigest())
            evidence = collector.write_payload(payload)
            self.assertTrue(evidence.is_file())
            with self.assertRaises(EvidenceCollectionError):
                collector.collect(
                    journal_path=journal,
                    session_id="missing",
                    chart_id=101,
                    start_utc=datetime(2026, 1, 2, tzinfo=UTC),
                    end_utc=datetime(2026, 1, 2, 0, 1, tzinfo=UTC),
                    source_sha256=SOURCE_SHA,
                    ex5_sha256=EX5_SHA,
                )


if __name__ == "__main__":
    unittest.main()
