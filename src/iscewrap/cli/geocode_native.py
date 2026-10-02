"""Command line interface for native ISCE2 ALOS geocoding."""

from __future__ import annotations

import argparse

from iscewrap.alos2 import geocode_raster_native_isce2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Geocode one raster using ISCE2's native ALOS geocoder."
    )
    parser.add_argument("input_file", help="Radar-coordinate raster to geocode.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output raster name. Default: INPUT.geo.",
    )
    parser.add_argument(
        "--track",
        required=True,
        help="Reference track XML, e.g. 250728.track.xml.",
    )
    parser.add_argument(
        "--dem",
        required=True,
        help="DEM for geocoding, without .xml suffix.",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("SOUTH", "NORTH", "WEST", "EAST"),
        help="Geocode bounding box. If omitted, infer with ISCE2 getBboxGeo().",
    )
    parser.add_argument(
        "--grid-reference",
        default=None,
        help=(
            "Existing geocoded raster whose VRT/XML extent should define the "
            "output grid. Useful for matching native alos2App.py products."
        ),
    )
    parser.add_argument(
        "--range-looks",
        type=int,
        default=None,
        help="Range looks. Default: infer from *_Nrlks_Malks filename.",
    )
    parser.add_argument(
        "--azimuth-looks",
        type=int,
        default=None,
        help="Azimuth looks. Default: infer from *_Nrlks_Malks filename.",
    )
    parser.add_argument(
        "--interp",
        choices=["sinc", "bilinear", "bicubic", "nearest"],
        default=None,
        help="Interpolation method. Default: ISCE2 logic, sinc for CFLOAT else bilinear.",
    )
    parser.add_argument("--top-shift", type=int, default=0)
    parser.add_argument("--left-shift", type=int, default=0)
    parser.add_argument(
        "--no-multilook-offset",
        action="store_true",
        help="Disable ISCE2 multilook center offset adjustment.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = geocode_raster_native_isce2(
        input_file=args.input_file,
        track_xml=args.track,
        dem_file=args.dem,
        output_file=args.output,
        grid_reference=args.grid_reference,
        bbox=args.bbox,
        range_looks=args.range_looks,
        azimuth_looks=args.azimuth_looks,
        interp_method=args.interp,
        top_shift=args.top_shift,
        left_shift=args.left_shift,
        add_multilook_offset=not args.no_multilook_offset,
    )

    print(f"output file: {result['output_file']}")
    print(f"xml file: {result['xml_file']}")
    print(f"vrt file: {result['vrt_file']}")
    print(f"grid reference: {result['grid_reference']}")
    print(f"bbox: {result['bbox']}")
    print(f"range looks: {result['range_looks']}")
    print(f"azimuth looks: {result['azimuth_looks']}")
    print(f"interpolation: {result['interp_method']}")


if __name__ == "__main__":
    main()
