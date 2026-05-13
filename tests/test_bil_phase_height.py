
from pathlib import Path

import numpy as np

from iscewrap.alos2 import (
    read_isce_raster,
    read_los_incidence_angle,
    convert_phase_to_height,
)


def write_xml(path, width, length, data_type="FLOAT", number_bands=2, scheme="BIL"):
    Path(str(path) + ".xml").write_text(
        f"""<imageFile>
        <property name="width"><value>{width}</value></property>
        <property name="length"><value>{length}</value></property>
        <property name="data_type"><value>{data_type}</value></property>
        <property name="number_bands"><value>{number_bands}</value></property>
        <property name="scheme"><value>{scheme}</value></property>
        </imageFile>"""
    )


def test_bil_reader_returns_band_length_width(tmp_path):
    length, width, bands = 3, 4, 2

    # BIL layout: row0 band0, row0 band1, row1 band0, row1 band1, ...
    band0 = np.full((length, width), 10, dtype=np.float32)
    band1 = np.full((length, width), 20, dtype=np.float32)
    bil = np.stack([band0, band1], axis=1)  # length, bands, width

    raster = tmp_path / "test.unw"
    bil.tofile(raster)
    write_xml(raster, width, length, number_bands=2, scheme="BIL")

    assert read_isce_raster(raster, band=0).shape == (length, width)
    assert read_isce_raster(raster, band=1).shape == (length, width)
    assert np.all(read_isce_raster(raster, band=0) == 10)
    assert np.all(read_isce_raster(raster, band=1) == 20)


def test_convert_unw_defaults_to_band1(tmp_path):
    length, width = 3, 4

    amp = np.ones((length, width), dtype=np.float32)
    phase = np.full((length, width), 2.0, dtype=np.float32)
    unw_bil = np.stack([amp, phase], axis=1)

    unw = tmp_path / "filt_201127-210122_8rlks_16alks.unw"
    unw_bil.tofile(unw)
    write_xml(unw, width, length, number_bands=2, scheme="BIL")

    incidence = np.full((length, width), 0.7, dtype=np.float32)
    heading = np.zeros((length, width), dtype=np.float32)
    los_bil = np.stack([incidence, heading], axis=1)

    los = tmp_path / "201127-210122_8rlks_16alks.los"
    los_bil.tofile(los)
    write_xml(los, width, length, number_bands=2, scheme="BIL")

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
        phase_file=unw,
        los_file=los,
        track_xml=track,
        baseline_log=log,
        output_file=out,
    )

    height = np.fromfile(out, dtype=np.float32).reshape(result["shape"])
    assert result["shape"] == (length, width)
    assert np.all(np.isfinite(height))
    assert np.nanmean(height) > 0
