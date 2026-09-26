# Architecture

```text
official archive or authorized local file
                  │
                  ▼
 source adapter ──► raw-asset hash + provider/product metadata
                  │
                  ▼
 native xarray grid / typed point table
                  │
                  ▼
 resolution-aware weather cube (optional sensors stay missing)
                  │
       ┌──────────┴──────────┐
       ▼                     ▼
 baseline rain cells     sensor evidence
 detector + tracker      and gated features
       │                     │
       └──────────┬──────────┘
                  ▼
 multi-sensor twin + hazards + qualitative confidence
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
 deterministic  raster     target ETA /
 track forecast nowcast    alert rules
       └──────────┬──────────┘
                  ▼
         causal analysis snapshot
             ┌────┴────┐
             ▼         ▼
        Streamlit    FastAPI
```

The proven rainfall path remains the default. `ReplayPlayer.analyze` orchestrates
`detect_cells`, `CellTracker.update`, `forecast_track`, risk scoring, and
`calculate_eta`. New services wrap these public interfaces instead of replacing them.

## Core contracts

- `RawAsset` records path, size, SHA-256, provider/product, official URL, access
  method, acquisition time, and synthetic status.
- `VariableLineage` records units, native/analysis resolution, temporal resolution,
  processing steps, resampling, and source record IDs.
- The weather cube uses `time,y,x`, 1-D latitude/longitude coordinates, a paired
  missing mask for each variable, and a temporal tolerance that prevents stale reuse.
- `MultiSensorStormCell` adds evidence histories, availability, lineage, and derived
  acceleration to the backward-compatible rainfall track.
- `AnalysisSnapshot` is the shared transport-neutral output for UI and API.

## Failure boundaries

An optional source may be missing, stale, unsupported, or unauthorized without
breaking the CMORPH path. Manual loaders reject unknown semantics rather than guess.
The live runner rate-limits providers, rejects duplicate/late frames, retries within a
bound, and reports cached-stale or unavailable status. API imports do not download
data. Historical analysis at time T never accesses observations after T; only the
separate evaluator compares forecasts with later truth.

## Interfaces

The Streamlit application reads the compact event from disk and remains useful
offline except for optional basemap tiles. FastAPI exposes `/health`, `/sources`,
`/events`, `/storms`, `/storms/{id}`, `/nowcast`, `/hazards`, `/alerts`, and
`/evaluation`. Analysis endpoints return HTTP 503 with a preparation command when
event data is absent.

