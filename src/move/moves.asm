; moves.asm - bank MOVE: the unit loop (S1), movement, turning and path
; finding (S3), and the UNIT.EMC routines that move.  Owner: the MOVE
; subsystem (see .claude/docs/port-code.md).  Every label in the
; "interface" sections is called by other banks: keep the name and the
; registers.  The path finder is in moves2.asm (bank MOVE2).
;
; The 68000 code is orig/sega/src/rom04.asm (and rom00/rom01 for the
; shared routines); each routine's header gives its address.  Where the
; port changes what the cartridge does, the comment says so and why
; (S1/S3/S7 "the cartridge's own bugs").
;
; Conventions: IX = the unit (window 1).  mv_info = its type's record in
; tbl_unit_info, loaded by every entry point (mv_load_info).  A call to
; another subsystem goes through MVCALL, which keeps IX.

; A far call that keeps IX (the callee may use it for its own records).
    MACRO MVCALL _fn_
        push ix
        FCALL _fn_
        pop ix
    ENDM

; ============================================================ the unit loop

; unit_tick_all ($043784): every unit, every pass (S1 "Units").  The six
; timers first, then each unit the find array holds, in the order made.
;
; The port walks the find array with a bitmap of the units already
; visited, so a unit freed during the pass (it closes the gap under the
; cursor) does not make the loop pass over the next one - S7's "fix:
; iterate a snapshot or by slot".  A unit made during the pass is appended
; and ticked in the same pass, as on the cartridge.  The Start/A/B cut
; (inputEvent) is the UI's; the port has none yet.
unit_tick_all:
        ; the clock, read once: the interrupt moves it
        di
        ld  hl, (timer_game)
        ld  (mv_uta_now), hl
        ld  hl, (timer_game + 2)
        ld  (mv_uta_now + 2), hl
        ei
        ld  hl, mv_tick_unit_move
        ld  c, 3
        call mv_uta_timer
        ld  (mv_uta_fmove), a
        ld  hl, mv_tick_unit_rot
        ld  c, 2
        call mv_uta_timer
        ld  (mv_uta_frot), a
        ld  hl, mv_tick_unit_turret
        ld  c, 20
        call mv_uta_timer
        ld  (mv_uta_fturret), a
        ld  hl, mv_tick_unit_script
        ld  c, 5
        call mv_uta_timer
        ld  (mv_uta_fscript), a
        ld  hl, mv_tick_unit_anim
        ld  c, 5
        call mv_uta_timer
        ld  (mv_uta_fanim), a
        ld  hl, mv_tick_unit_dev
        ld  c, 60
        call mv_uta_timer
        ld  (mv_uta_fdev), a
        ; nobody visited yet
        ld  hl, mv_uta_done
        ld  b, 13
        xor a
mv_uta_clr:
        ld  (hl), a
        inc hl
        djnz mv_uta_clr
        ld  (mv_uta_pos), a
mv_uta_next:
        ; The visited units are a prefix of the find array (it keeps the
        ; order made, gaps closed), so the next is the first not visited:
        ; back up over any that slid down under the cursor, then forward.
        ld  a, (mv_uta_pos)
        ld  c, a
mv_uta_back:
        ld  a, c
        or  a
        jr  z, mv_uta_fwd
        dec a
        call mv_uta_slot_at
        call mv_uta_done_bit
        jr  nz, mv_uta_fwd
        dec c
        jr  mv_uta_back
mv_uta_fwd:
        ld  a, (unit_find_count)
        ld  b, a
        ld  a, c
        cp  b
        ret nc                  ; c >= count: the pass is over
        call mv_uta_slot_at
        ld  (mv_uta_slot), a
        call mv_uta_done_bit
        jr  z, mv_uta_take
        inc c
        jr  mv_uta_fwd
mv_uta_take:
        ld  a, (hl)
        or  b
        ld  (hl), a
        inc c
        ld  a, c
        ld  (mv_uta_pos), a
        ld  a, (mv_uta_slot)
        call unit_ptr
        push hl
        pop ix
        ; the search passes over a unit off the map (unit_find_next)
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, mv_uta_go
        ld  a, (validate_strict)
        or  a
        jr  z, mv_uta_next
mv_uta_go:
        ld  (mv_script_unit), ix
        call mv_uta_unit
        jr  mv_uta_next

; A = a position in the find array -> A = the slot there.  Clobbers DE, HL.
mv_uta_slot_at:
        ld  e, a
        ld  d, 0
        ld  hl, unit_find
        add hl, de
        ld  a, (hl)
        ret

; A = a slot -> HL = its byte of mv_uta_done, B = its bit, NZ if visited.
; Keeps C.
mv_uta_done_bit:
        ld  b, a
        and 7
        ld  hl, mv_uta_masks
        add a, l
        ld  l, a
        adc a, h
        sub l
        ld  h, a
        ld  a, (hl)
        push af
        ld  a, b
        rrca
        rrca
        rrca
        and $1F
        ld  hl, mv_uta_done
        add a, l
        ld  l, a
        adc a, h
        sub l
        ld  h, a
        pop af
        ld  b, a
        and (hl)
        ret

mv_uta_masks:
        DB  1, 2, 4, 8, 16, 32, 64, 128

; HL -> a timer's due time, C = its period -> A = 1 if it fires this pass
; (the clock at or past it; the new due time is the clock + the period),
; else 0.  Clobbers B, DE, HL.
mv_uta_timer:
        ld  de, mv_uta_now
        push hl
        ld  b, 4
        or  a
mv_ut_cmp: ld  a, (de)
        sbc a, (hl)
        inc de
        inc hl
        djnz mv_ut_cmp
        pop hl
        ld  a, 0
        ret c
        ld  de, mv_uta_now
        ld  a, (de)
        add a, c
        ld  (hl), a
        ld  b, 3
mv_ut_add: inc de
        inc hl
        ld  a, (de)
        adc a, 0
        ld  (hl), a
        djnz mv_ut_add
        ld  a, 1
        ret

; One unit's work (S1 steps 1-13, $04384E-$043CC4).  IX = the unit.
mv_uta_unit:
        call mv_load_info
        ; 1. Starport cargo: a Frigate still carrying (flags2 bit 9) is held
        ; while units bought are pending; otherwise the bit goes.  (The
        ; cartridge then ticks the next unit without this test; the port
        ; just goes on to it.)
        ld  a, (ix + O_TYPE)
        cp  UNIT_FRIGATE
        jr  nz, mv_uu_fremen
        bit 1, (ix + O_FLAGS2 + 1)
        jr  z, mv_uu_fremen
    IF EXIST st_starport_cargo_pending   ; STRUCT's (S6 $FFC348)
        ld  hl, (st_starport_cargo_pending)
        ld  a, h
        or  l
        ret nz
    ENDIF
        res 1, (ix + O_FLAGS2 + 1)
mv_uu_fremen:
        ; 2. Fremen soldiers below twice their type's hit points - always,
        ; the cartridge's kept bug ($0438B8) - Hunt with a new target
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_FREMEN
        jr  nz, mv_uu_fx
        ld  a, (ix + O_TYPE)
        cp  UNIT_TROOPERS
        jr  z, mv_uu_fr1
        cp  UNIT_TROOPER
        jr  nz, mv_uu_fx
mv_uu_fr1: ld  a, UI_hitpoints
        call mv_info_word
        add hl, hl
        ex  de, hl
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        call mv_lt_signed
        jr  nc, mv_uu_fx
        ld  a, (ix + U_ACTION)
        cp  ORDER_HUNT
        jr  z, mv_uu_fx
        ld  a, ORDER_HUNT
        MVCALL unit_give_order
        ld  a, 4
        MVCALL unit_find_target
        MVCALL unit_set_target
mv_uu_fx:
        ; 3. an effect animation on the unit (flags2 bit 11, the flash of
        ; an attack's target): fx_anim_tick $00A786 (bank MOVE2); when it
        ; has run out the bit goes
        bit 3, (ix + O_FLAGS2 + 1)
        jr  z, mv_uu_fx1
        MVCALL fx_anim_tick
        jr  nz, mv_uu_fx1
        res 3, (ix + O_FLAGS2 + 1)
mv_uu_fx1:
        ; 4. off the map: nothing more
        bit OF_NOTONMAP, (ix + O_FLAGS)
        ret nz
        ; 5. turret aim: a turret turns at the target
        ld  a, (mv_uta_fturret)
        or  a
        jr  z, mv_uu_move
        ld  a, (ix + U_TARGETATTACK)
        or  (ix + U_TARGETATTACK + 1)
        jr  z, mv_uu_move
        call mv_has_turret
        jr  z, mv_uu_move
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        call mv_dir_to_ref
        ld  bc, $0001           ; not at once, the turret
        call unit_set_facing
mv_uu_move:
        ; 6. movement, then the fire delay; a homing projectile steers
        ld  a, (mv_uta_fmove)
        or  a
        jr  z, mv_uu_rot
        call mv_unit_move_tick
        bit OF_USED, (ix + O_FLAGS)
        ret z                   ; the port: a unit its move removed is done
        call mv_load_info
        ld  a, (ix + U_FIREDELAY)
        or  a
        jr  z, mv_uu_rot
        call mv_mt
        cp  4
        jr  nz, mv_uu_fd
        ld  a, UI_flags + 1
        call mv_info_byte
        bit 7, a                ; isNormalUnit: not a homing projectile
        jr  nz, mv_uu_fd
        ; at the target if it is a flyer, else at the destination
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        push hl
        call mv_ref_unit
        jr  z, mv_uu_hdest
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, mv_uu_hdest
        pop hl
        call mv_dir_to_ref
        jr  mv_uu_hface
mv_uu_hdest:
        pop hl
        push ix
        pop de
        ld  hl, U_DEST_Y
        add hl, de
        ex  de, hl
        call mv_dir_to_de
mv_uu_hface:
        ld  bc, 0
        call unit_set_facing
mv_uu_fd:  dec (ix + U_FIREDELAY)
mv_uu_rot:
        ; 7. rotation: the hull a step, the turret too
        ld  a, (mv_uta_frot)
        or  a
        jr  z, mv_uu_dev
        ld  c, 0
        call unit_turn_step
        call mv_has_turret
        jr  z, mv_uu_dev
        ld  c, 1
        call unit_turn_step
mv_uu_dev:
        ; 8. deviation wears off (S4)
        ld  a, (mv_uta_fdev)
        or  a
        jr  z, mv_uu_back
        ld  a, 1
        MVCALL unit_deviation_wear
mv_uu_back:
        ; 9. back on the map: a ground unit whose square names nothing
        call mv_mt
        cp  4
        jr  z, mv_uu_anim
        call mv_own_sq
        call mv_object_at
        jr  nz, mv_uu_anim
        ld  a, 1
        MVCALL unit_update_map
mv_uu_anim:
        ; 10. animation
        ld  a, (mv_uta_fanim)
        or  a
        jp  z, mv_uu_script
        ld  l, (ix + U_ANIMTIMER)
        ld  h, (ix + U_ANIMTIMER + 1)
        ld  a, h
        or  l
        jr  z, mv_uu_an0
        dec hl
        ld  (ix + U_ANIMTIMER), l
        ld  (ix + U_ANIMTIMER + 1), h
        jr  mv_uu_script
mv_uu_an0: ; a foot soldier on the move steps its walking frame
        call mv_mt
        or  a
        jr  nz, mv_uu_harv
        ld  a, (ix + U_SPEED)
        or  a
        jr  z, mv_uu_harv
        ld  a, (ix + U_SPRITEOFS)
        bit 7, a
        jr  nz, mv_uu_harv
        and $3F
        inc a
        ld  (ix + U_SPRITEOFS), a
        ld  a, UI_animationSpeed
        call mv_info_word
        ld  de, 5
        call sdiv16
        ld  (ix + U_ANIMTIMER), l
        ld  (ix + U_ANIMTIMER + 1), h
mv_uu_harv:
        ; a Harvester harvesting on spice steps its three-frame overlay
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, mv_uu_script
        ld  a, (ix + U_ACTION)
        cp  ORDER_HARVEST
        jr  nz, mv_uu_hide
        call mv_own_sq
        call map_landscape
        cp  LST_SPICE
        jr  z, mv_uu_hv
        cp  LST_THICKSPICE
        jr  nz, mv_uu_hide
mv_uu_hv:  ld  a, (ix + U_SPRITEOFS)
        inc a
        ld  (ix + U_SPRITEOFS), a
        jp  m, mv_uu_hv1
        cp  3
        jr  c, mv_uu_hv1
        ld  (ix + U_SPRITEOFS), 0
mv_uu_hv1: call mv_harvest_bit
        or  (hl)
        ld  (hl), a
        ld  (ix + U_ANIMTIMER), 1
        ld  (ix + U_ANIMTIMER + 1), 0
        jr  mv_uu_script
mv_uu_hide:
        call mv_harvest_bit
        cpl
        and (hl)
        ld  (hl), a
mv_uu_script:
        ; 11. the script: count its delay down, or run it for 49
        ; instructions (on screen, or scriptNoSlowdown) or 17
        ld  a, (mv_uta_fscript)
        or  a
        jr  z, mv_uu_queue
        ld  l, (ix + O_DELAY)
        ld  h, (ix + O_DELAY + 1)
        ld  a, h
        or  l
        jr  z, mv_uu_sc1
        dec hl
        ld  (ix + O_DELAY), l
        ld  (ix + O_DELAY + 1), h
        jr  mv_uu_queue
mv_uu_sc1: ld  a, (ix + O_SCRIPT + SC_PC)
        or  (ix + O_SCRIPT + SC_PC + 1)
        jr  z, mv_uu_queue         ; not loaded: a stopped script stays stopped
        ld  b, 49
        ld  a, UI_objectFlags + 1
        call mv_info_byte
        bit 3, a                ; scriptNoSlowdown
        jr  nz, mv_uu_sc2
        call mv_on_screen
        jr  nz, mv_uu_sc2
        ld  b, 17
mv_uu_sc2: ld  a, (player_house)   ; variable 3 = the player's house
        ld  (ix + O_SCRIPT + SC_VARS + 6), a
        ld  (ix + O_SCRIPT + SC_VARS + 7), 0
        push ix
        ld  de, O_SCRIPT
        add ix, de
        FCALL emc_run_budget
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
mv_uu_queue:
        ; 12. the queued order, once the unit is on a square
        ld  a, (ix + U_NEXTACTION)
        cp  $FF
        jr  z, mv_uu_pend
        ld  b, a
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jr  nz, mv_uu_pend
        ld  a, b
        MVCALL unit_give_order
        ld  (ix + U_NEXTACTION), $FF
mv_uu_pend:
        ; 13. a pending deploy or self-destruct (flags2 bit 7): once its
        ; animation has run out (fx_anim_tick, bank MOVE2) the MCV deploys,
        ; the Devastator is ordered to Die ($043C72)
        bit 7, (ix + O_FLAGS2)
        ret z
        MVCALL fx_anim_tick
        ret nz
        res 7, (ix + O_FLAGS2)
        ld  a, (ix + O_TYPE)
        cp  UNIT_MCV
        jr  nz, mv_uu_pd1
        MVCALL unit_deploy_mcv
        or  a
        jr  nz, mv_uu_pd1
        ld  a, $2F
        MVCALL snd_effect
mv_uu_pd1: ld  a, (ix + O_TYPE)
        cp  UNIT_DEVASTATOR
        ret nz
        ld  a, ORDER_DIE
        MVCALL unit_give_order
        ret

; view_square_visible ($005DE6): NZ if the unit's square is on screen,
; with the cartridge's margins: rows top..top+7, columns left..left+10.
mv_on_screen:
        ld  hl, (view_y)
        add hl, hl
        add hl, hl
        add hl, hl
        ld  b, h                ; the top row (view_y / 32)
        ld  a, (ix + O_POS_Y + 1)
        sub b
        cp  8
        jr  nc, mv_mos_no
        ld  hl, (view_x)
        add hl, hl
        add hl, hl
        add hl, hl
        ld  b, h
        ld  a, (ix + O_POS_X + 1)
        sub b
        cp  11
        jr  nc, mv_mos_no
        or  1
        ret
mv_mos_no: xor a
        ret

; -> HL = the unit's byte of mv_harvest_shown, A = its bit.  Clobbers B, DE.
mv_harvest_bit:
        ld  a, (ix + O_INDEX)
        call mv_uta_done_bit       ; the same layout as mv_uta_done
        ld  de, mv_harvest_shown - mv_uta_done
        add hl, de
        ld  a, b
        ret

; ============================================================ movement

; mv_unit_move_tick ($047FBA): IX = the unit; one movement tick (S3).  A foot
; or tracked unit still turning to its step only turns (Mega Drive only);
; otherwise the fraction accumulates and a carry moves the unit.
mv_unit_move_tick:
        call mv_load_info
        call mv_mt
        cp  2
        jr  nc, mv_umt_1
        ld  a, (ix + U_OR0_TARGET)
        cp  (ix + U_OR0_CURRENT)
        jr  z, mv_umt_1
        ld  c, 0
        jp  unit_turn_step
mv_umt_1:  ld  a, (ix + U_SPEED)
        or  a
        ret z
        ld  a, (ix + U_SPEEDREM)
        add a, (ix + U_SPEEDTICK)
        ld  (mv_umt_rem), a
        jr  nc, mv_umt_2
        ; a carry: move min(speed * 16, the distance left + 16)
        call mv_pos_ptr
        push hl
        ld  de, U_DEST_Y - O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        call tile_distance
        ld  de, 16
        add hl, de
        ex  de, hl
        ld  l, (ix + U_SPEED)
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        or  a
        sbc hl, de
        add hl, de
        jr  c, mv_umt_3
        ex  de, hl
mv_umt_3:  ld  a, h                ; tile_move_by_direction takes at most 255
        or  a
        ld  a, l
        jr  z, mv_umt_4
        ld  a, 255
mv_umt_4:  call unit_move
mv_umt_2:  ld  a, (mv_umt_rem)
        ld  (ix + U_SPEEDREM), a
        ret

; unit_set_speed ($047F44): IX = the unit, A = the speed asked for (0 stops
; it).  speed = v >> 4 and speedPerTick 255 when that is nonzero, else
; speed 1 and speedPerTick (v << 4) & 255, where v = movingSpeedFactor * s
; rounded by math_mul_shr8 (+$50, not the PC's truncation).  Clobbers
; A, BC, DE, HL.
unit_set_speed:
        ld  (ix + U_SPEED), 0
        ld  (ix + U_SPEEDREM), 0
        ld  (ix + U_SPEEDTICK), 0
        or  a
        jr  z, mv_uss_zero
        ld  (ix + U_MOVINGSPEED), a
        ld  e, a
        ld  d, 0
        push de
        call mv_load_info
        ld  a, UI_movingSpeedFactor
        call mv_info_word
        pop de
        call mul_shr8           ; HL = v
        ld  a, l
        and $F0
        or  h
        jr  z, mv_uss_small
        ; v >> 4, its low byte
        ld  a, l
        rra
        rra
        rra
        rra
        and $0F
        ld  l, a
        ld  a, h
        add a, a
        add a, a
        add a, a
        add a, a
        or  l
        ld  (ix + U_SPEED), a
        ld  (ix + U_SPEEDTICK), $FF
        ret
mv_uss_small:
        ld  (ix + U_SPEED), 1
        ld  a, l
        add a, a
        add a, a
        add a, a
        add a, a
        ld  (ix + U_SPEEDTICK), a
        ret
mv_uss_zero:
        ld  (ix + U_MOVINGSPEED), 0
        ret

; unit_set_facing ($047E1C): IX = the unit, C = 0 the hull / 1 the turret,
; A = the facing, B = nonzero at once.  Otherwise the turn speed is the
; type's turningSpeed * 4, negative when the short way round is
; anticlockwise.  Clobbers A, DE, HL.
unit_set_facing:
        push bc
        call mv_orient_ptr      ; HL -> speed, target, current
        pop bc
        ld  (hl), 0
        inc hl
        ld  (hl), a
        inc hl
        inc b
        dec b
        jr  z, mv_usf_turn
        ld  (hl), a
        ret
mv_usf_turn:
        sub (hl)                ; (wanted - current) & 255
        ret z
        ld  d, a
        push hl
        call mv_load_info
        ld  a, UI_turningSpeed
        call mv_info_byte
        add a, a
        add a, a                ; the rate, turningSpeed * 4
        pop hl
        dec hl
        dec hl                  ; -> the speed
        ld  e, a
        ; the 68000 negates when -128 < diff < 0 or diff > 128 (diff =
        ; wanted - current, 0-255 each), which for the 8-bit difference is
        ; exactly "above 128"
        ld  a, d
        cp  129
        ld  a, e
        jr  c, mv_usf_pos
        neg
mv_usf_pos:
        ld  (hl), a
        ret

; C = 0 / 1 -> HL -> the hull's (+$68) or the turret's (+$6B) three bytes.
; Keeps A.
mv_orient_ptr:
        push de
        push ix
        pop hl
        ld  de, U_OR0_SPEED
        add hl, de
        pop de
        dec c
        ret nz
        inc hl
        inc hl
        inc hl
        ret

; unit_turn_step ($047E94): IX = the unit, C = 0 the hull / 1 the turret.
; One step of the turn; within one step it snaps to the target and stops.
; (The cartridge then redraws when the frame drawn changes; the renderer
; here draws from the record.)  Clobbers A, BC, HL.
unit_turn_step:
        push de
        call mv_orient_ptr
        pop de
        ld  a, (hl)
        or  a
        ret z
        ld  b, a                ; the speed, signed
        inc hl
        ld  a, (hl)             ; the target
        inc hl
        sub (hl)                ; target - current, 8 bits
        cp  129
        jr  c, mv_uts_1
        neg                     ; wrapped to -128..128 and made positive
mv_uts_1:  ld  c, a                ; how far is left
        ld  a, b
        bit 7, a
        jr  z, mv_uts_2
        neg
mv_uts_2:  cp  c                   ; |speed| >= left: arrive
        jr  nc, mv_uts_snap
        ld  a, (hl)
        add a, b
        ld  (hl), a
        ret
mv_uts_snap:
        dec hl
        ld  a, (hl)
        inc hl
        ld  (hl), a
        dec hl
        dec hl
        ld  (hl), 0
        ret

; unit_start_step ($0476AE): IX = the unit -> A = 1 if a step into the
; square it faces has started, 0 if that square cannot be entered (S3 "A
; step").
unit_start_step:
        call mv_load_info
        ; the facing squared to an eighth: the hull at once, the turret after
        ld  a, (ix + U_OR0_CURRENT)
        add a, 16
        and $E0
        ld  (mv_ss_face), a
        ld  bc, $0100
        call unit_set_facing
        ld  a, (mv_ss_face)
        ld  bc, $0001
        call unit_set_facing
        ; the square ahead: map_pos_step $019AD8 (+-256 an axis)
        ld  a, (mv_ss_face)
        rlca
        rlca
        rlca
        and 7
        ld  (mv_ss_dir), a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_map_pos_step_y
        add hl, de
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        add hl, bc
        ld  (mv_ss_new), hl
        ld  hl, tbl_map_pos_step_x
        add hl, de
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        add hl, bc
        ld  (mv_ss_new + 2), hl
        ld  hl, mv_ss_new
        call pos_square
        ld  (mv_ss_sq), hl
        ld  (ix + U_DISTDEST), $FF
        ld  (ix + U_DISTDEST + 1), $7F
        ; can it be entered?  Above 255, or -1: no
        ld  a, (mv_ss_dir)
        call unit_tile_enter_score
        ld  a, h
        and l
        inc a
        jr  z, mv_ss_no
        bit 7, h
        jr  nz, mv_ss_ok
        ld  a, h
        or  a
        jr  z, mv_ss_ok
mv_ss_no:  xor a
        ret
mv_ss_ok:  call mv_load_info
        ; the speed of the ground ahead for the movement type (a structure
        ; counts as concrete; a Saboteur on a wall gets 255)
        ld  hl, (mv_ss_sq)
        call map_landscape
        cp  LST_STRUCTURE
        jr  nz, mv_ss_1
        ld  a, LST_CONCRETE
mv_ss_1:   ld  (mv_ss_lt), a
        call mv_ground_speed    ; A = the speed, 0 for no ground
        ld  (mv_ss_speed), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, mv_ss_2
        ld  a, (mv_ss_lt)
        cp  LST_WALL
        jr  nz, mv_ss_2
        ld  a, 255
        ld  (mv_ss_speed), a
mv_ss_2:   ; isWobbling: cleared, then set by the ground (the PC never clears it)
        res OF_WOBBLING, (ix + O_FLAGS)
        ld  a, (mv_ss_lt)
        cp  LANDSCAPE_COUNT
        jr  nc, mv_ss_3
        call landscape_info
        ld  de, LS_letUnitWobble
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  z, mv_ss_3
        set OF_WOBBLING, (ix + O_FLAGS)
mv_ss_3:   ; below half its hit points a ground unit loses a quarter
        call mv_mt
        cp  4
        jr  z, mv_ss_4
        ld  a, UI_hitpoints
        call mv_info_word
        sra h
        rr  l
        ex  de, hl              ; DE = half the type's
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        call mv_lt_signed       ; hp < half: carry
        jr  nc, mv_ss_4
        ld  a, (mv_ss_speed)
        ld  b, a
        srl a
        srl a
        neg
        add a, b
        ld  (mv_ss_speed), a
mv_ss_4:   ld  a, (mv_ss_speed)
        call unit_set_speed
        ; the square ahead is claimed (not by the Sandworm)
        call mv_mt
        cp  5
        jr  z, mv_ss_5
        ld  hl, mv_ss_new
        ld  de, claim_pos
        ld  bc, 4
        ldir
        ld  a, 1
        MVCALL unit_update_map
        ld  hl, 0
        ld  (claim_pos), hl
        ld  (claim_pos + 2), hl
mv_ss_5:   ; currentDestination = the square ahead; the deviation clock -10
        ld  hl, (mv_ss_new)
        ld  (ix + U_DEST_Y), l
        ld  (ix + U_DEST_Y + 1), h
        ld  hl, (mv_ss_new + 2)
        ld  (ix + U_DEST_X), l
        ld  (ix + U_DEST_X + 1), h
        ld  a, 10
        MVCALL unit_deviation_wear
        ; the step (Mega Drive only): 32 straight, 40 diagonal, through the
        ; sine table (tile_dir_offset_y $011720, _x $01175E)
        ld  a, (mv_ss_face)
        and $30                 ; (f & $F0) is 0, 64, 128 or 192?
        ld  c, 32
        jr  z, mv_ss_6
        ld  c, 40
mv_ss_6:   ld  a, (ix + U_OR0_CURRENT)
        push bc
        ld  e, a
        ld  d, 0
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        call mv_scaled          ; HL = (A * C + 64) >> 7
        ld  (ix + U_STEP_Y), l
        ld  (ix + U_STEP_Y + 1), h
        pop bc
        ld  e, (ix + U_OR0_CURRENT)
        ld  d, 0
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        call mv_scaled
        ld  (ix + U_STEP_X), l
        ld  (ix + U_STEP_X + 1), h
        ld  a, 1
        ret

; A = a signed byte, C = an unsigned byte -> HL = (A * C + 64) >> 7,
; arithmetic.  Clobbers A, B, DE.
mv_scaled:
        call smul_d8
        ld  de, $40
        add hl, de
        jp  sar7_hl

; A = a landscape type -> A = its speed for the unit's movement type (0
; where it cannot go, and for a type off the table).  Clobbers DE, HL.
mv_ground_speed:
        cp  LANDSCAPE_COUNT
        jr  nc, mv_mgs_none
        call landscape_info
        ld  de, LS_movementSpeed
        add hl, de
        push hl
        call mv_mt
        pop hl
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, (hl)
        ret
mv_mgs_none:
        xor a
        ret

; unit_move ($04607C): IX = the unit, A = the distance (S3 "Moving").
; -> A = 1 when the step is done (arrived, removed or burst), else 0.
unit_move:
        ld  (mv_um_dist), a
        xor a
        ld  (mv_um_ret), a
        ld  (mv_um_bloom), a
        bit OF_USED, (ix + O_FLAGS)
        ret z
        call mv_load_info
        call mv_mt
        cp  4
        jr  nz, mv_um_ground
        ld  a, (ix + O_TYPE)
        or  a
        jr  nz, mv_um_fly
        ; a Carryall (Mega Drive only) whose claim is a unit under Attack or
        ; Hunt lets go of it and does not move this time
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        call mv_ref_unit
        jr  z, mv_um_fly
        ld  de, U_ACTION
        add hl, de
        ld  a, (hl)
        or  a
        jr  z, mv_um_letgo
        cp  ORDER_HUNT
        jr  nz, mv_um_fly
mv_um_letgo:
        MVCALL obj_var4_clear
        ld  (ix + O_SCRIPT + SC_VARS + 8), 0
        ld  (ix + O_SCRIPT + SC_VARS + 9), 0
        xor a
        ret
mv_um_fly: ; along the hull's facing
        call mv_pos_to_new
        ld  a, (mv_um_dist)
        ld  c, a
        ld  a, (ix + U_OR0_CURRENT)
        ld  hl, mv_um_new
        call tile_move_by_direction
        jr  mv_um_moved
mv_um_ground:
        ; the fixed step, each word masked to $3FFF (tile_add_offset
        ; $01179A); the distance is not used
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        ld  e, (ix + U_STEP_Y)
        ld  d, (ix + U_STEP_Y + 1)
        add hl, de
        ld  a, h
        and $3F
        ld  h, a
        ld  (mv_um_new), hl
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        ld  e, (ix + U_STEP_X)
        ld  d, (ix + U_STEP_X + 1)
        add hl, de
        ld  a, h
        and $3F
        ld  h, a
        ld  (mv_um_new + 2), hl
mv_um_moved:
        ; the same place: nothing happens
        call mv_pos_ptr
        ld  de, mv_um_new
        ld  b, 4
mv_um_same:
        ld  a, (de)
        cp  (hl)
        jr  nz, mv_um_differs
        inc hl
        inc de
        djnz mv_um_same
        xor a
        ret
mv_um_differs:
        ; off the map (bit 14 or 15 of a word)
        ld  a, (mv_um_new + 1)
        ld  b, a
        ld  a, (mv_um_new + 3)
        or  b
        and $C0
        jr  z, mv_um_on
        ld  a, UI_flags
        call mv_info_byte
        bit 7, a                ; mustStayInMap
        jr  nz, mv_um_stay
        MVCALL unit_remove
        ld  a, 1
        ret
mv_um_stay:
        ; stay, and turn up to 15 further
        call mv_pos_to_new
        call random
        and 15
        add a, (ix + U_OR0_CURRENT)
        ld  bc, 0
        call unit_set_facing
        ; a byScenario craft carrying nothing, with no claim, leaves
        bit OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
        jr  z, mv_um_on
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, mv_um_on
        ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        or  (ix + O_SCRIPT + SC_VARS + 9)
        jr  nz, mv_um_on
        MVCALL unit_remove
        ld  a, 1
        ret
mv_um_on:
        ; the wobble (drawing only)
        ld  (ix + U_WOBBLE), 0
        ld  a, UI_flags
        call mv_info_byte
        bit 4, a                ; canWobble
        jr  z, mv_um_nowob
        bit OF_WOBBLING, (ix + O_FLAGS)
        jr  z, mv_um_nowob
        call random
        and 7
        ld  (ix + U_WOBBLE), a
mv_um_nowob:
        call mv_um_dist_new
        ld  hl, mv_um_new
        call pos_square
        ld  (mv_um_sq), hl
        ; crushing: a tracked unit near its step's end runs over an enemy
        ; soldier on the new square
        ld  a, UI_flags
        call mv_info_byte
        bit 5, a                ; isTracked
        jp  z, mv_um_nocrush
        ld  hl, (mv_um_d3)
        ld  de, 48
        call mv_lt_signed
        jp  nc, mv_um_nocrush
        ld  hl, (mv_um_sq)
        call mv_unit_at
        jp  z, mv_um_nocrush
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, mv_um_nocrush
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jr  z, mv_um_nocrush
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jr  nz, mv_um_nocrush
        ; math_near_256 $0043FA: within 256 on both axes.  The port's fix:
        ; the answer is 1, not y - 256 (which is 0 at y = $100)
        ld  l, (iy + O_POS_Y)
        ld  h, (iy + O_POS_Y + 1)
        ld  e, (ix + O_POS_Y)
        ld  d, (ix + O_POS_Y + 1)
        call mv_within_256
        jr  nc, mv_um_nocrush
        ld  l, (iy + O_POS_X)
        ld  h, (iy + O_POS_X + 1)
        ld  e, (ix + O_POS_X)
        ld  d, (ix + O_POS_X + 1)
        call mv_within_256
        jr  nc, mv_um_nocrush
        ; the victim: deselected, forgotten, crushed (variable 1 = 1), Die
        ld  a, (unit_selected)
        cp  (iy + O_INDEX)
        jr  nz, mv_um_cr1
        ld  a, $FF
        ld  (unit_selected), a
mv_um_cr1: push ix
        push iy
        pop ix
        MVCALL unit_drop_references
        ld  (ix + O_SCRIPT + SC_VARS + 2), 1
        ld  (ix + O_SCRIPT + SC_VARS + 3), 0
        ld  a, ORDER_DIE
        MVCALL unit_give_order
        pop ix
mv_um_nocrush:
        ; off the map while it moves
        xor a
        MVCALL unit_update_map
        call mv_mt
        cp  4
        jr  nz, mv_um_1
        ld  a, (ix + O_FLAGS)
        xor 1 << OF_ANIMFLIP
        ld  (ix + O_FLAGS), a
mv_um_1:   call mv_um_dist_new
        ld  a, (ix + O_TYPE)
        cp  UNIT_SONICBLAST
        jp  nz, mv_um_notsonic
        ; ---- the Sonic Blast (S4): hurts what it passes, weakens as it goes
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        sra h
        rr  l
        sra h
        rr  l
        inc hl
        ld  (mv_um_dmg), hl
        ld  hl, (mv_um_sq)
        call mv_unit_at
        jr  z, mv_um_sb_struct
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_flags
        add hl, de
        bit 3, (hl)             ; sonicProtection
        jr  nz, mv_um_sb_weak
        push ix
        push iy
        pop ix
        ld  hl, (mv_um_dmg)
        FCALL unit_damage
        pop ix
        jr  mv_um_sb_weak
mv_um_sb_struct:
        ld  hl, (mv_um_sq)
        call mv_struct_at
        jr  z, mv_um_sb_weak
        push ix
        push hl
        pop ix
        ld  hl, (mv_um_dmg)
        FCALL struct_damage
        pop ix
mv_um_sb_weak:
        call mv_load_info
        ld  a, UI_damage
        call mv_info_word
        sra h
        rr  l
        ex  de, hl
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        call mv_lt_signed
        jr  nc, mv_um_sb1
        set OF_BULLETBIG, (ix + O_FLAGS)
mv_um_sb1: ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        dec hl
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ld  a, h
        or  l
        jr  z, mv_um_sb_gone
        ld  a, (ix + U_FIREDELAY)
        or  a
        jp  nz, mv_um_write
mv_um_sb_gone:
        MVCALL unit_remove
        jp  mv_um_write
mv_um_notsonic:
        ld  hl, (mv_um_sq)
        call map_landscape
        ld  (mv_um_lt), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_BULLET
        jr  nz, mv_um_arr
        ; ---- a bullet meets a wall, a structure or a mountain (a
        ; structure's bullet passes over its own house's)
        ld  a, (mv_um_lt)
        cp  LST_WALL
        jr  z, mv_um_bw
        cp  LST_STRUCTURE
        jr  nz, mv_um_bw2
mv_um_bw:  ld  a, (ix + U_ORIGIN + 1)
        and $C0
        cp  REF_STRUCT >> 8
        jr  nz, mv_um_bw2
        ld  hl, (mv_um_sq)
        call mv_map_flags
        and 7
        cp  (ix + O_HOUSE)
        jr  nz, mv_um_bw2
        xor a
        ld  (mv_um_lt), a
mv_um_bw2: ld  a, (mv_um_lt)
        cp  LST_WALL
        jr  z, mv_um_bhit
        cp  LST_STRUCTURE
        jr  z, mv_um_bhit
        cp  LST_MOUNTAIN
        jr  z, mv_um_bhit
        cp  LST_BLOOM
        jr  nz, mv_um_arr
        ; over a bloom it sets it off; nothing else happens this move
        ld  hl, (mv_um_sq)
        ld  a, $FF
        MVCALL map_bloom_explode
        ld  a, 1
        ret
mv_um_bhit:
        call mv_new_to_pos
        call mv_pos_to_arg
        call mv_um_linked9
        call mv_um_explode_hp
        MVCALL unit_remove
        ld  a, 1
        ret
mv_um_arr:
        ; ---- arrived: past the end, or within 12 (the PC: under 16)
        ld  hl, (mv_um_d3)
        ld  e, (ix + U_DISTDEST)
        ld  d, (ix + U_DISTDEST + 1)
        ex  de, hl
        call mv_lt_signed       ; distanceToDestination < d
        jr  c, mv_um_yes
        ld  hl, (mv_um_d3)
        ld  de, 13
        call mv_lt_signed       ; d <= 12
        jp  nc, mv_um_write
mv_um_yes: ld  a, 1
        ld  (mv_um_ret), a
        ld  a, UI_flags
        call mv_info_byte
        bit 1, a                ; isBullet
        jp  z, mv_um_notbullet
        ; ---- a projectile arrives once its fireDelay is out (or type 20)
        ld  a, (ix + U_FIREDELAY)
        or  a
        jr  z, mv_um_p1
        ld  a, (ix + O_TYPE)
        cp  UNIT_AROCKET
        jp  nz, mv_um_write
mv_um_p1:  ld  a, (ix + O_TYPE)
        cp  UNIT_DEATHHAND
        jr  nz, mv_um_p2
        call mv_um_death_hand
        jp  mv_um_premove
mv_um_p2:  ld  a, UI_explosionType
        call mv_info_word
        ld  a, h
        and l
        inc a
        jp  z, mv_um_premove       ; -1: no explosion
        ld  a, (mv_um_lt)
        cp  LST_BLOOM
        jr  nz, mv_um_p3
        ld  hl, (mv_um_sq)
        ld  a, $FF
        MVCALL map_bloom_explode
        call mv_load_info
mv_um_p3:  ; impactOnSand: over empty sand under the shot, a burst of type 8
        ld  a, UI_flags + 1
        call mv_info_byte
        bit 3, a
        jr  z, mv_um_p4
        call mv_own_sq
        push hl
        call mv_map_flags
        pop hl
        bit MF_UNIT, a
        jr  nz, mv_um_p4
        call map_landscape
        or  a
        jr  nz, mv_um_p4
        call mv_new_to_arg
        ld  a, 8
        call mv_um_explode_hp
        ld  a, (ix + O_TYPE)
        cp  UNIT_BULLET
        jp  nz, mv_um_ground_new
        bit 7, (ix + O_LINKED)
        jp  nz, mv_um_premove
        jr  mv_um_ground_new
mv_um_p4:  ld  a, (ix + O_TYPE)
        cp  UNIT_ROCKET
        jr  nz, mv_um_p5
        call mv_new_to_arg
        ld  a, 3
        call mv_um_explode_hp
        jr  mv_um_ground_new
mv_um_p5:  cp  UNIT_GROCKET
        jr  nz, mv_um_p6
        ; the Deviator's gas (map_deviate_area $00ADBE, S4)
        call mv_new_to_arg
        ld  a, (ix + O_HOUSE)
        call mv_deviate_area
        jr  mv_um_premove
mv_um_p6:  cp  UNIT_MINIROCKET
        jr  nz, mv_um_p7
        call mv_new_to_arg
        ld  a, 2
        call mv_um_explode_hp
        jr  mv_um_ground_new
mv_um_p7:  ; anything else: somewhere in the square's quarter
        ; (math_random_quarter $0047A6), type 1 if linked to unit 9
        call mv_new_to_arg
        ld  de, $0003           ; rand_between 0..3
        call rand_between
        ld  b, 0
        bit 0, a
        jr  z, mv_um_q1
        ld  b, 16
mv_um_q1:  ld  c, 0
        bit 1, a
        jr  z, mv_um_q2
        ld  c, 16
mv_um_q2:  ld  hl, (arg_pos + 2)
        ld  e, b
        ld  d, 0
        add hl, de
        ld  (arg_pos + 2), hl
        ld  hl, (arg_pos)
        ld  e, c
        add hl, de
        ld  (arg_pos), hl
        ld  hl, arg_pos
        ld  de, mv_pos
        ld  bc, 4
        ldir
        call mv_um_linked9
        push af
        call mv_um_explode_hp
        pop af
        or  a
        jr  z, mv_um_premove
        call mv_pos_to_argp
        MVCALL map_explosion_ground
        jr  mv_um_premove
mv_um_ground_new:
        call mv_new_to_arg
        MVCALL map_explosion_ground
mv_um_premove:
        MVCALL unit_remove
        ld  a, (mv_um_ret)
        ret
mv_um_notbullet:
        ld  a, UI_flags
        call mv_info_byte
        bit 6, a                ; isGroundUnit
        jp  z, mv_um_write
        ; ---- a ground unit arrives: snapped onto its destination
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jr  z, mv_um_g1
        push ix
        pop hl
        ld  de, U_DEST_Y
        add hl, de
        ld  de, mv_um_new
        ld  bc, 4
        ldir
mv_um_g1:  ; +$64 = +$60, +$60 = the position it leaves; no destination
        push ix
        pop hl
        ld  de, U_PRELAST_Y
        add hl, de
        push hl
        ld  de, U_LAST_Y - U_PRELAST_Y
        add hl, de
        ex  de, hl
        pop hl
        push hl
        ld  bc, 4
        ldir
        pop de
        call mv_pos_ptr
        ld  bc, 4
        ldir
        xor a
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ; a unit that degrades loses a hit point one time in four
        bit OF_DEGRADES - 8, (ix + O_FLAGS + 1)
        jr  z, mv_um_g2
        call random
        and 3
        jr  nz, mv_um_g2
        ld  hl, 1
        MVCALL unit_damage
mv_um_g2:  ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, mv_um_g3
        ; the Saboteur blows up on a square with another unit (Mega Drive)
        ; or within 32 of its move target
        ld  hl, (mv_um_sq)
        call mv_unit_at
        jr  z, mv_um_sab2
        push ix
        pop de
        or  a
        sbc hl, de
        jr  nz, mv_um_sab_boom
mv_um_sab2:
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        ld  a, h
        or  l
        jr  z, mv_um_g3
        ld  de, mv_pos
        call ref_position
        call mv_pos_ptr
        ld  de, mv_pos
        call tile_distance
        ld  de, 32
        call mv_lt_signed
        jr  nc, mv_um_g3
mv_um_sab_boom:
        call mv_new_to_arg
        ld  a, 4
        ld  hl, 500
        ld  de, 0
        MVCALL map_make_explosion
        MVCALL unit_remove
        ld  a, 1
        ret
mv_um_g3:  xor a
        call unit_set_speed
        ; targetMove goes if it named this square
        ld  hl, (mv_um_sq)
        call ref_make_square
        ld  a, l
        cp  (ix + U_TARGETMOVE)
        jr  nz, mv_um_g4
        ld  a, h
        cp  (ix + U_TARGETMOVE + 1)
        jr  nz, mv_um_g4
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
mv_um_g4:  ; on a structure's square: it goes in
        ld  hl, (mv_um_sq)
        call mv_struct_at
        jr  z, mv_um_g5
        push hl
        push ix
        pop hl
        ld  de, U_PRELAST_Y
        add hl, de
        ld  b, 8
mv_um_g4a: ld  (hl), 0
        inc hl
        djnz mv_um_g4a
        pop iy
        MVCALL unit_enter_structure
        ld  a, 1
        ret
mv_um_g5:  ; stopping on the bloom sets it off (not the Sandworm)
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, mv_um_write
        ld  hl, (mv_um_sq)
        call map_ground_icon
        ld  de, BLOOM_ICON
        or  a
        sbc hl, de
        jr  nz, mv_um_write
        call mv_um_unbloom
mv_um_write:
        ; ---- where it now is
        ld  hl, (mv_um_d3)
        ld  (ix + U_DISTDEST), l
        ld  (ix + U_DISTDEST + 1), h
        call mv_new_to_pos
        ; (the cursor following the selected unit is the UI's)
        ld  a, 1
        MVCALL unit_update_map
        ld  a, (mv_um_bloom)
        or  a
        jr  z, mv_um_done
        ld  hl, (mv_um_sq)
        ld  a, (ix + O_HOUSE)
        MVCALL map_bloom_explode
mv_um_done:
        ld  a, (mv_um_ret)
        ret

; The square's ground icon back from mapGround (the bloom goes; S3 step 8).
mv_um_unbloom:
        ld  a, (cur_w1)
        push af
        ld  a, PG_MAPGROUND
        call map_w1
        ld  hl, (mv_um_sq)
        ld  a, h
        and $0F
        or  $40
        ld  h, a
        ld  b, (hl)
        pop af
        call map_w1
        ld  hl, (mv_um_sq)
        call map_addr
        ld  (hl), b
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        res 0, (hl)             ; ground bit 8: the byte is 0-255
        ld  a, 1
        ld  (mv_um_bloom), a
        ret

; mv_um_d3 = tile_distance(mv_um_new, currentDestination).
mv_um_dist_new:
        push ix
        pop hl
        ld  de, U_DEST_Y
        add hl, de
        ex  de, hl
        ld  hl, mv_um_new
        call tile_distance
        ld  (mv_um_d3), hl
        ret

; A = 1 if the unit's linkedID is 9, else 0.
mv_um_linked9:
        ld  a, (ix + O_LINKED)
        sub 9
        ld  a, 0
        ret nz
        inc a
        ret

; A = the type, arg_pos = where: map_make_explosion with the unit's hit
; points as the damage and its origin as the cause.
mv_um_explode_hp:
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ld  e, (ix + U_ORIGIN)
        ld  d, (ix + U_ORIGIN + 1)
        MVCALL map_make_explosion
        ret

; The Death Hand ($0464D6): seventeen blasts of the type's explosion, 200
; each, round where it came down, each with its crater; then sound $0E.
mv_um_death_hand:
        ld  hl, tbl_death_hand
        ld  b, 17
mv_udh_1:  push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; dx
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; dy
        ld  hl, (mv_um_new + 2)
        add hl, de
        ld  (mv_pos + 2), hl
        ld  hl, (mv_um_new)
        add hl, bc
        ld  a, (mv_pos + 3)     ; x below 0 borrows from y (the 68000's
        bit 7, a                ; 32-bit add)
        jr  z, mv_udh_2
        dec hl
mv_udh_2:  ld  (mv_pos), hl
        ld  a, h                ; off the map (either word past 63
        and $C0                 ; squares): skipped - S4's fix, where the
        ld  c, a                ; cartridge blasts a wrapped square
        ld  a, (mv_pos + 3)
        and $C0
        or  c
        jr  nz, mv_udh_3
        call mv_pos_to_argp
        call mv_load_info
        ld  a, UI_explosionType
        call mv_info_byte
        ld  hl, 200
        ld  de, 0
        MVCALL map_make_explosion
        call mv_pos_to_argp
        MVCALL map_explosion_ground
mv_udh_3:  pop hl
        ld  bc, 4
        add hl, bc
        pop bc
        djnz mv_udh_1
        ld  a, $0E
        MVCALL snd_effect
        ret

; map_deviate_area ($00ADBE, S4, COMBAT2): the Deviator's gas at arg_pos
; for house A.
mv_deviate_area:
        push ix
        FCALL map_deviate_area
        pop ix
        ret

; ============================================================ entering squares

; unit_tile_enter_score ($005624): IX = the unit, HL = the square, A = the
; direction as the caller passes it -> HL = the cost: 256 impossible, the
; negated unit_can_enter_structure for a structure, else 255 - the ground's
; speed (3/8 less on an odd direction, which no router ever passes).
; Clobbers everything but IX.
unit_tile_enter_score:
        ld  (mv_tes_dir), a
        ld  (mv_tes_sq), hl
        call mv_load_info
        ; off the playable map and not flying
        ld  hl, (mv_tes_sq)
        call map_valid
        jr  c, mv_tes_1
        call mv_mt
        cp  4
        jp  nz, mv_tes_wall
mv_tes_1:  ; a unit there (not this one; the Sandworm ignores units)
        ld  hl, (mv_tes_sq)
        call mv_unit_at
        jr  z, mv_tes_struct
        push ix
        pop de
        or  a
        sbc hl, de
        jr  z, mv_tes_struct
        add hl, de
        push hl
        pop iy
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, mv_tes_struct
        cp  UNIT_SABOTEUR
        jr  nz, mv_tes_2
        ; a Saboteur whose move target it is: free
        call mv_ref_of_iy_unit
        ld  a, l
        cp  (ix + U_TARGETMOVE)
        jr  nz, mv_tes_2
        ld  a, h
        cp  (ix + U_TARGETMOVE + 1)
        jr  nz, mv_tes_2
        ld  hl, 0
        ret
mv_tes_2:  ; allied (a deviated unit counts as Ordos): a wall
        call mv_house_dev
        ld  b, a
        push ix
        push iy
        pop ix
        call mv_house_dev
        pop ix
        ld  c, a
        call house_are_allied
        or  a
        jp  nz, mv_tes_wall
        ; only an enemy soldier, and only under a tracked unit or a
        ; Harvester
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, mv_tes_wall
        call mv_mt
        cp  1
        jr  z, mv_tes_struct
        cp  2
        jr  nz, mv_tes_wall
mv_tes_struct:
        ld  hl, (mv_tes_sq)
        call mv_struct_at
        jr  z, mv_tes_ground
        push hl
        pop iy
        call unit_can_enter_structure
        or  a
        jr  z, mv_tes_wall
        neg
        ld  l, a
        ld  h, $FF
        ret
mv_tes_ground:
        ld  hl, (mv_tes_sq)
        call map_landscape
        ld  (mv_tes_lt), a
        call mv_ground_speed
        ld  (mv_tes_speed), a
        ; a Saboteur against a wall of a house it is not allied with: 255
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, mv_tes_3
        ld  a, (mv_tes_lt)
        cp  LST_WALL
        jr  nz, mv_tes_3
        ld  hl, (mv_tes_sq)
        call mv_map_flags
        and 7
        ld  c, a
        ld  b, (ix + O_HOUSE)
        call house_are_allied
        or  a
        jr  nz, mv_tes_3
        ld  a, 255
        ld  (mv_tes_speed), a
mv_tes_3:  ld  a, (mv_tes_speed)
        or  a
        jr  z, mv_tes_wall
        cpl                     ; 255 - speed
        ld  l, a
        ld  h, 0
        ld  a, (mv_tes_dir)
        rra
        ret nc
        ; the diagonal term (dead for routes: S3)
        ld  a, l
        srl a
        srl a
        ld  b, a
        ld  a, l
        srl a
        srl a
        srl a
        add a, b
        neg
        add a, l
        ld  l, a
        ret
mv_tes_wall:
        ld  hl, 256
        ret

; unit_can_enter_structure ($00556A): IX = the unit, IY = the structure ->
; A = 0 no, 1 yes, 2 it is expected (S3).  A deviated unit counts as
; Ordos.  Clobbers BC, DE, HL.
unit_can_enter_structure:
        call mv_house_dev
        cp  (iy + O_HOUSE)
        jr  z, mv_uce_own
        ; another house's: a Saboteur sent at it, or a soldier at one that
        ; can be captured
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, mv_uce_1
        call mv_uce_is_target
        ld  a, 2
        ret z
mv_uce_1:  ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, mv_uce_no
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 7, (hl)             ; conquerable
        jr  z, mv_uce_no
        call mv_uce_is_target
        ld  a, 2
        ret z
        dec a
        ret
mv_uce_own:
        ; its own: only a type the structure takes; 2 if it expects this
        ; unit, 1 if nothing is linked to it
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_enterFilter
        add hl, de
        ld  a, (ix + O_TYPE)
        ld  b, a
        srl a
        srl a
        srl a
        cp  4
        jr  nc, mv_uce_no
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, b
        and 7
        ld  b, a
        ld  a, (hl)
        inc b
mv_uce_bit:
        dec b
        jr  z, mv_uce_got
        rrca
        jr  mv_uce_bit
mv_uce_got:
        rrca                    ; the type's bit into the carry
        jr  nc, mv_uce_no
        ld  a, (iy + O_SCRIPT + SC_VARS + 8)
        cp  (ix + O_INDEX)
        jr  nz, mv_uce_2
        ld  a, (iy + O_SCRIPT + SC_VARS + 9)
        cp  REF_UNIT >> 8
        jr  nz, mv_uce_2
        ld  a, 2
        ret
mv_uce_2:  ld  a, (iy + O_LINKED)
        cp  $FF
        ld  a, 1
        ret z
mv_uce_no: xor a
        ret

; Z if the unit's targetMove is a reference to the structure IY.
mv_uce_is_target:
        ld  a, (ix + U_TARGETMOVE)
        cp  (iy + O_INDEX)
        ret nz
        ld  a, (ix + U_TARGETMOVE + 1)
        cp  REF_STRUCT >> 8
        ret

; ============================================================ the helpers

mv_load_info:
        push de
        push hl
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  (mv_info), hl
        pop hl
        pop de
        ret

; A = an offset -> HL -> that byte of the unit's type record.
mv_info_ptr:
        ld  hl, (mv_info)
        add a, l
        ld  l, a
        ret nc
        inc h
        ret

; A = an offset -> A = the byte there.  Clobbers HL.
mv_info_byte:
        call mv_info_ptr
        ld  a, (hl)
        ret

; A = an offset -> HL = the word there.  Clobbers A.
mv_info_word:
        call mv_info_ptr
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ret

; -> A = the unit's movementType.  Clobbers HL.
mv_mt:
        ld  a, UI_movementType
        jr  mv_info_byte

; -> NZ if the unit's type has a turret (objectFlags bit 6).  Clobbers A, HL.
mv_has_turret:
        ld  a, UI_objectFlags
        call mv_info_byte
        and $40
        ret

; -> A = the unit's house for alliances: Ordos (2) while deviated.
mv_house_dev:
        ld  a, (ix + U_DEVIATED)
        or  a
        ld  a, 2
        ret nz
        ld  a, (ix + O_HOUSE)
        ret

; -> HL -> the unit's position.
mv_pos_ptr:
        push de
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        pop de
        ret

; -> HL = the unit's square.  Clobbers A.
mv_own_sq:
        call mv_pos_ptr
        jp  pos_square

; The unit's position into mv_um_new / mv_um_new into the position / either
; into arg_pos.  Clobber BC, DE, HL.
mv_pos_to_new:
        call mv_pos_ptr
        ld  de, mv_um_new
        ld  bc, 4
        ldir
        ret
mv_new_to_pos:
        call mv_pos_ptr
        ex  de, hl
        ld  hl, mv_um_new
        ld  bc, 4
        ldir
        ret
mv_new_to_arg:
        ld  hl, mv_um_new
        jr  mv_mna_1
mv_pos_to_arg:
        call mv_pos_ptr
mv_mna_1:  ld  de, arg_pos
        ld  bc, 4
        ldir
        ret

; mv_pos -> arg_pos.  Clobbers BC, DE, HL.
mv_pos_to_argp:
        ld  hl, mv_pos
        jr  mv_mna_1

; HL = a reference -> A = the direction from the unit to its position.
; Clobbers BC, DE, HL.
mv_dir_to_ref:
        ld  de, mv_pos
        call ref_position
        ld  de, mv_pos
        ; fall through
; DE -> a position -> A = the direction from the unit to it.
mv_dir_to_de:
        call mv_pos_ptr
        jp  tile_direction

; Carry if HL < DE, both signed.  Clobbers A, HL.
mv_lt_signed:
        ld  a, h
        xor d
        jp  m, mv_mls_diff
        or  a
        sbc hl, de
        ret
mv_mls_diff:
        ld  a, h
        rlca                    ; carry = HL is the negative one
        ret

; Carry if |HL - DE| <= 256 (16-bit, signed).  Clobbers A, HL.
mv_within_256:
        or  a
        sbc hl, de
        call abs_hl
        ld  a, h
        or  a
        scf
        ret z
        dec a
        jr  nz, mv_mw_no
        ld  a, l
        or  a
        scf
        ret z
mv_mw_no:  or  a
        ret

; HL = a square -> A = its flags byte.  Keeps HL.
mv_map_flags:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret

; HL = a square -> A = its index byte (slot + 1).  Keeps HL.
mv_map_index:
        push hl
        ld  a, h
        and $0F
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret

; map_unit_at ($01A934): HL = a square -> HL = the unit there, or 0 (Z).
; Clobbers A, DE.
mv_unit_at:
        ld  a, h
        cp  $10
        jr  nc, mv_mua_no
        call mv_map_flags
        bit MF_UNIT, a
        jr  z, mv_mua_no
        call mv_map_index
        or  a
        jr  z, mv_mua_no
        dec a
        cp  UNIT_COUNT
        jr  nc, mv_mua_no
        call unit_ptr
        or  1
        ret
mv_mua_no: ld  hl, 0
        xor a
        ret

; map_structure_at ($01A96E): HL = a square -> HL = the structure there,
; or 0 (Z).  Clobbers A, DE.
mv_struct_at:
        ld  a, h
        cp  $10
        jr  nc, mv_mua_no
        call mv_map_flags
        bit MF_STRUCT, a
        jr  z, mv_mua_no
        call mv_map_index
        or  a
        jr  z, mv_mua_no
        dec a
        cp  STRUCT_COUNT
        jr  nc, mv_mua_no
        call struct_ptr
        or  1
        ret

; map_object_at ($01A8D8): HL = a square -> NZ if a unit or a structure
; is named there.  Clobbers A, DE, HL.
mv_object_at:
        call mv_map_index
        or  a
        ret z
        call mv_map_flags
        and (1 << MF_UNIT) | (1 << MF_STRUCT)
        ret

; ref_unit ($02E38C): HL = a reference -> HL = the unit it names, or 0
; (Z).  Clobbers A, DE.
mv_ref_unit:
        ld  a, h
        and $C0
        cp  REF_UNIT >> 8
        jr  nz, mv_mua_no
        ld  a, h
        and $3F
        jr  nz, mv_mua_no
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, mv_mua_no
        call unit_ptr
        or  1
        ret

; ref_struct ($02E1D0): HL = a reference -> HL = the structure, or 0 (Z).
mv_ref_struct:
        ld  a, h
        and $C0
        cp  REF_STRUCT >> 8
        jr  nz, mv_mua_no
        ld  a, h
        and $3F
        jr  nz, mv_mua_no
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, mv_mua_no
        call struct_ptr
        or  1
        ret

; ref_object ($02E352): HL = a reference -> HL = the unit or structure,
; or 0 (Z).
mv_ref_object:
        push hl
        call mv_ref_unit
        pop de
        ret nz
        ex  de, hl
        jr  mv_ref_struct

; ref_make ($02E17C) for the unit IY: its reference, 0 if it is not
; allocated.  -> HL.
mv_ref_of_iy_unit:
        ld  hl, 0
        bit OF_ALLOCATED, (iy + O_FLAGS)
        ret z
        ld  l, (iy + O_INDEX)
        ld  h, REF_UNIT >> 8
        ret

; The same for the unit IX.
mv_ref_of_unit:
        ld  hl, 0
        bit OF_ALLOCATED, (ix + O_FLAGS)
        ret z
        ld  l, (ix + O_INDEX)
        ld  h, REF_UNIT >> 8
        ret

; obj_var4_link ($023CCC): HL = the reference from, DE = the one to.  Both
; must be good; links elsewhere are broken first; then each names the
; other in its variable 4, unless the first already names something.
mv_var4_link:
        ld  (mv_lk_from), hl
        ld  (mv_lk_to), de
        call ref_is_valid
        or  a
        ret z
        ld  hl, (mv_lk_to)
        call ref_is_valid
        or  a
        ret z
        ld  hl, (mv_lk_from)
        call mv_ref_object
        ret z
        ld  (mv_lk_a), hl
        ld  hl, (mv_lk_to)
        call mv_ref_object
        ret z
        ld  (mv_lk_b), hl
        push ix
        ; the two variables 4
        ld  ix, (mv_lk_a)
        ld  e, (ix + O_SCRIPT + SC_VARS + 8)
        ld  d, (ix + O_SCRIPT + SC_VARS + 9)
        ld  ix, (mv_lk_b)
        ld  a, e
        cp  (ix + O_SCRIPT + SC_VARS + 8)
        jr  nz, mv_lk_break
        ld  a, d
        cp  (ix + O_SCRIPT + SC_VARS + 9)
        jr  z, mv_lk_set
mv_lk_break:
        ld  ix, (mv_lk_a)
        FCALL obj_var4_clear
        ld  ix, (mv_lk_b)
        FCALL obj_var4_clear
mv_lk_set: ld  ix, (mv_lk_a)
        ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        or  (ix + O_SCRIPT + SC_VARS + 9)
        jr  nz, mv_lk_done
        ld  hl, (mv_lk_to)
        FCALL obj_var4_set
        ld  ix, (mv_lk_b)
        ld  hl, (mv_lk_from)
        FCALL obj_var4_set
mv_lk_done:
        pop ix
        ret

; mv_unit_summon_idle ($04875A): B = the unit type, C = the house, HL = the
; reference it is to fetch, A = nonzero to make a Carryall if none is idle
; -> HL = the unit sent (targetMove and variable 4 = the reference), or 0.
; Idle: carrying nothing, going nowhere.  A Carryall made here comes in at
; position 0 and is byScenario.
mv_unit_summon_idle:
        ld  (mv_si_ref), hl
        ld  (mv_si_make), a
        ld  a, b
        ld  (mv_si_type), a
        ld  a, c
        ld  (mv_si_house), a
        push ix
        ld  a, (unit_find_count)
        or  a
        jr  z, mv_si_none
        ld  b, a
        ld  hl, unit_find
mv_si_loop:
        push bc
        push hl
        ld  a, (hl)
        call unit_ptr
        push hl
        pop ix
        pop hl
        pop bc
        ld  a, (mv_si_type)
        cp  (ix + O_TYPE)
        jr  nz, mv_si_next
        ld  a, (mv_si_house)
        cp  (ix + O_HOUSE)
        jr  nz, mv_si_next
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, mv_si_on
        ld  a, (validate_strict)
        or  a
        jr  z, mv_si_next
mv_si_on:  ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, mv_si_next
        ld  a, (ix + U_TARGETMOVE)
        or  (ix + U_TARGETMOVE + 1)
        jr  z, mv_si_found
mv_si_next:
        inc hl
        djnz mv_si_loop
mv_si_none:
        ld  a, (mv_si_make)
        or  a
        jr  z, mv_si_fail
        ld  a, (mv_si_type)
        or  a
        jr  nz, mv_si_fail
        ; a new Carryall at position 0, whatever the unit cap says
        ld  hl, validate_strict
        inc (hl)
        ld  hl, 0
        ld  (arg_pos), hl
        ld  (arg_pos + 2), hl
        ld  a, (mv_si_house)
        ld  c, a
        ld  b, UNIT_CARRYALL
        ld  d, $60
        ld  a, $FF
        FCALL unit_spawn
        push af
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        pop af
        jr  z, mv_si_fail
        push hl
        pop ix
        set OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
mv_si_found:
        ld  hl, (mv_si_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        FCALL obj_var4_set
        push ix
        pop hl
        pop ix
        ld  a, h
        or  l
        ret
mv_si_fail:
        pop ix
        ld  hl, 0
        xor a
        ret

; The unit calls a Carryall for itself (emc_unit_step $0454F0/$0455BA):
; its link broken, a Carryall of its house summoned (made if none is
; idle) and the two linked.
mv_call_carryall:
        MVCALL obj_var4_clear
        call mv_ref_of_unit
        ld  (mv_cc_me), hl
        ld  b, UNIT_CARRYALL
        ld  c, (ix + O_HOUSE)
        ld  hl, (mv_cc_me)
        ld  a, 1
        call mv_unit_summon_idle
        ret z
        push hl
        pop iy
        call mv_ref_of_iy_unit
        ex  de, hl
        push iy
        ld  hl, (mv_cc_me)
        call mv_var4_link
        pop iy
        ld  hl, (mv_cc_me)
        ld  (iy + U_TARGETMOVE), l
        ld  (iy + U_TARGETMOVE + 1), h
        ret

; ============================================================ destinations

; unit_set_destination ($047D18, PC Unit_SetDestination): IX = the unit,
; HL = a reference.  A square holding another unit or a structure becomes
; a reference to that; a structure of the unit's own house it may enter
; (or any structure, for a flyer) is linked to it through variable 4.
; targetMove = the reference, and the route is dropped.  (go.to's work, and
; the UI's Move click.)
unit_set_destination:
        ld  (mv_sd_ref), hl
        call ref_is_valid
        or  a
        ret z
        call mv_load_info
        ld  hl, (mv_sd_ref)
        ld  a, l
        cp  (ix + U_TARGETMOVE)
        jp  nz, mv_sd_1
        ld  a, h
        cp  (ix + U_TARGETMOVE + 1)
        ret z
mv_sd_1:   ld  a, h
        and $C0
        cp  REF_TILE >> 8
        jr  nz, mv_sd_str
        ; a square: what stands there
        call ref_square
        ld  (mv_sd_sq), hl
        call mv_unit_at
        jr  z, mv_sd_nounit
        push ix
        pop de
        or  a
        sbc hl, de
        jr  z, mv_sd_str
        add hl, de
        push hl
        pop iy
        call mv_ref_of_iy_unit
        ld  (mv_sd_ref), hl
        jr  mv_sd_str
mv_sd_nounit:
        ld  hl, (mv_sd_sq)
        call mv_struct_at
        jr  z, mv_sd_str
        ld  de, O_INDEX
        add hl, de
        ld  l, (hl)
        ld  h, REF_STRUCT >> 8
        ld  (mv_sd_ref), hl
mv_sd_str: ld  hl, (mv_sd_ref)
        call mv_ref_struct
        jr  z, mv_sd_set
        push hl
        pop iy
        ld  a, (iy + O_HOUSE)
        cp  (ix + O_HOUSE)
        jp  nz, mv_sd_2
        call unit_can_enter_structure
        cp  1
        jr  z, mv_sd_link
mv_sd_2:   call mv_mt
        cp  4
        jr  nz, mv_sd_set
mv_sd_link:
        ld  e, (iy + O_INDEX)
        ld  d, REF_STRUCT >> 8
        call mv_ref_of_unit
        call mv_var4_link
mv_sd_set: ld  hl, (mv_sd_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        call mv_route_ptr
        ld  (hl), $FF
        ret

; -> HL -> the unit's route (+$7C, beyond IX's reach).
mv_route_ptr:
        push de
        push ix
        pop hl
        ld  de, U_ROUTE
        add hl, de
        pop de
        ret

; ============================================================ the UNIT.EMC routines
;
; Each is far-called with IX = the script state (the unit + O_SCRIPT) and
; answers in HL.  mv_ef_enter reads nothing: arguments are taken first.

; IX = the script state -> IX = the unit, its type loaded.  Keeps HL.
mv_ef_enter:
        ld  (mv_ef_state), ix
        push hl
        ld  de, -O_SCRIPT
        add ix, de
        call mv_load_info
        pop hl
        ret

; The script's first argument -> HL, and mv_ef_enter.
mv_ef_arg0:
        xor a
        call emc_arg
        jr  mv_ef_enter

; UNIT 3 distance ($01110C): tile_distance to the reference, -1 if stale.
ef_u_distance:
        call mv_ef_arg0
        push hl
        call ref_is_valid
        pop hl
        or  a
        jr  z, mv_ef_minus1
        ld  de, mv_pos
        call ref_position
mv_efd_pos:
        call mv_pos_ptr
        ld  de, mv_pos
        jp  tile_distance
mv_ef_minus1:
        ld  hl, $FFFF
        ret

; UNIT 62 distance.to ($011152, ref_distance_to_edge $02E0A8): as
; distance, but to a structure's near edge: the square of its layout's
; edge facing the unit (tbl_layout_edge), at its centre.
ef_u_distance_to:
        call mv_ef_arg0
        ld  (mv_ef_ref), hl
        call ref_is_valid
        or  a
        jr  z, mv_ef_minus1
        ld  hl, (mv_ef_ref)
        call mv_ref_struct
        jr  nz, mv_edt_struct
        ld  hl, (mv_ef_ref)
        ld  de, mv_pos
        call ref_position
        jr  mv_efd_pos
mv_edt_struct:
        push hl
        pop iy
        ld  hl, (mv_ef_ref)
        call mv_dir_to_ref      ; the direction to its centre
        add a, 16
        rlca
        rlca
        rlca
        and 7
        add a, 4
        and 7
        ld  c, a                ; the edge facing us
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        add a, a
        add a, c
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_edge
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        push de
        call pos_square
        pop de
        add hl, de
        ld  de, mv_pos
        call square_centre
        jr  mv_efd_pos

; UNIT 56 facing.of ($0111E6): a unit's hull facing, $80 if it names none.
ef_u_facing_of:
        call mv_ef_arg0
        call mv_ref_unit
        ld  a, $80
        jr  z, mv_efo_1
        ld  de, U_OR0_CURRENT
        add hl, de
        ld  a, (hl)
mv_efo_1:  ld  l, a
        ld  h, 0
        ret

; UNIT 6 dir.to ($044D2E): the direction to the reference, or the hull's
; facing if it is stale.
ef_u_dir_to:
        call mv_ef_arg0
        push hl
        call ref_is_valid
        pop hl
        or  a
        ld  a, (ix + U_OR0_CURRENT)
        jr  z, mv_efo_1
        call mv_dir_to_ref
        jr  mv_efo_1

; UNIT 7 turn ($044C44): the hull starts turning to n; answers the facing
; now.
ef_u_turn:
        call mv_ef_arg0
        ld  a, l
        ld  bc, 0
        call unit_set_facing
        ld  a, (ix + U_OR0_CURRENT)
        jr  mv_efo_1

; UNIT 19 frame ($0443F8): spriteOffset = -n.
ef_u_frame:
        call mv_ef_arg0
        ld  a, l
        neg
        ld  (ix + U_SPRITEOFS), a
        ld  hl, 0
        ret

; UNIT 26 stop ($044358): speed 0.
ef_u_stop:
        call mv_ef_enter
        xor a
        call unit_set_speed
        ld  hl, 0
        ret

; UNIT 27 speed ($044380): n clamped to 0-255 (192/256 of it for a
; byScenario unit) through unit_set_speed; answers the whole speed.
ef_u_speed:
        call mv_ef_arg0
        bit 7, h
        jr  nz, mv_esp_0
        ld  a, h
        or  a
        jr  nz, mv_esp_255
        ld  a, l
        cp  255
        jr  c, mv_esp_1
mv_esp_255:
        ld  a, 255
        jr  mv_esp_1
mv_esp_0:  xor a
mv_esp_1:  bit OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
        jr  z, mv_esp_2
        ld  l, a
        ld  h, 0
        ld  de, 192
        call mul_shr8
        ld  a, l
mv_esp_2:  call unit_set_speed
        ld  l, (ix + U_SPEED)
        ld  h, 0
        ret

; UNIT 25 head.for ($044F92): the hull turns at the reference, whose
; position becomes currentDestination - unless a projectile (not
; isNormalUnit) is already under way.
ef_u_head_for:
        call mv_ef_arg0
        ld  (mv_ef_ref), hl
        call ref_is_valid
        or  a
        jr  z, mv_ehf_done
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jr  z, mv_ehf_1
        ld  a, UI_flags + 1
        call mv_info_byte
        bit 7, a
        jr  z, mv_ehf_2
mv_ehf_1:  push ix
        pop de
        ld  hl, U_DEST_Y
        add hl, de
        ex  de, hl
        ld  hl, (mv_ef_ref)
        call ref_position
mv_ehf_2:  push ix
        pop de
        ld  hl, U_DEST_Y
        add hl, de
        ex  de, hl
        call mv_dir_to_de
        ld  bc, 0
        call unit_set_facing
mv_ehf_done:
        ld  hl, 0
        ret

; UNIT 61 turning? ($044C78): 1 while the unit is between squares (not a
; flyer) or its gun (the turret, else the hull) is turning; otherwise the
; gun starts turning at targetAttack and it answers 1 if that needed a
; turn.
ef_u_turning:
        call mv_ef_enter
        call mv_mt
        cp  4
        jr  z, mv_etu_1
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jr  nz, mv_etu_yes
mv_etu_1:  ld  c, 0
        call mv_has_turret
        jr  z, mv_etu_2
        inc c
mv_etu_2:  push bc
        call mv_orient_ptr
        pop bc
        ld  a, (hl)
        or  a
        jr  nz, mv_etu_yes
        inc hl
        inc hl
        ld  a, (hl)
        ld  (mv_ef_cur), a
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        push bc
        push hl
        call ref_is_valid
        pop hl
        pop bc
        or  a
        jr  z, mv_etu_no
        push bc
        call mv_dir_to_ref
        pop bc
        ld  hl, mv_ef_cur
        cp  (hl)
        jr  z, mv_etu_no
        ld  b, 0
        call unit_set_facing
mv_etu_yes:
        ld  hl, 1
        ret
mv_etu_no: ld  hl, 0
        ret

; UNIT 5 go.to ($044D7E): where the unit is going.  0 or a stale reference
; clears targetMove; a Harvester takes a place as it is (route dropped),
; and a structure only if nobody has claimed it.
ef_u_go_to:
        call mv_ef_arg0
        ld  (mv_ef_ref), hl
        ld  a, h
        or  l
        jr  z, mv_egt_clear
        call ref_is_valid
        or  a
        jr  z, mv_egt_clear
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, mv_egt_set
        ld  hl, (mv_ef_ref)
        call mv_ref_struct
        jr  nz, mv_egt_str
        ld  hl, (mv_ef_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        call mv_route_ptr
        ld  (hl), $FF
        jr  mv_egt_done
mv_egt_str:
        ld  de, O_SCRIPT + SC_VARS + 8
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  nz, mv_egt_done
mv_egt_set:
        ld  hl, (mv_ef_ref)
        call unit_set_destination
        jr  mv_egt_done
mv_egt_clear:
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
mv_egt_done:
        ld  hl, 0
        ret

; UNIT 47 blocked? ($045B6A): 1 if what the unit carries could not be put
; down there.  A place: off the playable map, nothing carried, or the
; cargo cannot stand on it (its position is then -1); a structure: 0 if it
; is the unit's own house's, else unit_can_enter_structure's word; anything
; else 1.
ef_u_blocked:
        call mv_ef_arg0
        ld  (mv_ef_ref), hl
        ld  a, h
        and $C0
        cp  REF_STRUCT >> 8
        jr  z, mv_ebl_struct
        cp  REF_TILE >> 8
        jr  nz, mv_ebl_yes
        call ref_square
        call map_valid
        jr  nc, mv_ebl_yes
        call mv_carried
        jr  z, mv_ebl_yes
        push hl
        pop iy
        push iy
        pop de
        ld  hl, O_POS_Y
        add hl, de
        ex  de, hl
        ld  hl, (mv_ef_ref)
        call ref_position
        push ix
        push iy
        pop ix
        FCALL unit_blocked_here
        push af
        or  a
        jr  z, mv_ebl_1
        ld  a, $FF
        ld  (ix + O_POS_Y), a
        ld  (ix + O_POS_Y + 1), a
        ld  (ix + O_POS_X), a
        ld  (ix + O_POS_X + 1), a
mv_ebl_1:  pop af
        pop ix
        or  a
        jr  nz, mv_ebl_yes
        jr  mv_ebl_no
mv_ebl_struct:
        ld  hl, (mv_ef_ref)
        call mv_ref_struct
        jr  z, mv_ebl_yes
        push hl
        pop iy
        ld  a, (iy + O_HOUSE)
        cp  (ix + O_HOUSE)
        jr  z, mv_ebl_no
        call mv_carried
        jr  z, mv_ebl_yes
        push ix
        push hl
        pop ix
        call unit_can_enter_structure
        pop ix
        or  a
        jr  nz, mv_ebl_yes
mv_ebl_no: ld  hl, 0
        ret
mv_ebl_yes:
        ld  hl, 1
        ret

; obj_linked_unit ($048EB4): -> HL = the unit IX carries (linkedID), or 0
; (Z).
mv_carried:
        ld  a, (ix + O_LINKED)
        cp  UNIT_COUNT
        jp  nc, mv_mua_no
        call unit_ptr
        or  1
        ret

; UNIT 48 nearby ($045C48): for a place, a random square within $50 of
; the unit - its row from one draw of tile_move_by_random $011688, its
; column from another; else 0.
ef_u_nearby:
        call mv_ef_arg0
        ld  a, h
        and $C0
        cp  REF_TILE >> 8
        ld  hl, 0
        ret nz
        call mv_near_random
        ld  a, (mv_nr_out + 3)
        ld  (mv_ef_col), a
        call mv_near_random
        ld  a, (mv_nr_out + 1)     ; the row
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (mv_ef_col)
        and $3F
        or  l
        ld  l, a
        jp  ref_make_square

; tile_move_by_random ($011688) with a distance of $50, centred: the
; unit's position moved a random way by up to $50 (in steps of 16), the
; result in mv_nr_out; left where it is if that leaves rows/columns 1-62.
mv_near_random:
        call random
        ld  c, a
        ld  a, $50
mv_nrr_1:  cp  c                   ; distance > r: done
        jr  z, mv_nrr_2
        jr  nc, mv_nrr_3
mv_nrr_2:  srl c
        jr  mv_nrr_1
mv_nrr_3:  call random
        ld  (mv_nr_dir), a
        ; x + (sin * r) >> 3, low four bits cleared
        ld  e, a
        ld  d, 0
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        push bc
        call smul_d8
        pop bc
        call mv_nr_shr3
        ld  e, (ix + O_POS_X)
        ld  d, (ix + O_POS_X + 1)
        add hl, de
        ld  (mv_nr_out + 2), hl
        ; y + (-cos * r) >> 3
        ld  a, (mv_nr_dir)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        push bc
        call smul_d8
        pop bc
        call mv_nr_shr3
        ld  e, (ix + O_POS_Y)
        ld  d, (ix + O_POS_Y + 1)
        add hl, de
        ld  (mv_nr_out), hl
        ; within $100..$3EFF on both axes, or where it was
        call mv_nr_inside
        jr  nc, mv_nr_back
        ld  hl, (mv_nr_out + 2)
        call mv_nr_inside_hl
        jr  nc, mv_nr_back
        ld  a, $80
        ld  (mv_nr_out), a
        ld  (mv_nr_out + 2), a
        ret
mv_nr_back:
        call mv_pos_ptr
        ld  de, mv_nr_out
        ld  bc, 4
        ldir
        ret
mv_nr_inside:
        ld  hl, (mv_nr_out)
mv_nr_inside_hl:
        ld  de, $100
        call mv_lt_signed_keep
        ccf
        ret nc
        ld  de, $3F00
        jp  mv_lt_signed
; HL = (HL >> 3) & $FFF0, arithmetic.
mv_nr_shr3:
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

; UNIT 49 fidget ($045CD8): a foot soldier now and then shows a random
; frame; a foot, tracked or wheeled unit now and then starts its hull or
; turret turning to a random facing.
ef_u_fidget:
        call mv_ef_enter
        ld  de, $000A
        call rand_between
        ld  (mv_ef_cur), a
        call mv_mt
        or  a
        jr  z, mv_efg_foot
        cp  1
        jr  z, mv_efg_turn
        cp  3
        jr  nz, mv_efg_done
        jr  mv_efg_turn
mv_efg_foot:
        ld  a, (mv_ef_cur)
        cp  9
        jr  c, mv_efg_turn
        call random
        and $3F
        ld  (ix + U_SPRITEOFS), a
mv_efg_turn:
        ld  a, (mv_ef_cur)
        cp  3
        jr  nc, mv_efg_done
        call random
        and 1
        xor 1
        ld  c, a                ; bit 0 set: the hull, else the turret
        call random
        ld  b, 0
        call unit_set_facing
mv_efg_done:
        ld  hl, 0
        ret

; UNIT 22 fly.to ($04442A): fly at targetMove (a Refinery's pad at +$80,
; +$100, a Starport's at +$E0, +$E0).  Within 128 slide up to 16 an axis;
; within 64 land on it and answer 1.  Further out turn at it with a speed
; that falls with the turn still to make.  Until it has arrived it sets a
; delay and steps the script back so the call runs again.  The port fixes
; the unwrapped angle ($044574): a turn across north is the short one.
ef_u_fly_to:
        call mv_ef_enter
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        ld  a, h
        or  l
        jp  z, mv_efy_zero
        push hl
        ld  de, mv_fy_to
        call ref_position
        pop hl
        call mv_ref_struct
        jr  z, mv_efy_1
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        ld  bc, $0080
        ld  de, $0100
        cp  STRUCT_REFINERY
        jr  z, mv_efy_pad
        ld  bc, $00E0
        ld  de, $00E0
        cp  STRUCT_STARPORT
        jr  nz, mv_efy_1
mv_efy_pad:
        ld  hl, (mv_fy_to)
        add hl, bc
        ld  (mv_fy_to), hl
        ld  hl, (mv_fy_to + 2)
        add hl, de
        ld  (mv_fy_to + 2), hl
mv_efy_1:  call mv_pos_ptr
        ld  de, mv_fy_to
        call tile_distance
        ld  (mv_fy_d), hl
        ld  de, 128
        call mv_lt_signed
        jr  nc, mv_efy_far
        ; close: stop, slide
        xor a
        call unit_set_speed
        ld  hl, (mv_fy_to + 2)
        ld  e, (ix + O_POS_X)
        ld  d, (ix + O_POS_X + 1)
        call mv_efy_clamp
        ld  (ix + O_POS_X), l
        ld  (ix + O_POS_X + 1), h
        ld  hl, (mv_fy_to)
        ld  e, (ix + O_POS_Y)
        ld  d, (ix + O_POS_Y + 1)
        call mv_efy_clamp
        ld  (ix + O_POS_Y), l
        ld  (ix + O_POS_Y + 1), h
        ld  hl, (mv_fy_d)
        ld  de, 65
        call mv_lt_signed
        jr  nc, mv_efy_wait2
        ; within 64: land
        call mv_pos_ptr
        ex  de, hl
        ld  hl, mv_fy_to
        ld  bc, 4
        ldir
        ld  hl, 1
        ret
mv_efy_wait2:
        ld  hl, 2
        jr  mv_efy_again
mv_efy_far:
        ld  de, mv_fy_to
        call mv_dir_to_de
        ld  (mv_ef_cur), a
        ld  bc, 0
        call unit_set_facing
        ld  a, (mv_ef_cur)
        sub (ix + U_OR0_CURRENT)
        cp  129
        jr  c, mv_efy_2
        neg                     ; the port: the short way round
mv_efy_2:  cpl                     ; 255 - the angle
        ld  e, a
        ld  d, 0
        ld  hl, (mv_fy_d)
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        ld  a, h
        or  a
        jr  z, mv_efy_3
        ld  l, 255
mv_efy_3:  ld  h, 0
        call mul_shr8
        ld  a, l
        call unit_set_speed
        ; the delay: distance >> 10, at least 1
        ld  a, (mv_fy_d + 1)
        sra a
        sra a
        ld  l, a
        ld  h, 0
        or  a
        jr  nz, mv_efy_again
        inc l
mv_efy_again:
        ; the delay, and the pc back a word so the call runs again
        ld  (ix + O_DELAY), l
        ld  (ix + O_DELAY + 1), h
        ld  l, (ix + O_SCRIPT + SC_PC)
        ld  h, (ix + O_SCRIPT + SC_PC + 1)
        dec hl
        dec hl
        ld  (ix + O_SCRIPT + SC_PC), l
        ld  (ix + O_SCRIPT + SC_PC + 1), h
mv_efy_zero:
        ld  hl, 0
        ret

; DE = where it is, HL = where it goes -> HL = DE + (HL - DE) clamped to
; -16..16.
mv_efy_clamp:
        or  a
        sbc hl, de
        push de
        ld  de, 17
        call mv_lt_signed_keep
        jr  c, mv_efc_1
        ld  hl, 16
mv_efc_1:  ld  de, -16
        call mv_lt_signed_keep
        jr  nc, mv_efc_2
        ld  hl, -16
mv_efc_2:  pop de
        add hl, de
        ret

; Carry if HL < DE signed; keeps HL.  Clobbers A.
mv_lt_signed_keep:
        push hl
        call mv_lt_signed
        pop hl
        ret

; UNIT 12 step ($0452C2): one step of the way to the reference (S3
; "Planning a route").  0 when arrived or given up, 1 while under way.
ef_u_step:
        call mv_ef_arg0
        ld  (mv_ef_ref), hl
        ; between squares, or the reference gone: still going
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
        jp  nz, mv_est_one
        call ref_is_valid
        or  a
        jp  z, mv_est_one
        call mv_own_sq
        ld  (mv_st_own), hl
        ld  hl, (mv_ef_ref)
        call ref_square
        ld  (mv_st_goal), hl
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, mv_est_1
        ; a Harvester sent to a Refinery aims at its pad
        ld  hl, (mv_ef_ref)
        call mv_ref_struct
        jr  z, mv_est_hsq
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        cp  STRUCT_REFINERY
        jr  nz, mv_est_1
        ld  de, O_POS_Y + 1 - O_TYPE
        add hl, de
        ld  a, (hl)
        inc a                   ; the row + 1
        inc hl
        inc hl
        ld  c, (hl)
        inc c
        inc c                   ; the column + 2
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, c
        and $3F
        or  l
        ld  l, a
        ld  a, h
        and $0F
        ld  h, a
        ld  (mv_st_goal), hl
        jr  mv_est_1
mv_est_hsq:
        ; ... sent to a square where a unit is on Guard, Harvest, Stop or
        ; Ambush: it gives it up (the port's fix: only if a unit is there)
        ld  hl, (mv_st_goal)
        call mv_unit_at
        jr  z, mv_est_1
        ld  de, U_ACTION
        add hl, de
        ld  a, (hl)
        cp  ORDER_GUARD
        jr  z, mv_est_hdrop
        cp  ORDER_HARVEST
        jr  z, mv_est_hdrop
        cp  ORDER_STOP
        jr  z, mv_est_hdrop
        cp  ORDER_AMBUSH
        jr  nz, mv_est_1
mv_est_hdrop:
        call mv_route_ptr
        ld  (hl), $FF
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
        ; and the argument on the script's stack
        ld  hl, (mv_ef_state)
        ld  de, SC_SP
        add hl, de
        ld  a, (hl)
        add a, a
        add a, SC_STACK - SC_SP
        ld  e, a
        ld  d, 0
        add hl, de
        ld  (hl), 0
        inc hl
        ld  (hl), 0
mv_est_1:  ; arrived, or the goal off the playable map: done
        ld  hl, (mv_st_goal)
        ld  de, (mv_st_own)
        or  a
        sbc hl, de
        jr  z, mv_est_arrived
        ld  hl, (mv_st_goal)
        call map_valid
        jr  c, mv_est_2
mv_est_arrived:
        call mv_route_ptr
        ld  (hl), $FF
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
        ld  hl, 0
        ret
mv_est_2:  call mv_route_ptr
        ld  a, (hl)
        cp  $FF
        jp  nz, mv_est_have
        ; no route yet: plan one, 16 squares at most
        ld  hl, (mv_st_own)
        ld  (mv_pf_start), hl
        ld  hl, (mv_st_goal)
        ld  (mv_pf_goal), hl
        push ix
        call mv_path_find
        pop ix
        call mv_load_info
        ld  a, (mv_pf_len)
        cp  16
        jr  c, mv_est_3
        ld  a, 16
mv_est_3:  or  a
        jr  z, mv_est_4
        ld  c, a
        ld  b, 0
        call mv_route_ptr
        ex  de, hl
        ld  hl, mv_pf_buf
        ldir
mv_est_4:  call mv_route_ptr
        ld  a, (hl)
        cp  $FF
        jp  nz, mv_est_go
        ; ---- no route at all
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  nz, mv_est_5
        ld  (ix + O_DELAY), $D0 ; 720
        ld  (ix + O_DELAY + 1), $02
mv_est_5:  ld  hl, (mv_st_own)
        call map_valid
        jr  c, mv_est_6
        ; off the playable map with a target: removed
        ld  a, (ix + U_TARGETATTACK)
        or  (ix + U_TARGETATTACK + 1)
        jp  z, mv_est_go
        MVCALL unit_remove
        jp  mv_est_one
mv_est_6:  ; Mega Drive only: give the attack up, or call a Carryall
        ld  a, (ix + U_TARGETATTACK)
        or  (ix + U_TARGETATTACK + 1)
        jr  z, mv_est_lift
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, mv_est_lift
        ; attacking: lifted if a Repair Facility has claimed it
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        call mv_ref_struct
        jr  z, mv_est_giveup
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        cp  STRUCT_REPAIR
        jr  nz, mv_est_giveup
        ; (its claim is a structure, so it is no Carryall)
        call mv_call_carryall
        jr  mv_est_go
mv_est_giveup:
        ld  a, (ix + O_HOUSE)
        ld  hl, player_house
        cp  (hl)
        jr  nz, mv_est_7
        ld  (ix + U_TARGETATTACK), 0
        ld  (ix + U_TARGETATTACK + 1), 0
        ld  a, ORDER_GUARD
        MVCALL unit_give_order
        jr  mv_est_go
mv_est_7:  ld  a, (ix + U_ACTION)
        cp  ORDER_HUNT
        jr  nz, mv_est_8
        ld  (ix + U_TARGETATTACK), 0
        ld  (ix + U_TARGETATTACK + 1), 0
        jr  mv_est_go
mv_est_8:  ld  a, ORDER_AREAGUARD
        MVCALL unit_give_order
        jr  mv_est_go
mv_est_lift:
        ; anything else calls a Carryall, unless its claim is one already
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        call mv_ref_unit
        jr  z, mv_est_lift2
        ld  de, O_TYPE
        add hl, de
        ld  a, (hl)
        or  a                   ; UNIT_CARRYALL
        jr  z, mv_est_go
mv_est_lift2:
        call mv_call_carryall
        jr  mv_est_go
mv_est_have:
        ; a route already, to a unit: cut where the goal now is
        ld  a, (ix + U_TARGETMOVE + 1)
        and $C0
        cp  REF_UNIT >> 8
        jr  nz, mv_est_go
        ld  hl, (mv_st_goal)
        ld  de, (mv_st_own)
        call tile_distance_packed
        ld  a, h
        or  a
        jr  nz, mv_est_go
        ld  a, l
        cp  16
        jr  nc, mv_est_go
        ld  e, a
        ld  d, 0
        call mv_route_ptr
        add hl, de
        ld  (hl), $FF
mv_est_go: ; face the first direction; once facing it, step
        bit OF_USED, (ix + O_FLAGS)
        jr  z, mv_est_one
        call mv_route_ptr
        ld  a, (hl)
        cp  $FF
        jr  z, mv_est_one
        rrca
        rrca
        rrca
        and $E0
        cp  (ix + U_OR0_CURRENT)
        jr  z, mv_est_step
        ld  bc, 0
        call unit_set_facing
mv_est_one:
        ld  hl, 1
        ret
mv_est_step:
        call unit_start_step
        or  a
        jr  z, mv_est_blocked
        ; the route moves down one
        call mv_route_ptr
        ld  d, h
        ld  e, l
        inc hl
        ld  bc, 15
        ldir
        ex  de, hl
        ld  (hl), $FF
        ld  hl, 1
        ret
mv_est_blocked:
        call mv_route_ptr
        ld  (hl), $FF
        ld  hl, 0
        ret

; ============================================================ the path finder
;
; path_find $012AAE, path_follow_edge $012D5A and path_smooth $012E62: the
; PC game's Script_Unit_Pathfinder with the Mega Drive's additions (the
; diagonal squeeze, 128 edge steps).  tools/tests/test_move.py checks it
; against the Python transcription in tools/sega/sega_spec_check.py.
; The cost is unit_path_cost $04526C: 0 into the square of the unit's
; targetMove, else unit_tile_enter_score with the direction << 5 (so its
; diagonal term never applies), -1 made 256; above 255 is a wall.

MV_PF_SIZE         EQU 40          ; emc_unit_step's buffer, $28
MV_PF_ROOM         EQU MV_PF_SIZE - 1
MV_FE_MAX          EQU 128         ; edge-following steps (the PC: 100)
MV_FE_OK           EQU 0           ; a piece round an obstacle: connected?
MV_FE_LEN          EQU 1           ; its length
MV_FE_SCORE        EQU 2           ; its cost, a signed word
MV_FE_BUF          EQU 4           ; its directions, $FF ended
MV_FE_SIZE         EQU MV_FE_BUF + MV_FE_MAX + 2

; HL = a square, A = a direction (0-7) -> HL = the square that way
; (tile_step_dir8 $012A9C: no wrap, no bounds).  Clobbers A.
mv_step8:
        push de
        and 7
        add a, a
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, tbl_tile_step_dir8
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop hl
        add hl, de
        pop de
        ret

; HL = from, DE = to (squares) -> A = the direction 0-7
; (tile_direction_packed >> 5 & 7).  Clobbers BC, DE, HL.
mv_dir8:
        call tile_direction_packed
        rlca
        rlca
        rlca
        and 7
        ret

; HL = a square, A = a direction -> HL = the cost, carry if it can be
; entered (the cost is at most 255, signed).  Clobbers all but IX.
mv_pf_cost:
        push de
        ld  de, (mv_pf_tmsq)
        or  a
        sbc hl, de
        add hl, de
        pop de
        jr  nz, mv_pfc_1
        ld  hl, 0
        scf
        ret
mv_pfc_1:  add a, a
        add a, a
        add a, a
        add a, a
        add a, a
        call unit_tile_enter_score
        ld  a, h
        and l
        inc a
        jr  nz, mv_pfc_2
        ld  hl, 256
mv_pfc_2:  bit 7, h
        scf
        ret nz
        ld  a, h
        or  a
        scf
        ret z
        or  a
        ret

; path_find: IX = the unit, mv_pf_start and mv_pf_goal the squares -> mv_pf_buf =
; the route (directions, then $FF if there is room), mv_pf_len its length
; with the $FF.  Straight at the goal while it can; at an obstacle, along
; the blocked line to the first square beyond, then round the obstacle
; both ways, keeping the cheaper.
mv_path_find:
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        call ref_square
        ld  (mv_pf_tmsq), hl
        ld  a, $FF
        ld  (mv_pf_buf), a
        xor a
        ld  (mv_pf_len), a
        ld  hl, (mv_pf_start)
        ld  (mv_pf_cur), hl
mv_pf_loop:
        ld  a, (mv_pf_len)
        cp  MV_PF_ROOM
        jp  nc, mv_pf_end
        ld  hl, (mv_pf_cur)
        ld  de, (mv_pf_goal)
        or  a
        sbc hl, de
        jp  z, mv_pf_end
        add hl, de
        call mv_dir8
        ld  (mv_pf_a3), a
        ld  hl, (mv_pf_cur)
        call mv_step8
        ld  (mv_pf_nxt), hl
        ld  a, (mv_pf_a3)
        call mv_pf_cost
        jr  nc, mv_pf_obst
        ld  a, (mv_pf_a3)
        call mv_pf_append
        ld  hl, (mv_pf_nxt)
        ld  (mv_pf_cur), hl
        jr  mv_pf_loop
mv_pf_obst:
        ; along the blocked line to a square that can be entered ($012B62)
        call mv_pf_nxt_goal
        jp  z, mv_pf_end
        ld  hl, (mv_pf_nxt)
        ld  de, (mv_pf_goal)
        call mv_dir8
        ld  (mv_pf_d3), a
        ld  hl, (mv_pf_nxt)
        call mv_step8
        ld  (mv_pf_nxt), hl
        ld  a, (mv_pf_d3)
        call mv_pf_cost
        jr  c, mv_pf_edges         ; (even on the goal itself: $012B8E)
        ld  a, (mv_pf_d3)
        rra
        jr  nc, mv_pf_obst
        ; Mega Drive only: on a diagonal, a square whose two back
        ; neighbours (e+3, e+5) can both be entered will do - take e+3
        ld  a, (mv_pf_d3)
        add a, 3
        call mv_pf_side_ok
        jr  nc, mv_pf_obst
        ld  a, (mv_pf_d3)
        add a, 5
        call mv_pf_side_ok
        jr  nc, mv_pf_obst
        ld  a, (mv_pf_d3)
        add a, 3
        ld  hl, (mv_pf_nxt)
        call mv_step8
        ld  (mv_pf_nxt), hl
mv_pf_edges:
        ; round the obstacle both ways; the cheaper wins, a tie clockwise
        ld  a, -1
        ld  hl, mv_fe_rec1
        call mv_follow_edge
        ld  a, 1
        ld  hl, mv_fe_rec2
        call mv_follow_edge
        ld  a, (mv_fe_rec1 + MV_FE_OK)
        ld  b, a
        ld  a, (mv_fe_rec2 + MV_FE_OK)
        or  b
        jr  z, mv_pf_neither
        ld  hl, mv_fe_rec1
        ld  a, (mv_fe_rec2 + MV_FE_OK)
        or  a
        jr  z, mv_pf_take
        ld  hl, mv_fe_rec2
        ld  a, b
        or  a
        jr  z, mv_pf_take
        ld  hl, (mv_fe_rec1 + MV_FE_SCORE)
        ld  de, (mv_fe_rec2 + MV_FE_SCORE)
        call mv_lt_signed
        ld  hl, mv_fe_rec2
        jr  nc, mv_pf_take
        ld  hl, mv_fe_rec1
mv_pf_take:
        ; as much of the piece as there is room for
        push hl
        ld  a, (mv_pf_len)
        ld  b, a
        ld  a, MV_PF_ROOM
        sub b
        ld  c, a
        inc hl
        ld  a, (hl)             ; MV_FE_LEN
        cp  c
        jr  c, mv_pf_t1
        ld  a, c
mv_pf_t1:  pop hl
        or  a
        jp  z, mv_pf_end
        ld  c, a
        ld  b, 0
        ld  de, MV_FE_BUF
        add hl, de
        push hl
        ld  a, (mv_pf_len)
        ld  e, a
        ld  d, 0
        ld  hl, mv_pf_buf
        add hl, de
        ex  de, hl
        pop hl
        ld  a, (mv_pf_len)
        add a, c
        ld  (mv_pf_len), a
        ldir
        ld  hl, (mv_pf_nxt)
        ld  (mv_pf_cur), hl
        jp  mv_pf_loop
mv_pf_neither:
        ; neither way: walk on while the line is open ($012C6C)
        call mv_pf_nxt_goal
        jp  z, mv_pf_end
        ld  hl, (mv_pf_nxt)
        ld  de, (mv_pf_goal)
        call mv_dir8
        ld  (mv_pf_d3), a
        ld  hl, (mv_pf_nxt)
        call mv_step8
        ld  (mv_pf_nxt), hl
        ld  a, (mv_pf_d3)
        call mv_pf_cost
        jr  c, mv_pf_neither
        jp  mv_pf_obst
mv_pf_end: ld  a, (mv_pf_len)
        cp  MV_PF_ROOM
        ret nc
        ld  a, $FF
        ; fall through

; A -> the end of the route.
mv_pf_append:
        push af
        ld  a, (mv_pf_len)
        ld  e, a
        ld  d, 0
        inc a
        ld  (mv_pf_len), a
        ld  hl, mv_pf_buf
        add hl, de
        pop af
        ld  (hl), a
        ret

; Z if mv_pf_nxt is the goal.  Clobbers HL, DE.
mv_pf_nxt_goal:
        ld  hl, (mv_pf_nxt)
        ld  de, (mv_pf_goal)
        or  a
        sbc hl, de
        ret

; A = a direction -> carry if the square that way from mv_pf_nxt can be
; entered.
mv_pf_side_ok:
        and 7
        push af
        ld  hl, (mv_pf_nxt)
        call mv_step8
        pop af
        jp  mv_pf_cost

; path_follow_edge: HL = the record to fill, A = the turn (-1 or +1).
; From mv_pf_cur, the first search direction mv_pf_a3, to mv_pf_nxt: turn until a
; square can be entered (or, on a diagonal, the next direction leads
; straight onto the target); record it and step; the next search starts
; three directions back.  Coming back round to the first direction, or
; back to the start, is failure; so are 128 steps.  On success the piece
; is smoothed.
mv_follow_edge:
        ld  (mv_fe_rec), hl
        ld  (mv_fe_turn), a
        ld  (hl), 0
        ld  de, MV_FE_BUF
        add hl, de
        ld  (mv_fe_buf), hl
        ld  hl, (mv_pf_cur)
        ld  (mv_fe_cur), hl
        ld  a, (mv_pf_a3)
        ld  (mv_fe_d5), a
        xor a
        ld  (mv_fe_n), a
mv_fe_outer:
        ld  a, (mv_fe_d5)
        ld  (mv_fe_d7), a
mv_fe_turn_l:
        ld  a, (mv_fe_turn)
        ld  b, a
        ld  a, (mv_fe_d7)
        add a, b
        and 7
        ld  (mv_fe_d7), a
        rra
        jr  nc, mv_fe_plain
        ld  a, (mv_fe_d7)
        add a, b
        and 7
        ld  (mv_fe_e), a
        ld  hl, (mv_fe_cur)
        call mv_step8
        ld  de, (mv_pf_nxt)
        or  a
        sbc hl, de
        jr  nz, mv_fe_plain
        ld  a, (mv_fe_e)
        ld  (mv_fe_d7), a
        ld  hl, (mv_fe_cur)
        call mv_step8
        ld  (mv_fe_nxt), hl
        jr  mv_fe_rec_l
mv_fe_plain:
        ld  a, (mv_fe_d5)
        ld  b, a
        ld  a, (mv_fe_d7)
        cp  b
        ret z
        ld  hl, (mv_fe_cur)
        call mv_step8
        ld  (mv_fe_nxt), hl
        ld  a, (mv_fe_d7)
        call mv_pf_cost
        jr  nc, mv_fe_turn_l
mv_fe_rec_l:
        ld  a, (mv_fe_n)
        ld  e, a
        ld  d, 0
        inc a
        ld  (mv_fe_n), a
        ld  hl, (mv_fe_buf)
        add hl, de
        ld  a, (mv_fe_d7)
        ld  (hl), a
        inc hl
        push hl
        ld  hl, (mv_fe_nxt)
        ld  de, (mv_pf_nxt)
        or  a
        sbc hl, de
        pop hl
        jr  nz, mv_fe_2
        ld  (hl), $FF
        call mv_smooth
        ld  hl, (mv_fe_rec)
        ld  (hl), 1
        ret
mv_fe_2:   ld  hl, (mv_fe_nxt)
        ld  de, (mv_pf_cur)
        or  a
        sbc hl, de
        ret z
        ld  a, (mv_fe_turn)
        ld  b, a
        add a, a
        add a, b
        ld  b, a
        ld  a, (mv_fe_d7)
        sub b
        and 7
        ld  (mv_fe_d5), a
        ld  hl, (mv_fe_nxt)
        ld  (mv_fe_cur), hl
        ld  a, (mv_fe_n)
        cp  MV_FE_MAX
        jp  c, mv_fe_outer
        ret

; path_smooth: the piece in mv_fe_buf (mv_fe_n directions, then $FF) from
; mv_pf_cur, smoothed with the table at $06C748 by the difference of two
; directions: opposite ones cancel; 45 degrees apart they stay, but a
; diagonal and a 45-degree turn become two straights if the square beside
; can be entered; 90 or 135 apart they fold into one and the walk backs up
; a square.  Dropped steps are $FE; then the piece is packed and its
; length and cost written to the record.
mv_smooth:
        ld  hl, (mv_pf_cur)
        ld  (mv_sm_d6), hl
        ld  a, (mv_fe_n)
        cp  2
        jp  c, mv_sm_pack
        ld  a, 1
        ld  (mv_sm_a5), a
mv_sm_loop:
        ld  a, (mv_sm_a5)
        call mv_sm_at
        cp  $FF
        jp  z, mv_sm_pack
        ld  a, (mv_sm_a5)
        dec a
        call mv_sm_back
        cp  $FE
        jr  nz, mv_sm_1
        call mv_sm_next
        jr  mv_sm_loop
mv_sm_1:   ld  (mv_sm_v4), a
        ld  b, a
        ld  a, (mv_sm_a5)
        call mv_sm_at
        sub b
        and 7
        ld  e, a
        ld  d, 0
        ld  hl, tbl_path_smooth
        add hl, de
        ld  a, (hl)
        ld  (mv_sm_d), a
        cp  3
        jr  nz, mv_sm_2
        ld  a, (mv_sm_a4)
        call mv_sm_at
        ld  (hl), $FE
        ld  a, (mv_sm_a5)
        call mv_sm_at
        ld  (hl), $FE
        call mv_sm_next
        jr  mv_sm_loop
mv_sm_2:   or  a
        jr  nz, mv_sm_3
        ld  hl, (mv_sm_d6)
        ld  a, (mv_sm_v4)
        call mv_step8
        ld  (mv_sm_d6), hl
        call mv_sm_next
        jr  mv_sm_loop
mv_sm_3:   ld  a, (mv_sm_v4)
        rra
        jr  nc, mv_sm_even
        ; the first a diagonal: d4 = it one eighth towards the second
        ld  a, (mv_sm_d)
        bit 7, a
        ld  a, 1
        jr  z, mv_sm_4
        ld  a, -1
mv_sm_4:   ld  b, a
        ld  a, (mv_sm_v4)
        add a, b
        and 7
        ld  (mv_sm_d4), a
        ld  a, (mv_sm_d)
        cp  1
        jr  z, mv_sm_45
        cp  -1
        jr  nz, mv_sm_fold
mv_sm_45:  ld  hl, (mv_sm_d6)
        ld  a, (mv_sm_d4)
        call mv_step8
        ld  a, (mv_sm_d4)
        call mv_pf_cost
        jr  nc, mv_sm_46
        ld  a, (mv_sm_d4)
        ld  b, a
        ld  a, (mv_sm_a5)
        call mv_sm_at
        ld  (hl), b
        ld  a, (mv_sm_a4)
        call mv_sm_at
        ld  (hl), b
mv_sm_46:  ld  a, (mv_sm_a4)
        call mv_sm_at
        ld  hl, (mv_sm_d6)
        call mv_step8
        ld  (mv_sm_d6), hl
        call mv_sm_next
        jp  mv_sm_loop
mv_sm_even:
        ld  a, (mv_sm_d)
        ld  b, a
        ld  a, (mv_sm_v4)
        add a, b
        and 7
        ld  (mv_sm_d4), a
mv_sm_fold:
        ld  a, (mv_sm_d4)
        ld  b, a
        ld  a, (mv_sm_a5)
        call mv_sm_at
        ld  (hl), b
        ld  a, (mv_sm_a4)
        call mv_sm_at
        ld  (hl), $FE
        ld  a, (mv_sm_a4)
        call mv_sm_back
        cp  $FE
        jr  z, mv_sm_restart
        add a, 4
        ld  hl, (mv_sm_d6)
        call mv_step8
        ld  (mv_sm_d6), hl
        jp  mv_sm_loop
mv_sm_restart:
        ld  hl, (mv_pf_cur)
        ld  (mv_sm_d6), hl
        jp  mv_sm_loop
mv_sm_pack:
        ld  hl, (mv_pf_cur)
        ld  (mv_sm_d6), hl
        ld  hl, 0
        ld  (mv_sm_score), hl
        xor a
        ld  (mv_sm_a4), a          ; where it reads
        ld  (mv_sm_a5), a          ; where it writes
mv_sm_p1:  ld  a, (mv_sm_a4)
        call mv_sm_at
        cp  $FF
        jr  z, mv_sm_p3
        cp  $FE
        jr  z, mv_sm_p2
        ld  (mv_sm_v4), a
        ld  hl, (mv_sm_d6)
        call mv_step8
        ld  (mv_sm_d6), hl
        ld  a, (mv_sm_v4)
        call mv_pf_cost
        ld  de, (mv_sm_score)
        add hl, de
        ld  (mv_sm_score), hl
        ld  a, (mv_sm_v4)
        ld  b, a
        ld  a, (mv_sm_a5)
        call mv_sm_at
        ld  (hl), b
        ld  hl, mv_sm_a5
        inc (hl)
mv_sm_p2:  ld  hl, mv_sm_a4
        inc (hl)
        jr  mv_sm_p1
mv_sm_p3:  ld  a, (mv_sm_a5)
        call mv_sm_at
        ld  (hl), $FF
        ld  hl, (mv_fe_rec)
        inc hl
        ld  a, (mv_sm_a5)
        ld  (hl), a
        inc hl
        ld  de, (mv_sm_score)
        ld  (hl), e
        inc hl
        ld  (hl), d
        ret

; A = an index -> HL -> mv_fe_buf[A], A = the byte.  Clobbers DE.
mv_sm_at:  ld  hl, (mv_fe_buf)
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, (hl)
        ret

mv_sm_next:
        ld  hl, mv_sm_a5
        inc (hl)
        ret

; A = an index: back over dropped steps ($FE) while not at the first ->
; mv_sm_a4 = the index, A = the byte there.
mv_sm_back:
        ld  (mv_sm_a4), a
mv_smb_1:  call mv_sm_at
        cp  $FE
        ret nz
        ld  a, (mv_sm_a4)
        or  a
        ld  a, $FE
        ret z
        ld  hl, mv_sm_a4
        dec (hl)
        ld  a, (hl)
        jr  mv_smb_1

; ------------------------------------------------ the bank's own scratch
mv_info:        DW 0            ; the type record of the unit in IX
mv_pos:         DS 4            ; a position worked out
mv_uta_now:        DS 4            ; the clock this pass
mv_uta_fmove:      DB 0            ; the six timers: fired this pass
mv_uta_frot:       DB 0
mv_uta_fturret:    DB 0
mv_uta_fscript:    DB 0
mv_uta_fanim:      DB 0
mv_uta_fdev:       DB 0
mv_uta_pos:        DB 0            ; where the walk of the find array is
mv_uta_slot:       DB 0
mv_uta_done:       DS 13           ; a bit per slot: ticked this pass
mv_umt_rem:        DB 0
mv_ss_face:        DB 0
mv_ss_dir:         DB 0
mv_ss_lt:          DB 0
mv_ss_speed:       DB 0
mv_ss_sq:          DW 0
mv_ss_new:         DS 4
mv_um_dist:        DB 0
mv_um_ret:         DB 0
mv_um_bloom:       DB 0
mv_um_lt:          DB 0
mv_um_new:         DS 4
mv_um_d3:          DW 0
mv_um_sq:          DW 0
mv_um_dmg:         DW 0
mv_tes_dir:        DB 0
mv_tes_lt:         DB 0
mv_tes_speed:      DB 0
mv_tes_sq:         DW 0
mv_lk_from:        DW 0
mv_lk_to:          DW 0
mv_lk_a:           DW 0
mv_lk_b:           DW 0
mv_si_ref:         DW 0
mv_si_make:        DB 0
mv_si_type:        DB 0
mv_si_house:       DB 0
mv_cc_me:          DW 0
mv_sd_ref:         DW 0
mv_sd_sq:          DW 0
mv_ef_state:       DW 0
mv_ef_ref:         DW 0
mv_ef_cur:         DB 0
mv_ef_col:         DB 0
mv_nr_dir:         DB 0
mv_nr_out:         DS 4
mv_fy_to:          DS 4
mv_fy_d:           DW 0
mv_st_own:         DW 0
mv_st_goal:        DW 0
mv_pf_start:       DW 0            ; path_find's start and goal squares
mv_pf_goal:        DW 0
mv_pf_len:         DB 0
mv_pf_buf:         DS MV_PF_SIZE      ; routeScratch $FFDE5C
mv_pf_tmsq:        DW 0
mv_pf_cur:         DW 0
mv_pf_nxt:         DW 0
mv_pf_a3:          DB 0
mv_pf_d3:          DB 0
mv_fe_rec:         DW 0
mv_fe_buf:         DW 0
mv_fe_turn:        DB 0
mv_fe_d5:          DB 0
mv_fe_d7:          DB 0
mv_fe_e:           DB 0
mv_fe_n:           DB 0
mv_fe_cur:         DW 0
mv_fe_nxt:         DW 0
mv_fe_rec1:        DS MV_FE_SIZE      ; anticlockwise
mv_fe_rec2:        DS MV_FE_SIZE      ; clockwise
mv_sm_d6:          DW 0
mv_sm_a4:          DB 0
mv_sm_a5:          DB 0
mv_sm_v4:          DB 0
mv_sm_d:           DB 0
mv_sm_d4:          DB 0
mv_sm_score:       DW 0
