from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import yaml

from storm_nowcast.api.app import create_app
from storm_nowcast.config import load_settings
from storm_nowcast.replay.player import save_event
from storm_nowcast.services.analysis import AnalysisService
from tests.test_insat_replay import _write_processed_insat
from tests.test_replay import replay_dataset, satellite_cube


def _client():
    service = AnalysisService.from_dataset(
        replay_dataset(), settings=load_settings(), event_id="synthetic-test-event"
    )
    return TestClient(create_app(service_override=service))


def test_api_metadata_matches_analysis_and_custom_event_operations():
    client = _client()

    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["mode"] == "analysis-and-event-management"
    assert "read-only" not in client.get("/openapi.json").json()["info"]["title"].lower()
    sources = client.get("/sources").json()
    assert any(item["source"].startswith("CMORPH") and item["implemented"] for item in sources)
    assert client.get("/events").status_code == 200


def test_read_only_api_exposes_shared_storm_nowcast_hazard_alert_and_evaluation_logic():
    client = _client()
    query = "?frame=2&target_lat=30.1&target_lon=75.3"

    storms = client.get("/storms" + query)
    assert storms.status_code == 200
    assert storms.json()[0]["id"] == "IPC-001"
    assert client.get("/storms/IPC-001" + query).status_code == 200
    assert client.get("/storms/UNKNOWN" + query).status_code == 404
    nowcast = client.get("/nowcast" + query).json()
    assert [item["lead_minutes"] for item in nowcast["tracks"][0]["forecasts"]] == [30, 60, 120]
    hazards = client.get("/hazards" + query).json()
    assert hazards["IPC-001"][0]["model_name"] == "Prototype Extreme Rain Risk"
    assert client.get("/alerts" + query).json() == []
    evaluation = client.get("/evaluation" + query).json()
    assert evaluation[0]["lead_minutes"] == 30


def test_missing_cached_event_is_reported_without_download_or_startup_crash(tmp_path: Path):
    settings = load_settings()
    settings.data.processed_event = tmp_path / "missing.nc"
    client = TestClient(create_app(settings=settings, catalog_path=tmp_path / "missing-events.yaml"))

    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["event_data"] == "missing"
    response = client.get("/storms")
    assert response.status_code == 503
    assert "prepare_demo.py" in response.json()["detail"]


def test_api_loads_event_scoped_real_insat_state_and_frame_metadata(tmp_path: Path):
    event = replay_dataset().copy(deep=True)
    event.attrs["event_id"] = "fixture-event"
    event_path = tmp_path / "event.nc"
    save_event(event, event_path)
    insat_dir = tmp_path / "insat"
    for filename, observation_time in (
        ("scan-2345.nc", datetime(2023, 7, 8, 23, 45, tzinfo=timezone.utc)),
        ("scan-0015.nc", datetime(2023, 7, 9, 0, 15, tzinfo=timezone.utc)),
        ("scan-0045.nc", datetime(2023, 7, 9, 0, 45, tzinfo=timezone.utc)),
    ):
        _write_processed_insat(
            insat_dir,
            filename=filename,
            observation_time=observation_time,
        )
    catalog_path = tmp_path / "configs" / "events.yaml"
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_text(
        yaml.safe_dump(
            {
                "events": [
                    {
                        "id": "fixture-event",
                        "name": "Fixture event",
                        "region": "Fixture region",
                        "observation_start": "2023-07-09T00:00:00Z",
                        "observation_end": "2023-07-09T01:00:00Z",
                        "sources": [
                            "NOAA CPC CMORPH V0.x RAW 8km-30min",
                            "ISRO/SAC MOSDAC INSAT-3DR 3RIMG_L1C_ASIA_MER",
                        ],
                        "frame_count": 3,
                        "data_path": str(event_path),
                        "insat_data_path": str(insat_dir),
                        "insat_max_age_minutes": 30,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = load_settings()
    settings.data.processed_event = event_path
    client = TestClient(create_app(settings=settings, catalog_path=catalog_path))

    nowcast = client.get("/nowcast?frame=1&target_lat=30.1&target_lon=75.3").json()
    assert nowcast["insat_available"] is True
    assert nowcast["insat_observation_time"] == "2023-07-09T00:15:00Z"
    assert nowcast["insat_age_minutes"] == 15.0
    assert nowcast["insat_provider"] == "ISRO/SAC MOSDAC"
    assert nowcast["insat_product"] == "3RIMG_L1C_ASIA_MER"
    assert nowcast["insat_source_file"] == "scan-0015.nc"
    assert nowcast["tracks"][0]["sensor_availability"]["SATELLITE"] == "AVAILABLE"
    event_nowcast = client.get(
        "/nowcast?event_id=fixture-event&frame=1&target_lat=30.1&target_lon=75.3"
    ).json()
    assert event_nowcast["insat_available"] is True
    sources = {item["source"]: item for item in client.get("/sources").json()}
    assert sources["ISRO MOSDAC INSAT"]["available"] is True
    events = client.get("/events").json()
    assert events[0]["sources"] == [
        "NOAA CPC CMORPH V0.x RAW 8km-30min",
        "ISRO/SAC MOSDAC INSAT-3DR 3RIMG_L1C_ASIA_MER",
    ]

    for path in insat_dir.glob("*.nc*"):
        path.unlink()

    event_query = "?event_id=fixture-event&frame=1&target_lat=30.1&target_lon=75.3"
    assert client.get("/nowcast" + event_query).json()["insat_available"] is False
    event_sources = {
        item["source"]: item
        for item in client.get("/sources?event_id=fixture-event").json()
    }
    assert event_sources["ISRO MOSDAC INSAT"]["available"] is False
    assert client.get("/nowcast?frame=1").json()["insat_available"] is False


def test_api_service_override_remains_insat_unavailable_without_local_file_lookup():
    service = AnalysisService.from_dataset(
        replay_dataset(), settings=load_settings(), event_id="synthetic-without-insat"
    )
    client = TestClient(create_app(service_override=service))

    assert client.get("/nowcast?frame=1").json()["insat_available"] is False
    mosdac = next(
        item for item in client.get("/sources").json() if item["source"] == "ISRO MOSDAC INSAT"
    )
    assert mosdac["available"] is False


def test_api_service_override_can_expose_pre_aligned_insat_without_catalog_dependency():
    service = AnalysisService.from_dataset(
        replay_dataset(),
        settings=load_settings(),
        event_id="synthetic-with-insat",
        satellite_cube=satellite_cube(),
    )
    client = TestClient(create_app(service_override=service))

    mosdac = next(
        item for item in client.get("/sources").json() if item["source"] == "ISRO MOSDAC INSAT"
    )
    assert mosdac["available"] is True
