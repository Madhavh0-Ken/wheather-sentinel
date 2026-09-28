# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Confirmed by the project brief: Python 3.11+ with Streamlit, Plotly, xarray, SciPy/scikit-image, Shapely, and PyProj. The application runs locally and remains demonstrable offline after official observations are cached.

## Users

Primary users are SIH judges and technical evaluators watching a five-minute demonstration. The operational interaction model is also suitable for a weather analyst reviewing a compact historical event, inspecting precipitation-cell state, and testing proximity to a target location.

## Product Purpose

StormNowcast demonstrates an end-to-end, scientifically honest severe-rain nowcasting workflow: acquire an official observation, derive Intense Precipitation Cells, maintain histories, extrapolate short-term movement, expose uncertainty and risk factors, and compare forecasts with later observations.

## Positioning

The product makes provenance and epistemic status part of the interface. Observations, derived analytics, deterministic forecasts, uncertainty, and unavailable inputs remain visibly distinct instead of being collapsed into an “AI weather prediction” claim.

## Operating Context

The principal workflow is historical replay over a configurable Indian study area. A user chooses a 30-minute frame, inspects the map and a tracked cell, places a target location, reads qualified closest-approach/ETA information, and then compares the issued forecast with later real observations.

## Capabilities and Constraints

- NOAA CPC CMORPH is the primary no-login authoritative source.
- CMORPH is precipitation data on an approximately 8 km grid; effective source resolution is coarser.
- Rainfall-derived objects are named “Intense Precipitation Cells,” never confirmed thunderstorms.
- The heuristic output is named “Prototype Extreme Rain Risk,” never cloudburst detection.
- Forecast leads are +30, +60, and +120 minutes and use deterministic motion extrapolation with increasing uncertainty.
- Authorized local MOSDAC INSAT-3DR observations can attach as optional causal evidence; IMD radar/lightning remain future-compatible adapters, and none of these paths can block CMORPH-only replay.
- Synthetic observations are restricted to tests and must be visibly and programmatically marked.

## Brand Commitments

The product name is StormNowcast. Voice is operational, direct, calm, and explicit about uncertainty and limitations. The user requested a polished weather-monitoring prototype with a map occupying most of the page, clean typography, clear status, replay controls, a forecast timeline, and no gimmicky animation.

## Evidence on Hand

- A cached official NOAA CPC CMORPH event over Himachal Pradesh and nearby north-west India, 2023-07-09 00:00–05:30 UTC, with 12 half-hour frames and optional preceding-quarter-hour MOSDAC INSAT-3DR evidence.
- Per-file official URLs, acquisition times, processing steps, and SHA-256 checksums in the provenance manifest.
- Real derived cell tracks and calculated +30/+60 forecast verification metrics.
- No operational validation study, confirmed thunderstorm labels, cloudburst labels, customer claims, or fabricated accuracy metrics exist and none may be invented.

## Product Principles

- Show provenance before persuasion.
- Separate observed, derived, and forecast information at a glance.
- Make uncertainty and insufficiency explicit.
- Prefer a complete deterministic baseline over unvalidated machine learning.
- Keep the demonstration usable after the network is disconnected.

## Accessibility & Inclusion

Do not communicate status by color alone. Controls require visible labels and keyboard focus; data colors must retain readable contrast on the dark operations surface.
