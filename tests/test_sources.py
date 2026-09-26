from datetime import datetime, timezone

import pytest

from storm_nowcast.data.download import validate_official_url
from storm_nowcast.data.sources import (
    CmorphSource,
    ImdLightningSource,
    ImdRadarSource,
    MosdacSatelliteSource,
)


def test_cmorph_url_uses_official_noaa_archive_and_hour_name():
    url = CmorphSource().build_url(datetime(2023, 7, 9, 6, tzinfo=timezone.utc))

    assert url == (
        "https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_V0.x/RAW/8km-30min/"
        "2023/202307/CMORPH_V0.x_RAW_8km-30min_2023070906.gz"
    )


def test_download_guard_rejects_non_noaa_hosts():
    with pytest.raises(ValueError, match="authoritative NOAA CPC"):
        validate_official_url("https://weather.example.org/cmorph/file.bz2")


def test_optional_adapters_disclose_access_requirements():
    mosdac = MosdacSatelliteSource().status()
    radar = ImdRadarSource().status()
    lightning = ImdLightningSource().status()

    assert mosdac.authentication_required is True
    assert mosdac.implemented is False
    assert "not yet verified" in mosdac.message
    assert radar.manual_file_required is True
    assert lightning.manual_file_required is True
    assert not any(status.available for status in (mosdac, radar, lightning))
