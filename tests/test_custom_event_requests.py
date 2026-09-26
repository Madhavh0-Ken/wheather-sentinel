from datetime import datetime, timedelta, timezone

import pytest

from storm_nowcast.config import Bounds


def _api():
    from storm_nowcast.events.custom import (
        CustomEventRequest,
        SizeUnit,
        bounds_from_center,
        custom_event_id,
        required_cmorph_hours,
        validate_custom_event_request,
    )
    from storm_nowcast.events.errors import EventErrorCode, EventOperationError

    return (
        CustomEventRequest,
        SizeUnit,
        bounds_from_center,
        custom_event_id,
        required_cmorph_hours,
        validate_custom_event_request,
        EventErrorCode,
        EventOperationError,
    )


def _request(**overrides):
    CustomEventRequest, *_ = _api()
    values = {
        "min_lat": 8.0,
        "max_lat": 13.0,
        "min_lon": 74.0,
        "max_lon": 78.0,
        "start_time": datetime(2024, 5, 18, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2024, 5, 18, 5, 30, tzinfo=timezone.utc),
        "event_name": "Kerala — 18 May 2024",
    }
    values.update(overrides)
    return CustomEventRequest(**values)


def test_inclusive_24_hour_window_has_49_frames_and_25_source_hours():
    *_, required_hours, validate, _, _ = _api()
    start = datetime(2024, 5, 18, 0, 0, tzinfo=timezone.utc)
    request = validate(
        _request(start_time=start, end_time=start + timedelta(hours=24)),
        now=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )

    assert request.expected_frame_count == 49
    hours = required_hours(request)
    assert len(hours) == 25
    assert hours[0] == start
    assert hours[-1] == start + timedelta(hours=24)


def test_times_normalize_to_utc_and_naive_time_is_rejected():
    *_, validate, EventErrorCode, EventOperationError = _api()
    india = timezone(timedelta(hours=5, minutes=30))
    request = validate(
        _request(
            start_time=datetime(2024, 5, 18, 5, 30, tzinfo=india),
            end_time=datetime(2024, 5, 18, 11, 0, tzinfo=india),
        ),
        now=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )

    assert request.start_time == datetime(2024, 5, 18, 0, 0, tzinfo=timezone.utc)
    assert request.end_time == datetime(2024, 5, 18, 5, 30, tzinfo=timezone.utc)
    with pytest.raises(EventOperationError) as captured:
        validate(
            _request(start_time=datetime(2024, 5, 18, 0, 0)),
            now=datetime(2026, 9, 26, tzinfo=timezone.utc),
        )
    assert captured.value.code == EventErrorCode.INVALID_TIME_WINDOW


def test_center_size_converts_degrees_and_kilometres_to_bounds():
    _, SizeUnit, convert, *_ = _api()

    degrees = convert(
        center_lat=10.0,
        center_lon=76.0,
        width=4.0,
        height=2.0,
        unit=SizeUnit.DEGREES,
    )
    kilometres = convert(
        center_lat=10.0,
        center_lon=76.0,
        width=100.0,
        height=200.0,
        unit=SizeUnit.KILOMETRES,
    )

    assert degrees == Bounds(min_lat=9.0, max_lat=11.0, min_lon=74.0, max_lon=78.0)
    assert kilometres.min_lat == pytest.approx(9.09588055, abs=1e-6)
    assert kilometres.max_lat == pytest.approx(10.90407045, abs=1e-6)
    assert kilometres.min_lon == pytest.approx(75.54395970, abs=1e-6)
    assert kilometres.max_lon == pytest.approx(76.45604030, abs=1e-6)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"min_lat": 10.0, "max_lat": 31.0}, "REGION_TOO_LARGE"),
        ({"min_lat": 59.0, "max_lat": 60.0}, "OUTSIDE_CMORPH_COVERAGE"),
        ({"min_lat": 10.0, "max_lat": 10.0}, "INVALID_BOUNDS"),
        ({"min_lon": 170.0, "max_lon": -170.0}, "DATELINE_CROSSING"),
        (
            {
                "start_time": datetime(2024, 5, 18, 0, 15, tzinfo=timezone.utc),
                "end_time": datetime(2024, 5, 18, 5, 30, tzinfo=timezone.utc),
            },
            "INVALID_TIME_WINDOW",
        ),
        (
            {
                "start_time": datetime(2022, 12, 31, 23, 30, tzinfo=timezone.utc),
                "end_time": datetime(2023, 1, 1, 0, 30, tzinfo=timezone.utc),
            },
            "UNSUPPORTED_ARCHIVE_DATE",
        ),
    ],
)
def test_bounds_reject_coverage_size_order_and_dateline_failures_with_stable_codes(
    overrides, expected_code
):
    *_, validate, _, EventOperationError = _api()

    with pytest.raises(EventOperationError) as captured:
        validate(
            _request(**overrides),
            now=datetime(2026, 9, 26, tzinfo=timezone.utc),
        )

    assert captured.value.code.value == expected_code
    assert captured.value.message


def test_converted_box_near_northern_limit_is_rejected():
    _, SizeUnit, convert, *_, EventErrorCode, EventOperationError = _api()

    with pytest.raises(EventOperationError) as captured:
        convert(
            center_lat=59.9,
            center_lon=76.0,
            width=10.0,
            height=30.0,
            unit=SizeUnit.KILOMETRES,
        )

    assert captured.value.code == EventErrorCode.OUTSIDE_CMORPH_COVERAGE


def test_event_id_is_deterministic_and_ignores_display_name():
    *_, event_id, _, validate, _, _ = _api()
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    first = validate(_request(event_name="Kerala rainfall"), now=now)
    second = validate(_request(event_name="A different display label"), now=now)

    assert event_id(first) == event_id(second)
    assert event_id(first).startswith("cmorph-custom-20240518T0000Z-10p50N-76p00E-")
    assert len(event_id(first).rsplit("-", 1)[-1]) == 8
