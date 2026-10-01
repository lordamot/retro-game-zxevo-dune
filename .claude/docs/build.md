# The SPG, and how it is built

## What comes out

`build/DUNE.DAT`: one SPG-format file, the ZX Evolution's paged executable -
about 3.2 MB in some 210 blocks, each a RAM page's worth.  A loader puts
every block in its page and jumps to the boot code in page 2 at `$8000`;
from then on the game never touches a disk.  `tools/spg.py` has the
format, `.claude/docs/port.md` what each page holds, and `src/pages.inc` is
the authority on the page numbers.  The emulator loads the SPG itself.

A real BaseConf machine cannot: its firmware runs TRD, SCL, FDI and TAP
files only (SPG is a TS-Conf format).  So beside the SPG come
**`build/dune.trd`** and **`build/DUNE.DAT`** (`tools/dune_trd.py`): a
TR-DOS disk the firmware mounts and boots, whose `boot` loads `dune` at
`$6000` - `src/loader/loader.asm`, which initialises the SD card over the
SPI port, walks the card's FAT16 or FAT32 root directory to DUNE.DAT (the
SPG under that name), streams its blocks into their pages and starts the
boot stub as an SPG loader would.  Both files go in the card's root.
`make verify` boots the disk from FAT16 and FAT32 card images
(`tools/sd_image.py`).

The loader prints with the game's own font (`font8.png`, cut by
`dune_trd.py`): under the firmware's TR-DOS the page at `$0000` is not the
BASIC ROM, and reading the ROM font there gave noise on a real machine.

The loader's screen shows `ERROR nn` and stops if something is wrong
(`src/loader/loader.asm`): 01 no card answers, 02-05 the card's
initialisation failed at CMD8 / ACMD41 / CMD58 / CMD16, 0A no `$55AA`
or no partition in sector 0, 0B not 512 bytes a sector, 14 no DUNE.DAT
in the root directory, 1E a sector never came, 1F the file's cluster
chain ended early (the file is shorter than its block table), 28 no
"SpectrumProg" signature, 29 not SPG v1.0, 2A a packed block, 2B a
block for page 5, the loader's own.

| pages | what |
|---|---|
| 2 | the boot code (`src/boot/boot.asm`) |
| 1, 5 / 3, 7 | the two screens (not in the file: the game clears them) |
| 8-23, 122 | code banks: MAIN, RENDER, VM, OBJ, MOVE, COMBAT, STRUCT, HOUSE, UI, FRONT, SCEN, TUTOR (19) and the second banks; PANEL |
| 24-38 | UNITS, WORLD, MAP, the loaded map's ground, the 27 missions, the 27 maps, the texts |
| 40-99 | the battle's art: map icons, overlays, sprite frames, the HUD, the radar |
| 97, 98, 100-121 | the front end's pictures, fonts and fades (123 is listed as its spare and empty) |
| 124-127 | the front end's unpack cache and background |
| 128-220 | the sound set - the effects, the tunes packed, the unpacker's buffer - for the General Sound card (`dune_tutorial.py` refuses to build if it reaches the Tutorial's pages) |
| 221-223, 0, 4, 6 | the Tutorial's tiles, frames and scripts (`tools/dune_tutorial.py`).  Nothing goes above #DF: the SPG format reserves #E0-#FF for the loaders, and `spg.py` refuses such a page |

## The pipeline

`make build` runs `tools/build_dune.py`:

```
orig/dune2.gen --(tools/sega/port_data.py, once)--> src/res/data/*.txt
               --(port_icons.py, port_sprites.py,--> src/res/art/*.png, *.txt
                  port_ui.py, port_tutorial.py,      src/res/art/ui/*.png, ui.txt,
                  once)                              zoom.txt, tutorial.txt, tutorial/
               --(make sega: sega_mod.py)---------> src/res/prebuilt/{music,sfx}/*.mod

src/res/data/        --(dune_data.py)--> build/gen/tables.inc (split into
                                         sections), scripts.inc,
                                         missions.inc, maps.inc, text.inc
src/res/art/         --(dune_art.py)---> build/gen/page_NNN.bin from 40,
                                         art.inc, sprites.inc,
                                         palette_battle.inc, radar_pens.inc
src/res/art/ui/      --(dune_front.py)-> build/gen/front.inc, panel.inc and
                                         the front end's data pages; through
                                         dune_tutorial.py, tutorial.inc and
                                         its pages (TUT_PAGES)
src/res/prebuilt/    --(dune_sound.py)-> build/gen/sound.bin (pages from
                                         128), sound_ids.inc, sound.inc
src/dune.asm + all   --(sjasmplus)-----> build/pages/pNNN.bin, dune.sym,
                                         dune.lst, dune.sld
                     --(build_dune.py)-> bank_of.txt, the checks, the debug
                                         block, build/DUNE.DAT
src/loader/loader.asm --(dune_trd.py)--> build/dune.trd (boot + the
                                         loader), build/DUNE.DAT (the SPG)
```

The extraction steps at the top are run by hand, once: from then on the
text and pictures in `src/res/` are the source (`.claude/rules/guideline.md`),
and `port_data.py check` proves the text still says what the cartridge
says.  `dune_data.py` runs on every build; the other three converters only
when one of their inputs is newer than their output (for `dune_front.py`:
itself, `dune_art.py`, which it imports, `src/res/art/ui/` and `ui.txt`;
for `dune_sound.py`: itself, `src/res/prebuilt/` and `sega_sound.txt`).

After assembling, `build_dune.py`:

- **checks that every code bank starts with the same stub**, byte for byte.
  `FCALL` switches window 0 from inside the stub and carries on at the
  next instruction, which is only safe if that instruction is the same in
  every bank;
- writes `build/bank_of.txt` (every label and the page it is in, from the
  SLD file) for `tools/dune_test.py`;
- fills in the **debug block** at the start of WORLD (`src/world.asm`):
  `dbg_house`/`dbg_mission` start straight in a battle, `dbg_flags` bit 0
  reveals the map, 1 the player takes no damage, 2 fast production, 3 no
  sound, 4 stop after the first frame of the battle, 7 test mode (the
  mailbox); `dbg_credits` the player's credits at start.

A "JR out of range" from the assembler is common when a routine grows:
`python3 tools/build_dune.py 2>&1 | python3 tools/fix_jr.py` turns those
JRs into JPs.

`build/dune.sym` names every routine and variable - the fastest way from
an address the emulator or the profiler printed to what is running there.
`tools/verify_build.py` and `tools/dune_test.py` read it.

## Debug builds

```sh
make run HOUSE=A MISSION=3            # straight into Atreides 3
make build HOUSE=O DBGFLAGS=5         # Ordos 1, map revealed, fast production
make build CREDITS=5000               # the player starts with 5000
python3 tools/build_dune.py --build-dir build-x --house H --mission 2
```

`--build-dir` keeps a build, its symbols and its generated files apart
from `build/`; everything that reads a build takes the same option.

## The make targets

| | |
|---|---|
| `make build` | the SPG |
| `make run` | build and play it in an SDL2 window with sound (`HOUSE=`, `MISSION=`, `DBGFLAGS=`, `CREDITS=`) |
| `make verify` | the smoke test - see below |
| `make shot` | start the SPG headless and photograph it five seconds in (`tmp/title.png`) |
| `make demo` | build straight into Atreides 1 and photograph it (`tmp/battle.png`) |
| `make sega` | the Mega Drive's music and effects as General Sound modules into `src/res/prebuilt/` |
| `make md` | re-capture the Mega Drive's video memory (`tmp/md/`), for reference |
| `make orig`, `orig-nes`, `orig-sega` | take the originals apart again and rebuild them, SHA-256 checked |
| `make sega-trace` | record what the running Mega Drive game does with every cartridge byte |
| `make run nes`, `make run sega` | rebuild an original from its deconstruction and play it |
| `make nvram` | regenerate the machine's battery-backed settings |
| `make toolchain` | rebuild everything in `bin/` from source |
| `make clean` | remove `build/` |

The earlier, NES-based port's targets (`make nes`, `rom`, `play`,
`compare`, `sheet`) went with it.  `make nes` on its own now says there is
no such target; `make run nes` is unaffected.

## make verify

`tools/verify_build.py` builds two debug variants - straight into the
Atreides' first mission, one with the sound card left alone and one with
the sound set uploaded - runs them headless in `bin/evo/evo-run`, and reads
the machine's own memory rather than trusting a screenshot:

- EGA mode at 14 MHz - the first thing to break if the configuration ports
  get shut;
- the mission loaded: the player's Construction Yard, units and credits,
  and one of the player's vehicles on the screen;
- **the loop keeps up**: passes per 500 frames, against a budget of three
  frames a pass (about 1.0 now; 1.33 at worst in any mission's heavy
  stretch, `test_missions.py --frames 20000`);
- A on a vehicle selects it, A on a square gives it Move to that square,
  and it drives off;
- the credits counter rolls up to the house's credits;
- the build panel starts a Windtrap, the Yard finishes it, and A puts it
  down on a free square;
- from power-on, A on every screen of the front end reaches the battle, and
  a lost mission goes through the defeat and score screens and starts
  again;
- the card is found and loaded, and the battle music plays;
- a NeoGS (`gsneo`: status bits 1-6 not 1s, a stale byte in the latch)
  is found and loaded too;
- with the card answering nothing (`gsdead`), the log stops at "no
  sound", a key takes it on, the intro passes silent and the battle runs
  with the card given up.

The frame-budget check is a real regression test: a single misplaced
`pop bc` before an `ld bc,4` once turned a sixteen-iteration loop into a
256-iteration one, and the only symptom was a game running at a fifth of
its speed.  It leaves `tmp/verify-battle.png` to look at.
