#!/usr/bin/env python3
"""build_dune.py - src/ -> build/DUNE.DAT (and dune.trd, the disk that
loads it).

    build_dune.py [--out build/DUNE.DAT] [--house H] [--mission N]
                  [--flags N] [--credits N]

The steps, each writing into build/:

  1. the generated includes and data pages (tools/dune_data.py for the
     game's tables, missions, maps, scripts and texts; tools/dune_art.py
     for the pictures; tools/dune_sound.py for the sound) - each only if
     its tool is there;
  2. sjasmplus src/dune.asm, which saves every page it fills into
     build/pages/pNNN.bin and names every label in build/dune.sym;
  3. the checks: every code bank starts with the same stub, byte for byte
     (far_call switches banks from inside the stub, so they must agree);
  4. the debug block in page WORLD, set from the command line;
  5. build/DUNE.DAT - the game as one SPG-format file, starting at the
     boot stub in page 2, $8000 (the disk's loader reads it by that name;
     there is no dune.spg any more).
  6. build/dune.trd and build/DUNE.DAT (tools/dune_trd.py): the disk the
     BaseConf firmware boots, whose loader reads DUNE.DAT - the SPG - off
     the SD card.

.claude/docs/port.md and build.md say why it is shaped like this.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from spg import write_spg                                  # noqa: E402
import dune_trd                                            # noqa: E402

SRC = ROOT / "src"
BUILD = ROOT / "build"          # --build-dir moves all three
PROFILE = False                 # --profile: the PROF marks assembled in
INTRO_MOD = None                # --intro-mod: another module as the intro's
GEN = BUILD / "gen"
PAGES = BUILD / "pages"
SJASM = ROOT / "bin/sjasmplus/sjasmplus"

# EGA palette byte for a colour with 2-bit channels: the value is sent
# inverted, green's and red's and blue's two bits spread over the byte as
# bit 7 g0, 6 r0, 5 b0, 4 g1, 1 r1, 0 b1 (.claude/docs/platform.md).
def ega_palette_byte(r, g, b):
    v = ((g & 1) << 7) | ((r & 1) << 6) | ((b & 1) << 5) | ((g >> 1) << 4) \
        | ((r >> 1) << 1) | (b >> 1)
    return v ^ 0xFF


TEST_PALETTE = [(0, 0, 0), (0, 0, 2), (2, 0, 0), (2, 0, 2), (0, 2, 0),
                (0, 2, 2), (2, 2, 0), (2, 2, 2), (1, 1, 1), (0, 0, 3),
                (3, 0, 0), (3, 0, 3), (0, 3, 0), (0, 3, 3), (3, 3, 0),
                (3, 3, 3)]


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode:
        sys.exit(f"build: {' '.join(str(c) for c in cmd)} failed")


# Where each of tools/dune_data.py's tables goes (see .claude/docs/port.md):
#   world    page WORLD, window 2 - the big record tables every bank reads
#   hot      straight after the stub in every logic bank, identically
#   <bank>   in that one bank only
# A table not named here is an error, so a new table has to be placed.
TABLE_SECTIONS = {
    "world": """unit_info struct_info house_info landscape actions
        icon_landscape""",
    "hot": """playable_area scale_offset crater tile_step_dir8 direction_packed
        map_pos_step_x map_pos_step_y path_smooth spice_ring spice_nesw
        fog_nesw neighbour8 neighbour9 mcv_squares layout_tiles layout_edge
        layout_count layout_around layout_size layout_centre layout_centre8
        layout_bottom slab_bits slab_flags wall_nesw struct_pos_offsets
        struct_anim_numbers unit_side_list struct_side_list house_side
        death_hand fremen_types fremen_count sin cos cot atan_quadrant
        quarter_sine""",
    "game1": "square_sample square_sample_half",
    "game3": """icon_map wall_mask wall_mask_values struct_icon_sets struct_anim
        icon_anim_ptr icon_anim overlay_stamp""",
    "render": """unit_frame_8 unit_frame_8b unit_frame_16 infantry_walk
        unit_sprite_nibble effect_ptr effect_scripts""",
    "main": "effect_song music voice_song song_start_now",
    "scen": "section_house team_actions movement_letters",
    "ui": """layout_cursor layout_cursor_frame radar_icon_colour
        radar_house_colour radar_house_pixels radar_border_colour""",
    "front": """rank_scores briefing_first campaign_attr campaign_attack_pal
        campaign_owner""",
}


ALIGNED_TABLES = {"radar_icon_colour"}    # indexed by a register's low byte (ui.asm rd_colours)


def split_tables():
    """build/gen/tables.inc -> tbl_equ.inc (every EQU) and tbl_<section>.inc
    (the data of the tables placed in that section)."""
    where = {}
    for sec, names in TABLE_SECTIONS.items():
        for n in names.split():
            assert n not in where, n
            where[n] = sec
    src = (GEN / "tables.inc").read_text().splitlines()
    equ, secs, cur = [], {k: [] for k in TABLE_SECTIONS}, None
    for line in src:
        m = re.match(r"; ---- tbl_(\w+):", line)
        if m:
            name = m.group(1)
            if name not in where:
                sys.exit(f"build: table tbl_{name} is not placed in TABLE_SECTIONS")
            cur = where[name]
            secs[cur].append(line)
            continue
        if re.match(r"\w+\s+EQU\s", line) and not re.match(r"tbl_\w+ EQU tbl_", line):
            equ.append(line)
        elif cur is None:
            equ.append(line)
        else:
            m = re.match(r"tbl_(\w+):", line)
            if m and m.group(1) in ALIGNED_TABLES:
                secs[cur].append("        ALIGN 256")
            secs[cur].append(line)
    (GEN / "tbl_equ.inc").write_text("\n".join(equ) + "\n")
    for sec, lines in secs.items():
        (GEN / f"tbl_{sec}.inc").write_text("\n".join(lines) + "\n")


PG_SOUND = 128                  # src/pages.inc


def gen_includes():
    GEN.mkdir(parents=True, exist_ok=True)
    (GEN / "test_palette.inc").write_text(
        "        DB " + ", ".join(f"${ega_palette_byte(*c):02X}"
                                  for c in TEST_PALETTE) + "\n")
    (GEN / "savepages.inc").write_text("".join(
        f'        SAVEDEV "{PAGES}/p{n:03d}.bin", {n}, 0, $4000\n'
        for n in [2] + list(range(8, 40)) + [122]))
    run([sys.executable, ROOT / "tools/dune_data.py", GEN])
    split_tables()
    art_in = [ROOT / "tools/dune_art.py"] + sorted((ROOT / "src/res/art").rglob("*"))
    art_out = GEN / "art.inc"
    if not art_out.exists() or max(f.stat().st_mtime for f in art_in) > art_out.stat().st_mtime:
        run([sys.executable, ROOT / "tools/dune_art.py", "--out", GEN])
    # the sound set for the General Sound card (pages PG_SOUND on)
    intro = INTRO_MOD or ROOT / "src/res/external.mod"
    snd_in = [ROOT / "tools/dune_sound.py", ROOT / "src/res/sega_sound.txt",
              intro] + \
        sorted((ROOT / "src/res/prebuilt").rglob("*"))
    snd_out = GEN / "sound.inc"
    if INTRO_MOD or not snd_out.exists() or max(f.stat().st_mtime for f in snd_in) > snd_out.stat().st_mtime:
        run([sys.executable, ROOT / "tools/dune_sound.py", "--out", GEN,
             "--base-page", str(PG_SOUND), "--intro", intro])
        for f in GEN.glob("page_*.bin"):        # a smaller set leaves none behind
            if int(f.stem[5:]) >= PG_SOUND:
                f.unlink()
        blob = (GEN / "sound.bin").read_bytes()
        for k in range(0, len(blob), 0x4000):
            chunk = blob[k:k + 0x4000]
            (GEN / f"page_{PG_SOUND + k // 0x4000:03d}.bin").write_bytes(
                chunk + bytes(0x4000 - len(chunk)))
    # the front end's pictures (tools/dune_front.py, pages PG_FRONT_ART on)
    front = ROOT / "tools/dune_front.py"
    if front.exists():
        # its pictures, its index beside them, the tools it imports or calls
        # (dune_art.py, dune_tutorial.py), and the sound ids it bakes into
        # its music and effect tables
        front_in = [front, ROOT / "src/res/art/ui.txt", ROOT / "tools/dune_art.py",
                    ROOT / "tools/dune_tutorial.py", ROOT / "tools/font_cyr.py"] \
            + [f for f in [GEN / "sound_ids.inc"] if f.exists()] \
            + sorted((ROOT / "src/res/art/ui").rglob("*"))
        front_out = GEN / "front.inc"
        if not front_out.exists() or max(f.stat().st_mtime for f in front_in) > front_out.stat().st_mtime:
            run([sys.executable, front, "--out", GEN])
    else:
        (GEN / "front.inc").write_text("; no tools/dune_front.py yet\n")


def assemble():
    PAGES.mkdir(parents=True, exist_ok=True)
    for f in PAGES.glob("p*.bin"):
        f.unlink()
    run([SJASM, "--nologo", "--msg=war",
         f"--sym={BUILD / 'dune.sym'}", f"--lst={BUILD / 'dune.lst'}",
         f"--sld={BUILD / 'dune.sld'}",
         f"-I{SRC}", f"-I{GEN}"]
        + (["-DPROFILE=1"] if PROFILE else []) + ["dune.asm"], cwd=SRC)


def write_bank_of():
    """build/bank_of.txt: every global label and the page it was assembled
    in (from the SLD file), for tools/dune_test.py."""
    out = []
    for line in (BUILD / "dune.sld").read_text().splitlines():
        f = line.split("|")
        if len(f) >= 8 and f[6] == "F" and "." not in f[7] and int(f[4]) >= 0:
            out.append(f"{f[7]} {f[4]}")
    (BUILD / "bank_of.txt").write_text("\n".join(sorted(set(out))) + "\n")


def read_sym():
    sym = {}
    for line in (BUILD / "dune.sym").read_text().splitlines():
        m = re.match(r"(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)", line)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
    return sym


def load_pages():
    pages = {}
    for f in sorted(PAGES.glob("p*.bin")):
        pages[int(f.stem[1:])] = bytearray(f.read_bytes())
    for f in sorted(GEN.glob("page_*.bin")):      # data pages from the tools
        n = int(f.stem.split("_")[1])
        if n > 0xDF:
            # a tool's page from an earlier layout: nothing may sit above
            # #DF (the SPG loaders live there), so it can only be stale
            print(f"build: removing stale {f.name} (no page above #DF)")
            f.unlink()
            continue
        assert n not in pages, f"page {n} is filled twice"
        pages[n] = bytearray(f.read_bytes())
    return pages


def check_stubs(pages, sym):
    size = sym["stub_end"]
    main = pages[sym["PG_MAIN"]][:size]
    banks = [v for k, v in sym.items() if k.startswith("PG_")
             and k not in ("PG_UNITS", "PG_WORLD", "PG_MAP", "PG_BOOT")
             and v in pages and (8 <= v < 24 or v == sym.get("PG_PANEL"))]
    banks = [b for b in banks if any(pages[b][:size])]
    for b in banks:
        if pages[b][:size] != main:
            sys.exit(f"build: the stub in page {b} differs from PG_MAIN's")
    return len(banks), size


def boot_clear_table(pages, sym):
    """boot.asm's table of what to zero at start: every page below #E0
    the SPG has no block for, from unit 0, and every page's tail beyond
    what write_spg keeps (it trims a page to its last non-zero byte, in
    512-byte units).  The boot page itself is left alone: the stack is
    in it, and nothing else."""
    boot = sym["PG_BOOT"]
    table = bytearray()
    for p in range(0xE0):
        if p == boot:
            continue
        data = pages.get(p, b"")
        end = (len(bytes(data).rstrip(b"\0")) + 511) // 512
        if end < 32:
            table += bytes([p, end])
    table += b"\xff"
    off = sym["boot_clear_table"] - 0x8000
    room = 2 * 224 + 1
    assert len(table) <= room, f"the boot's clear table needs {len(table)} bytes"
    pages[boot][off:off + len(table)] = table


def set_debug(pages, sym, args):
    world = pages[sym["PG_WORLD"]]
    off = sym["dbg_block"] - 0x8000
    assert world[off:off + 4] == b"DBG0"
    if args.house is not None:
        world[off + 4] = "HAO".index(args.house.upper()[0]) \
            if args.house[0].isalpha() else int(args.house)
        world[off + 5] = args.mission
    world[off + 6] = args.flags
    world[off + 7:off + 9] = args.credits.to_bytes(2, "little")
    world[off + 9] = args.flags2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-dir", help="build here instead of build/ (the"
                    " SPG, the symbols and every generated file)")
    ap.add_argument("--out")
    ap.add_argument("--house", help="start straight in a battle: H, A or O")
    ap.add_argument("--mission", type=int, default=1)
    ap.add_argument("--flags", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--credits", type=int, default=0)
    ap.add_argument("--intro-mod", type=Path,
                    help="play this module as the intro's instead of "
                    "src/res/external.mod (a test build; tools/gs_chantest.py "
                    "makes one that sounds the card's four channels in turn)")
    ap.add_argument("--flags2", type=lambda s: int(s, 0), default=0,
                    help="the second debug byte: 1 the sound card taken for "
                    "1 MB, the intro and the lego tune only, nothing streamed")
    ap.add_argument("--profile", action="store_true",
                    help="assemble the profiler's marks in (src/evo.inc PROF: "
                    "OUT ($FD),A, which writes $7FFD on a real machine - "
                    "for bin/evo/evo-run --profile only)")
    args = ap.parse_args()
    global BUILD, GEN, PAGES, PROFILE, INTRO_MOD
    PROFILE = args.profile
    INTRO_MOD = args.intro_mod.resolve() if args.intro_mod else None
    if args.build_dir:
        BUILD = Path(args.build_dir).resolve()
        GEN = BUILD / "gen"
        PAGES = BUILD / "pages"
    if not args.out:
        args.out = str(BUILD / "DUNE.DAT")

    gen_includes()
    assemble()
    write_bank_of()
    sym = read_sym()
    pages = load_pages()
    nb, stub = check_stubs(pages, sym)
    set_debug(pages, sym, args)
    assert not any(pages.get(5, b"")), "page 5 is the disk loader's: it must stay empty"
    boot_clear_table(pages, sym)
    blocks, size = write_spg(args.out, pages, pc=sym["boot"], sp=0xBFFE,
                             page3=0, clock=2)
    code = sum(len(pages[p].rstrip(b"\0")) for p in pages if 8 <= p < 24)
    print(f"{args.out}: {size} bytes, {blocks} blocks; {nb} code banks, "
          f"stub {stub} bytes, {code} bytes of code")
    # the disk the firmware boots, and the SPG under the loader's name
    trd, dat, n = dune_trd.build(Path(args.out), Path(args.out).parent)
    print(f"{trd}: loader {n} bytes; {dat}: {dat.stat().st_size} bytes")


if __name__ == "__main__":
    main()
