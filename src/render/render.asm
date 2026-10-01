; render.asm - the battlefield on the screen (bank RENDER).
;
; The screen is 40 x 25 cells of 8x8 pixels.  A cell shows one of the 16
; cells of a 32x32 map icon (ground, then an overlay over it), and sprites
; are drawn over the cells.  The game draws into the screen not showing
; and flips (stub/video.asm), so each of the two screens remembers what it
; shows: which view, which map icons, which sprites - and a frame redraws
; only the cells where that differs from what should be there now.
;
; render_frame, called with the game's windows in place (units in W1,
; WORLD in W2, the map in W3):
;
;   0. wait until the screen drawn last time is showing: its flip was
;      asked for at the end of that frame and happens at a frame
;      interrupt, while the game's logic runs;
;   1. read the view's squares out of the map, comparing them with this
;      screen's copy: a square whose icons differ has all its cells dirty,
;      and every cell is dirty if the view has moved since this screen was
;      drawn;
;   2. put the sprites the logic listed on screen coordinates, sorted;
;   3. mark dirty the cells under the sprites this screen showed that are
;      gone or moved, and under the new or moved ones; then, until nothing
;      changes, every sprite with a dirty cell under it is drawn too and
;      its cells marked;
;   4. pass A (planes 0 and 2): the dirty cells, then the sprites; pass B
;      (planes 1 and 3) the same, leaving the cells clean;
;   5. the new sprite list is this screen's now; ask for the flip, aim
;      draw_a/draw_b at the screen showing now, and return without waiting
;      for the flip.  (Whatever draws on the screens next - the front end,
;      a panel - starts by waiting for frames with the palette black, so
;      the flip is long done by the time it draws.)
;
; The profiler's marks: 9 the wait for the last flip, 1 the set-up, 3 the
; squares (13 of it the copy after the view moved, rf_scroll), 2 the
; sprite list, 4 matching it with the old one, 11 restoring
; what went, 12 what else must be drawn, 5/6 pass A's cells and sprites,
; 7/8 pass B's, 10 the rest.
;
; Art (tools/dune_art.py):
;   ground icon n    page PG_ICONS + n/32, address $4000 + (n%32)*512,
;                    16 cells of 32 bytes (row-major), each cell: plane 0
;                    rows 0-7, plane 2 rows 0-7 (pass A), plane 1, plane 3
;                    (pass B)
;   overlay icon n   page PG_OVERLAYS + n/16, address $4000 + (n%16)*1024,
;                    16 cells of 64 bytes, each pass 32 bytes of (mask,
;                    data) pairs: screen = screen AND mask OR data
;   OVL_FOG          the full fog: a black cell, no ground under it

CELLS_W         EQU 40
CELLS_H         EQU 25
CELLS           EQU CELLS_W * CELLS_H
GRID_W          EQU 11          ; squares across the view grid (10 + 1)
GRID_H          EQU 8           ; squares down (200/32 = 6.25, + 1)

; ------------------------------------------------------------- the frame

render_frame:
        PROF 9
        ; the screen drawn last time is shown at a frame interrupt; until
        ; then this one is the screen showing
rf_wait:
        ld  a, (flip_req)
        or  a
        jr  nz, rf_wait
        PROF 1
        ; which screen are we drawing: 0 if draw_a is screen 0's page
        ld  a, (draw_a)
        cp  PG_SCR0_A
        ld  a, 0
        jr  z, rf_scr
        inc a
rf_scr: ld  (rf_screen), a
        xor a
        ld  (rf_scrolled), a
        call rf_select          ; the per-screen state pointers
        call rf_shake           ; the view this screen shows
        ; the view's cell offset into its first square
        ld  a, (view_x)
        rra
        rra
        rra
        and 3
        ld  (rdc_sx), a
        ld  a, (view_y)
        rra
        rra
        rra
        and 3
        ld  (rdc_sy), a
        PROF 3
        call rf_grid
        PROF 2
        ld  a, PG_SPRDIR        ; the sprite directory (the map is done with)
        call map_w3
        call rf_prep_sprites
        PROF 4
        call rf_match_sprites
        PROF 5
        ; pass A
        call vid_map_a
        xor a
        ld  (rf_pass), a
        call rf_draw_cells
        PROF 6
        call rf_draw_sprites
        PROF 7
        ; pass B
        call vid_map_b
        ld  a, 16
        ld  (rf_pass), a
        call rf_draw_cells
        PROF 8
        call rf_draw_sprites
        PROF 10
        call rf_remember
        call rf_unshake
        call map_game           ; units in W1, the map in W3 again
        ; show it at the next frame interrupt, and draw on the other screen
        ; next - the one showing now (vid_flip's rule, before the flip)
        ld  a, (port_7ffd)
        and 8                   ; showing screen 1?
        ld  a, PG_SCR0_A
        jr  z, rf_next
        ld  a, PG_SCR1_A
rf_next:
        ld  (draw_a), a
        xor 4                   ; page B is page A xor 4
        ld  (draw_b), a
        ld  a, 1
        ld  (flip_req), a
        ld  a, (rf_pal_pending)
        or  a
        ret z
        xor a
        ld  (rf_pal_pending), a
        ld  hl, battle_pal      ; waits for the interrupt, which flips
        jp  vid_palette         ; first: the colours come up with the picture

; ------------------------------------------------------------ the shake
;
; view_shake_frame (ui/ui.asm) walks the cartridge's offsets, a few pixels
; either way, a frame at a time; here the view moves in cells, and a view
; moved is a screen redrawn whole - several frames.  So the shake is two
; pictures taking turns: one screen keeps the view where it is, the other
; is drawn a cell away (8 pixels right, down or both, the way the walk
; first goes) for as long as the shake lasts.  Each screen then draws only
; what changes, as ever, and a shake costs one whole redraw of that screen
; when it begins and one when it ends, however long it lasts.  The cursor
; and the panel are in screen coordinates and stay still, as on the Mega
; Drive.
rf_shake:
        xor a
        ld  (rf_shaken), a
        ld  hl, (view_x)
        ld  (rf_home_x), hl
        ld  hl, (view_y)
        ld  (rf_home_y), hl
        ld  a, (shake_on)
        or  a
        jr  nz, rsh_1
        ld  (rf_shake_dx), a    ; the next shake takes its own way
        ld  (rf_shake_dy), a
        ret
rsh_1:  ld  a, (rf_shake_dx)
        ld  l, a
        ld  a, (rf_shake_dy)
        or  l
        jr  nz, rsh_3
        ; the way and the screen: the first one drawn with the walk off 0
        ld  a, (shake_ox)
        call rsh_way
        ld  (rf_shake_dx), a
        ld  l, a
        ld  a, (shake_oy)
        call rsh_way
        ld  (rf_shake_dy), a
        or  l
        ret z                   ; not yet
        ld  a, (rf_screen)
        ld  (rf_shake_scr), a
rsh_3:  ld  a, (rf_screen)
        ld  hl, rf_shake_scr
        cp  (hl)
        ret nz
        ld  a, 1
        ld  (rf_shaken), a
        ld  a, (rf_shake_dx)
        ld  e, a
        ld  d, 0
        ld  hl, (view_x)
        add hl, de
        ld  (view_x), hl
        ld  a, (rf_shake_dy)
        ld  e, a
        ld  hl, (view_y)
        add hl, de
        ld  (view_y), hl
        ret
; A = an offset (signed) -> 8 if it is above 0, else 0.
rsh_way:
        dec a
        cp  $7F
        ld  a, 8
        ret c
        xor a
        ret

; After the frame the view is where the game has it again.
rf_unshake:
        ld  a, (rf_shaken)
        or  a
        ret z
        ld  hl, (rf_home_x)
        ld  (view_x), hl
        ld  hl, (rf_home_y)
        ld  (view_y), hl
        ret

; render_invalidate: both screens were drawn over (the front end, a
; panel): the next frame of each redraws everything, the palette too.
render_invalidate:
        ld  hl, rf_last_view0
        ld  b, 4
rin_1:  ld  (hl), $FF
        inc hl
        djnz rin_1
        ld  hl, rf_last_view1
        ld  b, 4
rin_2:  ld  (hl), $FF
        inc hl
        djnz rin_2
        ld  a, 1                ; the palette once the first picture shows
        ld  (rf_pal_pending), a ; (set now, the screen still showing the
        ret                     ; front end's picture took its colours)

battle_pal:
        INCLUDE "palette_battle.inc"

; Point rf_msk, rf_rec, rf_lastv and rf_old at this screen's own.
rf_select:
        ld  a, (rf_screen)
        or  a
        ld  hl, rf_msk0
        ld  de, rf_rec0
        ld  bc, rf_old0
        jr  z, rfs_set
        ld  hl, rf_msk1
        ld  de, rf_rec1
        ld  bc, rf_old1
rfs_set:
        ld  (rf_msk), hl
        ld  (rf_rec), de
        ld  (rf_oldp), bc
        ld  a, (bc)
        ld  l, a
        inc bc
        ld  a, (bc)
        ld  h, a
        ld  (rf_old), hl
        ld  hl, rf_last_view0
        ld  de, rgo_f0
        ld  bc, rf_rgen0
        ld  a, (rf_screen)
        or  a
        jr  z, rfs_1
        ld  hl, rf_last_view1
        ld  de, rgo_f1
        ld  bc, rf_rgen1
rfs_1:  ld  (rf_lastv), hl
        ld  (rf_orbf), de
        ld  (rf_rgenp), bc
        ret

; -------------------------------------------------- 1. the view's squares
;
; view_x, view_y (WORLD): the view's top-left in map pixels, multiples of
; 8.  The screen's squares are the GRID_H x GRID_W from square (view_y>>5,
; view_x>>5), each the map's ground-low and high bytes; squares off the map
; read as fog.  Each screen keeps, per square (rf_rec), the two bytes it
; shows there and where their pictures are (REC_*), and the square's dirty
; cells (rf_msk: a word, bit k = cell k, row-major, 4 x 4).  A square whose
; two bytes differ from what the screen shows has all its cells dirty, and
; its record is brought up to date.

REC_GROUND      EQU 0           ; the map's two bytes
REC_HIGH        EQU 1
REC_GPAGE       EQU 2           ; the ground icon's page, 0: the full fog
REC_GHI         EQU 3           ;   and its address's high byte
REC_OPAGE       EQU 4           ; the overlay's page, 0: none
REC_OHI         EQU 5           ;   and its address's high byte
REC_SIZE        EQU 8

rf_grid:
        ; the view moved since this screen showed it: everything is dirty,
        ; and every record is made again
        ld  hl, (rf_lastv)
        ld  de, view_x
        ld  b, 4
rgv_cmp:
        ld  a, (de)
        cp  (hl)
        jr  nz, rgv_moved
        inc de
        inc hl
        djnz rgv_cmp
rgv_same:
        xor a
        ld  (rg_force), a
        ld  hl, rg_plain
        ld  a, (dbg_flags)
        rra                     ; bit 0 (LOOKAROUND): overlays from $34 up
        jr  nc, rg_go           ; are left off - the other loop
        ld  hl, rg_reveal
        jr  rg_go
rgv_moved:
        ; the screen showing is near the new view: its picture, moved, is
        ; this one's, and only what that leaves out is drawn
        call rf_scroll
        jr  c, rgv_whole
        ld  de, (rf_lastv)
        ld  hl, view_x
        ld  bc, 4
        ldir
        jr  rgv_same
rgv_whole:
        ld  de, (rf_lastv)
        ld  hl, view_x
        ld  bc, 4
        ldir
        ld  hl, (rf_msk)
        ld  (hl), $FF
        ld  d, h
        ld  e, l
        inc de
        ld  bc, GRID_W * GRID_H * 2 - 1
        ldir
        ld  a, 1
        ld  (rg_force), a
        ld  hl, rg_all
rg_go:  ld  (rg_call + 1), hl
        ld  hl, (view_y)
        call px_to_square
        ld  c, a                ; C = map row
        ld  hl, (view_x)
        call px_to_square
        ld  (rg_col), a
        ; squares of a row on the map: min(GRID_W, 64 - column)
        ld  b, a
        ld  a, 64
        sub b
        jr  nc, rg_2
        xor a
rg_2:   cp  GRID_W
        jr  c, rg_3
        ld  a, GRID_W
rg_3:   ld  (rg_on), a
        ld  hl, (rf_rec)
        ld  b, GRID_H
rg_row: push bc
        ld  a, c
        cp  64
        jp  nc, rg_offrow
        ; DE = MAP_GROUND + row * 64 + column
        and 3
        rrca
        rrca
        ld  e, a
        ld  a, (rg_col)
        or  e
        ld  e, a
        ld  a, c
        rra
        rra
        and $0F
        add a, MAP_GROUND >> 8
        ld  d, a
        ld  a, (rg_on)
        or  a
        jr  z, rg_rest
        ld  b, a
rg_call:
        call rg_plain
rg_rest:
        ld  a, (rg_on)
        sub GRID_W
        jr  z, rg_next
        neg
        ld  b, a
        call rg_fog
rg_next:
        pop bc
        inc c
        djnz rg_row
        PROF 17
        ; fall into rg_orbs

; The house markers' orb turns: the next of eight frames every eighth
; video frame, the same for all (the frame hook's $00608E and $006D10 send
; $00690C's frames to the marker tiles).  Every record showing a marker
; (overlay ORB_FIRST..) is pointed at the frame of now, stored as overlay
; ORB_SLOT + marker * 8 + frame (dune_art.py); one that was showing
; another has the orb's cells - 8, 9, 12, 13, the bottom-left quarter -
; dirty.  A record made afresh points at the static picture, so it takes
; the frame here too.
rg_orbs:
        ld  a, (frame_count)
        rrca
        rrca
        rrca
        and 7
        ld  c, a
        ld  a, (rg_force)       ; nothing to do unless the frame moved on
        or  a                   ; or a record was made afresh (it points at
        jr  nz, rgo_do          ; the static picture until this runs)
        ld  a, (rg_touched)
        or  a
        jr  nz, rgo_do
        ld  hl, (rf_orbf)       ; this screen's records show that frame
        ld  a, (hl)             ; (each screen has its own: the other was
        cp  c                   ; left a pass behind for good once)
        ret z
rgo_do: xor a
        ld  (rg_touched), a
        ld  hl, (rf_orbf)
        ld  (hl), c
        ld  a, c
        ld  (rgo_f), a
        ld  hl, (rf_rec)
        ld  de, (rf_msk)
        ld  b, GRID_W * GRID_H
rgo_loop:
        inc l                   ; -> REC_HIGH (records are 8-aligned)
        ld  a, (hl)
        srl a
        sub ORB_FIRST
        cp  ORB_MARKERS
        jr  nc, rgo_next
        add a, a
        add a, a
        add a, a
        ld  c, a
        ld  a, (rgo_f)
        add a, c
        add a, ORB_SLOT
        ld  c, a                ; C = the frame's overlay slot
        rrca
        rrca
        rrca
        rrca
        and 7
        add a, PG_OVERLAYS
        inc l
        inc l
        inc l                   ; -> REC_OPAGE
        cp  (hl)
        ld  (hl), a
        ld  a, c
        ld  c, 0
        jr  z, rgo_1
        inc c                   ; C: it changed
rgo_1:  and 15
        add a, a
        add a, a
        add a, $40
        inc l                   ; -> REC_OHI
        cp  (hl)
        ld  (hl), a
        jr  nz, rgo_mark
        dec c
        jr  nz, rgo_next
rgo_mark:
        inc de                  ; cells 8, 9, 12, 13: the high byte's
        ld  a, (de)             ; bits 0, 1, 4, 5
        or  $33
        ld  (de), a
        dec de
rgo_next:
        ld  a, l
        and $F8
        add a, REC_SIZE
        ld  l, a
        jr  nc, rgo_2
        inc h
rgo_2:  inc de
        inc de
        djnz rgo_loop
        ret

rg_offrow:
        ld  b, GRID_W
        call rg_fog
        jp  rg_next

; B squares from DE (in MAP_GROUND; MAP_HIGH is $1000 on) against the
; records from HL.  (The records are 8-aligned: L steps inside one.)
rg_plain:
        ld  a, (de)             ; the ground's low byte
        cp  (hl)
        jr  nz, rgp_d1
        set 4, d
        inc l
        ld  a, (de)             ; the high byte
        cp  (hl)
        jr  nz, rgp_d2
        res 4, d
rgp_n1: ld  a, l
        add a, REC_SIZE - 1
        ld  l, a
        jr  nc, rgp_n2
        inc h
rgp_n2: inc e
        djnz rg_plain
        ret
rgp_d1: ld  (hl), a
        set 4, d
        inc l
        ld  a, (de)
rgp_d2: ld  (hl), a
        res 4, d
        call rg_new
        jr  rgp_n1

rg_reveal:
        ld  a, (de)
        cp  (hl)
        jr  nz, rgr_d1
        set 4, d
        inc l
        ld  a, (de)
        cp  $34 << 1            ; overlays from $34 up are left off
        jr  c, rgr_1
        and 1
rgr_1:  cp  (hl)
        jr  nz, rgr_d2
        res 4, d
rgr_n1: ld  a, l
        add a, REC_SIZE - 1
        ld  l, a
        jr  nc, rgr_n2
        inc h
rgr_n2: inc e
        djnz rg_reveal
        ret
rgr_d1: ld  (hl), a
        set 4, d
        inc l
        ld  a, (de)
        cp  $34 << 1
        jr  c, rgr_d2
        and 1
rgr_d2: ld  (hl), a
        res 4, d
        call rg_new
        jr  rgr_n1

; The view moved: every record made again.
rg_all:
        ld  a, (de)
        ld  (hl), a
        set 4, d
        inc l
        ld  a, (de)
        res 4, d
        push af
        ld  a, (dbg_flags)
        rra
        jr  nc, rga_1
        pop af
        cp  $34 << 1
        jr  c, rga_2
        and 1
        jr  rga_2
rga_1:  pop af
rga_2:  ld  (hl), a
        call rg_new
        ld  a, l
        add a, REC_SIZE - 1
        ld  l, a
        jr  nc, rga_3
        inc h
rga_3:  inc e
        djnz rg_all
        ret

; B squares off the map: the fog.
rg_fog:
        ld  a, (rg_force)
        or  a
        jr  nz, rgf_d1          ; (all made again)
        ld  a, (hl)
        or  a
        jr  nz, rgf_d1
        inc l
        ld  a, (hl)
        cp  OVL_FOG << 1
        jr  nz, rgf_d2
rgf_n1: ld  a, l
        add a, REC_SIZE - 1
        ld  l, a
        jr  nc, rgf_n2
        inc h
rgf_n2: djnz rg_fog
        ret
rgf_d1: ld  (hl), 0
        inc l
rgf_d2: ld  (hl), OVL_FOG << 1
        call rg_new
        jr  rgf_n1

; HL -> a record's high byte, just brought up to date: where its pictures
; are, and all its cells dirty.  Keeps BC, DE, HL.
rg_new:
        push bc
        push de
        push hl
        ld  a, 1
        ld  (rg_touched), a     ; (rg_orbs looks at it)
        ld  b, (hl)             ; the high byte
        dec l
        ld  c, (hl)             ; the ground's low byte
        inc l
        inc l                   ; -> REC_GPAGE
        ld  a, b
        and $FE
        cp  OVL_FOG << 1
        jr  nz, rgn_icons
        ld  (hl), 0             ; the full fog: black
        jr  rgn_mask
rgn_icons:
        ; the ground icon (B bit 0, C): page PG_ICONS + icon / 32, at
        ; $4000 + (icon % 32) * 512
        ld  a, b
        and 1
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  a, c
        rlca
        rlca
        rlca
        and 7
        or  e
        add a, PG_ICONS
        ld  (hl), a
        inc l
        ld  a, c
        and 31
        add a, a
        add a, $40
        ld  (hl), a
        inc l
        ; the overlay (B >> 1): none, or page PG_OVERLAYS + n / 16, at
        ; $4000 + (n % 16) * 1024
        ld  a, b
        srl a
        ld  (hl), a
        jr  z, rgn_mask
        ld  c, a
        rrca
        rrca
        rrca
        rrca
        and 7
        add a, PG_OVERLAYS
        ld  (hl), a
        inc l
        ld  a, c
        and 15
        add a, a
        add a, a
        add a, $40
        ld  (hl), a
rgn_mask:
        ; its mask: rf_msk + (record - rf_rec) / 4
        pop hl
        push hl
        dec l                   ; -> the record
        ld  de, (rf_rec)
        or  a
        sbc hl, de
        srl h
        rr  l
        srl h
        rr  l
        ld  de, (rf_msk)
        add hl, de
        ld  (hl), $FF
        inc hl
        ld  (hl), $FF
        pop hl
        pop de
        pop bc
        ret

; HL = a pixel coordinate (0..2047) -> A = HL >> 5.
px_to_square:
        ld  a, l
        rla
        rl  h
        rla
        rl  h
        rla
        rl  h                   ; H = HL >> 5 (the low bits fall away)
        ld  a, h
        ret

; ------------------------------------------------------------ scrolling
;
; The view moved since this screen was drawn.  The other screen - the one
; showing, drawn last pass - is mostly a cell or two from the new view, so
; its picture is copied over this one, moved by the difference: a plane is
; 40 bytes a line, so a move of whole cells is one block copy a plane.
; This screen then takes over what the other knows about what it shows:
; its squares' records, moved by whole squares, and its sprite list, moved
; by the pixels.  Its masks start clean but for the cells the copy leaves
; out - the edge the view moved towards, where the rows' ends wrap round -
; and the frame goes on as if the view had not moved: the squares that
; changed since and the squares new to the grid are drawn, the sprites
; matched against the moved list (one drawn in screen coordinates, the
; HUD, has moved as far as the copy is concerned, and is drawn again).
; The copy is about 0.55M T-states, against 2M for drawing every cell.
;
; -> NC done; C: the other screen is too far from the new view, or was
; drawn over, and everything is drawn.

; A byte copied costs about 17 T-states and a byte drawn about 37 a pass,
; so the copy pays whenever the pictures overlap at all; these keep a
; sliver of overlap from costing the fixed part for nothing.
RSC_MAX_DX      EQU 32          ; cells either way across
RSC_MAX_DY      EQU 20          ;   and down

rf_scroll:
        ; the other screen's view
        ld  a, (rf_screen)
        or  a
        ld  hl, rf_last_view1
        jr  z, rsc_1
        ld  hl, rf_last_view0
rsc_1:  ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = its view_x
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; HL = its view_y
        ld  a, d
        inc a
        scf
        ret z                   ; $FFFF: drawn over since
        ld  (rsc_ox), de
        ld  (rsc_oy), hl
        ; the move in cells, near enough
        ex  de, hl
        ld  hl, (view_y)
        or  a
        sbc hl, de
        ld  (rsc_dyp), hl
        ld  b, RSC_MAX_DY
        call rsc_cells
        ret c
        ld  (rsc_dyc), a
        ld  hl, (view_x)
        ld  de, (rsc_ox)
        or  a
        sbc hl, de
        ld  (rsc_dxp), hl
        ld  b, RSC_MAX_DX
        call rsc_cells
        ret c
        ld  (rsc_dxc), a
        PROF 13
        ld  a, 1
        ld  (rf_scrolled), a
        call rsc_copy
        call rsc_records
        call rsc_masks
        call rsc_list
        PROF 3
        or  a
        ret

; HL = a move in pixels (a multiple of 8), B = a limit in cells: A = the
; move in cells, C if it is beyond the limit either way.
rsc_cells:
        sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        ld  a, h
        or  a
        jr  z, rscc_pos
        inc a
        scf
        ret nz                  ; far
        ld  a, l
        neg                     ; the cells, the other way
        ld  c, a
        ld  a, b
        cp  c                   ; C: beyond
        ld  a, l
        ret
rscc_pos:
        ld  a, b
        cp  l
        ld  a, l
        ret

; The copy: the source's offset from the destination is dy * 320 + dx
; bytes in every plane; what would come from outside the plane is left
; out (the rows at the top or the bottom), and what comes round from the
; next row or the last (a column at one side) is on the edge made dirty.
rsc_copy:
        ld  a, (rsc_dyc)
        ld  l, a
        rla
        sbc a, a
        ld  h, a                ; HL = dy
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; * 64
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl              ; * 256
        add hl, de              ; * 320
        ld  a, (rsc_dxc)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        add hl, de              ; HL = the offset
        bit 7, h
        jr  nz, rscp_neg
        ex  de, hl
        ld  hl, $4000
        add hl, de
        ld  (rsc_src), hl       ; the source further on
        ld  hl, $C000
        ld  (rsc_dst), hl
        ld  hl, 8000
        or  a
        sbc hl, de
        jr  rscp_len
rscp_neg:
        ex  de, hl
        ld  hl, $4000
        ld  (rsc_src), hl
        ld  hl, $C000
        or  a
        sbc hl, de
        ld  (rsc_dst), hl       ; the destination further on
        ld  hl, 8000
        add hl, de
rscp_len:
        ld  (rsc_len), hl
        ; the screen showing in window 1, this one in window 3: page A's
        ; planes 0 and 2, then page B's 1 and 3
        ld  a, (draw_a)
        xor PG_SCR0_A ^ PG_SCR1_A
        call map_w1
        call vid_map_a
        call rscp_planes
        ld  a, (draw_b)
        xor PG_SCR0_B ^ PG_SCR1_B
        call map_w1
        call vid_map_b
        call rscp_planes
        jp  map_game
rscp_planes:
        ld  hl, (rsc_src)
        ld  de, (rsc_dst)
        ld  bc, (rsc_len)
        call rf_blit
        ld  hl, (rsc_src)
        ld  a, h
        add a, $20
        ld  h, a
        ld  de, (rsc_dst)
        ld  a, d
        add a, $20
        ld  d, a
        ld  bc, (rsc_len)
        ; fall through

; BC bytes (not 0) from HL to DE, sixteen LDIs a turn: the first turn goes
; in part way, so that BC reaches 0 at a turn's end.
rf_blit:
        ld  a, c
        neg
        and 15                  ; the LDIs the first turn skips
        add a, a
        push hl
        add a, rfb_16 & $FF
        ld  l, a
        ld  a, rfb_16 >> 8
        adc a, 0
        ld  h, a
        ld  (rfb_go + 1), hl
        pop hl
rfb_go: jp  rfb_16
rfb_16:
        REPT 16
        ldi
        ENDR
        jp  pe, rfb_16
        ret

; The records: this screen's for grid square (i, j) is the other's for
; (i + dqx, j + dqy) where it has one, else none ($FF: made again by
; rf_grid, all its cells dirty).
rsc_records:
        ld  hl, (view_x)
        call px_to_square
        ld  b, a
        ld  hl, (rsc_ox)
        call px_to_square
        ld  c, a
        ld  a, b
        sub c
        ld  (rsc_dqx), a
        ld  hl, (view_y)
        call px_to_square
        ld  b, a
        ld  hl, (rsc_oy)
        call px_to_square
        ld  c, a
        ld  a, b
        sub c
        ld  (rsc_dqy), a
        ; K = the other's records - this one's + (dqy * GRID_W + dqx) * 8
        ld  a, (rsc_dqy)
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        add hl, hl
        add hl, de              ; * 11
        ld  a, (rsc_dqx)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        add hl, de
        add hl, hl
        add hl, hl
        add hl, hl              ; * REC_SIZE
        ex  de, hl
        ld  a, (rf_screen)
        or  a
        ld  hl, rf_rec1 - rf_rec0
        jr  z, rscr_1
        ld  hl, rf_rec0 - rf_rec1
rscr_1: add hl, de
        ld  (rsc_k), hl
        ld  hl, (rf_rec)
        ld  c, 0                ; C = j
rscr_row:
        ld  b, 0                ; B = i
rscr_col:
        ld  a, (rsc_dqy)
        add a, c
        cp  GRID_H
        jr  nc, rscr_none
        ld  a, (rsc_dqx)
        add a, b
        cp  GRID_W
        jr  nc, rscr_none
        push bc
        ld  d, h
        ld  e, l
        ld  bc, (rsc_k)
        add hl, bc
        ld  bc, REC_SIZE
        ldir
        ex  de, hl
        pop bc
        jr  rscr_next
rscr_none:
        ld  a, $FF
        REPT REC_SIZE
        ld  (hl), a
        inc hl
        ENDR
rscr_next:
        inc b
        ld  a, b
        cp  GRID_W
        jr  nz, rscr_col
        inc c
        ld  a, c
        cp  GRID_H
        jr  nz, rscr_row
        ret

; The masks: clean, but for the cells the copy left out.
rsc_masks:
        ld  hl, (rf_msk)
        ld  b, GRID_W * GRID_H * 2
        xor a
rscm_1: ld  (hl), a
        inc hl
        djnz rscm_1
        ; the columns: the last dx on the right, or the first -dx
        ld  a, (rsc_dxc)
        or  a
        jr  z, rscm_rows
        jp  m, rscm_left
        ld  c, a
        ld  a, CELLS_W
        sub c
        jr  rscm_cols
rscm_left:
        neg
        ld  c, a
        xor a
rscm_cols:                      ; A = the first column, C = columns
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  de, 0
        ld  b, CELLS_H * 8
        call rscm_rect
rscm_rows:
        ; the rows: the last dy at the bottom, or the first -dy
        ld  a, (rsc_dyc)
        or  a
        ret z
        jp  m, rscm_top
        ld  c, a
        ld  a, CELLS_H
        sub c
        jr  rscm_rws
rscm_top:
        neg
        ld  c, a
        xor a
rscm_rws:                       ; A = the first row, C = rows
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ex  de, hl              ; DE = y
        ld  a, c
        add a, a
        add a, a
        add a, a
        ld  b, a                ; B = the height
        ld  hl, 0
        ld  c, CELLS_W
        ; fall through
; HL = x, DE = y, C = the width in cells, B = the height in pixels: those
; cells dirty.
rscm_rect:
        ld  ix, rsc_rect
        ld  (ix + E_X), l
        ld  (ix + E_X + 1), h
        ld  (ix + E_Y), e
        ld  (ix + E_Y + 1), d
        ld  (ix + E_W), c
        ld  (ix + E_H), b
        ld  hl, rsc_rect
        call rf_rect_calc
        ld  ix, rsc_rect
        jp  rf_rect_set

; The sprite list: this screen's is the other's, each entry moved by the
; view's move the other way and its cells worked out again.  A key's y is
; moved and clamped as rf_prep_sprites clamps it; that is monotonic, so
; the records stay sorted (an entry that was clamped may not match its
; sprite now, and is drawn again).
rsc_list:
        ld  a, (rf_screen)
        or  a
        ld  hl, (rf_old1)
        jr  z, rscl_1
        ld  hl, (rf_old0)
rscl_1: ld  (rsc_olist), hl
        ld  de, (rf_old)
        ld  a, (hl)
        ld  (de), a
        or  a
        ret z
        ld  (rsc_n), a
        ; the records, n * 4 bytes, and the entries, n * E_SIZE
        push hl
        push de
        inc hl
        inc de
        ld  c, a
        ld  b, 0
        sla c
        rl  b
        sla c
        rl  b
        ldir
        pop de
        pop hl
        push de
        ld  bc, L_ENTRIES
        add hl, bc
        ex  de, hl
        add hl, bc
        ex  de, hl
        push hl
        ld  a, (rsc_n)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        ld  b, h
        ld  c, l
        add hl, hl
        add hl, hl
        add hl, bc              ; * E_SIZE
        ld  b, h
        ld  c, l
        pop hl
        ldir
        pop hl                  ; -> this screen's list
        ; the records: the key's y, and the entry in this list
        ld  de, (rsc_olist)
        push hl
        or  a
        sbc hl, de
        ld  (rsc_pdiff), hl
        pop hl
        inc hl
        ld  a, (rsc_n)
        ld  b, a
rscl_rec:
        push bc
        ld  e, (hl)
        ld  d, 0
        push hl
        ex  de, hl
        ld  de, (rsc_dyp)
        or  a
        sbc hl, de
        ld  a, h
        or  a
        ld  a, l
        jr  z, rscl_k
        ld  a, 0
        jp  m, rscl_k
        ld  a, 255
rscl_k: pop hl
        ld  (hl), a
        inc hl
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        push hl
        ld  hl, (rsc_pdiff)
        add hl, de
        ex  de, hl
        pop hl
        ld  (hl), d
        dec hl
        ld  (hl), e
        inc hl
        inc hl
        pop bc
        djnz rscl_rec
        ; the entries: x and y, and their cells
        ld  hl, (rf_old)
        ld  de, L_ENTRIES
        add hl, de
        ld  a, (rsc_n)
        ld  b, a
rscl_ent:
        push bc
        push hl
        ld  bc, (rsc_dxp)
        call rscl_sub
        ld  bc, (rsc_dyp)
        call rscl_sub
        pop hl
        push hl
        call rf_rect_calc
        pop hl
        ld  de, E_SIZE
        add hl, de
        pop bc
        djnz rscl_ent
        ret
; (HL) -= BC, a word; HL += 2.
rscl_sub:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        or  a
        sbc hl, bc
        ex  de, hl
        ld  (hl), d
        dec hl
        ld  (hl), e
        inc hl
        inc hl
        ret

; ------------------------------------------------------ the dirty cells
;
; Every sprite entry carries the cells it covers, worked out once when it
; is made (rf_rect_calc), as the squares they lie in:
;   E_SQ (w)   the first square's mask, as an offset into rf_msk ($FFxx:
;              the sprite is wholly off the grid)
;   E_NC, E_NR the squares across and down
;   E_CB0, E_CB1  the columns in the first and the last square across: a
;              nibble, twice (one square across: E_CB0 has both ends)
;   E_RS0, E_RS1  the rows in the first and the last square down, as a
;              mask word (one square down: E_RS0 has both ends)
; Grid cells are screen cells + the view's offset into its first square
; (rdc_sx, rdc_sy).  A frame shifted by 2, 4 or 6 pixels covers a column
; more.

; HL = an entry with its x, y, W and h: its cells.
rf_rect_calc:
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = x
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = y
        inc hl
        inc hl
        inc hl
        inc hl                  ; -> E_W
        ld  a, c
        and 6
        ld  a, (hl)             ; W, and a column more when shifted
        jr  z, rrc_1
        inc a
rrc_1:  ld  (rrc_w), a
        inc hl
        ld  a, (hl)             ; h
        inc hl
        inc hl
        ld  (rrc_out), hl       ; -> E_SQ
        ; the last row: ((y + h - 1) >> 3) + sy
        dec a
        ld  l, a
        ld  h, 0
        add hl, de
        ld  a, l
        sra h
        rra
        sra h
        rra
        sra h
        rra
        ld  hl, rdc_sy
        add a, (hl)
        ld  l, a                ; L = r1
        ; the first: (y >> 3) + sy
        ld  a, e
        sra d
        rra
        sra d
        rra
        sra d
        rra
        ld  h, a
        ld  a, (rdc_sy)
        add a, h
        ld  h, a                ; H = r0
        ; the columns: from (x >> 3) + sx, W' of them
        ld  a, c
        sra b
        rra
        sra b
        rra
        sra b
        rra                     ; (signed, -128..127 is plenty)
        ld  e, a
        ld  a, (rdc_sx)
        add a, e
        ld  e, a                ; E = c0
        ld  a, (rrc_w)
        dec a
        add a, e
        ld  d, a                ; D = c1
        ; clipped to the grid
        bit 7, l
        jr  nz, rrc_none        ; wholly above
        bit 7, d
        jr  nz, rrc_none        ; wholly left
        bit 7, h
        jr  z, rrc_2
        ld  h, 0
rrc_2:  bit 7, e
        jr  z, rrc_3
        ld  e, 0
rrc_3:  ld  a, l
        cp  GRID_H * 4
        jr  c, rrc_4
        ld  l, GRID_H * 4 - 1
rrc_4:  ld  a, d
        cp  GRID_W * 4
        jr  c, rrc_5
        ld  d, GRID_W * 4 - 1
rrc_5:  ld  a, l
        cp  h
        jr  c, rrc_none
        ld  a, d
        cp  e
        jr  nc, rrc_on
rrc_none:
        ld  hl, (rrc_out)
        inc hl
        ld  (hl), $FF           ; E_SQ: off the grid
        ret
rrc_on:
        ; H = r0, L = r1, E = c0, D = c1: the rows and columns inside the
        ; first and last squares
        ld  a, h
        and 3
        add a, a
        add a, a
        ld  (rrc_ra), a         ; ra0 * 4
        ld  a, l
        and 3
        ld  (rrc_rb), a         ; rb1
        ld  a, e
        and 3
        add a, a
        add a, a
        ld  (rrc_ca), a         ; ca0 * 4
        ld  a, d
        and 3
        ld  (rrc_cb), a         ; cb1
        ; the squares
        ld  a, h
        and $FC
        ld  b, a                ; B = qr0 * 4
        ld  a, l
        and $FC
        sub b
        rrca
        rrca
        ld  l, a                ; L = NR - 1
        ld  a, e
        and $FC
        ld  c, a                ; C = qc0 * 4
        ld  a, d
        and $FC
        sub c
        rrca
        rrca
        ld  h, a                ; H = NC - 1
        ex  de, hl              ; D = NC - 1, E = NR - 1
        ; E_SQ: qr0 * 22 + qc0 * 2
        ld  a, b
        add a, a
        add a, a
        add a, b                ; qr0 * 20
        srl b
        add a, b                ; qr0 * 22
        srl c
        add a, c
        ld  hl, (rrc_out)
        ld  (hl), a
        inc hl
        ld  (hl), 0
        inc hl
        ld  a, d
        inc a
        ld  (hl), a             ; E_NC
        inc hl
        ld  a, e
        inc a
        ld  (hl), a             ; E_NR
        inc hl
        ; E_CB0, E_CB1: one square across, ca0..cb1; else ca0..3 and 0..cb1
        ld  a, d
        or  a
        ld  a, (rrc_ca)
        jr  nz, rrc_cw
        ld  c, a
        ld  a, (rrc_cb)
        or  c
        call rrc_nib
        inc hl
        jr  rrc_rows
rrc_cw: or  3
        call rrc_nib
        ld  a, (rrc_cb)
        call rrc_nib
rrc_rows:
        ; E_RS0, E_RS1 the same way down
        ld  a, e
        or  a
        ld  a, (rrc_ra)
        jr  nz, rrc_rw
        ld  c, a
        ld  a, (rrc_rb)
        or  c
        jr  rrc_rsel
rrc_rw: or  3
        call rrc_rsel
        ld  a, (rrc_rb)
        ; fall through

; A = a * 4 + b (a <= b): the mask word of rows a..b to (HL), HL += 2.
rrc_rsel:
        add a, a
        or  rr_rsel & $FF
        ld  c, a
        ld  b, rr_rsel >> 8
        ld  a, (bc)
        ld  (hl), a
        inc hl
        inc c
        ld  a, (bc)
        ld  (hl), a
        inc hl
        ret
; A = a * 4 + b (a <= b): the byte with columns a..b in both nibbles to
; (HL), HL += 1.
rrc_nib:
        or  rr_nibs & $FF
        ld  c, a
        ld  b, rr_nibs >> 8
        ld  a, (bc)
        ld  (hl), a
        inc hl
        ret

; columns a..b (index a * 4 + b), as a nibble in both halves
        ALIGN 16
rr_nibs:
        DB  $11, $33, $77, $FF
        DB  0,   $22, $66, $EE
        DB  0,   0,   $44, $CC
        DB  0,   0,   0,   $88
; rows a..b (index a * 4 + b): the mask's low byte (rows 0, 1), high (2, 3)
        ALIGN 32
rr_rsel:
        DW  $000F, $00FF, $0FFF, $FFFF
        DW  0,     $00F0, $0FF0, $FFF0
        DW  0,     0,     $0F00, $FF00
        DW  0,     0,     0,     $F000

; IX = an entry.  rf_rect_set: mark its cells.  rf_rect_clear: make them
; clean.  rf_rect_test: NZ if any of them is dirty.
rf_rect_set:
        ld  hl, rrs_set
        jr  rr_go
rf_rect_clear:
        ld  hl, rrs_clear
        jr  rr_go
rf_rect_test:
        ld  a, (ix + E_SQ + 1)
        or  a
        jr  z, rrt_on
        xor a                   ; off the grid
        ret
rrt_on:
        ; anything dirty in its squares at all?  (Mostly not.)
        ld  l, (ix + E_SQ)
        ld  h, 0
        ld  de, (rf_msk)
        add hl, de
        ld  b, (ix + E_NR)
        ld  de, GRID_W * 2
rrt_row:
        push hl
        ld  c, (ix + E_NC)
        xor a
rrt_col:
        or  (hl)
        inc hl
        or  (hl)
        inc hl
        dec c
        jr  nz, rrt_col
        pop hl
        or  a
        jr  nz, rrt_look
        add hl, de
        djnz rrt_row
        ret                     ; Z: nothing
rrt_look:
        ld  hl, rrs_test        ; then cell by cell
rr_go:  ld  (rr_call + 1), hl
        ld  a, (ix + E_SQ + 1)
        or  a
        jr  nz, rr_none         ; off the grid
        ; the column bytes: E_CB0, $FF ..., E_CB1
        ld  hl, rr_cols
        ld  a, (ix + E_CB0)
        ld  (hl), a
        ld  a, (ix + E_NC)
        dec a
        jr  z, rr_c2
        inc hl
        dec a
        jr  z, rr_c1
        ld  b, a
        ld  a, $FF
rr_cm:  ld  (hl), a
        inc hl
        djnz rr_cm
rr_c1:  ld  a, (ix + E_CB1)
        ld  (hl), a
rr_c2:  ; the first square's mask
        ld  l, (ix + E_SQ)
        ld  h, 0
        ld  de, (rf_msk)
        add hl, de
        ; each row of squares: E_RS0, $FFFF ..., E_RS1
        ld  b, (ix + E_NR)
        ld  e, (ix + E_RS0)
        ld  d, (ix + E_RS0 + 1)
rr_row: push bc
        push hl
        ld  a, e
        ld  (rrs_lo + 1), a
        ld  (rrc_lo + 1), a
        ld  (rrt_lo + 1), a
        ld  a, d
        ld  (rrs_hi + 1), a
        ld  (rrc_hi + 1), a
        ld  (rrt_hi + 1), a
        ld  de, rr_cols
        ld  b, (ix + E_NC)
rr_call:
        call rrs_set
        pop hl
        pop bc
        ret nz                  ; the test found a dirty cell
        ld  de, GRID_W * 2
        add hl, de
        ld  a, b
        cp  2
        ld  de, $FFFF           ; a row in the middle: all four
        jr  nz, rr_r1
        ld  e, (ix + E_RS1)     ; the last
        ld  d, (ix + E_RS1 + 1)
rr_r1:  djnz rr_row
        xor a                   ; (Z: in the test, nothing was dirty)
        ret
rr_none:
        xor a
        ret

; B squares' masks from HL, their column bytes at DE.
rrs_set:
        ld  a, (de)
rrs_lo: and 0
        or  (hl)
        ld  (hl), a
        inc hl
        ld  a, (de)
rrs_hi: and 0
        or  (hl)
        ld  (hl), a
        inc hl
        inc de
        djnz rrs_set
        xor a
        ret
rrs_clear:
        ld  a, (de)
rrc_lo: and 0
        cpl
        and (hl)
        ld  (hl), a
        inc hl
        ld  a, (de)
rrc_hi: and 0
        cpl
        and (hl)
        ld  (hl), a
        inc hl
        inc de
        djnz rrs_clear
        xor a
        ret
rrs_test:
        ld  a, (de)
rrt_lo: and 0
        and (hl)
        ret nz
        inc hl
        ld  a, (de)
rrt_hi: and 0
        and (hl)
        ret nz
        inc hl
        inc de
        djnz rrs_test
        xor a
        ret

; ---------------------------------------------- 3. which sprites are drawn
;
; A sprite this screen already shows - same place, same frame - is left
; alone unless something under it changes; every other sprite of the old
; list has its cells restored, and every new or moved one is drawn.  Then,
; until nothing changes, a sprite with a dirty cell under it has all its
; cells marked and is drawn too, so that whatever overlaps it is redrawn
; in the right order.
rf_match_sprites:
        xor a
        ld  (rf_radar_drawn), a
        ld  (rmf_redraw), a
        ld  (rmf_hud), a
        ld  a, (rg_force)
        or  a
        jr  z, rms_old
        ; the view moved: every cell is dirty and every sprite is drawn
        ld  hl, (rf_new)
        ld  a, (hl)
        or  a
        ret z
        ld  b, a
        ld  de, L_ENTRIES
        add hl, de
rms_all:
        push bc
        push hl
        call rf_rect_calc       ; (for when this list is the old one)
        pop ix
        push ix
        ld  (ix + E_FLAG), 1
        ld  a, (ix + E_PAGE)
        cp  PG_RADAR
        jr  nz, rms_all1
        ld  a, (ix + E_W)
        cp  8
        jr  nz, rms_all1
        ld  (rf_radar_drawn), a
rms_all1:
        pop hl
        ld  de, E_SIZE
        add hl, de
        pop bc
        djnz rms_all
        jp  rf_radar_cover
rms_old:
        ; the old list: nothing matched yet
        ld  hl, (rf_old)
        ld  a, (hl)
        ld  (rmf_orem), a
        or  a
        jr  z, rms_new
        ld  b, a
        ld  de, L_ENTRIES + E_FLAG
        add hl, de
        ld  de, E_SIZE
rms_clr:
        ld  (hl), 0
        add hl, de
        djnz rms_clr
rms_new:
        ld  hl, (rf_old)
        inc hl
        ld  (rmf_optr), hl
        ; each new sprite, in order: look for itself in the old list
        ld  hl, (rf_new)
        ld  a, (hl)
        or  a
        jr  z, rms_unmatched
        ld  b, a
        inc hl
rms_nloop:
        push bc
        call rms_find           ; HL -> the record, past it on return
        pop bc
        djnz rms_nloop
rms_unmatched:
        PROF 11
        ; the old sprites nothing matched: restore their cells
        ld  hl, (rf_old)
        ld  a, (hl)
        or  a
        jr  z, rms_spread
        ld  b, a
        ld  de, L_ENTRIES
        add hl, de
rms_oloop:
        push bc
        push hl
        push hl
        pop ix
        ld  a, (ix + E_FLAG)
        or  a
        call z, rf_rect_set
        pop hl
        ld  de, E_SIZE
        add hl, de
        pop bc
        djnz rms_oloop
rms_spread:
        PROF 12
        ; a sprite left alone with a dirty cell under it is drawn after all
        xor a
        ld  (rms_changed), a
        ld  hl, (rf_new)
        ld  a, (hl)
        or  a
        ret z
        ld  b, a
        ld  de, L_ENTRIES
        add hl, de
rms_sloop:
        push bc
        push hl
        push hl
        pop ix
        ld  a, (ix + E_FLAG)
        or  a
        jr  nz, rms_snext
        call rf_rect_test
        jr  z, rms_snext
        ld  (ix + E_FLAG), 1
        call rms_mark_new
        ld  a, 1
        ld  (rms_changed), a
rms_snext:
        pop hl
        ld  de, E_SIZE
        add hl, de
        pop bc
        djnz rms_sloop
        ld  a, (rms_changed)
        or  a
        jr  nz, rms_spread
        ; fall through

; The radar's picture is opaque and sits on whole cells (240, 120; 8 x 64):
; when it is drawn, the cells under it need not be - they were marked so
; that what overlaps it is drawn again (rms_spread), and now that is known
; their painting can go.  A marker moving on the radar would otherwise
; repaint 64 cells of map nobody sees.
rf_radar_cover:
        ld  a, (rf_radar_drawn)
        or  a
        ret z
        ld  ix, rf_radar_rect
        ld  hl, 240
        ld  (ix + E_X), l
        ld  (ix + E_X + 1), h
        ld  hl, 120
        ld  (ix + E_Y), l
        ld  (ix + E_Y + 1), h
        ld  (ix + E_W), 8
        ld  (ix + E_H), 64
        ld  hl, (rdc_sx)        ; (rdc_sy after it)
        ld  de, (rf_radar_sxy)
        or  a
        sbc hl, de
        jp  z, rf_rect_clear    ; the same offset: the same cells
        ld  hl, (rdc_sx)
        ld  (rf_radar_sxy), hl
        ld  hl, rf_radar_rect
        call rf_rect_calc
        jp  rf_rect_clear

; IX = a new entry to be drawn: mark its cells.  The radar's picture is
; noted: it hides everything under it (rf_radar_cover).
rms_mark_new:
        ld  a, (ix + E_PAGE)
        cp  PG_RADAR
        jp  nz, rf_rect_set
        ld  a, (ix + E_W)
        cp  8
        jp  nz, rf_rect_set
        ld  (rf_radar_drawn), a
        jp  rf_rect_set

; HL = a new record (key, entry): an unmatched old entry with the same
; key, place and frame gets marked matched and this one is not drawn;
; otherwise it is drawn and its cells marked.  Both lists are sorted by
; key, so the old one is walked alongside: past the keys below this one,
; then through the run of equal keys.  -> HL past the record.
rms_find:
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = the key
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = the entry
        inc hl
        push hl
        ld  (rmf_new), bc
        ld  a, (rmf_hud)        ; the radar's picture is drawn again this
        or  a                   ; pass: what sits over it (the marker, the
        jr  z, rmf_go           ; cursor, the warning) is drawn again too,
        ld  a, d                ; or the copy would wipe it - whole, no
        cp  RPS_HUD_LAYER + 1   ; cell marked (rmf_done), if it is where
        jr  c, rmf_go           ; it was
        ld  a, 1
        ld  (rmf_redraw), a
rmf_go: ld  hl, (rmf_optr)
        ld  a, (rmf_orem)
        or  a
        jr  z, rmf_none
        ld  b, a
rmf_skip:
        inc hl
        ld  a, (hl)             ; the old key's high byte
        dec hl
        cp  d
        jr  c, rmf_past         ; old < new: behind us for good
        jr  nz, rmf_none        ; the old list is past it
        ld  a, (hl)
        cp  e
        jr  c, rmf_past
        jr  nz, rmf_none
        jr  rmf_run
rmf_past:
        inc hl
        inc hl
        inc hl
        inc hl
        ld  (rmf_optr), hl
        ld  a, b
        dec a
        ld  (rmf_orem), a
        djnz rmf_skip
        jr  rmf_none
rmf_run:
        ; the run of equal keys from HL (B records left)
        push hl
        inc hl
        inc hl
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; HL = the old entry
        push de
        push bc
        call rmf_same
        pop bc
        pop de
        pop hl
        jr  z, rmf_done         ; matched: not drawn
        inc hl
        inc hl
        inc hl
        inc hl
        dec b
        jr  z, rmf_none
        ld  a, (hl)
        cp  e
        jr  nz, rmf_none
        inc hl
        ld  a, (hl)
        dec hl
        cp  d
        jr  z, rmf_run
rmf_none:
        xor a
        ld  (rmf_redraw), a
        ld  hl, (rmf_new)
        call rf_rect_calc
        ld  ix, (rmf_new)
        ld  (ix + E_FLAG), 1
        call rms_mark_new
        pop hl
        ret
rmf_done:
        ld  ix, (rmf_new)
        ld  a, (rmf_redraw)     ; matched: not drawn - unless it is the
        ld  (ix + E_FLAG), a    ; radar's picture with new rows, which is
        xor a                   ; drawn whole over its old self, no cell
        ld  (rmf_redraw), a     ; marked (a marked cell would have every
        pop hl                  ; sprite near it drawn again)
        ret

; HL = an old entry: Z (and it is marked matched) if it is unmatched and
; has the same x, y, page and address as the new one (rmf_new).
rmf_same:
        push hl
        ld  de, E_FLAG
        add hl, de
        ld  a, (hl)
        pop hl
        or  a
        ret nz
        ; the radar's picture (page PG_RADAR, 8 wide) is drawn in place a
        ; row a frame: it is the same only while no cell row of it was
        ; completed since this screen copied it (radar_gen)
        push hl
        ld  hl, (rmf_new)
        ld  de, E_PAGE
        add hl, de
        ld  a, (hl)
        cp  PG_RADAR
        jr  nz, rmfs_1
        ld  de, E_W - E_PAGE
        add hl, de
        ld  a, (hl)
        cp  8
        jr  nz, rmfs_1
        ld  hl, (rf_rgenp)
        ld  a, (radar_gen)
        cp  (hl)
        ld  (hl), a
        jr  z, rmfs_1
        ld  a, 1
        ld  (rmf_redraw), a     ; matched below, and drawn (rmf_done)
        ld  (rmf_hud), a
rmfs_1: pop hl
        ld  de, (rmf_new)
        REPT 6
        ld  a, (de)
        cp  (hl)
        ret nz
        inc hl
        inc de
        ENDR
        ld  a, (de)
        cp  (hl)
        ret nz
        ld  de, E_FLAG - 6
        add hl, de
        ld  (hl), 1
        ; the cells it covers are the old one's (the view has not moved)
        inc hl                  ; -> E_SQ
        ld  de, (rmf_new)
        ex  de, hl
        ld  bc, E_SQ
        add hl, bc
        ex  de, hl
        ld  bc, E_SIZE - E_SQ
        ldir
        xor a
        ret

; ---------------------------------------------------- 4. drawing the cells
;
; Square by square: a square with dirty cells has each dirty cell that is
; on the screen copied - the ground's, then the overlay's over them.  Pass
; B leaves the square clean.

rf_draw_cells:
        ld  hl, (rf_msk)
        ld  c, 0                ; C = the square's row
rdc_row:
        ld  b, GRID_W           ; B = GRID_W - its column
rdc_col:
        ld  a, (hl)
        inc hl
        or  (hl)
        inc hl
        jr  nz, rdc_dirty
rdc_next:
        djnz rdc_col
        inc c
        ld  a, c
        cp  GRID_H
        jr  nz, rdc_row
        ret
rdc_dirty:
        push bc
        push hl
        dec hl
        dec hl
        call rf_square
        pop hl
        pop bc
        ld  a, (rf_pass)
        or  a
        jr  z, rdc_next
        dec hl                  ; pass B: the square is clean now
        ld  (hl), 0
        dec hl
        ld  (hl), 0
        inc hl
        inc hl
        jr  rdc_next

; HL -> a square's mask, B = GRID_W - its column, C = its row: its dirty
; cells on the screen.
rf_square:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        dec hl
        ld  (rsq_mask), de
        ; its record: rf_rec + (the mask - rf_msk) * 4
        ld  de, (rf_msk)
        or  a
        sbc hl, de
        add hl, hl
        add hl, hl
        ld  de, (rf_rec)
        add hl, de
        inc l
        inc l                   ; -> REC_GPAGE
        push hl
        ; its first cell's screen column and row: 4 * column - sx, 4 * row
        ; - sy (may be off the screen), and its screen address
        ld  a, GRID_W
        sub b
        add a, a
        add a, a
        ld  e, a
        ld  a, (rdc_sx)
        neg
        add a, e
        ld  (rsq_x0), a
        ld  e, a
        ld  a, c
        add a, a
        add a, a
        ld  d, a
        ld  a, (rdc_sy)
        neg
        add a, d
        ld  (rsq_y0), a
        add a, 3                ; 0..31
        add a, a
        add a, rc_rows & $FF
        ld  l, a
        ld  a, rc_rows >> 8
        adc a, 0
        ld  h, a
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  a, e
        rla
        sbc a, a
        ld  d, a
        add hl, de
        ld  (rsq_dst), hl
        ; each row's dirty cells, only those on the screen
        ld  de, (rsq_mask)
        ld  a, (rsq_x0)
        cp  CELLS_W - 3
        jr  nc, rsq_edge
        ld  a, (rsq_y0)
        cp  CELLS_H - 3
        jr  nc, rsq_edge
        ; all of the square on the screen
        ld  a, d
        and e
        inc a
        jp  z, rsq_whole        ; and all of it dirty: the fast way
        ld  a, e
        and $0F
        ld  (rse_nib), a
        ld  a, e
        rrca
        rrca
        rrca
        rrca
        and $0F
        ld  (rse_nib + 1), a
        ld  a, d
        and $0F
        ld  (rse_nib + 2), a
        ld  a, d
        rrca
        rrca
        rrca
        rrca
        and $0F
        ld  (rse_nib + 3), a
        jr  rsq_pics
rsq_edge:
        ld  a, (rsq_x0)
        add a, 3                ; 0..43
        add a, rc_colvalid & $FF
        ld  l, a
        ld  a, rc_colvalid >> 8
        adc a, 0
        ld  h, a
        ld  b, (hl)             ; B = the square's columns on the screen
        ld  a, (rsq_y0)
        add a, 3                ; 0..31
        add a, rc_rowvalid & $FF
        ld  l, a
        ld  a, rc_rowvalid >> 8
        adc a, 0
        ld  h, a
        ld  c, (hl)             ; C = its rows on the screen
        ld  a, e
        and b
        rr  c
        jr  c, rsq_n0
        xor a
rsq_n0: ld  (rse_nib), a
        ld  a, e
        rrca
        rrca
        rrca
        rrca
        and b
        rr  c
        jr  c, rsq_n1
        xor a
rsq_n1: ld  (rse_nib + 1), a
        ld  a, d
        and b
        rr  c
        jr  c, rsq_n2
        xor a
rsq_n2: ld  (rse_nib + 2), a
        ld  a, d
        rrca
        rrca
        rrca
        rrca
        and b
        rr  c
        jr  c, rsq_n3
        xor a
rsq_n3: ld  (rse_nib + 3), a
rsq_pics:
        pop hl
        ; the pictures
        ld  a, (hl)             ; REC_GPAGE
        or  a
        jr  z, rsq_fog
        inc l
        ld  d, (hl)             ; REC_GHI
        inc l
        ld  c, (hl)             ; REC_OPAGE
        inc l
        ld  b, (hl)             ; REC_OHI
        push bc
        call rc_map_art
        ld  a, (rf_pass)
        ld  e, a                ; DE = cell 0's bytes for this pass
        ld  hl, rse_ground
        call rsq_each
        pop bc
        ld  a, c
        or  a
        ret z                   ; no overlay
        call rc_map_art
        ld  d, b
        ld  a, (rf_pass)
        add a, a
        ld  e, a
        ld  hl, rse_overlay
        jp  rsq_each
rsq_fog:
        ld  hl, rse_fog
        jp  rsq_each            ; (the source is not read)

; A whole square on the screen: its 16 cells row by row, the ground's then
; the overlay's, or black.  (The record's pointer is on the stack.)
rsq_whole:
        pop hl                  ; -> REC_GPAGE
        ld  a, (hl)
        or  a
        jr  z, rsw_black
        inc l
        ld  d, (hl)             ; REC_GHI
        inc l
        ld  c, (hl)             ; REC_OPAGE
        inc l
        ld  b, (hl)             ; REC_OHI
        push bc
        call rc_map_art
        ld  a, (rf_pass)
        ld  e, a                ; DE = cell 0's bytes for this pass
        ld  hl, (rsq_dst)
        ld  c, 4
rsw_row:
        push hl
        ld  b, 4
rsw_col:
        push bc
        push hl
        call rc_copy
        pop hl
        pop bc
        inc hl
        ld  a, e
        add a, 32 - 15          ; the next cell's bytes
        ld  e, a
        jr  nc, rsw_1
        inc d
rsw_1:  djnz rsw_col
        pop hl
        ld  a, l
        add a, 320 & $FF
        ld  l, a
        ld  a, h
        adc a, 320 >> 8
        ld  h, a
        dec c
        jr  nz, rsw_row
        pop bc
        ld  a, c
        or  a
        ret z                   ; no overlay
        call rc_map_art
        ld  d, b
        ld  a, (rf_pass)
        add a, a
        ld  e, a
        ld  hl, (rsq_dst)
        ld  c, 4
rsw_orow:
        push hl
        ld  b, 4
rsw_ocol:
        push bc
        push hl
        call rc_masked
        pop hl
        pop bc
        inc hl
        ld  a, e
        add a, 64 - 31
        ld  e, a
        jr  nc, rsw_2
        inc d
rsw_2:  djnz rsw_ocol
        pop hl
        ld  a, l
        add a, 320 & $FF
        ld  l, a
        ld  a, h
        adc a, 320 >> 8
        ld  h, a
        dec c
        jr  nz, rsw_orow
        ret
rsw_black:
        ld  hl, (rsq_dst)
        ld  c, 4
rsw_brow:
        push hl
        ld  b, 4
rsw_bcol:
        push bc
        push hl
        call rc_black
        pop hl
        pop bc
        inc hl
        djnz rsw_bcol
        pop hl
        ld  a, l
        add a, 320 & $FF
        ld  l, a
        ld  a, h
        adc a, 320 >> 8
        ld  h, a
        dec c
        jr  nz, rsw_brow
        ret

; The square's dirty cells on the screen (rse_nib), each drawn by the
; routine at the start of the block HL points at: [the routine (w), the
; source's step a cell (a byte) when passed over, when drawn (what the
; routine did not step itself), a row (w)].  DE = cell 0's source.  The
; row's screen address and source are kept in the other register set
; (nothing else uses it: the interrupt saves only what it touches).
rsq_each:
        ld  a, (hl)
        ld  (rse_call + 1), a
        ld  (rse_callf + 1), a
        inc hl
        ld  a, (hl)
        ld  (rse_call + 2), a
        ld  (rse_callf + 2), a
        inc hl
        ld  a, (hl)
        ld  (rse_skip + 1), a
        inc hl
        ld  a, (hl)
        ld  (rse_after + 1), a
        ld  (rse_afterf + 1), a
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)             ; BC = a row's step in the source
        ld  hl, (rsq_dst)
        exx                     ; HL', DE', BC': the row's screen, source, step
        ld  hl, rse_nib
        ld  b, 4
rse_row:
        ld  a, (hl)
        or  a
        jr  z, rse_next         ; nothing to draw in this row
        push hl
        push bc
        ld  c, a
        exx
        push hl
        push de
        exx
        pop de
        pop hl
        cp  $0F
        jr  z, rse_four
rse_cell:
        srl c
        jr  nc, rse_pass
        push bc
        push hl
rse_call:
        call rc_copy
        pop hl
        pop bc
        ld  a, e
rse_after:
        add a, 0
        ld  e, a
        inc hl
        ld  a, c
        or  a
        jr  nz, rse_cell
        jr  rse_rdone
rse_pass:
        ld  a, e
rse_skip:
        add a, 0
        ld  e, a
        inc hl
        jr  rse_cell            ; (a bit is still to come)
rse_four:
        ; the whole row
        ld  c, 4
rse_f1: push bc
        push hl
rse_callf:
        call rc_copy
        pop hl
        pop bc
        ld  a, e
rse_afterf:
        add a, 0
        ld  e, a
        inc hl
        dec c
        jr  nz, rse_f1
rse_rdone:
        pop bc
        pop hl
rse_next:
        exx                     ; the next row: 320 on, and the source's step
        ld  a, l
        add a, 320 & $FF
        ld  l, a
        ld  a, h
        adc a, 320 >> 8
        ld  h, a
        ex  de, hl
        add hl, bc
        ex  de, hl
        exx
        inc hl
        djnz rse_row
        ret

rse_ground:
        DW  rc_copy
        DB  32, 32 - 15
        DW  128
rse_overlay:
        DW  rc_masked
        DB  64, 64 - 31
        DW  256
rse_fog:
        DW  rc_black
        DB  0, 0
        DW  0

; SCR_LO + row * 320, rows -3 to 28 (from -3: the rows off the top are not
; drawn, only counted from)
rc_rows:
rcr_n = -3
        DUP 32
        DW  SCR_LO + rcr_n * 320
rcr_n = rcr_n + 1
        EDUP

; y0 + 3 (y0 from -3 to 28) -> the rows y0 .. y0 + 3 on the screen
rc_rowvalid:
rrv_n = -3
        DUP 32
        DB  (((rrv_n >= 0) && (rrv_n < 25)) & 1) | (((rrv_n >= -1) && (rrv_n < 24)) & 2) | (((rrv_n >= -2) && (rrv_n < 23)) & 4) | (((rrv_n >= -3) && (rrv_n < 22)) & 8)
rrv_n = rrv_n + 1
        EDUP

; x0 + 3 (x0 from -3 to 40) -> the columns x0 .. x0 + 3 on the screen
rc_colvalid:
rcv_n = -3
        DUP 44
        DB  (((rcv_n >= 0) && (rcv_n < 40)) & 1) | (((rcv_n >= -1) && (rcv_n < 39)) & 2) | (((rcv_n >= -2) && (rcv_n < 38)) & 4) | (((rcv_n >= -3) && (rcv_n < 37)) & 8)
rcv_n = rcv_n + 1
        EDUP

; A black cell (both planes of this pass): HL = the screen address.
rc_black:
        ld  bc, 40
        xor a
        REPT 8
        ld  (hl), a
        add hl, bc
        ENDR
        ld  bc, $2000 - 8 * 40
        add hl, bc
        ld  bc, 40
        REPT 7
        ld  (hl), a
        add hl, bc
        ENDR
        ld  (hl), a
        ret

; 16 bytes from DE (16-aligned: E is only stepped) to the cell at HL, the
; low plane's eight rows then the high plane's.  -> DE + 15.
rc_copy:
        ld  bc, 40
        REPT 8
        ld  a, (de)
        ld  (hl), a
        inc e
        add hl, bc
        ENDR
        ld  bc, $2000 - 8 * 40
        add hl, bc
        ld  bc, 40
        REPT 7
        ld  a, (de)
        ld  (hl), a
        inc e
        add hl, bc
        ENDR
        ld  a, (de)
        ld  (hl), a
        ret

; 16 (mask, data) pairs from DE (32-aligned) over the cell at HL.
; -> DE + 31.
rc_masked:
        ld  bc, 40
        REPT 8
        ld  a, (de)
        and (hl)
        inc e
        ex  de, hl
        or  (hl)
        inc l
        ex  de, hl
        ld  (hl), a
        add hl, bc
        ENDR
        ld  bc, $2000 - 8 * 40
        add hl, bc
        ld  bc, 40
        REPT 7
        ld  a, (de)
        and (hl)
        inc e
        ex  de, hl
        or  (hl)
        inc l
        ex  de, hl
        ld  (hl), a
        add hl, bc
        ENDR
        ld  a, (de)
        and (hl)
        inc e
        ex  de, hl
        or  (hl)
        ex  de, hl
        ld  (hl), a
        ret

; A = an art page for window 1, mapped only if it is not there already.
rc_map_art:
        push hl
        ld  hl, cur_w1
        cp  (hl)
        pop hl
        ret z
        jp  map_w1

;  -------------------------------------------------------- 2. the sprites
;
; rf_prep_sprites (with the units in window 1 and the map in window 3)
; turns every unit the player can see into entries of the new list, then
; COMBAT's explosions, the markers and the HUD.  A list is kept in two
; parts: the entries, in the order they were made -
;   +0 x (w) +2 y (w)  the frame's top-left on the screen (may be off it)
;   +4 page +5 address (w)  the frame (tools/dune_art.py: +0 W, +1 h, then
;                           planes 0-3 of h rows of W (mask, data) pairs)
;   +7 W  +8 h  +9 a flag: in the new list, draw it this frame; in a
;                           screen's old list, a new entry matched it
; - and, sorted, a record per entry: its key (w: layer << 8 | y) and
; where it is, so that a higher layer, and lower on the screen within a
; layer, is drawn later (sprites.txt "draw order"); equal keys keep the
; order they were made in.
;
; Drawing: a frame is stored once; x & 6 shifts it by 2, 4 or 6 pixels by
; feeding screen plane d from source plane (d - p) & 3, one column further
; right when d < p (p = (x & 6) / 2).

E_X             EQU 0
E_Y             EQU 2
E_PAGE          EQU 4
E_ADDR          EQU 5
E_W             EQU 7
E_H             EQU 8
E_FLAG          EQU 9
E_SQ            EQU 10              ; the cells it covers (rf_rect_calc)
E_NC            EQU 12
E_NR            EQU 13
E_CB0           EQU 14
E_CB1           EQU 15
E_RS0           EQU 16
E_RS1           EQU 18
E_SIZE          EQU 20
L_COUNT         EQU 0
L_RECS          EQU 1               ; RF_MAX_SPR records: key (w), entry (w)
L_ENTRIES       EQU L_RECS + RF_MAX_SPR * 4
L_SIZE          EQU L_ENTRIES + RF_MAX_SPR * E_SIZE

; the draw layer of each unit type (sprites.txt)
spr_unit_layer:
        DB  $10, $10, $04, $04, $04, $04, $0B, $08, $08, $08, $08, $08
        DB  $08, $08, $08, $08, $08, $08, $0C, $0C, $0C, $0C, $0C, $0B
        DB  $14, $02, $0F

rf_prep_sprites:
        ; the positions (1/8 pixel) of the objects that may be on the screen:
        ; view - 64 <= position / 8 < view + 384 across, + 264 down
        ld  hl, (view_x)
        ld  bc, 384
        call rps_bounds
        ld  (rps_xlo), hl
        ld  (rps_xw), de
        call rps_hbytes
        ld  (rps_xhb), hl
        ld  hl, (view_y)
        ld  bc, 264
        call rps_bounds
        ld  (rps_ylo), hl
        ld  (rps_yw), de
        call rps_hbytes
        ld  (rps_yhb), hl
        ld  hl, (rf_new)
        push hl
        inc hl
        ld  (rps_rec), hl       ; the next record
        ld  de, L_ENTRIES - L_RECS
        add hl, de
        ld  (rps_out), hl       ; the next entry
        xor a
        ld  (rps_n), a
        ld  a, RF_MAX_SPR       ; the units, markers and effects stop
        ld  hl, rps_hud_n       ; short of the list's end by what the HUD
        sub (hl)                ; took last pass: the cursor, the credits
        ld  (rps_limit), a      ; and the radar go in last and must fit
        ld  a, (unit_find_count)
        or  a
        jr  z, rps_end
        ld  b, a
        ld  hl, unit_find
rps_loop:
        push bc
        push hl
        ld  a, (hl)
        call unit_ptr
        push hl
        pop ix
        call rps_unit
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        call z, rps_harvest
        pop hl
        inc hl
        pop bc
        djnz rps_loop
rps_end:
        PROF 14
        call rps_markers
        PROF 15
        call rps_fx
        PROF 16
        ld  a, RF_MAX_SPR
        ld  (rps_limit), a
        ld  a, (rps_n)
        ld  (rps_hud_n), a      ; before the HUD, for the moment
        call rps_hud
        ld  hl, rps_hud_n
        ld  a, (rps_n)
        sub (hl)
        add a, 2                ; the HUD's count, and two spare
        ld  (hl), a
        pop hl
        ld  a, (rps_n)
        ld  (hl), a             ; the list's count
        ret

; IX = a unit: a Harvester at work gets its dust (sprites.txt "harvester
; dust": MOVE's mv_harvest_shown bit, frame 282 + its +$73, placed by its
; facing).
rps_harvest:
        bit OF_NOTONMAP, (ix + O_FLAGS)
        ret nz
        ld  a, (ix + O_INDEX)
        ld  e, a
        srl e
        srl e
        srl e
        ld  d, 0
        ld  hl, mv_harvest_shown
        add hl, de
        and 7
        ld  b, a
        ld  a, (hl)
        inc b
rph_bit:
        dec b
        jr  z, rph_b0
        rrca
        jr  rph_bit
rph_b0: rrca
        ret nc
        ; the unit's own screen position again
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        ex  de, hl
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        call shr3_hl
        ld  bc, (view_y)
        or  a
        sbc hl, bc
        push hl
        ; + the facing's offset
        ld  a, (ix + U_OR0_CURRENT)
        add a, 16
        rlca
        rlca
        rlca
        and 7
        add a, a
        ld  c, a
        ld  b, 0
        ld  hl, rph_dust_xy
        add hl, bc
        ld  a, (hl)
        inc hl
        push hl
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        add hl, de
        ld  (rpu_x), hl
        pop hl
        ld  a, (hl)
        pop de
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        add hl, de
        ld  (rpu_y), hl
        ld  a, $09
        ld  (rpu_layer), a
        ld  a, (ix + $73)
        cp  3
        jr  c, rph_f
        xor a
rph_f:  add a, 282 & $FF
        ld  e, a
        ld  d, 282 >> 8
        jp  rps_frame

rph_dust_xy:
        DB  -8, 8, -20, 4, -24, -8, -20, -20, -8, -24, 4, -20, 8, -8, 4, 4

; The structure markers (STRUCT's st_markers, struct/world.inc): the
; picture a structure's marker sprite shows - the low-power bolt, 'OK' or
; the repair hammer, frames 329, 327, 328 - at its position plus the offset
; its layout gives (sprites.txt "structure markers"), under everything
; (layer $00).  Only the player's structures have one, so no fog.  Every
; marker flashes as the cartridge's sprite engine flashes it: a marker
; sprite is made with a blink period (struct_marker_set_bit0/1/2 $009AD6,
; $009A62, $009B26: 3, 6, 7) and no phase bit, and spr_render ($0010D8)
; then skips it for one frame in period + 1 - the bolt every fourth
; frame, 'OK' every seventh, the hammer every eighth.  Here by the frame
; counter: the bolt on frames & 3 = 3, the other two on frames & 7 = 7.
rps_markers:
        xor a
        ld  (rpu_line), a
        ld  (rpu_layer), a
        ld  hl, st_markers
        ld  b, STRUCT_COUNT
rpm_loop:
        ld  a, (hl)
        and $30
        call nz, rpm_one
        inc hl
        djnz rpm_loop
        ret
rpm_one:
        push bc
        push hl
        rrca
        rrca
        rrca
        rrca
        dec a
        ld  (rpm_kind), a       ; the flag: 0 bolt, 1 'OK', 2 hammer
        ; the flash: off one frame in four (the bolt) or eight
        ld  c, 3
        or  a
        jr  z, rpm_flash
        ld  c, 7
rpm_flash:
        ld  a, (frame_count)
        and c
        cp  c
        jp  z, rpm_skip
        ld  a, STRUCT_COUNT
        sub b                   ; the structure's index
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        jr  z, rpm_skip
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  nz, rpm_skip
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        and 7
        add a, a
        ld  e, a
        ld  a, (rpm_kind)
        add a, a
        add a, a
        add a, a
        add a, a
        add a, e
        ld  e, a
        ld  d, 0
        ld  hl, rpm_offsets
        add hl, de              ; -> dx, dy
        push hl
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        pop de
        ld  a, (de)
        inc de
        ld  c, a
        ld  b, 0
        add hl, bc
        ld  (rpu_x), hl
        ld  bc, 64              ; only near the screen: -64 <= x < 448
        add hl, bc
        ld  a, h
        cp  2
        jr  nc, rpm_skip
        ld  a, (de)
        push af
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        call shr3_hl
        ld  de, (view_y)
        or  a
        sbc hl, de
        pop af
        ld  c, a
        ld  b, 0
        add hl, bc
        ld  (rpu_y), hl
        ld  bc, 64
        add hl, bc
        ld  a, h
        cp  2
        jr  nc, rpm_skip
        ld  a, (rpm_kind)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, rpm_frames
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        call rps_frame
rpm_skip:
        pop hl
        pop bc
        ret

; By flag (0 the bolt, 1 'OK', 2 the hammer): the frame, and by layout
; 0-7 the offset from the position (sprites.txt: the bolt $0658E0 - one
; for all, 'OK' $009AB6, the hammer $0659F6).
rpm_frames:
        DW  329, 327, 328
rpm_offsets:
        DB  20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20
        DB  20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 36, 36, 36, 36
        DB  4, 4, 4, 4, 4, 4, 20, 20, 36, 20, 36, 20, 36, 36, 36, 36
rpm_kind:
        DB  0

; COMBAT's explosions (fx_list, combat/world.inc): every entry in use with
; a frame; smoke takes the frame of the global smoke phase (0-2).
RPS_FX_LAYER    EQU $13

rps_fx:
        ld  a, RPS_FX_LAYER
        ld  (rpu_layer), a
        ld  ix, fx_list
        ld  b, FX_COUNT
rfx_loop:
        push bc
        ld  a, (ix + FX_STEP)
        or  a
        jr  z, rfx_next
        ld  e, (ix + FX_FRAME)
        ld  d, (ix + FX_FRAME + 1)
        ld  a, d
        and e
        inc a
        jr  z, rfx_next         ; a blank step
        bit 7, d
        jr  z, rfx_frame
        res 7, d
        ld  a, (frame_count)    ; the smoke phase
        rrca
        rrca
        rrca
        and $1F
rfx_mod3:
        sub 3
        jr  nc, rfx_mod3
        add a, 3
        add a, e
        ld  e, a
        jr  nc, rfx_frame
        inc d
rfx_frame:
        push de
        ld  l, (ix + FX_X)
        ld  h, (ix + FX_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        ld  (rpu_x), hl
        ld  l, (ix + FX_Y)
        ld  h, (ix + FX_Y + 1)
        call shr3_hl
        ld  de, (view_y)
        or  a
        sbc hl, de
        ld  (rpu_y), hl
        ld  a, (ix + FX_HOUSE)
        cp  6
        jr  c, rfx_h
        xor a
rfx_h:  ld  e, a
        ld  d, 0
        ld  hl, spr_line_of_house
        add hl, de
        ld  a, (hl)
        ld  (rpu_line), a
        pop de
        ; only near the screen
        ld  hl, (rpu_x)         ; -64 <= x < 448
        ld  bc, 64
        add hl, bc
        ld  a, h
        cp  2
        jr  nc, rfx_next
        ld  hl, (rpu_y)         ; -64 <= y < 448
        add hl, bc
        ld  a, h
        cp  2
        jr  nc, rfx_next
        push ix
        call rps_frame
        pop ix
rfx_next:
        ld  de, FX_SIZE
        add ix, de
        pop bc
        dec b
        jp  nz, rfx_loop
        ret

; The battle's markers, over everything: the bracket round the selected
; unit or structure and the cursor.  Above the panel and the radar come
; the radar's marker, then the cursor, then the low-credits warning (the
; Mega Drive's layers $FC, $FD and $FF).
;
; The two cursor sprites are what ui_battle_button sets with no button
; ($028596-$0287C6, cursor_set_frames $004B34) - by the selection, not by
; what is under the cursor:
; - one of the player's units selected, not a Saboteur: the crosshair
;   (anim 5, frame 331) and the white bracket round it (anim 6, 332);
; - another house's unit, or the player's Saboteur: the square (anim 0,
;   330) and the red bracket (anim 29, 333);
; - a structure: the square and the corners round it ($0C7EFE) - the
;   crosshair for the player's Palace with its weapon armed (flags2 bit
;   7, $FFDC4C, flags2 bit 8 clear, $0286B0-$0286D8);
; - nothing: the square.
; The bracket blinks (spr_create with period 10 and bit 3, cursor_create
; $004AFA; spr_render $0010B8): eleven frames hidden, eleven shown.
RPS_BRACKET_LAYER EQU $1F         ; the bracket and corners: under the radar
RPS_HUD_LAYER   EQU $20
RPS_MARK_LAYER  EQU $21
RPS_CURSOR_LAYER EQU $22
RPS_WARN_LAYER  EQU $23
RPH_BLINK       EQU 11

rps_hud:
        xor a
        ld  (rpu_line), a
        ld  a, RPS_BRACKET_LAYER
        ld  (rpu_layer), a
        call rph_blink
        call rph_pick           ; leaves IX on the selected unit
        ld  hl, (rph_bracket)
        ld  a, h
        or  l
        jr  z, rph_cursor
        ld  a, (rph_hidden)
        or  a
        jr  nz, rph_cursor
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  nz, rph_cursor
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        ld  (rpu_x), hl
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        call shr3_hl
        ld  de, (view_y)
        or  a
        sbc hl, de
        ld  (rpu_y), hl
        ld  de, (rph_bracket)
        call rps_frame
rph_cursor:
        call rph_struct_box
        ld  a, RPS_HUD_LAYER
        ld  (rpu_layer), a
        call rph_radar
        call rph_credits
        call rph_panel
        call rph_warning
        ld  a, RPS_CURSOR_LAYER
        ld  (rpu_layer), a
        ld  a, (place_active)
        or  a
        jp  nz, rph_place
        ld  hl, (cursor_x)
        ld  (rpu_x), hl
        ld  hl, (cursor_y)
        ld  (rpu_y), hl
        ld  de, (rph_pointer)
        jp  rps_frame
rph_pointer: DW 330

; The bracket's blink, once a pass: rph_hidden nonzero in its eleven
; frames off.  The Mega Drive's sprite starts its count hidden (+4 = 0,
; bit 4 clear: the first frame reloads the count and hides it) and counts
; only the frames it is shown in - a hidden sprite is skipped before its
; blink is stepped ($0010BA) - so the phase stands still while nothing
; is selected.  Counted frames 1-11 hidden, 12-22 shown: rph_phase is
; the count less one, mod 22, hidden below 11.
rph_blink:
        ld  hl, (frame_count)
        ld  de, (rph_seen)
        ld  (rph_seen), hl
        ld  a, (unit_selected)
        ld  b, a
        ld  a, (struct_selected)
        and b
        inc a
        ret z                   ; nothing selected: no bracket to count
        or  a
        sbc hl, de
        ld  a, h                ; a long wait (a panel) counts as 200
        or  a
        jr  nz, rbl_0
        ld  a, l
        cp  200
        jr  c, rbl_1
rbl_0:  ld  a, 200
rbl_1:  ld  hl, rph_phase
        add a, (hl)
rbl_2:  sub 2 * RPH_BLINK
        jr  nc, rbl_2
        add a, 2 * RPH_BLINK
        ld  (hl), a
        cp  RPH_BLINK
        ld  a, 0
        jr  nc, rbl_3
        inc a
rbl_3:  ld  (rph_hidden), a
        ret
rph_seen:   DW 0
rph_phase:  DB 2 * RPH_BLINK - 1   ; the frames counted less one
rph_hidden: DB 1

; The two cursor sprites' frames for the selection ($028596-$0287C6):
; rph_pointer the pointer's, rph_bracket the unit bracket's (0: no unit
; selected; a structure's corners are rph_struct_box's).
rph_pick:
        ld  hl, 330             ; the square
        ld  (rph_pointer), hl
        ld  hl, 0
        ld  (rph_bracket), hl
        ld  a, (unit_selected)
        cp  $FF
        jr  z, rpk_struct
        call unit_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  hl, 333             ; another house's, or a Saboteur
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, rpk_ubr
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  z, rpk_ubr
        ld  de, 331             ; the crosshair: where to send it
        ld  (rph_pointer), de
        dec hl                  ; 332, the player's
rpk_ubr:
        ld  (rph_bracket), hl
        ret
rpk_struct:
        ; the player's Palace with its weapon armed: the crosshair
        ld  a, (struct_selected)
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        ret nz
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        ld  a, (special_armed)
        or  a
        ret z
        bit 7, (ix + O_FLAGS2)
        ret z
        bit 0, (ix + O_FLAGS2 + 1)
        ret nz
        ld  hl, 331
        ld  (rph_pointer), hl
        ret
rph_bracket: DW 0

; Placing a building: the cursor is its footprint (cursor_set_frames
; $004B34 with a placement cursor), its squares from the cursor's point -
; which the grid cursor keeps on the map's squares - frame 338 where it
; fits at the square under the cursor, 339 where not.
rph_place:
        ld  hl, (place_sq)
        ld  a, h
        cp  $10
        ret nc                  ; not looked at yet
        ld  hl, (cursor_x)
        ld  (rph_px), hl
        ld  hl, (cursor_y)
        ld  (rph_py), hl
        ld  a, (place_h)
        ld  c, a
        ld  hl, (rph_py)
rpp_row:
        ld  (rpu_y), hl
        ld  a, (place_w)
        ld  b, a
        ld  hl, (rph_px)
rpp_col:
        ld  (rpu_x), hl
        push bc
        ld  de, 338
        ld  a, (place_fits)
        or  a
        jr  nz, rpp_f
        inc de
rpp_f:  call rps_frame
        pop bc
        ld  hl, (rpu_x)
        ld  de, 32
        add hl, de
        djnz rpp_col
        ld  hl, (rpu_y)
        ld  de, 32
        add hl, de
        dec c
        jr  nz, rpp_row
        ret
rph_px: DW  0
rph_py: DW  0

; A picture that is not in the directory: A = its page, HL = its address,
; IY -> dx, dy, W, h.
rps_raw:
        ld  c, a
        ex  de, hl
        ld  hl, rps_limit
        ld  a, (rps_n)
        cp  (hl)
        ret nc
        jp  rpf_have

; The radar at (240, 120): the switching animation's frame, or the
; picture UI draws, or nothing with the options' radar off.
HUD_STATIC      EQU 412

rph_radar:
        ld  a, (radar_option)
        or  a
        ret z
        ld  hl, 240
        ld  (rpu_x), hl
        ld  hl, 120
        ld  (rpu_y), hl
        ld  a, (radar_static)
        cp  $FF
        jr  z, rpr_pic
        ld  e, a
        ld  d, 0
        ld  hl, HUD_STATIC
        add hl, de
        ex  de, hl
        call rps_frame
        jr  rph_mark
rpr_pic:
        ld  hl, (radar_front)
        ld  a, h
        or  l
        jr  z, rph_mark
        ld  iy, rpr_info
        ld  a, PG_RADAR
        call rps_raw
        ; fall through

; The radar's marker (radar_place_marker $005518, shown with the radar by
; radar_show_marker $0054E4): the square under the cursor, counted from
; the map's first square ($FFBF54) - ((pixel - first) & $7F0) >> 4 on a
; 32 x 32 map, two radar pixels a square, and >> 5 on a 64 x 64 one, whose
; first square is 1,1 and so has the marker a pixel up and left of the
; square's own, as the cartridge draws it.  The picture's corner is 3 up
; and left of that point (ui/ui.asm rd_mark_pens); the view is the game's,
; not the shaken one.
rph_mark:
        ld  a, RPS_MARK_LAYER
        ld  (rpu_layer), a
        ld  a, (radar_small)
        or  a
        ld  de, -32
        jr  z, rpm_1
        ld  de, -512
rpm_1:  ld  hl, (cursor_x)
        ld  bc, (rf_home_x)
        add hl, bc
        add hl, de
        call rpm_px
        ld  l, a
        ld  h, 0
        ld  bc, 240 - 3
        add hl, bc
        ld  bc, RADAR_MARK
        bit 0, l
        jr  z, rpm_2
        dec l                   ; odd: the picture drawn a pixel right
        ld  bc, RADAR_MARK + RADAR_MARK_SIZE
rpm_2:  ld  (rpu_x), hl
        push bc
        ld  hl, (cursor_y)
        ld  bc, (rf_home_y)
        add hl, bc
        add hl, de
        call rpm_px
        add a, 120 - 3
        ld  l, a
        ld  h, 0
        ld  (rpu_y), hl
        pop hl
        ld  iy, rpm_info
        ld  a, PG_RADAR
        call rps_raw
        ld  a, RPS_HUD_LAYER
        ld  (rpu_layer), a
        ret
; HL = pixels from the first square -> A = the radar pixel.
rpm_px:
        ld  a, l
        rrca
        rrca
        rrca
        rrca
        and $0F
        ld  c, a
        ld  a, h
        rlca
        rlca
        rlca
        rlca
        and $70
        or  c                   ; (HL & $7F0) >> 4
        ld  c, a
        ld  a, (radar_small)
        or  a
        ld  a, c
        ret nz
        srl a
        ret
rpr_info:
        DB  0, 0, 8, 64
rpm_info:
        DB  0, 0, 1, 7

; The CREDITS LOW warning (ui_warning_blink $0099A8, the sprite of
; ui_sidebar_sprites_init $009BDA): 88 x 8 at (112, 112), over everything.
HUD_LOW         EQU 410

rph_warning:
        ld  a, (crd_low)
        or  a
        ret z
        ld  a, RPS_WARN_LAYER
        ld  (rpu_layer), a
        ld  hl, 112
        ld  (rpu_x), hl
        ld  (rpu_y), hl
        ld  de, HUD_LOW
        call rps_frame
        ld  a, RPS_HUD_LAYER
        ld  (rpu_layer), a
        ret

; The credits counter: crd_text at (256, 16).
HUD_DIGITS      EQU 400
HUD_UNIT        EQU 430
HUD_STRUCT      EQU 460
HUD_BAR         EQU 480

rph_credits:
        ld  hl, 16
        ld  (rpu_y), hl
        ld  hl, 256
        ld  (rpu_x), hl
        ld  hl, crd_text
        ld  b, 6
rpc_loop:
        push bc
        push hl
        ld  a, (hl)
        cp  10
        jr  nc, rpc_next
        ld  e, a
        ld  d, 0
        ld  hl, HUD_DIGITS
        add hl, de
        ex  de, hl
        call rps_frame
rpc_next:
        ld  hl, (rpu_x)
        ld  de, 8
        add hl, de
        ld  (rpu_x), hl
        pop hl
        inc hl
        pop bc
        djnz rpc_loop
        ret

; The side panel: the selection's portrait at (272, 48) and its health
; bar at (272, 72), eighths filled, red under a quarter, yellow under
; three, green above (ui_draw_selection_panel $0294BE).
rph_panel:
        ld  a, (unit_selected)
        cp  $FF
        jr  z, rpp_struct
        call unit_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (ix + O_TYPE)
        push af
        call unit_info
        pop af
        ld  de, HUD_UNIT
        jr  rpp_show
rpp_struct:
        ld  a, (struct_selected)
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (ix + O_TYPE)
        push af
        call struct_info
        pop af
        ld  de, HUD_STRUCT
rpp_show:
        ; HL = the type's record (hit points at +16 in both), A = type
        push hl
        ld  l, a
        ld  h, 0
        add hl, de
        ex  de, hl
        ld  hl, 272
        ld  (rpu_x), hl
        ld  hl, 48
        ld  (rpu_y), hl
        call rps_frame
        pop hl
        ld  de, UI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = the most
        ld  a, d
        or  e
        ret z
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ; eighths: (hp * 8 + most - 1) / most, 0-8
        push de
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, de
        dec hl
        call udiv16             ; HL / DE
        pop de
        ld  a, l
        cp  9
        jr  c, rpp_e
        ld  a, 8
rpp_e:  ld  c, a
        ; the colour by quarters: 0 red, 1-2 yellow, 3-4 green
        ld  b, 2 * 9
        cp  2
        jr  c, rpp_c
        ld  b, 1 * 9
        cp  6
        jr  c, rpp_c
        ld  b, 0
rpp_c:  ld  a, b
        add a, c
        ld  e, a
        ld  d, 0
        ld  hl, HUD_BAR
        add hl, de
        ex  de, hl
        ld  hl, 72
        ld  (rpu_y), hl
        call rps_frame
        ; the lower half as UI chose it (ui_selection_panel): the second
        ; bar, the lower picture, the label over it ($FFFF: none)
        ld  hl, (panel_bar2_y)
        ld  (rpu_y), hl
        ld  de, (panel_bar2)
        call rps_frame
        ld  hl, 88
        ld  (rpu_y), hl
        ld  de, (panel_pic2)
        call rps_frame
        ld  a, (panel_label)
        or  a
        ret z
        ld  de, HUD_LABEL
        jp  rps_frame

; The corners round the selected structure: its squares' box, blinking
; with the unit's bracket.
rph_struct_box:
        ld  a, (struct_selected)
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (rph_hidden)
        or  a
        ret nz
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_size_r
        add hl, de
        ld  a, (hl)
        ld  (rsb_w), a
        inc hl
        inc hl
        ld  a, (hl)
        ld  (rsb_h), a
        ; the box: x0 = position / 8 - view, x1 = x0 + w * 32 - 1
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        ld  (rsb_x0), hl
        ld  a, (rsb_w)
        call rsb_span
        ld  (rsb_x1), hl
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        call shr3_hl
        ld  de, (view_y)
        or  a
        sbc hl, de
        ld  (rsb_y0), hl
        ld  a, (rsb_h)
        call rsb_span
        ld  (rsb_y1), hl
        ; the corners' frames sit 4 pixels out (TL: its frame's dx, dy 3)
        ld  hl, (rsb_x0)
        ld  de, (rsb_y0)
        ld  bc, 334
        call rsb_corner
        ld  hl, (rsb_x1)
        ld  de, (rsb_y0)
        ld  bc, 335
        call rsb_corner
        ld  hl, (rsb_x0)
        ld  de, (rsb_y1)
        ld  bc, 336
        call rsb_corner
        ld  hl, (rsb_x1)
        ld  de, (rsb_y1)
        ld  bc, 337
        ; fall through
; HL = x, DE = y of the box's corner, BC = the frame (334 TL, 335 TR, 336
; BL, 337 BR): left corners -4, right -12; top -4, bottom -12.
rsb_corner:
        push de
        ld  de, -4
        bit 0, c
        jr  z, rsc_x
        ld  de, -12
rsc_x:  add hl, de
        ld  (rpu_x), hl
        pop hl
        ld  de, -4
        ld  a, c
        cp  336 & $FF
        jr  c, rsc_y
        ld  de, -12
rsc_y:  add hl, de
        ld  (rpu_y), hl
        ld  d, b
        ld  e, c
        jp  rps_frame

; HL = a start, A = squares -> HL = the start + A * 32 - 1.
rsb_span:
        ex  de, hl
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        dec hl
        add hl, de
        ret

tbl_layout_size_r:
        DW  1, 1, 2, 1, 1, 2, 2, 2, 2, 3, 3, 2, 3, 3
rsb_x0: DW  0
rsb_x1: DW  0
rsb_y0: DW  0
rsb_y1: DW  0
rsb_w:  DB  0
rsb_h:  DB  0


; HL = the view's coordinate, BC = the far bound -> HL = the lowest
; position in view (max(0, HL - 64) * 8), DE = how many from there
; ((HL + BC) * 8 - that).
; HL = the lowest position, DE = the width -> L = its high byte, H = one
; past the highest's: rps_unit's quick test (positions stay below $4800).
rps_hbytes:
        ld  a, h
        add hl, de
        ld  l, a
        inc h
        ret

rps_bounds:
        push hl
        add hl, bc
        add hl, hl
        add hl, hl
        add hl, hl
        ex  de, hl              ; DE = (view + BC) * 8
        pop hl
        ld  bc, -64
        add hl, bc
        jr  c, rpb_1
        ld  hl, 0               ; (the view is less than 64 in)
rpb_1:  add hl, hl
        add hl, hl
        add hl, hl
        ex  de, hl
        or  a
        sbc hl, de
        ex  de, hl
        ret

; IX = a unit: add its sprite(s) if the player can see it.  Off the map
; only while U_SHOWN (a Harvester on a Refinery's pad).
rps_unit:
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, rpu_onmap
        ld  a, (ix + U_SHOWN)
        or  a
        ret z
rpu_onmap:
        ; roughly on the screen? (frames are at most 51 pixels): -64 <= x
        ; < 384 and -64 <= y < 264 on it, x and y = position / 8 - view.
        ; The high bytes first: most units are nowhere near
        ld  hl, (rps_yhb)
        ld  a, (ix + O_POS_Y + 1)
        cp  l
        ret c
        cp  h
        ret nc
        ld  hl, (rps_xhb)
        ld  a, (ix + O_POS_X + 1)
        cp  l
        ret c
        cp  h
        ret nc
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        ld  de, (rps_xlo)
        or  a
        sbc hl, de
        ret c
        ld  de, (rps_xw)
        sbc hl, de
        ret nc
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        ld  de, (rps_ylo)
        or  a
        sbc hl, de
        ret c
        ld  de, (rps_yw)
        sbc hl, de
        ret nc
        PROF 18
        ; the screen position of the object
        ld  l, (ix + O_POS_X)
        ld  h, (ix + O_POS_X + 1)
        call shr3_hl
        ld  de, (view_x)
        or  a
        sbc hl, de
        ld  (rpu_x), hl
        ld  l, (ix + O_POS_Y)
        ld  h, (ix + O_POS_Y + 1)
        call shr3_hl
        ld  de, (view_y)
        or  a
        sbc hl, de
        ld  (rpu_y), hl
        ; hidden under the fog: the player's own always show; the rest
        ; only on a square that is revealed and not under the full fog
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, rpu_seen
        ld  a, PG_MAP           ; the map in place of the directory, a moment
        call map_w3
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  c, 0                ; C = 0: not seen
        bit MF_UNVEILED, (hl)
        jr  z, rpu_fog
        ld  a, h
        xor (MAP_FLAGS ^ MAP_HIGH) >> 8
        ld  h, a
        ld  a, (hl)
        and $FE
        cp  OVL_FOG << 1
        jr  z, rpu_fog
        inc c
rpu_fog:
        ld  a, PG_SPRDIR
        call map_w3
        dec c
        ret nz
rpu_seen:
        ; the house's palette line
        ld  a, (ix + O_HOUSE)
        cp  6
        jr  c, rpu_h
        xor a
rpu_h:  ld  e, a
        ld  d, 0
        ld  hl, spr_line_of_house
        add hl, de
        ld  a, (hl)
        ld  (rpu_line), a
        ; the layer
        ld  e, (ix + O_TYPE)
        ld  hl, spr_unit_layer
        add hl, de
        ld  a, (hl)
        ld  (rpu_layer), a
        ; an effect animation's blink has it off this pass (MOVE2)
        bit 7, (ix + U_BLINK)
        ret nz
        ; the frame, by the type's mode
        ld  a, (ix + O_TYPE)
        ld  l, a
        ld  h, 0
        ld  de, spr_unit_mode
        add hl, de
        ld  a, (hl)
        ld  (rpu_mode), a
        ld  a, (ix + U_OR0_CURRENT)
        add a, 16
        rlca
        rlca
        rlca
        and 7
        ld  c, a                ; C = dir8
        ld  a, (rpu_mode)
        or  a
        jr  z, rpu_m0
        dec a
        jr  z, rpu_m1
        dec a
        jr  z, rpu_m2
        dec a
        jr  z, rpu_m3
        dec a
        jr  z, rpu_m4
        dec a
        jr  z, rpu_m5
        dec a
        jr  z, rpu_m6
        ; 7 the Frigate: its picture, and its cargo while bit 9 is set
        ld  a, c
        call rpu_add
        bit 1, (ix + O_FLAGS2 + 1)
        ret z
        ld  a, c
        add a, 8
        jp  rpu_add
rpu_m0: xor a
        jp  rpu_add
rpu_m1: ld  a, c
        jp  rpu_add
rpu_m2: ld  a, (ix + U_OR0_CURRENT)
        add a, 8
        rlca
        rlca
        rlca
        rlca
        and 15
        jp  rpu_add
rpu_m3: ld  a, (ix + U_SPRITEOFS)
        and 3
        ld  b, a
        ld  a, c
        add a, a
        add a, a
        add a, b
        jp  rpu_add
rpu_m4: ld  a, c                ; 'Thopter: dir8 * 3 + the rotor phase
        add a, a
        add a, c
        ld  hl, rotor_phase
        add a, (hl)
        jp  rpu_add
rpu_m5: ld  a, (ix + O_LINKED)  ; Carryall: + 8 while it carries
        inc a
        ld  a, c
        jr  z, rpu_m5a
        add a, 8
rpu_m5a:
        jp  rpu_add
rpu_m6: ld  a, c                ; Tank, Siege Tank: hull, then the turret
        call rpu_add
        ld  a, 1                ; the turret takes the hull's key, so it
        ld  (rpu_lock), a       ; goes in after it whatever its frame's dy
        ld  a, (ix + U_OR1_CURRENT)
        add a, 16
        rlca
        rlca
        rlca
        and 7
        add a, 8
        call rpu_add
        xor a
        ld  (rpu_lock), a
        ret

; A = the index into the type's 32 frame ids: add that frame.
rpu_add:
        push bc
        ld  e, a
        ld  d, 0
        ld  a, (ix + O_TYPE)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl              ; * 64
        add hl, de
        add hl, de
        ld  de, spr_unit_ids
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = the frame id
        ld  a, d
        and e
        inc a
        call nz, rps_frame
        pop bc
        ret

; DE = a frame id: add it at rpu_x/rpu_y (the object) in rpu_line, rpu_layer.
rps_frame:
        PROF 19
        ld  a, (rps_n)
        ld  hl, rps_limit
        cp  (hl)
        ret nc
        ld  hl, SPR_FRAMES - 1  ; an id past the directory: nothing
        or  a
        sbc hl, de
        ret c
        ; spr_info: dx, dy, W, h
        ld  h, d
        ld  l, e
        add hl, hl
        add hl, hl
        ld  bc, spr_info
        add hl, bc
        push hl
        pop iy
        ; spr_loc + id * 3: the page (bit 7: a copy per palette line)
        ld  h, d
        ld  l, e
        add hl, hl
        add hl, de
        ld  bc, spr_loc
        add hl, bc
        ld  a, (hl)
        or  a
        ret z                   ; a frame with no picture
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = the address
        ld  c, a
        bit 7, a
        jr  z, rpf_have
        res 7, c
        ; + line * (2 + 8 * W * h)
        ld  a, (rpu_line)
        or  a
        jr  z, rpf_have
        ld  b, a
        push de
        ld  e, (iy + 3)         ; h
        ld  d, 0
        ld  a, (iy + 2)         ; W
        ld  hl, 0
rpf_wh: add hl, de
        dec a
        jr  nz, rpf_wh
        add hl, hl
        add hl, hl
        add hl, hl
        inc hl
        inc hl                  ; the frame's size
        ex  de, hl
        pop hl
rpf_ln: add hl, de
        djnz rpf_ln
        ex  de, hl
; C = the page, DE = the address, IY -> dx, dy, W, h: the entry, and its
; record in the sorted list.
rpf_have:
        ld  hl, (rps_out)
        push hl                 ; the entry
        ; x = rpu_x + dx
        push de
        ld  a, (iy + 0)         ; dx, signed
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        push hl
        ld  hl, (rpu_x)
        add hl, de
        ex  de, hl
        pop hl
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ; y = rpu_y + dy
        ld  a, (iy + 1)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        push hl
        ld  hl, (rpu_y)
        add hl, de
        ld  (rpu_fy), hl
        ex  de, hl
        pop hl
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        pop de
        ld  (hl), c             ; the page
        inc hl
        ld  (hl), e             ; the address
        inc hl
        ld  (hl), d
        inc hl
        ld  a, (iy + 2)         ; W
        ld  (hl), a
        inc hl
        ld  a, (iy + 3)         ; h
        ld  (hl), a
        inc hl
        ld  (hl), 1             ; E_FLAG (rf_match_sprites decides)
        ld  de, E_SIZE - E_FLAG
        add hl, de
        ld  (rps_out), hl
        ; the key: layer << 8 | y clamped to 0-255
        ld  hl, (rpu_fy)
        ld  a, (rpu_lock)
        or  a
        jr  z, rpf_ky
        ld  hl, (rpu_lastfy)
rpf_ky: ld  (rpu_lastfy), hl
        ld  a, h
        or  a
        ld  a, l
        jr  z, rpf_k
        ld  a, 0
        jp  m, rpf_k
        ld  a, 255
rpf_k:  ld  e, a
        ld  a, (rpu_layer)
        ld  d, a                ; DE = the key
        ; into the sorted records: after every one whose key is not above
        ; it (the list is made mostly in order: usually none is passed)
        ld  hl, (rps_rec)       ; -> the free record at the end
        ld  a, (rps_n)
        or  a
        jr  z, rpf_put
        ld  b, a
rpf_scan:
        dec hl
        dec hl
        dec hl                  ; -> the record before's key high byte
        ld  a, d
        cp  (hl)
        jr  c, rpf_more         ; its layer is above ours
        jr  nz, rpf_here
        dec hl
        ld  a, e
        cp  (hl)
        inc hl
        jr  nc, rpf_here        ; its key is not above ours
rpf_more:
        dec hl
        djnz rpf_scan
        jr  rpf_move            ; HL -> the first record
rpf_here:
        inc hl
        inc hl
        inc hl                  ; -> the record after it
rpf_move:
        ; HL = our place: it and the records after move up by one
        push de
        push hl
        ex  de, hl
        ld  hl, (rps_rec)
        or  a
        sbc hl, de              ; the bytes to move
        jr  z, rpf_moved
        ld  b, h
        ld  c, l
        ld  hl, (rps_rec)
        dec hl
        ld  d, h
        ld  e, l
        inc de
        inc de
        inc de
        inc de
        lddr
rpf_moved:
        pop hl
        pop de
rpf_put:
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        pop de                  ; the entry
        ld  (hl), e
        inc hl
        ld  (hl), d
        ld  hl, (rps_rec)
        inc hl
        inc hl
        inc hl
        inc hl
        ld  (rps_rec), hl
        ld  hl, rps_n
        inc (hl)
        ret

; HL = HL >> 3, logical (positions are never negative).
shr3_hl:
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ret

; ------------------------------------------------------------- drawing them

rf_draw_sprites:
        ld  hl, (rf_new)
        ld  a, (hl)
        or  a
        ret z
        inc hl
        ld  b, a
rds_loop:
        push bc
        inc hl
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        push hl
        ld  hl, E_FLAG
        add hl, de
        ld  a, (hl)
        or  a
        call nz, rf_sprite
        pop hl
        pop bc
        djnz rds_loop
        ret

; DE = an entry: draw its two planes of this pass, clipped.
rf_sprite:
        push de
        pop ix
        ld  a, (ix + E_PAGE)
        call rc_map_art
        ; the rows: skip max(0, -y), draw up to the bottom
        ld  e, (ix + E_Y)
        ld  d, (ix + E_Y + 1)
        ld  c, (ix + E_H)
        ld  b, 0                ; rows skipped
        bit 7, d
        jr  z, rsp_r_nonneg
        ld  a, e
        neg
        ld  b, a
        cp  c
        ret nc
        ld  de, 0
rsp_r_nonneg:
        ld  a, d
        or  a
        ret nz
        ld  a, e
        cp  SCR_H
        ret nc
        ld  (rsp_y), a
        ld  a, SCR_H
        sub e
        ld  e, a
        ld  a, c
        sub b
        cp  e
        jr  c, rsp_r_fit
        ld  a, e
rsp_r_fit:
        ld  (rsp_rows), a
        ; a source row is W * 2 bytes; the rows skipped rskip * W * 2
        ld  a, (ix + E_W)
        add a, a
        ld  (rsp_w2), a
        ld  hl, 0
        ld  d, h
        ld  e, a
        inc b
        jr  rsp_sk2
rsp_sk1:
        add hl, de
rsp_sk2:
        djnz rsp_sk1
        ld  (rsp_sk), hl
        ; one plane's block: h * W * 2
        ld  hl, 0
        ld  b, (ix + E_H)
rsp_pl: add hl, de
        djnz rsp_pl
        ld  (rsp_plane), hl
        ; the phase and the first column
        ld  a, (ix + E_X)
        and 6
        rrca
        ld  (rsp_phase), a
        ld  e, (ix + E_X)
        ld  d, (ix + E_X + 1)
        ld  a, e
        sra d
        rra
        sra d
        rra
        sra d
        rra
        ld  (rsp_col), a
        ; the screen's row: y * 40
        ld  a, (rsp_y)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        ld  (rsp_yoff), hl
        ; the radar's picture is opaque and whole (8 columns, on a cell):
        ; its data bytes are copied, the masks passed over - a third of the
        ; time, and it is drawn whenever its marker moves
        xor a
        ld  (rsp_opaque), a
        ld  a, (ix + E_PAGE)
        cp  PG_RADAR
        jr  nz, rsp_pl2
        ld  a, (ix + E_W)
        cp  8
        jr  nz, rsp_pl2
        ld  (rsp_opaque), a
rsp_pl2:
        ; the screen planes of this pass: A 0 and 2, B 1 and 3
        ld  a, (rf_pass)
        or  a
        ld  a, 0
        jr  z, rsp_pa
        inc a
rsp_pa: ld  (rsp_d), a
        ld  hl, SCR_LO
        call rsp_one
        ld  a, (rsp_d)
        add a, 2
        ld  (rsp_d), a
        ld  hl, SCR_HI
        ; fall through

; Screen plane rsp_d at base HL: from source plane (d - p) & 3, one column
; right if d < p.
rsp_one:
        ld  de, (rsp_yoff)
        add hl, de
        ld  (rsp_base), hl
        ld  a, (rsp_phase)
        ld  b, a
        ld  a, (rsp_d)
        sub b
        and 3                   ; the source plane
        ld  c, a
        ld  a, (rsp_d)
        cp  b
        ld  a, (rsp_col)
        jr  nc, rso_c
        inc a                   ; d < p: one column right
rso_c:  ld  (rsp_c0), a
        ; the source: frame + 2 + s * plane + rskip * W * 2
        ld  l, (ix + E_ADDR)
        ld  h, (ix + E_ADDR + 1)
        inc hl
        inc hl
        ld  de, (rsp_plane)
        inc c
rso_s:  dec c
        jr  z, rso_s0
        add hl, de
        jr  rso_s
rso_s0: ld  de, (rsp_sk)
        add hl, de
        ; the columns: skip max(0, -c0), n = min(W, 40 - c0) - skip
        ld  c, (ix + E_W)
        ld  b, 0
        ld  a, (rsp_c0)
        bit 7, a
        jr  z, rso_cpos
        neg
        ld  b, a                ; columns skipped
        cp  c
        ret nc
        xor a
rso_cpos:
        cp  CELLS_W
        ret nc
        ld  e, a                ; the first screen column
        ld  a, CELLS_W
        sub e
        ld  d, a                ; room to the right
        ld  a, c
        sub b
        cp  d
        jr  c, rso_cfit
        ld  a, d
rso_cfit:
        or  a
        ret z
        ld  (rsp_n), a
        ; the source past the columns skipped
        ld  a, b
        add a, a
        add a, l
        ld  l, a
        jr  nc, rso_1
        inc h
rso_1:  ; the screen: base + column
        push hl
        ld  hl, (rsp_base)
        ld  d, 0
        add hl, de
        ex  de, hl              ; DE = the screen
        pop hl                  ; HL = the source
        ld  a, (rsp_rows)
        or  a
        ret z
        ld  b, a
        ld  a, (rsp_opaque)
        or  a
        jr  z, rpd_masked
        ld  a, (rsp_n)
        cp  8
        jp  z, rpd_opaque
rpd_masked:
        ; rows of n (mask, data) pairs: into the unrolled row n from its
        ; end; the source then steps past what the row did not take
        ld  a, (rsp_n)
        ld  c, a
        add a, a
        add a, a
        add a, a
        sub c                   ; n * 7 bytes of code
        neg
        push de
        ld  e, a
        ld  d, $FF
        push hl
        ld  hl, rmr_end
        add hl, de
        ld  (rpd_jump + 1), hl
        pop hl
        pop de
        ld  a, (rsp_w2)
        sub c
        sub c                   ; source bytes past the row: mostly none
        ld  (rpd_skip + 1), a
        ld  a, rpd_t0 - rmr_end - 2
        jr  z, rpd_0
        xor a                   ; (to rpd_t1)
rpd_0:  ld  (rmr_end + 1), a
        ld  a, CELLS_W
        sub c
        ld  c, a                ; C = the screen's step
rpd_jump:
        jp  rmr_end
        ; the unrolled row: HL = the source, DE = the screen
        REPT 11
        ld  a, (de)             ; the screen
        and (hl)                ; AND the mask
        inc hl
        or  (hl)                ; OR the data
        inc hl
        ld  (de), a
        inc de
        ENDR
rmr_end:
        jr  rpd_t0              ; (rpd_t1 when the source steps)
rpd_t1: ld  a, l
rpd_skip:
        add a, 0
        ld  l, a
        jr  nc, rpd_t0
        inc h
rpd_t0: ld  a, e
        add a, c
        ld  e, a
        jr  nc, rpd_2
        inc d
rpd_2:  djnz rpd_jump
        ret
rpd_opaque:
        ; 8 data bytes a row, the masks passed over (ldi counts BC down:
        ; the rows are counted in A)
        ld  a, b
rpo_row:
        push af
        REPT 8
        inc hl
        ldi
        ENDR
        ld  a, e
        add a, 40 - 8
        ld  e, a
        jr  nc, rpo_1
        inc d
rpo_1:  pop af
        dec a
        jr  nz, rpo_row
        ret

; ---------------------------------------------------------- 5. remember
; This screen now shows the sprites of the new list: it becomes the
; screen's old list, and its old one the next new one.  (Pass B left the
; cells clean.)
rf_remember:
        ld  hl, (rf_oldp)
        ld  de, (rf_new)
        ld  c, (hl)
        ld  (hl), e
        inc hl
        ld  b, (hl)
        ld  (hl), d
        ld  (rf_new), bc
        ret
