#!/usr/bin/env python3
"""sega_text.py - every word `orig/dune2.gen` says.

    sega_text.py [--rom orig/dune2.gen] [--out orig/sega/res/text]

Writes `strings.txt`: the whole string table, with the address each string
lives at.  Unlike the NES demo, the Mega Drive Dune II keeps its text as
plain NUL-terminated ASCII, so this is a matter of finding the runs rather
than working out an encoding - but there is something worth noticing in
them, which is why the tool exists rather than a grep.

## The .wsa names

Half the strings are pairs: a name the player sees and a filename nobody
does.

    Const Yard      construc.wsa
    Windtrap        windtrap.wsa
    Spice Silo      storage.wsa

`.wsa` is Westwood's own animation format, and those files are the ones
that shipped with the PC Dune II in 1992.  The Mega Drive port kept the
whole table - names, filenames and all - and simply resolved the filenames
to offsets when it was built.  The table is therefore the game's own list
of what a building and a unit *are*, in the order the original had them,
and it is written out here as such.
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

RUN = re.compile(rb"[\x20-\x7E]{4,}")
WSA = re.compile(r"^[a-z0-9\-]{1,8}\.(wsa|cps|pal|voc|shp)$", re.I)


def strings(rom, least=4):
    out = []
    for m in RUN.finditer(rom):
        s = m.group().decode("ascii")
        letters = sum(c.isalpha() for c in s)
        if letters < 3 or len(set(s)) < 4:
            continue
        out.append((m.start(), s))
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/text"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    found = strings(rom)
    assets = [(o, s) for o, s in found if WSA.match(s)]

    lines = [
        "# strings.txt - every string in orig/dune2.gen.",
        "#",
        "# Written by tools/sega/sega_text.py.  Reference only: the bytes",
        "# themselves are in orig/sega/src/romNN.asm, where a string shows",
        "# up as a dc.b run, so changing one means editing the source and",
        "# rebuilding.",
        "#",
        "# The Mega Drive game keeps its text as plain NUL-terminated ASCII.",
        f"# {len(assets)} of these are Westwood asset filenames - .wsa",
        "# animations, .cps pictures, .pal palettes - carried over from the",
        "# 1992 PC original and resolved to offsets when this port was built.",
        "#",
        "# address  text",
        "",
    ]
    for o, s in found:
        lines.append(f"${o:06X}  {s}")
    (out / "strings.txt").write_text("\n".join(lines) + "\n")

    # the name/filename pairs, in the order the game has them
    pairs = []
    for i, (o, s) in enumerate(found):
        if WSA.match(s) and i and not WSA.match(found[i - 1][1]):
            pairs.append((found[i - 1][0], found[i - 1][1].strip(), s))
    plines = [
        "# assets.txt - what the game calls each thing, and the Westwood",
        "# file the picture of it came from.",
        "#",
        "# Written by tools/sega/sega_text.py.  A name the player sees, then",
        "# the .wsa/.cps the PC Dune II kept it in; the Mega Drive build",
        "# resolved the filename to an offset but left the table intact.",
        "#",
        "# address  name                  file",
        "",
    ]
    for o, name, f in pairs:
        plines.append(f"${o:06X}  {name:<20}  {f}")
    (out / "assets.txt").write_text("\n".join(plines) + "\n")

    print(f"{len(found)} strings -> {out}/strings.txt")
    print(f"{len(pairs)} name/file pairs -> {out}/assets.txt")


if __name__ == "__main__":
    main()
