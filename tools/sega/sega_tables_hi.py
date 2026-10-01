#!/usr/bin/env python3
"""The data in banks 02 to 05 ($020000-$05FFFF) that nothing named yet.

Every entry says what the bytes are and who reads them, and `check()`
asserts each mechanical property the reading rests on: record counts
against the loop bounds and immediates in the reading code, frames whose
piece count gives their length exactly, pointer tables whose strides and
targets agree, Format80 streams that end on their own $80, strings that
end on their NUL, palettes whose every word is a CRAM colour, and code
that decodes and re-encodes.

Two readings here correct regions already named elsewhere:

- BUILD/PLAYER/TEAM/UNIT.EMC end at $04F6BE, not $0522A4.  UNIT.EMC's own
  FORM header says $153A, and $04DB28 + $042E + 4 = $04DF5A shows the
  length counts from after the tag; the 11 238 bytes after it are tiles,
  a Format80 block and two fonts (below).
- Every "N tiles, Format80" region stops one byte short: the $80 that
  ends the stream (the decompressor at $000C3E reads it) is left out.  The
  ones in this range are claimed here.

`$029AB0-$02DC8C` is a byte-for-byte copy of `$000000-$0041DC` (all but
16 header bytes - an April build's "T-50 1994.APR" and its serial and
checksum), which is why a second Z80 driver sits inside it; the sweep's
"code" at $029BC0-$029C03 and $029CA2-$029CAF is that header's text.

    python3 tools/sega/sega_tables_hi.py        # run check()
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import m68k                                                # noqa: E402
from sega_gfx import lcw                                   # noqa: E402

ROM = HERE.parent.parent / "orig" / "dune2.gen"

FRAME = "a sprite frame in the $02EC72 layout (a count-1 word, then 12 " \
        "bytes a piece: width, height, y, size/link, attribute, x)"

# The Format80 streams in this range whose closing $80 no region claims:
# (where the stream starts, where its $80 is).
F80_ENDS = [
    (0x030888, 0x0312BA), (0x0312BC, 0x031DA7), (0x031DA8, 0x032469),
    (0x03324C, 0x033B55), (0x033B56, 0x0345B6), (0x0345B8, 0x035029),
    (0x03502A, 0x035ADD), (0x035ADE, 0x035D0A), (0x036E7E, 0x0378A2),
    (0x0378A4, 0x03846C), (0x03846E, 0x0388AE), (0x039214, 0x0399ED),
    (0x0399EE, 0x03A39E), (0x03A3A0, 0x03AD0E), (0x03AD10, 0x03B55E),
    (0x03B560, 0x03BCB4), (0x03BCB6, 0x03C17C), (0x03CA14, 0x03D491),
    (0x03D492, 0x03DF48), (0x03DF4A, 0x03E6AC), (0x03F57A, 0x03FDE2),
    (0x03FDE4, 0x040646), (0x040648, 0x04077F),
]

# The six 64-colour palettes beside the pictures, and where the picture
# data names each one.
PALETTES = [(0x0307F4, 0x041B4E), (0x0331AC, 0x041B88),
            (0x036DEA, 0x041BD6), (0x03916E, 0x041CE8),
            (0x03C980, 0x041FDC), (0x03F4E6, 0x0423D2)]

TABLES = [
    # --- bank 02: the lists, the password screen, the campaign map ---
    (0x020212, 0x020236, "3 x 3 destination cells (x, y words) for the "
                         "rectangle copier at $02017A, indexed arg1*12 + "
                         "arg2*4 at $0201AC"),
    (0x020236, 0x02026C, "3 x 3 (count word, pointer) entries: the "
                         "rectangle lists $02017A copies and $020142 "
                         "counts, indexed arg1*18 + arg2*6"),
    (0x02026C, 0x02038C, "the eight rectangle lists those point at: 36 "
                         "rectangles of four words (x, y, width, height in "
                         "cells), each list ending where the next begins"),
    (0x0204CE, 0x0204D0, "two zero bytes aligning the table after them"),
    (0x0204D0, 0x0204E4, "a byte for each of the 19 structure types and "
                         "one over, read at $0204F0 when a structure is set "
                         "up ($00E5F0, $048C0C): 0 for the two slabs and "
                         "the wall, which join no list, -1 for the two "
                         "turrets, 1 for the rest"),
    (0x02056E, 0x02058A, "a byte for each of the 27 unit types and one "
                         "over, read at $020594, $043378, $043436, $0435A4: "
                         "1 for types 0-17 and the Sandworm, 0 for the "
                         "rockets, bullet, sonic blast and Frigate"),
    (0x02064C, 0x020654, "list heads $FFDBDC and $FFDBD8 - the structures "
                         "friendly to the player and the rest - by list "
                         "number, read at $02065A"),
    (0x020696, 0x02069E, "list heads $FFDBE8 and $FFDBE4, the same for the "
                         "units, read at $0206A4"),
    (0x0206D2, 0x0206DA, "list heads $FFDBDC and $FFDBD8 again, read at "
                         "$0206E0"),
    (0x020700, 0x020708, "list heads $FFDBE8 and $FFDBE4 again, read at "
                         "$02070E"),
    (0x02072E, 0x020736, "list heads $FFDBD8 and $FFDBDC by the answer of "
                         "$023720 (0 hostile, 1 allied): where $02077E "
                         "unlinks a structure from"),
    (0x0207D4, 0x0207DC, "list heads $FFDBE4 and $FFDBE8 by the same "
                         "answer: where $02081A unlinks a unit from"),
    (0x020DA1, 0x020DA2, "the NUL ending 'Off', the last of the options "
                         "screen's words at $020D4F"),
    (0x0215B6, 0x0215BC, "three strings '_', ' ' and '_': the password "
                         "cursor, drawn by $022190 from $021624, $02175A "
                         "and $0217E6"),
    (0x0218F2, 0x0218FE, "'1.2-011794' - the version and its date - a NUL "
                         "and a pad byte, drawn by $022190 from $021A1A"),
    (0x021A2E, 0x021A58, "'ARE YOU SURE?', thirteen spaces and ' YES      "
                         "NO ', 14 bytes each with the NUL, drawn from "
                         "$021AA0, $021AB4 and $021AC8"),
    (0x021CF8, 0x021D06, "seven words, the spacing of the options menu's "
                         "rows (16,16,16,16,32,16,16) - the 32 is the gap "
                         "before Enter Password: how far the pointer jumps, "
                         "read at $021C3C, $021CB6 and $0223B8"),
    (0x021FC6, 0x021FE4, "the password keyboard, three rows of ten: A-Z "
                         "and '<>!!', looked up from the cursor cell at "
                         "$021FB4"),
    (0x02252C, 0x02261E, FRAME + ", 20 pieces: handed to $1000 by $022168"),
    (0x02261E, 0x022758, FRAME + ", 26 pieces: handed to $1000 by $0222EC"),
    (0x022758, 0x022772, FRAME + ", 2 pieces: named at $021D5A and "
                         "$021F1E"),
    (0x022772, 0x02278C, FRAME + ", 2 pieces: named at $021F2E and "
                         "$0222A2"),
    (0x02278C, 0x0227B2, FRAME + ", 3 pieces: named at $0221FA"),
    (0x0227B2, 0x0227B4, "two zero bytes before the code at $0227B4"),
    (0x023750, 0x023756, "each house's side, -1 0 -1 +1 -1 -1 (Harkonnen, "
                         "Atreides, Ordos, Fremen, Sardaukar, Mercenary): "
                         "$023720 calls two houses allies when they are one "
                         "house, when their sides add up to more than zero, "
                         "or when the sum is negative and neither is the "
                         "player's house - the PC game's House_AreAllied"),
    (0x02403E, 0x02405E, "16 words, n/4 for each n: read at $0242B8 by the "
                         "4-bit blitter at $02427E"),
    (0x02405E, 0x02407E, "16 words, n&3 for each n: read at $0242C0"),
    (0x02407E, 0x02417E, "256 bytes, a recolouring applied to each byte of "
                         "pixels when $02427E is asked to: each nibble 1-7 "
                         "becomes 9-F and 8 becomes 0 (read $0242EC-"
                         "$024304)"),
    (0x02417E, 0x02427E, "256 bytes, the transparency mask for a byte of "
                         "pixels: $F for a nibble of colour 0, else 0; "
                         "ANDed in before the pixels are ORed ($024316-"
                         "$02432E)"),
    (0x0244C0, 0x0244C8, "four words, one per animation slot at $FFA500 "
                         "($24 apart): the base $024522 writes to slot+$1A"),
    (0x024B8A, 0x025562, "the campaign map's zoom into a region: ten "
                         "records of $FC, one per region number (-$C46.w, "
                         "0-9, from the records at $096048), each 21 steps "
                         "of (dx, dy, 16.16 scale, width, height) - read by "
                         "$0256AA"),
    (0x025562, 0x02568A, "37 steps of (16.16 scale, width, height), the "
                         "shape of the table before it without dx and dy; "
                         "no instruction or pointer names it and the trace "
                         "never read it"),
    (0x0257E8, 0x025930, "an image of the VDP sprite table: 41 sprites of "
                         "8 bytes linked 1 to 40 and ended by link 0, "
                         "copied to $FFA62C by $0259E0 (82 longs)"),
    (0x025930, 0x025954, "three tables of three Format80 pointers, one per "
                         "playable house: unpacked by $025976 to $FF0000, "
                         "$026004 to $FF1000 and $026024 to $FF1B40"),
    (0x025954, 0x02596C, "two tables of three (dy, dx) word pairs by house, "
                         "added to sprite positions at $025A1E and $025A3C"),
    (0x0276BA, 0x0276E8, "'* Upgrade * ' and 'Dmg:' (14 bytes each, copied "
                         "by $0276F6/$02771E) and three '%8.1d' formats"),
    (0x027900, 0x02793C, "'Out Of Stock', ' Send Order ' and 'Dmg:' (14 "
                         "bytes each, copied from $02794A on) and three "
                         "'%8.1d' formats: the starport's words"),
    (0x029AB0, 0x02C3FE, "a copy of $000000-$00294E, byte for byte but for "
                         "16 header bytes ('(C)T-50 1994.APR', serial, "
                         "checksum): an older build's vectors, header, "
                         "start-up and library, never run or read"),
    (0x02DC88, 0x02DC8C, "the last four bytes of that copy ($0041D8-"
                         "$0041DB), after the Z80 driver's second copy"),
    (0x02DD4C, 0x02DD54, "seven sound numbers and a zero: cannon (fx), "
                         "heavy drop, explosion 1, rifle (fx), machinegun "
                         "(fx), rocket launch, static (fx) (named by the "
                         "sound test at $087FD4) - a list nothing reads"),
    (0x02DD54, 0x02DDAE, "a byte for each sound number 0-89, read by the "
                         "sound call at $02DD22: non-zero ($FF for 0-19, 1 "
                         "for 60-89) starts it through $1664, zero (20-59) "
                         "queues it in the one-sound slot at $FFF800"),
    (0x02DDE2, 0x02DDE4, "two zero bytes before the code at $02DDE4"),
    (0x02E2CE, 0x02E2EE, "eight (x, y) longs by structure layout (+$3C & "
                         "7): the centre of a footprint in 1/256 squares - "
                         "1x1, 1x2, 2x1, 2x2, 3x2, 2x3, 3x3, none - added "
                         "at $02E2C4"),
    (0x02EC56, 0x02EC66, "eight words by house: the palette line OR'd into "
                         "a sprite's attribute at $02EC3E ($0000 $2000 "
                         "$6000 $2000 $4000, then zeros)"),
] + [
    # --- banks 03/04: the palettes and the Format80 end codes ---
    (a, a + 128, "a 64-colour palette: named by the picture data at $%06X, "
                 "faded to by $0006C8" % ref) for a, ref in PALETTES
] + [
    (end, end + 1, "the $80 that ends the Format80 stream at $%06X - the "
                   "decompressor at $000C3E reads it" % start)
    for start, end in F80_ENDS
] + [
    (0x0412F5, 0x0412F6, "a zero byte after the Format80 block that ends at "
                         "$0412F4"),
    (0x0412F6, 0x041376, "a 64-colour palette, named at $04293A"),
    # --- the text strip at $042996 ---
    (0x042AC8, 0x042B48, "128 bytes, character code to glyph number (0-"
                         "$21) for the text strip $042A04 draws"),
    (0x042B48, 0x042CFA, FRAME + ", 36 pieces: the text strip, handed to "
                         "$1000 by $042996"),
    (0x042CFA, 0x04313A, "34 tiles, the text strip's glyphs: DMA'd one at "
                         "a time by $042A04, $042A52 and $0223EC"),
    (0x04313A, 0x04313C, "two zero bytes before the code at $04313C"),
    # --- bank 04: the C library's data ---
    (0x0492E4, 0x04935C, "'Math library must precede standard C library "
                         "...', the C library's printf stub, pushed at "
                         "$049604"),
    (0x049956, 0x049978, "'0123456789abcdef' and '0123456789ABCDEF' with "
                         "their NULs, named at $049A08 and $049A02"),
    (0x049C6E, 0x049C70, "two zero bytes before the code at $049C70"),
    (0x049F36, 0x049F38, "two zero bytes after the code before"),
    (0x049F38, 0x049FB9, "the C library's character classes: EOF and then "
                         "ASCII 0-127 ($80 control, $40 space, $08 "
                         "punctuation, $04 digit, $02 upper, $01 lower, $10 "
                         "hex, $20 octal) - read at $049434 and after"),
    (0x049FB9, 0x049FBC, "three zero bytes"),
    # --- bank 04: the game's static data ---
    (0x049FBC, 0x04A13C, "12 tiles, a frame in colour $B: DMA'd to VRAM "
                         "$7C00 ($C0 words) by $00810A, $0085AE, $008E4C "
                         "and $009282"),
    (0x04A13C, 0x04A14A, FRAME + ", 1 piece: handed to $1000 by $0080F6 "
                         "and $008E38"),
    (0x04A14A, 0x04A1DA, "18 icon slots of (x, y, frame pointer), a grid "
                         "three wide: $008276 places one per entry ($11 "
                         "dbf)"),
    (0x04A1DA, 0x04A2D6, "the 18 one-piece 24x32 frames those slots name"),
    (0x04A2D6, 0x04A2DC, "a position (x $C0, y $68) and its layer byte "
                         "(read at $0012FE), handed to $1000 by $007F1C"),
    (0x04A2DC, 0x04A2F6, FRAME + ", 2 pieces: the one $007F28 shows at it"),
    (0x04A2F6, 0x04A314, "a position (x $A0, y $10), layer 1, and a "
                         "2-piece frame of two 8x24 pieces on tiles $3F0 and "
                         "$3F3 - the same construct as $04A2D6/$04A2DC, which "
                         "$007F1C and $007F28 show; nothing shows this one"),
    (0x04A314, 0x04A514, "four blocks of 4 tiles (128 bytes): the three "
                         "buttons' pictures, named by the records at "
                         "$04A514"),
    (0x04A514, 0x04A544, "three buttons of (x, y, frame, tiles, tiles for "
                         "house 0 otherwise): $00821A places each and DMAs "
                         "its 4 tiles"),
    (0x04A544, 0x04A56E, "the three buttons' one-piece 16x16 frames"),
    (0x04A56E, 0x04A5CE, "12 slots of (x, y, frame pointer), the 3-wide "
                         "grid again: $008FE8 places them ($B dbf) and "
                         "$00920E steers the cursor by them"),
    (0x04A5CE, 0x04A5E6, "six more (x, y) of that grid, rows $90 and $A8 - "
                         "outside both readers' counts, never read"),
    (0x04A5E6, 0x04A68E, "the 12 one-piece 24x32 frames those slots name"),
    (0x04A68E, 0x04A704, "five frames in the $02EC72 layout (1, 1, 2, 3, "
                         "2 pieces), the first handed to $1000 by $008EA8"),
    (0x04A704, 0x04A712, FRAME + ", 1 piece: handed to $1000 by $008EDE"),
    (0x04A712, 0x04A716, "a null pointer, entry -1 of the table after it: "
                         "an object with no structure reads it at $00DEFC"),
    (0x04A716, 0x04A84E, "78 pointers to the structure records in RAM, "
                         "$FF4EB8 on, $62 apart - read at $00B7D0 and 12 "
                         "more"),
    (0x04A84E, 0x04A852, "a null pointer, entry 0 of the unit table read "
                         "one-based ($045384) and -1 of it at $00E1DC"),
    (0x04A852, 0x04A9EA, "102 pointers to the unit records in RAM, $FF1000 "
                         "on, $8C apart - $0431C8 walks all $66"),
    (0x04A9EA, 0x04A9F2, "four words that are array sizes: $37C8 = 102 "
                         "units x $8C, $0540 = 16 x $54 (what $02DE60 "
                         "returns), $01A4 = 6 x $46 (what $0227D8 clears), "
                         "$1DDC = 78 structures x $62; nothing reads them"),
    (0x04A9F2, 0x04AA06, "5 pointers to $20-byte records at $FF7C9C: "
                         "cleared by $0045DE, read at $0235F0"),
    (0x04AA06, 0x04AA1A, "5 pointers to $20-byte records at $FFBDFC: "
                         "cleared by $0045E4, read at $0434EA"),
    (0x04AA1A, 0x04AA1C, "two zero bytes"),
    (0x04AA1C, 0x04AA20, "the map's address, $FF7D9C: four bytes a square, "
                         "loaded by 118 instructions"),
    (0x04AA20, 0x04AA24, "a null pointer, passed to $004C88 at $012564"),
    (0x04AA24, 0x04AA28, "a pointer to the icon map after it, loaded by "
                         "$0093F2 and 11 more"),
    (0x04AA28, 0x04ADE8, "the icon map (Dune II's ICON.MAP): 27 word "
                         "offsets, then the groups of icon numbers they "
                         "open, 480 words"),
    (0x04ADE8, 0x04DAE8, "the 360 map icons: 4x4 VDP name-table words "
                         "each (32x32 pixels) - $005B54 and $005C8C draw "
                         "the map with them, $00749C one icon"),
    (0x04DAE8, 0x04DB28, "8 pairs of pointers to quarter-rows of the icons "
                         "above, read by index*8 at $00B4B4"),
    # --- after UNIT.EMC's FORM ---
    (0x04F6BE, 0x0506C0, "a length word ($1000) and 128 tiles, DMA'd to "
                         "VRAM $8000 by $008172, $008E82 and $019A2C"),
    (0x0506C0, 0x050ACC, "a length word ($1000) and a Format80 block of "
                         "4096 bytes: 128 tiles, unpacked by $019A52 and "
                         "$025A66"),
    (0x050ACC, 0x050C2C, "11 tiles, a blank and the digits 0-9: $00A610 "
                         "picks one per character, $009638 blanks with "
                         "the first"),
    (0x050C2C, 0x051C2C, "a 128-glyph font indexed by character code: "
                         "$022190 draws with it when asked, $026E46 sends "
                         "it all to VRAM $A000"),
    (0x051C2C, 0x052C2C, "the other 128-glyph font, $022190's default; its "
                         "last 8 bytes are also $052C24, the file "
                         "directory less one entry ($0046E4, $004A78)"),
]

CODE = [
    (0x02017A, "the entry of the rectangle copier the sweep decoded from "
               "$020190: saves all, reads three arguments"),
    (0x02281A, "clears $FFDC24 and $FFDC08 and returns; no caller found"),
    (0x02DC8C, "jmp $168A.w and an rts: a sound-library stub; no caller"),
    (0x02DC92, "jmp $1698.w and an rts: a sound-library stub; no caller"),
    (0x02DDBE, "jmp $16A6.w and an rts: a sound-library stub; no caller"),
    (0x02DDC8, "the rts after the jmp at $02DDC4, never reached"),
    (0x02DE6A, "clears $FFDCA0 and $FFDC5C and returns; no caller found"),
    (0x04320C, "clears $FFDE58 and $FFDCBC and returns; no caller found"),
    (0x049C1C, "the signed entry of the long-division helper at $049C2C: "
               "negates, then joins it; no caller found"),
    (0x049C60, "the negative-divisor path of that helper, reached from "
               "$049C26"),
]


def _w(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def _l(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


def frame_end(rom, a):
    """A frame in the $02EC72 layout: count-1 word, 12 bytes a piece."""
    return a + 2 + (_w(rom, a) + 1) * 12


def cstrings(rom, a, end):
    out = []
    while a < end:
        z = rom.index(0, a)
        out.append(rom[a:z].decode("ascii"))
        a = z + 1
    return out


def check(rom):
    rom = bytes(rom)
    # nothing overlaps, everything is inside banks 02-05
    spans = sorted(TABLES)
    for (s, e, _), (s2, _, _) in zip(spans, spans[1:]):
        assert s < e <= s2, hex(s)
    assert spans[0][0] >= 0x020000 and spans[-1][1] <= 0x060000

    # the rectangle lists: 9 entries, chained end to end
    lens = [(_w(rom, 0x020236 + i * 6), _l(rom, 0x020238 + i * 6))
            for i in range(9)]
    live = [(n, p) for n, p in lens if n]
    assert live[0][1] == 0x02026C
    for (n, p), (_, q) in zip(live, live[1:]):
        assert p + n * 8 == q
    assert live[-1][1] + live[-1][0] * 8 == 0x02038C
    assert sum(n for n, _ in live) == 36
    assert rom[0x0201AC:0x0201B2] == bytes.fromhex("43F900020212")

    # the type tables, and their readers
    assert rom[0x0204F0:0x0204F4] == bytes.fromhex("163B00DE")
    assert rom[0x0204D0:0x0204E3] == bytes([0, 0] + [1] * 12 +
                                           [0, 0xFF, 0xFF, 1, 1])
    assert rom[0x02056E:0x020589] == bytes([1] * 18 + [0] * 7 + [1, 0])
    assert rom[0x020594:0x020598] == bytes.fromhex("103B00D8")
    heads = {0x02064C: (0xFFDBDC, 0xFFDBD8), 0x020696: (0xFFDBE8, 0xFFDBE4),
             0x0206D2: (0xFFDBDC, 0xFFDBD8), 0x020700: (0xFFDBE8, 0xFFDBE4),
             0x02072E: (0xFFDBD8, 0xFFDBDC), 0x0207D4: (0xFFDBE4, 0xFFDBE8)}
    for a, v in heads.items():
        assert (_l(rom, a), _l(rom, a + 4)) == v, hex(a)

    # the strings
    assert rom[0x020D9E:0x020DA2] == b"Off\0"
    assert cstrings(rom, 0x0215B6, 0x0215BC) == ["_", " ", "_"]
    assert rom[0x0218F2:0x0218FE] == b"1.2-011794\0\0"
    assert cstrings(rom, 0x021A2E, 0x021A58) == [
        "ARE YOU SURE?", " " * 13, " YES      NO "]
    assert [_w(rom, 0x021CF8 + 2 * i) for i in range(7)] == \
        [16, 16, 16, 16, 32, 16, 16]
    assert rom[0x021FC6:0x021FE4] == b"ABCDEFGHIJKLMNOPQRSTUVWXYZ<>!!"
    assert rom[0x0276BA:0x0276E8] == (b"* Upgrade * \0\0Dmg:        \0\0" +
                                      b"%8.1d\0" * 3)
    assert rom[0x027900:0x02793C] == (b"Out Of Stock\0\0 Send Order \0\0" +
                                      b"Dmg:        \0\0" + b"%8.1d\0" * 3)
    assert rom[0x0492E4] == 0x0A and rom[0x04935B] == 0 and \
        b"Math library must precede" in rom[0x0492E4:0x04935C]
    assert rom[0x049956:0x049978] == (b"0123456789abcdef\0"
                                      b"0123456789ABCDEF\0")

    # every frame's piece count gives its length exactly
    for a, e in [(0x02252C, 0x02261E), (0x02261E, 0x022758),
                 (0x022758, 0x022772), (0x022772, 0x02278C),
                 (0x02278C, 0x0227B2), (0x042B48, 0x042CFA),
                 (0x04A13C, 0x04A14A), (0x04A2DC, 0x04A2F6),
                 (0x04A2FA, 0x04A314), (0x04A704, 0x04A712)]:
        assert frame_end(rom, a) == e, hex(a)
    for first, n, end in [(0x04A1DA, 18, 0x04A2D6), (0x04A544, 3, 0x04A56E),
                          (0x04A5E6, 12, 0x04A68E), (0x04A68E, 5, 0x04A704)]:
        a = first
        for _ in range(n):
            a = frame_end(rom, a)
        assert a == end, hex(first)
    # the slot tables point at those frames, one each, in order
    for tab, n, frames in [(0x04A14A, 18, 0x04A1DA), (0x04A56E, 12, 0x04A5E6)]:
        for i in range(n):
            assert _l(rom, tab + 8 * i + 4) == frames + 14 * i
    assert rom[0x0082A0:0x0082A2] == bytes.fromhex("7411")    # 18 slots
    assert rom[0x00900A:0x00900C] == bytes.fromhex("740B")    # 12 slots
    for i, (f, t0, t1) in enumerate([(0x04A544, 0x04A314, 0x04A314),
                                     (0x04A552, 0x04A414, 0x04A394),
                                     (0x04A560, 0x04A494, 0x04A494)]):
        r = 0x04A514 + 16 * i
        assert (_l(rom, r + 4), _l(rom, r + 8), _l(rom, r + 12)) == \
            (f, t0, t1)
    assert rom[0x008110:0x008116] == bytes.fromhex("223C7C0000C0")

    # the side table and the ally test that reads it
    assert rom[0x023750:0x023756] == bytes.fromhex("FF00FF01FFFF")
    assert rom[0x023732:0x02373A] == bytes.fromhex("103B101CD03B9018")

    # the blitter's tables
    assert [_w(rom, 0x02403E + 2 * n) for n in range(16)] == \
        [n // 4 for n in range(16)]
    assert [_w(rom, 0x02405E + 2 * n) for n in range(16)] == \
        [n & 3 for n in range(16)]

    def nib(n):
        return 0 if n in (0, 8) else n | 8
    assert all(rom[0x02407E + b] == (nib(b >> 4) << 4 | nib(b & 15))
               for b in range(256))
    assert all(rom[0x02417E + b] == ((0xF0 if b >> 4 == 0 else 0) |
                                     (0x0F if b & 15 == 0 else 0))
               for b in range(256))
    assert rom[0x0242B4:0x0242CC] == bytes.fromhex(
        "43FAFD883C31200043FAFDA03E31200043FAFDB84BFAFEB4")

    # the zoom: ten records of 21 steps; the index is 0-9
    assert rom[0x0256B6:0x0256BE] == bytes.fromhex("C0FC00FC49FAF4CE")
    for r in range(10):
        a = 0x024B8A + r * 0xFC
        assert _l(rom, a + 4) == 0x10000
        scales = [_l(rom, a + 12 * k + 4) for k in range(1, 21)]
        assert all(0x6000 <= s <= 0xFF00 for s in scales)
    assert _l(rom, 0x025562) == 0x10000 and (0x02568A - 0x025562) % 8 == 0

    # the sprite table image: 41 entries, links 1..40 then 0
    assert rom[0x0259E0:0x0259EC] == bytes.fromhex("303C005141FAFE0243F900FF")
    links = [rom[0x0257E8 + 8 * i + 3] for i in range(41)]
    assert links == list(range(1, 41)) + [0]
    # nine Format80 pointers, all into the picture banks
    assert all(0x090000 <= _l(rom, 0x025930 + 4 * i) < 0x0B0000
               for i in range(9))

    # the old copy of the cartridge's first 16 KB
    diff = [i for i in range(0x41DC) if rom[0x029AB0 + i] != rom[i]]
    assert len(diff) == 16 and all(0x100 <= i < 0x1C0 for i in diff)
    assert rom[0x029AB0 + 0x110:0x029AB0 + 0x120] == b"(C)T-50 1994.APR"

    # the sound kinds: $FF for 0-19, 0 for 20-59, 1 for 60-89
    assert rom[0x02DD54:0x02DDAE] == bytes([0xFF] * 20 + [0] * 40 + [1] * 30)
    assert rom[0x02DD22:0x02DD26] == bytes.fromhex("123B0030")

    # footprint centres and the house palette bits
    assert [(_w(rom, 0x02E2CE + 4 * i), _w(rom, 0x02E2D0 + 4 * i))
            for i in range(8)] == [(0x80, 0x80), (0x80, 0x100), (0x100, 0x80),
                                   (0x100, 0x100), (0x180, 0x100),
                                   (0x100, 0x180), (0x180, 0x180), (0, 0)]
    assert [_w(rom, 0x02EC56 + 2 * i) for i in range(8)] == \
        [0, 0x2000, 0x6000, 0x2000, 0x4000, 0, 0, 0]

    # palettes: every word a CRAM colour, and named where it says
    for a, ref in PALETTES + [(0x0412F6, None)]:
        assert all(_w(rom, x) & 0xF111 == 0 for x in range(a, a + 128, 2))
        if ref:
            assert _l(rom, ref) == a
    # every Format80 end code is the byte the stream stops on
    for start, end in F80_ENDS:
        _, used = lcw(rom[start:end + 1])
        assert start + used == end + 1 and rom[end] == 0x80, hex(end)

    # the text strip: char map values stay inside the 34 glyphs
    assert max(rom[0x042AC8:0x042B48]) == 0x21
    assert (0x04313A - 0x042CFA) == 34 * 32

    # the character classes
    ct = rom[0x049F38:0x049FB9]
    assert ct[0] == 0 and ct[1 + 0x20] == 0x40 and ct[1 + 0x7F] == 0x80
    assert all(ct[1 + c] & 0x04 for c in range(0x30, 0x3A))
    assert all(ct[1 + c] & 0x02 for c in range(0x41, 0x5B))
    assert all(ct[1 + c] & 0x01 for c in range(0x61, 0x7B))
    assert all(ct[1 + c] & 0x10 for c in b"0123456789abcdefABCDEF")
    assert rom[0x04942E:0x049434] == bytes.fromhex("43F900049F39")

    # the RAM pointer tables, their strides and the sizes that agree
    st = [_l(rom, 0x04A716 + 4 * i) for i in range(78)]
    un = [_l(rom, 0x04A852 + 4 * i) for i in range(102)]
    assert st == [0xFF4EB8 + 0x62 * i for i in range(78)]
    assert un == [0xFF1000 + 0x8C * i for i in range(102)]
    assert _l(rom, 0x04A712) == 0 and _l(rom, 0x04A84E) == 0
    assert rom[0x0431FE:0x043202] == bytes.fromhex("0C430066")
    assert [_w(rom, 0x04A9EA + 2 * i) for i in range(4)] == \
        [102 * 0x8C, 16 * 0x54, 6 * 0x46, 78 * 0x62]
    assert [_l(rom, 0x04A9F2 + 4 * i) for i in range(5)] == \
        [0xFF7C9C + 0x20 * i for i in range(5)]
    assert [_l(rom, 0x04AA06 + 4 * i) for i in range(5)] == \
        [0xFFBDFC + 0x20 * i for i in range(5)]
    assert rom[0x0045EC:0x0045EE] == bytes.fromhex("7213")  # 20 x 8 bytes
    assert _l(rom, 0x04AA1C) == 0xFF7D9C and _l(rom, 0x04AA20) == 0
    assert _l(rom, 0x04AA24) == 0x04AA28

    # the icon map and the icons
    im = [_w(rom, a) for a in range(0x04AA28, 0x04ADE8, 2)]
    assert im[0] == 27 and im[:27] == sorted(im[:27]) and im[26] < len(im)
    assert max(im[27:]) < 360 and (0x04DAE8 - 0x04ADE8) == 360 * 32
    for i in range(16):
        p = _l(rom, 0x04DAE8 + 4 * i)
        assert 0x04ADE8 <= p < 0x04DAE8 and (p - 0x04ADE8) % 4 == 0

    # after UNIT.EMC: its FORM ends where the tiles begin
    assert rom[0x04E180:0x04E184] == b"FORM"
    assert 0x04E180 + _l(rom, 0x04E184) + 4 == 0x04F6BE
    assert _w(rom, 0x04F6BE) == 0x1000 and 0x04F6C0 + 0x1000 == 0x0506C0
    assert _w(rom, 0x0506C0) == 0x1000
    out, used = lcw(rom[0x0506C2:0x050ACC])
    assert len(out) == 0x1000 and 0x0506C2 + used == 0x050ACC
    assert (0x050C2C - 0x050ACC) == 11 * 32
    assert rom[0x02219C:0x0221B0] == bytes.fromhex(
        "47F900050C2C4A6F00166600000847F900051C2C")
    assert rom[0x0046E4:0x0046EA] == bytes.fromhex("41F900052C24")

    # the code
    for a, _ in CODE:
        ins = m68k.decode(rom, a, 0)
        assert m68k.roundtrips(ins), hex(a)
    for a, end in [(0x02017A, 0x020190), (0x02281A, 0x02282A),
                   (0x02DE6A, 0x02DE7A), (0x04320C, 0x04321C),
                   (0x049C1C, 0x049C2C), (0x049C60, 0x049C6E)]:
        p = a
        while p < end:
            ins = m68k.decode(rom, p, 0)
            assert m68k.roundtrips(ins), hex(p)
            p += ins.length
        assert p == end, hex(a)
    return True


def main():
    rom = ROM.read_bytes()
    check(rom)
    n = sum(e - s for s, e, _ in TABLES)
    print(f"{len(TABLES)} tables, {n} bytes; {len(CODE)} code entries - "
          f"check passed")


if __name__ == "__main__":
    main()
