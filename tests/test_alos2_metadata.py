from pathlib import Path

from iscewrap.alos2.metadata import parse_alos2_img_filename, get_alos2_multilook_from_mode


def test_parse_alos2_img_filename():
    info = parse_alos2_img_filename(
        Path("IMG-HH-ALOS2123456789-220406-FBD-example")
    )
    assert info["polarization"] == "HH"
    assert info["frame"] == "6789"
    assert info["date"] == "220406"
    assert info["mode"] == "FBD"


def test_get_alos2_multilook_from_mode():
    looks = get_alos2_multilook_from_mode("FBD")
    assert looks["number of range looks 1"] == 2
    assert looks["number of azimuth looks 1"] == 4
