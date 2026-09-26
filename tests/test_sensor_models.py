from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from storm_nowcast.models.sensors import (
    RawAsset,
    SourceDescriptor,
    SpatialResolution,
    TemporalSupport,
    VariableLineage,
)


def test_variable_lineage_preserves_native_and_analysis_resolution_without_false_upgrade():
    lineage = VariableLineage(
        variable="rain_rate",
        source_record_ids=["sha256:abc"],
        status="OBSERVED",
        native_units="mm h-1",
        processed_units="mm h-1",
        native_spatial_resolution=SpatialResolution(
            grid_spacing_km=8.0,
            effective_resolution_note="Effective resolution is coarser than grid spacing.",
        ),
        analysis_grid_resolution_km=3.0,
        resampling_method="nearest",
        native_temporal_resolution_minutes=30,
    )

    assert lineage.native_spatial_resolution.grid_spacing_km == 8.0
    assert lineage.analysis_grid_resolution_km == 3.0
    assert lineage.is_resampled_to_finer_grid is True


def test_raw_asset_requires_real_sha256_and_explicit_synthetic_flag(tmp_path: Path):
    source = SourceDescriptor(
        provider="ISRO MOSDAC",
        product="User-selected official INSAT product",
        sensor="SATELLITE",
        official_url="https://mosdac.gov.in/",
        access_method="authenticated manual import",
        authentication_required=True,
    )

    with pytest.raises(ValidationError):
        RawAsset(path=tmp_path / "official.h5", sha256="not-a-hash", size_bytes=10, source=source)

    asset = RawAsset(
        path=tmp_path / "fixture.h5",
        sha256="a" * 64,
        size_bytes=10,
        source=source,
        is_synthetic=True,
    )
    assert asset.is_synthetic is True


def test_temporal_support_rejects_reversed_observation_window():
    with pytest.raises(ValidationError, match="observation_start"):
        TemporalSupport(
            observation_start=datetime(2023, 7, 9, 1, tzinfo=timezone.utc),
            observation_end=datetime(2023, 7, 9, 0, tzinfo=timezone.utc),
            native_resolution_minutes=30,
        )
