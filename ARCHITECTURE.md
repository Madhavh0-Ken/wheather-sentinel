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

Custom CMORPH preparation adds one shared boundary before replay:

```text
CustomEventRequest -> validate UTC/bounds -> deterministic event ID -> event lock
  -> validated shared NOAA cache -> exact inclusive crop -> temporary event
  -> replay-based readiness summary -> checksum/schema verification
  -> atomic promotion -> EventRepository -> Streamlit / FastAPI / CLI
```

The builder is synchronous for this MVP but contains no Streamlit or HTTP logic, so
it can later run in a background worker without changing the data pipeline.

The offline training-data branch is separate from causal replay. It groups complete
events first, then creates independent horizon datasets using exact in-event history
and target timestamps. Whole-event chronological splitting occurs before any model
fitting, and normalization may use training inputs only. With one available event,
artifact generation is permitted but splitting, training, and learned-model scoring
remain unavailable.

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
- `CustomEventManifest` is the versioned ownership/integrity envelope for a custom
  `event.nc` and `provenance.json` pair.
- `EventRepository` is the only path-resolution, readiness, promotion, and deletion
  boundary for custom events.

## Failure boundaries

An optional source may be missing, stale, unsupported, or unauthorized without
breaking the CMORPH path. Manual loaders reject unknown semantics rather than guess.
The live runner rate-limits providers, rejects duplicate/late frames, retries within a
bound, and reports cached-stale or unavailable status. API imports do not download
data. Historical analysis at time T never accesses observations after T; only the
separate evaluator compares forecasts with later truth.

Custom-event locks contain owner and UTC acquisition metadata and allow bounded
stale recovery. Every failed builder transaction removes its owned temporary
directory and releases only its own lock. Existing custom events are revalidated by
schema, structure, timestamps, and checksums before reuse. Deletion resolves a
validated event ID directly beneath the custom root and cannot target built-in or
shared raw data.

## Interfaces

The Streamlit application reads compact events from disk and remains useful offline
except for optional basemap tiles. FastAPI exposes `/health`, `/sources`, event
prepare/list/detail/delete routes, and `/storms`, `/storms/{id}`, `/nowcast`,
`/hazards`, `/alerts`, and `/evaluation`. Analysis routes accept optional `event_id`;
omission preserves the built-in default. Domain failures share stable codes across
the dashboard and API.
