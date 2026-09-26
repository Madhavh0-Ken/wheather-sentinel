# StormNowcast MVP Design

## Purpose

StormNowcast is a scientifically honest, offline-capable Streamlit prototype for demonstrating short-term movement of intense precipitation over a configurable Indian study area. Its primary audience is an SIH judging panel. The MVP must make the complete chain from an official observation to a derived object, track, movement extrapolation, transparent risk score, target proximity result, and replay evaluation visible within a five-minute demonstration.

The product does not diagnose thunderstorms or cloudbursts from rainfall alone. CMORPH-derived objects are always called **Intense Precipitation Cells**, and its hazard output is always called **Prototype Extreme Rain Risk**.

## Scope

The working path is NOAA CPC CMORPH download, binary parsing, regional extraction, replay, cell detection, tracking, motion forecasting, risk scoring, closest approach/ETA, evaluation, and an operational-style dashboard. MOSDAC INSAT and IMD radar/lightning remain typed adapter boundaries with explicit credential or file requirements. Hail, downburst, neural networks, and unvalidated six-hour prediction are excluded.

## Data Source and Event

The primary observation is NOAA CPC CMORPH satellite precipitation. The 8 km grid is 0.072756669 degrees longitude by 0.072771377 degrees latitude, spans 60°S–60°N, and provides two 30-minute rainfall-rate fields per hourly file in little-endian float32 format. NOAA notes that the underlying satellite estimates are coarser than the grid spacing; the application displays this caveat.

The preparation script tries a short ordered list of documented Indian monsoon windows and scores frames by regional high-percentile rainfall and usable temporal continuity. It stops at the first suitable sequence rather than searching indefinitely. The default study area is configurable and initially covers Himachal Pradesh and nearby north-west India (29–33°N, 75–79°E), with July 2023 monsoon dates as the first candidate. At most the small number of hourly source files needed for a 12-frame, six-hour sequence are retained. The chosen event and exact frame count are written into the processed dataset and provenance manifest.

NASA GPM IMERG, MOSDAC, and IMD are not silently substituted for one another. Their adapters report readiness and authentication/manual-file requirements. MOSDAC is documented as requiring SSO; IMD radar and lightning adapters accept official user-supplied files when available.

## Architecture and Data Flow

`scripts/prepare_demo.py` downloads candidate CMORPH `.bz2` files from the official NOAA CPC host, verifies the host, records SHA-256 checksums, parses both half-hour fields, subsets the configured bounding box, validates coordinates and timestamps, and writes one compact NetCDF event plus a JSON provenance manifest.

The domain pipeline consumes the normalized `xarray.Dataset`:

1. Threshold rainfall rate and run connected-component labeling.
2. Reject components below configurable pixel/area limits and convert retained masks to cell records with centroid, area, intensity statistics, bounds, and footprint geometry.
3. Match consecutive cells with a Hungarian assignment cost derived from geodesic centroid distance, bounding-box/footprint overlap, and intensity similarity; unmatched detections receive stable new identifiers.
4. Build `StormCell` history and derive speed, bearing, area trend, and intensity trend from observed states only.
5. Extrapolate the recent geodesic motion to +30, +60, and +120 minutes. Attach uncertainty radii that strictly increase with lead time and reflect recent motion inconsistency.
6. Calculate a bounded Prototype Extreme Rain Risk score from current intensity, observed trend, persistence, movement speed, and growth. Expose the normalized factors and human-readable contributors.
7. Compare forecast segments and uncertainty radii with a target point. Report closest approach and a qualified ETA only when the target falls within the uncertainty corridor.
8. Compare forecasts issued at replay time T against later detected observations using position error, IoU where footprints exist, and track continuity. Never invent missing metrics.

## Internal Models and Boundaries

Pydantic/dataclass models represent provenance, observations, detected cells, tracked states, forecasts, risk assessments, ETA results, and evaluation metrics. Data adapters implement a small common interface: availability/status, acquisition, and normalized loading. The core algorithms depend only on normalized models and arrays, so future MOSDAC/IMD sources can feed the same pipeline.

All timestamps are timezone-aware UTC. Geographic coordinates use EPSG:4326; distances, bearings, and destination points use geodesic calculations. Area is estimated from latitude-aware grid-cell dimensions. Missing and invalid values stay masked and cannot create detections.

## Dashboard

The Streamlit app uses a wide layout with a dark, operational weather-console theme. A status header shows event time, official source, native grid spacing/resolution caveat, frame count, and pipeline health. The main map displays the rainfall raster, observed cell footprints and centroids, persistent IDs, observed history, forecast points/lines, increasing uncertainty circles, and a target marker.

Replay controls select an event and frame and provide previous, next, and timed play. The selected frame only uses observations at or before its timestamp. A cell inspector shows current intensity, area, speed, bearing, trends, forecasts, risk factors, and limitations. A target panel reports closest approach, qualified ETA, and uncertainty. An evaluation panel calculates metrics from later real frames when they exist. A provenance panel exposes original URLs, timestamps, processing, and checksums.

Visual semantics are fixed: blue/cyan for **OBSERVED**, amber for **DERIVED**, and magenta/dashed for **FORECAST**. Synthetic data is rejected by the application unless explicitly enabled for tests and is prominently marked if ever displayed.

## Failure Handling

Download failures identify the URL and preserve already cached files. The preparation script can resume. Malformed binary size, bad coordinates, missing frames, or checksum mismatches produce actionable errors. The dashboard never fabricates fallback observations: when the processed event is absent it presents the exact preparation command; when a source-specific input is absent it presents that adapter's requirement.

Sparse or stationary tracks return low-confidence movement and no unjustified ETA. Evaluation returns “Insufficient observations for validated metric.” for leads without future truth. One failed optional adapter cannot break the CMORPH pipeline.

## Testing and Acceptance

Unit tests use clearly marked synthetic fixtures for configuration, grids, CMORPH binary parsing, coordinate orientation, segmentation and centroids, assignment and persistent IDs, geodesic speed/bearing, forecasts and monotonic uncertainty, risk bounds/contributors, ETA gating, provenance/checksums, replay causality, and evaluation metrics. Integration tests process a tiny deterministic dataset through the full pipeline. Tests never present synthetic values as real observations.

Acceptance also requires an official NOAA download, successful parsing of a real multi-frame Indian sequence, detected and tracked cells in that sequence, calculated forecasts/risk/ETA or a scientifically justified no-ETA result, real forecast evaluation where future observations exist, a passing test suite, and a Streamlit startup health check.

## Documentation and Honest Limitations

README provides Windows/VS Code setup, download, run, replay, and demo instructions plus an ASCII architecture diagram. `DATA_SOURCES.md` records authoritative sources, access constraints, resolution, cadence, variables, and caveats. `PROJECT_STATUS.md` separates implemented, real-data-backed, and validated status.

The dashboard and documentation state that CMORPH is a satellite precipitation estimate, not radar; grid spacing is approximately 8 km while effective source resolution is coarser; detected objects are not confirmed thunderstorms; forecasts are deterministic extrapolations, not operational meteorological forecasts; and the risk score is an unvalidated prototype heuristic rather than cloudburst detection.
