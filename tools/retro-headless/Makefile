# Builds the two libretro frontends this project drives the reference
# machines with: the FCEUmm core for the original NES demo, and Genesis
# Plus GX for the Mega Drive Dune II.
#
#   retro-run    headless and scriptable - captures, dumps, verification
#   retro-play   an SDL2 window with sound and a keyboard - `make run nes`
#                and `make run sega`
#
# libretro.h is vendored here so the frontends build without the core
# clones present; RETROINC still overrides it when the clones are around
# and their header has moved on.  SDL2 is linked through an $ORIGIN rpath,
# exactly as bin/evo/evo-play does, so no system-wide SDL is needed.
RETROINC ?= .
SDLINC   ?= ../../tmp/sdl2/include2
SDLLIB   ?= ../../tmp/sdl2/lib
CC       ?= cc
CFLAGS   ?= -O2 -g -Wall -I$(RETROINC)
.DEFAULT_GOAL := all
all: retro-run retro-play

retro-run: retro-run.c libretro.h
	$(CC) $(CFLAGS) -o $@ retro-run.c -ldl

retro-play: retro-play.c libretro.h
	$(CC) $(CFLAGS) -I$(SDLINC) -o $@ retro-play.c -ldl \
	    -L$(SDLLIB) -lSDL2 -Wl,-rpath,'$$ORIGIN/lib' -lm

clean:
	rm -f retro-run retro-play
