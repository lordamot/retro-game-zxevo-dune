"""spec_s8.py - the tests of orig/sega/spec/S8-map.md: the map and the fog.

Loaded by sega_spec_check.py into its own namespace (`scenario`, `frames`,
`Check`, `Ram`, `state`, `_run`, `WORK`, `ROM` and the rest are its).
Every name defined here starts with `s8` so that the modules of the other
specs, which share the namespace, cannot collide with it.
"""

import tempfile as _s8_tempfile
from pathlib import Path as _S8Path

S8_MAP = 0xFF7D9C          # map: 64 x 64 squares of 4 bytes (*$04AA1C)
S8_COPY = 0xFF6C98         # mapGround: the loaded ground icon of each square
S8_SEED = 0xFFC064         # scenarioMap (l): the Seed, 1-27
S8_SCALE = 0xFFC068        # mapScale (w)
S8_VEILED = 0xFFC224       # veiledIcon (w)
S8_BLOOM = 0xFFC228        # bloomIcon (w)
S8_BLOOMS = 0xFFC71C       # scenarioBlooms (l): the mission's 'B' list, in ROM
S8_PLAYER = 0xFFC274
S8_RADAR_ROW = 0xFFBF6A    # radarRow (w): the next row, & 63
S8_RADAR_ON = 0xFFBF6C     # radarShowsMap (b)
S8_SMALL = 0xFFBF51        # radarSmallMap (b): the map is 32 x 32
S8_HOOKS = (0x608E, 0x6D0C)

S8_LIMITS = 0x06CE7A       # (x0, y0, w, h) per mapScale
S8_MAPS = 0x01B276         # the 27 battlefields' pointers
S8_LAND = 0x005818         # landscape type of each of 360 icons
S8_RADAR_ICON = 0x005256   # radar colour of each of 360 icons
S8_RADAR_HOUSE = 0x00524E  # radar colour of each house
S8_RADAR_EDGE = 0x0054C0   # the edge pixel colour of each house
S8_BORDER = 0x00543C       # a border row's longword of pixels per house
S8_ICONMAP = 0x04AA28      # ICON.MAP: 27 group starts, then the icons
S8_BLOOM_OFS = 0x0714A0    # the 'B' list's square offset per mapScale
S8_UNITS = 0x06C5B4        # unit type records, by pointer
S8_BUILDINGS = 0x06B94C    # building type records, by pointer
S8_LAYOUT_CENTRE = 0x06B930


def s8_rb(a):
    return rom()[a]


def s8_sb(a):
    v = rom()[a]
    return v - 256 if v > 127 else v


def s8_ws(a):
    v = rom_w(a)
    return v - 65536 if v > 32767 else v


def s8_limits(scale):
    return [rom_w(S8_LIMITS + 8 * scale + 2 * i) for i in range(4)]


def s8_valid(scale, sq):
    """map_is_valid_position $005798."""
    x0, y0, w, h = s8_limits(scale)
    return x0 <= (sq & 63) < x0 + w and y0 <= (sq >> 6) < y0 + h


def s8_stored(seed):
    """The ground icon of every square as map_load $01B1D4 writes it:
    None where a 32 x 32 map writes nothing."""
    p = rom_l(S8_MAPS + 4 * (seed - 1))
    out = [None] * 4096
    small = p & 0x80000000
    p &= 0xFFFFFF
    for sq in range(4096):
        y, x = sq >> 6, sq & 63
        if small:
            if not (16 <= x < 48 and 16 <= y < 48):
                continue
            v = rom()[p + (y - 16) * 32 + (x - 16)]
        else:
            v = rom()[p + sq]
        out[sq] = {0xB0: 0x7F, 0xC0: 0xBF}.get(v, v)
    return out


def s8_word(r, sq):
    return r.w(S8_MAP + 4 * sq)


def s8_flags(r, sq):
    return r.u(S8_MAP + 4 * sq + 2, 1)


def s8_index(r, sq):
    return r.u(S8_MAP + 4 * sq + 3, 1)


def s8_land(r, sq):
    """map_get_landscape_type $0057E6."""
    w = s8_word(r, sq)
    g = s8_sb(S8_LAND + (w & 0x1FF))
    o = s8_sb(S8_LAND + ((w >> 9) & 0x7F))
    return o if o == 13 else g


def s8_icon(group, i):
    return rom_w(S8_ICONMAP + 2 * (rom_w(S8_ICONMAP + 2 * group) + i))


def s8_distance_squares(dy, dx):
    """tile_distance_squares $0115C2 between two square corners."""
    a, b = abs(dy) * 256, abs(dx) * 256
    d = (max(a, b) + (min(a, b) >> 1))
    return (d + 0x80) >> 8


def s8_unfog_shape(sq, radius):
    """The squares map_unfog_radius $019FFE reveals round a square: the
    (2r+1) box, inside the 64 x 64 array, rounded distance <= r."""
    y, x = sq >> 6, sq & 63
    out = set()
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if 0 <= y + dy < 64 and 0 <= x + dx < 64 \
                    and s8_distance_squares(dy, dx) <= radius:
                out.add(((y + dy) << 6) + x + dx)
    return out


def s8_square_of(pos):
    return ((pos >> 24) << 6) + ((pos >> 8) & 0xFF)


# ---------------------------------------------------------- the runs

def s8_split(lines, step, dump):
    """The script with `dump(i)` inserted after every `step` frames
    (a press is not split), and the frame count each dump is taken at."""
    out, at, t, nxt = [], [], 0, step
    for ln in lines:
        parts = ln.split()
        if parts and parts[0] == "run":
            n = int(parts[1])
            while n:
                k = min(n, nxt - t)
                out.append(f"run {k}")
                t += k
                n -= k
                if t >= nxt:
                    out.append(dump(len(at)))
                    at.append(t)
                    nxt += step
            continue
        out.append(ln)
        if parts and parts[0] == "press":
            t += int(parts[2])
            while t >= nxt:
                out.append(dump(len(at)))
                at.append(t)
                nxt += step
    return out, at


def s8_start(name):
    """The first battle frame of a sega_touch scenario: the state and the
    RAM of the first frame whose hook is a battle's, found by playing the
    scenario three times (the machine is deterministic: every 100 frames,
    then every frame near the hit, then to it and save).  Cached under
    tmp/sega/spec/s8/."""
    work = WORK / "s8"
    work.mkdir(parents=True, exist_ok=True)
    st, raw = work / f"{name}-start.state", work / f"{name}-start.ram"
    if st.exists() and raw.exists():
        return st, Ram(raw.read_bytes())
    lines = sega_touch.scenarios(ROM.read_bytes())[name]

    def first(lines, step):
        with _s8_tempfile.TemporaryDirectory() as d:
            body, at = s8_split(lines, step, lambda i: f"ram {d}/{i}.bin")
            _run(body)
            for i, t in enumerate(at):
                p = _S8Path(d) / f"{i}.bin"
                if p.exists() and Ram(p.read_bytes()).l(0xFFE002) in S8_HOOKS:
                    return t
        sys.exit(f"error: {name} never reached a battle")

    t0 = first(lines, 100)
    # replay exactly to t0 - 100, then frame by frame
    body, at = s8_split(lines, 1, lambda i: f"#{i}")
    upto = body[:body.index(f"#{t0 - 101}") + 1] if t0 > 100 else []
    with _s8_tempfile.TemporaryDirectory() as d:
        lines2 = [ln for ln in upto if not ln.startswith("#")]
        rest = body[len(upto):]
        probe, n = [], 0
        for ln in rest:
            if ln.startswith("#"):
                probe.append(f"ram {d}/{n}.bin")
                n += 1
                if n > 110:
                    break
            else:
                probe.append(ln)
        _run(lines2 + probe)
        hit = next(i for i in range(n) if (_S8Path(d) / f"{i}.bin").exists()
                   and Ram((_S8Path(d) / f"{i}.bin").read_bytes()).l(0xFFE002)
                   in S8_HOOKS)
    cut = []
    k = 0
    for ln in rest:
        if ln.startswith("#"):
            if k == hit:
                break
            k += 1
        else:
            cut.append(ln)
    _run(lines2 + cut + [f"save {st}", f"ram {raw}"])
    return st, Ram(raw.read_bytes())


def s8_play(st, lines, step):
    """Load a state file, play script `lines`, and dump RAM every `step`
    frames of them (s8_split)."""
    with _s8_tempfile.TemporaryDirectory() as d:
        body, at = s8_split(lines, step, lambda i: f"ram {d}/{i}.bin")
        _run([f"load {st}", f"ram {d}/start.bin"] + body)
        out = [Ram((_S8Path(d) / "start.bin").read_bytes())]
        for i in range(len(at)):
            p = _S8Path(d) / f"{i}.bin"
            if p.exists():
                out.append(Ram(p.read_bytes()))
        return out


def s8_frames_vram(st, n, every=1):
    """RAM and VRAM after each of n + 1 dumps from a state file."""
    with _s8_tempfile.TemporaryDirectory() as d:
        lines = [f"load {st}"]
        for i in range(n + 1):
            lines += [f"ram {d}/{i}.bin", f"vram {d}/{i}.vram"]
            if i < n:
                lines.append(f"run {every}")
        _run(lines)
        out = []
        for i in range(n + 1):
            v = bytearray((_S8Path(d) / f"{i}.vram").read_bytes())
            v[0::2], v[1::2] = v[1::2], v[0::2]
            out.append((Ram((_S8Path(d) / f"{i}.bin").read_bytes()), bytes(v)))
        return out


def s8_object_squares(pos, size):
    """map_visit_object_squares $019E0C for sizes up to 32: the squares an
    object of `size` pixels at `pos` covers (the half-size long at $06CC26
    taken off, then up to nine offsets from $06C806 + 32 * (size - 1))."""
    d = min(max(size - 1, 15), 32)
    base = (pos - rom_l(0x06CC26 + 4 * d)) & 0xFFFFFFFF
    out, prev, off = [], None, 0
    for i in range(9):
        if i:
            off = rom_l(0x06C806 + 32 * d + 4 * (i - 1))
            if off == 0:
                break
        y = ((base >> 16) + (off >> 16)) & 0xFFFF
        x = ((base & 0xFFFF) + (off & 0xFFFF)) & 0xFFFF
        if (y | x) & 0xC000:
            continue
        sq = ((y >> 8) << 6) + (x >> 8)
        if sq != prev:
            out.append(sq)
            prev = sq
    return out


# ---------------------------------------------------------- predictions

S8_STARTS = ("m1-0", "m1-1", "m1-2", "pw-DIPLOMATIC", "pw-DOMINATION",
             "pw-ETERNALSUN", "pw-SPICEDANCE", "pw-DEATHRULER")


def s8_blooms(r):
    """The mission's 'B' list: the squares map_load's caller ($016306)
    turns into spice blooms."""
    p = r.l(S8_BLOOMS)
    if not p:
        return []
    off = rom_w(S8_BLOOM_OFS + 2 * r.w(S8_SCALE))
    return [(rom_w(p + 2 + 2 * i) + off) & 0xFFFF for i in range(rom_w(p))]


def s8_fog_tile(r, sq):
    """map_update_fog_edge $01AADC: the overlay a revealed square gets from
    its four neighbours (N E S W, $07156A), 0 when all are revealed."""
    mask = 0
    for i, d in enumerate((-64, 1, 64, -1)):
        n = sq + d
        # the x of a neighbour is taken & 63 and never tested; only the
        # row can leave the map
        if not (0 <= n < 4096) or not (s8_flags(r, n) & 8):
            mask |= 1 << i
    return 0 if mask == 0 else s8_icon(7, mask)


def s8_revealed_at_start(r, shape=None):
    """What game_prepare $026578 reveals: round every structure of the
    player's the fog radius of its type's sight from its layout's centre,
    round every unit of the player's on the map its type's sight, and the
    squares under each ground unit's sprite."""
    shape = shape or s8_unfog_shape
    pl = r.w(S8_PLAYER)
    out = set()
    for u in range(102):
        a = 0xFF1000 + u * 0x8C
        f = r.w(a + 4)
        if not (f & 1) or (f & 4) or r.u(a + 8, 1) != pl:
            continue
        t = rom_l(S8_UNITS + 4 * r.u(a + 2, 1))
        sight = rom_w(t + 0x12)
        if sight:
            out |= shape(s8_square_of(r.l(a + 0xA)), sight)
        if rom_w(t + 0x3E) != 4:
            out |= set(s8_object_squares(r.l(a + 0xA), rom_w(t + 0x3A) + 3))
    for s in range(73):
        a = 0xFF4EB8 + s * 0x62
        f = r.w(a + 4)
        if not (f & 1) or (f & 4) or r.u(a + 8, 1) != pl:
            continue
        t = rom_l(S8_BUILDINGS + 4 * r.u(a + 2, 1))
        centre = (r.l(a + 0xA) + rom_l(S8_LAYOUT_CENTRE + 4 * rom_w(t + 0x3C))) \
            & 0xFFFFFFFF
        if rom_w(t + 0x12):
            out |= shape(s8_square_of(centre), rom_w(t + 0x12))
    return out


def s8_radar_row(r, row):
    """radar_frame $005124 with the map off (radarShowsMap clear): the 64
    pixels of radar row `row`."""
    pl = r.w(S8_PLAYER)
    if row in (0, 63):
        return [rom()[S8_BORDER + 4 * pl] >> 4] * 64
    small = r.u(S8_SMALL, 1)
    edge = rom()[S8_RADAR_EDGE + pl]
    if small:
        sqs = [((16 + row // 2) << 6) + 16 + x for x in range(32)]
    else:
        sqs = [(row << 6) + x for x in range(64)]
    cols = []
    for sq in sqs:
        c = 12
        if s8_flags(r, sq) & 0x20 and s8_index(r, sq):
            a = 0xFF4EB8 + (s8_index(r, sq) - 1) * 0x62
            if r.u(a + 8, 1) == pl:
                c = rom()[S8_RADAR_HOUSE + pl]
        cols.append(c)
    if small:
        cols = [c for c in cols for _ in (0, 1)]
    cols[0] = cols[-1] = edge
    return cols


def s8_vram_row(v, row):
    """A radar row as radar_upload_row $00504A left it in VRAM: eight
    longwords 128 bytes apart from $D000 + 4 * (row & 31), the second
    half of the rows $400 on."""
    base = 0xD000 + (row & 31) * 4 + (0x400 if row & 32 else 0)
    px = []
    for k in range(8):
        for b in v[base + 128 * k:base + 128 * k + 4]:
            px += [b >> 4, b & 15]
    return px


# ---------------------------------------------------------- the scenarios

@scenario("S8", "the map after a mission loads is its stored battlefield")
def s8_load(c):
    for name in S8_STARTS:
        _, r = s8_start(name)
        want = s8_stored(r.l(S8_SEED))
        blooms = set(s8_blooms(r))
        veiled = r.w(S8_VEILED)
        c.that(veiled == s8_icon(7, 15), f"{name}: veiled icon {veiled:#x}")
        for sq in range(4096):
            if want[sq] is None:
                continue
            w = s8_word(r, sq)
            c.that(r.u(S8_COPY + sq, 1) == want[sq],
                   f"{name}: copy at {sq} is not the stored map")
            g = w & 0x1FF
            if sq in blooms:
                c.that(g == r.w(S8_BLOOM), f"{name}: bloom at {sq} is {g:#x}")
            elif g != want[sq]:
                # only what the mission put there: slabs, walls, structures
                lt = s8_sb(S8_LAND + g)
                c.that(lt in (10, 11, 12),
                       f"{name}: square {sq} ground {g:#x}, stored "
                       f"{want[sq]:#x}")
            ov = w >> 9
            if s8_flags(r, sq) & 8:
                c.that(ov == s8_fog_tile(r, sq),
                       f"{name}: revealed {sq} overlay {ov:#x}")
            else:
                c.that(ov == veiled, f"{name}: fogged {sq} overlay {ov:#x}")


@scenario("S8", "control: map_load without its two icon swaps, or a 32 x 32 map "
                "at the corner, does not fit")
def s8_load_control(c):
    bad = 0
    for name in S8_STARTS:
        _, r = s8_start(name)
        seed = r.l(S8_SEED)
        p = rom_l(S8_MAPS + 4 * (seed - 1))
        for sq in range(4096):
            y, x = sq >> 6, sq & 63
            if p & 0x80000000:
                if y >= 32 or x >= 32:
                    continue
                v = rom()[(p & 0xFFFFFF) + y * 32 + x]
            else:
                v = rom()[p + sq]
            bad += r.u(S8_COPY + sq, 1) != v
    c.that(bad > 1000, f"the wrong loader fits too well ({bad} misfits)")


@scenario("S8", "a mission starts with exactly the player's sight shapes revealed")
def s8_fog_start(c):
    for name in S8_STARTS:
        _, r = s8_start(name)
        rev = {sq for sq in range(4096) if s8_flags(r, sq) & 8}
        want = s8_revealed_at_start(r)
        c.that(rev == want, f"{name}: {len(rev - want)} revealed beyond the "
               f"prediction, {len(want - rev)} predicted and fogged")


@scenario("S8", "control: the distance not rounded up, or a square radius, "
                "does not fit")
def s8_fog_control(c):
    # A circle, dx*dx + dy*dy <= r*r, gives the same shape as the game's
    # rounded distance for every radius up to 4 (the first difference is
    # at 5, a Launcher's or a Starport's sight), so it cannot be the
    # control here; dropping the +$80 of tile_distance_squares can.
    def floor(sq, rad):
        y, x = sq >> 6, sq & 63
        out = set()
        for dy in range(-rad, rad + 1):
            for dx in range(-rad, rad + 1):
                a, b = abs(dy) * 256, abs(dx) * 256
                if 0 <= y + dy < 64 and 0 <= x + dx < 64 \
                        and (max(a, b) + (min(a, b) >> 1)) >> 8 <= rad:
                    out.add(((y + dy) << 6) + x + dx)
        return out

    def box(sq, rad):
        y, x = sq >> 6, sq & 63
        return {((y + dy) << 6) + x + dx for dy in range(-rad, rad + 1)
                for dx in range(-rad, rad + 1)
                if 0 <= y + dy < 64 and 0 <= x + dx < 64}

    for shape, what in ((floor, "unrounded"), (box, "box")):
        wrong = 0
        for name in S8_STARTS:
            _, r = s8_start(name)
            rev = {sq for sq in range(4096) if s8_flags(r, sq) & 8}
            wrong += rev != s8_revealed_at_start(r, shape)
        c.that(wrong == len(S8_STARTS), f"the {what} radius fits "
               f"{len(S8_STARTS) - wrong} of {len(S8_STARTS)} missions")


@scenario("S8", "in play: fog only lifts, edges follow the neighbours, craters "
                "follow the landscape")
def s8_fog_play(c):
    import random as _random
    for name in ("pw-SPICEDANCE", "pw-DEATHRULER", "m1-1"):
        st, _ = s8_start(name)
        # a random player (sega_touch's), the same every run
        # (Start is left out: its menu leads out of the battle)
        lines = [ln.replace("start", "mdc") for ln in
                 sega_touch.random_input(_random.Random(8), 8000)]
        d = s8_play(st, lines, 50)
        seed = d[0].l(S8_SEED)
        d = [r for r in d if r.l(0xFFE002) in S8_HOOKS and r.l(S8_SEED) == seed]
        c.that(sum(s8_flags(d[-1], q) & 8 for q in range(4096)) >
               sum(s8_flags(d[0], q) & 8 for q in range(4096)),
               f"{name}: nothing was revealed in play")
        veiled = d[0].w(S8_VEILED)
        scale = d[0].w(S8_SCALE)
        loaded = s8_stored(seed)
        for a, b in zip(d, d[1:]):
            for sq in range(4096):
                if s8_flags(a, sq) & 8:
                    c.that(s8_flags(b, sq) & 8, f"{name}: {sq} fogged again")
        for i, r in enumerate(d):
            for sq in range(4096):
                w = s8_word(r, sq)
                ov = w >> 9
                rev = s8_flags(r, sq) & 8
                if not rev:
                    # outside a 32 x 32 map nothing was ever written
                    if loaded[sq] is not None:
                        c.that(ov == veiled,
                               f"{name}@{i}: fogged {sq} ov {ov:#x}")
                    continue
                if ov == 0 or veiled - 15 <= ov <= veiled:
                    c.that(ov == s8_fog_tile(r, sq),
                           f"{name}@{i}: {sq} edge {ov:#x}")
                elif 1 <= ov <= 12:
                    lt = s8_land(r, sq)
                    c.that(lt not in (6, 8, 9, 10, 11, 12, 13, 14),
                           f"{name}@{i}: crater {ov} on landscape {lt}")
                    c.that(s8_valid(scale, sq), f"{name}@{i}: crater off map")
                    if ov <= 6:
                        c.that(lt in (4, 5), f"{name}@{i}: rock crater on {lt}")
                    else:
                        c.that(lt not in (4, 5),
                               f"{name}@{i}: sand crater on rock {lt}")
                if s8_valid(scale, sq):
                    c.that(s8_land(r, sq) >= 0, f"{name}@{i}: {sq} no landscape")
                if s8_flags(r, sq) & 0x20:
                    c.that(s8_land(r, sq) == 12,
                           f"{name}@{i}: structure on landscape "
                           f"{s8_land(r, sq)}")


@scenario("S8", "the radar with the map off: grey, the player's structures, "
                "house-coloured edges")
def s8_radar_off(c):
    for name in ("m1-0", "pw-DIPLOMATIC", "pw-ETERNALSUN", "pw-DEATHRULER"):
        st, _ = s8_start(name)
        d = s8_frames_vram(st, 2, every=70)
        for r, v in d[1:]:
            c.that(not r.u(S8_RADAR_ON, 1), f"{name}: the radar is on")
            for row in range(64):
                c.that(s8_vram_row(v, row) == s8_radar_row(r, row),
                       f"{name}: radar row {row}")


@scenario("S8", "control: a 32 x 32 radar read as a 64 x 64 one does not fit")
def s8_radar_control(c):
    st, _ = s8_start("m1-0")
    r, v = s8_frames_vram(st, 1, every=70)[1]
    mem = bytearray(r.mem)
    mem[S8_SMALL - 0xFF0000] = 0
    r.mem = bytes(mem)
    wrong = sum(s8_vram_row(v, row) != s8_radar_row(r, row) for row in range(64))
    c.that(wrong >= 4, f"only {wrong} rows differ")


@scenario("S8", "control: fog edges read with the neighbours W S E N do not fit")
def s8_edge_control(c):
    wrong = 0
    for name in S8_STARTS:
        _, r = s8_start(name)
        for sq in range(4096):
            if not s8_flags(r, sq) & 8:
                continue
            mask = 0
            for i, d in enumerate((-1, 64, 1, -64)):
                n = sq + d
                if not (0 <= n < 4096) or not (s8_flags(r, n) & 8):
                    mask |= 1 << i
            want = 0 if mask == 0 else s8_icon(7, mask)
            wrong += (s8_word(r, sq) >> 9) != want
    c.that(wrong > 20, f"only {wrong} edges misfit")
