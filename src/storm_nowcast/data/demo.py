from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import xarray as xr

from storm_nowcast.config import Settings
from storm_nowcast.data.download import download_file
from storm_nowcast.data.provenance import write_manifest
from storm_nowcast.data.rainfall import load_cmorph_file
from storm_nowcast.data.sources import CmorphSource
from storm_nowcast.models.schemas import ProvenanceRecord
from storm_nowcast.replay.player import save_event, score_event


CANDIDATE_STARTS = (
    datetime(2023, 7, 9, 0, tzinfo=timezone.utc),
    datetime(2023, 7, 8, 18, tzinfo=timezone.utc),
    datetime(2023, 7, 10, 0, tzinfo=timezone.utc),
)


@dataclass(frozen=True)
class PreparedEvent:
    path: Path
    start: datetime
    end: datetime
    frame_count: int
    score: float
    source_files: tuple[Path, ...]


def _load_existing(path: Path) -> PreparedEvent:
    dataset = xr.load_dataset(path, engine="h5netcdf")
    start = datetime.fromisoformat(str(dataset.attrs["observation_start"]).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(dataset.attrs["observation_end"]).replace("Z", "+00:00"))
    return PreparedEvent(path, start, end, dataset.sizes["time"], float(dataset.attrs["event_score"]), ())


def prepare_event(settings: Settings, allow_download: bool = True) -> PreparedEvent:
    output = settings.data.processed_event
    if output.exists():
        return _load_existing(output)
    if not allow_download:
        raise FileNotFoundError(f"Prepared real event not found at {output}")

    source = CmorphSource()
    hours_needed = (settings.data.max_frames + 1) // 2
    best: tuple[float, xr.Dataset, list[Path], list[ProvenanceRecord]] | None = None
    for start in CANDIDATE_STARTS:
        datasets: list[xr.Dataset] = []
        files: list[Path] = []
        records: list[ProvenanceRecord] = []
        try:
            for offset in range(hours_needed):
                hour = start + timedelta(hours=offset)
                url = source.build_url(hour)
                destination = settings.data.raw_dir / Path(url).name
                result = download_file(url, destination)
                dataset = load_cmorph_file(destination, hour, settings.study_area.bounds)
                datasets.append(dataset)
                files.append(destination)
                records.append(
                    ProvenanceRecord(
                        provider=source.provider,
                        product=source.product,
                        source_url=url,
                        acquired_at=datetime.now(timezone.utc),
                        observation_start=hour,
                        observation_end=hour + timedelta(minutes=30),
                        sha256=result.sha256,
                        processing_steps=[
                            "downloaded from official NOAA CPC HTTPS archive",
                            "decompressed official gzip/bzip2 source archive",
                            "parsed little-endian float32",
                            "subset to configured EPSG:4326 study area",
                        ],
                        local_file=str(destination),
                    )
                )
        except Exception as exc:
            print(f"Candidate {start.isoformat()} unavailable: {exc}")
            continue
        combined = xr.concat(datasets, dim="time").sortby("time").isel(time=slice(0, settings.data.max_frames))
        _, unique_index = np.unique(combined.time.values, return_index=True)
        combined = combined.isel(time=np.sort(unique_index))
        score = score_event(combined, settings.detection.threshold_mm_hr)
        if best is None or score > best[0]:
            best = (score, combined, files, records)
        wet_frames = int(
            np.sum(
                np.nanmax(combined.rain_rate.values, axis=(1, 2))
                >= settings.detection.threshold_mm_hr
            )
        )
        if wet_frames >= 3:
            break

    if best is None:
        raise RuntimeError("No official CMORPH candidate event could be downloaded")
    score, event, files, records = best
    start_time = datetime.fromtimestamp(event.time.values[0].astype("datetime64[s]").astype(int), tz=timezone.utc)
    end_time = datetime.fromtimestamp(event.time.values[-1].astype("datetime64[s]").astype(int), tz=timezone.utc)
    event.attrs.update(
        {
            "event_id": f"cmorph-india-{start_time:%Y%m%dT%H%MZ}",
            "study_area": settings.study_area.name,
            "observation_start": start_time.isoformat().replace("+00:00", "Z"),
            "observation_end": end_time.isoformat().replace("+00:00", "Z"),
            "event_score": score,
            "frame_count": event.sizes["time"],
            "is_synthetic": False,
        }
    )
    save_event(event, output)
    write_manifest(settings.data.provenance_manifest, records)
    return PreparedEvent(output, start_time, end_time, event.sizes["time"], score, tuple(files))
