#!/usr/bin/env python3
"""sega_touch.py - find out what the Mega Drive Dune II does with its bytes.

A disassembler can only guess which bytes of a cartridge are code and
which are data.  The machine knows: bin/gen's Genesis core is patched to
keep a byte of flags for every cartridge address (see patch_gpgx_touch in
tools/build_toolchain.py) and the address of the instruction that first
read it.  This drives the game to make that record as complete as it can
be, and writes it down.

The game is driven by coverage, not by a script.  A pool of save states
starts with the machine just switched on; each round takes a state from
the pool, plays a few seconds of random input on it, and keeps the state
it ends in if that stretch ran an instruction nothing had run before.
Random input is a poor player, but it is a tireless one, and every new
screen it stumbles into becomes somewhere the next round can start from.

    sega_touch.py fuzz [--rounds N] [--jobs J]   grow the record
    sega_touch.py seed [NAME...]                 the scenarios, by the front door
    sega_touch.py replay                         rebuild it from the pool
    sega_touch.py stats                          what the record says
    sega_touch.py export                         write orig/sega/res/trace.txt

Everything under tmp/sega/touch/ is scratch; orig/sega/res/trace.txt is
the result, as text, and tools/sega/sega_extract.py reads it.
"""

import argparse
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
RUN = ROOT / "bin/gen/retro-run"
CORE = ROOT / "bin/gen/genesis_plus_gx_libretro.so"
ROM = ROOT / "orig/dune2.gen"
WORK = ROOT / "tmp/sega/touch"
TRACE = ROOT / "orig/sega/res/trace.txt"
SIZE = 0x100000

# The boot's checksum at $00293C reads every byte of the cartridge and
# means nothing by it; its reads are not recorded.
BLIND = [0x00293C]

EXEC, FETCH, DATA, DMA, Z80, CRAM, VSRAM = 1, 2, 4, 8, 16, 32, 64
READ = DATA | DMA | Z80 | CRAM | VSRAM

BUTTONS = ["up", "down", "left", "right", "mda", "mdb", "mdc", "start"]


def run_script(lines, tag):
    """Run a retro-run script; return (touch, reader) for that run."""
    with tempfile.TemporaryDirectory(dir=WORK) as d:
        t, r = Path(d) / "t.bin", Path(d) / "r.bin"
        s = Path(d) / "s.script"
        body = [f"blind {hex(b)}" for b in BLIND] + lines + [
            f"touch {t}", f"reader {r}"]
        s.write_text("\n".join(body) + "\n")
        p = subprocess.run([str(RUN), "--core", str(CORE), "--rom", str(ROM),
                            "--script", str(s)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if p.returncode or not t.exists():
            return None, None
        return t.read_bytes(), r.read_bytes()


# ---------------------------------------------------------- the scenarios
#
# Random input finds the first mission and the menus, and then stalls: it
# will not win a battle.  These go where it cannot, by the front door.
# The options screen has a music test and a sound test, which play every
# tune and every effect; and the password screen takes the 29 words in the
# table at $08811C - a mission for every house from the second to the
# ninth, the ending, and four for the playtesters.

MENU = ["run 2200"]                                   # the title's menu
OPTIONS = MENU + ["press down 6", "run 40", "press mdc 6", "run 150"]
PASSWORD = OPTIONS + ["press down 6", "run 20"] * 5 + [
    "press mdc 6", "run 210"]
GRID = ["ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ<>!"]


def password_table(rom):
    """The 29 passwords at $08811C: (word, kind, value) until a null."""
    out, a = [], 0x08811C
    while True:
        p = int.from_bytes(rom[a:a + 4], "big")
        if not p:
            return out
        word = rom[p:rom.index(0, p)].decode("ascii")
        out.append((word, int.from_bytes(rom[a + 4:a + 6], "big"),
                    int.from_bytes(rom[a + 6:a + 8], "big")))
        a += 8


def rub_out():
    """From END back to the first letter: `<` ten times."""
    return ["press left 4", "run 8"] * 2 + ["press mdc 4", "run 12"] * 10


def type_password(word, r=0, c=0):
    """Walk the letter grid from row r, column c; after the tenth letter
    the cursor is on END."""
    out = []
    for ch in word:
        R = next(i for i, row in enumerate(GRID) if ch in row)
        C = GRID[R].index(ch)
        out += ["press down 4", "run 8"] * max(0, R - r)
        out += ["press up 4", "run 8"] * max(0, r - R)
        out += ["press right 4", "run 8"] * max(0, C - c)
        out += ["press left 4", "run 8"] * max(0, c - C)
        out += ["press mdc 4", "run 12"]
        r, c = R, C
    return out + ["run 30", "press mdc 4", "run 12"]


def in_game(word):
    """START in a battle, the options' password line, the word, and back
    to the battle: SPLURGEOLA there is 25000 credits, which wins any
    mission with a quota, and DUNEFINALE is the ending."""
    return (["press start 6", "run 120"] + ["press down 6", "run 20"] * 5
            + ["press mdc 6", "run 210"] + type_password(word)
            + ["run 60", "press start 6", "run 120", "press start 6",
               "run 200"])


# the house choice shows Atreides, Ordos, Harkonnen from left to right;
# the password table's kinds are Harkonnen, Atreides, Ordos
CREST = {1: 0, 2: 1, 0: 2}
ONWARD = ["press mdc 6", "run 300"]          # through whatever is on screen


def scenarios(rom):
    """name -> script lines.  Each ends somewhere worth starting from."""
    sc = {"attract": ["run 30000"]}
    test = OPTIONS + ["press down 4", "run 10"] * 3
    sc["music"] = test + ["press mdc 4", "run 900"] + \
        ["press right 4", "run 20", "press mdc 4", "run 900"] * 24
    sc["sounds"] = test + ["press down 4", "run 10", "press mdc 4",
                           "run 150"] + \
        ["press right 4", "run 20", "press mdc 4", "run 150"] * 70
    sc["tutorial"] = MENU + ["press down 6", "run 20"] * 2 + [
        "press mdc 6", "run 300"]
    words = password_table(rom)
    for kind in range(3):
        m1 = MENU + ["press mdc 6", "run 300"] + \
            ["press right 6", "run 20"] * CREST[kind] + ONWARD * 10 + \
            ["run 600"]
        sc[f"m1-{kind}"] = m1
        sc[f"m1win-{kind}"] = m1 + in_game("SPLURGEOLA") + ONWARD * 40
        # the mentat's advice, instead of proceeding
        sc[f"advice-{kind}"] = MENU + ["press mdc 6", "run 300"] + \
            ["press right 6", "run 20"] * CREST[kind] + ONWARD * 3 + \
            ["press down 6", "run 20"] + ONWARD * 6
        first = next(w for w, k, v in words if k == kind)
        sc[f"end-{kind}"] = (PASSWORD + type_password(first) + ONWARD * 12
                             + ["run 600"] + in_game("DUNEFINALE")
                             + ["run 30000"])
    for word, kind, value in words:
        # through the mentat and into the battle: the briefing wants a
        # button now and then, and more presses do no harm
        tail = ["run 300"] + ["press mdc 6", "run 200"] * 12 + ["run 600"]
        if kind == 3:
            tail = ["run 20000"]                 # the ending plays itself
        sc["pw-" + word] = PASSWORD + type_password(word) + tail
        if kind < 3:
            sc["win-" + word] = (sc["pw-" + word] + in_game("SPLURGEOLA")
                                 + ONWARD * 40)
            # PLAYTESTER first: the player's side takes no damage, which is
            # what lets a random player live long enough to build things
            sc["pt-" + word] = (PASSWORD + type_password("PLAYTESTER")
                                + rub_out() + type_password(word, 2, 6)
                                + tail)
    return sc


def seed(args):
    """Play every scenario and put where each ends into the pool."""
    rec = Record()
    rom = ROM.read_bytes()
    pool = WORK / "pool"
    pool.mkdir(parents=True, exist_ok=True)
    sc = scenarios(rom)
    names = [n for n in sc if not args.only or n in args.only]

    with ProcessPoolExecutor(args.jobs) as ex:
        for name, t, r in ex.map(_seed_job, [(n, sc[n]) for n in names]):
            new = rec.merge(t, r) if t is not None else -1
            print(f"  {name:<16} +{new}", flush=True)
    rec.save()
    print(f"{int(np.count_nonzero(rec.touch & EXEC))} instructions run")


def _seed_job(item):
    name, lines = item
    dst = WORK / "pool" / f"seed-{name}.state"
    t, r = run_script(lines + [f"save {dst}"], name)
    return name, t, r


def random_input(rng, frames):
    """A stretch of play: the pad held in some direction for a while,
    buttons pressed now and then - which is roughly what a player does
    with a strategy game on a pad."""
    out, left = [], frames
    while left > 0:
        k = rng.random()
        if k < 0.06:
            # a build, the way a player does one: A on the yard, B to start
            # the first thing on offer, time for it to finish, C to place
            # it, somewhere near, and C or B to put it down
            out += ["press mda 6", "run 30"]
            out += ["press down 6", "run 10"] * rng.randrange(4)
            out += ["press mdb 6", "run 600", "press mdc 6", "run 30"]
            out += [f"press {rng.choice(BUTTONS[:4])} 6", "run 10"] * \
                rng.randrange(1, 5)
            out += [f"press {rng.choice(('mdc', 'mdb'))} 6", "run 30"]
            left -= 820
            continue
        if k < 0.10:
            # pick something up and send it somewhere
            out += ["press mda 6", "run 20"]
            out += [f"hold {rng.choice(BUTTONS[:4])}",
                    f"run {rng.choice((20, 60, 120))}", "release"]
            out += ["press mda 6", "run 60"]
            left -= 200
            continue
        n = rng.choice((4, 8, 12, 20, 40, 80))
        n = min(n, left)
        k = rng.random()
        if k < 0.45:
            pad = [rng.choice(BUTTONS[:4])]
            if rng.random() < 0.3:
                pad.append(rng.choice(BUTTONS[4:7]))
            out.append(f"hold {','.join(pad)}")
            out.append(f"run {n}")
            out.append("release")
        elif k < 0.85:
            b = rng.choice(BUTTONS[4:] + ["mdc", "mdc", "mdb"])
            out.append(f"press {b} 6")
            out.append(f"run {n}")
        else:
            out.append(f"run {n}")
        left -= n + (6 if k >= 0.45 and k < 0.85 else 0)
    return out


def one_round(job):
    """Play one stretch from a pool state.  Runs in a worker process."""
    src, dst, seed, frames = job
    rng = random.Random(seed)
    lines = []
    if src:
        lines.append(f"load {src}")
    else:
        lines.append(f"run {rng.choice((60, 900, 2400, 4000))}")
    lines += random_input(rng, frames)
    lines.append(f"save {dst}")
    t, r = run_script(lines, seed)
    return src, dst, seed, t, r


class Record:
    """The merged record: flags ORed together, the first reader kept."""

    def __init__(self):
        WORK.mkdir(parents=True, exist_ok=True)
        tp, rp = WORK / "touch.bin", WORK / "reader.bin"
        self.touch = (np.fromfile(tp, np.uint8) if tp.exists()
                      else np.zeros(SIZE, np.uint8))
        self.reader = (np.fromfile(rp, "<u4") if rp.exists()
                       else np.zeros(SIZE, "<u4"))

    def merge(self, t, r):
        """OR a run in; return how many instruction starts were new."""
        t = np.frombuffer(t, np.uint8)
        r = np.frombuffer(r, "<u4")
        new = int(np.count_nonzero((t & EXEC) & ~(self.touch & EXEC)))
        take = (self.reader == 0) & (r != 0)
        self.reader[take] = r[take]
        self.touch |= t
        return new

    def save(self):
        self.touch.tofile(WORK / "touch.bin")
        self.reader.tofile(WORK / "reader.bin")


def fuzz(args):
    rec = Record()
    pool_dir = WORK / "pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    pool = sorted(pool_dir.glob("*.state"), key=lambda p: p.stat().st_mtime)
    # a state's worth is how much it found; states that keep finding things
    # are picked more often
    score = {p: 1.0 for p in pool}
    rng = random.Random(args.seed)
    serial = len(pool)
    with ProcessPoolExecutor(args.jobs) as ex:
        for rnd in range(args.rounds):
            jobs = []
            for j in range(args.jobs):
                if not pool or rng.random() < 0.05:
                    src = None
                else:
                    w = [score[p] for p in pool]
                    src = rng.choices(pool, weights=w)[0]
                serial += 1
                dst = pool_dir / f"{serial:06d}.state"
                jobs.append((str(src) if src else None, str(dst),
                             rng.randrange(1 << 30), args.frames))
            found = 0
            for src, dst, seed, t, r in ex.map(one_round, jobs):
                dst = Path(dst)
                if t is None:
                    dst.unlink(missing_ok=True)
                    continue
                new = rec.merge(t, r)
                if src:
                    score[Path(src)] = score[Path(src)] * 0.9 + new * 0.1
                if new:
                    found += new
                    pool.append(dst)
                    score[dst] = 1.0 + new
                else:
                    dst.unlink(missing_ok=True)
            rec.save()
            ex_n = int(np.count_nonzero(rec.touch & EXEC))
            print(f"round {rnd + 1}: +{found} instructions, {ex_n} run in "
                  f"all, {len(pool)} states", flush=True)


def replay(args):
    """Rebuild the record from the pool alone: every state played on for a
    while from where it stands.  For when the core has learned to record
    something new and the old record is thrown away."""
    rec = Record()
    pool = sorted((WORK / "pool").glob("*.state"))
    jobs = [(str(p), str(WORK / f"replay-{i}.tmp"), i, args.frames)
            for i, p in enumerate(pool)]
    with ProcessPoolExecutor(args.jobs) as ex:
        for src, dst, seed, t, r in ex.map(one_round, jobs):
            Path(dst).unlink(missing_ok=True)
            if t is not None:
                rec.merge(t, r)
    rec.save()
    print(f"{len(pool)} states replayed, "
          f"{int(np.count_nonzero(rec.touch & EXEC))} instructions run")


def stats(args):
    rec = Record()
    n = [int(np.count_nonzero(rec.touch & (1 << k))) for k in range(7)]
    names = ["instruction starts", "instruction bytes", "read as data",
             "sent to VRAM by DMA", "read by the Z80", "sent to CRAM by DMA",
             "sent to VSRAM by DMA"]
    for k in range(7):
        print(f"  {n[k]:8d}  {names[k]}")
    print(f"  {int(np.count_nonzero(rec.touch)):8d}  touched at all")


def export(args):
    """Write the record down as text, in two parts.

    `C START-END N` is a run of bytes the 68000 fetched as instructions,
    N of them starting there.  Runs are contiguous, so decoding forwards
    from START finds the instructions; the last one may reach past END,
    because a branch that is not taken never fetches its displacement.

    `D START-END FLAGS READER` is a run of bytes read as data, with the
    same flags and the same first reader: d the 68000; v, c and s the
    VDP's DMA into VRAM, CRAM and VSRAM; z the Z80.  The reader is the instruction that first read them - for
    a DMA, the write to the VDP that started it; the Z80 has no address
    the 68000 knows, and is written z80.
    """
    rec = Record()
    t = rec.touch
    rd = rec.reader
    L = ["# trace.txt - what the running game did with each byte.",
         "#",
         "# Written by tools/sega/sega_touch.py from Genesis Plus GX, patched",
         "# to record it (tools/build_toolchain.py, patch_gpgx_touch), while",
         "# a coverage-guided random player drove the game.",
         "#",
         "#   C start-end n             n instructions were run from here",
         "#   D start-end flags readers read as data: d by the 68000; v, c",
         "#                             and s by a DMA into VRAM, CRAM and",
         "#                             VSRAM; z by the Z80.  The readers",
         "#                             are the instructions that first did",
         "#",
         "# Bytes never touched are not listed.  Not reached is not the same",
         "# as dead: a random player does not finish the campaign.",
         ""]
    fetch = (t & FETCH) != 0
    starts = (t & EXEC) != 0
    edges = np.flatnonzero(np.diff(np.concatenate(([0], fetch.view(np.int8),
                                                   [0]))))
    for a, e in zip(edges[::2], edges[1::2]):
        n = int(np.count_nonzero(starts[a:e]))
        L.append(f"C ${a:06X}-${e - 1:06X} {n}")
    kind = (t & READ).astype(np.int64)
    change = np.flatnonzero(np.diff(np.concatenate(([-1], kind, [-1]))))
    for a, e in zip(change[:-1], change[1:]):
        k = int(kind[a])
        if not k:
            continue
        fl = "".join(c for c, bit in (("d", DATA), ("v", DMA), ("c", CRAM),
                                      ("s", VSRAM), ("z", Z80)) if k & bit)
        who = []
        for v in np.unique(rd[a:e]).tolist():
            if not v:
                continue
            w = "z80" if v & 0x40000000 else f"${v & 0xFFFFFF:06X}"
            if w not in who:
                who.append(w)
        L.append(f"D ${a:06X}-${e - 1:06X} {fl} {','.join(who) or '-'}")
    TRACE.write_text("\n".join(L) + "\n")
    print(f"wrote {TRACE}: {len(L)} lines")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fuzz")
    f.add_argument("--rounds", type=int, default=20)
    f.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    f.add_argument("--frames", type=int, default=1800)
    f.add_argument("--seed", type=int, default=1)
    sd = sub.add_parser("seed")
    sd.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    sd.add_argument("only", nargs="*")
    r = sub.add_parser("replay")
    r.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    r.add_argument("--frames", type=int, default=600)
    sub.add_parser("stats")
    sub.add_parser("export")
    args = ap.parse_args()
    {"fuzz": fuzz, "seed": seed, "replay": replay, "stats": stats,
     "export": export}[args.cmd](args)


if __name__ == "__main__":
    main()
