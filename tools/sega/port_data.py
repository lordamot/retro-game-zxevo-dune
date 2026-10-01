#!/usr/bin/env python3
"""port_data.py - the game's data out of the cartridge, into readable text.

    port_data.py [extract]     orig/dune2.gen -> src/res/data/  (run once)
    port_data.py check         prove src/res/data/ and tools/dune_data.py
                               against the cartridge, and assemble every
                               include file with sjasmplus

`extract` writes everything the port needs from `orig/` as text under
`src/res/data/`; from then on the build reads only that text
(`tools/dune_data.py`).  The text is the source: nothing reads `orig/`
again, except `check`, which is how the text is known to say what the
cartridge says:

  * every record and constant table: `dune_data.py` is run, `tables.inc`
    is assembled by sjasmplus, and the bytes under each `tbl_*` label are
    compared with the ROM's, each field put back into the ROM's byte
    order and every pointer resolved to the index the text gives it;
  * the three scripts assemble to exactly the cartridge's bytecode and
    entry tables;
  * the 27 missions encode to exactly the cartridge's record streams;
  * the 27 maps and every string are byte for byte the cartridge's;
  * a test file includes each .inc into a DEVICE ZXSPECTRUM4096 page.

Where each table is and what it means comes from the specs
(`orig/sega/spec/S1-S10`) and `orig/sega/regions.txt`; each table in the
text says its address.  See `.claude/docs/port.md`.
"""

import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

import dune_data  # noqa: E402

ROM_PATH = ROOT / "orig/dune2.gen"
OUT = ROOT / "src/res/data"
TMP = ROOT / "tmp/port-data"
SJASM = ROOT / "bin/sjasmplus/sjasmplus"

ROM = ROM_PATH.read_bytes()


def w(a):
    return int.from_bytes(ROM[a:a + 2], "big")


def sw(a):
    v = w(a)
    return v - 0x10000 if v & 0x8000 else v


def lg(a):
    return int.from_bytes(ROM[a:a + 4], "big")


def cstr(a):
    e = ROM.index(b"\0", a)
    return ROM[a:e]


def regions():
    out = []
    for line in (ROOT / "orig/sega/regions.txt").read_text().splitlines():
        m = re.match(r"\$([0-9A-F]{6})-\$([0-9A-F]{6})", line)
        if m:
            out.append((int(m[1], 16), int(m[2], 16)))
    return out


REGIONS = regions()


def within_region(a, n):
    """A table must sit inside one named region of the cartridge."""
    return any(s <= a and a + n - 1 <= e for s, e in REGIONS)


# ------------------------------------------------------------ identifiers
#
# The words the text uses for the things the tables list, so a mission
# says "Tank" and not 9.  Unique, and one word each.

UNIT_IDS = ["Carryall", "Thopter", "Infantry", "Troopers", "Soldier",
            "Trooper", "Saboteur", "Launcher", "Deviator", "Tank",
            "SiegeTank", "Devastator", "SonicTank", "Trike", "RaiderTrike",
            "Quad", "Harvester", "MCV", "DeathHand", "Rocket", "ARocket",
            "GRocket", "MiniRocket", "Bullet", "SonicBlast", "Sandworm",
            "Frigate"]
STRUCT_IDS = ["Slab", "Slab4", "Palace", "LightFactory", "HeavyFactory",
              "HiTech", "IX", "WOR", "ConstYard", "Windtrap", "Barracks",
              "Starport", "Refinery", "Repair", "Wall", "Turret", "RTurret",
              "Silo", "Outpost"]
HOUSE_IDS = ["Harkonnen", "Atreides", "Ordos", "Fremen", "Sardaukar",
             "Mercenary"]
ORDER_IDS = ["Attack", "Move", "Retreat", "Guard", "AreaGuard", "Harvest",
             "Return", "Stop", "Ambush", "Sabotage", "Die", "Hunt", "Deploy",
             "Destruct"]
LANDSCAPE_IDS = ["Sand", "PartialRock", "Dune", "PartialDune", "Rock",
                 "MostlyRock", "Mountain", "PartialMountain", "Spice",
                 "ThickSpice", "Concrete", "Wall", "Structure",
                 "DestroyedWall", "Bloom"]

# ----------------------------------------------------------- record tables
#
# (offset, type, name, comment).  A name is the specs' where a spec names
# the field (the spec is given); `fXX` is a field no spec names, with what
# is known about it in the comment.  "PC" is OpenDUNE's name for the field
# at the same place, where the values agree with it - a hint, not a claim.

OBJECT_HEAD = [
    (0x00, "w", "f00", "PC stringID_abbrev"),
    (0x02, "str", "name", "the name (units.txt, buildings.txt)"),
    (0x06, "w", "f06", "PC stringID_full"),
    (0x08, "str", "wsa", "the PC picture file it was drawn from"),
]

UNIT_FIELDS = OBJECT_HEAD + [
    (0x0C, "hw", "objectFlags", "S4/S1: bit 6 hasTurret, 11 scriptNoSlowdown, 12 targetAir, 13 priority"),
    (0x0E, "w", "spawnChance", "S4: chance in 256 that a Soldier survives the unit"),
    (0x10, "w", "hitpoints", "S3/S4"),
    (0x12, "w", "sight", "S8: how far round it the fog lifts"),
    (0x14, "w", "f14", "PC spriteID"),
    (0x16, "w", "buildCredits", "S4/S6: the cost"),
    (0x18, "w", "buildTime", "S6: in build ticks"),
    (0x1A, "w", "availableCampaign", "S6 (ObjectInfo)"),
    (0x1C, "hl", "structuresRequired", "S6: a bit per structure type"),
    (0x20, "b", "sortPriority", "S6/S10: the build panel's order"),
    (0x21, "b", "upgradeLevelRequired", "S6"),
    (0x22, "w", "f22", "PC actionsPlayer[0]"),
    (0x24, "w", "f24", "PC actionsPlayer[1]"),
    (0x26, "w", "f26", "PC actionsPlayer[2]"),
    (0x28, "w", "actionPlayer", "S7: the player's units' default order"),
    (0x2A, "w", "f2A", ""),
    (0x2C, "w", "f2C", "PC hintStringID"),
    (0x2E, "w", "priorityBuild", "S4/S6/S7"),
    (0x30, "w", "priorityTarget", "S4/S6"),
    (0x32, "hb", "availableHouse", "S6: a bit per house"),
    (0x33, "b", "f33", ""),
    (0x34, "w", "indexStart", "S2: first unit slot of the type"),
    (0x36, "w", "indexEnd", "S2: last unit slot of the type"),
    (0x38, "hw", "flags", "S3/S4: 1 isBullet, 2 explodeOnDeath, 3 sonicProtection, 4 canWobble, 5 isTracked, 6 isGroundUnit, 7 mustStayInMap, 10 firesTwice, 11 impactOnSand, 12 isNotDeviatable, 13 hasAnimationSet, 14 notAccurate, 15 isNormalUnit"),
    (0x3A, "w", "dimension", "S3/S8: sprite size; dimension + 3 pixels of squares"),
    (0x3C, "w", "f3C", ""),
    (0x3E, "w", "movementType", "S3: 0 foot, 1 tracked, 2 harvester, 3 wheeled, 4 winger, 5 slither"),
    (0x40, "w", "animationSpeed", "S1/S3"),
    (0x42, "w", "movingSpeedFactor", "S3"),
    (0x44, "w", "turningSpeed", "S3"),
    (0x46, "w", "f46", "units.txt 'sprite'; PC groundSpriteID"),
    (0x48, "sw", "f48", "units.txt 'turret' sprite, -1 none; PC turretSpriteID"),
    (0x4A, "sw", "actionAI", "S7: the computer's units' default order"),
    (0x4C, "w", "f4C", "PC displayMode"),
    (0x4E, "w", "f4E", "PC destroyedSpriteID"),
    (0x50, "w", "fireDelay", "S4: reload is twice this"),
    (0x52, "w", "fireDistance", "S4: in squares"),
    (0x54, "w", "damage", "S4"),
    (0x56, "sw", "explosionType", "S3/S4"),
    (0x58, "sw", "bulletType", "S4: the projectile unit type, -1 none"),
    (0x5A, "sw", "bulletSound", "S4/S10: an effect id (tbl_effect_song)"),
]

STRUCT_FIELDS = OBJECT_HEAD + [
    (0x0C, "hw", "flags", "S6/S3/S5: bit 1 factory, 3 a slab (MD), 4 busyStateIsIncoming, 7 conquerable"),
    (0x0E, "w", "spawnChance", "S4: chance at +$E that a Soldier is left"),
    (0x10, "w", "hitpoints", "S5/S6"),
    (0x12, "w", "sight", "S8"),
    (0x14, "w", "f14", "PC spriteID"),
    (0x16, "w", "buildCredits", "S6"),
    (0x18, "w", "buildTime", "S6: in build ticks"),
    (0x1A, "w", "availableCampaign", "S6: offered from campaign n - 1"),
    (0x1C, "hl", "structuresRequired", "S6: a longword; bit 18 the Outpost"),
    (0x20, "b", "sortPriority", "S6"),
    (0x21, "b", "upgradeLevelRequired", "S6"),
    (0x22, "w", "f22", "PC actionsPlayer[0]"),
    (0x24, "w", "f24", "PC actionsPlayer[1]"),
    (0x26, "w", "f26", "PC actionsPlayer[2]"),
    (0x28, "w", "f28", "PC actionsPlayer[3]"),
    (0x2A, "w", "f2A", ""),
    (0x2C, "w", "f2C", "PC hintStringID"),
    (0x2E, "w", "priorityBuild", "S6"),
    (0x30, "w", "priorityTarget", "S6"),
    (0x32, "hb", "availableHouse", "S6: a bit per house"),
    (0x33, "b", "f33", ""),
    (0x34, "hl", "enterFilter", "S3: a bit per unit type that may enter"),
    (0x38, "w", "creditsStorage", "S5"),
    (0x3A, "sw", "powerUsage", "S5: negative produces"),
    (0x3C, "w", "layout", "S6/S8: index into the tbl_layout_* tables"),
    (0x3E, "w", "f3E", "PC iconGroup"),
    (0x40, "ref*3:struct_anim", "animation", "S6: three animation scripts, word index into tbl_struct_anim"),
    (0x4C, "sw*10", "buildableUnits", "S6: -1 unused; read for Barracks and WOR"),
    (0x60, "w*3", "upgradeCampaign", "S6"),
]

HOUSE_FIELDS = [
    (0x00, "w", "f00", ""),
    (0x02, "str", "name", "S9: the first letter names the SCEN file"),
    (0x06, "w", "toughness", "S4"),
    (0x08, "w", "degradingChance", "S2/S4"),
    (0x0A, "w", "degradingAmount", "S4"),
    (0x0C, "w", "f0C", "houses.txt 'colour'; PC minimapColour"),
    (0x0E, "w", "specialCountDown", "S4"),
    (0x10, "w", "starportDeliveryTime", "S4/S6"),
    (0x12, "w", "prefixChar", "houses.txt 'prefix'"),
    (0x14, "w", "specialWeapon", "S4: 1 Death Hand, 2 Fremen, 3 Saboteur"),
    (0x16, "w", "f16", ""),
    (0x18, "w", "f18", ""),
    (0x1A, "sw", "f1A", "houses.txt 'mentat': the mentat's music track, -1 none"),
    (0x1C, "w", "f1C", ""),
]

LANDSCAPE_FIELDS = [
    (0x00, "hw", "f00", ""),
    (0x02, "hw", "f02", ""),
    (0x04, "b*6", "movementSpeed", "S3: by movementType; 0 impassable"),
    (0x0A, "w", "letUnitWobble", "S3"),
    (0x0C, "w", "isValidForStructure", "S3/S6/S8: a building may stand here"),
    (0x0E, "w", "isSand", "S3/S8"),
    (0x10, "w", "isValidForStructure2", "S3/S6/S8: a slab may go here"),
    (0x12, "sw", "spice", "S3/S5: -1 sand, dunes and bloom, 0 rock, 25 spice, 100 thick"),
    (0x14, "w", "craterType", "S8: 0 none, 1 sand, 2 rock (through tbl_crater)"),
    (0x16, "sw", "radarColour", "S3/S8: the PC's; unused on the Mega Drive"),
    (0x18, "w", "spriteID", "S3/S8: the PC's; unused on the Mega Drive"),
    (0x1A, "w", "f1A", ""),
]

ACTION_FIELDS = [
    (0x00, "str", "name", "the name is the longword 4 bytes before $06CEF8 + 12n"),
    (0x04, "w", "f00", "1: may interrupt a unit already busy (Die, Destruct); PC switchType"),
    (0x06, "w", "f02", "1 Attack/Move, 3 the rest; PC selectionType"),
    (0x08, "w", "f04", "PC soundID (a feedback voice id)"),
    (0x0A, "hw", "f06", "PC stringID"),
]

RECORDS = [
    # file, table, rom, count, size, prefix, idprefix, ids, fields, anchor, doc
    ("units", "unit_info", 0x06BC00, 27, 0x5C, "UI_", "UNIT_", UNIT_IDS,
     UNIT_FIELDS, None,
     ["The 27 unit types (S2-S7).  ROM pointers to each record are at",
      "$06C5B4; here index a record as tbl_unit_info + UNIT_INFO_SIZE * type."]),
    ("structures", "struct_info", 0x06AFA6, 19, 0x66, "SI_", "STRUCT_",
     STRUCT_IDS, STRUCT_FIELDS, None,
     ["The 19 structure types (S6).  ROM pointers at $06B94C."]),
    ("houses", "house_info", 0x06C750, 6, 0x1E, "HI_", "HOUSE_", HOUSE_IDS,
     HOUSE_FIELDS, None, ["The six houses (S4, S9)."]),
    ("landscape", "landscape", 0x06CCAA, 15, 28, "LS_", "LST_",
     LANDSCAPE_IDS, LANDSCAPE_FIELDS, None,
     ["The 15 landscape types, 28 bytes each (S3, S6, S8).",
      "The record starts at $06CCAA, not $06CCAE: the region is",
      "$06CCAA-$06CE4D, 15 x 28 exactly, ending where the movement-letter",
      "pointers begin; $06CCAE is the movementSpeed array at +4, which is",
      "why S3 and S8 count their offsets from there (S3's +$06 is +$0A",
      "here) and S6 counts from $06CCAA.  +0 and +2 are read by nothing",
      "the specs name."]),
    ("actions", "actions", 0x06CEF4, 14, 12, "ACT_", "ORDER_", ORDER_IDS,
     ACTION_FIELDS, 0x06CEF8,
     ["The fourteen orders (actions.txt).  The code reads records at",
      "$06CEF8 + 12n; the name of order n is the longword 4 bytes before.",
      "tbl_actions is that $06CEF8, so ACT_name is -4; tbl_actions_start",
      "is the name of order 0."]),
]


TITLES = {"units": "the 27 unit types, the table at $06BC00",
          "structures": "the 19 structure types, the table at $06AFA6",
          "houses": "the six houses, the table at $06C750",
          "landscape": "the 15 landscape types, the table at $06CCAA",
          "actions": "the fourteen orders, the table at $06CEF4"}


def field_size(typ):
    t, _, cnt = typ.partition(":")[0].partition("*")
    return dune_data.SIZE["ref" if t.startswith("ref") else t] * int(cnt or 1)


def fmt(typ, a, table_rom=None):
    """The value of one field element at ROM address a, as text."""
    t = typ.split(":")[0]
    if t == "b":
        return str(ROM[a])
    if t == "sb":
        v = ROM[a]
        return str(v - 256 if v > 127 else v)
    if t == "hb":
        return f"${ROM[a]:02X}"
    if t == "w":
        return str(w(a))
    if t == "sw":
        return str(sw(a))
    if t == "hw":
        return f"${w(a):04X}"
    if t == "l":
        return str(lg(a))
    if t == "sl":
        v = lg(a)
        return str(v - (1 << 32) if v >> 31 else v)
    if t == "hl":
        return f"${lg(a):08X}"
    if t == "pos":
        return f"{sw(a)},{sw(a + 2)}"
    if t == "str":
        return quote(cstr(lg(a)))
    if t == "ref":
        target = typ.split(":", 1)[1]
        p = lg(a)
        if p == 0:
            return "none"
        base, size = TARGETS[target]
        assert (p - base) % size == 0 and p >= base, (typ, hex(p))
        if target.startswith("@"):
            return str((p - base) // size)
        return f"{target}[{(p - base) // size}]"
    if t == "chr":
        s = cstr(lg(a))
        assert len(s) == 1
        return f"'{s.decode()}'"
    raise ValueError(typ)


def quote(bs):
    out = '"'
    for b in bs:
        c = chr(b)
        if c in '"\\':
            out += "\\" + c
        elif 32 <= b < 127:
            out += c
        elif b == 10:
            out += "\\n"
        else:
            out += f"\\x{b:02X}"
    return out + '"'


def split_type(typ):
    t, _, target = typ.partition(":")
    assert target.count(":") == 0
    base, _, cnt = t.partition("*")
    return base, int(cnt or 1), target


def write_records():
    for (fname, table, rom, count, size, prefix, idprefix, ids, fields,
         anchor, doc) in RECORDS:
        assert within_region(rom, count * size), table
        assert sum(field_size(f[1]) for f in fields) == size, table
        lines = [f"# {fname}.txt - {TITLES[fname]}",
                 "#",
                 "# Written once by tools/sega/port_data.py from orig/dune2.gen;",
                 "# this text is now the source, compiled by tools/dune_data.py.",
                 "# The format is in the header of src/res/data/tables.txt.",
                 "", f"table {table}"]
        lines += [f"# {d}" for d in doc]
        lines += [f"rom ${rom:06X}", f"count {count}", f"size ${size:02X}",
                  f"prefix {prefix}", f"idprefix {idprefix}"]
        if anchor is not None:
            lines.append(f"anchor ${anchor:06X}")
        for off, typ, name, com in fields:
            base, cnt, target = split_type(typ)
            t = base + (f"*{cnt}" if cnt > 1 else "")
            nm = name + (f":{target}" if target else "")
            lines.append(f"field ${off:02X} {t:<6} {nm}".rstrip()
                         if not com else
                         f"field ${off:02X} {t:<6} {nm:<22} ; {com}")
        lines += ["", "records"]
        for i in range(count):
            r = rom + i * size
            lines.append(f"record {i} {ids[i]}")
            for off, typ, name, _ in fields:
                base, cnt, target = split_type(typ)
                el = dune_data.SIZE[base]
                vals = [fmt(base + (f":{target}" if target else ""),
                            r + off + k * el) for k in range(cnt)]
                lines.append(f"  {name} = {' '.join(vals)}")
        lines.append("end")
        (OUT / f"{fname}.txt").write_text("\n".join(lines) + "\n")


# -------------------------------------------------------- constant tables
#
# (name, rom, fields, count, doc).  fields: [(name, type)] - a type may be
# `t*n`.  Each is checked to lie inside one of the cartridge's named
# regions.  One table per line of the specs' "tables" sections, and the
# ones the code beside them reads.

SMALL = [
    ("# ---- the map and the ground (S3, S5, S8)",),
    ("icon_landscape", 0x005818, [("type", "sb")], 360,
     "S3/S5/S8: the landscape type (tbl_landscape) of each of the 360 map icons, -1 for icons that are not ground; map_get_landscape_type $0057E6 looks up the ground icon, and the overlay icon wins when it gives 13"),
    ("icon_map", 0x04AA28, [("word", "w")], 480,
     "S8: ICON.MAP - 27 word offsets (in words from the start) to the groups, then the groups' icon numbers"),
    ("playable_area", 0x06CE7A, [("x0", "w"), ("y0", "w"), ("width", "w"), ("height", "w")], 2,
     "S3/S8: the playable area per mapScale (0: 64 x 64, 1: 32 x 32); map_is_valid_position $005798"),
    ("scale_offset", 0x0714A0, [("offset", "w")], 2,
     "S8/S9: added to a square of a mission file per mapScale: 0, and $410 (16 rows and 16 columns in)"),
    ("section_house", 0x0714A4, [("house", "w")], 8,
     "S9: the house of mission-file section s is tbl_section_house[s - 2] (the loader indexes from $0714A0, so this continues tbl_scale_offset): 0, 1, 2, 4"),
    ("crater", 0x0C7EDC, [("base", "sw")], 3,
     "S8: by landscape craterType: -1 never scarred, else compared with the fog icons; map_explosion_ground $0273EA"),
    ("overlay_stamp", 0x00B142, [("flag", "b")], 128,
     "S8: per overlay value 0-127 of a map animation: 1 means the icon is stamped over every square of a structure layout ($00B0C2)"),
    ("tile_step_dir8", 0x012A9C, [("step", "sw")], 8,
     "S3: the square offset of each of the eight directions, N first and clockwise"),
    ("direction_packed", 0x0115A2, [("heading", "sw")], 16,
     "S3: tile_direction_packed $01152A - the heading for four bits dy<=0 (8), dx<=0 (4), |dy|>2|dx| (2), |dx|>2|dy| (1); -1 where 2 and 1 are both set"),
    ("map_pos_step_x", 0x0714C6, [("dx", "sw")], 8,
     "S3: map_pos_step $019AD8 - the x step of the eight directions, 1/256 squares"),
    ("map_pos_step_y", 0x0714D6, [("dy", "sw")], 8,
     "S3: the y step of the eight directions"),
    ("path_smooth", 0x06C748, [("fold", "sb")], 8,
     "S3: path_smooth $012E62 - by the difference of two directions"),
    ("spice_ring", 0x0714F2, [("dx", "sw"), ("dy64", "sw")], 24,
     "S5: map_find_spice - (x, y*64) square offsets: the eight around a square, then the sixteen around those"),
    ("spice_nesw", 0x071562, [("step", "sw")], 4,
     "S5: N E S W as square offsets, read by $01A720 (map_fix_spice_edges)"),
    ("fog_nesw", 0x07156A, [("step", "sw")], 4,
     "S8: the same four offsets, read by $01AB5C (map_update_fog_edge)"),
    ("neighbour8", 0x0C7EBC, [("dx", "sw"), ("dy64", "sw")], 8,
     "S8: a square's eight neighbours as (dx, dy*64), NW clockwise to W; summed per step at $0273B2"),
    ("neighbour9", 0x0FEE6C, [("step", "sw")], 9,
     "the square and its eight neighbours as square offsets, read at $048D5C"),
    ("mcv_squares", 0x0FEE20, [("step", "sw")], 4,
     "S6: where a deploying MCV tries its Construction Yard: 0, -1, -64, -65 ($045E64)"),
    ("square_sample", 0x06C826, [("offset", "pos*8")], 32,
     "S3: unit_update_map - eight (y, x) offsets per object size n (15-32 pixels), each visited square; $019F74"),
    ("square_sample_half", 0x06CC26, [("half", "pos")], 33,
     "S3: the half size (y, x) subtracted from the position first; $019F70"),

    ("# ---- structures (S6, S8)",),
    ("layout_tiles", 0x06B738, [("step", "sw*9")], 7,
     "S6: struct_place - the square offsets of each layout (unused slots 0)"),
    ("layout_edge", 0x06B7B6, [("step", "sw*8")], 7,
     "per layout, eight square offsets by direction (PC layoutEdgeTiles; no reader named in the specs)"),
    ("layout_count", 0x06B826, [("squares", "w")], 7,
     "S6: the number of squares of each layout"),
    ("layout_around", 0x06B834, [("step", "sw*16")], 7,
     "S6: the squares around each layout, 0 ends (the 3x3 fills all sixteen)"),
    ("layout_size", 0x06B914, [("width", "w"), ("height", "w")], 7,
     "per layout, (width, height) in squares (PC layoutSize)"),
    ("layout_centre", 0x06B930, [("centre", "pos")], 7,
     "S8: added to a structure's position (y, x) for its centre - the fog is lifted from there"),
    ("layout_centre8", 0x02E2CE, [("centre", "pos")], 8,
     "S2: ref_position $02E256 - the same by layout & 7, the eighth (none) 0"),
    ("layout_bottom", 0x00B3D0, [("dy", "w")], 8,
     "how far down a layout's bottom row's centre is, in pixels"),
    ("layout_cursor", 0x0C7EE2, [("shape", "w")], 14,
     "S10: the placement cursor for each layout, then the seven for a place that will not do ($028644)"),
    ("layout_cursor_frame", 0x0C7EFE, [("frame", "w")], 8,
     "S10: a number per layout handed with the cursor frame ($0286AC)"),
    ("slab_bits", 0x06BBBE, [("bit", "b")], 4,
     "S6: struct_check_location - 1, 2, 4, 8, one per neighbour"),
    ("slab_flags", 0x06BBC2, [("flag", "b*12")], 4,
     "S6: struct_check_location - a row of 12 flags per neighbour ($00F3C4)"),
    ("wall_nesw", 0x06BA6C, [("step", "sw")], 4,
     "the four neighbours N E S W, read by $00EE4C (wall joining)"),
    ("wall_mask", 0x06BA74, [("mask", "b")], 256,
     "the 256-byte neighbour-mask table $00EDCC copies to RAM (wall joining)"),
    ("wall_mask_values", 0x06BB74, [("mask", "b")], 74,
     "74 mask values: $00EDEE writes each one's index into the RAM copy of tbl_wall_mask"),
    ("struct_icon_sets", 0x06BA0C, [("icon", "w*4"), ("zero", "w*4")], 6,
     "6 records: four icon numbers and four zero words, read by $00D800 and $00D89E-$00DA82"),
    ("struct_pos_offsets", 0x06B9FC, [("offset", "pos")], 4,
     "four (y, x) offsets added to a map position by $00DB94"),
    ("struct_anim_numbers", 0x06BBF2, [("anim", "w")], 7,
     "S6/S8: seven map-icon animation numbers ($2E, 0, 0, $2D, 0, $2C, $2B) that $00F7C2 hands to map_anim_start"),
    ("struct_anim", 0x06AE28, [("word", "hw")], 191,
     "S6: the structure animation scripts, in the PC's opcodes (top nibble 1 abort, 3 pause, 4 rewind, 6 ground tile, 7 jump back); struct_info +$40 points into them"),

    ("# ---- objects and sides (S2, S4, S7)",),
    ("unit_side_list", 0x02056E, [("counted", "b")], 28,
     "S2: per unit type (and one over): 1 joins a side list and is counted"),
    ("struct_side_list", 0x0204D0, [("list", "sb")], 20,
     "S2: per structure type (and one over): 0 slabs and wall, -1 turrets, 1 the rest"),
    ("house_side", 0x023750, [("side", "sb")], 6,
     "S2: house_are_allied $023720 - each house's side, -1 0 -1 +1 -1 -1"),
    ("team_actions", 0x06CE66, [("letter", "chr")], 5,
     "S7/S9: the team behaviours' letters N S F K G (ROM: pointers to one-letter strings; here the letters)"),
    ("movement_letters", 0x06CE4E, [("letter", "chr")], 6,
     "S7/S9: the movement types' letters F T H W W S (ROM: pointers; here the letters) - the first match wins"),
    ("death_hand", 0x0FEE28, [("dx", "sw"), ("dy", "sw")], 17,
     "S4: the Death Hand's blast - 17 (x, y) offsets in 1/256 squares: the centre, eight at one square, eight at two ($0464E4)"),
    ("fremen_types", 0x095CD0, [("type", "w")], 4,
     "S4: the Fremen a Palace sends: one of these unit types at random for each"),
    ("fremen_count", 0x095CD8, [("count", "b")], 16,
     "S4: how many Fremen, by the sum of bytes 3 and 5 of $FFBE5C"),

    ("# ---- the radar (S8)",),
    ("radar_icon_colour", 0x005256, [("colour", "sb")], 360,
     "S8: radar colour of each map icon; a positive overlay entry wins, -1 is left to the unit check"),
    ("radar_house_colour", 0x00524E, [("colour", "b")], 8,
     "S8: a unit's or structure's radar colour by house: 4 7 6 9 13 0"),
    ("radar_house_pixels", 0x00543C, [("pixel", "hb")], 12,
     "S8: three house-colour pixel longwords (4 bits a pixel) for rows 0 and 63"),
    ("radar_border_colour", 0x0054C0, [("colour", "b")], 8,
     "S8: the first and last pixel of each radar row by the player's house"),

    ("# ---- sound (S1, S10)",),
    ("effect_song", 0x06A876, [("song", "sb")], 66,
     "S10: snd_play_effect - effect id 0-$40 to song, -1 none (the 66th is never read)"),
    ("music", 0x06A8B8, [("song", "sw"), ("frames", "sw")], 39,
     "S1/S10: snd_play_music - track to (song, frames to play it or -1)"),
    ("voice_song", 0x06A954, [("song", "sb")], 96,
     "S10: snd_play_voice - feedback id 0-$5D to song, -1 none; then two zero bytes"),
    ("song_start_now", 0x02DD54, [("mode", "b")], 90,
     "S10: snd_play - per song 0-89: nonzero starts it at once, 0 queues it for the vertical blank"),

    ("# ---- animations (S4, S8)",),
    ("icon_anim_ptr", 0x06A9B4, [("script", "ref:icon_anim")], 64,
     "S8: map_anim_start - animation number & $3F to its script, a word index into tbl_icon_anim"),
    ("icon_anim", 0x06AAB4, [("word", "sw")], 442,
     "S8: the map-icon animation scripts: (icon, frames) word pairs ended by (0, -1)"),
    ("effect_ptr", 0x0C80A2, [("script", "ref:effect_scripts")], 24,
     "S4: the effect scripts by number, a word index into tbl_effect_scripts"),
    ("effect_scripts", 0x0C7F0E, [("word", "sw")], 202,
     "S4: 24 effect scripts: (animation-table index, frames) word pairs, each ended by (0, -1)"),
    ("unit_frame_8", 0x06C640, [("frame", "w"), ("flip", "w")], 8,
     "(frame, flip) per facing: $012458 picks a unit's sprite frame and flip"),
    ("unit_frame_8b", 0x06C660, [("frame", "w"), ("flip", "w")], 8,
     "(frame, flip) per facing, for another kind of unit; $0123DC"),
    ("unit_frame_16", 0x06C680, [("frame", "w"), ("flip", "w")], 16,
     "16 (frame, flip) pairs; $012320"),
    ("infantry_walk", 0x06C6C0, [("frame", "b")], 4,
     "S1: the infantry walk cycle 0 1 0 2, by step & 3"),
    ("unit_sprite_nibble", 0x06C6C4, [("sprite", "w")], 16,
     "16 sprite numbers indexed by a nibble at $0124A8"),

    ("# ---- the score and the campaign (S9)",),
    ("rank_scores", 0x0A68CA, [("score", "w")], 8,
     "S9: the score thresholds of the ranks (txt_ranks), then $FFFF"),
    ("briefing_first", 0x087F30, [("index", "ref:@$087D74/4")], 3,
     "S9: per house, the first of its 36 mission strings in txt_briefings (ROM: pointers into the table at $087D74; here indices): Harkonnen 75, Atreides 3, Ordos 39"),
    ("campaign_attr", 0x095CE8, [("attr", "hw")], 4,
     "S9: the campaign map's tile attribute for each owner 0-3"),
    ("campaign_attack_pal", 0x095CF0, [("offset", "w")], 4,
     "S9: for owners 1-3, the offset of the six colours of the territory under attack"),
    ("campaign_owner", 0x095D0C, [("owner", "w*10")], 30,
     "S9: who owns each of the ten territories (0 nobody, 1 H, 2 A, 3 O) - a row before each mission and one after; three tables of 10 rows: Atreides, Ordos, Harkonnen"),

    ("# ---- maths",),
    ("sin", 0x06CFA4, [("v", "sb")], 256,
     "S3: 126 * sin(2 pi n / 256), 0 = north"),
    ("cos", 0x06D0A4, [("v", "sb")], 256,
     "S3: the same a quarter turn on"),
    ("cot", 0x0198B8, [("v", "l")], 32,
     "S3: tile_direction's arctangent $019940 - 256 * cot(i * 360/256), $3FFF for 0"),
    ("atan_quadrant", 0x019938, [("base", "w")], 4,
     "the arctangent's quadrant base angles, by the signs of dx (bit 0) and dy (bit 1)"),
    ("quarter_sine", 0x00030C, [("v", "w")], 65,
     "256 * sin(i * 90/64 degrees), i = 0..64, for the angle-and-radius routine $000AB0"),
]

TARGETS = {}


def resolve_targets():
    for t in SMALL:
        if len(t) > 1:
            name, rom, fields = t[0], t[1], t[2]
            if len(fields) == 1:
                TARGETS[name] = (rom, field_size(fields[0][1]) //
                                 max(1, split_type(fields[0][1])[1]))
    TARGETS["@$087D74/4"] = (0x087D74, 4)


def write_small():
    out = ["# tables.txt - the constant tables the game reads, one per spec table.",
           "#",
           "# Written once by tools/sega/port_data.py from orig/dune2.gen; the",
           "# text is now the source and tools/dune_data.py compiles it into",
           "# build/gen/tables.inc.  The build never reads orig/.",
           "#",
           "# The format (shared by units.txt, structures.txt, houses.txt,",
           "# landscape.txt and actions.txt):",
           "#",
           "#   table NAME           the label is tbl_NAME",
           "#   rom $XXXXXX          where the cartridge keeps it (documentation,",
           "#                        and what port_data.py check compares with)",
           "#   count N / size $NN   records, bytes a record",
           "#   anchor $XXXXXX       tbl_NAME is this address; tbl_NAME_start the first byte",
           "#   prefix P_            field offsets become EQUs P_name",
           "#   idprefix I_          record identifiers become EQUs I_IDENT (the record number)",
           "#   field $OFF TYPE[*N] NAME[:TARGET] ; comment",
           "#   records              then  record N IDENT / name = values ... end",
           "#   data                 then values, record by record, field by field ... end",
           "#",
           "# Types (dune_data.py's header has the byte order):",
           "#   b sb hb      byte, unsigned / signed / shown in hex",
           "#   w sw hw      word                     -> little-endian",
           "#   l sl hl      32-bit value             -> little-endian, low word first",
           "#   pos          y,x: a position or a (y, x) word pair -> y word, x word, each LE",
           "#   str          \"text\": a ROM string pointer -> dw record number, 0",
           "#   ref:T        T[n]: a ROM pointer into table T -> dw n, 0 (none -> $FFFF, $FFFF)",
           "#   chr          'c': a pointer to a one-letter string -> the letter, one byte",
           "#",
           "# Values: 12  -3  $FF  'H'.  '#' starts a comment line, ';' a comment.",
           ""]
    for t in SMALL:
        if len(t) == 1:
            out += ["", t[0], ""]
            continue
        name, rom, fields, count, doc = t
        per = sum(field_size(f[1]) for f in fields)
        assert within_region(rom, per * count), name
        out.append(f"table {name}")
        for line in wrap(doc, 70):
            out.append(f"# {line}")
        out += [f"rom ${rom:06X}", f"count {count}"]
        off = 0
        for fn, typ in fields:
            base, cnt, target = split_type(typ)
            t_ = base + (f"*{cnt}" if cnt > 1 else "")
            out.append(f"field ${off:02X} {t_} {fn}"
                       + (f":{target}" if target else ""))
            off += field_size(typ)
        out.append("data")
        single = len(fields) == 1 and split_type(fields[0][1])[1] == 1
        vals = []
        for i in range(count):
            r = rom + i * per
            row, off = [], 0
            for fn, typ in fields:
                base, cnt, target = split_type(typ)
                el = dune_data.SIZE[base]
                for k in range(cnt):
                    row.append(fmt(base + (f":{target}" if target else ""),
                                   r + off + k * el))
                off += field_size(typ)
            if single:
                vals += row
            else:
                out.append("  " + " ".join(row) + f"   ; {i}")
        for k in range(0, len(vals), 16):
            out.append("  " + " ".join(vals[k:k + 16]))
        out += ["end", ""]
    (OUT / "tables.txt").write_text("\n".join(out) + "\n")


def wrap(s, n):
    out, cur = [], ""
    for word in s.split():
        if cur and len(cur) + 1 + len(word) > n:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        out.append(cur)
    return out


# -------------------------------------------------------------------- maps

MAP_TABLE = 0x01B276


def map_of(seed):
    p = lg(MAP_TABLE + 4 * (seed - 1))
    scale = 32 if p >> 31 else 64
    a = p & 0xFFFFFF
    return a, scale, ROM[a:a + scale * scale]


def scen_names():
    names = []
    for line in (ROOT / "orig/sega/res/data/files.txt").read_text().splitlines():
        if line.startswith("SCEN"):
            p = line.split()
            names.append((p[0].split(".")[0], int(p[1][1:], 16), int(p[2])))
    return names


def write_maps():
    (OUT / "maps").mkdir(parents=True, exist_ok=True)
    used = {}
    for name, a, n in scen_names():
        recs, _ = parse_scen(ROM[a:a + n])
        for tag, ws, _ in recs:
            if tag == 0x0153:
                used.setdefault(ws[0], []).append(name)
    for seed in range(1, 28):
        a, scale, body = map_of(seed)
        who = ", ".join(used.get(seed, [])) or "no mission"
        lines = [f"# map{seed:02d}.txt - the battlefield for Seed={seed} ({who}).",
                 "#",
                 f"# From orig/dune2.gen ${a:06X}, the table at $01B276 (S8).",
                 "# A byte a square: its ground icon (tbl_icon_landscape gives the",
                 f"# landscape), {scale} rows of {scale}, the top row first.",
                 "# A 32 x 32 map covers rows and columns 16-47 of the 64 x 64 array.",
                 "", f"scale {scale}", ""]
        for r in range(scale):
            lines.append(" ".join(f"{b:02X}" for b in
                                  body[r * scale:(r + 1) * scale]))
        (OUT / "maps" / f"map{seed:02d}.txt").write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------- missions

def parse_scen(d):
    """(tag, words, tail bytes) records to the $FFFF; the loader's lengths
    ($0161F0, see tools/sega/sega_scen.py)."""
    out, i = [], 0
    while True:
        tag = int.from_bytes(d[i:i + 2], "big")
        i += 2
        if tag == 0xFFFF:
            return out, i
        sec, key = tag >> 8, tag & 0xFF

        def wd(k):
            return int.from_bytes(d[i + 2 * k:i + 2 * k + 2], "big")
        if sec == 0 and key <= 2:
            ln = wd(0)
            out.append((tag, [ln], d[i + 2:i + 2 + ln]))
            i += 2 + ln
        elif sec == 1 and key in (0x42, 0x46):
            ln = wd(0)
            out.append((tag, [wd(k) for k in range(ln + 1)], b""))
            i += 2 + 2 * ln
        elif sec <= 6:
            out.append((tag, [wd(0)], b""))
            i += 2
        elif sec in (7, 8, 9, 10):
            n = {7: 5, 8: 6, 10: 4}.get(sec, 3 if key == 0x47 else 5)
            out.append((tag, [wd(k) for k in range(n)], b""))
            i += 2 * n
        else:
            raise ValueError(f"section {sec}")


def xy(sq):
    return f"x{sq % 64} y{sq // 64}"


def name_or(lst, v):
    return lst[v] if 0 <= v < len(lst) else str(v)


def mission_text(name, a, d):
    recs, n = parse_scen(d)
    assert n == len(d), name
    B = dune_data
    lines = [f"# {name}.txt - mission {int(name[5:])} of the {dict(H='Harkonnen', A='Atreides', O='Ordos')[name[4]]}.",
             "#",
             f"# From orig/dune2.gen ${a:06X}, {len(d)} bytes: SCEN{name[4]}{name[5:]}.INI in the",
             "# directory at $052C2C (S9).  One line a record, in the cartridge's",
             "# order; tools/dune_data.py encodes them back to the tagged stream",
             "# (tag = section << 8 | key, then words), which port_data.py check",
             "# proves equal to the cartridge's.",
             "#",
             "#   BASIC  key value          [BASIC]; a picture is \"NAME\" and its length word",
             "#   MAP    Seed n | Bloom sq..  [MAP]; squares are y*64+x",
             "#   HOUSE  house key value     Quota Credits Brain(H human, C computer) MaxUnit",
             "#   CHOAM  unit count          the starport's stock",
             "#   TEAM   key house behaviour movement min max",
             "#   UNIT   key house type health square facing order",
             "#   GEN    square house type   a wall or slab",
             "#   STRUCT index house type health square",
             "#   REINF  key house type where delay['+' repeats]",
             "#   END                        the $FFFF",
             ""]
    for tag, ws, tail in recs:
        sec, key = tag >> 8, tag & 0xFF
        if sec == 0 and key <= 2:
            nm_, _, pad = tail.partition(b"\0")
            text = f"BASIC {B.BASIC[key]:<12} {quote(nm_)} {ws[0]}"
            if nm_ + bytes(ws[0] - len(nm_)) != tail:
                text += f" hex:{tail[len(nm_):].hex().upper()}"
            lines.append(text)
        elif sec == 0:
            com = f"   ; {xy(ws[0])}" if key in (5, 6) else ""
            lines.append(f"BASIC {B.BASIC[key]:<12} {ws[0]}{com}")
        elif sec == 1 and key in (0x42, 0x46):
            lines.append(f"MAP   {B.MAP_KEY[key]:<5} "
                         + " ".join(str(v) for v in ws[1:])
                         + "   ; " + ", ".join(xy(v) for v in ws[1:]))
        elif sec == 1:
            lines.append(f"MAP   {B.MAP_KEY[key]:<5} {ws[0]}")
        elif sec in (2, 3, 4, 5):
            h = HOUSE_IDS[B.SECTION_HOUSE[sec]]
            k = B.HOUSE_KEY[key]
            v = chr(ws[0]) if k == "Brain" else str(ws[0])
            lines.append(f"HOUSE {h:<10} {k:<8} {v}")
        elif sec == 6:
            lines.append(f"CHOAM {UNIT_IDS[key]:<12} {ws[0]}")
        elif sec == 7:
            house, beh, mov, lo, hi = ws
            bn = B.BEHAVIOUR.get(chr(beh), f"${beh:04X}")
            mn = B.MOVEMENT.get(chr(mov), f"${mov:04X}")
            lines.append(f"TEAM  {key:<3} {HOUSE_IDS[house]:<10} {bn:<9} "
                         f"{mn:<9} {lo} {hi}")
        elif sec == 8:
            house, kind, hp, sq, face, act = ws
            lines.append(f"UNIT  {key:<3} {HOUSE_IDS[house]:<10} "
                         f"{name_or(UNIT_IDS, kind):<11} {hp} {sq:<5} "
                         f"{B.COMPASS.get(face, str(face)):<3} "
                         f"{name_or(ORDER_IDS, act):<9} ; {xy(sq)}")
        elif sec == 9 and key == 0x47:
            sq, house, kind = ws
            lines.append(f"GEN   {sq:<5} {HOUSE_IDS[house]:<10} "
                         f"{name_or(STRUCT_IDS, kind)}   ; {xy(sq)}")
        elif sec == 9:
            idx, house, kind, hp, sq = ws
            assert key == 0x49
            lines.append(f"STRUCT {idx:<3} {HOUSE_IDS[house]:<10} "
                         f"{name_or(STRUCT_IDS, kind):<12} {hp} {sq:<5}"
                         f" ; {xy(sq)}")
        elif sec == 10:
            house, kind, where, when = ws
            wt = (f"{when >> 8}{'+' if when & 0xFF else ''}"
                  if when & 0xFF in (0, 0x2B) else f"${when:04X}")
            lines.append(f"REINF {key:<3} {HOUSE_IDS[house]:<10} "
                         f"{UNIT_IDS[kind]:<11} {B.LOCATION.get(where, str(where)):<9} {wt}")
        else:
            raise ValueError(tag)
    lines.append("END")
    return "\n".join(lines) + "\n"


def write_missions():
    (OUT / "missions").mkdir(parents=True, exist_ok=True)
    for name, a, n in scen_names():
        (OUT / "missions" / f"{name}.txt").write_text(
            mission_text(name, a, ROM[a:a + n]))


# ----------------------------------------------------------------- scripts

import emc_disasm  # noqa: E402

EMC_FILES = {"unit": "UNIT.EMC", "build": "BUILD.EMC", "team": "TEAM.EMC"}
TEAM_ENTRIES = ["team_normal", "team_staging", "team_flee", "team_kamikaze",
                "team_guard", "team_entry5"]

# the names S7 gives the routines, by script and call index
FUNC_NAMES = {
    "unit": {0: "get", 1: "act", 2: "print", 3: "distance", 4: "explode",
             5: "go.to", 6: "dir.to", 7: "turn", 8: "fire", 9: "deploy",
             10: "act.default", 12: "step", 13: "enemy?", 14: "blast.stub",
             15: "die", 16: "delay", 17: "friend?", 18: "explode.big",
             19: "frame", 20: "deliver", 22: "fly.to", 23: "random",
             25: "head.for", 26: "stop", 27: "speed", 28: "find.target",
             30: "seek.dock", 32: "amount", 33: "survivor", 34: "pick.up",
             35: "call.unit", 36: "dismiss", 37: "find.struct",
             39: "rts.stub", 40: "unfog", 41: "find.spice", 42: "harvest",
             44: "linked.type", 45: "kind", 47: "blocked?", 48: "nearby",
             49: "fidget", 50: "count", 51: "go.nearest", 54: "find.prey",
             55: "claim.ok?", 56: "facing.of", 58: "aim", 59: "not.unit?",
             60: "delay.rnd", 61: "turning?", 62: "distance.to"},
    "team": {0: "delay", 2: "members", 3: "recruit", 4: "spread",
             5: "gather", 6: "find.target", 7: "attack", 8: "behave",
             9: "behave.orig", 10: "delay.rnd", 12: "min", 13: "target"},
    "build": {0: "delay", 2: "check.link", 3: "send.for", 4: "set.state",
              5: "print", 6: "unclaim", 7: "release", 8: "find.target",
              9: "aim", 11: "fire", 13: "state", 15: "unfog", 21: "refine",
              22: "explode", 23: "destroy"},
}


def emc_chunks(name):
    fname = EMC_FILES[name]
    for line in (ROOT / "orig/sega/res/data/files.txt").read_text().splitlines():
        if line.startswith(fname + " "):
            p = line.split()
            a, n = int(p[1][1:], 16), int(p[2])
            return a, emc_disasm.chunks(ROM[a:a + n])
    raise KeyError(fname)


def func_names(name):
    tab, count = emc_disasm.FUNC_TABLE[EMC_FILES[name]]
    names = {}
    for i in range(count):
        at = lg(tab + 4 * i)
        nm = FUNC_NAMES[name].get(i)
        if nm is None:
            nm = f"zero{i}" if at in (0x045F82, 0x043CEC, 0x0112EE, 0x011106,
                                      0x02E500, 0x00C64E) else f"fn{i}"
        names[i] = (nm, at)
    return tab, count, names


def script_text(name):
    a, c = emc_chunks(name)
    data, ordr = c["DATA"], emc_disasm.entries(c["ORDR"])
    ins = emc_disasm.decode(data)
    tab, count, funcs = func_names(name)
    who = {"unit": UNIT_IDS, "build": STRUCT_IDS}.get(name)
    labels = {}
    entry_names = []
    for i, e in enumerate(ordr):
        lab = (f"{name}_{who[i].lower()}" if who else TEAM_ENTRIES[i])
        entry_names.append(lab)
        labels.setdefault(e, []).append(lab)
    for off, (op, par, size, cur) in ins.items():
        if op in (0, 15):
            t = par & 0x7FFF
            if not any(l.startswith("w") and l[1:].isdigit()
                       for l in labels.get(t, [])):
                labels.setdefault(t, []).append(f"w{t}")
    lines = [f"; {name}.emc - {EMC_FILES[name]}, the {len(data) // 2} words of its",
             f"; DATA chunk ({len(ordr)} entry points), from orig/dune2.gen ${a:06X}.",
             ";",
             "; Written once by tools/sega/port_data.py; this text is now the source.",
             "; tools/dune_data.py assembles it back to the cartridge's bytecode",
             "; exactly (port_data.py check proves it) and writes scripts.inc.",
             "; S7 is the reference for the machine and for every routine.",
             ";",
             "; .functions N         the size of the script's call table",
             "; .func I NAME         call index I, the 68000 routine it reaches",
             "; .entry I LABEL       ORDR entry I (a unit, a building, a behaviour)",
             "; LABEL:               a word offset; wNNN labels keep the offsets of",
             ";                      orig/sega/res/data/scripts/*.txt",
             ";",
             "; One instruction a line; the encoding is fixed per instruction:",
             ";   goto L        $8000 | L                  (1 word)",
             ";   goto-if L     $2F00, $8000 | L: pops, jumps if it was zero (2 words)",
             ";   push.w n      $2300, n                   (2 words)",
             ";   everything else $4000 | op << 8 | byte   (1 word):",
             ";   setret push.ret push.pc push.b push.var push.loc push.arg",
             ";   pop.ret ret pop.var pop.loc pop.arg drop reserve call unary",
             ";   binary return;   .word $XXXX is a raw word.",
             "",
             f".script {name}",
             f".functions {count}"]
    for i in range(count):
        nm, at = funcs[i]
        desc = emc_disasm.ROUTINE.get(at, ("", ""))[1]
        lines.append(f".func {i:<3} {nm:<13} ; ${at:06X}"
                     + (f" {desc}" if desc else ""))
    lines.append("")
    for i, lab in enumerate(entry_names):
        lines.append(f".entry {i:<3} {lab}")
    for off in sorted(ins):
        op, par, size, cur = ins[off]
        if off in labels:
            lines.append("")
            for lab in labels[off]:
                lines.append(f"{lab}:")
        if op == 0:
            body = f"goto     {first_w(labels, par & 0x7FFF)}"
        elif op == 15:
            assert par & 0x8000
            body = f"goto-if  {first_w(labels, par & 0x7FFF)}"
        elif op == 2:
            body = {0: "push.ret", 1: "push.pc"}[par]
        elif op == 8:
            body = {0: "pop.ret", 1: "ret"}[par]
        elif op == 14:
            body = f"call     {funcs[par][0]}"
        elif op == 16:
            body = f"unary    {emc_disasm.UNARY[par]}"
        elif op == 17:
            body = f"binary   {emc_disasm.BINARY[par & 0x1F]}"
        elif op == 18:
            body = "return"
        else:
            body = f"{dune_data_mnemonic(op):<8} {par}"
        lines.append(f"    {body:<28}; {off}")
    return "\n".join(lines) + "\n"


def first_w(labels, t):
    return next(l for l in labels[t] if l.startswith("w") and l[1:].isdigit())


def dune_data_mnemonic(op):
    for k, v in dune_data.EMC_OPS.items():
        if v == op:
            return k
    raise KeyError(op)


def write_scripts():
    (OUT / "scripts").mkdir(parents=True, exist_ok=True)
    for name in EMC_FILES:
        (OUT / "scripts" / f"{name}.emc").write_text(script_text(name))


# -------------------------------------------------------------------- text

BRIEF_TABLE = 0x087D74


def text_items():
    """group -> [(id, bytes, attrs, comment)], every string the port shows."""
    g = {}
    # the mentat: 3 house descriptions, then 9 x (briefing, win, lose,
    # advice) for Atreides, Ordos, Harkonnen - S9 "The mentat's texts"
    items = []
    houses = ["house_H", "house_A", "house_O"]
    for i in range(111):
        p = lg(BRIEF_TABLE + 4 * i)
        if i < 3:
            ident = houses[i]
        else:
            h = "AOH"[(i - 3) // 36]
            m = (i - 3) % 36 // 4 + 1
            kind = ["brief", "win", "lose", "advice"][(i - 3) % 4]
            ident = f"{h}{m}_{kind}"
        items.append((ident, cstr(p), {}, f"${p:06X}"))
    g["briefings"] = items
    # the closing credits, one text
    g["credits"] = [("credits", cstr(0x01192C), {}, "$01192C")]
    # passwords (S9): the word, its kind and value
    items = []
    a = 0x08811C
    while lg(a):
        p = lg(a)
        items.append((cstr(p).decode(), cstr(p), {"kind": w(a + 4),
                                                   "value": w(a + 6)},
                      f"${p:06X}"))
        a += 8
    g["passwords"] = items
    # the options screen's music and sound tests (S1, S10)
    for grp, a in (("music_test", 0x087F3C), ("sound_test", 0x087FD4)):
        items = []
        while lg(a):
            p = lg(a)
            s = cstr(p)
            items.append((re.sub(r"\W+", "_", s.decode().strip()).strip("_")
                          + f"_{len(items)}", s, {"song": lg(a + 4)},
                          f"${p:06X}"))
            a += 8
        g[grp] = items
    # the score page (S9): nine ranks of 17 and three houses of 9, fixed
    g["ranks"] = [(f"rank{i}", ROM[0x0A68DA + 17 * i:0x0A68DA + 17 * i + 17],
                   {}, f"${0x0A68DA + 17 * i:06X}") for i in range(9)]
    g["score_houses"] = [(HOUSE_IDS[i], ROM[0x0A6974 + 9 * i:0x0A6974 + 9 * i + 9],
                          {}, f"${0x0A6974 + 9 * i:06X}") for i in range(3)]
    # the few words the Mega Drive draws as text rather than pictures
    ui = [
        ("title_present", 0x0173F0, "menu_title $01755E"),
        ("title_start_game", 0x0173F8, "menu_title $017812"),
        ("title_options", 0x017403, "menu_title $01782A"),
        ("title_tutorial", 0x01740B, "menu_title $017842"),
        ("opt_on", 0x020D4F, "the options screen's switches ($020D4F on)"),
        ("opt_off", 0x020D53, ""),
        ("opt_restart", 0x020D67, "opt_screen $020EBE"),
        ("opt_pick_house", 0x020D77, "opt_screen $020ED2"),
        ("confirm_blank", 0x021A40, "opt_confirm: nine spaces"),
        ("confirm_yes_no", 0x021A4A, "opt_confirm $021AC8"),
        ("build_upgrade", 0x0276BA, "ui_build_info_text"),
        ("build_dmg", 0x0276C8, "ui_build_info_text $02771E"),
        ("starport_out_of_stock", 0x027900, "the starport's words"),
        ("starport_send_order", 0x02790E, "ui_starport_info_text $027972"),
        ("starport_dmg", 0x02791C, "ui_starport_info_text $02799A"),
        ("password_cursor", 0x0215B6, "$022190: the password cursor"),
        ("password_blank", 0x0215B8, ""),
        ("password_keys", None, "$021FB4: the password keyboard, 3 rows of 10"),
        ("version", None, "VERSIONNUM ($0218FE)"),
        ("region_lock", 0x0028D8, "$0028D2: the region-lock screen"),
    ]
    items = []
    for ident, a, com in ui:
        if ident == "password_keys":
            s, a = ROM[0x021FC6:0x021FE4], 0x021FC6
        elif ident == "version":
            a = ROM.index(b"1.2-011794\0")
            s = cstr(a)
        else:
            s = cstr(a)
        items.append((ident, s, {}, f"${a:06X} {com}".strip()))
    g["ui"] = items
    return g


GLYPH_FONTS = [(0x051C2C, "the default font of the text routine $022190"),
               (0x050C2C, "the other font ($022190 when asked; $026E46 sends it "
                          "to VRAM $A000)")]


def glyph_ranges(codes):
    out, run = [], []
    for c in codes + [None]:
        if run and (c is None or c != run[-1] + 1):
            out.append(f"${run[0]:02X}-${run[-1]:02X}" if len(run) > 1
                       else f"${run[0]:02X}")
            run = []
        if c is not None:
            run.append(c)
    return ", ".join(out)


def write_charset(groups):
    lines = ["# charset.txt - which characters the cartridge can draw.",
             "#",
             "# Written once by tools/sega/port_data.py; notes only, no strings.",
             "# The Mega Drive keeps its text as ASCII, and so does the port:",
             "# text.inc holds the character codes as they are, ended by $FF.",
             "#"]
    for a, what in GLYPH_FONTS:
        space = ROM[a + 32 * 32:a + 33 * 32]
        codes = [c for c in range(128)
                 if c == 32 or ROM[a + 32 * c:a + 32 * c + 32] != space]
        lines.append(f"# ${a:06X}: 128 glyphs of 8x8, 4 bits a pixel, by "
                     f"character code - {what}.")
        lines.append(f"#   drawn (not blank): {glyph_ranges(codes)}")
    lines += ["#   So both have every printable ASCII character, $20-$7E, and "
              "32 symbols",
              "#   below $20 that no string here uses.",
              "#",
              "# $001ED6: the region-lock and exception screens' font, 59 "
              "glyphs,",
              "#   $20-$5A only - space, punctuation, digits and capitals.",
              "#"]
    m = ROM[0x042AC8:0x042B48]
    codes = [c for c in range(128) if m[c]] + [32]
    lines.append("# $042AC8: the tutorial's text strip maps characters to 34 "
                 "glyphs; it has")
    lines.append(f"#   {''.join(chr(c) for c in sorted(set(codes)))!r} "
                 "(lower case drawn as capitals)")
    lines += ["#", "# The characters the strings in this folder use:"]
    for grp, items in groups.items():
        used = sorted({b for _, s, _, _ in items for b in s})
        pr = "".join(chr(b) for b in used if 32 <= b < 127)
        other = [f"${b:02X}" for b in used if not 32 <= b < 127]
        lines.append(f"#   {grp}: {pr!r}" + (f" and {' '.join(other)}"
                                                if other else ""))
    lines += ["#",
              "# ` stands for an apostrophe in the mentat's prose; the credits'",
              "# $FF n (a colour) is {cN} in credits.txt and $FE n in the port."]
    (OUT / "text" / "charset.txt").write_text("\n".join(lines) + "\n")


def write_text():
    (OUT / "text").mkdir(parents=True, exist_ok=True)
    g = text_items()
    write_charset(g)
    docs = {
        "briefings": ["the mentat's 111 texts (S9): the three houses' descriptions,",
                      "then for each mission a briefing, a victory, a defeat and",
                      "advice - Atreides (from index 3), Ordos (39), Harkonnen (75),",
                      "missions 1-9 (tbl_briefing_first).  The table is $087D74.",
                      "The prose has no line breaks: a block's lines join with a",
                      "space.  ` is the cartridge's apostrophe."],
        "credits": ["the closing credits ($01192C, $0117B4 scrolls them): one text,",
                    "a block's lines joined by new lines ($0A).  {cN} is the",
                    "cartridge's $FF N - a colour, 2 heading, 3 name; the port",
                    "writes it as $FE N, since $FF ends a string there."],
        "passwords": ["the 29 passwords (S9, $08811C; res/data/passwords.txt):",
                      "kind 0-2 a house (value the mission), 3 the ending, 6",
                      "LOOKAROUND, 7 SPLURGEOLA, 9 PLAYTESTER, 10 VERSIONNUM."],
        "music_test": ["the options screen's music test ($087F3C): each tune's",
                       "name and its song number (S10)."],
        "sound_test": ["the options screen's sound test ($087FD4): each sound's",
                       "name and its song number (S10)."],
        "ranks": ["the score page's nine ranks (S9, $0A68DA): 17 characters each,",
                  "centred with spaces; earned at tbl_rank_scores."],
        "score_houses": ["the score page's three house names ($0A6974), 9 each, centred."],
        "ui": ["every word the Mega Drive draws as text: the title menu, the",
               "options screen, the confirm box, the build panel's and the",
               "starport's info boxes, the password screen, the version and the",
               "region-lock screen.  Everything else on those screens - the",
               "buttons, the victory and defeat captions, the score headings - is",
               "a picture, not text.  The tutorial's captions are in its picture",
               "scripts (orig/sega/res/art/pictures.txt) and are not here."],
    }
    for grp, items in g.items():
        join = "newline" if grp == "credits" else "space"
        lines = [f"# {grp}.txt - {docs[grp][0]}"]
        lines += [f"# {d}" for d in docs[grp][1:]]
        lines += ["#",
                  "# Written once by tools/sega/port_data.py from orig/dune2.gen;",
                  "# this text is now the source (tools/dune_data.py -> text.inc).",
                  "# @id \"text\" [attr=value] is one string; @id [attr=value] then",
                  "# lines then @end is a long one.  Escapes: \\n \\\" \\\\ \\xNN {cN}.",
                  "# The characters are ASCII; charset.txt says which the fonts have."]
        lines += ["", f".join {join}", ""]
        for ident, s, attrs, com in items:
            at = "".join(f" {k}={v}" for k, v in attrs.items())
            if grp in ("briefings", "credits"):
                lines.append(f"@{ident}{at}   ; {com}")
                lines += block_lines(s, join)
                lines.append("@end")
                lines.append("")
            else:
                lines.append(f"@{ident:<22} {quote_text(s)}{at}   ; {com}")
        (OUT / "text" / f"{grp}.txt").write_text("\n".join(lines) + "\n")


def quote_text(bs):
    out = '"'
    i = 0
    while i < len(bs):
        b = bs[i]
        if b == 0xFF:
            out += f"{{c{bs[i + 1]}}}"
            i += 2
            continue
        c = chr(b)
        if c in '"\\':
            out += "\\" + c
        elif 32 <= b < 127:
            out += c
        elif b == 10:
            out += "\\n"
        else:
            out += f"\\x{b:02X}"
        i += 1
    return out + '"'


def block_lines(bs, join):
    s = ""
    i = 0
    while i < len(bs):
        if bs[i] == 0xFF:
            s += f"{{c{bs[i + 1]}}}"
            i += 2
        else:
            assert bs[i] == 10 or 32 <= bs[i] < 127, bs[i]
            s += chr(bs[i])
            i += 1
    if join == "newline":
        return s.split("\n")
    # wrap at single spaces only, so joining with one space gives it back
    words = s.split(" ")
    if "" in words:                       # a double space: keep one line
        return [s]
    out, cur = [], ""
    for wd in words:
        if cur and len(cur) + 1 + len(wd) > 72:
            out.append(cur)
            cur = wd
        else:
            cur = f"{cur} {wd}" if cur else wd
    out.append(cur)
    return out


# ------------------------------------------------------------------- check

def assemble(src, name):
    """Assemble a test file with sjasmplus; the symbols and the pages."""
    TMP.mkdir(parents=True, exist_ok=True)
    asm = TMP / f"{name}.asm"
    asm.write_text(src)
    sym = TMP / f"{name}.sym"
    r = subprocess.run([str(SJASM), "--nologo", f"--sym={sym}",
                        f"--inc={TMP / 'gen'}", str(asm)],
                       capture_output=True, text=True, cwd=TMP)
    if r.returncode:
        raise SystemExit(f"sjasmplus failed on {name}:\n{r.stdout}{r.stderr}")
    syms = {}
    for line in sym.read_text().splitlines():
        m = re.match(r"(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m[1]] = int(m[2], 16)
    return syms


def rom_port_bytes(t):
    """What tables.inc must hold for table t, worked out from the ROM
    directly: each field put into the port's byte order, each pointer
    turned into the index the text claims for it."""
    out = bytearray()
    stride = t.size if t.form == "records" else \
        sum(f.size for f in t.fields)
    for r in range(t.count):
        base = t.rom + r * stride
        for f in t.fields:
            el = dune_data.SIZE[f.typ]
            for k in range(f.count):
                a = base + f.off + k * el
                if f.typ in ("b", "sb", "hb"):
                    out.append(ROM[a])
                elif f.typ in ("w", "sw", "hw"):
                    out += ROM[a:a + 2][::-1]
                elif f.typ in ("l", "sl", "hl"):
                    out += ROM[a:a + 4][::-1]
                elif f.typ == "pos":
                    out += ROM[a:a + 2][::-1] + ROM[a + 2:a + 4][::-1]
                elif f.typ == "str":
                    out += struct.pack("<HH", r, 0)
                elif f.typ == "ref":
                    p = lg(a)
                    if p == 0:
                        out += b"\xff\xff\xff\xff"
                    else:
                        tb, ts = TARGETS[f.target]
                        out += struct.pack("<HH", (p - tb) // ts, 0)
                elif f.typ == "chr":
                    out.append(ROM[lg(a)])
    return bytes(out)


def device_test(incs):
    lines = ["\tDEVICE ZXSPECTRUM4096"]
    page = 16
    for inc in incs:
        lines += [f"\tMMU 3 n, {page}", "\tORG $C000", f"\tINCLUDE \"{inc}\""]
        page += 8
    return "\n".join(lines) + "\n"


def check():
    resolve_targets()
    gen = TMP / "gen"
    r = subprocess.run([sys.executable, str(ROOT / "tools/dune_data.py"),
                        str(gen)], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    print(r.stdout.strip())
    fails = 0
    sizes = {p.name: 0 for p in gen.glob("*.inc")}

    # 1. every .inc assembles, each on its own and all together
    for inc in sorted(sizes):
        assemble(device_test([inc]), inc.split(".")[0])
    syms = assemble(device_test(["tables.inc", "scripts.inc", "missions.inc",
                                 "maps.inc", "text.inc"]), "all")

    # sizes: where each one ends, from a page start
    for inc in sorted(sizes):
        src = device_test([inc]) + "inc_end_addr EQU $\ninc_end_page EQU $$\n"
        sy = assemble(src, "size_" + inc.split(".")[0])
        sizes[inc] = ((sy["inc_end_page"] - 16) * 16384
                      + sy["inc_end_addr"] - 0xC000)
    print("sizes: " + ", ".join(f"{k} {v}" for k, v in sorted(sizes.items())))

    # 2. the tables, byte for byte against the ROM
    TMP.joinpath("tables.asm").write_text(
        "\tOUTPUT \"tables.bin\"\n\tORG 0\n\tINCLUDE \"tables.inc\"\n")
    subprocess.run([str(SJASM), "--nologo", f"--inc={gen}",
                    "--sym=tables.sym", "tables.asm"],
                   capture_output=True, cwd=TMP, check=True)
    tb = (TMP / "tables.bin").read_bytes()
    tsyms = {}
    for line in (TMP / "tables.sym").read_text().splitlines():
        m = re.match(r"(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            tsyms[m[1]] = int(m[2], 16)
    tables = dune_data.load_tables()
    for t in tables.values():
        want = rom_port_bytes(t)
        lab = t.label + ("_start" if t.anchor is not None else "")
        at = tsyms[lab]
        got = tb[at:at + len(want)]
        if got != want:
            k = next(i for i in range(len(want)) if got[i] != want[i])
            print(f"FAIL {t.label}: byte {k} differs")
            fails += 1
        # and every string field says what the ROM's pointer says
        for r_, row in enumerate(dune_data.record_values(t)):
            for f, vals in row:
                if f.typ == "str":
                    p = lg(t.rom + r_ * t.size + f.off)
                    if dune_data.unescape(vals[0]) != cstr(p):
                        print(f"FAIL {t.name}.{f.name}[{r_}]")
                        fails += 1
    print(f"tables: {len(tables)} checked against the ROM")

    # 3. the scripts, exactly
    for sc in dune_data.load_scripts():
        _, c = emc_chunks(sc.name)
        data = b"".join(v.to_bytes(2, "big") for v in sc.words)
        ordr = b"".join(sc.labels[sc.entries[i]].to_bytes(2, "big")
                        for i in range(len(sc.entries)))
        ok = data == c["DATA"] and ordr == c["ORDR"]
        fails += not ok
        print(f"script {sc.name}: {len(sc.words)} words, "
              f"{len(sc.entries)} entries - {'exact' if ok else 'FAIL'}")

    # 4. the missions, exactly
    nm = dune_data.Names(tables)
    ok = 0
    for name, a, n in scen_names():
        recs = dune_data.mission_records(OUT / "missions" / f"{name}.txt", nm)
        if dune_data.encode_mission(recs, big=True) == ROM[a:a + n]:
            ok += 1
        else:
            print(f"FAIL {name}")
            fails += 1
    print(f"missions: {ok} of 27 exact")

    # 5. the maps
    ok = 0
    for seed in range(1, 28):
        _, scale, body = map_of(seed)
        s2, b2 = dune_data.read_map(OUT / "maps" / f"map{seed:02d}.txt")
        ok += (s2, b2) == (scale, body)
    fails += ok != 27
    print(f"maps: {ok} of 27 exact")

    # 6. the text
    want = text_items()
    ok = total = 0
    for grp, items in want.items():
        got = dune_data.read_text(OUT / "text" / f"{grp}.txt")
        for (i1, s1, a1, _), (i2, s2, a2) in zip(items, got):
            total += 1
            if (s1, a1) == (s2, a2):
                ok += 1
            else:
                print(f"FAIL text {grp} {i1}")
        if len(items) != len(got):
            print(f"FAIL text {grp}: {len(got)} strings, want {len(items)}")
            fails += 1
    fails += ok != total
    print(f"text: {ok} of {total} strings exact")
    print("labels in the combined test: " + str(len(syms)))
    if fails:
        raise SystemExit(f"{fails} failures")
    print("all checks pass")


def extract():
    resolve_targets()
    OUT.mkdir(parents=True, exist_ok=True)
    write_records()
    write_small()
    write_maps()
    write_missions()
    write_scripts()
    write_text()
    print(f"extracted -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    {"extract": extract, "check": check}[cmd]()
