# Dune II for the ZX Evolution

A port of the Mega Drive **Dune II - The Battle for Arrakis** to the **ZX
Evolution BaseConf**.

As closed as it was possible:
- fully playable with music and sounds
- optional run without GeneralSound card (no sounds at all then - not recommended)
- built from scratch based on original rom file (not included)
- generated code is MIT License

How to build yourself:
- pipeline tested on Ubuntu Linux only
- `make toolchain`, `make build`, `make run`

How to run yourself:
- put ./build/dune.trd and ./build/DUNE.DAT in SD card root
- start Evo
- "file browser" - "mount A:"
- "Run TRDOS"

Check `./prompts` directory for full build history and sufferings.

## Known problems and plans

- NeoGS detection does not work

Any feedback on playability issues appreciated.

## Controls

The keyboard is the Mega Drive pad:

| Key | Pad | |
|---|---|---|
| Q A O P, the arrow keys, 7 6 5 8, a Kempston stick | d-pad | move the cursor |
| SPACE, M, fire | A | select; with something selected, the order that fits what is under the cursor - move, attack, harvest, guard, deploy; on a structure, its panel |
| Z, N | B | back |
| X, SYMBOL SHIFT (held) | C | the d-pad moves the view |
| ENTER | Start | the options |

REDEFINE KEYS on the title menu gives each button a key of your own.

## Screens

![Scr01](readme/01.png)
![Scr02](readme/02.png)
![Scr03](readme/03.png)
![Scr04](readme/04.png)

## How it is made

The Mega Drive cartridge was taken apart first (`orig/sega/`, below), and
what the game does was written down as ten specifications,
not included here - the battle pass, the records, movement, combat,
the economy, production, the AI, the map, missions and the screens - each
claim with the 68000 address it comes from, and tested against the running
cartridge.  The port is Z80 assembly written from those specs, routine by
routine, in 16 KB code banks that call each other through a far-call
trampoline; the records keep the cartridge's field offsets, so its RAM and
the port's can be compared field by field.

- **The data** is the cartridge's, as text in `src/res/data/`: unit and
  structure types, houses, the 27 missions, the 27 maps, the four EMC
  script files and every string.
- **The pictures** are the cartridge's, cut out of it and out of its video
  memory as PNG in its own colours (`src/res/art/`), and converted at build
  time: sixteen colours chosen for the battlefield, the rest drawn as
  two-colour checkerboards; sprites masked, in four house colourings.
- **The sound** is the cartridge's songs and samples, played through a
  model of its Z80 sound driver and written as ProTracker modules
  (`src/res/prebuilt/`), uploaded to the card at start-up.

The renderer redraws only the 8x8 cells that changed since the screen
being drawn last showed them, with sprites over them, double-buffered; a
battle pass takes about 1.8 frames, and game time is counted in frames as
the cartridge counts it.

`.claude/docs/progress.md` says what works and what is missing.

## Layout

```
src/            the Z80 game; src/res/ its data, pictures and sound
tools/          the Python CLIs, the ZX Evolution emulator and the libretro
                frontend (both C); tools/tests/ the subsystems' tests
bin/            built: sjasmplus, evo-run/evo-play, the NES and Mega Drive
                cores, the BaseConf firmware and the General Sound ROM
.claude/docs/   the port, the machine, graphics, the game, the build, the
                emulator, sound, the tools, the originals, progress
.claude/skills/ how to work on each part
```

Start with `.claude/docs/port.md` (the port's shape) and
`.claude/docs/platform.md` (what the machine is).

## Credits

*Dune II - The Battle for Arrakis* is Westwood Studios', published by
Virgin Interactive, 1992-1994; the Mega Drive version in `orig/` is the game
this port reproduces.  *Sand Emperor* demo 5 is by TI (2021).  The ZX
Evolution is NedoPC's.  The emulator is built on **libxpeccy** from
samstyle/Xpeccy; the reference machines run **FCEUmm** and **Genesis Plus
GX** through libretro; the assembler is **sjasmplus**.  The BaseConf
firmware and the General Sound ROM are taken from the ZEsarUX distribution.

This repository is a port and a preservation effort.  The originals are
included as found, in `orig/`, and are never modified.
