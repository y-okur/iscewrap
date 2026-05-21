"""ALOS-4 product extraction and metadata parsing utilities."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import zipfile

from .organize import parse_alos4_summary


ALOS4_IMG_PATTERN = re.compile(
    r"IMG-"
    r"(?P<polarization>[A-Z]{2})-"
    r"ALOS4"
    r"(?P<path>\d{3})"
    r"(?P<frame>\d{4})"
    r"(?P<date>\d{6})"
    r"(?P<obs_mode>[A-Z]{3})"
    r"PRA"
    r"(?P<beam_code>\d{4})",
    re.IGNORECASE,
)


VALID_POLARIZATIONS = {"HH", "HV", "VH", "VV"}


def extract_alos4_zip(
    zip_file: str | Path,
    output_dir: str | Path,
    *,
    polarizations: str | list[str] | tuple[str, ...] | set[str] | None = None,
) -> Path:
    """Extract an ALOS-4 ZIP product into ``output_dir / zip_file.stem``.

    ``polarizations`` filters polarization-specific files such as ``IMG-HH-*``
    and ``BRS-HV-*``. Shared CEOS/product metadata files are always extracted.
    """
    zip_file = Path(zip_file).resolve()
    output_dir = Path(output_dir).resolve()
    extract_dir = output_dir / zip_file.stem
    selected_polarizations = _normalize_polarizations(polarizations)

    if extract_dir.exists():
        print(f"Already extracted: {extract_dir}")
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting {zip_file} -> {extract_dir}")
    with zipfile.ZipFile(zip_file, "r") as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(
                    f"Unsafe ZIP member path in {zip_file}: {member.filename}"
                )

            target = extract_dir / member_path
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            if not _should_extract_member(member_path, selected_polarizations):
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    return extract_dir


def find_alos4_files(product_dir: str | Path) -> dict[str, list[Path]]:
    """Find standard ALOS-4 CEOS product files inside a product directory."""
    product_dir = Path(product_dir).resolve()
    files = {
        "IMG": sorted(product_dir.rglob("IMG-*")),
        "LED": sorted(product_dir.rglob("LED-*")),
        "TRL": sorted(product_dir.rglob("TRL-*")),
        "VOL": sorted(product_dir.rglob("VOL-*")),
        "BRS": sorted(product_dir.rglob("BRS-*")),
        "summary": sorted(product_dir.rglob("summary-ALOS4*.txt")),
        "kml": sorted(product_dir.rglob("*.kml")),
    }

    if len(files["IMG"]) == 0:
        raise FileNotFoundError(f"No IMG-* file found in {product_dir}")

    return files


def parse_alos4_img_filename(img_file: str | Path) -> dict[str, str]:
    """Parse polarization, path, frame, date, and mode from an ALOS-4 IMG name."""
    img_file = Path(img_file)
    match = ALOS4_IMG_PATTERN.search(img_file.name)

    if match is None:
        raise ValueError(f"Could not parse ALOS-4 IMG filename: {img_file.name}")

    groups = match.groupdict()
    return {
        "polarization": groups["polarization"].upper(),
        "path": groups["path"],
        "frame": groups["frame"].lstrip("0") or "0",
        "frame_padded": groups["frame"],
        "date": f"20{groups['date']}",
        "obs_mode": groups["obs_mode"].upper(),
        "beam_code": groups["beam_code"],
        "beam": groups["beam_code"][-2:],
        "full_name": img_file.name,
    }


def detect_product_metadata(product_dir: str | Path) -> dict:
    """Detect ALOS-4 product files and lightweight metadata."""
    files = find_alos4_files(product_dir)
    img_file = _select_primary_img(files["IMG"])
    product_root = img_file.parent.resolve()
    img_info = parse_alos4_img_filename(img_file)

    summary = {}
    if files["summary"]:
        summary = parse_alos4_summary(files["summary"][0])

    return {
        "product_root": product_root,
        "img_file": img_file,
        "img_info": img_info,
        "summary": summary,
        "files": files,
    }


def _select_primary_img(img_files: list[Path], preferred_polarization: str = "HH") -> Path:
    preferred = [
        img_file
        for img_file in img_files
        if img_file.name.startswith(f"IMG-{preferred_polarization.upper()}-")
    ]
    if preferred:
        return preferred[0]
    return img_files[0]


def _normalize_polarizations(
    polarizations: str | list[str] | tuple[str, ...] | set[str] | None,
) -> set[str] | None:
    if polarizations is None:
        return None

    if isinstance(polarizations, str):
        values = [polarizations]
    else:
        values = list(polarizations)

    normalized = {value.upper() for value in values}
    invalid = sorted(normalized - VALID_POLARIZATIONS)
    if invalid:
        raise ValueError(
            f"Unsupported polarization(s): {invalid}. "
            f"Expected one or more of {sorted(VALID_POLARIZATIONS)}."
        )
    return normalized


def _should_extract_member(member_path: Path, polarizations: set[str] | None) -> bool:
    if polarizations is None:
        return True

    match = re.match(r"^(?:IMG|BRS)-(?P<polarization>[A-Z]{2})-", member_path.name, re.IGNORECASE)
    if match is None:
        return True

    return match.group("polarization").upper() in polarizations
