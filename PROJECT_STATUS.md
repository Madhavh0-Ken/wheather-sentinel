# Project status

Status date: 2026-09-28. Protected fallback: git commit `3d0a01a`.

Latest verification in this checkout: **218 tests passed, 0 failed, 1
platform-dependent symlink test skipped** after the real INSAT replay integration.
Built-in and offline custom-event smoke paths plus Streamlit/API health are part of
the final handoff checklist.

| Capability | Status | Qualification |
|---|---|---|
| CMORPH acquisition/parser/extraction | ✅ COMPLETE | Official NOAA CPC source; 12 cached regional frames |
| Historical replay and map | ✅ COMPLETE | 30-minute causal replay with optional native-grid TIR1 layer; online basemap may be unavailable offline |
| Cell detection/tracking | ✅ COMPLETE | Rainfall-derived Intense Precipitation Cells, not confirmed thunderstorms |
| Track speed/direction/intensity trend | ✅ COMPLETE | Derived from cell histories |
| +30/+60/+120 movement forecast | ✅ COMPLETE baseline | Deterministic extrapolation with heuristic uncertainty |
| Target approach / qualified ETA | ✅ COMPLETE | ETA means corridor intersection, not an exact warning time |
| Prototype Extreme Rain Risk | ✅ COMPLETE baseline | Uncalibrated and not cloudburst detection |
| Real-event evaluation | 🟡 PARTIAL | One sample each at +30 and +60 for the default analysis cut; +120 insufficient |
| Multi-sensor source/provenance contracts | ✅ COMPLETE | Typed metadata and explicit missing states |
| MOSDAC INSAT-3DR L1C reader | ✅ COMPLETE | Genuine `3RIMG_L1C_ASIA_MER` files verified; TIR1/WV calibrated to kelvin with provenance |
| Optional INSAT replay evidence | ✅ COMPLETE | Backward-only, 30-minute maximum age, explicit masks; built-in mapping is 12 frames at 15 minutes |
| Generic IMD/NWP local-file adapters | 🟡 PARTIAL | Official authenticated or user-supplied samples are the blocker |
| Resolution-aware weather cube | ✅ COMPLETE | Missing masks and lineage; no silent imputation |
| Multi-sensor digital twin | ✅ COMPLETE | Built-in event carries CMORPH analysis plus optional causal INSAT evidence |
| Convective Initiation Score | 🟡 PARTIAL | Implemented but unavailable with CMORPH alone; precursor evidence required |
| Lightning jump analytics | 🟡 PARTIAL | Implemented; no verified lightning file connected |
| Raster +10 to +120 minute translation nowcast | 🟡 PARTIAL | Tested with synthetic fields; not enabled in the real replay |
| Event-separated training-data pipeline | ✅ COMPLETE | Real event yields 7/6/4/2/0 samples at +30/+60/+120/+180/+360 |
| Live runner | 🟡 PARTIAL | Framework tested; no provider-specific live source configured |
| Alert engine / JSON | ✅ COMPLETE | Prototype feed only; no external delivery |
| FastAPI event operations | ✅ COMPLETE | Prepare/list/detail/delete plus event-scoped analysis; omitted ID preserves built-in default |
| Hail model | 🔴 BLOCKED | No verified labels; absence is not reported as zero risk |
| Downburst model | 🔴 BLOCKED | Verified gust/radar/report labels are absent |
| Learned 2–6 hour forecast | 🔴 BLOCKED | One event cannot support train/validation/test and held-out evaluation |

## Configurable region status

- Configurable CMORPH regions: complete. Requests support center/size or explicit
  bounds, with 20 by 20 degree and inclusive 24-hour caps (49 observations).
- Custom-event repository: complete. Versioned manifests, checksums, locks, atomic
  promotion, offline reopening, and ID-only safe deletion are verified.
- FastAPI event operations: complete. Prepare/list/detail/delete and event-scoped
  analysis preserve the built-in default when `event_id` is omitted.

## Repository map

```text
StormNowcast/
├── app.py                         Streamlit GIS console
├── configs/                       Runtime and event catalog YAML
├── data/
│   ├── manual/                    Official user-supplied input landing areas
│   ├── raw/                       Download cache (generated/ignored)
│   ├── events/custom/             Atomic custom events (generated/ignored)
│   └── processed/                 Compact built-in replay and provenance (generated/ignored)
├── scripts/
│   ├── prepare_demo.py            Prepare/verify real CMORPH event
│   ├── prepare_custom_event.py    Prepare bounded reusable CMORPH event
│   ├── ingest_official.py         Explicit manual official-file import
│   └── build_training_dataset.py  Build causal per-horizon artifacts
├── src/storm_nowcast/
│   ├── data/                      Sources, parsers, provenance, adapters
│   ├── training/                  Leakage-safe event/horizon datasets
│   ├── fusion/                    Alignment and weather cube
│   ├── detection/, tracking/      Cells, IDs, histories, twins
│   ├── nowcast/, hazards/, eta/   Forecast and qualified impacts
│   ├── replay/, services/, live/  Causal orchestration
│   ├── alerts/, api/              Rules and event-aware service
│   └── visualization/             Map and status panels
└── tests/                         Unit, integration, regression, UI, and API tests
```

## Next data-based work

1. Obtain one authorized IMD radar/lightning sample with metadata documentation.
2. Retain only non-restricted INSAT structural fixtures; genuine local source and
   processed files remain ignored.
3. Assemble multiple independent Indian rainfall events and evaluate by event-grouped
   chronological splits.
4. Enable raster nowcasting on the real replay only after its field mapping and
   evaluation are demonstrated.
5. Consider learned hail/downburst or 2–6 hour models only after authoritative labels
   and environmental predictors exist.
