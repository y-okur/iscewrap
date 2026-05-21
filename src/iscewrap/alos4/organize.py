"""Organize ALOS-4 products into ISCE2-ready acquisition folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import zipfile


ALOS4_STRIPMAP_ZIP_PATTERN = re.compile(
    r"^(?P<path>\d+)-"
    r"(?P<frame>\d+)-"
    r"(?P<mode>[A-Z0-9]+)_(?P<beam>\d+)"
    r"(?:_(?P<direction>[A-Z]))?-"
    r"(?P<date>\d{8})"
    r"\.zip$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Alos4StripmapProduct:
    """Metadata parsed from an ALOS-4 stripmap product ZIP filename."""

    zip_file: Path
    path: str
    frame: str
    mode: str
    beam: str
    date: str
    direction: str | None = None

    @property
    def group_name(self) -> str:
        """Return the stack group name for products that can be paired."""
        return f"path_{self.path}/{self.mode}_{self.beam}"


def parse_alos4_stripmap_zip_name(zip_file: str | Path) -> Alos4StripmapProduct:
    """Parse an ALOS-4 stripmap ZIP filename.

    Expected names look like ``125-710-RU1_08_F-20250728.zip``. Products with
    the same path, mode, beam/off-nadir, and date are extracted into the same
    acquisition folder.
    """
    zip_file = Path(zip_file)
    match = ALOS4_STRIPMAP_ZIP_PATTERN.match(zip_file.name)

    if match is None:
        raise ValueError(f"Not an ALOS-4 stripmap ZIP filename: {zip_file.name}")

    groups = match.groupdict()
    return Alos4StripmapProduct(
        zip_file=zip_file,
        path=groups["path"],
        frame=groups["frame"],
        mode=groups["mode"].upper(),
        beam=groups["beam"],
        date=groups["date"],
        direction=None
        if groups["direction"] is None
        else groups["direction"].upper(),
    )


def parse_alos4_summary(summary_file: str | Path) -> dict[str, str]:
    """Parse an ALOS-4 summary text file into a key/value dictionary."""
    summary_file = Path(summary_file).resolve()
    metadata: dict[str, str] = {}

    with open(summary_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)
            metadata[key] = value.strip().strip('"')

    return metadata


def find_alos4_stripmap_zips(input_dir: str | Path) -> list[Path]:
    """Find ALOS-4 stripmap ZIP products in a directory."""
    input_dir = Path(input_dir).resolve()
    return sorted(
        zip_file
        for zip_file in input_dir.glob("*.zip")
        if ALOS4_STRIPMAP_ZIP_PATTERN.match(zip_file.name)
    )


def organize_alos4_stripmap_zips(
    zip_files: str | Path | list[str | Path] | tuple[str | Path, ...],
    output_dir: str | Path,
    *,
    overwrite: bool = False,
    polarizations: str | list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, dict]:
    """Extract ALOS-4 stripmap ZIPs into grouped YYYYMMDD folders."""
    output_dir = Path(output_dir).resolve()
    selected_polarizations = _normalize_polarizations(polarizations)
    products = [
        parse_alos4_stripmap_zip_name(zip_file)
        for zip_file in _normalize_zip_inputs(zip_files)
    ]

    grouped: dict[str, dict] = {}
    for product in products:
        date_dir = output_dir / product.group_name / product.date
        date_dir.mkdir(parents=True, exist_ok=True)
        _extract_zip(
            product.zip_file,
            date_dir,
            overwrite=overwrite,
            polarizations=selected_polarizations,
        )

        group = grouped.setdefault(
            product.group_name,
            {
                "path": product.path,
                "mode": product.mode,
                "beam": product.beam,
                "dates": {},
            },
        )
        date_entry = group["dates"].setdefault(
            product.date,
            {
                "date_dir": date_dir,
                "frames": [],
                "products": [],
            },
        )
        date_entry["frames"].append(product.frame)
        date_entry["products"].append(product)

    for group in grouped.values():
        for date_entry in group["dates"].values():
            date_entry["frames"] = sorted(set(date_entry["frames"]))
            date_entry["products"] = sorted(
                date_entry["products"],
                key=lambda item: (item.frame, item.zip_file.name),
            )

    return grouped


def find_alos4_product_dirs(input_dir: str | Path) -> list[Path]:
    """Find extracted ALOS-4 product directories containing summary files."""
    input_dir = Path(input_dir).resolve()
    return sorted({summary.parent for summary in input_dir.rglob("summary-ALOS4*.txt")})


def _normalize_zip_inputs(
    zip_files: str | Path | list[str | Path] | tuple[str | Path, ...],
) -> list[Path]:
    if isinstance(zip_files, (str, Path)):
        zip_files = Path(zip_files).resolve()

    if isinstance(zip_files, Path):
        if zip_files.is_dir():
            return find_alos4_stripmap_zips(zip_files)
        return [zip_files]

    return [Path(zip_file).resolve() for zip_file in zip_files]


def _extract_zip(
    zip_file: Path,
    output_dir: Path,
    *,
    overwrite: bool,
    polarizations: set[str] | None,
) -> None:
    zip_file = zip_file.resolve()

    with zipfile.ZipFile(zip_file, "r") as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(
                    f"Unsafe ZIP member path in {zip_file}: {member.filename}"
                )

            target = output_dir / member_path
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            if not _should_extract_member(member_path, polarizations):
                continue

            if target.exists() and not overwrite:
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _normalize_polarizations(
    polarizations: str | list[str] | tuple[str, ...] | set[str] | None,
) -> set[str] | None:
    if polarizations is None:
        return None

    if isinstance(polarizations, str):
        values = [polarizations]
    else:
        values = list(polarizations)

    valid = {"HH", "HV", "VH", "VV"}
    normalized = {value.upper() for value in values}
    invalid = sorted(normalized - valid)
    if invalid:
        raise ValueError(
            f"Unsupported polarization(s): {invalid}. "
            f"Expected one or more of {sorted(valid)}."
        )
    return normalized


def _should_extract_member(member_path: Path, polarizations: set[str] | None) -> bool:
    if polarizations is None:
        return True

    match = re.match(r"^(?:IMG|BRS)-(?P<polarization>[A-Z]{2})-", member_path.name, re.IGNORECASE)
    if match is None:
        return True

    return match.group("polarization").upper() in polarizations
