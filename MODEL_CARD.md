# Model and heuristic card

StormNowcast currently combines deterministic geometry and transparent heuristics;
it does not ship a trained neural weather model.

## Intense Precipitation Cells

Connected components above the configured 10 mm h⁻¹ threshold, with at least two
source-grid pixels, form rainfall-derived objects. Assignment uses spatial distance
and overlap to preserve IDs across observations. Outputs include footprint, centroid,
area, maximum rain rate, velocity, bearing, trend, and history. These objects are not
confirmed thunderstorms.

## Movement forecasts

The dashboard baseline extrapolates recent tracked motion to +30, +60, and +120
minutes. Its uncertainty radius grows from a 12 km base at 18 km per forecast hour.
The label is a deterministic movement forecast, not an operational IMD forecast.

An additional raster nowcaster estimates whole-field translation by phase
correlation and advects the latest field at +10, +20, +30, +60, +90, and +120
minutes. Growth is bounded to 0.5–1.5 of the recent interval trend. Insufficient
finite coverage triggers the deterministic track fallback. This component is tested
but not enabled for the default real-event dashboard and has not been validated on a
multi-event real corpus.

## Prototype Extreme Rain Risk

This is a transparent 0–100 heuristic derived from current rain intensity, footprint,
persistence, and trend. It produces named levels and contributors. The numeric value
is not a probability, has not been calibrated, and must not be described as
cloudburst detection or operational warning guidance.

## Convective initiation and lightning

The Convective Initiation Score is emitted only when defensible precursor features
such as satellite cooling/expansion, radar growth, lightning initiation/trend, or
moisture context are present. CMORPH-only input returns insufficient data. Lightning
jump analytics distinguish observed counts from a documented derived trend. Neither
is a calibrated probability.

## Hail, downburst, and 2–6 hour output

Hail and downburst assessments return `INSUFFICIENT_DATA`; no zero score is invented.
The 2–6 hour interface returns `TRAINING_DATA_REQUIRED`. Authoritative labels,
environmental predictors, multiple independent events, and held-out event-grouped
validation are prerequisites for any future learned model.

## Intended use and exclusions

Intended uses are local demonstration, software integration, retrospective event
inspection, and research prototyping. Do not use the output for public warnings,
emergency response, aviation, flood control, or claims of forecast skill beyond the
reported event/sample counts.

