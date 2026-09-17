from __future__ import annotations

import math
from collections.abc import Callable


def percentile_scores(values: list[float | int | None], transform: Callable[[float], float] | None = None) -> list[float | None]:
    transform = transform or (lambda value: value)
    present = [(index, transform(float(value))) for index, value in enumerate(values) if value is not None]
    result: list[float | None] = [None] * len(values)
    if not present:
        return result
    unique_values = {value for _, value in present}
    if len(unique_values) == 1:
        for index, _ in present:
            result[index] = 0.5
        return result
    sorted_values = sorted(value for _, value in present)
    denominator = len(sorted_values) - 1
    for index, value in present:
        lower = sum(candidate < value for candidate in sorted_values)
        equal = sum(candidate == value for candidate in sorted_values)
        result[index] = (lower + (equal - 1) / 2) / denominator
    return result


def log1p(value: float) -> float:
    return math.log1p(max(0.0, value))


def mean_available(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None
