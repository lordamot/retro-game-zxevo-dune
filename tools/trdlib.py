"""Shared constants and helpers for reading/writing TR-DOS .trd disk images.

Format reference: .claude/docs/tools/trd.md
"""

import struct

SECTOR_SIZE = 256
SECTORS_PER_TRACK = 16
TRACKS = 80
SIDES = 2
TOTAL_SECTORS = TRACKS * SIDES * SECTORS_PER_TRACK  # 2560
IMAGE_SIZE = TOTAL_SECTORS * SECTOR_SIZE  # 655360

# Track 0 is entirely reserved for the catalog + system sector.
CATALOG_ENTRY_SIZE = 16
CATALOG_ENTRIES_MAX = 128
CATALOG_BYTES = CATALOG_ENTRY_SIZE * CATALOG_ENTRIES_MAX  # 2048 -> sectors 0-7
SYSTEM_SECTOR_INDEX = 8  # track 0, sector 8
FIRST_DATA_SECTOR_INDEX = SECTORS_PER_TRACK  # track 1, sector 0
DATA_SECTORS_AVAILABLE = TOTAL_SECTORS - SECTORS_PER_TRACK  # 2544

DEFAULT_DISK_TYPE = 0x16  # 80 tracks, 2 sides
TRDOS_SIGNATURE = 0x10

DELETED_MARKER = 0x01
END_OF_CATALOG_MARKER = 0x00

# Offsets within the system sector (track 0, sector 8).
OFF_FIRST_FREE_SECTOR = 0xE1
OFF_FIRST_FREE_TRACK = 0xE2
OFF_DISK_TYPE = 0xE3
OFF_FILE_COUNT = 0xE4
OFF_FREE_SECTORS = 0xE5  # 2 bytes, little-endian
OFF_TRDOS_SIGNATURE = 0xE7
OFF_LABEL = 0xF5  # 8 bytes


def sector_offset(track, sector):
    return (track * SECTORS_PER_TRACK + sector) * SECTOR_SIZE


def linear_to_track_sector(linear_sector):
    return divmod(linear_sector, SECTORS_PER_TRACK)


def parse_catalog_entry(raw):
    """Parse one 16-byte catalog entry. Returns a dict, or None at end of catalog."""
    if raw[0] == END_OF_CATALOG_MARKER:
        return None
    deleted = raw[0] == DELETED_MARKER
    name = raw[0:8].decode("ascii", errors="replace").rstrip(" ")
    file_type = chr(raw[8])
    param1, length, sectors, start_sector, start_track = struct.unpack("<HHBBB", raw[9:16])
    return {
        "deleted": deleted,
        "name": name,
        "type": file_type,
        "param1": param1,
        "length": length,
        "sectors": sectors,
        "start_sector": start_sector,
        "start_track": start_track,
    }


def build_catalog_entry(entry):
    """Build a 16-byte catalog entry from a dict as produced by parse_catalog_entry."""
    name_bytes = entry["name"].encode("ascii")[:8].ljust(8, b" ")
    type_byte = entry["type"].encode("ascii")[:1]
    return (
        name_bytes
        + type_byte
        + struct.pack(
            "<HHBBB",
            entry["param1"],
            entry["length"],
            entry["sectors"],
            entry["start_sector"],
            entry["start_track"],
        )
    )
