#!/usr/bin/env python3
"""m68k.py - a matched 68000 disassembler and assembler.

The Mega Drive half of the same bargain the 6502 pair makes on the NES
side: `sega_extract.py` disassembles a region and immediately re-assembles
every instruction it wrote, and anything that does not come back as the
same words is emitted as `dc.w` instead.  `build_sega.py` then rebuilds the
whole 1 MB cartridge and checks its SHA-256, so the disassembly under
`orig/sega/src/` is verified rather than believed.

## One table, both directions

Encodings are written once, as bit patterns, and both the decoder and the
encoder read them.  That is the whole design: a disassembler and an
assembler that disagree are worse than useless on a project whose only
proof is that the bytes come back, so they are not allowed to be two
descriptions of the same thing.

    "0100111001010rrr"  unlk    An

Fixed bits are `0` and `1`; a letter is a field.  Decoding matches the
fixed bits and pulls the fields out; encoding puts them back.  Fields:

    s   size, 00=b 01=w 10=l        z   size, 01=b 11=w 10=l (MOVE)
    m,r EA mode and register        M,R second EA
    d   data register               a   address register
    c   condition code              q   quick data
    v   trap vector                 e   opmode / direction bits

Syntax is Motorola: `move.w $1234(a0,d1.w),d2`, `$` hex, `#` immediate,
`-(an)` and `(an)+`, `label(pc)` for PC-relative.
"""

import re

# ------------------------------------------------------------------ sizes
SIZE_BITS = {0: "b", 1: "w", 2: "l"}
BITS_SIZE = {v: k for k, v in SIZE_BITS.items()}
MOVE_SIZE = {1: "b", 3: "w", 2: "l"}
SIZE_MOVE = {v: k for k, v in MOVE_SIZE.items()}
CC = ["t", "f", "hi", "ls", "cc", "cs", "ne", "eq",
      "vc", "vs", "pl", "mi", "ge", "lt", "gt", "le"]
CC_INDEX = {c: i for i, c in enumerate(CC)}


class Fail(Exception):
    """This word is not an instruction we know how to write down."""


# ------------------------------------------------------------ bit patterns
class Pattern:
    __slots__ = ("mask", "value", "fields", "text")

    def __init__(self, bits):
        if len(bits) != 16:
            raise ValueError(f"pattern {bits!r} is not 16 bits")
        self.mask = self.value = 0
        self.fields = {}
        for i, ch in enumerate(bits):
            bit = 15 - i
            if ch in "01":
                self.mask |= 1 << bit
                self.value |= int(ch) << bit
            else:
                lo, n = self.fields.get(ch, (bit, 0))
                self.fields[ch] = (min(lo, bit), n + 1)
        self.text = bits

    def match(self, word):
        return (word & self.mask) == self.value

    def get(self, word, name):
        lo, n = self.fields[name]
        return (word >> lo) & ((1 << n) - 1)

    def put(self, **kw):
        word = self.value
        for name, v in kw.items():
            lo, n = self.fields[name]
            if v >> n:
                raise Fail(f"{name}={v} does not fit in {n} bits")
            word |= v << lo
        return word


# --------------------------------------------------------------- operands
class EA:
    """An effective address: what it is, and the words that spell it out."""

    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)

    def __repr__(self):
        return f"EA({self.kind}, {self.__dict__})"


def _brief(word):
    """A brief extension word: the index register, its size and a signed
    byte of displacement.

    Bits 10-8 are the 68020's scale factor and must be zero on a 68000, so
    a word with them set is not an instruction we are looking at - it is
    data being read sideways, and saying so here is what keeps it out of
    the listing."""
    if word & 0x0700:
        raise Fail("brief extension word has 68020 bits set")
    reg = (word >> 12) & 7
    is_a = bool(word & 0x8000)
    size = "l" if word & 0x0800 else "w"
    disp = word & 0xFF
    if disp > 127:
        disp -= 256
    return reg, is_a, size, disp


def read_ea(mode, reg, words, pos, size, pc):
    """Decode one effective address, consuming extension words."""
    if mode == 0:
        return EA("d", reg=reg), pos
    if mode == 1:
        return EA("a", reg=reg), pos
    if mode == 2:
        return EA("ind", reg=reg), pos
    if mode == 3:
        return EA("post", reg=reg), pos
    if mode == 4:
        return EA("pre", reg=reg), pos
    if mode == 5:
        d = words[pos]
        pos += 1
        if d > 0x7FFF:
            d -= 0x10000
        return EA("disp", reg=reg, disp=d), pos
    if mode == 6:
        w = words[pos]
        at = pc + pos * 2
        pos += 1
        ix, is_a, isz, d = _brief(w)
        return EA("index", reg=reg, ix=ix, ixa=is_a, ixs=isz, disp=d), pos
    if mode == 7:
        if reg == 0:
            v = words[pos]
            pos += 1
            if v > 0x7FFF:
                v -= 0x10000
            return EA("absw", addr=v), pos
        if reg == 1:
            v = (words[pos] << 16) | words[pos + 1]
            pos += 2
            return EA("absl", addr=v), pos
        if reg == 2:
            d = words[pos]
            at = pc + pos * 2
            pos += 1
            if d > 0x7FFF:
                d -= 0x10000
            return EA("pcdisp", disp=d, target=at + d), pos
        if reg == 3:
            w = words[pos]
            at = pc + pos * 2
            pos += 1
            ix, is_a, isz, d = _brief(w)
            return EA("pcindex", ix=ix, ixa=is_a, ixs=isz, disp=d,
                      target=at + d), pos
        if reg == 4:
            if size == "l":
                v = (words[pos] << 16) | words[pos + 1]
                pos += 2
            else:
                v = words[pos]
                pos += 1
                if size == "b":
                    # a byte immediate still costs a whole word and an
                    # assembler zeroes the half it does not use; anything
                    # else in there means this is data
                    if v & 0xFF00:
                        raise Fail("byte immediate with a dirty high half")
                    v &= 0xFF
            return EA("imm", value=v), pos
    raise Fail(f"effective address {mode}/{reg}")


def ea_text(ea, symbols=None, pc=None):
    k = ea.kind
    if k == "d":
        return f"d{ea.reg}"
    if k == "a":
        return f"a{ea.reg}"
    if k == "ind":
        return f"(a{ea.reg})"
    if k == "post":
        return f"(a{ea.reg})+"
    if k == "pre":
        return f"-(a{ea.reg})"
    if k == "disp":
        return f"{_signed(ea.disp)}(a{ea.reg})"
    if k == "index":
        ir = f"a{ea.ix}" if ea.ixa else f"d{ea.ix}"
        return f"{_signed(ea.disp)}(a{ea.reg},{ir}.{ea.ixs})"
    if k == "absw":
        return f"{_hex(ea.addr)}.w"
    if k == "absl":
        name = symbols.get(ea.addr) if symbols else None
        return name if name else f"{_hex(ea.addr)}.l"
    if k == "pcdisp":
        name = symbols.get(ea.target) if symbols else None
        return f"{name}(pc)" if name else f"{_hex(ea.target)}(pc)"
    if k == "pcindex":
        ir = f"a{ea.ix}" if ea.ixa else f"d{ea.ix}"
        name = symbols.get(ea.target) if symbols else None
        base = name if name else _hex(ea.target)
        return f"{base}(pc,{ir}.{ea.ixs})"
    if k == "imm":
        return f"#{_hex(ea.value)}"
    raise Fail(k)


def _hex(v):
    if v < 0:
        return f"-${-v:X}"
    return f"${v:X}"


def _signed(v):
    return _hex(v)


def ea_words(ea, size, ext_pc=None, strict=True):
    """The extension words an effective address needs, and its mode/reg.

    `ext_pc` is the address the first of those words will sit at, which the
    two PC-relative modes need: what goes in the ROM is the distance from
    that word to the target, so an assembler that does not know where it is
    cannot write one.
    """
    k = ea.kind
    if k == "d":
        return 0, ea.reg, []
    if k == "a":
        return 1, ea.reg, []
    if k == "ind":
        return 2, ea.reg, []
    if k == "post":
        return 3, ea.reg, []
    if k == "pre":
        return 4, ea.reg, []
    if k == "disp":
        return 5, ea.reg, [ea.disp & 0xFFFF]
    if k == "index":
        w = ((ea.ix & 7) << 12) | (0x8000 if ea.ixa else 0) | \
            (0x0800 if ea.ixs == "l" else 0) | (ea.disp & 0xFF)
        return 6, ea.reg, [w]
    if k == "absw":
        return 7, 0, [ea.addr & 0xFFFF]
    if k == "absl":
        return 7, 1, [(ea.addr >> 16) & 0xFFFF, ea.addr & 0xFFFF]
    if k == "pcdisp":
        d = ea.target - ext_pc if ext_pc is not None else ea.disp
        if not -32768 <= d <= 32767:
            if strict:
                raise Fail("pc-relative displacement out of range")
            d = 0
        return 7, 2, [d & 0xFFFF]
    if k == "pcindex":
        d = ea.target - ext_pc if ext_pc is not None else ea.disp
        if not -128 <= d <= 127:
            if strict:
                raise Fail("pc-relative index displacement out of range")
            d = 0
        w = ((ea.ix & 7) << 12) | (0x8000 if ea.ixa else 0) | \
            (0x0800 if ea.ixs == "l" else 0) | (d & 0xFF)
        return 7, 3, [w]
    if k == "imm":
        if size == "l":
            return 7, 4, [(ea.value >> 16) & 0xFFFF, ea.value & 0xFFFF]
        return 7, 4, [ea.value & 0xFFFF]
    raise Fail(k)


# ------------------------------------------------------------------ parser
_EA_RX = [
    ("d", re.compile(r"^d([0-7])$", re.I)),
    ("a", re.compile(r"^(?:a([0-7])|sp)$", re.I)),
    ("post", re.compile(r"^\((?:a([0-7])|sp)\)\+$", re.I)),
    ("pre", re.compile(r"^-\((?:a([0-7])|sp)\)$", re.I)),
    ("ind", re.compile(r"^\((?:a([0-7])|sp)\)$", re.I)),
    ("imm", re.compile(r"^#(.+)$")),
]
_DISP_RX = re.compile(r"^(.*)\((?:a([0-7])|sp)\)$", re.I)
_INDEX_RX = re.compile(r"^(.*)\((?:a([0-7])|sp),\s*([ad])([0-7])\.([wl])\)$", re.I)
_PC_RX = re.compile(r"^(.*)\(pc\)$", re.I)
_PCIX_RX = re.compile(r"^(.*)\(pc,\s*([ad])([0-7])\.([wl])\)$", re.I)
_ABS_RX = re.compile(r"^(.+)\.([wl])$", re.I)


def value_of(expr, symbols, pc):
    """Evaluate an operand expression: $hex, decimal, a label, + and -."""
    expr = expr.strip()
    total, sign, tok = 0, 1, ""

    def term(t):
        t = t.strip()
        if t.startswith("-"):
            return -term(t[1:])
        if not t:
            raise Fail("empty term")
        if t == "*":
            return pc
        if t[0] == "$":
            return int(t[1:], 16)
        if t[0] == "%":
            return int(t[1:], 2)
        if t[0].isdigit():
            return int(t, 10)
        if symbols is not None and t in symbols:
            return symbols[t]
        raise Fail(f"unknown symbol {t!r}")

    for ch in expr:
        if ch in "+-" and tok.strip():
            total += sign * term(tok)
            sign = 1 if ch == "+" else -1
            tok = ""
        else:
            tok += ch
    return total + sign * term(tok)


def parse_ea(s, symbols, pc, size="w"):
    s = s.strip()
    for kind, rx in _EA_RX:
        m = rx.match(s)
        if not m:
            continue
        if kind == "imm":
            return EA("imm", value=value_of(m.group(1), symbols, pc) &
                      (0xFFFFFFFF if size == "l" else
                       0xFFFF if size == "w" else 0xFF))
        reg = 7 if m.group(1) is None else int(m.group(1))
        return EA(kind, reg=reg)
    m = _PCIX_RX.match(s)
    if m:
        target = value_of(m.group(1), symbols, pc)
        return EA("pcindex", ix=int(m.group(3)), ixa=m.group(2).lower() == "a",
                  ixs=m.group(4).lower(), disp=target, target=target)
    m = _PC_RX.match(s)
    if m:
        target = value_of(m.group(1), symbols, pc)
        return EA("pcdisp", disp=target, target=target)
    m = _INDEX_RX.match(s)
    if m:
        reg = 7 if m.group(2) is None else int(m.group(2))
        return EA("index", reg=reg, ix=int(m.group(4)),
                  ixa=m.group(3).lower() == "a", ixs=m.group(5).lower(),
                  disp=value_of(m.group(1), symbols, pc) if m.group(1).strip() else 0)
    m = _DISP_RX.match(s)
    if m:
        reg = 7 if m.group(2) is None else int(m.group(2))
        return EA("disp", reg=reg,
                  disp=value_of(m.group(1), symbols, pc) if m.group(1).strip() else 0)
    m = _ABS_RX.match(s)
    if m:
        v = value_of(m.group(1), symbols, pc)
        return EA("absw" if m.group(2).lower() == "w" else "absl", addr=v)
    return EA("absl", addr=value_of(s, symbols, pc))



# --------------------------------------------------------------- reg lists
def reglist_text(mask, predecrement=False):
    """A MOVEM mask as `d0-d3/a5`.  In the `-(An)` form the bits run the
    other way round, which is the classic way to get this wrong."""
    bits = [(mask >> i) & 1 for i in range(16)]
    if predecrement:
        bits = bits[::-1]
    names = [f"d{i}" for i in range(8)] + [f"a{i}" for i in range(8)]
    out, i = [], 0
    while i < 16:
        if not bits[i]:
            i += 1
            continue
        j = i
        while j + 1 < 16 and bits[j + 1] and (j + 1) // 8 == i // 8:
            j += 1
        out.append(names[i] if i == j else f"{names[i]}-{names[j]}")
        i = j + 1
    return "/".join(out) if out else "0"


def reglist_mask(text, predecrement=False):
    names = {f"d{i}": i for i in range(8)}
    names.update({f"a{i}": 8 + i for i in range(8)})
    names["sp"] = 15
    bits = [0] * 16
    if text.strip() != "0":
        for part in text.split("/"):
            part = part.strip().lower()
            if "-" in part:
                a, b = part.split("-")
                for k in range(names[a.strip()], names[b.strip()] + 1):
                    bits[k] = 1
            else:
                bits[names[part]] = 1
    if predecrement:
        bits = bits[::-1]
    return sum(b << i for i, b in enumerate(bits))


# ------------------------------------------------------------------ decode
class Ins:
    __slots__ = ("addr", "mnem", "size", "ops", "length", "words", "target",
                 "flow")

    def __init__(self, addr, mnem, size, ops, length, words,
                 target=None, flow="next"):
        self.addr, self.mnem, self.size, self.ops = addr, mnem, size, ops
        self.length, self.words = length, words
        self.target, self.flow = target, flow


# Where control goes after each instruction: "next" falls through, "stop"
# does not, "call" and "jump" also name a target, "branch" does both.
FLOW_STOP = {"rts", "rte", "rtr", "jmp", "bra", "illegal", "trap", "stop"}


def alterable(e, data_only=False):
    """Can this effective address be written to?

    The 68000's addressing categories are not decoration: a `move.w d0,d1`
    and a `move.w d0,$1234(pc)` have the same shape but only one of them
    exists, and the difference is the whole reason a blind sweep can tell
    code from data at all.  Rejecting an impossible destination here keeps
    tables and pictures out of the listing.
    """
    if e.kind in ("imm", "pcdisp", "pcindex", "label", "reg"):
        return False
    if data_only and e.kind == "a":
        return False
    return True


def _ea_target(e):
    if e.kind in ("absl", "absw"):
        return e.addr
    if e.kind in ("pcdisp", "pcindex"):
        return e.target
    return None


def decode(mem, pos, org):
    """Decode one instruction at `mem[pos]`, mapped at CPU address `org`.

    Raises Fail for anything not covered - which the caller turns into
    `dc.w`, so an unknown encoding costs readability and never
    correctness.
    """
    addr = org + pos
    if pos + 2 > len(mem):
        raise Fail("ran off the end")
    xw = [int.from_bytes(mem[pos + 2 + i * 2:pos + 4 + i * 2], "big")
          for i in range((min(len(mem) - pos - 2, 20)) // 2)]
    p = 0

    def ea(mode, reg, size):
        nonlocal p
        e, p2 = read_ea(mode, reg, xw, p, size, addr + 2)
        p = p2
        return e

    def done(mnem, size, ops, target=None, flow=None):
        n = 2 + p * 2
        if pos + n > len(mem):
            raise Fail("ran off the end")
        words = [int.from_bytes(mem[pos + i * 2:pos + i * 2 + 2], "big")
                 for i in range(n // 2)]
        if flow is None:
            flow = "stop" if mnem in FLOW_STOP else "next"
        return Ins(addr, mnem, size, ops, n, words, target, flow)

    w = int.from_bytes(mem[pos:pos + 2], "big")
    top, m, r, d = w >> 12, (w >> 3) & 7, w & 7, (w >> 9) & 7
    sz = (w >> 6) & 3

    # ---------------------------------------------------------- line 0
    if top == 0:
        if (w & 0xFF00) in (0x0000, 0x0200, 0x0400, 0x0600, 0x0A00, 0x0C00) \
                and sz != 3:
            mnem = {0x00: "ori", 0x02: "andi", 0x04: "subi", 0x06: "addi",
                    0x0A: "eori", 0x0C: "cmpi"}[w >> 8]
            size = SIZE_BITS[sz]
            if (w & 0xFF) in (0x3C, 0x7C) and mnem in ("ori", "andi", "eori"):
                imm = ea(7, 4, "b" if (w & 0xFF) == 0x3C else "w")
                return done(mnem, "b" if (w & 0xFF) == 0x3C else "w",
                            [imm, EA("reg", name="ccr" if (w & 0xFF) == 0x3C
                                     else "sr")])
            imm = ea(7, 4, size)
            return done(mnem, size, [imm, ea(m, r, size)])
        if (w & 0xF138) == 0x0108:
            size = "l" if w & 0x40 else "w"
            disp = xw[p]
            p += 1
            if disp > 0x7FFF:
                disp -= 0x10000
            slot = EA("disp", reg=r, disp=disp)
            ops = [EA("d", reg=d), slot] if w & 0x80 else [slot, EA("d", reg=d)]
            return done("movep", size, ops)
        if (w & 0xFF00) == 0x0800:
            mnem = ["btst", "bchg", "bclr", "bset"][sz]
            imm = ea(7, 4, "b")
            return done(mnem, "b" if m else "l", [imm, ea(m, r, "b")])
        if (w & 0xF100) == 0x0100:
            mnem = ["btst", "bchg", "bclr", "bset"][sz]
            return done(mnem, "b" if m else "l",
                        [EA("d", reg=d), ea(m, r, "b")])
        raise Fail("line 0")

    # ------------------------------------------------- lines 1, 2, 3: MOVE
    if top in (1, 2, 3):
        size = MOVE_SIZE[top]
        src = ea(m, r, size)
        dm, dr = (w >> 6) & 7, (w >> 9) & 7
        dst = ea(dm, dr, size)
        if not alterable(dst):
            raise Fail("move needs a destination it can write to")
        if size == "b" and (src.kind == "a" or dm == 1):
            raise Fail("byte moves cannot name an address register")
        return done("movea" if dm == 1 else "move", size, [src, dst])

    # ---------------------------------------------------------- line 4
    if top == 4:
        if (w & 0xFFF8) == 0x4E50:
            disp = xw[p]
            p += 1
            if disp > 0x7FFF:
                disp -= 0x10000
            return done("link", "w", [EA("a", reg=r), EA("imm", value=disp)])
        if (w & 0xFFF8) == 0x4E58:
            return done("unlk", None, [EA("a", reg=r)])
        if (w & 0xFFF0) == 0x4E60:
            a, u = EA("a", reg=r), EA("reg", name="usp")
            return done("move", "l", [u, a] if w & 8 else [a, u])
        if (w & 0xFFF0) == 0x4E40:
            return done("trap", None, [EA("imm", value=w & 15)])
        simple = {0x4E70: "reset", 0x4E71: "nop", 0x4E73: "rte",
                  0x4E75: "rts", 0x4E76: "trapv", 0x4E77: "rtr",
                  0x4AFC: "illegal"}
        if w in simple:
            return done(simple[w], None, [])
        if w == 0x4E72:
            return done("stop", None, [ea(7, 4, "w")])
        if (w & 0xFF80) == 0x4E80:
            mnem = "jmp" if w & 0x40 else "jsr"
            dst = ea(m, r, "l")
            tgt = _ea_target(dst)
            if tgt is not None and tgt & 1:
                raise Fail("jump to an odd address")
            return done(mnem, None, [dst], tgt,
                        "jump" if mnem == "jmp" else "call")
        if (w & 0xF1C0) == 0x41C0:
            src = ea(m, r, "l")
            return done("lea", "l", [src, EA("a", reg=d)])
        if (w & 0xF1C0) == 0x4180:
            return done("chk", "w", [ea(m, r, "w"), EA("d", reg=d)])
        if (w & 0xFFF8) == 0x4840:
            return done("swap", "w", [EA("d", reg=r)])
        if (w & 0xFFC0) == 0x4840:
            return done("pea", "l", [ea(m, r, "l")])
        if (w & 0xFFF8) in (0x4880, 0x48C0):
            return done("ext", "w" if w & 0x40 == 0 else "l",
                        [EA("d", reg=r)])
        if (w & 0xFFC0) == 0x4800:
            return done("nbcd", "b", [ea(m, r, "b")])
        if (w & 0xFB80) == 0x4880:
            size = "l" if w & 0x40 else "w"
            mask = xw[p]
            p += 1
            dst = ea(m, r, size)
            if dst.kind in ("d", "a", "imm"):
                raise Fail("movem needs a memory operand")
            if not (w & 0x0400) and dst.kind in ("post", "pcdisp", "pcindex"):
                raise Fail("registers cannot be stored through that mode")
            if (w & 0x0400) and dst.kind == "pre":
                raise Fail("registers cannot be loaded through -(An)")
            regs = EA("regs", mask=mask, pre=(m == 4))
            return done("movem", size,
                        [dst, regs] if w & 0x0400 else [regs, dst])
        if (w & 0xFFC0) == 0x4AC0:
            return done("tas", "b", [ea(m, r, "b")])
        if (w & 0xFF00) == 0x4A00 and sz != 3:
            return done("tst", SIZE_BITS[sz], [ea(m, r, SIZE_BITS[sz])])
        if (w & 0xFF00) in (0x4000, 0x4200, 0x4400, 0x4600):
            if sz == 3:
                if w & 0x0E00 == 0x0000:              # move from sr
                    return done("move", "w", [EA("reg", name="sr"),
                                              ea(m, r, "w")])
                if w & 0x0E00 == 0x0400:              # move to ccr
                    return done("move", "w", [ea(m, r, "w"),
                                              EA("reg", name="ccr")])
                if w & 0x0E00 == 0x0600:              # move to sr
                    return done("move", "w", [ea(m, r, "w"),
                                              EA("reg", name="sr")])
                raise Fail("size 3")
            mnem = {0x40: "negx", 0x42: "clr", 0x44: "neg", 0x46: "not"}[w >> 8]
            dst = ea(m, r, SIZE_BITS[sz])
            if not alterable(dst, data_only=True):
                raise Fail(f"{mnem} needs a data destination")
            return done(mnem, SIZE_BITS[sz], [dst])
        raise Fail("line 4")

    # ----------------------------------------- line 5: ADDQ/SUBQ, Scc, DBcc
    if top == 5:
        if sz == 3:
            cc = CC[(w >> 8) & 15]
            if m == 1:
                disp = xw[p]
                p += 1
                if disp > 0x7FFF:
                    disp -= 0x10000
                tgt = addr + 2 + disp
                if tgt & 1:
                    raise Fail("dbcc to an odd address")
                return done(f"db{cc}", None,
                            [EA("d", reg=r), EA("label", addr=tgt)],
                            tgt, "branch")
            return done(f"s{cc}", "b", [ea(m, r, "b")])
        q = ((w >> 9) & 7) or 8
        mnem = "subq" if w & 0x0100 else "addq"
        size = SIZE_BITS[sz]
        return done(mnem, size, [EA("imm", value=q), ea(m, r, size)])

    # ------------------------------------------------ line 6: Bcc, BSR, BRA
    if top == 6:
        cc = (w >> 8) & 15
        disp = w & 0xFF
        if disp == 0:
            disp = xw[p]
            p += 1
            if disp > 0x7FFF:
                disp -= 0x10000
            tgt = addr + 2 + disp
            suffix = ".w"
            if tgt & 1:
                raise Fail("branch to an odd address")
        elif disp == 0xFF:
            raise Fail("32-bit branch is not 68000")
        else:
            if disp > 127:
                disp -= 256
            tgt = addr + 2 + disp
            suffix = ".s"
            if tgt & 1:
                raise Fail("branch to an odd address")
        mnem = {0: "bra", 1: "bsr"}.get(cc, f"b{CC[cc]}") + suffix
        flow = "call" if cc == 1 else ("jump" if cc == 0 else "branch")
        return done(mnem, None, [EA("label", addr=tgt)], tgt, flow)

    # ----------------------------------------------------- line 7: MOVEQ
    if top == 7:
        if w & 0x0100:
            raise Fail("line 7")
        v = w & 0xFF
        return done("moveq", "l", [EA("imm", value=v - 256 if v > 127 else v),
                                   EA("d", reg=d)])

    # ------------------------------- lines 8, 9, B, C, D: the arithmetic
    if top in (8, 9, 11, 12, 13):
        base = {8: "or", 9: "sub", 11: "cmp", 12: "and", 13: "add"}[top]
        opmode = (w >> 6) & 7
        if opmode in (3, 7):                       # <op>A or MUL/DIV
            if top in (9, 11, 13):
                size = "w" if opmode == 3 else "l"
                return done(base + "a", size,
                            [ea(m, r, size), EA("a", reg=d)])
            mnem = {8: "divu", 12: "mulu"}[top] if opmode == 3 else \
                   {8: "divs", 12: "muls"}[top]
            return done(mnem, "w", [ea(m, r, "w"), EA("d", reg=d)])
        if top == 11 and opmode >= 4:              # EOR or CMPM
            if m == 1:
                return done("cmpm", SIZE_BITS[opmode & 3],
                            [EA("post", reg=r), EA("post", reg=d)])
            size = SIZE_BITS[opmode & 3]
            return done("eor", size, [EA("d", reg=d), ea(m, r, size)])
        if top in (9, 13) and opmode >= 4 and m in (0, 1) and (w & 0x0130) == 0x0100:
            mnem = base[0] + "ubx" if top == 9 else "addx"
            mnem = {"9": "subx"}.get(str(top), mnem)
            mnem = "subx" if top == 9 else "addx"
            size = SIZE_BITS[opmode & 3]
            ops = ([EA("d", reg=r), EA("d", reg=d)] if m == 0 else
                   [EA("pre", reg=r), EA("pre", reg=d)])
            return done(mnem, size, ops)
        if top in (8, 12) and opmode == 4 and m in (0, 1) and (w & 0x01F0) == 0x0100:
            mnem = "sbcd" if top == 8 else "abcd"
            ops = ([EA("d", reg=r), EA("d", reg=d)] if m == 0 else
                   [EA("pre", reg=r), EA("pre", reg=d)])
            return done(mnem, "b", ops)
        # EXG only ever has a register in the low field (mode 0 or 1);
        # with a memory mode the same opmode is AND Dn,<ea> - `and.l
        # d1,(a4)` is $C394, and the game runs it at $024334
        if top == 12 and opmode in (5, 6) and m in (0, 1) and \
                (w & 0x0130) in (0x0100, 0x0110):
            kind = w & 0x00F8
            if kind == 0x0040:
                return done("exg", "l", [EA("d", reg=d), EA("d", reg=r)])
            if kind == 0x0048:
                return done("exg", "l", [EA("a", reg=d), EA("a", reg=r)])
            if kind == 0x0088:
                return done("exg", "l", [EA("d", reg=d), EA("a", reg=r)])
            raise Fail("exg")
        size = SIZE_BITS[opmode & 3]
        if opmode < 3:                             # <ea> op Dn -> Dn
            src = ea(m, r, size)
            if base != "cmp" and size == "b" and src.kind == "a":
                raise Fail("byte operations cannot name an address register")
            return done(base, size, [src, EA("d", reg=d)])
        dst = ea(m, r, size)                       # Dn op <ea> -> <ea>
        if dst.kind in ("d", "a") or not alterable(dst):
            raise Fail("this direction needs a memory destination")
        return done(base, size, [EA("d", reg=d), dst])

    # ------------------------------------------- line E: shifts and rotates
    if top == 14:
        kind = ["as", "ls", "rox", "ro"]
        direction = "l" if w & 0x0100 else "r"
        if sz == 3:
            if w & 0x0800:
                raise Fail("bit 11 is not zero in a memory shift")
            mnem = kind[(w >> 9) & 3] + direction
            dst = ea(m, r, "w")
            if not alterable(dst) or dst.kind in ("d", "a"):
                raise Fail("a memory shift needs a memory destination")
            return done(mnem, "w", [dst])
        mnem = kind[(w >> 3) & 3] + direction
        size = SIZE_BITS[sz]
        count = (w >> 9) & 7
        src = EA("d", reg=count) if w & 0x0020 else \
            EA("imm", value=count or 8)
        return done(mnem, size, [src, EA("d", reg=r)])

    raise Fail(f"line {top:X}")


# -------------------------------------------------------------------- text
def op_text(e, symbols=None):
    if e.kind == "reg":
        return e.name
    if e.kind == "regs":
        return reglist_text(e.mask, e.pre)
    if e.kind == "label":
        name = symbols.get(e.addr) if symbols else None
        return name if name else _hex(e.addr)
    return ea_text(e, symbols)


def text(ins, symbols=None):
    """One instruction as source text."""
    mnem = ins.mnem
    if "." not in mnem and ins.size:
        mnem = f"{mnem}.{ins.size}"
    if not ins.ops:
        return mnem
    return f"{mnem} " + ",".join(op_text(e, symbols) for e in ins.ops)


def split_operands(s):
    """Split on commas outside brackets: `(a0,d1.w)` is one operand."""
    out, cur, depth = [], "", 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out]


# ----------------------------------------------------------------- encode
def _w(v):
    return [v & 0xFFFF]


def _is_reg(s, letter):
    return re.fullmatch(rf"{letter}[0-7]", s.lower()) is not None


ARITH = {"or": 8, "sub": 9, "cmp": 11, "and": 12, "add": 13}
SHIFTS = {"as": 0, "ls": 1, "rox": 2, "ro": 3}


def encode(mnem, operands, pc, symbols=None, strict=True):
    """Encode one instruction at `pc`.  Returns bytes.

    The mirror of `decode`: every branch here answers one there, and
    `sega_extract.py` checks the two agree on each instruction it writes.

    `strict=False` is the assembler's first pass, where labels are not
    known yet: every displacement is in range because none of them is real,
    and nothing here may change an instruction's length on that account.
    """
    mnem = mnem.lower()
    base, _, suffix = mnem.partition(".")
    size = suffix if suffix in ("b", "w", "l") else None
    ops = split_operands(operands) if operands.strip() else []
    esz = size or "w"

    # Where the next extension word will land.  The two PC-relative modes
    # are written as a distance from their own word, so an encoder has to
    # keep count as it goes: opcode first, then any immediate or register
    # mask, then the effective addresses in the order they are written.
    cursor = [pc + 2]

    def _adv(n):
        cursor[0] += 2 * n

    def _mr(e, sz):
        mode, reg, x = ea_words(e, sz, cursor[0], strict)
        _adv(len(x))
        return mode, reg, x

    def parse(i, sz=None):
        return parse_ea(ops[i], symbols, pc, sz or esz)

    # --- no operands
    simple = {"reset": 0x4E70, "nop": 0x4E71, "rte": 0x4E73, "rts": 0x4E75,
              "trapv": 0x4E76, "rtr": 0x4E77, "illegal": 0x4AFC}
    if base in simple and not ops:
        return _pack(_w(simple[base]))

    if base == "trap":
        return _pack(_w(0x4E40 | (value_of(ops[0].lstrip("#"), symbols, pc) & 15)))
    if base == "stop":
        return _pack(_w(0x4E72) + _w(value_of(ops[0].lstrip("#"), symbols, pc)))
    if base == "unlk":
        return _pack(_w(0x4E58 | int(ops[0][1])))
    if base == "link":
        return _pack(_w(0x4E50 | int(ops[0][1])) +
                     _w(value_of(ops[1].lstrip("#"), symbols, pc)))
    if base == "swap":
        return _pack(_w(0x4840 | int(ops[0][1])))
    if base == "ext":
        return _pack(_w((0x48C0 if size == "l" else 0x4880) | int(ops[0][1])))

    # --- branches
    if base in ("bra", "bsr") or (len(base) == 3 and base[0] == "b"
                                  and base[1:] in CC_INDEX):
        cc = {"bra": 0, "bsr": 1}.get(base, CC_INDEX.get(base[1:], -1))
        if cc < 0:
            raise Fail(mnem)
        target = value_of(ops[0], symbols, pc)
        disp = target - (pc + 2)
        if suffix == "s":
            if strict and (not -128 <= disp <= 127 or disp in (0, -1)):
                raise Fail("short branch out of range")
            if not strict:
                disp = 2
            return _pack(_w(0x6000 | (cc << 8) | (disp & 0xFF)))
        if not -32768 <= disp <= 32767:
            if strict:
                raise Fail("branch out of range")
            disp = 0
        return _pack(_w(0x6000 | (cc << 8)) + _w(disp & 0xFFFF))

    # --- DBcc and Scc
    if base.startswith("db") and base[2:] in CC_INDEX:
        cc = CC_INDEX[base[2:]]
        target = value_of(ops[1], symbols, pc)
        disp = target - (pc + 2)
        if not -32768 <= disp <= 32767:
            if strict:
                raise Fail("dbcc out of range")
            disp = 0
        return _pack(_w(0x50C8 | (cc << 8) | int(ops[0][1])) + _w(disp & 0xFFFF))
    if base.startswith("s") and base[1:] in CC_INDEX and len(base) > 1:
        cc = CC_INDEX[base[1:]]
        m, r, x = _mr(parse(0, "b"), "b")
        return _pack(_w(0x50C0 | (cc << 8) | (m << 3) | r) + x)

    # --- MOVEQ
    if base == "moveq":
        v = value_of(ops[0].lstrip("#"), symbols, pc)
        return _pack(_w(0x7000 | (int(ops[1][1]) << 9) | (v & 0xFF)))

    # --- MOVE / MOVEA and the control registers
    if base in ("move", "movea"):
        a, b = ops
        al, bl = a.lower(), b.lower()
        if bl in ("ccr", "sr"):
            m, r, x = _mr(parse(0, "w"), "w")
            head = 0x44C0 if bl == "ccr" else 0x46C0
            return _pack(_w(head | (m << 3) | r) + x)
        if al == "sr":
            m, r, x = _mr(parse(1, "w"), "w")
            return _pack(_w(0x40C0 | (m << 3) | r) + x)
        if bl == "usp":
            return _pack(_w(0x4E60 | int(a[1])))
        if al == "usp":
            return _pack(_w(0x4E68 | int(b[1])))
        src = parse(0)
        dst = parse(1)
        sm, sr, sx = _mr(src, size)
        dm, dr, dx = _mr(dst, size)
        if base == "movea" and dm != 1:
            raise Fail("movea needs an address register")
        return _pack(_w((SIZE_MOVE[size] << 12) | (dr << 9) | (dm << 6) |
                        (sm << 3) | sr) + sx + dx)

    # --- immediates
    imm_ops = {"ori": 0x00, "andi": 0x02, "subi": 0x04, "addi": 0x06,
               "eori": 0x0A, "cmpi": 0x0C}
    if base in imm_ops:
        head = imm_ops[base] << 8
        if ops[1].lower() in ("ccr", "sr"):
            to_sr = ops[1].lower() == "sr"
            v = value_of(ops[0].lstrip("#"), symbols, pc)
            return _pack(_w(head | (0x7C if to_sr else 0x3C)) + _w(v))
        v = value_of(ops[0].lstrip("#"), symbols, pc)
        imm = _w(v) if size != "l" else [(v >> 16) & 0xFFFF, v & 0xFFFF]
        _adv(len(imm))
        m, r, x = _mr(parse(1), size)
        head |= (BITS_SIZE[size] << 6) | (m << 3) | r
        return _pack(_w(head) + imm + x)

    # --- bit operations
    bits = {"btst": 0, "bchg": 1, "bclr": 2, "bset": 3}
    if base in bits:
        k = bits[base]
        if ops[0].startswith("#"):
            v = value_of(ops[0][1:], symbols, pc)
            _adv(1)
            m, r, x = _mr(parse(1, "b"), "b")
            return _pack(_w(0x0800 | (k << 6) | (m << 3) | r) + _w(v) + x)
        m, r, x = _mr(parse(1, "b"), "b")
        return _pack(_w(0x0100 | (int(ops[0][1]) << 9) | (k << 6) |
                        (m << 3) | r) + x)

    # --- one-EA operations
    one = {"negx": 0x4000, "clr": 0x4200, "neg": 0x4400, "not": 0x4600,
           "tst": 0x4A00}
    if base in one:
        m, r, x = _mr(parse(0), size)
        return _pack(_w(one[base] | (BITS_SIZE[size] << 6) | (m << 3) | r) + x)
    plain = {"pea": (0x4840, "l"), "tas": (0x4AC0, "b"), "nbcd": (0x4800, "b"),
             "jsr": (0x4E80, "l"), "jmp": (0x4EC0, "l")}
    if base in plain:
        head, s = plain[base]
        m, r, x = _mr(parse(0, s), s)
        return _pack(_w(head | (m << 3) | r) + x)
    if base == "lea":
        m, r, x = _mr(parse(0, "l"), "l")
        return _pack(_w(0x41C0 | (int(ops[1][1]) << 9) | (m << 3) | r) + x)
    if base == "chk":
        m, r, x = _mr(parse(0, "w"), "w")
        return _pack(_w(0x4180 | (int(ops[1][1]) << 9) | (m << 3) | r) + x)

    # --- MOVEM
    if base == "movem":
        to_regs = _is_movem_dest_regs(ops)
        ea_str = ops[0] if to_regs else ops[1]
        lst = ops[1] if to_regs else ops[0]
        e = parse_ea(ea_str, symbols, pc, size)
        _adv(1)                                   # the register mask word
        m, r, x = _mr(e, size)
        mask = reglist_mask(lst, e.kind == "pre")
        head = 0x4880 | (0x0400 if to_regs else 0) | \
            (0x40 if size == "l" else 0) | (m << 3) | r
        return _pack(_w(head) + _w(mask) + x)

    # --- MOVEP
    if base == "movep":
        to_mem = ops[0].lower().startswith("d") and _is_reg(ops[0], "d")
        reg = int((ops[0] if to_mem else ops[1])[1])
        slot = parse_ea(ops[1] if to_mem else ops[0], symbols, pc, size)
        head = 0x0108 | (reg << 9) | (0x80 if to_mem else 0) | \
            (0x40 if size == "l" else 0) | slot.reg
        return _pack(_w(head) + _w(slot.disp & 0xFFFF))

    # --- ADDQ / SUBQ
    if base in ("addq", "subq"):
        v = value_of(ops[0].lstrip("#"), symbols, pc)
        m, r, x = _mr(parse(1), size)
        return _pack(_w(0x5000 | (0x0100 if base == "subq" else 0) |
                        ((v & 7) << 9) | (BITS_SIZE[size] << 6) |
                        (m << 3) | r) + x)

    # --- the multiply/divide pairs
    md = {"divu": (8, 3), "divs": (8, 7), "mulu": (12, 3), "muls": (12, 7)}
    if base in md:
        line, opmode = md[base]
        m, r, x = _mr(parse(0, "w"), "w")
        return _pack(_w((line << 12) | (int(ops[1][1]) << 9) | (opmode << 6) |
                        (m << 3) | r) + x)

    # --- the BCD and extend pairs
    pairs = {"sbcd": (8, 0x0100, "b"), "abcd": (12, 0x0100, "b"),
             "subx": (9, 0x0100, None), "addx": (13, 0x0100, None)}
    if base in pairs:
        line, head, forced = pairs[base]
        s = forced or size
        a, b = ops
        if _is_reg(a, "d"):
            m, ry, rx = 0, int(a[1]), int(b[1])
        else:
            m = 1
            ry, rx = (int(re.search(r"a([0-7])", x, re.I).group(1))
                      for x in (a, b))
        opmode = 4 if base in ("sbcd", "abcd") else (4 | BITS_SIZE[s])
        return _pack(_w((line << 12) | (rx << 9) | (opmode << 6) | head |
                        (m << 3) | ry))
    if base == "cmpm":
        ay, ax = (int(re.search(r"a([0-7])", x, re.I).group(1)) for x in ops)
        return _pack(_w(0xB108 | (ax << 9) | (BITS_SIZE[size] << 6) | ay))
    if base == "exg":
        a, b = ops[0].lower(), ops[1].lower()
        if _is_reg(a, "d") and _is_reg(b, "d"):
            head, x, y = 0x0140, int(a[1]), int(b[1])
        elif _is_reg(a, "a") and _is_reg(b, "a"):
            head, x, y = 0x0148, int(a[1]), int(b[1])
        elif _is_reg(a, "d") and _is_reg(b, "a"):
            head, x, y = 0x0188, int(a[1]), int(b[1])
        else:
            raise Fail("exg wants Dn,Dn / An,An / Dn,An")
        return _pack(_w(0xC000 | (x << 9) | head | y))

    # --- <op>A
    if base.endswith("a") and base[:-1] in ARITH and base[:-1] != "or":
        line = ARITH[base[:-1]]
        m, r, x = _mr(parse(0), size)
        opmode = 3 if size == "w" else 7
        return _pack(_w((line << 12) | (int(ops[1][1]) << 9) | (opmode << 6) |
                        (m << 3) | r) + x)

    # --- EOR, and the five register/memory arithmetic instructions
    if base == "eor":
        m, r, x = _mr(parse(1), size)
        return _pack(_w(0xB100 | (int(ops[0][1]) << 9) |
                        (BITS_SIZE[size] << 6) | (m << 3) | r) + x)
    if base in ARITH:
        line = ARITH[base]
        if _is_reg(ops[1], "d") and not _is_reg(ops[0], "d"):
            to_dn = True
        elif _is_reg(ops[0], "d") and not _is_reg(ops[1], "d"):
            to_dn = False
        else:
            to_dn = True                    # Dn,Dn is the <ea>,Dn encoding
        src, dst = (0, 1) if to_dn else (1, 0)
        dn = int(ops[1 if to_dn else 0][1])
        m, r, x = _mr(parse(src), size)
        opmode = BITS_SIZE[size] | (0 if to_dn else 4)
        return _pack(_w((line << 12) | (dn << 9) | (opmode << 6) |
                        (m << 3) | r) + x)

    # --- shifts and rotates
    if len(base) > 1 and base[-1] in "lr" and base[:-1] in SHIFTS:
        kind = SHIFTS[base[:-1]]
        left = base[-1] == "l"
        if len(ops) == 1:
            m, r, x = _mr(parse(0, "w"), "w")
            return _pack(_w(0xE0C0 | (kind << 9) | (0x0100 if left else 0) |
                            (m << 3) | r) + x)
        head = 0xE000 | (0x0100 if left else 0) | (BITS_SIZE[size] << 6) | \
            (kind << 3) | int(ops[1][1])
        if ops[0].startswith("#"):
            v = value_of(ops[0][1:], symbols, pc) & 7
            return _pack(_w(head | (v << 9)))
        return _pack(_w(head | (int(ops[0][1]) << 9) | 0x0020))

    raise Fail(f"cannot encode {mnem} {operands!r}")


def _pack(words):
    out = bytearray()
    for w in words:
        out += (w & 0xFFFF).to_bytes(2, "big")
    return bytes(out)


def _is_movem_dest_regs(ops):
    """True for `movem <ea>,<list>` - the memory-to-register direction."""
    return not re.fullmatch(r"[da][0-7](-[da][0-7])?(/[da][0-7](-[da][0-7])?)*",
                            ops[0].strip().lower()) and ops[0].strip() != "0"


def roundtrips(ins, symbols=None):
    """True when writing this instruction down and reading it back gives
    the same words.  Every instruction in the deconstruction passes this."""
    try:
        t = text(ins)
        head, _, rest = t.partition(" ")
        got = encode(head, rest, ins.addr, symbols)
    except (Fail, KeyError, IndexError, ValueError):
        return False
    return got == b"".join(w.to_bytes(2, "big") for w in ins.words)
