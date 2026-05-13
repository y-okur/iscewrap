
from pathlib import Path

from iscewrap.alos2.workflow import (
    _parse_reference_bounding_box_from_log,
    _create_empty_dem_files_from_bounding_box,
)


def test_parse_reference_bounding_box_from_log(tmp_path):
    log = tmp_path / "alos2App_full_terminal.log"
    log.write_text(
        "something\n"
        "runBaseline.reference bounding box = [-7.9500308685499395, -7.188338323611367, 110.22857805247759, 111.04552250189458]\n"
    )

    bbox = _parse_reference_bounding_box_from_log(log)

    assert bbox == [
        -7.9500308685499395,
        -7.188338323611367,
        110.22857805247759,
        111.04552250189458,
    ]


def test_create_empty_dem_files_from_bounding_box(tmp_path):
    bbox = [-7.9500308685499395, -7.188338323611367, 110.22857805247759, 111.04552250189458]
    result = _create_empty_dem_files_from_bounding_box(bbox, tmp_path)

    assert result["extent"] == {
        "south": -8,
        "north": -7,
        "west": 110,
        "east": 112,
    }

    dem1 = result["dem_1_arcsec"]
    dem3 = result["dem_3_arcsec"]
    wbd = result["wbd_1_arcsec"]

    assert dem1.exists()
    assert dem3.exists()
    assert wbd.exists()
    assert Path(str(dem1) + ".xml").exists()
    assert Path(str(dem1) + ".vrt").exists()
    assert Path(str(dem3) + ".xml").exists()
    assert Path(str(dem3) + ".vrt").exists()
    assert Path(str(wbd) + ".xml").exists()
    assert Path(str(wbd) + ".vrt").exists()

    assert dem1.stat().st_size == 7200 * 3600 * 2
    assert dem3.stat().st_size == 2400 * 1200 * 2
    assert wbd.stat().st_size == 7200 * 3600

    with open(wbd, "rb") as f:
        assert f.read(10) == bytes([1]) * 10

    xml_text = Path(str(dem1) + ".xml").read_text()
    vrt_text = Path(str(wbd) + ".vrt").read_text()

    assert "demLat_S08_S07_Lon_E110_E112.dem.wgs84" in xml_text
    assert "swbdLat_S08_S07_Lon_E110_E112.wbd" in vrt_text
