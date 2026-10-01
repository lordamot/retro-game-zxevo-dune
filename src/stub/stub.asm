; stub.asm - the first bytes of every code bank.
;
; Code runs in window 0, one 16 KB bank at a time, and every bank starts
; with this file - assembled at the same address, so the same bytes.  That
; is what lets far_call switch window 0 from inside window 0: the next
; instruction comes from the new bank, and it is the same instruction.
; tools/build_dune.py checks that every bank's stub is identical.
;
; Everything here may use only its own labels and the globals in WORLD
; (window 2, never switched).  Nothing in it may depend on which bank it is
; running in.

        ORG $0000
stub_start:
        di
        jp  stub_reset

; ------------------------------------------------------------ page switching
;
; A = the page.  Clobber A only.

map_w1:
        ld  (cur_w1), a
        push bc
        cpl
        ld  bc, MMU_W1
        out (c), a
        pop bc
        ret

map_w3:
        ld  (cur_w3), a
        push bc
        cpl
        ld  bc, MMU_W3
        out (c), a
        pop bc
        ret

; Put the game's own data back: units in window 1, the map in window 3.
map_game:
        ld  a, PG_UNITS
        call map_w1
        ld  a, PG_MAP
        jr  map_w3

        DS  $0038 - $, $00
        jp  isr

        DS  $0066 - $, $00
        retn                    ; the NMI button: ignored

; ------------------------------------------------------------- far calls
;
;   FCALL label   =   call far_call : db page : dw address
;
; The target's bank goes in window 0, the target is called with every
; register as the caller left it (bar the flags), and on the way back the
; caller's bank is put back with every register as the target left it,
; flags included.

far_call:
        ld  (fc_save_hl), hl
        ld  (fc_save_a), a
        pop hl                  ; -> the inline page and address
        ld  a, (hl)
        inc hl
        ld  (fc_bank), a
        ld  a, (hl)
        inc hl
        ld  (fc_jump + 1), a
        ld  a, (hl)
        inc hl
        ld  (fc_jump + 2), a
        push hl                 ; where to come back to
        ld  a, (cur_bank)
        push af                 ; the bank to come back to (A is the high byte)
        ld  hl, far_ret
        push hl
        ld  a, (fc_bank)
        ld  (cur_bank), a
        push bc
        cpl
        ld  bc, MMU_W0
        out (c), a              ; from here on we are in the target's bank
        pop bc
        ld  a, (fc_save_a)
        ld  hl, (fc_save_hl)
        jp  fc_jump

far_ret:
        ex  (sp), hl            ; H = the caller's bank; the result HL saved
        push af
        push bc
        ld  a, h
        ld  (cur_bank), a
        cpl
        ld  bc, MMU_W0
        out (c), a
        pop bc
        pop af
        pop hl
        ret

; far_call_ind: the same, with the page and address in memory at HL
; (3 bytes) instead of inline.  HL and A are not passed through.
far_call_ind:
        ld  a, (hl)
        inc hl
        ld  (fc_bank), a
        ld  a, (hl)
        inc hl
        ld  (fc_jump + 1), a
        ld  a, (hl)
        ld  (fc_jump + 2), a
        jr  fcm_go

; far_call_mem: the target already in fc_bank and fc_jump; every register
; passes through.
far_call_mem:
        ld  (fc_save_hl), hl
        ld  (fc_save_a), a
fcm_go: ld  a, (cur_bank)
        push af
        ld  hl, far_ret
        push hl
        ld  a, (fc_bank)
        ld  (cur_bank), a
        push bc
        cpl
        ld  bc, MMU_W0
        out (c), a
        pop bc
        ld  a, (fc_save_a)
        ld  hl, (fc_save_hl)
        jp  fc_jump

; far_jump: as far_call, but for good (no way back): used to change the
; main flow between banks.  The inline bytes are the same as FCALL's.
far_jump:
        pop hl
        ld  a, (hl)
        inc hl
        ld  (cur_bank), a
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        cpl
        ld  bc, MMU_W0
        out (c), a
        jp  (hl)


; ------------------------------------------------------- the frame interrupt
;
; IM 1.  Counts frames, runs the game clock (S1: the battle's frame hook
; advances timerGame and timerGUI only while they are switched on), and
; shows the other screen when the main loop has asked for it.
isr:
        push af
        push hl
        ld  hl, (frame_count)
        inc hl
        ld  (frame_count), hl
        ; the crash catcher (world_vars.inc wd_*, front/front.asm
        ; front_crash): the interrupted PC is under af and hl; the byte
        ; before it is HALT when the game is waiting for a frame, which
        ; is fine and clears the count.  Otherwise the count grows, and
        ; at WD_LIMIT the game is stuck or running garbage: crash_go.
        ld  a, (wd_armed)
        or  a
        jr  z, isr_wd_done
        ld  hl, 4
        add hl, sp
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        dec hl
        ld  a, (hl)
        cp  $76
        jr  nz, isr_wd_busy
        ld  hl, 0
        ld  (wd_idle), hl
        jr  isr_wd_done
isr_wd_busy:
        inc hl
        ld  (wd_pc), hl
        ld  hl, (wd_idle)
        inc hl
        ld  (wd_idle), hl
        ld  a, h
        cp  HIGH WD_LIMIT
        jr  c, isr_wd_done
        jr  nz, isr_wd_crash
        ld  a, l
        cp  LOW WD_LIMIT
        jr  c, isr_wd_done
isr_wd_crash:
        ld  hl, 6               ; the interrupted SP: past af, hl, the PC
        add hl, sp
        ld  (wd_sp), hl
        xor a
        ld  (wd_why), a
        jr  crash_go
isr_wd_done:
        ld  a, (timer_game_on)
        or  a
        jr  z, isr_no_game
        ld  hl, timer_game
        inc (hl)
        jr  nz, isr_no_game
        inc hl
        inc (hl)
        jr  nz, isr_no_game
        inc hl
        inc (hl)
isr_no_game:
        ld  a, (timer_gui_on)
        or  a
        jr  z, isr_no_gui
        ld  hl, timer_gui
        inc (hl)
        jr  nz, isr_no_gui
        inc hl
        inc (hl)
        jr  nz, isr_no_gui
        inc hl
        inc (hl)
isr_no_gui:
        ld  a, (flip_req)
        or  a
        jr  z, isr_done
        push bc
        ld  a, (port_7ffd)
        xor 8
        ld  (port_7ffd), a
        ld  bc, PORT_7FFD
        out (c), a
        pop bc
        xor a
        ld  (flip_req), a
isr_done:
        push bc
        push de
        call pad_read
        pop de
        pop bc
        pop hl
        pop af
        ei
        ret

; -------------------------------------------------------------- reset
; Nothing jumps to 0 on purpose, so anything that lands here has crashed:
; the crash screen, with the stack it came with (the top word is usually
; the return address it fell through).
stub_reset:
        ld  (wd_sp), sp
        ld  hl, 0
        ld  (wd_pc), hl
        ld  a, 1
        ld  (wd_why), a
        ; fall through

; ------------------------------------------------------- the crash screen
; wd_pc, wd_sp, wd_why set: keep the top of that stack before this one
; grows over it, put WORLD and the FRONT bank in their windows and show
; it.  Interrupts off until front_crash has disarmed the catcher.
crash_go:
        di
        ld  a, (cur_bank)
        ld  (wd_bank), a
        ld  a, 1
        out (PORT_BF), a        ; the shadow ports, whatever happened
        ld  a, (PG_WORLD ^ $3F) | $40
        ld  bc, MMUF_W2
        out (c), a
        xor a
        ld  (wd_armed), a
        ld  hl, (wd_sp)
        ld  de, wd_stack
        ld  bc, 16
        ldir
        ld  sp, STACK_TOP
        ld  a, PG_FRONT
        ld  (cur_bank), a
        cpl
        ld  bc, MMU_W0
        out (c), a
        jp  front_crash         ; in PG_FRONT, which is now mapped

; ------------------------------------------------------- script arguments
; A routine an EMC script calls finds its arguments on the script's stack,
; the first at stack[sp] (S7: the caller drops them afterwards).  IX = the
; script state, A = which argument (0 = the top) -> HL = it.  Clobbers DE.
emc_arg:
        add a, (ix + SC_SP)
        add a, a
        add a, SC_STACK
        ld  e, a
        ld  d, 0
        push ix
        pop hl
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ret

        INCLUDE "core.asm"
        INCLUDE "maths.asm"
        INCLUDE "random.asm"
        INCLUDE "video.asm"
        INCLUDE "input.asm"

stub_end:
