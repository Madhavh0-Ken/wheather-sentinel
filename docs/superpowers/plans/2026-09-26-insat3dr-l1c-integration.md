# INSAT-3DR L1C Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict product-specific ingestion path for official MOSDAC `3RIMG_L1C_ASIA_MER` HDF files without weakening the CMORPH fallback or claiming unperformed real-file verification.

**Architecture:** A focused reader in `data/satellite.py` validates the published root schema, decodes channel counts through the file-supplied temperature LUTs, transforms the file-supplied Mercator grid to WGS84, and returns the existing `IngestedProduct` contract. The existing CLI and documentation expose that reader while keeping the generic MOSDAC adapter intact.

**Tech Stack:** Python 3.11+, h5py, numpy, xarray, pyproj, pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-insat3dr-l1c-integration-design.md`

## Global Constraints

- Preserve CMORPH-only replay and all existing public interfaces.
- Production observations must be authoritative and require explicit origin confirmation.
- Synthetic HDF data may appear only in tests and must be marked synthetic.
- Do not call a water-vapour channel brightness temperature a humidity observation.
- Do not claim product verification until an authorized real file is processed.

## Review Focus

- A fill-value count must become missing data, never a valid LUT lookup.
- A count outside the LUT range must fail explicitly instead of clipping.
- A non-L1C or non-Imager file must be rejected before scientific values are emitted.
- Projection metadata must drive coordinates; filenames or hard-coded grids must not.
- Existing generic MOSDAC ingestion and the CMORPH suite must remain green.

---

### Task 1: Product-specific INSAT-3DR L1C reader

**Files:**
- Modify: `src/storm_nowcast/data/satellite.py`
- Create: `tests/test_insat3dr_l1c.py`

**Interfaces:**
- Consumes: `Bounds`, `IngestedProduct`, `RawAsset`, `TemporalSupport`, `VariableLineage`.
- Produces: `load_insat3dr_l1c_asia_mer(path: Path, *, bounds: Bounds, is_synthetic: bool = False, confirmed_official_origin: bool = False) -> IngestedProduct`.

- [ ] Write synthetic official-schema HDF tests for TIR1 LUT decoding, missing values, acquisition time, Mercator-to-WGS84 cropping, native resolution, checksum provenance, and product validation.
- [ ] Run `pytest tests/test_insat3dr_l1c.py -q` and confirm failure because the reader does not exist.
- [ ] Implement the minimal strict reader and reusable private metadata helpers.
- [ ] Run `pytest tests/test_insat3dr_l1c.py tests/test_manual_gridded_adapters.py -q` and confirm all pass.
- [ ] Commit the reader and tests.

### Task 2: CLI, acquisition instructions, and regression verification

**Files:**
- Modify: `scripts/ingest_official.py`
- Modify: `tests/test_ingest_cli.py`
- Modify: `data/manual/mosdac_satellite/README.md`
- Modify: `DATA_SOURCES.md`
- Modify: `PROJECT_STATUS.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `load_insat3dr_l1c_asia_mer(...)` from Task 1.
- Produces: `--source mosdac-insat3dr-l1c` ingestion mode and exact authenticated download instructions.

- [ ] Add a failing CLI test that imports the synthetic documented-format HDF without a variable map or user-supplied resolution.
- [ ] Run the targeted test and confirm the new source choice is rejected.
- [ ] Wire the CLI to the product-specific reader and preserve generic `--source mosdac` behavior.
- [ ] Document product DOI, official product/format/policy URLs, MOSDAC registration/order action, the 2023-07-09 UTC window, destination directory, filename pattern, and command; label real-file verification blocked.
- [ ] Run the targeted adapter/CLI tests, complete pytest suite, cached CMORPH preparation, Streamlit health, and git-status checks.
- [ ] Commit the integration and verified documentation.
