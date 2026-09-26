# Validation record

## Real event

- Source: NOAA CPC CMORPH V0.x RAW 8km-30min.
- Event: 2023-07-09 00:00–05:30 UTC.
- Study area: 29–33°N, 75–79°E (Himachal Pradesh and nearby north-west India).
- Cache: six official hourly archives; 12 half-hour frames.
- Peak in the compact event: 50 mm h⁻¹.
- Synthetic production observations: none.

For the dashboard's default analysis cut (frame 9, 2023-07-09 04:30 UTC), later real
observations yield:

| Lead | Mean position error | Footprint IoU | Track continuity | Matched samples |
|---|---:|---:|---:|---:|
| +30 min | 22.40 km | 0.599 | 100% | 1 |
| +60 min | 23.74 km | 0.522 | 100% | 1 |
| +120 min | Insufficient observations | — | — | 0 |

These are demonstration calculations, not general accuracy estimates. One matched
sample cannot establish forecast skill, and the event was selected for a useful
movement demonstration rather than held out from model development.

## Automated verification scope

The suite covers source URL construction, binary parsing, preprocessing, provenance,
detection, tracking, forecasts, ETA, risk, replay causality, baseline regression,
manual adapters, resolution metadata, weather-cube alignment, sensor absence,
digital twins, initiation gating, lightning analytics, raster motion/fallback,
confidence, hazard availability, live failures, alerts, API routes, visualization,
and Streamlit startup. Synthetic arrays are used only as isolated deterministic test
fixtures; they are not presented as observational evidence.

## Required future validation

- Collect independent events across seasons and regions.
- Define event-grouped chronological train/development/test splits before fitting any
  learned component.
- Report per-lead errors, calibration where applicable, missed/detected event counts,
  and uncertainty intervals with materially larger sample counts.
- Verify every MOSDAC/IMD/NWP decoder against authorized source files and provider
  documentation before enabling it.

