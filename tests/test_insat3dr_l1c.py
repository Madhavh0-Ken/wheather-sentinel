from datetime import datetime, timezone

import h5py
import numpy as np
import pytest
from pyproj import CRS, Transformer

from storm_nowcast.config import Bounds
from storm_nowcast.data import satellite


def _write_l1c_fixture(
    path,
    *,
    processing_level="L1C",
    sensor_id="IMG",
    counts=None,
    include_wv=False,
    acquisition_start="09-07-2023T00:00:00",
    acquisition_end="09-07-2023T00:26:00",
):
    geographic = CRS.from_epsg(4326)
    mercator = CRS.from_proj4(
        "+proj=merc +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 +a=6378137 +b=6356752.314245 +units=m +no_defs"
    )
    forward = Transformer.from_crs(geographic, mercator, always_xy=True)
    x, _ = forward.transform(np.asarray([75.0, 76.0, 77.0]), np.zeros(3))
    _, y = forward.transform(np.zeros(3), np.asarray([32.0, 31.0, 30.0]))
    image_counts = np.asarray(
        counts
        if counts is not None
        else [[[400, 410, 420], [430, 1023, 450], [460, 470, 480]]],
        dtype=np.uint16,
    )
    temperature_lut = 180.0 + np.arange(1024, dtype=np.float32) / 10.0
    temperature_lut[1023] = 999.0

    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            {
                "conventions": "CF-1.6",
                "title": "3RIMG_09JUL2023_0000_L1C_ASIA_MER_V01R00",
                "source": "INSAT-3DR Imager (IMG)",
                "Satellite_Name": "INSAT-3DR",
                "Sensor_Id": sensor_id,
                "Sensor_Name": "IMAGER",
                "Processing_Level": processing_level,
                "Product_Type": "SECTOR",
                "Acquisition_Date": "09JUL2023",
                "Acquisition_Time_in_GMT": "0000",
                "Acquisition_Start_Time": acquisition_start,
                "Acquisition_End_Time": acquisition_end,
                "Product_Creation_Time": "2023-07-09T00:35:00",
                "HDF_Product_File_Name": path.name,
            }
        )
        handle.create_dataset("X", data=x).attrs.update(
            {"standard_name": "projection_x_coordinate", "units": "m"}
        )
        handle.create_dataset("Y", data=y).attrs.update(
            {"standard_name": "projection_y_coordinate", "units": "m"}
        )
        projection = handle.create_dataset("Projection_Information", data=np.asarray([0], dtype=np.int8))
        projection.attrs.update(
            {
                "grid_mapping_name": "mercator",
                "false_easting": 0.0,
                "false_northing": 0.0,
                "longitude_of_projection_origin": 0.0,
                "standard_parallel": 0.0,
                "semi_major_axis": 6378137.0,
                "semi_minor_axis": 6356752.314245,
            }
        )
        tir1 = handle.create_dataset("IMG_TIR1", data=image_counts)
        tir1.attrs.update(
            {
                "_FillValue": np.uint16(1023),
                "resolution": 4.0,
                "resolution_unit": "km",
                "grid_mapping": "Projection_Information",
                "bits_per_pixel": 10,
            }
        )
        tir1_lut = handle.create_dataset("IMG_TIR1_TEMP", data=temperature_lut)
        tir1_lut.attrs.update({"units": "K", "_FillValue": 999.0})
        if include_wv:
            wv = handle.create_dataset("IMG_WV", data=image_counts)
            wv.attrs.update(
                {
                    "_FillValue": np.uint16(1023),
                    "resolution": 8.0,
                    "resolution_unit": "km",
                    "grid_mapping": "Projection_Information",
                    "bits_per_pixel": 10,
                }
            )
            wv_lut = handle.create_dataset("IMG_WV_TEMP", data=temperature_lut + 5.0)
            wv_lut.attrs.update({"units": "K", "_FillValue": 1004.0})


def _reader():
    reader = getattr(satellite, "load_insat3dr_l1c_asia_mer", None)
    assert reader is not None, "product-specific INSAT-3DR L1C reader is missing"
    return reader


def test_l1c_reader_decodes_lut_geolocation_time_missing_values_and_lineage(tmp_path):
    path = tmp_path / "3RIMG_09JUL2023_0000_L1C_ASIA_MER_V01R00.h5"
    _write_l1c_fixture(path)

    product = _reader()(
        path,
        bounds=Bounds(min_lat=30.5, max_lat=32.5, min_lon=75.5, max_lon=77.5),
        is_synthetic=True,
    )

    field = product.dataset["infrared_brightness_temperature"]
    assert product.dataset.latitude.values == pytest.approx([31.0, 32.0], abs=1e-5)
    assert product.dataset.longitude.values == pytest.approx([76.0, 77.0], abs=1e-5)
    assert np.isnan(field.sel(latitude=31.0, longitude=76.0, method="nearest").item())
    assert field.sel(latitude=32.0, longitude=76.0, method="nearest").item() == pytest.approx(221.0)
    assert field.attrs["units"] == "K"
    assert product.temporal_support.observation_start == datetime(2023, 7, 9, tzinfo=timezone.utc)
    assert product.temporal_support.observation_end == datetime(2023, 7, 9, 0, 26, tzinfo=timezone.utc)
    lineage = product.lineage["infrared_brightness_temperature"]
    assert lineage.native_spatial_resolution.grid_spacing_km == 4.0
    assert lineage.native_temporal_resolution_minutes == 30.0
    assert "IMG_TIR1_TEMP" in " ".join(lineage.processing_steps)
    assert product.asset.sha256 and product.asset.is_synthetic is True
    assert product.asset.source.product == "3RIMG_L1C_ASIA_MER"


def test_l1c_reader_labels_wv_channel_as_brightness_temperature_not_humidity(tmp_path):
    path = tmp_path / "3RIMG_09JUL2023_0030_L1C_ASIA_MER_V01R00.h5"
    _write_l1c_fixture(path, include_wv=True)

    product = _reader()(
        path,
        bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
        is_synthetic=True,
    )

    assert "water_vapour_brightness_temperature" in product.dataset
    assert "water_vapour" not in product.dataset
    assert product.lineage["water_vapour_brightness_temperature"].native_spatial_resolution.grid_spacing_km == 8.0


def test_l1c_reader_parses_real_mosdac_acquisition_times_as_utc(tmp_path):
    path = tmp_path / "3RIMG_09JUL2023_2345_L1C_ASIA_MER_V01R00.h5"
    _write_l1c_fixture(
        path,
        acquisition_start="09-JUL-2023T23:45:28",
        acquisition_end="10-JUL-2023T00:12:22",
    )

    product = _reader()(
        path,
        bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
        is_synthetic=True,
    )

    assert product.temporal_support.observation_start == datetime(
        2023, 7, 9, 23, 45, 28, tzinfo=timezone.utc
    )
    assert product.temporal_support.observation_end == datetime(
        2023, 7, 10, 0, 12, 22, tzinfo=timezone.utc
    )


def test_l1c_reader_rejects_malformed_mosdac_acquisition_time(tmp_path):
    path = tmp_path / "malformed-acquisition-time.h5"
    _write_l1c_fixture(path, acquisition_start="31-FEB-2023T23:45:28")

    with pytest.raises(ValueError, match="Invalid Acquisition_Start_Time"):
        _reader()(
            path,
            bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
            is_synthetic=True,
        )


@pytest.mark.parametrize(
    ("processing_level", "sensor_id", "message"),
    [("L1B", "IMG", "L1C"), ("L1C", "SND", "Imager")],
)
def test_l1c_reader_rejects_wrong_product_before_emitting_values(
    tmp_path, processing_level, sensor_id, message
):
    path = tmp_path / "wrong-product.h5"
    _write_l1c_fixture(path, processing_level=processing_level, sensor_id=sensor_id)

    with pytest.raises(ValueError, match=message):
        _reader()(
            path,
            bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
            is_synthetic=True,
        )


def test_l1c_reader_rejects_non_fill_count_outside_temperature_lut(tmp_path):
    path = tmp_path / "bad-count.h5"
    _write_l1c_fixture(path, counts=[[[400, 410, 2048], [430, 440, 450], [460, 470, 480]]])

    with pytest.raises(ValueError, match="outside IMG_TIR1_TEMP lookup table"):
        _reader()(
            path,
            bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
            is_synthetic=True,
        )


def test_l1c_reader_requires_explicit_origin_confirmation_for_production_file(tmp_path):
    path = tmp_path / "3RIMG_09JUL2023_0100_L1C_ASIA_MER_V01R00.h5"
    _write_l1c_fixture(path)

    with pytest.raises(ValueError, match="confirmed_official_origin"):
        _reader()(
            path,
            bounds=Bounds(min_lat=29.0, max_lat=33.0, min_lon=74.0, max_lon=78.0),
        )
