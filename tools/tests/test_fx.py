#!/usr/bin/env python3
"""test_fx.py - the effect animations on units (bank MOVE2: fx_anim_start
$00A74E, fx_anim_tick $00A786, and what starts and ends them) on the
running machine.

    python3 tools/tests/test_fx.py [--build-dir build] [--only NAME]

Every scenario loads Atreides 1 through MAIN's start_mission (the
tools/dune_test.py mailbox), turns one of the player's Trikes into the
unit it needs, and far-calls MOVE2's routines and the unit loop.  What is
checked is what the Mega Drive was seen to do (bin/gen/retro-run, the
MCV and the Trike of the same mission): an MCV told to deploy on its own
square gets Stop, flags2 bit 7 and an animation of 255 frames blinking
every 8 with sound $2E, and becomes a Construction Yard when it runs out;
the target of an attack gets flags2 bit 11 and 24 frames blinking every 6
with sound $24; a new order stops a deploy.  The blink is checked against
a model of the sprite engine's counter (spr_render $0010D8).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
from dune_test import Machine, w16, s16          # noqa: E402

PG_UNITS, PG_WORLD, PG_MAP = 24, 25, 26
UNITS, U_SIZE = 0x4000, 0x8C
STRUCTS, S_SIZE = 0x8100, 0x62
ATTACK, MOVE, GUARD, STOP, DIE, DEPLOY = 0, 1, 3, 7, 10, 12
MCV, DEVASTATOR, HARVESTER, CONSTYARD = 17, 11, 16, 8
TRIKE_A, TRIKE_B, ENEMY = 34, 38, 35    # Atreides 1: two Trikes, an Ordos soldier
FX_SOUND, FX_LIFE, BLINK, PERIOD, FLAGS2 = 0x0E, 0x0F, 0x10, 0x11, 0x06

UNFINISHED = []


def uaddr(n):
    return UNITS + n * U_SIZE


class Rig:
    def __init__(self, bdir):
        self.m = Machine(build_dir=bdir)
        self.sym = self.m.sym
        self.m.poke_label("rnd_seed", bytes((0x12, 0x34, 0x56)))
        self.load = self.m.call("start_mission", a=1, bc=1 << 8, frames=120,
                                pages=(PG_WORLD, PG_UNITS, PG_MAP))

    def poke_u(self, n, off, data):
        self.m.poke_page(PG_UNITS, n * U_SIZE + off, bytes(data))

    def ftp(self, n):
        self.m.poke_label("frames_this_pass", n.to_bytes(2, "little"))

    def call(self, label, frames=4, **kw):
        return self.m.call(label, frames=frames, pages=(PG_WORLD, PG_UNITS, PG_MAP), **kw)

    def run(self):
        self.res = self.m.run()
        UNFINISHED.extend(s for s in range(self.m.steps) if not self.res.regs(s)["done"])
        return self.res

    def unit(self, step, n):
        return self.res.page(step, PG_UNITS)[n * U_SIZE:(n + 1) * U_SIZE]


class Blink:
    """fx_anim_start / fx_anim_tick as the port runs them: the sprite
    engine's counter a frame at a time (spr_render $0010D8), then the life."""
    def __init__(self, speed, life):
        self.cnt, self.per, self.life, self.off = speed, speed, life, False

    def tick(self, ftp):
        self.off, sound = False, False
        if self.per:
            for _ in range(ftp):
                if self.cnt == 0:
                    self.cnt, self.off = self.per, True
                else:
                    self.cnt -= 1
                    sound = sound or self.cnt == 0
        self.life -= ftp
        if self.life <= 0:
            self.cnt = self.per = self.life = 0
            self.off = False
            return False, False
        return True, sound

    def bytes(self):
        return (self.life, self.cnt | (0x80 if self.off else 0), self.per)


def fx_bytes(u):
    return (u[FX_LIFE], u[BLINK], u[PERIOD])


def check(out, ok, what):
    if not ok:
        out.append("  " + what)
    return (1, 0) if ok else (0, 1)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


# ------------------------------------------------------------ scenarios

def t_deploy(bdir, out):
    """The MCV on its own square: Stop, bit 7, the animation; the blink and
    the life frame by frame; B ends it; the unit loop then deploys it."""
    rg = Rig(bdir)
    rg.poke_u(TRIKE_A, 2, [MCV])
    rg.ftp(1)
    ix = uaddr(TRIKE_A)
    s_start = rg.call("unit_fx_order", a=DEPLOY, ix=ix)
    ticks = [rg.call("fx_anim_tick", ix=ix, frames=2) for _ in range(30)]
    s_again = rg.call("unit_fx_order", a=DEPLOY, ix=ix)       # stops it
    s_move = rg.call("unit_fx_order", a=MOVE, ix=ix)          # nothing to stop
    s_restart = rg.call("unit_fx_order", a=DEPLOY, ix=ix)
    s_b = rg.call("unit_fx_press_b", a=TRIKE_A)
    s_bnone = rg.call("unit_fx_press_b", a=0xFF)
    s_loop = rg.call("unit_tick_all", frames=40)
    res = rg.run()
    r = (0, 0)
    reg = res.regs(s_start)
    u = rg.unit(s_start, TRIKE_A)
    r = add(r, check(out, reg["a"] == STOP, f"deploy: order {reg['a']}, not Stop"))
    r = add(r, check(out, w16(u, FLAGS2) & 0x80, "deploy: flags2 bit 7 not set"))
    r = add(r, check(out, (u[FX_SOUND], fx_bytes(u)) == (0x2E, (255, 8, 8)),
                     f"deploy: sound/life/blink/period {u[FX_SOUND]:#x} {fx_bytes(u)}"))
    model = Blink(8, 255)
    offs = 0
    for k, s in enumerate(ticks):
        running, _ = model.tick(1)
        offs += model.off
        u = rg.unit(s, TRIKE_A)
        reg = res.regs(s)
        got = fx_bytes(u)
        if got != model.bytes() or bool(reg["f"] & 0x40) == running:
            r = add(r, check(out, False, f"deploy tick {k + 1}: {got} Z={reg['f'] >> 6 & 1}, "
                             f"model {model.bytes()} running {running}"))
            break
    else:
        r = add(r, check(out, True, ""))
    r = add(r, check(out, offs == 3, f"deploy: {offs} frames off in 30, not 3 (one in 9)"))
    u = rg.unit(s_again, TRIKE_A)
    reg = res.regs(s_again)
    r = add(r, check(out, reg["a"] == STOP and not w16(u, FLAGS2) & 0x80 and fx_bytes(u) == (0, 0, 0),
                     f"deploy again: order {reg['a']}, flags2 {w16(u, FLAGS2):#x}, {fx_bytes(u)}"))
    reg = res.regs(s_move)
    r = add(r, check(out, reg["a"] == MOVE, f"MCV sent elsewhere: order {reg['a']}"))
    u = rg.unit(s_restart, TRIKE_A)
    r = add(r, check(out, w16(u, FLAGS2) & 0x80 and fx_bytes(u) == (255, 8, 8), "deploy restarted"))
    u = rg.unit(s_b, TRIKE_A)
    reg = res.regs(s_b)
    r = add(r, check(out, not reg["f"] & 0x40 and w16(u, FLAGS2) & 0x80 and fx_bytes(u) == (0, 0, 0),
                     f"B: Z={reg['f'] >> 6 & 1}, flags2 {w16(u, FLAGS2):#x}, {fx_bytes(u)}"))
    r = add(r, check(out, res.regs(s_bnone)["f"] & 0x40, "B with nothing selected: not Z"))
    # the unit loop: the MCV is gone and a Yard stands on its square
    u0 = rg.unit(s_start, TRIKE_A)
    sq = u0[0x0B] * 64 + u0[0x0D]
    u = rg.unit(s_loop, TRIKE_A)
    w = res.page(s_loop, PG_WORLD)
    yards = [n for n in range(73)
             if w[STRUCTS - 0x8000 + n * S_SIZE + 4] & 1
             and w[STRUCTS - 0x8000 + n * S_SIZE + 2] == CONSTYARD
             and w[STRUCTS - 0x8000 + n * S_SIZE + 0x0B] * 64 + w[STRUCTS - 0x8000 + n * S_SIZE + 0x0D] == sq]
    r = add(r, check(out, not u[4] & 1 and yards, f"the loop: MCV used {u[4] & 1}, Yard at {sq}: {yards}"))
    return r


def t_no_room(bdir, out):
    """An MCV where a Yard cannot stand: sound $2F, no animation, Stop."""
    rg = Rig(bdir)
    rg.poke_u(TRIKE_A, 2, [MCV])
    s0 = rg.call("fx_anim_tick", ix=uaddr(TRIKE_A))           # just to read the map
    res0 = rg.run()
    u = rg.unit(s0, TRIKE_A)
    sq = u[0x0B] * 64 + u[0x0D]
    rg = Rig(bdir)
    rg.poke_u(TRIKE_A, 2, [MCV])
    # a square of the Yard's 2x2 made sand
    rg.m.poke_page(PG_MAP, sq + 65, [0x7F])
    rg.m.poke_page(PG_MAP, 0x1000 + sq + 65, [res0.page(s0, PG_MAP)[0x1000 + sq + 65] & 0xFE])
    s = rg.call("unit_fx_order", a=DEPLOY, ix=uaddr(TRIKE_A))
    res = rg.run()
    u = rg.unit(s, TRIKE_A)
    reg = res.regs(s)
    index = res.page(s, PG_MAP)[0x3000 + sq]
    return check(out, reg["a"] == STOP and not w16(u, FLAGS2) & 0x80 and fx_bytes(u) == (0, 0, 0)
                 and index == TRIKE_A + 1,
                 f"no room: order {reg['a']}, flags2 {w16(u, FLAGS2):#x}, {fx_bytes(u)}, "
                 f"square's unit {index}")


def t_flash(bdir, out):
    """An attack on an enemy unit: it flashes 24 frames, every 6, sound
    $24; its bit 11 goes with the flash in the unit loop.  Not over a
    structure, not for a Harvester."""
    rg = Rig(bdir)
    rg.ftp(1)
    ix, en = uaddr(TRIKE_B), uaddr(ENEMY)
    s_hit = rg.call("unit_fx_order", a=ATTACK, ix=ix, hl=en)
    rg.ftp(5)
    loops = [rg.call("unit_tick_all", frames=30) for _ in range(5)]
    s_struct = rg.call("unit_fx_order", a=ATTACK, ix=ix, hl=en, de=STRUCTS)
    rg.poke_u(TRIKE_B, 2, [HARVESTER])
    s_harv = rg.call("unit_fx_order", a=MOVE, ix=ix, hl=en)
    res = rg.run()
    r = (0, 0)
    reg = res.regs(s_hit)
    e = rg.unit(s_hit, ENEMY)
    r = add(r, check(out, reg["a"] == ATTACK and w16(e, FLAGS2) & 0x800
                     and (e[FX_SOUND], fx_bytes(e)) == (0x24, (24, 6, 6)),
                     f"flash: order {reg['a']}, flags2 {w16(e, FLAGS2):#x}, "
                     f"{e[FX_SOUND]:#x} {fx_bytes(e)}"))
    model = Blink(6, 24)
    for k, s in enumerate(loops):
        running, _ = model.tick(5)
        e = rg.unit(s, ENEMY)
        bit = bool(w16(e, FLAGS2) & 0x800)
        if not e[4] & 1:
            break                           # it died meanwhile: nothing to see
        if fx_bytes(e) != model.bytes() or bit != running:
            r = add(r, check(out, False, f"flash pass {k + 1}: {fx_bytes(e)} bit11 {bit}, "
                             f"model {model.bytes()} {running}"))
            break
    else:
        r = add(r, check(out, True, ""))
    e = rg.unit(s_struct, ENEMY)
    r = add(r, check(out, not w16(e, FLAGS2) & 0x800, "a structure there: no flash"))
    e = rg.unit(s_harv, ENEMY)
    r = add(r, check(out, not w16(e, FLAGS2) & 0x800, "a Harvester's order: no flash"))
    return r


def t_devastator(bdir, out):
    """The Devastator on itself (Guard): bit 7 and 255 frames; a new order
    stops it; run out, the unit loop orders it to Die."""
    rg = Rig(bdir)
    rg.poke_u(TRIKE_B, 2, [DEVASTATOR])
    rg.ftp(1)
    ix = uaddr(TRIKE_B)
    s_go = rg.call("unit_fx_order", a=GUARD, ix=ix)
    s_stop = rg.call("unit_fx_order", a=MOVE, ix=ix)
    s_go2 = rg.call("unit_fx_order", a=GUARD, ix=ix)
    rg.poke_u(TRIKE_B, FX_LIFE, [3])
    rg.ftp(5)
    s_loop = rg.call("unit_tick_all", frames=30)
    res = rg.run()
    r = (0, 0)
    u = rg.unit(s_go, TRIKE_B)
    r = add(r, check(out, res.regs(s_go)["a"] == GUARD and w16(u, FLAGS2) & 0x80
                     and (u[FX_SOUND], fx_bytes(u)) == (0x2E, (255, 8, 8)),
                     f"self-destruct: {res.regs(s_go)['a']} {w16(u, FLAGS2):#x} {fx_bytes(u)}"))
    u = rg.unit(s_stop, TRIKE_B)
    r = add(r, check(out, res.regs(s_stop)["a"] == MOVE and not w16(u, FLAGS2) & 0x80
                     and fx_bytes(u) == (0, 0, 0), "a new order stops it"))
    u = rg.unit(s_go2, TRIKE_B)
    r = add(r, check(out, w16(u, FLAGS2) & 0x80, "started again"))
    u = rg.unit(s_loop, TRIKE_B)
    r = add(r, check(out, not w16(u, FLAGS2) & 0x80 and u[0x54] == DIE,
                     f"run out: flags2 {w16(u, FLAGS2):#x}, order {u[0x54]}"))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    b = args.build_dir
    tests = [
        ("deploy", lambda o: t_deploy(b, o)),
        ("no room", lambda o: t_no_room(b, o)),
        ("flash", lambda o: t_flash(b, o)),
        ("devastator", lambda o: t_devastator(b, o)),
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
        for line in out:
            print(line)
    sys.exit(1 if total_bad else 0)


if __name__ == "__main__":
    main()
