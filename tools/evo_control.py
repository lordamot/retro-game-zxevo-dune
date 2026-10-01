#!/usr/bin/env python3
"""evo_control.py - drive the bundled ZX Evolution emulator from Python.

`bin/evo/evo-run` is the headless machine and takes a small script language
(see .claude/docs/tools/evo-emulate.md).  This wraps it so the recurring
jobs are one command instead of a hand-written script every time:

    evo_control.py boot   --trd F.trd [--shot OUT.png] [--frames N]
                          boot the disk through the firmware's TR-DOS entry
    evo_control.py script FILE [--trd F.trd]
                          run a script file as-is
    evo_control.py play   [--trd F.trd | --spg DUNE.DAT] [--scale N]
                          open the playable window
    evo_control.py script FILE [--spg DUNE.DAT]
                          a script with an SPG loaded first (the game)
    evo_control.py nvram  [--out bin/evo/evo-nvram.bin]
                          regenerate the machine's saved settings

Screenshots come out of the emulator as 24-bit BMP; a --shot ending in .png
is converted afterwards (Pillow), which is what the docs and the skills use.

Why the boot dance: on a real ZX Evolution the firmware's boot menu comes up
first, and out of the box its drive A is the SD-card "virtual drive", not
the floppy.  `nvram` bakes the two settings this project wants (virtual
drive moved to B, CPU clock 14 MHz) into bin/evo/evo-nvram.bin, which every
other command then loads, exactly as the battery does on the real board.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVO = ROOT / "bin/evo"
RUN = EVO / "evo-run"
PLAY = EVO / "evo-play"
ROM = EVO / "zxevo_baseconf.rom"
GSROM = EVO / "gs105a.rom"
NVRAM = EVO / "evo-nvram.bin"

# The firmware's boot menu needs a moment before it takes keys, then two
# ENTERs: one for "TR-DOS boot", one to pick the "boot" file it found.
BOOT_SCRIPT = """\
run 250
press enter 4
run 60
press enter 4
run {frames}
"""

# Y cycles which drive is the virtual (SD) one, W cycles the CPU clock.
NVRAM_SCRIPT = """\
run 250
press y 4
run 60
press w 4
run 60
"""


def need(path):
    if not path.exists():
        sys.exit(f"error: {path.relative_to(ROOT)} is missing - run `make toolchain`")


def evo_run(script_text, trd=None, shot=None, extra=(), nvram=True, capture=False,
            spg=None):
    need(RUN); need(ROM)
    with tempfile.NamedTemporaryFile("w", suffix=".script", delete=False) as f:
        f.write(script_text)
        script = f.name
    bmp = None
    cmd = [str(RUN), "--rom", str(ROM), "--script", script]
    if GSROM.exists():
        cmd += ["--gsrom", str(GSROM)]
    if nvram and NVRAM.exists():
        cmd += ["--nvram", str(NVRAM)]
    if trd:
        cmd += ["--trd", str(trd)]
    if spg:
        cmd += ["--spg", str(spg)]
    if shot:
        bmp = str(Path(shot).with_suffix(".bmp"))
        cmd += ["--shot", bmp]
    cmd += list(extra)
    try:
        res = subprocess.run(cmd, check=True,
                             capture_output=capture, text=capture)
    finally:
        os.unlink(script)
    if shot and str(shot).endswith(".png"):
        to_png(bmp, shot)
    return res


def to_png(bmp, png):
    try:
        from PIL import Image
    except ImportError:
        shutil.copy2(bmp, png)
        print(f"note: Pillow not available, left {bmp} as BMP")
        return
    Image.open(bmp).save(png)
    os.unlink(bmp)


def cmd_boot(args):
    evo_run(BOOT_SCRIPT.format(frames=args.frames), trd=args.trd, shot=args.shot)
    if args.shot:
        print(f"screenshot: {args.shot}")


def cmd_script(args):
    evo_run(Path(args.file).read_text(), trd=args.trd, shot=args.shot,
            spg=args.spg)


def cmd_play(args):
    need(PLAY); need(ROM)
    cmd = [str(PLAY), "--rom", str(ROM), "--scale", str(args.scale)]
    if GSROM.exists():
        cmd += ["--gsrom", str(GSROM)]
    if NVRAM.exists():
        cmd += ["--nvram", str(NVRAM)]
    if args.trd:
        cmd += ["--trd", str(args.trd)]
    if args.spg:
        cmd += ["--spg", str(args.spg)]
    os.execv(str(PLAY), cmd)


def cmd_nvram(args):
    out = Path(args.out)
    evo_run(NVRAM_SCRIPT, nvram=False, extra=["--save-nvram", str(out)])
    print(f"wrote {out} ({out.stat().st_size} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("boot", help="boot a .trd through the firmware")
    p.add_argument("--trd", required=True)
    p.add_argument("--shot")
    p.add_argument("--frames", type=int, default=500)
    p.set_defaults(func=cmd_boot)

    p = sub.add_parser("script", help="run an evo-run script file")
    p.add_argument("file")
    p.add_argument("--trd")
    p.add_argument("--spg")
    p.add_argument("--shot")
    p.set_defaults(func=cmd_script)

    p = sub.add_parser("play", help="open the playable SDL2 window")
    p.add_argument("--trd")
    p.add_argument("--spg")
    p.add_argument("--scale", type=int, default=1)
    p.set_defaults(func=cmd_play)

    p = sub.add_parser("nvram", help="regenerate the machine's saved settings")
    p.add_argument("--out", default=str(NVRAM))
    p.set_defaults(func=cmd_nvram)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
