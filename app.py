from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import xarray as xr

from storm_nowcast.config import load_settings
from storm_nowcast.data.provenance import read_manifest
from storm_nowcast.data.sources import (
    CmorphSource,
    ImdLightningSource,
    ImdRadarSource,
    MosdacSatelliteSource,
)
from storm_nowcast.evaluation import evaluate_forecasts
from storm_nowcast.replay.player import ReplayPlayer
from storm_nowcast.visualization.layers import build_map


def event_status_message(path: Path) -> str:
    if Path(path).exists():
        return f"Prepared official CMORPH event ready: {path}"
    return (
        f"No prepared CMORPH event is available at {path}. "
        "Run `python scripts/prepare_demo.py` while connected to the internet, then reload."
    )


def observation_mode(path: Path) -> tuple[str, str]:
    """Describe the data mode without implying a live network connection."""
    if Path(path).exists():
        return "CACHED HISTORICAL EVENT", "cached"
    return "EVENT DATA MISSING", "missing"


@st.cache_resource(show_spinner=False)
def load_event(path: str) -> xr.Dataset:
    return xr.load_dataset(path, engine="h5netcdf")


def _css() -> None:
    font_path = Path(__file__).parent / "assets" / "fonts" / "SourceCodeVF-Upright.woff2"
    font_data = base64.b64encode(font_path.read_bytes()).decode("ascii") if font_path.exists() else ""
    st.markdown(
        """
        <style>
        @font-face { font-family:'Storm Console'; src:url(data:font/woff2;base64,__FONT_DATA__) format('woff2');
          font-weight:200 900; font-display:swap; }
        :root { --ink:#07111C; --panel:#0D1B29; --line:#294052; --text:#EAF6FF;
          --muted:#A7C0D2; --obs:#45C4E8; --derived:#F6B73C; --forecast:#F15BB5; }
        .stApp { background: var(--ink); color: var(--text); }
        .block-container { max-width: 1560px; padding: .65rem 1.6rem 3rem; }
        h1, h2, h3 { font-family:'Storm Console', 'Segoe UI', sans-serif !important; letter-spacing:-0.04em; color:var(--text); }
        h1 { font-size:1.75rem !important; margin:0 !important; line-height:1.35 !important; padding-top:.12rem; }
        [data-testid="stHeader"] { background:rgba(7,17,28,.94); }
        [data-testid="stMetric"] { background:transparent; border-top:1px solid var(--line); padding-top:.65rem; }
        [data-testid="stMetricValue"] { font-variant-numeric:tabular-nums; font-size:1.25rem; }
        [data-testid="stSidebar"] { background:#091522; border-right:1px solid var(--line); }
        .status-mast { display:flex; gap:1.2rem; align-items:center; justify-content:space-between;
          padding:.25rem 0 .5rem; border-bottom:1px solid var(--line); margin-bottom:.4rem; }
        .brand-lockup { display:flex; align-items:baseline; gap:.8rem; }
        .brand-lockup strong { font-size:1.75rem; letter-spacing:-.035em; }
        .brand-lockup span { color:var(--muted); font-size:.82rem; }
        .product-deck { color:var(--muted); font-size:.86rem; max-width:54ch; }
        .signal { display:flex; gap:.75rem; align-items:center; color:var(--muted); font-size:.78rem; }
        .signal b { color:#8CE6C0; font-weight:650; }
        .signal.missing b { color:#FF8A92; }
        .status-dot { width:8px; height:8px; border-radius:50%; background:#42D39B; display:inline-block; }
        .signal.missing .status-dot { background:#FF4D5A; }
        .class-strip { display:flex; gap:1.1rem; flex-wrap:wrap; font-size:.72rem; letter-spacing:.05em;
          text-transform:uppercase; margin:.05rem 0 .4rem; color:var(--muted); }
        .class-strip span::before { content:""; display:inline-block; width:18px; height:3px; margin-right:7px; vertical-align:middle; }
        .class-strip .observed::before { background:var(--obs); }
        .class-strip .derived::before { background:var(--derived); }
        .class-strip .forecast::before { background:var(--forecast); }
        .class-strip .target::before { background:#FFFFFF; }
        .cue { border:1px solid var(--line); background:#091724; padding:.72rem .9rem; margin:.15rem 0 .7rem;
          display:flex; justify-content:space-between; gap:1rem; font-variant-numeric:tabular-nums; }
        .cue strong { color:var(--obs); }
        .readout { border-top:1px solid var(--line); padding-top:.8rem; margin-top:.7rem; }
        .readout h3 { font-size:1.05rem; margin:0 0 .75rem; }
        .readout dl { display:grid; grid-template-columns:1fr auto; gap:.46rem 1rem; margin:0; }
        .readout dt { color:var(--muted); font-size:.8rem; }
        .readout dd { margin:0; font-variant-numeric:tabular-nums; font-weight:620; text-align:right; }
        .risk-high { color:#FFD166; }
        .limitation { color:var(--muted); font-size:.78rem; line-height:1.48; border-top:1px solid var(--line); padding-top:.75rem; }
        .stButton button, .stDownloadButton button { border-radius:6px; border:1px solid #36526A; }
        .st-key-replay_controls [data-testid="stHorizontalBlock"] { flex-wrap:nowrap; gap:.45rem; align-items:end; }
        .st-key-replay_controls [data-testid="column"] { min-width:0; }
        .stButton button:focus-visible, input:focus-visible { outline:3px solid rgba(69,196,232,.55) !important; outline-offset:2px; }
        ::selection { background:#45C4E8; color:#07111C; }
        * { scrollbar-color:#36526A #07111C; }
        @media (max-width:760px) {
          .block-container { padding:1.55rem .75rem 2rem; }
          .status-mast { gap:.25rem; padding:.1rem 0 .35rem; }
          .product-deck { font-size:.7rem; max-width:24ch; }
          .signal { gap:.35rem; font-size:.66rem; text-align:right; }
          .signal span:last-child { display:none; }
          .class-strip { font-size:.62rem; gap:.6rem; margin-bottom:.2rem; }
          .class-strip span::before { width:12px; margin-right:4px; }
          .st-key-replay_controls [data-testid="stHorizontalBlock"] {
            display:grid !important; grid-template-columns:60px 60px minmax(96px,1fr) 86px; gap:.25rem;
          }
          .st-key-replay_controls [data-testid="column"] { width:100% !important; flex:none !important; }
          .st-key-replay_controls .stButton button { min-height:2.5rem; padding:.25rem .45rem; }
          .st-key-replay_controls button p, .st-key-replay_controls label p { font-size:.68rem !important; white-space:nowrap; }
          .cue { flex-direction:column; gap:.25rem; }
        }
        </style>
        """.replace("__FONT_DATA__", font_data),
        unsafe_allow_html=True,
    )


def _source_sidebar() -> None:
    st.sidebar.header("Source readiness")
    for status in (
        CmorphSource().status(),
        MosdacSatelliteSource().status(),
        ImdRadarSource().status(),
        ImdLightningSource().status(),
    ):
        marker = "READY" if status.available else "INPUT REQUIRED"
        st.sidebar.markdown(f"**{status.source}**  \n`{marker}`  \n{status.message}")
    st.sidebar.divider()
    st.sidebar.caption(
        "CMORPH is a satellite precipitation estimate—not radar. Grid spacing is approximately "
        "8 km; effective source resolution is coarser."
    )


def _track_readout(track, eta) -> None:
    direction = "Unavailable" if track.bearing_deg is None else f"{track.bearing_deg:.0f}°"
    trend = "Increasing" if track.intensity_trend_mm_hr_per_hour > 1 else (
        "Weakening" if track.intensity_trend_mm_hr_per_hour < -1 else "Steady"
    )
    risk = track.risk
    st.markdown(
        f"""
        <div class="readout">
          <h3>Derived {track.id} · Intense Precipitation Cell</h3>
          <dl>
            <dt>Maximum rain rate</dt><dd>{track.current.max_intensity:.1f} mm h⁻¹</dd>
            <dt>Footprint area</dt><dd>{track.current.area_km2:.0f} km²</dd>
            <dt>Motion</dt><dd>{track.speed_kmh:.1f} km h⁻¹</dd>
            <dt>Bearing</dt><dd>{direction}</dd>
            <dt>Intensity trend</dt><dd>{trend}</dd>
            <dt>Tracked observation states</dt><dd>{len(track.history)}</dd>
          </dl>
        </div>
        <div class="readout">
          <h3>Prototype Extreme Rain Risk · heuristic</h3>
          <dl><dt>Risk level</dt><dd class="risk-high">{risk.level}</dd>
          <dt>Transparent score</dt><dd>{risk.score:.1f} / 100</dd></dl>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(int(risk.score), text=" · ".join(risk.contributors))
    forecast_rows = [
        {
            "Lead": f"+{point.lead_minutes} min",
            "Valid UTC": point.valid_at.strftime("%H:%M"),
            "Heuristic radius": f"{point.uncertainty_km:.0f} km",
            "Heuristic confidence": point.confidence,
        }
        for point in track.forecasts
    ]
    st.dataframe(pd.DataFrame(forecast_rows), hide_index=True, width="stretch")
    st.caption(
        "Radii and confidence labels are uncalibrated prototype heuristics, not statistical intervals or operational guidance."
    )
    arrival = eta.estimated_arrival.strftime("%Y-%m-%d %H:%M UTC") if eta.estimated_arrival else "Not issued"
    st.markdown(
        f"""
        <div class="readout">
          <h3>Target closest approach / qualified ETA</h3>
          <dl><dt>Approaches corridor</dt><dd>{'YES' if eta.approaches_target else 'NO'}</dd>
          <dt>Closest distance</dt><dd>{eta.closest_distance_km:.1f} km</dd>
          <dt>Forecast lead</dt><dd>+{eta.closest_lead_minutes} min</dd>
          <dt>Estimated arrival</dt><dd>{arrival}</dd></dl>
          <p class="limitation">{eta.explanation}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="StormNowcast", page_icon="SN", layout="wide")
    _css()
    settings = load_settings()
    _source_sidebar()
    st.title("StormNowcast")
    mode_label, mode_class = observation_mode(settings.data.processed_event)
    st.markdown(
        f"""
        <div class="status-mast">
          <div class="product-deck">Regional precipitation movement prototype · historical observation replay</div>
          <div class="signal {mode_class}"><span class="status-dot"></span><b>{mode_label}</b><span>NOAA CPC · CMORPH</span></div>
        </div>
        <div class="class-strip"><span class="observed">Observed grid</span><span class="derived">Derived analytics</span><span class="forecast">Deterministic forecast</span><span class="target">Target</span></div>
        """,
        unsafe_allow_html=True,
    )

    if not settings.data.processed_event.exists():
        st.error(event_status_message(settings.data.processed_event), icon=None)
        st.code(".\\.venv\\Scripts\\python.exe scripts\\prepare_demo.py", language="powershell")
        return

    dataset = load_event(str(settings.data.processed_event))
    player = ReplayPlayer(dataset, settings)
    default_frame = max(0, player.frame_count - 3)
    if "frame_index" not in st.session_state:
        st.session_state.frame_index = default_frame

    with st.container(key="replay_controls"):
        control_a, control_b, control_c, control_d = st.columns([1, 1, 5, 1.2])
        if control_a.button("Prev", help="Previous frame", width="stretch", disabled=st.session_state.frame_index == 0):
            st.session_state.frame_index -= 1
            st.rerun()
        if control_b.button("Next", help="Next frame", width="stretch", disabled=st.session_state.frame_index >= player.frame_count - 1):
            st.session_state.frame_index += 1
            st.rerun()
        selected_frame = control_c.slider(
            "Historical replay frame",
            min_value=0,
            max_value=player.frame_count - 1,
            value=st.session_state.frame_index,
            format="Frame %d",
        )
        st.session_state.frame_index = selected_frame
        playing = control_d.toggle("Play replay", value=False)

    if "target_lat" not in st.session_state:
        st.session_state.target_lat = float(settings.target.latitude)
    if "target_lon" not in st.session_state:
        st.session_state.target_lon = float(settings.target.longitude)
    target_lat = float(st.session_state.target_lat)
    target_lon = float(st.session_state.target_lon)
    target = (target_lat, target_lon)
    snapshot = player.analyze(st.session_state.frame_index, target)
    st.markdown(
        f"""
        <div class="cue"><span><strong>ANALYSIS CUT {snapshot.frame_index + 1:02d}/{player.frame_count:02d}</strong> · {snapshot.timestamp:%Y-%m-%d %H:%M UTC}</span>
        <span>Only observations through this timestamp are used</span></div>
        """,
        unsafe_allow_html=True,
    )

    map_column, rail_column = st.columns([2.15, 1], gap="large")
    with map_column:
        st.plotly_chart(build_map(snapshot, target), width="stretch", config={"displaylogo": False})
        st.caption(
            "OBSERVED rainfall · DERIVED cell footprints/history · FORECAST extrapolation and increasing uncertainty. "
            "Basemap tiles may be unavailable offline; weather overlays and analytics remain functional."
        )
    with rail_column:
        with st.expander(f"Edit target · {target_lat:.2f}°, {target_lon:.2f}°"):
            st.number_input(
                "Target latitude", min_value=-90.0, max_value=90.0, step=0.01, key="target_lat"
            )
            st.number_input(
                "Target longitude", min_value=-180.0, max_value=180.0, step=0.01, key="target_lon"
            )
        if snapshot.tracks:
            track_ids = [track.id for track in snapshot.tracks]
            selected_id = st.selectbox("Inspect Intense Precipitation Cell", track_ids)
            track = next(item for item in snapshot.tracks if item.id == selected_id)
            _track_readout(track, snapshot.eta_by_track[track.id])
        else:
            st.info("No Intense Precipitation Cell meets the configured threshold in this frame.", icon=None)

    st.subheader("Forecast vs later observation")
    metrics = evaluate_forecasts(snapshot.tracks, player.all_tracks())
    evaluation_rows = []
    for metric in metrics:
        evaluation_rows.append(
            {
                "Lead": f"+{metric.lead_minutes} min" if metric.lead_minutes else "Unavailable",
                "Position error": f"{metric.position_error_km:.2f} km" if metric.position_error_km is not None else metric.message,
                "Footprint IoU": f"{metric.iou:.3f}" if metric.iou is not None else "—",
                "Track continuity": f"{metric.track_continuity:.0%}" if metric.track_continuity is not None else "—",
                "Samples": metric.sample_count,
            }
        )
    st.dataframe(pd.DataFrame(evaluation_rows), hide_index=True, width="stretch")
    st.caption("Metrics are calculated only where a later real observation exists; no accuracy values are fabricated.")

    info_left, info_right = st.columns([1.35, 1])
    with info_left:
        st.subheader("Observation provenance")
        if settings.data.provenance_manifest.exists():
            records = read_manifest(settings.data.provenance_manifest)
            st.write(
                f"{len(records)} official NOAA CPC hourly files · acquired with SHA-256 checksums · "
                f"{dataset.attrs.get('observation_start')} to {dataset.attrs.get('observation_end')}"
            )
            with st.expander("Inspect source records"):
                st.json(json.loads(settings.data.provenance_manifest.read_text(encoding="utf-8")))
        else:
            st.warning("Provenance manifest is missing. Re-run the preparation command.", icon=None)
    with info_right:
        st.subheader("Scientific limitations")
        st.markdown(
            "- CMORPH is a satellite precipitation estimate, not weather radar.\n"
            "- The approximately 8 km grid spacing does not imply 1–3 km source observations; effective resolution is coarser.\n"
            "- Intense Precipitation Cells are rainfall-derived objects, not confirmed thunderstorms.\n"
            "- Prototype Extreme Rain Risk is an unvalidated heuristic, not cloudburst detection.\n"
            "- Movement forecasts are deterministic extrapolations, not operational IMD forecasts."
        )

    if playing and st.session_state.frame_index < player.frame_count - 1:
        time.sleep(0.8)
        st.session_state.frame_index += 1
        st.rerun()


if __name__ == "__main__":
    main()
