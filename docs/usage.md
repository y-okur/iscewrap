# iscewrap Usage

This is a quick reference for the current ALOS-2, ALOS-4, and `.geo` utilities.

## Installation

From the repository root:

```bash
pip install -e .
```

After installation, the command line tools include:

```bash
iscewrap-alos2
iscewrap-alos4
alos4app.py
iscewrap-alos4app
iscewrap-geo-to-kml
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
  --range-sampling-rate 98=98242186.9
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

## Geocode a Radar Raster

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
    method="linear",
)
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

