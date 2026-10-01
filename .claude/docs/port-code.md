# Writing the port's Z80 code

How the game code is organised and the rules every bank follows.  The
memory map and why it is shaped this way are in `port.md`; what the game
must *do* is in `orig/sega/spec/S1-S10` (the specs), with the cartridge's
68000 code in `orig/sega/src/` and its routine names in
`orig/sega/res/names/`.

## Banks and calls

Code runs in window 0, one 16 KB bank at a time (`src/pages.inc`).  Every
bank starts with the **stub** (`src/stub/`): the interrupt handler, the
far-call trampoline, page switching, maths, random numbers and the core
library.  Logic banks also carry the **hot tables** straight after the stub
(`build/gen/tbl_hot.inc`); drawing banks (RENDER, UI, FRONT, TUTOR, PANEL) do not.

- `FCALL label` calls a routine in any bank.  A, BC, DE, HL, IX, IY go in
  and come back as the callee left them; flags go back but not in.  It
  costs about 450 T-states, so call inside your own bank where you can
  (a battle pass makes only a dozen: the unit loop stays in its bank).
- Routines in the stub are called with a plain `call` from any bank.
- **A pointer handed to another bank must point into windows 1-3**
  (UNITS, WORLD, MAP).  A bank's own variables are out of sight the moment
  it far-calls: `arg_pos` in WORLD is there for positions.
- A bank may keep private variables in its own page (code pages are RAM):
  put them at the end of its source.  Only state other banks or the
  renderer must see goes in WORLD, through your `<bank>/world.inc`.

While game logic runs the windows are: W0 your bank, W1 `UNITS` (units,
houses, teams), W2 `WORLD` (structures, tables, globals, stack), W3 `MAP`.
`map_game` puts W1 and W3 back.  Anything that maps another page into W1
or W3 must put them back before returning.

## Records and the 68000's byte order

Units, structures, houses and teams keep **the cartridge's offsets**
(`src/records.inc`, from S2), so a spec's `+$4E` is `U_DEST_Y`.  But the
port is little-endian: a word at `+$k` has its low byte at `+$k`.  So:

| 68000 | the port |
|---|---|
| `move.w $k(a2)` | the word at `+$k`, low byte first |
| `btst #n,$k(a2)` with `k` even (a byte op on a word's **high** byte) | bit `n` of byte `+$k+1` (the word's bit `8+n`) |
| `btst #n,$k(a2)` with `k` odd (the word's low byte) | bit `n` of byte `+$k-1` |
| `move.w $k(a2),d0; btst #n,d0` | bit `n` of the word: byte `+$k` for 0-7, `+$k+1` for 8-15 |
| a position `$A(a2)` (a long: y word, x word) | y word at `+$0A`, x word at `+$0C` |
| a 32-bit value (credits, `structuresBuilt`) | 4 bytes, low first |

`records.inc` names the flag bits by their *word* bit numbers (`OF_*`);
`set OF_x, (ix+O_FLAGS)` works for bits 0-7, `set OF_x-8, (ix+O_FLAGS+1)`
for 8-15.

Unit type, structure type, house and landscape tables are
`tbl_unit_info` etc. with the ROM's offsets (`UI_*`, `SI_*`, `HI_*`,
`LS_*`); `unit_info` / `struct_info` / `house_info` / `landscape_info`
(stub) turn a number into the record's address.

## The library

In the stub (any bank, plain `call`):

| routine | does |
|---|---|
| `unit_ptr`, `struct_ptr`, `house_ptr`, `team_ptr` | A = slot -> HL = record |
| `unit_info`, `struct_info`, `house_info`, `landscape_info` | A = type -> HL = its table record |
| `map_addr`, `map_ground_icon`, `map_overlay_icon`, `map_landscape` | HL = square -> address / icon / landscape type |
| `map_valid` | HL = square -> carry if playable |
| `pos_square` | HL -> position -> HL = square |
| `square_centre` | HL = square, DE -> 4 bytes: its centre |
| `tile_distance` | HL, DE -> positions -> HL |
| `tile_distance_packed` | HL, DE = squares -> HL |
| `tile_direction` | HL, DE -> positions -> A (0 north, $40 east) |
| `tile_direction_packed` | HL, DE = squares -> A ($00-$E0, $FF none) |
| `tile_move_by_direction` | HL -> position (moved in place), A = direction, C = distance |
| `house_are_allied` | B, C = houses -> A = 1 / 0 |
| `ref_is_valid`, `ref_position`, `ref_square`, `ref_make_square` | references (S2) |
| `random`, `rand_between` | the cartridge's generator exactly |
| `mul16`, `mul32`, `mul_shr8`, `div_shl8`, `udiv16`, `sdiv16` | including `math_mul_shr8` and `math_div_shl8` |
| `emc_arg` | A = n -> HL = the n-th argument of the running script's call |
| `map_w1`, `map_w3`, `map_game` | page switching |

In bank OBJ (`FCALL`): the pools and searches (`unit_create`,
`unit_spawn`, `unit_free`, `unit_remove`, `unit_find_first/next`,
`struct_allocate`, `struct_free`, `struct_find_first/next`, `team_alloc`,
`team_find_first/next`, `house_allocate`, `house_used`), the side lists
(`unit_head`/`unit_lnext`, `struct_head`/`struct_lnext` in WORLD: 0 the
player's side, 1 the rest), `unit_give_order`, `obj_var4_set/clear`,
`ref_unit_ptr`, `ref_struct_ptr`, `ref_object_ptr`,
`unit_drop_references`, the map's objects (`map_object_at`,
`map_unit_at`, `unit_update_map`, `unit_blocked_here`), the fog
(`map_unfog_radius`, `map_reveal_square`, `map_update_fog_edge`,
`map_square_unveiled`), and putting structures, slabs and walls on the
map.  Each routine's header gives its registers.

Sounds (bank MAIN, `FCALL`): `snd_effect` (A = an effect id, S10's
`$06A876` numbering), `snd_voice` (A = a feedback id, `$06A954`),
`snd_music` (A = a music track, `$06A8B8`).

## The script machine

`src/vm/emc.asm` runs the cartridge's own bytecode.  A routine a script
calls (the `ef_*` labels in `src/vm/functions.asm`'s tables) is
far-called with **IX = the script state** (the record + `O_SCRIPT`, or a
team + `T_SCRIPT`); the delay word is at `IX-2`.  It reads its arguments
with `emc_arg` (A = 0 is the top of the script's stack) and answers in HL.
The object the script belongs to is `IX - O_SCRIPT`.  To run a script:
`FCALL emc_run_budget` (IX = state, B = budget), `emc_run_three`,
`emc_run`, `emc_start` (IX, A = script, HL = entry), `emc_reset`.

## Who owns what

Each subsystem owns its bank's sources and is the only one to edit them:

| subsystem | files | specs |
|---|---|---|
| MOVE | `src/move/*` (banks MOVE, MOVE2) | S1 units, S3 |
| COMBAT | `src/combat/*` (COMBAT, COMBAT2) | S4 |
| STRUCT | `src/struct/*` (STRUCT, STRUCT2) | S1 structures, S5, S6 |
| HOUSE | `src/house/*` (HOUSE, HOUSE2) | S1 houses and teams, S7, S9's end |

| FRONT | `src/front/*`, `tools/dune_front.py`, `tools/dune_tutorial.py` (FRONT, TUTOR = page 19, pages 97-98, 100-121, 124-127, 221-223, 0, 4, 6) | S10's front end, the Tutorial |
| PANEL | `src/front/panel.asm` (PANEL, page 122) | S10's structure panels |

**All banks share one label namespace**, so a label that is not an
interface routine starts with its bank's prefix: `mv_` MOVE, `cb_` COMBAT,
`st_` STRUCT, `hs_` HOUSE, `fe_` FRONT, `tu` TUTOR, `pn_` PANEL (the older banks use `rf_`/`rs`
RENDER, `u`/`ua_`/`ubi_` UI).

The labels already in those files are the **interface**: other banks call
them by name with the registers their headers give.  Keep both; add
whatever else you need.  If you need a change in a shared file (the stub,
OBJ, VM, SCEN, MAIN, `records.inc`, `world_vars.inc`), say so in your
report rather than editing it.

## Building and testing

    make build && make verify && make test
    python3 tools/build_dune.py --build-dir build-x --house A --mission 1
    python3 tools/build_dune.py ... 2>&1 | python3 tools/fix_jr.py   # JR out of range -> JP

`--build-dir` keeps a build, its symbols and generated files apart from
`build/` (and every test takes the same option - a directory left from an
older run is an older game).  `tools/dune_test.py` calls routines on the
running machine (`Machine(build_dir=...)`: poke memory, `call` a label
with registers, read registers and pages back); `python3
tools/dune_test.py state` prints the units, structures and houses after N
frames.  `tools/tests/test_struct.py` and `tools/tests/rig.py` (which lets
`tools/sega/sega_spec_check.py`'s models read the port's pages) are the
patterns to copy; check every call's `done`.  Test against the specs'
models where they exist (`tools/sega/spec_s*.py`, `sega_spec_check.py`)
and against the specs' own numbers.

The frame budget matters: the whole pass - units, one of the rotating
loops, and drawing - takes about one frame now (the renderer does not wait
for the screen swap; the next pass's logic runs meanwhile), and must stay
well under the check's three.  The profiler (`OUT
($FD),A` marks, `bin/evo/evo-run --profile`) says where time goes.
