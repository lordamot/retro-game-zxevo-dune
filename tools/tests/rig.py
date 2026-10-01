"""rig.py - what test_move.py and test_combat.py share: a mission loaded
on the machine through tools/dune_test.py's mailbox, pokes into the port's
records, and a view of the port's pages at the Mega Drive's addresses, so
that the S3/S4 models of tools/sega/sega_spec_check.py run on the port's
RAM unchanged.

Not a test itself (make test runs tools/tests/test_*.py only).
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "tools/sega"))
from dune_test import Machine          # noqa: E402
import sega_spec_check as S             # noqa: E402  the S3/S4 models

PG_UNITS, PG_WORLD, PG_MAP = 24, 25, 26
ALL = (PG_WORLD, PG_UNITS, PG_MAP)
U_SIZE, S_SIZE, H_SIZE, T_SIZE = 0x8C, 0x62, 0x46, 0x54
UNITS, HOUSES, TEAMS = 0x4000, 0x7800, 0x7A00       # window 1 (page UNITS)
STRUCTS = 0x8100                                    # window 2 (page WORLD)

# the 68000's addresses the models read (S2, S3)
MD_UNITS, MD_STRUCTS, MD_HOUSES = 0xFF1000, 0xFF4EB8, 0xFF4D10
MD_MAP, MD_PLAYER, MD_SCALE = 0xFF7D9C, 0xFFC274, 0xFFC068

# records.inc
O_SCRIPT, SC_PC, SC_SP, SC_VARS, SC_STACK = 0x16, 0x00, 0x0B, 0x0C, 0x16
ORDER = dict(attack=0, move=1, retreat=2, guard=3, areaguard=4, harvest=5,
             ret=6, stop=7, ambush=8, sabotage=9, die=10, hunt=11,
             deploy=12, destruct=13)
REF_UNIT, REF_STRUCT, REF_TILE = 0x4000, 0x8000, 0xC000


def w16(b, o):
    return b[o] | (b[o + 1] << 8)


def s16(b, o):
    v = w16(b, o)
    return v - 0x10000 if v & 0x8000 else v


def put16(b, o, v):
    b[o] = v & 0xFF
    b[o + 1] = (v >> 8) & 0xFF


def rnd(seed):
    """math_random $000E42 (tools/tests/test_core.py)."""
    s1, s2, s3 = seed
    d0 = s3 >> 2
    x = (s3 >> 1) & 1
    ns1 = ((s1 << 1) | x) & 255
    x = s1 >> 7
    ns2 = ((s2 << 1) | x) & 255
    x = (s2 >> 7) ^ 1
    d0 = (d0 - s3 - x) & 255
    ns3 = (s3 >> 1) | ((d0 & 1) << 7)
    return (ns1, ns2, ns3), ns3 ^ ns2


def tile_ref(sq):
    """ref_make_square (stub): kind 3, y in bits 8-13, x in bits 1-6."""
    return REF_TILE | (sq >> 6 & 63) << 8 | 0x81 | (sq & 63) << 1


def ut(t, off):
    """A unit type's word at +off ($06BC00 through $06C5B4)."""
    return S.rom_w(S.utype(t) + off)


def st(t, off):
    """A structure type's word ($06AFA6 through $06B94C)."""
    return S.rom_w(S.btype(t) + off)


def md_unit(slot):
    return MD_UNITS + U_SIZE * slot


def md_struct(slot):
    return MD_STRUCTS + S_SIZE * slot


def unit_rec(slot, utype, house, y, x, hp=None, action=3, face=0, flags=3):
    """A fresh unit record: used and allocated, on no route, seen by all."""
    r = bytearray(U_SIZE)
    r[0] = slot
    r[2] = utype
    r[3] = 0xFF
    put16(r, 4, flags)
    r[6] = 1                                   # isUnit
    r[8] = house
    r[9] = 0xFF
    put16(r, 0x0A, y)
    put16(r, 0x0C, x)
    put16(r, 0x12, ut(utype, 0x10) if hp is None else hp)
    r[O_SCRIPT + SC_SP] = 15                   # an empty stack
    r[0x54] = action
    r[0x55] = 0xFF
    r[0x69] = r[0x6A] = r[0x6C] = r[0x6D] = face
    r[0x74] = house
    r[0x7C:0x8C] = b"\xFF" * 16
    return r


def with_arg(rec, value):
    """The script's stack holding one argument (emc_arg 0)."""
    rec[O_SCRIPT + SC_SP] = 14
    put16(rec, O_SCRIPT + SC_STACK + 28, value)
    return rec


# The byte fields of each record (S2, records.inc).  A byte read anywhere
# else is a byte of a word, and a word's high byte - the 68000's first -
# is the port's second: +$0A read as a byte is the square's row.
UNIT_BYTES = {2, 3, 8, 9, 0x54, 0x55, 0x56, 0x5E, 0x5F, *range(0x68, 0x76),
              *range(0x7C, 0x8C)}
STRUCT_BYTES = {2, 3, 8, 9, 0x0F, 0x50, 0x54, 0x55}
HOUSE_BYTES = set()


def sq_of(y, x):
    """The square of a position's two words."""
    return (y >> 8 & 63) * 64 + (x >> 8 & 63)


_COT = [S.rom_l(0x0198B8 + 4 * i) for i in range(32)]
_QUAD = [S.rom_w(0x019938 + 2 * i) for i in range(4)]


def tile_direction(p, q):
    """tile_direction $0115F4 from position p to q (68000 longs), through
    the arctangent at $019940 and its tables ($0198B8, $019938)."""
    dy = (((q >> 16) - (p >> 16)) + 0x8000) % 0x10000 - 0x8000
    dx = (((q & 0xFFFF) - (p & 0xFFFF)) + 0x8000) % 0x10000 - 0x8000
    d7 = 0
    if dy <= 0:
        d7 += 2
        dy = -dy
    if dx < 0:
        d7 += 1
        dx = -dx
    d3, d4, d5 = _QUAD[d7], 0, 0x7FFF
    if dx >= dy:
        if dy:
            d5 = (dx << 8) // dy
    else:
        d4 = 1
        if dx:
            d5 = (dy << 8) // dx
    i = 0
    while i < 32 and d5 < _COT[i]:
        i += 1
    d0 = i if d4 else 0x40 - i
    d3 = d3 + d0 if d7 in (1, 2) else d3 - d0 + 0x40
    return d3 & 0xFF


# $02E2CE: each layout's centre (y << 16 | x, 256ths), what ref_position adds
LAYOUT_CENTRE = [S.rom_l(0x02E2CE + 4 * i) for i in range(8)]


def ref_pos(a, ref):
    """ref_position $02E256 on a PortRam: a square's centre, a unit's
    position, a structure's corner plus its layout's centre."""
    kind, v = ref >> 14, ref & 0x3FFF
    if kind == 3:
        sq = (v & 0x3F00) >> 2 | (v & 0x7E) >> 1
        return (sq >> 6) << 24 | 0x80 << 16 | (sq & 63) << 8 | 0x80
    if kind == 1:
        return a.l(md_unit(v) + 0xA)
    if kind == 2:
        s = md_struct(v)
        lay = S.rom_w(S.btype(a.b(s + 2)) + 0x3C) & 7
        return (a.l(s + 0xA) + LAYOUT_CENTRE[lay]) & 0xFFFFFFFF
    return 0


def ref_valid(a, ref):
    """ref_is_valid $02E2FA: a square always; a unit or structure while
    its slot is in use."""
    kind, v = ref >> 14, ref & 0xFF
    if kind == 3:
        return True
    if kind == 1:
        return v < 102 and bool(a.w(md_unit(v) + 4) & 1)
    if kind == 2:
        return v < 73 and bool(a.w(md_struct(v) + 4) & 1)
    return False


def tile_distance_packed(a, b):
    """tile_distance_packed $0114EC: tile_distance between two squares."""
    dy, dx = abs((a >> 6) - (b >> 6)), abs((a & 63) - (b & 63))
    return dy + (dx >> 1) if dy >= dx else dx + (dy >> 1)


def squares(p, q):
    """tile_distance_squares $0115C2: the distance rounded to squares."""
    return (S.tile_distance(p, q) + 0x80) >> 8 & 0xFF


def unveiled(a, sq):
    """map_square_unveiled $01AFE6: revealed, and no fog overlay on it."""
    if not a.b(S.MAP + 4 * sq + 2) & 8:
        return False
    ov = a.w(S.MAP + 4 * sq) >> 9
    return not 0x6C <= ov <= 0x7B


class PortRam:
    """sega_spec_check's Ram, read off the port's pages: the same 68000
    addresses and big-endian values, mapped onto the port's records
    (records.inc keeps the cartridge's offsets; words are little-endian and
    a position is y word, x word)."""

    def __init__(self, sym, w, u, mp):
        self.sym, self.wp, self.up, self.mp = sym, w, u, mp
        self.glob = {MD_PLAYER: w[sym["player_house"] - 0x8000],
                     MD_SCALE: w[sym["map_scale"] - 0x8000]}

    def _field(self, addr):
        for base, n, size, page, at, bytes_ in (
                (MD_UNITS, 102, U_SIZE, self.up, 0, UNIT_BYTES),
                (MD_STRUCTS, 73, S_SIZE, self.wp, STRUCTS - 0x8000, STRUCT_BYTES),
                (MD_HOUSES, 6, H_SIZE, self.up, HOUSES - 0x4000, HOUSE_BYTES)):
            if base <= addr < base + n * size:
                rec, off = divmod(addr - base, size)
                return page, at + rec * size, off, bytes_
        raise KeyError(f"PortRam: no port address for {addr:#x}")

    def u(self, addr, size):
        if MD_MAP <= addr < MD_MAP + 0x4000:
            s, k = divmod(addr - MD_MAP, 4)
            if k == 0 and size == 2:
                return self.mp[s] | self.mp[0x1000 + s] << 8
            if k in (2, 3) and size == 1:
                return self.mp[0x1000 * k + s]
            raise KeyError(f"PortRam: map {addr:#x}/{size}")
        if addr in self.glob:
            return self.glob[addr]
        p, rec, off, bytes_ = self._field(addr)
        o = rec + off
        if size == 1:
            return p[o] if off in bytes_ else p[rec + (off ^ 1)]
        if size == 2:
            return w16(p, o)
        return w16(p, o) << 16 | w16(p, o + 2)

    def s(self, addr, size):
        v = self.u(addr, size)
        return v - (1 << (8 * size)) if v >> (8 * size - 1) else v

    def l(self, addr):                              # noqa: E743
        return self.u(addr, 4)

    def w(self, addr):
        return self.u(addr, 2)

    def b(self, addr):
        return self.u(addr, 1)

    def with_unit(self, slot, rec):
        """The same RAM with one unit record replaced."""
        up = bytearray(self.up)
        up[slot * U_SIZE:(slot + 1) * U_SIZE] = rec
        return PortRam(self.sym, self.wp, bytes(up), self.mp)

    # the port's own side lists (S2): 0 the player's side, 1 the rest
    def unit_list(self, side):
        return self._list("unit_head", "unit_lnext", side)

    def struct_list(self, side):
        return self._list("struct_head", "struct_lnext", side)

    def _list(self, head, nxt, side):
        out, n = [], self.wp[self.sym[head] - 0x8000 + side]
        while n != 0xFF and len(out) < 110:
            out.append(n)
            n = self.wp[self.sym[nxt] - 0x8000 + n]
        return out


class Rig:
    """One machine run: a mission loaded through start_mission, then the
    queued pokes and calls.  Counts every call that had not finished when
    its pages were dumped (a call still running makes every later call in
    the run answer for the one before it)."""

    def __init__(self, bdir, house, mission, seed=(0x12, 0x34, 0x56)):
        self.m = Machine(build_dir=bdir)
        self.sym = self.m.sym
        self.m.poke_label("rnd_seed", bytes(seed))
        self.load = self.m.call("start_mission", a=house, bc=mission << 8,
                                frames=120, pages=ALL)
        self.res = None

    def a(self, label):
        return self.sym[label]

    def bank(self, label):
        return self.m.page_of(label)

    def poke_w(self, addr, data):
        if isinstance(addr, str):
            addr = self.sym[addr]
        self.m.poke_page(PG_WORLD, addr - 0x8000, bytes(data))

    def poke_u(self, addr, data):
        self.m.poke_page(PG_UNITS, addr - 0x4000, bytes(data))

    def poke_unit(self, slot, rec):
        self.poke_u(UNITS + slot * U_SIZE, rec)

    def poke_struct(self, slot, off, data):
        self.poke_w(STRUCTS + slot * S_SIZE + off, data)

    def poke_sq(self, sq, ground=None, high=None, flags=None, index=None):
        for plane, v in ((0, ground), (1, high), (2, flags), (3, index)):
            if v is not None:
                self.m.poke_page(PG_MAP, plane * 0x1000 + sq, [v])

    def poke_bank(self, label, data):
        """A bank's private variable (window 0) in that bank's page."""
        self.m.poke_page(self.bank(label), self.sym[label], bytes(data))

    def call(self, label, frames=4, pages=ALL, **kw):
        return self.m.call(label, frames=frames, pages=pages, **kw)

    def run(self):
        self.res = self.m.run()
        self.unfinished = [s for s in range(self.m.steps)
                           if not self.res.regs(s)["done"]]
        return self.res

    def cleanup(self):
        if self.res is not None:
            shutil.rmtree(self.res.tmp, ignore_errors=True)

    # reading a step back
    def regs(self, step):
        return self.res.regs(step)

    def page(self, step, page):
        return self.res.page(step, page)

    def ram(self, step):
        r = self.res
        return PortRam(self.sym, r.page(step, PG_WORLD), r.page(step, PG_UNITS),
                       r.page(step, PG_MAP))

    def unit(self, step, slot):
        return self.res.page(step, PG_UNITS)[slot * U_SIZE:][:U_SIZE]

    def struct(self, step, slot):
        o = STRUCTS - 0x8000 + slot * S_SIZE
        return self.res.page(step, PG_WORLD)[o:o + S_SIZE]

    def wvar(self, step, label, n=1):
        o = self.sym[label] - 0x8000
        return int.from_bytes(self.res.page(step, PG_WORLD)[o:o + n], "little")

    def bvar(self, step, label, n=1):
        """A bank's private variable after the step (its page dumped)."""
        o = self.sym[label]
        return self.res.page(step, self.bank(label))[o:o + n]


def probe(rg):
    """A call that changes nothing, to dump the pages as the next call will
    find them, the pokes included."""
    return rg.call("unit_ptr", a=0, frames=1)


def load_ram(bdir, house, mission):
    """A mission just loaded, for choosing squares and slots."""
    rg = Rig(bdir, house, mission)
    rg.run()
    ram = rg.ram(rg.load)
    rg.cleanup()
    return ram


def free_squares(ram, need=0x30):
    """Playable squares with no object on them and no bloom."""
    out = []
    for sq in range(64, 4032):
        if not S.valid_square(ram, sq):
            continue
        if ram.b(S.MAP + 4 * sq + 2) & need:
            continue
        if ram.w(S.MAP + 4 * sq) & 0x1FF == 0xD0:
            continue
        out.append(sq)
    return out


def free_slots(ram, lo=25, hi=101):
    """Unit slots of the ground range not in use."""
    return [n for n in range(lo, hi + 1) if not ram.w(md_unit(n) + 4) & 1]


class Suite:
    """Groups of checks, each one machine run; a group reports ok/total,
    and a few of its failures."""

    def __init__(self):
        self.total_bad = 0

    def group(self, name, fn, only=None):
        if only and only not in name:
            return
        out = []
        ok, bad, rig = fn(out)
        if rig is not None:
            if rig.unfinished:
                bad += len(rig.unfinished)
                out.append(f"  {len(rig.unfinished)} calls did not finish "
                           f"(steps {rig.unfinished[:8]})")
            rig.cleanup()
        self.total_bad += bad
        print(f"{name:14s} {ok}/{ok + bad}")
        for line in out[:12]:
            print(line)


class Tally:
    """ok/bad counting with the first few failures kept."""

    def __init__(self, out, keep=6):
        self.out, self.keep, self.ok, self.bad = out, keep, 0, 0

    def check(self, good, msg):
        if good:
            self.ok += 1
        else:
            self.bad += 1
            if self.bad <= self.keep:
                self.out.append("  " + msg())
        return good
