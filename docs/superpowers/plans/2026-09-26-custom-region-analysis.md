# Configurable CMORPH Region Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users prepare, reopen, analyze, and safely delete geographically configurable official NOAA CMORPH events without changing the built-in replay default.

**Architecture:** A canonical custom-event request feeds one synchronous, UI-neutral `CmorphEventBuilder`. The builder uses a validating shared NOAA cache, exclusive per-event locks, atomic event directories, and an `EventRepository` that merges immutable built-ins with versioned custom manifests. Streamlit, FastAPI, and a CLI consume those services; all scientific analysis remains in the existing replay/services layer.

**Tech Stack:** Python 3.11+, Pydantic, xarray/h5netcdf, requests, PyProj, Plotly, Streamlit, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-custom-region-analysis-design.md`

## Global Constraints

- Preserve `configs/events.yaml`, `data/processed/cmorph_india_event.nc`, and the omitted-`event_id` built-in default.
- Use only NOAA CPC `CMORPH V0.x RAW 8km-30min` official HTTPS URLs.
- Accept ordered non-dateline bounds within [-59.963614, 59.963615296] latitude and at most 20 degrees per side.
- Normalize aware timestamps to UTC; reject naive or non-half-hour inputs; use inclusive endpoints and at most 24 hours (49 frames).
- Treat `event_name` as display metadata only; paths use the deterministic event ID.
- Custom manifests use `schema_version: 1` and `kind: custom`.
- No unbounded retry: one initial official request plus one recovery attempt per corrupt/missing file.
- Synthetic data remain test-only; the separate smoke path uses cached official CMORPH.
- UI wording remains Intense Precipitation Cell, Prototype Extreme Rain Risk, and Deterministic Short-Range Nowcast.

## Review Focus

- Center/size conversion near 59.963615296 degrees must reject the converted box when an edge leaves coverage; Task 1 tests this.
- Repeating identical bounds/window with a different display name must reuse the same ID/path; Tasks 1 and 4 test this.
- A non-empty cached archive with the wrong decompressed byte count must be rejected and redownloaded once; Task 2 tests this.
- Two contenders for an expired lock must not both become owners; Task 3 tests atomic stale-lock recovery.
- A forged manifest, symlink, traversal-like ID, or custom record outside the root must never be deleted; Task 3 tests each refusal.

---

### Task 1: Canonical region, time, identity, and error contracts

**Files:**
- Create: `src/storm_nowcast/events/errors.py`
- Create: `src/storm_nowcast/events/custom.py`
- Modify: `src/storm_nowcast/events/__init__.py`
- Create: `tests/test_custom_event_requests.py`

**Interfaces:**
- Produces: `EventErrorCode`, `EventOperationError`, `CustomEventRequest`, `SizeUnit`, `bounds_from_center(...)`, `validate_custom_event_request(request, *, now)`, `custom_event_id(request)`, `required_cmorph_hours(request)`.
- `CustomEventRequest` exposes canonical UTC `start_time`/`end_time`, `bounds`, `center`, `expected_frame_count`, and optional `event_name`.

- [ ] **Step 1: Write failing request-contract tests**

Add tests named `test_inclusive_24_hour_window_has_49_frames_and_25_source_hours`, `test_times_normalize_to_utc_and_naive_time_is_rejected`, `test_center_size_converts_degrees_and_kilometres_to_bounds`, `test_bounds_reject_coverage_size_order_and_dateline_failures_with_stable_codes`, `test_converted_box_near_northern_limit_is_rejected`, and `test_event_id_is_deterministic_and_ignores_display_name`. Use literal Kerala bounds/times and assert exact error codes and frame/hour counts.

- [ ] **Step 2: Run Task 1 tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_custom_event_requests.py -q`
Expected: FAIL because the custom-event contracts do not exist.

- [ ] **Step 3: Implement the minimal contracts**

Use `pyproj.Geod` for kilometre conversion. Format readable event IDs from canonical UTC start and center, then append the first eight hex characters of SHA-256 over canonical bounds plus both endpoints. Domain failures carry `code`, `message`, and `details`.

- [ ] **Step 4: Verify Task 1 GREEN and full regression**

Run: `.venv\Scripts\python.exe -m pytest tests\test_custom_event_requests.py -q`
Expected: all Task 1 tests pass.

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: complete suite passes.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/storm_nowcast/events tests/test_custom_event_requests.py
git commit -m "feat: define custom CMORPH event requests"
```

### Task 2: Validating official CMORPH shared cache

**Files:**
- Create: `src/storm_nowcast/data/cmorph_cache.py`
- Modify: `src/storm_nowcast/data/download.py`
- Modify: `src/storm_nowcast/data/sources.py`
- Create: `tests/test_cmorph_cache.py`

**Interfaces:**
- Consumes: `Bounds`, `CmorphSource.build_url`, `load_cmorph_file`, and `EventOperationError`.
- Produces: `CmorphCache(root, *, downloader, clock, grid_spec=CMORPH_GRID)`, `CachedCmorphAsset`, `CmorphCache.get(hour, bounds, *, allow_download=True)`, and `validate_cmorph_archive(path, *, grid_spec=CMORPH_GRID)`.

- [ ] **Step 1: Write failing cache tests**

Cover official filename/extension enumeration, valid-cache reuse without invoking the injected downloader, legacy-cache adoption after full validation, wrong decompressed byte count, corrupt compression, checksum/URL sidecar mismatch, bounded one-redownload recovery, and final `NOAA_UNAVAILABLE`/`NOAA_FILE_CORRUPT` codes. Use a tiny injected `CmorphGridSpec` and real gzip/bzip2 bytes rather than mocking parser behavior.

- [ ] **Step 2: Run Task 2 tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_cmorph_cache.py -q`
Expected: FAIL because `CmorphCache` is absent.

- [ ] **Step 3: Implement cache validation and bounded recovery**

Write `<archive>.meta.json` atomically with URL, filename, compressed size, SHA-256, acquired UTC time, and validated UTC time. Add `reuse_existing: bool = True` as a keyword-only `download_file` parameter; `False` replaces only the exact validated NOAA cache destination while retaining the host guard and partial-file behavior.

- [ ] **Step 4: Verify Task 2 GREEN and source regressions**

Run: `.venv\Scripts\python.exe -m pytest tests\test_cmorph_cache.py tests\test_sources.py tests\test_provenance.py -q`
Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/storm_nowcast/data tests/test_cmorph_cache.py
git commit -m "feat: validate and reuse CMORPH cache files"
```

### Task 3: Versioned custom-event repository, locks, and safe deletion

**Files:**
- Create: `src/storm_nowcast/events/locking.py`
- Create: `src/storm_nowcast/events/repository.py`
- Modify: `src/storm_nowcast/events/custom.py`
- Create: `tests/test_event_repository.py`

**Interfaces:**
- Consumes: Task 1 errors and canonical event IDs; existing `EventRecord`/`load_event_catalog`.
- Produces: `CustomEventManifest`, `EventLibraryRecord`, `EventBuildLock`, `EventRepository.list_events()`, `get(event_id)`, `validate_directory(path, expected_event_id)`, `validate_ready(event_id)`, `promote(temp_dir, event_id)`, and `delete(event_id)`.

- [ ] **Step 1: Write failing repository and locking tests**

Test merged built-in/custom listing, schema/version checks, NetCDF/provenance checksums, missing processed files, regular-file/symlink rules, exclusive current locks, stale-lock recovery with one winner, owner-token-only release, atomic directory promotion, promotion collision, built-in protection, missing IDs, traversal-like IDs, forged manifest IDs, paths outside root, and custom deletion leaving the shared raw cache untouched.

- [ ] **Step 2: Run Task 3 tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_repository.py -q`
Expected: FAIL because repository and lock types are absent.

- [ ] **Step 3: Implement repository ownership and atomic operations**

Resolve the custom root once. Require final event directories to be direct, non-symlink children. Lock files store event ID, PID, hostname, owner token, and UTC start; stale threshold defaults to two hours. Promotion accepts only a verified temporary direct child and uses one filesystem rename.

- [ ] **Step 4: Verify Task 3 GREEN and catalog regression**

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_repository.py tests\test_event_catalog.py -q`
Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/storm_nowcast/events tests/test_event_repository.py
git commit -m "feat: add safe custom event repository"
```

### Task 4: Transactional EventBuilder and scientifically qualified analysis

**Files:**
- Create: `src/storm_nowcast/events/builder.py`
- Create: `scripts/prepare_custom_event.py`
- Modify: `src/storm_nowcast/replay/player.py`
- Modify: `src/storm_nowcast/eta/calculator.py`
- Create: `tests/test_event_builder.py`
- Modify: `tests/test_replay.py`
- Create: `tests/test_prepare_custom_event_cli.py`

**Interfaces:**
- Consumes: `CustomEventRequest`, `CmorphCache`, `EventRepository`, `EventBuildLock`, `save_event`, and existing analysis services.
- Produces: `BuildStage`, `PreparedCustomEvent`, `CmorphEventBuilder.prepare(request, progress=None, *, allow_download=True)`, and a CLI that delegates to the builder.

- [ ] **Step 1: Write failing builder transaction tests**

With a real repository and injected tiny official-file cache, assert exact inclusive timestamps/frame count, concatenation/de-duplication, preserved NaNs/mask, provenance/source bounds, display-name-only behavior, reused-event validation, real scientific pipeline invocation, valid no-rainfall/no-cell readiness, and one-frame forecast/ETA unavailability. Parameterize failures after lock, temp creation, source acquisition, NetCDF write, manifest write, verification, and promotion; every case must leave no temp directory and no owned lock.

- [ ] **Step 2: Write and run failing CLI behavior test**

The CLI test passes explicit bounds/window and an injected/local test configuration, then asserts the produced deterministic event manifest instead of inspecting source text.

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_builder.py tests\test_prepare_custom_event_cli.py tests\test_replay.py -q`
Expected: FAIL because the builder and sufficiency behavior are absent.

- [ ] **Step 3: Implement minimal transactional orchestration**

`prepare` emits the eight approved `BuildStage` values, performs all work inside `try/finally`, verifies expected timestamps before writing, computes artifact checksums before the manifest, validates the temporary event through the repository, and promotes once. Update replay so histories shorter than two observations get no forecast and receive a qualified unavailable ETA result without changing mature-track outputs.

- [ ] **Step 4: Verify Task 4 GREEN and baseline stability**

Run: `.venv\Scripts\python.exe -m pytest tests\test_event_builder.py tests\test_prepare_custom_event_cli.py tests\test_replay.py tests\test_baseline_regression.py tests\test_pipeline.py -q`
Expected: all selected tests pass and the mature built-in contract remains unchanged.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/storm_nowcast/events src/storm_nowcast/replay/player.py src/storm_nowcast/eta/calculator.py scripts/prepare_custom_event.py tests
git commit -m "feat: prepare transactional custom CMORPH events"
```

### Task 5: Dashboard workflow, event library, and adaptive map

**Files:**
- Modify: `app.py`
- Create: `src/storm_nowcast/visualization/region.py`
- Modify: `src/storm_nowcast/visualization/layers.py`
- Create: `tests/test_region_visualization.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_visualization.py`

**Interfaces:**
- Consumes: Tasks 1, 3, and 4 plus existing `ReplayPlayer`, source panels, and `build_map`.
- Produces: `build_region_preview(bounds)`, `map_view(bounds)`, selected-track-aware `build_map(...)`, and the Streamlit Analyze New Region workflow.

- [ ] **Step 1: Write failing pure visualization and UI-state tests**

Test preview outline/center, zoom decreasing with larger spans, event-specific map revision, selected-track emphasis, built-in/custom labels, 49-frame request summary, default target reset to event center, outside-target warning, no-cell state, insufficient forecast/evaluation copy, deletion controls hidden for built-ins, and workflow presence through `AppTest`. Inject a fake builder/repository below the Streamlit surface; do not assert fake call counts instead of rendered/selected outcomes.

- [ ] **Step 2: Run Task 5 tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_region_visualization.py tests\test_app.py tests\test_visualization.py -q`
Expected: FAIL because the preparation workflow and adaptive map interfaces are absent.

- [ ] **Step 3: Implement the existing-world UI extension**

Keep the map-first visual system and native accessible controls. Use a full-width preparation surface, optional presets, center/box modes, UTC inputs, preview, request summary, `st.status` progress, safe inline deletion confirmation, offline event selection, and error-code-to-copy mapping. On success select the event, reset frame/target state, clear only event-loading caches, and rerun into replay.

- [ ] **Step 4: Verify Task 5 GREEN**

Run: `.venv\Scripts\python.exe -m pytest tests\test_region_visualization.py tests\test_app.py tests\test_visualization.py tests\test_dashboard_extension.py -q`
Expected: all selected tests pass.

- [ ] **Step 5: Run the Impeccable mechanical detector once after UI completion**

Run: `& 'C:\Users\Madhav\.codex\plugins\cache\openai-curated-remote\impeccable\4.3.1\skills\impeccable\scripts\impeccable.cmd' detect --json app.py src/storm_nowcast/visualization/region.py src/storm_nowcast/visualization/layers.py`
Expected: no unresolved mechanical findings; record any non-applicable finding with evidence.

- [ ] **Step 6: Commit Task 5**

```powershell
git add app.py src/storm_nowcast/visualization tests/test_region_visualization.py tests/test_app.py tests/test_visualization.py
git commit -m "feat: add custom region dashboard workflow"
```

### Task 6: FastAPI custom-event operations and event-scoped analysis

**Files:**
- Modify: `src/storm_nowcast/api/app.py`
- Modify: `src/storm_nowcast/api/dependencies.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_api_events.py`

**Interfaces:**
- Consumes: shared builder/repository and `AnalysisService.from_dataset`.
- Produces: `POST /events/prepare`, `GET /events/{event_id}`, `DELETE /events/{event_id}`, dynamic merged `GET /events`, optional `event_id` analysis query, and stable `{code,message,details}` errors.

- [ ] **Step 1: Write failing route tests**

Use real temporary repositories and injected fake source acquisition. Assert request validation/error codes, 49-frame summary, create/reuse results, list/detail/delete behavior, built-in deletion refusal, in-progress `409`, provider `503`, path-safe ID-only deletion, selected custom-event analysis, missing custom event, and omitted-event regression using the existing built-in/service override.

- [ ] **Step 2: Run Task 6 tests and verify RED**

Run: `.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_api_events.py -q`
Expected: FAIL because the mutating event routes and event-scoped service cache are absent.

- [ ] **Step 3: Implement thin API adapters**

Add dependency injection parameters for builder/repository. Convert `EventOperationError` through one handler. Cache analysis services by `(event_id, event_nc_checksum)` and invalidate after delete/rebuild. Preserve the default built-in path and existing response contracts when `event_id` is omitted.

- [ ] **Step 4: Verify Task 6 GREEN and full suite**

Run: `.venv\Scripts\python.exe -m pytest tests\test_api.py tests\test_api_events.py -q`
Expected: all API tests pass.

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: complete suite passes.

- [ ] **Step 5: Commit Task 6**

```powershell
git add src/storm_nowcast/api tests/test_api.py tests/test_api_events.py
git commit -m "feat: expose custom events through FastAPI"
```

### Task 7: Documentation, real cached-data smoke path, and final verification

**Files:**
- Create: `CUSTOM_REGION_ANALYSIS.md`
- Modify: `README.md`
- Modify: `DEMO_GUIDE.md`
- Modify: `PROJECT_STATUS.md`
- Modify: `ARCHITECTURE.md`
- Modify: `DATA_SOURCES.md`

**Interfaces:**
- Consumes: completed UI/API/CLI behavior and official cached source files.
- Produces: exact user/API/CLI instructions, coverage/window/cache/deletion limitations, and a five-minute configurable-region demo flow.

- [ ] **Step 1: Write documentation from verified behavior**

Document both input methods, provider limits, inclusive 49-frame maximum, UTC alignment, official caching, deterministic IDs, event storage, offline reopening, safe deletion, error codes, Kerala UI/API/CLI examples, and unchanged scientific language. Mark network-dependent preparation separately from offline cached reuse.

- [ ] **Step 2: Run the complete automated suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: zero failures.

- [ ] **Step 3: Verify the built-in fallback unchanged**

Run: `.venv\Scripts\python.exe scripts\prepare_demo.py --no-download`
Expected: 12 frames and a detected/tracked demonstration cell.

- [ ] **Step 4: Run a real cached-CMORPH custom-event smoke test**

Use `scripts\prepare_custom_event.py --no-download` for a supported subregion and 2023-07-09 cached hours. Verify manifest schema, requested bounds/times, checksums, processed NetCDF, offline reopen, and that no source download occurs. Remove the generated smoke event through repository deletion, not filesystem paths.

- [ ] **Step 5: Verify Streamlit, API, and visual states**

Start or reuse local Streamlit and FastAPI processes. Check both health endpoints, capture one 1440px desktop and one 390px mobile UI state, inspect both once, fix material issues in one batch if needed, and confirm once. Preserve the built-in default and demonstrate the Analyze New Region preview without requiring a live download.

- [ ] **Step 6: Run integrity and repository checks**

Run: `git diff --check`

Verify no tracked generated event/cache files, no temporary/lock remnants, built-in checksums unchanged, and `git status --short` contains only intended documentation/code before commit.

- [ ] **Step 7: Commit documentation and verified handoff**

```powershell
git add CUSTOM_REGION_ANALYSIS.md README.md DEMO_GUIDE.md PROJECT_STATUS.md ARCHITECTURE.md DATA_SOURCES.md
git commit -m "docs: explain custom CMORPH region analysis"
```

- [ ] **Step 8: Perform whole-branch review**

Review the spec and this plan line by line against the full branch diff. Classify findings as critical, important, or minor; fix all confirmed findings test-first, rerun the relevant focused tests and complete suite, then record final commands and evidence.
