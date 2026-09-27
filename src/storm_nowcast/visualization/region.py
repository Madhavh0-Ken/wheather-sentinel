from __future__ import annotations

import math

import plotly.graph_objects as go

from storm_nowcast.config import Bounds


def map_view(bounds: Bounds) -> dict[str, object]:
    """Return a stable viewport that fits a non-dateline-crossing rectangle."""
    span = max(bounds.max_lat - bounds.min_lat, bounds.max_lon - bounds.min_lon)
    zoom = max(2.2, min(9.0, math.log2(180.0 / max(span, 0.05))))
    return {
        "center": {
            "lat": (bounds.min_lat + bounds.max_lat) / 2.0,
            "lon": (bounds.min_lon + bounds.max_lon) / 2.0,
        },
        "zoom": zoom,
    }


def build_region_preview(bounds: Bounds) -> go.Figure:
    view = map_view(bounds)
    center = view["center"]
    figure = go.Figure()
    figure.add_trace(
        go.Scattermap(
            lat=[bounds.min_lat, bounds.min_lat, bounds.max_lat, bounds.max_lat, bounds.min_lat],
            lon=[bounds.min_lon, bounds.max_lon, bounds.max_lon, bounds.min_lon, bounds.min_lon],
            mode="lines",
            fill="toself",
            fillcolor="rgba(69,196,232,0.10)",
            line={"color": "#45C4E8", "width": 3},
            name="REQUESTED REGION",
            hovertemplate="Requested CMORPH crop<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scattermap(
            lat=[center["lat"]],
            lon=[center["lon"]],
            mode="markers",
            marker={"color": "#FFFFFF", "size": 10, "symbol": "cross"},
            name="REGION CENTER",
            hovertemplate="Region center<extra></extra>",
        )
    )
    figure.update_layout(
        height=380,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="#07111C",
        plot_bgcolor="#07111C",
        font={"family": "Segoe UI, sans-serif", "color": "#EAF6FF"},
        showlegend=False,
        map={"style": "carto-darkmatter", **view},
        uirevision=(
            f"region-preview:{bounds.min_lat:.4f}:{bounds.max_lat:.4f}:"
            f"{bounds.min_lon:.4f}:{bounds.max_lon:.4f}"
        ),
    )
    return figure
