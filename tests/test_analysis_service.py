from storm_nowcast.config import load_settings
from storm_nowcast.services.analysis import AnalysisService
from tests.test_replay import replay_dataset


def test_analysis_snapshot_is_transport_neutral_and_strictly_causal():
    service = AnalysisService.from_dataset(
        replay_dataset(), settings=load_settings(), event_id="synthetic-test-event"
    )

    snapshot = service.snapshot(frame_index=1, target=(30.1, 75.3))

    assert snapshot.event_id == "synthetic-test-event"
    assert snapshot.mode == "HISTORICAL_REPLAY"
    assert all(timestamp <= snapshot.observation_time for timestamp in snapshot.source_times)
    assert snapshot.frame_index == 1
    assert snapshot.tracks[0].id == "IPC-001"
    assert snapshot.tracks[0].hazards[0].model_name == "Prototype Extreme Rain Risk"
    assert snapshot.tracks[0].hazards[2].status == "INSUFFICIENT_DATA"
    assert snapshot.model_dump(mode="json")["observation_time"].endswith("Z")
