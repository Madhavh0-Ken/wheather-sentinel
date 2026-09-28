# Real INSAT Replay Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the twelve genuine MOSDAC INSAT-3DR observations to the existing built-in CMORPH replay with strict causal alignment, truthful provenance, optional native-grid TIR1 display, and complete CMORPH-only fallback.

**Architecture:** Strict processed-INSAT loading produces existing `IngestedProduct` values with per-time provenance. The existing weather cube gains backward-only temporal alignment and emits explicit alignment metadata and masks; `ReplayPlayer` consumes that optional cube and projects its evidence through the existing digital twin, API, and dashboard without modifying the CMORPH event artifact.

**Tech Stack:** Python 3.11+, NumPy, xarray, h5netcdf, Pydantic, Plotly, Streamlit, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-real-insat-replay-integration-design.md`

## Global Constraints

- Use the existing fusion/weather-cube/replay path as the only temporal-selection authority.
- Select only INSAT observations at or before the replay time and no older than 30 minutes by default.
- Preserve the twelve specified mappings and exact 15-minute ages for the built-in event.
- Exclude out-of-window files by validated observation time, never by a filename exception.
- Do not modify or rebuild `data/processed/cmorph_india_event.nc`.
- Preserve CMORPH-only behavior when the INSAT directory is absent, empty, or partially populated.
- Use only the real `infrared_brightness_temperature` and `water_vapour_brightness_temperature` variables and their recorded metadata.
- Render TIR1 source-grid samples without interpolation or claims of higher physical resolution.
- Keep Convective Initiation unavailable; do not infer thunderstorms, hail, downbursts, or cloudbursts.
- Do not commit HDF5, NetCDF, local provenance, credentials, screenshots, logs, or other generated verification artifacts.

## Review Focus

- Duplicate source times from two processed files must fail instead of receiving an implicit priority (Task 1 test).
- A processed NetCDF whose dataset metadata conflicts with its provenance document must fail explicitly (Task 1 test).
- A future observation within the numeric tolerance must remain unavailable rather than being selected (Task 1 test).
- An observation exactly 30 minutes old must be accepted while one older by any amount must be rejected (Task 1 test).
- A frame whose selected satellite grid is entirely missing must report INSAT unavailable to consumers (Task 2 test).

---

### Task 1: Strict processed INSAT loading and causal weather-cube alignment

**Files:**
- Create: `src/storm_nowcast/data/insat_replay.py`
- Modify: `src/storm_nowcast/fusion/alignment.py`
- Modify: `src/storm_nowcast/fusion/cube.py`
- Create: `tests/test_insat_replay.py`
- Modify: `tests/test_weather_cube.py`

**Interfaces:**
- Consumes: `IngestedProduct`, `RawAsset`, `TemporalSupport`, `VariableLineage`, `build_weather_cube(...)`, and adjacent `.nc.provenance.json` files.
- Produces: `load_processed_insat_observations(directory: Path, *, event_start: datetime, event_end: datetime, max_age_minutes: int = 30) -> list[IngestedProduct]` and `build_insat_replay_cube(directory: Path, *, target_times: tuple[np.datetime64, ...], event_start: datetime, event_end: datetime, max_age_minutes: int = 30) -> xr.Dataset | None`.
- Extends: `ResamplingPolicy.temporal_method` with backward-only selection while keeping `nearest` as the default.

- [ ] **Step 1: Write failing strict-loader and causal-alignment tests**

Add local NetCDF/provenance fixtures and tests named for: real product/channel metadata, all twelve expected mappings, previous-day 23:45 selection, no-future selection, exact 30-minute acceptance, over-age rejection, partial availability masks, missing directory fallback, duplicate-time rejection, provenance conflict rejection, and exclusion of the 09 July 23:45 observation by event time.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_insat_replay.py tests\test_weather_cube.py -q`

Expected: FAIL because the processed replay loader and backward alignment policy do not exist; existing nearest-alignment tests still collect.

- [ ] **Step 3: Implement strict loading and causal cube metadata**

Validate dataset/provider/product/channel units and adjacent provenance, attach processed filename and source provenance to each observation, filter with `event_start - max_age <= observation_time <= event_end`, and reject duplicate times. Extend cube grouping only for matching provider/product variables on distinct times. Emit per-variable observation time, age, availability, source filename, source record ID/provenance, and pixel missing mask. Use the native INSAT coordinate arrays as the cube grid.

- [ ] **Step 4: Run focused fusion tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_insat_replay.py tests\test_weather_cube.py tests\test_resolution_provenance.py -q`

Expected: all selected tests pass; existing nearest selection and duplicate-provider protection remain intact.

- [ ] **Step 5: Commit**

```powershell
git add src/storm_nowcast/data/insat_replay.py src/storm_nowcast/fusion/alignment.py src/storm_nowcast/fusion/cube.py tests/test_insat_replay.py tests/test_weather_cube.py
git commit -m "feat: causally align processed INSAT observations"
```

### Task 2: Replay-frame evidence and digital-twin propagation

**Files:**
- Modify: `src/storm_nowcast/replay/player.py`
- Modify: `src/storm_nowcast/models/twin.py`
- Modify: `src/storm_nowcast/tracking/twin.py`
- Modify: `src/storm_nowcast/services/analysis.py`
- Modify: `tests/test_replay.py`
- Modify: `tests/test_multisensor_twin.py`
- Modify: `tests/test_analysis_service.py`
- Modify: `tests/test_baseline_regression.py`

**Interfaces:**
- Consumes: the pre-aligned satellite cube from Task 1.
- Produces: typed `SatelliteFrameEvidence`, optional `ReplayPlayer(..., satellite_cube=...)`, per-track `SensorEvidence`, and additive frame-level INSAT fields on `AnalysisSnapshot`.

- [ ] **Step 1: Write failing replay/evidence tests**

Test exact 15-minute age propagation, source metadata/provenance, TIR1 and WV availability, pixel masks, nearest source-grid samples at cell centroids, SATELLITE digital-twin availability, an all-missing selected grid becoming unavailable, missing satellite cube fallback, and equality of existing CMORPH-only replay/baseline outputs.

- [ ] **Step 2: Run replay/evidence tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_replay.py tests\test_multisensor_twin.py tests\test_analysis_service.py tests\test_baseline_regression.py -q`

Expected: FAIL on absent satellite frame/evidence fields while existing CMORPH-only cases remain valid.

- [ ] **Step 3: Implement additive replay and service propagation**

Slice only the pre-aligned cube at the selected frame. Treat absent, stale, or all-missing TIR1 as unavailable. Build existing `SensorEvidence` records with actual sampled brightness temperatures and source record IDs. Keep CI inputs unchanged because no cooling-rate field is derived.

- [ ] **Step 4: Run replay/evidence tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_replay.py tests\test_multisensor_twin.py tests\test_analysis_service.py tests\test_baseline_regression.py tests\test_initiation.py -q`

Expected: all selected tests pass and CMORPH-only snapshots remain backward compatible.

- [ ] **Step 5: Commit**

```powershell
git add src/storm_nowcast/replay/player.py src/storm_nowcast/models/twin.py src/storm_nowcast/tracking/twin.py src/storm_nowcast/services/analysis.py tests/test_replay.py tests/test_multisensor_twin.py tests/test_analysis_service.py tests/test_baseline_regression.py
git commit -m "feat: expose INSAT evidence in replay snapshots"
```

### Task 3: Event-scoped loading and FastAPI source state

**Files:**
- Modify: `configs/events.yaml`
- Modify: `src/storm_nowcast/events/catalog.py`
- Modify: `src/storm_nowcast/events/custom.py`
- Modify: `src/storm_nowcast/events/repository.py`
- Modify: `src/storm_nowcast/data/sources.py`
- Modify: `src/storm_nowcast/api/dependencies.py`
- Modify: `src/storm_nowcast/api/app.py`
- Modify: `tests/test_event_catalog.py`
- Modify: `tests/test_event_repository.py`
- Modify: `tests/test_sources.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_api_events.py`

**Interfaces:**
- Consumes: event-scoped optional INSAT directory and Task 1/2 replay construction.
- Produces: built-in event source metadata, real INSAT availability through `/sources` and `/events`, and frame-specific INSAT fields through existing analysis routes.

- [ ] **Step 1: Write failing catalog/API tests**

Use temporary event and INSAT fixtures to assert real built-in CMORPH/INSAT source state, provider/product/provenance in `/nowcast`, unavailable satellite state with missing and partial files, unchanged custom-event behavior, and no local-directory dependency in synthetic service overrides.

- [ ] **Step 2: Run API/event tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_catalog.py tests\test_event_repository.py tests\test_sources.py tests\test_api.py tests\test_api_events.py -q`

Expected: FAIL because event-scoped satellite configuration and API state are absent.

- [ ] **Step 3: Implement event-scoped optional loading and additive responses**

Add optional built-in catalog fields for the processed INSAT directory and maximum age, preserve defaults for old catalogs/custom manifests, and construct the replay cube only for events declaring those fields. Keep all routes and existing response fields. Report radar, lightning, surface/AWS/ARG, and NWP unavailable.

- [ ] **Step 4: Run API/event tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_catalog.py tests\test_event_repository.py tests\test_sources.py tests\test_api.py tests\test_api_events.py -q`

Expected: all selected tests pass with both INSAT-backed and CMORPH-only fixtures.

- [ ] **Step 5: Commit**

```powershell
git add configs/events.yaml src/storm_nowcast/events src/storm_nowcast/data/sources.py src/storm_nowcast/api tests/test_event_catalog.py tests/test_event_repository.py tests/test_sources.py tests/test_api.py tests/test_api_events.py
git commit -m "feat: expose event INSAT state through FastAPI"
```

### Task 4: Existing-dashboard evidence and native TIR1 layer

**Files:**
- Modify: `src/storm_nowcast/visualization/layers.py`
- Modify: `src/storm_nowcast/visualization/panels.py`
- Modify: `app.py`
- Modify: `tests/test_visualization.py`
- Modify: `tests/test_dashboard_extension.py`
- Modify: `tests/test_app.py`

**Interfaces:**
- Consumes: Task 2 replay evidence and Task 3 event source state.
- Produces: optional native-grid TIR1 Plotly trace, frame evidence/provenance panel, and dynamic six-sensor readiness display.

- [ ] **Step 1: Write failing visualization/dashboard tests**

Assert the exact TIR1 label, kelvin colorbar, one marker per finite native sample with no interpolation, no trace for unavailable frames, frame timestamp/age/product/channel/provenance copy, real CMORPH and INSAT readiness, unchanged unavailable sources, and explicit NOAA precipitation versus MOSDAC satellite wording. Assert CI stays unavailable and rainfall objects remain Intense Precipitation Cells.

- [ ] **Step 2: Run visualization/dashboard tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_visualization.py tests\test_dashboard_extension.py tests\test_app.py -q`

Expected: FAIL because the TIR1 layer and dynamic evidence/readiness UI are absent.

- [ ] **Step 3: Implement the additive dashboard layer and panels**

Add the optional layer to the existing observation-layer selector. Render finite source-grid points directly and keep the rainfall layer independent. Feed the dashboard through the same event-scoped replay constructor as the API. Add selected-frame evidence and combined provenance without changing the page layout or hazard language.

- [ ] **Step 4: Run visualization/dashboard tests and verify GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_visualization.py tests\test_dashboard_extension.py tests\test_app.py -q`

Expected: all selected tests pass, including existing responsive/custom-event tests.

- [ ] **Step 5: Commit**

```powershell
git add src/storm_nowcast/visualization app.py tests/test_visualization.py tests/test_dashboard_extension.py tests/test_app.py
git commit -m "feat: show real INSAT evidence in dashboard"
```

### Task 5: Documentation and real-system verification

**Files:**
- Modify: `README.md`
- Modify: `DATA_SOURCES.md`
- Modify: `PROJECT_STATUS.md`
- Modify: `docs/superpowers/specs/2026-09-28-real-insat-replay-integration-design.md` only if verified behavior requires a factual correction

**Interfaces:**
- Consumes: completed integration from Tasks 1–4 and the local ignored real data.
- Produces: accurate operator documentation and recorded verification evidence; no committed data artifacts.

- [ ] **Step 1: Update documentation**

Document event-specific optional INSAT discovery, the two real calibrated variables, provider/product, causal age rule, native 4 km metadata, dashboard layer, CMORPH-only fallback, and scientific limitations. Remove obsolete claims that the reader or real file remains unverified.

- [ ] **Step 2: Run focused INSAT and complete tests**

Run: `.venv\Scripts\python.exe -m pytest tests\test_insat_replay.py tests\test_insat3dr_l1c.py tests\test_weather_cube.py tests\test_replay.py tests\test_api.py tests\test_api_events.py tests\test_dashboard_extension.py tests\test_visualization.py tests\test_app.py -q`

Expected: all focused tests pass.

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: complete suite passes with only documented skips.

- [ ] **Step 3: Run real replay verification**

Run a local script against `data/processed/cmorph_india_event.nc` and `data/processed/insat/` that prints frame count, availability count, selected filename/time/age per frame, variables, provider/product, future-selection count, and selection count for the out-of-window 09 July 23:45 file.

Expected: 12 CMORPH frames, 12 INSAT-available frames, all ages 15 minutes, both real variables present, zero future selections, and zero selections of the out-of-window file. Repeat with a nonexistent INSAT directory and verify 12 CMORPH frames still analyze.

- [ ] **Step 4: Start and verify Streamlit and FastAPI**

Start both services locally without downloads. Check HTTP health, exercise `/events`, `/sources`, and `/nowcast` for the built-in event, capture and inspect the dashboard at a representative replay frame with the TIR1 layer enabled, and confirm the evidence/readiness/provenance/scientific-language states.

Expected: both services start cleanly; API returns real INSAT metadata; dashboard visibly distinguishes precipitation from satellite brightness temperature; no unrelated hazard claim appears.

- [ ] **Step 5: Commit documentation**

```powershell
git add README.md DATA_SOURCES.md PROJECT_STATUS.md docs/superpowers/specs/2026-09-28-real-insat-replay-integration-design.md
git commit -m "docs: document real INSAT replay evidence"
```

- [ ] **Step 6: Verify repository hygiene**

Run: `git status --short --ignored`

Expected: source/test/documentation work is committed; HDF5, NetCDF, local provenance, screenshots, logs, and credentials are not tracked.
