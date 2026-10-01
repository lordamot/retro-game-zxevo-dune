#!/usr/bin/env python3
"""test_render.py - the battlefield renderer (bank RENDER) against itself.

    python3 tools/tests/test_render.py [--build-dir build] [--only NAME]

scroll: when the view moves, render_frame copies the screen showing over
the one it draws, moved by the difference, and draws only what the copy
left out (rf_scroll).  Every case loads Atreides 1 in test mode (nothing
runs between the mailbox's calls), draws both screens at a view, moves
the view through a chain of steps with a render_frame each - every one of
them a copy of the other screen's picture where it is near enough - then
calls render_invalidate and draws the other screen whole at the same
view.  The two screens must be the same byte for byte, and each step must
have gone the way expected (rf_scrolled: copied; or not, because the view
is where this screen was drawn already, or too far from the other's).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
from dune_test import Machine          # noqa: E402

PG_UNITS, PG_WORLD, PG_MAP, PG_RENDER = 24, 25, 26, 9
SCREENS = (1, 5, 3, 7)                  # screen 0's pages A, B; screen 1's
PLANE = 8000

MAX_DX, MAX_DY = 32, 20                 # RSC_MAX_DX, RSC_MAX_DY

# (name, start view, steps in cells)
CASES = [
    ("right", (640, 1024), [(1, 0)] * 6),
    ("left", (640, 1024), [(-1, 0)] * 6),
    ("down", (640, 1024), [(0, 1)] * 6),
    ("up", (640, 1024), [(0, -1)] * 6),
    ("diagonal", (600, 1000), [(1, 1), (1, -1), (-1, 1), (2, 3), (-3, -2)]),
    ("to and fro", (640, 1024), [(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)]),
    ("far", (640, 1024), [(14, 0), (-14, 7), (7, -14), (32, 20), (-32, -20)]),
    ("too far", (640, 1024), [(33, 0), (0, 21), (1, 0), (-32, -21)]),
    ("map's corner", (0, 0), [(1, 1), (-1, 0), (0, -1)]),
    ("map's far corner", (1728, 1848), [(1, 1), (1, 0), (0, 1)]),
]


def expected(start, steps):
    """Whether each step copies: the screens take turns, and a screen
    copies the other when the view has moved since it was drawn itself
    and is near enough the other's."""
    views = [start, start]              # both drawn at the start
    scr, out = 0, []
    x, y = start
    for dx, dy in steps:
        x, y = x + dx * 8, y + dy * 8
        ox, oy = views[1 - scr]
        out.append((x, y) != views[scr] and abs(x - ox) <= MAX_DX * 8
                   and abs(y - oy) <= MAX_DY * 8)
        views[scr] = (x, y)
        scr = 1 - scr
    return out


def run_case(bdir, start, steps):
    m = Machine(build_dir=bdir)
    m.poke_label("rnd_seed", bytes((0x12, 0x34, 0x56)))
    m.call("start_mission", a=1, bc=1 << 8, frames=120)

    def view(x, y):
        m.poke_label("view_x", (x & 0xFFFF).to_bytes(2, "little"))
        m.poke_label("view_y", (y & 0xFFFF).to_bytes(2, "little"))

    def render():
        return m.call("render_frame", w1=PG_UNITS, w3=PG_MAP, frames=40,
                      pages=(PG_WORLD, PG_RENDER))

    x, y = start
    view(x, y)
    render()
    render()
    done = []
    for dx, dy in steps:
        x, y = x + dx * 8, y + dy * 8
        view(x, y)
        done.append(render())
    m.call("render_invalidate", frames=3)
    view(x, y)
    last = m.call("render_frame", w1=PG_UNITS, w3=PG_MAP, frames=40,
                  pages=(PG_WORLD, PG_RENDER) + SCREENS)
    res = m.run()
    return m, res, done, last


def t_scroll(bdir, out, only=None):
    ok = bad = 0
    for name, start, steps in CASES:
        if only and only not in name:
            continue
        m, res, done, last = run_case(bdir, start, steps)
        copies = expected(start, steps)
        flag = m.sym["rf_scrolled"]
        errs = []
        for s in done + [last]:
            if not res.regs(s)["done"]:
                errs.append(f"step {s} did not finish")
        for k, (s, want) in enumerate(zip(done, copies)):
            got = bool(res.page(s, PG_RENDER)[flag])
            if got != want:
                errs.append(f"step {k}: {'copied' if got else 'not copied'}, "
                            f"expected {'copied' if want else 'not'}")
        pages = {p: res.page(last, p) for p in SCREENS}
        for a, b, what in ((1, 3, "A"), (5, 7, "B")):
            for base in (0, 0x2000):
                pa = pages[a][base:base + PLANE]
                pb = pages[b][base:base + PLANE]
                diff = [i for i in range(PLANE) if pa[i] != pb[i]]
                if diff:
                    cells = sorted({(i % 40, i // 320) for i in diff})
                    errs.append(f"page {what} plane at +{base:#x}: {len(diff)} bytes "
                                f"differ, cells (col, row) {cells[:8]}"
                                f"{' ...' if len(cells) > 8 else ''}")
        if errs:
            bad += 1
            out.append(f"  {name}:")
            out.extend(f"    {e}" for e in errs)
        else:
            ok += 1
    return ok, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--only")
    args = ap.parse_args()
    ok, bad = t_scroll(args.build_dir, out := [], args.only)
    print(f"{'scroll':12s} {ok}/{ok + bad}")
    for line in out:
        print(line)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
