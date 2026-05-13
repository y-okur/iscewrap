from iscewrap.alos2.xml import create_alos2app_xml


def test_create_alos2app_xml(tmp_path):
    ref = tmp_path / "ref"
    sec = tmp_path / "sec"
    ref.mkdir()
    sec.mkdir()

    xml_file = create_alos2app_xml(
        reference_dir=ref,
        secondary_dir=sec,
        output_xml=tmp_path / "alos2App.xml",
        geocode_file_list=["diff*int", "filt*int*"],
    )

    text = xml_file.read_text()
    assert "geocode file list" in text
    assert '&quot;diff*int&quot;' in text or '"diff*int"' in text
