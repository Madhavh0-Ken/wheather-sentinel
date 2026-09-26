# StormNowcast MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete offline-capable Streamlit MVP that downloads and replays official NOAA CMORPH precipitation over India, detects and tracks Intense Precipitation Cells, extrapolates movement, calculates transparent risk/ETA, and evaluates forecasts against later real frames.

**Architecture:** A source adapter converts official CMORPH binary files into a compact regional `xarray.Dataset` with provenance. Focused domain modules operate on normalized arrays and typed models; a replay service orchestrates causal analysis for the Streamlit UI. Optional authenticated providers are isolated status/file adapters and cannot block the CMORPH path.

**Tech Stack:** Python 3.11+, NumPy, pandas, xarray, SciPy, scikit-image, Shapely, PyProj, Plotly, Streamlit, Pydantic Settings, PyYAML, Requests, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-storm-nowcast-design.md`

## Global Constraints

- Always label rainfall-derived objects “Intense Precipitation Cells”; never confirmed thunderstorms.
- Always label the heuristic “Prototype Extreme Rain Risk”; never cloudburst detection.
- Preserve CMORPH's approximately 8 km grid disclosure and NOAA's coarser effective-resolution caveat.
- Use only official NOAA CPC URLs for bundled real observations; preserve acquisition provenance and SHA-256.
- Synthetic data is permitted only in tests and must carry `is_synthetic=true`.
- Forecast leads are exactly +30, +60, and +120 minutes with strictly increasing uncertainty.
- All timestamps are timezone-aware UTC and coordinates are EPSG:4326.
- Python 3.11+ and Windows/VS Code instructions are required.

## Review Focus

- A truncated/wrong-size CMORPH file must fail validation instead of being reshaped silently (Task 2 test).
- Longitudes that cross the 0/360 boundary must subset correctly or raise a clear unsupported-bounds error (Task 2 test).
- A missing frame must not create impossible speed or continuity claims (Task 4 test).
- Stationary/one-observation tracks must not return an exact ETA (Task 6 test).
- Replay analysis at T must not read any observation later than T except inside the explicitly labeled evaluator (Task 7 test).

---

### Task 1: Repository, configuration, and domain schemas

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `configs/default.yaml`
- Create: `src/storm_nowcast/__init__.py`, `src/storm_nowcast/config.py`, `src/storm_nowcast/models/schemas.py`
- Test: `tests/test_config.py`, `tests/test_schemas.py`

**Interfaces:**
- Produces: `load_settings(path: Path | None) -> Settings`; models `Bounds`, `ProvenanceRecord`, `DetectedCell`, `CellObservation`, `StormCell`, `ForecastPoint`, `RiskAssessment`, `ETAResult`, `EvaluationMetrics`.

- [ ] Write failing tests for default/overridden bounds, invalid bounds, UTC timestamps, and explicit synthetic flags.
- [ ] Run `python -m pytest tests/test_config.py tests/test_schemas.py -v` and confirm failures.
- [ ] Add packaging/dependencies, validated settings, YAML configuration, and focused schemas.
- [ ] Run the tests and confirm they pass.
- [ ] Commit `feat: add project configuration and domain models`.

### Task 2: Provenance, official download, and CMORPH parsing

**Files:**
- Create: `src/storm_nowcast/data/sources.py`, `provenance.py`, `download.py`, `rainfall.py`, `satellite.py`, `radar.py`, `lightning.py`, `stations.py`
- Create: `scripts/fetch_data.py`
- Test: `tests/test_provenance.py`, `tests/test_cmorph.py`, `tests/test_sources.py`

**Interfaces:**
- Consumes: `Settings`, `Bounds`, `ProvenanceRecord`.
- Produces: `CmorphSource.build_url(timestamp) -> str`, `download_file(url, destination) -> DownloadResult`, `parse_cmorph_bytes(payload, hour, bounds) -> xr.Dataset`, `load_cmorph_file(path, hour, bounds) -> xr.Dataset`, adapter `status() -> SourceStatus`.

- [ ] Write failing tests for official-host enforcement, URL naming, checksums, coordinate orientation, two 30-minute fields, regional subset, longitude validation, and wrong byte length.
- [ ] Run those tests and confirm failures.
- [ ] Implement resumable safe download, manifest provenance, CMORPH little-endian parsing/subsetting, and honest optional-adapter statuses.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: ingest official CMORPH precipitation`.

### Task 3: Grid validation and Intense Precipitation Cell detection

**Files:**
- Create: `src/storm_nowcast/preprocessing/spatial.py`, `temporal.py`, `grid.py`, `validation.py`
- Create: `src/storm_nowcast/detection/storms.py`
- Test: `tests/test_grid.py`, `tests/test_detection.py`

**Interfaces:**
- Consumes: `xr.DataArray` rainfall rate and `DetectionConfig`.
- Produces: `validate_weather_dataset(ds)`, `grid_cell_area_km2(lat, dlat, dlon)`, `detect_cells(field, timestamp, config) -> list[DetectedCell]`.

- [ ] Write failing tests for ascending coordinates, missing masks, threshold segmentation, minimum area, centroid, intensity statistics, bounds, and footprint geometry.
- [ ] Run tests and confirm failures.
- [ ] Implement validation and connected-component detection with latitude-aware area estimates.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: detect intense precipitation cells`.

### Task 4: Persistent tracking and digital-twin histories

**Files:**
- Create: `src/storm_nowcast/tracking/tracker.py`
- Test: `tests/test_tracking.py`

**Interfaces:**
- Consumes: ordered `list[DetectedCell]` frames.
- Produces: `CellTracker.update(detections, timestamp) -> list[StormCell]`, `haversine_km`, `initial_bearing_deg`; histories include speed, bearing, intensity/area trends, first/last seen.

- [ ] Write failing tests for nearest/overlap matching, stable IDs, unmatched cells, disappearance, missing-frame time deltas, speed, bearing, and trends.
- [ ] Run tests and confirm failures.
- [ ] Implement gated Hungarian assignment and immutable observation histories.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: track precipitation cells across frames`.

### Task 5: Motion forecast and Prototype Extreme Rain Risk

**Files:**
- Create: `src/storm_nowcast/nowcast/motion.py`, `src/storm_nowcast/hazards/extreme_rain.py`
- Test: `tests/test_motion.py`, `tests/test_risk.py`

**Interfaces:**
- Consumes: `StormCell`, configurable lead minutes and risk thresholds.
- Produces: `forecast_track(cell, leads=(30,60,120)) -> list[ForecastPoint]`; `score_extreme_rain_risk(cell) -> RiskAssessment`.

- [ ] Write failing tests for geodesic destination, exact leads, stationary behavior, monotonic uncertainty, score bounds, labels, and visible contributing factors.
- [ ] Run tests and confirm failures.
- [ ] Implement recent-motion extrapolation, uncertainty growth, and transparent bounded scoring.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: add movement forecast and rain risk`.

### Task 6: Target closest approach and qualified ETA

**Files:**
- Create: `src/storm_nowcast/eta/calculator.py`
- Test: `tests/test_eta.py`

**Interfaces:**
- Consumes: target latitude/longitude, forecast points, issuance time.
- Produces: `calculate_eta(target_lat, target_lon, forecasts, issued_at) -> ETAResult` with closest distance, lead, uncertainty, approach flag, optional ETA, and explanation.

- [ ] Write failing tests for corridor intersection, closest forecast, no approach, one-observation/stationary uncertainty, and no unjustified exact ETA.
- [ ] Run tests and confirm failures.
- [ ] Implement geodesic distance comparison and evidence gating.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: calculate target closest approach and ETA`.

### Task 7: Real-event preparation, replay, and evaluation

**Files:**
- Create: `src/storm_nowcast/replay/player.py`, `src/storm_nowcast/evaluation.py`
- Create: `scripts/prepare_demo.py`
- Test: `tests/test_replay.py`, `tests/test_evaluation.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: official regional datasets plus Tasks 3–6 services.
- Produces: `prepare_event(settings) -> PreparedEvent`; `ReplayPlayer.analyze(frame_index, target) -> ReplaySnapshot`; `evaluate_forecasts(snapshot, later_tracks) -> EvaluationMetrics`.

- [ ] Write failing tests for candidate selection scoring, compact NetCDF metadata, replay bounds, strict causal analysis, real-future evaluation isolation, position error, IoU, continuity, and insufficient observations.
- [ ] Run tests and confirm failures.
- [ ] Implement bounded event selection/download, event persistence, replay orchestration, and observed-future metrics.
- [ ] Run tests and confirm they pass.
- [ ] Run `python scripts/prepare_demo.py`, confirm official-host URLs, real multi-frame data, detected/tracked cells, and record the selected event.
- [ ] Commit `feat: prepare and replay real CMORPH event`.

### Task 8: Operational Streamlit dashboard

**Files:**
- Create: `app.py`, `src/storm_nowcast/visualization/layers.py`, `.streamlit/config.toml`
- Test: `tests/test_visualization.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: `ReplayPlayer`, prepared event, source statuses.
- Produces: `build_map(snapshot, target) -> plotly.graph_objects.Figure`; Streamlit entry point with replay, inspector, ETA, evaluation, provenance, and limitation panels.

- [ ] Write failing tests for OBSERVED/DERIVED/FORECAST layer labels, uncertainty ordering, missing-event message, and import/startup safety.
- [ ] Run tests and confirm failures.
- [ ] Implement responsive dark console UI, map layers, replay controls, cell/target panels, evaluation, provenance, and graceful empty/error states.
- [ ] Run tests and confirm they pass.
- [ ] Commit `feat: add StormNowcast operations dashboard`.

### Task 9: Documentation and end-to-end verification

**Files:**
- Create: `README.md`, `DATA_SOURCES.md`, `PROJECT_STATUS.md`
- Modify: all files needed by discovered defects.

**Interfaces:**
- Consumes: verified commands, actual selected event metadata, test and smoke-test results.
- Produces: honest setup/run/data/demo documentation and final working repository.

- [ ] Document problem, solution, ASCII architecture, Windows/VS Code setup, source acquisition, algorithms, replay, limitations, manual MOSDAC/IMD steps, status matrix, and five-minute demo.
- [ ] Run `python -m pytest -q` and fix every failure.
- [ ] Run `python scripts/prepare_demo.py --no-download` and verify the cached real event end-to-end.
- [ ] Launch `python -m streamlit run app.py --server.headless true --server.port 8501`, request the health endpoint, inspect logs, and stop cleanly.
- [ ] Check the repository for forbidden scientific wording, fake observations, invented metrics, secrets, and untracked required files.
- [ ] Commit `docs: complete StormNowcast MVP handoff`.
