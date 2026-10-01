#!/usr/bin/env python3
"""spg.py - write an SPG v1.0 file, the ZX Evolution's paged executable.

    from spg import write_spg
    write_spg(path, pages, pc=0x8000, sp=0xBFFE, page3=0, clock=2)

`pages` maps a RAM page number (0-255) to its bytes (up to 16 KB).  Each
page becomes one block, cut back to the last non-zero byte and rounded up
to 512; an all-zero page is left out (the machine's RAM is cleared by the
loader... or not - so the game clears every page it relies on itself).

The format (as libxpeccy's and ZEsarUX's loaders read it):

    +$00  32 bytes   a description
    +$20  12 bytes   "SpectrumProg"
    +$2C  byte       version, $10
    +$2D  3 bytes    day, month, year - 2000
    +$30  word       PC
    +$32  word       SP
    +$34  byte       the page for window 3
    +$35  byte       bits 0-1 the clock (0 3.5, 1 7, 2 14 MHz), bit 2 EI
    +$36  word       pager address (0: none)
    +$38  word       resident address (0: none)
    +$3A  word       the number of blocks
    +$3C  3 bytes    seconds, minutes, hours
    +$3F  17 bytes   reserved
    +$50  32 bytes   the creator
    +$70  144 bytes  reserved
    +$100 256 x 3    blocks: offset/512 (bit 7 = the last), size/512 - 1
                     (bits 6-7 the packer, 0 = none), page - #00-#DF only,
                     the loaders live above
    +$400            the blocks' bytes, in order
"""

import datetime
import os
import subprocess


def _build_time():
    # the header's date and time, kept reproducible: SOURCE_DATE_EPOCH if
    # set, else the last git commit's time, else (no git) the clock
    ts = os.environ.get("SOURCE_DATE_EPOCH")
    if not ts:
        try:
            ts = subprocess.run(
                ["git", "log", "-1", "--format=%ct"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            ts = ""
    if not ts:
        return datetime.datetime.now()
    return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)


def write_spg(path, pages, pc, sp, page3=0, clock=2, ei=False,
              name="Dune II", creator="tools/spg.py"):
    blocks = []
    for page in sorted(pages):
        data = bytes(pages[page])
        assert len(data) <= 0x4000, f"page {page} is {len(data)} bytes"
        # "Page (#00-#DF are allowed)": the loaders keep themselves in
        # #E0-#FF and a block there overwrites the loader while it runs
        assert page <= 0xDF or not any(data), \
            f"page {page} ({page:#04x}) is above #DF, which the SPG format forbids"
        end = len(data.rstrip(b"\0"))
        if end == 0:
            continue
        end = (end + 511) & ~511
        blocks.append((page, data[:end].ljust(end, b"\0")))
    assert 0 < len(blocks) <= 256, f"{len(blocks)} blocks"
    now = _build_time()
    hd = bytearray(0x100)
    hd[0:32] = name.encode("ascii")[:32].ljust(32, b" ")
    hd[0x20:0x2C] = b"SpectrumProg"
    hd[0x2C] = 0x10
    hd[0x2D:0x30] = bytes([now.day, now.month, now.year - 2000])
    hd[0x30:0x32] = pc.to_bytes(2, "little")
    hd[0x32:0x34] = sp.to_bytes(2, "little")
    hd[0x34] = page3
    hd[0x35] = (clock & 3) | (4 if ei else 0)
    hd[0x3A:0x3C] = len(blocks).to_bytes(2, "little")
    hd[0x3C:0x3F] = bytes([now.second, now.minute, now.hour])
    hd[0x50:0x70] = creator.encode("ascii")[:32].ljust(32, b" ")
    table = bytearray(768)
    body = bytearray()
    for i, (page, data) in enumerate(blocks):
        table[i * 3] = 0 | (0x80 if i == len(blocks) - 1 else 0)
        table[i * 3 + 1] = len(data) // 512 - 1
        table[i * 3 + 2] = page
        body += data
    with open(path, "wb") as f:
        f.write(hd + table + body)
    return len(blocks), 0x400 + len(body)
