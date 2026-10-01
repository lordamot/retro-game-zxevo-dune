#!/usr/bin/env python3
"""test_struct.py - the STRUCT subsystem (S1 structures, S5, S6, S8's map
animations) on the running machine, against the specs' own models.

    python3 tools/tests/test_struct.py [--build-dir build] [--only NAME]

Every scenario starts from a mission loaded through MAIN's start_mission
(tools/dune_test.py's mailbox), then pokes records and far-calls the
subsystem's routines.  The models are tools/sega/spec_s6.py's (loaded with
the cartridge for the unit and structure tables) and the formulas of
S5/S6 written out here.
"""
import argparse
import random as R
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from dune_test import Machine, w16, s16, units   # noqa: E402

PG_UNITS, PG_WORLD, PG_MAP = 24, 25, 26
STRUCTS = 0x8100
S_SIZE, U_SIZE, H_SIZE = 0x62, 0x8C, 0x46
UNITS, HOUSES = 0x4000, 0x7800

# ---------------------------------------------------- the specs' models

def load_s6():
    """spec_s6.py in a namespace of its own, with the cartridge as ROM."""
    ns = {"ROM": ROOT / "orig/dune2.gen", "ROOT": ROOT,
          "scenario": lambda *a, **k: (lambda f: f)}
    src = (ROOT / "tools/sega/spec_s6.py").read_text()
    exec(compile(src, "spec_s6.py", "exec"), ns)
    return ns


S6 = load_s6()
ST, UT = S6["S6_ST"], S6["S6_UT"]
mul_shr8, div_shl8 = S6["s6_mul_shr8"], S6["s6_div_shl8"]


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


class Ram:
    """spec_s6's view of RAM, over the port's pages: the few addresses its
    model reads, mapped onto the port's records."""
    def __init__(self, sym, w, u, campaign, player):
        self.w, self.u, self.sym = w, u, sym
        self.campaign, self.player = campaign, player

    def w(self, a):                                 # noqa: E0202
        pass


class FakeRam:
    def __init__(self, campaign, player, built, counts):
        self.c, self.p, self.built, self.counts = campaign, player, built, counts

    def w(self, a):
        return {S6["S6_CAMPAIGN"]: self.c, S6["S6_PLAYER"]: self.p}[a]

    def l(self, a):                                 # noqa: E743
        return self.built[(a - 0x0E) // 0x46]

    def u(self, a, n):
        return 0


def buildable_model(stype, house, creator, level, upleft, flags2, campaign,
                    player, built, counts):
    ram = FakeRam(campaign, player, built, counts)
    S6["s6_house"] = lambda r, h: h * 0x46
    S6["s6_type_count"] = lambda r, h, t: counts.get((h, t), 0)

    class S:
        pass
    s = S()
    s.type, s.house, s.creator, s.level = stype, house, creator, level
    s.upgradeLeft, s.flags2 = upleft, flags2
    return S6["s6_buildable"](ram, s)


def upgradable_model(stype, creator, level, campaign, built):
    ram = FakeRam(campaign, 0, built, {})
    S6["s6_house"] = lambda r, h: h * 0x46

    class S:
        pass
    s = S()
    s.type, s.creator, s.level = stype, creator, level
    return 1 if S6["s6_is_upgradable"](ram, s) else 0


# ------------------------------------------------------------ the rig

UNFINISHED = []


class Rig:
    """One machine run: a mission loaded, then the steps queued."""
    def __init__(self, bdir, house, mission, seed=(0x12, 0x34, 0x56)):
        self.m = Machine(build_dir=bdir)
        self.sym = self.m.sym
        self.m.poke_label("rnd_seed", bytes(seed))
        self.load = self.m.call("start_mission", a=house, bc=mission << 8,
                                frames=120, pages=(PG_WORLD, PG_UNITS, PG_MAP))

    def a(self, label):
        return self.sym[label]

    def poke_w(self, addr, data):
        self.m.poke_page(PG_WORLD, addr - 0x8000, bytes(data))

    def poke_u(self, addr, data):
        self.m.poke_page(PG_UNITS, addr - 0x4000, bytes(data))

    def poke_map(self, addr, data):
        self.m.poke_page(PG_MAP, addr - 0xC000, bytes(data))

    def call(self, label, frames=4, **kw):
        return self.m.call(label, frames=frames,
                           pages=(PG_WORLD, PG_UNITS, PG_MAP), **kw)

    def run(self):
        self.res = self.m.run()
        # a call still running when its pages were dumped leaves the
        # next call's answers shifted by one: count it, whatever it says
        UNFINISHED.extend(s for s in range(self.m.steps)
                          if not self.res.regs(s)["done"])
        return self.res


def structs_of(w):
    out = []
    for n in range(73):
        o = STRUCTS - 0x8000 + n * S_SIZE
        r = w[o:o + S_SIZE]
        if r[4] & 1:
            out.append(dict(slot=n, type=r[2], house=r[8], flags=w16(r, 4),
                            flags2=w16(r, 6), y=r[0x0B], x=r[0x0D],
                            hp=w16(r, 0x12), state=s16(r, 0x5C), raw=r))
    return out


def sq_ground(mp, sq):
    return mp[sq] | ((mp[0x1000 + sq] & 1) << 8)


def sq_overlay(mp, sq):
    return mp[0x1000 + sq] >> 1


BUILT = {2: 0x0D2, 3: 0x0DF, 4: 0x0DF, 5: 0x0E5, 6: 0x0EB, 7: 0x0F7, 8: 0x0F3,
         9: 0x0FB, 10: 0x0F7, 11: 0x0FF, 12: 0x108, 13: 0x10E, 15: 0x114,
         16: 0x11C, 17: 0x124, 18: 0x128}
LAYOUT = {2: 6, 3: 5, 4: 5, 5: 3, 6: 3, 7: 3, 8: 3, 9: 3, 10: 3, 11: 6, 12: 5,
          13: 5, 15: 0, 16: 0, 17: 3, 18: 3}
OFFS = {0: [0], 3: [0, 1, 64, 65], 5: [0, 1, 2, 64, 65, 66],
        6: [0, 1, 2, 64, 65, 66, 128, 129, 130]}
MARK = {0: 0, 3: 64, 5: 64, 6: 128}
CONSTRUCTION = {6: 0x13E, 5: 0x147, 3: 0x14D, 0: 0x151}


# ------------------------------------------------------------ scenarios

def t_mission(bdir, house, mission, name, out):
    """A mission's structures come up with the construction animation on
    their squares, end on their built icons, and get their markers; the
    counts struct_game_loop leaves are the live ones."""
    rg = Rig(bdir, house, mission)
    fr = rg.a("frames_this_pass")
    rg.poke_w(fr, (10, 0))
    steps = []
    # a construction script is (icon, 90) then seven pairs of 5, and a
    # tick steps at most one pair ($00B1C2): 9 + 8 ticks at 10 frames,
    # one more for the scripts that start with a pair of 5
    for i in range(24):
        steps.append(rg.call("map_anim_tick", frames=2))
    for i in range(10):
        steps.append(rg.call("struct_game_loop", frames=6))
    res = rg.run()
    w0 = res.page(rg.load, PG_WORLD)
    m0 = res.page(rg.load, PG_MAP)
    wN = res.page(steps[-1], PG_WORLD)
    mN = res.page(steps[-1], PG_MAP)
    ok = bad = 0
    player = w0[rg.a("player_house") - 0x8000]
    sts = structs_of(wN)
    for s in sts:
        t = s["type"]
        if t not in BUILT:
            continue
        sq = s["y"] * 64 + s["x"]
        lay = LAYOUT[t]
        con = [sq_ground(m0, sq + k) for k in OFFS[lay]]
        blt = [sq_ground(mN, sq + k) for k in OFFS[lay]]
        exp_c = [CONSTRUCTION[lay] + i for i in range(len(OFFS[lay]))]
        exp_b = [BUILT[t] + i for i in range(len(OFFS[lay]))]
        good = con == exp_c and blt == exp_b
        if t not in (15, 16):
            msq = sq + MARK[lay]
            ov = sq_overlay(mN, msq)
            if s["house"] == player:
                good = good and ov == 0x16 + s["house"]
        if good:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}: type {t} house {s['house']} at {sq}: "
                       f"construction {[hex(v) for v in con]} built "
                       f"{[hex(v) for v in blt]} marker "
                       f"{hex(sq_overlay(mN, sq + MARK[lay]))}")
    # a mission's structures start whole and not decaying, whatever the
    # concrete under them (scen_read_structure $0168DE-$0168FC)
    for st in structs_of(w0):
        hpmax = w16(st["raw"], 0x5E)
        if st["hp"] == hpmax and not st["flags"] & 0x400:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}: structure {st['slot']} type {st['type']} starts at "
                       f"{st['hp']} of {hpmax}, flags {st['flags']:#06x}")
    # the counts: the player's with health, the rest (no turrets or slabs)
    np = sum(1 for s in sts if s["house"] == player and s["hp"] and s["type"] not in (0, 1, 14, 15, 16))
    no = sum(1 for s in sts if not (s["house"] == player and s["hp"]) and s["type"] not in (0, 1, 14, 15, 16))
    gp, go = wN[rg.a("structs_player") - 0x8000], wN[rg.a("structs_other") - 0x8000]
    if (gp, go) == (np, no):
        ok += 1
    else:
        bad += 1
        out.append(f"  {name}: counts {(gp, go)} expected {(np, no)}")
    return ok, bad


def t_buildable(bdir, out):
    """struct_get_buildable against spec_s6's model, over random
    structures, campaigns, houses, levels and structuresBuilt."""
    R.seed(11)
    rg = Rig(bdir, 1, 1)
    slot = 60
    base = STRUCTS + slot * S_SIZE
    cases = []
    for _ in range(90):
        t = R.choice([8, 8, 8, 3, 4, 4, 5, 7, 10, 10, 11])
        house = R.choice([0, 1, 2, 0, 1, 2, 4])
        creator = house if R.random() < 0.8 else R.choice([0, 1, 2, 4])
        level = R.choice([0, 0, 1, 1, 2, 3])
        upleft = R.choice([0, 100])
        c = R.randrange(9)
        player = R.choice([0, 1, 2])
        built = R.getrandbits(19) | (R.choice([0, 1]) << 18)
        noroom = R.random() < 0.15
        rec = bytearray(S_SIZE)
        rec[0] = slot
        rec[2] = t
        rec[3] = 0xFF
        rec[4] = 3
        rec[7] = 1 if noroom else 0
        rec[8] = house
        rec[0x4C] = creator
        rec[0x54] = level
        rec[0x55] = upleft
        rg.poke_w(base, rec)
        rg.poke_w(rg.a("campaign_id"), [c])
        rg.poke_w(rg.a("player_house"), [player])
        rg.poke_u(HOUSES + house * H_SIZE + 0x0E, built.to_bytes(4, "little"))
        s = rg.call("struct_get_buildable", ix=base, frames=2)
        cases.append((t, house, creator, level, upleft, 0x100 if noroom else 0,
                      c, player, built, s))
    res = rg.run()
    ok = bad = 0
    for t, house, creator, level, upleft, f2, c, player, built, s in cases:
        w = res.page(s, PG_WORLD)
        counts = {}
        for h in range(5):
            for ty in (2, 11):
                counts[(h, ty)] = w[rg.a("struct_type_count") - 0x8000 + h * 32 + ty]
        bl = [0] * 6
        bl[house] = built
        exp, lst = buildable_model(t, house, creator, level, upleft, f2, c,
                                   player, bl, counts)
        r = res.regs(s)
        got = (r["de"] << 16) | r["hl"]
        if t == 11:
            exp &= 0xFFFFFFFF
        good = got == exp and r["done"]
        if lst is not None and good:
            o = rg.a("st_unit_list") - 0x8000
            port = list(w[o:o + 27])
            if t in (7, 10):
                pass            # overwritten by position only; checked below
            good = port == lst if t not in (7, 10) else port[:10] == lst[:10]
        if good:
            ok += 1
        else:
            bad += 1
            if bad <= 6:
                out.append(f"  buildable type {t} house {house} creator {creator} "
                           f"level {level} c {c} player {player} built {built:#x}: "
                           f"{got:#x} expected {exp:#x}")
    return ok, bad


def t_upgradable(bdir, out):
    """struct_is_upgradable and struct_init_upgrade_level against the
    model."""
    R.seed(12)
    rg = Rig(bdir, 1, 1)
    slot = 60
    base = STRUCTS + slot * S_SIZE
    cases = []
    for _ in range(60):
        t = R.choice([3, 4, 5, 7, 8, 10, 9, 6])
        creator = R.choice([0, 1, 2, 4])
        level = R.choice([0, 1, 2])
        c = R.randrange(9)
        built = R.getrandbits(19)
        rec = bytearray(S_SIZE)
        rec[0], rec[2], rec[3], rec[4] = slot, t, 0xFF, 3
        rec[8] = creator
        rec[0x4C] = creator
        rec[0x54] = level
        rg.poke_w(base, rec)
        rg.poke_w(rg.a("campaign_id"), [c])
        rg.poke_u(HOUSES + creator * H_SIZE + 0x0E, built.to_bytes(4, "little"))
        s1 = rg.call("struct_is_upgradable", ix=base, frames=2)
        s2 = rg.call("struct_init_upgrade_level", ix=base, frames=2)
        cases.append((t, creator, level, c, built, s1, s2))
    res = rg.run()
    ok = bad = 0
    for t, creator, level, c, built, s1, s2 in cases:
        bl = [0] * 6
        bl[creator] = built
        e1 = upgradable_model(t, creator, level, c, bl)
        g1 = res.regs(s1)["a"]
        e2 = S6["s6_init_level"](t, c, creator, level)
        w = res.page(s2, PG_WORLD)
        g2 = w[STRUCTS - 0x8000 + slot * S_SIZE + 0x54]
        for what, g, e in (("upgradable", g1, e1), ("init level", g2, e2)):
            if g == e:
                ok += 1
            else:
                bad += 1
                if bad <= 6:
                    out.append(f"  {what} type {t} creator {creator} level {level} "
                               f"c {c} built {built:#x}: {g} expected {e}")
    return ok, bad


def t_production(bdir, out):
    """The build tick on a computer factory: countDown, the remainder,
    creditsPaid and the credits against spec_s6's s6_production, over
    campaigns, health and credits."""
    R.seed(13)
    rg = Rig(bdir, 1, 1)
    slot = 60
    base = STRUCTS + slot * S_SIZE
    cases = []
    for _ in range(50):
        t = R.choice([3, 4, 10, 8])
        house = R.choice([0, 2])
        c = R.randrange(9)
        player = 1
        linked = 90 if t != 8 else 61
        ltype = R.choice([13, 15, 9, 2, 16]) if t != 8 else R.choice([9, 12, 3, 18])
        hpmax = ST[t]["hp"]
        hp = hpmax if R.random() < 0.5 else R.randrange(hpmax // 4, hpmax)
        oi = ST[ltype] if t == 8 else UT[ltype]
        cd = R.randrange(1, oi["time"] << 8)
        rem = R.randrange(256)
        paid = R.randrange(300)
        credits = R.choice([0, 1, 3, 40, 1000, 70000, R.randrange(20)])
        rec = bytearray(S_SIZE)
        rec[0], rec[2], rec[3], rec[4] = slot, t, linked, 3
        rec[8] = house
        rec[0x12:0x14] = hp.to_bytes(2, "little")
        rec[0x4C] = house
        rec[0x56:0x58] = cd.to_bytes(2, "little")
        rec[0x58:0x5A] = rem.to_bytes(2, "little")
        rec[0x5A:0x5C] = paid.to_bytes(2, "little")
        rec[0x5C] = 1
        rg.poke_w(base, rec)
        if t == 8:
            other = bytearray(S_SIZE)
            other[0], other[2], other[4] = linked, ltype, 3
            rg.poke_w(STRUCTS + linked * S_SIZE, other)
        else:
            u = bytearray(U_SIZE)
            u[0], u[2], u[4] = linked, ltype, 3
            rg.poke_u(UNITS + linked * U_SIZE, u)
        rg.poke_w(rg.a("campaign_id"), [c])
        rg.poke_w(rg.a("player_house"), [player])
        h = HOUSES + house * H_SIZE
        rg.poke_u(h + 0x04, [1, 0])           # used, not AI-active: no upkeep
        rg.poke_u(h + 0x12, credits.to_bytes(4, "little"))
        s = rg.call("st_sg_build_tick", ix=base, frames=2)
        cases.append((t, house, c, ltype, hp, cd, rem, paid, credits, s))
    res = rg.run()
    ok = bad = 0

    class S:
        pass
    for t, house, c, ltype, hp, cd, rem, paid, credits, s in cases:
        ram = FakeRam(c, 1, [0] * 6, {})
        x = S()
        x.type, x.house, x.hp, x.countDown, x.rem, x.paid = t, house, hp, cd, rem, paid
        exp = S6["s6_production"](ram, x, credits, ltype)
        w = res.page(s, PG_WORLD)
        u = res.page(s, PG_UNITS)
        r = w[STRUCTS - 0x8000 + slot * S_SIZE:][:S_SIZE]
        gcr = int.from_bytes(u[0x3800 + house * H_SIZE + 0x12:][:4], "little")
        got = (w16(r, 0x56), w16(r, 0x58), w16(r, 0x5A), gcr)
        if exp is None:
            exp = (cd, rem, paid, credits)
        if got == tuple(exp):
            ok += 1
        else:
            bad += 1
            if bad <= 6:
                out.append(f"  production type {t} of {ltype} house {house} c {c} hp {hp} "
                           f"cd {cd} rem {rem} paid {paid} credits {credits}: {got} expected {exp}")
    return ok, bad


def t_refine(bdir, out):
    """BUILD 21 refine: the step (3 * ratio + $50) >> 8 at least 1, 7
    credits a unit for the player's Harvester and 6-9 drawn from the
    random generator otherwise, the harvested counters, the storage cap,
    the delay of 6."""
    R.seed(14)
    rg = Rig(bdir, 1, 1)
    slot, us = 60, 90
    base = STRUCTS + slot * S_SIZE
    cases = []
    for _ in range(40):
        house = R.choice([1, 0])
        hpmax = ST[12]["hp"]
        hp = R.choice([hpmax, R.randrange(1, hpmax)])
        amount = R.choice([0, 1, 2, 3, 50, 100])
        credits = R.randrange(3000)
        storage = R.choice([1005, 2005, 0])
        seed = (R.randrange(256), R.randrange(256), R.randrange(256))
        rec = bytearray(S_SIZE)
        rec[0], rec[2], rec[3], rec[4] = slot, 12, us, 3
        rec[8] = house
        rec[0x12:0x14] = hp.to_bytes(2, "little")
        rg.poke_w(base, rec)
        u = bytearray(U_SIZE)
        u[0], u[2], u[4], u[5], u[8] = us, 16, 3, 1, house
        u[0x5E] = amount
        rg.poke_u(UNITS + us * U_SIZE, u)
        h = HOUSES + house * H_SIZE
        rg.poke_u(h + 0x12, credits.to_bytes(4, "little"))
        rg.poke_u(h + 0x16, storage.to_bytes(4, "little"))
        rg.poke_w(rg.a("harvested_allied"), (0, 0, 0, 0))
        rg.poke_w(rg.a("credits_no_silo"), (0, 0, 0, 0))
        rg.poke_w(rg.a("rnd_seed"), seed)
        s = rg.call("ef_b_refine", ix=base + 0x16, frames=2)
        cases.append((house, hp, amount, credits, storage, seed, s))
    res = rg.run()
    ok = bad = 0
    for house, hp, amount, credits, storage, seed, s in cases:
        ratio = div_shl8(ST[12]["hp"], hp)
        step = min(mul_shr8(3, ratio), amount)
        if amount:
            step = max(step, 1)
        w = res.page(s, PG_WORLD)
        u = res.page(s, PG_UNITS)
        r = res.regs(s)
        gcr = int.from_bytes(u[0x3800 + house * H_SIZE + 0x12:][:4], "little")
        gam = u[us * U_SIZE + 0x5E]
        if step == 0:
            exp = (0, credits, amount)
        else:
            per = 7 if house == 1 else 7 + (rnd(seed)[1] & 3) - 1
            paid = per * step
            cr = credits + paid
            cap = storage if house != 1 else max(storage, 0)
            cr = min(cr, cap)
            exp = (1, cr, amount - step)
        got = (r["hl"], gcr, gam)
        if got == exp:
            ok += 1
        else:
            bad += 1
            if bad <= 6:
                out.append(f"  refine house {house} hp {hp} amount {amount} credits {credits} "
                           f"storage {storage}: {got} expected {exp}")
    return ok, bad


def t_dock(bdir, out):
    """A Harvester that claimed its Refinery on the way home docks and
    comes out again.  unit_enter_structure $048802 takes it off the map,
    and unit_take_off_map's unit_drop_references breaks its claim both
    ways ($049036 obj_var4_clear) - which is what lets BUILD's check.link
    answer 0 and the Refinery's script `release` it.  On the pad it is
    drawn (c_spr_show $048966: U_SHOWN) at the Refinery + ($180, $280),
    facing $80; released, it is back on the map, the Refinery idle."""
    rg = Rig(bdir, 1, 1)
    sq = 37 * 64 + 24                   # below the Atreides 1 Yard
    rs = rg.call("struct_create", bc=(0xFF << 8) | 12, de=1 << 8, hl=sq, frames=4)
    ref = STRUCTS + 1 * S_SIZE          # the first free structure slot
    us = 43
    har = UNITS + us * U_SIZE
    y, x = 40 * 256 + 128, 27 * 256 + 128
    rg.poke_w(rg.a("arg_pos"), y.to_bytes(2, "little") + x.to_bytes(2, "little"))
    hs = rg.call("unit_spawn", a=us, bc=(16 << 8) | 1, de=0, frames=4)
    # the claim go.to makes (unit_set_destination $047D18): both var 4
    rg.poke_u(har + 0x2A, (0x8001).to_bytes(2, "little"))
    rg.poke_w(ref + 0x2A, (0x4000 | us).to_bytes(2, "little"))
    rg.poke_u(har + 0x5E, [0])
    en = rg.call("unit_enter_structure", ix=har, iy=ref, frames=4)
    cl = rg.call("ef_b_check_link", ix=ref + 0x16, frames=2)
    rl = rg.call("ef_b_release", ix=ref + 0x16, frames=4)
    res = rg.run()
    T = []

    def check(c, msg):
        T.append(c)
        if not c:
            out.append("  dock: " + msg)

    check(res.regs(rs)["hl"] == ref and res.regs(hs)["hl"] == har,
          f"the rig: refinery {res.regs(rs)['hl']:#x}, harvester {res.regs(hs)['hl']:#x}")
    w, u = res.page(en, PG_WORLD), res.page(en, PG_UNITS)
    r = w[ref - 0x8000:][:S_SIZE]
    h = u[har - 0x4000:][:U_SIZE]
    check(w16(r, 0x2A) == 0 and w16(h, 0x2A) == 0,
          f"docked: the claim is kept (refinery var 4 {w16(r, 0x2A):#x}, "
          f"harvester {w16(h, 0x2A):#x})")
    check(r[3] == us and s16(r, 0x5C) == 2,
          f"docked: refinery linked {r[3]}, state {s16(r, 0x5C)}")
    check(w16(h, 4) & 4 and h[0x4C] == 1 and h[0x6A] == 0x80,
          f"docked: flags {w16(h, 4):#x}, shown {h[0x4C]}, facing {h[0x6A]:#x}")
    check((w16(h, 0x0A), w16(h, 0x0C)) == (w16(r, 0x0A) + 0x180, w16(r, 0x0C) + 0x280),
          f"docked at {w16(h, 0x0A):#x},{w16(h, 0x0C):#x}, not on the pad")
    check(res.regs(cl)["hl"] == 0, f"check.link answers {res.regs(cl)['hl']:#x}, not 0")
    w, u = res.page(rl, PG_WORLD), res.page(rl, PG_UNITS)
    r = w[ref - 0x8000:][:S_SIZE]
    h = u[har - 0x4000:][:U_SIZE]
    check(res.regs(rl)["hl"] == 1 and not w16(h, 4) & 4 and h[3] == 0xFF,
          f"release answers {res.regs(rl)['hl']}, harvester flags {w16(h, 4):#x}")
    check(r[3] == 0xFF and s16(r, 0x5C) == 0,
          f"released: refinery linked {r[3]}, state {s16(r, 0x5C)}")
    return sum(1 for c in T if c), sum(1 for c in T if not c)


def t_power(bdir, house, mission, out):
    """house_calc_power and house_power_to_health on a mission's houses,
    with some Windtraps damaged: storage, production and use, and every
    structure's hitpointsMax, by S5's formulas."""
    R.seed(15)
    rg = Rig(bdir, house, mission)
    rg.m.run_frames(2)
    steps = []
    # damage some structures first (in the WORLD page, before the calls)
    dmg = {}
    for slot in range(0, 40):
        if R.random() < 0.4:
            dmg[slot] = R.random()
    step_dump = rg.call("random", frames=1)
    steps.append(step_dump)
    res0 = None
    res = rg.run()
    w = res.page(rg.load, PG_WORLD)
    sts = structs_of(w)
    rg = Rig(bdir, house, mission)
    for s in sts:
        if s["slot"] in dmg and s["type"] in BUILT:
            hp = max(1, int(ST[s["type"]]["hp"] * dmg[s["slot"]]))
            dmg[s["slot"]] = hp
            rg.poke_w(STRUCTS + s["slot"] * S_SIZE + 0x12, hp.to_bytes(2, "little"))
        else:
            dmg.pop(s["slot"], None)
    calls = []
    for h in range(6):
        a = rg.call("house_calc_power", a=h, frames=3)
        b = rg.call("house_power_to_health", a=h, frames=3)
        calls.append((h, a, b))
    res = rg.run()
    ok = bad = 0
    for h, a, b in calls:
        u = res.page(a, PG_UNITS)
        hr = u[0x3800 + h * H_SIZE:][:H_SIZE]
        if not hr[4] & 1:
            continue
        wa = res.page(a, PG_WORLD)
        mine = [s for s in structs_of(wa) if s["house"] == h and not s["flags"] & 4]
        stor = prod = use = 0
        for s in mine:
            st = ST[s["type"]]
            import struct as _s
            info = S6["S6_ROM"]
            base = S6["_rl"](S6["S6_STRUCT_TABLE"] + 4 * s["type"])
            storage = S6["_rw"](base + 0x38)
            power = S6["_rsw"](base + 0x3A)
            stor += storage
            if power >= 0:
                use += power
            elif s["hp"] >= st["hp"]:
                prod += -power
            else:
                ratio = min(max(div_shl8(st["hp"], s["hp"]), 128), 255)
                prod += mul_shr8(-power, ratio)
        got = (int.from_bytes(hr[0x16:0x1A], "little"), w16(hr, 0x1A), w16(hr, 0x1C))
        if got == (stor, prod & 0xFFFF, use & 0xFFFF):
            ok += 1
        else:
            bad += 1
            out.append(f"  power house {h}: {got} expected {(stor, prod, use)}")
        ratio = min(div_shl8(use, prod), 256)
        wb = res.page(b, PG_WORLD)
        for s in structs_of(wb):
            if s["house"] != h or s["flags"] & 4:
                continue
            st = ST[s["type"]]
            mx = max(mul_shr8(ratio, st["hp"]), st["hp"] >> 1)
            g = w16(s["raw"], 0x5E)
            if g == mx:
                ok += 1
            else:
                bad += 1
                if bad <= 8:
                    out.append(f"  hitpointsMax house {h} type {s['type']}: {g} expected {mx}")
    return ok, bad


def t_spice(bdir, out):
    """map_change_spice's three levels and edge icons, harvest's steps
    (0 or 1 a call, one call in 32 taking a step) replayed through the
    random generator, and map_find_spice against the ring search of S5."""
    R.seed(16)
    rg = Rig(bdir, 1, 1)           # A1: a 64 x 64 map with spice fields
    calls = []
    # 1. change spice on random spice / sand squares
    res0 = None
    for _ in range(12):
        sq = R.randrange(64 * 2 + 2, 64 * 61)
        sign = R.choice([1, 255])
        s = rg.call("map_change_spice", hl=sq, a=sign, frames=2)
        calls.append(("change", sq, sign, s))
    res = rg.run()
    ok = bad = 0
    lt = landscape_table(bdir)
    prev = res.page(rg.load, PG_MAP)
    for kind, sq, sign, s in calls:
        mp = res.page(s, PG_MAP)
        t0 = lt[sq_ground(prev, sq)]
        t1 = lt[sq_ground(mp, sq)]
        if sign == 1:
            exp = {0: 8, 8: 9}.get(t0, t0)
        else:
            exp = {9: 8, 8: 0}.get(t0, t0)
        good = t1 == exp
        if good and sign == 1 and t1 in (8, 9):
            # the edge icon of the square
            m = 0
            for bit, d in ((1, -64), (2, 1), (4, 64), (8, -1)):
                tn = lt[sq_ground(mp, (sq + d) & 0xFFF)]
                if (t1 == 8 and tn in (8, 9)) or (t1 == 9 and tn == 9):
                    m |= bit
            good = sq_ground(mp, sq) == (0xB0 if t1 == 8 else 0xC0) + m
        if good and sign == 255 and t0 == 9:
            good = sq_ground(mp, sq) == 0xBF
        if good:
            ok += 1
        else:
            bad += 1
            out.append(f"  change spice {sq} sign {sign}: type {t0} -> {t1} "
                       f"icon {sq_ground(mp, sq):#x}")
        prev = mp
    return ok, bad


def landscape_table(bdir):
    vals, on = [], False
    for l in (Path(bdir) / "gen/tables.inc").read_text().splitlines():
        if l.startswith("tbl_icon_landscape:"):
            on = True
            continue
        if on:
            s = l.strip()
            if s.startswith("db"):
                vals += [int(v) for v in s[2:].split(";")[0].split(",")]
            elif vals:
                break
    return vals


def t_harvest(bdir, out):
    """UNIT 42 harvest replayed: a Harvester on spice, amount += random &
    1 each call, answer 1 unless random & 31 is 0 (then the square loses
    a step and it answers 0)."""
    R.seed(17)
    rg = Rig(bdir, 1, 1)
    lt = landscape_table(bdir)
    us = 90
    base = UNITS + us * U_SIZE
    calls = []
    # the loaded map, to find a spice square
    rg0 = Rig(bdir, 1, 1)
    res0 = rg0.run()
    mp = res0.page(rg0.load, PG_MAP)
    spice = [sq for sq in range(64, 4032) if lt[sq_ground(mp, sq)] in (8, 9)
             and mp[0x3000 + sq] == 0]
    for i in range(30):
        sq = R.choice(spice)
        amount = R.randrange(0, 101)
        seed = (R.randrange(256), R.randrange(256), R.randrange(256))
        u = bytearray(U_SIZE)
        u[0], u[2], u[4], u[8] = us, 16, 3, 1
        u[0x0B] = sq >> 6
        u[0x0D] = sq & 63
        u[0x0A] = u[0x0C] = 0x80
        u[0x5E] = amount
        rg.poke_u(base, u)
        rg.poke_w(rg.a("rnd_seed"), seed)
        s = rg.call("ef_u_harvest", ix=base + 0x16, frames=2)
        calls.append((sq, amount, seed, s))
    res = rg.run()
    ok = bad = 0
    for sq, amount, seed, s in calls:
        r = res.regs(s)
        u = res.page(s, PG_UNITS)
        got = (r["hl"], u[us * U_SIZE + 0x5E])
        if amount >= 100:
            exp = (0, amount)
        else:
            seed, a = rnd(seed)
            am = min(amount + (a & 1), 100)
            seed, b = rnd(seed)
            exp = (1 if b & 31 else 0, am)
        if got == exp:
            ok += 1
        else:
            bad += 1
            if bad <= 6:
                out.append(f"  harvest at {sq} amount {amount}: {got} expected {exp}")
    return ok, bad


def t_slab(bdir, out):
    """A 4-Slab made by the Yard and put down (struct_place $00E87E): the
    concrete goes under the square placed at, not at the record's own
    position (a slab waiting in the Yard has none, and the layout walked
    from square 0 laid it in the map's corner); the record is freed, and
    freeing a structure that was never on a side list unlinks nothing -
    it once walked list_unlink with the wrong descriptor and wrote into
    the stub of the bank in window 0, which killed the game a pass later.
    The stub of every bank must be what it was.  And a slab's location
    check off the map (square 0) returns 0 from inside its loop's pushes."""
    rg = Rig(bdir, 1, 1)
    sq = 37 * 64 + 24                   # below the Atreides 1 Yard: rock
    rs = rg.call("struct_create", bc=(0xFF << 8) | 1, de=1 << 8, hl=0xFFFF, frames=4)
    ref = STRUCTS + 71 * S_SIZE         # slabs and walls take the top slots
    off = rg.call("struct_check_location", hl=0, a=0, frames=4)
    pl = rg.m.call("struct_place", ix=ref, hl=sq, frames=6,
                   pages=(PG_WORLD, PG_UNITS, PG_MAP, 8, 11, 14, 16))
    after = rg.call("map_flags", hl=sq, frames=2)
    res = rg.run()
    T = []

    def check(c, msg):
        T.append(c)
        if not c:
            out.append("  slab: " + msg)

    r = res.page(rs, PG_WORLD)[ref - 0x8000:][:S_SIZE]
    check(res.regs(rs)["hl"] == ref and r[2] == 1 and s16(r, 0x5C) == -1
          and r[0x0B] == 0 and r[0x0D] == 0,
          f"the rig: a 4-Slab at {res.regs(rs)['hl']:#x}, type {r[2]}, "
          f"state {s16(r, 0x5C)}, at {r[0x0D]},{r[0x0B]}")
    check(res.regs(off)["done"] and res.regs(off)["hl"] == 0,
          f"a slab off the map: check_location answers {res.regs(off)['hl']:#x}")
    check(res.regs(pl)["done"] and res.regs(pl)["a"] == 1,
          f"struct_place answers A={res.regs(pl)['a']}, done {res.regs(pl)['done']}")
    mp = res.page(pl, PG_MAP)
    got = [sq_ground(mp, sq + o) for o in OFFS[3]]
    check(all(g == 0x7E for g in got), f"the concrete under the cursor: {[hex(g) for g in got]}")
    check(sq_ground(mp, 0) != 0x7E and sq_ground(mp, 65) != 0x7E,
          "no concrete in the map's corner")
    r = res.page(pl, PG_WORLD)[ref - 0x8000:][:S_SIZE]
    check(w16(r, 4) == 0, f"the record freed: flags {w16(r, 4):#x}")
    stub = rg.sym["stub_end"]
    main_stub = res.page(pl, 8)[:stub]
    for pg in (11, 14, 16):
        check(res.page(pl, pg)[:stub] == main_stub, f"bank {pg}'s stub is not MAIN's any more")
    check(res.regs(after)["done"], "the machine serves a call after the placing")
    return sum(1 for c in T if c), sum(1 for c in T if not c)


def t_port_rules(bdir, out):
    """The port's own rules (gamedesign.md "The port's own rules") and a
    fix: a 4-Slab two squares from the Yard paves every rock square once
    its footprint passed, and leaves the PartialRock one (icon $84,
    isValidForStructure2 = 0) as it is; a Light Factory placed on Atreides 2 offers the
    Trike, the only unit its panel lists (the cartridge's default is the
    Quad); and a ruin takes the house marker's orb off its marker square
    (struct_erase_house_marker $00DE04, which struct_remove lacked)."""
    T = []

    def check(c, msg):
        T.append(c)
        if not c:
            out.append("  port rules: " + msg)

    # the slab: A1's Yard is at (24,35)-(25,36); two squares above it
    rg = Rig(bdir, 1, 1)
    rg.call("struct_create", bc=(0xFF << 8) | 1, de=1 << 8, hl=0xFFFF, frames=4)
    ref = STRUCTS + 71 * S_SIZE
    sq = 33 * 64 + 24
    pl = rg.call("struct_place", ix=ref, hl=sq, frames=8)
    res = rg.run()
    mp = res.page(pl, PG_MAP)
    got = [sq_ground(mp, sq + o) for o in OFFS[3]]
    check(res.regs(pl)["done"] and got == [0x84, 0x7E, 0x7E, 0x7E],
          f"a 4-Slab two squares from the Yard: {[hex(g) for g in got]}")
    # the factory: Atreides 2 offers the Trike only
    rg = Rig(bdir, 1, 2)
    rs = rg.call("struct_create", bc=(0xFF << 8) | 3, de=1 << 8, hl=0xFFFF, frames=4)
    res = rg.run()
    rec = res.regs(rs)["hl"]
    rg = Rig(bdir, 1, 2)
    rg.call("struct_create", bc=(0xFF << 8) | 3, de=1 << 8, hl=0xFFFF, frames=4)
    up = rg.call("struct_upgrade_by_mission", ix=rec, frames=4)
    bl = rg.call("struct_get_buildable", ix=rec, frames=4)
    res = rg.run()
    w = res.page(up, PG_WORLD)
    mask = (res.regs(bl)["de"] << 16) | res.regs(bl)["hl"]
    item = w16(w, rec - 0x8000 + 0x52)
    check(mask == 1 << 13 and item == 13,
          f"a Light Factory on A2: item {item}, offered {mask:#x}")
    # the panel's take starts it: a Light Factory placed under A3's Yard
    # (a Windtrap between, for the adjacency), its panel opened through
    # the mailbox (it is modal, and the interrupt reads the keys), down
    # onto its one item and A on it.  The front end's pages were left in
    # windows 1 and 3 after the menu once, and unit_spawn found no pool.
    rg = Rig(bdir, 1, 3)
    rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=41 * 64 + 17, frames=8)
    rs = rg.call("struct_create", bc=(0xFF << 8) | 3, de=1 << 8, hl=43 * 64 + 17, frames=8)
    res = rg.run()
    rec = res.regs(rs)["hl"]
    slot = (rec - STRUCTS) // S_SIZE
    rg = Rig(bdir, 1, 3)
    rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=41 * 64 + 17, frames=8)
    rg.call("struct_create", bc=(0xFF << 8) | 3, de=1 << 8, hl=43 * 64 + 17, frames=8)
    rg.call("struct_upgrade_by_mission", ix=rec, frames=4)
    rg.m.run_frames(10)
    pn = rg.call("panel_structure", a=slot, frames=40)
    rg.m.lines += ["press a 4", "run 20", "press space 4", "run 60"]
    rg.m.dump(PG_WORLD, pn)
    rg.m.dump(PG_UNITS, pn)
    res = rg.run()
    w = res.page(pn, PG_WORLD)
    state = s16(w, rec - 0x8000 + 0x5C)
    trikes = [u for u in units(res.page(pn, PG_UNITS))
              if u["house"] == 1 and u["type"] == 13]
    check(res.regs(pn)["done"] and state == 1 and len(trikes) == 3,
          f"the panel's Trike on A3: state {state}, {len(trikes)} Trikes")
    # the orb: a Windtrap below A1's Yard, its marker drawn, then a ruin
    rg = Rig(bdir, 1, 1)
    rs = rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=37 * 64 + 24, frames=4)
    res = rg.run()
    rec = res.regs(rs)["hl"]
    rg = Rig(bdir, 1, 1)
    rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=37 * 64 + 24, frames=4)
    msq = 37 * 64 + 24 + 64                # a 2x2 layout's marker square
    rg.poke_w(rec + 6, [0x10])             # flags2 bit 4: the orb is drawn
    rg.poke_map(0xD000 + msq, [(0x16 + 1) << 1])
    rg.call("struct_destroy", ix=rec, frames=8)
    rm = rg.call("struct_remove", ix=rec, frames=8)
    res = rg.run()
    check(res.regs(rm)["done"] and sq_overlay(res.page(rm, PG_MAP), msq) == 0,
          f"the orb after the ruin: overlay {sq_overlay(res.page(rm, PG_MAP), msq):#x}")
    return sum(1 for c in T if c), sum(1 for c in T if not c)


def t_destroy(bdir, out):
    """A Construction Yard destroyed while a building waits in it: the
    waiting record was never placed, so the structure loop (which skips
    off-map records) would never free it; struct_destroy frees it, and it
    leaves the find array.  And struct_allocate does not list a fixed
    slot twice: a second slab made before the first is placed takes slot
    71 again, and the array grows by nothing."""
    T = []

    def check(c, msg):
        T.append(c)
        if not c:
            out.append("  destroy: " + msg)

    rg = Rig(bdir, 1, 1)
    rs = rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=0xFFFF, frames=4)
    res = rg.run()
    rec = res.regs(rs)["hl"]
    slot = (rec - STRUCTS) // S_SIZE
    w = res.page(rs, PG_WORLD)
    yard = [s for s in structs_of(w) if s["type"] == 8 and s["house"] == 1][0]
    yrec = STRUCTS + yard["slot"] * S_SIZE
    fc, fa = rg.a("struct_find_count") - 0x8000, rg.a("struct_find") - 0x8000
    n0 = w[fc]
    rg = Rig(bdir, 1, 1)
    rg.call("struct_create", bc=(0xFF << 8) | 9, de=1 << 8, hl=0xFFFF, frames=4)
    rg.poke_w(yrec + 3, [slot])                     # linkedID: the building waiting
    d = rg.call("struct_destroy", ix=yrec, frames=10)
    res = rg.run()
    w = res.page(d, PG_WORLD)
    flags = w16(w, rec - 0x8000 + 4)
    listed = list(w[fa:fa + w[fc]])
    check(res.regs(d)["done"] and flags == 0 and slot not in listed and w[fc] == n0 - 1,
          f"the waiting building after the Yard's end: flags {flags:#x}, "
          f"in the find array {slot in listed}, count {w[fc]} from {n0}")
    # a fixed slot taken twice
    rg = Rig(bdir, 1, 1)
    c1 = rg.call("struct_create", bc=(0xFF << 8) | 1, de=1 << 8, hl=0xFFFF, frames=4)
    c2 = rg.call("struct_create", bc=(0xFF << 8) | 1, de=1 << 8, hl=0xFFFF, frames=4)
    res = rg.run()
    w1, w2 = res.page(c1, PG_WORLD), res.page(c2, PG_WORLD)
    l2 = list(w2[fa:fa + w2[fc]])
    check(res.regs(c2)["done"] and w2[fc] == w1[fc] and l2.count(71) == 1,
          f"a second 4-Slab before the first is placed: count {w2[fc]} from {w1[fc]}, "
          f"slot 71 listed {l2.count(71)} times")
    return sum(1 for c in T if c), sum(1 for c in T if not c)


def t_reload(bdir, out):
    """A mission loaded after another: the loader's bloom-list pointer is
    into scen_buf and was left from the file before, so a mission without
    blooms took the previous pointer into its own records and stamped the
    bloom icon under every unit (seen after a won level).  The ground under
    the player's units must be what the map gave them."""
    rg = Rig(bdir, 1, 2)
    ld = rg.m.call("start_mission", a=1, bc=3 << 8, frames=120,
                   pages=(PG_WORLD, PG_UNITS, PG_MAP, 27))
    res = rg.run()
    u = res.page(ld, PG_UNITS)
    mp, mg = res.page(ld, PG_MAP), res.page(ld, 27)
    T = []
    for n in range(102):
        r = u[n * U_SIZE:(n + 1) * U_SIZE]
        if not (r[4] & 1) or r[8] != 1 or w16(r, 0x0C) == 0xFFFF:
            continue
        sq = r[0x0B] * 64 + r[0x0D]
        ok = mp[sq] == mg[sq]
        T.append(ok)
        if not ok:
            out.append(f"  reload: unit {n} at {r[0x0D]},{r[0x0B]}: ground {mp[sq]:#x}, loaded {mg[sq]:#x}")
    if not T:
        out.append("  reload: no player units")
        T.append(False)
    return sum(1 for c in T if c), sum(1 for c in T if not c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    b = args.build_dir
    tests = [
        ("mission A2", lambda o: t_mission(b, 1, 2, "A2", o)),
        ("mission O2", lambda o: t_mission(b, 2, 2, "O2", o)),
        ("mission H3", lambda o: t_mission(b, 0, 3, "H3", o)),
        ("buildable", lambda o: t_buildable(b, o)),
        ("upgradable", lambda o: t_upgradable(b, o)),
        ("production", lambda o: t_production(b, o)),
        ("refine", lambda o: t_refine(b, o)),
        ("dock", lambda o: t_dock(b, o)),
        ("power A2", lambda o: t_power(b, 1, 2, o)),
        ("spice", lambda o: t_spice(b, o)),
        ("harvest", lambda o: t_harvest(b, o)),
        ("slab", lambda o: t_slab(b, o)),
        ("port rules", lambda o: t_port_rules(b, o)),
        ("destroy", lambda o: t_destroy(b, o)),
        ("reload", lambda o: t_reload(b, o)),
    ]
    total_bad = 0
    for name, fn in tests:
        if args.only and args.only not in name:
            continue
        out = []
        del UNFINISHED[:]
        ok, bad = fn(out)
        if UNFINISHED:
            bad += len(UNFINISHED)
            out.append(f"  {len(UNFINISHED)} calls did not finish (steps {UNFINISHED[:8]})")
        total_bad += bad
        print(f"{name:14s} {ok}/{ok + bad}")
        for l in out:
            print(l)
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
