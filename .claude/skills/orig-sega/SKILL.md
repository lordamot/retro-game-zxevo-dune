---
name: orig-sega
description: Work on the Mega Drive original's deconstruction under orig/sega - the 68000 disassembly, the strings and Westwood asset table, the tiles and palettes, the sound layout, and rebuilding the cartridge. Use when asked how the real Dune II works, where something is in its ROM, or to change and rebuild it.
---

# The Mega Drive original, taken apart

`orig/sega/` is *Dune II - The Battle for Arrakis* (Virgin/Westwood, 1994)
disassembled into sources that build the 1 MB cartridge back **byte for
byte**.  `.claude/docs/originals.md` is the full account.

## The commands

```sh
make orig-sega                                # take it apart again, rebuild, check
make run sega                                 # rebuild and play it
python3 tools/sega/build_sega.py              # just rebuild, SHA-256 checked
python3 tools/sega/build_sega.py --no-check   # rebuild after changing something
python3 tools/sega/run_sega.py --script tools/md_battle.script --shot tmp/sega/x.png
```

## Where things are

| | |
|---|---|
| `orig/sega/rom.map` | what every byte of the ROM is |
| `orig/sega/gaps.txt` | what is still nobody's - empty, and it should stay that way |
| `orig/sega/regions.txt` | every named region and what it is |
| `orig/sega/res/trace.txt` | what the running game did with each byte (`make sega-trace`) |
| `orig/sega/res/names/*.txt` | the routines' names, each with `does`, `in`, `out` and `affects` - checked by `tools/sega/sega_names.py check`, written into the listing by the extractor |
| `orig/sega/src/vectors.asm` | the 68000 exception table |
| `orig/sega/src/rom00.asm` … `rom0F.asm` | the cartridge, 64 KB a file |
| `orig/sega/src/megadrive.inc` | the VDP, the Z80 and the pads by name |
| `orig/sega/res/text/assets.txt` | each thing's name and its Westwood `.wsa` |
| `orig/sega/res/art/` | the uncompressed tiles, the palettes, and the index |
| `orig/sega/res/sound/sound.txt` | the Z80 driver and the sample banks |
| `orig/sega/res/sound/music.txt` | the driver's commands, its resource banks and 97 songs |
| `orig/sega/res/data/files/` | Westwood's own data files, extracted whole |
| `orig/sega/res/data/{buildings,units,houses,missions}.txt` | the game's numbers |
| `orig/sega/spec/S*.md` | the game specified subsystem by subsystem - state, tick order, formulas, Mega Drive against PC, bugs - tested by `tools/sega/sega_spec_check.py` |
| `orig/sega/res/data/files/SCEN*.ini` | the 27 missions written back as text |
| `orig/sega/res/data/actions.txt` | the fourteen orders, and each unit's default |
| `orig/sega/res/data/functions.txt` | what each routine a script can call does |
| `orig/sega/res/data/scripts/` | the four `.EMC` scripts, disassembled |
| `.claude/docs/sega-internals.md` | what all of that says about the game |

## Before reverse-engineering anything about the game

Look in `orig/sega/res/data/` first.  The cartridge carries the PC Dune
II's own data files - `PROFILE.INI`, `HOUSE.INI`, the campaign maps, the
27 missions, and four `.EMC` script files that are the AI - and they are
already extracted.  A question like "what does a Siege Tank cost" or "how
does the enemy get harder" is answered there, not in the 68000.

## Things that will catch you

- **The running game is the ground truth, and it is recorded.**  The
  Genesis core is patched to flag every cartridge byte it executes, reads,
  DMAs to VRAM/CRAM or lets the Z80 read, with the first reader's address
  (`retro-run`'s `touch`, `reader`, `untouch`, `blind`).
  `tools/sega/sega_touch.py` plays scripted scenarios (every password,
  the music and sound tests, SPLURGEOLA to win, DUNEFINALE for the ending)
  and a coverage-guided random player, and writes `res/trace.txt`.  The
  extractor trusts it before any reading: executed is code, read-only is
  not.  Before arguing about what a block is, look at who reads it there.
- **Every region's meaning lives in a module with a `check()`**:
  `sega_tables_lo.py` (banks 00-01), `sega_tables_hi.py` (02-05),
  `sega_blocks.py` (06-0F), `sega_sprites.py`, `sega_pictures.py`,
  `sega_maps.py`, plus `NAMED` in `sega_extract.py`.  The extractor runs
  the checks and stops if one fails; a region two modules both claim with
  different extents is reported to `tmp/sega/clashes.txt`.  Change the
  module, not the listing.
- **A named region is data even to a guess**: the static trace may not
  decode into one unless the machine fetched those bytes.  Without that,
  pointer-shaped longwords walk into portraits and palettes.
- **Passwords get anywhere.**  The table at `$08811C` (29 of them,
  `res/data/passwords.txt`): a mission for every house, DUNEFINALE (the
  ending, typed in a battle's options), SPLURGEOLA (25000 credits - wins a
  quota mission), PLAYTESTER (the player takes no damage), LOOKAROUND.

- **All sixteen files assemble as one program.**  The cartridge is one
  address space and a subroutine in `rom02` is called from half the
  others, so `build_sega.py` uses `assemble_many()` with one shared symbol
  table.  Assembling a file on its own will fail on the first cross-file
  label.
- **The addressing rules are the code/data test.**  `move.w d0,$1234(pc)`
  does not exist, a byte immediate has a zero high half, a branch never
  lands on an odd address, and bits 10-8 of a brief extension word are
  zero on a 68000.  `alterable()` in `tools/sega/m68k.py` enforces that;
  loosening it fills the listing with tables read sideways.
- **Do not relax the round-trip check** in `tools/sega/sega_extract.py`.
  Every instruction is re-encoded before it is written and anything that
  does not match becomes `dc.w`.  That is the whole reason the rebuild can
  be byte-exact without trusting the disassembler.
- **The art is decompressed.**  Westwood Format80, decompressor at
  `$000C32`, `tools/sega/sega_gfx.py`: every building and unit in its own
  colours in `res/art/sprites/`, and 6791 more tiles in `res/art/blocks/`
  from the `(count.w, pointer.l)` lists the loader at `$000CD8` reads.
  Bit 15 of the *count* is the compressed flag - MOVEA sets no flags on a
  68000, which is what the `bpl` after it is really testing.
- **An asset list is only real if every block in it is compressed.**  Six
  bytes shaped like a count and a pointer are six bytes of anything, and a
  raw block is checked by nothing; a compressed one has to survive the
  decompressor.  Relaxing this claims 75 lists instead of 14 and swallows
  119 710 bytes of traced code.  Do not relax it.
- **The AI is not 68000 code.**  It is Westwood EMC script bytecode at
  `$04DB28`, and `tools/sega/emc_disasm.py` reads it: one entry point per
  building in `BUILD.EMC` and per unit in `UNIT.EMC`, proved by the counts
  (19 and 27) and the sizes (the four infantry get 19 words each).  All
  nineteen opcodes are named out of the interpreter's own switch at
  `$016F40`, and 48 of the 88 distinct routines behind the 104 call slots
  are named in `res/data/functions.txt`.  The three scripts differ only in
  which global they work on - `$FFDEA0` a unit, `$FFD5AC` a structure,
  `$FFDCA8` a team, `$FFC208` whichever it is - and everything they pass
  around is a **tagged reference**: top two bits the kind (1 unit,
  2 structure, 3 a map square - not the other way round, which is how it
  was first written down), read by the `$02Exxx` module.
- **A call site is `push` args, `call`, `drop n`, then `push the return
  value` only if the answer is wanted** - and in that order.  The drop
  comes first; looking for the push first says almost everything is an
  order, which is wrong and was wrong here once.
- **The fourteen orders are named, at `$06CEF8`**, and the name of order
  *n* is the longword **four bytes before** its record.  That is what puts
  Attack at 0 rather than Move, and it is confirmed twice over: every unit
  type's default order at `+$28` comes out right (Guard for fighters, Stop
  for carriers and projectiles, Attack for the Sandworm), and the two
  orders that may interrupt a busy unit are exactly Die and Destruct.  The
  mission files and a script's `act` use the same numbering.
- **Variable 0 of a unit's script is the order it is under.**  `$043766`
  in `$0436A0` writes it to unit+`$22`, which is variable 0 of the script
  object at unit+`$16`.  Every unit routine is a switch on it.
- **A `jmp TBL(pc,Xn.w)` is a switch and the table is readable.**  47 of
  them, and `switch_tables()` in `sega_extract.py` reads all 47: the table
  starts where the jmp's own displacement points, it is word offsets or a
  ladder of `bra.s`, it ends at the lowest address its entries name, and
  the `cmpi.l #N,Dn` in front confirms the count.  Do not drop the guard -
  three tables read one entry too many without it.
- **A mission file's format is the loader's, at `$0161F0`.**  Eleven
  sections, a handler each, and every handler says how long its record is.
  The check is that all 27 files parse straight through and end on their
  own `$FFFF` with nothing over.  Do not go back to looking for runs of
  records at a constant spacing: that reading had the reinforcements down
  as structures, because a map position's high byte is `$0A` and so is the
  reinforcement tag.  Section 5 is the **Sardaukar**, section 6 is
  **CHOAM** - the starport's stock, keyed by unit index.
- **`$060E84` is the animation table**: 357 records of eight bytes, each
  two tagged 24-bit addresses - the pixels and the list that goes with
  them - read at `$004B7A` and `$004BB2`.  It ends at `$0619AC`, which is
  the lowest address it points at; that is the check, not a guess.
- **Two sets of numbers disagree, and the binary one wins.**  The table at
  `$06AFA6` and the text `PROFILE.INI` give different costs for the Palace
  and the Carryall.  The game never opens `PROFILE.INI`: filenames are
  built by `"SCEN%c%03d.INI"` ($016086) and `"%s.EMC"` ($016D26), and the
  words PROFILE, HOUSE, REGION and PLAYER are nowhere in the code.  Quote
  the table.
- **Art comes from two places, not one.**  The `(count, pointer)` asset
  lists the loader at `$000CD8` reads, and plain tables of longwords that
  each land on a Format80 block - `stream_tables()` in `sega_gfx.py`,
  five of them, 3911 tiles.  Both rest on the same check: the block has
  to decompress to a whole number of tiles.
- **The game names its own 58 sounds at `$020870`, but not in song
  order.**  The options screen's music and sound tests (`$087F3C`,
  `$087FD4`) pair each name with its song number, and that is the only
  map: `moveq #40` is "positive select", the click, not "explosion 1"
  (38).  Songs 64-83 are sampled and hold explosions, gunfire, screams
  and the worm as well as the speech; most effects also have a
  synthesised "(fx)" twin in 20-44.
- **The sound library is called with `jsr $xxxx.w`.**  Absolute *short*,
  `4EB8`, not `4EB9` - so a cross-reference scan that knows only the long
  form and the pc-relative ones finds nothing but the initialiser and
  concludes the game never plays a sound.  It does; `res/sound/music.txt`
  has all seven commands it sends and where from.
- **A song is a directory of 16-bit offsets, then tracks.**  The 68000
  hands the driver four 24-bit resource pointers with command `$0B`
  (`$02DD14` for the front end, `$02DCC8` for the game) and starts a song
  by number with `$10`.  The third pointer is the directory; a track is a
  byte stream where `< $60` is a note, `$60-$72` are nineteen commands and
  the two high forms are the note's length and the delay after it.
  `tools/sega/sega_seq.py`, 97 songs in 143 tracks.  What a sound *is* -
  the 39-byte instrument record, byte 0 its type (0 FM, 1 DAC sample, 2
  and 3 PSG tone and noise, `$63` silent) - and the pitch envelopes are
  in `res/sound/instruments.txt`, from `tools/sega/sega_instr.py`.  Every
  driver command and track command is in `res/sound/commands.txt`, from
  the COMMANDS and TRACK tables in `sega_seq.py` - count a handler's bytes
  through the routines it calls (`L08A5` reads the voice number).
- **To see what the driver is really doing, dump the Z80's RAM.**  The
  Genesis core is patched to hand it over: `z80 FILE` in a `retro-run`
  script writes the 8 KB, and the ring at `$1B40` with its indices at
  `$0036`/`$0037` says exactly what the game has asked for.

## Changing something

Edit the source, rebuild with `--no-check`, play it with `make run sega`.
Put the check back afterwards.

## Naming a routine

Names live in `orig/sega/res/names/*.txt`, a block a routine:

```
$023720  house_are_allied
  does:    ...what it does, in the game's terms
  in:      4(a7).w one house, 6(a7).w the other
  out:     d0 1 allied, 0 not
  affects: d1, a1
```

All four fields are required.  `python3 tools/sega/sega_names.py check`
validates (identifier, unique, on an instruction start), `stats` says
which called routines lack a name.  Then `python3 tools/sega/sega_extract.py`
and `build_sega.py`.  Much of the code is the PC game's C: OpenDUNE's names
are a fair hint, but the description has to be of this cartridge's code.
