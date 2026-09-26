from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from storm_nowcast.models.schemas import DetectedCell, ProvenanceRecord


def test_provenance_converts_aware_timestamps_to_utc():
    record = ProvenanceRecord(
        provider="NOAA Climate Prediction Center",
        product="CMORPH",
        source_url="https://ftp.cpc.ncep.noaa.gov/example",
        acquired_at=datetime(2023, 7, 9, 12, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        observation_start=datetime(2023, 7, 9, 0, tzinfo=timezone.utc),
        observation_end=datetime(2023, 7, 9, 0, 30, tzinfo=timezone.utc),
        sha256="a" * 64,
    )

    assert record.acquired_at.utcoffset() == timedelta(0)
    assert record.acquired_at.hour == 6
    assert record.acquired_at.minute == 30


def test_provenance_rejects_naive_timestamps():
    with pytest.raises(ValidationError):
        ProvenanceRecord(
            provider="NOAA Climate Prediction Center",
            product="CMORPH",
            source_url="https://ftp.cpc.ncep.noaa.gov/example",
            acquired_at=datetime(2023, 7, 9, 12),
            observation_start=datetime(2023, 7, 9, 0, tzinfo=timezone.utc),
            observation_end=datetime(2023, 7, 9, 0, 30, tzinfo=timezone.utc),
            sha256="a" * 64,
        )


def test_real_records_default_to_not_synthetic_but_test_fixtures_can_be_marked():
    common = dict(
        local_id=1,
        timestamp=datetime(2023, 7, 9, tzinfo=timezone.utc),
        centroid_lat=31.0,
        centroid_lon=77.0,
        area_km2=64.0,
        max_intensity=42.0,
        mean_intensity=27.0,
        pixel_count=1,
        bbox=(30.96, 76.96, 31.04, 77.04),
        polygon_geojson={"type": "Polygon", "coordinates": []},
    )

    assert DetectedCell(**common).is_synthetic is False
    assert DetectedCell(**common, is_synthetic=True).is_synthetic is True
