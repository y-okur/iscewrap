"""Command-line interface for ALOS-2 ISCE2 processing."""

from __future__ import annotations

import argparse

from iscewrap.alos2.workflow import process_alos2_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an ALOS-2 ISCE2 alos2App.py workflow.")
    parser.add_argument("reference_input", help="Reference ALOS-2 ZIP file or extracted product directory.")
    parser.add_argument("secondary_input", help="Secondary ALOS-2 ZIP file or extracted product directory.")
    parser.add_argument("work_dir", help="Working directory.")
    parser.add_argument("--dem-coreg", default=None)
    parser.add_argument("--dem-geocode", default=None)
    parser.add_argument("--water-body", default=None)
    parser.add_argument("--alos2app-cmd", default="alos2App.py")
    parser.add_argument("--start-step", default=None)
    parser.add_argument("--end-step", default=None)
    parser.add_argument("--no-run", action="store_true", help="Only create the XML file.")
    parser.add_argument("--gpu", action="store_true", help="Use GPU.")
    parser.add_argument("--no-steps", action="store_true", help="Do not pass --steps to alos2App.py.")
    parser.add_argument(
        "--geocode-file-list",
        nargs="*",
        default=None,
        help='Files or glob patterns to geocode, e.g. --geocode-file-list "diff*int" "filt*int*"',
    )

    args = parser.parse_args()

    result = process_alos2_pair(
        reference_input=args.reference_input,
        secondary_input=args.secondary_input,
        work_dir=args.work_dir,
        dem_coreg=args.dem_coreg,
        dem_geocode=args.dem_geocode,
        water_body=args.water_body,
        use_gpu=args.gpu,
        run=not args.no_run,
        alos2app_cmd=args.alos2app_cmd,
        start_step=args.start_step,
        end_step=args.end_step,
        steps=not args.no_steps,
        geocode_file_list=args.geocode_file_list,
    )

    print("\nDone.")
    print(f"Pair name: {result['pair_name']}")
    print(f"XML file: {result['xml_file']}")
    print(f"Run directory: {result['run_dir']}")


if __name__ == "__main__":
    main()
