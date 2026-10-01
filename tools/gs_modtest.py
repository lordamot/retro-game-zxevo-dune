#!/usr/bin/env python3
"""gs_modtest.py - play a .mod through the General Sound card's own ROM
player, in the emulator, and record what comes out.

    python3 tools/gs_modtest.py FILE.mod [--seconds 20] [--wav OUT.wav]

This is the check that a module is *General Sound compatible* rather than
merely a ProTracker file: it builds a small TR-DOS disk (`tmp/modtest/`)
holding `tools/gs_modtest/modtest.asm`, the module cut into pieces and a
BASIC program that feeds them to the card with the ROM's own commands -
`$30` load module, the bytes, `$D2` end of stream, `$31` play - boots it in
`bin/evo/evo-run` with `bin/evo/gs105a.rom` fitted, and records the sound.

It prints how loud the recording is and when the sound starts, and fails
if the card stayed silent.
"""

import argparse
import array
import json
import struct
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp/modtest"
SJASM = ROOT / "bin/sjasmplus/sjasmplus"
EVO = ROOT / "bin/evo"
ORG = 0x7000
PIECE = 16384 - 2               # a piece and its length fit $8000-$BFFF


def basic(pieces):
    """The loader, tokenized - see basic_boot in tools/build_dune.py for
    why TR-DOS commands go through `RANDOMIZE USR 15619: REM:`."""
    CLEAR, RANDOMIZE, USR, VAL, REM, LOAD, CODE = (
        b"\xfd", b"\xf9", b"\xc0", b"\xb0", b"\xea", b"\xef", b"\xaf")

    def num(n):
        return VAL + b' "' + str(n).encode() + b'"'

    def trdos(cmd):
        return (RANDOMIZE + b" " + USR + b" " + num(15619) + b":" + REM
                + b":" + cmd)

    def call(addr):
        return RANDOMIZE + b" " + USR + b" " + num(addr)

    lines = [(10, CLEAR + b" " + num(ORG - 1)),
             (20, trdos(LOAD + b' "modtest"' + CODE)),
             (30, call(ORG))]
    n = 40
    for i in range(pieces):
        lines.append((n, trdos(LOAD + b' "m%d"' % i + CODE)))
        lines.append((n + 10, call(ORG + 3)))
        n += 20
    lines.append((n, call(ORG + 6)))
    out = bytearray()
    for n, body in lines:
        out += (struct.pack(">H", n) + struct.pack("<H", len(body) + 1)
                + body + b"\x0d")
    return bytes(out)


def build(mod, work=TMP):
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([SJASM, "--nologo", f"--raw={work / 'modtest.bin'}",
                    ROOT / "tools/gs_modtest/modtest.asm"], check=True,
                   stdout=subprocess.DEVNULL)
    data = mod.read_bytes()
    pieces = [data[i:i + PIECE] for i in range(0, len(data), PIECE)]
    files = []
    for i, p in enumerate(pieces):
        (work / f"m{i}.bin").write_bytes(struct.pack("<H", len(p)) + p)
        files.append({"name": f"m{i}", "type": "C", "param1": 0x8000,
                      "length": len(p) + 2, "file": f"m{i}.bin"})
    boot = basic(len(pieces))
    (work / "boot.bin").write_bytes(boot)
    code = (work / "modtest.bin").read_bytes()
    manifest = {"label": "MODTEST", "disk_type": 22, "files": [
        {"name": "boot", "type": "B", "param1": len(boot),
         "length": len(boot), "file": "boot.bin"},
        {"name": "modtest", "type": "C", "param1": ORG,
         "length": len(code), "file": "modtest.bin"}] + files}
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2))
    subprocess.run([sys.executable, ROOT / "tools/trd_build.py",
                    work / "manifest.json", work / "modtest.trd", "--force"],
                   check=True, stdout=subprocess.DEVNULL)
    return len(pieces)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mod", type=Path)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--wav", type=Path)
    ap.add_argument("--dir", type=Path, default=TMP,
                    help="where the disk and the script are made")
    args = ap.parse_args()
    work = args.dir
    args.wav = args.wav or work / "modtest.wav"

    pieces = build(args.mod, work)
    # boot and the load take their time; the recording starts at once so
    # the moment the module starts can be read off it
    frames = int(args.seconds * 50) + 250 + 150 * pieces
    script = work / "modtest.script"
    script.write_text(f"wav {args.wav}\nrun 250\npress enter 4\nrun 60\n"
                      f"press enter 4\n"
                      f"run {frames}\nwavstop\n")
    subprocess.run([EVO / "evo-run", "--rom", EVO / "zxevo_baseconf.rom",
                    "--gsrom", EVO / "gs105a.rom",
                    "--nvram", EVO / "evo-nvram.bin",
                    "--trd", work / "modtest.trd", "--script", script,
                    "--quiet"], check=True)

    w = wave.open(str(args.wav))
    rate, ch = w.getframerate(), w.getnchannels()
    a = array.array("h", w.readframes(w.getnframes()))
    mono = [sum(a[i:i + ch]) / ch for i in range(0, len(a), ch)]
    # the card's DACs idle at $80, which is not zero once it is mixed, so
    # loudness is the spread inside a tenth of a second, not the level
    block = rate // 10
    loud = []
    for i in range(0, len(mono) - block + 1, block):
        b = mono[i:i + block]
        m = sum(b) / block
        loud.append((sum((v - m) ** 2 for v in b) / block) ** 0.5)
    print(f"{args.mod.name}: {pieces} pieces, {len(mono) / rate:.1f}s "
          f"recorded -> {args.wav}")
    # the firmware beeps once at about 4.9s; anything after 6s is the card
    heard = [i for i, v in enumerate(loud) if v > 100 and i >= 60]
    if not heard:
        sys.exit(f"{args.mod.name}: silent - the card never played it")
    print(f"  sound from {heard[0] / 10:.1f}s to {heard[-1] / 10:.1f}s, "
          f"loudest {max(loud):.0f} rms, {len(heard) / 10:.1f}s audible")


if __name__ == "__main__":
    main()
