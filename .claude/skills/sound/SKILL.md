---
name: sound
description: The sound - the Mega Drive Dune II's music and effects as General Sound modules, and the card's own ROM that plays them. Use when adding a sound, changing the music, or when anything about audio is wrong.
---

# Sound

The music and effects are the Mega Drive's own, converted into ProTracker
modules and effect samples from what its sound driver tells the chips, and
the **General Sound card's own ROM** plays them.  Every tune has its own
samples (nothing shared).  At power-on, behind the start-up log, the 36
effects the game plays and every tune the card has room for go to it (on
2 MB all the game plays but the finale and the ending's); the rest are
kept in the SPG packed and streamed to the card when wanted.  `.claude/docs/sound.md` is the
full account; read it before touching `src/gs.asm` or `tools/dune_sound.py`.

## The pipeline

```sh
make sega                                   # src/res/sega_sound.txt -> src/res/prebuilt/
python3 tools/sega/sega_mod.py --only title # one of them
python3 tools/modlib.py src/res/prebuilt/music/title.mod
python3 tools/gs_modtest.py src/res/prebuilt/music/title.mod   # on the card
make build                                  # dune_sound.py: packs, lays out
cat build/gen/sound.txt                     # what went where, how it packed
```

- `tools/sega/sega_mod.py` makes the modules from the song data through
  `tools/sega/sega_driver.py`, never from a recording;
  `src/res/prebuilt/report.txt` says what each tune kept and dropped.  If a
  tune loses the wrong track, name the ones that matter in its line:
  `music title front 0 tracks=0,3,5`.  The cartridge is PAL.  `SHARE_TOL`
  is -1 (each tune renders its own instruments); `--share N` would share
  samples between tunes again.
- `tools/dune_sound.py` packs each tune's card image (header and patterns,
  then the samples byte-delta coded) with a byte-aligned LZ77 that a 92-byte
  Z80 routine unpacks 512 bytes at a time (0.57 of the size), checks every
  tune unpacks to itself, and writes the sample records the ROM's parser
  would have built.  `BOOT_ORDER` is the order tunes go to the card at
  start-up while they fit (the front end's, the three mentats', the five
  battle tunes, the Tutorial's, ...), `SUCCESSORS` what the loader fetches
  while each tune plays, and the `COST_` constants what the start-up
  log's bar counts in.
- `snd_boot` (`main.asm`) puts up FRONT's start-up log (`front_boot`,
  `front_boot_say`) and writes a line for each step, "ok" or "error"
  (which stops the start-up for good): the machine (`evo_check`), the
  card (`gs_probe`), its memory (`gs_init` waits for its memory test,
  `gs_pages`), `gs_setup`, the effects (`gs_load_fx`), then each start-up
  tune (`gs_boot_next`, `gs_load_now`) - the port's intro tune first
  (`MUS_INTRO`, `src/res/external.mod`, `PORT_MUSIC` in `dune_sound.py`)
  - all with nothing playing, the bar from `gs_tick`.  Then the intro
  plays on its screen (`front_intro`) until a key, nothing loading under
  it, and `gs_intro_done` fades it, frees its pages and puts on the
  start-up tune it kept off.  `dbg_flags` bit 3: none of it, and no
  screen.  The switches `sound_on`/`music_on` go on either way (not in
  test mode), so only `gs_ok` says a card was found.
- `src/gs.asm` uploads the effects (`$38`) and the start-up tunes, then
  `gs_bg` moves the next tune a chunk at a time from the game's loops
  (`snd_bg_pass` in the battle pass, `snd_idle` in the front end's frame and
  waits and the Tutorial's) and `gs_music_play` switches to a tune on the
  card (page table, records, channels, `$31`).  A tune asked for before it
  is there starts after a silence, the moment it arrives.  The game calls
  `snd_effect`, `snd_voice`, `snd_music` (the cartridge's numbers, S10) or
  `snd_mus`/`snd_sfx` (`MUS_`/`SFX_` names) in `src/main/main.asm`.
  `snd_music` is the cartridge's `snd_play_music $00A806` and the battle
  draws its tune only where the cartridge does (`bl_music`, `$01253A`): no
  sound code may draw from the game's generator anywhere else, or the
  game's random numbers part from the cartridge's (and from a run with no
  card).

## The card

Three things about the card's ROM will waste your time if you forget them,
and all three are in the doc: the **first argument goes before the
command**; some commands (`$17`) cannot be used because they do not release
the command port; and a block's **length goes across uncomplemented**.
Two more: `$30`/`$38` answer with the flag already cleared (read the
answer as soon as the command is taken, never wait for bit 7), and
`$31`/`$39` leave theirs with the flag set (read it before sending more).

And the streaming's own: the ROM **mixes in its main loop, from code in its
page 0 at `$8000`**, so a `$12` while anything plays must be wrapped in its
"do not mix" flag (`$4086`, written with `$14`); it **takes a command only
between two 256-sample buffers**; and a 12 MHz card spends 91-100% of its
time mixing a tune, so while one plays the loader only takes the mixer's
idle moments (a `$22` probe taken at once) and nothing while effects mix -
a trickle.  With no tune playing it goes as fast as its caller allows.

## Hearing it

```sh
python3 tools/build_dune.py --build-dir build-snd --house A --mission 1
bin/evo/evo-run --rom bin/evo/zxevo_baseconf.rom --gsrom bin/evo/gs105a.rom \
                --script S        # S: spg build-snd/DUNE.DAT, run 1900,
                                  # wav tmp/battle.wav, run 250, wavstop
```

The intro's tune and its screen come 29.5 s after power-on with a 2 MB
card (10.9 s the card's memory test, 2.4 s the effects, the rest the
tunes), the opening after a key; with no card the log says "GS detect
error" and stops; with `dbg_flags` bit 3 there is no screen (the opening
at 0.12 s).  When it is silent, look at `gs_ok` in page 8 (MAIN; `sound_on`/
`music_on` in WORLD are on without a card too), `gs_nboot`/`gs_boot`
(the start-up set), `gs_cur` (the MUS id
asked for), `gs_wait` (1: waited for, not on the card yet), `gs_ld`/
`gs_ldc` (the tune being loaded, its next chunk), `gs_tst` (per tune: 2 on
the card) and `gs_wants`; `gsmem 0 F` is the card's RAM at `$4000`: the
page table at `$0000`, `$0084`-`$0087` the mixer's flags, `$008C`/`$008E`
its buffer indices, the module's position at `$0159`-`$015B`.  `make
verify` checks that the card is found and loaded and the battle music
plays.
