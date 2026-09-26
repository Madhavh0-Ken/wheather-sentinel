from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from pyproj import Geod
from shapely.geometry import shape

from storm_nowcast.replay.player import ReplaySnapshot
from storm_nowcast.config import Bounds
from storm_nowcast.visualization.region import map_view


WGS84 = Geod(ellps="WGS84")
OBSERVED = "#45C4E8"
DERIVED = "#F6B73C"
FORECAST = "#F15BB5"


def _outline(geojson: dict) -> tuple[list[float], list[float]]:
    geometry = shape(geojson)
    if geometry.geom_type == "MultiPolygon":
        geometry = max(geometry.geoms, key=lambda part: part.area)
    longitude, latitude = geometry.exterior.xy
    return list(latitude), list(longitude)


def _uncertainty_circle(latitude: float, longitude: float, radius_km: float) -> tuple[list[float], list[float]]:
    bearings = np.linspace(0, 360, 49)
    lons, lats, _ = WGS84.fwd(
        np.full_like(bearings, longitude),
        np.full_like(bearings, latitude),
        bearings,
        np.full_like(bearings, radius_km * 1000),
    )
    return list(lats), list(lons)


def _coordinate_edges(values: np.ndarray) -> np.ndarray:
    """Return cell edges without interpolating or smoothing source values."""
    values = np.asarray(values, dtype=float)
    if values.size == 1:
        return np.array([values[0] - 0.036, values[0] + 0.036])
    midpoints = (values[:-1] + values[1:]) / 2
    return np.concatenate(
        ([values[0] - (midpoints[0] - values[0])], midpoints, [values[-1] + (values[-1] - midpoints[-1])])
    )


def _rainfall_grid_trace(snapshot: ReplaySnapshot) -> go.Choroplethmap:
    field = np.asarray(snapshot.rainfall.values, dtype=float)
    latitudes = np.asarray(snapshot.rainfall.latitude.values, dtype=float)
    longitudes = np.asarray(snapshot.rainfall.longitude.values, dtype=float)
    latitude_edges = _coordinate_edges(latitudes)
    longitude_edges = _coordinate_edges(longitudes)
    features: list[dict] = []
    locations: list[str] = []
    rates: list[float] = []
    for row, column in np.argwhere(np.isfinite(field) & (field > 0)):
        cell_id = f"r{row}c{column}"
        south, north = latitude_edges[row], latitude_edges[row + 1]
        west, east = longitude_edges[column], longitude_edges[column + 1]
        features.append(
            {
                "type": "Feature",
                "properties": {"id": cell_id},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
                },
            }
        )
        locations.append(cell_id)
        rates.append(float(field[row, column]))
    return go.Choroplethmap(
        geojson={"type": "FeatureCollection", "features": features},
        locations=locations,
        z=rates,
        featureidkey="properties.id",
        zmin=0,
        zmax=max(50.0, float(np.nanmax(field))),
        colorscale=[
            [0.0, "#102536"],
            [0.2, "#17415A"],
            [0.45, "#22B8CF"],
            [0.72, "#F6B73C"],
            [1.0, "#FF4D5A"],
        ],
        marker={"opacity": 0.82, "line": {"width": 0}},
        colorbar={
            "title": {"text": "mm h⁻¹", "side": "top"},
            "thickness": 10,
            "len": 0.42,
            "x": 0.015,
            "y": 0.04,
            "xanchor": "left",
            "yanchor": "bottom",
            "tickfont": {"color": "#EAF6FF"},
        },
        name="OBSERVED · Rain rate (source grid)",
        hovertemplate="OBSERVED source grid cell<br>%{z:.1f} mm h⁻¹<extra></extra>",
    )


def build_map(
    snapshot: ReplaySnapshot,
    target: tuple[float, float],
    *,
    show_rainfall: bool = True,
    event_id: str | None = None,
    bounds: Bounds | None = None,
    selected_track_id: str | None = None,
) -> go.Figure:
    figure = go.Figure()
    if show_rainfall:
        figure.add_trace(_rainfall_grid_trace(snapshot))

    for track in snapshot.tracks:
        selected = selected_track_id is None or selected_track_id == track.id
        emphasis = 1.0 if selected else 0.34
        history_lats = [item.centroid_lat for item in track.history]
        history_lons = [item.centroid_lon for item in track.history]
        figure.add_trace(
            go.Scattermap(
                lat=history_lats,
                lon=history_lons,
                mode="lines+markers",
                line={"color": DERIVED, "width": 3.5 if selected else 1.4},
                marker={"color": DERIVED, "size": 8 if selected else 5},
                opacity=emphasis,
                name=f"DERIVED · {track.id} history",
                legendgroup="derived",
                hovertemplate=f"DERIVED tracked history · {track.id}<extra></extra>",
            )
        )
        footprint_lat, footprint_lon = _outline(track.current.polygon_geojson)
        figure.add_trace(
            go.Scattermap(
                lat=footprint_lat,
                lon=footprint_lon,
                mode="lines",
                fill="toself",
                fillcolor="rgba(246,183,60,0.13)",
                line={"color": DERIVED, "width": 2.5 if selected else 1},
                opacity=emphasis,
                name=f"DERIVED · {track.id} footprint",
                legendgroup="derived",
                hovertemplate=(
                    f"DERIVED · {track.id}<br>Max {track.current.max_intensity:.1f} mm h⁻¹"
                    "<extra></extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scattermap(
                lat=[track.current.centroid_lat],
                lon=[track.current.centroid_lon],
                mode="markers+text",
                marker={"color": DERIVED, "size": 11},
                opacity=emphasis,
                text=[track.id],
                textposition="top right",
                textfont={"color": "#FFF1CC", "size": 12},
                name=f"DERIVED · {track.id} centroid",
                legendgroup="derived",
                showlegend=False,
                hovertemplate=f"DERIVED · {track.id} centroid<extra></extra>",
            )
        )
        forecast_lats = [track.current.centroid_lat, *[point.latitude for point in track.forecasts]]
        forecast_lons = [track.current.centroid_lon, *[point.longitude for point in track.forecasts]]
        figure.add_trace(
            go.Scattermap(
                lat=forecast_lats,
                lon=forecast_lons,
                mode="lines+markers",
                line={"color": FORECAST, "width": 3.5 if selected else 1.4},
                marker={"color": FORECAST, "size": 8 if selected else 5},
                opacity=emphasis,
                name=f"FORECAST · {track.id} track",
                legendgroup="forecast",
                hovertemplate="FORECAST · %{text}<extra></extra>",
                text=["issued", *[f"+{point.lead_minutes} min" for point in track.forecasts]],
            )
        )
        for point in track.forecasts:
            circle_lat, circle_lon = _uncertainty_circle(
                point.latitude, point.longitude, point.uncertainty_km
            )
            figure.add_trace(
                go.Scattermap(
                    lat=circle_lat,
                    lon=circle_lon,
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(241,91,181,0.10)",
                    line={"color": "#FFD4EE", "width": 2},
                    opacity=emphasis,
                    name=f"FORECAST · +{point.lead_minutes} min uncertainty",
                    legendgroup="forecast",
                    showlegend=False,
                    meta={"uncertainty_km": point.uncertainty_km},
                    hovertemplate=(
                        f"FORECAST · +{point.lead_minutes} min<br>"
                        f"Heuristic uncertainty radius {point.uncertainty_km:.0f} km<extra></extra>"
                    ),
                )
            )

    figure.add_trace(
        go.Scattermap(
            lat=[target[0]],
            lon=[target[1]],
            mode="markers",
            marker={"color": "#FFFFFF", "size": 14, "symbol": "cross"},
            name="TARGET · Selected location",
            hovertemplate="TARGET · Selected location<extra></extra>",
        )
    )
    if bounds is None:
        bounds = Bounds(
            min_lat=float(np.min(snapshot.rainfall.latitude.values)),
            max_lat=float(np.max(snapshot.rainfall.latitude.values)),
            min_lon=float(np.min(snapshot.rainfall.longitude.values)),
            max_lon=float(np.max(snapshot.rainfall.longitude.values)),
        )
    view = map_view(bounds)
    figure.update_layout(
        height=610,
        margin={"l": 0, "r": 0, "t": 42, "b": 0},
        paper_bgcolor="#07111C",
        plot_bgcolor="#07111C",
        font={"family": "Segoe UI, sans-serif", "color": "#EAF6FF"},
        showlegend=False,
        map={
            "style": "carto-darkmatter",
            **view,
        },
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.01,
            "yanchor": "bottom",
            "bgcolor": "rgba(7,17,28,0.86)",
            "bordercolor": "#294052",
            "borderwidth": 1,
            "font": {"size": 11},
        },
        uirevision=f"storm-nowcast-map:{event_id or 'default'}",
    )
    return figure
