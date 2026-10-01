#!/usr/bin/env python3
"""sega_data.py - what everything in Dune II costs, and what it needs first.

    sega_data.py [--rom orig/dune2.gen] [--out orig/sega/res/data]

Writes `buildings.txt`, `units.txt`, `houses.txt` and `actions.txt` out of
the four tables the game indexes directly:

    $06AFA6   19 buildings, $66 bytes each
    $06BC00   27 units,     $5C bytes each
    $06C750    6 houses,    $1E bytes each
    $06CEF8   14 orders,    $0C bytes each

Each record begins the same way - a string id, a pointer to the name, a
second string id, a pointer to the `.wsa` the picture came from - which is
how the tables were found at all: the names in the ROM are pointed at from
exactly one place each, at a constant stride.

## How the fields were identified, and which ones were not

By their values.  This is Dune II, and Dune II's numbers are known: a
Palace costs 999 and a Windtrap 300, a light factory has 800 hit points, a
Trike costs 150 and an MCV 900.  A column that reads 5, 15, 999, 400, 600,
500, 500, 400, 400, 300, 300, 500, 400, 700, 50, 125, 250, 150, 400 down
nineteen buildings is the cost, and there is no other column it could be.

The same test settles the house table completely: Harkonnen toughness 200,
degrading chance 85, minimap colour 144, and a `prefixChar` that really
does hold 'H', 'A', 'O'.

Columns whose values match nothing known are printed as numbers under
their offset and left unnamed.  Guessing at them would put things in this
file that are not true, and the way to settle them is to find the code
that reads `$16(a0)` off the table base - which is what the disassembly in
`orig/sega/src/` is for.

## One thing worth knowing

`PROFILE.INI` (res/data/files/) is in the ROM too, as text, and it is the
PC game's own copy of this table - and the two disagree.  The INI says a
Carryall costs 300 and a Palace 0; the binary table says 800 and 999.

The table below is the one to believe.  Files in this cartridge are opened
by a name the code builds, and there are exactly two places that build
one - "SCEN%c%03d.INI" at $016086 and "%s.EMC" at $016D26.  The words
PROFILE, HOUSE and REGION appear nowhere in the code at all, so those
files are never read: they are the PC original's, carried along and left.
Comparing them against this table is how you see what the Mega Drive
edition changed.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

BUILDINGS = (0x06AFA6, 0x66, 19)
UNITS = (0x06BC00, 0x5C, 27)
HOUSES = (0x06C750, 0x1E, 6)
# The fourteen orders a unit can be under.  Found from the one place that
# reads it - `lea $6CEF8,a0` at $043718, with a stride of twelve worked out
# in three instructions - and the name of order n is the longword four
# bytes *before* its record, which is the tail of the record in front.
ACTIONS = (0x06CEF8, 0x0C, 14)

SPECIAL = {0: "-", 1: "Death Hand", 2: "Fremen", 3: "Saboteur"}


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

    def w(a):
        return int.from_bytes(rom[a:a + 2], "big")

    def lg(a):
        return int.from_bytes(rom[a:a + 4], "big")

    def s(a):
        if not 0 < a < len(rom):
            return "-"
        e = rom.find(b"\0", a)
        return rom[a:e].decode("latin1").strip() if 0 < e - a < 40 else "-"

    # ---------------------------------------------------------- buildings
    base, stride, n = BUILDINGS
    names = [s(lg(base + i * stride + 2)) or "?" for i in range(n)]
    # the two Concrete entries and the two Barracks share a name; the .wsa
    # is what tells them apart, so it goes in the label
    label = []
    for i in range(n):
        wsa = s(lg(base + i * stride + 8))
        label.append(f"{names[i]} ({wsa.split('.')[0]})"
                     if names.count(names[i]) > 1 else names[i])

    def needs(mask):
        got = [label[b] for b in range(n) if mask >> b & 1]
        return ", ".join(got) if got else "-"

    lines = [
        "# buildings.txt - the 19 buildings, from the table at $06AFA6.",
        "#",
        "# Written by tools/sega/sega_data.py.  19 records of $66 bytes.",
        "# Cost, build time and hit points are certain: they are Dune II's",
        "# own numbers.  'needs' is structuresRequired, the longword at",
        "# +$1C (tested whole: `and.l`/`cmp.l $1C(a3)` at $010224 and",
        "# $010C66), a bitmask over this table's own indices - which is how",
        "# the game knows a Refinery wants a Windtrap and a Heavy Factory an",
        "# Outpost, bit 18, in the high word.  Const Yard's $FFFF is 'always'.",
        "#",
        "# 'sight' (+$12) is how far round it the fog lifts: BUILD.EMC's",
        "# routine 15 hands it to $019FFE.  It was once printed twice, as",
        "# a tech level and as a radius; it is only the second.",
        "#",
        "# idx name                  cost  time    hp  sight  campaign",
        "",
    ]
    for i in range(n):
        r = base + i * stride
        lines.append("%3d  %-20s %5d %5d %5d %6d %8d"
                     % (i, label[i], w(r + 0x16), w(r + 0x18), w(r + 0x10),
                        w(r + 0x12), w(r + 0x1A)))
    lines += ["", "# what each one has to be built after", ""]
    for i in range(n):
        r = base + i * stride
        m = lg(r + 0x1C)
        lines.append("%-20s %s" % (label[i],
                                   "always" if m == 0xFFFF else needs(m)))
    lines += ["", "# the columns that are not identified, by offset", "",
              "# idx name                 " +
              "".join("   +%02X" % o for o in (0x0C, 0x0E, 0x14, 0x20))]
    for i in range(n):
        r = base + i * stride
        lines.append("%3d  %-20s %s" % (i, label[i], "".join(
            "%6d" % w(r + o) for o in (0x0C, 0x0E, 0x14, 0x20))))
    (out / "buildings.txt").write_text("\n".join(lines) + "\n")

    # -------------------------------------------------------------- units
    base, stride, n = UNITS
    lines = [
        "# units.txt - the 27 units, from the table at $06BC00.",
        "#",
        "# Written by tools/sega/sega_data.py.  27 records of $5C bytes.",
        "# The last nine are not units anyone builds - rockets, a bullet, a",
        "# sonic blast, the sandworm and the frigate that brings a starport",
        "# order - which is why their cost is zero.",
        "#",
        "# 'turret' is the second sprite a unit draws on top of itself; -1",
        "# means it has none, and the units that have one are exactly the",
        "# ones whose gun turns independently of the hull.",
        "#",
        "# 'sight' (+$12) is how far round it the fog lifts - UNIT.EMC's",
        "# routine 40 hands it to $019FFE; it is not a tech level.",
        "#",
        "# idx name           cost  time    hp sight  speed  sprite turret",
        "",
    ]
    for i in range(n):
        r = base + i * stride
        turret = w(r + 0x48)
        lines.append("%3d  %-14s %5d %5d %5d %5d %6d %7d %6s"
                     % (i, s(lg(r + 2)), w(r + 0x16), w(r + 0x18),
                        w(r + 0x10), w(r + 0x12), w(r + 0x42), w(r + 0x46),
                        "-" if turret == 0xFFFF else turret))
    lines += ["", "# and where its picture came from", ""]
    for i in range(n):
        r = base + i * stride
        lines.append("%-14s %s" % (s(lg(r + 2)), s(lg(r + 8))))
    lines += ["", "# the columns that are not identified, by offset", "",
              "# idx name           " +
              "".join("   +%02X" % o for o in
                      (0x0C, 0x0E, 0x14, 0x1E, 0x20, 0x2E, 0x30, 0x32,
                       0x50, 0x52, 0x54))]
    for i in range(n):
        r = base + i * stride
        lines.append("%3d  %-14s %s" % (i, s(lg(r + 2)), "".join(
            "%6d" % w(r + o) for o in
            (0x0C, 0x0E, 0x14, 0x1E, 0x20, 0x2E, 0x30, 0x32,
             0x50, 0x52, 0x54))))
    (out / "units.txt").write_text("\n".join(lines) + "\n")

    # ------------------------------------------------------------ actions
    base, stride, n = ACTIONS
    lines = [
        "# actions.txt - the fourteen orders a unit can be under.",
        "#",
        "# Written by tools/sega/sega_data.py from the table at $06CEF8,",
        "# which $0436A0 - the routine that gives a unit an order - reads",
        "# with a stride of twelve.  The name of order n is the longword",
        "# four bytes *before* its record; that is where the record in",
        "# front ends, and it is what puts Attack at 0 rather than Move.",
        "#",
        "# Two things say that numbering is right, and neither is a guess:",
        "#",
        "#   * every unit type's default order at +$28 of the unit table",
        "#     comes out sensible - Guard for everything that fights,",
        "#     Stop for the Carryall, the Harvester, the MCV and every",
        "#     projectile, and Attack for the Sandworm, which is the one",
        "#     thing on Arrakis that needs no telling;",
        "#   * the two orders that may interrupt a unit already busy are",
        "#     exactly Die and Destruct.",
        "#",
        "# It is the same numbering the mission files use for a unit's",
        "# starting order, and the same one a script's `act` takes.",
        "#",
        "# idx name          +0  +2    +4     +6   may interrupt a unit",
        "#                                            already busy",
        "",
    ]
    for i in range(n):
        r = base + i * stride
        lines.append("%3d  %-12s %3d %3d %6d  $%04X   %s"
                     % (i, s(lg(r - 4)), w(r), w(r + 2), w(r + 4),
                        w(r + 6), "yes" if w(r) else "-"))
    lines += ["", "# what each unit type does when nothing has told it "
                  "otherwise", ""]
    ub, ustride, un = UNITS
    for i in range(un):
        r = ub + i * ustride
        d = w(r + 0x28)
        lines.append("%3d  %-14s %s"
                     % (i, s(lg(r + 2)),
                        s(lg(base + d * stride - 4)) if d < n else d))
    (out / "actions.txt").write_text("\n".join(lines) + "\n")

    # ------------------------------------------------------------- houses
    base, stride, n = HOUSES
    lines = [
        "# houses.txt - the six houses, from the table at $06C750.",
        "#",
        "# Written by tools/sega/sega_data.py.  Six records of $1E bytes,",
        "# and every field in this one is settled - the values are Dune",
        "# II's own and the prefix really is a letter.",
        "#",
        "# 'toughness' and 'decay' are what make a house feel like itself:",
        "# the Ordos lose a point of health from a building every so often",
        "# (chance 10, amount 1), the Harkonnen far more (85, 2), and the",
        "# Atreides not at all.  'countdown' is how long the house's",
        "# special weapon takes to recharge, which is why a Harkonnen",
        "# Death Hand is rare and an Atreides Fremen call is not.",
        "#",
        "# name        tough  decay  chance  colour  countdown  starport"
        "  prefix  special      mentat",
        "",
    ]
    for i in range(n):
        r = base + i * stride
        ment = w(r + 0x1A)
        lines.append("%-12s %5d %6d %7d %7d %10d %9d %7s  %-12s %s"
                     % (s(lg(r + 2)), w(r + 6), w(r + 0x0A), w(r + 8),
                        w(r + 0x0C), w(r + 0x0E), w(r + 0x10),
                        chr(w(r + 0x12)), SPECIAL.get(w(r + 0x14), "?"),
                        "-" if ment == 0xFFFF else ment))
    lines += [
        "",
        "# The three houses with a mentat are the three you can play.  The",
        "# other three exist so the game can put their units on the map:",
        "# the Fremen the Atreides call in, the Sardaukar the Emperor",
        "# sends, and the Mercenaries, which Dune II never uses.",
        "",
        "# the columns that are not identified, by offset",
        "",
        "# name           +16   +18",
    ]
    for i in range(n):
        r = base + i * stride
        lines.append("%-12s %5d %5d" % (s(lg(r + 2)), w(r + 0x16), w(r + 0x18)))
    (out / "houses.txt").write_text("\n".join(lines) + "\n")

    # ---- the passwords
    #
    # The checker at $0218FE looks the ten letters up in this table and
    # switches on the kind; it does not compute anything, so the table is
    # every password there is.  Kinds 0-2 are a house, and the value is the
    # mission it starts on ($FFC274 and $FFC04C); DEMOLITION really does
    # put the Harkonnen mentat on the screen, which is the check that the
    # kind is the house's index in the table above.
    kinds = {3: "the ending - needs a game in progress ($FFC278)",
             6: "toggles $FFC198: shows the whole map",
             7: "sets the credits to 25000 - needs a game in progress",
             9: "toggles bit 0 of $FFC019 (the word $FFC018 is what is tested): the player's side takes no damage "
                "($046BDE, $00F8F8)",
             10: "shows the version: V2-01179?"}
    houses = ["Harkonnen", "Atreides", "Ordos"]
    lines = ["# passwords.txt - every password the game takes, from the table",
             "# at $08811C: eight bytes a word - a pointer to the ten letters,",
             "# a kind and a value - until a null pointer.",
             "#",
             "# Written by tools/sega/sega_data.py.  The checker at $0218FE",
             "# looks the word up and switches on the kind (the switch at",
             "# $021978); nothing is computed, so this is all of them.",
             "# The letters themselves are at $020C10.",
             "",
             "# word         kind  what"]
    a = 0x08811C
    while lg(a):
        word = s(lg(a))
        kind, value = w(a + 4), w(a + 6)
        what = (f"{houses[kind]}, mission {value}" if kind < 3
                else kinds.get(kind, "?"))
        lines.append(f"{word:<14} {kind:3d}  {what}")
        a += 8
    (out / "passwords.txt").write_text("\n".join(lines) + "\n")

    print(f"19 buildings, 27 units, 6 houses, 14 orders, passwords -> {out}/")


if __name__ == "__main__":
    main()
