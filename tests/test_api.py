from pathlib import Path

from fastapi.testclient import TestClient

from storm_nowcast.api.app import create_app
from storm_nowcast.config import load_settings
from storm_nowcast.services.analysis import AnalysisService
from tests.test_replay import replay_dataset


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
