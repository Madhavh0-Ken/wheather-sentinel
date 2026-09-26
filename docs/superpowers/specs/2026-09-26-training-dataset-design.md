# Event-separated nowcast training dataset design

## Intent

Build the data pipeline required before any learned 0-6 hour model. The pipeline uses
only genuine event observations in production, creates causal history/target pairs,
and makes event leakage structurally difficult. It does not train a model and does
not turn the single cached demonstration event into a validation claim.

## Sample contract

For each event and forecast horizon, a sample contains the exact observation fields
at T-120, T-90, T-60, T-30, and T plus the target field at T+lead. Supported lead
times are +30, +60, +120, +180, and +360 minutes. A sample is emitted only when every
requested timestamp exists exactly in the same event; no interpolation, padding, or
cross-event borrowing occurs. Missing grid values remain NaN.

Horizon datasets retain event ID, analysis time, all history times, target time,
spatial coordinates, source variable, and sample count. They can be converted to
xarray and written to NetCDF without changing values.

## Leakage prevention

Events are ordered by observation start and assigned whole to train, validation, or
test. At least three events are required. Any temporal overlap between events assigned
to different splits is rejected. Normalization statistics are fitted only from input
histories belonging to train events; targets and validation/test events are excluded.

## Current real-data behavior

The cached 2023-07-09 CMORPH event can generate per-horizon demonstration samples,
but one event cannot produce independent train, validation, and test partitions. The
manifest therefore reports split and learned-model status as `UNAVAILABLE`, with the
exact sample count for each horizon. No accuracy or probability is produced.

## Verification

Synthetic tests prove exact causal indexing, horizon counts, event isolation,
chronological splitting, overlap rejection, train-only normalization, and serializable
xarray output. A smoke test builds the manifest from the cached official event.
