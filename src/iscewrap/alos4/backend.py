"""Runtime ALOS-4 sensor compatibility backend for ISCE2 Alos2Proc.

This module keeps the ALOS-4-specific behavior in importable package code
instead of generating ad-hoc monkeypatches into a temporary launcher.  It still
reuses ISCE2's mature ALOS-2 stripmap processing chain, but the product file
discovery, range sampling constants, and ALOS-4 CEOS layout corrections live
here as the beginning of a native ALOS-4 backend.
"""

from __future__ import annotations

from pathlib import Path
import glob as _glob
import os

from .metadata import detect_product_metadata, parse_alos4_img_filename


DEFAULT_ALOS4_RANGE_SAMPLING_RATES = {
    # JAXA PALSAR-3 CEOS sampling-frequency settings.  The ALOS-2 reader
    # indexes this table by integer MHz code.
    98: 98_242_186.875,
    49: 49_121_093.4375,
    32: 32_747_395.625,
    16: 16_373_697.8125,
}


_ORIGINAL_GLOB = None
_REGISTERED_PRODUCT_DIRS: tuple[Path, ...] = ()
_ALIAS_DIR_BY_PRODUCT_DIR: dict[Path, Path] = {}


def install_alos4_backend(
    *,
    reference_dir,
    secondary_dir,
    alias_dir,
    compat_mode="FBD",
    use_aliases=True,
    range_sampling_rates: dict[int, float] | None = None,
) -> None:
    """Install ALOS-4 runtime hooks into the current Python process.

    The hooks are intentionally narrow: they affect ALOS-2 CEOS filename
    discovery inside the registered reference/secondary directories, add ALOS-4
    range sampling constants, and correct the CEOS image/swath metadata cases
    seen in the first UWD products.
    """
    global _ORIGINAL_GLOB, _REGISTERED_PRODUCT_DIRS, _ALIAS_DIR_BY_PRODUCT_DIR

    _REGISTERED_PRODUCT_DIRS = (
        Path(reference_dir).resolve(),
        Path(secondary_dir).resolve(),
    )
    if use_aliases:
        alias_root = Path(alias_dir).resolve()
        _ALIAS_DIR_BY_PRODUCT_DIR = {
            _REGISTERED_PRODUCT_DIRS[0]: _prepare_native_alias_dir(
                _REGISTERED_PRODUCT_DIRS[0],
                alias_root / "reference",
                compat_mode=compat_mode,
            ),
            _REGISTERED_PRODUCT_DIRS[1]: _prepare_native_alias_dir(
                _REGISTERED_PRODUCT_DIRS[1],
                alias_root / "secondary",
                compat_mode=compat_mode,
            ),
        }
    else:
        _ALIAS_DIR_BY_PRODUCT_DIR = {}

    rates = default_range_sampling_rates(range_sampling_rates)

    import isce  # noqa: F401
    from isceobj.Sensor.MultiMode.ALOS2 import ALOS2
    import isceobj.Alos2Proc.runBaseline as alos2_baseline

    ALOS2.fsampConst.update(rates)

    if _ORIGINAL_GLOB is None:
        _ORIGINAL_GLOB = _glob.glob
        _glob.glob = _glob_with_alos4_names

    if not getattr(ALOS2, "_iscewrap_alos4_backend_installed", False):
        ALOS2._iscewrap_original_readImage = ALOS2.readImage
        ALOS2._iscewrap_original_setSwath = ALOS2.setSwath
        ALOS2._iscewrap_original_setTrack = ALOS2.setTrack

        ALOS2.readImage = _read_image_with_dynamic_alos4_headers
        ALOS2.setSwath = _set_swath_with_alos4_corrections
        ALOS2.setTrack = _set_track_with_alos4_fallback
        ALOS2._iscewrap_alos4_backend_installed = True

    if not getattr(alos2_baseline, "_iscewrap_alos4_backend_installed", False):
        alos2_baseline._iscewrap_original_runBaseline = alos2_baseline.runBaseline
        alos2_baseline.runBaseline = _run_baseline_with_alos4_debug
        alos2_baseline._iscewrap_alos4_backend_installed = True


def default_range_sampling_rates(
    range_sampling_rates: dict[int, float] | None = None,
) -> dict[int, float]:
    """Return ALOS-4 range sampling rates, allowing caller overrides."""
    rates = dict(DEFAULT_ALOS4_RANGE_SAMPLING_RATES)
    if range_sampling_rates:
        rates.update(
            {int(key): float(value) for key, value in range_sampling_rates.items()}
        )
    return rates


def _glob_with_alos4_names(pattern, *args, **kwargs):
    matches = _ORIGINAL_GLOB(pattern, *args, **kwargs)
    if matches or "ALOS2" not in str(pattern):
        return matches

    translated = _translate_alos2_ceos_pattern_to_alias(pattern)
    if translated is None:
        return matches

    return _ORIGINAL_GLOB(str(translated), *args, **kwargs)


def _translate_alos2_ceos_pattern_to_alias(pattern) -> Path | None:
    pattern_path = Path(pattern)
    parent = pattern_path.parent.resolve()
    name = pattern_path.name
    alias_dir = _ALIAS_DIR_BY_PRODUCT_DIR.get(parent)
    if alias_dir is None:
        return None

    prefix = name.split("ALOS2", 1)[0]
    if not any(prefix.startswith(kind) for kind in ("IMG-", "LED-", "TRL-", "VOL-")):
        return None

    return alias_dir / name


def _prepare_native_alias_dir(
    product_dir: Path,
    alias_dir: Path,
    *,
    compat_mode: str,
) -> Path:
    alias_dir.mkdir(parents=True, exist_ok=True)
    files = detect_product_metadata(product_dir)["files"]

    for img_file in files["IMG"]:
        info = parse_alos4_img_filename(img_file)
        stem = _alos2_compatible_stem(info, compat_mode)
        _link_replace(img_file, alias_dir / f"IMG-{info['polarization']}-{stem}")
        _link_matching_aux(files["LED"], img_file.parent, alias_dir / f"LED-{stem}")
        _link_matching_aux(files["TRL"], img_file.parent, alias_dir / f"TRL-{stem}")
        _link_matching_aux(files["VOL"], img_file.parent, alias_dir / f"VOL-{stem}")

    return alias_dir


def _alos2_compatible_stem(info: dict[str, str], compat_mode: str) -> str:
    frame_token = f"{info['path']}{info['frame_padded']}"
    date_token = info["date"][2:]
    return f"ALOS2{frame_token}-{date_token}-{compat_mode.upper()}"


def _link_matching_aux(files: list[Path], product_root: Path, target: Path) -> None:
    matches = [file for file in files if file.parent.resolve() == product_root.resolve()]
    if matches:
        _link_replace(matches[0], target)


def _link_replace(source: Path, target: Path) -> None:
    source = source.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() and Path(os.readlink(target)) == source:
            return
        target.unlink()
    target.symlink_to(source)


def _read_image_with_dynamic_alos4_headers(self):
    import isceobj
    import isceobj.Sensor.CEOS as CEOS
    from isceobj.Sensor import xmlPrefix

    if not _is_alos4_path(self.imageFile):
        return self._iscewrap_original_readImage()

    if not self.useVirtualFile:
        return self._iscewrap_original_readImage()

    with open(self.imageFile, "rb") as fp:
        image_fdr = CEOS.CEOSDB(
            xml=os.path.join(xmlPrefix, "alos2_slc/image_file.xml"),
            dataFile=fp,
        )
        image_fdr.parse()
        file_header_bytes = image_fdr.getEndOfRecordPosition()
        fp.seek(file_header_bytes)
        record_length = image_fdr.metadata["SAR DATA record length"]
        width = image_fdr.metadata["Number of pixels per line per SAR channel"]
        length = image_fdr.metadata["Number of SAR DATA records"]
        line_header_bytes = record_length - width * 8
        if line_header_bytes < 0:
            raise ValueError(
                "Invalid ALOS-4 CEOS record geometry: "
                f"recordLength={record_length}, width={width}"
            )

        image_data = CEOS.CEOSDB(
            xml=os.path.join(xmlPrefix, "alos2_slc/image_record.xml"),
            dataFile=fp,
        )
        image_data.parseFast()

    image = isceobj.createSlcImage()
    image.setFilename(self.outputFile)
    image.setWidth(width)
    image.setLength(length)
    image.renderHdr()

    with open(self.outputFile + ".vrt", "w") as fid:
        fid.write(
            '<VRTDataset rasterXSize="{0}" rasterYSize="{1}">\n'
            '    <VRTRasterBand band="1" dataType="CFloat32" '
            'subClass="VRTRawRasterBand">\n'
            '        <SourceFilename relativeToVRT="0">{2}</SourceFilename>\n'
            "        <ByteOrder>MSB</ByteOrder>\n"
            "        <ImageOffset>{3}</ImageOffset>\n"
            "        <PixelOffset>8</PixelOffset>\n"
            "        <LineOffset>{4}</LineOffset>\n"
            "    </VRTRasterBand>\n"
            "</VRTDataset>".format(
                width,
                length,
                self.imageFile,
                file_header_bytes + line_header_bytes,
                record_length,
            )
        )

    print(
        "[iscewrap-alos4] CEOS image layout:",
        "file=", self.imageFile,
        "fileHeaderBytes=", file_header_bytes,
        "lineHeaderBytes=", line_header_bytes,
        "recordLength=", record_length,
        "width=", width,
        "length=", length,
        flush=True,
    )
    return image_fdr, image_data


def _set_swath_with_alos4_corrections(
    self,
    leaderFDR,
    sceneHeaderRecord,
    platformPositionRecord,
    facilityRecord,
    imageFDR,
    imageData,
):
    if _is_alos4_path(self.imageFile):
        range_key = "Slant range to 1st data sample"
        starting_range = imageData.metadata.get(range_key)
        if starting_range is not None and starting_range > 10_000_000:
            imageData.metadata[range_key] = starting_range * 0.01

    result = self._iscewrap_original_setSwath(
        leaderFDR,
        sceneHeaderRecord,
        platformPositionRecord,
        facilityRecord,
        imageFDR,
        imageData,
    )

    if _is_alos4_path(self.imageFile):
        swath = self.track.frames[-1].swaths[-1]
        print(
            "[iscewrap-alos4] swath geometry:",
            "file=", self.imageFile,
            "samples=", swath.numberOfSamples,
            "lines=", swath.numberOfLines,
            "startingRange=", swath.startingRange,
            "rangeSamplingRate=", swath.rangeSamplingRate,
            "rangePixelSize=", swath.rangePixelSize,
            "prf=", swath.prf,
            "sensingStart=", swath.sensingStart,
            flush=True,
        )

    return result


def _set_track_with_alos4_fallback(
    self,
    leaderFDR,
    sceneHeaderRecord,
    platformPositionRecord,
    facilityRecord,
    imageFDR,
    imageData,
):
    if _is_alos4_path(self.imageFile):
        key = "Time direction indicator along line direction"
        value = sceneHeaderRecord.metadata.get(key)
        if value is None or str(value).strip() == "":
            inferred = _infer_pass_direction(self, platformPositionRecord)
            if inferred is not None:
                sceneHeaderRecord.metadata[key] = inferred

    return self._iscewrap_original_setTrack(
        leaderFDR,
        sceneHeaderRecord,
        platformPositionRecord,
        facilityRecord,
        imageFDR,
        imageData,
    )


def _is_alos4_path(path) -> bool:
    path = Path(path)
    return "ALOS4" in path.name or "ALOS4" in path.resolve().name


def _infer_pass_direction(self, platformPositionRecord):
    orbit = self.readOrbit(platformPositionRecord)
    vectors = list(orbit)
    if not vectors:
        return None

    velocity = vectors[len(vectors) // 2].getVelocity()
    if velocity[2] > 0:
        return "ASCEND"
    if velocity[2] < 0:
        return "DESCEND"
    return None


def _run_baseline_with_alos4_debug(self):
    import datetime
    import isceobj.Alos2Proc.runBaseline as alos2_baseline

    reference_track = self._insar.loadTrack(reference=True)
    secondary_track = self._insar.loadTrack(reference=False)
    try:
        reference_swath = reference_track.frames[0].swaths[0]
        mid_range = (
            reference_swath.startingRange
            + reference_swath.rangePixelSize * reference_swath.numberOfSamples * 0.5
        )
        mid_sensing_start = reference_swath.sensingStart + datetime.timedelta(
            seconds=reference_swath.numberOfLines * 0.5 / reference_swath.prf
        )
        llh = reference_track.orbit.rdr2geo(mid_sensing_start, mid_range)
        print(
            "[iscewrap-alos4] baseline geometry:",
            "midRange=", mid_range,
            "midSensingStart=", mid_sensing_start,
            "llh=", llh,
            "referenceOrbitVectors=", len(list(reference_track.orbit)),
            "secondaryOrbitVectors=", len(list(secondary_track.orbit)),
            flush=True,
        )
    except Exception as exc:
        print("[iscewrap-alos4] baseline geometry debug failed:", exc, flush=True)

    return alos2_baseline._iscewrap_original_runBaseline(self)
