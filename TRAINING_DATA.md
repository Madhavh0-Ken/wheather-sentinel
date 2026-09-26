# Training data

## Current corpus

StormNowcast currently has one production event eligible for dataset generation:

| Event | Region | Period (UTC) | Source | Frames | Synthetic |
|---|---|---|---|---:|---|
| `cmorph-india-20230709T0000Z` | Himachal Pradesh and nearby north-west India | 2023-07-09 00:00-05:30 | NOAA CPC CMORPH V0.x RAW 8km-30min | 12 | No |

This is a demonstration event, not an adequate learned-model corpus.

## Sample definition

Each horizon dataset uses exact observations at T-120, T-90, T-60, T-30, and T as
inputs. Its target is the same observed variable at one of T+30, T+60, T+120, T+180,
or T+360 minutes. A sample exists only when every timestamp is present in the same
event. The builder does not interpolate missing times, borrow frames from another
event, or fill missing pixels.

The current `rain_rate` artifacts contain:

| Target horizon | Samples | Statistical use |
|---|---:|---|
| +30 min | 7 | Demonstration only |
| +60 min | 6 | Demonstration only |
| +120 min | 4 | Statistically weak; demonstration only |
| +180 min | 2 | Statistically weak; demonstration only |
| +360 min | 0 | Unavailable |

These counts are training-pair availability counts, not accuracy measurements.

## Leakage prevention

- History times must be at or before T; targets must be after T.
- History and target frames must belong to the same event.
- Events are sorted by observation start and assigned whole to one split.
- At least three independent events are required for train, validation, and test.
- Events whose time windows overlap across a split boundary are rejected.
- Normalization is fitted from training inputs only; future targets and validation/test
  inputs never contribute statistics.
- Synthetic datasets require an explicit test-only opt-in and cannot enter the
  production builder.

## Current split and model status

**TRAIN:** UNAVAILABLE

**VALIDATION:** UNAVAILABLE

**TEST:** UNAVAILABLE

Reason: one event cannot produce three independent event-separated partitions.

**2-6 hour learned nowcast unavailable: additional synchronized historical events
required.** No model has been trained and no learned-model accuracy is reported.

## Build command and outputs

```powershell
.\.venv\Scripts\python.exe scripts\build_training_dataset.py
```

Generated, git-ignored artifacts are written to `data/processed/training/`:

- `rain_rate_lead_030.nc`
- `rain_rate_lead_060.nc`
- `rain_rate_lead_120.nc`
- `rain_rate_lead_180.nc`
- `training_manifest.json`

No +360 file is written because there are zero valid samples. The manifest records
events, sample counts, source paths, split status, leakage policy, normalization
status, and learned-model status.
