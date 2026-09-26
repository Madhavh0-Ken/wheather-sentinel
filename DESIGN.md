---
name: StormNowcast
description: A broadcast meteorology analysis desk for transparent historical precipitation replay.
colors:
  ink: "#07111C"
  panel: "#0D1B29"
  sidebar: "#091522"
  cue: "#091724"
  line: "#294052"
  control-border: "#36526A"
  text: "#EAF6FF"
  muted: "#A7C0D2"
  observed: "#45C4E8"
  derived: "#F6B73C"
  forecast: "#F15BB5"
  target: "#FFFFFF"
  ready: "#8CE6C0"
  ready-dot: "#42D39B"
  missing: "#FF8A92"
  rain-extreme: "#FF4D5A"
  risk: "#FFD166"
  uncertainty-line: "#FFD4EE"
  rain-low: "#102536"
  rain-mid-low: "#17415A"
  rain-mid: "#22B8CF"
typography:
  display:
    fontFamily: "'Storm Console', 'Segoe UI', sans-serif"
    fontSize: "1.75rem"
    lineHeight: 1.35
    letterSpacing: "-0.04em"
  title:
    fontFamily: "'Storm Console', 'Segoe UI', sans-serif"
    fontSize: "1.05rem"
    letterSpacing: "-0.04em"
  body:
    fontFamily: "sans-serif"
  plot:
    fontFamily: "'Segoe UI', sans-serif"
  label:
    fontSize: "0.72rem"
    letterSpacing: "0.05em"
  readout-label:
    fontSize: "0.8rem"
  readout-value:
    fontWeight: 620
  limitation:
    fontSize: "0.78rem"
    lineHeight: 1.48
rounded:
  control: "6px"
  signal: "50%"
spacing:
  compact: "0.25rem"
  control-gap: "0.45rem"
  half: "0.5rem"
  inset: "0.75rem"
  normal: "1rem"
  desktop-gutter: "1.6rem"
components:
  button:
    rounded: "{rounded.control}"
  field:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
  analysis-cue:
    backgroundColor: "{colors.cue}"
    textColor: "{colors.text}"
    padding: "0.72rem 0.9rem"
  status-ready:
    textColor: "{colors.ready}"
  status-missing:
    textColor: "{colors.missing}"
  readout:
    textColor: "{colors.text}"
  classification-label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
---

# Design System: StormNowcast

## Overview

**Creative North Star: "The Broadcast Meteorology Analysis Desk"**

A dark, precise instrument surface makes the weather field the central evidence. Compact labels, stable cell identities, measurement numerals, and a restrained source-status ribbon convey a calm operations desk. The established direction is dense and legible, with the map carrying the visual interest.

Scientific status is part of the visual language. An observation, a derived cell, a forecast, and a chosen target remain distinguishable by wording, geometry, and color. Cached historical data is explicitly labeled; a green readiness signal does not imply a live feed.

**Key Characteristics:**

- Deep ink ground with flat, hairline-separated readouts.
- Console headings paired with quiet sans-serif operational text.
- Cyan, amber, magenta, and white identify distinct information classes.
- Source-grid weather texture and synchronized replay supply the signature.
- Explicit units, UTC timestamps, provenance, and qualified uncertainty remain visible.

This records the built system in `app.py`, `.streamlit/config.toml`, and `src/storm_nowcast/visualization/layers.py`. The surface composition and task priorities remain in `.impeccable/surfaces/app-py.md`.

## Colors

The palette combines cool instrument neutrals with sharply separated data-class accents. Frontmatter values are normative; names below explain their use.

### Primary

**Observed Cyan** identifies observed-data labels, the current analysis cue, the replay slider, selection, and the application's primary interactive accent. It does not replace the calibrated rainfall scale.

### Secondary

**Derived Amber** identifies rainfall-derived cell boundaries, centroids, and tracked histories. **Forecast Magenta** identifies deterministic extrapolated tracks and translucent forecast envelopes. **Target White** marks the selected geographic target with a cross.

### Neutral

**Deep Ink** is the app and plot ground. **Instrument Panel** backs native fields; **Sidebar Ink** distinguishes source readiness; **Cue Ink** backs the timestamp band. **Cool White** is primary text, **Muted Steel** is supporting text, **Hairline Steel** divides regions, and **Control Steel** outlines buttons.

### Status and data scales

**Ready Mint** and its green dot accompany the explicit cached-event status. **Missing Rose** and its red dot accompany missing-event text. **Risk Amber** emphasizes the named risk level without implying validation.

Rain rate has a separate five-stop scale: Rain Low, Rain Mid Low, Rain Mid, Derived Amber, and Rain Extreme at normalized positions 0, 0.2, 0.45, 0.72, and 1. The lower bound is zero; the upper bound is the greater of 50 mm h⁻¹ and the current frame maximum. The visible colorbar supplies units and scale. Do not assume equal colors encode equal rates across frames whose maxima exceed 50.

**The Epistemic Color Rule.** Pair every information-class color with OBSERVED, DERIVED, FORECAST, or TARGET wording and distinguishable geometry; never rely on hue alone.

**The Scale Context Rule.** Amber in a calibrated rain raster is an intensity value; amber cell outlines are derived objects. Preserve the colorbar, class strip, and hover labels that disambiguate them.

## Typography

The heading face is **Storm Console**, a local CSS alias for the embedded **Source Code variable upright** WOFF2 asset at `assets/fonts/SourceCodeVF-Upright.woff2`. Its declared weight range is 200–900 and it uses swap loading. It is embedded as a data URL so headings require no external font request. Segoe UI and sans-serif provide heading fallbacks.

Body text and native controls retain Streamlit's sans-serif theme. Plotly explicitly uses Segoe UI, sans-serif. Do not describe the entire app as monospaced: the console face belongs to headings and the sans-serif body keeps long explanations readable.

The display role is the product title; the title role is the compact inspector section heading. Classification labels are uppercase and lightly tracked. Readout labels are smaller and muted; values carry stronger weight and align right. Analysis timestamps, readout values, and metrics use tabular numerals. Sizes not explicitly owned by the app remain native Streamlit values.

**The Measurement Rule.** Keep values, units, UTC times, and persistent cell IDs legible together; use tabular numerals in changing numerical readouts.

## Layout

The wide app container caps at 1560px. Desktop padding is 0.65rem top, 1.6rem horizontal, and 3rem bottom. The title and status masthead precede a wrapping class strip, a replay row, and the full-width analysis cue.

The main desktop workspace uses a 2.15:1 map-to-inspector column ratio with Streamlit's large gutter. The map is 610px high, with a 42px top plot margin. Inspector sections stack as one continuous situation report rather than separate floating cards. Evaluation follows the workspace; provenance and scientific limitations form a 1.35:1 secondary row. Source readiness belongs to the native collapsible sidebar.

At the app's explicit 760px breakpoint, page padding becomes 1.55rem top, 0.75rem horizontal, and 2rem bottom. The masthead compresses, its duplicated source suffix hides, class labels and swatches become smaller, and the timestamp cue stacks. Replay uses four columns of 60px, 60px, minmax(96px, 1fr), and 86px with a 0.25rem gap. Buttons have a 2.5rem minimum height and compact non-wrapping labels. Native Streamlit columns stack the inspector below the map and the lower information sections vertically; wide data tables remain scrollable. Do not infer a second custom breakpoint from native behavior.

Desktop and mobile review captures establish the overall composition. Current source is authoritative for replay sizing and labels updated after those captures.

## Elevation & Depth

The custom UI has no decorative shadows. Depth comes from closely related dark surfaces, bright data marks, and single-pixel dividers. The map's real grid and translucent analytic overlays supply layered information, not simulated material.

Derived footprints use a low-opacity amber fill. Forecast envelopes use a low-opacity magenta fill with a pale rose perimeter. Overlap should remain visible without hiding the observation field. Native Streamlit popovers retain framework behavior; the app does not define an independent shadow scale.

## Shapes

The recurring form is a rectangle with restrained corners: hard-edged analysis bands and readout divisions, gently rounded native controls, and fine borders. Buttons use the control radius. Small circular dots are reserved for readiness; forecast circles represent geographic uncertainty and are not decorative badges.

Rainfall polygons follow coordinate-derived grid-cell edges. Their crisp rectangular texture is essential evidence of the approximately 8 km source spacing; the effective observing resolution remains coarser.

## Components

### Source masthead and classification strip

The compact masthead joins a product descriptor to explicit cached/missing status. A dot supplements the text. The classification strip uses short horizontal swatches plus labels; it wraps on narrow screens. These are informational labels, not clickable chips or navigation.

### Replay controls and analysis cue

Prev and Next bracket a labeled frame slider and Play replay toggle. Boundary buttons disable at the first and last observations. Playback advances with an approximately 0.8-second pause per rerun, stopping advancement at the last frame; rendering time is additional. There are no decorative transitions.

Every frame update supplies one synchronized analysis cut: timestamp, observed grid, derived state/history, forecast geometry, target assessment, and retrospective evaluation. The cue states that analysis uses only observations through its timestamp. Keyboard focus on buttons and inputs is a 3px translucent cyan outline offset by 2px.

### Map and calibrated legend

Rainfall is a grid-native choropleth: one polygon per positive finite source cell, no smoothing or interpolation, 0.82 fill opacity, and no polygon stroke. Its hover identifies an OBSERVED source grid cell and rate. Do not replace it with a blended density heatmap.

Derived history uses amber lines and small markers; the footprint uses a thinner amber border and transparent fill; a larger centroid marker carries the persistent IPC identifier. Forecast paths use magenta lines and markers with issued/lead-time hovers. Increasing uncertainty is drawn as geodesic circles with pale perimeters and transparent fill, explicitly described as heuristic. The white target is a cross.

The plot preserves map interaction state across replay through a stable UI revision. The global class strip replaces an overcrowded per-track legend, while the map retains a vertical rainfall colorbar at bottom left. Basemap attribution remains visible. Online basemap tiles may fail offline; cached observations and analysis overlays remain usable.

### Inspector and target controls

A collapsed target editor exposes labeled latitude and longitude number inputs. Cell selection uses a native selectbox with stable IDs. Flat definition-list readouts align labels left and values right, separated by horizontal rules. The risk progress bar is accompanied by a named level, numeric score, and contributors; it is not a validated probability.

A compact table lists +30, +60, and +120-minute leads, UTC validity, heuristic radius, and heuristic confidence. Target proximity includes its explanation and qualified ETA; unavailable arrivals say Not issued. No-cell frames use a clear informational state.

### Evaluation, provenance, and limitations

Retrospective verification uses a table with real sample counts and explicit insufficient-observation messages. Provenance expands to source records; scientific limitations remain readable in ordinary body text. These are supporting evidence, not promotional metrics.

### Buttons and fields

Buttons have a thin Control Steel border and the shared small radius. Fields use the panel ground and bright text. Hover, pressed, disabled, selection, expander, slider, and toggle behavior otherwise belongs to native Streamlit; do not fabricate a custom motion or variant system. Preserve native keyboard interaction and labels when adding controls.

## Do's and Don'ts

### Do:

- Do preserve observed, derived, forecast, and target wording alongside color and geometry.
- Do render rainfall at its real grid-cell edges and keep units and the colorbar visible.
- Do use console headings, quiet sans-serif body copy, and tabular measurement readouts.
- Do preserve map emphasis, flat inspector sections, and a stacked mobile reading order.
- Do keep cached status, UTC validity, provenance, and uncertainty qualifications explicit.

### Don'ts:

- Don't smooth the source grid into an apparent higher-resolution weather field.
- Don't turn heuristic risk or forecast envelopes into validated warning or probability claims.
- Don't use readiness green to imply a live network feed.
- Don't add an equal-card metric grid, decorative elevation, or gimmicky animation to this operations surface.
- Don't hide insufficient observations or replace missing metrics with invented values.

