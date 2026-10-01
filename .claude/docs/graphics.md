# How the picture is made

The ZX Evolution's ATM EGA mode gives 320x200 pixels in sixteen colours out
of 64, with no attribute clash: any pixel may be any colour.  What it does
not give is a convenient memory layout or any hardware to move pictures,
and everything below follows from working with the one it has.  The
pictures themselves are the Mega Drive cartridge's own (`.claude/skills/art`).

## Four planes in two pages

Every group of eight pixels across the screen is spread over four planes,
and each plane byte holds **two** pixels:

```
pixel     0 1   2 3   4 5   6 7
plane     0     1     2     3
```

| | |
|---|---|
| plane 0 | RAM page A, offset $0000 |
| plane 1 | RAM page B, offset $0000 |
| plane 2 | RAM page A, offset $2000 |
| plane 3 | RAM page B, offset $2000 |

A plane is 40 bytes a line, 200 lines, 8000 bytes.  Within a byte, bits
0-2 and bit 6 are the **left** pixel's colour and bits 3-5 and bit 7 the
**right** one's - the ZX attribute byte's ink/paper/bright wiring reused.

**A plane byte is two pixels, not a colour.**  `vid_fill_page` writes the
byte it is given into both planes of the mapped page, which is right for
black and gives vertical stripes for anything else - filling with colour 7
writes `00000111`, one gold pixel and one black one, over and over.
`vid_colour_byte` makes the byte from a colour: it doubles the low three
bits into bits 3-5 and lights bits 6 and 7 if the colour has its top bit.

## Two screens

Page A is 1 and page B is 5 for the first screen, 3 and 7 for the second;
bit 3 of port `$7FFD` picks which the video reads.  The game always draws
on the screen that is not showing (`draw_a`/`draw_b` in the stub) and
asks the frame interrupt to swap them (`flip_req`), so nothing is ever seen
half drawn.  `vid_flip` asks and waits for the swap.  The battle's
`render_frame` asks and does not wait: it aims `draw_a`/`draw_b` at the
screen showing (the one the swap will hide) and returns, and the next
pass's logic runs while the swap is pending; the next `render_frame` waits
for it before it draws.  Whatever draws on the screens after a battle
pass (the options, a structure's panel, the result) begins with the
palette black and a background filled, well over a frame, so the swap is
long done by then.  `$7FFD` cannot be read back; `port_7ffd` shadows it,
and nothing but bit 3 ever changes (bit 4 picks the live set of window
registers - see `platform.md`).

## Two passes

Only window 3 is free for the screen, so only one of a screen's two pages
is mapped at a time, and both hold their planes at the same two addresses,
`$C000` and `$E000`.  So everything is drawn twice:

```
map page A -> draw, from the plane 0 and plane 2 bytes of each picture
map page B -> draw again, from the plane 1 and plane 3 bytes
```

Every drawing routine writes to the same addresses on both passes; only
where its source bytes are changes.  That is why every picture format
below stores the bytes pass A wants before the bytes pass B wants.

## The colours

The Mega Drive's battlefield uses 31 colours, three bits a channel; the
ZX Evolution has 64, two bits a channel, and shows sixteen.  A plain
nearest-colour mapping puts the main sand and rock shades on the same
colour, so `tools/dune_art.py` draws every Mega Drive colour either as one
of the sixteen or as a fixed checkerboard of two of them (a pixel's parity
is `(x + y) & 1`), and chooses the sixteen that make the sum of those
approximations, weighted by how many pixels use each colour, as small as it
can.  Some are pinned: black (colour 0 - the fog and beyond the map), white,
and the house hues the terrain has none of.

The front end has a palette per screen, chosen from that screen's own
pictures by `tools/dune_front.py`, with a fade from black
(`FA_PAL_*`, `fe_fade_in`/`fe_fade_out` in FRONT).  `vid_palette` writes
sixteen bytes; `.claude/docs/platform.md` has the port's quirks.

## The battlefield

`src/render/render.asm` (bank RENDER).  The Mega Drive's squares are 32x32
pixels, and so are the port's: the screen is 40 x 25 cells of 8x8, a
square is 4 x 4 cells, and the view is 10 x 6.25 squares - the view grid
is 11 x 8 (`GRID_W`, `GRID_H`) so a view that is not on a square boundary
is still covered.  The view moves in 8-pixel steps (`view_x`, `view_y` are
multiples of 8): there is no scroll register, and a cell is the smallest
thing that can be copied without shifting.

`render_frame` runs once a battle pass, with the game's windows in place:

0. wait until the screen drawn last time is showing (its swap was asked
   for, not waited for - "Two screens");
1. read the view's squares out of the map and compare them with **the
   screen about to be drawn**: every cell is dirty if the view has moved
   since that screen was drawn; so are the cells of every square whose
   icons differ from what that screen shows;
2. list the sprites the logic has on screen coordinates, sorted;
3. mark dirty the cells under the sprites that screen showed and that are
   gone or have moved, and under the new or moved ones; then every sprite
   with a dirty cell under it is drawn too, and its cells marked, until
   nothing changes;
4. pass A: the dirty cells, then the sprites; pass B the same, leaving the
   cells clean;
5. the new sprite list becomes that screen's, and the swap is asked for.

Each screen keeps its own of everything, because the two screens are a
pass apart: what the screen being drawn needs is what changed since *it*
was last drawn, two passes ago.  Per view square (`rf_rec0/1`, 8 bytes)
the map's two bytes it shows there and where their pictures are - the
ground icon's page and address, the overlay's or none, or the full fog -
worked out when the square's bytes change; per square a 16-bit dirty mask
(`rf_msk0/1`, bit k = the square's cell k); its sprite list; and the view
it was drawn at.

**When the view has moved** since a screen was drawn, the other screen -
the one showing, drawn a pass ago - is usually a cell or two from the new
view, so `rf_scroll` copies its picture over this one moved by the
difference.  A plane is 40 bytes a line, so a move of whole cells is one
block copy a plane (`rf_blit`, sixteen LDIs a turn): the screen showing
goes in window 1, the one drawn in window 3, pages A then B.  The screen
drawn then takes over what the other knows: its records, moved by whole
squares (a square new to the grid gets none, and is drawn), and its
sprite list, each entry moved by the view's move the other way and its
cells worked out again.  Its masks start clean but for what the copy left
out - the columns on the side the view moved towards, where the rows'
ends wrap round, and the rows at the top or the bottom - and the frame
goes on as if the view had not moved: the squares that changed since,
the sprites that moved.  Everything drawn in screen coordinates (the
cursor, the HUD) has moved as far as the copy is concerned, and is
restored and drawn again.  The copy is about 0.57M T-states a pass,
against about 1.75M for drawing all 1000 cells; a byte copied costs 17
T-states and one drawn 37, so any overlap pays, and only a move of more
than 32 cells across or 20 down (`RSC_MAX_DX`, `RSC_MAX_DY`), or a
screen drawn over since (`render_invalidate`), draws every cell.
`tools/tests/test_render.py` scrolls through chains of moves, copy after
copy, and checks the result against the other screen drawn whole at the
same view, byte for byte.

A square with dirty cells is drawn row by row of its cells, the ground's
cells then the overlay's over them; a square all dirty and wholly on the
screen goes the quick way, sixteen cells straight.

A square shows a **ground icon** and, over it, an **overlay icon**
(craters, the structures' house markers, the fog's edges and the like -
`src/res/art/icons.txt` says what each is).  The formats (`tools/dune_art.py`):

    ground icon n    page PG_ICONS + n/32, address $4000 + (n%32)*512:
                     16 cells of 32 bytes, row by row; a cell is plane 0's
                     eight rows, plane 2's (pass A), plane 1's, plane 3's
    overlay icon n   page PG_OVERLAYS + n/16, address $4000 + (n%16)*1024:
                     16 cells of 64 bytes, each pass 32 bytes of (mask,
                     data) pairs - screen = screen AND mask OR data
    OVL_FOG ($7B)    the full fog: drawn as a black cell, no ground under it
    the orb          the house markers, overlays 22-26, turn: marker
                     22 + h, frame f is overlay ORB_SLOT ($20) + h * 8 + f,
                     from icons_marker.png, in slots no overlay uses

**The house marker's orb turns**, as on the Mega Drive, where the frame
hook sends the next of eight frames (`$00690C`) to the marker's tiles
every eighth frame (`$00608E`, `$006D10`), the same frame for every
structure.  After reading the squares, `rg_orbs` points every record
showing a marker at the frame of now (`frame_count / 8 & 7`), and marks
the four cells of the orb (8, 9, 12, 13: the bottom-left quarter) dirty
where that changed - four cells a structure redrawn every eight frames.
The 88 records are looked at only in a pass where the frame moved on, the
view moved, or a record was made again (`rg_touched`, set by `rg_new`):
otherwise every marker already points at the frame of now.  The frame
each screen shows is kept per screen (`rgo_f0/1`): with one for both, the
second screen was left a step behind for good and the orbs jumped between
two phases.

Art pages are mapped into window 1 while drawing; `rc_map_art` maps one
only if it is not there already.

## Sprites

There is no sprite hardware, so every unit, explosion and marker is a
masked picture drawn over the cells, and the cells under it are redrawn
when it moves.

`rf_prep_sprites` turns every unit the player can see into entries of
the new list - screen x and y, the frame's page and address, its width and
height - with a sort key `layer << 8 | y` (the layers are `sprites.txt`'s
"draw order"; within a layer, the one lower on the screen goes later).
A unit far from the view is rejected on the high bytes of its position
first (`rps_yhb`, `rps_xhb`): most units are.  A Tank's turret takes the
hull's key (`rpu_lock`), so it goes in after the hull whatever its
frame's dy - sorted by its own y it went under the hull at some
headings.  The bracket and the corners are layer `$1F`, under the panel's
pictures (`$20`): sorted with them by y they flashed over the radar.  The list holds 64
(`RF_MAX_SPR`); the units, markers and effects stop short of the end by
what the HUD took last pass plus two (`rps_hud_n`), so that the cursor,
the credits and the radar - added last - always fit.  Then it
then adds the structure markers (STRUCT's `st_markers`: 'OK' on a
Construction Yard whose building waits while it is not selected and on a
ready Palace, the repair hammer, a Windtrap's low-power bolt - frames
327-329, layer $00, placed by the structure's layout; `struct_animate`
sets and clears them as `$00DC98`-`$00DDA2` does; each flashes as the
cartridge's sprite engine flashes it - a marker sprite is made with a
blink period, 3 for the bolt, 6 for 'OK', 7 for the hammer, and
`spr_render $0010D8` skips it for one frame in period + 1, so the bolt
is off every fourth frame and the other two every eighth, here by the
frame counter), COMBAT's explosions
and smoke (`fx_list`), a working Harvester's dust, the bracket round a
selected unit (332 the player's, 333 another house's or a Saboteur) or
the corners round a selected structure - both blinking eleven frames off,
eleven on, counted only while something is selected - a building's
footprint while it is being placed (frame 338 if it fits, 339 if not) and
the cursor: the crosshair (331) while one of the player's units is
selected or the Palace's weapon is armed, the square (330) otherwise
(`rph_pick`, `ui_battle_button $028596`).  A list is its entries in the order they were
made and a record per entry, (key, where the entry is), kept sorted as
they come: an entry goes in after every one whose key is not above its
own, so equal keys stay in the order made.  Three lists take turns: each
screen's (what it shows) and the one being made, which becomes the drawn
screen's when the frame is done.  A unit is looked at on the screen only
if its position is in the view (with 64 pixels to spare); an enemy's only
if its square is revealed and not under the full fog.  A unit off the
map (`isNotOnMap`) is left out, except while its `U_SHOWN` byte is set:
a Harvester docked in a Refinery, drawn on the pad where
`unit_enter_structure` put it, as the Mega Drive leaves its sprite shown
there (`c_spr_show $048966`) until `unit_take_off_map` or `pick.up` hides
it.  The sprite
directory (`sprites.inc`: `spr_info`, `spr_loc`, the unit tables) is in a
page of its own, `PG_SPRDIR`, mapped into window 3 while the list is made
(the map goes back for a moment to look under the fog).

A **frame** (`sprites.inc`, `spr_loc`) is W bytes by h rows per plane, in
(mask, data) pairs, planes 0-3.  House-coloured frames are stored four
times, once per Mega Drive palette line, all built by `dune_art.py` from
`sprites/house-p0.png`..`house-p3.png`; the rest once, from `fixed.png`.
Vertical placement is exact.  Horizontally, `x & 6` shifts a frame by 2, 4
or 6 pixels without a second copy: screen plane `d` is fed from source
plane `(d - p) & 3`, one column further right when `d < p` (`p = (x & 6) /
2`).  So sprites move in 2-pixel steps, which is the finest a two-pixel
byte allows without shifting bits.

A sprite this screen already shows - same place, same frame - is left
alone unless something under it changed; every other sprite of the old
list has its cells restored, and every new or moved one is drawn.  Then,
until nothing changes, a sprite with a dirty cell under it has all its
cells marked and is drawn too, so whatever overlaps it is redrawn in
order.  Every entry carries the cells it covers, as the squares they are
in and which columns and rows of each (`rf_rect_calc`: `E_SQ` .. `E_RS1`),
worked out once - for a new or moved sprite, or for all of them when the
view has moved; a sprite left alone has its old entry's.  Marking,
restoring and asking whether any is dirty are then a mask operation a
square.  The test is per cell: a sprite is drawn only if a cell it covers
is dirty.  That draws exactly what a full redraw would show - a cell not
dirty keeps its pixels, and nothing drawn or changed covers it - so it
gives the same screen as the looser per-square test it replaced, with
fewer sprites and cells drawn.  When the view has moved, every cell is
dirty and every sprite is simply drawn.

## The HUD

The port draws the battle's HUD as sprite frames, numbered from 400 after
the game's own
(`dune_art.py`): the credits digits (400-409, the counter at 256,16), the
low-credits warning (410), the radar off and its static (411-423), the
side panel's label (424, the red no sign), each unit's and structure's
portrait (430 on, 460 on; at 272,48; each in the palette line its
portrait animation record names, `ui_picture1_show $0098DC` - line 3
for the units but the Sonic Tank's, line 1, which was green in line 3),
the Fremen (458, 459: animations
$5E and $68, which no portrait table names) and the bars (480 on, nine
frames a colour, 0-8 eighths full: green, yellow, red, and pens 7 and 3 of
line 2, blue and orange).  The health bar is at 272,72, red under a
quarter, yellow under three, green above.

The panel's lower half is the cartridge's decision, not the renderer's:
UI's `ui_selection_panel` runs `ui_draw_selection_panel $0294BE` at the
end of every input step and leaves frames in WORLD - `panel_pic2`,
`panel_bar2` at `panel_bar2_y`, `panel_label` - which `rph_panel` draws
after the health bar.  The lower picture (272,88) is what a factory makes,
the spanner while upgrading, the Repair Facility's unit or the Palace's
weapon; the second bar is production, the upgrade, the repair or the
Palace's charge at 272,112 in blue, the Starport's delivery or a
Windtrap's power at 272,80 in blue, a Refinery's or Silo's spice or a
Harvester's load at 272,80 in orange - in eighths of the 32 pixels the
cartridge counts; the label goes over the picture, 4 pixels in.  Where the
cartridge leaves a sprite as it was, the variable is left too.  The label
and the picture share a sort key, so the label is drawn over it because
the sort keeps equal keys in the order they came.

The radar (240,120) is drawn by UI from the map
into its own page (`PG_RADAR`, one picture, a row a frame in place, as
the cartridge's rows go straight to VRAM - so a scan shows as it comes,
top down, after the switch-on animation; it was two pictures swapped
after a whole scan, and the map appeared at once), and shown only with a
working Outpost, with its switch-on and switch-off animations (S10).  It
is opaque, so the cells under it are not painted and its picture is copied
without a mask; `radar_gen` (WORLD) counts the cell rows completed while
the map shows (and a blanking), and each screen copies the picture again
when its own count is behind (`rmf_same`, `rf_rgen0/1`) - whole, with
what sits over it (the marker, the cursor, the warning: layers above
`$20`), and with no cell marked: a marked cell under the radar had every
sprite near it drawn again, and in a full base that spread over the
screen (0.3 frame a pass in Ordos 8 until it was found).  Over it goes the marker - a 5x5 white bracket on the
square under the **cursor**, not the view (`radar_place_marker $005518`) -
then the cursor, then the CREDITS LOW warning (112,112; `ui_warning_blink
$0099A8`), in that order, over everything else.

## Screen shake

The Mega Drive shakes the view a pixel or two a frame for 16 frames after
a big blast and 60 after a structure falls (`view_shake_start $005DCC`,
`view_shake_frame $005E26`: a random walk kept within 4 pixels of where it
began; C held stops it).  Here a view moved costs a copy of the screen
(about 2 frames), so a per-pass shake is out.  Instead the port runs the cartridge's walk (the
same two random numbers a frame, input frozen, C cancelling) and draws
one of the two screen buffers a cell (8 pixels) away for the whole shake
while the other stays put: the buffers alternate each pass, so the view
jumps between the two positions.  That is two copies of the screen per
shake whatever its length; it starts about 15 frames late and ends with a
redraw pass.

## Fog

The fog is part of the map, as on the Mega Drive: an unseen square's
overlay is the full fog, `OVL_FOG`, which the renderer draws as solid
colour 0 without reading the ground; the border of what has been seen is
drawn with the cartridge's own fog-edge overlays, one for each mask of
revealed N, E, S, W neighbours (`map_update_fog_edge`, S8).  `dbg_flags`
bit 0 reveals the whole map.

## The front end

`src/front/front.asm`'s first half is a screen library that FRONT and the
structure panels (bank PANEL) share.  It works on a **background** - pages
126 and 127, laid out like a screen's two pages - that holds what the
screen shows under the sprites:

- a **picture** (`FA_*`, `tools/dune_front.py`) is LZ-packed in the data
  pages from 100 on; `fe_unlz` unpacks it into the cache (pages 124/125)
  and it is copied from there into the background or straight into the
  screen being drawn;
- **text** is drawn into the background in one of three fonts (`font8`,
  `font_menu`, `font_score` in `src/res/art/ui/`), 2 bits a pixel: three
  inks, the third a shadow, each set per string;
- a **territory** of the campaign map is a mask drawn in its owner's
  colours (an `OWN` table per owner);
- **sprites** (the ship, the cursors, the mentat's face) go over it, and
  are queued each frame.

The options screen's pointer (`fe_fop_ptr`) is six sprites shown one
after another, a new one every 8 frames: the cartridge rotates colours
8-13 of palette line 1 a place every 8 frames while that screen waits
(`opt_screen $0214A0`, `pal_cycle_cram $02208A`) and the pointer's pens
are among them, so it shimmers; `port_ui.py` photographs the six looks
(`options_pointer_0-5.png`).  A screen drawn over by the front end (the
options, a panel) comes back through `render_invalidate`: everything dirty, and the battle's palette
put up only at the end of the first pass, after the swap is asked for
(`rf_pal_pending`) - put up at once, it coloured the front end's picture
still showing for a frame.

Two screens of the port's own come before the opening (`sound.md`), and
both are the library's too, in the title's palette on black.  The
**start-up log** (`front_boot`, `front_boot_say`, `front_boot_bar`,
`front_load_bar`, `front_boot_done`) writes a white line, left-aligned,
for each check and each thing that goes to the sound card (`port.txt`'s
`boot_*`), "ok" or "error" after it, with the bar's track at the bottom;
each line, and the bar as it grows by the pixel, goes straight from the
background onto both screens (`fe_boot_show`), with no frame waited for,
as the start-up reports its progress.  The **intro's screen**
(`front_intro`) has the port's words (`port.txt`'s `intro_*`, in
Russian, each line centred by `fe_lines`), the port's version top right
(`intro_version`: its `{version}` is `PORT_VERSION` in `tools/dune_data.py`,
the one place it is set) and PRESS ANY KEY blinking under
them, 16 frames on and 16 off, while the intro's tune plays.  Their
font is
`FA_FONT_INTRO`: font8 with Cyrillic at glyphs 0-20 and a clearer '@'
(`src/res/art/ui/font_cyr.txt`, `tools/font_cyr.py` - drawn for the port,
in font8's manner, since the cartridge has no Cyrillic); a Cyrillic letter
is `$80 + n` in `text.inc`, and `fe_textn`'s `and $7F` makes that glyph
n, so no other font or string is touched.

**REDEFINE KEYS** (`fe_redefine`, from the title menu's fourth line) is
the port's own screen too, in the same colours: the eight buttons' names,
a question mark where the key goes, the key's name (`port.txt`'s
`keys_names`, five characters a key) once pressed.

The title's **starfield** is drawn every frame over the background, on
black pixels only, scrolling as the cartridge's `menu_scroll_*` does; the
planet is blitted at its plane position plus the scroll.

The **Tutorial** (bank TUTOR, `src/front/tutorial.asm`, data pages
221-223, 0, 4, 6 from `tools/dune_tutorial.py`) is the one place the port draws the
Mega Drive's way: its tiles as 4-bit pens and its name-table frames, plane
A composited over plane B cell by cell with flips and priority, the pens
turned into colours through pen-pair tables chosen per picture group.  It
draws straight onto screen 0 and keeps screen 1 as a clean copy of the
planes, so the pad and the text box can be redrawn without rendering cells
again.  Two things the Mega Drive does in hardware have to be done here by
hand: when a picture brings new tiles, or a palette change recolours a
line, **every cell showing them has to be redrawn** (the VDP recolours an
unchanged name table for free); and stepping upwards through a
vertically flipped tile needs 16-bit pointer arithmetic, because a tile's
last line can end on a 256-byte boundary.

Each screen keeps a list of the rectangles that differ from the
background; `fe_frame` copies them back from the background into the
screen being drawn, draws the sprites, and flips.  A Mega Drive screen is
224 lines and this one 200: each screen gives up the 24 lines `ui.txt`
says it can spare.  `tools/dune_front.py --preview DIR` writes every screen
as the port will show it.

## Where the time goes

`OUT ($FD),A` with a mark below `$40` (the `PROF` macro in `src/evo.inc`)
starts charging cycles to that mark, and `bin/evo/evo-run --profile`
reports them.  MAIN has marks 20-28 round the battle pass (21 the units'
tick, 22 the rotating loop, 25 the radar's row, 26 the credits, 27 the
explosions, 28 the map's animations).  RENDER's (`render_frame`'s header
lists them): 9 the wait for the last swap, 3 the squares (13 of it the
copy after the view moved, 17 the orbs), 2 the sprite list's unit loop
(18 a unit on the screen, 19 a frame's entry and its sorted insert), 14
the markers, 15 the effects, 16 the HUD, 4 matching it with the old one
(11 restoring what went, 12 what else must be drawn), 5/6 pass A's cells
and sprites, 7/8 pass B's.  The profiler must be on before the SPG runs
(`emulator.md`).  Measured in Ordos 9 idle (1.17 frames a pass, 336K T at
14 MHz): the unit loop 111K, the sprite list's entries and inserts 33K
(17 a pass, about 1.9K each - the next thing to make cheaper), the radar's
row 23K, the rotating loop 24K, matching 24K, the squares 12K, the unit
loop's rejects 12K, the four drawing passes 30K.

A pass - the units, one of the rotating loops, and the drawing - is
seldom more than a frame of work now, and since the swap is not waited
for, a pass takes that and no more: in the 27 missions played for 20000
frames with the player idle, most windows average 1.0-1.1 frames a pass
and the worst (a fight at the base) about 1.3 (`test_missions.py --frames
20000`).  A pass cannot be shorter than a frame: the logic waits for one
and the swap happens at one.  The drawing of an ordinary pass is about
100-130K T-states (0.4 frame); a big fight with every unit on the screen
moving and sixteen explosions going about 1.8M (6 frames, 1.5M of it
copying cells and sprites); a pass after the view moved a cell about
0.98M (3.4 frames: the copy 0.57M, the edge, the HUD and the sprites on
the edge the rest), where drawing every cell was 2.05M (7.2); a whole
redraw is left for a jump or a screen drawn over.  With C held the view
moves at the cartridge's 7 pixels a frame (`gamedesign.md`): in Atreides
1, 392 pixels in the first 60 frames, a pass every 4 frames - where it
used to move a cell a pass, a pass every 7 frames, about 1 pixel a
frame.  `make
verify` fails if a pass stops fitting in three frames.
