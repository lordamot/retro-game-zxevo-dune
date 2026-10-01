#!/usr/bin/env python3
"""sega_asm.py - the two-pass 68000 assembler the Mega Drive deconstruction
rebuilds with.

    sega_asm.py SOURCE.asm --out OUT.bin [--expect N]

The twin of `tools/nes/nes_asm.py`, and small for the same reason: it only
has to assemble what `sega_extract.py` writes.  Motorola syntax, `$` hex,
and six directives:

    .org  $000200          set the assembly address
    dc.b  $01,'A'          bytes
    dc.w  $1234,label      big-endian words
    dc.l  $12345678        big-endian longs
    .res  N[,FILL]         N bytes of FILL (default $00)
    .assert-size N         fail unless exactly N bytes came out
    .include "file"        splice another source in
    label:                 a definition; `label = $1234` also works

Labels may be used before they are defined.  The first pass sizes every
instruction with unknown labels standing in as long addresses, exactly as
they are written out, so nothing changes length between the passes; if
something did, the size assertion at the end of each file catches it
rather than letting a wrong ROM through.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m68k import Fail, encode, value_of                    # noqa: E402

LABEL = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.]*):")
EQU = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.]*)\s*=\s*(.+)$")


def _strip_comment(line):
    out, q = "", None
    for c in line:
        if q:
            out += c
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            out += c
        elif c == ";":
            break
        else:
            out += c
    return out.rstrip()


def _split_list(s):
    out, cur, q, depth = [], "", None, 0
    for c in s:
        if q:
            cur += c
            if c == q:
                q = None
            continue
        if c in "'\"":
            q = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if c == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out]


class Lazy(dict):
    """First-pass symbol table: an unknown label reads as a long address in
    the middle of the ROM, so nothing is sized short and then grown."""

    def __init__(self, real):
        super().__init__()
        self.real = real

    def __contains__(self, k):
        return True

    def __getitem__(self, k):
        return self.real.get(k, 0x00080000)

    def get(self, k, default=None):
        return self.real.get(k, 0x00080000)


class Assembler:
    def __init__(self, text, name="<source>", base_dir=None, symbols=None):
        self.name = name
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self.lines = self._expand(text, name)
        # shared on purpose: the cartridge is one address space split over
        # sixteen files, and a JSR in one of them names a label in another
        self.symbols = {} if symbols is None else symbols

    def _expand(self, text, name, depth=0):
        if depth > 8:
            raise Fail(f"{name}: .include nested too deeply")
        out = []
        for raw in text.splitlines():
            line = _strip_comment(raw).strip()
            if line.lower().startswith(".include"):
                p = self.base_dir / line.split(None, 1)[1].strip().strip('"\'')
                out += self._expand(p.read_text(), p.name, depth + 1)
            else:
                out.append(raw)
        return out

    def run(self):
        self._pass(1)
        return self._pass(2)

    def _pass(self, n):
        pc, out, expect = 0, bytearray(), None
        syms = self.symbols if n == 2 else Lazy(self.symbols)
        for lineno, raw in enumerate(self.lines, 1):
            line = _strip_comment(raw).strip()
            if not line:
                continue
            m = EQU.match(line)
            if m and ":" not in line.split("=")[0]:
                try:
                    self.symbols[m.group(1)] = value_of(m.group(2),
                                                        self.symbols, pc)
                except Fail:
                    if n == 2:
                        raise
                continue
            m = LABEL.match(line)
            if m:
                self.symbols[m.group(1)] = pc
                line = line[m.end():].strip()
                if not line:
                    continue
            try:
                emitted = self._stmt(line, pc, syms, strict=(n == 2))
            except (Fail, KeyError, IndexError, ValueError) as e:
                if n == 1:
                    raise Fail(f"{self.name}:{lineno}: {e}") from None
                raise Fail(f"{self.name}:{lineno}: {line}: {e}") from None
            if emitted is None:
                pc = self.pc_after
                continue
            if isinstance(emitted, int):
                expect = emitted
                continue
            if n == 2:
                out += emitted
            pc += len(emitted)
        if n == 2:
            if expect is not None and len(out) != expect:
                raise Fail(f"{self.name}: produced {len(out)} bytes, "
                           f"expected {expect}")
            return bytes(out)
        return None

    def _stmt(self, line, pc, syms, strict=True):
        head, _, rest = line.partition(" ")
        low = head.lower()
        if low == ".org":
            self.pc_after = value_of(rest, self.symbols, pc)
            return None
        if low in ("dc.b", "dc.w", "dc.l"):
            width = {"dc.b": 1, "dc.w": 2, "dc.l": 4}[low]
            b = bytearray()
            for item in _split_list(rest):
                if len(item) > 2 and item[0] == item[-1] == '"':
                    b += item[1:-1].encode("latin1")
                    continue
                v = value_of(item, syms, pc)
                b += (v & ((1 << (8 * width)) - 1)).to_bytes(width, "big")
            return bytes(b)
        if low == ".res":
            parts = _split_list(rest)
            count = value_of(parts[0], self.symbols, pc)
            fill = value_of(parts[1], self.symbols, pc) & 0xFF \
                if len(parts) > 1 else 0
            return bytes([fill]) * count
        if low == ".assert-size":
            return value_of(rest, self.symbols, pc)
        if low == ".include":
            return b""
        return encode(head, rest, pc, syms, strict)


def assemble(text, name="<source>", base_dir=None):
    return Assembler(text, name, base_dir).run()


def assemble_many(sources):
    """Assemble several files as one program.

    `sources` is a list of (name, text, base_dir).  Every label goes into
    one table, because the Mega Drive has one address space: the reset
    vector in `vectors.asm` names a label in `rom00.asm`, and a subroutine
    at $2F000 is called from half the others.  Two rounds, like the two
    passes inside a file - the first measures and collects, the second
    emits.
    """
    symbols = {}
    units = [Assembler(t, n, d, symbols) for n, t, d in sources]
    for u in units:
        u._pass(1)
    return [u._pass(2) for u in units]


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", type=int)
    args = ap.parse_args()
    src = Path(args.source)
    data = assemble(src.read_text(), src.name, src.parent)
    if args.expect is not None and len(data) != args.expect:
        sys.exit(f"sega_asm: {src}: {len(data)} bytes, expected {args.expect}")
    Path(args.out).write_bytes(data)
    print(f"{src} -> {args.out}  {len(data)} bytes  "
          f"sha256 {hashlib.sha256(data).hexdigest()[:16]}")


if __name__ == "__main__":
    main()
