; functions.asm - the routines the three scripts may call (S7), as tables
; of (bank, address), and the small ones that live here.
;
; A routine is far-called with IX = the calling script's state (the delay
; word at IX-2) and answers in HL.  It reads its arguments with emc_arg
; (A = 0 the top of the stack).  The object the script belongs to is in
; script_object (and script_unit / script_struct / script_team).
; Unimplemented entries point at ef_zero, which answers 0.

    MACRO EF _fn_
        DB  $$_fn_
        DW  _fn_
    ENDM

emc_unit_funcs:
        EF  ef_u_get                        ;  0 get
        EF  ef_u_act                        ;  1 act
        EF  ef_zero                         ;  2 print (never called)
        EF  ef_u_distance                   ;  3 distance
        EF  ef_u_explode                    ;  4 explode
        EF  ef_u_go_to                      ;  5 go.to
        EF  ef_u_dir_to                     ;  6 dir.to
        EF  ef_u_turn                       ;  7 turn
        EF  ef_u_fire                       ;  8 fire
        EF  ef_u_deploy                     ;  9 deploy
        EF  ef_u_act_default                ; 10 act.default
        EF  ef_zero                         ; 11 (0)
        EF  ef_u_step                       ; 12 step
        EF  ef_u_enemy                      ; 13 enemy?
        EF  ef_zero                         ; 14 (the death blast: a stub on the Mega Drive)
        EF  ef_u_die                        ; 15 die
        EF  ef_delay                       ; 16 delay
        EF  ef_u_friend                     ; 17 friend?
        EF  ef_u_explode_big                ; 18 explode.big
        EF  ef_u_frame                      ; 19 frame
        EF  ef_u_deliver                    ; 20 deliver
        EF  ef_zero                         ; 21 (0)
        EF  ef_u_fly_to                     ; 22 fly.to
        EF  ef_random                     ; 23 random
        EF  ef_zero                         ; 24 (never called)
        EF  ef_u_head_for                   ; 25 head.for
        EF  ef_u_stop                       ; 26 stop
        EF  ef_u_speed                      ; 27 speed
        EF  ef_u_find_target                ; 28 find.target
        EF  ef_zero                         ; 29 (never called)
        EF  ef_u_seek_dock                  ; 30 seek.dock
        EF  ef_zero                         ; 31 (never called)
        EF  ef_u_amount                     ; 32 amount
        EF  ef_u_survivor                   ; 33 survivor
        EF  ef_u_pick_up                    ; 34 pick.up
        EF  ef_u_call_unit                  ; 35 call.unit
        EF  ef_u_dismiss                    ; 36 dismiss
        EF  ef_u_find_struct                ; 37 find.struct
        EF  ef_zero                         ; 38 (0)
        EF  ef_zero                         ; 39 (a bare rts: answer 0)
        EF  ef_u_unfog                      ; 40 unfog
        EF  ef_u_find_spice                 ; 41 find.spice
        EF  ef_u_harvest                    ; 42 harvest
        EF  ef_zero                         ; 43 (0)
        EF  ef_u_linked_type                ; 44 linked.type
        EF  ef_u_kind                       ; 45 kind
        EF  ef_zero                         ; 46 (never called)
        EF  ef_u_blocked                    ; 47 blocked?
        EF  ef_u_nearby                     ; 48 nearby
        EF  ef_u_fidget                     ; 49 fidget
        EF  ef_u_count                      ; 50 count
        EF  ef_u_go_nearest                 ; 51 go.nearest
        EF  ef_zero                         ; 52 (0)
        EF  ef_zero                         ; 53 (0)
        EF  ef_u_find_prey                  ; 54 find.prey
        EF  ef_u_claim_ok                   ; 55 claim.ok?
        EF  ef_u_facing_of                  ; 56 facing.of
        EF  ef_zero                         ; 57 (0)
        EF  ef_u_aim                        ; 58 aim
        EF  ef_u_not_unit                   ; 59 not.unit?
        EF  ef_delay_rnd               ; 60 delay.rnd
        EF  ef_u_turning                    ; 61 turning?
        EF  ef_u_distance_to                ; 62 distance.to
        EF  ef_zero                         ; 63 (0)

emc_team_funcs:
        EF  ef_delay                       ;  0 delay
        EF  ef_zero                         ;  1 (never called)
        EF  ef_t_members                    ;  2 members
        EF  ef_t_recruit                    ;  3 recruit
        EF  ef_t_spread                     ;  4 spread
        EF  ef_t_gather                     ;  5 gather
        EF  ef_t_find_target                ;  6 find.target
        EF  ef_t_attack                     ;  7 attack
        EF  ef_t_behave                     ;  8 behave
        EF  ef_t_behave_orig                ;  9 behave.orig
        EF  ef_delay_rnd               ; 10 delay.rnd
        EF  ef_zero                         ; 11 (0)
        EF  ef_t_min                        ; 12 min
        EF  ef_t_target                     ; 13 target
        EF  ef_zero                         ; 14 (0)

emc_build_funcs:
        EF  ef_delay                       ;  0 delay
        EF  ef_zero                         ;  1 (0)
        EF  ef_b_check_link                 ;  2 check.link
        EF  ef_b_send_for                   ;  3 send.for
        EF  ef_b_set_state                  ;  4 set.state
        EF  ef_zero                         ;  5 print (never called)
        EF  ef_b_unclaim                    ;  6 unclaim
        EF  ef_b_release                    ;  7 release
        EF  ef_b_find_target                ;  8 find.target
        EF  ef_b_aim                        ;  9 aim
        EF  ef_zero                         ; 10 (never called)
        EF  ef_b_fire                       ; 11 fire
        EF  ef_zero                         ; 12 (0)
        EF  ef_b_state                      ; 13 state
        EF  ef_zero                         ; 14 (never called)
        EF  ef_b_unfog                      ; 15 unfog
        EF  ef_zero                         ; 16 (0)
        EF  ef_zero                         ; 17 (0)
        EF  ef_zero                         ; 18 (0)
        EF  ef_zero                         ; 19 (0)
        EF  ef_zero                         ; 20 (0)
        EF  ef_b_refine                     ; 21 refine
        EF  ef_b_explode                    ; 22 explode
        EF  ef_b_destroy                    ; 23 destroy
        EF  ef_zero                         ; 24 (0)

; ------------------------------------------------------------ the routines

ef_zero:
        ld  hl, 0
        ret

; emc_delay ($01108A): the top of the stack / 5 (towards zero) into the
; delay word; answers it.
ef_delay:
        xor a
        call emc_arg
        ld  de, 5
        call sdiv16
ef_set_delay:
        ld  (ix - 2), l
        ld  (ix - 1), h
        ret

; emc_delay_random ($0110A6): (n * random + $50) >> 8, then / 5.
ef_delay_rnd:
        xor a
        call emc_arg
        call random
        ld  e, a
        ld  d, 0
        call mul_shr8
        ld  de, 5
        call sdiv16
        jr  ef_set_delay

; emc_unit_random ($0110D8): rand_between(top, the word under it), bytes.
ef_random:
        ld  a, 1
        call emc_arg
        push hl
        xor a
        call emc_arg
        pop de
        ld  d, l                ; D = low (the top), E = high
        call rand_between
        ld  l, a
        ld  h, 0
        ret
