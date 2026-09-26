from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import xarray as xr
from scipy.ndimage import shift as shift_array
from skimage.registration import phase_cross_correlation

from storm_nowcast.models.schemas import StormCell
from storm_nowcast.nowcast.base import ForecastField, MotionEstimate, RasterForecastProduct
from storm_nowcast.nowcast.motion import forecast_track


DEFAULT_RASTER_LEADS = (10, 20, 30, 60, 90, 120)


def estimate_translation(
    previous: xr.DataArray,
    current: xr.DataArray,
    *,
    delta_minutes: int,
    minimum_finite_coverage: float = 0.5,
) -> MotionEstimate:
    if previous.shape != current.shape or previous.dims != current.dims:
        raise ValueError("Raster motion inputs must share shape and dimensions")
    if delta_minutes <= 0:
        raise ValueError("delta_minutes must be positive")
    first = np.asarray(previous.values, dtype=float)
    second = np.asarray(current.values, dtype=float)
    finite = np.isfinite(first) & np.isfinite(second)
    coverage = float(np.mean(finite))
    if coverage < minimum_finite_coverage:
        return MotionEstimate(
            available=False,
            finite_coverage=coverage,
            explanation=(
                f"Finite coverage {coverage:.1%} is below the {minimum_finite_coverage:.0%} motion threshold."
            ),
        )
    first_filled = np.where(finite, first, 0.0)
    second_filled = np.where(finite, second, 0.0)
    if np.std(first_filled) < 1e-9 and np.std(second_filled) < 1e-9:
        return MotionEstimate(
            available=True,
            shift_y_pixels=0.0,
            shift_x_pixels=0.0,
            finite_coverage=coverage,
            quality=1.0,
            explanation="Fields are spatially uniform; translation is set to zero.",
        )
    registration_shift, error, _ = phase_cross_correlation(
        first_filled,
        second_filled,
        upsample_factor=10,
        normalization=None,
    )
    return MotionEstimate(
        available=True,
        shift_y_pixels=float(-registration_shift[0]),
        shift_x_pixels=float(-registration_shift[1]),
        finite_coverage=coverage,
        quality=float(max(0.0, 1.0 - error)) if np.isfinite(error) else None,
        explanation=f"Translation estimated from two fields {delta_minutes} minutes apart.",
    )


def _elapsed_minutes(previous: xr.DataArray, current: xr.DataArray) -> int:
    first = previous.attrs.get("timestamp")
    second = current.attrs.get("timestamp")
    if not first or not second:
        return 10
    first_time = datetime.fromisoformat(str(first).replace("Z", "+00:00"))
    second_time = datetime.fromisoformat(str(second).replace("Z", "+00:00"))
    elapsed = int((second_time - first_time).total_seconds() / 60)
    if elapsed <= 0:
        raise ValueError("Raster observations must advance in time")
    return elapsed


def forecast_rainfall_fields(
    previous: xr.DataArray,
    current: xr.DataArray,
    *,
    issued_at: datetime,
    leads: tuple[int, ...] = DEFAULT_RASTER_LEADS,
    deterministic_cell: StormCell | None = None,
    base_uncertainty_km: float = 9.0,
    uncertainty_growth_km_per_hour: float = 18.0,
) -> RasterForecastProduct:
    delta_minutes = _elapsed_minutes(previous, current)
    motion = estimate_translation(previous, current, delta_minutes=delta_minutes)
    method = "phase-correlation translation advection"
    if not motion.available:
        points = forecast_track(
            deterministic_cell,
            leads,
            base_uncertainty_km=base_uncertainty_km,
            uncertainty_growth_km_per_hour=uncertainty_growth_km_per_hour,
        ) if deterministic_cell is not None else []
        return RasterForecastProduct(
            issued_at=issued_at,
            method="deterministic track fallback" if points else "unavailable",
            motion=motion,
            point_forecasts=points,
            fallback_used=True,
            fallback_reason=motion.explanation,
        )
    first_sum = float(np.nansum(previous.values))
    second_sum = float(np.nansum(current.values))
    interval_ratio = second_sum / first_sum if first_sum > 0 else 1.0
    fields: list[ForecastField] = []
    current_values = np.nan_to_num(np.asarray(current.values, dtype=float), nan=0.0)
    for lead in leads:
        intervals = lead / delta_minutes
        projected_growth = float(np.clip(interval_ratio**intervals, 0.5, 1.5))
        shifted = shift_array(
            current_values,
            shift=(motion.shift_y_pixels * intervals, motion.shift_x_pixels * intervals),
            order=1,
            mode="constant",
            cval=0.0,
            prefilter=False,
        )
        forecast = current.copy(data=np.maximum(shifted * projected_growth, 0.0))
        forecast.attrs.update(
            {
                "variable_status": "FORECAST",
                "forecast_method": method,
                "growth_factor": projected_growth,
                "lead_minutes": lead,
            }
        )
        confidence = "HIGH" if lead <= 20 and motion.quality is not None and motion.quality >= 0.7 else "MODERATE" if lead <= 60 else "LOW"
        fields.append(
            ForecastField(
                lead_minutes=lead,
                valid_at=issued_at + timedelta(minutes=lead),
                rain_rate=forecast,
                uncertainty_km=base_uncertainty_km + uncertainty_growth_km_per_hour * lead / 60,
                confidence=confidence,
            )
        )
    return RasterForecastProduct(
        issued_at=issued_at,
        method=method,
        motion=motion,
        fields=fields,
    )
