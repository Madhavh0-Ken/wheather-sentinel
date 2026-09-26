# StormNowcast full-system roadmap

Updated: 2026-09-26. Safety baseline: git commit `3d0a01a`.

## Product rule

The working NOAA CMORPH replay is the fallback system. New sensors are optional,
feature-gated inputs. Missing credentials, unavailable files, unsupported formats,
or failed updates must never stop CMORPH-only detection, tracking, deterministic
forecasting, Prototype Extreme Rain Risk, ETA, replay, or retrospective evaluation.

## Status at the start of this extension

| Capability | Status | Evidence |
|---|---|---|
| NOAA CPC CMORPH ingest | Complete | Public official archive; six cached files with SHA-256 provenance |
| Real regional replay | Complete | 12 frames, 2023-07-09 00:00â€“05:30 UTC, 29â€“33Â°N / 75â€“79Â°E |
| Intense Precipitation Cells | Complete | Rainfall-derived objects; not confirmed thunderstorms |
| Tracking and deterministic +30/+60/+120 min motion | Complete | Automated tests and real-event dashboard |
| Prototype Extreme Rain Risk / target ETA | Complete heuristic | Uncalibrated; not cloudburst detection or warning guidance |
| Forecast evaluation | Demo metric only | One real event; +30 and +60 min each have one matched sample |
| MOSDAC, IMD radar/lightning/stations | Status-only before this task | Authentication/manual official files required |
| Multi-sensor fusion, CI, optical flow, alerts, API | Not implemented before this task | Added in staged work below |
| Hail/downburst learned models | Blocked | Verified labels and sufficient samples are unavailable |

## Delivery stages

1. **Truth and contracts** â€” typed source assets, resolution, temporal support,
   per-variable lineage, feature flags, and a frozen CMORPH regression path.
2. **Official-file ingestion** â€” MOSDAC satellite, IMD radar, lightning and
   surface manual-import loaders. Product-specific decoding is enabled only after
   actual official metadata identifies the format and variables.
3. **Common weather cube** â€” configurable analysis grid with explicit native and
   processed resolution, resampling method, availability, and missing masks.
4. **Digital twin and explainable analytics** â€” sensor evidence attached without
   silent imputation; CI score and lightning jump only when inputs support them;
   unsupported hail/downburst states are first-class outputs.
5. **Nowcasting** â€” retain linear motion; add raster motion/advection with explicit
   fallback and leads +10/+20/+30/+60/+90/+120. Longer horizons remain capability
   states until environmental inputs and multi-event validation exist.
6. **Operations** â€” event catalog, causal replay, live-source polling with cache and
   retry, alert feed/JSON, and a read-only FastAPI service.
7. **Dashboard and validation** â€” sensor/layer availability, observed/derived/
   forecast/unavailable labels, demo-vs-validated language, and complete handoff docs.

## External blockers

- MOSDAC SSO/order approval and an authorized official INSAT sample are required to
  verify product-specific channel/geolocation decoding.
- IMD radar, lightning, and AWS/ARG access or authorized official files are required
  to verify exact formats and run genuine multi-sensor evaluation.
- Hail and downburst models require authoritative event labels. They remain
  unavailable, not zero-risk.
- A trained 2â€“6 hour model requires synchronized multi-event observations, a
  chronological event-grouped split, and genuine held-out evaluation.

## Validation policy

Only genuine later observations may produce performance metrics. Synthetic fixtures
are test-only and carry `is_synthetic=true`. The one cached event is a demonstration,
not a general validation dataset. Resampling never changes the stated physical source
resolution.

## Implemented extension status

All seven delivery stages above now have working contracts and automated tests.
CMORPH remains the only connected and real-data-verified source. Generic explicit
local-file adapters, the weather cube, multi-sensor twins, gated analytics, raster
translation nowcasting, live polling, alert rules, FastAPI, and dashboard availability
panels are implemented. Product-specific MOSDAC/IMD/NWP verification, operational
live feeds, hail/downburst models, and trained 2–6 hour forecasting remain blocked by
authorized real files, labels, and a multi-event validation corpus.
