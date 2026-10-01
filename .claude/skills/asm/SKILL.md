---
name: asm
description: Work on the Z80 engine - where each module lives, the register conventions, and the mistakes this codebase has actually made. Use when editing anything under src/*.asm.
---

# The engine

Assembled by `bin/sjasmplus/sjasmplus` from `src/dune.asm`, which lays the
whole game out as a 4 MB image of RAM pages: the WORLD page, the boot
page, then one code bank after another, each a 16 KB page for window 0
that starts with the same **stub**.  `make build` runs it through
`tools/build_dune.py`.  Read `.claude/docs/port-code.md` before writing
code - it has the banks, `FCALL`, the library, the script machine and who
owns which files; `.claude/docs/port.md` has the pages and windows.

| | |
|---|---|
| `dune.asm` | the page layout, `FCALL`/`FJUMP`, `LOGIC_BANK`/`DRAW_BANK` |
| `evo.inc` | the machine: ports, video modes, the screens' pages, `PROF` |
| `pages.inc` | which page holds what - the authority |
| `records.inc` | the unit, structure, house and team records at the cartridge's offsets (S2), the flag bits (`OF_*`), the table offsets (`UI_*`, `SI_*`, `HI_*`, `LS_*`) |
| `world.asm`, `world_vars.inc` | page WORLD: the debug block, the test mailbox, the globals, the structures, the stack |
| `stub/` | in every bank: the interrupt at `$0038`, the far-call trampoline, page switching, maths, the cartridge's random generator, the pad, the video, the core library |
| `main/` | start-up, the battle pass (S1), the sound calls, the mission flow, the mailbox server |
| `obj/` | pools, references, orders, the map's objects, the fog (S2, S8) |
| `vm/` | the EMC interpreter and the routines scripts call |
| `move/`, `combat/`, `struct/`, `house/` | S3, S4, S5-S6, S7-S9: a bank each and a second bank (MOVE2 holds the units' effect animations) |
| `scen/` | loading a mission (S9) |
| `render/`, `ui/` | the battlefield on screen; the controls, HUD and radar (S10) |
| `front/` | the front end and its screen library; `panel.asm` the structure panels (bank PANEL); `tutorial.asm` the Tutorial (bank TUTOR) |
| `gs.asm` | the General Sound card: upload and play |

Every routine cites the cartridge routine it reproduces (`$00B1C2`), and
`orig/sega/src/` and `orig/sega/res/names/` are where to read the
original.

## Conventions

- **One label namespace for all banks**: a label that is not an interface
  routine starts with its bank's prefix (`mv_`, `cb_`, `st_`, `hs_`, `fe_`,
  `pn_`; RENDER `rf_`/`rs`/`rc_`...).
- **`FCALL label`** reaches any bank (about 250 T-states): A, BC, DE, HL,
  IX, IY in and out; flags come back but do not go in.  A stub routine is a
  plain `call`.  Call within your own bank where you can.
- **A pointer handed to another bank must point into windows 1-3.**  A
  bank's own variables vanish the moment it far-calls.
- **Anything that maps another page into window 1 or 3 puts the game's
  back** (`map_game`) before it returns.
- **The stub is the same in every bank, byte for byte** - the build checks
  it.  Changing the stub changes every bank.
- The frame budget is real: a battle pass is about one frame (1.33 at
  worst in any mission's heaviest stretch) and the check fails at 3.  Measure with `PROF` and `evo-run --profile`.

## Mistakes this codebase has already made

- **`ld bc,nn` eats a `djnz` counter.**  Twice.  `pop bc` has to come
  *after* the `ld bc` that steps a pointer, or the loop runs 256 times.
  Symptom: the game runs at a fifth of the speed and the profiler shows one
  routine at 99%.
- **The 68000's byte order.**  The records keep the cartridge's offsets, but
  a word's low byte comes first: a `btst #n,$k(a2)` on an even `k` tests the
  word's high byte, which is byte `+$k+1` here.  `port-code.md` has the
  table.
- **Two branches that jump to each other on a condition nothing in between
  changes** loop for ever - production did, whenever a house had 1-255
  credits.  A mailbox test that checks every call's `done` finds it.
- **`IN A,(n)` puts A on the top half of the address bus, not B.**  The
  keyboard half-row goes in A.
- **A helper that clobbers A between reading a value and using it** - the
  headers say what a routine clobbers; believe them.
- **A string ends with `$FF`**, not zero.
- **"JR out of range"** after a routine grows: `python3 tools/build_dune.py
  2>&1 | python3 tools/fix_jr.py` turns those into JPs.

## Checking a change

```sh
make build && make verify
python3 tools/tests/test_struct.py        # and the other suites in tools/tests/
```

When something is wrong somewhere unclear: `tools/dune_test.py` calls any
routine on the running machine (the `build` skill), `build/dune.sym` turns
an address into a routine, and `bin/evo/evo-run` with `state` in a script
prints the PC and which page is in each window.
