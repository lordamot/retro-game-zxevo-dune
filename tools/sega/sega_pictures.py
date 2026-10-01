#!/usr/bin/env python3
"""sega_pictures.py - the tutorial's pictures, their animations, and the
little language that plays them.

    sega_pictures.py [--rom orig/dune2.gen] [--out orig/sega/res/art]

The Mega Drive Dune II has a TUTORIAL on its title screen (it also plays
in the attract loop).  It is a slide show: *descriptions of terrain*,
*of units* and *of buildings*, then *constructing buildings*,
*harvesting*, and *attacking and guarding*, each a full-screen picture that
changes under a cursor sprite and a text box.  It ends on *Your Battle
Begins...*.  This file is all of that.

## The picture table, $0416DA

The loader at `$041662` reads it, and it is **12 records of 12 bytes**:

    move.w  $10(a7),d0          ; the record number
    mulu.w  #$C,d0
    lea.l   $416DA.l,a3
    adda.l  d0,a3
    move.l  (a3)+,d0            ; +0: an asset list, or 0
    beq.w   ...
    movea.l d0,a0
    suba.l  a1,a1               ;     its tiles go to VRAM 0
    jsr     $CD8.w              ;     the tile loader
    move.l  (a3)+,(a2)          ; +4: block A, or 0
    move.l  (a3),$A(a2)         ; +8: block B, or 0
    ...                         ; A is Format80-unpacked to $FF1C00,
                                ; B to $FF7400 (`moveq #-1,d0` - no
                                ; length limit - then `jsr $C32.w`)

Three records (2, 5 and 8) are all zero and nothing loads them.  Two
(7 and 10) have no asset list: they are always loaded straight after 6 and
9, and draw with those records' tiles.  The table ends at `$04176A`, where
the next routine begins - 12 x 12 = 144 bytes, not the "36 longwords in
groups ended by a zero" the listing used to say (a zero there is just an
empty field).

## Block A and block B: a plane's animation

The player at `$04176A` hands one of them to the frame decoder `$0417E0`,
which writes into a 64-cell-wide buffer (`$FF0000` for A, `$FF0E00` for
B) that is then DMA'd, `$700` words = 28 rows of 64, to the nametable
whose address sits in the RAM word named by the table at `$0417DC`:
`$FFE022` for A and `$FFE024` for B.  `$004448` and `$004466` show those
two words are the VDP's **plane A** and **plane B** nametable addresses
(registers 2 and 4); the tutorial sets them to `$C000` and `$E000` at
`$0306C0`.  So A is the front plane and B the one behind it.

An unpacked block is a series of frames, each a 16-bit byte count and then
that many bytes of commands, and `$FFFF` in place of a count ends it.  The
decoder keeps the count in d7 and decrements it for every byte it takes:

    c = $80        skip: the next byte n says how many cells to leave alone
    c > $80        literal: c & $7F words follow, one a cell
    c < $80        run: one word follows, written c times
                   (`cmpi.b #$80,d0` / `bpl` - so > $80 is the literal)

A cell is a VDP nametable word (priority, palette, flips, tile).  Rows are
40 cells: at the 40th the pointer skips `$30` bytes, the other 24 cells of
the 64-cell plane row.  A frame is done when d7 reaches exactly zero
(`subq.w #1,d7` / `bne`), and the player adds count + 2 to the block's
offset, so the next call plays the next frame; at `$FFFF` it returns -1
and stays where it is.

## The checks, all of which pass

  * Every block's Format80 stream stops on its own end marker, and the
    bytes after it are either the next thing or one zero of padding to an
    even address.  The measured trace agrees: of the decompressor's reads
    (PCs $000C32-$000CD7) in this stretch, not one falls outside a block
    named here, and every block the tutorial ran was read to its last
    byte.  (Picture 10's two blocks and all of picture 11 were not run in
    the traced session; they pass the same parse.)
  * Every frame of every block brings d7 to **exactly** zero - a frame
    that did not would make the 68000 run on through memory, because the
    test is `bne`, not `bgt` - and every block ends on `$FFFF` with not
    one byte left over.  A run of length 0 (which `dbf` would turn into
    65536) never occurs.
  * Every frame covers exactly 1120 cells: 40 x 28, one screen.  The code
    does not require that; the data simply is that.
  * A and B of one record have the same number of frames.
  * No map names a tile the record's asset list did not load.
  * The whole stretch `$0307F4-$041662` is covered exactly - no gaps, no
    overlaps - by the palettes, the asset lists, their tile blocks, the A
    and B blocks and single zero bytes of padding.  That is what makes
    every extent here exact rather than estimated.

## The script interpreter, $0418D4

The tutorial routine at `$030674` calls `$0418D4` with scripts 0, 1, 3,
5, 6 and 7 in turn, stopping early if one returns non-zero (the player
pressed START).  `$04190E` is 8 longword pointers to the scripts, and
entries 2 and 4 are zero - exactly the two the caller skips.  A script is
16-bit words: an opcode, which is already a byte offset into the table of
27 word offsets at `$04192E` (relative to the table; entry 0 is unused
because opcode 0 ends the script), and then its operands.  The table ends
where its lowest handler starts, `$04192E + $36 = $041964`.  The opcodes,
read from the handlers:

    $02 w      wait w frames; START aborts the script ($0418A4)
    $04 w      load picture record w ($041662)
    $06 w      play the next frame of plane w (0 = A, 1 = B) and DMA it
    $08        mark: remember this place
    $0A w      until: go back to the mark unless the last $06 returned w
    $0C l      goto l                         (never used)
    $0E        fade to black ($004330)
    $10 l      fade in to the 64-colour palette at l ($004320)
    $12 w      repeat w times ...
    $14        ... loop
    $16 w n    decode n frames of plane w without showing them
    $18 w      play sound w ($02DDAE)
    $1A        rewind both planes             (never used)
    $1C        rewind plane A
    $1E        rewind plane B                 (never used)
    $20        set up the cursor sprite       (never used)
    $22 y x s  the cursor sprite: shape s at (x, y) ($01314A)
    $24        remove the cursor sprite       (never used)
    $26 y x    move the cursor sprite ($0131F8)
    $28        slide the cursor up 96 pixels over 32 frames
    $2A        slide it down again
    $2C l      set the 64-colour palette at l at once ($000F56)
    $2E        wait for the vertical blank    (never used)
    $30 text   show the text box: a string ending in 0, then to even
    $32        remove the text box ($0429CA)
    $34        clear plane B ($041B0E)

The six "never used" handlers are exactly the six that the listing had as
`dc.b`: nothing ever ran them, so the trace never saw them as code.

The check: walking each script from its table entry, every opcode is in
the table, every string ends, every script ends on its own 0, and the six
scripts lie end to end from `$041B40` to `$042946` with one hole - the
128-byte palette `$041F4E`, which script 3's `$2C` names.

## The palettes

Each record's palette is the 128 bytes just in front of its asset list,
and the script fades it in with `$10`.  Five of them - $0307F4, $0331AC,
$036DEA, $03C980 and $03F4E6 - are byte for byte the same.  Checked
against the machine: CRAM dumped every 150 frames through a whole
tutorial matched those, `$03916E` on the build menu, `$041F4E` after the
script's `$2C`, and `$0412F6` on *Your Battle Begins*.

## What the scripts actually show

Every plane A frame of every picture is played.  Plane B is not: every
B block is one to three frames that draw a background, then a frame that
blanks the whole plane (a run of word 0 over all 1120 cells), then frames
that change nothing (`$80 $FF` x 4, `$80 $64`).  The two planes were
plainly exported in step, and the scripts play B exactly as far as the
last frame before the blank one - so the blanking frame is never seen.
The one exception is picture 7, whose B is never played at all; its frame
0 is cell for cell what picture 6's B already left on the screen.  That is
why the renders follow the scripts (`play()`), not the frame numbers.

Checked against the machine: screenshots every 100 frames through a
whole tutorial, 360 of them, and 159 match one of the rendered screens
pixel for pixel.  The rest were taken with the cursor sprite, the pad or
the text box on screen, which the renders leave out, or mid-fade.

Writes `pictures.txt` and `pictures/scriptN.png`: for each script, every
screen it stops on, in order, both planes with the tiles and palette in
effect - the tutorial as the player sees it, minus the cursor sprite and
the text box.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_gfx import lcw, Truncated                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent

TABLE = 0x0416DA            # 12 records of (asset list, block A, block B)
RECORDS = 12
PLANE_VARS = 0x0417DC       # two words: the RAM words holding plane A/B
SCRIPTS = 0x04190E          # 8 longword pointers, two of them zero
SCRIPT_COUNT = 8
OPCODES = 0x04192E          # 27 word offsets, relative to the table
OPCODE_COUNT = 27
SPAN = (0x0307F4, 0x041662)     # everything the table's records occupy
COLS, ROWS, STRIDE = 40, 28, 64

# what each opcode takes: w a word, l a longword, s a string
OPERANDS = {0x02: "w", 0x04: "w", 0x06: "w", 0x08: "", 0x0A: "w",
            0x0C: "l", 0x0E: "", 0x10: "l", 0x12: "w", 0x14: "",
            0x16: "ww", 0x18: "w", 0x1A: "", 0x1C: "", 0x1E: "", 0x20: "",
            0x22: "www", 0x24: "", 0x26: "ww", 0x28: "", 0x2A: "",
            0x2C: "l", 0x2E: "", 0x30: "s", 0x32: "", 0x34: ""}
NAMES = {0x02: "wait", 0x04: "picture", 0x06: "frame", 0x08: "mark",
         0x0A: "until", 0x0C: "goto", 0x0E: "fadeout", 0x10: "fadein",
         0x12: "repeat", 0x14: "loop", 0x16: "skip", 0x18: "sound",
         0x1A: "rewind", 0x1C: "rewindA", 0x1E: "rewindB",
         0x20: "cursoron", 0x22: "cursor", 0x24: "cursoroff",
         0x26: "cursorxy", 0x28: "slideup", 0x2A: "slidedown",
         0x2C: "palette", 0x2E: "vsync", 0x30: "text", 0x32: "textoff",
         0x34: "clearB"}

# what the running game shows for each picture - read off screenshots of
# the tutorial, not guessed from the data
WHAT = {0: "descriptions of terrain, then of units",
        1: "descriptions of buildings",
        3: "constructing buildings: the map, the pad and the yard",
        4: "constructing buildings: the build menu",
        6: "harvesting spice: the harvester to the spice",
        7: "harvesting spice: the harvester back to the refinery",
        9: "attacking and guarding: attacking an enemy unit",
        10: "attacking and guarding: guarding an area",
        11: "Your Battle Begins..."}


def word(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def long(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


class Bad(Exception):
    pass


# ---------------------------------------------------------------- records

def asset_list(rom, at):
    """[(tiles, pointer, compressed)] of the list at `at`, and its length.
    The same format as sega_gfx.asset_list(), without its two-block
    minimum: record 11's list has one block and the code still names it."""
    recs, i = [], at
    while True:
        cnt = word(rom, i)
        if cnt == 0:
            return recs, i + 2 - at
        recs.append((cnt & 0x7FFF, long(rom, i + 2), bool(cnt & 0x8000)))
        i += 6


def records(rom):
    return [(long(rom, TABLE + 12 * r), long(rom, TABLE + 12 * r + 4),
             long(rom, TABLE + 12 * r + 8)) for r in range(RECORDS)]


def unpack(rom, at):
    """A Format80 block run to its own end marker, as `$000C32` does with
    d0 = -1: (bytes, how many bytes of the stream it read)."""
    try:
        return lcw(rom[at:at + 0x20000])
    except (Truncated, IndexError):
        raise Bad(f"${at:06X}: the Format80 stream does not decode")


# ----------------------------------------------------------------- frames

def frames(data, where=""):
    """The frames of an unpacked A or B block, decoded exactly as
    `$0417E0` does, with every check it implies.  Each frame is a list of
    ('skip', n) / ('put', [words]) in cell order."""
    out, o = [], 0
    while True:
        if o + 2 > len(data):
            raise Bad(f"{where}: runs off the end without $FFFF")
        n = word(data, o)
        if n == 0xFFFF:
            if o + 2 != len(data):
                raise Bad(f"{where}: {len(data) - o - 2} bytes after $FFFF")
            return out
        if n == 0:
            raise Bad(f"{where}: a frame of length 0 would never end")
        p, d7, ops, cells = o + 2, n, [], 0
        while d7 > 0:
            c = data[p]
            p += 1
            if c == 0x80:
                k = data[p]
                p += 1
                d7 -= 2
                ops.append(("skip", k))
                cells += k
            elif c > 0x80:
                k = c & 0x7F
                ops.append(("put", [word(data, p + 2 * j) for j in range(k)]))
                p += 2 * k
                d7 -= 1 + 2 * k
                cells += k
            else:
                if c == 0:
                    raise Bad(f"{where}: a run of 0 (dbf makes it 65536)")
                ops.append(("put", [word(data, p)] * c))
                p += 2
                d7 -= 3
                cells += c
        if d7 != 0:
            raise Bad(f"{where}: frame {len(out)} overruns its count by "
                      f"{-d7}")
        if cells != COLS * ROWS:
            raise Bad(f"{where}: frame {len(out)} covers {cells} cells")
        out.append(ops)
        o += 2 + n


def apply(buf, ops):
    """One frame into a 64 x 28 plane buffer, pointer arithmetic and all."""
    p = col = 0
    for kind, v in ops:
        if kind == "skip":
            p += v
            col += v
            if col >= COLS:
                p += (STRIDE - COLS) * (col // COLS)
                col %= COLS
        else:
            for w in v:
                buf[p] = w
                p += 1
                col += 1
                if col == COLS:
                    p += STRIDE - COLS
                    col = 0


# ---------------------------------------------------------------- scripts

def script(rom, at):
    """[(address, opcode, operands)] from `at` to its closing 0."""
    out, a = [], at
    while True:
        op = word(rom, a)
        if op == 0:
            out.append((a, 0, []))
            return out, a + 2
        if op not in OPERANDS:
            raise Bad(f"${a:06X}: opcode ${op:02X} is not in the table")
        p, args = a + 2, []
        for k in OPERANDS[op]:
            if k == "w":
                args.append(word(rom, p))
                p += 2
            elif k == "l":
                args.append(long(rom, p))
                p += 4
            else:
                e = rom.index(b"\0", p)
                if e - p > 80:
                    raise Bad(f"${p:06X}: an unterminated string")
                args.append(rom[p:e].decode("latin-1"))
                p = (e + 2) & ~1
        out.append((a, op, args))
        if op == 0x0C:
            raise Bad(f"${a:06X}: goto - not followed, never used")
        a = p


def opcode_table(rom):
    offs = [word(rom, OPCODES + 2 * i) for i in range(OPCODE_COUNT)]
    lowest = min(o for o in offs if o)
    if OPCODES + lowest != OPCODES + 2 * OPCODE_COUNT:
        raise Bad("the opcode table does not end at its lowest handler")
    if any(2 * i not in OPERANDS for i, o in enumerate(offs) if o):
        raise Bad("a handler with no known operands")
    return {2 * i: OPCODES + o for i, o in enumerate(offs) if o}


def scripts(rom):
    """{number: (start, end, [(addr, op, args)])} for the non-empty ones."""
    out = {}
    for i in range(SCRIPT_COUNT):
        p = long(rom, SCRIPTS + 4 * i)
        if p:
            body, end = script(rom, p)
            out[i] = (p, end, body)
    return out


def fmt(op, args):
    if op == 0:
        return "end"
    parts = []
    for k, v in zip(OPERANDS[op], args):
        if k == "w":
            parts.append(str(v))
        elif k == "l":
            parts.append(f"${v:06X}")
        else:
            parts.append('"' + v.replace("\n", "|") + '"')
    return NAMES[op] + (" " + ", ".join(parts) if parts else "")


# ------------------------------------------------------------------ check

def everything(rom):
    """Decode it all and run every check; raise Bad on the first failure.
    Returns what the regions and the writer need."""
    recs = records(rom)
    info = {}
    for r, (lst, a, b) in enumerate(recs):
        d = {"list": lst, "blocks": [], "planes": {}}
        if lst:
            tl, size = asset_list(rom, lst)
            d["list_size"] = size
            tiles = bytearray()
            for n, ptr, packed in tl:
                if not packed:
                    raise Bad(f"record {r}: a raw block in its list")
                got, used = unpack(rom, ptr)
                if len(got) != n * 32:
                    raise Bad(f"${ptr:06X}: {len(got)} bytes, not {n} tiles")
                d["blocks"].append((ptr, ptr + used, n))
                tiles += got
            d["tiles"] = bytes(tiles)
        for name, at in (("A", a), ("B", b)):
            if not at:
                continue
            got, used = unpack(rom, at)
            fr = frames(got, f"record {r} block {name} ${at:06X}")
            d["planes"][name] = (at, at + used, len(got), fr)
        if "A" in d["planes"] and "B" in d["planes"]:
            if len(d["planes"]["A"][3]) != len(d["planes"]["B"][3]):
                raise Bad(f"record {r}: A and B differ in frame count")
        info[r] = d

    scr = scripts(rom)
    opcode_table(rom)

    # play the scripts' loads to see which tiles and palette each picture
    # is shown with: a picture's palette is the first one its script
    # fades in (or sets) after loading it, or failing that the one already
    # on screen - its frames are drawn while the screen is black
    tiles_from, pal_of, cur, lister, shown = {}, {}, None, None, None
    palette_users = {}

    def settle():
        if cur is not None and cur not in pal_of and shown is not None:
            pal_of[cur] = shown

    for s, (_, _, body) in sorted(scr.items()):
        for a, op, args in body:
            if op == 0x04:
                settle()
                cur = args[0]
                if recs[cur][0]:
                    lister = cur
                if lister is None:
                    raise Bad(f"script {s}: picture {cur} before any tiles")
                if tiles_from.setdefault(cur, lister) != lister:
                    raise Bad(f"picture {cur} is shown with two tile sets")
            elif op in (0x10, 0x2C):
                shown = args[0]
                palette_users.setdefault(shown, []).append((s, a, op))
                if cur is not None:
                    pal_of.setdefault(cur, shown)
    settle()
    for r, d in info.items():
        if not d["planes"]:
            continue
        if r not in tiles_from:
            raise Bad(f"record {r}: no script loads it")
        d["tiles_from"] = tiles_from[r]
        d["palette"] = pal_of.get(r)
        count = len(info[tiles_from[r]]["tiles"]) // 32
        top = max(w & 0x7FF for _, _, _, fr in d["planes"].values()
                  for ops in fr for k, v in ops if k == "put" for w in v)
        if top >= count:
            raise Bad(f"record {r}: tile {top} but only {count} loaded")
        d["top_tile"] = top

    # the stretch the records live in is covered exactly
    pieces = []
    for pal in palette_users:
        if SPAN[0] <= pal < SPAN[1]:
            pieces.append((pal, pal + 128, "palette"))
    for r, d in info.items():
        if d["list"]:
            pieces.append((d["list"], d["list"] + d["list_size"], "list"))
        for s, e, _ in d["blocks"]:
            pieces.append((s, e, "tiles"))
        for s, e, _, _ in d["planes"].values():
            pieces.append((s, e, "plane"))
    pieces.sort()
    pads = []
    at = SPAN[0]
    for s, e, what in pieces:
        if s == at + 1 and at & 1 and rom[at] == 0:
            pads.append(at)
        elif s != at:
            raise Bad(f"${at:06X}-${s:06X} is not accounted for")
        at = e
    if at == SPAN[1] - 1 and rom[at] == 0:
        pads.append(at)
    elif at != SPAN[1]:
        raise Bad(f"the records' stretch ends at ${at:06X}")

    # the scripts lie end to end, with the one palette between
    spans = sorted((s, e) for s, e, _ in scr.values())
    spans += [(p, p + 128) for p in palette_users if not
              SPAN[0] <= p < SPAN[1]]
    spans.sort()
    for (s0, e0), (s1, e1) in zip(spans, spans[1:]):
        if e0 != s1:
            raise Bad(f"scripts: ${e0:06X}-${s1:06X} is not accounted for")
    return info, scr, palette_users, pads, spans


# ---------------------------------------------------------------- regions

def picture_regions(rom, with_tiles=False):
    """Named regions for sega_extract.py: [(start, end_exclusive, text)].

    The asset lists and their tile blocks are sega_gfx.art_regions()'s
    already, so they are left out unless `with_tiles` - all but picture
    11's, which that sweep misses: its list has a single block, and
    sega_gfx.asset_list() wants two.  (A tile block here runs to its end
    marker; art_regions() stops one byte short of it, where the tiles
    are complete.)"""
    info, scr, palette_users, pads, spans = everything(rom)
    out = [(TABLE, TABLE + 12 * RECORDS,
            "the picture table: 12 records of (asset list, plane A "
            "animation, plane B animation), 0 for none - read by $041662, "
            "see res/art/pictures.txt"),
           (PLANE_VARS, PLANE_VARS + 4,
            "two short addresses, $FFE022 and $FFE024: the RAM words that "
            "hold the plane A and plane B nametable addresses - read by "
            "$0417C2 to aim a frame's DMA"),
           (SCRIPTS, SCRIPTS + 4 * SCRIPT_COUNT,
            "the tutorial's 8 script pointers (2 and 4 empty) - read by "
            "$0418E8, called with 0,1,3,5,6,7 from $030674"),
           (OPCODES, OPCODES + 2 * OPCODE_COUNT,
            "the tutorial script's 27 opcode handlers, as word offsets "
            "from here - read by $0418FC; see res/art/pictures.txt")]
    for r, d in info.items():
        what = WHAT.get(r, "")
        if d["list"] and (with_tiles or len(d["blocks"]) < 2):
            n = sum(t for _, _, t in d["blocks"])
            out.append((d["list"], d["list"] + d["list_size"],
                        f"picture {r}'s asset list: {len(d['blocks'])} "
                        f"block(s), {n} tiles, read by $000CD8"))
            for s, e, t in d["blocks"]:
                out.append((s, e, f"{t} tiles for picture {r}, Format80 "
                                  f"(to its end marker)"))
        for name, (s, e, size, fr) in d["planes"].items():
            out.append((s, e,
                        f"picture {r} ({what}), plane {name}: Format80, "
                        f"{size} bytes, {len(fr)} frame{'s' * (len(fr) > 1)} of a 40 x 28 "
                        f"tile map - played by $0417E0"))
    for p, users in sorted(palette_users.items()):
        how = ", ".join(f"script {s} ${a:06X} "
                        f"{'fade in' if op == 0x10 else 'set'}"
                        for s, a, op in users)
        out.append((p, p + 128, f"a 64-colour palette for the tutorial "
                                f"({how})"))
    for p in pads:
        out.append((p, p + 1, "a zero byte of padding to an even address"))
    for s, (a, e, body) in sorted(scr.items()):
        pics = sorted({args[0] for _, op, args in body if op == 0x04})
        out.append((a, e, f"tutorial script {s}: {len(body)} commands, "
                          f"picture{'s' * (len(pics) > 1)} "
                          f"{', '.join(map(str, pics))} - read "
                          f"by $0418D4, see res/art/pictures.txt"))
    return sorted(out)


# ----------------------------------------------------------------- render

def cram_rgb(w):
    return (((w >> 1) & 7) * 255 // 7, ((w >> 5) & 7) * 255 // 7,
            ((w >> 9) & 7) * 255 // 7)


def play(rom, info, scr, number):
    """Run script `number` the way $0418D4 does, minus the sprites, the
    text and the waiting, and return what the player is shown:
    [(picture, plane A cells, plane B cells, palette address)], one each
    time the script waits on a screen that differs from the last one.
    Also returns {(picture, plane): set of frame numbers decoded}.

    This is what the renders are made from, rather than the two planes
    played in step: every B block carries a frame that blanks the plane
    (picture 0's frame 1, say), and only the script says it is never
    shown."""
    a, end, body = scr[number]
    at = {addr: i for i, (addr, _, _) in enumerate(body)}
    vram = {"A": [0] * (STRIDE * ROWS), "B": [0] * (STRIDE * ROWS)}
    buf = {"A": [0] * (STRIDE * ROWS), "B": [0] * (STRIDE * ROWS)}
    pos, cur, pal, dark = {}, None, None, True
    shown, played = [], {}
    i = mark = 0
    d6 = d7 = 0
    steps = 0
    while True:
        steps += 1
        if steps > 100000:
            raise Bad(f"script {number} does not finish")
        addr, op, args = body[i]
        nxt = i + 1
        if op == 0:
            return shown, played
        if op == 0x04:
            cur = args[0]
            pos = {"A": 0, "B": 0}
        elif op in (0x06, 0x16):
            plane = "AB"[args[0]]
            for _ in range(args[1] if op == 0x16 else 1):
                fr = info[cur]["planes"].get(plane)
                if fr is None:
                    d7 = 0
                    continue
                fr = fr[3]
                if pos[plane] >= len(fr):
                    d7 = 0xFFFF
                    continue
                played.setdefault((cur, plane), set()).add(pos[plane])
                apply(buf[plane], fr[pos[plane]])
                pos[plane] += 1
                d7 = 0
                if op == 0x06:
                    vram[plane] = list(buf[plane])
        elif op == 0x08:
            mark = nxt
        elif op == 0x0A:
            if d7 != args[0]:
                nxt = mark
        elif op == 0x0E:
            dark = True
        elif op in (0x10, 0x2C):
            pal, dark = args[0], False
        elif op == 0x12:
            d6, mark = args[0], nxt
        elif op == 0x14:
            d6 -= 1
            if d6:
                nxt = mark
        elif op == 0x1C:
            pos["A"] = 0
        elif op == 0x34:
            vram["B"] = [0] * (STRIDE * ROWS)
        if op in (0x02, 0x10, 0x2C) and not dark:
            state = (cur, tuple(vram["A"]), tuple(vram["B"]), pal)
            if not shown or shown[-1] != state:
                shown.append(state)
        i = nxt


def render(vram_a, vram_b, tiles, pal):
    """One screen: the two planes over the backdrop, the VDP's way."""
    from PIL import Image
    rgb = [cram_rgb(p) for p in pal]
    img = Image.new("RGB", (COLS * 8, ROWS * 8), rgb[0])
    px = img.load()
    # the VDP's order: B low, A low, B high, A high
    for buf, pri in ((vram_b, 0), (vram_a, 0), (vram_b, 1), (vram_a, 1)):
        for row in range(ROWS):
            for col in range(COLS):
                w = buf[row * STRIDE + col]
                if (w >> 15) != pri:
                    continue
                t = (w & 0x7FF) * 32
                line = (w >> 13) & 3
                vf, hf = (w >> 12) & 1, (w >> 11) & 1
                for y in range(8):
                    sy = 7 - y if vf else y
                    for x in range(8):
                        sx = 7 - x if hf else x
                        c = (tiles[t + sy * 4 + sx // 2] >>
                             (0 if sx & 1 else 4)) & 15
                        if c:
                            px[col * 8 + x, row * 8 + y] = rgb[line * 16 + c]
    return img


def sheet(images, path, across=4):
    from PIL import Image
    w, h = images[0].size
    down = (len(images) + across - 1) // across
    s = Image.new("RGB", (across * (w + 2) - 2, down * (h + 2) - 2),
                  (40, 40, 40))
    for i, im in enumerate(images):
        s.paste(im, ((i % across) * (w + 2), (i // across) * (h + 2)))
    s.save(path)


# ------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/art"))
    args = ap.parse_args()
    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    (out / "pictures").mkdir(parents=True, exist_ok=True)

    info, scr, palette_users, pads, spans = everything(rom)
    regions = picture_regions(rom, with_tiles=True)

    L = ["# The tutorial's pictures - written by tools/sega/sega_pictures.py",
         "#",
         "# The picture table at $0416DA: 12 records of (asset list, plane A,",
         "# plane B), loaded by $041662.  A plane block is Format80; unpacked",
         "# it is frames of a 40 x 28 tile map, each a byte count and then",
         "# $80 n = skip n cells, $81-$FF = that & $7F words follow,",
         "# $01-$7F = the next word that many times; $FFFF ends it.",
         "# Plane A is the front plane ($FFE022), B the back one ($FFE024).",
         "# Every frame parses to exactly its count and covers 1120 cells;",
         "# every block ends on $FFFF with nothing left over.",
         "#",
         "# Renders: pictures/scriptN.png, every screen each script stops on,",
         "# drawn from the tiles, the maps and the palette the script gives.",
         ""]
    played = {}
    for n in sorted(scr):
        for k, v in play(rom, info, scr, n)[1].items():
            played.setdefault(k, set()).update(v)
    total = {"plane": 0, "tiles": 0}
    for r, d in info.items():
        if not d["list"] and not d["planes"]:
            L.append(f"picture {r:2}: empty (all three fields zero; no "
                     f"script loads it)")
            continue
        L.append(f"picture {r:2}: {WHAT.get(r, '')}")
        if d["list"]:
            n = sum(t for _, _, t in d["blocks"])
            L.append(f"    tiles   ${d['list']:06X}  asset list, "
                     f"{len(d['blocks'])} block(s), {n} tiles to VRAM 0")
            for s, e, t in d["blocks"]:
                L.append(f"            ${s:06X}-${e - 1:06X} {e - s:5} bytes"
                         f"  {t} tiles")
                total["tiles"] += e - s
        else:
            L.append(f"    tiles   none of its own - uses picture "
                     f"{d['tiles_from']}'s, loaded just before")
        for name, (s, e, size, fr) in d["planes"].items():
            got = sorted(played.get((r, name), ()))
            use = ("all played" if got == list(range(len(fr))) else
                   "the scripts play " + (", ".join(map(str, got)) or
                                          "none"))
            L.append(f"    plane {name} ${s:06X}-${e - 1:06X} {e - s:5} bytes "
                     f"-> {size} bytes, {len(fr)} frame{'s' * (len(fr) > 1)}, {use}")
            total["plane"] += e - s
        if d.get("palette"):
            L.append(f"    palette ${d['palette']:06X}")
        L.append(f"    highest tile used {d['top_tile']}")
        L.append("")

    L.append("palettes (64 colours, 128 bytes each):")
    seen = {}
    for p in sorted(palette_users):
        same = seen.setdefault(rom[p:p + 128], p)
        note = "" if same == p else f"  (the same bytes as ${same:06X})"
        L.append(f"    ${p:06X}{note}")
    L.append("")
    L.append("the script opcodes (table $04192E, handlers):")
    for op, h in sorted(opcode_table(rom).items()):
        L.append(f"    ${op:02X} {NAMES[op]:10} {OPERANDS[op] or '-':4}"
                 f"  ${h:06X}")
    L.append("")
    for s, (a, e, body) in sorted(scr.items()):
        L.append(f"script {s}: ${a:06X}-${e - 1:06X}")
        for at, op, args in body:
            L.append(f"    ${at:06X}  {fmt(op, args)}")
        L.append("")
    L.append(f"bytes: {total['plane']} in plane blocks, {total['tiles']} in "
             f"tile blocks, {len(pads)} padding; "
             f"{sum(e - s for s, e, _ in regions)} in all the regions "
             f"named here")
    (out / "pictures.txt").write_text("\n".join(L) + "\n")

    for n in sorted(scr):
        shown, _ = play(rom, info, scr, n)
        imgs = []
        for pic, va, vb, pal in shown:
            tiles = info[info[pic]["tiles_from"]]["tiles"]
            imgs.append(render(va, vb, tiles,
                               [word(rom, pal + 2 * i) for i in range(64)]))
        sheet(imgs, out / "pictures" / f"script{n}.png")
    print(f"{len(regions)} regions, "
          f"{sum(e - s for s, e, _ in regions)} bytes; "
          f"wrote {out / 'pictures.txt'}")


if __name__ == "__main__":
    main()
