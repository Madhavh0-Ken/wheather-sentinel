# StormNowcast full-system extension implementation plan

**Goal:** Add defensible multi-sensor ingestion, fusion, analytics, operations, API,
and documentation while preserving commit `3d0a01a` as the CMORPH fallback.

**Spec:** `docs/superpowers/specs/2026-09-26-full-system-extension-design.md`

### Task 1: Freeze fallback and add truth-bearing contracts

**Files:** `config.py`, `models/sensors.py`, `models/schemas.py`, `data/sources.py`,
`configs/default.yaml`, `tests/test_baseline_regression.py`, `tests/test_sensor_models.py`.

- Write failing regression and model validation tests.
- Add feature flags, manual paths, source/resolution/lineage models, and truthful statuses.
- Keep existing public rainfall interfaces and outputs unchanged.
- Run targeted and full tests; commit.

### Task 2: Implement official manual-file adapters

**Files:** `data/satellite.py`, `radar.py`, `lightning.py`, `stations.py`, `nwp.py`,
`data/manual.py`, `scripts/ingest_official.py`, `data/manual/**/README.md`, adapter tests.

- Test metadata-driven CF NetCDF/HDF5 inspection, timestamps, bounds, missing values,
  units and provenance before implementation.
- Test explicit official-event CSV mappings for lightning/stations.
- Fail clearly on unknown formats/semantics; never guess channels or IMD layouts.
- Add derived satellite cooling/expansion and lightning window features only where
  metadata and consecutive observations support them.
- Run targeted and full tests; commit.

### Task 3: Build the common weather cube

**Files:** `fusion/cube.py`, `fusion/alignment.py`, `preprocessing/metadata.py`,
`tests/test_weather_cube.py`, `tests/test_resolution_provenance.py`.

- Test `time,y,x` alignment, missing masks, native-vs-analysis resolution, observed/
  derived state and coarse-grid honesty.
- Implement configurable nearest/linear policies and temporal tolerances per variable.
- Preserve source record IDs and resampling methods on every variable.
- Run targeted and full tests; commit.

### Task 4: Add multi-sensor twins and explainable hazard capability

**Files:** `models/twin.py`, `tracking/twin.py`, `initiation/scoring.py`,
`lightning/analytics.py`, `hazards/registry.py`, `confidence/framework.py`, tests.

- Test availability masks, absence without imputation, evidence histories and acceleration.
- Test CI insufficient-data gates and explainable scoring with real-valued test fixtures.
- Test lightning jump method and observed/derived distinctions.
- Wrap current extreme-rain heuristic; return typed unavailable hail/downburst states.
- Add evidence-bearing qualitative confidence.
- Run targeted and full tests; commit.

### Task 5: Add short-range raster nowcasting and long-range capability gates

**Files:** `nowcast/base.py`, `nowcast/optical_flow.py`, `nowcast/capabilities.py`, tests.

- Test exact +10/+20/+30/+60/+90/+120 leads, known translations, growth bounds,
  increasing uncertainty, missing coverage and deterministic fallback.
- Implement translation estimation/advection using installed scientific libraries.
- Keep `forecast_track` as the default and comparison baseline.
- Return explicit training-data-required state for unsupported 2â€“6 hour ML.
- Run targeted and full tests; commit.

### Task 6: Add event catalog, replay/live services and alerts

**Files:** `services/analysis.py`, `events/catalog.py`, `live/runner.py`,
`alerts/engine.py`, `configs/events.yaml`, tests.

- Test causal snapshots, event metadata, duplicate/late live frames, retry, stale cache,
  rule firing, deduplication and suppression of unsupported hazards.
- Share the existing replay/detection/forecast logic rather than duplicate it.
- Write dashboard alert feed and JSON serialization; no external sends.
- Run targeted and full tests; commit.

### Task 7: Add read-only FastAPI service

**Files:** `api/app.py`, `api/dependencies.py`, `tests/test_api.py`, `pyproject.toml`.

- Test all required GET endpoints against the cached event and missing-event states.
- Add FastAPI/uvicorn dependencies and thin handlers over shared services.
- Ensure API import/startup does not download or mutate data.
- Run targeted and full tests; commit.

### Task 8: Upgrade the Streamlit GIS dashboard

**Files:** `app.py`, `visualization/layers.py`, `visualization/panels.py`, UI tests.

- Test availability labels, source timestamps/resolutions, unsupported hazards, mode
  selection and fallback behavior.
- Add historical/live modes, sensor layer controls, twin evidence, CI/lightning states,
  confidence explanations and alert feed without disrupting the existing map.
- Keep unavailable sources explicit and the cached CMORPH replay fully usable.
- Run UI detector/review as required, targeted and full tests; commit.

### Task 9: Complete validation and handoff documentation

**Files:** `README.md`, `DATA_SOURCES.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`,
`MODEL_CARD.md`, `VALIDATION.md`, `DEMO_GUIDE.md`, `THIRD_PARTY_NOTICES.md`.

- Document only verified source access and formats; list authentication blockers.
- Record the exact cached event and tiny demo metric sample counts.
- Run pytest, cached preparation, Streamlit and FastAPI health smoke tests.
- Scan for forbidden claims, secrets, synthetic production observations, and false
  resolution/probability wording.
- Commit the verified handoff.
