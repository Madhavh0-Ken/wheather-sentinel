from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import BaseModel


class LightningJumpResult(BaseModel):
    status: Literal["DERIVED", "INSUFFICIENT_DATA"]
    observed_current_count: int
    observed_history: list[int]
    derived_growth_count: int | None = None
    threshold_count: float | None = None
    jump_detected: bool | None = None
    method: str


def detect_lightning_jump(
    window_counts: list[int],
    *,
    window_minutes: int,
    sigma_multiplier: float = 2.0,
    minimum_count: int = 10,
) -> LightningJumpResult:
    if not window_counts:
        raise ValueError("At least one observed lightning count is required")
    current = int(window_counts[-1])
    history = [int(value) for value in window_counts[:-1]]
    method = (
        f"Current {window_minutes}-minute count compared with the prior-window mean plus "
        f"{sigma_multiplier:g} population standard deviations and minimum count {minimum_count}."
    )
    if len(history) < 2:
        return LightningJumpResult(
            status="INSUFFICIENT_DATA",
            observed_current_count=current,
            observed_history=history,
            method=method,
        )
    threshold = max(float(minimum_count), float(np.mean(history) + sigma_multiplier * np.std(history)))
    return LightningJumpResult(
        status="DERIVED",
        observed_current_count=current,
        observed_history=history,
        derived_growth_count=current - history[-1],
        threshold_count=threshold,
        jump_detected=current >= threshold and current >= 2 * max(float(np.mean(history)), 1.0),
        method=method,
    )
