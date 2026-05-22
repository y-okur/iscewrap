"""Command line interface for plotting complex GDAL-readable rasters."""

from __future__ import annotations

import argparse

from iscewrap.plot import plotcomplexdata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot complex raster amplitude or phase."
    )
    parser.add_argument("input", help="Path to the input raster file.")
    parser.add_argument(
        "--display",
        choices=["phs", "amp"],
        default="phs",
        help='Display "phs" for phase or "amp" for amplitude. Default: phs.',
    )
    parser.add_argument("--vmin", dest="datamin", type=float, default=None)
    parser.add_argument("--vmax", dest="datamax", type=float, default=None)
    parser.add_argument("--title", default="")
    parser.add_argument("--aspect", type=float, default=1.0)
    parser.add_argument("--interpolation", default="nearest")
    parser.add_argument(
        "--no-colorbar",
        action="store_true",
        help="Do not draw a colorbar.",
    )
    parser.add_argument(
        "--colorbar-orientation",
        choices=["horizontal", "vertical"],
        default="horizontal",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    plotcomplexdata(
        GDALfilename=args.input,
        display=args.display,
        datamin=args.datamin,
        datamax=args.datamax,
        title=args.title,
        aspect=args.aspect,
        interpolation=args.interpolation,
        draw_colorbar=not args.no_colorbar,
        colorbar_orientation=args.colorbar_orientation,
    )


if __name__ == "__main__":
    main()
