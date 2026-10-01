#!/usr/bin/env python3
"""verify_build.py - the smoke test: does the SPG actually play?

    verify_build.py [--keep DIR]

Builds two debug variants of src/ (tools/build_dune.py --build-dir):
build-verify/ goes straight into the Atreides' first mission with the
sound card left alone, build-verify-snd/ does the same with the sound set
uploaded.  Each is run headless in bin/evo/evo-run, and the machine's own
memory is checked rather than a screenshot trusted.

What it asserts, and why each one is here:

  EGA mode at 14 MHz                  the whole port depends on it, and it
                                      is the first thing to break if the
                                      configuration ports get shut
  the mission loaded                  the player's Construction Yard and
                                      units are there, the houses are in
                                      use and the player has credits
  the counter shows the credits       ui_draw_credits rolled credits_shown
                                      up to the house's credits
  a click gives an order              the cursor is put on one of the
                                      player's vehicles, A pressed, the
                                      cursor moved, A pressed: the unit
                                      must now have the Move order and a
                                      square to go to - and have left
  a building goes down                the Yard builds a Windtrap and A on a
                                      free square next to it places it
  the front end leads to a battle     from power-on, A on every screen;
                                      and a lost mission comes round again
  the battle loop keeps up            passes against frames over 500
                                      frames.  The Mega Drive's pass is a
                                      frame or two; FRAME_BUDGET is what
                                      this port may take.  This port has
                                      once been unplayably slow because of
                                      a one-instruction mistake; this is
                                      what catches the next one.
  the sound card plays                with the sound set uploaded behind
                                      the start-up log, the driver found
                                      the card, the intro's tune played
                                      after it, with nothing loading, and
                                      then gave its pages back, every other
                                      start-up tune is on it, and the
                                      battle's first pass
                                      started a tune from it, heard
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from dune_test import (EVO, ROM, GSROM, NVRAM, PG_UNITS, PG_WORLD, read_sym,  # noqa: E402
                       units, structures, houses, w16)

FRAME_BUDGET = 3.0              # frames a battle pass may take on average
PG_MAIN = 8                     # src/pages.inc: MAIN, gs.asm's state
CODE_BANKS = list(range(8, 24)) + [122]   # every bank with a stub (pages.inc)
SOUND_FRAMES = 1700             # the start-up log is done (about 1450) and
                                # the intro's screen waits for a key, its
                                # tune playing
SOUND_AFTER = 700               # a key: the intro's tune fades, the tunes it
                                # kept off the card go on, the battle starts
PLAYER = 1                      # Atreides
UNIT_MCV, UNIT_HARVESTER = 17, 16
FOOT = (2, 3, 4, 5, 6)          # the foot soldiers
SCREEN_X, SCREEN_Y = 64, 88     # where a screenshot's picture starts (2x)

failures = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        failures.append(what)


def build(build_dir, flags):
    r = subprocess.run([sys.executable, ROOT / "tools/build_dune.py",
                        "--build-dir", build_dir, "--house", "A",
                        "--mission", "1", "--flags", str(flags)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"verify: the build failed\n{r.stdout}{r.stderr}")
    return read_sym(Path(build_dir) / "dune.sym")


def evo(lines, tmp):
    script = tmp / "v.script"
    script.write_text("\n".join(lines) + "\n")
    r = subprocess.run([str(EVO), "--rom", str(ROM), "--gsrom", str(GSROM),
                        "--script", str(script)], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"verify: evo-run failed\n{r.stderr}")
    return r.stdout


def peeks(out):
    """'ADDR: b b ...' lines of a run -> {addr: bytes}."""
    got = {}
    for line in out.splitlines():
        m = re.match(r"([0-9A-F]{4}): ((?:[0-9A-F]{2} ?)+)$", line.strip())
        if m:
            got[int(m.group(1), 16)] = bytes(int(x, 16) for x in m.group(2).split())
    return got


def battle(tmp):
    print("battle (Atreides 1, no sound):")
    d = ROOT / "build-verify"
    sym = build(d, 8)
    spg = d / "DUNE.DAT"

    def pk(name, n=2):
        return f"peek 0x{sym[name]:04X} {n}"

    # first run: where things are after 100 frames
    out = evo([f"spg {spg}", "run 100", "state",
               f"page {PG_UNITS} {tmp}/u0.bin", f"page {PG_WORLD} {tmp}/w0.bin"], tmp)
    st = [l for l in out.splitlines() if l.startswith("pc=")][-1]
    check("video=ega16c" in st, "EGA mode (" + st.split()[2] + ")")
    check("turbo=4.0" in st, "14 MHz (" + st.split()[3] + ")")
    u0, w0 = (tmp / "u0.bin").read_bytes(), (tmp / "w0.bin").read_bytes()
    us, ss, hs = units(u0), structures(w0), houses(u0)
    mine = [u for u in us if u["house"] == PLAYER]
    check(any(s["house"] == PLAYER and s["type"] == 8 for s in ss),
          "the player's Construction Yard is there")
    check(len(mine) >= 2, f"the player has units ({len(mine)})")
    check(any(h["house"] == PLAYER and h["credits"] > 0 for h in hs),
          "the player has credits")
    view_x = w16(w0, sym["view_x"] - 0x8000)
    view_y = w16(w0, sym["view_y"] - 0x8000)

    # a vehicle on the screen to give an order to
    cand = [u for u in mine if u["type"] not in FOOT + (UNIT_MCV,)
            and 16 <= u["x"] // 8 - view_x < 300 and 16 <= u["y"] // 8 - view_y < 184]
    check(bool(cand), "a player's vehicle is on the screen")

    # second run: the same, the order, then 500 frames timed
    lines = [f"spg {spg}", "run 100"]
    target = None
    if cand:
        u = cand[0]
        cx, cy = u["x"] // 8 - view_x, u["y"] // 8 - view_y
        tx = cx + (64 if cx < 160 else -64)
        ty = cy
        target = ((u["y"] // 256) + (ty - cy) // 32, (u["x"] // 256) + (tx - cx) // 32)
        cxa = sym["cursor_x"]
        lines += [f"poke 0x{cxa:04X} {cx & 255}", f"poke 0x{cxa + 1:04X} {cx >> 8}",
                  f"poke 0x{cxa + 2:04X} {cy & 255}", f"poke 0x{cxa + 3:04X} {cy >> 8}",
                  "run 4", "press space 2", "run 4", pk("unit_selected", 1),
                  f"poke 0x{cxa:04X} {tx & 255}", f"poke 0x{cxa + 1:04X} {tx >> 8}",
                  "run 4", "press space 2", "run 4",
                  f"page {PG_UNITS} {tmp}/u1.bin"]
    lines += [pk("frame_count"), pk("pass_count"), "run 500",
              pk("frame_count"), pk("pass_count"),
              f"page {PG_UNITS} {tmp}/u2.bin", f"page {PG_WORLD} {tmp}/w2.bin",
              f"shot {tmp}/battle.bmp"]
    lines += [f"page {p} {tmp}/bank{p}.bin" for p in CODE_BANKS]
    out = evo(lines, tmp)
    fc = sym["frame_count"]
    pc = sym["pass_count"]
    vals = []
    for line in out.splitlines():
        m = re.match(r"([0-9A-F]{4}): ([0-9A-F]{2}) ([0-9A-F]{2})$", line.strip())
        if m and int(m.group(1), 16) in (fc, pc):
            vals.append(int(m.group(3) + m.group(2), 16))
    if len(vals) == 4:
        frames = (vals[2] - vals[0]) & 0xFFFF
        passes = (vals[3] - vals[1]) & 0xFFFF
        rate = frames / passes if passes else 99
        check(rate <= FRAME_BUDGET,
              f"the loop keeps up: {passes} passes in {frames} frames, "
              f"{rate:.2f} frames a pass (budget {FRAME_BUDGET})")
    else:
        check(False, "the loop keeps up (counters not read)")
    if cand:
        u = cand[0]
        sel = [v for a, v in peeks(out).items() if a == sym["unit_selected"]]
        check(bool(sel) and sel[0][0] == u["slot"], f"A selects unit {u['slot']}")
        after = {x["slot"]: x for x in units((tmp / "u1.bin").read_bytes())}.get(u["slot"])
        ok = after and after["order"] == 1 and (after["tmove"] >> 14) == 3
        check(bool(ok), "A again gives it Move to a square"
              + (f" (order {after['order']}, targetMove ${after['tmove']:04X})" if after else ""))
        later = {x["slot"]: x for x in units((tmp / "u2.bin").read_bytes())}.get(u["slot"])
        moved = later and (later["x"], later["y"]) != (u["x"], u["y"])
        check(bool(moved), "and it drives off")
    w2 = (tmp / "w2.bin").read_bytes()
    shown = w16(w2, sym["credits_shown"] - 0x8000) | (w16(w2, sym["credits_shown"] - 0x7FFE) << 16)
    cred2 = next((h["credits"] for h in houses((tmp / "u2.bin").read_bytes())
                  if h["house"] == PLAYER), 0)
    check(shown == cred2, f"the counter shows the credits ({shown} of {cred2})")
    # the stub is code only, the same in every bank: a write into it (a
    # pointer gone wrong with window 0 mapped) shows up as a crash much
    # later, somewhere else; here it shows up as a bank whose stub differs
    stub = sym["stub_end"]
    main_stub = (tmp / f"bank{PG_MAIN}.bin").read_bytes()[:stub]
    odd = [p for p in CODE_BANKS
           if (tmp / f"bank{p}.bin").read_bytes()[:stub] != main_stub]
    check(not odd, "every bank's stub is still MAIN's"
          + (f" (not {odd})" if odd else ""))
    try:
        from PIL import Image
        Image.open(tmp / "battle.bmp").save(ROOT / "tmp/verify-battle.png")
    except Exception:                           # noqa: BLE001
        pass


def placing(tmp):
    """The player opens the Yard's build panel, takes the Windtrap, leaves,
    and when it is done puts it down below the Yard: all by the keys."""
    print("building (Atreides 1):")
    from dune_test import Machine
    d = ROOT / "build-verify"
    m = Machine(build_dir=d, battle=100)
    # A on the Yard twice opens its build panel; the Windtrap is the
    # second item on the row under EXIT FIX STOP
    ycx, ycy = 24 * 32 - 640 + 16, 35 * 32 - 1024 + 16
    m.poke_label("unit_selected", [0xFF])
    m.poke_label("cursor_x", [ycx & 255, ycx >> 8, ycy & 255, ycy >> 8])
    m.lines += ["run 6", "press space 3", "run 10", "press space 3", "run 60",
                "press a 2", "run 10", "press p 2", "run 10",
                "press space 3", "run 30"]
    m.run_frames(3000)
    m.lines.append(f"page {PG_WORLD} {{tmp}}/s0_p{PG_WORLD}.bin")
    m.poke_label("unit_selected", [0xFF])
    m.poke_label("struct_selected", [0])
    view_x, view_y = 640, 1024                  # where A1 opens
    cx, cy = 24 * 32 - view_x + 16, 37 * 32 - view_y + 16
    m.poke_label("cursor_x", [cx & 255, cx >> 8, cy & 255, cy >> 8])
    m.lines += ["run 10", "press space 2", "run 60",
                f"page {PG_WORLD} {tmp}/w_place.bin"]
    r = m.run(keep=tmp / "place")
    before = {s["slot"]: s for s in structures(r.page(0, PG_WORLD))}
    wt = [s for s in before.values() if s["type"] == 9]
    check(bool(wt) and before[0]["state"] == 2,
          "the build panel starts a Windtrap and the Yard finishes it")
    after = [s for s in structures((tmp / "w_place.bin").read_bytes()) if s["type"] == 9]
    ok = after and (after[0]["y"] >> 8, after[0]["x"] >> 8) == (37, 24)
    check(bool(ok), "A puts it down below the Yard" +
          (f" (at {after[0]['x'] >> 8},{after[0]['y'] >> 8})" if after else ""))


def front(tmp):
    """From power-on: the logos, the title, START GAME, the Atreides crest,
    YES, the briefing and PROCEED, all by pressing A, must end in a battle;
    losing it (the Yard destroyed through the mailbox) must go through the
    defeat and score screens back to the same mission's battle."""
    print("front end (no --house):")
    from dune_test import Machine
    d = ROOT / "build-verify-front"
    r = subprocess.run([sys.executable, ROOT / "tools/build_dune.py",
                        "--build-dir", d, "--flags", "8"],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"verify: the build failed\n{r.stdout}{r.stderr}")
    sym = read_sym(d / "dune.sym")
    pc = sym["pass_count"] - 0x8000
    lines = [f"spg {d / 'DUNE.DAT'}"]
    for _ in range(14):
        lines += ["run 150", "press space 3"]
    lines += ["run 300", f"page {PG_WORLD} {tmp}/f1.bin",
              f"page {PG_UNITS} {tmp}/f1u.bin"]
    evo(lines, tmp)
    w = (tmp / "f1.bin").read_bytes()
    passes = w16(w, pc)
    mine = [s for s in structures(w) if s["house"] == PLAYER]
    check(passes > 50 and bool(mine),
          f"A through the front end reaches Atreides 1 ({passes} passes)")
    # lose it: the Yard's hit points to 0 and struct_destroy, then A on
    # every screen until the battle runs again
    m = Machine(build_dir=d, battle=1)
    m.lines = lines[:-2]
    yard = next((s for s in mine if s["type"] == 8), None)
    if yard is None:
        check(False, "a lost mission comes back")
        return
    a = 0x8100 + yard["slot"] * 0x62
    m.poke_page(PG_WORLD, a - 0x8000 + 0x12, [0, 0])
    m.call("struct_destroy", ix=a, frames=10)
    for _ in range(16):
        m.lines += ["run 150", "press space 3"]
    m.lines += ["run 300", f"page {PG_WORLD} {tmp}/f2.bin"]
    m.run(keep=tmp / "front")
    w2 = (tmp / "f2.bin").read_bytes()
    back = [s for s in structures(w2) if s["house"] == PLAYER and s["type"] == 8]
    check(bool(back) and w2[sym["scenario_id"] - 0x8000] == 1,
          "a lost mission goes through the defeat and score screens and "
          "starts again")


def disk(tmp):
    """The way a real machine starts it: the firmware boots dune.trd, whose
    loader reads DUNE.DAT off the card - a FAT16 one and a FAT32 one - and
    the game must be running in its EGA screen soon after."""
    print("disk boot (dune.trd, DUNE.DAT on a card):")
    d = ROOT / "build-verify-front"          # built by front()
    for kind in ("fat16", "fat32"):
        img = tmp / f"card_{kind}.img"
        r = subprocess.run([sys.executable, ROOT / "tools/sd_image.py", img]
                           + (["--fat32"] if kind == "fat32" else [])
                           + [d / "DUNE.DAT"], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"verify: sd_image.py failed\n{r.stdout}{r.stderr}")
        script = tmp / f"disk_{kind}.script"
        script.write_text("run 250\npress enter 4\nrun 60\npress enter 4\n"
                          "run 300\nstate\nrun 1200\nstate\n")
        r = subprocess.run([str(EVO), "--rom", str(ROM), "--gsrom", str(GSROM),
                            "--nvram", str(NVRAM), "--trd", str(d / "dune.trd"),
                            "--sd", str(img), "--script", str(script), "--quiet"],
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"verify: evo-run failed\n{r.stderr}")
        states = [l for l in r.stdout.splitlines() if l.startswith("pc=")]
        loading = "video=zx" in states[0] and " sp=5F" in states[0]
        running = "video=ega16c" in states[-1]
        check(loading and running,
              f"{kind}: the loader runs, the game is in its screen 30 s after boot")


def sound(tmp):
    """The card is found and loaded behind the start-up log (about 29 s
    of 2 MB: the memory test, the effects, the intro and twelve tunes),
    the intro's screen waits for a key, its tune playing, the battle then
    starts its first tune at its first pass, from the card, and it is
    heard.  sound_on is no proof: the switches are on with no card too."""
    print("sound (Atreides 1, the sound set uploaded):")
    d = ROOT / "build-verify-snd"
    sym = build(d, 0)
    out = evo([f"spg {d / 'DUNE.DAT'}", f"run {SOUND_FRAMES}",
               f"page {PG_MAIN} {tmp}/intro.bin",
               "press space 3", f"run {SOUND_AFTER}",
               f"page {PG_MAIN} {tmp}/main.bin",
               f"wav {tmp}/battle.wav", "run 100", "wavstop"], tmp)
    intro = sym["MUS_INTRO"]
    i = (tmp / "intro.bin").read_bytes()
    nb = i[sym["gs_nboot"]]
    loaded = all(i[sym["gs_tst"] + t] == 2
                 for t in i[sym["gs_boot"]:sym["gs_boot"] + nb])
    check(i[sym["gs_cur"]] == intro and not i[sym["gs_wait"]]
          and i[sym["snd_shown"]] == 1 and loaded
          and i[sym["gs_ld"]] == 0xFF,
          "the start-up set all on the card before the intro's tune plays, "
          "and nothing loading under it")
    m = (tmp / "main.bin").read_bytes()
    check(m[sym["gs_ok"]] == 1, "the card was found and loaded")
    nboot = m[sym["gs_nboot"]]
    boot = m[sym["gs_boot"]:sym["gs_boot"] + nboot]
    tst = m[sym["gs_tst"]:sym["gs_tst"] + 64]
    on = [t for t in range(64) if tst[t] == 2]
    check(nboot >= 12 and tst[intro] == 0 and len(on) >= 12
          and tst[sym["MUS_STARPORT"]] == 2,
          f"{nboot} tunes put on the card at start-up; after the intro "
          f"{len(on)} there, the Tutorial's among them, the intro's gone")
    cur, wait = m[sym["gs_cur"]], m[sym["gs_wait"]]
    check(cur in boot and not wait,
          f"the battle's first tune plays from the card at once (MUS {cur})")
    import wave
    import array
    with wave.open(str(tmp / "battle.wav")) as w:
        s = array.array("h", w.readframes(w.getnframes()))
    rms = (sum(x * x for x in s) / max(len(s), 1)) ** 0.5
    check(rms > 300, f"the battle music plays (level {rms:.0f})")


def nocard(tmp):
    """No sound card: the start-up log says "error" and "no sound", waits
    for a key, the intro shows silent, and the battle runs with the card
    given up (gs_ok 0, gs_dead 1)."""
    print("no card (Atreides 1, the card answers nothing):")
    d = ROOT / "build-verify-nocard"
    sym = build(d, 0)

    def pk(name, n=1):
        return f"peek 0x{sym[name]:04X} {n}"
    out = evo(["gsdead", f"spg {d / 'DUNE.DAT'}", "run 150",
               f"page {PG_MAIN} {tmp}/nc0.bin",
               "press space 3", "run 300", "press space 3", "run 900",
               pk("pass_count", 2), "run 200", pk("pass_count", 2),
               f"page {PG_MAIN} {tmp}/nc1.bin", f"page {PG_WORLD} {tmp}/nc1w.bin",
               "state"], tmp)
    m0 = (tmp / "nc0.bin").read_bytes()
    check(m0[sym["gs_ok"]] == 0 and m0[sym["snd_shown"]] == 0,
          "the card is not found and the log waits at \"no sound\"")
    m1 = (tmp / "nc1.bin").read_bytes()
    w1 = (tmp / "nc1w.bin").read_bytes()
    check(m1[sym["gs_ok"]] == 0 and m1[sym["gs_dead"]] == 1
          and w1[sym["sound_on"] - 0x8000] == 1,
          "a key: the start-up goes on with the card given up, the switches on")
    pc = sym["pass_count"]
    passes = [int(m.group(2) + m.group(1), 16) for m in
              (re.match(rf"{pc:04X}: ([0-9A-F]{{2}}) ([0-9A-F]{{2}})$", l.strip())
               for l in out.splitlines()) if m]
    st = [l for l in out.splitlines() if l.startswith("pc=")][-1]
    check("video=ega16c" in st and len(passes) == 2 and passes[1] != passes[0],
          "the intro passed silent and the battle runs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", help="keep the run's files in this directory")
    ap.add_argument("--no-sound", action="store_true", help="skip the sound run")
    args = ap.parse_args()
    tmp = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="verify_"))
    tmp.mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp").mkdir(exist_ok=True)
    battle(tmp)
    placing(tmp)
    front(tmp)
    disk(tmp)
    if not args.no_sound:
        sound(tmp)
        nocard(tmp)
    if failures:
        print(f"verify: {len(failures)} check(s) failed")
        sys.exit(1)
    print("verify: all checks passed (screenshot: tmp/verify-battle.png)")


if __name__ == "__main__":
    main()
