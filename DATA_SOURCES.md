# Data sources and ingestion status

## Connected and verified

| Source | Access | Native statement | Current evidence |
|---|---|---|---|
| NOAA CPC CMORPH V0.x RAW 8km-30min | Public official HTTPS; no login | Approximately 8 km grid, 30-minute frames; effective resolution is coarser | Six official hourly archives, SHA-256 records, 12 real frames |

Base archive:
<https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_V0.x/RAW/8km-30min/>

The cached demonstration covers 2023-07-09 00:00–05:30 UTC and 29–33°N,
75–79°E. Each hourly archive contains two half-hour fields. Raw archives are stored
under `data/raw/cmorph/`; the compact extracted event and provenance manifest are
under `data/processed/`. These generated files are intentionally git-ignored.

## Implemented import contracts awaiting official data

| Sensor/product family | Loader state | Required before it can be called verified |
|---|---|---|
| ISRO MOSDAC INSAT | Generic explicit CF-compatible NetCDF/HDF5 import; cooling/expansion derivation for suitable consecutive Kelvin fields | Authenticated MOSDAC access, official sample, explicit variable mapping, product-specific verification |
| IMD Doppler Weather Radar | Generic explicit CF-compatible NetCDF/HDF5 import | Authorized official file, variable mapping, native resolution, format verification |
| IMD lightning | Explicit point CSV import and window-count analytics | Authorized official file and explicit time/latitude/longitude mapping |
| IMD AWS/ARG surface | Explicit point CSV import | Authorized official file, explicit columns and units |
| Official NWP | Generic explicit CF-compatible NetCDF/HDF5 import | Provider, product, official URL, file, variable mapping, and native resolution |

The importers never infer an undocumented channel or column. They require the user to
confirm official origin and write a sidecar provenance record. Example:

```powershell
.\.venv\Scripts\python.exe scripts\ingest_official.py `
  --source imd-radar `
  --input C:\official-data\radar.nc `
  --output data\manual\imd_radar\radar-normalized.nc `
  --variable reflectivity=DBZH `
  --native-resolution-km 1.0 `
  --confirm-official-origin
```

Use `--column canonical=source_name` for lightning or surface CSV files. See the
README in each `data/manual/*` directory for the required canonical variables. The
command validates structure and provenance; it does not prove the provider supplied
the file.

## Authentication

This repository contains no credentials and no login bypass. The current generic
MOSDAC/IMD adapters ingest already-authorized local files; they do not automate SSO,
ordering, or protected downloads. Obtain data through the provider's official access
process, keep credentials outside the repository, and place only approved files in
the relevant manual-data directory. Authentication absence never blocks the verified
CMORPH replay.

## Resolution and synthetic-data policy

Every gridded variable carries native resolution, analysis-grid resolution,
resampling method, units, source IDs, and an observed/derived/forecast status. A
configurable 3 km analysis grid is an alignment surface only: it creates no 3 km
observation claim. Point observations remain point tables until an explicit
aggregation is requested. Synthetic arrays and events appear only in automated tests
and are marked `is_synthetic=true` where the model supports that field.

