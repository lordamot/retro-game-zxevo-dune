#!/usr/bin/env python3
"""sega_blocks.py - what the rest of banks 06 to 0F is.

    sega_blocks.py [--rom orig/dune2.gen]

The regions `sega_extract.py` could only call "data the code at $X points
at", "seen to read", "sent to VRAM" or "pixel-shaped, NOT confirmed", and
the gaps nobody claimed, from $060000 to the end - read one by one from
the code that uses them.  `BLOCKS` is (start, end exclusive, what it is
and who reads it), in the house style of `NAMED`; `CODE` is routines
found sitting as data; `check(rom)` asserts the mechanical properties the
names rest on, and running this file runs it.

The animation table's own pixels and lists ($0619AC-$071573, what the
records at $060E84 name) are not here - only what sits among them.

Three things the existing regions have wrong, which these fix:

- The missions end at $060E84, not $0609C8: SCENO009.INI's last 1212
  bytes were left over from before its records were parsed.
- Every Format80 extent from the art finder stops one byte short.
  `lcw(expect=size)` quits when the output is full, but $000C32 goes on
  to read the $80 that ends the stream - which is why the trace shows 78
  one-byte "read by $000C3E" regions, each a $80 right after a stream.
  `END_MARKS` names the ones from $060000 on.
- The eight "128 tiles" blocks at $0C3D8A-$0C4FF2 and $0C500A-$0C5DAA
  are not tiles but four frames each of a 64 x 32 tile map: the burning
  wreck after a lost battle and the surrender after a won one, played by
  $0C7DEC and $0C7E22 into the window plane.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sega_gfx import lcw                         # noqa: E402
from sega_scen import parse as scen_parse        # noqa: E402

# (stream start, the $80 that ends it): the byte after each art finder
# extent.  A picture's stream starts at its record + $CA.
END_MARKS = [
    (0x0883B2, 0x088961),
    (0x088A2C, 0x089192),
    (0x08925E, 0x0897E5),
    (0x0898B0, 0x089E9C),
    (0x089F68, 0x08A6ED),
    (0x08A7B8, 0x08AD1A),
    (0x08ADE6, 0x08B52E),
    (0x08B5FA, 0x08BD54),
    (0x08BE20, 0x08C5B2),
    (0x08C67E, 0x08CB94),
    (0x08CC60, 0x08D21F),
    (0x08D2EA, 0x08D874),
    (0x08D940, 0x08DE00),
    (0x08DECC, 0x08E379),
    (0x08E444, 0x08EA78),
    (0x08EB44, 0x08F1C7),
    (0x08F316, 0x08F8C5),
    (0x08F990, 0x08FDAF),
    (0x090526, 0x090C2C),
    (0x090CF8, 0x0912D9),
    (0x0913A4, 0x091AFF),
    (0x091BCA, 0x092191),
    (0x09225C, 0x0927E8),
    (0x0928B4, 0x092DAC),
    (0x092E78, 0x0933A1),
    (0x09346C, 0x093A7A),
    (0x093B46, 0x094129),
    (0x0941F4, 0x094642),
    (0x09470E, 0x094B46),
    (0x094C12, 0x095107),
    (0x0951D2, 0x09577A),
    (0x095846, 0x095CCF),
    (0x0A6F2A, 0x0A7712),
    (0x0A7714, 0x0A7F82),
    (0x0A7F84, 0x0A873A),
    (0x0A873C, 0x0A8B8E),
    (0x0A8BA0, 0x0A9728),
    (0x0A972A, 0x0A9B92),
    (0x0A9BCE, 0x0AA4EB),
    (0x0AA4EC, 0x0AB1B3),
    (0x0AB1B4, 0x0ABE4A),
    (0x0ABE4C, 0x0AC9AE),
    (0x0AC9B0, 0x0AD42D),
    (0x0AD42E, 0x0AE05E),
    (0x0AE060, 0x0AED34),
    (0x0AED36, 0x0AF80E),
    (0x0AFE9E, 0x0B0A6C),
    (0x0B0A6E, 0x0B1690),
    (0x0B1692, 0x0B211C),
    (0x0B2962, 0x0B327C),
    (0x0B327E, 0x0B38AF),
    (0x0B38B0, 0x0B42AF),
    (0x0B42B0, 0x0B4D3F),
    (0x0B4D40, 0x0B56E2),
    (0x0B56E4, 0x0B60D1),
    (0x0B64C0, 0x0B6C9A),
    (0x0B6C9C, 0x0B75B9),
    (0x0B75BA, 0x0B7E65),
    (0x0B7E66, 0x0B85CC),
    (0x0B85CE, 0x0B8DF2),
    (0x0B8DF4, 0x0B953A),
    (0x0B9552, 0x0B9A93),
    (0x0B9A94, 0x0BA462),
    (0x0BA464, 0x0BAB3B),
    (0x0BAB58, 0x0BB1DA),
    (0x0BB1DC, 0x0BB9AC),
    (0x0BB9AE, 0x0BC09E),
    (0x0BC0A0, 0x0BC4D4),
    (0x0BC50A, 0x0BCD13),
    (0x0BCD14, 0x0BD744),
    (0x0BD746, 0x0BE1DD),
    (0x0BE1DE, 0x0BECFC),
    (0x0BECFE, 0x0BF8C7),
    (0x0BF8C8, 0x0C04D1),
    (0x0C04D2, 0x0C0F60),
    (0x0C0F62, 0x0C11E5),
    (0x0C1202, 0x0C1B22),
    (0x0C1B24, 0x0C2149),
    (0x0C214A, 0x0C2B47),
]

BLOCKS = [

    # ---- the tail of the last mission file -------------------------------
    # SCENO009.INI is the last file in the directory at $052C2C and so has
    # no next entry to end it; read record by record (sega_scen.parse, the
    # switch at $0161F0) it ends on its own $FFFF at $060E82, which is what
    # tools/sega/sega_files.py DATA_END says.  NAMED in sega_extract.py still
    # stops the missions at $0609C8 - the old reading, 1212 bytes short.
    (0x0609C8, 0x060E84, "the last 1212 bytes of SCENO009.INI: its "
                         "reinforcement and unit records and the $FFFF that "
                         "ends it - read by the mission loader at $016294 and "
                         "$016868; NAMED stops the missions here, 1212 bytes "
                         "short"),

    # ---- the unit pictures' table, continued -------------------------------
    (0x08F234, 0x08F24C, "six longwords after the 27 unit-picture pointers "
                         "at $08F1C8: a zero and five copies of $08D220, the "
                         "Starport's picture; $009062 indexes the table with "
                         "no bound, but no caller was seen passing 27 or more"),

    # ---- the options screen's music test and sound test -------------------
    (0x087F30, 0x087F3C, "3 pointers, one a house, into the mentat's string "
                         "table at $087D74: where that house's four strings a "
                         "mission begin - $01F43A takes it, and "
                         "-$10(a2,mission*16) the string"),
    (0x087F3C, 0x087FD4, "the music test: 18 tunes of (name pointer, song "
                         "number) and a null - 'cyrils council' to 'finale'; "
                         "read by the options screen at $020E1C and $0211C2"),
    (0x087FD4, 0x08811C, "the sound test: 40 sounds of (name pointer, sound "
                         "number) and a null - 'target' to 'planet shimmer'; "
                         "read by the options screen at $020E3A and $0212F0"),
    (0x08828C, 0x08829C, "8 colours: $021A6A hands them to $0044C0, which "
                         "writes them to CRAM line 1 from colour 8 - the "
                         "'ARE YOU SURE?' box's"),

    # ---- the Fremen -------------------------------------------------------
    # $022D1A is the palace's special weapon: 1 the Death Hand, 2 the
    # Fremen, 3 the Saboteur.
    (0x095CD0, 0x095CD8, "the Fremen: 4 unit types, one picked at random for "
                         "each by $004396 - Troopers, Trooper, Troopers, "
                         "Troopers - read at $022EEC"),
    (0x095CD8, 0x095CE8, "how many Fremen the palace sends, a byte indexed by "
                         "the sum of bytes 3 and 5 of the record at $FFBE5C: "
                         "5 5 4 4 3 2 1 0, then eight zeros - read at $022EA4"),

    # ---- the campaign map ---------------------------------------------------
    # Ten territories, each drawn twice over from sprite-shaped pieces: a
    # piece list is (x, y, VDP size) then (dx, dy, size) records to a
    # six-byte zero; $023F5C walks it and $02427E blits each piece's tiles
    # into the bitmap at $FF0000, recolouring them by owner.  The tile
    # counts the lists add up to are exactly the byte offsets in $09D114
    # and $09D13C, and the two tile sets end where those counts say.
    (0x095CE8, 0x095CF0, "the campaign map: the tile attribute for each owner "
                         "0-3 - palette lines 0, 2, 1, 3 - read at $02451C"),
    (0x095CF0, 0x095CF8, "the campaign map: for owners 1-3, the offset into "
                         "the palette at $0A2D76 of the six colours $0262F2 "
                         "writes to CRAM for the territory under attack "
                         "(owner 0 is never looked up)"),
    (0x095CF8, 0x095D0C, "the campaign map: ten zero owners - what the border "
                         "pieces are drawn with, read at $023F76 when $025F30 "
                         "draws them"),
    (0x095D0C, 0x095F64, "the campaign map: who owns each of the ten "
                         "territories, a word each (0 nobody, 1 Harkonnen, "
                         "2 Atreides, 3 Ordos), a row before each of the nine "
                         "missions and one after - three tables of 10 x 10, "
                         "Atreides, Ordos, Harkonnen; in the last row the "
                         "player's house owns them all"),
    (0x095F64, 0x095F70, "3 pointers, one a house, to its ownership table "
                         "above - read at $024998 and $025F44"),
    (0x095F70, 0x096048, "the campaign map: for each house and each of nine "
                         "missions, 8 bytes - the arrow's position (-32, -50), "
                         "the arrow picture's offset (0) and the territory "
                         "attacked next - read at $025FB8; Atreides, Ordos, "
                         "Harkonnen"),
    (0x096048, 0x096054, "3 pointers, one a house, to its records above - "
                         "read at $025FA4"),
    (0x096054, 0x096150, "the campaign map: ten piece lists, one a territory, "
                         "for its borders - the tiles at $09631C"),
    (0x096150, 0x096178, "10 pointers, one to each territory's border piece "
                         "list - read at $02455C, $02497E and $025F2A"),
    (0x096178, 0x0962D4, "the campaign map: ten piece lists, one a territory, "
                         "for its land - the tiles at $0986DE"),
    (0x0962D4, 0x0962FC, "10 pointers, one to each territory's land piece "
                         "list - read at $023F10, $024532 and $025F68"),
    (0x0962FC, 0x09631C, "16 words: how many tiles a sprite of each VDP size "
                         "has, (w+1)*(h+1) - read at $023F86 to step through "
                         "the tiles piece by piece"),
    (0x09631C, 0x0986DC, "the campaign map's borders: 286 uncompressed tiles, "
                         "the lines between the ten territories, piece by "
                         "piece; blitted by $0242DE and DMA'd by $0245B0"),
    (0x0986DC, 0x0986DE, "$1A $00 after the border tiles - nothing reads "
                         "them but the fixed-length DMA at $0245B0 running "
                         "past the last territory; $1A is MS-DOS's "
                         "end-of-file mark"),
    (0x0986DE, 0x09CF1E, "the campaign map's land: 578 uncompressed tiles, the "
                         "ten territories in relief, piece by piece; blitted "
                         "by $0242DE and DMA'd by $0245E0"),
    (0x09CF1E, 0x09CF20, "$1A $00 after the land tiles, as after the borders "
                         "- read only by the DMA at $0245E0 running over"),
    (0x09CF20, 0x09D114, "the campaign map's arrow, Format80: 36 tiles, four "
                         "3x3 arrows - up, right, down, left - unpacked by "
                         "$025F94 to $FF0000 and 9 tiles of it sent to VRAM "
                         "$E000 by $025FD6; and a zero to even it"),
    (0x09D114, 0x09D13C, "10 longwords: where each territory's border tiles "
                         "begin, bytes from $09631C - read at $02453C"),
    (0x09D13C, 0x09D164, "10 longwords: where each territory's land tiles "
                         "begin, bytes from $0986DE - read at $024546"),

    # ---- the mentat's buttons and the campaign map's palettes --------------
    (0x0A27F4, 0x0A2810, "Format80, 20 tiles: the frame drawn round the "
                         "chosen button - $025C04 unpacks it and sends it to "
                         "VRAM $B120"),
    (0x0A2810, 0x0A2A3C, "Format80, 40 tiles: the PROCEED and ADVICE buttons "
                         "- $025C3A unpacks it and sends it to VRAM $B3A0 "
                         "after the first mission"),
    (0x0A2A3C, 0x0A2BF6, "Format80, 40 tiles: the YES and NO buttons - "
                         "$025C6C sends them to VRAM $B3A0 before the first "
                         "mission, when the mentat asks you to join"),
    (0x0A2BF6, 0x0A2D76, "three whole palettes, 64 colours, one a house: "
                         "$026082 copies lines 2 and 3 of the player's into "
                         "the campaign map's palette; lines 0 and 1 of each "
                         "are never read"),
    (0x0A2D76, 0x0A2DF6, "a whole palette, 64 colours: the campaign map's - "
                         "$02615E loads it through $000A8A, $026050 takes "
                         "lines 0-1 from it, $02474E cycles colours 40-43 and "
                         "$0262F6 the owners' six-colour flashes"),
    (0x0A2DF6, 0x0A2E76, "a whole palette, 64 colours: the campaign map's "
                         "before the last mission, which $02605E and $02616C "
                         "use instead when the mission is 8"),
    (0x0A2E76, 0x0A2E78, "two zero bytes between the palettes and the stream "
                         "table at $0A2E78"),

    # ---- the score screen and the password screen -------------------------
    (0x0A5D06, 0x0A5D86, "a whole palette, 64 colours: the score and "
                         "password screens' - $02721C loads it through "
                         "$000A8A"),
    (0x0A5D86, 0x0A5E5C, "Format80, 3584 bytes: the score screen's text as a "
                         "tile map, 28 rows of 64 cells - SCORE, TIME, the "
                         "rank, and SPICE HARVESTED / UNITS / STRUCTURES "
                         "DESTROYED BY YOU and ENEMY; $026E64 unpacks it and "
                         "sends it to VRAM $EE00; and a zero to even it"),
    (0x0A5E5C, 0x0A5EDC, "Format80, 3584 bytes: the password screen's tile "
                         "map - YOUR PASSWORD FOR COMPLETING ... MISSION ... "
                         "IS; $026F18 unpacks it and sends it to VRAM $EE00; "
                         "and a zero to even it"),

    # ---- eleven palettes ----------------------------------------------------
    # 11 x 128 bytes from $0A6990 to the asset list at $0A6F10.  Unused
    # slots are magenta, $0E0E.  The screen loader at $0C7D0E sends the
    # third longword of a screen's record at $0C7C18 to $000F56.
    (0x0A6990, 0x0A6A10, "a whole palette, 64 colours: $0080B6 copies line 2 "
                         "of it (the 32 bytes at $0A69D0) into a palette "
                         "buffer; lines 0, 1 and 3 are never read"),
    (0x0A6A10, 0x0A6A90, "a whole palette, 64 colours: screen 0 of the "
                         "screen table at $0C7C18, Select your House - "
                         "$0C7DA8 hands it to $000F56"),
    (0x0A6A90, 0x0A6B10, "a whole palette, 64 colours: screen 9 of the "
                         "screen table at $0C7C18, the burning wreck after a "
                         "lost battle - $0C7DA8 hands it to $000F56"),
    (0x0A6B10, 0x0A6B90, "a whole palette, 64 colours: screen 11 of the "
                         "screen table at $0C7C18, the surrender after a won "
                         "battle - $0C7DA8 hands it to $000F56"),
    (0x0A6B90, 0x0A6C10, "a whole palette, 64 colours: screens 1-3 and 10 "
                         "of the screen table at $0C7C18 - the options and "
                         "the password entry - through $000F56"),
    (0x0A6C10, 0x0A6C90, "a whole palette, 64 colours: $008DF4 copies line 2 "
                         "of it (the 32 bytes at $0A6C50) into a palette "
                         "buffer; the rest is never read"),
    (0x0A6C90, 0x0A6D10, "a whole palette, 64 colours: the battlefield's - "
                         "screen 4 of the screen table at $0C7C18, and "
                         "copied whole by $0080A4, $008DE2 and $00A3F8"),
    (0x0A6D10, 0x0A6D90, "a whole palette, 64 colours: screens 7 and 8 of "
                         "the screen table at $0C7C18 - 8 is Arrakis behind "
                         "the end credits"),
    (0x0A6D90, 0x0A6E10, "a whole palette, 64 colours: screens 12 and 13 of "
                         "the screen table at $0C7C18, the opening's starfield "
                         "and planet"),
    (0x0A6E10, 0x0A6E90, "a whole palette, 64 colours: $01750A hands it to "
                         "the fade at $004308 for colours 16-63 in the "
                         "opening, after screen 13"),
    (0x0A6E90, 0x0A6F10, "a whole palette's worth: $017632 sends the first 48 "
                         "colours to CRAM lines 1-3 through $0044C0; the last "
                         "16 are the magenta filler"),

    # ---- the end of the unit code's tables --------------------------------
    (0x0FEE20, 0x0FEE28, "4 map-square offsets - 0, -1, -64, -65: the square "
                         "and the ones left, above and above-left of it, "
                         "tried in turn by $045E64 with $00E580"),
    (0x0FEE28, 0x0FEE6C, "the Death Hand's blast: 17 pairs of position "
                         "offsets in 1/256 of a square, the first word for "
                         "the position's low half and the second for its "
                         "high - the centre, eight at one square and eight "
                         "at two; read at $0464E4 when unit type 18 "
                         "explodes"),
    (0x0FEE6C, 0x0FEE7E, "9 map-square offsets: the square itself and its "
                         "eight neighbours (0, -1, 1, -64, 64, -65, -63, 65, "
                         "63) - read at $048D5C"),
    (0x0FEE7E, 0x0FEE80, "two zero bytes after the last table, before the "
                         "$FF fill"),
    (0x0641E6, 0x064246, "24 pointers to one-piece sprite lists, 8 facings x 3 frames: $009678 picks (facing+16)/32 + 8*frame and hangs it on a unit's sprite; $01239A and $043BA4 call it only when the unit's square is landscape 8 or 9 (spice) - the harvester's harvesting overlay"),
    (0x064246, 0x064346, "the menu highlight box as a one-colour mask, 8 tiles (a 2x2 left end, then 2x2 of top and bottom edge): $004886 paints every set pixel one colour that cycles with the frame counter and DMAs it to VRAM $F780; $021D74 and $0222D4 DMA the first four tiles as they are"),
    (0x064FE2, 0x065022, "16 pointers to the building-placement cursor's sprite lists, read at $004C16 for cursor states -1..-16: state -k draws four 4x4 quarters of tile $7BC (the pixels at $06473E), quarter j in palette 0 if bit j of k-1 is set and palette 3 if not; entries 0 and 15 point at lists at $064E0E and $064E40"),
    (0x065022, 0x0652DE, "the placement cursor's lists for masks 1-14: 14 sprite lists of four 4x4 pieces, 50 bytes each, named by the table at $064FE2"),
    (0x0652DE, 0x0652F8, "a two-piece sprite list (2x4 tiles of $7BC and its mirror, a 32x32 diamond) in the placement lists' form - no pointer to it and never read"),
    (0x0655F6, 0x065676, "the front-end menu pointer: 4 tiles, DMA'd to VRAM $F780 by $021BD4 (animation record 8 names it too)"),
    (0x065676, 0x065684, "its sprite list: one 2x2 piece of tile $7BC, hung on the pointer's sprite by $021BAC"),
    (0x065B32, 0x065B46, "a sprite list (one 3x3 piece, tile $57F) and the fixed screen position $0110,$0058,$FFFF the sprite object reads it from - both handed to $001000 by $009C7E"),
    (0x065CA6, 0x065CD2, "a sprite list (three pieces, tiles $40E/$412/$416) and its fixed screen position $0070,$0070,$FFFF - both handed to $001000 by $009C06"),
    (0x0673CA, 0x068BCA, "the radar switching on and off: 12 frames of 512 bytes, one 4x4 quarter each (static, then a collapsing line, then a dot), DMA'd to VRAM $D000 one at a time by $005154 and drawn mirrored four ways by the list at $068C66 (animation records 37-48 name the same frames)"),
    (0x068BCA, 0x068C16, "the radar-off script: (delay byte, 24-bit frame) longwords and a zero long, stepped by $005124; started by $004F40"),
    (0x068C16, 0x068C66, "the radar-on script, the same frames backwards; started by $004E2A"),
    (0x068C66, 0x068C98, "the radar-noise sprite list: four 4x4 pieces of tile $680, plain, h-flipped, v-flipped and both - a 64x64 picture from one quarter"),
    (0x06A790, 0x06A7A4, "a sidebar sprite: list (one 4x3 piece, tile $794 - the slot the command icons are DMA'd to) and screen position $0110,$0030,$FFFF; $009C36"),
    (0x06A7A4, 0x06A7B8, "a sidebar sprite: list (one 4x1 piece, tile $7A2, palette 2) and position $0110,$0048,$FFFF; $009C5E"),
    (0x06A7B8, 0x06A7CC, "a sidebar sprite: list (one 4x3 piece, tile $7A6) and position $0110,$0058,$FFFF; $009C9E"),
    (0x06A7CC, 0x06A7E0, "a sidebar sprite: list (one 4x1 piece, tile $7B2, palette 2) and position $0110,$0070,$FFFF; $009CC6"),
    (0x06A7E0, 0x06A7E6, "a screen position $0110,$0050,$FFFF on its own, used by $0096AC/$0096BC"),
    (0x06A7E6, 0x06A80C, "a two-piece sprite list (tiles $7B6, $7B8, palette 1) and two positions for it, $0110,$0010 and $0108,$0010; $009BC8/$009BDA"),
    (0x06A80C, 0x06A82C, "one tile: a small hollow square marker, DMA'd by $004EB0 to the tile the list at $06A82C names"),
    (0x06A82C, 0x06A83A, "its sprite list: one 1x1 piece of tile $7A1, palette 2, offset -3,-3; $004E80"),
    (0x06A83A, 0x06A86C, "the radar's own sprite list: four 4x4 pieces, tiles $680/$690/$6A0/$6B0 in palette 2 - the 64x64 minimap; hung on the radar sprite by $004ED4 and by $005172 when the switch-on script ends"),
    (0x06A86C, 0x06A876, "ten bytes of $FF that nothing reads"),
    (0x06A876, 0x06A8B8, "sound effect numbers, one signed byte for each effect the game asks for (0..$40; negative plays nothing), played through $02DD1E by $00A7E8; the 66th byte is past the guard and never read"),
    (0x06A8B8, 0x06A954, "the music table: 39 records of (song number, frames to play it or -1), read by $00A86C/$00A88C, played through $02DD1E"),
    (0x06A954, 0x06A9B4, "voice numbers: 94 signed bytes (index < $5E, negative = none) mapped to the speech songs 64-66 and played by $00A8F0, then two zero bytes"),
    (0x06A9B4, 0x06AAB4, "64 pointers to the map-icon animation scripts, indexed by animation number & $3F at $00AEAA; entries 0-10 and 47-63 are the empty script at $06AAB4"),
    (0x06AAB4, 0x06AE28, "the map-icon animation scripts: runs of (icon, frames) word pairs ended by 0,$FFFF - flashing lights and the like on the structures; $00AEAA starts one 8*n bytes in"),
    (0x06AE28, 0x06AFA6, "the structure animation scripts in the PC game's opcodes (top nibble 1 abort, 3 pause, 4 rewind, 6 ground tile, 7 jump back): every building record holds three pointers into them at +$40; the first two scripts ($06AE28) are named by nothing and the trace never read any of it"),
    (0x06B9FC, 0x06BA0C, "8 words added to a map position by $00DB94"),
    (0x06BA0C, 0x06BA6C, "6 records of 16 bytes, four icon numbers and four zero words, read by $00D800 and $00D89E-$00DA82"),
    (0x06BA6C, 0x06BA74, "the four neighbour offsets on a 64-square-wide map, N E S W (-64, +1, +64, -1), read by $00EE4C"),
    (0x06BA74, 0x06BB74, "a 256-byte neighbour-mask table copied into RAM at $FFD5B4 by $00EDCC"),
    (0x06BB74, 0x06BBBE, "74 mask values; $00EDEE writes each one's index into the RAM copy of the table above"),
    (0x06BBBE, 0x06BBC2, "the bits 1, 2, 4, 8 - one per neighbour"),
    (0x06BBC2, 0x06BBF2, "4 rows of 12 flag bytes, one row per neighbour, read by $00F3C4"),
    (0x06BBF2, 0x06BC00, "7 map-icon animation numbers ($2E, 0, 0, $2D, 0, $2C, $2B) that $00F7C2 hands to $00AE58"),
    (0x06C620, 0x06C640, "8 (frame, flip) word pairs, one per facing - the form of the table after it; nothing points at it and it was never read"),
    (0x06C640, 0x06C660, "8 (frame, flip) word pairs, one per facing: $012458 picks a unit's sprite frame and flip"),
    (0x06C660, 0x06C680, "8 more (frame, flip) pairs, for another kind of unit; $0123DC"),
    (0x06C680, 0x06C6C0, "16 (frame, flip) pairs; $012320"),
    (0x06C6C0, 0x06C6C4, "the infantry walk cycle, 0 1 0 2, indexed by step & 3 at $012474"),
    (0x06C6C4, 0x06C6E4, "16 sprite numbers ($9F-$A1, $31-$3D) indexed by a nibble at $0124A8"),
    (0x06C6E4, 0x06C6F8, "the five language codes ENG FRE GER ITA SPA, four bytes each, indexed by $FFC03C at $01270C"),
    (0x06C6F8, 0x06C70C, "ten colours, black then nine whites, loaded by $0127D4"),
    (0x06C70C, 0x06C748, "three ramps of ten colours (red, blue, green) fading to black, 20 bytes each, indexed by house at $0127E8 and loaded by $004308"),
    (0x06C748, 0x06C750, "8 signed bytes indexed by facing at $012ED2"),
    (0x06C81C, 0x06C826, "ten zero bytes between the house table and the footprint offsets"),
    (0x06C826, 0x06CC26, "square-sampling offsets: 32 records of 8 longwords (y<<16|x in 1/256 squares), record n for an object n pixels across; $019F74 clamps n to 15..32 and visits each distinct square the offsets land on"),
    (0x06CC26, 0x06CCAA, "33 longwords, the half-size ((n+1)*8 both ways, $180 for the last) subtracted from the position first, same index; $019F70"),
    (0x06CCAA, 0x06CE4E, "the landscape table: 15 records of 28 bytes, one per landscape type (sand to bloom field - what $0057E6 returns), movement speeds at +4..+7; read by $005734, $00F166/$00F506, $016AC6, $046FD8, $0475D6, $04778A, $0477AE, $027436"),
    (0x06CE4E, 0x06CE66, "6 pointers to the initials of the movement types F T H W W S (foot, tracked, harvester, wheeled, winged, slither), matched by $016682"),
    (0x06CE66, 0x06CE7A, "5 pointers to the initials of the team actions N S F K G (normal, staging, flee, kamikaze, guard), matched by $016660"),
    (0x06CE7A, 0x06CE8A, "the map limits for the two map sizes, (first x, first y, width, height): 1,1,62,62 and 16,16,32,32; indexed by $FFC068 at $005A10 and $01A1B8-$01A280"),
    (0x06CE8A, 0x06CEF4, "106 bytes of small words (0, 1, 2) after the map limits - nothing points into them and the trace never read them"),
    (0x06CEF4, 0x06CF9C, "the fourteen orders: 12 bytes each, the name pointer then the record the code reads at +4 ($06CEF8, stride 12, $043718); $0130B0 looks a name up in it"),
    (0x06CF9C, 0x06CFA2, "six zero bytes"),
    (0x06CFA2, 0x06CFA4, "the default language, read into $FFC03C by $0124E2 (0, English), and a zero byte"),
    (0x06CFA4, 0x06D0A4, "sine: 256 signed bytes, 126*sin(2*pi*n/256), read by $01166C"),
    (0x06D0A4, 0x06D1A4, "cosine: the same table a quarter turn on, read by $011652"),
    (0x06D1A4, 0x06D324, "command icon: Palace - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 2)"),
    (0x06D324, 0x06D4A4, "command icon: Vehicle (liteftry) / Vehicle (hvyftry) - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 3, building menu 4)"),
    (0x06D4A4, 0x06D624, "command icon: Hi-Tech - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 5)"),
    (0x06D624, 0x06D7A4, "command icon: IX / Const Yard - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 6, building menu 8)"),
    (0x06D7A4, 0x06D924, "command icon: Windtrap - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 9)"),
    (0x06D924, 0x06DAA4, "command icon: Barracks (wor) / Barracks (barrac) - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 7, building menu 10)"),
    (0x06DAA4, 0x06DC24, "command icon: Starport - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 11)"),
    (0x06DC24, 0x06DDA4, "command icon: Refinery - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 12)"),
    (0x06DDA4, 0x06DF24, "command icon: Repair - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 13)"),
    (0x06DF24, 0x06E0A4, "command icon: Wall - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 14)"),
    (0x06E0A4, 0x06E224, "command icon: Turret - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 15)"),
    (0x06E224, 0x06E3A4, "command icon: R-Turret - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 16)"),
    (0x06E3A4, 0x06E524, "command icon: Spice Silo - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 17)"),
    (0x06E524, 0x06E6A4, "command icon: Outpost - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 18)"),
    (0x06E6A4, 0x06E824, "command icon: Concrete (slab) / Concrete (4slab) - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index building menu 0, building menu 1)"),
    (0x06E888, 0x06EA08, "command icon: the repair wrench - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 27, building menu 19)"),
    (0x06EA08, 0x06EB88, "command icon: Siege Tank - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 10)"),
    (0x06EB88, 0x06ED08, "command icon: Death Hand - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 18)"),
    (0x06ED08, 0x06EE88, "command icon: Quad - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 15)"),
    (0x06EE88, 0x06F008, "command icon: Trooper - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 5)"),
    (0x06F008, 0x06F188, "command icon: Carryall - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 0)"),
    (0x06F188, 0x06F308, "command icon: Tank - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 9)"),
    (0x06F308, 0x06F488, "command icon: Sonic Tank - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 12)"),
    (0x06F488, 0x06F608, "command icon: Trike - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 13)"),
    (0x06F608, 0x06F788, "command icon: Raider Trike - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 14)"),
    (0x06F788, 0x06F908, "command icon: Infantry - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 2)"),
    (0x06F908, 0x06FA88, "command icon: a unit icon named only by animation records 94, 95, 104 - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044"),
    (0x06FA88, 0x06FC08, "command icon: a unit icon named only by animation records 94, 95, 104 - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044"),
    (0x06FC08, 0x06FD88, "command icon: Saboteur - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 6)"),
    (0x06FD88, 0x06FF08, "command icon: 'Thopter - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 1)"),
    (0x06FF08, 0x070088, "command icon: Launcher / Rocket / ARocket / GRocket - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 7, unit menu 19, unit menu 20, unit menu 21)"),
    (0x070088, 0x070208, "command icon: Harvester - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 16)"),
    (0x070208, 0x070388, "command icon: MCV - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 17)"),
    (0x070388, 0x070508, "command icon: Soldier - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 4)"),
    (0x070508, 0x070688, "command icon: Troopers - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 3)"),
    (0x070688, 0x070808, "command icon: a unit icon named only by animation records 94, 95, 104 - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044"),
    (0x070808, 0x070988, "command icon: Sandworm - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 25)"),
    (0x070988, 0x070B08, "command icon: Devastator - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 11)"),
    (0x070B08, 0x070C88, "command icon: Deviator - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu 8)"),
    (0x070D20, 0x070EA0, "command icon: the EXIT button - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu -1, unit menu 28, building menu -1)"),
    (0x070EA0, 0x071020, "command icon: the FIX button - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu -2, unit menu 29, building menu -2)"),
    (0x071020, 0x0711A0, "command icon: the STOP button - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu -3, unit menu 30, building menu -3)"),
    (0x0711A0, 0x071320, "command icon: the FIX button, dimmed - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu -4, unit menu 31, building menu -4)"),
    (0x071320, 0x0714A0, "command icon: the STOP button, dimmed - 4x3 tiles in sprite order, 384 bytes DMA'd whole by $0082E6/$009044 (index unit menu -5, unit menu 32, building menu -5)"),
    (0x06E824, 0x06E888, "the building menu's icon table: 25 pointers for indexes -5..19 (the table proper at $06E838, $00826A's second entry); $0082D0 DMAs the icon"),
    (0x070C88, 0x070D20, "the unit menu's icon table: 38 pointers for indexes -5..32 (the table proper at $070C9C, zero where a unit has no icon); $0082D0 and $00902E"),
    (0x0714A0, 0x0714A4, "the map offset for each map size: 0 and $410 (16 rows and 16 squares in), indexed by $FFC068 at $016868, $0168A2, $01649E"),
    (0x0714A4, 0x0714B4, "8 words 0, 1, 2, 4, 3, 0, 0, 0 read through the table above by $0165BC with a mission-file index (2-5 seen)"),
    (0x0714B4, 0x0714C6, "the eight neighbour offsets on a 64-wide map, N NE E SE S SW W NW, and a zero word - never read"),
    (0x0714C6, 0x0714D6, "the x step of the eight directions in 1/256 squares, read by $019B0C"),
    (0x0714D6, 0x0714E6, "the y step of the eight directions, read by $019B1A"),
    (0x0714E6, 0x0714F2, "three routines, $019D34, $019DB8 and $019E0A, one of which $019CD4 hands to the square walker at $019E0C"),
    (0x0714F2, 0x071552, "24 (x, y*64) pairs: the 8 squares around a square and then the 16 around those; $01A4C4 adds each pair to a position"),
    (0x071552, 0x071562, "8 words after the ring table that the trace never read"),
    (0x071562, 0x07156A, "N E S W as map offsets (-64, 1, 64, -1), read by $01A720"),
    (0x07156A, 0x071572, "the same four offsets again, read by $01AB5C"),
    (0x071572, 0x071574, "two zero bytes before the battlefields"),

    # ---- the screen table and the plane maps it names ---------------------
    # $0C7D0E takes a screen number and reads a 16-byte record at $0C7C18:
    # an asset list (tiles, through $000CD8); a nametable list whose top
    # byte picks the plane through $0C7DDA (0 window, 2 plane B, 4 plane A)
    # and whose entries are $8000|size and a Format80 stream, unpacked to
    # $FF0000 and DMA'd to that plane; a palette for $000F56 or -1; and a
    # block DMA'd to VRAM $8000 (always $04F6BE, the font).  "confirmed"
    # means the unpacked map was found byte for byte in VRAM in a state.
    (0x0C3566, 0x0C356E, "screen 5's nametable list: one map for the window"),
    (0x0C356E, 0x0C3A9A, "Format80, 3584 bytes: a 64 x 28 tile map for the "
                         "window - the battle's structure panel, picture box "
                         "and build list; screen 5, loaded by $0287D8"),
    (0x0C3A9A, 0x0C3AA2, "screen 0's nametable list: one map for the window"),
    (0x0C3AA2, 0x0C3D82, "Format80, 3584 bytes: the tile map of 'Select your "
                         "House' and the three crests; screen 0, $026BCA"),
    (0x0C3D82, 0x0C3D8A, "screen 9's nametable list; its size word $8E00 is "
                         "read again by $0C7DFE for the animation"),
    (0x0C5002, 0x0C500A, "screen 11's nametable list; its size word is read "
                         "again by $0C7E34 for the animation"),
    (0x0C5DBA, 0x0C5DC8, "screen 12's nametable list: two 4096-byte maps for "
                         "plane A"),
    (0x0C5DC8, 0x0C6048, "Format80, 4096 bytes: the opening's starfield, "
                         "plane A at VRAM $E000; screen 12, $0174B2 "
                         "(confirmed)"),
    (0x0C6048, 0x0C622A, "Format80, 4096 bytes: screen 12's second map, at "
                         "VRAM $F000 (confirmed)"),
    (0x0C622A, 0x0C6238, "screen 13's nametable list: two maps for plane B"),
    (0x0C6238, 0x0C6500, "Format80, 4096 bytes, and a zero to even it: the "
                         "opening's planet and the title's backdrop, plane B "
                         "at VRAM $C000; screen 13, $017504 and $01777A "
                         "(confirmed)"),
    (0x0C6500, 0x0C6734, "Format80, 4096 bytes, and a zero to even it: screen "
                         "13's second map, at VRAM $D000 (confirmed)"),
    (0x0C6734, 0x0C673C, "the nametable list of screens 1, 2, 3 and 14 - the "
                         "four records are the same"),
    (0x0C673C, 0x0C6E02, "Format80, 3584 bytes, and a zero to even it: the "
                         "OPTIONS screen; screen 14, $020E04 (confirmed at "
                         "VRAM $6000)"),
    (0x0C6E02, 0x0C6E0A, "screen 10's nametable list"),
    (0x0C6E0A, 0x0C71EE, "Format80, 3584 bytes: 'ENTER YOUR PASSWORD' and its "
                         "letter grid; screen 10, $02163A"),
    (0x0C71EE, 0x0C71F6, "screen 8's nametable list"),
    (0x0C71F6, 0x0C75AA, "Format80, 3584 bytes, and a zero to even it: "
                         "Arrakis among the stars behind the end credits, "
                         "plane B; screen 8, $012796 after the last mission "
                         "(confirmed at VRAM $C000)"),
    (0x0C75AA, 0x0C75B2, "screen 6's nametable list"),
    (0x0C75B2, 0x0C7A60, "Format80, 3584 bytes, and a zero to even it: the "
                         "Starport's order panel, three rows; screen 6, "
                         "$028A14, the case for structure type 11 - never "
                         "reached by the trace"),
    (0x0C7A60, 0x0C7A68, "screen 7's nametable list"),
    (0x0C7A68, 0x0C7C18, "Format80, 3584 bytes: 'DUNE - The Battle for "
                         "Arrakis' for plane A; screen 7, which no call site "
                         "passes and the trace never read"),
    (0x0C7C18, 0x0C7D08, "the screen table: 15 records of four longwords - "
                         "asset list; plane and nametable list; palette or "
                         "-1; font block or 0 - read by $0C7D0E.  Screens 0, "
                         "4-6 and 8-14 are used; 1-3 copy 14"),
    (0x0C7D08, 0x0C7D0E, "$FFFFFFFF $0000 after the 15th record; no screen "
                         "number reaches it"),
    (0x0C7DDA, 0x0C7DEC, "for plane 0, 2 and 4, the RAM words ($FFE01E, "
                         "$FFE022, $FFE024) that hold the window's, plane B's "
                         "and plane A's VRAM base - read at $0C7D46 - then "
                         "three longwords of window register values for "
                         "$0C7E82"),

    # ---- the structure cursor and the effect scripts ----------------------
    (0x0C7EA0, 0x0C7EBC, "7 (x, y) cursor limits, one a structure layout - "
                         "1x1, 2x1, 1x2, 2x2, 2x3, 3x2, 3x3 - $140-32*w and "
                         "$E0-32*h; handed to $004DA8 at $028604 and $028DC4"),
    (0x0C7EBC, 0x0C7EDC, "a map square's eight neighbours as (dx, dy*64) word "
                         "pairs, NW clockwise to W - summed per step at "
                         "$0273B2"),
    (0x0C7EDC, 0x0C7EE2, "3 words (-1, 2, 1) indexed by the first word of a "
                         "landscape record at $06CCBE, read at $027450; -1 "
                         "leaves the square alone, anything else is compared "
                         "with $FFC224-$10 - the first of the 16 fog-edge "
                         "tiles ($FFC224 is the full-fog tile)"),
    (0x0C7EE2, 0x0C7EFE, "14 words: a cursor shape for each of the 7 "
                         "layouts, and 7 more when $00F0FC returns 0 - read "
                         "at $028644"),
    (0x0C7EFE, 0x0C7F0E, "8 words (9 9 9 10 11 11 30 30) indexed by the "
                         "structure layout, handed with the cursor frame to "
                         "$004B34 at $0286AC and $02879A"),
    (0x0C7F0E, 0x0C80A2, "24 effect scripts: (animation-table index into "
                         "$060E84, frames to show) word pairs, each ended by "
                         "(0, $FFFF) - read at $00AEFC and $00B254; three are "
                         "empty"),
    (0x0C80A2, 0x0C8102, "24 pointers, one to each effect script - read by "
                         "$00AEF0"),
    (0x0C8102, 0x0C8104, "two zero bytes before the front end's sample "
                         "directory"),
] + [(mark, mark + 1, "the $80 that ends the Format80 stream at $%06X - "
      "$000C3E reads it; the extent before it stops one byte short"
      % start) for start, mark in END_MARKS]

CODE = [
    (0x0130B0, "looks an order up by name: lea $6CEF2+2, compares through $029A34, steps 12, 14 times; sits as dc.b in rom01.asm"),
]


def _w(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def _l(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _unpacks(rom, start, end, size):
    """A Format80 stream that makes `size` bytes and whose end mark is the
    last byte before `end` (or the one before a zero that evens it)."""
    out, used = lcw(rom[start:start + 0x10000])
    assert len(out) == size, (hex(start), len(out), size)
    stop = start + used
    assert rom[stop - 1] == 0x80, hex(start)
    assert stop == end or (stop + 1 == end and rom[stop] == 0), \
        (hex(start), hex(stop), hex(end))
    return out


def _palette(rom, start, end):
    for a in range(start, end, 2):
        assert not _w(rom, a) & 0xF111, hex(a)


def _check_mine(rom):
    # SCENO009.INI parses straight through to its $FFFF at $060E82
    recs, ok = scen_parse(rom[0x0603DE:0x060E84])
    assert ok and _w(rom, 0x060E82) == 0xFFFF

    # the unit picture table's tail: a zero and five Starport pictures
    assert _l(rom, 0x08F234) == 0
    assert all(_l(rom, 0x08F238 + 4 * i) == 0x08D220 for i in range(5))
    assert _l(rom, 0x08829C + 4 * 11) == 0x08D220

    # the mentat's per-house pointers land on 16-byte records of $087D74
    for i in range(3):
        p = _l(rom, 0x087F30 + 4 * i)
        assert 0x087D74 <= p < 0x087F30 and (p - 0x087D74) % 16 == 12

    # the two test lists: (string, number) pairs, then a null
    for start, end, n in ((0x087F3C, 0x087FD4, 18), (0x087FD4, 0x08811C, 40)):
        assert (end - start) // 8 == n + 1
        for a in range(start, end - 8, 8):
            p = _l(rom, a)
            s = rom[p:rom.index(0, p)]
            assert 0 < len(s) <= 16 and all(32 <= c < 127 for c in s)
            assert _w(rom, a + 4) == 0 and _w(rom, a + 6) < 97
        assert rom[end - 8:end] == bytes(8)

    _palette(rom, 0x08828C, 0x08829C)

    # the Fremen are infantry
    assert [_w(rom, 0x095CD0 + 2 * i) for i in range(4)] == [3, 5, 3, 3]

    # the campaign map
    sizes = [_w(rom, 0x0962FC + 2 * i) for i in range(16)]
    assert sizes == [(s // 4 + 1) * (s % 4 + 1) for s in range(16)]
    assert rom[0x095CF8:0x095D0C] == bytes(20)
    houses = [_l(rom, 0x095F64 + 4 * h) for h in range(3)]
    assert sorted(houses) == [0x095D0C, 0x095DD4, 0x095E9C]
    for h, t in enumerate(houses):
        rows = [[_w(rom, t + 20 * m + 2 * i) for i in range(10)]
                for m in range(10)]
        assert all(0 <= v <= 3 for r in rows for v in r)
        assert rows[-1] == [h + 1] * 10
    recs = [_l(rom, 0x096048 + 4 * h) for h in range(3)]
    assert sorted(recs) == [0x095F70, 0x095FB8, 0x096000]
    for t in recs:
        assert sorted(_w(rom, t + 8 * m + 6) for m in range(9)) != []
        assert all(_w(rom, t + 8 * m + 6) < 10 for m in range(9))
    for table, lists_from, lists_to, offsets, tiles, tiles_end in (
            (0x096150, 0x096054, 0x096150, 0x09D114, 0x09631C, 0x0986DC),
            (0x0962D4, 0x096178, 0x0962D4, 0x09D13C, 0x0986DE, 0x09CF1E)):
        at, total = lists_from, 0
        for i in range(10):
            p = _l(rom, table + 4 * i)
            assert p == at                     # the lists are end to end
            assert _l(rom, offsets + 4 * i) == total * 32
            total += sizes[_w(rom, p + 4)]
            p += 6
            while _l(rom, p):
                total += sizes[_w(rom, p + 4)]
                p += 6
            assert rom[p:p + 6] == bytes(6)
            at = p + 6
        assert at == lists_to
        assert tiles + total * 32 == tiles_end
    assert rom[0x0986DC:0x0986DE] == rom[0x09CF1E:0x09CF20] == b"\x1a\x00"
    _unpacks(rom, 0x09CF20, 0x09D114, 36 * 32)

    # the buttons, the palettes and the two text screens
    _unpacks(rom, 0x0A27F4, 0x0A2810, 20 * 32)
    _unpacks(rom, 0x0A2810, 0x0A2A3C, 40 * 32)
    _unpacks(rom, 0x0A2A3C, 0x0A2BF6, 40 * 32)
    _palette(rom, 0x0A2BF6, 0x0A2E76)
    assert rom[0x0A2E76:0x0A2E78] == bytes(2)
    _palette(rom, 0x0A5D06, 0x0A5D86)
    for a, e in ((0x0A5D86, 0x0A5E5C), (0x0A5E5C, 0x0A5EDC)):
        m = _unpacks(rom, a, e, 0x700 * 2)
        cells = [_w(m, i) for i in range(0, len(m), 2)]
        assert all((c & 0x7FF) < 0x400 for c in cells)
    _palette(rom, 0x0A6990, 0x0A6F10)
    for i, pal in ((0, 0x0A6A10), (9, 0x0A6A90), (11, 0x0A6B10),
                   (1, 0x0A6B90), (2, 0x0A6B90), (3, 0x0A6B90),
                   (10, 0x0A6B90), (4, 0x0A6C90), (7, 0x0A6D10),
                   (8, 0x0A6D10), (12, 0x0A6D90), (13, 0x0A6D90)):
        assert _l(rom, 0x0C7C18 + 16 * i + 8) == pal

    # the unit code's offset tables
    assert [_s16(_w(rom, 0x0FEE20 + 2 * i)) for i in range(4)] == \
        [0, -1, -64, -65]
    pairs = [(_s16(_w(rom, 0x0FEE28 + 4 * i)),
              _s16(_w(rom, 0x0FEE2A + 4 * i))) for i in range(17)]
    assert pairs[0] == (0, 0)
    assert all(abs(a) <= 512 and abs(b) <= 512 for a, b in pairs)
    assert [_s16(_w(rom, 0x0FEE6C + 2 * i)) for i in range(9)] == \
        [0, -1, 1, -64, 64, -65, -63, 65, 63]
    assert rom[0x0FEE7E:0x0FEE80] == bytes(2) and rom[0x0FEE80] == 0xFF

    # every Format80 stream ends on its $80, one byte past the extent the
    # art finder gave it
    for start, mark in END_MARKS:
        out, used = lcw(rom[start:start + 0x10000])
        assert start + used == mark + 1 and rom[mark] == 0x80, hex(start)


def _check_bank06(rom):
    w = lambda a: int.from_bytes(rom[a:a + 2], "big")
    l = lambda a: int.from_bytes(rom[a:a + 4], "big")
    s8 = lambda b: b - 256 if b > 127 else b

    def plist(a):                              # count-1, then 12 bytes a piece
        return a + 2 + 12 * (w(a) + 1)

    # the harvesting overlay: 24 pointers, every one a one-piece list
    for k in range(24):
        p = l(0x0641E6 + 4 * k)
        assert 0x064096 <= p < 0x0641E6 and w(p) == 0
    # the highlight box is a one-colour mask
    assert set(rom[0x064246:0x064346]) == {0, 0x11}
    # placement: 16 pointers, list k's quarters coloured by the bits of k
    ends = []
    for k in range(16):
        p = l(0x064FE2 + 4 * k)
        assert w(p) == 3
        for j in range(4):
            attr = w(p + 2 + 12 * j + 8)
            assert attr & 0x7FF == 0x7BC
            assert (attr & 0x6000 == 0) == bool(k >> j & 1)
        ends.append(plist(p))
    assert l(0x064FE2 + 4 * 1) == 0x065022 and max(ends) == 0x0652DE
    assert plist(0x0652DE) == 0x0652F8
    # list-then-position records end on $FFFF
    for a, pos in ((0x065B32, 0x065B40), (0x065CA6, 0x065CCC),
                   (0x06A790, 0x06A79E), (0x06A7A4, 0x06A7B2),
                   (0x06A7B8, 0x06A7C6), (0x06A7CC, 0x06A7DA),
                   (0x06A7E6, 0x06A800)):
        assert plist(a) == pos and w(pos + 4) == 0xFFFF
    assert w(0x06A7E4) == 0xFFFF and w(0x06A804) == 0xFFFF and w(0x06A80A) == 0xFFFF
    assert plist(0x06A82C) == 0x06A83A and plist(0x06A83A) == 0x06A86C
    assert plist(0x068C66) == 0x068C98 and plist(0x065676) == 0x065684
    assert rom[0x06A86C:0x06A876] == b"\xFF" * 10
    # radar scripts: (delay, frame) longs over the 12 frames, then zero
    frames = {0x0673CA + 512 * k for k in range(12)}
    for a, end in ((0x068BCA, 0x068C16), (0x068C16, 0x068C66)):
        while l(a):
            assert l(a) & 0xFFFFFF in frames
            a += 4
        assert a + 4 == end
    # music: 39 records, then the voice table
    assert all(w(0x06A8B8 + 4 * k) < 0x100 or w(0x06A8B8 + 4 * k) == 0xFFFF
               for k in range(39))
    assert {s8(b) for b in rom[0x06A954:0x06A954 + 0x5E]} <= {-1, 64, 65, 66}
    # icon animation scripts: 64 pointers into the scripts, each ends 0,FFFF
    for k in range(64):
        p = l(0x06A9B4 + 4 * k)
        assert 0x06AAB4 <= p < 0x06AE28
    a = 0x06AAB4
    while a < 0x06AE28:
        a += 4
        if w(a - 4) == 0 and w(a - 2) == 0xFFFF:
            continue
    assert w(0x06AE24) == 0 and w(0x06AE26) == 0xFFFF
    # structure scripts: opcodes only, and the building table points in
    assert all(w(a) >> 12 in (1, 3, 4, 6, 7)
               for a in range(0x06AE28, 0x06AFA6, 2))
    for k in range(19):
        for j in range(3):
            p = l(0x06AFA6 + 0x66 * k + 0x40 + 4 * j)
            assert p == 0 or 0x06AE28 <= p < 0x06AFA6
    assert [w(0x06BA6C + 2 * i) for i in range(4)] == [0xFFC0, 1, 0x40, 0xFFFF]
    assert rom[0x06BBBE:0x06BBC2] == bytes([1, 2, 4, 8])
    assert rom[0x06C6E4:0x06C6F8] == b"ENG\0FRE\0GER\0ITA\0SPA\0"
    for h in range(3):
        ramp = [w(0x06C70C + 20 * h + 2 * i) for i in range(1, 8)]
        assert ramp == [v << (4 * (0, 2, 1)[h]) for v in (14, 12, 10, 8, 6, 4, 2)]
    assert rom[0x06C81C:0x06C826] == bytes(10)
    # footprint offsets and half sizes
    for n in range(1, 33):
        assert l(0x06C806 + 32 * n) >> 16 == min(n, 31) * 16 or n == 32
    assert all(l(0x06CC26 + 4 * n) == (8 * (n + 1)) * 0x10001 for n in range(32))
    assert l(0x06CC26 + 4 * 32) == 0x01800180
    # the initials
    assert bytes(rom[l(0x06CE4E + 4 * i)] for i in range(6)) == b"FTHWWS"
    assert bytes(rom[l(0x06CE66 + 4 * i)] for i in range(5)) == b"NSFKG"
    assert [w(0x06CE7A + 2 * i) for i in range(8)] == [1, 1, 62, 62, 16, 16, 32, 32]
    # orders: 14 names, each a pointer to text
    assert rom[l(0x06CEF4):l(0x06CEF4) + 6] == b"Attack"
    assert rom[l(0x06CEF4 + 12 * 13):l(0x06CEF4 + 12 * 13) + 8] == b"Destruct"
    assert rom[0x06CF9C:0x06CFA2] == bytes(6) and rom[0x06CFA2] == 0
    # sine and cosine
    import math
    for i in range(256):
        assert abs(s8(rom[0x06CFA4 + i]) - 126 * math.sin(2 * math.pi * i / 256)) <= 1
        assert rom[0x06D0A4 + i] == rom[0x06CFA4 + (i + 64) % 256]
    # the icon tables: every pointer lands on a 384-byte frame of the run
    starts = {0x06D1A4 + 384 * k for k in range(15)} | \
             {0x06E888 + 384 * k for k in range(16)} | \
             {0x070808 + 384 * k for k in range(4)} | \
             {0x070D20 + 384 * k for k in range(5)} | \
             {0x06F908, 0x06FA88, 0x070688, 0x070208, 0x070388,
              0x070508, 0x070088, 0x06FF08, 0x06FC08, 0x06FD88}
    for k in range(25):
        assert l(0x06E824 + 4 * k) in starts
    for k in range(38):
        p = l(0x070C88 + 4 * k)
        assert p == 0 or p in starts
    # the small map tables
    sw = lambda a: w(a) - 0x10000 if w(a) & 0x8000 else w(a)
    assert [sw(0x0714B4 + 2 * i) for i in range(9)] == [-64, -63, 1, 65, 64, 63, -1, -65, 0]
    assert [sw(0x0714C6 + 2 * i) for i in range(8)] == [0, 256, 256, 256, 0, -256, -256, -256]
    assert [sw(0x0714D6 + 2 * i) for i in range(8)] == [-256, -256, 0, 256, 256, 256, 0, -256]
    assert [l(0x0714E6 + 4 * i) for i in range(3)] == [0x019D34, 0x019DB8, 0x019E0A]
    ring = [sw(0x0714F2 + 4 * k) + sw(0x0714F4 + 4 * k) for k in range(24)]
    assert len(set(ring)) == 24 and 0 not in ring
    assert [sw(0x071562 + 2 * i) for i in range(8)] == [-64, 1, 64, -1] * 2
    assert rom[0x071572:0x071574] == bytes(2)


def _check_bank0c(rom):
    w = lambda a: int.from_bytes(rom[a:a + 2], "big")      # noqa: E731
    l = lambda a: int.from_bytes(rom[a:a + 4], "big")      # noqa: E731
    # the screen table: 15 records of 16 bytes, read by $0C7D0E
    lists=set()
    for i in range(15):
        r=0x0C7C18+16*i
        assert rom[r+4] in (0,2,4)
        if l(r+4)&0xFFFFFF: lists.add(l(r+4)&0xFFFFFF)
    assert rom[0x0C7D08:0x0C7D0E]==b'\xff\xff\xff\xff\x00\x00'
    streams={}
    for L in lists:
        a=L
        while w(a):
            v=w(a); assert v&0x8000; p=l(a+2); a+=6
            out,used=lcw(rom[p:p+0x10000])
            assert len(out)==v&0x7FFF or (v&0x7FFF==0xE00 and len(out)==0x1000), (hex(p),len(out))
            assert rom[p+used-1]==0x80
            streams[p]=p+used
        assert a+2==min(streams[l(L+2)] if False else a+2, a+2)
    # each list is directly followed by its first stream
    for L in lists: assert l(L+2)==L+8 or (L==0x0C5DBA and l(L+2)==L+14) or (L==0x0C622A and l(L+2)==L+14)
    # pads after odd-length streams are single zero bytes
    for e in (0x0C64FF,0x0C6733,0x0C6E01,0x0C75A9,0x0C7A5F):
        assert rom[e]==0 and e in streams.values()
    assert streams[0x0C7A68]==0x0C7C18 and streams[0x0C356E]==0x0C3A9A
    # the four-frame animations: size words read at $0C7DFE / $0C7E34
    for tab,sz in ((0x0C4FF2,0x0C3D82),(0x0C5DAA,0x0C5002)):
        assert w(sz)==0x8E00
        for k in range(4):
            out,_=lcw(rom[l(tab+4*k):l(tab+4*k)+0x10000]); assert len(out)==4096
    # $0C7DDA: three RAM word pointers, then three (h,v) window register pairs
    assert [w(0x0C7DDA+2*k) for k in range(3)]==[0xE01E,0xE022,0xE024]
    assert [l(0x0C7DE0+4*k) for k in range(3)]==[0x0014001E,0,0]
    # layout bounds: width 1/2/3 -> $120/$100/$E0, height 1/2/3 -> $C0/$A0/$80
    lay=[(1,1),(2,1),(1,2),(2,2),(2,3),(3,2),(3,3)]
    for k,(cw,ch) in enumerate(lay):
        assert w(0x0C7EA0+4*k)==0x140-0x20*cw and w(0x0C7EA2+4*k)==0xE0-0x20*ch
    # eight neighbours on a 64-wide map, as (dx, dy*64) pairs
    nb=[(w(0x0C7EBC+4*k)-(w(0x0C7EBC+4*k)>>15<<16))+(w(0x0C7EBE+4*k)-(w(0x0C7EBE+4*k)>>15<<16)) for k in range(8)]
    assert nb==[-65,-64,-63,1,65,64,63,-1]
    # effect scripts: 24 pointers, (animation index, frames) pairs ended by (0,$FFFF)
    ps=[l(0x0C80A2+4*i) for i in range(24)]
    assert ps[0]==0x0C7F0E and all((p-0x0C7F0E)%4==0 for p in ps)
    end=0
    for p in ps:
        a=p
        while not (w(a)==0 and w(a+2)==0xFFFF):
            assert 0<w(a)<357 and 0<w(a+2)<0x8000; a+=4
        end=max(end,a+4)
    assert end==0x0C80A2 and rom[0x0C8102:0x0C8104]==b'\0\0'


def check(rom):
    _check_mine(rom)
    _check_bank06(rom)
    _check_bank0c(rom)
    s = sorted(BLOCKS)
    for a, b, _ in s:
        assert 0x060000 <= a < b <= 0x100000, hex(a)
    for x, y in zip(s, s[1:]):
        assert x[1] <= y[0], (hex(x[0]), hex(y[0]))
    return len(s), sum(b - a for a, b, _ in s)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rom", default=str(ROOT / "orig/dune2.gen"))
    args = ap.parse_args()
    n, size = check(Path(args.rom).read_bytes())
    print(f"{n} blocks, {size} bytes, every check holds")


if __name__ == "__main__":
    main()
