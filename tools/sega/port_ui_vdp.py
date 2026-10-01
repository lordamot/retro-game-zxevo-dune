"""port_ui_vdp.py - the Mega Drive VDP, layer by layer, for port_ui.py.

A screenshot mixes the two planes, the window and the sprites; the port
needs them apart.  This reads one moment's dumps (vram, cram, vsram,
vdpreg, as bin/gen/retro-run writes them) and draws each layer on its own,
as RGBA with alpha 0 wherever the layer's pixel is pen 0 - which is what
the VDP itself treats as "nothing here".

Genesis Plus GX stores VRAM and VSRAM as native-endian 16-bit words, so
every byte address is XORed with 1 (CLAUDE.md, "Genesis Plus GX stores
VRAM native-endian").  CRAM words are BBBGGGRRR, each channel v*255//7.
"""

from pathlib import Path

import numpy as np
from PIL import Image


def md_colour(w):
    return ((w & 7) * 255 // 7, ((w >> 3) & 7) * 255 // 7,
            ((w >> 6) & 7) * 255 // 7)


class VDP:
    def __init__(self, d):
        d = Path(d)
        self.dir = d
        self.vram = np.frombuffer(d.joinpath("vram.bin").read_bytes(),
                                  np.uint8).reshape(-1, 2)[:, ::-1] \
            .reshape(-1).copy()                       # big-endian again
        cram = d.joinpath("cram.bin").read_bytes()
        self.cramw = [cram[i * 2] | (cram[i * 2 + 1] << 8) for i in range(64)]
        self.pal = [md_colour(w) for w in self.cramw]
        vs = d.joinpath("vsram.bin").read_bytes()
        self.vsram = [vs[i * 2] | (vs[i * 2 + 1] << 8) for i in range(40)]
        self.reg = d.joinpath("vdpreg.bin").read_bytes()
        r = self.reg
        self.h40 = bool(r[12] & 0x81)
        self.sw = 320 if self.h40 else 256
        self.sh = 240 if r[1] & 0x08 else 224
        self.plane_a = (r[2] & 0x38) << 10
        self.win = (r[3] & (0x3C if self.h40 else 0x3E)) << 10
        self.plane_b = (r[4] & 0x07) << 13
        self.sat = (r[5] & (0x7E if self.h40 else 0x7F)) << 9
        self.hs = (r[13] & 0x3F) << 10
        self.pw = [32, 64, 64, 128][r[16] & 3]
        self.ph = [32, 64, 64, 128][(r[16] >> 4) & 3]
        self.backdrop = r[7] & 0x3F
        # the four 16-colour lines as RGBA arrays, pen 0 transparent
        self.lut = np.zeros((4, 16, 4), np.uint8)
        for l in range(4):
            for p in range(16):
                self.lut[l, p, :3] = self.pal[l * 16 + p]
                self.lut[l, p, 3] = 0 if p == 0 else 255
        # every pattern as 8x8 pens
        v = self.vram
        hi, lo = v >> 4, v & 15
        pix = np.stack([hi, lo], -1).reshape(2048, 8, 8)
        self.tiles = pix

    # --------------------------------------------------------------- words
    def w16(self, a):
        a &= 0xFFFF
        return (int(self.vram[a]) << 8) | int(self.vram[(a + 1) & 0xFFFF])

    def palette_lines(self):
        return [[self.cramw[l * 16 + p] for p in range(16)] for l in range(4)]

    # -------------------------------------------------------------- tiles
    def tile(self, e):
        """Pens of a name-table entry's pattern, flipped as it says."""
        t = self.tiles[e & 0x7FF]
        if e & 0x0800:
            t = t[:, ::-1]
        if e & 0x1000:
            t = t[::-1, :]
        return t

    def tile_rgba(self, e):
        return self.lut[(e >> 13) & 3][self.tile(e)]

    def entry(self, base, tx, ty, pw=None, ph=None):
        pw = pw or self.pw
        ph = ph or self.ph
        return self.w16(base + ((ty % ph) * pw + (tx % pw)) * 2)

    def plane_map(self, base, pw=None, ph=None):
        pw = pw or self.pw
        ph = ph or self.ph
        return np.array([[self.entry(base, x, y, pw, ph) for x in range(pw)]
                         for y in range(ph)], np.int32)

    def plane_rgba(self, base, pw=None, ph=None, prio=None):
        """The whole name table, unscrolled, RGBA (and a priority mask)."""
        m = self.plane_map(base, pw, ph)
        h, w = m.shape
        img = np.zeros((h * 8, w * 8, 4), np.uint8)
        pri = np.zeros((h * 8, w * 8), bool)
        for y in range(h):
            for x in range(w):
                e = int(m[y, x])
                if prio is not None and bool(e & 0x8000) != prio:
                    continue
                img[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = self.tile_rgba(e)
                pri[y * 8:y * 8 + 8, x * 8:x * 8 + 8] = bool(e & 0x8000)
        return img, pri, m

    # ------------------------------------------------------------- scroll
    def hscroll(self, line, plane):
        """Horizontal scroll of a plane (0 A, 1 B) on a screen line."""
        mode = self.reg[11] & 3
        row = {0: 0, 1: line & 7, 2: line & ~7, 3: line}[mode]
        return self.w16(self.hs + row * 4 + plane * 2) & 0x3FF

    def vscroll(self, col, plane):
        if self.reg[11] & 4:
            return self.vsram[(col // 2) * 2 + plane] & 0x3FF
        return self.vsram[plane] & 0x3FF

    def screen_plane(self, which):
        """A plane as it appears on the screen (scrolled), RGBA + prio."""
        base = self.plane_a if which == 0 else self.plane_b
        full, pri, _ = self.plane_rgba(base)
        H, W = full.shape[:2]
        out = np.zeros((self.sh, self.sw, 4), np.uint8)
        op = np.zeros((self.sh, self.sw), bool)
        xs = np.arange(self.sw)
        for y in range(self.sh):
            hs = self.hscroll(y, which)
            for cx in range(0, self.sw, 16):
                vs = self.vscroll(cx // 8, which)
                sy = (y + vs) % H
                sx = (xs[cx:cx + 16] - hs) % W
                out[y, cx:cx + 16] = full[sy, sx]
                op[y, cx:cx + 16] = pri[sy, sx]
        return out, op

    def window_area(self):
        """(x0, x1, y0, y1) in pixels of the window plane, or None."""
        h, v = self.reg[17], self.reg[18]
        hp, vp = (h & 0x1F) * 16, (v & 0x1F) * 8
        right, down = bool(h & 0x80), bool(v & 0x80)
        if hp == 0 and vp == 0 and not right and not down:
            return None
        x0, x1 = (hp, self.sw) if right else (0, hp)
        y0, y1 = (vp, self.sh) if down else (0, vp)
        # the window covers the union of its column band and its row band
        return (x0, x1, y0, y1)

    def screen_window(self):
        """The window plane, where it is shown, RGBA; else None."""
        wa = self.window_area()
        if wa is None:
            return None, None
        ww = 64 if self.h40 else 32
        full, pri, _ = self.plane_rgba(self.win, ww, 32)
        out = np.zeros((self.sh, self.sw, 4), np.uint8)
        mask = np.zeros((self.sh, self.sw), bool)
        x0, x1, y0, y1 = wa
        h, v = self.reg[17], self.reg[18]
        if h & 0x1F or h & 0x80:
            mask[:, x0:x1] = True
        if v & 0x1F or v & 0x80:
            mask[y0:y1, :] = True
        out[mask] = full[:self.sh, :self.sw][mask]
        return out, mask

    # ------------------------------------------------------------ sprites
    def sprites(self):
        out, i, seen = [], 0, set()
        for _ in range(80):
            if i in seen:
                break
            seen.add(i)
            o = self.sat + i * 8
            y = self.w16(o) & 0x3FF
            size = int(self.vram[(o + 2) & 0xFFFF])
            link = int(self.vram[(o + 3) & 0xFFFF]) & 0x7F
            attr = self.w16(o + 4)
            x = self.w16(o + 6) & 0x1FF
            out.append({"i": i, "x": x - 128, "y": y - 128, "rawx": x,
                        "w": ((size >> 2) & 3) + 1, "h": (size & 3) + 1,
                        "attr": attr, "tile": attr & 0x7FF,
                        "pal": (attr >> 13) & 3, "hf": (attr >> 11) & 1,
                        "vf": (attr >> 12) & 1, "prio": attr >> 15})
            if link == 0:
                break
            i = link
        return out

    def sprite_rgba(self, s):
        w, h = s["w"], s["h"]
        img = np.zeros((h * 8, w * 8, 4), np.uint8)
        t = s["tile"]
        for cx in range(w):
            for cy in range(h):
                e = (s["attr"] & 0xF800) | ((t + cx * h + cy) & 0x7FF)
                dx = (w - 1 - cx) if s["hf"] else cx
                dy = (h - 1 - cy) if s["vf"] else cy
                img[dy * 8:dy * 8 + 8, dx * 8:dx * 8 + 8] = self.tile_rgba(e)
        return img

    def screen_sprites(self, keep=None):
        """All sprites on the screen, the first in the list on top."""
        out = np.zeros((self.sh, self.sw, 4), np.uint8)
        for s in reversed(self.sprites()):
            if keep is not None and not keep(s):
                continue
            paste(out, self.sprite_rgba(s), s["x"], s["y"])
        return out

    def composite(self):
        bd = self.pal[self.backdrop]
        img = np.zeros((self.sh, self.sw, 4), np.uint8)
        img[..., :3] = bd
        img[..., 3] = 255
        a, ap = self.screen_plane(0)
        b, bp = self.screen_plane(1)
        w, wm = self.screen_window()
        if w is not None:
            a = np.where(wm[..., None], w, a)
        sp = self.screen_sprites()
        for layer in (b, a, sp):       # priority ignored: good enough
            m = layer[..., 3] > 0
            img[m] = layer[m]
        return img


def paste(dst, src, x, y):
    """Alpha-over src onto dst at (x, y), clipped."""
    h, w = src.shape[:2]
    H, W = dst.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x0 >= x1 or y0 >= y1:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    m = s[..., 3] > 0
    dst[y0:y1, x0:x1][m] = s[m]


def save(arr, path):
    Image.fromarray(arr, "RGBA").save(path)


def crop_alpha(arr):
    """Trim fully transparent borders: -> (array, dx, dy)."""
    a = arr[..., 3] > 0
    if not a.any():
        return arr[:0, :0], 0, 0
    ys, xs = np.flatnonzero(a.any(1)), np.flatnonzero(a.any(0))
    return arr[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1], int(xs[0]), int(ys[0])
