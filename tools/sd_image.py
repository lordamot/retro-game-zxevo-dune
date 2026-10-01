#!/usr/bin/env python3
"""sd_image.py - an SD card image for the emulator: an MBR, one FAT16 or
FAT32 partition, the given files in its root directory.

    sd_image.py OUT.img [--fat32] [--size MB] FILE...

bin/evo/evo-run reads it with `--sd OUT.img` (`sd F` in a script) as the
firmware would a real card, and the disk loader (src/loader/loader.asm)
finds DUNE.DAT on it.  The file system is written here, not by a host
tool: FAT16 unless --fat32, the files as one contiguous cluster chain
each, 8.3 names in upper case.  It is what a card formatted by anything
looks like to the loader, apart from fragmentation, which the loader
follows through the FAT anyway.
"""

import os
import struct
import sys
import time

SECTOR = 512
PART_START = 2048               # the partition's first sector, as fdisk does


def name83(path):
    base = os.path.basename(path).upper()
    stem, _, ext = base.rpartition(".")
    if not stem:
        stem, ext = ext, ""
    return stem[:8].ljust(8).encode() + ext[:3].ljust(3).encode()


def layout(total, fat32):
    """The BPB numbers for a partition of `total` sectors."""
    if fat32:
        spc, rsv, nfat, rootent = 8, 32, 2, 0
        clusters = (total - rsv) // spc
        spf = (clusters * 4 + SECTOR - 1) // SECTOR
        clusters = (total - rsv - nfat * spf) // spc
    else:
        rsv, nfat, rootent = 4, 2, 512
        spc = 1
        while (total - rsv) // spc >= 65525:
            spc *= 2
        clusters = (total - rsv - rootent * 32 // SECTOR) // spc
        spf = (clusters * 2 + SECTOR - 1) // SECTOR
        clusters = (total - rsv - nfat * spf - rootent * 32 // SECTOR) // spc
    return spc, rsv, nfat, rootent, spf, clusters


def boot_sector(total, fat32, spc, rsv, nfat, rootent, spf, label):
    b = bytearray(SECTOR)
    b[0:3] = b"\xEB\x58\x90" if fat32 else b"\xEB\x3C\x90"
    b[3:11] = b"EVODUNE "
    struct.pack_into("<HBHBHHBHHHII", b, 11, SECTOR, spc, rsv, nfat, rootent,
                     total if total < 65536 else 0, 0xF8,
                     0 if fat32 else spf, 32, 64, PART_START,
                     total if total >= 65536 or fat32 else 0)
    vol = int(time.time()) & 0xFFFFFFFF
    if fat32:
        struct.pack_into("<IHHIHH", b, 36, spf, 0, 0, 2, 1, 6)
        b[64] = 0x80
        b[66] = 0x29
        struct.pack_into("<I", b, 67, vol)
        b[71:82] = label
        b[82:90] = b"FAT32   "
    else:
        b[36] = 0x80
        b[38] = 0x29
        struct.pack_into("<I", b, 39, vol)
        b[43:54] = label
        b[54:62] = b"FAT16   "
    b[510:512] = b"\x55\xAA"
    return b


def main():
    args = sys.argv[1:]
    if not args or "-h" in args:
        sys.exit(__doc__)
    out = args.pop(0)
    fat32 = "--fat32" in args
    size_mb = None
    if "--size" in args:
        i = args.index("--size")
        size_mb = int(args[i + 1])
        del args[i:i + 2]
    files = [a for a in args if a != "--fat32"]
    total_bytes = sum(os.path.getsize(f) for f in files)
    if size_mb is None:
        size_mb = max(64 if not fat32 else 80, total_bytes // (1 << 20) * 2 + 16)
    total = size_mb * 2048                     # the partition, in sectors
    spc, rsv, nfat, rootent, spf, clusters = layout(total, fat32)
    label = b"DUNE       "
    part = bytearray(total * SECTOR)
    part[0:SECTOR] = boot_sector(total, fat32, spc, rsv, nfat, rootent, spf, label)
    fat_off = rsv * SECTOR
    if fat32:
        fsinfo = bytearray(SECTOR)
        fsinfo[0:4] = b"RRaA"
        fsinfo[484:488] = b"rrAa"
        struct.pack_into("<II", fsinfo, 488, 0xFFFFFFFF, 3)
        fsinfo[510:512] = b"\x55\xAA"
        part[SECTOR:2 * SECTOR] = fsinfo
        part[6 * SECTOR:7 * SECTOR] = part[0:SECTOR]
        part[7 * SECTOR:8 * SECTOR] = fsinfo
        root_off = fat_off + nfat * spf * SECTOR      # cluster 2
        data_off = root_off
        eoc = 0x0FFFFFFF
    else:
        root_off = fat_off + nfat * spf * SECTOR
        data_off = root_off + rootent * 32
        eoc = 0xFFFF
    csz = spc * SECTOR

    def fat_set(c, v):
        if fat32:
            struct.pack_into("<I", part, fat_off + c * 4, v)
        else:
            struct.pack_into("<H", part, fat_off + c * 2, v)

    fat_set(0, 0x0FFFFFF8 if fat32 else 0xFFF8)
    fat_set(1, eoc)
    nxt = 2
    if fat32:
        fat_set(2, eoc)                        # the root directory's cluster
        nxt = 3
    t = time.localtime()
    dirent = 0
    entry = bytearray(32)
    entry[0:11] = label
    entry[11] = 0x08                           # the volume label
    part[root_off:root_off + 32] = entry
    dirent = 1
    for f in files:
        data = open(f, "rb").read()
        n = (len(data) + csz - 1) // csz
        if nxt + n > clusters + 2:
            sys.exit(f"sd_image: {f} does not fit ({n} clusters of {csz})")
        first = nxt
        for i in range(n):
            c = nxt + i
            o = data_off + (c - 2) * csz
            part[o:o + min(csz, len(data) - i * csz)] = data[i * csz:(i + 1) * csz]
            fat_set(c, c + 1 if i < n - 1 else eoc)
        nxt += n
        e = bytearray(32)
        e[0:11] = name83(f)
        e[11] = 0x20
        struct.pack_into("<H", e, 22, (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2))
        struct.pack_into("<H", e, 24, ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday)
        struct.pack_into("<H", e, 20, first >> 16)
        struct.pack_into("<H", e, 26, first & 0xFFFF)
        struct.pack_into("<I", e, 28, len(data))
        part[root_off + dirent * 32:root_off + dirent * 32 + 32] = e
        dirent += 1
        print(f"  {f}: {len(data)} bytes, clusters {first}-{nxt - 1}")
    if nfat == 2:
        part[fat_off + spf * SECTOR:fat_off + 2 * spf * SECTOR] = \
            part[fat_off:fat_off + spf * SECTOR]
    mbr = bytearray(SECTOR)
    mbr[0x1BE:0x1CE] = (bytes([0x80, 0, 0, 0, 0x0C if fat32 else 0x06, 0xFE, 0xFF, 0xFF])
                        + struct.pack("<II", PART_START, total))
    mbr[510:512] = b"\x55\xAA"
    with open(out, "wb") as o:
        o.write(mbr)
        o.write(b"\0" * (PART_START - 1) * SECTOR)
        o.write(part)
        o.truncate((PART_START + total + 2048) * SECTOR)
    print(f"{out}: {'FAT32' if fat32 else 'FAT16'}, {size_mb} MB partition at sector "
          f"{PART_START}, {spc} sectors a cluster, {clusters} clusters")


if __name__ == "__main__":
    main()
