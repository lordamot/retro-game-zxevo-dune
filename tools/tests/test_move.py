#!/usr/bin/env python3
"""test_move.py - the MOVE subsystem (S1 units, S3) on the running machine,
against the S3 models of tools/sega/sega_spec_check.py.

    python3 tools/tests/test_move.py [--build-dir build] [--only NAME]

Every group is one evo-run: Harkonnen mission 8 (64 x 64, walls, concrete,
the structures and units of five houses) is loaded through start_mission,
records are poked, and MOVE's routines are far-called.  sega_spec_check's
models then run on the port's own pages (tools/tests/rig.py's PortRam), so
a route, a cost or a step is predicted from exactly the RAM the port had.

  speed    unit_set_speed: speed, speedPerTick, the remainder and
           movingSpeed for random types and speeds (S3 "Speed")
  turn     unit_set_facing and unit_turn_step, hull and turret, the sign
           of the turn and the snap (S3 "Turning")
  enter    unit_tile_enter_score / unit_can_enter_structure on the
           mission's squares, units and structures, with poked units of
           other houses, deviated units, Saboteurs and filters (S3 "The
           cost of a square")
  start    unit_start_step: the facing squared, the square ahead, the
           cost test, the ground's speed with the Saboteur and health
           rules, wobble, the step offsets and the claim (S3 "A step")
  tick     mv_unit_move_tick: turning on the spot, the carry, the fixed
           ground step, flying along the facing, arrival and its
           bookkeeping (snap, +$60/+$64, targetMove), crushing (S3)
  path     mv_path_find against path_find/follow_edge/smooth over the
           mission map with walls and mountains poked in: straight runs,
           detours both ways, the diagonal squeeze, dead ends
  step     UNIT 12 step: arrived, off the map, a route planned and cut,
           the hull turned, a step started and the route shifted, blocked,
           the Harvester's pad, giving up an attack (S3 "Planning a route")
  fly      UNIT 22 fly.to: slide and land, the pads, the speed and the
           delay far out, with the port's wrapped angle (S3 "Flying")
  loop     unit_tick_all (S1 "Units"): the six timers' firing and next due
           times, then the turret aim, the movement tick's turn and the
           reload, rotation, deviation wear, back on the map, the walking
           and harvesting animations, the script delay and the queued order

The path model is sega_spec_check.path_find, which these tests corrected:
walking the blocked line, a square that can be entered starts the edge
following even when it is the goal ($012B8C) - the port had it right.
"""
import argparse
import random as R
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rig import (Rig, Suite, Tally, S, ALL, PG_UNITS, U_SIZE, UNITS,   # noqa: E402
                 ORDER, O_SCRIPT, SC_PC, REF_UNIT, REF_STRUCT, MD_PLAYER,
                 md_unit, md_struct, unit_rec, with_arg, tile_ref, ut, w16,
                 s16, put16, ROOT, probe, free_squares, sq_of, tile_direction,
                 ref_pos, ref_valid, tile_distance_packed)
import rig                              # noqa: E402

HOUSE, MISSION = 0, 8            # H8
SLOT = 90                        # the unit under test (a ground slot)
UREC = UNITS + SLOT * U_SIZE
MU = md_unit(SLOT)
GROUND = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
ICON_LS = S.rom()[0x005818:0x005818 + 512]


def icon_of(landscape):
    """A ground icon of that landscape type (map_get_landscape_type's table)."""
    return next(i for i in range(512) if ICON_LS[i] == landscape)


def pos_of(p):
    return p >> 16, p & 0xFFFF


def mt_of(t):
    return ut(t, 0x3E)


# ---------------------------------------------------------------- models

def set_facing(t, sp, tg, cur, f, at_once):
    """unit_set_facing $047E1C."""
    sp, tg = 0, f
    if at_once:
        return 0, f, f
    if cur == f:
        return 0, f, cur
    sp = ut(t, 0x44) * 4 & 0xFF
    diff = f - cur
    if -128 < diff < 0 or diff > 128:
        sp = -sp & 0xFF
    return sp, tg, cur


def speed_fields(t, s):
    """unit_set_speed $047F44 -> (speed, perTick, remainder, movingSpeed)."""
    if s == 0:
        return 0, 0, 0, 0
    sp, pt = S.speed_fields(t, s)
    return sp, pt, 0, s


def step_offsets(f):
    """tile_dir_offset_y/_x for a step at facing f (an eighth)."""
    n = 0x20 if f & 0x3F == 0 else 0x28
    sin, cos = S.sbyte(S.rom()[0x06CFA4 + f]), S.sbyte(S.rom()[0x06D0A4 + f])
    return (-cos * n + 0x40) >> 7 & 0xFFFF, (sin * n + 0x40) >> 7 & 0xFFFF


def pos_step(y, x, f):
    """map_pos_step $019AD8: a square ahead, the sub-square part kept."""
    d = f >> 5
    dy = S.sbyte16(S.rom_w(0x0714D6 + 2 * d))
    dx = S.sbyte16(S.rom_w(0x0714C6 + 2 * d))
    return (y + dy) & 0xFFFF, (x + dx) & 0xFFFF


# path_find $012AAE with path_follow_edge and path_smooth: the S3 model
# (sega_spec_check.path_find, which these tests corrected: a square that can
# be entered on the blocked line starts the edge following even when it is
# the goal - the port and the cartridge agree, $012B8C)
path_find = S.path_find


def route_of(ram, u, start, goal):
    return path_find(start, goal, 40, lambda s, d: S.path_cost(ram, u, s, d), 255)


# ---------------------------------------------------------------- groups

def g_speed(b, out):
    R.seed(21)
    rg = Rig(b, HOUSE, MISSION)
    cases = []
    for _ in range(90):
        t = R.randrange(27)
        s = R.choice([0, 255, 112, 160, 64, 192, R.randrange(1, 32),
                      R.randrange(1, 256), R.randrange(1, 256)])
        rec = unit_rec(SLOT, t, 1, 0x2080, 0x2080)
        rec[0x6E:0x72] = bytes(R.randrange(256) for _ in range(4))
        rg.poke_unit(SLOT, rec)
        cases.append((t, s, rg.call("unit_set_speed", ix=UREC, a=s, frames=1,
                                    pages=(PG_UNITS,))))
    rg.run()
    T = Tally(out)
    for t, s, step in cases:
        u = rg.unit(step, SLOT)
        got = (u[0x70], u[0x6E], u[0x6F], u[0x71])
        exp = speed_fields(t, s)
        T.check(got == exp, lambda: f"type {t} speed {s}: (speed, perTick, "
                f"rem, moving) {got}, expected {exp}")
    return T.ok, T.bad, rg


def g_turn(b, out):
    R.seed(22)
    rg = Rig(b, HOUSE, MISSION)
    cases = []
    for _ in range(45):
        t = R.choice([0, 1, 2, 4, 6, 7, 9, 10, 11, 13, 15, 16, 17, 25])
        which = R.randrange(2)
        cur = R.randrange(256)
        f = R.choice([R.randrange(256), cur, cur + 128, cur + 129, cur + 127,
                      cur - 3, cur + 5, cur + 200]) & 0xFF
        at_once = R.random() < 0.15
        rec = unit_rec(SLOT, t, 1, 0x2080, 0x2080)
        o = 0x68 + 3 * which
        rec[o], rec[o + 1], rec[o + 2] = R.randrange(256), R.randrange(256), cur
        rg.poke_unit(SLOT, rec)
        s0 = rg.call("unit_set_facing", ix=UREC, a=f, bc=int(at_once) << 8 | which,
                     frames=1, pages=(PG_UNITS,))
        turns = [rg.call("unit_turn_step", ix=UREC, bc=which, frames=1,
                         pages=(PG_UNITS,)) for _ in range(4)]
        cases.append((t, which, cur, f, at_once, s0, turns))
    rg.run()
    T = Tally(out)
    for t, which, cur, f, at_once, s0, turns in cases:
        o = 0x68 + 3 * which
        st_ = set_facing(t, 0, 0, cur, f, at_once)
        u = rg.unit(s0, SLOT)
        T.check(tuple(u[o:o + 3]) == st_, lambda: f"set_facing type {t} "
                f"{'turret' if which else 'hull'} {cur}->{f} at once {at_once}: "
                f"{tuple(u[o:o + 3])}, expected {st_}")
        sp, tg, c = st_
        for n, s in enumerate(turns):
            sp, c = S.turn_step(sp, tg, c)
            u = rg.unit(s, SLOT)
            got = (u[o], u[o + 2])
            T.check(got == (sp, c), lambda: f"turn_step {n + 1} type {t} "
                    f"{cur}->{f}: (speed, current) {got}, expected {(sp, c)}")
    return T.ok, T.bad, rg


def g_enter(b, out):
    R.seed(23)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    # units of every house on the map, some deviated; soldiers among them
    others = {}
    for slot in range(70, 86):
        sq = R.choice(free)
        free.remove(sq)
        t = R.choice([2, 4, 4, 3, 5, 9, 13, 16, 6])
        h = R.choice([0, 1, 2, 4, 5])
        rec = unit_rec(slot, t, h, (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80)
        if R.random() < 0.2:
            rec[0x5F] = 60
        rg.poke_unit(slot, rec)
        rg.poke_sq(sq, flags=(ram0.b(S.MAP + 4 * sq + 2) & 0xCF) | 0x10, index=slot + 1)
        others[slot] = sq
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    # squares to try: round the poked units, the structures, walls, edges
    spots = list(others.values())
    for n in structs:
        base = md_struct(n)
        spots.append(ram0.b(base + 0xA) * 64 + ram0.b(base + 0xC))
    walls = [sq for sq in range(4096) if S.landscape(ram0, sq) in (11, 6, 7, 10)]
    cases = []
    for i in range(160):
        t = R.choice(GROUND + [6, 6, 25, 1, 0])
        h = R.choice([0, 0, 1, 2, 4])
        rec = unit_rec(SLOT, t, h, 0x2080, 0x2080)
        if R.random() < 0.2:
            rec[0x5F] = 40
        tm = R.random()
        if tm < 0.3:
            tgt = R.choice(list(others))
            put16(rec, 0x5C, REF_UNIT | tgt)
        elif tm < 0.55 and structs:
            put16(rec, 0x5C, REF_STRUCT | R.choice(structs))
        elif tm < 0.7:
            put16(rec, 0x5C, tile_ref(R.randrange(4096)))
        rg.poke_unit(SLOT, rec)
        if structs and R.random() < 0.3:
            # a structure of the unit's house expecting it, or linked
            n = R.choice(structs)
            rg.poke_struct(n, 0x2A, [SLOT, 0x40] if R.random() < 0.5 else [0, 0])
            rg.poke_struct(n, 0x03, [R.choice([0xFF, 0xFF, 5])])
            rg.poke_struct(n, 0x08, [R.choice([h, h, 1, 2])])
        k = R.random()
        if k < 0.45:
            sq = R.choice(spots) + R.choice([0, 1, -1, 64, -64, 65, -63, 0, 0])
        elif k < 0.6:
            sq = R.choice(walls)
        elif k < 0.7:
            sq = R.choice([R.randrange(64), 63 * 64 + R.randrange(64),
                           R.randrange(64) * 64, R.randrange(64) * 64 + 63])
        else:
            sq = R.randrange(4096)
        o = R.choice([R.randrange(8), R.randrange(8) << 5])
        cases.append((t, sq & 0xFFF, o, rg.call("unit_tile_enter_score", ix=UREC,
                                                 hl=sq & 0xFFF, a=o, frames=2)))
    # aimed at what may be entered: a Saboteur at the unit or the enemy
    # structure it is sent to, a soldier at a structure that can be taken,
    # a unit at its own house's structure (its filter, expected or not)
    for i in range(70):
        n = R.choice(structs)
        base = md_struct(n)
        stype, shouse = ram0.b(base + 2), ram0.b(base + 8)
        ssq = ram0.b(base + 0xA) * 64 + ram0.b(base + 0xC)
        filt = S.rom_l(S.btype(stype) + 0x34)
        kind = R.choice(["sab_unit", "sab_struct", "soldier", "own", "own"])
        sq = ssq
        if kind == "sab_unit":
            t, h = 6, R.choice([0, 1, 2])
            v = R.choice(list(others))
            sq = others[v]
            tm = R.choice([REF_UNIT | v, REF_UNIT | v, 0])
        elif kind == "sab_struct":
            t, h = 6, R.choice([hh for hh in (0, 1, 2, 4) if hh != shouse])
            tm = R.choice([REF_STRUCT | n, 0])
        elif kind == "soldier":
            t, h = R.choice([2, 3, 4, 5]), R.choice([hh for hh in (0, 1, 2, 4) if hh != shouse])
            tm = R.choice([REF_STRUCT | n, 0])
        else:
            fits = [ty for ty in range(27) if filt >> ty & 1]
            t, h = R.choice(fits or GROUND), shouse
            tm = R.choice([REF_STRUCT | n, 0])
            rg.poke_struct(n, 0x2A, [SLOT, 0x40] if R.random() < 0.5 else [0, 0])
            rg.poke_struct(n, 0x03, [R.choice([0xFF, 0xFF, 5])])
        rec = unit_rec(SLOT, t, h, 0x2080, 0x2080)
        put16(rec, 0x5C, tm)
        rg.poke_unit(SLOT, rec)
        o = R.randrange(8) << 5
        cases.append((t, sq, o, rg.call("unit_tile_enter_score", ix=UREC, hl=sq,
                                        a=o, frames=2)))
    rg.run()
    T = Tally(out)
    kinds = {}
    for t, sq, o, step in cases:
        ram = rg.ram(step)
        exp = S.enter_score(ram, MU, sq, o)
        got = s16(bytes([rg.regs(step)["hl"] & 0xFF, rg.regs(step)["hl"] >> 8]), 0)
        key = exp if exp <= 0 or exp == 256 else "ground"
        kinds[key] = kinds.get(key, 0) + 1
        T.check(got == exp, lambda: f"type {t} square {sq} o {o}: {got}, expected {exp}")
    out.append(f"  (cases by answer: {kinds})")
    return T.ok, T.bad, rg


def g_start(b, out):
    R.seed(24)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    near = [sq for sq in free if any(ram0.b(S.MAP + 4 * (sq + d) + 2) & 0x30 or
                                     S.landscape(ram0, sq + d) in (6, 7, 11, 10)
                                     for d in (-65, -64, -63, -1, 1, 63, 64, 65))]
    cases = []
    for i in range(70):
        t = R.choice(GROUND + [6, 6, 25])
        h = R.choice([0, 1, 2, 4])
        sq = R.choice(near if R.random() < 0.7 else free)
        y = (sq >> 6) << 8 | R.randrange(256)
        x = (sq & 63) << 8 | R.randrange(256)
        hpmax = ut(t, 0x10)
        hp = R.choice([hpmax, hpmax, R.randrange(1, max(2, hpmax))])
        rec = unit_rec(SLOT, t, h, y, x, hp=hp)
        rec[0x68], rec[0x69], rec[0x6A] = R.randrange(256), R.randrange(256), R.randrange(256)
        rec[0x6B], rec[0x6C], rec[0x6D] = 0, R.randrange(256), R.randrange(256)
        rec[0x6E:0x72] = bytes(R.randrange(256) for _ in range(4))
        put16(rec, 0x58, R.randrange(65536))
        if R.random() < 0.3:
            put16(rec, 0x5C, tile_ref(sq + R.choice([1, 64, -1, -64])))
        rg.poke_unit(SLOT, rec)
        pre = probe(rg)
        cases.append((t, sq, pre, rg.call("unit_start_step", ix=UREC, frames=4)))
    rg.run()
    T = Tally(out)
    started = 0
    for t, sq, pre, step in cases:
        a = rg.ram(pre)
        u0 = rg.unit(pre, SLOT)
        u = rg.unit(step, SLOT)
        mt = mt_of(t)
        f = (u0[0x6A] + 16) & 0xE0
        ny, nx = pos_step(w16(u0, 0x0A), w16(u0, 0x0C), f)
        nsq = sq_of(ny, nx)
        score = S.enter_score(a, MU, nsq, f >> 5)
        can = not (score > 255 or score == -1)
        exp = {"answer": int(can), "hull": (0, f, f),
               "turret": set_facing(t, u0[0x6B], u0[0x6C], u0[0x6D], f, False),
               "distdest": 0x7FFF}
        got = {"answer": rg.regs(step)["a"], "hull": tuple(u[0x68:0x6B]),
               "turret": tuple(u[0x6B:0x6E]), "distdest": w16(u, 0x58)}
        if can:
            started += 1
            lt = S.landscape(a, nsq)
            lt = 10 if lt == 12 else lt
            sp = S.land_speed(lt, mt)
            if t == 6 and lt == 11:
                sp = 255
            if mt != 4 and hpmax_half(t) > s16(u0, 0x12):
                sp -= sp >> 2
            exp["speed"] = speed_fields(t, sp)
            got["speed"] = (u[0x70], u[0x6E], u[0x6F], u[0x71])
            exp["wobble"] = int(S.rom_w(0x06CCB4 + 28 * lt) != 0)
            got["wobble"] = u[4] >> 7 & 1
            exp["dest"] = (ny, nx)
            got["dest"] = (w16(u, 0x4E), w16(u, 0x50))
            exp["step"] = step_offsets(f)
            got["step"] = (w16(u, 0x7A), w16(u, 0x78))
            held = a.b(S.MAP + 4 * nsq + 3) and a.b(S.MAP + 4 * nsq + 2) & 0x30
            if mt != 5 and not held:
                mp = rg.page(step, 26)
                exp["claim"] = (1, SLOT + 1)
                got["claim"] = (mp[0x2000 + nsq] >> 4 & 1, mp[0x3000 + nsq])
        else:
            exp["dest"] = (0, 0)
            got["dest"] = (w16(u, 0x4E), w16(u, 0x50))
            exp["speed"] = tuple(u0[k] for k in (0x70, 0x6E, 0x6F, 0x71))
            got["speed"] = tuple(u[k] for k in (0x70, 0x6E, 0x6F, 0x71))
        for k in exp:
            T.check(got[k] == exp[k], lambda: f"type {t} at {sq} facing {u0[0x6A]} "
                    f"onto {nsq} (score {score}): {k} {got[k]}, expected {exp[k]}")
    out.append(f"  ({started} of {len(cases)} steps started)")
    return T.ok, T.bad, rg


def hpmax_half(t):
    v = ut(t, 0x10)
    return (v - 0x10000 if v & 0x8000 else v) >> 1


def g_tick(b, out):
    R.seed(25)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    freeset = set(free)
    inner = [sq for sq in free if all(sq + d in freeset for d in
                                      (-65, -64, -63, -1, 1, 63, 64, 65))]
    cases = []
    for i in range(110):
        kind = R.random()
        f = R.randrange(8) << 5
        sq = R.choice(inner)
        y0 = (sq >> 6) << 8 | R.randrange(256)
        x0 = (sq & 63) << 8 | R.randrange(256)
        if kind < 0.72:                       # a ground unit on its step
            t = R.choice(GROUND)
            dy, dx = pos_step(y0, x0, f)
            sy, sx = step_offsets(f)
            k = R.randrange(9)
            y = (y0 + S.sbyte16(sy) * k) & 0x3FFF
            x = (x0 + S.sbyte16(sx) * k) & 0x3FFF
            rec = unit_rec(SLOT, t, R.choice([0, 1, 2]), y, x, face=f)
            put16(rec, 0x4E, dy)
            put16(rec, 0x50, dx)
            put16(rec, 0x7A, sy)
            put16(rec, 0x78, sx)
            put16(rec, 0x58, 0x7FFF if k == 0 else
                  S.tile_distance(y << 16 | x, dy << 16 | dx) + R.choice([0, 0, 1, -1, 30]))
            if mt_of(t) in (0, 1) and R.random() < 0.15:
                rec[0x69] = R.randrange(256)          # still turning to it
                rec[0x68] = set_facing(t, 0, 0, f, rec[0x69], False)[0]
            if R.random() < 0.4:
                put16(rec, 0x5C, tile_ref(sq_of(dy, dx)))
        else:                                # a flyer
            t = R.choice([1, 1, 0])
            rec = unit_rec(SLOT, t, R.choice([0, 1, 2]), y0, x0, face=R.randrange(256))
            dy = (y0 + R.randrange(-1500, 1500)) & 0x3FFF
            dx = (x0 + R.randrange(-1500, 1500)) & 0x3FFF
            put16(rec, 0x4E, dy)
            put16(rec, 0x50, dx)
            put16(rec, 0x58, R.choice([0x7FFF, R.randrange(3000)]))
        s = R.choice([R.randrange(1, 256), 255, 160, 112, 64])
        sp, pt, _, mv = speed_fields(t, s)
        rec[0x6E], rec[0x6F], rec[0x70], rec[0x71] = pt, R.randrange(256), sp, mv
        if R.random() < 0.05:
            rec[0x70] = 0
        put16(rec, 0x60, R.randrange(0x4000))
        put16(rec, 0x62, R.randrange(0x4000))
        put16(rec, 0x64, R.randrange(0x4000))
        put16(rec, 0x66, R.randrange(0x4000))
        rg.poke_unit(SLOT, rec)
        pre = probe(rg)
        cases.append((t, pre, rg.call("mv_unit_move_tick", ix=UREC, frames=3)))
    # crushing: a tank's last carry onto an enemy / an allied soldier
    crush = []
    for i in range(8):
        sq = R.choice(inner)
        f = 64                                   # east
        y0, x0 = (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80
        dy, dx = pos_step(y0, x0, f)
        near = i % 4 != 3
        x = dx - (0x20 if near else 0x60)        # the carry lands within 48 or not
        victim_house = 1 if i % 2 == 0 else 0    # Atreides: an enemy of H
        rec = unit_rec(SLOT, 9, 0, y0, x, face=f)
        put16(rec, 0x4E, dy)
        put16(rec, 0x50, dx)
        put16(rec, 0x7A, 0)
        put16(rec, 0x78, 0x20)
        put16(rec, 0x58, 0x7FFF)
        rec[0x6E], rec[0x6F], rec[0x70], rec[0x71] = 255, 200, 1, 160
        rg.poke_unit(SLOT, rec)
        vslot = 60
        vsq = sq_of(y0, x + 0x20)
        vrec = unit_rec(vslot, 4, victim_house, (vsq >> 6) << 8 | 0x80,
                        (vsq & 63) << 8 | 0x80, action=ORDER["guard"])
        rg.poke_unit(vslot, vrec)
        rg.poke_sq(vsq, flags=(ram0.b(S.MAP + 4 * vsq + 2) & 0xCF) | 0x10, index=vslot + 1)
        crush.append((near, victim_house, vsq,
                      rg.call("mv_unit_move_tick", ix=UREC, frames=4)))
    rg.run()
    T = Tally(out)
    arrivals = moves = 0
    for t, pre, step in cases:
        a = rg.ram(pre)
        u0 = rg.unit(pre, SLOT)
        u = rg.unit(step, SLOT)
        mt, flags = mt_of(t), ut(t, 0x38)
        p = a.l(MU + 0xA)
        dst = a.l(MU + 0x4E)
        exp = {"pos": p, "rem": u0[0x6F], "hull": tuple(u0[0x68:0x6B]),
               "speed": (u0[0x70], u0[0x6E], u0[0x71]), "dest": dst,
               "last": (a.l(MU + 0x60), a.l(MU + 0x64)), "tmove": a.w(MU + 0x5C),
               "distdest": a.w(MU + 0x58), "flip": u0[4] >> 5 & 1}
        if mt in (0, 1) and u0[0x69] != u0[0x6A]:
            sp, c = S.turn_step(u0[0x68], u0[0x69], u0[0x6A])
            exp["hull"] = (sp, u0[0x69], c)
        elif u0[0x70]:
            tot = u0[0x6F] + u0[0x6E]
            exp["rem"] = tot & 0xFF
            if tot >= 256:
                if mt == 4:
                    n = min(u0[0x70] * 16, S.tile_distance(p, dst) + 16, 255)
                    q = S.move_by_direction(p, u0[0x6A], n)
                else:
                    q = ((p >> 16) + w16(u0, 0x7A) & 0x3FFF) << 16 | \
                        ((p & 0xFFFF) + w16(u0, 0x78)) & 0x3FFF
                if q != p:
                    moves += 1
                    d = S.tile_distance(q, dst)
                    arrived = d > a.w(MU + 0x58) or d <= 12
                    exp["distdest"] = d
                    exp["pos"] = q
                    if mt == 4:
                        exp["flip"] ^= 1
                    if arrived and flags & 0x40:
                        arrivals += 1
                        exp["pos"] = dst if dst else q
                        exp["last"] = (p, a.l(MU + 0x60))
                        exp["dest"] = 0
                        exp["speed"] = (0, 0, 0)
                        if a.w(MU + 0x5C) == tile_ref(S.square_of(q)):
                            exp["tmove"] = 0
        got = {"pos": w16(u, 0x0A) << 16 | w16(u, 0x0C), "rem": u[0x6F],
               "hull": tuple(u[0x68:0x6B]), "speed": (u[0x70], u[0x6E], u[0x71]),
               "dest": w16(u, 0x4E) << 16 | w16(u, 0x50),
               "last": (w16(u, 0x60) << 16 | w16(u, 0x62), w16(u, 0x64) << 16 | w16(u, 0x66)),
               "tmove": w16(u, 0x5C), "distdest": w16(u, 0x58), "flip": u[4] >> 5 & 1}
        for k in exp:
            T.check(got[k] == exp[k], lambda: f"type {t} at {p:#x} to {dst:#x}: {k} "
                    f"{got[k]}, expected {exp[k]}")
    for near, vh, vsq, step in crush:
        v = rg.unit(step, 60)
        dies = near and vh == 1
        got = (v[0x54] == ORDER["die"], w16(v, O_SCRIPT + 0x0C + 2))
        exp = (dies, 1 if dies else 0)
        T.check(got == exp, lambda: f"crush near {near} victim house {vh}: "
                f"(dies, var1) {got}, expected {exp}")
    out.append(f"  ({moves} moves, {arrivals} arrivals, {len(crush)} crush cases)")
    return T.ok, T.bad, rg


# icons for the obstacles poked into the map
WALL_ICON, MOUNTAIN_ICON = icon_of(11), icon_of(6)


def g_path(b, out):
    R.seed(26)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    # walls and mountains: short lines and blobs over the open ground
    free = free_squares(ram0)
    for _ in range(45):
        sq = R.choice(free)
        icon = WALL_ICON if R.random() < 0.5 else MOUNTAIN_ICON
        d = R.choice([1, 64, 65, 63])
        for k in range(R.randrange(2, 7)):
            s = sq + d * k
            if 64 < s < 4032 and s in free:
                rg.poke_sq(s, ground=icon & 0xFF, high=icon >> 8)
    bank = rg.bank("mv_path_find")
    cases = []
    for i in range(110):
        t = R.choice([9, 9, 16, 13, 2, 15, 7, 6, 17])
        start = R.choice(free)
        r = R.choice([4, 8, 12, 20])
        gy = min(62, max(1, (start >> 6) + R.randrange(-r, r + 1)))
        gx = min(62, max(1, (start & 63) + R.randrange(-r, r + 1)))
        goal = gy * 64 + gx
        rec = unit_rec(SLOT, t, R.choice([0, 0, 1, 2]), (start >> 6) << 8 | 0x80,
                       (start & 63) << 8 | 0x80, flags=3)
        tm = R.random()
        put16(rec, 0x5C, tile_ref(goal) if tm < 0.8 else
              (0 if tm < 0.9 else tile_ref(R.choice(free))))
        rg.poke_unit(SLOT, rec)
        rg.poke_bank("mv_pf_start", start.to_bytes(2, "little") + goal.to_bytes(2, "little"))
        cases.append((t, start, goal, rg.call("mv_path_find", ix=UREC, frames=12,
                                               pages=ALL + (bank,))))
    rg.run()
    T = Tally(out)
    detours = long_ = 0
    for t, start, goal, step in cases:
        ram = rg.ram(step)
        exp = route_of(ram, MU, start, goal)
        n = rg.bvar(step, "mv_pf_len")[0]
        got = list(rg.bvar(step, "mv_pf_buf", 40)[:n])
        straight = path_find(start, goal, 40, lambda s, d: 0, 255)
        detours += exp != straight
        long_ += len(exp) > 16
        T.check(got == exp, lambda: f"type {t} {start}->{goal}: {got}, expected {exp}")
    out.append(f"  ({len(cases)} routes, {detours} not straight, {long_} longer than 16)")
    return T.ok, T.bad, rg


def g_step(b, out):
    """UNIT 12 step, one scenario a call; the model follows $0452C2."""
    R.seed(27)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    freeset = set(free)
    inner = [sq for sq in free if all(sq + d in freeset for d in
                                      (-65, -64, -63, -1, 1, 63, 64, 65))]
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    refineries = [n for n in structs if ram0.b(md_struct(n) + 2) == 12]
    cases = []

    def add(kind, rec, **kw):
        rg.poke_unit(SLOT, rec)
        pre = probe(rg)
        cases.append((kind, pre, rg.call("ef_u_step", ix=UREC + O_SCRIPT, frames=12), kw))

    def unit_at(sq, t=9, h=1, face=0):
        return unit_rec(SLOT, t, h, (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80, face=face)

    for i in range(70):
        sq = R.choice(inner)
        t = R.choice([9, 13, 2, 15, 16, 7])
        kind = R.choice(["plan", "plan", "plan", "facing", "facing", "route",
                         "busy", "arrived", "offmap", "stale", "blocked", "cut"])
        goal = R.choice(free)
        if kind == "plan":
            rec = unit_at(sq, t, face=R.randrange(256))
            put16(rec, 0x5C, tile_ref(goal))
            add(kind, with_arg(rec, tile_ref(goal)))
        elif kind == "facing":
            # already facing the first direction: the step starts
            rec = unit_at(sq, t)
            put16(rec, 0x5C, tile_ref(goal))
            rt = route_of(ram0.with_unit(SLOT, rec), MU, sq, goal)
            face = (rt[0] << 5) & 0xFF if rt and rt[0] != 0xFF else 0
            rec = unit_at(sq, t, face=face)
            put16(rec, 0x5C, tile_ref(goal))
            add(kind, with_arg(rec, tile_ref(goal)))
        elif kind == "route":
            # a route already: turn or step along it
            rec = unit_at(sq, t, face=R.choice([0, 64, 96, 128]))
            dirs = [R.randrange(8) for _ in range(R.randrange(1, 17))]
            rec[0x7C:0x7C + len(dirs)] = bytes(dirs)
            if len(dirs) < 16:
                rec[0x7C + len(dirs)] = 0xFF
            if R.random() < 0.5:
                rec[0x6A] = rec[0x69] = dirs[0] << 5
            put16(rec, 0x5C, tile_ref(goal))
            add(kind, with_arg(rec, tile_ref(goal)))
        elif kind == "busy":
            rec = unit_at(sq, t)
            put16(rec, 0x4E, 0x1234)
            put16(rec, 0x5C, tile_ref(goal))
            add(kind, with_arg(rec, tile_ref(goal)))
        elif kind == "arrived":
            rec = unit_at(sq, t)
            put16(rec, 0x5C, tile_ref(sq))
            rec[0x7C] = 3
            add(kind, with_arg(rec, tile_ref(sq)))
        elif kind == "offmap":
            off = R.choice([R.randrange(64), 63 * 64 + R.randrange(64), 64 * R.randrange(64)])
            rec = unit_at(sq, t)
            put16(rec, 0x5C, tile_ref(off))
            add(kind, with_arg(rec, tile_ref(off)))
        elif kind == "stale":
            rec = unit_at(sq, t)
            add(kind, with_arg(rec, REF_UNIT | 101))       # slot 101 unused
        elif kind == "blocked":
            # facing a wall (or a friendly unit) with a route into it
            d = R.randrange(8)
            nsq = S.step8(sq, d)
            rec = unit_at(sq, 9, face=d << 5)
            rec[0x7C], rec[0x7D] = d, 0xFF
            put16(rec, 0x5C, tile_ref(goal))
            rg.poke_sq(nsq, ground=WALL_ICON & 0xFF, high=WALL_ICON >> 8)
            add(kind, with_arg(rec, tile_ref(goal)))
        else:                                   # "cut": a route to a unit
            other = 64
            osq = R.choice(free)
            orec = unit_rec(other, 4, 1, (osq >> 6) << 8 | 0x80, (osq & 63) << 8 | 0x80)
            rg.poke_unit(other, orec)
            rec = unit_at(sq, t, face=R.choice([0, 64]))
            rec[0x7C:0x8C] = bytes(R.randrange(8) for _ in range(16))
            put16(rec, 0x5C, REF_UNIT | other)
            add(kind, with_arg(rec, REF_UNIT | other))
    # a Harvester sent to a Refinery aims at its pad
    for n in refineries[:3]:
        sq = R.choice(inner)
        rec = unit_at(sq, 16)
        put16(rec, 0x5C, REF_STRUCT | n)
        add("pad", with_arg(rec, REF_STRUCT | n), refinery=n)
    # boxed in: no route at all, while attacking (the player's: Guard;
    # a computer's: Area Guard, or on Hunt the target dropped)
    for h, action in ((0, ORDER["attack"]), (1, ORDER["attack"]), (1, ORDER["hunt"])):
        sq = R.choice(inner)
        for d in range(8):
            s = S.step8(sq, d)
            rg.poke_sq(s, ground=WALL_ICON & 0xFF, high=WALL_ICON >> 8)
        goal = R.choice(free)
        rec = unit_rec(SLOT, 9, h, (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80,
                       action=action)
        put16(rec, 0x5C, tile_ref(goal))
        put16(rec, 0x5A, REF_UNIT | 70)
        add("boxed", with_arg(rec, tile_ref(goal)), house=h, action=action)
    rg.run()
    T = Tally(out)
    seen = {}
    for kind, pre, step, kw in cases:
        a = rg.ram(pre)
        u0 = rg.unit(pre, SLOT)
        u = rg.unit(step, SLOT)
        ans, exp = step_model(a, u0, kind, kw)
        seen[kind] = seen.get(kind, 0) + 1
        got = {"answer": rg.regs(step)["hl"], "route": list(u[0x7C:0x8C]),
               "tmove": w16(u, 0x5C), "hull": tuple(u[0x68:0x6B]),
               "dest": w16(u, 0x4E) << 16 | w16(u, 0x50),
               "attack": w16(u, 0x5A), "action": u[0x54]}
        exp["answer"] = ans
        for k in exp:
            T.check(got[k] == exp[k], lambda: f"{kind} {kw}: {k} {got[k]}, "
                    f"expected {exp[k]}")
    out.append(f"  (scenarios {seen})")
    return T.ok, T.bad, rg


def step_model(a, u0, kind, kw):
    """emc_unit_step $0452C2 on the state before -> (answer, fields)."""
    t = u0[2]
    route = list(u0[0x7C:0x8C])
    exp = {"route": route, "tmove": w16(u0, 0x5C), "hull": tuple(u0[0x68:0x6B]),
           "dest": w16(u0, 0x4E) << 16 | w16(u0, 0x50), "attack": w16(u0, 0x5A),
           "action": u0[0x54]}
    ref = w16(u0, O_SCRIPT + 0x16 + 28)
    if exp["dest"] or not ref_valid(a, ref):
        return 1, exp
    own = S.square_of(a.l(MU + 0xA))
    goal = S.ref_square(a, ref)
    if t == 16 and ref >> 14 == 2:
        s = md_struct(ref & 0x3FFF)
        if a.b(s + 2) == 12:
            goal = S.square_of((a.l(s + 0xA) + 0x01000200) & 0xFFFFFFFF)
    if goal == own or not S.valid_square(a, goal):
        route[0] = 0xFF
        exp["tmove"] = 0
        return 0, exp
    if route[0] == 0xFF:
        rt = route_of(a, MU, own, goal)
        n = min(len(rt), 16)
        route[:n] = rt[:n]
        if route[0] == 0xFF:
            exp["tmove"] = 0
            if exp["attack"] and t != 16:
                if u0[8] == a.w(MD_PLAYER):
                    exp["attack"] = 0
                    exp["action"] = ORDER["guard"]
                elif u0[0x54] == ORDER["hunt"]:
                    exp["attack"] = 0
                else:
                    exp["action"] = ORDER["areaguard"]
            return 1, exp
    elif w16(u0, 0x5C) >> 14 == 1:
        dp = tile_distance_packed(goal, own)
        if dp < 16:
            route[dp] = 0xFF
    if route[0] == 0xFF:
        return 1, exp
    f = route[0] << 5 & 0xFF
    if f != u0[0x6A]:
        exp["hull"] = set_facing(t, u0[0x68], u0[0x69], u0[0x6A], f, False)
        return 1, exp
    # the step: unit_start_step (its details are the start group's)
    ny, nx = pos_step(w16(u0, 0x0A), w16(u0, 0x0C), f)
    score = S.enter_score(a, MU, sq_of(ny, nx), f >> 5)
    exp["hull"] = (0, f, f)
    if score > 255 or score == -1:
        route[0] = 0xFF
        return 0, exp
    exp["dest"] = ny << 16 | nx
    route[:] = route[1:] + [0xFF]
    return 1, exp


def g_fly(b, out):
    R.seed(28)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    pads = [n for n in structs if ram0.b(md_struct(n) + 2) in (11, 12)]
    others = [n for n in structs if n not in pads]
    cases = []
    for i in range(70):
        t = R.choice([0, 1, 1, 0])
        k = R.random()
        if k < 0.35 and pads:
            ref = REF_STRUCT | R.choice(pads)
        elif k < 0.45 and others:
            ref = REF_STRUCT | R.choice(others)
        else:
            ref = tile_ref(R.randrange(64 * 2, 64 * 62))
        tgt = ref_pos(ram0, ref)
        r = R.choice([30, 64, 65, 100, 127, 128, 300, 900, 3000, 9000])
        ang = R.randrange(256)
        y, x = pos_of(S.move_by_direction(tgt, ang, min(r, 255)))
        if r > 255:
            y = (tgt >> 16) + R.randrange(-r, r + 1)
            x = (tgt & 0xFFFF) + R.randrange(-r, r + 1)
            y, x = min(max(y, 0x100), 0x3E00), min(max(x, 0x100), 0x3E00)
        rec = unit_rec(SLOT, t, R.choice([0, 1]), y & 0xFFFF, x & 0xFFFF,
                       face=R.randrange(256))
        rec[0x68] = 0
        put16(rec, 0x5C, ref)
        put16(rec, O_SCRIPT + SC_PC, 0x1234)
        put16(rec, 0x14, 0)
        rg.poke_unit(SLOT, rec)
        pre = probe(rg)
        cases.append((t, ref, pre, rg.call("ef_u_fly_to", ix=UREC + O_SCRIPT, frames=3)))
    rg.run()
    T = Tally(out)
    kinds = {}
    for t, ref, pre, step in cases:
        a = rg.ram(pre)
        u0 = rg.unit(pre, SLOT)
        u = rg.unit(step, SLOT)
        p = a.l(MU + 0xA)
        to = ref_pos(a, ref)
        if ref >> 14 == 2:
            ty = a.b(md_struct(ref & 0x3FFF) + 2)
            to = (to + {12: 0x00800100, 11: 0x00E000E0}.get(ty, 0)) & 0xFFFFFFFF
        d = S.tile_distance(p, to)
        exp = {"pos": p, "hull": tuple(u0[0x68:0x6B]),
               "speed": (u0[0x70], u0[0x6E], u0[0x6F], u0[0x71]),
               "delay": 0, "pc": 0x1234}
        if d < 128:
            exp["speed"] = (0, 0, 0, 0)
            py, px = pos_of(p)
            ty_, tx_ = pos_of(to)
            ny = (py + max(-16, min(16, S.sbyte16((ty_ - py) & 0xFFFF)))) & 0xFFFF
            nx = (px + max(-16, min(16, S.sbyte16((tx_ - px) & 0xFFFF)))) & 0xFFFF
            if d <= 64:
                exp["pos"], ans = to, 1
                kinds["land"] = kinds.get("land", 0) + 1
            else:
                exp["pos"], ans = ny << 16 | nx, 0
                exp["delay"], exp["pc"] = 2, 0x1232
                kinds["slide"] = kinds.get("slide", 0) + 1
        else:
            want = tile_direction(p, to)
            exp["hull"] = set_facing(t, u0[0x68], u0[0x69], u0[0x6A], want, False)
            ang = (want - u0[0x6A]) & 0xFF
            ang = min(ang, 256 - ang)                   # the port's fix
            v = S.mul_shr8(min(d >> 3, 255), 255 - ang)
            exp["speed"] = speed_fields(t, v & 0xFF) if v < 256 else None
            exp["delay"], exp["pc"], ans = max(d >> 10, 1), 0x1232, 0
            kinds["far"] = kinds.get("far", 0) + 1
        got = {"pos": w16(u, 0x0A) << 16 | w16(u, 0x0C), "hull": tuple(u[0x68:0x6B]),
               "speed": (u[0x70], u[0x6E], u[0x6F], u[0x71]),
               "delay": w16(u, 0x14), "pc": w16(u, O_SCRIPT + SC_PC)}
        exp["answer"], got["answer"] = ans, rg.regs(step)["hl"]
        for k in exp:
            T.check(got[k] == exp[k], lambda: f"type {t} to {ref:#x} from {p:#x} "
                    f"(distance {d}): {k} {got[k]}, expected {exp[k]}")
    out.append(f"  (cases {kinds})")
    return T.ok, T.bad, rg


TIMERS = (("mv_tick_unit_move", 3), ("mv_tick_unit_rot", 2),
          ("mv_tick_unit_turret", 20), ("mv_tick_unit_script", 5),
          ("mv_tick_unit_anim", 5), ("mv_tick_unit_dev", 60))


def g_loop(b, out):
    """unit_tick_all with the find array holding one unit (its script not
    loaded): the six timers, then S1's steps 5-12 for it."""
    R.seed(29)
    ram0 = rig.load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    spice = [sq for sq in free if S.landscape(ram0, sq) in (8, 9)]
    rg.poke_w("timer_game_on", [0])
    rg.poke_w("validate_strict", [0])
    cases = []
    for i in range(70):
        now = R.randrange(1 << 32) if R.random() < 0.2 else R.randrange(200000)
        dues = [(now - R.randrange(0, 40)) & 0xFFFFFFFF if R.random() < 0.6
                else (now + R.randrange(1, 40)) & 0xFFFFFFFF for _ in TIMERS]
        rg.poke_w("timer_game", now.to_bytes(4, "little"))
        for (name, _), d in zip(TIMERS, dues):
            rg.poke_w(name, d.to_bytes(4, "little"))
        rg.poke_w("unit_find", [SLOT])
        rg.poke_w("unit_find_count", [1])
        t = R.choice([2, 4, 9, 10, 13, 15, 16, 16, 7, 12])
        sq = R.choice(spice if t == 16 and R.random() < 0.6 else free)
        rec = unit_rec(SLOT, t, R.choice([0, 1, 2]), (sq >> 6) << 8 | 0x80,
                       (sq & 63) << 8 | 0x80,
                       action=ORDER["harvest"] if t == 16 and R.random() < 0.7
                       else ORDER["guard"])
        for o in (0x68, 0x6B):
            cur, want = R.randrange(256), R.randrange(256)
            if R.random() < 0.3:
                want = cur
            rec[o:o + 3] = bytes(set_facing(t, 0, 0, cur, want, False))
        if R.random() < 0.6:
            put16(rec, 0x5A, tile_ref(R.choice(free)))
        rec[0x56] = R.choice([0, 0, 1, 5, 200])
        rec[0x5F] = R.choice([0, 0, R.randrange(2, 120)])
        put16(rec, 0x76, R.choice([0, 0, 1, 3]))
        rec[0x73] = R.choice([R.randrange(0x40), R.randrange(3), 0x85])
        if mt_of(t) == 0 and R.random() < 0.6:
            rec[0x70], rec[0x6E], rec[0x6F] = 1, 0, R.randrange(256)   # walking, no carry
        put16(rec, 0x14, R.choice([0, 0, 1, 4]))
        if R.random() < 0.3:
            rec[0x55] = R.choice([ORDER["guard"], ORDER["move"], ORDER["areaguard"]])
        rg.poke_unit(SLOT, rec)
        pre = probe(rg)
        cases.append((t, now, dues, pre, rg.call("unit_tick_all", frames=4)))
    rg.run()
    T = Tally(out)
    fired = [0] * 6
    for t, now, dues, pre, step in cases:
        a = rg.ram(pre)
        u0 = rg.unit(pre, SLOT)
        u = rg.unit(step, SLOT)
        fire = [now >= d for d in dues]
        for k, f in enumerate(fire):
            fired[k] += f
        fmove, frot, fturret, fscript, fanim, fdev = fire
        mt = mt_of(t)
        turret = ut(t, 0x0C) & 0x40
        hull, tur = list(u0[0x68:0x6B]), list(u0[0x6B:0x6E])
        fd, dev, anim, so, delay = u0[0x56], u0[0x5F], w16(u0, 0x76), u0[0x73], w16(u0, 0x14)
        action, nxt = u0[0x54], u0[0x55]
        own = sq_of(w16(u0, 0x0A), w16(u0, 0x0C))
        shown = None
        if fturret and w16(u0, 0x5A) and turret:
            want = tile_direction(a.l(MU + 0xA), ref_pos(a, w16(u0, 0x5A)))
            tur = list(set_facing(t, *tur, want, False))
        if fmove:
            if mt in (0, 1) and hull[1] != hull[2]:
                hull[0], hull[2] = S.turn_step(*hull)
            if fd:
                fd -= 1
        if frot:
            hull[0], hull[2] = S.turn_step(*hull)
            if turret:
                tur[0], tur[2] = S.turn_step(*tur)
        if fdev and dev and ut(t, 0x38) & 0x8000:
            dev -= 1                     # (poked above 1: it never runs out here)
        if fanim:
            if anim:
                anim -= 1
            else:
                if mt == 0 and u0[0x70] and not so & 0x80:
                    so = (so & 0x3F) + 1
                    anim = ut(t, 0x40) // 5
                if t == 16:
                    if action == ORDER["harvest"] and S.landscape(a, own) in (8, 9):
                        so = (so + 1) & 0xFF
                        if not so & 0x80 and so >= 3:
                            so = 0
                        shown, anim = 1, 1
                    else:
                        shown = 0
        if fscript and delay:
            delay -= 1
        if nxt != 0xFF:
            action, nxt, delay = nxt, 0xFF, 0
        exp = {"due": [(now + p) & 0xFFFFFFFF if f else d
                       for (_, p), f, d in zip(TIMERS, fire, dues)],
               "hull": tuple(hull), "turret": tuple(tur), "fireDelay": fd,
               "deviated": dev, "anim": (anim, so), "delay": delay,
               "order": (action, nxt)}
        got = {"due": [rg.wvar(step, name, 4) for name, _ in TIMERS],
               "hull": tuple(u[0x68:0x6B]), "turret": tuple(u[0x6B:0x6E]),
               "fireDelay": u[0x56], "deviated": u[0x5F],
               "anim": (w16(u, 0x76), u[0x73]), "delay": w16(u, 0x14),
               "order": (u[0x54], u[0x55])}
        if shown is not None:
            exp["shown"] = shown
            got["shown"] = rg.wvar(step, "mv_harvest_shown", 13) >> SLOT & 1
        held = a.b(S.MAP + 4 * own + 3) and a.b(S.MAP + 4 * own + 2) & 0x30
        if not held:
            mp = rg.page(step, 26)
            exp["claim"] = (1, SLOT + 1)
            got["claim"] = (mp[0x2000 + own] >> 4 & 1, mp[0x3000 + own])
        for k in exp:
            T.check(got[k] == exp[k], lambda: f"type {t} now {now} fired {fire}: "
                    f"{k} {got[k]}, expected {exp[k]}")
    out.append(f"  (timers fired {fired} of {len(cases)} passes)")
    return T.ok, T.bad, rg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    b = args.build_dir
    s = Suite()
    for name, fn in (("speed", g_speed), ("turn", g_turn), ("enter", g_enter),
                     ("start", g_start), ("tick", g_tick), ("path", g_path),
                     ("step", g_step), ("fly", g_fly), ("loop", g_loop)):
        s.group(name, lambda o, fn=fn: fn(b, o), args.only)
    sys.exit(1 if s.total_bad else 0)


if __name__ == "__main__":
    main()
