#!/usr/bin/env python3
"""sega_music.py - the Mega Drive Dune II's sound: where it lives in the ROM.

    sega_music.py [--rom orig/dune2.gen] [--out orig/sega/res/sound]
                  [--wav]

Writes `sound.txt`, an index of the ROM's audio: where the Z80 sound driver
is set up from, and which stretches of the cartridge are eight-bit sample
data for the YM2612's DAC.  With `--wav` it also writes each sample block
out as a listenable WAV under `res/sound/`, which is the quickest way to
tell a drum from a voice line.

## How a Mega Drive makes a noise, and how this one does

Two chips answer to two processors.  The 68000 owns the picture; the Z80
owns the sound, running its own program out of 8 KB of its own RAM at
$A00000 with the YM2612 mapped into it at $4000 and the PSG reachable
through the VDP.  The 68000 must stop the Z80 through $A11100 before it may
touch any of that, which is why every sound driver on the machine begins
with the same little dance, and why finding `$00A00000` and `$00A11100`
close together in the code finds where the driver is loaded.

The samples are the giveaway.  Eight-bit unsigned PCM played through the
DAC is smooth - neighbouring bytes differ by very little - and it sits
around the middle of the range, while code, pointers and compressed art do
neither.  Measuring that over the ROM finds the sample banks without
knowing anything about the driver's format.

What this does not do is take the *music* apart into notes - that is
`sega_seq.py`, which reads the driver's own sequence format and writes
`music.txt` beside this file.  It also bounds the sample banks properly:
the shape test below is measured over 8 KB windows and so swallows the
front end's songs, which sit at `$0CF914` in the middle of the second
bank.  For hearing the music rather than reading it, `make sega`
(`tools/sega/sega_mod.py`) plays it through a model of the driver into
General Sound modules.
"""

import argparse
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

STEP = 0x2000            # the window sample statistics are measured over


def looks_like_pcm(block, step=7):
    """Two numbers: how far neighbouring bytes are apart, and how much of
    the block sits away from the rails."""
    if len(block) < 64:
        return 255.0, 0.0
    diffs = [abs(block[i + 1] - block[i])
             for i in range(0, len(block) - 1, step)]
    mid = sum(1 for x in block if 0x40 <= x < 0xC0) / len(block)
    return sum(diffs) / len(diffs), mid


def sample_banks(rom, max_diff=26.0, min_mid=0.75):
    """Contiguous stretches whose statistics say "DAC sample"."""
    out, start = [], None
    for o in range(0, len(rom), STEP):
        diff, mid = looks_like_pcm(rom[o:o + STEP])
        if diff <= max_diff and mid >= min_mid:
            if start is None:
                start = o
        else:
            if start is not None:
                out.append((start, o - start))
            start = None
    if start is not None:
        out.append((start, len(rom) - start))
    return out


def z80_reads(rom):
    """A byte a cartridge address: 1 where the recorded run saw the Z80
    read it.  None if there is no record."""
    path = ROOT / "orig/sega/res/trace.txt"
    if not path.exists():
        return None
    out = bytearray(len(rom))
    for line in path.read_text().splitlines():
        f = line.split()
        if len(f) >= 3 and f[0] == "D" and "z" in f[2]:
            a, b = (int(x.strip("$"), 16) for x in f[1].split("-"))
            out[a:b + 1] = b"\x01" * (b + 1 - a)
    return out


def driver_sites(rom):
    """Where the 68000 talks to the Z80: the two addresses that have to
    appear together for a sound driver to be loaded at all."""
    out = []
    for i in range(0, len(rom) - 4, 2):
        if rom[i:i + 4] == b"\x00\xa0\x00\x00":
            window = rom[max(0, i - 32):i + 64]
            if b"\x00\xa1\x11\x00" in window:
                out.append(i)
    return out


def write_wav(path, data, rate=8000):
    body = bytes(data)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVEfmt " + \
        struct.pack("<IHHIIHH", 16, 1, 1, rate, rate, 1, 8) + \
        b"data" + struct.pack("<I", len(body))
    path.write_bytes(hdr + body)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/sound"))
    ap.add_argument("--wav", action="store_true",
                    help="also write each sample bank out as a WAV")
    ap.add_argument("--rate", type=int, default=8000)
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    shaped = sample_banks(rom)
    sites = driver_sites(rom)
    # The shape test is a guess, and it once guessed wrong: $070000 looks
    # like sample and is the 27 mission maps and some sprite pixels.  What
    # settles it is whether the Z80 reads the bank, which the recorded run
    # says (res/trace.txt, tools/sega/sega_touch.py) - a sample is played
    # by the driver, through its window onto the cartridge, and nothing
    # else is.
    heard = z80_reads(rom)
    banks, wrong = [], []
    for o, n in shaped:
        part = sum(heard[o:o + n]) if heard is not None else n
        (banks if part * 2 >= n else wrong).append((o, n))

    lines = [
        "# sound.txt - where orig/dune2.gen keeps its sound.",
        "#",
        "# Written by tools/sega/sega_music.py.",
        "#",
        "# The Z80 owns the sound on this machine: its own program in its",
        "# own 8 KB at $A00000, the YM2612 at $A04000, and the 68000 locked",
        "# out of both until it has stopped the Z80 through $A11100.  Each",
        "# address below is a place in the code where those two appear",
        "# together, which is where the driver is uploaded.",
        "",
    ]
    for o in sites:
        lines.append(f"driver   ${o:06X}   the 68000 loads the Z80 here")
    lines += [
        "",
        "# Eight-bit unsigned PCM for the YM2612's DAC, found by its shape:",
        "# neighbouring bytes close together and the whole block sitting",
        "# away from $00 and $FF - and then kept only if the Z80 was seen to",
        "# read it, because a smooth run of bytes is not always a sound.",
        "# res/sound/music.txt has the exact banks, sample by sample.",
        "",
    ]
    total = 0
    for i, (o, n) in enumerate(banks):
        diff, mid = looks_like_pcm(rom[o:o + n])
        total += n
        lines.append(f"sample   ${o:06X}  {n:7d} bytes  "
                     f"step {diff:5.1f}  mid {mid:.2f}"
                     + (f"  sample{i:02d}.wav" if args.wav else ""))
        if args.wav:
            write_wav(out / f"sample{i:02d}.wav", rom[o:o + n], args.rate)
    for o, n in wrong:
        lines.append(f"# not sample: ${o:06X}, {n} bytes, has the shape and "
                     "the Z80 never reads it - it is the mission maps")
    lines += [
        "",
        f"# {total} bytes of sample in {len(banks)} "
        f"bank{'s' if len(banks) != 1 else ''} "
        f"({100 * total / len(rom):.0f}% of the cartridge).",
        "#",
        "# The music itself is a sequence the driver reads, taken apart in",
        "# music.txt and songs_*.txt beside this file.  To hear it,",
        "# `make sega` (tools/sega/sega_mod.py) plays it through a model of",
        "# the driver into General Sound modules, and .claude/docs/sound.md",
        "# says what this project does with the result.",
    ]
    (out / "sound.txt").write_text("\n".join(lines) + "\n")
    print(f"{len(sites)} driver sites, {len(banks)} sample banks "
          f"({total} bytes) -> {out}/sound.txt")


if __name__ == "__main__":
    main()
