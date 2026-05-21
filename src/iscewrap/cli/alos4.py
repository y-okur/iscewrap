"""Command line interface for ALOS-4 pair processing."""

from __future__ import annotations

import argparse

from iscewrap.alos4 import process_alos4_pair


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create XML and optionally run ISCE2 alos2App.py for ALOS-4 data."
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
    parser.add_argument("--alos2-compat-mode", default="FBD")
    parser.add_argument(
        "--backend",
        choices=["native", "compat"],
        default="native",
        help="Use native ALOS-4 filename hooks or the older ALOS-2 symlink staging fallback.",
    )
    parser.add_argument(
        "--range-sampling-rate",
        action="append",
        default=[],
        metavar="CODE=HZ",
        help="Patch an ALOS-4 range sampling code for ISCE2, e.g. 98=98000000",
    )
    parser.add_argument(
        "--stage-compat-names",
        action="store_true",
        help="Stage ALOS-4 files as ALOS-2-style symlinks before running.",
    )
    parser.add_argument("--no-run", action="store_true")
    parser.add_argument("--use-gpu", action="store_true")
    parser.add_argument("--no-ionosphere", action="store_true")
    parser.add_argument("--no-apply-ionosphere", action="store_true")
    parser.add_argument(
        "--polarization",
        action="append",
        choices=["HH", "HV", "VH", "VV"],
        help="Extract only this polarization from ZIP inputs. Can be repeated.",
    )
    parser.add_argument("--geocode-file-list", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = process_alos4_pair(
        reference_input=args.reference_input,
        secondary_input=args.secondary_input,
        work_dir=args.work_dir,
        dem_coreg=args.dem_coreg,
        dem_geocode=args.dem_geocode,
        water_body=args.water_body,
        run=not args.no_run,
        alos2app_cmd=args.alos2app_cmd,
        start_step=args.start_step,
        end_step=args.end_step,
        alos2_compat_mode=args.alos2_compat_mode,
        backend=args.backend,
        stage_compat_names=args.stage_compat_names,
        range_sampling_rates=_parse_range_sampling_rates(args.range_sampling_rate),
        use_gpu=args.use_gpu,
        do_ionosphere=not args.no_ionosphere,
        apply_ionosphere=not args.no_apply_ionosphere,
        polarizations=args.polarization,
        geocode_file_list=args.geocode_file_list,
    )
    print(result["xml_file"])


def _parse_range_sampling_rates(values: list[str]) -> dict[int, float] | None:
    if not values:
        return None

    rates = {}
    for value in values:
        code, sep, hz = value.partition("=")
        if sep == "":
            raise ValueError(f"Expected CODE=HZ for --range-sampling-rate, got: {value}")
        rates[int(code)] = float(hz)
    return rates


if __name__ == "__main__":
    main()
