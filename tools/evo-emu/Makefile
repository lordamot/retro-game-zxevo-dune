# Build the two ZX Evolution frontends.
#
# Everything compiles into $(OUT) (tools/build_toolchain.py points that at
# tmp/) and only the finished binaries are copied to bin/.
#
#   LXDIR   where samstyle/Xpeccy was cloned (its src/ holds libxpeccy)
#   SDLINC  SDL2 headers  (tmp/sdl2/include2, so <SDL2/SDL.h> resolves)
#   SDLLIB  directory holding libSDL2-2.0.so.0
#
# evo-run needs nothing but libc; evo-play links SDL2 through an $ORIGIN
# rpath so no system-wide SDL install is required.

OUT     ?= .
LXDIR   ?= ../../tmp/xpeccy/src
SDLINC  ?= ../../tmp/sdl2/include2
SDLLIB  ?= ../../tmp/sdl2/lib

CC      ?= cc
CFLAGS  ?= -O2 -std=gnu99 -Wall -Wextra -Wno-unused-parameter \
           -DWORDS_LITTLE_ENDIAN -I. -I$(LXDIR)
LDLIBS  ?= -lm

# tools/build_toolchain.py renames libxpeccy's "cpu/NEC V30" directory to
# "cpu/NEC_V30" after cloning: make cannot express a target whose path has a
# space in it, and every object here is a make target.
LXSRC   := $(shell find $(LXDIR)/libxpeccy -name '*.c' 2>/dev/null)
LXOBJ   := $(patsubst $(LXDIR)/%.c,$(OUT)/lx/%.o,$(LXSRC))

all: $(OUT)/evo-run $(OUT)/evo-play

# libxpeccy is third-party: compile it quietly, its warnings are not ours
$(OUT)/lx/%.o: $(LXDIR)/%.c
	@mkdir -p $(dir $@)
	$(CC) -O2 -std=gnu99 -w -DWORDS_LITTLE_ENDIAN -I$(LXDIR) -I$(LXDIR)/libxpeccy -c -o $@ $<

$(OUT)/libxpeccy.a: $(LXOBJ)
	ar rcs $@ $^

$(OUT)/evo.o: evo.c evo.h
	$(CC) $(CFLAGS) -c -o $@ $<

$(OUT)/evo-run.o: evo-run.c evo.h
	$(CC) $(CFLAGS) -c -o $@ $<

$(OUT)/evo-play.o: evo-play.c evo.h
	$(CC) $(CFLAGS) -I$(SDLINC) -c -o $@ $<

$(OUT)/evo-run: $(OUT)/evo.o $(OUT)/evo-run.o $(OUT)/libxpeccy.a
	$(CC) -o $@ $^ $(LDLIBS)

$(OUT)/evo-play: $(OUT)/evo.o $(OUT)/evo-play.o $(OUT)/libxpeccy.a
	$(CC) -o $@ $^ -L$(SDLLIB) -lSDL2 -Wl,-rpath,'$$ORIGIN/lib' $(LDLIBS)

clean:
	rm -rf $(OUT)/lx $(OUT)/*.o $(OUT)/libxpeccy.a $(OUT)/evo-run $(OUT)/evo-play

.PHONY: all clean
