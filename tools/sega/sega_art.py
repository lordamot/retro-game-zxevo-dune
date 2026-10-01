#!/usr/bin/env python3
"""sega_art.py - the Mega Drive Dune II's pictures, and where they are not.

    sega_art.py [--rom orig/dune2.gen] [--out orig/sega/res/art]

Writes what can honestly be written: the tiles the cartridge keeps
uncompressed, the palettes the game actually loads, and an index saying
which is which.  It also says plainly what it has *not* got, because on
this ROM that is most of it.

## What is in there, and what is not

A Mega Drive tile is 8x8 pixels, four bits a pixel, 32 bytes - a nibble per
pixel, left to right, top to bottom, and the nibble is an index into one of
the four sixteen-colour palettes the VDP holds at once.  A colour is a
nine-bit word, `0000 BBB0 GGG0 RRR0`: three bits a channel, and the zero
bits are why a CRAM word is so easy to recognise.

Only a small part of this cartridge's art is stored that way; the rest is
compressed.  **That compression is now undone** - it is Westwood's
Format80 and `tools/sega/sega_gfx.py` unpacks it - so
this tool is the lesser half of the picture and is kept for the tiles that
really are stored plainly and for the palette survey.  Start with
`res/art/sprites.txt`.

So this tool writes three things:

  * `tiles/*.png` - the runs the ROM does hold as plain 4bpp tiles, as
    16-colour indexed sheets, which read back exactly;
  * `palettes.txt` - every 16-colour CRAM-shaped table, with the colours
    written out as both the Mega Drive's nine bits and 24-bit RGB;
  * `art.txt` - the index, including the ranges that are compressed and
    what is known about them.

The pictures the *port* uses come from the NES demo instead
(`.claude/docs/nes-art.md`); nothing here feeds the build.  This is the
other original, kept so the two can be compared.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

TILE = 32                # 8x8 pixels, one nibble each


def cram_rgb(w):
    """A Mega Drive colour word to 8-bit RGB."""
    r = ((w >> 1) & 7) * 255 // 7
    g = ((w >> 5) & 7) * 255 // 7
    b = ((w >> 9) & 7) * 255 // 7
    return r, g, b


def is_cram(w):
    return (w & 0xF111) == 0


def find_palettes(rom, want=16):
    """Runs of exactly CRAM-shaped words, at even addresses, long enough to
    be a palette the VDP could load in one go."""
    out, i, n = [], 0, len(rom)
    while i + 2 <= n:
        j, count = i, 0
        while j + 2 <= n and is_cram(int.from_bytes(rom[j:j + 2], "big")):
            j += 2
            count += 1
        if count >= want:
            out.append((i, count))
            i = j
        else:
            i += 2 if count == 0 else j - i
    return out


def tile_score(block):
    """How much a 32-byte block looks like a drawn tile rather than noise.

    A tile drawn by hand uses few of the sixteen pens and repeats them
    along a row; a longword of code or a pointer does neither.
    """
    nibbles = []
    for b in block:
        nibbles += [b >> 4, b & 15]
    used = len(set(nibbles))
    runs = sum(1 for i in range(1, 64) if nibbles[i] == nibbles[i - 1])
    return used, runs


def find_tile_runs(rom, least=32):
    """Stretches that look like a sheet of 4bpp tiles.

    Looking like a tile is not enough: a run of one pattern repeated is
    filler, and a compressed block often has stretches that pass the
    per-tile test by luck.  A sheet of art is a run whose tiles are mostly
    different from each other, so that is what is asked for.
    """
    out = []
    n = len(rom) // TILE
    run_start = None

    def keep(a, b):
        tiles = [rom[i * TILE:(i + 1) * TILE] for i in range(a, b)]
        if len(set(tiles)) * 2 < len(tiles):
            return
        out.append((a * TILE, b - a))

    for t in range(n):
        blk = rom[t * TILE:(t + 1) * TILE]
        used, runs = tile_score(blk)
        if 2 <= used <= 10 and runs >= 24 and len(set(blk)) > 1:
            if run_start is None:
                run_start = t
        else:
            if run_start is not None and t - run_start >= least:
                keep(run_start, t)
            run_start = None
    if run_start is not None and n - run_start >= least:
        keep(run_start, n)
    return out


def sheet(rom, offset, count, palette=None):
    """`count` tiles from `offset` as one 16-colour indexed image."""
    from PIL import Image
    cols = 16
    rows = (count + cols - 1) // cols
    img = Image.new("P", (cols * 8, rows * 8))
    pal = []
    for i in range(16):
        if palette and i < len(palette):
            pal += list(cram_rgb(palette[i]))
        else:
            v = i * 17
            pal += [v, v, v]
    img.putpalette(pal + [0] * (256 * 3 - len(pal)))
    px = img.load()
    for t in range(count):
        blk = rom[offset + t * TILE:offset + (t + 1) * TILE]
        ox, oy = (t % cols) * 8, (t // cols) * 8
        for y in range(8):
            for x in range(8):
                b = blk[y * 4 + x // 2]
                px[ox + x, oy + y] = (b >> 4) if x % 2 == 0 else (b & 15)
    return img


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/art"))
    ap.add_argument("--max-sheets", type=int, default=24)
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    (out / "tiles").mkdir(parents=True, exist_ok=True)

    pals = find_palettes(rom)
    runs = sorted(find_tile_runs(rom), key=lambda r: -r[1])[:args.max_sheets]
    runs.sort()

    written = []
    for offset, count in runs:
        n = min(count, 256)
        name = f"tiles_{offset:06X}.png"
        sheet(rom, offset, n).save(out / "tiles" / name)
        written.append((offset, count, n, name))

    plines = ["# palettes.txt - every CRAM-shaped colour table in the ROM.",
              "#",
              "# A Mega Drive colour is one word, 0000 BBB0 GGG0 RRR0 - three",
              "# bits a channel out of a possible eight, and the zero bits",
              "# are what makes a palette findable at all.  Sixteen of them",
              "# is one of the four the VDP holds.",
              "#",
              "# Not every run below is a palette the game loads: a table of",
              "# small even numbers has the same shape.  The ones the game",
              "# really used are in tmp/md/cram.bin after `make md`, and they",
              "# are not in the ROM verbatim - like the tiles, they are",
              "# compressed.",
              ""]
    for o, count in pals:
        if count < 16:
            continue
        plines.append(f"${o:06X}  {count} colours")
        for k in range(0, min(count, 64), 16):
            row = []
            for i in range(k, min(k + 16, count)):
                w = int.from_bytes(rom[o + i * 2:o + i * 2 + 2], "big")
                r, g, b = cram_rgb(w)
                row.append(f"{w:04X}={r:02X}{g:02X}{b:02X}")
            plines.append("    " + " ".join(row))
    (out / "palettes.txt").write_text("\n".join(plines) + "\n")

    alines = ["# art.txt - the cartridge's pictures.",
              "#",
              "# Written by tools/sega/sega_art.py.  A tile is 8x8 pixels at",
              "# four bits each, 32 bytes, and the sheets below are the runs",
              "# of the ROM that are stored that way.  They are drawn in grey",
              "# because which palette goes with which sheet is in the code,",
              "# not beside the pixels.",
              "#",
              "# MOST OF THIS GAME'S ART IS NOT HERE - it is compressed, and",
              "# tools/sega/sega_gfx.py undoes that: Westwood Format80, with",
              "# the decompressor at $000C32.  See res/art/sprites.txt for",
              "# every building and unit in its own colours and 6791 more",
              "# tiles besides.  These sheets are only what the ROM stores",
              "# plainly.",
              "#",
              "# offset    tiles  drawn  sheet",
              ""]
    for offset, count, n, name in written:
        alines.append(f"${offset:06X}  {count:5d}  {n:5d}  tiles/{name}")
    alines += ["",
               f"# {len([p for p in pals if p[1] >= 16])} palette-shaped runs "
               "-> palettes.txt"]
    (out / "art.txt").write_text("\n".join(alines) + "\n")

    print(f"{len(written)} tile sheets -> {out}/tiles/")
    print(f"{len([p for p in pals if p[1] >= 16])} palette-shaped runs "
          f"-> {out}/palettes.txt")


if __name__ == "__main__":
    main()
