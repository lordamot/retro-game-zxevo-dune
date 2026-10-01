#!/usr/bin/env python3
"""sega_seq.py - the Mega Drive Dune II's music, taken apart into notes.

    sega_seq.py [--rom orig/dune2.gen] [--out orig/sega/res/sound]

Writes `music.txt`: the sound driver's command protocol, the two banks of
sound resources the game installs, and every song in them disassembled
into its tracks and their events.

`sega_z80.py` finds the driver and disassembles its Z80; `sega_music.py`
finds the DAC samples by their shape.  This is the third piece - what the
driver is *told*, and what it reads when it is told it.

## How the 68000 asks for a tune

The driver owns the Z80's 8 KB.  Two bytes of it are the mailbox: a write
index at `$0036` that only the 68000 touches and a read index at `$0037`
that only the Z80 touches, over a 64-byte ring at `$1B40`.  A command is
`$FF`, an opcode, and the opcode's arguments; the driver's main loop reads
until it sees `$FF`, takes the next byte as the opcode and jumps.

The 68000 side is a library of one function per command, all of them
entered through the same three routines - `$001596` takes the Z80's bus and
loads the two pointers, `$0015EA` pushes one byte, `$0015CC` gives the bus
back.  The whole library appears twice, once in bank 0 and once at
`$02AF00`, and only the bank 0 copy is ever called.

The game uses seven of the driver's twenty-four commands.  The important two are
`$0B`, which installs four 24-bit ROM addresses the driver reads all its
data through, and `$10`, which starts a song.

## The four resources

Every one of `$0B`'s four pointers is a directory in the same idiom: a run
of 16-bit offsets relative to the directory itself, and **the first offset
divided by the entry size is how many entries there are**, because entry
0's data follows the last offset.  Nothing in the format says how many
there are; that division is the whole trick, and it is the same one in
all four.

| pointer | what it is | read by |
|---|---|---|
| 0 | instruments: 39 bytes, the sound slot a voice plays through | `$02`, `$03`, the track's `patch` |
| 1 | pitch envelopes: `(ticks, signed 16-bit step)` triples, ended by a zero | `$06`, the track's `bend` |
| 2 | the songs | `$10`, the track's `song` |
| 3 | samples: 12-byte descriptors indexed by note, holding a 24-bit offset and a 16-bit length | played through the DAC |

The four are laid out one after another in the cartridge and the whole
bank is contiguous - samples, then songs, then envelopes, then
instruments, ending exactly where the next thing begins.  Both banks check
out that way, which is written down at the end of `music.txt`.

## What a song is

`$0B`'s third pointer is the song directory: a list of 16-bit offsets,
little-endian inside a big-endian cartridge, each relative to the
directory itself.  The number of songs is the first offset divided by two,
because song 0's header follows the last entry.

A song header is a track count and then one 16-bit offset per track.  Each
track is an independent byte stream, given a voice of its own - sixteen
voices of 32 bytes at `$1B80` - and read a byte at a time through the
cartridge bank register at `$6000`.

    < $60        a note: this is the pitch, and the voice's own sound slot
                 (sixteen of 39 bytes at `$188A`) says what it sounds like
    $60 - $72    one of nineteen commands, below
    $80 - $BF    how long the note sounds, a variable-length number
    $C0 - $FF    how long until the next event, a variable-length number

The two variable-length forms carry six bits a byte, most significant
first, and end at the first byte that does not continue them - which the
driver then re-reads as the next event.  It stores both counts negated, as
up-counters that end at zero.

## Why the commands are named the way they are

Every name below is what the driver's handler does, not a guess:
`$60` clears the voice's flags and stops, `$6F` adds a signed 16-bit
number to the track pointer, `$70` writes a byte into the sixteen
variables at `$1B22` and `$71` compares one of them and branches.  Every
one of the nineteen, and every one of the 24 commands the 68000 sends, is
written out in `commands.txt` with the handler it was read from.  `$67`
(and driver command `$0E`) set flag 7, which only the channel allocator
reads (`$1815`): with it set, a voice is not handed back its own free
channel first.

## How this knows it read the format right

It measures itself, and says so at the end of `music.txt`.  Follow every
track of every song to its `end` and add up the bytes: in both banks the
total is exactly the distance from the directory to the last track's last
byte, with no byte claimed twice and none left over.  Both banks then stop
where the next resource pointer starts - the front end's songs end at
`$0D01F5` and the game's at `$0FE129`, which are the very addresses
command `$0B` installed beside them.  Neither of those had to come out
that way if the header or the events were being read wrongly.
"""

import argparse
import struct
import sys
import textwrap
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# the 68000 library, bank 0's copy
API_OPEN = 0x001596          # take the Z80 bus, point at the ring
API_PUT = 0x0015EA           # push one byte
API_FRAME = 0x0015DE         # push $FF, then one byte
API_PUT3 = 0x001608          # push three bytes of a long, low first
API_CLOSE = 0x0015CC         # give the bus back
API_INIT = 0x001624          # upload, reset, then command $0B

# the two copies of that library; a call from inside one of them is the
# library talking to itself, not the game asking for a sound
LIB = ((0x001500, 0x0017A0), (0x02AF00, 0x02B300))

# the Z80 driver, at $00294E in the cartridge and $0000 in its own RAM
DRIVER = 0x00294E
DRIVER_END = 0x0041D8
DISPATCH = 0x095B            # the CP/JP Z chain the main loop runs on

# The driver's commands, read handler by handler in res/sound/z80driver.asm.
# `bytes` counts every byte the handler takes off the ring, including the
# ones the routines it calls read - L08A5 reads one (a voice number, and
# points IX at that voice's record), L01D1 reads one.  An earlier table
# counted only the handler's own L01D1 calls and so had $02 at nothing,
# $04 at one and $1E at two.  Extra bytes a sender writes are harmless:
# the main loop skips everything up to the next $FF.
#
#   op: (bytes, name, arguments, what it does)
COMMANDS = {
    0x00: (2, "note on", "voice, note",
           "play a note on a voice, through the instrument already loaded "
           "into its slot (L1153 finds the slot, L1208 plays it).  How far "
           "it is turned down is the master attenuation plus the voice's "
           "own."),
    0x01: (2, "note off", "voice, note",
           "key off whichever channel is sounding that voice's note: the "
           "FM, PSG tone and noise channel tables are searched for the "
           "(voice, note) pair $00 left there (L16A0), and an FM channel is "
           "keyed off through register $28, a PSG one put into release."),
    0x02: (2, "load instrument", "voice, instrument",
           "copy instrument n out of resource 0 into the voice's 39-byte "
           "slot and remember it at voice+13 (L172A)."),
    0x03: (1, "reload instrument", "instrument",
           "copy instrument n into the slot of every voice that has it "
           "loaded (L176A)."),
    0x04: (3, "detune", "voice, low, high",
           "set the voice's pitch offset, 8.8 semitones added to every note "
           "(L0F58, into $0F78 and $0F88; added in L10AA)."),
    0x05: (1, "tempo", "tempo",
           "set the music clock: the byte times $DA, doubled, becomes the "
           "16-bit step at $08BE that each frame adds to the accumulator "
           "at $08C0 (L0E1D).  Track command $68 does the same with 40 "
           "added."),
    0x06: (2, "pitch envelope", "voice, envelope",
           "give the voice pitch envelope n (voice+29) and start it now - "
           "unless the voice restarts its envelope on every note anyway "
           "(flag 6)."),
    0x07: (2, "retrigger", "voice, on/off",
           "voice flag 6: restart the pitch envelope with every note."),
    0x0B: (12, "install resources", "four 24-bit addresses, low byte first",
           "where the instruments (0), pitch envelopes (1), songs (2) and "
           "samples (3) are in the cartridge, stored at $0AA5."),
    0x0C: (0, "pause all", "-",
           "clear flag 4 (running) on every voice and release every channel "
           "whose voice is not running (L0CFB).  The voices keep their "
           "place; $0D carries on from it."),
    0x0D: (0, "resume all", "-",
           "set flag 4 (running) again on every active voice that is not "
           "protected (flag 5) - L0B89.  Once listed as 'stop the music'; "
           "it is the opposite."),
    0x0E: (2, "flag 7", "voice, on/off",
           "set or clear voice flag 7, which only the channel allocator "
           "reads ($1815): a voice with it set is not given its own free "
           "channel back first."),
    0x10: (1, "play song", "song",
           "start song n from resource 2: every free voice (not active, not "
           "protected) gets one of its tracks and the flags $11 - active "
           "and running (L0BDF)."),
    0x12: (1, "stop song", "song, or $FF for all",
           "free every unprotected voice playing song n and release their "
           "channels (L0CA0)."),
    0x14: (2, "priority", "voice, priority",
           "voice+28: how hard the voice holds its channel when channels "
           "are handed out (L1676, L1836)."),
    0x16: (0, "reset voices", "-",
           "free all sixteen voices outright, protected or not, and release "
           "the channels."),
    0x17: (3, "mute track", "song, track, 1 mute / 0 sound",
           "set or clear flag 1 (muted) on the voice playing that track of "
           "that song: a muted voice keeps time but plays no notes."),
    0x1A: (2, "sample rate", "slot, rate",
           "for an instrument slot holding a sample instrument (type 1), "
           "replace byte 1 - the DAC rate nibble."),
    0x1B: (2, "set variable", "variable, value",
           "write one of the song variables at $1B22, the ones track "
           "commands $70 and $71 set and test; the 68000 can read them back "
           "straight out of Z80 RAM."),
    0x1C: (1, "protect", "voice",
           "set flag 5: pause, resume, stop-song and play-song all leave "
           "the voice alone."),
    0x1D: (1, "unprotect", "voice", "clear flag 5."),
    0x1E: (4, "detune a track", "song, track, low, high",
           "find the voice playing that track of that song and detune it "
           "as $04 does; if none is, the two detune bytes are read and "
           "dropped."),
    0x1F: (2, "voice attenuation", "voice, amount",
           "voice+30, added to the master attenuation when a note starts "
           "(L1208).  Track command $72 5 does the same."),
    0x20: (1, "master attenuation", "amount",
           "$15D1, added to every voice's own when a note starts.  The sum "
           "turns the FM carriers down: TL becomes TL + (127 - TL) x "
           "sum / 128 (L15F7), so 0 leaves an instrument as it is and 127 "
           "silences it, and a sum past 127 is taken as 127.  Track command "
           "$72 4 does the same."),
}
CMD_ARGS = {op: v[0] for op, v in COMMANDS.items()}
CMD_NAME = {op: v[1] for op, v in COMMANDS.items()}

# The nineteen track commands, $60 + k, read from the switch at $0570.
#   (name, argument bytes, arguments, what it does)
TRACK = [
    ("end", 0, "-", "free the voice: flags, gate and all (L0606)."),
    ("instrument", 1, "instrument",
     "load instrument n into the voice's slot (L0613)."),
    ("envelope", 1, "envelope",
     "give the voice pitch envelope n and start it, unless it retriggers "
     "on every note anyway (L05C0)."),
    ("rest", 0, "-", "nothing; the delay that follows is the rest."),
    ("loop", 1, "count",
     "push a loop: the count and the address after it, onto the voice's "
     "four-deep stack at voice+16 (L0621); endloop searches it from "
     "+25 down (L064C)."),
    ("endloop", 0, "-",
     "count the innermost loop down and go back to its start, or pop it "
     "when it runs out; a count of 127 loops for ever (L064C)."),
    ("retrigger", 1, "on/off",
     "flag 6: restart the pitch envelope with every note (L05DD)."),
    ("flag7", 1, "on/off",
     "set or clear flag 7 (L05F2), which the channel allocator reads "
     "($1815): the voice is not given its own free channel back first."),
    ("tempo", 1, "tempo",
     "set the music clock, as driver command $05 does with 40 added "
     "(L068B)."),
    ("mute", 1, "bit 4 clear mute / set sound, bits 0-3 track",
     "mute or sound another track of this same song (L0696)."),
    ("priority", 1, "priority",
     "voice+28, as driver command $14 (L06D3)."),
    ("song", 1, "song",
     "start another song, as driver command $10 (L06DC)."),
    ("detune", 2, "low, high",
     "the voice's pitch offset, 8.8 semitones (L06EB)."),
    ("frameclock", 0, "-",
     "flag 3: run this voice on the frame clock - once a frame, whatever "
     "the tempo - instead of the music clock (L070C)."),
    ("rate", 1, "rate",
     "if the voice's instrument is a sample, set its rate nibble "
     "(L0713)."),
    ("jump", 2, "signed 16-bit offset",
     "go on reading that many bytes further on, counted from after the "
     "offset (L0725)."),
    ("set", 2, "variable, value",
     "song variable n = value (L074B)."),
    ("branch", 4, "variable, test, value, offset",
     "if the test holds, skip forward the offset - one unsigned byte, "
     "counted from after it (L0752)."),
    ("ext", 2, "sub-command, value",
     "one of six: 0 stop song n, 1 pause song n, 2 resume all, 3 pause "
     "the song whose number is in variable 0, 4 master attenuation, 5 "
     "this voice's attenuation (L07A6)."),
]
SEQ = [(name, n) for name, n, _, _ in TRACK]

# `branch`'s tests, as `variable <test> value`: the handler does CP (HL)
# with the value in A and the variable at (HL).  An earlier table had 2 to
# 5 the wrong way round.
CMP = ["?", "==", "<=", "<", ">=", ">", "!="]

# The YM2612 runs at the master clock over seven and counts timer A at a
# 144th of that.  A sample's flags byte carries the timer's period in its
# low nibble - the driver at $01370 writes registers $24 and $25 with the
# negated nibble - so one byte leaves the DAC every `k` timer ticks and the
# sample's rate is this over `k`.
#
# The cartridge is the European one - region "E" at $1F0 - and runs on a
# PAL machine, so the master clock is 53203424 Hz and not the NTSC
# 53693175: the YM2612 gets 7600489 Hz and the timer 52781 Hz.
YM_TICK = 7600489 / 144            # 52781 Hz, the PAL cartridge

# The game's own names for its sounds, and which song each one is.  The
# names sit at $020870, 58 of 16 bytes, but their order there is not the
# song numbering.  What joins a name to a song is the options screen's two
# test lists: the music test at $087F3C (18 records) and the sound test at
# $087FD4 (40), each a (name pointer, song number) pair ended by a zero
# longword.  The music test hands the number straight to snd_song_start
# ($0212A2, from $87F40), so this is the game's own map.  Read through it,
# song 40 is "positive select" - the button click at 13 call sites - and
# the sampled songs 64-83 hold the explosions, gunfire and screams as well
# as the speech.
SOUND_NAMES = 0x020870
SOUND_NAMES_N = 58
SOUND_TESTS = (0x087F3C, 0x087FD4)


def sound_names(rom):
    """song number -> the name the options screen shows for it."""
    out = {}
    for a in SOUND_TESTS:
        while True:
            p = int.from_bytes(rom[a:a + 4], "big")
            if not p:
                break
            assert SOUND_NAMES <= p < SOUND_NAMES + 16 * SOUND_NAMES_N
            song = int.from_bytes(rom[a + 4:a + 8], "big")
            assert song not in out, song
            out[song] = rom[p:p + 15].decode("latin1").strip()
            a += 8
    return out


def sound_name(rom, i):
    return sound_names(rom).get(i, "")


def sample_rate(flags):
    k = flags & 0x0F
    return YM_TICK / k if k else 0


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def s8(v):
    return v - 0x100 if v & 0x80 else v


def call_sites(rom, target):
    """Every place the 68000 calls or jumps to `target`.

    All five shapes matter, and one of them is why the sound looked dead
    the first time it was looked at: this library is called with `jsr
    $1624.w`, absolute *short*, which is `4EB8` and not the `4EB9` a
    long-address call would be.
    """
    out = []
    for i in range(0, len(rom) - 6, 2):
        w = int.from_bytes(rom[i:i + 2], "big")
        t = None
        if w in (0x4EBA, 0x4EFA, 0x6100, 0x6000):
            t = i + 2 + s16(int.from_bytes(rom[i + 2:i + 4], "big"))
        elif rom[i] in (0x60, 0x61) and rom[i + 1] not in (0x00, 0xFF):
            t = i + 2 + s8(rom[i + 1])
        elif w in (0x4EB9, 0x4EF9):
            t = int.from_bytes(rom[i + 2:i + 6], "big")
        elif w in (0x4EB8, 0x4EF8):
            t = s16(int.from_bytes(rom[i + 2:i + 4], "big")) & 0xFFFFFF
        if t == target:
            out.append(i)
    return out


def resource_sets(rom):
    """The four pointers each `jsr $1624` hands the driver.

    They are the four `pea.l` immediately in front of it, and the last one
    pushed is the first argument, so they come out in reverse.  A set of
    four identical pointers is the library's own way of saying "nothing":
    both of those in this cartridge point at four `$FF` bytes.
    """
    sets = []
    for site in call_sites(rom, API_INIT):
        peas, a = [], site - 6
        while len(peas) < 4 and a > 0:
            if int.from_bytes(rom[a:a + 2], "big") != 0x4879:
                break
            peas.append(int.from_bytes(rom[a + 2:a + 6], "big"))
            a -= 6
        if len(peas) != 4:
            continue
        empty = len(set(peas)) == 1
        sets.append((site, peas, empty))
    return sets


def vlq(rom, p):
    """The driver's variable-length number: six bits a byte, top first,
    ended by the first byte that does not carry the same two top bits."""
    v = rom[p] & 0x3F
    top = rom[p] & 0xC0
    p += 1
    while p < len(rom) and rom[p] & 0xC0 == top:
        v = ((v << 6) | (rom[p] & 0x3F)) & 0xFFFF
        p += 1
    return v, p


def track(rom, start, limit=0x4000):
    """One track's events, from its first byte to its `end`."""
    out, p, seen = [], start, set()
    while p < len(rom) and p - start < limit:
        if p in seen:
            out.append((p, "loops back here", ()))
            break
        seen.add(p)
        a, b = p, rom[p]
        if b & 0x80:
            v, p = vlq(rom, p)
            out.append((a, "gate" if not b & 0x40 else "delay", (v,)))
            continue
        if b < 0x60:
            out.append((a, "note", (b,)))
            p += 1
            continue
        k = b - 0x60
        if k >= len(SEQ):
            out.append((a, f"bad ${b:02X}", ()))
            break
        name, n = SEQ[k]
        args = tuple(rom[p + 1:p + 1 + n])
        p += 1 + n
        out.append((a, name, args))
        if name == "end":
            break
        if name == "jump":
            p = a + 3 + s16(args[0] | (args[1] << 8))
    return out


def show(ev):
    a, name, args = ev
    if name == "note":
        return f"  ${a:06X}  note   ${args[0]:02X}"
    if name in ("gate", "delay"):
        return f"  ${a:06X}  {name:<6} {args[0]}"
    if name == "jump":
        d = s16(args[0] | (args[1] << 8))
        return f"  ${a:06X}  jump   {d:+d} -> ${a + 3 + d:06X}"
    if name == "set":
        return f"  ${a:06X}  set    var {args[0]} = {args[1]}"
    if name == "branch":
        op = CMP[args[1]] if args[1] < len(CMP) else f"op{args[1]}"
        return (f"  ${a:06X}  branch var {args[0]} {op} {args[2]}"
                f" -> {args[3]:+d}")
    if args:
        return f"  ${a:06X}  {name:<6} " + " ".join(str(x) for x in args)
    return f"  ${a:06X}  {name}"


def directory(rom, base, size):
    """The offsets of a resource directory, and how many there are: the
    first offset over the entry size, because entry 0 follows the list."""
    first = struct.unpack_from("<H", rom, base)[0]
    n = first // size
    return [struct.unpack_from("<H", rom, base + i * 2)[0] for i in range(n)]


def instruments(rom, base):
    """Resource 0: 39-byte sound slots.  A record can be shorter than 39 -
    the driver always reads 39 and uses what the type byte needs - so the
    length here is the distance to the next record that starts after it."""
    offs = directory(rom, base, 2)
    out = []
    for i, o in enumerate(offs):
        later = [x for x in offs if x > o]
        out.append((i, base + o, (min(later) - o) if later else 0x27))
    return out


def envelopes(rom, base):
    """Resource 1: (ticks, signed 16-bit step) triples after a two-byte
    header, ended by a zero byte.  Returns the steps, or None if the
    entry does not parse that way."""
    offs = directory(rom, base, 2)
    out = []
    for i, o in enumerate(offs):
        p, steps = base + o + 2, []
        while p < len(rom) and rom[p] != 0:
            steps.append((rom[p], s16(struct.unpack_from("<H", rom, p + 1)[0])))
            p += 3
        end = p + 1
        later = [x for x in offs if x > o]
        want = base + min(later) if later else end
        out.append((i, base + o, steps, end == want))
    return out


def samples(rom, base):
    """Resource 3: 12-byte descriptors indexed by note - a flags byte, a
    24-bit offset from the directory, a 16-bit offset added to it, and a
    16-bit length."""
    n = int.from_bytes(rom[base + 1:base + 4], "little") // 12
    out = []
    for i in range(n):
        a = base + i * 12
        out.append((i, rom[a],
                    int.from_bytes(rom[a + 1:a + 4], "little"),
                    struct.unpack_from("<H", rom, a + 4)[0],
                    struct.unpack_from("<H", rom, a + 6)[0]))
    return out


VOICE_KIND = {0: "FM", 1: "sampled", 2: "PSG tone", 3: "PSG noise"}


def song_voices(rom, base, b0, b3):
    """What each song actually makes a noise with.

    A note is a pitch; whether it comes out of the FM chip, the PSG or the
    DAC is the *instrument's* business, and the track's `patch` says which
    instrument.  Type 1 is the sampled one - it takes YM2612 channel 6,
    which is the DAC channel - and only there does a note index the sample
    table.  This is what says which of the Mega Drive's effects are
    synthesised (songs 20-44) and which sampled (64-83, the speech and
    the explosions, gunfire, screams and the worm alike).
    """
    kinds = {i: rom[a] for i, a, _ in instruments(rom, b0)}
    have = {i for i, _, _, _, n in samples(rom, b3) if n}
    out = {}
    for i, _, tr in songs(rom, base):
        used, smp = set(), []
        for t in tr:
            cur = None
            for _, name, args in track(rom, t):
                if name == "instrument":
                    cur = kinds.get(args[0])
                    if cur is not None:
                        used.add(cur)
                elif name == "note" and cur == 1:
                    k = (args[0] - 0x30) % 0x60
                    if k in have and k not in smp:
                        smp.append(k)
        out[i] = (sorted(used), smp)
    return out


def songs(rom, base):
    """The directory at `base`: a list of 16-bit offsets into itself, as
    many of them as the first offset allows before song 0's header."""
    first = struct.unpack_from("<H", rom, base)[0]
    out = []
    for i in range(first // 2):
        off = struct.unpack_from("<H", rom, base + i * 2)[0]
        hdr = base + off
        n = rom[hdr]
        tr = [base + struct.unpack_from("<H", rom, hdr + 1 + k * 2)[0]
              for k in range(n)]
        out.append((i, hdr, tr))
    return out


def dispatch(drv):
    """The driver's own command table, out of the `CP n / JP Z,handler`
    chain its main loop is written as."""
    out, p = {}, DISPATCH
    while p + 5 < len(drv) and drv[p] == 0xFE and drv[p + 2] == 0xCA:
        out[drv[p + 1]] = drv[p + 3] | (drv[p + 4] << 8)
        p += 5
    return out


def check(rom, base):
    """Every byte from the directory to the end of the last track, claimed
    exactly once.  Returns (claimed, distinct, span)."""
    ss = songs(rom, base)
    claimed, cov, hi = 2 * len(ss), set(range(base, base + 2 * len(ss))), base
    for _, hdr, tr in ss:
        n = 1 + 2 * rom[hdr]
        claimed += n
        cov |= set(range(hdr, hdr + n))
        for t in tr:
            end = track(rom, t)[-1][0] + 1
            claimed += end - t
            cov |= set(range(t, end))
            hi = max(hi, end)
    return claimed, len(cov), hi - base


def commands_text(rom, senders):
    """commands.txt: the driver's two languages, written to be read.

    `senders` is {opcode: [(wrapper address, sites in the game)]}."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import sega_names
    names = {}
    for path in sorted(sega_names.NAMES.glob("*.txt")):
        for _, a, name, _ in sega_names.read(path):
            names[a] = name

    def para(text, indent=7):
        return textwrap.wrap(text, 72 - indent, initial_indent=" " * indent,
                             subsequent_indent=" " * indent)

    L = ["# commands.txt - how the Mega Drive Dune II talks to its sound",
         "# driver, and what its songs are made of.",
         "#",
         "# Written by tools/sega/sega_seq.py from its tables COMMANDS and",
         "# TRACK, each read out of the Z80 driver (res/sound/z80driver.asm)",
         "# handler by handler; the L labels are the driver's own.",
         "",
         "THE DRIVER",
         "",
         "The Z80 plays everything.  It has sixteen voices - a voice reads one",
         "track of a song and plays it through whatever channel it gets: six FM,",
         "three PSG tone, one noise, or the DAC.  A voice is 32 bytes at $1B80:",
         "",
         "   +3   where it is in its track (24 bits)",
         "   +6   flags: 0 active, 1 muted, 3 on the frame clock, 4 running,",
         "        5 protected, 6 retrigger the envelope on every note,",
         "        7 not given its own free channel back first ($1815)",
         "   +7   the time to its next event",
         "   +11  how long its note has left to sound",
         "   +13  its instrument          +14  the song    +15  the track",
         "   +16  its loop stack, four deep (+16 +19 +22 +25), three bytes",
         "        a loop",
         "   +28  its priority for a channel",
         "   +29  its pitch envelope",
         "   +30  its attenuation, added to the master attenuation",
         "",
         "Each voice also has a 39-byte instrument slot at $188A + 39 x voice,",
         "which instruments.txt describes field by field.",
         "",
         "There are two clocks.  The frame clock ticks once a frame - the",
         "Z80's vertical-blank interrupt, 49.7 a second: the cartridge is",
         "the European one (region E) and runs on a PAL machine.",
         "The music clock is a 16-bit accumulator the frame adds the tempo to;",
         "each time its high byte moves on, the music ticks.  A voice runs on",
         "the music clock unless its track said `frameclock`.",
         "",
         "Loudness is set by attenuation: the master attenuation ($15D1)",
         "plus the voice's own, taken when a note starts and applied to the",
         "FM carriers' level - 0 leaves the instrument as it is, 127 is",
         "silence.  Caught in the music test, a tune plays at master 9",
         "with its voices at 0, 7 and 13.",
         "",
         "",
         "THE 68000's COMMANDS",
         "",
         "The 68000 stops the Z80, writes $FF, a command and its bytes into the",
         "64-byte ring at Z80 $1B40, and lets it go.  The driver reads the ring",
         "a byte at a time and skips everything that is not $FF, so a sender",
         "that writes more bytes than a command takes does no harm - one of",
         "the 68000 library's senders, snd_drv_tempo_word, does exactly that.",
         "",
         "Of the 24, the game sends seven: install resources, play song, stop",
         "song, reset voices and mute track, and - only through two jump",
         "stubs nothing calls - pause and resume.  The rest are the library's,",
         "unused.",
         ""]
    for op in sorted(COMMANDS):
        n, name, args, what = COMMANDS[op]
        L.append(f"${op:02X}  {name}  ({n} byte{'s' if n != 1 else ''}: "
                 f"{args})")
        L += para(what)
        for w, used in senders.get(op, []):
            who = names.get(w, f"${w:06X}")
            L += para(f"sent by {who} (${w:06X})"
                      + (f", from {used} place{'s' if used != 1 else ''} "
                         "in the game" if used else ", which nothing calls"))
        L.append("")
    L += ["",
          "A SONG",
          "",
          "A song is a directory entry in resource 2: a header naming its",
          "tracks, each track a stream of bytes one voice reads.  A byte below",
          "$60 is a note; $60-$72 are the commands below; the two high forms",
          "are times:",
          "",
          "   $00-$5F  a note, played through the voice's instrument",
          "   $80-$BF  how long the note sounds (a gate)",
          "   $C0-$FF  how long until the next event (a delay)",
          "",
          "A time is a variable-length number: six bits a byte, most",
          "significant first, for as long as the bytes are of the same form;",
          "the first byte that is not ends it, and is read again as the next",
          "event.  songs_*.txt has every song written out this way.",
          "",
          "The track commands:",
          ""]
    for k, (name, n, args, what) in enumerate(TRACK):
        L.append(f"${0x60 + k:02X}  {name}  ({n} byte{'s' if n != 1 else ''}"
                 f": {args})")
        L += para(what)
        L.append("")
    L += ["`branch`'s tests, as `variable <test> value`:",
          "",
          "   " + "   ".join(f"{i} {c}" for i, c in enumerate(CMP) if i),
          "",
          "The song variables live at Z80 $1B22.  A track sets and tests them,",
          "the 68000 sets them with command $1B and can read them back.",
          ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/sound"))
    ap.add_argument("--wav", action="store_true",
                    help="also write every sample out as a WAV, at the rate "
                         "its flags byte asks for")
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    drv = rom[DRIVER:DRIVER_END]

    L = []
    L.append("# music.txt - what the Mega Drive Dune II's sound driver is")
    L.append("# told, and the songs it reads when it is told it.")
    L.append("#")
    L.append("# Written by tools/sega/sega_seq.py.  The driver itself is")
    L.append("# res/sound/z80driver.asm; the DAC samples are in sound.txt.")
    L.append("")

    table = dispatch(drv)
    L.append(f"## The driver's commands ({len(table)} of them)")
    L.append("#")
    L.append("# A command is $FF, an opcode, then its arguments, written")
    L.append("# into the 64-byte ring at Z80 $1B40.  `used` counts the")
    L.append("# places in the cartridge that send it.")
    L.append("")
    L.append("#  cmd  handler  args  used  what it does")
    def outside(sites):
        return [a for a in sites
                if not any(lo <= a < hi for lo, hi in LIB)]

    api = {}
    for site in call_sites(rom, API_OPEN):
        # the wrapper's own command byte is the moveq right after the call
        if rom[site + 4] == 0x70:
            api.setdefault(rom[site + 5], []).append(site)
    for op in sorted(table):
        n = CMD_ARGS.get(op, "?")
        if op == 0x0B:
            used = len(outside(call_sites(rom, API_INIT)))
        else:
            used = sum(len(outside(call_sites(rom, w)))
                       for w in api.get(op, []))
        L.append(f"  ${op:02X}   ${table[op]:04X}    {str(n):>4}  {used:>4}"
                 f"  {CMD_NAME.get(op, '')}")
    L.append("")

    sets = resource_sets(rom)
    L.append(f"## The resource pointers ({len(sets)} installations)")
    L.append("#")
    L.append("# Command $0B hands the driver four 24-bit addresses.  It")
    L.append("# reads its sounds through the first two, its songs through")
    L.append("# the third and its samples through the fourth.  Four")
    L.append("# identical pointers mean nothing is installed: both of")
    L.append("# those here point at four $FF bytes.")
    L.append("")
    real = []
    for site, peas, empty in sets:
        who = "empty" if empty else "sounds/sounds/songs/samples"
        L.append(f"  jsr at ${site:06X}   "
                 + " ".join(f"${p:06X}" for p in peas) + f"   {who}")
        if not empty:
            real.append((site, peas))
    L.append("")

    for site, peas in real:
        b0, b1, b2, b3 = peas
        L.append(f"## The sound bank installed at ${site:06X}")
        L.append("#")
        L.append(f"# samples ${b3:06X}, songs ${b2:06X}, "
                 f"envelopes ${b1:06X}, instruments ${b0:06X}")
        L.append("")
        sm = samples(rom, b3)
        L.append(f"{len(sm)} samples, indexed by note.  `at` is where the")
        L.append("sample itself starts; the descriptors chain, each one")
        L.append("beginning where the one before it ended.  The rate is the")
        L.append("flags byte's low nibble read as a YM2612 timer A period -")
        L.append(f"{YM_TICK:.0f} Hz over it, on this PAL cartridge - and the")
        L.append("emulator agrees: the driver's stream pointer moves 202")
        L.append("bytes a 50 Hz frame on a nibble of 5 and 106 on a nibble")
        L.append("of 10, which is 10.0 and 5.3 kHz less the driver's own")
        L.append("overhead.")
        L.append("")
        L.append("#  n  flags       at    length     rate")
        run = None
        chain = True
        for i, fl, off, add, ln in sm:
            if ln:
                if run is not None and off != run:
                    chain = False
                run = off + ln
            L.append(f"  {i:2d}   ${fl:02X}   ${b3 + off:06X}  {ln:7d}"
                     + (f"  {sample_rate(fl):7.0f} Hz  {ln / sample_rate(fl):.2f}s"
                        if ln else "   empty"))
        L.append("")
        L.append(f"# the chain {'holds' if chain else 'DOES NOT hold'}, and "
                 f"the last sample ends at ${b3 + run:06X}"
                 + (" - the song directory" if b3 + run == b2 else ""))
        L.append("")

        ev = envelopes(rom, b1)
        L.append(f"{len(ev)} pitch envelopes: a signed start offset, then")
        L.append("(ticks, signed 16-bit step) triples ended by a zero.")
        L.append("")
        for i, a, steps, fits in ev:
            body = " ".join(f"{n}x{d:+d}" for n, d in steps) or "-"
            L.append(f"  {i:2d}  ${a:06X}  {body}"
                     + ("" if fits else "   DOES NOT FIT ITS ENTRY"))
        L.append("")

        ins = instruments(rom, b0)
        kinds = {}
        for i, a, n in ins:
            kinds[rom[a]] = kinds.get(rom[a], 0) + 1
        L.append(f"{len(ins)} instruments, by the type byte each starts "
                 "with: "
                 + ", ".join(f"type ${k:02X}: {v}" for k, v in sorted(kinds.items())))
        L.append("# The driver always reads 39 bytes into the sound slot and")
        L.append("# uses what the type needs, so a short record is not an")
        L.append("# error - `bytes` is the distance to the next one.  Type 0 is")
        L.append("# FM, 1 a sample, 2 and 3 PSG tone and noise, $63 silent;")
        L.append("# instruments.txt names every field of every one.")
        L.append("")
        for i, a, n in ins:
            L.append(f"  {i:3d}  ${a:06X}  type ${rom[a]:02X}  {n:2d} bytes  "
                     + " ".join(f"{b:02X}" for b in rom[a + 1:a + min(n, 12)]))
        L.append("")

    total = 0
    for site, peas in real:
        base = peas[2]
        ss = songs(rom, base)
        total += len(ss)
        named_songs = len(ss) > max(sound_names(rom))
        voices = song_voices(rom, base, peas[0], peas[3])
        L.append(f"## The {len(ss)} songs of the bank installed at "
                 f"${site:06X}")
        if named_songs:
            L.append(f"# named by the options screen's music and sound tests"
                     f" (${SOUND_TESTS[0]:06X}, ${SOUND_TESTS[1]:06X})")
        voices = song_voices(rom, base, peas[0], peas[3])
        L.append(f"# directory ${base:06X}, samples ${peas[3]:06X}")
        L.append("")
        for i, hdr, tr in ss:
            k, smp = voices[i]
            how = "/".join(VOICE_KIND.get(x, str(x)) for x in k)
            L.append(f"song {i:2d}  header ${hdr:06X}  {len(tr)} tracks"
                     + (f"  {sound_name(rom, i):<16}" if named_songs else "")
                     + (f"  {how}" if how else "")
                     + ("  sample " + ",".join(str(x) for x in smp)
                        if smp else ""))
            for k, t in enumerate(tr):
                ev = track(rom, t)
                notes = sum(1 for e in ev if e[1] == "note")
                L.append(f"  track {k}  ${t:06X}  {len(ev)} events,"
                         f" {notes} notes")
            L.append("")

    L.append("## The check")
    L.append("#")
    L.append("# Bytes claimed by a header or a track, against bytes that")
    L.append("# exist between the directory and the last track's end.  The")
    L.append("# three being equal says every byte is spoken for and none")
    L.append("# twice - which is not something a misread header could do.")
    L.append("")
    for site, peas in real:
        b0, b1, b2, b3 = peas
        sm = samples(rom, b3)
        last = max(o + n for _, _, o, _, n in sm)
        ev = envelopes(rom, b1)
        ins = instruments(rom, b0)
        end = max(a for _, a, _ in ins)
        L.append(f"  bank ${site:06X}")
        L.append(f"    samples end ${b3 + last:06X}, songs start ${b2:06X}"
                 f"  {'exact' if b3 + last == b2 else 'GAP'}")
        L.append(f"    envelopes end ${ev[-1][1]:06X}+, instruments start "
                 f"${b0:06X}  "
                 + ("all fit" if all(f for *_, f in ev) else "A GAP"))
        L.append(f"    last instrument at ${end:06X}, type {rom[end]}"
                 f" - the driver reads 39 bytes from there whatever the"
                 f" record's real length")
        c, d, span = check(rom, peas[2])
        ok = "exact" if c == d == span else "MISMATCH"
        L.append(f"  ${peas[2]:06X}  claimed {c}, distinct {d}, "
                 f"span {span}  {ok}")
        L.append(f"           ends at ${peas[2] + span:06X}, which is the "
                 f"resource installed beside it"
                 if peas[2] + span == peas[1] else
                 f"           ends at ${peas[2] + span:06X}")
    L.append("")

    (out / "music.txt").write_text("\n".join(L) + "\n")
    senders = {}
    for op, sites in api.items():
        for site in sites:
            senders.setdefault(op, []).append(
                (site, len(outside(call_sites(rom, site)))))
    senders.setdefault(0x0B, []).append(
        (API_INIT, len(outside(call_sites(rom, API_INIT)))))
    (out / "commands.txt").write_text(commands_text(rom, senders))

    # the events themselves, one file a bank, because they are long
    for site, peas in real:
        base = peas[2]
        E = [f"# songs.txt - every event of every song in the bank",
             f"# installed at ${site:06X}, directory ${base:06X}.",
             "#",
             "# Written by tools/sega/sega_seq.py.  `note` is a pitch and",
             "# the voice's sound slot says what it sounds like; `gate`",
             "# is how long it sounds and `delay` how long until the next",
             "# event.", ""]
        for i, hdr, tr in songs(rom, base):
            E.append(f"song {i} at ${hdr:06X}, {len(tr)} tracks")
            for k, t in enumerate(tr):
                E.append(f" track {k} at ${t:06X}")
                for ev in track(rom, t):
                    E.append(show(ev))
            E.append("")
        (out / f"songs_{base:06X}.txt").write_text("\n".join(E) + "\n")

    if args.wav:
        d = out / "samples"
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.wav"):
            old.unlink()
        n = 0
        for site, peas in real:
            b3 = peas[3]
            for i, fl, off, add, ln in samples(rom, b3):
                if not ln:
                    continue
                w = wave.open(str(d / f"{b3:06X}_{i:02d}.wav"), "wb")
                w.setnchannels(1)
                w.setsampwidth(1)
                w.setframerate(int(round(sample_rate(fl))))
                w.writeframes(rom[b3 + off:b3 + off + ln])
                w.close()
                n += 1
        print(f"{n} samples -> {d}")

    bad = [f"${peas[2]:06X}" for _, peas in real
           if len(set(check(rom, peas[2]))) != 1]
    print(f"{len(table)} driver commands, {len(real)} sound banks, "
          f"{total} songs -> {out}/music.txt")
    if bad:
        raise SystemExit("the song banks at " + ", ".join(bad) +
                         " do not add up: see the check in music.txt")


if __name__ == "__main__":
    main()
