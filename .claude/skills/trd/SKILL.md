---
name: trd
description: TR-DOS disk images - the catalog format, building one, unpacking one, and the boot file. Use when working with a .trd (tools/gs_modtest.py builds one); the game itself ships as an SPG, not a disk.
---

# TR-DOS disks

## The format

640 KB: 80 tracks, two sides, 16 sectors of 256 bytes.  Track 0 is the
catalog (sectors 0-7, sixteen bytes an entry, up to 128 entries) and the
system sector (sector 8).  Files start at track 1 and are stored
contiguously in catalog order.

A catalog entry:

| offset | | |
|---|---|---|
| 0-7 | name, space-padded | |
| 8 | type | `B` BASIC, `C` code, `D` data |
| 9-10 | param1 | `C`: the load address.  `B`: the program's length |
| 11-12 | length | the file's length in bytes |
| 13 | sectors | |
| 14 | start sector | |
| 15 | start track | |

**The length fields matter.**  A `B` file whose declared length is the
padded sector size rather than the real byte count loads trailing zeros
into the BASIC program, and the machine wanders off with no error.

## The tools

```sh
python3 tools/trd_build.py MANIFEST.json OUT.trd --force
python3 tools/trd_unpack.py IMAGE.trd OUTDIR
```

The manifest is `{"label", "disk_type", "files": [{name, type, param1,
length, file}]}`; `tools/gs_modtest.py` writes one and calls the builder.

## Who uses a disk now

Not the game: it ships as one SPG file (`.claude/docs/build.md`), loaded
straight into RAM pages.  The earlier port was a disk - a BASIC `boot`, a
loader and the parts as `C` files - and git history has it.
`tools/gs_modtest.py` still builds a small disk to feed a module to the
General Sound card through BASIC, and `evo-run --trd` boots one through
the firmware (the `evo-emulate` skill).

The firmware's "TR-DOS boot" looks for a file called exactly `boot` of type
`B`.

## The BASIC

A `LOAD` inside a BASIC *program* goes to the tape unless it is executed
through TR-DOS's own entry: `RANDOMIZE USR 15619: REM:` and then the
command, **as tokens**.  On a machine with no tape, getting that wrong is a
blank screen and a hang.  `tools/gs_modtest.py` builds those bytes itself
(`trdos()`); `tools/basic_tokenize.py` is for ordinary BASIC and cannot do
the `REM` trick.
