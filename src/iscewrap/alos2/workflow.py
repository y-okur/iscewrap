"""High-level ALOS-2 pair processing workflow."""

from __future__ import annotations

from pathlib import Path
import math
import re

from .metadata import detect_product_metadata, extract_alos2_zip
from .runner import run_isce2_alos2app, validate_alos2_steps
from .xml import create_alos2app_xml


def process_alos2_pair(
    reference_input,
    secondary_input,
    work_dir,
    dem_coreg=None,
    dem_geocode=None,
    water_body=None,
    use_gpu=False,
    do_ionosphere=True,
    apply_ionosphere=True,
    run=True,
    alos2app_cmd="alos2App.py",
    do_insar=True,
    steps=True,
    start_step=None,
    end_step=None,
    geocode_file_list=None,
    interferogram_filter_strength=0.3,
    interferogram_filter_window_size=32,
    interferogram_filter_step_size=4,
    remove_magnitude_before_filtering=True,
    do_dense_offset=False,
    estimate_residual_offset_after_geometrical_coregistration=False,
    delete_geometry_files_used_for_dense_offset_estimation=False,
    dense_offset_estimation_window_width=64,
    dense_offset_estimation_window_height=64,
    dense_offset_skip_width=32,
    dense_offset_skip_height=32,
) -> dict:
    """Create XML and optionally run ISCE2 ``alos2App.py`` for one ALOS-2 pair."""
    validate_alos2_steps(start_step, end_step)

    reference_input = Path(reference_input).resolve()
    secondary_input = Path(secondary_input).resolve()
    work_dir = Path(work_dir).resolve()

    raw_dir = work_dir / "raw"
    xml_dir = work_dir / "xml"
    run_dir = work_dir / "run"

    raw_dir.mkdir(parents=True, exist_ok=True)
    xml_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    reference_dir = (
        extract_alos2_zip(reference_input, raw_dir)
        if reference_input.suffix.lower() == ".zip"
        else reference_input
    )
    secondary_dir = (
        extract_alos2_zip(secondary_input, raw_dir)
        if secondary_input.suffix.lower() == ".zip"
        else secondary_input
    )

    reference_meta = detect_product_metadata(reference_dir)
    secondary_meta = detect_product_metadata(secondary_dir)

    reference_dir = reference_meta["product_root"]
    secondary_dir = secondary_meta["product_root"]

    reference_info = reference_meta["img_info"]
    secondary_info = secondary_meta["img_info"]

    multilook_params = reference_meta["multilook"]

    pair_name = f"{reference_info['date']}_{secondary_info['date']}"
    xml_file = (xml_dir / f"alos2App_{pair_name}.xml").resolve()

    create_alos2app_xml(
        reference_dir=reference_dir,
        secondary_dir=secondary_dir,
        output_xml=xml_file,
        reference_frame=reference_info["frame"],
        secondary_frame=secondary_info["frame"],
        reference_polarization=reference_info["polarization"],
        secondary_polarization=secondary_info["polarization"],
        do_insar=do_insar,
        multilook_params=multilook_params,
        dem_coreg=dem_coreg,
        dem_geocode=dem_geocode,
        water_body=water_body,
        use_gpu=use_gpu,
        do_ionosphere=do_ionosphere,
        apply_ionosphere=apply_ionosphere,
        interferogram_filter_strength=interferogram_filter_strength,
        interferogram_filter_window_size=interferogram_filter_window_size,
        interferogram_filter_step_size=interferogram_filter_step_size,
        remove_magnitude_before_filtering=remove_magnitude_before_filtering,
        do_dense_offset=do_dense_offset,
        estimate_residual_offset_after_geometrical_coregistration=(
            estimate_residual_offset_after_geometrical_coregistration
        ),
        delete_geometry_files_used_for_dense_offset_estimation=(
            delete_geometry_files_used_for_dense_offset_estimation
        ),
        dense_offset_estimation_window_width=dense_offset_estimation_window_width,
        dense_offset_estimation_window_height=dense_offset_estimation_window_height,
        dense_offset_skip_width=dense_offset_skip_width,
        dense_offset_skip_height=dense_offset_skip_height,
        geocode_file_list=geocode_file_list,
    )

    result = None

    if run:
        result = run_isce2_alos2app(
            xml_file=xml_file,
            work_dir=run_dir,
            alos2app_cmd=alos2app_cmd,
            start_step=start_step,
            end_step=end_step,
            steps=steps,
        )

    return {
        "pair_name": pair_name,
        "reference_dir": reference_dir,
        "secondary_dir": secondary_dir,
        "xml_file": xml_file,
        "run_dir": run_dir,
        "reference_info": reference_info,
        "secondary_info": secondary_info,
        "multilook_params": multilook_params,
        "start_step": start_step,
        "end_step": end_step,
        "stdout": None if result is None else result.stdout,
        "stderr": None if result is None else result.stderr,
    }

def _parse_reference_bounding_box_from_log(log_file: str | Path) -> list[float]:
    """Parse the reference bounding box from ``alos2App.py`` terminal log.

    Expected log line example:
        runBaseline.reference bounding box = [-7.95, -7.18, 110.22, 111.04]

    Returns
    -------
    list[float]
        ``[min_lat, max_lat, min_lon, max_lon]``.
    """
    log_file = Path(log_file)

    if not log_file.exists():
        raise FileNotFoundError(f"Baseline log file not found: {log_file}")

    text = log_file.read_text(encoding="utf-8", errors="replace")

    pattern = (
        r"runBaseline\.reference bounding box\s*=\s*"
        r"\[\s*"
        r"(?P<min_lat>[-+0-9.eE]+)\s*,\s*"
        r"(?P<max_lat>[-+0-9.eE]+)\s*,\s*"
        r"(?P<min_lon>[-+0-9.eE]+)\s*,\s*"
        r"(?P<max_lon>[-+0-9.eE]+)\s*"
        r"\]"
    )

    match = re.search(pattern, text)
    if match is None:
        raise ValueError(
            "Could not find 'runBaseline.reference bounding box = [...]' "
            f"in log file: {log_file}"
        )

    return [
        float(match.group("min_lat")),
        float(match.group("max_lat")),
        float(match.group("min_lon")),
        float(match.group("max_lon")),
    ]


def _format_lat(value: int) -> str:
    """Format integer latitude for ISCE DEM filenames."""
    hemi = "N" if value >= 0 else "S"
    return f"{hemi}{abs(int(value)):02d}"


def _format_lon(value: int) -> str:
    """Format integer longitude for ISCE DEM filenames."""
    hemi = "E" if value >= 0 else "W"
    return f"{hemi}{abs(int(value)):03d}"


def _rounded_dem_extent(bounding_box: list[float]) -> tuple[int, int, int, int]:
    """Round a floating bounding box outward to integer-degree DEM bounds.

    Input order is ``[min_lat, max_lat, min_lon, max_lon]``.
    Output order is ``(south, north, west, east)``.
    """
    min_lat, max_lat, min_lon, max_lon = bounding_box
    south = math.floor(min_lat)
    north = math.ceil(max_lat)
    west = math.floor(min_lon)
    east = math.ceil(max_lon)

    if south >= north or west >= east:
        raise ValueError(
            "Invalid rounded DEM extent: "
            f"south={south}, north={north}, west={west}, east={east}"
        )

    return south, north, west, east


def _dem_filename(south: int, north: int, west: int, east: int) -> str:
    """Create an ISCE-style DEM filename from integer-degree bounds."""
    return (
        f"demLat_{_format_lat(south)}_{_format_lat(north)}_"
        f"Lon_{_format_lon(west)}_{_format_lon(east)}.dem.wgs84"
    )


def _wbd_filename(south: int, north: int, west: int, east: int) -> str:
    """Create an ISCE-style water-body filename from integer-degree bounds."""
    return (
        f"swbdLat_{_format_lat(south)}_{_format_lat(north)}_"
        f"Lon_{_format_lon(west)}_{_format_lon(east)}.wbd"
    )


def _write_constant_binary_file(
    output_file: str | Path,
    total_values: int,
    dtype_bytes: int,
    fill_byte: int = 0,
    chunk_values: int = 8_000_000,
) -> Path:
    """Write a constant-value binary raster efficiently.

    DEM zeros are written by truncating the file. WBD values are written as
    literal bytes because WBD must be filled with 1.
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = int(total_values) * int(dtype_bytes)

    if fill_byte == 0:
        with open(output_file, "wb") as f:
            f.truncate(total_bytes)
        return output_file

    chunk_bytes = bytes([fill_byte]) * min(int(chunk_values) * int(dtype_bytes), total_bytes)
    remaining = total_bytes

    with open(output_file, "wb") as f:
        while remaining > 0:
            n = min(len(chunk_bytes), remaining)
            f.write(chunk_bytes[:n])
            remaining -= n

    return output_file


def _write_isce_raster_xml(
    raster_file: str | Path,
    width: int,
    length: int,
    west: int,
    east: int,
    south: int,
    north: int,
    delta: float,
    data_type: str,
    family: str,
    image_type: str | None = None,
    reference: str | None = None,
) -> Path:
    """Write ISCE XML metadata for a single-band geographic raster."""
    raster_file = Path(raster_file).resolve()
    xml_file = Path(str(raster_file) + ".xml")

    def prop(name: str, value, doc: str | None = None, indent: str = "    ") -> str:
        doc_text = "" if doc is None else f"\n{indent}    <doc>{doc}</doc>"
        return (
            f'{indent}<property name="{name}">\n'
            f"{indent}    <value>{value}</value>{doc_text}\n"
            f"{indent}</property>"
        )

    def coord_component(
        name: str,
        delta_value: float,
        ending: float,
        size: int,
        starting: float,
        doc: str,
    ) -> str:
        return (
            f'    <component name="{name}">\n'
            "        <factorymodule>isceobj.Image</factorymodule>\n"
            "        <factoryname>createCoordinate</factoryname>\n"
            f"        <doc>{doc}</doc>\n"
            f"{prop('delta', delta_value, 'Coordinate quantization.', indent='        ')}\n"
            f"{prop('endingvalue', ending, 'Ending value of the coordinate.', indent='        ')}\n"
            f"{prop('family', 'imagecoordinate', 'Instance family name', indent='        ')}\n"
            f"{prop('name', 'imagecoordinate_name', 'Instance name', indent='        ')}\n"
            f"{prop('size', size, 'Coordinate size.', indent='        ')}\n"
            f"{prop('startingvalue', starting, 'Starting value of the coordinate.', indent='        ')}\n"
            "    </component>"
        )

    extra = [
        prop("data_type", data_type, "Image data type."),
        prop("extra_file_name", raster_file.name + ".vrt", "For example name of vrt metadata."),
        prop("family", family, "Instance family name"),
        prop("file_name", raster_file, "Name of the image file."),
    ]

    if image_type is not None:
        extra.append(prop("image_type", image_type, "Image type used for displaying."))

    extra.extend(
        [
            prop("length", length, "Image length"),
            prop(
                "metadata_location",
                raster_file.name + ".xml",
                "Location of the metadata file where the instance was defined",
            ),
            prop("name", f"{family}_name", "Instance name"),
            prop("number_bands", 1, "Number of image bands."),
        ]
    )

    if reference is not None:
        extra.append(prop("reference", reference, "Geodetic datum"))

    extra.extend(
        [
            prop("scheme", "BIP", "Interleaving scheme of the image."),
            prop("width", width, "Image width"),
            prop("xmax", float(east), "Maximum range value"),
            prop("xmin", float(west), "Minimum range value"),
        ]
    )

    text = (
        "<imageFile>\n"
        f"{prop('ISCE_VERSION', 'Generated by iscewrap')}\n"
        f"{prop('access_mode', 'READ', 'Image access mode.')}\n"
        f"{prop('byte_order', 'l', 'Endianness of the image.')}\n"
        f"{coord_component('coordinate1', delta, float(east), width, float(west), '[' + repr('First coordinate of a 2D image (width).') + ']')}\n"
        f"{coord_component('coordinate2', -delta, float(south), length, float(north), '[' + repr('Second coordinate of a 2D image (length).') + ']')}\n"
        f"{chr(10).join(extra)}\n"
        "</imageFile>\n"
    )

    xml_file.write_text(text, encoding="utf-8")
    return xml_file


def _write_vrt(
    raster_file: str | Path,
    width: int,
    length: int,
    west: int,
    north: int,
    delta: float,
    vrt_dtype: str,
    pixel_offset: int,
    line_offset: int,
) -> Path:
    """Write GDAL VRT metadata for a raw geographic raster."""
    raster_file = Path(raster_file)
    vrt_file = Path(str(raster_file) + ".vrt")

    text = (
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{length}">\n'
        "    <SRS>EPSG:4326</SRS>\n"
        f"    <GeoTransform>{float(west)}, {delta}, 0.0, {float(north)}, 0.0, {-delta}</GeoTransform>\n"
        f'    <VRTRasterBand dataType="{vrt_dtype}" band="1" subClass="VRTRawRasterBand">\n'
        f"        <SourceFilename relativeToVRT=\"1\">{raster_file.name}</SourceFilename>\n"
        "        <ByteOrder>LSB</ByteOrder>\n"
        "        <ImageOffset>0</ImageOffset>\n"
        f"        <PixelOffset>{pixel_offset}</PixelOffset>\n"
        f"        <LineOffset>{line_offset}</LineOffset>\n"
        "    </VRTRasterBand>\n"
        "</VRTDataset>\n"
    )
    vrt_file.write_text(text, encoding="utf-8")
    return vrt_file


def _create_empty_dem_files_from_bounding_box(
    bounding_box: list[float],
    output_dir: str | Path,
) -> dict:
    """Create empty 1-arcsec DEM, 3-arcsec DEM, and 1-arcsec WBD files.

    DEM rasters are zero-valued signed 16-bit integers.
    WBD raster is filled with 1 and has the same extent/resolution as the
    1-arcsec DEM.
    """
    output_dir = Path(output_dir).resolve()
    south, north, west, east = _rounded_dem_extent(bounding_box)

    dem_1_dir = output_dir / "dem_1_arcsec"
    dem_3_dir = output_dir / "dem_3_arcsec"
    wbd_dir = output_dir / "wbd_1_arcsec"

    dem_1_file = dem_1_dir / _dem_filename(south, north, west, east)
    dem_3_file = dem_3_dir / _dem_filename(south, north, west, east)
    wbd_file = wbd_dir / _wbd_filename(south, north, west, east)

    width_1 = (east - west) * 3600
    length_1 = (north - south) * 3600
    delta_1 = 1.0 / 3600.0

    width_3 = (east - west) * 1200
    length_3 = (north - south) * 1200
    delta_3 = 1.0 / 1200.0

    _write_constant_binary_file(dem_1_file, width_1 * length_1, dtype_bytes=2, fill_byte=0)
    _write_isce_raster_xml(
        dem_1_file,
        width=width_1,
        length=length_1,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta_1,
        data_type="SHORT",
        family="demimage",
        image_type="dem",
        reference="WGS84",
    )
    _write_vrt(
        dem_1_file,
        width=width_1,
        length=length_1,
        west=west,
        north=north,
        delta=delta_1,
        vrt_dtype="Int16",
        pixel_offset=2,
        line_offset=width_1 * 2,
    )

    _write_constant_binary_file(dem_3_file, width_3 * length_3, dtype_bytes=2, fill_byte=0)
    _write_isce_raster_xml(
        dem_3_file,
        width=width_3,
        length=length_3,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta_3,
        data_type="SHORT",
        family="demimage",
        image_type="dem",
        reference="WGS84",
    )
    _write_vrt(
        dem_3_file,
        width=width_3,
        length=length_3,
        west=west,
        north=north,
        delta=delta_3,
        vrt_dtype="Int16",
        pixel_offset=2,
        line_offset=width_3 * 2,
    )

    _write_constant_binary_file(wbd_file, width_1 * length_1, dtype_bytes=1, fill_byte=1)
    _write_isce_raster_xml(
        wbd_file,
        width=width_1,
        length=length_1,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta_1,
        data_type="BYTE",
        family="image",
        image_type=None,
        reference=None,
    )
    _write_vrt(
        wbd_file,
        width=width_1,
        length=length_1,
        west=west,
        north=north,
        delta=delta_1,
        vrt_dtype="Byte",
        pixel_offset=1,
        line_offset=width_1,
    )

    return {
        "bounding_box": bounding_box,
        "extent": {
            "south": south,
            "north": north,
            "west": west,
            "east": east,
        },
        "dem_coreg": dem_1_file,
        "dem_geocode": dem_3_file,
        "water_body": wbd_file,
        "dem_1_arcsec": dem_1_file,
        "dem_3_arcsec": dem_3_file,
        "wbd_1_arcsec": wbd_file,
    }

def generate_dem(
    reference_input,
    secondary_input,
    work_dir,
    dem_coreg=None,
    dem_geocode=None,
    water_body=None,
    use_gpu=False,
    do_ionosphere=True,
    apply_ionosphere=True,
    run=True,
    alos2app_cmd="alos2App.py",
    do_insar=True,
    steps=True,
    start_step=None,
    end_step=None,
    geocode_file_list=None,
    interferogram_filter_strength=0.3,
    interferogram_filter_window_size=32,
    interferogram_filter_step_size=4,
    remove_magnitude_before_filtering=True,
) -> dict:
    """Generate DEM/topographic-phase products using internally created empty DEMs.

    This workflow keeps the same external structure as ``process_alos2_pair``,
    but removes the dense-offset parameters. It performs two runs internally:

    1. Run ``alos2App.py`` through ``baseline`` to obtain
       ``runBaseline.reference bounding box`` from the terminal log.
    2. Create empty DEM/WBD files from that bounding box:
       - 1-arcsec DEM, zero-valued int16, used for coregistration
       - 3-arcsec DEM, zero-valued int16, used for geocoding
       - 1-arcsec WBD, filled with 1, used as water-body mask
    3. Run ``alos2App.py`` with those DEM/WBD paths explicitly written into the
       XML, so ISCE does not attempt to download DEM files.

    If ``dem_coreg``, ``dem_geocode``, or ``water_body`` are provided, that path
    is respected and only missing files are generated internally.
    """
    validate_alos2_steps(start_step, end_step)

    work_dir = Path(work_dir).resolve()
    baseline_work_dir = work_dir / "baseline_for_empty_dem"
    empty_dem_dir = work_dir / "empty_dem"
    final_work_dir = work_dir / "final"

    user_provided_all_dem_paths = (
        dem_coreg is not None and dem_geocode is not None and water_body is not None
    )

    baseline_result = None
    empty_dem = None

    if not user_provided_all_dem_paths:
        baseline_result = process_alos2_pair(
            reference_input=reference_input,
            secondary_input=secondary_input,
            work_dir=baseline_work_dir,
            dem_coreg=dem_coreg,
            dem_geocode=dem_geocode,
            water_body=water_body,
            use_gpu=use_gpu,
            do_ionosphere=do_ionosphere,
            apply_ionosphere=apply_ionosphere,
            run=True,
            alos2app_cmd=alos2app_cmd,
            do_insar=do_insar,
            steps=steps,
            start_step=None,
            end_step="baseline",
            geocode_file_list=geocode_file_list,
            interferogram_filter_strength=interferogram_filter_strength,
            interferogram_filter_window_size=interferogram_filter_window_size,
            interferogram_filter_step_size=interferogram_filter_step_size,
            remove_magnitude_before_filtering=remove_magnitude_before_filtering,
            do_dense_offset=False,
            estimate_residual_offset_after_geometrical_coregistration=False,
            delete_geometry_files_used_for_dense_offset_estimation=False,
            dense_offset_estimation_window_width=64,
            dense_offset_estimation_window_height=64,
            dense_offset_skip_width=32,
            dense_offset_skip_height=32,
        )

        baseline_log = Path(baseline_result["run_dir"]) / "alos2App_full_terminal.log"
        bounding_box = _parse_reference_bounding_box_from_log(baseline_log)
        empty_dem = _create_empty_dem_files_from_bounding_box(
            bounding_box=bounding_box,
            output_dir=empty_dem_dir,
        )

        if dem_coreg is None:
            dem_coreg = empty_dem["dem_coreg"]
        if dem_geocode is None:
            dem_geocode = empty_dem["dem_geocode"]
        if water_body is None:
            water_body = empty_dem["water_body"]

    final_result = None

    if run:
        final_result = process_alos2_pair(
            reference_input=reference_input,
            secondary_input=secondary_input,
            work_dir=final_work_dir,
            dem_coreg=dem_coreg,
            dem_geocode=dem_geocode,
            water_body=water_body,
            use_gpu=use_gpu,
            do_ionosphere=do_ionosphere,
            apply_ionosphere=apply_ionosphere,
            run=True,
            alos2app_cmd=alos2app_cmd,
            do_insar=do_insar,
            steps=steps,
            start_step=start_step,
            end_step=end_step,
            geocode_file_list=geocode_file_list,
            interferogram_filter_strength=interferogram_filter_strength,
            interferogram_filter_window_size=interferogram_filter_window_size,
            interferogram_filter_step_size=interferogram_filter_step_size,
            remove_magnitude_before_filtering=remove_magnitude_before_filtering,
            do_dense_offset=False,
            estimate_residual_offset_after_geometrical_coregistration=False,
            delete_geometry_files_used_for_dense_offset_estimation=False,
            dense_offset_estimation_window_width=64,
            dense_offset_estimation_window_height=64,
            dense_offset_skip_width=32,
            dense_offset_skip_height=32,
        )

    return {
        "baseline_result": baseline_result,
        "final_result": final_result,
        "empty_dem": empty_dem,
        "dem_coreg": Path(dem_coreg).resolve() if dem_coreg is not None else None,
        "dem_geocode": Path(dem_geocode).resolve() if dem_geocode is not None else None,
        "water_body": Path(water_body).resolve() if water_body is not None else None,
        "work_dir": work_dir,
        "baseline_work_dir": baseline_work_dir,
        "final_work_dir": final_work_dir,
        "xml_file": None if final_result is None else final_result["xml_file"],
        "run_dir": None if final_result is None else final_result["run_dir"],
        "stdout": None if final_result is None else final_result["stdout"],
        "stderr": None if final_result is None else final_result["stderr"],
    }

# ---------------------------------------------------------------------------
# Phase-to-height conversion helpers
# ---------------------------------------------------------------------------

def _xml_property_value(root, name: str) -> str | None:
    """Find an ISCE XML property value by property name."""
    name = name.lower()
    for prop in root.iter("property"):
        if prop.attrib.get("name", "").lower() != name:
            continue

        value = prop.find("value")
        if value is not None and value.text is not None:
            return value.text.strip()

        if prop.text is not None and prop.text.strip():
            return prop.text.strip()

    return None


def read_track_metadata(track_xml: str | Path) -> dict[str, float]:
    """Read radar wavelength and slant-range metadata from an ISCE track XML.

    Parameters
    ----------
    track_xml : str or Path
        Path to ``YYMMDD.track.xml``.

    Returns
    -------
    dict
        Contains available values among:
        ``radar_wavelength``, ``starting_range``, ``range_pixel_size``,
        ``number_of_samples``, and ``number_of_lines``.
    """
    import xml.etree.ElementTree as ET

    track_xml = Path(track_xml)
    root = ET.parse(track_xml).getroot()

    def get_float(name):
        value = _xml_property_value(root, name)
        return None if value is None else float(value)

    def get_int(name):
        value = _xml_property_value(root, name)
        return None if value is None else int(float(value))

    return {
        "radar_wavelength": get_float("radarwavelength"),
        "starting_range": get_float("startingrange"),
        "range_pixel_size": get_float("rangepixelsize"),
        "number_of_samples": get_int("numberofsamples"),
        "number_of_lines": get_int("numberoflines"),
    }


def read_isce_raster_metadata(raster_file: str | Path) -> dict:
    """Read width, length, dtype, number of bands, and scheme from ISCE XML."""
    import xml.etree.ElementTree as ET
    import numpy as np

    raster_file = Path(raster_file)
    xml_file = Path(str(raster_file) + ".xml")

    if not xml_file.exists():
        raise FileNotFoundError(f"Could not find ISCE XML metadata: {xml_file}")

    root = ET.parse(xml_file).getroot()

    dtype_map = {
        "BYTE": np.uint8,
        "SHORT": np.int16,
        "INT": np.int32,
        "LONG": np.int64,
        "FLOAT": np.float32,
        "DOUBLE": np.float64,
        "CFLOAT": np.complex64,
        "CDOUBLE": np.complex128,
    }

    width = _xml_property_value(root, "width")
    length = _xml_property_value(root, "length")
    data_type = _xml_property_value(root, "data_type") or "FLOAT"
    number_bands = _xml_property_value(root, "number_bands") or "1"
    scheme = (_xml_property_value(root, "scheme") or "BIP").upper()

    if width is None or length is None:
        raise ValueError(f"Could not read width/length from {xml_file}")

    data_type_key = data_type.upper()
    if data_type_key not in dtype_map:
        raise ValueError(f"Unsupported ISCE data_type={data_type!r} in {xml_file}")

    return {
        "width": int(width),
        "length": int(length),
        "dtype": np.dtype(dtype_map[data_type_key]),
        "data_type": data_type_key,
        "number_bands": int(number_bands),
        "scheme": scheme,
    }


def read_isce_raster(
    raster_file: str | Path,
    band: int | None = None,
    metadata: dict | None = None,
):
    """Read an ISCE raw binary raster.

    Supports common single/multi-band ISCE schemes: ``BIP``, ``BIL``, and
    ``BSQ``. Band indexing is zero-based. If ``band`` is omitted, the full
    array is returned.

    Returns
    -------
    numpy.ndarray
        Single band shape is ``(length, width)``. Full multi-band output shape
        depends on scheme-normalized representation: ``(bands, length, width)``.
    """
    import numpy as np

    raster_file = Path(raster_file)
    meta = metadata or read_isce_raster_metadata(raster_file)

    width = meta["width"]
    length = meta["length"]
    dtype = meta["dtype"]
    number_bands = meta["number_bands"]
    scheme = meta["scheme"].upper()

    data = np.fromfile(raster_file, dtype=dtype)
    expected = width * length * number_bands

    if data.size != expected:
        raise ValueError(
            f"Raster size mismatch for {raster_file}: "
            f"found {data.size}, expected {expected} "
            f"({length} x {width} x {number_bands})"
        )

    if number_bands == 1:
        arr = data.reshape(length, width)
        if band is not None and band != 0:
            raise ValueError(f"Requested band={band}, but raster has only one band")
        return arr

    if scheme == "BIP":
        arr = data.reshape(length, width, number_bands).transpose(2, 0, 1)
    elif scheme == "BIL":
        # BIL layout is line-major: for each row, all bands are stored
        # consecutively. Normalize to (bands, length, width).
        arr = data.reshape(length, number_bands, width).transpose(1, 0, 2)
    elif scheme == "BSQ":
        arr = data.reshape(number_bands, length, width)
    else:
        raise ValueError(f"Unsupported raster scheme={scheme!r} for {raster_file}")

    if band is None:
        return arr

    if band < 0 or band >= number_bands:
        raise ValueError(
            f"Requested band={band}, but raster has {number_bands} bands"
        )

    return arr[band]


def read_los_incidence_angle(
    los_file: str | Path,
    incidence_band: int = 0,
    degrees: bool | None = None,
):
    """Read incidence angle from a two-band ISCE ``*.los`` file.

    By convention for your file:
    - band 0: incidence angle
    - band 1: satellite heading

    Parameters
    ----------
    los_file : str or Path
        Path to ``*.los``.
    incidence_band : int, default 0
        Zero-based incidence band index.
    degrees : bool or None, default None
        If None, infer unit from values. Values larger than pi are interpreted
        as degrees and converted to radians.

    Returns
    -------
    numpy.ndarray
        Incidence angle in radians.
    """
    import numpy as np

    incidence = read_isce_raster(los_file, band=incidence_band).astype(np.float32)

    if degrees is None:
        finite = incidence[np.isfinite(incidence)]
        degrees = bool(finite.size > 0 and np.nanmedian(np.abs(finite)) > np.pi)

    if degrees:
        incidence = np.deg2rad(incidence)

    return incidence


def make_bperp_image(
    shape: tuple[int, int],
    center: float,
    lowerleft: float,
    lowerright: float,
    upperleft: float,
    upperright: float,
):
    """Create a perpendicular-baseline image from corner and center values.

    The image exactly matches the four corner values and the center value. It
    starts from bilinear interpolation of the corners, then adds a smooth
    zero-at-the-corners correction to match the center.
    """
    import numpy as np

    length, width = shape

    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, length, dtype=np.float32)[:, None]

    bperp = (
        upperleft * (1.0 - x) * (1.0 - y)
        + upperright * x * (1.0 - y)
        + lowerleft * (1.0 - x) * y
        + lowerright * x * y
    )

    bilinear_center = 0.25 * (upperleft + upperright + lowerleft + lowerright)
    center_delta = center - bilinear_center

    # 0 at corners and edges; 1 at image center.
    center_bubble = 16.0 * x * (1.0 - x) * y * (1.0 - y)
    bperp = bperp + center_delta * center_bubble

    return bperp.astype(np.float32)


def parse_bperp_values_from_log(log_file: str | Path) -> dict[str, float]:
    """Parse perpendicular baseline values from ``alos2App.py`` terminal log."""
    log_file = Path(log_file)

    if not log_file.exists():
        raise FileNotFoundError(f"Log file not found: {log_file}")

    text = log_file.read_text(encoding="utf-8", errors="replace")

    labels = {
        "center": "center",
        "lowerleft": "lowerleft",
        "lowerright": "lowerright",
        "upperleft": "upperleft",
        "upperright": "upperright",
    }

    out = {}
    for key, label in labels.items():
        pattern = (
            rf"runBaseline\.perpendicular baseline at {label} "
            rf"of reference track\s*=\s*(?P<value>[-+0-9.eE]+)"
        )
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(
                f"Could not parse perpendicular baseline value for {label} "
                f"from {log_file}"
            )
        out[key] = float(match.group("value"))

    return out


def make_bperp_image_from_log(
    log_file: str | Path,
    shape: tuple[int, int],
):
    """Create a perpendicular-baseline image by parsing an ISCE log file."""
    values = parse_bperp_values_from_log(log_file)
    return make_bperp_image(shape=shape, **values)


def infer_range_looks_from_filename(path: str | Path, default: int | None = None) -> int:
    """Infer range looks from names like ``*_8rlks_16alks.*``."""
    name = Path(path).name
    match = re.search(r"_(\d+)rlks_(\d+)alks", name)

    if match is None:
        if default is None:
            raise ValueError(
                f"Could not infer range looks from filename: {name}. "
                "Provide range_looks explicitly."
            )
        return int(default)

    return int(match.group(1))


def make_slant_range_image(
    shape: tuple[int, int],
    starting_range: float,
    range_pixel_size: float,
    range_looks: int = 1,
):
    """Create a slant-range image/row vector for a multilooked radar product.

    The returned array has shape ``(1, width)`` so it broadcasts over rows.
    """
    import numpy as np

    _, width = shape
    columns = np.arange(width, dtype=np.float32)

    slant_range = (
        float(starting_range)
        + columns * float(range_pixel_size) * int(range_looks)
    )

    return slant_range[None, :].astype(np.float32)


def make_slant_range_image_from_track_xml(
    shape: tuple[int, int],
    track_xml: str | Path,
    range_looks: int = 1,
):
    """Create a slant-range image/row vector using ``YYMMDD.track.xml``."""
    meta = read_track_metadata(track_xml)

    missing = [
        key
        for key in ["starting_range", "range_pixel_size"]
        if meta.get(key) is None
    ]
    if missing:
        raise ValueError(f"Missing required track XML values: {missing}")

    return make_slant_range_image(
        shape=shape,
        starting_range=meta["starting_range"],
        range_pixel_size=meta["range_pixel_size"],
        range_looks=range_looks,
    )


def read_radar_wavelength(track_xml: str | Path) -> float:
    """Read radar wavelength in meters from ``YYMMDD.track.xml``."""
    meta = read_track_metadata(track_xml)

    if meta.get("radar_wavelength") is None:
        raise ValueError(f"Could not find radarwavelength in {track_xml}")

    return meta["radar_wavelength"]


def write_float_raster_with_xml_like(
    output_file: str | Path,
    array,
    template_raster: str | Path,
    data_type: str = "FLOAT",
) -> Path:
    """Write a float32 raster and copy basic dimensions from a template XML."""
    import numpy as np
    import xml.etree.ElementTree as ET

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    arr = np.asarray(array, dtype=np.float32)
    arr.tofile(output_file)

    template_meta = read_isce_raster_metadata(template_raster)
    xml_file = Path(str(output_file) + ".xml")

    # Minimal ISCE XML sufficient for reading dimensions/dtype later.
    root = ET.Element("imageFile")

    def add_prop(name, value):
        prop = ET.SubElement(root, "property", name=name)
        val = ET.SubElement(prop, "value")
        val.text = str(value)

    add_prop("access_mode", "READ")
    add_prop("byte_order", "l")
    add_prop("data_type", data_type)
    add_prop("file_name", str(output_file.resolve()))
    add_prop("length", template_meta["length"])
    add_prop("number_bands", 1)
    add_prop("scheme", "BIP")
    add_prop("width", template_meta["width"])

    ET.ElementTree(root).write(xml_file, encoding="utf-8", xml_declaration=False)

    return output_file


def phase_to_height(
    phase,
    bperp,
    incidence_angle,
    wavelength: float,
    slant_range,
    sign: float = 1.0,
    invalid_value: float = 0.0,
):
    """Convert topographic phase to height pixel by pixel.

    Formula
    -------
    ``height = sign * phase * wavelength * R * sin(theta) / (4*pi*Bperp)``

    Parameters
    ----------
    phase : array-like
        Topographic phase in radians.
    bperp : array-like
        Perpendicular baseline in meters.
    incidence_angle : array-like
        Incidence angle in radians.
    wavelength : float
        Radar wavelength in meters.
    slant_range : array-like
        Slant range in meters. Can be scalar, ``(1, width)``, or full 2D image.
    sign : float, default 1.0
        Use ``-1`` if the output topography is inverted.
    invalid_value : float, default 0.0
        Value used where output is NaN/Inf.

    Returns
    -------
    numpy.ndarray
        Height in meters.
    """
    import numpy as np

    phase = np.asarray(phase, dtype=np.float32)
    bperp = np.asarray(bperp, dtype=np.float32)
    incidence_angle = np.asarray(incidence_angle, dtype=np.float32)
    slant_range = np.asarray(slant_range, dtype=np.float32)

    with np.errstate(divide="ignore", invalid="ignore"):
        height = (
            float(sign)
            * phase
            * float(wavelength)
            * slant_range
            * np.sin(incidence_angle)
            / (4.0 * np.pi * bperp)
        )

    height = np.where(np.isfinite(height), height, invalid_value)
    return height.astype(np.float32)


def convert_phase_to_height(
    phase_file: str | Path,
    los_file: str | Path,
    track_xml: str | Path,
    baseline_log: str | Path,
    output_file: str | Path,
    range_looks: int | None = None,
    phase_band: int | None = None,
    phase_is_complex: bool | None = None,
    incidence_band: int = 0,
    incidence_degrees: bool | None = None,
    sign: float = 1.0,
    invalid_value: float = 0.0,
) -> dict:
    """Convert an ISCE topographic phase raster to height.

    This high-level helper reads:
    - phase from ``phase_file``
    - incidence angle from band 0 of ``los_file``
    - radar wavelength, starting range, and range pixel size from ``track_xml``
    - five perpendicular baseline values from ``baseline_log``

    Parameters
    ----------
    phase_file : str or Path
        Topographic phase raster. If it is complex and ``phase_is_complex`` is
        True, ``np.angle`` is used.
    los_file : str or Path
        Two-band LOS file. Band 0 is incidence angle.
    track_xml : str or Path
        Reference ``YYMMDD.track.xml`` file.
    baseline_log : str or Path
        ``alos2App_full_terminal.log`` containing perpendicular baseline values.
    output_file : str or Path
        Output height raster path.
    range_looks : int, optional
        Range looks of the phase product. If omitted, inferred from
        ``phase_file`` name like ``*_8rlks_16alks.*``.
    phase_band : int, optional
        Band to read if phase raster is multi-band. If omitted for an ISCE
        ``.unw`` file, band 1 is used automatically because band 0 is usually
        amplitude/coherence-like and band 1 is unwrapped phase.
    phase_is_complex : bool, optional
        If None, complex dtype is detected automatically.
    sign : float, default 1.0
        Use ``-1.0`` if the recovered topography is inverted.

    Returns
    -------
    dict
        Paths and arrays used in the conversion metadata. Large arrays are not
        returned, only paths and scalar metadata.
    """
    import numpy as np

    phase_file = Path(phase_file)
    los_file = Path(los_file)
    track_xml = Path(track_xml)
    baseline_log = Path(baseline_log)
    output_file = Path(output_file)

    phase_meta = read_isce_raster_metadata(phase_file)

    if phase_band is None and phase_meta["number_bands"] > 1:
        # ISCE .unw files are commonly two-band BIL rasters:
        # band 0 = amplitude/coherence-like quantity, band 1 = unwrapped phase.
        if phase_file.suffix.lower() == ".unw":
            phase_band = 1
        else:
            raise ValueError(
                f"{phase_file} has {phase_meta['number_bands']} bands. "
                "Please provide phase_band explicitly. For ISCE .unw files, "
                "the unwrapped phase is usually phase_band=1."
            )

    raw_phase = read_isce_raster(phase_file, band=phase_band, metadata=phase_meta)

    if phase_is_complex is None:
        phase_is_complex = np.iscomplexobj(raw_phase)

    if phase_is_complex:
        phase = np.angle(raw_phase).astype(np.float32)
    else:
        phase = raw_phase.astype(np.float32)

    shape = phase.shape

    incidence = read_los_incidence_angle(
        los_file,
        incidence_band=incidence_band,
        degrees=incidence_degrees,
    )

    if incidence.shape != shape:
        raise ValueError(
            f"Incidence shape {incidence.shape} does not match phase shape {shape}. "
            "Check that phase_file and los_file have the same looks/extent."
        )

    bperp_values = parse_bperp_values_from_log(baseline_log)
    bperp = make_bperp_image(shape=shape, **bperp_values)

    if range_looks is None:
        range_looks = infer_range_looks_from_filename(phase_file)

    track_meta = read_track_metadata(track_xml)
    wavelength = track_meta["radar_wavelength"]

    if wavelength is None:
        raise ValueError(f"Could not read radarwavelength from {track_xml}")

    slant_range = make_slant_range_image_from_track_xml(
        shape=shape,
        track_xml=track_xml,
        range_looks=range_looks,
    )

    height = phase_to_height(
        phase=phase,
        bperp=bperp,
        incidence_angle=incidence,
        wavelength=wavelength,
        slant_range=slant_range,
        sign=sign,
        invalid_value=invalid_value,
    )

    write_float_raster_with_xml_like(
        output_file=output_file,
        array=height,
        template_raster=phase_file,
        data_type="FLOAT",
    )

    return {
        "output_file": output_file,
        "output_xml": Path(str(output_file) + ".xml"),
        "phase_file": phase_file,
        "los_file": los_file,
        "track_xml": track_xml,
        "baseline_log": baseline_log,
        "shape": shape,
        "range_looks": range_looks,
        "wavelength": wavelength,
        "starting_range": track_meta["starting_range"],
        "range_pixel_size": track_meta["range_pixel_size"],
        "bperp_values": bperp_values,
        "sign": sign,
    }

# ---------------------------------------------------------------------------
# Geocoding and DEM-comparison helpers
# ---------------------------------------------------------------------------

def write_isce_geocoded_float(
    output_file: str | Path,
    array,
    lon_min: float,
    lat_max: float,
    resolution: float,
) -> dict:
    """Write a geocoded float32 raster in ISCE raw + XML + VRT format.

    Parameters
    ----------
    output_file : str or Path
        Output raw raster file, e.g. ``height_from_phase_geo.dem``.
    array : array-like
        2D geocoded raster.
    lon_min : float
        Western edge / starting longitude.
    lat_max : float
        Northern edge / starting latitude.
    resolution : float
        Geographic pixel spacing in degrees.

    Returns
    -------
    dict
        Output file paths and shape.
    """
    import numpy as np

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    array = np.asarray(array, dtype=np.float32)
    length, width = array.shape
    array.tofile(output_file)

    xml_file = Path(str(output_file) + ".xml")
    vrt_file = Path(str(output_file) + ".vrt")

    lon_max = lon_min + width * resolution
    lat_min = lat_max - length * resolution

    xml_file.write_text(
        f"""<imageFile>
    <property name="access_mode"><value>READ</value></property>
    <property name="byte_order"><value>l</value></property>
    <component name="coordinate1">
        <property name="delta"><value>{resolution}</value></property>
        <property name="endingvalue"><value>{lon_max}</value></property>
        <property name="size"><value>{width}</value></property>
        <property name="startingvalue"><value>{lon_min}</value></property>
    </component>
    <component name="coordinate2">
        <property name="delta"><value>{-resolution}</value></property>
        <property name="endingvalue"><value>{lat_min}</value></property>
        <property name="size"><value>{length}</value></property>
        <property name="startingvalue"><value>{lat_max}</value></property>
    </component>
    <property name="data_type"><value>FLOAT</value></property>
    <property name="extra_file_name"><value>{output_file.name}.vrt</value></property>
    <property name="family"><value>image</value></property>
    <property name="file_name"><value>{output_file.resolve()}</value></property>
    <property name="length"><value>{length}</value></property>
    <property name="number_bands"><value>1</value></property>
    <property name="scheme"><value>BIP</value></property>
    <property name="width"><value>{width}</value></property>
    <property name="xmax"><value>{lon_max}</value></property>
    <property name="xmin"><value>{lon_min}</value></property>
</imageFile>
""",
        encoding="utf-8",
    )

    vrt_file.write_text(
        f"""<VRTDataset rasterXSize="{width}" rasterYSize="{length}">
    <SRS>EPSG:4326</SRS>
    <GeoTransform>{lon_min}, {resolution}, 0.0, {lat_max}, 0.0, {-resolution}</GeoTransform>
    <VRTRasterBand dataType="Float32" band="1" subClass="VRTRawRasterBand">
        <SourceFilename relativeToVRT="1">{output_file.name}</SourceFilename>
        <ByteOrder>LSB</ByteOrder>
        <ImageOffset>0</ImageOffset>
        <PixelOffset>4</PixelOffset>
        <LineOffset>{width * 4}</LineOffset>
    </VRTRasterBand>
</VRTDataset>
""",
        encoding="utf-8",
    )

    return {
        "output_file": output_file,
        "xml_file": xml_file,
        "vrt_file": vrt_file,
        "shape": array.shape,
    }


def geocode_raster(
    input_file: str | Path,
    lat_file: str | Path,
    lon_file: str | Path,
    output_file: str | Path,
    resolution: float = 1 / 3600,
    method: str = "linear",
    nodata=float("nan"),
) -> dict:
    """Geocode a radar-coordinate raster using ISCE latitude/longitude rasters.

    The output is written in ISCE raw + XML + VRT format, not GeoTIFF.

    Parameters
    ----------
    input_file : str or Path
        Radar-coordinate raster to geocode.
    lat_file : str or Path
        ISCE latitude raster with same shape as ``input_file``.
    lon_file : str or Path
        ISCE longitude raster with same shape as ``input_file``.
    output_file : str or Path
        Output raw raster path, e.g. ``height_from_phase_geo.dem``.
    resolution : float, default 1/3600
        Output geographic resolution in degrees.
    method : {"linear", "nearest", "cubic"}, default "linear"
        Interpolation method passed to ``scipy.interpolate.griddata``.
    nodata : float, default NaN
        Fill value for output pixels outside interpolation support.

    Returns
    -------
    dict
        Output paths, shape, extent, resolution, and method.
    """
    import numpy as np
    from scipy.interpolate import griddata

    input_file = Path(input_file)
    lat_file = Path(lat_file)
    lon_file = Path(lon_file)
    output_file = Path(output_file)

    data = read_isce_raster(input_file)
    lat = read_isce_raster(lat_file)
    lon = read_isce_raster(lon_file)

    if data.shape != lat.shape or data.shape != lon.shape:
        raise ValueError(
            f"Shape mismatch:\n"
            f"data: {data.shape}\n"
            f"lat : {lat.shape}\n"
            f"lon : {lon.shape}"
        )

    mask = (
        np.isfinite(data)
        & np.isfinite(lat)
        & np.isfinite(lon)
        & (lat != 0)
        & (lon != 0)
    )

    if not np.any(mask):
        raise ValueError("No valid pixels found after masking data/lat/lon.")

    values = data[mask]
    lats = lat[mask]
    lons = lon[mask]

    lon_min = float(np.nanmin(lons))
    lon_max = float(np.nanmax(lons))
    lat_min = float(np.nanmin(lats))
    lat_max = float(np.nanmax(lats))

    grid_lon = np.arange(lon_min, lon_max + resolution, resolution)
    grid_lat = np.arange(lat_max, lat_min - resolution, -resolution)

    grid_lon2d, grid_lat2d = np.meshgrid(grid_lon, grid_lat)

    geo = griddata(
        np.column_stack([lons, lats]),
        values,
        (grid_lon2d, grid_lat2d),
        method=method,
        fill_value=nodata,
    ).astype(np.float32)

    out = write_isce_geocoded_float(
        output_file=output_file,
        array=geo,
        lon_min=lon_min,
        lat_max=lat_max,
        resolution=resolution,
    )

    out.update(
        {
            "extent": {
                "lon_min": lon_min,
                "lon_max": lon_max,
                "lat_min": lat_min,
                "lat_max": lat_max,
            },
            "resolution": resolution,
            "method": method,
        }
    )

    return out


def remove_mean_offset(pred, ref, mask):
    """Remove median offset between predicted/generated and reference rasters."""
    import numpy as np

    offset = np.nanmedian(pred[mask] - ref[mask])
    return pred - offset, offset


def plot_dem_comparison(
    generated_dem_file: str | Path,
    reference_dem_file: str | Path,
    remove_offset: bool = True,
    vmin=None,
    vmax=None,
    residual_vlim=None,
    cmap: str = "terrain",
):
    """Plot generated DEM, reference DEM, and residual.

    Parameters
    ----------
    generated_dem_file : str or Path
        Generated DEM raster readable by ``read_isce_raster``.
    reference_dem_file : str or Path
        Reference DEM raster readable by ``read_isce_raster``.
    remove_offset : bool, default True
        If True, remove median offset from generated DEM before residual.
    vmin, vmax : float, optional
        Shared color limits for generated/reference panels.
    residual_vlim : float, optional
        Symmetric residual color limit.
    cmap : str, default "terrain"
        Colormap for DEM panels.

    Returns
    -------
    dict
        Generated/reference/residual arrays, mask, and removed offset.
    """
    import numpy as np
    import matplotlib.pyplot as plt

    gen = read_isce_raster(generated_dem_file).astype(np.float32)
    ref = read_isce_raster(reference_dem_file).astype(np.float32)

    if gen.shape != ref.shape:
        raise ValueError(
            f"Shape mismatch: generated={gen.shape}, reference={ref.shape}"
        )

    mask = np.isfinite(gen) & np.isfinite(ref) & (ref != 0)

    if not np.any(mask):
        raise ValueError("No valid pixels found for DEM comparison.")

    offset = 0.0
    if remove_offset:
        gen, offset = remove_mean_offset(gen, ref, mask)

    residual = gen - ref

    if vmin is None:
        vmin = np.nanpercentile(ref[mask], 2)
    if vmax is None:
        vmax = np.nanpercentile(ref[mask], 98)

    if residual_vlim is None:
        residual_vlim = np.nanpercentile(np.abs(residual[mask]), 98)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    im0 = axes[0].imshow(gen, cmap=cmap, vmin=vmin, vmax=vmax)
    axes[0].set_title(f"Generated DEM\noffset removed = {offset:.2f} m")
    axes[0].axis("off")
    plt.colorbar(im0, ax=axes[0], fraction=0.046, label="m")

    im1 = axes[1].imshow(ref, cmap=cmap, vmin=vmin, vmax=vmax)
    axes[1].set_title("Reference DEM")
    axes[1].axis("off")
    plt.colorbar(im1, ax=axes[1], fraction=0.046, label="m")

    im2 = axes[2].imshow(
        residual,
        cmap="RdBu_r",
        vmin=-residual_vlim,
        vmax=residual_vlim,
    )
    axes[2].set_title(
        f"Residual: Generated - Reference\n"
        f"median={np.nanmedian(residual[mask]):.2f} m, "
        f"std={np.nanstd(residual[mask]):.2f} m"
    )
    axes[2].axis("off")
    plt.colorbar(im2, ax=axes[2], fraction=0.046, label="m")

    plt.tight_layout()
    plt.show()

    print("Generated DEM:", gen.shape, np.nanmin(gen), np.nanmax(gen))
    print("Reference DEM:", ref.shape, np.nanmin(ref), np.nanmax(ref))
    print("Residual median:", np.nanmedian(residual[mask]))
    print("Residual mean:", np.nanmean(residual[mask]))
    print("Residual std:", np.nanstd(residual[mask]))
    print("Residual RMSE:", np.sqrt(np.nanmean(residual[mask] ** 2)))

    return {
        "generated": gen,
        "reference": ref,
        "residual": residual,
        "mask": mask,
        "offset_removed": offset,
    }
