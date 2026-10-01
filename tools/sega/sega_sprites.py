#!/usr/bin/env python3
"""sega_sprites.py - the sprite animations of the Mega Drive Dune II.

    sega_sprites.py [--rom orig/dune2.gen] [--out orig/sega/res/art]
                    [--vram FILE]

Everything that moves on the battlefield - the units, the explosions, the
cursors, the build icons - is a hardware sprite drawn from a *list*, and
the animation table at $060E84 is what pairs a list with its pixels.

## A list

The sprite engine walks its chain at $001088; for each sprite it takes the
list at sprite+8 ($00118C) and draws every piece of it ($001192-$001288):

    +0   word   piece count - 1
    +2   12 bytes a piece:
         +0  width   } a box used only for clipping ($0011A4-$0011C4)
         +2  height  }
         +4  y offset
         +6  the VDP size word: bits 11-8 are the size (3-2 cells across
             - 1, 1-0 cells down - 1), the low byte (the link) is zero
         +8  the attribute word: tile in bits 10-0, flips 11-12, palette
             13-14, priority 15
         +10 x offset

The tile number is **absolute**.  $001248 keeps bits 15 and 12-0 of the
piece and only exclusive-ors in the sprite's own flips and priority
($00124C-$001258); a piece with palette bits of its own keeps them,
otherwise the sprite's palette - the house's - shows through
($00125E-$001272).  So a list says exactly which VRAM tiles it needs,
and the check below is that those tiles are there.

## A record of the animation table

357 records of two longwords, pixels then list, read by six routines:
$004B34 (the two cursor sprites), $00950C and $009594 (every unit,
structure and effect), $0098DC and $009942 (the portrait of what is
selected).  The top byte of each longword is a tag:

  the pixels' tag: only its **sign** is ever tested.  Negative ($80):
    $00950C/$009594 DMA the pixels at the moment the sprite is made, to
    the tile of the list's first piece, as many 32-byte cells as that
    piece has - the length comes from the table at $0094EC indexed by
    the piece's size byte ($009534-$009540).  Zero or positive ($00,
    $7F): nothing is sent; the art is already in VRAM, put there once a
    mission by $00A41E from the preload list at $00A488.  $00 and $7F
    are never told apart by any code.  (The $7F records' pointers always
    land where the frame's first tile would be in the block the preload
    list sends; the $00 ones sometimes do and sometimes point nowhere
    useful - both unused.)  A whole record of zero is an empty slot
    ($009520).

  the list's tag: the **drawing layer**.  $00954E copies it to +4 of
    the sprite's owner, and $0012F6 makes the sort key of the sprite
    chain from exactly that byte and the owner's y ($0012FE-$001304),
    which $0013F4 keeps the chain in order by.  The front-end sprites
    whose owners are constants in ROM carry $FF there, and $004E76
    writes $FC.  Two values mean more: $0B turns the house palette off
    ($009556, $0095E2), and a negative one ($FA-$FF) leaves bit 1 of the
    sprite's flags clear ($00956A), which exempts it from the crowded-
    band thinning at $0011E8.  $0098DC/$009942 accept only $FE (palette
    1) and $FF (palette 3).  A 68000 has a 24-bit bus, so where the whole
    longword goes into sprite+8 ($004B82, $0095B6) the tag is simply
    ignored by the fetch.

## Where the pixels go, and how much

  $00A41E, the preload list at $00A488: records of (VRAM address.w,
    words.w, pointer.l), ended by a zero; a pointer with bit 31 set is
    raw and DMA'd as it stands, one without is Format80 and goes
    through $000C32 first.  36 blocks, and every compressed one comes
    out to exactly the length the list gives.
  $004B34 sets $FFBF04/$FFBF08; the vertical interrupt at $0067BC/
    $00685C sends $80 words from each to VRAM $F780 (tile $7BC) and
    $F880 (tile $7C4).  Given a negative animation number $004BF2 uses
    the 16 lists at $064FE2 and the two 256-byte halves at $06473E.
  $00950C/$009594: the tag-$80 records above.
  $0098DC/$009942 send $C0 words (12 tiles, a 32 x 24 portrait) to
    $F280 and $F4C0; $0082D0 and $00902E send the same size from the
    two portrait tables at $06E838 and $070C9C.  $0082D0 indexes them
    with a signed byte, so five pointers before each base are reached.
  $00AFF6 cycles three frames of three 9-tile objects from $00AF76;
    $00B052 three 6-tile frames from $00B01C; $005124 plays the frame
    scripts at $068BCA and $068C16 (a byte of delay and a 24-bit pointer
    a longword, ended by zero), $100 words each to $D000.

A block's extent is what its reader sends, cut to what its lists draw
where the reader over-sends: the cursor DMA always moves 256 bytes, and
from $064D3E it runs 128 bytes into the lists that follow.

## The checks

  every Format80 block decompresses to exactly its preload length;
  every piece of every list has a zero link byte and a zero top nibble
    in its size word;
  every tile every record's list draws is in VRAM by one of the routes
    above - the preloaded ranges, the record's own DMA, the cursor
    slots or the portrait slot;
  no two regions overlap, except lists that share a tail (a list that
    begins at another's piece +10, whose x offset of zero reads as a
    count of one), which are one region;
  with --vram, the preloaded ranges of a battle's VRAM equal the
    decompressed blocks.

What does not fit is printed, not hidden: seven records whose list
pointer lands inside a list and reads a count of 33 or $FFF4 (none of the
seven was read in any recorded play), and animation 7, whose list draws
VRAM tile 0.  Three stretches have a shape and no reader - two lists
at $0652DE and $065312 and a tile at $066B44 - and are named as such.
The lists at $02EC72-$030673 that some records use belong to the 256-frame
table there and are left to it.

Writes `animations.txt` and a PNG per drawable record under
`animations/`, in the colours of a mission-1 battle's CRAM.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_gfx import lcw, Truncated                           # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent

TABLE, COUNT = 0x060E84, 357          # read at $004B7A, $004BB2, $009510,
                                      # $0095A8, $0098F4, $00995A
PRELOAD = 0x00A488                    # read by $00A41E
SLOT_TILES = {0x7BC: 0xF780, 0x7C4: 0xF880}   # $FFBF04, $FFBF08
PORTRAIT_TILE = 0x794                 # $F280, where $0098DC sends a face
PORTRAIT_BYTES = 0x180                # $C0 words
CELLS = [((s >> 2) + 1) * ((s & 3) + 1) for s in range(16)]

# List-pointer tables: (address, count, the code that indexes them)
LIST_TABLES = [
    (0x064FE2, 16, "$004C16 (a negative animation number)"),
    (0x0641E6, 24, "$00969E (8 directions x 3)"),
    (0x0659F6, 7, "$009B46"),
    (0x009AB6, 8, "$009A7C"),
]
# Lists and owner records named straight from code.
CODE_LISTS = {
    0x064DE6: "$004AF4", 0x065676: "$021BAC, $022370",
    0x0658E0: "$009AEA", 0x065CA6: "$009C06", 0x06A790: "$009C36",
    0x06A7A4: "$009C5E", 0x06A7B8: "$009C9E", 0x06A7CC: "$009CC6",
    0x06A7E6: "$009BD0, $009BE6", 0x06A82C: "$004E80",
    0x06A83A: "$004ED4, $005172", 0x068C66: "$004E46, $004F56",
}
# An owner is what sprite+0 points at: y.w, x.w, the layer byte, a pad.
OWNERS = {
    0x065B40: "$009C72", 0x065CCC: "$009BFA", 0x06A79E: "$009C2A",
    0x06A7B2: "$009C52", 0x06A7C6: "$009C92", 0x06A7DA: "$009CBA, $009856",
    0x06A7E0: "$0096AC, $0096BC", 0x06A800: "$009BDE", 0x06A806: "$009BC8",
}
PORTRAIT_TABLES = [(0x06E838, 5, 20), (0x070C9C, 5, 33)]   # base, before, after
FRAME_SETS = (0x00AF76, 3, 3, 0x00AFBE)   # 3 frames of 3 objects, then 3 ptrs
DF20_FRAMES = (0x00B01C, 3)               # $00B052: $60 words to $DF20
FRAME_SCRIPTS = [0x068BCA, 0x068C16]      # $005124: $100 words to $D000

# The CRAM of a mission-1 battle (tmp/sega/touch/pool/seed-m1-0.state,
# two frames on), as the core keeps it: nine bits, BBBGGGRRR.
BATTLE_CRAM = [
    0x000, 0x0EE, 0x0A5, 0x05C, 0x013, 0x04A, 0x01E, 0x00D,
    0x092, 0x1FF, 0x164, 0x089, 0x000, 0x02F, 0x005, 0x001,
    0x000, 0x12D, 0x052, 0x009, 0x177, 0x014, 0x00A, 0x037,
    0x01D, 0x1FF, 0x164, 0x089, 0x000, 0x1F8, 0x190, 0x040,
    0x000, 0x03F, 0x02F, 0x016, 0x004, 0x002, 0x028, 0x190,
    0x11B, 0x1FF, 0x164, 0x089, 0x000, 0x184, 0x102, 0x041,
    0x000, 0x005, 0x002, 0x09B, 0x009, 0x137, 0x0A6, 0x053,
    0x150, 0x1FF, 0x164, 0x089, 0x000, 0x03E, 0x028, 0x008,
]


def w16(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def l32(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


def pieces(rom, a):
    """[(tile, cells, attr, size, x, y)] of the list at `a`, or None when
    it is not one: too many pieces, or a size word with a link byte or a
    top nibble."""
    if a + 2 > len(rom):
        return None
    n = w16(rom, a) + 1
    if n > 64:
        return None
    out = []
    for k in range(n):
        b = a + 2 + 12 * k
        sw, at = w16(rom, b + 6), w16(rom, b + 8)
        if sw & 0xF0FF:
            return None
        s = sw >> 8
        y, x = w16(rom, b + 4), w16(rom, b + 10)
        out.append((at & 0x7FF, CELLS[s], at, s,
                    x - 0x10000 if x & 0x8000 else x,
                    y - 0x10000 if y & 0x8000 else y))
    return out


def list_end(rom, a):
    return a + 2 + 12 * (w16(rom, a) + 1)


def preload(rom):
    """[(entry, vram, nbytes, ptr, raw, end)] from $00A488."""
    out, a = [], PRELOAD
    while l32(rom, a):
        d3, p = l32(rom, a), l32(rom, a + 4)
        vram, nbytes, ptr, raw = d3 >> 16, (d3 & 0xFFFF) * 2, p & 0xFFFFFF, p >> 31
        if raw:
            end, ok = ptr + nbytes, True
        else:
            try:
                data, used = lcw(rom[ptr:ptr + 0x10000])
            except (Truncated, IndexError):
                data, used = b"", 0
            end, ok = ptr + used, len(data) == nbytes
        out.append((a, vram, nbytes, ptr, raw, end, ok))
        a += 8
    return out, a + 4


def records(rom):
    out = []
    for i in range(COUNT):
        p, q = l32(rom, TABLE + 8 * i), l32(rom, TABLE + 8 * i + 4)
        out.append((i, p >> 24, p & 0xFFFFFF, q >> 24, q & 0xFFFFFF))
    return out


def analyse(rom):
    """Everything: blocks, lists, tables, what each record is, problems."""
    blocks, lists, tables, problems = {}, {}, [], []
    kinds = {}

    def block(a, n, what, reader):
        if a in blocks and blocks[a][0] != n:
            problems.append(f"${a:06X}: {what} wants {n} bytes, "
                            f"{blocks[a][1]} wants {blocks[a][0]}")
            n = max(n, blocks[a][0])
        old = blocks.get(a, (n, what, set()))
        blocks[a] = (n, old[1], old[2] | {reader})

    def lst(a, reader):
        if pieces(rom, a) is None:
            problems.append(f"${a:06X} named by {reader} is not a list")
            return
        lists.setdefault(a, set()).add(reader)

    # the preload list
    pre, pre_end = preload(rom)
    loaded = {}
    for (e, vram, n, ptr, raw, end, ok) in pre:
        t0 = vram // 32
        for t in range(t0, t0 + n // 32):
            loaded[t] = ptr
        if not ok:
            problems.append(f"${ptr:06X} does not decompress to {n} bytes")
        if raw:
            block(ptr, n, f"{n // 32} tiles of sprite pixels, uncompressed, "
                  f"DMA'd to VRAM ${vram:04X} (tile ${t0:03X}) by $00A41E "
                  "from the preload list at $00A488", "$00A44A")
        else:
            blocks[ptr] = (end - ptr, f"{n // 32} tiles of sprite pixels, "
                           f"Format80 ({n} bytes unpacked), decompressed "
                           f"by $00A41E and DMA'd to VRAM ${vram:04X} "
                           f"(tile ${t0:03X}); from the preload list at "
                           "$00A488", {"$00A440"})
    tables.append((PRELOAD, pre_end, f"the sprite preload list: {len(pre)} "
                   "records of VRAM address, word count and pointer (bit 31: "
                   "raw, else Format80), ended by a zero - read by $00A41E"))

    # the records
    recs = records(rom)
    for (i, pt, pa, lt, la) in recs:
        if pt == 0 and pa == 0:
            kinds[i] = ("empty", None)
            continue
        ps = pieces(rom, la)
        if ps is None:
            kinds[i] = ("bad list", None)
            problems.append(f"animation {i}: list ${la:06X} (tag ${lt:02X}) "
                            f"reads a count of {w16(rom, la) + 1} - it lands "
                            "inside another list")
            continue
        lst(la, "the animation table")
        need = set()
        for t, c, *_ in ps:
            need |= set(range(t, t + c))
        if pt & 0x80:
            t0, c = ps[0][0], ps[0][1]
            block(pa, c * 32, f"{c} tiles of sprite pixels, uncompressed, "
                  f"DMA'd to tile ${t0:03X} by $00950C/$009594 when the "
                  "sprite is made", "$009540")
            have = set(range(t0, t0 + c)) | set(loaded)
            kinds[i] = ("create", (pa, c * 32))
        elif need <= set(range(0x7BC, 0x7CC)):
            base = 0x7C4 if min(need) >= 0x7C4 else 0x7BC
            n = (max(need) + 1 - base) * 32
            block(pa, n, f"{n // 32} tiles of cursor-sprite pixels, "
                  f"uncompressed, DMA'd to VRAM ${SLOT_TILES[base]:04X} by "
                  "the vertical interrupt ($006804/$0068A4) after $004B34 "
                  "names it", "$004B90")
            have = need
            kinds[i] = ("cursor", (pa, n))
        elif lt in (0xFE, 0xFF) and need <= set(range(PORTRAIT_TILE,
                                                     PORTRAIT_TILE + 12)):
            block(pa, PORTRAIT_BYTES, "a 32 x 24 portrait, 12 tiles, "
                  "uncompressed - DMA'd to $F280/$F4C0 by $0098DC/$009942",
                  "$009932")
            have = need
            kinds[i] = ("portrait", (pa, PORTRAIT_BYTES))
        else:
            have = set(loaded)
            kinds[i] = ("preloaded", None)
        if not need <= have:
            miss = sorted(need - have)
            problems.append(f"animation {i}: tiles {', '.join('$%03X' % t for t in miss[:6])} "
                            "are not put in VRAM by anything this knows"
                            + (" (tile 0, blank in every VRAM dump looked at)"
                               if miss == [0] else ""))
    tables.append((TABLE, TABLE + 8 * COUNT, f"the animation table: {COUNT} "
                   "records of pixels.l and list.l; the pixels' sign says "
                   "'DMA when made', the list's top byte is the drawing layer "
                   "- read by $004B34, $00950C, $009594, $0098DC, $009942"))

    # the other list tables and code references
    for (a, n, who) in LIST_TABLES:
        for k in range(n):
            lst(l32(rom, a + 4 * k) & 0xFFFFFF, f"${a:06X}")
        if a >= 0x060000:
            tables.append((a, a + 4 * n, f"{n} pointers to sprite lists, "
                           f"indexed by {who}"))
    for a, who in CODE_LISTS.items():
        lst(a, who)
    block(0x064246, 256, "8 tiles of cursor-sprite pixels, uncompressed - "
          "recoloured and DMA'd to $F780 by $004886, and made by $00950C",
          "$004896")
    block(0x0655F6, 128, "4 tiles of cursor-sprite pixels, uncompressed, "
          "DMA'd to $F780 by $021BC6/$02238A", "$021BD4")
    block(0x06A80C, 32, "one tile of sprite pixels, uncompressed, DMA'd to "
          "the tile of the list at $06A82C by $004EAA", "$004EB0")
    # the portrait tables
    for (base, before, after) in PORTRAIT_TABLES:
        start = base - 4 * before
        for k in range(before + after):
            p = l32(rom, start + 4 * k)
            if p:
                block(p & 0xFFFFFF, PORTRAIT_BYTES, "a 32 x 24 portrait, 12 "
                      "tiles, uncompressed - DMA'd by $0082D0/$00902E/"
                      "$0098DC/$009942", "$0082E6")
        tables.append((start, base + 4 * after, f"{before + after} pointers "
                       f"to portraits; $0082D0 indexes ${base:06X} with a "
                       f"signed byte, so the {before} before it are reached"
                       + (", and $00902E indexes it unsigned"
                          if base == 0x070C9C else "")))
    # $00AF76 and $00B01C
    a, nf, no, ptrs = FRAME_SETS
    for k in range(nf * no):
        e = a + 8 * k
        p, v, n = l32(rom, e) & 0xFFFFFF, w16(rom, e + 4), w16(rom, e + 6) * 2
        block(p, n, f"{n // 32} tiles of sprite pixels, uncompressed - one "
              f"of three frames $00AFF6 cycles into VRAM ${v:04X}", "$00B000")
    tables.append((a, ptrs, f"{nf} frames x {no} objects of (pointer.l, "
                   "VRAM.w, words.w) - read by $00AFFA-$00B012"))
    tables.append((ptrs, ptrs + 4 * nf, f"{nf} pointers into the table "
                   f"above, one a frame - read by $00AFF6"))
    a, n = DF20_FRAMES
    for k in range(n):
        block(l32(rom, a + 4 * k) & 0xFFFFFF, 192, "6 tiles of sprite pixels, "
              "uncompressed - a frame $00B052 sends to $DF20", "$00B05E")
    tables.append((a, a + 4 * n, f"{n} pointers to 6-tile frames - read by "
                   "$00B052"))
    # the frame scripts
    for s in FRAME_SCRIPTS:
        a = s
        while l32(rom, a):
            block(l32(rom, a) & 0xFFFFFF, 512, "16 tiles of sprite pixels, "
                  "uncompressed - a frame the script player at $005124 "
                  "sends to $D000", "$00515A")
            a += 4
        tables.append((s, a + 4, f"a frame script: {(a - s) // 4} longwords "
                       "of delay.b and a 24-bit frame pointer, ended by zero "
                       "- played by $005124"))
    # a blank tile nobody sends
    blank = recs[7][2]
    if rom[blank:blank + 32] == bytes(32):
        blocks[blank] = (32, "32 zero bytes, a blank tile - named as the "
                         "pixels of animation 7, whose list draws tile 0; "
                         "nothing sends it (the pointer is positive)",
                         set())
    return dict(blocks=blocks, lists=lists, tables=tables, kinds=kinds,
                problems=problems, preload=pre, records=recs,
                loaded=loaded)


def _list_groups(rom, lists):
    """Lists merged where they overlap (shared tails)."""
    spans = sorted((a, list_end(rom, a)) for a in lists)
    out = []
    for a, e in spans:
        if out and a < out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
            out[-1][2].append(a)
        else:
            out.append([a, e, [a]])
    return out


AREA = (0x0619AC, 0x06A86C)      # the pixels and lists
PORTRAITS = (0x06D1A4, 0x0714A0)  # the portraits and their tables
OWN_TABLE = (0x02EC72, 0x030674)  # 256 frames, already named elsewhere
ORPHANS = [
    (0x0652DE, 26, "list"), (0x065312, 14, "list"),
    (0x066B44, 32, "tile"),
]


def sprite_regions(rom):
    """[(start, end_exclusive, description)] for sega_extract.py."""
    an = analyse(rom)
    out = []
    for a, (n, what, _) in an["blocks"].items():
        out.append((a, a + n, what))
        if "Format80" in what and (a + n) & 1 and rom[a + n] == 0:
            out.append((a + n, a + n + 1, "a zero byte to bring the "
                        "Format80 stream before it to a word boundary"))
    for a, n, kind in ORPHANS:
        if kind == "list":
            ok = pieces(rom, a) is not None and list_end(rom, a) == a + n
            d = ("has the shape of a sprite list ("
                 f"{w16(rom, a) + 1} piece(s), cursor tiles) but nothing found "
                 "names it and the trace never read it")
        else:
            ok = True
            d = ("32 bytes with the shape of one sprite tile (a larger ring "
                 "than the preloaded tile at $066B24 before it) - nothing "
                 "found names it and the trace never read it")
        if ok:
            out.append((a, a + n, d))
    for a, e, members in _list_groups(rom, an["lists"]):
        if OWN_TABLE[0] <= a < OWN_TABLE[1]:
            continue
        who = sorted(set().union(*(an["lists"][m] for m in members)))
        if len(members) == 1:
            np_ = w16(rom, a) + 1
            d = (f"a sprite list: {np_} piece{'s' if np_ > 1 else ''} of 12 "
                 f"bytes after a count word - named by {', '.join(who)}")
        else:
            d = (f"{len(members)} sprite lists sharing a tail ("
                 + ", ".join(f"${m:06X}" for m in members)
                 + f") - named by {', '.join(who)}")
        out.append((a, e, d))
    for a, who in OWNERS.items():
        out.append((a, a + 6, f"a sprite owner in ROM: y, x, layer ${rom[a + 4]:02X} "
                    f"and a pad byte - handed to $001000 by {who}"))
    for a, e, d in an["tables"]:
        out.append((a, e, d))
    out.sort()
    return out


def overlaps(regions):
    bad = []
    for (a, e, d), (b, f, g) in zip(regions, regions[1:]):
        if b < e:
            bad.append((a, e, d, b, f, g))
    return bad


# ---------------------------------------------------------------- pictures

def rgb(w):
    return ((w & 7) * 255 // 7, ((w >> 3) & 7) * 255 // 7,
            ((w >> 6) & 7) * 255 // 7)


def vram_of(rom, an):
    """A VRAM with the preloaded art in it."""
    v = bytearray(0x10000)
    for (e, vram, n, ptr, raw, end, ok) in an["preload"]:
        data = rom[ptr:ptr + n] if raw else lcw(rom[ptr:ptr + 0x10000])[0]
        v[vram:vram + n] = data[:n]
    return v


def draw(rom, v, ps, house_pal):
    """An RGBA image of a list, or None if it draws nothing."""
    from PIL import Image
    xs, ys = [], []
    for t, c, at, s, x, y in ps:
        w, h = ((s >> 2) + 1) * 8, ((s & 3) + 1) * 8
        xs += [x, x + w]
        ys += [y, y + h]
    x0, y0 = min(xs), min(ys)
    img = Image.new("RGBA", (max(xs) - x0, max(ys) - y0), (0, 0, 0, 0))
    px = img.load()
    for t, c, at, s, x, y in reversed(ps):        # the first piece on top
        cw, ch = (s >> 2) + 1, (s & 3) + 1
        hf, vf = at & 0x800, at & 0x1000
        line = (at >> 13) & 3 if at & 0x6000 else house_pal
        for cx in range(cw):
            for cy in range(ch):
                tile = (t + cx * ch + cy) & 0x7FF
                sx = (cw - 1 - cx) if hf else cx
                sy = (ch - 1 - cy) if vf else cy
                b = v[tile * 32:tile * 32 + 32]
                for yy in range(8):
                    for xx in range(8):
                        val = b[yy * 4 + xx // 2]
                        val = val >> 4 if xx % 2 == 0 else val & 15
                        if not val:
                            continue
                        dx = 7 - xx if hf else xx
                        dy = 7 - yy if vf else yy
                        px[x - x0 + sx * 8 + dx, y - y0 + sy * 8 + dy] = \
                            rgb(BATTLE_CRAM[line * 16 + val]) + (255,)
    return img


def render_all(rom, an, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.png"):
        old.unlink()
    base = vram_of(rom, an)
    n = 0
    for (i, pt, pa, lt, la) in an["records"]:
        kind = an["kinds"][i][0]
        if kind in ("empty", "bad list"):
            continue
        ps = pieces(rom, la)
        v = bytearray(base)
        if kind == "create":
            t0 = ps[0][0]
            v[t0 * 32:t0 * 32 + ps[0][1] * 32] = rom[pa:pa + ps[0][1] * 32]
        elif kind == "cursor":
            base_t = 0x7C4 if min(p[0] for p in ps) >= 0x7C4 else 0x7BC
            sz = an["kinds"][i][1][1]
            v[base_t * 32:base_t * 32 + sz] = rom[pa:pa + sz]
        elif kind == "portrait":
            v[PORTRAIT_TILE * 32:PORTRAIT_TILE * 32 + PORTRAIT_BYTES] = \
                rom[pa:pa + PORTRAIT_BYTES]
        house = {0xFE: 1, 0xFF: 3}.get(lt, 0) if kind == "portrait" else 0
        img = draw(rom, v, ps, house)
        if img is None or img.getbbox() is None:
            continue
        img.save(outdir / f"{i:03d}.png")
        n += 1
    return n


# ---------------------------------------------------------------- index

def index_text(rom, an, regions, bad, rendered):
    L = []
    say = L.append
    say("# animations.txt - the sprite animation system of the Mega Drive "
        "Dune II")
    say("#")
    say("# Written by tools/sega/sega_sprites.py; its docstring has the "
        "evidence.")
    say(f"# The animation table at ${TABLE:06X}: {COUNT} records of "
        "pixels.l, list.l.")
    say("# pixels tag: $80 = DMA'd when the sprite is made ($00950C); "
        "$00/$7F = already in VRAM.")
    say("# list tag: the drawing layer ($0012F6); $0B = no house palette; "
        "negative = never thinned.")
    say("# PNGs in animations/ use a mission-1 battle's CRAM, house "
        "palette line 0.")
    say("")
    say("== the preload list at $00A488 (read by $00A41E)")
    for (e, vram, n, ptr, raw, end, ok) in an["preload"]:
        say(f"  ${e:06X}  VRAM ${vram:04X} tile ${vram // 32:03X}  "
            f"{n // 32:3d} tiles  ${ptr:06X}-${end:06X}  "
            f"{'raw' if raw else 'Format80'}{'' if ok else '  SIZE MISMATCH'}")
    say("")
    say("== the records")
    for (i, pt, pa, lt, la) in an["records"]:
        kind, extra = an["kinds"][i]
        if kind == "empty":
            say(f"  {i:3d}  empty")
            continue
        ps = pieces(rom, la)
        tiles = (" ".join(f"${t:03X}+{c}" for t, c, *_ in ps)
                 if ps else "-")
        png = " (png)" if i in rendered else ""
        say(f"  {i:3d}  pixels ${pt:02X}:${pa:06X}  list ${lt:02X}:${la:06X}"
            f"  {kind:9s}  {tiles}{png}")
    say("")
    say("== regions")
    for a, e, d in regions:
        say(f"  ${a:06X}-${e - 1:06X} {e - a:6d}  {d}")
    say("")
    say("== what does not fit")
    for p in an["problems"]:
        say(f"  {p}")
    for (a, e, d, b, f, g) in bad:
        say(f"  overlap: ${a:06X}-${e:06X} ({d[:40]}) and ${b:06X}-${f:06X}")
    if not an["problems"] and not bad:
        say("  nothing")
    return "\n".join(L) + "\n"


def vram_check(rom, an, path):
    import numpy as np
    raw = np.fromfile(path, np.uint8).reshape(-1, 2)[:, ::-1].reshape(-1)
    v = raw.tobytes()
    # the three objects $00AFF6 animates may be on any of their frames
    alt = {}
    a = FRAME_SETS[0]
    for k in range(FRAME_SETS[1] * FRAME_SETS[2]):
        p, vr = l32(rom, a + 8 * k) & 0xFFFFFF, w16(rom, a + 8 * k + 4)
        n = w16(rom, a + 8 * k + 6) * 2
        for t in range(n // 32):
            alt.setdefault(vr + 32 * t, set()).add(rom[p + 32 * t:p + 32 * t + 32])
    good = bad = 0
    for (e, vram, n, ptr, rw, end, ok) in an["preload"]:
        data = rom[ptr:ptr + n] if rw else lcw(rom[ptr:ptr + 0x10000])[0]
        for k in range(n // 32):
            here = v[vram + 32 * k:vram + 32 * k + 32]
            if here == data[32 * k:32 * k + 32] or \
                    here in alt.get(vram + 32 * k, ()):
                good += 1
            else:
                bad += 1
    return good, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/art"))
    ap.add_argument("--vram", help="a VRAM dump (retro-run 'vram') to check "
                    "the preloaded art against")
    ap.add_argument("--no-png", action="store_true")
    args = ap.parse_args()
    rom = Path(args.rom).read_bytes()
    an = analyse(rom)
    regions = sprite_regions(rom)
    bad = overlaps(regions)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rendered = set()
    if not args.no_png:
        render_all(rom, an, out / "animations")
        rendered = {int(p.stem) for p in (out / "animations").glob("*.png")}
    (out / "animations.txt").write_text(index_text(rom, an, regions, bad,
                                                   rendered))
    total = sum(e - a for a, e, _ in regions)
    kinds = {}
    for k, _ in an["kinds"].values():
        kinds[k] = kinds.get(k, 0) + 1
    print(f"{len(regions)} regions, {total} bytes; records: "
          + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    print(f"{len(an['preload'])} preloaded blocks, all "
          f"{'exact' if all(p[6] for p in an['preload']) else 'NOT exact'}; "
          f"{len(rendered)} pictures")
    if args.vram:
        g, b = vram_check(rom, an, args.vram)
        print(f"VRAM: {g} preloaded tiles match, {b} differ")
    for p in an["problems"]:
        print("  does not fit:", p)
    for (a, e, d, b, f, g) in bad:
        print(f"  OVERLAP ${a:06X}-${e:06X} / ${b:06X}-${f:06X}: {d[:50]} / {g[:50]}")


if __name__ == "__main__":
    main()
