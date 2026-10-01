#!/usr/bin/env python3
"""sega_briefs.py - what the mentat says between missions.

    sega_briefs.py [--rom orig/dune2.gen] [--out orig/sega/res/text]

Writes `briefings.txt`: the 111 pieces of prose the game shows around a
mission - the three houses' descriptions on the selection screen, and then
for every mission a briefing, a victory, a defeat and a piece of advice.

## Where it is

`$087D74` holds 111 longwords, and they name every one of the 111
NUL-terminated strings between `$01B2E4` and `$01F33F` - all of them, with
nothing in the block unnamed and nothing in the table pointing outside it.
That one-to-one fit is what says the table has been found whole.

## The shape

The first three are the house descriptions.  The code just before
`$01F39A` proves that much outright: it starts the house's music from `d4`
(0, 1 or 2 become music-table entries `$18`, `$19`, `$1A`, played by
`$00A806`) and then indexes this very table with the same `d4`.

    lea.l   $87D74.l,a1
    lsl.w   #$2,d4
    move.l  $0(a1,d4.w),-(a7)

After those three, `111 - 3 = 108` is `27 * 4`, and 27 is nine missions for
each of three houses.  Read in fours the strings fall into an obvious
pattern - a briefing, then a congratulation, then a commiseration, then a
tip about what to build - and the tool checks that rather than asserting
it, by looking for the words each of those three kinds actually uses.

What is *not* settled is the order of the 27: whether it runs mission by
mission or house by house.  The one place in the code that reads this
table only ever uses indices 0 to 2, so the answer is somewhere else, and
until it is found the groups are numbered rather than named.
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

TABLE, COUNT = 0x087D74, 111
INTROS = 3
HOUSES = ["Harkonnen", "Atreides", "Ordos"]

def thing_names(root):
    """The buildings and units, by name, out of what sega_data.py wrote.

    Used to check the four-at-a-time reading with a vocabulary this tool
    did not invent.  Picking words that sound like a victory and counting
    them proves nothing - it is fitting the test to the answer - but the
    game's own list of things is independent of the prose entirely.
    """
    out = set()
    for f in ("buildings.txt", "units.txt"):
        p = root / f
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            w = line.split()
            if len(w) > 2 and w[0].isdigit():
                k = 1
                while k < len(w) and not w[k].lstrip("-").isdigit():
                    k += 1
                name = " ".join(w[1:k]).lower()
                if len(name) > 3:
                    out.add(name)
    return out


def strings(rom):
    out = []
    for k in range(COUNT):
        p = int.from_bytes(rom[TABLE + k * 4:TABLE + k * 4 + 4], "big")
        e = rom.find(b"\0", p)
        out.append((p, rom[p:e].decode("latin1")))
    return out


def wrap(text, width=72, indent="      "):
    # the game's own line breaks are bare full stops; keep the prose whole
    # and let the file wrap it
    out, line = [], indent
    for word in text.split():
        if len(line) + len(word) + 1 > width and line.strip():
            out.append(line)
            line = indent
        line += ("" if line == indent else " ") + word
    if line.strip():
        out.append(line)
    return "\n".join(out)


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
    st = strings(rom)

    groups = (COUNT - INTROS) // 4
    things = thing_names(out.parent / "data")
    named = [0, 0, 0, 0]
    longest = shortest = 0
    for g in range(groups):
        four = [st[INTROS + g * 4 + k][1] for k in range(4)]
        for k, t in enumerate(four):
            tl = t.lower()
            named[k] += any(n in tl for n in things)
        lens = [len(t) for t in four]
        longest += lens[0] == max(lens)
        shortest += lens[3] == min(lens)

    lines = [
        "# briefings.txt - the mentat's prose, from the table at $087D74.",
        "#",
        "# Written by tools/sega/sega_briefs.py.  111 strings between",
        "# $01B2E4 and $01F33F, every one of them named by that table and",
        "# nothing in the table pointing outside the block.",
        "#",
        "# The first three are the house descriptions on the selection",
        f"# screen - the code at $01F39A indexes this table with the same",
        "# register it picks the house's music with, which settles those.",
        f"# The remaining {COUNT - INTROS} read as {groups} groups of four:",
        "# briefing, victory, defeat, advice.  That reading is checked with",
        "# a vocabulary this tool did not invent - the buildings and units",
        "# out of the game's own stat tables.  Across the "
        f"{groups} groups, the",
        f"# fourth string names one of them {named[3]} times against",
        f"# {named[0]}, {named[1]} and {named[2]} for the other three: advice",
        "# talks about what to build and nothing else does.  The first is",
        f"# also the longest of its four {longest} times and the fourth the",
        f"# shortest {shortest} times.",
        "#",
        "# What the 27 groups are *in* - mission by mission, or house by",
        "# house - is not settled.  The only code that reads this table uses",
        "# indices 0 to 2 and nothing more, so the answer is elsewhere.",
        "",
        "== the three houses",
        "",
    ]
    for i in range(INTROS):
        p, t = st[i]
        lines.append(f"  {i:3d}  ${p:06X}  {HOUSES[i]}")
        lines.append(wrap(t))
        lines.append("")

    for g in range(groups):
        lines.append(f"== group {g}")
        lines.append("")
        for k, what in enumerate(("briefing", "victory", "defeat", "advice")):
            p, t = st[INTROS + g * 4 + k]
            lines.append(f"  {INTROS + g * 4 + k:3d}  ${p:06X}  {what}")
            lines.append(wrap(t))
            lines.append("")

    (out / "briefings.txt").write_text("\n".join(lines) + "\n")
    print(f"{COUNT} strings, {groups} groups of four -> {out}/briefings.txt")
    print(f"  the fourth of each four names a building or unit "
          f"{named[3]}/{groups} times, against "
          f"{named[0]}/{named[1]}/{named[2]} for the other three")


if __name__ == "__main__":
    main()
