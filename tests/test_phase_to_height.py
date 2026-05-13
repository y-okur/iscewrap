
from pathlib import Path

import numpy as np

from iscewrap.alos2 import (
    convert_phase_to_height,
    make_bperp_image,
    phase_to_height,
    read_track_metadata,
)


def write_simple_isce_xml(path, width, length, data_type="FLOAT", number_bands=1, scheme="BIP"):
    Path(str(path) + ".xml").write_text(
        f"""<imageFile>
        <property name="width"><value>{width}</value></property>
        <property name="length"><value>{length}</value></property>
        <property name="data_type"><value>{data_type}</value></property>
        <property name="number_bands"><value>{number_bands}</value></property>
        <property name="scheme"><value>{scheme}</value></property>
        </imageFile>"""
    )


def test_read_track_metadata(tmp_path):
    track = tmp_path / "201127.track.xml"
    track.write_text(
        """<productmanager_name>
        <component name="instance">
        <property name="radarwavelength"><value>0.2424525</value></property>
        <property name="rangepixelsize"><value>4.291266717869248</value></property>
        <property name="startingrange"><value>789235.0</value></property>
        </component>
        </productmanager_name>"""
    )

    meta = read_track_metadata(track)

    assert meta["radar_wavelength"] == 0.2424525
    assert meta["range_pixel_size"] == 4.291266717869248
    assert meta["starting_range"] == 789235.0


def test_convert_phase_to_height(tmp_path):
    length, width = 3, 4

    phase = np.ones((length, width), dtype=np.float32)
    phase_file = tmp_path / "201127-210122_8rlks_16alks.topophase"
    phase.tofile(phase_file)
    write_simple_isce_xml(phase_file, width, length, data_type="FLOAT", number_bands=1)

    # BIP two-band LOS: [incidence, heading] per pixel
    incidence = np.full((length, width), np.deg2rad(35.0), dtype=np.float32)
    heading = np.zeros((length, width), dtype=np.float32)
    los_bip = np.stack([incidence, heading], axis=-1)
    los_file = tmp_path / "201127-210122_8rlks_16alks.los"
    los_bip.tofile(los_file)
    write_simple_isce_xml(los_file, width, length, data_type="FLOAT", number_bands=2, scheme="BIP")

    track = tmp_path / "201127.track.xml"
    track.write_text(
        """<productmanager_name>
        <component name="instance">
        <property name="radarwavelength"><value>0.2424525</value></property>
        <property name="rangepixelsize"><value>4.0</value></property>
        <property name="startingrange"><value>800000.0</value></property>
        </component>
        </productmanager_name>"""
    )

    log = tmp_path / "alos2App_full_terminal.log"
    log.write_text(
        "runBaseline.perpendicular baseline at center of reference track = 131.0\n"
        "runBaseline.perpendicular baseline at lowerleft of reference track = 133.0\n"
        "runBaseline.perpendicular baseline at lowerright of reference track = 126.0\n"
        "runBaseline.perpendicular baseline at upperleft of reference track = 137.0\n"
        "runBaseline.perpendicular baseline at upperright of reference track = 129.0\n"
    )

    out = tmp_path / "height.dem"
    result = convert_phase_to_height(
        phase_file=phase_file,
        los_file=los_file,
        track_xml=track,
        baseline_log=log,
        output_file=out,
    )

    assert out.exists()
    assert Path(str(out) + ".xml").exists()

    height = np.fromfile(out, dtype=np.float32).reshape(length, width)
    assert np.all(np.isfinite(height))
    assert result["range_looks"] == 8
    assert result["wavelength"] == 0.2424525
