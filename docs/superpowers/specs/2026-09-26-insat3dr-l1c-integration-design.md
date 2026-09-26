# INSAT-3DR L1C integration design

## Intent

Replace the generic-only MOSDAC path with a product-specific reader for the official
`3RIMG_L1C_ASIA_MER` product while preserving the CMORPH replay as the default and
fallback. The reader must be useful as soon as an authorized file is supplied, but the
project must continue to label the integration unverified until that happens.

## Official contract

The selected source is the MOSDAC INSAT-3DR Imager six-channel Level-1C Asian-sector
Mercator product, DOI `10.19038/SAC/10/3RIMG_L1C_ASIA_MER`. MOSDAC documents it as a
half-hourly HDF product for registered researchers. Files follow the documented
`SSNNN_DDMMMYYYY_HHmm_LOP_XXX.h5` convention, with current archives also carrying a
version suffix.

The reader accepts only an HDF file whose root metadata identifies the Imager and L1C
processing. It reads `IMG_TIR1` digital counts and the `IMG_TIR1_TEMP` calibration
lookup table, masks the channel fill value before lookup, and outputs
`infrared_brightness_temperature` in kelvin. `IMG_WV` plus `IMG_WV_TEMP` is optional
and, when present, becomes `water_vapour_brightness_temperature`; it is not described
as humidity. Observation time comes from official acquisition metadata. Coordinates
come from the file's `X`, `Y`, and `Projection_Information` CF projection attributes,
transformed to WGS84 with `pyproj` before cropping.

Native channel resolution is taken from each channel's official HDF attribute and
retained in lineage. The TIR1 and WV variables remain separate products when their
native grids differ; no implicit resampling or invented fine detail is allowed.

## Failure behavior

Unknown satellites, sensors, processing levels, projections, missing calibration
tables, out-of-range counts, malformed times, or non-intersecting bounds fail with a
specific `ValueError`. Production files still require explicit confirmation of
official origin. Generic CF import remains available for other documented products.

## Integration and verification

`scripts/ingest_official.py` gets a dedicated `mosdac-insat3dr-l1c` source mode that
needs no guessed variable mapping or user-entered resolution. Tests create synthetic
HDF fixtures matching the published schema and prove calibration, time parsing,
geolocation, cropping, provenance, missing-data handling, and validation. These tests
validate the documented format contract, not a real observation. Documentation gives
the exact MOSDAC product, official URLs, login action, date/time range, destination,
and ingestion command for the existing 2023-07-09 event.
