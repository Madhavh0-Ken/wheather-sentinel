from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class SourceStatus(BaseModel):
    source: str
    available: bool
    authentication_required: bool = False
    manual_file_required: bool = False
    implemented: bool = False
    verified_with_real_data: bool = False
    data_path: str | None = None
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
            implemented=True,
            verified_with_real_data=True,
            message="Public official NOAA CPC download; no login required.",
        )


class MosdacSatelliteSource:
    def status(
        self,
        *,
        available: bool = False,
        data_path: Path | None = None,
    ) -> SourceStatus:
        return SourceStatus(
            source="ISRO MOSDAC INSAT",
            available=available,
            authentication_required=True,
            manual_file_required=True,
            implemented=True,
            verified_with_real_data=True,
            data_path=str(data_path) if data_path is not None else None,
            message=(
                "Verified real ISRO/SAC MOSDAC 3RIMG_L1C_ASIA_MER observations are available."
                if available
                else "Authenticated MOSDAC access and an official 3RIMG_L1C_ASIA_MER file are required."
            ),
        )


class ImdRadarSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department Doppler Weather Radar",
            available=False,
            manual_file_required=True,
            implemented=True,
            message=(
                "Product-specific loading is not yet verified; authenticated IMD access "
                "or an official user-supplied file is required."
            ),
        )


class ImdLightningSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department lightning observations",
            available=False,
            manual_file_required=True,
            implemented=True,
            message=(
                "Product-specific loading is not yet verified; official IMD access or "
                "an official user-supplied file is required."
            ),
        )


class ImdStationSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="India Meteorological Department surface observations",
            available=False,
            manual_file_required=True,
            implemented=True,
            message="Loading is not yet verified; provide an official IMD station file.",
        )


class NwpSource:
    def status(self) -> SourceStatus:
        return SourceStatus(
            source="Numerical weather prediction",
            available=False,
            manual_file_required=True,
            implemented=True,
            message="No official NWP dataset is configured for this event.",
        )
