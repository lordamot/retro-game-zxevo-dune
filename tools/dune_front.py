#!/usr/bin/env python3
"""dune_front.py - the front end's pictures (src/res/art/ui/) -> EGA pages.

    dune_front.py [--out build/gen] [--preview DIR]

Reads the Mega Drive's front-end screens as tools/sega/port_ui.py left
them (src/res/art/ui/*.png and ui.txt: positions, palettes, sequences) and
writes, into --out:

    page_NNN.bin    16 KB data pages PG_FRONT_ART (100) on (DATA_PAGES)
    panel.inc       for bank PANEL (src/front/panel.asm): its tables
    front.inc       for bank FRONT (src/front/front.asm): the asset
                    directory fe_dir, an FA_<name> EQU per asset, the
                    pens (PN_<screen>_<name>) and the small tables

Each screen gets its own 16 colours out of the EGA's 64, chosen the way
tools/dune_art.py chooses the battle's (every Mega Drive colour drawn as
one of the 16 or a 2x2 pattern of two, the error weighted by pixel count)
but in numpy, so a screen costs a second instead of half a minute.  The
Mega Drive shows 224 lines and the port 200: every screen says which 24
it gives up (OFFSET below; ui.txt's 'least').

## The assets (src/front/front.asm reads them)

Every asset is in one data page, in window 1 ($4000-$7FFF).  fe_dir has
(page, address) per FA_ number.

  PIC   a picture, packed.  +0 column (8 px), +1 y, +2 width in bytes,
        +3 height, +4 flags (bit 0: the next FA_ is more of the same
        picture, bit 1: masked).  Then stream A (planes 0 and 2) and
        stream B (planes 1 and 3), each unpacked into its cache page
        (PG_FE_CACHE_A/B at $C000) as plane 0|1 at $C000 and plane 2|3 at
        $E000, w bytes a row (2w masked: mask, data pairs).  A picture 40
        bytes wide is unpacked where it sits on the screen ($C000 + y*40),
        so the cache is then a copy of the screen's rows.
  SPR   a masked sprite, raw.  +0 column, +1 y, +2 w, +3 h, then plane 0,
        2, 1, 3: h rows of w (mask, data) pairs.  screen = screen AND mask
        OR data.
  TERR  a campaign territory as pens.  +0 column, +1 y, +2 w, +3 h, then
        packed (unpacked into the cache A page): h rows of w*4 bytes, per
        8 pixels the pixel pairs of planes 0-3, each (left pen << 4 |
        right pen); pen 0 is not part of it.
  OWN   768 bytes, 256-aligned: the AND mask, the data for even rows and
        for odd rows of every pen pair - one owner's colours on a screen.
  FONT  128 glyphs x 16 bytes: 8 rows of (plane 0 << 4 | plane 2), then 8
        of (plane 1 << 4 | plane 3); a plane's 4 bits are two pixels'
        codes, left * 4 + right: 0 nothing, 1 ink A, 2 ink B, 3 ink C.
  FADE  n, then n palettes from dark to the screen's colours; FA_PAL_x
        is the same number (fe_pal takes the last step).
  ZOOM  the campaign map's zoom (zoom.txt, zoom_records): per territory
        where its pens start in the zoom's buffer, the buffer's corner on
        the screen, the step's move and 16 x (scale, width, height).
  STARS the opening's starfield (ui.txt's star list, star_asset): the
        stars' plane positions and glyphs, and per screen its glyphs'
        pixels in that screen's pens.

A territory's pens (TERR) are its land (1-7, 15) and its own border
pieces (8, campaign_border_N.png) where it has no land; fe_own can leave
either out (the whole map draws every border first and the land over it).

The Tutorial's pictures are tools/dune_tutorial.py's, which this calls:
pages of its own (dune_tutorial.py TUT_PAGES), a directory of their own.

## The packing

Byte-oriented LZ, decoded by fe_unlz: a byte t < $80 is t + 1 literal
bytes; t >= $80 copies (t & $7F) + 3 bytes from `offset` (the next two
bytes, little-endian) back in the output.  A stream is two planes, the
second unpacked $2000 after the first; offsets count in that address
space and no token crosses from one plane into the other.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import font_cyr                                   # noqa: E402
from dune_art import pair_byte, pair_mask, palette_byte, ega_rgb, _lab, \
    BAYER, MIX_CONTRAST                                          # noqa: E402

UI = ROOT / "src/res/art/ui"
UI_TXT = ROOT / "src/res/art/ui.txt"
PG_FRONT_ART = 100              # src/pages.inc
PG_LAST_DATA = 123              # 124, 125 the unpack cache; 126, 127 the
# the data pages, in the order they are filled: 100-121 (122 is the PANEL
# bank), then the three the battle art leaves (97, 98) and 123
DATA_PAGES = list(range(PG_FRONT_ART, 122)) + [97, 98, 123]
                                # screen's background copy (front.asm)
MIX_PENALTY = (0, 6, 10, 6)     # as dune_art.Palette
PAGE = 0x4000


def load(name):
    return Image.open(UI / name).convert("RGBA")


def hexrgb(h):
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


# ------------------------------------------------------------------ ui.txt

def read_ui():
    """ui.txt -> {screen: {'pal': [4 x [16 rgb]], 'pics': {file: (x, y)},
    'notes': [str]}}"""
    out, cur, mode = {}, None, None
    for raw in UI_TXT.read_text().splitlines():
        m = re.match(r"== (\S+)", raw)
        if m:
            cur = out.setdefault(m.group(1), dict(pal=[], pics={}, notes=[]))
            mode = None
            continue
        if cur is None:
            continue
        s = raw.strip()
        if s in ("palette", "notes") or s.startswith(("pictures", "text")):
            mode = s.split()[0]
            continue
        if mode == "palette":
            m = re.match(r"(\d): (.*)", s)
            if m:
                cur["pal"].append([hexrgb(h) for h in m.group(2).split()])
        elif mode == "pictures":
            t = s.split()
            if t and t[0].endswith(".png"):
                x = int(t[1]) if t[1] != "-" else None
                y = int(t[2]) if t[2] != "-" else None
                cur["pics"][t[0]] = (x, y)
        elif mode == "notes":
            cur["notes"].append(s)
    return out


# ------------------------------------------------------------ the palette

_LEVELS = np.array((0, 85, 170, 255), float)
EGA = [(r, g, b) for r in range(4) for g in range(4) for b in range(4)]
EGA_RGB = np.array([ega_rgb(c) for c in EGA], float)


def lab_np(rgb):
    return np.array([_lab(tuple(c)) for c in rgb], float)


def _options():
    oi, oj, oq = [], [], []
    for i in range(64):
        oi.append(i); oj.append(i); oq.append(0)
    for i in range(64):
        for j in range(64):
            if i == j:
                continue
            oi.append(i); oj.append(j); oq.append(1)
            if i < j:
                oi.append(i); oj.append(j); oq.append(2)
    oi, oj, oq = np.array(oi), np.array(oj), np.array(oq)
    a, b = EGA_RGB[oi], EGA_RGB[oj]
    mix = (a * (4 - oq[:, None]) + b * oq[:, None]) / 4
    la, lb = lab_np(a), lab_np(b)
    pen = np.array(MIX_PENALTY)[oq] + ((la - lb) ** 2).sum(1) * MIX_CONTRAST
    pen[oq == 0] = 0
    return oi, oj, oq, lab_np(mix), pen


OPT = None


class Palette:
    """dune_art.Palette's choice, vectorised: 16 EGA colours (the fixed
    ones first) and for every source colour a pair of entries and a 2x2
    pattern."""

    def __init__(self, hist, fixed=((0, 0, 0),), size=16):
        global OPT
        if OPT is None:
            OPT = _options()
        oi, oj, oq, olab, pen = OPT
        srcs = list(hist)
        w = np.array([hist[s] for s in srcs], float)
        ls = lab_np(srcs)
        cost = ((ls[:, None, :] - olab[None, :, :]) ** 2).sum(-1) + pen[None, :]
        self._oi, self._oj, self._oq = oi, oj, oq

        def error(cols):
            ins = np.zeros(64, bool)
            ins[cols] = True
            allowed = ins[oi] & ins[oj]
            return float((w * cost[:, allowed].min(1)).sum())

        fixed_i = [EGA.index(c) for c in fixed]
        cols = list(fixed_i)
        cands = [c for c in range(64) if c not in cols]
        while len(cols) < size:
            best = min(cands, key=lambda c: error(cols + [c]))
            cols.append(best)
            cands.remove(best)
        improved = True
        while improved:
            improved = False
            base = error(cols)
            for i in range(len(fixed_i), size):
                for c in list(cands):
                    trial = cols[:i] + [c] + cols[i + 1:]
                    e = error(trial)
                    if e < base - 1e-6:
                        cands.append(cols[i])
                        cands.remove(c)
                        cols, base, improved = trial, e, True
        self.ega = cols
        self.cols = [EGA[c] for c in cols]
        self.map = {}
        for s in srcs:
            self.map[s] = self._best(s)

    def _best(self, src):
        oi, oj, oq, olab, pen = OPT
        ins = np.zeros(64, bool)
        ins[self.ega] = True
        allowed = np.nonzero(ins[oi] & ins[oj])[0]
        ls = lab_np([src])[0]
        c = ((olab[allowed] - ls) ** 2).sum(1) + pen[allowed]
        k = allowed[int(np.argmin(c))]
        pos = {e: n for n, e in enumerate(self.ega)}
        return pos[oi[k]], pos[oj[k]], int(oq[k])

    def index(self, rgb, x, y):
        rgb = tuple(rgb)
        if rgb not in self.map:
            self.map[rgb] = self._best(rgb)
        a, b, q = self.map[rgb]
        return b if BAYER[y & 1][x & 1] < q else a

    def pen(self, rgb):
        """The single entry nearest a colour (text)."""
        ls = np.array(_lab(rgb))
        la = lab_np([ega_rgb(c) for c in self.cols])
        return int(np.argmin(((la - ls) ** 2).sum(1)))

    def bytes(self):
        return bytes(palette_byte(c) for c in self.cols)

    def faded(self, k, n):
        """The palette k/n of the way up from black."""
        return bytes(palette_byte(tuple(int(v * k / n + 0.5) for v in c))
                     for c in self.cols)


def histogram(items):
    """[(RGBA image, weight)] -> {rgb: count}"""
    hist = {}
    for im, wt in items:
        a = np.asarray(im.convert("RGBA")).reshape(-1, 4)
        a = a[a[:, 3] > 0][:, :3]
        if not len(a):
            continue
        u, n = np.unique(a, axis=0, return_counts=True)
        for c, k in zip(map(tuple, u), n):
            c = tuple(int(v) for v in c)
            hist[c] = hist.get(c, 0) + int(k) * wt
    return hist


def quantize(im, pal, x0, y0):
    """RGBA image placed at screen (x0, y0) -> int array of entries, -1
    where transparent."""
    a = np.asarray(im.convert("RGBA"))
    h, w = a.shape[:2]
    out = np.full((h, w), -1, int)
    flat = a.reshape(-1, 4)
    opaque = flat[:, 3] > 0
    if not opaque.any():
        return out
    u, inv = np.unique(flat[opaque][:, :3], axis=0, return_inverse=True)
    keys = [tuple(int(v) for v in c) for c in u]
    for k in keys:
        pal.index(k, 0, 0)              # fills pal.map for a new colour
    maps = np.array([pal.map[k] for k in keys])
    ys, xs = np.divmod(np.nonzero(opaque)[0], w)
    abq = maps[inv.reshape(-1)]
    thr = np.array(BAYER)[(ys + y0) & 1, (xs + x0) & 1]
    val = np.where(thr < abq[:, 2], abq[:, 1], abq[:, 0])
    out.reshape(-1)[np.nonzero(opaque)[0]] = val
    return out


# ------------------------------------------------------------ EGA bytes

PAIR = np.zeros((17, 17), np.uint8)        # [left + 1, right + 1] -> byte
MASK = np.zeros((17, 17), np.uint8)
for _l in range(-1, 16):
    for _r in range(-1, 16):
        PAIR[_l + 1, _r + 1] = pair_byte(max(_l, 0), max(_r, 0))
        MASK[_l + 1, _r + 1] = pair_mask(_l < 0, _r < 0)


def align(idx, shift):
    """Pad an index array on the left by shift and on the right to a whole
    number of bytes (8 pixels)."""
    h, w = idx.shape
    W = (shift + w + 7) // 8
    out = np.full((h, W * 8), -1, int)
    out[:, shift:shift + w] = idx
    return out


def planes(idx):
    """h x 8W entries -> [4 planes of (data, mask)], each h x W uint8."""
    res = []
    for p in range(4):
        L = idx[:, 2 * p::8] + 1
        R = idx[:, 2 * p + 1::8] + 1
        res.append((PAIR[L, R], MASK[L, R]))
    return res


def interleave(data, mask):
    h, w = data.shape
    out = np.empty((h, 2 * w), np.uint8)
    out[:, 0::2] = mask
    out[:, 1::2] = data
    return out


# --------------------------------------------------------------- packing

def lz_pack(segments, bases):
    """Pack segments (bytes) that unpack at bases (virtual addresses):
    -> bytes.  Tokens never cross a segment's end; a match's source stays
    inside one segment."""
    data = b"".join(segments)
    vaddr = []
    seg_of = []
    for n, (s, b) in enumerate(zip(segments, bases)):
        vaddr.extend(range(b, b + len(s)))
        seg_of.extend([n] * len(s))
    ends = []
    k = 0
    for s in segments:
        k += len(s)
        ends.append(k)
    out = bytearray()
    lits = bytearray()

    def flush():
        i = 0
        while i < len(lits):
            n = min(128, len(lits) - i)
            out.append(n - 1)
            out.extend(lits[i:i + n])
            i += n
        lits.clear()

    heads = {}
    N = len(data)
    i = 0
    seg = 0
    while i < N:
        while i >= ends[seg]:
            flush()
            seg += 1
        best_len, best_off = 0, 0
        if i + 3 <= ends[seg]:
            key = data[i:i + 3]
            cands = heads.get(key, ())
            limit = min(ends[seg] - i, 130)
            for c in reversed(cands[-48:]):
                off = vaddr[i] - vaddr[c]
                if off > 0xFFFF:
                    continue
                cend = ends[seg_of[c]]
                lim = min(limit, cend - c) if seg_of[c] != seg else limit
                n = 0
                while n < lim and data[c + n] == data[i + n]:
                    n += 1
                if n > best_len:
                    best_len, best_off = n, off
                    if n == limit:
                        break
        if best_len >= 3:
            flush()
            out.append(0x80 | (best_len - 3))
            out.append(best_off & 0xFF)
            out.append(best_off >> 8)
            for k in range(i, i + best_len):
                if k + 3 <= N:
                    heads.setdefault(data[k:k + 3], []).append(k)
            i += best_len
        else:
            lits.append(data[i])
            if i + 3 <= N:
                heads.setdefault(data[i:i + 3], []).append(i)
            i += 1
    flush()
    return bytes(out)


def lz_unpack(stream, sizes, bases):
    """The Z80's decoder, for the self-check."""
    mem = {}
    pos = 0
    for size, base in zip(sizes, bases):
        d = base
        while d < base + size:
            t = stream[pos]
            pos += 1
            if t < 0x80:
                for k in range(t + 1):
                    mem[d] = stream[pos + k]
                    d += 1
                pos += t + 1
            else:
                n = (t & 0x7F) + 3
                off = stream[pos] | (stream[pos + 1] << 8)
                pos += 2
                for k in range(n):
                    mem[d] = mem[d - off]
                    d += 1
        assert d == base + size
    return [bytes(mem[b + k] for k in range(s)) for s, b in zip(sizes, bases)], pos


# ---------------------------------------------------------------- output

class Out:
    def __init__(self):
        self.assets = []            # (name, bytes, align)
        self.names = {}
        self.pens = []              # (equ, value)
        self.lines = []             # extra front.inc lines
        self.same = {}              # identical data -> its number
        self.aliases = []           # (name, number): a second name

    def add(self, name, data, align=1):
        name = re.sub(r"[^A-Za-z0-9_]", "_", name)     # a label
        assert name not in self.names, name
        assert len(data) <= PAGE, (name, len(data))
        # identical panel icons and pictures share one copy (the front
        # end counts on its frames being consecutive: those never do)
        key = (bytes(data), align)
        if name.startswith(("i_", "p_")) and key in self.same:
            self.names[name] = self.same[key]
            self.aliases.append((name, self.same[key]))
            return self.same[key]
        self.same[key] = len(self.assets)
        self.names[name] = len(self.assets)
        self.assets.append((name, bytes(data), align))
        return self.names[name]

    def pic(self, name, idx, x, y, masked=False):
        """An entry array placed at screen (x, y) -> one or more PIC
        chunks (bands of rows, each packed into one page)."""
        idx, x, y = clip(idx, x, y)
        if idx is None:
            raise SystemExit(f"{name}: off the screen")
        col, shift = x // 8, x % 8
        a = align(idx, shift)
        h, W8 = a.shape
        W = W8 // 8
        pl = planes(a)
        # bands: each stream's planes unpack into 8 KB, and the packed
        # picture must fit a page
        per = 2 if masked else 1
        max_rows = min(h, 8192 // (W * per))
        chunks = []
        r = 0
        while r < h:
            n = min(max_rows, h - r)
            while True:
                blob = self._pic_chunk(pl, r, n, W, col, y + r, masked)
                if len(blob) <= PAGE - 64 or n <= 8:
                    break
                n = (n * 3) // 4
            chunks.append(blob)
            r += n
        ids = []
        for k, blob in enumerate(chunks):
            flags = (1 if k < len(chunks) - 1 else 0) | (2 if masked else 0)
            blob = blob[:4] + bytes([flags]) + blob[5:]
            ids.append(self.add(name if k == 0 else f"{name}_{k}", blob))
        return ids[0]

    def _pic_chunk(self, pl, r, n, W, col, y, masked):
        streams = []
        for pa, pb in ((0, 2), (1, 3)):
            segs = []
            for p in (pa, pb):
                d, m = pl[p]
                d, m = d[r:r + n], m[r:r + n]
                segs.append((interleave(d, m) if masked else d).tobytes())
            base0 = y * 40 if (W == 40 and not masked) else 0
            bases = [base0, base0 + 0x2000]
            s = lz_pack(segs, bases)
            back, used = lz_unpack(s, [len(x) for x in segs], bases)
            assert back == segs and used == len(s)
            streams.append(s)
        return bytes([col, y, W, n, 0]) + streams[0] + streams[1]

    def spr(self, name, idx, x, y):
        idx, x, y = clip(idx, x, y)
        if idx is None:
            return self.add(name, bytes([0, 0, 1, 0]))
        col, shift = x // 8, x % 8
        a = align(idx, shift)
        h, W8 = a.shape
        pl = planes(a)
        body = b"".join(interleave(*pl[p]).tobytes() for p in (0, 2, 1, 3))
        return self.add(name, bytes([col, y, W8 // 8, h]) + body)

    def pen(self, equ, value):
        self.pens.append((equ, value))

    def write(self, out):
        if len(self.assets) > 256:
            raise SystemExit(f"dune_front: {len(self.assets)} assets; the FA_ "
                             "numbers are bytes (256 at most)")
        pages = []                  # [bytearray, used]
        loc = []
        order = sorted(range(len(self.assets)),
                       key=lambda k: -len(self.assets[k][1]))
        where = {}
        for k in order:
            name, data, al = self.assets[k]
            for n, pg in enumerate(pages):
                at = (pg[1] + al - 1) // al * al
                if at + len(data) <= PAGE:
                    break
            else:
                pages.append([bytearray(PAGE), 0])
                n = len(pages) - 1
                at = 0
            pg = pages[n]
            pg[0][at:at + len(data)] = data
            pg[1] = at + len(data)
            if n >= len(DATA_PAGES):
                raise SystemExit(f"dune_front: more than {len(DATA_PAGES)} pages")
            where[k] = (DATA_PAGES[n], 0x4000 + at)
        for n, (buf, used) in enumerate(pages):
            (out / f"page_{DATA_PAGES[n]:03d}.bin").write_bytes(bytes(buf))
        L = ["; front.inc - written by tools/dune_front.py; do not edit.",
             f"FE_DATA_PAGES   EQU {len(pages)}"]
        for k, (name, data, al) in enumerate(self.assets):
            L.append(f"FA_{name.upper():24} EQU {k}")
        for name, k in self.aliases:
            L.append(f"FA_{name.upper():24} EQU {k}\t; the same as another")
        for equ, v in self.pens:
            L.append(f"{equ:28} EQU {v}")
        L += self.lines
        L.append("; the directory: page, address (window 1) per FA_ number")
        L.append("fe_dir:")
        for k, (name, data, al) in enumerate(self.assets):
            pg, ad = where[k]
            L.append(f"        DB {pg}\n        DW ${ad:04X}\t; {name}, {len(data)}")
        (out / "front.inc").write_text("\n".join(L) + "\n")
        return len(pages), sum(p[1] for p in pages)


def clip(idx, x, y):
    """Cut an entry array at the screen's edges (320 x 200)."""
    h, w = idx.shape
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, 320), min(y + h, 200)
    if x1 <= x0 or y1 <= y0:
        return None, x, y
    return idx[y0 - y:y1 - y, x0 - x:x1 - x], x0, y0


# ------------------------------------------------------------------ fonts

def font_codes(name):
    """A font sheet -> 128 x 8 x 8 codes (0 nothing, 1 ink A, 2 B, 3 C)."""
    im = np.asarray(load(name))
    codes = np.zeros((128, 8, 8), int)
    for g in range(128):
        cell = im[(g // 16) * 8:(g // 16) * 8 + 8, (g % 16) * 8:(g % 16) * 8 + 8]
        for y in range(8):
            for x in range(8):
                r, gg, b, a = (int(v) for v in cell[y, x])
                c = 0
                if a:
                    rgb = (r, gg, b)
                    if name == "font8.png":
                        c = 1 if rgb == (255, 255, 255) else 3 if rgb == (0, 0, 0) else 2
                    elif name == "font_menu.png":
                        c = 1 if rgb == (255, 255, 255) else 0
                    else:
                        c = {(255, 255, 0): 1, (0, 145, 0): 2,
                             (0, 0, 0): 3}.get(rgb, 0)
                codes[g, y, x] = c
        if name == "font_menu.png":
            # the menu font's black is its background: keep only the
            # shadow, the black right of or below the ink
            ink = codes[g] == 1
            sh = np.zeros_like(ink)
            sh[:, 1:] |= ink[:, :-1]
            sh[1:, :] |= ink[:-1, :]
            sh[1:, 1:] |= ink[:-1, :-1]
            cellrgb = cell[:, :, :3].sum(2)
            codes[g][(~ink) & sh & (cellrgb == 0)] = 3
    return codes


def font_bytes(codes):
    out = bytearray()
    for g in range(128):
        a = bytearray()
        b = bytearray()
        for y in range(8):
            row = codes[g, y]
            nib = [int(row[2 * p] * 4 + row[2 * p + 1]) for p in range(4)]
            a.append(nib[0] << 4 | nib[2])
            b.append(nib[1] << 4 | nib[3])
        out += a + b
    return out


def draw_text(canvas, codes, x, y, text, inks):
    """Draw a string into an RGBA canvas (PIL) with the font's codes;
    inks = colours for codes 1, 2, 3 (None: nothing)."""
    px = canvas.load()
    for i, ch in enumerate(text):
        g = ord(ch) & 0x7F
        for yy in range(8):
            for xx in range(8):
                c = codes[g, yy, xx]
                if c and inks[c - 1] is not None:
                    X, Y = x + i * 8 + xx, y + yy
                    if 0 <= X < canvas.width and 0 <= Y < canvas.height:
                        px[X, Y] = inks[c - 1] + (255,)


# ---------------------------------------------------------------- screens

BLACK, WHITE = (0, 0, 0), (255, 255, 255)
YELLOW = (255, 255, 0)

# The 24 lines each screen gives up: its pictures move up by this.
OFF_LOGO, OFF_TITLE, OFF_MENTAT, OFF_END = 8, 24, 8, 16


def canvas():
    return Image.new("RGBA", (320, 200), (0, 0, 0, 255))


def paste(cv, im, x, y):
    cv.paste(im, (x, y), im)


def star_list():
    """ui.txt's starfield: [(plane x, y, glyph)]."""
    txt = " ".join(read_ui()["logos"]["notes"])
    return [(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            for m in re.finditer(r"(\d+),(\d+),(\d)",
                                 txt.split("Stars (plane x, y, glyph):")[1])]


def stars(off):
    """The starfield at rest (ui.txt: plane x + 320 mod 1024)."""
    glyphs = [load("title_star_0.png"), load("title_star_1.png")]
    im = Image.new("RGBA", (320, 200), (0, 0, 0, 0))
    for px, py, g in star_list():
        x = (px + 320) % 1024
        if x < 320:
            paste(im, glyphs[g], x, py - off)
    return im


def star_asset(pals):
    """FA_STARS, for the starfield that scrolls under the logos, PRESENT
    and the planet's arrival (menu_scroll_vblank $017C32): the stars,
    then for each screen that shows them - (lines dropped, palette) in
    pals - each glyph's lit pixels as the pens of that palette.

        +0 n, then n x (plane x lo, hi, y, glyph)
        per screen: the lines dropped, then per glyph: k, k x (dx, dy, pen)
    """
    out = bytearray()
    st = star_list()
    out.append(len(st))
    for px, py, g in st:
        out += bytes([px & 0xFF, px >> 8, py, g])
    glyphs = [np.asarray(load(f"title_star_{g}.png")) for g in (0, 1)]
    for off, pal in pals:
        out.append(off)
        for a in glyphs:
            pix = [(x, y, pal.pen(tuple(int(v) for v in a[y, x, :3])))
                   for y in range(a.shape[0]) for x in range(a.shape[1])
                   if a[y, x, 3]]
            out.append(len(pix))
            for x, y, pen in pix:
                out += bytes([x, y, pen])
    return bytes(out)


def opaque(im):
    """Over black."""
    cv = Image.new("RGBA", im.size, (0, 0, 0, 255))
    cv.alpha_composite(im)
    return cv


LAND_PEN = {c: n + 1 for n, c in enumerate(
    hexrgb(h) for h in "FFDA91 DAB66D B69148 916D24 6D4800 482424 240000".split())}
LAND_PEN[BLACK] = 15
BORDER_PEN = 8          # a territory's own border pieces: pen 7's colour


def land_pens(im):
    a = np.asarray(im)
    pens = np.zeros(a.shape[:2], int)
    for y in range(a.shape[0]):
        for x in range(a.shape[1]):
            if a[y, x, 3]:
                pens[y, x] = LAND_PEN[tuple(int(v) for v in a[y, x, :3])]
    return pens


def owner_colours(ui):
    """Per owner (0 nobody, 1 H, 2 A, 3 O) the colour of each pen 1-15,
    bright (the campaign screen) and dim (behind the mentat)."""
    cp = ui["campaign"]["pal"]
    mp = ui["mentat-atreides"]["pal"]
    bright, dim = [], []
    for o, line in enumerate((0, 2, 1, 3)):         # $095CE8
        bright.append([None] + [cp[line][k] for k in range(1, 15)] + [BLACK])
    for o, (line, add) in enumerate(((0, 0), (0, 7), (1, 0), (1, 7))):
        dim.append([None] + [mp[line][min(k + add, 15)] if k < 8 else mp[line][k]
                             for k in range(1, 15)] + [BLACK])
    for cols in bright + dim:
        cols[BORDER_PEN] = cols[7]
    return bright, dim


def own_table(pal, cols):
    """OWN: mask, even-row and odd-row data for every pen pair."""
    t = bytearray(768)
    for v in range(256):
        pl, pr = v >> 4, v & 15
        t[v] = pair_mask(pl == 0, pr == 0)
        for par in (0, 1):
            li = pal.index(cols[pl], 0, par) if pl else 0
            ri = pal.index(cols[pr], 1, par) if pr else 0
            t[256 * (1 + par) + v] = pair_byte(li, ri)
    return t


def zoom_records(cpics):
    """zoom.txt -> FA_ZOOM, a record of 6 + 16 * 3 bytes per territory
    for fe_zoom: where the territory's pens (its TERR, from its PNG's
    column and line) start in the zoom buffer (x, y), the buffer's corner
    on the port's screen (x, y), dx, dy, then renders 0-15 as (the
    scale's fraction in 256ths - 0 for 1.0 -, width and height in
    tiles)."""
    recs, cur = {}, None
    for raw in (UI / "zoom.txt").read_text().splitlines():
        m = re.match(r"territory (\d+) origin (-?\d+) (-?\d+)", raw)
        if m:
            cur = recs.setdefault(int(m.group(1)), dict(
                origin=(int(m.group(2)), int(m.group(3))), steps=[]))
            continue
        m = re.match(r"\s+step\s+(\d+):\s+(-?\d+)\s+(-?\d+)\s+\$([0-9A-F]+)"
                     r"\s+(\d+)\s+(\d+)", raw)
        if m:
            cur["steps"].append(tuple(int(m.group(k)) for k in (2, 3))
                                + (int(m.group(4), 16),)
                                + tuple(int(m.group(k)) for k in (5, 6)))
    out = bytearray()
    for t in range(10):
        r = recs[t]
        ox, oy = r["origin"]
        x, y = cpics[f"campaign_land_{t}.png"]
        bx0, by0 = (x // 8) * 8 - ox, y - oy
        assert 0 <= bx0 < 256 and 0 <= by0 < 256, (t, bx0, by0)
        dxs = {s[0] for s in r["steps"][1:]}
        dys = {s[1] for s in r["steps"][1:]}
        assert len(dxs) == 1 and len(dys) == 1, t     # one move per step
        out += bytes([bx0, by0, ox, oy - OFF_MENTAT, dxs.pop() & 0xFF,
                      dys.pop() & 0xFF])
        for dx, dy, sc, w, h in r["steps"][:16]:
            assert sc & 0xFF == 0 and sc <= 0x10000, (t, sc)
            out += bytes([(sc >> 8) & 0xFF, w, h])
    return bytes(out)


def terr_bytes(pens, x, y):
    col, shift = x // 8, x % 8
    h, w = pens.shape
    W = (shift + w + 7) // 8
    a = np.zeros((h, W * 8), int)
    a[:, shift:shift + w] = pens
    body = bytearray()
    for r in range(h):
        for c in range(W):
            for p in range(4):
                body.append(a[r, c * 8 + 2 * p] << 4 | a[r, c * 8 + 2 * p + 1])
    packed = lz_pack([bytes(body)], [0])
    back, used = lz_unpack(packed, [len(body)], [0])
    assert back[0] == bytes(body) and used == len(packed)
    return bytes([col, y, W, h]) + packed, col, W


def build(out, preview=None):
    ui = read_ui()
    O = Out()
    prev = {}

    def screen_pal(name, items, fixed=(BLACK,)):
        pal = Palette(histogram(items), fixed=fixed)
        steps = [pal.faded(k, 4) for k in range(1, 5)]
        assert steps[-1] == pal.bytes()
        k = O.add(f"fade_{name}", bytes([4]) + b"".join(steps))
        O.names[f"pal_{name}"] = k          # the colours: the last step
        O.aliases.append((f"pal_{name}", k))
        return pal

    def full(name, cv, pal, off=0):
        prev[name] = (cv, pal)
        return O.pic(name, quantize(cv, pal, 0, 0), 0, 0)

    def rect(name, im, x, y, pal, masked=False):
        return O.pic(name, quantize(im, pal, x, y), x, y, masked=masked)

    def sprite(name, im, x, y, pal):
        return O.spr(name, quantize(im, pal, x, y), x, y)

    f8 = font_codes("font8.png")
    fmenu = font_codes("font_menu.png")
    fscore = font_codes("font_score.png")
    fonts = bytearray()
    for c in (f8, fmenu, fscore):
        fonts += font_bytes(c)
    O.add("font8", fonts[0:2048])
    O.add("font_menu", fonts[2048:4096])
    O.add("font_score", fonts[4096:6144])
    # the start-up screens' font (the port's): font8 with the Cyrillic
    # letters of font_cyr.txt at glyphs 0.. (their codes are $80 + n) and
    # its own '@' where font8 has a (c)
    fint = f8.copy()
    _, drawn, own = font_cyr.load()
    for n, (_, g) in enumerate(drawn):
        fint[n] = np.array(g)
    for c, g in own.items():
        fint[c] = np.array(g)
    O.add("font_intro", font_bytes(fint))

    # ---- the logos and PRESENT
    # (the starfield is not in the pictures: it scrolls under them, drawn
    # by fe_stars from FA_STARS - but it votes for the colours)
    pics = ui["logos"]["pics"]
    st = stars(OFF_LOGO)
    cv = canvas()
    for f in ("title_virgin.png", "title_westwood.png", "title_copyright.png"):
        x, y = pics[f]
        paste(cv, load(f), x, y - OFF_LOGO)
    pv = canvas()
    draw_text(pv, f8, 128, 112 - OFF_LOGO, "PRESENT", (WHITE, None, BLACK))
    pal = screen_pal("logo", [(cv, 1), (pv, 1), (st, 2)],
                     fixed=(BLACK, (3, 3, 3)))
    logo_pal = pal
    full("logo", cv, pal)
    full("present", pv, pal)

    # ---- the title
    pics = ui["title"]["pics"]
    st = stars(OFF_TITLE)
    planet = load("title_planet.png")
    px, py = pics["title_planet.png"]
    py -= OFF_TITLE
    rest = canvas()
    paste(rest, st, 0, 0)
    paste(rest, planet, px, py)
    words = rest.copy()
    for f in ("title_logo.png", "title_subtitle.png", "title_licence.png"):
        x, y = pics[f]
        paste(words, load(f), x, y - OFF_TITLE)
    ships = [(load(f"title_ship_{n:02d}.png"), pics[f"title_ship_{n:02d}.png"])
             for n in range(23)]
    pointers = [load(f"title_pointer_{n}.png") for n in range(5)]
    menu = words.copy()
    for k, s in enumerate(("START GAME", "OPTIONS", "TUTORIAL")):
        draw_text(menu, f8, 128, 160 + 8 * k - OFF_TITLE, s, (WHITE, None, BLACK))
    items = [(menu, 1)] + [(im, 4) for im, _ in ships] + [(p, 20) for p in pointers]
    pal = screen_pal("title", items, fixed=(BLACK, (3, 3, 3)))
    full("title_rest", rest, pal)
    full("title_words", words, pal)
    pl = Image.new("RGBA", ((px & 7) + planet.width, planet.height), (0, 0, 0, 255))
    pl.alpha_composite(planet, ((px & 7), 0))
    rect("title_planet", pl, px & ~7, py, pal)
    O.lines.append(f"FE_PLANET_COL   EQU {px // 8}")
    O.add("stars", star_asset([(OFF_LOGO, logo_pal), (OFF_TITLE, pal)]))
    for n, (im, (x, y)) in enumerate(ships):
        sprite(f"ship_{n}", im, x, y - OFF_TITLE, pal)
    x, y = pics["title_pointer_0.png"]
    for n, p in enumerate(pointers):
        sprite(f"title_pointer_{n}", p, x, y - OFF_TITLE, pal)
    O.lines.append(f"FE_TITLE_PTR_Y  EQU {y - OFF_TITLE}")
    O.lines.append(f"FE_TITLE_PTR_COL EQU {x // 8}")
    O.pen("PN_TITLE_WHITE", pal.pen(WHITE))
    # the port's start-up log and intro screen (front_boot, front_intro,
    # before the opening; the cartridge has none) in the title's colours:
    # the words in its white, the bar in the planet's sand on a dark track
    O.pen("PN_LOAD_WORD", pal.pen(WHITE))
    O.pen("PN_LOAD_BAR", pal.pen((255, 170, 85)))
    O.pen("PN_LOAD_TRACK", pal.pen((85, 0, 0)))

    # ---- the house choice
    pics = ui["house"]["pics"]
    cv = canvas()
    for f in ("house_title.png", "crest_atreides.png", "crest_label_atreides.png",
              "crest_ordos.png", "crest_label_ordos.png", "crest_harkonnen.png",
              "crest_label_harkonnen.png"):
        x, y = pics[f]
        paste(cv, load(f), x, y)
    hl = [load(f"house_highlight_{n}.png") for n in range(3)]
    pal = screen_pal("house", [(cv, 1)] + [(h, 10) for h in hl])
    full("house", cv, pal)
    for n, h in enumerate(hl):
        sprite(f"house_hl_{n}", h, 32, 136, pal)

    # ---- the campaign map's pieces (pens, for every screen that shows it)
    cpics = ui["campaign"]["pics"]
    bpos = {}
    for raw in (UI / "zoom.txt").read_text().splitlines():
        m = re.match(r"border (\d+) at (\d+) (\d+)", raw)
        if m:
            bpos[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    terr = []
    for t in range(11):
        f = f"campaign_land_{t}.png" if t < 10 else "campaign_borders.png"
        x, y = cpics[f]
        pens = land_pens(load(f))
        if t < 10:
            # with its own border pieces (pen 8, where it has no land), as
            # a lifted territory's sprite and the zoom's buffer have them
            # (zoom.txt); on the whole map fe_own hides them and terr_10
            # draws every border first, in owner 0's colours, the land
            # over it - as the Mega Drive's map does
            bx, by = bpos[t]
            bp = land_pens(load(f"campaign_border_{t}.png"))
            x0, y0 = min(x, bx), min(y, by)
            x1 = max(x + pens.shape[1], bx + bp.shape[1])
            y1 = max(y + pens.shape[0], by + bp.shape[0])
            u = np.zeros((y1 - y0, x1 - x0), int)
            u[y - y0:y - y0 + pens.shape[0], x - x0:x - x0 + pens.shape[1]] = pens
            bb = u[by - y0:by - y0 + bp.shape[0], bx - x0:bx - x0 + bp.shape[1]]
            bb[(bp > 0) & (bb == 0)] = BORDER_PEN
            pens, x, y = u, x0, y0
            cpics[f] = (x, y)
        data, col, W = terr_bytes(pens, x, y - OFF_MENTAT)
        O.add(f"terr_{t}", data)
        h, w = pens.shape
        ys, xs = np.nonzero(pens)
        terr.append((x + xs.mean(), y - OFF_MENTAT + ys.mean(), col, W, y - OFF_MENTAT, h))
    bright, dim = owner_colours(ui)

    def map_images(cols):
        """The map in every owner's colours, for the palette's votes."""
        out = []
        for o in range(4):
            for t in range(10):
                im = load(f"campaign_land_{t}.png")
                a = np.asarray(im).copy()
                pens = land_pens(im)
                for y in range(a.shape[0]):
                    for x in range(a.shape[1]):
                        if pens[y, x]:
                            a[y, x, :3] = cols[o][pens[y, x]]
                out.append((Image.fromarray(a), 1))
        return out

    # ---- the mentats (one screen per house: his colours and the dim map)
    mpics = {"H": ui["mentat-harkonnen"]["pics"], "A": ui["mentat-atreides"]["pics"],
             "O": ui["mentat-ordos"]["pics"]}
    bpics = dict(ui["mentat-yesno"]["pics"])
    bpics.update(ui["briefing-choose"]["pics"])
    dim_maps = map_images(dim)
    buttons = {b: load(f"mentat_button_{b}.png")
               for b in ("yes", "no", "proceed", "advice")}
    bhl = load("mentat_button_highlight.png")
    for hn, H in enumerate("HAO"):
        name = {"H": "harkonnen", "A": "atreides", "O": "ordos"}[H]
        p = mpics[H]
        base = load(f"mentat_{name}.png")
        bx, by = p[f"mentat_{name}.png"]
        eyes = [load(f"mentat_{name}_eyes_{k}.png") for k in range(5)]
        nm = 5 if H != "O" else 4
        mouths = [load(f"mentat_{name}_mouth_{k}.png") for k in range(nm)]
        ex, ey = p[f"mentat_{name}_eyes_0.png"]
        mx, my = p[f"mentat_{name}_mouth_0.png"]
        text = canvas()
        draw_text(text, f8, 0, 0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", (WHITE, None, BLACK))
        items = dim_maps + [(base, 6), (text, 20)] + [(e, 2) for e in eyes] + \
            [(m, 2) for m in mouths] + [(b, 8) for b in buttons.values()] + [(bhl, 8)]
        pal = screen_pal(f"mentat_{H}", items, fixed=(BLACK, (3, 3, 3)))
        by -= OFF_MENTAT
        # the portrait, masked: it goes over the map
        rect(f"mentat_{H}", base, bx, by, pal, masked=True)
        for k, e in enumerate(eyes):
            cv = Image.new("RGBA", e.size, (0, 0, 0, 255))
            cv.alpha_composite(base.crop((ex - bx, ey - OFF_MENTAT - by,
                                          ex - bx + e.width, ey - OFF_MENTAT - by + e.height)))
            cv.alpha_composite(e)
            rect(f"eyes_{H}_{k}", cv, ex, ey - OFF_MENTAT, pal)
        for k in range(5):
            m = mouths[min(k, nm - 1)]
            cv = Image.new("RGBA", m.size, (0, 0, 0, 255))
            cv.alpha_composite(base.crop((mx - bx, my - OFF_MENTAT - by,
                                          mx - bx + m.width, my - OFF_MENTAT - by + m.height)))
            cv.alpha_composite(m)
            rect(f"mouth_{H}_{k}", cv, mx, my - OFF_MENTAT, pal)
        for b, im in buttons.items():
            rect(f"button_{H}_{b}", im, 192, 168 - OFF_MENTAT, pal)
        sprite(f"button_hl_{H}", bhl, 192, 168 - OFF_MENTAT, pal)
        for o in range(4):
            O.add(f"own_dim_{H}_{o}", own_table(pal, dim[o]), align=256)
        O.pen(f"PN_MENTAT_{H}_WHITE", pal.pen(WHITE))
        # a preview: the map as before Atreides mission 1
        pv = canvas()
        prev[f"mentat_{H}"] = (pv, pal)
    O.lines += [f"FE_BUTTON_COL   EQU {192 // 8}",
                f"FE_BUTTON_Y0    EQU {168 - OFF_MENTAT}",
                f"FE_BUTTON_Y1    EQU {192 - OFF_MENTAT}"]

    # ---- the campaign screen: the map in full light
    arrows = [load(f"campaign_arrow_{d}.png") for d in ("up", "right", "down", "left")]
    pal = screen_pal("campaign", map_images(bright) + [(a, 10) for a in arrows])
    for o in range(4):
        O.add(f"own_bright_{o}", own_table(pal, bright[o]), align=256)
    # the arrow: pointing down at the territory's middle
    ar = arrows[2]
    for t in range(10):
        cx, cy = terr[t][0], terr[t][1]
        sprite(f"arrow_{t}", ar, int(cx) - ar.width // 2, int(cy) - ar.height - 4, pal)
    # the territory table: column, width, y, height of each piece
    O.lines.append("fe_terr_box:\t; per piece: column, width (bytes), y, height")
    for t in range(11):
        _, _, col, W, y, h = terr[t]
        O.lines.append(f"        DB {col}, {W}, {y}, {h}")
    tgt = {}
    for n in ui["campaign"]["notes"]:
        m = re.match(r"(Atreides|Ordos|Harkonnen)\s+(\d( \d){8})$", n)
        if m:
            tgt[m.group(1)] = [int(v) for v in m.group(2).split()]
    O.lines.append("fe_attack:\t; per house (H, A, O), missions 1-9: the territory attacked")
    for h in ("Harkonnen", "Atreides", "Ordos"):
        O.lines.append("        DB " + ", ".join(str(v) for v in tgt[h]))
    O.add("zoom", zoom_records(cpics))

    # ---- victory and defeat
    for kind in ("victory", "defeat"):
        pics = ui[kind]["pics"]
        cv = canvas()
        cv.alpha_composite(load(f"{kind}_screen.png").crop((0, 0, 320, 200)))
        frames = []
        fx, fy = pics[f"{kind}_frame_1.png"]
        for k in (1, 2, 3):
            f = load(f"{kind}_frame_{k}.png")
            fr = cv.crop((fx, fy, fx + f.width, fy + f.height))
            fr.alpha_composite(f)
            frames.append(fr)
        banner = load(f"{kind}_banner.png")
        pal = screen_pal(kind, [(cv, 1)] + [(f, 1) for f in frames] + [(banner, 20)])
        full(kind, cv, pal)
        fr0 = cv.crop((fx, fy, fx + frames[0].width, fy + frames[0].height))
        for k, fr in enumerate([fr0] + frames):
            rect(f"{kind}_f{k}", fr, fx, fy, pal)
        bx, by = pics[f"{kind}_banner.png"]
        sprite(f"{kind}_banner", banner, bx, 176, pal)

    # ---- the score page and the password after it
    pics = ui["score"]["pics"]
    sc = canvas()
    sc.alpha_composite(load("score_screen.png").crop((0, 0, 320, 200)))
    lab = sc.copy()
    paste(lab, load("score_labels.png"), *pics["score_labels.png"])
    pw = sc.copy()
    pwtext = [(48, 48, "YOUR PASSWORD FOR COMPLETING"),
              (112, 80, "MISSION"), (192, 80, "IS"),
              (96, 96, ">>"), (208, 96, "<<")]
    bars = [(255, 72, 0), (182, 0, 0), (0, 109, 255), (0, 0, 218)]
    items = [(lab, 1), (pw, 1)]
    bar_im = Image.new("RGBA", (4, 4))
    for k, c in enumerate(bars):
        bar_im.putpixel((k, 0), c + (255,))
    items.append((bar_im, 400))
    t = canvas()
    draw_text(t, fscore, 0, 0, "0123456789", (YELLOW, None, BLACK))
    items.append((t, 20))
    pal = screen_pal("score", items, fixed=(BLACK, (3, 3, 3), (3, 3, 0)))
    full("score", lab, pal)
    for x, y, s in pwtext:
        draw_text(pw, fscore, x, y, s, (WHITE, None, BLACK))
    full("score_pw", pw, pal)
    for n, c in (("YELLOW", YELLOW), ("WHITE", WHITE), ("BLACK", BLACK),
                 ("YOU_HI", bars[0]), ("YOU", bars[1]), ("ENEMY_HI", bars[2]),
                 ("ENEMY", bars[3])):
        O.pen(f"PN_SCORE_{n}", pal.pen(c))

    # ---- options and password
    for kind in ("options", "password"):
        cv = canvas()
        cv.alpha_composite(load(f"{kind}_screen.png").crop((0, 0, 320, 200)))
        extra = []
        if kind == "options":
            ptrs = [load(f"options_pointer_{n}.png") for n in range(6)]
            extra += [(p, 10) for p in ptrs]
        else:
            ptr = load("password_key_cursor.png")
            extra.append((ptr, 10))
        t = canvas()
        draw_text(t, fmenu, 0, 0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                  ((72, 218, 255), None, BLACK))
        draw_text(t, fmenu, 0, 8, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", (WHITE, None, BLACK))
        extra.append((t, 4))
        pal = screen_pal(kind, [(cv, 1)] + extra)
        full(kind, cv, pal)
        if kind == "options":
            x, y = ui["options"]["pics"]["options_pointer.png"]
            for n, p in enumerate(ptrs):
                sprite(f"options_ptr_{n}", p, x, y, pal)
            O.lines.append(f"FE_OPT_PTR_COL  EQU {x // 8}")
            O.lines.append(f"FE_OPT_PTR_DY   EQU {40 - y}")
            O.pen("PN_OPT_CYAN", pal.pen((72, 218, 255)))
            O.pen("PN_OPT_WHITE", pal.pen(WHITE))
        else:
            sprite("password_key", ptr, 84, 52, pal)
            O.pen("PN_PW_WHITE", pal.pen(WHITE))
        O.pen(f"PN_{kind.upper()[:3]}_BLACK", 0)

    # ---- the ending: Arrakis in the house's colours
    notes = " ".join(ui["ending"]["notes"])
    ramps = [[hexrgb(h) for h in m.group(1).split()]
             for m in re.finditer(r"ramp \d: ((?:[0-9A-F]{6} ?){10})", notes)]
    planet = load("ending_planet.png")
    ex, ey = ui["ending"]["pics"]["ending_planet.png"]
    st = stars(OFF_END)
    for hn, H in enumerate("HAO"):
        a = np.asarray(planet).copy()
        for y in range(a.shape[0]):
            for x in range(a.shape[1]):
                c = tuple(int(v) for v in a[y, x, :3])
                if a[y, x, 3] and c in ramps[1]:
                    a[y, x, :3] = ramps[hn][ramps[1].index(c)]
        cv = canvas()
        paste(cv, st, 0, 0)
        paste(cv, Image.fromarray(a), ex, ey - OFF_END)
        t = canvas()
        draw_text(t, f8, 0, 0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", (WHITE, None, BLACK))
        draw_text(t, f8, 0, 8, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", (YELLOW, None, BLACK))
        pal = screen_pal(f"ending_{H}", [(cv, 1), (t, 30)],
                         fixed=(BLACK, (3, 3, 3), (3, 3, 0)))
        full(f"ending_{H}", cv, pal)
        O.pen(f"PN_END_{H}_WHITE", pal.pen(WHITE))
        O.pen(f"PN_END_{H}_YELLOW", pal.pen(YELLOW))

    # ---- the structure panels (build and Starport): one palette for
    # both, the grid's 32x24 icons, the items' pictures at half size (the
    # panel bank doubles them into the 96x56 box)
    import glob
    icon_s, icon_u, item_s, item_u = {}, {}, {}, {}
    for f in sorted(glob.glob(str(UI / "icon_structure_*.png"))):
        icon_s[int(Path(f).name.split("_")[2])] = Path(f).name
    for f in sorted(glob.glob(str(UI / "icon_unit_*.png"))):
        icon_u[int(Path(f).name.split("_")[2])] = Path(f).name
    for f in sorted(glob.glob(str(UI / "build_item_building_*.png"))):
        item_s[int(Path(f).name.split("_")[3])] = Path(f).name
    for f in sorted(glob.glob(str(UI / "build_item_unit_*.png"))):
        item_u[int(Path(f).name.split("_")[3])] = Path(f).name
    for n, m in ((1, 0), (4, 3), (8, 6), (10, 7)):          # ui.txt: the same
        icon_s.setdefault(n, icon_s[m])
    for n in (19, 20, 21):
        icon_u.setdefault(n, icon_u[7])
    buttons = ["icon_exit_line1.png", "icon_repair_line1.png", "icon_cancel_line1.png",
               "icon_repair_off_line1.png", "icon_cancel_off_line1.png"]
    bp = load("build_panel.png").crop((0, 0, 320, 200))
    sp = load("starport_panel.png").crop((0, 0, 320, 200))
    marks = [load("build_marker.png"), load("starport_marker.png")]
    items = [(bp, 1), (sp, 1)] + [(load(f), 1) for f in set(item_s.values()) | set(item_u.values())] \
        + [(load(f), 2) for f in set(icon_s.values()) | set(icon_u.values())] \
        + [(load(f), 4) for f in buttons] + [(m, 20) for m in marks]
    t = canvas()
    draw_text(t, fmenu, 0, 0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", (WHITE, None, BLACK))
    items.append((t, 30))
    pal = screen_pal("panel", items, fixed=(BLACK, (3, 3, 3)))
    full("build_panel", bp, pal)
    full("starport_panel", sp, pal)
    ic = {}
    for f in sorted(set(icon_s.values()) | set(icon_u.values()) | set(buttons)):
        ic[f] = rect("i_" + f[5:-4], opaque(load(f)), 32, 48, pal)
    it = {}
    for f in sorted(set(item_s.values()) | set(item_u.values())):
        half = opaque(load(f)).resize((48, 28), Image.BOX)
        it[f] = rect("p_" + f[11:-4], half, 160, 40, pal)
    sprite("build_marker", marks[0], 32, 48, pal)
    sprite("starport_marker", marks[1], 32, 48, pal)
    O.pen("PN_PANEL_WHITE", pal.pen(WHITE))
    box = tuple(int(v) for v in np.asarray(bp)[106, 200, :3])
    O.pen("PN_PANEL_BOX", pal.index(box, 0, 0))
    P = ["; panel.inc - written by tools/dune_front.py; do not edit.",
         "; the FA_ of each structure type's and unit type's grid icon and",
         "; half-size picture ($FF none), the buttons', and the tables that",
         "; double a plane byte's left or right pixel"]

    def row(label, d, n):
        P.append(label + ":")
        P.append("        DB " + ", ".join(str(d[k]) if k in d else "$FF" for k in range(n)))
    row("pn_icon_s", {k: ic[f] for k, f in icon_s.items()}, 19)
    row("pn_icon_u", {k: ic[f] for k, f in icon_u.items()}, 27)
    row("pn_item_s", {k: it[f] for k, f in item_s.items()}, 19)
    row("pn_item_u", {k: it[f] for k, f in item_u.items()}, 27)
    row("pn_buttons", {k: ic[f] for k, f in enumerate(buttons)}, 5)
    dl = [(b & 0x47) | ((b & 7) << 3) | ((b & 0x40) << 1) for b in range(256)]
    dr = [(b & 0xB8) | ((b >> 3) & 7) | ((b & 0x80) >> 1) for b in range(256)]
    P.append("        ALIGN 256")
    P.append("pn_dupl:")
    P += ["        DB " + ", ".join(f"${v:02X}" for v in dl[i:i + 16]) for i in range(0, 256, 16)]
    P.append("pn_dupr:")
    P += ["        DB " + ", ".join(f"${v:02X}" for v in dr[i:i + 16]) for i in range(0, 256, 16)]
    (Path(out) / "panel.inc").write_text("\n".join(P) + "\n")
    prev["panel"] = (bp, pal)

    # ---- the sound test and the music test: the port's ids for the names
    ids = {}
    si = Path(out) / "sound_ids.inc"
    if si.exists():
        for line in si.read_text().splitlines():
            m = re.match(r"((?:MUS|SFX)_\w+)\s+EQU\s+(\d+)", line)
            if m:
                ids[m.group(1)] = int(m.group(2))
    txt = ROOT / "src/res/data/text"

    def names(f):
        return [re.sub(r"[^a-z0-9]+", "_", m.group(1).strip().lower()).strip("_")
                for m in re.finditer(r'^@\S+\s+"([^"]*)"', (txt / f).read_text(), re.M)]
    mus = [ids.get(f"MUS_{n.upper()}", 255) for n in names("music_test.txt")]
    sfx = [ids.get(f"SFX_{n.upper()}", 255) for n in names("sound_test.txt")]
    O.lines.append("fe_music_ids:\t; the music test's tunes as MUS_ ids ($FF: not in the set)")
    O.lines.append("        DB " + ", ".join(str(v) for v in mus))
    O.lines.append("fe_sound_ids:\t; the sound test's effects as SFX_ ids")
    O.lines.append("        DB " + ", ".join(str(v) for v in sfx))

    npages, used = O.write(Path(out))
    import dune_tutorial                    # the Tutorial: its own pages
    dune_tutorial.build(Path(out))
    if preview:
        d = Path(preview)
        d.mkdir(parents=True, exist_ok=True)
        for name, (cv, pal) in prev.items():
            q = quantize(cv, pal, 0, 0)
            rgb = np.array([ega_rgb(c) for c in pal.cols], np.uint8)
            img = rgb[np.maximum(q, 0)]
            Image.fromarray(img).save(d / f"{name}.png")
    print(f"dune_front: {len(O.assets)} assets in {npages} pages from "
          f"{PG_FRONT_ART} ({used} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "build/gen"))
    ap.add_argument("--preview")
    args = ap.parse_args()
    build(Path(args.out), args.preview)


if __name__ == "__main__":
    main()
