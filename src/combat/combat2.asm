; combat2.asm - bank COMBAT2: the rest of the COMBAT subsystem (S4): the
; script routines of UNIT.EMC and BUILD.EMC that combat owns, dying, the
; Deviator, the Palace's weapons, the Sandworm's choice, the turrets, and
; the small pieces of other specs that combat's routines need (a dying
; player's unit leaving its team, spilt spice, the references to a
; destroyed structure, a unit put on the map).
;
; Routines here far-call into COMBAT (map_make_explosion,
; fx_explosion_start, unit_fire_projectile ...).  A script routine (ef_*)
; is called with IX = the script state and answers in HL; it may leave IX
; changed (the machine keeps its own).  Other routines keep IX unless they
; say so.

; =================================================== UNIT.EMC's routines

; UNIT 28 find.target ($043D60): the argument is the mode (S4).
ef_u_find_target:
        xor a
        call emc_arg
        ld  a, l
        call cb_2obj
        FCALL unit_find_target
        ret

; UNIT 13 enemy? ($0113AC): 1 if the reference names a unit or a
; structure whose house is not the running object's (S7).  Places and
; stale references answer 0.
ef_u_enemy:
        xor a
        call emc_arg
        call cb_2obj
cb_2enemy:
        ld  (cb_2ref), hl
        call ref_is_valid
        or  a
        jr  z, cb_2zero
        ld  hl, (cb_2ref)
        call cb_2ref_object
        jr  z, cb_2zero
        ld  a, (cb_2ref + 1)
        and $C0
        cp  REF_TILE >> 8
        jr  z, cb_2zero
        ld  de, O_HOUSE
        add hl, de
        ld  a, (hl)
        cp  (ix + O_HOUSE)
        jr  z, cb_2zero
cb_2one:
        ld  hl, 1
        ret
cb_2zero:
        ld  hl, 0
        ret

; UNIT 17 friend? ($011358): 1 if the reference names an object in use
; and on the map (flags & 5 = 1) that enemy? does not call an enemy.
ef_u_friend:
        xor a
        call emc_arg
        call cb_2obj
        push hl
        call cb_2ref_object
        pop de
        jr  z, cb_2zero
        inc hl
        inc hl
        inc hl
        inc hl
        ld  a, (hl)
        and 5
        dec a
        jr  nz, cb_2zero
        ex  de, hl
        call cb_2enemy
        ld  a, l
        xor 1
        ld  l, a
        ret

; UNIT 59 not.unit? ($01118A): 1 unless the reference names a unit.
ef_u_not_unit:
        xor a
        call emc_arg
        ld  a, h
        and $C0
        cp  REF_UNIT >> 8
        jr  z, cb_2zero
        jr  cb_2one

; UNIT 58 aim ($044E04): targetAttack = the reference (S4).  A unit with
; no turret also heads there and turns its hull; the gun turns either
; way.  A stale reference clears the target.  A Harvester does nothing;
; a Sandworm heading for a place keeps its target until it is there.
; Answers the target.
ef_u_aim:
        xor a
        call emc_arg
        ld  (cb_2ref), hl
        call cb_2obj
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_2zero
        cp  UNIT_SANDWORM
        jr  nz, cb_2aim1
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ld  a, h
        and $C0
        cp  REF_TILE >> 8
        jr  nz, cb_2aim1
        ld  a, (ix + U_TARGETMOVE)
        cp  l
        jr  nz, cb_2aim1
        ld  a, (ix + U_TARGETMOVE + 1)
        cp  h
        jr  nz, cb_2aim1
        call ref_square
        push hl
        call cb_2sq
        pop de
        or  a
        sbc hl, de
        jr  nz, cb_2aim_keep    ; not there yet: keep it
        ld  a, (ix + O_POS_Y)
        or  (ix + O_POS_X)
        and $7F
        jr  z, cb_2aim1
cb_2aim_keep:
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ret
cb_2aim1:
        ld  hl, (cb_2ref)
        ld  a, h
        or  l
        jr  z, cb_2aim_clear
        call ref_is_valid
        or  a
        jr  nz, cb_2aim2
cb_2aim_clear:
        xor a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
        ld  hl, 0
        ret
cb_2aim2:
        ld  hl, (cb_2ref)
        ld  de, cb_2p
        call ref_position
        call cb_2pos
        ld  de, cb_2p
        call tile_direction
        ld  (cb_2dir), a
        ld  hl, (cb_2ref)
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
        call cb_2uinfo
        bit 6, (iy + UI_objectFlags)        ; hasTurret
        jr  nz, cb_2aim3
        ld  hl, (cb_2ref)       ; (cb_2uinfo left the type record in HL)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  a, (cb_2dir)
        ld  bc, 0               ; the hull, not at once
        FCALL unit_set_facing
cb_2aim3:
        ld  a, (cb_2dir)
        ld  bc, 1               ; the turret, not at once
        FCALL unit_set_facing
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ret

; UNIT 54 find.prey ($045EC6, worm_find_prey $047650): the unit the
; Sandworm most wants, of every unit a search finds (later ones win
; ties; a best score of 0 or less answers 0) (S4, S7).
ef_u_find_prey:
        call cb_2obj
        ld  hl, 0
        ld  (cb_2best), hl
        ld  (cb_2score), hl
        ld  b, 0
cb_2fp1:
        call cb_2unext
        jr  z, cb_2fp2
        push bc
        push hl
        pop iy
        call cb_2prey_score
        ld  de, (cb_2score)
        call cb_2scmp           ; score < best: no
        jr  c, cb_2fp3
        ld  (cb_2score), hl
        ld  (cb_2best), iy
cb_2fp3:
        pop bc
        jr  cb_2fp1
cb_2fp2:
        ld  hl, (cb_2score)
        ld  a, h
        or  l
        jp  z, cb_2zero
        ld  hl, (cb_2best)
        ld  a, (hl)
        ld  l, a
        ld  h, REF_UNIT >> 8
        ret

; worm_prey_score ($04754E): IX = the worm, IY = a unit -> HL.  0 unless
; its square is unveiled and sand-like (landscape isSand); 100 on foot,
; 1000 tracked or harvester, 5000 wheeled; four times that if it moves or
; is reloading; over the distance in squares, doubled under 2.
cb_2prey_score:
        call cb_2sq_iy
        push hl
        FCALL map_square_unveiled
        pop hl
        jr  z, cb_2ps0
        call map_landscape
        call landscape_info
        ld  de, LS_isSand
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  z, cb_2ps0
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        ld  hl, 100
        or  a
        jr  z, cb_2ps1
        ld  hl, 1000
        cp  3
        jr  c, cb_2ps1
        ld  hl, 5000
        jr  z, cb_2ps1
cb_2ps0:
        ld  hl, 0
        ret
cb_2ps1:
        ld  a, (iy + U_SPEED)
        or  (iy + U_FIREDELAY)
        jr  z, cb_2ps2
        add hl, hl
        add hl, hl
cb_2ps2:
        push hl
        call cb_2pos
        ex  de, hl
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call tile_distance
        ld  bc, $80
        add hl, bc
        ld  e, h
        ld  d, 0                ; DE = the distance in squares
        pop hl
        ld  a, d
        or  e
        jr  z, cb_2ps3
        push de
        call sdiv16
        pop de
cb_2ps3:
        ld  a, e
        cp  2
        ret nc
        add hl, hl
        ret

; UNIT 15 die ($0445EE): the unit is destroyed (S4).  Unless it flies,
; the score moves by max(cost / 100, 1): down for the player's (never
; below 0) with killedAllied, up with killedEnemy for anyone else's.  A
; Saboteur blows up: type 4, 500 damage, a scorch mark.  Then it is
; removed.
ef_u_die:
        call cb_2obj
        call cb_2uinfo
        ld  a, (iy + UI_movementType)
        cp  4
        jr  z, cb_2die2
        push iy
        pop hl
        ld  de, UI_buildCredits
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 100
        call sdiv16
        ld  de, 1
        call cb_2scmp
        jr  nc, cb_2die0
        ex  de, hl
cb_2die0:
        ex  de, hl              ; DE = the score
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, cb_2die1
        ld  hl, (killed_allied)
        inc hl
        ld  (killed_allied), hl
        ld  hl, (score)
        call cb_2scmp           ; score < s: the whole score
        jr  nc, cb_2die_a
        ld  d, h
        ld  e, l
cb_2die_a:
        or  a
        sbc hl, de
        ld  (score), hl
        jr  cb_2die2
cb_2die1:
        ld  hl, (killed_enemy)
        inc hl
        ld  (killed_enemy), hl
        ld  hl, (score)
        add hl, de
        ld  (score), hl
cb_2die2:
        ld  a, (player_house)
        FCALL unit_unseen_by_houses
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, cb_2die3
        call cb_2pos_arg
        ld  a, 4
        ld  hl, 500
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
        call cb_2pos_arg
        FCALL map_explosion_ground
cb_2die3:
        FCALL unit_remove
        ld  hl, 0
        ret

; UNIT 4 explode ($045808): the death animation where the unit stands and
; its sound: one run over (script variable 1 = 1) is squashed (22, 23,
; effect 35), anything else dies (20, 21 in its house's colours, effect
; 30); the lower number for the single infantry (type +$4C = 3).
ef_u_explode:
        call cb_2obj
        call cb_2uinfo
        call cb_2pos_arg
        ld  a, (ix + O_SCRIPT + SC_VARS + 2)
        dec a
        or  (ix + O_SCRIPT + SC_VARS + 3)
        ld  a, (iy + UI_f4C)
        jr  nz, cb_2ex1
        cp  3
        ld  a, 23
        jr  nz, cb_2ex0
        dec a
cb_2ex0:
        ld  c, 0
        FCALL fx_explosion_start
        ld  a, 35
        jr  cb_2ex3
cb_2ex1:
        cp  3
        ld  a, 21
        jr  nz, cb_2ex2
        dec a
cb_2ex2:
        ld  c, (ix + O_HOUSE)
        FCALL fx_explosion_start
        ld  a, 30
cb_2ex3:
        FCALL snd_effect
        ld  hl, 1
        ret

; UNIT 18 explode.big ($0446C8): a type-11 explosion on the unit with
; random(25, 50) damage and no cause, then seven of type 6 at +-random(3,
; 10) * 16 on each axis, each doing - and delayed by - d6 += random(10,
; 25), then a scorch mark (and the cartridge's screen shake of 16).  The
; cartridge never sets d6 first; the port starts it from 0 (S4: fix).
; The y offset borrows from the x offset's sign, as the 68000's 32-bit
; add does (S4: keep).
ef_u_explode_big:
        call cb_2obj
        call cb_2pos_arg
        ld  de, $1932           ; rand_between(25, 50)
        call rand_between
        ld  l, a
        ld  h, 0
        ld  a, 11
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
        ld  hl, 0
        ld  (cb_2d6), hl
        ld  a, 7
        ld  (cb_2n), a
cb_2eb1:
        ld  de, $0A19           ; d6 += rand_between(10, 25)
        call rand_between
        ld  e, a
        ld  d, 0
        ld  hl, (cb_2d6)
        add hl, de
        ld  (cb_2d6), hl
        call cb_2offset         ; x: negative if the random bit is set
        call random
        rra
        call c, neg_hl
        ld  (cb_2dx), hl
        call cb_2offset         ; y: negative if it is clear
        call random
        rra
        call nc, neg_hl
        ld  a, (cb_2dx + 1)     ; the borrow from x's sign
        rla
        jr  nc, cb_2eb2
        dec hl
cb_2eb2:
        ld  e, (ix + O_POS_Y)
        ld  d, (ix + O_POS_Y + 1)
        add hl, de
        ld  (arg_pos), hl
        ld  e, (ix + O_POS_X)
        ld  d, (ix + O_POS_X + 1)
        ld  hl, (cb_2dx)
        add hl, de
        ld  (arg_pos + 2), hl
        ld  a, 6
        ld  hl, (cb_2d6)
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
        ld  hl, cb_2n
        dec (hl)
        jr  nz, cb_2eb1
        call cb_2pos_arg
        FCALL map_explosion_ground
        ld  a, 16               ; view_shake_start(16) ($0447D2)
        FCALL view_shake_start
        ld  hl, 0
        ret
; HL = rand_between(3, 10) * 16.
cb_2offset:
        ld  de, $030A
        call rand_between
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ret

; UNIT 33 survivor ($04587C): with random < the type's spawnChance, a
; Soldier of the unit's house is made within 20 of it (centred in its
; square), inherits its deviation, and is given the order the argument
; names.  Answers 1 if one was made.
ef_u_survivor:
        xor a
        call emc_arg
        ld  a, l
        ld  (cb_2n), a
        call cb_2obj
        call cb_2uinfo
        call random
        ld  l, a
        ld  h, 0
        ld  e, (iy + UI_spawnChance)
        ld  d, (iy + UI_spawnChance + 1)
        call cb_2scmp
        jp  nc, cb_2zero
        call random
        ld  (cb_2dir), a        ; the facing
        call cb_2pos_arg
        ld  hl, arg_pos
        ld  de, 20
        ld  a, 1
        FCALL cb_tile_move_by_random
        ld  a, (cb_2dir)
        ld  d, a
        ld  b, UNIT_SOLDIER
        ld  c, (ix + O_HOUSE)
        ld  a, (ix + U_DEVIATED)
        ld  (cb_2t), a
        ld  a, $FF
        FCALL unit_spawn
        jp  z, cb_2zero
        push hl
        pop ix
        ld  a, (cb_2t)
        ld  (ix + U_DEVIATED), a
        ld  a, (cb_2n)
        FCALL unit_give_order
        jp  cb_2one

; ================================================== BUILD.EMC's routines

; BUILD 8 find.target ($00CA0C): the argument is n, the range (S4).  A
; turret keeps its target (script variable 2, +$26) while it is within n
; (3n for a flyer); otherwise the nearest unit of the other side's list
; that is allocated, in the playable area, seen by the turret's house and
; within n - and an unseen Ornithopter within 3n is taken at once.  Bit 7
; of +$07 (port: +$06 bit 7) says it has one.  Answers the reference.
ef_b_find_target:
        xor a
        call emc_arg
        ld  (cb_2n16), hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de
        ld  (cb_2n3), hl
        call cb_2obj
        ld  l, (ix + O_SCRIPT + SC_VARS + 4)
        ld  h, (ix + O_SCRIPT + SC_VARS + 5)
        ld  (cb_2ref), hl
        call cb_2ref_unit
        jr  z, cb_2bf_search
        push hl
        pop iy
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jr  z, cb_2bf_search
        call cb_2dist_iy        ; HL = the distance
        push hl
        ld  a, (iy + O_TYPE)
        call unit_info
        ld  bc, UI_movementType
        add hl, bc
        ld  a, (hl)
        ld  de, (cb_2n16)
        cp  4
        jr  nz, cb_2bf1
        ld  de, (cb_2n3)
cb_2bf1:
        pop hl
        call cb_2scmp           ; d < n: keep it
        jr  nc, cb_2bf_search
        ld  hl, (cb_2ref)
        ret
cb_2bf_search:
        ld  hl, 0
        ld  (cb_2best), hl
        ld  hl, $7D00
        ld  (cb_2score), hl
        ld  a, (ix + O_HOUSE)
        call cb_2hbit
        ld  (cb_2t), a
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        ld  hl, unit_head
        call cb_2add_a
        ld  a, (hl)
cb_2bf_loop:
        cp  $FF
        jp  z, cb_2bf_done
        ld  (cb_2slot), a
        call unit_ptr
        push hl
        pop iy
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jr  z, cb_2bf_next
        call cb_2sq_iy
        call cb_2valid16
        jr  nc, cb_2bf_next
        ld  a, (cb_2t)
        and (iy + O_SEEN)
        jr  z, cb_2bf_unseen
        call cb_2dist_iy
        ld  de, (cb_2score)
        call cb_2scmp
        jr  nc, cb_2bf_next
        ld  de, (cb_2n16)
        call cb_2scmp
        jr  nc, cb_2bf_next
        ld  (cb_2score), hl
        ld  (cb_2best), iy
        jr  cb_2bf_next
cb_2bf_unseen:
        ld  a, (iy + O_TYPE)
        cp  UNIT_THOPTER
        jr  nz, cb_2bf_next
        call cb_2dist_iy
        ld  de, (cb_2score)
        call cb_2scmp
        jr  nc, cb_2bf_next
        ld  de, (cb_2n3)
        call cb_2scmp
        jr  nc, cb_2bf_next
        ld  (cb_2best), iy
        jr  cb_2bf_done
cb_2bf_next:
        ld  a, (cb_2slot)
        ld  hl, unit_lnext
        call cb_2add_a
        ld  a, (hl)
        jp  cb_2bf_loop
cb_2bf_done:
        ld  hl, (cb_2best)
        ld  a, h
        or  l
        jr  z, cb_2bf_none
        set 7, (ix + O_FLAGS2)
        ld  a, (hl)
        ld  l, a
        ld  h, REF_UNIT >> 8
        ret
cb_2bf_none:
        res 7, (ix + O_FLAGS2)
        ret

; BUILD 9 aim ($00CB92): turns the turret one eighth towards the
; reference, by rewriting its square's icon (the turret groups of
; ICON.MAP: 23 the Turret's, 24 the Rocket Turret's, eight facings from
; their third icon) and +$4E; +$0F = 30.  Answers 1 if it turned (or the
; square shows no turret icon), 0 if it already faces it.
ef_b_aim:
        xor a
        call emc_arg
        ld  a, h
        or  l
        jp  z, cb_2zero
        ld  (cb_2ref), hl
        call cb_2obj
        ld  (ix + S_TURRETFACING), 30
        ld  hl, (cb_2ref)
        call ref_square
        ld  (cb_2tsq), hl
        call cb_2sq
        ld  (cb_2ssq), hl
        call cb_2turret_base    ; DE = the first facing icon
        ld  hl, (cb_2ssq)
        push de
        call map_ground_icon
        pop de
        or  a
        sbc hl, de
        jp  c, cb_2one
        ld  a, h
        or  a
        jp  nz, cb_2one
        ld  a, l
        cp  8
        jp  nc, cb_2one
        ld  (cb_2t), a          ; d4, the facing now
        ld  (cb_2base), de
        ld  hl, (cb_2ssq)
        ld  de, cb_2p
        call square_centre
        ld  hl, (cb_2tsq)
        ld  de, cb_2q
        call square_centre
        ld  hl, cb_2p
        ld  de, cb_2q
        call tile_direction
        add a, $10
        rlca
        rlca
        rlca
        and 7                   ; d3
        ld  hl, cb_2t
        sub (hl)
        jp  z, cb_2zero         ; facing it already
cb_2ba1:
        cp  5                   ; into -4..4 (signed)
        jp  m, cb_2ba2
        sub 8
        jr  cb_2ba1
cb_2ba2:
        cp  -4
        jp  p, cb_2ba3
        add a, 8
        jr  cb_2ba2
cb_2ba3:
        or  a
        ld  a, (hl)
        jp  p, cb_2ba4
        dec a
        dec a
cb_2ba4:
        inc a
        and 7
        ld  (hl), a
        ld  (ix + S_ROTSPRITEDIFF), a
        ld  (ix + S_ROTSPRITEDIFF + 1), 0
        ld  hl, (cb_2base)
        ld  e, a
        ld  d, 0
        add hl, de              ; the new icon
        ex  de, hl
        ld  hl, (cb_2ssq)
        call map_addr
        ld  (hl), e
        ld  a, h
        add a, (MAP_HIGH - MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and $FE
        or  d
        ld  (hl), a
        jp  cb_2one

; IX = a turret -> DE = its group's first facing icon: ICON.MAP[ICON.MAP
; [23 or 24] + 2] (read out of bank STRUCT's copy, tbl_icon_map, through
; window 1).  Clobbers A, HL.
cb_2turret_base:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_RTURRET
        ld  e, 23 * 2
        jr  nz, cb_2tb1
        ld  e, 24 * 2
cb_2tb1:
        ld  a, $$tbl_icon_map
        call map_w1
        ld  d, 0
        ld  hl, tbl_icon_map + $4000
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc de
        inc de
        ex  de, hl
        add hl, hl
        ld  de, tbl_icon_map + $4000
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, PG_UNITS
        jp  map_w1

; BUILD 11 fire ($00CDD0): the argument is the range (S4).  A target that
; is out of range, not allocated, off the map or allied - unless it is an
; Ornithopter - is dropped.  A Rocket Turret fires a turret rocket (20)
; with 30 damage at anything 3 squares away or more and answers the
; Launcher's fireDelay + 30; closer, and a Turret always, a bullet (23)
; with 20 damage and a firing animation on its square (map_anim_start,
; script facing + $1B, or + $23 for a Rocket Turret) and the Tank's
; fireDelay.  The shot's origin is the structure and its linkedID 9.
ef_b_fire:
        xor a
        call emc_arg
        ld  (cb_2n16), hl
        call cb_2obj
        ld  l, (ix + O_SCRIPT + SC_VARS + 4)
        ld  h, (ix + O_SCRIPT + SC_VARS + 5)
        ld  (cb_2ref), hl
        ld  a, h
        or  l
        jp  z, cb_2zero
        call ref_square
        call cb_2valid16
        jp  nc, cb_2zero
        ld  hl, (cb_2ref)
        call cb_2ref_unit
        jr  z, cb_2bfi_ok
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        cp  UNIT_THOPTER
        jr  z, cb_2bfi_ok
        call cb_2dist_iy
        ld  de, (cb_2n16)
        call cb_2scmp           ; d >= range: dropped
        jr  nc, cb_2bfi_drop
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jr  z, cb_2bfi_drop
        bit OF_NOTONMAP, (iy + O_FLAGS)
        jr  nz, cb_2bfi_drop
        ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jr  z, cb_2bfi_ok
cb_2bfi_drop:
        xor a
        ld  (ix + O_SCRIPT + SC_VARS + 4), a
        ld  (ix + O_SCRIPT + SC_VARS + 5), a
        res 7, (ix + O_FLAGS2)
        jp  cb_2zero
cb_2bfi_ok:
        call cb_2sq
        ld  (cb_2ssq), hl
        ld  a, UNIT_BULLET
        ld  (cb_2t), a
        ld  c, $1B
        ld  a, (ix + O_TYPE)
        cp  STRUCT_RTURRET
        jr  nz, cb_2bfi_anim
        ld  a, UNIT_AROCKET
        ld  (cb_2t), a
        ld  hl, (cb_2ref)
        ld  de, cb_2p
        call ref_position
        call cb_2pos
        ld  de, cb_2p
        call tile_distance
        ld  de, $300
        call cb_2scmp
        jr  nc, cb_2bfi_shoot   ; 3 squares or more: the rocket
        ld  a, UNIT_BULLET
        ld  (cb_2t), a
        ld  c, $23
cb_2bfi_anim:
        push bc
        call cb_2turret_base
        ld  hl, (cb_2ssq)
        push de
        call map_ground_icon
        pop de
        or  a
        sbc hl, de
        pop bc
        ld  a, l
        add a, c                ; the firing animation for the facing
        ld  hl, (cb_2ssq)
        FCALL map_anim_start
cb_2bfi_shoot:
        call cb_2pos_arg
        ld  hl, arg_pos         ; from the middle of its square
        ld  a, (hl)
        add a, $80
        ld  (hl), a
        inc hl
        jr  nc, cb_2bs1
        inc (hl)
cb_2bs1:
        inc hl
        ld  a, (hl)
        add a, $80
        ld  (hl), a
        inc hl
        jr  nc, cb_2bs2
        inc (hl)
cb_2bs2:
        ld  a, (cb_2t)
        cp  UNIT_AROCKET
        jr  nz, cb_2bs3
        ld  a, UNIT_LAUNCHER
        call unit_info
        ld  de, UI_fireDelay
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 30
        add hl, de
        ld  (cb_2score), hl     ; the answer
        ld  hl, 30              ; the damage
        jr  cb_2bs4
cb_2bs3:
        ld  a, UNIT_TANK
        call unit_info
        ld  de, UI_fireDelay
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  (cb_2score), hl
        ld  hl, 20
cb_2bs4:
        ld  a, (cb_2t)
        ld  b, a
        ld  c, (ix + O_HOUSE)
        ld  de, (cb_2ref)
        ld  a, (ix + O_INDEX)
        ld  (cb_2slot), a
        FCALL unit_fire_projectile
        ld  a, h
        or  l
        jp  z, cb_2zero
        ld  de, O_LINKED
        add hl, de
        ld  (hl), 9
        ld  de, U_ORIGIN - O_LINKED
        add hl, de
        ld  a, (cb_2slot)
        ld  (hl), a
        inc hl
        ld  (hl), REF_STRUCT >> 8
        ld  hl, (cb_2score)
        ret

; ============================================================ the Deviator

; map_deviate_area ($00ADBE): arg_pos = where, A = the house the units go
; to (the deviator rocket's) (S4).  Effect 57 and animation 7; every unit
; of the other side's list within 2 squares (tile_distance >> 4 < 32) is
; unit_deviate'd.  The cartridge reads the house of the list from what a2
; held (the rocket); the port takes it from A (S4: fix).
map_deviate_area:
        ld  (cb_2t), a
        ld  hl, arg_pos
        ld  de, cb_2p
        ld  bc, 4
        ldir
        ld  a, 57
        FCALL snd_effect
        ld  a, 7
        ld  c, 3
        FCALL fx_explosion_start
        ld  a, (cb_2t)
        ld  b, a
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        ld  hl, unit_head
        call cb_2add_a
        ld  a, (hl)
cb_2da1:
        cp  $FF
        ret z
        push ix
        ld  c, a
        ld  hl, unit_lnext      ; the next one first: deviating relinks
        call cb_2add_a
        ld  a, (hl)
        ld  (cb_2slot), a
        ld  a, c
        call unit_ptr
        push hl
        pop ix
        ld  hl, cb_2p
        call cb_2pos_de
        call tile_distance
        ld  de, 32 * 16
        call cb_2scmp
        jr  nc, cb_2da2
        ld  a, (cb_2t)
        call unit_deviate
cb_2da2:
        pop ix
        ld  a, (cb_2slot)
        jr  cb_2da1

; unit_deviate ($047882): IX = the unit, A = the house it goes to -> A =
; 1 if it changed (S4).  Only a normal unit, not deviated, not
; isNotDeviatable, not Fremen (Mega Drive), and with random & 255 below
; its house's toughness (an eighth less unless it is the player's).  Its
; house, counts, list, sight and order change (the order by the player's
; house being Ordos: kept, S4), deviated = 120, and every reference to it
; is dropped.
unit_deviate:
        ld  (cb_2h), a
        call cb_2uinfo
        bit 15 - 8, (iy + UI_flags + 1)
        jp  z, cb_2dv_no
        ld  a, (ix + U_DEVIATED)
        or  a
        jp  nz, cb_2dv_no
        bit 12 - 8, (iy + UI_flags + 1)
        jp  nz, cb_2dv_no
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_FREMEN
        jp  z, cb_2dv_no
        call house_info
        ld  de, HI_toughness
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, cb_2dv1
        ld  h, d
        ld  l, e
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ex  de, hl
        or  a
        sbc hl, de
        ex  de, hl
cb_2dv1:
        call random
        ld  l, a
        ld  h, 0
        call cb_2scmp           ; random < chance: deviated
        jp  nc, cb_2dv_no
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        FCALL unit_type_count_addr
        dec (hl)
        ld  a, (ix + O_INDEX)
        FCALL unit_list_unlink
        ld  a, (cb_2h)
        ld  (ix + O_HOUSE), a
        ld  a, (ix + O_INDEX)
        FCALL unit_list_link
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        FCALL unit_type_count_addr
        inc (hl)
        ld  (ix + U_DEVIATED), 120
        ld  a, 2
        FCALL unit_update_map
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, cb_2dv2
        ld  a, (ix + O_HOUSE)
        call cb_2hbit
cb_2dv2:
        ld  (ix + O_SEEN), a
        call cb_2sq
        call cb_2mflags
        bit MF_UNVEILED, a
        jr  z, cb_2dv3
        ld  a, (player_house)
        FCALL unit_seen_by_house
cb_2dv3:
        call cb_2uinfo
        ld  a, (player_house)
        cp  HOUSE_ORDOS
        ld  a, (iy + UI_actionPlayer)
        jr  z, cb_2dv4
        ld  a, (iy + UI_actionAI)
cb_2dv4:
        FCALL unit_give_order
        FCALL unit_drop_references
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_2dv5
        xor a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
cb_2dv5:
        xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, 1
        ret
cb_2dv_no:
        xor a
        ret

; ============================================================== the Palace

; struct_activate_special ($022CC4): IX = the Palace -> A = 1 if it
; launched or armed something (S4).  By the house's specialWeapon:
;   1 Death Hand: a missile (18) made off the map as house_missile; the
;     player gets the 7-step countdown (the target cursor is the UI's), a
;     computer house launches at once at the first structure not allied
;     with it (none: the missile is freed).  specialDelay 300.
;   2 Fremen: a random location of kind 4 off the screen; $095CD8[the
;     Fremen troopers alive] of them, of $095CD0[random 0-3], house 3,
;     within 30, double hit points; with a target square, Attack what is
;     on it or Move there.  specialDelay 180.
;   3 Saboteur: the linked one or a new one on a free square next to the
;     Palace, Sabotage, aimed at the target square; no free square: the
;     countdown is 1 and it tries again.  specialDelay 240.
; Each resets countDown (+$56) to the house's specialCountDown.
struct_activate_special:
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        ld  a, (hl)
        ld  c, 0
        bit HF_HUMAN, a
        jr  z, cb_2sa0
        inc c
cb_2sa0:
        ld  a, c
        ld  (cb_2human), a
        or  a
        jr  nz, cb_2sa1
        bit HF_USED, (hl)
        jp  z, cb_2sa_no
cb_2sa1:
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_specialWeapon
        add hl, de
        ld  a, (hl)
        cp  1
        jr  z, cb_2sa_hand
        cp  2
        jp  z, cb_2sa_fremen
        cp  3
        jp  z, cb_2sa_sab
cb_2sa_no:
        xor a
        ret
cb_2sa_hand:
        ld  hl, validate_strict
        inc (hl)
        ld  hl, $FFFF
        ld  (arg_pos), hl
        ld  (arg_pos + 2), hl
        call random
        ld  d, a
        ld  b, UNIT_DEATHHAND
        ld  c, (ix + O_HOUSE)
        ld  a, $FF
        push ix
        FCALL unit_spawn
        pop ix
        ld  (house_missile), hl
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        jr  z, cb_2sa_no
        ld  hl, 300
        call cb_2countdown
        ld  a, (cb_2human)
        or  a
        jr  z, cb_2sa_h1
        ld  hl, 7
        ld  (house_missile_count), hl
        ld  a, 1
        ret
cb_2sa_h1:                      ; a computer house: at the first enemy structure
        ld  b, 0
cb_2sa_h2:
        ld  a, (struct_find_count)
        cp  b
        jr  z, cb_2sa_h4
        jr  c, cb_2sa_h4
        ld  e, b
        ld  d, 0
        inc b
        ld  hl, struct_find
        add hl, de
        ld  a, (hl)
        push bc
        call struct_ptr
        push hl
        pop iy
        pop bc
        bit OF_NOTONMAP, (iy + O_FLAGS)
        jr  z, cb_2sa_h3
        ld  a, (validate_strict)
        or  a
        jr  z, cb_2sa_h2
cb_2sa_h3:
        push bc
        ld  b, (iy + O_HOUSE)
        ld  c, (ix + O_HOUSE)
        call house_are_allied
        pop bc
        or  a
        jr  nz, cb_2sa_h2
        call cb_2sq_iy
        call unit_launch_house_missile
        ld  a, 1
        ret
cb_2sa_h4:
        push ix
        ld  ix, (house_missile)
        FCALL unit_free
        pop ix
        ld  hl, 0
        ld  (house_missile), hl
        ld  a, 1
        ret
cb_2sa_fremen:
        ; a location of kind 4, row from one call, column from another,
        ; until it is off the screen
        ld  a, 4
        FCALL map_find_location
        ld  (cb_2tsq), hl
        ld  a, 4
        FCALL map_find_location
        add hl, hl
        add hl, hl
        ld  a, h                ; the row (bits 6-11 of the second)
        and $3F
        ld  (cb_2p + 1), a
        ld  a, $80
        ld  (cb_2p), a
        ld  (cb_2p + 2), a
        ld  a, (cb_2tsq)
        and $3F
        ld  (cb_2p + 3), a
        call cb_2on_screen
        jr  c, cb_2sa_fremen
        ld  b, HOUSE_FREMEN
        ld  a, UNIT_TROOPERS
        FCALL unit_type_count_addr
        ld  c, (hl)
        ld  b, HOUSE_FREMEN
        ld  a, UNIT_TROOPER
        FCALL unit_type_count_addr
        ld  a, (hl)
        add a, c
        and $0F                 ; (the table has 16 entries)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_fremen_count
        add hl, de
        ld  a, (hl)
        ld  (cb_2n), a
cb_2sf1:
        ld  a, (cb_2n)
        or  a
        jp  z, cb_2sf_done
        dec a
        ld  (cb_2n), a
        ld  hl, validate_strict
        inc (hl)
        call random
        ld  (cb_2dir), a
        ld  hl, cb_2p
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  hl, arg_pos
        ld  de, 30
        ld  a, 1
        FCALL cb_tile_move_by_random
        ld  de, 3               ; rand_between(0, 3)
        call rand_between
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_fremen_types
        add hl, de
        ld  b, (hl)
        ld  c, HOUSE_FREMEN
        ld  a, (cb_2dir)
        ld  d, a
        ld  a, $FF
        push ix
        FCALL unit_spawn
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        jr  z, cb_2sf2
        push hl
        pop ix
        ld  l, (ix + O_HP)      ; double hit points
        ld  h, (ix + O_HP + 1)
        add hl, hl
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ld  hl, (special_target_square)
        ld  a, h
        or  l
        jr  z, cb_2sf2
        call cb_2mflags
        bit MF_UNIT, a
        jr  nz, cb_2sf_obj
        bit MF_STRUCT, a
        jr  nz, cb_2sf_obj
        ; an empty square: Move there (the cartridge's flag test always
        ; passes and aims at index - 1 of nothing: S4 says Move, the port
        ; does that)
        ld  a, ORDER_MOVE
        FCALL unit_give_order
        ld  hl, (special_target_square)
        call ref_make_square
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  (ix + U_ROUTE), $FF
        jr  cb_2sf2
cb_2sf_obj:
        push af
        xor a                   ; Attack what is on it
        FCALL unit_give_order
        pop af
        ld  hl, (special_target_square)
        call cb_2mindex
        dec a
        ld  l, a
        ld  h, REF_UNIT >> 8
        ld  a, (cb_2mf)
        bit MF_UNIT, a
        jr  nz, cb_2sf3
        ld  h, REF_STRUCT >> 8
cb_2sf3:
        FCALL unit_set_target
cb_2sf2:
        pop ix
        jp  cb_2sf1
cb_2sf_done:
        ld  hl, 180
        call cb_2countdown
        ld  a, 1
        ret
cb_2sa_sab:
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, cb_2ss1
        ld  hl, validate_strict
        inc (hl)
        ld  hl, $FFFF
        ld  (arg_pos), hl
        ld  (arg_pos + 2), hl
        call random
        ld  d, a
        ld  b, UNIT_SABOTEUR
        ld  c, (ix + O_HOUSE)
        ld  a, $FF
        push ix
        FCALL unit_spawn
        pop ix
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        jr  cb_2ss2
cb_2ss1:
        call unit_ptr
cb_2ss2:
        ld  a, h
        or  l
        jp  z, cb_2sa_no
        push hl
        pop iy
        ld  a, (iy + O_INDEX)
        ld  (ix + O_LINKED), a
        push iy
        ld  iy, 0               ; (the cartridge passes no unit)
        FCALL struct_find_free_square
        pop iy
        ld  a, h
        or  l
        jr  z, cb_2ss_none
        ld  a, h
        and l
        inc a
        jr  z, cb_2ss_none
        ld  (cb_2tsq), hl
        ld  (ix + O_LINKED), $FF
        ld  hl, 240
        call cb_2countdown
        push ix
        push iy
        pop ix
        ld  hl, (cb_2tsq)
        call cb_unit_place
        ld  a, ORDER_SABOTAGE
        FCALL unit_give_order
        ld  hl, (special_target_square)
        call ref_make_square
        FCALL unit_set_target
        pop ix
        ld  a, 1
        ret
cb_2ss_none:
        ld  (ix + S_COUNTDOWN), 1
        ld  (ix + S_COUNTDOWN + 1), 0
        xor a
        ret

; HL = the specialDelay: countDown = the house's specialCountDown.
cb_2countdown:
        ld  (ix + S_ROTSPRITEDIFF), l
        ld  (ix + S_ROTSPRITEDIFF + 1), h
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_specialCountDown
        add hl, de
        ld  a, (hl)
        ld  (ix + S_COUNTDOWN), a
        inc hl
        ld  a, (hl)
        ld  (ix + S_COUNTDOWN + 1), a
        ret

; view_square_visible ($005DE6): cb_2p = a position -> carry if its
; square is on the screen with a one-square margin: row within (view row
; - 1, view row + 8), column within (view column - 1, view column + 11),
; exclusive, the view's first square being view_y / 32, view_x / 32.
cb_2on_screen:
        ld  hl, (view_y)
        call cb_2div32
        ld  a, (cb_2p + 1)
        ld  c, 8
        call cb_2in_range
        ret nc
        ld  hl, (view_x)
        call cb_2div32
        ld  a, (cb_2p + 3)
        ld  c, 11
; A = the row or column v, HL = the view's first, C = the span -> carry
; if first - 1 < v < first + span.
cb_2in_range:
        ld  e, a
        ld  d, 0
        dec hl
        ex  de, hl              ; HL = v, DE = first - 1
        call cb_2scmp
        jr  c, cb_2ir_no
        jr  z, cb_2ir_no
        inc de
        ld  a, c
        add a, e
        ld  e, a
        jr  nc, cb_2ir1
        inc d
cb_2ir1:
        jp  cb_2scmp            ; v < first + span
cb_2ir_no:
        or  a
        ret
cb_2div32:
        ld  a, l
        srl h
        rra
        srl h
        rra
        srl h
        rra
        srl h
        rra
        srl h
        rra
        ld  l, a
        ret

; unit_launch_house_missile ($02313A): HL = the square aimed at (S4).
; The aim is scattered by up to 160; the placeholder is freed and a real
; Death Hand fired from the house's palacePosition (+$22) with 500
; damage; effect 27 for a computer's launch; house_missile and the
; countdown cleared (the player's cursor going back is the UI's).
unit_launch_house_missile:
        ld  de, (house_missile)
        ld  a, d
        or  e
        ret z
        push ix
        ld  de, arg_pos         ; in WORLD: cb_tile_move_by_random is
        call square_centre      ; COMBAT's, and a COMBAT2 address handed
        ld  hl, arg_pos         ; across the FCALL would read COMBAT's page
        ld  de, 160
        xor a
        FCALL cb_tile_move_by_random
        ld  hl, arg_pos
        call pos_square
        call ref_make_square
        ld  (cb_2ref), hl
        ld  ix, (house_missile)
        ld  a, (ix + O_HOUSE)
        ld  (cb_2h), a
        ld  a, (ix + O_TYPE)
        ld  (cb_2t), a
        FCALL unit_free
        ld  a, (cb_2h)
        call house_ptr
        ld  de, H_PALACE_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  a, (cb_2t)
        ld  b, a
        ld  a, (cb_2h)
        ld  c, a
        ld  hl, 500
        ld  de, (cb_2ref)
        FCALL unit_fire_projectile
        ld  a, (player_house)
        ld  hl, cb_2h
        cp  (hl)
        jr  z, cb_2lm1
        ld  a, 27
        FCALL snd_effect
cb_2lm1:
        ld  hl, 0
        ld  (house_missile_count), hl
        ld  (house_missile), hl
        pop ix
        ret

; ======================================== other specs' pieces combat needs

; unit_deactivate_player ($049136): IX = a unit.  One of the player's
; that is allocated stops being so and leaves its team.  (Cancelling the
; player's command when it was the selected unit is the UI's.)  Keeps IX.
cb_deactivate_player:
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        bit OF_ALLOCATED, (ix + O_FLAGS)
        ret z
        res OF_ALLOCATED, (ix + O_FLAGS)
        ; team_remove_unit $02E406
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

; map_spice_fill_circle ($01ACC4, S5): HL = the centre square, A = the
; radius (0: nothing).  Every square of the box within the radius
; (tile_distance_packed) that is not spice gets spice (map_change_spice
; +1, STRUCT) - one exactly at the radius only on a random bit - and then
; the centre.  Keeps IX.
cb_spice_fill_circle:
        or  a
        ret z
        ld  (cb_2r), a
        ld  (cb_2tsq), hl
        neg
        ld  (cb_2dy), a
cb_2sc1:
        ld  a, (cb_2r)
        neg
        ld  (cb_2dx), a
cb_2sc2:
        ; the square: (row + dy) * 64 + column + dx, as the 68000 adds it
        ld  hl, (cb_2tsq)
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  l, a
        ld  a, (cb_2dy)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        ld  h, 0
        add hl, de
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (cb_2tsq)
        and $3F
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, (cb_2dx)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (cb_2ssq), hl
        ex  de, hl
        ld  hl, (cb_2tsq)
        call tile_distance_packed
        ld  a, (cb_2r)
        cp  l
        jr  z, cb_2sc_edge
        jr  c, cb_2sc_next      ; outside
        jr  cb_2sc_in
cb_2sc_edge:
        call random
        rra
        jr  nc, cb_2sc_next
cb_2sc_in:
        ld  hl, (cb_2ssq)
        call map_landscape
        cp  LST_SPICE
        jr  z, cb_2sc_next
        ld  hl, (cb_2ssq)
        ld  a, 1
        FCALL map_change_spice
cb_2sc_next:
        ld  hl, cb_2dx
        inc (hl)
        ld  a, (cb_2r)
        sub (hl)
        jp  p, cb_2sc2
        ld  hl, cb_2dy
        inc (hl)
        ld  a, (cb_2r)
        sub (hl)
        jp  p, cb_2sc1
        ld  hl, (cb_2tsq)
        ld  a, 1
        FCALL map_change_spice
        ret

; struct_free_refs ($010CDC): IX = a structure going.  Its claim broken,
; and every unit's claim on it, targetAttack and targetMove naming it,
; and every team's target naming it, cleared.  Keeps IX.
cb_struct_free_refs:
        ld  a, (ix + O_INDEX)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        ld  (cb_2ref), hl
        FCALL obj_var4_clear
        push ix
        ld  b, 0
cb_2fr1:
        call cb_2unext
        jr  z, cb_2fr4
        push bc
        push hl
        pop ix
        ld  de, (cb_2ref)
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)    ; variable 4: the claim
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        or  a
        sbc hl, de
        jr  nz, cb_2fr2
        FCALL obj_var4_clear
        ld  de, (cb_2ref)
cb_2fr2:
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        or  a
        sbc hl, de
        jr  nz, cb_2fr3
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
cb_2fr3:
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        or  a
        sbc hl, de
        jr  nz, cb_2fr3a
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
cb_2fr3a:
        pop bc
        jr  cb_2fr1
cb_2fr4:
        pop ix
        ld  a, (team_find_count)
        or  a
        ret z
        ld  b, a
        ld  hl, team_find
cb_2fr5:
        push bc
        push hl
        ld  a, (hl)
        call team_ptr
        ld  de, T_TARGET
        add hl, de
        ld  de, (cb_2ref)
        ld  a, (hl)
        cp  e
        jr  nz, cb_2fr6
        inc hl
        ld  a, (hl)
        cp  d
        jr  nz, cb_2fr6
        ld  (hl), 0
        dec hl
        ld  (hl), 0
cb_2fr6:
        pop hl
        inc hl
        pop bc
        djnz cb_2fr5
        ret

; unit_place ($048534), as the Palace's Saboteur needs it: IX = a unit
; off the map, HL = a square.  Put in the middle of the square with no
; step, a home if it has none, no claim; if it cannot stand there it
; stays off the map (A = 0).  Otherwise no destination, target or move
; target (a Harvester keeps its target), seen if the square is unveiled,
; its default order, on the map (A = 1).  Keeps IX.
cb_unit_place:
        push ix
        pop de
        ex  de, hl
        push de
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        call square_centre
        res OF_NOTONMAP, (ix + O_FLAGS)
        xor a
        ld  (ix + U_STEP_X), a
        ld  (ix + U_STEP_X + 1), a
        ld  (ix + U_STEP_Y), a
        ld  (ix + U_STEP_Y + 1), a
        ld  a, (ix + U_ORIGIN)
        or  (ix + U_ORIGIN + 1)
        jr  nz, cb_2up1
        FCALL unit_choose_home
cb_2up1:
        xor a
        ld  (ix + O_SCRIPT + SC_VARS + 8), a
        ld  (ix + O_SCRIPT + SC_VARS + 9), a
        FCALL unit_blocked_here
        or  a
        jr  z, cb_2up2
        set OF_NOTONMAP, (ix + O_FLAGS)
        xor a
        ret
cb_2up2:
        xor a
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_2up3
        xor a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
cb_2up3:
        call cb_2sq
        call cb_2mflags
        bit MF_UNVEILED, a
        jr  z, cb_2up4
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, cb_2up3a
        ld  a, (ix + O_HOUSE)
        call cb_2hbit
cb_2up3a:
        ld  (ix + O_SEEN), a
        ld  a, (player_house)
        FCALL unit_seen_by_house
cb_2up4:
        call cb_2uinfo
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, cb_2up5
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, cb_2up5
        cp  UNIT_SABOTEUR
        jr  z, cb_2up5
        ld  a, (iy + UI_actionPlayer)
        jr  cb_2up6
cb_2up5:
        ld  a, (iy + UI_actionAI)
cb_2up6:
        FCALL unit_give_order
        ld  (ix + U_SPRITEOFS), 0
        ld  a, 1
        FCALL unit_update_map
        res 1, (ix + O_FLAGS2 + 1)
        ld  a, 1
        ret

; ================================================================ helpers

cb_2obj:
        ld  de, -O_SCRIPT
        add ix, de
        ret
cb_2uinfo:
        ld  a, (ix + O_TYPE)
        call unit_info
        push hl
        pop iy
        ret
cb_2pos:
        push de
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        pop de
        ret
cb_2pos_de:
        push hl
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        ret
cb_2pos_arg:
        push af
        call cb_2pos
        ld  de, arg_pos
        ld  bc, 4
        ldir
        pop af
        ret
cb_2sq:
        call cb_2pos
        jp  pos_square
cb_2sq_iy:
        push de
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        pop de
        jp  pos_square
; HL = the distance from IX to IY.  Clobbers A, BC, DE.
cb_2dist_iy:
        call cb_2pos
        ex  de, hl
        push iy
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        jp  tile_distance
cb_2valid16:
        ld  a, h
        cp  $10
        ret nc
        jp  map_valid
cb_2scmp:
        ld  a, h
        xor d
        jp  m, cb_2scmp_d
        push hl
        sbc hl, de
        pop hl
        ret
cb_2scmp_d:
        ld  a, h
        rla
        ret
cb_2hbit:
        push bc
        inc a
        ld  b, a
        ld  a, $80
cb_2hb1:
        rlca
        djnz cb_2hb1
        pop bc
        ret
; HL += A.
cb_2add_a:
        add a, l
        ld  l, a
        ret nc
        inc h
        ret
cb_2ref_unit:
        ld  a, h
        cp  REF_UNIT >> 8
        jr  nz, cb_2none
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, cb_2none
        call unit_ptr
        or  1
        ret
cb_2none:
        ld  hl, 0
        xor a
        ret
; ref_object ($02E352): HL = a reference -> HL = the unit (kind 1) or
; structure (kind 2), NZ; or Z.
cb_2ref_object:
        ld  a, h
        and $C0
        cp  REF_UNIT >> 8
        jr  z, cb_2ro_u
        cp  REF_STRUCT >> 8
        jr  nz, cb_2none
        ld  a, h
        and $3F
        jr  nz, cb_2none
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, cb_2none
        call struct_ptr
        or  1
        ret
cb_2ro_u:
        ld  a, h
        and $3F
        jr  nz, cb_2none
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, cb_2none
        call unit_ptr
        or  1
        ret
cb_2mflags:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        ld  (cb_2mf), a
        pop hl
        ret
cb_2mindex:
        push hl
        ld  a, h
        and $0F
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret
; B = a position in the find array -> HL = the next unit a search for any
; house and type finds (not isNotOnMap unless validate_strict), B after
; it, NZ; or Z.  Clobbers A, DE.
cb_2unext:
        ld  a, (unit_find_count)
        cp  b
        jr  z, cb_2un_end
        jr  c, cb_2un_end
        ld  e, b
        ld  d, 0
        inc b
        ld  hl, unit_find
        add hl, de
        ld  a, (hl)
        call unit_ptr
        push hl
        inc hl
        inc hl
        inc hl
        inc hl
        bit OF_NOTONMAP, (hl)
        pop hl
        jr  z, cb_2un_ok
        ld  a, (validate_strict)
        or  a
        jr  z, cb_2unext
cb_2un_ok:
        or  1
        ret
cb_2un_end:
        xor a
        ret

; ---------------------------------------------------------- the statics
cb_2ref:        DW 0
cb_2dir:        DB 0
cb_2best:       DW 0
cb_2score:      DW 0
cb_2d6:         DW 0
cb_2dx:         DW 0
cb_2dy:         DB 0
cb_2n:          DB 0
cb_2n16:        DW 0
cb_2n3:         DW 0
cb_2t:          DB 0
cb_2h:          DB 0
cb_2r:          DB 0
cb_2mf:         DB 0
cb_2slot:       DB 0
cb_2human:      DB 0
cb_2tsq:        DW 0
cb_2ssq:        DW 0
cb_2base:       DW 0
cb_2p:          DS 4
cb_2q:          DS 4
