#!/usr/bin/env python3
"""dune_test.py - call the game's routines on the emulated machine.

    from dune_test import Machine
    m = Machine()                       # build/DUNE.DAT and build/dune.sym
    m.poke_page(26, 0x0000, bytes(...)) # put things in RAM first
    c = m.call("tile_distance", hl=..., de=..., frames=5)
    m.dump(26)                          # a page after the call
    res = m.run()                       # one bin/evo/evo-run, all steps
    res.regs(c)["hl"]; res.page(c, 26)

    m = Machine(build_dir="build-x", battle=100)   # calls into a running
                                                  # battle (a --house build)
    python3 tools/dune_test.py state [--frames N] [--spg build/DUNE.DAT]
        boot the game (optionally straight into a battle), run N frames,
        and print the units, structures and houses as the specs name them

How it works: the SPG is started with dbg_flags bit 7 set, which makes
the MAIN bank wait on the mailbox at $8010 of page WORLD (src/world.asm):
a script of evo-run commands pokes the target bank, address and registers
in, sets tst_state to 1, runs some frames, and dumps the pages asked for.
All the steps go into one evo-run script, so a test costs one emulator
start.  A call that has not finished in its frames is reported as such.
"""

import argparse
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVO = ROOT / "bin/evo/evo-run"
ROM = ROOT / "bin/evo/zxevo_baseconf.rom"
GSROM = ROOT / "bin/evo/gs105a.rom"
NVRAM = ROOT / "bin/evo/evo-nvram.bin"
BOOT_FRAMES = 50                # the boot's clear of the unfilled RAM

PG_UNITS, PG_WORLD, PG_MAP = 24, 25, 26
MAILBOX = 0x10                  # offset in WORLD
DBG_FLAGS = 6


def read_sym(path):
    sym = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(r"(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
    return sym


class Result:
    def __init__(self, tmp, steps):
        self.tmp = Path(tmp)
        self.steps = steps

    def page(self, step, page):
        return (self.tmp / f"s{step}_p{page}.bin").read_bytes()

    def regs(self, step):
        w = self.page(step, PG_WORLD)
        st = w[MAILBOX]
        out = struct.unpack("<6H", w[MAILBOX + 18:MAILBOX + 30])
        names = ("af", "bc", "de", "hl", "ix", "iy")
        r = dict(zip(names, out))
        r["a"] = r["af"] >> 8
        r["f"] = r["af"] & 0xFF
        r["done"] = st == 2
        return r


class Machine:
    def __init__(self, spg=None, sym=None, build_dir=None, battle=0):
        """build_dir: a --build-dir of tools/build_dune.py (default build/).
        battle: 0 - test mode, the MAIN bank only serves the mailbox; N -
        the game runs (a build made with --house goes into its battle) and
        calls are served at the start of a battle pass, after N frames."""
        b = Path(build_dir) if build_dir else ROOT / "build"
        spg = spg or b / "DUNE.DAT"
        sym = sym or b / "dune.sym"
        self.spg = Path(spg)
        self.sym_path = Path(sym)
        self.sym = read_sym(sym)
        # the boot zeroes every page the SPG left unfilled before anything
        # else runs, about 33 frames (boot.asm): nothing is served before
        if battle:
            self.lines = [f"spg {self.spg}", f"run {battle + BOOT_FRAMES}"]
        else:
            self.lines = [f"spg {self.spg}",
                          f"pokepage {PG_WORLD} {DBG_FLAGS} 128",
                          f"run {5 + BOOT_FRAMES}"]
        self.steps = 0

    def addr(self, label):
        return self.sym[label] if isinstance(label, str) else label

    def poke_page(self, page, off, data):
        for i, b in enumerate(bytes(data)):
            self.lines.append(f"pokepage {page} {off + i} {b}")

    def poke_label(self, label, data):
        """A WORLD variable (window 2 address)."""
        a = self.addr(label)
        assert 0x8000 <= a < 0xC000, label
        self.poke_page(PG_WORLD, a - 0x8000, data)

    def run_frames(self, n):
        self.lines.append(f"run {n}")

    def call(self, label, bank=None, a=0, f=0, bc=0, de=0, hl=0, ix=0, iy=0,
             w1=0, w3=0, frames=10, pages=(PG_WORLD,)):
        """Queue a call; returns its step number."""
        addr = self.addr(label)
        if bank is None:
            bank = self.page_of(label)
        box = bytearray(30)
        box[1] = w1
        box[2] = w3
        box[3] = bank
        box[4:6] = addr.to_bytes(2, "little")
        box[6:18] = struct.pack("<6H", (a << 8) | f, bc, de, hl, ix, iy)
        self.poke_page(PG_WORLD, MAILBOX + 1, box[1:18])
        self.lines.append(f"pokepage {PG_WORLD} {MAILBOX} 1")
        self.lines.append(f"run {frames}")
        step = self.steps
        self.steps += 1
        for p in set(pages) | {PG_WORLD}:
            self.lines.append(f"page {p} {{tmp}}/s{step}_p{p}.bin")
        return step

    def dump(self, page, step=None):
        s = self.steps - 1 if step is None else step
        self.lines.append(f"page {page} {{tmp}}/s{s}_p{page}.bin")

    def page_of(self, label):
        """The code bank a label is in: the PG_ constant whose bank range
        holds it is not recorded by the assembler, so the tests name the
        bank through the `$$label` table the build writes (bank_of.txt)."""
        banks = getattr(self, "_banks", None)
        if banks is None:
            banks = {}
            f = Path(self.sym_path).parent / "bank_of.txt"
            if f.exists():
                for line in f.read_text().splitlines():
                    name, page = line.split()
                    banks[name] = int(page)
            self._banks = banks
        if label not in banks:
            raise KeyError(f"{label}: not in build/bank_of.txt - pass bank=")
        return banks[label]

    def run(self, keep=None):
        tmp = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="dune_test_"))
        tmp.mkdir(parents=True, exist_ok=True)
        script = tmp / "test.script"
        script.write_text("\n".join(l.replace("{tmp}", str(tmp))
                                    for l in self.lines) + "\n")
        r = subprocess.run([str(EVO), "--rom", str(ROM), "--gsrom", str(GSROM),
                            "--script", str(script), "--quiet"],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"dune_test: evo-run failed:\n{r.stderr}")
        return Result(tmp, self.steps)


# -------------------------------------------------------------- decoding

def w16(b, o):
    return b[o] | (b[o + 1] << 8)


def s16(b, o):
    v = w16(b, o)
    return v - 0x10000 if v & 0x8000 else v


def units(units_page):
    out = []
    for n in range(102):
        o = n * 0x8C
        r = units_page[o:o + 0x8C]
        if not (r[4] & 1):
            continue
        out.append(dict(slot=n, type=r[2], house=r[8], flags=w16(r, 4),
                        flags2=w16(r, 6), y=w16(r, 0x0A), x=w16(r, 0x0C),
                        hp=w16(r, 0x12), delay=w16(r, 0x14),
                        pc=w16(r, 0x16), order=r[0x54], var0=w16(r, 0x22),
                        facing=r[0x6A], speed=r[0x70], dest=(w16(r, 0x4E), w16(r, 0x50)),
                        tmove=w16(r, 0x5C), tattack=w16(r, 0x5A)))
    return out


def structures(world_page, structs_base=0x8100):
    out = []
    for n in range(73):
        o = structs_base - 0x8000 + n * 0x62
        r = world_page[o:o + 0x62]
        if not (r[4] & 1):
            continue
        out.append(dict(slot=n, type=r[2], house=r[8], flags=w16(r, 4),
                        y=w16(r, 0x0A), x=w16(r, 0x0C), hp=w16(r, 0x12),
                        state=s16(r, 0x5C), pc=w16(r, 0x16)))
    return out


def houses(units_page):
    out = []
    for n in range(6):
        o = 0x3800 + n * 0x46
        r = units_page[o:o + 0x46]
        if not (r[4] & 1):
            continue
        out.append(dict(house=n, flags=w16(r, 4), credits=w16(r, 0x12) | (w16(r, 0x14) << 16),
                        units=w16(r, 6), maxunits=w16(r, 8)))
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("state")
    p.add_argument("--frames", type=int, default=200)
    p.add_argument("--spg", default=str(ROOT / "build/DUNE.DAT"))
    args = ap.parse_args()
    if args.cmd == "state":
        tmp = Path(tempfile.mkdtemp(prefix="dune_state_"))
        script = tmp / "s.script"
        script.write_text(f"spg {args.spg}\nrun {args.frames}\n"
                          f"page {PG_UNITS} {tmp}/u.bin\npage {PG_WORLD} {tmp}/w.bin\n")
        subprocess.run([str(EVO), "--rom", str(ROM), "--gsrom", str(GSROM),
                        "--script", str(script), "--quiet"], check=True,
                       capture_output=True)
        u = (tmp / "u.bin").read_bytes()
        w = (tmp / "w.bin").read_bytes()
        for h in houses(u):
            print("house", h)
        for s in structures(w):
            print("struct", s)
        for x in units(u):
            print("unit", x)


if __name__ == "__main__":
    main()
