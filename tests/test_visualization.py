from dataclasses import replace

from storm_nowcast.config import Bounds, load_settings
from storm_nowcast.replay.player import ReplayPlayer
from storm_nowcast.visualization.layers import build_map
from tests.test_replay import replay_dataset


def test_map_exposes_observed_derived_and_forecast_layer_classes():
    settings = load_settings()
    snapshot = ReplayPlayer(replay_dataset(), settings).analyze(2, target=(30.1, 75.3))

    figure = build_map(snapshot, target=(30.1, 75.3))
    names = {trace.name for trace in figure.data}

    assert any(name.startswith("OBSERVED · Rain rate") for name in names)
    assert figure.data[0].type == "choroplethmap"
    assert not any(trace.type == "densitymap" for trace in figure.data)
    assert any(name.startswith("DERIVED · IPC-001 history") for name in names)
    assert any(name.startswith("DERIVED · IPC-001 footprint") for name in names)
    assert any(name.startswith("FORECAST · IPC-001 track") for name in names)
    assert "TARGET · Selected location" in names
    assert figure.layout.showlegend is False


def test_forecast_uncertainty_layers_are_strictly_increasing():
    settings = load_settings()
    snapshot = ReplayPlayer(replay_dataset(), settings).analyze(2, target=(30.1, 75.3))

    figure = build_map(snapshot, target=(30.1, 75.3))
    uncertainties = [
        float(trace.meta["uncertainty_km"])
        for trace in figure.data
        if isinstance(trace.meta, dict) and "uncertainty_km" in trace.meta
    ]

    assert uncertainties == sorted(uncertainties)
    assert len(set(uncertainties)) == 3


def test_rainfall_grid_uses_one_unsmoothed_polygon_per_positive_source_cell():
    settings = load_settings()
    snapshot = ReplayPlayer(replay_dataset(), settings).analyze(2, target=(30.1, 75.3))

    rainfall = build_map(snapshot, target=(30.1, 75.3)).data[0]
    positive_cells = int((snapshot.rainfall.values > 0).sum())

    assert rainfall.type == "choroplethmap"
    assert len(rainfall.locations) == positive_cells
    assert "source grid cell" in rainfall.hovertemplate


def test_rainfall_layer_can_be_hidden_without_hiding_derived_forecast_or_target():
    settings = load_settings()
    snapshot = ReplayPlayer(replay_dataset(), settings).analyze(2, target=(30.1, 75.3))

    figure = build_map(snapshot, target=(30.1, 75.3), show_rainfall=False)
    names = {trace.name for trace in figure.data}

    assert not any(name.startswith("OBSERVED Â· Rain rate") for name in names)
    assert any(name.startswith("DERIVED") for name in names)
    assert any(name.startswith("FORECAST") for name in names)
    assert any(name.startswith("TARGET") for name in names)


def test_map_revision_and_view_are_event_specific():
    snapshot = ReplayPlayer(replay_dataset(), load_settings()).analyze(2, target=(30.1, 75.3))
    bounds = Bounds(min_lat=29.0, max_lat=31.0, min_lon=74.0, max_lon=78.0)

    figure = build_map(snapshot, (30.1, 75.3), event_id="custom-one", bounds=bounds)

    assert figure.layout.uirevision == "storm-nowcast-map:custom-one"
    assert figure.layout.map.center.lat == 30.0
    assert figure.layout.map.center.lon == 76.0


def test_selected_track_keeps_full_emphasis_while_other_tracks_are_quiet():
    snapshot = ReplayPlayer(replay_dataset(), load_settings()).analyze(2, target=(30.1, 75.3))
    second = snapshot.tracks[0].model_copy(update={"id": "IPC-002"})
    snapshot = replace(snapshot, tracks=[snapshot.tracks[0], second])

    figure = build_map(snapshot, (30.1, 75.3), selected_track_id="IPC-001")
    selected = next(trace for trace in figure.data if "IPC-001 history" in trace.name)
    other = next(trace for trace in figure.data if "IPC-002 history" in trace.name)

    assert selected.line.width > other.line.width
    assert selected.opacity > other.opacity
