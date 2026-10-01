#!/usr/bin/env python3
"""sega_extract.py - take `orig/dune2.gen` apart into sources.

    sega_extract.py [--rom orig/dune2.gen] [--out orig/sega]

Writes a deconstruction that rebuilds:

    orig/sega/rom.map          the region map - what every byte of the ROM is
    orig/sega/src/vectors.asm  the 68000 exception table, named
    orig/sega/src/header.asm   the Mega Drive header, as fields
    orig/sega/src/megadrive.inc  the VDP, the Z80 and the pad, by name
    orig/sega/src/romNN.asm    64 KB of the cartridge, disassembled

`build_sega.py` puts them back together and checks the SHA-256 against the
original, so what is under `src/` is the ROM and not a description of it.

## How the code is found

Easier than on the NES, and for one reason: the 68000 has no banking.  The
whole megabyte is mapped at $000000 and every address in it means what it
says, so a recursive-descent trace can actually follow the program.

  * the 64 exception vectors are the certain entry points - vector 1 is
    the reset address, $000200;
  * every JSR, BSR and JMP target the trace meets is followed;
  * runs of consecutive longwords that all point into the cartridge are
    jump tables, and their entries are offered as well - which is how the
    layers below the first one get found at all;
  * whatever is left over is read forwards a byte at a time, and any run
    that decodes cleanly to an RTS or a JMP is kept, marked as found by
    sweep rather than by a call.

Every instruction written out is re-assembled before it is written, and one
that does not come back as the same words is emitted as `dc.w` instead.
That is what makes the 100% rebuild possible without trusting the
disassembler: it is not allowed to write down anything it cannot read back.
"""

import argparse
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import m68k                                                # noqa: E402
from sega_gfx import art_regions, raw_tile_runs             # noqa: E402
from sega_maps import map_regions                           # noqa: E402
import sega_blocks                                          # noqa: E402
import sega_names                                           # noqa: E402
import sega_pictures                                        # noqa: E402
import sega_sprites                                         # noqa: E402
import sega_tables_hi                                       # noqa: E402
import sega_tables_lo                                       # noqa: E402


def identified(rom):
    """What the modules that read one kind of thing each have to say.

    Each keeps its own list and its own check(), and the check is run here:
    a module whose claims no longer hold stops the extraction rather than
    writing them into the listing.  Returns `(regions, code)` - regions as
    `(start, end, what)`, code as `(entry, why)` for routines nothing in
    the running game or the trace reaches, which each module has decoded
    and checked will re-assemble.
    """
    for m in (sega_tables_lo, sega_tables_hi, sega_blocks):
        m.check(rom)
    regions = (list(sega_tables_lo.TABLES) + list(sega_tables_hi.TABLES)
               + list(sega_blocks.BLOCKS)
               + sega_pictures.picture_regions(rom)
               + sega_sprites.sprite_regions(rom))
    code = (list(sega_tables_lo.CODE) + list(sega_tables_hi.CODE)
            + list(sega_blocks.CODE))
    return regions, code


def merge_regions(general, specific):
    """One list out of two, where the specific word wins.

    A region the reading modules name with exactly the extent a general
    finder gave it (a Format80 block that turns out to be a tile map, a
    run of 'pixels' that is a portrait) keeps only the specific name.
    Anything else overlapping is reported, because two claims on one byte
    is a question and not an answer.
    """
    exact = {(a, b) for a, b, _ in specific}
    out = [r for r in general if (r[0], r[1]) not in exact] + list(specific)
    out.sort()
    clashes = []
    reach = []
    for a, b, what in out:
        for c, d, w2 in reach:
            if c < b and a < d and not (c <= a and b <= d) and \
                    not (a <= c and d <= b):
                clashes.append((a, b, what, c, d, w2))
        reach = [r for r in reach if r[1] > a] + [(a, b, what)]
    return out, clashes

CHUNK = 0x10000          # one source file: 64 KB of cartridge
MIN_RUN = 4              # instructions a seed must decode before it is believed

VECTORS = [
    "initial_sp", "reset", "bus_error", "address_error", "illegal_instruction",
    "divide_by_zero", "chk_instruction", "trapv_instruction",
    "privilege_violation", "trace", "line_1010", "line_1111",
] + [f"reserved_{i}" for i in range(12, 24)] + [
    "spurious_interrupt",
] + [f"autovector_{i}" for i in range(1, 8)] + [
    "trap_0", "trap_1", "trap_2", "trap_3", "trap_4", "trap_5", "trap_6",
    "trap_7", "trap_8", "trap_9", "trap_10", "trap_11", "trap_12", "trap_13",
    "trap_14", "trap_15",
] + [f"unused_{i}" for i in range(48, 64)]

# The Mega Drive's hardware, by name.  The three interrupt autovectors that
# matter are 4 (horizontal), 6 (vertical) and 2 (external).
HARDWARE = {
    0xA00000: "Z80_RAM", 0xA04000: "Z80_YM2612", 0xA10000: "IO_VERSION",
    0xA10002: "IO_DATA1", 0xA10004: "IO_DATA2", 0xA10006: "IO_DATA3",
    0xA10008: "IO_CTRL1", 0xA1000A: "IO_CTRL2", 0xA1000C: "IO_CTRL3",
    0xA11100: "Z80_BUSREQ", 0xA11200: "Z80_RESET",
    0xC00000: "VDP_DATA", 0xC00002: "VDP_DATA_MIRROR",
    0xC00004: "VDP_CTRL", 0xC00006: "VDP_CTRL_MIRROR",
    0xC00008: "VDP_HV", 0xC00011: "VDP_PSG",
}


# ------------------------------------------------------------------ tracing
TRACE = ROOT / "orig/sega/res/trace.txt"


def load_trace(rom, path=TRACE):
    """What the running game did, as recorded by tools/sega/sega_touch.py.

    This is the one kind of knowledge the listing cannot get by reading:
    an instruction the machine executed is code, and a byte the machine
    read as data and never fetched as an instruction is not.  The file
    keeps a run of code as its first address and the number of
    instructions in it, and a run is contiguous, so decoding forwards from
    the first address has to come to exactly that many instructions and
    end exactly on the run's last byte - which is checked, because a
    decoder that disagreed with the machine would be worse than none.

    Returns `(starts, inner, forbid, reads)`: the instruction addresses;
    a bitmap of the bytes inside them after the first word, where no other
    instruction may begin; a bitmap of bytes that were read as data and
    never fetched; and the data runs as `(start, end, flags, reader)`.
    """
    n = len(rom)
    starts, inner, forbid, reads = set(), bytearray(n), bytearray(n), []
    if not path.exists():
        return starts, inner, forbid, reads
    fetched = bytearray(n)
    for line in path.read_text().splitlines():
        if not line or line[0] == "#":
            continue
        f = line.split()
        a, b = (int(x.strip("$"), 16) for x in f[1].split("-"))
        if f[0] == "C":
            want = int(f[2])
            if not want:
                continue            # the reset vectors, fetched as a long
            at, got = a, 0
            while at <= b:
                try:
                    ins = m68k.decode(rom, at, 0)
                except m68k.Fail as e:
                    raise SystemExit(f"trace.txt: the machine ran ${at:06X} "
                                     f"and the decoder cannot read it ({e})")
                starts.add(at)
                for k in range(1, ins.length):
                    inner[at + k] = 1
                at += ins.length
                got += 1
            if got != want:
                raise SystemExit(f"trace.txt: ${a:06X}-${b:06X} decodes to "
                                 f"{got} instructions, the machine ran {want}")
            for k in range(a, b + 1):
                fetched[k] = 1
        else:
            who = [int(w[1:], 16) for w in f[3].split(",") if w[0] == "$"]
            reads.append((a, b + 1, f[2], who))
    for a, b, _, _ in reads:
        for k in range(a, b):
            if not fetched[k] and not inner[k]:
                forbid[k] = 1
    return starts, inner, forbid, reads


def load_names(code, reserved):
    """The routines' names and what each does, from orig/sega/res/names/ -
    the format and the rules are sega_names.py's, and so is the check: a
    bad block stops the extraction and says which file and line.
    Returns {address: (name, {does, in, out, affects})}."""
    return sega_names.load(set(code), reserved)


def collect_longs(rom, run=3):
    """Addresses inside runs of longwords that all point into the ROM -
    the shape of a jump table."""
    out = set()
    i, n = 0, len(rom)
    while i + 4 <= n:
        j, seq = i, []
        while j + 4 <= n:
            v = int.from_bytes(rom[j:j + 4], "big")
            if not (0x200 <= v < n) or v & 1:
                break
            seq.append(v)
            j += 4
        if len(seq) >= run:
            out |= set(seq)
            i = j
        else:
            i += 4 if seq else 2
    return out


def collect_calls(rom):
    """Every absolute JSR/JMP operand, read off a blind sweep.  It
    over-collects on purpose; the trace throws back what does not decode."""
    out = set()
    for i in range(0, len(rom) - 6, 2):
        w = int.from_bytes(rom[i:i + 2], "big")
        if w in (0x4EB9, 0x4EF9):                  # jsr/jmp (xxx).l
            v = int.from_bytes(rom[i + 2:i + 6], "big")
            if 0x200 <= v < len(rom) and not v & 1:
                out.add(v)
    return out


def switch_tables(rom, cap=256):
    """`jmp TBL(pc,Xn.w)` - the 68000's switch, and the one branch the
    trace cannot follow, because where it goes is in a register.

    Both shapes a compiler emits are right there in the ROM, though, and
    both can be read exactly rather than guessed at.  The table always
    begins at the effective address the jmp itself names, which is the
    instruction's own displacement and nothing else:

      * a **table of word offsets** from the table's own start, so entry
        `k` sends the program to `TBL + w[k]`; and
      * a **ladder of `bra.s`**, two bytes a case, sometimes with an
        `rts` or a `nop` among them.

    Neither needs a length from anywhere: no case can jump backwards into
    the table, so the table ends at the lowest address any of its own
    entries names, and reading stops there.  That is what fixes the count
    - the `cmpi`/`bgt` guard in front of the jmp says the same thing, but
    it is not always there and this always is.

    One more thing says the same number a second time and is worth
    reading, because the lowest-target rule is off by an entry or two
    where the last case's code happens to start with an even small word:
    the **bound the compiler put in front of the jmp**.  A switch is
    always guarded, by `cmpi.l #N,Dn` and a `bgt` or by an `andi` mask,
    and the smaller of the two counts is the one to believe.  Three of
    this cartridge's tables read one entry too many without it, and one
    of those three claimed two bytes of the routine's own code.

    Returns `(jmp, start, end, kind, targets)` per table.  For the offset
    shape the region is data and the caller must keep the sweep out of it;
    for the branch shape it is code, and every slot has to be seeded on its
    own, since the trace stops dead at each `bra.s` it decodes.
    """
    out, n = [], len(rom)

    def word(a):
        return int.from_bytes(rom[a:a + 2], "big")

    def guard(a, reg, back=32):
        """How many cases the code in front of the jmp allows, or None.
        `cmpi #N,Dn` with a `bgt` behind it means 0..N, and an `andi`
        mask means 0..mask; the nearest one to the jmp is the live one."""
        best = None
        for b in range(max(0, a - back), a, 2):
            v, imm = word(b), None
            if v == 0x0C80 | reg:                      # cmpi.l #N,Dn
                imm = int.from_bytes(rom[b + 2:b + 6], "big")
            elif v in (0x0C40 | reg, 0x0240 | reg,     # cmpi.w / andi.w
                       0x0C00 | reg, 0x0200 | reg):    # cmpi.b / andi.b
                imm = word(b + 2)
            if imm is not None and 0 < imm < 0x1000:
                best = imm + 1
        return best

    for a in range(0, n - 4, 2):
        if word(a) not in (0x4EFB, 0x4EBB):        # jmp/jsr d(pc,Xn)
            continue
        ext = word(a + 2)
        # A brief extension word: bits 10-8 are zero on a 68000, and a
        # long index is a computed address rather than a table walk.
        if ext & 0x0F00:
            continue
        disp = ext & 0xFF
        if disp & 0x80:
            disp -= 0x100
        tbl = a + 2 + disp                          # pc is the ext word
        if tbl & 1 or not 0x200 <= tbl < n:
            continue
        head = word(tbl)
        if head >> 8 == 0x60 or head in (0x4E75, 0x4E71):
            slots, low, p = [], None, tbl
            most = cap if ext & 0x8000 else (guard(a, (ext >> 12) & 7)
                                             or cap)
            while len(slots) < most:
                if low is not None and p >= low:
                    break
                v = word(p)
                if v >> 8 == 0x60:                  # bra.s, forward only
                    d = v & 0xFF
                    if d in (0, 0xFF) or p + 2 + d >= n:
                        break
                    low = min(low, p + 2 + d) if low else p + 2 + d
                elif v not in (0x4E75, 0x4E71):     # rts and nop fill
                    break
                slots.append(p)
                p += 2
            if len(slots) >= 2:
                out.append((a, tbl, p, "bra", slots))
            continue
        most = cap if ext & 0x8000 else (guard(a, (ext >> 12) & 7) or cap)
        offs, low, p = [], None, tbl
        while len(offs) < most:
            if low is not None and p >= tbl + low:
                break
            o = word(p)
            if not o or o & 1 or o > 0x4000 or tbl + o >= n:
                break
            offs.append(o)
            low = min(low, o) if low else o
            p += 2
        # The lowest case cannot be inside the table itself; if it is,
        # these words are not offsets and the whole reading is wrong.
        if len(offs) >= 2 and low >= len(offs) * 2:
            out.append((a, tbl, p, "off", [tbl + o for o in offs]))
    return out


def pointer_runs(rom, least=4, skip=()):
    """Runs of longwords that all point into the cartridge.

    A 68000 game is held together by these: tables of subroutine
    addresses, of string addresses, of record addresses.  Writing them out
    as `dc.l label` instead of forty hex bytes is most of what makes the
    listing readable, and every address in one is somewhere the trace
    should try.

    Zero counts as an entry - a null slot in a table is ordinary - but the
    test has to be strict or it eats the artwork: four bytes of pixels are
    a small even number, which is a valid ROM address, so a picture reads
    as a table of pointers to the bottom of the cartridge.  A run must
    therefore be mostly non-zero, hold at least three different addresses,
    and none of them may be in the first kilobyte, which is the vector
    table and the header and nothing ever points there.

    `skip` keeps tables out of the stretches already known to be something
    else - the samples, the embedded files - where a false positive is
    both likely and useless.
    """
    lo = 0x400
    out, i, n = [], 0, len(rom) & ~3
    while i + 4 <= n:
        if any(a <= i < b for a, b, _ in skip):
            i = max(b for a, b, _ in skip if a <= i < b)
            continue
        j, seq = i, []
        while j + 4 <= n:
            v = int.from_bytes(rom[j:j + 4], "big")
            if v and not (lo <= v < n and not v & 1):
                break
            seq.append(v)
            j += 4
        real = [v for v in seq if v]
        if len(seq) >= least and len(set(real)) >= 3 and \
                len(real) * 2 >= len(seq):
            out.append((i, len(seq)))
            i = j
        else:
            i += 4 if seq else 2
    return out


# Stretches of the ROM this project has identified.  The listing prints a
# banner when it reaches one, so a reader landing in the middle of 200 KB
# of dc.b knows what they are looking at.
# The three script function tables, found by reading the calls to the
# script loader at $016C0E-$016C5A: it is handed a name, a place to put
# the script, and one of these.  The counts settle the reading - UNIT.EMC
# calls function indices up to 62 and its table has 64 entries, TEAM up to
# 13 with 15, BUILD up to 23 with 25.
SCRIPT_FUNCS = {
    "UNIT": (0x0FED20, 64),
    "TEAM": (0x0FECE4, 15),
    "BUILD": (0x06B998, 25),
}

NAMED = [
    (0x000000, 0x000100, "the 68000's exception table - see src/vectors.asm; "
                         "the boot's checksum reads $18E and $1A4 of the "
                         "header, $00285A the level-6 vector"),
    (0x000100, 0x000200, "the cartridge header - see src/header.asm"),
    (0x0046AE, 0x0046B0, "opens a file by name in the directory at $052C2C"),
    (0x016C0E, 0x016C64, "loads the three scripts: UNIT, TEAM and BUILD, "
                         "each with its own function table"),
    # $188A bytes, which is the length the uploader at $00152A computes
    # for itself, not a guess - and the two copies are byte-identical.
    (0x00294E, 0x0041D8, "the Z80 sound driver, uploaded to $A00000: "
                         "6282 bytes of Z80 code, not 68000 - see "
                         "res/sound/z80driver.asm"),
    (0x02C3FE, 0x02DC88, "the Z80 sound driver again - the second copy, "
                         "byte for byte"),
    # UNIT.EMC's FORM says $153A: it ends at $04F6BE, and what follows is
    # tiles and fonts, not script (sega_tables_hi.py).  This once ran on to
    # $0522A4, 11238 bytes too far.
    (0x04DB28, 0x04F6BE, "BUILD/PLAYER/TEAM/UNIT.EMC - Westwood script "
                         "bytecode: the units' and the computer's behaviour"),
    (0x052C2C, 0x052D58, "the file directory: pairs of (name, data) "
                         "pointers, 37 entries"),
    (0x052D58, 0x052F24, "the file names"),
    (0x052F24, 0x054074, "HOUSE.INI and PROFILE.INI, as text"),
    (0x054074, 0x056FA6, "REGION.INI and the three campaign maps, as text"),
    # SCENO009.INI is the last file and runs to its own $FFFF at $060E84;
    # this once stopped at $0609C8, 1212 bytes short.
    (0x056FA6, 0x060E84, "the 27 missions - see res/data/missions.txt"),
    (0x06AFA6, 0x06B94C, "the building table: 19 records of $66 bytes - "
                         "see res/data/buildings.txt"),
    (0x06BC00, 0x06C5B4, "the unit table: 27 records of $5C bytes - "
                         "see res/data/units.txt"),
    (0x06C750, 0x06C81C, "the house table: 6 records of $1E bytes - "
                         "see res/data/houses.txt"),
    (0x01B2E4, 0x01F340, "the mentat's prose: 111 strings, three house "
                         "descriptions and then four a mission - see "
                         "res/text/briefings.txt"),
    (0x087D74, 0x087F30, "111 pointers, one to each of the mentat's strings"),
    (0x06B94C, 0x06B998, "19 pointers, one to each building record"),
    (0x06B998, 0x06B9FC, "BUILD.EMC's function table: 25 routines the "
                         "structure scripts call"),
    (0x06C5B4, 0x06C620, "27 pointers, one to each unit record"),
    (0x0FECE4, 0x0FED20, "TEAM.EMC's function table: 15 routines"),
    (0x0FED20, 0x0FEE20, "UNIT.EMC's function table: 64 routines the unit "
                         "scripts call - see res/data/scripts/"),
    # The two sound banks, exactly: command $0B at $02DD14 and $02DCC8
    # hands the Z80 driver four pointers into each, and every byte from
    # the first to the last is spoken for.  res/sound/music.txt.
    (0x0C8104, 0x0C814C, "the front end's sample directory: 6 descriptors "
                         "of 12 bytes, indexed by note"),
    (0x0C814C, 0x0CF914, "the front end's 6 samples, end to end"),
    (0x0CF914, 0x0D01F5, "the front end's 13 songs: a directory of 16-bit "
                         "offsets, then a header a song and then the "
                         "tracks - see res/sound/music.txt"),
    (0x0D01F5, 0x0D0252, "the front end's 6 pitch envelopes"),
    (0x0D0252, 0x0D0663, "the front end's 46 instruments, 39 bytes read "
                         "into a voice's sound slot"),
    (0x0D0663, 0x0D078F, "the game's sample directory: 25 descriptors"),
    (0x0D078F, 0x0F6307, "the game's 25 samples, end to end"),
    (0x0F6307, 0x0FE129, "the game's 84 songs - see res/sound/music.txt"),
    (0x0FE129, 0x0FE25A, "the game's 10 pitch envelopes"),
    (0x0FE25A, 0x0FECE4, "the game's 105 instruments"),
    (0x0FEE80, 0x100000, "$FF to the end of the cartridge: 4480 bytes of "
                         "nothing"),
    # 256 records of 26 bytes, and the size byte of every one of the 512
    # pieces agrees with the width and height beside it - 8, 16, 24 or 32
    # pixels each way, which is exactly what the VDP's two-bit fields say.
    (0x02EC72, 0x030674, "256 sprite frames: a count word and two pieces of "
                         "12 bytes - width, height (a box to clip by), y, the "
                         "VDP's size and link bytes, its attribute word, x"),
    # Their order is not the song numbering.  The options screen's music
    # and sound tests ($087F3C, $087FD4) point at them in (name, song)
    # pairs, and that is what joins a name to a song.
    (0x020870, 0x020C10, "the game's 58 sound names, 16 bytes each: "
                         "eighteen tunes and then the effects and the "
                         "speech, in an order that is not the song "
                         "numbering - the music and sound tests at "
                         "$087F3C and $087FD4 pair each with its song; "
                         "see res/sound/music.txt"),
    # These were once taken for the names of the PC game's music files.
    # They are the passwords: $08811C points at every one of them and the
    # checker at $0218FE compares against them - res/data/passwords.txt.
    (0x020C10, 0x020D4F, "the 29 passwords, ten letters and a NUL each - "
                         "see res/data/passwords.txt"),
    (0x08811C, 0x088208, "the password table: a pointer to the word, its "
                         "kind and its value, 29 of them and a null - read "
                         "by $0218FE"),
    (0x08820C, 0x08828C, "a whole palette, 64 colours: $021B74 hands it "
                         "to $000F56, which copies it to the shadow at "
                         "$FFE2B4 and sends it to CRAM"),
    (0x020D4F, 0x020DA1, "the options screen's words"),
    (0x0A68CA, 0x0A68DA, "seven score thresholds and $FFFF - the ranks "
                         "below are earned at them"),
    (0x0A68DA, 0x0A6973, "the nine ranks, 17 bytes each, centred with "
                         "spaces: Sand Snake to Ruler of Arrakis"),
    (0x0A6974, 0x0A6990, "the three house names, 9 bytes each, centred"),
]


def plausible(rom, pos):
    n = 0
    while n < MIN_RUN:
        try:
            ins = m68k.decode(rom, pos, 0)
        except m68k.Fail:
            return False
        if not m68k.roundtrips(ins):
            return False
        n += 1
        if ins.flow in ("stop", "jump"):
            return True
        pos += ins.length
    return True


def trace(rom, seeds, code, forbid=None, inner=None, name_seeds=True):
    """Recursive descent.  Fills `code` in place; returns the labels.

    `forbid` is the bytes the running game read as data and never fetched,
    and `inner` the bytes inside instructions it did execute: no
    instruction may cover the first or begin on the second, whatever the
    decoder thinks of them.

    `name_seeds` is False for the instructions the machine ran: they are
    code, but most of them are the middle of a routine, and only what
    something branches to deserves a label.
    """
    labels = set()
    todo, seen = list(seeds), set()
    while todo:
        at = todo.pop()
        if at in seen or at & 1 or not (0 <= at < len(rom)):
            continue
        seen.add(at)
        if at in code or not plausible(rom, at):
            continue
        if inner is not None and inner[at]:
            continue
        # a seed is named only if an instruction is placed there: a
        # pointer-shaped longword that lands in data names nothing
        head = at
        while 0 <= at < len(rom):
            if at in code:
                break
            if inner is not None and inner[at]:
                break
            try:
                ins = m68k.decode(rom, at, 0)
            except m68k.Fail:
                break
            if not m68k.roundtrips(ins):
                break
            if forbid is not None and any(
                    forbid[at + k] for k in range(ins.length)
                    if at + k < len(forbid)):
                break
            if any(at + k in code for k in range(2, ins.length, 2)):
                break
            code[at] = ins
            if at == head and name_seeds:
                labels.add(at)
            if ins.target is not None and 0 <= ins.target < len(rom):
                labels.add(ins.target)
                todo.append(ins.target)
            if ins.flow in ("stop", "jump"):
                break
            at += ins.length
    return labels


def animation_table(rom, at=0x060E84):
    """The table at $060E84, and the two things every entry of it names.

    The code reads it twice, at $004B7A and $004BB2, and both say the same
    thing in the same four instructions:

        lsl.w   #$3,d0             ; the record is eight bytes
        lea     $60E84.l,a1
        adda.l  d0,a1
        move.l  $4(a1),$8(a0)      ; the second long, tag and all
        move.l  (a1),d0
        andi.l  #$FFFFFF,d0        ; the first, masked to an address
        move.l  d0,$FFBF04.l       ; where the graphics are read from

    So a record is two tagged 24-bit addresses: the pixels, and a list
    that goes into the sprite record whole.  A slot that is not used is
    $00000000/$FFFFFFFF.

    Nothing says how many records there are - and nothing has to.  Read
    forwards while both halves are addresses inside the cartridge and it
    stops after 357 of them, at $0619AC; and $0619AC is the lowest address
    any of those 357 records points at.  The table ends exactly where the
    first thing it names begins, which is not a coincidence a wrong length
    could produce.

    Returns `(start, end, first_targets, second_targets)`.
    """
    n, k, first, second = len(rom), 0, set(), set()

    def long(a):
        return int.from_bytes(rom[a:a + 4], "big")

    while at + 8 * k + 8 <= n:
        x, y = long(at + 8 * k), long(at + 8 * k + 4)
        if x == 0 and y == 0xFFFFFFFF:                 # an unused slot
            k += 1
            continue
        if not (0x200 <= (x & 0xFFFFFF) < n and 0x200 <= (y & 0xFFFFFF) < n):
            break
        first.add(x & 0xFFFFFF)
        second.add(y & 0xFFFFFF)
        k += 1
    end = at + 8 * k
    if not first or min(first) != end:
        return None
    return at, end, first, second


def pointed_at(rom, code, free, extra=()):
    """Data nothing has identified, but that something points *at*.

    `lea $6.0E84.l,a1` is not a guess: the trace decoded that instruction,
    and the address it builds is a table the program reads.  Knowing who
    reads a block is not the same as knowing what is in it, and the banner
    says so - but it turns 40 KB of anonymous `dc.b` into blocks with a
    caller, which is where anyone reading further would have to start.

    `extra` is for addresses that are not built by an instruction but by a
    table the code indexes - the animation table above - which is the same
    claim and deserves the same treatment.

    A block runs from the address to the next thing that is already
    accounted for, or to the next address anything else points at.
    """
    want = {}
    for v, who in extra:
        if 0x200 <= v < len(rom) and free[v]:
            want.setdefault(v, []).append(who)
    for a, ins in code.items():
        w = int.from_bytes(rom[a:a + 2], "big")
        if (w & 0xF1FF) in (0x41F9, 0x2079, 0x207C) or w == 0x4879:
            if ins.length < 6:
                continue
            v = int.from_bytes(rom[a + 2:a + 6], "big")
            if 0x200 <= v < len(rom) and free[v]:
                want.setdefault(v, []).append(a)
    out = []
    for v in sorted(want):
        end = v
        while end < len(rom) and free[end] and (end == v or end not in want):
            end += 1
        if end - v < 8:
            continue
        who = sorted(want[v], key=lambda x: (isinstance(x, str), x))
        lead = who[0]
        out.append((v, end,
                    (lead if isinstance(lead, str)
                     else f"data the code at ${lead:06X} points at")
                    + (f" (and {len(who) - 1} more)" if len(who) > 1 else "")
                    + " - what is in it is not identified"))
    return out


def read_regions(reads, free):
    """Bytes nothing has named that the running game read, one region a
    stretch of them that nothing else interrupts.  Like pointed_at(), a
    place and its readers rather than a meaning - but a measured one: the
    machine read these, and from there.  A table two instructions read
    alternately is still one table, so neighbouring runs are joined and
    every reader is named."""
    runs = []
    for a, b, flags, who in sorted(reads):
        k = a
        while k < b:
            if not free[k]:
                k += 1
                continue
            e = k
            while e < b and free[e]:
                e += 1
            if runs and runs[-1][1] == k:
                runs[-1][1] = e
                runs[-1][2].add(flags)
                runs[-1][3].update(who)
            else:
                runs.append([k, e, {flags}, set(who)])
            k = e
    out = []
    for a, b, flags, who in runs:
        fl = "".join(sorted(set("".join(flags))))
        by = sorted(who)
        names = ", ".join(f"${w:06X}" for w in by[:4]) + \
            (f" and {len(by) - 4} more" if len(by) > 4 else "")
        if "c" in fl:
            what = "colours, sent to CRAM by DMA"
        elif "s" in fl:
            what = "sent to the vertical scroll RAM by DMA"
        elif "v" in fl:
            what = "sent to VRAM by DMA"
        elif "z" in fl and "d" not in fl:
            what = "read by the Z80 through its window onto the cartridge"
        else:
            what = "data the game was seen to read"
        if by:
            what += f" (started or read by {names})"
        out.append((a, b, what + " - what is in it is not identified"))
    return out


def gap_sweep(rom, code, spoken_for=None):
    """What the trace never reached, read forwards, keeping any run that
    decodes cleanly all the way to a return.

    `spoken_for` is a bitmap of the bytes some named region already
    accounts for, and the sweep must not cross it.  Without that it reads
    pictures as instructions: a Format80 stream beginning `81 00` decodes
    happily as `sbcd.b d0,d0`, and five such lines in a row are all this
    needs to call a picture code.
    """
    found, labels = {}, set()
    at, n = 0, len(rom)
    while at < n:
        if spoken_for is not None and spoken_for[at]:
            at += 1
            continue
        if at in code or at in found:
            ins = code.get(at) or found.get(at)
            at += ins.length if ins else 2
            continue
        run, pos, ok = {}, at, False
        while pos < n and pos - at < 512:
            if pos in code or pos in found:
                break
            if spoken_for is not None and spoken_for[pos]:
                break
            try:
                ins = m68k.decode(rom, pos, 0)
            except m68k.Fail:
                break
            if not m68k.roundtrips(ins):
                break
            run[pos] = ins
            pos += ins.length
            if ins.flow in ("stop", "jump"):
                ok = len(run) >= 5
                break
        if ok:
            found.update(run)
            labels.add(at)
            at = pos
        else:
            at += 2
    return found, labels


def stub_sweep(rom, code, named):
    """The last few bytes between two routines that nothing reaches.

    What is left once the trace, the modules and the sweep are done is
    mostly a lone `rts`, a `moveq #0,d0; rts`, or the head of a routine
    that falls into code the trace did find - too short for gap_sweep()'s
    five instructions.  A run counts only if it decodes, instruction by
    instruction, to exactly its own last byte, and then either stops
    (return, jump, branch) or runs straight on into an instruction already
    known.  A run of zeros is never a stub: `ori.b #0,d0` is what padding
    looks like decoded.
    """
    taken = bytearray(len(rom))
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            taken[i] = 1
    for a, ins in code.items():
        for k in range(ins.length):
            taken[a + k] = 1
    out, at, n = {}, 0x200, len(rom)
    while at < n:
        if taken[at]:
            at += 1
            continue
        end = at
        while end < n and not taken[end]:
            end += 1
        run, pos, last = {}, at, None
        # zero words in front are padding, and the stub starts after them
        while pos + 2 <= end and not rom[pos] and not rom[pos + 1]:
            pos += 2
        if any(rom[pos:end]) and not pos & 1:
            while pos < end:
                try:
                    ins = m68k.decode(rom, pos, 0)
                except m68k.Fail:
                    break
                if not m68k.roundtrips(ins) or pos + ins.length > end:
                    break
                run[pos], last = ins, ins
                pos += ins.length
        if run and pos == end and (last.flow in ("stop", "jump")
                                   or end in code):
            out.update(run)
        at = end
    return out


def padding(rom, code, stubs, named):
    """What is left: runs of one repeated byte - zeros after a stream of
    odd length or between two routines, $FF where a table was cut short -
    that nothing names, reads or runs."""
    taken = bytearray(len(rom))
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            taken[i] = 1
    for c in (code, stubs):
        for a, ins in c.items():
            for k in range(ins.length):
                taken[a + k] = 1
    out, at = [], 0x200
    while at < len(rom):
        if taken[at]:
            at += 1
            continue
        end = at
        while end < len(rom) and not taken[end]:
            end += 1
        if len(set(rom[at:end])) == 1:
            v = rom[at]
            out.append((at, end, f"{end - at} byte{'s' if end - at > 1 else ''}"
                        f" of ${v:02X} that nothing names, reads or runs - "
                        + ("padding to an even address" if end - at == 1 and
                           end % 2 == 0 else "padding")))
        at = end
    return out


def stub_heads(stubs):
    """The first instruction of each run stub_sweep() found."""
    ends = {a + i.length for a, i in stubs.items()}
    return {a for a in stubs if a not in ends}


def align_labels(rom, code, labels, measured=frozenset()):
    """A label inside an instruction the trace placed means the trace was
    wrong about one of them; the instruction gives way so the source can
    still name the address.

    Unless the machine ran that instruction.  Then the label is what is
    wrong - something read as code that was not, pointing where it
    pleased - and it is the label that goes; anything that still aims
    there is written with the number instead.
    """
    for at in measured:
        ins = code.get(at)
        if ins:
            for k in range(1, ins.length):
                labels.discard(at + k)
    changed = True
    while changed:
        changed = False
        inside = {}
        for at, ins in code.items():
            for k in range(2, ins.length, 2):
                inside[at + k] = at
        for a in labels:
            if a in inside:
                del code[inside[a]]
                changed = True
                break


# ------------------------------------------------------------------- output
PRINTABLE = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
                b"0123456789 .,:;!?'-&()/*+=@#$%[]<>_")


def ascii_run(buf, least=5):
    n = 0
    while n < len(buf) and buf[n] in PRINTABLE and buf[n] != 0x22:
        n += 1
    if n < least:
        return 0
    run = buf[:n]
    letters = sum(1 for b in run if 0x41 <= (b | 0x20) <= 0x7A)
    if letters < 3 or letters * 2 < n or len(set(run)) < 4:
        return 0
    return n


def emit(rom, start, end, code, labels, swept, syms, title, pointers=(),
         named=(), words=(), notes=None):
    out = [f"; {title}",
           ";",
           "; Written by tools/sega/sega_extract.py.  Instructions are where",
           "; the trace reached and every one of them was re-assembled before",
           "; it was written; dc.b is everything else - data, or code whose",
           "; entry point has not been found.  Rebuilt by",
           "; tools/sega/build_sega.py, which checks the whole cartridge",
           "; against the original's SHA-256.",
           "",
           '.include "megadrive.inc"',
           "",
           f".org ${start:06X}",
           ""]
    pending = bytearray()
    pend_at = start
    ptr = {a: n for a, n in pointers if start <= a < end}
    wtbl = {a: v for a, v in words.items() if start <= a < end}
    banners = {a: (b, what) for a, b, what in named if start <= a < end}

    def flush():
        nonlocal pending, pend_at
        while pending:
            n = ascii_run(pending)
            if n:
                out.append('        dc.b    "%s"' % pending[:n].decode("ascii"))
                pending = pending[n:]
                pend_at += n
                continue
            same = 1
            while same < len(pending) and pending[same] == pending[0]:
                same += 1
            if same >= 64:
                out.append(f"        .res    {same},${pending[0]:02X}")
                pending = pending[same:]
                pend_at += same
                continue
            take = min(16, len(pending))
            for i in range(1, take):
                if ascii_run(pending[i:]):
                    take = i
                    break
            chunk, pending = pending[:take], pending[take:]
            gutter = "".join(chr(b) if b in PRINTABLE else "." for b in chunk)
            line = "        dc.b    " + ",".join(f"${b:02X}" for b in chunk)
            out.append(f"{line:<86}; {pend_at:06X}  {gutter}")
            pend_at += take

    at = start
    prev_at = prev_end = None
    while at < end:
        if at in banners:
            flush()
            b, what = banners[at]
            out.append("")
            out.append(f"; ==== ${at:06X}-${b - 1:06X}: {what}")
            out.append("")
        if notes and at in notes:
            flush()
            name, fields = notes[at]
            out += ["", "; " + "-" * 72, f"; {name}"]
            for key in ("does", "in", "out", "affects"):
                for k, part in enumerate(textwrap.wrap(fields[key], 62)):
                    out.append(f";   {key + ':' if k == 0 else '':<9}{part}")
            out.append("; " + "-" * 72)
        if at in labels:
            flush()
            out.append(f"{syms[at]}:")
        if at in wtbl and at not in code:
            flush()
            stop, entries = wtbl[at]
            for k, t in enumerate(entries):
                here = at + k * 2
                # something else may name a word of the table - a pointer
                # run that lands in it, say.  The label still has to be
                # written or the source will not assemble.
                if k and here in labels:
                    out.append(f"{syms[here]}:")
                v = int.from_bytes(rom[here:here + 2], "big")
                name = syms.get(t, f"${t:06X}")
                out.append(f"        dc.w    ${v:04X}"
                           f"{'':<20}; {here:06X}  -> {name}")
            at = stop
            continue
        if at in ptr and at not in code:
            flush()
            n = ptr[at]
            out.append(f"; ---- a table of {n} pointers")
            for k in range(n):
                v = int.from_bytes(rom[at + k * 4:at + k * 4 + 4], "big")
                name = syms.get(v) if v else None
                body = name if name else f"${v:06X}"
                out.append(f"        dc.l    {body:<24}; ${at + k * 4:06X}")
            at += n * 4
            continue
        ins = code.get(at)
        if ins is None:
            if not pending:
                pend_at = at
            pending.append(rom[at])
            at += 1
            continue
        flush()
        if at in swept and (prev_end != at or prev_at not in swept):
            out.append("; ----- nothing calls this and the running game "
                       "never ran it: found by reading forwards")
        prev_at, prev_end = at, at + ins.length
        body = m68k.text(ins, syms)
        raw = "".join(f"{w:04X} " for w in ins.words).strip()
        head, _, rest = body.partition(" ")
        # a short absolute call cannot carry a symbol, so say where it goes
        t = ins.target
        also = (f"  -> {syms[t]}" if notes and t in notes and t in syms
                and syms[t] not in body else "")
        out.append(f"        {head:<8}{rest:<40}; {at:06X}  {raw}{also}")
        at += ins.length
    flush()
    out += ["", f".assert-size {end - start}", ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    (out / "src").mkdir(parents=True, exist_ok=True)

    vecs = [int.from_bytes(rom[i * 4:i * 4 + 4], "big") for i in range(64)]

    # Where the pictures are.  tools/sega/sega_gfx.py knows, because it
    # unpacks them and its decompressor reports how much of the input each
    # stream ate; without that the listing would go on calling half the
    # cartridge anonymous data long after the art had been read out of it.
    print("finding the art...", flush=True)
    extra, extra_code = identified(rom)
    named, clashes = merge_regions(NAMED + art_regions(rom) + map_regions(rom),
                                   extra)
    if clashes:
        print(f"  {len(clashes)} regions overlap without one holding the "
              "other - see tmp/sega/clashes.txt", flush=True)
        c = ROOT / "tmp/sega/clashes.txt"
        c.parent.mkdir(parents=True, exist_ok=True)
        c.write_text("".join(f"${a:06X}-${b:06X} {w}\n  ${x:06X}-${y:06X} "
                             f"{w2}\n" for a, b, w, x, y, w2 in clashes))

    print("tracing...", flush=True)
    code = {}
    seeds = {v for v in vecs[1:] if 0x200 <= v < len(rom) and not v & 1}
    seeds |= collect_calls(rom)
    measured, inner, forbid, reads = load_trace(rom)
    ptables = pointer_runs(rom, skip=named)
    # Twelve bytes of `bge.w; addq.w; bra.w` can look like three longwords
    # that point into the cartridge.  A run the machine executed is not a
    # table, whatever it looks like.
    ptables = [(a, n) for a, n in ptables
               if not any(k in measured or inner[k]
                          for k in range(a, a + 4 * n))]
    # Everything the scripts can call is code, whether or not anything in
    # the 68000 names it: the interpreter reaches it through the table.
    script_fns = set()
    for a, n in SCRIPT_FUNCS.values():
        for k in range(n):
            v = int.from_bytes(rom[a + k * 4:a + k * 4 + 4], "big")
            if 0x200 <= v < len(rom) and not v & 1:
                script_fns.add(v)
    # The switch tables.  A `jmp TBL(pc,Xn.w)` is a hole in the trace -
    # the case number is in a register - but the table it reads is not,
    # and every case it can reach is an entry point the trace would
    # otherwise never be given.
    switches = switch_tables(rom)
    switch_seeds = set()
    for _, tbl, _, kind, entries in switches:
        switch_seeds |= set(entries)
        if kind == "bra":
            # each slot is one instruction and the trace stops at every
            # one of them, so each has to be a seed in its own right
            for at in entries:
                v = int.from_bytes(rom[at:at + 2], "big")
                if v >> 8 == 0x60:
                    switch_seeds.add(at + 2 + (v & 0xFF))
    # What the machine itself ran goes in first, so nothing a guess finds
    # can take its place - and nothing a guess finds may cover a byte the
    # machine only ever read, or begin inside an instruction it ran.
    # A named region is data, and no guess may decode it as code - only
    # the machine can say otherwise, by running it (the two NAMED banners
    # over routines, $0046AE and $016C0E, are exactly that).  Without this
    # the pointer-shaped seeds walk into portraits and palettes.
    fetched = bytearray(len(rom))
    for at in measured:
        fetched[at] = 1
    for i in range(len(rom)):
        if inner[i]:
            fetched[i] = 1
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            if not fetched[i]:
                forbid[i] = 1
    labels = trace(rom, measured, code, forbid, inner, name_seeds=False)
    # the routines the reading modules found and nothing calls
    labels |= trace(rom, {a for a, _ in extra_code}, code, forbid, inner)
    # Everything so far is certain: what the machine ran, what follows from
    # it by the program's own flow, and what the modules decoded and
    # checked.  A label a later guess puts inside one of these is the guess
    # being wrong, not the instruction.
    certain = set(code)
    labels |= trace(rom, seeds | script_fns | switch_seeds, code,
                    forbid, inner)
    labels |= trace(rom, collect_longs(rom), code, forbid, inner)
    # every entry of every pointer table is somewhere worth trying
    ptr_targets = set()
    for a, n in ptables:
        for k in range(n):
            v = int.from_bytes(rom[a + k * 4:a + k * 4 + 4], "big")
            if v:
                ptr_targets.add(v)
    labels |= trace(rom, ptr_targets, code, forbid, inner)
    # a pointer table is data; the sweep must not read one as code
    for a, n in ptables:
        for k in range(0, n * 4, 2):
            code.pop(a + k, None)
    # and neither is a switch's offset table, which sits in the middle of
    # the routine it belongs to and would otherwise be read as instructions
    wtables = {}
    for _, tbl, end, kind, entries in switches:
        if kind != "off":
            continue
        for k in range(tbl, end, 2):
            code.pop(k, None)
        wtables[tbl] = (end, entries)
    anim0 = animation_table(rom)
    if anim0:
        named.append((anim0[0], anim0[1],
                      f"the animation table: {(anim0[1] - anim0[0]) // 8} "
                      "records of two tagged addresses - the pixels and the "
                      "list that goes with them; read at $004B7A and $004BB2"))
    named = sorted(named + [
        (tbl, end, f"a switch: {(end - tbl) // 2} word offsets from here, "
                   f"for the jmp at ${jmp:06X}")
        for jmp, tbl, end, kind, _ in switches if kind == "off"])
    spoken_for = bytearray(len(rom))
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            spoken_for[i] = 1
    for i in range(len(rom)):
        if forbid[i] or inner[i]:
            spoken_for[i] = 1
    swept, sweptlab = gap_sweep(rom, code, spoken_for)
    code.update(swept)
    labels |= sweptlab
    # every target of every instruction has to be a label, including the
    # ones the sweep found: an assembler cannot branch to an address that
    # nothing names
    labels |= {i.target for i in code.values()
               if i.target is not None and 0 <= i.target < len(rom)}
    labels = {a for a in labels if 0x200 <= a < len(rom)}
    align_labels(rom, code, labels, certain)
    swept = {a for a in swept if a in code}
    # Two instructions over the same bytes: the sweep began inside one the
    # program's flow reaches ($004FFE, $0067EA, $009AFE, $010016 once).
    # The certain one stays; of two guesses, the earlier.
    ks = sorted(code)
    keep_end = -1
    for x in ks:
        if x < keep_end:
            prev = max(k for k in ks if k < x and k in code)
            loser = prev if (x in certain and prev not in certain) else x
            code.pop(loser, None)
            swept.discard(loser)
            if loser == prev:
                keep_end = x + code[x].length
            continue
        keep_end = x + code[x].length
    stubs = stub_sweep(rom, code, named)
    named = sorted(named + padding(rom, code, stubs, named))
    code.update(stubs)
    swept |= set(stubs)
    labels |= stub_heads(stubs)
    labels |= {i.target for i in stubs.values()
               if i.target is not None and 0x200 <= i.target < len(rom)}
    align_labels(rom, code, labels, certain)

    # Anything still unclaimed that is shaped like pixels.  Only the gaps
    # are searched, so this cannot swallow code the trace found; and it is
    # labelled as unconfirmed, because looking like a tile is not the same
    # as being one - see raw_tile_runs().
    free = bytearray(b"\x01" * len(rom))
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            free[i] = 0
    for a, ins in code.items():
        for k in range(ins.length):
            if a + k < len(rom):
                free[a + k] = 0
    named = sorted(named + raw_tile_runs(rom, free))
    # anything still nobody's that an instruction nevertheless points at
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            free[i] = 0
    anim = animation_table(rom)
    extra = []
    if anim:
        _, _, first, second = anim
        extra = ([(v, "pixels the animation table at $060E84 names")
                  for v in sorted(first)]
                 + [(v, "a list the animation table at $060E84 names")
                    for v in sorted(second)])
    pointed = pointed_at(rom, code, free, extra)
    named = sorted(named + pointed)
    # and anything still nobody's that the running game was seen to read
    for a, b, _ in pointed:
        for i in range(a, b):
            free[i] = 0
    seen = read_regions(reads, free)
    named = sorted(named + seen)
    pointed = pointed + seen

    # A candidate table earns the name only if the trace found something at
    # the other end of it.  Four bytes of artwork are a small even number
    # and so a valid ROM address; two of them landing on an instruction the
    # trace independently reached is not luck.
    kept = []
    for a, n in ptables:
        real, hit = 0, set()
        for k in range(n):
            v = int.from_bytes(rom[a + k * 4:a + k * 4 + 4], "big")
            if not v:
                continue
            real += 1
            if (v in code or v in labels) and v & 0xFFFF:
                hit.add(v)
        # Code is a seventh of this cartridge, so a couple of chance hits
        # in a long run mean nothing; most of a real table lands on
        # something, and three different somethings is past coincidence.
        # A target on a 64 KB boundary does not count: those are where the
        # chunks start, so they are always code, and artwork is full of
        # $00010000.
        if len(hit) >= 3 and len(hit) * 2 >= real:
            kept.append((a, n))
    ptables = kept

    # A table has to break wherever something names an address inside it,
    # or the label has nowhere to be written and the source will not
    # assemble.  Splitting is safe: two shorter tables are still tables.
    split = []
    for a, n in ptables:
        cur = []
        for k in range(n):
            here = a + k * 4
            if here in labels and cur:
                if len(cur) >= 2:
                    split.append((cur[0], len(cur)))
                cur = []
            if here + 2 in labels:
                # something names the middle of this longword, so it is not
                # a pointer - end the run and leave this entry as bytes
                if len(cur) >= 2:
                    split.append((cur[0], len(cur)))
                cur = []
                continue
            cur.append(here)
        if len(cur) >= 2:
            split.append((cur[0], len(cur)))
    ptables = split

    syms = {a: f"L_{a:06X}" for a in labels}
    for i, v in enumerate(vecs):
        if i and 0x200 <= v < len(rom):
            syms.setdefault(v, VECTORS[i] if i < len(VECTORS) else f"vec_{i}")
    syms[vecs[1]] = "reset"
    syms.update(HARDWARE)
    names = load_names(code, set(HARDWARE.values()) | set(VECTORS)
                       | {"reset"})
    for a, (name, _) in names.items():
        syms[a] = name
    labels |= {a for a in syms if 0x200 <= a < len(rom)}

    # ---- the exception table
    lines = ["; vectors.asm - the 68000 exception table.",
             ";",
             "; The first two longs are what the processor loads before it",
             "; runs anything at all: the initial stack pointer and the",
             "; address of the first instruction.  Everything after them is",
             "; where the machine goes when something happens - a bus error,",
             "; a TRAP, or the VDP's line and frame interrupts, which are",
             "; autovectors 4 and 6 and the two this game actually uses.",
             "",
             ".org $000000",
             ""]
    for i, v in enumerate(vecs):
        name = VECTORS[i] if i < len(VECTORS) else f"vec_{i}"
        target = syms.get(v, f"${v:06X}") if i else f"${v:08X}"
        lines.append(f"        dc.l    {target:<24}; {i:2d}  {name}")
    lines += ["", ".assert-size 256", ""]
    (out / "src/vectors.asm").write_text("\n".join(lines) + "\n")

    # ---- the header
    h = rom[0x100:0x200]

    def field(a, b, label):
        return (f'        dc.b    "{h[a:b].decode("latin1")}"'.ljust(60)
                + f"; ${0x100 + a:04X}  {label}")

    hdr = ["; header.asm - the Mega Drive cartridge header.",
           ";",
           "; The console reads none of this: it is for the licensee, the",
           "; region lockout and the loader.  The one field with teeth is the",
           "; checksum at $18E, which some cartridges check themselves - this",
           "; one does not, but build_sega.py reproduces it anyway because",
           "; the rebuild has to be the original byte for byte.",
           "",
           ".org $000100",
           "",
           field(0x00, 0x10, "console"),
           field(0x10, 0x20, "copyright and date"),
           field(0x20, 0x50, "domestic name"),
           field(0x50, 0x80, "international name"),
           field(0x80, 0x8E, "serial"),
           f"        dc.w    ${int.from_bytes(h[0x8E:0x90], 'big'):04X}"
           .ljust(60) + "; $018E  checksum",
           field(0x90, 0xA0, "the devices it takes"),
           f"        dc.l    ${int.from_bytes(h[0xA0:0xA4], 'big'):08X},"
           f"${int.from_bytes(h[0xA4:0xA8], 'big'):08X}".ljust(60)
           + "; $01A0  ROM start and end",
           f"        dc.l    ${int.from_bytes(h[0xA8:0xAC], 'big'):08X},"
           f"${int.from_bytes(h[0xAC:0xB0], 'big'):08X}".ljust(60)
           + "; $01A8  RAM start and end",
           "        dc.b    " + ",".join(f"${b:02X}" for b in h[0xB0:0xBC])
           + "   ; $01B0  save-RAM description",
           field(0xBC, 0xC8, "modem"),
           field(0xC8, 0xF0, "notes"),
           field(0xF0, 0x100, "regions"),
           "",
           ".assert-size 256",
           ""]
    (out / "src/header.asm").write_text("\n".join(hdr) + "\n")

    inc = ["; megadrive.inc - the addresses the disassembly names.",
           ";",
           "; The VDP's two ports at $C00000 and $C00004 are the whole of its",
           "; interface: a command written to the control port says which of",
           "; VRAM, CRAM and VSRAM the next data-port access lands in.  The",
           "; Z80 has to be stopped through $A11100 before the 68000 may",
           "; touch its RAM at $A00000.",
           ""]
    for a in sorted(HARDWARE):
        inc.append(f"{HARDWARE[a]:<18} = ${a:06X}")
    inc.append("")
    (out / "src/megadrive.inc").write_text("\n".join(inc))

    # ---- the cartridge itself
    regions = [{"kind": "vectors", "src": "src/vectors.asm",
                "start": 0, "size": 256},
               {"kind": "header", "src": "src/header.asm",
                "start": 0x100, "size": 256}]
    stats = []
    # the first chunk starts after the vectors and the header, so the
    # boundaries are 64 KB apart from zero rather than from $200
    starts = [0x200] + list(range(CHUNK, len(rom), CHUNK))
    for start in starts:
        end = min(start - start % CHUNK + CHUNK, len(rom))
        name = f"rom{start // CHUNK:02X}.asm"
        title = (f"${start:06X}-${end - 1:06X} of the cartridge"
                 + (" - the reset address is at the top" if start == 0x200
                    else ""))
        src = emit(rom, start, end, code, labels, swept, syms, title,
                   ptables, named, wtables, names)
        (out / "src" / name).write_text(src)
        cb = sum(i.length for a, i in code.items() if start <= a < end)
        regions.append({"kind": "code", "src": f"src/{name}", "start": start,
                        "size": end - start, "code_bytes": cb})
        stats.append((name, cb, end - start))

    manifest = {
        "rom": Path(args.rom).name,
        "sha256": hashlib.sha256(rom).hexdigest(),
        "size": len(rom),
        "regions": regions,
    }
    (out / "rom.map").write_text(json.dumps(manifest, indent=2) + "\n")

    tot_code = sum(c for _, c, _ in stats)
    tot = sum(t for _, _, t in stats)
    cov = bytearray(len(rom))
    for a, b, _ in named:
        for i in range(max(0, a), min(b, len(rom))):
            cov[i] = 1
    # named data is what is named and not code: the two banners over
    # routines ($0046AE, $016C0E) name instructions, and the exception
    # table and header below $200 are not part of the 64 KB chunks counted
    for a, ins in code.items():
        for k in range(ins.length):
            if a + k < len(cov):
                cov[a + k] = 0
    known = sum(cov[0x200:])
    rest = tot - tot_code - known
    # `pointed` is a weaker claim than the rest and is counted apart: it
    # says an instruction builds this address, not what the bytes mean.
    weak = sum(b - a for a, b, _ in pointed)

    # What is still nobody's: neither traced as an instruction nor inside
    # a named region.  Written out because the next thing to chase is
    # always the biggest of these, and guessing which that is has been
    # wrong twice.
    free = bytearray(cov)
    for a, ins in code.items():
        for k in range(ins.length):
            if a + k < len(free):
                free[a + k] = 1
    runs, start = [], None
    for i in range(0x200, len(rom)):
        if not free[i] and start is None:
            start = i
        elif free[i] and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(rom)))
    big = sorted(runs, key=lambda r: r[1] - r[0], reverse=True)
    G = ["# gaps.txt - every byte of the cartridge that is still neither",
         "# an instruction the trace reached nor part of a named region.",
         "#",
         "# Written by tools/sega/sega_extract.py.  Largest first; the",
         "# tail of one-byte alignment gaps is left out.",
         "",
         f"# {len(runs)} runs, {sum(b - a for a, b in runs)} bytes",
         ""]
    for a, b in big:
        if b - a < 16:
            break
        G.append(f"  ${a:06X}-${b - 1:06X}  {b - a:7d}")
    (out / "gaps.txt").write_text("\n".join(G) + "\n")

    # Every named region, in address order, with what it is claimed to
    # be.  gaps.txt says what nobody has named; this says what the names
    # are, and so which of them are only a place ("points at") and not
    # yet a meaning.
    R = ["# regions.txt - every named region of the cartridge, in order.",
         "#",
         "# Written by tools/sega/sega_extract.py.  A region whose",
         "# description ends 'not identified' is only pointed at.",
         ""]
    for a, b, what in named:
        R.append(f"${a:06X}-${b - 1:06X} {b - a:7d}  {what}")
    (out / "regions.txt").write_text("\n".join(R) + "\n")
    print(f"{tot} bytes: {tot_code} code ({100 * tot_code / tot:.1f}%), "
          f"{known} named data ({100 * known / tot:.1f}%), "
          f"{rest} unaccounted for ({100 * rest / tot:.1f}%)")
    print(f"  of the named data, {weak} bytes ({100 * weak / tot:.1f}%) are "
          f"only *pointed at*: an instruction builds the address, but what "
          f"is in the block is not identified")
    print(f"{len(code)} instructions, {len(labels)} labels, "
          f"{len(named)} named regions")
    for n, c, t in stats:
        print(f"  {n}  {c:6d}/{t}  {'#' * int(40 * c / t)}")
    print(f"wrote {out}/rom.map")


if __name__ == "__main__":
    main()
