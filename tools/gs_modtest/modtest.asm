; modtest.asm - hand a ProTracker module to the General Sound card's own
; ROM player and let it play.
;
; Built and driven by tools/gs_modtest.py, which puts this at $7000, the
; module on the disk in pieces, and a BASIC program that calls:
;
;   $7000  wait for the card to finish its memory test, then send $30
;          "load module": from here on every data byte is the module's
;   $7003  stream one piece, loaded at $8000: a 16-bit length, then that
;          many bytes of the module
;   $7006  send $D2 to close the stream, then $31 "play module" with the
;          handle $30 gave back
;
; The card's ROM is v1.05a; the three traps in .claude/docs/sound.md apply,
; and the one that matters here is that a command's first argument goes to
; the data port *before* the command.  $30 takes none and answers the
; module's handle; $31 takes the handle first.

GS_DATA         EQU $B3
GS_CMD          EQU $BB
GS_IDLE         EQU $7E         ; neither latch has anything in it
GS_SETTLE       EQU 16          ; frames it has to stay that way

        ORG $7000

        jp  load
        jp  piece
        jp  play

; the card tests its memory after power-on and the status flickers while
; it does: wait for it to sit still at idle for a quarter of a second
load:
        ei
        ld  b, 250
ld_l:   push bc
        ld  c, GS_SETTLE
ld_s:   halt
        in  a, (GS_CMD)
        and $81
        cp  GS_IDLE & $81
        jr  nz, ld_no
        dec c
        jr  nz, ld_s
        pop bc
        jr  ld_go
ld_no:  pop bc
        djnz ld_l
ld_go:  ld  a, $30
        call cmd
        call recv
        ld  (handle), a
        ret

piece:
        ld  hl, $8000
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        inc hl
pc_l:   ld  a, b
        or  c
        ret z
        call wdata
        ld  a, (hl)
        out (GS_DATA), a
        inc hl
        dec bc
        jr  pc_l

play:
        ld  a, $D2
        call cmd
        call wdata
        ld  a, (handle)
        out (GS_DATA), a
        ld  a, $31
        call cmd
        jp  wcmd

; wait for the card to take the last command, then send A
cmd:    push af
        call wcmd
        pop af
        out (GS_CMD), a
        ret

wcmd:   in  a, (GS_CMD)
        rrca
        jr  c, wcmd
        ret

; wait until the card has taken the last data byte
wdata:  in  a, (GS_CMD)
        rlca
        jr  c, wdata
        ret

; the card's answer to a command.  $30's handler puts the handle in the
; latch (`OUT (3)`, $43ED) and then reads the data port (`IN (2)`, $43EF),
; and that read clears the one flag both directions share - so waiting for
; bit 7 waits for ever.  The answer is there once the command is taken.
recv:   call wcmd
        in  a, (GS_DATA)
        ret

handle: db  0
