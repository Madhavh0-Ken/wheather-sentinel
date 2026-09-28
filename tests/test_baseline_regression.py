import pytest

from storm_nowcast.config import load_settings
from storm_nowcast.replay.player import ReplayPlayer
from tests.test_replay import replay_dataset


def test_cmorph_only_analysis_contract_remains_stable():
    snapshot = ReplayPlayer(replay_dataset(), load_settings()).analyze(2, target=(30.1, 75.3))

    assert snapshot.observation_times == tuple(sorted(snapshot.observation_times))
    assert [track.id for track in snapshot.tracks] == ["IPC-001"]
    track = snapshot.tracks[0]
    assert track.speed_kmh == pytest.approx(19.0831526)
    assert track.risk.level == "MODERATE"
    assert track.risk.score == pytest.approx(45.2)
    assert [point.lead_minutes for point in track.forecasts] == [30, 60, 120]
    assert [point.uncertainty_km for point in track.forecasts] == [21.0, 30.0, 48.0]
    assert snapshot.eta_by_track[track.id].closest_lead_minutes == 30
    assert snapshot.insat.available is False
    assert snapshot.sensor_evidence_by_track[track.id] == []


def test_new_sensor_features_are_disabled_by_default():
    settings = load_settings()

    assert settings.features.satellite is False
    assert settings.features.radar is False
    assert settings.features.lightning is False
    assert settings.features.surface is False
    assert settings.features.nwp is False
    assert settings.features.optical_flow is False
