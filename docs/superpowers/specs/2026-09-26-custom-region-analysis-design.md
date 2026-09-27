# Configurable CMORPH Region Analysis Design

## Intent

Extend the existing StormNowcast application with a geographically configurable
NOAA CMORPH workflow. A user selects a supported region and inclusive UTC time
window, previews it, prepares an official-data event, and opens that event in the
existing replay, detection, tracking, deterministic-nowcast, risk, ETA, and
verification interfaces.

The cached north-west India event remains immutable and is the default whenever no
event ID is selected. This extension does not change the scientific interpretation
of CMORPH, add meteorological sources, or duplicate analysis algorithms.

## Goals

- Support center-and-size and explicit bounding-box region entry.
- Support any non-dateline-crossing rectangle within the CMORPH grid, capped at
  20 degrees of latitude by 20 degrees of longitude.
- Support inclusive, half-hour-aligned UTC windows longer than zero and no longer
  than 24 hours. A full 24-hour span contains 49 observations.
- Download only the official hourly NOAA CPC files needed by the requested frames,
  reuse validated cache files, and preserve provenance.
- Store custom events separately and make them reopenable offline.
- Share one EventBuilder and repository across Streamlit, FastAPI, and an optional
  command-line entry point.
- Make custom-event creation atomic, concurrency-safe, and recoverable after an
  interrupted process.
- Delete only validated custom events addressed by repository event ID.
- Keep the existing CMORPH replay and analysis APIs backward compatible.

## Non-goals

- Place-name geocoding or a new mapping dependency.
- Dateline-crossing regions.
- More than 24 hours or more than 20 degrees per side in one request.
- New INSAT, radar, lightning, NWP, machine-learning, or warning capabilities.
- Deleting shared raw NOAA archives when deleting a custom event.
- Replacing or visually redesigning the existing operations dashboard.

## Authoritative source and coverage

The source remains NOAA Climate Prediction Center
`CMORPH V0.x RAW 8km-30min` from the existing official HTTPS archive. The published
control grid has 4,948 longitudes beginning at 0.036378335 degrees with spacing
0.072756669 degrees, and 1,649 latitudes beginning at -59.963614 degrees with spacing
0.072771377 degrees. The resulting supported latitude interval is
[-59.963614, 59.963615296]. User longitudes use the conventional [-180, 180]
representation. Bounds must be ordered, must not cross the dateline, and may span at
most 20 degrees in either dimension.

The currently accessible V0.x archive tree begins in 2023. Local validation rejects
earlier requests and timestamps later than the latest completed UTC half hour. Actual
file availability remains authoritative: the builder must handle missing archive
hours without implying that every nominal timestamp exists.

CMORPH retains its stated approximately 8 km grid spacing and coarser effective
resolution after cropping. No resampling creates a finer observation claim.

## Canonical request and time semantics

`CustomEventRequest` is the single request model used by the UI, API, builder, and
CLI. It contains bounds, `start_time`, `end_time`, and optional `event_name`.

All timestamps are converted to timezone-aware UTC before validation, comparison,
event-ID generation, file enumeration, or manifest serialization. Naive timestamps
are rejected. Start and end are inclusive observation timestamps and must land on a
half-hour boundary (`:00` or `:30`, with zero seconds and microseconds). End must be
later than start and the elapsed span must be at most 24 hours.

Expected frame count is:

```text
((end_time - start_time) / 30 minutes) + 1
```

Thus 00:00 through 05:30 contains 12 frames, and a full inclusive 24-hour span
contains 49 frames. Required source hours are the unique UTC hours containing those
half-hour observations. This definition is identical in UI summaries, API
validation, builder logic, manifests, and tests.

Center-and-size conversion produces the same canonical bounds model. Degree sizes
are split equally around the center. Kilometre sizes are converted geodesically, not
with a fixed kilometres-per-degree constant. The converted rectangle is then subject
to the same coverage, size, ordering, and dateline rules.

## Deterministic identity

Event identity is derived only from the canonical bounds and UTC time window.
`event_name` is display metadata and never influences IDs or filesystem paths. The
ID contains a readable prefix and center plus a short digest of the complete
canonical request, for example:

```text
cmorph-custom-20240518T0000Z-10p50N-76p00E-a1b2c3d4
```

Equivalent canonical requests therefore reuse the same event even when their display
names differ. Repository methods accept validated event IDs, never filesystem paths.

## Storage layout

```text
data/
  raw/cmorph/                         shared provider archive cache
  events/custom/
    .locks/                           per-event ownership records
    <event-id>/
      event.nc                        normalized regional observations
      manifest.json                   versioned event metadata and readiness
      provenance.json                 source-file provenance records
```

Temporary builds use unique sibling directories named `.tmp-<event-id>-<uuid>`.
They are never included in the event library. The existing built-in processed event,
its provenance, and `configs/events.yaml` remain unchanged.

`manifest.json` begins with `schema_version: 1` and `kind: custom`. It records:

- deterministic event ID and display name;
- canonical bounds and inclusive UTC window;
- expected and actual frame counts;
- provider, product, native resolution, creation time, and data paths;
- source URLs/files and cache-reuse state;
- checksums for `event.nc` and `provenance.json`;
- approximate stored size;
- readiness and qualified analysis summary;
- warnings and scientific limitations.

The manifest is structurally validated. Its recorded checksums and the structural
contracts of `event.nc` and `provenance.json` are verified before a cached event is
reported ready.

## Event repository

`EventRepository` merges immutable built-in records from `configs/events.yaml` with
validated custom manifests discovered beneath the custom root. Custom records cannot
shadow built-in IDs. Invalid or incomplete directories are excluded from normal
selection and reported as invalid repository entries rather than silently loaded.

Readiness validation requires a supported manifest schema, matching directory and
manifest event IDs, regular non-symlink files, matching checksums, normalized xarray
structure, exact time bounds/frame count, and valid provenance structure. Reopening a
cached event always performs this validation before returning `ready`.

Deletion resolves only a repository event ID. It rejects built-in IDs, unknown IDs,
symlinks, manifest/directory identity mismatches, unsupported ownership envelopes,
and any resolved path not directly beneath the configured custom root. A minimally
valid ownership envelope (`kind`, supported schema, and matching ID) permits removal
of a custom event whose processed data are incomplete. Shared raw files and built-in
data are never removed.

## Locking and stale-lock recovery

The builder creates a per-event lock atomically with exclusive file creation. Lock
metadata contains event ID, process ID, hostname, owner token, and UTC acquisition
time. A current lock produces `EVENT_BUILD_IN_PROGRESS`; the builder never performs
duplicate work.

Locks older than a configured two-hour stale threshold are recoverable. Recovery
uses an atomic ownership-token transition so two contenders cannot both claim the
same stale lock. The lock is released in `finally` only when its owner token matches.
Every failure also removes that build's path-safe temporary directory. No retry or
cleanup operation targets a path outside the custom-event root.

## Official-file caching and validation

The existing `CmorphSource` constructs only official NOAA CPC HTTPS URLs. For each
required hour, the builder:

1. Looks for the shared cached archive and metadata.
2. Validates the official URL, non-empty size, compression stream, exact decompressed
   CMORPH byte length, checksum, and parsability for the requested bounds.
3. Reuses the file without a network request when valid.
4. Removes only the exact invalid generated cache entry and metadata, then performs
   one official redownload attempt.
5. Fails with a typed error if the initial request plus that single retry cannot
   produce a valid file.

Retry behavior is bounded. There is no recursive or unbounded network loop. Cache
metadata preserves official URL, source filename, byte count, SHA-256 checksum,
original acquisition time, and last validation time. Existing valid cache files that
predate sidecar metadata may be adopted after full validation; their file timestamp
is recorded as the best available acquisition evidence and that qualification is
included in processing history.

## EventBuilder transaction

`CmorphEventBuilder.prepare(request, progress=None)` is the orchestration boundary.
It is synchronous for this MVP but has no UI or HTTP dependencies, so a future job
runner can invoke it unchanged.

The transaction is:

1. Canonicalize and validate the request.
2. Compute the deterministic event ID.
3. Acquire the event lock.
4. Revalidate and reuse an existing complete event when possible.
5. Create a unique temporary event directory.
6. Enumerate the minimum official source hours.
7. Validate or download each source file.
8. Parse each official binary file, crop the requested region, concatenate, remove
   duplicate timestamps, and select exactly the inclusive requested observations.
9. Verify expected timestamps and frame count without fabricating missing frames.
10. Preserve NaNs and produce the paired missing mask.
11. Write NetCDF and provenance into the temporary directory.
12. Run the existing replay/detection/tracking analysis to summarize readiness.
13. Write the versioned manifest and verify the complete temporary event.
14. Atomically rename it to the deterministic final directory.
15. Release the lock in `finally`.

If any step fails, the visible library is unchanged. Temporary data inside this
repository are safely removed. On Windows/OneDrive an atomic-promotion failure is
reported as `EVENT_STORAGE_FAILED`; because the temporary directory is within the
visible repository, it is cleaned rather than retained. Diagnostics contain the
stage and error code without exposing credentials or stack traces to the UI.

## Analysis sufficiency and scientific behavior

Prepared data enter `ReplayPlayer` and `AnalysisService`; detection, tracking, risk,
forecast, ETA, and evaluation logic are not copied into the builder, API, or UI.

- One observation state supports observed rainfall, detection, and the rainfall risk
  heuristic, but not motion forecast or ETA.
- At least two valid observations of a tracked cell are required before issuing the
  deterministic motion forecast.
- Evaluation uses only later real observations at exact valid times.
- Missing future truth yields `Insufficient future observations for verification.`
- Missing motion history yields `Insufficient temporal history for motion forecast.`
- A valid event with no finite rainfall or no detected cells remains preserved and
  reopenable. `analysis_ready` remains true for observation display, while the
  analysis summary records zero cells and unavailable track-dependent outputs.

These rules apply to built-in and custom events without changing the proven built-in
analysis at frames with sufficient history.

## Dashboard interaction

The established operations design remains authoritative. The workflow selector
offers `Historical Replay`, `Analyze New Region`, and preserved `Live Mode`.

`Analyze New Region` is a full-width preparation workspace with:

- center-and-size or bounding-box entry;
- degree or kilometre size units;
- optional Kerala, Delhi NCR, Mumbai, Bengaluru, and Chennai convenience presets;
- date, first-observation UTC time, and last-observation UTC time;
- a no-download preview map showing the box and center;
- a request summary showing bounds, inclusive span, expected frame count, required
  hourly files, and native-resolution disclosure;
- one `Download & Analyze` primary action.

The progress surface reflects real callbacks from the builder and analysis:

1. Checking archive
2. Validating cached observations
3. Downloading official observations
4. Cropping study region
5. Preparing event atomically
6. Detecting and tracking cells
7. Building available forecasts
8. Complete

Success selects the new event, resets the target to its bounding-box center, chooses
an analysis frame, clears only relevant Streamlit resource caches, and reruns into
Historical Replay. Errors are mapped from stable codes to concise corrective copy.

The event selector prefixes `Built-in` and `Custom` entries. A validated custom event
shows approximate stored size and an inline confirmation flow for deletion. Previously
prepared events reopen without network access.

The replay map derives center and zoom from event bounds and changes its UI revision
when the event changes. The selected cell retains full amber/magenta emphasis; other
cells use quieter line weight and opacity. Target coordinates default to event center.
An outside-region target remains allowed with a visible warning.

## FastAPI interaction

The API remains backward compatible. When `event_id` is omitted, all existing
analysis routes continue to use the built-in event.

New routes are:

- `POST /events/prepare` — synchronously invoke the shared EventBuilder and return
  the manifest, `created`/`reused` state, and qualified readiness;
- `GET /events` — list the merged built-in/custom library;
- `GET /events/{event_id}` — return one repository record and readiness;
- `DELETE /events/{event_id}` — remove a validated custom event by ID only.

Existing `/storms`, `/storms/{storm_id}`, `/nowcast`, `/hazards`, `/alerts`, and
`/evaluation` accept an optional event ID and load the selected event through a
service cache keyed by repository identity and artifact checksum. No route contains
download, parsing, or scientific-analysis implementation.

## Error contract

Every domain error carries a stable `code`, human-readable `message`, and optional
structured `details`. The initial codes and HTTP mappings are:

| Code | HTTP | Meaning |
|---|---:|---|
| `INVALID_BOUNDS` | 422 | Coordinates are unordered or invalid |
| `REGION_TOO_LARGE` | 422 | Width or height exceeds 20 degrees |
| `OUTSIDE_CMORPH_COVERAGE` | 422 | Latitude is outside the provider grid |
| `DATELINE_CROSSING` | 422 | Requested bounds cross the dateline |
| `INVALID_TIME_WINDOW` | 422 | UTC, alignment, ordering, or 24-hour rule failed |
| `UNSUPPORTED_ARCHIVE_DATE` | 422 | Date is outside the accessible archive period |
| `EVENT_BUILD_IN_PROGRESS` | 409 | Another owner holds the event lock |
| `NOAA_UNAVAILABLE` | 503 | Required official source file cannot be obtained |
| `NOAA_FILE_CORRUPT` | 502 | Official/cache file failed bounded validation |
| `CACHED_EVENT_INVALID` | 409 | Existing custom event failed readiness validation |
| `EVENT_NOT_FOUND` | 404 | Repository ID is unknown |
| `BUILTIN_EVENT_PROTECTED` | 409 | Mutation targeted an immutable built-in event |
| `UNSAFE_EVENT_PATH` | 409 | Repository ownership/path validation failed |
| `EVENT_STORAGE_FAILED` | 507 | Temporary write or atomic promotion failed |

Streamlit maps the same codes to inline field errors, warnings, or operation failures.
Unexpected internal exceptions are logged and converted to a generic safe message;
raw stack traces are not presented to users.

## Verification strategy

Implementation follows test-driven development in six slices:

1. Region/time validation and deterministic identity, including geodesic conversion,
   coverage, dateline rejection, and the 49-frame inclusive 24-hour case.
2. Official URL enumeration, byte-layout validation, bounded download recovery,
   cache adoption, and no-duplicate-download behavior with mocked HTTP.
3. Versioned repository records, artifact integrity, exclusive/stale locks, atomic
   promotion, failure cleanup, safe deletion, and built-in protection.
4. Builder integration with normalized xarray output and existing scientific services,
   including insufficient history/truth and valid no-rainfall/no-cell events.
5. Dashboard workflow, preview, summaries, event library, offline reopening, deletion
   confirmation, target behavior, map fitting, selected-cell emphasis, and errors.
6. API preparation/library/deletion and optional event analysis, with dependency
   injection and built-in-default regression coverage.

Normal unit and integration tests mock network access. A separate real-data smoke path
uses the already cached official global CMORPH files to prepare and reopen a custom
regional event without downloading. Final verification runs the complete pytest suite,
the unchanged built-in preparation command, the offline custom build, Streamlit health,
FastAPI smoke tests, manifest/checksum validation, git checks, and one bounded
desktop/mobile design review plus the mechanical UI detector.

## Documentation

Update `README.md`, `DEMO_GUIDE.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, and
`DATA_SOURCES.md`. Add `CUSTOM_REGION_ANALYSIS.md` covering coordinates, UTC windows,
inclusive frame semantics, coverage, native resolution, caching, event reopening,
deletion, API/CLI examples, errors, and scientific limitations.
