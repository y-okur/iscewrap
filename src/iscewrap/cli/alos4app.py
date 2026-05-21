"""Command line interface for the prototype ALOS-2/ALOS-4 app."""

from __future__ import annotations

import argparse

from iscewrap.alos4app import detect_alos_input, process_alos_pair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prototype ALOS app. Auto-detects ALOS-2 vs ALOS-4 inputs, runs "
            "the full ALOS-2 workflow for ALOS-2 pairs, and runs the ALOS-4 "
            "UWD backend for ALOS-4 UWD pairs."
        )
    )
    parser.add_argument("reference_input")
    parser.add_argument("secondary_input")
    parser.add_argument("work_dir")
    parser.add_argument("--dem-coreg")
    parser.add_argument("--dem-geocode")
    parser.add_argument("--water-body")
    parser.add_argument("--alos2app-cmd", default="alos2App.py")
    parser.add_argument("--start-step")
    parser.add_argument("--end-step")
    parser.add_argument("--alos4-compat-mode", default="FBD")
    parser.add_argument(
        "--alos4-backend",
        choices=["native", "compat"],
        default="native",
        help="Use native ALOS-4 filename hooks or the older ALOS-2 symlink staging fallback.",
    )
    parser.add_argument(
        "--alos4-stage-compat-names",
        action="store_true",
        help="Stage ALOS-4 files as ALOS-2-style symlinks before running.",
    )
    parser.add_argument(
        "--alos4-range-sampling-rate",
        action="append",
        default=[],
        metavar="CODE=HZ",
        help="Patch an ALOS-4 range sampling code, e.g. 98=98242186.9",
    )
    parser.add_argument(
        "--polarization",
        action="append",
        choices=["HH", "HV", "VH", "VV"],
        help="Extract only this polarization from ZIP inputs. Can be repeated.",
    )
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--no-ionosphere", action="store_true")
    parser.add_argument("--no-apply-ionosphere", action="store_true")
    parser.add_argument("--no-auto-dem", action="store_true")
    parser.add_argument("--dem-overwrite", action="store_true")
    parser.add_argument("--no-dem-wgs84-ellipsoid", action="store_true")
    parser.add_argument("--geocode-file-list", nargs="*")
    parser.add_argument("--detect-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.detect_only:
        print(f"reference: {detect_alos_input(args.reference_input)}")
        print(f"secondary: {detect_alos_input(args.secondary_input)}")
        return

    result = process_alos_pair(
        reference_input=args.reference_input,
        secondary_input=args.secondary_input,
        work_dir=args.work_dir,
        dem_coreg=args.dem_coreg,
        dem_geocode=args.dem_geocode,
        water_body=args.water_body,
        auto_prepare_dem=not args.no_auto_dem,
        dem_overwrite=args.dem_overwrite,
        convert_dem_to_wgs84_ellipsoid=not args.no_dem_wgs84_ellipsoid,
        run=not args.no_run,
        alos2app_cmd=args.alos2app_cmd,
        start_step=args.start_step,
        end_step=args.end_step,
        alos4_compat_mode=args.alos4_compat_mode,
        alos4_backend=args.alos4_backend,
        alos4_stage_compat_names=args.alos4_stage_compat_names,
        alos4_range_sampling_rates=_parse_range_sampling_rates(
            args.alos4_range_sampling_rate
        ),
        polarizations=args.polarization,
        use_gpu=args.use_gpu,
        do_ionosphere=not args.no_ionosphere,
        apply_ionosphere=not args.no_apply_ionosphere,
        geocode_file_list=args.geocode_file_list,
    )
    print(f"workflow: {result['workflow']}")
    print(f"pair name: {result['pair_name']}")
    print(f"xml file: {result['xml_file']}")
    print(f"run directory: {result['run_dir']}")


def _parse_range_sampling_rates(values: list[str]) -> dict[int, float] | None:
    if not values:
        return None

    rates = {}
    for value in values:
        code, sep, hz = value.partition("=")
        if sep == "":
            raise ValueError(
                f"Expected CODE=HZ for --alos4-range-sampling-rate, got: {value}"
            )
        rates[int(code)] = float(hz)
    return rates


if __name__ == "__main__":
    main()
