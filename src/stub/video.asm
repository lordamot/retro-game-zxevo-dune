; video.asm - the screen: mode, palette, the two screens.  Part of the stub.
;
; ATM EGA, 320x200 in 16 of 64 colours, four planes over two pages (evo.inc
; has the layout).  There are two screens; the game always draws on the
; one that is not showing (draw_a/draw_b) and asks the interrupt to swap
; them (vid_flip), so nothing is ever seen half drawn.

; EGA mode at 14 MHz.
vid_ega:
        ld  bc, PORT_77
        ld  a, V_EGA | TURBO14
        out (c), a
        ret

; HL = sixteen palette bytes (tools/dune_art.py makes them: the colour
; inverted, the channel bits spread over the byte as the port wants).
;
; A write to port $FF changes the entry of the colour the beam is showing
; at that moment (the BaseConf manual, 7.2) - which is only the border
; register's colour while the beam is in the border.  So the sixteen
; writes are done right after the frame interrupt, in the top border,
; when interrupts are enabled (the emulator takes the border register
; always and never showed the difference: on a real machine writes in the
; picture land in whatever colour is under the beam, and every screen came
; out in the wrong colours).  With interrupts off the writes go out at
; once, wherever the beam is.
;
; The index is the border register.  Its low three bits come from the
; value and the fourth from address line A3, inverted - so entries 8-15 go
; out through port $F6.  The border is latched once a scanline, so each
; entry waits a line before its colour goes to port $FF: sixteen entries
; take about twenty lines of the border's eighty.
; Clobbers A, BC, DE, HL.
vid_palette:
        ld  a, i
        jp  po, vp_start        ; interrupts off: no frame to wait for
        ld  a, (frame_count)
vp_sync:
        ld  d, a
        ld  a, (frame_count)
        cp  d
        jr  z, vp_sync          ; the interrupt has just run: top border
vp_start:
        ld  d, 0                ; the entry
vp_loop:
        ld  a, d
        and 7
        ld  c, PORT_FE
        bit 3, d
        jr  z, vp_low
        ld  c, PORT_F6
vp_low:
        ld  b, 0
        out (c), a
        ld  bc, 40              ; over a scanline at 14 MHz (896 T)
vp_wait:
        dec bc
        ld  a, b
        or  c
        jr  nz, vp_wait
        ld  a, (hl)
        out (PORT_FF), a
        inc hl
        inc d
        ld  a, d
        cp  16
        jr  nz, vp_loop
        xor a
        out (PORT_FE), a        ; border black
        ret

; Map the drawing screen's page A (planes 0 and 2) or B (1 and 3) into
; window 3.  Clobbers A.
vid_map_a:
        ld  a, (draw_a)
        jp  map_w3
vid_map_b:
        ld  a, (draw_b)
        jp  map_w3

; Show the screen just drawn, at the next frame interrupt, and wait for it;
; then aim the drawing at the other one.  Clobbers A.
vid_flip:
        ld  a, 1
        ld  (flip_req), a
vf_wait:
        ld  a, (flip_req)
        or  a
        jr  nz, vf_wait
        ld  a, (port_7ffd)
        and 8                   ; showing screen 1?
        ld  a, PG_SCR0_A
        jr  nz, vf_set          ; then draw on screen 0
        ld  a, PG_SCR1_A
vf_set:
        ld  (draw_a), a
        xor 4                   ; page B is page A xor 4
        ld  (draw_b), a
        ret

; Wait for the next frame interrupt.  Clobbers A.
vid_wait_frame:
        ld  a, (frame_count)
vwf_loop:
        halt
        push hl
        ld  hl, frame_count
        cp  (hl)
        pop hl
        jr  z, vwf_loop
        ret

; Fill the mapped page's two planes with the byte in A (two pixels: use
; vid_colour_byte to make one from a colour).  Clobbers BC, DE, HL.
vid_fill_page:
        ld  hl, SCR_LO
        call vfp_plane
        ld  hl, SCR_HI
vfp_plane:
        ld  (hl), a
        ld  d, h
        ld  e, l
        inc de
        ld  bc, PLANE_SIZE - 1
        ldir
        ret

; A = colour 0-15 -> A = the plane byte with both pixels that colour.
vid_colour_byte:
        push bc
        ld  c, a
        and 7
        ld  b, a
        add a, a
        add a, a
        add a, a
        or  b
        bit 3, c
        jr  z, vcb_done
        or  $C0
vcb_done:
        pop bc
        ret

; Clear both screens, all four pages, to colour 0.  Clobbers A, BC, DE, HL.
vid_clear_all:
        ld  a, PG_SCR0_A
        call vca_page
        ld  a, PG_SCR0_B
        call vca_page
        ld  a, PG_SCR1_A
        call vca_page
        ld  a, PG_SCR1_B
vca_page:
        call map_w3
        xor a
        jr  vid_fill_page
