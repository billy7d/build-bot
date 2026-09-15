"""Naive priors used as mandatory audit benchmarks."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .labels import build_expected_r_label, build_label
from .models import PriorModel


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _canonical_map(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        identifier = str(row.get("canonical_opportunity_id") or "")
        if not identifier:
            raise ValueError("baseline input requires canonical_opportunity_id")
        if identifier in by_id:
            raise ValueError(f"baseline input contains duplicate canonical sample: {identifier}")
        by_id[identifier] = row
    return by_id


def fit_unconditional_prior(rows: Iterable[Mapping[str, Any]], train_ids: Iterable[str]) -> PriorModel:
    by_id = _canonical_map(rows)
    ids = tuple(sorted({str(value) for value in train_ids}))
    labels = [build_label(by_id[item]) for item in ids if item in by_id]
    labels = [int(value) for value in labels if value in (0, 1)]
    targets = [build_expected_r_label(by_id[item]) for item in ids if item in by_id]
    targets = [float(value) for value in targets if value is not None]
    return PriorModel("unconditional_prior", _mean(labels), _mean(targets), len(labels), len(targets), ids)


def fit_regime_prior(
    rows: Iterable[Mapping[str, Any]],
    train_ids: Iterable[str],
    regimes: Mapping[str, Any],
) -> PriorModel:
    by_id = _canonical_map(rows)
    ids = tuple(sorted({str(value) for value in train_ids}))
    grouped: dict[str, dict[str, list[float]]] = {}
    for identifier in ids:
        if identifier not in by_id:
            continue
        regime = regimes.get(identifier)
        if hasattr(regime, "composite_regime"):
            group = str(regime.composite_regime)
        elif isinstance(regime, Mapping):
            group = str(regime.get("composite_regime", "UNKNOWN"))
        else:
            group = str(regime or "UNKNOWN")
        bucket = grouped.setdefault(group, {"labels": [], "targets": []})
        label = build_label(by_id[identifier])
        target = build_expected_r_label(by_id[identifier])
        if label in (0, 1):
            bucket["labels"].append(float(label))
        if target is not None:
            bucket["targets"].append(float(target))
    group_payload = {
        group: {
            "probability": _mean(bucket["labels"]),
            "expected_r": _mean(bucket["targets"]),
            "support": len(bucket["labels"]),
            "expected_support": len(bucket["targets"]),
        }
        for group, bucket in sorted(grouped.items())
    }
    all_labels = [value for bucket in grouped.values() for value in bucket["labels"]]
    all_targets = [value for bucket in grouped.values() for value in bucket["targets"]]
    return PriorModel(
        "regime_prior", _mean(all_labels), _mean(all_targets), len(all_labels), len(all_targets), ids, group_payload
    )


def prior_prediction(model: PriorModel, row: Mapping[str, Any], regime: Any = None) -> tuple[float | None, float | None]:
    if model.model_type != "regime_prior":
        return model.probability, model.expected_r
    if hasattr(regime, "composite_regime"):
        group = str(regime.composite_regime)
    elif isinstance(regime, Mapping):
        group = str(regime.get("composite_regime", "UNKNOWN"))
    else:
        group = str(regime or "UNKNOWN")
    payload = model.by_group.get(group)
    if payload:
        return payload.get("probability"), payload.get("expected_r")
    return model.probability, model.expected_r


__all__ = ["fit_regime_prior", "fit_unconditional_prior", "prior_prediction"]
