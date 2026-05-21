"""Utilities for geographic ISCE rasters."""

from __future__ import annotations

from pathlib import Path
import zipfile


def geo_to_kml(
    input_file: str | Path,
    output_file: str | Path | None = None,
    *,
    output_png: str | Path | None = None,
    band: int | None = None,
    value_mode: str = "auto",
    cmap: str | None = None,
    alpha: float = 0.75,
    percentile_clip: tuple[float, float] | None = (2.0, 98.0),
    vmin: float | None = None,
    vmax: float | None = None,
    name: str | None = None,
    colorbar: bool = False,
) -> dict:
    """Convert a geocoded ISCE ``.geo`` raster to a KML/KMZ image overlay.

    The function reads the raw ISCE raster and its ``.xml``/``.vrt`` sidecars,
    renders a PNG, and writes a KML ``GroundOverlay`` using the product's
    geographic extent.  If ``output_file`` ends in ``.kmz``, the KML and PNG are
    packaged into one KMZ archive.
    """
    import numpy as np

    from .alos2.workflow import read_isce_raster, read_isce_raster_metadata

    input_file = Path(input_file).resolve()
    if output_file is None:
        output_file = input_file.with_suffix(input_file.suffix + ".kml")
    output_file = Path(output_file).resolve()

    if output_png is None:
        png_name = input_file.name + ".png"
        output_png = output_file.with_name(png_name)
    output_png = Path(output_png).resolve()

    meta = read_isce_raster_metadata(input_file)
    data = read_isce_raster(input_file, band=band, metadata=meta)
    if data.ndim == 3:
        data = data[0]

    image_values, render_mode = _prepare_render_values(data, value_mode=value_mode)
    extent = read_geo_extent(input_file)

    if cmap is None:
        cmap = "hsv" if render_mode == "phase" else "viridis"

    png_file = render_geo_png(
        image_values,
        output_png,
        cmap=cmap,
        alpha=alpha,
        percentile_clip=percentile_clip,
        vmin=vmin,
        vmax=vmax,
        phase=render_mode == "phase",
        colorbar=colorbar,
    )

    overlay_name = name or input_file.name
    if output_file.suffix.lower() == ".kmz":
        kml_text = _kml_text(
            name=overlay_name,
            href=png_file.name,
            extent=extent,
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doc.kml", kml_text)
            zf.write(png_file, arcname=png_file.name)
        kml_file = output_file
    else:
        kml_file = write_ground_overlay_kml(
            output_file,
            image_href=png_file.name,
            extent=extent,
            name=overlay_name,
        )

    return {
        "input_file": input_file,
        "kml_file": kml_file,
        "png_file": png_file,
        "extent": extent,
        "value_mode": render_mode,
        "cmap": cmap,
    }


def read_geo_extent(raster_file: str | Path) -> dict[str, float]:
    """Read geographic extent from a geocoded ISCE raster sidecar."""
    raster_file = Path(raster_file).resolve()
    vrt_file = Path(str(raster_file) + ".vrt")
    xml_file = Path(str(raster_file) + ".xml")

    if vrt_file.exists():
        extent = _read_extent_from_vrt(vrt_file)
        if extent is not None:
            return extent

    if xml_file.exists():
        extent = _read_extent_from_xml(xml_file)
        if extent is not None:
            return extent

    raise ValueError(
        "Could not read geographic extent. Expected GeoTransform in "
        f"{vrt_file} or coordinate components in {xml_file}."
    )


def render_geo_png(
    array,
    output_png: str | Path,
    *,
    cmap: str = "viridis",
    alpha: float = 0.75,
    percentile_clip: tuple[float, float] | None = (2.0, 98.0),
    vmin: float | None = None,
    vmax: float | None = None,
    phase: bool = False,
    colorbar: bool = False,
) -> Path:
    """Render a 2D numeric array to a transparent PNG."""
    import os
    import tempfile

    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "iscewrap-mpl"),
    )

    import matplotlib.cm as cm
    import matplotlib.image as mpimg
    import numpy as np

    output_png = Path(output_png).resolve()
    output_png.parent.mkdir(parents=True, exist_ok=True)

    values = np.asarray(array, dtype=np.float32)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError("Cannot render PNG because raster has no finite pixels.")

    if phase and vmin is None and vmax is None:
        vmin, vmax = -np.pi, np.pi
    elif vmin is None or vmax is None:
        if percentile_clip is None:
            low = float(np.nanmin(values[finite]))
            high = float(np.nanmax(values[finite]))
        else:
            low, high = np.nanpercentile(values[finite], percentile_clip)
        if vmin is None:
            vmin = float(low)
        if vmax is None:
            vmax = float(high)

    if vmax == vmin:
        vmax = vmin + 1.0

    normalized = np.clip((values - vmin) / (vmax - vmin), 0.0, 1.0)
    rgba = cm.get_cmap(cmap)(normalized)
    rgba[..., 3] = np.where(finite, float(alpha), 0.0)

    if colorbar:
        _render_png_with_colorbar(rgba, output_png, cmap=cmap, vmin=vmin, vmax=vmax)
    else:
        mpimg.imsave(output_png, rgba)

    return output_png


def write_ground_overlay_kml(
    output_kml: str | Path,
    *,
    image_href: str,
    extent: dict[str, float],
    name: str,
) -> Path:
    """Write a KML GroundOverlay document."""
    output_kml = Path(output_kml).resolve()
    output_kml.parent.mkdir(parents=True, exist_ok=True)
    output_kml.write_text(
        _kml_text(name=name, href=image_href, extent=extent),
        encoding="utf-8",
    )
    return output_kml


def _prepare_render_values(data, *, value_mode: str):
    import numpy as np

    valid_modes = {"auto", "real", "imag", "magnitude", "phase"}
    if value_mode not in valid_modes:
        raise ValueError(f"value_mode must be one of {sorted(valid_modes)}")

    is_complex = np.iscomplexobj(data)
    mode = "phase" if value_mode == "auto" and is_complex else value_mode
    if mode == "auto":
        mode = "real"

    if mode == "real":
        return np.real(data), mode
    if mode == "imag":
        return np.imag(data), mode
    if mode == "magnitude":
        return np.abs(data), mode
    if mode == "phase":
        return np.angle(data) if is_complex else np.asarray(data), mode

    raise AssertionError(f"Unhandled value_mode: {mode}")


def _read_extent_from_vrt(vrt_file: Path) -> dict[str, float] | None:
    import xml.etree.ElementTree as ET

    root = ET.parse(vrt_file).getroot()
    geo = root.findtext("GeoTransform")
    if geo is None:
        return None

    values = [float(value.strip()) for value in geo.split(",")]
    if len(values) != 6:
        return None

    origin_x, pixel_width, rot_x, origin_y, rot_y, pixel_height = values
    if rot_x != 0.0 or rot_y != 0.0:
        raise ValueError(f"Rotated GeoTransform is not supported: {vrt_file}")

    width = int(root.attrib["rasterXSize"])
    length = int(root.attrib["rasterYSize"])
    west = origin_x
    east = origin_x + pixel_width * width
    north = origin_y
    south = origin_y + pixel_height * length
    return _ordered_extent(west=west, east=east, south=south, north=north)


def _read_extent_from_xml(xml_file: Path) -> dict[str, float] | None:
    import xml.etree.ElementTree as ET

    root = ET.parse(xml_file).getroot()
    coord1 = _component_by_name(root, "coordinate1")
    coord2 = _component_by_name(root, "coordinate2")
    if coord1 is None or coord2 is None:
        return None

    x0 = _component_property_float(coord1, "startingvalue")
    x1 = _component_property_float(coord1, "endingvalue")
    y0 = _component_property_float(coord2, "startingvalue")
    y1 = _component_property_float(coord2, "endingvalue")
    if None in {x0, x1, y0, y1}:
        return None

    return _ordered_extent(west=x0, east=x1, south=y1, north=y0)


def _component_by_name(root, name: str):
    for component in root.findall("component"):
        if component.attrib.get("name") == name:
            return component
    return None


def _component_property_float(component, name: str) -> float | None:
    for prop in component.findall("property"):
        if prop.attrib.get("name") == name:
            value = prop.findtext("value")
            return None if value is None else float(value)
    return None


def _ordered_extent(*, west: float, east: float, south: float, north: float) -> dict[str, float]:
    return {
        "west": min(float(west), float(east)),
        "east": max(float(west), float(east)),
        "south": min(float(south), float(north)),
        "north": max(float(south), float(north)),
    }


def _kml_text(*, name: str, href: str, extent: dict[str, float]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{_escape_xml(name)}</name>
    <GroundOverlay>
      <name>{_escape_xml(name)}</name>
      <Icon>
        <href>{_escape_xml(href)}</href>
      </Icon>
      <LatLonBox>
        <north>{extent["north"]}</north>
        <south>{extent["south"]}</south>
        <east>{extent["east"]}</east>
        <west>{extent["west"]}</west>
      </LatLonBox>
    </GroundOverlay>
  </Document>
</kml>
"""


def _escape_xml(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_png_with_colorbar(rgba, output_png: Path, *, cmap: str, vmin: float, vmax: float) -> None:
    import os
    import tempfile

    os.environ.setdefault(
        "MPLCONFIGDIR",
        str(Path(tempfile.gettempdir()) / "iscewrap-mpl"),
    )

    import matplotlib.pyplot as plt
    import matplotlib as mpl

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    ax.imshow(rgba)
    ax.set_axis_off()
    norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
    fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=cmap), ax=ax, fraction=0.035)
    fig.savefig(output_png, transparent=True, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
