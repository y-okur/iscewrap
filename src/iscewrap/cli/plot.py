"""Command line interface for plotting GDAL-readable rasters."""

from __future__ import annotations

import argparse

from iscewrap.plot import plot_raster


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot a GDAL-readable raster.")
    parser.add_argument("input", help="Path to the input raster file.")
    parser.add_argument(
        "--band",
        type=int,
        default=1,
        help="One-based raster band. Default: 1.",
    )
    parser.add_argument(
        "--wrap",
        action="store_true",
        help="Wrap values between -pi and pi.",
    )
    parser.add_argument(
        "--cmap",
        dest="colormap",
        default="rainbow",
        help="Matplotlib colormap. Default: rainbow.",
    )
    parser.add_argument("--vmin", dest="datamin", type=float, default=None)
    parser.add_argument("--vmax", dest="datamax", type=float, default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument(
        "--amplitude-scale",
        choices=["auto", "linear", "log", "db"],
        default="auto",
        help=(
            "Amplitude display scaling. auto applies log10 only to detected "
            "ISCE amplitude bands. Default: auto."
        ),
    )
    parser.add_argument("--nodata", type=float, default=None)
    parser.add_argument("--interpolation", default="nearest")
    parser.add_argument("--aspect", type=float, default=1.0)
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
    plot_raster(
        input_file=args.input,
        band=args.band,
        wrap="wrap" if args.wrap else None,
        colormap=args.colormap,
        datamin=args.datamin,
        datamax=args.datamax,
        title=args.title,
        aspect=args.aspect,
        interpolation=args.interpolation,
        nodata=args.nodata,
        draw_colorbar=not args.no_colorbar,
        colorbar_orientation=args.colorbar_orientation,
        amplitude_scale=args.amplitude_scale,
    )


if __name__ == "__main__":
    main()
