# iscewrap

A lightweight Python wrapper for running and modifying ISCE/ISCE2 workflows, with an initial focus on `alos2App.py`.

`iscewrap` is designed to make ISCE processing more reproducible by:

- editing ISCE XML parameters programmatically,
- running selected workflow steps,
- keeping a simple command-line interface,
- logging commands and outputs,
- optionally saving ISCE processing objects/pickles when supported by the workflow,
- providing reusable utilities for ALOS-2 processing.

> This repository is an initial template. It is intentionally minimal so it can be extended around your existing ISCE workflows.

---

## Installation

From the repository root:

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

---

## Basic usage

### Run an ALOS-2 step

```bash
iscewrap-alos2 run xml/alos2App.xml --start filt
```

### Run a range of steps

```bash
iscewrap-alos2 run xml/alos2App.xml --start preprocess --end geocode
```

### Add geocode file list

```bash
iscewrap-alos2 run xml/alos2App.xml \
  --start geocode \
  --geocode-file-list "diff*.int" "filt*.int*"
```

This creates a temporary XML file with:

```xml
<property name="geocode file list">["diff*.int", "filt*.int*"]</property>
```

and runs ISCE with that modified XML.

### Write modified XML without running

```bash
iscewrap-alos2 edit-xml xml/alos2App.xml modified_alos2App.xml \
  --geocode-file-list "diff*.int" "filt*.int*"
```

---

## Python usage

```python
from iscewrap.alos2 import run_alos2

result = run_alos2(
    xml_file="xml/alos2App.xml",
    start="filt",
    end=None,
    geocode_file_list=["diff*.int", "filt*.int*"],
    workdir="run",
)
print(result.returncode)
```

---

## Project layout

```text
iscewrap/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── examples/
│   └── alos2_config.yaml
├── src/
│   └── iscewrap/
│       ├── __init__.py
│       ├── alos2.py
│       ├── cli.py
│       ├── runner.py
│       └── xml_utils.py
└── tests/
    └── test_xml_utils.py
```

---

## Notes

This wrapper assumes that ISCE/ISCE2 is already installed and that commands such as `alos2App.py` are available in your active shell environment.

For example:

```bash
conda activate isce264
which alos2App.py
```

If `alos2App.py` is not found, activate the correct ISCE environment before running `iscewrap`.

---

## License

MIT
