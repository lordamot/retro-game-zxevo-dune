#!/usr/bin/env python3
"""dune_sound.py - the Mega Drive sound set, laid out for the General Sound
card and for the Z80 that streams it there.

    python3 tools/dune_sound.py [--out build/gen] [--base-page 128]
                                [--card-pages 62] [--drop NAME,NAME...]
                                [--keep-all] [--list src/res/sega_sound.txt]

Reads `src/res/sega_sound.txt` and the modules `tools/sega/sega_mod.py`
made from it (`src/res/prebuilt/music/*.mod`, `src/res/prebuilt/sfx/*.mod`)
and writes into OUT:

    sound.bin      the effects as they go to the card and every tune packed
                   (below); the SPG loads it into RAM pages BASE.. (16 KB
                   each, back to back).  One more page after it is the
                   unpacker's buffer (SND_BUF_PAGE).
    sound_ids.inc  EQUs only: MUS_<name>, SFX_<name>, the counts, the pages
                   - safe to include in any bank
    sound.inc      the tables src/gs.asm uploads, streams and plays from,
                   and the Mega Drive's own numbering mapped onto the ids
                   (S10): effect id ($06A876), voice id ($06A954), music
                   track ($06A8B8) with the battle tunes' lengths in frames.
                   Included by gs.asm.
    sound.txt      the layout in words: what went where, what was left out

## How the card is used (.claude/docs/sound.md, "The port's sound")

The card's own ROM plays everything: the modules with its ProTracker
player, the effects as its "FX samples".  It parses a module in place at
logical address 0, so a tune is written straight into card pages, already
the way its `$30` would have left it, and started by pointing the first
logical pages of the ROM's page table at it; this tool works out the
sample records the parser would have built (`rom_sample_table`).

At start-up, behind the start-up log, the effects go to the card and
then as many tunes as its pages hold, in BOOT_ORDER (the most wanted
first; a 2 MB card holds every tune the game plays but the finale and the
ending's).  Every tune is kept in the SPG packed, and `src/gs.asm` moves
the one asked for, and the ones that may come next, to the card in the
background, a CHUNK at a time, from the game's own loops, when it is not
there already - so each tune has its own samples, rendered for it alone,
and nothing is shared between tunes.  On the card:

    logical pages 0 .. W-1       the tune playing (W: the largest tune)
    logical pages W .. W+E-1     the effects, loaded with $38, for ever
    card slots 0 .. E-1          the effects' pages
    card slots E ..              a pool of pages for tunes, 32 KB each: a
                                 tune takes as many as it needs, anywhere

## The packing

A tune is its card image: the header and patterns, padded to a CHUNK, then
its samples, unsigned.  The samples are byte-delta coded (each byte less
the one before), the header and patterns are not.  That goes through a
byte-aligned LZ77 made for a small Z80 unpacker that works a chunk at a
time:

    $01-$7F   literal run: that many bytes follow
    $80-$BF   match, length (T & $3F) + 3, offset - 1 in the next byte
    $C0-$FF   match, length (T & $3F) + 3, offset - 1 in the next two
              (low first); offsets up to 16384
    $00       the rest of this 16 KB page is unused: carry on at the start
              of the next page (a token never straddles two pages, nor
              ends on a page's last byte)

Every CHUNK of output is made of whole tokens, so the unpacker stops on a
chunk's end; and every BLOCK (16 KB, the unpacker's buffer) starts afresh -
no match reaches back into the block before - so a chunk is unpacked in
place in the buffer at its offset in the block.  The parse is optimal-ish
(a shortest path over positions with hash-chained match candidates), and
slow in Python: its result is cached in OUT/lzcache/ by the image's hash.
`unpack()` is the Z80 unpacker's model, and every tune is unpacked again
and compared before anything is written.
"""

import argparse
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import modlib  # noqa: E402

CARD_PAGE = 32768               # the card's paged window, $8000-$FFFF
ZX_PAGE = 16384                 # a Z80 RAM page in window 1 or 3
MK_HEADER = 1084                # an "M.K." module's header
MAX_FX = 60                     # the ROM's FX sample slots ($C546: cp $3C)
MAX_LOGICAL = 64                # entries in the ROM's page table ($4000)
CHUNK = 512                     # bytes one step of the streaming sends
BLOCK = 16384                   # the unpacker's buffer: LZ restarts here
PACK_VERSION = 1                # bump when the packed format changes
LAST_ZX_PAGE = 248              # the Tutorial's pages start at 249

# Left out by default: the effects nothing in the S10 tables (or the
# screens that call snd_play directly) ever plays - the synthesised twins
# of sampled effects and a few more.  Every tune is in.  See sound.txt.
DEFAULT_DROP = [
    "machinegun_fx", "rifle_fx", "planet_shimmer", "heavy_drop",
    "static_fx", "worm_eats_fx", "rocket_launch", "cannon_fx",
    "explosion1",
]

# The order the tunes go to the card at start-up, behind the loading
# screen: every one that fits the pages the card has, the most wanted
# first (one that does not fit is passed over for a smaller one after it).
# What plays soonest and most surely leads: the title at once, the house
# choice ($1C), the briefing's end ($1D), the mentat of each house
# (mentat_house_confirm $01F342 and mentat_briefing $01F3E6: $18
# Harkonnen, $19 Atreides, $1A Ordos), the five battle tunes (tracks
# 8-12), the Tutorial's (the title menu plays it after 900 idle frames),
# the last mission's finale, the ending, and last the tunes only the
# options' music test plays (the fly-overs' victory tunes and the dirges -
# the port has no fly-over).  A 2 MB card (62 pages) holds everything up
# to the Tutorial's; a 1 MB card (30) the title, the house choice, the
# briefing's end and two of the mentats.  The rest stream when wanted.
# The card cannot take a tune while it plays one without the music
# suffering (sound.md, "The card's time"): what is not here in time is a
# silence the first time it is wanted.
BOOT_ORDER = ["intro", "title", "chosen_destiny", "evasive_action",
              "radnors_scheme", "cyrils_council", "ammons_advice",
              "spice_trip", "trenching", "command_post", "the_lego_tune",
              "turbulence", "starport", "finale", "song18", "conquest",
              "harkonnen_rules", "slitherin", "atreides_dirge",
              "harkonnen_dirge", "ordos_dirge"]

# The port's own tunes, not the cartridge's: (name, module).  The intro
# plays on the intro's screen once the rest is on the card (main.asm,
# snd_boot), and leads BOOT_ORDER so that it is sure to be there; its pages
# go back to the pool as the title comes (gs_intro_done), and the start-up
# tunes it kept out go in them.
PORT_MUSIC = [("intro", ROOT / "src/res/external.mod")]   # --intro replaces the path

# The start-up log's bar (src/main/main.asm, gs_tick) moves with what
# the start-up costs, in half-milliseconds as bin/evo measures them: the
# card's own memory test (2 MB: 10.8 s from power-on, TEST_FRAMES frames
# of 48.8 Hz), an effect's bytes through $38 (COST_FX_US a byte) and a
# tune's chunks through the loader (COST_CHUNK each, unpacking included).
TEST_FRAMES = 527
COST_FX_US = 6.6
COST_CHUNK = 11
FRAME_US = 1e6 / 48.8

# What may be asked for next while a tune plays, most likely first (S10,
# "Where each tune plays" in sound.md): the loader fetches these in the
# background when the tune starts - on a card too small to have them all
# from start-up.  The battle's tunes are not here: the battle draws its
# next when the one playing runs out, as the cartridge does, and nothing
# can know it sooner.  After a battle comes the mentat of the player's
# house, which main.asm asks for itself.  Tunes only the options' music
# test plays have none.
SUCCESSORS = {
    "title": ["chosen_destiny", "starport", "evasive_action"],
    "chosen_destiny": ["radnors_scheme", "cyrils_council", "ammons_advice"],
    "radnors_scheme": ["evasive_action", "chosen_destiny"],
    "cyrils_council": ["evasive_action", "chosen_destiny"],
    "ammons_advice": ["evasive_action", "chosen_destiny"],
    "starport": ["title"],
    "finale": ["song18"],
    "song18": ["title"],
}
MAX_SUCC = 3

# Speech outranks everything; the ROM lets a new effect take a channel from
# a playing one only if its priority is strictly higher ($CA9C).
SPEECH = {"unit_approach", "const_complete", "under_attack", "yes_sir",
          "acknowledged", "reporting", "moving_out"}
PRIO_SPEECH, PRIO_FX = 0xC0, 0x80

# Mega Drive tables (orig/sega/spec/S10-screens.md, tools/sega/spec_s10.py)
S10_EFFECTS = {6: 44, 7: 42, 8: 84, 12: 25, 13: 82, 14: 81, 15: 79, 16: 80,
               17: 67, 18: 68, 20: 70, 27: 83, 30: 76, 31: 76, 32: 76,
               33: 76, 34: 76, 35: 78, 36: 23, 38: 40, 39: 35, 40: 36,
               41: 39, 42: 74, 43: 34, 44: 29, 46: 28, 47: 26, 49: 39,
               50: 71, 51: 81, 52: 27, 53: 21, 56: 69, 57: 69, 58: 72,
               59: 73, 62: 75, 63: 77, 64: 72}
S10_VOICES = {0: 65, 1: 64, 2: 64, 3: 64, 4: 64, 5: 64, 48: 66}
S10_MUSIC = {1: (5, -1), 2: (16, -1), 3: (15, -1), 4: (14, -1),
             5: (13, -1), 6: (12, -1), 7: (11, -1), 8: (1, 10020),
             9: (2, 7320), 10: (3, 7560), 11: (4, 8040), 12: (10, 9840),
             24: (6, -1), 25: (0, -1), 26: (8, -1), 28: (9, -1),
             29: (7, -1), 33: (18, -1), 38: (17, -1)}
N_EFFECTS, N_VOICES, N_TRACKS = 0x41, 0x5E, 0x27


def parse_list(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].split()
        if line:
            out.append((line[0], line[1], line[2], int(line[3])))
    return out


# ------------------------------------------------------------ the modules

def paged(lin):
    """A linear card address as the ROM keeps one: (page, lo, hi) with the
    offset in $8000-$FFFF."""
    off = 0x8000 | (lin & 0x7FFF)
    return lin >> 15, off & 0xFF, off >> 8


def npat_of(d):
    return max(d[952:1080]) + 1


def sample_lengths(d):
    """The 31 samples' lengths in bytes, from their headers."""
    return [2 * struct.unpack(">H", d[42 + 30 * i:44 + 30 * i])[0]
            for i in range(31)]


def rom_sample_table(d, starts=None):
    """The 31 16-byte records the ROM's module parser writes at $5400
    ($0DB1-$0EDE).  `starts` gives each sample's linear card address; left
    out, the samples follow the patterns as the parser finds them, for a
    module at card address 0.  Bytes the ROM leaves as they were are 0
    here; `defined` says which those are not."""
    start = MK_HEADER + npat_of(d) * 1024
    recs, defined = [], []
    for i in range(31):
        h = d[20 + 30 * i:50 + 30 * i]
        length, ft, vol, ls, ll = struct.unpack(">HBBHH", h[22:])
        if starts is not None:
            start = starts[i]
        r = bytearray(16)
        r[0:3] = paged(start)
        ok = set(range(0, 8))
        looped = not (ll >> 8 == 0 and (ll & 0xFF) < 2) and ls < length
        end = start + 2 * length
        if looped:
            lstart = start + 2 * ls
            lend = lstart + 2 * ll
            r[8:11] = paged(lstart)
            r[11:14] = paged(lend)
            r[3:6] = r[11:14]
            ok |= set(range(8, 14))
        else:
            r[8] = 0xFF
            r[3:6] = paged(end)
            ok.add(8)
        r[6] = (ft * 2) & 0xFF
        r[7] = vol
        recs.append(bytes(r))
        defined.append(ok)
        start = end
    return recs, defined


def unsigned(b):
    """Samples as the ROM leaves them: $0EE1 adds $80 to every byte."""
    return bytes((x + 0x80) & 0xFF for x in b)


def card_image(d):
    """The module as the ROM's own `$30` leaves it in the card's memory:
    its samples made unsigned."""
    s = MK_HEADER + npat_of(d) * 1024
    return d[:s] + unsigned(d[s:])


def used_samples(d):
    n = 0
    for i, length in enumerate(sample_lengths(d)):
        if length:
            n = i + 1
    return n


def init_module():
    """The smallest module the ROM accepts: one silent pattern, no samples.
    Loading it once with $30 is what makes the ROM set up its module
    channels; its bytes are never played."""
    head = b"init".ljust(20, b"\0")
    head += (bytes(22) + struct.pack(">HBBHH", 0, 0, 0, 0, 1)) * 31
    return head + bytes([1, 0]) + bytes(128) + b"M.K." + bytes(1024)


def tune_image(d):
    """(image, head chunks, sample records): the header and patterns
    padded to a whole CHUNK, the samples after them unsigned, the whole
    padded to a CHUNK; and the records pointing at the samples there, for
    a tune at logical address 0."""
    head = d[:MK_HEADER + npat_of(d) * 1024]
    hc = -(-len(head) // CHUNK)
    img = bytearray(head.ljust(hc * CHUNK, b"\0"))
    starts, p = [], len(head)
    for n in sample_lengths(d):
        starts.append(len(img))
        img += unsigned(d[p:p + n])
        p += n
    img += bytes(-len(img) % CHUNK)
    recs, _ = rom_sample_table(d, starts)
    return bytes(img), hc, recs


# ------------------------------------------------------------ the packer

def delta(img, from_):
    """Bytes from `from_` on as each less the one before (the first less
    0); before it as they are."""
    out = bytearray(img[:from_])
    last = 0
    for b in img[from_:]:
        out.append((b - last) & 0xFF)
        last = b
    return bytes(out)


def undelta(t, from_):
    out = bytearray(t[:from_])
    last = 0
    for b in t[from_:]:
        last = (last + b) & 0xFF
        out.append(last)
    return bytes(out)


def match_cost(off):
    return 2 if off <= 256 else 3


def pack_block(data, lo, hi):
    """Tokens for data[lo:hi] (one BLOCK), none crossing a CHUNK boundary,
    matches only inside the block: a list of ("L", bytes) and
    ("M", length, offset)."""
    n = hi - lo
    INF = 1 << 40
    head, prev = {}, {}
    best = [INF] * (n + 1)
    run = [0] * (n + 1)
    how = [None] * (n + 1)
    best[0] = 0
    for i in range(n):
        p = lo + i
        cend = (i // CHUNK + 1) * CHUNK         # this chunk's end
        cands = []
        if i + 3 <= n:
            k = data[p:p + 3]
            c = head.get(k)
            bl, chain, lim = 2, 0, min(cend - i, 66)
            while c is not None and chain < 48:
                ln = 0
                while ln < lim and data[c + ln] == data[p + ln]:
                    ln += 1
                if ln > bl:
                    bl = ln
                    cands.append((ln, p - c))
                    if ln == lim:
                        break
                c = prev.get(c)
                chain += 1
            prev[p] = head.get(k)
            head[k] = p
        b = best[i]
        if b >= INF:
            continue
        r = 0 if i % CHUNK == 0 else run[i]
        c = b + 1 + (1 if r % 127 == 0 else 0)
        if c < best[i + 1] or (c == best[i + 1] and r + 1 > run[i + 1]):
            best[i + 1], run[i + 1], how[i + 1] = c, r + 1, ("L",)
        for ln, off in cands:
            mc = match_cost(off)
            for ll in (range(3, ln + 1) if ln < 10 else (ln, ln - 1, 3, 4)):
                c = b + mc
                if c < best[i + ll]:
                    best[i + ll], run[i + ll], how[i + ll] = c, 0, \
                        ("M", ll, off)
    # walk back
    steps, i = [], n
    while i > 0:
        h = how[i]
        if h[0] == "L":
            steps.append(("L", i - 1))
            i -= 1
        else:
            steps.append(("M", h[1], h[2]))
            i -= h[1]
    steps.reverse()
    toks, pos = [], 0
    for s in steps:
        if s[0] == "L":
            if toks and toks[-1][0] == "L" and len(toks[-1][1]) < 127 \
                    and pos % CHUNK != 0:
                toks[-1] = ("L", toks[-1][1] + data[lo + pos:lo + pos + 1])
            else:
                toks.append(("L", data[lo + pos:lo + pos + 1]))
            pos += 1
        else:
            toks.append(s)
            pos += s[1]
    return toks


def token_bytes(t):
    if t[0] == "L":
        return bytes([len(t[1])]) + t[1]
    _, ln, off = t
    if off <= 256:
        return bytes([0x80 | (ln - 3), off - 1])
    return bytes([0xC0 | (ln - 3), (off - 1) & 0xFF, (off - 1) >> 8])


def pack(img, hc, cache=None):
    """The tune's token stream, without page markers (place() adds
    them).  Cached by the image's hash."""
    key = hashlib.sha1(img + bytes([hc, PACK_VERSION])).hexdigest()
    f = cache / f"{key}.lz" if cache else None
    if f and f.exists():
        return f.read_bytes()
    t = delta(img, hc * CHUNK)
    out = bytearray()
    for lo in range(0, len(t), BLOCK):
        for tok in pack_block(t, lo, min(len(t), lo + BLOCK)):
            out += token_bytes(tok)
    if f:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(out)
    return bytes(out)


def tokens_of(stream):
    """Split a stream without markers back into its tokens' bytes."""
    i = 0
    while i < len(stream):
        t = stream[i]
        n = 1 + t if t < 0x80 else (2 if t < 0xC0 else 3)
        assert t, "a marker in an unplaced stream"
        yield stream[i:i + n]
        i += n


def place(stream, at):
    """The stream as it lies from ZX offset `at` on: a $00 wherever the
    next token would straddle a page, and the rest of that page unused."""
    out = bytearray()
    for tok in tokens_of(stream):
        p = (at + len(out)) % ZX_PAGE
        if p + len(tok) >= ZX_PAGE:     # the last byte is kept for a $00
            out.append(0)
            out += bytes(ZX_PAGE - p - 1)
        out += tok
    return bytes(out)


def unpack(placed, at, chunks, hc):
    """The Z80 unpacker's model (gs_unpack, then the sending loop's
    undelta): the image back from a placed stream."""
    src = at
    buf = bytearray(BLOCK)
    t = bytearray()
    blob = placed
    for c in range(chunks):
        d = (c * CHUNK) % BLOCK
        end = d + CHUNK
        while d < end:
            tok = blob[src - at]
            src += 1
            if tok == 0:
                src += ZX_PAGE - (src % ZX_PAGE) if src % ZX_PAGE else 0
                continue
            if tok < 0x80:
                buf[d:d + tok] = blob[src - at:src - at + tok]
                src += tok
                d += tok
                continue
            ln = (tok & 0x3F) + 3
            off = blob[src - at] + 1
            src += 1
            if tok >= 0xC0:
                off += blob[src - at] << 8
                src += 1
            assert off <= d, "a match before its block"
            for k in range(ln):
                buf[d + k] = buf[d + k - off]
            d += ln
        assert d == end, "a token across a chunk's end"
        t += buf[end - CHUNK:end]
    return undelta(bytes(t), hc * CHUNK)


# ------------------------------------------------------------ the effects

def fx_sample(path):
    """(unsigned data, FX note) out of a one-sample effect module.  The FX
    note is the card's own numbering, where note 36 is ProTracker's C-1
    (the period table at $6C00 in the ROM's page 0, 856 * 8 at note 0)."""
    title, samples, patterns, orders, restart = modlib.read(path)
    s = samples[0]
    assert s.finetune == 0 and not s.loop_len, path
    cell = patterns[orders[0]][0][0]
    assert cell.note is not None and cell.sample == 1, path
    return unsigned(s.data), 36 + cell.note, s.volume


# ------------------------------------------------------------ the layout

class Item:
    pass


def ident(name):
    return "".join(c if c.isalnum() else "_" for c in name).upper()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", type=Path,
                    default=ROOT / "src/res/sega_sound.txt")
    ap.add_argument("--prebuilt", type=Path,
                    default=ROOT / "src/res/prebuilt")
    ap.add_argument("--out", type=Path, default=ROOT / "build/gen")
    ap.add_argument("--base-page", type=int, default=128)
    ap.add_argument("--card-pages", type=int, default=62,
                    help="32 KB pages the card's ROM finds: 62 on 2 MB")
    ap.add_argument("--drop", default=",".join(DEFAULT_DROP),
                    help="names to leave out, comma separated")
    ap.add_argument("--keep-all", action="store_true",
                    help="drop nothing")
    ap.add_argument("--intro", type=Path,
                    help="the intro's module (default src/res/external.mod)")
    ap.add_argument("--only", default="",
                    help="keep only these names (for tests)")
    args = ap.parse_args()
    if args.intro:
        PORT_MUSIC[0] = ("intro", args.intro)

    drop = set() if args.keep_all else set(filter(None,
                                                  args.drop.split(",")))
    only = set(filter(None, args.only.split(",")))
    entries = parse_list(args.list)
    names = {e[1] for e in entries} | {n for n, _ in PORT_MUSIC}
    for n in drop | only:
        if n not in names:
            sys.exit(f"dune_sound: no sound called {n}")
    keep = [e for e in entries if e[1] not in drop
            and (not only or e[1] in only)]
    music, sfx = read_set(args, keep)
    lay_out(args, music, sfx)
    write_out(args, entries, keep, music, sfx)


def read_set(args, keep):
    music, sfx = [], []
    cache = args.out / "lzcache"
    for kind, name, bank, song in keep:
        it = Item()
        it.name, it.bank, it.song = name, bank, song
        if kind == "music":
            d = (args.prebuilt / "music" / f"{name}.mod").read_bytes()
            it.d = d
            it.npat = npat_of(d)
            it.nsamp = used_samples(d)
            it.songlen, it.restart = d[950], d[951]
            it.img, it.hc, recs = tune_image(d)
            it.recs = recs[:it.nsamp]
            it.chunks = len(it.img) // CHUNK
            it.pages = -(-len(it.img) // CARD_PAGE)
            it.packed = pack(it.img, it.hc, cache)
            it.id = len(music)
            music.append(it)
        else:
            p = args.prebuilt / "sfx" / f"{name}.mod"
            it.data, it.note, it.vol = fx_sample(p)
            it.prio = PRIO_SPEECH if name in SPEECH else PRIO_FX
            it.id = len(sfx)
            sfx.append(it)
    # the port's own tunes, after the cartridge's: modules as they are
    for name, path in PORT_MUSIC:
        only = set(filter(None, args.only.split(",")))
        if only and name not in only:
            continue
        it = Item()
        it.name, it.bank, it.song = name, "port", 0
        d = path.read_bytes()
        if d[1080:1084] != b"M.K.":
            sys.exit(f"dune_sound: {path} is not a four-channel M.K. module")
        it.d = d
        it.npat = npat_of(d)
        it.nsamp = used_samples(d)
        it.songlen, it.restart = d[950], d[951]
        it.img, it.hc, recs = tune_image(d)
        it.recs = recs[:it.nsamp]
        it.chunks = len(it.img) // CHUNK
        it.pages = -(-len(it.img) // CARD_PAGE)
        it.packed = pack(it.img, it.hc, cache)
        it.id = len(music)
        music.append(it)
    if not music:
        sys.exit("dune_sound: no music left")
    if len(sfx) > MAX_FX:
        sys.exit(f"dune_sound: {len(sfx)} effects, the ROM holds {MAX_FX}")
    return music, sfx


def boot_set(order, pool):
    """The tunes gs_boot_set puts on a card with `pool` pages for tunes:
    each of `order` that still fits, in turn (src/gs.asm, gs_boot_set)."""
    out = []
    for m in order:
        if m.pages <= pool:
            out.append(m)
            pool -= m.pages
    return out


def lay_out(args, music, sfx):
    """The card's logical pages and slots, and sound.bin."""
    a = args
    a.window = max(m.pages for m in music)
    pos = a.window * CARD_PAGE
    for f in sfx:
        f.lin = pos
        pos += len(f.data)
    a.fx_bytes = pos - a.window * CARD_PAGE
    a.fx_pages = -(-a.fx_bytes // CARD_PAGE)
    if a.window + a.fx_pages > MAX_LOGICAL:
        sys.exit("dune_sound: the effects and the largest tune need "
                 f"{a.window + a.fx_pages} logical pages, the ROM has "
                 f"{MAX_LOGICAL}")
    # the start-up order (BOOT_ORDER, then any tune it leaves out), and the
    # smallest card this plays on: the effects and two of the largest
    # tunes (the one playing and the next being fetched)
    by_name = {m.name: m for m in music}
    a.order = [by_name[n] for n in BOOT_ORDER if n in by_name]
    a.order += [m for m in music if m not in a.order]
    a.card_min = a.fx_pages + 2 * a.window
    if a.card_min > a.card_pages:
        sys.exit(f"dune_sound: needs {a.card_min} card pages, the card "
                 f"has {a.card_pages}")
    a.start = boot_set(a.order, a.card_pages - a.fx_pages)
    # the costs the loading screen's bar counts in (half-milliseconds)
    for f in sfx:
        f.cost = round(len(f.data) * COST_FX_US / 500)
    a.fx_cost = sum(f.cost for f in sfx)
    a.boot_cost = a.fx_cost + sum(m.chunks * COST_CHUNK for m in a.start)
    a.test_cost = round(TEST_FRAMES * FRAME_US / 500)
    if a.boot_cost + a.test_cost > 0xFFFF:
        sys.exit("dune_sound: the start-up's cost does not fit 16 bits")
    # sound.bin: the init module, the effects, the packed tunes
    blob = bytearray()

    def at(it):
        it.zx_off = len(blob)
        it.zx_page = a.base_page + it.zx_off // ZX_PAGE
        it.zx_addr = it.zx_off % ZX_PAGE

    a.init = Item()
    a.init.data = init_module()
    at(a.init)
    blob += a.init.data
    for f in sfx:
        at(f)
        blob += f.data
    for m in music:
        at(m)
        m.placed = place(m.packed, m.zx_off)
        blob += m.placed
        back = unpack(m.placed, m.zx_off, m.chunks, m.hc)
        assert back == m.img, f"{m.name} does not unpack to itself"
    a.blob = bytes(blob)
    a.zx_data_pages = -(-len(blob) // ZX_PAGE)
    a.buf_page = a.base_page + a.zx_data_pages
    a.zx_pages = a.zx_data_pages + 1
    if a.buf_page > LAST_ZX_PAGE:
        sys.exit(f"dune_sound: the sound set reaches page {a.buf_page}; "
                 f"{LAST_ZX_PAGE} is the last it may have")


def write_out(args, entries, keep, music, sfx):
    a = args
    out = a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "sound.bin").write_bytes(a.blob)
    by_name = {m.name: m for m in music}

    # ---- sound_ids.inc
    ids = ["; sound_ids.inc - made by tools/dune_sound.py; do not edit.", ""]
    ids += [f"SND_BASE_PAGE   EQU {a.base_page}",
            f"SND_ZX_PAGES    EQU {a.zx_pages}\t\t; 16 KB pages, with the "
            "buffer",
            f"SND_BUF_PAGE    EQU {a.buf_page}\t\t; the unpacker's buffer",
            f"SND_CARD_PAGES  EQU {a.card_min}\t\t; 32 KB card pages it "
            "needs at least",
            f"SND_WINDOW      EQU {a.window}\t\t; logical pages of the "
            "largest tune",
            f"SND_FX_PAGES    EQU {a.fx_pages}\t\t; card pages of the "
            "effects",
            f"SND_CHUNK       EQU {CHUNK}\t\t; bytes a streaming step sends",
            "; the loading screen's bar, in half-milliseconds of bin/evo:",
            f"SND_TEST_FRAMES EQU {TEST_FRAMES}\t\t; the card's memory "
            "test (2 MB), in frames",
            f"SND_TEST_COST   EQU {a.test_cost}\t\t; ... and what it costs",
            f"SND_COST_CHUNK  EQU {COST_CHUNK}\t\t; a tune's chunk",
            f"SND_FX_COST     EQU {a.fx_cost}\t\t; all the effects",
            f"SND_BOOT_COST   EQU {a.boot_cost}\t\t; the effects and the "
            f"tunes of a {a.card_pages}-page card",
            f"MUS_COUNT       EQU {len(music)}",
            f"SFX_COUNT       EQU {len(sfx)}",
            f"SND_SUCC        EQU {MAX_SUCC}\t\t; successors a tune names",
            "SND_NONE        EQU $FF", ""]
    for m in music:
        ids.append(f"MUS_{ident(m.name):<20} EQU {m.id}")
    ids.append("")
    for f in sfx:
        ids.append(f"SFX_{ident(f.name):<20} EQU {f.id}")
    (out / "sound_ids.inc").write_text("\n".join(ids) + "\n")

    # ---- sound.inc
    L = ["; sound.inc - made by tools/dune_sound.py; do not edit.",
         "; The tables src/gs.asm uploads, streams and plays from.  Needs",
         "; sound_ids.inc first.  A ZX address is in RAM page `page`, seen",
         "; in window 3 ($C000) for the effects, window 1 ($4000) for the",
         "; packed tunes; either runs on into the next page number.",
         ""]
    L += ["; the module the ROM is given once with $30, so that it sets up",
          "; its module channels: page, offset, length",
          f"snd_init:       DB {a.init.zx_page}",
          f"                DW ${0xC000 + a.init.zx_addr:04X}, "
          f"{len(a.init.data)}",
          ""]
    L += ["; a tune: where its packed stream starts (page, offset), its",
          "; chunks, how many of them are header and patterns (not delta",
          "; coded), its card pages; then what starting it writes into the",
          "; card: the song length - 1 ($415C), restart ($415D), patterns",
          "; ($419E), format ($419F), and its sample records ($5400, 16",
          "; bytes each) and their count",
          "SM_PAGE         EQU 0",
          "SM_ADDR         EQU 1",
          "SM_CHUNKS       EQU 3",
          "SM_HEAD         EQU 5",
          "SM_PAGES        EQU 6",
          "SM_SONG         EQU 7",
          "SM_RECS         EQU 11",
          "SM_NSAMP        EQU 13",
          "SND_MOD_SIZE    EQU 14",
          "snd_mods:"]
    for m in music:
        L.append(f"                DB {m.zx_page}\t\t; MUS_{ident(m.name)}")
        L.append(f"                DW ${0x4000 + m.zx_addr:04X}, {m.chunks}")
        L.append(f"                DB {m.hc}, {m.pages}")
        L.append(f"                DB {m.songlen - 1}, {m.restart}, "
                 f"{m.npat}, $FF")
        L.append(f"                DW snd_rec_{m.id}")
        L.append(f"                DB {m.nsamp}")
    L.append("")
    L += ["; the order the tunes go to the card at start-up, the most",
          "; wanted first: each that still fits the card's pages",
          f"snd_start:      DB {len(a.order)}"]
    for i in range(0, len(a.order), 4):
        L.append("                DB " + ", ".join(
            f"MUS_{ident(m.name)}" for m in a.order[i:i + 4]))
    L.append("")
    L += ["; what may be asked for after each tune, most likely first:",
          "; the loader fetches them when it starts"]
    L.append("snd_succ:")
    for m in music:
        s = [by_name[n].id for n in SUCCESSORS.get(m.name, [])
             if n in by_name][:MAX_SUCC]
        s += [0xFF] * (MAX_SUCC - len(s))
        L.append("                DB " + ", ".join(
            f"MUS_{ident(music[x].name)}" if x != 0xFF else "SND_NONE"
            for x in s) + f"\t; after {m.name}")
    L.append("")
    L += ["; an effect: page, offset, length (3 bytes), card address "
          "(3 bytes,",
          "; logical), FX note, volume, priority; what sending it costs",
          "; (the loading screen's bar)",
          "snd_fx:"]
    for f in sfx:
        n = len(f.data)
        L.append(f"                DB {f.zx_page}\t\t; SFX_{ident(f.name)}")
        L.append(f"                DW ${0xC000 + f.zx_addr:04X}")
        L.append(f"                DB {n & 0xFF}, {(n >> 8) & 0xFF}, "
                 f"{n >> 16}")
        L.append(f"                DB {f.lin & 0xFF}, {(f.lin >> 8) & 0xFF}, "
                 f"{f.lin >> 16}")
        L.append(f"                DB {f.note}, {f.vol}, ${f.prio:02X}")
        L.append(f"                DW {f.cost}")
    L.append("SND_FX_COSTOF   EQU 12")
    L.append("SND_FX_SIZE     EQU 14")
    L.append("")
    for m in music:
        L.append(f"snd_rec_{m.id}:\t\t\t\t; {m.name}")
        for r in m.recs:
            L.append("                DB " + ", ".join(f"${b:02X}" for b in r))
    L.append("")

    # the Mega Drive's numbering
    mus_by_song = {m.song: m for m in music if m.bank == "game"}
    fx_by_song = {f.song: f for f in sfx if f.bank == "game"}

    def fxid(song):
        f = fx_by_song.get(song)
        return f"SFX_{ident(f.name)}" if f else "SND_NONE"

    L += ["; effect id 0-$40 (snd_play_effect, $06A876) -> SFX id",
          "snd_effect_map:"]
    row = [fxid(S10_EFFECTS[i]) if i in S10_EFFECTS else "SND_NONE"
           for i in range(N_EFFECTS)]
    for i in range(0, len(row), 8):
        L.append("                DB " + ", ".join(row[i:i + 8]))
    L += ["", "; voice id 0-$5D (snd_play_voice, $06A954) -> SFX id",
          "snd_voice_map:"]
    row = [fxid(S10_VOICES[i]) if i in S10_VOICES else "SND_NONE"
           for i in range(N_VOICES)]
    for i in range(0, len(row), 8):
        L.append("                DB " + ", ".join(row[i:i + 8]))
    L += ["", "; music track 0-$26 (snd_play_music, $06A8B8) -> MUS id",
          "snd_track_map:"]
    row = []
    for t in range(N_TRACKS):
        song = S10_MUSIC.get(t, (-1, -1))[0]
        m = mus_by_song.get(song)
        row.append(f"MUS_{ident(m.name)}" if m else "SND_NONE")
    for i in range(0, len(row), 8):
        L.append("                DB " + ", ".join(row[i:i + 8]))
    L += ["", "; ... and what snd_play_music puts in musicFramesLeft for it",
          "; ($06A8BA, $00A894): the frames it runs before the battle's",
          "; shuffle moves on (only tracks 8-12 are timed), $FFFF (-1) for",
          "; the rest; 0 where the track has no song at all ($06A8B8",
          "; negative: snd_play_music does nothing, $00A874) - whether or",
          "; not the port has a tune for it",
          "snd_track_frames:"]
    row = []
    for t in range(N_TRACKS):
        song, frames = S10_MUSIC.get(t, (-1, -1))
        row.append("0" if song < 0 else "$FFFF" if frames < 0 else
                   str(frames))
    for i in range(0, len(row), 8):
        L.append("                DW " + ", ".join(row[i:i + 8]))
    (out / "sound.inc").write_text("\n".join(L) + "\n")

    # ---- sound.txt
    img = sum(len(m.img) for m in music)
    packed = sum(len(m.packed) for m in music)
    heads = sum(m.hc * CHUNK for m in music)
    hpk = smp = 0
    for m in music:
        # the share of the packed stream that is header and patterns: the
        # tokens until the head's chunks are out
        n = 0
        for tok in tokens_of(m.packed):
            if n >= m.hc * CHUNK:
                break
            t = tok[0]
            n += t if t < 0x80 else (t & 0x3F) + 3
            hpk += len(tok)
        smp += len(m.img) - m.hc * CHUNK
    pool = args.card_pages - a.fx_pages
    T = [f"sound.bin: {len(a.blob)} bytes in {a.zx_data_pages} Z80 pages "
         f"from {a.base_page}, and page {a.buf_page} the unpacker's buffer",
         f"music: {len(music)} tunes, {img} bytes as they go to the card, "
         f"{packed} packed ({packed / img:.3f}): header and patterns "
         f"{heads} -> {hpk} ({hpk / heads:.3f}), samples {smp} -> "
         f"{packed - hpk} ({(packed - hpk) / smp:.3f})",
         f"effects: {len(sfx)}, {a.fx_bytes} bytes as they are, in card "
         f"slots 0-{a.fx_pages - 1} (logical pages {a.window}-"
         f"{a.window + a.fx_pages - 1})",
         f"card: tunes at logical pages 0-{a.window - 1}; {pool} of "
         f"{args.card_pages} pages for them (needs at least {a.card_min} "
         "pages in all)"]
    for pages in sorted({args.card_pages, 30}, reverse=True):
        st = boot_set(a.order, pages - a.fx_pages)
        T.append(f"start-up, a {pages}-page card: the effects and "
                 f"{', '.join(m.name for m in st)}; "
                 f"{a.fx_bytes + sum(len(m.img) for m in st)} bytes in "
                 f"{a.fx_pages + sum(m.pages for m in st)} card pages; "
                 "streamed when wanted: "
                 + (", ".join(m.name for m in a.order if m not in st)
                    or "nothing"))
        # after the intro's screen (gs_intro_done): the set without the
        # port's own tunes
        port = {n for n, _ in PORT_MUSIC}
        rest = [m for m in a.order if m.name not in port]
        af = boot_set(rest, pages - a.fx_pages)
        T.append(f"  after the intro: out {', '.join(m.name for m in st if m not in af) or '-'}"
                 f"; in {', '.join(m.name for m in af if m not in st) or '-'}")
    T.append(f"loading screen: the memory test {a.test_cost}, the upload "
             f"{a.boot_cost} (effects {a.fx_cost}) half-ms")
    T.append("")
    for m in music:
        T.append(f"MUS {m.id:2} {m.name:16} {len(m.img):7} bytes, "
                 f"{m.pages} card pages, {m.chunks:3} chunks ({m.hc} head), "
                 f"packed {len(m.packed):6} ({len(m.packed) / len(m.img):.2f})"
                 f" at page {m.zx_page} +${m.zx_addr:04X}; "
                 f"{m.nsamp} samples; next: "
                 + (", ".join(SUCCESSORS.get(m.name, [])) or "-"))
    for f in sfx:
        T.append(f"SFX {f.id:2} {f.name:18} {len(f.data):7} bytes, note "
                 f"{f.note}, card ${f.lin:06X}")
    dropped = [e for e in entries if e not in keep]
    if dropped:
        T.append("")
        for kind, name, bank, song in dropped:
            n = (args.prebuilt / ("music" if kind == "music" else "sfx")
                 / f"{name}.mod").stat().st_size
            T.append(f"left out: {kind} {name} ({bank} song {song}, "
                     f"{n} bytes as a module)")
    (out / "sound.txt").write_text("\n".join(T) + "\n")
    print("\n".join(T[:8]))


if __name__ == "__main__":
    main()
