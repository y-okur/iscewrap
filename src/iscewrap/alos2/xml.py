"""XML writers for ISCE2 alos2App.py."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence
import xml.etree.ElementTree as ET
from xml.dom import minidom


def add_property(parent: ET.Element, name: str, value) -> ET.Element:
    """Add an ISCE-style XML property."""
    prop = ET.SubElement(parent, "property", name=name)
    prop.text = str(value)
    return prop


def format_isce_list(values: Sequence[str] | str) -> str:
    """Format a Python sequence as an ISCE XML list string.

    Examples
    --------
    ["diff*int", "filt*int*"] -> ["diff*int", "filt*int*"]
    "diff*int" -> ["diff*int"]
    """
    if isinstance(values, str):
        values = [values]
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


def write_pretty_xml(root: ET.Element, output_xml: str | Path) -> Path:
    """Write pretty-formatted XML to disk."""
    output_xml = Path(output_xml)
    output_xml.parent.mkdir(parents=True, exist_ok=True)

    xml_bytes = ET.tostring(root, encoding="utf-8")
    pretty_xml = minidom.parseString(xml_bytes).toprettyxml(indent="  ")

    with open(output_xml, "w", encoding="utf-8") as f:
        f.write(pretty_xml)

    return output_xml


def create_alos2app_xml(
    reference_dir,
    secondary_dir,
    output_xml,
    reference_frame=None,
    secondary_frame=None,
    reference_polarization=None,
    secondary_polarization=None,
    multilook_params=None,
    dem_coreg=None,
    dem_geocode=None,
    water_body=None,
    do_insar=True,
    use_gpu=False,
    do_ionosphere=True,
    apply_ionosphere=True,
    geocode_file_list=None,
    interferogram_filter_strength=0.3,
    interferogram_filter_window_size=32,
    interferogram_filter_step_size=4,
    remove_magnitude_before_filtering=True,
    do_dense_offset=False,
    estimate_residual_offset_after_geometrical_coregistration=True,
    delete_geometry_files_used_for_dense_offset_estimation=False,
    dense_offset_estimation_window_width=128,
    dense_offset_estimation_window_height=128,
    dense_offset_skip_width=64,
    dense_offset_skip_height=64,
) -> Path:
    """Create an ``alos2App.py`` XML configuration file."""
    output_xml = Path(output_xml)

    root = ET.Element("alos2App")
    component = ET.SubElement(root, "component", name="alos2insar")

    add_property(component, "reference directory", Path(reference_dir).resolve())
    add_property(component, "secondary directory", Path(secondary_dir).resolve())

    if reference_frame is not None:
        add_property(component, "reference frames", f"[{reference_frame}]")

    if secondary_frame is not None:
        add_property(component, "secondary frames", f"[{secondary_frame}]")

    if reference_polarization is not None:
        add_property(component, "reference polarization", reference_polarization)

    if secondary_polarization is not None:
        add_property(component, "secondary polarization", secondary_polarization)

    if dem_coreg is not None:
        add_property(component, "dem for coregistration", Path(dem_coreg).resolve())

    if dem_geocode is not None:
        add_property(component, "dem for geocoding", Path(dem_geocode).resolve())

    if water_body is not None:
        add_property(component, "water body", Path(water_body).resolve())

    add_property(component, "do InSAR", do_insar)
    add_property(component, "use GPU", use_gpu)

    if multilook_params is not None:
        for key, value in multilook_params.items():
            add_property(component, key, value)

    add_property(component, "do ionospheric phase estimation", do_ionosphere)
    add_property(component, "apply ionospheric phase correction", apply_ionosphere)

    add_property(component, "interferogram filter strength", interferogram_filter_strength)
    add_property(component, "interferogram filter window size", interferogram_filter_window_size)
    add_property(component, "interferogram filter step size", interferogram_filter_step_size)
    add_property(component, "remove magnitude before filtering", remove_magnitude_before_filtering)

    add_property(component, "do dense offset", do_dense_offset)
    add_property(
        component,
        "estimate residual offset after geometrical coregistration",
        estimate_residual_offset_after_geometrical_coregistration,
    )
    add_property(
        component,
        "delete geometry files used for dense offset estimation",
        delete_geometry_files_used_for_dense_offset_estimation,
    )
    add_property(component, "dense offset estimation window width", dense_offset_estimation_window_width)
    add_property(component, "dense offset estimation window height", dense_offset_estimation_window_height)
    add_property(component, "dense offset skip width", dense_offset_skip_width)
    add_property(component, "dense offset skip height", dense_offset_skip_height)

    if geocode_file_list:
        add_property(component, "geocode file list", format_isce_list(geocode_file_list))

    return write_pretty_xml(root, output_xml)
