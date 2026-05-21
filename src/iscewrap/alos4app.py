"""Prototype ALOS app front door for ALOS-2 and ALOS-4 workflows."""

from __future__ import annotations

from pathlib import Path
import zipfile

from iscewrap.alos2.metadata import parse_alos2_img_filename
from iscewrap.alos2.organize import parse_alos2_stripmap_zip_name
from iscewrap.alos2.workflow import process_alos2_pair
from iscewrap.alos4.metadata import parse_alos4_img_filename
from iscewrap.alos4.organize import parse_alos4_stripmap_zip_name
from iscewrap.alos4.workflow import process_alos4_pair


SUPPORTED_ALOS4_OBS_MODES = {"UWD"}


def process_alos_pair(
    reference_input,
    secondary_input,
    work_dir,
    *,
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
    polarizations=None,
    alos4_multilook_params=None,
    alos4_compat_mode="FBD",
    alos4_stage_compat_names=False,
    alos4_backend="native",
    alos4_range_sampling_rates=None,
    interferogram_filter_strength=0.3,
    interferogram_filter_window_size=32,
    interferogram_filter_step_size=4,
    remove_magnitude_before_filtering=True,
    use_water_body_to_determine_number_of_matching_offsets=True,
    do_dense_offset=False,
    estimate_residual_offset_after_geometrical_coregistration=False,
    delete_geometry_files_used_for_dense_offset_estimation=False,
    dense_offset_estimation_window_width=64,
    dense_offset_estimation_window_height=64,
    dense_offset_skip_width=32,
    dense_offset_skip_height=32,
) -> dict:
    """Process an ALOS pair by detecting the sensor family from both inputs.

    Current prototype support:

    * ALOS-2 + ALOS-2: dispatches to the existing full ``alos2App.py`` wrapper.
    * ALOS-4 UWD + ALOS-4 UWD: dispatches to the ALOS-4 backend that keeps
      native ALOS-4 filenames and reuses ISCE2 ``Alos2Proc`` functions.

    Mixed ALOS-2/ALOS-4 pairs are intentionally rejected for now.
    """
    reference_product = detect_alos_input(reference_input)
    secondary_product = detect_alos_input(secondary_input)

    if reference_product["sensor"] != secondary_product["sensor"]:
        raise ValueError(
            "Mixed ALOS-2/ALOS-4 pairs are not enabled yet. "
            f"Detected reference={reference_product['sensor']} and "
            f"secondary={secondary_product['sensor']}."
        )

    common_kwargs = {
        "reference_input": reference_input,
        "secondary_input": secondary_input,
        "work_dir": work_dir,
        "dem_coreg": dem_coreg,
        "dem_geocode": dem_geocode,
        "water_body": water_body,
        "auto_prepare_dem": auto_prepare_dem,
        "dem_overwrite": dem_overwrite,
        "convert_dem_to_wgs84_ellipsoid": convert_dem_to_wgs84_ellipsoid,
        "use_gpu": use_gpu,
        "do_ionosphere": do_ionosphere,
        "apply_ionosphere": apply_ionosphere,
        "run": run,
        "alos2app_cmd": alos2app_cmd,
        "do_insar": do_insar,
        "steps": steps,
        "start_step": start_step,
        "end_step": end_step,
        "geocode_file_list": geocode_file_list,
        "polarizations": polarizations,
        "interferogram_filter_strength": interferogram_filter_strength,
        "interferogram_filter_window_size": interferogram_filter_window_size,
        "interferogram_filter_step_size": interferogram_filter_step_size,
        "remove_magnitude_before_filtering": remove_magnitude_before_filtering,
        "do_dense_offset": do_dense_offset,
        "estimate_residual_offset_after_geometrical_coregistration": (
            estimate_residual_offset_after_geometrical_coregistration
        ),
        "delete_geometry_files_used_for_dense_offset_estimation": (
            delete_geometry_files_used_for_dense_offset_estimation
        ),
        "dense_offset_estimation_window_width": dense_offset_estimation_window_width,
        "dense_offset_estimation_window_height": dense_offset_estimation_window_height,
        "dense_offset_skip_width": dense_offset_skip_width,
        "dense_offset_skip_height": dense_offset_skip_height,
    }

    if reference_product["sensor"] == "ALOS2":
        result = process_alos2_pair(**common_kwargs)
        result["workflow"] = "ALOS2"
        result["reference_product"] = reference_product
        result["secondary_product"] = secondary_product
        return result

    _validate_alos4_uwd_pair(reference_product, secondary_product)

    alos4_kwargs = {
        **common_kwargs,
        "multilook_params": alos4_multilook_params,
        "alos2_compat_mode": alos4_compat_mode,
        "stage_compat_names": alos4_stage_compat_names,
        "backend": alos4_backend,
        "range_sampling_rates": alos4_range_sampling_rates,
        "use_water_body_to_determine_number_of_matching_offsets": (
            use_water_body_to_determine_number_of_matching_offsets
        ),
    }
    result = process_alos4_pair(**alos4_kwargs)
    result["workflow"] = (
        "ALOS4_UWD_NATIVE" if alos4_backend == "native" else "ALOS4_UWD_COMPAT"
    )
    result["reference_product"] = reference_product
    result["secondary_product"] = secondary_product
    return result


def detect_alos_input(input_path) -> dict[str, str | Path | None]:
    """Detect ALOS sensor and lightweight product metadata from a ZIP or folder."""
    path = Path(input_path).resolve()

    if path.suffix.lower() == ".zip":
        from_name = _detect_zip_filename(path)
        if from_name is not None:
            return from_name
        return _detect_zip_members(path)

    if path.is_dir():
        return _detect_directory(path)

    return _detect_filename(path)


def _validate_alos4_uwd_pair(reference_product: dict, secondary_product: dict) -> None:
    modes = {
        reference_product.get("obs_mode"),
        secondary_product.get("obs_mode"),
    }
    unsupported = sorted(mode for mode in modes if mode not in SUPPORTED_ALOS4_OBS_MODES)
    if unsupported:
        raise ValueError(
            "The ALOS-4 prototype currently supports UWD-UWD pairs only. "
            f"Detected unsupported observation mode(s): {unsupported}."
        )


def _detect_zip_filename(path: Path) -> dict[str, str | Path | None] | None:
    try:
        product = parse_alos4_stripmap_zip_name(path)
    except ValueError:
        pass
    else:
        return {
            "sensor": "ALOS4",
            "source": path,
            "path": product.path,
            "frame": product.frame,
            "date": product.date,
            "obs_mode": _alos4_zip_mode_to_obs_mode(product.mode),
            "beam": product.beam,
        }

    try:
        product = parse_alos2_stripmap_zip_name(path)
    except ValueError:
        return None

    return {
        "sensor": "ALOS2",
        "source": path,
        "path": product.path,
        "frame": product.frame,
        "date": product.date,
        "obs_mode": product.mode,
        "beam": product.beam,
    }


def _detect_zip_members(path: Path) -> dict[str, str | Path | None]:
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            detected = _detect_filename(Path(name))
            if detected["sensor"] in {"ALOS2", "ALOS4"}:
                detected["source"] = path
                return detected

    raise ValueError(f"Could not identify ALOS sensor from ZIP contents: {path}")


def _detect_directory(path: Path) -> dict[str, str | Path | None]:
    for img_file in sorted(path.rglob("IMG-*")):
        detected = _detect_filename(img_file)
        if detected["sensor"] in {"ALOS2", "ALOS4"}:
            return detected

    raise ValueError(f"Could not identify ALOS sensor from directory: {path}")


def _detect_filename(path: Path) -> dict[str, str | Path | None]:
    try:
        info = parse_alos4_img_filename(path)
    except ValueError:
        pass
    else:
        return {
            "sensor": "ALOS4",
            "source": path,
            "path": info["path"],
            "frame": info["frame"],
            "date": info["date"],
            "obs_mode": info["obs_mode"],
            "beam": info["beam"],
        }

    try:
        info = parse_alos2_img_filename(path)
    except ValueError:
        return {"sensor": "UNKNOWN", "source": path, "obs_mode": None}

    return {
        "sensor": "ALOS2",
        "source": path,
        "path": None,
        "frame": info["frame"],
        "date": f"20{info['date']}",
        "obs_mode": info["mode"],
        "beam": None,
    }


def _alos4_zip_mode_to_obs_mode(mode: str) -> str | None:
    """Map observed ALOS-4 ZIP mode tokens to summary/SceneID observation modes."""
    prefix = mode[:2].upper()
    mapping = {
        "RU": "UWD",
        "RF": "FWD",
    }
    return mapping.get(prefix)
