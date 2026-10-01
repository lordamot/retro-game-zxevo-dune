---
name: game
description: Change or explain how the game plays - rules, numbers, units, buildings, the enemy - in this port of the Mega Drive Dune II. Use when asked to change a price, alter the AI, fix a rule, or explain game logic.
---

# The game itself

The port runs the Mega Drive cartridge's own rules.  What the game must do
is in `orig/sega/spec/S1-S10` (each with a tested Python model,
`tools/sega/sega_spec_check.py`); the cartridge's 68000 code is in
`orig/sega/src/` with routine names in `orig/sega/res/names/`.  Every
routine in `src/` cites the cartridge address it reproduces - start there.

## The numbers

Not in the code: `src/res/data/` holds the cartridge's tables as text
(unit and structure types, houses, landscape, orders), the 27 missions,
the 27 maps and the four EMC scripts.  `tools/dune_data.py` turns them
into `tbl_*` tables with the ROM's field offsets (`UI_*`, `SI_*`, `HI_*`,
`LS_*`).  Change a number there.

## Where things are

| | |
|---|---|
| unit loop, movement, path finding (S1, S3) | `src/move/` |
| targets, firing, damage, explosions (S4) | `src/combat/` |
| structures, production, economy, Starport (S5, S6) | `src/struct/` |
| houses, teams, the AI, reinforcements, the end (S1, S7, S9) | `src/house/` |
| pools, references, the map's objects, fog (S2, S8) | `src/obj/` |
| the scripts' interpreter and routine tables (S7) | `src/vm/` |
| loading a mission (S9) | `src/scen/` |
| the controls, credits, radar, placing (S10) | `src/ui/` |
| the battle loop, sound calls, mission flow (S1) | `src/main/` |

Records keep the cartridge's offsets but are little-endian - read the
byte-order table in `.claude/docs/port-code.md` before touching a flag.
Where the specs mark a cartridge bug as fixed, the port's comment says so.
