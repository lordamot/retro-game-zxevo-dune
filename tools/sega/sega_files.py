#!/usr/bin/env python3
"""sega_files.py - the data files Westwood left inside the cartridge.

    sega_files.py [--rom orig/dune2.gen] [--out orig/sega/res/data]

The Mega Drive Dune II carries the PC game's own data files, whole, behind
a little directory of names near `$052C2C`.  This writes them out.

## What that directory is

Thirty-seven entries, each a pair of longwords - a pointer to a
NUL-terminated name and a pointer to the data:

    $052C2C  ->  "BUILD.EMC"     $04DB28
                 "PLAYER.EMC"    $04DF5A
                 "TEAM.EMC"      $04E022
                 "UNIT.EMC"      $04E180
                 "HOUSE.INI"     $052F24
                 "PROFILE.INI"   $053178
                 "REGION.INI"    $054074   REGIONA/H/O.INI
                 "SCENA001.INI"  $056FA6   ... 27 of them, nine a house

A file's length is the distance to the next one when they are sorted by
address, which they are not in the table.  Two routines at `$0046AE` and
`$00004A3A` look a name up in it, so this is a filesystem the game really
opens files through, not a leftover.

## Why it matters

Half of these are the PC original's text, unchanged.  `PROFILE.INI` is the
table of what everything costs and how long it takes to build;
`HOUSE.INI` is what makes a house behave like itself.  The `.EMC` files are
Westwood's own script bytecode - `UNIT.EMC` is 5 KB of it - and
they are where the units' and the computer player's behaviour actually
lives.  The `SCEN*.INI` and `REGION*.INI` are not text on this machine:
the port converted them to a tagged binary, which `sega_scen.py` reads.

Text files come out as themselves.  Binary ones come out as `.bin` beside
a hex listing, so both are readable and neither is guessed at.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

DIR_START = 0x052C2C
DIR_END = 0x052D58
# The last file in the directory has no next one to end it.  SCENO009.INI
# ends itself: a mission file is a run of tagged records terminated by
# $FFFF, and reading it record by record - see tools/sega/sega_scen.py -
# lands exactly on that word at $060E82.  It was cut 1212 bytes short here
# until the records were parsed properly.
DATA_END = 0x060E84


WHAT = {
    "BUILD.EMC": "script bytecode: what a structure does each tick",
    "PLAYER.EMC": "script bytecode: the computer player's turn",
    "TEAM.EMC": "script bytecode: how a group of units behaves together",
    "UNIT.EMC": "script bytecode: every unit's behaviour",
    "HOUSE.INI": "the six houses: decay, special weapon, weakness, voice",
    "PROFILE.INI": "[CONSTRUCT]: cost, build time, hit points, priorities",
    "REGION.INI": "the campaign map: which region follows which",
    "REGIONA.INI": "the Atreides campaign's regions and their text",
    "REGIONH.INI": "the Harkonnen campaign's",
    "REGIONO.INI": "the Ordos campaign's",
}


def read_dir(rom):
    """The name/data pairs, in table order."""
    out = []
    for a in range(DIR_START, DIR_END, 8):
        np = int.from_bytes(rom[a:a + 4], "big")
        dp = int.from_bytes(rom[a + 4:a + 8], "big")
        if not np:
            break
        end = rom.find(b"\0", np)
        if not (0 < end - np < 40):
            break
        out.append((rom[np:end].decode("latin1"), dp, a))
    return out


def with_lengths(entries):
    """A file ends where the next one begins, so they have to be sorted by
    address first - the table is not."""
    order = sorted(entries, key=lambda e: e[1])
    out = []
    for i, (name, dp, at) in enumerate(order):
        end = order[i + 1][1] if i + 1 < len(order) else DATA_END
        # An IFF file says how long it is, and that wins.  UNIT.EMC is the
        # last script, and what follows it is not a file but tiles and
        # fonts ($04F6BE on) - the distance to the next directory entry
        # once made it 19876 bytes when its FORM says 5438.
        if ROM_BYTES is not None and ROM_BYTES[dp:dp + 4] == b"FORM":
            end = dp + 4 + int.from_bytes(ROM_BYTES[dp + 4:dp + 8], "big")
        out.append((name, dp, end - dp, at))
    return out


ROM_BYTES = None        # set by main(), so with_lengths() can read FORMs


def is_text(b):
    if not b:
        return False
    printable = sum(1 for c in b if 32 <= c < 127 or c in (9, 10, 13))
    return printable / len(b) > 0.95


def hexdump(b, base):
    out = []
    for i in range(0, len(b), 16):
        row = b[i:i + 16]
        out.append("%06X  %-47s  %s" % (
            base + i, " ".join("%02X" % c for c in row),
            "".join(chr(c) if 32 <= c < 127 else "." for c in row)))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/data"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    (out / "files").mkdir(parents=True, exist_ok=True)

    global ROM_BYTES
    ROM_BYTES = rom
    entries = with_lengths(read_dir(rom))
    index = [
        "# files.txt - the data files inside orig/dune2.gen.",
        "#",
        "# Written by tools/sega/sega_files.py from the directory at",
        f"# ${DIR_START:06X}: pairs of longwords, a name and its data.  The",
        "# game opens files through it by name, at $0046AE and $004A3A.",
        "#",
        "# Text files are written out as themselves; binary ones as .bin",
        "# with a .hex listing beside them.  sega_scen.py reads the",
        "# scenarios properly.",
        "#",
        "# name          address  bytes  kind   what it is",
        "",
    ]
    ntext = 0
    for name, dp, n, at in entries:
        data = rom[dp:dp + n]
        text = is_text(data)
        if text:
            (out / "files" / name).write_bytes(data)
            ntext += 1
        else:
            (out / "files" / (name + ".bin")).write_bytes(data)
            (out / "files" / (name + ".hex")).write_text(hexdump(data, dp))
        index.append("%-13s $%06X  %5d  %-6s %s"
                     % (name, dp, n, "text" if text else "binary",
                        WHAT.get(name, "one of the 27 missions"
                                 if name.startswith("SCEN") else "")))
    index += [
        "",
        f"# {len(entries)} files, {ntext} of them plain text.",
        "#",
        "# The nine SCENA/SCENH/SCENO files are the campaign: nine missions",
        "# for each of the three playable houses.  They are a tagged binary",
        "# on this machine rather than the PC's text; read them with",
        "# tools/sega/sega_scen.py, which writes them back out as the INI",
        "# they were.",
    ]
    (out / "files.txt").write_text("\n".join(index) + "\n")
    print(f"{len(entries)} files ({ntext} text) -> {out}/files/")
    print(f"index -> {out}/files.txt")


if __name__ == "__main__":
    main()
