"""S9 - a mission from start to end: its scenarios for sega_spec_check.py.

Loaded by sega_spec_check.py into its own namespace (see
load_spec_modules there), so `scenario`, `state`, `_run`, `Ram`, `Check`,
`ROOT` and the rest are used here without importing.

A mission is checked where it has just been loaded: the password path
(the title's password screen, the word, the mentat's briefing) is played
to the briefing and saved; the scenario then presses through the briefing
and takes the last RAM dump before the battle's frame hook goes in -
loaded, prepared, and not yet played.  Everything the mission file says
is compared with what the loader put in RAM.  The win is played from the
Atreides/Ordos/Harkonnen mission 1 with SPLURGEOLA: the level-end
decisions are predicted from RAM, and the score screen is read out of
VRAM and compared with the score the spec says it shows.
"""

import collections as _collections
import sys as _sys
import tempfile as _tempfile
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import sega_scen as _scen  # noqa: E402
import sega_touch as _touch  # noqa: E402

_ROM = ROM.read_bytes()                      # noqa: F821 (the checker's)
_BATTLE_HOOKS = (0x608E, 0x6D0C)
_UNIT, _STRUCT, _HOUSE = 0xFF1000, 0xFF4EB8, 0xFF4D10
_REINF = 0xFFC0A2
_OFFSET = {0: 0, 1: 1040}                    # $0714A0 by MapScale
_HOUSE_ORDER = [0, 1, 2, 4, 3]               # house_allocate, $01617C-$0161A4
_KIND_HOUSE = {0: 0, 1: 1, 2: 2}             # password kind -> house


def _w(a):
    return int.from_bytes(_ROM[a:a + 2], "big")


def _l(a):
    return int.from_bytes(_ROM[a:a + 4], "big")


def _unit_type(t):
    return _l(0x06C5B4 + 4 * t)


def _counted(t):
    """unit_create's cap rule: $02056E[type] and not a winger (S2)."""
    return _ROM[0x02056E + t] != 0 and _w(_unit_type(t) + 0x3E) != 4


def _mission(house, mission):
    """The records of SCEN<letter><nnn>.INI, and the file's name."""
    name = f"SCEN{'HAO'[house]}{mission:03d}.INI"
    for line in (ROOT / "orig/sega/res/data/files.txt").read_text() \
            .splitlines():                                  # noqa: F821
        p = line.split()
        if p and p[0] == name:
            a, n = int(p[1][1:], 16), int(p[2])
            recs, ok = _scen.parse(_ROM[a:a + n])
            by = _collections.defaultdict(list)
            for sec, key, v in recs:
                by[sec].append((key, v))
            by["order"] = recs
            return name, by
    raise KeyError(name)


def _passwords():
    return {w: (k, v) for w, k, v in _touch.password_table(_ROM)}


def _s9_state(name, lines):
    """A save state of its own, built once into tmp/sega/spec/."""
    dst = WORK / f"s9-{name}.state"                         # noqa: F821
    if not dst.exists():
        WORK.mkdir(parents=True, exist_ok=True)             # noqa: F821
        _run(list(lines) + [f"save {dst}"])                 # noqa: F821
    return dst


def _play(st, plan):
    """Load `st` and play `plan`: script lines, and ('dump', vram) for a
    dump of RAM (and VRAM if asked).  Answers the dumps in order."""
    with _tempfile.TemporaryDirectory() as d:
        lines, n = [f"load {st}"], 0
        for p in plan:
            if isinstance(p, tuple):
                lines.append(f"ram {d}/{n}.bin")
                if p[1]:
                    lines.append(f"vram {d}/{n}.v")
                n += 1
            else:
                lines.append(p)
        _run(lines)                                        # noqa: F821
        out = []
        for i in range(n):
            r = Ram((_Path(d) / f"{i}.bin").read_bytes())  # noqa: F821
            v = _Path(d) / f"{i}.v"
            if v.exists():
                b = bytearray(v.read_bytes())
                b[0::2], b[1::2] = b[1::2], b[0::2]
                r.vram = bytes(b)
            out.append(r)
        return out


def _loaded(dumps, after=0):
    """The last dump with no frame hook before the battle's goes in: the
    mission read and prepared, and not a pass played."""
    for i in range(max(after, 1), len(dumps)):
        if dumps[i].l(HOOK) in _BATTLE_HOOKS and \
                dumps[i - 1].l(HOOK) == 0:                  # noqa: F821
            return dumps[i - 1]
    return None


def _check_load(c, r, house, mission, bonus, early_ok=False):
    """Everything a mission file puts into RAM, against the file."""
    name, by = _mission(house, mission)
    tag = f"{name}:"
    head = dict(by[0])
    off = _OFFSET[head.get(4, 0)]
    c.that(r.w(0xFFC274) == house, f"{tag} player house {r.w(0xFFC274)}")
    c.that(r.w(0xFFC04C) == mission and r.w(0xFFC050) == mission - 1,
           f"{tag} mission {r.w(0xFFC04C)}/{r.w(0xFFC050)}")
    # the scenario block $FFC05C-$FFC141: cleared, then filled
    c.that(r.w(0xFFC05C) == 683, f"{tag} $FFC05C is {r.w(0xFFC05C)}")
    for a in (0xFFC05E, 0xFFC096, 0xFFC098, 0xFFC09A, 0xFFC09C, 0xFFC09E,
              0xFFC0A0):
        c.that(r.w(a) == 0, f"{tag} ${a:06X} not cleared: {r.w(a)}")
    c.that(r.w(0xFFC060) == head.get(8, 0),
           f"{tag} winFlags {r.w(0xFFC060)} != key 8 {head.get(8)}")
    c.that(r.w(0xFFC062) == head.get(7, 0),
           f"{tag} loseFlags {r.w(0xFFC062)} != key 7 {head.get(7)}")
    seed = dict(by[1]).get(0x53)
    c.that(r.l(0xFFC064) == seed, f"{tag} seed {r.l(0xFFC064)} != {seed}")
    c.that(r.w(0xFFC068) == head.get(4, 0), f"{tag} map scale")
    c.that(r.w(0xFFC06A) == head.get(3, 0), f"{tag} timeout")
    for key, a in ((2, 0xFFC06C), (1, 0xFFC07A), (0, 0xFFC088)):
        s = r.mem[a - RAM:a - RAM + 14].split(b"\0")[0].decode("latin1")  # noqa
        c.that(s == head.get(key), f"{tag} picture {key} {s!r}")
    # CursorPos and TacticalPos, moved by the map scale's offset; the
    # seed's handler ($016554) then puts the tactical view 4 columns left
    # of and 3 rows above the cursor, so a TacticalPos read before the
    # seed is lost
    cursor = tactical = None
    for sec, key, v in by["order"]:
        if sec == 0 and key == 5:
            cursor = v + off
        elif sec == 0 and key == 6:
            tactical = v + off
        elif sec == 1 and key == 0x53:
            tactical = ((cursor & 0x3F) - 4) | ((cursor & 0xFC0) - 0xC0)
    c.that(r.w(0xFFC244) == cursor and r.w(0xFFC248) == cursor,
           f"{tag} cursor {r.w(0xFFC244)} != {cursor}")
    c.that(r.w(0xFFC238) == tactical and r.w(0xFFC23C) == tactical,
           f"{tag} tactical {r.w(0xFFC238)} != {tactical}")

    # the houses: 0 1 2 4 3 allocated, the unit-less freed, one skipped
    # after each free (house_free closes the gap the walk stands on)
    # units and reinforcements are made in file order, each in the lowest
    # free slot of its type's range (+$34-+$36, S2); one with no slot
    # left is not made
    taken_slots, units, reinf = set(), [], {}
    for sec, key, v in by["order"]:
        if sec not in (8, 10):
            continue
        t = v[1]
        lo, hi = _w(_unit_type(t) + 0x34), _w(_unit_type(t) + 0x36)
        free = [k for k in range(lo, hi + 1) if k not in taken_slots]
        if not free:
            continue
        taken_slots.add(free[0])
        if sec == 8:
            units.append(v)
        else:
            reinf[key] = v
    count = _collections.Counter()
    for v in units + [(h, t) for h, t, _, _ in reinf.values()]:
        if _counted(v[1]):
            count[v[0]] += 1
    order, i = list(_HOUSE_ORDER), 0
    while i < len(order):
        if count[order[i]] == 0:
            order.pop(i)
            i += 1                         # the house that slid in is passed
        else:
            i += 1
    used = [(r.l(0xFFDC0C + 4 * k) - _HOUSE) // 0x46
            for k in range(r.w(0xFFDC08))]
    c.that(used == order, f"{tag} houses in use {used}, expected {order}")
    player = None
    for sec in (2, 3, 4, 5):
        if not by[sec]:
            continue
        h = _scen.SECTION_HOUSE[sec]
        f = {k: v for k, v in by[sec]}
        b = _HOUSE + 0x46 * h
        human = f.get(0x42) == 0x48
        cred = f.get(0x43, 0) + (bonus if human else 0)
        if human:
            player = h
            # the password path's extra credit may or may not have been
            # given by the time the hook goes in
            c.that(r.l(b + 0x12) in (cred - bonus, cred),
                   f"{tag} player credits {r.l(b + 0x12)} != {cred}")
            c.that(r.l(0xFFC054) == r.l(b + 0x12), f"{tag} creditsNoSilo")
            c.that(r.l(0xFFC278) == b, f"{tag} $FFC278")
        else:
            c.that(r.l(b + 0x12) in (cred, min(cred, r.l(b + 0x16))),
                   f"{tag} house {h} credits {r.l(b + 0x12)} != {cred}")
        c.that(bool(r.w(b + 4) & 2) == human, f"{tag} house {h} human bit")
        c.that(r.w(b + 8) == f.get(0x4D, 0), f"{tag} house {h} max units")
        c.that(r.w(b + 0x20) == f.get(0x51, 0), f"{tag} house {h} quota")
    c.that(player == house, f"{tag} Brain=H is house {player}")

    # the units: the file's, on their squares, and the reinforcements'
    # waiting off the map
    have = _collections.Counter()
    waiting = _collections.defaultdict(list)
    for k in range(102):
        b = _UNIT + 0x8C * k
        if not r.w(b + 4) & 1:
            continue
        t, h = r.u(b + 2, 1), r.u(b + 8, 1)
        if r.w(b + 4) & 4:
            waiting[(h, t)].append(k)
            continue
        have[(h, t, r.l(b + 0xA), r.u(b + 0x6A, 1), r.u(b + 0x54, 1),
              r.w(b + 0x12))] += 1
    want = _collections.Counter()
    for h, t, hp, sq, face, act in units:
        s = sq + off
        pos = ((((s & 0xFC0) << 10) + (s & 63)) << 8) + 0x800080
        want[(h, t, pos, face, act,
              (_w(_unit_type(t) + 0x10) * hp) >> 8)] += 1
    c.that(have == want, f"{tag} units differ: extra {have - want}, "
           f"missing {want - have}")

    # the structures: ID records only, top-left of the square, full health
    have = _collections.Counter()
    for k in range(73):
        b = _STRUCT + 0x62 * k
        if r.w(b + 4) & 1:
            have[(r.u(b + 2, 1), r.u(b + 8, 1), r.l(b + 0xA),
                  r.w(b + 0x12), r.w(b + 0x5C))] += 1
    want = _collections.Counter()
    refineries = _collections.Counter()
    taken = set()
    for key, v in by[9]:
        if key == 0x47:
            continue
        idx, h, t, hp, sq = v
        s = sq + off
        if s in taken:
            continue
        taken.add(s)
        want[(t, h, ((s >> 6) << 24) | ((s & 63) << 8),
              _w(_l(0x06B94C + 4 * t) + 0x10), 0)] += 1
        refineries[h] += t == 12
    c.that(have == want, f"{tag} structures differ: extra {have - want}, "
           f"missing {want - have}")
    for h in range(5):
        b = _HOUSE + 0x46 * h
        if h in order:
            n = refineries[h] - (1 if h < 3 and refineries[h] else 0)
            c.that(r.w(b + 2) == n, f"{tag} house {h} harvestersIncoming "
                   f"{r.w(b + 2)} != {n}")

    # the reinforcements
    # the record's key is its slot: the file counts from 1, so slot 0 is
    # never used
    for k in range(16):
        b = _REINF + 10 * k
        got = [r.w(b + 2 * j) for j in range(5)]
        if k not in reinf:
            c.that(got[0] == 0xFFFF, f"{tag} reinforcement {k} not empty")
            continue
        h, t, where, when = reinf[k]
        t0 = (when >> 8) * 6 + 1
        c.that(got[0] in waiting[(h, t)], f"{tag} reinforcement {k} unit "
               f"{got[0]} is not a waiting {h}/{t}")
        c.that(got[1:] == [where, t0, t0, int(when & 0xFF == 0x2B)] or
               got[1:] == [where, t0 - 1, t0, int(when & 0xFF == 0x2B)],
               f"{tag} reinforcement {k}: {got[1:]} (delay {when >> 8})")
    # CHOAM
    stock = {key: v for key, v in by[6]}
    for t in range(28):
        c.that(r.s(0xFFC2A0 + 2 * t, 2) == stock.get(t, -1),
               f"{tag} starport stock {t}: {r.s(0xFFC2A0 + 2 * t, 2)}")
    # the blooms: the tile number becomes $FFC228's
    mp = _l(0x04AA1C)
    for key, v in by[1]:
        if key == 0x42:
            for sq in v:
                a = mp + 4 * (sq + off)
                c.that(r.w(a) & 0x1FF == r.w(0xFFC228) & 0x1FF,
                       f"{tag} bloom at {sq} not marked")
    # the prepared state
    c.that(r.l(0xFFC5A4) == r.l(CLOCK), f"{tag} missionStartTime")  # noqa
    # game_prepare sets it; a snapshot taken between scen_load and
    # game_prepare (dumps 10 frames apart) still has the last mission's
    if r.l(0xFFC150) >= r.l(0xFFC5A4) or not early_ok:
        c.that(r.l(0xFFC150) == r.l(CLOCK) + 70, f"{tag} power start")  # noqa
    c.that(r.w(0xFFDBEC) == 1 and r.w(0xFFDBEE) == 1,
           f"{tag} structure counts not 1/1")
    # credits shown: game_prepare's $FFFF is replaced at once by the
    # counter's reset (ui_draw_credits mode 2), which rolls up from 0
    c.that(r.l(0xFFC058) <= r.l(r.l(0xFFC278) + 0x12),
           f"{tag} credits shown {r.l(0xFFC058)}")
    return by


_LOAD_WORDS = ["DEMOLITION", "SPICEDANCE", "ARRAKISSUN", "EVILMENTAT",
               "SONICBLAST", "POWERCRUSH"]


def _brief(word):
    return _s9_state("brief-" + word, _touch.PASSWORD +
                     _touch.type_password(word) + ["run 300"])


def _through_briefing(n=600):
    plan = []
    for i in range(n):
        if i % 40 == 0:
            plan.append("press mdc 6")
        plan += ["run 3", ("dump", False)]
    return plan


@scenario("S9", "a password's mission is in RAM as its file says")  # noqa
def s9_load(c):
    pw = _passwords()
    for word in _LOAD_WORDS:
        kind, mission = pw[word]
        d = _play(_brief(word), _through_briefing())
        r = _loaded(d)
        c.that(r is not None, f"{word}: never reached the battle")
        if r is not None:
            # the password path gives the player one credit
            # (game_battle_loop $012528) before the first pass
            _check_load(c, r, _KIND_HOUSE[kind], mission, 1)


@scenario("S9", "a mission's labels read the PC way round do not fit (control)")  # noqa
def s9_flags_control(c):
    """sega_scen.py calls key 7 WinFlags and key 8 LoseFlags.  The code
    that reads $FFC060/$FFC062 says it is the other way: key 8 is what
    GameLoop_IsLevelFinished reads and key 7 what GameLoop_IsLevelWon
    reads.  The file order proves nothing, so this only checks the
    stored words against the keys: with the keys swapped they misfit."""
    miss = 0
    for word in _LOAD_WORDS[:3]:
        kind, mission = _passwords()[word]
        r = _loaded(_play(_brief(word), _through_briefing()))
        head = dict(_mission(_KIND_HOUSE[kind], mission)[1][0])
        miss += r.w(0xFFC060) != head.get(7, 0)
    c.that(miss > 0, "swapped keys fit as well")


def _finished(r):
    """game_is_level_finished $0229B4, from RAM."""
    done = r.w(0xFFDBEE) == 0 or (r.w(0xFFDBEC) == 0 and r.w(0xFFC050))
    if r.w(0xFFC060) & 4 and r.l(0xFFC058) != 0xFFFF:
        quota = r.w(r.l(0xFFC278) + 0x20)
        done = done or quota <= r.l(0xFFC058)
    return bool(done)


def _won(r):
    """game_is_level_won $022A28, from RAM."""
    f = r.w(0xFFC062)
    won = False
    if f & 3:
        won = r.w(0xFFDBEE) != 0 and (r.w(0xFFC050) == 0 or
                                     r.w(0xFFDBEC) == 0)
    if f & 4 and not won and r.l(0xFFC058) != 0xFFFF:
        won = r.w(r.l(0xFFC278) + 0x20) <= r.l(0xFFC058)
    if f & 8:
        won = won and r.l(CLOCK) < r.l(0xFFC144)            # noqa: F821
    return bool(won)


def _pc_finished(r):
    """The PC's GameLoop_IsLevelFinished: nothing before 7200 ticks."""
    if r.l(CLOCK) - r.l(0xFFC5A4) < 7200:                  # noqa: F821
        return False
    return _finished(r)


def _win_run(kind):
    """Mission 1 of house `kind`, SPLURGEOLA typed, then played on: per
    frame through the battle, then every 10 frames with VRAM, pressing C
    now and then, through the victory, the score and the next briefing."""
    plan = _touch.in_game("SPLURGEOLA")
    assert plan[-1] == "run 200"          # the battle is back from here
    plan = plan[:-1]
    plan += [x for _ in range(1500) for x in ("run 1", ("dump", False))]
    for i in range(1500):
        if i % 30 == 29:
            plan.append("press mdc 6")
        plan += ["run 10", ("dump", True)]
    return _play(state(f"m1-{kind}"), plan)               # noqa: F821


_RUNS = {}


def _win(kind):
    if kind not in _RUNS:
        _RUNS[kind] = _win_run(kind)
    return _RUNS[kind]


def _level_end_checks(d):
    """(before, after, finished) for each level-end check seen: a check
    that said "not yet" moves tickLevelEnd; one that said "over" sets
    $FFBE9C first (tickLevelEnd moves only when the screens are done)."""
    out = []
    for a, b in zip(d, d[1:]):
        if b.u(0xFFBE9C, 1) and not a.u(0xFFBE9C, 1) and \
                a.l(HOOK) in _BATTLE_HOOKS:                 # noqa: F821
            out.append((a, b, True))
        elif b.l(0xFFDC28) != a.l(0xFFDC28) and not b.u(0xFFBE9C, 1):
            out.append((a, b, False))
    return out


@scenario("S9", "the level-end decision is the one the spec predicts from RAM")  # noqa
def s9_decision(c):
    for kind in (0, 1, 2):
        d = _win(kind)
        checks = _level_end_checks(d)
        c.that(any(f for _, _, f in checks), f"m1-{kind}: never finished")
        for a, b, f in checks:
            c.that(f in (_finished(a), _finished(b)),
                   f"m1-{kind}: check at {b.l(CLOCK)} said {f}")  # noqa
            if f:
                won = _won(a) or _won(b)
                after = [x for x in d if x.w(0xFFC050) != a.w(0xFFC050)]
                c.that(bool(after) == won and
                       (not after or after[0].w(0xFFC050) ==
                        a.w(0xFFC050) + 1),
                       f"m1-{kind}: won {won}, campaign went "
                       f"{a.w(0xFFC050)} -> "
                       f"{after[0].w(0xFFC050) if after else '-'}")


@scenario("S9", "with the PC's 7200-tick minimum the finish is not predicted (control)")  # noqa
def s9_decision_control(c):
    miss = 0
    for kind in (0, 1, 2):
        for a, b, f in _level_end_checks(_win(kind)):
            miss += f not in (_pc_finished(a), _pc_finished(b))
    c.that(miss > 0, "the PC's rule fits too")


def _screen(r):
    """The score page out of VRAM: score, hours, minutes, rank."""
    def digits(a, n):
        v, seen = 0, False
        for i in range(n):
            t = int.from_bytes(r.vram[a + 2 * i:a + 2 * i + 2], "big")
            if 0x4530 <= t <= 0x4539:
                v, seen = v * 10 + t - 0x4530, True
        return v if seen else None
    rank = bytes((int.from_bytes(r.vram[0xF198 + 2 * i:0xF19A + 2 * i],
                                 "big") - 0x4500) & 0xFF for i in range(17))
    return (digits(0xEF92, 5), digits(0xEFBC, 2), digits(0xEFC2, 2),
            rank.decode("latin1"))


def _rank(score, won, mission):
    if won and mission == 9:
        i = 8
    else:
        i = 0
        while score >= _w(0x0A68CA + 2 * i):
            i += 1
    return _ROM[0x0A68DA + 17 * i:0x0A68DA + 17 * i + 17].decode("latin1")


def _score_page(d):
    for r in d:
        if hasattr(r, "vram") and r.l(HOOK) == 0:           # noqa: F821
            s = _screen(r)
            if s[0] is not None and s[2] is not None and \
                    s[3].strip() and s[3].isprintable():
                return r, s
    return None, None


@scenario("S9", "the score page shows the battle's score, time and rank")  # noqa
def s9_score(c):
    for kind in (0, 1, 2):
        d = _win(kind)
        fin = next(a for a, b, f in _level_end_checks(d) if f)
        r, s = _score_page(d)
        c.that(r is not None, f"m1-{kind}: no score page")
        if r is None:
            continue
        score = fin.w(0xFFC05E)
        c.that(r.w(0xFFC05E) == score, f"m1-{kind}: score moved after the "
               f"finish: {score} -> {r.w(0xFFC05E)}")
        ticks = r.l(CLOCK) - r.l(0xFFC5A4)                  # noqa: F821
        hours, minutes = ticks // 3000 // 60, ticks % 180000 // 3000
        c.that(s[0] == score, f"m1-{kind}: page says {s[0]}, "
               f"the spec {score}")
        c.that((s[1] or 0, s[2]) == (hours, minutes),
               f"m1-{kind}: time {s[1]}:{s[2]} for {ticks} ticks")
        c.that(s[3] == _rank(score, True, 1),
               f"m1-{kind}: rank {s[3]!r}")


@scenario("S9", "the PC's Update_Score (credits / 100 and more) does not fit (control)")  # noqa
def s9_score_control(c):
    miss = 0
    for kind in (0, 1, 2):
        d = _win(kind)
        r, s = _score_page(d)
        if r is None:
            continue
        pc = r.w(0xFFC05E) + r.l(r.l(0xFFC278) + 0x12) // 100
        miss += s[0] != pc
    c.that(miss > 0, "the PC's score fits too")


@scenario("S9", "after a win the next mission loads as its file says")  # noqa
def s9_next(c):
    for kind in (0, 1, 2):
        d = _win(kind)
        fin = next(i for i, (a, b) in enumerate(zip(d, d[1:]))
                   if b.u(0xFFBE9C, 1) and not a.u(0xFFBE9C, 1))
        r = _loaded(d, fin + 1)
        c.that(r is not None, f"m1-{kind}: the next mission never loaded")
        if r is not None:
            house = r.w(0xFFC274)
            c.that(house == kind, f"m1-{kind}: house {house}")
            # loaded from the battle loop: no credit is given this time
            _check_load(c, r, house, 2, 0, early_ok=True)
