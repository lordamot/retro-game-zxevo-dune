---
name: build
description: Build the game (an SPG file), run it, and check it still plays. Use when asked to build, run, screenshot or verify this port, or when a change needs proving.
---

# Building and running

```sh
make build                         # src/ -> build/DUNE.DAT, and dune.trd +
                                   # DUNE.DAT, what a real machine boots
make build HOUSE=A MISSION=3       # straight into that battle (H A O)
make build DBGFLAGS=8 CREDITS=5000 # the debug block: 1 reveal, 2 no damage,
                                   # 4 fast build, 8 no sound (skips the
                                   # ~18 s card test and upload), 32 only the
                                   # intro's tune on the card and no loading
                                   # later (a real card that stops answering),
                                   # 64 the joystick port is never read (the
                                   # keys only), see src/world.asm
python3 tools/build_dune.py --build-dir build-1mb --flags2 1
                                   # the sound card taken for 1 MB, the intro
                                   # and the lego tune only, nothing streamed
python3 tools/build_dune.py --build-dir build-prof --profile
                                   # a profiling build: the PROF marks in
                                   # (never ship one - they write $7FFD)
make run                           # build and play it in an SDL2 window
make demo                          # into Atreides 1, photograph it
make verify                        # check from memory that it plays
make test                          # build, then every tools/tests/test_*.py
```

`make build` is `tools/build_dune.py`: the tables, missions, maps and
texts, the battle art, the sound set and the front end's pictures are made
from `src/res/`, `src/dune.asm` is assembled into RAM pages, and the pages
go into one SPG; `tools/dune_trd.py` then makes the disk whose loader
(`src/loader/loader.asm`) reads DUNE.DAT - the SPG - off the SD card, the
only way the BaseConf firmware can start it.  `--build-dir DIR` keeps a build (and its `dune.sym`,
`dune.lst`, `bank_of.txt`) apart from others.  `.claude/docs/port.md`
and `.claude/docs/port-code.md` describe the result.

## After any change, run `make verify`

`tools/verify_build.py` builds straight into Atreides 1 and reads the
machine's memory: EGA at 14 MHz, the mission loaded, A selects a unit and
gives it Move and it drives off, the credits counter, a Windtrap built and
placed, the battle pass within three frames, the disk booting the game
off a FAT16 and a FAT32 card image, and (a second build) the
sound card loaded and the music audible.  The pass rate is a real
regression test: a one-instruction loop bug once made a pass nine frames.

## After a change to game logic, run `make test` too

`make test` builds and runs the subsystems' suites (`tools/tests/test_*.py`:
the stub, MOVE, COMBAT, STRUCT, HOUSE, the effects, the UI, and all 27
missions run with the player idle), about three minutes in all, and
fails if any check does.  Each suite loads a mission through
`tools/dune_test.py`'s mailbox, pokes records, far-calls the subsystem's
routines and compares what they leave with the specs' models - for MOVE
and COMBAT, `tools/sega/sega_spec_check.py`'s own S3/S4 models, run on
the port's pages through `tools/tests/rig.py`.  One suite, or one group of
it: `python3 tools/tests/test_combat.py --only fire`.  A call that has not
finished in its frames is a failure too: it would shift every later
call's answers by one.

## When the build stops

- **`[JR] Target out of range`** - `python3 tools/build_dune.py ... 2>&1 |
  python3 tools/fix_jr.py` turns them into JPs.
- **`ASSERT $ <= $4000`** after a bank - that 16 KB bank is full; move
  code to the subsystem's second bank (MOVE2, COMBAT2 ...) or tables out of
  it (`TABLE_SECTIONS` in `build_dune.py`).
- **`Duplicate label`** - every bank shares one namespace; private labels
  carry the bank's prefix (`port-code.md`).
- **`table tbl_X is not placed`** - a new table from `dune_data.py` needs a
  section in `TABLE_SECTIONS`.

## Looking inside

`tools/dune_test.py` calls routines on the running machine, in test mode
or inside a running battle (`Machine(build_dir=..., battle=100)`), and
`python3 tools/dune_test.py state` prints units, structures and houses.
`build/dune.sym` and `build/bank_of.txt` turn a PC into a routine: every
code bank starts at `$0000` in window 0, so the bank is in the emulator's
`state` line (`banks=rN`: page N/64).
