# Handover: the Mega Drive Dune II as a source for the port

**Status (2026-09-26): carried out.**  The specs and the sound conversion
are done (their sections below say how), and the port was then written
from them - `.claude/docs/port.md` and `progress.md` take it from there.
The record layouts live in `orig/sega/spec/S2-objects.md` and, for the
port, `src/records.inc`.  What follows is the plan as it was made, kept
because the specs refer to it.

`orig/sega/` is complete as a *deconstruction*.  The cartridge rebuilds
byte for byte, every byte is code or a named region, all 907 routines are
named and documented, and the data, art, AI scripts and sound driver are
decoded.  What it is not yet is a *specification* someone could implement
the game from without re-reading 68000 assembly.  This plan closes that gap
in three pieces of work, and says how each is known to be finished.

Where the port stands on sound today: `.claude/docs/sound.md`.  How the
deconstruction was done: `.claude/docs/sega-internals.md`,
`.claude/skills/orig-sega/SKILL.md`.

## The rules that carry over

- **Every claim cites the code.**  An address for every constant, formula
  and branch.  "Looks like" is not a spec.
- **The machine settles arguments.**  `orig/sega/res/trace.txt` and the
  emulator (`bin/gen/retro-run`, save states in `tmp/sega/touch/pool/`)
  are the check on any reading.  A spec that can be tested against RAM
  dumps should be.
- **Tables live in modules with a `check()`**, and text is generated from
  them - the way `sega_seq.py` writes both `music.txt` and `commands.txt`
  from one table.  Nothing is edited in `orig/sega/src/` by hand.
- `make orig-sega`, `make build` and `make verify` keep passing.

The order is **records first**, because every spec is written in terms of
record fields.  **Specs** follow, one subsystem at a time.  **Sound** is
independent of both and can run in parallel.

---

## 1. Finalise the record layouts

### Goal

Every field of every record the game uses is named, sized and explained,
with the routines that read and write it.  After this, no spec needs to
say "`+$4E`".

### What exists

The object header is known: `+$00` index, `+$02` type, `+$04` flags,
`+$08` house, `+$0A` position, `+$12` hit points, `+$16` script state.
Also known are the main unit and structure fields (the header comment of
`orig/sega/res/names/02-010000.txt`), the house fields, the team record
(`$54` bytes, `05-028000.txt`), the sprite record (`00-000200.txt`), the
map square (`sega-internals.md`) and the Z80 voice (`commands.txt`).

Still open in the ROM tables:

- `units.txt`: 11 columns (`+0C +0E +14 +1E +20 +2E +30 +32 +50 +52 +54`);
- `buildings.txt`: 4 columns (`+0C +0E +14 +20`; `+1C` is the 32-bit `structuresRequired`, S6);
- `houses.txt`: 2 columns (`+16 +18`).

Still open in RAM: meanings known only by mechanism - structure `+$4E` and
`+$50`, team `+$18`, unit flag bit 6 of `+$04`, `$FFC264`, `$FFC728`,
`$FFBF7C`, `$FFC148`.

One conflict to resolve: the structure pool is described as 73 pointers
at `$04A716` (bound `$49`) in one place, and as 78 records of `$62` in
another.

### Method

1. **A field-access index**, `tools/sega/sega_fields.py`.  For every
   instruction with a `d(An)` operand, work out where `An` came from
   inside the routine: which getter returned it (`unit_get $043656`,
   `$00BAFE` for structures, `house_get`, the `$6C5B4[type]` unit table,
   `$6B94C[type]` building table, `$FFDEA0` the script's unit, and so on).
   Record (record kind, offset, size, read or write, routine).  Instances
   where the base cannot be traced are listed, not guessed.
2. **Runtime ranges.**  Dump RAM from each seed state (battle, win,
   mission 1 per house) and write down each field's observed values over
   a few seconds of play.  A column whose values match a known Dune II
   quantity is identified that way, and then confirmed by its reader.
3. **OpenDUNE as a hint.**  `ObjectInfo`, `UnitInfo`, `StructureInfo` and
   `HouseInfo` name most of these fields.  Each name is confirmed by the
   code that reads the offset in this cartridge.

### Deliverables

- `tools/sega/sega_records.py`: one table per record kind (offset, size,
  name, meaning, readers, writers), with a `check()`.  The check requires
  that every access the field index finds lands on a named field.
- `orig/sega/res/data/records.txt`, generated from that table.
- `sega_data.py` names the remaining columns of `units.txt`,
  `buildings.txt` and `houses.txt`.

### Done when

- The field index reports no access to an unnamed offset of a record
  whose base it could trace.
- The ROM tables have no "not identified" column.
- Every mechanism-only name above is either explained or explicitly
  marked as unused.

---

## 2. The specs

**Status (2026-09-26):** all ten are written - `orig/sega/spec/S1-frame.md`
to `S10-screens.md`, 5800 lines - and `tools/sega/sega_spec_check.py`
runs their 61 scenarios, every one passing, most with a negative control
that fails as it should.  Step 1 was not done first: each spec names the
fields it uses in its own State section, and the records step now
gathers those into one checked table rather than starting from nothing.
Writing them corrected the deconstruction in several places (the sound
names, the win/lose flag labels, the 32-bit prerequisites, the EMC
opcodes 6/7/10/11/18); the specs' own "bugs" sections list what the
cartridge gets wrong.

### Goal

One document per gameplay subsystem, written so the game can be
reimplemented from it: state, per-tick order, formulas, tables, decisions,
and where the Mega Drive differs from the PC game.

### The specs and where each starts

| # | subsystem | entry points |
|---|---|---|
| S1 | the frame: tick order, timers, what runs how often | `game_battle_loop $0124D8`, `unit_tick_all $043784`, `struct_game_loop $00BCD8`, `game_loop_house $02375C`, `team_tick $02E444` |
| S2 | objects: creation, pools, removal, references | `unit_create $043326`, `struct_create $00E580`, the `$02Exxx` reference module |
| S3 | movement and pathfinding | `unit_move $04607C`, `unit_move_tick $047FBA`, `path_find $012AAE`, `path_follow_edge $012D5A`, `path_smooth $012E62`, `$005624` (tile enter score), `$00556A` |
| S4 | combat | `unit_find_target $048F00`, `unit_fire_projectile $04834A`, `unit_damage $046BA6`, `struct_damage $00F8D6`, explosions `$00A934`, the Deviator, the Death Hand |
| S5 | economy | `emc_unit_harvest $045A9C`, `emc_build_refine $00D068`, `map_find_spice $01A146`, `map_change_spice $01A518`, credits and storage, `house_calc_power $01048C` |
| S6 | production and the base | `struct_build_object $00FA84`, `struct_place $00E6CC`, prerequisites and upgrades, the Starport, `unit_deliver $048102` (Carryall) |
| S7 | the enemy | the EMC VM `emc_run $016EF0` and the four scripts (`res/data/scripts/`), teams, the house's build choice, reinforcements |
| S8 | the map and the fog | `map_load $01B1D4`, the icons, `map_unfog_radius $019FFE`, fog edges |
| S9 | a mission from start to end | `scen_load $016098`, the win and lose checks (`$0229B4`, `$022A28`), score, rank, the campaign, passwords |
| S10 | controls and screens | reference only: the port has its own front end |

### What a spec contains

- **State**: the record fields it uses, by the names from part 1.
- **The per-tick sequence**: what runs in what order and how often.
- **Every formula**, with its constants and their addresses.  Integer
  widths and rounding are kept as the 68000 does them.
- **Every table**, by address and with its contents - quoted from the
  generated resource files where they already exist.
- **Mega Drive against PC.**  Where the code matches OpenDUNE, say so and
  give the PC name.  Where it differs, say how: the Light Factory upgrade,
  house 2's WOR, the Palace countdown, and the rest listed in
  `sega-internals.md`.
- **The cartridge's own bugs**, each with a recommendation for the port:
  keep it or fix it.  Examples are the uninitialised `d6` in `$0446C8`,
  the Fremen Hunt test, and the first free Refinery chosen instead of the
  nearest.
- **Tests**: at least one scenario per spec that the emulator can check.
  Load a state, run N frames, and compare the RAM fields the spec
  predicts - a unit's position after M ticks of movement, a structure's
  hit points after a known hit, credits after one refinery unload.

### Deliverables

`orig/sega/spec/S1-frame.md` … `S10-screens.md`, and a
`tools/sega/sega_spec_check.py` that runs each spec's scenarios in
`retro-run` and compares the RAM.

### Done when

Every spec's scenarios pass.  Every formula cites its address.  No spec
refers to a raw offset or an unnamed routine.

---

## 3. The sound, to the General Sound card as MOD files

**Status (2026-09-26):** done for the conversion, by a route slightly
different from the plan below.  There is no chip log: the driver itself is
modelled (`tools/sega/sega_driver.py`), checked against the real game's
music test instead, and the chips are the core's own - `chiprender` for
the FM, the PSG and DAC in Python.  The card's ROM plays the modules
(decision A), and all 65 load and play in `bin/evo`.
`tools/sega/sega_mod.py` writes `src/res/prebuilt/music/*.mod`,
`sfx/*.mod` and `report.txt` from `src/res/sega_sound.txt`;
`.claude/docs/sound.md` has how.  Since done: effects play over a module
through the ROM's FX commands, and the port plays every sound by the
cartridge's own numbers (`src/gs.asm`).

### The principle

Work from what the chips were *told*, not from a recording of what came
out.  A mixed WAV has every voice baked together and
inseparable, and it is the wrong source for a tracker module.  The
Mega Drive's music is instruments playing notes, and a MOD is instruments
playing notes; the conversion should keep it that way.

Not everything is music, though.  The two banks hold 97 song slots (84
in the game's, 13 in the front end's), and what is in them falls into
three kinds, each going to the card differently.  Names come from the
options screen's music and sound tests (`$087F3C`, `$087FD4`), which pair
each name with its song number; the order of the name list at `$020870`
is not the numbering (`res/sound/music.txt`):

| kind | songs | what they are | to the card as |
|---|---|---|---|
| music | game bank 0-17 (the 18 tunes) and 18; front-end bank 0 | instruments playing patterns | **MOD**: samples from the instruments, patterns from the tracks |
| synthesised effects | game bank 20-44 (41 is not an effect but a fade-out: track command `$72` 4 raising the master attenuation); front-end bank 10-12 | FM or PSG sounds shaped by pitch envelopes, noise and slides - the "(fx)" rifle, machinegun, cannon, worm and static, explosions 1 and 2, the menu sounds | **one-shot PCM**, rendered whole from the chip model |
| sampled | game bank 64-83 | DAC samples: the speech **and** sampled effects - explosion 3, multi explosion, cannon, rifle, machinegun, missile, scream, squish, worm eats, static, placement, building | **the samples as they are**, resampled |

Many effects exist twice, a synthesised "(fx)" song and a sampled one;
which the game plays for an event is the effect table's choice
(`orig/sega/spec/S10-screens.md`).  The empty slots (19, 45-63, front
end 1-9) are nothing.

A song's kind is decided mechanically - track count, how long it runs,
whether it loops, which instrument types it uses (`instruments.txt`) -
with an explicit list of overrides for the borderline cases.

### Step 1: the register log

Add a command to the patched Genesis core that logs every YM2612 and PSG
register write, with its time in Z80 cycles or output samples.  The patch
goes in `tools/build_toolchain.py`, like `patch_gpgx_touch`, and
`retro-run` gets `chiplog FILE` / `chiplog off`.

Drive it through the options screen's music and sound tests
(`sega_touch.py` already knows the way in), one song at a time, from
silence to silence.  The result is deterministic, and it is exactly what
the driver asked the chips to do.

An alternative, if the in-game capture proves noisy: run the Z80 driver
alone in a Z80 emulator, feed it commands `$0B` and `$10` through the
ring, and log its port writes.  `commands.txt` describes the protocol
completely.

### Step 2: the chip renderer

Build a small standalone renderer from the core's own chip code
(`core/sound/ym3438.c` or `ym2612.c`, and `psg.c`) that replays a
register log to PCM.  It renders **each channel on its own** by muting
the others, which gives clean stems: the "expected output" of every
voice.  It lives in `tools/sega/chiprender/` and is built into
`bin/gen/` by `build_toolchain.py`.

### Step 3: instruments to MOD samples

For each instrument a tune uses (`instruments.txt`), synthesise a note
through the renderer from a made-up register stream (key on, hold, key
off):

- **FM**: render at a reference pitch.  The sustain is periodic once the
  envelope settles, so cut the MOD loop on a whole number of periods.
  The attack and decay go in front of the loop; the release becomes a
  volume slide or note cut at the note's gate.
- **PSG tone**: a square wave at a given attenuation, so synthesise it
  directly.  The driver's PSG envelope (attack, decay, sustain, release in
  `instruments.txt`) becomes volume commands on the pattern row.
- **PSG noise**: a rendered noise sample, looped.
- **DAC sample instruments**: the sample the note selects, as it is.

A MOD sample plays well over only a few octaves.  An instrument whose
notes span more than that gets one sample per octave band, and the
pattern picks the band.

### Step 4: tracks to patterns

- **Time**: the driver's music clock (tempo step `$08BE` per frame) and
  each event's delay become rows.  Choose rows per music tick per song so
  every event lands on a row exactly.  A voice on the frame clock
  (`frameclock`) is converted on its own timebase.
- **Notes**: driver note number → MOD period, and the sample band.
- **Gates**: note off → note cut (`ECx`) or a volume slide for the
  release.
- **Detune and pitch envelopes**: fine-tune (`E5x`) or portamento and
  vibrato (`1xx`, `2xx`, `4xy`) where they fit.  Where they do not - a
  swoop, a growl - the envelope is baked into a sample for that note.
- **Attenuation**: master plus voice, mapped to MOD volume (`Cxx`) through
  the same TL curve the driver uses (`L15F7`).
- **Structure**: `loop`/`endloop`, `jump` and `branch` → the pattern
  order, `Bxx` and `Dxx`.  Nested loops are unrolled.

### Step 5: the channel budget

A Mega Drive tune can sound up to eleven channels at once (six FM, three
PSG tone, noise, DAC).  A MOD has four.  For each tune:

- measure how many voices sound at once, from the stems;
- keep the voices with the highest driver priority (`voice+28`) and the
  most notes;
- mix the rest into the nearest kept voice's samples where they always
  play together (a drum pattern, a chord), otherwise drop them.

Write down per tune what was kept, mixed and dropped, and why.

### Step 6: effects and speech

- **Effects**: render each one's stems from its register log, sum them,
  trim the silence, and resample to the card's rate.  They go into the
  existing sample pipeline (`tools/gs_sound.py`) as one-shots, keyed by
  the game's own sound numbers.
- **Sampled songs**: the 30 DAC samples from `sega_seq.py --wav`, speech
  and sampled effects alike, resampled the same way.

### The decision to make first: who plays the MOD

The port currently takes the card over.  `src/gs/gsplayer.asm` replaces
the ROM and mixes four PCM channels.  There are two ways to add MOD
playback:

- **A. Use the card's ROM MOD player.**  General Sound's ROM plays
  ProTracker modules itself.  First read `bin/evo/gs105a.rom`'s command
  table (`$0300`) for the module commands - load, play, stop, and how
  effects play alongside - and test one module in `bin/evo`.  The cost:
  the port stops uploading its own player and works within the ROM's
  commands and their traps (`sound.md`: the first argument goes before the
  command, some commands cannot be used, block lengths are not
  complemented).
- **B. Teach `gsplayer.asm` to sequence patterns.**  Keep the current
  player and add a pattern reader that drives its four channels.  The
  cost: a tracker written in Z80 on the card, and `CARD_RATE` in
  `tools/gs_sound.py` re-measured after every change to the mixing loop.

**Recommendation:** try A first.  It is a reading and a test, not a
rewrite.  If the ROM cannot play effects over a module the way the game
needs, fall back to B with what A taught about the format.

### Deliverables

- `retro-run chiplog`, the patch that makes it possible, and
  `bin/gen/chiprender`.
- `tools/sega/sega_mod.py`: songs → `.mod` for the tunes, one-shots for
  the effects, plus a report per song (kind, channels kept, mixed and
  dropped, samples made).
- `src/res/sega_sound.txt`, naming what goes onto the disk.  This follows
  `nes_sound.txt`'s pattern: resources are text, and the binaries are
  built.

### Done when

- **Every tune converts, and a check compares it:** rendered offline, the
  module matches the kept stems in note timing (exact to a row) and pitch
  (within a few cents).  Plays that differ are listed.
- **Effects are indistinguishable** from their summed stems at the card's
  rate.
- **It plays on the machine:** `make verify` passes with the new sound,
  and `CARD_RATE` is re-measured if the player changed.

---

## Order and size

| step | depends on | size |
|---|---|---|
| 1. records | - | medium: one tool, one table, runtime dumps |
| 2. specs S1-S9 | records | large: nine documents, each a real reading job; S3, S4 and S7 are the biggest |
| 3. sound, the decision (A or B) | - | small |
| 3. sound, chiplog and renderer | - | medium |
| 3. sound, the converter | chiplog, renderer, the decision | large |

Records and the sound work can start together.  The specs follow the
records, and can then be split one subsystem per worker, the same way the
routine naming was.
