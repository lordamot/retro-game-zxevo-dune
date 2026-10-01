# The game: what it plays, and where it differs

The game is the Mega Drive *Dune II - The Battle for Arrakis*
(`orig/dune2.gen`, the PAL release), played by its own rules.  What those
rules are is written down in `orig/sega/spec/S1-S10`, each claim with the
cartridge address it comes from and most of them tested against the
running cartridge (`tools/sega/sega_spec_check.py`); the port reproduces
them routine by routine and cites the address in its comments.  This page
is the map, not the rules.

## Where the rules are

| spec | what | the port |
|---|---|---|
| S1 frame | the battle pass: the unit loop, the rotating structure, team and house loops, the timers | `src/main/`, `src/move/`, `src/house/` |
| S2 objects | the unit, structure, house and team records, pools, references, orders | `src/obj/`, `src/records.inc` |
| S3 movement | speed, turning, path finding, the map's objects | `src/move/` |
| S4 combat | targets, firing, projectiles, damage, explosions, deviation, the Palace weapons | `src/combat/` |
| S5 economy | spice, Harvesters, Refineries, Silos, credits, Carryalls | `src/struct/`, `src/move/` |
| S6 production | building, upgrading, repairing, the Starport, power, what can be built when | `src/struct/`, `src/front/panel.asm` |
| S7 enemy | the AI: houses waking, teams, the build choice, the EMC scripts | `src/house/`, `src/vm/` |
| S8 map | landscape, the fog, spice blooms, map animations, the radar | `src/obj/map.asm`, `src/struct/`, `src/ui/` |
| S9 mission | loading a mission, reinforcements, winning and losing, the score | `src/scen/`, `src/house/` |
| S10 screens | the front end, the controls, the HUD, the options, the sounds | `src/front/`, `src/ui/`, `src/main/` |

**The numbers are the cartridge's**, as text in `src/res/data/` (unit and
structure types, houses, landscape, orders, the 27 missions, the 27 maps,
the four EMC scripts), turned into tables with the ROM's own field offsets
by `tools/dune_data.py` (`.claude/skills/game`).  **The AI is the
cartridge's**: the EMC bytecode of `UNIT`, `TEAM` and `BUILD` runs
unchanged on the port's interpreter (`src/vm/emc.asm`), which calls the
same routines the 68000 one does.

## The shape of it

The Mega Drive's own sequence (S10): the logos; the title, with the
planet and the ship; START GAME, OPTIONS, TUTORIAL; the three crests; the
mentat's description of the house and the briefing, a sentence at a time,
PROCEED or ADVICE; the campaign map; the battle; the victory or defeat
pictures, the mentat's verdict, the score page and the password; the
ending after the last mission.  A loss plays the mission again, a win the
next.  The options screen (its pointer slides between rows 4 pixels a
frame and wraps from the last row to the first, `opt_pointer_key
$021C16`, keys waiting for it) has the music and sound switches, the radar, the
music and sound tests, password entry, restart, another house and the
cheat words (LOOKAROUND shows the whole map and hides it again - the
renderer's reveal, `dbg_flags` bit 0 - SPLURGEOLA the credits, PLAYTESTER
and VERSIONNUM as the cartridge).

Nine missions a house; a mission's `Seed` names one of the 27 battlefields
the cartridge stores whole (there is no map generator).  The level-end
check runs every 300 ticks: won when the enemy's structures are gone (or a
spice quota is met, where the mission says so), lost when the player's are.

## The controls

The Mega Drive pad on the ZX keyboard (`src/stub/input.asm`, read on every
frame interrupt):

| pad | keys |
|---|---|
| d-pad | Q A O P, the cursor keys, 7 6 5 8, a Kempston stick |
| A - select, and the order that fits what is under the cursor | SPACE, M, fire |
| B - back | Z, N |
| C - held, the d-pad moves the view | X, SYMBOL SHIFT |
| Start - the options | ENTER |

These are WORLD's `pad_keys`, two keys a button, which the interrupt reads.
**REDEFINE KEYS**, the port's own fourth line on the title menu
(`fe_redefine`, FRONT), asks for a key for each of the eight buttons in
turn - a key already given is refused - and replaces the table: one key a
button from then on, until the machine is reset.  The joystick is read as
it is either way.  The cartridge has a pad and no such screen.

**Scrolling.**  C held moves the view as the cartridge does
(`irq_battle_free_cursor $006E3A`-`$006E6E`): 7 pixels a frame for the
first 60 frames C and a direction are held together, 14 after that, the
count starting again when either is let go.  (S10 says only that C turns
the d-pad onto the view; the speed is in the code.)  Without C the
Mega Drive's view follows the cursor once it leaves the middle of the
screen, at up to 3 pixels a frame; the port's follows it only when the
cursor is pushed against an edge, at those 3 pixels a frame, because a
moved view costs a copy of the screen.  The view moves in cells, by the
pixels a pass earns, and what is left of a cell is kept for the next
pass (`view_move`).

As on the Mega Drive there is no command menu: A on a square gives Move,
Attack, Harvest, Guard or deploy from what is there (Move, not Attack, on
a unit hidden in the fog), and A on a selected structure opens its panel.
A on the MCV itself starts its deploy: it blinks and beeps for 255 frames
and then becomes a Construction Yard; A again or a Move cancels it.

B (`ui_battle_button $02838E`) drops a selected unit and goes back to the
structure selected before it (or the player's last one); hurries a
pending deploy or self-destruct; ends the placing of a finished building;
disarms a ready Palace; and on an idle factory or Yard **starts its last
item again** - S10 says B stops production, and the running cartridge
says otherwise, so the port does what the machine does.  During a build
it does nothing.

The side panel (`ui_draw_selection_panel $0294BE`, run at the end of
every input poll) does more than S10's summary says, and the port does
what the running cartridge was seen to do (`tmp/sidebar/`, `test_ui.py
sidebar`):

- **A label S10 leaves out**: the red no sign over the lower picture, for
  a factory with no room (flags2 bit 8; not a Yard making a 4-Slab or a
  Wall), a Hi-Tech with no aircraft slot, and a Palace in its delay
  (`+$4E`), which then shows no bar either.  A ready Palace shows none.
- **"For an enemy, only portrait and bar"** holds for structures only: an
  enemy Harvester shows its load too - the unit branch never looks at
  the house.
- **"A Windtrap's power"** is the house's power used of power made (at
  least 1), so plenty of power is a nearly empty bar.  A Refinery's or
  Silo's is the credits of the storage, both halved until the storage fits
  11 bits.  The Atreides Palace's picture is the Fremen (animation `$5E`)
  whatever its `+$52` says.
- **Drawing it changes the game**: a production whose countdown has run
  out is marked finished there (`ui_struct_action $012144`: flags2 bit 14
  off, 13 on), so a finished factory drops its bar once it is looked at;
  and a captured factory (`+$4C` not the player) re-reads `+$52` from what
  it holds (`$0295B4`).
- The names file calls `$06A7DA` the second bar's "upper" position and
  `$06A7E0` its "lower": on screen they are y 112 and y 80, the other way
  round, and both records are x then y, not y then x.

## Two fixes the listing does not have

- **A 4-Slab paves every square that can take concrete once its
  footprint has passed.**  The footprint's own check has answered whether
  the slab touches the base; asking each square again by itself
  (`struct_check_location(square, 0)`, which the listing at
  `struct_place $00E87E` calls with nothing set, and whose ring for a 1x1
  layout is the eight neighbours) paved only the row next to the Yard of
  a 4-Slab put down two squares from it, while the footprint showed green
  and the whole slab touched.  `st_sp_slab` runs the per-square checks
  with only the touch test skipped (`st_cl_notouch`): rock and nothing
  standing on it is enough, and a square of sand, dunes or mountain in
  the footprint is left as it is, as the cartridge leaves it
  (`test_struct.py port rules`).  Skipping the test with
  `validate_strict`, as it once did, paved the mountain too.
- **A factory's item is one its panel offers.**  The cartridge's
  `struct_default_build_type $010D9E` gives a Light Factory the Quad
  whatever the mission's tech, and B on the idle factory builds it with no
  check; the sidebar shows it.  Here `st_offer_of` (STRUCT2) keeps the
  cartridge's choice when `struct_get_buildable` offers it and takes the
  first offered type otherwise, at the default, after an upgrade by
  mission, on capture and for the Heavy Factory without an Outpost.

## Time

Game time is counted in frames, as the cartridge counts it: the interrupt
counts frames and each battle pass is told how many went by
(`frames_this_pass`), and every timer, delay and animation moves by that
much.  So the game runs at the cartridge's speed however long a pass takes
- about one frame here in most of a battle, a little more in big fights -
and only the drawing is less frequent when it takes longer.  The ZX Evolution's frame is the Pentagon's, 71680 T-states
at 3.5 MHz, 48.8 a second against the PAL Mega Drive's 49.70, so the whole
game runs about 2% slower; nothing has been seen to mind.

## Where the port differs, on purpose

**Cartridge bugs.**  Every spec ends with a table of the cartridge's bugs
and what the port does with each - keep it (the game was balanced with it,
or it is how the units behaved) or fix it.  The fixes:

| spec | what the cartridge does | the port |
|---|---|---|
| S1 | a structure script, or a team's, that stops ends the loop for all later ones | the loop goes on |
| S1 | the unit after a held Frigate skips the Frigate test | tested |
| S1 | the credit cap is applied to whichever house the last loop left current | each house capped in its own loop |
| S2 | `linkedID = $FF` read as index -1; a structure reference above 72 reads a null record | tested, bounded |
| S3 | an aircraft's turn across north is not wrapped, so it crawls | wrapped to 0-128, as the PC does |
| S3 | a Harvester's goal square is read as a unit without testing there is one; the "near" test fails for a crusher exactly on y = `$0100` | tested; answers near |
| S4 | the big explosion's seven blasts start from an uninitialised register; deviation reads a stale register for the house | from 0; the house passed |
| S4 | credits lost with a structure use the low words only; Death Hand blasts may land off the map | whole amounts; off-map blasts skipped |
| S5 | a Carryall takes the first free Refinery, not the nearest; a computer house's refinery cap uses the player's figure | the nearest; its own storage |
| S6 | an upgrade that turns one factory type into another does not move the per-type counts; `structuresBuilt` is kept per side, so computer houses share buildings for every requirement | counted; per house |
| S6 | the computer's build choice runs for a Starport, reading past the unit table | skipped |
| S7 | a unit freed in the middle of a loop over the units makes it skip the next one | not skipped |
| S8 | arrival edges ignore the playable area's origin on 32 x 32 maps; "enemy base" and "home base" both mean near the player | fixed, with S9's reinforcements |
| S9 | freeing houses while walking their list leaves one in use with no units; the reinforcement slots count from 1 | only the houses the file names; from 0 |
| S10 | a spoken-feedback id of -2 passes the range guard; the build menu passes an unloaded register | tested; passed |

The port-side fixes found since the specs were written are in the code's
comments (`Port fix`), and in `progress.md` when they matter to play.

**The machine.**

- **The screen is 320x200, not 320x224.**  The battlefield is 10 x 6.25
  squares instead of 10 x 7; each front-end screen gives up the 24 lines
  it can spare (`src/res/art/ui.txt`).
- **Sixteen colours, not the Mega Drive's up to 61** (the battlefield alone
  uses 31).  The rest are fixed two-colour checkerboards (`graphics.md`).
- **The view scrolls in 8-pixel steps and sprites move in 2-pixel steps**
  across (exact up and down): there is no scroll register and a byte is two
  pixels.  It follows the cursor only at the screen's edges, not once it
  leaves the middle (above).  When the view stops at the map's edge with C
  held, the cartridge moves the cursor on instead; the port's cursor stays.
- **Sound** is the cartridge's own music and effects, converted through a
  model of its sound driver into modules the General Sound card's ROM plays
  (`sound.md`).  The card's 2 MB does not hold the whole set; what is left
  out is listed there.

**Debugging** (not in the game): the debug block at the start of WORLD
(`src/world.asm`, set by `make run HOUSE= MISSION= DBGFLAGS= CREDITS=`)
starts a battle directly, reveals the map, makes the player invulnerable,
speeds production up, or silences the card.
