from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from storm_nowcast.data.provenance import sha256_file


OFFICIAL_CMORPH_HOSTS = {"ftp.cpc.ncep.noaa.gov", "www.ftp.cpc.ncep.noaa.gov"}


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    downloaded: bool
    byte_count: int


def validate_official_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_CMORPH_HOSTS:
        raise ValueError("Download URL is not an authoritative NOAA CPC HTTPS host")


def download_file(url: str, destination: Path, timeout: tuple[int, int] = (15, 120)) -> DownloadResult:
    validate_official_url(url)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size:
        return DownloadResult(destination, sha256_file(destination), False, destination.stat().st_size)

    partial = destination.with_suffix(destination.suffix + ".part")
    existing = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as response:
        response.raise_for_status()
        append = existing > 0 and response.status_code == 206
        mode = "ab" if append else "wb"
        with partial.open(mode) as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    partial.replace(destination)
    return DownloadResult(destination, sha256_file(destination), True, destination.stat().st_size)

