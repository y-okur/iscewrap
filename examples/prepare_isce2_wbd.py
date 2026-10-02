#!/usr/bin/env python3
"""Download/mosaic NASA SRTMSWBD tiles into an ISCE2-compatible WBD.

The output convention matches ISCE2 ALOS processing:

    0   land
    -1  water
    -2  no data

The file is declared as BYTE, so water is written as unsigned byte 255. ISCE2
reads the same byte as signed int8, where it becomes -1.

Earthdata download requires a ~/.netrc entry like:

    machine urs.earthdata.nasa.gov login YOUR_USERNAME password YOUR_PASSWORD

and the file should usually be protected with:

    chmod 600 ~/.netrc
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import netrc
from pathlib import Path
import shutil
import urllib.parse
import urllib.request
import zipfile

import numpy as np


SRTMSWBD_COLLECTION_CONCEPT_ID = "C2763268445-LPCLOUD"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
EARTHDATA_LOGIN_HOST = "urs.earthdata.nasa.gov"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare an ISCE2-compatible .wbd/.xml/.vrt from NASA SRTMSWBD."
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("SOUTH", "NORTH", "WEST", "EAST"),
        required=True,
        help="Geographic bounding box in degrees.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for the output WBD and downloaded tile cache.",
    )
    parser.add_argument(
        "--tile-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing manually downloaded *.SRTMSWBD.raw.zip tiles. "
            "Defaults to OUTPUT_DIR/tiles."
        ),
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="Download missing tiles from NASA Earthdata using ~/.netrc.",
    )
    parser.add_argument(
        "--netrc",
        type=Path,
        default=None,
        help="Optional .netrc path. Defaults to ~/.netrc.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing downloaded tiles and output WBD.",
    )
    args = parser.parse_args()

    output = prepare_isce2_wbd(
        bbox=args.bbox,
        output_dir=args.output_dir,
        tile_dir=args.tile_dir,
        download_missing=args.download_missing,
        netrc_file=args.netrc,
        overwrite=args.overwrite,
    )
    print(f"WBD: {output}")
    print(f"XML: {output}.xml")
    print(f"VRT: {output}.vrt")


def prepare_isce2_wbd(
    *,
    bbox: list[float],
    output_dir: Path,
    tile_dir: Path | None = None,
    download_missing: bool = False,
    netrc_file: Path | None = None,
    overwrite: bool = False,
) -> Path:
    south, north, west, east = rounded_extent(bbox)
    output_dir = output_dir.resolve()
    tile_dir = (output_dir / "tiles" if tile_dir is None else tile_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tile_dir.mkdir(parents=True, exist_ok=True)

    expected = {
        swbd_tile_id(lat, lon): (lat, lon)
        for lat in range(south, north)
        for lon in range(west, east)
    }
    tile_files = find_existing_tiles(tile_dir, expected)

    missing = sorted(tile_id for tile_id in expected if tile_id not in tile_files)
    if missing and not download_missing:
        raise RuntimeError(
            "Missing SWBD tiles: "
            + ", ".join(missing)
            + "\nPut the .raw.zip files in --tile-dir or rerun with --download-missing."
        )

    if missing:
        downloads = query_nasa_swbd_granules(south=south, north=north, west=west, east=east)
        opener = earthdata_opener(netrc_file)
        for tile_id in missing:
            if tile_id not in downloads:
                raise RuntimeError(f"NASA CMR did not return a URL for {tile_id}")
            zip_file = tile_dir / f"{tile_id}.zip"
            tile_files[tile_id] = download_file(
                downloads[tile_id],
                zip_file,
                opener=opener,
                overwrite=overwrite,
            )

    output_file = output_dir / wbd_filename(south, north, west, east)
    write_wbd_mosaic(
        tile_zip_files={expected[tile_id]: tile_files[tile_id] for tile_id in expected},
        output_file=output_file,
        south=south,
        north=north,
        west=west,
        east=east,
        overwrite=overwrite,
    )
    return output_file


def rounded_extent(bbox: list[float]) -> tuple[int, int, int, int]:
    south, north, west, east = bbox
    return math.floor(south), math.ceil(north), math.floor(west), math.ceil(east)


def format_lat(value: int) -> str:
    return f"{'N' if value >= 0 else 'S'}{abs(value):02d}"


def format_lon(value: int) -> str:
    return f"{'E' if value >= 0 else 'W'}{abs(value):03d}"


def swbd_tile_id(lat: int, lon: int) -> str:
    return f"{format_lat(lat)}{format_lon(lon)}.SRTMSWBD.raw"


def wbd_filename(south: int, north: int, west: int, east: int) -> str:
    return (
        f"swbdLat_{format_lat(south)}_{format_lat(north)}_"
        f"Lon_{format_lon(west)}_{format_lon(east)}.wbd"
    )


def find_existing_tiles(tile_dir: Path, expected: dict[str, tuple[int, int]]) -> dict[str, Path]:
    found = {}
    for tile_id in expected:
        matches = sorted(tile_dir.glob(f"{tile_id}*.zip"))
        if matches:
            found[tile_id] = matches[0]
    return found


def query_nasa_swbd_granules(
    *,
    south: int,
    north: int,
    west: int,
    east: int,
) -> dict[str, str]:
    params = {
        "collection_concept_id": SRTMSWBD_COLLECTION_CONCEPT_ID,
        "bounding_box": f"{west},{south},{east},{north}",
        "page_size": 2000,
    }
    url = f"{CMR_GRANULES_URL}?{urllib.parse.urlencode(params)}"
    print(f"Querying NASA CMR: {url}")

    with urllib.request.urlopen(url, timeout=60) as response:
        feed = json.load(response).get("feed", {})

    downloads = {}
    for entry in feed.get("entry", []):
        tile_id = entry.get("producer_granule_id") or entry.get("title")
        if not tile_id:
            continue
        for link in entry.get("links", []):
            href = link.get("href", "")
            rel = link.get("rel", "")
            inherited = link.get("inherited", False)
            if inherited or not href.startswith("https://"):
                continue
            if rel.endswith("/data#") and href.endswith(".SRTMSWBD.raw.zip"):
                downloads[tile_id] = href
                break
    return downloads


def earthdata_opener(netrc_file: Path | None):
    try:
        auth = netrc.netrc(None if netrc_file is None else str(netrc_file))
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Earthdata .netrc credentials were not found. Create ~/.netrc with "
            "urs.earthdata.nasa.gov credentials."
        ) from exc
    except netrc.NetrcParseError as exc:
        message = str(exc)
        if "access too permissive" in message:
            message += "; fix with: chmod 600 ~/.netrc"
        raise RuntimeError(f"Could not parse .netrc: {message}") from exc

    credentials = auth.authenticators(EARTHDATA_LOGIN_HOST)
    if credentials is None:
        raise RuntimeError(f".netrc has no entry for {EARTHDATA_LOGIN_HOST!r}")

    login, _, password = credentials
    password_mgr = urllib.request.HTTPPasswordMgrWithPriorAuth()
    password_mgr.add_password(
        realm=None,
        uri=f"https://{EARTHDATA_LOGIN_HOST}",
        user=login,
        passwd=password,
        is_authenticated=True,
    )
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPBasicAuthHandler(password_mgr),
    )


def download_file(url: str, output_file: Path, *, opener, overwrite: bool = False) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists() and output_file.stat().st_size > 0 and not overwrite:
        print(f"Already downloaded: {output_file}")
        return output_file

    print(f"Downloading: {url}")
    tmp_file = output_file.with_suffix(output_file.suffix + ".part")
    if tmp_file.exists():
        tmp_file.unlink()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "isce2-wbd"})
        with opener.open(request, timeout=120) as response, open(tmp_file, "wb") as f:
            shutil.copyfileobj(response, f)
        tmp_file.replace(output_file)
    except Exception:
        if tmp_file.exists():
            tmp_file.unlink()
        raise
    return output_file


def read_swbd_raw_zip(zip_file: Path) -> np.ndarray:
    with zipfile.ZipFile(zip_file, "r") as zf:
        members = [
            info
            for info in zf.infolist()
            if not info.is_dir() and info.filename.lower().endswith(".raw")
        ]
        if len(members) != 1:
            raise RuntimeError(f"Expected one .raw member in {zip_file}, found {len(members)}")
        raw = zf.read(members[0])

    side = math.isqrt(len(raw))
    if side * side != len(raw) or side not in (3600, 3601):
        raise RuntimeError(f"Unsupported SWBD tile byte count in {zip_file}: {len(raw)}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(side, side)


def write_wbd_mosaic(
    *,
    tile_zip_files: dict[tuple[int, int], Path],
    output_file: Path,
    south: int,
    north: int,
    west: int,
    east: int,
    overwrite: bool = False,
) -> None:
    width = (east - west) * 3600
    length = (north - south) * 3600
    if output_file.exists() and output_file.stat().st_size > 0 and not overwrite:
        print(f"Already prepared: {output_file}")
    else:
        mosaic = np.memmap(output_file, mode="w+", dtype=np.uint8, shape=(length, width))
        for lat in range(south, north):
            for lon in range(west, east):
                tile = read_swbd_raw_zip(tile_zip_files[(lat, lon)])
                isce_tile = np.where(tile[:3600, :3600] != 0, 255, 0).astype(np.uint8)
                row = (north - lat - 1) * 3600
                col = (lon - west) * 3600
                mosaic[row : row + 3600, col : col + 3600] = isce_tile
        mosaic.flush()
        del mosaic

    write_isce_wbd_xml(output_file, width=width, length=length)
    write_isce_wbd_vrt(output_file, width=width, length=length)

    signed = np.fromfile(output_file, dtype=np.int8)
    values, counts = np.unique(signed, return_counts=True)
    print("ISCE int8 values:", dict(zip(values.tolist(), counts.tolist())))


def write_isce_wbd_xml(output_file: Path, *, width: int, length: int) -> None:
    xml = f"""<imageFile>
    <property name="byte_order"><value>l</value></property>
    <component name="coordinate1">
        <factorymodule>isceobj.Image</factorymodule>
        <factoryname>createCoordinate</factoryname>
        <property name="delta"><value>1</value></property>
        <property name="endingvalue"><value>{width}</value></property>
        <property name="family"><value>imagecoordinate</value></property>
        <property name="name"><value>imagecoordinate_name</value></property>
        <property name="size"><value>{width}</value></property>
        <property name="startingvalue"><value>0</value></property>
    </component>
    <component name="coordinate2">
        <factorymodule>isceobj.Image</factorymodule>
        <factoryname>createCoordinate</factoryname>
        <property name="delta"><value>1</value></property>
        <property name="endingvalue"><value>{length}</value></property>
        <property name="family"><value>imagecoordinate</value></property>
        <property name="name"><value>imagecoordinate_name</value></property>
        <property name="size"><value>{length}</value></property>
        <property name="startingvalue"><value>0</value></property>
    </component>
    <property name="data_type"><value>BYTE</value></property>
    <property name="description"><value>['water body. (0) --- land; (-1) --- water; (-2) --- no data.']</value></property>
    <property name="extra_file_name"><value>{output_file.name}.vrt</value></property>
    <property name="family"><value>image</value></property>
    <property name="file_name"><value>{output_file.name}</value></property>
    <property name="length"><value>{length}</value></property>
    <property name="name"><value>image_name</value></property>
    <property name="number_bands"><value>1</value></property>
    <property name="scheme"><value>BIP</value></property>
    <property name="width"><value>{width}</value></property>
    <property name="xmax"><value>{width}</value></property>
    <property name="xmin"><value>0</value></property>
</imageFile>
"""
    Path(str(output_file) + ".xml").write_text(xml, encoding="utf-8")


def write_isce_wbd_vrt(output_file: Path, *, width: int, length: int) -> None:
    vrt = f"""<VRTDataset rasterXSize="{width}" rasterYSize="{length}">
    <VRTRasterBand dataType="Byte" band="1" subClass="VRTRawRasterBand">
        <SourceFilename relativeToVRT="1">{output_file.name}</SourceFilename>
        <ByteOrder>LSB</ByteOrder>
        <ImageOffset>0</ImageOffset>
        <PixelOffset>1</PixelOffset>
        <LineOffset>{width}</LineOffset>
    </VRTRasterBand>
</VRTDataset>
"""
    Path(str(output_file) + ".vrt").write_text(vrt, encoding="utf-8")


if __name__ == "__main__":
    main()
