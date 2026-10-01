#!/usr/bin/env python3
"""port_tutorial.py - the front end's moving parts the stills leave out:
the Tutorial and the campaign map's zoom, as port resources.

    port_tutorial.py [all]      everything below
    port_tutorial.py zoom       src/res/art/ui/zoom.txt only
    port_tutorial.py tutorial   src/res/art/ui/tutorial/ only

tools/sega/port_ui.py takes the front end's screens apart as still
pictures; this does the two things that are not stills.  Like it, it reads
the cartridge and the running game (bin/gen/retro-run) and writes text
and PNG under src/res/, which tools/dune_front.py (and dune_tutorial.py)
turn into data pages at build time - the build never reads orig/.

## zoom.txt - the campaign map's zoom ($0256AA)

After the other territories have fallen off the map, campaign_attack
($026108) zooms into the one attacked next: campaign_zoom renders the
territory from a byte-a-pixel buffer ($FF7380) at a growing scale
(campaign_zoom_render $024AEE, a 16.16 step both ways) and moves the
plane's scroll by (dx, dy) every step.  The table at $024B8A has a record
of 21 steps for each territory; 17 are rendered.  The buffer's (0, 0) is
the territory's first land piece ($0962D4), which is also the top-left of
its pieces, so that point is where the zoom is anchored on the screen.

## tutorial/ - the Tutorial ($030674)

See the docstring of `tutorial()` below.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROMF = ROOT / "orig/dune2.gen"
ROM = ROMF.read_bytes()
UI = ROOT / "src/res/art/ui"

ZOOM_TABLE = 0x024B8A           # 10 records of $FC: 21 x (dx, dy, scale, w, h)
LAND_LISTS = 0x0962D4           # the ten territories' land piece lists
ZOOM_STEPS = 17                 # campaign_zoom renders steps 0-16


def w16(a):
    return int.from_bytes(ROM[a:a + 2], "big")


def s16(a):
    v = w16(a)
    return v - 0x10000 if v & 0x8000 else v


def l32(a):
    return int.from_bytes(ROM[a:a + 4], "big")


# ------------------------------------------------------------------- zoom

def zoom():
    L = ["# zoom.txt - the campaign map's zoom into the territory attacked",
         "# next (campaign_attack $026108, campaign_zoom $0256AA).  Written by",
         "# tools/sega/port_tutorial.py; read by tools/dune_front.py.",
         "#",
         "# origin: the territory's first land piece ($0962D4 list, first",
         "#   long) in Mega Drive screen pixels - the zoom buffer's (0, 0)",
         "#   and so the point the zoom grows from",
         "# step n: dx dy scale w h - the table at $024B8A: the scroll moves",
         "#   by (-dx, +dy) before step n is shown; scale is the 16.16",
         "#   sampling step of campaign_zoom_render ($024AEE); w x h the",
         "#   tiles it renders.  campaign_zoom shows render n-1 with the",
         "#   scroll of step n, every 5 frames (measured: 4179, 4184, ...),",
         "#   and campaign_zoom_vblank darkens the palette a step every 5",
         "#   frames from 40 frames after it is installed (black 70 frames",
         "#   after), so steps 1-13 are seen and the rest render in the dark.",
         ""]
    for t in range(10):
        a = l32(LAND_LISTS + 4 * t)
        x, y = s16(a), s16(a + 2)
        L.append(f"territory {t} origin {x} {y}")
        base = ZOOM_TABLE + t * 0xFC
        for n in range(ZOOM_STEPS):
            p = base + 12 * n
            dx, dy, sc, w, h = s16(p), s16(p + 2), l32(p + 4), w16(p + 8), \
                w16(p + 10)
            L.append(f"  step {n:2}: {dx:3} {dy:3} ${sc:08X} {w:2} {h:2}")
    L += ["",
          "# campaign_border_N.png: territory N's own border pieces ($096150,",
          "# tiles $09631C), drawn in palette line 0 like campaign_land_N.png.",
          "# campaign_draw_pieces_chunky draws them into the zoom's buffer",
          "# after the land, and a lifted territory's sprite carries them",
          "# (campaign_lift_territory $0244C8): x y of each picture."]
    L += borders()
    out = UI / "zoom.txt"
    out.write_text("\n".join(L) + "\n")
    print(f"wrote {out}")


def borders():
    """campaign_border_N.png, as port_ui.py draws campaign_land_N.png (the
    pieces at their own screen positions, offset (0, 0)), in the land's
    colours: pen p of line 0 of the campaign palette (ui.txt)."""
    import numpy as np
    from PIL import Image
    import port_ui
    from port_ui_vdp import crop_alpha
    line0 = None
    sect = False
    for raw in (ROOT / "src/res/art/ui.txt").read_text().splitlines():
        if raw.startswith("== campaign "):
            sect = True
        elif sect and raw.strip().startswith("0:"):
            line0 = [tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
                     for h in raw.split(":")[1].split()]
            break
    lut = np.zeros((16, 4), np.uint8)
    for p in range(1, 16):
        lut[p, :3] = line0[p]
        lut[p, 3] = 255
    out = []
    for n, pcs in enumerate(port_ui.territory_lists(0x096150, 0x09D114)):
        img = port_ui.draw_pieces(pcs, 0x09631C, lut)
        c, dx, dy = crop_alpha(img)
        Image.fromarray(np.ascontiguousarray(c), "RGBA").save(
            UI / f"campaign_border_{n}.png")
        out.append(f"border {n} at {dx} {dy}")
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", nargs="?", default="all",
                    choices=("all", "zoom", "tutorial"))
    args = ap.parse_args()
    if args.what in ("all", "zoom"):
        zoom()
    if args.what in ("all", "tutorial"):
        tutorial()


PAD_FRAMES = 0x013216           # six (0.l, frame list.l): the pad's shapes
PAD_TILES = 0x013872            # their asset list, loaded to VRAM $5960
PAD_BASE_TILE = 0x5960 // 32
BOX_FRAME = 0x042B48            # the text box's sprite list
BOX_GLYPHS = 0x042CFA           # its 4bpp glyphs, raw, 32 bytes each
BOX_MAP = 0x042AC8              # character -> glyph
BOX_TILE = 0x670                # its tiles from VRAM $CE00: corner (glyph
                                # 9 over 11), edge (glyph 10), then text


def sprite_list(a):
    """(w, h, dy, size, attr, dx) records: a count-1 word, then 12 bytes
    each - the frames spr_create ($001000) builds sprites from."""
    n = w16(a) + 1
    return [tuple(w16(a + 2 + 12 * i + 2 * k) for k in range(6))
            for i in range(n)]


def pens_of(tile_bytes):
    """32 bytes of a 4bpp tile -> 8 x 8 pens."""
    out = []
    for r in range(8):
        row = []
        for b in tile_bytes[r * 4:r * 4 + 4]:
            row += [b >> 4, b & 15]
        out.append(row)
    return out


def draw_list(recs, tile_of, w, h):
    """A sprite list drawn as pens, (0, 0) at the list's origin: the
    VDP's tile order (down each column first), flips, and the first
    sprite on top - pen 0 is transparent."""
    img = [[0] * w for _ in range(h)]
    for sw, sh, dy, size, attr, dx in reversed(recs):
        tw, th = ((size >> 10) & 3) + 1, ((size >> 8) & 3) + 1
        t0, hf, vf = attr & 0x7FF, (attr >> 11) & 1, (attr >> 12) & 1
        for cx in range(tw):
            for cy in range(th):
                p = pens_of(tile_of(t0 + cx * th + cy))
                ox = (tw - 1 - cx if hf else cx) * 8
                oy = (th - 1 - cy if vf else cy) * 8
                for y in range(8):
                    for x in range(8):
                        v = p[7 - y if vf else y][7 - x if hf else x]
                        X, Y = dx + ox + x, dy + oy + y
                        if v and 0 <= X < w and 0 <= Y < h:
                            img[Y][X] = v
    return img


def save_pens(img, path):
    """A pen picture as greys: pen p is p * 17."""
    from PIL import Image
    h, w = len(img), len(img[0])
    im = Image.new("L", (w, h))
    im.putdata([v * 17 for row in img for v in row])
    im.save(path)


def tutorial():
    """## tutorial/ and tutorial.txt - the Tutorial

    ui_tutorial ($030674) plays scripts 0, 1, 3, 5, 6 and 7 of the picture
    interpreter tut_run_script ($0418D4); sega_pictures.py has taken all
    of it apart and checked it, and this writes it out for the port:

      tiles_N.png   the tiles picture N loads (asset list), 16 a row, as
                    pens (grey = pen * 17); the name tables say the line
      pad_S.png     the pad the "cursor" opcodes show, shape S (0-5,
                    frames $013216, tiles $013872), pens of line 0; its
                    top-left is the cursor's position
      textbox.png   the text box's frame ($042B48, glyphs 9-11 of
                    $042CFA) with its two blank lines (pen 15,
                    textbox_blank), pens of line 1; font.png its 34 glyphs
      tutorial.txt  the palettes, each picture's plane animations (the
                    frames of sega_pictures.frames(), as text), the
                    scripts, the glyph map
    """
    import sega_pictures as sp
    from sega_gfx import lcw
    out = UI / "tutorial"
    out.mkdir(parents=True, exist_ok=True)
    info, scr, palette_users, pads, spans = sp.everything(ROM)
    L = ["# tutorial.txt - the Tutorial (ui_tutorial $030674), for",
         "# tools/dune_tutorial.py.  Written by tools/sega/port_tutorial.py",
         "# from the cartridge through tools/sega/sega_pictures.py, which",
         "# says what everything here is and checks it.",
         "#",
         "# palette $ADDR: 64 colours, four lines of 16, RRGGBB",
         "# picture N tiles M: its plane animations draw with the tiles of",
         "#   picture M (tiles_M.png); 'A k:'/'B k:' is frame k of plane A",
         "#   (in front) or B, cell by cell over a 40 x 28 name table:",
         "#   +n leaves n cells, n*WORD writes WORD n times, W,W,... writes",
         "#   those words; a word is the VDP's (priority, line, flips, tile)",
         "# tiles N count K: tiles_N.png holds K tiles (the rest is padding)",
         "# script N: the opcodes of pictures.txt, one a line",
         "# glyphs: the text box's glyph for each character code 32-95",
         ""]
    for p in sorted(palette_users):
        cols = [sp.cram_rgb(w16(p + 2 * i)) for i in range(64)]
        L.append(f"palette ${p:06X}")
        for ln in range(4):
            L.append("  " + " ".join("%02X%02X%02X" % c
                                     for c in cols[ln * 16:ln * 16 + 16]))
    L.append("")
    # the tile sets
    for r, d in sorted(info.items()):
        if not d.get("list"):
            continue
        tiles = d["tiles"]
        n = len(tiles) // 32
        across = 16
        img = [[0] * (across * 8) for _ in range(((n + across - 1) // across) * 8)]
        for t in range(n):
            p = pens_of(tiles[t * 32:t * 32 + 32])
            for y in range(8):
                for x in range(8):
                    img[(t // across) * 8 + y][(t % across) * 8 + x] = p[y][x]
        save_pens(img, out / f"tiles_{r}.png")
        L.append(f"tiles {r} count {n}")
    # the plane animations
    for r, d in sorted(info.items()):
        if not d["planes"]:
            continue
        L.append(f"picture {r} tiles {d['tiles_from']}")
        for name in ("A", "B"):
            if name not in d["planes"]:
                continue
            for k, ops in enumerate(d["planes"][name][3]):
                toks = []
                for kind, v in ops:
                    if kind == "skip":
                        toks.append(f"+{v}")
                    elif len(v) > 1 and len(set(v)) == 1 and \
                            _was_run(d, name, k, len(toks)):
                        toks.append(f"{len(v)}*{v[0]:04X}")
                    else:
                        toks.append(",".join(f"{x:04X}" for x in v))
                L.append(f"  {name} {k}: " + " ".join(toks))
    L.append("")
    # the scripts
    for n, (a, e, body) in sorted(scr.items()):
        L.append(f"script {n}")
        for at, op, args in body:
            L.append("  " + sp.fmt(op, args))
    L.append("")
    # the pad
    pad_tiles = bytearray()
    for cnt, ptr, packed in sp.asset_list(ROM, PAD_TILES)[0]:
        got, _ = lcw(ROM[ptr:ptr + 0x10000], expect=cnt * 32) \
            if packed else (ROM[ptr:ptr + cnt * 32], cnt * 32)
        pad_tiles += got[:cnt * 32]

    def pad_tile(t):
        k = t - PAD_BASE_TILE
        return pad_tiles[k * 32:k * 32 + 32]
    for s in range(6):
        recs = sprite_list(l32(PAD_FRAMES + 8 * s + 4))
        save_pens(draw_list(recs, pad_tile, 208, 96), out / f"pad_{s}.png")
    # the text box: its frame and blank lines, and the glyphs

    def glyph(g):
        return ROM[BOX_GLYPHS + 32 * g:BOX_GLYPHS + 32 * g + 32]

    def box_tile(t):
        if t == BOX_TILE:
            return glyph(9)
        if t == BOX_TILE + 1:
            return glyph(11)
        if BOX_TILE + 2 <= t < BOX_TILE + 6:
            return glyph(10)
        return bytes([0xFF] * 32)               # textbox_blank
    save_pens(draw_list(sprite_list(BOX_FRAME), box_tile, 272, 32),
              out / "textbox.png")
    img = [[0] * 128 for _ in range(24)]
    for g in range(34):
        p = pens_of(glyph(g))
        for y in range(8):
            for x in range(8):
                img[(g // 16) * 8 + y][(g % 16) * 8 + x] = p[y][x]
    save_pens(img, out / "font.png")
    L.append("glyphs " + " ".join(str(ROM[BOX_MAP + c]) for c in range(32, 96)))
    L.append("")
    (UI / "tutorial.txt").write_text("\n".join(L) + "\n")
    print(f"wrote {UI / 'tutorial.txt'} and {out}/")


_RUNS = {}


def _was_run(d, name, k, pos):
    """Whether the frame's op at `pos` was a run ($01-$7F) rather than a
    literal of equal words ($81-$FF): sega_pictures.frames() turns both
    into ('put', words), so the block is read again here."""
    import sega_pictures as sp
    key = (id(d), name, k)
    if key not in _RUNS:
        start = d["planes"][name][0]
        data, _ = sp.unpack(ROM, start)
        o = 0
        for _ in range(k):
            o += 2 + int.from_bytes(data[o:o + 2], "big")
        n = int.from_bytes(data[o:o + 2], "big")
        p, end, kinds = o + 2, o + 2 + n, []
        while p < end:
            c = data[p]
            if c == 0x80:
                kinds.append("skip")
                p += 2
            elif c > 0x80:
                kinds.append("lit")
                p += 1 + 2 * (c & 0x7F)
            else:
                kinds.append("run")
                p += 3
        _RUNS[key] = kinds
    return _RUNS[key][pos] == "run"


if __name__ == "__main__":
    main()
