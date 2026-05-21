from pathlib import Path
import zipfile

from iscewrap.alos4 import (
    default_range_sampling_rates,
    detect_product_metadata,
    extract_alos4_zip,
    find_alos4_product_dirs,
    organize_alos4_stripmap_zips,
    parse_alos4_img_filename,
    parse_alos4_stripmap_zip_name,
    parse_alos4_summary,
    process_alos4_pair,
    stage_alos4_as_alos2_names,
)
from iscewrap.alos4.backend import _prepare_native_alias_dir


def _make_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def test_parse_alos4_stripmap_zip_name():
    product = parse_alos4_stripmap_zip_name("125-710-RU1_08_F-20250728.zip")

    assert product.path == "125"
    assert product.frame == "710"
    assert product.mode == "RU1"
    assert product.beam == "08"
    assert product.direction == "F"
    assert product.date == "20250728"
    assert product.group_name == "path_125/RU1_08"


def test_parse_alos4_summary(tmp_path):
    summary = tmp_path / "summary-ALOS41250710250728UWDPRA0108-1.1__-.txt"
    summary.write_text(
        '\n'.join(
            [
                'Scs_SceneID="ALOS41250710250728UWDPRA0108"',
                'Scs_ObsMode="UWD"',
                'Img_OffNadirAngle="35.4"',
                'Pdi_ProductFormat="CEOS"',
                'Lbi_Satellite="ALOS4"',
            ]
        )
    )

    metadata = parse_alos4_summary(summary)

    assert metadata["Scs_ObsMode"] == "UWD"
    assert metadata["Img_OffNadirAngle"] == "35.4"
    assert metadata["Pdi_ProductFormat"] == "CEOS"
    assert metadata["Lbi_Satellite"] == "ALOS4"


def test_parse_alos4_img_filename():
    info = parse_alos4_img_filename("IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-")

    assert info["polarization"] == "HH"
    assert info["path"] == "125"
    assert info["frame"] == "710"
    assert info["frame_padded"] == "0710"
    assert info["date"] == "20250728"
    assert info["obs_mode"] == "UWD"
    assert info["beam"] == "08"


def test_detect_product_metadata_prefers_hh(tmp_path):
    product_dir = tmp_path / "0000316145"
    product_dir.mkdir()
    (product_dir / "IMG-HV-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (product_dir / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (product_dir / "summary-ALOS41250710250728UWDPRA0108-1.1__-.txt").write_text(
        'Lbi_Satellite="ALOS4"\n'
    )

    metadata = detect_product_metadata(tmp_path)

    assert metadata["img_info"]["polarization"] == "HH"
    assert metadata["summary"]["Lbi_Satellite"] == "ALOS4"


def test_organize_alos4_stripmap_zips_groups_frames_by_date(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _make_zip(
        zip_dir / "125-710-RU1_08_F-20250728.zip",
        {"0000316145/IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-": "a"},
    )
    _make_zip(
        zip_dir / "125-720-RU1_08_F-20250728.zip",
        {"0000316146/IMG-HH-ALOS41250720250728UWDPRA0108-1.1__-": "b"},
    )

    groups = organize_alos4_stripmap_zips(zip_dir, tmp_path / "organized")
    date_info = groups["path_125/RU1_08"]["dates"]["20250728"]

    assert date_info["frames"] == ["710", "720"]
    assert (
        date_info["date_dir"]
        / "0000316145"
        / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-"
    ).read_text() == "a"


def test_extract_alos4_zip_filters_polarization_files(tmp_path):
    zip_file = tmp_path / "125-710-RU1_08_F-20250728.zip"
    _make_zip(
        zip_file,
        {
            "0000316145/IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-": "hh",
            "0000316145/IMG-HV-ALOS41250710250728UWDPRA0108-1.1__-": "hv",
            "0000316145/BRS-HH-ALOS41250710250728UWDPRA0108-1.1__-.jpg": "hh browse",
            "0000316145/BRS-HV-ALOS41250710250728UWDPRA0108-1.1__-.jpg": "hv browse",
            "0000316145/LED-ALOS41250710250728UWDPRA0108-1.1__-": "leader",
            "ALOS41250710250728UWDPRA0108_1.1__-.kml": "kml",
        },
    )

    extract_dir = extract_alos4_zip(zip_file, tmp_path / "raw", polarizations="HH")

    assert (extract_dir / "0000316145" / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").exists()
    assert not (extract_dir / "0000316145" / "IMG-HV-ALOS41250710250728UWDPRA0108-1.1__-").exists()
    assert (extract_dir / "0000316145" / "BRS-HH-ALOS41250710250728UWDPRA0108-1.1__-.jpg").exists()
    assert not (extract_dir / "0000316145" / "BRS-HV-ALOS41250710250728UWDPRA0108-1.1__-.jpg").exists()
    assert (extract_dir / "0000316145" / "LED-ALOS41250710250728UWDPRA0108-1.1__-").exists()
    assert (extract_dir / "ALOS41250710250728UWDPRA0108_1.1__-.kml").exists()


def test_organize_alos4_stripmap_zips_filters_polarization_files(tmp_path):
    zip_dir = tmp_path / "zips"
    zip_dir.mkdir()
    _make_zip(
        zip_dir / "125-710-RU1_08_F-20250728.zip",
        {
            "0000316145/IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-": "hh",
            "0000316145/IMG-HV-ALOS41250710250728UWDPRA0108-1.1__-": "hv",
            "0000316145/LED-ALOS41250710250728UWDPRA0108-1.1__-": "leader",
        },
    )

    groups = organize_alos4_stripmap_zips(
        zip_dir,
        tmp_path / "organized",
        polarizations=["HV"],
    )
    date_dir = groups["path_125/RU1_08"]["dates"]["20250728"]["date_dir"]

    assert not (date_dir / "0000316145" / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").exists()
    assert (date_dir / "0000316145" / "IMG-HV-ALOS41250710250728UWDPRA0108-1.1__-").exists()
    assert (date_dir / "0000316145" / "LED-ALOS41250710250728UWDPRA0108-1.1__-").exists()


def test_find_alos4_product_dirs(tmp_path):
    product_dir = tmp_path / "root" / "0000316145"
    product_dir.mkdir(parents=True)
    (product_dir / "summary-ALOS41250710250728UWDPRA0108-1.1__-.txt").write_text("")

    assert find_alos4_product_dirs(tmp_path) == [product_dir.resolve()]


def test_process_alos4_pair_writes_xml_without_running(tmp_path):
    reference = tmp_path / "reference" / "0000316145"
    secondary = tmp_path / "secondary" / "0000316145"
    reference.mkdir(parents=True)
    secondary.mkdir(parents=True)

    (reference / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "IMG-HH-ALOS41250710250809UWDPRA0108-1.1__-").write_text("")
    (reference / "LED-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "LED-ALOS41250710250809UWDPRA0108-1.1__-").write_text("")

    result = process_alos4_pair(
        reference_input=tmp_path / "reference",
        secondary_input=tmp_path / "secondary",
        work_dir=tmp_path / "work",
        run=False,
    )

    xml_text = result["xml_file"].read_text()
    assert "reference directory" in xml_text
    assert "secondary directory" in xml_text
    assert result["pair_name"] == "20250728_20250809"
    assert result["backend"] == "native"
    assert result["reference_processing_dir"] == reference.resolve()
    assert result["secondary_processing_dir"] == secondary.resolve()
    assert result["stage_compat_names"] is False
    assert result["range_sampling_rates"] == {98: 98_242_186.9}


def test_process_alos4_pair_can_stage_compat_names(tmp_path):
    reference = tmp_path / "reference" / "0000316145"
    secondary = tmp_path / "secondary" / "0000316145"
    reference.mkdir(parents=True)
    secondary.mkdir(parents=True)

    (reference / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "IMG-HH-ALOS41250710250809UWDPRA0108-1.1__-").write_text("")
    (reference / "LED-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "LED-ALOS41250710250809UWDPRA0108-1.1__-").write_text("")

    result = process_alos4_pair(
        reference_input=tmp_path / "reference",
        secondary_input=tmp_path / "secondary",
        work_dir=tmp_path / "work",
        run=False,
        backend="compat",
    )

    assert result["backend"] == "compat"
    assert result["stage_compat_names"] is True
    assert (result["reference_processing_dir"] / "IMG-HH-ALOS21250710-250728-FBD").is_symlink()
    assert (result["secondary_processing_dir"] / "LED-ALOS21250710-250809-FBD").is_symlink()


def test_stage_alos4_as_alos2_names(tmp_path):
    product_dir = tmp_path / "product"
    product_dir.mkdir()
    img = product_dir / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-"
    led = product_dir / "LED-ALOS41250710250728UWDPRA0108-1.1__-"
    img.write_text("image")
    led.write_text("leader")

    staged = stage_alos4_as_alos2_names(product_dir, tmp_path / "staged")

    assert (staged / "IMG-HH-ALOS21250710-250728-FBD").resolve() == img.resolve()
    assert (staged / "LED-ALOS21250710-250728-FBD").resolve() == led.resolve()


def test_prepare_native_alias_dir_flattens_alos4_names_for_isce2_globs(tmp_path):
    product_dir = tmp_path / "product" / "0000316145"
    product_dir.mkdir(parents=True)
    img = product_dir / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-"
    led = product_dir / "LED-ALOS41250710250728UWDPRA0108-1.1__-"
    img.write_text("image")
    led.write_text("leader")

    alias_dir = _prepare_native_alias_dir(
        tmp_path / "product",
        tmp_path / "aliases",
        compat_mode="FBD",
    )

    assert (alias_dir / "IMG-HH-ALOS21250710-250728-FBD").resolve() == img.resolve()
    assert (alias_dir / "LED-ALOS21250710-250728-FBD").resolve() == led.resolve()


def test_process_alos4_pair_accepts_custom_range_sampling_rate(tmp_path):
    reference = tmp_path / "reference"
    secondary = tmp_path / "secondary"
    reference.mkdir()
    secondary.mkdir()

    (reference / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "IMG-HH-ALOS41250710250809UWDPRA0108-1.1__-").write_text("")

    result = process_alos4_pair(
        reference_input=reference,
        secondary_input=secondary,
        work_dir=tmp_path / "work",
        run=False,
        range_sampling_rates={98: 98_304_000.0},
    )

    assert result["range_sampling_rates"] == {98: 98_304_000.0}


def test_default_range_sampling_rates_accepts_overrides():
    assert default_range_sampling_rates({98: 98_304_000.0, 32: 32_747_395.6}) == {
        98: 98_304_000.0,
        32: 32_747_395.6,
    }
