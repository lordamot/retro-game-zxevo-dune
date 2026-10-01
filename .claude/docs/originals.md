# The two originals, taken apart

Both cartridges in `orig/` now have a deconstruction beside them:
`orig/nes/` and `orig/sega/`.  Each is a set of sources that **build the
cartridge back, byte for byte**, and each is checked on every build.

```sh
make orig         # take both apart again and rebuild both
make orig-nes     # just the NES demo
make orig-sega    # just the Mega Drive game
make run nes      # rebuild the NES original and play it
make run sega     # rebuild the Mega Drive original and play it
```

|  | NES demo | Mega Drive game |
|---|---|---|
| file | `orig/sand_emperor_demo5d9.nes` | `orig/dune2.gen` |
| size | 384 KB (256 PRG + 128 CHR) | 1 MB |
| processor | 6502 | 68000 |
| mapper | VRC6 (iNES 26) | none: flat at $000000 |
| sources | `orig/nes/src/prg00-15.asm` | `orig/sega/src/rom00-0F.asm` |
| disassembled | 22% of the program | 13.6% of the cartridge is code, **every byte accounted for** |
| rebuild | `tools/nes/build_nes.py` | `tools/sega/build_sega.py` |

## Why byte-exactness is the whole design

A disassembly nobody can rebuild is a description, and a description
drifts.  So both sides are arranged around one rule: **the disassembler may
not write down anything it cannot read back.**

Each tool is a matched pair - `tools/nes/m6502.py` and
`tools/sega/m68k.py` each hold a decoder and an encoder over one table -
and the extractor re-assembles every instruction the moment it disassembles
it.  Anything that does not come back as the same bytes is emitted as data
instead.  Then the build assembles the whole cartridge and compares the
SHA-256.

The consequence is worth stating plainly: an unknown encoding, a
mis-guessed data region, a bug in the encoder - none of them can corrupt
the ROM.  They can only cost readability.  That is why it is safe to let
the trace guess at all.

## How the code is found

Both use recursive descent from the entry points, then a sweep.

**Certain seeds.**  On the Mega Drive, the 64 exception vectors, of which
vector 1 is the reset address.  On the NES, the three vectors at the top of
the fixed bank - and only those, because nothing else has a known address.

**Call targets.**  Every JSR/BSR/JMP operand in the whole ROM, collected by
a blind sweep.  It over-collects; the trace throws back what does not
decode.

**Jump tables.**  Runs of consecutive pointers that all land inside the
cartridge.  Most of what either game does is dispatched through one of
these, and without them a trace from the vectors finds only the top layer.

**Switch tables.**  On the Mega Drive a `jmp TBL(pc,Xn.w)` is where a trace
from the vectors stops, because which case it takes is in a register.  The
table is not a guess, though: it starts at the effective address the `jmp`
itself names, it is either a run of word offsets from its own start or a
ladder of `bra.s`, and no case can jump backwards into it - so it ends at
the lowest address its own entries point at.  The `cmpi.l #N,Dn` the
compiler puts in front says the same count a second time, and where the two
disagree the guard wins.  There are 47 of these and reading them is worth
4074 bytes of code, including the scenario loader and the whole EMC script
interpreter.

**The gaps.**  What is left is read forwards a byte at a time, keeping any
run that decodes cleanly all the way to a return.  These are marked in the
listing, because "this decodes as code" is a weaker statement than "this is
code", and the reader should be told which one is being made.

What tells code from data in practice is not cleverness but the 68000's own
rules: `move.w d0,$1234(pc)` does not exist, a byte immediate does not have
a dirty high half, a branch does not land on an odd address, and bits 10-8
of a brief extension word are zero on a 68000.  Enforcing those - see
`alterable()` in `m68k.py` - is most of the difference between a listing
and a mess.

## The NES side: banking is the problem

`$8000-$BFFF` and `$C000-$DFFF` are paged and only `$E000-$FFFF` is fixed,
so a call to `$8F00` lands in whichever bank was in at the time, which is a
fact about the code and not about the address.  Every bank is therefore
offered every target the whole ROM names, and keeps the ones that decode.
That is why 22% and not more.

Its text does not appear in a hex dump either: the demo draws with **8x16
sprites**, so a character is stored as `2*(c - $20) + 1`.  The extractor
puts the words in the comment and `tools/nes/nes_text.py` writes the table
out.

## The Mega Drive side: compression is the problem

The code reads well; the art does not exist in the ROM in any readable
form.  Barely a hundred tiles of two thousand match live VRAM verbatim -
the rest is compressed in something close to Westwood's own formats, whose
filenames are still sitting in the string table:

```
Const Yard      construc.wsa
Windtrap        windtrap.wsa
Spice Silo      storage.wsa
```

`orig/sega/res/text/assets.txt` is that table in the game's own order,
which is a useful thing to have even before the pictures can be read.

That is no longer where it stands.  The compression is Westwood Format80,
the decompressor is at `$000C32`, and `tools/sega/sega_gfx.py` undoes it:
every building and unit in its own colours, 13769 tiles besides, and every
stream marked in the listing.  That, and reading, got to 94.5%.  The
rest came from asking the machine: the Genesis core is patched to record
what the running game does with every byte (executed, read, sent by DMA,
read by the Z80, and by whom), `tools/sega/sega_touch.py` drives the game
through every password and test screen and a coverage-guided random
player, and `orig/sega/res/trace.txt` is the record the extractor trusts
first.  Nothing is unaccounted for now; `orig/sega/gaps.txt` is empty and
`orig/sega/regions.txt` says what every named stretch is.

18% of the cartridge - the banks from `$0C8000` - is eight-bit sample
for the YM2612's DAC.  It was first found by its shape: recorded sound
has neighbouring bytes close together and sits away from the rails.  The
shape test also claimed 96 KB at `$070000`, which the Z80 never reads -
it is the 27 stored battlefields - and that is why the shape is now only
believed where the recorded run saw the Z80 read.  The music is not found that way and does not need to be:
command `$0B` hands the Z80 driver the addresses of its own resource
banks, and `sega_seq.py` reads the 97 songs out of them.

## The tools

Under `tools/nes/` and `tools/sega/`, each documented in
`.claude/docs/tools.md`:

| | |
|---|---|
| `m6502.py`, `m68k.py` | the matched decoder/encoder pairs |
| `nes_asm.py`, `sega_asm.py` | the two-pass assemblers the rebuilds use |
| `nes_extract.py`, `sega_extract.py` | cartridge -> sources |
| `build_nes.py`, `build_sega.py` | sources -> cartridge, SHA-256 checked |
| `run_nes.py`, `run_sega.py` | rebuild and play |
| `nes_chr.py`, `nes_text.py` | the patterns and the words |
| `sega_text.py`, `sega_art.py`, `sega_music.py` | the same, where it can be done |
| `sega_z80.py`, `sega_seq.py` | the Z80 sound driver, and the songs it reads |

The window both originals open in is `bin/nes/retro-play` and
`bin/gen/retro-play` - the same binary, built from
`tools/retro-headless/retro-play.c`, an SDL2 twin of the headless
`retro-run` this project already drove both machines with.
