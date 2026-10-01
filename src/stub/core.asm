; core.asm - what every logic bank needs, in the stub so it costs no far
; call: record pointers, the map, positions, distances, directions,
; alliances and references.  Each routine is the cartridge's own (address
; in its header) unless it says otherwise.
;
; Positions are 4 bytes in memory, y word then x word (1/256 of a square;
; the high byte is the square).  Routines taking positions take pointers.

; ---------------------------------------------------------- the records

; A = a unit slot -> HL = its record.  Clobbers DE.
unit_ptr:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_unit_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a structure slot -> HL.  Clobbers DE.
struct_ptr:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_struct_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a house 0-5 -> HL = its record ($46 bytes).  Clobbers DE.
house_ptr:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_house_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a team slot -> HL ($54 bytes).  Clobbers DE.
team_ptr:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_team_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a unit type -> HL = its tbl_unit_info record.  Clobbers DE.
unit_info:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_unit_info_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a structure type -> HL = its tbl_struct_info record.  Clobbers DE.
struct_info:
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tbl_struct_info_ptr
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

; A = a house -> HL = its tbl_house_info record (30 bytes).  Clobbers DE.
house_info:
        ld  l, a
        add a, a
        add a, a
        add a, a
        add a, a                ; *16
        sub l                   ; *15
        add a, a                ; *30 (houses 0-5: fits a byte)
        ld  l, a
        ld  h, 0
        ld  de, tbl_house_info
        add hl, de
        ret

; The pointer tables.
tbl_unit_ptr:
.n = 0
        DUP UNIT_COUNT
        DW  UNITS_BASE + U_SIZE * .n
.n = .n + 1
        EDUP
tbl_struct_ptr:
.n = 0
        DUP STRUCT_COUNT
        DW  STRUCTS_BASE + S_SIZE * .n
.n = .n + 1
        EDUP
tbl_house_ptr:
.n = 0
        DUP HOUSE_COUNT
        DW  HOUSES_BASE + H_SIZE * .n
.n = .n + 1
        EDUP
tbl_team_ptr:
.n = 0
        DUP TEAM_COUNT
        DW  TEAMS_BASE + T_SIZE * .n
.n = .n + 1
        EDUP
tbl_unit_info_ptr:
.n = 0
        DUP UNIT_INFO_COUNT
        DW  tbl_unit_info + UNIT_INFO_SIZE * .n
.n = .n + 1
        EDUP
tbl_struct_info_ptr:
.n = 0
        DUP STRUCT_INFO_COUNT
        DW  tbl_struct_info + STRUCT_INFO_SIZE * .n
.n = .n + 1
        EDUP

; -------------------------------------------------------------- the map
;
; The map is in window 3 while game logic runs (map_game).  A square is
; y*64 + x; its four bytes are at MAP_GROUND/HIGH/FLAGS/INDEX + square.

; HL = a square -> HL = its MAP_GROUND address.
map_addr:
        ld  a, h
        and $0F
        or  MAP_GROUND >> 8
        ld  h, a
        ret

; HL = a square -> HL = its ground icon (0-511).  Clobbers A, DE.
map_ground_icon:
        call map_addr
        ld  e, (hl)
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and 1
        ld  h, a
        ld  l, e
        ret

; HL = a square -> A = its overlay icon (0-127).  Clobbers HL.
map_overlay_icon:
        call map_addr
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        srl a
        ret

; map_get_landscape_type ($0057E6): HL = a square -> A = its landscape
; type (S3/S8), $FF for "no ground".  The byte table at $005818 by ground
; icon; an overlay that the table calls 13 makes it a destroyed wall.
; Clobbers DE, HL.
map_landscape:
        push hl
        call map_overlay_icon
        ld  e, a
        ld  d, 0
        ld  hl, tbl_icon_landscape
        add hl, de
        ld  a, (hl)
        pop hl
        cp  13
        ret z
        call map_ground_icon
        ld  de, tbl_icon_landscape
        add hl, de
        ld  a, (hl)
        ret

; A = a landscape type -> HL = its tbl_landscape record.  Clobbers DE.
landscape_info:
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl              ; *4
        ld  d, h
        ld  e, l
        add hl, hl              ; *8
        add hl, de              ; *12
        add hl, hl              ; *24
        add hl, de              ; *28
        ld  de, tbl_landscape
        add hl, de
        ret

; map_is_valid_position ($005798): HL = a square -> carry set if it is in
; the playable area for the map's scale ($06CE7A: x0, y0, w, h words).
; Keeps HL, DE.  Clobbers A.
map_valid:
        push hl
        push de
        ld  a, l
        and $3F
        ld  e, a                ; x
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  d, a                ; y
        ld  a, (map_scale)
        add a, a
        add a, a
        add a, a
        ld  hl, tbl_playable_area
        add a, l
        ld  l, a
        jr  nc, mv_1
        inc h
mv_1:   ld  a, e
        sub (hl)                ; x - x0
        jr  c, mv_no
        inc hl
        inc hl
        inc hl
        inc hl
        cp  (hl)                ; < w
        jr  nc, mv_no
        dec hl
        dec hl
        ld  a, d
        sub (hl)                ; y - y0
        jr  c, mv_no
        inc hl
        inc hl
        inc hl
        inc hl
        cp  (hl)                ; < h
        jr  nc, mv_no
        pop de
        pop hl
        scf
        ret
mv_no:  pop de
        pop hl
        or  a
        ret

; ------------------------------------------------------------ positions

; HL -> a position -> HL = its square, y*64 + x.  Clobbers A.
pos_square:
        inc hl
        ld  a, (hl)             ; y high byte: the row
        inc hl
        inc hl
        push de
        ld  e, (hl)             ; x high byte: the column
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, e
        and $3F
        or  l
        ld  l, a
        ld  a, h
        and $0F
        ld  h, a
        pop de
        ret

; HL = a square -> (DE) = the position of its centre (square * 256 + 128
; on each axis).  Keeps HL.  Clobbers A.
square_centre:
        push hl
        ld  a, $80
        ld  (de), a
        inc de
        add hl, hl
        add hl, hl              ; H = the row
        ld  a, h
        and $3F
        ld  (de), a
        inc de
        ld  a, $80
        ld  (de), a
        inc de
        pop hl
        ld  a, l
        and $3F
        ld  (de), a
        dec de
        dec de
        dec de
        ret

; tile_distance ($0115CE): HL, DE -> two positions -> HL = the larger of
; |dy| and |dx| plus half the smaller, in 1/256 squares.  Clobbers A, BC.
tile_distance:
        push de
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = y1
        inc hl
        push hl
        ex  de, hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = y2
        inc hl
        ex  (sp), hl            ; stack -> x2's address, HL -> x1
        push hl
        ld  h, b
        ld  l, c
        or  a
        sbc hl, de
        call abs_hl
        ld  b, h
        ld  c, l                ; BC = |dy|
        pop hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = x1
        pop hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; HL = x2
        or  a
        sbc hl, de
        call abs_hl             ; HL = |dx|
        pop de
        ; the larger plus half the smaller
        or  a
        sbc hl, bc
        add hl, bc
        jr  c, td_dy_big        ; |dx| < |dy|
        srl b
        rr  c
        add hl, bc
        ret
td_dy_big:
        srl h
        rr  l
        add hl, bc
        ret

; tile_distance_packed ($0114EC): HL, DE = two squares -> HL = the same
; distance in whole squares.  Clobbers A, BC.
tile_distance_packed:
        ld  a, l
        and $3F
        ld  b, a
        ld  a, e
        and $3F
        sub b
        jr  nc, tdp_1
        neg
tdp_1:  ld  c, a                ; |dx|
        add hl, hl
        add hl, hl
        ex  de, hl
        add hl, hl
        add hl, hl              ; H = y2, D = y1
        ld  a, h
        and $3F
        ld  b, a
        ld  a, d
        and $3F
        sub b
        jr  nc, tdp_2
        neg
tdp_2:  ld  b, a                ; |dy|
        cp  c
        jr  nc, tdp_3           ; |dy| >= |dx|
        srl a
        add a, c
        jr  tdp_4
tdp_3:  ld  a, c
        srl a
        add a, b
tdp_4:  ld  l, a
        ld  h, 0
        ret

; tile_direction_packed ($01152A): HL = from, DE = to (squares) -> A =
; the heading $00-$E0 in steps of $20, or $FF (the table's -1) for none.
; Clobbers BC, DE, HL.
tile_direction_packed:
        ; x0 = HL & 63, y0 = HL >> 6; x1, y1 the same of DE
        ld  a, l
        and $3F
        ld  b, a                ; x0
        ld  a, e
        and $3F
        ld  c, a                ; x1
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  h, a                ; y0
        ex  de, hl
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  l, a                ; y1
        ld  h, d                ; H = y0
        ; d3: y1 <= y0 -> 8; x1 <= x0 -> 4
        ld  e, 0
        ld  a, h
        cp  l
        jr  c, tdk_1            ; y0 < y1: no
        set 3, e
tdk_1:  ld  a, b
        cp  c
        jr  c, tdk_2
        set 2, e
tdk_2:  ; dx = x1 - x0, dy = y1 - y0 (signed bytes)
        ld  a, c
        sub b
        ld  c, a                ; dx
        ld  a, l
        sub h
        ld  b, a                ; dy
        ; |dy| > |2*dx| -> 2
        ld  a, c
        add a, a
        jp  p, tdk_3
        neg
tdk_3:  ld  d, a                ; |2dx|
        ld  a, b
        or  a
        jp  p, tdk_4
        neg
tdk_4:  cp  d
        jr  z, tdk_5
        jr  c, tdk_5
        set 1, e
tdk_5:  ; |dx| > |2*dy| -> 1
        ld  a, b
        add a, a
        jp  p, tdk_6
        neg
tdk_6:  ld  d, a
        ld  a, c
        or  a
        jp  p, tdk_7
        neg
tdk_7:  cp  d
        jr  z, tdk_8
        jr  c, tdk_8
        set 0, e
tdk_8:  ld  d, 0
        ld  hl, tbl_direction_packed
        add hl, de
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        bit 7, h
        ld  a, $FF
        ret nz
        ld  a, l
        ret

; tile_direction ($0115F4, math_atan2 $019940): HL = from, DE = to
; (positions) -> A = the direction 0-255 (0 north, $40 east).
; Clobbers BC, DE, HL.
tile_direction:
        push hl
        push de
        ; dy = y2 - y1, dx = x2 - x1
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        inc hl
        ex  de, hl
        ld  a, (hl)
        inc hl
        push hl
        ld  h, (hl)
        ld  l, a
        or  a
        sbc hl, bc
        ld  (atn_dy), hl
        pop hl
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = x2
        ex  de, hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = x1
        ld  h, b
        ld  l, c
        or  a
        sbc hl, de
        ld  (atn_dx), hl
        pop de
        pop hl
        ; the quadrant: dy <= 0 +2 (and dy = -dy); dx < 0 +1 (dx = -dx)
        ld  c, 0
        ld  hl, (atn_dy)
        ld  a, h
        or  a
        jp  m, atn_dyneg
        or  l
        jr  nz, atn_dypos
atn_dyneg:
        set 1, c
        call neg_hl
atn_dypos:
        ld  (atn_dy), hl
        ld  hl, (atn_dx)
        bit 7, h
        jr  z, atn_dxpos
        set 0, c
        call neg_hl
atn_dxpos:
        ld  (atn_dx), hl
        ld  a, c
        ld  (atn_q), a
        ; ratio: dx >= dy -> 256*dx/dy (d4 = 0); else 256*dy/dx (d4 = 1);
        ; a zero divisor leaves $7FFF
        xor a
        ld  (atn_d4), a
        ld  de, (atn_dy)
        or  a
        sbc hl, de              ; dx - dy
        jr  nc, atn_dxge
        ld  a, 1
        ld  (atn_d4), a
        ld  de, (atn_dx)        ; divisor dx
        ld  hl, (atn_dy)        ; dividend dy
        jr  atn_div
atn_dxge:
        ld  de, (atn_dy)        ; divisor dy
        ld  hl, (atn_dx)
atn_div:
        ld  a, d
        or  e
        jr  z, atn_inf
        ; 24-bit (HL << 8) / DE -> AHL (we need it compared with 16-bit
        ; table values: anything >= $10000 is bigger than all of them)
        ld  b, h
        ld  c, l
        call div24_16           ; A:H:L = (BC << 8) / DE
        or  a
        jr  nz, atn_inf
        jr  atn_search
atn_inf:
        ld  hl, $7FFF
atn_search:
        ; the first i with ratio >= cot[i] (cot descends); none -> 32
        ex  de, hl              ; DE = the ratio
        ld  hl, tbl_cot
        ld  b, 0
atn_s1:
        ld  a, (hl)
        inc hl
        ld  c, (hl)             ; the low word of the entry (they fit 16 bits)
        inc hl
        inc hl
        inc hl
        push hl
        ld  h, c
        ld  l, a
        ex  de, hl
        push hl
        or  a
        sbc hl, de              ; ratio - cot[i]
        pop hl
        ex  de, hl
        pop hl
        jr  nc, atn_found
        inc b
        ld  a, b
        cp  32
        jr  nz, atn_s1
atn_found:
        ld  a, (atn_d4)
        or  a
        ld  a, b
        jr  nz, atn_ok
        ld  a, $40
        sub b
atn_ok: ld  b, a                ; the angle within the quadrant
        ld  a, (atn_q)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_atan_quadrant
        add hl, de
        add hl, de
        ld  c, (hl)             ; the quadrant's base
        ld  a, e
        or  a
        jr  z, atn_sub
        cp  3
        jr  z, atn_sub
        ld  a, c                ; quadrants 1, 2: base + angle
        add a, b
        ret
atn_sub:
        ld  a, c                ; quadrants 0, 3: base - angle + $40
        sub b
        add a, $40
        ret

; A:H:L = (BC * 256) / DE, unsigned; DE non-zero.  Clobbers BC.
; The dividend is B:C:d24_lo and becomes the quotient bit by bit.
div24_16:
        xor a
        ld  (d24_lo), a
        ld  hl, 0               ; the remainder
        ld  a, 24
d24_loop:
        push af
        ld  a, (d24_lo)
        sla a
        ld  (d24_lo), a
        rl  c
        rl  b
        adc hl, hl
        sbc hl, de
        jr  nc, d24_fit
        add hl, de
        jr  d24_next
d24_fit:
        ld  a, (d24_lo)
        inc a
        ld  (d24_lo), a
d24_next:
        pop af
        dec a
        jr  nz, d24_loop
        ld  a, (d24_lo)
        ld  l, a
        ld  h, c
        ld  a, b
        ret

; tile_move_by_direction ($01162E): HL -> a position (changed in place),
; A = the direction, C = the distance (0-255).  y += (-cos * d + 64) >> 7,
; x += (sin * d + 64) >> 7, arithmetic.  Clobbers A, BC, DE.
tile_move_by_direction:
        ld  b, a
        ld  a, c
        or  a
        ret z
        push hl
        ; y
        push bc
        ld  a, b
        ld  e, a
        ld  d, 0
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        call smul_d8            ; HL = A (signed) * C (unsigned)
        pop bc
        ld  de, $40
        add hl, de
        call sar7_hl
        ex  de, hl
        pop hl
        push hl
        ld  a, (hl)
        add a, e
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, d
        ld  (hl), a
        ; x
        ld  e, b
        ld  d, 0
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        call smul_d8
        ld  de, $40
        add hl, de
        call sar7_hl
        ex  de, hl
        pop hl
        push hl
        inc hl
        inc hl
        ld  a, (hl)
        add a, e
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, d
        ld  (hl), a
        pop hl
        ret

; HL = A (signed byte) * C (unsigned byte).  Clobbers A, B, DE.
smul_d8:
        ld  e, a
        rla
        sbc a, a
        ld  d, a                ; DE = sign-extended A
        ld  hl, 0
        ld  a, c
        ld  b, 8
smd_l:  add hl, hl
        rla
        jr  nc, smd_n
        add hl, de
smd_n:  djnz smd_l
        ret
; HL >>= 7, arithmetic.  Clobbers A.
sar7_hl:
        ld  a, l
        rla                     ; carry = bit 7 of L
        ld  a, h
        rla                     ; A = H << 1 | that bit; carry = the sign
        ld  l, a
        sbc a, a                ; $FF if negative, else 0
        ld  h, a
        ret

; ------------------------------------------------------------- alliances

; house_are_allied ($023720): B, C = two houses -> A = 1 allied, 0 not.
; A house is allied with itself; otherwise by the sides at $023750: a sum
; above 0 allied, 0 not, below 0 allied only if neither is the player's.
; Clobbers DE, HL.
house_are_allied:
        bit 7, b
        jr  nz, haa_no
        bit 7, c
        jr  nz, haa_no
        ld  a, b
        cp  c
        jr  z, haa_yes
        ld  hl, tbl_house_side
        ld  e, b
        ld  d, 0
        add hl, de
        ld  a, (hl)
        ld  hl, tbl_house_side
        ld  e, c
        add hl, de
        add a, (hl)
        jr  z, haa_no
        jp  p, haa_yes
        ld  a, (player_house)
        cp  b
        jr  z, haa_no
        cp  c
        jr  z, haa_no
haa_yes:
        ld  a, 1
        ret
haa_no: xor a
        ret

; ------------------------------------------------------------ references
;
; kind << 14 | value: 1 unit, 2 structure, 3 map square (S2).

; ref_is_valid ($02E2FA): HL = a reference -> A = 1 valid, 0 not: a
; unit used and allocated, a structure used (and, the port's bound, a real
; slot), a square always.  Clobbers DE, HL.
ref_is_valid:
        ld  a, h
        and $C0
        ret z                   ; kind 0: never (A = 0)
        cp  $C0
        jr  z, riv_yes          ; a square: always
        cp  $40
        ld  a, l
        jr  z, riv_unit
        cp  STRUCT_COUNT
        jr  nc, riv_no
        call struct_ptr
        inc hl
        inc hl
        inc hl
        inc hl
        ld  a, (hl)
        and 1 << OF_USED
        ret z
        jr  riv_yes
riv_unit:
        cp  UNIT_COUNT
        jr  nc, riv_no
        call unit_ptr
        inc hl
        inc hl
        inc hl
        inc hl
        ld  a, (hl)
        and (1 << OF_USED) | (1 << OF_ALLOCATED)
        cp  (1 << OF_USED) | (1 << OF_ALLOCATED)
        jr  nz, riv_no
riv_yes:
        ld  a, 1
        ret
riv_no: xor a
        ret

; ref_square ($02E1F6): HL = a reference -> HL = the square of its
; position (ref_position).  Clobbers A, BC, DE.
ref_square:
        ld  de, ref_pos
        call ref_position
        ld  hl, ref_pos
        jp  pos_square

; ref_position ($02E256): HL = a reference, DE -> 4 bytes to fill with its
; position: a square's centre; a unit's position; a structure's position
; plus its layout's centre ($02E2CE by type +$3C & 7).  Clobbers A, BC, HL.
ref_position:
        ld  a, h
        and $C0
        cp  $C0
        jr  z, rp_square
        cp  $40
        jr  z, rp_unit
        cp  $80
        jr  z, rp_struct
        ; nothing: zeros
        xor a
        ld  (de), a
        inc de
        ld  (de), a
        inc de
        ld  (de), a
        inc de
        ld  (de), a
        dec de
        dec de
        dec de
        ret
rp_square:
        ; $C000 | row << 8 | $80 | col << 1 | 1 (S2): the square is
        ; row*64 + col
        ld  a, l
        rra
        and $3F                 ; col
        ld  c, a
        ld  a, h
        and $3F                 ; row
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, l
        or  c
        ld  l, a
        jp  square_centre
rp_unit:
        push de
        ld  a, l
        push de
        call unit_ptr
        pop de
        ld  bc, O_POS_Y
        add hl, bc
        ld  bc, 4
        ldir
        pop de
        ret
rp_struct:
        push de
        ld  a, l
        call struct_ptr         ; HL = the record
        pop de
        push de
        push hl
        ld  bc, O_POS_Y
        add hl, bc
        ld  bc, 4
        ldir                    ; its corner position
        pop hl
        inc hl
        inc hl
        ld  a, (hl)             ; the type
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        and 7
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_centre8
        add hl, de              ; the centre (dy, dx)
        pop de
        push de
        ld  a, (de)
        add a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        adc a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        add a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        adc a, (hl)
        ld  (de), a
        pop de
        ret

; ref_make_square: HL = a square -> HL = its reference (S2: $C000 | row
; << 8 | $80 | col << 1 | 1).  Clobbers A.
ref_make_square:
        ld  a, l
        and $3F
        add a, a
        or  $81
        push af
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        or  $C0
        ld  h, a
        pop af
        ld  l, a
        ret
