"""spec_s6.py - the tests of orig/sega/spec/S6-production.md.

Loaded by sega_spec_check.py into its own namespace, so `scenario`,
`frames`, `Check`, `ROM` and the S1 constants are used here unimported.

The model below is the spec's, written as Python: the structure build
tick (struct_game_loop $00BEC0-$00C556), what a factory may build
(struct_get_buildable $00FE58) and the computer's choice
(struct_ai_pick_next_build $0234FC).  The tests run the cartridge frame
by frame and compare every structure the tick touched with what the
model says it should now hold.
"""

S6_ROM = ROM.read_bytes()

S6_STRUCT_TABLE = 0x06B94C      # 19 pointers to the $66-byte records
S6_UNIT_TABLE = 0x06C5B4        # 27 pointers to the $5C-byte records
S6_TICK_BUILD = 0xFFD5A0        # tickStructureStructure (S1)
S6_FIND_COUNT, S6_FIND = 0xFFD318, 0xFFD31C
S6_HOUSES = 0xFFDC24            # pointer to six $46-byte records
S6_CAMPAIGN, S6_PLAYER = 0xFFC050, 0xFFC274
S6_TYPE_COUNT = 0x04A9F2        # per house: pointer to a byte per structure type
S6_UNIT_LIST = 0xFFC620         # the 27-byte "what this factory offers" list


def _rw(a):
    return int.from_bytes(S6_ROM[a:a + 2], "big")


def _rl(a):
    return int.from_bytes(S6_ROM[a:a + 4], "big")


def _rsw(a):
    v = _rw(a)
    return v - 0x10000 if v & 0x8000 else v


def s6_stype(t):
    """A structure type's record, as a dict of the fields S6 uses."""
    b = _rl(S6_STRUCT_TABLE + 4 * t)
    return {"flags": _rw(b + 0x0C), "hp": _rw(b + 0x10), "credits": _rw(b + 0x16),
            "time": _rw(b + 0x18), "campaign": _rw(b + 0x1A),
            "required": _rl(b + 0x1C), "upgradeLevel": S6_ROM[b + 0x21],
            "house": S6_ROM[b + 0x32], "priorityBuild": _rw(b + 0x2E),
            "units": [_rsw(b + 0x4C + 2 * i) for i in range(10)],
            "upgradeCampaign": [_rw(b + 0x60 + 2 * i) for i in range(3)]}


def s6_utype(t):
    b = _rl(S6_UNIT_TABLE + 4 * t)
    return {"credits": _rw(b + 0x16), "time": _rw(b + 0x18),
            "required": _rl(b + 0x1C), "upgradeLevel": S6_ROM[b + 0x21],
            "house": S6_ROM[b + 0x32], "priorityBuild": _rw(b + 0x2E)}


S6_ST = [s6_stype(t) for t in range(19)]
S6_UT = [s6_utype(t) for t in range(27)]


# ---------------------------------------------------------- arithmetic

def s6_mul_shr8(a, b):
    """math_mul_shr8 $0199D8: (a*b + $50) >> 8, saturated at $FFFF."""
    return min((((a & 0xFFFF) * (b & 0xFFFF)) + 0x50) >> 8, 0xFFFF)


def s6_div_shl8(a, b):
    """math_div_shl8 $0199F6: b*256/a, both halved (rounding up) until
    b*256 fits in 16 bits; a divisor of 0 answers $FFFF."""
    d1, d0 = a & 0xFFFF, (b & 0xFFFF) << 8
    while d0 > 0xFFFF:
        d0 = (d0 + 1) >> 1
        d1 = ((d1 + 1) & 0xFFFF) >> 1
    if d1 == 0:
        return 0xFFFF
    return (d0 // d1) & 0xFFFF


# ---------------------------------------------------------- RAM views

def s6_structs(r):
    """(address, index) of every structure in use, in find order."""
    return [r.l(S6_FIND + 4 * i) for i in range(r.w(S6_FIND_COUNT))]


def s6_house(r, h):
    return r.l(S6_HOUSES) + 0x46 * h


def s6_type_count(r, h, t):
    return r.u(_rl(S6_TYPE_COUNT + 4 * h) + t, 1)


class S6Struct:
    def __init__(self, r, a):
        self.a = a
        self.type = r.u(a + 2, 1)
        self.link = r.u(a + 3, 1)
        self.flags = r.w(a + 4)
        self.flags2 = r.w(a + 6)
        self.house = r.u(a + 8, 1)
        self.hp = r.w(a + 0x12)
        self.creator = r.w(a + 0x4C)
        self.obj = r.s(a + 0x52, 2)
        self.level = r.u(a + 0x54, 1)
        self.upgradeLeft = r.u(a + 0x55, 1)
        self.countDown = r.w(a + 0x56)
        self.rem = r.w(a + 0x58)
        self.paid = r.w(a + 0x5A)
        self.state = r.s(a + 0x5C, 2)


# ---------------------------------------------------------- the model

def s6_buildable(r, s):
    """struct_get_buildable $00FE58 for structure s: the bitmask, and the
    27 bytes it leaves at $FFC620 for a unit factory (None otherwise)."""
    c = r.w(S6_CAMPAIGN)
    player = r.w(S6_PLAYER)
    built = r.l(s6_house(r, s.house) + 0x0E)
    m = 0
    t = s.type
    if t == 8:                                    # Construction Yard, $00FEC8
        for i in range(19):
            st = S6_ST[i]
            avail, req = st["campaign"], st["required"]
            if i == 7 and s.house == 0 and c >= 1:
                req &= ~(1 << 10)
                avail = 2
            if (built & req) != req and s.house == player:
                continue
            if s.house != 0 and i == 3:
                avail = 2
            if i in (4, 6) or (i == 7 and player == 2):
                continue
            if c < avail - 1:
                continue
            if not st["house"] & (1 << s.house):
                continue
            if st["upgradeLevel"] <= s.level or s.house != player:
                m |= 1 << i
        m |= 1 << 1
        if s.flags2 & 0x100:
            return m & 0x4002, None
        if m & 0x804:
            if s6_type_count(r, s.house, 2):
                m &= ~(1 << 2)
            if s6_type_count(r, s.house, 11):
                m &= ~(1 << 11)
        return m, None
    if t == 11:
        return 0xFFFFFFFF, None
    if t in (3, 4):                               # $01001A / $0100D6
        if t == 4:
            if 3 <= c <= 8:
                if c >= 6:
                    m |= 1 << 10
                    if built & (1 << 5):
                        cr = s.creator
                        if cr == 0:
                            m |= 1 << 11
                        elif cr == 1:
                            m |= 1 << 12
                        elif cr == 2:
                            m |= 1 << 8
                        elif cr == 4:
                            if player == 0:
                                m |= 1 << 12
                            elif player == 1:
                                m |= 1 << 11
                            elif player == 2:
                                m |= (1 << 12) | (1 << 11)
                if c >= 5 and s.level >= 3:
                    m |= 1 << 10
                if c >= 4 and s.level >= 2 and s.creator != 2:
                    m |= 1 << 7
                if s.level >= 1:
                    m |= 1 << 17
                m |= (1 << 16) | (1 << 9)
            m |= 1 << 15
        if 1 <= c <= 8:
            if c >= 2 and s.level >= 1:
                m |= 1 << 15
            if s.creator in (1, 4):
                m |= 1 << 13
            elif s.creator == 2:
                m |= 1 << 14
        if not built & 0x40000:
            m &= 0xFFFDF97F
    elif t == 5:                                  # $010170
        if 4 <= c <= 8:
            if c >= 6 and s.level:
                m |= 1 << 1
            m |= 1
    elif t in (7, 10):                            # $0101D0, the PC's own path
        # $0101D0: the list is written by position in the type's +$4C
        # list of units, not by unit type
        lst = [0] * 27
        for pos, u in enumerate(S6_ST[t]["units"]):
            if u == -1:
                continue
            if u == 13 and s.creator == 2:
                u = 14
            ut = S6_UT[u]
            need = ut["upgradeLevel"]
            if (built & ut["required"]) != ut["required"]:
                continue
            if not ut["house"] & (1 << s.creator):
                continue
            if s.house == 2:
                if t == 10 and u == 5:
                    need = 9
                elif t == 7 and u == 2:
                    need = 0
            if need <= s.level:
                lst[pos] = 1
                m |= 1 << u
            elif s.upgradeLeft and need <= s.level + 1:
                lst[pos] = 0xFF
        return m, lst
    else:
        return 0, None
    lst = [1 if m & (1 << i) else 0xFF for i in range(27)]
    return m, lst


def s6_ai_candidates(r, s):
    """What struct_ai_pick_next_build $0234FC chooses among."""
    m, _ = s6_buildable(r, s)
    if s.type == 5:
        # $023542: a Carryall of the house anywhere takes the Carryall off
        for i in range(r.w(0xFFDCBC)):
            u = r.l(0xFFDCC0 + 4 * i)
            if r.u(u + 2, 1) == 0 and r.u(u + 8, 1) == s.house:
                m &= ~1
                break
    if s.type == 4:
        m &= 0xFFFCFFFF
    return m


def s6_ai_pick_md(m, rolls):
    """The Mega Drive rule, given the rolls each candidate gets in
    order: the first whose roll is 0 mod 4 is taken at once
    ($0235AA); otherwise the highest priorityBuild, the first of
    equals ($0235C8)."""
    best = -1
    for i in range(32):
        if not m & (1 << i):
            continue
        if next(rolls) & 3 == 0:
            return i
        if best == -1 or (i < 27 and S6_UT[i]["priorityBuild"] > S6_UT[best]["priorityBuild"]):
            best = i
    return best


def s6_production(r, s, credits, linked_type, pc_rounding=False, no_cap=False):
    """The production step, $00C13C-$00C2DE, for a structure that
    passes its conditions.  `linked_type` is the unit or structure
    being made.  Returns (countDown, rem, paid, credits)."""
    st = S6_ST[s.type]
    player = r.w(S6_PLAYER)
    c = r.w(S6_CAMPAIGN)
    oi = S6_ST[linked_type] if s.type == 8 else S6_UT[linked_type]
    speed = 0x100 if s.hp == st["hp"] else s6_div_shl8(st["hp"], s.hp)
    if s.house != player and not no_cap:
        cap = c * 20 + 0x5F
        if speed >= cap:
            speed = cap
    cost = s6_div_shl8(oi["time"], oi["credits"])
    if speed != 0x100:
        cost = (speed * cost) >> 8 if pc_rounding else s6_mul_shr8(cost, speed)
    if s.type == 13:
        cost = max(cost >> 2, 1)
    cost = (cost + s.rem) & 0xFFFF
    pay = cost >> 8
    if credits and pay >= credits:
        pay = credits & 0xFFFF
    if pay > credits:
        return None
    rem = cost & 0xFF
    credits -= pay
    paid = (s.paid + pay) & 0xFFFF
    cd = 0 if speed > s.countDown else s.countDown - speed
    if cd == 0:
        rem = 0
    return cd, rem, paid, credits


def s6_linked_type(r, s):
    if s.type == 8:
        return r.u(_rl(0x04A716 + 4 * s.link) + 2, 1) if s.link < 73 else None
    u = _rl(0x04A852 + 4 * s.link)
    return r.u(u + 2, 1)


def _s6_tick_frames(d):
    return [i for i, (a, b) in enumerate(zip(d, d[1:]))
            if a.l(S6_TICK_BUILD) != b.l(S6_TICK_BUILD)]


def _s6_check_production(c, d, pc_rounding=False, no_cap=False):
    """Every build tick: each structure in production must hold, after
    the tick, the countDown, remainder and paid total the model gives,
    and its house the credits (when nothing else moved them)."""
    stats = {"production": 0, "credits": 0, "misses": 0}
    for i in _s6_tick_frames(d):
        a, b = d[i], d[i + 1]
        # a pass may run past the frame's end (S1): then use the next dump
        after = [b]
        if i + 2 < len(d):
            after.append(d[i + 2])
        houses = {}
        ok_all = True
        for addr in s6_structs(a):
            s = S6Struct(a, addr)
            st = S6_ST[s.type]
            if (s.flags & 0x4000 or s.flags2 & 0x1000 or s.flags2 & 2 or
                    s.flags & 0x2000 or s.countDown == 0 or s.link == 0xFF or
                    s.state != 1 or not st["flags"] & 2):
                continue
            lt = s6_linked_type(a, s)
            h = s.house
            cr = houses.get(h, a.l(s6_house(a, h) + 0x12))
            got = s6_production(a, s, cr, lt, pc_rounding, no_cap)
            if got is None:
                continue
            cd, rem, paid, cr = got
            houses[h] = cr
            fits = False
            for x in after:
                t = S6Struct(x, addr)
                if cd == 0:
                    if t.countDown == 0:
                        fits = True
                elif (t.countDown, t.rem, t.paid) == (cd, rem, paid):
                    fits = True
                if fits:
                    break
            stats["production"] += 1
            if not fits:
                ok_all = False
                stats["misses"] += 1
            c.that(fits, f"frame {i}: structure {s.a:06X} type {s.type} "
                   f"making {lt}: model cd {cd} rem {rem} paid {paid}, "
                   f"machine cd {S6Struct(b, addr).countDown} rem "
                   f"{S6Struct(b, addr).rem} paid {S6Struct(b, addr).paid}")
        # credits: only for a house with no Harvester in a Refinery, no
        # unit in a Repair Facility and nothing repairing or upgrading
        for h, cr in houses.items():
            quiet = True
            for addr in s6_structs(a):
                s = S6Struct(a, addr)
                if s.house == h and ((s.type in (12, 13) and s.link != 0xFF)
                                     or s.flags & 0x2000 or s.flags2 & 2):
                    quiet = False
            if not quiet or not ok_all:
                continue
            got = [x.l(s6_house(x, h) + 0x12) for x in after]
            stats["credits"] += 1
            c.that(cr in got, f"frame {i}: house {h} credits {got[0]}, model {cr}")
    return stats


S6_PRODUCTION_STATES = ["fz-000321", "fz-001380", "pw-DOMINATION", "win-DEFTHUNTER"]


@scenario("S6", "a factory's countDown, remainder, paid and credits each build tick")
def s6_production_tick(c):
    total = 0
    for name in S6_PRODUCTION_STATES:
        d = frames(name, 2500)
        st = _s6_check_production(c, d)
        total += st["production"]
    c.that(total > 50, f"only {total} production steps seen")


@scenario("S6", "without the computer's speed cap the production does not fit (control)")
def s6_production_control(c):
    misses = 0
    for name in S6_PRODUCTION_STATES[:2]:
        d = frames(name, 2500)
        inner = Check()
        st = _s6_check_production(inner, d, no_cap=True)
        misses += st["misses"]
    c.that(misses > 0, "the uncapped model fits too; the test cannot tell them apart")
    c.misses = misses


def _s6_picks(d):
    """(frame, structure, chosen type) for every computer factory that
    started a build: linked went from $FF to something, countDown was 0."""
    out = []
    for i, (a, b) in enumerate(zip(d, d[1:])):
        for addr in s6_structs(a):
            s, t = S6Struct(a, addr), S6Struct(b, addr)
            if s.type != t.type or s.house != t.house:
                continue
            if s.house == a.w(S6_PLAYER):
                continue
            if s.link == 0xFF and t.link != 0xFF and t.countDown:
                out.append((i, s, t.obj))
    return out


S6_SEED = 0xFFE017               # math_random's three bytes, $FFE017-$FFE019


def s6_random(seed):
    """math_random $000E42, instruction for instruction: (s1, s2, s3) ->
    (value, new seed).  s3 at $FFE019 is the PC's seed[0]."""
    s1, s2, s3 = seed
    d0 = s3 >> 2
    x = (s3 >> 1) & 1                 # lsr.b #2 leaves bit 1 in X
    n1 = ((s1 << 1) | x) & 0xFF       # roxl.b #1
    x = s1 >> 7
    n2 = ((s2 << 1) | x) & 0xFF       # roxl.b #1
    x = (s2 >> 7) ^ 1                 # eori.b #$11,ccr flips X
    d0 = (d0 - s3 - x) & 0x1FF        # subx.b
    d0 &= 0xFF
    x = d0 & 1                        # lsr.b #1
    n3 = ((x << 7) | (s3 >> 1)) & 0xFF   # roxr.b #1
    return n3 ^ n2, (n1, n2, n3)


def s6_seed(r):
    return (r.u(S6_SEED, 1), r.u(S6_SEED + 1, 1), r.u(S6_SEED + 2, 1))


def _s6_rolls(seed):
    while True:
        v, seed = s6_random(seed)
        yield v


def s6_ai_pick_pc(m, rolls):
    """The PC rule (OpenDUNE Structure_AI_PickNextToBuild): a roll only
    makes i the current choice, and a later candidate with a higher
    priorityBuild still replaces it."""
    best = -1
    for i in range(32):
        if not m & (1 << i):
            continue
        if next(rolls) & 3 == 0:
            best = i
        if best != -1 and i < 27 and best < 27 and \
                S6_UT[i]["priorityBuild"] <= S6_UT[best]["priorityBuild"]:
            continue
        best = i
    return best


def _s6_reachable(a, b, m, pick):
    """Every choice `pick` could make from some point in the random
    sequence between the two dumps: (choices, n) where n is how many
    numbers the frame drew, or (None, None) if the seed after is not
    reached within 20000 draws."""
    s0, s1 = s6_seed(a), s6_seed(b)
    seeds, s, n = [s0], s0, 0
    while s != s1:
        _, s = s6_random(s)
        seeds.append(s)
        n += 1
        if n > 20000:
            return None, None
    out = set()
    for k in range(n):
        g = _s6_rolls(seeds[k])
        used = [0]

        def counted():
            for v in g:
                used[0] += 1
                yield v
        choice = pick(m, counted())
        if k + used[0] <= n:
            out.add(choice)
    return out, n


S6_PICK_STATES = ["win-DEFTHUNTER", "pw-DOMINATION", "fz-001380"]


@scenario("S6", "a computer factory's choice is among what $00FE58 allows")
def s6_ai_choice(c):
    seen = 0
    c.pc_misses = 0
    for name in S6_PICK_STATES:
        d = frames(name, 6000)
        picks = _s6_picks(d)
        for i, s, chose in picks:
            a, b = d[i], d[i + 1]
            m = s6_ai_candidates(a, s)
            seen += 1
            c.that(m & (1 << chose), f"{name} frame {i}: type {s.type} chose "
                   f"{chose}, not in {m:#x}")
            # the list is the last get_buildable's: only this pick's if no
            # factory after it in find order also asked this tick
            _, lst = s6_buildable(a, s)
            order = [x.a for x in _s6_idle_ai_factories(a)]
            if lst is not None and s.a in order and order[-1] == s.a:
                ram = [b.u(S6_UNIT_LIST + k, 1) for k in range(27)]
                c.that(ram == lst, f"{name} frame {i}: $FFC620 {ram} model {lst}")
            # the random numbers the frame drew: some window of them must
            # give this choice under the Mega Drive rule
            # A frame can end between the draws and the write of the link
            # (unit_spawn is long): then the draws are in the frame before.
            first = a
            md, n = _s6_reachable(a, b, m, s6_ai_pick_md)
            if (md is None or chose not in md) and i > 0:
                first = d[i - 1]
                md, n = _s6_reachable(first, b, m, s6_ai_pick_md)
            c.that(md is not None, f"{name} frame {i}: seed after not reached")
            if md is None:
                continue
            c.that(chose in md, f"{name} frame {i}: chose {chose}, the rule "
                   f"reaches only {sorted(md)} in {n} draws")
            pc, _ = _s6_reachable(first, b, m, s6_ai_pick_pc)
            if chose not in pc:
                c.pc_misses += 1
    c.that(seen >= 10, f"only {seen} computer builds started")


@scenario("S6", "the PC's choice rule cannot give some of the choices made (control)")
def s6_ai_choice_control(c):
    inner = Check()
    s6_ai_choice(inner)
    c.that(inner.pc_misses > 0, "every choice also fits the PC's rule")


S6_UNCOUNTED = {0, 1, 18, 19, 20, 21, 22, 23, 24, 26}   # aircraft, projectiles, Frigate (S2)


def _s6_idle_ai_factories(a):
    """The computer factories that reach the pick at $00C53C this tick,
    in find order: AI active, allocated, credits, at least half health,
    a factory, nothing in hand."""
    out = []
    for addr in s6_structs(a):
        s = S6Struct(a, addr)
        h = s6_house(a, s.house)
        st = S6_ST[s.type]
        if (s.house == a.w(S6_PLAYER) or not a.w(h + 4) & 8 or
                not s.flags & 2 or not a.l(h + 0x12) or
                not st["flags"] & 2 or s.countDown or s.link != 0xFF or
                s.hp * 2 < st["hp"] or s.flags & 0x2000 or s.flags2 & 2):
            continue
        out.append(s)
    return out


@scenario("S6", "every idle computer factory starts something on the build tick")
def s6_ai_idle(c):
    for name in S6_PRODUCTION_STATES:
        d = frames(name, 2500)
        for i in _s6_tick_frames(d):
            a, b = d[i], d[i + 1]
            count = {}
            for s in _s6_idle_ai_factories(a):
                if s.type in (8, 11) or not s6_ai_candidates(a, s):
                    continue
                h = s6_house(a, s.house)
                n = count.get(s.house, a.w(h + 6))
                t = S6Struct(b, s.a)
                late = S6Struct(d[i + 2], s.a) if i + 2 < len(d) else t
                started = t.link != 0xFF or late.link != 0xFF
                if n >= a.w(h + 8):
                    # at its cap: unit_spawn refuses and nothing starts (S2)
                    c.that(not started, f"{name} frame {i}: factory {s.a:06X} "
                           f"started a unit at the cap")
                    continue
                c.that(started, f"{name} frame {i}: idle factory {s.a:06X} "
                       f"type {s.type} did not start")
                if started:
                    made = t.obj if t.link != 0xFF else late.obj
                    if made not in S6_UNCOUNTED:
                        count[s.house] = n + 1


def s6_init_level(t, c, creator, level):
    """struct_init_upgrade_level $010A98: a computer house's structure
    starts upgraded by campaign.  `level` is what struct_create set
    before ($00E644: a Harkonnen Light Factory 1)."""
    if t == 3:
        return 1 if c >= 2 else level
    if t == 4:
        return {3: 1, 4: 2}.get(c, 3 if 5 <= c <= 8 else level)
    if t == 5:
        return 1 if c >= 6 and creator != 0 else level
    if t == 7:
        if c >= 5 and creator == 2:
            level = 1
        if c >= 3 and creator == 0:
            level = 1
        return level
    if t == 8:
        return 1 if c >= 5 else level
    if t == 10:
        return 1 if c != 0 else level
    if 3 <= t <= 10:
        return 0
    return level


def s6_is_upgradable(r, s):
    """struct_is_upgradable $010BA2."""
    c = r.w(S6_CAMPAIGN)
    st = S6_ST[s.type]
    if s.creator == 0 and s.type == 5:
        return False
    if s.creator == 2 and s.type == 4:
        if c == 5:
            return True
        if c > 5:
            return False
        if s.level == 1 and c < st["upgradeCampaign"][2]:
            return False
    uc = st["upgradeCampaign"][s.level] if s.level < 3 else 0
    if uc and uc <= c + 1:
        if s.type == 8:
            built = r.l(s6_house(r, s.creator) + 0x0E)
            need = S6_ST[16]["required"]
            if built & need != need:
                return False
        if s.type == 10 and s.creator == 1 and s.level == 1:
            return False
        if s.type == 4 and s.creator == 2 and c >= 7:
            return False
        return True
    return s.type == 7 and s.creator == 0 and s.level == 0 and c >= 3


@scenario("S6", "upgrade levels and upgrade time as a mission's structures start")
def s6_levels(c):
    names = sorted(p.stem for p in (ROOT / "tmp/sega/touch/pool").glob("seed-pw-*.state"))
    names = [n[5:] for n in names if n[8:] not in ("DUNEFINALE", "LOOKAROUND",
             "PLAYTESTER", "SPLURGEOLA", "VERSIONNUM")]
    seen = 0
    for name in names:
        r = frames(name, 0)[0]
        cmp = r.w(S6_CAMPAIGN)
        player = r.w(S6_PLAYER)
        for addr in s6_structs(r):
            s = S6Struct(r, addr)
            if s.type not in range(3, 11) or s.flags2 & 2:
                continue
            seen += 1
            base = 1 if (s.house == 0 and s.type == 3) else 0
            if s.house != player:
                want = s6_init_level(s.type, cmp, s.creator, base)
                c.that(s.level == want, f"{name}: computer type {s.type} level "
                       f"{s.level}, model {want}")
                c.that(s.upgradeLeft == 0, f"{name}: computer type {s.type} "
                       f"upgradeTimeLeft {s.upgradeLeft}")
            else:
                # the scenario loader raises the player's Construction
                # Yard to 1 from campaign 6 ($016948), after struct_create
                # has set upgradeTimeLeft at level 0
                lv = 1 if s.type == 8 and cmp >= 6 else base
                c.that(s.level == lv, f"{name}: player type {s.type} level "
                       f"{s.level}, model {lv}")
                if S6_ST[s.type]["flags"] & 2:
                    s.level = base
                    want = 100 if s6_is_upgradable(r, s) else 0
                    c.that(s.upgradeLeft == want, f"{name}: player type "
                           f"{s.type} upgradeTimeLeft {s.upgradeLeft}, model {want}")
    c.that(seen > 50, f"only {seen} structures")
