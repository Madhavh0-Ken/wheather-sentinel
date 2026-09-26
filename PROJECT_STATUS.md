# Project status

Status date: 2026-09-26. Protected fallback: git commit `3d0a01a`.

Latest verification in this checkout: **98 tests passed, 0 failed**; cached CMORPH
preparation and a fresh Streamlit health check passed. FastAPI route tests are part
of the complete suite.

| Capability | Status | Qualification |
|---|---|---|
| CMORPH acquisition/parser/extraction | Working with real data | Official NOAA CPC source; 12 cached regional frames |
| Historical replay and map | Working | 30-minute causal replay; online basemap may be unavailable offline |
| Cell detection/tracking | Working | Rainfall-derived Intense Precipitation Cells, not confirmed thunderstorms |
| Track speed/direction/intensity trend | Working | Derived from cell histories |
| +30/+60/+120 movement forecast | Working baseline | Deterministic extrapolation with heuristic uncertainty |
| Target approach / qualified ETA | Working | ETA means corridor intersection, not an exact warning time |
| Prototype Extreme Rain Risk | Working heuristic | Uncalibrated and not cloudburst detection |
| Real-event evaluation | Working where observations exist | One sample each at +30 and +60 for the default analysis cut; +120 insufficient |
| Multi-sensor source/provenance contracts | Implemented and tested | Typed metadata and explicit missing states |
| MOSDAC INSAT-3DR L1C reader | Product-specific code and schema tests complete; real-file verification blocked | `3RIMG_L1C_ASIA_MER`; authenticated file required |
| Generic MOSDAC/IMD/NWP local-file adapters | Implemented, not real-data verified | Official authenticated or user-supplied samples are the blocker |
| Resolution-aware weather cube | Implemented and tested | Missing masks and lineage; no silent imputation |
| Multi-sensor digital twin | Implemented and tested | Current real event has rainfall evidence only |
| Convective Initiation Score | Gated | Unavailable with CMORPH alone; requires precursor evidence |
| Lightning jump analytics | Implemented and tested | No verified lightning file connected |
| Raster +10 to +120 minute translation nowcast | Implemented and tested | Not enabled in the default real-event dashboard; synthetic tests only |
| Live runner | Implemented and tested | No provider-specific live source configured |
| Alert engine / JSON | Implemented and tested | Prototype feed only; no external delivery |
| Read-only FastAPI | Working | Eight analysis/source/event endpoint groups plus health |
| Hail/downburst models | Unavailable | No verified labels; absence is not reported as zero risk |
| Learned 2–6 hour forecast | Training data required | No multi-event synchronized training and held-out evaluation corpus |

## Repository map

```text
StormNowcast/
├── app.py                         Streamlit GIS console
├── configs/                       Runtime and event catalog YAML
├── data/
│   ├── manual/                    Official user-supplied input landing areas
│   ├── raw/                       Download cache (generated/ignored)
│   └── processed/                 Compact replay and provenance (generated/ignored)
├── scripts/
│   ├── prepare_demo.py            Prepare/verify real CMORPH event
│   └── ingest_official.py         Explicit manual official-file import
├── src/storm_nowcast/
│   ├── data/                      Sources, parsers, provenance, adapters
│   ├── fusion/                    Alignment and weather cube
│   ├── detection/, tracking/      Cells, IDs, histories, twins
│   ├── nowcast/, hazards/, eta/   Forecast and qualified impacts
│   ├── replay/, services/, live/  Causal orchestration
│   ├── alerts/, api/              Rules and read-only service
│   └── visualization/             Map and status panels
└── tests/                         Unit, integration, regression, UI, and API tests
```

## Next data-based work

1. Download the requested authorized MOSDAC `3RIMG_L1C_ASIA_MER` files for
   2023-07-09 00:00-05:30 UTC and run the product-specific importer.
2. Obtain one authorized IMD radar/lightning sample with metadata documentation.
3. Compare decoded INSAT metadata/ranges against the authorized file and retain only
   non-restricted structural fixtures.
4. Assemble multiple independent Indian rainfall events and evaluate by event-grouped
   chronological splits.
5. Enable raster nowcasting on the real replay only after its field mapping and
   evaluation are demonstrated.
6. Consider learned hail/downburst or 2–6 hour models only after authoritative labels
   and environmental predictors exist.
