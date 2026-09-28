# Data sources and ingestion status

## Connected and verified

| Source | Access | Native statement | Current evidence |
|---|---|---|---|
| NOAA CPC CMORPH V0.x RAW 8km-30min | Public official HTTPS; no login | Approximately 8 km grid, 30-minute frames; effective resolution is coarser | Six official hourly archives, SHA-256 records, 12 real frames |
| ISRO/SAC MOSDAC INSAT-3DR `3RIMG_L1C_ASIA_MER` | Authorized local files from authenticated MOSDAC access | TIR1 and WV brightness temperature in kelvin; native metadata 4 km | Product-specific reader verified with genuine files; 12 causal observations attached to the built-in replay |

Base archive:
<https://ftp.cpc.ncep.noaa.gov/precip/CMORPH_V0.x/RAW/8km-30min/>

The cached demonstration covers 2023-07-09 00:00–05:30 UTC and 29–33°N,
75–79°E. Each hourly archive contains two half-hour fields. Raw archives are stored
under `data/raw/cmorph/`; the compact extracted event and provenance manifest are
under `data/processed/`. These generated files are intentionally git-ignored.

The configurable workflow uses the same official product for any supported,
non-dateline-crossing rectangle inside the published latitude grid. A request is
capped at 20 degrees by 20 degrees and an inclusive 24-hour UTC window. Cached raw
files are shared across events and are reused only after compressed layout, checksum,
official URL, and requested-crop parsing validation. Custom processed events live
under `data/events/custom/<event_id>/`; deleting one never deletes the shared cache.
See [CUSTOM_REGION_ANALYSIS.md](CUSTOM_REGION_ANALYSIS.md).

## Implemented import contracts awaiting official data

| Sensor/product family | Loader state | Required before it can be called verified |
|---|---|---|
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

### INSAT-3DR priority product

The selected product is MOSDAC `3RIMG_L1C_ASIA_MER`, DOI
`10.19038/SAC/10/3RIMG_L1C_ASIA_MER`: half-hourly INSAT-3DR Imager Level-1C data in
Mercator projection for the Asian sector. Official references:

- Product and constraints: <https://mosdac.gov.in/doi/164/>
- HDF structure, channel names, calibration LUTs, acquisition metadata, and projection:
  <https://www.mosdac.gov.in/docs/INSAT3D_Products.pdf>
- Registration/access policy: <https://www.mosdac.gov.in/data-access-policy>

The synchronized event is 2023-07-09 00:00–05:30 UTC. Its twelve causal INSAT scans
run from 2023-07-08 23:45 through 2023-07-09 05:15 UTC. The product-specific reader
has been verified against genuine MOSDAC files and produces two calibrated fields:
`infrared_brightness_temperature` from `IMG_TIR1`/`IMG_TIR1_TEMP` and
`water_vapour_brightness_temperature` from `IMG_WV`/`IMG_WV_TEMP`, both in kelvin.
Authorized source files belong in `data/manual/mosdac_satellite/`; normalized products
and their provenance sidecars belong in `data/processed/insat/`. Both locations are
generated/local and git-ignored. No password, token, or session cookie is stored.

Replay alignment uses validated observation metadata, never filename-specific time
rules. Selection is backward-only (`observation_time <= replay_time`) with a default
maximum age of 30 minutes. The built-in half-hour frames select the preceding
quarter-hour INSAT scans at an exact age of 15 minutes. Out-of-window files are not
selected. Per-frame availability and per-pixel missing masks are explicit; stale or
absent evidence is reported unavailable rather than carried forward. INSAT remains
optional, so deleting or omitting the local INSAT directory does not alter the
original CMORPH artifact or disable CMORPH-only replay.

The dashboard can display the actual TIR1 source grid as **INSAT-3DR TIR1 Brightness
Temperature (K) — native metadata 4 km**. Finite samples are plotted directly with no
artificial spatial upscaling. WV remains visible in evidence metadata without a
second map layer. Brightness temperature alone is not used to infer thunderstorms,
hail, downbursts, or cloudbursts.

## Authentication

This repository contains no credentials and no login bypass. MOSDAC's official policy
provides dataset access according to account profile; `3RIMG_L1C_ASIA_MER` is listed
for registered researchers. The adapters ingest already-authorized local files and do
not automate SSO, ordering, CAPTCHA, or protected downloads. Authentication absence
never blocks the verified CMORPH replay.

## Resolution and synthetic-data policy

Every gridded variable carries native resolution, analysis-grid resolution,
resampling method, units, source IDs, and an observed/derived/forecast status. A
configurable 3 km analysis grid is an alignment surface only: it creates no 3 km
observation claim. Point observations remain point tables until an explicit
aggregation is requested. Synthetic arrays and events appear only in automated tests
and are marked `is_synthetic=true` where the model supports that field.
