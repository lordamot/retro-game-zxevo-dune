#!/usr/bin/env python3
"""Extract files and metadata from a TR-DOS .trd disk image.

Usage:
    trd_unpack.py IMAGE.trd OUTPUT_DIR [--force]

Writes one binary blob per catalog entry plus a manifest.json describing
the disk label, type and per-file catalog metadata. The manifest is a
valid input for trd_build.py, so unpack -> build round-trips byte-for-byte.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trdlib as trd


def sanitize_filename(name, file_type):
    safe = "".join(c if c.isalnum() or c in "!._-" else "_" for c in name)
    safe = safe.strip("_") or "file"
    return f"{safe}.{file_type}.bin"


def unpack(image_path, output_dir, force):
    data = image_path.read_bytes()
    if len(data) != trd.IMAGE_SIZE:
        print(
            f"warning: image size {len(data)} bytes, expected {trd.IMAGE_SIZE} "
            "(standard 80-track/2-side TR-DOS disk)",
            file=sys.stderr,
        )

    catalog = data[0 : trd.CATALOG_BYTES]
    system_sector = data[
        trd.SYSTEM_SECTOR_INDEX * trd.SECTOR_SIZE : (trd.SYSTEM_SECTOR_INDEX + 1) * trd.SECTOR_SIZE
    ]

    disk_type = system_sector[trd.OFF_DISK_TYPE]
    label = system_sector[trd.OFF_LABEL : trd.OFF_LABEL + 8].decode("ascii", errors="replace").rstrip(" ")

    output_dir.mkdir(parents=True, exist_ok=True)
    existing = [p for p in output_dir.iterdir()]
    if existing and not force:
        sys.exit(f"error: {output_dir} is not empty (use --force to overwrite)")

    files_meta = []
    for i in range(trd.CATALOG_ENTRIES_MAX):
        raw_entry = catalog[i * trd.CATALOG_ENTRY_SIZE : (i + 1) * trd.CATALOG_ENTRY_SIZE]
        entry = trd.parse_catalog_entry(raw_entry)
        if entry is None:
            break
        if entry["deleted"]:
            files_meta.append({"index": i, "deleted": True})
            continue

        start = trd.sector_offset(entry["start_track"], entry["start_sector"])
        size = entry["sectors"] * trd.SECTOR_SIZE
        blob = data[start : start + size]

        out_name = sanitize_filename(entry["name"], entry["type"])
        (output_dir / out_name).write_bytes(blob)

        files_meta.append(
            {
                "index": i,
                "name": entry["name"],
                "type": entry["type"],
                "param1": entry["param1"],
                "length": entry["length"],
                "sectors": entry["sectors"],
                "file": out_name,
            }
        )
        print(f"{entry['name']!r:12} {entry['type']}  {entry['sectors']:4d} sectors -> {out_name}")

    manifest = {
        "label": label,
        "disk_type": disk_type,
        "files": files_meta,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\n{len(files_meta)} catalog entries -> {manifest_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path, help="source .trd file")
    parser.add_argument("output_dir", type=Path, help="directory to write extracted files + manifest.json")
    parser.add_argument("--force", action="store_true", help="allow writing into a non-empty output directory")
    args = parser.parse_args()

    if not args.image.is_file():
        sys.exit(f"error: {args.image} not found")

    unpack(args.image, args.output_dir, args.force)


if __name__ == "__main__":
    main()
