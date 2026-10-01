#!/usr/bin/env python3
"""font_cyr.py - the port's Cyrillic letters (src/res/art/ui/font_cyr.txt).

    python3 tools/font_cyr.py [--preview FILE.png] [TEXT]

Read by tools/dune_data.py (how a Cyrillic letter is encoded in text.inc)
and tools/dune_front.py (the letters' glyphs in FA_FONT_INTRO).  A letter
with an alias is the Latin capital of the same shape; a drawn one is
$80 + its place in the file, which the text routine's `and $7F` turns into
glyph n of the font.  Small letters are their capitals.  A drawn ASCII
character replaces font8's in that font.  Run on its own it
prints TEXT's codes, and --preview draws the drawn letters (and TEXT) the
way the font will show them, shadow included.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "src/res/art/ui/font_cyr.txt"
FIRST = 0x80


def load(path=FILE):
    """-> (alias {letter: Latin capital}, [(letter, 8x8 codes)], {ASCII
    code: 8x8 codes} replacing font8's): codes 0 nothing, 1 ink, 3 the
    shadow, as tools/dune_front.py's font_codes."""
    alias, glyphs, own = {}, [], {}
    lines = [ln.rstrip() for ln in path.read_text().splitlines()]
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        i += 1
        if not s or s.startswith("#"):
            continue
        if s.startswith("alias"):
            for pair in s.split()[1:]:
                k, _, v = pair.partition("=")
                alias[k] = v
            continue
        if len(s) != 1:
            sys.exit(f"{path}: expected a letter, got {s!r}")
        rows = lines[i:i + 7]
        i += 7
        if len(rows) != 7 or any(len(r) != 7 or set(r) - set("#.")
                                 for r in rows):
            sys.exit(f"{path}: {s}: 7 rows of 7 '#' or '.'")
        ink = [[r[x] == "#" for x in range(7)] + [False] for r in rows]
        ink.append([False] * 8)
        codes = [[0] * 8 for _ in range(8)]
        for y in range(8):
            for x in range(8):
                if ink[y][x]:
                    codes[y][x] = 1
                elif (x and ink[y][x - 1]) or (y and ink[y - 1][x]) or \
                        (x and y and ink[y - 1][x - 1]):
                    codes[y][x] = 3
        if ord(s) < 128:
            own[ord(s)] = codes
        else:
            glyphs.append((s, codes))
    if len(glyphs) > 32:
        sys.exit(f"{path}: {len(glyphs)} letters, the font has room for 32")
    return alias, glyphs, own


_MAP = None


def char_map():
    """{character: code} for every Cyrillic letter the file knows, both
    cases."""
    global _MAP
    if _MAP is None:
        alias, glyphs, _ = load()
        m = {}
        for k, v in alias.items():
            m[k] = ord(v)
        for n, (k, _) in enumerate(glyphs):
            m[k] = FIRST + n
        for k in list(m):
            m[k.lower()] = m[k]
        _MAP = m
    return _MAP


def code(ch):
    """A character -> its byte: ASCII as it is, Cyrillic by the file."""
    if ord(ch) < 128:
        return ord(ch)
    m = char_map()
    if ch not in m:
        sys.exit(f"font_cyr: no glyph for {ch!r} (src/res/art/ui/font_cyr.txt)")
    return m[ch]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--preview", type=Path)
    ap.add_argument("text", nargs="?", default="")
    a = ap.parse_args()
    alias, glyphs, own = load()
    print(f"{len(glyphs)} drawn, {len(alias)} aliases, {len(own)} ASCII")
    if a.text:
        print(" ".join(f"{code(c):02X}" for c in a.text))
    if a.preview:
        sys.path.insert(0, str(Path(__file__).parent))
        from PIL import Image
        import dune_front
        f8 = dune_front.font_codes("font8.png")
        for n, (_, g) in enumerate(glyphs):
            f8[n] = g
        for c, g in own.items():
            f8[c] = g
        text = "".join(k for k, _ in glyphs) + "\n" + a.text.upper()
        rows = text.split("\n")
        w = max(len(r) for r in rows) * 8
        im = Image.new("RGB", (w + 8, len(rows) * 10 + 8), (40, 20, 10))
        px = im.load()
        cols = {1: (255, 255, 255), 2: (200, 200, 200), 3: (0, 0, 0)}
        for ry, r in enumerate(rows):
            for i, ch in enumerate(r):
                g = code(ch) & 0x7F
                for y in range(8):
                    for x in range(8):
                        c = f8[g][y][x]
                        if c:
                            px[4 + i * 8 + x, 4 + ry * 10 + y] = cols[c]
        im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(a.preview)


if __name__ == "__main__":
    main()
