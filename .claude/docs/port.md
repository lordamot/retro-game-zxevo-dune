# The port: Mega Drive Dune II on the ZX Evolution

The game is rebuilt from the Mega Drive cartridge's own rules and data
(`orig/sega/spec/S1-S10`, `orig/sega/res/`), in Z80 assembly, for a ZX
Evolution BaseConf at 14 MHz with a General Sound card (2 MB).  It is built
as **`build/DUNE.DAT`**, a single SPG-format file of up to 4 MB that loads every
byte the game needs straight into RAM pages, and shipped as
**`build/dune.trd` + `build/DUNE.DAT`**, because the BaseConf firmware
runs no SPG: the disk's loader reads the SPG (DUNE.DAT) off the SD card
(`build.md`).  There is no disk access after the start.

`orig/` is never written.  Tools read it and write sources and resources
into `src/` (PNG pictures, text data); `make build` turns `src/` into the
SPG.

## The machine, as the game sets it up

- CPU 14 MHz, ATM **EGA 320x200, 16 of 64 colours** (`platform.md`,
  `graphics.md` for the plane layout).
- All four windows are RAM.  The memory manager is programmed with the
  short `xx7F7` port (8-bit page, inverted) after the long `xxFF7` form has
  cleared each window's "mix with `$7FFD`" flag once.  `$7FFD` keeps bit 4
  set, as the firmware leaves it; only bit 3 (the screen) ever changes.
- IM 1, with our own handler at `$0038` in RAM.

### Windows during a battle

| window | holds | notes |
|---|---|---|
| W0 `$0000` | a **code bank**: `MAIN`, `VM`, `GAME1`..., `RENDER`, `UI`, `FRONT`, `TUTOR` | switched by `FCALL` |
| W1 `$4000` | `UNITS`: the 102 unit records, the 6 houses, the 16 teams | art pages while drawing, pictures in the front end |
| W2 `$8000` | `WORLD`: the 73 structures, the constant tables, the globals, the stack, the view and sprite lists | **never switched** once the game runs |
| W3 `$C000` | `MAP` during logic | the screen while drawing |

Every code bank begins with the same **stub** (`src/stub/`): the interrupt
handler at `$0038`, the far-call trampoline, page switching, maths and
random numbers.  Because the stub is byte-for-byte the same in every bank,
the trampoline can switch window 0 under its own feet and carry on.  The
build checks the stubs are identical.

`FCALL label` is `call far_call` followed by the label's page (`$$label`)
and address.  It maps the bank, calls, and maps the caller's bank back;
registers pass through both ways (flags are not preserved on the way in).
A bank may keep private data after its code (the renderer's dirty maps).

So in the middle of the game logic everything is in reach at once: the
code, the units, the structures and tables, and the map.  Rendering needs
the units and the map only through lists the logic leaves in `WORLD`.

### Record layouts

Units, structures, houses and teams keep **the Mega Drive's offsets**
(`S2-objects.md`), so a spec's `+$4E` is the port's `+$4E` and the port's
RAM can be compared with the cartridge's field by field.  Two differences:
words are little-endian, and addresses shrink - a script's `pc` is a 16-bit
offset into its bytecode, a position is still y word then x word.

## Pages

| pages | contents |
|---|---|
| 1, 5 / 3, 7 | the two EGA screens (planes 0,2 / 1,3) |
| 8-15 | code banks (window 0) |
| 16-31 | game state: `UNITS`, `WORLD`, `MAP`; missions, maps, texts |
| 32-127 | art: map icons, sprites (pre-shifted at start-up), pictures |
| 128-220 | sound: the effects and the tunes packed, for the General Sound card (`sound.md`) |
| 221-223, 0, 4, 6 | the Tutorial's tiles, frames and scripts (`tools/dune_tutorial.py`) |
| 224-255 | nobody's: the SPG format keeps #E0-#FF for the loaders (`spg.py` refuses a block there) |

`src/pages.inc` is the authority; `tools/build_dune.py` checks nothing
overlaps.

## Drawing

Squares are 32x32 as on the Mega Drive, so the view is 10 x 6.25 squares.
The screen is kept as 40 x 25 cells of 8x8, each with a dirty bit per
screen buffer.  Both screens are used: the game draws into the one not
shown and flips on the frame interrupt.

- **Icons** (ground and overlay) are stored whole, 512 bytes each in cell
  order (16 cells of 32 bytes: plane 0, plane 2, plane 1, plane 3, 8 bytes
  each).  An overlay icon also carries a mask (1024 bytes).
- **Sprites** are masked frames, stored once per Mega Drive palette line
  for the house-coloured ones (four copies, built by `dune_art.py`) and
  once for the rest.  A frame is shifted to any even x by rotating which
  source plane feeds which screen plane, so there are no pre-shifted
  copies.  `graphics.md` has the renderer.
- The view scrolls in 8-pixel steps.  A scroll marks every cell dirty.

## Art resources (what the extraction tools produce)

Pictures in `src/res/art/` are PNG, **RGBA**, in the Mega Drive's own
colours (`v * 255 // 7` per 3-bit channel), fully transparent where the
cartridge draws nothing.  Beside each set, a text index says what every
picture is.  The build (`tools/dune_art.py`) chooses the 16 EGA colours
and converts.

## Debugging handles

- `build/dune.sym` names every routine and variable.
- `tools/dune_state.py` reads a running game's pages out of `bin/evo/evo-run`
  and prints the units, structures and houses as the specs name them.
- A debug block at the start of `WORLD` (`dbg_*` in `src/world.asm`)
  says which house and mission to start, whether to skip the front end,
  and cheats (reveal the map, no damage, fast build, money).
  `make run HOUSE=A MISSION=3` and `evo-run`'s `poke` set it.
