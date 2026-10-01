; pools.asm - bank OBJ: the four pools (S2), the lists beside them, and
; the per-house, per-type counts.
;
; Records live in UNITS (window 1: units, houses, teams) and WORLD (window
; 2: structures).  Beside each pool the cartridge keeps a "find array" -
; the records in use, in the order they were made, gaps closed - which is
; what every search walks; and for units and structures two linked lists,
; the player's side and the rest, newest first, which is what the target
; finders walk.  The port keeps both, as slot numbers.
;
; Conventions: a routine that makes or finds a record answers HL = the
; record, or HL = 0 with Z set for none.  IX is kept unless stated.

; ------------------------------------------------------------ resetting

; game_reset_state's pool part ($02687A): every pool, list and count
; empty, every record zero.
pools_reset:
        ; units, houses, teams: all of page UNITS below $8000
        ld  hl, UNITS_BASE
        ld  de, UNITS_BASE + 1
        ld  bc, $8000 - UNITS_BASE - 1
        ld  (hl), 0
        ldir
        ld  hl, structs
        ld  de, structs + 1
        ld  bc, S_SIZE * STRUCT_COUNT - 1
        ld  (hl), 0
        ldir
        ld  hl, pool_vars_start
        ld  de, pool_vars_start + 1
        ld  bc, pool_vars_end - pool_vars_start - 1
        ld  (hl), 0
        ldir
        ld  hl, st_markers      ; no structure markers ($0268F2)
        ld  de, st_markers + 1
        ld  bc, STRUCT_COUNT - 1
        ld  (hl), 0
        ldir
        ld  a, $FF
        ld  (unit_head), a
        ld  (unit_head + 1), a
        ld  (struct_head), a
        ld  (struct_head + 1), a
        ; no slot is in a side list ($FF), which list_link and list_unlink
        ; rely on
        ld  hl, unit_lside
        ld  b, UNIT_COUNT
pr_us:  ld  (hl), a
        inc hl
        djnz pr_us
        ld  hl, struct_lside
        ld  b, STRUCT_COUNT
pr_ss:  ld  (hl), a
        inc hl
        djnz pr_ss
        ld  a, 1
        ld  (air_slot_free), a
        ld  a, 70
        ld  (struct_slots_free), a
        ; every team and house record knows its own index
        ld  b, 0
pr_teams:
        ld  a, b
        call team_ptr
        ld  (hl), b
        inc b
        ld  a, b
        cp  TEAM_COUNT
        jr  nz, pr_teams
        ret

; ------------------------------------------------------------- the units

; unit_create ($043326): A = the slot, or $FF for the first free one of
; the type's range; B = the type, C = the house.  -> HL = the unit, or 0.
; Honours the house's cap (S2), the slot ranges, airSlotFree and
; groundSlotsFull, and books the unit everywhere.  Clobbers everything but
; IX, IY.
unit_create:
        ld  (uc_slot), a
        ld  a, b
        ld  (uc_type), a
        ld  a, c
        ld  (uc_house), a
        cp  $FF
        jp  z, uc_none
        ld  a, b
        cp  $FF
        jp  z, uc_none
        ; the cap: a counted type (the side-list byte) that is no winger
        ld  a, (uc_house)
        call house_ptr
        push hl
        pop iy                  ; IY = the house (kept for later)
        ld  a, (uc_type)
        call uc_counted         ; Z: not counted
        jr  z, uc_capok
        ld  l, (iy + H_UNITCOUNT)
        ld  h, (iy + H_UNITCOUNT + 1)
        ld  e, (iy + H_UNITCOUNTMAX)
        ld  d, (iy + H_UNITCOUNTMAX + 1)
        or  a
        sbc hl, de
        jr  c, uc_capok         ; under the cap
        ld  a, (uc_type)        ; the slither (5, the Sandworm) is exempt
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  5
        jr  z, uc_capok
        ld  a, (validate_strict)
        or  a
        jp  z, uc_none
uc_capok:
        ld  a, (uc_type)
        call unit_info
        ld  de, UI_indexStart
        add hl, de
        ld  c, (hl)             ; the range: C..B
        inc hl
        inc hl
        ld  b, (hl)
        ld  a, (uc_slot)
        cp  $FF
        jr  nz, uc_given
        ; the first free slot of the range
        ld  a, c
uc_scan:
        ld  (uc_slot), a
        push bc
        call unit_ptr
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        bit OF_USED, (hl)
        jr  z, uc_found
        ld  a, (uc_slot)
        inc a
        cp  b
        jr  z, uc_scan
        jr  c, uc_scan
        ld  a, $FF              ; none: note the slot as past the range
        ld  (uc_slot), a
uc_found:
        ; a range ending at 10 sets airSlotFree = (slot < 10); ending at
        ; 101, groundSlotsFull = (slot >= 101)
        ld  a, b
        cp  10
        jr  nz, uc_f1
        ld  a, (uc_slot)
        cp  10
        ld  a, 1
        jr  c, uc_f0
        xor a
uc_f0:  ld  (air_slot_free), a
        jr  uc_f2
uc_f1:  cp  101
        jr  nz, uc_f2
        ld  a, (uc_slot)
        cp  101
        ld  a, 0
        jr  c, uc_f3
        inc a
uc_f3:  ld  (ground_slots_full), a
uc_f2:  ld  a, (uc_slot)
        cp  $FF
        jp  z, uc_none
        jr  uc_take
uc_given:
        call unit_ptr
        inc hl
        inc hl
        inc hl
        inc hl
        bit OF_USED, (hl)
        jr  nz, uc_none
uc_take:
        ; a counted type adds one to the house's count
        ld  a, (uc_type)
        call uc_counted
        jr  z, uc_nocount
        inc (iy + H_UNITCOUNT)
        jr  nz, uc_nocount
        inc (iy + H_UNITCOUNT + 1)
uc_nocount:
        ld  a, (uc_slot)
        call unit_ptr
        push hl
        ld  d, h
        ld  e, l
        inc de
        ld  (hl), 0
        ld  bc, U_SIZE - 1
        ldir
        pop hl
        push hl
        pop iy                  ; IY = the unit now
        ld  a, (uc_slot)
        ld  (iy + O_INDEX), a
        ld  a, (uc_type)
        ld  (iy + O_TYPE), a
        ld  (iy + O_LINKED), $FF
        ld  (iy + O_FLAGS), (1 << OF_USED) | (1 << OF_ALLOCATED)
        ld  (iy + O_FLAGS2), 1  ; isUnit
        ld  a, (uc_house)
        ld  (iy + O_HOUSE), a
        ld  (iy + U_ORIGHOUSE), a
        ld  (iy + U_ROUTE), $FF
        ld  a, (uc_type)
        cp  UNIT_SANDWORM
        jr  nz, uc_notworm
        ld  (iy + U_AMOUNT), 3
uc_notworm:
        ; the unit's two spice-search bytes are dropped (S5: they do nothing)
        ld  a, (uc_slot)
        call unit_list_link
        ld  a, (uc_slot)
        ld  hl, unit_find
        ld  de, (unit_find_count)
        ld  d, 0
        add hl, de
        ld  (hl), a
        ld  hl, unit_find_count
        inc (hl)
        ld  a, (uc_house)
        ld  b, a
        ld  a, (uc_type)
        call unit_type_count_addr
        inc (hl)
        push iy
        pop hl
        ld  a, h
        or  l
        ret
uc_none:
        ld  hl, 0
        xor a
        ret

; A = a unit type -> NZ if it is counted: in the side lists ($02056E) and
; not a winger.  Clobbers DE, HL.
uc_counted:
        ld  e, a
        ld  d, 0
        ld  hl, tbl_unit_side_list
        add hl, de
        ld  a, (hl)
        or  a
        ret z
        ld  a, e
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  z, ucc_no
        or  1                   ; NZ
        ret
ucc_no: xor a
        ret

; B = a house, A = a type -> HL = its unitTypeCount byte.  Houses 5 and
; up count in house 0's row, as the cartridge's table does.  Clobbers DE.
unit_type_count_addr:
        ld  e, a
        ld  a, b
        cp  5
        jr  c, utc_1
        xor a
utc_1:  add a, a
        add a, a
        add a, a
        add a, a
        add a, a                ; *32
        add a, e
        ld  e, a
        ld  d, 0
        ld  hl, unit_type_count
        add hl, de
        ret

; B = a house, A = a type -> HL = its structTypeCount byte.
struct_type_count_addr:
        ld  e, a
        ld  a, b
        cp  5
        jr  c, stc_1
        xor a
stc_1:  add a, a
        add a, a
        add a, a
        add a, a
        add a, a
        add a, e
        ld  e, a
        ld  d, 0
        ld  hl, struct_type_count
        add hl, de
        ret

; unit_free ($0434FC): IX = the unit.  Its script reset, every reference
; to it dropped, its counts and lists undone, the record freed.
unit_free:
        xor a
        ld  (ix + O_SCRIPT + SC_PC), a
        ld  (ix + O_SCRIPT + SC_PC + 1), a
        call unit_drop_references
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call unit_type_count_addr
        dec (hl)
        ld  a, (ix + O_INDEX)
        call unit_list_unlink
        ; the Frigate on its way (S6 $FFC260)
        ld  a, (frigate_coming)
        cp  (ix + O_INDEX)
        jp  nz, uf_1
        ld  a, $FF
        ld  (frigate_coming), a
uf_1:   ld  (ix + O_FLAGS), 0
        ld  (ix + O_FLAGS + 1), 0
        ; out of the find array
        ld  a, (ix + O_INDEX)
        ld  hl, unit_find
        ld  bc, unit_find_count
        call find_remove
        ; a counted type: one off its original house's count
        ld  a, (ix + O_TYPE)
        call uc_counted
        jp  z, uf_2
        ld  a, (ix + U_ORIGHOUSE)
        call house_ptr
        ld  de, H_UNITCOUNT
        add hl, de
        ld  a, (hl)
        sub 1
        ld  (hl), a
        inc hl
        ld  a, (hl)
        sbc a, 0
        ld  (hl), a
uf_2:   ld  a, (ix + O_INDEX)
        cp  25
        jp  c, uf_3
        xor a                   ; a ground slot 25-101 is free again
        ld  (ground_slots_full), a
        ret
uf_3:   cp  11
        ret nc
        ld  a, 1                ; an aircraft slot 0-10
        ld  (air_slot_free), a
        ret

; A = a slot, HL = a find array, BC -> its count: take the slot out, gaps
; closed.  Clobbers A, DE, HL.
find_remove:
        push bc
        ld  e, a
        ld  a, (bc)
        or  a
        jr  z, fr_done
        ld  b, a
fr_loop:
        ld  a, (hl)
        cp  e
        jr  z, fr_hit
        inc hl
        djnz fr_loop
        jr  fr_done
fr_hit:
        dec b
        jr  z, fr_last
        ld  d, h
        ld  e, l
        inc hl
        ld  c, b
        ld  b, 0
        ldir
fr_last:
        pop bc
        ld  a, (bc)
        dec a
        ld  (bc), a
        ret
fr_done:
        pop bc
        ret

; ----------------------------------------------------------- side lists
;
; S2: a unit or structure is in the list of the player's side (0) or of
; the rest (1), by house_are_allied(its house, the player).  New ones go
; at the head.  Projectiles and the Frigate ($02056E = 0), slabs and walls
; ($0204D0 = 0) join none.  A list is described by four pointers: the
; side of each slot ($FF none), prev, next, and the two heads.

unit_lists:     DW unit_lside, unit_lprev, unit_lnext, unit_head
struct_lists:   DW struct_lside, struct_lprev, struct_lnext, struct_head

; A = a unit slot: link it.  Clobbers everything but IX, IY.
unit_list_link:
        ld  c, a
        call unit_ptr
        ld  de, tbl_unit_side_list
        push hl
        inc hl
        inc hl
        ld  l, (hl)
        ld  h, 0
        add hl, de
        ld  a, (hl)
        pop hl
        or  a
        ret z
        ld  de, O_HOUSE
        add hl, de
        ld  b, (hl)
        ld  hl, unit_lists
        jr  lists_link_side

; A = a structure slot: link it, one structure slot fewer free.
struct_list_link:
        ld  c, a
        call struct_ptr
        push hl
        inc hl
        inc hl
        ld  l, (hl)
        ld  h, 0
        ld  de, tbl_struct_side_list
        add hl, de
        ld  a, (hl)
        pop hl
        or  a
        ret z
        ld  a, (struct_slots_free)
        dec a
        ld  (struct_slots_free), a
        ld  de, O_HOUSE
        add hl, de
        ld  b, (hl)
        ld  hl, struct_lists
        ; fall through

; HL = the descriptor, C = the slot, B = its house.
lists_link_side:
        push hl
        push bc
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        xor 1                   ; 0 the player's side, 1 the rest
        pop bc
        pop hl
        ; fall through

; HL = the descriptor, C = the slot, A = the list.  A slot already in a
; list leaves it first (linking it twice would make it its own next).
list_link:
        ld  (ll_desc), hl
        ld  (ll_list), a
        ld  a, c
        ld  (ll_slot), a
        xor a
        call ll_elem
        ld  a, (hl)
        cp  $FF
        jr  z, ll_new
        ld  a, (ll_list)
        push af
        ld  hl, (ll_desc)
        ld  a, (ll_slot)
        ld  c, a
        call list_unlink
        pop af
        ld  (ll_list), a
        ld  a, (ll_slot)
        ld  c, a
ll_new:
        ld  a, 0                ; side[slot] = list
        call ll_elem
        ld  a, (ll_list)
        ld  (hl), a
        ld  a, 2                ; prev[slot] = none
        call ll_elem
        ld  (hl), $FF
        call ll_head            ; old = head; head = slot
        ld  a, (hl)
        ld  (ll_other), a
        ld  a, (ll_slot)
        ld  (hl), a
        ld  a, 4                ; next[slot] = old
        call ll_elem
        ld  a, (ll_other)
        ld  (hl), a
        cp  $FF
        ret z
        ld  a, (ll_other)       ; prev[old] = slot
        ld  (ll_slot2), a
        ld  a, 2
        call ll_elem2
        ld  a, (ll_slot)
        ld  (hl), a
        ret

; A = a unit slot: unlink it if it is in a list.
unit_list_unlink:
        ld  c, a
        ld  hl, unit_lists
        jr  list_unlink

; A = a structure slot: unlink it (a structure slot free again).  On no
; side list - a slab freed at placement, a building freed before it was
; placed - there is nothing to unlink and the count does not move (S2:
; structSlotsFree is 70 minus the structures on the side lists).  This
; once went on into list_unlink with HL at the side entry instead of the
; descriptor, and the "unlink" wrote into the stub of whatever bank was
; in window 0: the game died a pass after a slab went down.
struct_list_unlink:
        ld  c, a
        ld  hl, struct_lists
        ld  (ll_desc), hl
        ld  a, c
        ld  (ll_slot), a
        xor a
        call ll_elem
        ld  a, (hl)
        cp  $FF
        ret z
        ld  a, (struct_slots_free)
        inc a
        ld  (struct_slots_free), a
        ld  hl, struct_lists
        ; fall through

; HL = the descriptor, C = the slot.
list_unlink:
        ld  (ll_desc), hl
        ld  a, c
        ld  (ll_slot), a
        xor a                   ; the side
        call ll_elem
        ld  a, (hl)
        cp  $FF
        ret z
        ld  (hl), $FF
        ld  (ll_list), a
        ld  a, 2
        call ll_elem
        ld  a, (hl)
        ld  (ll_prev), a        ; p
        ld  a, 4
        call ll_elem
        ld  a, (hl)
        ld  (ll_other), a       ; n
        ; p == none: head = n, else next[p] = n
        ld  a, (ll_prev)
        cp  $FF
        jr  nz, lu_mid
        call ll_head
        jr  lu_set
lu_mid: ld  (ll_slot2), a
        ld  a, 4
        call ll_elem2
lu_set: ld  a, (ll_other)
        ld  (hl), a
        ; n != none: prev[n] = p
        cp  $FF
        ret z
        ld  (ll_slot2), a
        ld  a, 2
        call ll_elem2
        ld  a, (ll_prev)
        ld  (hl), a
        ret

; A = the offset of an array in the descriptor -> HL = &array[ll_slot]
; (ll_elem) or &array[ll_slot2] (ll_elem2).  Clobbers A, DE.
ll_elem:
        ld  e, a
        ld  a, (ll_slot)
        jr  lle_go
ll_elem2:
        ld  e, a
        ld  a, (ll_slot2)
lle_go: ld  d, 0
        ld  hl, (ll_desc)
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  l, a
        ld  h, 0
        add hl, de
        ret

; HL = &head[ll_list].  Clobbers A, DE.
ll_head:
        ld  hl, (ll_desc)
        ld  de, 6
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, (ll_list)
        ld  l, a
        ld  h, 0
        add hl, de
        ret

; ------------------------------------------------------------ structures

; struct_allocate ($00B906): A = the slot or $FF for the first free of
; 0-69; B = the type.  A slab, 4-slab or wall takes its fixed slot (72,
; 71, 70) whatever is there.  -> HL = the record (cleared, index, type,
; used|allocated, no link, turret facing, in the find array) or 0.
struct_allocate:
        ld  c, a
        ld  a, b
        or  a
        ld  a, 72
        jr  z, sa_fixed
        ld  a, b
        cp  1
        ld  a, 71
        jr  z, sa_fixed
        ld  a, b
        cp  STRUCT_WALL
        ld  a, 70
        jr  z, sa_fixed
        ld  a, c
        cp  $FF
        jr  nz, sa_given
        xor a
sa_scan:
        ld  c, a
        push bc
        call struct_ptr
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        bit OF_USED, (hl)
        ld  a, c
        jr  z, sa_fixed
        inc a
        cp  70
        jr  c, sa_scan
        jr  sa_none
sa_given:
        push bc
        call struct_ptr
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        bit OF_USED, (hl)
        jr  nz, sa_none
        ld  a, c
sa_fixed:
        ld  c, a                ; C = the slot
        push bc
        call struct_ptr
        push hl
        ld  d, h
        ld  e, l
        inc de
        ld  (hl), 0
        ld  bc, S_SIZE - 1
        ldir
        pop hl
        pop bc
        push hl
        ld  (hl), c             ; index
        inc hl
        inc hl
        ld  (hl), b             ; type
        inc hl
        ld  (hl), $FF           ; linkedID
        inc hl
        ld  (hl), (1 << OF_USED) | (1 << OF_ALLOCATED)
        pop hl
        push hl
        ld  de, S_TURRETFACING
        add hl, de
        ld  a, b
        cp  STRUCT_TURRET
        jp  z, sa_turret
        cp  STRUCT_RTURRET
        jp  z, sa_turret
        ld  (hl), $FF
        jr  sa_list
sa_turret:
        ld  (hl), $7F
sa_list:
        ld  a, (struct_find_count)
        or  a
        jr  z, sa_add
        ld  b, a
        ld  hl, struct_find
        ld  a, c
sa_l1:  cp  (hl)                ; a fixed slot taken again is listed
        jr  z, sa_listed        ; already: the array must not grow
        inc hl
        djnz sa_l1
sa_add: ld  hl, struct_find
        ld  de, (struct_find_count)
        ld  d, 0
        add hl, de
        ld  (hl), a
        ld  hl, struct_find_count
        inc (hl)
sa_listed:
        pop hl
        ld  a, h
        or  l
        ret
sa_none:
        ld  hl, 0
        xor a
        ret

; struct_free ($00BA52): IX = the structure.  Script reset, the per-type
; count down, off its side list, flags 0, out of the find array.  (The
; house marker is the renderer's business: it follows the flags.)
struct_free:
        xor a
        ld  (ix + O_SCRIPT + SC_PC), a
        ld  (ix + O_SCRIPT + SC_PC + 1), a
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call struct_type_count_addr
        dec (hl)
        ld  a, (ix + O_INDEX)
        call struct_list_unlink
        ld  (ix + O_FLAGS), 0
        ld  (ix + O_FLAGS + 1), 0
        ld  a, (ix + O_INDEX)
        ld  hl, struct_find
        ld  bc, struct_find_count
        jp  find_remove

; ----------------------------------------------------------------- teams

; team_alloc ($02DEFE): A = the slot, or $FF for the lowest unused.  ->
; HL = the team (cleared, index, used) or 0.
team_alloc:
        cp  $FF
        jr  nz, ta_given
        xor a
ta_scan:
        push af
        call team_ptr
        pop af
        push hl
        inc hl
        inc hl
        ld  c, a
        ld  a, (hl)
        inc hl
        or  (hl)
        ld  a, c
        pop hl
        jr  z, ta_take
        inc a
        cp  TEAM_COUNT
        jr  c, ta_scan
        ld  hl, 0
        xor a
        ret
ta_given:
        push af
        call team_ptr
        pop af
ta_take:
        push hl
        push af
        ld  d, h
        ld  e, l
        inc de
        ld  (hl), 0
        ld  bc, T_SIZE - 1
        ldir
        pop af
        pop hl
        ld  (hl), a             ; index
        inc hl
        inc hl
        ld  (hl), 1             ; used
        dec hl
        dec hl
        push hl
        ld  hl, team_find
        ld  de, (team_find_count)
        ld  d, 0
        add hl, de
        ld  (hl), a
        ld  hl, team_find_count
        inc (hl)
        pop hl
        ld  a, h
        or  l
        ret

; ---------------------------------------------------------------- houses

; house_allocate ($02282A): A = the house.  index, flags = used,
; starportLinkedID = -1, and it joins the house find array.
house_allocate:
        push af                 ; the house (LDIR takes BC)
        call house_ptr
        push hl
        ld  d, h
        ld  e, l
        inc de
        ld  (hl), 0
        ld  bc, H_SIZE - 1
        ldir
        pop iy
        pop af
        ld  c, a
        ld  (iy + H_INDEX), a
        ld  (iy + H_FLAGS), 1 << HF_USED
        ld  (iy + H_STARPORTLINK), $FF
        ld  (iy + H_STARPORTLINK + 1), $FF
        ld  hl, house_find
        ld  de, (house_find_count)
        ld  d, 0
        add hl, de
        ld  (hl), c
        ld  hl, house_find_count
        inc (hl)
        ret

; house_free ($0228BC): A = the house: out of the find array, not used.
house_free:
        push af
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        res HF_USED, (hl)
        pop af
        ld  hl, house_find
        ld  bc, house_find_count
        jp  find_remove

; A = a house -> NZ if it is in use.  Clobbers DE, HL.
house_used:
        cp  HOUSE_COUNT
        jr  nc, hu_no
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        bit HF_USED, (hl)
        ret
hu_no:  xor a
        ret

; ---------------------------------------------------------------- searches
;
; A search state is 3 bytes: house ($FF any), type ($FF any), the position
; in the find array ($FF before the first).  Units and structures that are
; isNotOnMap are passed over unless validate_strict.

; HL = the state, B = house, C = type -> HL = the first unit or 0 (Z).
unit_find_first:
        ld  (hl), b
        inc hl
        ld  (hl), c
        inc hl
        ld  (hl), $FF
        dec hl
        dec hl
        ; fall through

; HL = the state -> HL = the next unit or 0 (Z).  Clobbers A, BC, DE.
unit_find_next:
        push hl
        pop iy
ufn_loop:
        inc (iy + 2)
        ld  a, (unit_find_count)
        ld  b, a
        ld  a, (iy + 2)
        cp  b
        jr  nc, ufn_none
        ld  e, a
        ld  d, 0
        ld  hl, unit_find
        add hl, de
        ld  a, (hl)
        call unit_ptr
        call find_match
        jr  nz, ufn_loop
        ld  a, h
        or  l
        ret
ufn_none:
        ld  (iy + 2), a         ; stays at the end
        ld  hl, 0
        xor a
        ret

; HL = a unit or structure, IY = a search state -> Z if it matches house,
; type and the on-map rule.  Keeps HL.  Clobbers A, DE.
find_match:
        push hl
        ld  de, O_TYPE
        add hl, de
        ld  a, (iy + 1)
        cp  $FF
        jr  z, fm_type_ok
        cp  (hl)
        jr  nz, fm_no
fm_type_ok:
        inc hl
        inc hl                  ; +4, flags
        bit OF_NOTONMAP, (hl)
        jr  z, fm_onmap
        ld  a, (validate_strict)
        or  a
        jr  z, fm_no
fm_onmap:
        pop hl
        push hl
        ld  de, O_HOUSE
        add hl, de
        ld  a, (iy + 0)
        cp  $FF
        jr  z, fm_yes
        cp  (hl)
        jr  nz, fm_no
fm_yes: pop hl
        xor a
        ret
fm_no:  pop hl
        or  1
        ret

; HL = the state, B = house, C = type -> HL = the first structure or 0.
struct_find_first:
        ld  (hl), b
        inc hl
        ld  (hl), c
        inc hl
        ld  (hl), $FF
        dec hl
        dec hl
        ; fall through
struct_find_next:
        push hl
        pop iy
sfn_loop:
        inc (iy + 2)
        ld  a, (struct_find_count)
        ld  b, a
        ld  a, (iy + 2)
        cp  b
        jr  nc, ufn_none
        ld  e, a
        ld  d, 0
        ld  hl, struct_find
        add hl, de
        ld  a, (hl)
        call struct_ptr
        call find_match
        jr  nz, sfn_loop
        ld  a, h
        or  l
        ret

; HL = the state, B = house -> HL = the first team of it (in use) or 0.
team_find_first:
        ld  (hl), b
        inc hl
        inc hl
        ld  (hl), $FF
        dec hl
        dec hl
team_find_next:
        push hl
        pop iy
tfn_loop:
        inc (iy + 2)
        ld  a, (team_find_count)
        ld  b, a
        ld  a, (iy + 2)
        cp  b
        jr  nc, ufn_none
        ld  e, a
        ld  d, 0
        ld  hl, team_find
        add hl, de
        ld  a, (hl)
        call team_ptr
        ld  a, (iy + 0)
        cp  $FF
        jr  z, tfn_yes
        push hl
        ld  de, T_HOUSE
        add hl, de
        cp  (hl)
        pop hl
        jr  nz, tfn_loop
tfn_yes:
        ld  a, h
        or  l
        ret

; ---------------------------------------------------------------- orders

; unit_give_order ($0436A0): IX = the unit, A = the order ($FF nothing).
; Nothing for a unit under Die or Destruct; a Fremen told to Guard Hunts;
; a Harvester leaving a Refinery is unclaimed.  An order that may not
; interrupt given to a unit between squares is queued; otherwise it is the
; order, and the script restarts at the type's entry with variable 0 = it.
unit_give_order:
        cp  $FF
        ret z
        ld  c, a
        ld  a, (ix + U_ACTION)
        cp  ORDER_DESTRUCT
        ret z
        cp  ORDER_DIE
        ret z
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_FREMEN
        jr  nz, ugo_1
        ld  a, c
        cp  ORDER_GUARD
        jr  nz, ugo_1
        ld  c, ORDER_HUNT
ugo_1:  ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, ugo_2
        push bc
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        call ref_struct_ptr
        jr  z, ugo_2p
        inc hl
        inc hl
        ld  a, (hl)
        cp  STRUCT_REFINERY
        call z, obj_var4_clear
ugo_2p: pop bc
ugo_2:  ; may the order interrupt?  (record +0)
        ld  a, c
        call order_record
        ld  a, (hl)
        or  a
        jr  nz, ugo_now
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jr  z, ugo_now
        ld  (ix + U_NEXTACTION), c
        ret
ugo_now:
        cp  2
        ret nc                  ; the record says neither (never happens)
        ld  (ix + U_ACTION), c
        ld  (ix + U_NEXTACTION), $FF
        xor a
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ld  (ix + O_DELAY), a
        ld  (ix + O_DELAY + 1), a
        push ix
        ld  de, O_SCRIPT
        add ix, de
        push bc
        ld  a, EMC_UNIT
        FCALL emc_reset
        pop bc
        ld  (ix + SC_VARS), c
        ld  (ix + SC_VARS + 1), 0
        pop hl
        push hl
        inc hl
        inc hl
        ld  l, (hl)
        ld  h, 0                ; the entry: the unit's type
        ld  a, EMC_UNIT
        FCALL emc_start
        pop ix
        ret

; A = an order -> HL = its tbl_actions record.  Clobbers DE.
order_record:
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl              ; *4
        ld  d, h
        ld  e, l
        add hl, hl              ; *8
        add hl, de              ; *12
        ld  de, tbl_actions
        add hl, de
        ret

; HL = a reference -> HL = the structure it names (if it is a structure
; reference to a used slot), Z if not.  Clobbers A, DE.
ref_struct_ptr:
        ld  a, h
        and $C0
        cp  $80
        jr  nz, rsp_no
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, rsp_no
        call struct_ptr
        ld  a, h
        or  l
        ret
rsp_no: ld  hl, 0
        xor a
        ret

; HL = a reference -> HL = the unit it names (a unit reference), Z if not.
ref_unit_ptr:
        ld  a, h
        and $C0
        cp  $40
        jr  nz, rsp_no
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, rsp_no
        call unit_ptr
        ld  a, h
        or  l
        ret

; HL = a reference -> HL = the unit or structure (ref_object $02E352).
ref_object_ptr:
        push hl
        call ref_unit_ptr
        pop de
        ret nz
        ex  de, hl
        jr  ref_struct_ptr

; ------------------------------------------------------ the claim links
;
; Script variable 4 ($2A of a unit or structure) is what the object has
; claimed or is linked to (S5, S7).

; obj_var4_set ($023D70): IX = the object, HL = the reference.  A
; structure whose type is "busy means something is coming"
; (busyStateIsIncoming, flags bit 4) and has no linked unit goes busy.
obj_var4_set:
        ld  (ix + O_SCRIPT + SC_VARS + 8), l
        ld  (ix + O_SCRIPT + SC_VARS + 9), h
        bit 0, (ix + O_FLAGS2)  ; a unit: nothing more
        ret nz
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 4, (hl)
        ret z
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret nz
        ld  (ix + S_STATE), 1   ; struct_set_state(1)
        ld  (ix + S_STATE + 1), 0
        ret

; obj_var4_clear ($023E04): IX = the object: its link broken both ways.
; The cartridge then compares the other end's +$5C (targetMove) with its
; +$2A and clears +$5C if they match ($023E52-$023E64) - but only after
; obj_var4_zero has already zeroed that +$2A ($023E2E), so the clause can
; only ever clear a +$5C that is already 0.  The port leaves it out: done
; before the zeroing, as it once was here, it cleared targets the Mega
; Drive keeps.
obj_var4_clear:
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        ld  a, h
        or  l
        push af
        push hl
        call ref_object_ptr
        ex  (sp), hl            ; stack = the other end, HL = the reference
        ld  (ov_ref), hl
        pop hl
        jr  z, ovc_self
        push hl
        pop iy                  ; IY = the other end
        ld  (iy + O_SCRIPT + SC_VARS + 8), 0
        ld  (iy + O_SCRIPT + SC_VARS + 9), 0
        push ix
        push iy
        pop ix
        call ovc_idle
        pop ix
ovc_self:
        pop af
        ld  (ix + O_SCRIPT + SC_VARS + 8), 0
        ld  (ix + O_SCRIPT + SC_VARS + 9), 0
        ; fall through

; obj_var4_zero ($023E9E, which the cartridge's obj_var4_clear calls for
; each end): IX = an object whose variable 4 is gone.  A structure whose
; type is busyStateIsIncoming (a Starport, a Refinery) with no linked unit
; goes idle - which is what puts a Starport back to 0 after its order, so
; that its lights (struct_animate $00D77A) run only while the Frigate is
; on its way (the link obj_var4_set makes).  Keeps IX, IY.
ovc_idle:
        bit 0, (ix + O_FLAGS2)  ; a unit: nothing more
        ret nz
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 4, (hl)
        ret z
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret nz
        ld  (ix + S_STATE), 0   ; struct_set_state(0)
        ld  (ix + S_STATE + 1), 0
        ret

; ----------------------------------------------------- dropping references

; unit_drop_references ($04900E): IX = a unit going.  Its own claim is
; broken both ways (obj_var4_clear - so a Refinery a Harvester claimed on
; its way home is free again once it docks, and releases it); every
; unit's targetAttack and targetMove naming it are cleared (a Harvester's
; +$5A is its sprite and is left) and a claim on it broken; every
; turret's target (variable 2), every team's target, and its team
; membership.
unit_drop_references:
        call obj_var4_clear
        ld  e, (ix + O_INDEX)
        ld  d, REF_UNIT >> 8
        ld  (udr_ref), de
        ; the units
        ld  a, (unit_find_count)
        or  a
        jr  z, udr_structs
        ld  b, a
        ld  hl, unit_find
udr_u:  push bc
        push hl
        ld  a, (hl)
        call unit_ptr
        push hl
        pop iy
        ld  de, (udr_ref)
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, udr_u1
        ld  a, (iy + U_TARGETATTACK)
        cp  e
        jr  nz, udr_u1
        ld  a, (iy + U_TARGETATTACK + 1)
        cp  d
        jr  nz, udr_u1
        ld  (iy + U_TARGETATTACK), 0
        ld  (iy + U_TARGETATTACK + 1), 0
udr_u1: ld  a, (iy + U_TARGETMOVE)
        cp  e
        jr  nz, udr_u2
        ld  a, (iy + U_TARGETMOVE + 1)
        cp  d
        jr  nz, udr_u2
        ld  (iy + U_TARGETMOVE), 0
        ld  (iy + U_TARGETMOVE + 1), 0
udr_u2: ld  a, (iy + O_SCRIPT + SC_VARS + 8)
        cp  e
        jr  nz, udr_u3
        ld  a, (iy + O_SCRIPT + SC_VARS + 9)
        cp  d
        jr  nz, udr_u3
        push ix
        push iy
        pop ix
        call obj_var4_clear
        pop ix
udr_u3: pop hl
        inc hl
        pop bc
        djnz udr_u
udr_structs:
        ld  a, (struct_find_count)
        or  a
        jr  z, udr_teams
        ld  b, a
        ld  hl, struct_find
udr_s:  push bc
        push hl
        ld  a, (hl)
        call struct_ptr
        push hl
        pop iy
        ld  a, (iy + O_TYPE)    ; only a turret's (type 15, 16)
        sub STRUCT_TURRET
        cp  2
        jr  nc, udr_s1
        ld  de, (udr_ref)
        ld  a, (iy + O_SCRIPT + SC_VARS + 4)
        cp  e
        jr  nz, udr_s1
        ld  a, (iy + O_SCRIPT + SC_VARS + 5)
        cp  d
        jr  nz, udr_s1
        ld  (iy + O_SCRIPT + SC_VARS + 4), 0
        ld  (iy + O_SCRIPT + SC_VARS + 5), 0
udr_s1: pop hl
        inc hl
        pop bc
        djnz udr_s
udr_teams:
        ld  b, 0
udr_t:  ld  a, b
        push bc
        call team_ptr
        push hl
        pop iy
        ld  de, (udr_ref)
        ld  a, (iy + T_TARGET)
        cp  e
        jr  nz, udr_t1
        ld  a, (iy + T_TARGET + 1)
        cp  d
        jr  nz, udr_t1
        ld  (iy + T_TARGET), 0
        ld  (iy + T_TARGET + 1), 0
udr_t1: pop bc
        inc b
        ld  a, b
        cp  TEAM_COUNT
        jr  nz, udr_t
        ; out of its team
        ld  a, (ix + U_TEAM)
        or  a
        ret z
        dec a
        call team_ptr
        push hl
        pop iy
        ld  a, (iy + T_MEMBERS)
        or  a
        jr  z, udr_t2
        dec (iy + T_MEMBERS)
udr_t2: ld  (ix + U_TEAM), 0
        ret

; B = a house, A = a structure type: its count + 1.
struct_type_count_inc:
        call struct_type_count_addr
        inc (hl)
        ret

; ------------------------------------------------------------- spawning

; unit_spawn ($0468B2): A = the slot or $FF, B = the type, C = the house,
; D = the facing, arg_pos = the position ($FFFF $FFFF: none, off the map).
; -> HL = the unit, or 0 (Z).  unit_create, then: hull and turret facing,
; speed 0, full health, the position and a home, no route, script
; stopped, order Guard; a tracked unit may wear out; a winger speed 255;
; with a position it goes on the map (freed if it cannot stand there) and
; takes its type's default order (+$28 the player's, +$4A the rest's).
unit_spawn:
        ld  e, a
        ld  a, d
        ld  (us_facing), a
        ld  a, e
        FCALL unit_create
        ret z
        push hl
        pop ix
        ld  a, (us_facing)
        ld  (ix + U_OR0_TARGET), a
        ld  (ix + U_OR0_CURRENT), a
        ld  (ix + U_OR1_TARGET), a
        ld  (ix + U_OR1_CURRENT), a
        xor a
        ld  (ix + U_OR0_SPEED), a
        ld  (ix + U_OR1_SPEED), a
        FCALL unit_set_speed
        ld  a, (ix + O_TYPE)
        call unit_info
        push hl
        pop iy                  ; IY = the type
        ld  a, (iy + UI_hitpoints)
        ld  (ix + O_HP), a
        ld  a, (iy + UI_hitpoints + 1)
        ld  (ix + O_HP + 1), a
        ld  hl, arg_pos
        ld  a, (hl)
        inc hl
        and (hl)
        inc hl
        and (hl)
        inc hl
        and (hl)
        inc a
        ld  (us_offmap), a      ; 0: no position
        push ix
        pop de
        ld  hl, O_POS_Y
        add hl, de
        ex  de, hl
        ld  hl, arg_pos
        ld  bc, 4
        ldir
        xor a
        ld  (ix + U_ORIGIN), a
        ld  (ix + U_ORIGIN + 1), a
        ld  (ix + U_ROUTE), $FF
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ld  a, (us_offmap)
        or  a
        jr  z, us_nohome
        call unit_choose_home
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        push hl
        push ix
        pop de
        ld  hl, U_PRELAST_Y
        add hl, de
        ex  de, hl
        pop hl
        push hl
        ld  bc, 4
        ldir
        pop hl
        ld  bc, 4
        ldir                    ; targetPreLast and targetLast
us_nohome:
        xor a
        ld  (ix + U_FIREDELAY), a
        ld  (ix + U_WOBBLE), a
        ld  (ix + U_SPRITEOFS), a
        ld  (ix + U_ANIMTIMER), a
        ld  (ix + U_ANIMTIMER + 1), a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  (ix + U_AMOUNT), a
        ld  (ix + O_LINKED), $FF
        ld  (ix + U_NEXTACTION), $FF
        ld  (ix + U_ACTION), ORDER_GUARD
        ld  (ix + U_DISTDEST), $FF
        ld  (ix + U_DISTDEST + 1), $7F
        ld  (ix + O_DELAY), a
        ld  (ix + O_DELAY + 1), a
        ld  (ix + O_SCRIPT + SC_PC), a
        ld  (ix + O_SCRIPT + SC_PC + 1), a
        set OF_ALLOCATED, (ix + O_FLAGS)
        call us_info            ; IY again: unit_choose_home's search
        ; a tracked unit wears out if random < the house's degrading chance
        ld  a, (iy + UI_movementType)
        cp  1
        jr  nz, us_nodeg
        call random
        ld  c, a
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_degradingChance
        add hl, de
        ld  a, c
        cp  (hl)
        jr  nc, us_nodeg
        set OF_DEGRADES - 8, (ix + O_FLAGS + 1)
us_nodeg:
        ld  a, 1
        ld  (us_ok), a
        ld  a, (iy + UI_movementType)
        cp  4
        jr  nz, us_ground
        ld  a, 255
        FCALL unit_set_speed
        jr  us_place
us_ground:
        ld  a, (us_offmap)
        or  a
        jr  z, us_place
        call unit_blocked_here
        xor 1
        ld  (us_ok), a
        call us_info            ; IY again: the unit found there
us_place:
        ld  a, (us_offmap)
        or  a
        jr  nz, us_on
        set OF_NOTONMAP, (ix + O_FLAGS)
        jr  us_done
us_on:  ld  a, (us_ok)
        or  a
        jr  nz, us_on2
        call unit_free
        ld  hl, 0
        xor a
        ret
us_on2: ld  a, 1
        call unit_update_map
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, (iy + UI_actionPlayer)
        jr  z, us_order
        ld  a, (iy + UI_actionAI)
us_order:
        call unit_give_order
us_done:
        push ix
        pop hl
        ld  a, h
        or  l
        ret
; IY = the type record of the unit at IX (unit_choose_home and
; unit_blocked_here use IY for their own records).
us_info:
        ld  a, (ix + O_TYPE)
        call unit_info
        push hl
        pop iy
        ret

; unit_blocked_here ($046F68): IX = a unit -> A = 1 if it cannot stand
; where it is: the ground forbids its movement type; a unit is there
; (unless an enemy soldier under a tracked vehicle); a structure is.  The
; Sandworm and flyers never are blocked.
unit_blocked_here:
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  (ubh_sq), hl
        call map_landscape
        call landscape_info
        ld  de, LS_movementSpeed
        add hl, de
        ld  a, (ix + O_TYPE)
        push hl
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  e, (hl)
        ld  d, 0
        pop hl
        add hl, de
        ld  a, (hl)
        or  a
        jr  z, ubh_yes
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, ubh_no
        ld  a, e
        cp  4
        jr  z, ubh_no
        ld  (ubh_mt), a
        ld  hl, (ubh_sq)
        call map_unit_at
        jr  z, ubh_struct
        push ix
        pop de
        or  a
        sbc hl, de
        add hl, de
        jr  z, ubh_struct
        push hl
        pop iy
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jr  nz, ubh_yes
        ld  a, (ubh_mt)
        cp  1
        jr  nz, ubh_yes
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, ubh_yes
ubh_struct:
        ld  hl, (ubh_sq)
        call map_flags
        bit MF_STRUCT, a
        jr  nz, ubh_yes
ubh_no: xor a
        ret
ubh_yes:
        ld  a, 1
        ret

; unit_choose_home ($048DAE): IX = a unit.  A Harvester's home is the
; nearest Refinery of its house in state 1, else the nearest at all;
; anything else's is the square it stands on.  -> A = 1 if it had one.
unit_choose_home:
        ld  a, (ix + U_ORIGIN)
        or  (ix + U_ORIGIN + 1)
        ld  (uch_had), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, uch_square
        ld  a, 1
        call uch_search
        jr  nz, uch_found
        xor a
        call uch_search
        jr  z, uch_ret
uch_found:
        ld  l, a
        ld  h, REF_STRUCT >> 8
        jr  uch_set
uch_square:
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        call ref_make_square
uch_set:
        ld  (ix + U_ORIGIN), l
        ld  (ix + U_ORIGIN + 1), h
uch_ret:
        ld  a, (uch_had)
        or  a
        ret z
        ld  a, 1
        ret

; A = 1: only Refineries in state 1; 0: any.  -> NZ and A = the nearest
; one's slot, Z none.
uch_search:
        ld  (uch_state1), a
        ld  a, $FF
        ld  (uch_best), a
        ld  hl, 0
        ld  (uch_bestd), hl
        ld  hl, uch_search_state
        ld  b, (ix + O_HOUSE)
        ld  c, STRUCT_REFINERY
        call struct_find_first
ucs_loop:
        jr  z, ucs_done
        push hl
        pop iy
        ld  a, (uch_state1)
        or  a
        jr  z, ucs_any
        ld  a, (iy + S_STATE)
        dec a
        or  (iy + S_STATE + 1)
        jr  nz, ucs_next
ucs_any:
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        push ix
        pop de
        ld  a, e
        add a, O_POS_Y
        ld  e, a
        jr  nc, ucs_1
        inc d
ucs_1:  call tile_distance
        ld  de, (uch_bestd)
        ld  a, d
        or  e
        jr  z, ucs_take
        or  a
        sbc hl, de
        add hl, de
        jr  nc, ucs_next
ucs_take:
        ld  (uch_bestd), hl
        ld  a, (iy + O_INDEX)
        ld  (uch_best), a
ucs_next:
        ld  hl, uch_search_state
        call struct_find_next
        jr  ucs_loop
ucs_done:
        ld  a, (uch_best)
        cp  $FF
        jr  z, ucs_none
        or  a
        ret nz
        or  1                   ; slot 0: still "found"
        ld  a, 0
        ret
ucs_none:
        xor a
        ret

; unit_remove ($04706A): IX = the unit.  Its marks on the nine squares
; round its square are cleared, it is deselected, lifted off the map,
; unseen by every house, and freed.
unit_remove:
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  (ur_sq), hl
        ld  hl, tbl_layout_around
        ld  b, 9
ur_loop:
        push bc
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push hl
        ld  hl, (ur_sq)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        call map_flags
        bit MF_UNIT, a
        jr  z, ur_next
        push hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (ix + O_INDEX)
        inc a
        cp  (hl)
        pop hl
        jr  nz, ur_next
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  (hl), 0
        ld  a, h
        xor (MAP_INDEX ^ MAP_FLAGS) >> 8
        ld  h, a
        res MF_UNIT, (hl)
ur_next:
        pop hl
        pop bc
        djnz ur_loop
        set OF_ALLOCATED, (ix + O_FLAGS)
        set OF_BULLETBIG, (ix + O_FLAGS)
        ld  a, (unit_selected)
        cp  (ix + O_INDEX)
        jr  nz, ur_1
        ld  a, $FF
        ld  (unit_selected), a
ur_1:   xor a
        call unit_update_map
        ld  a, $FF
        FCALL unit_unseen_by_houses
        jp  unit_free

us_facing:      DB 0
us_offmap:      DB 0
us_ok:          DB 0
ubh_sq:         DW 0
ubh_mt:         DB 0
uch_had:        DB 0
uch_state1:     DB 0
uch_best:       DB 0
uch_bestd:      DW 0
uch_search_state: DS 3
ur_sq:          DW 0
