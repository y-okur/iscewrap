"""High-level ALOS-2 pair processing workflow."""

from __future__ import annotations

from pathlib import Path
import http.cookiejar
import json
import math
import netrc
import shutil
import re
import subprocess
import urllib.parse
import urllib.request
import zipfile

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
    auto_prepare_dem=True,
    dem_overwrite=False,
    convert_dem_to_wgs84_ellipsoid=True,
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
    polarizations=None,
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
        extract_alos2_zip(reference_input, raw_dir, polarizations=polarizations)
        if reference_input.suffix.lower() == ".zip"
        else reference_input
    )
    secondary_dir = (
        extract_alos2_zip(secondary_input, raw_dir, polarizations=polarizations)
        if secondary_input.suffix.lower() == ".zip"
        else secondary_input
    )

    reference_meta = detect_product_metadata(reference_dir)
    secondary_meta = detect_product_metadata(secondary_dir)

    reference_dir = _select_alos2_processing_dir(reference_dir, reference_meta)
    secondary_dir = _select_alos2_processing_dir(secondary_dir, secondary_meta)

    reference_info = reference_meta["img_info"]
    secondary_info = secondary_meta["img_info"]

    multilook_params = reference_meta["multilook"]

    pair_name = f"{reference_info['date']}_{secondary_info['date']}"
    xml_file = (xml_dir / f"alos2App_{pair_name}.xml").resolve()

    dem_result = None
    baseline_result = None
    missing_dem_inputs = dem_coreg is None or dem_geocode is None or water_body is None

    if auto_prepare_dem and missing_dem_inputs and run:
        # First create a minimal XML without DEM/WBD paths and run through
        # baseline only. The baseline log gives the scene geographic bounding
        # box needed for local SRTM/WBD preparation.
        create_alos2app_xml(
            reference_dir=reference_dir,
            secondary_dir=secondary_dir,
            output_xml=xml_file,
            # reference_frame=reference_info["frame"],
            # secondary_frame=secondary_info["frame"],
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

        baseline_result = run_isce2_alos2app(
            xml_file=xml_file,
            work_dir=run_dir,
            alos2app_cmd=alos2app_cmd,
            start_step=None,
            end_step="baseline",
            steps=steps,
        )
        baseline_log = run_dir / "alos2App_full_terminal.log"
        bounding_box = _parse_reference_bounding_box_from_log(baseline_log)
        dem_result = prepare_srtm_dem_and_wbd(
            bounding_box=bounding_box,
            output_dir=work_dir / "dem",
            dem_coreg=dem_coreg,
            dem_geocode=dem_geocode,
            water_body=water_body,
            overwrite=dem_overwrite,
            convert_to_wgs84_ellipsoid=convert_dem_to_wgs84_ellipsoid,
        )
        dem_coreg = dem_result["dem_coreg"]
        dem_geocode = dem_result["dem_geocode"]
        water_body = dem_result["water_body"]

    create_alos2app_xml(
        reference_dir=reference_dir,
        secondary_dir=secondary_dir,
        output_xml=xml_file,
        # reference_frame=reference_info["frame"],
        # secondary_frame=secondary_info["frame"],
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

    result = baseline_result

    if run:
        # If the user only asked for baseline and auto DEM preparation already
        # ran that step, keep the baseline result and avoid running it twice.
        if not (baseline_result is not None and end_step == "baseline"):
            dense_offset_requested = _dense_offset_step_requested(
                start_step=start_step,
                end_step=end_step,
                do_dense_offset=do_dense_offset,
            )

            if dense_offset_requested and _step_index(start_step) < _step_index("dense_offset"):
                # Dense-offset processing in alos2App.py expects generic WBD
                # files named wbd.rdr(.xml/.vrt), while earlier ALOS-2 steps
                # create pair/look-specific names such as
                # YYMMDD-YYMMDD_2rlks_4alks.wbd.  Run up to slc_match first
                # so those WBD files exist, prepare the compatibility names,
                # then continue from dense_offset.
                first_end_step = "slc_match"
                result = run_isce2_alos2app(
                    xml_file=xml_file,
                    work_dir=run_dir,
                    alos2app_cmd=alos2app_cmd,
                    start_step=start_step,
                    end_step=first_end_step,
                    steps=steps,
                )
                prepare_dense_offset_wbd(
                    run_dir=run_dir,
                    multilook_params=multilook_params,
                )
                result = run_isce2_alos2app(
                    xml_file=xml_file,
                    work_dir=run_dir,
                    alos2app_cmd=alos2app_cmd,
                    start_step="dense_offset",
                    end_step=end_step,
                    steps=steps,
                )
            else:
                if dense_offset_requested:
                    prepare_dense_offset_wbd(
                        run_dir=run_dir,
                        multilook_params=multilook_params,
                    )

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
        "dem_result": dem_result,
        "dem_coreg": None if dem_coreg is None else Path(dem_coreg).resolve(),
        "dem_geocode": None if dem_geocode is None else Path(dem_geocode).resolve(),
        "water_body": None if water_body is None else Path(water_body).resolve(),
        "start_step": start_step,
        "end_step": end_step,
        "stdout": None if result is None else result.stdout,
        "stderr": None if result is None else result.stderr,
    }


def _select_alos2_processing_dir(input_dir: Path, metadata: dict) -> Path:
    """Use product root for one product, or preserve a folder of stitched frames."""
    img_roots = {img_file.parent.resolve() for img_file in metadata["files"]["IMG"]}
    if len(img_roots) == 1:
        return metadata["product_root"]
    return input_dir.resolve()


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



def _step_index(step: str | None) -> int:
    """Return the alos2App.py processing-step index.

    ``None`` is treated as the beginning of the processing chain.
    """
    from .constants import ALOS2APP_STEPS

    if step is None:
        return 0
    return ALOS2APP_STEPS.index(step)


def _dense_offset_step_requested(
    start_step: str | None,
    end_step: str | None,
    do_dense_offset: bool,
) -> bool:
    """Return True when the requested processing range includes dense_offset."""
    if not do_dense_offset:
        return False

    from .constants import ALOS2APP_STEPS

    dense_index = ALOS2APP_STEPS.index("dense_offset")
    start_index = _step_index(start_step)
    end_index = len(ALOS2APP_STEPS) - 1 if end_step is None else _step_index(end_step)
    return start_index <= dense_index <= end_index


def _copy_and_retarget_isce_sidecars(src: Path, dst: Path) -> None:
    """Copy an ISCE raster and sidecars, retargeting sidecar filenames.

    ISCE XML/VRT sidecars may store either a relative basename or an absolute
    ``file_name``.  When copying a pair-specific WBD such as
    ``insar/201127-210122_2rlks_4alks.wbd`` to ``dense_offset/wbd.rdr``, both
    forms must be rewritten; otherwise ISCE can still try to read the original
    file from the wrong directory.
    """
    src = Path(src).resolve()
    dst = Path(dst).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    for suffix in ["", ".xml", ".vrt"]:
        src_file = Path(str(src) + suffix)
        dst_file = Path(str(dst) + suffix)

        if not src_file.exists():
            raise FileNotFoundError(f"Required source file not found: {src_file}")

        shutil.copy2(src_file, dst_file)

        if suffix in {".xml", ".vrt"}:
            sidecar_text = dst_file.read_text(encoding="utf-8", errors="replace")

            # Replace most-specific paths first, then fallback to basename.
            replacements = [
                (str(src_file.resolve()), str(dst_file.resolve())),
                (str(src.resolve()), str(dst.resolve())),
                (src_file.name, dst_file.name),
                (src.name, dst.name),
            ]
            for old, new in replacements:
                sidecar_text = sidecar_text.replace(old, new)

            dst_file.write_text(sidecar_text, encoding="utf-8")


def prepare_dense_offset_wbd(run_dir: str | Path, multilook_params: dict) -> Path:
    """Prepare generic ``wbd.rdr`` files required by ISCE2 dense_offset.

    ALOS-2 processing steps create radar-coordinate water-body files with
    pair/look-specific names, for example::

        insar/YYMMDD-YYMMDD_2rlks_4alks.wbd

    but some ISCE2 dense-offset code expects the generic basename::

        wbd.rdr

    relative to the dense-offset working directory.  This helper finds the WBD
    file matching the mode-dependent first-stage multilooks, then writes
    ``wbd.rdr``, ``wbd.rdr.xml``, and ``wbd.rdr.vrt`` only inside
    ``run/dense_offset/``. The source WBD is still searched in the normal ISCE
    output locations such as ``run/insar/``.
    """
    run_dir = Path(run_dir).resolve()
    insar_dir = run_dir / "insar"
    dense_dir = run_dir / "dense_offset"
    dense_dir.mkdir(parents=True, exist_ok=True)

    range_looks = int(multilook_params["number of range looks 1"])
    azimuth_looks = int(multilook_params["number of azimuth looks 1"])
    pattern = f"*_{range_looks}rlks_{azimuth_looks}alks.wbd"

    search_dirs = [insar_dir, run_dir, dense_dir]

    candidates = []
    for search_dir in search_dirs:
        if search_dir.exists():
            candidates.extend(
                p for p in search_dir.glob(pattern)
                if p.name != "wbd.rdr" and p.is_file()
            )

    if not candidates:
        fallback = []
        for search_dir in search_dirs:
            if search_dir.exists():
                fallback.extend(
                    p for p in search_dir.glob("*.wbd")
                    if p.name != "wbd.rdr" and p.is_file()
                )
        if not fallback:
            searched = ", ".join(str(d) for d in search_dirs)
            raise FileNotFoundError(
                "Could not find any radar-coordinate WBD file for dense offset. "
                f"Expected pattern: {pattern}. Searched: {searched}"
            )
        src = sorted(fallback)[0]
        print(
            "Warning: could not find WBD matching "
            f"{pattern}; using fallback {src}"
        )
    else:
        # Prefer the canonical pair/look-specific WBD produced in run/insar.
        candidates = sorted(candidates, key=lambda p: (p.parent != insar_dir, str(p)))
        src = candidates[0]

    dst = dense_dir / "wbd.rdr"
    _copy_and_retarget_isce_sidecars(src, dst)

    print("Prepared dense-offset WBD files:")
    print(f"  {src} -> {dst}")

    return dst


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

    DEM zeros and all-land WBD masks are written by truncating the file. Nonzero
    WBD values are written as literal bytes.
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
    WBD raster is filled with 0 and has the same extent/resolution as the
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

    _write_constant_binary_file(wbd_file, width_1 * length_1, dtype_bytes=1, fill_byte=0)
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


# ---------------------------------------------------------------------------
# DEM/WBD preparation helpers
# ---------------------------------------------------------------------------

SRTMGL1_BASE_URL = "https://step.esa.int/auxdata/dem/SRTMGL1"
SRTMGL3_BASE_URL = "https://step.esa.int/auxdata/dem/SRTMGL3"
SRTMSWBD_COLLECTION_CONCEPT_ID = "C2763268445-LPCLOUD"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
EARTHDATA_LOGIN_HOST = "urs.earthdata.nasa.gov"


def _run_external_command(cmd: list[str | Path], cwd: str | Path | None = None) -> None:
    """Run an external command and raise a useful error if it fails."""
    cmd = [str(c) for c in cmd]
    print("Running:", " ".join(cmd))
    try:
        subprocess.run(cmd, cwd=None if cwd is None else Path(cwd), check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required external command was not found: {cmd[0]!r}. "
            "Please make sure GDAL tools such as gdalbuildvrt, gdalwarp, "
            "and gdalinfo are available in your PATH."
        ) from exc


def _srtm_zip_name(lat: int, lon: int, arcsec: int) -> str:
    """Return ESA STEP SRTM zip filename for a tile.

    ESA STEP reliably exposes SRTMGL1 tiles as 1-degree HGT zip files.
    In some regions, equivalent SRTMGL3 filenames are not present on the
    STEP server, so the production workflow downloads SRTMGL1 and derives
    the 3-arcsec DEM locally by resampling.  This function is therefore
    intentionally restricted to SRTMGL1 downloads.
    """
    if arcsec == 1:
        return f"{_format_lat(lat)}{_format_lon(lon)}.SRTMGL1.hgt.zip"
    raise ValueError(
        "Direct SRTMGL3 downloads are not used because the ESA STEP "
        "SRTMGL3 URL pattern is not reliable. Download SRTMGL1 and "
        "derive the 3-arcsec DEM locally instead."
    )


def _srtm_hgt_name(lat: int, lon: int) -> str:
    """Return HGT filename inside an ESA STEP SRTM zip file."""
    return f"{_format_lat(lat)}{_format_lon(lon)}.hgt"


def _download_file(url: str, output_file: str | Path, overwrite: bool = False) -> Path:
    """Download a file unless it already exists."""
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists() and output_file.stat().st_size > 0 and not overwrite:
        print(f"Already downloaded: {output_file}")
        return output_file

    print(f"Downloading: {url}")
    try:
        urllib.request.urlretrieve(url, output_file)
    except Exception as exc:
        if output_file.exists() and output_file.stat().st_size == 0:
            output_file.unlink()
        raise RuntimeError(f"Could not download {url}") from exc

    return output_file


def _earthdata_opener(netrc_file: str | Path | None = None):
    """Return a cookie-aware urllib opener configured with Earthdata .netrc."""
    try:
        auth = netrc.netrc(None if netrc_file is None else str(netrc_file))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Earthdata .netrc credentials were not found. "
            "Create ~/.netrc with your urs.earthdata.nasa.gov login, or pass "
            "water_body explicitly to skip NASA SWBD download."
        ) from exc
    except netrc.NetrcParseError as exc:
        message = str(exc)
        if "access too permissive" in message:
            message += "; fix with: chmod 600 ~/.netrc"
        raise RuntimeError(f"Could not parse Earthdata .netrc: {message}") from exc

    credentials = auth.authenticators(EARTHDATA_LOGIN_HOST)
    if credentials is None:
        raise RuntimeError(
            f"Earthdata .netrc has no entry for {EARTHDATA_LOGIN_HOST!r}."
        )

    login, _, password = credentials
    password_mgr = urllib.request.HTTPPasswordMgrWithPriorAuth()
    password_mgr.add_password(
        realm=None,
        uri=f"https://{EARTHDATA_LOGIN_HOST}",
        user=login,
        passwd=password,
        is_authenticated=True,
    )
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPBasicAuthHandler(password_mgr),
    )


def _download_file_with_opener(
    url: str,
    output_file: str | Path,
    opener,
    overwrite: bool = False,
) -> Path:
    """Download a protected file with a urllib opener unless it already exists."""
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists() and output_file.stat().st_size > 0 and not overwrite:
        print(f"Already downloaded: {output_file}")
        return output_file

    print(f"Downloading NASA Earthdata SWBD: {url}")
    tmp_file = output_file.with_suffix(output_file.suffix + ".part")
    if tmp_file.exists():
        tmp_file.unlink()

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "iscewrap"})
        with opener.open(request, timeout=120) as response, open(tmp_file, "wb") as f:
            shutil.copyfileobj(response, f)
        tmp_file.replace(output_file)
    except Exception as exc:
        if tmp_file.exists():
            tmp_file.unlink()
        raise RuntimeError(f"Could not download NASA Earthdata SWBD file {url}") from exc

    return output_file


def _swbd_tile_id(lat: int, lon: int) -> str:
    """Return NASA SWBD one-degree tile id, e.g. N00E021.SRTMSWBD.raw."""
    return f"{_format_lat(lat)}{_format_lon(lon)}.SRTMSWBD.raw"


def _query_nasa_swbd_granules(
    south: int,
    north: int,
    west: int,
    east: int,
) -> dict[str, str]:
    """Return CMR download URLs keyed by SWBD tile id."""
    params = {
        "collection_concept_id": SRTMSWBD_COLLECTION_CONCEPT_ID,
        "bounding_box": f"{west},{south},{east},{north}",
        "page_size": 2000,
    }
    url = f"{CMR_GRANULES_URL}?{urllib.parse.urlencode(params)}"
    print(f"Querying NASA CMR SWBD granules: {url}")

    with urllib.request.urlopen(url, timeout=60) as response:
        feed = json.load(response).get("feed", {})

    downloads: dict[str, str] = {}
    for entry in feed.get("entry", []):
        tile_id = entry.get("producer_granule_id") or entry.get("title")
        if not tile_id:
            continue
        for link in entry.get("links", []):
            href = link.get("href", "")
            rel = link.get("rel", "")
            inherited = link.get("inherited", False)
            if inherited or not href.startswith("https://"):
                continue
            if rel.endswith("/data#") and href.endswith(".SRTMSWBD.raw.zip"):
                downloads[tile_id] = href
                break

    return downloads


def _read_swbd_raw_from_zip(zip_file: str | Path):
    """Read a NASA SWBD raw zip and return a 2D uint8 tile array."""
    import numpy as np

    zip_file = Path(zip_file)
    with zipfile.ZipFile(zip_file, "r") as zf:
        members = [
            info
            for info in zf.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".raw")
        ]
        if len(members) != 1:
            raise RuntimeError(
                f"Expected exactly one .raw file in {zip_file}, found {len(members)}"
            )
        raw = zf.read(members[0])

    side = int(math.isqrt(len(raw)))
    if side * side != len(raw):
        raise RuntimeError(
            f"SWBD raw tile in {zip_file} has {len(raw)} bytes, not a square raster"
        )
    if side not in (3600, 3601):
        raise RuntimeError(
            f"Unsupported SWBD raw tile size {side}x{side} in {zip_file}"
        )

    return np.frombuffer(raw, dtype=np.uint8).reshape(side, side)


def _write_nasa_swbd_mosaic(
    tile_zip_files: dict[tuple[int, int], Path],
    output_file: str | Path,
    south: int,
    north: int,
    west: int,
    east: int,
    overwrite: bool = False,
) -> Path:
    """Mosaic NASA one-degree SWBD raw zips into an ISCE-compatible WBD file."""
    import numpy as np

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    delta = 1.0 / 3600.0
    width = int((east - west) * 3600)
    length = int((north - south) * 3600)

    if output_file.exists() and output_file.stat().st_size > 0 and not overwrite:
        print(f"Already prepared NASA SWBD mosaic: {output_file}")
    else:
        mosaic = np.memmap(output_file, mode="w+", dtype=np.uint8, shape=(length, width))
        for lat in range(south, north):
            for lon in range(west, east):
                tile = _read_swbd_raw_from_zip(tile_zip_files[(lat, lon)])
                # NASA raw SWBD stores water as nonzero. ISCE ALOS processing
                # expects 0=land and int8 -1=water; in a BYTE file, -1 is 255.
                tile = np.where(tile[:3600, :3600] != 0, 255, 0).astype(np.uint8)
                row = (north - lat - 1) * 3600
                col = (lon - west) * 3600
                mosaic[row : row + 3600, col : col + 3600] = tile
        mosaic.flush()
        del mosaic

    _write_isce_raster_xml(
        output_file,
        width=width,
        length=length,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta,
        data_type="BYTE",
        family="image",
        image_type=None,
        reference=None,
    )
    _write_vrt(
        output_file,
        width=width,
        length=length,
        west=west,
        north=north,
        delta=delta,
        vrt_dtype="Byte",
        pixel_offset=1,
        line_offset=width,
    )

    return output_file


def _prepare_nasa_swbd_from_bounding_box(
    bounding_box: list[float],
    output_dir: str | Path,
    overwrite: bool = False,
    netrc_file: str | Path | None = None,
) -> Path:
    """Download NASA SRTMSWBD.003 tiles and create an ISCE-compatible WBD."""
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    south, north, west, east = _rounded_dem_extent(bounding_box)
    wbd_file = output_dir / _wbd_filename(south, north, west, east)
    tile_dir = output_dir / "tiles"
    tile_dir.mkdir(parents=True, exist_ok=True)

    downloads = _query_nasa_swbd_granules(south=south, north=north, west=west, east=east)
    expected = {
        _swbd_tile_id(lat, lon): (lat, lon)
        for lat in range(south, north)
        for lon in range(west, east)
    }
    missing = sorted(tile_id for tile_id in expected if tile_id not in downloads)
    if missing:
        raise RuntimeError(
            "NASA CMR did not return all required SWBD tiles: " + ", ".join(missing)
        )

    opener = _earthdata_opener(netrc_file=netrc_file)
    tile_zip_files: dict[tuple[int, int], Path] = {}
    for tile_id, lat_lon in expected.items():
        zip_file = tile_dir / f"{tile_id}.zip"
        tile_zip_files[lat_lon] = _download_file_with_opener(
            downloads[tile_id],
            zip_file,
            opener=opener,
            overwrite=overwrite,
        )

    return _write_nasa_swbd_mosaic(
        tile_zip_files=tile_zip_files,
        output_file=wbd_file,
        south=south,
        north=north,
        west=west,
        east=east,
        overwrite=overwrite,
    )


def _download_srtm_tiles(
    south: int,
    north: int,
    west: int,
    east: int,
    tile_dir: str | Path,
    arcsec: int,
    overwrite: bool = False,
) -> list[Path]:
    """Download and unzip all SRTM tiles covering integer-degree bounds."""
    tile_dir = Path(tile_dir).resolve()
    tile_dir.mkdir(parents=True, exist_ok=True)

    base_url = SRTMGL1_BASE_URL if arcsec == 1 else SRTMGL3_BASE_URL
    hgt_files: list[Path] = []

    for lat in range(south, north):
        for lon in range(west, east):
            zip_name = _srtm_zip_name(lat, lon, arcsec=arcsec)
            hgt_name = _srtm_hgt_name(lat, lon)
            zip_file = tile_dir / zip_name
            hgt_file = tile_dir / hgt_name
            url = f"{base_url}/{zip_name}"

            if not hgt_file.exists() or overwrite:
                _download_file(url, zip_file, overwrite=overwrite)
                print(f"Unzipping: {zip_file}")
                with zipfile.ZipFile(zip_file, "r") as zf:
                    zf.extractall(tile_dir)

            if not hgt_file.exists():
                raise FileNotFoundError(
                    f"Expected HGT file was not created: {hgt_file}. "
                    f"Check the downloaded archive: {zip_file}"
                )

            hgt_files.append(hgt_file)

    return hgt_files


def _prepare_one_srtm_dem(
    bounding_box: list[float],
    output_dir: str | Path,
    arcsec: int,
    convert_to_wgs84_ellipsoid: bool = True,
    overwrite: bool = False,
) -> Path:
    """Download, stitch, crop, and convert one SRTM DEM to ISCE format.

    The SRTM source elevations are EGM96 orthometric heights. With
    ``convert_to_wgs84_ellipsoid=True``, GDAL is asked to transform
    ``EPSG:4326+5773`` to ``EPSG:4979`` so the output is ellipsoid height,
    which is what ISCE generally expects for ``*.dem.wgs84``.
    """
    if arcsec not in (1, 3):
        raise ValueError("arcsec must be either 1 or 3")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    south, north, west, east = _rounded_dem_extent(bounding_box)
    delta = 1.0 / (3600.0 if arcsec == 1 else 1200.0)
    width = int(round((east - west) / delta))
    length = int(round((north - south) / delta))

    dem_file = output_dir / _dem_filename(south, north, west, east)
    tile_dir = output_dir / "tiles"
    hgt_files = _download_srtm_tiles(
        south=south,
        north=north,
        west=west,
        east=east,
        tile_dir=tile_dir,
        arcsec=arcsec,
        overwrite=overwrite,
    )

    mosaic_vrt = output_dir / f"srtm_{arcsec}_arcsec_egm96_mosaic.vrt"
    _run_external_command(["gdalbuildvrt", mosaic_vrt, *hgt_files])

    if dem_file.exists() and not overwrite:
        print(f"Already prepared DEM: {dem_file}")
    else:
        cmd = [
            "gdalwarp",
            "-overwrite",
            "-te", str(west), str(south), str(east), str(north),
            "-tr", str(delta), str(delta),
            "-r", "bilinear",
            "-of", "ENVI",
            "-ot", "Float32",
        ]
        if convert_to_wgs84_ellipsoid:
            cmd += ["-s_srs", "EPSG:4326+5773", "-t_srs", "EPSG:4979"]
        else:
            cmd += ["-t_srs", "EPSG:4326"]
        cmd += [mosaic_vrt, dem_file]
        _run_external_command(cmd)

    _write_isce_raster_xml(
        dem_file,
        width=width,
        length=length,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta,
        data_type="FLOAT",
        family="demimage",
        image_type="dem",
        reference="WGS84",
    )
    _write_vrt(
        dem_file,
        width=width,
        length=length,
        west=west,
        north=north,
        delta=delta,
        vrt_dtype="Float32",
        pixel_offset=4,
        line_offset=width * 4,
    )

    return dem_file


def _source_for_gdal(path: str | Path) -> Path:
    """Return the best GDAL-readable path for an ISCE raw raster."""
    path = Path(path).resolve()
    vrt = Path(str(path) + ".vrt")
    if vrt.exists():
        return vrt
    return path


def _prepare_resampled_dem_from_source(
    source_dem: str | Path,
    bounding_box: list[float],
    output_dir: str | Path,
    arcsec: int,
    overwrite: bool = False,
) -> Path:
    """Create an ISCE DEM by resampling an existing DEM source.

    This is used for the 3-arcsec geocoding DEM. It avoids relying on the
    legacy SRTMGL3 download endpoint, which can return 404 for valid tiles.
    The source DEM is normally the freshly prepared SRTMGL1 WGS84 DEM.
    """
    if arcsec not in (1, 3):
        raise ValueError("arcsec must be either 1 or 3")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    south, north, west, east = _rounded_dem_extent(bounding_box)
    delta = 1.0 / (3600.0 if arcsec == 1 else 1200.0)
    width = int(round((east - west) / delta))
    length = int(round((north - south) / delta))

    dem_file = output_dir / _dem_filename(south, north, west, east)
    source_for_gdal = _source_for_gdal(source_dem)

    if dem_file.exists() and not overwrite:
        print(f"Already prepared DEM: {dem_file}")
    else:
        _run_external_command([
            "gdalwarp",
            "-overwrite",
            "-t_srs", "EPSG:4326",
            "-te", str(west), str(south), str(east), str(north),
            "-tr", str(delta), str(delta),
            "-r", "bilinear",
            "-of", "ENVI",
            "-ot", "Float32",
            source_for_gdal,
            dem_file,
        ])

    _write_isce_raster_xml(
        dem_file,
        width=width,
        length=length,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta,
        data_type="FLOAT",
        family="demimage",
        image_type="dem",
        reference="WGS84",
    )
    _write_vrt(
        dem_file,
        width=width,
        length=length,
        west=west,
        north=north,
        delta=delta,
        vrt_dtype="Float32",
        pixel_offset=4,
        line_offset=width * 4,
    )

    return dem_file


def _create_all_land_wbd_from_bounding_box(
    bounding_box: list[float],
    output_dir: str | Path,
    overwrite: bool = False,
) -> Path:
    """Create a 1-arcsec all-land/all-valid water-body mask filled with 0.

    This is a robust fallback when legacy SWBD downloads fail. It intentionally
    does not mask water; it simply prevents ISCE from attempting broken WBD
    downloads while keeping the XML input complete.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    south, north, west, east = _rounded_dem_extent(bounding_box)
    delta = 1.0 / 3600.0
    width = int((east - west) * 3600)
    length = int((north - south) * 3600)
    wbd_file = output_dir / _wbd_filename(south, north, west, east)

    print(
        "[iscewrap-wbd] Generating valid-only all-land WBD fallback "
        f"(no water masking): {wbd_file}",
        flush=True,
    )
    if not wbd_file.exists() or overwrite:
        _write_constant_binary_file(
            wbd_file,
            total_values=width * length,
            dtype_bytes=1,
            fill_byte=0,
        )

    _write_isce_raster_xml(
        wbd_file,
        width=width,
        length=length,
        west=west,
        east=east,
        south=south,
        north=north,
        delta=delta,
        data_type="BYTE",
        family="image",
        image_type=None,
        reference=None,
    )
    _write_vrt(
        wbd_file,
        width=width,
        length=length,
        west=west,
        north=north,
        delta=delta,
        vrt_dtype="Byte",
        pixel_offset=1,
        line_offset=width,
    )

    return wbd_file


def prepare_srtm_dem_and_wbd(
    bounding_box: list[float],
    output_dir: str | Path,
    dem_coreg: str | Path | None = None,
    dem_geocode: str | Path | None = None,
    water_body: str | Path | None = None,
    overwrite: bool = False,
    convert_to_wgs84_ellipsoid: bool = True,
) -> dict:
    """Prepare missing DEM/WBD inputs for ALOS-2 processing.

    Directory layout under ``output_dir`` is exactly:

    - ``dem_1_arcsec``: SRTMGL1 DEM converted to ISCE ``*.dem.wgs84``
    - ``dem_3_arcsec``: 3-arcsec DEM derived locally from SRTMGL1 and converted to ISCE ``*.dem.wgs84``
    - ``wbd_1_arcsec``: NASA SRTMSWBD.003 when available, otherwise all-land fallback WBD file

    Provided paths are respected; only missing inputs are generated.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    dem_1_dir = output_dir / "dem_1_arcsec"
    dem_3_dir = output_dir / "dem_3_arcsec"
    wbd_dir = output_dir / "wbd_1_arcsec"

    if dem_coreg is None:
        dem_coreg = _prepare_one_srtm_dem(
            bounding_box=bounding_box,
            output_dir=dem_1_dir,
            arcsec=1,
            convert_to_wgs84_ellipsoid=convert_to_wgs84_ellipsoid,
            overwrite=overwrite,
        )
    else:
        dem_coreg = Path(dem_coreg).resolve()

    if dem_geocode is None:
        # The ESA STEP SRTMGL3 URL pattern is not reliable in all regions.
        # To avoid 404 failures, derive the 3-arcsec DEM from the already
        # prepared 1-arcsec DEM by resampling.
        dem_geocode = _prepare_resampled_dem_from_source(
            source_dem=dem_coreg,
            bounding_box=bounding_box,
            output_dir=dem_3_dir,
            arcsec=3,
            overwrite=overwrite,
        )
    else:
        dem_geocode = Path(dem_geocode).resolve()

    water_body_source = "provided"
    if water_body is None:
        try:
            print(
                "[iscewrap-wbd] Preparing NASA SRTMSWBD.003 water-body mask "
                "from CMR/Earthdata",
                flush=True,
            )
            water_body = _prepare_nasa_swbd_from_bounding_box(
                bounding_box=bounding_box,
                output_dir=wbd_dir,
                overwrite=overwrite,
            )
            water_body_source = "nasa_srtmswbd"
            print(
                f"[iscewrap-wbd] Using NASA SRTMSWBD.003 water-body mask: {water_body}",
                flush=True,
            )
        except Exception as exc:
            print(
                "[iscewrap-wbd] NASA SRTMSWBD.003 download/mosaic failed; "
                f"falling back to valid-only all-land WBD. Reason: {exc}",
                flush=True,
            )
            water_body = _create_all_land_wbd_from_bounding_box(
                bounding_box=bounding_box,
                output_dir=wbd_dir,
                overwrite=overwrite,
            )
            water_body_source = "all_land_fallback"
    else:
        water_body = Path(water_body).resolve()
        print(f"[iscewrap-wbd] Using provided water-body mask: {water_body}", flush=True)

    south, north, west, east = _rounded_dem_extent(bounding_box)
    return {
        "bounding_box": bounding_box,
        "extent": {"south": south, "north": north, "west": west, "east": east},
        "dem_coreg": Path(dem_coreg).resolve(),
        "dem_geocode": Path(dem_geocode).resolve(),
        "water_body": Path(water_body).resolve(),
        "dem_1_arcsec": Path(dem_coreg).resolve(),
        "dem_3_arcsec": Path(dem_geocode).resolve(),
        "wbd_1_arcsec": Path(water_body).resolve(),
        "water_body_source": water_body_source,
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
    """Run the DEM-generation workflow using empty DEM inputs.

    This workflow is intentionally different from ``process_alos2_pair`` with
    automatic SRTM preparation.  For phase-to-height / DEM generation, ISCE must
    be run with zero-valued empty DEMs so that topographic phase is preserved
    instead of being removed using an external real DEM.

    Workflow
    --------
    1. Run ``alos2App.py`` through ``baseline`` only, without DEM/WBD inputs.
    2. Parse ``runBaseline.reference bounding box`` from the terminal log.
    3. Create empty DEM/WBD files under ``work_dir/empty_dem``.
    4. Recreate the processing XML using the empty DEM/WBD paths.
    5. Run the requested processing range.

    If ``dem_coreg``, ``dem_geocode``, or ``water_body`` are provided, those
    paths are respected; only missing inputs are replaced by empty files.
    """
    work_dir = Path(work_dir).resolve()

    # First run only to baseline to get the geographic bounding box.  Do not
    # enable automatic SRTM preparation here; generate_dem must use empty DEMs.
    baseline_result = process_alos2_pair(
        reference_input=reference_input,
        secondary_input=secondary_input,
        work_dir=work_dir,
        dem_coreg=None,
        dem_geocode=None,
        water_body=None,
        auto_prepare_dem=False,
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

    empty_dem_result = _create_empty_dem_files_from_bounding_box(
        bounding_box=bounding_box,
        output_dir=work_dir / "empty_dem",
    )

    # Use user-provided paths only if explicitly supplied.  Otherwise force the
    # empty DEM/WBD paths for the DEM-generation workflow.
    if dem_coreg is None:
        dem_coreg = empty_dem_result["dem_coreg"]
    if dem_geocode is None:
        dem_geocode = empty_dem_result["dem_geocode"]
    if water_body is None:
        water_body = empty_dem_result["water_body"]

    final_result = process_alos2_pair(
        reference_input=reference_input,
        secondary_input=secondary_input,
        work_dir=work_dir,
        dem_coreg=dem_coreg,
        dem_geocode=dem_geocode,
        water_body=water_body,
        auto_prepare_dem=False,
        use_gpu=use_gpu,
        do_ionosphere=do_ionosphere,
        apply_ionosphere=apply_ionosphere,
        run=run,
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

    final_result["baseline_result"] = baseline_result
    final_result["empty_dem_result"] = empty_dem_result
    final_result["empty_dem_coreg"] = Path(empty_dem_result["dem_coreg"]).resolve()
    final_result["empty_dem_geocode"] = Path(empty_dem_result["dem_geocode"]).resolve()
    final_result["empty_water_body"] = Path(empty_dem_result["water_body"]).resolve()

    return final_result



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
    return infer_looks_from_filename(path, default=(default, None))[0]


def infer_looks_from_filename(
    path: str | Path,
    default: tuple[int | None, int | None] | None = None,
) -> tuple[int, int]:
    """Infer range and azimuth looks from names like ``*_8rlks_16alks.*``."""
    name = Path(path).name
    match = re.search(r"_(\d+)rlks_(\d+)alks", name)

    if match is None:
        if default is None or default[0] is None or default[1] is None:
            raise ValueError(
                f"Could not infer range/azimuth looks from filename: {name}. "
                "Provide range_looks and azimuth_looks explicitly."
            )
        return int(default[0]), int(default[1])

    return int(match.group(1)), int(match.group(2))


def geocode_raster_native_isce2(
    input_file: str | Path,
    track_xml: str | Path,
    dem_file: str | Path,
    output_file: str | Path | None = None,
    grid_reference: str | Path | None = None,
    bbox: list[float] | tuple[float, float, float, float] | None = None,
    range_looks: int | None = None,
    azimuth_looks: int | None = None,
    interp_method: str | None = None,
    top_shift: int = 0,
    left_shift: int = 0,
    add_multilook_offset: bool = True,
) -> dict:
    """Run ISCE2's native ALOS-2 geocoder for one raster.

    This wraps ``isceobj.Alos2Proc.runGeocode.geocode`` so the output grid and
    geocoding behavior match native ``alos2App.py``.  Looks are inferred from
    filenames like ``*_8rlks_16alks.*`` unless explicitly supplied.

    ``bbox`` follows ISCE2 ordering: ``[south, north, west, east]``.  If
    ``grid_reference`` is supplied, its geocoded extent is used as the bbox so
    the output aligns with an existing native ISCE2 geocoded product.
    """
    input_file = Path(input_file).resolve()
    track_xml = Path(track_xml).resolve()
    dem_file = Path(dem_file).resolve()
    output_file = None if output_file is None else Path(output_file).resolve()
    grid_reference = (
        None if grid_reference is None else Path(grid_reference).resolve()
    )

    _ensure_isce2_components_on_path()

    if range_looks is None or azimuth_looks is None:
        inferred_range, inferred_azimuth = infer_looks_from_filename(
            input_file,
            default=(range_looks, azimuth_looks),
        )
        range_looks = inferred_range if range_looks is None else range_looks
        azimuth_looks = inferred_azimuth if azimuth_looks is None else azimuth_looks

    track = _load_isce2_track(track_xml)

    if bbox is None and grid_reference is not None:
        bbox = _bbox_from_geocoded_reference(grid_reference)

    if bbox is None:
        from isceobj.Alos2Proc.Alos2ProcPublic import getBboxGeo

        input_meta = read_isce_raster_metadata(input_file)
        bbox = getBboxGeo(
            track,
            useTrackOnly=True,
            numberOfSamples=input_meta["width"],
            numberOfLines=input_meta["length"],
            numberRangeLooks=int(range_looks),
            numberAzimuthLooks=int(azimuth_looks),
        )
    if interp_method is None:
        interp_method = _default_native_geocode_interp(input_file)

    from isceobj.Alos2Proc.runGeocode import geocode

    cwd = Path.cwd()
    try:
        # ISCE2 writes output beside input_file and expects relative sidecars
        # there, matching native alos2App.py behavior inside run/insar.
        import os

        os.chdir(input_file.parent)
        geocode(
            track,
            str(dem_file),
            input_file.name,
            list(map(float, bbox)),
            int(range_looks),
            int(azimuth_looks),
            interp_method.lower(),
            int(top_shift),
            int(left_shift),
            addMultilookOffset=bool(add_multilook_offset),
        )
    finally:
        os.chdir(cwd)

    native_output = input_file.with_name(input_file.name + ".geo")
    if output_file is None:
        output_file = native_output
    elif output_file != native_output:
        _rename_isce_raster(native_output, output_file)

    grid_snapped = False
    if grid_reference is not None:
        _snap_geocoded_raster_to_reference(output_file, grid_reference)
        grid_snapped = True

    return {
        "input_file": input_file,
        "output_file": output_file,
        "xml_file": Path(str(output_file) + ".xml"),
        "vrt_file": Path(str(output_file) + ".vrt"),
        "track_xml": track_xml,
        "dem_file": dem_file,
        "grid_reference": grid_reference,
        "grid_snapped": grid_snapped,
        "bbox": list(map(float, bbox)),
        "range_looks": int(range_looks),
        "azimuth_looks": int(azimuth_looks),
        "interp_method": interp_method.lower(),
        "top_shift": int(top_shift),
        "left_shift": int(left_shift),
        "add_multilook_offset": bool(add_multilook_offset),
    }


def _load_isce2_track(track_xml: Path):
    _ensure_isce2_components_on_path()
    from iscesys.Component.ProductManager import ProductManager

    pm = ProductManager()
    pm.configure()
    track_xml_to_load = _sanitize_track_xml_for_standalone_load(track_xml)
    track = pm.loadProduct(str(track_xml_to_load))
    return track


def _sanitize_track_xml_for_standalone_load(track_xml: Path) -> Path:
    """Remove stale frame references from track XML before standalone loading."""
    import tempfile
    import xml.etree.ElementTree as ET

    tree = ET.parse(track_xml)
    root = tree.getroot()
    removed = False
    for parent in root.iter():
        for child in list(parent):
            if child.tag == "property" and child.attrib.get("name", "").lower() == "frames":
                parent.remove(child)
                removed = True

    if not removed:
        return track_xml

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        suffix=".track.xml",
        prefix="iscewrap_",
        delete=False,
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    tree.write(tmp_path, encoding="utf-8", xml_declaration=False)
    return tmp_path


def _bbox_from_geocoded_reference(reference_file: Path) -> list[float]:
    """Read ISCE bbox ordering from an existing geocoded reference product."""
    from iscewrap.geo import read_geo_extent

    extent = read_geo_extent(reference_file)
    return [
        float(extent["south"]),
        float(extent["north"]),
        float(extent["west"]),
        float(extent["east"]),
    ]


def _snap_geocoded_raster_to_reference(raster_file: Path, reference_file: Path) -> None:
    """Crop a geocoded raster to exactly match a reference VRT grid."""
    import numpy as np

    source_grid = _read_vrt_grid(raster_file)
    target_grid = _read_vrt_grid(reference_file)
    source_meta = read_isce_raster_metadata(raster_file)
    data = read_isce_raster(raster_file, metadata=source_meta)

    xres = source_grid["xres"]
    yres = abs(source_grid["yres"])
    if not np.isclose(xres, target_grid["xres"]) or not np.isclose(
        yres,
        abs(target_grid["yres"]),
    ):
        raise ValueError(
            "Cannot snap geocoded raster to reference with different resolution: "
            f"source=({xres}, {yres}), "
            f"target=({target_grid['xres']}, {abs(target_grid['yres'])})"
        )

    col0 = int(round((target_grid["west"] - source_grid["west"]) / xres))
    row0 = int(round((source_grid["north"] - target_grid["north"]) / yres))
    length = int(target_grid["length"])
    width = int(target_grid["width"])

    if row0 < 0 or col0 < 0:
        raise ValueError(
            f"Reference grid starts outside source grid: row={row0}, col={col0}"
        )
    if row0 + length > source_meta["length"] or col0 + width > source_meta["width"]:
        raise ValueError(
            "Reference grid is not contained in source geocoded raster: "
            f"source=({source_meta['length']}, {source_meta['width']}), "
            f"crop=({row0}:{row0 + length}, {col0}:{col0 + width})"
        )

    if data.ndim == 2:
        cropped = data[row0 : row0 + length, col0 : col0 + width]
    else:
        cropped = data[:, row0 : row0 + length, col0 : col0 + width]

    _write_isce_geocoded_raster_preserve_scheme(
        output_file=raster_file,
        array=cropped,
        lon_min=target_grid["west"],
        lat_max=target_grid["north"],
        resolution=xres,
        data_type=source_meta["data_type"],
        scheme=source_meta["scheme"],
    )


def _read_vrt_grid(raster_file: Path) -> dict:
    import xml.etree.ElementTree as ET

    raster_file = _normalize_isce_raster_path(raster_file)
    vrt_file = Path(str(raster_file) + ".vrt")
    root = ET.parse(vrt_file).getroot()
    values = [float(value.strip()) for value in root.findtext("GeoTransform").split(",")]
    if len(values) != 6:
        raise ValueError(f"Invalid GeoTransform in {vrt_file}")
    west, xres, _, north, _, yres = values
    return {
        "raster_file": raster_file,
        "width": int(root.attrib["rasterXSize"]),
        "length": int(root.attrib["rasterYSize"]),
        "west": west,
        "north": north,
        "xres": xres,
        "yres": yres,
        "east": west + int(root.attrib["rasterXSize"]) * xres,
        "south": north + int(root.attrib["rasterYSize"]) * yres,
    }


def _normalize_isce_raster_path(path: Path) -> Path:
    name = path.name
    if name.endswith(".vrt"):
        return path.with_name(name[:-4])
    if name.endswith(".xml"):
        return path.with_name(name[:-4])
    return path


def _write_isce_geocoded_raster_preserve_scheme(
    output_file: Path,
    array,
    lon_min: float,
    lat_max: float,
    resolution: float,
    data_type: str,
    scheme: str,
) -> dict:
    import numpy as np

    arr = np.asarray(array)
    data_type = data_type.upper()
    scheme = scheme.upper()
    if data_type == "CFLOAT":
        arr = arr.astype(np.complex64)
        vrt_dtype = "CFloat32"
        pixel_bytes = 8
    elif data_type == "FLOAT":
        arr = arr.astype(np.float32)
        vrt_dtype = "Float32"
        pixel_bytes = 4
    elif data_type == "DOUBLE":
        arr = arr.astype(np.float64)
        vrt_dtype = "Float64"
        pixel_bytes = 8
    else:
        # Fall back to the existing writer for types we do not need to preserve yet.
        return write_isce_geocoded_raster(
            output_file=output_file,
            array=arr,
            lon_min=lon_min,
            lat_max=lat_max,
            resolution=resolution,
            data_type=data_type,
        )

    if arr.ndim == 2:
        length, width = arr.shape
        number_bands = 1
        scheme = "BIP"
        arr_to_write = arr
    else:
        number_bands, length, width = arr.shape
        if scheme == "BIL":
            arr_to_write = arr.transpose(1, 0, 2)
        elif scheme == "BIP":
            arr_to_write = arr.transpose(1, 2, 0)
        else:
            scheme = "BSQ"
            arr_to_write = arr

    arr_to_write.tofile(output_file)
    return _write_isce_geocoded_sidecars(
        output_file=output_file,
        width=width,
        length=length,
        number_bands=number_bands,
        scheme=scheme,
        data_type=data_type,
        vrt_dtype=vrt_dtype,
        pixel_bytes=pixel_bytes,
        lon_min=lon_min,
        lat_max=lat_max,
        resolution=resolution,
    )


def _write_isce_geocoded_sidecars(
    *,
    output_file: Path,
    width: int,
    length: int,
    number_bands: int,
    scheme: str,
    data_type: str,
    vrt_dtype: str,
    pixel_bytes: int,
    lon_min: float,
    lat_max: float,
    resolution: float,
) -> dict:
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
    <property name="data_type"><value>{data_type}</value></property>
    <property name="extra_file_name"><value>{output_file.name}.vrt</value></property>
    <property name="family"><value>image</value></property>
    <property name="file_name"><value>{output_file.resolve()}</value></property>
    <property name="length"><value>{length}</value></property>
    <property name="number_bands"><value>{number_bands}</value></property>
    <property name="scheme"><value>{scheme}</value></property>
    <property name="width"><value>{width}</value></property>
    <property name="xmax"><value>{lon_max}</value></property>
    <property name="xmin"><value>{lon_min}</value></property>
</imageFile>
""",
        encoding="utf-8",
    )

    band_xml = _vrt_bands_for_scheme(
        number_bands=number_bands,
        width=width,
        length=length,
        scheme=scheme,
        vrt_dtype=vrt_dtype,
        pixel_bytes=pixel_bytes,
        source_name=output_file.name,
    )
    vrt_file.write_text(
        f"""<VRTDataset rasterXSize="{width}" rasterYSize="{length}">
    <SRS>EPSG:4326</SRS>
    <GeoTransform>{lon_min}, {resolution}, 0.0, {lat_max}, 0.0, {-resolution}</GeoTransform>
{band_xml}
</VRTDataset>
""",
        encoding="utf-8",
    )
    return {"xml_file": xml_file, "vrt_file": vrt_file}


def _vrt_bands_for_scheme(
    *,
    number_bands: int,
    width: int,
    length: int,
    scheme: str,
    vrt_dtype: str,
    pixel_bytes: int,
    source_name: str,
) -> str:
    if number_bands == 1:
        return _vrt_raw_band(
            band=1,
            data_type=vrt_dtype,
            source_name=source_name,
            image_offset=0,
            pixel_offset=pixel_bytes,
            line_offset=width * pixel_bytes,
        )

    bands = []
    for band in range(number_bands):
        if scheme == "BIL":
            image_offset = band * width * pixel_bytes
            pixel_offset = pixel_bytes
            line_offset = width * number_bands * pixel_bytes
        elif scheme == "BIP":
            image_offset = band * pixel_bytes
            pixel_offset = number_bands * pixel_bytes
            line_offset = width * number_bands * pixel_bytes
        else:
            image_offset = band * length * width * pixel_bytes
            pixel_offset = pixel_bytes
            line_offset = width * pixel_bytes
        bands.append(
            _vrt_raw_band(
                band=band + 1,
                data_type=vrt_dtype,
                source_name=source_name,
                image_offset=image_offset,
                pixel_offset=pixel_offset,
                line_offset=line_offset,
            )
        )
    return "\n".join(bands)


def _default_native_geocode_interp(input_file: Path) -> str:
    _ensure_isce2_components_on_path()
    import isceobj

    image = isceobj.createImage()
    image.load(str(input_file) + ".xml")
    if image.dataType.upper() == "CFLOAT":
        return "sinc"
    return "bilinear"


def _ensure_isce2_components_on_path() -> None:
    """Add ISCE2 package paths to sys.path when console scripts need them."""
    import site
    import sys

    try:
        import isceobj  # noqa: F401
        import isce  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    candidates = []
    for site_dir in site.getsitepackages():
        candidates.append(Path(site_dir) / "isce2" / "components")
        candidates.append(Path(site_dir))
    user_site = site.getusersitepackages()
    candidates.append(Path(user_site) / "isce2" / "components")
    candidates.append(Path(user_site))
    site_packages = (
        Path(sys.prefix)
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    candidates.append(
        site_packages / "isce2" / "components"
    )
    candidates.append(site_packages)

    for root in (
        Path.home() / "miniforge3" / "envs",
        Path.home() / "miniconda3" / "envs",
        Path.home() / "anaconda3" / "envs",
    ):
        if root.exists():
            for candidate in root.glob("*/lib/python*/site-packages"):
                candidates.append(candidate / "isce2" / "components")

    for candidate in candidates:
        if candidate.exists():
            sys.path.insert(0, str(candidate))
            try:
                import isceobj  # noqa: F401
                import isce  # noqa: F401
                return
            except ModuleNotFoundError:
                continue

    raise ModuleNotFoundError(
        "Could not import ISCE2 modules. Activate the ISCE2 environment or add "
        "both site-packages and the ISCE2 components directory to PYTHONPATH."
    )


def _rename_isce_raster(source_file: Path, output_file: Path) -> None:
    """Rename an ISCE raster and sidecars after native geocode writes default name."""
    import shutil
    import xml.etree.ElementTree as ET

    output_file.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".xml", ".vrt"):
        target = Path(str(output_file) + suffix)
        if target.exists():
            target.unlink()

    for suffix in ("", ".xml", ".vrt"):
        source = Path(str(source_file) + suffix)
        if source.exists():
            shutil.move(str(source), str(Path(str(output_file) + suffix)))

    xml_file = Path(str(output_file) + ".xml")
    if xml_file.exists():
        root = ET.parse(xml_file).getroot()
        _set_xml_property_value(root, "file_name", str(output_file))
        _set_xml_property_value(root, "extra_file_name", output_file.name + ".vrt")
        ET.ElementTree(root).write(xml_file, encoding="utf-8", xml_declaration=False)

    vrt_file = Path(str(output_file) + ".vrt")
    if vrt_file.exists():
        tree = ET.parse(vrt_file)
        root = tree.getroot()
        for source_name in root.iter("SourceFilename"):
            source_name.text = output_file.name
            source_name.attrib["relativeToVRT"] = "1"
        tree.write(vrt_file, encoding="utf-8", xml_declaration=False)


def _set_xml_property_value(root, name: str, value: str) -> None:
    import xml.etree.ElementTree as ET

    for prop in root.iter("property"):
        if prop.attrib.get("name", "").lower() != name.lower():
            continue
        value_node = prop.find("value")
        if value_node is None:
            value_node = ET.SubElement(prop, "value")
        value_node.text = value
        return


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


    track_meta = read_track_metadata(track_xml)
    wavelength = track_meta["radar_wavelength"]

    if wavelength is None:
        raise ValueError(f"Could not read radarwavelength from {track_xml}")

    slant_range = make_slant_range_image_from_track_xml(
        shape=shape,
        track_xml=track_xml,
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
    return write_isce_geocoded_raster(
        output_file=output_file,
        array=array,
        lon_min=lon_min,
        lat_max=lat_max,
        resolution=resolution,
        data_type="FLOAT",
    )


def write_isce_geocoded_raster(
    output_file: str | Path,
    array,
    lon_min: float,
    lat_max: float,
    resolution: float,
    data_type: str | None = None,
) -> dict:
    """Write a geocoded ISCE raw raster with XML and VRT sidecars.

    ``array`` may be a 2D single-band raster or a 3D array normalized as
    ``(bands, length, width)``.  Multi-band output is written as BSQ.  Complex
    arrays are preserved as ISCE ``CFLOAT`` instead of being cast to real float.
    """
    import numpy as np

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    array = np.asarray(array)
    if data_type is None:
        data_type = "CFLOAT" if np.iscomplexobj(array) else "FLOAT"
    data_type = data_type.upper()

    if data_type == "CFLOAT":
        array = array.astype(np.complex64)
        vrt_dtype = "CFloat32"
        pixel_bytes = 8
    elif data_type == "FLOAT":
        array = array.astype(np.float32)
        vrt_dtype = "Float32"
        pixel_bytes = 4
    else:
        raise ValueError(f"Unsupported geocoded output data_type: {data_type}")

    if array.ndim == 2:
        length, width = array.shape
        number_bands = 1
        scheme = "BIP"
        array_to_write = array
    elif array.ndim == 3:
        number_bands, length, width = array.shape
        scheme = "BSQ"
        array_to_write = array
    else:
        raise ValueError(
            f"Expected 2D or 3D array for geocoded raster, got shape {array.shape}"
        )

    array_to_write.tofile(output_file)

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
    <property name="data_type"><value>{data_type}</value></property>
    <property name="extra_file_name"><value>{output_file.name}.vrt</value></property>
    <property name="family"><value>image</value></property>
    <property name="file_name"><value>{output_file.resolve()}</value></property>
    <property name="length"><value>{length}</value></property>
    <property name="number_bands"><value>{number_bands}</value></property>
    <property name="scheme"><value>{scheme}</value></property>
    <property name="width"><value>{width}</value></property>
    <property name="xmax"><value>{lon_max}</value></property>
    <property name="xmin"><value>{lon_min}</value></property>
</imageFile>
""",
        encoding="utf-8",
    )

    if number_bands == 1:
        band_xml = _vrt_raw_band(
            band=1,
            data_type=vrt_dtype,
            source_name=output_file.name,
            image_offset=0,
            pixel_offset=pixel_bytes,
            line_offset=width * pixel_bytes,
        )
    else:
        band_xml = "\n".join(
            _vrt_raw_band(
                band=band + 1,
                data_type=vrt_dtype,
                source_name=output_file.name,
                image_offset=band * length * width * pixel_bytes,
                pixel_offset=pixel_bytes,
                line_offset=width * pixel_bytes,
            )
            for band in range(number_bands)
        )

    vrt_file.write_text(
        f"""<VRTDataset rasterXSize="{width}" rasterYSize="{length}">
    <SRS>EPSG:4326</SRS>
    <GeoTransform>{lon_min}, {resolution}, 0.0, {lat_max}, 0.0, {-resolution}</GeoTransform>
{band_xml}
</VRTDataset>
""",
        encoding="utf-8",
    )

    return {
        "output_file": output_file,
        "xml_file": xml_file,
        "vrt_file": vrt_file,
        "shape": array.shape,
        "data_type": data_type,
        "number_bands": number_bands,
        "scheme": scheme,
    }


def _vrt_raw_band(
    *,
    band: int,
    data_type: str,
    source_name: str,
    image_offset: int,
    pixel_offset: int,
    line_offset: int,
) -> str:
    return f"""    <VRTRasterBand dataType="{data_type}" band="{band}" subClass="VRTRawRasterBand">
        <SourceFilename relativeToVRT="1">{source_name}</SourceFilename>
        <ByteOrder>LSB</ByteOrder>
        <ImageOffset>{image_offset}</ImageOffset>
        <PixelOffset>{pixel_offset}</PixelOffset>
        <LineOffset>{line_offset}</LineOffset>
    </VRTRasterBand>"""


def geocode_raster(
    input_file: str | Path,
    lat_file: str | Path,
    lon_file: str | Path,
    output_file: str | Path,
    resolution: float = 1 / 3600,
    method: str = "nearest",
    nodata=float("nan"),
    band: int | None = None,
    verbose: bool = True,
    mask_edges: bool = True,
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
    method : {"linear", "nearest", "cubic"}, default "nearest"
        Interpolation method passed to ``scipy.interpolate.griddata``.
    nodata : float, default NaN
        Fill value for output pixels outside interpolation support.
    band : int, optional
        Zero-based band to geocode.  If omitted, all input bands are geocoded.
        Complex single-band rasters are preserved as complex output.
    verbose : bool, default True
        Print progress messages while reading, masking, interpolating, and
        writing the geocoded output.
    mask_edges : bool, default True
        Mask output pixels outside the valid source footprint. This prevents
        nearest-neighbor interpolation from stretching edge pixels into the
        rectangular geographic output grid.

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

    def log(message: str) -> None:
        if verbose:
            print(f"[iscewrap-geocode] {message}", flush=True)

    log(f"reading input raster: {input_file}")
    input_meta = read_isce_raster_metadata(input_file)
    data = read_isce_raster(input_file, band=band, metadata=input_meta)
    log(f"reading latitude raster: {lat_file}")
    lat = read_isce_raster(lat_file)
    log(f"reading longitude raster: {lon_file}")
    lon = read_isce_raster(lon_file)
    log(f"input shape: {data.shape}")

    if lat.shape != lon.shape:
        raise ValueError(
            f"Shape mismatch:\n"
            f"lat : {lat.shape}\n"
            f"lon : {lon.shape}"
        )

    if data.ndim == 2:
        data_bands = [data]
        output_single_band = True
    elif data.ndim == 3:
        data_bands = [data[index] for index in range(data.shape[0])]
        output_single_band = False
    else:
        raise ValueError(f"Unsupported input raster shape: {data.shape}")

    for index, data_band in enumerate(data_bands):
        if data_band.shape != lat.shape:
            raise ValueError(
                f"Shape mismatch for input band {index}:\n"
                f"data: {data_band.shape}\n"
                f"lat : {lat.shape}\n"
                f"lon : {lon.shape}"
            )

    mask = (
        np.isfinite(lat)
        & np.isfinite(lon)
        & (lat != 0)
        & (lon != 0)
    )
    for data_band in data_bands:
        mask &= np.isfinite(data_band)

    if not np.any(mask):
        raise ValueError("No valid pixels found after masking data/lat/lon.")

    valid_pixels = int(np.count_nonzero(mask))
    total_pixels = int(mask.size)
    log(
        "valid pixels after finite/nonzero lat/lon mask: "
        f"{valid_pixels}/{total_pixels}"
    )

    lats = lat[mask]
    lons = lon[mask]

    lon_min = float(np.nanmin(lons))
    lon_max = float(np.nanmax(lons))
    lat_min = float(np.nanmin(lats))
    lat_max = float(np.nanmax(lats))
    log(
        "extent: "
        f"lon=[{lon_min}, {lon_max}], lat=[{lat_min}, {lat_max}]"
    )

    grid_lon = np.arange(lon_min, lon_max + resolution, resolution)
    grid_lat = np.arange(lat_max, lat_min - resolution, -resolution)

    grid_lon2d, grid_lat2d = np.meshgrid(grid_lon, grid_lat)
    log(
        "interpolating to geographic grid: "
        f"shape={grid_lon2d.shape}, resolution={resolution}, method={method}"
    )
    if mask_edges:
        log("building source footprint mask")
        footprint_mask = _source_footprint_mask(lat, lon, mask, grid_lon2d, grid_lat2d)
    else:
        footprint_mask = None

    points = np.column_stack([lons, lats])
    geocoded_bands = []
    for index, data_band in enumerate(data_bands):
        if len(data_bands) > 1:
            log(f"interpolating band {index}")
        geocoded_bands.append(
            griddata(
                points,
                data_band[mask],
                (grid_lon2d, grid_lat2d),
                method=method,
                fill_value=nodata,
            )
        )
        if footprint_mask is not None:
            geocoded_bands[-1] = np.where(
                footprint_mask,
                geocoded_bands[-1],
                nodata,
            )

    if output_single_band:
        geo = geocoded_bands[0]
    else:
        geo = np.stack(geocoded_bands, axis=0)

    log(f"writing geocoded raster: {output_file}")
    out = write_isce_geocoded_raster(
        output_file=output_file,
        array=geo,
        lon_min=lon_min,
        lat_max=lat_max,
        resolution=resolution,
        data_type="CFLOAT" if np.iscomplexobj(geo) else "FLOAT",
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
            "band": band,
            "input_number_bands": input_meta["number_bands"],
            "mask_edges": mask_edges,
        }
    )

    log("done")
    return out


def _source_footprint_mask(lat, lon, valid_mask, grid_lon2d, grid_lat2d):
    """Return a mask for grid cells inside the valid source geolocation footprint."""
    import numpy as np
    from matplotlib.path import Path as MplPath

    valid_mask = np.asarray(valid_mask, dtype=bool)
    rows, cols = valid_mask.shape
    vertices = []

    for col in range(cols):
        row_indexes = np.flatnonzero(valid_mask[:, col])
        if row_indexes.size:
            row = row_indexes[0]
            vertices.append((float(lon[row, col]), float(lat[row, col])))

    for row in range(rows):
        col_indexes = np.flatnonzero(valid_mask[row, :])
        if col_indexes.size:
            col = col_indexes[-1]
            vertices.append((float(lon[row, col]), float(lat[row, col])))

    for col in range(cols - 1, -1, -1):
        row_indexes = np.flatnonzero(valid_mask[:, col])
        if row_indexes.size:
            row = row_indexes[-1]
            vertices.append((float(lon[row, col]), float(lat[row, col])))

    for row in range(rows - 1, -1, -1):
        col_indexes = np.flatnonzero(valid_mask[row, :])
        if col_indexes.size:
            col = col_indexes[0]
            vertices.append((float(lon[row, col]), float(lat[row, col])))

    vertices = np.asarray(vertices, dtype=np.float64)
    finite = np.isfinite(vertices).all(axis=1)
    vertices = vertices[finite]
    if vertices.shape[0] < 3:
        raise ValueError("Could not build a valid source footprint polygon.")

    path = MplPath(vertices)
    points = np.column_stack([grid_lon2d.ravel(), grid_lat2d.ravel()])
    return path.contains_points(points).reshape(grid_lon2d.shape)


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
