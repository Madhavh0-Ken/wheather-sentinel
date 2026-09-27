# StormNowcast

StormNowcast is a local, map-first prototype for replaying authoritative rainfall
observations over India, detecting **Intense Precipitation Cells**, tracking them,
and issuing transparent short-range movement extrapolations. Its only verified
production data path is the public NOAA CPC CMORPH archive. CMORPH has an
approximately 8 km grid and coarser effective resolution; the application does not
present it as radar or as 1–3 km observations.

The risk output is named **Prototype Extreme Rain Risk**. It is an uncalibrated
rainfall-derived heuristic, not meteorological cloudburst detection and not an
operational warning.

## Quick start on Windows

From the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\prepare_demo.py
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501
```

Open <http://localhost:8501>. The first preparation command downloads only six
official hourly CMORPH archives and creates a 12-frame regional event. After those
files are cached, verify or start without network access using:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_demo.py --no-download
```

To analyze another supported region, choose **Analyze New Region** in the dashboard
or use `scripts\prepare_custom_event.py`. Requests are limited to 20 degrees by 20
degrees and an inclusive 24-hour UTC span (49 half-hour observations). Prepared
custom events are checksum-validated, reopen offline, and do not replace the
built-in default. See [CUSTOM_REGION_ANALYSIS.md](CUSTOM_REGION_ANALYSIS.md).

Run the API in a second terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn storm_nowcast.api.app:app --host 127.0.0.1 --port 8000
```

API documentation is at <http://127.0.0.1:8000/docs>. Run all tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Build causal training-data artifacts (this does not train a model):

```powershell
.\.venv\Scripts\python.exe scripts\build_training_dataset.py
```

## What works

- Official NOAA CPC CMORPH download, checksum provenance, binary parsing, regional
  extraction, and 30-minute historical replay.
- Grid-native interactive rainfall map; no visual upscaling into false detail.
- Intense Precipitation Cell detection, persistent IDs, tracking, speed, bearing,
  intensity trend, deterministic +30/+60/+120 minute movement, increasing heuristic
  uncertainty, target closest approach, and qualified ETA.
- Prototype Extreme Rain Risk and real forecast-versus-later-observation evaluation
  where later frames exist.
- Typed multi-sensor contracts, generic explicit official-file import, a
  resolution-aware weather cube, evidence-bearing digital twins, sensor-gated
  initiation/lightning analytics, raster translation nowcasting, live polling,
  alert rules, and an event-aware FastAPI layer.
- Product-specific documented-schema ingestion for MOSDAC INSAT-3DR
  `3RIMG_L1C_ASIA_MER`, including file-supplied TIR1/WV calibration LUTs,
  Mercator geolocation, acquisition time, native resolution, and checksum provenance.
- Horizon-specific T-120/T-90/T-60/T-30/T datasets with event-separated split and
  train-only normalization contracts; the current one-event corpus remains unsuitable
  for learned-model training.
- Historical/live-mode UI. Live mode truthfully falls back because no live provider
  is configured in this build.
- Center/size or bounding-box CMORPH preparation, map preview, validated shared raw
  cache, atomic custom-event repository, offline reopening, safe deletion, and
  event-scoped Streamlit/FastAPI analysis.

## What is not connected

The product-specific MOSDAC INSAT reader is verified against the official published
schema using synthetic test fixtures, but no authorized real INSAT file is present;
it is therefore not reported as a connected real source. IMD radar, lightning, and
surface files also require authorized official files and remain generic/unverified.
NWP uses the same explicit manual-import contract and is also unverified. Hail,
downburst, and learned 2–6 hour forecasting remain unavailable because authoritative
labels and a multi-event training/validation corpus are absent.

See [DATA_SOURCES.md](DATA_SOURCES.md), [PROJECT_STATUS.md](PROJECT_STATUS.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [MODEL_CARD.md](MODEL_CARD.md), and
[VALIDATION.md](VALIDATION.md) for the exact evidence and limitations. See also
[CUSTOM_REGION_ANALYSIS.md](CUSTOM_REGION_ANALYSIS.md),
[TRAINING_DATA.md](TRAINING_DATA.md), and [SENSOR_INTEGRATION.md](SENSOR_INTEGRATION.md).
The known-good CMORPH checkpoint is git commit `3d0a01a`.
