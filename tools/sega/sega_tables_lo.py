"""What the unnamed data and the stray code in banks 00 and 01 are.

Banks 00 and 01 ($000200-$01FFFF) hold every region the extractor could
only call "data the code at $X points at", "data the game was seen to
read" or "NOT confirmed as art", and every run of bytes nobody claimed.
This file says what each one is, with its exact extent:

    TABLES  (start, end_exclusive, description) - data, and who reads it
    CODE    (entry, why) - stretches that are really 68000 code the trace
            did not reach (or reached, but the listing kept as dc.b)
    CODE_ENDS  entry -> end_exclusive, where an extent is asserted

check(rom) asserts every mechanical property the descriptions rest on:
palette words are colours, counts match the loops that read them,
Format80 streams end where the next thing begins, pointers land where
they are said to, and every CODE stretch decodes and re-assembles.

    python3 tools/sega/sega_tables_lo.py       # run check() on orig/dune2.gen
"""
import math    # noqa: F401
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import m68k        # noqa: E402
import sega_gfx    # noqa: E402


# ======================================================================
# $000200-$009D7F
#
# Bank 00 below $00A000 - the parent agent's share.

TABLES_0000 = [
    (0x00028E, 0x0002FA, "the start-up table the reset code at $000200 walks with a5: three words for d5-d7 ($8000, $3FFF, $0100), five longwords for a0-a4 (Z80 RAM $A00000, Z80 bus request $A11100, Z80 reset $A11200, VDP data $C00000, VDP control $C00004), the 24 VDP register values (loop at $000238, dbf from $17), the VRAM-clear DMA command $40000080, the 38-byte Z80 stub copied to $A00000 (loop at $000250, dbf from $25), two more VDP words ($8104, $8F02), the CRAM and VSRAM write commands $C0000000 and $40000010, and the four PSG mute bytes $9F $BF $DF $FF - Sega's standard ICD_BLK4 start-up"),
    (0x00030C, 0x00038E, "a quarter sine wave, 65 words 256*sin(i*90/64 degrees) with the fraction dropped for i = 0..64, read by $000AC8 in the angle-and-radius-to-x,y routine at $000AB0 (index d0 & $3F and 64 minus it, so both 0 and 64 are read)"),
    (0x0008AC, 0x0008C0, "the DMA queue's dispatch table: five longwords indexed by the request type (high byte of the request's first word, x4 at $000874) and jumped through at $000876 - types 0-2 (VRAM, CRAM, VSRAM copy) go to $0008C0, type 3 (VRAM fill, $9780) to $00097E, type 4 (VRAM copy, $97C0) to $0009D4"),
    (0x000972, 0x00097E, "the VDP DMA write commands for the three memory-to-VDP request types, OR'd with the destination at $00093C: $40000080 VRAM, $C0000080 CRAM, $40000090 VSRAM"),
    (0x000A74, 0x000A82, "seven backdrop colours ($0E00 blue, $00E0 green, $000E red, $0EEE white, $0EE0 cyan, $0E0E magenta, $00EE yellow) for the unreached fatal-error stop at $000A3C: it writes entry d0 to CRAM 0 at $000A5E and executes illegal"),
    (0x004788, 0x004792, "five sprite palette-line words ($0000, $2000, $6000, $0000, $4000) OR'd into a sprite's attribute word by $00476E, indexed by its second argument x2 at $00477E"),
    (0x004B2E, 0x004B34, "three palette-line words ($0000, $2000, $6000) by the player's house (x2 at $004B6E), for sprite types $1C and $1E"),
    (0x004F38, 0x004F40, "four palette-line words ($0000, $2000, $6000, $4000) by the player's house, OR'd into the radar sprite by $004F66"),
    (0x0085E0, 0x0085EA, "five VRAM addresses ($0EE0-$0F60, tiles $77-$7B): $008612 picks one at random for each of six tiles at VRAM $7E00 and queues a VRAM-to-VRAM copy of $20 words (request $401) - a twinkle"),
    (0x0092B4, 0x0092B8, "four colour indices ($A, $B, $F, $B) that $009278 cycles through with (counter & $1F) >> 3 to paint the 12-tile mask at $049FBC, as $0085DC does on the other screen"),
    (0x001164, 0x001184, "eight (dx, dy) word pairs added to a sprite's screen position at $00115E/$001160 when bit 2 of its flags byte (+7) is set, picked by bits 0-2 of byte $72 of the object it follows: (0,0) (0,-1) (1,0) (0,-1) (1,0) (0,0) (1,0) (0,0) - a one-pixel shake"),
    (0x001792, 0x001796, "four $FF bytes: the empty sound resource - $000E1E-$000E30 and $02A8CE-$02A8E0 push this address four times and $001624 hands it to the Z80 driver as command $0B's four resource pointers, meaning nothing is installed (res/sound/music.txt)"),
    (0x0018CE, 0x0018D6, "the SEGA logo's asset list, read by $000CD8 from $00186C: one entry, count $8031 (bit 15 set: Format80, 49 tiles) at $001914, loaded to VRAM 0; then the zero terminator"),
    (0x0018D6, 0x001914, "the SEGA logo's shine: 31 colours, of which $0018AE copies eleven at a time from $0018D6 + d0 (d0 = 40, 38 .. 0) into shadow palette entries 2-12 at $FFE2B8 and $0018C2 sends them to CRAM - the gradient slides across the letters"),
    (0x001914, 0x001D2A, "the SEGA logo's 49 tiles, Format80 (stream ends at $001D2A, where the next block starts), named by the asset list at $0018CE"),
    (0x001D2A, 0x001DA3, "the SEGA logo's name table, Format80: $00187C hands it to $000D20, which unpacks it to $FFFF0000 and sends the 4096 bytes ($1000 in d0) to the plane at $FFE022; the stream ends at $001DA3"),
    (0x001DA3, 0x001DA4, "one zero byte that puts the palette after it on a word boundary"),
    (0x001DA4, 0x001E24, "the SEGA logo's 64 colours, loaded by $00188A through $000F56 into the shadow palette $FFE2B4"),
    (0x001EB0, 0x001ED6, "the title line of the unused exception screen: \"  DENZIL'S EXECEPTION ANALYSIS V1.1\", a newline, the zero terminator and one pad byte, printed by $001EA4 through $0027CA; nothing reaches $001E36 (all 62 exception vectors go to $000200)"),
    (0x001ED6, 0x002636, "the 8x8 font of the region-lock and exception screens: 59 tiles, characters $20-$5A (space to Z; $00267C subtracts $20 to get the tile), sent to VRAM 0 by $002806 with d1 = $3B0 words from $0028B4 and $001E8C - $0021A0-$0021B5 in the middle of it is font pixels, not code"),
    (0x002636, 0x00263E, "the four colours of the region-lock and exception screens ($0007 red - bit 0 is not a colour bit, the VDP drops it - $0EEE white, $0000, $0888 grey), written to CRAM 0 by $0027E2 with d2 = 4 from $0028AC and $001E82"),
    (0x0028D8, 0x002928, "the region-lock message: twelve newlines, \"       THIS CARTRIDGE IS FOR SALE\", two newlines, \"         AND USE IN EUROPE ONLY!\" and a zero, printed by $0028D2 when $00282A finds bit 6 of $A10001 clear (not a PAL machine)"),
    (0x0041D8, 0x0041DC, "four $FF fill bytes: the Z80 driver's upload at $00153E/$001544 runs from $00294E up to a1 = $0041D8, and the code resumes at $0041DC; nothing reads them"),
    (0x0045CC, 0x0045DE, "a 16-entry on/off pattern (0 or 1) returned by $0045C2 for a map square whose value (the square's byte in the table at *$04AA1C, >>1 & $7F) lies 0-15 below $FFC224, the full-fog overlay tile ($7B in battle) - so the pattern is over the 16 fog-edge tiles up to it, followed by two zero bytes nothing reads (the index cannot exceed 15); $0045DE, which follows, is reached through the pointer at $0268AC"),
    (0x0047BA, 0x0047CA, "four (x, y) offsets as packed longwords - (0,0) (0,16) (16,0) (16,16) - one of which $0047A6 adds to its argument, chosen by the random number $000C0C returns between 0 and 3: a random quarter of a 32-pixel square"),
    (0x004E66, 0x004E6E, "four sprite palette-line words ($0000, $2000, $6000, $4000) OR'd into a sprite's attribute word by $004E56 and $00518C, indexed by the player's house at $FFC274"),
    (0x004FAE, 0x004FBA, "three longwords of eight pixels in the player's house colour ($44444444 Harkonnen red, $77777777 Atreides blue, $66666666 Ordos green), indexed by $FFC274 x4 at $004FA0 and written eight times to fill the radar's top and bottom tile rows at $FFF3B0"),
    (0x00524E, 0x005256, "the radar colour of a unit or structure by its house (byte +8 of the record $00BAFE/$043656 return), read at $00521E and $005416: Harkonnen 4, Atreides 7, Ordos 6, Fremen 9, Sardaukar 13, Mercenary 0, then two zero entries"),
    (0x005256, 0x0053BE, "the radar colour of each of the 360 landscape tiles (the low nine bits of a map square's word, $005228), also looked up first by the square's top seven bits ($0051EA; a positive entry wins); $FF entries are left to the unit check.  Ends where the code at $0053BE begins"),
    (0x00543C, 0x005448, "the same three house-colour pixel longwords as $004FAE, read at $005454 by $005448 to fill the radar's first tile row"),
    (0x0054C0, 0x0054C8, "the radar border colour by the player's house, read at $00547E into d2 and written to the first and last byte of each radar row: 4, 7, 6 for the playable three, then 13, 7, 0, 0, 0"),
    (0x005818, 0x005980, "the landscape type of each of the 360 map tiles (0 sand .. 14, $FF none), read at $0057FA by the low nine bits of a map square's word and at $00580A by its top seven bits, which win only when they give $0D; ends where the code at $005980 begins.  $005960-$00597F inside it is not a separate block: $013102 loads #$5960 into a1 as a VRAM address for $000CD8"),
    (0x0064F2, 0x006516, "nine (width, height) word pairs in pixels - (16,16) (32,16) (48,16) (32,32) (0,0) (48,16) (0,0) (64,16) (48,48) - indexed by the first word of a sprite's frame record x4 at $00635A and $0063C2, and read directly at $006516/$00651A, to keep the sprite on screen"),
    (0x00690C, 0x006D0C, "eight frames of a 2x2-tile animation, 128 bytes each: $00608E steps $FFBF68 through 0-7 once every eight calls and DMAs frame n ($690C + n*128, 64 words) to VRAM $57C0"),
    (0x007218, 0x00721C, "two scroll-edge offsets, -32 and +320, picked by the sign of the horizontal scroll step at $007244: the column just off the left or right edge of the screen that the scroll brings in"),
    (0x007A74, 0x007A78, "two scroll-edge offsets, -32 and +224, picked by the sign of the vertical scroll step at $007AA6: the row just above or below the screen"),
    (0x007E52, 0x007E6E, "seven sprite frame-record pointers ($00883A x3, $008848, $008856 x2, $008864) that $007E48 stores into the sprite's frame at +8, indexed by the argument x4 - not eight: the next longword is the start of the table below"),
    (0x007E6E, 0x007E8E, "two 16-byte nibble-to-colour maps for $007E8E (a5 = $7E6E + argument x16): each 4-bit value in the words at $FFC768 is looked up at $007EE2 and doubled into a pixel pair of the tiles written to VRAM $8020"),
    (0x007FC8, 0x008008, "four frames of eight name-table words (tiles $1BE-$1DD, palette 2), one chosen by the frame counter & 3 and DMAd by $007F8C to the plane at $FFE01E + $9E at random intervals of 7-27 frames"),
    (0x008044, 0x008048, "two name-table words ($404D, $41DE) alternated by $008008 at the plane offset $1AC every 4-11 frames"),
    (0x008084, 0x008088, "two name-table words ($40A4, $41DF) alternated by $008048 at the plane offset $3C4 every 7-17 frames"),
    (0x00826A, 0x008276, "two longwords and two words indexed by $FFC614 (0 units, 1 structures): the lists of pixel blocks at $070C9C and $06E838 that $00829C reads into a4, then the palette-line words $6000 and $2000 read at $008296"),
    (0x0082FA, 0x008302, "the two sprite tables, indexed by $FFC614 x4 at $008352: $08F1C8 the 27 units, $08829C the 19 structures"),
    (0x00843E, 0x008462, "18 name-table offsets (six columns of three rows starting at $06A8), read by $008406 in the loop from d2 = $11, each the top-left of a two-tile cell"),
    (0x0085DC, 0x0085E0, "four colour indices ($B, $C, $F, $C) that $0085A4 cycles through with (counter & $1F) >> 3, painting every set pixel of the 12-tile mask at $049FBC before it is DMAd"),
    (0x008634, 0x008834, "16 tiles (512 bytes) of a pointer's four 2x2 frames, DMAd by $008146 to VRAM $5D80 (tiles $2EC-$2FB)"),
    (0x008834, 0x00883A, "the position record handed to $001000 as the pointer sprite's +0 at $00811C: x $00F0, y $0050, then $FD00"),
    (0x00883A, 0x008872, "four sprite frame records (a piece count less one, then one 12-byte piece: width 16, height 16, y 0, size $0500, attribute $22EC/$22F0/$22F4/$22F8, x 0) - the pointer's frames, named by the table at $007E52 and drawn by $001190-$0011A2"),
    (0x008946, 0x008996, "ten records of (position longword, frame pointer) that $008930/$00893E copy to $FFBFFE and the sprite's +8: x $0110 with y $27-$4F, frames $04A68E-$04A6EA; stepped 0-9 or 9-0 every animation tick by $0088D6"),
    (0x0089D2, 0x0089F2, "four frames of four name-table words, one picked by the frame counter & 3 and DMAd by $008996 to the plane offset $842 at random intervals of 7-27 frames"),
    (0x008A32, 0x008A92, "sixteen frames of three name-table words (6 bytes, mulu #6 at $008A14), picked by the frame counter & 15 and DMAd by $0089F2 to the plane offset $9A every 4-11 frames"),
    (0x008B08, 0x008DD4, "a 179-step flight path of (x, y) word pairs that $008AEE copies to $FFC00C/$FFC00A; $FFC014 counts 0-$B3 (cmpi #$B3 / ble at $008AAA) or from $B3 back down, the direction and the sprite's flip chosen at random at each end.  Index $B3 is one past the end: it reads the first instruction of $008DD4 (x $48E7, y $2038) - an off-by-one in the game"),
    (0x009148, 0x00916C, "18 name-table offsets, the same six-by-three grid as $00843E, read by $009110 in the loop from d2 = $11"),
    (0x0094EA, 0x0094EC, "two zero bytes between the rts at $0094E8 and the table below; nothing reads them"),
    (0x0094EC, 0x00950C, "the DMA length in words of a sprite of each VDP size code: 16 words ($10, $20, $30, $40, $20, $40, $60, $80, $30, $60, $90, $C0, $40, $80, $C0, $100 = 16 x width x height tiles), read at $00953A with the frame's size byte x2"),
    (0x009584, 0x009594, "eight palette-line words by house (x2 at $009566 and $0095F4): Harkonnen $0000, Atreides $2000, Ordos $6000, Fremen $2000, Sardaukar $4000, then three zeros"),
    (0x00960C, 0x00962C, "a second copy of the size-code-to-DMA-words table at $0094EC, read at $0095D2"),
    (0x009732, 0x00973E, "the first bar's three parameters for $00976E, read with (a2)+: its pixel buffer $FFC758, the DMA request longword $F4400040 (VRAM $F440, $40 words) passed at $009848, and the RAM word $FFC736 holding its sprite ($009724)"),
    (0x00973E, 0x00974E, "the bar's fill colour by quarter ($44444444 red, $22222222, $22222222, $66666666 green), read at $009716 with ((filled*32/full) & $18) >> 1"),
    (0x00974E, 0x00976E, "eight left-aligned pixel masks for a partly filled 8-pixel column ($00000000, $F0000000 .. $FFFFFFF0), ANDed at $0097C0-$0097FE through a6 = $974E + fraction x4"),
    (0x00979A, 0x0097BA, "eight single-pixel end markers in colour $C ($C0000000, $0C000000 .. $0000000C), ORed at $0097C2-$0097FA through a0 = $979A + fraction x4"),
    (0x0098D0, 0x0098DC, "the second bar's three parameters for $00976E: pixel buffer $FFC7D8, DMA request $F6400040 (VRAM $F640, $40 words), sprite word $FFC740 ($0098C2)"),
    (0x009AB6, 0x009AD6, "eight sprite frame-record pointers ($0657A4 six times, $0657B2 twice) indexed by the argument x4 at $009A7C and stored into the sprite's +8"),
]

CODE_0000 = [
    (0x00045C, "clears the longwords at $FFE3B6 and $FFE3BA; called by bsr at $000A42, and runs straight into the traced $000472"),
    (0x000578, "a lone rts after the routine ending at $000576; nothing calls it"),
    (0x00057A, "a shadow-palette fade: clears d1 entries from $FFE2B4 + 2*d0 and walks them up towards the colours at a0; runs into the traced $00059E, no caller found"),
    (0x000B8E, "reads a d1-sized block of a name table back from VRAM into $FFFF0000, writes it reversed with the vertical-flip bit toggled (eori #$800) to $FFFF1000 and sends it back through $0007F0; runs into the traced $000C00, no caller found"),
    (0x000A3C, "an unreached fatal-error stop: sets up the VDP, writes the colour picked from $000A74 by d0 to CRAM 0 and executes illegal; nothing calls it"),
    (0x000AF4, "the tail of the sweep-reached angle routine at $000AB0 (target of bne.s at $000AEC): exg, neg, movem, rts"),
    (0x001082, "bclr d0,$7(a0); rts - a sprite-flag helper nothing calls"),
    (0x0013CE, "bset d0,$7(a0); rts - a sprite-flag helper nothing calls"),
    (0x0013DC, "bclr #6,$7(a0); rts - the pair of the traced $0013D4, nothing calls it"),
    (0x0013EE, "move.l a1,$8(a0); rts - sets a sprite's frame; nothing calls it"),
    (0x001860, "two bare rts after the level-6 handler's rte at $00185E; nothing points at them"),
    (0x002700, "the entry of the unused printf: lea $267C(pc),a2 (the character writer) and bsr $00270A; no caller"),
    (0x002764, "the printf's %c arm (beq.w from $00273E): move.w (a1)+,d0, stop on zero, else write it"),
    (0x00279C, "move.l (a1)+,d0 / bra.w $00270E: unreachable (it follows the bra.w at $002798) - skips a longword argument"),
    (0x00438A, "C-callable wrapper: jmp $000CD8 (the asset-list loader) with a0 and a1 taken from the stack; no caller"),
    (0x0043E6, "C-callable wrapper: jmp $0013F4 with a0 from the stack and a1 = $F3A8; no caller"),
    (0x00458E, "a bare rts; nothing points at it"),
    (0x00465C, "moveq #0 / rts and moveq #1 / rts: branch targets of the traced $004644-$004656 that the trace never took"),
    (0x00476C, "a bare rts; nothing points at it"),
    (0x0047CA, "returns $F3B0 in a0 and d0; no caller"),
    (0x0047D8, "movea.l #'GETC',a1 / illegal - a debugging trap nothing reaches"),
    (0x0049C4, "C-callable wrapper: argument x64 and jmp $0007E0; no caller"),
    (0x004A62, "returns $FFFF0000 in a0 and d0; no caller"),
    (0x004AB2, "a bare rts after the traced $004AAE; nothing points at it"),
    (0x004C4A, "three moveq #0 / rts stubs and a bare rts; nothing points at them"),
    (0x004C84, "a bare rts; nothing points at it"),
    (0x004CB6, "two moveq #0 / rts stubs; nothing points at them"),
    (0x004DC0, "a bare rts; nothing points at it"),
    (0x004E22, "movea.w d0,a0 / jmp $0013E4: the arm of beq.w at $004E14 the trace never took"),
    (0x004EF2, "a routine entry after the rts at $004EF0 that runs into the traced $004F00; no caller found"),
    (0x004FF2, "a routine entry after the rts at $004FF0 (lea $FFBF12, btst #7 of the radar sprite's flags at $004FFE) - the listing's ori.b at $005000 is the tail of that btst, read from the wrong place; no caller found"),
    (0x0050F4, "a routine entry after the jmp at $0050F0 that runs into the traced $005100; no caller found"),
    (0x0067EA, "bclr #1,$FFBF0C.l, the fall-through of beq.w at $0067E6 - the listing's cmpm.b at $0067F0 is the last word of this instruction"),
    (0x006ECA, "the diagonal arms of the d-pad switch at $006E78: $006ECA, $006ED0, $006ED6, $006EDC each load the x and y steps from d6/d7 and join at $006EE0"),
    (0x009228, "the arm of bra.s at $009226 in the flight-path routine; runs into the traced $009230"),
    (0x009AFE, "move.b #3,$E(a3), the target of beq.s at $009AF4 - the listing's ori.b at $009B00 is the tail of this instruction"),
    (0x001682, "sound command sender: jsr $001596, moveq #$05 (set tempo, scaled), bra $00166A - one byte argument; never called"),
    (0x00168A, "sound command sender for $0C (silence everything): jsr $001596, jsr $0015DE, jmp $0015CC"),
    (0x001698, "sound command sender for $0D (stop the music)"),
    (0x0016B4, "sound command sender for $1C (voice flag 5 on), one argument via $00166A"),
    (0x0016BC, "sound command sender for $1D (voice flag 5 off), one argument via $00166A"),
    (0x0016E2, "sound command sender for $00 (play sound in slot), two arguments via $0016CA"),
    (0x0016EA, "sound command sender for $01 (load sound slot), two arguments via $0016CA"),
    (0x0016F2, "sound command sender for $14 (set voice byte 28), two arguments via $0016CA"),
    (0x00171E, "sound command sender for $06 (start a pitch envelope), two arguments via $0016CA"),
    (0x001726, "sound command sender for $07 (voice flag 6), two arguments via $0016CA"),
    (0x00172E, "sound command sender for $0E (voice flag 7), two arguments via $0016CA"),
    (0x00175C, "sound command sender for $1B (set a driver variable), two arguments via bra.w $0016CA"),
    (0x001766, "reads Z80 RAM $A01B22 + the byte argument with the bus held ($00150C/$001520) - a query of the driver's state; runs into the traced $001780"),
    (0x001788, "sound command sender for $1A (set slot byte 1), two arguments via bra.w $0016CA"),
    (0x001796, "rts, then rte at $001798, then move.w $C(a7),d0 / subq.w #2,d0 / stop #$2700 at $00179A - library leftovers nothing points at (every exception vector but level 6 goes to $000200)"),
    (0x0027B4, "the untaken arms of the unused printf at $00270A: '\\c' gives $0D, and $0027C4 is its exit (movem, rts) taken at the terminating zero"),
    (0x004AC0, "three unreferenced helpers: $004AC0 byte-swaps its word argument, $004AC8 is a bare rts, $004ACA swaps the halves of its longword argument"),
    (0x0061FC, "arm 3 of the 16-way d-pad switch at $0061F0 (jmp at $0061EC, index & $F x4): bra.w $0064D2, the do-nothing arm, also taken for 7 and 11-15 - combinations of opposite directions that a pad cannot give"),
    (0x00620C, "arm 7 of the d-pad switch at $0061F0: bra.w $0064D2"),
    (0x00621C, "arms 11-15 of the d-pad switch at $0061F0 ($00621C-$00622F): five bra.w $0064D2"),
    (0x006E8C, "arm 5 of the second d-pad switch: bra.w $006ECA"),
    (0x006E90, "arm 6 of the second d-pad switch: bra.w $006ED0"),
    (0x006E94, "arm 7 of the second d-pad switch: bra.w $007066"),
    (0x006E9C, "arms 9-15 of the second d-pad switch ($006E9C-$006EB7): $006ED6, $006EDC, then five bra.w $007066"),
    (0x006E84, "arms 3, 5, 6, 7 and 9-15 of the second d-pad switch at $006E78 (jmp at $006E74): the diagonals go to $006ECA/$006ED0/$006ED6/$006EDC, the impossible combinations to $007066"),
    (0x006ED0, "diagonal arm of the second d-pad switch (from $006E90): move.l d7,d2 / move.l d6,d3 / bra.s $006EE0"),
    (0x006ED6, "diagonal arm of the second d-pad switch (from $006E9C): move.l d7,d3, runs into $006ED8"),
    (0x006EDC, "diagonal arm of the second d-pad switch (from $006EA0): move.l d6,d2, runs into $006EDE"),
    (0x00721C, "the horizontal-scroll column update: called by bsr at $007A46 and $007A54 (sweep-reached), decodes cleanly to $0073A7 and runs into the traced $0073A8"),
    (0x007A78, "the vertical-scroll row update: called by bsr.s at $007A3E and $007A5E, runs into the sweep-reached $007A8A"),
]


def _check_0000(rom):
    w = lambda a: int.from_bytes(rom[a:a + 2], "big")
    l = lambda a: int.from_bytes(rom[a:a + 4], "big")

    def colours(a, n):
        for i in range(n):
            assert w(a + 2 * i) & 0xF111 == 0, hex(a + 2 * i)

    def ins(a):
        i = m68k.decode(rom, a, 0)
        assert m68k.roundtrips(i), hex(a)
        return i

    def text(a):
        return m68k.text(ins(a))

    # the start-up table
    assert text(0x000210) == "lea.l $28E(pc),a5"
    assert [w(0x28E + 2 * i) for i in range(3)] == [0x8000, 0x3FFF, 0x0100]
    assert [l(0x294 + 4 * i) for i in range(5)] == [0xA00000, 0xA11100, 0xA11200, 0xC00000, 0xC00004]
    assert all(0x80 <= 0x80 + i for i in range(24))
    assert l(0x2C0) == 0x40000080 and rom[0x2C4] == 0xAF      # xor a
    assert l(0x2EA) == 0x81048F02 and l(0x2EE) == 0xC0000000 and l(0x2F2) == 0x40000010
    assert rom[0x2F6:0x2FA] == b"\x9F\xBF\xDF\xFF"
    # sine
    import math
    assert [w(0x30C + 2 * i) for i in range(65)] == [int(256 * math.sin(i * math.pi / 128) + 1e-9) for i in range(65)]
    assert text(0x000AC8) == "lea.l $30C(pc),a0"
    # DMA queue
    assert [l(0x8AC + 4 * i) for i in range(5)] == [0x8C0, 0x8C0, 0x8C0, 0x97E, 0x9D4]
    assert [l(0x972 + 4 * i) for i in range(3)] == [0x40000080, 0xC0000080, 0x40000090]
    # sound
    assert [w(0xA74 + 2 * i) for i in range(7)] == [0xE00, 0xE0, 0xE, 0xEEE, 0xEE0, 0xE0E, 0xEE]
    assert text(0x000A5E) == "move.w $A74(pc,d2.w),d0" and text(0x000A72) == "illegal"
    assert text(0x00477E) == "move.w $4788(pc,d0.w),d0" and text(0x004B6E) == "move.w $4B2E(pc,d1.w),d1"
    assert text(0x004F66) == "move.w $4F38(pc,d0.w),d0" and text(0x008612) == "movea.w $85E0(pc,d0.w),a0"
    assert [w(0x85E0 + 2 * i) for i in range(5)] == [0xEE0, 0xF00, 0xF20, 0xF40, 0xF60]
    assert text(0x009278) == "move.b $92B4(pc,d0.w),d0"
    for a, want in ((0x4FFE, "btst.b #$7,$7(a1)"), (0x67EA, "bclr.b #$1,$FFBF0C.l"), (0x9AFE, "move.b #$3,$E(a3)")):
        assert text(a) == want, text(a)
    assert text(0x001544) == "lea.l $41D8.l,a1" and rom[0x41D8:0x41DC] == b"\xFF" * 4
    assert rom[0x94EA:0x94EC] == b"\0\0"
    assert rom[0x1792:0x1796] == b"\xFF" * 4
    for a, cmd in ((0x1682, 5), (0x168A, 0xC), (0x1698, 0xD), (0x16B4, 0x1C), (0x16BC, 0x1D),
                   (0x16E2, 0), (0x16EA, 1), (0x16F2, 0x14), (0x171E, 6), (0x1726, 7),
                   (0x172E, 0xE), (0x175C, 0x1B), (0x1788, 0x1A)):
        assert text(a) == "jsr $1596(pc)", hex(a)
        assert text(a + 4) == "moveq.l #$%X,d0" % cmd, (hex(a), text(a + 4))
    # SEGA logo
    assert w(0x18CE) == 0x8031 and l(0x18D0) == 0x1914 and w(0x18D4) == 0
    t, used = sega_gfx.lcw(rom[0x1914:0x1914 + 0x4000])
    assert len(t) == 49 * 32 and 0x1914 + used == 0x1D2A
    t, used = sega_gfx.lcw(rom[0x1D2A:0x1D2A + 0x4000])
    assert len(t) == 0x1000 and 0x1D2A + used == 0x1DA3 and rom[0x1DA3] == 0
    colours(0x18D6, 31)
    colours(0x1DA4, 64)
    assert [w(0x2636 + 2 * i) for i in range(4)] == [0x0007, 0x0EEE, 0x0000, 0x0888]
    # font and region lock
    assert rom[0x1EB0:0x1ED3] == b"  DENZIL'S EXECEPTION ANALYSIS V1.1"
    assert text(0x0028BC) == "move.w #$3B0,d1" and 0x1ED6 + 0x3B0 * 2 == 0x2636
    assert rom[0x2927] == 0 and b"EUROPE ONLY!" in rom[0x28D8:0x2928]
    # radar
    assert rom[0x4FAE:0x4FBA] == rom[0x543C:0x5448] == bytes.fromhex("444444447777777766666666")
    assert rom[0x524E:0x5256] == bytes([4, 7, 6, 9, 13, 0, 0, 0])
    assert ins(0x53BE).mnem.startswith("movem") and ins(0x5980).mnem.startswith("move")
    assert text(0x0057FA) == "move.b $5818(pc,d0.w),d0"
    assert text(0x013102) == "movea.l #$5960,a1" and text(0x013108) == "jsr $CD8.w"
    # sprite sizes / DMA lengths
    size = [16 * (s // 4 + 1) * (s % 4 + 1) for s in range(16)]
    assert [w(0x94EC + 2 * i) for i in range(16)] == size == [w(0x960C + 2 * i) for i in range(16)]
    # tables of pointers
    assert [l(0x7E52 + 4 * i) for i in range(7)] == [0x883A] * 3 + [0x8848, 0x8856, 0x8856, 0x8864]
    for a in (0x883A, 0x8848, 0x8856, 0x8864):
        assert w(a) == 0 and w(a + 2) == 16 and w(a + 4) == 16
    assert [l(0x82FA), l(0x82FE)] == [0x08F1C8, 0x08829C]
    assert [l(0x826A), l(0x826E), w(0x8272), w(0x8274)] == [0x070C9C, 0x06E838, 0x6000, 0x2000]
    assert text(0x008AAA) == "cmpi.w #$B3,$FFC014.l" and 0x8B08 + 4 * 0xB3 == 0x8DD4
    assert ins(0x8DD4).mnem.startswith("movem")
    assert [l(0x9AB6 + 4 * i) for i in range(8)] == [0x657A4] * 6 + [0x657B2] * 2
    # d-pad switches: every arm a bra.w
    for T in (0x61F0, 0x6E78):
        for i in range(16):
            assert ins(T + 4 * i).mnem == "bra.w"
    for a in (0x45C, 0x57A, 0xB8E, 0x721C, 0x7A78, 0x4AC0, 0x4ACA, 0x27B4, 0x1766):
        ins(a)
    return True

CODE_ENDS_0000 = {}


# ======================================================================
# $009D80-$00FFFF
#
# Tables and stray code in $009D80-$00FFFF (fork's part of sega_tables_lo).
#
# $009D80-$00A3F7 starts below $00A000; it is here because the pictures it
# describes run across the boundary and have to be read together.

TABLES_A000 = [
    (0x009D80, 0x009D98,
     "the Victory/Defeat banner table: two 12-byte records (pixels, sprite "
     "frame, 16 colours), picked by $009D06's argument times 12 - 0 Defeat "
     "(called from $0129F4), 1 Victory (from $01290C)"),
    (0x009D98, 0x009DB2,
     "the Defeat banner's sprite frame: piece count-1 = 1, then two 12-byte "
     "pieces (4x3 tiles at $580, 3x3 at $58C, 32 pixels apart); put up "
     "through $001000 by $009D06"),
    (0x009DB2, 0x009DD8,
     "the Victory banner's sprite frame: piece count-1 = 2, then three "
     "12-byte 3x3-tile pieces at tiles $580/$589/$592, 24 pixels apart; put "
     "up through $001000 by $009D06"),
    (0x009DD8, 0x00A078,
     "the word 'Defeat' in 21 tiles (4x3 + 3x3, column-major), DMA'd by "
     "$009D2A to VRAM $B000 (tile $580) - the DMA moves 28 tiles, so it also "
     "carries the first 7 of the Victory tiles after it, which nothing shows"),
    (0x00A078, 0x00A3D8,
     "the word 'Victory!' in 27 tiles (three 3x3 blocks, column-major), "
     "DMA'd by $009D2A to VRAM $B000 (28 tiles moved; the 28th is the "
     "palette below)"),
    (0x00A3D8, 0x00A3F8,
     "the Victory/Defeat banner's 16 colours (black, golds, whites), DMA'd "
     "by $009D60 to CRAM line 3; the shadow copy $009D64 makes reads 32 "
     "bytes from $60 further on ($00A438, code) - a slip in the original"),
    (0x00A488, 0x00A5AC,
     "the battle screen's tile load list, walked by $00A41E: 36 records of "
     "(VRAM address.w, length in words.w, source.l) ended by a zero "
     "longword; a source with bit 31 set is DMA'd as it stands (8 of them), "
     "any other is a Format80 block unpacked to $FF0000/$FF0800 first "
     "(28, each unpacking to exactly twice the length)"),
    (0x00AF76, 0x00AFBE,
     "three frames of a three-block tile animation: each frame is three "
     "(source.l, VRAM<<16 | $90 words) pairs - 9 tiles each to VRAM "
     "$96C0/$97E0/$9900 - DMA'd by $00AFCA every ten ticks"),
    (0x00AFBE, 0x00AFCA,
     "pointers to the three frames above, indexed by the countdown at "
     "$FFD304 (2, 1, 0) in $00AFF6"),
    (0x00B01C, 0x00B028,
     "three pointers to 6-tile frames at $066B72/$066C32/$066CF2, one DMA'd "
     "every ten ticks to VRAM $DF20 by $00B028 (countdown at $FFD300)"),
    (0x00B09C, 0x00B0A4,
     "squares-1 of each of the seven building layouts (1x1, 2x1, 1x2, 2x2, "
     "2x3, 3x2, 3x3 -> 0,1,1,3,5,5,8), the dbf count $00B0E2 walks the "
     "18-byte offset lists at $06B738 with; then one zero pad byte before "
     "the code at $00B0A4"),
    (0x00B142, 0x00B1C2,
     "128 flags, one per overlay value 0-127 (word +6 of a 16-byte record "
     "from the pool at $FFC8C8), read by $00B0C2: set (46-53, 55-59, 72-74) "
     "means the value is stamped into every square of the record's layout, "
     "clear means it goes into the square's top seven bits only"),
    (0x00B3B0, 0x00B3D0,
     "one flag per unit type (27, indexed by byte +2 of the unit), read by "
     "$00B39E: set for Soldier, Trooper, Trike, Raider Trike and Quad, and "
     "it sets bit 2 of the sprite's +7 - the jitter the table at $001164 "
     "supplies; the last five bytes are zero and past type 26"),
    (0x00B3D0, 0x00B3E0,
     "eight words (16,16,48,48,80,48,80,0), one a structure layout: how far "
     "down its bottom row's centre is, 32 to a row - 16, 48, 80 for one, "
     "two and three rows (layout 1 is 2x1, 2 is 1x2, 4 is 2x3, 5 is 3x2, 6 "
     "is 3x3).  $00DC1C passes the building table's +$3C as $00B3E0's "
     "second argument and $00B476 adds this to the coordinates"),
    (0x00B52C, 0x00B540,
     "palette-line bits doubled into a longword (two name-table cells) for "
     "houses 0-4 - Harkonnen 0, Atreides line 1, Ordos line 3, Fremen line "
     "1, Sardaukar line 2 - ORed by $00B4F8 into the 2x2 marker at tiles "
     "$2BE-$2C1"),
    (0x00B5B8, 0x00B5C8,
     "four sprite-frame pointers ($00B5F8.. one per direction) for the "
     "seven-aircraft fly-over started by $00B572 (from $026A22), picked by "
     "a random 0-3"),
    (0x00B5C8, 0x00B5D8,
     "the fly-over's velocity per direction, (dx.w, dy.w): (0,3), (-3,0), "
     "(0,-3), (3,0) - copied to $FFD30C by $00B57C"),
    (0x00B5D8, 0x00B5E8,
     "the fly-over's start position per direction, (x.w, y.w) just off an "
     "edge - copied to $FFD306 by $00B584"),
    (0x00B5E8, 0x00B5F8,
     "the fly-over's palette bits per house (8 words: 0, $2000, $6000, "
     "$2000, $4000, then zeros), indexed by $00B572's argument in $00B5AA"),
    (0x00B5F8, 0x00B750,
     "the fly-over's four sprite frames, 86 bytes each: piece count-1 = 6, "
     "then seven 12-byte 4x4-tile pieces 32 pixels apart in a line - tile "
     "$7D0 (nose up) or $7F0 (nose right), flipped per direction; drawn by "
     "$001190"),
    (0x00BB5C, 0x00BCD7,
     "the 19 buildings' names and Westwood .wsa file names, 38 NUL-ended "
     "strings pointed at by +2 and +8 of each $66-byte record of the "
     "building table at $06AFA6 (names printed through $049A4A)"),
    (0x00BCD7, 0x00BCD8,
     "one zero pad byte to put the code at $00BCD8 on an even address"),
    (0x00A6F4, 0x00A704,
     "four pointers to 16-tile pixel blocks at $06341E/$06361E/$06381E/"
     "$063A1E (in that order: $61E, $81E, $A1E, $41E), one DMA'd by "
     "$00A6AE to VRAM $7FC0 per the argument & 3"),
    (0x00A73E, 0x00A74E,
     "four sprite-frame pointers ($0696B8, $0696C6, $0696D4, $0696B8) "
     "stored into an object's +8 by $00A704 per the argument & 3"),
]

CODE_A000 = [
    (0x00A662, "unreferenced: sets frame $06A7CC on the object at $FFC740, "
               "clears bit 3 of its +7 and jumps to $0013B0 - no caller or "
               "pointer anywhere; decodes cleanly, ends in jmp"),
    (0x00B840, "unreferenced: clears $FFD4B4.l and $FFD318.w (the state of "
               "the routine before it) and returns - no caller or pointer"),
]

BUILDING_TABLE, BUILDING_REC = 0x06AFA6, 0x66


def w(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def l(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


def frame(rom, a):
    """A sprite frame: count-1 word then 12-byte pieces; return its end."""
    return a + 2 + 12 * (w(rom, a) + 1)


def _check_A000(rom):
    # banner table
    assert [l(rom, 0x9D80 + 4 * i) for i in range(6)] == [
        0x9DD8, 0x9D98, 0xA3D8, 0xA078, 0x9DB2, 0xA3D8]
    assert frame(rom, 0x9D98) == 0x9DB2 and frame(rom, 0x9DB2) == 0x9DD8
    assert (0xA078 - 0x9DD8) // 32 == 21 and (0xA3D8 - 0xA078) // 32 == 27
    assert l(rom, 0x9D24) == 0x223CB000 and w(rom, 0x9D28) == 0x01C0
    assert all(w(rom, 0xA3D8 + 2 * i) & 0xF111 == 0 for i in range(16))
    # load list
    a, n = 0xA488, 0
    while l(rom, a):
        cnt, src = w(rom, a + 2), l(rom, a + 4)
        if not src & 0x80000000:
            out, _ = sega_gfx.lcw(rom[src:src + 0x10000])
            assert len(out) == 2 * cnt, hex(a)
        a, n = a + 8, n + 1
    assert n == 36 and a == 0xA5A8
    # animation frames
    assert [l(rom, 0xAFBE + 4 * i) for i in range(3)] == [0xAF76, 0xAF8E,
                                                         0xAFA6]
    for f in range(9):
        assert l(rom, 0xAF76 + 8 * f + 4) & 0xFFFF == 0x90
    assert [l(rom, 0xB01C + 4 * i) for i in range(3)] == [0x66B72, 0x66C32,
                                                         0x66CF2]
    assert l(rom, 0xB05A) == 0xDF200060
    # layouts: squares-1 against the 18-byte offset lists' capacity
    assert list(rom[0xB09C:0xB0A4]) == [0, 1, 1, 3, 5, 5, 8, 0]
    assert set(rom[0xB142:0xB1C2]) == {0, 1} and rom[0xB1C2:0xB1C4] == \
        b"\x61\x00"
    assert set(rom[0xB3B0:0xB3D0]) == {0, 1} and not any(rom[0xB3CB:0xB3D0])
    assert [w(rom, 0xB3D0 + 2 * i) for i in range(8)] == [
        16, 16, 48, 48, 80, 48, 80, 0]
    assert [l(rom, 0xB52C + 4 * i) for i in range(5)] == [
        0, 0x20002000, 0x60006000, 0x20002000, 0x40004000]
    # fly-over
    frames = [l(rom, 0xB5B8 + 4 * i) for i in range(4)]
    assert frames == [0xB5F8, 0xB64E, 0xB6A4, 0xB6FA]
    for f in frames:
        assert w(rom, f) == 6 and frame(rom, f) in frames + [0xB750]
    # building names
    strings, a = [], 0xBB5C
    while a < 0xBCD7:
        e = rom.index(b"\0", a)
        strings.append(a)
        a = e + 1
    assert a == 0xBCD7 and len(strings) == 38 and rom[0xBCD7] == 0
    for i in range(19):
        r = BUILDING_TABLE + i * BUILDING_REC
        assert l(rom, r + 2) == strings[2 * i]
        assert l(rom, r + 8) == strings[2 * i + 1]
        assert rom[strings[2 * i + 1]:].split(b"\0")[0].endswith(b".wsa")
    assert [l(rom, 0xA6F4 + 4 * i) for i in range(4)] == [
        0x6361E, 0x6381E, 0x63A1E, 0x6341E]
    assert [l(rom, 0xA73E + 4 * i) for i in range(4)] == [
        0x696B8, 0x696C6, 0x696D4, 0x696B8]
    # stray code: decodes, round-trips, ends in a flow stop
    for entry, end in ((0xA662, 0xA67A), (0xB840, 0xB850)):
        a = entry
        while a < end:
            ins = m68k.decode(rom, a, 0)
            assert m68k.roundtrips(ins), hex(a)
            a += ins.length
        assert a == end and ins.mnem in ("jmp", "rts")
    # nothing in the cartridge points at them
    for entry, _ in CODE_A000:
        assert entry.to_bytes(4, "big") not in rom

CODE_ENDS_A000 = {}


# ======================================================================
# $010000-$01FFFF
#
# Bank 01 ($010000-$01FFFF): what the unnamed regions and the gaps are.
#
# A fragment for tools/sega/sega_tables_lo.py: TABLES, CODE and
# check_part(rom).  Every mechanical property the descriptions rest on is
# asserted in check_part().

# The Format80 blocks bank 01 already names, as (first byte, the byte
# after the named extent).  The named extents stop one byte short: the
# $80 that ends each stream is left out, and $000C3E reads it.
F80_BLOCKS = [
    (0x013898, 0x013EAF), (0x013EB0, 0x0144C5), (0x0144C6, 0x014BB2),
    (0x014BB4, 0x015236), (0x015238, 0x015961), (0x015962, 0x016077),
    (0x017F3E, 0x01871E), (0x018720, 0x018EF6), (0x018EF8, 0x019047),
]
F80_PADS = [0x014BB3, 0x015237, 0x01871F, 0x018EF7]

UNIT_TABLE, UNIT_STRIDE, UNITS = 0x06BC00, 0x5C, 27
HOUSE_TABLE, HOUSE_STRIDE, HOUSES = 0x06C752, 0x1E, 6
ORDER_NAMES, ORDER_STRIDE, ORDERS = 0x06CEF4, 12, 14
MOVE_LETTERS, TEAM_LETTERS = 0x06CE4E, 0x06CE66

TABLES_10000 = [
    (0x010E54, 0x011014, "the 27 unit types' names and .wsa picture names, "
     "NUL-terminated in pairs (Carryall/carryall.wsa ... Frigate), plus one "
     "zero pad byte - pointed at by +$02 and +$08 of each $5C-byte unit "
     "record at $06BC00 (the last eight, Rocket to Frigate, have a name only)"),
    (0x0115A2, 0x0115C2, "16 direction words read by $011596: the index is "
     "four bits built by $01154E - dy<0 (8), dx<0 (4), |dy|>2|dx| (2), "
     "|dx|>2|dy| (1) - and the word is the heading in 256ths of a turn "
     "($00,$20,...,$E0), $FFFF where bits 1 and 0 would both be set"),
    (0x01192C, 0x011E76, "the closing credits, one text: \"The End\" and "
     "then the credits proper, lines ended by $0A, $FF n selecting the "
     "colour (n = 2 heading, 3 name), ended by a NUL at $011E75 - "
     "$0117B4 scrolls it from $01192C and, when it reaches the NUL, starts "
     "again at $01193A, i.e. without \"The End\""),
    (0x011E76, 0x011E78, "two zero bytes after the credits, padding "
     "before the routine at $011E78"),
    (0x011F2C, 0x011F34, "two \"%6d\" format strings for the sprintf at "
     "$0491C2: $011F2C is pushed by $011FD6, $011F30 by $0120F8 (the "
     "credits counter)"),
    (0x0126C6, 0x0126C8, "the string \".\", appended by $0126F2 (strcat "
     "at $049ACC) to a file name copied to $FFD6D8"),
    (0x012A9C, 0x012AAC, "8 words: the map-square step for each of the "
     "eight directions on the 64-square-wide map (-64, -63, +1, +65, +64, "
     "+63, -1, -65 = N, NE, E, SE, S, SW, W, NW) - $012A8C adds entry "
     "arg2 to square arg1"),
    (0x013004, 0x013038, "the six house names (Harkonnen, Atreides, Ordos, "
     "Fremen, Sardaukar, Mercenary), NUL-terminated - pointed at by +$00 "
     "of each $1E-byte house record at $06C752; $0160D6 reads the first "
     "letter for the SCEN%c%03d.INI name"),
    (0x013038, 0x013044, "the six movement types as one-letter strings "
     "(F T H W W S: foot, tracked, harvester, wheeled, winged, slither), "
     "pointed at by the 6 longwords at $06CE4E - $01668E compares a team "
     "line's letter against each"),
    (0x013044, 0x01304E, "the five team actions as one-letter strings "
     "(N S F K G: normal, staging, flee, kamikaze, guard), pointed at by "
     "the 5 longwords at $06CE66 - $01666C compares against each"),
    (0x01304E, 0x0130B0, "the fourteen order names (Attack ... Destruct), "
     "NUL-terminated, pointed at by the longword four bytes before each "
     "12-byte order record at $06CEF8"),
    (0x013216, 0x013246, "6 pairs of longwords (zero, sprite frame) read "
     "by $01318A as +4 of entry n*8: the frames $01314A shows for the "
     "object at $FFD70C"),
    (0x013246, 0x0137F2, "6 sprite frames of 20 pieces, 242 bytes each: a "
     "count word (pieces-1) then 12-byte pieces - width, height (a box to clip by), y, the "
     "VDP's size and link bytes, its attribute word, x - drawn by $001190"),
    (0x0137F2, 0x013872, "64 colours (four palette lines) that no code was "
     "found to load and the trace never read; the same 128 bytes are at "
     "$0307F4, $0331AC, $036DEA, $03C980 and $03F4E6"),
    (0x016088, 0x016098, "\"SCEN%c%03d.INI\", pushed by $0160DE, and a "
     "zero pad byte"),
    (0x016B86, 0x016BA4, "the names \"UNIT\", \"TEAM\", \"BUILD\" (pushed "
     "by $016C1A/$016C38/$016C56 when the three scripts are loaded), "
     "\"DUNE\" and \"MESSAGE\" (passed to $0126C8 by $016C9C/$016CB6), "
     "and a zero pad byte"),
    (0x016D28, 0x016D30, "\"%s.EMC\", pushed by $016D38, and a zero pad "
     "byte"),
    (0x0173F0, 0x017414, "the title menu's words \"PRESENT\", \"START "
     "GAME\", \"OPTIONS\", \"TUTORIAL\", pushed by $01755E/$017812/"
     "$01782A/$017842 and printed by $01FF62"),
    (0x017B5A, 0x017B68, "a one-piece sprite frame (8 x 8, attribute "
     "$44BE) - the title menu's pointer, created by $017A34 through "
     "$001000"),
    (0x019048, 0x0190C0, "15 pairs of longwords (zero, sprite frame) in "
     "the shape of $013216, naming the same 15 frames as $019582 in the "
     "same order; no code was found to read it and the trace never did"),
    (0x0190C0, 0x019576, "45 sprite frames for the three tutorial "
     "pointer demonstrations (15 each), a count word (pieces-1) then "
     "12-byte pieces - width, height (a box to clip by), y, size/link, attribute, x - drawn "
     "by $001190"),
    (0x019576, 0x019582, "3 pointers to the demonstrations' frame lists, "
     "indexed by the argument of $017DC4 (and by $017EE8)"),
    (0x019582, 0x019636, "3 lists of 15 sprite-frame pointers, one per "
     "demonstration: $017DF6 shows entry 0, $017F02 each later one"),
    (0x019636, 0x019642, "3 pointers to the demonstrations' scripts, "
     "indexed by the argument of $017DC4"),
    (0x019642, 0x0198B8, "3 scripts of words read by $017E12, one per "
     "demonstration: 1 x y moves the pointer and waits for a button, 2 "
     "steps to the next frame, 0 ends"),
    (0x0198B8, 0x019938, "32 longwords: 256 * cot(i * 360/256 degrees) "
     "for i = 1-31, $3FFF for i = 0 - the arctangent search at $0199A0 "
     "inside atan2 at $019940"),
    (0x019938, 0x019940, "4 words, atan2's quadrant base angles ($40, "
     "$80, $00, $C0), read by $01996A by the signs of dx (bit 0) and dy "
     "(bit 1)"),
    (0x0199D4, 0x0199D8, "4 bytes, one per quadrant, read by $0199B8: "
     "nonzero adds the angle within the quadrant to the base, zero "
     "subtracts it from base+$40"),
]
TABLES_10000 += [(end, end + 1, "the $80 that ends the Format80 stream "
            "beginning at $%06X - read by $000C3E, and left out of that "
            "block's named extent" % start) for start, end in F80_BLOCKS]
TABLES_10000 += [(p, p + 1, "a zero pad byte after a Format80 stream, so the "
            "next one starts even") for p in F80_PADS]
TABLES_10000.sort()

CODE_10000 = [
    (0x0130B0, "order-by-name lookup: compares a string with each of "
     "the 14 order names through $029A34 and returns the index or -1; "
     "no caller found (ends rts at $0130EE)"),
    (0x016B4A, "tail of the routine at $016A6C, reached by the bra.w at "
     "$016A8E; flows into the traced $016B6E"),
    (0x017AD6, "the menu pointer's 'down' step: bge.w/addq/bra and the "
     "wrap at $017AE2 - the trace ran $017AD6-$017ADF, left as dc.b by "
     "the extractor"),
    (0x01FD88, "reached by the bne.s at $01FD80 (returns $4242 if "
     "$FFD716 is $A8)"),
    (0x01FF5C, "movem.l/rts epilogue labelled by a branch; left as dc.b"),
    (0x01FFE8, "no caller found: queues d7+1 rows of $80 bytes through "
     "$00038E (d0=$0301) into the name table at $FFE01E; runs on past "
     "the bank into $020000-$020022"),
]

# instruction extents of the CODE_10000 entries, to check they decode
CODE_ENDS_10000 = {0x0130B0: 0x0130F0, 0x016B4A: 0x016B6E, 0x017AD6: 0x017AE8,
             0x01FD88: 0x01FD98, 0x01FF5C: 0x01FF62, 0x01FFE8: 0x020024}


def _w(rom, a):
    return int.from_bytes(rom[a:a + 2], "big")


def _l(rom, a):
    return int.from_bytes(rom[a:a + 4], "big")


def _s16(v):
    return v - 0x10000 if v & 0x8000 else v


def _cstr(rom, a):
    return rom[a:rom.index(b"\0", a)]


def _pea_pc(rom, at, target):
    """`pea d16(pc)` at `at` names `target`."""
    assert _w(rom, at) == 0x487A, hex(at)
    assert at + 2 + _s16(_w(rom, at + 2)) == target, hex(at)


def _frames(rom, start, end):
    """A run of sprite frames: count word, then count+1 12-byte pieces."""
    a, out = start, []
    while a < end:
        out.append(a)
        a += 2 + (_w(rom, a) + 1) * 12
    assert a == end, (hex(start), hex(a))
    return out


def _check_10000(rom):
    import math

    # Format80 terminators and pads
    for start, end in F80_BLOCKS:
        _, used = sega_gfx.lcw(rom[start:start + 0x10000])
        assert start + used == end + 1 and rom[end] == 0x80, hex(start)
    for p in F80_PADS:
        assert rom[p] == 0
    # unit names
    at = 0x010E54
    for i in range(UNITS):
        rec = UNIT_TABLE + i * UNIT_STRIDE
        for off in (2, 8):
            if off == 8 and _l(rom, rec + 8) == 0:
                continue
            if _l(rom, rec + off) != at:
                assert off == 8, (i, off)
                continue
            at += len(_cstr(rom, at)) + 1
    assert at == 0x011013 and rom[0x011013] == 0
    # direction words
    d = [_w(rom, 0x0115A2 + 2 * i) for i in range(16)]
    assert all((v == 0xFFFF) == (i & 3 == 3) for i, v in enumerate(d))
    assert all(v % 0x20 == 0 for v in d if v != 0xFFFF)
    assert _w(rom, 0x011596) == 0x363B          # move.w d(pc,d3.w),d3
    # credits
    z = rom.index(b"\0", 0x01192C)
    assert z == 0x011E75 and rom[0x011E76:0x011E78] == b"\0\0"
    body = rom[0x01192C:z]
    i = 0
    while i < len(body):
        if body[i] == 0xFF:
            assert body[i + 1] in (2, 3)
            i += 2
            continue
        assert body[i] == 0x0A or 0x20 <= body[i] < 0x7F, hex(i)
        i += 1
    assert rom[0x01193A:0x01193C] == b"\xff\x03"
    assert _l(rom, 0x0117C6) == 0x01192C and _l(rom, 0x011822) == 0x01193A
    # format strings and names pushed pc-relative
    assert rom[0x011F2C:0x011F34] == b"%6d\0%6d\0"
    _pea_pc(rom, 0x011FD6, 0x011F2C)
    _pea_pc(rom, 0x0120F8, 0x011F30)
    assert rom[0x0126C6:0x0126C8] == b".\0"
    _pea_pc(rom, 0x0126F2, 0x0126C6)
    assert rom[0x016088:0x016098] == b"SCEN%c%03d.INI\0\0"
    _pea_pc(rom, 0x0160DE, 0x016088)
    assert rom[0x016B86:0x016BA4] == b"UNIT\0TEAM\0BUILD\0DUNE\0MESSAGE\0\0"
    for at, s in ((0x016C1A, 0x016B86), (0x016C38, 0x016B8B),
                  (0x016C56, 0x016B90)):
        _pea_pc(rom, at, s)
    assert _l(rom, 0x016C9E) == 0x016B96 and _l(rom, 0x016CB8) == 0x016B9B
    assert rom[0x016D28:0x016D30] == b"%s.EMC\0\0"
    _pea_pc(rom, 0x016D38, 0x016D28)
    assert rom[0x0173F0:0x017414] == \
        b"PRESENT\0START GAME\0OPTIONS\0TUTORIAL\0"
    for at, s in ((0x01755E, 0x0173F0), (0x017812, 0x0173F8),
                  (0x01782A, 0x017403), (0x017842, 0x01740B)):
        _pea_pc(rom, at, s)
    # map-square steps
    assert [_s16(_w(rom, 0x012A9C + 2 * i)) for i in range(8)] == \
        [-64, -63, 1, 65, 64, 63, -1, -65]
    assert _w(rom, 0x012A92) == 0x303B
    # houses, movement types, team actions, orders
    at = 0x013004
    for i in range(HOUSES):
        assert _l(rom, HOUSE_TABLE + i * HOUSE_STRIDE) == at
        at += len(_cstr(rom, at)) + 1
    assert at == 0x013038
    for i in range(6):
        assert _l(rom, MOVE_LETTERS + 4 * i) == 0x013038 + 2 * i
    for i in range(5):
        assert _l(rom, TEAM_LETTERS + 4 * i) == 0x013044 + 2 * i
    assert rom[0x013038:0x01304E:2] == b"FTHWWSNSFKG"
    assert set(rom[0x013039:0x01304E:2]) == {0}
    at = 0x01304E
    for i in range(ORDERS):
        assert _l(rom, ORDER_NAMES + i * ORDER_STRIDE) == at
        at += len(_cstr(rom, at)) + 1
    assert at == 0x0130B0
    # the cursor object's frames and the stray palette
    fr = [_l(rom, 0x013216 + 8 * i + 4) for i in range(6)]
    assert all(_l(rom, 0x013216 + 8 * i) == 0 for i in range(6))
    assert fr == _frames(rom, 0x013246, 0x0137F2)
    assert all(_w(rom, f) == 19 for f in fr)
    for a in range(0x0137F2, 0x013872, 2):
        assert _w(rom, a) & 0xF111 == 0
    pal = rom[0x0137F2:0x013872]
    for a in (0x0307F4, 0x0331AC, 0x036DEA, 0x03C980, 0x03F4E6):
        assert rom[a:a + 128] == pal
    assert _l(rom, 0x013104) == 0x5960          # a VRAM address, not ROM
    # menu pointer frame
    assert _frames(rom, 0x017B5A, 0x017B68) == [0x017B5A]
    assert _l(rom, 0x017A36) == 0x017B5A
    # tutorial demonstrations
    frames = _frames(rom, 0x0190C0, 0x019576)
    assert len(frames) == 45
    lists = [_l(rom, 0x019576 + 4 * i) for i in range(3)]
    assert lists == [0x019582, 0x0195BE, 0x0195FA]
    ptrs = [_l(rom, a) for a in range(0x019582, 0x019636, 4)]
    assert sorted(ptrs) == frames
    assert [_l(rom, 0x01904C + 8 * i) for i in range(15)] == ptrs[:15]
    assert all(_l(rom, 0x019048 + 8 * i) == 0 for i in range(15))
    scripts = [_l(rom, 0x019636 + 4 * i) for i in range(3)]
    assert scripts == [0x019642, 0x019714, 0x0197E6]
    for s, e in zip(scripts, scripts[1:] + [0x0198B8]):
        a, steps = s, 0
        while True:
            c = _w(rom, a)
            a += 2
            if c == 0:
                break
            assert c in (1, 2)
            if c == 1:
                a += 4
            else:
                steps += 1
        assert a == e and steps == 14
    assert _l(rom, 0x017DE0) == 0x019636 and _l(rom, 0x017DEE) == 0x019576
    # arctangent tables
    cot = [_l(rom, 0x0198B8 + 4 * i) for i in range(32)]
    assert cot[0] == 0x3FFF
    assert all(cot[i] == int(256 / math.tan(i * 2 * math.pi / 256))
               for i in range(1, 32))
    assert [_w(rom, 0x019938 + 2 * i) for i in range(4)] == \
        [0x40, 0x80, 0x00, 0xC0]
    assert list(rom[0x0199D4:0x0199D8]) == [0, 1, 1, 0]
    assert _w(rom, 0x0199A0) == 0x41FA and \
        0x0199A2 + _s16(_w(rom, 0x0199A2)) == 0x0198B8
    # code
    for entry, end in CODE_ENDS_10000.items():
        a = entry
        while a < end:
            ins = m68k.decode(rom, a, 0)
            assert m68k.roundtrips(ins), hex(a)
            a += ins.length
        assert a == end, hex(entry)
    # extents do not overlap
    prev = 0
    for s, e, _ in TABLES_10000:
        assert s >= prev and e > s, hex(s)
        prev = e
    return True


# ======================================================================
# the small leftovers of $00A000-$01FFFF
#
# The small leftovers in $00A000-$01FFFF that neither bank's pass settled.

# Two zero bytes after a routine's rts, so that the next routine starts on
# a longword boundary (every one of them is followed by an address that is
# a multiple of 4, and nothing reads them).
_ALIGN = [0x00E25E, 0x0117B2, 0x0124D6, 0x01272E, 0x012A7A, 0x016A66,
          0x0173EE, 0x017A1A, 0x019A26, 0x019A8A, 0x01B1D2, 0x01FC46]

TABLES_X = [(a, a + 2, "two zero bytes after the rts at $%06X that put the "
           "next routine on a longword boundary; nothing reads them"
           % (a - 2)) for a in _ALIGN]
TABLES_X.append((0x01B2E2, 0x01B2E4, "two zero bytes between the last of the 27 map pointers at $01B276 (read by $01B1D4 with an index, not up to a terminator) and the mentat's prose at $01B2E4, which puts the prose on a longword boundary; the trace never read them"))
TABLES_X.sort()

CODE_X = [
    (0x00CC52, "addi.l #$800080,d2, the fall-through of lsl.l at $00CC50 - "
               "the label the listing puts at $00CC54 falls inside it"),
    (0x00DDDA, "tst.w $FFC728.l, the target of the routine's branches - the "
               "label the listing puts at $00DDDE falls inside it"),
    (0x00F0F4, "moveq #1,d0 then the epilogue at $00F0F6 (movem, rts): "
               "targets of beq.s at $00F086/$00F08C and bra.s at $00F0E6/"
               "$00F0F2 that the trace never took"),
    (0x010016, "bra.w $01039A, the fall-through after bclr at $010012 - the "
               "listing's bclr.l d1,d2 at $010018 is this branch's "
               "displacement word"),
    (0x01006C, "bra.s $01009A, unreachable: it follows the bra.s at $01006A"),
    (0x0110FE, "move.w $FFC04C.l,d0 / rts - a getter nothing calls"),
    (0x01110A, "a bare rts after the traced $011106-$011108; nothing points "
               "at it"),
    (0x01154E, "movem.w 4(a7),d0-d1/a0-a1, an entry after the bra.s at "
               "$01154C that runs into the traced $011554; no caller found"),
    (0x012142, "a bare rts after the rts at $012140; nothing points at it"),
    (0x012AAC, "a bare rts after the table at $012A9C; nothing points at it"),
    (0x016086, "a bare rts after the rts at $016084; nothing points at it"),
    (0x016AB0, "moveq #-1,d6, the target of beq.s at $016A8C that the trace "
               "never took; runs into the traced $016AB2"),
    (0x01F9B8, "bra.s $01F9CE, unreachable: it follows the bra.s at $01F9B6"),
    (0x01FA16, "movea.w #1,a4 / movea.w #2,a5 / move.w #0,-$30(a6) - the "
               "trace ran it (flags 3 at $01FA16), yet the listing has it "
               "as dc.b"),
    (0x01FEDA, "movem.l (a7)+,d0-d4/a0-a1 / rts, the target of beq.w at "
               "$01FE74 that the trace never took"),
]

CODE_ENDS_X = {0x00CC52: 0x00CC58, 0x00DDDA: 0x00DDE0, 0x00F0F4: 0x00F0FC,
             0x010016: 0x01001A, 0x01006C: 0x01006E, 0x0110FE: 0x011106,
             0x01110A: 0x01110C, 0x01154E: 0x011554, 0x012142: 0x012144,
             0x012AAC: 0x012AAE, 0x016086: 0x016088, 0x016AB0: 0x016AB2,
             0x01F9B8: 0x01F9BA, 0x01FA16: 0x01FA24, 0x01FEDA: 0x01FEE0}


def _check_X(rom):
    assert rom[0x1B2E2:0x1B2E4] == b"\0\0"
    for a in _ALIGN:
        assert rom[a:a + 2] == b"\0\0" and (a + 2) % 4 == 0, hex(a)
        assert rom[a - 2:a] == b"\x4E\x75", hex(a)
    want = {0x00CC52: "addi.l #$800080,d2", 0x00DDDA: "tst.w $FFC728.l",
            0x010016: "bra.w $1039A", 0x01006C: "bra.s $1009A",
            0x01F9B8: "bra.s $1F9CE", 0x016AB0: "moveq.l #-$1,d6"}
    for a, end in CODE_ENDS_X.items():
        p = a
        while p < end:
            i = m68k.decode(rom, p, 0)
            assert m68k.roundtrips(i), hex(p)
            if p == a and a in want:
                assert m68k.text(i) == want[a], (hex(a), m68k.text(i))
            p += i.length
        assert p == end, hex(a)
    return True


# ======================================================================
TABLES = sorted(TABLES_0000 + TABLES_A000 + TABLES_10000 + TABLES_X)
CODE = sorted(CODE_0000 + CODE_A000 + CODE_10000 + CODE_X)
CODE_ENDS = {}
for _d in (CODE_ENDS_0000, CODE_ENDS_A000, CODE_ENDS_10000, CODE_ENDS_X):
    CODE_ENDS.update(_d)


def check(rom):
    """Assert every property the descriptions above rely on."""
    for part in (_check_0000, _check_A000, _check_10000, _check_X):
        assert part(rom) is not False
    last = 0x200
    for start, end, what in TABLES:
        assert 0x200 <= start < end <= 0x20000, hex(start)
        assert start >= last, "overlap at $%06X" % start
        assert what, hex(start)
        last = end
    for entry, why in CODE:
        assert entry % 2 == 0 and why, hex(entry)
        for start, end, _ in TABLES:
            assert not start <= entry < end, "code $%06X inside a table" % entry
        m68k.roundtrips(m68k.decode(rom, entry, 0)) or \
            (_ for _ in ()).throw(AssertionError(hex(entry)))
    for entry, end in CODE_ENDS.items():
        p = entry
        while p < end:
            i = m68k.decode(rom, p, 0)
            assert m68k.roundtrips(i), hex(p)
            p += i.length
        assert p == end, hex(entry)
    return True


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(_HERE))
    rom = open(os.path.join(root, "orig", "dune2.gen"), "rb").read()
    check(rom)
    print("%d tables, %d bytes; %d code entries - all checks pass"
          % (len(TABLES), sum(e - s for s, e, _ in TABLES), len(CODE)))
