from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.yaml"


class Bounds(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @model_validator(mode="after")
    def validate_range(self) -> "Bounds":
        if not (-90 <= self.min_lat < self.max_lat <= 90):
            raise ValueError("Latitude bounds must be ordered within [-90, 90]")
        if not (-180 <= self.min_lon < self.max_lon <= 360):
            raise ValueError("Longitude bounds must be ordered within [-180, 360]")
        return self


class StudyAreaConfig(BaseModel):
    name: str
    bounds: Bounds


class DataConfig(BaseModel):
    raw_dir: Path = Path("data/raw/cmorph")
    processed_event: Path = Path("data/processed/cmorph_india_event.nc")
    provenance_manifest: Path = Path("data/processed/cmorph_india_event.provenance.json")
    max_frames: int = Field(default=12, ge=4, le=48)


class ManualDataConfig(BaseModel):
    mosdac_satellite_dir: Path = Path("data/manual/mosdac_satellite")
    imd_radar_dir: Path = Path("data/manual/imd_radar")
    imd_lightning_dir: Path = Path("data/manual/imd_lightning")
    imd_surface_dir: Path = Path("data/manual/imd_surface")
    nwp_dir: Path = Path("data/manual/nwp")


class FeatureFlags(BaseModel):
    satellite: bool = False
    radar: bool = False
    lightning: bool = False
    surface: bool = False
    nwp: bool = False
    optical_flow: bool = False
    live_mode: bool = False
    alerts: bool = True
    api: bool = True


class AnalysisGridConfig(BaseModel):
    resolution_km: float = Field(default=3.0, ge=1.0, le=25.0)
    temporal_tolerance_minutes: int = Field(default=15, ge=0, le=180)


class DetectionConfig(BaseModel):
    threshold_mm_hr: float = Field(default=10.0, ge=0)
    minimum_pixels: int = Field(default=2, ge=1)


class TrackingConfig(BaseModel):
    max_distance_km: float = Field(default=100.0, gt=0)
    max_gap_minutes: int = Field(default=90, ge=30)
    max_assignment_cost: float = Field(default=1.5, gt=0)


class ForecastConfig(BaseModel):
    lead_minutes: tuple[int, ...] = (30, 60, 120)
    base_uncertainty_km: float = Field(default=12.0, gt=0)
    uncertainty_growth_km_per_hour: float = Field(default=18.0, gt=0)

    @model_validator(mode="after")
    def validate_leads(self) -> "ForecastConfig":
        if tuple(sorted(set(self.lead_minutes))) != self.lead_minutes:
            raise ValueError("Forecast lead minutes must be unique and increasing")
        return self


class TargetConfig(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STORM_NOWCAST_", env_nested_delimiter="__", extra="ignore"
    )

    study_area: StudyAreaConfig
    data: DataConfig = DataConfig()
    manual_data: ManualDataConfig = ManualDataConfig()
    features: FeatureFlags = FeatureFlags()
    analysis_grid: AnalysisGridConfig = AnalysisGridConfig()
    detection: DetectionConfig = DetectionConfig()
    tracking: TrackingConfig = TrackingConfig()
    forecast: ForecastConfig = ForecastConfig()
    target: TargetConfig = TargetConfig(latitude=31.1048, longitude=77.1734)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _environment_overrides() -> dict[str, Any]:
    prefix = "STORM_NOWCAST_"
    result: dict[str, Any] = {}
    for name, raw_value in os.environ.items():
        if not name.startswith(prefix):
            continue
        keys = [part.lower() for part in name[len(prefix) :].split("__") if part]
        if not keys:
            continue
        cursor = result
        for key in keys[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[keys[-1]] = yaml.safe_load(raw_value)
    return result


def load_settings(path: Path | None = None) -> Settings:
    default_data = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    if path is not None:
        override = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        default_data = _merge(default_data, override)
    default_data = _merge(default_data, _environment_overrides())
    return Settings(**default_data)
