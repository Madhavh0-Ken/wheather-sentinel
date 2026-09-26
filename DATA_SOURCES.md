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
| ISRO/SAC MOSDAC INSAT-3DR `3RIMG_L1C_ASIA_MER` | Product-specific documented-schema HDF reader for TIR1 and optional WV brightness temperature; generic explicit CF import also remains | Authenticated MOSDAC file and real-file verification |
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

The synchronized-event request is 2023-07-09 00:00-05:30 UTC. Expected portal files
match `3RIMG_09JUL2023_HHmm_L1C_ASIA_MER*.h5` and belong in
`data/manual/mosdac_satellite/`. See that directory's README for the exact portal
steps and ingestion command. No password, token, or session cookie is stored.

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
