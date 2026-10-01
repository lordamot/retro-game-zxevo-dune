#!/usr/bin/env python3
"""test_ui.py - the battle's controls (bank UI, S10) on the running machine:
B, the grid cursor while placing, the view shake and the low-credits
warning, against transcriptions of the cartridge's code.

    python3 tools/tests/test_ui.py [--build-dir build] [--only NAME]

Every scenario loads Atreides 1 through MAIN's start_mission (the
tools/dune_test.py mailbox), pokes records and the UI bank's own state,
and far-calls UI's routines.  What is checked is what the Mega Drive was
seen to do (bin/gen/retro-run on the same mission): B on the idle,
selected Construction Yard starts its item again and while it builds does
nothing; with its building finished B drops it; a unit's B goes back to
the structure selected before; the grid cursor snaps to the square it is
in and carries on to the grid; the warning's 90/900/60 frames.
"""
import argparse
import random as R
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
from dune_test import Machine, w16, s16          # noqa: E402

PG_UNITS, PG_WORLD, PG_MAP, PG_UI = 24, 25, 26, 16
STRUCTS, S_SIZE = 0x8100, 0x62
UNITS, U_SIZE = 0x4000, 0x8C
PAGES = (PG_WORLD, PG_UNITS, PG_UI)
YARD, WINDTRAP, PALACE, LIGHTF = 8, 9, 2, 3
TRIKE = 34                                  # Atreides 1: the player's Trike

UNFINISHED = []


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


def rand_between(seed, lo, hi):
    """math_rand_between $000C0C."""
    seed, d0 = rnd(seed)
    d3 = (hi - lo + 1) & 255
    d1 = 0xFF
    while d3 <= d0:
        d1 >>= 1
        d0 &= d1
        if d0 == 0:
            break
    return seed, (d0 + lo) & 255


class Rig:
    def __init__(self, bdir):
        self.m = Machine(build_dir=bdir)
        self.sym = self.m.sym
        self.m.poke_label("rnd_seed", bytes((0x12, 0x34, 0x56)))
        self.load = self.m.call("start_mission", a=1, bc=1 << 8, frames=120,
                                pages=PAGES)

    def a(self, label):
        return self.sym[label]

    def poke(self, label, data):
        """A WORLD variable or one of the UI bank's own."""
        a = self.a(label)
        if 0x8000 <= a < 0xC000:
            self.m.poke_page(PG_WORLD, a - 0x8000, bytes(data))
        else:
            self.m.poke_page(PG_UI, a, bytes(data))

    def poke_s(self, slot, off, data):
        self.m.poke_page(PG_WORLD, STRUCTS - 0x8000 + slot * S_SIZE + off, bytes(data))

    def call(self, label, frames=3, **kw):
        return self.m.call(label, frames=frames, pages=PAGES, **kw)

    def run(self):
        self.res = self.m.run()
        UNFINISHED.extend(s for s in range(self.m.steps)
                          if not self.res.regs(s)["done"])
        return self.res

    def var(self, step, label, n=1, signed=False):
        a = self.a(label)
        if 0x8000 <= a < 0xC000:
            b = self.res.page(step, PG_WORLD)[a - 0x8000:][:n]
        else:
            b = self.res.page(step, PG_UI)[a:][:n]
        v = int.from_bytes(b, "little")
        return v - (1 << 8 * n) if signed and v >> (8 * n - 1) else v

    def struct(self, step, slot):
        r = self.res.page(step, PG_WORLD)[STRUCTS - 0x8000 + slot * S_SIZE:][:S_SIZE]
        return dict(type=r[2], linked=r[3], flags=w16(r, 4), flags2=w16(r, 6),
                    house=r[8], state=s16(r, 0x5C), objtype=w16(r, 0x52))


def record(slot, stype, house, flags2=0):
    r = bytearray(S_SIZE)
    r[0], r[2], r[3], r[4] = slot, stype, 0xFF, 3
    r[6:8] = flags2.to_bytes(2, "little")
    r[8] = house
    r[0x0A:0x0E] = bytes((0x80, 40, 0x80, 40))
    r[0x12:0x14] = (200).to_bytes(2, "little")
    r[0x4C] = house
    return r


def t_b(bdir, out):
    """ui_battle_button $02838E, every branch."""
    rg = Rig(bdir)
    ok = bad = 0
    checks = []

    def sel(struct=0xFF, last=0xFF, unit=0xFF, own=0):
        rg.poke("struct_selected", [struct])
        rg.poke("struct_last", [last])
        rg.poke("unit_selected", [unit])
        rg.poke("struct_last_own", [own])

    # the idle Yard, selected: B starts its item again; B again, nothing
    sel(0, 0)
    s1 = rg.call("ui_press_b")
    s2 = rg.call("ui_press_b")
    # its building finished (flags2 bit 13): dropped
    rg.poke_s(0, 7, [0x20])
    sel(0, 0)
    s3 = rg.call("ui_press_b")
    rg.poke_s(0, 7, [0x00])
    # a unit selected, the Yard before it: back to the Yard
    sel(0xFF, 0, TRIKE)
    s4 = rg.call("ui_press_b")
    # another house's structure: the player's last one
    rg.poke_s(60, 0, record(60, WINDTRAP, 2))
    sel(60, 60)
    s5 = rg.call("ui_press_b")
    # a unit selected, another house's structure before it: the last own
    sel(0xFF, 60, TRIKE)
    s6 = rg.call("ui_press_b")
    # the player's Palace, weapon ready (flags2 bit 7): disarmed
    rg.poke_s(61, 0, record(61, PALACE, 1, 0x80))
    sel(61, 61)
    rg.poke("special_armed", [1])
    s7 = rg.call("ui_press_b")
    # an idle Light Factory with no room for what it makes (flags2 bit 8):
    # refused, nothing starts
    rg.poke_s(62, 0, record(62, LIGHTF, 1, 0x0100))
    rg.poke_s(62, 0x52, [13, 0])                # a Trike
    sel(62, 62)
    s8 = rg.call("ui_press_b")
    # the same with room: it starts
    rg.poke_s(62, 7, [0x00])
    sel(62, 62)
    s9 = rg.call("ui_press_b")
    # nothing selected: nothing
    sel()
    s10 = rg.call("ui_press_b")
    rg.run()

    y1, y2 = rg.struct(s1, 0), rg.struct(s2, 0)
    checks.append(("idle Yard starts", y1["state"] == 1 and y1["flags2"] & 0x4000
                   and y1["linked"] != 0xFF, y1))
    checks.append(("B while it builds: nothing", y2["linked"] == y1["linked"]
                   and y2["state"] == 1, y2))
    checks.append(("finished Yard dropped", rg.var(s3, "struct_selected") == 0xFF
                   and rg.var(s3, "struct_last") == 0xFF, rg.var(s3, "struct_selected")))
    checks.append(("unit: back to the Yard", rg.var(s4, "unit_selected") == 0xFF
                   and rg.var(s4, "struct_selected") == 0, rg.var(s4, "struct_selected")))
    checks.append(("enemy's: the last own", rg.var(s5, "struct_selected") == 0
                   and rg.var(s5, "struct_last") == 0, rg.var(s5, "struct_selected")))
    checks.append(("unit over an enemy's: the last own",
                   rg.var(s6, "struct_selected") == 0 and rg.var(s6, "unit_selected") == 0xFF,
                   rg.var(s6, "struct_selected")))
    checks.append(("Palace disarmed", rg.var(s7, "special_armed") == 0
                   and rg.var(s7, "struct_selected") == 61, rg.var(s7, "special_armed")))
    f8, f9 = rg.struct(s8, 62), rg.struct(s9, 62)
    checks.append(("no room: refused", f8["state"] == 0 and not f8["flags2"] & 0x4000, f8))
    checks.append(("room: the factory starts", f9["state"] == 1 and f9["flags2"] & 0x4000
                   and f9["linked"] != 0xFF, f9))
    checks.append(("nothing selected", rg.var(s10, "struct_selected") == 0xFF, None))
    for name, good, got in checks:
        if good:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}: {got}")
    return ok, bad


def markers_model(stype, selected, done, repairing, countdown, armed, noroom,
                  use, prod, before):
    """struct_animate's markers ($00DC98-$00DDA2) on the byte st_markers
    keeps: flags in bits 0-2 (0 bolt, 1 'OK', 2 hammer), the sprite's
    picture in bits 4-5 (1 + the flag that set it, 0 no sprite)."""
    def put(f):
        return (before & 0x0F) | (1 << f) | ((f + 1) << 4)

    def clear(f):
        return before & ~(1 << f) & 0x0F if before & (1 << f) else before

    if stype == YARD:
        if not selected and done:
            return put(1)
    elif stype == PALACE:
        if countdown == 0 and not armed and not noroom:
            return put(1)
    elif stype == WINDTRAP:
        if repairing:
            return before
        return put(0) if use > prod else clear(0)
    else:
        return before
    return put(2) if repairing else clear(1)


def t_markers(bdir, out):
    """The structure markers ('OK', the hammer, the bolt): struct_animate
    against markers_model, and the Yard's 'OK' after B puts its finished
    building back."""
    rg = Rig(bdir)
    ok = bad = 0
    mk = rg.a("st_markers") - 0x8000
    player = 0x7800 - 0x4000 + 1 * 0x46
    cases = []
    R.seed(5)
    # a finished Yard holds its building (linked): struct_check_build_choice
    # clears bits 13-14 of one that holds nothing
    rg.poke_s(63, 0, record(63, WINDTRAP, 1))
    rg.poke_s(0, 3, [63])
    for stype, slot in ((YARD, 0), (PALACE, 61), (WINDTRAP, 60)):
        for _ in range(12):
            c = dict(stype=stype, selected=R.random() < 0.3, done=R.random() < 0.5,
                     repairing=R.random() < 0.3, countdown=R.choice((0, 0, 30)),
                     armed=R.random() < 0.3, noroom=False,
                     use=R.randrange(0, 60), prod=R.randrange(0, 60),
                     before=R.choice((0, 0x22, 0x34, 0x11, 0x36, 0x26)))
            if slot:
                rg.poke_s(slot, 0, record(slot, stype, 1))
            rg.poke_s(slot, 4, [3, 0x20 if c["repairing"] else 0])
            rg.poke_s(slot, 7, [0x20 if c["done"] else 0])
            rg.poke_s(slot, 0x56, c["countdown"].to_bytes(2, "little"))
            rg.poke("struct_selected", [slot if c["selected"] else 0xFF])
            rg.poke("special_armed", [1 if c["armed"] else 0])
            rg.m.poke_page(PG_UNITS, player + 0x1A,
                           c["prod"].to_bytes(2, "little") + c["use"].to_bytes(2, "little"))
            rg.m.poke_page(PG_WORLD, mk + slot, [c["before"]])
            ix = STRUCTS + slot * S_SIZE
            cases.append((slot, c, rg.call("st_struct_animate", ix=ix)))
    # the game's own way: the Yard's building finished and it selected
    # (placing), B puts it back, and the next pass shows 'OK'
    rg.poke_s(0, 4, [3, 0])
    rg.poke_s(0, 7, [0x20])
    rg.m.poke_page(PG_WORLD, mk, [0])
    rg.poke("struct_selected", [0])
    rg.poke("struct_last", [0])
    rg.poke("unit_selected", [0xFF])
    y1 = rg.call("st_struct_animate", ix=STRUCTS)
    rg.call("ui_press_b")
    y2 = rg.call("st_struct_animate", ix=STRUCTS)
    rg.run()
    for slot, c, step in cases:
        got = rg.res.page(step, PG_WORLD)[mk + slot]
        want = markers_model(**c)
        if got == want:
            ok += 1
        else:
            bad += 1
            out.append(f"  slot {slot} {c}: {got:02X}, want {want:02X}")
    for name, step, want in (("placing: no 'OK'", y1, 0x00),
                             ("B, then 'OK'", y2, 0x22)):
        got = rg.res.page(step, PG_WORLD)[mk]
        if got == want:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}: {got:02X}, want {want:02X}")
    return ok, bad


def t_grid(bdir, out):
    """The grid cursor ($004CBE, $00617A-$006462): the snap, the carry to
    the grid, and the square under it (+16)."""
    rg = Rig(bdir)
    rg.poke("view_x", (640).to_bytes(2, "little"))
    rg.poke("view_y", (1024).to_bytes(2, "little"))
    rg.poke_s(0, 7, [0x20])                     # the Yard's building is done
    rg.poke_s(0, 0x52, [WINDTRAP, 0])           # a 2 x 2
    rg.poke("struct_selected", [0])
    rg.poke("cursor_grid", [0])
    rg.poke("cursor_x", (150).to_bytes(2, "little"))
    rg.poke("cursor_y", (170).to_bytes(2, "little"))
    rg.poke("frames_this_pass", (4).to_bytes(2, "little"))
    s1 = rg.call("ui_battle_input")
    # off the grid, last gone right: it carries on to the next line
    rg.poke("cursor_x", (133).to_bytes(2, "little"))
    rg.poke("cursor_dirs", [0x08])
    carry = [rg.call("ui_battle_input") for _ in range(10)]
    # off the grid, last gone up
    rg.poke("cursor_y", (135).to_bytes(2, "little"))
    rg.poke("cursor_dirs", [0x01])
    up = [rg.call("ui_battle_input") for _ in range(4)]
    # off the grid with no way to go (a poke): the square it is in
    rg.poke("cursor_x", (150).to_bytes(2, "little"))
    rg.poke("cursor_dirs", [0x00])
    s3 = rg.call("ui_battle_input")
    # the building placed elsewhere: the free cursor again, where it is
    rg.poke_s(0, 7, [0x00])
    rg.poke("cursor_x", (150).to_bytes(2, "little"))
    s4 = rg.call("ui_battle_input")
    rg.run()
    ok = bad = 0
    xs = [rg.var(s, "cursor_x", 2) for s in carry]
    ys = [rg.var(s, "cursor_y", 2) for s in up]
    checks = [
        ("grid on", rg.var(s1, "cursor_grid") == 1 and rg.var(s1, "place_active") == 1),
        ("snapped to 128,160", (rg.var(s1, "cursor_x", 2), rg.var(s1, "cursor_y", 2)) == (128, 160)),
        ("square +16: 24,37", rg.var(s1, "place_sq", 2) == 37 * 64 + 24),
        ("carries right to 160, no further", xs[-1] == 160 and max(xs) == 160
         and all(a <= b for a, b in zip(xs, xs[1:]))),
        ("carries up to 128", ys[-1] == 128 and min(ys) == 128),
        ("at rest: the square it is in", rg.var(s3, "cursor_x", 2) == 128),
        ("free again", rg.var(s4, "cursor_grid") == 0 and rg.var(s4, "cursor_x", 2) == 150),
    ]
    for name, good in checks:
        if good:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}: x {xs} y {ys} s1 {rg.var(s1, 'cursor_x', 2)},"
                       f"{rg.var(s1, 'cursor_y', 2)} sq {rg.var(s1, 'place_sq', 2):04X}")
    return ok, bad


def t_warning(bdir, out):
    """ui_warning_blink $0099A8 and the sprite's blink (spr_render
    $0010B8) against a transcription, over 1500 frames in passes of 1-4."""
    rg = Rig(bdir)
    steps = []
    # not armed (a mission begun under 50 credits): 1 does nothing
    rg.poke("warn_armed", [0])
    rg.poke("warn_shown", [0])
    rg.poke("frames_this_pass", (3).to_bytes(2, "little"))
    s0 = rg.call("ui_warning_blink", a=1)
    rg.call("ui_warning_blink", a=0)
    passes = [(1 + (k * 7) % 4) for k in range(420)]
    for f in passes:
        rg.poke("frames_this_pass", f.to_bytes(2, "little"))
        rg.call("ui_warning_blink", a=1, frames=1)
        steps.append(rg.call("uwb_frame", frames=1))
    rg.run()
    ok = bad = 0
    if rg.var(s0, "warn_shown") == 0 and rg.var(s0, "warn_armed") == 0:
        ok += 1
    else:
        bad += 1
        out.append("  unarmed: it came on")
    t1, t2, shown, blink = 90, 0, 0, 0
    for f, s in zip(passes, steps):
        if t2 >= 0:
            t2 -= f
        else:
            t1 -= f
            if t1 >= 0:
                shown = 1
            else:
                t2, t1, shown = 900, 60, 0
        drawn = 0
        if shown:
            for _ in range(min(f, 18)):
                if blink:
                    blink -= 1
                    drawn = 1
                else:
                    blink, drawn = 8, 0
        got = (rg.var(s, "warn_t1", 2, True), rg.var(s, "warn_t2", 2, True),
               rg.var(s, "warn_shown"), rg.var(s, "crd_low"))
        if got == (t1, t2, shown, drawn):
            ok += 1
        else:
            bad += 1
            if bad <= 4:
                out.append(f"  got {got} expected {(t1, t2, shown, drawn)}")
    return ok, bad


def t_shake(bdir, out):
    """view_shake_start $005DCC and view_shake_frame $005E26: the walk
    drawn from the game's random numbers, two a frame, and the end."""
    rg = Rig(bdir)
    rg.poke("ubi_frames", [3])
    s0 = rg.call("view_shake_start", a=16)
    steps = [rg.call("view_shake_frame") for _ in range(8)]
    # C held: none starts; C held while it shakes: it stops at once
    rg.m.lines.append("hold x")
    rg.m.run_frames(3)
    c1 = rg.call("view_shake_start", a=16)
    rg.m.lines.append("release")
    rg.m.run_frames(3)
    rg.call("view_shake_start", a=16)
    rg.m.lines.append("hold x")
    rg.m.run_frames(3)
    c2 = rg.call("view_shake_frame")
    rg.m.lines.append("release")
    rg.run()
    ok = bad = 0
    for name, s, good in (("C held: no shake", c1, rg.var(c1, "shake_on") == 0),
                          ("C held: it stops", c2, rg.var(c2, "shake_on") == 0
                           and rg.var(c2, "shake_frames", 2) == 0
                           and not rg.res.regs(c2)["f"] & 0x40)):
        if good:
            ok += 1
        else:
            bad += 1
            out.append(f"  {name}")
    seed = tuple(rg.res.page(s0, PG_WORLD)[rg.a("rnd_seed") - 0x8000:][:3])
    frames, ox, oy, on = 16, 0, 0, True
    for s in steps:
        was_on = on
        for _ in range(3 if on else 0):
            if frames <= 0:
                on, ox, oy = False, 0, 0
                break
            frames -= 1
            for axis in (0, 1):
                seed, r = rand_between(seed, 0, 4)
                o = ox if axis == 0 else oy
                o = o + r if -4 <= o + r - 2 <= 4 else o - r
                if axis == 0:
                    ox = o
                else:
                    oy = o
        got = (rg.var(s, "shake_on"), rg.var(s, "shake_ox", 1, True),
               rg.var(s, "shake_oy", 1, True), rg.var(s, "shake_frames", 2))
        exp = (1 if on else 0, ox, oy, frames if on else 0)
        z = bool(rg.res.regs(s)["f"] & 0x40)
        if got == exp and z != was_on:
            ok += 1
        else:
            bad += 1
            out.append(f"  got {got} Z {z} expected {exp}, Z {not was_on}")
    return ok, bad


def t_order(bdir, out):
    """A with the Trike selected, on an Ordos soldier's square
    ($027F00-$028190): Attack where it can be seen, Move where the fog's
    pattern hides it (map_square_pattern $004590)."""
    first = Rig(bdir)
    first.run()
    u = first.res.page(first.load, PG_UNITS)
    enemy = next(n for n in range(102)
                 if u[n * U_SIZE + 4] & 1 and u[n * U_SIZE + 8] == 2
                 and u[n * U_SIZE + 2] == 4)
    r = u[enemy * U_SIZE:][:U_SIZE]
    sx, sy = r[0x0D], r[0x0B]
    sq = sy * 64 + sx
    vx, vy = sx * 32 - 160, sy * 32 - 96
    cases = []
    rg = Rig(bdir)
    for overlay, order in ((0, 0), (0x6C, 1), (0x6D, 0), (0x7B, 1)):
        hi = rg.m
        rg.poke("view_x", vx.to_bytes(2, "little"))
        rg.poke("view_y", vy.to_bytes(2, "little"))
        rg.poke("cursor_x", (176).to_bytes(2, "little"))
        rg.poke("cursor_y", (112).to_bytes(2, "little"))
        rg.poke("unit_selected", [TRIKE])
        rg.poke("struct_selected", [0xFF])
        hi.poke_page(PG_MAP, 0xD000 - 0xC000 + sq, [overlay << 1])
        rg.m.poke_page(PG_UNITS, TRIKE * U_SIZE + 0x54, [0xFF])
        cases.append((overlay, order, rg.call("ui_press_a")))
    rg.run()
    ok = bad = 0
    for overlay, order, s in cases:
        got = rg.res.page(s, PG_UNITS)[TRIKE * U_SIZE + 0x54]
        if got == order:
            ok += 1
        else:
            bad += 1
            out.append(f"  overlay ${overlay:02X} on unit {enemy} at {sx},{sy}: order {got}, "
                       f"expected {order}")
    return ok, bad


PG_RENDER = 9                               # bank RENDER, at $0000


def cursor_pick(unit, struct, armed, player):
    """ui_battle_button with no button ($028596-$0287C6): the pointer's
    frame and the unit bracket's (0 for none) by the selection.  unit and
    struct are (used, type, house, flags2) or None."""
    if unit:
        used, utype, house, _ = unit
        if not used:
            return 330, 0
        if house == player and utype != 6:  # not a Saboteur
            return 331, 332
        return 330, 333
    if struct:
        used, stype, house, f2 = struct
        if (used and stype == PALACE and house == player and armed
                and f2 & 0x80 and not f2 & 0x100):
            return 331, 0
    return 330, 0


def t_cursor(bdir, out):
    """The two cursor sprites by the selection (rph_pick, $028596 on):
    every branch, with the Trike, an Ordos unit, a Saboteur, a unit not in
    use, the Palace armed and not, another house's Palace and the Yard."""
    first = Rig(bdir)
    first.run()
    u = first.res.page(first.load, PG_UNITS)
    enemy = next(n for n in range(102)
                 if u[n * U_SIZE + 4] & 1 and u[n * U_SIZE + 8] == 2)
    free = next(n for n in range(102) if not u[n * U_SIZE + 4] & 1)
    player = 1
    rg = Rig(bdir)
    pages = PAGES + (PG_RENDER,)
    sym = rg.sym
    cases = []

    def unit_case(n, utype=None):
        r = u[n * U_SIZE:][:U_SIZE]
        t = r[2] if utype is None else utype
        rg.m.poke_page(PG_UNITS, n * U_SIZE + 2, [t])
        rg.poke("unit_selected", [n])
        rg.poke("struct_selected", [0xFF])
        s = rg.m.call("rph_pick", frames=2, pages=pages)
        rg.m.poke_page(PG_UNITS, n * U_SIZE + 2, [r[2]])
        cases.append(((r[4] & 1, t, r[8], w16(r, 6)), None, 0, s))

    unit_case(TRIKE)
    unit_case(TRIKE, 6)
    unit_case(enemy)
    unit_case(free)
    slot = 40
    for stype, house, f2, armed in (
            (PALACE, 1, 0x80, 1), (PALACE, 1, 0x80, 0), (PALACE, 1, 0, 1),
            (PALACE, 1, 0x180, 1), (PALACE, 2, 0x80, 1), (YARD, 1, 0x80, 1)):
        rg.poke_s(slot, 0, record(slot, stype, house, f2))
        rg.poke("unit_selected", [0xFF])
        rg.poke("struct_selected", [slot])
        rg.poke("special_armed", [armed])
        s = rg.m.call("rph_pick", frames=2, pages=pages)
        cases.append((None, (1, stype, house, f2), armed, s))
    rg.poke("struct_selected", [0xFF])
    cases.append((None, None, 0, rg.m.call("rph_pick", frames=2, pages=pages)))
    rg.run()
    ok = bad = 0
    for unit, struct, armed, s in cases:
        pg = rg.res.page(s, PG_RENDER)
        got = (w16(pg, sym["rph_pointer"]), w16(pg, sym["rph_bracket"]))
        want = cursor_pick(unit, struct, armed, player)
        if got == want:
            ok += 1
        else:
            bad += 1
            out.append(f"  unit {unit} structure {struct} armed {armed}: "
                       f"{got}, expected {want}")
    return ok, bad


def t_blink(bdir, out):
    """The bracket's blink (spr_render $0010B8 on the sprite cursor_create
    $004AFA makes: period 10, bit 3), transcribed frame by frame, against
    rph_blink over passes of 1-4 frames, with the selection dropped for a
    while: the count stands still then."""
    rg = Rig(bdir)
    pages = PAGES + (PG_RENDER,)
    fc = 5000
    rg.poke("frame_count", fc.to_bytes(2, "little"))
    rg.poke("unit_selected", [0xFF])       # nothing selected: only the
    rg.poke("struct_selected", [0xFF])     # frame is noted
    rg.m.call("rph_blink", frames=1, pages=pages)
    # the sprite as the Mega Drive keeps it: +4 count, +5 period, bit 4
    cnt, per, ph4 = 0, 10, 0
    steps = []
    for k in range(300):
        f = 1 + (k * 5) % 4
        sel = not (120 <= k < 150)
        hidden = None
        for _ in range(f):
            if not sel:
                continue
            if not ph4:
                if cnt:
                    cnt -= 1
                    hidden = 0
                else:
                    cnt, hidden, ph4 = per, 1, 1
            else:
                if cnt:
                    cnt -= 1
                    hidden = 1
                else:
                    cnt, hidden, ph4 = per, 0, 0
        fc += f
        rg.poke("frame_count", (fc & 0xFFFF).to_bytes(2, "little"))
        rg.poke("unit_selected", [TRIKE if sel else 0xFF])
        s = rg.m.call("rph_blink", frames=1, pages=pages)
        if sel:
            steps.append((k, hidden, s))
    rg.run()
    ok = bad = 0
    for k, hidden, s in steps:
        got = rg.res.page(s, PG_RENDER)[rg.sym["rph_hidden"]]
        if got == hidden:
            ok += 1
        else:
            bad += 1
            if bad <= 4:
                out.append(f"  pass {k}: hidden {got}, expected {hidden}")
    return ok, bad


def t_view_move(bdir, out):
    """view_move: the pixels a pass earns move the view along each held
    axis in whole cells, what is left of a cell carried to the next pass
    and dropped on an axis that stops.  Random passes from the middle of
    Atreides 1's playable area (no clamping), against a model."""
    rg = Rig(bdir)
    pages = PAGES
    R.seed(7)
    L, Rt, U, D = 1 << 2, 1 << 3, 1 << 0, 1 << 1
    x, y = 864, 1024                        # 512-1216 across is playable
    rg.poke("view_x", x.to_bytes(2, "little"))
    rg.poke("view_y", y.to_bytes(2, "little"))
    rg.poke("ubv_frac", [0, 0])
    fx = fy = 0
    steps = []
    for k in range(60):
        px = R.choice((0, 3, 5, 7, 12, 14, 21, 24, 49, 56, 112))
        dirs = R.choice((0, L, Rt, U, D, L | U, Rt | D, L | D, Rt | U))
        if abs(x - 864) > 150:              # back towards the middle
            dirs = dirs & ~(L | Rt) | (L if x > 864 else Rt)
        if abs(y - 1024) > 100:
            dirs = dirs & ~(U | D) | (U if y > 1024 else D)
        s = rg.m.call("view_move", a=px, bc=dirs, frames=1, pages=pages)
        for axis in (0, 1):
            neg, pos = (L, Rt) if axis == 0 else (U, D)
            v = -px if dirs & neg else px if dirs & pos else 0
            f = fx if axis == 0 else fy
            if v == 0:
                f, move = 0, 0
            else:
                tot = f + v
                move = (abs(tot) & ~7) * (1 if tot >= 0 else -1)
                f = tot - move
            if axis == 0:
                fx, x = f, x + move
            else:
                fy, y = f, y + move
        steps.append((k, s, x, y, fx, fy))
    rg.run()
    ok = bad = 0
    for k, s, ex, ey, efx, efy in steps:
        got = (rg.var(s, "view_x", 2), rg.var(s, "view_y", 2),
               rg.var(s, "ubv_frac", 1, True),
               int.from_bytes(bytes([rg.res.page(s, PG_UI)[rg.a("ubv_frac") + 1]]),
                              "little", signed=True))
        if got == (ex, ey, efx, efy):
            ok += 1
        else:
            bad += 1
            if bad <= 4:
                out.append(f"  pass {k}: got {got}, expected {(ex, ey, efx, efy)}")
    return ok, bad


def t_resync(bdir, out):
    """ui_time_resync after the options screen or a panel (time_resync
    $004764 at $02156A, $0289F6, $028D5E): the next pass counts from now,
    and the music's countdown is charged the frames spent there
    ($028A02-$028A04)."""
    R.seed(21)
    rg = Rig(bdir)
    cases = []
    for _ in range(12):
        seen = R.randrange(65536)
        spent = R.choice([0, 1, 7, 150, 3000, R.randrange(20000)])
        music = R.choice([0xFFFF, 0, 5, 7000, R.randrange(65536)])
        rg.poke("frame_seen", seen.to_bytes(2, "little"))
        rg.poke("frame_count", ((seen + spent) & 0xFFFF).to_bytes(2, "little"))
        rg.poke("music_frames_left", music.to_bytes(2, "little"))
        cases.append((seen, spent, music, rg.call("ui_time_resync")))
    rg.run()
    ok = bad = 0
    for seen, spent, music, s in cases:
        # the frame counter runs on between the poke and the call: the new
        # frame_seen is a frame or two past it, and the music is charged
        # exactly what lies between the old and the new
        now = rg.var(s, "frame_seen", 2)
        late = (now - seen - spent) & 0xFFFF
        taken = (now - seen) & 0xFFFF
        got = (late <= 3, rg.var(s, "music_frames_left", 2))
        want = (True, (music - taken) & 0xFFFF)
        if got == want:
            ok += 1
        else:
            bad += 1
            out.append(f"  seen {seen} spent {spent} music {music}: {got}, expected {want}")
    return ok, bad


# ------------------------------------------------ the side panel's lower half
#
# ui_draw_selection_panel $0294BE transcribed: what the lower picture, the
# second bar and the label become for a selection, from the cartridge's own
# tables.  The panel's state carries over from one call to the next as its
# sprites do (a branch may leave one as it was), so the cases run in order.

ROM = (ROOT / "orig/dune2.gen").read_bytes()
NONE = 0xFFFF
HOUSES, H_SIZE = 0x3800, 0x46               # page UNITS
PLAYER, ENEMY = 1, 2
SLOT, LINK_S, LINK_U = 60, 61, 90           # the structure, what it holds


def rw(a):
    return int.from_bytes(ROM[a:a + 2], "big")


def rl(a):
    return int.from_bytes(ROM[a:a + 4], "big")


def sx(v, bits=16):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


S_INFO = [rl(0x06B94C + 4 * t) for t in range(19)]
U_INFO = [rl(0x06C5B4 + 4 * t) for t in range(27)]


def s_anim(t):
    return rw(S_INFO[t] + 0x14)


def u_anim(t):
    return rw(U_INFO[t] + 0x14)


def makes(t):                               # the type's +$0C bit 1
    return rw(S_INFO[t] + 0x0C) & 2


class Panel:
    """The sprites $FFC73C (picture), $FFC740 (bar, cache $FFC742) and the
    label ($FFC724), as frame numbers."""

    def __init__(self, sym):
        self.sym = sym
        self.anim = {s_anim(t): sym["HUD_STRUCT"] + t for t in range(19)}
        self.anim.update({u_anim(t): sym["HUD_UNIT"] + t
                          for t in range(27) if u_anim(t)})
        self.anim[0x40] = sym["HUD_STRUCT"] + 19        # the spanner
        self.anim[0x5E] = sym["HUD_FREMEN"]
        self.pic2 = self.bar2 = NONE
        self.y, self.label, self.cache = 112, 0, None

    def pic(self, anim):                    # ui_picture2_show $009942
        if sx(anim) > 0:
            self.pic2 = self.anim[anim]

    def bar_hide(self):                     # $009BB4
        self.bar2, self.cache = NONE, None

    def pb_hide(self):                      # $009BAA
        self.pic2 = NONE
        self.bar_hide()

    def bar(self, cur, full, y, pen):       # $009862
        cur, full = sx(cur), sx(full)
        if cur <= 0:
            return self.bar_hide()
        if full <= 0 or (cur, full) == self.cache:
            return
        self.cache, self.y = (cur, full), y
        q, r = divmod((min(cur, full) << 5) & 0xFFFF, full)
        if r == 0:
            q -= 1
        base = self.sym["HUD_BAR_PEN7" if pen == 7 else "HUD_BAR_PEN3"]
        self.bar2 = base + (((q & 31) + 4) >> 2)

    def structure(self, s, h, air, linked_s, linked_u):
        """s, h: the structure's and its house's fields (s is changed as the
        cartridge changes it)."""
        t = s["type"]
        if not s["used"] or s["house"] != PLAYER:
            self.label = 0
            return self.pb_hide()
        if s["flags2"] & 2:                                     # upgrading
            self.pic(0x40)
            self.bar(sx(-s["upg"], 8) + 100, 100, 112, 7)
            if not s["flags2"] & 0x100:
                self.label = 0
            return
        if s["creator"] != PLAYER:                              # captured
            if s["linked"] & 0x80 or not makes(t):
                s["linked"] = 0xFF
            else:
                s["obj"] = (linked_s if t == 8 else linked_u)["type"]
        obj = sx(s["obj"])
        if t == 8:
            self.label = int(bool(s["flags2"] & 0x100) and obj not in (1, 14))
        else:
            self.label = int((t != 11 and bool(s["flags2"] & 0x100))
                             or (t == 5 and not air))
        if t == 11:                                             # Starport
            self.pb_hide()
            if sx(h["link"]) > -1:
                d3 = rw(0x06C750 + 30 * s["house"] + 0x10)
                self.bar(d3 - h["time"], d3, 80, 7)
            return
        if makes(t):
            if obj >= 0:
                self.pic(s_anim(obj) if t == 8 else u_anim(obj))
            if not s["flags2"] & 0x4000:
                return self.bar_hide()
            if (s["linked"] != 0xFF and not s["flags"] & 0x4000
                    and s["count"] == 0):                       # $012144
                s["flags2"] = s["flags2"] & ~0x4000 | 0x2000
            d3 = rw((S_INFO if t == 8 else U_INFO)[obj] + 0x18)
            return self.bar(d3 - (s["count"] >> 8), d3, 112, 7)
        if t == 13 and not s["linked"] & 0x80:                  # Repair
            self.pic(u_anim(linked_u["type"]))
            return self.bar(linked_u["time"] - s["count"], linked_u["time"], 112, 7)
        if t == 2:                                              # Palace
            self.pic(0x5E if s["house"] == 1 else u_anim(obj))
            if s["delay"]:
                self.label = 1
                return self.bar_hide()
            self.label = 0
            d3 = rw(0x06C750 + 30 * s["house"] + 0x0E)
            if not s["count"]:
                return self.bar_hide()
            return self.bar(d3 - s["count"], d3, 112, 7)
        self.pic2 = NONE
        if t == 9:                                              # Windtrap
            return self.bar(h["use"] or 1, h["prod"], 80, 7)
        if t in (12, 17):                                       # the spice
            d3, d4 = h["credits"], h["storage"]
            while d4 > 0x7FF:
                d3, d4 = d3 >> 1, d4 >> 1
            return self.bar(d3 or 1, d4, 80, 3)
        return self.bar_hide()

    def unit(self, u):
        self.label = 0
        if not u["used"] or not u["hp"] or u["type"] != 16:
            return self.pb_hide()
        self.bar(sx(u["amount"], 8), 100, 80, 3)

    def nothing(self):
        self.label = 0
        self.pb_hide()


def sidebar_cases(n):
    """A seeded mix of selections: mostly the player's structures of every
    type, with the flags and fields each branch reads."""
    R.seed(294)
    out = []
    kinds = [2, 3, 4, 5, 7, 8, 8, 9, 10, 11, 12, 13, 13, 17, 2, 0, 6, 15, 18]
    for _ in range(n):
        r = R.random()
        if r < 0.06:
            out.append(("none", None))
            continue
        if r < 0.2:
            out.append(("unit", dict(
                slot=R.choice([TRIKE, TRIKE, 25]), used=R.random() < 0.9,
                type=R.choice([16, 16, 16, 13, 4]),
                hp=R.choice([0, 100, 150, 150]),
                amount=R.choice([0, 1, 50, 99, 100, 101, 127, 128, 200, 255]))))
            continue
        t = R.choice(kinds)
        f2 = 0x8000
        f2 |= 2 if R.random() < 0.15 else 0
        f2 |= 0x100 if R.random() < 0.35 else 0
        f2 |= 0x2000 if R.random() < 0.2 else 0
        top = 19 if t == 8 else 27
        obj = R.choice([R.randrange(top), R.randrange(top), 1, 14, 16, 0xFFFF])
        if t == 2:
            obj = R.choice([3, 6, 18, 20])
        if obj != 0xFFFF and obj < top:
            f2 |= 0x4000 if R.random() < 0.5 else 0
        count = R.choice([0, 0, 0, 1, 0xFF, 0x100, 0x240, 0x0C00, 0x2400, R.randrange(0x3000)])
        if t == 2:
            count = R.choice([0, 1, 25, 49, 50, 124, 399, 400, 401])
        s = dict(type=t, used=R.random() < 0.95,
                 house=PLAYER if R.random() < 0.85 else ENEMY,
                 flags=0x0003 | (0x4000 if R.random() < 0.2 else 0),
                 flags2=f2, linked=R.choice([0xFF, 0xFF, LINK_S if t == 8 else LINK_U, 0x85]),
                 creator=PLAYER if R.random() < 0.8 else ENEMY,
                 delay=R.choice([0, 0, 0, 1, 300]), obj=obj,
                 upg=R.choice([0, 10, 50, 90, 100, 128, 200, 246]), count=count)
        h = dict(prod=R.choice([0, 100, 250, 3000]), use=R.choice([0, 30, 100, 400]),
                 credits=R.choice([0, 1, 990, 5000, 70000, 3000000]),
                 storage=R.choice([0, 1000, 1005, 4000, 80000, 2500000]),
                 time=R.choice([0, 3, 9, 10, 12]), link=R.choice([0xFFFF, 0, 41]))
        ls = dict(type=R.randrange(19))
        lu = dict(type=R.randrange(27), time=R.choice([1, 12, 300, 700]))
        out.append(("struct", (s, h, R.choice([0, 1]), ls, lu)))
    return out


def t_sidebar(bdir, out):
    """ui_selection_panel against the transcription of $0294BE: the lower
    picture, the second bar (frame and y), the label, and what it changes
    in the structure (+$52 of a captured factory, a finished production's
    flags2, a captured non-factory's linkedID)."""
    rg = Rig(bdir)
    cases = sidebar_cases(400)
    steps = []
    rg.poke("unit_selected", [0xFF])
    rg.poke("struct_selected", [0xFF])
    first = rg.call("ui_selection_panel")
    for kind, c in cases:
        if kind == "none":
            rg.poke("unit_selected", [0xFF])
            rg.poke("struct_selected", [0xFF])
        elif kind == "unit":
            u = c
            base = u["slot"] * U_SIZE
            rg.m.poke_page(PG_UNITS, base + 2, [u["type"]])
            rg.m.poke_page(PG_UNITS, base + 4, [3 if u["used"] else 2])
            rg.m.poke_page(PG_UNITS, base + 0x12, u["hp"].to_bytes(2, "little"))
            rg.m.poke_page(PG_UNITS, base + 0x5E, [u["amount"]])
            rg.poke("struct_selected", [0xFF])
            rg.poke("unit_selected", [u["slot"]])
        else:
            s, h, air, ls, lu = c
            r = bytearray(S_SIZE)
            r[0], r[2], r[3] = SLOT, s["type"], s["linked"]
            r[4:6] = (s["flags"] if s["used"] else 2).to_bytes(2, "little")
            r[6:8] = s["flags2"].to_bytes(2, "little")
            r[8] = s["house"]
            r[0x0A:0x0E] = bytes((0x80, 40, 0x80, 40))
            r[0x12:0x14] = (200).to_bytes(2, "little")
            r[0x4C] = s["creator"]
            r[0x4E:0x50] = s["delay"].to_bytes(2, "little")
            r[0x52:0x54] = s["obj"].to_bytes(2, "little")
            r[0x55] = s["upg"]
            r[0x56:0x58] = s["count"].to_bytes(2, "little")
            rg.poke_s(SLOT, 0, r)
            rg.poke_s(LINK_S, 2, [ls["type"]])
            rg.m.poke_page(PG_UNITS, LINK_U * U_SIZE + 2, [lu["type"]])
            rg.m.poke_page(PG_UNITS, LINK_U * U_SIZE + 0x5A, lu["time"].to_bytes(2, "little"))
            hb = HOUSES + s["house"] * H_SIZE
            rg.m.poke_page(PG_UNITS, hb + 0x12, h["credits"].to_bytes(4, "little"))
            rg.m.poke_page(PG_UNITS, hb + 0x16, h["storage"].to_bytes(4, "little"))
            rg.m.poke_page(PG_UNITS, hb + 0x1A, h["prod"].to_bytes(2, "little"))
            rg.m.poke_page(PG_UNITS, hb + 0x1C, h["use"].to_bytes(2, "little"))
            rg.m.poke_page(PG_UNITS, hb + 0x2E, h["time"].to_bytes(2, "little"))
            rg.m.poke_page(PG_UNITS, hb + 0x30, h["link"].to_bytes(2, "little"))
            rg.poke("air_slot_free", [air])
            rg.poke("unit_selected", [0xFF])
            rg.poke("struct_selected", [SLOT])
        steps.append(rg.call("ui_selection_panel"))
    rg.run()
    P = Panel(rg.sym)
    P.nothing()
    ok = bad = 0
    seen = set()

    def got(step):
        return (rg.var(step, "panel_pic2", 2), rg.var(step, "panel_bar2", 2),
                rg.var(step, "panel_bar2_y", 2), rg.var(step, "panel_label"))

    if got(first) != (NONE, NONE, 112, 0) and got(first)[:2] != (NONE, NONE):
        bad += 1
        out.append(f"  nothing selected: {got(first)}")
    for (kind, c), step in zip(cases, steps):
        extra = want_extra = ()
        if kind == "none":
            P.nothing()
        elif kind == "unit":
            P.unit(c)
        else:
            s, h, air, ls, lu = c
            s = dict(s)
            P.structure(s, h, air, ls, lu)
            rec = rg.res.page(step, PG_WORLD)[STRUCTS - 0x8000 + SLOT * S_SIZE:][:S_SIZE]
            extra = (w16(rec, 0x52), w16(rec, 6), rec[3])
            want_extra = (s["obj"], s["flags2"], s["linked"])
        want = (P.pic2, P.bar2, P.y if P.bar2 != NONE else None, P.label)
        g = got(step)
        g = (g[0], g[1], g[2] if g[1] != NONE else None, g[3])
        if g == want and extra == want_extra:
            ok += 1
            if kind == "struct":
                seen.add((c[0]["type"], P.bar2 != NONE, P.label))
        else:
            bad += 1
            if bad <= 6:
                out.append(f"  {kind} {c if kind != 'struct' else c[0]}: got {g} {extra}, "
                           f"expected {want} {want_extra}")
            # carry on from what the machine did
            P.pic2, P.bar2, P.label = g[0], g[1], g[3]
            P.cache = None if g[1] == NONE else P.cache
    # every branch was reached
    types = {t for t, _, _ in seen}
    for t in (2, 3, 5, 8, 9, 11, 12, 13, 17):
        if t not in types:
            bad += 1
            out.append(f"  no case of structure type {t} passed")
    if not any(b for t, b, _ in seen if t == 8) or not any(lab for _, _, lab in seen):
        bad += 1
        out.append("  no Yard with a bar, or no label, among the cases")
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    b = args.build_dir
    tests = [
        ("B", lambda o: t_b(b, o)),
        ("markers", lambda o: t_markers(b, o)),
        ("grid cursor", lambda o: t_grid(b, o)),
        ("warning", lambda o: t_warning(b, o)),
        ("shake", lambda o: t_shake(b, o)),
        ("order", lambda o: t_order(b, o)),
        ("cursor", lambda o: t_cursor(b, o)),
        ("blink", lambda o: t_blink(b, o)),
        ("resync", lambda o: t_resync(b, o)),
        ("view move", lambda o: t_view_move(b, o)),
        ("sidebar", lambda o: t_sidebar(b, o)),
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
        print(f"{name:12s} {ok}/{ok + bad}")
        for line in out:
            print(line)
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
