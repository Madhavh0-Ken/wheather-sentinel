# StormNowcast full-system extension design

## Intent and invariants

Extend the existing CMORPH MVP toward the SIH multi-sensor architecture without
replacing or weakening the checkpoint at `3d0a01a`. CMORPH-only operation remains the
default and fallback. Production observations must come from authoritative providers;
unknown formats, missing credentials, absent labels, and insufficient validation are
reported as capability states rather than filled with fabricated data or scores.

The established scientific names remain binding: rainfall objects are **Intense
Precipitation Cells** and the rainfall heuristic is **Prototype Extreme Rain Risk**.
CMORPH keeps its approximately 8 km grid disclosure and coarser effective-resolution
caveat.

## Architecture

```text
Official assets / authenticated or manual imports
        |
        v
Source adapters -> native xarray / point-event tables -> provenance registry
        |                         |
        +-----------> resolution-aware common weather cube
                                      |
                         rainfall baseline detector/tracker
                                      |
                         multi-sensor digital-twin wrapper
                                      |
                +---------------------+---------------------+
                |                     |                     |
       deterministic/flow       explainable CI       hazard registry
           nowcasters               score             and confidence
                +---------------------+---------------------+
                                      |
                            analysis snapshot service
                     / replay / live / alerts / FastAPI \
                                      |
                              Streamlit GIS console
```

Existing `detect_cells`, `CellTracker.update`, `forecast_track`, `calculate_eta`, and
`ReplayPlayer.analyze` stay backward compatible. New orchestration wraps them rather
than rewriting the proven rainfall path.

## Source and provenance contracts

`SourceDescriptor`, `RawAsset`, `SpatialResolution`, `TemporalSupport`,
`VariableLineage`, and `IngestedProduct` describe an untouched official asset and its
native decoded dataset. Asset hashes, provider/product, observation/acquisition time,
native units/resolution, processing steps, resampling method, missing/QC masks,
observed/derived status, and synthetic status are explicit.

Manual adapters accept only user-supplied official files. Generic CF-compatible
NetCDF/HDF5 and explicit CSV column mappings are supported without guessing product
channels or semantics. Unsupported product layouts fail with a precise inspection
report. MOSDAC/IMD status text distinguishes implementation from current data access.

## Common weather cube

The cube uses `time, y, x` dimensions with EPSG:4326 latitude/longitude coordinates.
Only available variables are present. Each data variable carries native spatial and
temporal resolution, analysis-grid resolution, provider/product, observed/derived
status, units, resampling method, and source record IDs. A paired missing mask is
required. Coarse inputs may be aligned to a finer configurable grid for analysis, but
the native resolution remains displayed and no new physical detail is claimed.

Point lightning/station records remain typed event tables until an explicit,
documented aggregation creates a grid.

## Digital twin, CI, hazards, and confidence

`MultiSensorStormCell` wraps the baseline `StormCell` with sensor evidence snapshots,
availability and freshness, acceleration, lineage, and quality explanations. Missing
sensors are never silently imputed.

Convective initiation is an explainable `Convective Initiation Score`, never an
uncalibrated probability. It is computed only from available defensible precursors
such as cloud-top cooling, reflectivity growth, lightning initiation/trend, and
moisture context. With CMORPH alone it returns insufficient data.

Extreme rain remains the existing heuristic. Lightning analytics include observed
counts/trends and a documented jump calculation when official events exist. Hail and
downburst return typed unavailable/insufficient-data assessments until verified labels
support training. Confidence is qualitative and evidence-bearing; probability wording
is reserved for genuinely calibrated models.

## Forecasting

The deterministic +30/+60/+120 minute baseline remains selectable. Raster motion uses
successive gridded fields to estimate translation and advect the latest observation at
+10/+20/+30/+60/+90/+120 minutes. It records input coverage, fallback reason, method,
and increasing heuristic uncertainty. Growth/decay may be bounded from recent real
trends; split/merge behavior is reported from tracking lineage when evidence supports
it. The 2â€“6 hour interface reports training/environmental-data requirements until a
real event-grouped dataset supports an evaluated model.

## Replay, live mode, alerts, and API

Analysis snapshots are transport-neutral Pydantic objects. Replay at T is strictly
causal; only a separate evaluator may reveal later truth. The event catalog records
date, region, sources, frames, and limitations.

Live polling uses provider-specific minimum intervals, bounded retry/backoff, cached
last-valid data, freshness timestamps, and explicit stale/unavailable states. It never
hammers providers or bypasses authentication.

Alerts are pure configurable rule evaluations over supported hazard assessments,
target approach, and confidence. They are shown in the dashboard and serialized as
JSON; no external delivery occurs without explicit future configuration.

FastAPI exposes read-only health, sources, storms, nowcast, hazards, alerts, events,
and evaluation endpoints using shared domain services. Scientific logic is not copied
into route handlers.

## UI and failure behavior

The existing map-first dashboard is preserved. New sensor and hazard sections always
label states as observed, derived, forecast, or unavailable. Native/processed
resolution and timestamps remain visible. A failed optional source degrades to the
last valid or CMORPH-only mode; a missing CMORPH event retains the existing recovery
instructions.

## Verification

Every new behavior follows red-green-refactor tests. Tests cover manual ingestion,
metadata truth, cube alignment, sensor absence, digital twins, CI gating, lightning
trends, raster motion/fallback, confidence, hazards, live failures, alerts, API, and
the frozen CMORPH baseline. Synthetic fixtures are explicitly test-only. Final checks
include all pytest tests, cached real-event preparation, Streamlit health, FastAPI
health, forbidden-claim scans, and real metric sample counts.
