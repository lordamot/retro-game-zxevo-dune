#!/usr/bin/env python3
"""sega_maps.py - the 27 battlefields of the Mega Drive Dune II.

    sega_maps.py [--rom orig/dune2.gen] [--out orig/sega/res/data]

The PC Dune II does not store its maps: a mission file names a `Seed`, and
the game grows the landscape from it every time.  The Mega Drive does not
do that.  It keeps all 27 maps in the cartridge, already made, and the
mission file's `Seed` is simply which one to load.

Found by watching the game read them.  The mission loader at $016500
handles the [MAP] section, and for the key 'S' it stores the number at
$FFC064 and calls $01B1D4, which looks it up in the table at $01B276 and
copies a byte a cell into $FF6C98:

    lea     $1B276(pc),a1        ; 27 longwords, one a map
    movea.l $0(a1,d0.w),a1       ; d0 = (Seed - 1) * 4
    ...                          ; bit 31 clear: 64 x 64, 4096 bytes
                                 ; bit 31 set:   32 x 32, 1024 bytes

The six small ones are the first two missions of each house - the ones
whose mission file says MapScale=1.  End to end the 27 fill $071574 to
$087D73 exactly, and stop where the mentat's pointer table begins.

For years this stretch was listed as sample for the DAC, because it has
the shape of one: smooth, and away from $00 and $FF.  The Z80, which
plays every sample there is, never reads a byte of it.

A cell is a terrain icon, already fitted to its neighbours - the edge of a
rock shelf, a dune's crest - which is the work the PC game's generator
does at run time.  `maps.txt` writes each map out as hex, a row a line.

Writes `maps.txt`.
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TABLE = 0x01B276
COUNT = 27


def maps(rom):
    """[(seed, address, side)] in table order."""
    out = []
    for i in range(COUNT):
        v = int.from_bytes(rom[TABLE + 4 * i:TABLE + 4 * i + 4], "big")
        out.append((i + 1, v & 0xFFFFFF, 32 if v >> 31 else 64))
    return out


def map_regions(rom):
    """Named regions for sega_extract.py."""
    out = [(TABLE, TABLE + COUNT * 4,
            "27 pointers, one to each battlefield; bit 31 set is a 32 x 32 "
            "map - read by $01B1D4, see res/data/maps.txt")]
    for seed, a, side in maps(rom):
        out.append((a, a + side * side,
                    f"the battlefield for Seed={seed}: {side} x {side} terrain "
                    "icons, a byte a cell - see res/data/maps.txt"))
    return out


def seeds_used(root):
    """Which mission files name which map, from missions.txt."""
    used = {}
    path = root / "orig/sega/res/data/missions.txt"
    if not path.exists():
        return used
    name = None
    for line in path.read_text().splitlines():
        m = re.match(r"== (\S+)", line)
        if m:
            name = m.group(1)
        m = re.match(r"\s+Seed=(\d+)", line)
        if m and name:
            used.setdefault(int(m.group(1)), []).append(name)
    return used


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/data"))
    args = ap.parse_args()
    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    listing = maps(rom)
    spans = sorted((a, a + s * s) for _, a, s in listing)
    for (a, b), (c, _) in zip(spans, spans[1:]):
        if b != c:
            raise SystemExit(f"maps do not meet: ${b:06X} and ${c:06X}")
    used = seeds_used(ROOT)

    L = ["# maps.txt - the 27 battlefields, from the table at $01B276.",
         "#",
         "# Written by tools/sega/sega_maps.py.  A mission file's Seed is",
         "# the number of its map here; the PC game grows a map from the",
         "# seed, the Mega Drive keeps every one made.  A cell is a byte: a",
         "# terrain icon, already fitted to its neighbours.",
         f"#   ${spans[0][0]:06X}-${spans[-1][1] - 1:06X}, end to end",
         ""]
    unused = [seed for seed, _, _ in listing if seed not in used]
    if used and unused:
        L += [f"# Seed {', '.join(map(str, unused))}: no mission file names "
              "them, and the recorded run", "# never loaded them either - "
              "three battlefields made and never used.", ""]
    for seed, a, side in listing:
        who = ", ".join(used.get(seed, [])) or "no mission file"
        L.append(f"== Seed={seed}  ${a:06X}  {side} x {side}  - {who}")
        for y in range(side):
            row = rom[a + y * side:a + y * side + side]
            L.append("   " + " ".join(f"{b:02X}" for b in row))
        L.append("")
    (out / "maps.txt").write_text("\n".join(L))
    print(f"{len(listing)} maps -> {out}/maps.txt")


if __name__ == "__main__":
    main()
