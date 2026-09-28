from storm_nowcast.config import load_settings
from storm_nowcast.services.analysis import AnalysisService
from tests.test_replay import replay_dataset, satellite_cube


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


def test_analysis_snapshot_serializes_real_insat_metadata_and_twin_availability():
    service = AnalysisService.from_dataset(
        replay_dataset(),
        settings=load_settings(),
        event_id="insat-test-event",
        satellite_cube=satellite_cube(),
    )

    snapshot = service.snapshot(frame_index=1, target=(30.1, 75.3))
    payload = snapshot.model_dump(mode="json")

    assert payload["insat_available"] is True
    assert payload["insat_observation_time"] == "2023-07-09T00:15:00Z"
    assert payload["insat_age_minutes"] == 15.0
    assert payload["insat_provider"] == "ISRO/SAC MOSDAC"
    assert payload["insat_product"] == "3RIMG_L1C_ASIA_MER"
    assert payload["insat_source_file"] == "scan-0015.nc"
    assert payload["insat_provenance"]["asset"]["sha256"] == "a" * 64
    assert {item["name"] for item in payload["insat_variables"]} == {
        "infrared_brightness_temperature",
        "water_vapour_brightness_temperature",
    }
    assert snapshot.tracks[0].sensor_availability["SATELLITE"] == "AVAILABLE"
