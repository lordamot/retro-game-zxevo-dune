#!/usr/bin/env python3
"""build_sega.py - put `orig/sega/` back together into a playable cartridge.

    build_sega.py [--src orig/sega] [--out build/sega/dune2.gen] [--check]

Reads `orig/sega/rom.map`, assembles every region out of `src/` with
`sega_asm.py`, and writes a Mega Drive ROM.  With `--check` (the default
whenever the map carries a SHA-256) it compares the result against the
original and fails on the first byte that differs - which is the point: a
deconstruction that does not rebuild is a description, not a deconstruction.

Nothing but Python is needed; the assembler is this repository's own.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_asm import assemble_many                         # noqa: E402


def build(src, out, check=True, quiet=False):
    src, out = Path(src), Path(out)
    mani = json.loads((src / "rom.map").read_text())
    paths = [src / r["src"] for r in mani["regions"]]
    parts = assemble_many([(p.name, p.read_text(), p.parent) for p in paths])

    rom = bytearray()
    for r, data in zip(mani["regions"], parts):
        if len(data) != r["size"]:
            raise SystemExit(f"{r['src']}: {len(data)} bytes, "
                             f"expected {r['size']}")
        if len(rom) != r["start"]:
            raise SystemExit(f"{r['src']}: starts at ${len(rom):06X}, "
                             f"the map says ${r['start']:06X}")
        rom += data
        if not quiet:
            print(f"  {r['src']:<20} ${r['start']:06X}  {len(data)} bytes")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(rom)
    got = hashlib.sha256(rom).hexdigest()
    if not quiet:
        print(f"{out}  {len(rom)} bytes  sha256 {got}")
    want = mani.get("sha256")
    if check and want and got != want:
        orig = ROOT / "orig" / mani["rom"]
        if orig.exists():
            a = orig.read_bytes()
            n = min(len(a), len(rom))
            first = next((i for i in range(n) if a[i] != rom[i]), n)
            print(f"first difference at ${first:06X}: original "
                  f"{a[first]:02X}, rebuilt {rom[first]:02X}", file=sys.stderr)
        raise SystemExit("build_sega: the rebuild does not match the original")
    if check and want and not quiet:
        print("matches the original byte for byte")
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(ROOT / "orig/sega"))
    ap.add_argument("--out", default=str(ROOT / "build/sega/dune2.gen"))
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    build(args.src, args.out, not args.no_check, args.quiet)


if __name__ == "__main__":
    main()
