# ALOS-4 Processing Corrections

This note tracks the ALOS-4 compatibility corrections added while building the
UWD prototype.  The current design keeps ALOS-4 handling in `iscewrap` package
code while reusing ISCE2's mature `Alos2Proc` processing functions.

## Current Scope

- ALOS-2/ALOS-2 pairs: routed through the existing ALOS-2 workflow.
- ALOS-4/ALOS-4 pairs: UWD-UWD only for now.
- Mixed ALOS-2/ALOS-4 pairs: detected but intentionally rejected until tested.
- ScanSAR and non-UWD ALOS-4 modes: deferred.

## Native Backend Strategy

File: `src/iscewrap/alos4/backend.py`

ISCE2's `runPreprocessor.py` searches for `ALOS2*` filenames and parses frame,
date, and mode from those names.  A pure glob translation to native `ALOS4*`
filenames is therefore not enough.

The native backend keeps the user-facing reference/secondary inputs as ALOS-4
directories, then creates a hidden run-local alias cache:

```text
run/.alos4_native_alias/reference/
run/.alos4_native_alias/secondary/
```

Those aliases use ALOS-2-compatible filenames but point to the real ALOS-4 CEOS
files.  This lets ISCE2's existing filename parser and processing chain proceed
without creating the older visible `work_dir/alos2_compat/` staging tree.

The older visible compatibility staging remains available through:

```python
process_alos4_pair(..., backend="compat")
```

## Corrections

### ALOS-4 Filename Discovery

Problem:

ISCE2 hard-codes patterns such as:

```python
LED-ALOS2*-*-*
IMG-HH-ALOS2*-*-*
```

ALOS-4 products use names such as:

```text
IMG-HH-ALOS41250710250728UWDPRA0108-1.1__-
LED-ALOS41250710250728UWDPRA0108-1.1__-
```

Correction:

The native backend creates hidden symlink aliases with ALOS-2-compatible names:

```text
IMG-HH-ALOS21250710-250728-FBD
LED-ALOS21250710-250728-FBD
```

This preserves ISCE2's expected frame/date/mode parsing while leaving the input
product layout unchanged.

### Range Sampling Rate

Problem:

The ALOS-4 UWD sample reports a range sampling code of `98`, which is not in
ISCE2's ALOS-2 `fsampConst` table.

Correction:

The backend patches the table at runtime:

```python
98: 98_242_186.9
```

This value came from the first successful ALOS-4 UWD LED/header inspection:

```text
98.2421869 MHz
```

Override path:

```python
process_alos4_pair(
    ...,
    range_sampling_rates={98: 98_242_186.9},
)
```

CLI:

```bash
iscewrap-alos4 REF SEC WORK --range-sampling-rate 98=98242186.9
```

### CEOS Image Layout / VRT Offsets

Problem:

ISCE2's ALOS-2 reader assumes fixed CEOS image offsets:

```text
file header: 720 bytes
line header: 544 bytes
```

The ALOS-4 sample required dynamic offsets from the parsed CEOS image file
record.  Without this, the SLC VRT can be misaligned and visible banding/artifact
patterns appear in the extracted SLC.

Correction:

For ALOS-4 images, the backend parses:

- `SAR DATA record length`
- `Number of pixels per line per SAR channel`
- `Number of SAR DATA records`
- `imageFDR.getEndOfRecordPosition()`

Then it derives:

```python
line_header_bytes = record_length - width * 8
image_offset = file_header_bytes + line_header_bytes
line_offset = record_length
```

The generated VRT uses those dynamic values.

### Slant Range Unit Correction

Problem:

ISCE2 reads `Slant range to 1st data sample` from the CEOS image record and
expects meters.  In the ALOS-4 UWD sample, the value appeared to be read as
centimeters, making the range about 100x too large.

Original ISCE2 use:

```python
swath.startingRange = imageData.metadata["Slant range to 1st data sample"]
```

Correction:

Before calling ISCE2's original `setSwath()`, the backend checks:

```python
if starting_range > 10_000_000:
    starting_range = starting_range * 0.01
```

The threshold is a sanity check.  Real L-band SAR slant ranges for these
products should be around hundreds of thousands of meters, not tens of millions.

Why this matters:

- `startingRange` drives radar geometry.
- If it is 100x too large, orbit-to-ground conversion fails or produces invalid
  geometry.
- This can lead to NaNs during baseline and later processing steps.

### Blank Pass Direction

Problem:

ISCE2 expects `Time direction indicator along line direction` to be `ASCEND` or
`DESCEND`.  The ALOS-4 sample had a blank value in the parsed scene header.

Correction:

The backend infers pass direction from the middle orbit state vector velocity:

```python
velocity_z > 0 -> ASCEND
velocity_z < 0 -> DESCEND
```

Then ISCE2's original `setTrack()` receives the filled metadata value.

### Baseline Debug Logging

Problem:

When geometry failed, the original logs did not show enough context to diagnose
whether range, orbit, or geolocation was wrong.

Correction:

The backend prints an ALOS-4 baseline debug line with:

- mid-range
- mid-sensing time
- orbit-derived LLH
- number of reference/secondary orbit vectors

This is diagnostic only; it does not change processing results.

## Known Open Items

- Confirm ALOS-4 FWD sampling defaults.  A known FWD sample produced code `32`
  and LED-derived sampling near `32.7473956 MHz`, but FWD is not enabled yet.
- Move from runtime hooks toward a true `alos4App.py` application class once the
  UWD workflow is stable.
- Test ALOS-2/ALOS-4 mixed pairs only after same-orbit handling is verified.
- Add ScanSAR-specific logic separately; current stripmap assumptions should not
  be stretched into ScanSAR.

