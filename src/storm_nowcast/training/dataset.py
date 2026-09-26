from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import xarray as xr


DEFAULT_HISTORY_MINUTES = (120, 90, 60, 30, 0)
DEFAULT_LEAD_MINUTES = (30, 60, 120, 180, 360)


@dataclass(frozen=True)
class SampleMetadata:
    event_id: str
    analysis_time: np.datetime64
    history_times: tuple[np.datetime64, ...]
    target_time: np.datetime64


@dataclass(frozen=True)
class HorizonDataset:
    variable: str
    lead_minutes: int
    history_offsets_minutes: tuple[int, ...]
    inputs: np.ndarray
    targets: np.ndarray
    samples: tuple[SampleMetadata, ...]
    spatial_dims: tuple[str, str]
    spatial_coordinates: tuple[np.ndarray, np.ndarray]
    is_synthetic: bool = False

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    def to_xarray(self) -> xr.Dataset:
        first_dim, second_dim = self.spatial_dims
        first_coordinate, second_coordinate = self.spatial_coordinates
        history_times = np.asarray(
            [sample.history_times for sample in self.samples],
            dtype="datetime64[ns]",
        ).reshape(self.sample_count, len(self.history_offsets_minutes))
        dataset = xr.Dataset(
            {
                "inputs": (
                    ("sample", "history_step", first_dim, second_dim),
                    self.inputs,
                ),
                "target": (("sample", first_dim, second_dim), self.targets),
            },
            coords={
                "sample": np.arange(self.sample_count),
                "history_step": np.arange(len(self.history_offsets_minutes)),
                "history_offset_minutes": (
                    "history_step",
                    -np.asarray(self.history_offsets_minutes, dtype=np.int32),
                ),
                first_dim: first_coordinate,
                second_dim: second_coordinate,
                "event_id": (
                    "sample",
                    np.asarray([sample.event_id for sample in self.samples], dtype=str),
                ),
                "analysis_time": (
                    "sample",
                    np.asarray([sample.analysis_time for sample in self.samples], dtype="datetime64[ns]"),
                ),
                "target_time": (
                    "sample",
                    np.asarray([sample.target_time for sample in self.samples], dtype="datetime64[ns]"),
                ),
                "history_time": (("sample", "history_step"), history_times),
            },
            attrs={
                "source_variable": self.variable,
                "lead_minutes": self.lead_minutes,
                "sample_count": self.sample_count,
                "history_offsets_minutes": ",".join(
                    str(value) for value in self.history_offsets_minutes
                ),
                "sample_policy": "exact timestamps within one event; no interpolation",
                "is_synthetic": int(self.is_synthetic),
            },
        )
        dataset.inputs.attrs["variable_status"] = "OBSERVED_HISTORY"
        dataset.target.attrs["variable_status"] = "OBSERVED_FUTURE_TARGET"
        return dataset


@dataclass(frozen=True)
class EventSplit:
    train_events: tuple[str, ...]
    validation_events: tuple[str, ...]
    test_events: tuple[str, ...]

    def __post_init__(self) -> None:
        groups = (set(self.train_events), set(self.validation_events), set(self.test_events))
        if not all(groups):
            raise ValueError("Train, validation, and test event groups must all be non-empty")
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("Train, validation, and test event groups must be disjoint")


@dataclass(frozen=True)
class NormalizationStats:
    mean: float
    standard_deviation: float
    fitted_event_ids: tuple[str, ...]
    input_variable: str


def _event_time_bounds(dataset: xr.Dataset) -> tuple[np.datetime64, np.datetime64]:
    if "time" not in dataset.coords or dataset.sizes.get("time", 0) == 0:
        raise ValueError("Every training event requires a non-empty time coordinate")
    times = np.asarray(dataset.time.values, dtype="datetime64[ns]")
    if np.any(np.isnat(times)) or np.any(times[1:] <= times[:-1]):
        raise ValueError("Event times must be valid, unique, and strictly increasing")
    return times[0], times[-1]


def _event_field(dataset: xr.Dataset, variable: str) -> tuple[xr.DataArray, tuple[str, str]]:
    if variable not in dataset:
        raise ValueError(f"Training variable is absent: {variable}")
    field = dataset[variable]
    if "time" not in field.dims or len(field.dims) != 3:
        raise ValueError(f"{variable} must have time plus exactly two spatial dimensions")
    spatial_dims = tuple(dimension for dimension in field.dims if dimension != "time")
    return field.transpose("time", *spatial_dims), (spatial_dims[0], spatial_dims[1])


def build_horizon_datasets(
    events: Mapping[str, xr.Dataset],
    *,
    variable: str,
    history_offsets_minutes: Sequence[int] = DEFAULT_HISTORY_MINUTES,
    lead_minutes: Sequence[int] = DEFAULT_LEAD_MINUTES,
    allow_synthetic: bool = False,
) -> dict[int, HorizonDataset]:
    if not events:
        raise ValueError("At least one event dataset is required")
    history = tuple(int(value) for value in history_offsets_minutes)
    leads = tuple(int(value) for value in lead_minutes)
    if not history or history[-1] != 0 or any(value < 0 for value in history):
        raise ValueError("History offsets must be non-negative lookback minutes ending at 0")
    if any(history[index] <= history[index + 1] for index in range(len(history) - 1)):
        raise ValueError("History offsets must be strictly decreasing toward 0")
    if not leads or any(value <= 0 for value in leads) or len(set(leads)) != len(leads):
        raise ValueError("Forecast leads must be unique positive minutes")

    ordered_events = sorted(events.items(), key=lambda item: _event_time_bounds(item[1])[0])
    input_lists: dict[int, list[np.ndarray]] = {lead: [] for lead in leads}
    target_lists: dict[int, list[np.ndarray]] = {lead: [] for lead in leads}
    sample_lists: dict[int, list[SampleMetadata]] = {lead: [] for lead in leads}
    expected_dims: tuple[str, str] | None = None
    expected_coordinates: tuple[np.ndarray, np.ndarray] | None = None
    event_synthetic_states: list[bool] = []

    for event_id, dataset in ordered_events:
        declared_id = dataset.attrs.get("event_id")
        if declared_id is not None and str(declared_id) != event_id:
            raise ValueError(f"Event key {event_id!r} does not match dataset event_id {declared_id!r}")
        is_synthetic = bool(dataset.attrs.get("is_synthetic", False))
        if is_synthetic and not allow_synthetic:
            raise ValueError("synthetic event data are allowed only with explicit test-only opt-in")
        event_synthetic_states.append(is_synthetic)
        field, spatial_dims = _event_field(dataset, variable)
        coordinates = (
            np.asarray(dataset.coords[spatial_dims[0]].values),
            np.asarray(dataset.coords[spatial_dims[1]].values),
        )
        if expected_dims is None:
            expected_dims = spatial_dims
            expected_coordinates = coordinates
        elif spatial_dims != expected_dims or any(
            not np.array_equal(current, expected)
            for current, expected in zip(coordinates, expected_coordinates or ())
        ):
            raise ValueError("All training events must share the same spatial grid before sampling")
        times = np.asarray(field.time.values, dtype="datetime64[ns]")
        _event_time_bounds(dataset)
        time_to_index = {timestamp: index for index, timestamp in enumerate(times)}
        values = np.asarray(field.values)
        for analysis_time in times:
            history_times = tuple(
                analysis_time - np.timedelta64(offset, "m") for offset in history
            )
            if any(timestamp not in time_to_index for timestamp in history_times):
                continue
            history_values = np.stack([values[time_to_index[timestamp]] for timestamp in history_times])
            for lead in leads:
                target_time = analysis_time + np.timedelta64(lead, "m")
                if target_time not in time_to_index:
                    continue
                input_lists[lead].append(history_values.copy())
                target_lists[lead].append(values[time_to_index[target_time]].copy())
                sample_lists[lead].append(
                    SampleMetadata(
                        event_id=event_id,
                        analysis_time=analysis_time,
                        history_times=history_times,
                        target_time=target_time,
                    )
                )

    assert expected_dims is not None and expected_coordinates is not None
    spatial_shape = tuple(len(coordinate) for coordinate in expected_coordinates)
    output: dict[int, HorizonDataset] = {}
    for lead in leads:
        inputs = (
            np.stack(input_lists[lead])
            if input_lists[lead]
            else np.empty((0, len(history), *spatial_shape), dtype=float)
        )
        targets = (
            np.stack(target_lists[lead])
            if target_lists[lead]
            else np.empty((0, *spatial_shape), dtype=float)
        )
        output[lead] = HorizonDataset(
            variable=variable,
            lead_minutes=lead,
            history_offsets_minutes=history,
            inputs=inputs,
            targets=targets,
            samples=tuple(sample_lists[lead]),
            spatial_dims=expected_dims,
            spatial_coordinates=expected_coordinates,
            is_synthetic=all(event_synthetic_states),
        )
    return output


def chronological_event_split(
    events: Mapping[str, xr.Dataset],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> EventSplit:
    if len(events) < 3:
        raise ValueError("At least three independent events are required for train/validation/test splits")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("Split fractions must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must leave a non-empty test fraction")
    ordered = sorted(
        ((event_id, *_event_time_bounds(dataset)) for event_id, dataset in events.items()),
        key=lambda item: item[1],
    )
    for previous, current in zip(ordered, ordered[1:]):
        if current[1] <= previous[2]:
            raise ValueError(
                f"Training events overlap in time: {previous[0]} and {current[0]}"
            )
    count = len(ordered)
    train_count = max(1, int(np.floor(count * train_fraction)))
    validation_count = max(1, int(np.floor(count * validation_fraction)))
    if train_count + validation_count >= count:
        train_count = count - validation_count - 1
    identifiers = tuple(item[0] for item in ordered)
    return EventSplit(
        train_events=identifiers[:train_count],
        validation_events=identifiers[train_count : train_count + validation_count],
        test_events=identifiers[train_count + validation_count :],
    )


def fit_training_normalization(
    dataset: HorizonDataset,
    split: EventSplit,
) -> NormalizationStats:
    train_ids = set(split.train_events)
    mask = np.asarray([sample.event_id in train_ids for sample in dataset.samples], dtype=bool)
    if not np.any(mask):
        raise ValueError("No horizon samples belong to the requested training events")
    training_inputs = np.asarray(dataset.inputs[mask], dtype=float)
    finite = training_inputs[np.isfinite(training_inputs)]
    if finite.size == 0:
        raise ValueError("Training inputs contain no finite values for normalization")
    standard_deviation = float(np.std(finite))
    if standard_deviation == 0.0:
        standard_deviation = 1.0
    return NormalizationStats(
        mean=float(np.mean(finite)),
        standard_deviation=standard_deviation,
        fitted_event_ids=split.train_events,
        input_variable=dataset.variable,
    )
