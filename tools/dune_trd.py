#!/usr/bin/env python3
"""dune_trd.py - the game as the BaseConf firmware can start it.

    dune_trd.py [--spg build/DUNE.DAT] [--out-dir build]

Writes, next to the SPG:

    dune.trd    a TR-DOS disk: `boot` (BASIC) loads `dune` (CODE) at $6000
                and calls it - src/loader/loader.asm, which reads DUNE.DAT
                off the SD card itself and starts the game
    DUNE.DAT    the SPG under the name the loader looks for

Both go on the card's root: the firmware's file browser mounts dune.trd
and boots it (or `Z.TR-DOS boot` with it mounted as A).  The firmware
runs TRD, SCL, FDI and TAP files and nothing else - an SPG is a TS-Conf
format, which is why the disk exists.

tools/sd_image.py makes a card image with the two on it for the emulator.
"""

import argparse
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
SJASM = ROOT / "bin/sjasmplus/sjasmplus"
LOADER = SRC / "loader/loader.asm"
ORG = 0x6000
DAT_NAME = "DUNE.DAT"           # src/loader/loader.asm s_name


def basic_boot():
    """The boot program, tokenized.  TR-DOS commands go through
    `RANDOMIZE USR 15619: REM:` so the same line runs under the 48 ROM."""
    CLEAR, RANDOMIZE, USR, VAL, REM, LOAD, CODE = (
        b"\xfd", b"\xf9", b"\xc0", b"\xb0", b"\xea", b"\xef", b"\xaf")

    def num(n):
        return VAL + b' "' + str(n).encode() + b'"'

    lines = [
        (10, CLEAR + b" " + num(ORG - 1)),
        (20, RANDOMIZE + b" " + USR + b" " + num(15619) + b":" + REM
             + b":" + LOAD + b' "dune"' + CODE),
        (30, RANDOMIZE + b" " + USR + b" " + num(ORG)),
    ]
    out = bytearray()
    for n, body in lines:
        out += (struct.pack(">H", n) + struct.pack("<H", len(body) + 1)
                + body + b"\x0d")
    return bytes(out)


def font(work):
    """The loader's font: the game's own 8x8 font (src/res/art/ui/font8.png,
    the cartridge's) as one bit a pixel, glyphs 32-127.  The loader cannot
    take the BASIC ROM's: under the firmware's TR-DOS the page at $0000 is
    not that ROM, and the text came out as noise on a real machine."""
    import dune_front
    codes = dune_front.font_codes("font8.png")
    out = bytearray()
    for g in range(32, 128):
        for y in range(8):
            out.append(int("".join("1" if c else "0" for c in codes[g, y]), 2))
    (work / "font.bin").write_bytes(bytes(out))


def build(spg, out_dir):
    work = out_dir / "trd"
    work.mkdir(parents=True, exist_ok=True)
    font(work)
    code = work / "dune.bin"
    subprocess.run([SJASM, "--nologo", "--msg=war", f"-I{SRC}", f"-I{work}",
                    f"--raw={code}", f"--sym={work / 'loader.sym'}",
                    str(LOADER)], check=True)
    boot = basic_boot()
    (work / "boot.bin").write_bytes(boot)
    manifest = {"label": "DUNE II", "disk_type": 22, "files": [
        {"name": "boot", "type": "B", "param1": len(boot),
         "length": len(boot), "file": "boot.bin"},
        {"name": "dune", "type": "C", "param1": ORG,
         "length": code.stat().st_size, "file": "dune.bin"}]}
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
    trd = out_dir / "dune.trd"
    subprocess.run([sys.executable, ROOT / "tools/trd_build.py",
                    work / "manifest.json", trd, "--force"],
                   check=True, stdout=subprocess.DEVNULL)
    dat = out_dir / DAT_NAME
    if Path(spg).resolve() != dat.resolve():
        shutil.copyfile(spg, dat)
    return trd, dat, code.stat().st_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spg", type=Path, default=ROOT / "build/DUNE.DAT",
                    help="the game (an SPG-format file; DUNE.DAT is the name)")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "build")
    args = ap.parse_args()
    trd, dat, n = build(args.spg, args.out_dir)
    print(f"{trd}: loader {n} bytes; {dat}: {dat.stat().st_size} bytes")


if __name__ == "__main__":
    main()
