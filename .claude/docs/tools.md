# The tools

Every recurring job is a standalone CLI, so it can be re-run and read.
Each has a skill under `.claude/skills/`.

## Building

| | |
|---|---|
| `tools/build_dune.py` | the whole pipeline: tables, missions, maps and texts (`dune_data.py`), the battle art (`dune_art.py`), the sound set (`dune_sound.py`), the front end's pictures (`dune_front.py`), assembly, and the SPG.  `--build-dir` keeps a build apart; `--house H/A/O --mission N` starts straight in that battle, `--flags` and `--credits` fill the debug block (`src/world.asm`).  `make build`. |
| `tools/spg.py` | not a command: writes an SPG v1.0 file (header, block table, pages); refuses a page above #DF, the loaders' |
| `tools/dune_trd.py` | called by `build_dune.py`: assembles `src/loader/loader.asm` and writes `build/dune.trd` (a TR-DOS disk: `boot` + the loader) and `build/DUNE.DAT` (the SPG under the name the loader looks for) - what a real machine runs, since its firmware boots disks and not SPGs |
| `tools/sd_image.py` | `OUT.img [--fat32] FILE...` -> an SD card image (MBR, one FAT16 or FAT32 partition, the files in its root), written by the tool itself; `bin/evo/evo-run --sd OUT.img` puts it in the emulated slot for the firmware and the disk loader |
| `tools/fix_jr.py` | reads the assembler's "JR out of range" errors on stdin and turns those JRs into JPs in `src/` |
| `tools/build_toolchain.py` | fetch and compile everything in `bin/`.  `make toolchain`. |
| `tools/verify_build.py` | two debug builds straight into Atreides 1, run headless: EGA at 14 MHz, the mission loaded, a click gives an order and the unit drives off, the counter, the pass rate, a Windtrap built and placed, the sound card playing, and a start with the card answering nothing ("no sound", a key, the battle silent).  `--no-sound` skips the 30-second sound run and the no-card run.  `make verify`. |

## The port

| | |
|---|---|
| `tools/dune_data.py` | `src/res/data/` (the Mega Drive's tables, missions, maps, scripts and texts as text) -> `tables.inc` (split into sections by `build_dune.py`), `scripts.inc`, `missions.inc`, `maps.inc`, `text.inc` |
| `tools/dune_art.py` | `src/res/art/` -> the battle palette, the 360 icons, the overlays and every sprite frame as EGA pages from `PG_ART`, `sprites.inc` (the directory: per frame dx, dy, W, h and page/address; per unit type its frames), `radar_pens.inc`.  The HUD's pictures (credits digits, portraits, the Fremen, bars, the side panel's label, radar static) are frames 400 on; `art.inc` names the ones UI chooses (`HUD_LABEL`, `HUD_FREMEN`, `HUD_BAR_PEN7`, `HUD_BAR_PEN3`) |
| `tools/dune_front.py` | `src/res/art/ui/` and `ui.txt` -> the front end's screens and the structure panels as data pages 100-121, 97, 98 (`DATA_PAGES`), `front.inc` for bank FRONT and `panel.inc` for bank PANEL: a 16-colour palette and a fade per screen (numpy, a second each), packed pictures (a byte LZ, `fe_unlz`), masked sprites, the campaign map's ten territories as pens with per-owner colour tables, the three fonts as 2-bit glyphs, the panels' icons and half-size item pictures, and the `FA_`/`PN_` names (at most 256).  Each screen gives up the 24 lines `ui.txt` says it can spare.  `--preview DIR` writes every full screen as the port will show it |
| `tools/dune_tutorial.py` | called by `dune_front.py`: `src/res/art/ui/tutorial.txt` and `tutorial/` -> the Tutorial as data pages 221-223, 0, 4, 6 (`TUT_PAGES`) and `tutorial.inc` for bank TUTOR (`src/front/tutorial.asm`): the cartridge's tiles as 4-bit pens and its name-table frames, both packed; per picture group 16 EGA colours voted for by every screen the scripts show (rendered as the VDP would), with a MAP per Mega Drive palette the Z80 builds its pen-pair tables from; the pad and the text box; the six scripts as TUTOR's bytecode, sounds mapped to `SFX_` ids |
| `tools/dune_test.py` | call any routine on the running game through the mailbox at WORLD `$8010`: `Machine(build_dir=...)` in test mode, or `Machine(..., battle=N)` to reach into a running battle (a call is served at the start of a pass - give it 4 frames or more).  `python3 tools/dune_test.py state` prints units, structures and houses |
| `tools/dune_view.py` | draw a loaded map the way the renderer should, to compare with a screenshot |
| `tools/tests/test_*.py` | the subsystems' suites: a mission loaded through the mailbox, records poked, routines far-called, and what they leave compared with the specs' models - `test_core.py` (the stub), `test_move.py` (S1 units, S3), `test_combat.py` (S4), `test_struct.py` (S5, S6), `test_house.py` (S7, S9), `test_fx.py` (the units' effect animations: the MCV's deploy, the flash, the Devastator), `test_ui.py` (S10's controls and HUD), `test_render.py` (the renderer against itself: the screen scrolled by copying, copy after copy, byte for byte against the same view drawn whole), `test_missions.py` (all 27 missions started through the debug block and run with the player idle, in parallel: loaded, still running - a mission the idle player loses is reported, not failed - and within the frame budget; `--frames 20000` is the late-game measurement).  Each takes `--build-dir` (default `build/`) and `--only GROUP`, prints ok/total per group, and counts a call that had not finished in its frames as a failure.  `make test` builds and runs them all, and fails if any fails |
| `tools/tests/rig.py` | not a command: what the MOVE and COMBAT suites share - the mission rig, a probe call that dumps the state a call will find, and `PortRam`, which lets `tools/sega/sega_spec_check.py`'s S3/S4 models (written for the 68000's RAM) read the port's pages at the cartridge's addresses |

## The disk

`dune_trd.py` builds the game's disk with `trd_build.py`; these also
serve `gs_modtest.py`, which builds a small TR-DOS disk, and looking at
`.trd` files.

| | |
|---|---|
| `tools/trd_build.py` | a manifest and some files -> a `.trd` |
| `tools/trd_unpack.py` | a `.trd` -> its files and a manifest |
| `tools/trdlib.py` | the catalog and system-sector format, shared by both |
| `tools/basic_tokenize.py`, `basic_detokenize.py`, `basiclib.py` | ZX BASIC `B` files <-> UTF-8 text.  A `LOAD` inside a `REM` after `RANDOMIZE USR 15619` needs real tokens there, which these cannot write; `gs_modtest.py` builds those bytes itself |

## Taking the port's resources out of the cartridge

Run by hand, once; what they write into `src/res/` is the source from then
on (`.claude/rules/guideline.md`).

| | |
|---|---|
| `tools/sega/port_data.py` | `extract`: the cartridge -> `src/res/data/` - the unit, structure, house, landscape and order tables, the 27 missions, the 27 maps, the four EMC scripts and every string, as text.  `check` proves the text and `dune_data.py` against the cartridge and assembles every include |
| `tools/sega/port_icons.py` | the 360 map icons -> `src/res/art/icons.png`, `icons_marker.png`, `icons.txt`, `structanims.txt` (the map-animation scripts and every structure state).  `--check` rebuilds a battlefield from a save state's RAM and compares |
| `tools/sega/port_sprites.py` | every sprite a battle draws -> `src/res/art/sprites/*.png` (four house palette lines and `fixed.png`), `sprites.txt`, `effects.txt`.  `--check` compares its predictions with battle save states |
| `tools/sega/port_ui.py` | the screens and the interface -> `src/res/art/ui/*.png`, `ui.txt`: `bin/gen/retro-run` plays the cartridge to each moment and dumps the VDP, and `port_ui_vdp.py` draws plane A, plane B, the window and the sprites apart |
| `tools/sega/port_ui_vdp.py` | not a command: one moment's VRAM, CRAM, VSRAM and registers drawn layer by layer, RGBA, alpha 0 where the VDP draws pen 0 |
| `tools/sega/port_tutorial.py` | extraction, run by hand like `port_ui.py`: `zoom` writes `src/res/art/ui/zoom.txt` (the campaign map's zoom table `$024B8A`, each territory's origin) and `campaign_border_N.png` (each territory's own border pieces); `tutorial` writes `src/res/art/ui/tutorial.txt` (palettes, every picture's plane frames as text, the scripts, the glyph map) and `tutorial/` (tile sheets, the pad's six shapes, the text box and its font, as pen PNGs) |

## The sound

| | |
|---|---|
| `tools/sega/sega_mod.py` | `src/res/sega_sound.txt` + the cartridge -> `src/res/prebuilt/music/*.mod` and `sfx/*.mod`, General Sound modules made from the song data, the instruments and the samples through `sega_driver.py`, never from a recording.  Each tune renders its own instruments (`SHARE_TOL` -1); `--share N` makes songs that play one instrument within N semitones share a sample.  Writes `report.txt` (what each track kept, merged and lost) and checks every module by reading it back.  `make sega` |
| `tools/sega/sega_driver.py` | not a command: the Mega Drive's Z80 sound driver as Python - which note starts on which chip channel when, at what pitch and attenuation |
| `tools/dune_sound.py` | the sound set for the card and the SPG: the effects as they go to the card, every tune packed (its card image, samples byte-delta coded, through a byte-aligned LZ77 that `gs_unpack` undoes 512 bytes at a time; 0.57; cached in `lzcache/`, and every tune unpacked again and compared), the sample records the ROM's parser would have built, the order tunes go to the card at start-up while they fit (`BOOT_ORDER`), what each tune's successors are (`SUCCESSORS`) and what the start-up log's bar counts in (`COST_FX_US`, `COST_CHUNK`); `sound.bin` (RAM pages from 128, the unpacker's buffer after it), `sound_ids.inc` (`MUS_`/`SFX_` ids), `sound.inc` (what `src/gs.asm` uploads, streams and plays, the S10 effect/voice/track maps), `sound.txt`.  `--drop` leaves out what no S10 table plays.  `sound.md` has the scheme |
| `tools/font_cyr.py` | the port's Cyrillic (`src/res/art/ui/font_cyr.txt`, for the intro screen's Russian): how `dune_data.py` encodes a letter (an alias to the Latin capital of the same shape, or `$80 + n` for a drawn one) and the glyphs `dune_front.py` puts in `FA_FONT_INTRO`; `--preview F.png TEXT` draws them |
| `tools/modlib.py` | ProTracker "M.K." modules written and read, and `gs_bpm`, the tempo by the General Sound ROM's own table.  `python3 tools/modlib.py FILE.mod` lists one |
| `tools/gs_modtest.py` | play a module through the General Sound ROM's own player in the emulator (`$30`, the bytes, `$D2`, `$31`), record it and say if the card was heard |

## Taking the two originals apart

Under `tools/nes/` and `tools/sega/`; the whole story is in
`.claude/docs/originals.md`.  Both deconstructions rebuild their cartridge
byte for byte and say so on every build.

| | |
|---|---|
| `tools/nes/m6502.py` | a matched 6502 disassembler and assembler, one table for both |
| `tools/sega/m68k.py` | the same for the 68000 |
| `tools/nes/nes_asm.py`, `tools/sega/sega_asm.py` | the two-pass assemblers the rebuilds use |
| `tools/nes/nes_extract.py` | the NES cartridge -> `orig/nes/src` + `res` + `rom.map` |
| `tools/sega/sega_extract.py` | the Mega Drive ROM -> `orig/sega/src`, `rom.map` and `gaps.txt` (what is still nobody's, largest first) |
| `tools/nes/build_nes.py`, `tools/sega/build_sega.py` | back again, SHA-256 checked.  `make orig` |
| `tools/nes/run_nes.py`, `tools/sega/run_sega.py` | rebuild and play.  `make run nes`, `make run sega` |
| `tools/nes/nes_chr.py` | what is on each of the 32 pattern sheets |
| `tools/nes/nes_text.py` | the demo's strings and the font it draws them with |
| `tools/sega/sega_text.py` | the Mega Drive's strings, and its Westwood asset table |
| `tools/sega/sega_art.py` | the tiles and palettes the ROM keeps uncompressed |
| `tools/sega/sega_music.py` | where the Z80 driver is loaded from, and where the samples are |
| `tools/sega/sega_files.py` | the 37 data files Westwood left in the cartridge, taken back out |
| `tools/sega/sega_data.py` | the building, unit and house tables -> readable text, and the 29 passwords |
| `tools/sega/sega_names.py` | the routines' names: `orig/sega/res/names/*.txt`, a block a routine - name, and what it does, its parameters (`in`), where the result is (`out`) and what else a call changes (`affects`).  `check` validates the files without touching the listing; the extractor puts the names and the four fields into the sources |
| `tools/sega/sega_maps.py` | the 27 battlefields, kept whole in the cartridge and picked by a mission's `Seed` |
| `tools/sega/sega_touch.py` | what the running game does with each byte - executed, read, sent to VRAM/CRAM by DMA, read by the Z80 - recorded by the patched core while scripted scenarios and a coverage-guided random player drive it; writes `orig/sega/res/trace.txt`, which the extractor treats as ground truth.  `make sega-trace` |
| `tools/sega/sega_scen.py` | the 27 missions: who plays, what wins, what each side starts with |
| `tools/sega/emc_disasm.py` | the four `.EMC` script files - Dune II's behaviour - as readable listings, one entry point per building and per unit |
| `tools/sega/sega_gfx.py` | Westwood Format80, undone: every building and unit in its own colours, and 9858 tiles more |
| `tools/sega/sega_z80.py` | the Z80 sound driver, disassembled |
| `tools/sega/sega_briefs.py` | the mentat's 111 briefings, victories, defeats and tips |
| `tools/sega/sega_seq.py` | the sound driver's command protocol, its four resource formats and its sequence format: 97 songs in 143 tracks, event by event, named from the game's own table.  `--wav` writes the 30 samples out at their real rates |
| `tools/sega/sega_spec_check.py` | the specs under `orig/sega/spec/`, tested: each scenario loads a save state (built from a `sega_touch.py` scenario), runs the cartridge frame by frame with a RAM dump each frame, and compares what the spec predicts - timers, positions, credits - with what the machine did |
| | (`emc_disasm.py` also writes `functions.txt`: the 104 script-callable routines, with size, call counts and what each touches) |

## Running things

| | |
|---|---|
| `tools/evo_control.py` | drive the ZX Evolution emulator: run a script with the SPG loaded (`script FILE --spg F`), open the window (`play --spg F`), boot a disk through the firmware, regenerate the saved settings |
| `tools/evo-emu/` | the emulator itself (C) |
| `tools/retro-headless/retro-run.c` | the headless libretro frontend both reference machines are driven with (C).  Its script dumps work RAM, video memory, the palette and - on the Mega Drive - the Z80's 8 KB (`z80 FILE`), which is where the sound driver's whole state lives |
| `tools/retro-headless/retro-run.c` (Mega Drive only) | `touch FILE`, `reader FILE`, `untouch` and `blind PC`: the cartridge access record the Genesis core keeps (`patch_gpgx_touch` in `tools/build_toolchain.py`) - a flags byte and a first-reader address for every ROM byte |
| `tools/retro-headless/retro-play.c` | the same in an SDL2 window, with sound and a keyboard - what `make run nes` and `make run sega` open (C) |
| `tools/md_battle.script` | the button presses that get the Mega Drive to its first battlefield |
| `tools/md_dump.py` | `make md`'s dumps of the Mega Drive's video memory (`tmp/md/`) drawn: every pattern under each palette line, the planes, the sprite table, the battlefield with a grid |
| `tools/demo.script` | five seconds of the SPG and a screenshot (`make shot`, `make demo`) |

## Reading code

| | |
|---|---|
| `tools/z80_disasm.py` | raw binary -> sjasmplus-syntax disassembly: the Mega Drive's sound driver (`tools/sega/sega_z80.py`), and the firmware when it would not boot |

### `tools/gs_chantest.py`

A four-channel module that sounds the sound card's DACs one at a time:
channel 1 a low note, channel 2 a fifth up, channel 3 an octave up,
channel 4 higher, then all four, then silence, and round again.  The ROM
puts the module's channels on DACs 0, 2, 3, 1, so the order heard is
left, right, right, left.  `python3 tools/build_dune.py --build-dir
build-chan --intro-mod build/chantest.mod` plays it as the intro's tune
behind PRESS ANY KEY: a note that is not heard is a DAC the card does not
bring out (the ZX-MultiSound played effects one time in four, which is
what four DACs with one alive would do).
