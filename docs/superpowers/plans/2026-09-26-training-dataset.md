# Event-Separated Training Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build causal, horizon-specific nowcast datasets and leakage-safe event splits before any learned model is trained.

**Architecture:** A new `training.dataset` module converts event xarray datasets into immutable numpy-backed horizon datasets with explicit sample metadata. Separate split and normalization functions enforce whole-event chronological partitions and train-input-only statistics. A CLI serializes available horizons plus a truth-bearing manifest from the existing event catalog.

**Tech Stack:** Python 3.11+, numpy, xarray, pydantic, PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-training-dataset-design.md`

## Global Constraints

- Production samples must come only from event datasets already marked non-synthetic.
- No history timestamp may be later than T; no target may be at or before T.
- Samples never cross event boundaries and splits never divide an event.
- Normalization uses training inputs only, never targets or validation/test data.
- One event must report split/model status `UNAVAILABLE`, not fabricate validation.

## Review Focus

- Missing exact timestamps must skip a sample rather than interpolate.
- Overlapping events assigned across splits must be rejected.
- Validation/test extremes must not alter fitted normalization statistics.
- Empty horizons such as +360 minutes must be reported with zero samples.
- Real cached data must remain unmodified and the CMORPH replay must still pass.

---

### Task 1: Causal horizon datasets and leakage-safe split contracts

**Files:**
- Create: `src/storm_nowcast/training/__init__.py`
- Create: `src/storm_nowcast/training/dataset.py`
- Create: `tests/test_training_dataset.py`

**Interfaces:**
- Produces: `build_horizon_datasets(...) -> dict[int, HorizonDataset]`, `chronological_event_split(...) -> EventSplit`, `fit_training_normalization(...) -> NormalizationStats`, and `HorizonDataset.to_xarray() -> xr.Dataset`.

- [ ] Write failing tests for exact history/target indexing, per-lead counts, event isolation, missing-time skipping, chronological split, overlap rejection, train-only normalization, and xarray export.
- [ ] Run the new tests and confirm failure because the training package is absent.
- [ ] Implement the minimal contracts and validation.
- [ ] Run the new tests and complete suite.
- [ ] Commit the core pipeline.

### Task 2: Real-event artifact builder and required documentation

**Files:**
- Create: `scripts/build_training_dataset.py`
- Create: `tests/test_training_cli.py`
- Create: `TRAINING_DATA.md`
- Create: `SENSOR_INTEGRATION.md`
- Modify: `README.md`
- Modify: `PROJECT_STATUS.md`
- Modify: `VALIDATION.md`
- Modify: `FULL_SYSTEM_ROADMAP.md`

**Interfaces:**
- Consumes: Task 1 horizon datasets and `configs/events.yaml`.
- Produces: horizon NetCDF files and `training_manifest.json` with events, samples, leads, split status, leakage policy, and learned-model status.

- [ ] Write a failing CLI test for a one-event manifest with exact counts and unavailable split/model status.
- [ ] Implement the builder and serialize non-empty horizon datasets.
- [ ] Run it against the cached official event and record exact real sample counts.
- [ ] Add the required training and sensor-integration documents and update status/validation/roadmap links without claiming a trained model.
- [ ] Run all tests, cached CMORPH preparation, Streamlit health, manifest validation, and git checks.
- [ ] Commit the verified pipeline and documentation.
