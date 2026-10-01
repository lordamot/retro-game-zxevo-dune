#!/usr/bin/env python3
"""test_core.py - the stub's core routines against Python transcriptions
of the cartridge's own (tools/dune_test.py runs them on the machine).

    python3 tools/tests/test_core.py
"""
import random as R
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dune_test import Machine          # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent


def load_table(name):
    """A table's values out of build/gen/tables.inc."""
    lines = (ROOT / "build/gen/tables.inc").read_text().splitlines()
    vals, on = [], False
    for l in lines:
        if l.startswith(f"{name}:"):
            on = True
            continue
        if on:
            s = l.strip()
            if s.startswith(("db ", "dw ", "dd ")):
                vals += [int(v.strip().replace("$", "0x"), 0) for v in s[3:].split(";")[0].split(",")]
            elif s.startswith(";") or not s:
                if vals and not s:
                    break
            else:
                break
    return vals


SIN = [v - 256 if v > 127 else v for v in load_table("tbl_sin")]
COS = [v - 256 if v > 127 else v for v in load_table("tbl_cos")]
COT = load_table("tbl_cot")
QUAD = load_table("tbl_atan_quadrant")
DIRP = load_table("tbl_direction_packed")


# ---- the models (68000 transcriptions)
def rnd(seed):
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


def atan2(dx, dy):
    d7 = 0
    if dy <= 0:
        d7 += 2
        dy = -dy
    if dx < 0:
        d7 += 1
        dx = -dx
    d3 = QUAD[d7]
    d4 = 0
    d5 = 0x7FFF
    if dx >= dy:
        if dy:
            d5 = (dx << 8) // dy
    else:
        d4 = 1
        if dx:
            d5 = (dy << 8) // dx
    i = 0
    while i < 32 and d5 < COT[i]:
        i += 1
    d0 = i if d4 else 0x40 - i
    if d7 in (1, 2):
        d3 += d0
    else:
        d3 = d3 - d0 + 0x40
    return d3 & 255


def dir_packed(a, b):
    x0, y0, x1, y1 = a & 63, (a >> 6) & 63, b & 63, (b >> 6) & 63
    d3 = 0
    if not y1 > y0:
        d3 += 8
    if not x1 > x0:
        d3 += 4
    dx, dy = x1 - x0, y1 - y0
    if abs(dy) > abs(2 * dx):
        d3 += 2
    if abs(dx) > abs(2 * dy):
        d3 += 1
    v = DIRP[d3]
    return 0xFF if v == 0xFFFF else v


def mul_shr8(a, b):
    return min((a * b + 0x50) >> 8, 0xFFFF)


def div_shl8(a, b):
    d0 = b << 8
    d1 = a
    while d0 > 0xFFFF:
        d0 = (d0 + 1) >> 1
        d1 = ((d1 + 1) & 0xFFFF) >> 1
    return 0xFFFF if d1 == 0 else (d0 // d1) & 0xFFFF


def move_dir(y, x, f, d):
    y += (-COS[f] * d + 64) >> 7
    x += (SIN[f] * d + 64) >> 7
    return y & 0xFFFF, x & 0xFFFF


def main():
    R.seed(7)
    m = Machine()
    checks = []
    # random: set the seed, call
    for _ in range(8):
        seed = (R.randrange(256), R.randrange(256), R.randrange(256))
        m.poke_label("rnd_seed", bytes(seed))
        s = m.call("random", frames=1)
        checks.append(("random", seed, s, rnd(seed)[1]))
    for _ in range(12):
        seed = (R.randrange(256), R.randrange(256), R.randrange(256))
        lo = R.randrange(0, 40)
        hi = lo + R.randrange(0, 200)
        m.poke_label("rnd_seed", bytes(seed))
        s = m.call("rand_between", de=(lo << 8) | (hi & 255), frames=1)
        checks.append(("rand_between", (seed, lo, hi), s, rand_between(seed, lo, hi)[1]))
    for _ in range(40):
        a = (R.randrange(0, 16384), R.randrange(0, 16384))
        b = (R.randrange(0, 16384), R.randrange(0, 16384))
        if R.random() < 0.2:
            b = (a[0] + R.randrange(-600, 600), a[1])
        if R.random() < 0.2:
            b = (a[0], a[1] + R.randrange(-600, 600))
        pa = a[0].to_bytes(2, "little") + a[1].to_bytes(2, "little")
        pb = (b[0] & 0xFFFF).to_bytes(2, "little") + (b[1] & 0xFFFF).to_bytes(2, "little")
        m.poke_label("ref_pos", pa)
        m.poke_label("tst_scratch", pb)
        s = m.call("tile_direction", hl=m.addr("ref_pos"), de=m.addr("tst_scratch"), frames=2)
        dy = ((b[0] - a[0]) + 0x8000) % 0x10000 - 0x8000
        dx = ((b[1] - a[1]) + 0x8000) % 0x10000 - 0x8000
        checks.append(("tile_direction", (a, b), s, atan2(dx, dy)))
    for _ in range(30):
        a, b = R.randrange(4096), R.randrange(4096)
        s = m.call("tile_direction_packed", hl=a, de=b, frames=1)
        checks.append(("tile_direction_packed", (a, b), s, dir_packed(a, b)))
    for _ in range(20):
        a, b = R.randrange(65536), R.randrange(65536)
        s = m.call("mul_shr8", hl=a, de=b, frames=1)
        checks.append(("mul_shr8", (a, b), s, mul_shr8(a, b)))
        a, b = R.randrange(1, 2000), R.randrange(65536)
        s = m.call("div_shl8", hl=a, de=b, frames=1)
        checks.append(("div_shl8", (a, b), s, div_shl8(a, b)))
    for _ in range(20):
        y, x, f, d = R.randrange(512, 15000), R.randrange(512, 15000), R.randrange(256), R.randrange(256)
        m.poke_label("ref_pos", y.to_bytes(2, "little") + x.to_bytes(2, "little"))
        s = m.call("tile_move_by_direction", hl=m.addr("ref_pos"), a=f, bc=d, frames=1)
        checks.append(("tile_move_by_direction", (y, x, f, d), s, move_dir(y, x, f, d)))
    res = m.run()
    bad = {}
    total = {}
    for name, args, s, exp in checks:
        r = res.regs(s)
        if name in ("random", "rand_between", "tile_direction", "tile_direction_packed"):
            got = r["a"]
        elif name == "tile_move_by_direction":
            w = res.page(s, 25)
            o = m.addr("ref_pos") - 0x8000
            got = (w[o] | w[o + 1] << 8, w[o + 2] | w[o + 3] << 8)
        else:
            got = r["hl"]
        total[name] = total.get(name, 0) + 1
        if got != exp or not r["done"]:
            bad[name] = bad.get(name, 0) + 1
            if bad[name] <= 3:
                print(f"  {name}{args}: expected {exp}, got {got}")
    for n in total:
        print(f"{n:24s} {total[n] - bad.get(n, 0)}/{total[n]}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
