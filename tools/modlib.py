#!/usr/bin/env python3
"""modlib.py - ProTracker modules, written and read back, for the General
Sound card.

Not a command of its own: `tools/sega/sega_mod.py` builds its modules
through this, and anything that wants to look inside one reads it here.

    python3 tools/modlib.py FILE.mod      # what is in a module

## The format, as the card's ROM reads it

A module is the 4-channel "M.K." ProTracker layout: a 20-byte title, 31
sample headers of 30 bytes, the order list, the four-byte tag at 1080,
then 64-row patterns of 4 x 4 bytes and the signed 8-bit samples.

General Sound's ROM (`bin/evo/gs105a.rom`) looks for "M.K.", "M!K!",
"4CHN" or "FLT4" at 1080 (`$0D22`), and its effect tables are at `$5900`
(row start), `$5940` (every tick) and `$5980` (the `Ex` sub-commands) -
the ROM runs them at `$D900` and up.  What they say:

- `Fxx` below `$20` is the speed, from `$20` up the BPM (`$52EE`), so a
  module can be timed exactly rather than in fiftieths of a second.
- `0xy` `1xx` `2xx` `3xx` `4xy` `5xy` `6xy` `7xy` `Axy` run every tick,
  `Bxx` `Cxx` `Dxx` `Exy` `Fxx` at the row's start.
- `9xx` (sample offset) has no row-start handler in the table and is not
  used here.
- A BPM is timed by the table at `$1831`: one word per BPM from 32, the
  number of the card's 37.5 kHz interrupts a tick lasts - 93750 / BPM,
  rounded.  `gs_bpm` picks the BPM whose entry is nearest a wanted tick,
  which is what makes a module's tempo right to 0.1% on the card.  (The
  emulator's card runs its interrupt some 0.4% fast: BPM 125, exactly 750
  interrupts, measures 0.4% short in `tools/gs_modtest.py`.  That is the
  model, not the ROM.)

Only notes C-1..B-3 - periods 856 down to 113 - are written: that is
what ProTracker itself allows and every player agrees on.
"""

import struct
import sys
from pathlib import Path

# ProTracker's periods for finetune 0, C-1 .. B-3.
PERIODS = [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
           428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
           214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113]
NOTES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#",
         "B-"]
PAL_CLOCK = 3546895              # the Amiga's, which every period is of
ROWS = 64
CHANNELS = 4
MAX_SAMPLES = 31
MAX_ORDERS = 128
MAX_PATTERNS = 64                # what the "M.K." tag promises a player


GS_ROM = Path(__file__).resolve().parent.parent / "bin/evo/gs105a.rom"
GS_INT = 37500                   # the card's interrupt, a second
_bpm_table = None


def gs_bpm(tick):
    """The BPM whose tick on the General Sound card is nearest `tick`
    seconds, by the ROM's own table at $1831."""
    global _bpm_table
    if _bpm_table is None:
        if GS_ROM.exists():
            d = GS_ROM.read_bytes()
            _bpm_table = {b: d[0x1831 + 2 * (b - 32)]
                          | d[0x1832 + 2 * (b - 32)] << 8
                          for b in range(32, 256)}
        else:
            _bpm_table = {b: round(93750 / b) for b in range(32, 256)}
    want = tick * GS_INT
    return min(_bpm_table, key=lambda b: abs(_bpm_table[b] - want))


def note_name(i):
    """Index into PERIODS -> "C-1"."""
    return f"{NOTES[i % 12]}{i // 12 + 1}"


def rate_of(i):
    """Index into PERIODS -> the rate a sample plays at, in Hz."""
    return PAL_CLOCK / PERIODS[i]


class Cell:
    """One channel of one row: a note (index into PERIODS, or None), a
    sample (1..31, or 0 for "keep the one playing"), and an effect."""
    __slots__ = ("note", "sample", "fx", "arg")

    def __init__(self, note=None, sample=0, fx=0, arg=0):
        self.note, self.sample, self.fx, self.arg = note, sample, fx, arg

    def pack(self):
        per = PERIODS[self.note] if self.note is not None else 0
        return bytes([(self.sample & 0xF0) | (per >> 8), per & 0xFF,
                      ((self.sample & 0x0F) << 4) | self.fx, self.arg])

    def empty(self):
        return self.note is None and not self.sample and not self.fx \
            and not self.arg

    def __repr__(self):
        n = note_name(self.note) if self.note is not None else "---"
        s = f"{self.sample:02d}" if self.sample else ".."
        e = f"{self.fx:X}{self.arg:02X}" if self.fx or self.arg else "..."
        return f"{n} {s} {e}"


class Sample:
    """A sample: signed 8-bit data, a volume 0..64, a loop (start and
    length in bytes, both even; length 0 for none) and a finetune -8..7."""

    def __init__(self, name, data, volume=64, loop_start=0, loop_len=0,
                 finetune=0):
        self.name, self.data = name, bytes(data)
        self.volume, self.finetune = volume, finetune
        self.loop_start, self.loop_len = loop_start, loop_len

    def header(self):
        data = self.data + (b"\0" if len(self.data) & 1 else b"")
        rs, rl = self.loop_start // 2, self.loop_len // 2
        if not rl:
            rs, rl = 0, 1
        return (self.name.encode("latin1")[:22].ljust(22, b"\0")
                + struct.pack(">HBBHH", len(data) // 2, self.finetune & 15,
                              self.volume, rs, rl))


def write(path, title, samples, patterns, orders, restart=0):
    """Write a module.  `patterns` is a list of 64 rows of 4 Cells;
    `orders` the pattern numbers to play in turn."""
    assert len(samples) <= MAX_SAMPLES, f"{len(samples)} samples"
    assert len(patterns) <= MAX_PATTERNS, f"{len(patterns)} patterns"
    assert 0 < len(orders) <= MAX_ORDERS, f"{len(orders)} orders"
    out = bytearray(title.encode("latin1")[:20].ljust(20, b"\0"))
    for s in samples:
        assert len(s.data) < 0x20000, f"{s.name}: {len(s.data)} bytes"
        out += s.header()
    for _ in range(MAX_SAMPLES - len(samples)):
        out += bytes(22) + struct.pack(">HBBHH", 0, 0, 0, 0, 1)
    out += bytes([len(orders), restart & 0x7F])
    out += bytes(orders) + bytes(MAX_ORDERS - len(orders))
    out += b"M.K."
    for p in patterns:
        assert len(p) == ROWS
        for row in p:
            assert len(row) == CHANNELS
            for c in row:
                out += c.pack()
    for s in samples:
        out += s.data + (b"\0" if len(s.data) & 1 else b"")
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


def read(path):
    """A module back: (title, samples, patterns, orders, restart)."""
    d = open(path, "rb").read()
    assert d[1080:1084] in (b"M.K.", b"M!K!", b"4CHN", b"FLT4"), path
    title = d[:20].rstrip(b"\0").decode("latin1")
    hdrs = []
    for i in range(MAX_SAMPLES):
        h = d[20 + 30 * i:50 + 30 * i]
        n, ft, vol, rs, rl = struct.unpack(">HBBHH", h[22:])
        hdrs.append((h[:22].rstrip(b"\0").decode("latin1"), n * 2,
                     ft if ft < 8 else ft - 16, vol, rs * 2,
                     rl * 2 if rl > 1 else 0))
    norders, restart = d[950], d[951]
    orders = list(d[952:952 + norders])
    npat = max(d[952:952 + 128]) + 1
    per_idx = {p: i for i, p in enumerate(PERIODS)}
    patterns, p = [], 1084
    for _ in range(npat):
        rows = []
        for _ in range(ROWS):
            row = []
            for _ in range(CHANNELS):
                b = d[p:p + 4]
                per = ((b[0] & 0x0F) << 8) | b[1]
                row.append(Cell(per_idx.get(per) if per else None,
                                (b[0] & 0xF0) | (b[2] >> 4), b[2] & 0x0F,
                                b[3]))
                p += 4
            rows.append(row)
        patterns.append(rows)
    samples = []
    for name, n, ft, vol, rs, rl in hdrs:
        samples.append(Sample(name, d[p:p + n], vol, rs, rl, ft))
        p += n
    return title, samples, patterns, orders, restart


def main():
    title, samples, patterns, orders, restart = read(sys.argv[1])
    print(f"{sys.argv[1]}: \"{title}\", {len(orders)} orders, "
          f"{len(patterns)} patterns, restart {restart}")
    for i, s in enumerate(samples, 1):
        if s.data:
            loop = (f" loop {s.loop_start}+{s.loop_len}" if s.loop_len
                    else "")
            print(f"  {i:2d} {s.name:<22} {len(s.data):6d} bytes"
                  f" vol {s.volume}{loop}")


if __name__ == "__main__":
    main()
