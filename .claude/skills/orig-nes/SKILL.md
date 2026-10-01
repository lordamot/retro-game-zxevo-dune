---
name: orig-nes
description: Work on the NES original's deconstruction under orig/nes - the 6502 disassembly, the pattern sheets, the strings, and rebuilding the cartridge. Use when asked about how Sand Emperor itself works, where something is in its ROM, or to change and rebuild it.
---

# The NES original, taken apart

`orig/nes/` is *Sand Emperor* demo 5 disassembled into sources that build
the cartridge back **byte for byte**.  `.claude/docs/originals.md` is the
full account; this is what to do.

## The commands

```sh
make orig-nes                              # take it apart again, rebuild, check
make run nes                               # rebuild and play it
python3 tools/nes/build_nes.py             # just rebuild, SHA-256 checked
python3 tools/nes/build_nes.py --no-check  # rebuild after changing something
python3 tools/nes/run_nes.py --script F --shot tmp/nes/x.png   # headless
```

## Running it

`make run nes` opens it in a window: the arrows are the d-pad, Z and X are
B and A, Enter is start, Tab is select (F12 a screenshot, F5 reset).
Headless, `run_nes.py --script F` runs a `retro-run` script against the
rebuilt cartridge - `run`, `hold`, `press`, `shot`, `ram`, `save`/`load`
and the NES's video dumps (`nt`, `pal`, `oam`, `chr`, `ppureg`); buttons
`a b select start up down left right`.  `.claude/docs/nes-tools.md` has the
script language.  `orig/control_en.txt` is the demo's author's own note on
what the buttons do.

The demo is reference material: an earlier port was built from it, and
the tools that cut its screens, patterns and music into that port went
with it (git history has them).  The current port reproduces the Mega
Drive cartridge (`orig-sega` skill).

## Where things are

| | |
|---|---|
| `orig/nes/rom.map` | what every byte of the file is |
| `orig/nes/src/prg00.asm` … `prg15.asm` | the sixteen 16 KB banks |
| `orig/nes/src/nes.inc` | PPU, APU and VRC6 registers by name |
| `orig/nes/res/chr/*.png` | all 8192 patterns, 256 to a sheet |
| `orig/nes/res/text/strings.txt` | every string and where it lives |
| `orig/nes/res/text/font.txt` | the 64 glyphs, drawn |

## Things that will catch you

- **Banks 0-14 are all `.org $8000` and bank 15 is `$C000`.**  Only
  `$E000-$FFFF` is fixed on a VRC6, so a `JSR $8F00` in one bank means
  nothing without knowing which bank was paged in.  That is why only about
  a fifth of the program disassembles, and why the rest is `.byte` rather
  than a guess.
- **Text is not ASCII.**  A character is drawn as an 8x16 sprite, so it is
  stored as `2*(c - $20) + 1`.  The listing puts the words in the comment;
  `tools/nes/nes_text.py` writes the table out.  Grepping for `NORM` finds
  nothing.
- **`.byte` is not "unknown".**  It is "not proved to be code".  A run the
  gap sweep found is marked in the listing; treat the mark as a warning,
  not a label.
- **Do not relax the round-trip check** in `tools/nes/nes_extract.py`.  It
  is what makes a wrong guess cost readability instead of correctness.
- Patterns are 4-colour indexed PNGs and the grey levels *are* the bit
  values.  Any editor that keeps the palette will do; anything that
  converts to RGB will break the rebuild.

## Changing something

Edit the source, rebuild with `--no-check`, play it with `make run nes`.
Put the check back the moment the experiment is over: without it nothing
is holding the sources to the cartridge.
