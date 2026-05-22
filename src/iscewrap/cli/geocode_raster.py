"""Command line interface for radar-to-geographic raster geocoding."""

from __future__ import annotations

import argparse

from iscewrap.alos2 import geocode_raster


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Geocode a radar-coordinate ISCE raster using matching latitude "
            "and longitude rasters."
        )
    )
    parser.add_argument("input_file", help="Radar-coordinate raster to geocode.")
    parser.add_argument("lat_file", help="ISCE latitude raster with same shape.")
    parser.add_argument("lon_file", help="ISCE longitude raster with same shape.")
    parser.add_argument("output_file", help="Output geocoded raw raster path.")
    parser.add_argument(
        "--resolution",
        type=float,
        default=1 / 3600,
        help="Output geographic spacing in degrees. Default: 1/3600.",
    )
    parser.add_argument(
        "--method",
        choices=["linear", "nearest", "cubic"],
        default="nearest",
        help="Interpolation method passed to scipy.interpolate.griddata.",
    )
    parser.add_argument(
        "--nodata",
        type=float,
        default=float("nan"),
        help="Fill value outside interpolation support. Default: NaN.",
    )
    parser.add_argument(
        "--band",
        type=int,
        default=None,
        help=(
            "Zero-based input band to geocode. Omit to geocode all bands and "
            "preserve a multi-band output."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress messages during geocoding.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = geocode_raster(
        input_file=args.input_file,
        lat_file=args.lat_file,
        lon_file=args.lon_file,
        output_file=args.output_file,
        resolution=args.resolution,
        method=args.method,
        nodata=args.nodata,
        band=args.band,
        verbose=not args.quiet,
    )

    print(f"output file: {result['output_file']}")
    print(f"xml file: {result['xml_file']}")
    print(f"vrt file: {result['vrt_file']}")
    print(f"shape: {result['shape']}")
    print(f"data type: {result['data_type']}")
    print(f"number of bands: {result['number_bands']}")
    print(f"extent: {result['extent']}")


if __name__ == "__main__":
    main()
