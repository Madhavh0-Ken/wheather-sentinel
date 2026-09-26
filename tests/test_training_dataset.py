from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import xarray as xr


def _event(
    event_id: str,
    start: datetime,
    *,
    frames: int = 12,
    base_value: float = 0.0,
    missing_index: int | None = None,
) -> xr.Dataset:
    times = [start + timedelta(minutes=30 * index) for index in range(frames)]
    if missing_index is not None:
        times.pop(missing_index)
    values = np.stack(
        [np.full((2, 3), base_value + index, dtype=np.float32) for index in range(len(times))]
    )
    return xr.Dataset(
        {"rain_rate": (("time", "latitude", "longitude"), values)},
        coords={
            "time": np.asarray(
                [timestamp.replace(tzinfo=None) for timestamp in times], dtype="datetime64[ns]"
            ),
            "latitude": [30.0, 31.0],
            "longitude": [75.0, 76.0, 77.0],
        },
        attrs={"event_id": event_id, "is_synthetic": 1},
    )


def _training_api():
    try:
        from storm_nowcast.training.dataset import (
            EventSplit,
            build_horizon_datasets,
            chronological_event_split,
            fit_training_normalization,
        )
    except ModuleNotFoundError:
        pytest.fail("storm_nowcast.training.dataset is missing")
    return EventSplit, build_horizon_datasets, chronological_event_split, fit_training_normalization


def test_horizon_dataset_uses_exact_causal_history_and_future_target_with_expected_counts():
    _, build, _, _ = _training_api()
    start = datetime(2023, 7, 9, tzinfo=timezone.utc)

    horizons = build(
        {"event-a": _event("event-a", start)},
        variable="rain_rate",
        allow_synthetic=True,
    )

    assert {lead: item.sample_count for lead, item in horizons.items()} == {
        30: 7,
        60: 6,
        120: 4,
        180: 2,
        360: 0,
    }
    first = horizons[30]
    assert first.inputs[0, :, 0, 0].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert first.targets[0, 0, 0] == 5.0
    assert first.samples[0].analysis_time == np.datetime64("2023-07-09T02:00:00")
    assert first.samples[0].target_time == np.datetime64("2023-07-09T02:30:00")
    assert all(time <= first.samples[0].analysis_time for time in first.samples[0].history_times)
    assert first.samples[0].target_time > first.samples[0].analysis_time


def test_missing_exact_history_timestamp_skips_samples_instead_of_interpolating():
    _, build, _, _ = _training_api()
    dataset = _event(
        "event-gap",
        datetime(2023, 7, 9, tzinfo=timezone.utc),
        missing_index=2,
    )

    horizon = build(
        {"event-gap": dataset},
        variable="rain_rate",
        lead_minutes=(30,),
        allow_synthetic=True,
    )[30]

    available = set(dataset.time.values.astype("datetime64[ns]"))
    assert 0 < horizon.sample_count < 7
    assert all(set(sample.history_times).issubset(available) for sample in horizon.samples)
    assert all(sample.target_time in available for sample in horizon.samples)


def test_samples_never_cross_event_boundaries_and_export_truthful_metadata():
    _, build, _, _ = _training_api()
    first_start = datetime(2023, 7, 1, tzinfo=timezone.utc)
    second_start = datetime(2023, 7, 3, tzinfo=timezone.utc)
    horizons = build(
        {
            "event-a": _event("event-a", first_start, frames=6, base_value=10),
            "event-b": _event("event-b", second_start, frames=6, base_value=50),
        },
        variable="rain_rate",
        lead_minutes=(30,),
        allow_synthetic=True,
    )

    horizon = horizons[30]
    assert [sample.event_id for sample in horizon.samples] == ["event-a", "event-b"]
    assert horizon.inputs[0].max() < horizon.inputs[1].min()
    exported = horizon.to_xarray()
    assert exported.inputs.dims == ("sample", "history_step", "latitude", "longitude")
    assert exported.target.dims == ("sample", "latitude", "longitude")
    assert exported.event_id.values.tolist() == ["event-a", "event-b"]
    assert exported.attrs["sample_count"] == 2
    assert exported.attrs["lead_minutes"] == 30


def test_chronological_split_assigns_whole_events_and_rejects_overlap():
    _, _, split_events, _ = _training_api()
    base = datetime(2023, 1, 1, tzinfo=timezone.utc)
    events = {
        f"event-{index}": _event(f"event-{index}", base + timedelta(days=index * 2), frames=6)
        for index in range(5)
    }

    split = split_events(events)

    assert split.train_events == ("event-0", "event-1", "event-2")
    assert split.validation_events == ("event-3",)
    assert split.test_events == ("event-4",)
    assert set(split.train_events).isdisjoint(split.validation_events + split.test_events)

    overlapping = {
        "event-a": _event("event-a", base, frames=6),
        "event-b": _event("event-b", base + timedelta(hours=2), frames=6),
        "event-c": _event("event-c", base + timedelta(days=2), frames=6),
    }
    with pytest.raises(ValueError, match="overlap"):
        split_events(overlapping)


def test_training_normalization_excludes_targets_validation_and_test_events():
    EventSplit, build, _, fit_normalization = _training_api()
    base = datetime(2023, 1, 1, tzinfo=timezone.utc)
    events = {
        "train": _event("train", base, frames=6, base_value=1),
        "validation": _event("validation", base + timedelta(days=2), frames=6, base_value=100),
        "test": _event("test", base + timedelta(days=4), frames=6, base_value=200),
    }
    horizon = build(
        events,
        variable="rain_rate",
        lead_minutes=(30,),
        allow_synthetic=True,
    )[30]
    split = EventSplit(
        train_events=("train",),
        validation_events=("validation",),
        test_events=("test",),
    )

    stats = fit_normalization(horizon, split)

    assert stats.mean == pytest.approx(3.0)
    assert stats.standard_deviation == pytest.approx(np.std([1, 2, 3, 4, 5]))
    assert stats.fitted_event_ids == ("train",)


def test_synthetic_event_requires_explicit_test_only_opt_in():
    _, build, _, _ = _training_api()
    with pytest.raises(ValueError, match="synthetic"):
        build(
            {"event-a": _event("event-a", datetime(2023, 7, 9, tzinfo=timezone.utc))},
            variable="rain_rate",
        )


def test_mixed_fixture_export_is_marked_synthetic_if_any_event_is_synthetic():
    _, build, _, _ = _training_api()
    base = datetime(2023, 7, 9, tzinfo=timezone.utc)
    real_event = _event("real-event", base, frames=6)
    real_event.attrs["is_synthetic"] = 0
    synthetic_event = _event("synthetic-event", base + timedelta(days=2), frames=6)

    horizon = build(
        {"real-event": real_event, "synthetic-event": synthetic_event},
        variable="rain_rate",
        lead_minutes=(30,),
        allow_synthetic=True,
    )[30]

    assert horizon.to_xarray().attrs["is_synthetic"] == 1
