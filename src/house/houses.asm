; houses.asm - bank HOUSE: the house loop (S1), what a house sees and the
; computer player's waking (S7), the reinforcements and deliveries by
; Carryall and Frigate (S1, S5, S6, S9), and the Carryall's script routines.
; Owner: the HOUSE subsystem (see .claude/docs/port-code.md).  The teams,
; map_find_location and the end of a mission are in houses2.asm (HOUSE2).
;
; Comments say what the cartridge does; addresses are its 68000 code in
; orig/sega/src/.  Where the port departs from it, it is a "port" row of
; a spec's bug table and says so.
;
; Routines and variables of other subsystems that are not in their
; interfaces are used only if they exist (IF EXIST; every other logic bank
; is assembled before this one in dune.asm, so the answer is the same in
; every pass):
;   unit_launch_house_missile  HL = the square       (COMBAT, $02313A)
;   house_power_to_health      A = the house         (STRUCT, $010594)
;   struct_set_state           IX = it, A = the state (STRUCT, $00FA0E)
;   unit_set_destination       IX = the unit, HL = a reference (MOVE,
;                              $047D18; else hs_set_destination's own copy)
;   map_find_spice             HL = the square, A = the radius,
;                              C = the unit's slot -> HL = a square or 0
;                                                    (STRUCT, $01A146)
;   starport_index             a WORLD byte, the Starport slot ($FFC17C)
;   starport_cargo_pending     a WORLD word ($FFC348)
; unit_place ($048534), obj_var4_link ($023CCC), unit_take_off_map
; ($04869C), unit_exists ($0432D2) and view_square_visible ($005DE6) are
; this bank's own copies (hs_*), as no interface has them.

HS_VAR4            EQU O_SCRIPT + SC_VARS + 8      ; script variable 4, +$2A

; ============================================================ the house loop

; game_loop_house ($02375C): the houses (S1).  Seven timers, then the
; Starport's restock, the house missile, the reinforcements, and each
; house's own work.  Keeps IX, IY.
game_loop_house:
        push ix
        push iy
        call hs_clock
        xor a
        ld  (hs_gl_house), a
        ld  (hs_gl_power), a
        ld  (hs_gl_starport), a
        ld  (hs_gl_reinf), a
        ld  (hs_gl_missile), a
        ; tickHouseHouse, 900 ($023770)
        ld  hl, tick_house_house
        call hs_due
        jr  c, hs_glh_1
        ld  a, 1
        ld  (hs_gl_house), a
        ld  de, 900
        call hs_set_due
hs_glh_1:
        ; tickHousePowerMaintenance, 10800: not before
        ; tickPowerMaintenanceStart, and only once the clock is past the
        ; due time ($02378C, bls).  The start is game_prepare's load + 70
        ; ($02683E); the load's clock is missionStartTime.
        ld  hl, mission_start_time
        ld  de, hs_gl_tmp
        ld  bc, 4
        ldir
        ld  hl, hs_gl_tmp
        ld  de, 70
        call hs_add32_de
        ld  hl, hs_now
        ld  de, hs_gl_tmp
        call hs_cp32               ; C: now < start
        jr  c, hs_glh_2
        ld  hl, tick_house_power
        ld  de, hs_now
        call hs_cp32               ; C: due < now
        jr  nc, hs_glh_2
        ld  a, 1
        ld  (hs_gl_power), a
        ld  hl, tick_house_power
        ld  de, 10800
        call hs_set_due
hs_glh_2:
        ; tickHouseStarport, 60 (the PC's 180)
        ld  hl, tick_house_starport
        call hs_due
        jr  c, hs_glh_3
        ld  a, 1
        ld  (hs_gl_starport), a
        ld  de, 60
        call hs_set_due
hs_glh_3:
        ; tickHouseReinforcement, 600
        ld  hl, tick_house_reinf
        call hs_due
        jr  c, hs_glh_4
        ld  a, 1
        ld  (hs_gl_reinf), a
        ld  de, 600
        call hs_set_due
hs_glh_4:
        ; tickHouseUnused, 5: set, never read ($0237EC)
        ld  hl, tick_house_unused
        call hs_due
        jr  c, hs_glh_5
        ld  de, 5
        call hs_set_due
hs_glh_5:
        ; tickHouseMissileCountdown, 60
        ld  hl, tick_house_missile
        call hs_due
        jr  c, hs_glh_6
        ld  a, 1
        ld  (hs_gl_missile), a
        ld  de, 60
        call hs_set_due
hs_glh_6:
        ; tickHouseStarportAvailability, 1800 ($02381E): a random type's
        ; stock goes up by one if it is 0-9.  -1 (never sold) stays; the PC
        ; skipped 0 and turned -1 into 1.
        ld  hl, tick_house_avail
        call hs_due
        jr  c, hs_glh_7
        ld  de, $001A           ; rand(0, 26)
        call rand_between
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, starport_available
        add hl, de
        inc hl
        ld  a, (hl)             ; the high byte
        dec hl
        or  a
        jr  nz, hs_glh_6a          ; negative, or over 255
        ld  a, (hl)
        cp  10
        jr  nc, hs_glh_6a
        inc (hl)
hs_glh_6a:
        ld  hl, tick_house_avail
        ld  de, 1800
        call hs_set_due
hs_glh_7:
        ; the missile countdown ($023878): at 0 the house missile is
        ; launched at a random square ("air", kind 4) of the player's
        ld  a, (hs_gl_missile)
        or  a
        jr  z, hs_glh_8
        ld  hl, (house_missile_count)
        ld  a, h
        or  l
        jr  z, hs_glh_8
        dec hl
        ld  (house_missile_count), hl
        ld  a, h
        or  l
        jr  nz, hs_glh_8
        ld  a, (player_house)
        ld  b, a
        ld  a, 4
        FCALL map_find_location
    IF EXIST unit_launch_house_missile
        FCALL unit_launch_house_missile
    ENDIF
hs_glh_8:
        ; the reinforcements
        ld  a, (hs_gl_reinf)
        or  a
        call nz, hs_reinforcements
        ; every house in use, in the find array's order ($023ABA)
        xor a
        ld  (hs_gl_i), a
hs_glh_h:
        ld  a, (house_find_count)
        ld  b, a
        ld  a, (hs_gl_i)
        cp  b
        jr  nc, hs_glh_end
        ld  e, a
        ld  d, 0
        ld  hl, house_find
        add hl, de
        ld  a, (hl)
        call hs_house_pass
        ld  hl, hs_gl_i
        inc (hl)
        jr  hs_glh_h
hs_glh_end:
        ; Mega Drive only ($023CA6): a player below 1000 credits may hold
        ; 1000 without storage
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        ld  de, hs_gl_1000
        call hs_cp32               ; C: credits < 1000
        jr  nc, hs_glh_x
        ld  hl, 1000
        ld  (credits_no_silo), hl
        ld  hl, 0
        ld  (credits_no_silo + 2), hl
hs_glh_x:
        pop iy
        pop ix
        ret

; One house's pass ($023ACC): A = the house.  The credit cap first (the
; cartridge caps whichever house the last loop left in scriptCurrentHouse,
; before this loop, $023A74; S1 port: each house in its own loop).
hs_house_pass:
        ld  (hs_gl_h), a
        call house_ptr
        push hl
        pop iy                  ; IY = the house
        call hs_credit_cap
        ; tickHouseHouse: playerCreditsNoSilo drops to 0 once the storage
        ; is above it; make sure there is a Harvester
        ld  a, (hs_gl_house)
        or  a
        jr  z, hs_hp_1
        ld  a, (hs_gl_h)
        ld  hl, player_house
        cp  (hl)
        jr  nz, hs_hp_0
        push iy
        pop hl
        ld  de, H_STORAGE
        add hl, de
        ex  de, hl
        ld  hl, credits_no_silo
        call hs_cp32               ; C: noSilo < storage
        jr  nc, hs_hp_0
        ld  hl, 0
        ld  (credits_no_silo), hl
        ld  (credits_no_silo + 2), hl
hs_hp_0:
        ld  a, (hs_gl_h)
        push iy
        call house_ensure_harvester
        pop iy
hs_hp_1:
        ; tickHouseStarport: the Frigate's countdown (S6)
        ld  a, (iy + H_STARPORTLINK)
        and (iy + H_STARPORTLINK + 1)
        inc a
        jr  z, hs_hp_2             ; $FFFF: nothing ordered
        ld  a, (hs_gl_starport)
        or  a
        jr  z, hs_hp_2
    IF EXIST struct_starport_tick
        ld  a, (hs_gl_h)        ; STRUCT's copy of the same ($023AFC)
        push iy
        FCALL struct_starport_tick
        pop iy
    ELSE
        call hs_starport_tick
    ENDIF
hs_hp_2:
        ; tickHouseHouse: power, the warning timers, one harvester owed
        ld  a, (hs_gl_house)
        or  a
        jr  z, hs_hp_3
        ld  a, (hs_gl_h)
        push iy
        FCALL house_calc_power
    IF EXIST house_power_to_health
        ld  a, (hs_gl_h)
        FCALL house_power_to_health
    ENDIF
        pop iy
        push iy
        pop hl
        ld  de, H_TIMERUNIT
        add hl, de
        ld  b, 3                ; +$28, +$2A, +$2C: down by one to 0
hs_hp_t:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, d
        or  e
        jr  z, hs_hp_t1
        dec de
        ld  (hl), d
        dec hl
        ld  (hl), e
        inc hl
hs_hp_t1:
        inc hl
        djnz hs_hp_t
        ld  a, (iy + H_HARVINCOMING)
        or  (iy + H_HARVINCOMING + 1)
        jr  z, hs_hp_3
        ld  a, (hs_gl_h)
        ld  b, a
        ld  a, UNIT_HARVESTER
        ld  hl, 0
        push iy
        call unit_deliver
        pop iy
        jr  z, hs_hp_3
        ld  l, (iy + H_HARVINCOMING)
        ld  h, (iy + H_HARVINCOMING + 1)
        dec hl
        ld  (iy + H_HARVINCOMING), l
        ld  (iy + H_HARVINCOMING + 1), h
hs_hp_3:
        ; tickHousePowerMaintenance: powerUsage / 32 + 1, at most what the
        ; house has ($023C64)
        ld  a, (hs_gl_power)
        or  a
        ret z
        ld  l, (iy + H_POWERUSE)
        ld  h, (iy + H_POWERUSE + 1)
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l                   ; asr.w #5
        ld  a, h
        rla
        sbc a, a                ; ext.l
        inc hl
        ld  (hs_gl_tmp), hl
        ld  (hs_gl_tmp + 2), a
        ld  (hs_gl_tmp + 3), a
        ld  a, h
        or  l
        jr  nz, hs_hp_4
        ld  hl, hs_gl_tmp + 2      ; the carry of +1 into the high word
        inc (hl)
        inc hl
        jr  nz, hs_hp_4
        inc (hl)
hs_hp_4:
        push iy
        pop hl
        ld  de, H_CREDITS
        add hl, de              ; HL -> the credits
        ld  de, hs_gl_tmp
        ex  de, hl
        call hs_cp32               ; C: cost < credits
        ex  de, hl              ; HL -> the credits
        jr  c, hs_hp_5
        push hl                 ; the cost is all the house has
        ld  de, hs_gl_tmp
        ld  bc, 4
        ldir
        pop hl
hs_hp_5:
        ; credits -= cost
        ld  de, hs_gl_tmp
        jp  hs_sub32

; The credit cap (S1 step 4): IY = the house.  A computer house is cut to
; its storage; the player to max(storage, playerCreditsNoSilo).
hs_credit_cap:
        push iy
        pop hl
        ld  de, H_STORAGE
        add hl, de
        ld  de, hs_gl_tmp
        ld  bc, 4
        ldir                    ; the limit: the storage
        ld  a, (hs_gl_h)
        ld  hl, player_house
        cp  (hl)
        jr  nz, hs_cc_1
        ld  hl, hs_gl_tmp
        ld  de, credits_no_silo
        call hs_cp32               ; C: storage < noSilo
        jr  nc, hs_cc_1
        ld  hl, credits_no_silo
        ld  de, hs_gl_tmp
        ld  bc, 4
        ldir
hs_cc_1:
        push iy
        pop hl
        ld  de, H_CREDITS
        add hl, de
        ld  de, hs_gl_tmp
        ex  de, hl
        call hs_cp32               ; C: limit < credits
        ret nc
        ld  bc, 4
        ldir                    ; credits = the limit
        ret

; tickHouseStarport ($023AFC): IY = the house.  starportTimeLeft counts
; down; at 0 a Frigate is made for the Starport the order was placed at
; (starportIndex, if it is still this house's) or else the first of the
; house's with nothing docked, and carries the order's chain.  The time is
; reset to the house's delivery time, or 1 if no Frigate could be made.
hs_starport_tick:
        ld  l, (iy + H_STARPORTTIME)
        ld  h, (iy + H_STARPORTTIME + 1)
        dec hl
        bit 7, h
        jr  nz, hs_st_0
        ld  a, h
        or  l
        jr  nz, hs_st_set
hs_st_0:
        ld  hl, 0
hs_st_set:
        ld  (iy + H_STARPORTTIME), l
        ld  (iy + H_STARPORTTIME + 1), h
        ld  a, h
        or  l
        ret nz
        ld  hl, 0
        ld  (hs_st_frigate), hl
    IF EXIST starport_index
        ld  a, (starport_index)
    ELSE
        ld  a, $FF
    ENDIF
        cp  STRUCT_COUNT
        jr  nc, hs_st_search
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        jr  z, hs_st_search
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  nz, hs_st_search
        ld  a, (ix + O_HOUSE)
        cp  (iy + H_INDEX)
        jr  nz, hs_st_search
        call hs_st_deliver
        jr  hs_st_made
hs_st_search:
        ; the first Starport of the house with nothing linked ($023B8A)
        ld  hl, hs_search2
        ld  b, (iy + H_INDEX)
        ld  c, STRUCT_STARPORT
        push iy
        FCALL struct_find_first
        pop iy
hs_st_l:
        jr  z, hs_st_made
        push hl
        pop ix
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, hs_st_n
        call hs_st_deliver
        jr  hs_st_made
hs_st_n:
        ld  hl, hs_search2
        push iy
        FCALL struct_find_next
        pop iy
        jr  hs_st_l
hs_st_made:
        ld  hl, (hs_st_frigate)
        ld  a, h
        or  l
        jr  z, hs_st_one
        ld  a, (iy + H_INDEX)
        call house_info
        ld  de, HI_starportDeliveryTime
        add hl, de
        ld  a, (hl)
        ld  (iy + H_STARPORTTIME), a
        inc hl
        ld  a, (hl)
        ld  (iy + H_STARPORTTIME + 1), a
        ret
hs_st_one:
        ld  (iy + H_STARPORTTIME), 1
        ld  (iy + H_STARPORTTIME + 1), 0
        ret

; IX = the Starport, IY = the house: a Frigate for it, carrying the chain.
hs_st_deliver:
        ld  l, (ix + O_INDEX)
        ld  h, REF_STRUCT >> 8
        ld  b, (iy + H_INDEX)
        ld  a, UNIT_FRIGATE
        push iy
        call unit_deliver
        pop iy
        ret z
        ld  (hs_st_frigate), hl
        push hl
        pop ix
        ld  a, (iy + H_STARPORTLINK)
        ld  (ix + O_LINKED), a
        ld  (iy + H_STARPORTLINK), $FF
        ld  (iy + H_STARPORTLINK + 1), $FF
        set OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        ret

; ------------------------------------------------------ the reinforcements

; The sixteen reinforcement records ($0238A6), on tickHouseReinforcement:
; unit (w; the byte $FF empty), where (w), time left (w), time between (w),
; repeat (w).  A record's time counts down; at 0 a Carryall is delivered
; to a place near the base and the unit goes into it.  One Carryall per
; pass serves every record of its house that comes due in the same pass
; ($02396E: a3 is kept across the records); one of another house has to
; wait for the next pass (time left 1).  A repeating record makes its next
; unit at once and starts counting again.
;
; S9/S8 port: the place is map_find_location of the record's own kind (6
; enemy base, 7 home base) for the unit's house, with the kinds told apart
; - the cartridge asks kind 7 and reads both as "the player's side".  Every
; computer reinforcement in the 27 files is Enemybase and every player one
; Homebase, so they land where the cartridge lands them.
hs_reinforcements:
        ld  hl, 0
        ld  (hs_rf_carryall), hl
        ld  hl, reinforcements
        ld  (hs_rf_rec), hl
        xor a
        ld  (hs_rf_n), a
hs_rf_loop:
        ld  ix, (hs_rf_rec)
        ld  a, (ix + 0)
        cp  $FF
        jp  z, hs_rf_next          ; empty
        ld  a, (ix + 4)
        or  (ix + 5)
        jp  z, hs_rf_next          ; done with
        ld  l, (ix + 4)
        ld  h, (ix + 5)
        dec hl
        ld  (ix + 4), l
        ld  (ix + 5), h
        ld  a, h
        or  l
        jp  nz, hs_rf_next
        ld  a, (ix + 0)
        call unit_ptr
        ld  (hs_rf_unit), hl
        push hl
        pop iy                  ; IY = the unit
        ; before campaign 8 a Sardaukar reinforcement waits while the
        ; Sardaukar have 10 or more Troopers and Trooper ($023912)
        ld  a, (campaign_id)
        cp  8
        jr  nc, hs_rf_1
        ld  a, (iy + O_HOUSE)
        cp  HOUSE_SARDAUKAR
        jr  nz, hs_rf_1
        ld  a, (unit_type_count + 4 * 32 + UNIT_TROOPERS)
        ld  b, a
        ld  a, (unit_type_count + 4 * 32 + UNIT_TROOPER)
        add a, b
        cp  10
        jp  nc, hs_rf_wait10
hs_rf_1:
        ; where: near the base
        ld  a, (iy + O_HOUSE)
        ld  b, a
        ld  a, (ix + 2)         ; the record's kind (S9 port)
        push ix
        push iy
        FCALL map_find_location
        pop iy
        pop ix
        call map_valid
        jp  nc, hs_rf_wait10
        ld  (hs_rf_square), hl
        ; the Carryall, unless this pass has one already
        ld  hl, (hs_rf_carryall)
        ld  a, h
        or  l
        jr  nz, hs_rf_2
        ld  hl, (hs_rf_square)
        call ref_make_square
        ld  b, (iy + O_HOUSE)
        ld  a, UNIT_CARRYALL
        push ix
        call unit_deliver
        pop ix
        ld  (hs_rf_carryall), hl
hs_rf_2:
        ld  hl, (hs_rf_carryall)
        ld  a, h
        or  l
        jr  z, hs_rf_later
        push hl
        pop iy                  ; IY = the Carryall
        ld  hl, (hs_rf_unit)
        ld  de, O_HOUSE
        add hl, de
        ld  a, (iy + O_HOUSE)
        cp  (hl)
        jr  nz, hs_rf_later
        ; into the Carryall: the unit goes at the head of its chain
        ld  hl, (hs_rf_unit)
        inc hl
        inc hl
        inc hl                  ; +3 linkedID
        ld  a, (iy + O_LINKED)
        ld  (hl), a
        ld  a, (ix + 0)
        ld  (iy + O_LINKED), a
        set OF_INTRANSPORT - 8, (iy + O_FLAGS + 1)
        ld  (ix + 0), $FF       ; delivered
        ; a repeating record makes the next unit now, off the map
        ld  a, (ix + 8)
        or  (ix + 9)
        jr  z, hs_rf_next
        ld  hl, (hs_rf_unit)
        inc hl
        inc hl
        ld  b, (hl)             ; the type
        ld  de, O_HOUSE - 2
        add hl, de
        ld  c, (hl)             ; the house
        ld  hl, validate_strict
        inc (hl)
        ld  hl, $FFFF
        ld  (arg_pos), hl
        ld  (arg_pos + 2), hl
        ld  d, 0
        ld  a, $FF
        push ix
        FCALL unit_spawn
        pop ix
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        jr  z, hs_rf_next
        ld  a, (hl)             ; its slot
        ld  (ix + 0), a
        ld  (ix + 1), 0
        ld  a, (ix + 6)
        ld  (ix + 4), a
        ld  a, (ix + 7)
        ld  (ix + 5), a
        jr  hs_rf_next
hs_rf_later:
        ld  (ix + 4), 1
        ld  (ix + 5), 0
        jr  hs_rf_next
hs_rf_wait10:
        ld  (ix + 4), 10
        ld  (ix + 5), 0
hs_rf_next:
        ld  hl, (hs_rf_rec)
        ld  de, 10
        add hl, de
        ld  (hs_rf_rec), hl
        ld  hl, hs_rf_n
        inc (hl)
        ld  a, (hl)
        cp  16
        jp  c, hs_rf_loop
        ret

; ================================================================ deliveries

; house_ensure_harvester ($048060): A = the house.  Nothing if one of its
; Carryalls carries a Harvester or a Harvester of the house exists
; anywhere (unit_exists $0432D2 - docked in a Refinery too); otherwise, if
; it has a Refinery, a Harvester is delivered to the first.  -> A = 1 if it
; has or now gets one.  (The PC also told the player "Harvester is heading
; to refinery"; the Mega Drive does not.)  Keeps IX, IY.
house_ensure_harvester:
        push ix
        push iy
        ld  (hs_eh_house), a
        ld  hl, hs_search
        ld  b, a
        ld  c, UNIT_CARRYALL
        FCALL unit_find_first
hs_eh_l:
        jr  z, hs_eh_2
        push hl
        pop ix
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, hs_eh_n
        call unit_ptr
        inc hl
        inc hl
        ld  a, (hl)
        cp  UNIT_HARVESTER
        jr  z, hs_eh_yes
hs_eh_n:
        ld  hl, hs_search
        FCALL unit_find_next
        jr  hs_eh_l
hs_eh_2:
        ld  a, (hs_eh_house)
        ld  b, a
        ld  c, UNIT_HARVESTER
        call hs_unit_exists
        jr  nz, hs_eh_yes
        ld  hl, hs_search
        ld  a, (hs_eh_house)
        ld  b, a
        ld  c, STRUCT_REFINERY
        FCALL struct_find_first
        jr  z, hs_eh_no
        ld  l, (hl)
        ld  h, REF_STRUCT >> 8
        ld  a, (hs_eh_house)
        ld  b, a
        ld  a, UNIT_HARVESTER
        call unit_deliver
hs_eh_yes:
        ld  a, 1
        jr  hs_eh_x
hs_eh_no:
        xor a
hs_eh_x:
        pop iy
        pop ix
        ret

; unit_exists ($0432D2): B = the house ($FF any), C = the type ($FF any) ->
; NZ (A = 1) if a unit in use is of both - off the map too.  Clobbers DE,
; HL.
hs_unit_exists:
        ld  a, (unit_find_count)
        or  a
        ret z
        ld  hl, unit_find
hs_ue_l:
        push af
        push hl
        ld  a, (hl)
        call unit_ptr
        ld  de, O_TYPE
        add hl, de
        ld  a, c
        cp  $FF
        jr  z, hs_ue_1
        cp  (hl)
        jr  nz, hs_ue_n
hs_ue_1:
        ld  de, O_HOUSE - O_TYPE
        add hl, de
        ld  a, b
        cp  $FF
        jr  z, hs_ue_yes
        cp  (hl)
        jr  z, hs_ue_yes
hs_ue_n:
        pop hl
        inc hl
        pop af
        dec a
        jr  nz, hs_ue_l
        ret                     ; Z, A = 0
hs_ue_yes:
        pop hl
        pop af
        ld  a, 1
        or  a
        ret

; unit_deliver ($048102): A = the type, B = the house, HL = the
; destination reference or 0 -> HL = the new unit or 0 (Z).  Keeps IX, IY.
;
; The unit comes in from an edge: a random kind 0-3 of map_find_location,
; asked twice, the column from the first answer and the row from the
; second (S8: harmless, kept); if that square is on screen, from the
; "opposite" edge (kind ^ 3).  It faces the middle of the map.  A flyer
; (movement 4) is made there and flies in by itself, marked byScenario (a
; Frigate is remembered in frigateComing).  Anything else is made off the
; map inside an idle Carryall of the house that is off screen - or a new
; Carryall made at the edge - which is sent to the destination.  If the
; unit cannot be made the Carryall is removed (even an old one - the
; cartridge's way), and a Harvester is owed to the house instead
; (harvestersIncoming, only if nothing is owed yet).
unit_deliver:
        push ix
        push iy
        ld  (hs_ud_type), a
        ld  a, b
        ld  (hs_ud_house), a
        ld  (hs_ud_dest), hl
        call random
        and 3
        ld  (hs_ud_kind), a
        call hs_ud_point
        ld  a, (hs_pos + 1)
        ld  b, a
        ld  a, (hs_pos + 3)
        ld  c, a
        call hs_square_visible
        jr  nc, hs_ud_1
        ld  a, (hs_ud_kind)
        xor 3
        ld  (hs_ud_kind), a
        call hs_ud_point
hs_ud_1:
        ; facing the middle of the map ($2000, $2000)
        ld  hl, hs_pos
        ld  de, hs_ud_centre
        call tile_direction
        ld  (hs_ud_facing), a
        ld  a, (hs_ud_type)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, hs_ud_carried
        ; a flyer
        ld  a, (hs_ud_type)
        ld  hl, hs_pos
        call hs_ud_spawn
        jp  z, hs_ud_fail0
        push hl
        pop ix
        set OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
        ld  hl, (hs_ud_dest)
        ld  a, h
        or  l
        call nz, hs_set_destination
        ld  a, (ix + O_TYPE)
        cp  UNIT_FRIGATE
        jr  nz, hs_ud_ix
        ld  a, (ix + O_INDEX)
        ld  (frigate_coming), a
hs_ud_ix:
        push ix
        pop hl
        jp  hs_ud_out
hs_ud_carried:
        ; an idle Carryall of the house, off screen ($04823A)
        ld  hl, hs_search
        ld  a, (hs_ud_house)
        ld  b, a
        ld  c, UNIT_CARRYALL
        FCALL unit_find_first
hs_udc_l:
        jr  z, hs_udc_new
        push hl
        pop ix
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, hs_udc_n
        ld  a, (ix + U_TARGETMOVE)
        or  (ix + U_TARGETMOVE + 1)
        jr  nz, hs_udc_n
        ld  b, (ix + O_POS_Y + 1)
        ld  c, (ix + O_POS_X + 1)
        call hs_square_visible
        jr  nc, hs_udc_have
hs_udc_n:
        ld  hl, hs_search
        FCALL unit_find_next
        jr  hs_udc_l
hs_udc_new:
        ; none: a new Carryall at the edge
        xor a                   ; UNIT_CARRYALL
        ld  hl, hs_pos
        call hs_ud_spawn
        jr  z, hs_ud_fail
        push hl
        pop ix
        ld  a, (hs_ud_house)
        ld  b, a
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        or  a
        jr  nz, hs_udc_scen
        ld  a, (hs_ud_house)
        ld  b, a
        ld  c, UNIT_CARRYALL
        call hs_unit_exists     ; (it finds the new one: always)
        jr  z, hs_udc_have
hs_udc_scen:
        set OF_BYSCENARIO - 8, (ix + O_FLAGS + 1)
hs_udc_have:
        ; IX = the Carryall: the unit, made off the map, goes in
        xor a
        ld  (hs_ud_facing), a
        ld  a, (hs_ud_type)
        ld  hl, hs_ud_offmap
        push ix
        call hs_ud_spawn
        pop ix
        jr  z, hs_udc_remove
        ld  (hs_ud_unit), hl
        set OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        ld  a, (hl)
        ld  (ix + O_LINKED), a
        ld  a, (hs_ud_type)
        cp  UNIT_HARVESTER
        jr  nz, hs_udc_1
        ld  de, U_AMOUNT
        add hl, de
        ld  (hl), 1
hs_udc_1:
        ld  hl, (hs_ud_dest)
        ld  a, h
        or  l
        call nz, hs_set_destination
        ld  hl, (hs_ud_unit)
        jr  hs_ud_out
hs_udc_remove:
        FCALL unit_remove
hs_ud_fail:
        ; a Harvester that cannot be made is owed ($048330)
        ld  a, (hs_ud_type)
        cp  UNIT_HARVESTER
        jr  nz, hs_ud_fail0
        ld  a, (hs_ud_house)
        call house_ptr
        ld  de, H_HARVINCOMING
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  nz, hs_ud_fail0
        dec hl
        inc (hl)
hs_ud_fail0:
        ld  hl, 0
hs_ud_out:
        pop iy
        pop ix
        ld  a, h
        or  l
        ret

; The arrival point: hs_pos = the centre of (row of the second answer,
; column of the first) of map_find_location(ud_kind).
hs_ud_point:
        ld  a, (hs_ud_house)
        ld  b, a
        ld  a, (hs_ud_kind)
        FCALL map_find_location
        ld  a, l
        and $3F
        ld  (hs_pos + 3), a     ; the column
        ld  a, (hs_ud_house)
        ld  b, a
        ld  a, (hs_ud_kind)
        FCALL map_find_location
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  (hs_pos + 1), a     ; the row
        ld  a, $80
        ld  (hs_pos), a
        ld  (hs_pos + 2), a
        ret

; A = the type, HL -> the position: unit_spawn with the unit cap lifted
; (validateStrictIfZero + 1), facing ud_facing, house ud_house -> HL, Z.
hs_ud_spawn:
        push af
        ld  de, arg_pos
        ld  bc, 4
        ldir
        pop af
        ld  b, a
        ld  a, (hs_ud_house)
        ld  c, a
        ld  a, (hs_ud_facing)
        ld  d, a
        ld  hl, validate_strict
        inc (hl)
        ld  a, $FF
        FCALL unit_spawn
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        ret

hs_ud_centre:   DW $2000, $2000
hs_ud_offmap:   DW $FFFF, $FFFF

; view_square_visible ($005DE6): B = a row, C = a column -> carry if the
; square is on screen with a margin: row in (vy - 1, vy + 8), column in
; (vx - 1, vx + 11), vy and vx the view's top-left square.  Clobbers A,
; DE, HL.
hs_square_visible:
        ld  hl, (view_y)
        call hs_sv_sq              ; A = vy
        dec a
        ld  e, a                ; vy - 1 (may be -1)
        add a, 9                ; vy + 8
        ld  d, a
        ld  a, b
        call hs_sv_in
        ret nc
        ld  hl, (view_x)
        call hs_sv_sq
        dec a
        ld  e, a
        add a, 12
        ld  d, a
        ld  a, c
        ; fall through
; E < A < D, signed words from bytes (the view is 0-63) -> carry.
hs_sv_in:
        push bc
        ld  c, a
        ld  a, e
        cp  $FF
        jr  z, hs_svi_lo           ; -1 < anything
        ld  a, c
        cp  e
        jr  z, hs_svi_no
        jr  c, hs_svi_no
hs_svi_lo:
        ld  a, c
        cp  d
        pop bc
        ret                     ; carry: A < D
hs_svi_no:
        pop bc
        or  a
        ret
hs_sv_sq:
        add hl, hl
        add hl, hl
        add hl, hl              ; H = pixels >> 5
        ld  a, h
        ret

; ============================================================ what is seen

; unit_seen_by_house ($023260): IX = a unit, A = the house that sees it
; (S7).  Keeps IX, IY.
;
; d4 = the house's bit, and the Fremen's too when the Atreides see
; anything but a Sandworm.  Already seen by those and the house awake:
; only the bits.  Otherwise, for a "normal" unit (type +$38 bit 15) or a
; Sandworm: the first sight counts it into the seer's allied or enemy
; count; a ground unit of an unfriendly house wakes the seer and the
; unit's house (which, the first time, staggers its structures' scripts
; 16, 32, 48 ... ticks apart - Mega Drive only); the player hears voice 1
; unless the warning timer runs, and the timer is set to 8 house ticks
; (the cartridge also writes variable 4 of team unit.team - the wrong team,
; and nothing reads it; S7 port: dropped); an unfriendly unit in Ambush
; turns to Hunt; and the unit is marked seen - by everyone if it is the
; player's, or a Fremen's while the player is Atreides.
unit_seen_by_house:
        push ix
        push iy
        ld  (hs_sb_house), a
        call house_ptr
        push hl
        pop iy                  ; IY = the seer
        ld  a, (hs_sb_house)
        call hs_house_bit
        ld  (hs_sb_bits), a
        ld  a, (hs_sb_house)
        cp  HOUSE_ATREIDES
        jr  nz, hs_sb_1
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, hs_sb_1
        ld  a, (hs_sb_bits)
        or  1 << HOUSE_FREMEN
        ld  (hs_sb_bits), a
hs_sb_1:
        ; seen already, and awake: just the bits
        ld  a, (hs_sb_bits)
        and (ix + O_SEEN)
        jr  z, hs_sb_2
        bit HF_AIACTIVE, (iy + H_FLAGS)
        jr  z, hs_sb_2
        ld  a, (hs_sb_bits)
        or  (ix + O_SEEN)
        ld  (ix + O_SEEN), a
        jp  hs_sb_out
hs_sb_2:
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  (hs_sb_info), hl
        ld  de, UI_flags + 1
        add hl, de
        bit 7, (hl)             ; isNormalUnit
        jr  nz, hs_sb_3
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jp  nz, hs_sb_out
hs_sb_3:
        ; the first sight is counted
        ld  a, (hs_sb_bits)
        and (ix + O_SEEN)
        jr  nz, hs_sb_4
        call hs_sb_allied          ; the unit's house and the seer
        or  a
        jr  z, hs_sb_3e
        ld  l, (iy + H_UNITSALLIED)
        ld  h, (iy + H_UNITSALLIED + 1)
        inc hl
        ld  (iy + H_UNITSALLIED), l
        ld  (iy + H_UNITSALLIED + 1), h
        jr  hs_sb_4
hs_sb_3e:
        ld  l, (iy + H_UNITSENEMY)
        ld  h, (iy + H_UNITSENEMY + 1)
        inc hl
        ld  (iy + H_UNITSENEMY), l
        ld  (iy + H_UNITSENEMY + 1), h
hs_sb_4:
        ; a ground unit of an unfriendly house wakes both houses
        ld  hl, (hs_sb_info)
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  z, hs_sb_5
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, hs_sb_5
        call hs_sb_allied
        or  a
        jr  nz, hs_sb_5
        set HF_AIACTIVE, (iy + H_FLAGS)
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        bit HF_AIACTIVE, (hl)
        jr  nz, hs_sb_5
        push hl
        ld  a, (ix + O_HOUSE)
        call hs_stagger_scripts
        pop hl
        set HF_AIACTIVE, (hl)
hs_sb_5:
        ; the player's warning
        ld  a, (hs_sb_house)
        ld  hl, player_house
        cp  (hl)
        jr  nz, hs_sb_6
        ld  a, (ix + O_HOUSE)
        ld  b, a
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        or  a
        jr  nz, hs_sb_6
        ld  a, (ix + O_TYPE)
        cp  UNIT_SANDWORM
        jr  z, hs_sb_6
        ld  a, (player_house)
        call house_ptr
        ld  de, H_TIMERUNIT
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  nz, hs_sb_5a
        push hl
        ld  a, 1
        FCALL snd_voice
        pop hl
hs_sb_5a:
        ld  (hl), 0
        dec hl
        ld  (hl), 8
hs_sb_6:
        ; an unfriendly unit in Ambush hunts
        call hs_sb_allied
        or  a
        jr  nz, hs_sb_7
        ld  a, (ix + U_ACTION)
        cp  ORDER_AMBUSH
        jr  nz, hs_sb_7
        ld  a, ORDER_HUNT
        FCALL unit_give_order
hs_sb_7:
        ; seenByHouses
        ld  a, (player_house)
        ld  b, a
        ld  a, (ix + O_HOUSE)
        cp  b
        jr  z, hs_sb_all
        cp  HOUSE_FREMEN
        jr  nz, hs_sb_8
        ld  a, b
        cp  HOUSE_ATREIDES
        jr  nz, hs_sb_8
hs_sb_all:
        ld  (ix + O_SEEN), $FF
        jr  hs_sb_out
hs_sb_8:
        ld  a, (hs_sb_bits)
        or  (ix + O_SEEN)
        ld  (ix + O_SEEN), a
hs_sb_out:
        pop iy
        pop ix
        ret

; house_are_allied(the unit's house, the seer) -> A.
hs_sb_allied:
        ld  b, (ix + O_HOUSE)
        ld  a, (hs_sb_house)
        ld  c, a
        jp  house_are_allied

; A = a house -> A = 1 << house.
hs_house_bit:
        ld  b, a
        inc b
        xor a
        scf
hs_hb_l:
        rla
        djnz hs_hb_l
        ret

; struct_stagger_scripts ($00BB1A): A = the house.  Every structure slot
; (all 73, used or not) of the house but Refineries gets a script delay of
; 16, 32, 48 ... - Mega Drive only, when the house's AI wakes.
hs_stagger_scripts:
        push ix
        call hs_ss_go
        pop ix
        ret
hs_ss_go:
        ld  c, a
        ld  de, 16
        ld  b, 0
hs_ss_l:
        push bc
        push de
        ld  a, b
        call struct_ptr
        pop de
        pop bc
        push hl
        pop ix
        ld  a, (ix + O_HOUSE)
        cp  c
        jr  nz, hs_ss_n
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REFINERY
        jr  z, hs_ss_n
        ld  (ix + O_DELAY), e
        ld  (ix + O_DELAY + 1), d
        ld  hl, 16
        add hl, de
        ex  de, hl
hs_ss_n:
        inc b
        ld  a, b
        cp  STRUCT_COUNT
        jr  c, hs_ss_l
        ret

; unit_unseen_by_houses ($02344C): IX = a unit, A = a house (not read:
; every house is done).  If it was the player's selection and is not the
; player's, it is deselected; every house in use that saw it counts it
; out of its allied or enemy count and loses its bit.  Keeps IX, IY.
unit_unseen_by_houses:
        push iy
        ld  a, (unit_selected)
        cp  (ix + O_INDEX)
        jr  nz, hs_uu_1
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, hs_uu_1
        ld  a, $FF
        ld  (unit_selected), a
hs_uu_1:
        ld  a, (ix + O_SEEN)
        or  a
        jr  z, hs_uu_out
        xor a
        ld  (hs_uu_i), a
hs_uu_l:
        ld  a, (house_find_count)
        ld  b, a
        ld  a, (hs_uu_i)
        cp  b
        jr  nc, hs_uu_out
        ld  e, a
        ld  d, 0
        ld  hl, house_find
        add hl, de
        ld  a, (hl)
        ld  (hs_uu_h), a
        call hs_house_bit
        ld  (hs_uu_b), a
        and (ix + O_SEEN)
        jr  z, hs_uu_n
        ld  a, (hs_uu_h)
        call house_ptr
        push hl
        pop iy
        ld  b, (ix + O_HOUSE)
        ld  a, (hs_uu_h)
        ld  c, a
        call house_are_allied
        or  a
        jr  nz, hs_uu_al
        ld  l, (iy + H_UNITSENEMY)
        ld  h, (iy + H_UNITSENEMY + 1)
        dec hl
        ld  (iy + H_UNITSENEMY), l
        ld  (iy + H_UNITSENEMY + 1), h
        jr  hs_uu_c
hs_uu_al:
        ld  l, (iy + H_UNITSALLIED)
        ld  h, (iy + H_UNITSALLIED + 1)
        dec hl
        ld  (iy + H_UNITSALLIED), l
        ld  (iy + H_UNITSALLIED + 1), h
hs_uu_c:
        ld  a, (hs_uu_b)
        cpl
        and (ix + O_SEEN)
        ld  (ix + O_SEEN), a
hs_uu_n:
        ld  hl, hs_uu_i
        inc (hl)
        jr  hs_uu_l
hs_uu_out:
        pop iy
        ret

; struct_house_under_attack ($02365C): A = the house (S7) -> A = 1, or 0
; for a computer house that was told before.  doneFullScaleAttack is set
; the first time; the player hears voice $30 at most every 8 house ticks
; (timerStructureAttack).  A computer house's units are then meant to
; hunt, but the search asks for type 0 (Carryalls) and a test that only
; Area Guard passes - so only an armed Carryall under Area Guard would
; (none is), as in the PC.  Kept.  Keeps IX, IY.
struct_house_under_attack:
        push ix
        push iy
        ld  (hs_ua_house), a
        call house_ptr
        push hl
        pop iy
        ld  a, (hs_ua_house)
        ld  hl, player_house
        cp  (hl)
        jr  z, hs_ua_1
        bit HF_FULLATTACK, (iy + H_FLAGS)
        jr  z, hs_ua_1
        xor a
        jr  hs_ua_out
hs_ua_1:
        set HF_FULLATTACK, (iy + H_FLAGS)
        bit HF_HUMAN, (iy + H_FLAGS)
        jr  z, hs_ua_ai
        ld  a, (iy + H_TIMERSTRUCT)
        or  (iy + H_TIMERSTRUCT + 1)
        jr  nz, hs_ua_yes
        ld  a, $30
        FCALL snd_voice
        ld  (iy + H_TIMERSTRUCT), 8
        ld  (iy + H_TIMERSTRUCT + 1), 0
        jr  hs_ua_yes
hs_ua_ai:
        ld  hl, hs_search2
        ld  a, (hs_ua_house)
        ld  b, a
        ld  c, UNIT_CARRYALL
        FCALL unit_find_first
hs_ua_l:
        jr  z, hs_ua_yes
        push hl
        pop ix
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_bulletType
        add hl, de
        ld  a, (hl)
        inc hl
        and (hl)
        inc a
        jr  z, hs_ua_n             ; unarmed
        ld  a, (ix + U_ACTION)
        cp  ORDER_AREAGUARD     ; (Guard and Ambush at once never)
        jr  nz, hs_ua_n
        ld  a, ORDER_HUNT
        FCALL unit_give_order
hs_ua_n:
        ld  hl, hs_search2
        FCALL unit_find_next
        jr  hs_ua_l
hs_ua_yes:
        ld  a, 1
hs_ua_out:
        pop iy
        pop ix
        ret

; ====================================================== the bank's own copies

; unit_set_destination ($047D18): IX = the unit, HL = a reference.  A
; square with another unit or a structure on it becomes that thing; a
; structure of the unit's house that will take it (unit_can_enter_structure
; = 1) - or any, for a flyer - is claimed for it (obj_var4_link); then
; targetMove = the reference and the route is dropped.  Nothing for a
; stale reference or the one it has.  Keeps IX.
hs_set_destination:
    IF EXIST unit_set_destination
        push iy
        FCALL unit_set_destination
        pop iy
        ret
    ELSE
        push iy
        ld  (hs_sd_ref), hl
        call ref_is_valid
        or  a
        jp  z, hs_sd_out
        ld  hl, (hs_sd_ref)
        ld  a, l
        cp  (ix + U_TARGETMOVE)
        jr  nz, hs_sd_1
        ld  a, h
        cp  (ix + U_TARGETMOVE + 1)
        jp  z, hs_sd_out
hs_sd_1:
        ld  a, h
        and $C0
        cp  $C0
        jr  nz, hs_sd_2
        call hs_ref_square      ; the square it names
        ld  (hs_sd_sq), hl
        FCALL map_unit_at
        jr  z, hs_sd_nounit
        push ix
        pop de
        or  a
        sbc hl, de
        jr  z, hs_sd_2             ; itself: the square stays
        add hl, de
        ld  l, (hl)
        ld  h, REF_UNIT >> 8
        ld  (hs_sd_ref), hl
        jr  hs_sd_2
hs_sd_nounit:
        ld  hl, (hs_sd_sq)
        call hs_struct_at
        jr  z, hs_sd_2
        ld  l, (hl)
        ld  h, REF_STRUCT >> 8
        ld  (hs_sd_ref), hl
hs_sd_2:
        ld  hl, (hs_sd_ref)
        call hs_ref_struct
        jr  z, hs_sd_set
        push hl
        pop iy
        ld  a, (iy + O_HOUSE)
        cp  (ix + O_HOUSE)
        jr  nz, hs_sd_fly
        FCALL unit_can_enter_structure
        cp  1
        jr  z, hs_sd_link
hs_sd_fly:
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, hs_sd_set
hs_sd_link:
        ld  e, (ix + O_INDEX)
        ld  d, REF_UNIT >> 8
        ld  l, (iy + O_INDEX)
        ld  h, REF_STRUCT >> 8
        call hs_var4_link
hs_sd_set:
        ld  hl, (hs_sd_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  (ix + U_ROUTE), $FF
hs_sd_out:
        pop iy
        ret
    ENDIF

; obj_var4_link ($023CCC): DE = the reference from, HL = the reference to.
; Both must be good; if their variables 4 differ, both links are broken;
; then, unless the first is linked (to the same thing), each gets the
; other.  -> A = 1, or 0 if either is stale.  Keeps IX, IY.
hs_var4_link:
        push ix
        push iy
        ld  (hs_vl_from), de
        ld  (hs_vl_to), hl
        call ref_is_valid
        or  a
        jr  z, hs_vl_out
        ld  hl, (hs_vl_from)
        call ref_is_valid
        or  a
        jr  z, hs_vl_out
        ld  hl, (hs_vl_from)
        call hs_ref_object
        jr  z, hs_vl_zero
        ld  (hs_vl_a2), hl
        ld  hl, (hs_vl_to)
        call hs_ref_object
        jr  z, hs_vl_zero
        ld  (hs_vl_a3), hl
        ld  ix, (hs_vl_a2)         ; IX = from (a2)
        ld  iy, (hs_vl_a3)         ; IY = to (a3)
        ld  a, (ix + HS_VAR4)
        cp  (iy + HS_VAR4)
        jr  nz, hs_vl_clear
        ld  a, (ix + HS_VAR4 + 1)
        cp  (iy + HS_VAR4 + 1)
        jr  z, hs_vl_1
hs_vl_clear:
        FCALL obj_var4_clear    ; (it uses IY)
        ld  ix, (hs_vl_a3)
        FCALL obj_var4_clear
        ld  ix, (hs_vl_a2)
hs_vl_1:
        ld  a, (ix + HS_VAR4)
        or  (ix + HS_VAR4 + 1)
        jr  nz, hs_vl_one
        ld  hl, (hs_vl_to)
        FCALL obj_var4_set
        ld  ix, (hs_vl_a3)
        ld  hl, (hs_vl_from)
        FCALL obj_var4_set
hs_vl_one:
        ld  a, 1
        jr  hs_vl_out
hs_vl_zero:
        xor a
hs_vl_out:
        pop iy
        pop ix
        ret

; A reference -> HL = the unit / structure / either it names, or 0 (Z).
; Clobbers A, DE.
hs_ref_unit:
        ld  a, h
        and $C0
        cp  $40
        jr  nz, hs_hr_no
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, hs_hr_no
        call unit_ptr
        or  1
        ret
hs_ref_struct:
        ld  a, h
        and $C0
        cp  $80
        jr  nz, hs_hr_no
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, hs_hr_no
        call struct_ptr
        or  1
        ret
hs_ref_object:
        ld  a, h
        and $C0
        cp  $40
        jr  z, hs_ref_unit
        jr  hs_ref_struct
hs_hr_no:
        ld  hl, 0
        xor a
        ret

; A square reference ($C000 | row << 8 | $80 | col << 1 | 1) -> HL = the
; square.  Clobbers A.
hs_ref_square:
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

; HL = a square -> HL = the structure on it, or 0 (Z).  Clobbers A.
hs_struct_at:
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_STRUCT, (hl)
        jr  z, hs_hr_no
        ld  a, h
        xor (MAP_FLAGS ^ MAP_INDEX) >> 8
        ld  h, a
        ld  a, (hl)
        or  a
        jr  z, hs_hr_no
        dec a
        call struct_ptr
        or  1
        ret

; unit_place ($048534): IX = the unit, hs_pos = a position -> A = 1 if it
; was put on the map there (the square's centre), 0 if the square cannot
; take it (then it is marked isNotOnMap).  A home is chosen if it has
; none; its claim is dropped; placed, it has no destination or target (a
; Harvester keeps its +$5A), it is seen as its square is, takes its
; house's default order (the player's Harvesters and Saboteurs the
; computer's), and a Starport cargo is counted delivered.  Keeps IX.
hs_unit_place:
        push iy
        res OF_NOTONMAP, (ix + O_FLAGS)
        ld  a, (hs_pos + 1)
        ld  (ix + O_POS_Y + 1), a
        ld  a, (hs_pos + 3)
        ld  (ix + O_POS_X + 1), a
        ld  a, $80
        ld  (ix + O_POS_Y), a
        ld  (ix + O_POS_X), a
        xor a
        ld  (ix + U_STEP_X), a
        ld  (ix + U_STEP_X + 1), a
        ld  (ix + U_STEP_Y), a
        ld  (ix + U_STEP_Y + 1), a
        ld  a, (ix + U_ORIGIN)
        or  (ix + U_ORIGIN + 1)
        jr  nz, hs_up_1
        FCALL unit_choose_home
hs_up_1:
        xor a
        ld  (ix + HS_VAR4), a
        ld  (ix + HS_VAR4 + 1), a
        FCALL unit_blocked_here
        or  a
        jr  z, hs_up_2
        set OF_NOTONMAP, (ix + O_FLAGS)
        xor a
        pop iy
        ret
hs_up_2:
        xor a
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, hs_up_3
        xor a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
hs_up_3:
        ; seen if the square is revealed
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNVEILED, (hl)
        jr  z, hs_up_4
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, hs_up_3a
        ld  a, (ix + O_HOUSE)
        call hs_house_bit
hs_up_3a:
        ld  (ix + O_SEEN), a
        ld  a, (player_house)
        call unit_seen_by_house
hs_up_4:
        ; the default order
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_actionAI
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, hs_up_5
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, hs_up_5
        cp  UNIT_SABOTEUR
        jr  z, hs_up_5
        ld  de, UI_actionPlayer
hs_up_5:
        add hl, de
        ld  a, (hl)
        FCALL unit_give_order
        ld  (ix + U_SPRITEOFS), 0
        ld  a, 1
        FCALL unit_update_map
        ; a Starport cargo is delivered (flags2 bit 9)
        bit 1, (ix + O_FLAGS2 + 1)
        jr  z, hs_up_6
        res 1, (ix + O_FLAGS2 + 1)
    IF EXIST starport_cargo_pending
        ld  hl, (starport_cargo_pending)
        dec hl
        bit 7, h
        jr  z, hs_up_5a
        ld  hl, 0               ; (bpl, else 0)
hs_up_5a:
        ld  (starport_cargo_pending), hl
    ENDIF
hs_up_6:
        ld  a, 1
        pop iy
        ret

; struct_set_state ($00FA0E): IY = a structure, A = the state.  STRUCT's
; if it is there (it also redraws the structure).  Keeps IX, IY.
hs_set_state_iy:
    IF EXIST struct_set_state
        push ix
        push iy
        pop ix
        push iy
        FCALL struct_set_state
        pop iy
        pop ix
    ELSE
        ld  (iy + S_STATE), a
        ld  (iy + S_STATE + 1), 0
    ENDIF
        ret

; unit_take_off_map ($04869C): IX = the unit.  Off its squares, its
; script reset, every reference to it dropped, isNotOnMap, unseen by the
; houses, its position -1.  Keeps IX.
hs_take_off_map:
        set 6, (ix + O_FLAGS)
        xor a
        FCALL unit_update_map
        res 6, (ix + O_FLAGS)
        push ix
        ld  de, O_SCRIPT
        add ix, de
        ld  a, EMC_UNIT
        FCALL emc_reset
        pop ix
        FCALL unit_drop_references
        set OF_NOTONMAP, (ix + O_FLAGS)
        ld  (ix + U_SHOWN), 0   ; its sprite hidden (c_spr_hide)
        ld  a, (player_house)
        call unit_unseen_by_houses
        ld  a, $FF
        ld  (ix + O_POS_Y), a
        ld  (ix + O_POS_Y + 1), a
        ld  (ix + O_POS_X), a
        ld  (ix + O_POS_X + 1), a
        ret

; ================================================= the UNIT.EMC routines
;
; Called with IX = the script state; the unit is IX - O_SCRIPT (the
; cartridge's scriptCurrentUnit and scriptCurrentObject).  Answer in HL.

; IX = the state -> IX = the unit.
hs_ef_object:
        ld  de, -O_SCRIPT
        add ix, de
        ret

; The argument on top of the stack -> HL (IX = the state).
hs_ef_arg0:
        xor a
        jp  emc_arg

; UNIT 0 get ($04500C): property n of the unit (the switch at $04503E).
ef_u_get:
        call hs_ef_arg0
        ld  a, h
        or  a
        jr  nz, hs_eg_zero
        ld  a, l
        cp  20
        jr  nc, hs_eg_zero
        call hs_ef_object
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, hs_eg_table
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  a, (ix + O_TYPE)
        push hl
        call unit_info          ; HL = the type
        ret                     ; to the property
hs_eg_zero:
        ld  hl, 0
        ret
hs_eg_table:    DW  hs_eg_health, hs_eg_tmove, hs_eg_range, hs_eg_index, hs_eg_facing
        DW  hs_eg_tattack, hs_eg_origin, hs_eg_type, hs_eg_self, hs_eg_speed
        DW  hs_eg_turnleft, hs_eg_moving, hs_eg_loaded, hs_eg_explodes, hs_eg_house
        DW  hs_eg_scenario, hs_eg_gunfacing, hs_eg_gunleft, hs_eg_turret, hs_eg_seen
hs_eg_health:
        ; 0: health * 256 / the type's (math_div_shl8)
        ld  de, UI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  e, (ix + O_HP)
        ld  d, (ix + O_HP + 1)
        jp  div_shl8
hs_eg_tmove:
        ; 1: targetMove if still good
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        push hl
        call ref_is_valid
        pop hl
        or  a
        ret nz
        jr  hs_eg_zero
hs_eg_range:
        ; 2: fire range << 8
        ld  de, UI_fireDistance
        add hl, de
        ld  h, (hl)
        ld  l, 0
        ret
hs_eg_index:
        ; 3
        ld  l, (ix + O_INDEX)
        ld  h, 0
        ret
hs_eg_facing:
        ; 4: the hull
        ld  l, (ix + U_OR0_CURRENT)
        ld  h, 0
        ret
hs_eg_tattack:
        ; 5
        ld  l, (ix + U_TARGETATTACK)
        ld  h, (ix + U_TARGETATTACK + 1)
        ret
hs_eg_origin:
        ; 6: its home, chosen first if it has none
        ld  a, (ix + U_ORIGIN)  ; (or always, for a Harvester)
        or  (ix + U_ORIGIN + 1)
        jr  z, hs_ego_1
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, hs_ego_2
hs_ego_1:
        FCALL unit_choose_home
hs_ego_2:
        ld  l, (ix + U_ORIGIN)
        ld  h, (ix + U_ORIGIN + 1)
        ret
hs_eg_type:
        ; 7
        ld  l, (ix + O_TYPE)
        ld  h, 0
        ret
hs_eg_self:
        ; 8: a reference to itself
        ld  l, (ix + O_INDEX)
        ld  h, REF_UNIT >> 8
        ret
hs_eg_speed:
        ; 9: +$71
        ld  l, (ix + U_MOVINGSPEED)
        ld  h, 0
        ret
hs_eg_turnleft:
        ; 10: |hull target - current|
        ld  a, (ix + U_OR0_TARGET)
        ld  b, (ix + U_OR0_CURRENT)
hs_eg_absdiff:
        sub b
        jr  nc, hs_egt_1
        neg
hs_egt_1:
        ld  l, a
        ld  h, 0
        ret
hs_eg_moving:
        ; 11: currentDestination != 0
        ld  a, (ix + U_DEST_Y)
        or  (ix + U_DEST_Y + 1)
        or  (ix + U_DEST_X)
        or  (ix + U_DEST_X + 1)
hs_eg_bool:
        ld  hl, 0
        ret z
        inc l
        ret
hs_eg_loaded:
        ; 12: fireDelay == 0
        ld  a, (ix + U_FIREDELAY)
        or  a
        ld  hl, 1
        ret z
        dec l
        ret
hs_eg_explodes:
        ; 13: type +$38 & 4
        ld  de, UI_flags
        add hl, de
        ld  a, (hl)
        and 4
        ld  l, a
        ld  h, 0
        ret
hs_eg_house:
        ; 14
        ld  l, (ix + O_HOUSE)
        ld  h, 0
        ret
hs_eg_scenario:
        ; 15: byScenario
        ld  a, (ix + O_FLAGS + 1)
        and 1 << (OF_BYSCENARIO - 8)
        jr  hs_eg_bool
hs_eg_gunfacing:
        ; 16: the turret's, else the hull's
        call hs_eg_hasturret
        jp  z, hs_eg_facing
        ld  l, (ix + U_OR1_CURRENT)
        ld  h, 0
        ret
hs_eg_gunleft:
        ; 17
        call hs_eg_hasturret
        jr  z, hs_eg_turnleft
        ld  a, (ix + U_OR1_TARGET)
        ld  b, (ix + U_OR1_CURRENT)
        jr  hs_eg_absdiff
hs_eg_turret:
        ; 18
        call hs_eg_hasturret
        jr  hs_eg_bool
hs_eg_seen:
        ; 19: seen by the player
        ld  a, (player_house)
        call hs_house_bit
        and (ix + O_SEEN)
        jr  hs_eg_bool
; HL = the type -> NZ if it has a turret (+$0C bit 6).
hs_eg_hasturret:
        ld  de, UI_objectFlags
        add hl, de
        bit 6, (hl)
        ret

; UNIT 1 act ($044F2E): the order on the stack - except that the player's
; unit is not told to Harvest while it has an order queued.
ef_u_act:
        call hs_ef_arg0
        call hs_ef_object
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, hs_ea_1
        ld  a, l
        cp  ORDER_HARVEST
        jr  nz, hs_ea_1
        ld  a, h
        or  a
        jr  nz, hs_ea_1
        ld  a, (ix + U_NEXTACTION)
        cp  $FF
        jr  nz, hs_ea_x
hs_ea_1:
        ld  a, l
        FCALL unit_give_order
hs_ea_x:
        ld  hl, 0
        ret

; UNIT 10 act.default ($044F78): the type's actionPlayer (+$28), whatever
; the house.
ef_u_act_default:
        call hs_ef_object
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_actionPlayer
        add hl, de
        ld  a, (hl)
        FCALL unit_give_order
        ld  hl, 0
        ret

; UNIT 20 deliver ($043D80): the carrier puts down what it carries at
; targetMove.  At a Starport the whole load goes into it (the structure's
; +3 takes the chain, state 2); another structure takes it if idle, or
; busy-because-something-comes in state 1, with nothing docked
; (unit_enter_structure), else the delivery is refused; on a place it is
; set down on the square under the carrier (unit_place) facing the
; carrier's way, sound $18 for the player's, and the carrier keeps the rest
; of its chain.  A unit reference just clears the carrier's targets.
; -> HL = 1 if something was delivered.
ef_u_deliver:
        call hs_ef_object
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, hs_efd_no
        call unit_ptr
        ld  (hs_efd_cargo), hl
        ld  a, (ix + U_TARGETMOVE + 1)
        and $C0
        cp  $40
        jp  z, hs_efd_unitref
        cp  $80
        jp  nz, hs_efd_place
        ; a structure
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        call hs_ref_struct
        jp  z, hs_efd_refused
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        cp  STRUCT_STARPORT
        jr  nz, hs_efd_other
        ; the whole load into the Starport ($043DF6)
        ld  a, (ix + O_LINKED)
        ld  (iy + O_LINKED), a
        ld  (ix + O_LINKED), $FF
        res OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        ld  (ix + U_AMOUNT), 0
        ld  a, 2
        push iy
        FCALL unit_update_map
        pop iy
        set 1, (ix + O_FLAGS2 + 1)
        ld  a, 2
        call hs_set_state_iy
        FCALL obj_var4_clear
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
        ld  hl, 1
        ret
hs_efd_other:
        ld  a, (iy + S_STATE)
        or  (iy + S_STATE + 1)
        jr  z, hs_efd_enter
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 4, (hl)             ; busyStateIsIncoming
        jr  z, hs_efd_refused
        ld  a, (iy + S_STATE + 1)
        or  a
        jr  nz, hs_efd_refused
        ld  a, (iy + S_STATE)
        cp  1
        jr  nz, hs_efd_refused
hs_efd_enter:
        ld  a, (iy + O_LINKED)
        cp  $FF
        jr  nz, hs_efd_refused
        push ix
        ld  ix, (hs_efd_cargo)
        FCALL unit_enter_structure
        pop ix
        FCALL obj_var4_clear
        xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  (ix + O_LINKED), $FF
        res OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        ld  (ix + U_AMOUNT), a
        ld  a, 2
        FCALL unit_update_map
        ld  hl, 1
        ret
hs_efd_refused:
        FCALL obj_var4_clear
hs_efd_clear:
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
hs_efd_no:
        ld  hl, 0
        ret
hs_efd_unitref:
        xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  (ix + U_TARGETATTACK), a
        ld  (ix + U_TARGETATTACK + 1), a
        jr  hs_efd_no
hs_efd_place:
        ; the square under the carrier ($043EE0)
        ld  a, (ix + O_POS_Y + 1)
        ld  (hs_pos + 1), a
        ld  a, (ix + O_POS_X + 1)
        ld  (hs_pos + 3), a
        ld  hl, hs_pos
        call pos_square
        call map_valid
        jr  nc, hs_efd_clear
        push ix
        ld  ix, (hs_efd_cargo)
        call hs_unit_place
        pop ix
        or  a
        jr  z, hs_efd_no
        ld  iy, (hs_efd_cargo)
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  nz, hs_efd_1
        ld  a, $18
        FCALL snd_effect
hs_efd_1:
        ; facing the carrier's way, at once, hull and turret; standing
        ld  a, (ix + U_OR0_CURRENT)
        push ix
        ld  ix, (hs_efd_cargo)
        push af
        ld  b, 1
        ld  c, 0
        FCALL unit_set_facing
        pop af
        ld  b, 1
        ld  c, 1
        FCALL unit_set_facing
        xor a
        FCALL unit_set_speed
        pop ix
        ; the carrier keeps the rest of the chain
        ld  iy, (hs_efd_cargo)
        ld  a, (iy + O_LINKED)
        ld  (ix + O_LINKED), a
        ld  (iy + O_LINKED), $FF
        cp  $FF
        jr  nz, hs_efd_2
        res OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        FCALL obj_var4_clear
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
hs_efd_2:
        ld  hl, 1
        ret

; UNIT 34 pick.up ($043FE0): a carrier with nothing aboard takes what
; targetMove names.  From a structure in state 2 the unit docked in it,
; then flies it back to where it was before (targetPreLast) - or, for a
; computer Harvester that remembers nowhere, to spice within 32 of the
; carrier (noSpiceFound set if none; not searched again while it is set);
; -> 1.  Or a unit on the map: lifted off and taken to a free Refinery (a
; Harvester) or Repair Facility (anything else) of its side, claimed for
; it; -> 0.  S5 port: the nearest free Refinery - the cartridge takes the
; first ($04421A, its best distance never kept).
ef_u_pick_up:
        call hs_ef_object
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  nz, hs_efd_no
        ld  a, (ix + U_TARGETMOVE + 1)
        and $C0
        cp  $40
        jp  z, hs_epu_unit
        cp  $80
        jp  nz, hs_efd_no
        ; out of a structure
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        call hs_ref_struct
        jp  z, hs_efd_refused
        push hl
        pop iy
        ld  a, (iy + S_STATE + 1)
        or  a
        jp  nz, hs_efd_refused
        ld  a, (iy + S_STATE)
        cp  2
        jp  nz, hs_efd_refused
        set OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        push iy
        FCALL obj_var4_clear
        pop iy
        xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, (iy + O_LINKED)
        ld  (ix + O_LINKED), a
        call unit_ptr
        ld  (hs_efd_cargo), hl
        push hl
        ld  de, U_SHOWN         ; off the pad (c_spr_hide $044072)
        add hl, de
        ld  (hl), 0
        pop hl
        inc hl
        inc hl
        inc hl
        ld  a, (hl)             ; the cargo's own chain stays in the dock
        ld  (iy + O_LINKED), a
        ld  (hl), $FF
        cp  $FF
        jr  nz, hs_epu_1
        xor a
        call hs_set_state_iy
hs_epu_1:
        ld  iy, (hs_efd_cargo)
        ld  a, (iy + U_PRELAST_Y)
        or  (iy + U_PRELAST_Y + 1)
        or  (iy + U_PRELAST_X)
        or  (iy + U_PRELAST_X + 1)
        jr  z, hs_epu_2
        ; back where it came from
        push iy
        pop hl
        ld  de, U_PRELAST_Y
        add hl, de
        call pos_square
        call ref_make_square
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        jr  hs_epu_3
hs_epu_2:
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, hs_epu_3
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  z, hs_epu_3
        xor a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        bit 5, (ix + O_FLAGS2)  ; noSpiceFound
        jr  nz, hs_epu_3
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  a, $20
        ld  c, (ix + O_INDEX)
        call hs_find_spice
        ld  a, h
        or  l
        jr  z, hs_epu_nospice
        call ref_make_square
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        jr  hs_epu_3
hs_epu_nospice:
        set 5, (ix + O_FLAGS2)
hs_epu_3:
        ld  a, 2
        FCALL unit_update_map
        ld  hl, 1
        ret

hs_epu_unit:
        ld  l, (ix + U_TARGETMOVE)
        ld  h, (ix + U_TARGETMOVE + 1)
        call hs_ref_unit
        jp  z, hs_efd_no
        ld  (hs_efd_cargo), hl
        push hl
        pop iy                  ; IY = the unit to lift
        ld  a, (unit_selected)
        cp  (iy + O_INDEX)
        jr  nz, hs_epu_u1
        ld  a, $FF
        ld  (unit_selected), a
hs_epu_u1:
        bit OF_ALLOCATED, (iy + O_FLAGS)
        jp  z, hs_efd_no
        ; the nearest free Refinery or Repair Facility of the carrier's side
        ld  a, STRUCT_REFINERY
        ld  b, (iy + O_TYPE)
        ld  c, a
        ld  a, b
        cp  UNIT_HARVESTER
        jr  z, hs_epu_u2
        ld  c, STRUCT_REPAIR
hs_epu_u2:
        ld  a, c
        ld  (hs_epu_type), a
        ld  a, $FF
        ld  (hs_epu_best), a
        ld  hl, 0
        ld  (hs_epu_bestd), hl
        ld  b, (ix + O_HOUSE)
        ld  a, (player_house)
        ld  c, a
        call house_are_allied
        xor 1                   ; 0 the player's side, 1 the rest
        ld  e, a
        ld  d, 0
        ld  hl, struct_head
        add hl, de
        ld  a, (hl)
hs_epu_l:
        cp  $FF
        jr  z, hs_epu_found
        ld  (hs_epu_s), a
        call struct_ptr
        push hl
        pop iy
        ld  a, (hs_epu_type)
        cp  (iy + O_TYPE)
        jr  nz, hs_epu_n
        ld  a, (iy + S_STATE)
        or  (iy + S_STATE + 1)
        jr  nz, hs_epu_n
        ld  a, (iy + HS_VAR4)
        or  (iy + HS_VAR4 + 1)
        jr  nz, hs_epu_n
        ; tile_distance_squares
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        push ix
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call tile_distance
        ld  de, $80
        add hl, de
        ld  l, h
        ld  h, 0
        ld  a, (hs_epu_best)
        cp  $FF
        jr  z, hs_epu_take
        ld  de, (hs_epu_bestd)
        push hl
        or  a
        sbc hl, de
        pop hl
        jr  nc, hs_epu_n
hs_epu_take:
        ld  (hs_epu_bestd), hl
        ld  a, (hs_epu_s)
        ld  (hs_epu_best), a
hs_epu_n:
        ld  a, (hs_epu_s)
        ld  e, a
        ld  d, 0
        ld  hl, struct_lnext
        add hl, de
        ld  a, (hl)
        jr  hs_epu_l
hs_epu_found:
        ld  a, (hs_epu_best)
        cp  $FF
        jp  z, hs_efd_no
        ; lift it
        ld  iy, (hs_efd_cargo)
        ld  a, (unit_selected)
        cp  (iy + O_INDEX)
        jr  nz, hs_epu_f1
        ld  a, $FF
        ld  (unit_selected), a
hs_epu_f1:
        ld  a, (iy + O_INDEX)
        ld  (ix + O_LINKED), a
        set OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        push ix
        ld  ix, (hs_efd_cargo)
        xor a
        FCALL unit_update_map
        call hs_take_off_map
        pop ix
        ; claimed: the carrier and the structure linked
        ld  e, (ix + O_INDEX)
        ld  d, REF_UNIT >> 8
        ld  a, (hs_epu_best)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        call hs_var4_link
        ld  a, (ix + HS_VAR4)
        ld  (ix + U_TARGETMOVE), a
        ld  a, (ix + HS_VAR4 + 1)
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, 2
        FCALL unit_update_map
        ; a Harvester with no spice near forgets where it was
        ld  iy, (hs_efd_cargo)
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jp  nz, hs_efd_no
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square         ; (its position is -1 now: square $FFF, as the
        ld  a, 4                ; cartridge reads it after taking it off)
        ld  c, (iy + O_INDEX)
        call hs_find_spice
        ld  a, h
        or  l
        jp  nz, hs_efd_no
        ld  iy, (hs_efd_cargo)
        ld  b, 8
        push iy
        pop hl
        ld  de, U_PRELAST_Y
        add hl, de
hs_epu_z:
        ld  (hl), 0
        inc hl
        djnz hs_epu_z
        jp  hs_efd_no

; map_find_spice ($01A146): HL = a square, A = the radius, C = the unit's
; slot -> HL = a square with spice or 0.  STRUCT's (S5); 0 while it has
; none.
hs_find_spice:
    IF EXIST map_find_spice
        push ix
        push iy
        FCALL map_find_spice
        pop iy
        pop ix
    ELSE
        ld  hl, 0
    ENDIF
        ret

; UNIT 35 call.unit ($045912): send for a unit of type n (a Carryall) to
; fetch this one.  What the unit has claimed already is the answer;
; otherwise, if the type can be carried (+$0C bit 8) and it is not
; deviated, a unit of that type of its house carrying nothing and going
; nowhere is claimed (unit_summon_idle $04875A, never creating one),
; linked to it and sent for it.  -> HL = a reference to it, or 0.
ef_u_call_unit:
        call hs_ef_arg0
        ld  a, l
        ld  (hs_cu_type), a
        call hs_ef_object
        ld  l, (ix + HS_VAR4)
        ld  h, (ix + HS_VAR4 + 1)
        ld  a, h
        or  l
        ret nz
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_objectFlags + 1
        add hl, de
        bit 0, (hl)
        jr  z, hs_cu_no
        ld  a, (ix + U_DEVIATED)
        or  a
        jr  nz, hs_cu_no
        ; unit_summon_idle(type, house, me, 0)
        ld  hl, hs_search
        ld  b, (ix + O_HOUSE)
        ld  a, (hs_cu_type)
        ld  c, a
        FCALL unit_find_first
hs_cu_l:
        jr  z, hs_cu_no
        push hl
        pop iy
        ld  a, (iy + O_LINKED)
        cp  $FF
        jr  nz, hs_cu_n
        ld  a, (iy + U_TARGETMOVE)
        or  (iy + U_TARGETMOVE + 1)
        jr  z, hs_cu_found
hs_cu_n:
        ld  hl, hs_search
        FCALL unit_find_next
        jr  hs_cu_l
hs_cu_found:
        ld  e, (ix + O_INDEX)
        ld  d, REF_UNIT >> 8
        ld  (iy + U_TARGETMOVE), e
        ld  (iy + U_TARGETMOVE + 1), d
        push ix
        push iy
        pop ix
        ex  de, hl
        FCALL obj_var4_set      ; the Carryall claims me
        pop ix
        ; obj_var4_link(me, it), and it is sent for me
        ld  e, (ix + O_INDEX)
        ld  d, REF_UNIT >> 8
        ld  l, (iy + O_INDEX)
        ld  h, REF_UNIT >> 8
        push hl
        push de
        call hs_var4_link
        pop de
        pop hl
        ld  (iy + U_TARGETMOVE), e
        ld  (iy + U_TARGETMOVE + 1), d
        ret
hs_cu_no:
        ld  hl, 0
        ret

; UNIT 36 dismiss ($0459D8): if what the unit has claimed is a Carryall,
; the Carryall goes nowhere and the claim is broken.
ef_u_dismiss:
        call hs_ef_object
        ld  l, (ix + HS_VAR4)
        ld  h, (ix + HS_VAR4 + 1)
        call hs_ref_unit
        jr  z, hs_cu_no
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        or  a
        jr  nz, hs_cu_no
        ld  (iy + U_TARGETMOVE), a
        ld  (iy + U_TARGETMOVE + 1), a
        FCALL obj_var4_clear
        jr  hs_cu_no

; UNIT 40 unfog ($045A8A, unit_unfog_around $04870A): the fog lifts round
; one of the player's units on the map, as far as its type's sight.
ef_u_unfog:
        call hs_ef_object
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  nz, hs_cu_no
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, hs_cu_no
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_sight
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  z, hs_cu_no
        dec hl
        ld  c, (hl)
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        FCALL map_unfog_radius
        jr  hs_cu_no

; UNIT 44 linked.type ($0112C4): the type of what I carry, or -1.
ef_u_linked_type:
        call hs_ef_object
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, hs_elt_none
        call unit_ptr
        inc hl
        inc hl
        ld  l, (hl)
        ld  h, 0
        ret
hs_elt_none:
        ld  hl, $FFFF
        ret

; UNIT 45 kind ($011292): the reference's kind 1-3, or -1 if it is stale.
ef_u_kind:
        call hs_ef_arg0
        push hl
        call ref_is_valid
        pop hl
        or  a
        jr  z, hs_elt_none
        ld  a, h
        rlca
        rlca
        and 3
        ld  l, a
        ld  h, 0
        ret

; UNIT 50 count ($011212): how many units of type n my house has (the
; search's rule: off the map not counted).
ef_u_count:
        call hs_ef_arg0
        ld  c, l
        call hs_ef_object
        ld  b, (ix + O_HOUSE)
        ld  hl, hs_search
        FCALL unit_find_first
        ld  bc, 0
hs_ec_l:
        jr  z, hs_ec_x
        inc bc
        push bc
        ld  hl, hs_search
        FCALL unit_find_next
        pop bc
        jr  hs_ec_l
hs_ec_x:
        ld  h, b
        ld  l, c
        ret

; ============================================================ 32-bit helpers

; Copy the clock into hs_now (the interrupt counts it).
hs_clock:
        di
        ld  hl, (timer_game)
        ld  (hs_now), hl
        ld  hl, (timer_game + 2)
        ld  (hs_now + 2), hl
        ei
        ret

; HL -> a due time: carry clear if hs_now >= it (the timer fires).  Keeps
; HL.
hs_due:
        ld  de, hs_now
        ex  de, hl
        call hs_cp32
        ex  de, hl
        ret

; HL -> a due time: it becomes hs_now + DE.
hs_set_due:
        push hl
        ld  bc, hs_now
        ld  a, (bc)
        add a, e
        ld  (hl), a
        inc hl
        inc bc
        ld  a, (bc)
        adc a, d
        ld  (hl), a
        inc hl
        inc bc
        ld  a, (bc)
        adc a, 0
        ld  (hl), a
        inc hl
        inc bc
        ld  a, (bc)
        adc a, 0
        ld  (hl), a
        pop hl
        ret

; HL -> a, DE -> b (32 bits, unsigned): carry if a < b, Z if equal.  Keeps
; HL, DE.  Clobbers A, BC.
hs_cp32:
        push hl
        push de
        inc hl
        inc hl
        inc hl
        inc de
        inc de
        inc de
        ld  b, 4
hs_c32_l:
        ld  a, (de)
        ld  c, a
        ld  a, (hl)
        cp  c
        jr  nz, hs_c32_x
        dec hl
        dec de
        djnz hs_c32_l
hs_c32_x:
        pop de
        pop hl
        ret

; (HL) += DE (32 bits).  Keeps HL.
hs_add32_de:
        push hl
        ld  a, (hl)
        add a, e
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, d
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, 0
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, 0
        ld  (hl), a
        pop hl
        ret

; (HL) -= (DE) (32 bits).
hs_sub32:
        ld  b, 4
        or  a
hs_s32_l:
        ld  a, (de)
        ld  c, a
        ld  a, (hl)
        sbc a, c
        ld  (hl), a
        inc hl
        inc de
        djnz hs_s32_l
        ret

; ------------------------------------------------------- the bank's own
hs_gl_house:    DB 0
hs_gl_power:    DB 0
hs_gl_starport: DB 0
hs_gl_reinf:    DB 0
hs_gl_missile:  DB 0
hs_gl_i:        DB 0
hs_gl_h:        DB 0
hs_gl_tmp:      DS 4
hs_gl_1000:     DD 1000
hs_st_frigate:  DW 0
hs_rf_carryall: DW 0
hs_rf_rec:      DW 0
hs_rf_n:        DB 0
hs_rf_unit:     DW 0
hs_rf_square:   DW 0
hs_eh_house:    DB 0
hs_ud_type:     DB 0
hs_ud_house:    DB 0
hs_ud_dest:     DW 0
hs_ud_kind:     DB 0
hs_ud_facing:   DB 0
hs_ud_unit:     DW 0
hs_sb_house:    DB 0
hs_sb_bits:     DB 0
hs_sb_info:     DW 0
hs_uu_i:        DB 0
hs_uu_h:        DB 0
hs_uu_b:        DB 0
hs_ua_house:    DB 0
hs_sd_ref:      DW 0
hs_sd_sq:       DW 0
hs_vl_from:     DW 0
hs_vl_to:       DW 0
hs_vl_a2:       DW 0
hs_vl_a3:       DW 0
hs_efd_cargo:   DW 0
hs_epu_type:    DB 0
hs_epu_best:    DB 0
hs_epu_bestd:   DW 0
hs_epu_s:       DB 0
hs_cu_type:     DB 0
