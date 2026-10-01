#!/usr/bin/env python3
"""sega_instr.py - what the Mega Drive Dune II's sounds are made of.

    sega_instr.py [--rom orig/dune2.gen] [--out orig/sega/res/sound]
                  [--touch tmp/sega/snap/touch.bin]

`sega_seq.py` takes the songs apart into notes, but a note is only a
pitch.  What it sounds like is the *instrument* the track last chose with
`patch`, and the driver keeps sixteen of those at Z80 `$188A`, 39 bytes
each, one a voice.  They come out of resource 0 of the two banks command
`$0B` installs, and the pitch envelopes a track starts with `bend` come
out of resource 1.  This decodes both, every field named by the Z80
instruction that reads it.  Writes `instruments.txt`.

## How the record was read

`$1739` copies an instrument in: it looks the number up in resource 0's
directory and always copies `$27` bytes into the voice's slot, whatever
the record is.  `$1208` plays a note through the slot and does nothing but
look at byte 0 and jump:

    $1226  ld a,(hl)     ; byte 0 of the slot
           cp 0 -> $1431 ; FM: channels at $1795 (FM1-6)
           cp 1 -> $12F9 ; sample: the DAC channel at $17B1 (FM6)
           cp 2 -> $1245 ; PSG tone: channels at $17C0 (tone 0-2)
           cp 3 -> $123C ; PSG noise: the channel at $17D6
           ret           ; anything else is silence ($FF is "empty",
                         ; which is what the reset at $08D8 writes)

and from there each kind reads the bytes it needs and no others:

- **FM**, `$1485`: byte 1 is register `$22` (the LFO), written only if its
  enable bit 3 is set.  Byte 2's top two bits go to register `$27`, the
  channel 3 mode, and bit 6 of it both claims FM3 alone (`$1434`) and
  swaps the normal `$A4/$A0` frequency for bytes 29-36, which go to
  `$A6,$A2,$AC,$A8,$AD,$A9,$AE,$AA` - FM3's four per-operator frequencies
  (`$1524-$15A5`).  The rest is written by walking the list at `$161E`,
  pairs of (register, byte of the slot less one): `$B0` from byte 3,
  `$B4` from byte 4, then `$30,$40,$50,$60,$70,$80` from bytes 5-10, 17-22,
  11-16 and 23-28 for the operators at register offsets +0, +8, +4 and +C
  - so the record keeps them in register order, +0 +4 +8 +C.  `$90`
  (SSG-EG) is in the list with a literal 0, not a byte of the record.
  Bytes of the list with bit 7 set are the four TLs, and for each one the
  driver rotates a carrier mask out of `$15C8` - `08 08 08 08 0A 0E 0E
  0F`, indexed by the algorithm in byte 3 - and, for a carrier, adds the
  voice's volume to it.  Byte 37's low nibble is the operator mask of the
  key-on (`$15A8`, register `$28`).  Byte 38 is copied and never read.
- **Sample**, `$12F9`: the note picks the sample, `(note - $30) mod $60`,
  as a 12-byte descriptor of resource 3 (`$132E-$1355`).  Byte 1, unless it
  is 4, replaces the descriptor's rate nibble (`$1366-$1376`); command `$1A`
  and track command `$6E` both write that byte, and both only if byte 0
  is 1.  The instrument names no sample at all.
- **PSG**, `$1260`: bytes 1-6 go to the channel's record at `$0009`,
  which the envelope routine at `$0066` runs every tick.  Byte 1 is the
  noise register's low bits (`$12C0`, written as `$E0|x` at `$00B3`);
  byte 2 the attack step (`+8`), byte 3 the sustain level (`<<4`, `+16`),
  byte 4 the peak level (`<<4`, `+36`), byte 5 the decay step (`+12`),
  byte 6 the release step (`+20`).  They are *attenuations*: the channel
  starts at `$FF`, silent, and `$0185` writes the top nibble to the PSG
  as `$90|n`, where 0 is loudest.  Attack steps down to the peak, decay
  moves to the sustain level from either side, key-off (bit 1 of the
  channel's flags) starts release, which climbs until it overflows.

A pitch envelope (`$0E2F`) is a signed 16-bit starting offset and then
`(ticks, signed 16-bit step)` triples ended by a tick count of 0
(`$0EFD-$0F16`).  The offset is added to the note as 8.8 semitones -
`$10AA` adds its high byte to the note and uses its low byte to
interpolate between two entries of the frequency table - so a step of 5
is 5/256 of a semitone a tick.  **The driver copies only 32 bytes of an
envelope** (`ld c,$20` at `$0E8D`, into one of four buffers at
`$1E80-$1EFF`): a header and ten triples.  Anything longer runs off the
end of its buffer into the next one.

## What proves it

Three things, and none of them is the data looking plausible:

- Both tables parse into whole records that fill their regions exactly.
  Each directory is 16-bit offsets whose first entry says how many there
  are; the records follow in directory order, each exactly as long as its
  kind (39, 7, 2 or 1 bytes), and the last one ends where the next thing
  begins: the envelopes at their bank's instrument directory, the game's
  instruments at `$0FECE4` (TEAM.EMC's function table) and the front
  end's at `$0D0663` (the game bank's sample directory).
- The Z80's own reads agree to the byte.  `tmp/sega/snap/touch.bin` has
  bit 4 set on every cartridge byte the Z80 read while the game was
  played.  An instrument loaded costs its directory word and 39 bytes from
  its start, an envelope its directory word and 32; predicted from which
  records were read at all, that accounts for every byte the trace holds
  - bar the song reader's 16-byte fetch running past the last track, and
  four directory words past the front end's tables, which are lookups of
  numbers that bank does not have (neither lookup is bounds-checked).  In
  particular the last 31 bytes of the game's two 63-byte vibratos were
  never read by anything.

And a Z80 RAM dump taken while the options screen's music test plays
holds, in each voice's slot, exactly the 39 bytes of the instrument the
voice's byte 13 names; in each busy envelope buffer, the first 32 bytes of
an envelope; and in each PSG channel record the attack, levels, decay and
release of its instrument, shifted as described.  The constants this file
leans on - the two copy lengths, the carrier masks, the register list -
are read back out of the driver on every run and compared.
"""

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_seq import (DRIVER, resource_sets, samples, songs,  # noqa: E402
                      track, s16, sample_rate, sound_name)

ROOT = Path(__file__).resolve().parent.parent.parent

SLOT = 0x27                 # $1760: ld c,$27 - the bytes copied per load
ENV_COPY = 0x20             # $0E8D: ld c,$20 - the bytes copied per bend

KIND = {0: "FM", 1: "sample", 2: "PSG tone", 3: "PSG noise"}
# the length the records actually have in the cartridge
SIZE = {0: 39, 1: 2, 2: 7, 3: 7}

# $15C8: the carrier mask per algorithm, a bit per TL in list order
CARRIERS = [0x08, 0x08, 0x08, 0x08, 0x0A, 0x0E, 0x0E, 0x0F]
# $161E: (register, slot byte) pairs; the byte is IX+d and IX is slot+1
REG_LIST = [(0xB0, 3), (0xB4, 4)]
for _base, _first in ((0, 5), (8, 17), (4, 11), (0xC, 23)):
    for _k, _reg in enumerate((0x30, 0x40, 0x50, 0x60, 0x70, 0x80)):
        REG_LIST.append((_reg + _base, _first + _k))
# $1528-$15A5: FM3's special-mode frequencies, register per slot byte
SPECIAL = [(0xA6, 29), (0xA2, 30), (0xAC, 31), (0xA8, 32),
           (0xAD, 33), (0xA9, 34), (0xAE, 35), (0xAA, 36)]
OPS = [("+0", 5), ("+4", 11), ("+8", 17), ("+C", 23)]
# the order the TLs are met in the list, so the order the mask is rotated
TL_ORDER = ["+0", "+8", "+4", "+C"]
# what bytes 29-36 hold in an FM record that is not special mode
FILLER = bytes([0x1F, 0xFF] * 4)
NOISE = ["N/512", "N/1024", "N/2048", "tone 2"]


def driver_check(rom):
    """The constants above, read back out of the driver in the cartridge,
    so that this file cannot drift from the code it describes."""
    z = rom[DRIVER:DRIVER + 0x188A]
    lst, p = [], 0x161E
    while z[p]:
        lst.append((z[p], (z[p + 1] & 0x7F) + 1 if z[p + 1] else None))
        p += 2
    fm = [(r, b) for r, b in lst if b is not None]
    zero = sorted(r for r, b in lst if b is None)
    return [
        ("copy per instrument, ld c,n at $1760", z[0x1760:0x1762],
         bytes([0x0E, SLOT])),
        ("copy per envelope, ld c,n at $0E8D", z[0x0E8D:0x0E8F],
         bytes([0x0E, ENV_COPY])),
        ("carrier masks at $15C8", z[0x15C8:0x15D0], bytes(CARRIERS)),
        ("register list at $161E", fm, REG_LIST),
        ("registers written 0 by it", zero, [0x90, 0x94, 0x98, 0x9C]),
    ]


def u16(rom, a):
    return struct.unpack_from("<H", rom, a)[0]


def table(rom, base):
    """A resource directory: 16-bit offsets from `base`, as many as the
    first offset leaves room for."""
    n = u16(rom, base) // 2
    return [base + u16(rom, base + 2 * i) for i in range(n)]


def instrument_records(rom, base):
    """[(n, addr, type, length by type, length to the next)]."""
    addrs = table(rom, base)
    out = []
    for i, a in enumerate(addrs):
        t = rom[a]
        want = SIZE.get(t, 1)
        gap = addrs[i + 1] - a if i + 1 < len(addrs) else None
        out.append((i, a, t, want, gap))
    return out


def envelope_records(rom, base):
    """[(n, addr, start offset, [(ticks, step)], length)]."""
    out = []
    for i, a in enumerate(table(rom, base)):
        start = s16(u16(rom, a))
        p, steps = a + 2, []
        while rom[p]:
            steps.append((rom[p], s16(u16(rom, p + 1))))
            p += 3
        out.append((i, a, start, steps, p + 1 - a))
    return out


def fm_lines(r):
    """An FM record's fields, as lines."""
    alg, fb = r[3] & 7, (r[3] >> 3) & 7
    pan = {0xC0: "L+R", 0x80: "L", 0x40: "R", 0: "off"}[r[4] & 0xC0]
    lfo = (f"LFO on, rate {r[1] & 7}" if r[1] & 8
           else "LFO register not written")
    special = bool(r[2] & 0x40)
    L = [f"      $22 {r[1]:02X} {lfo}   $27 mode bits {r[2] & 0xC0:02X}"
         f"{' - FM3 special mode, FM3 only' if special else ''}",
         f"      $B0 {r[3]:02X} alg {alg} fb {fb}   "
         f"$B4 {r[4]:02X} pan {pan} ams {(r[4] >> 4) & 3} fms {r[4] & 7}"
         f"   key-on ops {r[37] & 0x0F:X}"
         + (f" (top nibble {r[37] >> 4:X})" if r[37] >> 4 else ""),
         "      op  DT MUL  TL KS AR AM D1R D2R SL RR   carrier"]
    mask = CARRIERS[alg]
    car = {op: bool(mask >> k & 1) for k, op in enumerate(TL_ORDER)}
    for name, f in OPS:
        dm, tl, ra, dr, d2, sr = r[f:f + 6]
        L.append(f"      {name:>2}  {dm >> 4 & 7:>2} {dm & 15:>3} {tl & 0x7F:>3}"
                 f" {ra >> 6:>2} {ra & 31:>2} {dr >> 7:>2} {dr & 31:>3}"
                 f" {d2 & 31:>3} {sr >> 4:>2} {sr & 15:>2}"
                 f"   {'yes' if car[name] else ''}")
    if special:
        fr = []
        for k in range(0, 8, 2):
            hi, lo = r[SPECIAL[k][1]], r[SPECIAL[k + 1][1]]
            fr.append(f"${SPECIAL[k][0]:02X}/${SPECIAL[k + 1][0]:02X}"
                      f" block {hi >> 3 & 7} fnum {(hi & 7) << 8 | lo}")
        L.append("      FM3 freqs: " + ", ".join(fr))
    elif bytes(r[29:37]) != FILLER:
        L.append("      bytes 29-36, unused here: "
                 + " ".join(f"{b:02X}" for b in r[29:37]))
    return L


def usage(rom, b0, b1, b2, b3):
    """Which songs pick each instrument and each envelope, and which
    samples each sample instrument's notes select."""
    kinds = {i: rom[a] for i, a, *_ in instrument_records(rom, b0)}
    nsamp = len(samples(rom, b3))
    ins, env, smp = {}, {}, {}
    for s, _, tr in songs(rom, b2):
        for t in tr:
            cur = None
            for _, name, args in track(rom, t):
                if name == "instrument":
                    cur = args[0]
                    ins.setdefault(cur, set()).add(s)
                elif name == "envelope":
                    env.setdefault(args[0], set()).add(s)
                elif name == "note" and cur is not None and kinds.get(cur) == 1:
                    k = (args[0] - 0x30) % 0x60
                    smp.setdefault(cur, set()).add(k if k < nsamp else -k)
    return ins, env, smp


def songs_str(ss, bank_is_game):
    out = []
    for s in sorted(ss):
        nm = sound_name_safe(s) if bank_is_game else ""
        out.append(f"{s}" + (f" ({nm})" if nm else ""))
    return ", ".join(out)


_ROM = None


def sound_name_safe(s):
    return sound_name(_ROM, s) if _ROM else ""


def trace_check(touch, rom, b0, b1, inst, envs):
    """Explain every byte the Z80 was seen to read, and nothing more.

    A load reads the record's directory word and a fixed window from its
    start: 39 bytes for an instrument, 32 for an envelope.  So a record
    counts as loaded when its word and its whole window were read, and
    then every byte read in these regions has to be one of those - or
    the song reader's overrun, below.  A byte past a window is the test:
    had the driver copied more than 32 bytes of an envelope, the long
    ones would show it.  Returns lines of report and a boolean."""
    lo = b1
    hi = inst[-1][1] + inst[-1][3]
    seen = {a for a in range(lo, hi) if touch[a] & 0x10}

    def got(r):
        return all(touch[a] & 0x10 for a in r)

    want, loaded_i, loaded_e = set(), [], []
    for i, a, *_ in inst:
        w, win = range(b0 + 2 * i, b0 + 2 * i + 2), range(a, a + SLOT)
        if got(w) and got(win):
            loaded_i.append(i)
            want |= set(w) | set(win)
    for i, a, *_ in envs:
        w, win = range(b1 + 2 * i, b1 + 2 * i + 2), range(a, a + ENV_COPY)
        if got(w) and got(win):
            loaded_e.append(i)
            want |= set(w) | set(win)
    # The track reader ($042D) fetches 16 bytes at a time, so the songs,
    # which end where the envelope directory begins, are read up to 15
    # bytes past their end.
    prefetch = {a for a in range(lo, lo + 15) if a in seen and a not in want}
    extra = seen - want - prefetch
    # Neither lookup checks its number against the table: $0E6B doubles
    # an envelope number into C alone, so it wraps at 128, and $1739
    # doubles an instrument number into DE.  A word read past the end of
    # a directory is such a lookup of a number the bank does not have.
    stray = []
    for a in sorted(extra):
        if a + 1 not in extra or a in {x + 1 for x, _ in stray}:
            continue
        k = a - b1
        if 0 <= k < 256 and not k & 1 and k // 2 >= len(envs):
            stray.append((a, f"envelope {k // 2} (or {k // 2 + 128})"))
            continue
        k = a - b0
        if k >= 0 and not k & 1 and k // 2 >= len(inst):
            stray.append((a, f"instrument {k // 2}"))
    for a, _ in stray:
        extra -= {a, a + 1}
    ok = not extra
    L = [f"  Z80 reads ${lo:06X}-${hi - 1:06X}: {len(seen)} bytes, explained"
         f" by {len(loaded_i)} instrument and {len(loaded_e)} envelope loads"
         + (f" and {len(prefetch)} of the song reader's overrun"
            if prefetch else "")
         + (f" and {len(stray)} out-of-range lookups" if stray else "")
         + (" - every byte" if ok else f" - {len(extra)} NOT explained")]
    for i, a, start, steps, n in envs:
        if n > ENV_COPY and i in loaded_e:
            past = [x for x in range(a + ENV_COPY, a + n) if touch[x] & 0x10]
            L.append(f"    envelope {i}: {n} bytes, first {ENV_COPY} read,"
                     f" {n - ENV_COPY - len(past)} of the other"
                     f" {n - ENV_COPY} never read")
    for a, what in stray:
        L.append(f"    ${a:06X}: the directory word of {what}, past the"
                 " end of the table - a lookup of a number this bank lacks")
    for a in sorted(extra)[:8]:
        L.append(f"    read and not explained: ${a:06X}")
    return L, ok


def bank(rom, touch, site, peas, is_game):
    b0, b1, b2, b3 = peas
    inst = instrument_records(rom, b0)
    envs = envelope_records(rom, b1)
    ins_use, env_use, smp_use = usage(rom, b0, b1, b2, b3)
    sm = samples(rom, b3)
    L, checks = [], []

    L.append(f"## The bank installed at ${site:06X}")
    L.append("#")
    L.append(f"# envelopes ${b1:06X} ({len(envs)}), "
             f"instruments ${b0:06X} ({len(inst)}), "
             f"samples ${b3:06X} ({len(sm)})")
    L.append("")

    # -- envelopes
    L.append("### Pitch envelopes")
    L.append("#")
    L.append("# start: the offset the note begins at, in 1/256 semitone.")
    L.append("# Then ticks x step, the step added once a tick.  `net` is")
    L.append("# where it ends up; `bytes` is its length.  A record over 32")
    L.append("# bytes is cut: the driver copies 32, so only the first ten")
    L.append("# steps are its own.")
    L.append("")
    for i, a, start, steps, n in envs:
        net = start + sum(t * d for t, d in steps)
        wraps = not -0x8000 <= net <= 0x7FFF
        cut = ""
        if n > ENV_COPY:
            kept = (ENV_COPY - 2) // 3
            net_k = start + sum(t * d for t, d in steps[:kept])
            cut = (f"   CUT: {len(steps)} steps, the driver keeps {kept}"
                   f" (net {net_k:+d}) and reads on into the next buffer")
        who = env_use.get(i)
        L.append(f"  {i:>2}  ${a:06X}  {n:>2} bytes  start {start:+d}"
                 f"  net {net:+d} ({net / 256:+.1f} semitones"
                 + (", past the 16-bit offset: it wraps" if wraps else "")
                 + f"){cut}")
        L.append("      " + (" ".join(f"{t}x{d:+d}" for t, d in steps) or "-"))
        L.append("      bend in songs: "
                 + (songs_str(who, is_game) if who else "none"))
    L.append("")

    # -- instruments
    counts = {}
    for _, _, t, _, _ in inst:
        counts[KIND.get(t, f"silent (${t:02X})")] = \
            counts.get(KIND.get(t, f"silent (${t:02X})"), 0) + 1
    L.append("### Instruments")
    L.append("#")
    L.append("# " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    L.append("#")
    L.append("# FM operators are in register order, +0 +4 +8 +C; TL is the")
    L.append("# record's own, before the driver adds the voice's volume to")
    L.append("# the carriers.  PSG levels are attenuation, 0 loudest, F off.")
    L.append("")
    for i, a, t, want, gap in inst:
        r = rom[a:a + SLOT]
        kind = KIND.get(t, "silent")
        head = f"  {i:>3}  ${a:06X}  type ${t:02X} {kind}"
        if t in (2, 3):
            head += (f"   attack {r[2]:02X}  peak {r[4] & 15:X}"
                     f"  decay {r[5]:02X}  sustain {r[3] & 15:X}"
                     f"  release {r[6]:02X}")
            if t == 3:
                head += (f"   noise {r[1]:02X}: "
                         f"{'white' if r[1] & 4 else 'periodic'}"
                         f" {NOISE[r[1] & 3]}")
        elif t == 1:
            if r[1] == 4:
                head += "   rate: the sample's own"
            else:
                head += (f"   rate nibble {r[1] & 15}"
                         f" ({sample_rate(r[1] & 15):.0f} Hz)")
            used = smp_use.get(i)
            head += ("   plays sample " + ",".join(
                str(k) if k >= 0 else f"{-k}(none)" for k in sorted(used))
                if used else "   plays nothing")
        L.append(head)
        if t == 0:
            L.extend(fm_lines(r))
        who = ins_use.get(i)
        L.append("      patch in songs: "
                 + (songs_str(who, is_game) if who else "none"))

    # -- checks
    checks.append("  bank ${:06X}".format(site))
    first_i = b0 + 2 * len(inst)
    first_e = b1 + 2 * len(envs)
    ok_order = (inst[0][1] == first_i and envs[0][1] == first_e
                and all(inst[k][1] < inst[k + 1][1]
                        for k in range(len(inst) - 1))
                and all(envs[k][1] < envs[k + 1][1]
                        for k in range(len(envs) - 1)))
    checks.append(f"    directories in order, records right after them:"
                  f" {'yes' if ok_order else 'NO'}")
    bad = [(i, a, want, gap) for i, a, t, want, gap in inst
           if gap is not None and gap != want]
    end_i = inst[-1][1] + inst[-1][3]
    checks.append(f"    instruments: {len(inst)} records, each its kind's"
                  f" length: {'yes' if not bad else 'NO'};"
                  f" end at ${end_i:06X}")
    for i, a, want, gap in bad:
        checks.append(f"      #{i} at ${a:06X} is {gap} bytes, its kind"
                      f" says {want}")
    bad_e = [i for k, (i, a, *_ , n) in enumerate(envs)
             if k + 1 < len(envs) and a + n != envs[k + 1][1]]
    end_e = envs[-1][1] + envs[-1][4]
    checks.append(f"    envelopes: {len(envs)} records end to end:"
                  f" {'yes' if not bad_e else 'NO ' + str(bad_e)};"
                  f" end at ${end_e:06X}, instruments start at ${b0:06X}"
                  f" - {'exact' if end_e == b0 else 'NOT exact'}")
    unused38 = sorted({rom[a + 38] for i, a, t, *_ in inst if t == 0})
    checks.append(f"    FM byte 38 (never read) holds: "
                  + " ".join(f"{v:02X}" for v in unused38))
    if touch is not None:
        tl, _ = trace_check(touch, rom, b0, b1, inst, envs)
        checks.extend(tl)
    return L, checks, counts, end_i


def main():
    global _ROM
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/sound"))
    ap.add_argument("--touch", default=str(ROOT / "tmp/sega/snap/touch.bin"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    _ROM = rom
    tp = Path(args.touch)
    touch = tp.read_bytes() if tp.exists() else None

    L = []
    L.append("# instruments.txt - what the Mega Drive Dune II's notes")
    L.append("# sound like: the instruments and pitch envelopes of both")
    L.append("# sound banks, field by field.")
    L.append("#")
    L.append("# Written by tools/sega/sega_instr.py, whose docstring gives")
    L.append("# the Z80 instruction behind every field.  The songs that")
    L.append("# use them are in music.txt.")
    L.append("")
    L.append("## The record, 39 bytes, byte 0 the type")
    L.append("#")
    L.append("# type 0 FM ($1431):")
    L.append("#   1      LFO, register $22 - only if bit 3 is set  ($14C1)")
    L.append("#   2      bits 7-6: register $27 on FM3; bit 6: FM3 special")
    L.append("#          mode, FM3 only                    ($1434, $1497)")
    L.append("#   3      FB/ALG, register $B0; ALG picks the carriers")
    L.append("#   4      pan/AMS/FMS, register $B4")
    L.append("#   5-10   operator +0:  $30 DT/MUL, $40 TL, $50 RS/AR,")
    L.append("#                        $60 AM/D1R, $70 D2R, $80 SL/RR")
    L.append("#   11-16  operator +4,  17-22 operator +8,  23-28 operator +C")
    L.append("#          (all via the list at $161E; SSG-EG gets 0)")
    L.append("#   29-36  FM3 special mode: $A6 $A2 $AC $A8 $AD $A9 $AE $AA;")
    L.append("#          otherwise unused, and 1F FF 1F FF 1F FF 1F FF")
    L.append("#          unless shown")
    L.append("#   37     low nibble: operators keyed on, register $28 ($15A8)")
    L.append("#   38     copied, never read")
    L.append("# type 1 sample ($12F9):")
    L.append("#   1      rate nibble for the DAC's timer A; 4 keeps the")
    L.append("#          sample's own  ($1366).  The note picks the sample:")
    L.append("#          (note - $30) mod $60 in resource 3")
    L.append("# type 2 PSG tone ($1245) / type 3 PSG noise ($123C), all")
    L.append("# into the channel record at $0009 ($1260-$12F4):")
    L.append("#   1      noise register bits (type 3): bit 2 white, 1-0 rate")
    L.append("#   2      attack step    3  sustain level   4  peak level")
    L.append("#   5      decay step     6  release step")
    L.append("#   A noise instrument always takes tone channel 2 as well and")
    L.append("#   tunes it to the note ($1297-$12BE: it tests the type byte,")
    L.append("#   which is 3, not the noise mode).")
    L.append("# any other type: the note is ignored ($123B).  The cartridge")
    L.append("# uses $63 for those, one byte long.")
    L.append("")

    all_checks, summary = [], []
    all_checks.append("  the driver, against this file's reading of it")
    for what, got, want in driver_check(rom):
        all_checks.append(f"    {what}: {'same' if got == want else 'DIFFERENT'}")
    for site, peas, empty in resource_sets(rom):
        if empty:
            continue
        is_game = site == 0x02DCC8
        body, checks, counts, _ = bank(rom, touch, site, peas, is_game)
        L.extend(body)
        L.append("")
        all_checks.extend(checks)
        summary.append((site, counts))

    L.append("## The check")
    L.append("#")
    L.append("# Every directory entry is a record of exactly its kind's")
    L.append("# length, end to end, and the tables stop where the next")
    L.append("# thing starts.  Then the Z80's recorded reads: loading an")
    L.append("# instrument reads its directory word and 39 bytes, starting")
    L.append("# an envelope its word and 32, and nothing else in these")
    L.append("# regions is read by anything.")
    L.append("")
    L.extend(all_checks)
    L.append("")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "instruments.txt").write_text(
        "\n".join(x.rstrip() for x in L) + "\n")
    for site, counts in summary:
        print(f"bank ${site:06X}: " + ", ".join(
            f"{k} {v}" for k, v in counts.items()))
    print("\n".join(all_checks))


if __name__ == "__main__":
    main()
