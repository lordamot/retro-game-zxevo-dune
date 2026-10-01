#!/usr/bin/env python3
"""port_icons.py - the Mega Drive battlefield's 32x32 map icons, as port art.

    port_icons.py [--rom orig/dune2.gen] [--out src/res/art]
                  [--states GLOB ...] [--check] [--no-dump]

Writes, into src/res/art/:

    icons.png         all 360 icons, 16 to a row, 32x32 each, RGBA
    icons_marker.png  the one animated icon family: icons 20-26, 8 frames
    icons.txt         one line per icon: group, landscape, use, what it is
    structanims.txt   the map-animation scripts and every structure state

and with --check compares a rebuild of the battlefield from the RAM map
and icons.png alone against the VDP's own planes, in every battle state.

## What an icon is

A map square has a 9-bit ground icon and a 7-bit overlay icon (S8).  An
icon is 4 x 4 VDP cells: the 16 name-table words of icon n are at ROM
$04ADE8 + 32*n, big-endian, tile in bits 0-10, h-flip 11, v-flip 12,
palette line 13-14, priority 15.  map_draw_square ($005EDE) copies the
ground icon's words into plane B ($FFE024) and the overlay icon's into
plane A ($FFE022) unchanged - so an icon's picture is exactly those 16
cells, drawn from the tiles that are in VRAM during a battle, in the
battle's CRAM.  There is nothing else to it: no per-mission tables, no
house recolouring.  Ground and overlay share the table (the overlay is
read as byte 0 of the square & $FE, times 16 - that is, overlay * 32).

## The art is the same in every battle

The tool dumps VRAM, CRAM, the VDP registers and work RAM from every
save state it is given (bin/gen/retro-run), keeps those whose frame hook
($FFE002) is one of the battle's two ($00608E, $006D0C), and asserts:

  - the icons use tiles 0-921 only;
  - those tiles are byte-identical in every battle - small and large
    maps, all three houses, the last missions - except tiles $2BE-$2C1
    (702-705);
  - the CRAM is identical in every battle.

Tiles 702-705 are the one animation on the battlefield's planes: the
battle's frame hook (irq_battle_grid_cursor $00608E / $006D0C) DMAs the
next of eight 2x2-tile frames at ROM $00690C (128 bytes each) to VRAM
$57C0 once every eight video frames, frames 0-7 in order ($FFBF68 is the
next frame).  Before the first time (the first battle frame) the tiles
hold leftovers.  The picture is a small glowing orb, and the icons that
use it are 20-26: 22-26 are the **house marker** (struct_draw_house_marker
$00B3E0 sets overlay $16 + house on a structure's bottom-left square and
writes the same 2x2 cells into plane A directly, in the house's palette
line from $00B52C), 20 and 21 are orb pieces nothing was found to write.
icons.png draws them with frame 0; icons_marker.png has all eight.

map_anim_tiles_a ($00AFCA, VRAM $96C0/$97E0/$9900) and map_anim_tiles_b
($00B028, VRAM $DF20) animate **sprite** tiles, not icon tiles: tiles
$4B6-$4D0 are the three 9-tile rotor frames of animations 289-297 (the
aircraft) and $6F9-$6FE the 6-tile smoke of animations 180-182.  No icon
refers to them, and no name-table word in any battle's planes does.

## Transparency

Alpha is 0 where a cell's pixel is colour 0 of its line.  On plane A
(overlays) that shows plane B.  On plane B (ground) it shows the
backdrop, which is CRAM entry VDP register 7 = 0: black in every battle.
Ground icons with transparent pixels: the empty ones (all tile 0).

The 16 fog icons $6C-$7B are the only icons with the priority bit: the
fog is drawn over the sprites, so a unit under the fog is hidden by the
plane itself.

## Structures

structanims.txt is generated from the ROM tables the code reads:
struct_place ($00ED68) starts map-animation script `type +$3E`,
struct_remove ($00F7CE) script `$06BBF2[layout]`, emc_build_fire
($00CF54) `$1B + facing` (Turret) or `$23 + facing` (R-Turret, targets
nearer than 3 squares), from the table at $06A9B4; map_anim_draw
($00B0A4) stamps an icon of 128 or more, or a flagged one ($00B142),
as consecutive icons over the layout's squares in their order at
$06B738, and puts any other icon in the square's overlay.
struct_animate ($00D656) turns idle turrets and flashes the Refinery's
and Starport's lights ($06BA0C-$06BA5C); emc_build_aim ($00CB92) turns a
turret towards its target; struct_connect_wall ($00EDAE) picks a wall
icon from a table built from $06BA74/$06BB74.  The file lists each.

## The check (--check)

For every battle state: the view origin is ($FFE3EC, $FFE3EE) in map
pixels; screen pixel (x, y) is map pixel (camX + x, camY + y) and plane
pixel ((x - hscroll) & 511, (y + vscroll) & 255) of each 64 x 32 plane.
The ground layer is rebuilt from the RAM map ($FF7D9C, 4 bytes a
square) and icons.png, the overlay layer likewise (with LOOKAROUND's
rule: overlays of $34 and up left out when $FFC198 is set), the house
marker in the orb frame VRAM holds; each is compared pixel for pixel
with the VDP's rendering of plane B and plane A over the 320 x 224
screen, and so is the screen they compose (A over B over the backdrop).
Sprites are not in the planes and so not compared.

Every pixel matches except one kind, which is counted as `stale`: when
the view is not on a whole cell, the column of cells at the right edge
and the row at the bottom that are only partly on screen may never have
been written by the view drawer (scroll_draw_right_column and its
siblings draw the cells *past* the edge as the view moves; the first
draw does not).  Those cells are tile 0 on both planes, so the screen
shows the backdrop - black - where the map says full fog, which is also
black: the composed screen matches everywhere.  The control is the same
rebuild with the view origin one square to the right: it must fail,
by thousands of pixels a state.

The squares on screen in the recorded battles show 51 distinct ground
icons, the fog edges, craters and the house markers; the rest of the
icons are drawn by the same words, tiles and CRAM, which the art checks
above show are the same in every battle.
"""

import argparse
import glob
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("error: this tool needs numpy and Pillow")

ROOT = Path(__file__).resolve().parent.parent.parent
RETRO = ROOT / "bin/gen/retro-run"
CORE = ROOT / "bin/gen/genesis_plus_gx_libretro.so"
DUMPS = ROOT / "tmp/port-icons/dumps"
DEFAULT_STATES = ["tmp/sega/spec/s8/*-start.state", "tmp/sega/spec/m1-*.state",
                  "tmp/sega/spec/pw-*.state", "tmp/sega/spec/pt-*.state",
                  "tmp/sega/spec/win-*.state"]

ICONS = 0x04ADE8            # 16 name-table words an icon
N_ICONS = 360
ICONMAP_PTR = 0x04AA24      # -> ICON.MAP at $04AA28: 27 group starts, then icons
ICONMAP_GROUPS = 27
LANDSCAPE = 0x005818        # a signed byte per icon
ANIM_FLAGS = 0x00B142       # 128 bytes: overlay value stamped as ground
ANIM_SCRIPTS = 0x06A9B4     # 64 pointers
STRUCT_TYPES, STRUCT_SIZE = 0x06AFA6, 0x66
LAYOUT_COUNT = 0x06B826     # squares a layout
LAYOUT_OFFS = 0x06B738      # 9 words a layout
RUBBLE_SCRIPT = 0x06BBF2    # a word per layout
LIGHTS = 0x06BA0C           # 6 lists of 8 words
WALL_TABLE, WALL_INDEX = 0x06BA74, 0x06BB74
ORB_FRAMES = 0x00690C       # 8 x 128 bytes -> VRAM $57C0
ORB_TILE = 0x2BE
BATTLE_HOOKS = (0x00608E, 0x006D0C)

MAP, CAMX, CAMY, LOOKAROUND, ORB_NEXT = 0xFF7D9C, 0xFFE3EC, 0xFFE3EE, 0xFFC198, 0xFFBF68
FRAME_HOOK = 0xFFE002

LANDSCAPE_NAMES = ["sand", "partial rock", "entirely dune", "partial dune",
                   "entirely rock", "mostly rock", "entirely mountain",
                   "partial mountain", "spice", "thick spice", "concrete slab",
                   "wall", "structure", "destroyed wall", "bloom field"]
STRUCT_NAMES = ["Slab", "4-Slab", "Palace", "Light Factory", "Heavy Factory",
                "Hi-Tech", "IX", "WOR", "Construction Yard", "Windtrap",
                "Barracks", "Starport", "Refinery", "Repair Facility", "Wall",
                "Turret", "R-Turret", "Silo", "Outpost"]
LAYOUT_NAMES = ["1x1", "2x1", "1x2", "2x2", "2x3", "3x2", "3x3"]
DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
HOUSES = ["Harkonnen", "Atreides", "Ordos", "Fremen", "Sardaukar"]
MASK = "mask bits N=1 E=2 S=4 W=8"


def w16(b, a):
    return int.from_bytes(b[a:a + 2], "big")


def s16(b, a):
    v = w16(b, a)
    return v - 0x10000 if v & 0x8000 else v


def l32(b, a):
    return int.from_bytes(b[a:a + 4], "big")


# ---------------------------------------------------------------- the ROM

class Rom:
    def __init__(self, path):
        self.b = Path(path).read_bytes()
        b = self.b
        self.icons = [[w16(b, ICONS + 32 * n + 2 * c) for c in range(16)]
                      for n in range(N_ICONS)]
        im = l32(b, ICONMAP_PTR)
        starts = [w16(b, im + 2 * g) for g in range(ICONMAP_GROUPS)]
        # the last group (the Outpost's) has 12 entries like its 2x2
        # siblings; the words after it are padding up to the icon table
        ends = starts[1:] + [starts[-1] + 12]
        self.groups = [[w16(b, im + 2 * i) for i in range(s, e)]
                       for s, e in zip(starts, ends)]
        self.landscape = [x - 256 if x > 127 else x
                          for x in b[LANDSCAPE:LANDSCAPE + N_ICONS]]
        self.flags = b[ANIM_FLAGS:ANIM_FLAGS + 128]
        self.scripts = {}
        self.script_ptr = []
        for n in range(64):
            p = l32(b, ANIM_SCRIPTS + 4 * n)
            self.script_ptr.append(p)
            steps, a = [], p
            while True:
                ic, d = w16(b, a), s16(b, a + 2)
                steps.append((ic, d))
                a += 4
                if d <= 0:
                    break
            self.scripts[n] = steps
        self.types = []
        for t in range(19):
            r = STRUCT_TYPES + STRUCT_SIZE * t
            self.types.append({"layout": w16(b, r + 0x3C),
                               "script": w16(b, r + 0x3E)})
        self.layouts = []
        for lay in range(7):
            cnt = w16(b, LAYOUT_COUNT + 2 * lay)
            offs = [s16(b, LAYOUT_OFFS + 18 * lay + 2 * i) for i in range(cnt)]
            self.layouts.append(offs)
        self.rubble = [w16(b, RUBBLE_SCRIPT + 2 * lay) for lay in range(7)]
        self.lights = [[w16(b, LIGHTS + 16 * k + 2 * f) for f in range(4)]
                       for k in range(6)]
        t = bytearray(b[WALL_TABLE:WALL_TABLE + 256])
        for i in range(0x4A):
            t[b[WALL_INDEX + i]] = i
        for k, v in ((0xA, 1), (8, 1), (1, 3), (5, 3), (0x22, 13), (0x88, 14),
                     (0x44, 17)):                   # $00EE06-$00EE2A
            t[k] = v
        self.wall_icon = [0x22 + t[m] for m in range(16)]   # $FFC234 + 1 + t
        self.orb = [b[ORB_FRAMES + 128 * f:ORB_FRAMES + 128 * f + 128]
                    for f in range(8)]

    def tiles_used(self):
        return sorted({e & 0x7FF for es in self.icons for e in es})

    def group_entries(self, n):
        return [(g, i) for g, es in enumerate(self.groups)
                for i, v in enumerate(es) if v == n]


# ---------------------------------------------------------- the save states

class Dump:
    """One battle's VRAM, CRAM, VDP registers and work RAM, un-swapped."""

    def __init__(self, d):
        d = Path(d)
        self.name = d.name
        v = bytearray(d.joinpath("vram.bin").read_bytes())
        v[0::2], v[1::2] = v[1::2], v[0::2]
        self.vram = bytes(v)
        r = bytearray(d.joinpath("ram.bin").read_bytes())
        r[0::2], r[1::2] = r[1::2], r[0::2]
        self.ram = bytes(r)
        c = d.joinpath("cram.bin").read_bytes()
        self.cram_raw = c
        self.cram = [c[2 * i] | (c[2 * i + 1] << 8) for i in range(64)]
        self.vsram = d.joinpath("vsram.bin").read_bytes()
        self.reg = d.joinpath("vdpreg.bin").read_bytes()

    def rw(self, a, size=2):
        o = a - 0xFF0000
        return int.from_bytes(self.ram[o:o + size], "big")

    def battle(self):
        return self.rw(FRAME_HOOK, 4) in BATTLE_HOOKS

    def tile(self, t):
        return self.vram[t * 32:t * 32 + 32]


def rgb(word):
    return ((word & 7) * 255 // 7, ((word >> 3) & 7) * 255 // 7,
            ((word >> 6) & 7) * 255 // 7)


def dump_states(patterns):
    files = []
    for p in patterns:
        files += sorted(glob.glob(str(ROOT / p)))
    if not files:
        sys.exit("error: no save states match " + " ".join(patterns))
    DUMPS.mkdir(parents=True, exist_ok=True)
    script = DUMPS / "dump.script"
    lines = []
    for f in files:
        d = DUMPS / Path(f).stem
        d.mkdir(exist_ok=True)
        lines += [f"load {f}", "run 1"]
        for what in ("vram", "cram", "vsram", "vdpreg", "ram"):
            lines.append(f"{what} {d}/{what}.bin")
    script.write_text("\n".join(lines) + "\n")
    r = subprocess.run([str(RETRO), "--core", str(CORE), "--rom",
                        str(ROOT / "orig/dune2.gen"), "--script", str(script)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("error: retro-run failed\n" + r.stderr[-2000:])
    return [DUMPS / Path(f).stem for f in files]


def load_battles(dirs):
    out = []
    for d in dirs:
        if not Path(d, "vram.bin").exists():
            continue
        dm = Dump(d)
        if dm.battle():
            out.append(dm)
    if not out:
        sys.exit("error: none of the states is a battle")
    return out


# --------------------------------------------------------------- pictures

def tile_indices(data):
    """32 bytes of 4bpp -> 8x8 numpy array of colour indices."""
    a = np.frombuffer(data, dtype=np.uint8).reshape(8, 4)
    out = np.empty((8, 8), dtype=np.uint8)
    out[:, 0::2] = a >> 4
    out[:, 1::2] = a & 15
    return out


def cell(tiles, e):
    """-> (8x8 indices, palette line) for a name-table word."""
    px = tiles[e & 0x7FF]
    if e & 0x0800:
        px = px[:, ::-1]
    if e & 0x1000:
        px = px[::-1, :]
    return px, (e >> 13) & 3


def icon_rgba(words, tiles, pal):
    img = np.zeros((32, 32, 4), dtype=np.uint8)
    for c, e in enumerate(words):
        px, line = cell(tiles, e)
        y, x = (c // 4) * 8, (c % 4) * 8
        for j in range(8):
            for i in range(8):
                v = px[j, i]
                if v:
                    img[y + j, x + i] = pal[line * 16 + v] + (255,)
    return img


def build_tiles(dump, orb_frame=0, rom=None):
    tiles = [tile_indices(dump.tile(t)) for t in range(2048)]
    if rom is not None:
        fr = rom.orb[orb_frame]
        for k in range(4):
            tiles[ORB_TILE + k] = tile_indices(fr[32 * k:32 * k + 32])
    return tiles


def render_icons(rom, dump):
    pal = [rgb(w) for w in dump.cram]
    tiles = build_tiles(dump, 0, rom)
    sheet = np.zeros((32 * 23, 32 * 16, 4), dtype=np.uint8)
    for n in range(N_ICONS):
        y, x = (n // 16) * 32, (n % 16) * 32
        sheet[y:y + 32, x:x + 32] = icon_rgba(rom.icons[n], tiles, pal)
    marker = np.zeros((32 * 7, 32 * 8, 4), dtype=np.uint8)
    for f in range(8):
        tf = build_tiles(dump, f, rom)
        for k, n in enumerate(range(20, 27)):
            marker[k * 32:k * 32 + 32, f * 32:f * 32 + 32] = \
                icon_rgba(rom.icons[n], tf, pal)
    return sheet, marker


# ----------------------------------------------------------------- consistency

def consistency(rom, battles):
    used = rom.tiles_used()
    assert used[0] == 0 and used[-1] < 1024, "icons reach unexpected tiles"
    orb = set(range(ORB_TILE, ORB_TILE + 4))
    key = Counter()
    for d in battles:
        key[b"".join(d.tile(t) for t in used if t not in orb)] += 1
    crams = Counter(d.cram_raw for d in battles)
    ref = battles[0]
    lines = [f"{len(battles)} battle states; icons use tiles 0-{used[-1]} "
             f"({len(used)} tiles)"]
    diff_tiles = Counter()
    for d in battles:
        for t in used:
            if d.tile(t) != ref.tile(t):
                diff_tiles[t] += 1
    other = sorted(t for t in diff_tiles if t not in orb)
    lines.append(f"tiles that differ between battles: "
                 f"{sorted(diff_tiles) if diff_tiles else 'none'}"
                 f" (outside the orb: {other if other else 'none'})")
    lines.append(f"distinct CRAMs: {len(crams)}")
    ok = len(key) == 1 and len(crams) == 1
    return ok, lines


# ---------------------------------------------------------- icons.txt

R_TURRET_FIRE = [0x37, 0x38, 0x39, 0x3A, 0x3B, 0x48, 0x49, 0x4A]


def place_icons(rom, t):
    """-> (built, construction) first icons of type t's place script."""
    steps = [st for st in rom.scripts[rom.types[t]["script"]] if st[1] > 0]
    built = steps[-1][0]
    build = next(ic for ic, _ in steps if ic != built)
    return built, build


def structure_icons(rom):
    """icon -> [what draws it], for every icon a structure state draws."""
    d = {}

    def put(n, s):
        d.setdefault(n, [])
        if s not in d[n]:
            d[n].append(s)
    for k in range(8):
        put(0x114 + k, f"Turret facing {DIRS[k]}")
        put(0x11C + k, f"R-Turret facing {DIRS[k]}")
    names = [(0, "square 2 (top right)"), (1, "square 5 (bottom right)")]
    for f in range(1, 4):
        for k, where in names:
            put(rom.lights[k][f], f"Refinery {where}, lights frame {f}")
        for k, where in ((2, "square 4 (centre)"), (3, "square 5 (right)"),
                         (4, "square 7 (bottom)"), (5, "square 8 (bottom right)")):
            put(rom.lights[k][f], f"Starport {where}, lights frame {f}")
    for t, ty in enumerate(rom.types):
        if t in (0, 1, 14, 15, 16):
            continue
        built, _ = place_icons(rom, t)
        for k in range(len(rom.layouts[ty["layout"]])):
            put(built + k, f"{STRUCT_NAMES[t]} square {k}")
    for t, ty in enumerate(rom.types):
        if t in (0, 1, 14):
            continue
        _, build = place_icons(rom, t)
        for k in range(len(rom.layouts[ty["layout"]])):
            put(build + k, f"under construction, "
                f"{LAYOUT_NAMES[ty['layout']]} square {k}")
    for lay, sc in enumerate(rom.rubble):
        if sc:
            ic = rom.scripts[sc][1][0]
            for k in range(len(rom.layouts[lay])):
                put(ic + k, f"rubble, {LAYOUT_NAMES[lay]} square {k}")
    return d


def describe(n, rom, sicons):
    blank = all(e == 0 for e in rom.icons[n])
    ls = rom.landscape[n]
    if n == 0:
        return "nothing: overlay 0, and the ground outside a 32 x 32 map"
    if 1 <= n <= 12:
        k = (n - 1) % 6
        return (f"{'rock' if n <= 6 else 'sand'} crater, shape {k % 2}, "
                f"depth {k // 2} (map_add_crater: +2 a blast, up to depth 2)")
    if n in (20, 21):
        return ("orb pieces (tiles $2BE-$2C2 flipped, so they animate with "
                "the marker); no writer found, never seen")
    if 22 <= n <= 26:
        return (f"house marker, {HOUSES[n - 22]}: an orb in the bottom-left "
                f"quarter, animated (icons_marker.png)")
    if n == 0x21:
        return "destroyed wall (wallIcon $FFC234, map_destroy_wall)"
    if 0x22 <= n <= 0x2D:
        masks = [m for m in range(16) if rom.wall_icon[m] == n]
        return f"wall, neighbouring walls {masks} ({MASK})"
    if 0x2E <= n <= 0x35:
        return (f"Turret firing, facing {DIRS[n - 0x2E]} (script "
                f"{0x1B + n - 0x2E}, 9 frames)")
    if n in R_TURRET_FIRE:
        k = R_TURRET_FIRE.index(n)
        return f"R-Turret firing, facing {DIRS[k]} (script {0x23 + k}, 9 frames)"
    if n == 0x36:
        return ("an R-Turret picture facing N; no script, table or map "
                "names it (the firing set skips it)")
    if 0x6C <= n <= 0x7B:
        m = n - 0x6C
        return (f"fog, fogged neighbours {m} ({MASK})"
                + ("; the full fog, veiledIcon" if m == 15 else ""))
    if n == 0x7C:
        return "rock, plain"
    if n == 0x7D:
        return "rock with scattered debris"
    if n == 0x7E:
        return "concrete slab (builtSlabIcon $FFC230)"
    if n == 0x7F:
        return "sand (landscapeIcon $FFC22C)"
    for base, name in ((0x80, "rock"), (0x90, "dunes"), (0xA0, "mountain"),
                       (0xB0, "spice"), (0xC0, "thick spice")):
        if base <= n < base + 16:
            return f"{name}, same-kind neighbours {n - base} ({MASK})"
    if n in (0xD0, 0xD1):
        return "spice bloom" + (" (bloomIcon $FFC228)" if n == 0xD0 else
                                ", a copy of $0D0 nothing names")
    own = {0xDB: "the Light Factory's", 0xEF: "the WOR's"}
    for base, who in own.items():
        if base <= n < base + 4:
            return (f"blank: {who} own ICON.MAP entries, but no structure "
                    f"type's script names them")
    if n in sicons:
        what = "; ".join(sicons[n])
        return what + (" - BLANK: the Mega Drive has no art here" if blank
                       else "")
    if 0x3C <= n <= 0x66 and ls >= 0 and not blank:
        return f"terrain transition ({LANDSCAPE_NAMES[ls]}), in the stored maps"
    if blank:
        return "blank (all tile 0)" + (
            f"; $005818 still calls it {LANDSCAPE_NAMES[ls]}" if ls >= 0 else "")
    return "not named by any script, table or map found"


def icon_use(n, rom, sicons, ground_seen, overlay_seen):
    u = []
    if (ground_seen.get(n) or n in sicons or (rom.landscape[n] >= 0 and
                                               any(rom.icons[n]))):
        u.append("ground")
    if n < 128 and (overlay_seen.get(n) or 1 <= n <= 12 or 22 <= n <= 26
                    or 0x6C <= n <= 0x7B):
        u.append("overlay")
    if 0x2E <= n <= 0x35 or n in R_TURRET_FIRE:
        u = ["ground"]
    return "+".join(u) or "-"


def icons_txt(rom, battles, cons_lines):
    ground_seen, overlay_seen = Counter(), Counter()
    for dm in battles:
        for sq in range(4096):
            w = dm.rw(MAP + 4 * sq)
            ground_seen[w & 0x1FF] += 1
            overlay_seen[w >> 9] += 1
    sicons = structure_icons(rom)
    out = ["# icons.txt - the Mega Drive Dune II's 360 map icons",
           "#",
           "# Written by tools/sega/port_icons.py; its docstring has the method.",
           "# Icon n is icons.png at column n % 16, row n // 16, 32 x 32 pixels,",
           "# RGBA in the battle CRAM's colours (v * 255 // 7), alpha 0 where",
           "# the cell's pixel is colour 0 of its line.  Ground icons go on",
           "# plane B, whose colour 0 shows the backdrop (CRAM 0: black);",
           "# overlays go on plane A, over the ground.  Icons 20-26 are",
           "# animated: icons_marker.png, a row an icon, a column a frame.",
           "# structanims.txt says how the structure icons are chosen.",
           "#",
           "# columns:",
           "#   icon      decimal, hex",
           "#   group     ICON.MAP group.entry, every one it appears at",
           "#   land      landscape type from $005818 (- none; S8 names them)",
           "#   use       ground / overlay: where the game puts it",
           "#   flags     P = priority bit (the fog: drawn over the sprites),",
           "#             B = blank (all 16 cells tile 0, fully transparent)",
           "#   seen      squares holding it as ground/overlay, summed over the",
           "#             recorded battles",
           "#",
           "# The art checks:"]
    for ln in cons_lines:
        out.append("#   " + ln)
    out.append("#")
    for n in range(N_ICONS):
        g = ",".join(f"{a}.{b}" for a, b in rom.group_entries(n)) or "-"
        ls = rom.landscape[n]
        land = f"{ls:2d}" if ls >= 0 else " -"
        fl = (("P" if any(e & 0x8000 for e in rom.icons[n]) else "")
              + ("B" if all(e == 0 for e in rom.icons[n]) else "")) or "-"
        use = icon_use(n, rom, sicons, ground_seen, overlay_seen)
        seen = f"{ground_seen.get(n, 0)}/{overlay_seen.get(n, 0) if n < 128 else 0}"
        out.append(f"{n:3d} ${n:03X}  {g:<39} {land}  {use:<14} {fl:<2} "
                   f"{seen:>12}  {describe(n, rom, sicons)}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------- structanims.txt

def structanims_txt(rom):
    users = {}

    def use(n, s):
        users.setdefault(n, []).append(s)
    for t, ty in enumerate(rom.types):
        use(ty["script"], f"struct_place: {STRUCT_NAMES[t]} placed")
    for lay, s in enumerate(rom.rubble):
        use(s, f"struct_remove: a {LAYOUT_NAMES[lay]} structure destroyed")
    for k in range(8):
        use(0x1B + k, f"emc_build_fire: Turret fires facing {DIRS[k]}")
        use(0x23 + k, f"emc_build_fire: R-Turret fires facing {DIRS[k]} "
            f"(target nearer than 3 squares)")
    o = []
    o += ["# structanims.txt - how the Mega Drive Dune II draws its structures",
          "#",
          "# Written by tools/sega/port_icons.py from the ROM tables the code",
          "# reads (addresses below).  Icons are the numbers of icons.txt /",
          "# icons.png.  Times are video frames (PAL, 49.7 a second): the",
          "# game's framesThisPass ($FFFFFE), which map_anim_tick and",
          "# struct_animate count down by.",
          "",
          "== map animations: map_anim_start $00AE58, map_anim_tick $00B1C2",
          "",
          "A script is (icon, delay) pairs from $06A9B4[n & $3F].  Starting it",
          "draws its first icon; when the delay has run out the next pair is",
          "read, and if that pair's delay is 0 or less the animation stops",
          "(that pair's icon is not drawn, and nothing is restored) - so the",
          "last icon drawn stays.  Starting one on a square stops the one",
          "already there (the record is keyed by the square).",
          "",
          "Drawing an icon (map_anim_draw $00B0A4):",
          "  icon 0          nothing is drawn (a pure wait)",
          "  icon >= 128, or flagged in $00B142 (46-53, 55-59, 72-74)",
          "                  stamped as GROUND over the structure's layout:",
          "                  square k (in the layout's offset order below) gets",
          "                  icon + k.  The square's overlay is cleared if it",
          "                  is 1-19 (craters, blanks) or $21, kept otherwise (fog,",
          "                  markers).",
          "  any other icon  goes in the start square's OVERLAY.",
          "Each square is redrawn at once.",
          "",
          "index  address  (icon,delay) ...                                  used by"]
    done = {}
    for n in range(64):
        p = rom.script_ptr[n]
        steps = " ".join(f"({ic:#05x},{d})" for ic, d in rom.scripts[n])
        u = "; ".join(users.get(n, [])) or "-"
        if p in done:
            o.append(f"{n:5d}  ${p:06X}  = script {done[p]}"
                     + (f"   {u}" if n in users else ""))
            continue
        done[p] = n
        o.append(f"{n:5d}  ${p:06X}  {steps}")
        o.append(f"{'':15}used by: {u}")
    o += ["",
          "Scripts 0-10 and 47-63 are one empty script ((0,1),(0,-1)): the",
          "Slab, 4-Slab and Wall start script 8 or 6 and nothing is drawn.",
          "Scripts 12 ($0DB, the Light Factory's own icons) and 16 ($0EF, the",
          "WOR's) are named by no structure type: the Light Factory draws the",
          "Heavy Factory's icons and the WOR the Barracks' (confirmed in the",
          "RAM maps of the recorded battles).  Icons $DB-$DE, $E9-$F2 are",
          "blank in the icon table: the Mega Drive has no art for them.",
          "",
          "== layouts: squares $06B826, offsets $06B738 (square = top-left + offset)",
          ""]
    for lay in range(7):
        o.append(f"  {lay} {LAYOUT_NAMES[lay]}  {len(rom.layouts[lay])} squares: "
                 + " ".join(str(x) for x in rom.layouts[lay])
                 + f"   rubble script {rom.rubble[lay]}")
    o += ["",
          "== the 19 structure types",
          "",
          "For each: the layout; the script struct_place starts (type +$3E);",
          "then the icons of its squares in every state, square k = the k-th",
          "offset of the layout.  'built' is what stays when the placing",
          "script ends; 'construction' is the first 90 frames (see the",
          "script: then 4 flashes of built/construction, 5 frames each, and",
          "it ends on built).  Every structure a mission places goes through",
          "struct_place too, so it also plays this.  'rubble' is stamped by",
          "struct_remove's script 20-40 frames after the structure is gone",
          "(until then the squares keep the structure's last icons).  There",
          "is no damaged state in the icons: a damaged structure looks the same.",
          ""]
    for t, ty in enumerate(rom.types):
        lay = ty["layout"]
        cnt = len(rom.layouts[lay])
        steps = rom.scripts[ty["script"]]
        o.append(f"{t:2d} {STRUCT_NAMES[t]}: layout {lay} ({LAYOUT_NAMES[lay]}),"
                 f" place script {ty['script']}")
        if t in (0, 1):
            o.append(f"   each paved square: ground $07E (builtSlabIcon), "
                     f"owner in the square; a 4-Slab paves the squares it can.")
            o.append(f"   no structure record stays; an explosion puts the "
                     f"square's mapGround back.")
            continue
        if t == 14:
            o.append("   the square's ground is the wall icon for the mask of its")
            o.append("   four neighbours that are walls (type 11) - struct_connect_wall:")
            o.append("   " + "  ".join(f"{m}:${rom.wall_icon[m]:03X}"
                                       for m in range(16)) + f"  ({MASK})")
            o.append("   placing one re-joins the neighbouring walls; a new wall is")
            o.append("   $022 before it is joined.  Destroyed: ground $021 (type 13),")
            o.append("   overlay kept (map_destroy_wall $01B160).")
            continue
        normal = steps[-2][0]
        build = steps[0][0] if steps[0][0] != normal else steps[1][0]
        o.append("   built:        " + " ".join(f"${normal + k:03X}"
                                               for k in range(cnt)))
        o.append("   construction: " + " ".join(f"${build + k:03X}"
                                               for k in range(cnt)))
        rs = rom.rubble[lay]
        if rs:
            ric = rom.scripts[rs][1][0]
            o.append(f"   rubble:       " + " ".join(f"${ric + k:03X}"
                                                   for k in range(cnt))
                     + f"   (script {rs}, after {rom.scripts[rs][0][1]} frames)")
        if t in (15, 16):
            base = 0x114 if t == 15 else 0x11C
            fire = ([0x2E + k for k in range(8)] if t == 15 else
                    [0x37, 0x38, 0x39, 0x3A, 0x3B, 0x48, 0x49, 0x4A])
            o.append("   facing (ground icon = base + facing, 0 = N, clockwise):")
            o.append("     " + " ".join(f"{DIRS[k]}:${base + k:03X}"
                                        for k in range(8)))
            o.append("   the facing IS the icon (icon - base); +$4E only mirrors it")
            o.append("   (struct_create sets it to ICON.MAP[group][1] = $165, emc_build_aim")
            o.append("   to 0-7; only the never-called emc_build_dir_to reads it).")
            o.append("   A new turret ends its place script on the base icon: facing N.")
            o.append("   aiming (emc_build_aim $00CB92, BUILD.EMC 9): one eighth a call")
            o.append("     towards the target, the shorter way; the structure's +$0F = 30.")
            o.append("   idle (struct_animate $00D6A4, unless flags2 bit 7 - it has a")
            o.append("     target): every random(100..125) frames, facing += random(0..2) - 1.")
            o.append("   firing (emc_build_fire $00CF54): script "
                     + ("27 + facing" if t == 15 else
                        "35 + facing, only if the target is nearer than 3 squares")
                     + ": ground")
            o.append("     " + " ".join(f"{DIRS[k]}:${fire[k]:03X}"
                                        for k in range(8))
                     + " for 9 frames, then the facing icon again.")
        if t == 12:
            o.append("   lights (struct_animate $00D77A): while state (+$5C) is 1")
            o.append("   (busy) - and on until back at frame 0 - every 20 frames")
            o.append("   frame = (frame + 1) & 3 (timer and frame at $FFD4B8 + 2 * slot;")
            o.append("   while +$0F is still negative the timer is set to random(72..84)):")
            o.append("     square 2 (+2):  " + " ".join(f"${x:03X}" for x in rom.lights[0]))
            o.append("     square 5 (+66): " + " ".join(f"${x:03X}" for x in rom.lights[1]))
            o.append("   (frame 0 = the built icon); each changed square whose overlay")
            o.append("   is 1-$7A has the fog lifted round it, radius 1.")
        if t == 11:
            o.append("   lights (struct_animate $00D77A), as the Refinery's:")
            o.append("     square 4 (+65):  " + " ".join(f"${x:03X}" for x in rom.lights[2]))
            o.append("     square 5 (+66):  " + " ".join(f"${x:03X}" for x in rom.lights[3]))
            o.append("     square 8 (+130): " + " ".join(f"${x:03X}" for x in rom.lights[5]))
            o.append("     square 7 (+129): " + " ".join(f"${x:03X}" for x in rom.lights[4]))
        if t not in (15, 16):
            o.append("   house marker: see below.")
        o.append("")
    o += ["== the house marker: struct_animate $00DB1A, struct_draw_house_marker $00B3E0",
          "",
          "Every structure but the Slabs, the Wall and the two turrets (their",
          "struct_animate cases end before it) is marked with its house, once",
          "(bit 4 of +$07).  Every 7 frames (timer $FFD54C + slot; the first",
          "time random(67..81)) the marker square is looked at: the square",
          "of the layout's bottom row, left column - top-left + $06B9FC[layout]",
          "(0, 0, 64, 64, 128, 64, 128).  The player's own structures are",
          "marked at once.  Another house's is marked only when that square's",
          "overlay is below $7B (not the full fog), and if the overlay is",
          "1-$7A the fog is first lifted round it, radius 1 (map_unfog_radius;",
          "so an enemy building half in sight reveals its corner).",
          "Marking sets the square's overlay to $16 + house - icons 22-26,",
          "whatever overlay was there - and writes the same 2x2 orb cells",
          "straight into plane A (cells 8, 9, 12, 13 of the square: the",
          "bottom-left quarter) in the house's palette line from $00B52C:",
          "Harkonnen 0, Atreides 1, Ordos 3, Fremen 1, Sardaukar 2.  Icon 25",
          "(Fremen) has line 0, so a Fremen marker changes colour when its",
          "square is next redrawn.  The orb is animated for all of them:",
          "icons_marker.png, 8 frames, the next every 8 video frames.",
          "",
          "== what is not an icon",
          "",
          "A damaged structure looks the same; smoke is a sprite (animations",
          "180-182, whose 6 tiles map_anim_tiles_b $00B028 cycles).  The",
          "selection box, the build progress and the ready/repair/upgrade",
          "markers are sprites too (struct_animate's tail, $009A62...).",
          ""]
    return "\n".join(o) + "\n"


# ------------------------------------------------------------------ check

def plane_layer(dump, tiles, pal, base, pw, ph):
    img = np.zeros((ph * 8, pw * 8, 4), dtype=np.uint8)
    for ty in range(ph):
        for tx in range(pw):
            a = base + (ty * pw + tx) * 2
            e = (dump.vram[a] << 8) | dump.vram[a + 1]
            px, line = cell(tiles, e)
            blk = pal[line * 16 + px.astype(np.int32)]
            blk[px == 0] = 0
            img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = blk
    return img


def check(rom, battles, sheet, marker):
    sizes = [32, 64, 64, 128]
    results = []
    all_px = all_bad = 0
    for dm in battles:
        pal = np.array([rgb(w) + (255,) for w in dm.cram], dtype=np.uint8)
        reg = dm.reg
        plane_a = (reg[2] & 0x38) << 10
        plane_b = (reg[4] & 0x07) << 13
        hs = (reg[13] & 0x3F) << 10
        pw, ph = sizes[reg[16] & 3], sizes[(reg[16] >> 4) & 3]
        tiles = [tile_indices(dm.tile(t)) for t in range(2048)]
        la = plane_layer(dm, tiles, pal, plane_a, pw, ph)
        lb = plane_layer(dm, tiles, pal, plane_b, pw, ph)
        h_a = w16(dm.vram, hs) & 0x3FF
        h_b = w16(dm.vram, hs + 2) & 0x3FF
        v_a = (dm.vsram[0] | (dm.vsram[1] << 8)) & 0x3FF
        v_b = (dm.vsram[2] | (dm.vsram[3] << 8)) & 0x3FF
        W, H = 320, 224
        sy, sx = np.mgrid[0:H, 0:W]
        vdp_a = la[(sy + v_a) % (ph * 8), (sx - h_a) % (pw * 8)]
        vdp_b = lb[(sy + v_b) % (ph * 8), (sx - h_b) % (pw * 8)]
        # which orb frame is in VRAM now
        now = dm.vram[ORB_TILE * 32:ORB_TILE * 32 + 128]
        frame = next((f for f in range(8) if rom.orb[f] == now), None)
        cx, cy = dm.rw(CAMX), dm.rw(CAMY)
        words = np.array([dm.rw(MAP + 4 * s) for s in range(4096)])
        look = dm.rw(LOOKAROUND, 1)

        def rebuild(ox, oy):
            mx, my = cx + ox + sx, cy + oy + sy
            sq = ((my >> 5) & 63) * 64 + ((mx >> 5) & 63)
            g = words[sq] & 0x1FF
            ov = words[sq] >> 9
            if look:
                ov = np.where(ov >= 0x34, 0, ov)
            iy, ix = my & 31, mx & 31
            eb = sheet[(g // 16) * 32 + iy, (g % 16) * 32 + ix]
            ea = sheet[(ov // 16) * 32 + iy, (ov % 16) * 32 + ix]
            orb = (ov >= 20) & (ov <= 26)
            if frame is not None:
                mk = marker[(np.clip(ov - 20, 0, 6)) * 32 + iy, frame * 32 + ix]
                ea = np.where(orb[..., None], mk, ea)
            return sq, ov, orb, ea, eb

        back = pal[reg[7] & 63]

        def screen(la_, lb_):
            return np.where(la_[..., 3:] > 0, la_,
                            np.where(lb_[..., 3:] > 0, lb_, back))
        sq, ov, is_orb, exp_a, exp_b = rebuild(0, 0)
        # the control: the same rebuild with the view origin a square off
        _, _, _, ca, cb = rebuild(32, 0)
        control = int(np.any(screen(ca, cb) != screen(vdp_a, vdp_b),
                             axis=2).sum())
        bad_b = np.any(exp_b != vdp_b, axis=2)
        bad_a = np.any(exp_a != vdp_a, axis=2)
        bad = bad_a | bad_b
        # what the screen shows: A over B over the backdrop
        see_vdp = screen(vdp_a, vdp_b)
        see_exp = screen(exp_a, exp_b)
        visible = np.any(see_vdp != see_exp, axis=2)
        # a cell the view drawer never wrote: transparent on both planes, in
        # the partial column at the right or the partial row at the bottom
        edge = (sx >= W - (cx & 7)) | (sy >= H - ((cy + H) & 7))
        empty = (vdp_a[..., 3] == 0) & (vdp_b[..., 3] == 0)
        stale = bad & edge & empty & ~visible
        orb_bad = bad & is_orb & ~stale
        other = bad & ~is_orb & ~stale
        n = W * H
        all_px += n
        all_bad += int(other.sum())
        bad_sq = sorted({int(s) for s in sq[other]})
        results.append({"name": dm.name, "b": int(bad_b.sum()),
                        "a": int(bad_a.sum()), "stale": int(stale.sum()),
                        "marker": int(orb_bad.sum()), "other": int(other.sum()),
                        "visible": int(visible.sum()), "frame": frame,
                        "control": control,
                        "shown": int((is_orb & (exp_a[..., 3] > 0)).sum()),
                        "squares": bad_sq[:8]})
    return results, all_px, all_bad


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "src/res/art"))
    ap.add_argument("--states", nargs="*", default=DEFAULT_STATES,
                    help="save-state globs, relative to the repository")
    ap.add_argument("--no-dump", action="store_true",
                    help="use the dumps already in tmp/port-icons/dumps")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    rom = Rom(args.rom)
    if args.no_dump:
        dirs = sorted(p for p in DUMPS.iterdir() if p.is_dir())
    else:
        dirs = dump_states(args.states)
    battles = load_battles(dirs)
    ok, cons = consistency(rom, battles)
    for ln in cons:
        print(ln)
    if not ok:
        sys.exit("error: the icon art or the CRAM differs between battles")

    sheet, marker = render_icons(rom, battles[0])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet, "RGBA").save(out / "icons.png")
    Image.fromarray(marker, "RGBA").save(out / "icons_marker.png")
    (out / "icons.txt").write_text(icons_txt(rom, battles, cons))
    (out / "structanims.txt").write_text(structanims_txt(rom))
    print(f"wrote {out}/icons.png, icons_marker.png, icons.txt, structanims.txt")

    if args.check:
        res, px, bad = check(rom, battles, sheet, marker)
        print(f"{'state':<22} {'planeB':>6} {'planeA':>6} {'stale':>6} "
              f"{'marker':>6} {'other':>6} {'screen':>6} orb "
              f"{'mk px':>5} {'ctrl':>6}  squares")
        for r in res:
            print(f"{r['name']:<22} {r['b']:6d} {r['a']:6d} {r['stale']:6d} "
                  f"{r['marker']:6d} {r['other']:6d} {r['visible']:6d} "
                  f"{'-' if r['frame'] is None else r['frame']:>3} "
                  f"{r['shown']:5d} {r['control']:6d}  "
                  + " ".join(f"{s // 64},{s % 64}" for s in r['squares']))
        vis = sum(r["visible"] for r in res)
        print(f"{len(res)} battles, {px} screen pixels on each plane; "
              f"{px - bad} match or are explained ({100 * (px - bad) / px:.4f}%);"
              f" {px - vis} of the composed screen match "
              f"({100 * (px - vis) / px:.4f}%)")
        if bad:
            sys.exit(1)


if __name__ == "__main__":
    main()
