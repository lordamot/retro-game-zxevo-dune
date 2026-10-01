#!/usr/bin/env python3
"""sega_scen.py - the 27 missions, read out of the cartridge.

    sega_scen.py [--rom orig/dune2.gen] [--out orig/sega/res/data]

Writes `missions.txt`, and `files/SCEN*.ini` - the mission files put back
into the text they were converted from.

## The format, and how it was settled

On the PC these were text - `SCENA001.INI` and its twenty-six siblings,
with `[BASIC]`, `[MAP]`, a section per house and then lists of units,
structures, teams and reinforcements.  The Mega Drive port converted them
to a tagged binary and kept the shape.  A record is

    tag(word)  payload

where the tag's high byte is the section and the low byte is either an
index or the first letter of the key it came from - which is why $0351 is
"house 3, Quota" and $0947 is "structures, GEN".  The file ends with
$FFFF.

None of that is guessed.  The loader is at **$0161F0** and it is a switch
on the tag's high byte: eleven sections, one handler each, and every
handler says in 68000 how long its record is and what each word in it
means.  Because a handler returns the pointer it has advanced, a record's
length is not a pattern to be found - it is written down in the code:

    section  handler   payload  what it is
      0      $016418   varies   [BASIC]
      1      $016500   varies   [MAP]
      2-5    $0165AC     2      a house's Quota/Credits/Brain/MaxUnit
      6      -           2      [CHOAM]: how many of unit `key` the
                                starport stocks (the handler is four
                                instructions, inline in the switch)
      7      $016650    10      [TEAMS]
      8      $0166CA    12      [UNITS]
      9      $016856   6 or 10  [STRUCTURES], GEN and ID
     10      $016988     8      [REINFORCEMENTS]

The test of the reading is that it comes out even.  Parsing every file
straight through, record after record, all 27 end exactly on their $FFFF
with nothing over - which the previous reading, made by looking for runs
of records whose index counted up at a constant spacing, could not do.
That older reading had the reinforcements down as structures, because a
map position's high byte is $0A and so is the reinforcement tag.

Three things the loader settles that pattern-matching had wrong or could
not reach:

  * **Section 5 is the Sardaukar, not the Fremen.**  $0165AC turns the
    section number into a house through the table at $0714A4, which holds
    0, 1, 2, 4 - and 4 is the Sardaukar.  They appear in exactly three
    missions, the ninth of each campaign, with 9000 to 15500 credits.
  * **Section 6 is CHOAM**, the starport's stock: the key is a unit index
    and the word is how many of it there are.  The eight keys that occur
    are 'Thopter, Launcher, Tank, Siege Tank, Trike, Quad, Harvester and
    MCV, which is Dune II's starport list.
  * **A team's two letters are looked up in the game's own tables** -
    behaviour in the five at $06CE66, movement in the six at $06CE4E -
    and the search takes the first match, so of the two 'W's in the
    movement list only Wheeled can ever be named by a scenario.
"""

import argparse
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Which house a section number means.  The loader reads it out of the
# table at $0714A4 - `lea $714A0,a0; add.w d0,d0; move.w (a0,d0.w),d4`
# with d0 the section - and these are the four words that table holds.
SECTION_HOUSE = {2: 0, 3: 1, 4: 2, 5: 4}
HOUSE_ID = ["Harkonnen", "Atreides", "Ordos", "Fremen", "Sardaukar",
            "Mercenary"]
# The key letters a house record can carry, and the [BASIC] words in the
# order section 0's own jump table takes them.
HOUSE_KEY = {0x51: "Quota", 0x43: "Credits", 0x42: "Brain", 0x4D: "MaxUnit"}
# Keys 7 and 8 are named by what reads them, not by position: 7 goes to
# $FFC062, which game_is_level_won reads - the PC's LoseFlags ("was it
# won?") - and 8 to $FFC060, which game_is_level_finished reads - the PC's
# WinFlags ("is it over?").
BASIC = {3: "Timeout", 4: "MapScale", 5: "CursorPos", 6: "TacticalPos",
         7: "LoseFlags", 8: "WinFlags"}
PICTURE = {0: "LosePicture", 1: "WinPicture", 2: "BriefPicture"}
# [MAP]'s three keys, by the letter $016500 compares against.
# 'B' is the spice blooms (the PC's Bloom=): map_load puts bloom icon $D0
# on each square it lists.
MAP_KEY = {0x42: "Bloom", 0x46: "Field", 0x53: "Seed"}

# The letters at $06CE66 and $06CE4E, with the words they are short for.
# Both lists are searched from the front and stop at the first match, so
# the second 'W' - Winged - is unreachable from a scenario file.
BEHAVIOUR = ["Normal", "Staging", "Flee", "Kamikaze", "Guard"]
BEHAVIOUR_LETTER = "NSFKG"
MOVEMENT = ["Foot", "Tracked", "Harvester", "Wheeled", "Winged", "Slither"]
MOVEMENT_LETTER = "FTHWWS"

# Where a reinforcement comes in.  Only 6 and 7 occur in the 27 files.
LOCATION = {6: "Enemybase", 7: "Homebase"}
# The eight facings a placed unit can have, 32 apart.
COMPASS = {0: "N", 32: "NE", 64: "E", 96: "SE", 128: "S", 160: "SW",
           192: "W", 224: "NW"}


def word(d, i):
    return int.from_bytes(d[i:i + 2], "big")


def parse(d):
    """Every record of a mission file, in the order the loader reads them.

    Returns `(records, ok)` where a record is `(section, key, value)` and
    `ok` says the file ended on its $FFFF with nothing left over.  That
    flag is the whole proof: a wrong length for any one section walks the
    pointer off the records and the file does not come out even.
    """
    out, i, n = [], 0, len(d)
    while i + 2 <= n:
        tag = word(d, i)
        if tag == 0xFFFF:
            return out, i + 2 >= n - 1
        sec, key = tag >> 8, tag & 0xFF
        i += 2
        if sec == 0 and key in PICTURE:
            # $016450: a length word, then that many bytes of NUL-ended name
            ln = word(d, i)
            out.append((sec, key, d[i + 2:i + 2 + ln].split(b"\0")[0]
                        .decode("latin1")))
            i += 2 + ln
        elif sec == 1 and key in (0x42, 0x46):
            # $016520: a count word, then that many words of map position
            ln = word(d, i)
            out.append((sec, key, [word(d, i + 2 + 2 * k)
                                   for k in range(ln)]))
            i += 2 + 2 * ln
        elif sec in (0, 1, 2, 3, 4, 5, 6):
            out.append((sec, key, word(d, i)))
            i += 2
        elif sec in (7, 8, 9, 10):
            ln = {7: 5, 8: 6, 10: 4}.get(sec, 3 if key == 0x47 else 5)
            out.append((sec, key, [word(d, i + 2 * k) for k in range(ln)]))
            i += 2 * ln
        else:
            return out, False
    return out, False


def letter(v):
    return chr(v) if 32 <= v < 127 else f"${v:04X}"


def named(table, letters, v):
    """A team's letter, through the game's own list - first match wins."""
    c = chr(v) if 32 <= v < 127 else None
    k = letters.find(c) if c else -1
    return table[k] if k >= 0 else f"?{letter(v)}"


def ini(name, recs, units, buildings, actions=()):
    """The mission put back into the text it was converted from.

    Nothing here is invented: every key is one the loader compares
    against, and every value is the word that was in the record.
    """
    out = [f"; {name} - written back out of orig/dune2.gen by",
           "; tools/sega/sega_scen.py.  The Mega Drive keeps these as a",
           "; tagged binary; this is the same records as text.", ""]
    by = collections.defaultdict(list)
    for sec, key, v in recs:
        by[sec].append((key, v))

    out.append("[BASIC]")
    for key, v in by[0]:
        out.append(f"{PICTURE.get(key, BASIC.get(key, key))}={v}")
    out.append("")
    if by[1]:
        out.append("[MAP]")
        for key, v in by[1]:
            k = MAP_KEY.get(key, key)
            out.append(f"{k}={v}" if not isinstance(v, list) else
                       f"; {k}: {len(v)} at " +
                       ",".join(str(p) for p in v))
        out.append("")
    for sec in (2, 3, 4, 5):
        if not by[sec]:
            continue
        out.append(f"[{HOUSE_ID[SECTION_HOUSE[sec]]}]")
        for key, v in by[sec]:
            k = HOUSE_KEY.get(key, key)
            out.append(f"{k}={letter(v) if k == 'Brain' else v}")
        out.append("")
    if by[6]:
        out.append("[CHOAM]")
        for key, v in by[6]:
            out.append(f"{units[key] if key < len(units) else key}={v}")
        out.append("")
    if by[7]:
        out.append("[TEAMS]")
        for i, (key, v) in enumerate(by[7], 1):
            house, beh, mov, lo, hi = v
            out.append(f"{i}={HOUSE_ID[house]},"
                       f"{named(BEHAVIOUR, BEHAVIOUR_LETTER, beh)},"
                       f"{named(MOVEMENT, MOVEMENT_LETTER, mov)},{lo},{hi}")
        out.append("")
    if by[8]:
        out.append("[UNITS]")
        for i, (key, v) in enumerate(by[8]):
            house, kind, hp, pos, face, act = v
            out.append(f"ID{i:03d}={HOUSE_ID[house]},"
                       f"{units[kind] if kind < len(units) else kind},"
                       f"{hp},{pos},{face},"
                       f"{actions[act] if act < len(actions) else act}")
        out.append("")
    if by[9]:
        out.append("[STRUCTURES]")
        for key, v in by[9]:
            if key == 0x47:                       # GEN: position, then two
                pos, house, kind = v
                out.append(f"GEN{pos}={HOUSE_ID[house]},"
                           f"{buildings[kind] if kind < len(buildings) else kind}")
            else:                                 # ID: index, and a hit count
                idx, house, kind, hp, pos = v
                out.append(f"ID{idx:03d}={HOUSE_ID[house]},"
                           f"{buildings[kind] if kind < len(buildings) else kind},"
                           f"{hp},{pos}")
        out.append("")
    if by[10]:
        out.append("[REINFORCEMENTS]")
        for i, (key, v) in enumerate(by[10], 1):
            house, kind, where, when = v
            out.append(f"{i}={HOUSE_ID[house]},"
                       f"{units[kind] if kind < len(units) else kind},"
                       f"{LOCATION.get(where, where)},{when >> 8}"
                       f"{'+' if when & 0xFF == 0x2B else ''}")
        out.append("")
    return "\n".join(out) + "\n"


def table_names(path, least=3):
    """The first column of names out of one of sega_data.py's tables."""
    names = []
    if not path.exists():
        return names
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) > least and p[0].isdigit() and int(p[0]) == len(names):
            k = 1
            while k < len(p) and not p[k].lstrip("-").isdigit():
                k += 1
            names.append(" ".join(p[1:k]))
    return names


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

    units = table_names(out / "units.txt")
    buildings = table_names(out / "buildings.txt")
    # the fourteen orders, so a unit's starting order reads as a word;
    # it is the same numbering $0436A0 uses - see actions.txt
    actions = table_names(out / "actions.txt", least=2)

    def order(n):
        return actions[n] if n < len(actions) else str(n)

    files = []
    for line in (out / "files.txt").read_text().splitlines():
        if line.startswith("SCEN"):
            p = line.split()
            files.append((p[0], int(p[1][1:], 16), int(p[2])))
    if not files:
        raise SystemExit("run tools/sega/sega_files.py first")

    lines = [
        "# missions.txt - the 27 missions in orig/dune2.gen.",
        "#",
        "# Written by tools/sega/sega_scen.py.  Nine missions for each of",
        "# the three playable houses, in the tagged binary the Mega Drive",
        "# port converted the PC's SCEN*.INI text into.",
        "#",
        "# Every field below comes from the loader at $0161F0, which is a",
        "# switch on the record tag with one handler per section; each",
        "# handler says how long its record is and what each word in it",
        "# means.  The reading is checked by the files coming out even:",
        "# all 27 parse record after record and end exactly on their",
        "# $FFFF with nothing left over.",
        "#",
        "# 'Brain' is H for the human player and C for the computer, and",
        "# exactly one house in every mission has an H.  Quota is the",
        "# spice the player must harvest to win where there is one; a",
        "# mission with Quota 0 is won by destroying the enemy instead.",
        "",
    ]
    complete = 0
    for name, a, n in files:
        d = rom[a:a + n]
        recs, ok = parse(d)
        complete += ok
        by = collections.defaultdict(list)
        for sec, key, v in recs:
            by[sec].append((key, v))
        head = dict(by[0])
        lines.append(f"== {name}   ${a:06X}  {n} bytes"
                     + ("" if ok else "   ** does not parse **"))
        lines.append(f"   briefing {head.get(2, '-'):<14} "
                     f"win {head.get(1, '-'):<12} lose {head.get(0, '-')}")
        lines.append("   " + "  ".join(f"{BASIC[k]}={head[k]}"
                                       for k in sorted(head) if k in BASIC))
        for sec in (2, 3, 4, 5):
            if not by[sec]:
                continue
            f = {HOUSE_KEY.get(k, k): v for k, v in by[sec]}
            who = "player" if f.get("Brain") == 0x48 else "computer"
            lines.append(f"   {HOUSE_ID[SECTION_HOUSE[sec]]:<10} {who:<8} "
                         f"credits {f.get('Credits', 0):<5} "
                         f"quota {f.get('Quota', 0):<5} "
                         f"max units {f.get('MaxUnit', 0)}")
        for key, v in by[1]:
            if isinstance(v, list) and v:
                lines.append(f"   {MAP_KEY.get(key, key)}: {len(v)} at "
                             + ", ".join(f"{p % 64},{p // 64}" for p in v))
            elif not isinstance(v, list):
                lines.append(f"   {MAP_KEY.get(key, key)}={v}")
        if by[6]:
            lines.append("   the starport stocks: " + ", ".join(
                f"{v} {units[k] if k < len(units) else k}"
                for k, v in by[6]))
        gen = sum(1 for k, _ in by[9] if k == 0x47)
        got = [f"{len(by[7])} teams", f"{len(by[8])} units",
               f"{gen} walls and slabs", f"{len(by[9]) - gen} buildings",
               f"{len(by[10])} reinforcements"]
        lines.append("   " + ", ".join(g for g in got if not g.startswith("0 ")))
        if by[7]:
            lines.append("   teams:")
            for i, (key, v) in enumerate(by[7], 1):
                house, beh, mov, lo, hi = v
                lines.append(
                    f"      {i:2d}  {HOUSE_ID[house]:<10} "
                    f"{named(MOVEMENT, MOVEMENT_LETTER, mov):<9} "
                    f"{named(BEHAVIOUR, BEHAVIOUR_LETTER, beh):<8} "
                    f"{lo} to {hi} units")
        if by[8]:
            lines.append("   units on the map at the start:")
            for i, (key, v) in enumerate(by[8], 1):
                house, kind, hp, pos, face, act = v
                lines.append(
                    f"      {i:2d}  {HOUSE_ID[house]:<10} "
                    f"{(units[kind] if kind < len(units) else kind):<14} "
                    f"at {pos % 64:2d},{pos // 64:<2d}  "
                    f"facing {COMPASS.get(face, face):<2}  "
                    f"health {hp}  {order(act)}")
        ids = [(k, v) for k, v in by[9] if k != 0x47]
        if ids:
            lines.append("   buildings on the map at the start:")
            for idx, house, kind, hp, pos in (v for _, v in ids):
                lines.append(
                    f"      {idx:2d}  {HOUSE_ID[house]:<10} "
                    f"{(buildings[kind] if kind < len(buildings) else kind):<20} "
                    f"at {pos % 64:2d},{pos // 64:<2d}  health {hp}")
        if by[10]:
            lines.append("   reinforcements:")
            for i, (key, v) in enumerate(by[10], 1):
                house, kind, where, when = v
                lines.append(
                    f"      {i:2d}  {HOUSE_ID[house]:<10} "
                    f"{(units[kind] if kind < len(units) else kind):<14} "
                    f"at the {LOCATION.get(where, where):<9} "
                    f"after {when >> 8}"
                    f"{', again and again' if when & 0xFF == 0x2B else ''}")
        lines.append("")
        (out / "files" / f"{name}").with_suffix(".ini").write_text(
            ini(name, recs, units, buildings, actions))

    lines += [
        f"# All {complete} of {len(files)} files parse straight through and",
        "# end on their own $FFFF, which is what says the record lengths",
        "# above are the loader's and not a guess.  The same records are",
        "# written back out as text in files/SCEN*.ini.",
    ]
    (out / "missions.txt").write_text("\n".join(lines) + "\n")
    print(f"{len(files)} missions, {complete} parsed whole "
          f"-> {out}/missions.txt")


if __name__ == "__main__":
    main()
