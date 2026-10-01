#!/usr/bin/env python3
"""build_toolchain.py - build every binary tool this repo needs into bin/.

Nothing is installed on the host: sources are fetched and compiled under
tmp/, and only the finished binaries are copied into bin/.

    bin/sjasmplus/sjasmplus     the Z80 assembler (github z00m128/sjasmplus)
    bin/evo/evo-run             headless ZX Evolution runner  (tools/evo-emu)
    bin/evo/evo-play            the same machine in an SDL2 window
    bin/evo/lib/libSDL2-*.so    the SDL2 runtime evo-play links against
    bin/nes/retro-run           headless runner for the original NES demo
    bin/nes/fceumm_libretro.so  the NES core it drives
    bin/gen/retro-run           the same binary, for the Mega Drive
    bin/gen/genesis_plus_gx_libretro.so  the Mega Drive core, patched so the
                                video memory the art comes out of can be read
    bin/gen/chiprender          the core's YM2612 alone, replaying a register
                                script to PCM (tools/sega/chiprender/)
    bin/evo/zxevo_baseconf.rom  the ZX Evolution firmware
    bin/evo/gs105a.rom          the General Sound card's ROM

The ZX Evolution frontends are built on **libxpeccy**, the machine library
inside samstyle/Xpeccy: it already models the PentEvo memory manager, the
ATM video modes, the turbo, the Beta Disk interface, TurboSound and the
General Sound card, but only ships a Qt application on top.  Only the
library is used here; the frontends in tools/evo-emu/ are this project's.

evo-play needs SDL2 headers (fetched from the SDL release tarball) and an
SDL2 runtime; both are vendored into bin/evo/lib and reached through an
$ORIGIN rpath, so nothing has to be installed system-wide.

Usage:
    python3 tools/build_toolchain.py [sjasmplus|evo|nes|gen|chiprender|all]
"""

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
SDL_DIR = TMP / "sdl2"   # headers and a runtime, vendored, never installed
BIN = ROOT / "bin"

SJASM_URL = "https://github.com/z00m128/sjasmplus.git"
XPECCY_URL = "https://github.com/samstyle/Xpeccy.git"
ZESARUX_URL = "https://github.com/chernandezba/zesarux.git"
FCEUMM_URL = "https://github.com/libretro/libretro-fceumm.git"
GPGX_URL = "https://github.com/libretro/Genesis-Plus-GX.git"
SDL_VER = "2.32.4"
SDL_URL = f"https://github.com/libsdl-org/SDL/releases/download/release-{SDL_VER}/SDL2-{SDL_VER}.tar.gz"
SDL_SO = "libSDL2-2.0.so.0"


# The ZX Evolution firmware and the General Sound card's ROM.  Neither is
# ours to generate; both ship inside the ZEsarUX distribution, which is the
# only place on this machine they can be had from without a browser.
ROMS = {
    "zxevo_baseconf.rom": "src/zxevo_baseconf.rom",   # BaseConf firmware, 512 KB
    "gs105a.rom":         "src/gs105a.rom",           # General Sound v1.05a
}


def run(cmd, cwd=None):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def clone(url, dest, depth=1, recursive=False):
    if dest.exists():
        print(f"  {dest.relative_to(ROOT)} already there")
        return False
    cmd = ["git", "clone", "--depth", str(depth), "-q"]
    if recursive:
        cmd.append("--recursive")
    run(cmd + [url, dest])
    return True


# ---------------------------------------------------------------- sjasmplus

def build_sjasmplus():
    src = TMP / "sjasmplus"
    clone(SJASM_URL, src, recursive=True)
    run(["make", "-j", str(os.cpu_count() or 2)], cwd=src)
    out = BIN / "sjasmplus"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "sjasmplus", out / "sjasmplus")
    for lic in ("LICENSE.md", "LICENSE"):
        if (src / lic).exists():
            shutil.copy2(src / lic, out / lic)
            break
    print(f"  -> {(out / 'sjasmplus').relative_to(ROOT)}")


# --------------------------------------------------------------------- SDL2

def fetch_sdl():
    """SDL2 headers and a runtime, without touching the host.

    The compiler needs <SDL2/SDL.h>, so the unpacked include/ directory is
    exposed a second time through a symlink literally named SDL2.
    """
    base = SDL_DIR
    inc, lib = base / "include", base / "lib"
    if not (inc / "SDL.h").exists():
        tar = TMP / f"SDL2-{SDL_VER}.tar.gz"
        if not tar.exists():
            print(f"+ fetch {SDL_URL}")
            urllib.request.urlretrieve(SDL_URL, tar)
        base.mkdir(parents=True, exist_ok=True)
        run(["tar", "xzf", tar, "-C", base, "--strip-components=1",
             f"SDL2-{SDL_VER}/include"])
    incdir = base / "include2"
    incdir.mkdir(exist_ok=True)
    if not (incdir / "SDL2").exists():
        (incdir / "SDL2").symlink_to("../include")
    lib.mkdir(parents=True, exist_ok=True)
    target = lib / SDL_SO
    if not target.exists():
        found = None
        for d in ("/usr/lib/x86_64-linux-gnu", "/usr/lib", "/usr/local/lib"):
            cand = Path(d) / SDL_SO
            if cand.exists():
                found = cand
                break
        if not found:
            sys.exit(f"error: no {SDL_SO} on this host; install one or point "
                     f"fetch_sdl() at a copy")
        shutil.copy2(found, target)
    if not (lib / "libSDL2.so").exists():
        (lib / "libSDL2.so").symlink_to(SDL_SO)
    return incdir, lib


# ------------------------------------------------------- ZX Evolution + ROMs

def fetch_roms():
    """Take the BaseConf firmware and the GS ROM out of a ZEsarUX checkout."""
    out = BIN / "evo"
    out.mkdir(parents=True, exist_ok=True)
    if all((out / name).exists() for name in ROMS):
        print("  ROMs already there")
        return
    src = TMP / "zesarux"
    clone(ZESARUX_URL, src)
    for name, rel in ROMS.items():
        shutil.copy2(src / rel, out / name)
        print(f"  -> {(out / name).relative_to(ROOT)}")
    fetch_gs105b()


GS105B_URL = ("https://raw.githubusercontent.com/UzixLS/zx-multisound/"
              "master/rom/gs105b.32K.rom")


def fetch_gs105b():
    """The General Sound ROM v1.05b, which the ZX-MultiSound rev.A1 (the
    card the port is played on) runs: 63 bytes away from 1.05a (the
    version strings, a memory pass that counts pages from $40DA instead of
    $4080, and a sample-end reload in the player) and the game's tunes
    render identically under both.  `evo-run --gsrom bin/evo/gs105b.rom`
    puts it in the emulated card."""
    out = BIN / "evo" / "gs105b.rom"
    if out.exists():
        return
    import urllib.request
    with urllib.request.urlopen(GS105B_URL, timeout=60) as r:
        data = r.read()
    assert len(data) == 32768, "gs105b.32K.rom: not 32 KB"
    out.write_bytes(data)
    print(f"  -> {out.relative_to(ROOT)}")


def patch_sdcard(path):
    """libxpeccy's SD card never leaves multi-block mode: CMD12 is answered
    by a branch that does not clear the flag, and CMD17 falls through
    CMD18's.  After the firmware's CMD18/CMD12 reads, a program's CMD17
    then never ends and its next command is swallowed - the disk loader
    (src/loader/loader.asm) reads one sector at a time and hit exactly
    that.  A real card is fine; this makes the model match it."""
    s = path.read_text()
    if "evo-emu:" in s:
        return
    old = ("\t\tsdcR1(sdc,0);\t\t\t\t// ok\n"
           "\t\tsdc->state = SDC_FREE;")
    new = ("\t\tsdcR1(sdc,0);\t\t\t\t// ok\n"
           "\t\tsdc->cont = 0;\t\t\t\t// evo-emu: a CMD17 after a CMD18 must end\n"
           "\t\tsdc->state = SDC_FREE;")
    assert old in s, "libxpeccy sdcard.c: the CMD12 branch moved"
    s = s.replace(old, new, 1)
    old = ("\t\t\t\tcase CMD18:\t\t\t\t// read multiple block\n"
           "\t\t\t\t\tsdc->cont = 1;\n"
           "\t\t\t\tcase CMD17:\t\t\t\t// read block\n")
    new = ("\t\t\t\tcase CMD17:\t\t\t\t// read block\n"
           "\t\t\t\t\tsdc->cont = 0;\t\t\t// evo-emu: not multiple\n"
           "\t\t\t\t\tgoto sdc_read_block;\n"
           "\t\t\t\tcase CMD18:\t\t\t\t// read multiple block\n"
           "\t\t\t\t\tsdc->cont = 1;\n"
           "\t\t\t\tsdc_read_block:\n")
    assert old in s, "libxpeccy sdcard.c: the CMD17/CMD18 cases moved"
    s = s.replace(old, new, 1)
    path.write_text(s)
    print("  patched libxpeccy sdcard.c (single-block reads end)")


def build_evo():
    src = TMP / "xpeccy"
    fresh = clone(XPECCY_URL, src)
    # libxpeccy keeps its 8086 core in a directory whose name has a space in
    # it; make cannot express a target with a space, so rename it once.
    nec = src / "src/libxpeccy/cpu/NEC V30"
    if nec.exists():
        nec.rename(src / "src/libxpeccy/cpu/NEC_V30")
        cpu_c = src / "src/libxpeccy/cpu/cpu.c"
        cpu_c.write_text(cpu_c.read_text().replace('"NEC V30/v30.h"', '"NEC_V30/v30.h"'))
    del fresh
    patch_sdcard(src / "src/libxpeccy/sdcard.c")
    patch_7ffd(src / "src/libxpeccy/hardware/pentevo.c")
    patch_gs_clock(src / "src/libxpeccy/sound")
    inc, lib = fetch_sdl()
    obj = TMP / "evo-build"
    obj.mkdir(parents=True, exist_ok=True)
    run(["make", "-C", ROOT / "tools/evo-emu",
         f"OUT={obj}", f"LXDIR={src / 'src'}",
         f"SDLINC={inc}", f"SDLLIB={lib}",
         "-j", str(os.cpu_count() or 2)])
    out = BIN / "evo"
    (out / "lib").mkdir(parents=True, exist_ok=True)
    for name in ("evo-run", "evo-play"):
        shutil.copy2(obj / name, out / name)
        (out / name).chmod(0o755)
    shutil.copy2(lib / SDL_SO, out / "lib" / SDL_SO)
    shutil.copy2(src / "LICENSE_eng", out / "LICENSE.libxpeccy")
    fetch_roms()
    print(f"  -> {(out / 'evo-run').relative_to(ROOT)}, "
          f"{(out / 'evo-play').relative_to(ROOT)}")


def patch_7ffd(path):
    """The BaseConf decodes a $7FFD write on A15 = 0 and the low byte $FD
    (or $FC) alone - zports.v: `(a[15]==1'b0) && portfd_wr` - so every
    OUT ($FD),A with A below $80 writes $7FFD, and bit 4 of the value
    picks the memory manager's register set.  libxpeccy asked for A14 = 1
    too (mask $C0FE), which hid exactly that: the profiler's marks, OUT
    ($FD),A with A below $40, were "inert" here and switched every window
    to the firmware's leftover pages on a real machine.  Decode as the
    FPGA does."""
    s = path.read_text()
    if "evo-emu:" in s:
        return
    old = "\t{0xc0fe,0x7ffd,2,2,2,NULL,\tevoOut7FFD},"
    new = "\t{0x80fe,0x7ffd,2,2,2,NULL,\tevoOut7FFD},\t// evo-emu: A15 = 0 alone, as zports.v"
    assert old in s, "libxpeccy pentevo.c: the 7FFD port entry moved"
    path.write_text(s.replace(old, new, 1))
    print("  patched libxpeccy pentevo.c ($7FFD decoded on A15 alone)")


def patch_gs_clock(d):
    """libxpeccy runs the sound card's Z80 at 12 MHz with an interrupt
    every 320 ticks, both hard-coded.  The ZX-MultiSound's runs at 16 MHz
    with the same 37.5 kHz interrupt (its own 12 MHz counter), so the
    ticks between interrupts differ; evo-run's `gsclock MHZ` sets both
    through a field."""
    h, c = d / "gs.h", d / "gs.c"
    s = h.read_text()
    if "evo-emu:" not in s:
        old = "\tint ns_per_tick;"
        assert old in s, "libxpeccy gs.h: ns_per_tick moved"
        h.write_text(s.replace(old, old + "\n\tint int_ticks;\t\t// evo-emu: CPU ticks between interrupts (320 at 12 MHz)", 1))
    s = c.read_text()
    if "evo-emu:" not in s:
        old = "\tres->ns_per_tick = 1000 / GS_FRQ;"
        assert old in s, "libxpeccy gs.c: ns_per_tick moved"
        s = s.replace(old, old + "\n\tres->int_ticks = 320;\t\t// evo-emu: see gs.h", 1)
        old = ("\t\tif (gs->cnt > 320) {\t// 12MHz CLK, 37.5KHz INT -> int in each 320 ticks\n"
               "\t\t\tgs->cnt -= 320;")
        assert s.count(old) == 2, "libxpeccy gs.c: the interrupt counter moved"
        s = s.replace(old, "\t\tif (gs->cnt > gs->int_ticks) {\t// evo-emu: 37.5 kHz at any clock\n\t\t\tgs->cnt -= gs->int_ticks;")
        c.write_text(s)
    print("  patched libxpeccy gs.c/gs.h (the card's clock is a field)")


# ------------------------------------------------- the two reference machines

def build_retro_run(retroinc):
    """The two libretro frontends: `retro-run`, headless and scriptable, and
    `retro-play`, the same machine in an SDL2 window.

    Each core keeps its own libretro.h and they do drift, so this is built
    once per core with RETROINC pointed at that core's copy; a vendored
    header in tools/retro-headless/ is the fallback when the clones are not
    there.  retro-play links SDL2 through an $ORIGIN rpath, the way
    bin/evo/evo-play does, so no system-wide SDL is needed.
    """
    obj = TMP / "retro-headless"
    obj.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "tools/retro-headless").iterdir():
        shutil.copy2(f, obj / f.name)
    incdir, libdir = fetch_sdl()
    run(["make", "-C", obj, f"RETROINC={retroinc}",
         f"SDLINC={incdir}", f"SDLLIB={libdir}"])
    return obj / "retro-run", obj / "retro-play"


def install_retro(binaries, out):
    """Both frontends and the SDL2 the windowed one needs, into bin/nes or
    bin/gen."""
    runner, player = binaries
    (out / "lib").mkdir(parents=True, exist_ok=True)
    for f in (runner, player):
        shutil.copy2(f, out / f.name)
        (out / f.name).chmod(0o755)
    for lib in (SDL_DIR / "lib").glob("libSDL2-2.0.so.0*"):
        shutil.copy2(lib, out / "lib" / lib.name)
    print(f"  -> {(out / 'retro-run').relative_to(ROOT)}, "
          f"{(out / 'retro-play').relative_to(ROOT)}")


def patch_fceumm(src):
    """Let the frontend read the PPU's memory.

    FCEUmm offers the 2 KB of work RAM and nothing else, which is enough for
    a cheat engine and not enough for this project: the port's graphics are
    the NES demo's own, and reading them out means the nametables, the
    palette, the sprite table and whichever 8 KB of CHR the mapper currently
    has banked in.  RETRO_MEMORY_VIDEO_RAM is a standard libretro id the
    core does not answer; the other three are private ids
    tools/retro-headless asks for by number.

    The nametables and the CHR are gathered through the PPU's own pointer
    tables rather than read raw, so mirroring and banking are already
    resolved by the time the frontend sees them.
    """
    p = src / "src/drivers/libretro/libretro.c"
    s = p.read_text()
    if "evo_ppu_snapshot" in s:
        print("  NES core already patched")
        return
    helper = """
/* --- added for zxevo-dune-demo: see .claude/docs/nes-art.md ------------- */
static uint8_t evo_nt_snapshot[0x1000];   /* four nametables, mirroring resolved */
static uint8_t evo_chr_snapshot[0x2000];  /* the 8 KB the PPU can see right now */

static void evo_ppu_snapshot(void)
{
   int i, j;
   for (i = 0; i < 4; i++)
      for (j = 0; j < 0x400; j++)
         evo_nt_snapshot[i * 0x400 + j] = vnapage[i] ? vnapage[i][j] : 0;
   for (i = 0; i < 0x2000; i++)
      evo_chr_snapshot[i] = VPage[i >> 10] ? VPage[i >> 10][i] : 0;
}
/* ----------------------------------------------------------------------- */

void *retro_get_memory_data(unsigned type)"""
    s = s.replace("void *retro_get_memory_data(unsigned type)", helper, 1)
    s = s.replace("""      case RETRO_MEMORY_SYSTEM_RAM:
         data = RAM;
         break;
      default:
         data = NULL;
         break;""", """      case RETRO_MEMORY_SYSTEM_RAM:
         data = RAM;
         break;
      case RETRO_MEMORY_VIDEO_RAM:
         evo_ppu_snapshot();
         data = evo_nt_snapshot;
         break;
      case 0x100:                /* palette RAM: 32 entries into the NES 64 */
         data = PALRAM;
         break;
      case 0x101:                /* the sprite table */
         data = SPRAM;
         break;
      case 0x102:                /* the CHR the mapper has banked in */
         evo_ppu_snapshot();
         data = evo_chr_snapshot;
         break;
      case 0x103:                /* the four PPU registers, as last written */
         data = PPU;
         break;
      default:
         data = NULL;
         break;""", 1)
    # and the sizes
    s = s.replace("""size_t retro_get_memory_size(unsigned type)
{""", """size_t retro_get_memory_size(unsigned type)
{
   switch (type)
   {
      case RETRO_MEMORY_VIDEO_RAM: return 0x1000;
      case 0x100:                  return 0x20;
      case 0x101:                  return 0x100;
      case 0x102:                  return 0x2000;
      case 0x103:                  return 4;
      default: break;
   }""", 1)
    p.write_text(s)
    print("  patched the NES core to expose the nametables, palette, OAM and CHR")


def build_nes():
    src = TMP / "fceumm"
    clone(FCEUMM_URL, src)
    patch_fceumm(src)
    run(["make", "-f", "Makefile.libretro", "-j", str(os.cpu_count() or 2)],
        cwd=src)
    out = BIN / "nes"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "fceumm_libretro.so", out / "fceumm_libretro.so")
    if (src / "LICENSE").exists():
        shutil.copy2(src / "LICENSE", out / "LICENSE")
    install_retro(
        build_retro_run(src / "src/drivers/libretro/libretro-common/include"),
        out)


def patch_gpgx(src):
    """Let the frontend read the VDP's memory, and the Z80's.

    Genesis Plus GX only offers SAVE_RAM and SYSTEM_RAM, which is everything
    a player needs and nothing this project does: the point of running Dune
    II here is to read the tiles and the palettes the real game builds, and
    those live in VRAM and CRAM.  RETRO_MEMORY_VIDEO_RAM is a standard
    libretro id the core simply does not answer; the other four are private
    ids tools/retro-headless asks for by number.  The last of them is the
    Z80's own 8 KB, which is where the sound driver and every byte of its
    state live: without it there is no way to see what the 68000 has asked
    the sound chip for.
    """
    p = src / "libretro/libretro.c"
    s = p.read_text()
    if "case 0x104:" in s:
        print("  Genesis core already patched")
        return
    data = """      case RETRO_MEMORY_VIDEO_RAM:
         return vram;
      case 0x100:                /* colour RAM: 64 nine-bit colours */
         return cram;
      case 0x101:                /* vertical scroll RAM */
         return vsram;
      case 0x102:                /* the VDP's 32 registers */
         return reg;
      case 0x104:                /* the Z80's own 8 KB, the sound driver */
         return zram;
"""
    size = """      case RETRO_MEMORY_VIDEO_RAM:
         return 0x10000;
      case 0x100:
         return 0x80;
      case 0x101:
         return 0x80;
      case 0x102:
         return 0x20;
      case 0x104:
         return 0x2000;
"""
    # An older build patched everything but the Z80, so patch whichever
    # of the two shapes is in front of us - and never both, or the switch
    # ends up with the same case twice and will not compile.
    if "case 0x102:" in s:
        s = s.replace("""      case 0x102:                /* the VDP's 32 registers */
         return reg;
""", data[data.index("      case 0x102:"):], 1)
        s = s.replace("""      case 0x102:
         return 0x20;
""", size[size.index("      case 0x102:"):], 1)
    else:
        s = s.replace("""      case RETRO_MEMORY_SYSTEM_RAM:
         return work_ram;
""", """      case RETRO_MEMORY_SYSTEM_RAM:
         return work_ram;
""" + data, 1)
        s = s.replace("""size_t retro_get_memory_size(unsigned id)
{
   int i;

   switch (id)
   {""", """size_t retro_get_memory_size(unsigned id)
{
   int i;

   switch (id)
   {
""" + size.rstrip("\n"), 1)
    p.write_text(s)
    print("  patched the Genesis core to expose VRAM, CRAM, VSRAM,\n         the VDP and the Z80's 8 KB")


def patch_gpgx_touch(src):
    """Record what the Mega Drive does with every byte of its cartridge.

    A disassembly can only guess which bytes are code and which are data;
    the running machine knows.  This keeps a byte of flags for each of the
    first megabyte of the 68000's address space - the whole cartridge -
    and a longword saying which instruction first read it as data:

        bit 0   an instruction starts here (the opcode was fetched)
        bit 1   fetched as part of an instruction (opcode or extension)
        bit 2   read as data by the 68000, pc-relative reads included
        bit 3   read by the VDP's DMA into VRAM - pixels and maps
        bit 4   read by the Z80 through its window onto the 68000 bus
        bit 5   read by the VDP's DMA into CRAM - colours
        bit 6   read by the VDP's DMA into VSRAM - vertical scroll

    A data read by any of up to eight named instructions is not recorded
    at all (id 0x107): the boot's checksum at $00293C reads the whole
    cartridge, and without this every byte would be "data".

    The reader is the address of the instruction that was executing, with
    bit 31 set so zero can mean "never".  For a DMA that is the write to
    the VDP that started it.  Both are private memory ids the frontend
    asks for by number (0x105, 0x106), like the VDP's memories above.
    """
    # some of the core's files are CRLF and some are not; patch them all
    # as LF and put back whatever each one had
    ends = {}

    def rd(p):
        t = p.read_bytes().decode("latin1")
        ends[p] = "\r\n" in t
        return t.replace("\r\n", "\n")

    def wr(p, t):
        p.write_bytes((t.replace("\n", "\r\n") if ends[p] else t)
                      .encode("latin1"))

    h = src / "core/m68k/m68kcpu.h"
    s = rd(h)
    if "rom_touch" in s:
        print("  Genesis core already records ROM access")
        return
    macro = """
/* ROM access recording - see tools/build_toolchain.py patch_gpgx_touch */
extern unsigned char rom_touch[0x100000];
extern unsigned int rom_reader[0x100000];
extern unsigned int rom_cur_pc;
extern unsigned int rom_blind[8];
static inline void rom_touch_f(unsigned int a, unsigned int n, unsigned int f)
{
  unsigned int i;
  if (f & 4)
    for (i = 0; i < 8 && rom_blind[i]; i++)
      if (rom_blind[i] == rom_cur_pc)
        return;
  a &= 0xFFFFFF;
  for (i = 0; i < n; i++)
    if (a + i < 0x100000)
    {
      rom_touch[a + i] |= f;
      if ((f & 0x7C) && !rom_reader[a + i])
        rom_reader[a + i] = rom_cur_pc | 0x80000000u;
    }
}
#define ROM_TOUCH(A, N, F) rom_touch_f((A), (N), (F))

"""
    anchor = "/* ======================================================================== */\n/* ============================ GENERAL DEFINES"
    assert anchor in s, "m68kcpu.h has moved on"
    s = s.replace(anchor, macro + anchor, 1)
    # pc-relative operands never reach m68ki_read_*: they are read like
    # immediates, so they have to be caught in the macros
    for n, w in (("8", 1), ("16", 2), ("32", 4)):
        s = s.replace(f"#define m68ki_read_pcrel_{n}(A) m68k_read_pcrelative_{n}(A)",
                      f"#define m68ki_read_pcrel_{n}(A) (ROM_TOUCH(A, {w}, 4), "
                      f"m68k_read_pcrelative_{n}(A))")
    # immediates: opcode and extension words, whichever way the core is
    # built to fetch them (it prefetches, so the #else branch is not it)
    for n, w in (("16", 2), ("32", 4)):
        s = s.replace(f"INLINE uint m68ki_read_imm_{n}(void)\n{{\n",
                      f"INLINE uint m68ki_read_imm_{n}(void)\n{{\n"
                      f"  ROM_TOUCH(REG_PC, {w}, 2);\n", 1)
    # data reads
    for n in ("8", "16", "32"):
        w = {"8": 1, "16": 2, "32": 4}[n]
        s = s.replace(f"INLINE uint m68ki_read_{n}(uint address)\n{{\n",
                      f"INLINE uint m68ki_read_{n}(uint address)\n{{\n"
                      f"  ROM_TOUCH(address, {w}, 4);\n", 1)
    wr(h, s)

    c = src / "core/m68k/m68kcpu.c"
    s = rd(c)
    s = s.replace("#include \"m68kcpu.h\"",
                  "#include \"m68kcpu.h\"\n"
                  "unsigned char rom_touch[0x100000];\n"
                  "unsigned int rom_reader[0x100000];\n"
                  "unsigned int rom_blind[8];\n"
                  "unsigned int rom_cur_pc;", 1)
    s = s.replace("""    /* Decode next instruction */
    REG_IR = m68ki_read_imm_16();

    /* 68K bus access refresh delay""", """    /* Decode next instruction */
    rom_cur_pc = REG_PC;
    ROM_TOUCH(REG_PC, 1, 1);
    REG_IR = m68ki_read_imm_16();

    /* 68K bus access refresh delay""", 1)
    # the IRQ-latency path runs one instruction outside the loop, after a
    # write to the VDP's control port - the boot does it at $000D72
    s = s.replace("""      m68ki_use_data_space() /* auto-disable (see m68kcpu.h) */
      REG_IR = m68ki_read_imm_16();
      m68ki_instruction_jump_table[REG_IR]();""", """      m68ki_use_data_space() /* auto-disable (see m68kcpu.h) */
      rom_cur_pc = REG_PC;
      ROM_TOUCH(REG_PC, 1, 1);
      REG_IR = m68ki_read_imm_16();
      m68ki_instruction_jump_table[REG_IR]();""", 1)
    assert s.count("rom_cur_pc = REG_PC") == 2, "m68kcpu.c has moved on"
    wr(c, s)

    v = src / "core/vdp_ctrl.c"
    s = rd(v)
    s = s.replace("""static void vdp_dma_68k_ext(unsigned int length)
{
  uint16 data;
""", """extern unsigned char rom_touch[0x100000];
extern unsigned int rom_reader[0x100000];
extern unsigned int rom_cur_pc;
static void vdp_dma_68k_ext(unsigned int length)
{
  uint16 data;
""", 1)
    # the first read in the function is the one from the cartridge side
    k = s.index("static void vdp_dma_68k_ext(unsigned int length)\n{\n  uint16 data;\n\n  /* 68k")
    old = """      data = *(uint16 *)(m68k.memory_map[source>>16].base + (source & 0xFFFF));
    }
"""
    k = s.index(old, k) + len(old)
    s = s[:k] + """    if (source < 0x100000)
    {
      /* where it went: CD3-CD0 say VRAM (1), CRAM (3) or VSRAM (5) */
      unsigned char f = (code & 0x0F) == 3 ? 32 : (code & 0x0F) == 5 ? 64 : 8;
      rom_touch[source] |= f; rom_touch[source + 1] |= f;
      if (!rom_reader[source]) rom_reader[source] = rom_reader[source + 1] = rom_cur_pc | 0x80000000u;
    }
""" + s[k:]
    assert "rom_touch[source] |= f" in s, "vdp_ctrl.c has moved on"
    wr(v, s)

    z = src / "core/memz80.c"
    s = rd(z)
    s = s.replace("unsigned char z80_memory_r(unsigned int address)\n{",
                  "extern unsigned char rom_touch[0x100000];\n"
                  "extern unsigned int rom_reader[0x100000];\n"
                  "unsigned char z80_memory_r(unsigned int address)\n{", 1)
    s = s.replace("""      address = zbank | (address & 0x7FFF);
      if (zbank_memory_map[address >> 16].read)""", """      address = zbank | (address & 0x7FFF);
      if (address < 0x100000)
      {
        rom_touch[address] |= 16;
        if (!rom_reader[address]) rom_reader[address] = 0xC0000000u;
      }
      if (zbank_memory_map[address >> 16].read)""", 1)
    assert "rom_touch[address] |= 16" in s, "memz80.c has moved on"
    wr(z, s)

    lr = src / "libretro/libretro.c"
    s = rd(lr)
    s = s.replace("""      case 0x104:                /* the Z80's own 8 KB, the sound driver */
         return zram;
""", """      case 0x104:                /* the Z80's own 8 KB, the sound driver */
         return zram;
      case 0x105:                /* what was done with each cartridge byte */
         return rom_touch;
      case 0x106:                /* which instruction first read it */
         return rom_reader;
      case 0x107:                /* up to eight instructions not to count */
         return rom_blind;
""", 1)
    s = s.replace("""      case 0x104:
         return 0x2000;
""", """      case 0x104:
         return 0x2000;
      case 0x105:
         return 0x100000;
      case 0x106:
         return 0x400000;
      case 0x107:
         return 0x20;
""", 1)
    s = s.replace("#include \"shared.h\"",
                  "#include \"shared.h\"\n"
                  "extern unsigned char rom_touch[0x100000];\n"
                  "extern unsigned int rom_reader[0x100000];\n"
                  "extern unsigned int rom_blind[8];", 1)
    assert "case 0x107:" in s, "libretro.c has moved on"
    wr(lr, s)
    print("  patched the Genesis core to record what it does with every "
          "cartridge byte")


def build_gen():
    src = TMP / "gpgx"
    clone(GPGX_URL, src)
    patch_gpgx(src)
    patch_gpgx_touch(src)
    run(["make", "-f", "Makefile.libretro", "-j", str(os.cpu_count() or 2)],
        cwd=src)
    out = BIN / "gen"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "genesis_plus_gx_libretro.so",
                 out / "genesis_plus_gx_libretro.so")
    shutil.copy2(src / "LICENSE.txt", out / "LICENSE")
    install_retro(build_retro_run(src / "libretro/libretro-common/include"),
                  out)
    build_chiprender(src, out)


def build_chiprender(src, out):
    """The core's Nuked OPN2 on its own, for tools/sega/sega_mod.py: it
    renders the Mega Drive's FM instruments into tracker samples."""
    obj = TMP / "chiprender"
    obj.mkdir(parents=True, exist_ok=True)
    snd = src / "core/sound"
    run(["cc", "-O2", "-DHAVE_YM3438_CORE", "-o", obj / "chiprender",
         "-I", snd,
         ROOT / "tools/sega/chiprender/chiprender.c", snd / "ym3438.c"])
    shutil.copy2(obj / "chiprender", out / "chiprender")
    print(f"  -> {(out / 'chiprender').relative_to(ROOT)}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    TMP.mkdir(exist_ok=True)
    BIN.mkdir(exist_ok=True)
    if what in ("all", "sjasmplus"):
        build_sjasmplus()
    if what in ("all", "evo"):
        build_evo()
    if what in ("all", "nes"):
        build_nes()
    if what in ("all", "gen"):
        build_gen()
    if what == "chiprender":
        build_chiprender(TMP / "gpgx", BIN / "gen")
    print("toolchain ready")


if __name__ == "__main__":
    main()
