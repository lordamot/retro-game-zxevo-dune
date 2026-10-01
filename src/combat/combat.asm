; combat.asm - bank COMBAT: targets, firing, projectiles, explosions,
; damage, the Deviator, the Palace's weapons (S4).  Owner: the COMBAT
; subsystem (see .claude/docs/port-code.md).
;
; What runs every tick is here: choosing targets, firing, the projectile's
; burst, explosions and their animations, damage.  The rarer pieces - the
; script routines that only ask questions, the Deviator, the Palace, the
; Sandworm's choice, the turrets, dying - are in bank COMBAT2
; (combat2.asm).  src/combat/world.inc has the explosion list the renderer
; draws.
;
; Every routine keeps IX unless it says otherwise.  IY, and every other
; register, may be clobbered.  The cartridge's C routines pass words; the
; port passes the same values in registers, named in each header.
;
; The statics at the end of this file are this bank's own; a routine that
; can be re-entered (map_make_explosion: its unit_damage may make a death
; explosion) saves its statics on the stack.

; =================================================== the interface: targets

; unit_find_target ($048F00): IX = the unit, A = the mode (0 Hunt, 1
; Guard, 2 Area Guard, 4 Sabotage) -> HL = a reference or 0 (S4).  Mode 4:
; the best structure, else the first eligible enemy unit.  Otherwise both,
; and the unit is taken when unit_attack_score beats the structure's
; unit_struct_target_priority; a Deviator (8) never looks at structures.
unit_find_target:
        ld  (cb_ft_mode), a
        cp  4
        jr  nz, cb_uft_both
        call cb_best_struct_target
        jr  nz, cb_uft_struct
        ld  a, (cb_ft_mode)
        call cb_find_enemy_unit
        jr  nz, cb_uft_unit
        ld  hl, 0
        ret
cb_uft_both:
        call cb_find_enemy_unit
        ld  (cb_ft_unit), hl
        ld  hl, 0
        ld  a, (ix + O_TYPE)
        cp  UNIT_DEVIATOR
        jr  z, cb_uft_1
        ld  a, (cb_ft_mode)
        call cb_best_struct_target
cb_uft_1:  ld  (cb_ft_struct), hl
        ld  a, h
        or  l
        jr  z, cb_uft_unit_or_none
        ld  hl, (cb_ft_unit)
        ld  a, h
        or  l
        jr  z, cb_uft_struct_saved
        ; both: the unit if its score beats the structure's priority
        ld  iy, (cb_ft_struct)
        call unit_struct_target_priority
        ld  (cb_ft_prio), hl
        ld  iy, (cb_ft_unit)
        call unit_attack_score
        ld  de, (cb_ft_prio)
        or  a
        sbc hl, de              ; unsigned words: score - priority
        jr  z, cb_uft_struct_saved
        jr  c, cb_uft_struct_saved
        ld  hl, (cb_ft_unit)
        jr  cb_uft_unit
cb_uft_unit_or_none:
        ld  hl, (cb_ft_unit)
        ld  a, h
        or  l
        ret z
        ; fall through
cb_uft_unit:                       ; HL = a unit record -> its reference
        ld  a, (hl)             ; +0 index
        ld  l, a
        ld  h, REF_UNIT >> 8
        ret
cb_uft_struct_saved:
        ld  hl, (cb_ft_struct)
cb_uft_struct:
        ld  a, (hl)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        ret

; unit_struct_target_priority ($010688): IX = the unit, IY = the
; structure -> HL (S4): 0 if allied or not seen by the unit's house,
; otherwise (priorityBuild + priorityTarget) / the distance in squares
; (to the structure's corner), at most 32000.
unit_struct_target_priority:
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jr  nz, cb_ustp_zero
        ld  a, (ix + O_HOUSE)
        call cb_hbit
        and (iy + O_SEEN)
        jr  z, cb_ustp_zero
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_priorityBuild
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        add hl, de
        push hl                 ; p
        call cb_pos
        ex  de, hl
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call cb_tile_squares       ; HL = d
        pop de                  ; DE = p
        ld  a, h
        or  l
        ex  de, hl              ; HL = p, DE = d
        call nz, udiv16
        jp  cb_cap_7d00
cb_ustp_zero:
        ld  hl, 0
        ret

; unit_attack_score ($047166): IX = the attacker, IY = the target unit ->
; HL (S4): 0 unless the target is allocated, seen by the attacker's house,
; not itself, not allied, a priority target (+$0C bit 13), a flyer only
; for targetAir (+$0C bit 12) and not in fog if it is the player's, and
; both stand in the playable area; otherwise its type's value (+$2E +
; +$30) / the distance in squares + 1, at most $7D00.
unit_attack_score:
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jp  z, cb_uas_zero
        ld  a, (ix + O_HOUSE)
        call cb_hbit
        and (iy + O_SEEN)
        jp  z, cb_uas_zero
        push ix
        pop hl
        push iy
        pop de
        or  a
        sbc hl, de
        jp  z, cb_uas_zero
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jp  nz, cb_uas_zero
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  (cb_as_tinfo), hl
        ld  de, UI_objectFlags + 1
        add hl, de
        bit 13 - 8, (hl)
        jr  z, cb_uas_zero
        ld  hl, (cb_as_tinfo)
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, cb_uas_ground
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_objectFlags + 1
        add hl, de
        bit 12 - 8, (hl)
        jr  z, cb_uas_zero
        call cb_sq_iy
        FCALL map_square_unveiled
        jr  nz, cb_uas_ground
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  z, cb_uas_zero
cb_uas_ground:
        call cb_sq_iy
        call cb_map_valid16
        jr  nc, cb_uas_zero
        call cb_pos
        ex  de, hl
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call cb_tile_squares
        ld  (cb_as_d), hl
        call cb_sq
        call cb_map_valid16
        jr  nc, cb_uas_zero
        ld  hl, (cb_as_tinfo)
        ld  de, UI_priorityBuild
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        add hl, de              ; p
        ld  de, (cb_as_d)
        ld  a, d
        or  e
        jr  z, cb_cap_7d00
        call udiv16
        inc hl
cb_cap_7d00:                       ; HL = min(HL, $7D00), unsigned
        ld  de, $7D00
        push hl
        or  a
        sbc hl, de
        pop hl
        ret c
        ex  de, hl
        ret
cb_uas_zero:
        ld  hl, 0
        ret

; unit_find_enemy_unit ($04730C): IX = the unit, A = the mode -> HL = the
; unit or 0 (Z) (S4).  Walks the other side's list and keeps the first
; unit that its house has seen, is allocated, stands in the playable area,
; is no flyer unless it can hit flyers, is within range for modes 1 (of
; the unit) and 2 (twice, of its home), and is not on its own square.
; The cartridge means to score them, but at $0474D6 every one scores 1
; and the first is kept: the port keeps that (S4's "port" column).  A
; unit with no home (+$52) is given its own square.
cb_find_enemy_unit:
        ld  (cb_fe_mode), a
        ld  a, (ix + U_ORIGIN)
        or  (ix + U_ORIGIN + 1)
        jr  nz, cb_fe_home
        call cb_sq
        call ref_make_square
        ld  (ix + U_ORIGIN), l
        ld  (ix + U_ORIGIN + 1), h
        call cb_pos
        ld  de, cb_fe_home_pos
        ld  bc, 4
        ldir
        jr  cb_fe_1
cb_fe_home:
        ld  l, (ix + U_ORIGIN)
        ld  h, (ix + U_ORIGIN + 1)
        ld  de, cb_fe_home_pos
        call ref_position
cb_fe_1:   call cb_uinfo
        ld  a, (iy + UI_fireDistance)
        ld  h, a
        ld  l, 0                ; range << 8
        ld  a, (cb_fe_mode)
        cp  2
        jr  nz, cb_fe_2
        add hl, hl
cb_fe_2:   ld  (cb_fe_range), hl
        ld  a, (iy + UI_objectFlags + 1)
        and 1 << (12 - 8)
        ld  (cb_fe_air), a
        ld  a, (ix + O_HOUSE)
        call cb_hbit
        ld  (cb_fe_seen), a
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        ld  hl, unit_head
        add a, l
        ld  l, a
        jr  nc, cb_fe_3
        inc h
cb_fe_3:   ld  a, (hl)
cb_fe_loop:
        cp  $FF
        jp  z, cb_fe_none
        ld  (cb_fe_slot), a
        call unit_ptr
        push hl
        pop iy
        ld  a, (cb_fe_seen)
        and (iy + O_SEEN)
        jr  z, cb_fe_next
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jr  z, cb_fe_next
        call cb_sq_iy
        call cb_map_valid16
        jr  nc, cb_fe_next
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, cb_fe_4
        ld  a, (cb_fe_air)
        or  a
        jr  z, cb_fe_next
cb_fe_4:   ld  a, (cb_fe_mode)
        or  a
        jr  z, cb_fe_take
        cp  4
        jr  z, cb_fe_take
        cp  1
        jr  nz, cb_fe_5
        call cb_pos             ; mode 1: within range of the unit
        jr  cb_fe_6
cb_fe_5:   cp  2
        jr  nz, cb_fe_next
        ld  hl, cb_fe_home_pos     ; mode 2: within twice it of the home
cb_fe_6:   push iy
        pop de
        ex  de, hl
        ld  bc, O_POS_Y
        add hl, bc
        ex  de, hl
        call tile_distance
        ld  de, (cb_fe_range)
        ex  de, hl
        call cb_scmp               ; range < d: out
        jr  c, cb_fe_next
cb_fe_take:
        call cb_pos
        ex  de, hl
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call cb_tile_squares
        ld  a, h
        or  l
        jr  z, cb_fe_next          ; its own square
        push iy
        pop hl
        or  1
        ret
cb_fe_next:
        ld  a, (cb_fe_slot)
        ld  hl, unit_lnext
        add a, l
        ld  l, a
        jr  nc, cb_fe_7
        inc h
cb_fe_7:   ld  a, (hl)
        jp  cb_fe_loop
cb_fe_none:
        ld  hl, 0
        xor a
        ret

; unit_find_best_struct_target ($01072C): IX = the unit, A = the mode ->
; HL = the structure or 0 (Z) (S4).  The other side's structure list,
; best unit_struct_target_priority (later ones win ties); mode 1 only
; within range of the unit (to the structure's centre), mode 2 within
; twice the range of the unit's home.  A best of 0 answers nothing.
cb_best_struct_target:
        ld  (cb_bs_mode), a
        ld  l, (ix + U_ORIGIN)
        ld  h, (ix + U_ORIGIN + 1)
        ld  de, cb_fe_home_pos
        call ref_position
        call cb_uinfo
        ld  a, (iy + UI_fireDistance)
        ld  h, a
        ld  l, 0
        ld  (cb_bs_range), hl
        ld  hl, 0
        ld  (cb_bs_best), hl
        ld  (cb_bs_score), hl
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        ld  hl, struct_head
        add a, l
        ld  l, a
        jr  nc, cb_bs_1
        inc h
cb_bs_1:   ld  a, (hl)
cb_bs_loop:
        cp  $FF
        jp  z, cb_bs_done
        ld  (cb_bs_slot), a
        call struct_ptr
        push hl
        pop iy
        ld  a, (cb_bs_mode)
        or  a
        jr  z, cb_bs_score_it
        cp  4
        jr  z, cb_bs_score_it
        cp  3
        jr  nc, cb_bs_next
        ; modes 1, 2: the structure's centre
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, cb_bs_centre
        ld  bc, 4
        ldir
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_centre
        add hl, de
        ld  de, cb_bs_centre
        call cb_pos_add            ; (DE) += (HL)
        ld  a, (cb_bs_mode)
        cp  1
        jr  nz, cb_bs_mode2
        call cb_pos
        ld  de, cb_bs_centre
        call tile_distance
        ld  de, (cb_bs_range)
        ex  de, hl
        call cb_scmp               ; range < d: out
        jr  c, cb_bs_next
        jr  cb_bs_score_it
cb_bs_mode2:
        ld  hl, cb_fe_home_pos
        ld  de, cb_bs_centre
        call tile_distance      ; compared with 2 * range as longs
        ld  de, (cb_bs_range)
        ex  de, hl
        add hl, hl              ; 2 * range: up to $FE00, unsigned
        or  a
        sbc hl, de
        jr  c, cb_bs_next
cb_bs_score_it:
        call unit_struct_target_priority
        ld  de, (cb_bs_score)
        call cb_scmp               ; p < best: keep the old one
        jr  c, cb_bs_next
        ld  (cb_bs_score), hl
        ld  (cb_bs_best), iy
cb_bs_next:
        ld  a, (cb_bs_slot)
        ld  hl, struct_lnext
        add a, l
        ld  l, a
        jr  nc, cb_bs_2
        inc h
cb_bs_2:   ld  a, (hl)
        jp  cb_bs_loop
cb_bs_done:
        ld  hl, (cb_bs_score)
        ld  a, h
        or  l
        ld  hl, 0
        ret z
        ld  hl, (cb_bs_best)
        or  1
        ret

; unit_set_target ($047BCC): IX = the unit, HL = the reference (S4).
; Harvesters are left alone; a stale or unchanged reference is ignored,
; and a flyer for a unit without targetAir.  A place with a unit on it
; becomes that unit, with a structure that structure; the unit's own
; reference becomes its square.  A unit with no turret also heads there.
unit_set_target:
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        ret z
        ld  (cb_st_ref), hl
        call ref_is_valid
        or  a
        ret z
        ld  hl, (cb_st_ref)
        ld  a, (ix + U_TARGETATTACK)
        cp  l
        jr  nz, cb_ust_1
        ld  a, (ix + U_TARGETATTACK + 1)
        cp  h
        ret z
cb_ust_1:  call cb_ref_unit
        jr  z, cb_ust_2
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, cb_ust_2
        call cb_uinfo
        bit 12 - 8, (iy + UI_objectFlags + 1)
        ret z
cb_ust_2:  ld  hl, (cb_st_ref)
        ld  a, h
        and $C0
        cp  REF_TILE >> 8
        jr  nz, cb_ust_3
        call cb_refsq
        call cb_mflags
        bit MF_UNIT, a
        jr  z, cb_ust_s
        call cb_mindex
        dec a
        ld  l, a
        ld  h, REF_UNIT >> 8
        jr  cb_ust_set3
cb_ust_s:  bit MF_STRUCT, a
        jr  z, cb_ust_3
        call cb_mindex
        dec a
        ld  l, a
        ld  h, REF_STRUCT >> 8
cb_ust_set3:
        ld  (cb_st_ref), hl
cb_ust_3:  ld  hl, (cb_st_ref)
        ld  a, h
        cp  REF_UNIT >> 8
        jr  nz, cb_ust_4
        ld  a, l
        cp  (ix + O_INDEX)
        jr  nz, cb_ust_4
        call cb_sq              ; itself: its square
        call ref_make_square
        ld  (cb_st_ref), hl
cb_ust_4:  ld  hl, (cb_st_ref)
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
        call cb_uinfo
        bit 6, (iy + UI_objectFlags)
        ret nz
        ld  hl, (cb_st_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  (ix + U_ROUTE), $FF
        ret

; ====================================================== the interface: damage

; unit_damage ($046BA6): IX = the unit, HL = the damage -> A = 1 if it
; died (S4).  The cartridge's third argument (an impact explosion on the
; unit) is 0 at every call site, so the port has no such path.
unit_damage:
        ld  (cb_ud_dmg), hl
        bit OF_ALLOCATED, (ix + O_FLAGS)
        jp  z, cb_ud_zero
        ld  a, (playtester)
        rra
        jr  nc, cb_ud_1
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  z, cb_ud_zero
cb_ud_1:   call cb_uinfo
        bit 15 - 8, (iy + UI_flags + 1)     ; isNormalUnit
        jr  nz, cb_ud_2
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jp  nz, cb_ud_zero
cb_ud_2:   ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ld  de, (cb_ud_dmg)
        call cb_scmp               ; hp < damage: 0
        jr  c, cb_ud_3
        or  a
        sbc hl, de
        jr  cb_ud_4
cb_ud_3:   ld  hl, 0
cb_ud_4:   ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        xor a
        call unit_deviation_wear
        ld  a, (ix + O_HP)
        or  (ix + O_HP + 1)
        jp  nz, cb_ud_alive
        ; ---- killed
        FCALL cb_deactivate_player
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, cb_ud_5
        ld  a, (ix + U_AMOUNT)  ; the spice spills: radius amount >> 5
        sra a
        sra a
        sra a
        sra a
        sra a
        ld  c, a
        call cb_sq
        ld  a, c
        FCALL cb_spice_fill_circle
cb_ud_5:   call cb_uinfo
        ld  a, (iy + UI_movementType)
        ld  c, 3
        cp  1
        jr  z, cb_ud_tracked
        ld  c, 19
        cp  2
        jr  z, cb_ud_boom
        ld  c, 1
        cp  3
        jr  z, cb_ud_boom
        ld  c, 3
        cp  4
        jr  nz, cb_ud_die
cb_ud_boom:                        ; a death explosion with no damage
        ld  a, c
        call cb_pos_arg
        ld  hl, 0
        ld  d, h
        ld  e, l
        call map_make_explosion
        jr  cb_ud_die
cb_ud_tracked:
        ld  a, c
        call cb_pos_arg
        ld  hl, 0
        ld  d, h
        ld  e, l
        call map_make_explosion
        call cb_pos_arg
        call map_explosion_ground
cb_ud_die: ld  a, ORDER_DIE
        FCALL unit_give_order
        ld  a, 1
        ret
cb_ud_alive:
        ; a computer unit in Ambush, not a Harvester, attacks
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, cb_ud_6
        ld  a, (ix + U_ACTION)
        cp  ORDER_AMBUSH
        jr  nz, cb_ud_6
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_ud_6
        ld  a, ORDER_ATTACK
        FCALL unit_give_order
cb_ud_6:   call cb_uinfo
        ld  l, (iy + UI_hitpoints)
        ld  h, (iy + UI_hitpoints + 1)
        sra h
        rr  l                   ; half the type's hit points
        ld  e, (ix + O_HP)
        ld  d, (ix + O_HP + 1)
        ex  de, hl
        call cb_scmp               ; hp < half: hurt
        jp  nc, cb_ud_healthy
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  nz, cb_ud_7
        ld  a, ORDER_DIE        ; the worm leaves
        FCALL unit_give_order
cb_ud_7:   ld  a, (ix + O_TYPE)
        cp  UNIT_TROOPERS
        jr  z, cb_ud_squad
        cp  UNIT_INFANTRY
        jr  nz, cb_ud_smoke
cb_ud_squad:                       ; a squad loses a man
        call cb_pos_arg
        ld  a, 21
        ld  c, (ix + O_HOUSE)
        call fx_explosion_start
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        FCALL unit_type_count_addr
        dec (hl)
        ld  a, (ix + O_TYPE)
        add a, 2
        ld  (ix + O_TYPE), a
        ld  b, (ix + O_HOUSE)
        FCALL unit_type_count_addr
        inc (hl)
        call cb_uinfo
        ld  a, (iy + UI_hitpoints)
        ld  (ix + O_HP), a
        ld  a, (iy + UI_hitpoints + 1)
        ld  (ix + O_HP + 1), a
        ld  a, 2
        FCALL unit_update_map
        call random
        ld  c, a
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_toughness
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; the toughness, a word
        ld  l, c
        ld  h, 0
        call cb_scmp
        jr  nc, cb_ud_smoke
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_SARDAUKAR
        jr  z, cb_ud_smoke
        ld  a, ORDER_RETREAT
        FCALL unit_give_order
cb_ud_smoke:                       ; tracked, harvester and wheeled units smoke
        call cb_uinfo
        ld  a, (iy + UI_movementType)
        dec a
        cp  3
        jp  nc, cb_ud_zero
        set OF_SMOKING, (ix + O_FLAGS)
        xor a
        ld  (ix + U_SPRITEOFS), a
        ld  (ix + U_ANIMTIMER), a
        ld  (ix + U_ANIMTIMER + 1), a
        jp  cb_ud_zero
cb_ud_healthy:
        ; a healthy Sandworm with nothing to do hunts a sand square near it
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jp  nz, cb_ud_zero
        ld  a, (ix + U_TARGETATTACK)
        or  (ix + U_TARGETATTACK + 1)
        jp  nz, cb_ud_zero
        ld  a, 10
        ld  (cb_ud_tries), a
cb_ud_w1:  call cb_sq
        push hl
        ld  de, 15              ; rand_between(0, 15): the row
        call rand_between
        push af
        call rand_between       ; the column
        ld  e, a
        pop af
        sub 8
        ld  l, a
        sbc a, a
        ld  h, a                ; (row - 8), signed
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  d, 0
        add hl, de
        ld  de, -8
        add hl, de
        pop de
        add hl, de              ; the square + (r - 8) * 64 + c - 8
        ld  (cb_ud_sq), hl
        call cb_map_valid16
        jr  nc, cb_ud_w2
        call map_landscape
        or  a
        jr  z, cb_ud_w3
cb_ud_w2:  ld  hl, 0
        ld  (cb_ud_sq), hl
cb_ud_w3:  ld  hl, cb_ud_tries
        dec (hl)
        jp  z, cb_ud_zero          ; (found on the tenth try: nothing either)
        ld  hl, (cb_ud_sq)
        ld  a, h
        or  l
        jr  z, cb_ud_w1
        ld  a, ORDER_HUNT
        FCALL unit_give_order
        ld  hl, (cb_ud_sq)
        call ref_make_square
        call unit_set_target
cb_ud_zero:
        xor a
        ret

; struct_damage ($00F8D6): IX = the structure, HL = the damage -> A = 1
; if it was destroyed (S4).  Nothing for 0 damage, a structure already
; dying (script variable 0 = 1), or the player's under PLAYTESTER.  At 0:
; the score and counters, struct_destroy (STRUCT), a voice, and every
; reference to it dropped.  The cartridge's range argument is not read.
struct_damage:
        ld  a, h
        or  l
        jp  z, cb_sd_zero
        ld  a, (ix + O_SCRIPT + SC_VARS)
        dec a
        or  (ix + O_SCRIPT + SC_VARS + 1)
        jp  z, cb_sd_zero
        ld  a, (playtester)
        rra
        jp  nc, cb_sd_1
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  z, cb_sd_zero
cb_sd_1:   ex  de, hl
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        or  a
        sbc hl, de
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        dec hl
        bit 7, h                ; hp - 1 >= 0: still standing
        jr  z, cb_sd_zero
        xor a
        ld  (ix + O_HP), a
        ld  (ix + O_HP + 1), a
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_buildCredits
        call cb_score_of           ; DE = max(cost / 100, 1)
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        push de
        call house_are_allied
        pop de
        or  a
        jr  z, cb_sd_enemy
        ld  hl, (destroyed_allied)
        inc hl
        ld  (destroyed_allied), hl
        call cb_score_down
        jp  cb_sd_2
cb_sd_enemy:
        ld  hl, (destroyed_enemy)
        inc hl
        ld  (destroyed_enemy), hl
        call cb_score_up
cb_sd_2:   ; the player's selected structure is selected no more ($00F996)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, cb_sd_2a
        ld  a, (struct_selected)
        cp  (ix + O_INDEX)
        jr  nz, cb_sd_2a
        ld  a, $FF
        ld  (struct_selected), a
cb_sd_2a:  FCALL struct_destroy
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, 21
        jr  nz, cb_sd_voice
        ld  a, (ix + O_HOUSE)
        cp  3
        jr  nc, cb_sd_3
        add a, 22               ; 22, 23, 24: Harkonnen, Atreides, Ordos
cb_sd_voice:
        FCALL snd_voice
cb_sd_3:   FCALL cb_struct_free_refs
        ld  a, 1
        ret
cb_sd_zero:
        xor a
        ret

; HL = a type record, DE = the offset of its cost -> DE = max(cost / 100,
; 1) (divs.w: the cost is a word).  Clobbers A, BC, HL.
cb_score_of:
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 100
        call sdiv16
        ld  de, 1
        call cb_scmp               ; q < 1: 1
        ret c
        ex  de, hl
        ret
; The score moves up by DE / down by DE (never below 0).  Clobbers HL.
cb_score_up:
        ld  hl, (score)
        add hl, de
        ld  (score), hl
        ret
cb_score_down:
        ld  hl, (score)
        ex  de, hl
        call cb_scmp               ; s < score: s; else all of the score
        jr  c, cb_sdn_1
        ld  h, d
        ld  l, e
cb_sdn_1:  ex  de, hl
        ld  hl, (score)
        or  a
        sbc hl, de
        ld  (score), hl
        ret

; ================================================== the interface: explosions

; map_make_explosion ($00A934): A = the type, arg_pos = where, HL = the
; damage, DE = the cause (a reference, 0 none) (S4).
;   1. Type 6: a cause that is a unit other than a Devastator does no
;      damage; the damage becomes the animation's first delay instead.
;   2. Every unit within 16 sixteenths of a square (32 for type 11) takes
;      damage >> (d / 4) (not a Sandworm from type 13, not the Frigate),
;      and reacts to the cause (the reactions of S4).
;   3. The structure on the square takes the full damage (type 2 becomes
;      15 on one below half health); its house is told.
;   4. A wall falls to 140 or more, or by chance below.  Mega Drive: every
;      unit aimed or headed at the square forgets it.
;   5. The animation, and the type's sound.
; Re-entrant: unit_damage may make a death explosion.
map_make_explosion:
        ld  (cb_mx_in_a), a
        ld  (cb_mx_in_hl), hl
        ld  (cb_mx_in_de), de
        ld  hl, cb_mx_vars         ; save the statics
        ld  b, CB_MX_WORDS
cb_mx_s:   ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push de
        djnz cb_mx_s
        push ix
        call cb_mx_body
        pop ix
        ld  hl, cb_mx_vars + CB_MX_WORDS * 2 - 1
        ld  b, CB_MX_WORDS
cb_mx_r:   pop de
        ld  (hl), d
        dec hl
        ld  (hl), e
        dec hl
        djnz cb_mx_r
        ret

cb_mx_body:
        ld  a, (cb_mx_in_a)
        ld  (cb_mx_type), a
        ld  hl, (cb_mx_in_hl)
        ld  (cb_mx_dmg), hl
        ld  hl, (cb_mx_in_de)
        ld  (cb_mx_cause), hl
        ld  hl, arg_pos
        ld  de, cb_mx_pos
        ld  bc, 4
        ldir
        ld  a, (cb_mx_type)
        cp  6
        jr  nz, cb_mx_1
        ld  hl, (cb_mx_dmg)        ; type 6: the damage is kept as the delay
        ld  (cb_mx_delay), hl
        ld  hl, (cb_mx_cause)
        call cb_ref_unit
        jr  z, cb_mx_1
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        cp  UNIT_DEVASTATOR
        jr  z, cb_mx_1
        ld  hl, 0
        ld  (cb_mx_dmg), hl
cb_mx_1:   ld  a, (cb_mx_type)
        cp  11
        ld  a, 16
        jr  nz, cb_mx_2
        ld  a, 32
cb_mx_2:   ld  (cb_mx_reach), a
        ld  hl, cb_mx_pos
        call pos_square
        ld  (cb_mx_sq), hl
        ld  hl, (cb_mx_dmg)
        ld  a, h
        or  l
        jp  z, cb_mx_wall
        ; ---- every unit within reach
        xor a
        ld  (cb_mx_i), a
cb_mx_uloop:
        ld  a, (cb_mx_i)
        ld  b, a
        call cb_unext
        jp  z, cb_mx_structure
        ld  a, b
        ld  (cb_mx_i), a
        ld  hl, cb_mx_pos
        call cb_pos_de
        call tile_distance
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l                   ; d = distance >> 4
        ld  a, h
        or  a
        jr  nz, cb_mx_uloop        ; (>= 256: out of reach)
        ld  a, (cb_mx_reach)
        ld  c, l
        cp  l
        jr  z, cb_mx_uloop
        jr  c, cb_mx_uloop
        ld  a, (ix + O_TYPE)
        cp  UNIT_FRIGATE
        jr  z, cb_mx_react
        cp  UNIT_SANDWORM
        jr  nz, cb_mx_hit
        ld  a, (cb_mx_type)
        cp  13
        jr  z, cb_mx_react
cb_mx_hit: ld  a, c
        srl a
        srl a                   ; d / 4: the shift
        ld  hl, (cb_mx_dmg)
        or  a
        jr  z, cb_mx_h2
        ld  b, a
cb_mx_h1:  srl h
        rr  l
        djnz cb_mx_h1
cb_mx_h2:  call unit_damage
cb_mx_react:
        ; ---- the reaction (not the player's units, not allied with the cause)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  z, cb_mx_uloop
        ld  hl, (cb_mx_cause)
        call cb_ref_unit
        jp  z, cb_mx_uloop
        push hl
        pop iy                  ; IY = the attacker
        push ix
        pop de
        or  a
        sbc hl, de
        jp  z, cb_mx_uloop
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jp  nz, cb_mx_uloop
        ld  a, (ix + U_TEAM)
        or  a
        jr  z, cb_mx_noteam
        dec a
        call team_ptr
        push hl
        ld  de, T_ACTION
        add hl, de
        ld  a, (hl)
        dec a
        inc hl
        or  (hl)
        pop hl
        jr  nz, cb_mx_team_target
        call cb_team_remove     ; a Staging team lets the unit go hunting
        ld  a, ORDER_HUNT
        FCALL unit_give_order
        jp  cb_mx_uloop
cb_mx_team_target:                 ; the team takes the attacker if its target does not shoot
        push hl
        ld  de, T_TARGET
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        call cb_ref_unit
        pop de
        jp  z, cb_mx_uloop
        push de
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        call unit_info
        ld  de, UI_bulletType
        add hl, de
        ld  a, (hl)
        inc hl
        and (hl)
        pop hl
        inc a
        jp  nz, cb_mx_uloop
        ld  de, T_TARGET
        add hl, de
        ld  de, (cb_mx_cause)
        ld  (hl), e
        inc hl
        ld  (hl), d
        jp  cb_mx_uloop
cb_mx_noteam:
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, cb_mx_gun
        ld  a, (iy + O_TYPE)    ; a Harvester shot at by a foot soldier
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, cb_mx_gun
        ld  a, (ix + U_TARGETMOVE)
        or  (ix + U_TARGETMOVE + 1)
        jr  nz, cb_mx_gun
        ld  a, (ix + U_ACTION)
        cp  ORDER_MOVE
        jr  z, cb_mx_hv1
        ld  a, ORDER_MOVE
        FCALL unit_give_order
cb_mx_hv1: ld  hl, (cb_mx_cause)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        jp  cb_mx_uloop
cb_mx_gun: call cb_uinfo
        ld  a, (iy + UI_bulletType)
        and (iy + UI_bulletType + 1)
        inc a
        jp  z, cb_mx_uloop         ; no gun
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, cb_mx_g1
        ld  a, (ix + U_ACTION)
        cp  ORDER_GUARD
        jr  nz, cb_mx_g1
        bit OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
        jr  z, cb_mx_g1
        ld  a, ORDER_HUNT
        FCALL unit_give_order
cb_mx_g1:  ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jp  z, cb_mx_uloop
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ld  a, h
        or  l
        jr  z, cb_mx_g3
        ld  a, (ix + U_ACTION)
        cp  ORDER_HUNT
        jp  nz, cb_mx_uloop
        call cb_ref_unit        ; Hunting a unit that is out of range?
        jr  z, cb_mx_g3
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        call ref_square
        push hl
        call cb_sq
        pop de
        call tile_distance_packed
        call cb_uinfo
        ld  e, (iy + UI_fireDistance)
        ld  d, (iy + UI_fireDistance + 1)
        call cb_scmp               ; d < range: keep it
        jp  c, cb_mx_uloop
cb_mx_g3:  ld  hl, (cb_mx_cause)
        call unit_set_target
        jp  cb_mx_uloop
cb_mx_structure:
        ; ---- the structure on the square takes the full damage
        ld  hl, (cb_mx_sq)
        call cb_mflags
        bit MF_STRUCT, a
        jr  z, cb_mx_wall
        call cb_mindex
        dec a
        call struct_ptr
        push hl
        pop ix
        ld  a, (cb_mx_type)
        cp  2
        jr  nz, cb_mx_s1
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        sra d
        rr  e                   ; half its type's hit points
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        call cb_scmp               ; hp < half: smoke
        jr  nc, cb_mx_s1
        ld  a, 15
        ld  (cb_mx_type), a
cb_mx_s1:  ld  a, (ix + O_HOUSE)
        FCALL struct_house_under_attack
        ld  hl, (cb_mx_dmg)
        call struct_damage
cb_mx_wall:
        ; ---- a wall may fall
        ld  hl, (cb_mx_sq)
        call map_landscape
        cp  LST_WALL
        jp  nz, cb_mx_anim
        ld  hl, (cb_mx_dmg)
        ld  a, h
        or  l
        jp  z, cb_mx_anim
        ld  a, STRUCT_WALL
        call struct_info
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; 140
        ld  hl, (cb_mx_dmg)
        or  a
        sbc hl, de              ; unsigned: damage >= hit points
        jr  nc, cb_mx_fall
        ex  de, hl              ; HL = hit points
        ld  de, (cb_mx_dmg)
        call div_shl8           ; damage * 256 / hit points
        call random
        ld  e, a
        ld  d, 0
        ex  de, hl
        call cb_scmp               ; random <= that: it falls
        jr  z, cb_mx_fall
        jr  nc, cb_mx_anim
cb_mx_fall:
        ld  hl, (cb_mx_sq)         ; map_destroy_wall $01B160
        call map_addr
        ld  (hl), CB_WALL_DESTROYED
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        res 0, (hl)
        add a, (MAP_FLAGS - MAP_HIGH) >> 8
        ld  h, a
        ld  a, (hl)
        and $C8
        ld  (hl), a
        ld  a, h
        add a, (MAP_INDEX - MAP_FLAGS) >> 8
        ld  h, a
        ld  (hl), 0
        ld  hl, (cb_mx_sq)         ; Mega Drive: aims at the square forgotten
        call ref_make_square
        ld  (cb_mx_wref), hl
        xor a
        ld  (cb_mx_i), a
cb_mx_w1:  ld  a, (cb_mx_i)
        ld  b, a
        call cb_unext
        jr  z, cb_mx_anim
        ld  a, b
        ld  (cb_mx_i), a
        ld  de, (cb_mx_wref)
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        or  a
        sbc hl, de
        jr  nz, cb_mx_w2
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
cb_mx_w2:  ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        or  a
        sbc hl, de
        jr  nz, cb_mx_w1
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        jr  cb_mx_w1
cb_mx_anim:
        ; ---- the animation and the sound
        ld  hl, cb_mx_pos
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  a, (cb_mx_type)
        ld  c, 3
        cp  19
        jr  nz, cb_mx_a1
        ld  c, 0
cb_mx_a1:  call fx_explosion_start
        ld  a, (cb_mx_type)
        cp  6
        jr  nz, cb_mx_snd
        ld  de, (cb_mx_delay)
        call fx_explosion_delay
cb_mx_snd: ld  a, (cb_mx_type)
        dec a
        cp  19
        ret nc
        ld  e, a
        ld  d, 0
        ld  hl, cb_mx_sounds
        add hl, de
        ld  a, (hl)
        or  a
        ret z
        FCALL snd_effect
        ret

; The effect of each explosion type 1-19 ($00AD5A), 0 none.
cb_mx_sounds:
        DB  41, 50, 49, 56, 0, 0, 0, 57, 0, 0, 0, 0, 63, 51, 0, 0, 0, 51, 57

CB_WALL_DESTROYED  EQU $21         ; wallIcon: a destroyed wall's ground (S8)

; map_explosion_ground ($0273EA): arg_pos = where (S8).  Only an unveiled
; square, only where the landscape's crater rule allows, not under a fog
; overlay: spice gives spice up (and so does thick spice round it), thick
; spice loses a step, a slab goes back to mapGround, a bloom goes off,
; structures and ruined walls are left, anything else gets a crater.
map_explosion_ground:
        ld  a, (arg_pos + 1)    ; y high byte * 64 + x high byte, unmasked
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (arg_pos + 3)
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, h
        cp  $10
        ret nc                  ; not on the 64 x 64 array
        ld  (cb_eg_sq), hl
        FCALL map_square_unveiled
        ret z
        ld  hl, (cb_eg_sq)
        call map_landscape
        ld  (cb_eg_land), a
        call landscape_info
        ld  de, LS_craterType
        add hl, de
        ld  a, (hl)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_crater
        add hl, de
        ld  a, (hl)
        inc hl
        and (hl)
        inc a
        ret z                   ; -1: never scarred
        ld  hl, (cb_eg_sq)
        call map_overlay_icon
        ld  (cb_eg_ov), a
        cp  $7B - 15            ; a fog overlay stops it
        jr  c, cb_eg_1
        cp  $7B + 1
        ret c
cb_eg_1:   ld  a, (cb_eg_land)
        cp  LST_SPICE
        jr  z, cb_eg_spice
        cp  LST_THICKSPICE
        jr  z, cb_eg_thick
        cp  LST_CONCRETE
        jr  z, cb_eg_slab
        cp  LST_BLOOM
        jr  z, cb_eg_bloom
        cp  LST_STRUCTURE
        ret z
        cp  LST_DESTROYEDWALL
        ret z
        ld  hl, (cb_eg_sq)
        call cb_mflags
        bit MF_STRUCT, a
        ret nz
        jp  cb_map_add_crater
cb_eg_spice:
        ld  de, 1
        call cb_eg_neighbour
        ld  de, -1
        call cb_eg_neighbour
        ld  de, 64
        call cb_eg_neighbour
        ld  de, -64
        call cb_eg_neighbour
        ld  a, (cb_eg_ov)          ; (the cartridge compares the overlay with 9)
        cp  9
        ret z
cb_eg_thick:
        ld  hl, (cb_eg_sq)
        ld  a, $FF
        FCALL map_change_spice
        ret
cb_eg_slab:
        ld  a, PG_MAPGROUND     ; the ground the square was loaded with
        call map_w1
        ld  hl, (cb_eg_sq)
        ld  de, $4000
        add hl, de
        ld  e, (hl)
        ld  a, PG_UNITS
        call map_w1
        ld  hl, (cb_eg_sq)
        call map_addr
        ld  (hl), e
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        res 0, (hl)
        ret
cb_eg_bloom:
        ld  hl, (cb_eg_sq)
        ld  a, (player_house)
        FCALL map_bloom_explode
        ret
; DE = an offset: a thick spice neighbour loses a step.
cb_eg_neighbour:
        ld  hl, (cb_eg_sq)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        push hl
        call map_landscape
        pop hl
        cp  LST_THICKSPICE
        ret nz
        ld  a, $FF
        FCALL map_change_spice
        ret

; cb_map_add_crater ($027608): HL = a square.  An overlay of 1-4 or 7-10
; deepens by 2; 5, 6, 11, 12 stay; anything else starts one: 1 on rock
; (landscape 4, 5), 7 elsewhere, plus a random 0 or 1.
cb_map_add_crater:
        ld  (cb_eg_sq), hl
        call map_overlay_icon
        or  a
        jr  z, cb_mac_new
        cp  13
        jr  nc, cb_mac_new
        cp  5
        jr  c, cb_mac_deeper
        cp  7
        ret c                   ; 5, 6
        cp  11
        ret nc                  ; 11, 12
cb_mac_deeper:
        add a, 2
        jr  cb_mac_set
cb_mac_new:
        ld  hl, (cb_eg_sq)
        call map_landscape
        ld  c, 7
        cp  LST_ROCK
        jr  z, cb_mac_rock
        cp  LST_MOSTLYROCK
        jr  nz, cb_mac_1
cb_mac_rock:
        ld  c, 1
cb_mac_1:  call random
        and 1
        add a, c
cb_mac_set:
        add a, a
        ld  c, a
        ld  hl, (cb_eg_sq)
        call map_addr
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and 1
        or  c
        ld  (hl), a
        ret

; ================================================ the explosion animations

; fx_explosion_start ($00AEDA): A = the type (0-23), arg_pos = where, C =
; the house (the palette) -> HL = the entry in fx_list, or 0 (Z) if none
; is free or the script is empty.
fx_explosion_start:
        ld  e, a
        ld  d, 0
        ld  hl, cb_fx_scripts
        add hl, de
        ld  b, (hl)             ; the first step, 1-based
        call cb_fx_step_addr
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (cb_fs_frame), de
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (cb_fs_ticks), de
        dec de
        bit 7, d
        jr  nz, cb_fxs_empty       ; ticks <= 0: nothing to show
        ld  hl, fx_list
        ld  a, FX_COUNT
cb_fxs_find:
        push hl
        ld  de, FX_STEP
        add hl, de
        ld  e, a
        ld  a, (hl)
        or  a
        ld  a, e
        pop hl
        jr  z, cb_fxs_free
        ld  de, FX_SIZE
        add hl, de
        dec a
        jr  nz, cb_fxs_find
        jr  cb_fxs_none
cb_fxs_empty:                      ; the script shows nothing
        ld  hl, 0
        xor a
        ret
; None free.  The cartridge's pool of 162 never runs dry; the port's
; FX_COUNT can in a big fight - a wreck (types 20-23, frames 315-318)
; holds its entry for 600 ticks and a hit structure smokes (9, 10, 15)
; for up to 204 - and a death that never shows is worse than a wreck cut
; short: the wreck or smoke with the least time left gives way.  With
; only blasts running, as the cartridge with no record: none (HL = 0).
cb_fxs_none:
        push bc
        ld  hl, 0
        ld  (cb_fs_best), hl
        ld  hl, $7FFF
        ld  (cb_fs_least), hl
        ld  hl, fx_list
        ld  a, FX_COUNT
cb_fxs_ev:
        push af
        push hl
        ld  de, FX_FRAME
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = the frame
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = the ticks left
        ld  a, d
        inc a
        jr  z, cb_fxs_evn       ; FX_BLANK: a blank step, not a wreck
        bit 7, d
        jr  nz, cb_fxs_evc      ; FX_SMOKE: the smoke
        ex  de, hl
        ld  de, -315
        add hl, de              ; the frame - 315: 0-3 is a wreck
        ld  a, h
        or  a
        jr  nz, cb_fxs_evn
        ld  a, l
        cp  4
        jr  nc, cb_fxs_evn
cb_fxs_evc:
        ld  hl, (cb_fs_least)
        or  a
        sbc hl, bc
        jr  c, cb_fxs_evn       ; more time left than the best so far: keep
        ld  (cb_fs_least), bc
        pop hl
        push hl
        ld  (cb_fs_best), hl
cb_fxs_evn:
        pop hl
        ld  de, FX_SIZE
        add hl, de
        pop af
        dec a
        jr  nz, cb_fxs_ev
        pop bc
        ld  hl, (cb_fs_best)
        ld  a, h
        or  l
        jr  nz, cb_fxs_free     ; that entry is overwritten
        ret                     ; A = 0, HL = 0
cb_fxs_free:                       ; HL = the entry, B = the step, C = the house
        push hl
        ex  de, hl
        ld  hl, arg_pos
        push bc
        ld  bc, 4
        ldir
        pop bc
        ex  de, hl              ; HL = the entry + FX_FRAME
        ld  de, (cb_fs_frame)
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  de, (cb_fs_ticks)
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  (hl), c
        inc hl
        inc b
        ld  (hl), b             ; the step after the first
        pop hl
        or  1
        ret

; fx_explosion_delay ($00AF64): HL = an entry (0 does nothing), DE = the
; ticks its step lasts.
fx_explosion_delay:
        ld  a, h
        or  l
        ret z
        ld  bc, FX_TICKS
        add hl, bc
        ld  (hl), e
        inc hl
        ld  (hl), d
        ret

; fx_explosion_tick ($00B224): steps the explosions by frames_this_pass
; (S1).  A step that runs out shows the next; one of 0 ticks or less ends
; the explosion and frees its entry.
fx_explosion_tick:
        push ix
        ld  hl, (frames_this_pass)
        ld  (cb_fx_d), hl
        ld  ix, fx_list
        ld  b, FX_COUNT
cb_fxt_loop:
        push bc
        ld  a, (ix + FX_STEP)
        or  a
        jr  z, cb_fxt_next
        ld  hl, (cb_fx_d)
        ld  a, h
        or  l
        jr  nz, cb_fxt_1
        ld  l, (ix + FX_TICKS)  ; no frame passed: as the cartridge, the
        ld  h, (ix + FX_TICKS + 1) ; step is ended at once
cb_fxt_1:  ex  de, hl
        ld  l, (ix + FX_TICKS)
        ld  h, (ix + FX_TICKS + 1)
        or  a
        sbc hl, de
        ld  (ix + FX_TICKS), l
        ld  (ix + FX_TICKS + 1), h
        dec hl
        bit 7, h
        jr  z, cb_fxt_next         ; still > 0
        ld  b, (ix + FX_STEP)
        call cb_fx_step_addr
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        dec hl
        bit 7, h
        jr  z, cb_fxt_2
        ld  (ix + FX_STEP), 0   ; the end
        jr  cb_fxt_next
cb_fxt_2:  inc hl
        ld  (ix + FX_TICKS), l
        ld  (ix + FX_TICKS + 1), h
        ld  (ix + FX_FRAME), e
        ld  (ix + FX_FRAME + 1), d
        inc (ix + FX_STEP)
cb_fxt_next:
        ld  de, FX_SIZE
        add ix, de
        pop bc
        djnz cb_fxt_loop
        pop ix
        ret

; B = a step (1-based) -> HL = its record in cb_fx_steps.  Clobbers DE.
cb_fx_step_addr:
        ld  l, b
        ld  h, 0
        dec hl
        add hl, hl
        add hl, hl
        ld  de, cb_fx_steps
        add hl, de
        ret

; combat_reset: no explosion running, no Death Hand waiting.  For a new
; battle (the loader's game_reset_state).
combat_reset:
        ld  hl, fx_list
        ld  de, fx_list + 1
        ld  bc, FX_COUNT * FX_SIZE - 1
        ld  (hl), 0
        ldir
        ld  hl, 0
        ld  (house_missile), hl
        ld  (house_missile_count), hl
        ld  (special_target_square), hl
        ret

; unit_deviation_wear ($047A5A): IX = the unit, A = n (0: the toughness
; of its current house) -> A = 1 if it went back (S4).  A deviated normal
; unit loses n of its deviation; when that is all of it, it goes back to
; its original house (+$74) with its counts, list, sight and default order,
; and every reference to it is dropped.  (The Mega Drive uses the current
; house's toughness for n = 0: an Ordos deviator's 128 ends a deviation of
; 120 at the first hit - S4: keep.)
unit_deviation_wear:
        ld  c, a
        ld  b, 0
        ld  a, (ix + U_DEVIATED)
        or  a
        ret z
        ld  a, c
        or  a
        jr  nz, cb_dw1
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_toughness
        add hl, de
        ld  c, (hl)
        inc hl
        ld  b, (hl)
cb_dw1: push bc
        call cb_uinfo
        pop bc
        bit 15 - 8, (iy + UI_flags + 1)
        jr  z, cb_dw_no
        ld  a, (ix + U_DEVIATED)
        ld  e, a
        rla
        sbc a, a
        ld  d, a                ; the deviation, sign-extended
        ld  h, b
        ld  l, c
        call cb_scmp            ; n < deviated: take n off
        jr  nc, cb_dw_back
        ld  a, (ix + U_DEVIATED)
        sub c
        ld  (ix + U_DEVIATED), a
cb_dw_no:
        xor a
        ret
cb_dw_back:
        ld  (ix + U_DEVIATED), 1
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        FCALL unit_type_count_addr
        dec (hl)
        ld  a, (ix + O_INDEX)
        FCALL unit_list_unlink
        ld  a, (ix + U_ORIGHOUSE)
        ld  (ix + O_HOUSE), a
        ld  a, (ix + O_INDEX)
        FCALL unit_list_link
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        FCALL unit_type_count_addr
        inc (hl)
        ld  (ix + U_DEVIATED), 0
        set OF_BULLETBIG, (ix + O_FLAGS)
        ld  a, 2
        FCALL unit_update_map
        res OF_BULLETBIG, (ix + O_FLAGS)
        call cb_uinfo
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, cb_dw2
        ld  (ix + O_SEEN), $FF
        ld  a, (iy + UI_actionPlayer)
        jr  cb_dw3
cb_dw2: ld  a, (ix + O_HOUSE)
        call cb_hbit
        ld  (ix + O_SEEN), a
        ld  a, (iy + UI_actionAI)
cb_dw3: FCALL unit_give_order
        FCALL unit_drop_references
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_dw4
        xor a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
cb_dw4: xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, 1
        ret

; ============================================== the interface: firing

; UNIT 8 fire ($0447E2, emc_unit_fire, S4): IX = the script -> HL = 1 if
; it fired (or the Sandworm ate), else 0.
ef_u_fire:
        call cb_obj
        call cb_uinfo
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ld  (cb_uf_tgt), hl
        ld  a, h
        or  l
        jp  z, cb_uf_zero
        call ref_is_valid
        or  a
        jp  z, cb_uf_zero
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jp  z, cb_uf_1
        call cb_sq              ; aimed at its own square: dropped
        call ref_make_square
        ld  de, (cb_uf_tgt)
        or  a
        sbc hl, de
        jp  nz, cb_uf_1
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
cb_uf_1:   ld  hl, (cb_uf_tgt)        ; changed underneath: set it again
        ld  a, (ix + U_TARGETATTACK)
        cp  l
        jr  nz, cb_uf_reset
        ld  a, (ix + U_TARGETATTACK + 1)
        cp  h
        jp  z, cb_uf_2
cb_uf_reset:
        call unit_set_target
        jp  cb_uf_zero
cb_uf_2:   ; the gun must have finished turning
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, cb_uf_hull
        bit 6, (iy + UI_objectFlags)
        jp  z, cb_uf_3
        ld  a, (ix + U_OR1_CURRENT)
        ld  (cb_uf_face), a
        cp  (ix + U_OR1_TARGET)
        jp  nz, cb_uf_zero
        jr  cb_uf_4
cb_uf_3:   ld  a, (iy + UI_movementType)
        cp  4
        jr  z, cb_uf_hull
        ld  a, (ix + U_OR0_CURRENT)
        cp  (ix + U_OR0_TARGET)
        jp  nz, cb_uf_zero
cb_uf_hull:
        ld  a, (ix + U_OR0_CURRENT)
        ld  (cb_uf_face), a
cb_uf_4:   ld  hl, (cb_uf_tgt)        ; a place with an object: aim at the object
        ld  a, h
        and $C0
        cp  REF_TILE >> 8
        jr  nz, cb_uf_5
        call ref_square
        call cb_mflags
        and (1 << MF_UNIT) | (1 << MF_STRUCT)
        jr  z, cb_uf_5
        call cb_mindex
        or  a
        jr  z, cb_uf_5
        ld  hl, (cb_uf_tgt)
        call unit_set_target
        call cb_uinfo
cb_uf_5:   ld  a, (ix + U_FIREDELAY)
        or  a
        jp  nz, cb_uf_zero
        ld  hl, (cb_uf_tgt)
        ld  de, cb_uf_tpos
        call ref_position
        ld  hl, (cb_uf_tgt)
        call cb_ref_distance_to_edge
        ld  (cb_uf_dist), hl
        call cb_uinfo              ; (clobbers HL and DE)
        ld  h, (iy + UI_fireDistance)
        ld  l, 0
        ld  de, (cb_uf_dist)
        call cb_scmp               ; range < distance: out of reach ($044932)
        jp  c, cb_uf_zero
        call cb_pos
        ld  de, cb_uf_tpos
        call tile_direction
        ld  c, a
        ld  a, (cb_uf_face)
        sub c                   ; |facing - direction|, no wrap-around
        jr  nc, cb_uf_6
        neg
cb_uf_6:   ld  c, a
        call cb_uinfo
        ld  a, (iy + UI_movementType)
        cp  4
        jr  nz, cb_uf_7
        srl c
        srl c
        srl c                   ; a winger's error counts an eighth
cb_uf_7:   ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  nz, cb_uf_8
        ld  c, 0
cb_uf_8:   ld  hl, (cb_uf_tgt)
        call cb_ref_unit
        jr  z, cb_uf_9
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, cb_uf_9
        ld  c, 0                ; at a flyer: no test
cb_uf_9:   ld  a, c
        cp  8
        jp  nc, cb_uf_zero
        ; ---- it fires
        call cb_uinfo
        ld  l, (iy + UI_damage)
        ld  h, (iy + UI_damage + 1)
        ld  (cb_uf_dmg), hl
        ld  a, (iy + UI_bulletSound)
        ld  (cb_uf_sound), a
        ld  a, (iy + UI_bulletType)
        ld  (cb_uf_kind), a
        xor a
        ld  (cb_uf_twice), a
        bit 10 - 8, (iy + UI_flags + 1)     ; firesTwice while above half health
        jr  z, cb_uf_10
        ld  e, (iy + UI_hitpoints)
        ld  d, (iy + UI_hitpoints + 1)
        sra d
        rr  e
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ex  de, hl
        call cb_scmp               ; half < hp
        jr  nc, cb_uf_10
        ld  a, 1
        ld  (cb_uf_twice), a
cb_uf_10:  ld  a, (ix + O_TYPE)
        cp  UNIT_TROOPERS
        jr  z, cb_uf_trooper
        cp  UNIT_TROOPER
        jr  nz, cb_uf_11
cb_uf_trooper:
        ld  hl, (cb_uf_dist)
        ld  de, $200 + 1
        call cb_scmp
        jr  c, cb_uf_tr1
        ld  a, UNIT_MINIROCKET  ; more than $200 away: a rocket
        ld  (cb_uf_kind), a
        ld  a, 42
        ld  (cb_uf_sound), a
cb_uf_tr1: ld  a, (ix + O_HOUSE)
        cp  HOUSE_FREMEN
        jr  nz, cb_uf_11
        ld  hl, (cb_uf_dmg)        ; Mega Drive: the Fremen hit four times as hard
        add hl, hl
        add hl, hl
        ld  (cb_uf_dmg), hl
cb_uf_11:  ld  a, (cb_uf_kind)
        cp  UNIT_SANDWORM
        jp  z, cb_uf_eat
        cp  UNIT_ROCKET
        jp  c, cb_uf_zero
        cp  UNIT_SONICBLAST + 1
        jp  nc, cb_uf_zero
        cp  UNIT_MINIROCKET
        jr  nz, cb_uf_12
        ld  hl, (cb_uf_dmg)        ; a rocket loses a quarter
        ld  d, h
        ld  e, l
        sra d
        rr  e
        sra d
        rr  e
        or  a
        sbc hl, de
        ld  (cb_uf_dmg), hl
cb_uf_12:  call cb_pos_arg
        ld  a, (cb_uf_kind)
        ld  b, a
        ld  c, (ix + O_HOUSE)
        ld  hl, (cb_uf_dmg)
        ld  de, (cb_uf_tgt)
        push ix
        call unit_fire_projectile
        pop ix
        ld  a, h
        or  l
        jp  z, cb_uf_zero
        ld  (cb_uf_proj), hl
        ld  de, U_ORIGIN
        add hl, de
        ld  a, (ix + O_INDEX)
        ld  (hl), a
        inc hl
        ld  (hl), REF_UNIT >> 8
        ld  a, (cb_uf_sound)
        cp  $FF
        jr  z, cb_uf_s1
        FCALL snd_effect
cb_uf_s1:  ld  a, 20
        call unit_deviation_wear
        ld  a, (cb_uf_kind)
        cp  UNIT_BULLET
        jr  nz, cb_uf_once
        ld  hl, (cb_uf_proj)
        inc hl
        inc hl
        inc hl                  ; +3 linkedID
        ld  a, (ix + O_TYPE)
        cp  UNIT_TANK
        jr  z, cb_uf_flash
        cp  UNIT_SIEGETANK
        jr  z, cb_uf_flash
        cp  UNIT_DEVASTATOR
        jr  z, cb_uf_big
        ld  (hl), $FF
        jr  cb_uf_once
cb_uf_flash:
        set 6, (ix + O_FLAGS2)  ; the muzzle flash (bit 6 of +$07)
cb_uf_big: ld  (hl), 9             ; a big gun
cb_uf_once:
        bit 5, (ix + O_FLAGS2)  ; fireOnce: back to Guard
        jp  z, cb_uf_reload
        res 5, (ix + O_FLAGS2)
        ld  a, ORDER_GUARD
        FCALL unit_give_order
        jr  cb_uf_reload
cb_uf_eat: ; ---- the Sandworm eats (S4)
        xor a
        FCALL unit_update_map
        ld  hl, (cb_uf_tgt)
        call cb_ref_unit
        jr  z, cb_uf_e1
        push ix
        push hl
        pop ix
        ld  a, (unit_selected)
        cp  (ix + O_INDEX)
        jr  nz, cb_uf_e0
        ld  a, $FF
        ld  (unit_selected), a
cb_uf_e0:  ld  (ix + O_SCRIPT + SC_VARS + 2), $FF      ; variable 1 = -1: eaten
        ld  (ix + O_SCRIPT + SC_VARS + 3), $FF
        FCALL cb_deactivate_player
        ld  a, (player_house)
        FCALL unit_unseen_by_houses
        FCALL unit_remove
        pop ix
cb_uf_e1:  call cb_uinfo
        ld  a, (iy + UI_explosionType)
        call cb_pos_arg
        ld  hl, 0
        ld  d, h
        ld  e, l
        call map_make_explosion
        ld  a, 63
        FCALL snd_effect
        ld  a, 1
        FCALL unit_update_map
        dec (ix + U_AMOUNT)
        ld  (ix + O_DELAY), 12  ; the script waits 12
        ld  (ix + O_DELAY + 1), 0
        ld  a, (ix + U_AMOUNT)
        dec a
        bit 7, a                ; amount < 1 (signed): the worm is done
        jr  z, cb_uf_reload
        ld  a, ORDER_DIE
        FCALL unit_give_order
cb_uf_reload:
        call cb_uinfo
        ld  a, (iy + UI_fireDelay)
        add a, a
        ld  (ix + U_FIREDELAY), a
        ld  a, (cb_uf_twice)
        or  a
        jr  z, cb_uf_r1
        ld  a, (ix + O_FLAGS)
        xor 1 << OF_FIRETWICE
        ld  (ix + O_FLAGS), a
        bit OF_FIRETWICE, a
        jr  z, cb_uf_r2
        ld  (ix + U_FIREDELAY), 5
        jr  cb_uf_r2
cb_uf_r1:  res OF_FIRETWICE, (ix + O_FLAGS)
cb_uf_r2:  call random
        and 1
        add a, (ix + U_FIREDELAY)
        ld  (ix + U_FIREDELAY), a
        ld  a, 2
        FCALL unit_update_map
        ld  hl, 1
        ret
cb_uf_zero:
        ld  hl, 0
        ret

; cb_ref_distance_to_edge ($02E0A8): IX = the unit, HL = the reference ->
; HL = the distance to it; to a structure, to the square of its footprint
; that faces the unit (tbl_layout_edge by layout and direction).
cb_ref_distance_to_edge:
        ld  (cb_de_ref), hl
        ld  a, h
        and $C0
        cp  REF_STRUCT >> 8
        jr  nz, cb_de_plain
        call cb_ref_struct
        jr  z, cb_de_plain
        push hl
        pop iy
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  (cb_de_sq), hl
        ld  hl, (cb_de_ref)
        ld  de, cb_de_pos
        call ref_position
        call cb_pos
        ld  de, cb_de_pos
        call tile_direction
        add a, $10
        rlca
        rlca
        rlca
        and 7                   ; ((direction + 16) & 255) >> 5
        add a, 4
        and 7
        ld  c, a
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        add a, a                ; layout * 8
        add a, c
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_edge
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (cb_de_sq)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  de, cb_de_pos
        call square_centre
        jr  cb_de_go
cb_de_plain:
        ld  hl, (cb_de_ref)
        ld  de, cb_de_pos
        call ref_position
cb_de_go:  call cb_pos
        ld  de, cb_de_pos
        jp  tile_distance

; unit_fire_projectile ($04834A): arg_pos = where from, B = the
; projectile type (18-24), C = the house, HL = the damage, DE = the
; target (a reference) -> HL = the projectile, or 0 (S4).  Rockets start
; at the origin facing the target, a bullet or sonic blast 32 north of it
; and then 128 towards it.  The shot carries the damage as its hit
; points.  IX is not kept.
unit_fire_projectile:
        ld  a, b
        ld  (cb_fp_type), a
        ld  a, c
        ld  (cb_fp_house), a
        ld  (cb_fp_dmg), hl
        ld  (cb_fp_tgt), de
        ld  hl, arg_pos
        ld  de, cb_fp_org
        ld  bc, 4
        ldir
        ld  hl, (cb_fp_tgt)
        ld  de, cb_fp_tpos
        call ref_position
        ld  hl, (cb_fp_tgt)
        call ref_is_valid
        or  a
        jp  z, cb_fp_none
        ld  a, (cb_fp_type)
        sub UNIT_DEATHHAND
        jp  c, cb_fp_none
        cp  UNIT_SONICBLAST - UNIT_DEATHHAND + 1
        jp  nc, cb_fp_none
        ld  hl, cb_fp_org
        ld  de, cb_fp_tpos
        call tile_direction
        ld  (cb_fp_dir), a
        ld  a, (cb_fp_type)
        cp  UNIT_BULLET
        jp  nc, cb_fp_bullet
        ; ---- a rocket
        ld  hl, cb_fp_org
        ld  de, arg_pos
        ld  bc, 4
        ldir
        call cb_fp_spawn
        jp  z, cb_fp_none
        ld  a, (cb_fp_type)
        call unit_info
        ld  de, UI_bulletSound
        add hl, de
        ld  a, (hl)
        FCALL snd_effect
        ld  hl, (cb_fp_tgt)
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
        ld  hl, (cb_fp_dmg)
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        call cb_fp_dest
        call cb_uinfo
        bit 14 - 8, (iy + UI_flags + 1)     ; notAccurate: a scattered aim
        jr  z, cb_fp_1
        call random
        and $0F
        jr  z, cb_fp_far
        ld  hl, cb_fp_org
        ld  de, cb_fp_tpos
        call tile_distance
        ld  a, h                ; distance >> 8 (asr: it is positive)
        jr  cb_fp_2
cb_fp_far: call random
cb_fp_2:   ld  l, a
        ld  h, 0
        ld  de, 8
        add hl, de
        ex  de, hl
        ld  hl, cb_fp_tpos
        xor a
        call cb_tile_move_by_random
        call cb_fp_dest
cb_fp_1:   call cb_uinfo
        ld  a, (iy + UI_fireDistance)
        ld  (ix + U_FIREDELAY), a
        ld  hl, (cb_fp_tgt)        ; doubled against a flyer
        call cb_ref_unit
        jr  z, cb_fp_3
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, cb_fp_3
        sla (ix + U_FIREDELAY)
cb_fp_3:   ld  a, (cb_fp_type)
        cp  UNIT_DEATHHAND
        jr  nz, cb_fp_unfog
        jr  cb_fp_done
cb_fp_bullet:
        ; ---- a bullet or sonic blast
        ld  hl, cb_fp_org
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  hl, arg_pos
        xor a
        ld  c, 32
        call tile_move_by_direction
        ld  hl, arg_pos
        ld  a, (cb_fp_dir)
        ld  c, 128
        call tile_move_by_direction
        call cb_fp_spawn
        jp  z, cb_fp_none
        ld  a, (cb_fp_type)
        cp  UNIT_SONICBLAST
        jr  nz, cb_fp_4
        call cb_uinfo
        ld  a, (iy + UI_fireDistance)
        ld  (ix + U_FIREDELAY), a
cb_fp_4:   call cb_fp_dest
        ld  hl, (cb_fp_dmg)
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ld  de, 16
        call cb_scmp
        jr  c, cb_fp_unfog
        set OF_BULLETBIG, (ix + O_FLAGS)
cb_fp_unfog:
        ; unless the player's house sees it, the fog lifts round it
        ld  a, (player_house)
        call cb_hbit
        and (ix + O_SEEN)
        jr  nz, cb_fp_done
        call cb_pos
        ld  c, 2
        FCALL map_unfog_radius
cb_fp_done:
        push ix
        pop hl
        ret
cb_fp_none:
        ld  hl, 0
        ret
; unit_spawn with the saved type, house and direction.  -> IX = the new
; unit, NZ; or Z.
cb_fp_spawn:
        ld  a, (cb_fp_type)
        ld  b, a
        ld  a, (cb_fp_house)
        ld  c, a
        ld  a, (cb_fp_dir)
        ld  d, a
        ld  a, $FF
        FCALL unit_spawn
        ret z
        push hl
        pop ix
        or  1
        ret
; currentDestination = cb_fp_tpos.
cb_fp_dest:
        push ix
        pop de
        ld  hl, U_DEST_Y
        add hl, de
        ex  de, hl
        ld  hl, cb_fp_tpos
        ld  bc, 4
        ldir
        ret

; cb_tile_move_by_random ($011688): HL -> a position (changed in place), DE
; = the distance (0 leaves it), A = nonzero to centre the result in its
; square.  A random direction and a random part of the distance; a result
; outside squares 1-62 leaves the position as it was.  Clobbers A, BC,
; DE, IY; keeps HL.
cb_tile_move_by_random:
        ld  (cb_tr_centre), a
        ld  a, d
        or  e
        ret z
        push hl
        call random
        ld  c, a
        ld  b, 0                ; BC = r
cb_tr_1:   ld  a, d                ; d > r: done
        or  a
        jr  nz, cb_tr_2
        ld  a, c
        cp  e
        jr  c, cb_tr_2
        srl c
        jr  cb_tr_1
cb_tr_2:   ld  a, c
        ld  (cb_tr_r), a
        call random
        ld  (cb_tr_a), a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        call cb_tr_scale
        ld  (cb_tr_dx), hl
        ld  a, (cb_tr_a)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        call cb_tr_scale
        ld  (cb_tr_dy), hl
        pop hl
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (cb_tr_dy)
        add hl, de              ; the new y
        call cb_tr_bound
        jr  nc, cb_tr_out
        ld  (cb_tr_y), hl
        pop hl
        push hl
        inc hl
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (cb_tr_dx)
        add hl, de              ; the new x
        call cb_tr_bound
        jr  nc, cb_tr_out
        ex  de, hl              ; DE = the new x
        ld  bc, (cb_tr_y)
        ld  a, (cb_tr_centre)
        or  a
        jr  z, cb_tr_3
        ld  c, $80
        ld  e, $80
cb_tr_3:   pop hl
        push hl
        ld  (hl), c
        inc hl
        ld  (hl), b
        inc hl
        ld  (hl), e
        inc hl
        ld  (hl), d
cb_tr_out: pop hl
        ret
; A = a signed sine or cosine -> HL = (A * r) >> 3 (arithmetic) & $FFF0
; (muls.w, asr.w #3, andi.w #$FFF0).  Clobbers A, BC, DE.
cb_tr_scale:
        push af
        ld  a, (cb_tr_r)
        ld  c, a
        pop af
        call smul_d8
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        ld  a, l
        and $F0
        ld  l, a
        ret
; HL = a coordinate -> carry if $100 <= HL < $3F00 (signed).
cb_tr_bound:
        push de
        ld  de, $100
        call cb_scmp
        jr  c, cb_trb_no
        ld  de, $3F00
        call cb_scmp
        pop de
        ret
cb_trb_no: pop de
        or  a
        ret

; ================================================================ helpers

; IX = a script state -> IX = its object (S7: the record's +$16).
; Clobbers DE.
cb_obj:
        ld  de, -O_SCRIPT
        add ix, de
        ret

; IY = the type record of the unit at IX.  Clobbers A, DE, HL.
cb_uinfo:
        ld  a, (ix + O_TYPE)
        call unit_info
        push hl
        pop iy
        ret

; HL = &IX's position.
cb_pos:
        push de
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        pop de
        ret
; DE = &IX's position (HL kept).
cb_pos_de:
        push hl
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        ret
; arg_pos = IX's position.  Keeps A.
cb_pos_arg:
        push af
        call cb_pos
        ld  de, arg_pos
        ld  bc, 4
        ldir
        pop af
        ret

; HL = the square of IX's (IY's) position.  Clobbers A.
cb_sq:
        call cb_pos
        jp  pos_square
cb_sq_iy:
        push de
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        pop de
        jp  pos_square

; HL, DE -> two positions -> HL = the distance in squares, rounded
; (tile_distance_squares $0115C2).  Clobbers A, BC.
cb_tile_squares:
        call tile_distance
        ld  bc, $80
        add hl, bc
        ld  l, h
        ld  h, 0
        ret

; HL = a square word -> carry if it is a playable square
; (map_is_valid_position $005798: the square is an unsigned word, so one
; outside $0000-$0FFF is never valid).  Keeps HL.  Clobbers A.
cb_map_valid16:
        ld  a, h
        cp  $10
        ret nc                  ; (carry clear: not valid)
        jp  map_valid

; Signed compare: carry set if HL < DE.  Keeps HL, DE.  Clobbers A.
cb_scmp:
        ld  a, h
        xor d
        jp  m, cb_scmp_diff
        push hl
        sbc hl, de              ; (carry is clear: the xor cleared it)
        pop hl
        ret
cb_scmp_diff:
        ld  a, h
        rla                     ; carry = HL is the negative one
        ret

; A = a house -> A = 1 << house.  Keeps BC.
cb_hbit:
        push bc
        inc a
        ld  b, a
        ld  a, $80
cb_cbh_1:  rlca
        djnz cb_cbh_1
        pop bc
        ret

; (DE) += (HL): two positions, word by word.  Clobbers A, BC; HL, DE
; come back advanced by 4.
cb_pos_add:
        ld  b, 2
cb_pa_1:   ld  a, (de)
        add a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        adc a, (hl)
        ld  (de), a
        inc de
        inc hl
        djnz cb_pa_1
        ret

; HL = a reference -> HL = the unit it names (kind 1, a real slot) and
; NZ, or HL = 0 and Z (ref_unit $02E38C).  Clobbers A, DE.
cb_ref_unit:
        ld  a, h
        cp  REF_UNIT >> 8
        jr  nz, cb_none
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, cb_none
        call unit_ptr
        or  1
        ret
cb_none:
        ld  hl, 0
        xor a
        ret
; The same for a structure (kind 2).
cb_ref_struct:
        ld  a, h
        cp  REF_STRUCT >> 8
        jr  nz, cb_none
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, cb_none
        call struct_ptr
        or  1
        ret

; HL = a square reference -> HL = its square.  Clobbers A.
cb_refsq:
        ld  a, l
        rra
        and $3F
        push af
        ld  a, h
        and $3F
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        pop af
        or  l
        ld  l, a
        ret

; HL = a square -> A = its flags byte / its index byte.  Keep HL.
cb_mflags:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret
cb_mindex:
        push hl
        ld  a, h
        and $0F
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret

; The units unit_find_first($FF, $FF) walks: the find array in order,
; passing over isNotOnMap ones unless validate_strict.  B = the position
; to look from -> IX = the unit, B = the position after it, NZ; Z at the
; end.  Clobbers A, DE, HL.
cb_unext:
        ld  a, (unit_find_count)
        cp  b
        jr  z, cb_cbu_end
        jr  c, cb_cbu_end
        ld  e, b
        ld  d, 0
        inc b
        ld  hl, unit_find
        add hl, de
        ld  a, (hl)
        call unit_ptr
        push hl
        pop ix
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, cb_cbu_ok
        ld  a, (validate_strict)
        or  a
        jr  z, cb_unext
cb_cbu_ok: or  1
        ret
cb_cbu_end:
        xor a
        ret

; team_remove_unit ($02E406): IX = a unit in a team (+$75 = slot + 1):
; the team's member count down, the unit out of it.  Clobbers A, DE, HL.
cb_team_remove:
        ld  a, (ix + U_TEAM)
        or  a
        ret z
        dec a
        call team_ptr
        ld  de, T_MEMBERS
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        dec de
        ld  (hl), d
        dec hl
        ld  (hl), e
        ld  (ix + U_TEAM), 0
        ret

; ============================================================ the tables

; The 24 explosion scripts of $0C80A2, as src/res/art/effects.txt reads
; them: for each type the first of its steps in cb_fx_steps (1-based); a
; step is (frame, ticks) - a sprites.txt frame id, FX_BLANK for '-',
; FX_SMOKE | 285 for 'smoke 285 286 287' - and a step of 0 ticks ends it.
    MACRO CB_FXS _frame_, _ticks_
        DW  _frame_, _ticks_
    ENDM
CB_FXEND   EQU 0

cb_fx_scripts:
        DB  (cb_fx0 - cb_fx_steps) / 4 + 1,  (cb_fx1 - cb_fx_steps) / 4 + 1
        DB  (cb_fx2 - cb_fx_steps) / 4 + 1,  (cb_fx3 - cb_fx_steps) / 4 + 1
        DB  (cb_fx4 - cb_fx_steps) / 4 + 1,  (cb_fx5 - cb_fx_steps) / 4 + 1
        DB  (cb_fx6 - cb_fx_steps) / 4 + 1,  (cb_fx7 - cb_fx_steps) / 4 + 1
        DB  (cb_fx8 - cb_fx_steps) / 4 + 1,  (cb_fx9 - cb_fx_steps) / 4 + 1
        DB  (cb_fx10 - cb_fx_steps) / 4 + 1, (cb_fx11 - cb_fx_steps) / 4 + 1
        DB  (cb_fx12 - cb_fx_steps) / 4 + 1, (cb_fx13 - cb_fx_steps) / 4 + 1
        DB  (cb_fx14 - cb_fx_steps) / 4 + 1, (cb_fx15 - cb_fx_steps) / 4 + 1
        DB  (cb_fx12 - cb_fx_steps) / 4 + 1, (cb_fx12 - cb_fx_steps) / 4 + 1
        DB  (cb_fx18 - cb_fx_steps) / 4 + 1, (cb_fx19 - cb_fx_steps) / 4 + 1
        DB  (cb_fx20 - cb_fx_steps) / 4 + 1, (cb_fx21 - cb_fx_steps) / 4 + 1
        DB  (cb_fx22 - cb_fx_steps) / 4 + 1, (cb_fx23 - cb_fx_steps) / 4 + 1

cb_fx_steps:
cb_fx0:    CB_FXS 288, 10
        CB_FXS 0, CB_FXEND
cb_fx1:    CB_FXS 288, 10
        CB_FXS 289, 10
        CB_FXS 290, 10
        CB_FXS 0, CB_FXEND
cb_fx2:    CB_FXS 291, 10
        CB_FXS 0, CB_FXEND
cb_fx3:
cb_fx8:    CB_FXS 291, 10
        CB_FXS 292, 10
        CB_FXS 293, 10
        CB_FXS 294, 10
        CB_FXS 295, 10
        CB_FXS 0, CB_FXEND
cb_fx4:    CB_FXS 296, 10
        CB_FXS 297, 10
        CB_FXS 298, 10
        CB_FXS 299, 10
        CB_FXS 300, 10
        CB_FXS 0, CB_FXEND
cb_fx5:    CB_FXS FX_BLANK, 20
        CB_FXS 291, 10
        CB_FXS 292, 10
        CB_FXS 293, 10
        CB_FXS 294, 10
        CB_FXS 295, 10
        CB_FXS 0, CB_FXEND
cb_fx6:    CB_FXS FX_BLANK, 20
        CB_FXS 296, 10
        CB_FXS 297, 10
        CB_FXS 298, 10
        CB_FXS 299, 10
        CB_FXS 300, 10
        CB_FXS 0, CB_FXEND
cb_fx7:    CB_FXS 301, 10             ; the Deviator's cloud
        CB_FXS 302, 10
        CB_FXS 303, 10
        CB_FXS 304, 10
        CB_FXS 305, 30
        CB_FXS 0, CB_FXEND
cb_fx9:    CB_FXS FX_SMOKE | 285, 84
        CB_FXS 0, CB_FXEND
cb_fx10:
cb_fx15:   CB_FXS FX_SMOKE | 285, 204 ; 15: a hit structure below half health
        CB_FXS 0, CB_FXEND
cb_fx11:   CB_FXS 291, 10
        CB_FXS 292, 10
        CB_FXS 297, 10
        CB_FXS 293, 10
        CB_FXS 294, 10
        CB_FXS 298, 10
        CB_FXS 299, 10
        CB_FXS 295, 10
cb_fx12:   CB_FXS 0, CB_FXEND            ; 12, 16, 17: nothing
cb_fx13:   CB_FXS 306, 10             ; the Sandworm
        CB_FXS 307, 10
        CB_FXS 308, 10
        CB_FXS 309, 10
        CB_FXS 310, 30
        CB_FXS 0, CB_FXEND
cb_fx14:   CB_FXS 291, 5
        CB_FXS 296, 7
        CB_FXS 292, 7
        CB_FXS 297, 10
        CB_FXS 298, 10
        CB_FXS 299, 10
        CB_FXS 300, 10
        CB_FXS 0, CB_FXEND
cb_fx18:   CB_FXS 291, 5
        CB_FXS 294, 15
        CB_FXS 0, CB_FXEND
cb_fx19:   CB_FXS 311, 5
        CB_FXS 312, 10
        CB_FXS 313, 10
        CB_FXS 312, 5
        CB_FXS 313, 5
        CB_FXS 312, 5
        CB_FXS 313, 5
        CB_FXS 314, 20
        CB_FXS 0, CB_FXEND
cb_fx20:   CB_FXS 315, 600            ; infantry dies (house-coloured)
        CB_FXS 0, CB_FXEND
cb_fx21:   CB_FXS 316, 600            ; a unit dies (house-coloured)
        CB_FXS 0, CB_FXEND
cb_fx22:   CB_FXS 317, 600            ; infantry run over
        CB_FXS 0, CB_FXEND
cb_fx23:   CB_FXS 318, 600            ; run over
        CB_FXS 0, CB_FXEND
cb_fx_steps_end:
        ASSERT (cb_fx_steps_end - cb_fx_steps) / 4 < 255

; ======================================================== the bank's statics

cb_ft_mode:        DB 0
cb_ft_unit:        DW 0
cb_ft_struct:      DW 0
cb_ft_prio:        DW 0
cb_as_tinfo:       DW 0
cb_as_d:           DW 0
cb_fe_mode:        DB 0
cb_fe_range:       DW 0
cb_fe_air:         DB 0
cb_fe_seen:        DB 0
cb_fe_slot:        DB 0
cb_fe_home_pos:    DS 4
cb_bs_mode:        DB 0
cb_bs_range:       DW 0
cb_bs_best:        DW 0
cb_bs_score:       DW 0
cb_bs_slot:        DB 0
cb_bs_centre:      DS 4
cb_st_ref:         DW 0
cb_ud_dmg:         DW 0
cb_ud_tries:       DB 0
cb_ud_sq:          DW 0
cb_eg_sq:          DW 0
cb_eg_land:        DB 0
cb_eg_ov:          DB 0
cb_fx_d:           DW 0
cb_uf_tgt:         DW 0
cb_uf_face:        DB 0
cb_uf_tpos:        DS 4
cb_uf_dist:        DW 0
cb_uf_dmg:         DW 0
cb_uf_sound:       DB 0
cb_uf_kind:        DB 0
cb_uf_twice:       DB 0
cb_uf_proj:        DW 0
cb_de_ref:         DW 0
cb_de_sq:          DW 0
cb_de_pos:         DS 4
cb_fp_type:        DB 0
cb_fp_house:       DB 0
cb_fp_dmg:         DW 0
cb_fp_tgt:         DW 0
cb_fp_org:         DS 4
cb_fp_tpos:        DS 4
cb_fp_dir:         DB 0
cb_tr_centre:      DB 0
cb_tr_r:           DB 0
cb_tr_a:           DB 0
cb_tr_dx:          DW 0
cb_tr_dy:          DW 0
cb_tr_y:           DW 0
cb_fs_frame:       DW 0
cb_fs_ticks:       DW 0
cb_fs_best:        DW 0        ; fx_explosion_start: the entry to retire
cb_fs_least:       DW 0        ; and its ticks left
cb_mx_in_a:        DB 0
cb_mx_in_hl:       DW 0
cb_mx_in_de:       DW 0
; map_make_explosion's statics, saved on the stack round every call
cb_mx_vars:
cb_mx_type:        DB 0
cb_mx_reach:       DB 0
cb_mx_pos:         DS 4
cb_mx_dmg:         DW 0
cb_mx_cause:       DW 0
cb_mx_delay:       DW 0
cb_mx_sq:          DW 0
cb_mx_wref:        DW 0
cb_mx_i:           DB 0
cb_mx_pad:         DB 0
CB_MX_WORDS        EQU ($ - cb_mx_vars) / 2
