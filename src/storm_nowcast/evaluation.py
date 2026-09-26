from __future__ import annotations

from collections import defaultdict

import numpy as np
from shapely.affinity import translate
from shapely.geometry import shape

from storm_nowcast.models.schemas import EvaluationMetrics, StormCell
from storm_nowcast.tracking.tracker import haversine_km


INSUFFICIENT = "Insufficient observations for validated metric."


def evaluate_forecasts(
    issued_tracks: list[StormCell],
    later_tracks: list[StormCell],
) -> list[EvaluationMetrics]:
    actual_by_id = {track.id: track for track in later_tracks}
    expected_by_lead: dict[int, int] = defaultdict(int)
    errors_by_lead: dict[int, list[float]] = defaultdict(list)
    iou_by_lead: dict[int, list[float]] = defaultdict(list)

    for issued in issued_tracks:
        actual_track = actual_by_id.get(issued.id)
        for forecast in issued.forecasts:
            expected_by_lead[forecast.lead_minutes] += 1
            if actual_track is None:
                continue
            actual = next(
                (item for item in actual_track.history if item.timestamp == forecast.valid_at),
                None,
            )
            if actual is None:
                continue
            errors_by_lead[forecast.lead_minutes].append(
                haversine_km(forecast.latitude, forecast.longitude, actual.centroid_lat, actual.centroid_lon)
            )
            current_shape = shape(issued.current.polygon_geojson)
            predicted_shape = translate(
                current_shape,
                xoff=forecast.longitude - issued.current.centroid_lon,
                yoff=forecast.latitude - issued.current.centroid_lat,
            )
            actual_shape = shape(actual.polygon_geojson)
            union = predicted_shape.union(actual_shape).area
            iou_by_lead[forecast.lead_minutes].append(
                predicted_shape.intersection(actual_shape).area / union if union else 0.0
            )

    if not expected_by_lead:
        return [EvaluationMetrics(message=INSUFFICIENT)]
    results: list[EvaluationMetrics] = []
    for lead in sorted(expected_by_lead):
        errors = errors_by_lead[lead]
        overlaps = iou_by_lead[lead]
        if not errors:
            results.append(EvaluationMetrics(lead_minutes=lead, message=INSUFFICIENT))
            continue
        results.append(
            EvaluationMetrics(
                lead_minutes=lead,
                position_error_km=float(np.mean(errors)),
                iou=float(np.mean(overlaps)),
                track_continuity=len(errors) / expected_by_lead[lead],
                sample_count=len(errors),
            )
        )
    return results

