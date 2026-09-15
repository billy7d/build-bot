"""Runtime config Phase 3 với execution authority bị khóa ở NONE."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from ..features.fingerprint import fingerprint
from .models import RUN_MODES


class Phase3ConfigError(ValueError):
    """Config vi phạm one-way/shadow-only contract."""


def _enabled(value: Any) -> bool:
    """Nhận diện cả boolean JSON và chuỗi cấu hình dễ gây nhầm."""

    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Phase3Config:
    mode: str = "SMOKE"
    execution_mode: str = "NONE"
    bundle_id: str | None = None
    telemetry_source: str = ""
    db_path: str = "data/trading_memory.db"
    report_dir: str = "reports/trading_agent/phase3"
    require_closed_bar: bool = True
    max_event_age_seconds: int | None = None
    future_tolerance_seconds: int = 0
    classification_min_resolved: int = 500
    regression_min_resolved: int = 500
    random_seed: int = 42

    def __post_init__(self) -> None:
        mode = str(self.mode).upper()
        if mode not in RUN_MODES:
            raise Phase3ConfigError(f"unsupported Phase 3 mode: {self.mode!r}")
        if str(self.execution_mode).upper() != "NONE":
            raise Phase3ConfigError("Phase 3 execution_mode must be NONE")
        if self.max_event_age_seconds is not None and self.max_event_age_seconds < 0:
            raise Phase3ConfigError("max_event_age_seconds must be non-negative")
        if self.future_tolerance_seconds < 0:
            raise Phase3ConfigError("future_tolerance_seconds must be non-negative")
        if self.classification_min_resolved < 1 or self.regression_min_resolved < 1:
            raise Phase3ConfigError("evidence thresholds must be positive")

    @property
    def live_execution_enabled(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["mode"] = str(self.mode).upper()
        value["execution_mode"] = "NONE"
        value["live_execution_enabled"] = False
        value["execution_authority"] = "NONE"
        value["trade_control_authority"] = "NONE"
        value["position_control_authority"] = "NONE"
        value["risk_control_authority"] = "NONE"
        return value

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Phase3Config":
        if _enabled(payload.get("live_execution_enabled")) or _enabled(payload.get("execution_enabled")):
            raise Phase3ConfigError("Phase 3 execution flags must be disabled")
        for key in (
            "execution_authority", "trade_control_authority",
            "position_control_authority", "risk_control_authority",
        ):
            if key in payload and str(payload[key]).upper() != "NONE":
                raise Phase3ConfigError(f"Phase 3 {key} must be NONE")
        values = {
            key: payload[key]
            for key in cls.__dataclass_fields__
            if key in payload and key not in {"live_execution_enabled"}
        }
        return cls(**values)


def load_config(path: str | Path | None = None) -> Phase3Config:
    if path is None:
        return Phase3Config()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise Phase3ConfigError("Phase 3 config JSON must be an object")
    return Phase3Config.from_dict(payload)


def write_config(config: Phase3Config, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["Phase3Config", "Phase3ConfigError", "load_config", "write_config"]
