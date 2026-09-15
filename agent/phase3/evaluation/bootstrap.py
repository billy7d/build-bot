"""Confidence interval theo block bootstrap deterministic."""

from __future__ import annotations

import random
from typing import Callable, Sequence


def block_bootstrap_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    block_size: int = 10,
    iterations: int = 1000,
    seed: int = 42,
) -> dict[str, float | int | None]:
    """Resample các block thời gian, không shuffle từng observation độc lập."""

    if not values:
        return {"count": 0, "estimate": None, "lower_95": None, "upper_95": None, "block_size": block_size, "iterations": 0}
    block_size = max(1, int(block_size))
    iterations = max(1, int(iterations))
    blocks = [tuple(float(item) for item in values[index:index + block_size]) for index in range(0, len(values), block_size)]
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(iterations):
        draw: list[float] = []
        while len(draw) < len(values):
            draw.extend(rng.choice(blocks))
        samples.append(float(statistic(draw[:len(values)])))
    samples.sort()
    lower = samples[int(0.025 * (len(samples) - 1))]
    upper = samples[int(0.975 * (len(samples) - 1))]
    return {
        "count": len(values),
        "estimate": float(statistic(values)),
        "lower_95": lower,
        "upper_95": upper,
        "block_size": block_size,
        "iterations": iterations,
        "seed": seed,
    }


__all__ = ["block_bootstrap_ci"]
