"""Command line helpers for geographic ISCE rasters."""

from __future__ import annotations

import argparse

from iscewrap.geo import geo_to_kml


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a geocoded ISCE .geo raster to a KML or KMZ overlay."
    )
    parser.add_argument("input_file")
    parser.add_argument("output_file", nargs="?")
    parser.add_argument("--output-png")
    parser.add_argument("--band", type=int)
    parser.add_argument(
        "--value-mode",
        choices=["auto", "real", "imag", "magnitude", "phase"],
        default="auto",
    )
    parser.add_argument("--cmap")
    parser.add_argument("--alpha", type=float, default=0.75)
    parser.add_argument("--vmin", type=float)
    parser.add_argument("--vmax", type=float)
    parser.add_argument(
        "--percentile-clip",
        nargs=2,
        type=float,
        metavar=("LOW", "HIGH"),
        default=(2.0, 98.0),
    )
    parser.add_argument("--no-percentile-clip", action="store_true")
    parser.add_argument("--name")
    parser.add_argument("--colorbar", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    result = geo_to_kml(
        input_file=args.input_file,
        output_file=args.output_file,
        output_png=args.output_png,
        band=args.band,
        value_mode=args.value_mode,
        cmap=args.cmap,
        alpha=args.alpha,
        percentile_clip=None if args.no_percentile_clip else tuple(args.percentile_clip),
        vmin=args.vmin,
        vmax=args.vmax,
        name=args.name,
        colorbar=args.colorbar,
    )
    print(f"kml file: {result['kml_file']}")
    print(f"png file: {result['png_file']}")
    print(f"extent: {result['extent']}")


if __name__ == "__main__":
    main()
