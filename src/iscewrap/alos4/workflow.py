"""High-level ALOS-4 pair processing workflow."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys

from iscewrap.alos2.workflow import (
    _parse_reference_bounding_box_from_log,
    _step_index,
    prepare_srtm_dem_and_wbd,
)
from iscewrap.alos2.runner import run_isce2_alos2app, validate_alos2_steps

from .backend import default_range_sampling_rates
from .metadata import detect_product_metadata, extract_alos4_zip
from .xml import create_alos4app_xml


def process_alos4_pair(
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
    multilook_params=None,
    alos2_compat_mode="FBD",
    stage_compat_names=False,
    backend="native",
    range_sampling_rates=None,
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
    polarizations=None,
) -> dict:
    """Create XML and optionally run the ALOS-4/ALOS-2 processing chain.

    The default backend keeps ALOS-4 files in their native filenames and installs
    package-level ISCE2 hooks at runtime.  ``backend="compat"`` keeps the earlier
    symlink staging behavior as a fallback.
    """
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
        extract_alos4_zip(reference_input, raw_dir, polarizations=polarizations)
        if reference_input.suffix.lower() == ".zip"
        else reference_input
    )
    secondary_dir = (
        extract_alos4_zip(secondary_input, raw_dir, polarizations=polarizations)
        if secondary_input.suffix.lower() == ".zip"
        else secondary_input
    )

    reference_meta = detect_product_metadata(reference_dir)
    secondary_meta = detect_product_metadata(secondary_dir)

    reference_dir = _select_alos4_processing_dir(reference_dir, reference_meta)
    secondary_dir = _select_alos4_processing_dir(secondary_dir, secondary_meta)

    reference_info = reference_meta["img_info"]
    secondary_info = secondary_meta["img_info"]

    pair_name = f"{reference_info['date']}_{secondary_info['date']}"
    xml_file = (xml_dir / f"alos4App_{pair_name}.xml").resolve()
    dem_result = None
    baseline_result = None

    if backend not in {"native", "compat"}:
        raise ValueError("backend must be either 'native' or 'compat'")

    use_compat_backend = backend == "compat" or stage_compat_names

    reference_processing_dir = reference_dir
    secondary_processing_dir = secondary_dir
    if use_compat_backend:
        compat_dir = work_dir / "alos2_compat"
        reference_processing_dir = stage_alos4_as_alos2_names(
            reference_dir,
            compat_dir / "reference",
            mode=alos2_compat_mode,
        )
        secondary_processing_dir = stage_alos4_as_alos2_names(
            secondary_dir,
            compat_dir / "secondary",
            mode=alos2_compat_mode,
        )

    missing_dem_inputs = dem_coreg is None or dem_geocode is None or water_body is None
    should_auto_prepare_dem = (
        auto_prepare_dem
        and missing_dem_inputs
        and run
        and _requested_step_range_reaches("download_dem", start_step, end_step)
    )

    if should_auto_prepare_dem:
        create_alos4app_xml(
            reference_dir=reference_processing_dir,
            secondary_dir=secondary_processing_dir,
            output_xml=xml_file,
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
            use_water_body_to_determine_number_of_matching_offsets=(
                use_water_body_to_determine_number_of_matching_offsets
            ),
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
        baseline_result = _run_patched_alos4_app(
            xml_file=xml_file,
            run_dir=run_dir,
            alos2app_cmd=alos2app_cmd,
            reference_dir=reference_processing_dir,
            secondary_dir=secondary_processing_dir,
            backend=backend,
            alos2_compat_mode=alos2_compat_mode,
            range_sampling_rates=range_sampling_rates,
            start_step=None,
            end_step="baseline",
            steps=steps,
        )
        baseline_log = run_dir / "alos4App_full_terminal.log"
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

    create_alos4app_xml(
        reference_dir=reference_processing_dir,
        secondary_dir=secondary_processing_dir,
        output_xml=xml_file,
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
        use_water_body_to_determine_number_of_matching_offsets=(
            use_water_body_to_determine_number_of_matching_offsets
        ),
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
        final_start_step = start_step
        if should_auto_prepare_dem:
            if end_step == "baseline":
                final_start_step = None
            elif _requested_step_range_reaches("download_dem", start_step, end_step):
                final_start_step = "download_dem"

        if final_start_step is not None or baseline_result is None:
            result = _run_patched_alos4_app(
                xml_file=xml_file,
                run_dir=run_dir,
                alos2app_cmd=alos2app_cmd,
                reference_dir=reference_processing_dir,
                secondary_dir=secondary_processing_dir,
                backend=backend,
                alos2_compat_mode=alos2_compat_mode,
                range_sampling_rates=range_sampling_rates,
                start_step=final_start_step,
                end_step=end_step,
                steps=steps,
            )

    return {
        "pair_name": pair_name,
        "reference_dir": reference_dir,
        "secondary_dir": secondary_dir,
        "reference_processing_dir": reference_processing_dir,
        "secondary_processing_dir": secondary_processing_dir,
        "xml_file": xml_file,
        "run_dir": run_dir,
        "reference_info": reference_info,
        "secondary_info": secondary_info,
        "reference_summary": reference_meta["summary"],
        "secondary_summary": secondary_meta["summary"],
        "multilook_params": multilook_params,
        "dem_result": dem_result,
        "backend": backend,
        "alos2_compat_mode": alos2_compat_mode,
        "stage_compat_names": use_compat_backend,
        "range_sampling_rates": default_range_sampling_rates(range_sampling_rates),
        "dem_coreg": None if dem_coreg is None else Path(dem_coreg).resolve(),
        "dem_geocode": None if dem_geocode is None else Path(dem_geocode).resolve(),
        "water_body": None if water_body is None else Path(water_body).resolve(),
        "start_step": start_step,
        "end_step": end_step,
        "stdout": None if result is None else result.stdout,
        "stderr": None if result is None else result.stderr,
    }


def _run_patched_alos4_app(
    *,
    xml_file: Path,
    run_dir: Path,
    alos2app_cmd: str,
    reference_dir: Path,
    secondary_dir: Path,
    backend: str,
    alos2_compat_mode: str,
    range_sampling_rates: dict[int, float] | None,
    start_step: str | None,
    end_step: str | None,
    steps: bool,
):
    patched_alos2app_cmd = _prepare_alos4_app_launcher(
        run_dir,
        alos2app_cmd=alos2app_cmd,
        reference_dir=reference_dir,
        secondary_dir=secondary_dir,
        backend=backend,
        alos2_compat_mode=alos2_compat_mode,
        range_sampling_rates=range_sampling_rates,
    )
    return run_isce2_alos2app(
        xml_file=xml_file,
        work_dir=run_dir,
        alos2app_cmd=patched_alos2app_cmd,
        start_step=start_step,
        end_step=end_step,
        steps=steps,
        log_file=run_dir / "alos4App_full_terminal.log",
    )


def _requested_step_range_reaches(
    target_step: str,
    start_step: str | None,
    end_step: str | None,
) -> bool:
    target_index = _step_index(target_step)
    start_index = _step_index(start_step)
    end_index = 10_000 if end_step is None else _step_index(end_step)
    return start_index <= target_index <= end_index


def _select_alos4_processing_dir(input_dir: Path, metadata: dict) -> Path:
    """Use product root for one product, or preserve a folder of stitched frames."""
    img_roots = {img_file.parent.resolve() for img_file in metadata["files"]["IMG"]}
    if len(img_roots) == 1:
        return metadata["product_root"]
    return input_dir.resolve()


def stage_alos4_as_alos2_names(
    product_dir: str | Path,
    output_dir: str | Path,
    *,
    mode: str = "FBD",
) -> Path:
    """Stage ALOS-4 CEOS files with ALOS-2-style names for ISCE2.

    ISCE2's ``runPreprocessor`` searches for names like
    ``LED-ALOS2<path><frame>-<YYMMDD>-<mode>``. ALOS-4 CEOS files are linked
    into a temporary directory with that naming convention while preserving the
    original data files.
    """
    product_dir = Path(product_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = detect_product_metadata(product_dir)["files"]
    for img_file in files["IMG"]:
        info = _parse_staging_img_info(img_file)
        frame_token = f"{info['path']}{info['frame_padded']}"
        date_token = info["date"][2:]
        stem = f"ALOS2{frame_token}-{date_token}-{mode.upper()}"

        _link_replace(img_file, output_dir / f"IMG-{info['polarization']}-{stem}")
        _link_matching_aux(files["LED"], img_file.parent, output_dir / f"LED-{stem}")
        _link_matching_aux(files["TRL"], img_file.parent, output_dir / f"TRL-{stem}")
        _link_matching_aux(files["VOL"], img_file.parent, output_dir / f"VOL-{stem}")

    return output_dir


def _parse_staging_img_info(img_file: Path) -> dict[str, str]:
    from .metadata import parse_alos4_img_filename

    return parse_alos4_img_filename(img_file)


def _link_matching_aux(files: list[Path], product_root: Path, target: Path) -> None:
    matches = [file for file in files if file.parent.resolve() == product_root.resolve()]
    if not matches:
        return
    _link_replace(matches[0], target)


def _link_replace(source: Path, target: Path) -> None:
    source = source.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() or target.is_symlink():
        if target.is_symlink() and Path(os.readlink(target)) == source:
            return
        target.unlink()

    target.symlink_to(source)


def _prepare_alos4_app_launcher(
    run_dir: Path,
    *,
    alos2app_cmd: str,
    reference_dir: Path,
    secondary_dir: Path,
    backend: str,
    alos2_compat_mode: str,
    range_sampling_rates: dict[int, float] | None,
) -> Path:
    """Create an ``alos4app.py`` launcher for the external ISCE process."""
    run_dir = Path(run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    rates = default_range_sampling_rates(range_sampling_rates)

    alos2app_path = shutil.which(alos2app_cmd)
    if alos2app_path is None:
        alos2app_path = alos2app_cmd
    alos2app_path = str(Path(alos2app_path).resolve())

    launcher = run_dir / "alos4_native_alos2App.py"
    launcher.write_text(
        "\n".join(
            [
                f"#!{sys.executable}",
                '"""ALOS-4 app launcher generated by iscewrap."""',
                "",
                "from pathlib import Path",
                "import runpy",
                "import sys",
                "",
                f"ALOS2APP = {alos2app_path!r}",
                f"REFERENCE_DIR = {str(Path(reference_dir).resolve())!r}",
                f"SECONDARY_DIR = {str(Path(secondary_dir).resolve())!r}",
                f"BACKEND = {backend!r}",
                f"ALOS2_COMPAT_MODE = {alos2_compat_mode!r}",
                f"ALIAS_DIR = {str((run_dir / '.alos4_native_alias').resolve())!r}",
                f"RATES = {rates!r}",
                "",
                "from iscewrap.alos4.backend import install_alos4_backend",
                "",
                "install_alos4_backend(",
                "    reference_dir=REFERENCE_DIR,",
                "    secondary_dir=SECONDARY_DIR,",
                "    alias_dir=ALIAS_DIR,",
                "    compat_mode=ALOS2_COMPAT_MODE,",
                "    use_aliases=BACKEND == 'native',",
                "    range_sampling_rates=RATES,",
                ")",
                'sys.argv = [ALOS2APP] + sys.argv[1:]',
                'runpy.run_path(str(Path(ALOS2APP)), run_name="__main__")',
                "",
            ]
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    return launcher
