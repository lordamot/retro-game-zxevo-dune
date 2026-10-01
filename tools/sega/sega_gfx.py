#!/usr/bin/env python3
"""sega_gfx.py - the compressed art, decompressed.

    sega_gfx.py [--rom orig/dune2.gen] [--out orig/sega/res/art] [--scan]

Most of this cartridge is pictures and none of them are stored as pictures.
This finds them, unpacks them and writes them out as PNGs with the colours
the game draws them in.

## The compression

Westwood's **Format80** - the same LZ the PC Dune II used - with its
16-bit fields still little-endian inside a big-endian cartridge, because
the data came over unchanged.  The decompressor is at `$000C32` and this
is what it does, command byte by command byte:

    0xxxxxxx  ppppppppp   copy (c>>4)+3 bytes from (c&0x0F)<<8|p back
                          from where the output has got to
    10cccccc              c literal bytes follow; $80 alone ends the stream
    11cccccc  oooo        copy (c&$3F)+3 bytes from offset oooo, counted
                          from the start of the output
    $FE       nnnn v      write the byte v, n times
    $FF       nnnn oooo   copy n bytes from offset oooo

## What an asset looks like

The caller at `$008352` lays it out:

    +$00   32 bytes   a palette: 16 Mega Drive colour words
    +$20   $A8 bytes  a table the code adds $0380 to and masks - the
                      sprite's own tile numbers
    +$C8   word       how many bytes it unpacks to
    +$CA   ...        the Format80 stream

Two tables of those are the game's cast: **19 at `$08829C`, one a
building, and 27 at `$08F1C8`, one a unit** - the same counts as the stat
tables and the script entry points, which is what says they line up.

## Why the reading is safe

Every asset carries the size it unpacks to, so a wrong decompressor is
caught immediately rather than producing plausible rubbish.  All of them
come out to the byte.  `--scan` uses the same property the other way
round: it walks the whole ROM offering every even address to the
decompressor and keeps the ones whose stream reproduces its own size word,
which finds the art nothing points at from a table this project has found.
"""

import argparse
import functools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Where the code itself says the asset lists are.  Found by scanning the
# ROM for calls to the loader at $000CD8 - there are six - and reading what
# each is handed:
#
#   $001874   lea $18CE,a0                 one list
#   $013108   lea $13872,a0                one list
#   $017DBE   lea $17F2A,a0                one list
#   $041686   a table of 6+6 longwords at $0416DA and $0416FE
#   $0C7D2E   a table of 16-byte records at $0C7C18, first long the list
#   $004392   a thunk; its caller supplies the pointer
#
# This beats sweeping for the shape, and finds lists the sweep cannot: a
# list whose blocks happen to sit where nothing else looks.
LIST_POINTERS = [0x0018CE, 0x013872, 0x017F2A]
LIST_TABLES = [(0x0416DA, 6, 4), (0x0416FE, 6, 4), (0x0C7C18, 15, 16)]

BUILDING_TABLE = (0x08829C, 19)
UNIT_TABLE = (0x08F1C8, 27)
PALETTE, TILEMAP, DATA = 0x00, 0x20, 0xC8


class Truncated(Exception):
    pass


def lcw(src, expect=None, limit=1 << 20):
    """Format80, exactly as `$000C32` runs it.

    Returns the unpacked bytes and **how many of the input they came
    from**.  The second number is what lets the disassembly mark where a
    stream begins and ends; without it 500 KB of this cartridge stays
    anonymous `dc.b` even after the pictures have been read out of it.
    """
    out, i = bytearray(), 0
    while i < len(src) and len(out) < limit:
        c = src[i]
        i += 1
        if not c & 0x80:                       # short copy, relative
            if i >= len(src):
                raise Truncated
            off = ((c & 0x0F) << 8) | src[i]
            i += 1
            n, p = (c >> 4) + 3, len(out) - off
            if p < 0:
                raise Truncated
            for k in range(n):
                out.append(out[p + k])
        elif not c & 0x40:                     # literals, or the end
            if c == 0x80:
                break
            n = c & 0x3F
            if i + n > len(src):
                raise Truncated
            out += src[i:i + n]
            i += n
        elif c == 0xFE:                        # a run of one byte
            if i + 3 > len(src):
                raise Truncated
            n = src[i] | (src[i + 1] << 8)
            out += bytes([src[i + 2]]) * n
            i += 3
        elif c == 0xFF:                        # long copy, absolute
            if i + 4 > len(src):
                raise Truncated
            n = src[i] | (src[i + 1] << 8)
            off = src[i + 2] | (src[i + 3] << 8)
            i += 4
            if off + n > len(out) + n:
                raise Truncated
            for k in range(n):
                if off + k >= len(out):
                    raise Truncated
                out.append(out[off + k])
        else:                                  # medium copy, absolute
            if i + 2 > len(src):
                raise Truncated
            n = (c & 0x3F) + 3
            off = src[i] | (src[i + 1] << 8)
            i += 2
            for k in range(n):
                if off + k >= len(out):
                    raise Truncated
                out.append(out[off + k])
        if expect is not None and len(out) >= expect:
            # the machine's decompressor goes on to read the $80 that ends
            # the stream (the recorded run has $000C3E reading it), so that
            # byte belongs to the stream too
            if i < len(src) and src[i] == 0x80:
                i += 1
            break
    return bytes(out), i


def cram(w):
    return (((w >> 1) & 7) * 255 // 7, ((w >> 5) & 7) * 255 // 7,
            ((w >> 9) & 7) * 255 // 7)


def unpack(rom, base, strict=True):
    """An asset's palette, its tiles, and whether it came out to the byte.

    The size word is the check: for nearly every asset the stream produces
    exactly that many bytes, and one that does not is either not an asset
    or is carrying something after the tiles.  `strict` demands the exact
    match and is what the ROM sweep uses, since there a near miss is a
    false positive; the two known tables are read leniently, because a
    table entry is already evidence.
    """
    d = base + DATA
    if d + 2 > len(rom):
        return None
    size = int.from_bytes(rom[d:d + 2], "big")
    if not 512 <= size <= 0x8000:
        return None
    try:
        tiles, used = lcw(rom[d + 2:d + 2 + 0x10000], expect=size)
    except (Truncated, IndexError):
        return None
    exact = len(tiles) == size
    if strict and not exact:
        return None
    if len(tiles) < 512:
        return None
    pal = [int.from_bytes(rom[base + i * 2:base + i * 2 + 2], "big")
           for i in range(16)]
    if any(w & 0xF111 for w in pal):
        return None
    n = len(tiles) // 32 * 32
    return pal, tiles[:n], exact, DATA + 2 + used


def render(pal, tiles, path, cols=16):
    from PIL import Image
    n = len(tiles) // 32
    rows = (n + cols - 1) // cols
    img = Image.new("P", (cols * 8, rows * 8))
    flat = []
    for w in pal:
        flat += list(cram(w))
    img.putpalette(flat + [0] * (768 - len(flat)))
    px = img.load()
    for t in range(n):
        b = tiles[t * 32:(t + 1) * 32]
        ox, oy = (t % cols) * 8, (t // cols) * 8
        for y in range(8):
            for x in range(8):
                v = b[y * 4 + x // 2]
                px[ox + x, oy + y] = (v >> 4) if x % 2 == 0 else (v & 15)
    img.save(path)
    return n


def asset_list(rom, at, limit=40, require_compressed=True):
    """The list of tile blocks at `at`, or None.

    The loader at `$000CD8` reads one of these: pairs of a count and a
    pointer, ended by a count of zero.

        move.w  (a3)+,d4          ; how many tiles
        beq.s   done              ; 0 ends the list
        movea.l (a3)+,a0          ; where they are
        bpl.s   raw               ; ...on the flags MOVE.W left, so this
        jsr     L_000C32(pc)      ; tests bit 15 of the COUNT: set means
                                  ; the block is Format80
        andi.w  #$7FFF,d4
        ...
        asl.w   #$5,d4            ; then VRAM advances by tiles * 32
        add.w   d4,d3

    MOVEA sets no condition codes on a 68000, which is why the `bpl` there
    is testing the count and not the pointer - and why the compressed flag
    lives in the top bit of a tile count.
    """
    recs, i, n = [], at, len(rom)
    while i + 6 <= n:
        cnt = int.from_bytes(rom[i:i + 2], "big")
        if cnt == 0:
            # How strict to be depends on where the address came from.
            # When *sweeping*, every block must be compressed: the shape
            # alone is six bytes of anything and a raw block is checked by
            # nothing, so allowing them claimed 61 stretches of ordinary
            # code as artwork.  When the *code* hands the loader this
            # address, that is the evidence, and a real list may perfectly
            # well hold raw blocks - thirteen of them do.
            if len(recs) < 2:
                return None
            if require_compressed and not all(c for _, _, c in recs):
                return None
            return recs
        ptr = int.from_bytes(rom[i + 2:i + 6], "big")
        tiles = cnt & 0x7FFF
        if not 1 <= tiles <= 2048 or not 0x200 <= ptr < n:
            return None
        recs.append((tiles, ptr, bool(cnt & 0x8000)))
        i += 6
        if len(recs) > limit:
            return None
    return None


def read_list(rom, recs):
    """Every block of a list, unpacked, as one run of tiles.

    The **last** block of a list is allowed to come up short.  Four of the
    lists the code names end that way and every earlier block in them
    unpacks to exactly its 4096 bytes, so it is the format and not a
    misreading: the stream stops at its end marker and the game uploads
    the declared tile count regardless, tail and all.  Anything short in
    the middle of a list is still a failure.
    """
    out = bytearray()
    for k, (tiles, ptr, packed) in enumerate(recs):
        want = tiles * 32
        last = k == len(recs) - 1
        if packed:
            try:
                got, _ = lcw(rom[ptr:ptr + 0x20000], expect=want)
            except (Truncated, IndexError):
                return None
            if len(got) < want and not last:
                return None
            out += got[:want].ljust(want, b"\0")
        else:
            if ptr + want > len(rom):
                return None
            out += rom[ptr:ptr + want]
    return bytes(out)


GREY = [(i * 17, i * 17, i * 17) for i in range(16)]


def render_rgb(pal, tiles, path, cols=16):
    from PIL import Image
    n = len(tiles) // 32
    rows = (n + cols - 1) // cols
    img = Image.new("P", (cols * 8, rows * 8))
    flat = []
    for c in pal:
        flat += list(c)
    img.putpalette(flat + [0] * (768 - len(flat)))
    px = img.load()
    for t in range(n):
        b = tiles[t * 32:(t + 1) * 32]
        ox, oy = (t % cols) * 8, (t // cols) * 8
        for y in range(8):
            for x in range(8):
                v = b[y * 4 + x // 2]
                px[ox + x, oy + y] = (v >> 4) if x % 2 == 0 else (v & 15)
    img.save(path)
    return n


def raw_tile_runs(rom, free, least=32):
    """Runs of plain 4bpp tiles inside the stretches nothing else claims.

    `free` is a bytearray with a 1 wherever a byte is still unaccounted
    for.  Searching only there is what makes this safe: the loose "does
    this look like a tile" test that eats real code when let loose over a
    whole cartridge cannot reach any here, because traced code is not in
    the gaps by construction.

    A run is believed to be *pixel-shaped* when its tiles use few of the
    sixteen pens and repeat them along their rows - drawn pictures do,
    longwords and pointers do not - and when they are not all the same.

    That is as far as it goes, and the listing says so.  Pixel-shaped is
    not the same as "art the game draws", and these runs fail the test
    that the Format80 blocks pass: comparing them against 64 KB of live
    VRAM from the middle of a battle (`make md`) finds **none** of the
    1066 tiles here, where the same comparison finds 2101 of the 6791 in
    the asset lists.  That is not proof they are nothing - the sprite sets
    score near zero on the same test only because no buildings were placed
    in that capture, and they are certainly real - but it is the whole of
    the evidence, and it is not enough to call these pictures.
    """
    out = []
    start = None
    n = len(rom) // 32
    for t in range(n):
        a = t * 32
        ok = all(free[a:a + 32]) and _tile_like(rom[a:a + 32])
        if ok:
            if start is None:
                start = t
        else:
            if start is not None and t - start >= least:
                _keep(rom, out, start, t)
            start = None
    if start is not None and n - start >= least:
        _keep(rom, out, start, n)
    return out


def _tile_like(b):
    if len(b) < 32:
        return False
    nib = []
    for x in b:
        nib += [x >> 4, x & 15]
    used = len(set(nib))
    runs = sum(1 for i in range(1, 64) if nib[i] == nib[i - 1])
    return 1 <= used <= 10 and runs >= 20


def _keep(rom, out, first, last):
    tiles = [rom[t * 32:(t + 1) * 32] for t in range(first, last)]
    if len(set(tiles)) < 8:
        return
    out.append((first * 32, last * 32,
                f"{last - first} tiles' worth of pixel-shaped data - NOT "
                f"confirmed as art; see raw_tile_runs()"))


@functools.lru_cache(maxsize=None)
def block(rom_id, v):
    """`v` as a Format80 block, if it is one: (input used, output length),
    and only when the output is a whole number of tiles.  That last test is
    the whole of the safety here - it is the same one that separates a real
    asset list from six bytes shaped like one."""
    rom = _ROM[rom_id]
    if v & 1 or not 0x200 <= v < len(rom) - 8:
        return None
    try:
        out, used = lcw(rom[v:v + 0x20000])
    except (Truncated, IndexError):
        return None
    if len(out) < 512 or len(out) % 32 or used < 32:
        return None
    return used, len(out)


_ROM = {}


def stream_tables(rom, least=3):
    """Runs of longwords that *all* point at whole-tile Format80 blocks.

    The asset lists the loader at `$000CD8` reads are not the only way this
    cartridge finds a picture: some of the art is reached through a plain
    table of pointers, and about 44 KB of it is claimed by nothing else.

    Three in a row is the bar, and it is a high one: a longword has to be
    even, has to land inside the cartridge, and what it lands on has to
    survive Format80 decompression and come out to an exact number of
    tiles.  Bytes that are not a pointer table fail on the first or second
    pointer nearly always; this finds five tables in a megabyte.
    """
    _ROM[id(rom)] = rom
    rid = id(rom)
    out, i = [], 0x200
    while i < len(rom) - 12:
        n = 0
        while n <= 128:
            w = int.from_bytes(rom[i + 4 * n:i + 4 * n + 4], "big")
            if not block(rid, w):
                break
            n += 1
        if n >= least:
            out.append((i, n))
            i += 4 * n
        else:
            i += 2
    return out


def named_lists(rom):
    """Every asset list the code names, without guessing."""
    out = list(LIST_POINTERS)
    for base, count, stride in LIST_TABLES:
        for k in range(count):
            a = base + k * stride
            v = int.from_bytes(rom[a:a + 4], "big")
            if 0x200 <= v < len(rom) and not v & 1:
                out.append(v)
    return sorted(set(out))


# The picture table: twelve records of (asset list, block A, block B) -
# the tutorial's screens.  Only its asset lists are read here, for their
# tiles; tools/sega/sega_pictures.py has the rest.
PICTURE_TABLE = 0x0416DA


def picture_table(rom, at=PICTURE_TABLE):
    """Every entry of the table at `at`, up to the first longword that is
    neither zero nor an even address in the two banks it covers."""
    out, k = [], 0
    while True:
        v = int.from_bytes(rom[at + 4 * k:at + 4 * k + 4], "big")
        if v and not (0x030000 <= v < 0x042000 and not v & 1):
            break
        out.append(v)
        k += 1
    return out


def art_regions(rom):
    """Every byte of this cartridge that is a picture, and what it is.

    The disassembly imports this so the listing can say so.  Three kinds:
    the sprite sets the two tables point at, the `(count, pointer)` lists
    the loader at `$000CD8` reads, and each block those lists name.  A
    compressed block's end is known because `lcw` reports how much of the
    input it ate - which is the only reason this can be done at all.
    """
    out = []
    for label, (tbl, count) in (("building", BUILDING_TABLE),
                                ("unit", UNIT_TABLE)):
        for i in range(count):
            base = int.from_bytes(rom[tbl + i * 4:tbl + i * 4 + 4], "big")
            got = unpack(rom, base, strict=False)
            if got:
                out.append((base, base + got[3],
                            f"{label} {i}: palette, tile map and a Format80 "
                            f"picture - see res/art/sprites.txt"))
        out.append((tbl, tbl + count * 4,
                    f"{count} pointers, one to each {label}'s picture"))

    swept = []
    at = 0
    while at + 6 <= len(rom):
        recs = asset_list(rom, at)
        if recs and read_list(rom, recs):
            swept.append(at)
            at += len(recs) * 6 + 2
            continue
        at += 2
    code_named = set(named_lists(rom))
    for at in sorted(set(swept) | code_named):
        recs = asset_list(rom, at, require_compressed=at not in code_named)
        if recs:
            tiles = read_list(rom, recs)
            if tiles and len(tiles) >= 512:
                out.append((at, at + len(recs) * 6 + 2,
                            f"an asset list: {len(recs)} blocks, "
                            f"{len(tiles) // 32} tiles, read by $000CD8"))
                for n, ptr, packed in recs:
                    if packed:
                        try:
                            _, used = lcw(rom[ptr:ptr + 0x20000],
                                          expect=n * 32)
                        except (Truncated, IndexError):
                            continue
                        out.append((ptr, ptr + used,
                                    f"{n} tiles, Format80"))
                    else:
                        out.append((ptr, ptr + n * 32,
                                    f"{n} tiles, stored plainly"))

    # The picture table's own records, and the tile-map animations its
    # blocks A and B unpack to, are sega_pictures.py's: it is twelve records
    # of three longwords, not groups ended by a zero, and what the blocks
    # hold is frames of a 40-column name table.

    # and the art the loader never sees: plain tables of pointers, each
    # one landing on a Format80 block that comes out to whole tiles
    rid = id(rom)
    for at, n in stream_tables(rom):
        ptrs = [int.from_bytes(rom[at + 4 * k:at + 4 * k + 4], "big")
                for k in range(n)]
        tiles = sum(block(rid, p)[1] for p in ptrs) // 32
        out.append((at, at + 4 * n,
                    f"{n} pointers to Format80 blocks, {tiles} tiles "
                    f"between them - see stream_tables()"))
        for p in ptrs:
            used, got = block(rid, p)
            out.append((p, p + used, f"{got // 32} tiles, Format80"))
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/art"))
    ap.add_argument("--scan", action="store_true",
                    help="also sweep the whole ROM for the asset lists the "
                         "loader at $000CD8 reads")
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    (out / "sprites").mkdir(parents=True, exist_ok=True)

    def names(path, count):
        if not path.exists():
            return [f"{i}" for i in range(count)]
        got = []
        for line in path.read_text().splitlines():
            p = line.split()
            if len(p) > 2 and p[0].isdigit() and int(p[0]) == len(got):
                k = 1
                while k < len(p) and not p[k].lstrip("-").isdigit():
                    k += 1
                got.append(" ".join(p[1:k]))
        return got[:count] if len(got) >= count else [f"{i}" for i in range(count)]

    lines = [
        "# sprites.txt - the game's pictures, decompressed.",
        "#",
        "# Written by tools/sega/sega_gfx.py.  Each is Westwood Format80 -",
        "# see the tool's header - and carries the size it unpacks to, so",
        "# every one below came out to the byte or it would not be here.",
        "# The PNG is drawn in the asset's own 16 colours.",
        "#",
        "# what                  address   tiles  file",
        "",
    ]
    seen = {}
    for label, (tbl, count), src in (
            ("building", BUILDING_TABLE, out.parent / "data/buildings.txt"),
            ("unit", UNIT_TABLE, out.parent / "data/units.txt")):
        who = names(src, count)
        for i in range(count):
            base = int.from_bytes(rom[tbl + i * 4:tbl + i * 4 + 4], "big")
            got = unpack(rom, base, strict=False)
            if not got:
                lines.append(f"{label} {who[i]:<15} ${base:06X}  "
                             f"did not unpack")
                continue
            pal, tiles, exact, _ = got
            slug = who[i].lower().replace(" ", "_").replace("'", "") \
                                 .replace("(", "").replace(")", "")
            name = f"{label}_{i:02d}_{slug}.png"
            n = render(pal, tiles, out / "sprites" / name)
            seen[base] = name
            lines.append(f"{label} {who[i]:<15} ${base:06X}  {n:5d}  "
                         f"sprites/{name}"
                         + ("" if exact else "   (the stream ends before "
                            "the size word says)"))

    extra = extra_bytes = tab_n = 0
    if args.scan:
        (out / "blocks").mkdir(parents=True, exist_ok=True)
        lines += [
            "",
            "# The asset lists the loader at $000CD8 reads - everything else",
            "# the game draws.  A list is (count.w, pointer.l) pairs ended by",
            "# a zero count, and the top bit of a count says its block is",
            "# compressed.  Found by sweeping for that shape and then",
            "# unpacking every block in the candidate: a list is only",
            "# reported when all of them come out.",
            "#",
            "# These are drawn in grey.  A block carries no palette - which",
            "# of the VDP's four the tiles are shown in is decided by the",
            "# code that loads them, not stored beside the pixels.",
            "#",
            "# list      blocks  tiles  file",
            "",
        ]
        at, swept = 0, []
        while at + 6 <= len(rom):
            recs = asset_list(rom, at)
            if recs:
                tiles = read_list(rom, recs)
                if tiles and len(tiles) >= 512:
                    swept.append(at)
                    at += len(recs) * 6 + 2
                    continue
            at += 2
        code_named = set(named_lists(rom))
        for at in sorted(set(swept) | code_named):
            recs = asset_list(rom, at,
                              require_compressed=at not in code_named)
            if recs:
                tiles = read_list(rom, recs)
                if tiles and len(tiles) >= 512:
                    name = f"blocks/list_{at:06X}.png"
                    n = render_rgb(GREY, tiles, out / name, cols=32)
                    where = "code" if at in code_named else "sweep"
                    lines.append(f"${at:06X}  {len(recs):5d}  {n:5d}  "
                                 f"{name:<28} {where}")
                    extra += 1
                    extra_bytes += len(tiles)
        lines.append("")
        lines.append(f"# {extra} lists, {extra_bytes} bytes of tile data "
                     f"({extra_bytes // 32} tiles).")

        lines += [
            "",
            "# The art the loader never sees: plain tables of longwords,",
            "# every one of them landing on a Format80 block that comes out",
            "# to a whole number of tiles.  Three in a row is the bar and it",
            "# finds five tables in a megabyte - see stream_tables().",
            "#",
            "# table    blocks  tiles  file",
            "",
        ]
        rid = id(rom)
        tab_n = tab_bytes = 0
        for at, n in stream_tables(rom):
            tiles = bytearray()
            for k in range(n):
                ptr = int.from_bytes(rom[at + 4 * k:at + 4 * k + 4], "big")
                tiles += lcw(rom[ptr:ptr + 0x20000], expect=block(rid, ptr)[1])[0]
            name = f"blocks/table_{at:06X}.png"
            got = render_rgb(GREY, bytes(tiles), out / name, cols=32)
            lines.append(f"${at:06X}  {n:5d}  {got:5d}  {name}")
            tab_n += 1
            tab_bytes += len(tiles)
        lines.append("")
        lines.append(f"# {tab_n} tables, {tab_bytes} bytes of tile data "
                     f"({tab_bytes // 32} tiles).")
        extra_bytes += tab_bytes

    (out / "sprites.txt").write_text("\n".join(lines) + "\n")
    print(f"{len(seen)} assets from the two tables"
          + (f", {extra} asset lists and {tab_n} pointer tables "
             f"({extra_bytes // 32} tiles)" if args.scan else "")
          + f" -> {out}/")


if __name__ == "__main__":
    main()
