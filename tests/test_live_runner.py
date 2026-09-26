from datetime import datetime, timedelta, timezone

from storm_nowcast.live.runner import LiveFrame, LiveRunner


class SequenceProvider:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def fetch_latest(self, after=None):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value


def test_live_runner_ignores_duplicate_and_late_frames():
    base = datetime(2023, 7, 9, tzinfo=timezone.utc)
    provider = SequenceProvider(
        [
            LiveFrame(source="satellite", timestamp=base, payload_ref="one"),
            LiveFrame(source="satellite", timestamp=base, payload_ref="duplicate"),
            LiveFrame(source="satellite", timestamp=base - timedelta(minutes=10), payload_ref="late"),
        ]
    )
    runner = LiveRunner({"satellite": provider}, retry_attempts=1, minimum_poll_interval_seconds=0)

    assert len(runner.poll_once(now=base).accepted_frames) == 1
    assert runner.poll_once(now=base + timedelta(minutes=1)).accepted_frames == []
    third = runner.poll_once(now=base + timedelta(minutes=2))
    assert third.accepted_frames == []
    assert third.sources["satellite"].last_observation_time == base
    assert third.sources["satellite"].status == "CURRENT"


def test_live_runner_retries_then_uses_timestamped_stale_cache():
    base = datetime(2023, 7, 9, tzinfo=timezone.utc)
    provider = SequenceProvider(
        [
            LiveFrame(source="radar", timestamp=base, payload_ref="cached"),
            RuntimeError("provider unavailable"),
            RuntimeError("provider unavailable"),
        ]
    )
    runner = LiveRunner(
        {"radar": provider}, retry_attempts=2, stale_after_minutes=30, minimum_poll_interval_seconds=0
    )
    runner.poll_once(now=base)

    result = runner.poll_once(now=base + timedelta(minutes=20))

    assert result.sources["radar"].status == "STALE_CACHE"
    assert result.sources["radar"].last_observation_time == base
    assert result.sources["radar"].error == "provider unavailable"
    assert provider.calls == 3
