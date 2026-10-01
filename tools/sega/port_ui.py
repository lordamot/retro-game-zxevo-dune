#!/usr/bin/env python3
"""port_ui.py - the Mega Drive Dune II's screens and interface, as port art.

    port_ui.py [all]        capture everything, write src/res/art/ui/*.png,
                            src/res/art/ui.txt and tmp/port-ui/sheet.png
    port_ui.py survey       only the dumps and a layer picture per capture
                            (tmp/port-ui/dumps/<name>/layers.png)
    port_ui.py --fresh ...  throw the cached dumps away first

Every picture here is read out of the VDP the way the game left it, never
out of a screenshot: bin/gen/retro-run plays the cartridge to a moment,
dumps VRAM, CRAM, VSRAM, the VDP registers and the work RAM, and
port_ui_vdp.py draws plane A, plane B, the window and the sprites apart,
each in RGBA with alpha 0 where the VDP draws pen 0.  Where the art is
kept whole in the cartridge (the build and Starport pictures, the unit
and structure icons, the fonts, the radar's switch-on frames, the
mentats' eyes and mouths) it is taken from there instead, but drawn in
the palette the running game had loaded on that screen - so the colours
are always the game's own at that moment.

## How each capture is reached (SCENES and series() below)

From power-on, with the pad:
  logos        700 frames: Virgin and Westwood
  present      1150 frames: "PRESENT" over the starfield
  title        sega_touch.MENU + 100: planet, logo, the menu
  title-ship   a series from frame 1560, every 3 frames: the fly-in
  title-pointer  a series on the menu: the pointer's frames
  house        the menu, C: "Select your House" (house-hl: a series)
  mentat-X     the house screen, right x n, C, 900 frames: the mentat of
               house X (A, O, H) describing it - and his RAM then holds
               all his eye and mouth frames; mentat-A-yes: 1200 more,
               the YES/NO question
  options      sega_touch.OPTIONS          password  sega_touch.PASSWORD
From the save states tools/sega/sega_spec_check.py leaves in tmp/sega/spec:
  brief-X      s9-brief-<word>.state + 90 frames: a briefing's text box
  choose       s9-brief-SPICEDANCE + 1400, C: PROCEED/ADVICE
  campaign     choose, C (PROCEED): a series every 8 frames; #30 is the
               whole map in full light
  battle       m1-1.state (Atreides mission 1): credits, radar, cursor
  sel-struct   the cursor onto the yard, A: the side panel, a structure
  sel-unit     the cursor down onto a unit, A: the side panel, a unit
  build        sel-struct, A: the Construction Yard's panel (screen 5);
               build-item: the cursor down onto the first item
  starport     m1-1.state with the yard's type byte poked to 11
               (Starport), then as build; starport-item: down one
  victory      m1-1.state, START, the password SPLURGEOLA in the battle
               (sega_touch.in_game): 25000 credits meet the quota
  score        victory, C x 4: the score page
  defeat       m1-1.state with the yard's house byte poked to the enemy's:
               no structure left, so the mission is lost
  ending       m1-1.state, the password DUNEFINALE in the battle, 1500
               frames: Arrakis and the end credits
A poke writes the save state's copy of the work RAM, which Genesis Plus
GX keeps at offset $10, byte-swapped per word like every RAM dump.

## What comes from the cartridge instead of the screen

  the build/Starport pictures   the cast at $08829C / $08F1C8, each
                                with its own 16 colours (line 0)
  unit and structure icons      the portrait tables $06E838 (line 1) and
                                $070C9C (line 3), side panel and grids
  the campaign map              ten territories' land and border pieces
                                ($0962D4, $096150), the arrow ($09CF20)
  cursors, radar static, the    animation records ($060E84) through
  low-credits warning           sega_sprites, in the live CRAM
  victory/defeat frames         name tables $0C5DAA / $0C4FF2 put into
                                the captured window
  fonts                         $0506C2 (Format80), $04F6C0 (raw); the
                                score font as the score page has it
  the mentat's eyes and mouth   the capture's RAM ($FF1000, $FF1B40)

The captures are cached in tmp/port-ui/dumps/; --fresh throws them away.
"""

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from port_ui_vdp import VDP, paste, crop_alpha, md_colour  # noqa: E402
import sega_gfx  # noqa: E402
import sega_touch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
RUN = ROOT / "bin/gen/retro-run"
CORE = ROOT / "bin/gen/genesis_plus_gx_libretro.so"
ROMF = ROOT / "orig/dune2.gen"
SPEC = ROOT / "tmp/sega/spec"
WORK = ROOT / "tmp/port-ui"
DUMPS = WORK / "dumps"
OUT = ROOT / "src/res/art/ui"
TXT = ROOT / "src/res/art/ui.txt"

ROM = ROMF.read_bytes()


def w16(a):
    return int.from_bytes(ROM[a:a + 2], "big")


def l32(a):
    return int.from_bytes(ROM[a:a + 4], "big")


# ------------------------------------------------------------ the machine

def retro(lines):
    s = WORK / "run.script"
    s.write_text("\n".join(lines) + "\n")
    p = subprocess.run([str(RUN), "--core", str(CORE), "--rom", str(ROMF),
                        "--script", str(s)], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"retro-run failed:\n{p.stderr[-2000:]}")


def poke(src, name, pokes):
    """A copy of a save state with work-RAM bytes changed: {addr: byte}."""
    dst = DUMPS / f"{name}.state"
    if not dst.exists():
        s = bytearray(Path(src).read_bytes())
        for a, b in pokes.items():
            s[0x10 + ((a & 0xFFFF) ^ 1)] = b
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(s)
    return dst


def dump_lines(d):
    return [f"vram {d}/vram.bin", f"cram {d}/cram.bin",
            f"vsram {d}/vsram.bin", f"vdpreg {d}/vdpreg.bin",
            f"ram {d}/ram.bin", f"shot {d}/shot.bmp", f"save {d}/end.state"]


def state(name):
    return DUMPS / name / "end.state"


def snap(name):
    """The capture `name` (SCENES), run once and cached."""
    d = DUMPS / name
    if not (d / "vram.bin").exists():
        lines = SCENES[name]()
        d.mkdir(parents=True, exist_ok=True)
        retro(lines + dump_lines(d))
    return VDP(d)


def ram(name):
    """The work RAM of a capture, big-endian again, indexed by $FF0000+."""
    r = np.frombuffer((DUMPS / name / "ram.bin").read_bytes(), np.uint8)
    return r.reshape(-1, 2)[:, ::-1].reshape(-1).tobytes()


def series(name, start_lines, step, count):
    """count captures, step frames apart, from one run: [VDP]."""
    d0 = DUMPS / name
    if not (d0 / f"{count - 1:03d}" / "vram.bin").exists():
        lines = list(start_lines)
        for i in range(count):
            d = d0 / f"{i:03d}"
            d.mkdir(parents=True, exist_ok=True)
            lines += dump_lines(d)[:-1] + [f"run {step}"]
        retro(lines)
    return [VDP(d0 / f"{i:03d}") for i in range(count)]


# ---------------------------------------------------------------- scenes

MENU = sega_touch.MENU
YARD_TYPE, YARD_HOUSE = 0xFF4EBA, 0xFF4EC0      # structure slot 0, S2
M1 = str(SPEC / "m1-1.state")                  # Atreides mission 1


def after(name, *lines):
    return [f"load {state(name)}", "run 1"] + list(lines)


def _house(k):
    """Crest k from the left: 0 Atreides, 1 Ordos, 2 Harkonnen."""
    snap("house")
    return after("house", *(["press right 6", "run 20"] * k),
                 "press mdc 6", "run 900")


def _poked_panel(kind, t):
    src = poke(M1, f"poke-{kind}", {YARD_TYPE: t})
    return [f"load {src}", "run 2", "hold right,down", "run 14", "release",
            "run 5", "press mda 6", "run 60", "press mda 6", "run 90"]


SCENES = {
    "logos": lambda: ["run 700"],
    "present": lambda: ["run 1150"],
    "flyby": lambda: ["run 1330"],
    "title": lambda: MENU + ["run 100"],
    "house": lambda: MENU + ["press mdc 6", "run 300"],
    "mentat-A": lambda: _house(0),
    "mentat-O": lambda: _house(1),
    "mentat-H": lambda: _house(2),
    "mentat-A-yes": lambda: (snap("mentat-A"),
                             after("mentat-A", "run 1200"))[1],
    "options": lambda: sega_touch.OPTIONS,
    "password": lambda: sega_touch.PASSWORD,
    "brief-O": lambda: [f"load {SPEC}/s9-brief-ARRAKISSUN.state", "run 90"],
    "brief-H": lambda: [f"load {SPEC}/s9-brief-DEMOLITION.state", "run 90"],
    "brief-A": lambda: [f"load {SPEC}/s9-brief-SPICEDANCE.state", "run 90"],
    "choose": lambda: [f"load {SPEC}/s9-brief-SPICEDANCE.state",
                       "run 1400", "press mdc 6", "run 100"],
    "battle": lambda: [f"load {M1}", "run 2"],
    "sel-struct": lambda: [f"load {M1}", "run 2", "hold right,down",
                           "run 14", "release", "run 5", "press mda 6",
                           "run 60"],
    "sel-unit": lambda: [f"load {M1}", "run 2", "hold down", "run 40",
                         "release", "run 5", "press mda 6", "run 60"],
    "build": lambda: (snap("sel-struct"),
                      after("sel-struct", "press mda 6", "run 90"))[1],
    "build-item": lambda: (snap("build"),
                           after("build", "press down 4", "run 40"))[1],
    "starport": lambda: _poked_panel("starport", 11),
    "starport-item": lambda: (snap("starport"),
                              after("starport", "press down 4",
                                    "run 40"))[1],
    "victory": lambda: [f"load {M1}", "run 1"]
    + sega_touch.in_game("SPLURGEOLA") + ["run 4500"],
    "score": lambda: (snap("victory"),
                      after("victory", "press mdc 6", "run 200",
                            "press mdc 6", "run 200", "press mdc 6",
                            "run 200", "press mdc 6", "run 600"))[1],
    "defeat": lambda: [f"load {poke(M1, 'poke-lose', {YARD_HOUSE: 2})}",
                       "run 1000"],
    "ending": lambda: [f"load {M1}", "run 1"]
    + sega_touch.in_game("DUNEFINALE") + ["run 1500"],
}



# ------------------------------------------------------------ the layers

FONT_MENU = 0x400        # $04F6BE, the screen font: VRAM $8000
FONT_TITLE = 0x480       # $0506C0 by font_load: VRAM $9000
FONT_MENTAT = 0x460      # $0506C0 by mentat_load: VRAM $8C00


def layer(v, which, drop=None):
    """Screen-space RGBA of 'A', 'B', 'W' (the window, where shown) or
    'S' (the sprites).  `drop` is a set of tile numbers (or a function of
    the tile number) whose cells are left out - the printed text, so a
    picture comes out without the words on it."""
    if which == "S":
        return v.screen_sprites()
    if which == "W":
        full, _, m = v.plane_rgba(v.win, 64, 32)
        img = full[:v.sh, :v.sw].copy()
        m = m[:v.sh // 8 + 1, :v.sw // 8]
        wa = v.window_area()
        if wa is None:
            img[...] = 0
    else:
        img, _ = v.screen_plane(0 if which == "A" else 1)
        m = None
    if drop is not None:
        kill = drop if callable(drop) else (lambda t: t in drop)
        base = {"A": v.plane_a, "B": v.plane_b, "W": v.win}[which]
        if which == "W":
            for ty in range(v.sh // 8):
                for tx in range(v.sw // 8):
                    if kill(int(m[ty, tx]) & 0x7FF):
                        img[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = 0
        else:
            # scrolled planes: undo cell by cell through the scroll
            pl = 0 if which == "A" else 1
            for y in range(v.sh):
                hs = v.hscroll(y, pl)
                for x in range(v.sw):
                    vs = v.vscroll(x // 8, pl)
                    tx = ((x - hs) % (v.pw * 8)) // 8
                    ty = ((y + vs) % (v.ph * 8)) // 8
                    if kill(v.entry(base, tx, ty) & 0x7FF):
                        img[y, x] = 0
    return img


def text_cells(v, which, base, lo=0x20, hi=0x80):
    """The printed text of a plane: [(col, row, string, palette line)] in
    screen cells, reading tile - base as the character."""
    if which == "W":
        pb, pw, ph, hs, vs = v.win, 64, 32, 0, 0
    else:
        pl = 0 if which == "A" else 1
        pb = v.plane_a if pl == 0 else v.plane_b
        pw, ph = v.pw, v.ph
        hs, vs = v.hscroll(0, pl), v.vscroll(0, pl)
    out = []
    for row in range(v.sh // 8):
        run, start, line = "", None, None
        for col in range(v.sw // 8 + 1):
            ch = None
            if col < v.sw // 8:
                tx = (col * 8 - hs) // 8 % pw
                ty = (row * 8 + vs) // 8 % ph
                e = v.entry(pb, tx, ty, pw, ph)
                c = (e & 0x7FF) - base
                if lo <= c < hi:
                    ch = chr(c)
            if ch is not None and (line is None or (e >> 13) & 3 == line
                                   or ch == " "):
                if start is None:
                    start, line = col, (e >> 13) & 3
                run += ch
            else:
                if run.strip():
                    lead = len(run) - len(run.lstrip())
                    out.append((start + lead, row, run.strip(), line))
                run, start, line = "", None, None
                if ch is not None:
                    start, line, run = col, (e >> 13) & 3, ch
    return out


def components(img, gap=1):
    """Bounding boxes of the groups of drawn 8x8 cells (8-connected, with
    `gap` empty cells allowed between) - [(x0, y0, x1, y1)] in pixels."""
    h, w = img.shape[0] // 8, img.shape[1] // 8
    occ = img[:h * 8, :w * 8, 3].reshape(h, 8, w, 8).max(axis=(1, 3)) > 0
    seen = np.zeros_like(occ)
    out = []
    for y in range(h):
        for x in range(w):
            if occ[y, x] and not seen[y, x]:
                st, cells = [(y, x)], []
                seen[y, x] = True
                while st:
                    cy, cx = st.pop()
                    cells.append((cy, cx))
                    for dy in range(-1 - gap, 2 + gap):
                        for dx in range(-1 - gap, 2 + gap):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < h and 0 <= nx < w and occ[ny, nx] \
                                    and not seen[ny, nx]:
                                seen[ny, nx] = True
                                st.append((ny, nx))
                ys = [c[0] for c in cells]
                xs = [c[1] for c in cells]
                sub = img[min(ys) * 8:max(ys) * 8 + 8,
                          min(xs) * 8:max(xs) * 8 + 8]
                _, dx, dy = crop_alpha(sub)
                c, _, _ = crop_alpha(sub)
                x0, y0 = min(xs) * 8 + dx, min(ys) * 8 + dy
                out.append((x0, y0, x0 + c.shape[1], y0 + c.shape[0]))
    return sorted(out, key=lambda b: (b[1], b[0]))


# ------------------------------------------------------------ the output

class Art:
    """The pictures written and what ui.txt says about each screen."""

    def __init__(self):
        self.pics = []                 # (file, w, h, screen, where, note)
        self.screens = []              # [dict]
        self.cur = None
        OUT.mkdir(parents=True, exist_ok=True)
        for old in OUT.glob("*.png"):
            old.unlink()

    def screen(self, key, title, capture, v, least, notes=()):
        """Start a screen's section: `least` says which 24 lines matter
        least when the port's 200 lines have to hold the 224."""
        self.cur = {"key": key, "title": title, "capture": capture,
                    "size": f"{v.sw}x{v.sh}" if v else "-",
                    "palette": v.palette_lines() if v else None,
                    "least": least, "pics": [], "text": [],
                    "notes": list(notes)}
        self.screens.append(self.cur)
        return self.cur

    def note(self, *lines):
        self.cur["notes"] += lines

    def save(self, fname, arr, x=None, y=None, where="", note="",
             trim=True):
        """Write a picture; x, y its place on the screen (after the trim)."""
        if trim:
            arr, dx, dy = crop_alpha(arr)
            if x is not None:
                x, y = x + dx, y + dy
        if arr.size == 0:
            print(f"  warning: {fname} is empty")
            return None
        Image.fromarray(np.ascontiguousarray(arr), "RGBA").save(OUT / fname)
        h, w = arr.shape[:2]
        self.pics.append((fname, w, h, self.cur["key"] if self.cur else "-",
                          where, note))
        if self.cur is not None:
            self.cur["pics"].append((fname, x, y, w, h, where, note))
        return (x, y, w, h)

    def text(self, v, which, base, fontname, lo=0x20, rows=None,
             minlen=1):
        for col, row, s, line in text_cells(v, which, base, lo):
            if rows is not None and row not in rows:
                continue
            if len(s) < minlen:
                continue
            self.cur["text"].append((col * 8, row * 8, s, line, fontname,
                                     which))

    def text_at(self, x, y, s, line, fontname, where=""):
        self.cur["text"].append((x, y, s, line, fontname, where))


def cut(arr, x0, y0, x1, y1):
    """A screen rectangle of a layer, as (array, x0, y0)."""
    return arr[y0:y1, x0:x1].copy(), x0, y0


def save_cut(art, fname, arr, box, where, note=""):
    a, x, y = cut(arr, *box)
    return art.save(fname, a, x, y, where, note)


def unique_sprites(vs, keep=lambda s: True):
    """Distinct pictures a set of sprites makes over a series of captures:
    [(rgba, x, y, capture index)] in order of first appearance."""
    seen, out = set(), []
    for i, v in enumerate(vs):
        sp = [s for s in v.sprites() if keep(s)]
        if not sp:
            continue
        img = np.zeros((v.sh + 64, v.sw + 64, 4), np.uint8)
        for s in reversed(sp):
            paste(img, v.sprite_rgba(s), s["x"] + 32, s["y"] + 32)
        c, dx, dy = crop_alpha(img)
        if c.size == 0:
            continue
        h = hashlib.md5(c.tobytes() + bytes(c.shape[:2])).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append((c, dx - 32, dy - 32, i))
    return out


def rgba_of(words, pens):
    """16 CRAM words -> an RGBA lookup; pen 0 transparent."""
    lut = np.zeros((16, 4), np.uint8)
    for p in range(16):
        lut[p, :3] = md_colour(words[p])
        lut[p, 3] = 0 if p == 0 else 255
    return lut[pens]


def rom_words(a, n=16):
    """n Mega Drive colour words (0BGR, even bits) in CRAM form."""
    out = []
    for i in range(n):
        w = w16(a + 2 * i)
        out.append(((w >> 1) & 7) | (((w >> 5) & 7) << 3)
                   | (((w >> 9) & 7) << 6))
    return out


def tiles_pens(data):
    """Raw 4bpp tile bytes -> (n, 8, 8) pens."""
    b = np.frombuffer(bytes(data), np.uint8)
    return np.stack([b >> 4, b & 15], -1).reshape(-1, 8, 8)


def sprite_block(pens, w, h, first=0):
    """w x h cells of a sprite, tiles column by column from `first`."""
    img = np.zeros((h * 8, w * 8), np.uint8)
    for cx in range(w):
        for cy in range(h):
            img[cy * 8:cy * 8 + 8, cx * 8:cx * 8 + 8] = \
                pens[first + cx * h + cy]
    return img


# ------------------------------------------------------------ the screens

def starfield(v):
    """Plane B's stars: the tiles of its small groups, their glyphs, and
    where each is in the 1024-pixel plane."""
    full, _, m = v.plane_rgba(v.plane_b)
    stars, tiles = [], set()
    for (x0, y0, x1, y1) in components(full, gap=0):
        if x1 - x0 <= 8 and y1 - y0 <= 8:
            for ty in range(y0 // 8, (y1 - 1) // 8 + 1):
                for tx in range(x0 // 8, (x1 - 1) // 8 + 1):
                    if m[ty, tx] & 0x7FF:
                        tiles.add(int(m[ty, tx]) & 0x7FF)
            stars.append((x0, y0, full[y0:y1, x0:x1]))
    return stars, tiles, full, m


def do_title(art):
    # -- Virgin and Westwood
    v = snap("logos")
    art.screen("logos", "Virgin and Westwood (the opening)", "logos", v,
               "rows 208-223: stars only")
    A = layer(v, "A")
    save_cut(art, "title_virgin.png", A, (112, 8, 216, 100), "plane A")
    save_cut(art, "title_westwood.png", A, (56, 100, 264, 170), "plane A",
             "with AND above it")
    save_cut(art, "title_copyright.png", A, (40, 172, 272, 212), "plane A")
    stars, star_tiles, full, _ = starfield(v)
    glyphs = {}
    for x, y, g in stars:
        k = g.tobytes() + bytes(g.shape[:2])
        if k not in glyphs:
            glyphs[k] = (len(glyphs), g)
    for k, (i, g) in glyphs.items():
        art.save(f"title_star_{i}.png", g, None, None, "plane B",
                 "a star of the scrolling starfield")
    art.note("starfield: plane B is 1024x256 and scrolls; screen x = "
             "(plane x + hscroll) mod 1024, hscroll 320 at rest.  Stars "
             "(plane x, y, glyph):")
    row = []
    for x, y, g in stars:
        i = glyphs[g.tobytes() + bytes(g.shape[:2])][0]
        row.append(f"{x},{y},{i}")
    for k in range(0, len(row), 10):
        art.note("  " + " ".join(row[k:k + 10]))

    v = snap("present")
    art.screen("present", "PRESENT", "present", v,
               "rows 200-223: stars only")
    art.text(v, "A", FONT_TITLE, "title")
    art.note("the logos fade out, then PRESENT (font title, line 3) fades "
             "in and out over the stars; frames ~1100-1250 after power-on")

    # -- the title: the planet slides in, the fly-in, the logo, the menu
    v = snap("title")
    sc = art.screen("title", "Title and main menu", "title", v,
                    "rows 208-223: the licence line (keep it at 192) and "
                    "stars; or drop rows 0-23, stars only")
    stars, star_tiles, full, m = starfield(v)
    kill = star_tiles
    planet = full.copy()
    for ty in range(m.shape[0]):
        for tx in range(m.shape[1]):
            if (int(m[ty, tx]) & 0x7FF) in kill:
                planet[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = 0
    hs = v.hscroll(0, 1)
    px0 = 700
    p, dx, dy = crop_alpha(planet[:, px0:])
    art.save("title_planet.png", p, (px0 + dx + hs) % 1024, dy,
             "plane B", f"at rest; its plane x is {px0 + dx}")
    A = layer(v, "A", drop=lambda t: FONT_TITLE + 0x20 <= t < FONT_TITLE + 0x80)
    save_cut(art, "title_logo.png", A, (32, 64, 288, 112), "plane A",
             "DUNE")
    save_cut(art, "title_subtitle.png", A, (40, 120, 272, 144), "plane A",
             "The Battle for Arrakis")
    save_cut(art, "title_licence.png", A, (88, 196, 232, 212), "plane A",
             "LICENSED BY SEGA ENTERPRISES, LTD.")
    art.text(v, "A", FONT_TITLE, "title")
    # the pointer: menu_pointer_set_frame's seven frames ($007E52)
    vs = series("title-pointer", MENU + ["run 100"], 2, 40)
    ptr = unique_sprites(vs)
    for i, (img, x, y, _) in enumerate(ptr):
        art.save(f"title_pointer_{i}.png", img, x, y, "sprite",
                 "the menu pointer, frame %d" % i)
    art.note("planet slide: plane B's hscroll runs from 999 (planet just "
             "off the right) to 320 over ~260 frames, 3 px a frame then "
             "easing (measured: 969 at frame 1150, 519 at 1300, 384 at "
             "1350, 321 at 1400, 320 from 1410)",
             "the logo, subtitle and licence appear at ~1600, the menu "
             "at ~1900; after 900 idle frames the opening runs again",
             "menu: up/down move the pointer a row (song 11), A/B/C/Start "
             "choose; START GAME -> house choice, OPTIONS -> options, "
             "TUTORIAL -> the tutorial")
    # the fly-in: a ship diving at the planet, getting smaller
    vs = series("title-ship", ["run 1560"], 3, 40)
    ships = unique_sprites(vs)
    for i, (img, x, y, k) in enumerate(ships):
        art.save(f"title_ship_{i:02d}.png", img, x, y, "sprites",
                 f"fly-in frame {i}, frame {1560 + 3 * k} after power-on")



HOUSES = {"A": "atreides", "O": "ordos", "H": "harkonnen"}


def sprites_img(v, keep):
    """The sprites `keep` accepts, composed at their screen places."""
    img = np.zeros((v.sh + 128, v.sw + 128, 4), np.uint8)
    for s in reversed(v.sprites()):
        if keep(s):
            paste(img, v.sprite_rgba(s), s["x"] + 64, s["y"] + 64)
    c, dx, dy = crop_alpha(img)
    return c, dx - 64, dy - 64


def do_house(art):
    v = snap("house")
    art.screen("house", "Select your House (screen 0)", "house", v,
               "rows 160-223: nothing below the labels (crop 0-199)")
    W = layer(v, "W")
    save_cut(art, "house_title.png", W, (88, 28, 232, 52), "window",
             "Select your House")
    for k, h in enumerate(("atreides", "ordos", "harkonnen")):
        x = 32 + 88 * k
        save_cut(art, f"crest_{h}.png", W, (x, 64, x + 80, 128), "window",
                 "crest in its frame")
        save_cut(art, f"crest_label_{h}.png", W, (x, 136, x + 80, 152),
                 "window", "name plate")
    vs = series("house-hl", SCENES["house"](), 3, 24)
    for i, (img, x, y, _) in enumerate(unique_sprites(vs)):
        art.save(f"house_highlight_{i}.png", img, x, y, "sprites",
                 "the plate highlight under the choice, frame %d" % i)
    art.note("the highlight sits on the chosen name plate (x 32, 120 or "
             "208, y 136); left/right move it; A, B, C (or any) choose "
             "the house under it - sega_touch walks it with right and C",
             "then the mentat of that house describes it and asks YES/NO; "
             "NO brings the crests back.  Music track $1C (song 9)")


def mentat_face(art, key, v, r):
    """The mentat's body (sprites), and his eye and mouth frames from the
    RAM mentat_load unpacked them to ($FF1000, $FF1B40)."""
    h = HOUSES[key]
    ov = lambda s: s["pal"] == 3 and 0x589 <= s["tile"] < 0x5C5
    body, bx, by = sprites_img(v, lambda s: s["pal"] == 3 and not ov(s)
                               and s["x"] > -64)
    art.save(f"mentat_{h}.png", body, bx, by, "sprites",
             "the mentat without his eyes and mouth")
    eyes = [s for s in v.sprites() if ov(s) and s["tile"] < 0x59B]
    mouth = [s for s in v.sprites() if ov(s) and s["tile"] >= 0x59B]
    lut = v.lut[3]
    for kind, sp, base, size, t0 in (("eyes", eyes, 0x1000, 0x240, 0x589),
                                     ("mouth", mouth, 0x1B40, 0x460,
                                      0x59B)):
        x0 = min(s["x"] for s in sp)
        y0 = min(s["y"] for s in sp)
        seen = []
        for k in range(5):
            pens = tiles_pens(r[base + k * size:base + (k + 1) * size])
            img = np.zeros((64, 64, 4), np.uint8)
            for s in sp:
                blk = sprite_block(pens, s["w"], s["h"], s["tile"] - t0)
                paste(img, lut[blk], s["x"] - x0, s["y"] - y0)
            if any(np.array_equal(img, o) for o in seen):
                continue
            seen.append(img)
            c = img[:max(s['y'] - y0 + s['h'] * 8 for s in sp),
                    :max(s['x'] - x0 + s['w'] * 8 for s in sp)]
            art.save(f"mentat_{h}_{kind}_{len(seen) - 1}.png", c, x0, y0,
                     "sprites", f"{kind}, frame {k} of the RAM copy "
                     f"(${0xFF0000 + base + k * size:06X})", trim=False)


def do_mentat(art):
    for key in "AOH":
        v = snap(f"mentat-{key}")
        h = HOUSES[key]
        art.screen(f"mentat-{h}", f"The mentat of house {h.title()} "
                   "describes it", f"mentat-{key}", v,
                   "rows 200-223: the bottom of the mentat's portrait "
                   "(crop it, or move him up 24)")
        mentat_face(art, key, v, ram(f"mentat-{key}"))
        art.text(v, "A", FONT_MENTAT, "mentat")
        art.note("behind him: the campaign map (== campaign) with the "
                 "ownership before mission 1, in this screen's palette "
                 "(dimmed; lines 0-2 below)")
    art.note("text box: mentat_speak splits the text at 36 columns and "
             "prints a sentence at a time from column 2, row 2 (x 16, "
             "y 16), up to four rows, font mentat in line 2; the mouth "
             "moves 4 frames a character while talking; A, B or C "
             "skips ahead",
             "eyes: a random frame at random intervals; mouth: a random "
             "frame 0-4 while talking, frame 0 when quiet "
             "(mentat_animate_face $01F622)",
             "the planes are scrolled down: vscroll 24 on both")
    # YES / NO
    v = snap("mentat-A-yes")
    art.screen("mentat-yesno", "The mentat asks: join the house? YES/NO",
               "mentat-A-yes", v, "as the mentat")
    art.text(v, "A", FONT_MENTAT, "mentat")
    buttons(art, v, ("yes", "no"))
    art.note("left/right move the highlight, A/B/C choose "
             "(mentat_choose $025BB4): YES -> mission 1's briefing, NO -> "
             "the crests")


def buttons(art, v, names):
    sp = [s for s in v.sprites() if s["pal"] == 2 and s["x"] > -64]
    hl = [s for s in sp if 0x589 <= s["tile"] < 0x59D]
    b1 = [s for s in sp if 0x59D <= s["tile"] < 0x5B1]
    b2 = [s for s in sp if 0x5B1 <= s["tile"] < 0x5C5]
    done = {f for f, *_ in art.pics}
    for nm, group in ((names[0], b1), (names[1], b2),
                      ("highlight", hl)):
        if f"mentat_button_{nm}.png" in done:
            continue
        img, x, y = sprites_img(v, lambda s, g=group: s in g)
        art.save(f"mentat_button_{nm}.png", img, x, y, "sprites",
                 "the frame over the chosen button" if nm == "highlight"
                 else f"the {nm.upper()} button")


def do_brief(art):
    for key, word in (("A", "SPICEDANCE"), ("O", "ARRAKISSUN"),
                      ("H", "DEMOLITION")):
        v = snap(f"brief-{key}")
        art.screen(f"briefing-{HOUSES[key]}", f"Briefing ({word}): the "
                   "mentat over the map", f"brief-{key}", v,
                   "as the mentat")
        art.text(v, "A", FONT_MENTAT, "mentat")
    art.note("the mentat says the mission's first string "
             "(res/text/briefings.txt), then PROCEED/ADVICE")
    v = snap("choose")
    art.screen("briefing-choose", "Briefing: PROCEED / ADVICE", "choose",
               v, "as the mentat")
    buttons(art, v, ("proceed", "advice"))
    art.note("ADVICE repeats the fourth string (the advice) and asks "
             "again; PROCEED plays effect 38 and music $1D (song 7) and "
             "goes on to the campaign map")
    do_campaign(art)


def territory_lists(ptab, offs):
    """The ten piece lists of the campaign map: [[(x, y, w, h, tile)]].
    A list is (x, y, VDP size), then (dx, dy, size) steps, to a zero
    step; the tile number runs on through the lists (campaign_draw_pieces
    $023F5C)."""
    out = []
    for n in range(10):
        a, t = l32(ptab + 4 * n), l32(offs + 4 * n) // 32
        pcs, x, y = [], 0, 0
        while True:
            dx, dy, sz = (w16(a + 2 * i) for i in range(3))
            a += 6
            dx -= 0x10000 if dx & 0x8000 else 0
            dy -= 0x10000 if dy & 0x8000 else 0
            if pcs and dx == dy == sz == 0:
                break
            x, y = (x + dx, y + dy) if pcs else (dx, dy)
            w, h = (sz >> 2) + 1, (sz & 3) + 1
            pcs.append((x, y, w, h, t))
            t += w * h
        out.append(pcs)
    return out


def draw_pieces(pcs, tiles_at, lut):
    img = np.zeros((256, 400, 4), np.uint8)
    for x, y, w, h, t in pcs:
        pens = tiles_pens(ROM[tiles_at + t * 32:tiles_at + (t + w * h) * 32])
        paste(img, lut[sprite_block(pens, w, h)], x, y)
    return img


def do_campaign(art):
    vs = series("campaign", after("choose", "press mdc 6"), 8, 60)
    v = vs[30]
    art.screen("campaign", "The campaign map (campaign_briefing $025ECA, "
               "campaign_attack $026108)", "campaign #30", v,
               "rows 0-23 (black above the map); the map is y 48-157")
    live = layer(v, "B")
    paste(live, layer(v, "A"), 0, 0)
    art.save("campaign_map.png", live, 0, 0, "planes B+A",
             "the whole map as shown (Atreides mission 3's owners), for "
             "reference")
    land = territory_lists(0x0962D4, 0x09D13C)
    bord = territory_lists(0x096150, 0x09D114)
    # where the bitmap lands on the screen: the best fit of all the land
    allland = np.zeros((256, 400, 4), np.uint8)
    for pcs in land:
        paste(allland, draw_pieces(pcs, 0x0986DE, v.lut[0]), 0, 0)
    best = None
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            a = allland[max(0, -dy):, max(0, -dx):][:v.sh - max(0, dy),
                                                    :v.sw - max(0, dx), 3]
            b = live[max(0, dy):, max(0, dx):][:a.shape[0], :a.shape[1], 3]
            sc = int(((a > 0) == (b > 0)).sum())
            if best is None or sc > best[0]:
                best = (sc, dx, dy)
    _, ox, oy = best
    for n, pcs in enumerate(land):
        img = draw_pieces(pcs, 0x0986DE, v.lut[0])
        c, dx, dy = crop_alpha(img)
        art.save(f"campaign_land_{n}.png", c, dx + ox, dy + oy,
                 "ROM $0986DE", f"territory {n}'s land, owner 0's colours")
    b = np.zeros((256, 400, 4), np.uint8)
    for pcs in bord:
        paste(b, draw_pieces(pcs, 0x09631C, v.lut[0]), 0, 0)
    c, dx, dy = crop_alpha(b)
    art.save("campaign_borders.png", c, dx + ox, dy + oy, "ROM $09631C",
             "the lines between the territories, drawn over the land")
    arrows, _ = sega_gfx.lcw(ROM[0x09CF20:0x09D114])
    pens = tiles_pens(arrows[:36 * 32])
    for k, nm in enumerate(("up", "right", "down", "left")):
        art.save(f"campaign_arrow_{nm}.png",
                 v.lut[2][sprite_block(pens, 3, 3, 9 * k)], None, None,
                 "ROM $09CF20", "the arrow, sprite in line 2")
    art.note(f"the land and border pieces are the ROM's piece lists "
             f"($0962D4, $096150) offset by ({ox}, {oy}) on the screen; "
             "each territory is drawn in its owner's palette line: owner "
             "0 nobody line 0, 1 Harkonnen line 2, 2 Atreides line 1, "
             "3 Ordos line 3 ($095CE8) - the PNGs are in line 0, so "
             "swap pens by the lines below; the borders always in line 0",
             "owners before each mission (a row of ten territories per "
             "mission, the tenth row after the last win; $095D0C):")
    for hid, hn in ((1, "Atreides"), (2, "Ordos"), (0, "Harkonnen")):
        a = l32(0x095F64 + 4 * hid)
        rows = [" ".join(str(w16(a + 20 * m + 2 * k)) for k in range(10))
                for m in range(10)]
        art.note(f"  {hn:9s} " + " | ".join(rows))
    art.note("the territory attacked next (arrow at -32, -50 from its "
             "centre, picture 0; $095F70), missions 1-9:")
    for hid, hn in ((1, "Atreides"), (2, "Ordos"), (0, "Harkonnen")):
        a = l32(0x096048 + 4 * hid)
        art.note(f"  {hn:9s} " + " ".join(str(w16(a + 8 * m + 6))
                                          for m in range(9)))
    art.note("sequence: after PROCEED the mentat slides left (24 frames, "
             "mentat_leave $025DAE) and the map brightens; the "
             "territories then come apart as sprites and drop away while "
             "the next one is zoomed into (song 7); nothing here can be "
             "chosen")



# ------------------------------------------------------------ the battle

import sega_sprites  # noqa: E402

_AN = None


def anim(i, cram):
    """Animation record i ($060E84) drawn as sega_sprites does, but in the
    colours `cram` (64 nine-bit words) - the running game's palette."""
    global _AN
    if _AN is None:
        _AN = sega_sprites.analyse(ROM)
    an = _AN
    base = sega_sprites.vram_of(ROM, an)
    (_, pt, pa, lt, la) = an["records"][i]
    kind = an["kinds"][i][0]
    ps = sega_sprites.pieces(ROM, la)
    v = bytearray(base)
    if kind == "create":
        t0 = ps[0][0]
        v[t0 * 32:t0 * 32 + ps[0][1] * 32] = ROM[pa:pa + ps[0][1] * 32]
    elif kind == "cursor":
        bt = 0x7C4 if min(p[0] for p in ps) >= 0x7C4 else 0x7BC
        sz = an["kinds"][i][1][1]
        v[bt * 32:bt * 32 + sz] = ROM[pa:pa + sz]
    old = sega_sprites.BATTLE_CRAM
    sega_sprites.BATTLE_CRAM = list(cram)
    try:
        img = sega_sprites.draw(ROM, v, ps, 0)
    finally:
        sega_sprites.BATTLE_CRAM = old
    xs = [p[4] for p in ps]
    ys = [p[5] for p in ps]
    return np.array(img.convert("RGBA")), min(xs), min(ys)


def names_of(kind):
    """Type number -> short name, from orig/sega/res/art/sprites/."""
    out = {}
    for f in (ROOT / "orig/sega/res/art/sprites").glob(f"{kind}_*.png"):
        n = f.stem.split("_", 2)
        out[int(n[1])] = n[2]
    return out


BUILDINGS = names_of("building")
UNITS = names_of("unit")
UNIT_EXTRA = {19: "frigate", 20: "unit_20", 6: "saboteur"}

CURSORS = {
    0: "the battle cursor: brackets", 1: "placement footprint, 1x1, fits",
    4: "placement footprint, 2x2, fits", 5: "attack: the target cross",
    6: "move: four arrows in", 8: "the pointer arrow (menus)",
    9: "selected structure's corners", 10: "corners (another size)",
    11: "corners (another size)", 12: "placement footprint, 3x2, fits",
    13: "placement footprint, 3x2, fits", 14: "placement footprint, 3x3",
    15: "placement footprint, 1x1 (red: does not fit)",
    18: "placement footprint, 2x2, does not fit",
    19: "placement footprint, 3x2, does not fit",
    20: "placement footprint, 3x2, does not fit",
    21: "placement footprint, 3x3, does not fit",
    29: "target mode: the red arrows", 30: "corners, small",
    23: "refused (the no sign)", 24: "OK", 26: "repair: the hammer",
}


def do_battle(art):
    v = snap("battle")
    cram = v.cramw
    art.screen("battle", "The battlefield (Atreides mission 1)", "battle",
               v, "the map view simply shows 24 lines less; the radar "
               "(y 144-207) and credits (y 16-23) move up 24 or stay")
    art.note("plane B is the map (32x32 squares of 8x8 tiles), plane A "
             "the fog over it; everything below is a sprite in the "
             "battle palette (lines 0-3 above, the same for all houses; "
             "pens 13-15 of each line are a house's colours: line 0 "
             "Harkonnen, 1 Atreides, 3 Ordos, 2 the others)")
    # credits: "%6d"; $050ACC is a blank tile, then 0-9 (ui_credits_draw)
    digits = tiles_pens(ROM[0x050ACC + 32:0x050ACC + 352])
    sheet = np.concatenate([v.lut[1][d] for d in digits], axis=1)
    art.save("battle_credits_digits.png", sheet, None, None,
             "ROM $050AEC", "0-9, 8x8 each, sprite line 1", trim=False)
    art.note("credits: six 8x8 digits, '%6d' right-aligned, sprites at "
             "x 256-303, y 16 (build/Starport panels: x 248); the shown "
             "number rolls towards the real one, effect 52 up / 53 down "
             "every 4th step (ui_draw_credits $011F34)")
    rad, x, y = sprites_img(v, lambda s: 0x680 <= s["tile"] < 0x6C0)
    art.save("battle_radar_off.png", rad, x, y, "sprites",
             "the radar with no Outpost: its frame, dark inside (line 2)")
    art.note("radar: 64x64 at (240,144), four 32x32 sprites; every frame "
             "one of its 64 rows is redrawn from the map (radar_frame "
             "$005124): a square's landscape colour, or the owner's "
             "colour of what stands on it")
    for k, i in enumerate(range(37, 49)):
        img, dx, dy = anim(i, cram)
        art.save(f"battle_radar_static_{k:02d}.png", img, 240, 144,
                 f"anim {i}", f"radar static, frame {k}")
    for nm, a0 in (("on", 0x068C16), ("off", 0x068BCA)):
        steps, a = [], a0
        while l32(a):
            q = l32(a)
            steps.append(f"{(q & 0xFFFFFF) - 0x0673CA >> 9:02d}x{q >> 24}")
            a += 4
        art.note(f"radar switch-{nm} (frame script ${a0:06X}): "
                 "static frame x frames shown - " + " ".join(steps)
                 + (" - then the map" if nm == "on" else ""))
    art.note("the static frames are drawn with pens 13-15 of line 0 "
             "(Harkonnen red); the game puts them in the player's own "
             "line, so swap those three pens for the house")
    img, dx, dy = anim(108, cram)
    art.save("battle_low_credits.png", img, None, None, "anim 108",
             "the blinking CREDITS warning, three pieces ($009BDA): on "
             "90 ticks, off 900, on 60... while credits < 50")
    art.note("view marker: the 1x1 sprite on the radar (tile $7A1, "
             "line 2) is the square under the cursor (radar_place_marker $005518)")
    for i, d in sorted(CURSORS.items()):
        img, dx, dy = anim(i, cram)
        art.save(f"cursor_{i:03d}.png", img, dx, dy, f"anim {i}",
                 f"{d}; x, y are its offset from the cursor point")
    # the side panel
    v = snap("sel-struct")
    art.screen("sidepanel", "Battle side panel: a structure selected",
               "sel-struct", v, "the panel is y 48-135: keep it")
    for nm, t in (("upper_picture", 0x794), ("health_bar", 0x7A2),
                  ("lower_picture", 0x7A6)):
        img, x, y = sprites_img(v, lambda s, t=t: s["tile"] == t)
        art.save(f"sidepanel_{nm}_example.png", img, x, y, "sprite",
                 "as captured (a Construction Yard, full health)")
    img, x, y = sprites_img(v, lambda s: s["tile"] == 0x7C4)
    art.save("battle_selection_corners.png", img, x, y, "sprites",
             "the four corners round a selected structure (line 0)")
    v2 = snap("sel-unit")
    img, x, y = sprites_img(v2, lambda s: s["tile"] == 0x7C4)
    art.save("battle_selection_unit.png", img, x, y, "sprites",
             "the marks round a selected unit (line 3)")
    art.note("upper picture: the selection's portrait, 32x24 sprite at "
             "(272,48) - structures in line 1, units in line 3 "
             "(icon_*.png); health bar: 32x8 at (272,72), filled in "
             "proportion, the fill pen by quarter of health 4, 2, 2, 6 "
             "of line 2 ($00973E); lower picture 32x24 at (272,88): what "
             "is being built, or the Repair Facility's unit",
             "second bar (production progress, upgrade countdown, "
             "palace charge, windtrap power, spice gauge, starport "
             "delivery): 32x8 at (272,112) or (272,80) ($06A7DA/$06A7E0) "
             "in pen 7 (or 3) of line 2 (ui_bar2_show_at_colour $009862)",
             "for an enemy only the portrait and health bar; for a "
             "Harvester also its load (ui_draw_selection_panel $0294BE)")
    icons(art, v)


def icons(art, v):
    """The unit and structure icons: 32x24, the portrait tables at
    $06E838 (structures, line 1) and $070C9C (units, line 3), which the
    side panel, the build grid and the Starport share.  The line is the
    portrait animation record's ($060E84: list type $FE line 1, $FF line
    3 - ui_picture1_show $0098DC), where one exists for the picture: the
    Sonic Tank's is $FE, line 1, the one unit drawn in the structures'
    colours."""
    done = {}
    specials = {-1: "exit", -2: "repair", -3: "cancel",
                -4: "repair_off", -5: "cancel_off"}
    anim_line = {}
    for _, _, pixels, lt, _ in sega_sprites.records(ROM):
        if lt in (0xFE, 0xFF):
            anim_line[pixels] = 1 if lt == 0xFE else 3
    for base, tline, kind, names, n in (
            (0x06E838, 1, "structure", BUILDINGS, 20),
            (0x070C9C, 3, "unit", {**UNIT_EXTRA, **UNITS}, 33)):
        for i in range(-5, n):
            p = l32(base + 4 * i)
            if not (0x06D000 <= p < 0x071500):
                continue
            line = anim_line.get(p, tline)
            pens = tiles_pens(ROM[p:p + 0x180])
            img = v.lut[line][sprite_block(pens, 4, 3)]
            if i < 0:
                nm = f"icon_{specials[i]}_line{line}.png"
                what = f"grid entry {i}, {specials[i]}"
            else:
                nm = f"icon_{kind}_{i:02d}_{names.get(i, 'x')}.png"
                what = f"{kind} {i}"
            if (p, line) in done:
                art.note(f"{nm[:-4]}: the same picture as {done[(p, line)]}")
                continue
            done[(p, line)] = nm
            art.save(nm, img, None, None, f"ROM ${p:06X}",
                     f"{what}, line {line}", trim=False)
    # two portraits no table names, only the side panel's code
    # (ui_draw_selection_panel $0294BE): the Fremen, drawn as animations
    # $5E and $68 ($060E84) in line 3
    for n, nm, what in ((0x5E, "icon_fremen_group.png", "a Fremen house's "
                         "Troopers; the Atreides Palace's lower picture"),
                        (0x68, "icon_fremen.png", "any other Fremen-house "
                         "unit")):
        p = l32(0x060E84 + 8 * n)
        pens = tiles_pens(ROM[p:p + 0x180])
        art.save(nm, v.lut[3][sprite_block(pens, 4, 3)], None, None,
                 f"ROM ${p:06X}", f"anim ${n:02X}: {what}, line 3",
                 trim=False)


def do_panels(art):
    for scene, key, title in (("build-item", "build",
                               "Build panel (screen 5), Construction Yard"),
                              ("starport-item", "starport",
                               "Starport panel (screen 6)")):
        v = snap(scene)
        art.screen(key, title, scene, v,
                   "rows 208-223: the panel's bottom edge; or 0-23 above "
                   "the credits.  Either loses a piece of the frame")
        W = layer(v, "W", drop=lambda t: FONT_MENU <= t < FONT_MENU + 0x80
                  or 0x380 <= t < 0x3D4)
        art.save(f"{key}_panel.png", W, 0, 0, "window", "the panel, "
                 "without the item picture and the words", trim=False)
        art.text(v, "W", FONT_MENU, "menu")
        icons_used = {}
        for s in v.sprites():
            t = s["tile"]
            if t in (0x2E0, 0x2E4, 0x2E8):
                nm = {0x2E0: "cost", 0x2E4: "power_or_ammo",
                      0x2E8: "armour"}[t]
                img, x, y = sprites_img(v, lambda q, s=s: q["i"] == s["i"])
                art.save(f"{key}_symbol_{nm}.png", img, x, y, "sprite",
                         "label of an info row")
            elif t == 0x3E0:
                img, x, y = sprites_img(v, lambda q, s=s: q["i"] == s["i"])
                art.save(f"{key}_marker.png", img, None, None, "sprite",
                         "the frame round the grid cell under the cursor "
                         "(line 2)")
            elif t == 0x2F0:
                img, x, y = sprites_img(v, lambda q, s=s: q["i"] == s["i"])
                art.save(f"{key}_footprint_example.png", img, x, y,
                         "sprite", "a structure's footprint, drawn from "
                         "its shape by menu_draw_pattern $007E8E")
        if key == "starport":
            vs = series("starport-anim", [f"load {state('starport')}",
                                          "run 1"], 6, 40)
            for nm, keep, what in (
                    ("lights", lambda s: s["tile"] in (0x1C5, 0x1C7),
                     "the column of lights by the picture box"),
                    ("frigate", lambda s: 0x1C0 <= s["tile"] < 0x200
                     and s["tile"] not in (0x1C5, 0x1C7),
                     "the dot flying the 179-point path ($008B08)")):
                for i, (img, x, y, _) in enumerate(unique_sprites(vs,
                                                                  keep)):
                    art.save(f"starport_{nm}_{i}.png", img, x, y,
                             "sprites", f"{what}, frame {i} "
                             "(ui_starport_animate $0088D6)")
            art.note("grid: 3 wide, 4 rows of 32x24 icons from (32,48); "
                     "the first row EXIT, FIX, STOP; the offer is the "
                     "unit types in stock (S6), icons in line 3",
                     "info box: name centred in 12 columns at row 13, "
                     "then price, stock ('Out Of Stock' at 0) and "
                     "'Send Order' with the total; A buys one if the "
                     "credits and the stock allow and no Frigate is on "
                     "its way",
                     "the picture box (160,40)-(255,95) shows the unit's "
                     "own picture (build_item_unit_*.png) with its 16 "
                     "colours in line 0")
        else:
            art.note("grid: 3 x 6 cells of 32x24 at x 32/64/96, y 48 + "
                     "24 n ($04A14A); cell 0-2 EXIT, FIX, STOP "
                     "(icon_exit/repair/cancel; *_off when disabled), then "
                     "the buildable types sorted by their +$20; icons of "
                     "structures in line 1, units in line 3",
                     "the picture box (160,40)-(255,95): the item's own "
                     "96x56 picture (build_item_*.png), its 16 colours "
                     "sent to line 0; the name centred in 12 columns at "
                     "(176,104), then three figures '%8.1d' right-aligned "
                     "to x 255 at y 128, 160, 192: cost, power (structures; "
                     "units: +$54) and hit points; '* Upgrade *' costs half",
                     "pad: moves a cell if it holds an item; A takes it "
                     "(a disabled one buzzes, effect 47); B and C nothing")
    # the pictures in the box: the cast, each in its own colours
    for table, n, kind, names in ((0x08829C, 19, "building", BUILDINGS),
                                  (0x08F1C8, 27, "unit", UNITS)):
        for i in range(n):
            a = l32(table + 4 * i)
            size = w16(a + 0xC8)
            try:
                data, _ = sega_gfx.lcw(ROM[a + 0xCA:a + 0xCA + 0x10000],
                                       expect=size)
            except Exception:
                continue
            pens = tiles_pens(data[:len(data) // 32 * 32])
            pal = rom_words(a)
            img = np.zeros((56, 96, 4), np.uint8)
            for r in range(7):
                for c in range(12):
                    e = (w16(a + 0x20 + 2 * (r * 12 + c)) + 0x380) & 0x9FFF
                    t = (e & 0x7FF) - 0x380
                    if t < 0 or t >= len(pens):
                        continue
                    tp = pens[t]
                    if e & 0x800:
                        tp = tp[:, ::-1]
                    if e & 0x1000:
                        tp = tp[::-1, :]
                    img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = rgba_of(pal, tp)
            nm = names.get(i, f"{i:02d}")
            art.save(f"build_item_{kind}_{i:02d}_{nm}.png", img, 160, 40,
                     f"ROM ${a:06X}", "its own 16 colours (CRAM line 0)",
                     trim=False)


# ------------------------------------------------------ the other screens

def do_options(art):
    v = snap("options")
    art.screen("options", "Options (screen 14; 1-3 are copies)", "options",
               v, "rows 168-199 hold only the picture; drop 200-223 "
               "(below PRESS START TO EXIT, which is at y 192)")
    W = layer(v, "W")
    art.save("options_screen.png", W, 0, 0, "window",
             "the picture with its words (the labels are picture tiles, "
             "not the font)", trim=False)
    img, x, y = sprites_img(v, lambda q: q["tile"] == 0x7BC)
    art.save("options_pointer.png", img, x, y, "sprite", "the row pointer")
    # the pointer's shimmer: opt_screen rotates colours 8-13 of palette
    # line 1 a place every 8 frames ($0214A0, pal_cycle_cram $02208A) and
    # the pointer's pens are 8-11: its six looks, one every 8 frames
    for i, v2 in enumerate(series("options-pointer", sega_touch.OPTIONS, 8, 6)):
        img, x, y = sprites_img(v2, lambda q: q["tile"] == 0x7BC)
        art.save(f"options_pointer_{i}.png", img, x, y, "sprite",
                 f"the row pointer, colour-cycle frame {i} of 6")
    rows = sorted({q["y"] for q in v.sprites() if q["pal"] == 2})
    art.note("labels (baked into options_screen.png) at x 32: MUSIC IS "
             "y 40, SOUNDS ARE 56, RADAR IS 72, MUSIC TEST 88, SOUND "
             "TEST 104, ENTER PASSWORD 136; in a battle also RESTART "
             "MISSION and PICK ANOTHER HOUSE below, each behind ARE YOU "
             "SURE? (opt_confirm $021A58)",
             f"values: sprites in line 2 at x 176, y {rows} - the words "
             "(ON/OFF, the tune and effect names of $087F3C/$087FD4) are "
             "drawn in the menu font (font_menu.png) into tiles $400 on",
             "pad: up/down move the pointer (x 16); left/right step a "
             "value; A/C on a test plays it; C on ENTER PASSWORD opens "
             "the password screen; Start leaves")


def do_password(art):
    v = snap("password")
    art.screen("password", "Enter your password (screen 10)", "password",
               v, "rows 200-223 (below PRESS START TO EXIT at y 192)")
    W = layer(v, "W")
    art.save("password_screen.png", W, 0, 0, "window",
             "the picture with the keyboard and its box", trim=False)
    img, x, y = sprites_img(v, lambda q: q["tile"] == 0x7BC)
    art.save("password_key_cursor.png", img, x, y, "sprites",
             "the frame round the key under the cursor")
    img, x, y = sprites_img(v, lambda q: q["pal"] == 3
                            and 0x400 <= q["tile"] < 0x480)
    art.save("password_entry_example.png", img, x, y, "sprites",
             "the typed word (empty: the underline cursor)")
    art.note("keyboard: three rows ABCDEFGHIJ / KLMNOPQRST / UVWXYZ<>! "
             "and END, keys 16 px apart from (88,56), rows 8 apart "
             "(the frame sprite sits at x 84 + 16 col, y 52 + 8 row); "
             "< and > move in the word, ! rubs out",
             "the word: ten letters, sprites at (120,112) on, drawn in "
             "the menu font; refused: song $1A or $4C, accepted: song $43 "
             "or $44 (pw_screen $0215BC); the 29 words are "
             "res/data/passwords.txt")


def with_window(v, words):
    """A copy of a capture with its window name table replaced."""
    import copy
    c = copy.copy(v)
    c.vram = v.vram.copy()
    c.vram[v.win:v.win + len(words)] = np.frombuffer(bytes(words),
                                                     np.uint8)
    return c


def do_end_screens(art):
    for scene, key, ptrs, title in (
            ("victory", "victory", 0x0C5DAA,
             "Victory (screen 11): the surrender"),
            ("defeat", "defeat", 0x0C4FF2,
             "Defeat (screen 9): the burning wreck")):
        v = snap(scene)
        art.screen(key, title, scene, v, "rows 200-223, below the banner "
                   "(y 176-199)")
        frames = []
        for k in range(4):
            data, _ = sega_gfx.lcw(ROM[l32(ptrs + 4 * k):], expect=0xE00)
            frames.append(layer(with_window(v, data[:0xE00]), "W"))
        art.save(f"{key}_screen.png", frames[0], 0, 0, "window",
                 "animation frame 0, the whole picture", trim=False)
        for k in range(1, 4):
            d = (frames[k] != frames[0]).any(-1)
            ys, xs = np.nonzero(d)
            if not len(ys):
                continue
            x0, x1 = xs.min() // 8 * 8, (xs.max() // 8 + 1) * 8
            y0, y1 = ys.min() // 8 * 8, (ys.max() // 8 + 1) * 8
            art.save(f"{key}_frame_{k}.png", frames[k][y0:y1, x0:x1],
                     x0, y0, "window", f"frame {k}: the cells that differ "
                     "from frame 0", trim=False)
        img, x, y = sprites_img(v, lambda q: q["pal"] == 3)
        art.save(f"{key}_banner.png", img, x, y, "sprites",
                 f"the {key.title()} word, line 3 (it slides up to "
                 "y 176)")
        art.note(f"the four frames are name tables at ${ptrs:06X} "
                 "(Format80, $700 words each), stepped every eleven "
                 "frames (screen_anim_*_frame); A, B, C or Start leaves; "
                 "then the mentat's victory or defeat text and the score")
    # the score page
    v = snap("score")
    art.screen("score", "The score page (score_screen $0271DE)", "score",
               v, "rows 200-223: picture only")
    art.save("score_screen.png", layer(v, "B"), 0, 0, "plane B",
             "the picture behind", trim=False)
    A = layer(v, "A", drop=lambda t: not 0x2F5 <= t < 0x310)
    art.save("score_labels.png", A, 0, 0, "plane A", "the fixed words "
             "(line 3), their own glyph tiles")
    art.text(v, "A", 0x500, "score", lo=0x20)
    art.note("the figures are printed in font_score.png (tile $500 + "
             "character): score, 5 digits at (104,24); time h:mm at "
             "(248,24); the rank, 17 characters centred at (96,56), line "
             "2; the six bars at x 80 on rows 13/14, 18/19, 23/24 (y 104, "
             "112, 144, 152, 184, 192) in glyphs $18 on, 'you' line 0, "
             "'enemy' line 1, counted up; the numbers right-aligned to "
             "x 295",
             "after a win short of mission 9 the next password follows "
             "with the house name and the mission number")
    # the ending
    v = snap("ending")
    art.screen("ending", "The end: Arrakis among the stars, the credits "
               "(screen 8, campaign_ending $012730)", "ending", v,
               "any 24: the credits scroll through")
    stars, star_tiles, full, m = starfield(v)
    B = layer(v, "B", drop=star_tiles)
    art.save("ending_planet.png", B, 0, 0, "plane B",
             "Arrakis in the house's colour ramp (here Atreides)")
    art.note("the planet's colours come from a 20-byte ramp per house at "
             "$06C70C, faded in; the stars are the title's glyphs")
    for k in range(3):
        ramp = rom_words(0x06C70C + 20 * k, 10)
        art.note(f"  ramp {k}: " + " ".join(hexcol(w) for w in ramp))
    art.note(
             "the credits: plane A scrolls up a pixel every three frames; "
             "each line centred, font title (tile $480 + character); "
             "$FF n sets the palette line (2 headings, 3 names).  The "
             "text ($01192C):")
    a, line, blank = 0x01192C, [], 0
    while ROM[a]:
        if ROM[a] == 0xFF:
            line.append(f"[{ROM[a + 1]}]")
            a += 2
            continue
        if ROM[a] == 10:
            if line:
                if blank > 1:
                    art.note(f"  ({blank - 1} blank rows)")
                art.note("  " + "".join(line))
                blank = 0
            blank += 1
            line = []
        else:
            line.append(chr(ROM[a]))
        a += 1
    if line:
        art.note("  " + "".join(line))


# ----------------------------------------------------------------- fonts

def glyph_sheet(pens, lut):
    """128 glyphs, 16 to a row: glyph n at (n % 16 * 8, n // 16 * 8)."""
    img = np.zeros((64, 128, 4), np.uint8)
    for n in range(128):
        img[n // 16 * 8:n // 16 * 8 + 8, n % 16 * 8:n % 16 * 8 + 8] = \
            lut[pens[n]]
    return img


def do_fonts(art):
    art.screen("fonts", "The fonts", "-", None, None)
    t, _ = sega_gfx.lcw(ROM[0x0506C2:0x0506C2 + 0x4000])
    m = snap("mentat-A")
    art.save("font8.png", glyph_sheet(tiles_pens(t[:0x1000]), m.lut[2]),
             None, None, "ROM $0506C2", "font title/mentat: 128 glyphs, "
             "in the mentat's line 2", trim=False)
    b = snap("build-item")
    art.save("font_menu.png",
             glyph_sheet(tiles_pens(ROM[0x04F6C0:0x04F6C0 + 0x1000]),
                         b.lut[1]), None, None, "ROM $04F6C0",
             "font menu: 128 glyphs, in the build panel's line 1",
             trim=False)
    sc = snap("score")
    art.save("font_score.png",
             glyph_sheet(sc.tiles[0x500:0x580], sc.lut[2]), None, None,
             "VRAM $A000", "font score: 128 glyphs, as the score page has "
             "them, in its line 2", trim=False)
    art.note(
        "every sheet is 16 x 8 glyphs of 8x8: glyph n is at x = n % 16 * 8,"
        " y = n // 16 * 8, and glyph n prints character n (ASCII); "
        "lower case draws the same small capitals as upper case; pen 0 is "
        "transparent, and the glyphs carry their own shadow pens, so a "
        "line is recoloured by pen, not by one colour",
        "font8.png (font 'title'/'mentat'): Format80 at $0506C2, 128 "
        "tiles.  The title menu and PRESENT (tile $480 + c, line 3), the "
        "mentat's text box (tile $460 + c, line 2), the end credits "
        "(tile $480 + c, lines 2 and 3).  Glyphs $00-$1F are the "
        "text box's frame and bar pieces",
        "font_menu.png (font 'menu'): raw at $04F6C0 (the screen table's "
        "font block $04F6BE: a length word, $1000, then the tiles), VRAM "
        "$8000 = tile $400 + c.  The build and Starport info box (line 1),"
        " the options' values and the password (drawn into sprite tiles).  "
        "$00-$1F are placeholders the panels overwrite",
        "font_score.png (font 'score'): tile $500 + c on the score page: "
        "the score, time, rank and figures (line 2), the bars (glyphs "
        "$18 on, lines 0 and 1)",
        "battle_credits_digits.png: the credits counter's own 0-9 "
        "($050ACC is the blank, then 0-9, raw)",
        "words that are pictures, not fonts: the options labels, the "
        "score page's fixed words (score_labels.png), the house plates, "
        "'Select your House', the Victory/Defeat banners, the title's "
        "DUNE and subtitle, PROCEED/ADVICE/YES/NO")

# ------------------------------------------------------------- ui.txt

def hexcol(w):
    r, g, b = md_colour(w)
    return f"{r:02X}{g:02X}{b:02X}"


def write_txt(art):
    L = []
    say = L.append
    say("# ui.txt - the Mega Drive Dune II's screens, as the port rebuilds "
        "them.")
    say("#")
    say("# Written by tools/sega/port_ui.py (its docstring says how each "
        "capture is reached).")
    say("# Pictures are src/res/art/ui/*.png: RGBA in the Mega Drive's own "
        "colours (v*255//7),")
    say("# alpha 0 where the VDP draws nothing.  Positions are screen "
        "pixels on the Mega Drive's")
    say("# 320x224; 'least' names the 24 lines the port's 320x200 can best "
        "do without.")
    say("# Palette lines are the 4 x 16 colours in CRAM at the capture, as "
        "RRGGBB; pen 0 is")
    say("# transparent (the backdrop).  Text is printed with a font "
        "(== fonts at the end):")
    say("# 'x y line \"text\"' - the palette line is the line the glyphs "
        "are drawn in.")
    say("")
    total = 0
    for sc in art.screens:
        say(f"== {sc['key']} - {sc['title']}")
        say(f"   capture {sc['capture']}   size {sc['size']}")
        if sc["least"]:
            say(f"   least   {sc['least']}")
        if sc["palette"]:
            say("   palette")
            for i, line in enumerate(sc["palette"]):
                say(f"     {i}: " + " ".join(hexcol(w) for w in line))
        if sc["pics"]:
            say("   pictures (file, x, y, w x h, layer, note)")
            for f, x, y, w, h, where, note in sc["pics"]:
                pos = f"{x:4d} {y:4d}" if x is not None else "   -    -"
                say(f"     {f:34s} {pos}  {w:3d} x {h:<3d} {where:9s} "
                    f"{note}".rstrip())
        if sc["text"]:
            say("   text (x, y, line, font, layer)")
            for x, y, s, line, fn, which in sc["text"]:
                say(f"     {x:4d} {y:4d}  {line}  {fn:7s} {which:2s} "
                    f"\"{s}\"")
        if sc["notes"]:
            say("   notes")
            for n in sc["notes"]:
                say(f"     {n}")
        say("")
    area = sum(w * h for _, w, h, *_ in art.pics)
    say(f"== totals: {len(art.pics)} pictures, {area} pixels "
        f"(sum of w x h)")
    TXT.write_text("\n".join(L) + "\n")
    print(f"wrote {TXT}: {len(art.pics)} pictures, {area} pixels")


def contact_sheet(art):
    """tmp/port-ui/sheet.png: every picture on a grey chequer."""
    ims = [(f, Image.open(OUT / f)) for f, *_ in art.pics]
    W = 1280
    x = y = rowh = 0
    pos = []
    for f, im in ims:
        w, h = im.size
        if x + w > W:
            x, y, rowh = 0, y + rowh + 12, 0
        pos.append((x, y))
        x += w + 4
        rowh = max(rowh, h)
    H = y + rowh + 4
    sheet = Image.new("RGBA", (W, H), (96, 96, 96, 255))
    ch = Image.new("RGBA", (W, H))
    px = np.zeros((H, W, 4), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    px[..., :3] = np.where((((yy // 8) + (xx // 8)) % 2 == 0)[..., None],
                           110, 80)
    px[..., 3] = 255
    sheet = Image.fromarray(px, "RGBA")
    for (f, im), p in zip(ims, pos):
        sheet.alpha_composite(im.convert("RGBA"), p)
    sheet.save(WORK / "sheet.png")
    print(f"wrote {WORK / 'sheet.png'} ({W}x{H})")

# ------------------------------------------------------------- the survey

def layers_picture(v, path):
    a, _ = v.screen_plane(0)
    b, _ = v.screen_plane(1)
    w, _ = v.screen_window()
    sp = v.screen_sprites()
    c = v.composite()
    W, H = v.sw, v.sh
    S = Image.new("RGBA", (W * 3, H * 2), (80, 0, 80, 255))
    for i, arr in enumerate([c, b, a, w if w is not None
                             else np.zeros_like(a), sp]):
        im = Image.fromarray(arr, "RGBA")
        bg = Image.new("RGBA", im.size, (80, 0, 80, 255))
        bg.alpha_composite(im)
        S.paste(bg, ((i % 3) * W, (i // 3) * H))
    S.save(path)


def survey(args):
    for name in SCENES:
        v = snap(name)
        layers_picture(v, DUMPS / name / "layers.png")
        print(f"  {name:12s} A=${v.plane_a:04X} B=${v.plane_b:04X} "
              f"W=${v.win:04X} win={v.window_area()} "
              f"sprites={len(v.sprites())}")


def parts(args):
    """Print each layer's groups of cells and its text, for choosing cuts."""
    for name in args.names:
        v = snap(name)
        for which in "ABWS":
            fonts = [(FONT_MENU, "menu"), (FONT_TITLE, "title"),
                     (FONT_MENTAT, "mentat")]
            if which != "S":
                for base, fn in fonts:
                    for t in text_cells(v, which, base):
                        print(f"  {name} {which} text[{fn}] col {t[0]:2d} "
                              f"row {t[1]:2d} line {t[3]} {t[2]!r}")
            img = layer(v, which)
            for b in components(img):
                print(f"  {name} {which} part {b}")


STEPS = [do_title, do_house, do_mentat, do_brief, do_battle, do_panels,
         do_options, do_password, do_end_screens, do_fonts]


def build_all(args):
    art = Art()
    for fn in STEPS:
        fn(art)
    write_txt(art)
    contact_sheet(art)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="all",
                    choices=["all", "survey", "parts"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    if args.fresh and DUMPS.exists():
        shutil.rmtree(DUMPS)
    DUMPS.mkdir(parents=True, exist_ok=True)
    if args.cmd == "survey":
        survey(args)
    elif args.cmd == "parts":
        parts(args)
    else:
        build_all(args)


if __name__ == "__main__":
    main()
