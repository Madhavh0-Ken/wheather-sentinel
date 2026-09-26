from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel


class SourceStatus(BaseModel):
    source: str
    available: bool
    authentication_required: bool = False
    manual_file_required: bool = False
    message: str


class CmorphSource:
    provider = "NOAA Climate Prediction Center"
    product = "CMORPH V0.x RAW 8km-30min"
    base_url = "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_V0.x/RAW/8km-30min"

    def build_url(self, timestamp: datetime) -> str:
        if timestamp.tzinfo is None:
            raise ValueError("CMORPH timestamps must be timezone-aware")
        utc = timestamp.astimezone(timezone.utc)
        extension = "gz" if utc.year <= 2025 else "bz2"
        return (
            f"{self.base_url}/{utc:%Y}/{utc:%Y%m}/"
            f"CMORPH_V0.x_RAW_8km-30min_{utc:%Y%m%d%H}.{extension}"
        )

    def status(self) -> SourceStatus:
        return SourceStatus(
            source=self.product,
            available=True,
            message="Public official NOAA CPC download; no login required.",
        )


class MosdacSatelliteSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="ISRO MOSDAC INSAT",
            available=False,
            authentication_required=True,
            message=(
                "Official adapter ready; source data not bundled because authenticated "
                "provider access is required."
            ),
        )


class ImdRadarSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department Doppler Weather Radar",
            available=False,
            manual_file_required=True,
            message=(
                "Official adapter ready; source data not bundled because authenticated "
                "provider access or an official user-supplied file is required."
            ),
        )


class ImdLightningSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department lightning observations",
            available=False,
            manual_file_required=True,
            message=(
                "Official adapter ready; source data not bundled because authenticated "
                "provider access or an official user-supplied file is required."
            ),
        )


class ImdStationSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department surface observations",
            available=False,
            manual_file_required=True,
            message="Official adapter ready; provide an official IMD station file.",
        )
