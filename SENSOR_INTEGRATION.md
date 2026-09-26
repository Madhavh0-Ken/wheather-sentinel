# Sensor integration

## Integration rule

Only observations from authoritative providers may enter production analysis. Every
asset requires provider/product identity, official URL, observation and acquisition
times, native spatial/temporal resolution, checksum, processing history, access
requirements, and observed/derived status. Missing sensors remain missing; they are
never silently imputed.

## Current source matrix

| Sensor | Provider/product | Reader | Real event connected | Blocker |
|---|---|---|---|---|
| Rainfall | NOAA CPC CMORPH V0.x RAW 8km-30min | Product-specific binary parser | Yes | None for cached replay |
| Satellite | ISRO/SAC MOSDAC `3RIMG_L1C_ASIA_MER` | Product-specific documented-schema HDF reader | No | Registered MOSDAC download required |
| Radar | IMD DWR | Explicit generic CF HDF/NetCDF adapter | No | Authorized product file and exact format required |
| Lightning | IMD | Explicit point CSV adapter | No | Authorized event file and column documentation required |
| Surface | IMD AWS/ARG | Explicit point CSV adapter | No | Authorized station file and units required |
| NWP | Authoritative provider selected per file | Explicit generic CF adapter | No | Provider/product/file mapping required |

## INSAT-3DR contract

The priority satellite product is MOSDAC `3RIMG_L1C_ASIA_MER`, DOI
`10.19038/SAC/10/3RIMG_L1C_ASIA_MER`. The reader validates INSAT-3DR Imager L1C
metadata, uses file-supplied Mercator projection parameters, and decodes:

- `IMG_TIR1` counts through `IMG_TIR1_TEMP` to observed infrared brightness
  temperature in kelvin, with native resolution taken from the channel metadata.
- Optional `IMG_WV` counts through `IMG_WV_TEMP` to observed water-vapour-channel
  brightness temperature in kelvin. This is not labelled as humidity.

Fill values remain missing, checksum provenance is retained, and derived cloud-top
cooling is calculated only from consecutive kelvin brightness-temperature fields.
The reader is tested against the official published schema but is not called
real-file verified until an authorized MOSDAC file is processed.

Exact acquisition instructions are in
`data/manual/mosdac_satellite/README.md` and official references are in
`DATA_SOURCES.md`.

## Fusion and storm evidence

Gridded sources enter the common `time,y,x` weather cube only through an explicit
alignment policy. Each variable retains native resolution, analysis-grid resolution,
resampling method, source IDs, and a paired missing mask. Point lightning and station
observations remain point tables until an explicit aggregation is requested.

Each multi-sensor storm twin carries a sensor availability mask. Convective initiation,
hazards, confidence, and nowcasts may use only evidence marked available at the
analysis time. The current real replay therefore remains rainfall-only and correctly
gates satellite/radar/lightning-dependent outputs as unavailable.
