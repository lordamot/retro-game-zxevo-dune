#!/usr/bin/env python3
"""dune_data.py - the game's data, text to sjasmplus include files.

    dune_data.py [OUTDIR]          (default build/gen)

Reads only `src/res/data/` - never `orig/`.  Writes:

    tables.inc    every record table and constant table, `tbl_*` labels,
                  record sizes, counts, field offsets and type ids as EQUs
    scripts.inc   the three EMC scripts assembled from `scripts/*.emc`
    missions.inc  the 27 mission record streams and `tbl_missions`
    maps.inc      the 27 battlefields and `tbl_maps`
    text.inc      every string, ended by $FF, and an index table per group:
                  one group per file of `text/` - the cartridge's words, and
                  `port.txt`'s, the port's own (txt_port_*); a
                  Cyrillic letter is encoded by tools/font_cyr.py

## Byte order

The cartridge is big-endian and the Z80 little-endian.  Everything here
comes out little-endian:

    b, sb, hb      a byte
    w, sw, hw      a word, LE
    l, sl, hl      a 32-bit value, LE: the low word first, each word LE
    pos            a position or a (y, x) pair of words: the y word first,
                   then the x word, each LE - the ROM's word order kept,
                   so `+2` is still x (port.md: "a position is still y
                   word then x word")
    str            a ROM pointer to a string: `dw index, 0` where index is
                   the record's number in the text group `txt_<table>_<field>`
    ref:T          a ROM pointer into table T: `dw element, 0` where
                   element is the index of the element it points at, in
                   T's own unit (a word table counts words); `none` (a null
                   pointer) is `dw $FFFF, $FFFF`
    chr            a ROM pointer to a one-letter string: the letter, one byte

So a record table keeps the ROM's offsets exactly; only `chr` shrinks.

## Paging

`missions.inc`, `maps.inc` and `text.inc` are bigger than a 16 KB page.
Each item in them (a mission, a map, a string) is kept inside one page:
the file is laid out as if it starts on a page boundary, and `ds` padding
is put in front of an item that would otherwise cross one.  Include them
at the start of a page with sjasmplus's `MMU <slot> n, <page>` so the
assembler moves on to the next page by itself; the index tables hold
`dw address : db page` (`$$label`), three bytes an entry.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import font_cyr                                   # noqa: E402  (tools/)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src/res/data"
PAGE = 16384

# The port's version, shown top right on the intro screen: `{version}` in
# a text/*.txt string is replaced by it (port.txt's @intro_version).
PORT_VERSION = "2026-09-30"

# ------------------------------------------------------------------ types

SIZE = {"b": 1, "sb": 1, "hb": 1, "w": 2, "sw": 2, "hw": 2,
        "l": 4, "sl": 4, "hl": 4, "pos": 4, "str": 4, "ref": 4, "chr": 4}
PORT_SIZE = dict(SIZE, chr=1)


class DataError(Exception):
    pass


def split_comment(line):
    """The line without its `;` comment, and the comment - quotes kept."""
    q = None
    for i, c in enumerate(line):
        if q:
            if c == "\\":
                continue
            if c == q:
                q = None
        elif c in "\"":
            q = c
        elif c == ";":
            return line[:i], line[i + 1:].strip()
    return line, ""


def tokens(s):
    """Whitespace-separated tokens; a "..." string is one token."""
    out, i, n = [], 0, len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        if s[i] == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            out.append(s[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace():
                j += 1
            out.append(s[i:j])
            i = j
    return out


def unescape(tok):
    """A "..." token to bytes: \\n \\" \\\\ \\xNN, {version} the port's."""
    body = tok[1:-1].replace("{version}", PORT_VERSION)
    out, i = bytearray(), 0
    while i < len(body):
        c = body[i]
        if c == "\\":
            e = body[i + 1]
            if e == "n":
                out.append(10)
                i += 2
            elif e == "x":
                out.append(int(body[i + 2:i + 4], 16))
                i += 4
            else:
                out.append(ord(e))
                i += 2
        else:
            out.append(font_cyr.code(c))
            i += 1
    return bytes(out)


def num(tok):
    """A number: 12, -3, $FF, 'H'."""
    t = tok
    if len(t) == 3 and t[0] == t[2] == "'":
        return ord(t[1])
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    v = int(t[1:], 16) if t.startswith("$") else int(t, 10)
    return -v if neg else v


# ------------------------------------------------------------------ tables

class Field:
    def __init__(self, off, typ, count, name, target, comment):
        self.off, self.typ, self.count = off, typ, count
        self.name, self.target, self.comment = name, target, comment

    @property
    def size(self):
        return SIZE[self.typ] * self.count


class Table:
    def __init__(self, name):
        self.name = name
        self.rom = None
        self.count = None
        self.size = None
        self.anchor = None
        self.prefix = None
        self.idprefix = None
        self.fields = []
        self.records = []          # list of (ident, {name: [tokens]})
        self.data = []             # flat token list, for `data` tables
        self.form = None
        self.doc = []

    @property
    def label(self):
        return "tbl_" + self.name

    def elem_size(self):
        return SIZE[self.fields[0].typ] if len(self.fields) == 1 else self.size


def parse_tables(path):
    tables, t, mode, rec = [], None, None, None
    doc = []
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        if raw.strip().startswith("#"):
            if t is not None and mode is None:
                t.doc.append(raw.strip()[1:].strip())
            continue
        line, com = split_comment(raw)
        s = line.strip()
        if not s:
            continue
        tk = tokens(s)
        try:
            if tk[0] == "table":
                t = Table(tk[1])
                tables.append(t)
                mode = None
            elif mode is None and tk[0] in ("rom", "count", "size", "anchor"):
                setattr(t, tk[0], num(tk[1]))
            elif mode is None and tk[0] in ("prefix", "idprefix"):
                setattr(t, tk[0], tk[1])
            elif mode is None and tk[0] == "field":
                off = num(tk[1])
                typ, _, cnt = tk[2].partition("*")
                name, _, target = tk[3].partition(":")
                if typ.startswith("ref"):
                    typ = "ref"
                if typ not in SIZE:
                    raise DataError(f"unknown type {typ}")
                t.fields.append(Field(off, typ, int(cnt or 1), name,
                                      target or None, com))
            elif tk[0] == "records":
                mode, t.form = "records", "records"
            elif tk[0] == "data":
                mode, t.form = "data", "data"
            elif tk[0] == "end":
                mode, t = None, None
            elif mode == "records" and tk[0] == "record":
                if int(tk[1]) != len(t.records):
                    raise DataError(f"record {tk[1]} out of order")
                rec = {}
                t.records.append((tk[2] if len(tk) > 2 else None, rec))
            elif mode == "records":
                if tk[1] != "=":
                    raise DataError("expected name = values")
                rec[tk[0]] = tk[2:]
            elif mode == "data":
                t.data.extend(tk)
            else:
                raise DataError(f"unexpected {tk[0]}")
        except (DataError, ValueError, IndexError) as e:
            raise DataError(f"{path}:{ln}: {e}") from None
    for t in tables:
        if t.size is None:
            t.size = sum(f.size for f in t.fields)
        if t.count is None and t.form == "data":
            per = sum(f.count for f in t.fields)
            t.count = len(t.data) // per
    return tables


FIRST = ["units", "structures", "houses", "landscape", "actions", "tables"]


def load_tables():
    out = []
    for p in sorted(DATA.glob("*.txt"),
                    key=lambda p: (FIRST.index(p.stem) if p.stem in FIRST
                                   else len(FIRST), p.stem)):
        out += parse_tables(p)
    return {t.name: t for t in out}


def record_values(t):
    """Each record as a list of (field, [tokens]) in field order."""
    out = []
    if t.form == "records":
        for ident, rec in t.records:
            row = []
            for f in t.fields:
                if f.name not in rec:
                    raise DataError(f"{t.name}: record {ident} lacks {f.name}")
                v = rec[f.name]
                if len(v) != f.count:
                    raise DataError(f"{t.name}.{f.name}: {len(v)} values, "
                                    f"want {f.count}")
                row.append((f, v))
            out.append(row)
    else:
        per = sum(f.count for f in t.fields)
        if len(t.data) != per * t.count:
            raise DataError(f"{t.name}: {len(t.data)} values for "
                            f"{t.count} x {per}")
        for r in range(t.count):
            vals = t.data[r * per:(r + 1) * per]
            row, k = [], 0
            for f in t.fields:
                row.append((f, vals[k:k + f.count]))
                k += f.count
            out.append(row)
    if len(out) != t.count:
        raise DataError(f"{t.name}: {len(out)} records, count {t.count}")
    return out


def check_range(v, typ):
    lo, hi = {1: (-128, 255), 2: (-32768, 65535),
              4: (-(1 << 31), (1 << 32) - 1)}[SIZE[typ]]
    if not lo <= v <= hi:
        raise DataError(f"{v} does not fit {typ}")
    return v


def value_port(f, tok, recno, tables):
    """One value as (sjasm directive, operand text, size)."""
    if f.typ in ("b", "sb", "hb", "w", "sw", "hw", "l", "sl", "hl"):
        n = SIZE[f.typ]
        v = check_range(num(tok), f.typ) & ((1 << 8 * n) - 1)
        d = {1: "db", 2: "dw", 4: "dd"}[n]
        return d, (f"${v:0{2 * n}X}" if f.typ[0] == "h" else str(v)), n
    if f.typ == "pos":
        y, x = tok.split(",")
        return "dw", f"{num(y) & 0xFFFF}, {num(x) & 0xFFFF}", 4
    if f.typ == "str":
        if not tok.startswith('"'):
            raise DataError(f"{f.name}: want a string, got {tok}")
        return "dw", f"{recno}, 0", 4
    if f.typ == "ref":
        if tok == "none":
            return "dw", "$FFFF, $FFFF", 4
        if f.target.startswith("@"):         # an index into a ROM table
            return "dw", f"{num(tok)}, 0", 4
        m = re.fullmatch(r"(\w+)\[(\d+)\]", tok)
        if not m or m.group(1) != f.target:
            raise DataError(f"{f.name}: want {f.target}[n], got {tok}")
        if m.group(1) not in tables:
            raise DataError(f"no table {m.group(1)}")
        return "dw", f"{int(m.group(2))}, 0", 4
    if f.typ == "chr":
        return "db", str(num(tok)), 1
    raise DataError(f.typ)


def ident_equ(s):
    return re.sub(r"[^A-Za-z0-9]", "_", s).upper()


def emit_tables(tables):
    out = ["; tables.inc - written by tools/dune_data.py from src/res/data/*.txt.",
           "; Do not edit: change the text and rebuild.  Words are little-endian;",
           "; see the header of tools/dune_data.py for every type.", ""]
    for t in tables.values():
        rows = record_values(t)
        size = sum(PORT_SIZE[f.typ] * f.count for f in t.fields)
        if t.form == "records" and size != t.size:
            raise DataError(f"{t.name}: fields cover {size}, size {t.size}")
        out.append(f"; ---- {t.label}: {t.count} x {size} bytes, from "
                   f"${t.rom:06X}" if t.rom is not None else
                   f"; ---- {t.label}")
        for d in t.doc:
            out.append(f";   {d}")
        if any(f.typ == "pos" for f in t.fields):
            out.append(";   pos: y word then x word, each LE - the ROM's word "
                       "order, not one LE 32-bit value")
        up = t.name.upper()
        out.append(f"{up}_COUNT EQU {t.count}")
        out.append(f"{up}_SIZE EQU {size}")
        base = (t.anchor - t.rom) if t.anchor is not None else 0
        if t.prefix:
            for f in t.fields:
                out.append(f"{t.prefix}{f.name} EQU {f.off - base}"
                           + (f"\t; {f.comment}" if f.comment else ""))
        if t.idprefix and t.form == "records":
            for i, (ident, _) in enumerate(t.records):
                out.append(f"{t.idprefix}{ident_equ(ident)} EQU {i}")
        label = t.label + ("_start" if t.anchor is not None else "")
        out.append(f"{label}:")
        if t.anchor is not None:
            out.append(f"{t.label} EQU {label} + {base}")
        for r, row in enumerate(rows):
            if t.form == "records":
                ident = t.records[r][0]
                out.append(f"\t; {r} {ident or ''}")
                for f, vals in row:
                    parts = [value_port(f, v, r, tables) for v in vals]
                    d = parts[0][0]
                    o = f.off - base
                    out.append(f"\t{d} {', '.join(p[1] for p in parts)}"
                               f"\t; {'-' if o < 0 else '+'}${abs(o):02X}"
                               f" {f.name} ({f.typ})")
        if t.form == "data":
            flat = []
            for r, row in enumerate(rows):
                for f, vals in row:
                    for v in vals:
                        flat.append(value_port(f, v, r, tables))
            line, cur = [], None
            for d, v, _ in flat:
                if d != cur or len(line) >= 16:
                    if line:
                        out.append(f"\t{cur} {', '.join(line)}")
                    line, cur = [], d
                line.append(v)
            if line:
                out.append(f"\t{cur} {', '.join(line)}")
        out.append("")
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- scripts

EMC_OPS = {"goto": 0, "setret": 1, "push.w": 3, "push.b": 4, "push.var": 5,
           "push.loc": 6, "push.arg": 7, "pop.var": 9, "pop.loc": 10,
           "pop.arg": 11, "drop": 12, "reserve": 13, "call": 14,
           "goto-if": 15, "unary": 16, "binary": 17, "return": 18}
EMC_FIXED = {"push.ret": (2, 0), "push.pc": (2, 1), "pop.ret": (8, 0),
             "ret": (8, 1)}
UNARY = ["!", "-", "~"]
BINARY = ["&&", "||", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*",
          "/", ">>", "<<", "&", "|", "%", "^"]


class Script:
    def __init__(self, name):
        self.name = name
        self.funcs = {}         # name -> index
        self.nfuncs = 0
        self.entries = {}       # index -> label
        self.words = []         # big-endian word values, as the ROM has them
        self.labels = {}


def assemble_emc(path):
    """A .emc listing to its bytecode, as big-endian word values."""
    sc = Script(path.stem)
    lines = []
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        line, _ = split_comment(raw)
        s = line.strip()
        if not s:
            continue
        lines.append((ln, s))
    # pass 1: directives, labels, sizes
    pc, body = 0, []
    for ln, s in lines:
        tk = s.split()
        try:
            if tk[0] == ".script":
                sc.name = tk[1]
            elif tk[0] == ".functions":
                sc.nfuncs = int(tk[1])
            elif tk[0] == ".func":
                sc.funcs[tk[2]] = int(tk[1])
            elif tk[0] == ".entry":
                sc.entries[int(tk[1])] = tk[2]
            elif s.endswith(":") and len(tk) == 1:
                if s[:-1] in sc.labels:
                    raise DataError(f"label {s[:-1]} twice")
                sc.labels[s[:-1]] = pc
            else:
                op = tk[0]
                size = 2 if op in ("push.w", "goto-if") else 1
                if op == ".word":
                    size = 1
                body.append((ln, tk, pc))
                pc += size
        except (IndexError, ValueError) as e:
            raise DataError(f"{path}:{ln}: {e}") from None
    # pass 2: encode
    words = []
    for ln, tk, at in body:
        try:
            op, arg = tk[0], tk[1] if len(tk) > 1 else None
            if op == ".word":
                words.append(num(arg) & 0xFFFF)
            elif op in EMC_FIXED:
                o, p = EMC_FIXED[op]
                words.append(0x4000 | o << 8 | p)
            elif op == "goto":
                words.append(0x8000 | sc.labels[arg])
            elif op == "goto-if":
                words += [0x2000 | 15 << 8, 0x8000 | sc.labels[arg]]
            elif op == "push.w":
                words += [0x2000 | 3 << 8, num(arg) & 0xFFFF]
            elif op in EMC_OPS:
                o = EMC_OPS[op]
                if op == "call":
                    p = sc.funcs[arg] if arg in sc.funcs else num(arg)
                elif op == "unary":
                    p = UNARY.index(arg)
                elif op == "binary":
                    p = BINARY.index(arg)
                elif arg is None:
                    p = 0
                else:
                    p = num(arg)
                if not -128 <= p <= 255:
                    raise DataError(f"{p} does not fit a byte")
                words.append(0x4000 | o << 8 | (p & 0xFF))
            else:
                raise DataError(f"unknown instruction {op}")
        except (KeyError, ValueError) as e:
            raise DataError(f"{path}:{ln}: unknown label or value {e}") \
                from None
        if len(words) != at + (2 if tk[0] in ("push.w", "goto-if") else 1):
            raise DataError(f"{path}:{ln}: size mismatch")
    sc.words = words
    missing = [i for i in range(len(sc.entries)) if i not in sc.entries]
    if missing:
        raise DataError(f"{path}: entries {missing} missing")
    for i, lab in sc.entries.items():
        if lab not in sc.labels:
            raise DataError(f"{path}: entry {i} names unknown {lab}")
    return sc


def load_scripts():
    return [assemble_emc(DATA / "scripts" / f"{n}.emc")
            for n in ("unit", "build", "team")]


def emit_scripts(scripts):
    out = ["; scripts.inc - written by tools/dune_data.py from "
           "src/res/data/scripts/*.emc.",
           "; The bytecode is the cartridge's, every 16-bit word little-endian",
           "; (instruction words and their inline parameter words alike).",
           "; emc_X_entries: one word per entry point, the word offset from",
           "; emc_X_code (as the EMC file's ORDR chunk has them).",
           "; EMCF_X_NAME: a script's call index for each routine it can call.",
           ""]
    for sc in scripts:
        n = sc.name.lower()
        up = n.upper()
        out.append(f"EMC_{up}_WORDS EQU {len(sc.words)}")
        out.append(f"EMC_{up}_ENTRIES EQU {len(sc.entries)}")
        out.append(f"EMC_{up}_FUNCS EQU {sc.nfuncs}")
        for name, i in sorted(sc.funcs.items(), key=lambda kv: kv[1]):
            out.append(f"EMCF_{up}_{ident_equ(name.rstrip('?'))}"
                       f"{'_Q' if name.endswith('?') else ''} EQU {i}")
        out.append(f"emc_{n}_entries:")
        for i in range(len(sc.entries)):
            lab = sc.entries[i]
            out.append(f"\tdw {sc.labels[lab]}\t; {i} {lab}")
        out.append(f"emc_{n}_code:")
        for k in range(0, len(sc.words), 16):
            out.append("\tdw " + ", ".join(f"${w:04X}"
                                           for w in sc.words[k:k + 16]))
        out.append("")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- missions

BASIC = {0: "LosePicture", 1: "WinPicture", 2: "BriefPicture",
         3: "Timeout", 4: "MapScale", 5: "CursorPos", 6: "TacticalPos",
         7: "LoseFlags", 8: "WinFlags"}
MAP_KEY = {0x42: "Bloom", 0x46: "Field", 0x53: "Seed"}
SECTION_HOUSE = {2: 0, 3: 1, 4: 2, 5: 4}
HOUSE_KEY = {0x51: "Quota", 0x43: "Credits", 0x42: "Brain", 0x4D: "MaxUnit"}
BEHAVIOUR = dict(zip("NSFKG", ["Normal", "Staging", "Flee", "Kamikaze",
                               "Guard"]))
MOVEMENT = {"F": "Foot", "T": "Tracked", "H": "Harvester", "W": "Wheeled",
            "S": "Slither"}
LOCATION = {6: "Enemybase", 7: "Homebase"}
COMPASS = {0: "N", 32: "NE", 64: "E", 96: "SE", 128: "S", 160: "SW",
           192: "W", 224: "NW"}


def names_of(tables, name):
    return [ident for ident, _ in tables[name].records]


class Names:
    def __init__(self, tables):
        self.unit = names_of(tables, "unit_info")
        self.struct = names_of(tables, "struct_info")
        self.house = names_of(tables, "house_info")
        self.order = names_of(tables, "actions")


def lookup(lst, tok):
    if tok in lst:
        return lst.index(tok)
    return num(tok)


def rev(d, tok):
    for k, v in d.items():
        if v == tok:
            return k
    return num(tok)


def mission_records(path, nm):
    """A mission text to its list of (tag, [words] or bytes)."""
    recs = []
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        line, _ = split_comment(raw)
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        tk = tokens(s)
        try:
            sec = tk[0]
            if sec == "END":
                recs.append(("end", None))
                continue
            if sec == "BASIC":
                key = rev(BASIC, tk[1])
                if key <= 2:
                    name = unescape(tk[2])
                    ln_ = num(tk[3])
                    body = name + bytes(ln_ - len(name))
                    if len(tk) > 4:          # a raw tail after the name
                        body = name + bytes.fromhex(tk[4][4:])
                    if len(body) != ln_:
                        raise DataError("picture length")
                    recs.append((key, [ln_], body))
                else:
                    recs.append((key, [num(tk[2])]))
            elif sec == "MAP":
                key = rev(MAP_KEY, tk[1])
                if key in (0x42, 0x46):
                    ws = [num(x) for x in tk[2:]]
                    recs.append((1 << 8 | key, [len(ws)] + ws))
                else:
                    recs.append((1 << 8 | key, [num(tk[2])]))
            elif sec == "HOUSE":
                h = lookup(nm.house, tk[1])
                secno = rev(SECTION_HOUSE, h) if isinstance(h, int) else h
                key = rev(HOUSE_KEY, tk[2])
                v = num(tk[3]) if key != 0x42 else (
                    ord(tk[3]) if len(tk[3]) == 1 else num(tk[3]))
                recs.append((secno << 8 | key, [v]))
            elif sec == "CHOAM":
                recs.append((6 << 8 | lookup(nm.unit, tk[1]), [num(tk[2])]))
            elif sec == "TEAM":
                key = num(tk[1])
                beh = rev(BEHAVIOUR, tk[3])
                mov = rev(MOVEMENT, tk[4])
                beh = ord(beh) if isinstance(beh, str) else beh
                mov = ord(mov) if isinstance(mov, str) else mov
                recs.append((7 << 8 | key, [lookup(nm.house, tk[2]), beh, mov,
                                            num(tk[5]), num(tk[6])]))
            elif sec == "UNIT":
                key = num(tk[1])
                recs.append((8 << 8 | key, [
                    lookup(nm.house, tk[2]), lookup(nm.unit, tk[3]),
                    num(tk[4]), num(tk[5]), rev(COMPASS, tk[6]),
                    lookup(nm.order, tk[7])]))
            elif sec == "GEN":
                recs.append((9 << 8 | 0x47, [num(tk[1]),
                                             lookup(nm.house, tk[2]),
                                             lookup(nm.struct, tk[3])]))
            elif sec == "STRUCT":
                recs.append((9 << 8 | 0x49, [
                    num(tk[1]), lookup(nm.house, tk[2]),
                    lookup(nm.struct, tk[3]), num(tk[4]), num(tk[5])]))
            elif sec == "REINF":
                key = num(tk[1])
                w = tk[5]
                if w.startswith("$"):
                    when = num(w)
                else:
                    when = int(w.rstrip("+")) << 8 | (0x2B if w.endswith("+")
                                                     else 0)
                recs.append((10 << 8 | key, [
                    lookup(nm.house, tk[2]), lookup(nm.unit, tk[3]),
                    rev(LOCATION, tk[4]), when]))
            elif sec == "RAW":
                recs.append((num(tk[1]), [num(x) for x in tk[2:]]))
            else:
                raise DataError(f"unknown section {sec}")
        except (DataError, ValueError, IndexError) as e:
            raise DataError(f"{path}:{ln}: {e}") from None
    if not recs or recs[-1][0] != "end":
        raise DataError(f"{path}: no END")
    return recs


def encode_mission(recs, big):
    """The record stream: the ROM's (big=True) or the port's."""
    order = "big" if big else "little"
    out = bytearray()
    for r in recs:
        if r[0] == "end":
            out += b"\xff\xff"
            continue
        tag, ws = r[0], r[1]
        out += (tag & 0xFFFF).to_bytes(2, order)
        for w in ws:
            out += (w & 0xFFFF).to_bytes(2, order)
        if len(r) > 2:
            out += r[2]
    return bytes(out)


MISSION_ORDER = [f"SCEN{h}{m:03d}" for h in "HAO" for m in range(1, 10)]


class Packer:
    """Lays items out so none crosses a 16 KB page, from a page start."""

    def __init__(self):
        self.at = 0
        self.lines = []

    def place(self, label, size, body):
        room = PAGE - self.at % PAGE
        if size <= PAGE and size > room:
            self.lines.append(f"\tds {room}\t; to the next page")
            self.at += room
        self.lines.append(f"{label}:")
        self.lines += body
        self.at += size


def db_lines(bs, per=16):
    return [f"\tdb {', '.join(f'${b:02X}' for b in bs[k:k + per])}"
            for k in range(0, len(bs), per)]


def emit_missions(tables):
    nm = Names(tables)
    pk = Packer()
    head = ["; missions.inc - written by tools/dune_data.py from "
            "src/res/data/missions/*.txt.",
            "; Each mission is the cartridge's tagged record stream with every",
            "; word little-endian: tag (low byte key, high byte section), then",
            "; the words the section's handler reads; a picture name is a",
            "; length word and that many bytes; $FFFF ends it.",
            "; tbl_missions: 27 x (dw address, db page), indexed",
            ";   house * 9 + mission - 1, houses 0 Harkonnen, 1 Atreides,",
            ";   2 Ordos (the SCEN file letters H, A, O), missions 1-9.",
            "; Include at the start of a page, with MMU <slot> n, <page>.",
            "", "MISSION_COUNT EQU 27", ""]
    tab = []
    for name in MISSION_ORDER:
        recs = mission_records(DATA / "missions" / f"{name}.txt", nm)
        body = encode_mission(recs, big=False)
        lab = f"mission_{name.lower()}"
        pk.place(lab, len(body), db_lines(body))
        tab.append(f"\tdw {lab}\n\tdb $${lab}")
    pk.place("tbl_missions", 3 * len(tab), tab)
    return "\n".join(head + pk.lines) + "\n"


# -------------------------------------------------------------------- maps

def read_map(path):
    scale, rows = None, []
    for raw in path.read_text().splitlines():
        line, _ = split_comment(raw)
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("scale"):
            scale = int(s.split()[1])
            continue
        rows.append(bytes.fromhex(s))
    if scale not in (32, 64) or len(rows) != scale or \
            any(len(r) != scale for r in rows):
        raise DataError(f"{path}: not a {scale} x {scale} map")
    return scale, b"".join(rows)


def emit_maps():
    maps = []
    for n in range(1, 28):
        scale, body = read_map(DATA / "maps" / f"map{n:02d}.txt")
        maps.append((n, scale, body))
    pk = Packer()
    # the big ones first: 4 KB each, then 1 KB each, so nothing straddles
    for n, scale, body in sorted(maps, key=lambda m: -m[1]):
        pk.place(f"map_{n:02d}", len(body), db_lines(body, 32))
    head = ["; maps.inc - written by tools/dune_data.py from "
            "src/res/data/maps/*.txt.",
            "; A map is a byte a square, a ground icon, row by row: 64 x 64,",
            "; or 32 x 32 for a small one (which covers rows and columns",
            "; 16-47 of the 64 x 64 array).",
            "; tbl_maps: 27 x (dw address, db page, db scale 32|64), by Seed",
            ";   - 1.  Include at the start of a page, MMU <slot> n, <page>.",
            "", "MAP_COUNT EQU 27", ""]
    tab = [f"\tdw map_{n:02d}\n\tdb $$map_{n:02d}, {scale}"
           for n, scale, _ in maps]
    pk.place("tbl_maps", 4 * len(tab), tab)
    return "\n".join(head + pk.lines) + "\n"


# -------------------------------------------------------------------- text

def read_text(path):
    """A text file's strings: [(id, bytes, {attr: value})], and its join."""
    join, items = " ", []
    cur = None
    for ln, raw in enumerate(path.read_text().splitlines(), 1):
        if cur is not None:
            if raw.strip() == "@end":
                ident, attrs, parts = cur
                text = join.join(parts)
                items.append((ident, text_bytes(text, path, ln), attrs))
                cur = None
            else:
                cur[2].append(raw)
            continue
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith(".join"):
            join = {"space": " ", "newline": "\n"}[s.split()[1]]
            continue
        if not s.startswith("@"):
            raise DataError(f"{path}:{ln}: expected @id")
        line, _ = split_comment(s)
        tk = tokens(line)
        ident = tk[0][1:]
        attrs, text = {}, None
        for t in tk[1:]:
            if t.startswith('"'):
                text = unescape(t)
            else:
                k, _, v = t.partition("=")
                attrs[k] = num(v)
        if text is None:
            cur = (ident, attrs, [])
        else:
            items.append((ident, text, attrs))
    if cur is not None:
        raise DataError(f"{path}: @{cur[0]} has no @end")
    return items


def text_bytes(s, path, ln):
    out = bytearray()
    i = 0
    while i < len(s):
        m = re.match(r"\{c(\d+)\}", s[i:])
        if m:
            out += bytes([0xFF, int(m.group(1))])
            i += m.end()
        elif s[i] == "\\" and s[i + 1] == "x":
            out.append(int(s[i + 2:i + 4], 16))
            i += 4
        else:
            out.append(font_cyr.code(s[i]))
            i += 1
    return bytes(out)


def port_string(bs):
    """The ROM's bytes to the port's: $FF n (a colour) becomes $FE n."""
    out = bytearray()
    i = 0
    while i < len(bs):
        if bs[i] == 0xFF:
            out += bytes([0xFE, bs[i + 1]])
            i += 2
        else:
            out.append(bs[i])
            i += 1
    return bytes(out)


def string_db(bs):
    parts, run = [], ""
    for b in bs:
        if 32 <= b < 127 and chr(b) not in '"\\':
            run += chr(b)
            if len(run) >= 60:
                parts.append(f'"{run}"')
                run = ""
        else:
            if run:
                parts.append(f'"{run}"')
                run = ""
            parts.append(f"${b:02X}")
    if run:
        parts.append(f'"{run}"')
    parts.append("$FF")
    lines, cur = [], []
    for p in parts:
        cur.append(p)
        if sum(len(c) for c in cur) > 60:
            lines.append("\tdb " + ", ".join(cur))
            cur = []
    if cur:
        lines.append("\tdb " + ", ".join(cur))
    return lines


def text_groups(tables):
    groups = []
    for p in sorted((DATA / "text").glob("*.txt")):
        items = read_text(p)
        if items:
            groups.append((p.stem, items))
    # the strings the record tables point at
    for t in tables.values():
        for f in t.fields:
            if f.typ != "str":
                continue
            items = []
            for r, row in enumerate(record_values(t)):
                for ff, vals in row:
                    if ff is f:
                        items.append((str(r), unescape(vals[0]), {}))
            groups.append((f"{t.name}_{f.name}", items))
    groups.sort(key=lambda g: sum(len(s) for _, s, _ in g[1]))
    return groups


def emit_text(tables):
    head = ["; text.inc - written by tools/dune_data.py from "
            "src/res/data/text/*.txt",
            "; and the string fields of src/res/data/*.txt.",
            "; A string is its characters as ASCII codes, ended by $FF.",
            "; $0A is a new line; $FE n switches to colour n (the credits).",
            "; txt_<group>: an index table, (dw address, db page) a string.",
            "; txt_<group>_<attr>: a value per string (db, or dw if wide).",
            "; txt_<group>_<id>: each string's own label.",
            "; Include at the start of a page, with MMU <slot> n, <page>.",
            ""]
    pk = Packer()
    groups = text_groups(tables)
    equs = []
    for g, items in groups:
        gl = f"txt_{g}"
        equs.append(f"{gl.upper()}_COUNT EQU {len(items)}")
        for ident, bs, _ in items:
            body = port_string(bs)
            pk.place(f"{gl}_{ident_equ(ident).lower()}", len(body) + 1,
                     string_db(body))
    for g, items in groups:
        gl = f"txt_{g}"
        pk.place(gl, 3 * len(items), [
            f"\tdw {gl}_{ident_equ(i).lower()}\n\tdb $${gl}_{ident_equ(i).lower()}"
            for i, _, _ in items])
        for k in sorted({k for _, _, a in items for k in a}):
            vals = [a.get(k, 0) for _, _, a in items]
            wide = not all(-128 <= v < 256 for v in vals)
            d = "dw" if wide else "db"
            lines = [f"\t{d} " + ", ".join(
                str(v & (0xFFFF if wide else 0xFF)) for v in vals[i:i + 16])
                for i in range(0, len(vals), 16)]
            pk.place(f"{gl}_{k}", len(vals) * (2 if wide else 1), lines)
    return "\n".join(head + equs + [""] + pk.lines) + "\n"


# -------------------------------------------------------------------- main

def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build/gen"
    out.mkdir(parents=True, exist_ok=True)
    try:
        tables = load_tables()
        files = {
            "tables.inc": emit_tables(tables),
            "scripts.inc": emit_scripts(load_scripts()),
            "missions.inc": emit_missions(tables),
            "maps.inc": emit_maps(),
            "text.inc": emit_text(tables),
        }
    except DataError as e:
        raise SystemExit(f"dune_data: {e}")
    for name, body in files.items():
        (out / name).write_text(body)
    print(f"dune_data: {', '.join(files)} -> {out}/")


if __name__ == "__main__":
    main()
