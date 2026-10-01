#!/usr/bin/env python3
"""sega_names.py - check the routine names in orig/sega/res/names/.

    sega_names.py check [FILE...]     every file, or the ones given
    sega_names.py stats               how many routines have a name

The names are text, a block a routine: the address and the name, then
four indented fields, every one of them required -

    $000C32  lcw_unpack
      does:    unpacks a Westwood Format80 stream, as the PC game packs its art
      in:      a0 the stream, a1 where to put it
      out:     -
      affects: d0-d1; the destination buffer

`in` is what the caller has to set up - registers, or stack arguments by
offset (`4(a7).w the unit`) - and `out` where the answer comes back ("-"
for nothing).  `affects` is everything else a call changes: the registers
it does not preserve, the RAM variables it writes, the VDP or the Z80.
A field may run on over further lines indented deeper than the key.

sega_extract.py puts them into the listing: the label becomes the name,
and the four fields go above the routine as a comment.  The extractor
refuses a bad file; this says the same thing without rewriting the
listing, so the files can be worked on while the sources are left alone.

A name has to be an identifier the assembler takes, may not look like the
extractor's own `L_xxxxxx`, is used once across all the files, and has to
sit on the first byte of an instruction in orig/sega/src/.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NAMES = ROOT / "orig/sega/res/names"
SRC = ROOT / "orig/sega/src"
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LINE = re.compile(r"\s+(\S+)\s.*; ([0-9A-F]{6})  [0-9A-F ]+")
RESERVED = {"reset", "VDP_DATA", "VDP_CTRL"}


def instruction_starts():
    out = set()
    for f in sorted(SRC.glob("rom*.asm")):
        for line in f.read_text().splitlines():
            m = LINE.match(line)
            if m and not m.group(1).startswith("dc."):
                out.add(int(m.group(2), 16))
    return out


FIELDS = ("does", "in", "out", "affects")


def read(path):
    """[(line, address, name, {field: text})] - or raise on a malformed
    block.  Missing fields are left out of the dict; check() says so."""
    out, cur, key = [], None, None
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            f = line.split()
            if len(f) != 2 or not f[0].startswith("$"):
                raise SystemExit(f"{path.name}:{n}: want '$ADDRESS name'")
            cur = (n, int(f[0][1:], 16), f[1], {})
            out.append(cur)
            key = None
            continue
        if cur is None:
            raise SystemExit(f"{path.name}:{n}: a field before any routine")
        m = re.match(r"\s+(does|in|out|affects):\s*(.*)$", line)
        if m:
            key = m.group(1)
            if key in cur[3]:
                raise SystemExit(f"{path.name}:{n}: '{key}' twice")
            cur[3][key] = m.group(2).strip()
        elif key:
            cur[3][key] += " " + line.strip()
        else:
            raise SystemExit(f"{path.name}:{n}: not a field: {line.strip()}")
    return out


def load(starts=None, reserved=()):
    """Every block of every file, checked; {address: (name, fields)}.
    Stops with the file and line of the first problem."""
    files = sorted(NAMES.glob("*.txt"))
    bad = problems(files, files, starts, set(reserved))
    if bad:
        raise SystemExit("\n".join(bad[:20]))
    out = {}
    for path in files:
        for _, a, name, fields in read(path):
            out[a] = (name, fields)
    return out


def problems(files, everything, starts, reserved=frozenset()):
    bad, names, addrs = [], {}, {}
    for path in everything:
        for n, a, name, fields in read(path):
            where = f"{path.name}:{n}"
            mine = path in files
            if not IDENT.match(name) or re.match(r"^L_[0-9A-F]{6}$", name) \
                    or name in RESERVED or name in reserved:
                bad.append(f"{where}: '{name}' cannot be a label")
            if name in names and (mine or names[name][1]):
                bad.append(f"{where}: '{name}' is also {names[name][0]}")
            if a in addrs and (mine or addrs[a][1]):
                bad.append(f"{where}: ${a:06X} is also named at {addrs[a][0]}")
            if mine and starts is not None and a not in starts:
                bad.append(f"{where}: ${a:06X} is not an instruction start")
            if mine:
                for k in FIELDS:
                    if not fields.get(k):
                        bad.append(f"{where}: '{name}' has no '{k}'")
            names.setdefault(name, (where, mine))
            addrs.setdefault(a, (where, mine))
    return bad


def check(files):
    everything = sorted(NAMES.glob("*.txt"))
    bad = problems(files, everything, instruction_starts())
    for b in bad:
        print(b)
    n = sum(len(read(p)) for p in everything)
    print(f"{n} routines named in {len(everything)} files, "
          f"{len(bad)} problems")
    return not bad


def stats():
    """How many of the routines something calls have a name."""
    starts = instruction_starts()
    named = {}
    for path in sorted(NAMES.glob("*.txt")):
        for _, a, name, _ in read(path):
            named[name] = a
    calls = set()
    for f in sorted(SRC.glob("rom*.asm")):
        for line in f.read_text().splitlines():
            m = re.match(r"\s+(jsr|bsr\.[sw])\s+(\S+)", line)
            if not m:
                continue
            t = m.group(2).split("(")[0]
            if t.startswith("$") and t.endswith(".w"):
                calls.add(int(t[1:-2], 16))
            elif re.match(r"^L_[0-9A-F]{6}$", t):
                calls.add(int(t[2:], 16))
            elif t in named:
                calls.add(named[t])
    called = calls & starts
    have = set(named.values())
    print(f"{len(have)} routines named; {len(called & have)} of the "
          f"{len(called)} called ones")
    for a in sorted(called - have):
        print(f"  called, not named: ${a:06X}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("files", nargs="*")
    sub.add_parser("stats")
    args = ap.parse_args()
    if args.cmd == "stats":
        stats()
        return
    files = [Path(f).resolve() for f in args.files] or \
        sorted(NAMES.glob("*.txt"))
    sys.exit(0 if check(files) else 1)


if __name__ == "__main__":
    main()
