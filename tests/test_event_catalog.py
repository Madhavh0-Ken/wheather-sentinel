from pathlib import Path

from storm_nowcast.events.catalog import load_event_catalog


def test_event_catalog_records_real_demo_sources_frames_and_limitations():
    catalog = load_event_catalog(Path("configs/events.yaml"))
    event = catalog.get("cmorph-india-20230709T0000Z")

    assert event.frame_count == 12
    assert event.sources == ["NOAA CPC CMORPH V0.x RAW 8km-30min"]
    assert event.region == "Himachal Pradesh and nearby north-west India"
    assert event.data_path.as_posix().endswith("data/processed/cmorph_india_event.nc")
    assert any("one event" in item.lower() for item in event.limitations)
