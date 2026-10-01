#!/usr/bin/env python3
"""test_combat.py - the COMBAT subsystem (S4) on the running machine,
against models written from S4 and the cartridge's code.

    python3 tools/tests/test_combat.py [--build-dir build] [--only NAME]

Every group is one evo-run: Harkonnen mission 8 (the structures and units
of five houses, turrets among them) is loaded through start_mission,
records are poked, and COMBAT's routines are far-called.  The models read
the port's own pages through tools/tests/rig.py's PortRam, the state just
before each call (a probe dumps it), and predict what the call leaves.

  damage    unit_damage: hit points (signed, floored at 0), death and the
            Die order, Ambush turning to Attack, below half: the Sandworm
            leaving, a squad losing a man (the type, full health, the
            counts, the Retreat drawn against the house's toughness, never
            the Sardaukar), smoke; PLAYTESTER, non-normal units
  struct    struct_damage: hit points, destroyed at 0 or below, the score
            and its floor, destroyedAllied/Enemy, a dying structure and
            PLAYTESTER taking nothing, the player's selection cleared
  explode   map_make_explosion: every unit within reach takes D >> (d / 4)
            (d = distance / 16; reach 16, 32 for type 11), not the Frigate,
            not the Sandworm from type 13; a type-6 blast caused by any
            unit but a Devastator does nothing; the structure on the square
            takes D; the reactions (teams, Harvesters, guards going hunting,
            retargeting on the cause, Hunt with a target out of range)
  fire      UNIT 8 fire: no target, stale, its own square, the gun still
            turning, reloading, out of range (to a structure's near edge),
            off by 8 or more (a flyer's error an eighth), and firing: the
            projectile's type, damage (Fremen troopers x4, a trooper's rocket
            less a quarter), origin, start, destination and range, the big
            gun's linkedID and flash, fireOnce, the reload and fireTwice
  target    unit_find_target modes 0-4: the first eligible enemy unit of
            the other side's list, the best structure by
            unit_struct_target_priority, and unit_attack_score between them
  settarget unit_set_target: Harvesters, stale and unchanged references,
            flyers, a place with a unit or structure on it, itself, and a
            unit with no turret heading there
  deviate   unit_deviate (the chance by toughness, an eighth less for the
            computer's; normal units only, not Fremen, not isNotDeviatable)
            and unit_deviation_wear (n = 0 is the current house's
            toughness; running out sends it home)
  die       UNIT 15 die: the score by max(cost / 100, 1) and its floor,
            killedAllied/Enemy, flyers not counted, the unit removed
  turret    BUILD 8 find.target (keep in range, 3n for a flyer, else the
            nearest seen, an unseen Ornithopter at once) and BUILD 11 fire
            (dropping a target, the Rocket Turret's rocket at 3 squares,
            the bullet, the answers 90 and 40, origin and linkedID)
  missile   unit_launch_house_missile: the placeholder freed, a Death
            Hand fired at the square scattered by tile_move_by_random(160)
            - sin * 160 >> 3, up to ten squares on the Mega Drive (it once
            handed a COMBAT2 address across the far call and was never
            scattered)
  aim       UNIT 58 aim: targetAttack = the reference, and targetMove too
            for a unit without a turret (it once took the type record's
            address)
"""
import argparse
import random as R
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from rig import (Rig, Suite, Tally, S, U_SIZE, UNITS, STRUCTS, S_SIZE,   # noqa: E402
                 T_SIZE, TEAMS, HOUSES, H_SIZE, ORDER, O_SCRIPT, REF_UNIT, REF_STRUCT, REF_TILE,
                 md_unit, md_struct, unit_rec, with_arg, tile_ref, ut, st, w16,
                 s16, put16, rnd, ROOT, probe, load_ram, free_squares,
                 free_slots, sq_of, tile_direction, ref_pos, ref_valid, squares,
                 tile_distance_packed, unveiled)
import test_move as M                  # noqa: E402  MOVE's models (set_facing)

HOUSE, MISSION = 0, 8                  # H8: the player is Harkonnen
PLAYER = HOUSE
DIE, DESTRUCT, ATTACK, AMBUSH = ORDER["die"], ORDER["destruct"], ORDER["attack"], ORDER["ambush"]
RETREAT, HUNT, GUARD, MOVE = ORDER["retreat"], ORDER["hunt"], ORDER["guard"], ORDER["move"]
AREAGUARD = ORDER["areaguard"]


def mt(t):
    return ut(t, 0x3E)


def sgn(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def toughness(h):
    """A house's toughness ($06C750, $1E bytes a house, +6)."""
    return S.rom_w(0x06C750 + 0x1E * h + 6)


def urec(a, slot):
    """A unit's record as the port keeps it (a copy)."""
    o = slot * U_SIZE
    return bytearray(a.up[o:o + U_SIZE])


def srec(a, slot):
    o = STRUCTS - 0x8000 + slot * S_SIZE
    return bytearray(a.wp[o:o + S_SIZE])


def pos(r):
    return w16(r, 0x0A) << 16 | w16(r, 0x0C)


def unit_ref_slot(ref):
    """ref_unit's test in COMBAT: kind 1 with the high byte exactly $40."""
    return ref & 0xFF if ref >> 8 == 0x40 and ref & 0xFF < 102 else None


# ---------------------------------------------------------------- models

def give_order(r, order):
    """unit_give_order $0436A0 on a unit going nowhere (Die and Destruct
    stick; a Fremen told to Guard Hunts)."""
    if order == 0xFF or r[0x54] in (DIE, DESTRUCT):
        return
    if r[8] == 3 and order == GUARD:
        order = HUNT
    if order in (DIE, DESTRUCT) or not any(r[0x4E:0x52]):
        r[0x54], r[0x55] = order, 0xFF
        put16(r, 0x14, 0)
    else:
        r[0x55] = order


def unit_damage(r, dmg, playtester, seed):
    """unit_damage $046BA6 -> 1 if it died.  seed: [the generator's state],
    advanced by the squad's Retreat draw."""
    t, h = r[2], r[8]
    if not w16(r, 4) & 2:
        return 0
    if playtester & 1 and h == PLAYER:
        return 0
    if not ut(t, 0x38) & 0x8000 and t != 25:
        return 0
    hp = sgn(w16(r, 0x12))
    hp = 0 if hp < sgn(dmg) else hp - dmg
    put16(r, 0x12, hp & 0xFFFF)
    assert r[0x5F] == 0
    if hp & 0xFFFF == 0:
        give_order(r, DIE)
        return 1
    if h != PLAYER and r[0x54] == AMBUSH and t != 16:
        give_order(r, ATTACK)
    if sgn(hp) < sgn(ut(t, 0x10)) >> 1:
        if t == 25:
            give_order(r, DIE)
        if t in (2, 3):
            t += 2
            r[2] = t
            put16(r, 0x12, ut(t, 0x10))
            seed[0], v = rnd(seed[0])
            if v < toughness(h) and h != 4:
                give_order(r, RETREAT)
        if mt(r[2]) in (1, 2, 3):
            r[4] |= 8
            r[0x73] = 0
            put16(r, 0x76, 0)
    else:
        assert not (t == 25 and not w16(r, 0x5A)), "a healthy worm would wander"
    return 0


def struct_damage(a, r, dmg, playtester, g):
    """struct_damage $00F8D6.  g: score, destroyed counters, selection."""
    if dmg == 0 or w16(r, 0x22) == 1:
        return 0
    if playtester & 1 and r[8] == PLAYER:
        return 0
    hp = (w16(r, 0x12) - dmg) & 0xFFFF
    put16(r, 0x12, hp)
    if hp and not hp & 0x8000:                     # tst.w; bgt
        return 0
    put16(r, 0x12, 0)
    s = max(st(r[2], 0x16) // 100, 1)
    if S.allied(a, r[8], PLAYER):
        g["destroyed_allied"] += 1
        g["score"] -= min(s, g["score"])
    else:
        g["destroyed_enemy"] += 1
        g["score"] += s
    if r[8] == PLAYER and g["struct_selected"] == r[0]:     # $00F9A4
        g["struct_selected"] = 0xFF
    return 1


def set_target(a, units, r, ref):
    """unit_set_target $047BCC.  units: slot -> record (for flyers)."""
    if r[2] == 16 or not ref_valid(a, ref) or w16(r, 0x5A) == ref:
        return
    v = unit_ref_slot(ref)
    if v is not None and mt(units[v][2]) == 4 and not ut(r[2], 0x0C) & 0x1000:
        return
    if ref >> 14 == 3:
        sq = (ref & 0x3F00) >> 2 | (ref & 0x7E) >> 1
        f, i = a.b(S.MAP + 4 * sq + 2), a.b(S.MAP + 4 * sq + 3)
        if f & 0x10:
            ref = REF_UNIT | (i - 1) & 0xFF
        elif f & 0x20:
            ref = REF_STRUCT | (i - 1) & 0xFF
    if ref == REF_UNIT | r[0]:
        ref = tile_ref(sq_of(w16(r, 0x0A), w16(r, 0x0C)))
    put16(r, 0x5A, ref)
    if not ut(r[2], 0x0C) & 0x40:
        put16(r, 0x5C, ref)
        r[0x7C] = 0xFF


def react(a, units, teams, r, cause):
    """map_make_explosion's reaction ($00AA1A) of a unit it reached."""
    if r[8] == PLAYER:
        return
    c = unit_ref_slot(cause)
    if c is None or c == r[0]:
        return
    cu = units[c]
    if S.allied(a, r[8], cu[8]):
        return
    if r[0x75]:
        tm = teams[r[0x75] - 1]
        if w16(tm, 0x0C) == 1:
            put16(tm, 0x04, w16(tm, 0x04) - 1)
            r[0x75] = 0
            give_order(r, HUNT)
            return
        v = unit_ref_slot(w16(tm, 0x1A))
        if v is not None and ut(units[v][2], 0x58) == 0xFFFF:
            put16(tm, 0x1A, cause)
        return
    if r[2] == 16 and mt(cu[2]) == 0 and not w16(r, 0x5C):
        if r[0x54] != MOVE:
            give_order(r, MOVE)
        put16(r, 0x5C, cause)
        return
    if ut(r[2], 0x58) == 0xFFFF:
        return
    if r[8] != PLAYER and r[0x54] == GUARD and w16(r, 4) & 0x200:
        give_order(r, HUNT)
    if r[2] == 25:
        return
    tgt = w16(r, 0x5A)
    if tgt:
        if r[0x54] != HUNT:
            return
        v = unit_ref_slot(tgt)
        if v is not None:
            own = sq_of(w16(r, 0x0A), w16(r, 0x0C))
            tsq = S.ref_square(a, tgt)
            if sgn(tile_distance_packed(tsq, own)) < sgn(ut(r[2], 0x52)):
                return
    set_target(a, units, r, cause)


def explosion(a, etype, p, dmg, cause, seed, glob):
    """map_make_explosion $00A934 -> (units, teams, structures touched)."""
    units = {n: urec(a, n) for n in range(102)}
    teams = [bytearray(a.up[TEAMS - 0x4000 + k * T_SIZE:][:T_SIZE]) for k in range(16)]
    touched = {}
    if etype == 6:
        c = unit_ref_slot(cause)
        if c is not None and units[c][2] != 11:
            dmg = 0
    reach = 32 if etype == 11 else 16
    sq = S.square_of(p)
    if dmg:
        wp, sym = a.wp, a.sym
        count = wp[sym["unit_find_count"] - 0x8000]
        strict = wp[sym["validate_strict"] - 0x8000]
        for k in range(count):
            n = wp[sym["unit_find"] - 0x8000 + k]
            r = units[n]
            if w16(r, 4) & 4 and not strict:
                continue
            d = sgn(S.tile_distance(p, pos(r))) >> 4
            if d >= reach:
                continue
            if not (r[2] == 25 and etype == 13) and r[2] != 26:
                unit_damage(r, dmg >> (d >> 2), glob["playtester"], seed)
            react(a, units, teams, r, cause)
        if a.b(S.MAP + 4 * sq + 2) & 0x20:
            n = a.b(S.MAP + 4 * sq + 3) - 1
            s = srec(a, n)
            struct_damage(a, s, dmg, glob["playtester"], glob)
            touched[n] = s
    return units, teams, touched


def distance_to_edge(a, r, ref):
    """ref_distance_to_edge $02E0A8: to a structure, the centre of the
    square of its footprint that faces the unit ($06B7B6)."""
    if ref >> 14 == 2 and (ref & 0xFF) < 73:
        s = md_struct(ref & 0xFF)
        ssq = a.b(s + 0xA) * 64 + a.b(s + 0xC)
        d = ((tile_direction(pos(r), ref_pos(a, ref)) + 16) & 0xFF) >> 5
        e = (d + 4) & 7
        lay = S.rom_w(S.btype(a.b(s + 2)) + 0x3C)
        esq = (ssq + S.sbyte16(S.rom_w(0x06B7B6 + 16 * lay + 2 * e))) & 0xFFF
        to = (esq >> 6) << 24 | 0x80 << 16 | (esq & 63) << 8 | 0x80
    else:
        to = ref_pos(a, ref)
    return S.tile_distance(pos(r), to)


def WHY(reason):
    """fire_model's reason for not firing, kept for the report."""
    WHY.last = reason


WHY.last = ""


def fire_model(a, r, units, glob):
    """emc_unit_fire $0447E2 -> (answer, projectile expectations or None)."""
    WHY.last = "fires"
    t, h = r[2], r[8]
    tgt = w16(r, 0x5A)
    if not tgt or not ref_valid(a, tgt):
        return 0, WHY("no target")
    own = sq_of(w16(r, 0x0A), w16(r, 0x0C))
    if t != 25 and tgt == tile_ref(own):
        put16(r, 0x5A, 0)
    if w16(r, 0x5A) != tgt:
        set_target(a, units, r, tgt)
        return 0, WHY("changed underneath")
    turret = ut(t, 0x0C) & 0x40
    if t == 25:
        face = r[0x6A]
    elif turret:
        if r[0x6C] != r[0x6D]:
            return 0, WHY("turret turning")
        face = r[0x6D]
    else:
        if mt(t) != 4 and r[0x69] != r[0x6A]:
            return 0, WHY("hull turning")
        face = r[0x6A]
    if tgt >> 14 == 3:
        sq = (tgt & 0x3F00) >> 2 | (tgt & 0x7E) >> 1
        if a.b(S.MAP + 4 * sq + 2) & 0x30 and a.b(S.MAP + 4 * sq + 3):
            set_target(a, units, r, tgt)
    if r[0x56]:
        return 0, WHY("reloading")
    tpos = ref_pos(a, tgt)
    dist = distance_to_edge(a, r, tgt)
    if sgn(ut(t, 0x52) << 8) < sgn(dist):
        return 0, WHY("out of range")
    d = tile_direction(pos(r), tpos)
    diff = abs(face - d)
    if mt(t) == 4:
        diff >>= 3
    if t == 25:
        diff = 0
    v = unit_ref_slot(tgt)
    if v is not None and mt(units[v][2]) == 4:
        diff = 0
    if diff >= 8:
        return 0, WHY("off by 8 or more")
    dmg, kind = ut(t, 0x54), ut(t, 0x58) & 0xFF
    twice = ut(t, 0x38) & 0x400 and sgn(ut(t, 0x10)) >> 1 < sgn(w16(r, 0x12))
    if t in (3, 5):
        if sgn(dist) >= 0x201:
            kind = 22
        if h == 3:
            dmg = dmg * 4 & 0xFFFF
    if not 19 <= kind <= 24:
        return 0, WHY("no projectile")
    if kind == 22:
        dmg -= sgn(dmg) >> 2
    proj = {"type": kind, "house": h, "hp": dmg & 0xFFFF, "origin": REF_UNIT | r[0]}
    org = pos(r)
    pd = tile_direction(org, tpos)
    proj["face"] = pd
    if kind < 23:
        proj["pos"] = org
        proj["target"] = tgt
        if not ut(kind, 0x38) & 0x4000:
            proj["dest"] = tpos
        fd = ut(kind, 0x52) & 0xFF
        if v is not None and mt(units[v][2]) == 4:
            fd = fd * 2 & 0xFF
        proj["fireDelay"] = fd
    else:
        proj["pos"] = S.move_by_direction(S.move_by_direction(org, 0, 32), pd, 128)
        proj["dest"] = tpos
        if kind == 24:
            proj["fireDelay"] = ut(kind, 0x52) & 0xFF
        proj["big"] = int(sgn(dmg) >= 16)
        if kind == 23:
            proj["linked"] = 9 if t in (9, 10, 11) else 0xFF
            if t in (9, 10):
                r[6] |= 0x40                            # the muzzle flash
    if r[6] & 0x20:
        r[6] &= ~0x20
        give_order(r, GUARD)
    fd = ut(t, 0x50) * 2 & 0xFF
    if twice:
        r[4] ^= 0x10
        if r[4] & 0x10:
            fd = 5
    else:
        r[4] &= ~0x10
    r[0x56] = fd                  # + random & 1: the check takes either
    return 1, proj


# ---------------------------------------------------------------- groups

def g_damage(b, out):
    R.seed(31)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    slot = free_slots(ram0)[0]
    free = free_squares(ram0)
    cases = []
    for i in range(130):
        t = R.choice([2, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
                      17, 25, 1, 0, 19, 23])
        h = R.choice([0, 0, 1, 2, 4, 4, 3])
        hpmax = ut(t, 0x10)
        hp = R.choice([hpmax, R.randrange(1, hpmax + 1), 1, hpmax // 2,
                       hpmax // 2 + 1, max(hpmax // 2 - 1, 1)])
        dmg = max(0, R.choice([0, 1, R.randrange(1, 60), hp - 1, hp, hp + 5,
                               hp - hpmax // 2, R.randrange(0, 600)]))
        sq = R.choice(free)
        rec = unit_rec(slot, t, h, (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80, hp=hp,
                       action=R.choice([GUARD, AMBUSH, AMBUSH, ATTACK, HUNT, MOVE, AREAGUARD]),
                       flags=3 if R.random() < 0.95 else 1)
        if t == 25:
            put16(rec, 0x5A, tile_ref(sq))
        pt = R.choice([0, 0, 0, 1])
        rg.poke_w("playtester", [pt])
        rg.poke_w("rnd_seed", [R.randrange(256) for _ in range(3)])
        rg.poke_unit(slot, rec)
        pre = probe(rg)
        cases.append((t, dmg, pt, pre, rg.call("unit_damage", ix=UNITS + slot * U_SIZE,
                                                hl=dmg, frames=4)))
    rg.run()
    T = Tally(out)
    kinds = {}
    for t, dmg, pt, pre, step in cases:
        a = rg.ram(pre)
        r = urec(a, slot)
        seed = [tuple(a.wp[rg.a("rnd_seed") - 0x8000:][:3])]
        died = unit_damage(r, dmg, pt, seed)
        u = rg.unit(step, slot)
        k = "died" if died else ("squad" if r[2] != t else ("hurt" if w16(r, 0x12) != w16(urec(a, slot), 0x12) else "none"))
        kinds[k] = kinds.get(k, 0) + 1
        exp = {"answer": died, "hp": w16(r, 0x12), "type": r[2], "action": r[0x54],
               "smoke": r[4] >> 3 & 1}
        got = {"answer": rg.regs(step)["a"], "hp": w16(u, 0x12), "type": u[2],
               "action": u[0x54], "smoke": u[4] >> 3 & 1}
        if r[2] != t:                               # the per-type counts
            c0 = a.wp[rg.a("unit_type_count") - 0x8000 + r[8] * 32:][:32]
            c1 = rg.page(step, 25)[rg.a("unit_type_count") - 0x8000 + r[8] * 32:][:32]
            exp["counts"] = ((c0[t] - 1) & 0xFF, (c0[r[2]] + 1) & 0xFF)
            got["counts"] = (c1[t], c1[r[2]])
        for key in exp:
            T.check(got[key] == exp[key], lambda: f"type {t} house {r[8]} hp "
                    f"{w16(urec(a, slot), 0x12)} damage {dmg} playtester {pt}: {key} "
                    f"{got[key]}, expected {exp[key]}")
    out.append(f"  (cases {kinds})")
    return T.ok, T.bad, rg


GLOBALS = ("score", "destroyed_allied", "destroyed_enemy", "struct_selected", "playtester")


def globs(rg, a):
    sym = rg.sym
    g = {}
    for k in GLOBALS:
        n = 1 if k in ("struct_selected", "playtester") else 2
        g[k] = int.from_bytes(a.wp[sym[k] - 0x8000:][:n], "little")
    return g


def g_struct(b, out):
    R.seed(32)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    R.shuffle(structs)
    kills = 0
    cases = []
    for i in range(70):
        n = structs[i % len(structs)]
        t = ram0.b(md_struct(n) + 2)
        hpmax = st(t, 0x10)
        hp = R.choice([hpmax, R.randrange(1, hpmax + 1), 1, 5])
        dmg = max(0, R.choice([0, 1, R.randrange(1, 200), hp - 1, hp, hp + 30]))
        if dmg >= hp:
            if kills >= 12 or n in [c[0] for c in cases if c[-1]]:
                dmg = max(hp - 1, 0)
            else:
                kills += 1
        dying = R.random() < 0.1
        rg.poke_struct(n, 0x12, hp.to_bytes(2, "little"))
        rg.poke_struct(n, 0x22, [1 if dying else 0, 0])
        rg.poke_w("playtester", [R.choice([0, 0, 0, 1])])
        rg.poke_w("score", R.randrange(0, 60).to_bytes(2, "little"))
        rg.poke_w("destroyed_allied", R.randrange(10).to_bytes(2, "little"))
        rg.poke_w("destroyed_enemy", R.randrange(10).to_bytes(2, "little"))
        rg.poke_w("struct_selected", [R.choice([n, n, 0xFF, (n + 1) % 73])])
        pre = probe(rg)
        cases.append((n, dmg, pre, rg.call("struct_damage", ix=STRUCTS + n * S_SIZE,
                                            hl=dmg, frames=10),
                       dmg >= hp and not dying))
    # the player's own, selected, destroyed: the selection goes ($00F9A4)
    killed = {c[0] for c in cases if c[-1]}
    mine = [n for n in structs if ram0.b(md_struct(n) + 8) == PLAYER and n not in killed]
    for n in mine[:3]:
        rg.poke_struct(n, 0x12, (10).to_bytes(2, "little"))
        rg.poke_struct(n, 0x22, [0, 0])
        rg.poke_w("playtester", [0])
        rg.poke_w("struct_selected", [n])
        pre = probe(rg)
        cases.append((n, 50, pre, rg.call("struct_damage", ix=STRUCTS + n * S_SIZE,
                                           hl=50, frames=10), True))
    rg.run()
    T = Tally(out)
    destroyed = 0
    for n, dmg, pre, step, _ in cases:
        a = rg.ram(pre)
        r = srec(a, n)
        g = globs(rg, a)
        before = dict(g)
        gone = struct_damage(a, r, dmg, g["playtester"], g)
        destroyed += gone
        after = rg.ram(step)
        ga = globs(rg, after)
        exp = {"answer": gone, "hp": w16(r, 0x12), **{k: g[k] for k in GLOBALS[:4]}}
        got = {"answer": rg.regs(step)["a"], "hp": w16(srec(after, n), 0x12),
               **{k: ga[k] for k in GLOBALS[:4]}}
        for key in exp:
            T.check(got[key] == exp[key], lambda: f"structure {n} (type {r[2]} house "
                    f"{r[8]}) damage {dmg} before {before}: {key} {got[key]}, "
                    f"expected {exp[key]}")
    out.append(f"  ({destroyed} destroyed)")
    return T.ok, T.bad, rg


def clear_round(ram, sq, r=2):
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            s = sq + 64 * dy + dx
            if not 64 <= s < 4032 or ram.b(S.MAP + 4 * s + 2) & 0x30 or \
                    S.landscape(ram, s) in (11, 12):
                return False
    return True


def g_explode(b, out):
    R.seed(33)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    fs = free_slots(ram0)[:7]
    count = ram0.wp[rg.a("unit_find_count") - 0x8000]
    rg.poke_w(rg.a("unit_find") + count, fs)            # into the unit search
    rg.poke_w("unit_find_count", [count + len(fs)])
    centres = [sq for sq in free_squares(ram0) if clear_round(ram0, sq)]
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1
               and ram0.b(md_struct(n) + 2) not in (14,)]
    cases = []
    for i in range(70):
        on_struct = i % 4 == 3 and structs
        if on_struct:
            n = R.choice(structs)
            s = md_struct(n)
            sq = ram0.b(s + 0xA) * 64 + ram0.b(s + 0xC)
            hp = st(ram0.b(s + 2), 0x10)
            rg.poke_struct(n, 0x12, hp.to_bytes(2, "little"))
            rg.poke_struct(n, 0x22, [0, 0])
        else:
            sq = R.choice(centres)
        p = ((sq >> 6) << 8 | R.randrange(256)) << 16 | (sq & 63) << 8 | R.randrange(256)
        for k, slot in enumerate(fs):
            t = R.choice([9, 10, 11, 12, 13, 14, 15, 17, 7, 8, 16, 25, 26, 0, 1, 4])
            h = R.choice([0, 1, 2, 4])
            r = R.choice([0, 30, 64, 100, 200, 255, 256, 300, 400, 500])
            ang = R.randrange(256)
            y, x = M.pos_of(S.move_by_direction(p, ang, min(r, 255)))
            if r > 255:
                y, x = (p >> 16) + R.choice([-r, r]), (p & 0xFFFF) + R.randrange(-r, r)
            rec = unit_rec(slot, t, h, y & 0x3FFF, x & 0x3FFF,
                           action=R.choice([GUARD, GUARD, HUNT, ATTACK, AMBUSH, MOVE, AREAGUARD]))
            if R.random() < 0.3:
                rec[5] |= 2                              # byScenario
            k2 = R.random()
            if k2 < 0.3:
                put16(rec, 0x5A, REF_UNIT | R.choice(fs))
            elif k2 < 0.5:
                put16(rec, 0x5A, tile_ref(R.choice(centres)))
            elif t == 25:
                put16(rec, 0x5A, tile_ref(sq))
            if R.random() < 0.2:
                put16(rec, 0x5C, tile_ref(R.choice(centres)))
            rg.poke_unit(slot, rec)
        etype = R.choice([0, 1, 2, 3, 4, 6, 6, 8, 11, 13, 19])
        dmg = R.choice([0, 10, 38, 60, 112, 150, 200, 500])
        cause = R.choice([0, REF_UNIT | R.choice(fs), REF_UNIT | R.choice(fs),
                          REF_UNIT | 101, REF_STRUCT | (structs[0] if structs else 0)])
        rg.poke_w("arg_pos", (p >> 16).to_bytes(2, "little") + (p & 0xFFFF).to_bytes(2, "little"))
        rg.poke_w("playtester", [R.choice([0, 0, 0, 1])])
        pre = probe(rg)
        cases.append((etype, p, dmg, cause, pre,
                      rg.call("map_make_explosion", a=etype, hl=dmg, de=cause, frames=10)))
    rg.run()
    T = Tally(out)
    hits = reacts = 0
    for etype, p, dmg, cause, pre, step in cases:
        a = rg.ram(pre)
        after = rg.ram(step)
        glob = globs(rg, a)
        seed = [tuple(a.wp[rg.a("rnd_seed") - 0x8000:][:3])]
        units, teams, touched = explosion(a, etype, p, dmg, cause, seed, glob)
        for slot in fs:
            r0, r, u = urec(a, slot), units[slot], urec(after, slot)
            hits += w16(r, 0x12) != w16(r0, 0x12)
            reacts += w16(r, 0x5A) != w16(r0, 0x5A) or r[0x54] != r0[0x54]
            for key, off, n in (("hp", 0x12, 2), ("action", 0x54, 1), ("next", 0x55, 1),
                                ("target", 0x5A, 2), ("move", 0x5C, 2), ("type", 2, 1)):
                e, g = r[off:off + n], u[off:off + n]
                T.check(e == g, lambda: f"type {etype} damage {dmg} cause {cause:#x} at "
                        f"{p:#x}: unit {slot} (type {r0[2]} house {r0[8]} at "
                        f"{pos(r0):#x}, distance {S.tile_distance(p, pos(r0))}) {key} "
                        f"{bytes(g).hex()}, expected {bytes(e).hex()}")
        for n, s in touched.items():
            T.check(w16(srec(after, n), 0x12) == w16(s, 0x12), lambda: f"type {etype} "
                    f"damage {dmg} on structure {n}: hp {w16(srec(after, n), 0x12)}, "
                    f"expected {w16(s, 0x12)}")
    out.append(f"  ({hits} unit hits, {reacts} reactions)")
    return T.ok, T.bad, rg


SHOOTERS = [9, 10, 11, 12, 7, 8, 13, 14, 15, 2, 3, 4, 5, 6, 1, 3, 5]


def g_fire(b, out):
    R.seed(34)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    free = free_squares(ram0)
    freeset = set(free)
    inner = [sq for sq in free if all(sq + d in freeset for d in
                                      (-65, -64, -63, -1, 1, 63, 64, 65))]
    fs = free_slots(ram0)
    me, other = fs[0], fs[1]
    assert not any(ram0.w(md_unit(n) + 4) & 1 for n in range(12, 22))
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    cases = []
    for i in range(170):
        t = R.choice(SHOOTERS)
        h = 3 if t in (3, 5) and R.random() < 0.4 else R.choice([0, 1, 2])
        rng = ut(t, 0x52) << 8
        kind = R.choice(["unit", "unit", "unit", "struct", "tile", "flyer",
                         "none", "stale", "own"])
        sq = R.choice(inner)
        p = ((sq >> 6) << 8 | 0x80) << 16 | (sq & 63) << 8 | 0x80
        tgt = 0
        orec = None
        if kind in ("unit", "flyer"):
            dist = min(R.choice([rng // 3, rng * 9 // 10, rng + 60, R.randrange(64, rng + 200)]), 2000)
            ty, tx = M.pos_of(S.move_by_direction(p, R.randrange(256), min(dist, 255)))
            if dist > 255:
                ang = R.randrange(256)
                ty = (p >> 16) + (-S.sbyte(S.rom()[0x06D0A4 + ang]) * dist >> 7)
                tx = (p & 0xFFFF) + (S.sbyte(S.rom()[0x06CFA4 + ang]) * dist >> 7)
            ot = 1 if kind == "flyer" else R.choice([9, 2, 13, 16])
            orec = unit_rec(other, ot, R.choice([1, 2, 0]), ty & 0x3FFF, tx & 0x3FFF)
            tgt = REF_UNIT | other
        elif kind == "struct":
            n = R.choice(structs)
            s = md_struct(n)
            sp = ram0.l(s + 0xA)
            d = R.randrange(0, max(rng + 300, 400))
            y, x = M.pos_of(S.move_by_direction(sp, R.randrange(256), min(d, 255)))
            if d > 255:
                y, x = (sp >> 16) + R.randrange(-d, d), (sp & 0xFFFF) + R.randrange(-d, d)
            p = (y & 0x3FFF) << 16 | x & 0x3FFF
            tgt = REF_STRUCT | n
        elif kind == "tile":
            k = max(1, ut(t, 0x52) + R.choice([-1, 0, 0, 1, 3]))
            ty = min(max((sq >> 6) + R.randrange(-k, k + 1), 1), 62)
            tx = min(max((sq & 63) + R.randrange(-k, k + 1), 1), 62)
            tgt = tile_ref(ty * 64 + tx)
        elif kind == "stale":
            tgt = REF_UNIT | fs[5]
        elif kind == "own":
            tgt = tile_ref(S.square_of(p))
        rec = unit_rec(me, t, h, p >> 16, p & 0xFFFF)
        put16(rec, 0x5A, tgt)
        # aim: on target, a little off, or turning still
        tp = ref_pos(ram0.with_unit(other, orec) if orec else ram0, tgt) if tgt else p
        face = (tile_direction(p, tp) + R.choice([0, 0, 0, 3, -3, 7, 8, 9, -9, 128])) & 0xFF
        turret = ut(t, 0x0C) & 0x40
        o = 0x6B if turret else 0x68
        rec[o:o + 3] = bytes((0, face, face))
        if R.random() < 0.1:
            rec[o + 1] = (face + 40) & 0xFF                 # still turning
        rec[0x56] = 0 if R.random() < 0.85 else 3
        if ut(t, 0x38) & 0x400 and R.random() < 0.5:
            put16(rec, 0x12, R.randrange(1, ut(t, 0x10) // 2 + 1))
        rec[4] |= R.choice([0, 0x10])
        rec[6] |= R.choice([0, 0, 0x20])
        if orec:
            rg.poke_unit(other, orec)
        rg.poke_unit(me, rec)
        rg.poke_w("rnd_seed", [R.randrange(256) for _ in range(3)])
        pre = probe(rg)
        step = rg.call("ef_u_fire", ix=UNITS + me * U_SIZE + O_SCRIPT, frames=6)
        cases.append((t, kind, pre, step))
        # the expected projectile goes again, so the next is in slot 12 too
        rm = rg.call("unit_remove", ix=UNITS + 12 * U_SIZE, frames=3) \
            if expect_fire(ram0, rec, orec, other, tgt) else None
        cases[-1] += (rm,)
    rg.run()
    T = Tally(out)
    kinds = {}
    for t, kind, pre, step, rm in cases:
        a = rg.ram(pre)
        units = {n: urec(a, n) for n in range(102)}
        r = units[me]
        r0 = bytearray(r)
        ans, proj = fire_model(a, r, units, globs(rg, a))
        after = rg.ram(step)
        u = urec(after, me)
        kinds[WHY.last] = kinds.get(WHY.last, 0) + 1
        exp = {"answer": ans, "target": w16(r, 0x5A), "move": w16(r, 0x5C),
               "flags": r[4] & 0x10, "flags2": r[6] & 0x60, "action": r[0x54]}
        got = {"answer": rg.regs(step)["hl"], "target": w16(u, 0x5A), "move": w16(u, 0x5C),
               "flags": u[4] & 0x10, "flags2": u[6] & 0x60, "action": u[0x54]}
        if ans:
            exp["reload"] = True
            got["reload"] = u[0x56] in (r[0x56], (r[0x56] + 1) & 0xFF)
        else:
            exp["reload"], got["reload"] = r0[0x56], u[0x56]
        if proj:
            q = urec(after, 12)
            exp["used"], got["used"] = 1, q[4] & 1
            for key, val in proj.items():
                g = {"type": q[2], "house": q[8], "hp": w16(q, 0x12),
                     "origin": w16(q, 0x52), "face": q[0x6A], "pos": pos(q),
                     "target": w16(q, 0x5A), "dest": w16(q, 0x4E) << 16 | w16(q, 0x50),
                     "fireDelay": q[0x56], "big": q[4] >> 6 & 1, "linked": q[3]}[key]
                exp["proj " + key], got["proj " + key] = val, g
        for key in exp:
            T.check(got[key] == exp[key], lambda: f"{kind}: type {t} house {r0[8]} "
                    f"target {w16(r0, 0x5A):#x} ({WHY.last}): {key} {got[key]}, "
                    f"expected {exp[key]}")
    out.append(f"  (cases {dict(sorted(kinds.items()))})")
    return T.ok, T.bad, rg


def expect_fire(ram0, rec, orec, other, tgt):
    """Whether a case is set up to fire (so its projectile is removed
    afterwards) - the model on the loaded state with the pokes applied."""
    a = ram0.with_unit(rec[0], rec)
    if orec:
        a = a.with_unit(other, orec)
    units = {n: urec(a, n) for n in range(102)}
    return fire_model(a, units[rec[0]], units, None)[0] == 1


def enemy_unit(a, r, mode):
    """unit_find_enemy_unit $04730C: the first eligible, in list order."""
    h, t = r[8], r[2]
    side = 1 if S.allied(a, h, PLAYER) else 0
    rng = ut(t, 0x52) << 8 & 0xFFFF
    if mode == 2:
        rng = rng * 2 & 0xFFFF
    org = w16(r, 0x52)
    if not org:
        put16(r, 0x52, tile_ref(sq_of(w16(r, 0x0A), w16(r, 0x0C))))
        home = pos(r)
    else:
        home = ref_pos(a, org)
    for v in a.unit_list(side):
        vr = urec(a, v)
        if not vr[9] >> h & 1 or not w16(vr, 4) & 2:
            continue
        if not S.valid_square(a, S.square_of(pos(vr))):
            continue
        if mt(vr[2]) == 4 and not ut(t, 0x0C) & 0x1000:
            continue
        if mode == 1:
            if sgn(S.tile_distance(pos(r), pos(vr))) > sgn(rng):
                continue
        elif mode == 2:
            if sgn(S.tile_distance(home, pos(vr))) > sgn(rng):
                continue
        elif mode not in (0, 4):
            continue
        if squares(pos(r), pos(vr)) == 0:
            continue
        return v
    return None


def struct_priority(a, r, n):
    """unit_struct_target_priority $010688."""
    s = srec(a, n)
    if S.allied(a, r[8], s[8]) or not s[9] >> r[8] & 1:
        return 0
    p = (st(s[2], 0x2E) + st(s[2], 0x30)) & 0xFFFF
    d = squares(pos(r), pos(s))
    if d:
        p //= d
    return min(p, 32000)


def attack_score(a, r, v):
    """unit_attack_score $047166."""
    vr = urec(a, v)
    if not w16(vr, 4) & 2 or not vr[9] >> r[8] & 1 or v == r[0]:
        return 0
    if S.allied(a, r[8], vr[8]) or not ut(vr[2], 0x0C) & 0x2000:
        return 0
    if mt(vr[2]) == 4:
        if not ut(r[2], 0x0C) & 0x1000:
            return 0
        if not unveiled(a, S.square_of(pos(vr))) and vr[8] == PLAYER:
            return 0
    if not S.valid_square(a, S.square_of(pos(vr))):
        return 0
    d = squares(pos(r), pos(vr))
    if not S.valid_square(a, S.square_of(pos(r))):
        return 0
    p = (ut(vr[2], 0x2E) + ut(vr[2], 0x30)) & 0xFFFF
    if d:
        p = p // d + 1
    return min(p, 0x7D00)


def best_struct(a, r, mode):
    """unit_find_best_struct_target $01072C."""
    side = 1 if S.allied(a, r[8], PLAYER) else 0
    home = ref_pos(a, w16(r, 0x52))
    rng = ut(r[2], 0x52) << 8 & 0xFFFF
    best, score = None, 0
    for n in a.struct_list(side):
        s = srec(a, n)
        if mode in (1, 2):
            lay = st(s[2], 0x3C)
            c = S.rom_l(0x06B930 + 4 * lay)
            centre = (pos(s) + c) & 0xFFFFFFFF
            if mode == 1 and sgn(S.tile_distance(pos(r), centre)) > sgn(rng):
                continue
            if mode == 2 and S.tile_distance(home, centre) > 2 * rng:
                continue
        elif mode not in (0, 4):
            continue
        p = struct_priority(a, r, n)
        if p >= score:
            best, score = n, p
    return best if score else None


def find_target(a, r, mode):
    """unit_find_target $048F00 -> a reference (r's origin written)."""
    if mode == 4:
        s = best_struct(a, r, 4)
        if s is not None:
            return REF_STRUCT | s
        v = enemy_unit(a, r, 4)
        return REF_UNIT | v if v is not None else 0
    v = enemy_unit(a, r, mode)
    s = None if r[2] == 8 else best_struct(a, r, mode)
    if s is None:
        return REF_UNIT | v if v is not None else 0
    if v is None:
        return REF_STRUCT | s
    if attack_score(a, r, v) > struct_priority(a, r, s):
        return REF_UNIT | v
    return REF_STRUCT | s


def g_target(b, out):
    R.seed(35)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    me = free_slots(ram0)[0]
    mission_units = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1]
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    free = free_squares(ram0)
    cases = []
    for i in range(110):
        t = R.choice([9, 10, 11, 12, 7, 8, 13, 15, 2, 4, 1, 3, 6, 9, 7])
        h = R.choice([0, 0, 1, 2, 4])
        sq = R.choice(free)
        rec = unit_rec(me, t, h, (sq >> 6) << 8 | R.randrange(256), (sq & 63) << 8 | R.randrange(256))
        if R.random() < 0.5:
            put16(rec, 0x52, tile_ref(R.choice(free)))
        rg.poke_unit(me, rec)
        # stir: some units seen or not, some moved near
        for n in R.sample(mission_units, 8):
            rg.poke_u(UNITS + n * U_SIZE + 9, [R.choice([0xFF, 0xFF, 1 << h, 0, 0x1F ^ (1 << h)])])
            if R.random() < 0.5:
                y = min(max((sq >> 6) + R.randrange(-6, 7), 1), 62)
                x = min(max((sq & 63) + R.randrange(-6, 7), 1), 62)
                rg.poke_u(UNITS + n * U_SIZE + 0x0A, [R.randrange(256), y, R.randrange(256), x])
        for n in R.sample(structs, 4):
            rg.poke_struct(n, 9, [R.choice([0xFF, 0, 1 << h])])
        mode = R.choice([0, 1, 1, 2, 2, 4, 3])
        pre = probe(rg)
        cases.append((t, mode, pre, rg.call("unit_find_target", ix=UNITS + me * U_SIZE,
                                             a=mode, frames=4)))
    rg.run()
    T = Tally(out)
    kinds = {}
    for t, mode, pre, step in cases:
        a = rg.ram(pre)
        r = urec(a, me)
        org0 = w16(r, 0x52)
        exp = find_target(a, r, mode)
        u = rg.unit(step, me)
        got = rg.regs(step)["hl"]
        kinds[exp >> 14] = kinds.get(exp >> 14, 0) + 1
        T.check(got == exp, lambda: f"type {t} house {r[8]} mode {mode} origin {org0:#x}: "
                f"{got:#x}, expected {exp:#x}")
        T.check(w16(u, 0x52) == w16(r, 0x52), lambda: f"type {t} mode {mode}: origin "
                f"{w16(u, 0x52):#x}, expected {w16(r, 0x52):#x}")
    out.append(f"  (answers by kind {dict(sorted(kinds.items()))}: 0 none, 1 unit, 2 structure)")
    return T.ok, T.bad, rg


def g_settarget(b, out):
    R.seed(36)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    fs = free_slots(ram0)
    me = fs[0]
    mission_units = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1]
    flyers = [n for n in mission_units if mt(ram0.b(md_unit(n) + 2)) == 4]
    structs = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1]
    occupied = [sq for sq in range(64, 4032) if ram0.b(S.MAP + 4 * sq + 2) & 0x30]
    free = free_squares(ram0)
    cases = []
    for i in range(90):
        t = R.choice([9, 10, 13, 15, 2, 16, 1, 0, 7, 12, 11, 4])
        sq = R.choice(free)
        rec = unit_rec(me, t, R.choice([0, 1, 2]), (sq >> 6) << 8 | 0x80, (sq & 63) << 8 | 0x80)
        k = R.random()
        if k < 0.25:
            ref = REF_UNIT | R.choice(mission_units)
        elif k < 0.35 and flyers:
            ref = REF_UNIT | R.choice(flyers)
        elif k < 0.5:
            ref = REF_STRUCT | R.choice(structs)
        elif k < 0.7:
            ref = tile_ref(R.choice(occupied))
        elif k < 0.8:
            ref = tile_ref(R.choice(free))
        elif k < 0.85:
            ref = REF_UNIT | me
        elif k < 0.9:
            ref = REF_UNIT | fs[4]                       # stale
        else:
            ref = tile_ref(sq)
        if R.random() < 0.1:
            put16(rec, 0x5A, ref)                        # unchanged
        rg.poke_unit(me, rec)
        pre = probe(rg)
        cases.append((t, ref, pre, rg.call("unit_set_target", ix=UNITS + me * U_SIZE,
                                            hl=ref, frames=3)))
    rg.run()
    T = Tally(out)
    for t, ref, pre, step in cases:
        a = rg.ram(pre)
        units = {n: urec(a, n) for n in range(102)}
        r = units[me]
        set_target(a, units, r, ref)
        u = rg.unit(step, me)
        exp = (w16(r, 0x5A), w16(r, 0x5C), r[0x7C])
        got = (w16(u, 0x5A), w16(u, 0x5C), u[0x7C])
        T.check(got == exp, lambda: f"type {t} ref {ref:#x}: (target, move, route) "
                f"{tuple(hex(v) for v in got)}, expected {tuple(hex(v) for v in exp)}")
    return T.ok, T.bad, rg


def deviate_model(a, r, house):
    """unit_deviate $047882 -> 1 if it went over."""
    t, h = r[2], r[8]
    if not ut(t, 0x38) & 0x8000 or r[0x5F] or ut(t, 0x38) & 0x1000 or h == 3:
        return 0
    chance = toughness(h)
    if h != PLAYER:
        chance -= chance >> 3
    seed = tuple(a.wp[a.sym["rnd_seed"] - 0x8000:][:3])
    if not rnd(seed)[1] < chance:
        return 0
    r[8] = house
    r[0x5F] = 120
    r[9] = 0xFF if house == PLAYER else 1 << house
    # on a revealed square the player sees it ($0479BA: the square's
    # centre, so the square itself; unit_seen_by_house - an Atreides
    # player's sight is the Fremen's too)
    if a.b(S.MAP + 4 * S.square_of(pos(r)) + 2) & 8:
        r[9] |= 1 << PLAYER | (8 if PLAYER == 1 and t != 25 else 0)
    give_order(r, ut(t, 0x28) & 0xFF if PLAYER == 2 else ut(t, 0x4A) & 0xFF)
    if t != 16:
        put16(r, 0x5A, 0)
    put16(r, 0x5C, 0)
    return 1


def wear_model(a, r, n):
    """unit_deviation_wear $047A5A -> 1 if it went home."""
    if not r[0x5F]:
        return 0
    if not n:
        n = toughness(r[8])
    if not ut(r[2], 0x38) & 0x8000:
        return 0
    if n < S.sbyte(r[0x5F]):
        r[0x5F] -= n
        return 0
    r[8] = r[0x74]
    r[0x5F] = 0
    r[9] = 0xFF if r[8] == PLAYER else 1 << r[8]
    give_order(r, ut(r[2], 0x28) & 0xFF if r[8] == PLAYER else ut(r[2], 0x4A) & 0xFF)
    if r[2] != 16:
        put16(r, 0x5A, 0)
    put16(r, 0x5C, 0)
    return 1


def g_deviate(b, out):
    R.seed(37)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    ground = [n for n in range(22, 102) if ram0.w(md_unit(n) + 4) & 1]
    cases = []
    for i in range(80):
        n = R.choice(ground)
        o = UNITS + n * U_SIZE
        rg.poke_w("rnd_seed", [R.randrange(256) for _ in range(3)])
        # nowhere to go, so a new order takes at once
        rg.poke_u(o + 0x4E, [0, 0, 0, 0])
        if R.random() < 0.55:
            rg.poke_u(o + 0x5F, [0])
            house = R.choice([2, 2, 0, 1])
            pre = probe(rg)
            cases.append(("deviate", n, house, pre,
                          rg.call("unit_deviate", ix=o, a=house, frames=6)))
        else:
            dev = R.choice([1, 20, 119, 120, 127, 128, 60])
            rg.poke_u(o + 0x5F, [dev])
            rg.poke_u(o + 0x74, [R.choice([0, 1, 2, 4])])
            k = R.choice([0, 0, 1, 20, 10, 150])
            pre = probe(rg)
            cases.append(("wear", n, k, pre,
                          rg.call("unit_deviation_wear", ix=o, a=k, frames=6)))
    rg.run()
    T = Tally(out)
    turned = 0
    for kind, n, arg, pre, step in cases:
        a = rg.ram(pre)
        r = urec(a, n)
        r0 = bytearray(r)
        ans = deviate_model(a, r, arg) if kind == "deviate" else wear_model(a, r, arg)
        turned += ans
        u = rg.unit(step, n)
        exp = {"answer": ans, "house": r[8], "deviated": r[0x5F], "seen": r[9],
               "action": r[0x54], "target": w16(r, 0x5A), "move": w16(r, 0x5C)}
        got = {"answer": rg.regs(step)["a"], "house": u[8], "deviated": u[0x5F],
               "seen": u[9], "action": u[0x54], "target": w16(u, 0x5A),
               "move": w16(u, 0x5C)}
        if ans:
            side = lambda hh: 0 if S.allied(a, hh, PLAYER) else 1  # noqa: E731
            after = rg.ram(step)
            exp["list"] = side(r[8])
            got["list"] = next((sd for sd in (0, 1) if n in after.unit_list(sd)), None)
        for key in exp:
            T.check(got[key] == exp[key], lambda: f"{kind} unit {n} (type {r0[2]} house "
                    f"{r0[8]} deviated {r0[0x5F]}) arg {arg}: {key} {got[key]}, "
                    f"expected {exp[key]}")
    out.append(f"  ({turned} of {len(cases)} changed sides)")
    return T.ok, T.bad, rg


def g_die(b, out):
    R.seed(38)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    units = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1
             and ram0.b(md_unit(n) + 2) not in (6,)]
    R.shuffle(units)
    cases = []
    for n in units[:32]:
        rg.poke_w("score", R.choice([0, 1, 3, 50, 400]).to_bytes(2, "little"))
        rg.poke_w("killed_allied", R.randrange(20).to_bytes(2, "little"))
        rg.poke_w("killed_enemy", R.randrange(20).to_bytes(2, "little"))
        pre = probe(rg)
        cases.append((n, pre, rg.call("ef_u_die", ix=UNITS + n * U_SIZE + O_SCRIPT, frames=6)))
    rg.run()
    T = Tally(out)
    for n, pre, step in cases:
        a = rg.ram(pre)
        r = urec(a, n)
        t, h = r[2], r[8]
        sc = [int.from_bytes(a.wp[rg.a(k) - 0x8000:][:2], "little")
              for k in ("score", "killed_allied", "killed_enemy")]
        if mt(t) != 4:
            s = max(ut(t, 0x16) // 100, 1)
            if h == PLAYER:
                sc[1] += 1
                sc[0] -= min(s, sc[0])
            else:
                sc[2] += 1
                sc[0] += s
        after = rg.ram(step)
        got = [int.from_bytes(after.wp[rg.a(k) - 0x8000:][:2], "little")
               for k in ("score", "killed_allied", "killed_enemy")]
        T.check(got == sc, lambda: f"unit {n} type {t} house {h}: (score, lost, "
                f"killed) {got}, expected {sc}")
        T.check(not after.w(md_unit(n) + 4) & 1, lambda: f"unit {n} type {t}: still used")
    return T.ok, T.bad, rg


def g_turret(b, out):
    R.seed(39)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    turrets = [n for n in range(73) if ram0.w(md_struct(n) + 4) & 1
               and ram0.b(md_struct(n) + 2) in (15, 16)]
    assert turrets, "no turret in the mission"
    mission_units = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1]
    fs = free_slots(ram0)
    other = fs[0]
    cases = []
    for i in range(80):
        n = R.choice(turrets)
        s = md_struct(n)
        sp = ram0.l(s + 0xA)
        arg = R.choice([1280, 2048])
        # a unit somewhere round the turret, of any house, maybe a flyer
        d = R.choice([100, 400, 700, 767, 768, 900, 1300, 2100, 3000, 4000])
        ang = R.randrange(256)
        y = (sp >> 16) + (-S.sbyte(S.rom()[0x06D0A4 + ang]) * d >> 7)
        x = (sp & 0xFFFF) + (S.sbyte(S.rom()[0x06CFA4 + ang]) * d >> 7)
        t = R.choice([9, 2, 13, 1, 1, 16])
        rec = unit_rec(other, t, R.choice([0, 1, 2, 4]), y & 0x3FFF, x & 0x3FFF)
        rec[9] = R.choice([0xFF, 0, 1 << ram0.b(s + 8)])
        rec[4] = R.choice([3, 3, 3, 1, 7])
        rg.poke_unit(other, rec)
        for m in R.sample(mission_units, 5):
            rg.poke_u(UNITS + m * U_SIZE + 9, [R.choice([0xFF, 0])])
        which = R.choice(["find", "fire", "fire"])
        var2 = R.choice([0, REF_UNIT | other, REF_UNIT | other, REF_UNIT | R.choice(mission_units),
                         tile_ref(S.square_of(ram0.l(md_unit(R.choice(mission_units)) + 0xA)))])
        rg.poke_struct(n, 0x26, var2.to_bytes(2, "little"))
        label = "ef_b_find_target" if which == "find" else "ef_b_fire"
        # the script's stack holds the range
        rg.poke_struct(n, O_SCRIPT + 0x0B, [14])
        rg.poke_struct(n, O_SCRIPT + 0x16 + 28, arg.to_bytes(2, "little"))
        pre = probe(rg)
        step = rg.call(label, ix=STRUCTS + n * S_SIZE + O_SCRIPT, frames=6)
        cases.append((which, n, arg, pre, step))
        # a projectile made goes again (slot 12), a turret's too
        cases[-1] += (rg.call("unit_remove", ix=UNITS + 12 * U_SIZE, frames=3)
                      if which == "fire" and turret_fires(ram0, n, rec, other, var2, arg)
                      else None,)
    rg.run()
    T = Tally(out)
    kinds = {}
    for which, n, arg, pre, step, rm in cases:
        a = rg.ram(pre)
        s = srec(a, n)
        after = rg.ram(step)
        s1 = srec(after, n)
        if which == "find":
            ans = turret_find(a, s, arg)
            exp = {"answer": ans, "has": (s[6] >> 7 & 1) if ans == w16(s, 0x26) and ans
                   else int(bool(ans))}
            got = {"answer": rg.regs(step)["hl"], "has": s1[6] >> 7 & 1}
            kinds[("find", ans >> 14)] = kinds.get(("find", ans >> 14), 0) + 1
        else:
            ans, proj, var = turret_fire(a, s, arg)
            exp = {"answer": ans, "var2": var}
            got = {"answer": rg.regs(step)["hl"], "var2": w16(s1, 0x26)}
            if proj:
                q = urec(after, 12)
                for key, val in proj.items():
                    exp["proj " + key] = val
                    got["proj " + key] = {"type": q[2], "hp": w16(q, 0x12),
                                          "origin": w16(q, 0x52), "linked": q[3],
                                          "house": q[8], "pos": pos(q)}[key]
            kinds[("fire", ans)] = kinds.get(("fire", ans), 0) + 1
        for key in exp:
            T.check(got[key] == exp[key], lambda: f"{which} turret {n} (type {s[2]}) arg "
                    f"{arg} var2 {w16(s, 0x26):#x}: {key} {got[key]}, expected {exp[key]}")
    out.append(f"  (cases {sorted(kinds.items())})")
    return T.ok, T.bad, rg


def turret_find(a, s, n):
    """emc_build_find_target $00CA0C -> the reference."""
    n3 = 3 * n
    tp = pos(s)
    v = unit_ref_slot(w16(s, 0x26))
    if v is not None:
        vr = urec(a, v)
        if w16(vr, 4) & 2:
            d = S.tile_distance(pos(vr), tp)
            if d < (n3 if mt(vr[2]) == 4 else n):
                return w16(s, 0x26)
    side = 1 if S.allied(a, s[8], PLAYER) else 0
    best, score = None, 0x7D00
    for v in a.unit_list(side):
        vr = urec(a, v)
        if not w16(vr, 4) & 2 or not S.valid_square(a, S.square_of(pos(vr))):
            continue
        d = S.tile_distance(pos(vr), tp)
        if vr[9] >> s[8] & 1:
            if d < score and d < n:
                best, score = v, d
        elif vr[2] == 1 and d < score and d < n3:
            best = v
            break
    return REF_UNIT | best if best is not None else 0


def turret_fire(a, s, n):
    """emc_build_fire $00CDD0 -> (answer, projectile, variable 2 after)."""
    ref = w16(s, 0x26)
    if not ref:
        return 0, None, ref
    if not S.valid_square(a, S.ref_square(a, ref)):
        return 0, None, ref
    v = unit_ref_slot(ref)
    if v is not None:
        vr = urec(a, v)
        if vr[2] != 1:
            d = S.tile_distance(pos(s), pos(vr))
            if sgn(d) >= sgn(n) or not w16(vr, 4) & 2 or w16(vr, 4) & 4 \
                    or S.allied(a, s[8], vr[8]):
                return 0, None, 0
    kind = 23
    tpos = ref_pos(a, ref)
    if s[2] == 16 and sgn(S.tile_distance(pos(s), tpos)) >= 0x300:
        kind = 20
    org = (pos(s) + 0x00800080) & 0xFFFFFFFF
    if kind == 20:
        ans, dmg = ut(7, 0x50) + 30, 30
        start = org
    else:
        ans, dmg = ut(9, 0x50), 20
        start = S.move_by_direction(S.move_by_direction(org, 0, 32),
                                    tile_direction(org, tpos), 128)
    return ans, {"type": kind, "hp": dmg, "origin": REF_STRUCT | s[0], "linked": 9,
                 "house": s[8], "pos": start}, ref


def turret_fires(ram0, n, rec, other, var2, arg):
    a = ram0.with_unit(other, rec)
    s = srec(a, n)
    put16(s, 0x26, var2)
    return turret_fire(a, s, arg)[0] != 0


def g_missile(b, out):
    """unit_launch_house_missile ($02313A): house_missile is the
    placeholder (a Death Hand record of the house); it is freed and a real
    Death Hand fired from the house's palacePosition at the square,
    scattered by tile_move_by_random with 160 ($011688: sine * r >> 3, r
    a random part of 160, so up to 2540 - nearly ten squares - which is
    the Mega Drive's wild Death Hand): the projectile's target is within
    ten squares of the aimed one, and over the seeds not always the same
    one."""
    ram0 = load_ram(b, HOUSE, MISSION)
    mine = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1
            and ram0.b(md_unit(n) + 8) == PLAYER]
    aim = 30 * 64 + 30                              # the square, row * 64 + column
    seeds = [(0x12, 0x34, 0x56), (0x01, 0x02, 0x03), (0x77, 0x11, 0x99),
             (0x5A, 0xC3, 0x0F), (0x80, 0x40, 0x20), (0xFE, 0xDC, 0xBA),
             (0x13, 0x57, 0x9B), (0x24, 0x68, 0xAC)]
    T = Tally(out)
    hit = set()
    for seed in seeds:
        rg = Rig(b, HOUSE, MISSION, seed=seed)
        n = mine[0]
        rec = UNITS + n * U_SIZE
        rg.poke_u(rec + 2, [18])                        # the placeholder's type
        rg.poke_w(rg.a("house_missile"), rec.to_bytes(2, "little"))
        palace = (20 << 8 | 0x80).to_bytes(2, "little") + (20 << 8 | 0x80).to_bytes(2, "little")
        rg.poke_u(HOUSES + PLAYER * H_SIZE + 0x22, palace)
        step = rg.call("unit_launch_house_missile", hl=aim, frames=8)
        rg.run()
        a = rg.ram(step)
        hm = int.from_bytes(a.wp[rg.a("house_missile") - 0x8000:][:2], "little")
        T.check(rg.regs(step)["done"] and hm == 0, lambda: f"seed {seed}: house_missile {hm:#x} after")
        hands = [k for k in range(102) if a.w(md_unit(k) + 4) & 1 and a.b(md_unit(k) + 2) == 18]
        T.check(len(hands) == 1, lambda: f"seed {seed}: {len(hands)} Death Hands after the launch")
        if len(hands) != 1:
            continue
        tm = a.w(md_unit(hands[0]) + 0x5C)
        ta = a.w(md_unit(hands[0]) + 0x5A)
        ref = tm if tm >> 14 == 3 else ta
        sq = (ref & 0x3F00) >> 2 | (ref & 0x7E) >> 1
        T.check(ref >> 14 == 3 and abs((sq >> 6) - 30) <= 10 and abs((sq & 63) - 30) <= 10,
                lambda: f"seed {seed}: the Death Hand's target {ref:#x} (square {sq >> 6},{sq & 63})")
        hit.add(sq)
        rg.cleanup()
    T.check(len(hit) > 1, lambda: f"the aim is never scattered: always square {hit}")
    return T.ok, T.bad, None


def g_aim(b, out):
    """UNIT 58 aim ($044E04): the reference into targetAttack, and into
    targetMove as well for a unit without a turret (the hull turns to
    it); a unit with one keeps its targetMove.  Answers the reference."""
    R.seed(41)
    ram0 = load_ram(b, HOUSE, MISSION)
    rg = Rig(b, HOUSE, MISSION)
    units = [n for n in range(102) if ram0.w(md_unit(n) + 4) & 1
             and ram0.b(md_unit(n) + 2) < 25 and ram0.b(md_unit(n) + 2) not in (16, 17)]
    R.shuffle(units)
    cases = []
    for n in units[:24]:
        other = R.choice([k for k in units if k != n])
        ref = REF_UNIT | other
        rec = bytearray(urec(ram0, n))
        with_arg(rec, ref)
        rg.poke_unit(n, rec)
        pre = probe(rg)
        cases.append((n, ref, pre, rg.call("ef_u_aim", ix=UNITS + n * U_SIZE + O_SCRIPT, frames=6)))
    rg.run()
    T = Tally(out)
    moved = 0
    for n, ref, pre, step in cases:
        before = rg.ram(pre)
        after = rg.ram(step)
        t = before.b(md_unit(n) + 2)
        tm0, tm1 = before.w(md_unit(n) + 0x5C), after.w(md_unit(n) + 0x5C)
        ta1 = after.w(md_unit(n) + 0x5A)
        T.check(rg.regs(step)["done"] and rg.regs(step)["hl"] == ref and ta1 == ref,
                lambda: f"unit {n} type {t}: answers {rg.regs(step)['hl']:#x}, targetAttack {ta1:#x}, wanted {ref:#x}")
        T.check(tm1 in (tm0, ref),
                lambda: f"unit {n} type {t}: targetMove {tm1:#x} (was {tm0:#x}, the reference {ref:#x})")
        moved += tm1 == ref
    T.check(moved > 0, lambda: "no unit without a turret took the reference as its targetMove")
    return T.ok, T.bad, rg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    b = args.build_dir
    s = Suite()
    for name, fn in (("damage", g_damage), ("struct", g_struct), ("explode", g_explode),
                     ("fire", g_fire), ("target", g_target), ("settarget", g_settarget),
                     ("deviate", g_deviate), ("die", g_die), ("turret", g_turret),
                     ("missile", g_missile), ("aim", g_aim)):
        s.group(name, lambda o, fn=fn: fn(b, o), args.only)
    sys.exit(1 if s.total_bad else 0)


if __name__ == "__main__":
    main()
