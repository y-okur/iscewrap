"""ALOS-2 product extraction and metadata parsing utilities."""

from __future__ import annotations

from pathlib import Path
import re
import zipfile

from .constants import ALOS2_LOOK_TABLE


def extract_alos2_zip(zip_file: str | Path, output_dir: str | Path) -> Path:
    """Extract an ALOS-2 ZIP product into ``output_dir / zip_file.stem``.

    If the directory already exists, extraction is skipped.
    """
    zip_file = Path(zip_file).resolve()
    output_dir = Path(output_dir).resolve()
    extract_dir = output_dir / zip_file.stem

    if extract_dir.exists():
        print(f"Already extracted: {extract_dir}")
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {zip_file} -> {extract_dir}")
    with zipfile.ZipFile(zip_file, "r") as z:
        z.extractall(extract_dir)

    return extract_dir


def find_alos2_files(product_dir: str | Path) -> dict[str, list[Path]]:
    """Find standard ALOS-2 product files inside a product directory."""
    product_dir = Path(product_dir).resolve()

    files = {
        "IMG": sorted(product_dir.rglob("IMG-*")),
        "LED": sorted(product_dir.rglob("LED-*")),
        "TRL": sorted(product_dir.rglob("TRL-*")),
        "VOL": sorted(product_dir.rglob("VOL-*")),
    }

    if len(files["IMG"]) == 0:
        raise FileNotFoundError(f"No IMG-* file found in {product_dir}")

    return files


def parse_alos2_img_filename(img_file: str | Path) -> dict[str, str]:
    """Parse polarization, frame, date, and acquisition mode from an IMG filename."""
    img_file = Path(img_file)
    name = img_file.name

    pattern = (
        r"IMG-"
        r"(?P<pol>[A-Z]{2})-"
        r"ALOS2(?P<track_frame>\d+)-"
        r"(?P<date>\d{6})-"
        r"(?P<mode>[A-Z]{3})"
    )

    match = re.search(pattern, name)

    if match is None:
        raise ValueError(f"Could not parse ALOS-2 IMG filename: {name}")

    track_frame = match.group("track_frame")

    return {
        "polarization": match.group("pol"),
        "frame": track_frame[-4:],
        "date": match.group("date"),
        "mode": match.group("mode"),
        "full_name": name,
    }


def get_alos2_multilook_from_mode(mode: str) -> dict[str, int]:
    """Return ISCE2 multilook parameters for an ALOS-2 acquisition mode."""
    mode = mode.upper()

    if mode not in ALOS2_LOOK_TABLE:
        raise ValueError(
            f"Unsupported ALOS-2 acquisition mode: {mode}. "
            f"Known modes: {list(ALOS2_LOOK_TABLE.keys())}"
        )

    looks = ALOS2_LOOK_TABLE[mode]

    return {
        "number of range looks 1": looks["look1"][0],
        "number of azimuth looks 1": looks["look1"][1],
        "number of range looks 2": looks["look2"][0],
        "number of azimuth looks 2": looks["look2"][1],
        "number of range looks ion": looks["look_ion"][0],
        "number of azimuth looks ion": looks["look_ion"][1],
    }


def detect_product_metadata(product_dir: str | Path) -> dict:
    """Detect product root, first IMG file, parsed metadata, and multilook settings."""
    files = find_alos2_files(product_dir)

    img_file = files["IMG"][0]
    product_root = img_file.parent.resolve()

    img_info = parse_alos2_img_filename(img_file)
    multilook = get_alos2_multilook_from_mode(img_info["mode"])

    return {
        "product_root": product_root,
        "img_file": img_file,
        "img_info": img_info,
        "multilook": multilook,
        "files": files,
    }
