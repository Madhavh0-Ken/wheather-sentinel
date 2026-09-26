from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from storm_nowcast.api.app import create_app
from storm_nowcast.config import load_settings
from storm_nowcast.events.errors import EventErrorCode, EventOperationError
from storm_nowcast.services.analysis import AnalysisService
from tests.test_event_builder import event_request, make_builder
from tests.test_replay import replay_dataset


def _payload(*, full_day: bool = False) -> dict:
    request = event_request(name="API region")
    end = datetime(2023, 7, 10, 0, 30, tzinfo=timezone.utc) if full_day else request.end_time
    return {
        "min_lat": request.min_lat,
        "max_lat": request.max_lat,
        "min_lon": request.min_lon,
        "max_lon": request.max_lon,
        "start_time": request.start_time.isoformat(),
        "end_time": end.isoformat(),
        "event_name": request.event_name,
    }


def _client(tmp_path):
    builder, repository, _, _ = make_builder(tmp_path)
    default_service = AnalysisService.from_dataset(
        replay_dataset(), settings=load_settings(), event_id="synthetic-test-event"
    )
    return (
        TestClient(
            create_app(
                settings=load_settings(),
                service_override=default_service,
                repository_override=repository,
                builder_override=builder,
            )
        ),
        repository,
    )


def test_api_prepares_reuses_lists_and_analyzes_custom_event_without_changing_default(tmp_path):
    client, _ = _client(tmp_path)

    created = client.post("/events/prepare", json=_payload())
    assert created.status_code == 200
    body = created.json()
    assert body["created"] is True and body["reused"] is False
    event_id = body["manifest"]["event_id"]
    assert body["manifest"]["frame_count"] == 3

    reused = client.post("/events/prepare", json={**_payload(), "event_name": "Ignored rename"})
    assert reused.json()["reused"] is True
    listed = client.get("/events").json()
    assert [(item["kind"], item["event_id"]) for item in listed] == [
        ("builtin", "builtin-event"),
        ("custom", event_id),
    ]
    assert client.get(f"/events/{event_id}").json()["ready"] is True

    selected = client.get(f"/nowcast?event_id={event_id}&frame=2&target_lat=30.1&target_lon=75.3")
    assert selected.status_code == 200
    assert selected.json()["event_id"] == event_id
    assert client.get("/nowcast?frame=2&target_lat=30.1&target_lon=75.3").json()["event_id"] == "synthetic-test-event"


def test_api_preserves_49_observations_for_full_inclusive_24_hour_span(tmp_path):
    client, _ = _client(tmp_path)

    response = client.post("/events/prepare", json=_payload(full_day=True))

    assert response.status_code == 200
    assert response.json()["manifest"]["expected_frame_count"] == 49
    assert response.json()["manifest"]["frame_count"] == 49
    assert len(response.json()["manifest"]["source_files"]) == 25


def test_api_delete_is_id_only_and_protects_builtins(tmp_path):
    client, _ = _client(tmp_path)
    event_id = client.post("/events/prepare", json=_payload()).json()["manifest"]["event_id"]

    protected = client.delete("/events/builtin-event")
    assert protected.status_code == 409
    assert protected.json()["code"] == "BUILTIN_EVENT_PROTECTED"
    unsafe = client.delete("/events/unsafe.id")
    assert unsafe.status_code == 409
    assert unsafe.json()["code"] == "UNSAFE_EVENT_PATH"

    assert client.delete(f"/events/{event_id}").status_code == 200
    missing = client.get(f"/events/{event_id}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "EVENT_NOT_FOUND"


def test_api_request_domain_validation_uses_stable_error_contract(tmp_path):
    client, _ = _client(tmp_path)
    payload = _payload()
    payload.update({"min_lon": 170.0, "max_lon": -170.0})

    response = client.post("/events/prepare", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "DATELINE_CROSSING"
    assert response.json()["message"]
    assert isinstance(response.json()["details"], dict)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (EventErrorCode.EVENT_BUILD_IN_PROGRESS, 409),
        (EventErrorCode.NOAA_UNAVAILABLE, 503),
    ],
)
def test_api_maps_builder_failures_to_stable_http_status(tmp_path, code, status):
    _, repository = _client(tmp_path)

    class FailingBuilder:
        def prepare(self, *_args, **_kwargs):
            raise EventOperationError(code, "safe failure", details={"source": "test"})

    default_service = AnalysisService.from_dataset(
        replay_dataset(), settings=load_settings(), event_id="synthetic-test-event"
    )
    client = TestClient(
        create_app(
            service_override=default_service,
            repository_override=repository,
            builder_override=FailingBuilder(),
        )
    )

    response = client.post("/events/prepare", json=_payload())

    assert response.status_code == status
    assert response.json() == {
        "code": code.value,
        "message": "safe failure",
        "details": {"source": "test"},
    }


def test_api_reports_unknown_selected_event_without_falling_back_to_builtin(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get("/storms?event_id=cmorph-custom-unknown")

    assert response.status_code == 404
    assert response.json()["code"] == "EVENT_NOT_FOUND"
