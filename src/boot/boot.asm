; boot.asm - where the SPG starts: page 2 at $8000.
;
; The SPG loader leaves window 0 on a ROM, windows 1 and 2 on pages 5 and 2
; and window 3 on the page the header names.  This opens the configuration
; ports, puts the clock at 14 MHz, clears each window's "mix with $7FFD"
; flag by mapping it once with the long xxFF7 form, and jumps into the MAIN
; bank, which maps window 2 (where this is running) itself.

        ORG $8000
boot:
        di
        ld  a, 1
        out (PORT_BF), a        ; the shadow ports answer from here on
        ld  bc, PORT_77
        ld  a, V_ZX | TURBO14
        out (c), a              ; manager on, 14 MHz, the plain screen for now
        ld  a, P7FFD_BASE
        ld  bc, PORT_7FFD
        out (c), a
        xor a
        ld  bc, PORT_EFF7
        out (c), a
        ld  a, (PG_MAIN ^ $3F) | $40
        ld  bc, MMUF_W0
        out (c), a
        ld  a, (PG_UNITS ^ $3F) | $40
        ld  bc, MMUF_W1
        out (c), a
        ld  a, (PG_MAP ^ $3F) | $40
        ld  bc, MMUF_W3
        out (c), a

; Zero every byte the SPG did not fill: the pages it has no block for and
; the tail of every page it trims (tools/build_dune.py writes the table).
; A real machine's RAM is random at power-on and the game trusted zeros in
; places - the emulator's RAM is zero, so it never showed.  No calls: the
; stack is in this page.
        ld  ix, boot_clear_table
bc_loop:
        ld  a, (ix + 0)
        cp  $FF
        jr  z, bc_done
        cpl
        ld  bc, MMU_W3
        out (c), a              ; the page in window 3
        ld  a, (ix + 1)         ; from this 512-byte unit
        add a, a
        or  $C0
        ld  h, a
        ld  l, 0
        ld  d, h
        ld  e, 1
        xor a
        ld  (hl), a
        sub l
        ld  c, a
        ld  a, 0
        sbc a, h
        ld  b, a                ; BC = $10000 - HL ...
        dec bc                  ; ... less one: the bytes to $FFFF
        ldir
        inc ix
        inc ix
        jr  bc_loop
bc_done:
        ld  a, (PG_MAP ^ $3F) | $40
        ld  bc, MMUF_W3
        out (c), a
        jp  main_init

boot_clear_table:
        DS  2 * 224 + 1, $FF    ; (page, unit) pairs, $FF the end
