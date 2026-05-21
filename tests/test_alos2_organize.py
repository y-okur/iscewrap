from pathlib import Path
import zipfile

from iscewrap.alos2 import (
    extract_alos2_zip,
    organize_alos2_stripmap_zips,
    parse_alos2_stripmap_zip_name,
)
from iscewrap.alos2.workflow import _select_alos2_processing_dir


def _make_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def test_parse_alos2_stripmap_zip_name():
    product = parse_alos2_stripmap_zip_name("24-3390-RF2_6-20160326_+2.zip")

    assert product.path == "24"
    assert product.frame == "3390"
    assert product.mode == "RF2"
    assert product.beam == "6"
    assert product.date == "20160326"
    assert product.suffix == "_+2"
    assert product.group_name == "path_24/RF2_6"


def test_organize_alos2_stripmap_zips_groups_frames_by_date(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _make_zip(zip_dir / "24-3390-RF2_6-20160326_+2.zip", {"IMG-3390": "a"})
    _make_zip(zip_dir / "24-3400-RF2_6-20160326.zip", {"IMG-3400": "b"})
    _make_zip(zip_dir / "24-3390-RF2_6-20160604_+2.zip", {"IMG-3390": "c"})

    groups = organize_alos2_stripmap_zips(zip_dir, tmp_path / "organized")

    date_20160326 = groups["path_24/RF2_6"]["dates"]["20160326"]
    date_20160604 = groups["path_24/RF2_6"]["dates"]["20160604"]

    assert date_20160326["frames"] == ["3390", "3400"]
    assert date_20160604["frames"] == ["3390"]
    assert (date_20160326["date_dir"] / "IMG-3390").read_text() == "a"
    assert (date_20160326["date_dir"] / "IMG-3400").read_text() == "b"


def test_extract_alos2_zip_filters_polarization_files(tmp_path):
    zip_file = tmp_path / "24-3390-RF2_6-20160326_+2.zip"
    _make_zip(
        zip_file,
        {
            "IMG-HH-ALOS20243390-160326-RF2": "hh",
            "IMG-HV-ALOS20243390-160326-RF2": "hv",
            "LED-ALOS20243390-160326-RF2": "leader",
        },
    )

    extract_dir = extract_alos2_zip(zip_file, tmp_path / "raw", polarizations="HH")

    assert (extract_dir / "IMG-HH-ALOS20243390-160326-RF2").exists()
    assert not (extract_dir / "IMG-HV-ALOS20243390-160326-RF2").exists()
    assert (extract_dir / "LED-ALOS20243390-160326-RF2").exists()


def test_organize_alos2_stripmap_zips_filters_polarization_files(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _make_zip(
        zip_dir / "24-3390-RF2_6-20160326_+2.zip",
        {
            "IMG-HH-ALOS20243390-160326-RF2": "hh",
            "IMG-HV-ALOS20243390-160326-RF2": "hv",
            "LED-ALOS20243390-160326-RF2": "leader",
        },
    )

    groups = organize_alos2_stripmap_zips(
        zip_dir,
        tmp_path / "organized",
        polarizations=["HV"],
    )
    date_dir = groups["path_24/RF2_6"]["dates"]["20160326"]["date_dir"]

    assert not (date_dir / "IMG-HH-ALOS20243390-160326-RF2").exists()
    assert (date_dir / "IMG-HV-ALOS20243390-160326-RF2").exists()
    assert (date_dir / "LED-ALOS20243390-160326-RF2").exists()


def test_select_processing_dir_preserves_multi_frame_parent(tmp_path):
    frame_3390 = tmp_path / "20160326" / "frame_3390"
    frame_3400 = tmp_path / "20160326" / "frame_3400"
    frame_3390.mkdir(parents=True)
    frame_3400.mkdir(parents=True)

    metadata = {
        "product_root": frame_3390,
        "files": {
            "IMG": [
                frame_3390 / "IMG-HH-ALOS20243390-160326-RF2",
                frame_3400 / "IMG-HH-ALOS20243400-160326-RF2",
            ],
        },
    }

    assert _select_alos2_processing_dir(tmp_path / "20160326", metadata) == (
        tmp_path / "20160326"
    ).resolve()
