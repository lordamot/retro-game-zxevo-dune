#!/usr/bin/env python3
"""dune_tutorial.py - the Tutorial (src/res/art/ui/tutorial.txt and
tutorial/) -> data pages TUT_PAGES (221-223, 0, 4, 6) and tutorial.inc
for bank TUTOR
(src/front/tutorial.asm).

Called by tools/dune_front.py (so the build runs it with the front end's
pictures); `dune_tutorial.py --out DIR` runs it alone.

The Mega Drive plays its tutorial as two planes of 8x8 tiles, each
animated by a stream of name-table frames, with the pad and a text box
as sprites over them (tools/sega/sega_pictures.py, port_tutorial.py).
The port does the same on the Z80 - pictures made of the cartridge's own
tiles would not fit as screens (80 KB of full screens and 356 KB of
changes, measured) - so this keeps the tiles as the cartridge's 4-bit
pens and the frames as the cartridge's name-table words, and chooses per
picture group the 16 EGA colours the pens are shown in.

## What it writes (every asset in one data page, found through tut_dir)

  TILES   a picture's tiles, packed (dune_front.lz_pack): 32 bytes a tile,
          the Mega Drive's 4bpp (a byte is two pixels, the left one in the
          high nibble); tiles 512 on are a second asset
  PLANE   a plane's frames, packed.  A frame is ops to the end ($00):
          $80 n leaves n cells, $81-$FF (n | $80) then n words writes
          them, $01-$7F n then one word writes it n times; words are the
          VDP's, low byte first; a frame of just $00 is the end of them
  MAP     per group and Mega Drive palette: for each of the 64 colours
          the bits a left pixel of it sets in a plane byte on an even
          line, then on an odd line (128 bytes), then the same for a right
          pixel (128) - the dither of dune_front.Palette, so the Z80 can
          build its pen-pair tables (TUTOR's conv) in a moment
  FADE    per group: 4 palettes from dark to the group's 16 colours
  PAD     the pad (pad_0.png), its lines 0-57 (the port shows no more of
          it), 104 bytes a line; PADn: shape n's rectangle that differs
          from shape 0 (line, lines, byte, bytes, then the pens)
  BOX     the text box (textbox.png), 136 bytes a line, 32 lines; FONT
          its 34 glyphs as 4bpp tiles; the glyph map in tutorial.inc
  SCRIPT  the six scripts as TUTOR's bytecode (TO_ below)

## The palette groups

A picture draws with its own tiles or with the last picture's (7 with
6's, 10 with 9's), and a group is one tile set with every picture and
Mega Drive palette that shows it.  Its 16 colours are voted for by every
screen the scripts show with it (rendered by sega_pictures), the pad and
the text box.  The palette opcode ($2C) changes only the Mega Drive's
palette, never the port's 16: the pictures already drawn keep their
pixels, and the ones drawn next use the new colours - which is all the
one palette change there is (the build menu's line 3, $041F4E) needs.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools/sega"))
from dune_front import Palette, histogram, lz_pack, lz_unpack       # noqa: E402
from dune_art import BAYER, palette_byte                           # noqa: E402

UI = ROOT / "src/res/art/ui"
TUT = UI / "tutorial"
# src/pages.inc PG_TUT_DATA.  The SPG format allows pages #00-#DF only:
# every loader (the firmware's, Wild Commander's) keeps itself in #E0-#FF,
# so the Tutorial sits in the free pages below that - the unused end of the
# sound reserve and the three pages no screen uses (screens are 1/5, 3/7).
TUT_PAGES = [221, 222, 223, 0, 4, 6]
PAGE = 0x4000
OFF = 8                         # the port shows the Mega Drive's lines 8-207
PAD_LINES = 58                  # the pad at y 150 shows lines 0-57 of itself
TU_BOX_AT = 0x1880              # tutorial.asm TU_BOXWORK - $4000 in page 127
SCRIPTS = (0, 1, 3, 5, 6, 7)    # ui_tutorial $030674
BLACK = (0, 0, 0)

# the bytecode (src/front/tutorial.asm tu_ops)
OPS = ["end", "wait", "picture", "frame", "mark", "until", "fadeout",
       "fadein", "repeat", "loop", "skip", "sound", "rewindA", "cursor",
       "cursorxy", "slideup", "slidedown", "palette", "text", "textoff",
       "clearB"]


def hexrgb(h):
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


# ------------------------------------------------------------ reading

def read_txt():
    pal, pics, scripts, glyphs, counts = {}, {}, {}, None, {}
    cur = None
    for raw in (UI / "tutorial.txt").read_text().splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        m = re.match(r"palette \$([0-9A-F]+)", raw)
        if m:
            cur = pal.setdefault(int(m.group(1), 16), [])
            continue
        m = re.match(r"picture (\d+) tiles (\d+)", raw)
        if m:
            cur = pics.setdefault(int(m.group(1)), dict(
                tiles=int(m.group(2)), A=[], B=[]))
            continue
        m = re.match(r"script (\d+)", raw)
        if m:
            cur = scripts.setdefault(int(m.group(1)), [])
            continue
        m = re.match(r"tiles (\d+) count (\d+)", raw)
        if m:
            counts[int(m.group(1))] = int(m.group(2))
            continue
        if raw.startswith("glyphs "):
            glyphs = [int(v) for v in raw.split()[1:]]
            continue
        s = raw.strip()
        if isinstance(cur, list) and cur is not None and re.match(r"[0-9A-F]{6} ", s):
            cur += [hexrgb(h) for h in s.split()]
            continue
        m = re.match(r"([AB]) (\d+): (.*)", s)
        if m:
            cur[m.group(1)].append(parse_frame(m.group(3)))
            continue
        cur.append(parse_op(s))
    return pal, pics, scripts, glyphs, counts


def parse_frame(txt):
    """-> [('skip', n) | ('lit', [words]) | ('run', n, word)]"""
    ops = []
    for t in txt.split():
        if t.startswith("+"):
            ops.append(("skip", int(t[1:])))
        elif "*" in t:
            n, w = t.split("*")
            ops.append(("run", int(n), int(w, 16)))
        else:
            ops.append(("lit", [int(w, 16) for w in t.split(",")]))
    return ops


def parse_op(s):
    m = re.match(r'(\w+)\s*(.*)', s)
    name, rest = m.group(1), m.group(2)
    if name == "text":
        return (name, [rest.strip()[1:-1].replace("|", "\n")])
    args = [int(a.strip().lstrip("$"), 16 if a.strip().startswith("$") else 10)
            for a in rest.split(",") if a.strip()]
    return (name, args)


def load_pens(name):
    return np.asarray(Image.open(TUT / name)) // 17


def tiles_bytes(pens):
    """A tile sheet (16 across) -> the 4bpp bytes, tile after tile."""
    h, w = pens.shape
    out = bytearray()
    for ty in range(h // 8):
        for tx in range(w // 8):
            cell = pens[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
            for r in range(8):
                for k in range(4):
                    out.append(int(cell[r, 2 * k]) << 4 | int(cell[r, 2 * k + 1]))
    return bytes(out)


# ----------------------------------------------------------- the model

def play(pics, scripts):
    """The scripts run as tut_run_script does, to learn which picture is
    shown with which palette and what the player sees: {script: [(pic,
    A cells, B cells, palette)]} at every wait, and {pic: palettes}."""
    shown, used = {}, {}
    for n in SCRIPTS:
        body = scripts[n]
        va = [0] * 1120
        vb = [0] * 1120
        bufs = {"A": [0] * 1120, "B": [0] * 1120}
        pos = {"A": 0, "B": 0}
        cur, pal = None, None
        out, i, mark, d6, last, steps = [], 0, 0, 0, 0, 0
        while True:
            steps += 1
            assert steps < 100000
            op, args = body[i]
            nxt = i + 1
            if op == "end":
                break
            if op == "picture":
                cur = args[0]
                pos = {"A": 0, "B": 0}
            elif op in ("frame", "skip"):
                plane = "AB"[args[0]]
                for _ in range(args[1] if op == "skip" else 1):
                    fr = pics[cur][plane]
                    if pos[plane] >= len(fr):
                        last = 0xFFFF
                        continue
                    apply(bufs[plane], fr[pos[plane]])
                    pos[plane] += 1
                    last = 0
                if op == "frame":
                    va, vb = list(bufs["A"]), list(bufs["B"])
            elif op == "mark":
                mark = nxt
            elif op == "until":
                assert args[0] == 0xFFFF
                if last != args[0]:
                    nxt = mark
            elif op == "repeat":
                d6, mark = args[0], nxt
            elif op == "loop":
                d6 -= 1
                if d6:
                    nxt = mark
            elif op == "rewindA":
                pos["A"] = 0
            elif op == "clearB":
                bufs["B"] = [0] * 1120
                vb = [0] * 1120
            elif op in ("fadein", "palette"):
                pal = args[0]
                used.setdefault(cur, set()).add(pal)
            if op == "wait" and pal is not None:
                out.append((cur, tuple(va), tuple(vb), pal))
            i = nxt
        shown[n] = out
    return shown, used


def apply(buf, ops):
    p = 0
    for op in ops:
        if op[0] == "skip":
            p += op[1]
        elif op[0] == "run":
            for _ in range(op[1]):
                buf[p] = op[2]
                p += 1
        else:
            for w in op[1]:
                buf[p] = w
                p += 1
    assert p == 1120


def render(va, vb, tiles, pal):
    """One screen as the VDP makes it (sega_pictures.render), RGB."""
    img = np.zeros((224, 320, 3), np.uint8)
    img[:, :] = pal[0]
    for buf, pri in ((vb, 0), (va, 0), (vb, 1), (va, 1)):
        for row in range(28):
            for col in range(40):
                w = buf[row * 40 + col]
                if (w >> 15) != pri:
                    continue
                t = (w & 0x7FF) * 32
                line = (w >> 13) & 3
                vf, hf = (w >> 12) & 1, (w >> 11) & 1
                for y in range(8):
                    sy = 7 - y if vf else y
                    for x in range(8):
                        sx = 7 - x if hf else x
                        c = (tiles[t + sy * 4 + sx // 2] >> (0 if sx & 1 else 4)) & 15
                        if c:
                            img[row * 8 + y, col * 8 + x] = pal[line * 16 + c]
    return img


def pens_rgb(pens, pal, line):
    img = np.zeros(pens.shape + (4,), np.uint8)
    for p in range(1, 16):
        img[pens == p, :3] = pal[line * 16 + p]
        img[pens == p, 3] = 255
    return Image.fromarray(img, "RGBA")


# ------------------------------------------------------------ encoding

def encode_frames(frames):
    """A plane's frames -> the PLANE bytes."""
    out = bytearray()
    for ops in frames:
        for op in ops:
            if op[0] == "skip":
                n = op[1]
                while n:
                    k = min(n, 255)
                    out += bytes([0x80, k])
                    n -= k
            elif op[0] == "run":
                n = op[1]
                while n:
                    k = min(n, 127)
                    out += bytes([k, op[2] & 0xFF, op[2] >> 8])
                    n -= k
            else:
                ws = op[1]
                for s in range(0, len(ws), 127):
                    part = ws[s:s + 127]
                    out.append(0x80 | len(part))
                    for w in part:
                        out += bytes([w & 0xFF, w >> 8])
        out.append(0)
    out.append(0)
    return bytes(out)


def pack(data):
    s = lz_pack([data], [0])
    back, used = lz_unpack(s, [len(data)], [0])
    assert back[0] == data and used == len(s)
    return s


def map_bytes(pal16, md):
    """MAP: per Mega Drive colour the plane bits of a left and a right
    pixel of it, on an even and an odd line."""
    left, right = bytearray(128), bytearray(128)
    for c in range(64):
        rgb = md[0] if c % 16 == 0 else md[c]       # pen 0: the backdrop
        a, b, q = pal16._best(rgb)
        for py in (0, 1):
            li = b if BAYER[py][0] < q else a
            ri = b if BAYER[py][1] < q else a
            left[c * 2 + py] = (li & 7) | ((li & 8) << 3)
            right[c * 2 + py] = ((ri & 7) << 3) | ((ri & 8) << 4)
    return bytes(left + right)


def sfx_ids(out):
    """Game song -> the port's SFX_ id ($FF: not in the sound set)."""
    names = {}
    for raw in (ROOT / "src/res/sega_sound.txt").read_text().splitlines():
        t = raw.split()
        if len(t) == 4 and t[0] == "sfx" and t[2] == "game":
            names[int(t[3])] = t[1]
    ids = {}
    si = Path(out) / "sound_ids.inc"
    if si.exists():
        for line in si.read_text().splitlines():
            m = re.match(r"SFX_(\w+)\s+EQU\s+(\d+)", line)
            if m:
                ids[m.group(1).lower()] = int(m.group(2))
    return {song: ids.get(name, 0xFF) for song, name in names.items()}


# ---------------------------------------------------------------- build

class Pages:
    def __init__(self):
        self.assets = []            # (name, bytes)

    def add(self, name, data):
        assert len(data) <= PAGE, (name, len(data))
        self.assets.append((name, bytes(data)))
        return len(self.assets) - 1

    def write(self, out):
        pages, where = [], {}
        for k in sorted(range(len(self.assets)), key=lambda k: -len(self.assets[k][1])):
            name, data = self.assets[k]
            for n, pg in enumerate(pages):
                if pg[1] + len(data) <= PAGE:
                    break
            else:
                pages.append([bytearray(PAGE), 0])
                n = len(pages) - 1
            if n >= len(TUT_PAGES):
                raise SystemExit(f"dune_tutorial: more than {len(TUT_PAGES)} pages")
            pg = pages[n]
            pg[0][pg[1]:pg[1] + len(data)] = data
            where[k] = (TUT_PAGES[n], 0x4000 + pg[1])
            pg[1] += len(data)
        for n, (buf, used) in enumerate(pages):
            (out / f"page_{TUT_PAGES[n]:03d}.bin").write_bytes(bytes(buf))
        return where, len(pages), sum(p[1] for p in pages)


def check_pages(out):
    """The sound set's pages (sound_ids.inc) must end below ours: both
    write page_NNN.bin into the same directory, and the second would
    silently win."""
    si = Path(out) / "sound_ids.inc"
    if not si.exists():
        return
    t = si.read_text()
    base = int(re.search(r"SND_BASE_PAGE\s+EQU\s+(\d+)", t).group(1))
    n = int(re.search(r"SND_ZX_PAGES\s+EQU\s+(\d+)", t).group(1))
    taken = set(range(base, base + n)) & set(TUT_PAGES)
    if taken:
        raise SystemExit(f"dune_tutorial: the sound set's pages reach {base + n - 1}, "
                         f"into the Tutorial's ({sorted(taken)})")


def build(out):
    out = Path(out)
    check_pages(out)
    md_pal, pics, scripts, glyphs, counts = read_txt()
    tile_sets = sorted({p["tiles"] for p in pics.values()})
    tiles = {t: tiles_bytes(load_pens(f"tiles_{t}.png"))[:counts[t] * 32]
             for t in tile_sets}
    shown, used = play(pics, scripts)
    group_of = {p: tile_sets.index(d["tiles"]) for p, d in pics.items()}
    pad = [load_pens(f"pad_{s}.png") for s in range(6)]
    box = load_pens("textbox.png")
    font = load_pens("font.png")
    P = Pages()
    lines = ["; tutorial.inc - written by tools/dune_tutorial.py; do not edit.",
             "; (included 256-aligned: the two tables first)",
             "tu_mask:\t; [pen pair]: the plane bits a pen 0 leaves as they were"]
    mask = [(0x47 if v >> 4 == 0 else 0) | (0xB8 if v & 15 == 0 else 0) for v in range(256)]
    swap = [((v & 15) << 4) | (v >> 4) for v in range(256)]
    lines += ["        DB " + ", ".join(f"${v:02X}" for v in mask[k:k + 16]) for k in range(0, 256, 16)]
    lines.append("tu_swap:\t; [byte]: its two pixels the other way round")
    lines += ["        DB " + ", ".join(f"${v:02X}" for v in swap[k:k + 16]) for k in range(0, 256, 16)]

    # ---- the palettes: a group's 16 colours, its fade, its maps
    maps = {}                           # (group, md palette) -> MAP asset
    fades = []
    pad_groups = set()
    for n in SCRIPTS:
        cur = None
        for op, args in scripts[n]:
            if op == "picture":
                cur = args[0]
            elif op == "cursor" and cur is not None:
                pad_groups.add(group_of[cur])
    for g, t in enumerate(tile_sets):
        items = []
        mds = set()
        for n in SCRIPTS:
            for pic, va, vb, pal in shown[n]:
                if group_of[pic] != g:
                    continue
                mds.add(pal)
                img = render(va, vb, tiles[t], md_pal[pal])[OFF:OFF + 200]
                items.append((Image.fromarray(img).convert("RGBA"), 1))
        for p, pals in used.items():
            if group_of[p] == g:
                mds |= pals
        if g in pad_groups:
            for pal in sorted(mds):
                items.append((pens_rgb(pad[0][:PAD_LINES], md_pal[pal], 0), 6))
                items.append((pens_rgb(box, md_pal[pal], 1), 6))
                items.append((pens_rgb(font, md_pal[pal], 1), 30))
        pal16 = Palette(histogram(items), fixed=(BLACK,))
        steps = [pal16.faded(k, 4) for k in range(1, 5)]
        fades.append(P.add(f"fade_{g}", b"".join(steps)))
        for pal in sorted(mds):
            maps[(g, pal)] = P.add(f"map_{g}_{pal:06X}", map_bytes(pal16, md_pal[pal]))

    # ---- the tiles and the planes
    tile_assets = {}
    for t in tile_sets:
        data = tiles[t]
        a0 = P.add(f"tiles_{t}_0", pack(data[:512 * 32]))
        a1 = P.add(f"tiles_{t}_1", pack(data[512 * 32:])) if len(data) > 512 * 32 else 0xFF
        tile_assets[t] = (a0, a1, len(data) // 32)
    plane_assets = {}
    need = {}
    for p, d in sorted(pics.items()):
        for name in ("A", "B"):
            if d[name]:
                raw = encode_frames(d[name])
                need[p] = need.get(p, 0) + len(raw)
                plane_assets[(p, name)] = (P.add(f"plane_{p}_{name}", pack(raw)), len(raw))
            else:
                plane_assets[(p, name)] = (0xFF, 0)
    # TUTOR's work page: two name tables, a dirty byte a cell, the frames
    assert 2 * 2240 + 1120 + max(need.values()) <= PAGE, need
    # page 127 above tiles 512 on: the text box's pens and the font
    assert max(len(v) for v in tiles.values()) - 512 * 32 <= TU_BOX_AT, "tiles"
    # the picture table: its tiles (FF: the last picture's), A, B, group
    lines.append("tu_pictures:\t; per picture 0-11: tiles lo, hi ($FF none), "
                 "count; A, its bytes; B, its bytes; group")
    loaded = set()
    for p in range(12):
        if p not in pics:
            lines.append("        DB $FF, $FF\n        DW 0\n        DB $FF\n        DW 0\n"
                         "        DB $FF\n        DW 0\n        DB 0")
            continue
        t = pics[p]["tiles"]
        own = t == p
        a0, a1, cnt = tile_assets[t] if own else (0xFF, 0xFF, 0)
        pa, na = plane_assets[(p, "A")]
        pb, nb = plane_assets[(p, "B")]
        lines.append(f"        DB {a0}, {a1}\n        DW {cnt}\n        DB {pa}\n        DW {na}\n"
                     f"        DB {pb}\n        DW {nb}\n        DB {group_of[p]}")
        loaded.add(p)
    lines.append("TU_PIC_SIZE     EQU 11")
    lines.append("tu_fades:\t; per group: its FADE asset")
    lines.append("        DB " + ", ".join(str(a) for a in fades))
    # the blank tile of each set (fully pen 0): the front plane skips it
    lines.append("tu_blank:\t; per picture: the tile that is all pen 0 ($FFFF none)")
    for p in range(12):
        b = 0xFFFF
        if p in pics:
            data = tiles[pics[p]["tiles"]]
            for k in range(len(data) // 32):
                if not any(data[k * 32:k * 32 + 32]):
                    b = k
                    break
        lines.append(f"        DW ${b:04X}")

    # ---- the pad, the text box, the font
    base = pad[0][:PAD_LINES]
    padb = bytes(int(base[y, 2 * k]) << 4 | int(base[y, 2 * k + 1])
                 for y in range(PAD_LINES) for k in range(104))
    pad_asset = P.add("pad", pack(padb))
    shape = [0xFF]
    for s in range(1, 6):
        img = pad[s][:PAD_LINES]
        d = np.nonzero(img != base)
        y0, y1 = int(d[0].min()), int(d[0].max()) + 1
        b0, b1 = int(d[1].min()) // 2, int(d[1].max()) // 2 + 1
        body = bytes(int(img[y, 2 * k]) << 4 | int(img[y, 2 * k + 1])
                     for y in range(y0, y1) for k in range(b0, b1))
        shape.append(P.add(f"pad_{s}", bytes([y0, y1 - y0, b0, b1 - b0]) + pack(body)))
    lines.append("tu_shapes:\t; per pad shape 1-5: its PADn asset (0: the base)")
    lines.append("        DB " + ", ".join(str(v) for v in shape))
    boxb = bytes(int(box[y, 2 * k]) << 4 | int(box[y, 2 * k + 1])
                 for y in range(32) for k in range(136))
    box_asset = P.add("box", pack(boxb))
    fontb = bytearray()
    for g in range(34):
        cell = font[(g // 16) * 8:(g // 16) * 8 + 8, (g % 16) * 8:(g % 16) * 8 + 8]
        for r in range(8):
            for k in range(4):
                fontb.append(int(cell[r, 2 * k]) << 4 | int(cell[r, 2 * k + 1]))
    font_asset = P.add("font", bytes(fontb))
    lines.append("tu_glyphs:\t; character 32-95 -> the text box's glyph")
    lines.append("        DB " + ", ".join(str(v) for v in glyphs))

    # ---- the scripts
    sfx = sfx_ids(out)
    code = bytearray()
    starts = []
    cur = None
    cur_map = cur_pal = None
    for n in SCRIPTS:
        starts.append(len(code))
        cur_group = None
        body = scripts[n]
        for i, (op, args) in enumerate(body):
            code.append(OPS.index(op))
            if op == "wait":
                code += bytes([args[0] & 0xFF, args[0] >> 8])
            elif op == "picture":
                # and the map its frames draw with: the Mega Drive's VDP
                # colours them when shown, the port when drawn - so the
                # palette the script fades in next (before another
                # picture), or the one in use
                cur = args[0]
                cur_group = group_of[cur]
                for op2, a2 in body[i + 1:]:
                    if op2 == "picture":
                        break
                    if op2 in ("fadein", "palette"):
                        cur_map = maps[(cur_group, a2[0])]
                        break
                assert cur_map is not None
                code += bytes([cur, cur_map])
            elif op in ("frame", "repeat"):
                assert args[0] < 256
                code.append(args[0])
            elif op == "until":
                assert args[0] == 0xFFFF       # until the plane's frames end
            elif op == "fadein":
                code.append(maps[(cur_group, args[0])])
                cur_pal = args[0]
            elif op == "palette":
                # and the lines whose colours it changes: on the Mega
                # Drive every cell drawn in them changes at once
                code.append(maps[(cur_group, args[0])])
                lines_changed = 0
                for ln in range(4):
                    if md_pal[cur_pal][ln * 16:ln * 16 + 16] != md_pal[args[0]][ln * 16:ln * 16 + 16]:
                        lines_changed |= 1 << ln
                code.append(lines_changed)
                cur_pal = args[0]
            elif op == "skip":
                code += bytes(args)
            elif op == "sound":
                code.append(sfx.get(args[0], 0xFF))
            elif op == "cursor":
                y, x, s = args
                assert x % 2 == 0 and 0 <= y - OFF < 256
                code += bytes([y - OFF, x, s])
            elif op == "cursorxy":
                y, x = args
                code += bytes([y - OFF, x])
            elif op == "text":
                code += args[0].encode("ascii") + b"\0"
            else:
                assert not args, (op, args)
    script_asset = P.add("script", bytes(code))
    lines.append("tu_scripts:\t; the six scripts' offsets in TA_SCRIPT")
    lines.append("        DW " + ", ".join(str(v) for v in starts))
    lines.append(f"TU_SCRIPTS      EQU {len(SCRIPTS)}")

    where, npages, used_bytes = P.write(out)
    names = [n for n, _ in P.assets]
    for k, n in enumerate(names):
        lines.append(f"TA_{n.upper():20} EQU {k}")
    lines.append(f"TA_PAD_BASE     EQU {pad_asset}")
    lines.append(f"TA_BOX_PENS     EQU {box_asset}")
    lines.append(f"TA_FONT_PENS    EQU {font_asset}")
    lines.append(f"TA_SCRIPTS      EQU {script_asset}")
    lines.append(f"TUT_DATA_PAGES  EQU {npages}")
    lines.append("tut_dir:\t; page, address (window 1) per TA_ number")
    for k, (n, data) in enumerate(P.assets):
        pg, ad = where[k]
        lines.append(f"        DB {pg}\n        DW ${ad:04X}\t; {n}, {len(data)}")
    (out / "tutorial.inc").write_text("\n".join(lines) + "\n")
    print(f"dune_tutorial: {len(P.assets)} assets in {npages} pages from "
          f"{TUT_PAGES[0]} ({used_bytes} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build/gen"))
    args = ap.parse_args()
    build(Path(args.out))


if __name__ == "__main__":
    main()
