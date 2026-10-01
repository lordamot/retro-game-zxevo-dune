; world.asm - page WORLD, window 2 ($8000-$BFFF), mapped for good once the
; game has started.  The globals, the constant tables, the structures and
; the stack.  Assembled as a page image: what is written here is the
; starting value.

        ORG $8000

; ------------------------------------------------------------ debug block
;
; At a fixed address so a test can poke it before the game starts
; (bin/evo/evo-run: `pokepage 25 OFFSET VALUE`) and tools/build_dune.py can
; set it from `make run HOUSE=... MISSION=...`.  See .claude/docs/port.md.
dbg_block:
dbg_magic:      DB "DBG0"       ; +0  so a tool can check it found the block
dbg_house:      DB $FF          ; +4  $FF: normal front end; else start this
                                ;     house (0 Harkonnen 1 Atreides 2 Ordos)
dbg_mission:    DB 1            ; +5  ... on this mission (1-9)
dbg_flags:      DB 0            ; +6  bit 0 reveal the map, bit 1 player takes
                                ;     no damage, bit 2 fast production,
                                ;     bit 3 no sound, bit 4 stop after the
                                ;     first frame of the battle (for tests),
                                ;     bit 5 (DBGF_NOLOAD) only the intro's
                                ;     tune goes to the sound card, nothing
                                ;     is loaded later (a test of the card),
                                ;     bit 6 (DBGF_NOJOY) the joystick port
                                ;     is never read - the keys only
DBGF_NOJOY      EQU 64
dbg_credits:    DW 0            ; +7  nonzero: the player's credits at start
dbg_flags2:     DB 0            ; +9  bit 0 (DBGF2_TEST1MB): the sound card
                                ;     taken for 1 MB (30 pages), the intro
                                ;     and the lego tune the only tunes on
                                ;     it, nothing streamed, every tune not
                                ;     on the card played as the lego tune -
                                ;     a test build for a card that sounds
                                ;     wrong (build_dune.py --flags2 1)
DBGF2_TEST1MB   EQU 1
dbg_spare:      DS 6            ; +10
                ; +16

; ------------------------------------------------------------ test mailbox
;
; tools/dune_test.py drives the game this way: with dbg_flags bit 7 set,
; the MAIN bank waits for tst_state = 1, maps tst_w1/tst_w3 (0 = the game's
; own), puts the registers in, far-calls tst_bank:tst_addr, stores the
; registers it comes back with, and sets tst_state = 2.  At $8010, fixed.
        ASSERT $ == $8010
tst_state:      DB 0            ; +0  0 idle, 1 a call is asked for, 2 done
tst_w1:         DB 0            ; +1  page for window 1 during the call, 0 UNITS
tst_w3:         DB 0            ; +2  page for window 3, 0 MAP
tst_bank:       DB 0            ; +3
tst_addr:       DW 0            ; +4
tst_in:         DS 12           ; +6  AF BC DE HL IX IY going in
tst_out:        DS 12           ; +18 the same coming out
tst_calls:      DW 0            ; +30 calls made
tst_scratch:    DS 16           ; +32 for the tests' own data
                ; $8040

; ----------------------------------------------------- the stub's globals
cur_bank:       DB 0            ; the code bank in window 0
cur_w1:         DB 0
cur_w3:         DB 0
fc_bank:        DB 0
fc_save_a:      DB 0
fc_save_hl:     DW 0
fc_jump:        jp  0           ; far_call's target, written in place
frame_count:    DW 0            ; +1 every frame interrupt (frameCount)
flip_req:       DB 0            ; set: the interrupt shows the other screen
port_7ffd:      DB P7FFD_BASE   ; what is in $7FFD (it cannot be read back)
timer_game_on:  DB 0            ; S1 timerGameOn
timer_gui_on:   DB 0            ; S1 timerGUIOn
timer_game:     DD 0            ; S1 timerGame, +1 a frame while on
timer_gui:      DD 0            ; S1 timerGUI
rnd_seed:       DB $12, $34, $56 ; math_random's three bytes ($FFE017-19)
pad_held:       DB 0            ; the pad now (stub/input.asm)
pad_press:      DB 0            ; buttons pressed since pad_take
pad_keys:                       ; per PAD_ button two keys: half-row, bit
        DB $FB, $01, $EF, $08   ; up      Q, 7
        DB $FD, $01, $EF, $10   ; down    A, 6
        DB $DF, $02, $F7, $10   ; left    O, 5
        DB $DF, $01, $EF, $04   ; right   P, 8
        DB $7F, $01, $7F, $04   ; A       SPACE, M
        DB $FE, $02, $7F, $08   ; B       Z, N
        DB $FE, $04, $7F, $02   ; C       X, SYMBOL SHIFT
        DB $BF, $01, $00, $00   ; Start   ENTER

; ------------------------------------------------------------ the screens
draw_a:         DB PG_SCR1_A    ; the screen being drawn (not the one shown)
draw_b:         DB PG_SCR1_B

        ASSERT $ <= STRUCTS_BASE

; ------------------------------------------------------ the structures
        ORG STRUCTS_BASE
structs:        DS  S_SIZE * STRUCT_COUNT, 0
structs_end:

; ------------------------------------------------ the big record tables
        INCLUDE "tbl_world.inc"
tables_end:

        INCLUDE "world_vars.inc"
world_vars_end:
        ASSERT $ <= $C000 - STACK_SIZE

; ------------------------------------------------------------- the stack
        ORG $C000 - STACK_SIZE
stack_bottom:
        DS  STACK_SIZE, $00
STACK_TOP       EQU $C000
