; combat/world.inc - the COMBAT subsystem's share of WORLD (window 2):
; only what other banks or the renderer must see.  Budget: 400 bytes.
;
; ------------------------------------------------ the explosion animations
;
; The cartridge keeps them in a pool shared with the map animations
; ($FFC8C8, running list $FFD2FC, free list $FFD2F8) and plays the 24
; scripts of $0C80A2 (fx_explosion_start $00AEDA, fx_explosion_tick
; $00B224).  The port keeps FX_COUNT entries here, for the renderer to
; draw; COMBAT (src/combat/combat.asm) starts and steps them.
;
; An entry, FX_SIZE bytes:
;
;   +0  w  y       the position, 1/256 of a square (as a unit's +$0A),
;   +2  w  x       low byte first; pixel = word >> 3
;   +4  w  frame   what to draw now: a frame id of src/res/art/sprites.txt
;                  (0-318), or
;                    FX_BLANK ($FFFF)   nothing this step (effects.txt '-')
;                    FX_SMOKE | id      bit 15 set: the smoke; id is the
;                                       frame of smoke phase 0 (285), and
;                                       the frame drawn is id + the phase
;                                       (0-2) of the cartridge's global
;                                       smoke cycle ($00B028)
;   +6  w  ticks   game frames left in this step (counted down by
;                  frames_this_pass)
;   +8  b  house   the house whose palette line a house-coloured frame
;                  (315, 316: house-p{L}.png) is drawn in - what the
;                  cartridge passes: 3 from map_make_explosion, 0 for type
;                  19, the dead unit's house for types 20/21
;   +9  b  step    0: the entry is free.  Otherwise COMBAT's own position
;                  in its step table (fx_steps, 1-based) - the renderer
;                  needs only "nonzero".
;
; Entries are in no order; the renderer draws every entry whose +9 is not
; 0 and whose frame is not FX_BLANK.

FX_COUNT        EQU 32          ; the cartridge's pool has 162 (S4); a
                                ; wreck holds an entry for 600 ticks and a
                                ; fight fills 16 - then fx_explosion_start
                                ; retires the oldest wreck or smoke
FX_SIZE         EQU 10
FX_Y            EQU 0
FX_X            EQU 2
FX_FRAME        EQU 4
FX_TICKS        EQU 6
FX_HOUSE        EQU 8
FX_STEP         EQU 9
FX_BLANK        EQU $FFFF
FX_SMOKE        EQU $8000

; fx_list, FX_COUNT * FX_SIZE bytes, is reserved at the end of
; world_vars.inc: 320 bytes fit only after the page-aligned front tables.

; ------------------------------------------------------------ the Palace
house_missile:  DW  0           ; $FFC1A0 the Death Hand waiting to be
                                ; launched: the unit record (W1), 0 none
house_missile_count: DW 0   ; $FFC1A4 the player's 7-step countdown
special_target_square: DW 0     ; $FFC1A8 the square the player picked for
                                ; the Palace's weapon (0: none)
