# The ZX Evolution BaseConf

Everything the port needs to know about the machine, and where it gets it
from.  The authorities are the NedoPC BaseConf documentation, and two
independent emulator implementations that agree with each other:
samstyle/Xpeccy's `src/libxpeccy/hardware/pentevo.c` (which this project's
emulator is built on) and ZEsarUX's `src/machines/baseconf.c`.

## The machine

| | |
|---|---|
| CPU | Z80 at 3.5, 7 or 14 MHz, switchable at run time |
| RAM | 4 MB, in 16 KB pages, through a four-window memory manager |
| ROM | 512 KB of firmware: a boot service, 128 BASIC and TR-DOS |
| Video | a ZX Spectrum ULA plus the ATM Turbo 2+ modes, 16 of 64 colours |
| Sound | TurboSound (two AY-3-8910s) and a General Sound card |
| Disk | Beta Disk interface, TR-DOS, .trd images; an SD card |
| Timing | Pentagon: 71680 T-states a frame at 3.5 MHz, 48.8 Hz |

The game runs it at **14 MHz in the ATM EGA video mode**, which is what the
whole port is arranged around, with every window RAM and the General Sound
card extended to 2 MB.

## The shadow ports

Almost everything below - the video mode, the clock, the memory manager -
lives on *shadow* ports, which only answer when bit 0 of port `$BF` is set,
or while TR-DOS is paged in.  BASIC and TR-DOS both hand control back with
them shut, and nothing says what state an SPG loader leaves them in, so
`src/boot/boot.asm` opens them before anything else and the game never
goes back through the firmware:

```
    ld  a, 1
    out ($BF), a
```

Forgetting this is silent: the `OUT` happens, nothing changes, and the
machine carries on in ZX mode at 7 MHz.  It cost an afternoon here.

Port `$7FFD` is decoded on A15 = 0 and the low byte `$FD` (or `$FC`)
alone, as on a Pentagon: `OUT ($FD),A` with any A below `$80` writes it,
with A as the value.  Bit 4 picks which of the memory manager's two sets
of window registers is live, so such a write with bit 4 clear moves every
window at once.  (The profiler's marks did that; see `emulator.md`.)

The one port that works the other way round is the Kempston joystick,
`$1F`: the manual marks it `noshad`, and it answers **only while the
shadow ports are shut**.  Open, the read is the floppy controller's status
(TR-DOS mode on) or nothing at all - and nothing at all is the byte the
video is fetching, so the pad saw random presses every frame on a real
machine.  `pad_read` (`src/stub/input.asm`) clears bit 0 of `$BF` for the
one `IN`, sets it again straight after, and drops a reading with left and
right or up and down held together.  The manager's and palette's settings
are latched, so the moment shut costs nothing.  The emulator answers the
floppy status there and never showed it.

## Video mode and clock: port `xx77`

Half of what this port says is in the address, not the value:

| | |
|---|---|
| A14 = 0 | the palette port answers.  A14 = 1 and it does not |
| A9 = 1 | TR-DOS mode switches off when code runs from RAM.  A9 = 0 holds it on: port $1F is then the floppy controller's status, not the joystick, and the firmware's virtual-drive trap answers every floppy-port access (the emulator models neither; `PORT_77` is `$8377`) |
| A8 = 1 | the memory manager is on.  A8 = 0 and all four windows are ROM |
| value bits 0-2 | the video mode |
| value bit 3 | 1 = 14 MHz, 0 = 7 MHz |

The modes, with bits 0 and 5 of port `$EFF7` both clear (which is how the
firmware leaves them):

| bits 0-2 | mode |
|---|---|
| 0 | **ATM EGA** - 320x200, 16 colours out of 64 |
| 2 | ATM hardware multicolour |
| 3 | the plain ZX Spectrum screen |
| 6 | ATM text, 80x25 |
| 7 | the firmware's own text mode |

`boot.asm` first writes `$8177` with the plain ZX screen at 14 MHz (the
manager on, the palette port open), and `vid_ega` in `src/stub/video.asm`
switches to EGA, `%00001000`, once there is something to show.

## The screen

ATM EGA is 320x200 in sixteen colours, and its memory is **four planes of
8000 bytes** spread over two RAM pages:

```
plane 0   page A + $0000    pixels 0 and 1 of every group of eight
plane 1   page B + $0000    pixels 2 and 3
plane 2   page A + $2000    pixels 4 and 5
plane 3   page B + $2000    pixels 6 and 7
```

A byte is two pixels, in the ZX attribute byte's wiring reused: **bits 0-2
and bit 6** are the left pixel's colour, **bits 3-5 and bit 7** the right
one's.  Page B is page A xor 4, and bit 3 of port `$7FFD` chooses whether
the video reads pages 1 and 5 or pages 3 and 7 - a free double buffer,
which the game uses everywhere: it draws on the screen not showing and
`vid_flip` asks the frame interrupt to swap them.

The consequences for drawing are in `.claude/docs/graphics.md`.

## The palette

Sixteen entries, each a colour out of 64: two bits a channel, so red, green
and blue are each 0, 1, 2 or 3, coming out as `$00`, `$55`, `$AA`, `$FF`.

Writing one is two ports and a wait:

1. **The index** is the border register.  Only its low three bits come from
   the value; the fourth comes from **address line A3, inverted**.  So
   `OUT ($FE),A` can only reach entries 0-7, and entries 8-15 have to go
   out through port `$F6`, which decodes identically but has A3 low.
2. **The colour** goes to port `$FF`, as `value XOR $FF` with the channel
   bits split across the byte:

   | bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
   |---|---|---|---|---|---|---|---|---|
   | | g0 | r0 | b0 | g1 | - | - | r1 | b1 |

3. **The border latches once a scanline**, so the two writes have to
   straddle a line boundary.  The delay in `vid_palette` is not padding;
   without it all sixteen colours land in one entry.
4. **The write changes the entry of the colour under the beam** (the
   manual, 7.2), which is the border register's colour only while the
   beam is in the border.  So `vid_palette` waits for the frame interrupt
   and writes in the top border, about twenty of its eighty lines.  The
   emulator takes the border register whatever the beam shows, so it
   never showed the difference; on a real machine every screen came out
   in wrong colours that changed from screen to screen, with bands where
   the writes fell.  With interrupts off the routine writes at once.

`tools/dune_art.py` builds the battlefield's sixteen bytes and
`tools/dune_front.py` one set per front-end screen, with the steps of its
fade; `vid_palette` in `src/stub/video.asm` writes whichever it is handed.

## The memory manager

One port per 16 KB window, the window chosen by the port's top two address
bits.  There are two forms, and the short one is only safe after the long
one:

| port | |
|---|---|
| `xx7F7` | "this window is RAM page N", eight bits of page, **inverted** - but it leaves the window's other flags alone, **including the one that says "mix the low bits in from port `$7FFD`"**, which the firmware sets on window 3 |
| `xxFF7` | the full form: bit 7 = mix with `$7FFD`, bit 6 = RAM (else ROM), bits 0-5 = the page, **inverted** |

Six bits of page is 64 pages, one megabyte, and this game uses all 256 -
code in pages 8-23, the art from 40, the sound from 128.  So the port uses
both: `boot.asm` maps windows 0, 1 and 3 once with the full form, which
clears the mixing flag, and MAIN's first instructions do the same for
window 2 (the boot code runs there until then); from then on the stub's
`map_w1`/`map_w3` and the far-call trampoline, for window 0, use the short
form (`MMU_W0`-`MMU_W3` in `src/evo.inc`):

```
    ld  a, page
    cpl
    ld  bc, MMU_W3          ; $F7F7
    out (c), a
```

The short form on its own cost a morning: window 3 kept coming up as page
0 however carefully page 1 was asked for, because the firmware had left
the mixing flag set and `$7FFD` was zero.

There is one more trap: which set of four window registers is live depends
on bit 4 of `$7FFD`.  The firmware leaves it set, so **never write `$7FFD`
with bit 4 clear** - every window would change at once.

## The memory map the game runs in

All four windows are RAM, so `$0038` is the game's own interrupt handler
and IM 1 needs no vector table.  During a battle:

```
$0000-$3FFF  window 0   a code bank (pages 8-23, 122), switched by FCALL
$4000-$7FFF  window 1   UNITS (page 24): units, houses, teams - or an art page
$8000-$BFFF  window 2   WORLD (page 25): structures, tables, globals, stack
$C000-$FFFF  window 3   MAP (page 26) for the logic, a screen page to draw
```

`.claude/docs/port.md` has the whole page map and why it is shaped this
way; `src/pages.inc` is the authority.

## Starting: the SPG

The game is one **SPG** file, the ZX Evolution's paged executable
(`tools/spg.py` writes it; the header and block table are described
there).  The loader puts each block into the RAM page the block table
names, maps the page the header names into window 3, sets the clock and
jumps to the header's PC: page 2 at `$8000`, `src/boot/boot.asm`.  Up to
4 MB can be loaded this way, so there is no disk access after the start.

The project's emulator loads an SPG itself (`--spg F`, or `spg F` in a
script), exactly as libxpeccy's and ZEsarUX's loaders read the format.

The SPG holds only what is not zero: pages it has no block for and the
tail of every page are left as the machine has them, which on a real
machine is random.  `boot.asm` therefore zeroes all of that first, from a
table `tools/build_dune.py` writes into the boot page (`boot_clear_table`),
so the game sees the same RAM as in the emulator, whose RAM starts at
zero.  `fillram SEED` in an emulator script puts random bytes in all 4 MB
to check that (`emulator.md`).

A real machine cannot: the BaseConf firmware (EVO Reset Service) runs
TRD, SCL, FDI and TAP files and treats an .spg as unknown - SPG is a
TS-Conf format.  So the game is delivered as `build/dune.trd` and
`build/DUNE.DAT` in the card's root: the firmware's file browser mounts
the disk and boots it (or `Z.TR-DOS boot` with it mounted as A), its
`boot` loads `src/loader/loader.asm` at `$6000`, and that reads DUNE.DAT
- the SPG under another name - off the card over the SPI port ($xx57 in
shadow mode; the manual's section 9.7), through the FAT16 or FAT32 root
directory and cluster chain, one 512-byte sector at a time with `INIR`,
each block straight into its page through window 3.  It then sets the
windows and SP as an SPG loader would and jumps to `$8000`.  The loader
lives in page 5 at `$6000-$6EFF` (the plain screen's page, which the
game clears anyway), so no block may target page 5, and none may target
#E0-#FF, where the firmware keeps its own resident code.

The emulator still boots the firmware for a TR-DOS disk (`--trd`): its
boot menu's "TR-DOS boot" looks for a file called `boot` of type `B`.  Out
of the box the firmware's drive A is the SD card's *virtual* drive, not the
floppy, so a .trd in drive A is invisible.  The setting lives in the
battery-backed CMOS; `bin/evo/evo-nvram.bin` is a copy with the virtual
drive moved to B and the clock set to 14 MHz, and every tool loads it.
`make nvram` regenerates it.  The game no longer ships as a disk; this is
for other programs (`tools/gs_modtest.py` builds one).

## Sound

Two AY-3-8910s at the usual Spectrum ports - `$FFFD` selects a register,
`$BFFD` writes it - and a General Sound card, which is a whole second Z80
with its own RAM (2 MB here) playing four channels of samples.  The game
uses only the card: every tune and effect is a module its own ROM plays.
`.claude/docs/sound.md` has the details.

## Timing

Pentagon timings: 71680 T-states a frame at 3.5 MHz, so **286720 at 14 MHz**,
48.8 frames a second (3.5 MHz / 71680).  `bin/evo/evo-run --profile` reports where they went;
`make verify` checks the battle loop still keeps up (a pass is about one
frame; the budget is 3).
