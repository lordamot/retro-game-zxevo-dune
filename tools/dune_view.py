#!/usr/bin/env python3
"""dune_view.py - draw what the battlefield should look like from a RAM
dump, with the Mega Drive's own icons, to set beside a screenshot.

    dune_view.py MAP.bin WORLD.bin OUT.png [--sym build/dune.sym]

MAP.bin is page MAP (26), WORLD.bin page WORLD (25); the view comes from
view_x/view_y.  Also prints the map squares of the view as numbers.
"""
import argparse
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("world")
    ap.add_argument("out")
    ap.add_argument("--sym", default=str(ROOT / "build/dune.sym"))
    a = ap.parse_args()
    sym = {}
    for l in Path(a.sym).read_text().splitlines():
        m = re.match(r"(\S+):\s+EQU\s+0x([0-9A-F]+)", l)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
    mp = Path(a.map).read_bytes()
    w = Path(a.world).read_bytes()
    vx = w[sym["view_x"] - 0x8000] | w[sym["view_x"] - 0x7FFF] << 8
    vy = w[sym["view_y"] - 0x8000] | w[sym["view_y"] - 0x7FFF] << 8
    icons = Image.open(ROOT / "src/res/art/icons.png").convert("RGBA")
    out = Image.new("RGB", (320, 200))
    for py in range(0, 200 + 32, 32):
        for px in range(0, 320 + 32, 32):
            mx, my = (vx + px) // 32, (vy + py) // 32
            if mx > 63 or my > 63:
                continue
            sq = my * 64 + mx
            g = mp[sq] | (mp[0x1000 + sq] & 1) << 8
            o = mp[0x1000 + sq] >> 1
            ox, oy = px - (vx % 32), py - (vy % 32)
            gi = icons.crop(((g % 16) * 32, (g // 16) * 32, (g % 16) * 32 + 32, (g // 16) * 32 + 32))
            tile = Image.new("RGBA", (32, 32), (0, 0, 0, 255))
            tile.alpha_composite(gi)
            if o:
                oi = icons.crop(((o % 16) * 32, (o // 16) * 32, (o % 16) * 32 + 32, (o // 16) * 32 + 32))
                tile.alpha_composite(oi)
            if o == 0x7B:
                tile = Image.new("RGBA", (32, 32), (0, 0, 0, 255))
            out.paste(tile.convert("RGB"), (ox, oy))
    out.save(a.out)
    print(f"view {vx},{vy}")
    for my in range(vy // 32, vy // 32 + 7):
        print(" ".join(f"{mp[my*64+mx] | (mp[0x1000+my*64+mx]&1)<<8:03X}/{mp[0x1000+my*64+mx]>>1:02X}"
                       for mx in range(vx // 32, vx // 32 + 10)))


if __name__ == "__main__":
    main()
