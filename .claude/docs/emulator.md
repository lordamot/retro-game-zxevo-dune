# The ZX Evolution emulator

There is no ZX Evolution emulator on this host that can be built without
installing Qt, so this project builds its own frontend on top of the one
machine library that already models the board properly.

## What it is made of

`tools/evo-emu/` is about 700 lines of C over **libxpeccy**, the plain-C
machine library inside samstyle/Xpeccy.  libxpeccy already implements the
PentEvo memory manager, the ATM video modes, the 3.5/7/14 MHz turbo, the
Beta Disk interface with .trd images, TurboSound and the General Sound
card; what it does not have is a frontend that can be scripted, and that is
what this is.

```
tools/evo-emu/evo.h       the machine, as a handful of calls
tools/evo-emu/evo.c       set-up, the frame loop, the framebuffer, keys
tools/evo-emu/evo-run.c   headless and scriptable
tools/evo-emu/evo-play.c  an SDL2 window with sound
```

`make toolchain` clones Xpeccy into `tmp/`, renames its
`cpu/NEC V30` directory (make cannot express a target whose path has a
space in it), compiles the library and both frontends, and copies the
finished binaries into `bin/evo/` along with the two ROMs it needs.

## The ROMs

`bin/evo/zxevo_baseconf.rom` is the real 512 KB ZX Evolution BaseConf
firmware - the December 2012 build, which identifies itself as "EVO Reset
Service v0.55b" when it boots.  `bin/evo/gs105a.rom` is the General Sound
card's own ROM.  Neither is this project's to generate; both ship inside
the ZEsarUX distribution, which `make toolchain` clones to fetch them.

## The saved settings

`fillram SEED` in a script fills all 4 MB of RAM with pseudo-random bytes
(`fillram 0` zeroes it): a real machine's RAM at power-on.  The emulator's
RAM starts at zero, which hides anything the game trusts to be zero; the
boot's clear table (`platform.md`) is checked this way.

`--sd F.img` (or `sd F.img` in a script) puts a raw SD card image - an MBR
and one FAT16 or FAT32 partition - in the board's slot, so the firmware's
own file browser and loaders can read it; libxpeccy answers the card's SPI
commands.  The firmware's browser draws in a text mode this emulator does
not render (the screen goes black); dump page 5 and read it by hand.

`bin/evo/evo-nvram.bin` is 256 bytes of the board's battery-backed CMOS.
Out of the box the firmware's drive A is the SD card's *virtual* drive, so
a floppy image in drive A is invisible and "TR-DOS boot" says "No Progs".
The saved copy has the virtual drive moved to B and the CPU clock set to
14 MHz.  `make nvram` regenerates it by booting the firmware and pressing
the two keys, which is exactly what a person would do once on real
hardware.

## evo-run: the headless machine

```
evo-run --rom bin/evo/zxevo_baseconf.rom [--gsrom F] [--trd F.trd]
        [--spg F.spg] [--sd F.img] [--nvram F] [--save-nvram F] [--script F]
        [--frames N] [--shot F.bmp] [--wav F.wav] [--profile] [--quiet]
```

A script is one command a line, `#` starts a comment:

| | |
|---|---|
| `run N` | run N frames |
| `reset` | hard reset |
| `hold KEYS` | hold these keys from now on (comma separated) |
| `release` | release everything |
| `press KEYS N` | hold KEYS for N frames, release, then two idle frames |
| `type TEXT` | press the letters and digits of TEXT one at a time |
| `trd FILE [DRIVE]` | insert a disk |
| `spg FILE` | load an SPG as its loader does - every block into its RAM page, the clock and window 3 as its header says - and jump to it; `--spg F` does the same at start-up |
| `poke ADDR V` / `pokepage PAGE OFFSET V` | write a byte into the CPU address space / straight into a RAM page (how `tools/dune_test.py` fills the debug block and the mailbox) |
| `shot FILE` | write the current frame as a 24-bit BMP |
| `wav FILE` / `wavstop` | capture audio |
| `ram FILE` | dump the 64 KB the CPU currently sees |
| `page N FILE` | dump one 16 KB RAM page |
| `gsmem N FILE` | dump one of the General Sound card's own 16 KB RAM pages |
| `gstrace N` | print the next N port accesses between the machine and the sound card, with the card's PC |
| `pctrap LO HI [PAGE]` | hex addresses: the first opcode fetch from LO..HI (with PAGE in window 0, or any) prints the last 64 fetches, each with its window-0 page, and SP.  `pctrap 4000 7FFF` catches a CPU that has fallen into data: the ring says how it got there |
| `wtrap LO HI [PAGE]` | the first write into LO..HI prints the value, PC and the same ring.  The stub ($0000-`stub_end` of every code bank) owns no variable, so `wtrap 0000 09FF` from the start finds the pointer that corrupts a bank - which otherwise shows up as a crash much later, somewhere else |
| `gsclock MHZ` | the sound card's Z80 at this clock, its interrupt still 37.5 kHz - `gsclock 16` is the ZX-MultiSound rev.A1 (libxpeccy's is 12) |
| `gsram KB` | the sound card's RAM this big (a power of two, before `spg`: the ROM's power-on test must see it), the pages above it being the low ones again.  `gsram 1024` is the 1 MB card: the ROM lists 31 pages, six tunes go on at start-up and the battle's first tune is streamed, not there at once |
| `gsneo` | the status port as a NeoGS drives it: bits 1-6 the card's last answer rather than libxpeccy's 1s (its FPGA leaves them "don't care"), and a byte left in the latch, as an earlier program's answer on a card that is not reset with the machine.  `make verify` starts the game with it |
| `gsdead` | from now on the sound card takes no command and gives no byte (its status reads "command pending, no data" for ever, its writes are dropped): a real card that has crashed while its mixer plays on.  Tests the game's bounded waits |
| `gswatch ADDR` / `gshits` | count the sound card's instruction fetches at ADDR (hex) from now / print the count: `gswatch 13B9` counts the ROM's music underruns (the interrupt finding the next buffer empty) |
| `peek ADDR [N]` | print N bytes from the CPU address space |
| `state` | PC, SP, the video mode, the clock, the paged-in banks, `$7FFD`, `$EFF7`, the `xx77` shadow |
| `profile` / `profreport` | start and report the cycle profiler |
| `echo TEXT` | print TEXT |

Key names are the ZX keyboard's: `a`..`z`, `0`..`9`, `enter`, `space`,
`caps`, `sym`, the shifted keys the ROM presents as keys of their own
(`up`, `down`, `left`, `right`, `del`, `edit`, `break`, `extend`), and
`kjup`/`kjdown`/`kjleft`/`kjright`/`kjfire` for a Kempston joystick.

The framebuffer is 768x576: two output pixels per source dot horizontally
so the 640-wide text modes come out at their real width, and two output
lines per source line so a screenshot has the right aspect ratio.

## evo-play: the window

```
evo-play --rom F [--gsrom F] [--trd F.trd] [--sd F.img] [--spg F.spg] [--nvram F] [--scale N] [--nosound]
         [--frames N]
```

The PC keyboard is mapped onto the ZX matrix by position; the arrow keys
are the CAPS SHIFT combinations the ROM reads as arrows, Left Shift is CAPS
SHIFT and Left Ctrl is SYMBOL SHIFT.  F12 saves `tmp/evo-shot.bmp`, F5
resets, Ctrl+Q quits.

**Key repeats are dropped.**  libxpeccy counts presses and releases per
matrix bit and only lifts a key when the count reaches zero, so a second
key-down with no release between them holds the key down for ever - and SDL
sends one of those every few tens of milliseconds while a key is held.
`evo-play` ignores `ev.key.repeat`, releases everything when the window
loses focus, and `evo_key` itself ignores a press or a release that does
not change what is held, so no frontend can jam the matrix by accident.

**It keeps the machine's time, not the monitor's.**  A ZX Evolution frame
is 20.36 ms, 49.1 a second.  Each frame is held back until the wall clock
has caught up with the emulated time it covered (`frame_ns`, which
`evo_frame` adds up), and after a stall it counts on from now instead of
racing.  It used to present with vsync and run a frame per refresh: on a
60 Hz monitor the game and the General Sound card both ran 23% fast, and
the sound queue threw away what it could not hold, so the music sounded
rushed.  The sound is kept about 80 ms ahead of the device (`AUDIO_LAG_MS`,
silence to begin with), and a millisecond a frame of pacing either way
keeps it there as the two clocks drift.  `--frames N` quits after N
frames; `EVO_PLAY_STATS=1` prints the frames, the wall time and the
emulated time on exit (500 frames: 10.18 s of each).

`make run` goes through `tools/evo_control.py play`, which supplies the
ROMs and the saved settings.  `--gsrom bin/evo/gs105b.rom` puts the ROM
the real card runs (General Sound 1.05b, the ZX-MultiSound's) in the
emulated card instead of 1.05a; the game's tunes render the same under
both (`sound.md`).

## The profiler

`OUT ($FD),A` with a mark number in A.  The emulator charges the cycles
between one mark and the next to the first of them, and `--profile` or the
script's `profile` command turns it on.  The marks exist only in a
profiling build: `python3 tools/build_dune.py --build-dir build-prof
--profile` defines `PROFILE`, and the `PROF` macro in `src/evo.inc`
assembles to nothing without it.  They must not be in a game build: the
BaseConf decodes a `$7FFD` write on A15 = 0 and the low byte alone
(zports.v), so `OUT ($FD),A` with A below `$80` *is* a `$7FFD` write, and
bit 4 of the value picks the memory manager's register set - a mark below
16 switched every window to the firmware's leftover pages and crashed the
real machine at the battle's first pass, while this emulator, which asked
for A14 = 1 as well, ran on.  `tools/build_toolchain.py` now patches
libxpeccy to decode as the FPGA does, so a stray mark crashes here too -
and so does a profiling build run with the profiler off: the hook
swallows a mark only while it is on, so `profile` goes before `spg` in
the script (or `--profile` on the command line), never after a `run`.
RENDER uses marks 1-19 round its steps and MAIN 20-28 round the battle
pass (`graphics.md` lists them).

## Things that will bite you

- **The firmware's boot menu is a real program** and needs a real four or
  five seconds of emulated time before it takes keys, so a disk boot starts
  with `run 250`.  An SPG loaded with `spg` or `--spg` does not go through
  the firmware and needs no wait (`tools/dune_test.py` runs 5 frames).
- **"TR-DOS boot" wants a file called `boot` of type `B`** and lists what
  it found; the list needs a second ENTER.  `tools/evo_control.py boot`
  does both.
- **The catalog's length fields matter.**  A `B` file whose declared length
  is the padded sector size rather than the real byte count loads trailing
  zeros into the BASIC program and the machine wanders off.
- **A disk is not inserted until the drive says so.**  `loadTRD` fills the
  track data and nothing else; `evo_insert_trd` also has to set `insert`,
  close the door and mark the drive 80-track double-sided.
