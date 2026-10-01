# spec_s7.py - S7 (the enemy) scenarios for sega_spec_check.py.
#
# Loaded by sega_spec_check.py into its own namespace, so `scenario`,
# `frames`, `Check`, `Ram`, `ROM`, `CLOCK` and the rest are already here.
#
# The heart of it is a Python EMC interpreter written from the spec
# (orig/sega/spec/S7-enemy.md): it takes a script state out of a RAM
# snapshot and steps it, with the Mega Drive's own word widths, byte-wide
# stack and frame pointers and missing bounds checks.  A `call` cannot be
# run - the routine behind it is 68000 code - so each one is modelled by
# what it may do to the script state: its answer (known when the routine
# only reads a field, a wildcard otherwise), the delay it may write, and
# the restart it may cause.  A wildcard answer that a `goto-if` then tests
# forks the run; the machine's state after the tick has to be one of the
# states the forks end in.

S7_RAM = 0xFF0000
S7_UNIT_INFO, S7_TEAM_INFO, S7_BUILD_INFO = 0xFFC1B0, 0xFFC1E0, 0xFFC1C8
S7_UNITS, S7_UNIT_SIZE, S7_UNIT_FIND, S7_UNIT_COUNT = 0xFF1000, 0x8C, 0xFFDCC0, 0xFFDCBC
S7_STRUCTS, S7_STRUCT_SIZE, S7_STRUCT_FIND, S7_STRUCT_COUNT = 0xFF4EB8, 0x62, 0xFFD31C, 0xFFD318
S7_TEAMS, S7_TEAM_SIZE, S7_TEAM_FIND, S7_TEAM_COUNT = 0xFF47CC, 0x54, 0xFFDC60, 0xFFDC5C
S7_HOUSES_PTR, S7_HOUSE_SIZE = 0xFFDC24, 0x46
S7_PLAYER = 0xFFC274
S7_TICK_UNIT_SCRIPT, S7_TICK_STRUCT_SCRIPT, S7_TICK_TEAM = 0xFFDE8C, 0xFFD59C, 0xFFDCA4
S7_UNIT_TYPES = 0x06C5B4

_S7_ROM = None


def _s7_rom():
    global _S7_ROM
    if _S7_ROM is None:
        _S7_ROM = ROM.read_bytes()
    return _S7_ROM


WILD = object()          # a value the model cannot know


def _sx8(v):
    v &= 0xFF
    return v - 0x100 if v & 0x80 else v


def _sx16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class EmcState:
    """One script state, as bytes over a RAM snapshot: reads fall through
    to the snapshot, writes land in an overlay - so a stack index that
    wanders outside the stack reads and writes the record round it, as the
    machine's does."""

    def __init__(self, ram, base, overlay=None, wild=None):
        self.ram = ram
        self.base = base            # the script state; the delay is base-2
        self.mem = dict(overlay or {})
        self.wild = set(wild or ())  # addresses (word-aligned) holding WILD

    def copy(self):
        return EmcState(self.ram, self.base, self.mem, self.wild)

    def rb(self, a):
        if a in self.mem:
            return self.mem[a]
        return self.ram.u(a, 1)

    def wb(self, a, v):
        self.mem[a] = v & 0xFF

    def rw(self, a):
        if a in self.wild:
            return WILD
        return (self.rb(a) << 8) | self.rb(a + 1)

    def ww(self, a, v):
        if v is WILD:
            self.wild.add(a)
            self.mem.pop(a, None)
            self.mem.pop(a + 1, None)
            return
        self.wild.discard(a)
        self.wb(a, v >> 8)
        self.wb(a + 1, v)

    def rl(self, a):
        return (self.rb(a) << 24) | (self.rb(a + 1) << 16) | \
            (self.rb(a + 2) << 8) | self.rb(a + 3)

    def wl(self, a, v):
        for i in range(4):
            self.wb(a + i, v >> (24 - 8 * i))

    # the fields
    pc = property(lambda s: s.rl(s.base), lambda s, v: s.wl(s.base, v))
    info = property(lambda s: s.rl(s.base + 4))
    ret = property(lambda s: s.rw(s.base + 8), lambda s, v: s.ww(s.base + 8, v))
    fp = property(lambda s: s.rb(s.base + 0xA), lambda s, v: s.wb(s.base + 0xA, v))
    sp = property(lambda s: s.rb(s.base + 0xB), lambda s, v: s.wb(s.base + 0xB, v))
    delay = property(lambda s: s.rw(s.base - 2), lambda s, v: s.ww(s.base - 2, v))

    def var_addr(self, n):
        return self.base + 0xC + ((2 * n) & 0xFFFF if n >= 0 else 2 * n)

    def slot(self, i16):
        """Address of stack word i, i a signed 16-bit index."""
        return self.base + 0x16 + _sx16(2 * i16)

    def push(self, v):
        self.sp = self.sp - 1
        self.ww(self.slot(_sx8(self.sp)), v)

    def pop(self):
        v = self.rw(self.slot(_sx8(self.sp)))
        self.sp = self.sp + 1
        return v

    def top(self):
        return self.rw(self.slot(_sx8(self.sp)))

    def start(self):
        return self.ram.l(self.info + 4) if self.info >= S7_RAM else \
            int.from_bytes(_s7_rom()[self.info + 4:self.info + 8], "big")

    def key(self, skip_vars=()):
        """What is compared: pc, return value, frame and stack pointers,
        the five variables (bar those named), the live stack words and the
        delay."""
        out = [self.pc, self.ret, self.fp, self.sp, self.delay]
        for n in range(5):
            out.append(None if n in skip_vars else self.rw(self.base + 0xC + 2 * n))
        sp = _sx8(self.sp)
        for i in range(max(sp, 0), 15):
            out.append(self.rw(self.slot(i)))
        return out


def _rom_word(a):
    r = _s7_rom()
    return (r[a] << 8) | r[a + 1]


class StopRun(Exception):
    pass


class Fork(Exception):
    """A goto-if on a value the model does not know: both ways are run."""


def emc_step(s, variant=None, branch=None):
    """One emc_run on state s.  Answers 1, 0 (stopped), or ('call', n)
    after putting the pc past the call; `variant` swaps in a deliberately
    wrong semantics, for the controls."""
    pc = s.pc
    if pc == 0:
        return 0
    start = s.start()
    word = _rom_word(pc)
    pc += 2
    op = (word >> 8) & 0x1F
    par = 0
    if word & 0x8000:
        op, par = 0, word & 0x7FFF
    elif word & 0x4000:
        par = _sx8(word) & 0xFFFF
    elif word & 0x2000:
        par = _rom_word(pc)
        pc += 2
    s.pc = pc

    def stop():
        s.pc = 0
        return 0

    if op == 0:
        s.pc = start + 2 * par
    elif op == 1:
        s.ret = par
    elif op == 2:
        if par == 0:
            s.push(s.ret)
        elif par == 1:
            d = s.pc - start
            if d < 0:
                d += 1
            loc = (d >> 1) + (0 if variant == "loc" else 1)
            s.push(loc & 0xFFFF)
            s.push(_sx8(s.fp) & 0xFFFF)
            s.fp = s.sp + (1 if variant == "fp" else 2)
        else:
            return stop()
    elif op in (3, 4):
        s.push(par)
    elif op == 5:
        s.push(s.rw(s.base + 0xC + _sx16(2 * par)))
    elif op == 6:                                   # a local
        i = (_sx8(s.fp) - (_sx16(par) + 2)) & 0xFFFF
        s.push(s.rw(s.slot(i)))
    elif op == 7:                                   # a parameter
        i = (_sx8(s.fp) + par - 1) & 0xFFFF
        s.push(s.rw(s.slot(i)))
    elif op == 8:
        if par == 0:
            s.ret = s.pop()
        elif par == 1:
            if s.sp == 15:
                return stop()
            v = s.pop()
            s.fp = v & 0xFF if v is not WILD else 0
            loc = s.pop()
            if loc is WILD:
                raise StopRun("return to an unknown place")
            s.pc = start + 2 * _sx16(loc)
        else:
            return stop()
    elif op == 9:
        s.ww(s.base + 0xC + _sx16(2 * par), s.pop())
    elif op == 10:
        v = s.pop()
        i = (_sx8(s.fp) - (_sx16(par) + 2)) & 0xFFFF
        s.ww(s.slot(i), v)
    elif op == 11:
        v = s.pop()
        i = (_sx8(s.fp) + par - 1) & 0xFFFF
        s.ww(s.slot(i), v)
    elif op == 12:
        s.sp = s.sp + par
    elif op == 13:
        s.sp = s.sp - par
    elif op == 14:
        return ("call", par & 0xFF)
    elif op == 15:
        v = s.pop()
        if v is WILD:
            if branch is None:
                raise Fork()
            v = 0 if branch else 1         # branch taken means it was zero
            if variant == "ifnz":
                v = 1 - v
        if (v != 0) if variant != "ifnz" else (v == 0):
            return 1
        s.pc = start + 2 * (par & 0x7FFF)
    elif op == 16:
        v = s.pop()
        if par > 2:
            return stop()
        if v is WILD:
            s.push(WILD)
        elif par == 0:
            s.push(1 if v == 0 else 0)
        elif par == 1:
            s.push((-v) & 0xFFFF)
        else:
            s.push((~v) & 0xFFFF)
    elif op == 17:
        r = s.pop()
        l = s.pop()
        if variant == "swap":
            l, r = r, l
        if par > 17:
            return stop()
        if l is WILD or r is WILD:
            s.push(WILD)
            return 1
        L, R = _sx16(l), _sx16(r)
        if par == 0:
            v = 1 if (L and R) else 0
        elif par == 1:
            v = 1 if (L or R) else 0
        elif par == 2:
            v = int(L == R)
        elif par == 3:
            v = int(L != R)
        elif par == 4:
            v = int(L < R)
        elif par == 5:
            v = int(L <= R)
        elif par == 6:
            v = int(L > R)
        elif par == 7:
            v = int(L >= R)
        elif par == 8:
            v = L + R
        elif par == 9:
            v = L - R
        elif par == 10:
            v = L * R
        elif par in (11, 16):
            if R == 0:
                raise StopRun("divide by zero")
            q = abs(L) // abs(R) * (1 if (L < 0) == (R < 0) else -1)
            if not -0x8000 <= q <= 0x7FFF:       # divs overflow: V set
                v = L if par == 11 else 0
            else:
                v = q if par == 11 else L - q * R
        elif par == 12:
            v = L >> (R & 63) if (R & 63) < 16 else (-1 if L < 0 else 0)
        elif par == 13:
            v = (L << (R & 63)) if (R & 63) < 16 else 0
        elif par == 14:
            v = L & R
        elif par == 15:
            v = L | R
        else:
            v = L ^ R
        s.push(v & 0xFFFF)
    elif op == 18:
        if s.sp == 15:
            return stop()
        s.ret = s.pop()
        loc = s.pop()
        s.wb(s.base + 0x34, 0)
        if loc is WILD:
            raise StopRun("return to an unknown place")
        s.pc = start + 2 * _sx16(loc)
    else:
        return stop()
    return 1


def _entry(info_addr, ram, n):
    start = ram.l(info_addr + 4)
    offs = ram.l(info_addr + 8)
    o = _rom_word(offs + 2 * n) if offs < S7_RAM else ram.w(offs + 2 * n)
    return start + 2 * o


def _restart(s, info_addr, entry):
    """emc_reset then emc_start: pc to the entry, fp $11, sp $0F."""
    t = s.copy()
    t.pc = _entry(info_addr, s.ram, entry)
    t.fp = 0x11
    t.sp = 0x0F
    t.wb(t.base + 0x34, 0)
    return t


# ------------------------------------------------ what each call may do

def _team_calls(t, ram, team):
    """TEAM.EMC calls: the states the call may leave (the pc already past
    it).  members/min/target read a team field, so their answer is known."""
    def fix(v):
        u = t.copy()
        u.ret = v
        return [u]

    def wild():
        return fix(WILD)

    def call(n):
        if n == 2:
            return fix(ram.w(team + 4))
        if n == 12:
            return fix(ram.w(team + 6))
        if n == 13:
            return fix(ram.w(team + 0x1A))
        if n in (1, 11, 14):
            return fix(0)
        if n == 0:                        # delay: top / 5, divs
            top = t.top()
            if top is WILD:
                u = t.copy(); u.delay = WILD; u.ret = WILD
                return [u]
            d = int(_sx16(top) / 5) & 0xFFFF
            u = t.copy(); u.delay = d; u.ret = d
            return [u]
        if n == 10:                       # delay.rnd
            u = t.copy(); u.delay = WILD; u.ret = WILD
            return [u]
        if n in (8, 9):                   # behave / behave.orig
            want = t.top() if n == 8 else ram.w(team + 0xE)
            cur = ram.w(team + 0xC)
            if want is WILD:
                return wild()
            if want == cur:
                return fix(0)
            u = _restart(t, S7_TEAM_INFO, want & 0xFF)
            u.ret = 0
            return [u]
        return wild()
    return call


def _build_calls(t, ram, st):
    def fix(v):
        u = t.copy()
        u.ret = v
        return [u]

    def call(n):
        if n == 13:                       # state
            return fix(ram.w(st + 0x5C))
        if n in (1, 12, 16, 17, 18, 19, 20, 24):
            return fix(0)
        if n == 0:
            top = t.top()
            u = t.copy()
            if top is WILD:
                u.delay = WILD; u.ret = WILD
            else:
                d = int(_sx16(top) / 5) & 0xFFFF
                u.delay = d; u.ret = d
            return [u]
        return fix(WILD)
    return call


def _unit_calls(t, ram, unit):
    typ = ram.u(unit + 2, 1)
    trec = int.from_bytes(_s7_rom()[S7_UNIT_TYPES + 4 * typ:S7_UNIT_TYPES + 4 * typ + 4], "big")

    def fix(v):
        u = t.copy()
        u.ret = v
        return [u]

    def order(o):
        """unit_give_order as far as the script sees it: ignored, queued,
        or a restart at the type's entry with variable 0 the order."""
        u = t.copy(); u.ret = 0
        r = _restart(t, S7_UNIT_INFO, typ)
        r.ww(r.base + 0xC, o)
        r.delay = 0
        r.ret = 0
        return [u, r]

    def call(n):
        if n in (11, 14, 21, 38, 43, 52, 53, 57, 63):
            return fix(0)
        if n == 39:                       # a bare rts: d0 as it was
            return fix(WILD)
        if n == 16:
            top = t.top()
            u = t.copy()
            if top is WILD:
                u.delay = WILD; u.ret = WILD
            else:
                d = int(_sx16(top) / 5) & 0xFFFF
                u.delay = d; u.ret = d
            return [u]
        if n == 60:
            u = t.copy(); u.delay = WILD; u.ret = WILD
            return [u]
        if n == 1:
            o = t.top()
            if o is WILD:
                return None
            return order(o)
        if n == 10:
            o = int.from_bytes(_s7_rom()[trec + 0x28:trec + 0x2A], "big")
            return order(o)
        if n == 22:                       # fly.to: may step back and wait
            u = t.copy(); u.ret = WILD
            w = t.copy(); w.ret = 0; w.delay = WILD; w.pc = t.pc - 2
            return [u, w]
        if n in (9, 15):                  # deploy, die: the unit may go
            return None
        return fix(WILD)
    return call


def emc_explore(s, calls, budget, stop_on_delay, variant=None, limit=400):
    """Every state a tick may end in: run up to `budget` instructions,
    stopping early when the script stops (and, for units, when a delay
    is set).  Answers (ends, undetermined) - ends a list of states, and
    undetermined True when the model cannot say."""
    ends = []
    todo = [(s.copy(), 0)]
    while todo:
        if len(todo) + len(ends) > limit:
            return ends, True
        st, n = todo.pop()
        if n == budget:
            ends.append(st)
            continue
        x = st.copy()
        try:
            r = emc_step(x, variant)
            st = x
        except Fork:
            for way in (True, False):
                x = st.copy()
                emc_step(x, variant, way)
                todo.append((x, n + 1))
            continue
        except StopRun:
            return ends, True
        if r == 0:
            ends.append(st)
            continue
        if isinstance(r, tuple):
            outs = calls(st)(r[1]) if callable(calls(st)) else None
            if outs is None:
                return ends, True
            nxt = outs
        else:
            nxt = [st]
        for x in nxt:
            if stop_on_delay:
                if x.delay is WILD:
                    # a wild delay: either it is 0 and the run goes on, or
                    # it is not and the run ends here
                    y = x.copy(); y.delay = 0
                    todo.append((y, n + 1))
                    ends.append(x)
                    continue
                if x.delay != 0:
                    ends.append(x)
                    continue
            todo.append((x, n + 1))
    return ends, False


def _match(ends, post, skip_vars):
    got = post.key(skip_vars)
    for e in ends:
        want = e.key(skip_vars)
        if len(want) != len(got):
            continue
        if all(w is WILD or w is None or w == g for w, g in zip(want, got)):
            return True
    return False


def _find_list(r, arr, cnt):
    return [r.l(arr + 4 * i) for i in range(r.w(cnt))]


def _ticks(d, timer):
    return [i for i, (a, b) in enumerate(zip(d, d[1:])) if a.l(timer) != b.l(timer)]


S7_FRAME_SEEN = 0xFFE008


def _window(d, i, timer):
    """The dumps a tick's results may show in: from the one after the
    tick's timer moved (i+1) to the first taken after the next pass began
    - a slow pass runs on over several frames - and never past the next
    firing of the same timer."""
    e = d[i + 1].w(S7_FRAME_SEEN)
    out = []
    for j in range(i + 1, min(len(d), i + 10)):
        if j > i + 1 and d[j].l(timer) != d[j - 1].l(timer):
            break
        out.append(j)
        if d[j].w(S7_FRAME_SEEN) != e:
            break
    return out


def _teams_tick(c, d, i, variant=None, tally=None):
    """Check one team tick: dump i before, i+1 after (or i+2 if the loop
    ran past the frame's end)."""
    pre = d[i]
    order = _find_list(pre, S7_TEAM_FIND, S7_TEAM_COUNT)
    houses = pre.l(S7_HOUSES_PTR)
    stopped = False
    for team in order:
        base = team + 0x1E
        s = EmcState(pre, base)
        house = pre.w(team + 0x10)
        active = pre.w(houses + house * S7_HOUSE_SIZE + 4) & 8
        if not active or stopped:
            ends = [s]
        elif pre.w(team + 0x1C):
            e = s.copy(); e.delay = pre.w(team + 0x1C) - 1
            ends = [e]
        elif s.pc == 0 or s.info == 0:
            ends = [s]
        else:
            tally["stepped"] = tally.get("stepped", 0) + 1
            ends, und = emc_explore(
                s, lambda st, t=team: _team_calls(st, pre, t), 1, False, variant)
            if und:
                tally["undetermined"] += 1
                continue
            if all(e.pc == 0 for e in ends):
                stopped = True
        ok = any(_match(ends, EmcState(d[j], base), (4,))
                 for j in _window(d, i, S7_TICK_TEAM))
        tally["checked"] += 1
        if not ok:
            tally["bad"] += 1
            if variant is None:
                c.that(False, f"team {team:#x} at tick {i}: pc {s.pc:#x} -> "
                       f"{EmcState(d[i + 1], base).pc:#x}")


@scenario("S7", "team scripts step one instruction a team tick, as the model says")
def s7_team_vm(c):
    tally = {"checked": 0, "bad": 0, "undetermined": 0}
    for name in ("pw-DOMINATION", "pw-SONICBLAST", "pw-ARRAKISSUN"):
        d = frames(name, 3000)
        for i in _ticks(d, S7_TICK_TEAM):
            _teams_tick(c, d, i, None, tally)
    c.count += tally["checked"]
    c.that(tally["checked"] > 500, f"only {tally['checked']} team steps checked")
    c.that(tally["undetermined"] * 20 < tally["checked"],
           f"{tally['undetermined']} undetermined")
    s7_team_vm.tally = tally


def _structs_tick(c, d, i, variant=None, tally=None):
    pre = d[i]
    order = _find_list(pre, S7_STRUCT_FIND, S7_STRUCT_COUNT)
    stopped = False
    post_order = set(_find_list(d[i + 1], S7_STRUCT_FIND, S7_STRUCT_COUNT))
    for st in order:
        if st not in post_order:
            continue
        base = st + 0x16
        s = EmcState(pre, base)
        if pre.w(st + 0x12) == 0 or d[i + 1].w(st + 0x12) == 0:
            continue                       # dying: struct_destroy restarts it
        if stopped:
            ends = [s]
        elif pre.w(st + 0x14):
            e = s.copy(); e.delay = pre.w(st + 0x14) - 1
            ends = [e]
        elif s.pc == 0:
            # not loaded: emc_reset and emc_start, and nothing runs
            ends = [_restart(s, S7_BUILD_INFO, pre.u(st + 2, 1))]
        else:
            tally["stepped"] = tally.get("stepped", 0) + 1
            ends, und = emc_explore(
                s, lambda x, a=st: _build_calls(x, pre, a), 3, False, variant)
            if und:
                tally["undetermined"] += 1
                continue
            if any(e.pc == 0 for e in ends) and all(e.pc == 0 for e in ends):
                stopped = True
            # the loop's own afterword: turrets halve their delay
            if pre.u(st + 2, 1) in (15, 16):
                for e in ends:
                    if e.delay is not WILD:
                        e.delay = _sx16(e.delay) >> 1 & 0xFFFF
        ok = any(_match(ends, EmcState(d[j], base), (4,))
                 for j in _window(d, i, S7_TICK_STRUCT_SCRIPT))
        tally["checked"] += 1
        if not ok:
            tally["bad"] += 1
            if variant is None:
                c.that(False, f"structure {st:#x} type {pre.u(st + 2, 1)} at "
                       f"tick {i}: pc {s.pc:#x} -> {EmcState(d[i + 1], base).pc:#x}")


@scenario("S7", "structure scripts run three instructions a script tick, as the model says")
def s7_build_vm(c):
    tally = {"checked": 0, "bad": 0, "undetermined": 0}
    for name in ("pw-DOMINATION", "pw-SONICBLAST"):
        d = frames(name, 2000)
        for i in _ticks(d, S7_TICK_STRUCT_SCRIPT):
            _structs_tick(c, d, i, None, tally)
    c.count += tally["checked"]
    s7_build_vm.tally = tally
    c.that(tally["checked"] > 1000, f"only {tally['checked']} structure ticks checked")
    c.that(tally["undetermined"] * 10 < tally["checked"],
           f"{tally['undetermined']} undetermined of {tally['checked']}")


def _units_tick(c, d, i, variant=None, tally=None):
    pre, post = d[i], d[i + 1]
    player = pre.w(S7_PLAYER)
    order = _find_list(pre, S7_UNIT_FIND, S7_UNIT_COUNT)
    post_set = set(_find_list(post, S7_UNIT_FIND, S7_UNIT_COUNT))
    win = _window(d, i, S7_TICK_UNIT_SCRIPT)
    for u in order:
        if u not in post_set or pre.w(u + 4) & 4:
            continue
        base = u + 0x16
        s = EmcState(pre, base)
        if any(not d[j].w(u + 4) & 1 for j in win):
            tally["removed"] += 1          # freed while the pass ran on
            continue
        if any(pre.u(u + 0x54, 1) != d[j].u(u + 0x54, 1) or
               pre.u(u + 2, 1) != d[j].u(u + 2, 1) for j in win):
            tally["reordered"] += 1        # an order from outside the script
            continue
        if pre.w(u + 0x14):
            e = s.copy(); e.delay = pre.w(u + 0x14) - 1
            ends = [e]
        elif s.pc == 0 or s.info == 0:
            ends = [s]
        else:
            s.ww(base + 0xC + 6, player)   # variable 3, set by the loop
            tally["stepped"] = tally.get("stepped", 0) + 1
            e17, u1 = emc_explore(
                s, lambda x, a=u: _unit_calls(x, pre, a), 17, True, variant)
            e49, u2 = emc_explore(
                s, lambda x, a=u: _unit_calls(x, pre, a), 49, True, variant)
            if u1 or u2:
                tally["undetermined"] += 1
                continue
            ends = e17 + e49
        # a unit freed earlier in the find array during the pass closes
        # the gap, and the loop's cursor then passes over the next unit:
        # this one may not have run at all
        idx = order.index(u)
        if any(not d[win[-1]].w(v + 4) & 1 for v in order[:idx]):
            ends = ends + [s]
            tally["maybe_skipped"] = tally.get("maybe_skipped", 0) + 1
        ok = any(_match(ends, EmcState(d[j], base), (1, 4)) for j in win)
        tally["checked"] += 1
        if not ok:
            tally["bad"] += 1
            if variant is None:
                c.that(False, f"unit {u:#x} type {pre.u(u + 2, 1)} order "
                       f"{pre.u(u + 0x54, 1)} at tick {i}: pc {s.pc:#x} -> "
                       f"{EmcState(post, base).pc:#x}")


@scenario("S7", "unit scripts run to a delay, a stop or their budget, as the model says")
def s7_unit_vm(c):
    tally = {"checked": 0, "bad": 0, "undetermined": 0, "reordered": 0, "removed": 0}
    for name in ("pw-DOMINATION", "pw-SONICBLAST"):
        d = frames(name, 1500)
        for i in _ticks(d, S7_TICK_UNIT_SCRIPT):
            _units_tick(c, d, i, None, tally)
    c.count += tally["checked"]
    s7_unit_vm.tally = tally
    c.that(tally["checked"] > 1000, f"only {tally['checked']} unit ticks checked")
    c.that(tally["undetermined"] * 4 < tally["checked"],
           f"{tally['undetermined']} undetermined of {tally['checked']}")


@scenario("S7", "a wrong VM does not fit (control)")
def s7_vm_control(c):
    """Four deliberate mistakes, each of which must misfit: goto-if
    jumping on non-zero, binary operands swapped, the frame pointer one
    off, the pushed return location without its +1."""
    s7_vm_control.bad = {}
    d = frames("pw-DOMINATION", 1500)
    for variant in ("ifnz", "swap", "fp", "loc"):
        tally = {"checked": 0, "bad": 0, "undetermined": 0, "reordered": 0, "removed": 0}
        for i in _ticks(d, S7_TICK_TEAM):
            _teams_tick(c, d, i, variant, tally)
        for i in _ticks(d, S7_TICK_STRUCT_SCRIPT):
            _structs_tick(c, d, i, variant, tally)
        for i in _ticks(d, S7_TICK_UNIT_SCRIPT)[:120]:
            _units_tick(c, d, i, variant, tally)
        s7_vm_control.bad[variant] = tally["bad"]
        c.that(tally["bad"] > 0, f"variant {variant} fits too: {tally}")


def _team_members(r):
    teams = _find_list(r, S7_TEAM_FIND, S7_TEAM_COUNT)
    units = _find_list(r, S7_UNIT_FIND, S7_UNIT_COUNT)
    return teams, units


def _s7_movement(typ):
    rom = _s7_rom()
    trec = int.from_bytes(rom[S7_UNIT_TYPES + 4 * typ:S7_UNIT_TYPES + 4 * typ + 4], "big")
    return int.from_bytes(rom[trec + 0x3E:trec + 0x40], "big")


def _s7_candidates(r, team, units, by_scenario):
    """The units a recruit that walked the team's own house would take:
    same house, same movement class, no Saboteur, in no team, and with
    byScenario (+$04 bit 9) as asked."""
    out = []
    for u in units:
        if r.u(u + 8, 1) != r.w(team + 0x10) or r.u(u + 0x75, 1):
            continue
        typ = r.u(u + 2, 1)
        if typ == 6 or _s7_movement(typ) != r.w(team + 0xA):
            continue
        if bool(r.w(u + 4) & 0x200) != by_scenario:
            continue
        out.append(u)
    return out


@scenario("S7", "teams never recruit: recruit walks the other side's list")
def s7_recruit(c):
    """emc_team_recruit $02E544 walks unit_list_first(house_are_allied(
    team house, player)) - the list of the *other* side - so it can never
    find a unit of the team's own house.  Checked: members stay 0 and no
    unit joins a team, although at the team ticks there were units a
    recruit of the team's own side would have taken."""
    ticks = md_rule = pc_rule = 0
    for name in ("pw-DOMINATION", "pw-ARRAKISSUN", "pw-SONICBLAST"):
        d = frames(name, 600, every=10)
        for k, r in enumerate(d):
            teams, units = _team_members(r)
            for t in teams:
                c.that(r.w(t + 4) == 0, f"{name}: team {r.w(t)} has {r.w(t + 4)} members")
            for u in units:
                c.that(r.u(u + 0x75, 1) == 0, f"{name}: unit {u:#x} is in a team")
            houses = r.l(S7_HOUSES_PTR)
            for t in teams:
                if not r.w(houses + r.w(t + 0x10) * S7_HOUSE_SIZE + 4) & 8:
                    continue
                ticks += 1
                md_rule += bool(_s7_candidates(r, t, units, False))
                pc_rule += bool(_s7_candidates(r, t, units, True))
            if k and r.l(S7_TICK_TEAM) != d[k - 1].l(S7_TICK_TEAM):
                # re-set 5-12 ticks after a firing inside this 10-frame gap
                ahead = r.l(S7_TICK_TEAM) - r.l(CLOCK)
                c.that(-5 <= ahead <= 12 and
                       r.l(S7_TICK_TEAM) - d[k - 1].l(CLOCK) >= 5,
                       f"team timer {r.l(S7_TICK_TEAM)} at clock {r.l(CLOCK)}")
    # the evidence that the empty teams are the bug and not a lack of
    # units: a recruit over its own side would have had someone to take
    c.that(ticks > 1000, f"only {ticks} active team samples")
    c.that(md_rule > 100, f"only {md_rule} samples with a unit to recruit")
    c.that(pc_rule > 100, f"only {pc_rule} samples with a scenario unit to recruit")
    s7_recruit.counts = (ticks, md_rule, pc_rule)


def _s7_dist(p, q):
    dy = abs(_sx16(p >> 16) - _sx16(q >> 16)) & 0xFFFF
    dx = abs(_sx16(p) - _sx16(q)) & 0xFFFF
    return (max(dx, dy) + (min(dx, dy) >> 1)) & 0xFFFF
