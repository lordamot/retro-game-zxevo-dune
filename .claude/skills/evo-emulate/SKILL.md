---
name: evo-emulate
description: Run and drive the ZX Evolution BaseConf emulator - boot a disk, script keypresses, take screenshots, dump memory, profile the frame. Use when asked to run, test, screenshot or debug anything on the target machine.
---

# Driving the ZX Evolution

The emulator is `bin/evo/evo-run` (headless, scriptable) and
`bin/evo/evo-play` (an SDL2 window).  Both are this project's frontends
over libxpeccy; `.claude/docs/emulator.md` is the full story.  The game is
an SPG (`build/DUNE.DAT`), which the emulator loads directly - no firmware
menu, no disk.

## The short way

```sh
make run                                   # build and play, window and sound
make run HOUSE=A MISSION=3                 # straight into a battle
python3 tools/evo_control.py script tools/demo.script --spg build/DUNE.DAT
python3 tools/evo_control.py play   --spg build/DUNE.DAT --scale 2
python3 tools/evo_control.py nvram         # regenerate the saved settings
python3 tools/dune_test.py state --frames 300   # boot, run, print units/structures/houses
```

## The long way

```sh
bin/evo/evo-run --rom bin/evo/zxevo_baseconf.rom \
                --gsrom bin/evo/gs105a.rom \
                --spg build/DUNE.DAT --script F [--profile] [--wav F.wav] [--quiet]
```

Script commands: `run N`, `reset`, `hold KEYS`, `release`, `press KEYS N`,
`type TEXT`, `fillram SEED` (random RAM, as a real machine's), `spg FILE`, `trd FILE`, `sd IMAGE` (an SD card image,
`tools/sd_image.py`; `--sd IMAGE` on the command line), `poke ADDR V`, `pokepage PAGE OFF V`,
`shot FILE`, `wav FILE`/`wavstop`, `ram FILE`, `page N FILE`,
`gsmem N FILE`, `peek ADDR [N]`, `state`, `gstrace N`,
`profile`/`profreport`, `echo`.

Keys are ZX names: `a`..`z`, `0`..`9`, `enter`, `space`, `caps`, `sym`,
`up`/`down`/`left`/`right`, `break`, plus `kjup`, `kjfire` and friends for
a Kempston joystick.  The game reads them as a Mega Drive pad: Q A O P
move, `space` is A, `z` is B, `x` (held) is C, `enter` is Start.

## Reading what happened

- `state` prints PC, SP, the video mode, the clock, the page in each window
  (`banks=r896,...`: divide by 64 for the page), `$7FFD`/`$EFF7`/the
  `xx77` shadow, and the sound card's PC.  `video=ega16c` and `turbo=4.0`
  is what a running game looks like.  With the window-0 page and
  `build/bank_of.txt` + `build/dune.sym`, a PC is a routine.
- `page 24 F`, `page 25 F`, `page 26 F` dump UNITS, WORLD and MAP;
  `build/dune.sym` gives WORLD's variables as `$8000 +` their offset.
  `tools/dune_test.py`'s `units()`, `structures()`, `houses()` decode them.
- To call a routine and read what it did, use the mailbox: `tools/dune_test.py`
  (`Machine().call("label", a=..., ix=..., frames=N)`, then `run()`).  Check
  `regs(step)["done"]` for every call.
- Screenshots come out as 768x576 BMP.  Convert with Pillow to look at them.

## Profiling

`OUT ($FD),A` with a mark number (`PROF n`, `src/evo.inc`); the emulator
charges the cycles until the next mark to that one.  RENDER uses 1-10,
MAIN 20-23.  At 14 MHz a frame is 286720 cycles (48.8 a second).

```sh
bin/evo/evo-run ... --spg build/DUNE.DAT --script tools/demo.script --profile
```

Mark 0 is the wait for the interrupt, so it is *idle* - the work is
everything else.

## Things that will waste your time

- A mailbox call still running when its pages are dumped makes the next
  step report its answers - give calls enough frames and check `done`.
- The tests read `build/` unless told `--build-dir`; an old build
  directory is an old game.
- Booting a **disk** (`--trd`) goes through the firmware: its menu needs
  ~250 frames before it takes a key, and without `--nvram
  bin/evo/evo-nvram.bin` it looks on the SD card's virtual drive and says
  "No Progs".  `evo_control.py boot` does the dance.
- Two presses of a key with no release between them jam it (libxpeccy
  counts them); `press` releases for you.
