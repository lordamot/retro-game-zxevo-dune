#!/usr/bin/env python3
"""run_sega.py - rebuild the Mega Drive deconstruction and play it.

    run_sega.py [--scale N] [--nosound] [--no-build]
    run_sega.py --script FILE [--shot OUT.png]

`make run sega` is the first form: `orig/sega/` is assembled into
`build/sega/dune2.gen`, checked against the original's SHA-256, and opened
in an SDL2 window with sound.

    arrows   d-pad              Z X C   the Mega Drive's A, B and C
    Enter    start              Tab     mode
    F12      screenshot         F5      reset      Escape  quit

Dune II's own front end wants Start twice and then C about fifteen times to
get through the briefing and into a battle; `tools/md_battle.script` is
those presses, and the second form runs it headlessly.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_sega import build                               # noqa: E402

CORE = ROOT / "bin/gen/genesis_plus_gx_libretro.so"
PLAY = ROOT / "bin/gen/retro-play"
RUN = ROOT / "bin/gen/retro-run"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(ROOT / "orig/sega"))
    ap.add_argument("--rom", default=str(ROOT / "build/sega/dune2.gen"))
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--nosound", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--script")
    ap.add_argument("--shot")
    args = ap.parse_args()

    rom = Path(args.rom)
    if not args.no_build:
        build(args.src, rom, quiet=True)
        print(f"{rom}: rebuilt from {args.src} and matched byte for byte")
    if not rom.exists():
        sys.exit(f"run_sega: {rom} is not there; drop --no-build")

    for tool in ((RUN if args.script else PLAY), CORE):
        if not tool.exists():
            sys.exit(f"run_sega: {tool} is missing - run `make toolchain`")

    if args.script:
        cmd = [str(RUN), "--core", str(CORE), "--rom", str(rom),
               "--script", args.script]
        if args.shot:
            cmd += ["--shot", str(Path(args.shot).with_suffix(".bmp"))]
        subprocess.run(cmd, check=True, cwd=ROOT)
        if args.shot and args.shot.endswith(".png"):
            from PIL import Image
            Image.open(Path(args.shot).with_suffix(".bmp")).save(args.shot)
            print(f"screenshot: {args.shot}")
        return

    cmd = [str(PLAY), "--core", str(CORE), "--rom", str(rom),
           "--scale", str(args.scale), "--title", "Dune II (rebuilt)",
           "--shot", str(ROOT / "tmp/sega/shot.bmp")]
    if args.nosound:
        cmd.append("--nosound")
    subprocess.run(cmd, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
