from __future__ import annotations

import base64
import json
import time
from datetime import datetime, time as clock_time, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
import xarray as xr

from storm_nowcast.config import Bounds, load_settings
from storm_nowcast.alerts.engine import AlertEngine, AlertRule
from storm_nowcast.confidence.framework import estimate_forecast_confidence
from storm_nowcast.data.provenance import read_manifest
from storm_nowcast.data.cmorph_cache import CmorphCache
from storm_nowcast.data.sources import (
    CmorphSource,
    ImdLightningSource,
    ImdRadarSource,
    MosdacSatelliteSource,
)
from storm_nowcast.evaluation import evaluate_forecasts
from storm_nowcast.events.builder import BuildStage, CmorphEventBuilder
from storm_nowcast.events.custom import (
    CustomEventRequest,
    EventLibraryRecord,
    SizeUnit,
    bounds_from_center,
    required_cmorph_hours,
)
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.events.repository import EventRepository
from storm_nowcast.hazards.registry import assess_hazards
from storm_nowcast.initiation.scoring import score_convective_initiation
from storm_nowcast.replay.player import ReplayPlayer
from storm_nowcast.tracking.twin import build_multisensor_twin
from storm_nowcast.visualization.layers import build_map
from storm_nowcast.visualization.region import build_region_preview
from storm_nowcast.visualization.panels import (
    hazard_rows,
    resolve_operating_mode,
    sensor_availability_rows,
)


PROJECT_ROOT = Path(__file__).resolve().parent
CUSTOM_EVENT_ROOT = PROJECT_ROOT / "data" / "events" / "custom"


def event_option_label(record: EventLibraryRecord) -> str:
    prefix = "Built-in" if record.kind == "builtin" else "Custom"
    return f"{prefix} | {record.display_name}"


def request_summary(request: CustomEventRequest) -> dict[str, object]:
    elapsed = request.end_time - request.start_time
    minutes = int(elapsed.total_seconds() // 60)
    return {
        "observations": request.expected_frame_count,
        "source_hours": len(required_cmorph_hours(request)),
        "span": f"{minutes // 60}h {minutes % 60:02d}m inclusive",
        "bounds": (
            f"{request.min_lat:.2f} to {request.max_lat:.2f} deg N/S | "
            f"{request.min_lon:.2f} to {request.max_lon:.2f} deg E/W"
        ),
    }


def target_outside_bounds(target: tuple[float, float], bounds: Bounds) -> bool:
    return not (
        bounds.min_lat <= target[0] <= bounds.max_lat
        and bounds.min_lon <= target[1] <= bounds.max_lon
    )


@st.cache_resource(show_spinner=False)
def event_repository() -> EventRepository:
    return EventRepository(PROJECT_ROOT / "configs" / "events.yaml", CUSTOM_EVENT_ROOT)


@st.cache_resource(show_spinner=False)
def event_builder() -> CmorphEventBuilder:
    return CmorphEventBuilder(
        event_repository(),
        CmorphCache(PROJECT_ROOT / "data" / "raw" / "cmorph"),
        load_settings(),
    )


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
        .request-band { border-top:1px solid var(--line); border-bottom:1px solid var(--line);
          padding:.72rem 0; margin:.45rem 0 .8rem; display:flex; flex-wrap:wrap; gap:.45rem 1.5rem;
          color:var(--muted); font-size:.82rem; font-variant-numeric:tabular-nums; }
        .request-band strong { color:var(--text); font-weight:650; }
        .preparation-note { max-width:72ch; color:var(--muted); line-height:1.52; margin-bottom:.8rem; }
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
          .st-key-replay_controls [data-testid="stColumn"] { width:100% !important; flex:none !important; }
          .st-key-replay_controls .stButton, .st-key-replay_controls .stButton button {
            width:100% !important; min-width:0 !important;
          }
          .st-key-replay_controls .stButton button { min-height:2.5rem; padding:.25rem .45rem; }
          .st-key-replay_controls button p, .st-key-replay_controls label p { font-size:.68rem !important; white-space:nowrap; }
          .cue { flex-direction:column; gap:.25rem; }
          .request-band { display:grid; grid-template-columns:1fr 1fr; gap:.5rem .8rem; }
        }
        </style>
        """.replace("__FONT_DATA__", font_data),
        unsafe_allow_html=True,
    )


def _source_sidebar(settings) -> tuple[object, bool, EventLibraryRecord, str]:
    st.sidebar.header("Operations")
    requested_mode = st.sidebar.radio(
        "Operating mode",
        ("Historical Replay", "Analyze New Region", "Live Mode"),
        key="operating_workflow",
    )
    mode = resolve_operating_mode(
        "Live Mode" if requested_mode == "Live Mode" else "Historical Replay",
        live_enabled=settings.features.live_mode,
        live_sources_available=False,
    )
    if mode.fallback:
        st.sidebar.warning(mode.message, icon=None)
    repository = event_repository()
    events = repository.list_events()
    by_id = {record.event_id: record for record in events}
    options = list(by_id)
    current = st.session_state.get("selected_event_id")
    if current not in by_id:
        current = options[0]
    selected_event = st.sidebar.selectbox(
        "Historical event",
        options=options,
        index=options.index(current),
        format_func=lambda event_id: event_option_label(by_id[event_id]),
        key="historical_event_id",
    )
    st.session_state.selected_event_id = selected_event
    selected_record = by_id[selected_event]
    if selected_record.kind == "custom":
        st.sidebar.caption(f"Validated custom event | {selected_record.stored_bytes / 1_048_576:.1f} MB")
        confirmed = st.sidebar.checkbox(
            "Confirm custom event deletion",
            key=f"confirm_delete_{selected_record.event_id}",
        )
        if st.sidebar.button(
            "Delete custom event",
            disabled=not confirmed,
            key=f"delete_{selected_record.event_id}",
        ):
            repository.delete(selected_record.event_id)
            load_event.clear()
            st.session_state.selected_event_id = options[0]
            st.session_state.historical_event_id = options[0]
            st.rerun()
    selected_layers = st.sidebar.multiselect(
        "Observation layers",
        options=("CMORPH rainfall",),
        default=("CMORPH rainfall",),
        help="Only layers backed by available observations can be enabled.",
    )
    st.sidebar.header("Source readiness")
    for status in (
        CmorphSource().status(),
        MosdacSatelliteSource().status(),
        ImdRadarSource().status(),
        ImdLightningSource().status(),
    ):
        marker = "VERIFIED REAL DATA" if status.verified_with_real_data else "OFFICIAL INPUT REQUIRED"
        st.sidebar.markdown(f"**{status.source}**  \n`{marker}`  \n{status.message}")
    st.sidebar.divider()
    st.sidebar.caption(
        "CMORPH is a satellite precipitation estimate—not radar. Grid spacing is approximately "
        "8 km; effective source resolution is coarser."
    )
    return mode, "CMORPH rainfall" in selected_layers, selected_record, requested_mode


ERROR_COPY = {
    EventErrorCode.DATELINE_CROSSING: "The selected box crosses the dateline. Choose a box with west longitude below east longitude.",
    EventErrorCode.REGION_TOO_LARGE: "Reduce the region to no more than 20Â° by 20Â°.",
    EventErrorCode.OUTSIDE_CMORPH_COVERAGE: "Move the region inside CMORPH latitude coverage (about 60Â°S to 60Â°N).",
    EventErrorCode.INVALID_TIME_WINDOW: "Use timezone-aware UTC half-hours with an inclusive span of 24 hours or less.",
    EventErrorCode.UNSUPPORTED_ARCHIVE_DATE: "Choose completed half-hour observations from the accessible archive (2023 onward).",
    EventErrorCode.EVENT_BUILD_IN_PROGRESS: "This exact event is already being prepared. Wait for that preparation to finish.",
    EventErrorCode.NOAA_UNAVAILABLE: "A required NOAA source hour is unavailable. Check the connection or retry with cached hours.",
    EventErrorCode.NOAA_FILE_CORRUPT: "A required NOAA file failed validation and could not be recovered safely.",
    EventErrorCode.EVENT_STORAGE_FAILED: "The event could not be stored atomically. No partial event was added.",
}


def _utc_datetime(selected_date, selected_time: clock_time) -> datetime:
    return datetime.combine(selected_date, selected_time, tzinfo=timezone.utc)


def _render_region_preparation(settings) -> None:
    st.subheader("Prepare a CMORPH region")
    st.markdown(
        '<p class="preparation-note">Choose a bounded area and inclusive UTC half-hour window. '
        "StormNowcast reuses validated NOAA files, creates the event atomically, then opens the existing replay and analysis desk.</p>",
        unsafe_allow_html=True,
    )
    presets = {
        "Custom": None,
        "Kerala": (10.3, 76.3),
        "Delhi NCR": (28.6, 77.2),
        "Mumbai": (19.1, 72.9),
        "Bengaluru": (13.0, 77.6),
        "Chennai": (13.1, 80.3),
    }
    preset = st.selectbox("Region preset", list(presets), help="Presets set a center only; adjust the size before preparing.")
    entry_mode = st.radio("Region entry", ("Center and size", "Bounding box"), horizontal=True)
    default_center = presets[preset] or (
        (settings.study_area.bounds.min_lat + settings.study_area.bounds.max_lat) / 2,
        (settings.study_area.bounds.min_lon + settings.study_area.bounds.max_lon) / 2,
    )
    bounds: Bounds | None = None
    try:
        if entry_mode == "Center and size":
            center_a, center_b, size_a, size_b, unit_column = st.columns([1, 1, 1, 1, 1.15])
            center_lat = center_a.number_input("Center latitude", -59.9, 59.9, float(default_center[0]), 0.1)
            center_lon = center_b.number_input("Center longitude", -180.0, 180.0, float(default_center[1]), 0.1)
            width = size_a.number_input("Width", 0.1, 20.0, 4.0, 0.5)
            height = size_b.number_input("Height", 0.1, 20.0, 4.0, 0.5)
            unit = unit_column.selectbox("Size unit", (SizeUnit.DEGREES, SizeUnit.KILOMETRES), format_func=lambda item: item.value.title())
            bounds = bounds_from_center(
                center_lat=center_lat,
                center_lon=center_lon,
                width=width,
                height=height,
                unit=unit,
            )
        else:
            box_a, box_b, box_c, box_d = st.columns(4)
            bounds = Bounds(
                min_lat=box_a.number_input("South latitude", -59.9, 59.9, 29.0, 0.1),
                max_lat=box_b.number_input("North latitude", -59.9, 59.9, 33.0, 0.1),
                min_lon=box_c.number_input("West longitude", -180.0, 180.0, 75.0, 0.1),
                max_lon=box_d.number_input("East longitude", -180.0, 180.0, 79.0, 0.1),
            )
    except (ValueError, EventOperationError) as exc:
        st.error(str(exc), icon=None)

    default_date = datetime(2023, 7, 9, tzinfo=timezone.utc).date()
    date_a, time_a, date_b, time_b, name_column = st.columns([1, 1, 1, 1, 1.4])
    start_date = date_a.date_input("Start date (UTC)", default_date)
    start_time = time_a.time_input("First observation", clock_time(0, 0), step=1800)
    end_date = date_b.date_input("End date (UTC)", default_date)
    end_time = time_b.time_input("Last observation", clock_time(5, 30), step=1800)
    event_name = name_column.text_input("Event name (optional)", placeholder="Display label only")

    request = None
    if bounds is not None:
        request = CustomEventRequest(
            min_lat=bounds.min_lat,
            max_lat=bounds.max_lat,
            min_lon=bounds.min_lon,
            max_lon=bounds.max_lon,
            start_time=_utc_datetime(start_date, start_time),
            end_time=_utc_datetime(end_date, end_time),
            event_name=event_name or None,
        )
        preview_column, summary_column = st.columns([1.65, 1], gap="large")
        with preview_column:
            st.plotly_chart(build_region_preview(bounds), width="stretch", config={"displaylogo": False})
        with summary_column:
            summary = request_summary(request)
            st.markdown(
                f"""
                <div class="request-band">
                  <span><strong>{summary['observations']}</strong><br>half-hour observations</span>
                  <span><strong>{summary['source_hours']}</strong><br>hourly source files</span>
                  <span><strong>{summary['span']}</strong><br>UTC time window</span>
                  <span><strong>{summary['bounds']}</strong><br>requested crop</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption("CMORPH uses approximately 8 km grid spacing; effective source resolution is coarser. No finer observations are created.")

    if st.button("Download & Analyze", type="primary", disabled=request is None, width="stretch") and request:
        with st.status("Checking archive", expanded=True) as status:
            def report(stage: BuildStage) -> None:
                status.update(label=stage.value, state="running")

            try:
                prepared = event_builder().prepare(request, progress=report)
            except EventOperationError as exc:
                status.update(label="Preparation stopped safely", state="error", expanded=True)
                st.error(ERROR_COPY.get(exc.code, exc.message), icon=None)
                st.caption(f"Error code: {exc.code.value}")
                return
            status.update(label="Event ready", state="complete", expanded=False)
        st.session_state.selected_event_id = prepared.manifest.event_id
        st.session_state.historical_event_id = prepared.manifest.event_id
        st.session_state.operating_workflow = "Historical Replay"
        st.session_state.frame_index = max(0, prepared.manifest.frame_count - 3)
        center = prepared.manifest.bounding_box
        st.session_state.target_lat = (center.min_lat + center.max_lat) / 2
        st.session_state.target_lon = (center.min_lon + center.max_lon) / 2
        load_event.clear()
        st.rerun()


def _track_readout(track, eta, *, observation_time: datetime, target: tuple[float, float]) -> None:
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
    twin = build_multisensor_twin(track, [])
    confidence = estimate_forecast_confidence(twin, lead_minutes=30)
    ci = score_convective_initiation({"rain_rate": track.current.max_intensity})
    st.markdown(
        f"""
        <div class="readout">
          <h3>Sensor evidence & evidence-quality estimate</h3>
          <dl><dt>Available sensors</dt><dd>Rainfall 1 / 6</dd>
          <dt>Evidence quality at +30 min</dt><dd>{confidence.label}</dd>
          <dt>Estimate kind</dt><dd>Input-quality heuristic</dd>
          <dt>Convective Initiation Score</dt><dd>Unavailable</dd></dl>
          <p class="limitation">{ci.explanation}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Hazard model availability"):
        st.dataframe(pd.DataFrame(hazard_rows(track)), hide_index=True, width="stretch")
        st.caption("Unavailable means required verified observations or labels are absent; it does not mean zero risk.")
    alert_engine = AlertEngine(
        [
            AlertRule(
                rule_id="prototype-extreme-rain-near-target",
                hazard="EXTREME_RAIN",
                risk_levels={"HIGH", "VERY HIGH"},
                minimum_confidence="MODERATE",
            )
        ]
    )
    alerts = alert_engine.evaluate(
        track_id=track.id,
        target=f"{target[0]:.2f}, {target[1]:.2f}",
        source_timestamp=observation_time,
        hazards=assess_hazards(track),
        eta=eta,
        confidence=confidence.label,
    )
    with st.expander(f"Prototype alert feed Â· {len(alerts)} active"):
        if alerts:
            for alert in alerts:
                st.warning(f"{alert.hazard}: {alert.risk} Â· {alert.explanation}", icon=None)
        else:
            st.caption("No prototype alert rule is triggered at this analysis cut. No message is sent externally.")
    st.progress(int(risk.score), text=" · ".join(risk.contributors))
    forecast_rows = [
        {
            "Lead": f"+{point.lead_minutes} min",
            "Valid UTC": point.valid_at.strftime("%H:%M"),
            "Heuristic radius": f"{point.uncertainty_km:.0f} km",
            "Track heuristic": point.confidence,
        }
        for point in track.forecasts
    ]
    if forecast_rows:
        st.dataframe(pd.DataFrame(forecast_rows), hide_index=True, width="stretch")
    else:
        st.info("Insufficient temporal history for motion forecast.", icon=None)
    st.caption(
        "Evidence quality above evaluates sensor availability and track history. The per-lead track heuristic "
        "is a separate motion-baseline label. Neither is calibrated or operational guidance."
    )
    arrival = eta.estimated_arrival.strftime("%Y-%m-%d %H:%M UTC") if eta.estimated_arrival else "Not issued"
    closest = f"{eta.closest_distance_km:.1f} km" if eta.closest_distance_km is not None else "Unavailable"
    lead = f"+{eta.closest_lead_minutes} min" if eta.closest_lead_minutes is not None else "Unavailable"
    st.markdown(
        f"""
        <div class="readout">
          <h3>Target closest approach / qualified ETA</h3>
          <dl><dt>Approaches corridor</dt><dd>{'YES' if eta.approaches_target else 'NO'}</dd>
          <dt>Closest distance</dt><dd>{closest}</dd>
          <dt>Forecast lead</dt><dd>{lead}</dd>
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
    mode, show_rainfall, selected_event, requested_workflow = _source_sidebar(settings)
    event_path = selected_event.data_path
    st.title("StormNowcast")
    mode_label, mode_class = observation_mode(event_path)
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

    if requested_workflow == "Analyze New Region":
        _render_region_preparation(settings)
        return

    if not event_path.exists():
        st.error(event_status_message(event_path), icon=None)
        st.code(".\\.venv\\Scripts\\python.exe scripts\\prepare_demo.py", language="powershell")
        return

    dataset = load_event(str(event_path))
    player = ReplayPlayer(dataset, settings)
    default_frame = max(0, player.frame_count - 3)
    dataset_bounds = selected_event.bounding_box or Bounds(
        min_lat=float(dataset.latitude.values.min()),
        max_lat=float(dataset.latitude.values.max()),
        min_lon=float(dataset.longitude.values.min()),
        max_lon=float(dataset.longitude.values.max()),
    )
    if st.session_state.get("active_event_id") != selected_event.event_id:
        st.session_state.active_event_id = selected_event.event_id
        st.session_state.frame_index = default_frame
        st.session_state.target_lat = (dataset_bounds.min_lat + dataset_bounds.max_lat) / 2
        st.session_state.target_lon = (dataset_bounds.min_lon + dataset_bounds.max_lon) / 2
    if "frame_index" not in st.session_state or st.session_state.frame_index >= player.frame_count:
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
    playing = control_d.toggle("Play", value=False, help="Automatically advance the historical replay")

    if mode.fallback:
        st.info(mode.message, icon=None)

    if "target_lat" not in st.session_state:
        st.session_state.target_lat = float(settings.target.latitude)
    if "target_lon" not in st.session_state:
        st.session_state.target_lon = float(settings.target.longitude)
    target_lat = float(st.session_state.target_lat)
    target_lon = float(st.session_state.target_lon)
    target = (target_lat, target_lon)
    if target_outside_bounds(target, dataset_bounds):
        st.warning("The selected target is outside this event region; closest-approach analysis remains available.", icon=None)
    snapshot = player.analyze(st.session_state.frame_index, target)
    st.markdown(
        f"""
        <div class="cue"><span><strong>ANALYSIS CUT {snapshot.frame_index + 1:02d}/{player.frame_count:02d}</strong> · {snapshot.timestamp:%Y-%m-%d %H:%M UTC}</span>
        <span>Only observations through this timestamp are used</span></div>
        """,
        unsafe_allow_html=True,
    )

    map_column, rail_column = st.columns([2.15, 1], gap="large")
    track_ids = [track.id for track in snapshot.tracks]
    track_key = f"selected_track_{selected_event.event_id}"
    selected_id = st.session_state.get(track_key)
    if selected_id not in track_ids:
        selected_id = track_ids[0] if track_ids else None
    with map_column:
        st.plotly_chart(
            build_map(
                snapshot,
                target,
                show_rainfall=show_rainfall,
                event_id=selected_event.event_id,
                bounds=dataset_bounds,
                selected_track_id=selected_id,
            ),
            width="stretch",
            config={"displaylogo": False},
        )
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
            selected_id = st.selectbox(
                "Inspect Intense Precipitation Cell",
                track_ids,
                index=track_ids.index(selected_id),
                key=track_key,
            )
            track = next(item for item in snapshot.tracks if item.id == selected_id)
            _track_readout(
                track,
                snapshot.eta_by_track[track.id],
                observation_time=snapshot.timestamp,
                target=target,
            )
        else:
            st.info("No Intense Precipitation Cell meets the configured threshold in this frame.", icon=None)

    with st.expander("Sensor evidence at this analysis cut Â· 1 available / 4 displayed"):
        st.dataframe(
            pd.DataFrame(sensor_availability_rows(snapshot.timestamp)),
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Native and processed resolution are shown separately. Resampling a coarse source never creates finer physical observations."
        )

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
        provenance_path = (
            selected_event.manifest_path.parent / "provenance.json"
            if selected_event.manifest_path is not None
            else settings.data.provenance_manifest
        )
        if provenance_path.exists():
            records = read_manifest(provenance_path)
            st.write(
                f"{len(records)} official NOAA CPC hourly files · acquired with SHA-256 checksums · "
                f"{dataset.attrs.get('observation_start')} to {dataset.attrs.get('observation_end')}"
            )
            with st.expander("Inspect source records"):
                st.json(json.loads(provenance_path.read_text(encoding="utf-8")))
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
