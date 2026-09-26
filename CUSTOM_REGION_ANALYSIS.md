# Custom CMORPH region analysis

StormNowcast can prepare an official NOAA CPC CMORPH event for a user-selected
rectangle and then open it in the same replay, detection, tracking, forecast, risk,
ETA, and verification pipeline as the built-in demonstration.

## Request rules

| Rule | Contract |
|---|---|
| Latitude coverage | `-59.963614` through `59.963615296` |
| Longitude input | `-180` through `180`; west must be below east |
| Maximum region | 20 degrees latitude by 20 degrees longitude |
| Time zone | Timezone-aware UTC only |
| Time alignment | `:00` or `:30`, with zero seconds |
| Maximum elapsed span | 24 hours |
| Endpoint semantics | Start and end observations are inclusive |

The frame count is `((end - start) / 30 minutes) + 1`. A full 24-hour span
therefore has 49 observations and can require 25 hourly source files. Dateline-
crossing boxes are rejected; split such a study area into two requests.

CMORPH has approximately 8 km grid spacing and coarser effective resolution. A crop
does not create finer observations. CMORPH is a satellite precipitation estimate,
not weather radar.

## Dashboard

Choose **Analyze New Region** in the Operations sidebar. You may enter either a
center plus width/height in degrees or kilometres, or explicit south, north, west,
and east bounds. Kerala, Delhi NCR, Mumbai, Bengaluru, and Chennai presets provide
editable centers.

The preview does not download data. It shows the requested box, center, inclusive
span, observation count, and required hourly files. **Download & Analyze** invokes
the shared builder and reports real preparation stages.

When preparation succeeds, StormNowcast selects the event, resets the target to the
event center, and opens Historical Replay. Valid dry/no-cell events remain available;
the observation display is ready while track-dependent output is marked unavailable.
Custom events can be reopened without network access. Only custom events show the
inline deletion flow.

## Command line

This Kerala example uses validated cached files only:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_custom_event.py `
  --min-lat 8.0 --max-lat 12.0 `
  --min-lon 74.0 --max-lon 78.0 `
  --start 2023-07-09T00:00:00Z `
  --end 2023-07-09T01:00:00Z `
  --name "Kerala CMORPH window" `
  --no-download
```

Omit `--no-download` (also available as `--offline`) to permit bounded downloads
from the official NOAA archive. A source acquisition uses at most two attempts. The
command prints the versioned manifest as JSON.

## API

```http
POST /events/prepare
Content-Type: application/json

{
  "min_lat": 8.0,
  "max_lat": 12.0,
  "min_lon": 74.0,
  "max_lon": 78.0,
  "start_time": "2023-07-09T00:00:00Z",
  "end_time": "2023-07-09T01:00:00Z",
  "event_name": "Kerala CMORPH window"
}
```

Library and analysis routes:

```text
GET    /events
GET    /events/{event_id}
DELETE /events/{event_id}
GET    /nowcast?event_id={event_id}&frame=2&target_lat=10.0&target_lon=76.0
```

All existing analysis routes accept optional `event_id`. Omitting it preserves the
built-in CMORPH event as the default. Deletion accepts a validated repository event
ID only; it never accepts a filesystem path and never removes shared raw archives.

Domain errors return a stable contract:

```json
{"code": "DATELINE_CROSSING", "message": "...", "details": {}}
```

Codes include `INVALID_BOUNDS`, `REGION_TOO_LARGE`, `OUTSIDE_CMORPH_COVERAGE`,
`DATELINE_CROSSING`, `INVALID_TIME_WINDOW`, `UNSUPPORTED_ARCHIVE_DATE`,
`EVENT_BUILD_IN_PROGRESS`, `NOAA_UNAVAILABLE`, `NOAA_FILE_CORRUPT`,
`CACHED_EVENT_INVALID`, `EVENT_NOT_FOUND`, `BUILTIN_EVENT_PROTECTED`,
`UNSAFE_EVENT_PATH`, and `EVENT_STORAGE_FAILED`.

## Identity, storage, and integrity

`event_name` is display metadata only. The deterministic `event_id` is derived from
canonical UTC timestamps and bounds, so equivalent requests reuse one event even if
their names differ.

```text
data/raw/cmorph/                 shared validated NOAA cache
data/events/custom/.locks/      per-event locks with owner/time metadata
data/events/custom/<event_id>/
  event.nc
  manifest.json
  provenance.json
```

Builders write a unique temporary sibling directory, verify NetCDF structure,
provenance, schema, identity, timestamps, frame count, and SHA-256 checksums, then
rename it atomically. Failed builds remove their temporary directory and release
their owned lock. Cached custom events are revalidated before they are reported
ready. Shared NOAA files survive custom-event deletion.

## Scientific limits

- A tracked cell needs at least two real observation states before a motion forecast
  or ETA is issued.
- Verification uses only later real observations at exact forecast-valid times.
- No rainfall or no detected cell is a valid observation result, not a provider or
  preparation failure.
- Intense Precipitation Cells are rainfall-derived objects, not confirmed storms.
- Prototype Extreme Rain Risk is an unvalidated heuristic, not an operational
  warning or cloudburst detector.
