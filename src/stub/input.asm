; input.asm - the keyboard and a Kempston joystick as a Mega Drive pad.
; Part of the stub: the frame interrupt calls pad_read, so the pad is
; sampled every frame however long the game's pass takes.
;
;   up, down, left, right   Q A O P, the arrows (CAPS + 7 6 5 8), 7 6 5 8
;   A  (select / order)     SPACE, M, fire
;   B  (back)               Z, N
;   C  (move the view)      X, SYMBOL SHIFT (hold)
;   Start (options)         ENTER
;
; A half-row goes out on the top of the address bus from A (IN A,(n) puts
; A there, not B), and a key is held while its bit is 0.

PAD_UP          EQU 0
PAD_DOWN        EQU 1
PAD_LEFT        EQU 2
PAD_RIGHT       EQU 3
PAD_A           EQU 4
PAD_B           EQU 5
PAD_C           EQU 6
PAD_START       EQU 7

; Clobbers A, BC, DE, HL.  pad_held = what is down now; pad_press gathers
; the buttons that went down since the game last took them (pad_take).
; The keys are WORLD's pad_keys, two a button in the order of the PAD_
; bits, each its half-row and its bit (0: none) - the layout above until
; the front end's REDEFINE KEYS changes it; the joystick is always read.
pad_read:
        ld  hl, pad_keys
        ld  bc, $0801           ; B = the buttons, C = this one's bit
        ld  e, 0
pr_btn: ld  d, 2
pr_key: ld  a, (hl)             ; the half-row
        inc hl
        in  a, (PORT_FE)
        cpl
        and (hl)                ; the key's bit: set while it is held
        inc hl
        jr  z, pr_up
        ld  a, e
        or  c
        ld  e, a
pr_up:  dec d
        jr  nz, pr_key
        rlc c
        djnz pr_btn
        ; Kempston: 000FUDLR, 1 = pressed.  The port answers only while
        ; the shadow ports are shut (the manual: "#xx1F RO noshad"); open,
        ; it is the floppy controller's or nothing at all - and nothing at
        ; all reads as the byte the video is fetching, random presses every
        ; frame on a real machine.  So shut them for the one read.  The
        ; manager's settings are latched and stay.
pr_15:  ld  a, (dbg_flags)
        and DBGF_NOJOY          ; a test build: the keys only
        jr  nz, pr_16
        xor a
        out (PORT_BF), a
        in  a, ($1F)
        ld  d, a
        ld  a, 1
        out (PORT_BF), a
        ld  a, d
        and $E0                 ; a real interface reads 0 in bits 5-7; with
        jr  nz, pr_16           ; anything else there, nothing is plugged in
        ld  a, d
        and %00001111
        cp  %00000011           ; left and right, or up and down, together:
        jr  z, pr_16            ; no stick does that, the port is floating
        and %00001100
        cp  %00001100
        jr  z, pr_16
        ld  a, d
        rra
        jr  nc, pr_k1
        set PAD_RIGHT, e
pr_k1:  rra
        jr  nc, pr_k2
        set PAD_LEFT, e
pr_k2:  rra
        jr  nc, pr_k3
        set PAD_DOWN, e
pr_k3:  rra
        jr  nc, pr_k4
        set PAD_UP, e
pr_k4:  rra
        jr  nc, pr_16
        set PAD_A, e
pr_16:  ld  a, (pad_held)
        cpl
        and e                   ; went down this frame
        ld  d, a
        ld  a, (pad_press)
        or  d
        ld  (pad_press), a
        ld  a, e
        ld  (pad_held), a
        ret

; A = the buttons pressed since the last call (and forget them).
pad_take:
        di
        ld  a, (pad_press)
        push af
        xor a
        ld  (pad_press), a
        pop af
        ei
        ret
