#!/usr/bin/env python3
"""sega_spec_check.py - test the Mega Drive Dune II specs against the machine.

Every spec under orig/sega/spec/ makes claims about what the game does
with its RAM: which timer fires when, what a unit's position is after M
ticks of movement, what the credits are after a refinery unloads.  A
claim that can be checked should be, and this is where it is checked:
each scenario loads a save state, runs the cartridge in bin/gen/retro-run
frame by frame, dumps the 68000's work RAM after every frame, and compares
what the spec predicts with what the machine did.

    sega_spec_check.py              run every scenario
    sega_spec_check.py S1 S3        just those specs' scenarios
    sega_spec_check.py --list       what there is

A scenario starts from a named state.  States are built, not stored: each
is a sega_touch.py scenario (the same scripted walk through the front end
that records the trace) played to its end and saved under tmp/sega/spec/.
If tmp/sega/touch/pool/ already holds that seed, it is copied instead.

Work RAM comes out of the core native-endian, like its VRAM, so every
16-bit word is byte-swapped here before anything reads it.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sega_touch  # noqa: E402

ROOT = sega_touch.ROOT
RUN, CORE, ROM = sega_touch.RUN, sega_touch.CORE, sega_touch.ROM
WORK = ROOT / "tmp/sega/spec"
POOL = ROOT / "tmp/sega/touch/pool"
RAM = 0xFF0000


# ---------------------------------------------------------- the machine

def state(name):
    """The save state `name` (a sega_touch scenario), built if need be."""
    WORK.mkdir(parents=True, exist_ok=True)
    dst = WORK / f"{name}.state"
    if dst.exists():
        return dst
    seed = POOL / f"seed-{name}.state"
    if seed.exists():
        shutil.copy(seed, dst)
        return dst
    lines = sega_touch.scenarios(ROM.read_bytes())[name]
    _run(lines + [f"save {dst}"])
    if not dst.exists():
        sys.exit(f"error: could not build the state {name}")
    return dst


def _run(lines):
    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "s.script"
        s.write_text("\n".join(lines) + "\n")
        p = subprocess.run([str(RUN), "--core", str(CORE), "--rom", str(ROM),
                            "--script", str(s)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode:
            sys.exit("error: retro-run failed")


class Ram:
    """One dump of work RAM, read big-endian as the 68000 sees it."""

    def __init__(self, raw):
        b = bytearray(raw)
        b[0::2], b[1::2] = b[1::2], b[0::2]
        self.mem = bytes(b)

    def u(self, addr, size):
        o = addr - RAM
        return int.from_bytes(self.mem[o:o + size], "big")

    def s(self, addr, size):
        v = self.u(addr, size)
        return v - (1 << (8 * size)) if v >> (8 * size - 1) else v

    def l(self, addr):
        return self.u(addr, 4)

    def w(self, addr):
        return self.u(addr, 2)

    def b(self, addr):
        return self.u(addr, 1)


_FRAMES = {}


def frames(name, n, before=(), every=1):
    """Load state `name`, play `before` (script lines), then dump RAM
    every `every` frames, n + 1 dumps in all (the first before any
    frame runs).  A run asked for twice is played once."""
    key = (name, n, tuple(before), every)
    if key not in _FRAMES:
        _FRAMES[key] = _frames(name, n, before, every)
    return _FRAMES[key]


def _frames(name, n, before, every):
    st = state(name)
    with tempfile.TemporaryDirectory() as d:
        lines = [f"load {st}", *before]
        for i in range(n + 1):
            lines.append(f"ram {d}/{i}.bin")
            if i < n:
                lines.append(f"run {every}")
        _run(lines)
        return [Ram((Path(d) / f"{i}.bin").read_bytes()) for i in range(n + 1)]


# ---------------------------------------------------------- the scenarios

SCENARIOS = []


def scenario(spec, what):
    def reg(f):
        SCENARIOS.append((spec, f.__name__, what, f))
        return f
    return reg


class Check:
    """Collects failures; a scenario passes when it has none."""

    def __init__(self):
        self.fails = []
        self.count = 0

    def that(self, ok, msg):
        self.count += 1
        if not ok:
            self.fails.append(msg)


# S1 - the frame ---------------------------------------------------------

CLOCK = 0xFFC598          # game.timerGame, +1 a frame from the battle hook
GUI = 0xFFC594            # game.timerGUI
FRAMES = 0xFFE01A         # sys.frameCount, +1 every vertical interrupt
HOOK = 0xFFE002           # sys.frameHook
MUSIC_LEFT = 0xFFC574     # music.framesLeft

# (next-due variable, period, which loop runs it)
UNIT_TIMERS = [(0xFFDE98, 3, "unit movement"), (0xFFDE94, 2, "unit rotation"),
               (0xFFDE90, 20, "unit turret aim"), (0xFFDE88, 5, "unit animation"),
               (0xFFDE8C, 5, "unit script"), (0xFFDE84, 60, "unit deviation")]
STRUCT_TIMERS = [(0xFFD5A0, 30, "structure build"), (0xFFD59C, 5, "structure script"),
                 (0xFFD598, 60, "structure palace")]
HOUSE_TIMERS = [(0xFFDC44, 900, "house"), (0xFFDC3C, 60, "house starport"),
                (0xFFDC38, 600, "house reinforcement"), (0xFFDC34, 5, "house unused"),
                (0xFFDC30, 60, "house missile"), (0xFFDC2C, 1800, "house availability")]
TEAM_NEXT = 0xFFDCA4


@scenario("S1", "the game clock is one tick a frame while a battle hook is in")
def s1_clock(c):
    d = frames("m1-0", 300)
    for a, b in zip(d, d[1:]):
        n = b.l(FRAMES) - a.l(FRAMES)
        c.that(n == 1, f"frame counter moved {n}")
        hooked = b.l(HOOK) in (0x608E, 0x6D0C)
        c.that(hooked, f"hook is {b.l(HOOK):#x}")
        c.that(b.l(CLOCK) - a.l(CLOCK) == 1,
               f"clock {a.l(CLOCK)} -> {b.l(CLOCK)} in one frame")
        c.that(b.l(GUI) - a.l(GUI) == 1, "GUI timer did not tick")
        c.that(b.s(MUSIC_LEFT, 2) - a.s(MUSIC_LEFT, 2) == -1,
               "music countdown is not one a frame")


@scenario("S1", "the Start menu takes the hook out and the clock stops")
def s1_pause(c):
    d = frames("m1-0", 20, before=["press start 6", "run 120"], every=5)
    for a, b in zip(d, d[1:]):
        c.that(b.l(HOOK) == 0, f"hook still {b.l(HOOK):#x} in the menu")
        c.that(b.l(CLOCK) == a.l(CLOCK), "clock moved in the menu")
        c.that(b.l(FRAMES) - a.l(FRAMES) == 5, "frames did not move")


def _timer_windows(c, d, timers, passes):
    """Every change of a next-due timer must be `fired + period` with
    `fired` the clock of a pass that ran that loop, at or after the old
    due time, and a pass that runs the loop while the timer is due must
    fire it.  `passes(i)` says whether the pass begun in frame i runs the
    loop."""
    def changed(i):
        return any(d[i].l(t) != d[i + 1].l(t) for t, _, _ in timers)

    for addr, period, what in timers:
        for i, (a, b) in enumerate(zip(d, d[1:])):
            old, new = a.l(addr), b.l(addr)
            if old == new:
                # it did not fire, so this pass (if it ran the loop) was
                # early - unless the loop is the late one seen next frame;
                # bcs and blt agree while the clock is small
                spill = i + 1 < len(d) - 1 and not passes(i + 1) \
                    and changed(i + 1)
                if passes(i) and not spill:
                    c.that(b.l(CLOCK) < old,
                           f"{what}: due {old}, clock {b.l(CLOCK)}, not fired")
                continue
            fired = new - period
            # a pass whose units ran past the frame's end writes its
            # rotating loop's timers in the next frame: late by one, and
            # only if nothing of that loop showed in the frame before
            late = i > 0 and passes(i - 1) and not changed(i - 1)
            c.that(passes(i) or late,
                   f"{what} fired on pass {i}, which does not run it")
            c.that(fired == b.l(CLOCK), f"{what}: set to {new}, clock "
                   f"{b.l(CLOCK)} (period {period})")
            c.that(fired >= old, f"{what}: fired at {fired}, due {old}")


@scenario("S1", "units every pass; teams, structures, houses, structures in turn")
def s1_schedule(c):
    d = frames("m1-0", 400)
    # one pass a frame here, so dump i+1 shows pass i; find the phase of
    # the round-robin from the first team firing
    team = [i for i, (a, b) in enumerate(zip(d, d[1:]))
            if a.l(TEAM_NEXT) != b.l(TEAM_NEXT)]
    c.that(len(team) > 10, "teams hardly ran")
    if not team:
        return
    p = team[0] % 4

    def phase(k):
        return lambda i: (i - p) % 4 == k

    _timer_windows(c, d, UNIT_TIMERS, lambda i: True)
    _timer_windows(c, d, STRUCT_TIMERS, lambda i: (i - p) % 2 == 1)
    _timer_windows(c, d, HOUSE_TIMERS, phase(2))
    for i in team:
        c.that((i - p) % 4 == 0, f"teams ran on pass {i}")
        step = d[i + 1].l(TEAM_NEXT) - d[i + 1].l(CLOCK)
        c.that(5 <= step <= 12, f"team timer set {step} ahead")
    # between two team passes that fired, none that was due was skipped
    for i in range(len(d) - 1):
        if (i - p) % 4 == 0 and i not in team:
            c.that(d[i + 1].l(CLOCK) < d[i].l(TEAM_NEXT),
                   f"teams due at {d[i].l(TEAM_NEXT)} skipped on pass {i}")


@scenario("S1", "the level-end check is asked every 300 ticks")
def s1_level_end(c):
    d = frames("m1-0", 30, every=20)
    nxt = [x.l(0xFFDC28) for x in d]
    changes = [(a, b) for a, b in zip(nxt, nxt[1:]) if a != b]
    c.that(len(changes) >= 1, "the level-end timer never moved")
    for a, b in changes:
        c.that(b - a >= 300, f"level-end check moved {a} -> {b}")


# S2 - objects ------------------------------------------------------------

_ROM = None


def rom():
    global _ROM
    if _ROM is None:
        _ROM = ROM.read_bytes()
    return _ROM


def rom_l(a):
    return int.from_bytes(rom()[a:a + 4], "big")


def rom_w(a):
    return int.from_bytes(rom()[a:a + 2], "big")


def unit_recs():
    """The 102 unit records, from the pointer table at $04A852."""
    return [rom_l(0x04A852 + 4 * i) for i in range(102)]


def struct_recs():
    """The 73 structure records the code uses, from $04A716."""
    return [rom_l(0x04A716 + 4 * i) for i in range(73)]


def unit_ranges():
    """(indexStart, indexEnd) of each unit type, +$34/+$36 of $06BC00."""
    return [(rom_w(rom_l(0x06C5B4 + 4 * t) + 0x34),
             rom_w(rom_l(0x06C5B4 + 4 * t) + 0x36)) for t in range(27)]


PC_UNIT_RANGES = ([(0, 10)] * 2 + [(22, 101)] * 4 + [(20, 21)]
                  + [(22, 101)] * 11 + [(12, 15)] * 7 + [(16, 17), (11, 11)])

TEAMS, HOUSES = 0xFF47CC, 0xFF4D10
SIDE = [-1, 0, -1, 1, -1, -1]            # $023750, house_are_allied


def allied(r, a, b):
    if a == b:
        return True
    t = SIDE[a] + SIDE[b]
    if t > 0:
        return True
    if t == 0:
        return False
    return r.w(0xFFC274) not in (a, b)


def movement(t):
    return rom_w(rom_l(0x06C5B4 + 4 * t) + 0x3E)


def unit_counted(t):
    """unit_create $043436: counted in the house's +6 unless the type
    joins no list ($02056E) or flies (movement 4)."""
    return rom()[0x02056E + t] and movement(t) != 4


def walk(r, head):
    out, n = [], r.l(head) & 0xFFFFFF
    while n and len(out) <= 200:
        out.append(n)
        n = r.w(n + 4)
        n = 0xFF0000 | n if n else 0
    return out


def check_pools(c, r, tag):
    """Everything the pool routines keep in step, in one RAM dump."""
    units, structs = unit_recs(), struct_recs()
    uu = [i for i, a in enumerate(units) if r.w(a + 4) & 1]
    ss = [i for i, a in enumerate(structs) if r.w(a + 4) & 1]
    lst = [r.l(0xFFDCC0 + 4 * i) for i in range(r.w(0xFFDCBC))]
    c.that(sorted(lst) == sorted(units[i] for i in uu),
           f"{tag}: unit list $FFDCC0 is not the units in use")
    lst = [r.l(0xFFD31C + 4 * i) for i in range(r.w(0xFFD318))]
    c.that(sorted(lst) == sorted(structs[i] for i in ss),
           f"{tag}: structure list $FFD31C is not the structures in use")
    for i in uu:
        c.that(r.w(units[i]) == i, f"{tag}: unit {i} says it is {r.w(units[i])}")
    for i in ss:
        c.that(r.w(structs[i]) == i, f"{tag}: structure {i} says {r.w(structs[i])}")
        t = r.b(structs[i] + 2)
        want = {0: 72, 1: 71, 14: 70}.get(t)
        c.that(i == want if want is not None else i < 70,
               f"{tag}: structure type {t} in slot {i}")
    c.that(r.l(0xFFDC24) == HOUSES, f"{tag}: house array not at $FF4D10")
    hh = [h for h in range(6) if r.w(HOUSES + 0x46 * h + 4) & 1]
    lst = [r.l(0xFFDC0C + 4 * i) for i in range(r.w(0xFFDC08))]
    c.that(sorted(lst) == [HOUSES + 0x46 * h for h in hh],
           f"{tag}: house list is not the houses in use")
    tt = [i for i in range(16) if r.w(TEAMS + 0x54 * i + 2)]
    lst = [r.l(0xFFDC60 + 4 * i) for i in range(r.w(0xFFDC5C))]
    c.that(sorted(lst) == [TEAMS + 0x54 * i for i in tt],
           f"{tag}: team list is not the teams in use")
    # per-house, per-type counts: units at $FFBDFC, structures at $FF7C9C
    for base, recs, used, n in ((0xFFBDFC, units, uu, 27),
                                (0xFF7C9C, structs, ss, 19)):
        for h in range(5):
            for t in range(n):
                have = sum(1 for i in used if r.b(recs[i] + 8) == h
                           and r.b(recs[i] + 2) == t)
                c.that(r.b(base + 32 * h + t) == have,
                       f"{tag}: count {base:#x} house {h} type {t} is "
                       f"{r.b(base + 32 * h + t)}, {have} exist")
    # a house's unitCount (+6) is its counted units, by original house
    for h in hh:
        have = sum(1 for i in uu if r.b(units[i] + 0x74) == h
                   and unit_counted(r.b(units[i] + 2)))
        c.that(r.w(HOUSES + 0x46 * h + 6) == have,
               f"{tag}: house {h} unitCount {r.w(HOUSES + 0x46 * h + 6)}, "
               f"counted units {have}")
    # the side lists: each object with a list type, once, on its side
    lists = {h: walk(r, h) for h in (0xFFDBDC, 0xFFDBD8, 0xFFDBE8,
                                     0xFFDBE4, 0xFFDBD0)}
    c.that(sum(len(v) for v in lists.values()) == 200,
           f"{tag}: the 200 nodes do not add up")
    player = r.w(0xFFC274)
    for heads, recs, used, table, link in (
            ((0xFFDBDC, 0xFFDBD8), structs, ss, 0x0204D0, 0x60),
            ((0xFFDBE8, 0xFFDBE4), units, uu, 0x02056E, 0x4C)):
        want = {i: allied(r, r.b(recs[i] + 8), player) for i in used
                if rom()[table + r.b(recs[i] + 2)]}
        got = {}
        for side, head in zip((True, False), heads):
            for n in lists[head]:
                i = r.w(n)
                c.that(i not in got, f"{tag}: {i} is in the lists twice")
                got[i] = side
                c.that((0xFF0000 | r.w(recs[i] + link)) == n,
                       f"{tag}: object {i}'s node is not {n:#x}")
        c.that(got == want, f"{tag}: side lists {sorted(got.items())[:4]} "
               f"against {sorted(want.items())[:4]}")
    listed = len(lists[0xFFDBDC]) + len(lists[0xFFDBD8])
    c.that(r.s(0xFFBEA2, 2) == 70 - listed,
           f"{tag}: $FFBEA2 is {r.s(0xFFBEA2, 2)}, {listed} structures listed")


S2_STATES = ["m1-0", "pt-DEATHRULER", "pw-DOMINATION", "pw-DEMOLITION"]


@scenario("S2", "the pools, their lists, counts and side lists agree")
def s2_pools(c):
    for st in S2_STATES:
        check_pools(c, frames(st, 0)[0], st)
    for i, r in enumerate(frames("pw-DEMOLITION", 2000)[::10]):
        check_pools(c, r, f"pw-DEMOLITION+{10 * i}")


@scenario("S2", "counting every unit, as the PC does, does not fit (control)")
def s2_count_control(c):
    units, misfit = unit_recs(), 0
    for st in S2_STATES:
        r = frames(st, 0)[0]
        for h in range(6):
            if not r.w(HOUSES + 0x46 * h + 4) & 1:
                continue
            every = sum(1 for a in units if r.w(a + 4) & 1
                        and r.b(a + 8) == h)
            misfit += every != r.w(HOUSES + 0x46 * h + 6)
    c.that(misfit >= 1, "every house's unitCount is all its units")


def _creations(c, ranges, runs=("pw-DOMINATION", "pw-DEMOLITION")):
    """Every unit that comes into use takes the lowest free slot of its
    type's range.  A slot freed and filled again in one frame counts as
    free.  Returns how many creations were seen."""
    units, seen = unit_recs(), 0
    for st in runs:
        d = frames(st, 2000)
        for f, (a, b) in enumerate(zip(d, d[1:])):
            fresh = [i for i, x in enumerate(units) if b.w(x + 4) & 1 and (
                not a.w(x + 4) & 1 or a.b(x + 2) != b.b(x + 2))]
            for i in sorted(fresh):
                s, e = ranges[b.b(units[i] + 2)]
                free = [j for j in range(s, e + 1)
                        if not a.w(units[j] + 4) & 1 or j in fresh]
                seen += 1
                c.that(bool(free) and free[0] == i,
                       f"{st} frame {f}: type {b.b(units[i] + 2)} went to "
                       f"slot {i}, first free {free[:1]}")
                fresh = [j for j in fresh if j != i]
    return seen


@scenario("S2", "a new unit takes the first free slot of its type's range")
def s2_create(c):
    n = _creations(c, unit_ranges())
    c.that(n >= 20, f"only {n} creations seen")


@scenario("S2", "with the PC's ranges the creations do not fit (control)")
def s2_create_control(c):
    wrong = Check()
    _creations(wrong, PC_UNIT_RANGES)
    c.that(len(wrong.fails) >= 5,
           f"the PC ranges fit too: {len(wrong.fails)} misfits")


def check_refs(c, r, tag):
    """Every reference a unit or team holds names something that is
    there: a unit in use and allocated, a structure in use, or a square
    in the form ref_make builds ($02E17C)."""
    units, structs = unit_recs(), struct_recs()
    held = []
    for i, a in enumerate(units):
        if r.w(a + 4) & 1:
            # a Harvester's +$5A is its harvest sprite, not a reference;
            # a projectile's +$52 names its shooter and nothing clears
            # it when the shooter dies (unit_drop_references, as the PC)
            t = r.b(a + 2)
            offs = [o for o in (0x52, 0x5A, 0x5C)
                    if not (o == 0x5A and t == 16)
                    and not (o == 0x52 and 18 <= t <= 24)]
            held += [(f"unit {i} +{o:#x}", r.w(a + o)) for o in offs]
    for i in range(16):
        if r.w(TEAMS + 0x54 * i + 2):
            held.append((f"team {i} +$1A", r.w(TEAMS + 0x54 * i + 0x1A)))
    for what, ref in held:
        kind, v = ref >> 14, ref & 0x3FFF
        if kind == 1:
            c.that(v < 102 and r.w(units[v] + 4) & 3 == 3,
                   f"{tag}: {what} = {ref:#06x}, a unit not in use")
        elif kind == 2:
            c.that(v < 73 and r.w(structs[v] + 4) & 1,
                   f"{tag}: {what} = {ref:#06x}, a structure not in use")
        elif kind == 3:
            c.that(ref & 0x81 == 0x81,
                   f"{tag}: {what} = {ref:#06x} is no square")
        else:
            c.that(ref == 0, f"{tag}: {what} = {ref:#06x}, kind 0 but not 0")


@scenario("S2", "references held by units and teams never go stale")
def s2_refs(c):
    for st in S2_STATES:
        check_refs(c, frames(st, 0)[0], st)
    for st in ("pw-DOMINATION", "pw-DEMOLITION"):
        for i, r in enumerate(frames(st, 2000)):
            check_refs(c, r, f"{st}+{i}")


# S3 - movement and pathfinding --------------------------------------------

MAP = 0xFF7D9C                    # *$04AA1C: 64 x 64 squares of 4 bytes
MOVE_T, ROT_T = 0xFFDE98, 0xFFDE94
STEPS8 = (-64, -63, 1, 65, 64, 63, -1, -65)          # $012A9C
# the battles S3 samples: busy ones, where units drive and are routed round
S3_STATES = ("pt-DEMOLITION", "pw-DOMINATION", "pw-SPICEDANCE",
             "pt-ARRAKISSUN", "pt-EVILMENTAT", "pt-WILYMENTAT",
             "pw-DEFTHUNTER", "pt-DUNERUNNER", "pt-SLYMELANIE")


def sbyte(x):
    return x - 256 if x > 127 else x


def utype(t):
    return rom_l(0x06C5B4 + 4 * t)


def btype(t):
    return rom_l(0x06B94C + 4 * t)


def mul_shr8(a, b):
    """math_mul_shr8 $0199D8: (a * b + $50) >> 8, capped at $FFFF."""
    return min((a * b + 0x50) >> 8, 0xFFFF)


def speed_fields(ttype, moving):
    """unit_set_speed $047F44: movingSpeed -> (speed +$70, perTick +$6E)."""
    v = mul_shr8(rom_w(utype(ttype) + 0x42), moving)
    if v >> 4:
        return v >> 4, 0xFF
    return 1, (v << 4) & 0xFF


def tile_distance(p, q):
    """tile_distance $0115CE: the larger axis plus half the smaller."""
    dy, dx = abs((p >> 16) - (q >> 16)), abs((p & 0xFFFF) - (q & 0xFFFF))
    return dy + (dx >> 1) if dy >= dx else dx + (dy >> 1)


def move_by_direction(p, d, n):
    """tile_move_by_direction $01162E, sin at $06CFA4, cos at $06D0A4."""
    n = min(n, 255)
    sin, cos = sbyte(rom()[0x06CFA4 + d]), sbyte(rom()[0x06D0A4 + d])
    y = ((p >> 16) + ((-cos * n + 0x40) >> 7)) & 0xFFFF
    x = ((p & 0xFFFF) + ((sin * n + 0x40) >> 7)) & 0xFFFF
    return y << 16 | x


def square_of(p):
    return (p >> 24) << 6 | (p >> 8) & 0xFF


def landscape(r, s):
    """map_get_landscape_type $0057E6: ground icon -> type through the
    bytes at $005818, unless the overlay says 13 (a destroyed wall)."""
    w = r.w(MAP + 4 * s)
    lt, ov = rom()[0x005818 + (w & 0x1FF)], rom()[0x005818 + (w >> 9 & 0x7F)]
    return sbyte(13 if ov == 13 else lt)


def land_speed(lt, mt):
    return rom()[0x06CCAE + 28 * lt + mt]


def valid_square(r, s):
    """map_is_valid_position $005798, limits at $06CE7A by map scale."""
    x0, y0, w, h = (rom_w(0x06CE7A + 8 * r.w(0xFFC068) + 2 * i)
                    for i in range(4))
    return x0 <= (s & 63) < x0 + w and y0 <= (s >> 6 & 63) < y0 + h


def object_at(r, s, bit, recs):
    if not 0 <= s < 0x1000 or not r.b(MAP + 4 * s + 2) & bit:
        return None
    return recs()[r.b(MAP + 4 * s + 3) - 1]


def unit_house(r, u):
    return 2 if r.b(u + 0x5F) else r.b(u + 8)


def ref_square(r, ref):
    """ref_square $02E1F6."""
    kind, v = ref >> 14, ref & 0x3FFF
    if kind == 0:
        return 0
    if kind == 3:
        return (v & 0x3F00) >> 2 | (v & 0x7E) >> 1
    rec = (unit_recs() if kind == 1 else struct_recs())[v]
    return r.b(rec + 0xA) << 6 | r.b(rec + 0xC)


def can_enter_structure(r, u, s):
    """unit_can_enter_structure $00556A."""
    b, t = btype(r.b(s + 2)), utype(r.b(u + 2))
    here = 0x8000 | r.w(s)
    if unit_house(r, u) != r.b(s + 8):
        if r.b(u + 2) == 6 and r.w(u + 0x5C) == here:
            return 2
        if rom_w(t + 0x3E) == 0 and rom_w(b + 0x0C) & 0x80:
            return 2 if r.w(u + 0x5C) == here else 1
        return 0
    if not rom_l(b + 0x34) >> r.b(u + 2) & 1:
        return 0
    if r.w(s + 0x2A) == 0x4000 | r.w(u):
        return 2
    return 1 if r.b(s + 3) == 0xFF else 0


def enter_score(r, u, s, o):
    """unit_tile_enter_score $005624; `o` as the caller passes it."""
    mt = rom_w(utype(r.b(u + 2)) + 0x3E)
    if not valid_square(r, s) and mt != 4:
        return 256
    v = object_at(r, s, 0x10, unit_recs)
    if v is not None and v != u and r.b(u + 2) != 25:
        if r.b(u + 2) == 6 and r.w(u + 0x5C) == 0x4000 | r.w(v):
            return 0
        if allied(r, unit_house(r, u), unit_house(r, v)):
            return 256
        if rom_w(utype(r.b(v + 2)) + 0x3E) != 0 or mt not in (1, 2):
            return 256
    st = object_at(r, s, 0x20, struct_recs)
    if st is not None:
        e = can_enter_structure(r, u, st)
        return 256 if e == 0 else -e
    lt = landscape(r, s)
    sp = land_speed(lt, mt)
    if r.b(u + 2) == 6 and lt == 11 and not allied(
            r, r.b(u + 8), r.b(MAP + 4 * s + 2) & 7):
        sp = 255
    if sp == 0:
        return 256
    c = sp ^ 0xFF
    if o & 1:
        c -= (c >> 2) + (c >> 3)
    return c


def path_cost(r, u, s, d):
    """unit_path_cost $04526C: free into the destination's own square."""
    if ref_square(r, r.w(u + 0x5C)) == s:
        return 0
    c = enter_score(r, u, s, d << 5)
    return 256 if c == -1 else c


def step8(s, d):
    return (s + STEPS8[d & 7]) & 0xFFFF


def direction_packed(a, b):
    """tile_direction_packed $01152A and its table at $0115A2."""
    dx, dy = (b & 63) - (a & 63), (b >> 6 & 63) - (a >> 6 & 63)
    i = (0 if dy > 0 else 8) + (0 if dx > 0 else 4)
    i += (2 if abs(dy) > 2 * abs(dx) else 0) + (1 if abs(dx) > 2 * abs(dy) else 0)
    return rom_w(0x0115A2 + 2 * i)


SMOOTH_OFFSET = (0, 0, 1, 2, 3, -2, -1, 0)             # $06C748


def path_smooth(start, route, cb, lim):
    """path_smooth $012E62 on a route of directions; returns (route,
    score)."""
    b, d6 = route + [0xFF], start
    if len(route) > 1:
        a5 = 1
        while b[a5] != 0xFF:
            a4 = a5 - 1
            while b[a4] == 0xFE and a4:
                a4 -= 1
            if b[a4] == 0xFE:
                a5 += 1
                continue
            d = SMOOTH_OFFSET[(b[a5] - b[a4]) & 7]
            if d == 3:
                b[a4] = b[a5] = 0xFE
                a5 += 1
                continue
            if d == 0:
                d6 = step8(d6, b[a4])
                a5 += 1
                continue
            if b[a4] & 1:
                d4 = (b[a4] + (-1 if d < 0 else 1)) & 7
                if abs(d) == 1:
                    if cb(step8(d6, d4), d4) <= lim:
                        b[a5] = b[a4] = d4
                    d6 = step8(d6, b[a4])
                    a5 += 1
                    continue
            else:
                d4 = (b[a4] + d) & 7
            b[a5], b[a4] = d4, 0xFE
            while b[a4] == 0xFE and a4:
                a4 -= 1
            d6 = step8(d6, (b[a4] + 4) & 7) if b[a4] != 0xFE else start
    out, score, s = [], 0, start
    for x in b[:b.index(0xFF)]:
        if x != 0xFE:
            s = step8(s, x)
            score += cb(s, x)
            out.append(x)
    return out, score


def follow_edge(dst, start, turn, d5, cb, lim):
    """path_follow_edge $012D5A: None, or (route, score)."""
    cur, out = start, []
    while len(out) < 0x80:
        d7 = d5
        while True:
            d7 = (d7 + turn) & 7
            if d7 & 1 and step8(cur, d7 + turn) == dst:
                d7 = (d7 + turn) & 7
                nxt = step8(cur, d7)
                break
            if d7 == d5:
                return None
            nxt = step8(cur, d7)
            if cb(nxt, d7) <= lim:
                break
        out.append(d7)
        if nxt == dst:
            return path_smooth(start, out, cb, lim)
        if nxt == start:
            return None
        d5, cur = (d7 - 3 * turn) & 7, nxt
    return None


def path_find(start, goal, size, cb, lim, turns=(-1, 1)):
    """path_find $012AAE: the route (directions, then $FF if room)."""
    route, cur, room = [], start, size - 1
    while room > len(route) and cur != goal:
        a3 = direction_packed(cur, goal) >> 5 & 7
        nxt = step8(cur, a3)
        c = cb(nxt, a3)
        if c <= lim:
            route.append(a3)
            cur = nxt
            continue
        best = None
        while nxt != goal:
            # along the blocked line to a square that can be entered - or,
            # on a diagonal, a square whose two back neighbours both can.
            # One that can be entered starts the edge following even when
            # it is the goal: the cost test ($012B8C) comes before the goal
            # test ($012B62), which is made only before a step.
            found = False
            while nxt != goal:
                d3 = direction_packed(nxt, goal) >> 5
                nxt = step8(nxt, d3)
                if cb(nxt, d3) <= lim:
                    found = True
                    break
                if d3 & 1 and cb(step8(nxt, d3 + 3), (d3 + 3) & 7) <= lim \
                        and cb(step8(nxt, d3 + 5), (d3 + 5) & 7) <= lim:
                    nxt = step8(nxt, d3 + 3)
                    found = True
                    break
            if not found:
                break
            ccw = follow_edge(nxt, cur, turns[0], a3, cb, lim)
            cw = follow_edge(nxt, cur, turns[1], a3, cb, lim)
            if ccw or cw:
                best = ccw if not cw or (ccw and ccw[1] < cw[1]) else cw
                break
            while nxt != goal:
                d3 = direction_packed(nxt, goal) >> 5
                nxt = step8(nxt, d3)
                if cb(nxt, d3) > lim:
                    break
        if best is None:
            break
        n = min(room - len(route), len(best[0]))
        if n <= 0:
            break
        route += best[0][:n]
        cur = nxt
    return route + [0xFF] if room > len(route) else route


def upto_ff(x):
    x = list(x)
    return x[:x.index(0xFF) + 1] if 0xFF in x else x


def live_units(a, b):
    """Units in use and on the map in both dumps, the same type."""
    for u in unit_recs():
        if a.w(u + 4) & 1 and b.w(u + 4) & 1 and not a.w(u + 4) & 4 \
                and a.b(u + 2) == b.b(u + 2):
            yield u


@scenario("S3", "speed, per-tick fraction and whole steps follow +$42 and movingSpeed")
def s3_speed(c):
    s3_speed_with(c, speed_fields)


def s3_speed_with(c, fields):
    for st in S3_STATES[:4]:
        for r in frames(st, 2000)[::10]:
            for u in unit_recs():
                if r.w(u + 4) & 1 and r.b(u + 0x71):
                    c.that(fields(r.b(u + 2), r.b(u + 0x71)) ==
                           (r.b(u + 0x70), r.b(u + 0x6E)),
                           f"{st}: type {r.b(u + 2)} moving {r.b(u + 0x71)} "
                           f"has {r.b(u + 0x70)}/{r.b(u + 0x6E)}")


@scenario("S3", "the PC's truncating multiply does not fit the speeds (control)")
def s3_speed_control(c):
    def pc(t, moving):
        v = rom_w(utype(t) + 0x42) * moving >> 8
        return (v >> 4, 0xFF) if v >> 4 else (1, (v << 4) & 0xFF)
    wrong = Check()
    s3_speed_with(wrong, pc)
    c.that(len(wrong.fails) >= 20, f"only {len(wrong.fails)} misfits")


def predict_move(a, u, pc_ground=False):
    """Where unit_move_tick $047FBA leaves a unit this movement tick, or
    None if it does not move.  pc_ground moves ground units the PC way:
    along the facing by min(speed * 16, distance + 16)."""
    t = a.b(u + 2)
    ty = utype(t)
    mt, flags = rom_w(ty + 0x3E), rom_w(ty + 0x38)
    if a.b(u + 0x70) == 0:
        return None
    if mt in (0, 1) and a.b(u + 0x69) != a.b(u + 0x6A):
        return None                                    # only turns
    if a.b(u + 0x6F) + a.b(u + 0x6E) < 256:
        return None                                    # no carry
    p, dst = a.l(u + 0xA), a.l(u + 0x4E)
    if mt == 4 or pc_ground:
        q = move_by_direction(p, a.b(u + 0x6A),
                              min(a.b(u + 0x70) * 16, tile_distance(p, dst) + 16))
    else:
        q = (((p >> 16) + a.w(u + 0x7A)) & 0x3FFF) << 16 | \
            ((p & 0xFFFF) + a.w(u + 0x78)) & 0x3FFF
    d = tile_distance(q, dst)
    arrived = d > a.w(u + 0x58) or d <= 12
    if arrived and flags & 0x02 and (a.b(u + 0x56) == 0 or t == 20):
        return p                     # a projectile explodes where it was
    if arrived and flags & 0x40 and dst:
        return dst                   # a ground unit snaps onto the square
    return q


def s3_moves(c, pc_ground=False):
    """Every change of a unit's position is one movement tick of it, and
    every change of its fraction alone is one tick without a carry.
    Checked on the transitions, not on the timer: in a heavy battle the
    unit loop runs frames behind, and the last units in its list (the
    newest - projectiles) move frames after the tick that moved them."""
    moves = 0
    for st in S3_STATES[:4]:
        d = frames(st, 2000)
        split = set()        # moved, fraction not yet written (below)
        for i, (a, b) in enumerate(zip(d, d[1:])):
            for u in live_units(a, b):
                if not a.l(u + 0x4E) or a.l(u + 0x4E) != b.l(u + 0x4E) and \
                        b.l(u + 0x4E) and a.l(u + 0xA) == b.l(u + 0xA):
                    continue
                p, q = a.l(u + 0xA), b.l(u + 0xA)
                if p != q:
                    moves += 1
                    pred = predict_move(a, u, pc_ground)
                    c.that(pred == q, f"{st} {i}: type {a.b(u + 2)} {p:#x} -> "
                           f"{q:#x}, predicted {pred and hex(pred)}")
                    if a.b(u + 0x6F) == b.b(u + 0x6F):
                        # the frame can end between unit_move's write of
                        # the position ($046864) and unit_move_tick's of
                        # the fraction ($048054)
                        split.add((u, i + 1))
                elif a.b(u + 0x6F) != b.b(u + 0x6F) and \
                        (a.b(u + 0x6E), a.b(u + 0x70)) == (b.b(u + 0x6E), b.b(u + 0x70)):
                    carry = a.b(u + 0x6F) + a.b(u + 0x6E) >= 256
                    c.that(b.b(u + 0x6F) == (a.b(u + 0x6F) + a.b(u + 0x6E)) & 0xFF
                           and carry == ((u, i) in split),
                           f"{st} {i}: fraction {a.b(u + 0x6F)} + {a.b(u + 0x6E)} "
                           f"-> {b.b(u + 0x6F)} without a move")
    return moves


@scenario("S3", "each movement tick moves a unit exactly as unit_move_tick does")
def s3_step(c):
    n = s3_moves(c)
    c.that(n >= 300, f"only {n} moves seen")


@scenario("S3", "moving ground units the PC way (by facing and speed) does not fit (control)")
def s3_step_control(c):
    wrong = Check()
    s3_moves(wrong, pc_ground=True)
    c.that(len(wrong.fails) >= 50, f"only {len(wrong.fails)} misfits")


def turn_step(sp, tg, cur):
    """unit_turn_step $047E94 on (speed, target, current)."""
    if sp == 0:
        return 0, cur
    diff = (tg - cur) & 0xFF
    diff = min(diff, 256 - diff)
    if abs(sbyte(sp)) >= diff:
        return 0, tg
    return sp, (cur + sp) & 0xFF


def s3_turns(c, move_turns=True):
    late = 0
    for st in S3_STATES[:4]:
        d = frames(st, 2000)
        for i, (a, b) in enumerate(zip(d, d[1:])):
            ev = [(a.l(MOVE_T) != b.l(MOVE_T), a.l(ROT_T) != b.l(ROT_T))]
            if i + 2 < len(d):
                ev.append((b.l(MOVE_T) != d[i + 2].l(MOVE_T),
                           b.l(ROT_T) != d[i + 2].l(ROT_T)))
            if not any(ev[0]):
                continue
            for u in live_units(a, b):
                sp, tg, cur = a.b(u + 0x68), a.b(u + 0x69), a.b(u + 0x6A)
                if sp == 0 and tg == cur or b.b(u + 0x69) != tg or \
                        sp == 0 and b.b(u + 0x68):
                    continue                  # still, or its script turned it
                mt = rom_w(utype(a.b(u + 2)) + 0x3E)
                states, s = [(sp, cur)], (sp, cur)
                for mv, rot in ev:
                    if mv and move_turns and mt in (0, 1) and s[1] != tg:
                        s = turn_step(s[0], tg, s[1])
                        states.append(s)
                    if rot:
                        s = turn_step(s[0], tg, s[1])
                        states.append(s)
                got = (b.b(u + 0x68), b.b(u + 0x6A))
                # the frame's own events, or some of them if the pass ran
                # late, or one carried over from the frame before
                n = (ev[0][0] and move_turns and mt in (0, 1) and cur != tg) \
                    + ev[0][1]
                ok = got in states[:n + 2]
                late += ok and got != states[min(n, len(states) - 1)]
                c.that(ok, f"{st} {i}: type {a.b(u + 2)} facing "
                       f"{(sp, tg, cur)} -> {got}, predicted {states[n:n + 1]}")
    return late


@scenario("S3", "hull and turret turn by the type's rate, on rotation and (foot, tracked) movement ticks")
def s3_turn(c):
    late = s3_turns(c)
    c.that(late * 20 < c.count, f"{late} of {c.count} turns off by a frame")


@scenario("S3", "without the movement-tick turn of foot and tracked units it does not fit (control)")
def s3_turn_control(c):
    wrong = Check()
    s3_turns(wrong, move_turns=False)
    c.that(len(wrong.fails) >= 20, f"only {len(wrong.fails)} misfits")


def route_cases():
    """(before, after, unit, start, goal) for every route the machine
    worked out: +$7C goes from $FF to a direction while the unit is on a
    square."""
    out = []
    for st in S3_STATES:
        d = frames(st, 3000)
        for a, b in zip(d, d[1:]):
            for u in live_units(a, b):
                if a.b(u + 0x7C) != 0xFF or b.b(u + 0x7C) == 0xFF or \
                        a.l(u + 0x4E):
                    continue
                ref = b.w(u + 0x5C)
                goal = ref_square(a, ref)
                if a.b(u + 2) == 16 and ref >> 14 == 2:
                    s = struct_recs()[ref & 0x3FFF]
                    if a.b(s + 2) == 12:        # a Refinery's pad (emc_unit_step)
                        goal = square_of((a.l(s + 0xA) + 0x01000200) & 0xFFFFFFFF)
                out.append((a, b, u, square_of(a.l(u + 0xA)), goal))
    return out


def s3_routes(c, turns=(-1, 1)):
    detours = 0
    for a, b, u, start, goal in route_cases():
        def cb(s, d, a=a, u=u):
            return path_cost(a, u, s, d)

        route = path_find(start, goal, 40, cb, 255, turns)
        straight = path_find(start, goal, 40, lambda s, d: 0, 255)
        detours += route != straight
        got = upto_ff(b.b(u + 0x7C + j) for j in range(16))
        c.that(got in (upto_ff(route[:16]), upto_ff(route[1:16] + [0xFF])),
               f"type {a.b(u + 2)} {start}->{goal}: route {got}, "
               f"predicted {upto_ff(route[:16])}")
    return detours


@scenario("S3", "every route the machine works out is path_find's, detours included")
def s3_path(c):
    detours = s3_routes(c)
    c.that(c.count >= 40 and detours >= 4,
           f"{c.count} routes, {detours} detours: too few to say")


@scenario("S3", "following an obstacle's edge the other way round does not fit (control)")
def s3_path_control(c):
    wrong = Check()
    s3_routes(wrong, turns=(1, -1))
    c.that(len(wrong.fails) >= 1, "reversed edge following fits too")


@scenario("S3", "a step starts on the square ahead, with the ground's speed")
def s3_start(c):
    for st in S3_STATES[:4]:
        d = frames(st, 2000)
        for i, (a, b) in enumerate(zip(d, d[1:])):
            for u in live_units(a, b):
                if a.l(u + 0x4E) or not b.l(u + 0x4E):
                    continue
                ty = utype(a.b(u + 2))
                mt = rom_w(ty + 0x3E)
                if mt == 4:
                    continue
                face = b.b(u + 0x6A)
                p = a.l(u + 0xA)
                dy = rom_w(0x0714D6 + 2 * (face >> 5))
                dx = rom_w(0x0714C6 + 2 * (face >> 5))
                dst = ((p >> 16) + sbyte16(dy) & 0xFFFF) << 16 | (p + sbyte16(dx)) & 0xFFFF
                c.that(face & 0x1F == 0, f"{st} {i}: step facing {face}")
                c.that(b.l(u + 0x4E) == dst, f"{st} {i}: destination "
                       f"{b.l(u + 0x4E):#x}, predicted {dst:#x}")
                lt = landscape(a, square_of(dst))
                sp = land_speed(10 if lt == 12 else lt, mt)
                if a.b(u + 2) == 6 and lt == 11:
                    sp = 255
                if rom_w(ty + 0x10) >> 1 > a.w(u + 0x12):
                    sp -= sp >> 2
                c.that(b.b(u + 0x71) == sp, f"{st} {i}: type {a.b(u + 2)} "
                       f"onto ground {lt} got speed {b.b(u + 0x71)}, predicted {sp}")
                n = 0x20 if face & 0x3F == 0 else 0x28
                sin, cos = sbyte(rom()[0x06CFA4 + face]), sbyte(rom()[0x06D0A4 + face])
                c.that((sbyte16(b.w(u + 0x7A)), sbyte16(b.w(u + 0x78))) ==
                       ((-cos * n + 0x40) >> 7, (sin * n + 0x40) >> 7),
                       f"{st} {i}: step offsets for facing {face}")


def sbyte16(x):
    return x - 65536 if x > 32767 else x


# S4 - combat --------------------------------------------------------------

UNITS = 0xFF1000                  # 102 records of $8C (S2)
STRUCTS = 0xFF4EB8                # 73 records of $62 (S2)
# the two battles that start with the sides in reach of each other; the
# first 6000 frames of each hold ~130 shots and ~30 changes of target
S4_RUNS = (("pw-DOMINATION", 6000), ("pw-DEMOLITION", 6000))
S4_CHUNK = 1000


def s4_transitions(name, total):
    """(frame, before, after) for every frame of a long run, in chunks so
    that only two dumps are held at once.  Not cached."""
    prev, base = None, 0
    while base < total:
        n = min(S4_CHUNK, total - base)
        d = _frames(name, n, (f"run {base}",) if base else (), 1)
        if prev is not None:
            yield base - 1, prev, d[0]
        for i, (a, b) in enumerate(zip(d, d[1:])):
            yield base + i, a, b
        prev, base = d[-1], base + n


def u_rec(i):
    return UNITS + 0x8C * i


def u_used(r, i):
    return r.w(u_rec(i) + 4) & 1


def ut_w(t, off):
    return rom_w(utype(t) + off)


def shot_damage(r, shooter, projectile_type):
    """emc_unit_fire $0447E2: the type's damage (+$54), four times as much
    for a Fremen (house 3) Troopers or Trooper, less a quarter for the
    trooper's rocket (unit 22)."""
    t = r.b(u_rec(shooter) + 2)
    dm = ut_w(t, 0x54)
    if t in (3, 5) and r.b(u_rec(shooter) + 8) == 3:
        dm = dm * 4 & 0xFFFF
    if projectile_type == 22:
        dm -= dm >> 2
    return dm


def reload_values(t, hp):
    """What +$56 holds right after a shot: the type's +$50 doubled (a
    byte), plus 0 or 1 at random; 5 or 6 for the quick second shot of a
    type that fires twice while above half health."""
    base = ut_w(t, 0x50) * 2 & 0xFF
    out = {base, base + 1 & 0xFF}
    if ut_w(t, 0x38) >> 10 & 1 and hp > ut_w(t, 0x10) >> 1:
        out |= {5, 6}
    return out


def ref_position(r, ref):
    """ref_position $02E256 for the three kinds."""
    kind, v = ref >> 14, ref & 0x3FFF
    if kind == 1:
        return r.l(u_rec(v) + 0xA)
    if kind == 2:
        return r.l(STRUCTS + 0x62 * v + 0xA)
    if kind == 3:
        return (v >> 6) << 24 | 0x80 << 16 | (v & 63) << 8 | 0x80
    return None


def enemy_candidates(r, u, mode):
    """unit_find_enemy_unit $04730C, as it runs: the units of the other
    side's list ($020708 with house_are_allied(unit, player)), in list
    order, that its house has seen, that are allocated, stand inside the
    playable map, are no flyer unless it can hit flyers, pass the mode's
    range and are not on its own square.  Every one of them scores 1
    (see S4), so the answer is the first."""
    o = u_rec(u)
    house, t = r.b(o + 8), r.b(o + 2)
    head = 0xFFDBE4 if allied(r, house, r.w(0xFFC274)) else 0xFFDBE8
    rng = ut_w(t, 0x52) << 8
    if mode == 2:
        rng <<= 1
    org = r.w(o + 0x52)
    home = ref_position(r, org) if org else r.l(o + 0xA)
    out = []
    for n in walk(r, head):
        v = r.w(n)
        vo = u_rec(v)
        if not r.b(vo + 9) >> house & 1 or not r.w(vo + 4) & 2:
            continue
        if not valid_square(r, square_of(r.l(vo + 0xA))):
            continue
        if ut_w(r.b(vo + 2), 0x3E) == 4 and not ut_w(t, 0x0C) >> 12 & 1:
            continue
        dist = tile_distance(r.l(o + 0xA), r.l(vo + 0xA))
        if mode == 1 and dist > rng:
            continue
        if mode == 2 and tile_distance(home, r.l(vo + 0xA)) > rng:
            continue
        if (dist + 0x80) >> 8 & 0xFFFF == 0:
            continue
        out.append(v)
    return out


def pc_priority_best(r, u, mode):
    """The PC's choice over the same units: Unit_GetTargetUnitPriority,
    (priorityTarget + priorityBuild) / distance + 1, the highest kept."""
    best, bp = None, 0
    for v in enemy_candidates(r, u, mode):
        vt = r.b(u_rec(v) + 2)
        dd = (tile_distance(r.l(u_rec(u) + 0xA), r.l(u_rec(v) + 0xA))
              + 0x80) >> 8
        p = ut_w(vt, 0x2E) + ut_w(vt, 0x30)
        p = min(p // dd + 1 if dd else p, 0x7D00)
        if p > bp:
            best, bp = v, p
    return best


_S4 = None


def s4_events():
    """One pass over S4_RUNS, collecting what the scenarios test."""
    global _S4
    if _S4 is not None:
        return _S4
    ev = {"shots": [], "hits": [], "shits": [], "targets": [], "scores": []}
    for name, total in S4_RUNS:
        pending, pending_scores = [], []
        for f, a, b in s4_transitions(name, total):
            # projectiles that went this frame: gone before b, or moved on
            gone = []
            for i in range(12, 22):
                o = u_rec(i)
                if u_used(a, i) and a.b(o + 2) != 24 and not (
                        u_used(b, i) and b.w(o + 0x52) == a.w(o + 0x52)
                        and b.l(o + 0x4E) == a.l(o + 0x4E)
                        and b.b(o + 2) == a.b(o + 2)):
                    gone.append(a.w(o + 0x12))
                # a new projectile, and who fired it
                if u_used(b, i) and not (u_used(a, i) and a.w(o + 0x52)
                                         == b.w(o + 0x52)
                                         and a.b(o + 2) == b.b(o + 2)):
                    org = b.w(o + 0x52)
                    if org >> 14 == 1:
                        s = org & 0x3FFF
                        ev["shots"].append((name, f, b.b(u_rec(s) + 2),
                                            b.b(o + 2), b.w(o + 0x12),
                                            shot_damage(b, s, b.b(o + 2)),
                                            b.b(u_rec(s) + 0x56),
                                            reload_values(b.b(u_rec(s) + 2),
                                                          b.w(u_rec(s) + 0x12)),
                                            a.l(MOVE_T) != b.l(MOVE_T)))
            # a hit shows in the frame the projectile goes, or the one
            # before (the unit loop can end a frame between the explosion
            # and the unit_remove that frees it) - so hits wait a frame
            for p in pending:
                p[-1] = p[-1] + gone
                (ev["hits"] if p[0] == "u" else ev["shits"]).append(tuple(p))
            pending = []
            for i in list(range(12)) + list(range(22, 102)):
                o = u_rec(i)
                if not (u_used(a, i) and u_used(b, i)) or a.b(o + 2) != b.b(o + 2):
                    continue
                dh = a.w(o + 0x12) - b.w(o + 0x12)
                if dh > 0 and b.w(o + 0x12):
                    pending.append(["u", name, f, b.b(o + 2), dh, list(gone)])
            for i in range(73):
                o = STRUCTS + 0x62 * i
                if not (a.w(o + 4) & 1 and b.w(o + 4) & 1):
                    continue
                dh = a.w(o + 0x12) - b.w(o + 0x12)
                if dh > 0 and b.w(o + 0x12) != b.w(o + 0x5E):
                    pending.append(["s", name, f, b.b(o + 2), dh, list(gone)])
            # new unit targets
            shooters = {a.w(u_rec(j) + 0x52) & 0x3FFF for j in range(12, 22)
                        if u_used(a, j)}
            shooters |= {b.w(u_rec(j) + 0x52) & 0x3FFF for j in range(12, 22)
                         if u_used(b, j)}
            for u in list(range(12)) + list(range(22, 102)):
                o = u_rec(u)
                if not (u_used(a, u) and u_used(b, u)) or a.b(o + 2) != b.b(o + 2):
                    continue
                t0, t1 = a.w(o + 0x5A), b.w(o + 0x5A)
                if t1 == t0 or t1 >> 14 != 1 or b.b(o + 2) == 16:
                    continue
                v = t1 & 0x3FFF
                firsts = [c[0] if c else None for c in
                          (enemy_candidates(a, u, m) for m in (0, 1, 2))]
                pcs = [pc_priority_best(a, u, m) for m in (0, 1, 2)]
                ev["targets"].append((name, f, u, v, firsts, pcs,
                                      v in shooters, a.b(o + 0x54)))
            # the score and the two kill counters; the unit that died may
            # be freed in the frame after (as for hits)
            freed = [(a.b(u_rec(i) + 2), a.b(u_rec(i) + 8))
                     for i in range(102) if u_used(a, i) and not u_used(b, i)]
            for p in pending_scores:
                p[-1] = p[-1] + freed
                ev["scores"].append(tuple(p))
            pending_scores = []
            if (a.w(0xFFC096), a.w(0xFFC098)) != (b.w(0xFFC096), b.w(0xFFC098)):
                pending_scores.append([name, f, a.w(0xFFC05E), b.w(0xFFC05E),
                                       b.w(0xFFC096) - a.w(0xFFC096),
                                       b.w(0xFFC098) - a.w(0xFFC098), freed])
    _S4 = ev
    return ev


def falloff(ds, steps=4):
    """map_make_explosion $00A934: damage >> (distance / 64), and only
    within 16 sixteenths of a square - so D, D/2, D/4 or D/8."""
    return {d >> k for d in ds for k in range(steps)}


@scenario("S4", "a projectile carries its shooter's damage, as emc_unit_fire makes it")
def s4_projectile(c):
    for name, f, st, pt, hp, want, _, _, _ in s4_events()["shots"]:
        c.that(hp == want, f"{name} frame {f}: unit {st}'s shot (type {pt}) "
               f"carries {hp}, the spec says {want}")


@scenario("S4", "the PC's damage table does not give the projectiles' damage (control)")
def s4_projectile_control(c):
    pc = {2: 3, 3: 5, 4: 3, 5: 5, 6: 2, 7: 75, 8: 0, 9: 25, 10: 30, 11: 40,
          12: 60, 13: 5, 14: 5, 15: 7}           # OpenDUNE g_table_unitInfo
    shots = s4_events()["shots"]
    bad = sum(hp != pc.get(st, hp) for _, _, st, _, hp, _, _, _, _ in shots)
    c.that(bad > len(shots) // 2, f"only {bad} of {len(shots)} shots differ")


@scenario("S4", "after a shot the reload is the type's +$50 doubled, plus 0 or 1")
def s4_reload(c):
    for name, f, st, _, _, _, fd, want, ticked in s4_events()["shots"]:
        # a shot first seen a frame late may have had a movement tick
        # taken off its reload already
        c.that(fd in want or ticked and fd + 1 in want, f"{name} frame {f}: "
               f"unit {st} reloads with {fd}, the spec says {sorted(want)}")


@scenario("S4", "reloading the PC's way (+$50 doubled at normal speed, twice this) does not fit (control)")
def s4_reload_control(c):
    shots = s4_events()["shots"]
    bad = sum(fd not in {ut_w(st, 0x50) * 4 & 0xFF, ut_w(st, 0x50) * 4 + 1 & 0xFF}
              for _, _, st, _, _, _, fd, _, _ in shots)
    c.that(bad > len(shots) // 2, f"only {bad} of {len(shots)} reloads differ")


@scenario("S4", "a hit takes D >> (distance / 64) from a unit, D from a structure")
def s4_damage(c):
    ev = s4_events()
    for _, name, f, t, dh, gone in ev["hits"]:
        c.that(dh in falloff(gone), f"{name} frame {f}: a unit of type {t} "
               f"lost {dh}, projectiles gone {gone}")
    for _, name, f, t, dh, gone in ev["shits"]:
        c.that(dh in gone, f"{name} frame {f}: a structure of type {t} "
               f"lost {dh}, projectiles gone {gone}")
    c.that(len(ev["hits"]) > 20, f"only {len(ev['hits'])} hits seen")


@scenario("S4", "without the falloff the unit hits do not fit (control)")
def s4_damage_control(c):
    hits = s4_events()["hits"]
    bad = sum(dh not in falloff(gone, 1) for _, _, _, _, dh, gone in hits)
    c.that(bad > 5, f"only {bad} of {len(hits)} hits need the falloff")


MODE_OF_ORDER = {11: 0, 3: 1, 4: 2}        # UNIT.EMC: Hunt, Guard, Area Guard


@scenario("S4", "a new unit target is the first eligible enemy in the side list, or the shooter")
def s4_target(c):
    ev = s4_events()["targets"]
    for name, f, u, v, firsts, _, shooter, order in ev:
        m = MODE_OF_ORDER.get(order)
        ok = shooter or (v == firsts[m] if m is not None else v in firsts)
        c.that(ok, f"{name} frame {f}: unit {u} (order {order}) took unit "
               f"{v}; first eligible by mode {firsts}")
    c.that(len(ev) > 20, f"only {len(ev)} targets taken")
    # No control here: in these runs a Guard unit never has two enemies in
    # range and a Hunt unit only takes targets by reaction, so "first in
    # the list" and the PC's "best value over distance" always agree.  The
    # spec's reading of $0474D6 is from the code alone (S4, targeting).


@scenario("S4", "a unit's death moves the score by its cost / 100 and counts it")
def s4_score(c):
    ev = s4_events()["scores"]
    for name, f, s0, s1, lost, killed, dead in ev:
        c.that(lost + killed == 1, f"{name} frame {f}: {lost} lost and "
               f"{killed} killed in one frame")
        deltas = {max(ut_w(t, 0x16) // 100, 1) * (1 if killed else -1)
                  for t, _ in dead if ut_w(t, 0x3E) != 4}
        d = s1 - s0
        c.that(d in deltas or (lost and s1 == 0), f"{name} frame {f}: the "
               f"score moved {d}, the dead are worth {sorted(deltas)}")
    c.that(len(ev) >= 2, f"only {len(ev)} deaths seen")



# ---------------------------------------------------------- the driver

def load_spec_modules():
    """Scenarios may also live beside this file as spec_s<N>.py, one module
    a spec.  They run in this module's namespace, so `scenario`, `frames`,
    `Check` and the rest are theirs to use without importing."""
    import runpy
    for p in sorted(Path(__file__).resolve().parent.glob("spec_s*.py")):
        runpy.run_path(str(p), init_globals=globals())


def main():
    load_spec_modules()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("specs", nargs="*", help="S1, S2 ... (default: all)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    todo = [s for s in SCENARIOS if not args.specs or s[0] in args.specs]
    if args.list:
        for spec, name, what, _ in todo:
            print(f"{spec:<4} {name:<18} {what}")
        return
    bad = 0
    for spec, name, what, f in todo:
        c = Check()
        f(c)
        ok = not c.fails and c.count
        bad += not ok
        print(f"{'pass' if ok else 'FAIL'}  {spec:<4} {name:<18} "
              f"{c.count} checks  {what}")
        for m in c.fails[:8]:
            print(f"        {m}")
        if len(c.fails) > 8:
            print(f"        ... and {len(c.fails) - 8} more")
    print(f"{len(todo) - bad} of {len(todo)} scenarios pass")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
