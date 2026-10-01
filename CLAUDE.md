# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in
this repository.

## Project overview

This project ports the Mega Drive **Dune II - The Battle for Arrakis** to
the **ZX Evolution BaseConf** (Z80 at 14 MHz, 4 MB, a General Sound card
with 2 MB).  It is built as **`build/DUNE.DAT`** - the whole game in the
machine's paged-executable format (SPG), up to 4 MB, every byte the game
needs loaded into RAM pages at once - and shipped as **`build/dune.trd` +
`build/DUNE.DAT`**: the BaseConf firmware runs no SPG file, so a TR-DOS
disk it does boot carries a loader (`src/loader/loader.asm`) that reads
DUNE.DAT off the SD card itself.  There is no `dune.spg` any more; the
emulator's `spg` command loads DUNE.DAT (the same bytes).

The game runs in the ZX Evolution's **ATM EGA mode - 320x200 in sixteen
colours out of 64 - at 14 MHz**, double-buffered, which is what the whole
renderer is arranged around.  The Mega Drive's battlefield uses 31 colours
on a 320x224 screen; the port chooses sixteen and draws the rest as fixed
two-colour checkerboards (`tools/dune_art.py`).

Nothing is installed on the host.  The repo builds its own assembler, its
own **ZX Evolution emulator** (`tools/evo-emu/`, a scriptable frontend over
libxpeccy, since no buildable one exists here) and both reference machines'
libretro cores into `bin/`.

```
make build     # src/ -> build/DUNE.DAT + dune.trd (what a real machine runs)
make run       # play it (SDL2 window, sound; the ZX keys are the Mega Drive pad)
make run HOUSE=A MISSION=3   # ... straight into that battle (H A O, 1-9)
make verify    # start it headless and check from memory that a battle,
               # the front end, building and the sound card really work
make demo      # build straight into a battle and photograph it
make shot      # photograph the SPG five seconds in
make sega      # the Mega Drive's music and effects as General Sound .mod files

make toolchain # rebuild the assembler, the emulator and both cores
```

Key documentation: `.claude/docs/port.md` (the port's shape: the SPG, the
pages, the windows, the record layouts), `.claude/docs/port-code.md` (how
the Z80 code is organised: banks, `FCALL`, the library, the script
machine, who owns what), `.claude/docs/progress.md` (state of the port),
`.claude/docs/platform.md` (the machine: video, the memory manager, the
shadow ports, the palette, starting an SPG), `.claude/docs/graphics.md`
(the planes, the renderer's dirty cells, sprites, the front end's
pictures), `.claude/docs/gamedesign.md` (the game as the port plays it, and
where it deliberately differs from the cartridge), `.claude/docs/build.md`
(the pipeline and the checks), `.claude/docs/emulator.md` (the emulator,
its script language and its profiler), `.claude/docs/sound.md` (the
Mega Drive's sound on the General Sound card), `.claude/docs/tools.md`,
`.claude/docs/sega-internals.md` and `.claude/docs/originals.md` (the
deconstructions), `.claude/docs/sega-handover.md` (how the deconstruction
became the specs the port is written from), `.claude/docs/nes-tools.md`
(the two reference machines and their script language).  Follow
`.claude/rules/guideline.md` and `.claude/rules/git.md`.

## Traps worth remembering

- **The Kempston port answers only with the shadow ports shut.**  The
  manual marks `#xx1F` "noshad": with `$BF` bit 0 set, which the game
  keeps for the manager and the palette, port `$1F` is the floppy
  controller's status (TR-DOS mode on) or nothing at all - and nothing at
  all reads as the byte the video is fetching, so the pad saw random
  presses every frame on a real machine: the intro skipped before its
  tune, menus wandering, a restart chosen.  `pad_read` shuts the shadow
  ports for the one read (`src/stub/input.asm`).  The emulator answers
  the floppy status there and never showed it.
- **The BaseConf firmware does not run SPG files.**  Its file browser
  knows TRD, SCL, FDI and TAP; an .spg is "unknown", and choosing one
  stages it into RAM from page #F4 downwards until it wraps into the
  firmware's own pages - a black screen on a real machine.  SPG is a
  TS-Conf format (TS-BIOS, Wild Commander).  So the game is delivered as
  `dune.trd` + `DUNE.DAT`: the disk's loader reads the SPG off the card
  over the SPI port (`src/loader/loader.asm`, `tools/dune_trd.py`), and
  `make verify` boots it that way, from FAT16 and FAT32 card images
  (`tools/sd_image.py`, `bin/evo/evo-run --sd`).
- **No block may live in pages #E0-#FF.**  The SPG format allows #00-#DF
  because every loader keeps itself above that (the firmware's resident
  code is in FE, Wild Commander's runner runs from FE).  The Tutorial once
  sat in 249-254 and would have overwritten any loader; `tools/spg.py`
  now refuses such a page and the Tutorial is in 221-223, 0, 4, 6.
- **libxpeccy's SD card never left multi-block mode.**  Its CMD12 branch
  does not clear the flag and CMD17 falls into CMD18's case, so after the
  firmware's CMD18/CMD12 reads a program's single-block read never ends
  and its next command is swallowed - the loader "read" zeros and died on
  the MBR.  `tools/build_toolchain.py` patches `sdcard.c`; a real card is
  fine.
- **Bit A9 of port `xx77` holds TR-DOS mode on.**  `PORT_77` was `$8177`
  (A9 = 0): TR-DOS mode never switched off, so port `$1F` read the floppy
  controller's status instead of the Kempston stick and every floppy-port
  access went through the firmware's virtual-drive trap, which is armed
  because the game boots from the virtual drive.  The emulator does
  neither.  `$8377` (A9 = 1) lets TR-DOS mode drop at the first RAM
  instruction; the shadow ports stay open through `$BF` bit 0.
- **A palette write changes the colour under the beam.**  Port `$FF`
  changes the entry of whatever colour the display is showing at that
  instant; only in the border is that the border register.  The emulator
  uses the border register always, so `vid_palette` writing mid-picture
  looked fine there and gave every screen the wrong colours on a real
  machine (blue intro, white mentat, orange house menu).  It now waits
  for the frame interrupt and writes in the top border.
- **A real machine's RAM is random; the emulator's is zero.**  The SPG
  carries no zero pages and trims every page's zero tail, and the game
  had trusted those zeros.  `boot.asm` zeroes everything the SPG did not
  fill from a table the build writes; `fillram SEED` in an evo-run script
  is the test.  The firmware's TR-DOS also does not leave the BASIC ROM
  at `$0000`: the disk loader carries its own font.
- **The configuration ports are shadow ports.**  `xx77` (video mode and
  clock) and `xxF7` (the memory manager) only answer while bit 0 of port
  `$BF` is set.  Anything that goes through BASIC or TR-DOS leaves them
  shut, and an `OUT` into a shut port changes nothing, silently.
  `src/boot/boot.asm` opens them first thing.
- **The short memory-manager port is only safe after the long one.**  The
  short `xx7F7` form (eight bits of page, inverted - all 256 pages) leaves
  the window's "mix the page number with `$7FFD`" flag alone, and the
  firmware sets it on window 3 - so the page you asked for is not the page
  you get.  `boot.asm` maps each window once with the long `xxFF7` form,
  which clears the flag; from then on the stub's `map_w1`/`map_w3` use the
  short form.  And never write `$7FFD` with bit 4 clear: that bit picks
  which set of window registers is live.
- **A plane byte is two pixels, not a colour.**  `vid_fill_page` writes the
  byte it is given into both planes, so filling with colour 7 paints
  `00000111` - one gold pixel and one black - all the way across, and the
  screen comes out striped.  `vid_colour_byte` turns a colour into the byte:
  the low three bits doubled into bits 3-5, bits 6 and 7 lit if the colour
  has its top bit.  `.claude/docs/graphics.md` has the layout.
- **The records keep the 68000's offsets but not its byte order.**  A word
  at `+$k` has its low byte at `+$k`, so a 68000 `btst #n,$k(a2)` on an
  even `k` is bit `n` of byte `+$k+1` here.  `.claude/docs/port-code.md`
  has the table; read it before touching a flag.
- **A bank's own address handed across an `FCALL` is the other bank's
  bytes.**  `unit_launch_house_missile` (COMBAT2) passed `HL = cb_2p`, its
  private static, to `cb_tile_move_by_random` in COMBAT: after the switch
  the callee read COMBAT's code at that address, took it for an out-of-
  bounds position and wrote nothing, so the Death Hand was never scattered
  - and a relayout of COMBAT would have turned the miss into a write into
  code.  Anything a far call reads through a pointer goes through
  windows 1-3 (`arg_pos` in WORLD); `port-code.md` says so, and this is
  what it looks like when forgotten.
- **A profiling build crashes unless the profiler is on first.**  The
  emulator swallows a `PROF` mark only while `profile` is on; with the
  FPGA-faithful `$7FFD` decode a mark that reaches the port switches the
  memory manager's register set, as on the real machine.  `profile` goes
  before `spg` in the script.
- **The renderer has two of everything, one a screen.**  Two screens,
  two lists of records, two sets of "what this screen shows"; a single
  byte that says "done" (the orb's frame, the radar picture's version)
  is right for the screen that set it and leaves the other a step behind
  for ever - the orbs jumped between two phases after the options screen.
  Per-screen state goes in `rf_select`'s set (`rf_lastv`, `rf_orbf`,
  `rf_rgenp`).
- **`ld bc,nn` eats a `djnz` counter.**  This has cost hours twice: `pop bc`
  must come *after* the `ld bc` that steps a pointer.  The symptom is that
  the game runs, but at a fifth of the speed.
- **A string ends with `$FF`, not zero** (`build/gen/text.inc`: ASCII, as
  the cartridge keeps it; `$0A` a new line, `$FE n` a colour).
- **A mailbox call that has not finished corrupts the answers after it.**
  `tools/dune_test.py` queues all its calls into one emulator run; if one
  is still running when its pages are dumped, the next call is poked into
  a busy mailbox and never served - its step reports the slow call's
  results - and a call that never returns leaves every later step with
  nothing.  Check `regs(step)["done"]` for every call -
  `tools/tests/test_struct.py` counts unfinished calls.  That is how an infinite loop in production
  (a house with 1-255 credits locked the machine) was found - it had been
  reported as "26 of 50 production cases are off".
- **The only start that counts is the firmware's: file browser, mount
  `dune.trd` as drive A, TR-DOS boot.**  That is how the real machine is
  started, by decision, and the SPG on its own is not a way in any more.
  `make verify` boots the disk too, but with it inserted as a real floppy:
  the firmware's virtual drive (its `trdemu` trap on the floppy ports, which
  a mounted disk goes through) is not modelled by libxpeccy, so the boot
  the real machine does is only partly tested here.
- **`OUT ($FD),A` with A below `$80` is a `$7FFD` write on the BaseConf.**
  The FPGA decodes that port on A15 = 0 and the low byte alone
  (`zports.v`: `(a[15]==1'b0) && portfd_wr`), and bit 4 of the value picks
  which set of window registers the memory manager uses.  The profiler's
  marks were exactly that with values below 16, "inert on hardware" by a
  wrong reading of the decode: the front end has none, the battle's first
  pass has twenty, and the real machine hung, restarted or ran garbage at
  every level start while libxpeccy - which wanted A14 = 1 too - played on.
  A game build now has no marks (`PROF` assembles only with `--profile`),
  and `build_toolchain.py` patches libxpeccy to decode as the FPGA does.
  The crash catcher below found it: a jump to 0 with SP inside the code.
- **Bits 1-6 of the sound card's status port mean nothing.**  Every
  emulator reads them as 1s (libxpeccy, ZEsarUX and MAME all OR in `$7E`)
  and so does an original GS, through the bus's pull-ups; `gs_probe`
  wanted them so, and a NeoGS - whose FPGA drives all eight lines, bits
  1-6 "don't care" (`zxbus.v`) - was "GS detect error".  The probe now
  toggles the data flag (write `$B3`: bit 7 set; read `$B3`: clear),
  which is the card's hardware on every GS.  A NeoGS is also not reset
  with the machine, so `gs_init` reads away a byte left in the latch.
  `gsneo` in an evo-run script is that card; `make verify` runs it.
- **The sound card's own page count is not to be trusted.**  The
  ZX-MultiSound rev.A1 has 1 MB and its ROM reports 62 pages - the ROM's
  test catches a plain alias and not what that card does - so the tunes
  loaded for 2 MB landed on each other.  `gs_pages_check` marks every
  listed page in both halves and keeps only the pages that hold their
  marks (`sound.md`).  `gsram 1024` in an evo-run script is the honest
  1 MB card.
- **Every mission is read from the same buffer, so a pointer into it
  outlives the file.**  `scen_blooms` was set when a file had a Bloom
  section and never cleared; the next file without one, loaded after a
  won level, took the old pointer into its own records and stamped the
  bloom icon under every unit.  A password load showed nothing, because
  the pointer was still zero.  `scen_load` clears it before parsing;
  `test_struct.py reload` loads a mission after another.
- **The stub is code only, and a write into it is a crash later,
  elsewhere.**  Every code bank carries the same stub at `$0000-stub_end`,
  with no variable of its own; a pointer gone wrong while window 0 holds
  a bank writes into that bank's copy, and the game dies a pass or a
  minute later in a routine that has nothing to do with it (a slab placed
  freed a record that was on no side list; `struct_list_unlink` walked
  `list_unlink` with the wrong descriptor and wrote `$FF` into OBJ's
  `unit_info`).  `make verify` now checks every bank's stub against
  MAIN's after the battle, and `wtrap 0000 09FF` in an evo-run script
  names the writer; `pctrap 4000 7FFF` names the jump when the CPU has
  fallen into data.
- **A crash on the real machine shows a screen, not a guess.**  The frame
  interrupt counts frames in which the game neither halted for a frame nor
  beat `wd_idle` (the battle's pass, `gs_tick`); at `WD_LIMIT` (30 s) the
  stub's `crash_go` maps FRONT and `front_crash` prints, on the log's
  screen, `0` (the watchdog) or `1` (a jump to address 0), then `PC`,
  `B` (the bank in window 0) and `SP`, and eight words from the top of
  that stack (world_vars.inc `wd_*`).  Read the photo against
  `build/dune.sym`: `bank_of.txt` says which bank a routine lives in.
  Nothing jumps to 0 on purpose any more; a restart goes through
  `main_entry`.
- **The tests build nothing of their own.**  They read `build/` (after
  `make build`) unless `--build-dir` says otherwise; a directory left by an
  earlier `--build-dir` run is a stale game, and tests pass or fail against
  that instead.
- **libxpeccy counts key presses per matrix bit.**  Two presses with no
  release between them leave the count at two, and the next release cannot
  lift the key: it is held down for ever.  SDL repeats key-down events
  while a key is held, so a frontend that passes those on jams every key it
  touches.  `evo_key` makes press and release idempotent and `evo-play`
  drops `ev.key.repeat`; both are needed.
- **`evo-play` keeps the machine's time, not the monitor's.**  A ZX
  Evolution frame is 49.1 a second; paced by vsync on a 60 Hz monitor the
  game and the sound card ran 23% fast and the music sounded rushed,
  which looks like a game bug and is not one.  `EVO_PLAY_STATS=1` prints
  the rate it really ran at.
- **`IN A,(n)` puts A on the top half of the address bus**, so a keyboard
  half-row goes in A, not B.
- **The General Sound card's first argument goes *before* the command**,
  some of its ROM's commands cannot be used at all, and a block's length
  goes across uncomplemented.  All three are in `.claude/docs/sound.md` and
  all three cost an afternoon.
- **Genesis Plus GX stores VRAM native-endian**, so every 16-bit word is
  byte-swapped from the Mega Drive's own layout.  Read `tmp/md/vram.bin`
  through `tools/md_dump.py`, not by hand.
- **A disassembler that cannot re-assemble what it wrote is not allowed
  to write it.**  Both deconstructions under `orig/` rest on this: the
  extractor re-encodes every instruction the moment it decodes it and
  emits `dc.w`/`.byte` for anything that does not come back identical, so
  a bad guess costs readability and never correctness.  Do not "improve"
  either disassembler by relaxing that check - the byte-exact rebuild is
  the only thing keeping the sources honest.
- **When reading and the machine disagree, the machine is right.**
  `orig/sega/res/trace.txt` records what the running Mega Drive game did
  with every cartridge byte - ran it, read it, DMA'd it, let the Z80 read
  it - and who read it (`make sega-trace`, `tools/sega/sega_touch.py`, a
  patched Genesis core).  It found 96 KB of "DAC samples" at `$070000`
  that the Z80 never reads (the 27 stored maps), a decoder bug, and code a
  pointer scan had filed as a table.  Look up who reads a block before
  arguing about what it is.
- **A mission's `Seed` is a map number, not a seed.**  The Mega Drive
  stores all 27 battlefields made (`$01B276`, `res/data/maps.txt`); the
  PC generator is not in the cartridge.
- **A Format80 stream ends with the `$80` the decompressor reads.**  A
  decoder stopped by "enough output" leaves that byte out of every block
  - 78 one-byte orphans once.  `lcw(expect=)` now eats it.
- **Every region's meaning lives in a module with a `check()`** - the
  `sega_tables_*`, `sega_blocks`, `sega_sprites`, `sega_pictures` and
  `sega_maps` modules, and `NAMED`.  The extractor runs every check and
  may not decode code inside a named region the machine never fetched.
  Edit the module, never the listing; `gaps.txt` is empty and should stay
  so.  Routine names are the same: `orig/sega/res/names/*.txt`, a block a
  routine with `does`, `in`, `out` and `affects`, checked by
  `tools/sega/sega_names.py check`.
- **The order of the sound names is not the song numbering.**  The 58
  names at `$020870` are joined to songs only by the options screen's
  music and sound tests - (name pointer, song number) records at
  `$087F3C` and `$087FD4`, handed to `snd_song_start` as they are.
  Read by position they call the menus' click (`moveq #40`, thirteen
  sites) "explosion 1"; it is *positive select*.  Read properly, songs
  64-83 are not only speech: explosions, gunfire, screams and the worm
  are sampled too (71 "explosion 3", 69 "cannon", 76 "scream"), and
  most effects also have a synthesised "(fx)" twin in songs 20-44.
  `sega_seq.py` names songs through the tests; do not go back to the
  position.
- **A RAM dump from the Genesis core is byte-swapped too**, like its
  VRAM: every 16-bit word of `retro-run`'s `ram FILE` has its bytes the
  other way round.  Read the 68000's work RAM through the `Ram` class in
  `tools/sega/sega_spec_check.py`, where a timer that should step by one
  otherwise appears to step by 256.
- **The gap sweep must not read a named region.**  `gap_sweep()` in
  `tools/sega/sega_extract.py` takes a bitmap of what is already spoken
  for and stops at it.  Without that it calls pictures code: a Format80
  stream beginning `81 00` decodes happily as `sbcd.b d0,d0`, and five
  such lines in a row are the whole of the sweep's test.  Fixing it moved
  5762 bytes out of "code" and is why that figure went *down*.
- **Not all the art is in an asset list.**  Some hangs off a plain table
  of longwords - three or more in a row where every one lands on a
  Format80 block that comes out to a whole number of tiles.  Five such
  tables, 3911 tiles, 44 KB.  `stream_tables()` in `sega_gfx.py`; the
  whole-tile test is the only thing keeping it honest, so do not relax it.
- **`jsr $xxxx.w` is how the sound library is called.**  Absolute
  *short*, `4EB8`, not the `4EB9` of a long address - and a
  cross-reference scan that knows only `4EB9`, `4EBA` and `61xx` finds
  the initialiser, nothing else, and concludes the Mega Drive Dune II
  never plays a sound.  It plays 97 of them: `orig/sega/res/sound/
  music.txt` has the driver's 24 commands, the four resource pointers
  command `$0B` installs, and every song's every note.  When a scan says
  a whole subsystem is dead, suspect the scan.
- **The Z80's 8 KB can be dumped, so ask the machine.**  `z80 FILE` in a
  `retro-run` script writes it out (the Genesis core is patched for it),
  and the sound driver's whole state is in there: the command ring at
  `$1B40` with its indices at `$0036`/`$0037`, the sixteen voices at
  `$1B80`, the resource pointers at `$0AA5`.  That is what settled the
  question above in one run.
- **A `jmp d(pc,Xn.w)` is a switch, and the table after it can be read
  exactly.**  47 of them in the Mega Drive cartridge, worth 4 KB of code -
  the scenario loader and the whole EMC interpreter among it.  The table
  ends at the lowest address its own entries name, and the `cmpi.l #N,Dn`
  in front of the jmp says the same count again; keep both, because three
  tables read one entry too many on the first test alone, and one of those
  swallowed two bytes of the routine's own code.
- **An EMC call site is `push` args, `call`, `drop n`, and only then
  `push the return value` if the answer is wanted.**  In that order.
  Looking for the push before the drop says 13 of 79 script routines are
  questions; reading them the right way round says 36.  The drop is what
  gives the arity and the push is what gives the question-from-order
  split, and both are in `res/data/functions.txt`.
- **The fourteen orders are at `$06CEF8`, and an order's name is the
  longword four bytes *before* its record.**  That is where the record in
  front ends, and it is what puts Attack at 0 rather than Move - get it
  wrong and every unit in every mission file is reported one order out.
  Two independent checks: each unit type's default order at `+$28` comes
  out sensible (Guard for fighters, Stop for the Carryall, Harvester, MCV
  and projectiles, Attack for the Sandworm), and the only two orders that
  may interrupt a busy unit are Die and Destruct.
- **A mission file is read by the switch at `$0161F0`, not by pattern.**
  Eleven sections with a handler each, and the handler is what says how
  long a record is.  The test is that all 27 files parse straight through
  and land on their own `$FFFF` with nothing left over - which the older
  constant-spacing reading could not do, and it had the reinforcements
  down as structures because a map position's high byte is `$0A` and so is
  the reinforcement tag.  `SCENO009.INI` is the last file in the directory
  and its length has to come from that `$FFFF`, not from a next entry:
  it is 2726 bytes, and was cut 1212 bytes short for exactly that reason.
- **`make run nes` is two goals, not an argument.**  make has no
  arguments, so `nes` and `sega` become no-ops when `run` is also asked
  for and the `run` recipe reads `MAKECMDGOALS`.  The no-op recipes are
  conditional rather than a second definition, or make warns on every
  invocation.
- **The sound driver is modelled, not logged.**  `tools/sega/sega_driver.py`
  plays songs the way the Z80 does; its full render lines up with the real
  game's music test at zero lag.  Three things it had to get right that
  the docs had wrong or left out: a new note never keys off the voice's
  last one (it takes another channel and both sound), a pitch envelope
  snaps back to 0 when it ends, and delays and gates are sticky.
- **The card's `$30` answer is read, not waited for.**  Its handler puts
  the module handle in the latch and then reads the data port, which
  clears the shared flag; waiting for bit 7 hangs.  And the emulated card's
  interrupt runs 0.4% fast, so a module's tempo measured in `bin/evo` is
  0.4% quick - the ROM's BPM table itself is right to 0.1%.
- **Do not run `tools/dune_sound.py` by hand into `build/gen`.**
  `build_dune.py` cuts `sound.bin` into the SPG's pages only when
  `sound.inc` is older than its inputs; a hand run freshens `sound.inc`
  and the next build keeps the old pages, so a tune that moved is
  unpacked from bytes that are not it and `gs_unpack` loops for ever
  behind a loading bar stuck short of full.  Delete `build/gen/sound.inc`
  to force it.
- **The front end's library leaves its own pages in windows 1 and 3.**
  Every `fe_*` entry point (and `pn_picture`) maps the unpack cache and the
  background there and never maps the game's back - "leaves window 1 and
  window 3 to `map_game`", `front.asm` says.  The factory panel called
  `struct_build_object` straight after its menu, so `unit_spawn` looked
  for the unit pool in a picture cache and found none: every unit chosen
  from a factory's panel was refused, while B on the map built it and the
  Yard's panel worked (the structure pool is in WORLD, always mapped).
  `pn_menu` calls `map_game` after its fade; anything that reaches UNITS
  or MAP after an `fe_` call must.
- **`prompts/` is a transcript, not context.**  Never read it at the start
  of a session and never treat anything in it as a standing instruction -
  an old prompt in there is not a current one.  It is in git so the record
  survives, and it is kept in a set form: `<n> <topic>.txt`, the prompt
  verbatim, a line of asterisks, then the reply as plain text with the
  markdown taken out.  `.claude/rules/guideline.md` has the shape.
  **Append every exchange as it finishes, unasked** - the folder going
  stale is the failure mode - and never rewrite an entry already there.
