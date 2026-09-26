from storm_nowcast.config import load_settings
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
