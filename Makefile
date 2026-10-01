BUILD_DIR := build
GAME_SPG  := $(BUILD_DIR)/DUNE.DAT

# `make run HOUSE=A MISSION=3` starts straight in that battle (H A O);
# DBGFLAGS and CREDITS set the rest of the debug block (src/world.asm).
HOUSE     ?=
MISSION   ?= 1
DBGFLAGS  ?= 0
CREDITS   ?= 0
BUILD_ARGS := $(if $(HOUSE),--house $(HOUSE) --mission $(MISSION)) \
              --flags $(DBGFLAGS) --credits $(CREDITS)

.PHONY: build run shot demo verify test md sega toolchain nvram clean
.PHONY: orig-nes orig-sega orig run-nes run-sega sega-trace

# `make run nes` and `make run sega` build one of the two originals out of
# its deconstruction under orig/ and play it.  make takes no arguments, so
# the machine has to be named as a second goal.  RUN_TARGET is which one,
# and RUNNING is set only when `run` was asked for as well - in which case
# `nes` and `sega` are naming a machine rather than asking for a target,
# and further down they become recipes that do nothing so that `run` does
# the work.  (`nes` is only ever a machine's name now.)
RUN_TARGET := $(filter nes sega,$(MAKECMDGOALS))
RUNNING    := $(and $(filter run,$(MAKECMDGOALS)),$(RUN_TARGET))

# src/ -> build/DUNE.DAT, the whole game as one SPG-format file, and
# the data, the art and the sound converted from src/res/, then assembled;
# and build/dune.trd + build/DUNE.DAT, the disk a real machine boots (its
# firmware runs no SPG) with the SPG beside it for the disk's loader.
build:
	python3 tools/build_dune.py --out $(GAME_SPG) $(BUILD_ARGS)

# `make run`       build this port and play it on the ZX Evolution
# `make run nes`   rebuild the NES original from orig/nes/ and play it
# `make run sega`  rebuild the Mega Drive original from orig/sega/ and play it
#
# On the ZX Evolution the keys are the Mega Drive pad: Q A O P, 5-8 or a
# Kempston stick move the cursor, SPACE or M is A (select, order), Z or N is
# B (back), X or SYMBOL SHIFT is C (held: the pad moves the view), ENTER is
# Start (options).
# F12 saves a screenshot, F5 resets, Ctrl+Q quits.
#
# On either original: the arrows are the d-pad, Z X C are the Mega Drive's
# A B C (and Z X the NES's B and A), Enter is start, Tab is select.
run:
ifeq ($(RUN_TARGET),nes)
	python3 tools/nes/run_nes.py
else ifeq ($(RUN_TARGET),sega)
	python3 tools/sega/run_sega.py
else ifneq ($(RUN_TARGET),)
	@echo "make run: say `make run nes` or `make run sega`, not both"; exit 1
else
	$(MAKE) build
	python3 tools/evo_control.py play --spg $(GAME_SPG) --scale 2
endif

# headless proof of life: start the SPG and photograph it after 5 seconds
shot: build
	python3 tools/evo_control.py script tools/demo.script --spg $(GAME_SPG)
	python3 -c "from PIL import Image; Image.open('tmp/battle.bmp').save('tmp/title.png')"
	@echo screenshot: tmp/title.png

# build straight into a battle and photograph it
demo:
	$(MAKE) build HOUSE=A MISSION=1 DBGFLAGS=8
	python3 tools/evo_control.py script tools/demo.script --spg $(GAME_SPG)
	python3 -c "from PIL import Image; Image.open('tmp/battle.bmp').save('tmp/battle.png')"
	@echo screenshot: tmp/battle.png

# the full check: a battle starts from the SPG, the mission is loaded, a
# click gives an order, the loop fits its frames, and the sound card plays
verify: build
	python3 tools/verify_build.py

# every subsystem's suite (tools/tests/test_*.py) on the fresh build, against
# the specs' models; fails if any suite does
test: build
	@fail=0; for t in tools/tests/test_*.py; do \
	    echo "== $$t"; python3 $$t || fail=1; \
	done; exit $$fail

ifeq ($(RUNNING),)

# the ORIGINAL Mega Drive Dune II's music and effects as General Sound
# modules: src/res/sega_sound.txt -> src/res/prebuilt/{music,sfx}/*.mod,
# converted from the song data and the instruments through a model of the
# cartridge's sound driver, not recorded (tools/sega/sega_mod.py)
sega:
	python3 tools/sega/sega_mod.py

else                          # `make run nes` / `make run sega`: see above
nes sega:
	@:
endif

# the Mega Drive's video memory, kept for reference (tmp/md/, read it
# through tools/md_dump.py)
md:
	mkdir -p tmp/md
	bin/gen/retro-run --core bin/gen/genesis_plus_gx_libretro.so \
	    --rom orig/dune2.gen --script tools/md_battle.script
	python3 tools/md_dump.py --dir tmp/md

# ---------------------------------------------------------------- the two
# originals, taken apart into sources under orig/nes/ and orig/sega/ and
# put back together again.  Both rebuilds are checked against the
# original's SHA-256, so the sources ARE the cartridges.

orig: orig-nes orig-sega

# the NES demo: 16 program banks disassembled, 8192 patterns as PNG sheets,
# the strings and the font it draws them with
orig-nes:
	python3 tools/nes/nes_extract.py
	python3 tools/nes/nes_chr.py
	python3 tools/nes/nes_text.py
	python3 tools/nes/build_nes.py

# the Mega Drive game: 1 MB disassembled, Westwood's own data files taken
# back out of it - the stats, the 27 missions, the AI scripts - the strings
# and the asset table, the tiles and palettes it keeps uncompressed, and
# where the Z80 driver and its samples live.
# .claude/docs/sega-internals.md is what all of this says about the game.
orig-sega:
	python3 tools/sega/sega_files.py
	python3 tools/sega/sega_data.py
	python3 tools/sega/sega_scen.py
	python3 tools/sega/sega_maps.py
	python3 tools/sega/emc_disasm.py
	python3 tools/sega/sega_extract.py
	python3 tools/sega/sega_text.py
	python3 tools/sega/sega_briefs.py
	python3 tools/sega/sega_art.py
	python3 tools/sega/sega_gfx.py --scan
	python3 tools/sega/sega_z80.py
	python3 tools/sega/sega_music.py
	python3 tools/sega/sega_seq.py
	python3 tools/sega/sega_instr.py
	python3 tools/sega/sega_sprites.py
	python3 tools/sega/sega_pictures.py
	python3 tools/sega/build_sega.py

# what the running Mega Drive game does with each byte of its cartridge:
# every scenario played by the front door (the passwords, the music and
# sound tests, a win, the ending), then a coverage-guided random player
# from where they end, written to orig/sega/res/trace.txt - which
# `make orig-sega` reads and does not regenerate.  Minutes, not seconds.
sega-trace:
	python3 tools/sega/sega_touch.py seed
	python3 tools/sega/sega_touch.py fuzz --rounds 100
	python3 tools/sega/sega_touch.py export

# rebuild the assembler, the ZX Evolution emulator and both reference
# machines into bin/ (compiles under tmp/, needs cc and make)
toolchain:
	python3 tools/build_toolchain.py

# regenerate the machine's battery-backed settings (see evo-emulate)
nvram:
	python3 tools/evo_control.py nvram

clean:
	rm -rf $(BUILD_DIR)

