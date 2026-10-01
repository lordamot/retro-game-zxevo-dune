#!/usr/bin/env python3
"""test_house.py - the HOUSE subsystem on the machine, against the specs.

    python3 tools/tests/test_house.py [--build-dir build] [--keep DIR]

One evo-run: Harkonnen mission 4 (SCENH004 - Ordos with a Refinery and
teams, four Sardaukar reinforcements that repeat) is loaded through
start_mission, and then the harness calls the HOUSE routines on it and
compares what they leave in RAM with models written from the specs:

  timers       S1: the house timers' next-due arithmetic over a run of clocks
               (fires at or after due; set to that pass's clock + period;
               power upkeep only after load + 70 and strictly past due)
  location     S8: map_find_location kinds 0-5 replayed with the
               cartridge's random generator; kinds 6/7 checked for their
               rules (near the right house's structure, playable, empty)
  harvester    S5/S6: house_ensure_harvester for the Ordos (a Refinery, no
               Harvester): a Carryall of theirs with a Harvester aboard
  seen         S7: unit_seen_by_house - the Ordos woken by the player's
               sight of their Ambush unit: counts, isAIActive both ways,
               the stagger 16, 32, 48 ..., the warning timer, Hunt
  teams        S1/S7: team_tick's 5 + (random & 7), and the inert teams
               going to Staging (members 0 < min)
  reinforce    S1/S9: the reinforcements arriving on the firing the model
               predicts, one Carryall for the four, the repeats made
  level end    S9: won when the enemy structures are gone (the next
               mission, rank, hours and minutes), lost (score / 10), the
               quota, and "not yet" moving tickLevelEnd by 300
"""
import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dune_test import Machine, units, structures, w16, s16   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PG_UNITS, PG_WORLD, PG_MAP = 24, 25, 26
HOUSES, TEAMS = 0x3800, 0x3A00
H_SIZE, T_SIZE, U_SIZE, S_SIZE = 0x46, 0x54, 0x8C, 0x62


# ------------------------------------------------------------ the models
def rnd(seed):
    """math_random $000E42 (as tools/tests/test_core.py)."""
    s1, s2, s3 = seed
    d0 = s3 >> 2
    x = (s3 >> 1) & 1
    ns1 = ((s1 << 1) | x) & 255
    x = s1 >> 7
    ns2 = ((s2 << 1) | x) & 255
    x = s2 >> 7
    x ^= 1
    d0 = (d0 - s3 - x) & 255
    x = d0 & 1
    ns3 = (s3 >> 1) | (x << 7)
    return (ns1, ns2, ns3), ns3 ^ ns2


def rand_between(seed, lo, hi):
    seed, d0 = rnd(seed)
    d3 = (hi - lo + 1) & 255
    d1 = 0xFF
    while True:
        if d3 > d0:
            break
        d1 >>= 1
        d0 &= d1
        if d0 == 0:
            break
    return seed, (d0 + lo) & 255


PERIODS = [("tick_house_house", 900), ("tick_house_power", 10800),
           ("tick_house_starport", 60), ("tick_house_reinf", 600),
           ("tick_house_unused", 5), ("tick_house_missile", 60),
           ("tick_house_avail", 1800)]


def timers_model(due, clock, start):
    """S1: one house pass at `clock`: the new due times."""
    out = dict(due)
    for name, period in PERIODS:
        if name == "tick_house_power":
            fire = clock >= start + 70 and clock > due[name]
        else:
            fire = clock >= due[name]
        if fire:
            out[name] = clock + period
    return out


def level_rank(score, won9):
    if won9:
        return 8
    i = 0
    for t in (50, 100, 150, 200, 250, 300, 400, 0xFFFF):
        if score >= t:
            i += 1
        else:
            break
    return i


class Page:
    def __init__(self, sym, world, units_pg=None, map_pg=None):
        self.sym, self.w, self.u, self.m = sym, world, units_pg, map_pg

    def wb(self, label, n=1, off=0):
        a = self.sym[label] - 0x8000 + off
        return int.from_bytes(self.w[a:a + n], "little")

    def house(self, h):
        o = HOUSES + h * H_SIZE
        return self.u[o:o + H_SIZE]

    def team(self, t):
        o = TEAMS + t * T_SIZE
        return self.u[o:o + T_SIZE]

    def unit(self, n):
        o = n * U_SIZE
        return self.u[o:o + U_SIZE]

    def struct(self, n):
        o = self.sym["structs"] - 0x8000 + n * S_SIZE
        return self.w[o:o + S_SIZE]

    def taken(self, sq):
        f = self.m[0x2000 + sq]
        return bool(f & 0x30) and self.m[0x3000 + sq] != 0


def valid(sq, scale=0):
    x0, y0, w, h = ((1, 1, 62, 62), (16, 16, 32, 32))[scale]
    x, y = sq & 63, sq >> 6
    return x0 <= x < x0 + w and y0 <= y < y0 + h


def find_location_model(seed, kind, page, tactical=0):
    """map_find_location kinds 0-5 (S8, the port's edges) on a 64 x 64
    map: (seed after, square)."""
    x0, y0, w, h = 1, 1, 62, 62
    while True:
        if kind == 0:
            seed, c = rand_between(seed, 1, w)
            sq = y0 * 64 + c + x0 - 1
        elif kind == 1:
            seed, r = rand_between(seed, 1, h)
            sq = (r + y0 - 1) * 64 + x0 + w - 1
        elif kind == 2:
            seed, c = rand_between(seed, 1, w)
            sq = (y0 + h - 1) * 64 + c + x0 - 1
        elif kind == 3:
            seed, r = rand_between(seed, 1, h)
            sq = (r + y0 - 1) * 64 + x0
        elif kind == 4:
            while True:
                seed, c = rand_between(seed, 1, w)
                seed, r = rand_between(seed, 1, h)
                sq = (r * 64 + c) & 0xFFF
                if valid(sq):
                    break
        else:
            while True:
                seed, c = rand_between(seed, 0, 6)
                seed, r = rand_between(seed, 0, 4)
                sq = (((tactical >> 6) & 63) + r) * 64 + (tactical & 63) + c
                sq &= 0xFFF
                if valid(sq):
                    break
        sq &= 0xFFF
        if sq and not page.taken(sq):
            return seed, sq


def tdp(a, b):
    """tile_distance_packed."""
    dx = abs((a & 63) - (b & 63))
    dy = abs(((a >> 6) & 63) - ((b >> 6) & 63))
    return max(dx, dy) + min(dx, dy) // 2


# -------------------------------------------------------------- the test
class Checks:
    def __init__(self):
        self.n = {}
        self.bad = {}

    def that(self, group, ok, msg):
        self.n[group] = self.n.get(group, 0) + 1
        if not ok:
            self.bad[group] = self.bad.get(group, 0) + 1
            if self.bad[group] <= 6:
                print(f"  {group}: {msg}")

    def report(self):
        for g in self.n:
            print(f"{g:12s} {self.n[g] - self.bad.get(g, 0)}/{self.n[g]}")
        return not self.bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--keep")
    args = ap.parse_args()
    m = Machine(build_dir=args.build_dir)
    sym = m.sym
    ALL = (PG_UNITS, PG_WORLD, PG_MAP)

    def poke32(label, v):
        m.poke_page(PG_WORLD, sym[label] - 0x8000, (v & 0xFFFFFFFF).to_bytes(4, "little"))

    def pokew(label, v, off=0):
        m.poke_page(PG_WORLD, sym[label] - 0x8000 + off, (v & 0xFFFF).to_bytes(2, "little"))

    def pokeb(label, v, off=0):
        m.poke_page(PG_WORLD, sym[label] - 0x8000 + off, bytes([v & 255]))

    steps = {}
    # the mission: Harkonnen 4
    steps["load"] = m.call("start_mission", a=0, bc=4 << 8, frames=400, pages=ALL)

    # --- the timers: all due at 0, then a run of clocks
    for name, _ in PERIODS:
        poke32(name, 0)
    poke32("mission_start_time", 1000)
    clocks = [1000, 1004, 1060, 1064, 1072, 1120, 1200, 1604, 1900, 1904,
              2804, 3000, 11800, 11871, 11872, 11900, 22700, 22750]
    steps["timers"] = []
    for c in clocks:
        poke32("timer_game", c)
        steps["timers"].append((c, m.call("game_loop_house", frames=25, pages=ALL)))

    # --- map_find_location, kinds 0-7
    steps["loc"] = []
    for kind, house in [(0, 0), (1, 0), (2, 0), (3, 0), (0, 2), (4, 0), (5, 0),
                        (7, 0), (6, 2), (7, 2), (6, 0), (3, 2), (1, 2)]:
        steps["loc"].append((kind, house, m.call("map_find_location", a=kind,
                                                  bc=house << 8, frames=10,
                                                  pages=ALL)))

    # --- house_ensure_harvester for the Ordos (2)
    steps["harv"] = m.call("house_ensure_harvester", a=2, frames=20, pages=ALL)

    # --- the level end, "not yet": tickLevelEnd moves by 300
    poke32("tick_level_end", 0)
    poke32("timer_game", 40000)
    steps["le_notyet"] = m.call("game_check_level_end", frames=4, pages=ALL)

    m_res = m.run(keep=args.keep and Path(args.keep) / "a")
    c = Checks()
    p0 = Page(sym, m_res.page(steps["load"], PG_WORLD),
              m_res.page(steps["load"], PG_UNITS), m_res.page(steps["load"], PG_MAP))
    c.that("load", m_res.regs(steps["load"])["done"], "start_mission did not finish")
    c.that("load", p0.wb("scenario_id") == 4 and p0.wb("player_house") == 0,
           f"mission {p0.wb('scenario_id')} house {p0.wb('player_house')}")

    # timers
    due = {n: 0 for n, _ in PERIODS}
    for clock, s in steps["timers"]:
        r = m_res.regs(s)
        pg = Page(sym, m_res.page(s, PG_WORLD))
        due = timers_model(due, clock, 1000)
        got = {n: pg.wb(n, 4) for n, _ in PERIODS}
        c.that("timers", r["done"], f"clock {clock}: the call did not finish")
        for n, _ in PERIODS:
            c.that("timers", got[n] == due[n], f"clock {clock}: {n} {got[n]} != {due[n]}")

    # map_find_location
    prev = None
    for kind, house, s in steps["loc"]:
        r = m_res.regs(s)
        before = Page(sym, m_res.page(s - 1, PG_WORLD), m_res.page(s - 1, PG_UNITS),
                      m_res.page(s - 1, PG_MAP))
        seed = tuple(before.w[sym["rnd_seed"] - 0x8000 + i] for i in range(3))
        sq = r["hl"]
        after = Page(sym, m_res.page(s, PG_WORLD))
        seed_after = tuple(after.w[sym["rnd_seed"] - 0x8000 + i] for i in range(3))
        if kind <= 5:
            ms, msq = find_location_model(seed, kind, before, before.wb("tactical_pos", 2))
            c.that("location", (msq, ms) == (sq, seed_after),
                   f"kind {kind}: {sq:#x} {seed_after} != model {msq:#x} {ms}")
        else:
            # near a structure of the house (7) or of one not allied (6)
            ok = sq != 0 and valid(sq) and not before.taken(sq)
            near = False
            for st in structures(before.w):
                if st["type"] in (0, 1, 14):
                    continue
                if kind == 7 and st["house"] != house:
                    continue
                if kind == 6 and not (st["house"] != house and
                                      not allied(st["house"], house, 0)):
                    continue
                ssq = (st["y"] >> 8) * 64 + (st["x"] >> 8)
                near |= tdp(ssq, sq) <= 7
            c.that("location", ok and near, f"kind {kind} house {house}: {sq:#x}")

    # house_ensure_harvester
    s = steps["harv"]
    pg = Page(sym, m_res.page(s, PG_WORLD), m_res.page(s, PG_UNITS))
    new = [u for u in units(pg.u) if u["house"] == 2 and u["type"] == 0]
    c.that("harvester", m_res.regs(s)["a"] == 1, "did not answer 1")
    c.that("harvester", len(new) == 1, f"{len(new)} Ordos Carryalls")
    if new:
        cy = pg.unit(new[0]["slot"])
        cargo = cy[3]
        c.that("harvester", cargo != 0xFF, "the Carryall carries nothing")
        if cargo != 0xFF:
            hv = pg.unit(cargo)
            c.that("harvester", hv[2] == 16 and hv[8] == 2 and hv[0x5E] == 1 and hv[4] & 4,
                   f"cargo type {hv[2]} house {hv[8]} amount {hv[0x5E]} flags {hv[4]:#x}")
        c.that("harvester", cy[5] & 1, "the Carryall is not inTransport")
        c.that("harvester", cy[5] & 2, "the Carryall is not byScenario")
        ref = w16(cy, 0x5C)
        refinery = [st for st in structures(pg.w) if st["house"] == 2 and st["type"] == 12]
        c.that("harvester", refinery and ref == 0x8000 | refinery[0]["slot"],
               f"targetMove {ref:#x}")
        # it came in from an edge: row or column 1 or 62
        y, x = cy[0x0B], cy[0x0D]
        c.that("harvester", y in (1, 62) or x in (1, 62), f"arrived at {y},{x}")

    # level end, not yet
    s = steps["le_notyet"]
    pg = Page(sym, m_res.page(s, PG_WORLD))
    c.that("level end", m_res.regs(s)["a"] == 1 and pg.wb("level_result") == 0,
           "not over: answered 0 or set a result")
    c.that("level end", pg.wb("tick_level_end", 4) == 40300,
           f"tickLevelEnd {pg.wb('tick_level_end', 4)}")

    ok = second_run(args, c)
    sys.exit(0 if c.report() and ok else 1)


SIDE = [-1, 0, -1, 1, -1, -1]


def allied(a, b, player):
    if a == b:
        return True
    s = SIDE[a] + SIDE[b]
    if s > 0:
        return True
    if s == 0:
        return False
    return a != player and b != player


def second_run(args, c):
    """The AI waking, the teams, the reinforcements and the end, from a
    fresh load of the same mission."""
    m = Machine(build_dir=args.build_dir)
    sym = m.sym
    ALL = (PG_UNITS, PG_WORLD, PG_MAP)

    def poke_w(label, v, n=2, off=0):
        m.poke_page(PG_WORLD, sym[label] - 0x8000 + off,
                    (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little"))

    load = m.call("start_mission", a=0, bc=4 << 8, frames=400, pages=ALL)
    res0 = m.run(keep=args.keep and Path(args.keep) / "b0")
    u0 = res0.page(load, PG_UNITS)
    w0 = res0.page(load, PG_WORLD)
    amb = [u for u in units(u0) if u["house"] == 2 and u["order"] == 8]
    c.that("seen", bool(amb), "no Ordos Ambush unit in SCENH004")
    if not amb:
        return False
    a = amb[0]["slot"]
    ordos_structs = [st["slot"] for st in structures(w0)
                     if st["house"] == 2 and st["type"] != 12]

    # the same machine again (one run each is simplest: the load is
    # deterministic)
    m = Machine(build_dir=args.build_dir)
    m.call("start_mission", a=0, bc=4 << 8, frames=400, pages=ALL)
    s_seen = m.call("unit_seen_by_house", a=0, ix=0x4000 + a * U_SIZE, frames=5, pages=ALL)
    # the teams: the clock, the timer, one instruction a tick
    poke_w("tick_team", 0, 4)
    team_steps = []
    clock = 5000
    for i in range(24):
        poke_w("timer_game", clock, 4)
        team_steps.append((clock, m.call("team_tick", frames=6, pages=ALL)))
        clock += 13
    # the reinforcements: all four due in three firings
    reinf = sym["reinforcements"] - 0x8000
    for k in range(4):
        m.poke_page(PG_WORLD, reinf + 10 * k + 4, (3).to_bytes(2, "little"))
    poke_w("tick_house_reinf", 0, 4)
    poke_w("mission_start_time", 0, 4)
    rsteps = []
    for clock in (60000, 60300, 60600, 61200):
        poke_w("timer_game", clock, 4)
        rsteps.append((clock, m.call("game_loop_house", frames=40, pages=ALL)))
    # the end: won (structs_other 0 after the enemy's structures are gone)
    for n in ordos_structs:
        m.poke_page(PG_WORLD, sym["structs"] - 0x8000 + n * S_SIZE + 4, bytes([0]))
    poke_w("structs_other", 0, 1)
    poke_w("score", 260)
    poke_w("mission_start_time", 1000, 4)
    ticks = 3 * 180000 + 7 * 3000 + 5
    poke_w("timer_game", 1000 + ticks, 4)
    poke_w("tick_level_end", 0, 4)
    s_won = m.call("game_check_level_end", frames=5, pages=ALL)
    res = m.run(keep=args.keep and Path(args.keep) / "b")

    # --- seen
    w = res.page(s_seen, PG_WORLD)
    u = res.page(s_seen, PG_UNITS)
    pg = Page(sym, w, u)
    hk, od = pg.house(0), pg.house(2)
    c.that("seen", res.regs(s_seen)["done"], "unit_seen_by_house did not finish")
    c.that("seen", hk[4] & 8 and od[4] & 8, f"isAIActive: player {hk[4]:#x} Ordos {od[4]:#x}")
    c.that("seen", w16(hk, 0x0A) == 1 and w16(hk, 0x0C) == 0,
           f"player's counts enemy {w16(hk, 0x0A)} allied {w16(hk, 0x0C)}")
    c.that("seen", w16(hk, 0x28) == 8, f"timerUnitAttack {w16(hk, 0x28)}")
    un = pg.unit(a)
    c.that("seen", un[0x54] == 11, f"the Ambush unit's order {un[0x54]}")
    c.that("seen", un[9] & 1, f"seenByHouses {un[9]:#x}")
    want = 16
    for n in range(73):
        st = pg.struct(n)
        if st[8] == 2 and st[2] != 12 and n in ordos_structs:
            c.that("seen", w16(st, 0x14) == want, f"structure {n} delay {w16(st, 0x14)} != {want}")
            want += 16
        elif st[4] & 1 and st[8] != 2:
            c.that("seen", w16(st, 0x14) == w16(Page(sym, w0).struct(n), 0x14),
                   f"structure {n} of house {st[8]} staggered")

    # --- the teams
    due = 0
    for clock, s in team_steps:
        before = Page(sym, res.page(s - 1, PG_WORLD))
        after = Page(sym, res.page(s, PG_WORLD))
        seed = tuple(before.w[sym["rnd_seed"] - 0x8000 + i] for i in range(3))
        if clock >= due:
            seed, r = rnd(seed)
            due = clock + 5 + (r & 7)
        c.that("teams", after.wb("tick_team", 4) == due,
               f"clock {clock}: tick_team {after.wb('tick_team', 4)} != {due}")
    last = Page(sym, res.page(team_steps[-1][1], PG_WORLD), res.page(team_steps[-1][1], PG_UNITS))
    teams = [last.team(t) for t in range(16) if last.team(t)[2]]
    c.that("teams", len(teams) == 5, f"{len(teams)} teams")
    staged = [t for t in teams if w16(t, 0x0C) == 1]
    c.that("teams", len(staged) == len(teams),
           f"behaviours {[w16(t, 0x0C) for t in teams]} (all should be Staging, 1)")
    c.that("teams", all(w16(t, 4) == 0 for t in teams), "a team has members")

    # --- the reinforcements
    fired = 0
    prev_units = units(res.page(rsteps[0][1] - 1, PG_UNITS))
    for i, (clock, s) in enumerate(rsteps):
        pg = Page(sym, res.page(s, PG_WORLD), res.page(s, PG_UNITS), res.page(s, PG_MAP))
        recs = [pg.w[reinf + 10 * k:reinf + 10 * k + 10] for k in range(4)]
        # the model: the timer fires at 60000 (due 0), 60600, 61200; not at 60300
        fires = clock in (60000, 60600, 61200)
        fired += fires
        left = max(0, 3 - fired)
        if fired < 3:
            c.that("reinforce", all(w16(r, 4) == left for r in recs),
                   f"clock {clock}: time left {[w16(r, 4) for r in recs]} != {left}")
        else:
            cys = [u for u in units(pg.u) if u["type"] == 0 and u["house"] == 4]
            if clock == 60600 + 600 * 0 and fired == 3:
                pass
            c.that("reinforce", len(cys) == 1, f"clock {clock}: {len(cys)} Sardaukar Carryalls")
            if cys:
                cy = pg.unit(cys[0]["slot"])
                chain, n = [], cy[3]
                while n != 0xFF and len(chain) < 10:
                    chain.append(n)
                    n = pg.unit(n)[3]
                c.that("reinforce", len(chain) == 4 and all(pg.unit(x)[2] == 3 for x in chain),
                       f"the Carryall carries {chain}")
                sq = (cy[0x5D] << 8 | cy[0x5C])
                tsq = (sq >> 8 & 63) * 64 + ((sq & 0xFF) >> 1 & 63)
                yard = [st for st in structures(pg.w) if st["house"] == 0]
                c.that("reinforce", (sq & 0xC000) == 0xC000 and yard and any(
                    tdp((st["y"] >> 8) * 64 + (st["x"] >> 8), tsq) <= 7 for st in yard),
                    f"the Carryall goes to {sq:#x}")
            # the repeats: new units, 37 to go again
            c.that("reinforce", all(r[0] != 0xFF and w16(r, 4) == 37 for r in recs),
                   f"repeats {[(r[0], w16(r, 4)) for r in recs]}")
            break

    # --- the end: won
    pg = Page(sym, res.page(s_won, PG_WORLD), res.page(s_won, PG_UNITS))
    c.that("level end", res.regs(s_won)["a"] == 0 and pg.wb("level_result") == 1,
           f"won: A {res.regs(s_won)['a']} level_result {pg.wb('level_result')}")
    c.that("level end", pg.wb("campaign_id") == 4 and pg.wb("scenario_id") == 5 and
           pg.wb("score_mission") == 4 and pg.wb("level_over") == 1,
           f"campaign {pg.wb('campaign_id')} scenario {pg.wb('scenario_id')}")
    c.that("level end", pg.wb("score_rank") == level_rank(260, False) == 5,
           f"rank {pg.wb('score_rank')}")
    c.that("level end", (pg.wb("score_hours", 2), pg.wb("score_minutes", 2)) == (3, 7),
           f"time {pg.wb('score_hours', 2)}:{pg.wb('score_minutes', 2)}")
    c.that("level end", not (pg.house(0)[4] & 4), "doneFullScaleAttack not cleared")

    return third_run(args, c)


def third_run(args, c):
    """Lost, and a quota won, from fresh loads."""
    m = Machine(build_dir=args.build_dir)
    sym = m.sym
    ALL = (PG_UNITS, PG_WORLD, PG_MAP)

    def poke_w(label, v, n=2):
        m.poke_page(PG_WORLD, sym[label] - 0x8000, (v & ((1 << (8 * n)) - 1)).to_bytes(n, "little"))

    m.call("start_mission", a=0, bc=4 << 8, frames=400, pages=ALL)
    cases = []
    for score, expect in ((125, 12), (-35, 0), (9, 0)):
        poke_w("structs_player", 0, 1)
        poke_w("structs_other", 3, 1)
        poke_w("score", score)
        poke_w("level_result", 0, 1)
        poke_w("tick_level_end", 0, 4)
        poke_w("timer_game", 90000, 4)
        cases.append(("lost", score, expect, m.call("game_check_level_end", frames=5, pages=ALL)))
    # a quota: winFlags bit 2 ends it, loseFlags bit 2 wins it, when the
    # counter shows the quota; the counter at $FFFF never does
    for shown, over in ((4999, False), (5000, True), (0xFFFF, False)):
        poke_w("structs_player", 1, 1)
        poke_w("structs_other", 1, 1)
        poke_w("win_flags", 4, 1)
        poke_w("lose_flags", 4, 1)
        poke_w("campaign_id", 3, 1)
        poke_w("level_result", 0, 1)
        m.poke_page(PG_UNITS, HOUSES + 0x20, (5000).to_bytes(2, "little"))
        poke_w("credits_shown", shown, 4)
        poke_w("tick_level_end", 0, 4)
        poke_w("timer_game", 95000, 4)
        cases.append(("quota", shown, over, m.call("game_check_level_end", frames=5, pages=ALL)))
    res = m.run(keep=args.keep and Path(args.keep) / "c")
    for kind, v, expect, s in cases:
        pg = Page(sym, res.page(s, PG_WORLD))
        r = res.regs(s)
        if kind == "lost":
            c.that("level end", r["a"] == 0 and pg.wb("level_result") == 2 and
                   s16(pg.w, sym["score"] - 0x8000) == expect and pg.wb("campaign_id") == 3,
                   f"lost with {v}: result {pg.wb('level_result')} score "
                   f"{s16(pg.w, sym['score'] - 0x8000)} campaign {pg.wb('campaign_id')}")
        else:
            c.that("level end", (r["a"] == 0) == expect and
                   pg.wb("level_result") == (1 if expect else 0),
                   f"quota shown {v}: A {r['a']} result {pg.wb('level_result')}")
    return True


if __name__ == "__main__":
    main()
