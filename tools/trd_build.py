#!/usr/bin/env python3
"""Build a TR-DOS .trd disk image from a manifest.json + file list.

Usage:
    trd_build.py MANIFEST.json OUTPUT.trd [--force]

manifest.json format (see .claude/docs/tools/trd.md):
    {
      "label": "OPEN IT!",
      "disk_type": 22,
      "files": [
        {"name": "OPEN IT!", "type": "B", "param1": 196, "file": "open_it.b.bin"},
        ...
      ]
    }

Files are placed on disk sequentially in catalog-entry order, starting at
track 1 sector 0 (track 0 is reserved for the catalog and system sector).
"""

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trdlib as trd


def build(manifest_path, output_path, force):
    manifest = json.loads(manifest_path.read_text())
    base_dir = manifest_path.parent
    label = manifest.get("label", "")
    disk_type = manifest.get("disk_type", trd.DEFAULT_DISK_TYPE)
    files = manifest["files"]

    if len(files) > trd.CATALOG_ENTRIES_MAX:
        sys.exit(f"error: {len(files)} catalog entries exceeds max {trd.CATALOG_ENTRIES_MAX}")

    image = bytearray(trd.IMAGE_SIZE)
    next_linear_sector = trd.FIRST_DATA_SECTOR_INDEX
    file_count = 0
    used_indices = set()

    for auto_index, entry in enumerate(files):
        index = entry.get("index", auto_index)
        if index >= trd.CATALOG_ENTRIES_MAX:
            sys.exit(f"error: catalog index {index} out of range")
        if index in used_indices:
            sys.exit(f"error: duplicate catalog index {index}")
        used_indices.add(index)
        catalog_off = index * trd.CATALOG_ENTRY_SIZE

        if entry.get("deleted"):
            image[catalog_off] = trd.DELETED_MARKER
            continue

        data_path = base_dir / entry["file"]
        if not data_path.is_file():
            sys.exit(f"error: {data_path} not found")
        raw = data_path.read_bytes()
        if len(raw) % trd.SECTOR_SIZE != 0:
            raw = raw + b"\x00" * (trd.SECTOR_SIZE - (len(raw) % trd.SECTOR_SIZE))

        sectors = entry.get("sectors", len(raw) // trd.SECTOR_SIZE)
        needed = sectors * trd.SECTOR_SIZE
        if needed < len(raw):
            sys.exit(f"error: {entry['file']} ({len(raw)} bytes) larger than declared sectors={sectors}")
        raw = raw + b"\x00" * (needed - len(raw))

        if next_linear_sector + sectors > trd.TOTAL_SECTORS:
            sys.exit("error: disk full, ran out of sectors")

        start_track, start_sector = trd.linear_to_track_sector(next_linear_sector)
        start = next_linear_sector * trd.SECTOR_SIZE
        image[start : start + needed] = raw
        next_linear_sector += sectors

        catalog_entry = {
            "name": entry["name"],
            "type": entry["type"],
            "param1": entry.get("param1", 0),
            "length": entry.get("length", needed),
            "sectors": sectors,
            "start_sector": start_sector,
            "start_track": start_track,
        }
        image[catalog_off : catalog_off + 16] = trd.build_catalog_entry(catalog_entry)
        file_count += 1
        print(
            f"{entry['name']!r:12} {entry['type']}  {sectors:4d} sectors "
            f"@ track {start_track} sector {start_sector}"
        )

    used_data_sectors = next_linear_sector - trd.FIRST_DATA_SECTOR_INDEX
    free_sectors = trd.DATA_SECTORS_AVAILABLE - used_data_sectors
    if free_sectors < 0:
        sys.exit("error: disk full")

    first_free_track, first_free_sector = trd.linear_to_track_sector(next_linear_sector)

    sys_off = trd.SYSTEM_SECTOR_INDEX * trd.SECTOR_SIZE
    image[sys_off + trd.OFF_FIRST_FREE_SECTOR] = first_free_sector
    image[sys_off + trd.OFF_FIRST_FREE_TRACK] = first_free_track
    image[sys_off + trd.OFF_DISK_TYPE] = disk_type
    image[sys_off + trd.OFF_FILE_COUNT] = file_count
    image[sys_off + trd.OFF_FREE_SECTORS : sys_off + trd.OFF_FREE_SECTORS + 2] = struct.pack("<H", free_sectors)
    image[sys_off + trd.OFF_TRDOS_SIGNATURE] = trd.TRDOS_SIGNATURE
    image[sys_off + trd.OFF_LABEL : sys_off + trd.OFF_LABEL + 8] = label.encode("ascii")[:8].ljust(8, b" ")

    if output_path.exists() and not force:
        sys.exit(f"error: {output_path} already exists (use --force to overwrite)")
    output_path.write_bytes(bytes(image))
    print(f"\n{file_count} files, {free_sectors} free sectors -> {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path, help="manifest.json describing the disk contents")
    parser.add_argument("output", type=Path, help="path to write the resulting .trd image")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    args = parser.parse_args()

    if not args.manifest.is_file():
        sys.exit(f"error: {args.manifest} not found")

    build(args.manifest, args.output, args.force)


if __name__ == "__main__":
    main()
