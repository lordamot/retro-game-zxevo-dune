; moves2.asm - bank MOVE2: more of the MOVE subsystem.
;
; ================================================ the effect animations
;
; A unit's effect animation (fx_anim_start $00A74E, fx_anim_tick $00A786):
; for a number of frames its sprite blinks, and the sound it started with
; comes round again at every blink.  The Mega Drive runs three:
;
;   an MCV told to deploy on its own square      8, 255 frames, sound $2E
;   the player's Devastator told to Guard itself 8, 255 frames, sound $2E
;     (both: flags2 bit 7; when it runs out the unit loop deploys the MCV
;     or orders the Devastator to Die, $043C72)
;   an enemy unit the player orders an attack on 6, 24 frames, sound $24
;     (flags2 bit 11, the target's flash; $04390A ticks it)
;
; all three started by the order click (ui_battle_button $027F8E-$028190,
; here unit_fx_order).  A new order stops a pending deploy or self-destruct,
; and B on the unit ($0284F0, unit_fx_press_b) makes it happen at once.
; Nothing else - no script, no AI - starts one.
;
; The blink is the sprite engine's (spr_render $0010D8, every frame): with
; its counter above 0 the sprite shows and the counter goes down; at 0 the
; counter is reloaded with the period and the sprite is off for that frame.
; A unit's sprite gets no phase bit (anim_make_sprite $00950C), so it is
; off one frame in period + 1.  The port has no per-frame sprite engine:
; fx_anim_tick runs the counter for the frames of the pass and leaves bit 7
; of U_BLINK set if one of them was off, and the renderer leaves the unit
; out of that pass's picture.  The sound comes round whenever the counter
; reached 0 during the pass - on the cartridge, whenever the tick found it
; at 0, which at its pass of one frame is every period + 1 frames too.

; fx_anim_start ($00A74E): IX = the unit, A = the sound effect, B = the
; blink period (frames), C = the life (frames).  The sound plays now and is
; kept for the blinks.  Keeps IX, IY.
fx_anim_start:
        ld  (ix + U_FXSOUND), a
        ld  (ix + U_FXLIFE), c
        ld  (ix + U_BLINK), b
        ld  (ix + U_BLINKPERIOD), b
        push ix
        FCALL snd_effect
        pop ix
        ret

; fx_anim_tick ($00A786): IX = the unit.  The frames of this pass come off
; the life; when it has run out the blink stops and the answer is Z (A = 0),
; otherwise NZ - and each time the blink counter reached 0 the kept sound
; is played again.  Keeps IX, IY.
fx_anim_tick:
        ; the blink, a frame at a time (spr_render $0010D8)
        ld  hl, (frames_this_pass)
        ld  a, h
        or  a
        ld  b, l
        jr  z, mv_fxt_0
        ld  b, 255              ; a pass that long: 255 frames will do
mv_fxt_0:
        ld  c, 0                ; bit 0 a frame off, bit 1 the counter at 0
        ld  a, (ix + U_BLINKPERIOD)
        or  a
        jr  z, mv_fxt_life      ; not blinking
        ld  d, a
        ld  a, (ix + U_BLINK)
        and $7F
        inc b
        dec b
        jr  z, mv_fxt_store
mv_fxt_frame:
        or  a
        jr  z, mv_fxt_reload
        dec a
        jr  nz, mv_fxt_next
        set 1, c                ; at 0: the sound comes round
        jr  mv_fxt_next
mv_fxt_reload:
        ld  a, d                ; reloaded, and this frame it is off
        set 0, c
mv_fxt_next:
        djnz mv_fxt_frame
mv_fxt_store:
        bit 0, c
        jr  z, mv_fxt_st1
        or  $80
mv_fxt_st1:
        ld  (ix + U_BLINK), a
mv_fxt_life:
        ; the life ($00A792): less the frames of the pass
        ld  e, (ix + U_FXLIFE)
        ld  d, 0
        ex  de, hl
        ld  de, (frames_this_pass)
        or  a
        sbc hl, de
        jr  z, mv_fxt_end
        jp  m, mv_fxt_end
        ld  (ix + U_FXLIFE), l
        ; the counter was at 0: the kept sound again ($00A7BC)
        bit 1, c
        jr  z, mv_fxt_run
        ld  a, (ix + U_FXSOUND)
        or  a
        jr  z, mv_fxt_run
        push ix
        FCALL snd_effect
        pop ix
mv_fxt_run:
        or  1
        ret
mv_fxt_end:
        ; the end ($00A79E): the sprite's counter and period cleared, its
        ; blink off, the life 0
        xor a
        ld  (ix + U_FXLIFE), a
        ld  (ix + U_BLINK), a
        ld  (ix + U_BLINKPERIOD), a
        ret

; unit_fx_order: the effect animations an order click starts or stops
; (ui_battle_button $027F8E-$028190).  IX = the player's unit being given
; the order, A = the order the click chose - ORDER_DEPLOY for an MCV on its
; own square, ORDER_GUARD for any other unit on its own square - HL = the
; other house's unit on the square (0 none), DE = the structure there (0
; none).  -> A = the order to give.  Keeps IX, IY.
;
;   The MCV ($027F8E).  On its own square it is told to Stop, and if no
;   deploy is under way and a Construction Yard may stand there ($00F0FC,
;   the MCV taken off its square for the question) the deploy animation
;   starts; if one may not, sound $2F.  On its own square again with the
;   deploy under way, or sent anywhere else, the deploy stops.
;   An other house's unit on a square with no structure ($02810C): it is
;   marked (flags2 bit 11) and flashes; not for an MCV or a Harvester,
;   which have orders of their own.
;   The Devastator ($02813E): a self-destruct under way stops at any new
;   order; on its own square (Guard) one starts.
unit_fx_order:
        ld  (mv_fx_ord), a
        push iy
        ld  a, (ix + O_TYPE)
        cp  UNIT_MCV
        jr  z, mv_fxo_mcv
        cp  UNIT_HARVESTER
        jp  z, mv_fxo_done
        ; the target flashes
        ld  a, d
        or  e
        jr  nz, mv_fxo_dev
        ld  a, h
        or  l
        jr  z, mv_fxo_dev
        push ix
        push hl
        pop ix
        set 3, (ix + O_FLAGS2 + 1)      ; flags2 bit 11
        ld  a, $24
        ld  bc, (6 << 8) | $18
        call fx_anim_start
        pop ix
mv_fxo_dev:
        ld  a, (ix + O_TYPE)
        cp  UNIT_DEVASTATOR
        jp  nz, mv_fxo_done
        bit 7, (ix + O_FLAGS2)
        jr  nz, mv_fxo_stop
        ld  a, (mv_fx_ord)
        cp  ORDER_GUARD
        jr  nz, mv_fxo_done
        jr  mv_fxo_start
mv_fxo_mcv:
        ld  a, (mv_fx_ord)
        cp  ORDER_DEPLOY
        jr  nz, mv_fxo_stop     ; elsewhere: it goes, the deploy stops
        ld  a, ORDER_STOP
        ld  (mv_fx_ord), a
        bit 7, (ix + O_FLAGS2)
        jr  nz, mv_fxo_stop     ; again: the deploy stops
        ; may a Yard stand on its square?  Not counting the MCV ($027FB0)
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  (mv_fx_sq), hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  (hl), 0
        ld  hl, (mv_fx_sq)
        ld  a, STRUCT_CONSTYARD
        push ix
        FCALL struct_check_location
        pop ix
        ld  a, h
        or  l
        ld  (mv_fx_ok), a
        ld  hl, (mv_fx_sq)
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (ix + O_INDEX)
        inc a
        ld  (hl), a             ; the MCV back on its square ($028008)
        ld  a, (mv_fx_ok)
        or  a
        jr  nz, mv_fxo_start
        ld  a, $2F              ; no room
        push ix
        FCALL snd_effect
        pop ix
        jr  mv_fxo_done
mv_fxo_start:
        ; the deploy or self-destruct: bit 7, the animation ($027FCE)
        set 7, (ix + O_FLAGS2)
        ld  a, $2E
        ld  bc, (8 << 8) | 255
        call fx_anim_start
        jr  mv_fxo_done
mv_fxo_stop:
        ; ($028178) bit 7 goes, the life is spent and the blink stops
        res 7, (ix + O_FLAGS2)
        ld  (ix + U_FXLIFE), 0
        call fx_anim_tick
mv_fxo_done:
        pop iy
        ld  a, (mv_fx_ord)
        ret

; unit_fx_press_b: B pressed with a unit selected ($0284F0).  A = the
; selected unit's slot ($FF none).  -> NZ if it has a deploy or
; self-destruct pending: its life is spent and its blink stopped, so the
; unit loop carries it out on the unit's next tick, and the unit stays
; selected.  Z otherwise (B goes on as usual).  Keeps IX, IY.
unit_fx_press_b:
        cp  $FF
        jr  z, mv_fxb_no
        push ix
        call unit_ptr
        push hl
        pop ix
        bit 7, (ix + O_FLAGS2)
        jr  z, mv_fxb_no1
        ld  (ix + U_FXLIFE), 0
        call fx_anim_tick
        pop ix
        or  1
        ret
mv_fxb_no1:
        pop ix
mv_fxb_no:
        xor a
        ret

; ------------------------------------------------ the bank's own scratch
mv_fx_ord:      DB 0
mv_fx_ok:       DB 0
mv_fx_sq:       DW 0
