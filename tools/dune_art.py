#!/usr/bin/env python3
"""dune_art.py - the pictures in src/res/art/ -> EGA pages and includes.

    dune_art.py [--out build/gen] [--preview DIR]

Reads the PNGs the extraction tools wrote (tools/sega/port_*.py; RGBA in
the Mega Drive's own colours) and writes, into --out:

    page_NNN.bin    16 KB art pages, numbered from PG_ART (src/pages.inc)
    art.inc         EQUs: where each kind of art starts, and constants
    palette_battle.inc   the battlefield's 16 palette bytes

## The colours

The ZX Evolution shows 16 of 64 colours, two bits a channel; the Mega
Drive's battlefield uses 31, three bits a channel, and a nearest-colour
mapping puts the main sand and rock shades on the same EGA colour.  So
every Mega Drive colour is drawn either as one of the 16 or as a fixed
checkerboard of two of them (a pixel's parity is (x + y) & 1), and the
16 are chosen to make the sum of those approximations, weighted by how
many pixels use each colour, as small as possible.  Colour 0 is black: it
is what the game shows under the fog and beyond the map.

## The formats (src/render/render.asm reads them)

A cell is 8x8 pixels, 32 bytes: plane 0's eight rows, plane 2's, plane
1's, plane 3's (pass A reads the first 16, pass B the last 16).  A plane
byte is two pixels: the left in bits 0-2 and 6, the right in bits 3-5
and 7.

    ground icon n    page PG_ICONS + n // 32, offset (n % 32) * 512:
                     its 16 cells row by row
    overlay icon n   page PG_OVERLAYS + n // 16, offset (n % 16) * 1024:
                     16 cells of 64 bytes, each pass 32 bytes of (mask,
                     data) pairs - screen AND mask OR data
    the orb          the house markers (overlays 22-26) turn, 8 frames:
                     marker 22 + h, frame f is stored as overlay
                     ORB_SLOT + h * 8 + f (icons_marker.png)
"""

import argparse
import itertools
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "src/res/art"

PG_ART = 40                     # src/pages.inc
LEVELS = (0, 85, 170, 255)
EGA = [(r, g, b) for r in range(4) for g in range(4) for b in range(4)]
OVL_FOG = 0x7B                  # the full-fog overlay: drawn as black


def ega_rgb(c):
    return tuple(LEVELS[v] for v in c)


def palette_byte(c):
    """The value port $FF wants for an EGA colour (platform.md)."""
    r, g, b = c
    v = ((g & 1) << 7) | ((r & 1) << 6) | ((b & 1) << 5) | ((g >> 1) << 4) \
        | ((r >> 1) << 1) | (b >> 1)
    return v ^ 0xFF


def _lab(c):
    """sRGB 0-255 -> CIELAB (D65)."""
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


_LAB = {}


def lab(c):
    c = tuple(int(round(v)) for v in c)
    if c not in _LAB:
        _LAB[c] = _lab(c)
    return _LAB[c]


def dist(a, b):
    """Squared CIELAB distance between two RGB triples."""
    la, lb = lab(a), lab(b)
    return (la[0] - lb[0]) ** 2 + (la[1] - lb[1]) ** 2 + (la[2] - lb[2]) ** 2


# ------------------------------------------------------------ the palette

BAYER = ((0, 2), (3, 1))        # 2x2 ordered thresholds, in quarters
MIX_CONTRAST = 0.1              # how much a mix of far-apart colours costs


class Palette:
    """16 EGA colours and, for every source colour, how to draw it: two
    palette indices (a, b) and how many quarters of the pixels take b,
    placed by a 2x2 ordered pattern (x & 1, y & 1)."""

    MIX_PENALTY = (0, 6, 10, 6) # a pattern costs something even when exact

    def __init__(self, hist, fixed=((0, 0, 0),), size=16):
        self.hist = hist
        self._cache = {}
        cols = list(fixed)
        cands = [c for c in EGA if c not in cols]
        while len(cols) < size:
            best = min(cands, key=lambda c: self.error(cols + [c]))
            cols.append(best)
            cands.remove(best)
        improved = True
        while improved:
            improved = False
            base = self.error(cols)
            for i in range(len(fixed), size):
                for c in list(cands):
                    trial = cols[:i] + [c] + cols[i + 1:]
                    e = self.error(trial)
                    if e < base - 1e-6:
                        cands.append(cols[i])
                        cands.remove(c)
                        cols, base, improved = trial, e, True
        self.cols = cols
        self.map = {src: self.best(src, cols)[1] for src in hist}

    def best(self, src, cols):
        rgbs = [ega_rgb(c) for c in cols]
        best = None
        for i, a in enumerate(rgbs):
            e = dist(src, a)
            if best is None or e < best[0]:
                best = (e, (i, i, 0))
        for i, j in itertools.permutations(range(len(rgbs)), 2):
            a, b = rgbs[i], rgbs[j]
            for q in (1, 2):
                if q == 2 and i > j:
                    continue
                mix = tuple((x * (4 - q) + y * q) / 4 for x, y in zip(a, b))
                e = dist(src, mix) + self.MIX_PENALTY[q] + dist(a, b) * MIX_CONTRAST
                if e < best[0]:
                    best = (e, (i, j, q))
        return best

    def error(self, cols):
        key = tuple(cols)
        if key not in self._cache:
            self._cache[key] = sum(n * self.best(src, cols)[0]
                                   for src, n in self.hist.items())
        return self._cache[key]

    def index(self, rgb, x, y):
        if rgb not in self.map:         # a colour that had no vote
            self.map[rgb] = self.best(rgb, self.cols)[1]
        a, b, q = self.map[rgb]
        return b if BAYER[y & 1][x & 1] < q else a

    def bytes(self):
        return bytes(palette_byte(c) for c in self.cols)


# --------------------------------------------------------------- EGA cells

def pair_byte(left, right):
    return (left & 7) | ((left & 8) << 3) | ((right & 7) << 3) | ((right & 8) << 4)


def pair_mask(lt, rt):
    """AND mask keeping the screen where a pixel is transparent."""
    return (0x47 if lt else 0) | (0xB8 if rt else 0)


PLANE_ORDER = (0, 2, 1, 3)      # pass A: planes 0, 2; pass B: 1, 3


def cell_bytes(pix, pal, ox, oy):
    """8x8 opaque cell at (ox, oy) of an RGBA pixel accessor -> 32 bytes."""
    out = bytearray()
    for plane in PLANE_ORDER:
        for y in range(8):
            x0 = ox + plane * 2
            l = pix[x0, oy + y]
            r = pix[x0 + 1, oy + y]
            li = pal.index(l[:3], x0, oy + y) if l[3] else 0
            ri = pal.index(r[:3], x0 + 1, oy + y) if r[3] else 0
            out.append(pair_byte(li, ri))
    return bytes(out)


def cell_masked(pix, pal, ox, oy):
    """8x8 cell with transparency -> 64 bytes: per pass 16 (mask, data)."""
    out = bytearray()
    for plane in PLANE_ORDER:
        for y in range(8):
            x0 = ox + plane * 2
            l = pix[x0, oy + y]
            r = pix[x0 + 1, oy + y]
            li = pal.index(l[:3], x0, oy + y) if l[3] else 0
            ri = pal.index(r[:3], x0 + 1, oy + y) if r[3] else 0
            out.append(pair_mask(not l[3], not r[3]))
            out.append(pair_byte(li if l[3] else 0, ri if r[3] else 0))
    return bytes(out)


# ------------------------------------------------------------------ icons

def load_icons():
    im = Image.open(ART / "icons.png").convert("RGBA")
    return im, im.load()


def icon_origin(n):
    return (n % 16) * 32, (n // 16) * 32


OVERLAY_ICONS = list(range(1, 13)) + list(range(20, 27)) + \
    list(range(0x6C, 0x7C))
ORB_FIRST = 22                  # the house markers, 22-26: their orb turns
ORB_MARKERS = 5
ORB_SLOT = 0x20                 # where their 8 frames each go (overlays)


def histogram(images):
    hist = {}
    for im in images:
        for p in im.get_flattened_data():
            if p[3]:
                hist[p[:3]] = hist.get(p[:3], 0) + 1
    return hist


# ---------------------------------------------------------------- sprites
#
# One copy of a frame serves every horizontal position: moving an EGA
# picture by 2 pixels moves plane k's bytes to plane k+1 (plane 3's to
# plane 0 of the next column), so the renderer only chooses which source
# plane feeds which screen plane.  A frame is stored as
#     +0 W, bytes of one plane row;  +1 h, rows
#     then planes 0, 1, 2, 3: h rows of W (mask, data) pairs
# per house palette line (house-p0..p3.png) or once (fixed.png).

LINE_OF_HOUSE = (0, 1, 3, 1, 2, 0)      # sprites.txt "palette lines"

# The battle palette keeps black (colour 0: the fog and beyond the map),
# white, and the house hues the terrain has none of - Atreides blue and
# cyan, Ordos green, Sardaukar purple; the rest is chosen.
BATTLE_FIXED = ((0, 0, 0), (3, 3, 3), (0, 1, 3), (0, 3, 3), (0, 2, 0), (2, 0, 2),
                (3, 2, 1))              # ... and the sand


def parse_sprites():
    frames = {}
    units = {}
    tanks = {}
    cur = None
    for raw in (ART / "sprites.txt").read_text().splitlines():
        line = raw.split("#")[0].rstrip()
        if not line.strip():
            continue
        t = line.split()
        if t[0].isdigit() and len(t) >= 8 and t[1].startswith(("house-p", "fixed")):
            frames[int(t[0])] = dict(sheet=t[1], x=int(t[2]), y=int(t[3]),
                                     w=int(t[4]), h=int(t[5]),
                                     dx=int(t[6]), dy=int(t[7]))
        elif t[0] == "unit":
            n = int(t[1])
            g = int(line.split("group")[1].split(",")[0])
            cur = units[n] = dict(group=g, dirs={})
        elif t[0] == "dir" and cur is not None:
            d = int(t[1])
            walk = int(t[3]) if len(t) > 3 and t[2] == "walk" else None
            carrying = "carrying" in t
            ids = [int(x) for x in line.split("->")[1].split()]
            cur["dirs"][(d, walk, carrying)] = ids
        elif t[0] == "tank":
            tanks[(int(t[1]), int(t[2]), int(t[3]))] = [int(t[5]), int(t[6])]
        elif t[0].startswith("=="):
            cur = None
    return frames, units, tanks


def sprite_sheets():
    out = {}
    for L in range(4):
        out[f"house-p{L}"] = Image.open(ART / f"sprites/house-p{L}.png").convert("RGBA")
    out["fixed"] = Image.open(ART / "sprites/fixed.png").convert("RGBA")
    return out


# The battle's HUD, as sprite frames after the game's own (ids 400 on):
#   400-409 the credits digits      430+n  unit n's portrait (32x24)
#   410     the low-credits warning 458, 459  the Fremen (anims $5E, $68)
#   411     the radar, off          460+n  structure n's portrait
#   412-423 the radar's static      480+9c+n  a bar, colour c (0 green,
#   424     the side panel's label          1 yellow, 2 red, 3 blue, 4
#           (the no sign, 24x24)            orange), n eighths full (32x8)
HUD_DIGITS, HUD_LOW, HUD_RADAR_OFF, HUD_STATIC = 400, 410, 411, 412
HUD_LABEL = 424
HUD_UNIT, HUD_FREMEN, HUD_STRUCT, HUD_BAR = 430, 458, 460, 480
# the pictures ui.txt says are shared
STRUCT_SAME = {1: 0, 4: 3, 8: 6, 10: 7}
UNIT_SAME = {19: 7, 20: 7, 21: 7}
# the battle's palette line 2 (ui.txt, == battle), which the bars and the
# radar are drawn in
LINE2 = ("000000 FFFF00 FFB600 DA4800 910000 480000 00B600 0048DA "
         "6D6D91 FFFFFF 9191B6 242448 000000 9100DA 480091 240024").split()
# the bars' pens: 6, 2, 4 (health by quarter, $00973E), 7 and 3 (the second
# bar: ui_bar2_show_at $00985C, ui_bar2_show_lower_alt $0096AC)
BAR_PENS = (6, 2, 4, 7, 3)
BAR_RGB = tuple(tuple(int(LINE2[p][k:k + 2], 16) for k in (0, 2, 4))
                for p in BAR_PENS)


def hud_frames():
    """-> frames (as parse_sprites), sheets they are cut from."""
    ui = ART / "ui"
    frames, sheets = {}, {}

    def add(fid, name, img, x=0, y=0, w=None, h=None, dx=0):
        sheets[name] = img
        frames[fid] = dict(sheet=name, x=x, y=y, w=w or img.width,
                           h=h or img.height, dx=dx, dy=0)

    def png(name):
        return Image.open(ui / name).convert("RGBA")

    digits = png("battle_credits_digits.png")
    for n in range(10):
        add(HUD_DIGITS + n, "ui:digits", digits, x=n * 8, w=8, h=8)
    add(HUD_LOW, "ui:low", png("battle_low_credits.png"))
    add(HUD_RADAR_OFF, "ui:radar_off", png("battle_radar_off.png"))
    for n in range(12):
        add(HUD_STATIC + n, f"ui:static{n}", png(f"battle_radar_static_{n:02d}.png"))
    for kind, base, same, count in (("unit", HUD_UNIT, UNIT_SAME, 28),
                                    ("structure", HUD_STRUCT, STRUCT_SAME, 20)):
        files = {int(f.name.split("_")[2]): f for f in ui.glob(f"icon_{kind}_*.png")}
        for n in range(count):
            src = files.get(same.get(n, n))
            if src:
                add(base + n, f"ui:{src.name}", Image.open(src).convert("RGBA"))
    add(HUD_FREMEN, "ui:fremen_group", png("icon_fremen_group.png"))
    add(HUD_FREMEN + 1, "ui:fremen", png("icon_fremen.png"))
    # the label: a sprite list of one 3 x 3 piece 4 pixels in ($065B32)
    add(HUD_LABEL, "ui:label", png("cursor_023.png"), dx=4)
    for c, rgb in enumerate(BAR_RGB):
        for n in range(9):
            im = Image.new("RGBA", (32, 8), (0, 0, 0, 255))
            for y in range(1, 7):
                for x in range(n * 4):
                    im.putpixel((x, y), rgb + (255,))
            add(HUD_BAR + c * 9 + n, f"gen:bar{c}_{n}", im)
    return frames, sheets


def frame_bytes(img, fr, pal):
    """A frame -> the stored format (see above)."""
    w, h = fr["w"], fr["h"]
    W = (w + 7) // 8
    px = img.load()
    planes = []
    for plane in range(4):
        rows = bytearray()
        for y in range(h):
            for c in range(W):
                pix = []
                for k in range(2):
                    x = c * 8 + plane * 2 + k
                    if x < w:
                        p = px[fr["x"] + x, fr["y"] + y]
                    else:
                        p = (0, 0, 0, 0)
                    pix.append(p)
                l, r = pix
                li = pal.index(l[:3], c * 8 + plane * 2, y) if l[3] else 0
                ri = pal.index(r[:3], c * 8 + plane * 2 + 1, y) if r[3] else 0
                rows.append(pair_mask(not l[3], not r[3]))
                rows.append(pair_byte(li if l[3] else 0, ri if r[3] else 0))
        planes.append(bytes(rows))
    return bytes([W, h]) + b"".join(planes)


# The unit tables for the renderer: per type a mode and 32 frame ids.
#   0 one frame             4 'Thopter: dir8 * 3 + rotor phase
#   1 dir8                  5 Carryall: dir8 + 8 if carrying
#   2 dir16                 6 Tank, Siege Tank: 0-7 hull, 8-15 turret
#   3 infantry: dir8*4+walk 7 Frigate: 0-7, 8-15 its cargo
def unit_tables(units, tanks):
    out = []
    for n in range(27):
        ids = [0xFFFF] * 32
        mode = 0
        if n in (9, 10):
            mode = 6
            t = n - 9
            for d in range(8):
                ids[d] = tanks[(t, d, 0)][0]
                ids[8 + d] = tanks[(t, 0, d)][1]
        elif n in units:
            u = units[n]
            g = u["group"]
            dirs = u["dirs"]
            if n == 0:
                mode = 5
                for (d, w, c), v in dirs.items():
                    ids[d + (8 if c else 0)] = v[0]
            elif n == 1:
                mode = 4
                for (d, w, c), v in dirs.items():
                    for ph in range(3):
                        ids[d * 3 + ph] = v[2 - ph]  # listed for phases 2 1 0
            elif n == 26:
                mode = 7
                for (d, w, c), v in dirs.items():
                    ids[d] = v[0]
                    ids[8 + d] = v[1]
            elif g in (3, 4):
                mode = 3
                for (d, w, c), v in dirs.items():
                    ids[d * 4 + w] = v[0]
            elif max(d for d, _, _ in dirs) >= 8:
                mode = 2
                for (d, w, c), v in dirs.items():
                    ids[d] = v[0]
            elif g == 0 and len(set(v[0] for v in dirs.values())) == 1:
                mode = 0
                ids[0] = dirs[(0, None, False)][0]
            else:
                mode = 1
                for (d, w, c), v in dirs.items():
                    ids[d] = v[0]
        elif n == 25:
            mode = 0
            ids[0] = 281
        out.append((mode, ids))
    return out


def build(out, preview=None):
    out.mkdir(parents=True, exist_ok=True)
    icons, pix = load_icons()
    frames, units, tanks = parse_sprites()
    sheets = sprite_sheets()
    # the palette: the icons, and the sprites weighted up (small, but
    # they are what the eye follows - the house colours above all)
    hist = histogram([icons])
    for name, im in sheets.items():
        for p in im.get_flattened_data():
            if p[3]:
                hist[p[:3]] = hist.get(p[:3], 0) + 2
    pal = Palette(hist, fixed=BATTLE_FIXED)
    # the HUD's frames join the game's (they do not vote on the palette)
    hframes, hsheets = hud_frames()
    frames.update(hframes)
    sheets.update(hsheets)

    pages = {}
    page_icons = PG_ART
    n_icon_pages = (360 + 31) // 32
    for n in range(360):
        page = page_icons + n // 32
        buf = pages.setdefault(page, bytearray(0x4000))
        ox, oy = icon_origin(n)
        data = b"".join(cell_bytes(pix, pal, ox + (k % 4) * 8, oy + (k // 4) * 8)
                        for k in range(16))
        off = (n % 32) * 512
        buf[off:off + 512] = data
    page_ovl = page_icons + n_icon_pages
    for n in range(128):
        page = page_ovl + n // 16
        buf = pages.setdefault(page, bytearray(0x4000))
        if n not in OVERLAY_ICONS:
            continue
        ox, oy = icon_origin(n)
        data = b"".join(cell_masked(pix, pal, ox + (k % 4) * 8, oy + (k // 4) * 8)
                        for k in range(16))
        off = (n % 16) * 1024
        buf[off:off + 1024] = data
    # the house markers' orb turning (icons_marker.png, the cartridge's
    # $00690C frames): marker 22 + h, frame f is overlay slot
    # ORB_SLOT + h * 8 + f, among the numbers no overlay uses
    mim = Image.open(ART / "icons_marker.png").convert("RGBA")
    mpix = mim.load()
    for h in range(ORB_MARKERS):
        for f in range(8):
            n = ORB_SLOT + h * 8 + f
            assert n not in OVERLAY_ICONS
            ox, oy = f * 32, (ORB_FIRST - 20 + h) * 32
            data = b"".join(cell_masked(mpix, pal, ox + (k % 4) * 8, oy + (k // 4) * 8)
                            for k in range(16))
            buf = pages[page_ovl + n // 16]
            off = (n % 16) * 1024
            buf[off:off + 1024] = data
    next_page = page_ovl + 8

    # the sprite frames, packed into pages.  A frame drawn in the four
    # palette lines ("house-p{L}") has its four copies back to back in one
    # page, so line L is at the address + L * its size (2 + 8 * W * h).
    page_spr = next_page
    blobs = {}
    for fid in sorted(frames):
        fr = frames[fid]
        per_line = "{L}" in fr["sheet"]
        blobs[fid] = (per_line, b"".join(
            frame_bytes(sheets[fr["sheet"].replace("{L}", str(L))], fr, pal)
            for L in (range(4) if per_line else (0,))))
    free = []                           # per sprite page: bytes used
    loc = {}                            # id -> (page | $80 if per line, address)
    for fid in sorted(blobs, key=lambda f: -len(blobs[f][1])):
        per_line, data = blobs[fid]
        for k, used in enumerate(free):         # first fit, biggest first
            if used + len(data) <= 0x4000:
                break
        else:
            free.append(0)
            k = len(free) - 1
        page = page_spr + k
        buf = pages.setdefault(page, bytearray(0x4000))
        buf[free[k]:free[k] + len(data)] = data
        loc[fid] = (page | (0x80 if per_line else 0), 0x4000 + free[k])
        free[k] += len(data)
    at_page = page_spr + len(free) - 1
    assert at_page < 0x80
    next_page = at_page + 1
    nframes = max(frames) + 1
    lines = ["; sprites.inc - the sprite directory (tools/dune_art.py)",
             f"SPR_FRAMES      EQU {nframes}",
             "; per frame: dx, dy (signed, from the object's position), W (bytes",
             "; of a plane row), h (rows)",
             "spr_info:"]
    for fid in range(nframes):
        fr = frames.get(fid, dict(dx=0, dy=0, w=0, h=0))
        lines.append(f"        DB  {fr['dx'] & 255}, {fr['dy'] & 255}, "
                     f"{(fr['w'] + 7) // 8}, {fr['h']}")
    lines.append("; per frame: page (bit 7: four copies, one per palette line, each")
    lines.append("; 2 + 8 * W * h bytes), address; page 0 = no picture")
    lines.append("spr_loc:")
    for fid in range(nframes):
        pg, ad = loc.get(fid, (0, 0))
        lines.append(f"        DB  {pg}")
        lines.append(f"        DW  ${ad:04X}")
    lines.append("spr_line_of_house:")
    lines.append("        DB  " + ", ".join(str(v) for v in LINE_OF_HOUSE))
    lines.append("spr_unit_mode:")
    tabs = unit_tables(units, tanks)
    lines.append("        DB  " + ", ".join(str(m) for m, _ in tabs))
    lines.append("spr_unit_ids:")
    for m, ids in tabs:
        lines.append("        DW  " + ", ".join(str(i) for i in ids))
    (out / "sprites.inc").write_text("\n".join(lines) + "\n")

    for page, buf in pages.items():
        (out / f"page_{page:03d}.bin").write_bytes(bytes(buf))
    (out / "palette_battle.inc").write_text(
        "; the battlefield's palette (tools/dune_art.py)\n        DB "
        + ", ".join(f"${b:02X}" for b in pal.bytes()) + "\n")
    (out / "art.inc").write_text(
        "; art.inc - where the art is (tools/dune_art.py)\n"
        f"PG_ICONS        EQU {page_icons}\n"
        f"PG_OVERLAYS     EQU {page_ovl}\n"
        f"PG_SPRITES      EQU {page_spr}\n"
        f"PG_ART_NEXT     EQU {next_page}\n"
        f"OVL_FOG         EQU ${OVL_FOG:02X}\n"
        f"ORB_FIRST       EQU {ORB_FIRST}\n"
        f"ORB_MARKERS     EQU {ORB_MARKERS}\n"
        f"ORB_SLOT        EQU ${ORB_SLOT:02X}\n"
        "; the side panel's frames that UI chooses (ui_selection_panel)\n"
        f"HUD_LABEL       EQU {HUD_LABEL}\n"
        f"HUD_FREMEN      EQU {HUD_FREMEN}\n"
        f"HUD_BAR_PEN7    EQU {HUD_BAR + 9 * BAR_PENS.index(7)}\n"
        f"HUD_BAR_PEN3    EQU {HUD_BAR + 9 * BAR_PENS.index(3)}\n")
    # the radar's pens: the Mega Drive draws it in palette line 2 of the
    # battle palette (src/res/art/ui.txt); each pen's nearest colour here,
    # as the left and right halves of a plane byte
    rgbs = [ega_rgb(c) for c in pal.cols]
    near = [min(range(16), key=lambda i: dist(tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)),
                                               rgbs[i])) for h in LINE2]
    (out / "radar_pens.inc").write_text(
        "; the radar's 16 pens (Mega Drive line 2) in the battle palette:\n"
        "; a plane byte's left pixel, then its right (tools/dune_art.py)\n"
        "radar_pen_l:\n        DB " + ", ".join(f"${pair_byte(e, 0):02X}" for e in near) + "\n"
        "radar_pen_r:\n        DB " + ", ".join(f"${pair_byte(0, e):02X}" for e in near) + "\n")
    if preview:
        write_preview(Path(preview), icons, pix, pal)
    print(f"dune_art: {len(pages)} pages from {page_icons} (sprites from {page_spr}, "
          f"{len(loc)} frames); palette "
          + " ".join("%d%d%d" % c for c in pal.cols))


def write_preview(d, icons, pix, pal):
    """icons.png as the ZX Evolution will show it."""
    d.mkdir(parents=True, exist_ok=True)
    w, h = icons.size
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            p = pix[x, y]
            px[x, y] = ega_rgb(pal.cols[pal.index(p[:3], x, y)]) if p[3] else (0, 0, 0)
    im.save(d / "icons_ega.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build/gen"))
    ap.add_argument("--preview")
    args = ap.parse_args()
    build(Path(args.out), args.preview)


if __name__ == "__main__":
    main()
