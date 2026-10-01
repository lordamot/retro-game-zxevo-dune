"""S5 - the economy: harvesting, the map's spice, refining, storage and power.

Loaded by sega_spec_check.py into its own namespace (scenario, frames,
Check, rom_w, landscape, MAP, allied and the rest come from there).
orig/sega/spec/S5-economy.md is what these check.
"""

S5_UNITS, S5_STRUCTS, S5_HOUSES = 0xFF1000, 0xFF4EB8, 0xFF4D10
S5_HARVESTER, S5_REFINERY = 16, 12
S5_SAND_TILE, S5_SPICE_FULL, S5_THICK_FULL = 0x7F, 0xBF, 0xCF

# computer harvesters at work, a refinery below its storage
S5_RUNS = ("pw-DIPLOMATIC", "pw-SPICEDANCE", "pw-DEATHRULER")
S5_N = 2000


def s5_u(i):
    return S5_UNITS + 0x8C * i


def s5_s(i):
    return S5_STRUCTS + 0x62 * i


def s5_h(h):
    return S5_HOUSES + 0x46 * h


def s5_div_shl8(a, b):
    """math_div_shl8 $0199F6: b * 256 / a, both halved (rounding up)
    until the dividend fits 16 bits; a zero divisor answers $FFFF."""
    d0, d1 = b << 8, a & 0xFFFF
    while d0 > 0xFFFF:
        d0 = (d0 + 1) >> 1
        d1 = ((d1 + 1) & 0xFFFF) >> 1
    if d1 == 0:
        return 0xFFFF
    q = d0 // d1
    return q if q <= 0xFFFF else d0


def s5_tile(r, sq):
    return r.w(MAP + 4 * sq) & 0x1FF


def s5_occupied(r, sq):
    return r.b(MAP + 4 * sq + 3) != 0


def s5_thick_near(r, sq):
    """map_find_thick_spice_near $01A4B2: the 24 offsets at $0714F2."""
    for i in range(24):
        dx = int.from_bytes(rom()[0x0714F2 + 4 * i:0x0714F4 + 4 * i], "big",
                            signed=True)
        dy = int.from_bytes(rom()[0x0714F4 + 4 * i:0x0714F6 + 4 * i], "big",
                            signed=True)
        s = (sq + dx + dy) & 0xFFFF
        if s >= 0x1000 or not valid_square(r, s) or s5_occupied(r, s):
            continue
        if s5_tile(r, s) != S5_THICK_FULL and landscape(r, s) == 9:
            return s
    return 0


def s5_find_spice(r, centre, radius):
    """map_find_spice $01A146: square rings out from the centre, rows top
    to bottom, the first and last row whole, the others only at their two
    ends; the first acceptable square wins."""
    x0, y0, w, h = (rom_w(0x06CE7A + 8 * r.w(0xFFC068) + 2 * i)
                    for i in range(4))
    cx, cy = centre & 63, centre >> 6 & 63

    def take(s):
        if not valid_square(r, s) or s5_occupied(r, s):
            return None
        lt = landscape(r, s)
        if lt == 8 and s5_tile(r, s) != S5_SPICE_FULL:
            return s5_thick_near(r, s) or s
        if lt == 9 and s5_tile(r, s) != S5_THICK_FULL:
            return s
        return None

    for d in range(radius):
        left, right = max(cx - d, x0), min(cx + d, x0 + w - 1)
        top, bottom = max(cy - d, y0), min(cy + d, y0 + h - 1)
        for y in range(top, bottom + 1):
            xs = range(left, right + 1) if y in (top, bottom) \
                else (left, right)
            for x in xs:
                got = take(y << 6 | x)
                if got is not None:
                    return got
    return 0


def s5_find_spice_pc(r, centre, radius):
    """OpenDUNE Map_SearchSpice: the nearest spice by distance, thick
    preferred within 4; the control for s5_find."""
    cx, cy = centre & 63, centre >> 6 & 63
    best1 = best2 = None
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if not (0 <= x < 64 and 0 <= y < 64):
                continue
            s = y << 6 | x
            if not valid_square(r, s) or s5_occupied(r, s):
                continue
            dy, dx = abs(y - cy), abs(x - cx)
            dist = dy + (dx >> 1) if dy >= dx else dx + (dy >> 1)
            lt = landscape(r, s)
            if lt == 9 and dist < 4 and (best2 is None or dist <= best2[0]):
                best2 = (dist, s)
            if lt == 8 and (best1 is None or dist <= best1[0]):
                best1 = (dist, s)
    if best2 and best2[0] <= radius:
        return best2[1]
    return best1[1] if best1 else 0


def s5_pc_spice_tile(r, sq, lt):
    """The tile OpenDUNE's Map_ChangeSpiceAmount leaves on the square it
    takes from: its own edges fixed up (the control for s5_spice)."""
    if lt == 0:
        return S5_SAND_TILE
    mask = 0
    for bit, off in enumerate((-64, 1, 64, -1)):
        n = sq + off
        if not (0 <= n < 0x1000):
            mask |= 1 << bit
            continue
        nl = landscape(r, n)
        if (lt == 8 and nl in (8, 9)) or (lt == 9 and nl == 9):
            mask |= 1 << bit
    return (0xB0 if lt == 8 else 0xC0) + mask


def s5_harvesters(r):
    return [i for i in range(102) if r.w(s5_u(i) + 4) & 1
            and r.b(s5_u(i) + 2) == S5_HARVESTER]


def s5_spice_events(c, runs, pc_tiles=False, n=S5_N):
    """Load growth and the spice taken from the harvester's square."""
    for name in runs:
        d = frames(name, n)
        for f in range(1, len(d)):
            a, b = d[f - 1], d[f]
            took = {}
            for i in s5_harvesters(a):
                if not b.w(s5_u(i) + 4) & 1:
                    continue
                l0, l1 = a.b(s5_u(i) + 0x5E), b.b(s5_u(i) + 0x5E)
                sq = square_of(b.l(s5_u(i) + 0xA))
                if l1 > l0 and b.b(s5_u(i) + 3) == 0xFF:
                    c.that(l1 == l0 + 1, f"{name} {f}: load {l0} -> {l1}")
                    c.that(l1 <= 100, f"{name} {f}: load {l1}")
                    c.that(landscape(a, sq) in (8, 9) or
                           landscape(b, sq) in (8, 9),
                           f"{name} {f}: harvested off spice")
                took[sq] = i
            for sq in range(0x1000):
                l0, l1 = landscape(a, sq), landscape(b, sq)
                if (l0, l1) not in ((9, 8), (8, 0)) or sq not in took:
                    continue
                want = S5_SPICE_FULL if l1 == 8 else S5_SAND_TILE
                if pc_tiles:
                    want = s5_pc_spice_tile(b, sq, l1)
                c.that(s5_tile(b, sq) == want,
                       f"{name} {f}: square {sq:#x} {l0}->{l1} shows "
                       f"{s5_tile(b, sq):#x}, spec {want:#x}")


@scenario("S5", "a harvest adds 0 or 1, and the square taken from shows $BF or sand")
def s5_spice(c):
    s5_spice_events(c, S5_RUNS)


def s5_cadence(c, runs, n=S5_N):
    """Harvest calls on one square come five unit-script ticks apart:
    call, delay 5, delay 10, call (UNIT.EMC w766-w872)."""
    for name in runs:
        d = frames(name, n)
        ticks, last = 0, {}
        for f in range(1, len(d)):
            a, b = d[f - 1], d[f]
            if a.l(0xFFDE8C) != b.l(0xFFDE8C):
                ticks += 1
            for i in s5_harvesters(a):
                u = s5_u(i)
                if b.b(u + 0x5E) != a.b(u + 0x5E) + 1 or b.b(u + 3) != 0xFF:
                    continue
                here = (b.l(u + 0xA), b.w(u + 0x5C), landscape(b, square_of(b.l(u + 0xA))))
                if i in last and last[i][1] == here:
                    c.that((ticks - last[i][0]) % 5 == 0,
                           f"{name} {f}: harvester {i} after "
                           f"{ticks - last[i][0]} script ticks")
                last[i] = (ticks, here)


@scenario("S5", "harvest calls are five unit-script ticks apart")
def s5_harvest_rate(c):
    s5_cadence(c, S5_RUNS)


def s5_refine_events(c, runs, pc_step=False, n=3500, every=2):
    """Every refine: the load it takes, what it pays, where the pay goes."""
    seen = 0
    for name in runs:
        d = frames(name, n, every=every)
        for f in range(1, len(d)):
            a, b = d[f - 1], d[f]
            for s in range(73):
                rec = s5_s(s)
                if not a.w(rec + 4) & 1 or a.b(rec + 2) != S5_REFINERY:
                    continue
                j = a.b(rec + 3)
                if j == 0xFF or b.b(rec + 3) != j:
                    continue
                l0, l1 = a.b(s5_u(j) + 0x5E), b.b(s5_u(j) + 0x5E)
                if l1 >= l0:
                    continue
                seen += 1
                hp, top = a.w(rec + 0x12), rom_w(btype(12) + 0x10)
                ratio = s5_div_shl8(top, hp)
                step = (ratio * 3) >> 8 if pc_step else mul_shr8(3, ratio)
                step = max(min(step, l0), 1)
                c.that(l0 - l1 == step, f"{name} {f * every}: refinery {s} "
                       f"took {l0 - l1}, spec {step} (hp {hp})")
                house = a.b(rec + 8)
                cnt = 0xFFC09E if allied(a, house, a.w(0xFFC274)) \
                    else 0xFFC0A0
                paid = b.w(cnt) - a.w(cnt)
                per = paid / max(l0 - l1, 1)
                want = {7} if house == a.w(0xFFC274) else {6, 7, 8, 9}
                c.that(paid % max(l0 - l1, 1) == 0 and per in want,
                       f"{name} {f * every}: paid {paid} for {l0 - l1}")
                h = s5_h(house)
                cap = max(a.l(h + 0x16), a.l(0xFFC054))
                c0, c1 = a.l(h + 0x12), b.l(h + 0x12)
                # the 30-tick pass pays for building, and a pass that runs
                # past the frame's end spreads its payments over two dumps
                built = any(d[g - 1].l(0xFFD5A0) != d[g].l(0xFFD5A0)
                            for g in (f - 1, f, f + 1) if 0 < g < len(d))
                c.that(c1 == min(c0 + paid, cap) or built,
                       f"{name} {f * every}: credits {c0} -> {c1}, paid "
                       f"{paid}, cap {cap}")
    c.that(seen > 20, f"only {seen} refines seen")


@scenario("S5", "a refine takes (3*health+$50)>>8 spice and pays 7 (6-9 for the AI) a unit, up to storage")
def s5_refine(c):
    s5_refine_events(c, ("pw-DIPLOMATIC", "pw-DEATHRULER", "pw-SPICEDANCE"))


def s5_power_check(c, r, tag, pc=False):
    """house_calc_power $01048C and house_power_to_health $010594, as they
    stand right after the house loop's 900-tick pass."""
    for h in range(6):
        hrec = s5_h(h)
        if not r.w(hrec + 4) & 1:
            continue
        stor = prod = use = 0
        mine = []
        for s in range(73):
            rec = s5_s(s)
            f = r.w(rec + 4)
            if not f & 1 or r.b(rec + 8) != h:
                continue
            if f & 4 and not r.w(0xFFC148):
                continue
            mine.append(rec)
            t = btype(r.b(rec + 2))
            stor += rom_w(t + 0x38)
            p = rom_w(t + 0x3A)
            p = p - 0x10000 if p & 0x8000 else p
            hp, top = r.w(rec + 0x12), rom_w(t + 0x10)
            if p >= 0:
                use = (use + p) & 0xFFFF
            elif hp >= top:
                prod = (prod - p) & 0xFFFF
            elif pc:
                prod += (-p) // 2 if hp <= top // 2 else (-p) * hp // top
            else:
                ratio = min(max(s5_div_shl8(top, hp), 0x80), 0xFF)
                prod = (prod + mul_shr8(-p, ratio)) & 0xFFFF
        c.that((r.l(hrec + 0x16), r.w(hrec + 0x1A), r.w(hrec + 0x1C))
               == (stor, prod, use),
               f"{tag} house {h}: storage/produced/used "
               f"{r.l(hrec + 0x16)}/{r.w(hrec + 0x1A)}/{r.w(hrec + 0x1C)}, "
               f"spec {stor}/{prod}/{use}")
        ratio = min(s5_div_shl8(use, prod), 0x100)
        for rec in mine:
            top = rom_w(btype(r.b(rec + 2)) + 0x10)
            want = (top * ratio) >> 8 if pc else mul_shr8(ratio, top)
            want = max(want, top >> 1)
            c.that(r.w(rec + 0x5E) == want,
                   f"{tag} house {h} structure {rec:#x}: max hp "
                   f"{r.w(rec + 0x5E)}, spec {want} (ratio {ratio})")


@scenario("S5", "storage, power and each structure's maximum health, recomputed every 900 ticks")
def s5_power(c):
    for name in S5_RUNS:
        d = frames(name, S5_N)
        for f in range(1, len(d)):
            if d[f - 1].l(0xFFDC44) != d[f].l(0xFFDC44):
                # a house pass that runs past the frame's end is caught
                # half-way: the next dump then holds its result
                c2 = Check()
                s5_power_check(c2, d[f], f"{name} {f}")
                if c2.fails and f + 1 < len(d):
                    c2 = Check()
                    s5_power_check(c2, d[f + 1], f"{name} {f + 1}")
                c.count += c2.count
                c.fails += c2.fails


@scenario("S5", "a harvester's new spice target is map_find_spice's (radius 32)")
def s5_find(c):
    s5_find_events(c)


def s5_find_events(c, finder=None, runs=S5_RUNS, n=S5_N):
    finder = finder or s5_find_spice
    seen = 0
    for name in runs:
        d = frames(name, n)
        for f in range(1, len(d)):
            a, b = d[f - 1], d[f]
            for i in s5_harvesters(a):
                u = s5_u(i)
                t0, t1 = a.w(u + 0x5C), b.w(u + 0x5C)
                if t1 == t0 or t1 >> 14 != 3 or a.w(u + 6) & 0x20 \
                        or b.b(u + 0x54) != 5 or b.b(u + 3) != 0xFF:
                    continue
                seen += 1
                here = square_of(b.l(u + 0xA))
                want = finder(b, here, 32)
                got = ref_square(b, t1)
                c.that(got == want, f"{name} {f}: harvester {i} at "
                       f"{here:#x} sent to {got:#x}, spec {want:#x}")
    c.that(seen >= 5, f"only {seen} searches seen")


@scenario("S5", "the PC's nearest-spice search does not fit the targets (control)")
def s5_find_control(c):
    c2 = Check()
    s5_find_events(c2, s5_find_spice_pc)
    c.that(len(c2.fails) > 0, "the PC's search fitted every target")
