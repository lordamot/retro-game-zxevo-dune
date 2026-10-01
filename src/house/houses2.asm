; houses2.asm - bank HOUSE2: the teams and the TEAM.EMC routines (S1, S7),
; where things arrive (S8 map_find_location and its helpers), and the end
; of a mission with its score and rank (S9).  Owner: the HOUSE subsystem.
;
; Every label that is not an interface routine starts with hs_ (the rule
; for the HOUSE banks).  Comments say what the cartridge does, at its
; 68000 addresses.

; ================================================================= the teams

; team_tick ($02E444): when timer_game >= tickTeamGameLoop, the next time is
; the clock + 5 + (random & 7); then every team in use whose house is
; awake (isAIActive) counts its delay down or runs one instruction.
; S1/S7 port: a script that stops no longer ends the loop for the teams
; after it ($02E4D6).  Keeps IX, IY.
team_tick:
        push ix
        push iy
        call hs2_clock
        ld  hl, hs_now
        ld  de, tick_team
        call hs2_cp32           ; C: now < due
        jr  c, hs_tt_out
        call random
        and 7
        add a, 5
        ld  e, a
        ld  d, 0
        ld  hl, hs_now
        ld  bc, tick_team
        call hs2_add_to         ; tick_team = now + DE
        xor a
        ld  (hs_ti), a
hs_tt_l:
        ld  a, (team_find_count)
        ld  b, a
        ld  a, (hs_ti)
        cp  b
        jr  nc, hs_tt_out
        ld  e, a
        ld  d, 0
        ld  hl, team_find
        add hl, de
        ld  a, (hl)
        call team_ptr
        push hl
        pop ix                  ; IX = the team
        ld  a, (ix + T_HOUSE)
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        bit HF_AIACTIVE, (hl)
        jr  z, hs_tt_n
        ld  l, (ix + T_DELAY)
        ld  h, (ix + T_DELAY + 1)
        ld  a, h
        or  l
        jr  z, hs_tt_run
        dec hl
        ld  (ix + T_DELAY), l
        ld  (ix + T_DELAY + 1), h
        jr  hs_tt_n
hs_tt_run:
        ld  de, T_SCRIPT
        add ix, de
        ld  a, (ix + SC_PC)
        or  (ix + SC_PC + 1)
        jr  z, hs_tt_n          ; not loaded
        FCALL emc_run
hs_tt_n:
        ld  hl, hs_ti
        inc (hl)
        jr  hs_tt_l
hs_tt_out:
        pop iy
        pop ix
        ret

; IX = a team's script state -> IX = the team (the cartridge's
; scriptCurrentTeam $FFDCA8).
hs_team:
        ld  de, -T_SCRIPT
        add ix, de
        ret

; TEAM 2 members ($02E520).
ef_t_members:
        call hs_team
        ld  l, (ix + T_MEMBERS)
        ld  h, (ix + T_MEMBERS + 1)
        ret

; TEAM 12 min ($02E52C).
ef_t_min:
        call hs_team
        ld  l, (ix + T_MINMEMBERS)
        ld  h, (ix + T_MINMEMBERS + 1)
        ret

; TEAM 13 target ($02E538).
ef_t_target:
        call hs_team
        ld  l, (ix + T_TARGET)
        ld  h, (ix + T_TARGET + 1)
        ret

; TEAM 3 recruit ($02E544): below its maximum, the team takes the unit of
; its house and movement type, not a Saboteur, nearest its position among
; those in no team - else among those in a team at or below its minimum -
; and answers the room left (0 if nobody was taken).  The PC quirk is kept:
; a candidate wins if nearer than the best so far or the best is at 0.
;
; The Mega Drive walks unit_list_first(house_are_allied(team's house,
; player)) - the list of the team's enemies - and takes only units
; without byScenario, so a computer team never finds anyone (S7: "keep by
; default").  With ai_recruit_fix set (the harder option) it walks its own
; side and takes the PC's units: only byScenario ones.
ef_t_recruit:
        call hs_team
        ld  l, (ix + T_MEMBERS)
        ld  h, (ix + T_MEMBERS + 1)
        ld  e, (ix + T_MAXMEMBERS)
        ld  d, (ix + T_MAXMEMBERS + 1)
        call hs2_cmps           ; members < max?
        jp  p, hs_tr_zero
        ld  hl, 0
        ld  (hs_tr_best), hl    ; a3
        ld  (hs_tr_bestd), hl   ; d3
        ld  (hs_tr_other), hl   ; a4
        ld  (hs_tr_otherd), hl  ; d4
        ld  b, (ix + T_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        ld  c, a                ; the list the cartridge walks
        ld  a, (ai_recruit_fix)
        or  a
        jr  z, hs_tr_1
        ld  a, c
        xor 1                   ; the fix: the team's own side
        ld  c, a
hs_tr_1:
        ld  b, 0
        ld  hl, unit_head
        add hl, bc
        ld  a, (hl)
hs_tr_l:
        cp  $FF
        jp  z, hs_tr_done
        ld  (hs_tr_slot), a
        call unit_ptr
        push hl
        pop iy                  ; IY = the unit
        ld  a, (iy + O_HOUSE)
        cp  (ix + T_HOUSE)
        jp  nz, hs_tr_n
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  (ix + T_MOVETYPE)
        jp  nz, hs_tr_n
        ld  a, (iy + O_FLAGS + 1)
        and 1 << (OF_BYSCENARIO - 8)
        ld  b, a
        ld  a, (ai_recruit_fix)
        or  a
        ld  a, b
        jr  z, hs_tr_md
        or  a                   ; the PC: only the mission's own
        jr  z, hs_tr_n
        jr  hs_tr_2
hs_tr_md:
        or  a                   ; the Mega Drive: none of them
        jr  nz, hs_tr_n
hs_tr_2:
        ld  a, (iy + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  z, hs_tr_n
        ld  a, (iy + U_TEAM)
        or  a
        jr  nz, hs_tr_inteam
        call hs_tr_dist
        ld  de, (hs_tr_bestd)
        call hs_tr_better
        jr  nc, hs_tr_n
        ld  (hs_tr_bestd), hl
        ld  (hs_tr_best), iy
        jr  hs_tr_n
hs_tr_inteam:
        ld  hl, (hs_tr_best)
        ld  a, h
        or  l
        jr  nz, hs_tr_n
        ld  a, (iy + U_TEAM)
        dec a
        call team_ptr
        push hl
        ld  de, T_MEMBERS
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop hl
        push de
        ld  de, T_MINMEMBERS
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop hl                  ; HL = its members, DE = its minimum
        ex  de, hl
        call hs2_cmps           ; min < members: skip (bgt)
        jp  m, hs_tr_n
        call hs_tr_dist
        ld  de, (hs_tr_otherd)
        call hs_tr_better
        jr  nc, hs_tr_n
        ld  (hs_tr_otherd), hl
        ld  (hs_tr_other), iy
hs_tr_n:
        ld  a, (hs_tr_slot)
        ld  e, a
        ld  d, 0
        ld  hl, unit_lnext
        add hl, de
        ld  a, (hl)
        jp  hs_tr_l
hs_tr_done:
        ld  hl, (hs_tr_best)
        ld  a, h
        or  l
        jr  nz, hs_tr_take
        ld  hl, (hs_tr_other)
        ld  a, h
        or  l
        jr  z, hs_tr_zero
hs_tr_take:
        push hl
        pop iy
        call hs_team_remove_unit
        ; team_add_unit ($02E3DC)
        ld  a, (ix + T_INDEX)
        inc a
        ld  (iy + U_TEAM), a
        ld  l, (ix + T_MEMBERS)
        ld  h, (ix + T_MEMBERS + 1)
        inc hl
        ld  (ix + T_MEMBERS), l
        ld  (ix + T_MEMBERS + 1), h
        ex  de, hl
        ld  l, (ix + T_MAXMEMBERS)
        ld  h, (ix + T_MAXMEMBERS + 1)
        or  a
        sbc hl, de
        ret
hs_tr_zero:
        ld  hl, 0
        ret

; IY = a unit, IX = the team -> HL = tile_distance(team position, unit).
hs_tr_dist:
        push ix
        pop hl
        ld  de, T_POS_Y
        add hl, de
        push iy
        pop de
        push hl
        ld  hl, O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        jp  tile_distance

; HL = a distance, DE = the best so far -> carry if it is better: nearer
; (signed, blt) or the best is 0.
hs_tr_better:
        ld  a, d
        or  e
        scf
        ret z
        push hl
        call hs2_cmps           ; HL < DE: sign
        pop hl
        scf
        ret m
        or  a
        ret

; team_remove_unit ($02E406): IY = a unit: out of whatever team it is in.
hs_team_remove_unit:
        ld  a, (iy + U_TEAM)
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
        ld  (iy + U_TEAM), 0
        ret

; The team's members, one by one: hs_mem_first / hs_mem_next -> IY = the
; next unit of the team's house (the search's rule) whose U_TEAM names this
; team, Z when there are no more.  IX = the team.
hs_mem_first:
        ld  hl, hs_search2
        ld  b, (ix + T_HOUSE)
        ld  c, $FF
        push ix
        FCALL unit_find_first
        pop ix
        jr  hs_mem_chk
hs_mem_next:
        ld  hl, hs_search2
        push ix
        FCALL unit_find_next
        pop ix
hs_mem_chk:
        ret z
        push hl
        pop iy
        ld  a, (ix + T_INDEX)
        inc a
        cp  (iy + U_TEAM)
        jr  nz, hs_mem_next
        or  1
        ret

; TEAM 4 spread ($02E67C): the members' squares averaged into the team's
; position (y square << 8, x square << 8); the answer is their average
; rounded distance from it (0 with no members); with a target and a
; targetTile, targetTile = 2 once the centre is within 10 squares of the
; target.
ef_t_spread:
        call hs_team
        ld  hl, 0
        ld  (hs_sp_n), hl
        ld  (hs_sp_x), hl
        ld  (hs_sp_y), hl
        call hs_mem_first
hs_sp_l:
        jr  z, hs_sp_avg
        ld  hl, (hs_sp_n)
        inc hl
        ld  (hs_sp_n), hl
        ld  hl, (hs_sp_x)
        ld  e, (iy + O_POS_X + 1)
        ld  d, 0
        add hl, de
        ld  (hs_sp_x), hl
        ld  hl, (hs_sp_y)
        ld  e, (iy + O_POS_Y + 1)
        add hl, de
        ld  (hs_sp_y), hl
        call hs_mem_next
        jr  hs_sp_l
hs_sp_avg:
        ld  hl, (hs_sp_n)
        ld  a, h
        or  l
        ret z                   ; HL = 0
        ld  hl, (hs_sp_x)
        ld  de, (hs_sp_n)
        call udiv16
        ld  (hs_sp_x), hl
        ld  hl, (hs_sp_y)
        ld  de, (hs_sp_n)
        call udiv16
        ld  (hs_sp_y), hl
        ld  (ix + T_POS_Y), 0
        ld  a, (hs_sp_y)
        ld  (ix + T_POS_Y + 1), a
        ld  (ix + T_POS_X), 0
        ld  a, (hs_sp_x)
        ld  (ix + T_POS_X + 1), a
        ; the average distance
        ld  hl, 0
        ld  (hs_sp_d), hl
        call hs_mem_first
hs_sp_dl:
        jr  z, hs_sp_d2
        call hs_tr_dist
        call hs2_rounded
        ld  de, (hs_sp_d)
        add hl, de
        ld  (hs_sp_d), hl
        call hs_mem_next
        jr  hs_sp_dl
hs_sp_d2:
        ld  hl, (hs_sp_d)
        ld  de, (hs_sp_n)
        call udiv16
        ld  (hs_sp_d), hl
        ; near the target?
        ld  a, (ix + T_TARGET)
        or  (ix + T_TARGET + 1)
        jr  z, hs_sp_x1
        ld  a, (ix + T_TARGETTILE)
        or  (ix + T_TARGETTILE + 1)
        jr  z, hs_sp_x1
        ld  l, (ix + T_TARGET)
        ld  h, (ix + T_TARGET + 1)
        call ref_square
        push hl
        ld  hl, (hs_sp_y)
        call hs2_row_col        ; HL = y * 64 + the column in hs_sp_x
        pop de
        call tile_distance_packed
        ld  de, 11
        call hs2_cmps
        jp  p, hs_sp_x1         ; > 10
        ld  (ix + T_TARGETTILE), 2
        ld  (ix + T_TARGETTILE + 1), 0
hs_sp_x1:
        ld  hl, (hs_sp_d)
        ret

; HL = a row -> HL = row * 64 + (hs_sp_x).
hs2_row_col:
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  de, (hs_sp_x)
        add hl, de
        ret

; HL = a distance in 1/256 squares -> HL = (it + $80) >> 8
; (tile_distance_squares $0115C2).
hs2_rounded:
        ld  de, $80
        add hl, de
        ld  l, h
        ld  h, 0
        ret

; TEAM 5 gather ($02E7C0): n on the stack.  A member further than n
; squares from the centre (n + 2 if where it is going is nearer to it than
; the centre) is ordered to Move to a random square within n * 16 / 256
; ... of the centre - y from one draw, x from another (Mega Drive,
; $02E88E/$02E8A2); the rest are ordered to Guard.  -> HL = how many moved.
ef_t_gather:
        xor a
        call emc_arg
        ld  (hs_ga_n), hl
        call hs_team
        ld  hl, 0
        ld  (hs_ga_sent), hl
        call hs_mem_first
hs_ga_l:
        jp  z, hs_ga_x
        ; d6 = the member's distance from the centre
        call hs_tr_dist
        call hs2_rounded
        ld  (hs_ga_d6), hl
        ld  a, (iy + U_TARGETMOVE)
        or  (iy + U_TARGETMOVE + 1)
        jr  nz, hs_ga_1
        ld  hl, $40
        ld  (hs_ga_d5), hl
        ld  (hs_ga_d7), hl
        jr  hs_ga_2
hs_ga_1:
        ld  l, (iy + U_TARGETMOVE)
        ld  h, (iy + U_TARGETMOVE + 1)
        ld  de, hs_pos2
        call ref_position       ; d7 = where it is going
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, hs_pos2
        call tile_distance
        call hs2_rounded
        ld  (hs_ga_d5), hl      ; the member from there
        push ix
        pop hl
        ld  de, T_POS_Y
        add hl, de
        ld  de, hs_pos2
        call tile_distance
        call hs2_rounded
        ld  (hs_ga_d7), hl      ; the centre from there
hs_ga_2:
        ld  hl, (hs_ga_d5)
        ld  de, (hs_ga_d7)
        or  a
        sbc hl, de              ; d5 < d7 (unsigned)?
        ld  hl, (hs_ga_n)
        jr  nc, hs_ga_3
        inc hl
        inc hl                  ; n + 2
hs_ga_3:
        ex  de, hl
        ld  hl, (hs_ga_d6)
        or  a
        sbc hl, de              ; d6 > limit?
        jr  z, hs_ga_guard
        jr  c, hs_ga_guard
        ; Move to a random square near the centre
        ld  a, ORDER_MOVE
        push iy
        pop hl
        push ix
        push hl
        pop ix
        FCALL unit_give_order
        pop ix
        ld  a, (hs_ga_n)
        add a, a
        add a, a
        add a, a
        add a, a                ; n << 4 (n is small)
        ld  c, a
        push ix
        pop hl
        ld  de, T_POS_Y
        add hl, de
        push hl
        push bc
        ld  de, hs_pos
        ld  b, 1
        call hs_tmbr            ; the first draw: x
        pop bc
        pop hl
        ld  de, hs_pos2
        ld  b, 1
        call hs_tmbr            ; the second: y
        ld  a, (hs_pos + 3)
        ld  (hs_pos2 + 3), a
        ld  hl, hs_pos2
        call pos_square
        call ref_make_square
        push ix
        push iy
        pop ix
        FCALL hs_set_destination
        pop ix
        ld  hl, (hs_ga_sent)
        inc hl
        ld  (hs_ga_sent), hl
        jr  hs_ga_n1
hs_ga_guard:
        ld  a, ORDER_GUARD
        push ix
        push iy
        pop ix
        FCALL unit_give_order
        pop ix
hs_ga_n1:
        call hs_mem_next
        jp  hs_ga_l
hs_ga_x:
        ld  hl, (hs_ga_sent)
        ret

; TEAM 6 find.target ($02E906): the first member whose unit_find_target
; (mode 4 for Kamikaze, action 3, else 0) answers something makes it the
; team's target; if it is new, targetTile = map_tile_in_direction_of(the
; member's square, the target's).  -> HL = the target or 0.
ef_t_find_target:
        call hs_team
        call hs_mem_first
hs_ft_l:
        jr  z, hs_ft_none
        ld  a, (ix + T_ACTION)
        cp  3
        ld  a, 4
        jr  z, hs_ft_1
        xor a
hs_ft_1:
        push ix
        push iy
        pop ix
        FCALL unit_find_target
        pop ix
        ld  a, h
        or  l
        jr  nz, hs_ft_got
        call hs_mem_next
        jr  hs_ft_l
hs_ft_got:
        ld  a, l
        cp  (ix + T_TARGET)
        jr  nz, hs_ft_new
        ld  a, h
        cp  (ix + T_TARGET + 1)
        ret z
hs_ft_new:
        ld  (ix + T_TARGET), l
        ld  (ix + T_TARGET + 1), h
        push hl
        call ref_square
        ex  de, hl              ; DE = the target's square
        push iy
        pop hl
        push de
        ld  de, O_POS_Y
        add hl, de
        call pos_square         ; HL = the member's square
        pop de
        call hs_tile_in_direction_of
        ld  (ix + T_TARGETTILE), l
        ld  (ix + T_TARGETTILE + 1), h
        pop hl
        ret
hs_ft_none:
        ld  hl, 0
        ret

; TEAM 7 attack ($02E9C4): with a target, every member is sent at it: to a
; point at its fire range from the target, in the direction from the
; target to it turned by rand(0, 127) - 64 (the PC took the quadrant); the
; target's own square if that point has something on it; and aimed at the
; target - given Attack first unless it is attacking already.  A member
; already attacking this target is left alone if it is going somewhere or
; stands at or beyond its range.  (The "no target: Guard" branch cannot be
; reached: the target is tested at the top - nothing to do.)
ef_t_attack:
        call hs_team
        ld  a, (ix + T_TARGET)
        or  (ix + T_TARGET + 1)
        jp  z, hs_tr_zero
        ld  l, (ix + T_TARGET)
        ld  h, (ix + T_TARGET + 1)
        ld  de, hs_at_pos
        call ref_position       ; d3
        ld  hl, hs_at_pos
        call pos_square
        ld  (hs_at_sq), hl      ; d6
        call hs_mem_first
hs_at_l:
        jp  z, hs_tr_zero
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_fireDistance
        add hl, de
        ld  a, (hl)
        ld  (hs_at_range + 1), a
        xor a
        ld  (hs_at_range), a    ; d4 = range << 8
        ld  a, (iy + U_ACTION)
        or  a
        jr  nz, hs_at_go
        ; attacking already: this target?
        ld  a, (iy + U_TARGETATTACK)
        cp  (ix + T_TARGET)
        jr  nz, hs_at_go
        ld  a, (iy + U_TARGETATTACK + 1)
        cp  (ix + T_TARGET + 1)
        jr  nz, hs_at_go
        ld  a, (iy + U_TARGETMOVE)
        or  (iy + U_TARGETMOVE + 1)
        jp  nz, hs_at_n
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, hs_at_pos
        call tile_distance
        ld  de, (hs_at_range)
        ex  de, hl
        call hs2_cmps           ; range <= distance: left alone (ble)
        jp  m, hs_at_n
        jp  z, hs_at_n
hs_at_go:
        ld  a, (iy + U_ACTION)
        or  a
        jr  z, hs_at_1
        push ix
        push iy
        pop ix
        xor a                   ; ORDER_ATTACK
        FCALL unit_give_order
        pop ix
hs_at_1:
        ; the direction from the target to the member, turned
        ld  de, $007F
        call rand_between
        ld  (hs_at_r), a
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        ld  hl, hs_at_pos
        call tile_direction     ; A = from the target to the member
        ld  b, a
        ld  a, (hs_at_r)
        add a, b
        sub $40                 ; (& $FF: the mover masks it)
        ld  (hs_at_dir), a
        ; the point: range from the target (capped at 255 by the mover)
        ld  hl, hs_at_pos
        ld  de, hs_pos
        ld  bc, 4
        ldir
        ld  hl, (hs_at_range)
        ld  c, 255
        ld  a, h
        or  a
        jr  nz, hs_at_2
        ld  c, l
hs_at_2:
        ld  a, (hs_at_dir)
        ld  hl, hs_pos
        call tile_move_by_direction
        ld  hl, hs_pos
        call pos_square
        push hl
        FCALL map_object_at
        pop hl
        jr  z, hs_at_3
        ld  hl, (hs_at_sq)
hs_at_3:
        call ref_make_square
        push ix
        push iy
        pop ix
        FCALL hs_set_destination
        pop ix
        ld  l, (ix + T_TARGET)
        ld  h, (ix + T_TARGET + 1)
        push ix
        push iy
        pop ix
        FCALL unit_set_target
        pop ix
hs_at_n:
        call hs_mem_next
        jp  hs_at_l

; TEAM 8 behave ($02EB66): n on the stack; if it is not the behaviour the
; team runs, the script restarts at entry n.
ef_t_behave:
        xor a
        call emc_arg
        push hl
        call hs_team
        pop hl
        ld  a, l
        cp  (ix + T_ACTION)
        jr  nz, hs_be_go
        ld  a, h
        cp  (ix + T_ACTION + 1)
        jr  z, hs_be_x
hs_be_go:
        ld  (ix + T_ACTION), l
        ld  (ix + T_ACTION + 1), h
hs_be_start:
        ld  de, T_SCRIPT
        add ix, de
        ld  a, EMC_TEAM
        FCALL emc_start
hs_be_x:
        ld  hl, 0
        ret

; TEAM 9 behave.orig ($02EBB2): back to the behaviour the mission gave.
ef_t_behave_orig:
        call hs_team
        ld  l, (ix + T_ACTIONSTART)
        ld  h, (ix + T_ACTIONSTART + 1)
        ld  a, l
        cp  (ix + T_ACTION)
        jr  nz, hs_be_go
        ld  a, h
        cp  (ix + T_ACTION + 1)
        jr  nz, hs_be_go
        jr  hs_be_x

; ================================================ where things arrive (S8)

; map_find_location ($01AD6C): A = the kind 0-7, B = the house (kinds 6
; and 7) -> HL = a square, or 0.  Keeps IX, IY.
;
;   0-3  north, east, south, west: a random square on that edge of the
;        playable area.  S8 port: the edges count from the area's origin
;        (x0 + w - 1 ...); the cartridge adds w and h to 0, which on a
;        64 x 64 map is the same square and on a 32 x 32 map is row or
;        column 1, or 32 - the middle of the battlefield.  The random
;        draws are the cartridge's: rand(1, w) and rand(1, h).
;   4    anywhere: rand(1, w), rand(1, h) until the square is playable
;        (as the cartridge: no origin added).
;   5    visible: the view's top-left square + rand(0, 4) rows,
;        rand(0, 6) columns, until playable.
;   6, 7 enemy base, home base: up to five passes over the structures; for
;        each, a point moved twice at random by up to $38 (row from the
;        second, column from the first), taken if it is playable, empty
;        and within 7 squares of the structure; 0 if none.  S8 port: 7 is
;        the house's own structures and 6 those of houses not allied with
;        it - the cartridge takes the player's side for both.
; A square with something on it is thrown away and the kind tried again
; (0-5).
map_find_location:
        push ix
        push iy
        ld  (hs_fl_kind), a
        ld  a, b
        ld  (hs_fl_house), a
hs_fl_again:
        ld  a, (map_scale)
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_playable_area
        add hl, de
        ld  a, (hl)
        ld  (hs_fl_x0), a
        inc hl
        inc hl
        ld  a, (hl)
        ld  (hs_fl_y0), a
        inc hl
        inc hl
        ld  a, (hl)
        ld  (hs_fl_w), a
        inc hl
        inc hl
        ld  a, (hl)
        ld  (hs_fl_h), a
        ld  a, (hs_fl_kind)
        cp  8
        jr  c, hs_fl_k
        ld  hl, 0               ; no such kind
        jp  hs_fl_out
hs_fl_k:
        cp  6
        jp  nc, hs_fl_base
        or  a
        jr  z, hs_fl_north
        dec a
        jr  z, hs_fl_east
        dec a
        jr  z, hs_fl_south
        dec a
        jr  z, hs_fl_west
        dec a
        jr  z, hs_fl_air
        ; 5: near the view
hs_fl_view:
        ld  de, $0006
        call rand_between
        ld  c, a                ; the column step (drawn first)
        ld  de, $0004
        call rand_between
        ld  b, a                ; the row step
        ld  hl, (tactical_pos)
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        add a, b                ; the row
        ld  b, a
        ld  a, (tactical_pos)
        and $3F
        add a, c
        ld  c, a
        call hs_fl_sq
        call map_valid
        jr  nc, hs_fl_view
        jr  hs_fl_check
hs_fl_north:
        call hs_fl_randw        ; the column
        ld  c, a
        ld  a, (hs_fl_y0)
        ld  b, a
        jr  hs_fl_edge
hs_fl_east:
        call hs_fl_randh
        ld  b, a
        ld  a, (hs_fl_x0)
        ld  c, a
        ld  a, (hs_fl_w)
        add a, c
        dec a
        ld  c, a
        jr  hs_fl_edge
hs_fl_south:
        call hs_fl_randw
        ld  c, a
        ld  a, (hs_fl_y0)
        ld  b, a
        ld  a, (hs_fl_h)
        add a, b
        dec a
        ld  b, a
        jr  hs_fl_edge
hs_fl_west:
        call hs_fl_randh
        ld  b, a
        ld  a, (hs_fl_x0)
        ld  c, a
hs_fl_edge:
        call hs_fl_sq
        jr  hs_fl_check
hs_fl_air:
        ld  a, (hs_fl_w)
        ld  e, a
        ld  d, 1
        call rand_between
        ld  c, a
        ld  a, (hs_fl_h)
        ld  e, a
        ld  d, 1
        call rand_between
        ld  b, a
        call hs_fl_sq
        call map_valid
        jr  nc, hs_fl_air
hs_fl_check:
        ; $FFF of it; 0 or taken: again
        ld  a, h
        and $0F
        ld  h, a
        or  l
        jp  z, hs_fl_again
        push hl
        FCALL map_object_at
        pop hl
        jp  nz, hs_fl_again
hs_fl_out:
        pop iy
        pop ix
        ret

; A = rand(1, w) + x0 - 1: a column.  (rand(1, h) + y0 - 1: a row.)
hs_fl_randw:
        ld  a, (hs_fl_w)
        ld  e, a
        ld  d, 1
        call rand_between
        ld  hl, hs_fl_x0
        add a, (hl)
        dec a
        ret
hs_fl_randh:
        ld  a, (hs_fl_h)
        ld  e, a
        ld  d, 1
        call rand_between
        ld  hl, hs_fl_y0
        add a, (hl)
        dec a
        ret

; B = a row, C = a column -> HL = the square (row * 64 + column, $FFF).
hs_fl_sq:
        ld  l, b
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, c
        add a, l
        ld  l, a
        ld  a, h
        adc a, 0
        and $0F
        ld  h, a
        ret

; Kinds 6 and 7.
hs_fl_base:
        ld  a, 5
        ld  (hs_fl_pass), a
hs_fl_bp:
        xor a
        ld  (hs_fl_i), a
hs_fl_bl:
        ld  a, (struct_find_count)
        ld  b, a
        ld  a, (hs_fl_i)
        cp  b
        jp  nc, hs_fl_bnext
        ld  e, a
        ld  d, 0
        ld  hl, struct_find
        add hl, de
        ld  a, (hl)
        call struct_ptr
        push hl
        pop iy
        ; a structure that is on a side list (no slab, no wall)
        ld  a, (iy + O_TYPE)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_struct_side_list
        add hl, de
        ld  a, (hl)
        or  a
        jp  z, hs_fl_bn
        ; the house's own (7), or one not allied with it (6)
        ld  a, (hs_fl_house)
        ld  b, a
        ld  c, (iy + O_HOUSE)
        ld  a, (hs_fl_kind)
        cp  7
        jr  nz, hs_fl_b6
        ld  a, b
        cp  c
        jp  nz, hs_fl_bn
        jr  hs_fl_b1
hs_fl_b6:
        call house_are_allied
        or  a
        jp  nz, hs_fl_bn
hs_fl_b1:
        ; two random points round it: the column of the first, the row
        ; of the second
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        push hl
        ld  de, hs_pos
        ld  bc, $0138
        call hs_tmbr
        pop hl
        ld  de, hs_pos2
        ld  bc, $0138
        call hs_tmbr
        ld  a, (hs_pos + 3)
        ld  (hs_pos2 + 3), a
        ld  hl, hs_pos2
        call pos_square
        call map_valid
        jr  nc, hs_fl_bn
        ld  (hs_fl_sqr), hl
        FCALL map_object_at
        jr  nz, hs_fl_bn
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  de, (hs_fl_sqr)
        call tile_distance_packed
        ld  a, h
        or  a
        jr  nz, hs_fl_bn
        ld  a, l
        cp  8
        jr  nc, hs_fl_bn
        ld  hl, (hs_fl_sqr)
        jp  hs_fl_out
hs_fl_bn:
        ld  hl, hs_fl_i
        inc (hl)
        jp  hs_fl_bl
hs_fl_bnext:
        ld  hl, hs_fl_pass
        dec (hl)
        jp  nz, hs_fl_bp
        ld  hl, 0
        jp  hs_fl_out

; tile_move_by_random ($011688): HL -> a position, DE -> where the answer
; goes, C = the distance (1-255), B = 1 to centre it in its square.  A
; random fraction of the distance (a random byte halved until below it) in
; a random direction: x += sin * d >> 3 & $FFF0, y += -cos * d >> 3 &
; $FFF0.  Off squares 1-62 the original comes back.  Clobbers A, BC, HL.
hs_tmbr:
        ld  (hs_tm_src), hl
        ld  (hs_tm_dst), de
        ld  a, b
        ld  (hs_tm_centre), a
        push bc
        ld  bc, 4
        ldir                    ; the answer starts as the original
        pop bc
        ld  a, c
        or  a
        ret z                   ; distance 0: unchanged
        call random
hs_tm_f:
        cp  c                   ; halved while the distance <= it
        jr  c, hs_tm_1
        srl a
        jr  hs_tm_f
hs_tm_1:
        ld  (hs_tm_d), a
        call random
        ld  (hs_tm_dir), a
        ; x += sin * d >> 3 & $FFF0
        ld  e, a
        ld  d, 0
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        ld  hl, hs_tm_d
        ld  c, (hl)
        call smul_d8
        call hs_sar3_f0
        ld  (hs_tm_dx), hl
        ; y += -cos * d >> 3 & $FFF0
        ld  a, (hs_tm_dir)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        ld  hl, hs_tm_d
        ld  c, (hl)
        call smul_d8
        call hs_sar3_f0
        ld  (hs_tm_dy), hl
        ld  hl, (hs_tm_src)
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push hl
        ld  hl, (hs_tm_dy)
        add hl, de
        ld  (hs_tm_ny), hl
        pop hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (hs_tm_dx)
        add hl, de
        ld  (hs_tm_nx), hl
        ; inside squares 1-62 on both axes, or the original stays
        ld  hl, (hs_tm_ny)
        call hs_tm_inmap
        ret nc
        ld  hl, (hs_tm_nx)
        call hs_tm_inmap
        ret nc
        ld  hl, (hs_tm_dst)
        ld  de, (hs_tm_ny)
        call hs_tm_put
        ld  de, (hs_tm_nx)
hs_tm_put:
        ld  a, (hs_tm_centre)
        or  a
        jr  z, hs_tm_p1
        ld  e, $80
hs_tm_p1:
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ret

; HL = a coordinate -> carry if it is in [$100, $3F00).
hs_tm_inmap:
        ld  a, h
        cp  $3F
        ret nc
        cp  1
        ccf
        ret

; HL = HL >> 3 (arithmetic) & $FFF0.
hs_sar3_f0:
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

; map_tile_in_direction_of ($01B03A): HL = the start square, DE = the
; destination -> HL = a square to head for, or 0: none if either is 0 or
; they are 10 or fewer squares apart; else up to four tries at a point
; min(distance, 20) squares (the mover caps it at 255/256) from the
; destination, on the bearing from the destination back to the start
; turned a random 31-94 either way, the first that is playable.
hs_tile_in_direction_of:
        ld  a, h
        or  l
        jr  z, hs_td_none
        ld  a, d
        or  e
        jr  z, hs_td_none
        ld  (hs_td_start), hl
        ld  (hs_td_dest), de
        push de
        call tile_distance_packed
        pop de
        ld  a, h
        or  a
        jr  nz, hs_td_far
        ld  a, l
        cp  11
        jr  c, hs_td_none
hs_td_far:
        ld  hl, (hs_td_dest)
        ld  de, (hs_td_start)
        call tile_direction_packed
        ld  (hs_td_dir), a
        ld  a, 4
        ld  (hs_td_try), a
hs_td_l:
        call random
        and $3F
        add a, $1F
        ld  b, a
        call random
        rrca
        ld  a, b
        jr  nc, hs_td_1
        neg
hs_td_1:
        ld  hl, hs_td_dir
        add a, (hl)
        push af
        ld  hl, (hs_td_dest)
        ld  de, hs_pos
        call square_centre
        pop af
        ld  c, 255
        ld  hl, hs_pos
        call tile_move_by_direction
        ld  hl, hs_pos
        call pos_square
        call map_valid
        ret c
        ld  hl, hs_td_try
        dec (hl)
        jr  nz, hs_td_l
hs_td_none:
        ld  hl, 0
        ret

; ============================================================ the end (S9)

; game_check_level_end ($022AAE): when the clock is past tickLevelEnd, ask
; whether the mission is over; either way tickLevelEnd = the clock + 300.
; -> A = 0 once it is over (level_result 1 won, 2 lost), else 1.  Keeps IX,
; IY.
;
; Over: levelOver = 1; music and voices stop; won -> the next mission
; (campaignID + 1, scenarioID = campaignID + 1; 10 after the ninth - the
; ending, and the machine restarts), mission 9 won plays music $26; lost
; -> voice $29, the score cut to a tenth (towards 0, never negative), the
; same mission again.  Either way the player's doneFullScaleAttack is
; cleared and the score page's numbers are left in WORLD (score_*).  The
; fly-overs, the screens and the mentat are the front end's.
game_check_level_end:
        push ix
        push iy
        call hs2_clock
        ld  hl, tick_level_end
        ld  de, hs_now
        call hs2_cp32           ; C: tick < now
        ld  a, 1
        jp  nc, hs_le_out
        call hs_level_finished
        or  a
        ld  a, 1
        jp  z, hs_le_next
        ; over
        xor a
        FCALL snd_music         ; stop the music
        ld  a, $FE
        FCALL snd_voice         ; and the voices
        ld  a, (campaign_id)
        inc a
        ld  (score_mission), a
        ; the time: the clock less missionStartTime
        ld  hl, hs_now
        ld  de, score_ticks
        ld  bc, 4
        ldir
        ld  hl, score_ticks
        ld  de, mission_start_time
        call hs2_sub32
        call hs_score_time
        call hs_level_won
        or  a
        jr  z, hs_le_lost
        ld  a, 1
        ld  (level_result), a
        ld  a, (campaign_id)
        cp  8
        jr  nz, hs_le_w1
        ld  a, $26
        FCALL snd_music
        ld  a, 8                ; Ruler of Arrakis
        ld  (score_rank), a
        jr  hs_le_w2
hs_le_w1:
        call hs_score_rank
hs_le_w2:
        ld  a, (campaign_id)
        inc a
        ld  (campaign_id), a
        inc a
        ld  (scenario_id), a    ; 10 after the ninth: the ending
        jr  hs_le_both
hs_le_lost:
        ld  a, 2
        ld  (level_result), a
        ld  a, $29
        FCALL snd_voice
        ld  hl, (score)
        ld  de, 10
        call sdiv16
        bit 7, h
        jr  z, hs_le_l1
        ld  hl, 0
hs_le_l1:
        ld  (score), hl
        call hs_score_rank
hs_le_both:
        ld  a, (player_house)
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        res HF_FULLATTACK, (hl)
        xor a
hs_le_next:
        push af
        ld  hl, hs_now
        ld  bc, tick_level_end
        ld  de, 300
        call hs2_add_to
        pop af
hs_le_out:
        pop iy
        pop ix
        ret

; game_is_level_finished ($0229B4) -> A = 1 if over (and levelOver = 1):
; the player has no structure left, or - after mission 1 - nobody else has
; one, or (winFlags bit 2) the credits counter shows the quota.
hs_level_finished:
        ld  a, (structs_player)
        or  a
        jr  z, hs_lf_yes
        ld  a, (structs_other)
        or  a
        jr  nz, hs_lf_q
        ld  a, (campaign_id)
        or  a
        jr  nz, hs_lf_yes
hs_lf_q:
        ld  a, (win_flags)
        and 4
        ret z
        call hs_quota_met
        or  a
        ret z
hs_lf_yes:
        ld  a, 1
        ld  (level_over), a
        ret

; game_is_level_won ($022A28) -> A = 1 if won.  loseFlags bits 0-1: the
; player still has a structure and (after mission 1) nobody else has;
; bit 2: the counter shows the quota; bit 3: only before the timeout,
; which nothing sets (0), so never (kept: no mission uses it).
hs_level_won:
        ld  c, 0
        ld  a, (lose_flags)
        and 3
        jr  z, hs_lw_2
        ld  a, (structs_player)
        or  a
        jr  z, hs_lw_2
        ld  a, (campaign_id)
        or  a
        jr  z, hs_lw_1
        ld  a, (structs_other)
        or  a
        jr  nz, hs_lw_2
hs_lw_1:
        ld  c, 1
hs_lw_2:
        ld  a, (lose_flags)
        and 4
        jr  z, hs_lw_3
        ld  a, c
        or  a
        jr  nz, hs_lw_3
        push bc
        call hs_quota_met
        pop bc
        ld  c, a
hs_lw_3:
        ld  a, (lose_flags)
        and 8
        jr  z, hs_lw_4
        ld  c, 0                ; the clock is never below tickGameTimeout (0)
hs_lw_4:
        ld  a, c
        ret

; -> A = 1 if credits_shown is not $FFFF and the player's quota <= it.
hs_quota_met:
        ld  hl, (credits_shown + 2)
        ld  a, h
        or  l
        jr  nz, hs_qm_1
        ld  hl, (credits_shown)
        ld  a, h
        and l
        inc a
        jr  z, hs_qm_no         ; exactly $FFFF
hs_qm_1:
        ld  a, (player_house)
        call house_ptr
        ld  de, H_QUOTA
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, hs_q
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  (hl), 0
        inc hl
        ld  (hl), 0
        ld  hl, credits_shown
        ld  de, hs_q
        call hs2_cp32           ; C: shown < quota
        ld  a, 0
        ret c
        inc a
        ret
hs_qm_no:
        xor a
        ret

; score_rank from score: how many of the thresholds at $0A68CA the score
; reaches, unsigned (score_put_totals $026EEE).
hs_score_rank:
        ld  hl, hs_thresholds
        ld  b, 0
hs_sr_l:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push hl
        ld  hl, (score)
        or  a
        sbc hl, de
        pop hl
        jr  c, hs_sr_x
        inc b
        ld  a, b
        cp  8
        jr  c, hs_sr_l
hs_sr_x:
        ld  a, b
        ld  (score_rank), a
        ret
hs_thresholds:
        DW  50, 100, 150, 200, 250, 300, 400, $FFFF

; score_ticks -> score_hours = ticks / 3000 / 60, score_minutes = the rest
; (score_ticks_to_time $026CE4, 50 a second).
hs_score_time:
        ld  hl, score_ticks
        ld  de, hs_dv
        ld  bc, 4
        ldir
        ld  bc, 3000
        call hs2_div32
        ld  bc, 60
        call hs2_div32          ; HL = the remainder: the minutes
        ld  (score_minutes), hl
        ld  hl, (hs_dv)
        ld  (score_hours), hl
        ret

; ============================================================ helpers

hs2_clock:
        di
        ld  hl, (timer_game)
        ld  (hs_now), hl
        ld  hl, (timer_game + 2)
        ld  (hs_now + 2), hl
        ei
        ret

; HL -> a, DE -> b: carry if a < b (32 bits, unsigned), Z if equal.  Keeps
; HL, DE.
hs2_cp32:
        push hl
        push de
        inc hl
        inc hl
        inc hl
        inc de
        inc de
        inc de
        ld  b, 4
hs2_c32l:
        ld  a, (de)
        ld  c, a
        ld  a, (hl)
        cp  c
        jr  nz, hs2_c32x
        dec hl
        dec de
        djnz hs2_c32l
hs2_c32x:
        pop de
        pop hl
        ret

; (BC) = (HL) + DE, 32 bits.
hs2_add_to:
        ld  a, (hl)
        add a, e
        ld  (bc), a
        inc hl
        inc bc
        ld  a, (hl)
        adc a, d
        ld  (bc), a
        inc hl
        inc bc
        ld  a, (hl)
        adc a, 0
        ld  (bc), a
        inc hl
        inc bc
        ld  a, (hl)
        adc a, 0
        ld  (bc), a
        ret

; (HL) -= (DE), 32 bits.
hs2_sub32:
        ld  b, 4
        or  a
hs2_s32l:
        ld  a, (de)
        ld  c, a
        ld  a, (hl)
        sbc a, c
        ld  (hl), a
        inc hl
        inc de
        djnz hs2_s32l
        ret

; Signed HL against DE: the S flag of HL - DE (with overflow corrected):
; M if HL < DE, P if HL >= DE; Z if equal.  Clobbers A.
hs2_cmps:
        push hl
        or  a
        sbc hl, de
        jr  z, hs2_cmps_z
        jp  po, hs2_cmps_ok
        ld  a, h
        xor $80
        or  1                   ; flip the sign, NZ
        pop hl
        ret
hs2_cmps_ok:
        ld  a, h
        or  1
        pop hl
        ret
hs2_cmps_z:
        pop hl
        ret                     ; Z, P

; hs_dv (32 bits) /= BC (below 32768); HL = the remainder.
hs2_div32:
        push ix
        ld  ix, hs_dv
        ld  hl, 0
        ld  d, 32
hs2_d32l:
        sla (ix + 0)
        rl  (ix + 1)
        rl  (ix + 2)
        rl  (ix + 3)
        adc hl, hl
        or  a
        sbc hl, bc
        jr  nc, hs2_d32f
        add hl, bc
        jr  hs2_d32n
hs2_d32f:
        inc (ix + 0)
hs2_d32n:
        dec d
        jr  nz, hs2_d32l
        pop ix
        ret

; ------------------------------------------------------- the bank's own
hs_ti:          DB 0
hs_tr_slot:     DB 0
hs_tr_best:     DW 0
hs_tr_bestd:    DW 0
hs_tr_other:    DW 0
hs_tr_otherd:   DW 0
hs_sp_n:        DW 0
hs_sp_x:        DW 0
hs_sp_y:        DW 0
hs_sp_d:        DW 0
hs_ga_n:        DW 0
hs_ga_sent:     DW 0
hs_ga_d5:       DW 0
hs_ga_d6:       DW 0
hs_ga_d7:       DW 0
hs_at_pos:      DS 4
hs_at_sq:       DW 0
hs_at_range:    DW 0
hs_at_r:        DB 0
hs_at_dir:      DB 0
hs_fl_kind:     DB 0
hs_fl_house:    DB 0
hs_fl_x0:       DB 0
hs_fl_y0:       DB 0
hs_fl_w:        DB 0
hs_fl_h:        DB 0
hs_fl_pass:     DB 0
hs_fl_i:        DB 0
hs_fl_sqr:      DW 0
hs_tm_src:      DW 0
hs_tm_centre:   DB 0
hs_tm_dst:      DW 0
hs_tm_d:        DB 0
hs_tm_dir:      DB 0
hs_tm_dx:       DW 0
hs_tm_dy:       DW 0
hs_tm_nx:       DW 0
hs_tm_ny:       DW 0
hs_td_start:    DW 0
hs_td_dest:     DW 0
hs_td_dir:      DB 0
hs_td_try:      DB 0
hs_q:           DS 4
hs_dv:          DS 4
