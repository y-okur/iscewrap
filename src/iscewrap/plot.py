"""Plotting helpers for ISCE rasters."""

from __future__ import annotations

from pathlib import Path


AMPLITUDE_PRODUCT_RULES = {
    "amp": "all",
    "cor": "first",
    "hgt": "first",
    "unw": "first",
    "msk.unw": "first",
}


def plot_raster(
    input_file: str | Path,
    band: int = 1,
    wrap: str | None = None,
    colormap: str = "rainbow",
    datamin: float | None = None,
    datamax: float | None = None,
    title: str | None = None,
    aspect=1,
    background=None,
    interpolation: str = "nearest",
    nodata=None,
    draw_colorbar: bool = True,
    colorbar_orientation: str = "horizontal",
    amplitude_scale: str = "auto",
):
    """Plot a GDAL-readable raster.

    Parameters
    ----------
    input_file : str or Path
        GDAL-readable raster path, including ISCE ``.vrt`` sidecars.
    band : int, default 1
        One-based GDAL raster band.
    amplitude_scale : {"auto", "linear", "log", "db"}, default "auto"
        ``auto`` applies ``log10`` to amplitude bands detected from common ISCE
        product names.  ``db`` applies ``20 * log10(abs(value))``.
    """
    import os
    import warnings

    import matplotlib.pyplot as plt
    import numpy as np
    from osgeo import gdal

    warnings.filterwarnings("ignore", category=RuntimeWarning)

    input_file = Path(input_file).resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    ds = gdal.Open(str(input_file), gdal.GA_ReadOnly)
    if ds is None:
        raise ValueError(f"GDAL could not open raster: {input_file}")

    data = ds.GetRasterBand(band).ReadAsArray()
    transform = ds.GetGeoTransform()
    ds = None

    data = np.asarray(data)

    if nodata is not None:
        try:
            data = data.astype(np.float32, copy=False)
            data[data == nodata] = np.nan
        except Exception:
            pass

    if background is None:
        try:
            data = data.astype(np.float32, copy=False)
            data[data == 0] = np.nan
        except Exception:
            pass

    data, applied_scale = prepare_plot_values(
        data,
        input_file=input_file,
        band=band,
        amplitude_scale=amplitude_scale,
    )

    xmin, xmax, ymin, ymax = _extent_from_transform(transform, data.shape)

    if wrap == "wrap":
        data = np.subtract(np.mod(data, 2 * np.pi), np.pi)

    if title is None:
        title = os.path.basename(input_file)
    if applied_scale in {"log", "db"}:
        title = f"{title} ({applied_scale} amplitude)"

    fig = plt.figure(figsize=(4, 8), dpi=80)
    ax = fig.add_subplot(111)
    cax = ax.imshow(
        data,
        vmin=datamin,
        vmax=datamax,
        cmap=colormap,
        extent=[xmin, xmax, ymin, ymax],
        interpolation=interpolation,
    )
    ax.set_title(title)
    if draw_colorbar:
        fig.colorbar(cax, orientation=colorbar_orientation, shrink=0.75)
    ax.set_aspect(aspect)
    plt.show()


def plotdata(
    GDALfilename,
    band,
    wrap,
    colormap,
    datamin,
    datamax,
    title,
    aspect=1,
    background=None,
    interpolation="nearest",
    nodata=None,
    draw_colorbar=True,
    colorbar_orientation="horizontal",
    amplitude_scale="auto",
):
    """Compatibility wrapper for the external ``plotdata.py`` function."""
    return plot_raster(
        input_file=GDALfilename,
        band=band,
        wrap=wrap,
        colormap=colormap,
        datamin=datamin,
        datamax=datamax,
        title=title,
        aspect=aspect,
        background=background,
        interpolation=interpolation,
        nodata=nodata,
        draw_colorbar=draw_colorbar,
        colorbar_orientation=colorbar_orientation,
        amplitude_scale=amplitude_scale,
    )


def plotcomplexdata(
    GDALfilename,
    display,
    datamin,
    datamax,
    title,
    aspect=1,
    interpolation="nearest",
    draw_colorbar=True,
    colorbar_orientation="horizontal",
):
    """Plot complex data amplitude or phase using the original calling style."""
    import matplotlib.pyplot as plt
    import numpy as np
    from osgeo import gdal

    input_file = Path(GDALfilename).resolve()
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    ds = gdal.Open(str(input_file), gdal.GA_ReadOnly)
    if ds is None:
        raise ValueError(f"GDAL could not open raster: {input_file}")

    slc = ds.GetRasterBand(1).ReadAsArray()
    transform = ds.GetGeoTransform()
    ds = None

    try:
        slc[slc == 0] = np.nan
    except Exception:
        pass

    xmin, xmax, ymin, ymax = _extent_from_transform(transform, slc.shape)

    fig = plt.figure(figsize=(12, 12), dpi=80)
    if display == "amp":
        ax = fig.add_subplot(111)
        amp = np.absolute(slc)
        amp[amp <= 0] = np.nan
        values = 20.0 * np.log10(amp)
        cax = ax.imshow(
            values,
            cmap="gray",
            vmin=datamin,
            vmax=datamax,
            extent=[xmin, xmax, ymin, ymax],
            interpolation=interpolation,
        )
        ax.set_title(title + " amplitude [dB]")
    elif display == "phs":
        ax = fig.add_subplot(111)
        cax = ax.imshow(
            np.angle(slc),
            cmap="rainbow",
            vmin=-np.pi if datamin is None else datamin,
            vmax=np.pi if datamax is None else datamax,
            extent=[xmin, xmax, ymin, ymax],
            interpolation=interpolation,
        )
        ax.set_title(title + " phase [rad]")
    else:
        raise ValueError('display must be "amp" or "phs"')

    if draw_colorbar:
        fig.colorbar(cax, orientation=colorbar_orientation, shrink=0.5)
    ax.set_aspect(aspect)
    plt.show()


def prepare_plot_values(
    data,
    *,
    input_file: str | Path,
    band: int,
    amplitude_scale: str = "auto",
):
    """Apply optional amplitude scaling and return ``(values, applied_scale)``."""
    import numpy as np

    valid = {"auto", "linear", "log", "db"}
    if amplitude_scale not in valid:
        raise ValueError(f"amplitude_scale must be one of {sorted(valid)}")

    should_scale = (
        is_isce_amplitude_band(input_file, band)
        if amplitude_scale == "auto"
        else amplitude_scale in {"log", "db"}
    )
    if not should_scale:
        return data, "linear"

    values = np.asarray(data, dtype=np.float32)
    values = np.abs(values)
    values = np.where(values > 0, values, np.nan)

    if amplitude_scale == "db":
        return 20.0 * np.log10(values), "db"
    return np.log10(values), "log"


def is_isce_amplitude_band(input_file: str | Path, band: int) -> bool:
    """Return True when ``band`` is an amplitude band for common ISCE products.

    ``band`` follows GDAL's one-based indexing.
    """
    product = infer_isce_product_kind(input_file)
    rule = AMPLITUDE_PRODUCT_RULES.get(product)
    if rule == "all":
        return True
    if rule == "first":
        return int(band) == 1
    return False


def infer_isce_product_kind(input_file: str | Path) -> str | None:
    """Infer common ISCE product kind from a path."""
    name = Path(input_file).name.lower()
    for suffix in (".vrt", ".xml"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]

    if name.endswith(".geo"):
        name = name[: -len(".geo")]

    if name.endswith("msk.unw"):
        return "msk.unw"

    for product in ("amp", "cor", "hgt", "unw"):
        if name.endswith(f".{product}") or name.endswith(product):
            return product

    return None


def _extent_from_transform(transform, shape):
    import numpy as np

    firstx = transform[0]
    firsty = transform[3]
    deltay = transform[5]
    deltax = transform[1]
    lastx = firstx + shape[1] * deltax
    lasty = firsty + shape[0] * deltay
    ymin = np.min([lasty, firsty])
    ymax = np.max([lasty, firsty])
    xmin = np.min([lastx, firstx])
    xmax = np.max([lastx, firstx])
    return xmin, xmax, ymin, ymax
