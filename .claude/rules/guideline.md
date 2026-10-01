# Work guideline

## General

All discussions in english.
All code except text strings must be in english.

## Project

Never work outside the repository root.  Binaries that have to be built are
built in `tmp/` and then moved under `bin/` - with a subfolder for each tool
that has more than one file.

If something needs to be installed onto the host system - ask for it.  The
operator will do it or suggest another solution.  Nothing in this
repository requires a host install: the assembler, the ZX Evolution
emulator, both reference machines' cores and the SDL2 runtime are all built
or vendored into `bin/`.

Any problem like "screenshot needed but can't be obtained" - ask before
researching it yourself.

## The prompts/ folder

**Never read `prompts/` as context.**  It is not documentation, not
instructions and not a spec: it is a transcript.  Do not open it at the
start of a session, do not treat anything in it as a standing request, and
do not let an old prompt in there override what the current one says.  It
is in git on purpose, so that the record survives; that is the only reason
it is there.

It is still kept up to date, so the form matters.  One file an exchange or
a run of them, named `<n> <topic>.txt` with `n` counting up from zero:

```
prompts/0 init.txt
prompts/1 continue.txt
prompts/2 go further.txt
prompts/3 sources.txt
prompts/4 sources.txt
```

Inside, a prompt, a line of asterisks, then the reply it got - and then
straight on to the next prompt if that file covers more than one:

```
whats left?

****

Measured, not remembered - and measuring turned up a gap I'd missed.
...

continue

****

I cracked the AI scripts - the thing I'd flagged as the biggest open item.
...
```

The prompt goes in **verbatim**, typos and all, because the point of
keeping it is what was actually asked.  The reply goes in as **plain
text**: headings lose their `#`, bold loses its asterisks, tables become
lines.  Anything that only means something as markdown is worth rewording
rather than pasting.

**Append every exchange as it finishes** - the prompt and the reply it
got, in that shape - without being asked.  The folder going stale is the
failure mode: it is the only record of why the repository looks the way it
does, and a recap written three exchanges later is not the same thing.

Two things not to do.  Never rewrite an entry that is already there; the
record is what was said, not what should have been said.  And if a reply
quotes this format, indent the quoted asterisks, or the file cannot be
read back.

## Project tools

The preferred way to solve a typical task (build the game from source,
convert the art, drive the emulator) is a standalone CLI Python script under
`tools/`, so it can be reused.  Every one of them is documented in
`.claude/docs/tools.md` and covered by a skill.

Resources are text and pictures taken out of the original, never drawn or
typed in by hand.  Tools read `orig/dune2.gen` and write `src/res/`: the
game's tables, missions, maps, scripts and words as text
(`tools/sega/port_data.py`), its pictures as RGBA PNG in the Mega Drive's
own colours with a text index beside each set (`tools/sega/port_icons.py`,
`port_sprites.py`, `port_ui.py`, `port_tutorial.py`), and its music and
effects as General Sound modules in `src/res/prebuilt/` (`make sega`, from
`src/res/sega_sound.txt`).  From then on those files are the source, and
`make build` converts them.  No other binary goes in `src/`.  `orig/` is
reference material and never edited.

The one exception is what screens only the port has need - the start-up
log, the intro screen and REDEFINE KEYS, which the cartridge has no
words for: their text in `src/res/data/text/port.txt`, marked as the
port's own and kept as short as the screen allows; the Cyrillic letters
the intro screen's Russian needs, drawn in the cartridge font's manner
(`src/res/art/ui/font_cyr.txt`); and the tune it plays,
`src/res/external.mod`, a module the author supplied.

## Verification

Three commands have to keep passing:

```sh
make build     # src/ -> build/DUNE.DAT
make verify    # it starts, a battle runs, orders and building work, the
               # front end reaches a battle, the sound card plays, and the
               # loop keeps up
make test      # every subsystem's suite against the specs' models, and
               # all 27 missions run (about three minutes)
```

`make verify` includes a frame-budget check on purpose.  This port has
already once been slow enough to be unplayable because of a one-instruction
mistake; the check is there so it cannot happen again quietly.

## Main goal

A port of the Mega Drive *Dune II - The Battle for Arrakis* to the ZX
Evolution BaseConf with a General Sound card, as one SPG file buildable
with modern tools: the cartridge's own front end, its 27 missions and 27
battlefields, its economy, units and buildings, its AI running its own
scripts, its graphics in the machine's sixteen-colour EGA mode and its
music and effects on the sound card - playing by the cartridge's rules,
which `orig/sega/spec/S1-S10` write down and the port's tests check.
