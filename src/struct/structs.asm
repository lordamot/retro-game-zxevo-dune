; structs.asm - bank STRUCT: the structure loop, making and placing
; structures, the map animations, power, and the BUILD.EMC routines
; (S1 "Structures", S5, S6, S8).  The rest of the subsystem - what a
; factory offers and builds, the Starport, spice and harvesting, docking,
; destruction - is in structs2.asm (bank STRUCT2).  Owner: the STRUCT
; subsystem (.claude/docs/port-code.md).
;
; Addresses in the comments are the Mega Drive cartridge's.  Word flag
; bits are named as the specs name them; in the port a word's bit n is
; bit n of byte +k (n < 8) or bit n-8 of byte +k+1.

; flags (+$04) and flags2 (+$06) bits used here, as (byte, bit)
st_SF_ALLOC_B      EQU O_FLAGS         ; bit 1 allocated
st_SF_DEGRADES     EQU 2               ; +5: bit 10
st_SF_REPAIRING    EQU 5               ; +5: bit 13
st_SF_ONHOLD       EQU 6               ; +5: bit 14
st_S2_UPGRADING    EQU 1               ; +6: bit 1
st_S2_MARKED       EQU 4               ; +6: bit 4 the house marker is drawn
st_S2_TARGET       EQU 7               ; +6: bit 7 a turret has a target / the Palace is ready
st_S2_NOROOM       EQU 0               ; +7: bit 8 no room for what it makes
st_S2_DONE         EQU 5               ; +7: bit 13 finished and announced
st_S2_RUNNING      EQU 6               ; +7: bit 14 (the panel's) production running

st_MK_POWER        EQU 0               ; the structure markers' flags ($FFC868)
st_MK_READY        EQU 1
st_MK_REPAIR       EQU 2

st_TURRET_ICON     EQU $114            ; ICON.MAP group 23 entry 2
st_RTURRET_ICON    EQU $11C            ; group 24 entry 2
st_TURRET_ANIM     EQU $165            ; group 23/24 entry 1: +$4E at creation

; ======================================================== the loop (S1)

; struct_game_loop ($00BCD8): the structures.  The four timers, then for
; every structure on the map in find order: struct_animate (every pass),
; the Palace's countdown, decay, the build tick (S6) and the script.
; Port fix (S1): a script that stops does not end the loop.
struct_game_loop:
        ld  hl, st_tk_build
        ld  de, 30
        call st_timer_due
        ld  (st_sg_build), a
        ; decay: only from campaign 2 ($00BD1A), and the timer is left
        ; alone below it
        xor a
        ld  (st_sg_decay), a
        ld  hl, st_tk_decay
        call st_timer_reached
        jr  z, st_sgl_1
        ld  a, (campaign_id)
        cp  2
        jr  c, st_sgl_1
        ld  de, 10800
        call st_timer_set
        ld  (st_sg_decay), a
st_sgl_1:  ld  hl, st_tk_script
        ld  de, 5
        call st_timer_due
        ld  (st_sg_script), a
        ld  hl, st_tk_palace
        ld  de, 60
        call st_timer_due
        ld  (st_sg_palace), a
        xor a
        ld  (structs_player), a
        ld  (structs_other), a
        ld  hl, st_sg_state
        ld  bc, $FFFF
        call st_sfind_first
st_sgl_loop:
        ret z
        call st_struct_animate
        ld  a, (st_sg_palace)
        or  a
        call nz, st_sg_palace_tick
        ld  a, (st_sg_decay)
        or  a
        call nz, st_sg_decay_tick
        ld  a, (st_sg_build)
        or  a
        call nz, st_sg_build_tick
        ld  a, (st_sg_script)
        or  a
        call nz, st_sg_script_tick
        ld  hl, st_sg_state
        call st_sfind_next
        jr  st_sgl_loop

; The script ($00C556): a delay counts down, a loaded script runs three
; instructions, one that is not loaded restarts at its type's entry.  A
; turret then halves its delay ($00C5E0, Mega Drive only).
st_sg_script_tick:
        ld  a, (ix + O_DELAY)
        or  (ix + O_DELAY + 1)
        jr  z, st_sst_run
        ld  l, (ix + O_DELAY)
        ld  h, (ix + O_DELAY + 1)
        dec hl
        ld  (ix + O_DELAY), l
        ld  (ix + O_DELAY + 1), h
        ret
st_sst_run:
        push ix
        ld  de, O_SCRIPT
        add ix, de
        ld  a, (ix + SC_PC)
        or  (ix + SC_PC + 1)
        jr  z, st_sst_load
        FCALL emc_run_three
        jr  st_sst_turret
st_sst_load:
        ld  l, (ix + O_TYPE - O_SCRIPT)
        ld  h, 0
        ld  a, EMC_BUILD
        FCALL emc_start
st_sst_turret:
        pop ix
        ld  a, (ix + O_TYPE)
        cp  STRUCT_TURRET
        jr  z, st_sst_half
        cp  STRUCT_RTURRET
        ret nz
st_sst_half:
        sra (ix + O_DELAY + 1)
        rr  (ix + O_DELAY)
        ret

; The Palace ($00BDDC): +$4E counts down first; then the weapon's
; countdown (+$56) while there is room for what it makes; at 0 an Ordos
; Palace blows up a Saboteur of its house, a computer house fires, and
; flags2 bit 7 says the weapon is ready.
st_sg_palace_tick:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        ret nz
        ld  l, (ix + S_ROTSPRITEDIFF)
        ld  h, (ix + S_ROTSPRITEDIFF + 1)
        ld  a, h
        or  l
        jr  z, st_spt_1
        dec hl
        ld  (ix + S_ROTSPRITEDIFF), l
        ld  (ix + S_ROTSPRITEDIFF + 1), h
        ret
st_spt_1:  ld  l, (ix + S_COUNTDOWN)
        ld  h, (ix + S_COUNTDOWN + 1)
        ld  a, h
        or  l
        jr  z, st_spt_2
        bit st_S2_NOROOM, (ix + O_FLAGS2 + 1)
        jr  nz, st_spt_2
        dec hl
        ld  (ix + S_COUNTDOWN), l
        ld  (ix + S_COUNTDOWN + 1), h
st_spt_2:  ld  a, h
        or  l
        ret nz
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_spt_3
        ; unit_find_first(house 2, type 6)
        ld  b, HOUSE_ORDOS
        ld  c, UNIT_SABOTEUR
        call st_ufind_one
        jr  z, st_spt_3
        push ix
        push hl
        pop ix
        ld  de, arg_pos
        push ix
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        ld  bc, 4
        ldir
        ld  a, 4
        ld  hl, 500
        ld  de, 0
        FCALL map_make_explosion
        FCALL unit_remove
        pop ix
st_spt_3:  ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_FLAGS
        add hl, de
        ld  a, (hl)
        and $0A
        cp  $08
        jr  nz, st_spt_4
        FCALL struct_activate_special
st_spt_4:  set st_S2_TARGET, (ix + O_FLAGS2)
        ret

; Decay ($00BE6C): a structure that degrades and has more than half its
; hit points loses its house's degradingAmount plus one ($00BEA8: the
; flag tested twice - kept, S1).
st_sg_decay_tick:
        bit st_SF_DEGRADES, (ix + O_FLAGS + 1)
        ret z
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        sra d
        rr  e                   ; type.hp / 2
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ex  de, hl
        or  a
        sbc hl, de              ; half - hp
        jp  p, st_spt_nodecay      ; half >= hp: nothing
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_degradingAmount
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        inc hl
        FCALL struct_damage
st_spt_nodecay:
        ret

; --------------------------------------------------- struct_animate
;
; struct_animate ($00D656), every pass of the loop: a turret idles; a
; Refinery or Starport steps its lights; every other structure keeps its
; house marker; a Construction Yard or Heavy Factory checks its choice
; ($00DEA0); the counts of live structures, and for the player's the
; "no room" bit (flags2 bit 8).
st_struct_animate:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_SLAB4 + 1
        ret c
        cp  STRUCT_WALL
        ret z
        cp  STRUCT_TURRET
        jp  z, st_sa_turret
        cp  STRUCT_RTURRET
        jp  z, st_sa_turret
        cp  STRUCT_STARPORT
        call z, st_sa_lights
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REFINERY
        call z, st_sa_lights
        call st_sa_marker
        ; $00DEA0 for a Construction Yard or Heavy Factory
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  z, st_sa_choice
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_sa_count
st_sa_choice:
        FCALL struct_check_build_choice
st_sa_count:
        ; the counts ($00DC3E): the player's with hit points, the rest
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  nz, st_sa_other
        ld  a, (ix + O_HP)
        or  (ix + O_HP + 1)
        jp  z, st_sa_other
        ld  hl, structs_player
        inc (hl)
        res st_S2_NOROOM, (ix + O_FLAGS2 + 1)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        jp  z, st_sa_palace
        cp  STRUCT_LIGHTFACTORY
        jp  z, st_sa_factory
        cp  STRUCT_HEAVYFACTORY
        jp  z, st_sa_factory
        cp  STRUCT_WOR
        jp  z, st_sa_factory
        cp  STRUCT_BARRACKS
        jp  z, st_sa_factory
        cp  STRUCT_STARPORT
        jp  z, st_sa_factory
        cp  STRUCT_HITECH
        jp  z, st_sa_hitech
        cp  STRUCT_WINDTRAP
        jp  z, st_sa_windtrap
        cp  STRUCT_CONSTYARD
        ret nz
        ld  a, (struct_slots_free)
        or  a
        call z, st_sa_noroom
        ; the Yard's marker ($00DCA6): 'OK' while its building waits and
        ; it is not the structure selected (flags2 bit 15), else the
        ; hammer while it is repaired, else none
        ld  a, (struct_selected)
        cp  (ix + O_INDEX)
        jr  z, st_sa_rep
        bit st_S2_DONE, (ix + O_FLAGS2 + 1)
        jr  z, st_sa_rep
        jr  st_sa_ready
st_sa_palace:
        ; an Atreides Palace with no ground slot for its Fremen
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ATREIDES
        jr  nz, st_sa_pal1
        ld  a, (ground_slots_full)
        or  a
        call nz, st_sa_noroom
st_sa_pal1:
        ; the Palace's marker ($00DD10): 'OK' while its weapon is ready
        ; (countDown 0), not armed and not held back, else as the Yard's
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        jr  nz, st_sa_rep
        ld  a, (special_armed)
        or  a
        jr  nz, st_sa_rep
        bit st_S2_NOROOM, (ix + O_FLAGS2 + 1)
        jr  nz, st_sa_rep
st_sa_ready:
        ld  a, st_MK_READY
        jp  struct_marker_set
st_sa_rep:
        ld  a, st_MK_REPAIR
        bit st_SF_REPAIRING, (ix + O_FLAGS + 1)
        jp  nz, struct_marker_set
        ld  a, st_MK_READY
        jp  struct_marker_clear
st_sa_windtrap:
        ; a Windtrap's ($00DD66), unless it is repaired: the bolt while its
        ; house uses more power than it makes
        bit st_SF_REPAIRING, (ix + O_FLAGS + 1)
        ret nz
        bit OF_ALLOCATED, (ix + O_FLAGS)
        jr  z, st_sa_wt0
        ld  a, (player_house)
        call house_ptr
        ld  de, H_POWERPROD
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; HL = used, DE = made
        ex  de, hl
        or  a
        sbc hl, de              ; made - used
        jp  p, st_sa_wt0
        ld  a, st_MK_POWER
        jp  struct_marker_set
st_sa_wt0:
        ld  a, st_MK_POWER
        jp  struct_marker_clear
st_sa_factory:
        ld  a, (ground_slots_full)
        or  a
        jr  nz, st_sa_fac1
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_UNITCOUNT
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; HL = the cap
        ex  de, hl
        or  a
        sbc hl, de              ; count - cap
        ret c
st_sa_fac1:
        bit st_S2_UPGRADING, (ix + O_FLAGS2)
        ret nz
        jr  st_sa_noroom
st_sa_hitech:
        ld  a, (air_slot_free)
        or  a
        ret nz
        bit st_S2_UPGRADING, (ix + O_FLAGS2)
        ret nz
st_sa_noroom:
        set st_S2_NOROOM, (ix + O_FLAGS2 + 1)
        ret
st_sa_other:
        ld  hl, structs_other
        inc (hl)
        ret

; ------------------------------------------------------------ the markers
;
; A structure has one marker sprite at most (+$10) and three flags
; ($FFC868 + its index; st_markers here): 0 the low-power bolt
; (struct_marker_set_bit0 $009AD6), 1 'OK' ($009A62), 2 the repair hammer
; ($009B26).  Setting a flag points the sprite at its picture, making it
; if there is none; clearing a flag that was set frees the sprite,
; whatever it showed ($009A38) - struct_animate puts back what should
; still show on the next pass.  The picture's place is by the structure's
; layout, which is the frame every caller passes (its type's +$3C), so
; the renderer works it out.

; struct_marker_set: IX = a structure, A = the flag (st_MK_*).
; Clobbers A, BC, D, HL.
struct_marker_set:
        ld  c, a
        inc a
        add a, a
        add a, a
        add a, a
        add a, a
        ld  d, a                ; the picture, in bits 4-5
        ld  a, c
        call st_mk_mask
        ld  a, (hl)
        and $0F
        or  b
        or  d
        ld  (hl), a
        ret

; struct_marker_clear: IX = a structure, A = the flag.  Clobbers A, B, HL.
struct_marker_clear:
        call st_mk_mask
        ld  a, (hl)
        and b
        ret z                   ; not set: the sprite stays
        ld  a, b
        cpl
        and (hl)
        and $0F                 ; the sprite freed
        ld  (hl), a
        ret

; A = a flag, IX = a structure -> B = the flag's mask, HL -> its byte.
st_mk_mask:
        ld  b, 1
        or  a
        jr  z, st_mkm_1
        ld  b, 2
        dec a
        jr  z, st_mkm_1
        ld  b, 4
st_mkm_1:  push de
        ld  e, (ix + O_INDEX)
        ld  d, 0
        ld  hl, st_markers
        add hl, de
        pop de
        ret

; An idle turret ($00D6A4): every random(100..125) frames its facing
; moves an eighth at random; the facing is the ground icon.  Not while
; it has a target.
st_sa_turret:
        bit st_S2_TARGET, (ix + O_FLAGS2)
        ret nz
        ld  a, (frames_this_pass)
        ld  b, a
        ld  a, (ix + S_TURRETFACING)
        sub b
        ld  (ix + S_TURRETFACING), a
        jr  z, st_sat_go
        ret p                   ; still positive
st_sat_go: call st_square
        push hl
        ld  bc, st_TURRET_ICON
        ld  a, (ix + O_TYPE)
        cp  STRUCT_RTURRET
        jr  nz, st_sat_1
        ld  bc, st_RTURRET_ICON
st_sat_1:  push bc
        call map_ground_icon    ; HL = the icon
        pop bc
        or  a
        sbc hl, bc              ; the facing
        ld  d, 0
        ld  e, 2
        call rand_between
        dec a
        add a, l
        and 7
        ld  l, a
        ld  h, 0
        add hl, bc
        ex  de, hl
        pop hl
        call st_set_ground
        ld  d, 100
        ld  e, 125
        call rand_between
        ld  (ix + S_TURRETFACING), a
        ret

; The lights of a Refinery or Starport ($00D77A): while it is busy (state
; 1) - and on until back at frame 0 - every 20 frames the next of four
; frames goes on its light squares; a square half in the fog has the fog
; lifted round it.  The first time, the timer is random(72..84).
st_sa_lights:
        ld  a, (ix + O_INDEX)
        cp  STRUCT_COUNT
        ret nc
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, st_lt_timer
        add hl, de              ; HL -> timer, frame
        bit 7, (ix + S_TURRETFACING)
        jr  z, st_sal_1
        ld  d, 72
        ld  e, 84
        call rand_between
        ld  (hl), a
st_sal_1:  ld  a, (ix + S_STATE)
        dec a
        or  (ix + S_STATE + 1)
        jr  z, st_sal_2            ; state 1
        inc hl
        ld  a, (hl)
        dec hl
        or  a
        ret z
st_sal_2:  ld  a, (frames_this_pass)
        ld  b, a
        ld  a, (hl)
        sub b
        ld  (hl), a
        jr  z, st_sal_3
        ret p
st_sal_3:  ld  (hl), 20
        inc hl
        ld  a, (hl)
        inc a
        and 3
        ld  (hl), a
        ld  (st_sal_frame), a
        call st_square
        ld  (st_sal_sq), hl
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REFINERY
        ld  hl, st_sal_ref
        ld  b, 2
        jr  z, st_sal_4
        ld  hl, st_sal_port
        ld  b, 4
st_sal_4:  push bc
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; the square's offset
        inc hl
        ld  c, (hl)             ; the icon set
        inc hl
        push hl
        ld  hl, (st_sal_sq)
        add hl, de
        push hl
        ; icon = set[c][frame]
        ld  a, (st_sal_frame)
        add a, a
        ld  l, c
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; *16
        ld  e, a
        ld  d, 0
        add hl, de
        ld  de, tbl_struct_icon_sets
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop hl
        call st_set_ground
        call st_sq_unfog_if_half
        pop hl
        pop bc
        djnz st_sal_4
        ret
st_sal_ref:        DW 2
                DB 0
                DW 66
                DB 1
st_sal_port:       DW 65
                DB 2
                DW 66
                DB 3
                DW 130
                DB 5
                DW 129
                DB 4

; HL = a square: if its overlay is 1 - $7A (a fog edge, a crater...), lift
; the fog one square round its centre.  Keeps nothing.
st_sq_unfog_if_half:
        push hl
        call map_overlay_icon
        pop hl
        or  a
        ret z
        cp  st_VEILED_ICON
        ret nc
st_sq_unfog1:
        ld  de, arg_pos
        call square_centre
        ld  hl, arg_pos
        ld  c, 1
        FCALL map_unfog_radius
        ret

; The house marker ($00DB1A): every 7 frames (the first time after
; random(67..81)) the marker square - the bottom row's left square - is
; looked at.  The player's structures are marked at once; another house's
; only when that square is not under the full fog, and one half in the
; fog lifts it round the square first.  Marking puts overlay $16 + house
; on the square once (flags2 bit 4); +$0F steps the orb's frame.
st_sa_marker:
        ld  a, (ix + O_INDEX)
        cp  STRUCT_COUNT
        ret nc
        ld  e, a
        ld  d, 0
        ld  hl, st_mk_timer
        add hl, de
        bit 7, (ix + S_TURRETFACING)
        jr  z, st_sam_1
        ld  (ix + S_TURRETFACING), 1
        ld  d, 67
        ld  e, 81
        call rand_between
        ld  (hl), a
st_sam_1:  ld  a, (frames_this_pass)
        ld  b, a
        ld  a, (hl)
        sub b
        ld  (hl), a
        jr  z, st_sam_2
        ret p
st_sam_2:  ld  (hl), 7
        call st_marker_square   ; HL = the square
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_sam_draw
        push hl
        call map_overlay_icon
        pop hl
        cp  st_VEILED_ICON
        ret nc
        or  a
        jr  z, st_sam_draw
        push hl
        call st_sq_unfog1
        pop hl
st_sam_draw:
        bit st_S2_MARKED, (ix + O_FLAGS2)
        jr  nz, st_sam_3
        set st_S2_MARKED, (ix + O_FLAGS2)
        ld  a, (ix + O_HOUSE)
        add a, $16
        call st_set_overlay
st_sam_3:  ld  a, (ix + S_TURRETFACING)
        inc a
        and 7
        ld  (ix + S_TURRETFACING), a
        ret

; IX = a structure -> HL = its marker square: the position's square plus
; $06B9FC[layout] (0, 0, 64, 64, 128, 64, 128).
st_marker_square:
        call st_layout
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_struct_pos_offsets
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        call st_square
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ret

; ------------------------------------------------ the build tick (S6)
;
; $00BEC0-$00C556: upgrading, else repairing, else producing and the
; Repair Facility, then the computer's upkeep.
st_sg_build_tick:
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        pop iy                  ; IY = the house
        bit st_S2_UPGRADING, (ix + O_FLAGS2)
        jp  nz, st_bt_upgrade
        bit st_SF_REPAIRING, (ix + O_FLAGS + 1)
        jp  nz, st_bt_repair
        ; C. producing ($00C104)
        bit st_SF_ONHOLD, (ix + O_FLAGS + 1)
        jp  nz, st_bt_resume
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        jp  z, st_bt_resume
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_bt_resume
        ld  a, (ix + S_STATE)
        dec a
        or  (ix + S_STATE + 1)
        jp  nz, st_bt_resume
        call st_info
        ld  de, SI_flags
        add hl, de
        bit 1, (hl)
        jp  z, st_bt_resume
        ; the object's record: a structure's for a Yard, else a unit's
        ld  a, (ix + O_LINKED)
        call st_linked_info     ; HL = the object's type record
        push hl
        call st_speed           ; DE = the speed
        ; the computer is capped at campaign * 20 + 95 ($00C1D4)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_bt_c1
        ld  a, (campaign_id)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        push hl
        add hl, hl
        add hl, hl
        pop bc
        add hl, bc              ; *20
        ld  bc, 95
        add hl, bc
        ; speed >= cap -> cap (the speed is at most 256, the cap positive)
        push hl
        ex  de, hl
        or  a
        sbc hl, de
        pop de
        jr  nc, st_bt_c1           ; speed >= cap: DE = cap
        add hl, de              ; back to the speed
        ex  de, hl
st_bt_c1:  ld  (st_bt_speed), de
        pop hl                  ; the object's record
        ld  de, UI_buildCredits ; the same offsets in both tables
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; the cost
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; the time
        call div_shl8           ; credits * 256 / time
        ld  de, (st_bt_speed)
        ld  a, d
        dec a
        or  e
        jr  z, st_bt_c2            ; full speed
        call mul_shr8
st_bt_c2:  ld  e, (ix + S_COSTREM)
        ld  d, (ix + S_COSTREM + 1)
        add hl, de              ; cost += the remainder
        ld  (st_bt_cost), hl
        ld  e, h
        ld  d, 0                ; pay = cost >> 8
        ; a house with some credits pays what it has when that is not
        ; more than the step ($00C23A; pay == credits is the same either
        ; way)
        call st_cr_zero
        jr  z, st_bt_c3
        call st_cr_lt              ; credits < pay?
        jr  nc, st_bt_c4
        ld  e, (iy + H_CREDITS)
        ld  d, (iy + H_CREDITS + 1)
        jr  st_bt_c4
st_bt_c3:  ld  a, e
        or  a
        jr  z, st_bt_c4
        ; pay > credits = 0 ($00C252): the player's goes on hold
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  nz, st_bt_repairfac
        set st_SF_ONHOLD, (ix + O_FLAGS + 1)
        jp  st_bt_repairfac
st_bt_c4:  ld  a, (st_bt_cost)
        ld  (ix + S_COSTREM), a
        ld  (ix + S_COSTREM + 1), 0
        call st_cr_sub
        call st_paid_add
        ; countDown = speed > countDown ? 0 : countDown - speed
        ld  l, (ix + S_COUNTDOWN)
        ld  h, (ix + S_COUNTDOWN + 1)
        ld  de, (st_bt_speed)
        or  a
        sbc hl, de
        jr  nc, st_bt_c5
        ld  hl, 0
st_bt_c5:  ld  (ix + S_COUNTDOWN), l
        ld  (ix + S_COUNTDOWN + 1), h
        ld  a, h
        or  l
        jp  nz, st_bt_repairfac
        ; done
        ld  (ix + S_COSTREM), 0
        ld  (ix + S_COSTREM + 1), 0
        ld  a, 2
        call struct_set_state
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_bt_ai_done
        ld  a, (ix + O_TYPE)
        cp  STRUCT_BARRACKS
        jp  z, st_bt_repairfac
        cp  STRUCT_WOR
        jp  z, st_bt_repairfac
        set st_S2_DONE, (ix + O_FLAGS2 + 1)
        xor a
        FCALL snd_voice
        jp  st_bt_repairfac
st_bt_ai_done:
        ; a computer Construction Yard puts its building down at once
        ; ($00C2E2): where one of the house's five lost ones stood
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jp  nz, st_bt_repairfac
        ld  a, (ix + O_LINKED)
        ld  (ix + O_LINKED), $FF
        push af
        xor a
        call struct_set_state
        pop af
        push ix
        call struct_ptr
        push hl
        pop ix                  ; IX = the building
        push iy
        pop hl
        ld  de, H_REBUILD
        add hl, de
        ld  b, 5
st_bt_rb:  push bc
        push hl
        ld  a, (hl)
        cp  (ix + O_TYPE)
        jr  nz, st_bt_rb1
        inc hl
        ld  a, (hl)
        or  a
        jr  nz, st_bt_rb1
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        push iy
        call struct_place
        pop iy
        jr  z, st_bt_rb1
        pop hl
        pop bc
        xor a
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
        ld  (ix + O_SEEN), $FF
        pop ix
        jp  st_bt_repairfac
st_bt_rb1: pop hl
        inc hl
        inc hl
        inc hl
        inc hl
        pop bc
        djnz st_bt_rb
        ; nowhere: its price back, and it goes
        call st_info
        ld  de, SI_buildCredits
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        call st_cr_add
        FCALL struct_free
        pop ix
        jp  st_bt_repairfac

; not producing: a structure on hold resumes as soon as its house has
; credits ($00C3A8)
st_bt_resume:
        call st_cr_zero
        jr  z, st_bt_repairfac
        res st_SF_ONHOLD, (ix + O_FLAGS + 1)
        ; fall through

; D. the Repair Facility ($00C3B4)
st_bt_repairfac:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REPAIR
        jp  nz, st_bt_upkeep
        bit st_SF_ONHOLD, (ix + O_FLAGS + 1)
        jr  z, st_bt_rf1
        call st_cr_zero
        jp  z, st_bt_upkeep
        res st_SF_ONHOLD, (ix + O_FLAGS + 1)
        jp  st_bt_upkeep
st_bt_rf1: ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        jp  z, st_bt_upkeep
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_bt_upkeep
        call st_speed
        ld  (st_bt_speed), de
        ld  a, (ix + O_LINKED)
        call unit_ptr
        ld  (st_bt_unit), hl
        inc hl
        inc hl
        ld  a, (hl)
        call unit_info
        ld  de, UI_buildCredits
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 2
        call mul_shr8
        ex  de, hl              ; DE = the cost
        call st_cr_lt
        jr  c, st_bt_upkeep
        call st_cr_sub
        ld  l, (ix + S_COUNTDOWN)
        ld  h, (ix + S_COUNTDOWN + 1)
        ld  de, (st_bt_speed)
        or  a
        sbc hl, de
        jr  nc, st_bt_rf2
        ld  hl, 0
st_bt_rf2: ld  (ix + S_COUNTDOWN), l
        ld  (ix + S_COUNTDOWN + 1), h
        ld  a, h
        or  l
        jr  nz, st_bt_upkeep
        ; repaired: a Harvester gets its harvest sprite back
        ld  hl, (st_bt_unit)
        inc hl
        inc hl
        ld  a, (hl)
        cp  UNIT_HARVESTER
        jr  nz, st_bt_rf3
        ld  de, U_TARGETATTACK - 2
        add hl, de
        ld  a, (ix + S_ROTSPRITEDIFF)
        ld  (hl), a
        inc hl
        ld  a, (ix + S_ROTSPRITEDIFF + 1)
        ld  (hl), a
st_bt_rf3: ld  a, 2
        call struct_set_state
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_bt_upkeep
        add a, $37
        FCALL snd_voice
        ; fall through

; E. the computer's upkeep ($00C4DC): repair below half health, else an
; idle factory picks its next build.  Port fix (S6): not the Starport.
st_bt_upkeep:
        bit HF_AIACTIVE, (iy + H_FLAGS)
        ret z
        bit 1, (ix + O_FLAGS)
        ret z
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret z
        call st_cr_zero
        ret z
        call st_info
        push hl
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        sra d
        rr  e
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        or  a
        sbc hl, de              ; hp - half
        pop hl
        jp  p, st_bt_up1
        set st_SF_REPAIRING, (ix + O_FLAGS + 1)
        ret
st_bt_up1: ld  de, SI_flags
        add hl, de
        bit 1, (hl)
        ret z
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        ret z
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        ret nz
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret nz
        FCALL struct_ai_pick_next_build
        ld  a, h
        and l
        inc a
        ret z
        FCALL struct_build_object
        ret

; A. upgrading ($00BED4): buildCredits / 20 a tick while there is money
; (it waits without); ten ticks; then the level goes up and the special
; cases ($00BF18-$00C04C).  Port fix (S6): the per-type counts follow a
; Light Factory that becomes a Heavy one and a Barracks that becomes a
; WOR.
st_bt_upgrade:
        call st_info
        ld  de, SI_buildCredits
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 20
        call sdiv16             ; HL = cost
        ex  de, hl
        call st_cr_lt
        ret c
        call st_cr_sub
        call st_paid_add
        ld  a, (ix + S_UPGRADETIME)
        sub 10
        ld  (ix + S_UPGRADETIME), a
        jr  z, st_bt_ug1
        ret p
st_bt_ug1: inc (ix + S_UPGRADELEVEL)
        res st_S2_UPGRADING, (ix + O_FLAGS2)
        ld  a, (ix + S_TYPEAFTERUPG)
        ld  (ix + S_OBJECTTYPE), a
        rla
        sbc a, a
        ld  (ix + S_OBJECTTYPE + 1), a
        ld  (ix + S_TYPEAFTERUPG), 0
        ld  a, (ix + O_TYPE)
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_bt_ug2
        ld  a, (ix + S_UPGRADELEVEL)
        cp  2
        jr  nz, st_bt_ug2
        ld  c, STRUCT_HEAVYFACTORY
        call st_bt_become
st_bt_ug2: ld  a, (ix + O_TYPE)
        cp  STRUCT_BARRACKS
        jr  nz, st_bt_ug3
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_bt_ug3
        ld  a, (ix + S_UPGRADELEVEL)
        cp  2
        jr  nz, st_bt_ug3
        ld  c, STRUCT_WOR
        call st_bt_become
st_bt_ug3: ld  a, (ix + O_HOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_bt_ug4
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_bt_ug4
        ld  a, (ix + S_UPGRADELEVEL)
        cp  2
        jr  nz, st_bt_ug4
        ld  (ix + S_UPGRADELEVEL), 3
st_bt_ug4: ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_bt_ug5
        ; no Outpost, or no Windtrap: the Rocket Turret gives way to the
        ; 4-Slab
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_OUTPOST
        call st_stc_addr
        ld  a, (hl)
        or  a
        jr  z, st_bt_ug4a
        ld  a, STRUCT_WINDTRAP
        call st_stc_addr
        ld  a, (hl)
        or  a
        jr  nz, st_bt_ug5
st_bt_ug4a:
        ld  a, (ix + S_OBJECTTYPE)
        cp  STRUCT_RTURRET
        jr  nz, st_bt_ug5
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, st_bt_ug5
        ld  (ix + S_OBJECTTYPE), STRUCT_SLAB4
st_bt_ug5: ld  a, (ix + O_TYPE)
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_bt_ug6
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_OUTPOST
        call st_stc_addr
        ld  a, (hl)
        or  a
        jr  nz, st_bt_ug6
        ld  a, (ix + O_HOUSE)
        ld  c, UNIT_TRIKE
        cp  HOUSE_ATREIDES
        jr  z, st_bt_ug5a
        ld  c, UNIT_RAIDERTRIKE
        cp  HOUSE_ORDOS
        jr  z, st_bt_ug5a
        ld  c, UNIT_QUAD
st_bt_ug5a:
        ld  (ix + S_OBJECTTYPE), c
        ld  (ix + S_OBJECTTYPE + 1), 0
        FCALL struct_offer_fix  ; one the panel offers (the port's)
st_bt_ug6: FCALL struct_is_upgradable
        or  a
        jr  z, st_bt_ug7
        ld  a, 100
st_bt_ug7: ld  (ix + S_UPGRADETIME), a
        ret

; C = the new type: IX becomes it, level 0, full health of the new type,
; its bit in structuresBuilt, and (the port's fix) the per-type counts.
st_bt_become:
        push bc
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call st_stc_addr
        dec (hl)
        pop bc
        ld  (ix + O_TYPE), c
        ld  a, c
        call st_stc_addr
        inc (hl)
        ld  (ix + S_UPGRADELEVEL), 0
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        ld  (ix + S_HPMAX), a
        ld  (ix + O_HP), a
        inc hl
        ld  a, (hl)
        ld  (ix + S_HPMAX + 1), a
        ld  (ix + O_HP + 1), a
        push iy
        pop hl
        ld  de, H_BUILT
        add hl, de
        ld  a, (ix + O_TYPE)
        jp  st_set_bit32

; B. repairing ($00C054): the Palace for nothing, anything else for
; (buildCredits * (2048 / hp) + $50) >> 8 a tick; +14 for the player,
; +6 below campaign 3 and +8 from it for the computer.  Out of money it
; stops; full, it stops too.
st_bt_repair:
        call st_info
        ld  de, 0
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        jr  z, st_bt_rp1
        push hl
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  de, 8
        call div_shl8           ; 2048 / hp
        ex  de, hl
        pop hl
        push hl
        ld  bc, SI_buildCredits
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call mul_shr8
        ex  de, hl
        pop hl
st_bt_rp1: call st_cr_lt
        jr  nc, st_bt_rp2
        res st_SF_REPAIRING, (ix + O_FLAGS + 1)
        ld  a, st_MK_REPAIR     ; ($00C0FA)
        jp  struct_marker_clear
st_bt_rp2: push hl
        call st_cr_sub
        ld  c, 14
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_bt_rp3
        ld  c, 6
        ld  a, (campaign_id)
        cp  3
        jr  c, st_bt_rp3
        ld  c, 8
st_bt_rp3: ld  a, (ix + O_HP)
        add a, c
        ld  (ix + O_HP), a
        jr  nc, st_bt_rp4
        inc (ix + O_HP + 1)
st_bt_rp4: pop hl
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        or  a
        sbc hl, de
        ret z
        ret m
        ld  (ix + O_HP), e
        ld  (ix + O_HP + 1), d
        ld  a, (ix + O_FLAGS + 1)
        and $9F
        ld  (ix + O_FLAGS + 1), a
        ld  a, st_MK_REPAIR     ; ($00C0E8)
        jp  struct_marker_clear

; IX = a structure -> DE = its speed: 256 at full health, else
; math_div_shl8(type.hp, hp).
st_speed:
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  e, (ix + O_HP)
        ld  d, (ix + O_HP + 1)
        or  a
        sbc hl, de
        jr  z, st_sts_full
        add hl, de
        call div_shl8
        ex  de, hl
        ret
st_sts_full:
        ld  de, 256
        ret

; IX = a factory, A = its linked slot -> HL = the object's type record:
; a structure's for a Construction Yard, else a unit's.
st_linked_info:
        ld  c, a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, c
        jr  nz, st_sli_unit
        call struct_ptr
        inc hl
        inc hl
        ld  a, (hl)
        jp  struct_info
st_sli_unit:
        call unit_ptr
        inc hl
        inc hl
        ld  a, (hl)
        jp  unit_info

; creditsPaid += DE
st_paid_add:
        ld  a, (ix + S_CREDITSPAID)
        add a, e
        ld  (ix + S_CREDITSPAID), a
        ld  a, (ix + S_CREDITSPAID + 1)
        adc a, d
        ld  (ix + S_CREDITSPAID + 1), a
        ret

; struct_set_state ($00FA0E): IX = a structure, A = the state (signed).
struct_set_state:
        ld  (ix + S_STATE), a
        rla
        sbc a, a
        ld  (ix + S_STATE + 1), a
        ret

; ========================================== making and placing (S2, S6)

; struct_create ($00E580): B = the slot or $FF, C = the type, D = the
; house, HL = the square or $FFFF for none.  -> HL = the structure (Z:
; none).  Allocated, counted for its house, linked; health; a turret's
; +$4E; the Harkonnen Light Factory's level; upgradeTimeLeft; the panel's
; lists (struct_build_object -2); the computer's upgrade level; placed if
; given a square (and freed again if that fails).
struct_create:
        ld  (st_sc_square), hl
        ld  a, c
        ld  (st_sc_type), a
        ld  a, d
        ld  (st_sc_house), a
        ld  a, b
        ld  b, c
        FCALL struct_allocate
        ret z
        push hl
        pop ix
        ld  a, (st_sc_house)
        ld  b, a
        ld  a, (st_sc_type)
        call st_stc_addr
        inc (hl)
        ld  a, (st_sc_house)
        ld  (ix + O_HOUSE), a
        ld  (ix + S_CREATORHOUSE), a
        ld  (ix + S_CREATORHOUSE + 1), 0
        set OF_NOTONMAP, (ix + O_FLAGS)
        xor a
        ld  (ix + O_POS_Y), a
        ld  (ix + O_POS_Y + 1), a
        ld  (ix + O_POS_X), a
        ld  (ix + O_POS_X + 1), a
        ld  (ix + O_LINKED), $FF
        ld  (ix + S_STATE), $FF
        ld  (ix + S_STATE + 1), $FF
        ld  a, (ix + O_INDEX)
        FCALL struct_list_link
        ld  a, (st_sc_type)
        cp  STRUCT_TURRET
        jr  z, st_sc_tur
        cp  STRUCT_RTURRET
        jr  nz, st_sc_0
st_sc_tur: ld  (ix + S_ROTSPRITEDIFF), st_TURRET_ANIM & $FF
        ld  (ix + S_ROTSPRITEDIFF + 1), st_TURRET_ANIM >> 8
st_sc_0:   call st_info
        push hl
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        ld  (ix + O_HP), a
        ld  (ix + S_HPMAX), a
        inc hl
        ld  a, (hl)
        ld  (ix + O_HP + 1), a
        ld  (ix + S_HPMAX + 1), a
        ; a Harkonnen Light Factory starts at level 1 ($00E644)
        ld  a, (st_sc_house)
        or  a
        jr  nz, st_sc_1
        ld  a, (st_sc_type)
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_sc_1
        ld  (ix + S_UPGRADELEVEL), 1
st_sc_1:   pop hl
        ld  de, SI_flags
        add hl, de
        bit 1, (hl)
        jr  z, st_sc_2
        FCALL struct_is_upgradable
        or  a
        jr  z, st_sc_1a
        ld  a, 100
st_sc_1a:  ld  (ix + S_UPGRADETIME), a
st_sc_2:   ld  (ix + S_OBJECTTYPE), $FF
        ld  (ix + S_OBJECTTYPE + 1), $FF
        ld  hl, -2
        FCALL struct_build_object
        ld  (ix + S_COUNTDOWN), 0
        ld  (ix + S_COUNTDOWN + 1), 0
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_sc_3
        FCALL struct_init_upgrade_level
        ld  (ix + S_UPGRADETIME), 0
st_sc_3:   ld  hl, (st_sc_square)
        ld  a, h
        and l
        inc a
        jr  z, st_sc_done
        call struct_place
        jr  nz, st_sc_done
        FCALL struct_free
        ld  hl, 0
        xor a
        ret
st_sc_done:
        push ix
        pop hl
        ld  a, h
        or  l
        ret

; struct_place ($00E6CC): IX = the structure, HL = the square.  -> A = 1
; and NZ if it went down, A = 0 and Z if not.
;   A Wall: struct_check_location, the wall icon and owner, the fog, the
;   neighbours joined; the record is freed.
;   A slab: every square of its layout that may take concrete does; the
;   record is freed if any did.
;   Anything else: checked (the player's by struct_check_location, a
;   computer's by struct_check_landscape; both pass when validate_strict),
;   put on the map with its health (less for squares off concrete, which
;   also make it degrade), seen, its script restarted, units under it
;   removed, the Windtrap count, the power recount, the Palace's weapon,
;   its squares written, the construction animation, the fog.
struct_place:
        ld  a, h
        and l
        inc a
        ret z                   ; -1: A = 0, Z
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_sp_square), hl
        ld  a, (ix + O_TYPE)
        cp  STRUCT_WALL
        jp  z, st_sp_wall
        ld  c, a
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, c
        jr  nz, st_sp_ai
        call struct_check_location
        jr  st_sp_chk
st_sp_ai:  call struct_check_landscape
st_sp_chk: ld  (st_sp_check), hl
        ld  a, h
        or  l
        jr  nz, st_sp_ok
        ld  a, (validate_strict)
        or  a
        ret z
st_sp_ok:  ld  a, (ix + O_TYPE)
        cp  STRUCT_SLAB4 + 1
        jp  c, st_sp_slab
        ; ---- a building ($00EAF0)
        res OF_NOTONMAP, (ix + O_FLAGS)
        ld  hl, (st_sp_square)
        ld  a, l
        and $3F
        ld  (ix + O_POS_X + 1), a
        ld  (ix + O_POS_X), 0
        add hl, hl
        add hl, hl
        ld  (ix + O_POS_Y + 1), h
        ld  (ix + O_POS_Y), 0
        ld  (ix + S_ROTSPRITEDIFF), 0
        ld  (ix + S_ROTSPRITEDIFF + 1), 0
        ; seen by everyone if it is the player's, else by its own house
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, st_sp_seen
        ld  a, (ix + O_HOUSE)
        call st_bit_of
        or  (ix + O_SEEN)
st_sp_seen:
        ld  (ix + O_SEEN), a
        ; health: less for squares off concrete, and it degrades
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ld  (ix + S_HPMAX), l
        ld  (ix + S_HPMAX + 1), h
        ld  de, (st_sp_check)
        bit 7, d
        jr  z, st_sp_hpok
        call neg_de             ; n
        sra h
        rr  l                   ; hp / 2
        push hl
        push de
        call st_layout_count    ; A = the squares (clobbers DE: n was
        pop de                  ; lost, and a Windtrap on rock began at 100)
        ld  l, a
        ld  h, 0
        call div_shl8           ; n * 256 / squares
        ex  de, hl
        pop hl
        call mul_shr8
        ex  de, hl
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        or  a
        sbc hl, de
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        set st_SF_DEGRADES, (ix + O_FLAGS + 1)
st_sp_hpok:
        ; the script: variables 0 and 4 cleared, restarted at its type
        ld  (ix + O_SCRIPT + SC_VARS), 0
        ld  (ix + O_SCRIPT + SC_VARS + 1), 0
        ld  (ix + O_SCRIPT + SC_VARS + 8), 0
        ld  (ix + O_SCRIPT + SC_VARS + 9), 0
        ld  (ix + O_DELAY), 0
        ld  (ix + O_DELAY + 1), 0
        push ix
        ld  l, (ix + O_TYPE)
        ld  h, 0
        ld  de, O_SCRIPT
        add ix, de
        ld  a, EMC_BUILD
        FCALL emc_start
        pop ix
        ; units standing on its squares are removed; running animations
        ; there stop
        call st_layout_first
st_sp_units:
        push bc
        push hl
        call st_layout_square   ; HL = the square
        push hl
        call map_anim_stop
        pop hl
        call st_sq_unit            ; HL = the unit or 0
        jr  z, st_sp_u1
        push ix
        push hl
        pop ix
        FCALL unit_remove
        pop ix
st_sp_u1:  pop hl
        pop bc
        inc hl
        inc hl
        djnz st_sp_units
        ; a Windtrap counts ($00EC66)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_WINDTRAP
        jr  nz, st_sp_1
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_WINDTRAPS
        add hl, de
        inc (hl)
        jr  nz, st_sp_1
        inc hl
        inc (hl)
st_sp_1:   ld  a, (validate_strict)
        or  a
        jr  nz, st_sp_2
        ld  a, (ix + O_HOUSE)
        call house_calc_power
st_sp_2:   ; the Palace's weapon ($00EC96): the Death Hand for the Harkonnen
        ; and Sardaukar, the Fremen (Troopers) for the Atreides, the
        ; Saboteur for the Ordos
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        jr  nz, st_sp_3
        ld  a, (ix + O_HOUSE)
        ld  c, UNIT_DEATHHAND
        or  a
        jr  z, st_sp_2a
        cp  HOUSE_SARDAUKAR
        jr  z, st_sp_2a
        ld  c, UNIT_TROOPERS
        cp  HOUSE_ATREIDES
        jr  z, st_sp_2a
        ld  c, UNIT_SABOTEUR
        cp  HOUSE_ORDOS
        jr  nz, st_sp_3
st_sp_2a:  ld  (ix + S_OBJECTTYPE), c
        ld  (ix + S_OBJECTTYPE + 1), 0
st_sp_3:   ; its squares: owner, the structure bit, its index and the built
        ; icons, and structuresBuilt ($00EF22, $00EDA0)
        FCALL struct_place_icons
        ; the construction animation, type +$3E, stamped over them
        call st_info
        ld  de, SI_f3E
        add hl, de
        ld  a, (hl)
        push af
        call st_layout
        ld  c, a
        pop af
        ld  hl, (st_sp_square)
        call st_map_anim_start_l
        call st_struct_unfog
        ld  a, 1
        or  a
        ret

; A Wall ($00E702).
st_sp_wall:
        ld  a, STRUCT_WALL
        call struct_check_location
        ld  a, h
        or  l
        ret z
        ld  hl, (st_sp_square)
        ld  a, (ix + O_HOUSE)
        FCALL map_place_wall
        ld  hl, (st_sp_square)  ; map_place_wall leaves HL on the west
        call st_sp_square_done  ; neighbour (its last wall_join): the
        FCALL struct_free       ; crater under the wall stayed ($00E702)
        ld  a, 1
        or  a
        ret

; HL = a square just paved or walled: the player's lift the fog one
; square round it; an unveiled square loses its overlay; an animation
; there stops.
st_sp_square_done:
        push hl
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        call z, st_sq_unfog1
        pop hl
        push hl
        call st_sq_unveiled
        pop hl
        jr  z, st_spsd_1
        xor a
        call st_set_overlay
st_spsd_1: jp  map_anim_stop

; A slab or 4-Slab ($00E87E): each square of the layout that passes
; struct_check_location(square, 0) becomes the house's concrete.  The
; layout is walked from the square being placed at (st_sp_square), not
; from the record's position: a slab waiting in the Yard has none (0, 0),
; and walking from there laid the concrete at the map's top-left corner -
; the slab "vanished" - and hung the game in the corner.
; The footprint's check has already said the slab touches the base, so
; each square is asked only whether it can take concrete - rock and
; nothing on it - with st_cl_notouch set for the moment.  Asking each
; square to touch the base by itself (as the listing at $00E87E reads:
; struct_check_location(square, 0) with nothing set) was a bug: a 4-Slab
; put down two squares from the Yard paved only the row next to it while
; its footprint showed green, and the whole slab did touch the base.
; (Skipping the touch test with validate_strict was one too: strict
; makes every landscape valid, and the slab paved mountains and sand.)
st_sp_slab:
        xor a
        ld  (st_sp_any), a
        ld  a, 1
        ld  (st_cl_notouch), a
        call st_layout
        call st_layout_tiles    ; HL -> the offsets, B = the count
st_sp_sl1: push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_sp_square)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_sp_sq2), hl
        xor a
        call struct_check_location
        ld  a, h
        or  l
        jr  z, st_sp_sl2
        ld  hl, (st_sp_sq2)
        ld  a, (ix + O_HOUSE)
        FCALL map_place_slab
        ld  hl, (st_sp_sq2)
        call st_sp_square_done
        ld  a, 1
        ld  (st_sp_any), a
st_sp_sl2: pop hl
        pop bc
        inc hl
        inc hl
        djnz st_sp_sl1
        xor a
        ld  (st_cl_notouch), a
        ld  a, (st_sp_any)
        or  a
        ret z
        FCALL struct_free
        ld  a, 1
        or  a
        ret

; struct_remove_fog ($01086C): IX = a structure: the player's lift the
; fog round their centre (position + $06B930[layout]) by their sight.
st_struct_unfog:
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        call st_layout
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_centre
        add hl, de
        ld  de, arg_pos
        ld  b, 2
st_sufg_1:  ld  a, (de)
        add a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        adc a, (hl)
        ld  (de), a
        inc de
        inc hl
        djnz st_sufg_1
        call st_info
        ld  de, SI_sight
        add hl, de
        ld  c, (hl)
        ld  hl, arg_pos
        FCALL map_unfog_radius
        ret

; ------------------------------------------------ where it may go (S6)

; struct_check_location ($00F0FC, PC Structure_IsValidBuildLocation):
; HL = the square, A = the type -> HL = 1 (all on concrete), -n (n
; squares off concrete) or 0 (not allowed).  st_slab_blocked gets the
; 4-Slab's blocked squares ($FFC258).
struct_check_location:
        ld  (st_cl_type), a
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_cl_square), hl
        ld  a, (st_cl_type)
        call struct_info
        ld  de, SI_flags
        add hl, de
        ld  a, (hl)
        ld  (st_cl_flags), a
        ld  de, SI_layout - SI_flags
        add hl, de
        ld  a, (hl)
        ld  (st_cl_layout), a
        ld  a, 1
        ld  (st_cl_ok), a
        xor a
        ld  (st_cl_count), a
        ld  (st_cl_touch), a
        ld  (st_cl_k), a
        ld  a, (st_cl_type)
        cp  1
        ld  a, 0
        jr  z, st_cl_0
        dec a
st_cl_0:   ld  (st_slab_blocked), a
        ld  a, (st_cl_layout)
        call st_layout_tiles       ; HL -> the offsets, B = the count
st_cl_loop:
        push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_cl_square)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_cl_sq), hl
        call map_valid
        jr  c, st_cl_1
        ld  a, (st_cl_type)
        or  a
        jr  nz, st_cl_off
        pop hl                  ; a slab off the map: out from inside the
        pop bc                  ; loop's pushes (returning over them once
        jp  st_cl_slabout       ; sent the CPU into a unit record)
st_cl_off:
        xor a
        ld  (st_cl_ok), a
        jp  st_cl_break
st_cl_1:   ld  hl, (st_cl_sq)
        call map_landscape
        ld  (st_cl_lt), a
        ld  a, (st_cl_flags)
        bit 3, a
        jr  z, st_cl_building
        ld  a, (st_cl_type)
        cp  1
        jr  nz, st_cl_slab1
        ; a 4-Slab ($00F1C8)
        call st_cl_pav_addr
        ld  (hl), 0
        ld  hl, (st_cl_sq)
        call st_sq_index
        or  a
        jr  z, st_cl_4s1
        ld  a, (st_cl_lt)
        cp  LST_STRUCTURE
        jr  nz, st_cl_4blk
st_cl_4s1: ld  a, (st_cl_lt)
        cp  LST_ROCK
        jr  z, st_cl_4pav
        cp  LST_MOSTLYROCK
        jr  z, st_cl_4pav
        cp  LST_DESTROYEDWALL
        jr  z, st_cl_4pav
        cp  LST_CONCRETE
        jr  c, st_cl_4cnt
        cp  LST_STRUCTURE + 1
        jr  nc, st_cl_4cnt
        ld  hl, (st_cl_sq)
        call st_sq_owner
        ld  hl, player_house
        cp  (hl)
        jr  nz, st_cl_4cnt
        ld  a, 1
        ld  (st_cl_touch), a
st_cl_4cnt:
        ld  hl, st_cl_count
        inc (hl)
st_cl_4blk:
        ld  a, (st_cl_k)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_slab_bits
        add hl, de
        ld  a, (st_slab_blocked)
        add a, (hl)
        ld  (st_slab_blocked), a
        jr  st_cl_next
st_cl_4pav:
        call st_cl_pav_addr
        ld  (hl), 1
        jr  st_cl_next
st_cl_slab1:
        ; a slab: the landscape must take one
        ld  a, (st_cl_lt)
        ld  de, LS_isValidForStructure2
        call st_cl_ls_flag
        jr  nz, st_cl_obj
        jr  st_cl_fail
st_cl_building:
        ld  a, (st_cl_lt)
        ld  de, LS_isValidForStructure
        call st_cl_ls_flag
        jr  z, st_cl_fail
        ld  a, (st_cl_lt)
        cp  LST_CONCRETE
        jr  c, st_cl_b1
        cp  LST_STRUCTURE + 1
        jr  nc, st_cl_b1
        ; concrete, wall or structure: the player's own
        ld  hl, (st_cl_sq)
        call st_sq_owner
        ld  hl, player_house
        cp  (hl)
        jr  z, st_cl_obj
        xor a
        ld  (st_cl_ok), a
        jr  st_cl_obj
st_cl_b1:  ld  hl, st_cl_count
        inc (hl)
st_cl_obj: ld  hl, (st_cl_sq)
        call st_sq_index
        or  a
        jr  z, st_cl_next
st_cl_fail:
        xor a
        ld  (st_cl_ok), a
        jr  st_cl_break
st_cl_next:
        ld  hl, st_cl_k
        inc (hl)
        pop hl
        pop bc
        inc hl
        inc hl
        dec b
        jp  nz, st_cl_loop
        jr  st_cl_after
st_cl_break:
        pop hl
        pop bc
st_cl_after:
        ; it must touch the base ($00F2FC), unless validate_strict, it has
        ; already failed, or it is a Construction Yard - or it is one
        ; square of a slab whose footprint has passed (st_sp_slab)
        ld  a, (validate_strict)
        or  a
        jp  nz, st_cl_result
        ld  a, (st_cl_notouch)
        or  a
        jp  nz, st_cl_result
        ld  a, (st_cl_ok)
        or  a
        jp  z, st_cl_result
        ld  a, (st_cl_type)
        cp  STRUCT_CONSTYARD
        jp  z, st_cl_result
        xor a
        ld  (st_cl_ok), a
        ld  (st_cl_k), a           ; d4, 0-15
st_cl_t_loop:
        ; the next square around: layout * 32 + k * 2
        ld  a, (st_cl_layout)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (st_cl_k)
        add a, a
        ld  e, a
        ld  d, 0
        add hl, de
        ld  de, tbl_layout_around
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, d
        or  e
        jr  z, st_cl_t_own
        ld  hl, (st_cl_square)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_cl_sq), hl
        call st_sq_struct          ; HL = a structure there, or Z
        jr  z, st_cl_t_ground
        ld  de, O_HOUSE
        add hl, de
        ld  a, (player_house)
        cp  (hl)
        jr  nz, st_cl_t_next
        jr  st_cl_t_hit
st_cl_t_ground:
        ld  hl, (st_cl_sq)
        call map_landscape
        cp  LST_CONCRETE
        jr  z, st_cl_t_g1
        cp  LST_WALL
        jr  nz, st_cl_t_next
st_cl_t_g1:
        ld  hl, (st_cl_sq)
        call st_sq_owner
        ld  hl, player_house
        cp  (hl)
        jr  nz, st_cl_t_next
st_cl_t_hit:
        ld  a, (st_cl_type)
        cp  1
        jr  nz, st_cl_t_yes
        ; a 4-Slab: the touching square must be one it can pave
        ld  b, 0
st_cl_t_pav:
        push bc
        ld  a, b
        ld  e, a
        ld  d, 0
        ld  hl, st_cl_pav
        add hl, de
        ld  a, (hl)
        or  a
        jr  z, st_cl_t_p1
        ld  a, b                ; slab_flags[b][k]: b * 12 + k
        add a, a
        add a, b
        add a, a
        add a, a
        ld  hl, st_cl_k
        add a, (hl)
        ld  e, a
        ld  hl, tbl_slab_flags
        add hl, de
        ld  a, (hl)
        or  a
        jr  z, st_cl_t_p1
        ld  a, 1
        ld  (st_cl_ok), a
st_cl_t_p1:
        pop bc
        inc b
        ld  a, b
        cp  4
        jr  c, st_cl_t_pav
st_cl_t_next:
        ld  hl, st_cl_k
        inc (hl)
        ld  a, (hl)
        cp  16
        jp  c, st_cl_t_loop
        jr  st_cl_t_end
st_cl_t_yes:
        ld  a, 1
        ld  (st_cl_ok), a
        jr  st_cl_t_end
st_cl_t_own:
        ; the list ended: one of its own squares on the player's
        ; concrete will do
        ld  a, (st_cl_layout)
        call st_layout_tiles
st_cl_t_o1:
        push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_cl_square)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        push hl
        call map_landscape
        pop hl
        cp  LST_CONCRETE
        jr  nz, st_cl_t_o2
        call st_sq_owner
        ld  hl, player_house
        cp  (hl)
        jr  nz, st_cl_t_o2
        ld  a, 1
        ld  (st_cl_ok), a
        pop hl
        pop bc
        jr  st_cl_t_end
st_cl_t_o2:
        pop hl
        pop bc
        inc hl
        inc hl
        djnz st_cl_t_o1
st_cl_t_end:
        ; a 4-Slab touching the base through its own blocked squares
        ld  a, (st_cl_type)
        cp  1
        jr  nz, st_cl_result
        ld  a, (st_cl_touch)
        or  a
        jr  z, st_cl_result
        ld  a, (st_slab_blocked)
        cp  15
        jr  z, st_cl_result
        ld  a, 1
        ld  (st_cl_ok), a
st_cl_result:
        ld  a, (st_cl_ok)
        or  a
        jr  z, st_cl_no
        ld  a, (st_slab_blocked)
        cp  15
        jr  z, st_cl_no
        ld  a, (st_cl_count)
        or  a
        ld  hl, 1
        ret z
        neg
        ld  l, a
        ld  h, $FF
        ret
st_cl_no:  ld  a, (st_cl_type)
        cp  1
        jr  nz, st_cl_zero
st_cl_slabout:
        ld  a, 15
        ld  (st_slab_blocked), a
st_cl_zero:
        ld  hl, 0
        ret

; HL -> cl_pav[cl_k]
st_cl_pav_addr:
        ld  a, (st_cl_k)
        ld  e, a
        ld  d, 0
        ld  hl, st_cl_pav
        add hl, de
        ret

; A = a landscape type, DE = the field -> NZ if the word is nonzero (or
; validate_strict), Z if not.  $FF (no ground) never allows.
st_cl_ls_flag:
        cp  LANDSCAPE_COUNT
        jr  nc, st_clf_no
        push de
        call landscape_info
        pop de
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        ret nz
st_clf_no: ld  a, (validate_strict)
        or  a
        ret

; struct_check_landscape ($00F4BE): the computer's check - every square on
; the map and of the right landscape (validate_strict lets any); HL = the
; square, A = the type -> HL = 1, -n (n squares off concrete) or 0.
struct_check_landscape:
        ld  (st_cl_type), a
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_cl_square), hl
        ld  a, (st_cl_type)
        call struct_info
        ld  de, SI_flags
        add hl, de
        ld  a, (hl)
        ld  (st_cl_flags), a
        ld  de, SI_layout - SI_flags
        add hl, de
        ld  c, (hl)
        xor a
        ld  (st_cl_count), a
        ld  a, c
        call st_layout_tiles
st_clk_loop:
        push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_cl_square)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        call map_valid
        jr  nc, st_clk_no
        call map_landscape
        ld  (st_cl_lt), a
        ld  a, (st_cl_flags)
        bit 3, a
        ld  a, (st_cl_lt)
        jr  z, st_clk_b
        ld  de, LS_isValidForStructure2
        call st_cl_ls_flag
        jr  z, st_clk_no
        jr  st_clk_next
st_clk_b:  ld  de, LS_isValidForStructure
        call st_cl_ls_flag
        jr  z, st_clk_no
        ld  a, (st_cl_lt)
        cp  LST_CONCRETE
        jr  z, st_clk_next
        ld  hl, st_cl_count
        inc (hl)
st_clk_next:
        pop hl
        pop bc
        inc hl
        inc hl
        djnz st_clk_loop
        ld  a, (st_cl_count)
        or  a
        ld  hl, 1
        ret z
        neg
        ld  l, a
        ld  h, $FF
        ret
st_clk_no: pop hl
        pop bc
        ld  hl, 0
        ret

; ============================================ power and storage (S5)

; house_calc_power ($01048C): A = the house.  Storage, power made and power
; used, over its structures (those on the map, or all while
; validate_strict); a damaged producer gives 128/256 - 255/256 of its
; power.  The player's house with nothing built loses playerCreditsNoSilo.
house_calc_power:
        ld  (st_hcp_house), a
        call house_ptr
        push hl
        pop iy
        xor a
        ld  (iy + H_STORAGE), a
        ld  (iy + H_STORAGE + 1), a
        ld  (iy + H_STORAGE + 2), a
        ld  (iy + H_STORAGE + 3), a
        ld  hl, 0
        ld  (st_hcp_prod), hl
        ld  (st_hcp_use), hl
        ld  a, (st_hcp_house)
        ld  b, a
        ld  c, $FF
        push ix
        ld  hl, st_hcp_state
        call st_sfind_first
st_hcp_loop:
        jr  z, st_hcp_done
        call st_info
        push hl
        ld  de, SI_creditsStorage
        add hl, de
        ld  a, (iy + H_STORAGE)
        add a, (hl)
        ld  (iy + H_STORAGE), a
        inc hl
        ld  a, (iy + H_STORAGE + 1)
        adc a, (hl)
        ld  (iy + H_STORAGE + 1), a
        jr  nc, st_hcp_1
        inc (iy + H_STORAGE + 2)
        jr  nz, st_hcp_1
        inc (iy + H_STORAGE + 3)
st_hcp_1:  inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; powerUsage
        pop hl
        bit 7, d
        jr  nz, st_hcp_prod1
        ld  hl, (st_hcp_use)
        add hl, de
        ld  (st_hcp_use), hl
        jr  st_hcp_next
st_hcp_prod1:
        call neg_de             ; what it makes
        push de
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; type.hp
        ld  e, (ix + O_HP)
        ld  d, (ix + O_HP + 1)
        push hl
        or  a
        sbc hl, de              ; type.hp - hp
        pop hl
        jr  z, st_hcp_full
        jr  c, st_hcp_full         ; hp >= type.hp (signed words; both positive)
        call div_shl8           ; hp * 256 / type.hp
        ld  a, h
        or  a
        jr  nz, st_hcp_255
        ld  a, l
        cp  $80
        jr  nc, st_hcp_2
        ld  l, $80
st_hcp_2:  cp  $FF
        jr  c, st_hcp_3
st_hcp_255:
        ld  hl, $FF
st_hcp_3:  pop de
        call mul_shr8           ; power * ratio
        ex  de, hl
        jr  st_hcp_add
st_hcp_full:
        pop de
st_hcp_add:
        ld  hl, (st_hcp_prod)
        add hl, de
        ld  (st_hcp_prod), hl
st_hcp_next:
        ld  hl, st_hcp_state
        call st_sfind_next
        jr  st_hcp_loop
st_hcp_done:
        pop ix
        ld  hl, (st_hcp_prod)
        ld  (iy + H_POWERPROD), l
        ld  (iy + H_POWERPROD + 1), h
        ld  hl, (st_hcp_use)
        ld  (iy + H_POWERUSE), l
        ld  (iy + H_POWERUSE + 1), h
        ; the player's house with nothing built: no credits without storage
        ld  a, (player_house)
        ld  hl, st_hcp_house
        cp  (hl)
        ret nz
        ld  a, (iy + H_BUILT)
        or  (iy + H_BUILT + 1)
        or  (iy + H_BUILT + 2)
        or  (iy + H_BUILT + 3)
        ret nz
        ld  a, (validate_strict)
        or  a
        ret nz
        ld  hl, 0
        ld  (credits_no_silo), hl
        ld  (credits_no_silo + 2), hl
        ret

; house_power_to_health ($010594): A = the house.  ratio = min(made * 256
; / used, 256); every structure of the house gets hitpointsMax =
; max((ratio * type.hp + $50) >> 8, type.hp / 2), and one above it is
; damaged by an eighth of the excess plus one.  (The player's radar state
; is the UI's.)
house_power_to_health:
        ld  (st_hcp_house), a
        FCALL radar_update_state        ; (it acts for the player only)
        ld  a, (st_hcp_house)
        call house_ptr
        ld  de, H_POWERPROD
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call div_shl8           ; made * 256 / used
        ld  de, 256
        or  a
        sbc hl, de
        add hl, de
        jr  c, st_hph_1
        ex  de, hl
st_hph_1:  ld  (st_hcp_prod), hl      ; the ratio
        ld  a, (st_hcp_house)
        ld  b, a
        ld  c, $FF
        push ix
        ld  hl, st_hcp_state
        call st_sfind_first
st_hph_loop:
        jr  z, st_hph_done
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        push de
        ld  hl, (st_hcp_prod)
        call mul_shr8           ; ratio * type.hp
        pop de
        sra d
        rr  e                   ; type.hp / 2
        ; the larger (signed)
        push hl
        or  a
        sbc hl, de
        pop hl
        jp  p, st_hph_2
        ex  de, hl
st_hph_2:  ld  (ix + S_HPMAX), l
        ld  (ix + S_HPMAX + 1), h
        ex  de, hl
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        or  a
        sbc hl, de              ; hp - max
        jr  z, st_hph_next
        jp  m, st_hph_next
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        inc hl
        ld  a, h
        or  l
        jr  z, st_hph_next
        bit 7, h
        jr  nz, st_hph_next
        FCALL struct_damage
st_hph_next:
        ld  hl, st_hcp_state
        call st_sfind_next
        jr  st_hph_loop
st_hph_done:
        pop ix
        ret

; ================================================= map animations (S8)
;
; map_anim_start ($00AE58) / map_anim_tick ($00B1C2): a script of (icon,
; delay) pairs from $06A9B4[n & $3F] runs on a square.  Starting one draws
; its first icon; when the delay has run out the next pair is read, and
; a pair whose delay is 0 or less ends it (that icon is not drawn).  An
; icon below 128 and not flagged ($00B142) goes in the square's overlay;
; any other is stamped as ground over the structure's layout, square k
; getting icon + k (map_anim_draw $00B0A4).  One animation a square.

; A = the script, HL = the square, IX = the structure (for its layout) or
; 0 (a single square).
map_anim_start:
        push ix
        ex  (sp), hl
        ld  c, a
        ld  a, h
        or  l
        ld  a, c
        ld  c, 0
        jr  z, st_mas_1
        push af
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  c, (hl)
        pop af
st_mas_1:  pop hl
        ; fall through

; A = the script, HL = the square, C = the layout.
st_map_anim_start_l:
        push ix
        ld  (st_ma_script), a
        ld  a, c
        ld  (st_ma_layout), a
        ld  a, h
        and $0F
        ld  h, a
        push hl
        call map_anim_stop
        pop hl
        ld  a, (st_ma_count)
        cp  st_MA_MAX
        jr  nc, st_mas_full
        push hl
        call st_ma_record          ; IX = record A
        pop hl
        ld  (ix + 0), l
        ld  (ix + 1), h
        ld  a, (st_ma_layout)
        ld  (ix + 8), a
        ld  a, (st_ma_script)
        and $3F
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        ld  de, tbl_icon_anim_ptr
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        add hl, hl
        ld  de, tbl_icon_anim
        add hl, de
        ld  a, (hl)
        ld  (ix + 2), a
        inc hl
        ld  a, (hl)
        ld  (ix + 3), a
        inc hl
        ld  a, (hl)
        ld  (ix + 4), a
        inc hl
        ld  a, (hl)
        ld  (ix + 5), a
        inc hl
        ld  (ix + 6), l
        ld  (ix + 7), h
        ld  hl, st_ma_count
        inc (hl)
        call st_ma_draw
st_mas_full:
        pop ix
        ret

; HL = a square: stop the animation running there, if any ($00B2BE).
; Keeps IX.
map_anim_stop:
        ld  a, (st_ma_count)
        or  a
        ret z
        push ix
        ld  b, a
        ld  ix, st_ma_pool
        ld  de, st_MA_SIZE
st_mst_1:  ld  a, (ix + 0)
        cp  l
        jr  nz, st_mst_2
        ld  a, (ix + 1)
        cp  h
        jr  z, st_mst_hit
st_mst_2:  add ix, de
        djnz st_mst_1
        pop ix
        ret
st_mst_hit:
        call st_ma_remove
        pop ix
        ret

; IX = a record: take it out, the last one moving into its place.
st_ma_remove:
        ld  hl, st_ma_count
        dec (hl)
        ld  a, (hl)
        push ix
        call st_ma_record          ; IX = the last
        push ix
        pop hl
        pop de
        ld  bc, st_MA_SIZE
        ldir
        ret

; A = an index -> IX = its record.  Clobbers DE.
st_ma_record:
        ld  ix, st_ma_pool
        or  a
        ret z
        ld  de, st_MA_SIZE
st_mar_1:  add ix, de
        dec a
        jr  nz, st_mar_1
        ret

; map_anim_tick ($00B1C2): every pass, by frames_this_pass.  Also counts
; the Starport's price timer down while it is positive (time_tick,
; S1/S6).
map_anim_tick:
        push ix
        push iy
        ld  hl, (st_starport_price_timer)
        bit 7, h
        jr  nz, st_mat_0
        ld  a, h
        or  l
        jr  z, st_mat_0
        ld  de, (frames_this_pass)
        or  a
        sbc hl, de
        ld  (st_starport_price_timer), hl
st_mat_0:  xor a
        ld  (st_ma_i), a
st_mat_loop:
        ld  a, (st_ma_i)
        ld  hl, st_ma_count
        cp  (hl)
        jr  nc, st_mat_done
        call st_ma_record
        ld  l, (ix + 4)
        ld  h, (ix + 5)
        ld  de, (frames_this_pass)
        or  a
        sbc hl, de
        ld  (ix + 4), l
        ld  (ix + 5), h
        jr  z, st_mat_step
        jp  p, st_mat_next
st_mat_step:
        ; the next pair
        ld  l, (ix + 6)
        ld  h, (ix + 7)
        ld  a, (hl)
        ld  (ix + 2), a
        inc hl
        ld  a, (hl)
        ld  (ix + 3), a
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  (ix + 4), e
        ld  (ix + 5), d
        ld  (ix + 6), l
        ld  (ix + 7), h
        ld  a, d
        or  e
        jr  z, st_mat_end
        bit 7, d
        jr  nz, st_mat_end
        call st_ma_draw
st_mat_next:
        ld  hl, st_ma_i
        inc (hl)
        jr  st_mat_loop
st_mat_end:
        call st_ma_remove          ; the same index now holds the next one
        jr  st_mat_loop
st_mat_done:
        pop iy
        pop ix
        ret

; IX = a record: draw its icon ($00B0A4).
st_ma_draw:
        ld  e, (ix + 2)
        ld  d, (ix + 3)
        ld  a, d
        or  e
        ret z
        ld  a, d
        or  a
        jr  nz, st_mad_stamp
        ld  a, e
        cp  $80
        jr  nc, st_mad_stamp
        ld  hl, tbl_overlay_stamp
        add hl, de
        ld  a, (hl)
        or  a
        jr  nz, st_mad_stamp
        ld  l, (ix + 0)
        ld  h, (ix + 1)
        ld  a, e
        jp  st_set_overlay
st_mad_stamp:
        ld  (st_ma_icon), de
        ld  a, (ix + 8)
        call st_layout_tiles
st_mad_1:  push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  l, (ix + 0)
        ld  h, (ix + 1)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ; the overlay: craters and blanks (1-$13) and $21 go
        push hl
        call map_overlay_icon
        pop hl
        cp  $21
        jr  z, st_mad_2
        cp  $14
        jr  nc, st_mad_3
st_mad_2:  xor a
        call st_set_overlay
st_mad_3:  ld  de, (st_ma_icon)
        call st_set_ground
        inc de
        ld  (st_ma_icon), de
        pop hl
        pop bc
        inc hl
        inc hl
        djnz st_mad_1
        ret

; ============================================= BUILD.EMC routines (S6)
;
; Far-called with IX = the structure's script state (the structure is IX
; - O_SCRIPT); arguments through emc_arg; the answer in HL.

; BUILD 13 state ($00C652): the structure's state.
ef_b_state:
        ld  l, (ix + S_STATE - O_SCRIPT)
        ld  h, (ix + S_STATE + 1 - O_SCRIPT)
        ret

; BUILD 4 set.state ($00C7CC): the top of the stack; -2 works it out: 0
; with nothing linked, 1 while what is linked is still being made, 2 when
; it is done.  Answers 0.
ef_b_set_state:
        xor a
        call emc_arg            ; HL = the state asked for
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, l
        cp  $FE
        jr  nz, st_ebs_set
        ld  a, h
        inc a
        jr  nz, st_ebs_set
        ld  l, 0
        ld  a, (ix + O_LINKED)
        inc a
        jr  z, st_ebs_set
        inc l
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        jr  nz, st_ebs_set
        inc l
st_ebs_set:
        ld  a, l
        call struct_set_state
        ld  hl, 0
        ret

; BUILD 15 unfog ($00D012): the player's structure lifts the fog round its
; centre by its sight.  Answers 0.
ef_b_unfog:
        ld  de, -O_SCRIPT
        add ix, de
        call st_struct_unfog
        ld  hl, 0
        ret

; BUILD 21 refine ($00D068): up to 3 spice (fewer when the Refinery is
; damaged: (3 * hp*256/type.hp + $50) >> 8, at least 1 while there is
; some) out of the docked Harvester, at 7 credits each (6-9 for another
; house's Harvester - the cartridge asks the Harvester's house), into the
; harvested totals (capped at 65000) and the house's credits, capped at
; its storage.  Port fix (S5): only the player's cap has
; playerCreditsNoSilo as its floor.  A delay of 6; answers 1.  Nothing
; linked: state 0; nothing left: state 2; both answer 0.
ef_b_refine:
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, st_ebr_1
        xor a
        call struct_set_state
        ld  hl, 0
        ret
st_ebr_1:  call unit_ptr
        push hl
        pop iy                  ; IY = the Harvester
        call st_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  e, (ix + O_HP)
        ld  d, (ix + O_HP + 1)
        call div_shl8
        ld  de, 3
        call mul_shr8           ; HL = the step
        ld  a, h
        or  a
        jr  nz, st_ebr_2
        ld  a, l
        cp  (iy + U_AMOUNT)
        jr  c, st_ebr_3
st_ebr_2:  ld  a, (iy + U_AMOUNT)
st_ebr_3:  ld  c, a
        ld  a, (iy + U_AMOUNT)
        or  a
        jr  z, st_ebr_4
        ld  a, c
        or  a
        jr  nz, st_ebr_4
        inc c
st_ebr_4:  ld  a, c
        or  a
        jr  nz, st_ebr_go
        ld  a, 2
        call struct_set_state
        ld  hl, 0
        ret
st_ebr_go: ld  (st_ebr_step), a
        ld  b, 7
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  z, st_ebr_5
        call random
        and 3
        add a, 6
        ld  b, a
st_ebr_5:  ld  a, (st_ebr_step)
        ld  l, a
        ld  h, 0
        ld  e, b
        ld  d, 0
        call mul16              ; paid
        ld  (st_ebr_paid), hl
        ld  a, (player_house)
        ld  c, a
        ld  b, (ix + O_HOUSE)
        call house_are_allied
        or  a
        ld  hl, harvested_allied
        jr  nz, st_ebr_6
        ld  hl, harvested_enemy
st_ebr_6:  ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ld  bc, (st_ebr_paid)
        add hl, bc
        jr  c, st_ebr_cap
        push hl
        ld  bc, 65000
        or  a
        sbc hl, bc
        pop hl
        jr  c, st_ebr_7
st_ebr_cap:
        ld  hl, 65000
st_ebr_7:  ex  de, hl
        ld  (hl), d
        dec hl
        ld  (hl), e
        ; the credits, capped at the storage
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push iy
        push hl
        pop iy
        ld  de, (st_ebr_paid)
        call st_cr_add
        call st_cr_cap
        pop iy
        ; the load
        ld  a, (st_ebr_step)
        ld  b, a
        ld  a, (iy + U_AMOUNT)
        sub b
        ld  (iy + U_AMOUNT), a
        jr  nz, st_ebr_8
        res OF_INTRANSPORT - 8, (iy + O_FLAGS + 1)
st_ebr_8:  ld  (ix + O_DELAY), 6
        ld  (ix + O_DELAY + 1), 0
        ld  hl, 1
        ret

; IY = a house: its credits cut to its storage; the player's to the larger
; of storage and playerCreditsNoSilo (S5's cap, fixed for the computer).
st_cr_cap:
        ld  l, (iy + H_STORAGE)
        ld  h, (iy + H_STORAGE + 1)
        ld  e, (iy + H_STORAGE + 2)
        ld  d, (iy + H_STORAGE + 3)
        ld  a, (player_house)
        cp  (iy + H_INDEX)
        jr  nz, st_crc_1
        ; the larger of the two
        push hl
        push de
        ld  a, (credits_no_silo)
        sub l
        ld  a, (credits_no_silo + 1)
        sbc a, h
        ld  a, (credits_no_silo + 2)
        sbc a, e
        ld  a, (credits_no_silo + 3)
        sbc a, d
        pop de
        pop hl
        jr  c, st_crc_1
        ld  hl, (credits_no_silo)
        ld  de, (credits_no_silo + 2)
st_crc_1:  ; credits > cap: credits = cap
        ld  a, l
        sub (iy + H_CREDITS)
        ld  a, h
        sbc a, (iy + H_CREDITS + 1)
        ld  a, e
        sbc a, (iy + H_CREDITS + 2)
        ld  a, d
        sbc a, (iy + H_CREDITS + 3)
        ret nc
        ld  (iy + H_CREDITS), l
        ld  (iy + H_CREDITS + 1), h
        ld  (iy + H_CREDITS + 2), e
        ld  (iy + H_CREDITS + 3), d
        ret

; house_cap_credits: A = a house: the cap above, for the house loop (S1,
; S5; the port caps each house in its own pass).
house_cap_credits:
        call house_ptr
        push hl
        pop iy
        jr  st_cr_cap

; ================================================== little helpers

; HL = a 3-byte search state, B = house ($FF any), C = type ($FF any) ->
; IX = the first structure (NZ), Z none.  Structures off the map are
; passed over unless validate_strict.  Keeps HL.  Clobbers A, BC, DE.
st_sfind_first:
        ld  (hl), b
        inc hl
        ld  (hl), c
        inc hl
        ld  (hl), $FF
        dec hl
        dec hl
; HL = the state -> IX = the next structure (NZ), Z at the end.
st_sfind_next:
        push hl
        inc hl
        inc hl
st_sfn_l:  inc (hl)
        ld  a, (struct_find_count)
        ld  c, a
        ld  a, (hl)
        cp  c
        jr  nc, st_sfn_end
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, struct_find
        add hl, de
        ld  a, (hl)
        call struct_ptr
        push hl
        pop ix
        pop hl
        dec hl
        ld  a, (hl)
        inc hl
        cp  $FF
        jr  z, st_sfn_t
        cp  (ix + O_TYPE)
        jr  nz, st_sfn_l
st_sfn_t:  bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, st_sfn_m
        ld  a, (validate_strict)
        or  a
        jr  z, st_sfn_l
st_sfn_m:  dec hl
        dec hl
        ld  a, (hl)
        inc hl
        inc hl
        cp  $FF
        jr  z, st_sfn_y
        cp  (ix + O_HOUSE)
        jr  nz, st_sfn_l
st_sfn_y:  pop hl
        or  1
        ret
st_sfn_end:
        ld  (hl), a
        pop hl
        xor a
        ret

; B = house, C = type: the first unit of them (unit_find_first, the
; on-map rule) -> HL = it, Z none.  Clobbers A, DE.
st_ufind_one:
        ld  a, (unit_find_count)
        or  a
        jr  z, st_ufo_none
        ld  hl, unit_find
st_ufo_1:  push af
        push hl
        ld  a, (hl)
        call unit_ptr
        ld  a, c
        cp  $FF
        jr  z, st_ufo_2
        push hl
        inc hl
        inc hl
        cp  (hl)
        pop hl
        jr  nz, st_ufo_no
st_ufo_2:  push hl
        ld  de, O_FLAGS
        add hl, de
        bit OF_NOTONMAP, (hl)
        pop hl
        jr  z, st_ufo_3
        ld  a, (validate_strict)
        or  a
        jr  z, st_ufo_no
st_ufo_3:  ld  a, b
        cp  $FF
        jr  z, st_ufo_yes
        push hl
        ld  de, O_HOUSE
        add hl, de
        cp  (hl)
        pop hl
        jr  z, st_ufo_yes
st_ufo_no: pop hl
        inc hl
        pop af
        dec a
        jr  nz, st_ufo_1
st_ufo_none:
        ld  hl, 0
        xor a
        ret
st_ufo_yes:
        pop de
        pop af
        ld  a, h
        or  l
        ret

; HL = a due time (4 bytes), DE = a period -> A = 1 (NZ) and the timer
; set to the clock plus the period, if timer_game has reached it; A = 0
; (Z) if not (S1: slippage is never made up).
st_timer_due:
        call st_timer_reached
        ret z
; HL = a timer, DE = the period: timer = timer_game + DE.  -> A = 1, NZ.
st_timer_set:
        push hl
        ld  a, (timer_game)
        add a, e
        ld  (hl), a
        inc hl
        ld  a, (timer_game + 1)
        adc a, d
        ld  (hl), a
        inc hl
        ld  a, (timer_game + 2)
        adc a, 0
        ld  (hl), a
        inc hl
        ld  a, (timer_game + 3)
        adc a, 0
        ld  (hl), a
        pop hl
        ld  a, 1
        or  a
        ret
; HL = a due time -> NZ if timer_game >= it.  Keeps HL, DE.
st_timer_reached:
        push hl
        ld  a, (timer_game)
        sub (hl)
        inc hl
        ld  a, (timer_game + 1)
        sbc a, (hl)
        inc hl
        ld  a, (timer_game + 2)
        sbc a, (hl)
        inc hl
        ld  a, (timer_game + 3)
        sbc a, (hl)
        pop hl
        jr  c, st_trc_no
        ld  a, 1
        or  a
        ret
st_trc_no: xor a
        ret

; IY = a house, DE = an amount -> CF if its credits are below it.
st_cr_lt:
        ld  a, (iy + H_CREDITS + 2)
        or  (iy + H_CREDITS + 3)
        ret nz
        ld  a, (iy + H_CREDITS)
        sub e
        ld  a, (iy + H_CREDITS + 1)
        sbc a, d
        ret
; IY = a house -> Z if it has no credits.
st_cr_zero:
        ld  a, (iy + H_CREDITS)
        or  (iy + H_CREDITS + 1)
        or  (iy + H_CREDITS + 2)
        or  (iy + H_CREDITS + 3)
        ret
; IY = a house: credits -= DE.
st_cr_sub:
        ld  a, (iy + H_CREDITS)
        sub e
        ld  (iy + H_CREDITS), a
        ld  a, (iy + H_CREDITS + 1)
        sbc a, d
        ld  (iy + H_CREDITS + 1), a
        ld  a, (iy + H_CREDITS + 2)
        sbc a, 0
        ld  (iy + H_CREDITS + 2), a
        ld  a, (iy + H_CREDITS + 3)
        sbc a, 0
        ld  (iy + H_CREDITS + 3), a
        ret
; IY = a house: credits += DE.
st_cr_add:
        ld  a, (iy + H_CREDITS)
        add a, e
        ld  (iy + H_CREDITS), a
        ld  a, (iy + H_CREDITS + 1)
        adc a, d
        ld  (iy + H_CREDITS + 1), a
        ld  a, (iy + H_CREDITS + 2)
        adc a, 0
        ld  (iy + H_CREDITS + 2), a
        ld  a, (iy + H_CREDITS + 3)
        adc a, 0
        ld  (iy + H_CREDITS + 3), a
        ret

; IX = a structure -> HL = its type record.  Clobbers A, DE.
st_info:
        ld  a, (ix + O_TYPE)
        jp  struct_info
; IX = a structure -> A = its layout.  Clobbers DE, HL.
st_layout:
        call st_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        ret
; IX = a structure -> A = the number of squares of its layout.
st_layout_count:
        call st_layout
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_count
        add hl, de
        ld  a, (hl)
        ret
; IX -> HL -> the layout's offsets, B = their count (st_layout_first), for
; st_layout_square (HL -> an offset -> HL = the square).
st_layout_first:
        call st_layout
; A = a layout -> HL -> its offsets, B = the count.  Clobbers DE.
st_layout_tiles:
        push af
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_count
        add hl, de
        ld  b, (hl)
        pop af
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
        ret
st_layout_square:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        call st_square
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ret
; IX = a structure (or unit) -> HL = the square of its position.
st_square:
        push ix
        pop hl
        ld  a, l
        add a, O_POS_Y
        ld  l, a
        jr  nc, st_sts_1
        inc h
st_sts_1:  jp  pos_square

; B = a house, A = a structure type -> HL = its structTypeCount byte (houses
; 5 and up count in house 0's row, as OBJ's).  Clobbers DE.
st_stc_addr:
        ld  e, a
        ld  a, b
        cp  5
        jr  c, st_stca_1
        xor a
st_stca_1: add a, a
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

; A = 0-7 -> A = 1 << A.
st_bit_of:
        push bc
        ld  b, a
        inc b
        xor a
        scf
st_bo_1:   rla
        djnz st_bo_1
        pop bc
        ret

; HL -> a 32-bit mask, A = a bit: set it.  Clobbers A, B, DE.
st_set_bit32:
        ld  b, a
        srl a
        srl a
        srl a
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, b
        and 7
        call st_bit_of
        or  (hl)
        ld  (hl), a
        ret

; HL = a square, DE = an icon: the ground, the overlay kept.  Keeps HL,
; DE.  Clobbers A.
st_set_ground:
        push hl
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
        pop hl
        ret
; HL = a square, A = an overlay icon.  Keeps HL.  Clobbers A.
st_set_overlay:
        push hl
        push bc
        add a, a
        ld  c, a
        ld  a, h
        and $0F
        or  MAP_HIGH >> 8
        ld  h, a
        ld  a, (hl)
        and 1
        or  c
        ld  (hl), a
        pop bc
        pop hl
        ret
; HL = a square -> A = its owner (flags bits 0-2).  Keeps HL.
st_sq_owner:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        and 7
        pop hl
        ret
; HL = a square -> A = its index byte (the object's slot + 1).  Keeps HL.
st_sq_index:
        push hl
        ld  a, h
        and $0F
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        ret
; HL = a square -> HL = the structure on it, or Z.  Clobbers A, DE.
st_sq_struct:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_STRUCT, (hl)
        pop hl
        jr  z, st_sqs_none
        call st_sq_index
        or  a
        jr  z, st_sqs_none
        dec a
        call struct_ptr
        or  1
        ret
st_sqs_none:
        ld  hl, 0
        xor a
        ret
; HL = a square -> HL = the unit on it, or Z.  Clobbers A, DE.
st_sq_unit:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNIT, (hl)
        pop hl
        jr  z, st_sqs_none
        call st_sq_index
        or  a
        jr  z, st_sqs_none
        dec a
        call unit_ptr
        or  1
        ret
; map_square_unveiled ($01AFE6): HL = a square -> NZ if revealed and not
; under a fog icon.  Keeps HL.
st_sq_unveiled:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNVEILED, (hl)
        pop hl
        ret z
        push hl
        call map_overlay_icon
        pop hl
        cp  st_VEILED_ICON + 1
        jr  nc, st_squ_yes
        cp  st_VEILED_ICON - 15
        jr  c, st_squ_yes
        xor a
        ret
st_squ_yes:
        or  1
        ret

st_VEILED_ICON     EQU $7B

; ------------------------------------------------ the bank's own data
st_MA_MAX          EQU 48
st_MA_SIZE         EQU 9               ; square w, icon w, delay w, next pair w, layout b

st_tk_build:       DD 0                ; tickStructureStructure $FFD5A0
st_tk_decay:       DD 0                ; tickStructureDegrade $FFD5A4
st_tk_script:      DD 0                ; tickStructureScript $FFD59C
st_tk_palace:      DD 0                ; tickStructurePalace $FFD598
st_sg_build:       DB 0
st_sg_decay:       DB 0
st_sg_script:      DB 0
st_sg_palace:      DB 0
st_sg_state:       DS 3
st_hcp_state:      DS 3
st_hcp_house:      DB 0
st_hcp_prod:       DW 0
st_hcp_use:        DW 0
st_bt_speed:       DW 0
st_bt_cost:        DW 0
st_bt_unit:        DW 0
st_sc_square:      DW 0
st_sc_type:        DB 0
st_sc_house:       DB 0
st_sp_square:      DW 0
st_sp_sq2:         DW 0
st_sp_check:       DW 0
st_sp_any:         DB 0
st_cl_notouch:     DB 0            ; st_sp_slab: skip the touch test only
st_sal_frame:      DB 0
st_sal_sq:         DW 0
st_cl_square:      DW 0
st_cl_sq:          DW 0
st_cl_type:        DB 0
st_cl_flags:       DB 0
st_cl_layout:      DB 0
st_cl_lt:          DB 0
st_cl_ok:          DB 0
st_cl_count:       DB 0
st_cl_touch:       DB 0
st_cl_k:           DB 0
st_cl_pav:         DS 4
st_ebr_step:       DB 0
st_ebr_paid:       DW 0
st_ma_script:      DB 0
st_ma_layout:      DB 0
st_ma_icon:        DW 0
st_ma_i:           DB 0
st_ma_count:       DB 0
st_ma_pool:        DS st_MA_MAX * st_MA_SIZE
st_lt_timer:       DS STRUCT_COUNT * 2 ; $FFD4B8: a light timer and frame a structure
st_mk_timer:       DS STRUCT_COUNT     ; $FFD54C: a marker timer a structure
