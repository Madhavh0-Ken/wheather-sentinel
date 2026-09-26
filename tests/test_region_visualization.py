from storm_nowcast.config import Bounds
from storm_nowcast.visualization.region import build_region_preview, map_view


def test_region_preview_draws_requested_outline_and_center():
    bounds = Bounds(min_lat=8.0, max_lat=12.0, min_lon=74.0, max_lon=78.0)

    figure = build_region_preview(bounds)

    assert figure.data[0].name == "REQUESTED REGION"
    assert list(figure.data[0].lat) == [8.0, 8.0, 12.0, 12.0, 8.0]
    assert list(figure.data[1].lat) == [10.0]
    assert list(figure.data[1].lon) == [76.0]
    assert figure.layout.map.center.lat == 10.0
    assert figure.layout.map.center.lon == 76.0


def test_map_view_zooms_out_as_region_span_grows():
    small = Bounds(min_lat=10.0, max_lat=11.0, min_lon=75.0, max_lon=76.0)
    large = Bounds(min_lat=0.0, max_lat=20.0, min_lon=65.0, max_lon=85.0)

    assert map_view(small)["zoom"] > map_view(large)["zoom"]
