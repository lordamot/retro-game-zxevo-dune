#!/usr/bin/env python3
"""test_missions.py - every one of the 27 missions starts and keeps running.

    python3 tools/tests/test_missions.py [--build-dir build] [--frames 3000]
                                         [--window 250] [--only H1,A9,...]
                                         [--jobs N] [--budget 3.0]

For each house (H, A, O) and mission (1-9) one headless evo-run: the debug
block is poked before the game starts (house, mission, dbg_flags bit 3 for
no sound - src/world.asm), so a single ordinary build reaches every battle
without the front end.  The player gives no orders; the computer builds,
harvests and attacks as its scripts say.  Every `--window` frames the
battle's pass counter is read, and each mission must show:

  loaded     scenario_id and player_house are the ones asked for
  running    the pass counter moves in every window until the mission is
             over (a hang or a crash stops it); a mission the computer
             wins or the player's harvest ends early (level_result 1 or
             2) is reported, not failed
  budget     no window averages more than `--budget` frames a pass (the
             same 3.0 as make verify's check)

It prints a line a mission - its windows' frames a pass, average and
worst - and the worst of all.  The runs go in parallel (`--jobs`, default
the machine's cores).  A long `--frames` (20000 is about seven minutes of
game time) is how the late game's frame budget is measured.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dune_test import EVO, ROM, GSROM, PG_WORLD, DBG_FLAGS, read_sym   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
HOUSES = "HAO"                  # dbg_house 0, 1, 2
DBG_HOUSE, DBG_MISSION = 4, 5   # offsets of the debug block in WORLD
NO_SOUND = 8                    # dbg_flags bit 3


def run_mission(spg, sym, house, mission, frames, window):
    """One evo-run: the mission started through the debug block, then the
    pass counter read every `window` frames.  -> (passes list, loaded)."""
    pc, sc, ph = sym["pass_count"], sym["scenario_id"], sym["player_house"]
    lr = sym["level_result"]
    lines = [f"spg {spg}",
             f"pokepage {PG_WORLD} {DBG_HOUSE} {house}",
             f"pokepage {PG_WORLD} {DBG_MISSION} {mission}",
             f"pokepage {PG_WORLD} {DBG_FLAGS} {NO_SOUND}",
             "run 300",
             f"peek {sc:#x} 1", f"peek {ph:#x} 1", f"peek {pc:#x} 2"]
    for _ in range(frames // window):
        lines += [f"run {window}", f"peek {pc:#x} 2", f"peek {lr:#x} 1"]
    with tempfile.NamedTemporaryFile("w", suffix=".script", delete=False) as f:
        f.write("\n".join(lines) + "\n")
        script = f.name
    try:
        r = subprocess.run([str(EVO), "--rom", str(ROM), "--gsrom", str(GSROM),
                            "--script", script, "--quiet"],
                           capture_output=True, text=True)
    finally:
        os.unlink(script)
    vals = {}
    seq = []
    results = []
    for line in r.stdout.splitlines():
        m = re.match(r"([0-9A-F]{4}):((?: [0-9A-F]{2})+)", line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        b = [int(x, 16) for x in m.group(2).split()]
        if addr == pc:
            seq.append(b[0] | (b[1] << 8))
        elif addr == lr:
            results.append(b[0])
        else:
            vals[addr] = b[0]
    loaded = vals.get(sc) == mission and vals.get(ph) == house
    return seq, loaded, results, r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", default=str(ROOT / "build"))
    ap.add_argument("--frames", type=int, default=3000)
    ap.add_argument("--window", type=int, default=250)
    ap.add_argument("--only", help="e.g. H1,A9")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--budget", type=float, default=3.0)
    args = ap.parse_args()
    b = Path(args.build_dir)
    spg, sym = b / "DUNE.DAT", read_sym(b / "dune.sym")
    todo = [(h, m) for h in range(3) for m in range(1, 10)]
    if args.only:
        want = {s.strip().upper() for s in args.only.split(",")}
        todo = [(h, m) for h, m in todo if f"{HOUSES[h]}{m}" in want]
    with ThreadPoolExecutor(args.jobs) as ex:
        results = list(ex.map(lambda hm: (hm, run_mission(spg, sym, *hm, args.frames,
                                                           args.window)), todo))
    bad = 0
    worst_all = (0.0, "")
    for (h, m), (seq, loaded, ends, rc) in results:
        name = f"{HOUSES[h]}{m}"
        # a mission that is over stops counting passes: keep the windows
        # before its end only
        over = next((i for i, v in enumerate(ends) if v), None)
        if over is not None:
            seq = seq[:over + 1]
        steps = [(b - a) & 0xFFFF for a, b in zip(seq, seq[1:])]
        fpp = [args.window / s if s else float("inf") for s in steps]
        problems = []
        if not loaded:
            problems.append("did not load")
        if rc:
            problems.append(f"evo-run exited with {rc}")
        if over is None and len(seq) < args.frames // args.window + 1:
            problems.append(f"only {len(seq)} readings of {args.frames // args.window + 1}")
        if any(s == 0 for s in steps):
            stuck = next(i for i, s in enumerate(steps) if s == 0)
            problems.append(f"stopped after {300 + stuck * args.window} frames")
        worst = max(fpp) if fpp else float("inf")
        if worst > args.budget:
            problems.append(f"over budget ({worst:.2f} > {args.budget})")
        total = sum(steps)
        avg = (len(steps) * args.window / total) if total else float("inf")
        if worst > worst_all[0] and worst != float("inf"):
            worst_all = (worst, name)
        shape = " ".join(f"{x:.1f}" if x != float("inf") else "-" for x in fpp)
        end = ""
        if over is not None:
            end = f"  ({('won', 'lost')[ends[over] == 2]} by {300 + (over + 1) * args.window} frames)"
        print(f"{name}  avg {avg:.2f}  worst {worst:.2f}{end}  "
              f"{'ok' if not problems else 'FAIL: ' + '; '.join(problems)}")
        print(f"    {shape}")
        bad += bool(problems)
    print(f"missions {len(results) - bad}/{len(results)}; worst window {worst_all[0]:.2f} "
          f"frames a pass ({worst_all[1]})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
