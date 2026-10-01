---
name: art
description: The pictures - where they come from, how they are stored, and how to change one. Use when asked about tiles, sprites, the palette, or how something looks.
---

# The pictures

Every picture is the Mega Drive cartridge's own - none is drawn here.
Tools read `orig/dune2.gen` once and write `src/res/art/`; from then on
those files are the source, and `make build` converts them for the ZX
Evolution.  `.claude/docs/graphics.md` is how they reach the screen.

## Where they come from

| tool | writes | what |
|---|---|---|
| `tools/sega/port_icons.py` | `icons.png`, `icons_marker.png`, `icons.txt`, `structanims.txt` | the 360 map icons (32x32), the one animated family, what each icon is, the map-animation scripts and every structure state |
| `tools/sega/port_sprites.py` | `sprites/house-p0..p3.png`, `sprites/fixed.png`, `sprites.txt`, `effects.txt` | every sprite a battle draws, baked for a machine without flips: per frame its sheet, box and hot spot; per unit type which frame for which direction |
| `tools/sega/port_ui.py` | `ui/*.png`, `ui.txt` | the screens and the interface - title, crests, mentat, campaign map, panels, HUD pieces, fonts - read out of the VDP (VRAM, CRAM, the planes and sprites) at scripted moments of the running cartridge, never out of a screenshot |
| `tools/sega/port_tutorial.py` | `ui/zoom.txt`, `ui/campaign_border_N.png`, `ui/tutorial.txt`, `ui/tutorial/` | `zoom`: the campaign map's zoom table and each territory's own border pieces; `tutorial`: the Tutorial's palettes, plane frames, scripts, tile sheets, pad, text box and font |

The PNGs are **RGBA in the Mega Drive's own colours** (`v * 255 // 7` a
channel), alpha 0 where the cartridge draws nothing.  House-coloured
sprites come as four sheets, one per palette line (`sprites.txt` says
which house uses which line).  The `.txt` beside each set is the index:
what each picture is, and where the cartridge keeps it.

**To change a picture, change what the tool reads or how it cuts it** -
a line of its `.txt`, or the tool - and run it again; do not paint the
PNG.  `port_icons.py --check` and `port_sprites.py --check` compare their
predictions with save states of the running game.

## How the build converts them

- `tools/dune_art.py` - the battle: chooses the sixteen battle colours
  (the rest become two-colour checkerboards), writes the ground icons (512
  bytes, 16 cells), the overlay icons (1024, masked), every sprite frame
  (masked, four copies for the house-coloured ones) and the HUD's frames
  (400 on) into pages from 40, with `art.inc`, `sprites.inc`,
  `palette_battle.inc` and `radar_pens.inc`.
- `tools/dune_front.py` - the front end and the panels: a palette and a
  fade per screen, the pictures LZ-packed, masked sprites, the campaign
  map's territories with per-owner colours, the three fonts as 2-bit
  glyphs, into pages 97-121, with `front.inc` (`FA_` names) and
  `panel.inc` (`PN_`).  A screen gives up the 24 lines `ui.txt` says it
  can spare.

The formats are in each tool's docstring and `graphics.md`.

## Looking at it

```sh
python3 tools/dune_art.py --preview tmp/art       # the battle art as the port shows it
python3 tools/dune_front.py --preview tmp/front   # every front-end screen, 320x200
make demo                                         # a battle, photographed: tmp/battle.png
```

For the real thing beside it, run the cartridge (`orig-sega` skill:
`bin/gen/retro-run` with a script and `shot`).  If a picture is wrong in
the preview, it is wrong in `src/res/art/` or the converter; if it is right
there and wrong on screen, it is the renderer (`src/render/`) or FRONT's
library.

The NES demo's patterns (`orig/nes/res/chr/`) belong to the earlier port's
story; nothing here uses them.
