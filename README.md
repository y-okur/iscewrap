# iscewrap

Lightweight Python wrappers for ISCE/ISCE2 workflows.

## Current features

- Create `alos2App.py` XML files
- Detect ALOS-2 product metadata from `IMG-*` filenames
- Organize ALOS-2 stripmap ZIP products into processable date folders
- Organize ALOS-4 stripmap ZIP products into processable date folders
- Set standard multilook parameters from ALOS-2 acquisition mode
- Run `alos2App.py` with optional `--steps`, `--start`, and `--end`
- Process one reference/secondary ALOS-2 pair from ZIP files or extracted folders
- Process prototype ALOS-4 UWD-UWD pairs through the native ALOS-4 backend
- Convert geocoded ISCE `.geo` rasters to KML/KMZ overlays

## Documentation

- [Usage guide](docs/usage.md)
- [ALOS-4 correction log](docs/alos4_corrections.md)

## Installation

```bash
pip install -e .
```

## Example

```python
from iscewrap.alos2 import process_alos2_pair

result = process_alos2_pair(
    reference_input="ALOS2_reference.zip",
    secondary_input="ALOS2_secondary.zip",
    work_dir="isce_work",
    dem_coreg="/path/to/dem/",
    dem_geocode="/path/to/dem",
    water_body="/path/to/wbd",
    use_gpu=False,
    start_step="preprocess",
    end_step="geocode",
    geocode_file_list=["diff*int", "filt*int*"],
)
```

## Organize ALOS-2 stripmap products

```python
from iscewrap.alos2 import organize_alos2_stripmap_zips

groups = organize_alos2_stripmap_zips(
    zip_files="/path/to/alos2_zips",
    output_dir="/path/to/organized",
    polarizations=["HH"],  # optional; omit to extract all polarizations
)

reference_dir = groups["path_24/RF2_6"]["dates"]["20160326"]["date_dir"]
secondary_dir = groups["path_24/RF2_6"]["dates"]["20160604"]["date_dir"]
```

The organizer expects ZIP names such as `24-3390-RF2_6-20160326_+2.zip`.
Products with the same path, acquisition mode, beam/off-nadir, and date are
extracted together as:

```text
organized/
  path_24/
    RF2_6/
      20160326/
      20160604/
```

## Organize ALOS-4 stripmap products

```python
from iscewrap.alos4 import organize_alos4_stripmap_zips, parse_alos4_summary

groups = organize_alos4_stripmap_zips(
    zip_files="/path/to/alos4_zips",
    output_dir="/path/to/organized",
    polarizations=["HH"],  # optional; omit to extract all polarizations
)

reference_dir = groups["path_125/RU1_08"]["dates"]["20250728"]["date_dir"]
```

The organizer expects ZIP names such as `125-710-RU1_08_F-20250728.zip`.
Products with the same path, acquisition mode, beam/off-nadir, and date are
extracted together as:

```text
organized/
  path_125/
    RU1_08/
      20250728/
```

Summary files can also be parsed directly:

```python
summary = parse_alos4_summary("summary-ALOS41250710250728UWDPRA0108-1.1__-.txt")
print(summary["Scs_ObsMode"])
print(summary["Img_OffNadirAngle"])
```

## Process an ALOS-4 pair

```python
from iscewrap.alos4 import process_alos4_pair

result = process_alos4_pair(
    reference_input="/path/to/organized/path_125/RU1_08/20250728",
    secondary_input="/path/to/organized/path_125/RU1_08/20250809",
    work_dir="alos4_isce_work",
    dem_coreg="/path/to/dem.dem.wgs84",
    dem_geocode="/path/to/dem.dem.wgs84",
    water_body="/path/to/waterBody.rdr",
    run=True,
    start_step="preprocess",
    end_step="geocode",
)
```

This wrapper creates an `alos2App.py`-compatible XML and runs ISCE2's existing
`Alos2Proc` workflow. The default `native` backend keeps the original ALOS-4
filenames and installs runtime hooks for ALOS-4 filename discovery, range
sampling constants, CEOS image layout, slant-range units, and blank pass
direction fields.

The earlier compatibility backend is still available as a fallback. It stages
temporary ALOS-2-style symlink names under `work_dir/alos2_compat/` for ISCE2
installations whose preprocessor cannot discover native ALOS-4 names:

```python
result = process_alos4_pair(
    reference_input=reference_dir,
    secondary_input=secondary_dir,
    work_dir="alos4_isce_work",
    backend="compat",
    alos2_compat_mode="FBS",
)
```

ALOS-4 products may expose range sampling codes that ISCE2's ALOS-2 reader does
not know. The wrapper currently patches UWD code `98` as `98_242_186.9` Hz at
runtime without editing your ISCE2 installation. Override it if your product
format documentation gives a more exact value:

```python
result = process_alos4_pair(
    reference_input=reference_dir,
    secondary_input=secondary_dir,
    work_dir="alos4_isce_work",
    range_sampling_rates={98: 98_304_000.0},
)
```

When DEM/WBD paths are not supplied, `process_alos4_pair()` follows the ALOS-2
fallback workflow: it first runs through `baseline`, parses the reference
bounding box, prepares DEM/WBD files from the ESA STEP SRTM mirror, regenerates
the XML with explicit DEM paths, and resumes at `prep_slc`. This avoids ISCE2's
native `download_dem` step and its old Earthdata URLs.

The same workflow is available from the command line:

```bash
iscewrap-alos4 reference_dir secondary_dir alos4_isce_work \
  --start-step preprocess \
  --end-step geocode \
  --range-sampling-rate 98=98242186.9
```

Use `--backend compat --alos2-compat-mode FBD` to force the older symlink
fallback.

## Prototype ALOS-4 app front door

```python
from iscewrap import process_alos_pair

result = process_alos_pair(
    reference_input=reference_dir,
    secondary_input=secondary_dir,
    work_dir="alos_isce_work",
    run=True,
    end_step="geocode",
)
```

`process_alos_pair()` detects both inputs. ALOS-2/ALOS-2 pairs are sent through
the existing full ALOS-2 workflow. ALOS-4/ALOS-4 pairs are currently accepted
only for UWD/UWD products and are routed through the native ALOS-4 backend.
Mixed ALOS-2/ALOS-4 pairs are intentionally rejected until that workflow is
tested.

The same prototype front door is available as:

```bash
alos4app.py reference_dir secondary_dir alos_isce_work --end-step geocode
```

## Convert `.geo` products to KML/KMZ

Geocoded ISCE rasters can be rendered as Google Earth overlays:

```python
from iscewrap import geo_to_kml

result = geo_to_kml(
    input_file="run/insar/filt_fine.int.geo",
    output_file="run/insar/filt_fine.int.geo.kmz",
    value_mode="phase",
)
```

The command line equivalent is:

```bash
iscewrap-geo-to-kml run/insar/filt_fine.int.geo run/insar/filt_fine.int.geo.kmz \
  --value-mode phase
```

Use `value_mode="magnitude"` for amplitude-like products, or leave
`value_mode="auto"` to use phase for complex rasters and real values otherwise.
