# iscewrap Usage

This is a quick reference for the current ALOS-2, ALOS-4, and `.geo` utilities.

## Installation

From the repository root:

```bash
pip install .
```

After installation, the command line tools include:

```bash
iscewrap-alos2
iscewrap-alos4
alos4app.py
iscewrap-alos4app
iscewrap-geocode
iscewrap-geocode-latlon
iscewrap-geo-to-kml
iscewrap-plot-real
iscewrap-plot-complex
```

## Detect and Process ALOS Pairs

The high-level front door is `process_alos_pair()`.  It detects the product
family and chooses the current supported workflow.

```python
from iscewrap import process_alos_pair

result = process_alos_pair(
    reference_input="/path/to/reference",
    secondary_input="/path/to/secondary",
    work_dir="/path/to/work",
    run=True,
    end_step="geocode",
)

print(result["workflow"])
print(result["xml_file"])
print(result["run_dir"])
```

Current routing:

- ALOS-2 + ALOS-2 -> full ALOS-2 workflow.
- ALOS-4 UWD + ALOS-4 UWD -> native ALOS-4 backend over ISCE2 `Alos2Proc`.
- Mixed ALOS-2/ALOS-4 -> rejected for now.
- ALOS-4 non-UWD -> rejected for now.

CLI:

```bash
alos4app.py REF_DIR SEC_DIR WORK_DIR --end-step geocode
```

Detection only:

```bash
alos4app.py REF_DIR SEC_DIR WORK_DIR --detect-only
```

## Process ALOS-4 UWD Pairs

Python:

```python
from iscewrap.alos4 import process_alos4_pair

result = process_alos4_pair(
    reference_input="/path/to/organized/path_125/RU1_08/20250728",
    secondary_input="/path/to/organized/path_125/RU1_08/20250809",
    work_dir="/path/to/alos4_work",
    run=True,
    end_step="geocode",
)
```

CLI:

```bash
iscewrap-alos4 REF_DIR SEC_DIR WORK_DIR --end-step geocode
```

Useful options:

```bash
iscewrap-alos4 REF_DIR SEC_DIR WORK_DIR \
  --start-step preprocess \
  --end-step baseline \
  --polarization HH \
  --range-sampling-rate 98=98242186.875
```

Native backend is the default.  To force the older visible symlink staging:

```bash
iscewrap-alos4 REF_DIR SEC_DIR WORK_DIR \
  --backend compat \
  --alos2-compat-mode FBD
```

Python equivalent:

```python
process_alos4_pair(
    reference_input=ref,
    secondary_input=sec,
    work_dir=work,
    backend="compat",
    alos2_compat_mode="FBD",
)
```

## Process ALOS-2 Pairs

Python:

```python
from iscewrap.alos2 import process_alos2_pair

result = process_alos2_pair(
    reference_input="/path/to/alos2_reference",
    secondary_input="/path/to/alos2_secondary",
    work_dir="/path/to/alos2_work",
    run=True,
    end_step="geocode",
)
```

CLI:

```bash
iscewrap-alos2 REF_DIR SEC_DIR WORK_DIR --end-step geocode
```

## Organize ALOS-4 ZIPs

Python:

```python
from iscewrap.alos4 import organize_alos4_stripmap_zips

groups = organize_alos4_stripmap_zips(
    zip_dir="/path/to/zips",
    output_dir="/path/to/organized",
    polarizations=["HH"],
)
```

CLI example script:

```bash
python examples/organize_alos4_stripmap.py
```

The organizer groups products like:

```text
organized/path_125/RU1_08/20250728/
```

## Native ISCE2 Geocode

`iscewrap-geocode` geocodes one raster with the same ISCE2 `geozero` pipeline
that `alos2App.py` uses, without running the whole application step.  This is
the default geocoding command to use for ALOS products when you want outputs on
the native ISCE2 grid.

Range and azimuth looks are inferred from names like `*_8rlks_16alks.unw`, but
can be overridden.

```bash
iscewrap-geocode filt_250728-250811_8rlks_16alks.unw \
  --track ../250728.track.xml \
  --dem /path/to/dem.dem.wgs84 \
  --bbox 35.75 36.475 139.47083333333333 140.3325
```

Optional overrides:

```bash
iscewrap-geocode filt_250728-250811_8rlks_16alks.unw \
  --track ../250728.track.xml \
  --dem /path/to/dem.dem.wgs84 \
  --grid-reference filt_250728-250811_8rlks_16alks_msk.unw.geo \
  --output custom_name.unw.geo \
  --interp bilinear
```

Use `--grid-reference` when you want exact alignment with an existing native
ISCE2 geocoded product. It reads that product's VRT/XML extent and uses the
same south/north/west/east geocode bbox.

## Lat/Lon Array Geocode

This helper converts a radar-coordinate raster using ISCE latitude/longitude
rasters and writes a geocoded raw raster with `.xml` and `.vrt` sidecars.

```python
from iscewrap.alos2 import geocode_raster

result = geocode_raster(
    input_file="height_from_phase.dem",
    lat_file="run/201127-210122_8rlks_16alks.lat",
    lon_file="run/201127-210122_8rlks_16alks.lon",
    output_file="height_from_phase.geo",
    resolution=1 / 3600,
    method="nearest",
)
```

CLI:

```bash
iscewrap-geocode-latlon height_from_phase.dem \
  run/201127-210122_8rlks_16alks.lat \
  run/201127-210122_8rlks_16alks.lon \
  height_from_phase.geo \
  --resolution 0.0002777777777777778 \
  --method nearest
```

`nearest` is the default because it is much faster for dense ISCE latitude and
longitude grids.  Use `--method linear` only for smaller rasters or when you can
afford the extra interpolation cost.

Nearest-neighbor interpolation can otherwise smear the nearest valid radar
sample into pixels just outside the real swath footprint.  The geocoder masks
outside the source footprint by default so those edge pixels become nodata.
Disable this only for debugging:

```bash
iscewrap-geocode-latlon input.rdr ref.lat ref.lon output.geo --no-edge-mask
```

Multi-band rasters are handled band-by-band.  If `input_file` has two real
bands, for example magnitude/coherence or magnitude/unwrapped phase, omitting
`--band` geocodes both bands and writes a two-band BSQ `.geo` product:

```bash
iscewrap-geocode-latlon filt_fine.unw ref.lat ref.lon filt_fine.unw.geo
```

To geocode only one band, pass a zero-based band index.  Band `1` is commonly
the unwrapped phase band in ISCE `.unw` files:

```bash
iscewrap-geocode-latlon filt_fine.unw ref.lat ref.lon filt_fine_phase.geo \
  --band 1
```

Complex rasters are preserved as complex `CFLOAT` output.  The geocoder does not
split a complex sample into two real bands; amplitude and phase should be formed
from the complex geocoded raster afterward, or rendered directly with
`iscewrap-geo-to-kml --value-mode magnitude` / `--value-mode phase`.

Progress messages are printed by default.  Add `--quiet` to suppress them:

```bash
iscewrap-geocode-latlon height_from_phase.dem ref.lat ref.lon height_from_phase.geo \
  --quiet
```

## Convert `.geo` Products to KML/KMZ

Use this after ISCE geocoding creates products such as:

```text
*.int.geo
*.unw.geo
*.cor.geo
```

Python:

```python
from iscewrap import geo_to_kml

result = geo_to_kml(
    input_file="run/insar/filt_fine.unw.geo",
    output_file="run/insar/filt_fine.unw.geo.kmz",
    band=1,
    value_mode="real",
)
```

CLI:

```bash
iscewrap-geo-to-kml run/insar/filt_fine.unw.geo \
  run/insar/filt_fine.unw.geo.kmz \
  --band 1 \
  --value-mode real
```

Two-band products are common:

- band `0`: usually magnitude/amplitude
- band `1`: often coherence or unwrapped phase, depending on product

Examples:

```bash
# Band 0 magnitude/amplitude
iscewrap-geo-to-kml run/insar/filt_fine.unw.geo amplitude.kmz \
  --band 0 \
  --value-mode real

# Band 1 unwrapped values
iscewrap-geo-to-kml run/insar/filt_fine.unw.geo unwrapped.kmz \
  --band 1 \
  --value-mode real

# Band 1 coherence-like product
iscewrap-geo-to-kml run/insar/phsig.cor.geo coherence.kmz \
  --band 1 \
  --value-mode real \
  --cmap viridis

# Complex/wrapped phase product
iscewrap-geo-to-kml run/insar/diff_int.geo phase.kmz \
  --band 0 \
  --value-mode phase \
  --cmap hsv
```

Rendering options:

```bash
iscewrap-geo-to-kml INPUT.geo OUTPUT.kmz \
  --band 1 \
  --value-mode real \
  --cmap plasma \
  --alpha 0.8 \
  --percentile-clip 1 99
```

Available `value_mode` choices:

- `auto`: phase for complex rasters, real values otherwise
- `real`: real values
- `imag`: imaginary values
- `magnitude`: absolute value
- `phase`: phase angle for complex rasters, or raw values for real rasters

## Plot ISCE Rasters

The package includes the plotting helpers from your external `plotdata.py` and
`plotcomplexdata.py` scripts:

```python
from iscewrap import plotdata, plotcomplexdata

plotdata("filt_fine.unw.geo.vrt", 1, None, "rainbow", None, None, "amplitude")
plotcomplexdata("diff_int.geo.vrt", "phs", None, None, "wrapped phase")
```

For real rasters, `plotdata()` automatically applies `log10` scaling when the
selected band is an amplitude band for common ISCE products:

- `*.amp`, `*.amp.geo`: both bands are amplitude
- `*.cor`, `*.cor.geo`: band 1 is amplitude, band 2 is coherence
- `*.unw`, `*.unw.geo`: band 1 is amplitude, band 2 is unwrapped phase
- `*.msk.unw`, `*.msk.unw.geo`: band 1 is masked amplitude, band 2 is masked unwrapped phase

`*.hgt` and `*.hgt.geo` products are single-band real height rasters and stay
linear by default.

CLI:

```bash
iscewrap-plot-real filt_fine.unw.geo.vrt
iscewrap-plot-real filt_fine.unw.geo.vrt --band 2 --cmap rainbow
iscewrap-plot-real filt_fine.unw.geo.vrt --band 1 --amplitude-scale linear
iscewrap-plot-real filt_fine.unw.geo.vrt --wrap --vmin -3.14 --vmax 3.14
iscewrap-plot-real filt_fine.unw.geo.vrt --title "masked amplitude"

iscewrap-plot-complex diff_int.geo.vrt --display phs
iscewrap-plot-complex diff_int.geo.vrt --display amp
```

`--amplitude-scale auto` is the default for `iscewrap-plot-real`. Use
`--amplitude-scale linear` to disable automatic amplitude log scaling, or
`--amplitude-scale db` to display amplitude in dB.

## DEM Preparation

When DEM/WBD paths are omitted, the ALOS workflows can run to `baseline`, parse
the bounding box, prepare SRTM/WBD files, regenerate XML with DEM paths, and
resume processing.

Explicit DEM inputs:

```python
process_alos_pair(
    reference_input=ref,
    secondary_input=sec,
    work_dir=work,
    dem_coreg="/path/to/dem.dem.wgs84",
    dem_geocode="/path/to/dem.dem.wgs84",
    water_body="/path/to/waterBody.rdr",
)
```

## Common Result Fields

Most processing functions return a dictionary containing:

```python
result["pair_name"]
result["xml_file"]
result["run_dir"]
result["reference_info"]
result["secondary_info"]
result["dem_result"]
result["stdout"]
result["stderr"]
```

ALOS-4 results also include:

```python
result["backend"]
result["range_sampling_rates"]
result["stage_compat_names"]
result["reference_summary"]
result["secondary_summary"]
```
