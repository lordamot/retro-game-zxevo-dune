; map.asm - bank OBJ: what stands on the map and what the player can see
; of it (S3 unit_update_map, S8 the fog, S6 putting a structure down).
;
; All of it runs with the map in window 3 (map_game).

VEILED          EQU $7B         ; veiledIcon: the full fog overlay
FOG_FIRST       EQU $6C         ; the fog group: $6C + a 4-bit mask
BUILT_SLAB      EQU $7E         ; builtSlabIcon
WALL_ICON       EQU $21         ; wallIcon: a destroyed wall's ground
BLOOM_ICON      EQU $D0         ; bloomIcon

; HL = a square -> A = its flags byte (keeps HL).
map_flags:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret

; map_object_at ($01A8D8): HL = a square -> HL = the unit (if bit 4) or
; the structure (bit 5) its index names, or 0 (Z).  Clobbers A, DE.
map_object_at:
        ld  a, h
        cp  $10
        jr  nc, moa_none
        push hl
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        or  a
        jr  z, moa_none
        dec a
        ld  e, a
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, e
        bit MF_UNIT, (hl)
        jr  nz, moa_unit
        bit MF_STRUCT, (hl)
        jr  z, moa_none
        call struct_ptr
        or  1
        ret
moa_unit:
        call unit_ptr
        or  1
        ret
moa_none:
        ld  hl, 0
        xor a
        ret

; map_square_unveiled ($01AFE6): HL = a square -> NZ if it is revealed
; and its overlay is not a fog icon.  Keeps HL.  Clobbers A.
map_square_unveiled:
        call map_flags
        bit MF_UNVEILED, a
        ret z
        push hl
        call map_overlay_icon
        pop hl
        cp  VEILED + 1
        jr  nc, msu_yes
        cp  VEILED - 15
        jr  c, msu_yes
        xor a
        ret
msu_yes:
        or  1
        ret

; map_update_fog_edge ($01AADC): HL = a square (masked to $FFF).  Not
; revealed: the full fog.  Revealed with a fog overlay (or anything, while
; validate_strict): the fog icon for the mask of its N, E, S, W neighbours
; that are not revealed ($07156A: -64 +1 +64 -1, wrapping); 0 clears it.
; A revealed square with another overlay is left alone.
map_update_fog_edge:
        ld  a, h
        and $0F
        ld  h, a
        call map_flags
        bit MF_UNVEILED, a
        ld  c, 15
        jr  z, mfe_set
        ld  a, (validate_strict)
        or  a
        jr  nz, mfe_mask
        push hl
        call map_overlay_icon
        pop hl
        cp  VEILED + 1
        ret nc
        cp  VEILED - 15
        ret c
mfe_mask:
        ld  c, 0
        ld  de, -64
        ld  b, 1
        call mfe_side
        ld  de, 1
        ld  b, 2
        call mfe_side
        ld  de, 64
        ld  b, 4
        call mfe_side
        ld  de, -1
        ld  b, 8
        call mfe_side
        ld  a, c
        or  a
        jr  z, mfe_write
        cp  15
        jr  z, mfe_set
        push bc
        push hl
        ; a half-fogged square shows its unit to the player
        call map_unit_at
        jr  z, mfe_nounit
        push ix
        push hl
        pop ix
        ld  a, (player_house)
        FCALL unit_seen_by_house
        pop ix
mfe_nounit:
        pop hl
        pop bc
mfe_set:
        ld  a, c
        add a, FOG_FIRST
        ld  c, a
mfe_write:
        ; overlay = C: the high byte keeps the ground's bit 8
        ld  a, h
        or  MAP_HIGH >> 8
        ld  h, a
        ld  a, (hl)
        and 1
        sla c
        or  c
        ld  (hl), a
        ret

; One neighbour: HL = the square, DE = the offset, B = the mask bit.
mfe_side:
        push hl
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        call map_flags
        pop hl
        bit MF_UNVEILED, a
        ret nz
        ld  a, c
        or  b
        ld  c, a
        ret

; HL = a square -> HL = the unit on it, or 0 (Z).  (map_unit_at $01A934)
map_unit_at:
        call map_flags
        bit MF_UNIT, a
        jp  z, moa_none
        jp  map_object_at

; map_reveal_square ($01A9A8): HL = a square, for the player (the only
; house it acts for).  Skipped if revealed and its overlay is not a fog
; icon (the range starts one lower here, $6B, the cartridge's way).
; Sets bit 3, shows its unit to the player, marks its structure seen by
; the player (and the Fremen, for the Atreides), re-picks the fog of it and
; its four neighbours.  -> A = 1 if it revealed it.
map_reveal_square:
        ld  a, h
        and $0F
        ld  h, a
        call map_flags
        bit MF_UNVEILED, a
        jr  z, mrs_do
        push hl
        call map_overlay_icon
        pop hl
        cp  VEILED + 1
        jr  nc, mrs_no
        cp  VEILED - 16
        jr  c, mrs_no
mrs_do:
        push hl
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        set MF_UNVEILED, (hl)
        pop hl
        push hl
        call map_unit_at
        jr  z, mrs_nounit
        push ix
        push hl
        pop ix
        ld  a, (player_house)
        FCALL unit_seen_by_house
        pop ix
mrs_nounit:
        pop hl
        push hl
        call map_flags
        bit MF_STRUCT, a
        jr  z, mrs_nostruct
        call map_object_at
        ld  de, O_SEEN
        add hl, de
        ld  a, (player_house)
        ld  b, a
        inc b
        ld  a, 0
        scf
mrs_bit:
        rla
        djnz mrs_bit            ; A = 1 << player
        or  (hl)
        ld  (hl), a
        ld  a, (player_house)
        cp  1
        jr  nz, mrs_nostruct
        set 3, (hl)             ; the Fremen see what the Atreides see
mrs_nostruct:
        pop hl
        push hl
        call map_update_fog_edge
        pop hl
        push hl
        inc hl
        call map_update_fog_edge
        pop hl
        push hl
        dec hl
        call map_update_fog_edge
        pop hl
        push hl
        ld  de, -64
        add hl, de
        call map_update_fog_edge
        pop hl
        push hl
        ld  de, 64
        add hl, de
        call map_update_fog_edge
        pop hl
        ld  a, 1
        ret
mrs_no: xor a
        ret

; map_unfog_radius ($019FFE): HL -> a position, C = the radius in
; squares.  Every square of the box round the position's square, on the
; 64 x 64 array and not yet revealed, whose rounded distance from the
; centre square's corner (tile_distance_squares) is at most C, is revealed
; for the player.  Nothing if the centre is off the playable map.
map_unfog_radius:
        ld  a, c
        ld  (mur_r), a
        call pos_square
        call map_valid
        ret nc
        ld  a, l
        and $3F
        ld  (mur_x0), a
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  (mur_y0), a
        ; the centre's corner position
        ld  (mur_c + 1), a
        ld  a, (mur_x0)
        ld  (mur_c + 3), a
        xor a
        ld  (mur_c), a
        ld  (mur_c + 2), a
        ld  a, (mur_r)
        neg
        ld  (mur_dy), a
mur_row:
        ld  a, (mur_r)
        neg
        ld  (mur_dx), a
mur_col:
        ld  a, (mur_y0)
        ld  hl, mur_dy
        add a, (hl)
        cp  64
        jr  nc, mur_next        ; off the array (or negative)
        ld  (mur_p + 1), a
        ld  l, a
        ld  a, (mur_x0)
        ld  de, mur_dx
        ex  de, hl
        add a, (hl)
        ex  de, hl
        cp  64
        jr  nc, mur_next
        ld  (mur_p + 3), a
        ; the square
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        or  l
        ld  l, a
        call map_flags
        bit MF_UNVEILED, a
        jr  nz, mur_next
        push hl
        xor a
        ld  (mur_p), a
        ld  (mur_p + 2), a
        ld  hl, mur_c
        ld  de, mur_p
        call tile_distance
        ld  de, $80
        add hl, de              ; rounded to squares: (d + $80) >> 8
        ld  a, (mur_r)
        cp  h
        pop hl
        jr  c, mur_next         ; further than r
        push hl
        call map_reveal_square
        pop hl
        push hl
        call map_overlay_icon
        pop hl
        or  a
        jr  nz, mur_next
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        set MF_UNVEILED, (hl)
mur_next:
        ld  a, (mur_dx)
        inc a
        ld  (mur_dx), a
        ld  hl, mur_r
        dec a
        cp  (hl)
        jr  nz, mur_col
        ld  a, (mur_dy)
        inc a
        ld  (mur_dy), a
        dec a
        cp  (hl)
        jp  nz, mur_row
        ret

; -------------------------------------------------------- unit claims

; unit_update_map ($019B48): IX = the unit, A = the mode: 0 off the map,
; 1 on it, 2 only refresh.  Aircraft are never on the map.  Mode 1 claims
; the square under the position (or claim_pos while that is set) if
; nothing holds it, and lifts the fog one square round a unit on the
; player's side whose square is not yet unveiled; then every square the
; sprite covers (the type's dimension + 3 pixels) is released (0) or
; revealed for the player's own unit (1).
unit_update_map:
        ld  (uum_mode), a
        bit OF_NOTONMAP, (ix + O_FLAGS)
        ret nz
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        ret z
        ; the place walked: claim_pos, or the unit's own position
        ld  hl, claim_pos
        ld  a, (hl)
        inc hl
        or  (hl)
        inc hl
        or  (hl)
        inc hl
        or  (hl)
        ld  hl, claim_pos
        jr  nz, uum_1
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
uum_1:  ld  de, uum_pos
        ld  bc, 4
        ldir
        ld  hl, uum_pos
        call pos_square
        ld  (uum_sq), hl
        ; seen or unseen by the player: by the unit's own square
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        call map_flags
        bit MF_UNVEILED, a
        jr  nz, uum_seen
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, uum_seen
        ld  a, (player_house)
        FCALL unit_unseen_by_houses
        jr  uum_2
uum_seen:
        ld  a, (player_house)
        FCALL unit_seen_by_house
uum_2:  ld  a, (uum_mode)
        cp  1
        jr  nz, uum_walk
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        or  a
        jr  z, uum_claim
        ld  hl, (uum_sq)
        call map_square_unveiled
        jr  nz, uum_claim
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, uum_claim
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  c, 1
        call map_unfog_radius
uum_claim:
        ld  hl, (uum_sq)
        call map_object_at
        jr  nz, uum_walk
        ld  hl, (uum_sq)
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (ix + O_INDEX)
        inc a
        ld  (hl), a
        ld  a, h
        xor (MAP_INDEX ^ MAP_FLAGS) >> 8
        ld  h, a
        set MF_UNIT, (hl)
uum_walk:
        ; the squares under the sprite
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_dimension
        add hl, de
        ld  a, (hl)
        add a, 3
        cp  33
        jr  c, uum_3
        ld  a, 32
uum_3:  ld  hl, uum_pos
        call uum_visit
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        ret nz
        ; the worm: also where it was and before
        push ix
        pop hl
        ld  de, U_PRELAST_Y
        add hl, de
        ld  de, uum_pos
        ld  bc, 4
        ldir
        ld  a, 32
        ld  hl, uum_pos
        call uum_visit
        push ix
        pop hl
        ld  de, U_LAST_Y
        add hl, de
        ld  de, uum_pos
        ld  bc, 4
        ldir
        ld  a, 32
        ld  hl, uum_pos
        ; fall through

; map_visit_object_squares ($019E0C) for units: A = the size in pixels,
; HL -> the position; each distinct square covered gets the mode's
; routine.  (The size-33 branch, the 5 x 5 clearing, has no caller that
; reaches it.)
uum_visit:
        or  a
        ret z
        dec a
        cp  15
        jr  nc, uv_1
        ld  a, 15
uv_1:   ld  (uv_size), a
        ; position - half size ($06CC26[size]), as one 32-bit y:x value
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; DE = y, BC = x
        push de
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        ld  de, tbl_square_sample_half
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; half y
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; half x
        ; x - half x, the borrow going into y
        push de
        push hl
        ld  h, b
        ld  l, c
        pop de
        or  a
        sbc hl, de
        ld  (uv_base + 2), hl
        pop de                  ; half y
        pop hl                  ; y
        sbc hl, de
        ld  (uv_base), hl
        ; the offsets: tbl_square_sample + 32 * (size - 1)
        ld  a, (uv_size)
        dec a
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  de, tbl_square_sample
        add hl, de
        ld  (uv_off), hl
        ld  hl, $FFFF
        ld  (uv_last), hl
        xor a
        ld  (uv_n), a
        ld  hl, 0
        ld  (uv_cur), hl
        ld  (uv_cur + 2), hl
uv_loop:
        ; pos = (base.y + cur.y, (base.x + cur.x) & $FFFF)
        ld  hl, (uv_base + 2)
        ld  de, (uv_cur + 2)
        add hl, de
        ld  (uv_pos + 2), hl
        ld  hl, (uv_base)
        ld  de, (uv_cur)
        add hl, de
        ld  (uv_pos), hl
        ; off the map if bit 14 or 15 is set in either word
        ld  a, (uv_pos + 1)
        and $C0
        jr  nz, uv_next
        ld  a, (uv_pos + 3)
        and $C0
        jr  nz, uv_next
        ld  hl, uv_pos
        call pos_square
        ld  de, (uv_last)
        or  a
        sbc hl, de
        add hl, de
        jr  z, uv_next
        ld  (uv_last), hl
        call uv_routine
uv_next:
        ld  hl, (uv_off)
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        inc hl
        ld  (uv_off), hl
        ld  (uv_cur), de
        ld  (uv_cur + 2), bc
        ld  a, d
        or  e
        or  b
        or  c
        ret z                   ; a zero offset ends the record
        ld  a, (uv_n)
        inc a
        ld  (uv_n), a
        cp  9
        jr  c, uv_loop
        ret

; The mode's routine for square HL ($0714E6).
uv_routine:
        ld  a, (uum_mode)
        or  a
        jr  z, uvr_release
        dec a
        ret nz                  ; mode 2: nothing
        ; mode 1: the player's unit reveals a square not yet revealed
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        call map_flags
        bit MF_UNVEILED, a
        ret nz
        jp  map_reveal_square
uvr_release:
        ; the unit's own claim: cleared, except on its destination square
        ; while bit 6 of its flags is clear
        call map_flags
        bit MF_UNIT, a
        ret z
        push hl
        call map_object_at
        push ix
        pop de
        or  a
        sbc hl, de
        pop hl
        ret nz
        push hl
        push ix
        pop hl
        ld  de, U_DEST_Y
        add hl, de
        call pos_square
        pop de
        or  a
        sbc hl, de
        ex  de, hl
        jr  nz, uvr_clear
        bit OF_BULLETBIG, (ix + O_FLAGS)
        ret z
uvr_clear:
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  (hl), 0
        ld  a, h
        xor (MAP_INDEX ^ MAP_FLAGS) >> 8
        ld  h, a
        res MF_UNIT, (hl)
        ret

; ----------------------------------------------------- structures down

; The icon a structure's squares show when built: square k of its layout
; is this + k (structanims.txt).  Slabs and the wall are special.
tbl_struct_built:
        DW  BUILT_SLAB, BUILT_SLAB, $0D2, $0DF, $0DF, $0E5, $0EB, $0F7, $0F3
        DW  $0FB, $0F7, $0FF, $108, $10E, $022, $114, $11C, $124, $128

; struct_place_icons: IX = a structure with its position set; write its
; squares - ground icon, owner, the structure bit and its index - and set
; its structuresBuilt bit.  (struct_place's map part, S6 $00E6CC; the
; checks, the power, the fog and the animation are the STRUCT bank's.)
struct_place_icons:
        ld  a, (ix + O_TYPE)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_struct_built
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (spi_icon), de
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  (spi_sq), hl
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        ld  (spi_layout), a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_count
        add hl, de
        ld  a, (hl)
        ld  (spi_count), a
        ld  a, (spi_layout)
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, de              ; *18
        ld  de, tbl_layout_tiles
        add hl, de
        ld  (spi_offs), hl
        xor a
        ld  (spi_k), a
spi_loop:
        ld  hl, (spi_offs)
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  (spi_offs), hl
        ld  hl, (spi_sq)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ; the icon: base + k
        ld  de, (spi_icon)
        ld  a, (spi_k)
        add a, e
        ld  e, a
        jr  nc, spi_1
        inc d
spi_1:  call map_set_ground     ; HL = square, DE = icon
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        and $F8
        or  (ix + O_HOUSE)
        set MF_STRUCT, a
        res MF_UNIT, a
        ld  (hl), a
        ld  a, h
        xor (MAP_INDEX ^ MAP_FLAGS) >> 8
        ld  h, a
        ld  a, (ix + O_INDEX)
        inc a
        ld  (hl), a
        ld  a, (spi_k)
        inc a
        ld  (spi_k), a
        ld  hl, spi_count
        cp  (hl)
        jr  c, spi_loop
        ; structuresBuilt |= 1 << type, for its house
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  a, (ix + O_TYPE)
        jp  set_bit32

; HL -> a 32-bit little-endian mask, A = a bit 0-31: set it.  Clobbers A,
; B, DE.
set_bit32:
        ld  b, a
        srl a
        srl a
        srl a
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, b
        and 7
        ld  b, a
        inc b
        xor a
        scf
sb32:   rla
        djnz sb32
        or  (hl)
        ld  (hl), a
        ret

; HL = a square, DE = a ground icon (0-511): write it, keeping the
; overlay.  Keeps HL (the square's MAP_GROUND address on return).
map_set_ground:
        ld  a, h
        and $0F
        or  MAP_GROUND >> 8
        ld  h, a
        ld  (hl), e
        ld  a, h
        xor (MAP_HIGH ^ MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and $FE
        or  d
        ld  (hl), a
        ld  a, h
        xor (MAP_HIGH ^ MAP_GROUND) >> 8
        ld  h, a
        ret

; A slab or 4-slab square: HL = the square, A = the house: concrete.
map_place_slab:
        ld  de, BUILT_SLAB
        push af
        call map_set_ground
        pop af
        ld  c, a
        ld  a, h
        xor (MAP_FLAGS ^ MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and $F8
        or  c
        ld  (hl), a
        ret

; A wall square: HL = the square, A = the house.  Ground $22, the owner;
; then it and its four neighbours that are walls are joined
; (struct_connect_wall: the icon for the mask N1 E2 S4 W8 of wall
; neighbours).
map_place_wall:
        push hl
        ld  c, a
        ld  de, $022
        call map_set_ground
        ld  a, h
        xor (MAP_FLAGS ^ MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and $F8
        or  c
        ld  (hl), a
        pop hl
        push hl
        call wall_join
        pop hl
        push hl
        ld  de, -64
        add hl, de
        call wall_join
        pop hl
        push hl
        inc hl
        call wall_join
        pop hl
        push hl
        ld  de, 64
        add hl, de
        call wall_join
        pop hl
        dec hl
        ; fall through

; HL = a square: if it is a wall, re-pick its icon from its neighbours.
wall_join:
        ld  a, h
        and $0F
        ld  h, a
        push hl
        call map_landscape
        pop hl
        cp  11
        ret nz
        ld  c, 0
        ld  de, -64
        ld  b, 1
        call wj_side
        ld  de, 1
        ld  b, 2
        call wj_side
        ld  de, 64
        ld  b, 4
        call wj_side
        ld  de, -1
        ld  b, 8
        call wj_side
        ld  e, c
        ld  d, 0
        push hl
        ld  hl, wall_icons
        add hl, de
        ld  e, (hl)
        pop hl
        jp  map_set_ground
wj_side:
        push hl
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        push bc
        call map_landscape
        pop bc
        pop hl
        cp  11
        ret nz
        ld  a, c
        or  b
        ld  c, a
        ret
wall_icons:
        DB  $22, $25, $23, $24, $25, $25, $26, $27
        DB  $23, $28, $23, $29, $2A, $2B, $2C, $2D

; ------------------------------------------------ the bank's own scratch
uum_mode:       DB 0
uum_pos:        DS 4
uum_sq:         DW 0
uv_size:        DB 0
uv_base:        DS 4
uv_off:         DW 0
uv_last:        DW 0
uv_n:           DB 0
uv_cur:         DS 4
uv_pos:         DS 4
mur_r:          DB 0
mur_x0:         DB 0
mur_y0:         DB 0
mur_c:          DS 4
mur_p:          DS 4
mur_dx:         DB 0
mur_dy:         DB 0
spi_icon:       DW 0
spi_sq:         DW 0
spi_layout:     DB 0
spi_count:      DB 0
spi_offs:       DW 0
spi_k:          DB 0
