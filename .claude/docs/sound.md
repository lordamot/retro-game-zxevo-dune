# Sound

The sound is the Mega Drive Dune II's own: its music and effects, turned
into ProTracker modules and effect samples from what the cartridge's sound
driver tells its chips, and played by the **General Sound card's own ROM**.
Every tune has samples of its own, rendered for it alone.  At power-on,
behind the start-up log, the 36 effects the game plays go to the card and
then every tune it has room for - on a 2 MB card every tune the game plays
but the last mission's finale and the ending's; the rest are kept in the
SPG packed and streamed to the card when they are about to be wanted, and
the card keeps what it has for as long as it has room.

The card the port is played on is a **ZX-MultiSound rev.A1** (UzixLS,
github.com/UzixLS/zx-multisound): General Sound with 1 MB - two Samsung
K6X4008C1F, 512 KB each - and, its README says, a 16 MHz Z80 (the PCBWay
page says 12), beside TurboSound FM, SAA and a SounDrive that *writes*
ports `$0F/$1F/$4F/$5F` (reads of `$1F` are still the Kempston).  **Its
ROM reports 62 pages on that 1 MB** ("GS 2Mb ok" in the log): the ROM's
power-on test marks each page's last byte with its number, from the top
down, and lists the pages that keep their own, which catches a plain
alias of the upper megabyte onto the lower (`bin/evo` with `gsram 1024`:
31 pages) but not whatever this card's CPLD does with the upper pages -
and thirteen tunes loaded into 62 pages landed on each other.  So
`gs_pages` does not take the count on trust: `gs_pages_check` marks
every page the ROM lists at eight places 4 KB apart (`$x010`), reads them
all back once all are marked, and cuts the count at the first page that
does not hold every one of its marks - with the same `$12`/`$14`/`$15`
the tunes go through, so what collides for a tune collides for a mark.
Eight places rather than two because a page bit wired to a line below
A15 lands the upper pages on the lower ones at another offset, and two
marks passed on that card.  And after each page's marks the ROM's page
table (`$4000`, read with `$22`) is compared with what it was: a page
whose marks change it is the ROM's own RAM under another number, the
table is put back and the count stops there.  Its ROM is **General Sound v1.05b** (psbhlw's
gs-firmware; `bin/evo/gs105b.rom`, fetched by `build_toolchain.py`),
which is 63 bytes away from the 1.05a everything here was read from: the
version strings, the `$30` memory pass counting its pages from `$40DA`
instead of `$4080` (so `gs.asm`'s cut of `$4080` to one page does not
shorten it - about 3 s on 1 MB, 6 s on 2 MB, which is why `GS_STALL` is
12 s), and a sample-end reload in the player (`$1147` -> `$1D00`: a
channel whose record's byte +10 is not `$FF` restarts at its loop start)
that changes nothing for the game's records.  The intro and a battle tune
rendered in `bin/evo` under both ROMs differ by 0.6% rms after alignment,
i.e. not at all; `verify_build.py`'s sound checks pass with either.  With
1 MB the card holds 30 pages (`SND_CARD_PAGES` needs 24): the intro, the
title, chosen destiny, evasive action and radnors scheme at start-up, the
rest streamed when wanted - see the start-up walk below.

- `make sega` (`tools/sega/sega_mod.py`): `src/res/sega_sound.txt` ->
  `src/res/prebuilt/music/*.mod`, `src/res/prebuilt/sfx/*.mod` (checked in;
  needs `bin/gen/chiprender`).
- `make build` (`tools/dune_sound.py`): the modules -> the tunes packed,
  the effects, `build/gen/sound.bin` in RAM pages 128 up, and the tables
  `src/gs.asm` uploads, streams and plays from.
- `src/gs.asm`: the host side - upload, the loader, then tunes and effects
  by the cartridge's own numbers (S10).  Called through `snd_effect`,
  `snd_voice`, `snd_music`, `snd_mus`, `snd_sfx` in `src/main/main.asm`,
  and moved on by `snd_bg_pass` (a battle pass) and `snd_idle` (the front
  end's frame and waits, the Tutorial's).  `snd_boot` there puts the set on
  the card behind FRONT's start-up log (`front_boot`), then plays the
  port's intro tune on its intro screen (`front_intro`).

History, in one line: an earlier port played the NES *Sand Emperor* demo's
two tunes, recorded (`tools/nes_sound.py`), through a mixer of its own
uploaded into the card (`src/gs/gsplayer.asm`, clocked by `CARD_RATE` in
`tools/gs_sound.py`), with the AY for effects.  All of that is gone, with
the Mega Drive *recorder* of that era (`tools/sega_sound.py`); git history
has them.

## Talking to the card

Two ports and a handshake:

| | |
|---|---|
| `$B3` | write: a byte to the card.  read: its reply |
| `$BB` | write: a command.  read: the status - bit 7 "a byte is in the data latch", bit 0 "a command has not been taken" |

Three things about the card's own ROM had to be worked out by reading it
(`tools/z80_disasm.py` over `bin/evo/gs105a.rom`; the dispatch table is at
`$0300`), and every one of them is a trap:

- **The first argument goes before the command.**  Every handler starts by
  reading the data latch without waiting, so by the time the command
  arrives its first argument has to be sitting there already.  The second
  and later ones the card asks for one at a time.
- **Not every command can be used.**  A handler is expected to take its
  command port back as soon as it has that first argument; while it has
  not, the card's argument-waiting loop keeps seeing a command pending and
  starts the same handler again from the top, so the *second* argument
  arrives as the first.  `$17` (read a byte by address) is one that does
  not.
- **A block's length goes across as it is, not complemented.**  The card
  complements the pair itself and adds one, turning it into minus the
  length.  Sending it complemented - which looks right - asks for 64 KB
  less than was meant and the card waits for bytes that never come.

And one about the hardware: the card tests its own memory for five to ten
seconds when it powers up, and while it does, the status line flickers.
One clear reading means nothing; `gs_init` waits for it to sit still at
"idle" for 65536 readings, which never happens during the test.

## The Mega Drive's sound, as General Sound modules

`make sega` (`tools/sega/sega_mod.py`) turns the Mega Drive Dune II's
music and effects into ProTracker modules the card's own ROM plays, and
puts them in `src/res/prebuilt/music/` and `src/res/prebuilt/sfx/`.
`src/res/sega_sound.txt` names each one (kind, name, bank, song, and
optionally `tracks=` to say which tracks matter most), and
`src/res/prebuilt/report.txt` says what each conversion kept and lost.

**It works from what the chips were told, never from a recording.**
`tools/sega/sega_driver.py` is the cartridge's Z80 driver as Python: which
note starts on which of the eleven chip channels when, with which
instrument, at which pitch (note, detune and pitch envelope, in 1/256
semitones) and attenuation, and when it is keyed off.  From that:

- every FM instrument is rendered through the Genesis core's own YM2612
  (`bin/gen/chiprender`, the Nuked OPN2) with exactly the registers the
  driver writes, one sample per 36-note band, recorded so a note plays at
  C-2 (8287 Hz), its sustain looped on whole periods;
- a PSG instrument is the chip's square or noise shaped by the driver's
  frame-by-frame envelope; a DAC instrument is the cartridge's sample;
- the notes go onto four channels - a track's own channel if free, else a
  free one, else the least important track's - and a channel is free once
  its note has *died away*, not when its gate says;
- a row is a whole number of music ticks and `BPM` makes the tempo exact:
  the BPM is picked from the card ROM's own table at `$1831`;
- attenuation becomes the note's volume through the driver's own TL
  formula; key-off becomes a volume slide as long as the release; pitch
  envelopes become `1xx`/`2xx` slides.

An effect is rendered whole - every channel, through the same models -
into one sample played once.

**The cartridge is PAL.**  It is the European release (region `E` at
`$1F0`) and the core runs it at 49.70 frames a second with the PAL clocks
(YM2612 7600489 Hz, PSG 3546893 Hz).  Modelled as NTSC, every tune came
out 20% fast.

### Each tune its own samples

`SHARE_TOL` in `sega_mod.py` is **-1**: every song renders the instruments
it plays for itself, recorded in the middle of its own notes and held for
as long as it holds them.  Nothing is shared between tunes.  The modules
are the ones commit 253dfbb had, byte for byte.

Sharing is still there (`Sharing`, `--share N`): songs that play one
instrument within N semitones of a common recording pitch then get the
very same sample, held for the longest either holds a note, each keeping
its own release.  The port used 1 when every tune had to sit on the card
at once (66 distinct instruments made the twenty tunes' 183 samples; 0.95
MB of samples instead of 1.31).  It streams the tunes instead now, so the
setting is only a line to change back, followed by `make sega`.

### How it is checked

- `sega_mod.py` reads every module back, replays its order list, and
  finds each note the driver model placed at its tick, channel, sample and
  note - and fails if it does not;
- the driver model's own full render, set beside the real game recorded
  from the options screen's music test in `bin/gen/retro-run`, lines up at
  zero lag all the way through (onset correlation 0.8-0.9, pitch-class
  similarity 0.8-0.9 on cyrils council, spice trip and the title);
- `tools/gs_modtest.py` plays each module through the card's ROM in
  `bin/evo/evo-run`; all of them load and play.

The loudness balance is the chip model's: the DAC drums sit near full
scale and most FM instruments 15-25 dB below, so a module's drums take
volume 64 and its FM 2-15.

### The card's ROM as a module player

`$30` (load module) answers the module's handle, then takes the module
a byte at a time on the data port until the command `$D2`; `$31`, handle
first, plays it.  One more trap for the list above: `$30` puts the handle
in the latch (`OUT (3)`) and *then* reads the data port (`IN (2)`), and
that read clears the one flag both directions share - so a host that
waits for bit 7 before reading the answer waits for ever.  Read it as soon
as the command has been taken.

The emulator's card runs its 37.5 kHz interrupt about 0.4% fast: BPM 125,
750 interrupts a tick by the ROM's table, measures 0.4% short.  That is
libxpeccy, not the ROM, and the modules are timed for the real card.

## The port's sound: loaded up front, the rest streamed

The Mega Drive port (`.claude/docs/port.md`) ships as one SPG with no
disk.  The effects go to the card once, at start-up, and with them every
tune the card has room for; the rest go when they are wanted, from the
SPG's own pages, packed.  `tools/dune_sound.py` lays the set out and packs it, `src/gs.asm`
uploads, streams and plays it.  The card's own ROM does all the playing:
its ProTracker player for the tunes, its "FX samples" for the effects.

### What the ROM can do (gs105a.rom, read, then tried)

The dispatch: commands below `$20` and from `$F0` up through the word
table at `$0300` (`$F0`-`$FF` as entries `$20`-`$2F`); `$20`-`$EF` through
two byte tables in ROM page 0, low bytes at `$D700`, high at `$D800` (ROM
offsets `$5700`/`$5800`), with page 0 put at `$8000` first.  The ones that
matter here:

| | first argument (before the command) | then | answer |
|---|---|---|---|
| `$12` | page at `$8000` | | |
| `$13` | L | H, then `JP (HL)` | |
| `$14` | length low | length high, address low, high; the bytes | |
| `$15` | length low | length high, address low, high | the bytes, one per read |
| `$22` | index | | the byte at `$4000` + index (the page table is the first 64) |
| `$23` | | | how many 32 KB pages the memory test found |
| `$2A` `$2B` | volume 0-64 | | (module / FX master volume) |
| `$30` | | the module's bytes, then command `$D2` | the handle, flag already cleared |
| `$31` | handle (0 = current) | | the handle, flag **set**: read it |
| `$32` | | | (stop; its own `IN` clears the flag) |
| `$37` | | | free everything |
| `$38` | | the sample's bytes (unsigned), then `$D2` | the handle, flag already cleared |
| `$39` | FX handle (0 = current) | | 0, or `$FF`, flag **set**: read it |
| `$3A` | channel mask | | (stop those effects) |
| `$3E` | 0: bytes are signed, 1: unsigned | as `$38` | as `$38` |
| `$3F` `$41` `$42` | note / volume / finetune | | (of the current FX) |
| `$45` `$46` `$47` | priority / first-choice mask / second mask | | |
| `$80+c` | FX handle | (`$88`: + note, `$90`: + volume) | play on DAC `c`, no choosing |
| `$F3` | | | warm reset: needs page 0 at `$8000` |
| `$F4` | | | cold reset: memory test again |

- **One module, ever.**  `$30` when a module is loaded jumps to the warm
  reset (`$C3E3`), and every effect goes with it.  And the parser works in
  place at *logical address 0*: it reads the header at `$8000` of page
  table entry 0 (`$1AE4`, `$0DB5`), so a module cannot be loaded anywhere
  else either.
- **`$30` makes the whole memory unsigned.**  After parsing it adds `$80`
  to every byte from the samples to the end of the last page (`$0EE1`,
  once, flag `$40B7`): six seconds with 2 MB.  `gs.asm` cuts the page count
  (`$4080`) to 1 for the one `$30` it does.
- **Everything is fetched through the page table.**  The player's sample
  records (`$5400`, 16 bytes each) and the FX records (`$4800` for 1-32,
  `$5900` for 33-60, `$C546`: `cp $3C`) hold *logical* addresses, turned
  into pages through the 64-entry table at `$4000` on every fetch - so a
  module's samples need not follow its patterns, and need not be anywhere
  near them.
- **Memory**: the power-on test finds the pages (`$01C9`, up to 63) and
  lists them at `$4000`; with 2 MB that is 62 (pages 2-63; page 1 is the
  one that aliases `$4000`-`$7FFF`), 1984 KB.  The test itself takes about
  10.5 s with 2 MB, 5 s with 1 MB.
- **Effects over music - yes.**  The FX channels are the four DACs (0, 1
  left; 2, 3 right); the module's four tracker channels are *on* DACs 0,
  2, 3, 1 (LRRL, `$C1A1`).  While an effect plays on a DAC the tracker
  channel there is not mixed (`$0F64`) but keeps its place in the song, and
  comes back when the effect ends.  `$39` picks the DAC (`$C9FA`): one in
  the sample's first mask where neither an effect nor the tune is sounding;
  then, if the sample's priority is `$40` or more, one with no effect
  (taking it from the tune), in the first mask and then the second; then
  the effect of lowest priority, if lower than the new one's; else nothing
  is played.  New samples start at priority `$80`, masks `$0F`, note `$3C`.
- **FX notes**: note 36 is ProTracker's C-1, so the note an effect plays
  at is 36 + its module note (C-3, 16574 Hz, is 60).  The ROM's period
  table is `$6C00` in page 0: 856 x 8 at note 0.
- **The mixing is done in the main loop, not the interrupt.**  The
  interrupt (37.5 kHz, a handler the ROM patches at `$4040`) only sends
  the next sample of the buffer playing to the four DACs.  The main loop
  (`$026E`) takes a pending command, else, while `$4084` says there is
  something to mix and `$4086` does not forbid it, calls the mixer at
  `$CDED`, which fills one buffer of 256 samples a call.  There are eight
  (`$4100`, four bytes each: full flag, page, mode), some 55 ms of sound:
  `$408C` is the one the mixer fills next and `$408E` the one playing
  (both x4), so the mixer is `(($408C - $408E) / 4 - 1) & 7` buffers
  ahead.  When the interrupt finds the next buffer empty (`$13B9`) it
  plays the last one again and clears `$4085`; the mixer starts it again
  (`$14CC`) when it has caught up.  `$4087` is `$FF` while the main loop
  is inside the mixer, `$40A0` the effect channels it is mixing.
- **A command is taken only between two buffers.**  So a command sent
  while a tune plays waits for the buffer being mixed, up to some 7 ms,
  and one that needs more bytes from the host (`$14`) holds the mixing up
  until it has them all.  `$22` needs nothing more: it answers the byte at
  `$4000` + its argument, any of the 256.
- **`$12` is unsafe while anything plays.**  The mixer's code is in the
  ROM's page 0 at `$8000` (`$CDED`), and `$12` puts another page there;
  if the main loop gets round to mixing before the next command it runs
  whatever that page holds.  The ROM's own `$31` and `$39` set `$4086`
  (the main loop's "do not mix") while they work; `gs.asm` does the same
  with a `$14` of one byte around every `$12`.  `$F5`/`$F6` set and clear
  it too, but only when `IXH` bit 7 is clear, which it is not before the
  first tune has played - so `gs.asm` writes the byte itself.
- **`$32` leaves the mixer "active".**  After a stop `$4084` stays set,
  the output stops (`$4085` = 0) and the buffer indices stand still, so a
  lead read then means nothing.
- **A tune keeps a 12 MHz card busy.**  Measured below ("The card's
  time"): 91-100% of the main loop's time goes to mixing any of the
  twenty tunes, and three of them are more than it can do.

### How the port uses it

**On the card.**  A tune is its `$30` image - header and patterns (padded
to 512 bytes), then its samples unsigned - written straight into card
pages; `dune_sound.py` computes the 31 sample records the parser would
have built (`rom_sample_table`, `$0DB1`-`$0EDE` line for line) for a tune
at logical address 0.  Logical pages 0..5 are the tune playing (6, the
largest tune), 6..17 the effects, loaded with `$38` at start-up and never
moved.  Card pages ("slots", indices into the page table the ROM built at
power-on) 0-11 hold the effects; the other 50 of a 2 MB card are a pool:
a tune takes as many as it needs, anywhere.  Starting a tune is:

1. `$32` stop;
2. page table entries 0.. -> its slots' pages (`$14` to `$4000`);
3. song length - 1 and restart (`$415C`), patterns and format (`$419E`),
   its sample records (`$5400`), and the four channel records at `$4600`
   as a fresh `$30` leaves them (read back once with `$15` after the one
   real `$30`, of a silent module, at start-up);
4. `$31` with handle 1.

**In the SPG.**  The effects as they go to the card; every tune packed
(below) - 1.13 MB for 1.98 MB of card images, the intro's with them - in
RAM pages 128-219, and page 220 the unpacker's 16 KB buffer; the
Tutorial's pages (221-223, 0, 4, 6) come straight after, so the set has
no room to grow.

**Start-up** (`snd_boot` in `main.asm`), before the opening, on the
start-up log (below): black, a white line for each check and each thing
that goes to the card, "ok" after it, or "error" - after the machine's
check the start-up stops there for good; after a card check it says "no
sound: press a key to play without", waits for a key and goes on with
the card given up (`sbt_snd`: `gs_abort`, so every `gs_` entry point does
nothing, and the intro and the game play silent).  Everything goes to the
card with nothing playing.

1. `evo_check`, "ZX Evo BaseConf detect": the memory manager puts RAM
   pages `$40`, `$80`, `$C0` and `$FF` into window 3 and each keeps a byte
   of its own - four megabytes, where a smaller machine's pages alias.
2. `gs_probe`, "GS detect": is there a card at all?  Its status register
   reads bits 1-6 as 1 and its ROM clears the command flag (bit 0) first
   thing (`$0148`: `OUT (5)`), and nothing has sent it a command, so 16384
   readings (0.06 s) must all have bits 1-6 set and one at least bit 0
   clear.  With no card the port is not decoded: the bus reads `$FF` (bit
   0 never clear), or - in `bin/evo`, which returns the Evo's port `$FF`
   for it - the floating bus, 0 on the black start-up screen.
   `dbg_flags` bit 3: none of this, no screen, and the opening at 0.12 s.
   Test mode (bit 7): nothing, as ever.
3. "GS memory": `gs_init` waits for the card's memory test (10.9 s from
   power-on in `bin/evo`, nothing on a card long powered), then warm-resets
   it; `gs_pages` asks `$23` for its pages, and the line says the card's
   size - `$23` counts the 32 KB pages the ROM leaves for modules, all but
   its own first (`bin/evo`'s card one fewer still: 62 for 2 MB), so the
   size is that and one more, rounded up to a power of two.  Fewer than
   `SND_CARD_PAGES`: "error", and the silent start.  (`gs_init`'s own
   commands are waited for: the waits give up on `gs_dead`, not on
   `gs_ok`, which `gs_init` clears first.)
4. `gs_setup`, "GS init done, loading": the page table, the silent `$30`,
   the effects' logical pages, and `gs_boot_set`, which takes `snd_start`
   (`BOOT_ORDER`) in order and keeps each that still fits the pages left -
   the port's intro tune first (`MUS_INTRO`, `PORT_MUSIC` in
   `dune_sound.py`: `src/res/external.mod`, a four-channel module as it
   is, 2 card pages), so that it is surely there, then the title, chosen
   destiny (the crests), evasive action (the briefing's end), the three
   mentats' (radnors scheme, cyrils council, ammons advice), the five
   battle tunes, starport (the Tutorial), then the finale, song18 and the
   music test's rarities.  On 2 MB that is the intro and twelve tunes, all
   62 pages - the intro's two push starport out and let the smallest dirge
   in; on 1 MB (30 pages) the intro, the title, chosen destiny, evasive and
   radnors.  The bar comes up.
5. `gs_load_fx`, "Sound effects" (2.4 s): `$38` each, then note, volume,
   priority, DACs (`$38` holds the ROM's mixer until its last byte).
6. `gs_boot_next` / `gs_load_now`, "Music: <name>" a line each (the music
   test's names; the title, the intro and song18 have the port's): the
   intro's, then the rest the least wanted first, the title last, so that
   the most wanted are the newest in the cache - all at full speed, about
   15 s on 2 MB.  The log is done at about 29.5 s from power-on.
7. `front_boot_done`: the bar full a moment, the log fades.  The intro's
   tune starts and `front_intro` fades its screen in: the port's words and
   PRESS ANY KEY, blinking, for as long as it takes - nothing loads under
   the music.  A key (the keyboard's, or the pad's; waited up again, so
   the opening does not see it) fades it out; `gs_intro_done` fades the
   tune out over 16 frames, stops it, and makes the card hold what it
   would have held with no intro: the set `gs_boot_set`'s rule gives
   without it is worked out again, a tune on the card outside it gives its
   pages up and one inside it that is missing goes on at once, whole - on
   2 MB out go the intro and ordos dirge and in comes starport (about 1 s,
   the screen black), on 1 MB in comes ammons advice.  `sound.txt` says
   what for both sizes.  Then the switches go on and the opening starts.

**Why nothing loads under the intro.**  The card mixes a tune in its main
loop and takes a command only between two buffers (next sections), so a
tune it plays and a tune it is given compete for its one Z80.  Under
`external.mod`, with `gs_chunk`'s rules (a chunk only when the mixer is
idle), measured in `bin/evo` with the ROM's underruns counted (`gswatch
13B9` in `evo-run`, `emulator.md`): the song's light opening, its first
7 s, leaves the card about 47 KB/s; the next 15 s about 20; the busy part
after that, which loops, about 6 KB/s - so all 1.43 MB of start-up tunes
under it would take some two minutes, and pushing harder starves the
mixer (40-370 underruns per 5 s in the busy part).  The port once loaded
the last 600 KB under the intro; `bin/evo` counted no underrun, but the
loading was reported to make strange sounds, and it is quicker
anyway to load everything first: the log ends at 29.5 s, where the black
screen alone used to last until 22 s and the loading until 37 s.  The
title tune that follows underruns in the opening as it did before the
intro existed: that is the title's own weight (below), not the loader's.

**A tune is faded before it is stopped from the options screen**
(`gs_music_fade`: the module volume 60, 56 .. 0 over sixteen frames, `$32`,
the volume back): the music switch and the music test's next tune.  `$32`
alone leaves the last note of a channel the next tune does not take
sounding.  The battle's own tune changes (the shuffle) still cut, as the
cartridge's do.

**The switches do not depend on the card.**  `sound_on` and `music_on`
are the cartridge's `soundOn`/`musicOn` (`$0093B6` starts them on), and
`snd_boot` turns them on (not in test mode; after a card's "error" and
the key too): the game's music logic - `musicFramesLeft`, the battle's
draws - runs the same with `dbg_flags` bit 3 as with a card, and only
`gs.asm` (`gs_ok`) knows there is nothing to hear.  So `sound_on` is no
sign that a card was found; `gs_ok` in MAIN's page is.

**The start-up log and the intro's screen** (`front_boot`,
`front_boot_say`, `front_boot_bar`, `front_load_bar`, `front_boot_done`
and `front_intro` in FRONT; the port's own - the cartridge has none):
the log's words are `port.txt`'s `boot_*` in `FA_FONT_INTRO` and the
title's white, a line every 9 pixels from the top, and under them a bar
of the planet's sand on a dark track, 184 pixels, in the title's palette
on black.  `gs.asm` calls `gs_tick` after each effect and chunk it sends;
`gs_tick` in `main.asm` sets the bar by what has been sent, each effect
and each chunk weighed by what it costs (`dune_sound.py`: 6.6 us an
effect byte through `$38`, 5.5 ms a tune's chunk with its unpacking, in
half milliseconds; `gs_up_total` from `gs_boot_set`: the effects and
every start-up tune, the intro's too), so on 2 MB the bar keeps one pace
from end to end.  It never moves back.

It draws with the FRONT library - `fe_prepare`, `fe_ink`/`fe_textn`,
`fe_fill` for a line and the track, `fe_begin` to show the black screen -
and copies each line, and the bar as it grows, straight from the
background onto both screens (`fe_boot_show`): `fe_frame` waits for a
frame and flips, which the loader cannot afford between two chunks, and
the library's fills are 8 pixels wide where the bar moves by one.

**The loader** (`gs.asm`, `gs_bg`/`gs_step`/`gs_chunk`).  A tune on the
card is `gs_tst` 2; a tune no one wants any more keeps its pages - and
plays again without a load - until a load needs them, the one started
longest ago first (`gs_tage`).  The loader fetches, in order: the tune
asked for, if it is not there yet (`gs_wait`); then the list `gs_wants`,
which starting a tune sets to its successors (`SUCCESSORS` in
`dune_sound.py`: the title -> chosen destiny, starport, radnors; a battle
tune -> radnors; the finale -> radnors, song18 ...) and to which the game
adds (`gs_want`): when a battle tune starts, the mentat of the player's
house, and in the last mission the finale.  Nothing draws a battle tune
ahead (below): on 2 MB all five are there from start-up; on a smaller
card one not there streams in, in a silence, when the shuffle draws it.

A step moves one chunk of 512 bytes: unpacked (once) into the buffer at
its place in its 16 KB, then, if the card has time (next section):

    $14: $FF into $4086      mixing held
    $22 x2 or x5             the mixer's state and lead, under the hold
    $12 page, $14 512 bytes  into the tune's card page (the delta undone
                             on the way: each byte the sum so far)
    $12 0                    the ROM's page 0 back at $8000
    $14: 0 into $4086        mixing again

After the last chunk the tune is `gs_tst` 2, and if it is the one asked
for it starts there and then.  Asked for before it is there, the music is
silent meanwhile: `gs_music_play` stops the old tune at once, as the
cartridge would have.

**Who calls it.**  `snd_bg_pass` once a battle pass: one chunk, or three
(`SND_MISS_CHUNKS`) while a tune asked for is waited for; `snd_idle` in the
front end's frame (after `flip_req` is set, before `vf_wait`), its waits
(`fe_wait`) and the Tutorial's (`tu_frames`, `tutw`): up to three chunks
while the frame lasts - none begun once it is over, though one begun late
can run past it - then `halt`.  `snd_idle` keeps every
register but A, as `vid_wait_frame` and `vid_flip` did - their callers
count in B.  Nothing loads with the music switched off.

### The card's time

The ROM mixes in its main loop (above), and on a 12 MHz card a four-channel
tune is nearly all it can do.  Measured in `bin/evo` with no loading at
all, per tune, over 300 frames: the share of time the main loop is inside
the mixer, and the mixer's lead (buffers ready after the one playing, of
7):

| | busy | lead |
|---|---|---|
| most tunes (cyrils, trenching, lego, starport, radnors, evasive, chosen, turbulence, harkonnen rules, slitherin, the dirges, finale, song18) | 0.91-0.98 | 5.3-6.2 on average |
| the title | 0.97 | 0-2 through its middle |
| spice trip, command post | 0.99-1.00 | 0-1, underrunning 2-4% of the time |
| conquest | 0.99 | 0-1 |

The same in the committed build with shared samples (7edff0e): the
overload of spice trip, command post and conquest is the ROM's, not the
streaming's.  A chunk holds the mixing up for about 5 ms; taken while the
mixer is catching up it comes back as a stutter - a buffer played twice,
counted at `$13B9` - often seconds later, in the next heavy passage.  At a
lead of 5 or more, radnors lost 25 ms over 30 s that way; even at 7, 16 ms.
So while a tune plays a chunk goes only when:

- the mixer is idle: a `$22` probe is taken within `GS_PROBE` polls (100
  us) - the main loop takes commands only between buffers, so a quick
  taker has nothing to mix; if it is not taken, its answer is collected
  later (`gs_pend`) and the loader backs off `GS_BACKOFF` calls;
- no effect is being mixed (`$40A0`), nor has one started in the last
  `GS_FX_QUIET` loader calls - an effect onset on a mixer short of lead
  is what stutters;
- the lead is `GS_AHEAD` (4) or more.

With no tune playing, only the lead counts (`GS_AHEAD_FX`, 1: effects only),
and not at all when nothing is mixed (`$4084`) or the output is stopped
(`$4085`, which `$32` leaves).  Counted underruns over 30-60 s, effects
off and fixed: trenching 11 with the loader and 11 without, lego,
turbulence, cyrils, evasive 0 and 0; with an effect a second, trenching 45
against 43 (the ROM's own count moves by that much between two runs), the
rest 0.  What that leaves the loader while a tune plays is a trickle:
0.1-1 KB/s (evasive 0.6, trenching 1.1, radnors 0.05, the title only in its
first seconds), nothing at all during a battle's effects.  On a card with
more time than this one - a faster Z80 - the same rules would let much
more through; they measure, they do not assume.

### The packing

`dune_sound.py` packs each tune's card image: the samples byte-delta coded
(each byte less the one before), the header and patterns not; then a
byte-aligned LZ77 made for a small Z80 unpacker that works a chunk at a
time: `$01`-`$7F` that many literal bytes; `$80`-`$BF` a match of `(T &
$3F) + 3` bytes, offset - 1 in one byte; `$C0`-`$FF` the same with a
two-byte offset (up to 16384); `$00` on to the next 16 KB page (no token
straddles two pages, nor ends on a page's last byte).  Every 512-byte chunk
is whole tokens and every 16 KB block starts afresh, so a chunk unpacks in
place in the 16 KB buffer.  The parse is optimal-ish (a shortest path over
positions, hash-chained candidates), 15 s for the set, cached in
`build/gen/lzcache/`; `unpack()` models the Z80 and every tune is unpacked
and compared on every build.

| | as on the card | packed | |
|---|---|---|---|
| header and patterns | 600 KB | 55 KB | 0.09 |
| samples | 1319 KB | 1041 KB | 0.79 |
| all 20 tunes | 1919 KB | 1096 KB | **0.57** |

(zlib on the same deltas gives 0.47, lzma 0.36; they need an entropy
decoder the Z80 would run at a fraction of the speed.)  `gs_unpack` is 92
bytes and about 36 T-states a byte on these tunes (literal runs and
matches by `LDIR`), 18 400 a chunk; undoing the delta costs 8 more a byte
in the sending loop.

### The battle's music, drawn when the cartridge draws it

`snd_music` is `snd_play_music $00A806`, with a card or without:

- **0** stops the song and leaves `musicFramesLeft` as it is (`$00A812`);
- **music off**: the song stops and `musicFramesLeft` becomes -1, unless
  it is negative already (`$00A8AE`) - so a battle with the music off
  draws a number every pass, as the cartridge's does;
- **a battle track, 8-12**: drawn again with the game's generator while it
  is the tune played last, `$FFC8B8` (`music_last`), which it then becomes
  (`$00A844`-`$00A860`);
- then, if the track has a song, it starts and `musicFramesLeft` becomes
  its length from `$06A8BA` (`$00A894`) - and -1 for every track but the
  battle's five (`snd_track_frames`: `$FFFF`; 0 marks a track with no song,
  which changes nothing, `$00A874`).

`game_battle_loop` sets `musicFramesLeft` to -1 before its first pass
(`$012532`; the port's `battle_loop`), and every pass begins with the
music (`$01253A`, `bl_music`): while it is negative, `c_rand_between(0, 4)
+ 8` and `snd_play_music`.  Those are the only draws a battle pass makes
for the music, in the port as in the cartridge.  So after the briefing's
evasive action (`$1D`, no length) the shuffle starts at the battle's first
pass - evasive plays over the campaign map, and a battle tune from the
first pass.  The port used to wait 3000 frames for it (its own "nothing
timed" fallback), and the streaming work had added a draw one tune ahead
as each tune started (`blm_ahead`), which put the game's generator off the
cartridge's from every battle's start; both are gone.  On the Mega Drive
(`bin/gen/retro-run`, Atreides from the title, work RAM every 10 frames):
after PROCEED `musicFramesLeft` -1 and song 7; at clock 5 of the battle
track 10 (song 3), 7554 frames left of 7560.

`music_last` holds only battle tracks, as `$FFC8B8` does.  What the
mentat's screens asked "is it playing already" of it is `music_track`
now (the port's; the cartridge has `$FFC194`).  And the mentat's tune is
the house's own (`snd_mentat`): `$18` Harkonnen (radnors scheme), `$19`
Atreides (cyrils council), `$1A` Ordos (ammons advice) -
`mentat_house_confirm $01F362`, `mentat_briefing $01F402`; on the Mega
Drive songs 6, 0 and 8 for the three houses.  S10's table has `$19` and
`$1A` as unused, and the port played radnors for everyone.

### Where each tune plays

`snd_music` takes the cartridge's track numbers (`$06A8B8`, S10) and
`gs_track` maps them to tunes; the front end and the battle already ask at
the cartridge's moments.  In `bin/evo`, 2 MB, driven through the game
(power-on, A on every screen, into Atreides 1, then `musicFramesLeft`
poked to 100 to see the shuffle move on):

- power-on: the start-up log to 29.5 s, then the intro's tune and its
  screen until a key, then the opening and the title; START,
  the Atreides crest, YES, PROCEED: chosen destiny, cyrils council,
  evasive, each at once from the card;
- the battle: its first tune at its first pass (the lego tune there) and
  the next when the first runs out (command post), each at once - no
  silence at either: the quietest 20 ms around them is 135 and 145 (AC
  level; silence is under 40, the music 150-1700).  The same flow on the
  old build: evasive for 3000 frames, then 4.8 s of silence for the first
  battle tune, and 0.5-1.4 s gaps after the shuffle's change;
- what streams on 2 MB: the last mission's finale and the ending's song18
  (1.5 s and 2.9 s after they are asked for, measured before this scheme)
  and the options' music test's rarities, about 1.5 s per 100 KB;
- on a 1 MB card (a throwaway build that took 30 pages): the Atreides
  mentat after 2.2 s, and each battle tune the first time after 5-6 s
  without music, the battle's effects still heard over it.

Recorded and set against the card's own `$30` playback of the same module
(`tools/gs_modtest.py`), from each tune's start: the title 24 s, radnors
27 s, evasive 30 s, finale 28 s, song18 44 s, trenching 22 s, lego 40 s -
median correlation 0.995-1.000 per half second, at zero lag (the title
within 1.3 ms); the dips are menu clicks and battle effects.

### The numbers

| | |
|---|---|
| the twenty tunes as the card holds them | 1.92 MB, 69 card pages |
| packed in the SPG | 1.10 MB (0.57) |
| the effects | 374 KB, 36 of the 45 made, card slots 0-11 |
| `sound.bin` | 1.51 MB, RAM pages 128-219; 220 the unpacker's buffer; 221 the Tutorial's first page |
| on the card at start-up, 2 MB | the effects and twelve tunes - the title, chosen destiny, evasive, the three mentats', the five battle tunes, starport: 1.80 MB, 62 of 62 pages (behind the start-up log the intro and ordos dirge instead of starport, which goes on after the intro) |
| on the card at start-up, 1 MB | the effects, the title, chosen destiny, evasive, radnors, ammons: 30 of 30 |
| smallest card | 24 pages: the effects and two of the largest tunes |
| power-on to the opening | the start-up log to 29.5 s in `bin/evo` (10.9 the card's memory test, 2.4 the effects, the rest the intro's tune and the twelve start-up tunes), then the intro's screen until a key, then about 2 s of fades and starport.  It was 39 s with 600 KB loaded under the intro, 29.3 s with no intro, 18.6 with four tunes and 21.5 before that.  No card: "GS detect error", "no sound: press a key to play without", and from the key the intro and the game silent; `dbg_flags` bit 3: 0.12 s |
| a chunk | about 0.2 frame of Z80 time with the card idle (unpack 18 000 T, sending 512 bytes at the card's pace, eleven commands) |
| battle pass, steady | 1.25-1.34 frames with the sound set; the loader 0.006-0.008 of it (probes and backing off) |
| battle pass, a tune waited for | three chunks a pass: +0.7 frame, 2.6-2.8 frames in all in the first battle's opening |
| front end | the frame's idle time: of 90 title and menu frames sampled, 89 the same with and without it, one a frame late (a chunk begun near the frame's end) |

Nine effects are left out by default (`DEFAULT_DROP`, listed in
`build/gen/sound.txt`): no S10 table plays them - the synthesised twins of
sampled effects, `planet_shimmer`, `static_fx`, `explosion1` and the rest.

A tune change costs the Z80 about 15 ms, an effect about 40 us.  With a
four-channel tune and an effect both playing, the card's mixer cannot
quite keep up (the lead above): that is the ROM, not the scheme.

Traps found doing it, beyond the ROM's (above):

- **FCALL hands the callee's registers back.**  `snd_idle` stands in for
  `vid_wait_frame` in loops that count in B; clobbering BC made the fades
  wait hundreds of frames and ate the menu's next key.
- **`gs_chunk`'s last `sbc hl, de` left carry set** on a chunk that went,
  which `gs_bg` read as "not now": one chunk a call.  Every exit says what
  it means with carry.
- **The card's `$22` probe is left pending when it times out**; `gs_sync`
  reads its answer before the next command, like `$39`'s.

### How it was checked

- `dune_sound.py` unpacks every tune through the Z80 unpacker's model and
  compares it with the image before writing anything;
- `bin/evo` flows (title to battle, a won and a lost mission to the next
  battle, the finale and the ending, the Tutorial): the loader's state and
  the card's buffers sampled every 25 frames, underruns counted at `$13B9`
  (a measuring copy of `evo-run`, kept out of the repository), every tune
  on the card compared byte for byte with its image at the end, and the
  recordings set against `gs_modtest.py`'s;
- the song position (`$415A`/`$415B`) against a run without the loader:
  the same tick for tick through the title while the loader probed;
- the game's generator with and without a card: straight into Atreides 1,
  a mailbox call at the start of every pass copying `timer_game` and
  `rnd_seed` (an `LDIR` in the stub), the seeds turned into draw counts:
  the same at every pass for the first 476 passes (clock 1-746).  Then a
  pass with the card takes a frame more - its commands cost time - the
  rotation of loops shifts, and the draws part at clock 749: timing, not
  music.  Before, they parted at the first pass;
- `make verify` checks that the card is found (`gs_ok`), that every tune
  of the start-up set is on it, and that the battle's first tune plays
  from it at once.

### The emulator

libxpeccy gives the card 2 MB but decodes only five bits of its page port,
so its ROM found 30 pages (960 KB).  `tools/evo-emu/evo.c` now wraps the
card's port writes (`gs_page_iwr`) and decodes six: page N, 1-63, is the
RAM's 32 KB block N-1, exactly as before for 1-31.  Nothing else in the
card changes; its memory test now takes 10.5 s instead of 5.

## Adding or changing a sound

1. A line in `src/res/sega_sound.txt` (kind, name, bank, song number -
   `orig/sega/res/sound/music.txt` names the songs through the options
   screen's music and sound tests), then `make sega`.  One module alone:
   `python3 tools/sega/sega_mod.py --only NAME`.
2. `python3 tools/modlib.py src/res/prebuilt/music/NAME.mod` lists it,
   `python3 tools/gs_modtest.py FILE.mod` plays it on the card, and
   `report.txt` says what it kept and dropped.
3. `make build`: `dune_sound.py` packs the tunes and says in
   `build/gen/sound.txt` where everything went, how well each tune packed
   and what goes to the card at start-up on 62 and 30 pages; it fails if
   the set reaches page 221 (the Tutorial's first, `dune_tutorial.TUT_PAGES`) or the effects and two of the
   largest tunes do not fit the card.  A new tune wants a place in
   `BOOT_ORDER` (the order the start-up puts tunes on the card while they
   fit; 1.6 s of start-up per 150 KB) and may want a line in `SUCCESSORS`
   (what the loader fetches while it plays, for a card too small for it).  A new effect
   needs an entry in the S10 maps in `dune_sound.py` if the game is to
   play it by the cartridge's number; `snd_sfx`/`snd_mus` play one by
   `SFX_`/`MUS_` name.  The ids follow the list's order - `front.asm` adds
   to `SFX_YES_SIR` to reach the speech after it, so do not reorder that
   run.
