; scen.asm - bank SCEN: loading a mission (S9 scen_load $016098 and
; game_prepare $026578) and its battlefield (S8 map_load $01B1D4).
;
; scen_load: A = the player's house (0 Harkonnen, 1 Atreides, 2 Ordos),
; B = the mission 1-9.  Everything of the last battle is reset, the
; mission's records are read in the cartridge's order, and the battle is
; made ready to start.  The deliberate differences from the cartridge are
; S9's "fix" rows: only the houses the file names are allocated, and a
; reinforcement's slot is its key - 1.

scen_load:
        ld  (sl_house), a
        ld  a, b
        ld  (sl_mission), a
        ld  (scenario_id), a    ; (set again after the reset below)
        ; the record stream, out of its page into our buffer
        ld  a, $$tbl_missions
        call map_w1
        ld  a, (sl_house)
        ld  b, a
        add a, a
        add a, a
        add a, a
        add a, b                ; house * 9
        ld  b, a
        ld  a, (scenario_id)
        dec a
        add a, b
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de              ; * 3
        ld  de, tbl_missions
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        call map_w1
        ex  de, hl
        ld  de, scen_buf
        ld  bc, SCEN_BUF_SIZE
        ldir
        call map_game
        ; no blooms until this file names some: the pointer is into
        ; scen_buf, which every mission is read from, so one left from the
        ; mission before pointed into this one's records - after a win the
        ; next mission had a bloom under every unit (its positions)
        ld  hl, 0
        ld  (scen_blooms), hl
        ; reset everything
        FCALL pools_reset
        call scen_reset_state
        ld  a, (sl_mission)
        ld  (scenario_id), a
        dec a
        ld  (campaign_id), a
        call scen_clear_map
        ld  a, 1
        ld  (validate_strict), a
        ; the records
        ld  hl, scen_buf
sl_loop:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, d
        and e
        inc a
        jr  z, sl_done          ; $FFFF: the end
        ld  (sl_ptr), hl
        ld  a, e
        ld  (sl_key), a
        ld  a, d
        cp  11
        jr  nc, sl_skip_bad
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, sl_sections
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call sl_jump
        ld  hl, (sl_ptr)
        jr  sl_loop
sl_skip_bad:
        ; a section the cartridge would not know: stop reading
sl_done:
        call scen_after_records
        call game_prepare
        xor a
        ld  (validate_strict), a
        ret

sl_jump:
        jp  (hl)

sl_sections:
        DW  sr_basic, sr_map, sr_house, sr_house, sr_house, sr_house
        DW  sr_choam, sr_team, sr_unit, sr_struct, sr_reinf

; The next word of the record -> HL (and sl_ptr moves on).  Keeps BC, DE.
sl_word:
        push de
        ld  hl, (sl_ptr)
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  (sl_ptr), hl
        ex  de, hl
        pop de
        ret

; A square from the file -> HL, with the 32 x 32 map's offset (1040 =
; 16 rows and 16 columns; $0714A0) added.
sl_square:
        call sl_word
        ld  a, (map_scale)
        or  a
        ret z
        ld  de, 1040
        add hl, de
        ret

; ------------------------------------------------------------- [BASIC]
sr_basic:
        ld  a, (sl_key)
        cp  3
        jr  nc, srb_1
        ; a picture name: a length word, then that many bytes - skipped
        call sl_word
        ex  de, hl
        ld  hl, (sl_ptr)
        add hl, de
        ld  (sl_ptr), hl
        ret
srb_1:  push af
        call sl_word
        pop af
        cp  3
        ret z                   ; Timeout: read, never used
        cp  4
        jr  nz, srb_2
        ld  a, l
        ld  (map_scale), a
        ret
srb_2:  cp  5
        jr  nz, srb_3
        call srb_offset
        ld  (cursor_pos), hl
        ret
srb_3:  cp  6
        jr  nz, srb_4
        call srb_offset
        ld  (tactical_pos), hl
        ret
srb_4:  cp  7
        jr  nz, srb_5
        ld  a, l
        ld  (lose_flags), a     ; key 7: the PC's LoseFlags - "did we win?"
        ret
srb_5:  cp  8
        ret nz
        ld  a, l
        ld  (win_flags), a      ; key 8: the PC's WinFlags - "is it over?"
        ret
srb_offset:
        ld  a, (map_scale)
        or  a
        ret z
        ld  de, 1040
        add hl, de
        ret

; --------------------------------------------------------------- [MAP]
sr_map:
        ld  a, (sl_key)
        cp  'S'
        jr  z, srm_seed
        cp  'B'
        jr  z, srm_bloom
        ; 'F' (Field): kept by the cartridge, never read - skipped
srm_skiplist:
        call sl_word            ; the count
        add hl, hl
        ex  de, hl
        ld  hl, (sl_ptr)
        add hl, de
        ld  (sl_ptr), hl
        ret
srm_bloom:
        ; remember where the list is; the blooms go down after the file
        ld  hl, (sl_ptr)
        ld  (scen_blooms), hl
        jr  srm_skiplist
srm_seed:
        call sl_word
        ld  a, l
        ld  (map_seed), a
        call map_load
        ; the view: the cursor less 4 columns and 3 rows
        ld  hl, (cursor_pos)
        ld  de, -(3 * 64 + 4)
        add hl, de
        ld  (tactical_pos), hl
        ret

; ------------------------------------------------------------ a house
sr_house:
        ld  hl, (sl_ptr)
        dec hl
        ld  a, (hl)             ; the tag's high byte: 2-5
        sub 2
        ld  e, a
        ld  d, 0
        ld  hl, sl_section_house
        add hl, de
        ld  a, (hl)
        ld  (sl_h), a
        FCALL house_used
        jr  nz, srh_1
        ld  a, (sl_h)
        FCALL house_allocate
srh_1:  call sl_word
        push hl
        ld  a, (sl_h)
        call house_ptr
        push hl
        pop iy
        pop hl
        ld  a, (sl_key)
        cp  'Q'
        jr  nz, srh_2
        ld  (iy + H_QUOTA), l
        ld  (iy + H_QUOTA + 1), h
        ret
srh_2:  cp  'C'
        jr  nz, srh_3
        ld  (iy + H_CREDITS), l
        ld  (iy + H_CREDITS + 1), h
        ld  a, h
        rla
        sbc a, a                ; a signed word, extended
        ld  (iy + H_CREDITS + 2), a
        ld  (iy + H_CREDITS + 3), a
        ret
srh_3:  cp  'B'
        jr  nz, srh_4
        ld  a, l
        cp  'H'
        jr  nz, srh_ai
        set HF_HUMAN, (iy + H_FLAGS)
        ld  a, (sl_h)
        ld  (player_house), a
        ld  l, (iy + H_CREDITS)
        ld  h, (iy + H_CREDITS + 1)
        ld  (credits_no_silo), hl
        ret
srh_ai: ld  a, (sl_h)
        ld  (enemy_house), a
        ret
srh_4:  cp  'M'
        ret nz
        ld  (iy + H_UNITCOUNTMAX), l
        ld  (iy + H_UNITCOUNTMAX + 1), h
        ret

sl_section_house:
        DB  0, 1, 2, 4          ; $0714A4: sections 2-5 are these houses

; ------------------------------------------------------------- [CHOAM]
sr_choam:
        call sl_word
        ld  a, (sl_key)
        cp  27
        ret nc
        add a, a
        ld  e, a
        ld  d, 0
        ex  de, hl
        ld  bc, starport_available
        add hl, bc
        ld  (hl), e
        inc hl
        ld  (hl), d
        ret

; ------------------------------------------------------------- [TEAMS]
; house, behaviour letter, movement letter, min, max (scen_read_team).
sr_team:
        call sl_word
        ld  a, l
        ld  (st_house), a
        call sl_word
        ld  a, l
        ld  hl, tbl_team_actions
        ld  b, 5
        call st_letter
        ret c                   ; no match: the team is dropped
        ld  (st_action), a
        call sl_word
        ld  a, l
        ld  hl, tbl_movement_letters
        ld  b, 6
        call st_letter
        ret c
        ld  (st_move), a
        call sl_word
        ld  a, l
        ld  (st_min), a
        call sl_word
        ld  a, l
        ld  (st_max), a
        ; team_create ($02DFB4)
        ld  a, $FF
        FCALL team_alloc
        ret z
        push hl
        pop ix
        ld  a, (st_house)
        ld  (ix + T_HOUSE), a
        ld  a, (st_action)
        ld  (ix + T_ACTION), a
        ld  (ix + T_ACTIONSTART), a
        ld  a, (st_move)
        ld  (ix + T_MOVETYPE), a
        ld  a, (st_min)
        ld  (ix + T_MINMEMBERS), a
        ld  a, (st_max)
        ld  (ix + T_MAXMEMBERS), a
        ld  (ix + T_DELAY), 0
        ld  (ix + T_DELAY + 1), 0
        ld  de, T_SCRIPT
        add ix, de
        ld  a, (st_action)
        ld  l, a
        ld  h, 0
        ld  a, EMC_TEAM
        FCALL emc_start
        ret

; A = a letter, HL = the table, B = its length -> A = the first match's
; index, carry set if none.
st_letter:
        ld  c, 0
stl_l:  cp  (hl)
        jr  z, stl_hit
        inc hl
        inc c
        djnz stl_l
        scf
        ret
stl_hit:
        ld  a, c
        or  a
        ret

; ------------------------------------------------------------- [UNITS]
; house, type, health, square, facing, order (scen_read_unit $0166CA).
sr_unit:
        call sl_word
        ld  a, l
        ld  (su_house), a
        call sl_word
        ld  a, l
        ld  (su_type), a
        call sl_word
        ld  (su_health), hl
        call sl_square
        ld  (su_square), hl
        call sl_word
        ld  a, l
        ld  (su_facing), a
        call sl_word
        ld  a, l
        ld  (su_order), a
        ; the lowest free slot of the type's range; none: not made
        ld  a, (su_type)
        ld  b, a
        ld  a, (su_house)
        ld  c, a
        ld  a, $FF
        FCALL unit_create
        ret z
        push hl
        pop ix
        ; hit points: the type's * health >> 8 (math_mul_shr8)
        ld  a, (su_type)
        call unit_info
        ld  de, UI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, (su_health)
        call mul_shr8
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ; the square's centre
        ld  hl, (su_square)
        push ix
        pop de
        ld  a, e
        add a, O_POS_Y
        ld  e, a
        jr  nc, su_1
        inc d
su_1:   call square_centre
        ; facing: hull and turret, current and target
        ld  a, (su_facing)
        ld  (ix + U_OR0_CURRENT), a
        ld  (ix + U_OR0_TARGET), a
        ld  (ix + U_OR1_CURRENT), a
        ld  (ix + U_OR1_TARGET), a
        ld  a, (su_order)
        ld  (ix + U_ACTION), a
        ld  (ix + U_NEXTACTION), $FF
        ld  a, (su_order)
        FCALL unit_give_order
        ; seen by its own house
        ld  a, (su_house)
        call house_bit
        ld  (ix + O_SEEN), a
        ld  a, 1
        FCALL unit_update_map
        ret

; A = a house -> A = 1 << house.
house_bit:
        ld  b, a
        inc b
        xor a
        scf
hb_l:   rla
        djnz hb_l
        ret

; -------------------------------------------------------- [STRUCTURES]
sr_struct:
        ld  a, (sl_key)
        cp  'G'
        jr  z, srs_gen
        ; index, house, type, health, square (the health is dropped: a
        ; mission's structures start whole)
        call sl_word            ; the index (a slot): read and dropped -
        ld  a, l                ; the cartridge asks struct_create for -1
        ld  (ss_index), a       ; ($0168C4 moveq #-1,d6), as below
        call sl_word
        ld  a, l
        ld  (ss_house), a
        call sl_word
        ld  a, l
        ld  (ss_type), a
        call sl_word            ; health: read and dropped
        call sl_square
        ld  (ss_square), hl
        ; only where no structure stands yet
        call map_flags_scen
        bit MF_STRUCT, a
        ret nz
        ld  b, $FF              ; the first free slot
        ld  a, (ss_type)
        ld  c, a
        ld  a, (ss_house)
        ld  d, a
        ld  hl, (ss_square)
        FCALL struct_create
        ret z
        push hl
        pop ix
        ; no decay, idle, and at full health whatever the placing found
        ; under it - struct_place takes some off, and sets decay, for
        ; squares off concrete ($0168DE-$0168FC)
        res OF_DEGRADES - 8, (ix + O_FLAGS + 1)
        ld  (ix + S_STATE), 0
        ld  (ix + S_STATE + 1), 0
        ld  a, (ix + S_HPMAX)
        ld  (ix + O_HP), a
        ld  a, (ix + S_HPMAX + 1)
        ld  (ix + O_HP + 1), a
        ; the player's Construction Yard starts upgraded from campaign 6
        ; on ($01693E)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, srs_1
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, srs_1
        ld  a, (campaign_id)
        cp  6
        jr  c, srs_1
        ld  (ix + S_UPGRADELEVEL), 1
srs_1:
        ; a Refinery owes its house a Harvester
        ld  a, (ss_type)
        cp  STRUCT_REFINERY
        ret nz
        ld  a, (ss_house)
        call house_ptr
        ld  de, H_HARVINCOMING
        add hl, de
        inc (hl)
        ret

; 'G': square, house, type - a wall or a slab, straight onto the map.
srs_gen:
        call sl_square
        ld  (ss_square), hl
        call sl_word
        ld  a, l
        ld  (ss_house), a
        call sl_word
        ld  a, l
        ld  (ss_type), a
        ld  hl, (ss_square)
        ld  a, (ss_type)
        cp  STRUCT_WALL
        ld  a, (ss_house)
        jr  z, srs_wall
        FCALL map_place_slab
        ret
srs_wall:
        FCALL map_place_wall
        ret

map_flags_scen:
        ld  hl, (ss_square)
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        ret

; ---------------------------------------------------- [REINFORCEMENTS]
; house, type, where (6 Enemybase, 7 Homebase), delay | '+' repeat.
sr_reinf:
        call sl_word
        ld  a, l
        ld  (sr_h), a
        call sl_word
        ld  a, l
        ld  (sr_t), a
        call sl_word
        ld  (sr_where), hl
        call sl_word
        ld  (sr_when), hl
        ; the slot: the key, counted from 1 in the file; the port from 0
        ld  a, (sl_key)
        or  a
        ret z
        dec a
        cp  16
        ret nc
        ld  (sr_slot), a
        ; the unit, made off the map now: it counts towards its house
        ld  a, (sr_t)
        ld  b, a
        ld  a, (sr_h)
        ld  c, a
        ld  a, $FF
        FCALL unit_create
        ret z
        push hl
        pop ix
        set OF_NOTONMAP, (ix + O_FLAGS)
        ld  a, (sr_t)
        call unit_info
        ld  de, UI_hitpoints
        add hl, de
        ld  a, (hl)
        ld  (ix + O_HP), a
        inc hl
        ld  a, (hl)
        ld  (ix + O_HP + 1), a
        ld  (ix + U_ACTION), ORDER_GUARD
        ld  (ix + U_NEXTACTION), $FF
        ld  (ix + O_LINKED), $FF
        ; the record: unit, where, time left, time between, repeat
        ld  a, (sr_slot)
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        add hl, hl              ; * 10
        ld  de, reinforcements
        add hl, de
        ld  a, (ix + O_INDEX)
        ld  (hl), a
        inc hl
        ld  (hl), 0
        inc hl
        ld  de, (sr_where)
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ; delay * 6 + 1 in reinforcement ticks, both counters
        ld  a, (sr_when + 1)    ; the delay is the high byte
        push hl
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de
        add hl, hl
        inc hl
        ex  de, hl
        pop hl
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  a, (sr_when)
        cp  '+'
        ld  a, 1
        jr  z, srr_rep
        xor a
srr_rep:
        ld  (hl), a
        inc hl
        ld  (hl), 0
        ret

; ------------------------------------------------------- after the file

scen_after_records:
        ; the blooms: the ground becomes bloomIcon, the overlay kept
        ld  hl, (scen_blooms)
        ld  a, h
        or  l
        jr  z, sar_1
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        inc hl
sar_b:  ld  a, b
        or  c
        jr  z, sar_1
        push bc
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push hl
        ex  de, hl
        ld  a, (map_scale)
        or  a
        jr  z, sar_b1
        ld  de, 1040
        add hl, de
sar_b1: ld  de, BLOOM_ICON
        FCALL map_set_ground
        pop hl
        pop bc
        dec bc
        jr  sar_b
sar_1:  ; the structure counts start at 1, so no end can be found before
        ; the structure loop has counted
        ld  a, 1
        ld  (structs_player), a
        ld  (structs_other), a
        ; harvestersIncoming - 1 for houses 0-2
        ld  b, 0
sar_hv: ld  a, b
        push bc
        FCALL house_used
        jr  z, sar_hv1
        ld  a, b
        call house_ptr
        ld  de, H_HARVINCOMING
        add hl, de
        ld  a, (hl)
        or  a
        jr  z, sar_hv1
        dec (hl)
sar_hv1:
        pop bc
        inc b
        ld  a, b
        cp  3
        jr  nz, sar_hv
        ; the clock
        ld  hl, (timer_game)
        ld  (mission_start_time), hl
        ld  hl, (timer_game + 2)
        ld  (mission_start_time + 2), hl
        ret

; game_prepare ($026578), the parts that exist so far: the fog lifted round
; the player's units and structures, every structure's script started.
game_prepare:
        ; units: each of the player's lifts the fog round it by its sight
        ld  a, (unit_find_count)
        or  a
        jr  z, gp_structs
        ld  b, a
        ld  hl, unit_find
gp_u:   push bc
        push hl
        ld  a, (hl)
        call unit_ptr
        push hl
        pop ix
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, gp_u1
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_sight
        add hl, de
        ld  c, (hl)
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        FCALL map_unfog_radius
gp_u1:  pop hl
        inc hl
        pop bc
        djnz gp_u
gp_structs:
        ld  a, (struct_find_count)
        or  a
        ret z
        ld  b, a
        ld  hl, struct_find
gp_s:   push bc
        push hl
        ld  a, (hl)
        call struct_ptr
        push hl
        pop ix
        ; its script, at its type's entry
        push ix
        ld  de, O_SCRIPT
        add ix, de
        ld  l, (ix + O_TYPE - O_SCRIPT)
        ld  h, 0
        ld  a, EMC_BUILD
        FCALL emc_start
        pop ix
        ; the player's lift the fog
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, gp_s1
        call scen_struct_unfog
gp_s1:  pop hl
        inc hl
        pop bc
        djnz gp_s
        ret

; struct_remove_fog ($01086C): IX = a structure: the fog round its centre
; (position + tbl_layout_centre[layout]) by its sight.
scen_struct_unfog:
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  a, (ix + O_TYPE)
        call struct_info
        push hl
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_centre
        add hl, de
        ld  de, arg_pos
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
        pop hl
        ld  de, SI_sight
        add hl, de
        ld  c, (hl)
        ld  hl, arg_pos
        FCALL map_unfog_radius
        ret

; ------------------------------------------------------------- the map

; Clear the map page: sand, under the full fog.
scen_clear_map:
        ld  hl, MAP_GROUND
        ld  de, MAP_GROUND + 1
        ld  bc, $1000 - 1
        ld  (hl), $7F
        ldir
        ld  hl, MAP_HIGH
        ld  de, MAP_HIGH + 1
        ld  bc, $1000 - 1
        ld  (hl), VEILED_HIGH
        ldir
        ld  hl, MAP_FLAGS
        ld  de, MAP_FLAGS + 1
        ld  bc, $2000 - 1
        ld  (hl), 0
        ldir
        ret

VEILED_HIGH     EQU $7B << 1

; map_load ($01B1D4): A = the Seed, 1-27.  Every square the map covers:
; its icon as the ground, the full fog over it; a 32 x 32 map fills rows
; and columns 16-47.  Then, over all squares, $B0 becomes $7F and $C0
; becomes $BF (a speck of spice with no spice round it, thick spice with
; no thick round it).  mapGround keeps each square's icon (page
; PG_MAPGROUND, which the map page has no room for).
map_load:
        push af
        ld  a, $$tbl_maps
        call map_w1
        pop af
        dec a
        add a, a
        add a, a
        ld  l, a
        ld  h, 0
        ld  de, tbl_maps
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  c, (hl)             ; 32 or 64
        call map_w1
        ex  de, hl              ; HL = the map's bytes (window 1)
        ld  a, c
        cp  64
        jr  z, ml_big
        ld  de, MAP_GROUND + 16 * 64 + 16
        ld  b, 32
ml_row: push bc
        ld  bc, 32
        ldir
        ex  de, hl
        ld  bc, 32
        add hl, bc
        ex  de, hl
        pop bc
        djnz ml_row
        jr  ml_swap
ml_big: ld  de, MAP_GROUND
        ld  bc, $1000
        ldir
ml_swap:
        call map_game
        ld  hl, MAP_GROUND
        ld  bc, $1000
ml_s:   ld  a, (hl)
        cp  $B0
        jr  nz, ml_s1
        ld  (hl), $7F
ml_s1:  cp  $C0
        jr  nz, ml_s2
        ld  (hl), $BF
ml_s2:  inc hl
        dec bc
        ld  a, b
        or  c
        jr  nz, ml_s
        ; mapGround: a copy of the ground's low bytes
        ld  a, PG_MAPGROUND
        call map_w1
        ld  hl, MAP_GROUND
        ld  de, $4000
        ld  bc, $1000
        ldir
        jp  map_game

; ------------------------------------------------------------ resetting

scen_reset_state:
        ld  hl, scen_vars_start
        ld  de, scen_vars_start + 1
        ld  bc, scen_vars_end - scen_vars_start - 1
        ld  (hl), 0
        ldir
        ; every reinforcement slot empty, every starport stock never sold
        ld  hl, reinforcements
        ld  b, 16
srs_r:  ld  (hl), $FF
        push de
        ld  de, 10
        add hl, de
        pop de
        djnz srs_r
        ld  hl, starport_available
        ld  b, 27 * 2
srs_s:  ld  (hl), $FF
        inc hl
        djnz srs_s
        ld  a, $FF
        ld  (enemy_house), a
        ld  (frigate_coming), a
        ret

; ------------------------------------------------------ the bank's own
sl_mission:     DB 0
sl_house:       DB 0
sl_ptr:         DW 0
sl_key:         DB 0
sl_h:           DB 0
st_house:       DB 0
st_action:      DB 0
st_move:        DB 0
st_min:         DB 0
st_max:         DB 0
su_house:       DB 0
su_type:        DB 0
su_health:      DW 0
su_square:      DW 0
su_facing:      DB 0
su_order:       DB 0
ss_index:       DB 0
ss_house:       DB 0
ss_type:        DB 0
ss_square:      DW 0
sr_h:           DB 0
sr_t:           DB 0
sr_where:       DW 0
sr_when:        DW 0
sr_slot:        DB 0
scen_blooms:    DW 0
SCEN_BUF_SIZE   EQU 4096
scen_buf:       DS SCEN_BUF_SIZE
