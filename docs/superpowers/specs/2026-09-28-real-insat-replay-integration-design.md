# Real INSAT Replay Integration Design

## Intent

Add the twelve genuine MOSDAC INSAT-3DR L1C ASIA_MER observations to the
existing built-in `cmorph-india-20230709T0000Z` replay as optional satellite
evidence. CMORPH remains the rainfall source and the basis for Intense
Precipitation Cells, tracking, forecasts, risk, and ETA. INSAT remains a
separate satellite observation and must never be described as rainfall, radar,
or proof of a thunderstorm or other hazard.

The integration must preserve the existing weather cube, digital twin, replay,
provenance, API, and dashboard architecture. It must not modify the prepared
CMORPH NetCDF. Removing some or all processed INSAT files must degrade only the
satellite evidence; CMORPH-only replay must continue unchanged.

## Verified real-data contract

The thirteen inspected processed files in `data/processed/insat/` each contain
one observation on a rectilinear `123 x 106` latitude/longitude grid. The two
real observed variables are:

- `infrared_brightness_temperature`, sourced from `IMG_TIR1`, calibrated with
  the file-supplied `IMG_TIR1_TEMP` lookup table, in kelvin, with 4 km native
  metadata.
- `water_vapour_brightness_temperature`, sourced from `IMG_WV`, calibrated
  with the file-supplied `IMG_WV_TEMP` lookup table, in kelvin, with 4 km native
  metadata. It is not humidity.

The files identify provider `ISRO/SAC MOSDAC`, product
`3RIMG_L1C_ASIA_MER`, EPSG:4326 output coordinates, the native file-supplied
Mercator CRS, original HDF SHA-256, channel lineage, and product creation time.
Adjacent `.nc.provenance.json` files retain the original HDF asset metadata and
processing steps. The inspected observations contain no missing pixels, but
the replay contract still emits availability and missing masks for absent,
stale, or partially missing observations.

## Event-scoped discovery and validation

The built-in event catalog declares an optional processed INSAT directory and
the default maximum age of 30 minutes. Custom events do not inherit the
built-in event's local satellite files.

Discovery reads `*.nc` files only from that configured directory, validates
each dataset and adjacent provenance document against the strict INSAT-3DR
product contract, and uses the dataset observation coordinate rather than the
filename as scientific time. Eligible source times lie in the closed interval
from `event_start - maximum_age` through `event_end`. This admits the previous
day 23:45 observation and excludes the unrelated same-day 23:45 verification
file without a filename-specific rule.

Missing directories and empty eligible sets produce an available CMORPH-only
replay. An invalid file inside the eligible time window fails explicitly rather
than being silently relabeled or guessed. Files outside the event window are
ignored after their observation time is validated.

## Causal fusion and masks

The existing fusion/weather-cube path is the single source of truth for
temporal selection. Its resampling policy gains a causal backward mode while
retaining the existing nearest mode for backward compatibility. Causal mode
selects the latest source time satisfying both:

1. `source_time <= target_time`
2. `target_time - source_time <= maximum_age`

It never selects a future observation. The weather cube records, per variable
and replay time, the selected observation time, age in minutes, availability,
source file, source record identifier, and an explicit pixel-level missing
mask. Multiple files for one product may contribute non-overlapping times;
competing providers or duplicate observation times remain errors.

The satellite cube uses the actual INSAT latitude/longitude grid as its target
grid, so no artificial spatial upscaling is performed. For this event its
twelve replay frames must map to 23:45, 00:15, 00:45, 01:15, 01:45, 02:15,
02:45, 03:15, 03:45, 04:15, 04:45, and 05:15 UTC respectively, with an age of
exactly 15 minutes for every frame.

## Replay and digital twin

`ReplayPlayer` continues to validate and analyze the unchanged CMORPH event.
It accepts an optional pre-aligned satellite cube. Each `ReplaySnapshot`
contains either a typed satellite frame or an explicit unavailable state. A
satellite frame carries the two real variables, their masks, observation time,
age, provider, product, processed source filename, original-source provenance,
and channel metadata.

For each active precipitation cell, the existing digital twin receives
satellite `SensorEvidence` sampled from the selected source grid at the cell
centroid. This changes satellite availability and retains source record IDs;
it does not change rainfall-derived cell identity or automatically enable a
Convective Initiation score. Brightness temperature alone is not a cloud-top
cooling rate, so CI remains qualified as unavailable in this task.

## API contract

Existing routes and fields remain valid. Analysis responses add frame-level
INSAT fields with safe unavailable defaults:

- `insat_available`
- `insat_observation_time`
- `insat_age_minutes`
- `insat_product`
- `insat_provider`
- `insat_source_file`
- `insat_provenance`
- `insat_variables`, including availability and missing-pixel summaries

Track sensor availability comes from the existing digital twin and reports
`SATELLITE=AVAILABLE` only when the selected frame has valid, non-stale
evidence. Event/source responses identify the built-in event's real CMORPH and
INSAT inputs while radar, lightning, surface/AWS/ARG, and NWP remain
unavailable. CMORPH-only API construction and synthetic test services retain
the same behavior they have today.

## Dashboard contract

The dashboard keeps its current layout and replay controls. Source readiness
for the built-in event reports real/available CMORPH and INSAT, and unavailable
radar, lightning, AWS/ARG, and NWP. Frame evidence shows the INSAT timestamp,
age, product, variables, source file, missing summary, and provenance while
clearly separating NOAA CPC CMORPH precipitation estimates from MOSDAC
INSAT-3DR satellite observations.

One optional map layer renders every finite calibrated TIR1 source-grid sample
without interpolation. Its exact label is:

`INSAT-3DR TIR1 Brightness Temperature (K) — native metadata 4 km`

The water-vapour brightness-temperature channel remains visible in evidence
and metadata but receives no second map layer. A missing or stale frame shows
INSAT as unavailable and emits no satellite raster. Scientific language keeps
the objects named Intense Precipitation Cells and makes no thunderstorm, hail,
downburst, cloudburst, or operational-forecast claim from brightness
temperature.

## Verification

Automated tests cover all twelve mappings, the previous-day boundary, future
rejection, maximum-age rejection, exact ages, missing and partial files,
provenance and product metadata, out-of-window exclusion, API state, dashboard
readiness, and CMORPH-only replay regression. Tests use local fixtures and no
internet access.

Final verification runs focused INSAT tests, the complete pytest suite, the
real built-in replay against local processed files, Streamlit and FastAPI
startup/health checks, a visual dashboard inspection, and assertions that zero
future observations and zero out-of-window verification files were selected.
Only source, tests, and required documentation are committed; HDF5, NetCDF,
local provenance, credentials, and generated verification artifacts remain
untracked or ignored.
