# iscewrap

Lightweight Python wrappers for ISCE/ISCE2 workflows.

## Current features

- Create `alos2App.py` XML files
- Detect ALOS-2 product metadata from `IMG-*` filenames
- Organize ALOS-2 stripmap ZIP products into processable date folders
- Set standard multilook parameters from ALOS-2 acquisition mode
- Run `alos2App.py` with optional `--steps`, `--start`, and `--end`
- Process one reference/secondary ALOS-2 pair from ZIP files or extracted folders

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
