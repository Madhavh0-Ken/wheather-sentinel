import json

from scripts.prepare_custom_event import main
from tests.test_event_builder import event_request, make_builder


def test_cli_delegates_explicit_region_and_window_to_builder(tmp_path, capsys):
    builder, _, _, _ = make_builder(tmp_path)
    request = event_request()

    exit_code = main(
        [
            "--min-lat", str(request.min_lat), "--max-lat", str(request.max_lat),
            "--min-lon", str(request.min_lon), "--max-lon", str(request.max_lon),
            "--start", request.start_time.isoformat(), "--end", request.end_time.isoformat(),
            "--name", "CLI event", "--offline",
        ],
        builder=builder,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["manifest"]["display_name"] == "CLI event"
    assert payload["manifest"]["frame_count"] == 3
    assert payload["created"] is True
