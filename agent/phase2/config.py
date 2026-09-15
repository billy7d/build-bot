"""Versioned Phase 2 configuration with conservative fixed defaults."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..features.splits import SplitConfig
from ..scoring.train import ModelConfig
from ..similarity.models import SimilarityConfig


DEFAULT_CONFIG_PATH = Path(__file__).with_name("default_config.json")


@dataclass(frozen=True)
class Phase2Config:
    version: str = "phase2-config/1"
    feature_set_version: str = "feature-store/1"
    split: SplitConfig = field(default_factory=lambda: SplitConfig(
        version="phase2-split/1",
        train_end="2024-01-01T00:00:00Z",
        validation_end="2025-01-01T00:00:00Z",
        forward_start=None,
    ))
    similarity: SimilarityConfig = field(default_factory=SimilarityConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    regime_version: str = "regime/1"
    random_seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_set_version": self.feature_set_version,
            "split": self.split.to_dict(),
            "similarity": self.similarity.to_dict(),
            "model": self.model.to_dict(),
            "regime_version": self.regime_version,
            "random_seed": self.random_seed,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Phase2Config":
        split_payload = dict(payload.get("split", {}))
        similarity_payload = dict(payload.get("similarity", {}))
        model_payload = dict(payload.get("model", {}))
        return cls(
            version=str(payload.get("version", "phase2-config/1")),
            feature_set_version=str(payload.get("feature_set_version", "feature-store/1")),
            split=SplitConfig(**{key: value for key, value in split_payload.items() if key in SplitConfig.__dataclass_fields__}),
            similarity=SimilarityConfig.from_dict(similarity_payload),
            model=ModelConfig.from_dict(model_payload),
            regime_version=str(payload.get("regime_version", "regime/1")),
            random_seed=int(payload.get("random_seed", 42)),
        )


def load_config(path: str | Path | None = None) -> Phase2Config:
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    if not target.exists():
        return Phase2Config()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Phase 2 config must be an object: {target}")
    return Phase2Config.from_dict(payload)


__all__ = ["DEFAULT_CONFIG_PATH", "Phase2Config", "load_config"]
