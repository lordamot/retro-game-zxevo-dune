# State of the port

The port of the Mega Drive *Dune II* (`orig/sega/`, specs S1-S10) to the
ZX Evolution BaseConf, as one SPG file.  The earlier NES-based port is
gone from `src/`; its story is in git history and `prompts/`.

## Working

**The machine and the build.**  `make build` makes `build/DUNE.DAT`: 16
code banks of 16 KB (`src/pages.inc`), the Mega Drive's tables, missions,
maps and scripts as data pages, the battle art from page 40, and the
sound set from page 128.  The emulator loads SPG files (`--spg`, and the
`spg FILE` script command).  A real machine cannot - the BaseConf
firmware runs no SPG - so `make build` also writes `build/dune.trd` and
`build/DUNE.DAT`: the firmware boots the disk and its loader
(`src/loader/loader.asm`) reads the SPG off the SD card through the FAT
(`build.md`); `make verify` boots it that way from FAT16 and FAT32 card
images.  `make verify` passes.

**A battle.**  Any of the 27 missions loads the cartridge's way (S9) and
runs: units tick with the cartridge's timers and run the original EMC
bytecode, move and find paths (S3), fight (S4); structures animate,
produce, refine, power and decay (S5, S6); houses, teams and the AI play
(S7); reinforcements arrive; the level-end check runs every 300 ticks
(S9).  A battle pass takes about a frame at 14 MHz (1.0-1.1 in most
missions, `graphics.md`).

**The screen.**  ATM EGA 320x200 in sixteen colours, double-buffered; only
changed cells are redrawn, and a sprite is redrawn only when it or
something under it changed.  The Mega Drive's icons and sprites, with the
house colours per palette line; the fog; explosions and smoke; the
Harvester's dust; units' effect animations (the MCV's deploy blink, the
flash on an attacked enemy, the Devastator's self-destruct); the
Starport's lights while the Frigate is on its way; a Harvester on the
Refinery's pad while it unloads; the structure markers ('OK' on a Yard
whose building waits and on a ready Palace - blinking, the port's touch -
the repair hammer, a Windtrap's low-power bolt); every structure's house
marker with its orb turning, eight frames as the cartridge's; the screen shake after a big blast or a fallen
structure (one screen buffer drawn a cell away - `graphics.md`).

**The controls (S10).**  The cursor with the Mega Drive's acceleration,
the view with C held at the cartridge's 7 and then 14 pixels a frame,
its shape by the selection (the crosshair for one of the player's units
or an armed Palace) and the blinking brackets round what is selected; C
held moves the view; A selects and gives the order that fits what is under
the cursor (Move, Attack, Harvest, Guard, deploy - an MCV blinks for 255
frames first), B does all the cartridge's B does (`gamedesign.md`), Start
calls the options.  REDEFINE KEYS on the title menu (the port's) gives
each button a key of its own.  A finished building is placed from the Construction
Yard with the square-by-square grid cursor and a footprint that shows
whether it fits.

**The HUD.**  The credits counter rolls by `ui_draw_credits`'s rule (the
quota reads it); the CREDITS LOW warning; the selection's portrait and
health bar, and under them all the side panel shows on the Mega Drive
(`ui_draw_selection_panel $0294BE`, decided by UI every input step):
what a factory or the Yard builds and its progress, the upgrade, the
Repair Facility's unit and its repair, the Palace's weapon and charge, a
Windtrap's power, a Refinery's or Silo's spice, the Starport's delivery,
a Harvester's load, and the red no sign when a factory has no room or the
Palace is in its delay - compared with the running cartridge screen by
screen; the radar with its switch-on and -off animations and the
marker on the cursor's square, the map shown only with a working
Outpost.
- The bars are eighths in a black box, where the cartridge draws a
  black-outlined bar pixel by pixel; the upper portrait of a Fremen-house
  unit is still its type's, not the Fremen (animations `$5E`/`$68`,
  `$029926`), though the frames are there (458, 459).

**Sound.**  All 20 tunes, each with samples of its own (nothing shared),
and the 36 effects the game plays.  At power-on the port's start-up log
(black, a line for each check - the machine, the card, its memory - and
each thing that goes to the card, "ok" or "error", which stops the
start-up; a progress bar by what the upload costs) sees the General Sound
card get the effects and every tune it has room for, with nothing
playing: on 2 MB twelve - the front end's, the three mentats', the five
battle tunes and the Tutorial's - so no tune the game plays waits but the
finale and the ending's.  Then the port's own intro tune
(`src/res/external.mod`) plays on its own screen (its words in Russian,
PRESS ANY KEY; from 29.5 s after power-on) until a key, and gives its
pages back after.  The rest
are kept in the SPG packed (0.57) and streamed to the card when wanted,
from the battle pass and the front end's idle time, and the card keeps
what it has while it has room (`sound.md`).  Effects, voices, the mentat's
tune by house and the battle music's no-repeat shuffle play by the
cartridge's own numbers, and the shuffle draws from the game's generator
exactly when the cartridge does (`snd_play_music $00A806`, the pass's
`$01253A`), with a card or without.

**Without a card.**  The start-up log's card checks (no card, one that
never settles, one with too few pages) say "error" and then the port's
"no sound: press a key to play without"; a key, and the start-up goes on
with the card given up - the intro and the game silent, the switches on
as the cartridge starts them (`sbt_snd` in `main.asm`; `make verify`
runs it with the emulated card answering nothing).  Only the machine
check still stops the start-up.

**The 2026-09-29 review's fixes.**  The Death Hand is scattered (its aim
was handed across a far call as a COMBAT2 address, and read COMBAT's
bytes) and its blasts off the map are skipped where the burst runs; the
sprite list keeps room for the HUD, so a screen full of units no longer
drops the cursor, the credits and the radar; the card's init waits are
real; the disk loader's command timeout is reported; a Yard destroyed
with a building waiting frees it; the credits lost with a structure come
from the whole 32-bit amounts; the mentat's box takes five lines (Ordos
1's defeat text); LOOKAROUND shows the whole map.  Faster: a pass in
Ordos 9 went from 1.24 to 1.17 frames (the orb pass only when the frame
moves on, the radar's row in one loop, units far from the view rejected
on their high bytes; `graphics.md`).

**2026-09-30, from a SONICBLAST playtest.**  The radar's colour table
was left unaligned by the row speed-up (black and white map); the map
now shows as its rows are drawn (one picture, in place) instead of at
the end of a scan; the orb's frame is per screen (it jumped after the
options screen); the bracket and corners sit under the radar; the
battle's palette comes up with its first picture after a front-end
screen; a tune is faded before the options screen stops or changes it;
the options pointer slides between rows and wraps; the Sonic Tank's
icon is in its own palette line (blue); a Tank's turret sorts with its
hull.

**2026-09-30, from a DUNERUNNER playtest.**  A 4-Slab paves only the
squares that can take concrete (sand, dunes and mountain in its
footprint are left; skipping the touch test with `validate_strict` had
made every landscape valid); a structure placed off concrete starts at
the cartridge's health (a Windtrap on bare rock 200 of 400, not 100: the
layout count clobbered the divisor); a wall's square loses its crater
(the square-finishing step ran on the west neighbour); a death always
shows: the explosion pool is 32 entries (was 16, the cartridge's 162)
and, full, retires the wreck or smoke with the least time left instead of
dropping the new blast - the stack, measured at 68 bytes used, is 256 to
make the room; the options pointer shimmers as the cartridge's palette
cycle makes it (six extracted frames, one every 8 frames); the intro's
version is `PORT_VERSION` in `tools/dune_data.py`.  Looked at and found
as the cartridge has them: blooms draw as ground icon `$D0` and
DUNERUNNER has none (its two Sandworms' mounds are what comes and goes),
the worm's sprite is the cartridge's own round mound (animation 213),
power drops when Windtraps die (`struct_remove` recounts; health halves
on the next 900-tick house pass), and a Carryall fetches only a unit on
plain Guard below half health for an idle Repair Facility, when one of
its house is free.

**Debugging and tests.**  The debug block (`src/world.asm`: house,
mission, flags, credits) is set by `build_dune.py`; `tools/dune_test.py`
calls any routine through the mailbox, in test mode or inside a running
battle.  `make test` runs a suite per subsystem against the specs' models
(`tools/tests/`: core, move, combat, struct, house, fx, ui, render), and every one
of the 27 missions starts and keeps running without a hang (`test_missions.py`).

**The front end.**  The Mega Drive's own sequence: logos and PRESENT over
the scrolling starfield, the title with the planet and the ship, the
Tutorial (from the menu, and as the title's attract after 900 idle
frames: the cartridge's own picture scripts, `src/front/tutorial.asm`,
bank TUTOR), the crests, the mentat's house description and
briefing (a sentence at a time, PROCEED/ADVICE), the campaign map (the
territories falling one after another, the zoom into the one attacked),
victory
and defeat pictures, the mentat's verdict, the score page, the password,
the options (music, sound, radar, the tests, password entry, restart, pick
another house, the cheat words) and the ending (`src/front/`,
`tools/dune_front.py`).  Missions follow one another: a loss plays the
mission again, a win the next.

**The panels.**  A on a selected structure opens its panel (`src/front/panel.asm`
via the FRONT library): the Construction Yard's build list, the factories'
and Barracks' unit lists, the Hi-Tech's flyers, the Starport's offers,
repair, stop, upgrade, with the item's picture and figures.  The Palace's
weapon is armed and fired from the battlefield.

## Not yet

- Approximated in the front end: the planet slides in 8-pixel steps
  while the stars move by the pixel; the logo fades dim the stars too; the
  Tutorial's fades are 4 steps, its pad shows its top 58 lines, 16 colours
  a picture group (the sand more orange, the grid greyer), and song 30
  (heavy_drop) is not in the sound set, so that part is silent; the zoom
  and the fall can be cut short by a button, which the Mega Drive does not
  allow.
- `front_noise`, `front_fm1`, `front_fm2` are uploaded to the card, but
  nothing plays them yet.
- A tune not on the card yet starts after a silence while it loads: on 2
  MB the finale and the ending's tune (1.5-3 s) and the music test's
  rarities; on a 1 MB card also the battle tunes the first time (5-6 s,
  the game's passes about 0.7 frame longer meanwhile), the Atreides
  mentat's and the Tutorial's.  A 12 MHz card spends nearly all its time
  mixing whatever tune plays, so it takes the next one only in the mixer's
  idle moments - a trickle, nothing during a battle's effects (`sound.md`,
  "The card's time").
- The start-up takes 29 s with 2 MB, 10.9 of them the card's own memory
  test; the upload could shrink by a few seconds if tunes were unpacked
  into free RAM during that test (only 480 KB of it is free).
- A pass with the card can take a frame more than without (its commands
  cost time), and from then on the passes - and so the game's random
  numbers - part from a run with no card: timing, as on the Mega Drive,
  not the music.
- The cartridge also draws a battle tune when its options screen closes
  with the music on (`$021570`) and in the build and Starport panels'
  loops while `musicFramesLeft` is negative (`$028906`, `$028C98`); the port's
  options and panels (FRONT, PANEL) do not.  After the last mission's
  victory the port's front end starts the mentat's tune over the finale,
  where `mentat_victory $01F512` only lets the sound fade.
- spice trip, command post, conquest, the middle of the title and a
  passage of radnors are more than the card's mixer can do at 12 MHz: they
  stutter slightly, as they did with shared samples.
- The frame budget holds with a margin now (the renderer no longer waits
  for the screen swap, and draws in about 60% of the time it took):
  played idle for 20000 frames, no mission's window averages more than
  1.33 frames a pass (Atreides 5; Atreides 4's attack on the base 1.22),
  where it was 2.0-2.8 (`test_missions.py --frames 20000`); at 3000
  frames the worst window is 1.14 (Ordos 9), 1.23 before the 2026-09-29
  speed-ups.  What a pass costs now (`graphics.md`): the unit loop a
  third of it, the sprite list's sorted inserts a tenth, the radar's row
  a fourteenth.  A pass
  while the view scrolls is about 4 frames (7 before): the screen showing
  is copied over the one drawn, moved, and only the new edge, the HUD
  and what moved are drawn - the copy itself is half of it (`graphics.md`).
  A fight with the whole screen full of moving units and explosions is
  about 6 frames of drawing (11 before).
- A worst-case route plan takes 3-6 frames (the cartridge's own
  algorithm).
