from pathlib import Path

from storm_nowcast.events.catalog import load_event_catalog


def test_event_catalog_records_real_demo_sources_frames_and_limitations():
    catalog = load_event_catalog(Path("configs/events.yaml"))
    event = catalog.get("cmorph-india-20230709T0000Z")

    assert event.frame_count == 12
    assert event.sources == [
        "NOAA CPC CMORPH V0.x RAW 8km-30min",
        "ISRO/SAC MOSDAC INSAT-3DR 3RIMG_L1C_ASIA_MER",
    ]
    assert event.region == "Himachal Pradesh and nearby north-west India"
    assert event.data_path.as_posix().endswith("data/processed/cmorph_india_event.nc")
    assert event.insat_data_path.as_posix().endswith("data/processed/insat")
    assert event.insat_max_age_minutes == 30
    assert any("one event" in item.lower() for item in event.limitations)
    assert not any("no radar, lightning, satellite-channel" in item.lower() for item in event.limitations)
