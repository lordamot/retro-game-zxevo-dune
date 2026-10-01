#!/usr/bin/env python3
"""gs_chantest.py - a four-channel module that sounds the sound card's
channels one at a time, to hear on a real card which of its four DACs
reach the output.

    gs_chantest.py OUT.mod
    python3 tools/build_dune.py --build-dir build-chan --intro-mod OUT.mod

Played as the intro's tune (behind PRESS ANY KEY): channel 1 a low note
for two seconds, silence, channel 2 a note a fifth up, channel 3 an
octave up, channel 4 higher still, then all four together, and round
again.  The ROM puts the module's channels 1-4 on the card's DACs 0, 2, 3
and 1 (sound.md), so what is heard in turn is DAC 0, 2, 3, 1.  A channel
that is not heard is one the card does not bring out.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from modlib import Cell, Sample, write, ROWS, CHANNELS   # noqa: E402

PERIOD = 64                     # bytes of one wave: a loop this long
NOTES = (12, 19, 24, 31)        # C-2, G-2, C-3, G-3 (modlib.PERIODS indices)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "chantest.mod")
    wave = bytes((int(100 * math.sin(2 * math.pi * i / PERIOD)) & 0xFF)
                 for i in range(PERIOD * 4))
    tone = Sample("tone", wave, volume=64, loop_start=0, loop_len=len(wave))
    rows = [[Cell() for _ in range(CHANNELS)] for _ in range(ROWS)]
    # 16 rows a channel at the module's default 6 ticks a row: about 2 s
    # of note, the last four rows of each block silent (note cut, C00)
    for ch in range(4):
        r0 = ch * 16
        rows[r0][ch] = Cell(NOTES[ch], 1)
        rows[r0 + 12][ch] = Cell(None, 0, 0xC, 0)      # volume 0: quiet
    pattern2 = [[Cell() for _ in range(CHANNELS)] for _ in range(ROWS)]
    for ch in range(4):
        pattern2[0][ch] = Cell(NOTES[ch], 1)            # all four at once
        pattern2[24][ch] = Cell(None, 0, 0xC, 0)
    n = write(out, "GS channel test", [tone], [rows, pattern2], [0, 1], restart=0)
    print(f"{out}: {n} bytes")


if __name__ == "__main__":
    main()
