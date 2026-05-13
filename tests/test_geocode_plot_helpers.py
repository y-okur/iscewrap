
from pathlib import Path

import numpy as np

from iscewrap.alos2 import (
    geocode_raster,
    plot_dem_comparison,
    read_isce_raster,
    write_isce_geocoded_float,
)


def write_xml(path, width, length, data_type="FLOAT", number_bands=1, scheme="BIP"):
    Path(str(path) + ".xml").write_text(
        f"""<imageFile>
        <property name="width"><value>{width}</value></property>
        <property name="length"><value>{length}</value></property>
        <property name="data_type"><value>{data_type}</value></property>
        <property name="number_bands"><value>{number_bands}</value></property>
        <property name="scheme"><value>{scheme}</value></property>
        </imageFile>"""
    )


def test_write_isce_geocoded_float(tmp_path):
    arr = np.arange(12, dtype=np.float32).reshape(3, 4)
    out = tmp_path / "geo.dem"

    result = write_isce_geocoded_float(
        output_file=out,
        array=arr,
        lon_min=100.0,
        lat_max=10.0,
        resolution=1 / 3600,
    )

    assert result["output_file"].exists()
    assert result["xml_file"].exists()
    assert result["vrt_file"].exists()

    reread = read_isce_raster(out)
    assert reread.shape == arr.shape
    assert np.allclose(reread, arr)


def test_geocode_raster_small_nearest(tmp_path):
    length, width = 4, 5
    data = np.arange(length * width, dtype=np.float32).reshape(length, width)
    lat = np.linspace(10.0, 9.9, length, dtype=np.float32)[:, None] * np.ones((1, width), dtype=np.float32)
    lon = np.ones((length, 1), dtype=np.float32) * np.linspace(100.0, 100.1, width, dtype=np.float32)[None, :]

    data_file = tmp_path / "data.dem"
    lat_file = tmp_path / "lat.rdr"
    lon_file = tmp_path / "lon.rdr"

    data.tofile(data_file)
    lat.tofile(lat_file)
    lon.tofile(lon_file)

    write_xml(data_file, width, length)
    write_xml(lat_file, width, length)
    write_xml(lon_file, width, length)

    out = tmp_path / "data_geo.dem"

    result = geocode_raster(
        input_file=data_file,
        lat_file=lat_file,
        lon_file=lon_file,
        output_file=out,
        resolution=0.05,
        method="nearest",
    )

    assert out.exists()
    assert Path(str(out) + ".xml").exists()
    assert Path(str(out) + ".vrt").exists()
    assert len(result["shape"]) == 2
