; loader.asm - DUNE.TRD's code file: reads DUNE.DAT off the SD card.
;
; The BaseConf firmware runs TRD, SCL, FDI and TAP files and nothing else;
; an SPG is a TS-Conf format.  So the game ships as a TR-DOS disk the
; firmware mounts and boots, whose boot loads this at $6000 and calls it,
; and DUNE.DAT beside it on the card - the SPG file under another name.
; This talks to the card itself over the SPI port (BaseConf manual 9.7),
; walks the FAT16 or FAT32 file system to DUNE.DAT in the root directory,
; and puts every block where the SPG's block table says, then leaves the
; machine as an SPG loader would: windows 1 and 2 on pages 5 and 2, window
; 3 on page 0, SP at $BFFE, and jumps to the boot stub at $8000.
;
; Built by tools/dune_trd.py (sjasmplus --raw), which also writes the disk.

        ORG $6000
        INCLUDE "evo.inc"

; The card in shadow mode (port $BF bit 0 set, which the loader needs
; anyway for the memory manager): $xx57 with A15 = 0 is the SPI byte, with
; A15 = 1 the CS line - bit 1 low selects the card, bit 0 stays 1.
SD_DATA         EQU $0057
SD_CS           EQU $8057
CS_OFF          EQU %11
CS_ON           EQU %01

FILE_NAME_LEN   EQU 11
HDR_BYTES       EQU 1024

; error codes (shown as a number after the message)
E_NOCARD        EQU 1           ; no answer to CMD0
E_CMD8          EQU 2
E_ACMD41        EQU 3
E_OCR           EQU 4
E_CMD16         EQU 5
E_MBR           EQU 10          ; no $55AA / no partition
E_BPB           EQU 11          ; not 512 bytes a sector
E_NOFILE        EQU 20
E_READ          EQU 30          ; a sector did not come
E_CHAIN         EQU 31          ; the cluster chain ended early
E_SIGN          EQU 40          ; not "SpectrumProg"
E_VERSION       EQU 41
E_PACKED        EQU 42
E_PAGE          EQU 43          ; a block for page 5, where this runs

entry:
        di
        ld  sp, entry
        ld  a, 1
        out (PORT_BF), a        ; the shadow ports answer from here on
        ld  bc, PORT_77
        ld  a, V_ZX | TURBO14
        out (c), a              ; manager on, 14 MHz, the plain screen
        ld  a, (0 ^ $3F) | $40
        ld  bc, MMUF_W3
        out (c), a              ; window 3: clear the "mix with $7FFD" flag
        xor a
        out (PORT_FE), a
        call cls
        ld  hl, s_title
        ld  de, $4020
        call print
        ld  hl, s_reading
        ld  de, $4860
        call print

        call sd_init
        call fat_mount
        call find_file
        call load_file

        ; hand over as the SPG loader would
        di
        ld  a, (5 ^ $3F) | $40
        ld  bc, MMUF_W1
        out (c), a
        ld  a, (2 ^ $3F) | $40
        ld  bc, MMUF_W2
        out (c), a
        ld  a, (0 ^ $3F) | $40
        ld  bc, MMUF_W3
        out (c), a
        ld  a, P7FFD_BASE
        ld  bc, PORT_7FFD
        out (c), a
        ld  a, $3F
        ld  i, a
        im  1
        ld  sp, $BFFE
        jp  $8000

; ------------------------------------------------------------------ errors
; A = the code.  Says so and stops.
fail:
        push af
        ld  hl, s_error
        ld  de, $5060
        call print
        pop af
        ld  de, $5060 + 7
        call print_hex
        call cs_off
        di
        halt

; --------------------------------------------------------------- the card
; A byte out, a byte in.  A read hands back the byte the previous exchange
; brought and starts another with $FF; the loops below only ever wait for a
; value, so that suits them.
sd_out:
        push bc
        ld  bc, SD_DATA
        out (c), a
        pop bc
        ret

sd_in:
        push bc
        ld  bc, SD_DATA
        in  a, (c)
        pop bc
        ret

cs_off:
        push af
        push bc
        ld  bc, SD_CS
        ld  a, CS_OFF
        out (c), a
        ld  a, $FF
        call sd_out
        pop bc
        pop af
        ret

cs_on:
        push af
        push bc
        ld  bc, SD_CS
        ld  a, CS_ON
        out (c), a
        ld  a, $FF
        call sd_out
        pop bc
        pop af
        ret

; A = the command byte, (arg) the four argument bytes most significant
; first, (crc) the checksum byte (put back to $FF afterwards).
; Out: A = R1; Z if the card answered, NZ if it never did.
sd_cmd:
        push af
        call cs_off
        call cs_on
        pop af
        push bc
        push de
        push hl
        ld  bc, SD_DATA
        out (c), a
        ld  hl, arg
        ld  a, (hl)
        out (c), a
        inc hl
        ld  a, (hl)
        out (c), a
        inc hl
        ld  a, (hl)
        out (c), a
        inc hl
        ld  a, (hl)
        out (c), a
        ld  a, (crc)
        out (c), a
        ld  a, $FF
        ld  (crc), a
        ld  d, 32
.wait:  in  a, (c)
        bit 7, a
        jr  z, .ok
        dec d
        jr  nz, .wait
        or  a                   ; never answered: A = $FF, NZ
.ok:    pop hl
        pop de
        pop bc
        ret

; (arg) = 0
arg_zero:
        xor a
        ld  (arg), a
        ld  (arg + 1), a
        ld  (arg + 2), a
        ld  (arg + 3), a
        ret

; CMD55 then ACMD41 with H as the argument's top byte.  Out: A = R1.
acmd41:
        call arg_zero
        ld  a, $40 | 55
        call sd_cmd
        call arg_zero
        ld  a, h
        ld  (arg), a
        ld  a, $40 | 41
        jp  sd_cmd

sd_init:
        call cs_off
        ld  b, 20               ; 160 clocks with the card deselected
.clk:   ld  a, $FF
        call sd_out
        djnz .clk
        ld  de, 2000
.cmd0:  call arg_zero
        ld  a, $95
        ld  (crc), a
        ld  a, $40 | 0
        call sd_cmd
        jr  nz, .again0
        cp  1                   ; idle
        jr  z, .cmd8
.again0:
        dec de
        ld  a, d
        or  e
        jr  nz, .cmd0
        ld  a, E_NOCARD
        jp  fail

.cmd8:  call arg_zero
        ld  a, 1
        ld  (arg + 2), a
        ld  a, $AA
        ld  (arg + 3), a
        ld  a, $87
        ld  (crc), a
        ld  a, $40 | 8
        call sd_cmd
        ld  b, a
        ld  a, E_CMD8
        jp  nz, fail
        bit 2, b                ; illegal command: a version 1 card
        jr  nz, .v1
        call sd_in
        call sd_in
        call sd_in              ; the echo: $01
        cp  1
        ld  a, E_CMD8
        jp  nz, fail
        call sd_in              ; $AA
        cp  $AA
        ld  a, E_CMD8
        jp  nz, fail
        ld  de, 8000
.a41:   ld  h, $40              ; HCS: high capacity is fine by us
        call acmd41
        jr  nz, .a41r
        or  a
        jr  z, .ocr
.a41r:  dec de
        ld  a, d
        or  e
        jr  nz, .a41
        ld  a, E_ACMD41
        jp  fail
.ocr:   call arg_zero
        ld  a, $40 | 58
        call sd_cmd
        ld  b, a
        ld  a, E_OCR
        jp  nz, fail
        call sd_in              ; OCR bits 31-24: bit 6 = block addressing
        and $40
        ld  (sdhc), a
        call sd_in
        call sd_in
        call sd_in
        jr  .blocklen

.v1:    ld  de, 8000
.a41v1: ld  h, 0
        call acmd41
        jr  nz, .a41v1r
        or  a
        jr  z, .blocklen
        bit 2, a                ; no ACMD41 either: an MMC, CMD1 then
        jr  nz, .mmc
.a41v1r:
        dec de
        ld  a, d
        or  e
        jr  nz, .a41v1
        ld  a, E_ACMD41
        jp  fail
.mmc:   ld  de, 8000
.cmd1:  call arg_zero
        ld  a, $40 | 1
        call sd_cmd
        jr  nz, .cmd1r
        or  a
        jr  z, .blocklen
.cmd1r: dec de
        ld  a, d
        or  e
        jr  nz, .cmd1
        ld  a, E_ACMD41
        jp  fail

.blocklen:
        ld  a, (sdhc)
        or  a
        jr  nz, .done
        call arg_zero           ; a byte-addressed card: 512 a block
        ld  a, 2
        ld  (arg + 2), a
        ld  a, $40 | 16
        call sd_cmd
        ld  b, a
        ld  a, E_CMD16
        jp  nz, fail
        ld  a, b
        or  a
        ld  a, E_CMD16
        jp  nz, fail
.done:  jp  cs_off

; Read sector (lba) to HL.  Out: HL just past it.  Fails on any error.
sd_read:
        push hl
        ld  a, (sdhc)
        or  a
        jr  nz, .blocks
        ld  hl, lba             ; byte address: lba * 512
        ld  a, (hl)
        inc hl
        ld  b, (hl)
        inc hl
        ld  c, (hl)
        ; arg = b2:b1:b0 of (lba << 9), most significant first
        xor a
        ld  (arg + 3), a
        ld  d, a
        ld  a, (lba)
        add a, a
        ld  (arg + 2), a
        ld  a, b
        rla
        ld  (arg + 1), a
        ld  a, c
        rla
        ld  (arg), a
        jr  .go
.blocks:
        ld  a, (lba + 3)
        ld  (arg), a
        ld  a, (lba + 2)
        ld  (arg + 1), a
        ld  a, (lba + 1)
        ld  (arg + 2), a
        ld  a, (lba)
        ld  (arg + 3), a
.go:    ld  a, $40 | 17
        call sd_cmd
        jr  nz, .err
        or  a
        jr  nz, .err
        ld  bc, SD_DATA
        ld  de, 0               ; 65536 tries for the data token
.token: in  a, (c)
        cp  $FE
        jr  z, .data
        dec de
        ld  a, d
        or  e
        jr  nz, .token
.err:   ld  a, E_READ
        jp  fail
.data:  pop hl
        ld  b, 0
        inir                    ; a read at A15 = 1 is still the byte
        inir
        in  a, (c)              ; the CRC, unchecked
        in  a, (c)
        jp  cs_off

; ---------------------------------------------------------- 32-bit helpers
; (HL) += (DE), four bytes each, little-endian
add32:
        ld  b, 4
        or  a
.l:     ld  a, (de)
        adc a, (hl)
        ld  (hl), a
        inc hl
        inc de
        djnz .l
        ret

; (HL) += DE (a 16-bit value)
add16_32:
        ld  a, e
        add a, (hl)
        ld  (hl), a
        inc hl
        ld  a, d
        adc a, (hl)
        ld  (hl), a
        inc hl
        ld  a, 0
        adc a, (hl)
        ld  (hl), a
        inc hl
        ld  a, 0
        adc a, (hl)
        ld  (hl), a
        ret

; (DE) = (HL), four bytes
copy32:
        ld  bc, 4
        ldir
        ret

; (HL) <<= 1, four bytes
shl32:
        or  a
        rl  (hl)
        inc hl
        rl  (hl)
        inc hl
        rl  (hl)
        inc hl
        rl  (hl)
        ret

; (HL) -= 1, four bytes
dec32:
        ld  b, 4
.l:     ld  a, (hl)
        sub 1
        ld  (hl), a
        ret nc
        inc hl
        djnz .l
        ret

; (HL) == (DE)?  Z if so.
cmp32:
        ld  b, 4
.l:     ld  a, (de)
        cp  (hl)
        ret nz
        inc hl
        inc de
        djnz .l
        ret

; ------------------------------------------------------------ the file system
fat_mount:
        call arg_zero
        ld  hl, 0
        ld  (lba), hl
        ld  (lba + 2), hl
        ld  hl, buf
        call sd_read
        ld  a, (buf + $1FE)
        cp  $55
        ld  a, E_MBR
        jp  nz, fail
        ld  a, (buf + $1FF)
        cp  $AA
        ld  a, E_MBR
        jp  nz, fail
        ld  a, (buf)            ; a jump: the boot sector itself
        cp  $EB
        jr  z, .bpb
        cp  $E9
        jr  z, .bpb
        ld  hl, buf + $1C6      ; else the MBR: partition 1's start
        ld  de, part
        call copy32
        ld  hl, part
        ld  de, lba
        call copy32
        ld  hl, buf
        call sd_read
        ld  a, (buf + $1FE)
        cp  $55
        ld  a, E_MBR
        jp  nz, fail
.bpb:   ld  hl, (buf + 11)      ; bytes a sector
        ld  de, 512
        or  a
        sbc hl, de
        ld  a, E_BPB
        jp  nz, fail
        ld  a, (buf + 13)
        ld  (spc), a
        ld  hl, (buf + 22)      ; FAT size, 16-bit: zero on FAT32
        ld  a, h
        or  l
        jr  nz, .fat16
        ld  a, 1
        ld  (fat32), a
        ld  hl, buf + 36
        ld  de, fatsz
        call copy32
        ld  hl, buf + 44
        ld  de, rootclus
        call copy32
        jr  .layout
.fat16: ld  (fatsz), hl
        xor a
        ld  (fat32), a
        ld  hl, 0
        ld  (fatsz + 2), hl
.layout:
        ; fat_start = part + reserved
        ld  hl, part
        ld  de, fat_start
        call copy32
        ld  de, (buf + 14)
        ld  hl, fat_start
        call add16_32
        ; root_start = fat_start + fats * fatsz
        ld  hl, fat_start
        ld  de, root_start
        call copy32
        ld  a, (buf + 16)
        ld  b, a
.fats:  push bc
        ld  hl, root_start
        ld  de, fatsz
        call add32
        pop bc
        djnz .fats
        ; root_secs = root entries / 16;  data_start = root_start + that
        ld  hl, (buf + 17)
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ld  (root_secs), hl
        ex  de, hl
        ld  hl, root_start
        ld  de, data_start
        call copy32
        ld  de, (root_secs)
        ld  hl, data_start
        call add16_32
        ld  hl, $FFFF           ; nothing cached yet
        ld  (fat_cache), hl
        ld  (fat_cache + 2), hl
        ret

; The sector of (cur_clus) + (sec_in_clus) into (lba).
clus_to_lba:
        ld  hl, cur_clus
        ld  de, lba
        call copy32
        ld  hl, lba
        call dec32
        ld  hl, lba
        call dec32
        ld  a, (spc)
.sh:    srl a
        jr  z, .shifted
        push af
        ld  hl, lba
        call shl32
        pop af
        jr  .sh
.shifted:
        ld  hl, lba
        ld  de, data_start
        call add32
        ld  a, (sec_in_clus)
        ld  e, a
        ld  d, 0
        ld  hl, lba
        jp  add16_32

; (cur_clus) = the chain's next.  Out: NZ at the end of the chain.
fat_next:
        ld  a, (fat32)
        or  a
        jr  nz, .f32
        ; FAT16: sector fat_start + clus / 256, entry (clus & 255) * 2
        ld  hl, (cur_clus)
        ld  a, l
        add a, a
        ld  c, a
        ld  b, buf_fat >> 8
        jr  nc, .lo16
        inc b
.lo16:  push bc
        ld  l, h
        ld  h, 0
        jr  .sector
.f32:   ; FAT32: sector fat_start + clus / 128, entry (clus & 127) * 4
        ld  a, (cur_clus)
        and $7F
        add a, a
        add a, a
        ld  c, a
        ld  b, buf_fat >> 8
        jr  nc, .lo32
        inc b
.lo32:  push bc
        ld  hl, (cur_clus)
        ld  a, (cur_clus + 2)
        ; HL:A >> 7
        add hl, hl
        rla
        ld  l, h
        ld  h, a
.sector:
        ld  (lba), hl
        ld  hl, 0
        ld  (lba + 2), hl
        ld  hl, lba
        ld  de, fat_start
        call add32
        ld  hl, lba
        ld  de, fat_cache
        call cmp32
        jr  z, .cached
        ld  hl, lba
        ld  de, fat_cache
        call copy32
        ld  hl, buf_fat
        call sd_read
.cached:
        pop hl                  ; the entry
        ld  a, (fat32)
        or  a
        jr  nz, .e32
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (cur_clus), de
        ld  hl, 0
        ld  (cur_clus + 2), hl
        ld  hl, $FFF8 - 1
        or  a
        sbc hl, de              ; carry: de >= $FFF8, the end
        ld  a, 0
        rla
        or  a
        ret
.e32:   ld  de, cur_clus
        call copy32
        ld  a, (cur_clus + 3)
        and $0F
        ld  (cur_clus + 3), a
        ; end if >= $0FFFFFF8: bytes 3,2,1 = $0F,$FF,$FF and byte 0 >= $F8
        cp  $0F
        jr  nz, .more
        ld  a, (cur_clus + 2)
        inc a
        jr  nz, .more
        ld  a, (cur_clus + 1)
        inc a
        jr  nz, .more
        ld  a, (cur_clus)
        cp  $F8
        ld  a, 0
        rla
        or  a                   ; NZ: the end
        ret
.more:  xor a
        ret

; Start reading a cluster chain at (DE:HL) - HL low.
stream_open:
        ld  (cur_clus), hl
        ld  (cur_clus + 2), de
        xor a
        ld  (sec_in_clus), a
        ld  (eof), a
        ret

; The chain's next sector to HL.  Out: HL just past it.
stream_next:
        ld  a, (eof)
        or  a
        ld  a, E_CHAIN
        jp  nz, fail
        push hl
        call clus_to_lba
        pop hl
        call sd_read
        push hl
        ld  a, (sec_in_clus)
        inc a
        ld  (sec_in_clus), a
        ld  hl, spc
        cp  (hl)
        jr  c, .same
        xor a
        ld  (sec_in_clus), a
        call fat_next
        jr  z, .same
        ld  a, 1
        ld  (eof), a
.same:  pop hl
        ret

; DUNE.DAT in the root directory: (cur_clus) = its first cluster.
find_file:
        ld  a, (fat32)
        or  a
        jr  nz, .f32
        ld  hl, root_start
        ld  de, lba
        call copy32
        ld  hl, (root_secs)
.f16:   push hl
        ld  hl, buf
        call sd_read
        call scan_dir
        pop hl
        ret z                   ; found
        jr  nc, .none           ; the directory ended
        push hl
        ld  hl, lba
        ld  de, 1
        call add16_32
        pop hl
        dec hl
        ld  a, h
        or  l
        jr  nz, .f16
        jr  .none
.f32:   ld  hl, (rootclus)
        ld  de, (rootclus + 2)
        call stream_open
.f32l:  ld  a, (eof)
        or  a
        jr  nz, .none
        ld  hl, buf
        call stream_next
        call scan_dir
        ret z
        jr  c, .f32l
.none:  ld  a, E_NOFILE
        jp  fail

; The 16 entries in buf.  Out: Z - found, and the file's chain is open;
; NZ and C - not here, look further; NZ and NC - the directory ends here.
scan_dir:
        ld  ix, buf
        ld  b, 16
.next:  ld  a, (ix + 0)
        or  a
        jr  z, .end
        cp  $E5
        jr  z, .skip
        bit 3, (ix + 11)        ; a label or a long-name piece
        jr  nz, .skip
        push ix
        pop hl
        ld  de, s_name
        ld  c, FILE_NAME_LEN
.cmp:   ld  a, (de)
        cp  (hl)
        jr  nz, .skip
        inc hl
        inc de
        dec c
        jr  nz, .cmp
        ld  l, (ix + 26)
        ld  h, (ix + 27)
        ld  e, (ix + 20)
        ld  d, (ix + 21)
        call stream_open
        xor a                   ; Z
        ret
.skip:  ld  de, 32
        add ix, de
        djnz .next
        or  1                   ; NZ ...
        scf                     ; ... and C: more sectors may hold it
        ret
.end:   or  1
        or  a                   ; NZ, NC
        ret

; ---------------------------------------------------------------- the SPG
load_file:
        ld  hl, hdr
        call stream_next
        call stream_next
        ld  hl, hdr + $20
        ld  de, s_sign
        ld  b, 12
.sig:   ld  a, (de)
        cp  (hl)
        ld  a, E_SIGN
        jp  nz, fail
        inc hl
        inc de
        djnz .sig
        ld  a, (hdr + $2C)
        cp  $10
        ld  a, E_VERSION
        jp  nz, fail
        ld  hl, (hdr + $3A)
        ld  (nblocks), hl
        ld  hl, 0
        ld  (done), hl
        ld  ix, hdr + $100
.block: ld  a, (ix + 1)
        and $C0
        ld  a, E_PACKED
        jp  nz, fail
        ld  a, (ix + 2)
        cp  5
        ld  a, E_PAGE
        jp  z, fail
        ld  a, (ix + 2)
        cpl
        ld  bc, MMU_W3
        out (c), a
        ld  a, (ix + 0)
        and $1F
        add a, a
        or  $C0
        ld  h, a
        ld  l, 0
        ld  a, (ix + 1)
        and $1F
        inc a
        ld  b, a
.sector:
        push bc
        call stream_next
        pop bc
        djnz .sector
        call progress
        bit 7, (ix + 0)
        ret nz
        inc ix
        inc ix
        inc ix
        ld  hl, (done)
        inc hl
        ld  (done), hl
        ld  de, (nblocks)
        or  a
        sbc hl, de
        jr  c, .block
        ret

; -------------------------------------------------------------- the screen
BAR_ATTR        EQU $5800 + 16 * 32
BAR_CELLS       EQU 32

progress:
        ld  hl, (acc)
        ld  de, BAR_CELLS
        add hl, de
        ld  (acc), hl
        ld  de, (nblocks)
.more:  ld  hl, (acc)
        or  a
        sbc hl, de
        ret c
        ld  (acc), hl
        ld  hl, (bar)
        ld  (hl), %00101000     ; paper cyan
        inc hl
        ld  (bar), hl
        jr  .more

cls:
        ld  hl, $4000
        ld  de, $4001
        ld  bc, $1800 - 1
        ld  (hl), 0
        ldir
        ld  hl, $5800
        ld  de, $5801
        ld  bc, $300 - 1
        ld  (hl), %00000111     ; white on black
        ldir
        ld  hl, BAR_ATTR
        ld  (bar), hl
        ld  de, BAR_ATTR + 1
        ld  bc, BAR_CELLS - 1
        ld  (hl), %00001000     ; paper blue
        ldir
        ret

; HL = a string ending in 0, DE = where (a screen address on a row's top)
print:
        ld  a, (hl)
        or  a
        ret z
        push hl
        push de
        sub 32
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  bc, font            ; the game's own: the page at $0000 is
        add hl, bc              ; not the BASIC ROM under the firmware
        ld  b, 8
.row:   ld  a, (hl)
        ld  (de), a
        inc hl
        inc d
        djnz .row
        pop de
        pop hl
        inc de
        inc hl
        jr  print

; A as two hex digits at DE
print_hex:
        push af
        rrca
        rrca
        rrca
        rrca
        call .digit
        pop af
.digit: and $0F
        add a, "0"
        cp  "9" + 1
        jr  c, .ok
        add a, "A" - "9" - 1
.ok:    ld  (s_digit), a
        push de
        ld  hl, s_digit
        call print
        pop de
        inc de
        ret

s_title:    db "DUNE II - THE BATTLE FOR ARRAKIS", 0
s_reading:  db "READING DUNE.DAT", 0
s_error:    db "ERROR", 0
s_digit:    db 0, 0
s_name:     db "DUNE    DAT"
s_sign:     db "SpectrumProg"
font:       INCBIN "font.bin"   ; glyphs 32-127, 8 bytes each (dune_trd.py)

; ----------------------------------------------------------------- state
sdhc:       db 0                ; non-zero: the card takes block numbers
fat32:      db 0
spc:        db 0                ; sectors a cluster
eof:        db 0
sec_in_clus: db 0
crc:        db $FF
arg:        ds 4
lba:        ds 4
part:       ds 4
fatsz:      ds 4
fat_start:  ds 4
root_start: ds 4
data_start: ds 4
rootclus:   ds 4
root_secs:  dw 0
fat_cache:  ds 4
cur_clus:   ds 4
nblocks:    dw 0
done:       dw 0
acc:        dw 0
bar:        dw 0

        ALIGN 256
buf:        ds 512              ; a sector
buf_fat:    ds 512              ; the FAT sector last read
hdr:        ds HDR_BYTES        ; the SPG's header and block table
loader_end:
        ASSERT loader_end <= $8000
