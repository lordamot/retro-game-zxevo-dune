#!/usr/bin/env python3
"""port_sprites.py - every sprite a Mega Drive Dune II battle draws, as port art.

    port_sprites.py                 write src/res/art/sprites/*.png and
                                    src/res/art/sprites.txt, effects.txt
    port_sprites.py --check         also run battle save states and compare
                                    what this predicts with the machine
    port_sprites.py --check-only    just the comparison

Everything comes out of orig/dune2.gen; the save states under
tmp/sega/spec/ are only used by --check.  tools/sega/sega_sprites.py
decoded the animation table and its lists; this tool works out *which*
of those the running game puts on screen for what, and bakes them into
pictures a machine without flips or sprite hardware can blit.

## How a sprite is drawn ($001088 spr_render)

A sprite object (16 bytes in the pool at $FFE6A8, chain head $FFF3AC) has
+0 its owner (a record whose +0 is y.w, +2 x.w, both 1/8 pixel, and +4
the layer byte), +6 an attribute word (bits 15-11: priority, V flip, H
flip, palette line; +7 is its flag byte) and +8 a frame list.  Each
piece of the list is drawn at owner/8 - camera ($FFE3BE x, $FFE3C0 y) +
the piece's own x/y.  The piece's attribute keeps bits 15 and 12-0 and
has the sprite's bits 15-11 exclusive-ored in ($001248-$001258): the
sprite's flip flips every piece **inside its own box**, the offsets are
not mirrored.  A piece with palette bits of its own keeps them, one
without takes the sprite's ($00125E-$001272).  Flag bit 2 adds the
one-pixel shake of $001164 picked by the unit's +$72 (wobbleIndex);
bit 5 blinks; bit 7 hides.  The chain is kept in descending order of the
layer byte (the list's tag, copied to owner +4 by $00954E) then y plus
the first piece's y ($0012F6) - but only re-sorted when a sprite is made
- and the VDP draws the first sprite of its table on top.

## What a unit shows ($01220C unit_draw)

The unit's sprite handle is +$10 and its owner is the unit's +$A, so the
position is +$A (y) and +$C (x).  The frame is the type's base animation
(+$46 of the type record at $06BC00; `sprite` in units.txt) plus an
offset for the hull facing +$6A, and a flip, by the type's display group
(+$4C):

    group 0  the base, no flip (the bullet); the Sonic Blast (type $18)
             instead one of 16 animations at $06C6C4 by (facing+8)>>4
    group 1  8 directions, (facing+16)>>5, table $06C660: (offset, flip)
    group 2  16 directions, (facing+8)>>4, table $06C680
    group 3,4 infantry: 8 directions through $06C640 give 0 up, 1 side,
             2 down (x3), plus the walk step $06C6C0[+$73 & 3] = 0,1,0,2
    group 5  as group 1, then the 'Thopter's own $00A704

A flip value is bit 0 H, bit 1 V ($0095E0 rotates it to bits 11-12).
The Carryall (type 0) uses base+3 while +3 (linkedID) is not $FF.  The
Tank and Siege Tank (9, 10) go to the 256-frame table at $02EC72: four
tables of 64 frames, frame = hull octant * 8 + turret octant (+$6D), both
(f+16)>>5; tables 0/1 are Tank/Siege at rest and 2/3 the same with the
turret recoiled a pixel, set by the shot at $044B6C/$044B9E, which also
sets flags2 bit 6 so unit_draw leaves the frame alone; the turn and aim
ticks clear the bit after their redraw, so the recoil shows until the
redraw after that.  Every frame is two pieces, turret first (on
top), hull second, both 24x24 at (-12,-12) save the recoil.  The
Sandworm (25) is never redrawn: it keeps its base animation 213 in
palette line 0.  The Frigate DMAs one of four 16-tile pictures to $7FC0
($00A6AE; the fourth, the cargo, while flags2 bit 9 is set).  The
'Thopter's three direction lists at $00A73E draw tiles $4B6/$4BF/$4C8,
which $00AFCA overwrites every ten ticks with one of three rotor frames
($00AF76, played 2,1,0 by $FFD304).  A Harvester on the map, harvesting
(+$54 = 5) on spice (landscape 8 or 9), shows a second sprite (handle in
+$5A, animation $DF made in house 0's palette) with the list
$0641E6[(facing+16)>>5 + 8 * (+$73)] ($009678): three dust frames at
eight offsets.

## The palette

A unit's sprite gets its house's palette line from $009584: Harkonnen 0,
Atreides 1, Ordos 3, Fremen 1, Sardaukar 2, Mercenary 0 (the table has
five houses; 5-7 read zeros).  List tag $0B (the bullet, the Saboteur,
the smoke) skips it and stays in line 0.  The battlefield's CRAM is the
64 colours at $0A6C90 for every mission - the check compares it with
each state's CRAM.  House-coloured frames are therefore written four
times, `house-p0..p3.png`, one per palette line, in the same layout;
frames whose pieces all carry their own palette, or that the game only
ever shows in one line, go to `fixed.png`.

## Explosions ($00AEDA fx_explosion_start, $00B224 fx_explosion_tick)

24 scripts at $0C80A2 of (animation, ticks) words, ended by a time of 0
or less.  The first step's sprite is made in the palette of the house
the caller passes; every later step is remade by $00B2A6 with house 0.
map_make_explosion passes 3 (line 1) except for type 19 (house 0); the
Deviator's cloud passes 3; a unit's death animation (20 infantry, 21 the
rest) its own house; being run over (22, 23) house 0.  Only pieces
without palette bits care.

## Markers, cursors

The house marker under a structure is not a sprite: $00B3E0 writes the
2x2 cells $2BE-$2C1 into the plane in the house's line (table $00B52C,
the same houses-to-lines as $009584), and the battle frame hook
$00608E cycles those four tiles through the eight 16x16 frames at
$00690C every eighth frame.  The structure markers ('OK', the repair
hammer, the low-power bolt) are sprites of $009A62/$009B26/$009AD6
hanging off the structure's position.  The cursor and the selection
bracket are the two sprites $004B34 re-points: the pixels are copied into
VRAM $F780 (tile $7BC) and $F880 ($7C4) a frame after the list is set.
The brackets round structures and the placement grids are written as
their pieces (a 16x16 corner, a 32x32 square) with the offsets; the rest
is flattened.

## The check

`--check` loads save states, runs them a few frames at a time and dumps
RAM, VRAM, CRAM and the VDP registers.  For every unit in use it
predicts, from its record alone, the frame list, flips and palette line
of its sprite, and compares them with the sprite object; then from the
sprite chain and the camera it predicts every piece the VDP gets, and
compares with the sprite buffer at $FFE428 that $006712 sends to the
VDP; then it renders what those pieces show from the live VRAM and CRAM
and compares it pixel for pixel with the frame written here - for the
units, the Harvester's dust, the explosions, the cursor and the bracket,
and the house marker's tiles.  The saved battles have no 'Thopter,
Frigate, MCV or rockets, so copies of six of them are patched (see
patched_state) into every type, facing, walk step and house, with a
unit or structure selected so the bracket shows.  A mismatch the game's
own timing accounts for (a walk step not yet redrawn, a DMA a frame
behind, tiles two sprites share, a unit moved after the sprite pass) is
counted as explained and named; anything else is printed.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_gfx import lcw                                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
ROM_PATH = ROOT / "orig/dune2.gen"
OUT_DIR = ROOT / "src/res/art"
RUN = ROOT / "bin/gen/retro-run"
CORE = ROOT / "bin/gen/genesis_plus_gx_libretro.so"
STATES = ROOT / "tmp/sega/spec"
WORK = ROOT / "tmp/port-sprites"

ANIM_TABLE, ANIM_COUNT = 0x060E84, 357
PRELOAD = 0x00A488
BATTLE_PALETTE = 0x0A6C90           # the battlefield's 64 colours
UNIT_TYPES = 0x06BC00               # 27 records of $5C
TYPE_SPRITE, TYPE_GROUP = 0x46, 0x4C
DIR8_INFANTRY = 0x06C640            # (offset, flip) x 8
DIR8 = 0x06C660                     # (offset, flip) x 8
DIR16 = 0x06C680                    # (offset, flip) x 16
WALK = 0x06C6C0                     # 4 bytes
DIR16_SONIC = 0x06C6C4              # 16 animations, the Sonic Blast
TANK_FRAMES = 0x02EC72              # 4 x 64 frames of 26 bytes
HARVEST_LISTS = 0x0641E6            # 3 x 8 list pointers
THOPTER_LISTS = 0x00A73E            # 4 list pointers
ROTOR_ORDER = 0x00AFBE              # 3 pointers to 3 x (ptr, vram, words)
FRIGATE_PIXELS = 0x00A6F4           # 4 pointers, 512 bytes each to $7FC0
FRIGATE_VRAM = 0x7FC0
SMOKE_FRAMES = 0x00B01C             # 3 pointers, 192 bytes each to $DF20
SMOKE_VRAM = 0xDF20
FX_SCRIPTS, FX_COUNT = 0x0C80A2, 24
HOUSE_LINES = 0x009584              # 8 words
MARKER_FRAMES = 0x00690C            # 8 frames of 4 tiles, to $57C0
MARKER_LINES = 0x00B52C
MARKER_DROP = 0x00B3D0              # how far below the position, by layout
MARKER1_LISTS = 0x009AB6            # 8 list pointers ("ready")
MARKER2_LISTS = 0x0659F6            # 7 list pointers ("repair")
MARKER0_LIST = 0x0658E0             # one list ("full")
PLACE_LISTS = 0x064FE2              # 16 placement-cursor lists
PLACE_PIXELS = 0x06473E             # 512 bytes, to $F780 and $F880
CURSOR_SLOTS = (0xF780, 0xF880)
SHAKE = 0x001164                    # 8 (dx, dy) word pairs

HOUSES = ["Harkonnen", "Atreides", "Ordos", "Fremen", "Sardaukar",
          "Mercenary"]
UNIT_NAMES = ["Carryall", "'Thopter", "Infantry", "Troopers", "Soldier",
              "Trooper", "Saboteur", "Launcher", "Deviator", "Tank",
              "Siege Tank", "Devastator", "Sonic Tank", "Trike",
              "Raider Trike", "Quad", "Harvester", "MCV", "Death Hand",
              "Rocket", "ARocket", "GRocket", "MiniRocket", "Bullet",
              "Sonic Blast", "Sandworm", "Frigate"]
CELLS = [((s >> 2) + 1) * ((s & 3) + 1) for s in range(16)]


# ---------------------------------------------------------------- the ROM

class Rom:
    def __init__(self, path=ROM_PATH):
        self.b = Path(path).read_bytes()

    def w(self, a):
        return int.from_bytes(self.b[a:a + 2], "big")

    def s(self, a):
        v = self.w(a)
        return v - 0x10000 if v & 0x8000 else v

    def l(self, a):
        return int.from_bytes(self.b[a:a + 4], "big")

    def ptr(self, a):
        return self.l(a) & 0xFFFFFF

    def pieces(self, a):
        """[(tile, attr, size, x, y)] of the frame list at `a`."""
        out = []
        for k in range(self.w(a) + 1):
            p = a + 2 + 12 * k
            at, sz = self.w(p + 8), self.b[p + 6]
            out.append((at & 0x7FF, at, sz, self.s(p + 10), self.s(p + 4)))
        return out

    def anim(self, n):
        """(pixels tag, pixels, list tag, list) of animation n."""
        p, q = self.l(ANIM_TABLE + 8 * n), self.l(ANIM_TABLE + 8 * n + 4)
        return p >> 24, p & 0xFFFFFF, q >> 24, q & 0xFFFFFF

    def utype(self, t, off):
        return self.s(UNIT_TYPES + 0x5C * t + off)

    def palette(self):
        """64 colours as the core keeps CRAM: nine bits, BBBGGGRRR."""
        out = []
        for i in range(64):
            v = self.w(BATTLE_PALETTE + 2 * i)
            out.append(((v >> 9) & 7) << 6 | ((v >> 5) & 7) << 3 |
                       ((v >> 1) & 7))
        return out

    def house_line(self, house):
        return self.w(HOUSE_LINES + 2 * (house & 7)) >> 13


def rgb(c9):
    return ((c9 & 7) * 255 // 7, ((c9 >> 3) & 7) * 255 // 7,
            ((c9 >> 6) & 7) * 255 // 7)


def base_vram(rom):
    """VRAM with what $00A41E preloads for every battle."""
    v = bytearray(0x10000)
    a = PRELOAD
    while rom.l(a):
        d3, p = rom.l(a), rom.l(a + 4)
        vram, n = d3 >> 16, (d3 & 0xFFFF) * 2
        src = p & 0xFFFFFF
        data = rom.b[src:src + n] if p >> 31 else \
            lcw(rom.b[src:src + 0x10000])[0]
        assert len(data) >= n, f"preload ${src:06X}"
        v[vram:vram + n] = data[:n]
        a += 8
    return v


def with_dma(v, dst, data):
    v = bytearray(v)
    v[dst:dst + len(data)] = data
    return v


# ------------------------------------------------------------ the picture

class Pic:
    """Pixels of one baked frame: {(x, y): (line, index)} relative to the
    object's position.  line None = the sprite's (the house's) line."""

    def __init__(self, px):
        self.px = px
        if px:
            xs = [x for x, _ in px]
            ys = [y for _, y in px]
            self.dx, self.dy = min(xs), min(ys)
            self.w, self.h = max(xs) - self.dx + 1, max(ys) - self.dy + 1
        else:
            self.dx = self.dy = 0
            self.w = self.h = 0

    @property
    def housed(self):
        return any(ln is None for ln, _ in self.px.values())

    def key(self):
        return (self.dx, self.dy, tuple(sorted(self.px.items(),
                                               key=lambda kv: kv[0])))

    def rgba(self, pal, line):
        from PIL import Image
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        p = img.load()
        for (x, y), (ln, i) in self.px.items():
            p[x - self.dx, y - self.dy] = \
                rgb(pal[(line if ln is None else ln) * 16 + i]) + (255,)
        return img


def draw_pieces(vram, pcs, sflip=0, sline=None):
    """What the VDP draws for a list: {(x, y): (line, index)}.  `pcs` are
    (tile, attr, size, x, y); the first piece is on top.  `sflip` is the
    sprite's flip (bit 0 H, bit 1 V); `sline` its palette line, None for
    'the house's'."""
    px = {}
    for tile, at, sz, x0, y0 in reversed(pcs):
        cw, ch = (sz >> 2) + 1, (sz & 3) + 1
        hf = bool(at & 0x800) ^ bool(sflip & 1)
        vf = bool(at & 0x1000) ^ bool(sflip & 2)
        line = (at >> 13) & 3 if at & 0x6000 else sline
        for cx in range(cw):
            for cy in range(ch):
                t = (tile + cx * ch + cy) & 0x7FF
                sx = (cw - 1 - cx) if hf else cx
                sy = (ch - 1 - cy) if vf else cy
                for yy in range(8):
                    for xx in range(8):
                        b = vram[t * 32 + yy * 4 + xx // 2]
                        c = b >> 4 if xx % 2 == 0 else b & 15
                        if not c:
                            continue
                        dx = 7 - xx if hf else xx
                        dy = 7 - yy if vf else yy
                        px[(x0 + sx * 8 + dx, y0 + sy * 8 + dy)] = (line, c)
    return px


# ------------------------------------------------------------- the catalogue

class Catalogue:
    """Unique baked frames.  A frame is housed (written four times) when a
    visible pixel takes the sprite's palette line and that line is the
    house's; otherwise it is fixed, with every line resolved."""

    def __init__(self, rom):
        self.rom = rom
        self.base = base_vram(rom)
        self.frames = []             # [Pic]
        self.names = []              # [[name, ...]]
        self.index = {}              # key -> id

    def add(self, name, pic):
        if not pic.px:
            return None
        k = pic.key()
        if k in self.index:
            i = self.index[k]
            if name not in self.names[i]:
                self.names[i].append(name)
            return i
        i = len(self.frames)
        self.index[k] = i
        self.frames.append(pic)
        self.names.append([name])
        return i

    # the VRAM a record is drawn from
    def vram_for(self, n, extra=None):
        pt, pa, lt, la = self.rom.anim(n)
        v = self.base
        if pt & 0x80:
            tile, at, sz, _, _ = self.rom.pieces(la)[0]
            v = with_dma(v, tile * 32, self.rom.b[pa:pa + CELLS[sz] * 32])
        if extra:
            for dst, data in extra:
                v = with_dma(v, dst, data)
        return v

    def anim_pic(self, n, flip=0, line=None, extra=None, lst=None):
        """Animation n as anim_set_sprite shows it: `line` None = the
        house's, unless the list tag is $0B (line 0)."""
        pt, pa, lt, la = self.rom.anim(n)
        if lt == 0x0B:
            line = 0
        return Pic(draw_pieces(self.vram_for(n, extra),
                               self.rom.pieces(lst or la), flip, line))


# ------------------------------------------------------ what a unit shows

def dir8(f):
    return ((f + 16) & 0xFF) >> 5


def dir16(f):
    return ((f + 8) & 0xFF) >> 4


def unit_choice(rom, t, facing, turret=0, walk=0, linked=0xFF, flags2=0):
    """unit_draw ($01220C) for a unit of type t.  Returns one of
        ('anim', animation, flip)
        ('tank', table, hull octant, turret octant)
        ('thopter', frame 0-3, flip)
        ('frigate', frame 0-3, flip)
        None - unit_draw leaves the sprite as it is."""
    if t in (9, 10):
        if flags2 & 0x40:
            return None
        return ("tank", t - 9, dir8(facing), dir8(turret))
    base = rom.utype(t, TYPE_SPRITE)
    if t == 0 and linked != 0xFF:
        base += 3
    grp = rom.utype(t, TYPE_GROUP)
    if grp < 0 or grp > 5:
        return ("anim", base, 0)
    if grp == 0:
        if t == 0x18:
            return ("anim", rom.s(DIR16_SONIC + 2 * dir16(facing)), 0)
        return ("anim", base, 0)
    if grp == 2:
        d = dir16(facing)
        return ("anim", base + rom.s(DIR16 + 4 * d), rom.s(DIR16 + 4 * d + 2))
    if grp in (3, 4):
        d = dir8(facing)
        off, flip = rom.s(DIR8_INFANTRY + 4 * d), rom.s(DIR8_INFANTRY + 4 * d + 2)
        return ("anim", base + 3 * off + rom.b[WALK + (walk & 3)], flip)
    # groups 1 and 5
    if t == 0x19:
        return None
    d = dir8(facing)
    off, flip = rom.s(DIR8 + 4 * d), rom.s(DIR8 + 4 * d + 2)
    if t == 1:
        return ("thopter", off, flip)
    if t == 0x1A:
        return ("frigate", 3 if flags2 & 0x200 else off, flip)
    return ("anim", base + off, flip)


def choice_list(rom, ch):
    """The frame list and sprite flip a choice puts on the sprite."""
    kind = ch[0]
    if kind == "anim":
        return rom.anim(ch[1])[3], ch[2]
    if kind == "tank":
        _, tb, h, tu = ch
        return TANK_FRAMES + 26 * (64 * tb + 8 * h + tu), 0
    if kind == "thopter":
        return rom.ptr(THOPTER_LISTS + 4 * (ch[1] & 3)), ch[2]
    if kind == "frigate":
        return rom.anim(298)[3], ch[2]
    raise ValueError(ch)


def rotor_vram(rom, phase):
    """The three 9-tile rotor blocks of frame `phase` (0-2, as $FFD304)."""
    fr = rom.ptr(ROTOR_ORDER + 4 * phase)
    out = []
    for k in range(3):
        e = fr + 8 * k
        p, v, n = rom.ptr(e), rom.w(e + 4), rom.w(e + 6) * 2
        out.append((v, rom.b[p:p + n]))
    return out


def smoke_vram(rom, phase):
    p = rom.ptr(SMOKE_FRAMES + 4 * phase)
    return [(SMOKE_VRAM, rom.b[p:p + 192])]


def frigate_vram(rom, frame):
    p = rom.ptr(FRIGATE_PIXELS + 4 * (frame & 3))
    return [(FRIGATE_VRAM, rom.b[p:p + 512])]


# ----------------------------------------------------------- building it

def build(rom):
    """The catalogue and the tables that say what each frame is for."""
    cat = Catalogue(rom)
    T = {"units": {}, "tank": {}, "harvest": {}, "fx": {}, "smoke": [],
         "marker": [], "smarkers": {}, "cursors": {}, "place": [],
         "worm": None, "rotor": [], "frigate": {}}

    # -- ground and air units through unit_draw
    for t in range(27):
        if t in (9, 10, 25):
            continue
        grp = rom.utype(t, TYPE_GROUP)
        rows = []
        variants = [("", 0xFF)] + ([("carrying", 0)] if t == 0 else [])
        for vname, linked in variants:
            walks = range(4) if grp in (3, 4) else [0]
            if t == 1:
                for d in range(8):
                    ch = unit_choice(rom, t, d * 32)
                    lst, flip = choice_list(rom, ch)
                    ids = []
                    for ph in range(3):
                        ids.append(cat.add(f"thopter.d{d}.r{ph}", Pic(
                            draw_pieces(cat.vram_for(289, rotor_vram(rom, ph)),
                                        rom.pieces(lst), flip, None))))
                    rows.append((vname, d, None, ch, ids))
                continue
            ndir = 16 if grp == 2 or t == 0x18 else 8
            for d in range(ndir):
                f = d * (256 // ndir)
                for wk in walks:
                    ch = unit_choice(rom, t, f, walk=wk, linked=linked)
                    if ch[0] == "frigate":
                        ids = [cat.add(f"frigate.f{ch[1]}.x{ch[2]}", Pic(
                            draw_pieces(cat.vram_for(298, frigate_vram(rom, ch[1])),
                                        rom.pieces(rom.anim(298)[3]), ch[2], None)))]
                        chc = unit_choice(rom, t, f, flags2=0x200)
                        ids.append(cat.add(f"frigate.f{chc[1]}.x{chc[2]}", Pic(
                            draw_pieces(cat.vram_for(298, frigate_vram(rom, chc[1])),
                                        rom.pieces(rom.anim(298)[3]), chc[2], None))))
                        rows.append((vname, d, wk, ch, ids))
                        continue
                    n, flip = ch[1], ch[2]
                    ids = [cat.add(f"a{n}{flipname(flip)}",
                                   cat.anim_pic(n, flip))]
                    rows.append((vname, d, wk if grp in (3, 4) else None, ch, ids))
        T["units"][t] = rows

    # -- the Tank and Siege Tank, hull and turret apart
    for tb in range(4):
        for h in range(8):
            for tu in range(8):
                a = TANK_FRAMES + 26 * (64 * tb + 8 * h + tu)
                tur, hull = rom.pieces(a)
                tank = "tank" if tb in (0, 2) else "siege"
                hid = cat.add(f"{tank}.hull.o{h}",
                              Pic(draw_pieces(cat.base, [hull[:3] + (-12, -12)])))
                tid = cat.add(f"{tank}.turret.o{tu}",
                              Pic(draw_pieces(cat.base, [tur[:3] + (-12, -12)])))
                T["tank"][(tb, h, tu)] = (hid, tid, tur[3] + 12, tur[4] + 12,
                                          hull[3] + 12, hull[4] + 12)

    # -- the Sandworm: animation 213, never redrawn, line 0
    T["worm"] = cat.add("sandworm", cat.anim_pic(213, 0, 0))

    # -- the Harvester's dust: 3 frames x 8 places, line 0
    for fr in range(3):
        for d in range(8):
            lst = rom.ptr(HARVEST_LISTS + 4 * (d + 8 * fr))
            pcs = rom.pieces(lst)
            pic = Pic(draw_pieces(cat.base, [pcs[0][:3] + (0, 0)], 0, 0))
            i = cat.add(f"harvest.f{fr}", pic)
            T["harvest"][(fr, d)] = (i, pcs[0][3], pcs[0][4])

    # -- smoke: animation 180's tiles cycled by $00B028
    for ph in (2, 1, 0):
        T["smoke"].append((ph, cat.add(f"smoke.p{ph}", Pic(draw_pieces(
            with_dma(cat.base, SMOKE_VRAM, smoke_vram(rom, ph)[0][1]),
            rom.pieces(rom.anim(180)[3]), 0, 0)))))

    # -- the explosion scripts
    for n in range(FX_COUNT):
        p = rom.ptr(FX_SCRIPTS + 4 * n)
        first = {19: 0, 22: 0, 23: 0}.get(n, 3)   # the house passed
        steps = []
        k = 0
        while True:
            fr, tk = rom.s(p), rom.s(p + 2)
            p += 4
            if tk <= 0:
                break
            if fr < 0:
                steps.append((None, tk))
                break
            house = first if k == 0 else 0
            if n in (20, 21) and k == 0:
                line = None          # the dying unit's own house
            else:
                line = rom.house_line(house)
            pt, pa, lt, la = rom.anim(fr)
            if fr == 180:
                ids = [T["smoke"][i][1] for i in range(3)]
                steps.append((("smoke", ids), tk))
            else:
                pic = cat.anim_pic(fr, 0, line)
                i = cat.add(f"a{fr}" + ("" if line is None or not pic.px
                                         or not _uses_sprite_line(rom, fr)
                                         else f".l{line}"), pic)
                steps.append((i, tk))
            k += 1
        T["fx"][n] = steps

    # -- the house marker: 8 frames of $2BE-$2C1, line of the house
    for h in range(5):                    # $00B52C says what $009584 says
        assert (rom.l(MARKER_LINES + 4 * h) >> 29) & 3 == rom.house_line(h)
    for fr in range(8):
        v = with_dma(cat.base, 0x2BE * 32,
                     rom.b[MARKER_FRAMES + 128 * fr:MARKER_FRAMES + 128 * fr + 128])
        # plane cells: $2BE $2BF over $2C0 $2C1
        pcs = [(0x2BE, 0, 0, 0, 0), (0x2BF, 0, 0, 8, 0),
               (0x2C0, 0, 0, 0, 8), (0x2C1, 0, 0, 8, 8)]
        T["marker"].append(cat.add(f"house_marker.f{fr}",
                                   Pic(draw_pieces(v, pcs, 0, None))))

    # -- structure markers (sprites), line 0 (the sprite has no house)
    for name, lists in (("ready", [rom.ptr(MARKER1_LISTS + 4 * i) for i in range(8)]),
                        ("repair", [rom.ptr(MARKER2_LISTS + 4 * i) for i in range(7)]),
                        ("power", [MARKER0_LIST])):
        pcs = rom.pieces(lists[0])
        i = cat.add(f"marker.{name}",
                    Pic(draw_pieces(cat.base, [pcs[0][:3] + (0, 0)], 0, 0)))
        T["smarkers"][name] = (i, [(rom.pieces(a)[0][3], rom.pieces(a)[0][4])
                                   for a in lists])

    # -- the cursor sprites.  One or two pieces are flattened; the
    # brackets round structures and the placement grids are kept as their
    # pieces (a 16x16 corner, a 32x32 square) and the offsets, because
    # flattened they are 100 x 100 of almost nothing.
    def parts(v, pcs, name):
        return [(cat.add(name, Pic(draw_pieces(v, [p[:3] + (0, 0)], 0, 0))),
                 p[3], p[4]) for p in pcs]
    for n, what in CURSOR_ANIMS:
        pt, pa, lt, la = rom.anim(n)
        pcs = rom.pieces(la)
        slot = CURSOR_SLOTS[1] if min(p[0] for p in pcs) >= 0x7C4 else CURSOR_SLOTS[0]
        v = with_dma(cat.base, slot, rom.b[pa:pa + 256])
        if slot == CURSOR_SLOTS[0]:       # d4 = d3: the same pixels twice
            v = with_dma(v, CURSOR_SLOTS[1], rom.b[pa:pa + 256])
        if len(pcs) <= 2:
            T["cursors"][n] = (what, cat.add(f"cursor.a{n}",
                                             Pic(draw_pieces(v, pcs, 0, 0))), None)
        else:
            kind = "square" if pcs[0][2] == 0xF else "corner"
            T["cursors"][n] = (what, None, parts(v, pcs, f"cursor.{kind}"))
    v = with_dma(cat.base, CURSOR_SLOTS[0], rom.b[PLACE_PIXELS:PLACE_PIXELS + 512])
    for k in range(16):
        pcs = rom.pieces(rom.ptr(PLACE_LISTS + 4 * k))
        T["place"].append(parts(v, pcs, "cursor.square"))
    return cat, T


def _uses_sprite_line(rom, n):
    return any(not (at & 0x6000) for _, at, _, _, _ in
               rom.pieces(rom.anim(n)[3]))


def flipname(flip):
    return {0: "", 1: ".h", 2: ".v", 3: ".hv"}[flip & 3]


# The cursor animations the battle uses, from the code that picks them
# ($028596-$0287C6, the tables $0C7EE2 and $0C7EFE, $004AE2, $0163E2).
CURSOR_ANIMS = [
    (0, "the square cursor: nothing of the player's selected"),
    (5, "the crosshair: one of the player's units selected, where to send it"),
    (6, "bracket round the selected unit, the player's"),
    (29, "bracket round a selected unit of another house, or the player's Saboteur"),
    (9, "bracket round a 1x1, 2x1 or 1x2 structure ($0C7EFE by layout 0-2)"),
    (10, "bracket round a 2x2 structure (layout 3, 9)"),
    (11, "bracket round a 2x3 or 3x2 structure (layout 4, 5)"),
    (30, "bracket round a 3x3 structure (layout 6, 7)"),
    (1, "placement, fits, layout 0 ($0C7EE2)"),
    (4, "placement, fits, layout 3"),
    (12, "placement, fits, layout 4"),
    (13, "placement, fits, layout 5"),
    (14, "placement, fits, layout 6"),
    (15, "placement, blocked, layout 0"),
    (18, "placement, blocked, layout 3"),
    (19, "placement, blocked, layout 4"),
    (20, "placement, blocked, layout 5"),
    (21, "placement, blocked, layout 6"),
]


# ------------------------------------------------------------- the sheets

def pack(cat, ids, width=256):
    """Shelf-pack frames: {id: (x, y)}, height."""
    order = sorted(ids, key=lambda i: (-cat.frames[i].h, i))
    pos, x, y, row = {}, 0, 0, 0
    for i in order:
        f = cat.frames[i]
        if x + f.w > width:
            x, y, row = 0, y + row + 1, 0
        pos[i] = (x, y)
        x += f.w + 1
        row = max(row, f.h)
    return pos, y + row


def write_sheets(cat, pal, outdir):
    from PIL import Image
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        old.unlink()
    housed = [i for i, f in enumerate(cat.frames) if f.housed]
    fixed = [i for i, f in enumerate(cat.frames) if not f.housed]
    place = {}
    pos, h = pack(cat, housed)
    for line in range(4):
        img = Image.new("RGBA", (256, h), (0, 0, 0, 0))
        for i, (x, y) in pos.items():
            img.paste(cat.frames[i].rgba(pal, line), (x, y))
        img.save(outdir / f"house-p{line}.png")
    for i, xy in pos.items():
        place[i] = ("house-p{L}",) + xy
    pos, h = pack(cat, fixed)
    img = Image.new("RGBA", (256, h), (0, 0, 0, 0))
    for i, (x, y) in pos.items():
        img.paste(cat.frames[i].rgba(pal, 0), (x, y))
    img.save(outdir / "fixed.png")
    for i, xy in pos.items():
        place[i] = ("fixed",) + xy
    return place


# ------------------------------------------------------------- the index

def ids_text(ids):
    return " ".join("-" if i is None else str(i) for i in ids)


def write_index(rom, cat, T, place, out):
    pal = rom.palette()
    L = []
    say = L.append
    say("# sprites.txt - every sprite a Mega Drive Dune II battle draws, for the port.")
    say("#")
    say("# Written by tools/sega/port_sprites.py from orig/dune2.gen; its docstring")
    say("# has the method and `port_sprites.py --check` compares it with the running")
    say("# cartridge.  Pictures are in sprites/: RGBA, the battlefield's own colours")
    say("# (the 64 at $0A6C90, v*255//7), alpha 0 where nothing is drawn.  Flips are")
    say("# baked in and multi-piece sprites flattened: one frame, one picture.")
    say("#")
    say("# Coordinates: an object's position is its record's y/x words (1/256 of a")
    say("# square, so pixel = word >> 3).  A frame's top-left pixel goes at")
    say("# position + (dx, dy); dx, dy are pixels and usually negative.")
    say("")
    say("== palette lines")
    say("# house-p{L}.png is the same layout drawn in palette line L.  A unit, its")
    say("# projectiles and its death animation use its house's line:")
    for h, name in enumerate(HOUSES):
        say(f"house {h} {name:10s} line {rom.house_line(h)}")
    say("# ($009584 / $02EC56 / $00B52C; Fremen share Atreides' line, Mercenaries")
    say("# Harkonnen's.  The CRAM is the same in every battle.)  The 64 colours,")
    say("# nine bits BBBGGGRRR as $0A6C90 gives them, then as RGB:")
    for ln in range(4):
        say(f"line {ln} " + " ".join(f"{c:03X}" for c in pal[16 * ln:16 * ln + 16]))
    for ln in range(4):
        say(f"line {ln} " + " ".join("%02X%02X%02X" % rgb(c)
                                    for c in pal[16 * ln:16 * ln + 16]))
    used = sorted({c for f in cat.frames if f.housed
                   for ln, c in f.px.values() if ln is None})
    same = [i for i in range(16) if len({pal[16 * ln + i] for ln in range(4)}) == 1]
    say("# House-coloured pixels use the indices " + ",".join(map(str, used))
        + "; " + ",".join(map(str, same)))
    say("# are the same colour in every line, so the four house sheets differ")
    say("# only where a pixel is " + ",".join(str(i) for i in used if i not in same)
        + ": one master and a recolouring at start-up is enough.")
    say("")
    say("== frames")
    say("# id  sheet        x    y   w   h   dx  dy  names")
    for i, f in enumerate(cat.frames):
        sh, x, y = place[i]
        say(f"{i:4d}  {sh:10s} {x:4d} {y:4d} {f.w:3d} {f.h:3d} {f.dx:4d} {f.dy:4d}  "
            + " ".join(cat.names[i]))
    say("")
    say("== draw order")
    say("# The chain is kept in descending order of layer << 16 | (y + the first")
    say("# piece's y), and the VDP draws the first on top: a higher layer covers a")
    say("# lower, and within a layer the object further down the screen covers the")
    say("# one above it.  (The key adds the object's y in 1/8 pixels to the piece's")
    say("# y in pixels, and the chain is only re-sorted when a sprite is made or")
    say("# an explosion steps, so a moving unit keeps the place it was made in;")
    say("# the port can simply sort by layer, then y.)  The layer is the tag of")
    say("# the animation the sprite was made from:")
    say("layer $FD  the cursor; $FA the bracket (the pointer is in screen pixels)")
    say("layer $14  explosions 0-11, 14, 18, 19; the Sonic Blast")
    say("layer $10  Carryall, 'Thopter")
    say("layer $0F  Frigate")
    say("layer $0C  rockets, Death Hand")
    say("layer $0B  bullet, Saboteur, smoke (explosions 9, 10, 15) - also: no house palette")
    say("layer $09  the Harvester's dust")
    say("layer $08  vehicles: Tank, Siege Tank, Devastator, Sonic Tank, Launcher,")
    say("           Deviator, Trike, Raider Trike, Quad, Harvester, MCV")
    say("layer $04  foot soldiers")
    say("layer $03  explosion 13 (the Sandworm)")
    say("layer $02  Sandworm")
    say("layer $00  structure markers; corpses (explosions 20-23)")
    say("# Within a band of 32 lines the Mega Drive drops pieces of flagged")
    say("# sprites when more than 16 sprites or 256 pixels share it ($0011E8);")
    say("# the port need not.")
    say("")
    say("== units")
    say("# unit <type> <name>: group <g>, base animation <n>")
    say("#   dir <d> [walk <w>] -> <frame id(s)>   (d: facing>>5 after +16 for 8")
    say("#   directions, facing>>4 after +8 for 16; walk: +$73 & 3)")
    for t, rows in T["units"].items():
        grp = rom.utype(t, TYPE_GROUP)
        base = rom.utype(t, TYPE_SPRITE)
        say(f"unit {t} {UNIT_NAMES[t]}: group {grp}, base animation {base}")
        if t == 1:
            say("  # three rotor phases each, shown by the global counter $FFD304")
            say("  # (2, 1, 0, 2 ... one step every 10 ticks): frames for 2 1 0")
        if t == 26:
            say("  # second id: flags2 bit 9 (Starport cargo not yet delivered)")
        if t == 0:
            say("  # carrying: +3 (linkedID) is not $FF")
        for vname, d, wk, ch, ids in rows:
            w = f" walk {wk}" if wk is not None else ""
            v = f" {vname}" if vname else ""
            if t == 1:
                ids = [ids[2], ids[1], ids[0]]
            say(f"  dir {d}{w}{v} -> {ids_text(ids)}")
    say("")
    say("== tank")
    say("# Tank (9) and Siege Tank (10): hull and turret are two frames drawn at the")
    say("# unit's position, turret on top.  <table> 0 Tank, 1 Siege Tank, 2 Tank")
    say("# firing, 3 Siege Tank firing (the turret recoils a pixel; shown from the")
    say("# shot until the next turn or aim redraw).  hull octant = (+$6A+16)>>5,")
    say("# turret octant = (+$6D+16)>>5.  The ids already include the -12,-12;")
    say("# 'turret +x +y' is an extra shift of the turret picture.")
    say("# table hull turret -> hull_id turret_id turret_shift")
    for (tb, h, tu), (hid, tid, tx, ty, hx, hy) in sorted(T["tank"].items()):
        extra = f" hull +{hx} +{hy}" if (hx, hy) != (0, 0) else ""
        say(f"tank {tb} {h} {tu} -> {hid} {tid} {tx:+d} {ty:+d}{extra}")
    say("")
    say("== sandworm")
    say(f"sandworm -> {T['worm']}   # never redrawn: no facing, line 0")
    say("")
    say("== harvester dust")
    say("# shown while a Harvester on the map harvests (+$54 = 5) on spice")
    say("# (landscape 8 or 9); frame = +$73 (0,1,2 stepping every animation tick),")
    say("# dir = (+$6A+16)>>5; the offset is added to the frame's dx dy.")
    for (fr, d), (i, x, y) in sorted(T["harvest"].items()):
        say(f"harvest frame {fr} dir {d} -> {i} {x:+d} {y:+d}")
    say("")
    say("== smoke")
    say("# animation 180, whose six tiles $00B028 overwrites every 10 ticks,")
    say("# counting $FFD300 2,1,0,2,...  Shown by explosions 9, 10 and 15.")
    for ph, i in T["smoke"]:
        say(f"smoke phase {ph} -> {i}")
    say("")
    say("== house marker")
    say("# 16x16, written into the plane in the house's line: its top-left is at")
    say("# the structure's position (the top-left corner of its top-left square)")
    say("# + (0, drop[layout]) - the bottom-left quarter of its bottom-left")
    say("# square.  8 frames, one step every 8 video frames ($FFBF68, $00608E).")
    say("drop " + " ".join(str(rom.s(MARKER_DROP + 2 * k)) for k in range(8)))
    say("house_marker -> " + ids_text(T["marker"]))
    say("")
    say("== structure markers")
    say("# sprites owned by the structure's position (+$A), line 0.  The offset")
    say("# is by layout (the building table's +$3C) and added to the frame's dx dy.")
    say("# ready  'OK', $009A62: a Construction Yard with a building ready to")
    say("#        place (flags2 bit 13), the Palace's weapon ready ($00DC98, $00DCFA)")
    say("# repair a hammer, $009B26: +4 bit 13 (repairing)")
    say("# power  a lightning bolt, $009AD6: on a Windtrap while its house uses")
    say("#        more power than it makes (house +$1C > +$1A, $00DD66)")
    say("# Only the one marker a structure has shows (one sprite, +$10).")
    for name, (i, offs) in T["smarkers"].items():
        say(f"marker {name} -> {i}   offsets by layout: "
            + " ".join(f"{x:+d},{y:+d}" for x, y in offs))
    say("")
    say("== cursors")
    say("# The pointer is in screen coordinates; the bracket follows the selected")
    say("# object's position and blinks (period 10 frames).")
    say("# 'pieces' are (frame@dx,dy) drawn together; the placement squares are")
    say("# green (line 3) where the square fits and red (line 0) where it is blocked.")
    for n, (what, i, pp) in T["cursors"].items():
        if pp is None:
            say(f"cursor anim {n} -> {i}   # {what}")
        else:
            say(f"cursor anim {n} -> pieces "
                + " ".join(f"{j}@{x:+d},{y:+d}" for j, x, y in pp) + f"   # {what}")
    say("# building placement ($004BF2): -1..-16, a 2x2 grid whose quarters fit or")
    say("# are blocked, one bit each")
    for k, pp in enumerate(T["place"]):
        say(f"cursor place {-k - 1} -> pieces "
            + " ".join(f"{j}@{x:+d},{y:+d}" for j, x, y in pp))
    say("")
    say("== shake")
    say("# Soldier, Trooper, Trike, Raider Trike and Quad ($00B3B0) are drawn")
    say("# shifted by this (dx, dy), picked by the unit's +$72 & 7 (wobbleIndex):")
    say("shake " + " ".join(f"{rom.s(SHAKE + 4 * k):+d},{rom.s(SHAKE + 4 * k + 2):+d}"
                            for k in range(8)))
    say("")
    say("== frames never shown")
    say("# The turret animations 116 and 126 in units.txt (the type table's +$48):")
    say("# unit_draw uses the 256-frame table instead.  Animations 111-113 and")
    say("# 121-123 (the Tank's and Siege Tank's own) only make the sprite; the")
    say("# first redraw points it into the 256-frame table.")
    out.write_text("\n".join(L) + "\n")


def write_effects(rom, T, out):
    L = []
    say = L.append
    say("# effects.txt - the explosion and effect animations of a Mega Drive Dune II")
    say("# battle, for the port.  Written by tools/sega/port_sprites.py.")
    say("#")
    say("# 24 scripts at $0C80A2, started by fx_explosion_start $00AEDA at a")
    say("# position; each step shows a frame (an id in sprites.txt) for so many")
    say("# ticks (game frames, $FFFFFE); '-' is a blank step; 'smoke a b c' is the")
    say("# smoke frame of the global phase.  The effect ends after its last step.")
    say("# 'house' in a step means the id is in house-p{L}.png in the line of the")
    say("# house that died (types 20, 21).")
    say("#")
    say("# who starts them: map_make_explosion $00A934 (types 0-19, by the")
    say("# weapon), map_deviate_area $00ADBE (7), emc_unit_explode $045808 (20")
    say("# infantry dies, 21 anything else dies, 22/23 run over), the Sandworm (13).")
    say("")
    names = {0: "a bullet's hit", 1: "a shell's hit (bullet +3 = 9)",
             7: "the Deviator's cloud", 13: "the Sandworm", 15:
             "smoke: a hit structure below half health (from 2)",
             19: "(made in house 0's line)", 20: "infantry dies", 21:
             "a unit dies", 22: "infantry run over", 23: "run over"}
    for n in range(FX_COUNT):
        steps = T["fx"][n]
        parts = []
        for s, tk in steps:
            if s is None:
                parts.append(f"-/{tk}")
            elif isinstance(s, tuple):
                parts.append(f"smoke {' '.join(map(str, s[1]))}/{tk}")
            else:
                parts.append(f"{s}/{tk}")
        say(f"fx {n:2d}  " + (" ".join(parts) if parts else "(nothing)")
            + (f"   # {names[n]}" if n in names else ""))
    say("")
    say("# A '-' step is animation 7, whose one piece is tile 0: blank.  Types")
    say("# 12, 16 and 17 end at once.  Only a step's first frame is drawn in the")
    say("# starter's line (map_make_explosion passes house 3, line 1); the rest")
    say("# are remade in house 0's (line 0) by $00B2A6 - the ids already say so.")
    out.write_text("\n".join(L) + "\n")


# ------------------------------------------------------------- the machine

class Ram:
    def __init__(self, raw):
        b = bytearray(raw)
        b[0::2], b[1::2] = b[1::2], b[0::2]
        self.m = bytes(b)

    def b(self, a):
        return self.m[a & 0xFFFF]

    def w(self, a):
        a &= 0xFFFF
        return int.from_bytes(self.m[a:a + 2], "big")

    def s(self, a):
        v = self.w(a)
        return v - 0x10000 if v & 0x8000 else v

    def l(self, a):
        a &= 0xFFFF
        return int.from_bytes(self.m[a:a + 4], "big")


def swap16(raw):
    b = bytearray(raw)
    b[0::2], b[1::2] = b[1::2], b[0::2]
    return bytes(b)


def run_states(names, frames, step):
    """{state: [dump dict]} - RAM, VRAM, CRAM, VDP registers."""
    out = {}
    with tempfile.TemporaryDirectory(dir=WORK) as d:
        d = Path(d)
        lines = []
        for s in names:
            src = WORK / (s + ".state")
            if not src.exists():
                src = STATES / (s + ".state")
            lines.append(f"load {src}")
            if s.startswith("patched-"):
                lines.append("run 30")    # let every patched unit be redrawn
            if s.startswith("fx-"):
                lines.append("run 1")     # one tick: the new steps are made
            for k in range(frames):
                lines.append(f"run {step}")
                for what in ("ram", "vram", "cram", "vdpreg"):
                    lines.append(f"{what} {d}/{s}.{k}.{what}")
        (d / "s.script").write_text("\n".join(lines) + "\n")
        subprocess.run([str(RUN), "--core", str(CORE), "--rom", str(ROM_PATH),
                        "--script", str(d / "s.script")], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for s in names:
            out[s] = []
            for k in range(frames):
                g = lambda w: (d / f"{s}.{k}.{w}").read_bytes()
                cram = g("cram")
                out[s].append(dict(ram=Ram(g("ram")), vram=swap16(g("vram")),
                                   cram=[cram[2 * i] | cram[2 * i + 1] << 8
                                         for i in range(64)],
                                   reg=g("vdpreg")))
    return out


PATCH_TYPES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17,
               18, 19, 20, 21, 22, 23, 24, 26]
PATCH_BASES = ["pt-DEVASTATOR", "pt-DEATHRULER", "pt-POWERCRUSH",
               "pt-SONICBLAST", "pt-ASHLIKENNY", "pt-DUNERUNNER"]
CHECK_STATES = ["pw-DOMINATION", "pw-DEMOLITION", "pw-SPICEDANCE",
                "pw-ARRAKISSUN", "pw-POWERCRUSH", "pw-SONICBLAST",
                "pw-STEALTHWAR", "pw-EVILMENTAT", "fz-000332", "fz-001380",
                "fz-000700", "fz-000119", "fz-002462", "fz-000108", "m1-2",
                "pt-DEVASTATOR", "pt-ITSJOEBWAN", "fz-000101", "fz-000636",
                "win-DEFTHUNTER", "fz-000234", "fz-000195"]


def patched_state(rom, src, dst, seed):
    """A copy of save state `src` with its units turned into other types,
    facings, walk steps and houses and put on screen, so that the check
    sees every type the saved battles lack ('Thopter, Frigate, MCV,
    rockets...).  The core keeps work RAM at +$10 of its state,
    byte-swapped like its dumps.  Each unit's sprite object is given the
    list and palette anim_make_sprite would have made it with, because the
    'Thopter's and Frigate's own routines never set them.  Harvesters and
    the Sandworm are left alone: a Harvester's +$5A is a sprite handle,
    anyone else's a reference, and the worm is never redrawn."""
    import random
    rnd = random.Random(seed)
    st = bytearray((STATES / (src + ".state")).read_bytes())

    def ad(a):
        return 0x10 + ((a & 0xFFFF) ^ 1)

    def rb(a):
        return st[ad(a)]

    def wb(a, v):
        st[ad(a)] = v & 0xFF

    def rw(a):
        return rb(a) << 8 | rb(a + 1)

    def ww(a, v):
        wb(a, v >> 8)
        wb(a + 1, v)
    camx, camy = rw(0xFFE3BE), rw(0xFFE3C0)
    k = 0
    first = None
    for i in range(102):
        u = 0xFF1000 + i * 0x8C
        if not rw(u + 4) & 2 or rw(u + 4) & 4 or not rw(u + 0x10):
            continue
        sx, sy = 24 + 36 * (k % 7), 24 + 36 * (k // 7 % 5)
        if rb(u + 2) in (16, 25):            # only brought into view
            ww(u + 0xA, (camy + sy) << 3)
            ww(u + 0xC, (camx + sx) << 3)
            k += 1
            continue
        t = PATCH_TYPES[(k + seed) % len(PATCH_TYPES)]
        wb(u + 2, t)
        wb(u + 8, rnd.randrange(6))
        wb(u + 0x6A, rnd.randrange(256))
        wb(u + 0x6D, rnd.randrange(256))
        wb(u + 0x73, rnd.randrange(4))
        wb(u + 3, rnd.choice((0xFF, 0x00)) if t == 0 else 0xFF)
        f2 = rw(u + 6) & ~0x240
        if t == 26 and rnd.randrange(2):
            f2 |= 0x200
        ww(u + 6, f2)
        h = 0xFF0000 | rw(u + 0x10)
        pt, pa, lt, la = rom.anim(rom.utype(t, TYPE_SPRITE))
        ww(h + 8, lt << 8 | la >> 16)
        ww(h + 10, la & 0xFFFF)
        line = 0 if lt == 0x0B else rom.house_line(rb(u + 8))
        ww(h + 6, (rw(h + 6) & 0x87FF) | line << 13)
        ww(u + 0xA, (camy + sy) << 3)
        ww(u + 0xC, (camx + sx) << 3)
        first = first or u
        k += 1
    # something selected, so the game puts the bracket up itself
    # ($028596-$0287C6): a unit on even seeds (the first one patched, its
    # flags2 bit 15 set, $FFC25C), one of the player's structures on odd
    # ones ($FFC578)
    player = rw(0xFFC274)
    if seed % 2 == 0 and first:
        ww(first + 6, rw(first + 6) | 0x8000)
        ww(0xFFC25C, first >> 16)
        ww(0xFFC25E, first & 0xFFFF)
    else:
        for i in range(70):
            b = 0xFF4EB8 + 0x62 * i
            if rw(b + 4) & 2 and rb(b + 8) == player:
                ww(b + 6, rw(b + 6) | 0x8000)
                ww(0xFFC578, b >> 16)
                ww(0xFFC57A, b & 0xFFFF)
                if (seed // 2) % 3 == 0:
                    break
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / (dst + ".state")).write_bytes(st)
    return dst


FX_BASES = ["fz-000119", "fz-001380", "fz-000101", "win-DEFTHUNTER",
            "fz-000636"]


def patched_fx(rom, src, dst, seed):
    """A copy of a fighting save state whose running explosions are
    pointed at other scripts and brought on screen, so that every
    explosion frame gets drawn by the game itself: +5/+8 are the script
    pointer's low 24 bits, +$A the time left, and a time of 1 makes
    $00B224 read the step at the pointer on the next tick and remake the
    sprite.  That tick remakes it in house 0, as it does every step after
    the first, so a script is entered at its second step when it has one."""
    st = bytearray((STATES / (src + ".state")).read_bytes())

    def ad(a):
        return 0x10 + ((a & 0xFFFF) ^ 1)

    def rw(a):
        return st[ad(a)] << 8 | st[ad(a + 1)]

    def ww(a, v):
        st[ad(a)], st[ad(a + 1)] = (v >> 8) & 0xFF, v & 0xFF
    camx, camy = rw(0xFFE3BE), rw(0xFFE3C0)
    e, k, seen = rw(0xFFD2FC), 0, set()
    while e and e not in seen:
        seen.add(e)
        a = 0xFF0000 | e
        n = (seed * 5 + k) % FX_COUNT
        p = rom.ptr(FX_SCRIPTS + 4 * n)
        if rom.s(p + 6) > 0 and rom.s(p + 4) >= 0:
            p += 4
        st[ad(a + 5)] = (p >> 16) & 0xFF
        ww(a + 8, p & 0xFFFF)
        ww(a + 0xA, 1)
        ww(a, (camy + 40 + 48 * (k // 5 % 4)) << 3)
        ww(a + 2, (camx + 40 + 48 * (k % 5)) << 3)
        k += 1
        e = rw(a + 0xE)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / (dst + ".state")).write_bytes(st)
    return dst


def sim_render(rom, ram):
    """spr_render ($001088) over the battle chain, without the crowded-band
    thinning: [(sprite, pieces or None if hidden, blinking)], chain order.
    A piece is (y, size, attr, x) as the sprite buffer holds it."""
    camx, camy = ram.s(0xFFE3BE), ram.s(0xFFE3C0)
    out = []
    spr = ram.w(0xFFF3AC)
    seen = set()
    while spr and spr not in seen:
        seen.add(spr)
        a = 0xFF0000 | spr
        fl = ram.b(a + 7)
        nxt = ram.w(a + 0xE)
        if fl & 0x80:
            out.append((spr, None, False, None))
            spr = nxt
            continue
        own = ram.l(a) & 0xFFFFFF
        mem = ram if own >= 0xFF0000 else rom     # an owner may be in ROM
        if fl & 0x40:                     # screen space: x first
            x, y = mem.s(own), mem.s(own + 2)
        else:
            y, x = mem.s(own), mem.s(own + 2)
            x, y = (x >> 3) - camx, (y >> 3) - camy
            if fl & 4:
                k = ram.b(own - 0xA + 0x72) & 7
                x += rom.s(SHAKE + 4 * k)
                y += rom.s(SHAKE + 4 * k + 2)
        pos = (x, y)
        x += 0x80
        y += 0x80
        attr = ram.w(a + 6)
        lst = ram.l(a + 8) & 0xFFFFFF
        pcs = []
        for k in range(rom.w(lst) + 1):
            p = lst + 2 + 12 * k
            pw, ph = rom.s(p), rom.s(p + 2)
            py, px = y + rom.s(p + 4), x + rom.s(p + 10)
            if px > 0x1BF or py > 0x15F or px + pw < 0x80 or py + ph < 0x80:
                continue
            pa = rom.w(p + 8)
            at = (pa & 0x9FFF) ^ (attr & 0xF800)
            if pa & 0x6000:
                at = (at & 0x9FFF) | pa
            pcs.append((py & 0xFFFF, rom.b[p + 6], at, px & 0xFFFF))
        out.append((spr, pcs, bool(fl & 0x20), pos))
        spr = nxt
    return out


def sat_buffer(ram):
    """The sprite buffer at $FFE428 as $006712 sends it: [(y, size, attr, x)]."""
    out = []
    i = 0
    for _ in range(80):
        o = 0xFFE428 + 8 * i
        y, sl, at, x = ram.w(o), ram.w(o + 2), ram.w(o + 4), ram.w(o + 6)
        out.append((y, sl >> 8, at, x))
        link = sl & 0xFF
        if not link:
            break
        i = link
    return out


def live_pixels(vram, cram, pcs, ox, oy):
    """{(x, y): rgb} the VDP draws for these pieces, relative to (ox, oy)."""
    px = {}
    for y, sz, at, x in reversed(pcs):
        got = draw_pieces(vram, [(at & 0x7FF, at, sz, (x - 0x80) - ox,
                                  (y - 0x80) - oy)], 0, 0)
        for k, (ln, c) in got.items():
            px[k] = rgb(cram[ln * 16 + c])
    return px


def frame_pixels(cat, pal, fid, line, ox=0, oy=0, out=None):
    out = {} if out is None else out
    for (x, y), (ln, c) in cat.frames[fid].px.items():
        out[(x + ox, y + oy)] = rgb(pal[(line if ln is None else ln) * 16 + c])
    return out


def candidate_pictures(rom, cat, T, ch, line, pal):
    """[(label, {(x, y): rgb})]: what the baked frames say the unit shows,
    first the expected one, then the ones the live VRAM may legitimately
    hold instead (another rotor phase, another frame of a DMA'd set)."""
    def pic_of(p):
        fid = cat.index.get(p.key())
        return None if fid is None else frame_pixels(cat, pal, fid, line)
    kind = ch[0]
    if kind == "tank":
        hid, tid, tx, ty, hx, hy = T["tank"][(ch[1], ch[2], ch[3])]
        px = frame_pixels(cat, pal, hid, line, hx, hy)
        frame_pixels(cat, pal, tid, line, tx, ty, px)
        return [("", px)]
    if kind == "thopter":
        lst, flip = choice_list(rom, ch)
        return [(f"rotor {ph}", pic_of(Pic(draw_pieces(
            cat.vram_for(289, rotor_vram(rom, ph)), rom.pieces(lst), flip, None))))
            for ph in (2, 1, 0)]
    if kind == "frigate":
        out = []
        for fr in range(4):
            out.append((f"the $7FC0 tiles hold frigate picture {fr} (two "
                        "Frigates share them)", pic_of(Pic(draw_pieces(
                cat.vram_for(298, frigate_vram(rom, fr)),
                rom.pieces(rom.anim(298)[3]), ch[2], None)))))
        out.sort(key=lambda lp: f"picture {ch[1]} " not in lp[0])
        return out
    n, flip = ch[1], ch[2]
    first = [("", pic_of(cat.anim_pic(n, flip, 0 if n == 213 else None)))]
    pt, pa, lt, la = rom.anim(n)
    if pt & 0x80:                        # tiles shared by a DMA'd set
        for m in range(ANIM_COUNT):
            q = rom.anim(m)
            if m != n and q[0] & 0x80 and q[3] == la:
                pic = Pic(draw_pieces(cat.vram_for(m), rom.pieces(la), flip,
                                      0 if lt == 0x0B else None))
                first.append((f"the DMA'd tiles still hold animation {m} (two "
                              "sprites share them, or the DMA is a frame behind)",
                              pic_of(pic)))
    return first


def other_candidates(rom, cat, lst, flip, line):
    """Pictures a non-unit sprite with this list may show: every
    animation with this list (the DMA'd ones each with their own pixels,
    the smoke in its three phases, the cursors from their slots), and the
    structure markers' lists, which are not in the table."""
    out = []
    for m in range(ANIM_COUNT):
        pt, pa, lt, la = rom.anim(m)
        if la != lst or not (pt or pa):
            continue
        pcs = rom.pieces(la)
        tiles = [q[0] for q in pcs]
        if 0x7BC <= min(tiles) and max(tiles) < 0x7CC:
            slot = CURSOR_SLOTS[1] if min(tiles) >= 0x7C4 else CURSOR_SLOTS[0]
            v = with_dma(cat.base, slot, rom.b[pa:pa + 256])
            if slot == CURSOR_SLOTS[0]:
                v = with_dma(v, CURSOR_SLOTS[1], rom.b[pa:pa + 256])
            vs = [v]
        elif m in (180, 181, 182):
            vs = [with_dma(cat.base, SMOKE_VRAM, smoke_vram(rom, ph)[0][1])
                  for ph in range(3)]
        else:
            vs = [cat.vram_for(m)]
        for v in vs:
            out.append((Pic(draw_pieces(v, pcs, flip, line)), v))
    if not out:
        out.append((Pic(draw_pieces(cat.base, rom.pieces(lst), flip, line)),
                    cat.base))
    return out


def baked(cat, rom, lst, pic, v, flip, line):
    """Is this picture in the catalogue - whole, or piece by piece (the
    brackets, placement squares and markers are kept as pieces), in its
    own line or as a house frame?"""
    def known(p):
        if p.key() in cat.index:
            return True
        q = Pic({k: (None if ln == line else ln, c) for k, (ln, c) in p.px.items()})
        return q.key() in cat.index
    if known(pic):
        return True
    return all(known(Pic(draw_pieces(v, [q[:3] + (0, 0)], flip, line)))
               for q in rom.pieces(lst))


def sprite_kind(rom, lst, own):
    if own == 0xFFBF12:
        return "cursor"
    if own == 0xFFBF5A:
        return "bracket"
    marks = [rom.ptr(MARKER1_LISTS + 4 * i) for i in range(8)] + \
        [rom.ptr(MARKER2_LISTS + 4 * i) for i in range(7)] + [MARKER0_LIST]
    if lst in marks:
        return "structure marker"
    return "explosion"


_FX_TILES = None


def fx_tiles(rom):
    """Every tile an explosion script's frames draw."""
    global _FX_TILES
    if _FX_TILES is None:
        _FX_TILES = set()
        for n in range(FX_COUNT):
            p = rom.ptr(FX_SCRIPTS + 4 * n)
            while rom.s(p + 2) > 0 and rom.s(p) >= 0:
                for q in rom.pieces(rom.anim(rom.s(p))[3]):
                    _FX_TILES.add(q[0])
                p += 4
    return _FX_TILES


def predicted_line(rom, t, ch, house):
    if t == 25:
        return 0
    if ch[0] == "anim" and rom.anim(ch[1])[2] == 0x0B:
        return 0
    return rom.house_line(house)


def check(rom, cat, T, frames=8, step=5):
    pal = rom.palette()
    names = list(CHECK_STATES)
    for n, base in enumerate(PATCH_BASES):
        for seed in range(3):
            names.append(patched_state(rom, base, f"patched-{base}-{seed}",
                                       7 * n + seed))
    for n, base in enumerate(FX_BASES):
        for seed in range(5):
            names.append(patched_fx(rom, base, f"fx-{base}-{seed}", 5 * n + seed))
    dumps = run_states(names, frames, step)
    C = {}                                # counter name -> [total, ok]
    cover = {"unit types": set(), "unit choices": set(), "explosion frames": set()}
    why = {}                              # explained mismatch -> count
    seen_in = {}                          # ... -> {"saved", "patched"}
    notes = []
    where = ""

    def count(name, ok, reason=None, note=None):
        c = C.setdefault(name, [0, 0])
        c[0] += 1
        c[1] += bool(ok)
        if not ok and reason:
            why[(name, reason)] = why.get((name, reason), 0) + 1
            where_ = where.split("/")[0]
            kinds = seen_in.setdefault((name, reason), set())
            kinds.add("patched" if where_.startswith(("patched-", "fx-"))
                      else "saved")
        if not ok and not reason and note:
            notes.append(note)
    for s, ds in dumps.items():
        for k, d in enumerate(ds):
            r, vram, cram = d["ram"], d["vram"], d["cram"]
            where = f"{s}/{k}"
            if r.l(0xFFE002) not in (0x608E, 0x6D0C):
                count("dumps in a battle", False, "not in a battle (menu)")
                continue
            count("dumps in a battle", True)
            if cram == pal:
                count("CRAM equal to $0A6C90", True)
            elif all(rgb(c) <= rgb(p) for c, p in zip(cram, pal)):
                count("CRAM equal to $0A6C90", False, "fading out (battle over)")
            else:
                count("CRAM equal to $0A6C90", False, None, f"{where}: CRAM differs")
            camx, camy = r.s(0xFFE3BE), r.s(0xFFE3C0)
            sim = sim_render(rom, r)
            by_spr = {spr: (ps, bl) for spr, ps, bl, _ in sim}
            for i in range(102):
                u = 0xFF1000 + i * 0x8C
                t = r.b(u + 2)
                spr = r.w(u + 0x10)
                if not r.w(u + 4) & 2 or not spr or t > 26 \
                        or r.b(u + 0x73) & 0x80:
                    continue
                a = 0xFF0000 | spr
                f2, walk = r.w(u + 6), r.b(u + 0x73)
                ch = unit_choice(rom, t, r.b(u + 0x6A), r.b(u + 0x6D), walk,
                                 r.b(u + 3), f2)
                lst, flip = r.l(a + 8) & 0xFFFFFF, (r.w(a + 6) >> 11) & 3
                line = (r.w(a + 6) >> 13) & 3
                if ch is None and t in (9, 10):   # the shot's frame is held
                    ch = ("tank", t - 9 + 2, dir8(r.b(u + 0x6A)),
                          dir8(r.b(u + 0x6D)))
                elif ch is None:                  # the worm
                    ch = ("anim", 213, 0)
                plst, pflip = choice_list(rom, ch)
                if ch[0] == "frigate":
                    plst = rom.anim(298)[3]       # the list it was made with
                pline = predicted_line(rom, t, ch, r.b(u + 8))
                ok = (plst, pflip, pline) == (lst, flip, line)
                reason = None
                if not ok and ch[0] == "tank" and ch[1] < 2 and \
                        lst == choice_list(rom, ("tank", ch[1] + 2) + ch[2:])[0]:
                    if f2 & 0x40:
                        ok = True
                    else:
                        reason = ("the shot's recoil frame stays until the "
                                  "first redraw after flags2 bit 6 is cleared")
                if not ok and ch[0] == "anim" and \
                        rom.utype(t, TYPE_GROUP) in (3, 4):
                    for w in range(4):
                        c2 = unit_choice(rom, t, r.b(u + 0x6A), walk=w)
                        if choice_list(rom, c2) == (lst, flip):
                            reason = ("walk step moved on by the animation "
                                      "tick, not redrawn yet")
                if not ok and ch[0] in ("anim", "tank") and not reason:
                    for df in (-32, -16, 16, 32):
                        c2 = unit_choice(rom, t, (r.b(u + 0x6A) + df) & 0xFF,
                                         r.b(u + 0x6D), walk, r.b(u + 3), 0)
                        if c2 and choice_list(rom, c2) == (lst, flip):
                            reason = ("facing changed since the last redraw "
                                      "(set without one, e.g. by a script)")
                if not ok and not reason and (r.w(u + 4) & 4 or
                                              r.b(a + 7) & 0x80):
                    reason = ("off the map or hidden: nothing redraws it "
                              "until it is back")
                if not ok and not reason and k and \
                        ds[k - 1]["ram"].w(u + 4) & 4:
                    reason = ("just put on the map (off it in the dump "
                              "before): redrawn at the next rotation tick")
                if not ok and (plst, pflip) == (lst, flip) and line == 0 and \
                        rom.utype(t, TYPE_SPRITE) < 0xEE:
                    reason = ("made this frame: $046A34 makes the sprite in "
                              "line 0 below animation $EE, the house's line "
                              "comes with the next redraw")
                count("unit sprite from the unit record", ok, reason,
                      f"{where}: unit {i} {UNIT_NAMES[t]} facing "
                      f"{r.b(u + 0x6A)} walk {walk}: predicted ${plst:06X} "
                      f"flip {pflip} line {pline}, the sprite has ${lst:06X} "
                      f"flip {flip} line {line}")
                if not ok:
                    continue
                # the picture against the live VRAM
                ps, blink = by_spr.get(spr, (None, False))
                if not ps or blink:
                    continue
                sx, sy = (r.s(u + 0xC) >> 3) - camx, (r.s(u + 0xA) >> 3) - camy
                if r.b(a + 7) & 4:
                    kk = r.b(u + 0x72) & 7
                    sx += rom.s(SHAKE + 4 * kk)
                    sy += rom.s(SHAKE + 4 * kk + 2)
                got = live_pixels(vram, cram, ps, sx, sy)
                cands = candidate_pictures(rom, cat, T, ch, pline, pal)

                def onscreen(px):
                    return {p: c for p, c in px.items()
                            if 0 <= p[0] + sx < 256 and 0 <= p[1] + sy < 224}
                got = onscreen(got)
                hit = [lab for lab, px in cands if px is not None and onscreen(px) == got]
                if not hit:
                    count("unit picture equal to the live VRAM", False, None,
                          f"{where}: unit {i} {UNIT_NAMES[t]} {ch}: no baked "
                          "frame equals the live pixels")
                elif hit[0] == cands[0][0]:
                    count("unit picture equal to the live VRAM", True)
                    cover["unit types"].add(t)
                    cover["unit choices"].add((t,) + ch)
                    if ch[0] == "thopter":
                        ph = r.w(0xFFD304)
                        count("'Thopter rotor phase is $FFD304's", hit[0] ==
                              f"rotor {ph}", "the new phase is DMA'd at the "
                              "next vertical interrupt")
                elif ch[0] == "thopter":
                    count("unit picture equal to the live VRAM", True)
                    count("'Thopter rotor phase is $FFD304's",
                          hit[0] == f"rotor {r.w(0xFFD304)}",
                          "the new phase is DMA'd at the next vertical interrupt")
                else:
                    count("unit picture equal to the live VRAM", False, hit[0])
            # the Harvester's dust
            for i in range(102):
                u = 0xFF1000 + i * 0x8C
                if not r.w(u + 4) & 2 or r.b(u + 2) != 16:
                    continue
                h = r.w(u + 0x5A)
                if not h or r.b((0xFF0000 | h) + 7) & 0x80:
                    continue
                want = rom.ptr(HARVEST_LISTS + 4 * (dir8(r.b(u + 0x6A)) +
                                                    8 * r.b(u + 0x73)))
                count("harvester dust list", r.l((0xFF0000 | h) + 8)
                      & 0xFFFFFF == want, None, f"{where}: harvester {i} dust")
            # explosions
            e = r.w(0xFFD2FC)
            seen = set()
            while e and e not in seen:
                seen.add(e)
                a = 0xFF0000 | e
                spr = r.w(a + 6)
                if spr:
                    cur = (r.l(a + 4) & 0xFF0000) | r.w(a + 8)
                    fr = rom.s(cur - 4)
                    got = r.l((0xFF0000 | spr) + 8) & 0xFFFFFF
                    count("explosion step's animation", fr >= 0 and
                          rom.anim(fr)[3] == got, None,
                          f"{where}: explosion ${e:04X}")
                e = r.w(a + 0xE)
            # the chain -> the sprite buffer
            buf = list(sat_buffer(r))
            missing = []
            for spr, ps, bl, _ in sim:
                if ps and not bl:
                    for p in ps:
                        if p in buf:
                            buf.remove(p)
                            count("piece predicted from the chain is in the "
                                  "sprite buffer", True)
                        else:
                            missing.append((p, r.b((0xFF0000 | spr) + 7) & 2))
            for spr, ps, bl, _ in sim:
                for p in (ps or []) if bl else []:
                    if p in buf:
                        buf.remove(p)
            buf = [p for p in buf if p[0] or p[3]]
            late = "the object moved or changed between the sprite pass " \
                   "(vertical interrupt) and the end of the frame"
            for p, thin in missing:
                count("piece predicted from the chain is in the sprite buffer",
                      False, late if buf else
                      "dropped by the crowded-band thinning ($0011E8)" if thin
                      else None, f"{where}: piece {[hex(v) for v in p]} missing")
            for p in buf:
                count("sprite-buffer pieces the chain accounts for", False,
                      late if missing else
                      "an explosion that ended between the sprite pass and "
                      "the end of the frame" if p[2] & 0x7FF in fx_tiles(rom)
                      else None,
                      f"{where}: buffer piece {[hex(v) for v in p]} not predicted")
            # every other visible sprite: a baked frame, equal to the VRAM
            units = {r.w(0xFF1000 + i * 0x8C + 0x10) for i in range(102)
                     if r.w(0xFF1000 + i * 0x8C + 4) & 2}
            shown = set(sat_buffer(r))
            for spr, ps, bl, pos in sim:
                if not ps or spr in units or (bl and not set(ps) <= shown):
                    continue
                a = 0xFF0000 | spr
                own = r.l(a) & 0xFFFFFF
                if own < 0xFF0000 or own in (0xFFBF4C, 0xFFBF76):
                    continue                  # sidebar, radar
                lst = r.l(a + 8) & 0xFFFFFF
                flip, line = (r.w(a + 6) >> 11) & 3, (r.w(a + 6) >> 13) & 3
                got = live_pixels(vram, cram, ps, *pos)
                got = {q: c for q, c in got.items()
                       if 0 <= q[0] + pos[0] < 256 and 0 <= q[1] + pos[1] < 224}
                ok = False
                for pic, v in other_candidates(rom, cat, lst, flip, line):
                    px = {q: rgb(cram[(line if ln is None else ln) * 16 + c])
                          for q, (ln, c) in pic.px.items()
                          if 0 <= q[0] + pos[0] < 256 and 0 <= q[1] + pos[1] < 224}
                    if px == got:
                        ok = baked(cat, rom, lst, pic, v, flip, line)
                        break
                what = sprite_kind(rom, lst, own)
                if ok:
                    cover.setdefault(what if what != "explosion" else
                                     "explosion frames", set()).add(
                        (lst, flip, line))
                count(f"{what}: picture is a baked frame equal to the VRAM",
                      ok, None, f"{where}: {what} sprite ${spr:04X} list "
                      f"${lst:06X} flip {flip} line {line} matches no baked frame")
            # the house marker's four tiles
            fr = r.w(0xFFBF68) & 7
            tiles = vram[0x2BE * 32:0x2C2 * 32]
            frames = [rom.b[MARKER_FRAMES + 128 * f:MARKER_FRAMES + 128 * f + 128]
                      for f in range(8)]
            count("house-marker tiles are one of the 8 frames", tiles in frames,
                  None, f"{where}: house-marker tiles are none of the frames")
    why = {k: (v, "/".join(sorted(seen_in[k]))) for k, v in why.items()}
    return C, why, notes, cover


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="also compare with battle save states")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args()
    rom = Rom()
    cat, T = build(rom)
    pal = rom.palette()
    if not args.check_only:
        out = Path(args.out)
        place = write_sheets(cat, pal, out / "sprites")
        write_index(rom, cat, T, place, out / "sprites.txt")
        write_effects(rom, T, out / "effects.txt")
        housed = [f for f in cat.frames if f.housed]
        fixed = [f for f in cat.frames if not f.housed]
        px = lambda fs: sum(f.w * f.h for f in fs)
        print(f"{len(cat.frames)} frames: {len(housed)} house-coloured "
              f"({px(housed)} pixels, x4 lines), {len(fixed)} fixed "
              f"({px(fixed)} pixels)")
    if args.check or args.check_only:
        C, why, notes, cover = check(rom, cat, T)
        for name, (n, ok) in C.items():
            print(f"{name}: {ok}/{n} ({100 * ok / max(n, 1):.1f}%)")
            for (nm, reason), (c, src) in sorted(why.items()):
                if nm == name:
                    print(f"    {c} explained ({src} states): {reason}")
            left = n - ok - sum(c for (nm, _), (c, _) in why.items() if nm == name)
            if left:
                print(f"    {left} not explained")
        print("covered: " + ", ".join(f"{len(v)} {k}" for k, v in cover.items()))
        print("unit types seen drawn: " + " ".join(
            str(t) for t in sorted(cover["unit types"])))
        for n in notes[:40]:
            print("  " + n)
        if len(notes) > 40:
            print(f"  ... {len(notes) - 40} more")


if __name__ == "__main__":
    main()
