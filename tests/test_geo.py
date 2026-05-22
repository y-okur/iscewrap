from pathlib import Path
import zipfile

import numpy as np

from iscewrap.geo import geo_to_kml, read_geo_extent
from iscewrap.plot import (
    infer_isce_product_kind,
    is_isce_amplitude_band,
    prepare_plot_values,
)
from iscewrap.alos2.workflow import (
    geocode_raster,
    read_isce_raster,
    read_isce_raster_metadata,
    write_isce_geocoded_float,
    write_isce_geocoded_raster,
)


def test_geo_to_kml_writes_ground_overlay(tmp_path):
    raster = tmp_path / "sample.geo"
    write_isce_geocoded_float(
        output_file=raster,
        array=np.arange(12, dtype=np.float32).reshape(3, 4),
        lon_min=10.0,
        lat_max=20.0,
        resolution=0.1,
    )

    result = geo_to_kml(raster, tmp_path / "sample.kml", alpha=0.5)

    kml_text = result["kml_file"].read_text()
    assert result["png_file"].exists()
    assert "<GroundOverlay>" in kml_text
    assert "<north>20.0</north>" in kml_text
    assert "<south>19.7</south>" in kml_text
    assert "<east>10.4</east>" in kml_text
    assert "<west>10.0</west>" in kml_text


def test_geo_to_kmz_packages_kml_and_png(tmp_path):
    raster = tmp_path / "sample.geo"
    write_isce_geocoded_float(
        output_file=raster,
        array=np.ones((2, 2), dtype=np.float32),
        lon_min=-1.0,
        lat_max=2.0,
        resolution=0.25,
    )

    result = geo_to_kml(raster, tmp_path / "sample.kmz")

    with zipfile.ZipFile(result["kml_file"]) as zf:
        names = set(zf.namelist())
        assert "doc.kml" in names
        assert result["png_file"].name in names


def test_read_geo_extent_from_xml_when_vrt_missing(tmp_path):
    raster = tmp_path / "sample.geo"
    write_isce_geocoded_float(
        output_file=raster,
        array=np.ones((2, 2), dtype=np.float32),
        lon_min=100.0,
        lat_max=40.0,
        resolution=0.5,
    )
    Path(str(raster) + ".vrt").unlink()

    assert read_geo_extent(raster) == {
        "west": 100.0,
        "east": 101.0,
        "south": 39.0,
        "north": 40.0,
    }


def test_geocode_raster_preserves_two_band_input_by_default(tmp_path):
    raster = tmp_path / "two_band.rdr"
    lat = tmp_path / "lat.rdr"
    lon = tmp_path / "lon.rdr"
    output = tmp_path / "two_band.geo"

    band0 = np.arange(6, dtype=np.float32).reshape(2, 3)
    band1 = band0 + 100.0
    write_isce_geocoded_raster(
        output_file=raster,
        array=np.stack([band0, band1], axis=0),
        lon_min=139.0,
        lat_max=36.0,
        resolution=0.01,
    )
    write_isce_geocoded_float(lat, np.array([[36.0, 36.0, 36.0], [35.99, 35.99, 35.99]], dtype=np.float32), 139.0, 36.0, 0.01)
    write_isce_geocoded_float(lon, np.array([[139.0, 139.01, 139.02], [139.0, 139.01, 139.02]], dtype=np.float32), 139.0, 36.0, 0.01)

    result = geocode_raster(
        input_file=raster,
        lat_file=lat,
        lon_file=lon,
        output_file=output,
        resolution=0.01,
        method="nearest",
        verbose=False,
    )

    meta = read_isce_raster_metadata(output)
    data = read_isce_raster(output)

    assert result["number_bands"] == 2
    assert result["scheme"] == "BSQ"
    assert meta["number_bands"] == 2
    assert data.shape[0] == 2


def test_geocode_raster_can_select_one_band(tmp_path):
    raster = tmp_path / "two_band.rdr"
    lat = tmp_path / "lat.rdr"
    lon = tmp_path / "lon.rdr"
    output = tmp_path / "band1.geo"

    band0 = np.arange(6, dtype=np.float32).reshape(2, 3)
    band1 = band0 + 100.0
    write_isce_geocoded_raster(
        output_file=raster,
        array=np.stack([band0, band1], axis=0),
        lon_min=139.0,
        lat_max=36.0,
        resolution=0.01,
    )
    write_isce_geocoded_float(lat, np.array([[36.0, 36.0, 36.0], [35.99, 35.99, 35.99]], dtype=np.float32), 139.0, 36.0, 0.01)
    write_isce_geocoded_float(lon, np.array([[139.0, 139.01, 139.02], [139.0, 139.01, 139.02]], dtype=np.float32), 139.0, 36.0, 0.01)

    result = geocode_raster(
        input_file=raster,
        lat_file=lat,
        lon_file=lon,
        output_file=output,
        resolution=0.01,
        method="nearest",
        band=1,
        verbose=False,
    )

    meta = read_isce_raster_metadata(output)
    data = read_isce_raster(output)

    assert result["number_bands"] == 1
    assert result["band"] == 1
    assert meta["number_bands"] == 1
    assert data.ndim == 2
    assert np.nanmax(data) >= 100.0


def test_geocode_raster_preserves_complex_input(tmp_path):
    raster = tmp_path / "complex.rdr"
    lat = tmp_path / "lat.rdr"
    lon = tmp_path / "lon.rdr"
    output = tmp_path / "complex.geo"

    data = (
        np.arange(6, dtype=np.float32).reshape(2, 3)
        + 1j * np.arange(10, 16, dtype=np.float32).reshape(2, 3)
    )
    write_isce_geocoded_raster(
        output_file=raster,
        array=data,
        lon_min=139.0,
        lat_max=36.0,
        resolution=0.01,
    )
    write_isce_geocoded_float(lat, np.array([[36.0, 36.0, 36.0], [35.99, 35.99, 35.99]], dtype=np.float32), 139.0, 36.0, 0.01)
    write_isce_geocoded_float(lon, np.array([[139.0, 139.01, 139.02], [139.0, 139.01, 139.02]], dtype=np.float32), 139.0, 36.0, 0.01)

    result = geocode_raster(
        input_file=raster,
        lat_file=lat,
        lon_file=lon,
        output_file=output,
        resolution=0.01,
        method="nearest",
        verbose=False,
    )

    meta = read_isce_raster_metadata(output)
    geocoded = read_isce_raster(output)

    assert result["data_type"] == "CFLOAT"
    assert meta["data_type"] == "CFLOAT"
    assert np.iscomplexobj(geocoded)


def test_infer_isce_amplitude_products():
    assert infer_isce_product_kind("foo.amp") == "amp"
    assert infer_isce_product_kind("foo.amp.geo") == "amp"
    assert infer_isce_product_kind("foo.cor.geo.vrt") == "cor"
    assert infer_isce_product_kind("foo.hgt") == "hgt"
    assert infer_isce_product_kind("foo.unw.geo") == "unw"
    assert infer_isce_product_kind("foo_msk.unw.geo") == "msk.unw"


def test_isce_amplitude_band_rules():
    assert is_isce_amplitude_band("foo.amp.geo", 1)
    assert is_isce_amplitude_band("foo.amp.geo", 2)
    assert is_isce_amplitude_band("foo.cor.geo", 1)
    assert not is_isce_amplitude_band("foo.cor.geo", 2)
    assert is_isce_amplitude_band("foo.hgt.geo", 1)
    assert not is_isce_amplitude_band("foo.hgt.geo", 2)
    assert is_isce_amplitude_band("foo.unw.geo", 1)
    assert not is_isce_amplitude_band("foo.unw.geo", 2)
    assert is_isce_amplitude_band("foo_msk.unw.geo", 1)
    assert not is_isce_amplitude_band("foo_msk.unw.geo", 2)


def test_prepare_plot_values_auto_log_scales_amplitude_band():
    data = np.array([[1.0, 10.0, 100.0]], dtype=np.float32)

    scaled, scale = prepare_plot_values(
        data,
        input_file="foo.unw.geo",
        band=1,
        amplitude_scale="auto",
    )
    unscaled, unscaled_mode = prepare_plot_values(
        data,
        input_file="foo.unw.geo",
        band=2,
        amplitude_scale="auto",
    )

    assert scale == "log"
    assert np.allclose(scaled, [[0.0, 1.0, 2.0]])
    assert unscaled_mode == "linear"
    assert np.array_equal(unscaled, data)
