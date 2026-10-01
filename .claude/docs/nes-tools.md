# The reference machines

Two originals sit in `orig/` and neither is edited.  Both are driven by the
same frontend, `tools/retro-headless/retro-run.c` - a small libretro host
that dlopens a core, runs a script, and can dump whatever the core will
show it.

| | |
|---|---|
| `orig/dune2.gen` | *Dune - The Battle for Arrakis*, Virgin/Westwood 1994, 1 MB, the PAL release.  **This is the game** the port reproduces - its rules, data, pictures and sound. |
| `orig/sand_emperor_demo5d9.nes` | *Sand Emperor* demo 5 (TI, 2021): a Dune II for the NES/Dandy with Mega Drive style controls.  iNES mapper 26 (Konami VRC6), 256 KB PRG + 128 KB CHR.  The earlier port was built from it; it is reference material now. |

## Running them

```
bin/nes/retro-run --core bin/nes/fceumm_libretro.so \
                  --rom orig/sand_emperor_demo5d9.nes --script F
bin/gen/retro-run --core bin/gen/genesis_plus_gx_libretro.so \
                  --rom orig/dune2.gen --script F
```

It is the same binary in both places; only the core differs.
`tools/nes/run_nes.py` and `tools/sega/run_sega.py` wrap it (and rebuild
the cartridge from its deconstruction first).  `make sega` converts the
Mega Drive's music and effects into General Sound modules, and `make md`
dumps the Mega Drive's video memory into `tmp/md/`.  The Mega Drive art the
port uses is read out of VDP dumps by `tools/sega/port_ui.py` and out of
the cartridge by `port_icons.py` and `port_sprites.py`.

## The script language

```
run N              run N frames
hold BTNS          hold these buttons (comma separated)
release            release everything
press BTNS N       hold for N frames, then release
shot FILE          a 24-bit BMP of the current frame
wav FILE / wavstop capture audio
ram FILE           the machine's work RAM (byte-swapped words on the Mega Drive)
sram FILE          battery-backed RAM
save FILE / load FILE   the whole machine's state, and back
reset              reset the machine
```

and, on the Mega Drive only (the Genesis core is patched for them):

```
z80 FILE           the sound Z80's 8 KB - the sound driver's whole state
touch FILE         the cartridge access record: a flags byte per ROM byte
reader FILE        who first read each ROM byte
untouch            clear the record
blind PC           stop recording reads made from PC
```

and four video dumps, which are one set of commands over two very different
machines and so have a name from each:

```
vram | nt FILE     Mega Drive: 64 KB of tiles and tilemaps
                   NES: the four nametables, mirroring resolved
cram | pal FILE    Mega Drive: 64 nine-bit colours
                   NES: the 32 bytes of palette RAM
vsram | oam FILE   Mega Drive: vertical scroll RAM
                   NES: the 256-byte sprite table
vdpreg | chr FILE  Mega Drive: the VDP's 32 registers
                   NES: the 8 KB of CHR the mapper has banked in
ppureg FILE        NES: the four PPU registers
```

Button names are the RetroPad's - `a b x y l r select start up down left
right` - plus **`mda` `mdb` `mdc`** for the Mega Drive's own A, B and C,
which Genesis Plus GX does not map to the same-named RetroPad buttons
(MD A is RetroPad Y, MD B is B, MD C is A).  The Dune II front end wants
`start` twice and then `mdc` about fifteen times.

The video dumps only work against the patched cores - `make toolchain`
adds those regions to both, because neither offers them.

## What each one is for

The **Mega Drive** game is the one the port reproduces.  Running it is how
a question about the real Dune II gets settled: `tools/sega/sega_spec_check.py`
tests the specs against it frame by frame, `tools/sega/sega_touch.py`
records what it does with every byte (`make sega-trace`), and
`tools/sega/port_ui.py` reads the port's screens and interface out of its
video memory.  The `orig-sega` skill has the details.

The **NES demo** is reference material.  The earlier port was built from
it - its screens, its patterns, its music - and the tools that did that
went with that port (git history has them).  What remains is its
deconstruction (`orig/nes/`, the `orig-nes` skill) and running it here.
`orig/control_en.txt` is its author's own note on the buttons.
