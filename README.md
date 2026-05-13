# iscewrap

Lightweight Python wrappers for ISCE/ISCE2 workflows.

## Current features

- Create `alos2App.py` XML files
- Detect ALOS-2 product metadata from `IMG-*` filenames
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
