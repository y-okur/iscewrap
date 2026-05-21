from pathlib import Path
import zipfile

import numpy as np

from iscewrap.geo import geo_to_kml, read_geo_extent
from iscewrap.alos2.workflow import write_isce_geocoded_float


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
