"""Organize ALOS-2 products into ISCE2-ready acquisition folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import zipfile


ALOS2_STRIPMAP_ZIP_PATTERN = re.compile(
    r"^(?P<path>\d+)-"
    r"(?P<frame>\d+)-"
    r"(?P<mode>[A-Z0-9]+)_(?P<beam>\d+)-"
    r"(?P<date>\d{8})"
    r"(?P<suffix>_[+-]?\d+)?"
    r"\.zip$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Alos2StripmapProduct:
    """Metadata parsed from an ALOS-2 stripmap product ZIP filename."""

    zip_file: Path
    path: str
    frame: str
    mode: str
    beam: str
    date: str
    suffix: str | None = None

    @property
    def group_name(self) -> str:
        """Return the ISCE-compatible stack group name for this product."""
        return f"path_{self.path}/{self.mode}_{self.beam}"


def parse_alos2_stripmap_zip_name(zip_file: str | Path) -> Alos2StripmapProduct:
    """Parse an ALOS-2 stripmap ZIP filename.

    Expected names look like ``24-3390-RF2_6-20160326_+2.zip``.  Products
    with the same path, mode, beam/off-nadir, and date can be placed in one
    date folder so ISCE2 can stitch/process the frames together.
    """
    zip_file = Path(zip_file)
    match = ALOS2_STRIPMAP_ZIP_PATTERN.match(zip_file.name)

    if match is None:
        raise ValueError(f"Not an ALOS-2 stripmap ZIP filename: {zip_file.name}")

    groups = match.groupdict()
    return Alos2StripmapProduct(
        zip_file=zip_file,
        path=groups["path"],
        frame=groups["frame"],
        mode=groups["mode"].upper(),
        beam=groups["beam"],
        date=groups["date"],
        suffix=groups["suffix"],
    )


def find_alos2_stripmap_zips(input_dir: str | Path) -> list[Path]:
    """Find ALOS-2 stripmap ZIP products in a directory."""
    input_dir = Path(input_dir).resolve()
    return sorted(
        zip_file
        for zip_file in input_dir.glob("*.zip")
        if ALOS2_STRIPMAP_ZIP_PATTERN.match(zip_file.name)
    )


def organize_alos2_stripmap_zips(
    zip_files: str | Path | list[str | Path] | tuple[str | Path, ...],
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, dict]:
    """Extract ALOS-2 stripmap ZIPs into grouped YYYYMMDD folders.

    Parameters
    ----------
    zip_files
        A directory containing ZIP products, a single ZIP product, or an
        iterable of ZIP products.
    output_dir
        Destination root. Products are written as
        ``output_dir/path_<path>/<mode>_<beam>/<YYYYMMDD>/``.
    overwrite
        If True, files inside ZIP products replace existing files.

    Returns
    -------
    dict
        Group/date index with extracted paths and parsed product metadata.
    """
    output_dir = Path(output_dir).resolve()
    products = [
        parse_alos2_stripmap_zip_name(zip_file)
        for zip_file in _normalize_zip_inputs(zip_files)
    ]

    grouped: dict[str, dict] = {}
    for product in products:
        date_dir = output_dir / product.group_name / product.date
        date_dir.mkdir(parents=True, exist_ok=True)
        _extract_zip_flat(product.zip_file, date_dir, overwrite=overwrite)

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


def _normalize_zip_inputs(
    zip_files: str | Path | list[str | Path] | tuple[str | Path, ...],
) -> list[Path]:
    if isinstance(zip_files, (str, Path)):
        zip_files = Path(zip_files).resolve()

    if isinstance(zip_files, Path):
        if zip_files.is_dir():
            return find_alos2_stripmap_zips(zip_files)
        return [zip_files]

    return [Path(zip_file).resolve() for zip_file in zip_files]


def _extract_zip_flat(zip_file: Path, output_dir: Path, *, overwrite: bool) -> None:
    """Extract one product ZIP into an acquisition folder."""
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

            if target.exists() and not overwrite:
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
