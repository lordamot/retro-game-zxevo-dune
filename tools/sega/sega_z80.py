#!/usr/bin/env python3
"""sega_z80.py - the Z80 sound driver, out of the 68000's cartridge.

    sega_z80.py [--rom orig/dune2.gen] [--out orig/sega/res/sound]

Writes `z80driver.asm`, the driver disassembled, and `z80driver.bin`
beside it.

## Where it is, exactly

Not guessed at.  The routine at `$00152A` uploads it, and it says its own
bounds:

    move.w  #$100,Z80_RESET      ; hold the Z80 in reset
    jsr     L_00150C(pc)         ; and take the bus
    lea.l   $294E.l,a0           ; from here
    lea.l   $41D8.l,a1           ; to here
    move.l  a1,d0
    sub.l   a0,d0                ; so this many bytes
    subq.w  #$1,d0
    lea.l   Z80_RAM,a1           ; into $A00000, which the Z80 sees as $0000
    move.b  (a0)+,(a1)+
    dbf     d0,L_001556
    move.b  #$0,(a1)+            ; then zero the rest of its 8 KB
    cmpa.l  #$A02000,a1
    bne.s   L_00155C

So the driver is **$188A bytes - 6282 - at $00294E, and it runs at $0000**.
Its first instructions agree: `di`, `im 1`, `ld sp,$1B20`, `jp $08C3` - a
stack at the top of the 8 KB and an entry point well inside 6282 bytes.

## What is here and what is not

The disassembly is `tools/z80_disasm.py`, which this repository already
had - it was written for the ZX Evolution side and the Z80 is the Z80.
What comes out is the driver's code.  What it *means* is `sega_seq.py`:
the mailbox the 68000 talks to it through, its twenty-four commands, and
the sequence format its tracks are written in, all in `res/sound/
music.txt`.  `res/sound/sound.txt` has where the samples live.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

START, END = 0x00294E, 0x0041D8       # from the upload routine at $00152A
ORG = 0x0000                          # $A00000 is the Z80's own $0000


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/sound"))
    args = ap.parse_args()

    rom = Path(args.rom).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    blob = rom[START:END]
    (out / "z80driver.bin").write_bytes(blob)

    asm = subprocess.run(
        [sys.executable, str(ROOT / "tools/z80_disasm.py"),
         str(out / "z80driver.bin"), "--org", str(ORG)],
        check=True, capture_output=True, text=True).stdout

    head = f"""; z80driver.asm - the Mega Drive Dune II's sound driver.
;
; {len(blob)} bytes taken from ${START:06X}-${END - 1:06X} of orig/dune2.gen and
; disassembled by tools/z80_disasm.py.  It runs at $0000 in the Z80's own
; 8 KB, which the 68000 sees at $A00000.
;
; The bounds are the upload routine's own: $00152A holds the Z80 in reset,
; takes its bus, copies ${END - START:04X} bytes from ${START:06X} into $A00000 and zeroes
; the rest of the 8 KB.  See tools/sega/sega_z80.py.
;
; It uses all three of the things a Z80 on this machine can reach, and the
; disassembly shows it: the YM2612 at $4000-$4002 (16 references), the
; cartridge bank register at $6000 (1), and the PSG at $7F11 (5).  What it
; does with them - its sequence format, and how the 68000 asks it for a
; tune - is not decoded.
;
"""
    (out / "z80driver.asm").write_text(head + asm)
    lines = asm.count("\n")
    print(f"{len(blob)} bytes -> {out}/z80driver.asm ({lines} lines)")


if __name__ == "__main__":
    main()
