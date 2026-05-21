from pathlib import Path
import zipfile

from iscewrap.alos4app import detect_alos_input, process_alos_pair


def _make_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def test_detect_alos4_uwd_directory(tmp_path):
    product = tmp_path / "alos4" / "0000316145"
    product.mkdir(parents=True)
    (product / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")

    detected = detect_alos_input(tmp_path / "alos4")

    assert detected["sensor"] == "ALOS4"
    assert detected["obs_mode"] == "UWD"
    assert detected["path"] == "125"
    assert detected["frame"] == "710"
    assert detected["beam"] == "08"


def test_detect_alos2_directory(tmp_path):
    product = tmp_path / "alos2"
    product.mkdir()
    (product / "IMG-HH-ALOS20243390-160326-FBD").write_text("")

    detected = detect_alos_input(product)

    assert detected["sensor"] == "ALOS2"
    assert detected["obs_mode"] == "FBD"
    assert detected["frame"] == "3390"


def test_detect_alos4_zip_from_name(tmp_path):
    zip_file = tmp_path / "125-710-RU1_08_F-20250728.zip"
    _make_zip(zip_file, {"placeholder": ""})

    detected = detect_alos_input(zip_file)

    assert detected["sensor"] == "ALOS4"
    assert detected["obs_mode"] == "UWD"
    assert detected["beam"] == "08"


def test_process_alos_pair_dispatches_alos4_uwd(tmp_path):
    reference = tmp_path / "reference" / "0000316145"
    secondary = tmp_path / "secondary" / "0000316146"
    reference.mkdir(parents=True)
    secondary.mkdir(parents=True)
    (reference / "IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "IMG-HH-ALOS41250710250811UWDPRA0108-1.1__-").write_text("")
    (reference / "LED-ALOS41250710250728UWDPRA0108-1.1__-").write_text("")
    (secondary / "LED-ALOS41250710250811UWDPRA0108-1.1__-").write_text("")

    result = process_alos_pair(
        reference_input=tmp_path / "reference",
        secondary_input=tmp_path / "secondary",
        work_dir=tmp_path / "work",
        run=False,
    )

    assert result["workflow"] == "ALOS4_UWD_NATIVE"
    assert result["pair_name"] == "20250728_20250811"
    assert result["backend"] == "native"
    assert result["range_sampling_rates"] == {98: 98_242_186.9}


def test_process_alos_pair_dispatches_alos2(tmp_path):
    reference = tmp_path / "reference"
    secondary = tmp_path / "secondary"
    reference.mkdir()
    secondary.mkdir()
    (reference / "IMG-HH-ALOS20243390-160326-FBD").write_text("")
    (secondary / "IMG-HH-ALOS20243390-160604-FBD").write_text("")

    result = process_alos_pair(
        reference_input=reference,
        secondary_input=secondary,
        work_dir=tmp_path / "work",
        run=False,
    )

    assert result["workflow"] == "ALOS2"
    assert result["pair_name"] == "160326_160604"


def test_process_alos_pair_rejects_alos4_non_uwd(tmp_path):
    reference = tmp_path / "reference"
    secondary = tmp_path / "secondary"
    reference.mkdir()
    secondary.mkdir()
    (reference / "IMG-HH-ALOS41370200250620FWDPRA0105-1.1__-").write_text("")
    (secondary / "IMG-HH-ALOS41370200251121FWDPRA0105-1.1__-").write_text("")

    try:
        process_alos_pair(
            reference_input=reference,
            secondary_input=secondary,
            work_dir=tmp_path / "work",
            run=False,
        )
    except ValueError as exc:
        assert "UWD-UWD" in str(exc)
    else:
        raise AssertionError("Expected FWD pair to be rejected")


def test_process_alos_pair_rejects_mixed_sensor_pair(tmp_path):
    reference = tmp_path / "reference"
    secondary = tmp_path / "secondary"
    reference.mkdir()
    secondary.mkdir()
    (reference / "IMG-HH-ALOS20243390-160326-FBD").write_text("")
    (secondary / "IMG-HH-ALOS41250710250811UWDPRA0108-1.1__-").write_text("")

    try:
        process_alos_pair(
            reference_input=reference,
            secondary_input=secondary,
            work_dir=tmp_path / "work",
            run=False,
        )
    except ValueError as exc:
        assert "Mixed ALOS-2/ALOS-4" in str(exc)
    else:
        raise AssertionError("Expected mixed sensor pair to be rejected")
