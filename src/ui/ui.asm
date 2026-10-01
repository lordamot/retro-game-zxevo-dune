; ui.asm - bank UI: the battle's controls (S10), for a keyboard or a
; joystick standing in for the Mega Drive pad (stub/input.asm).
;
; ui_battle_input is the battle loop's input step (battle_input_poll
; $004C88): the cursor, the view, and what A and B do; then, as the
; cartridge's always does, the side panel (ui_draw_selection_panel
; $0294BE, below).

; ------------------------------------------------------------- the cursor
;
; The d-pad moves the cursor; its speed builds up by 1/16 pixel a frame
; while a direction is held, to at most 3 pixels a frame ($006180).  With
; C held the d-pad moves the view instead.  At the screen's edges the view
; follows the cursor (the Mega Drive scrolls when the cursor leaves the
; middle; the port, whose scrolling costs a copy of the screen, at the
; edges).  The view moves in cells, by the pixels a pass earns (view_move).
;
; Two modes, the cartridge's two frame hooks.  The free cursor
; (irq_battle_free_cursor $006D0C) goes pixel by pixel.  The grid cursor
; (irq_battle_grid_cursor $00608E), on while a Construction Yard's
; finished building is being placed, stops only where the footprint lines
; up with the map's squares: an axis let go off the grid carries on the
; way it last went until it is on it.  While the view shakes neither reads
; the pad (view_shake_frame $005E26).

CURSOR_MAX_SPEED EQU 3 * 256

ui_battle_input:
        call ubi_input
        jp  ui_selection_panel  ; always last ($004CAE)
ubi_input:
        ld  a, (frames_this_pass)
        or  a
        jr  nz, ubi_1
        inc a
ubi_1:  cp  8
        jr  c, ubi_2
        ld  a, 8                ; a very slow pass does not fling it
ubi_2:  ld  (ubi_frames), a
        call ui_place_mode
        call view_shake_frame
        jr  z, ubi_pad
        jp  pad_take            ; what is pressed while it shakes is lost
ubi_pad:
        ld  a, (cursor_grid)
        or  a
        jp  nz, ubi_grid
        ld  a, (pad_held)
        ld  c, a
        and $0F
        jr  z, ubi_still
        bit PAD_C, c
        jr  nz, ubi_moving
ubi_still:
        ; the view's count of fast frames starts again unless C and a
        ; direction are held together ($006E2C-$006E42)
        ld  a, UBV_SLOW
        ld  (ubv_slow), a
        ld  a, c
        and $0F
        jr  nz, ubi_moving
        ld  hl, 0
        ld  (cursor_speed), hl
        ld  (ubv_frac), hl      ; the view's part cells
        jp  ubi_buttons
ubi_moving:
        call ubi_speed
        ld  a, (pad_held)
        ld  c, a
        bit PAD_C, c
        jp  nz, ubi_view
        ; the cursor
        ld  a, (ubi_step)
        ld  e, a
        ld  d, 0
        bit PAD_LEFT, c
        jr  z, ubi_4
        ld  hl, (cursor_x)
        or  a
        sbc hl, de
        jr  nc, ubi_4s
        ld  hl, 0
ubi_4s: ld  (cursor_x), hl
ubi_4:  bit PAD_RIGHT, c
        jr  z, ubi_5
        ld  hl, (cursor_x)
        add hl, de
        push hl
        ld  bc, 319
        or  a
        sbc hl, bc
        pop hl
        jr  c, ubi_5s
        ld  hl, 319
ubi_5s: ld  (cursor_x), hl
ubi_5:  ld  a, (pad_held)
        ld  c, a
        bit PAD_UP, c
        jr  z, ubi_6
        ld  hl, (cursor_y)
        or  a
        sbc hl, de
        jr  nc, ubi_6s
        ld  hl, 0
ubi_6s: ld  (cursor_y), hl
ubi_6:  bit PAD_DOWN, c
        jr  z, ubi_edges
        ld  hl, (cursor_y)
        add hl, de
        push hl
        ld  bc, 199
        or  a
        sbc hl, bc
        pop hl
        jr  c, ubi_7s
        ld  hl, 199
ubi_7s: ld  (cursor_y), hl
ubi_edges:
        ; the view follows a cursor pushed at an edge, at 3 pixels a frame
        ; (the most the Mega Drive's follows it at, $0070BE-$0070D4)
        ld  a, (pad_held)
        ld  c, a
        ld  b, 0                ; B = the directions pushing at an edge
        ld  hl, (cursor_x)
        ld  a, h
        or  a
        jr  nz, ube_r
        ld  a, l
        cp  4
        jr  nc, ube_r
        ld  a, c
        and 1 << PAD_LEFT
        or  b
        ld  b, a
ube_r:  ld  hl, (cursor_x)
        ld  de, 316
        or  a
        sbc hl, de
        jr  c, ube_u
        ld  a, c
        and 1 << PAD_RIGHT
        or  b
        ld  b, a
ube_u:  ld  a, (cursor_y)
        cp  4
        jr  nc, ube_d
        ld  a, c
        and 1 << PAD_UP
        or  b
        ld  b, a
ube_d:  ld  a, (cursor_y)
        cp  196
        jr  c, ube_go
        ld  a, c
        and 1 << PAD_DOWN
        or  b
        ld  b, a
ube_go: ld  c, b
        ld  a, (ubi_frames)
        ld  b, a
        add a, a
        add a, b
        call view_move
        jr  ubi_buttons
ubi_view:
        ; C held: the d-pad moves the view, 7 pixels a frame for the first
        ; UBV_SLOW frames C and a direction are held together, 14 after
        ; that ($006E3A-$006E6E, $006EEC-$006F8C)
        ld  a, (ubi_frames)
        ld  b, a
        xor a
ubv_1:  ld  e, 14
        ld  hl, ubv_slow
        inc (hl)
        dec (hl)
        jr  z, ubv_2
        dec (hl)
        ld  e, 7
ubv_2:  add a, e
        djnz ubv_1
        ld  hl, pad_held
        ld  c, (hl)
        call view_move
ubi_buttons:
        call ui_place_update
        call pad_take
        ld  (ubi_pressed), a
        bit PAD_A, a
        call nz, ui_press_a
        ld  a, (ubi_pressed)
        bit PAD_B, a
        call nz, ui_press_b
        ld  a, (ubi_pressed)
        bit PAD_START, a
        ret z
        ; Start: the options screen (opt_screen $020DA2); the game clock
        ; holds while it is up
        xor a
        ld  (timer_game_on), a
        FCALL front_options
        or  a
        jr  z, ubi_resume
        ld  (battle_request), a
        cp  3
        jr  nz, ubi_resume
        ld  a, b
        ld  (game_mission), a
        ld  a, c
        ld  (game_house), a
ubi_resume:
        ld  a, 1
        ld  (timer_game_on), a
        call ui_time_resync     ; ($02156A)
        FCALL render_invalidate
        ret

; time_resync ($004764) after the options screen or a structure's panel:
; the next pass counts its frames from now, so the time spent there is
; not the game's - but the music's countdown ran on, as the tune did (the
; panels add it back, $028A02-$028A04 and $028D6A-$028D6C; the options'
; menu loop charges it frame by frame, ui_menu_frame $008896).  Clobbers
; A, DE, HL.
ui_time_resync:
        ld  hl, (frame_count)
        ld  de, (frame_seen)
        ld  (frame_seen), hl
        or  a
        sbc hl, de              ; the frames spent
        ex  de, hl
        ld  hl, (music_frames_left)
        or  a
        sbc hl, de
        ld  (music_frames_left), hl
        ret

; The speed: +16/256 a frame while held, to at most CURSOR_MAX_SPEED
; ($006180-$00619A); then ubi_step, the whole pixels of this pass (speed x
; frames, the fraction kept in cursor_frac).  Keeps BC.
ubi_speed:
        push bc
        ld  hl, (cursor_speed)
        ld  a, (ubi_frames)
        ld  b, a
ubi_acc:
        ld  de, 16
        add hl, de
        djnz ubi_acc
        ld  de, CURSOR_MAX_SPEED
        or  a
        sbc hl, de
        add hl, de
        jr  c, ubi_3
        ex  de, hl
ubi_3:  ld  (cursor_speed), hl
        pop bc
ubi_step_px:
        push bc
        ld  hl, (cursor_speed)
        ld  a, (ubi_frames)
        ld  e, a
        ld  d, 0
        call mul16
        ld  a, (cursor_frac)
        add a, l
        ld  (cursor_frac), a
        ld  a, h
        adc a, 0
        ld  (ubi_step), a       ; whole pixels this pass
        pop bc
        ret

; ---------------------------------------------------------- the grid cursor
;
; irq_battle_grid_cursor $00617A-$006462.  The held directions move the
; cursor as the free one moves, within the footprint's limits (below).
; An axis not held that is off the map's 32-pixel grid carries on the way
; it last went ($FFBF48), at a pixel a frame beside a held axis or 1 1/16
; ($11000) with nothing held, and stops on the grid.  Up with down, or
; left with right, moves nothing.  At an edge the view follows, and the
; cursor gives the view's move back so that the footprint keeps its place
; on the map.
ubi_grid:
        ld  a, (pad_held)
        ld  c, a
        and $0F
        ld  b, a                ; B = the directions held
        bit PAD_C, c
        jr  z, ubg_1
        ; C: the view moves and the cursor stays, off the grid perhaps; the
        ; directions are kept for the carry afterwards
        or  a
        jp  z, ubi_buttons
        ld  (cursor_dirs), a
        jp  ubi_view
ubg_1:  or  a
        jr  z, ubg_none
        and $03
        cp  $03
        jp  z, ubi_buttons
        ld  a, b
        and $0C
        cp  $0C
        jp  z, ubi_buttons
        call ubi_speed          ; the held axes: ubi_step
        ld  a, (ubi_frames)
        ld  (ubg_carry), a      ; a carried one: a pixel a frame
        ld  c, 0
        ld  a, b
        and $03
        jr  nz, ubg_2
        call ubg_off_y
        jr  z, ubg_2
        ld  a, (cursor_dirs)
        and $03
        ld  c, a
ubg_2:  ld  a, b
        and $0C
        jr  nz, ubg_3
        call ubg_off_x
        jr  z, ubg_3
        ld  a, (cursor_dirs)
        and $0C
        or  c
        ld  c, a
ubg_3:  ld  a, b
        or  c
        ld  (cursor_dirs), a
        jr  ubg_move
ubg_none:
        ; nothing held ($006230): an axis off the grid carries on
        ld  hl, 256
        ld  (cursor_speed), hl
        ld  c, 0
        call ubg_off_y
        jr  z, ubg_n1
        ld  a, (cursor_dirs)
        and $03
        ld  c, a
        jr  nz, ubg_n1
        call ubg_snap_y         ; at rest off the grid, which only a poke
ubg_n1: call ubg_off_x          ; leaves it: the square it is in
        jr  z, ubg_n2
        ld  a, (cursor_dirs)
        and $0C
        jr  nz, ubg_n1a
        call ubg_snap_x
        xor a
ubg_n1a:
        or  c
        ld  c, a
ubg_n2: ld  a, c
        or  a
        jp  z, ubi_buttons
        ld  (cursor_dirs), a
        ld  hl, 256 + 16        ; $10000 + the frame's $1000
        ld  (cursor_speed), hl
        call ubi_step_px
        ld  a, (ubi_step)
        ld  (ubg_carry), a
        ld  b, 0
        ; fall through

; B = the directions held (moved by ubi_step within the limits), C = the
; ones carried (moved by ubg_carry, as far as the grid).
ubg_move:
        ; ---- x
        ld  hl, (cursor_x)
        ld  a, (ubi_step)
        ld  e, a
        ld  d, 0
        bit PAD_LEFT, b
        jr  z, ubgx_1
        or  a
        sbc hl, de
        jr  nc, ubgx_1
        ld  hl, 0
ubgx_1: bit PAD_RIGHT, b
        jr  z, ubgx_2
        add hl, de
ubgx_2: bit PAD_LEFT, c
        jr  z, ubgx_3
        ld  de, (view_x)
        call ubg_off
        call ubg_carry_min
        or  a
        sbc hl, de
        jr  nc, ubgx_3
        ld  hl, 0
ubgx_3: bit PAD_RIGHT, c
        jr  z, ubgx_4
        ld  de, (view_x)
        call ubg_off
        jr  z, ubgx_4
        neg
        add a, 32
        call ubg_carry_min
        add hl, de
ubgx_4: ld  de, (ubg_xmax)
        call ubg_clamp
        ld  (cursor_x), hl
        ; the view follows at an edge
        ld  a, b
        or  c
        bit PAD_LEFT, a
        jr  z, ubgx_5
        ld  a, h
        or  a
        jr  nz, ubgx_5
        ld  a, l
        cp  4
        jr  nc, ubgx_5
        ld  hl, view_left
        call ubg_follow_x
ubgx_5: ld  a, b
        or  c
        bit PAD_RIGHT, a
        jr  z, ubgy
        ld  hl, (ubg_xmax)
        ld  de, -3
        add hl, de
        ld  de, (cursor_x)
        or  a
        sbc hl, de
        jr  z, ubgx_6
        jr  nc, ubgy
ubgx_6: ld  hl, view_right
        call ubg_follow_x
ubgy:   ; ---- y
        ld  hl, (cursor_y)
        ld  a, (ubi_step)
        ld  e, a
        ld  d, 0
        bit PAD_UP, b
        jr  z, ubgy_1
        or  a
        sbc hl, de
        jr  nc, ubgy_1
        ld  hl, 0
ubgy_1: bit PAD_DOWN, b
        jr  z, ubgy_2
        add hl, de
ubgy_2: bit PAD_UP, c
        jr  z, ubgy_3
        ld  de, (view_y)
        call ubg_off
        call ubg_carry_min
        or  a
        sbc hl, de
        jr  nc, ubgy_3
        ld  hl, 0
ubgy_3: bit PAD_DOWN, c
        jr  z, ubgy_4
        ld  de, (view_y)
        call ubg_off
        jr  z, ubgy_4
        neg
        add a, 32
        call ubg_carry_min
        add hl, de
ubgy_4: ld  de, (ubg_ymax)
        call ubg_clamp
        ld  (cursor_y), hl
        ld  a, b
        or  c
        bit PAD_UP, a
        jr  z, ubgy_5
        ld  a, l
        cp  4
        jr  nc, ubgy_5
        ld  hl, view_up
        call ubg_follow_y
ubgy_5: ld  a, b
        or  c
        bit PAD_DOWN, a
        jp  z, ubi_buttons
        ld  hl, (ubg_yedge)
        ld  de, -3
        add hl, de
        ld  de, (cursor_y)
        or  a
        sbc hl, de
        jr  z, ubgy_6
        jp  nc, ubi_buttons
ubgy_6: ld  hl, view_down
        call ubg_follow_y
        jp  ubi_buttons

; HL = a cursor coordinate, DE = the view's -> A = how far the point is past
; the grid line before it ((HL + DE) & 31), Z on it.  Keeps HL.
ubg_off:
        ld  a, l
        add a, e
        and 31
        ret
ubg_off_x:
        ld  hl, (cursor_x)
        ld  de, (view_x)
        jr  ubg_off
ubg_off_y:
        ld  hl, (cursor_y)
        ld  de, (view_y)
        jr  ubg_off

; A = the way to the grid -> DE = the least of it and ubg_carry.
ubg_carry_min:
        push hl
        ld  hl, ubg_carry
        cp  (hl)
        jr  c, ucm_1
        ld  a, (hl)
ucm_1:  ld  e, a
        ld  d, 0
        pop hl
        ret

; HL = a coordinate, DE = its largest -> HL no larger (a wrap below 0 is
; not possible: the callers clamp at 0 first).
ubg_clamp:
        push hl
        or  a
        sbc hl, de
        pop hl
        ret c
        ret z
        ex  de, hl
        ret

; HL = view_left or view_right (view_up/view_down): move the view, and the
; cursor gives the move back.  Keeps BC.
ubg_follow_x:
        push bc
        ld  de, (view_x)
        push de
        call ubg_jp_hl
        pop de
        ld  hl, (view_x)
        or  a
        sbc hl, de              ; the view's move
        ex  de, hl
        ld  hl, (cursor_x)
        or  a
        sbc hl, de
        ld  (cursor_x), hl
        pop bc
        ret
ubg_follow_y:
        push bc
        ld  de, (view_y)
        push de
        call ubg_jp_hl
        pop de
        ld  hl, (view_y)
        or  a
        sbc hl, de
        ex  de, hl
        ld  hl, (cursor_y)
        or  a
        sbc hl, de
        ld  (cursor_y), hl
        pop bc
        ret
ubg_jp_hl:
        jp  (hl)

; A cursor at rest off the grid goes to the square it is in (or the next
; one, if that is before the screen's edge); within the limits.
ubg_snap_x:
        push bc
        ld  hl, (cursor_x)
        ld  de, (view_x)
        ld  bc, (ubg_xmax)
        call ubg_snap
        ld  (cursor_x), hl
        pop bc
        ret
ubg_snap_y:
        push bc
        ld  hl, (cursor_y)
        ld  de, (view_y)
        ld  bc, (ubg_ymax)
        call ubg_snap
        ld  (cursor_y), hl
        pop bc
        ret
; HL = a coordinate, DE = the view's, BC = the largest -> HL on the grid:
; ((HL + DE) & ~31) - DE, + 32 if that is below 0, - 32 while above BC.
ubg_snap:
        add hl, de
        ld  a, l
        and $E0
        ld  l, a
        or  a
        sbc hl, de
        bit 7, h
        jr  z, usn_1
        ld  de, 32
        add hl, de
usn_1:  push hl
        or  a
        sbc hl, bc
        pop hl
        ret c
        ret z
        ld  de, -32
        add hl, de
        jr  usn_1

; ------------------------------------------------- switching the cursor's mode
;
; The cartridge picks the hook where ui_battle_button sets the pointer
; ($028596, ui_cursor_for_selection $028D7A): the grid cursor while the
; player's Construction Yard is selected with its building finished, the
; free one otherwise.  Every pass, first: place_active, the footprint's
; size and the limits it gives the cursor ($0C7EA0: 320 - 32w and 224 -
; 32h), and the mode.  The port shows the Mega Drive's view less its 24
; bottom lines, so a footprint may hang below the screen by that much; the
; view follows when it is pushed past the screen's own bottom (ubg_yedge,
; 200 - 32h).
ui_place_mode:
        call ui_place_yard
        ld  a, 0
        jr  z, upm_set
        ld  a, (ix + S_OBJECTTYPE)
        call struct_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_size
        add hl, de              ; the width and height, words
        ld  a, (hl)
        ld  (place_w), a
        inc hl
        inc hl
        ld  a, (hl)
        ld  (place_h), a
        ld  a, (place_w)
        ld  de, 320
        call upm_max
        ld  (ubg_xmax), hl
        ld  a, (place_h)
        ld  de, 224
        call upm_max
        ld  (ubg_ymax), hl
        ld  a, (place_h)
        ld  de, 200
        call upm_max
        ld  (ubg_yedge), hl
        ld  a, 1
upm_set:
        ld  (place_active), a
        ld  hl, cursor_grid
        cp  (hl)
        ret z
        ld  (hl), a
        or  a
        jr  nz, cursor_mode_grid
        ; fall through

; cursor_mode_free ($004D16): the free cursor's hook again; the cursor
; stays where it is (the cartridge also drops a pending view move and
; button, which the port has not got).
cursor_mode_free:
        ret

; cursor_mode_grid ($004CBE): the cursor goes to the top-left of the
; square it is in, and from now on it stops only on squares.
cursor_mode_grid:
        call ubg_snap_x
        jp  ubg_snap_y

; A = squares, DE = the screen's size -> HL = DE - 32 * A.
upm_max:
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ex  de, hl
        or  a
        sbc hl, de
        ret

; The view, 8 pixels at a time, kept on the playable map.
; A = pixels (at most 127), C = directions (the pad's bits): the view
; moves that far along each axis a direction is held on.  It moves in
; cells, so what is left of a cell is kept for the next pass, and dropped
; on an axis that is not moving.
view_move:
        ld  b, a
        xor a
        bit PAD_LEFT, c
        jr  z, vmv_1
        sub b
vmv_1:  bit PAD_RIGHT, c
        jr  z, vmv_2
        ld  a, b
vmv_2:  ld  hl, ubv_frac
        ld  de, view_x
        call vmv_axis
        xor a
        bit PAD_UP, c
        jr  z, vmv_3
        sub b
vmv_3:  bit PAD_DOWN, c
        jr  z, vmv_4
        ld  a, b
vmv_4:  ld  hl, ubv_frac + 1
        ld  de, view_y
        call vmv_axis
        jp  ui_view_clamp
; A = the pixels (signed, at most 112 either way), HL -> the axis's part
; cell (-7..7), DE -> its view: the view moves by the whole cells of the
; two together, and the rest is kept.  Keeps BC.
vmv_axis:
        or  a
        jr  nz, vmva_1
        ld  (hl), a             ; not moving: nothing left over
        ret
vmva_1: add a, (hl)
        push bc
        ld  c, a
        bit 7, a
        jr  nz, vmva_neg
        and 7
        ld  (hl), a             ; what is left
        ld  a, c
        and $F8
        ld  c, a
        ld  b, 0                ; BC = the whole cells' pixels
        jr  vmva_add
vmva_neg:
        neg
        ld  b, a
        and 7
        neg
        ld  (hl), a             ; what is left, the other way
        ld  a, b
        and $F8
        neg
        ld  c, a
        ld  b, $FF              ; BC = minus the whole cells' pixels
        jr  nz, vmva_add
        ld  b, 0
vmva_add:
        ex  de, hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        add hl, bc
        ex  de, hl
        ld  (hl), d
        dec hl
        ld  (hl), e
        pop bc
        ret
view_left:
        ld  hl, (view_x)
        ld  de, -8
        jr  vw_x
view_right:
        ld  hl, (view_x)
        ld  de, 8
vw_x:   add hl, de
        ld  (view_x), hl
        jp  ui_view_clamp
view_up:
        ld  hl, (view_y)
        ld  de, -8
        jr  vw_y
view_down:
        ld  hl, (view_y)
        ld  de, 8
vw_y:   add hl, de
        ld  (view_y), hl
        ; fall through

; Keep the view inside the playable area of the map's scale (in pixels:
; x0*32 .. (x0 + w)*32 - 320, the same for y with 200).
ui_view_clamp:
        push bc
        ld  a, (map_scale)
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_playable_area
        add hl, de
        push hl
        pop ix
        ld  a, (ix + 0)
        ld  c, (ix + 4)
        ld  hl, view_x
        ld  de, 320
        call uvc_axis
        ld  a, (ix + 2)
        ld  c, (ix + 6)
        ld  hl, view_y
        ld  de, 200
        call uvc_axis
        pop bc
        ret

; HL -> the view word, A = the first square, C = the squares, DE = the
; screen's size in pixels: clamp.
uvc_axis:
        push hl
        ld  l, a
        ld  h, 0
        add a, c
        ld  b, a                ; the end square
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  (uvc_lo), hl        ; the lowest view
        ld  l, b
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        or  a
        sbc hl, de
        ld  (uvc_hi), hl        ; the highest view
        pop hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        push hl
        ex  de, hl              ; HL = the view
        ld  de, (uvc_lo)
        bit 7, h
        jr  nz, uvc_low
        or  a
        sbc hl, de
        add hl, de
        jr  nc, uvc_1
uvc_low:
        ex  de, hl
        jr  uvc_set
uvc_1:  ld  de, (uvc_hi)
        or  a
        sbc hl, de
        add hl, de
        jr  c, uvc_set
        ex  de, hl
uvc_set:
        ld  a, l
        and $F8
        ld  l, a
        ex  de, hl
        pop hl
        ld  (hl), d
        dec hl
        ld  (hl), e
        ret

; The square under the cursor -> HL ($FFC240).  The grid cursor's is the
; square nearest its top-left, the point + 16 ($006468).  Clobbers A, DE.
cursor_square:
        ld  hl, (cursor_y)
        ld  de, (view_y)
        add hl, de
        call csq_grid
        ld  a, l
        rla
        rl  h
        rla
        rl  h
        rla
        rl  h                   ; H = y >> 5, the row
        ld  a, h
        and $3F
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        push hl
        ld  hl, (cursor_x)
        ld  de, (view_x)
        add hl, de
        call csq_grid
        ld  a, l
        rla
        rl  h
        rla
        rl  h
        rla
        rl  h
        ld  a, h
        and $3F
        pop hl
        or  l
        ld  l, a
        ret
csq_grid:
        ld  a, (cursor_grid)
        or  a
        ret z
        ld  de, 16
        add hl, de
        ret

; ---------------------------------------------------------------- A and B

; A: with one of the player's units selected, an order for it by what is
; under the cursor (ui_battle_button $027F18-$02813E, then the target
; click ui_viewport_click $00E260); otherwise select what is there.
ui_press_a:
        call cursor_square
        ld  (ua_sq), hl
        ld  a, (place_active)
        or  a
        jp  nz, ua_place
        ; the Palace's weapon armed: A on another square fires it
        ld  a, (special_armed)
        or  a
        jr  z, uapa_1
        call ua_palace_ready
        jp  nz, ua_fire_special
        xor a
        ld  (special_armed), a
uapa_1:
        ld  a, (unit_selected)
        cp  $FF
        jr  z, ua_select
        call unit_ptr
        push hl
        pop ix
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, ua_select
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  z, ua_select
        jp  ua_order

; Select the unit or structure under the cursor ($027B4C...).
ua_select:
        ld  hl, (ua_sq)
        FCALL map_unit_at
        jr  z, ua_sel_struct
        push hl
        pop ix
        ld  a, (ix + O_INDEX)
        ld  (unit_selected), a
        ld  a, $FF
        ld  (struct_selected), a
        call usp_pb_hide        ; the lower picture and bar go ($02829E)
        ld  a, 38               ; the click
        FCALL snd_effect
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        ; the acknowledgement: 17 a foot soldier, 15 anything else
        call ua_is_foot
        ld  a, 17
        jr  z, ua_ack
        ld  a, 15
ua_ack: FCALL snd_effect
        ret
ua_sel_struct:
        ld  hl, (ua_sq)
        FCALL map_object_at
        ret z
        push hl
        pop ix
        ld  a, (ix + O_INDEX)
        ld  b, a
        ld  a, (struct_selected)
        cp  b
        jr  z, ua_panel
        ld  a, b
        ld  (struct_selected), a
        ld  (struct_last), a
        ld  a, (player_house)   ; the player's: B comes back to it ($027C88)
        cp  (ix + O_HOUSE)
        jr  nz, uss_1
        ld  a, b
        ld  (struct_last_own), a
uss_1:  ld  a, $FF
        ld  (unit_selected), a
        ld  a, 38
        FCALL snd_effect
        ret
ua_panel:
        ; A on the selected structure again.  The player's Palace with its
        ; weapon ready arms it ($027D10); anything else opens its panel
        ; (ui_structure_menu $028F38, bank PANEL).
        call ua_palace_ready
        jr  z, uap_menu
        ld  a, 1
        ld  (special_armed), a
        FCALL struct_marker_clear       ; its 'OK' goes (A = 1, $027D2E)
        ret
uap_menu:
        ld  a, (struct_selected)
        FCALL panel_structure
        call ui_time_resync     ; ($0289F6, $028D5E)
        FCALL render_invalidate
        ret

; -> IX = the selected structure and NZ if it is the player's Palace with
; its weapon ready: flags2 bit 7, countDown 0, flags2 bit 8 clear.
ua_palace_ready:
        ld  a, (struct_selected)
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        jr  nz, upr_no
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, upr_no
        bit 7, (ix + O_FLAGS2)
        jr  z, upr_no
        bit 0, (ix + O_FLAGS2 + 1)
        jr  nz, upr_no
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        jr  nz, upr_no
        or  1
        ret
upr_no: xor a
        ret

; A on a square with the Palace's weapon armed ($027E66): fire it there.
ua_fire_special:
        ld  hl, (ua_sq)
        ld  (special_target_square), hl
        push ix
        FCALL struct_activate_special
        pop ix
        ld  a, (ix + O_HOUSE)
        or  a
        jr  nz, ufs_1           ; the Harkonnen's Death Hand flies now
        ld  hl, (ua_sq)
        FCALL unit_launch_house_missile
ufs_1:  xor a
        ld  (special_armed), a
        ld  hl, 0
        ld  (special_target_square), hl
        ret

; IX = a unit -> Z if it moves on foot.
ua_is_foot:
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        or  a
        ret

; IX = the player's selected unit: an order from the square under the
; cursor.  The Mega Drive then drops the selection ($00E3EA).
ua_order:
        ld  hl, (ua_sq)
        push hl
        call map_landscape
        ld  (ua_land), a
        pop hl
        ; the unit there (not the player's own, which counts as ground; nor
        ; one the fog hides, map_square_pattern $027F00)
        push hl
        call ua_square_seen
        jr  z, uao_nounit
        FCALL map_unit_at
        jr  z, uao_nounit
        push hl
        pop iy
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  z, uao_nounit
        ld  (ua_unit), hl
        jr  uao_1
uao_nounit:
        ld  hl, 0
        ld  (ua_unit), hl
uao_1:  pop hl
        ; the structure there
        push hl
        call map_flags_ui
        bit MF_STRUCT, a
        pop hl
        ld  de, 0
        jr  z, uao_2
        FCALL map_object_at
        ex  de, hl
uao_2:  ld  (ua_struct), de
        ; by type
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, uao_notharv
        ld  a, (ua_land)
        cp  8
        jr  z, uao_harvest
        cp  9
        jr  nz, uao_move
uao_harvest:
        res 5, (ix + O_FLAGS2)  ; noSpiceFound
        ld  a, ORDER_HARVEST
        jp  ua_give
uao_notharv:
        cp  UNIT_MCV
        jr  nz, uao_other
        ; the MCV on itself deploys: MOVE2's unit_fx_order starts (or
        ; stops) its deploy animation and makes the order Stop ($027F8E)
        ld  hl, (ua_sq)
        push ix
        pop de
        call ua_on_self
        jr  nz, uao_move
        ld  a, ORDER_DEPLOY
        jp  ua_give
uao_other:
        ; on itself: Guard
        ld  hl, (ua_sq)
        push ix
        pop de
        call ua_on_self
        ld  a, ORDER_GUARD
        jp  z, ua_give
        ; no unit and no structure to aim at: the ground's click ($028134)
        ld  hl, (ua_unit)
        ld  de, (ua_struct)
        ld  a, h
        or  l
        or  d
        or  e
        jr  nz, uao_o1
        ld  a, $24
        FCALL snd_effect
uao_o1: ; an enemy unit or structure, a bloom, a wall: Attack
        ld  hl, (ua_unit)
        ld  a, h
        or  l
        jr  nz, uao_attack
        ld  a, (ua_land)
        cp  14
        jr  z, uao_bloom
        cp  11
        jr  z, uao_attack
        ld  hl, (ua_struct)
        ld  a, h
        or  l
        jr  z, uao_move
        push hl
        pop iy
        ld  a, (player_house)
        cp  (iy + O_HOUSE)
        jr  nz, uao_attack
        ; its own structure: into it if it may enter, else Move there
uao_move:
        ld  a, ORDER_MOVE
        jr  ua_give
uao_bloom:
        set 5, (ix + O_FLAGS2)  ; fire once, then Guard
uao_attack:
        ld  a, ORDER_ATTACK
        ; fall through

; A = the order for IX on ua_sq (the target click, $00E2B0-$00E3CE).
ua_give:
        ; the effect animations the order starts or stops - the target's
        ; flash, the MCV's deploy, the Devastator's self-destruct (MOVE2)
        ld  hl, (ua_unit)
        ld  de, (ua_struct)
        FCALL unit_fx_order
        ld  (ua_ord), a
        ; not a Harvester: its target goes; everything's move target and
        ; route go
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, uag_1
        ld  (ix + U_TARGETATTACK), 0
        ld  (ix + U_TARGETATTACK + 1), 0
uag_1:  ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
        ld  (ix + U_ROUTE), $FF
        ; the reference: the square for Move and Harvest, and for a wall
        ; or structure square; else what stands there (a unit)
        ld  a, (ua_ord)
        cp  ORDER_MOVE
        jr  z, uag_sq
        cp  ORDER_HARVEST
        jr  z, uag_sq
        ld  a, (ua_land)
        cp  11
        jr  nc, uag_sq
        ld  hl, (ua_unit)
        ld  a, h
        or  l
        jr  z, uag_sq
        push hl
        pop iy
        ld  l, (iy + O_INDEX)
        ld  h, REF_UNIT >> 8
        jr  uag_ref
uag_sq: ld  hl, (ua_sq)
        call ref_make_square
uag_ref:
        ld  (ua_ref), hl
        ld  a, (ua_ord)
        FCALL unit_give_order
        ld  a, (ua_ord)
        ld  hl, (ua_ref)
        cp  ORDER_MOVE
        jr  nz, uag_2
        FCALL unit_set_destination
        jr  uag_done
uag_2:  cp  ORDER_HARVEST
        jr  nz, uag_3
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        jr  uag_done
uag_3:  cp  ORDER_DEPLOY
        jr  z, uag_done
        cp  ORDER_GUARD
        jr  z, uag_done
        FCALL unit_set_target
uag_done:
        ; the acknowledgement: 16 a foot soldier, 18 anything else
        call ua_is_foot
        ld  a, 16
        jr  z, uag_ack
        ld  a, 18
uag_ack:
        FCALL snd_effect
        ld  a, $FF
        ld  (unit_selected), a
        ret

; HL = a unit or 0 -> Z if it is IX.
ua_self:
        push ix
        pop de
        or  a
        sbc hl, de
        ret
; HL = a square, DE = a unit -> Z if the unit stands on that square.
ua_on_self:
        push hl
        ex  de, hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        pop de
        or  a
        sbc hl, de
        ret

map_flags_ui:
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        ret

; map_square_pattern ($004590): HL = a square -> Z if what stands there is
; hidden: its overlay is one of the 16 fog icons up to the full fog
; ($FFC224, VEILED) and the cartridge's pattern ($0045CC) says 0 for it.
; Any other overlay: NZ.  Keeps HL.  Clobbers A, DE.
ua_square_seen:
        push hl
        call map_overlay_icon
        sub VEILED - 15
        jr  c, uqs_yes
        cp  16
        jr  nc, uqs_yes
        ld  e, a
        ld  d, 0
        ld  hl, uqs_pattern
        add hl, de
        ld  a, (hl)
        pop hl
        or  a
        ret
uqs_yes:
        pop hl
        or  1
        ret
uqs_pattern:
        DB  0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0

; ----------------------------------------------------- placing a building
;
; With the player's Construction Yard selected and the building it made
; waiting (flags2 bit 13), the cursor shows the building's squares, and A
; puts it down (ui_battle_button $027D84, ui_viewport_click $00E3F4).

; -> IX = the selected structure if it is the player's Yard with a building
; waiting (NZ), else Z.
ui_place_yard:
        ld  a, (struct_selected)
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, upy_no
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, upy_no
        bit 5, (ix + O_FLAGS2 + 1)      ; flags2 bit 13
        ret
upy_no: xor a
        ret

; Every pass, after the cursor has moved: whether the footprint fits, when
; the square under the cursor changes (ui_place_mode has set place_active
; and the size).
ui_place_update:
        ld  a, (place_active)
        or  a
        jr  z, upu_set
        call ui_place_yard
        ld  a, 0
        jr  z, upu_set
        ld  a, (ix + S_OBJECTTYPE)
        ld  (upu_type), a
        call cursor_square
        ld  de, (place_sq)
        or  a
        sbc hl, de
        add hl, de
        jr  z, upu_same
        ld  (place_sq), hl
        ld  a, (upu_type)
        push ix
        FCALL struct_check_location
        pop ix
        ld  a, h
        or  l
        jr  z, upu_fit
        ld  a, 1
upu_fit:
        ld  (place_fits), a
upu_same:
        ld  a, 1
upu_set:
        ld  (place_active), a
        or  a
        ret nz
        ld  hl, $FFFF           ; look again when it comes back
        ld  (place_sq), hl
        ret

; A in placing mode.
ua_place:
        call ui_place_yard
        ret z
        ld  (upl_yard), ix
        ld  a, (ix + S_OBJECTTYPE)
        ld  (upl_type), a
        ld  hl, (ua_sq)
        push ix
        FCALL struct_check_location
        pop ix
        ld  a, h
        or  l
        jr  nz, upl_ok
        ld  a, $2F              ; it does not fit
        FCALL snd_effect
        ret
upl_ok:
        ; the building leaves the Yard
        ld  a, (ix + O_LINKED)
        ld  (upl_slot), a
        ld  (ix + O_LINKED), $FF
        res 6, (ix + O_FLAGS2)
        ld  a, $14
        FCALL snd_effect
        ld  a, (upl_slot)
        call struct_ptr
        push hl
        pop ix
        ld  (upl_built), ix
        FCALL struct_upgrade_by_mission
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  z, upl_1
        cp  STRUCT_PALACE
        jr  nz, upl_2
upl_1:  ld  iy, (upl_yard)
        ld  (iy + S_OBJECTTYPE), 1
        ld  (iy + S_OBJECTTYPE + 1), 0
upl_2:  ld  ix, (upl_built)
        ld  hl, (ua_sq)
        FCALL struct_place
        ret z
        ; struct_selected_clear_bits: the Yard's flags2 bits 13 and 14
        ld  iy, (upl_yard)
        ld  a, (iy + O_FLAGS2 + 1)
        and ~$60
        ld  (iy + O_FLAGS2 + 1), a
        ld  ix, (upl_built)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        jr  nz, upl_3
        ; the house's Palace is here now
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_PALACE_Y
        add hl, de
        ld  a, (ix + O_POS_Y)
        ld  (hl), a
        inc hl
        ld  a, (ix + O_POS_Y + 1)
        ld  (hl), a
        inc hl
        ld  a, (ix + O_POS_X)
        ld  (hl), a
        inc hl
        ld  a, (ix + O_POS_X + 1)
        ld  (hl), a
upl_3:  ; the player's first Refinery sends a Harvester in a Carryall
        ld  a, (upl_type)
        cp  STRUCT_REFINERY
        jr  nz, upl_4
        ld  a, (validate_strict)
        or  a
        jr  nz, upl_4
        inc a
        ld  (validate_strict), a
        ld  hl, (ua_sq)
        ld  de, 65              ; a square in from its corner
        add hl, de
        call ref_make_square
        ld  a, (player_house)
        ld  b, a
        ld  a, UNIT_HARVESTER
        FCALL unit_deliver
        push af
        xor a
        ld  (validate_strict), a
        pop af
        jr  z, upl_4
        push hl
        pop iy
        ld  ix, (upl_built)
        ld  l, (ix + O_INDEX)
        ld  h, REF_STRUCT >> 8
        ld  (iy + U_ORIGIN), l
        ld  (iy + U_ORIGIN + 1), h
upl_4:  ; the Yard offers its first item again if what it had is gone
        ld  ix, (upl_yard)
        FCALL struct_get_buildable      ; DE:HL
        ld  a, (ix + S_OBJECTTYPE)
        call upl_bit
        jr  nz, upl_5
        ld  hl, -2
        FCALL struct_build_object
upl_5:  xor a
        ld  (place_active), a
        ld  a, (player_house)
        FCALL radar_update_state
        ret

; DE:HL = a bit per type, A = a type -> NZ if its bit is set.
upl_bit:
        cp  16
        jr  c, upb_lo
        sub 16
        ex  de, hl
upb_lo: cp  8
        jr  c, upb_l
        sub 8
        ld  l, h
upb_l:  ld  b, a
        inc b
        ld  a, l
upb_s:  dec b
        jr  z, upb_t
        rrca
        jr  upb_s
upb_t:  and 1
        ret

upu_type:       DB 0
upl_type:       DB 0
upl_slot:       DB 0
upl_yard:       DW 0
upl_built:      DW 0

; ------------------------------------------------------------------- B
;
; ui_battle_button $02838E.  The cartridge keeps the structure pointer
; ($FFC578, struct_last here) while a unit is selected and only hides it
; (flags2 bit 15); struct_selected is the structure shown.
;
;   - A unit selected: one with a deploy or a self-destruct pending
;     (flags2 bit 7) has it hurried to its end and stays selected
;     ($0284F0-$028514: MOVE2's effect animations answer that first).
;     Otherwise it is dropped ($028518), and the structure selected before
;     it comes back if it is the player's, else the player's last one
;     (structureLastOwn $FFC57C).
;   - Another house's structure: the player's last one instead, with the
;     click ($0284CA).
;   - The player's Palace, weapon ready: disarmed ($0284C0).
;   - The player's Construction Yard, selected, its building finished:
;     dropped, and the placing with it ($02840A).
;   - The player's factory or Yard, selected and idle, not repairing nor
;     upgrading: it starts its item again (struct_build_object with its
;     objectType, flags2 bit 14, effect 13; $028462), refused (effect 47)
;     where the side panel shows its label: no room for what it makes
;     (flags2 bit 8, not for a Yard's 4-Slab or Wall), or a Hi-Tech with
;     no aircraft slot free ($029568-$02963C).  S10 calls this stopping
;     production; the machine starts it (and while it builds, B does
;     nothing).  The cartridge also sets $FFC030, a PC leftover nothing
;     shows, and puts up the label when refused; the port has neither.
ui_press_b:
        ; a selected unit's pending deploy or self-destruct happens now and
        ; it stays selected ($0284F0, MOVE2)
        ld  a, (unit_selected)
        FCALL unit_fx_press_b
        ret nz
        ld  a, (unit_selected)
        cp  $FF
        jr  z, upb_struct
        ld  a, $FF
        ld  (unit_selected), a
        call upb_last           ; IX = it, NZ the player's, Z none
        ret z
        jp  p, upb_show         ; (P: the player's)
        call upb_own            ; another's: the player's last one
        ret
upb_show:
        ld  a, (ix + O_INDEX)
        ld  (struct_selected), a
        ret

upb_struct:
        call upb_last
        ret z
        jp  p, upb_mine
        ; another house's
        call upb_own
        ret z
        ld  a, 38
        FCALL snd_effect
        ret
upb_mine:
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 1, (hl)             ; a factory
        jr  nz, upb_factory
        ld  a, (ix + O_TYPE)
        cp  STRUCT_PALACE
        ret nz
        bit 7, (ix + O_FLAGS2)
        ret z
        xor a
        ld  (special_armed), a
        ret
upb_factory:
        ld  a, (struct_selected) ; flags2 bit 15: only while it is shown
        cp  (ix + O_INDEX)
        ret nz
        ld  a, (ix + O_FLAGS2 + 1)
        and $60                 ; bits 13 (finished) and 14 (building)
        jr  z, upb_idle
        and $20
        ret z                   ; building: nothing
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ret nz
        ld  a, $FF
        ld  (struct_selected), a
        ld  (struct_last), a
        ret
upb_idle:
        bit OF_REPAIRING - 8, (ix + O_FLAGS + 1)
        ret nz
        bit 1, (ix + O_FLAGS2)  ; upgrading
        ret nz
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, upb_label
        ld  a, (ix + S_OBJECTTYPE)
        cp  STRUCT_SLAB4
        jr  z, upb_build
        cp  STRUCT_WALL
        jr  z, upb_build
upb_label:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  z, upb_hitech
        bit 0, (ix + O_FLAGS2 + 1)      ; flags2 bit 8: no room
        jr  nz, upb_refused
upb_hitech:
        cp  STRUCT_HITECH
        jr  nz, upb_build
        ld  a, (air_slot_free)
        or  a
        jr  z, upb_refused
upb_build:
        ld  l, (ix + S_OBJECTTYPE)
        ld  h, (ix + S_OBJECTTYPE + 1)
        push ix
        FCALL struct_build_object
        pop ix
        ld  a, h
        or  l
        jr  z, upb_refused
        set 6, (ix + O_FLAGS2 + 1)      ; flags2 bit 14: building
        ld  a, 13
        FCALL snd_effect
        ret
upb_refused:
        ld  a, $2F
        FCALL snd_effect
        ret

; struct_last -> IX = it; Z none (or no longer in use), else P the
; player's, M another house's.
upb_last:
        ld  a, (struct_last)
upb_slot:
        cp  $FF
        ret z
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        ret z
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, 1
        jr  z, upl_mine
        neg
upl_mine:
        or  a
        ret

; The player's last structure (struct_last_own) becomes the selection ->
; Z if there is none.  (The cartridge forgets it when it is destroyed;
; the port finds out here.)
upb_own:
        ld  a, (struct_last_own)
        call upb_slot
        jr  z, upo_none
        jp  m, upo_none
        ld  a, (ix + O_INDEX)
        ld  (struct_selected), a
        ld  (struct_last), a
        or  1
        ret
upo_none:
        ld  a, $FF
        ld  (struct_selected), a
        ld  (struct_last), a
        xor a
        ret

; ------------------------------------------------------ the view shake
;
; view_shake_start ($005DCC), from any bank (FCALL): A = frames.  The view
; shakes that long, unless C is held.  A Devastator's or a Destruct's blast
; shakes it 16 frames (UNIT 18, $0447D2), a structure's destruction 60
; (BUILD 22, $00D338).  The cartridge remembers where the view is, so a
; shake begun over another starts from the shaken place and the view does
; not quite come home; here the offsets start again from 0 and it does.
; Keeps everything but A and the flags.
view_shake_start:
        push hl
        ld  l, a
        ld  a, (pad_held)
        bit PAD_C, a
        jr  nz, vss_c
        ld  h, 0
        ld  (shake_frames), hl
        xor a
        ld  (shake_ox), a
        ld  (shake_oy), a
        inc a
        ld  (shake_on), a
vss_c:  pop hl
        ret

; view_shake_frame ($005E26), every pass: for each frame of it a step of
; the cartridge's walk (two of the game's random numbers a frame, as the
; cartridge draws them); at the end, or with C held, back.  -> NZ while it
; shakes and on the pass it stops: the frame hook reads no pad then.  The
; port cannot move the view by a pixel, so the renderer draws one of its
; two screens a cell away along the walk's first way (render.asm).
view_shake_frame:
        ld  a, (shake_on)
        or  a
        ret z
        ld  a, (pad_held)
        bit PAD_C, a
        jr  nz, vsf_end
        ld  a, (ubi_frames)
        ld  b, a
vsf_frame:
        ld  hl, (shake_frames)
        ld  a, h
        or  l
        jr  z, vsf_end
        bit 7, h
        jr  nz, vsf_end
        dec hl
        ld  (shake_frames), hl
        ld  hl, shake_ox
        call vsf_step
        ld  hl, shake_oy
        call vsf_step
        djnz vsf_frame
        or  1
        ret
vsf_end:
        xor a
        ld  (shake_on), a
        ld  (shake_ox), a
        ld  (shake_oy), a
        ld  h, a
        ld  l, a
        ld  (shake_frames), hl
        or  1
        ret

; HL -> an offset (signed byte).  r = rand_between(0, 4); where o + r - 2
; stays within 4 of 0 the offset goes on by r, else back by r: the
; cartridge tests with r - 2 and moves by r, so it wanders over -1..6.
vsf_step:
        ld  de, $0004           ; math_rand_between(0, 4)
        call rand_between
        ld  c, a
        add a, (hl)
        add a, 2                ; o + r - 2, + 4
        cp  9
        ld  a, (hl)
        jr  nc, vsf_back
        add a, c
        ld  (hl), a
        ret
vsf_back:
        sub c
        ld  (hl), a
        ret

; ------------------------------------------------------ a mission's start
;
; ui_battle_start: after the mission is loaded (main.asm start_mission).
; The free cursor; no shake; the warning as ui_sidebar_sprites_init
; ($009BDA) leaves it - out, and not armed until the credits have once
; been 50 or more; no structure selected, and B's way back is the player's
; Construction Yard (scen_read_structure $016938: the last one read); the
; side panel's lower half empty (ui_sidebar_pictures_init $009C2A).
ui_battle_start:
        call usp_none           ; the side panel's lower half: nothing
        xor a
        ld  (cursor_grid), a
        ld  (cursor_dirs), a
        ld  (shake_on), a
        ld  (shake_ox), a
        ld  (shake_oy), a
        ld  (warn_armed), a
        ld  (warn_shown), a
        ld  (warn_blink), a
        ld  (crd_low), a
        ld  h, a
        ld  l, a
        ld  (shake_frames), hl
        dec hl
        ld  (warn_t1), hl
        ld  (warn_t2), hl
        ld  a, $FF
        ld  (struct_last), a
        ld  (struct_last_own), a
        ld  a, (struct_find_count)
        or  a
        ret z
        ld  b, a
        ld  hl, struct_find
ubs_1:  push bc
        push hl
        ld  a, (hl)
        ld  c, a
        call struct_ptr
        push hl
        pop ix
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, ubs_2
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, ubs_2
        ld  a, c
        ld  (struct_last_own), a
ubs_2:  pop hl
        inc hl
        pop bc
        djnz ubs_1
        ret

; ------------------------------------------------ the bank's own state
cursor_grid:    DB 0            ; 1: the grid cursor's hook ($00608E) is in
cursor_dirs:    DB 0            ; $FFBF48 the directions the cursor last went
ubg_carry:      DB 0            ; how far a carried axis may go this pass
ubg_xmax:       DW 0            ; the grid cursor's limits ($0C7EA0)
ubg_ymax:       DW 0
ubg_yedge:      DW 0            ; where the view follows a footprint down
struct_last:    DB $FF          ; $FFC578 itself: kept while a unit is selected
struct_last_own: DB $FF         ; $FFC57C structureLastOwn
shake_frames:   DW 0            ; $FFBEA8 the shake's frames left
warn_armed:     DB 0            ; the warning sprite's +7 bit 0
warn_shown:     DB 0            ; ... not hidden (its bit 7 clear)
warn_blink:     DB 0            ; ... its blink counter (+4)
warn_t1:        DW $FFFF        ; $FFC864 the time it stays on
warn_t2:        DW $FFFF        ; $FFC866 the time it stays off
; ------------------------------------------------ the bank's own scratch
ubi_frames:     DB 0
ubi_step:       DB 0
UBV_SLOW        EQU 60
ubv_slow:       DB UBV_SLOW     ; C held: the frames of 7 pixels left
ubv_frac:       DB 0, 0         ; the view's part cells across and down
ubi_pressed:    DB 0
uvc_lo:         DW 0
uvc_hi:         DW 0
ua_sq:          DW 0
ua_land:        DB 0
ua_unit:        DW 0
ua_struct:      DW 0
ua_ord:         DB 0
ua_ref:         DW 0

; ---------------------------------------------------- the credits counter
;
; ui_draw_credits ($011F34, PC GUI_DrawCredits), every pass: A = the mode
; (0 normal, 1 force, 2 reset, 3 redraw).  Rolls crd_value towards the
; player's credits by an eighth of an accumulated step each GUI tick, the
; step a quarter of the gap (a word, at least 1, at most 128 either way);
; credits_shown, which the quota is tested against, follows it.  The
; renderer draws crd_digits.
;
; The cartridge calls it once a battle pass ($01268C) and steps at most
; once a GUI tick - which is once a frame there, where a pass is a frame.
; A pass here is nearer two, so in mode 0 it takes one step for every
; tick gone by since the last, up to UDC_CATCHUP (a longer pause drops the
; rest), and the counter rolls at the Mega Drive's speed.  The low-credits
; warning is looked at once a call: its timers run by frames_this_pass.
UDC_CATCHUP     EQU 4

ui_draw_credits:
        ld  (udc_mode), a
        call uwb_frame          ; the warning's blink, every frame
        xor a
        ld  (udc_rep), a
        ld  b, UDC_CATCHUP
udc_loop:
        push bc
        call udc_body
        pop bc
        ld  a, (udc_mode)
        or  a
        ret nz                  ; the forced modes step once
        ld  a, 1
        ld  (udc_rep), a
        push bc
        ld  hl, timer_gui
        ld  de, crd_tick
        call cmp32              ; timer - tick: carry once caught up
        pop bc
        ret c
        djnz udc_loop
        ld  hl, (timer_gui)     ; still behind: the rest go
        ld  de, (timer_gui + 2)
        ld  bc, 1
        add hl, bc
        jr  nc, udc_l1
        inc de
udc_l1: ld  (crd_tick), hl
        ld  (crd_tick + 2), de
        ret

; One step (the cartridge's whole routine, less the call's own set-up).
udc_body:
        ; at most once a GUI tick unless the mode says otherwise
        ld  a, (udc_mode)
        or  a
        jr  nz, udc_go
        ld  hl, timer_gui
        ld  de, crd_tick
        call cmp32              ; timer - tick
        ret c
udc_go:
        ; the next tick due: the one after this in mode 0 (so ticks gone by
        ; are stepped in turn), the one after now otherwise
        ld  hl, (crd_tick)
        ld  de, (crd_tick + 2)
        ld  a, (udc_mode)
        or  a
        jr  z, udc_t0
        ld  hl, (timer_gui)
        ld  de, (timer_gui + 2)
udc_t0: ld  bc, 1
        add hl, bc
        jr  nc, udc_t
        inc de
udc_t:  ld  (crd_tick), hl
        ld  (crd_tick + 2), de
        ; the player's credits -> udc_cred
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        ld  (udc_cp), hl
        ld  de, udc_cred
        ld  bc, 4
        ldir
        ; the warning ($011F72): shown < 50 and settled - 1; shown >= 50 - 0;
        ; still rolling under 50 - not called.  Once a call.
        ld  a, (udc_rep)
        or  a
        jr  nz, udc_w9
        ld  hl, (credits_shown + 2)
        ld  a, h
        or  l
        jr  nz, udc_w0
        ld  hl, (credits_shown)
        ld  de, 50
        or  a
        sbc hl, de
        jr  nc, udc_w0
        ld  hl, credits_shown
        ld  de, udc_cred
        call cmp32
        jr  nz, udc_w9
        ld  a, 1
        jr  udc_w
udc_w0: xor a
udc_w:  call ui_warning_blink
udc_w9:
        ld  hl, credits_shown
        ld  de, udc_cred
        call cmp32
        ret z
        ld  a, (udc_mode)
        cp  2
        jr  nz, udc_m3
        ld  hl, udc_cred
        ld  de, credits_shown
        ld  bc, 4
        ldir
        ld  hl, 0
        ld  (crd_value), hl
        ld  (crd_value + 2), hl
udc_m3: ld  a, (udc_mode)
        cp  3
        jr  nz, udc_m0
        ld  hl, credits_shown
        ld  de, crd_value
        ld  bc, 4
        ldir
        ld  hl, crd_value
        ld  de, crd_digits
        ld  bc, 4
        ldir
        jp  udc_text
udc_m0: ld  a, (udc_mode)
        or  a
        jr  nz, udc_diff
        ld  hl, crd_value
        ld  de, udc_cred
        call cmp32
        ret z
udc_diff:
        ; d3 = the low word of credits - value
        ld  hl, (udc_cred)
        ld  de, (crd_value)
        or  a
        sbc hl, de
        ld  a, h
        or  l
        jr  z, udc_nostep
        sra h
        rr  l
        sra h
        rr  l
        ld  a, h
        or  l
        jr  nz, udc_d1
        ld  l, 1
udc_d1: ; clamp to -128..128
        bit 7, h
        jr  nz, udc_dneg
        ld  de, 129
        push hl
        or  a
        sbc hl, de
        pop hl
        jr  c, udc_dset
        ld  hl, 128
        jr  udc_dset
udc_dneg:
        ld  de, -128
        push hl
        or  a
        sbc hl, de              ; d3 - (-128): carry if d3 < -128
        pop hl
        jr  nc, udc_dset
        ex  de, hl
udc_dset:
        ld  (udc_d3), hl
        ; step += d3, sign-extended
        ld  a, h
        rla
        sbc a, a
        ld  e, a
        ld  d, a
        ld  bc, (crd_step)
        add hl, bc
        ld  (crd_step), hl
        ld  hl, (crd_step + 2)
        adc hl, de
        ld  (crd_step + 2), hl
        jr  udc_stepped
udc_nostep:
        ld  (udc_d3), hl        ; 0
        ld  (crd_step), hl
        ld  (crd_step + 2), hl
udc_stepped:
        ; a negative step with nothing left to take goes
        ld  a, (crd_step + 3)
        bit 7, a
        jr  z, udc_s1
        ld  hl, (crd_value)
        ld  de, (crd_value + 2)
        ld  a, h
        or  l
        or  d
        or  e
        jr  nz, udc_s1
        ld  (crd_step), hl
        ld  (crd_step + 2), hl
udc_s1:
        ; value += step >> 3 (arithmetic), + 1 if the step is negative
        ld  hl, (crd_step)
        ld  de, (crd_step + 2)
        ld  b, 3
udc_sh: sra d
        rr  e
        rr  h
        rr  l
        djnz udc_sh
        ld  a, (crd_step + 3)
        bit 7, a
        jr  z, udc_s2
        ld  bc, 1
        add hl, bc
        jr  nc, udc_s2
        inc de
udc_s2: ld  bc, (crd_value)
        add hl, bc
        ld  (crd_value), hl
        ex  de, hl
        ld  bc, (crd_value + 2)
        adc hl, bc
        ld  (crd_value + 2), hl
        ; the step keeps its remainder: & 7 if positive, | $FFF8 if negative
        ld  a, (crd_step + 3)
        bit 7, a
        jr  nz, udc_rneg
        ld  hl, (crd_step)
        ld  de, (crd_step + 2)
        ld  a, h
        or  l
        or  d
        or  e
        jr  z, udc_r9
        ld  a, (crd_step)
        and 7
        ld  l, a
        ld  h, 0
        ld  (crd_step), hl
        ld  l, h
        ld  (crd_step + 2), hl
        jr  udc_r9
udc_rneg:
        ld  a, (crd_step)
        or  $F8
        ld  (crd_step), a
        ld  a, $FF
        ld  (crd_step + 1), a
udc_r9:
        ; a negative value is 0 (and credits past 100000000 go)
        ld  a, (crd_value + 3)
        bit 7, a
        jr  z, udc_v
        ld  hl, 0
        ld  (crd_value), hl
        ld  (crd_value + 2), hl
        ld  hl, udc_cred
        ld  de, udc_limit
        call cmp32              ; credits - 100000000
        jr  c, udc_v
        jr  z, udc_v
        ld  hl, (udc_cp)
        xor a
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
udc_v:
        ; shown = value (or value - 1, not below 0, while falling); the
        ; digits = value (+ 1 while rising)
        ld  hl, crd_value
        ld  de, credits_shown
        ld  bc, 4
        ldir
        ld  hl, crd_value
        ld  de, crd_digits
        ld  bc, 4
        ldir
        ld  a, (crd_step + 3)
        bit 7, a
        jr  z, udc_up
        ld  hl, credits_shown
        call dec32_floor
        jr  udc_snd
udc_up: ld  hl, (crd_step)
        ld  de, (crd_step + 2)
        ld  a, h
        or  l
        or  d
        or  e
        jr  z, udc_snd
        ld  hl, crd_digits
        call inc32
udc_snd:
        ; every fourth step a click: $34 up, $35 down
        ld  a, (crd_count)
        and 3
        jr  nz, udc_cnt
        ld  hl, (udc_d3)
        bit 7, h
        ld  a, $35
        jr  nz, udc_eff
        ld  a, h
        or  l
        ld  a, $35
        jr  z, udc_eff
        ld  a, $34
udc_eff:
        FCALL snd_effect
udc_cnt:
        ld  hl, (crd_count)
        inc hl
        ld  (crd_count), hl
        ; fall through

; crd_digits -> crd_text, "%6d" (at most 999999 shown).
udc_text:
        ld  hl, (crd_digits)
        ld  de, (crd_digits + 2)
        ; above 999999: 999999
        ld  a, d
        or  a
        jr  nz, udt_max
        ld  a, e
        cp  $0F
        jr  c, udt_ok
        jr  nz, udt_max
        ld  a, h
        cp  $42
        jr  c, udt_ok
        jr  nz, udt_max
        ld  a, l
        cp  $40
        jr  c, udt_ok
udt_max:
        ld  hl, 999999 & $FFFF
        ld  e, 999999 >> 16
udt_ok: ; E:HL, repeated subtraction of each power of ten
        ld  ix, udt_pow
        ld  iy, crd_text
        ld  b, 6
        ld  c, 0                ; a digit printed yet
udt_dig:
        xor a
udt_sub:
        push af
        ld  a, l
        sub (ix + 0)
        ld  l, a
        ld  a, h
        sbc a, (ix + 1)
        ld  h, a
        ld  a, e
        sbc a, (ix + 2)
        ld  e, a
        jr  c, udt_back
        pop af
        inc a
        jr  udt_sub
udt_back:
        ld  a, l
        add a, (ix + 0)
        ld  l, a
        ld  a, h
        adc a, (ix + 1)
        ld  h, a
        ld  a, e
        adc a, (ix + 2)
        ld  e, a
        pop af
        or  a
        jr  nz, udt_put
        cp  c                   ; 0: a leading zero unless one was printed
        jr  nz, udt_put
        ld  a, b
        dec a
        ld  a, 0
        jr  z, udt_put          ; the last digit always shows
        ld  a, $FF
        jr  udt_put2
udt_put:
        ld  c, 1
udt_put2:
        ld  (iy + 0), a
        inc iy
        inc ix
        inc ix
        inc ix
        djnz udt_dig
        ret

udt_pow:
        DB  100000 & $FF, (100000 >> 8) & $FF, 100000 >> 16
        DB  10000 & $FF, 10000 >> 8, 0
        DB  1000 & $FF, 1000 >> 8, 0
        DB  100, 0, 0
        DB  10, 0, 0
        DB  1, 0, 0

; HL, DE -> two unsigned longs: flags of (HL) - (DE) (C below, Z equal).
cmp32:
        push bc
        ld  b, 4
        inc hl
        inc hl
        inc hl
        inc de
        inc de
        inc de
c32_l:  ld  a, (de)
        ld  c, a
        ld  a, (hl)
        cp  c
        jr  nz, c32_x
        dec hl
        dec de
        djnz c32_l
c32_x:  pop bc
        ret

; HL -> a long: + 1.
inc32:
        ld  b, 4
i32_l:  inc (hl)
        ret nz
        inc hl
        djnz i32_l
        ret

; HL -> a long: - 1, but not below 0.
dec32_floor:
        push hl
        ld  a, (hl)
        inc hl
        or  (hl)
        inc hl
        or  (hl)
        inc hl
        or  (hl)
        pop hl
        ret z
        ld  b, 4
d32_l:  ld  a, (hl)
        dec (hl)
        or  a
        ret nz
        inc hl
        djnz d32_l
        ret

udc_mode:       DB 0
udc_rep:        DB 0            ; 1 on a catch-up step: the warning is not looked at again
udc_cp:         DW 0
udc_cred:       DD 0
udc_d3:         DW 0
udc_limit:      DD 100000000

; ------------------------------------------------ the low-credits warning
;
; ui_warning_blink ($0099A8): A = 1 while the warning applies (the credits
; shown under 50 and settled), 0 when they are 50 or more.  With 0 it goes
; out and is armed: next time it applies it comes on for 90 frames, then
; off for 900, on for 60, off for 900, on for 60... (timers $FFC864 and
; $FFC866, less the frames of the pass).  With 1 and not armed it does
; nothing - so a mission begun under 50 credits (ui_sidebar_sprites_init
; $009BDA leaves it unarmed) says nothing until they have been 50 once.
; The picture is CREDITS LOW, 88 x 8 at (112, 112) (render.asm).
ui_warning_blink:
        or  a
        jr  nz, uwb_on
        ld  hl, 90
        ld  (warn_t1), hl
        ld  hl, 0
        ld  (warn_t2), hl
        ld  (warn_shown), a
        inc a
        ld  (warn_armed), a
        ret
uwb_on: ld  a, (warn_armed)
        or  a
        ret z
        ld  de, (frames_this_pass)
        ld  hl, (warn_t2)
        bit 7, h
        jr  nz, uwb_1
        or  a                   ; off: its time runs
        sbc hl, de
        ld  (warn_t2), hl
        ret
uwb_1:  ld  hl, (warn_t1)       ; on: its time runs
        or  a
        sbc hl, de
        ld  (warn_t1), hl
        ld  a, 1
        bit 7, h
        jr  z, uwb_2
        ld  hl, 900             ; then off for 900, and on for 60 after
        ld  (warn_t2), hl
        ld  hl, 60
        ld  (warn_t1), hl
        xor a
uwb_2:  ld  (warn_shown), a
        ret

; Every pass: the sprite blinks at speed 8 while it is on (spr_blink_on
; $0013B8, spr_render $0010D8): a frame with its counter at 0 leaves it
; out and sets the counter to 8, every other frame counts down and draws
; it.  crd_low = whether the pass's last frame draws it.
uwb_frame:
        ld  a, (warn_shown)
        or  a
        jr  z, uwf_set
        ld  hl, (frames_this_pass)
        ld  a, h
        or  a
        ld  a, 18               ; a long pass is cut to two turns: its
        jr  nz, uwf_1           ; phase may slip, which nobody sees
        ld  a, l
        or  a
        jr  nz, uwf_0
        inc a
uwf_0:  cp  18
        jr  c, uwf_1
        ld  a, 18
uwf_1:  ld  b, a
        ld  hl, warn_blink
uwf_l:  ld  a, (hl)
        or  a
        jr  z, uwf_skip
        dec (hl)
        ld  a, 1
        jr  uwf_n
uwf_skip:
        ld  (hl), 8
        xor a
uwf_n:  djnz uwf_l
uwf_set:
        ld  (crd_low), a
        ret

; ------------------------------------------ the side panel's lower half
;
; ui_selection_panel: ui_draw_selection_panel ($0294BE), at the end of
; every input step, where battle_input_poll calls it ($004CAE).  The upper
; half - the portrait and the health bar - the renderer works out for
; itself (render.asm rph_panel); this decides the rest, as sprite frames
; in WORLD that rph_panel draws after them:
;
;   panel_pic2   the lower picture at (272, 88): what a factory makes
;                (+$52), the spanner while upgrading (anim $40), the
;                Repair Facility's unit, the Palace's weapon - the Fremen
;                for the Atreides (anim $5E), else +$52's portrait
;   panel_bar2   the second bar, at panel_bar2_y: production, the upgrade,
;                the repair and the Palace's charge at 112 in pen 7; the
;                Starport's delivery and a Windtrap's power use against
;                what is made at 80 in pen 7; a Refinery's or Silo's
;                credits against storage and a Harvester's load at 80 in
;                pen 3
;   panel_label  the no sign over the picture: a factory with no room
;                (flags2 bit 8; not a Yard making a 4-Slab or Wall), a
;                Hi-Tech with no aircraft slot, a Palace in its delay
;                (+$4E)
;
; Each is a sprite the cartridge shows, hides or leaves as it was, and a
; branch that leaves one alone leaves its variable alone: an upgrading
; structure with no room keeps its label, a factory whose +$52 is negative
; keeps the picture, a Harvester keeps it too (selecting a unit hid it,
; $02829E), a full value of 0 keeps the bar.  Another house's structure
; shows neither.  Two side effects are the cartridge's: a captured factory
; (+$4C not the player) takes +$52 from what it holds ($0295B4, $0295CE),
; and a production whose countdown has run out is finished - flags2 bit 14
; off, 13 on (ui_struct_action $012144, called at $0296CC).
ui_selection_panel:
        ld  a, (unit_selected)
        cp  $FF
        jp  nz, usp_unit
        ld  a, (struct_selected)
        cp  $FF
        jp  z, usp_none
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        jp  z, usp_none
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jp  nz, usp_none        ; another's ($0298EE)
        bit 1, (ix + O_FLAGS2)
        jr  z, usp_1
        ; upgrading: the spanner, and 100 - upgradeTimeLeft of 100
        ld  hl, HUD_STRUCT + 19 ; anim $40
        ld  (panel_pic2), hl
        ld  a, (ix + S_UPGRADETIME)
        neg
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        ld  de, 100
        add hl, de
        call usp_bar2_hi
        bit 0, (ix + O_FLAGS2 + 1)
        ret nz                  ; no room: the label as it was
        xor a
        ld  (panel_label), a
        ret
usp_1:  ; a captured structure (its creator +$4C not the player): what it
        ; makes is what it holds, or it holds nothing ($029568-$0295D4)
        ld  a, (ix + S_CREATORHOUSE + 1)
        or  a
        jr  nz, usp_cap
        ld  a, (player_house)
        cp  (ix + S_CREATORHOUSE)
        jr  z, usp_2
usp_cap:
        bit 7, (ix + O_LINKED)
        jr  nz, usp_cap_none
        call usp_makes
        jr  z, usp_cap_none
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, (ix + O_LINKED)
        jr  nz, usp_cap_u
        call struct_ptr
        jr  usp_cap_t
usp_cap_u:
        call unit_ptr
usp_cap_t:
        inc hl
        inc hl
        ld  a, (hl)             ; its type, a byte made a word
        ld  (ix + S_OBJECTTYPE), a
        rla
        sbc a, a
        ld  (ix + S_OBJECTTYPE + 1), a
        jr  usp_2
usp_cap_none:
        ld  (ix + O_LINKED), $FF
usp_2:  ; the label ($0295DA-$02963C)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, usp_3
        bit 0, (ix + O_FLAGS2 + 1)      ; flags2 bit 8: no room
        jr  z, usp_loff
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, usp_lon
        ld  a, (ix + S_OBJECTTYPE)
        cp  STRUCT_SLAB4
        jr  z, usp_loff
        cp  STRUCT_WALL
        jr  z, usp_loff
        jr  usp_lon
usp_3:  cp  STRUCT_STARPORT
        jr  z, usp_4
        bit 0, (ix + O_FLAGS2 + 1)
        jr  nz, usp_lon
usp_4:  cp  STRUCT_HITECH
        jr  nz, usp_loff
        ld  a, (air_slot_free)
        or  a
        jr  nz, usp_loff
usp_lon:
        ld  a, 1
        jr  usp_l
usp_loff:
        xor a
usp_l:  ld  (panel_label), a
        ; the rest by type ($029642)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jp  z, usp_starport
        call usp_makes
        jr  nz, usp_factory
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REPAIR
        jr  nz, usp_5
        bit 7, (ix + O_LINKED)
        jp  z, usp_repair
usp_5:  cp  STRUCT_PALACE
        jp  z, usp_palace
        ld  hl, $FFFF           ; no picture ($02981A)
        ld  (panel_pic2), hl
        cp  STRUCT_WINDTRAP
        jp  z, usp_windtrap
        cp  STRUCT_REFINERY
        jp  z, usp_spice
        cp  STRUCT_SILO
        jp  z, usp_spice
        jp  usp_bar2_hide

; A factory or the Yard ($02964C-$02972A): +$52's portrait, and while it
; builds (flags2 bit 14) buildTime - (countDown >> 8) of buildTime.
usp_factory:
        ld  l, (ix + S_OBJECTTYPE)
        ld  h, (ix + S_OBJECTTYPE + 1)
        bit 7, h
        jr  nz, usp_f1          ; negative: the picture as it was
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, l
        jr  nz, usp_f0
        call usp_pic_struct
        jr  usp_f1
usp_f0: call usp_pic_unit
usp_f1: bit 6, (ix + O_FLAGS2 + 1)
        jp  z, usp_bar2_hide
        call usp_action
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        ret nz                  ; (no type: the cartridge reads past its table)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, (ix + S_OBJECTTYPE)
        jr  nz, usp_f2
        cp  STRUCT_INFO_COUNT
        ret nc
        call struct_info
        ld  de, SI_buildTime
        jr  usp_f3
usp_f2: cp  UNIT_INFO_COUNT
        ret nc
        call unit_info
        ld  de, UI_buildTime
usp_f3: add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; DE = buildTime
        ld  l, (ix + S_COUNTDOWN + 1)
        ld  h, 0                ; countDown >> 8 (lsr.w)
        ex  de, hl
        push hl
        or  a
        sbc hl, de
        pop de
        jp  usp_bar2_hi

; ui_struct_action ($012144) as the panel calls it, on the structure
; itself: one making something, not on hold, its countdown run out, is
; finished - flags2 bit 14 off, bit 13 on.  (What it offers, $FFC030, a PC
; leftover, nothing shows.)
usp_action:
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret z
        bit OF_ONHOLD - 8, (ix + O_FLAGS + 1)
        ret nz
        ld  a, (ix + S_COUNTDOWN)
        or  (ix + S_COUNTDOWN + 1)
        ret nz
        res 6, (ix + O_FLAGS2 + 1)
        set 5, (ix + O_FLAGS2 + 1)
        ret

; The Repair Facility with a unit in it ($02972E-$029784): the unit's
; portrait, and its repair time (its +$5A) less the countdown, of that.
usp_repair:
        ld  a, (ix + O_LINKED)
        call unit_ptr
        push hl
        pop iy
        ld  a, (iy + O_TYPE)
        ld  h, 0
        call usp_pic_unit
        ld  l, (iy + U_TARGETATTACK)
        ld  h, (iy + U_TARGETATTACK + 1)
        ld  d, h
        ld  e, l
        ld  c, (ix + S_COUNTDOWN)
        ld  b, (ix + S_COUNTDOWN + 1)
        or  a
        sbc hl, bc
        jp  usp_bar2_hi

; The Palace ($029788-$029816): the Fremen for the Atreides, else +$52's
; portrait.  In its delay (+$4E) the label and no bar; else the house's
; weapon time ($06C75E) less the countdown, of that, while it counts.
usp_palace:
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ATREIDES
        jr  nz, usp_p1
        ld  hl, HUD_FREMEN      ; anim $5E
        ld  (panel_pic2), hl
        jr  usp_p2
usp_p1: ld  a, (ix + S_OBJECTTYPE)
        ld  h, (ix + S_OBJECTTYPE + 1)
        call usp_pic_unit
usp_p2: ld  a, (ix + S_ROTSPRITEDIFF)
        or  (ix + S_ROTSPRITEDIFF + 1)
        jr  z, usp_p3
        ld  a, 1
        ld  (panel_label), a
        jp  usp_bar2_hide
usp_p3: xor a
        ld  (panel_label), a
        ld  c, (ix + S_COUNTDOWN)
        ld  b, (ix + S_COUNTDOWN + 1)
        ld  a, b
        or  c
        jp  z, usp_bar2_hide
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_specialCountDown
        call usp_time
        jp  usp_bar2_hi
; HL + DE -> a time in the house's table, BC = what is left of it -> HL =
; the time less that, DE = the time.
usp_time:
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  h, d
        ld  l, e
        or  a
        sbc hl, bc
        ret

; The Starport ($02989A-$0298EA): no picture; with a Frigate on its way
; (the house's +$30 not negative), the delivery time ($06C760) less the
; house's countdown (+$2E), of that, at y 80.
usp_starport:
        call usp_pb_hide
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        pop iy
        bit 7, (iy + H_STARPORTLINK + 1)
        ret nz
        ld  c, (iy + H_STARPORTTIME)
        ld  b, (iy + H_STARPORTTIME + 1)
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_starportDeliveryTime
        call usp_time
        jp  usp_bar2_lo

; A Windtrap ($029838-$02985A): the player's power used (at least 1) of
; what is made, at y 80.
usp_windtrap:
        ld  a, (player_house)
        call house_ptr
        push hl
        pop iy
        ld  l, (iy + H_POWERUSE)
        ld  h, (iy + H_POWERUSE + 1)
        ld  a, h
        or  l
        jr  nz, usp_w1
        inc hl
usp_w1: ld  e, (iy + H_POWERPROD)
        ld  d, (iy + H_POWERPROD + 1)
        jp  usp_bar2_lo

; A Refinery or a Silo ($02985E-$02988C): the player's credits of the
; storage, both halved until the storage is $7FF or less, the credits at
; least 1; in pen 3 at y 80.
usp_spice:
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        ld  de, usp_d3
        ld  bc, 8
        ldir                    ; the credits, then the storage (+$16)
usp_s1: ld  hl, usp_d4 + 3
        ld  a, (hl)
        dec hl
        or  (hl)
        jr  nz, usp_s2
        dec hl
        ld  a, (hl)
        cp  8
        jr  c, usp_s3
usp_s2: ld  hl, usp_d4 + 3
        call usp_shr32
        ld  hl, usp_d3 + 3
        call usp_shr32
        jr  usp_s1
usp_s3: ld  hl, (usp_d3)
        ld  a, h
        or  l
        ld  bc, (usp_d3 + 2)
        or  b
        or  c
        jr  nz, usp_s4
        inc hl
usp_s4: ld  de, (usp_d4)
        jp  usp_bar2_lo3
; HL -> the top byte of a 32-bit value: halve it.
usp_shr32:
        srl (hl)
        dec hl
        rr  (hl)
        dec hl
        rr  (hl)
        dec hl
        rr  (hl)
        ret

; A unit ($029904-$0299DA): no label; a Harvester's load of 100 in pen 3
; at y 80 (the picture as it was), anything else neither picture nor bar.
usp_unit:
        xor a
        ld  (panel_label), a
        ld  a, (unit_selected)
        call unit_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        jr  z, usp_pb_hide
        ld  a, (ix + O_HP)
        or  (ix + O_HP + 1)
        jr  z, usp_pb_hide
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, usp_pb_hide     ; (with neither, $0299A0)
        ld  a, (ix + U_AMOUNT)
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        ld  de, 100
        jp  usp_bar2_lo3

; Nothing to show (L_0299D0; another house's structure, L_0298EE); the
; lower picture and the bar (ui_picture2_bar2_hide $009BAA); the bar
; alone, its value forgotten (ui_bar2_hide $009BB4).  Clobber A (the
; first), HL.
usp_none:
        xor a
        ld  (panel_label), a
usp_pb_hide:
        ld  hl, $FFFF
        ld  (panel_pic2), hl
usp_bar2_hide:
        ld  hl, $FFFF
        ld  (panel_bar2), hl
        ld  (usp_b2val), hl
        ld  (usp_b2full), hl
        ret

; IX = a structure -> NZ if its type makes things (+$0C bit 1).
; Clobbers A, DE, HL.
usp_makes:
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        bit 1, (hl)
        ret

; A = a structure type, H = its high byte -> panel_pic2 its portrait
; (every type's +$14 is one: anims 65-83).  Clobbers A, DE, HL.
usp_pic_struct:
        ld  e, a
        ld  a, h
        or  a
        ret nz
        ld  a, e
        cp  STRUCT_INFO_COUNT
        ret nc
        ld  hl, HUD_STRUCT
        jr  usp_pic
; A = a unit type, H = its high byte -> panel_pic2 its portrait, if the
; type's +$14 names one (0 does nothing, ui_picture2_show $009942).
; Clobbers A, DE, HL.
usp_pic_unit:
        ld  e, a
        ld  a, h
        or  a
        ret nz
        ld  a, e
        cp  UNIT_INFO_COUNT
        ret nc
        push af
        call unit_info
        ld  de, UI_f14
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        pop de                  ; D = the type
        ret z
        ld  e, d
        ld  hl, HUD_UNIT
usp_pic:
        ld  d, 0
        add hl, de
        ld  (panel_pic2), hl
        ret

; The second bar, HL = the value, DE = the full value (signed words):
; ui_bar2_show ($009856) at (272, 112) and ui_bar2_show_lower ($0096BC) at
; (272, 80), both in pen 7, and ui_bar2_show_lower_alt ($0096AC) at (272,
; 80) in pen 3; ui_bar2_show_at_colour ($009862) for all three.  A value
; of 0 or less hides the bar; a full value of 0 or less leaves it as it
; is, and so does the pair it showed last ($FFC742) - its place and colour
; too.  Otherwise the value, at most the full one, fills n = (value << 5,
; a word) / full pixels, one less if that divides exactly: the pixel its
; end is drawn at.  The frames are eighths, (n & 31) / 4 + 1 of them.
; Clobbers A, BC, DE, HL.
usp_bar2_hi:
        ld  a, 112
        ld  bc, HUD_BAR_PEN7
        jr  usp_bar2
usp_bar2_lo:
        ld  a, 80
        ld  bc, HUD_BAR_PEN7
        jr  usp_bar2
usp_bar2_lo3:
        ld  a, 80
        ld  bc, HUD_BAR_PEN3
usp_bar2:
        ld  (usp_b2y), a
        ld  (usp_b2f), bc
        bit 7, h
        jr  nz, usp_bar2_hide
        ld  a, h
        or  l
        jr  z, usp_bar2_hide
        bit 7, d
        ret nz
        ld  a, d
        or  e
        ret z
        push hl
        ld  bc, (usp_b2val)
        or  a
        sbc hl, bc
        jr  nz, usp_b2_new
        ld  hl, (usp_b2full)
        sbc hl, de
        jr  nz, usp_b2_new
        pop hl
        ret                     ; as shown
usp_b2_new:
        pop hl
        ld  (usp_b2val), hl
        ld  (usp_b2full), de
        ld  a, (usp_b2y)
        ld  (panel_bar2_y), a
        xor a
        ld  (panel_bar2_y + 1), a
        push hl
        sbc hl, de
        pop hl
        jr  c, usp_b2_1
        ld  h, d                ; no more than the full value
        ld  l, e
usp_b2_1:
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        call udiv16             ; HL = n, DE = the remainder
        ld  a, d
        or  e
        jr  nz, usp_b2_2
        dec hl
usp_b2_2:
        ld  a, l
        and 31
        add a, 4
        rrca
        rrca
        and $3F
        ld  hl, (usp_b2f)
        add a, l
        ld  l, a
        adc a, h
        sub l
        ld  h, a
        ld  (panel_bar2), hl
        ret

usp_b2val:      DW $FFFF        ; $FFC742 the pair the bar shows
usp_b2full:     DW $FFFF
usp_b2y:        DB 0
usp_b2f:        DW 0            ; the bar's first frame (its colour)
usp_d3:         DS 4            ; the credits, then the storage
usp_d4:         DS 4

; --------------------------------------------------------------- the radar
;
; S8 radar_frame $005124.  The radar is a 64 x 64 picture at (240, 120)
; (the Mega Drive's y 144, less the 24 lines the port has not got).  It is
; drawn a row a frame into the picture not showing, and the two swap when
; the last row is done, so the renderer redraws it once a scan.  The
; pictures are sprite frames (render.asm's format) in page PG_RADAR:
; W = 8, h = 64, four planes of (mask 0, data) pairs.

RADAR_A         EQU $4000
RADAR_B         EQU $5100
RADAR_PLANE     EQU 64 * 8 * 2
RADAR_MARK      EQU $6200       ; the marker, twice: then a pixel right
RADAR_MARK_SIZE EQU 2 + 4 * 7 * 2

; radar_init ($0050D2): at a mission's start.  Blank, the map not shown.
radar_init:
        call rd_make_marks
        ld  a, (map_scale)
        ld  (radar_small), a
        xor a
        ld  (radar_shows), a
        ld  hl, 0
        ld  (rd_script), hl
        ld  a, $FF
        ld  (radar_static), a
        ; both pictures' headers
        ld  a, PG_RADAR
        call map_w1
        ld  hl, RADAR_A
        ld  (hl), 8
        inc hl
        ld  (hl), 64
        ld  hl, RADAR_B
        ld  (hl), 8
        inc hl
        ld  (hl), 64
        call map_game
        ld  hl, RADAR_A         ; the one picture: rows go into it as they
        ld  (radar_front), hl   ; are made, as the cartridge's rows go to
        jp  radar_blank         ; VRAM, so a scan shows as it comes

; radar_blank: every row of an empty radar, at once.
radar_blank:
        xor a
        ld  (radar_row), a
        ld  a, 1
        ld  (rd_blank), a
rb_row: call rd_one_row
        ld  a, (radar_row)
        or  a
        jr  nz, rb_row
        xor a
        ld  (rd_blank), a
        ld  hl, radar_gen       ; blanked: copied once
        inc (hl)
        ret

; radar_update_state ($01A7FA, PC House_UpdateRadarState): A = a house.
; For the player's only: the radar works while it has an Outpost and uses
; no more power than it makes.  -> A = 1 if it has just come on.
radar_update_state:
        ld  b, a
        ld  a, (player_house)
        cp  b
        ld  a, 0
        ret nz
        ld  a, b
        call house_ptr
        push hl
        pop iy
        ; works: an Outpost (bit 18 of structuresBuilt), use <= output
        ld  c, 0
        bit 2, (iy + H_BUILT + 2)
        jr  z, rus_1
        ld  l, (iy + H_POWERPROD)
        ld  h, (iy + H_POWERPROD + 1)
        ld  e, (iy + H_POWERUSE)
        ld  d, (iy + H_POWERUSE + 1)
        or  a
        sbc hl, de              ; output - use, signed
        jp  pe, rus_ov
        jp  m, rus_1
        jr  rus_works
rus_ov: jp  p, rus_1            ; (overflow flips the sign)
rus_works:
        inc c
rus_1:  ; C = 1 it works.  Word bit 4 of H_FLAGS (the low byte's bit 4,
        ; a port-only bit next to S7's 0-3; nothing else reads it): it was on
        bit 4, (iy + H_FLAGS)
        jr  z, rus_was_off
        ld  a, c
        or  a
        jr  z, rus_off          ; on, and no longer works
        ld  a, (radar_option)
        cp  2
        jr  z, rus_on
        xor a
        ret
rus_was_off:
        ld  a, c
        or  a
        ret z
rus_on: ld  a, (radar_option)
        cp  1
        jr  nz, rus_on2
        call radar_switch_on
        ld  a, $3E
        FCALL snd_effect
rus_on2:
        ld  a, (radar_option)
        cp  2
        jr  nz, rus_on3
        ld  a, 1                ; radar_restart_scan
        ld  (radar_shows), a
        xor a
        ld  (radar_row), a
rus_on3:
        set 4, (iy + H_FLAGS)
        ld  a, 1
        ret
rus_off:
        ld  a, (radar_option)
        or  a
        jr  z, rus_off2
        ld  a, $3E
        FCALL snd_effect
        call radar_switch_off
rus_off2:
        res 4, (iy + H_FLAGS)
        xor a
        ret

radar_switch_on:
        ld  a, 1
        ld  (radar_shows), a
        ld  hl, rd_script_on
        jr  rso_go
radar_switch_off:
        call radar_blank
        xor a
        ld  (radar_shows), a
        ld  hl, rd_script_off
rso_go: ld  (rd_script), hl
        ld  hl, 0
        ld  (rd_delay), hl
        xor a
        ld  (radar_row), a
        ret

; radar_frame: every pass.  The switching animation steps by the frames
; passed; otherwise one row a frame.
radar_frame:
        ld  hl, (rd_script)
        ld  a, h
        or  l
        jr  z, rf_rows
        ld  hl, (rd_delay)
        ld  de, (frames_this_pass)
        or  a
        sbc hl, de
        ld  (rd_delay), hl
        jr  z, rf_step
        bit 7, h
        ret z
rf_step:
        ld  hl, (rd_script)
        ld  a, (hl)             ; the frame, $FF the end
        inc hl
        ld  e, (hl)             ; its frames
        inc hl
        ld  (rd_script), hl
        cp  $FF
        jr  z, rf_end
        ld  (radar_static), a
        ld  d, 0
        ld  (rd_delay), de
        ret
rf_end: ld  hl, 0
        ld  (rd_script), hl
        ld  a, $FF
        ld  (radar_static), a
rf_rows:
        ld  a, (frames_this_pass)
        or  a
        jr  nz, rfr_1
        inc a
rfr_1:  cp  8
        jr  c, rfr_2
        ld  a, 8
rfr_2:  ld  b, a
rfr_loop:
        push bc
        call rd_one_row
        pop bc
        djnz rfr_loop
        ret

; One row, radar_row & 63, into the back picture; after row 63 the two
; swap.
rd_one_row:
        ld  a, (radar_row)
        and 63
        ld  (rd_r), a
        call rd_colours
        ; into the picture: plane p, row r: + 2 + p * RADAR_PLANE + r * 16
        ld  a, PG_RADAR
        call map_w1
        ld  a, (rd_r)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        inc hl
        inc hl
        ld  de, (radar_front)
        add hl, de              ; plane 0's row
        ld  c, 0                ; the plane
rdo_plane:
        push hl
        ld  b, 8                ; columns
        ld  a, c
        add a, a
        ld  e, a
        ld  d, 0
        ld  ix, rd_col
        add ix, de              ; pixel 2p of column 0
rdo_col:
        ld  (hl), 0             ; mask: opaque
        inc hl
        push hl
        ld  e, (ix + 0)
        ld  d, 0
        ld  hl, radar_pen_l
        add hl, de
        ld  a, (hl)
        ld  e, (ix + 1)
        ld  hl, radar_pen_r
        add hl, de
        or  (hl)
        pop hl
        ld  (hl), a
        inc hl
        ld  de, 8
        add ix, de
        djnz rdo_col
        pop hl
        ld  de, RADAR_PLANE
        add hl, de
        inc c
        ld  a, c
        cp  4
        jr  nz, rdo_plane
        call map_game
        ld  a, (radar_row)
        inc a
        and 63
        ld  (radar_row), a
        and 7
        ret nz
        ld  a, (radar_shows)    ; a cell row of the map is complete: the
        or  a                   ; renderer copies the picture again (the
        ret z                   ; map off, its rows are all the same)
        ld  hl, radar_gen
        inc (hl)
        ret

; rd_r -> rd_col: the 64 pens of the row (MD line 2 numbers).
rd_colours:
        ld  a, (player_house)
        cp  3
        jr  c, rdc_h
        ld  a, 2
rdc_h:  ld  (rd_house3), a
        ld  a, (rd_r)
        or  a
        jp  z, rdc_border
        cp  63
        jp  z, rdc_border
        ld  a, (rd_blank)
        or  a
        jp  nz, rdc_empty
        ; the map row and its first square
        ld  a, (radar_small)
        or  a
        ld  a, (rd_r)
        ld  b, 64
        ld  c, 0
        jr  z, rdc_big
        srl a
        add a, 16
        ld  b, 32
        ld  c, 16
rdc_big:
        ; DE = the square, row * 64 + first column, in MAP_HIGH; a row's
        ; squares are one byte apart and never cross E's 256
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, l
        or  c
        ld  e, a
        ld  a, h
        or  MAP_HIGH >> 8
        ld  d, a
        ld  ix, rd_col
        ld  a, (radar_shows)
        or  a
        jr  z, rdc_offsq
        ; the map shown: rd_square_map's rule, inlined (a row is drawn
        ; every pass, 64 squares of it), the planes reached by D's bits
        ; (MAP_GROUND $C, MAP_HIGH $D, MAP_FLAGS $E, MAP_INDEX $F) and
        ; tbl_radar_icon_colour by L (256-aligned, dune.asm)
rdc_sq: ld  a, (de)             ; ground bit 8 | overlay << 1
        ld  c, a
        srl a
        ld  l, a
        ld  h, tbl_radar_icon_colour >> 8
        ld  a, (hl)             ; the overlay's entry: positive wins
        or  a
        jp  m, rdc_obj
        jr  nz, rdc_put
rdc_obj:
        set 5, d                ; MAP_INDEX: what stands there
        ld  a, (de)
        res 5, d
        or  a
        jr  nz, rdc_object
        res 4, d                ; MAP_GROUND: the icon's low byte
        ld  a, (de)
        set 4, d
        ld  l, a
        ld  a, c
        and 1                   ; and its bit 8
        add a, tbl_radar_icon_colour >> 8
        ld  h, a
        ld  a, (hl)
        and $0F
rdc_put:
        ld  (ix + 0), a
        inc ix
        inc e
        djnz rdc_sq
        jr  rdc_small
rdc_object:
        ; A = the slot + 1 of a unit (MAP_FLAGS bit MF_UNIT) or a structure:
        ; the pen of its house
        dec a
        push bc
        push de
        ld  c, a
        set 5, d
        res 4, d                ; MAP_FLAGS
        ld  a, (de)
        and 1 << MF_UNIT
        ld  a, c
        jr  z, rdc_st
        call unit_ptr
        jr  rdc_hs
rdc_st: call struct_ptr
rdc_hs: ld  de, O_HOUSE
        add hl, de
        ld  e, (hl)
        ld  d, 0
        ld  hl, tbl_radar_house_colour
        add hl, de
        ld  a, (hl)
        pop de
        pop bc
        jp  rdc_put
rdc_offsq:
        ; the map off: rd_square_off with the plain square number
        push bc
        push de
        ld  a, d
        and $0F
        ld  h, a
        ld  l, e
        call rd_square_off
        pop de
        pop bc
        ld  (ix + 0), a
        inc ix
        inc e
        djnz rdc_offsq
rdc_small:
        ; the small map: each of its 32 pens twice
        ld  a, (radar_small)
        or  a
        jr  z, rdc_edge
        ld  hl, rd_col + 31
        ld  de, rd_col + 63
        ld  b, 32
rdc_dbl:
        ld  a, (hl)
        ld  (de), a
        dec de
        ld  (de), a
        dec de
        dec hl
        djnz rdc_dbl
rdc_edge:
        ; the edge pixels (radar_pack_row)
        ld  a, (player_house)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_radar_border_colour
        add hl, de
        ld  a, (hl)
        ld  (rd_col), a
        ld  (rd_col + 63), a
        ret
rdc_empty:
        ld  a, 12
        ld  hl, rd_col
        ld  b, 64
rdc_e:  ld  (hl), a
        inc hl
        djnz rdc_e
        ld  a, (player_house)
        ld  e, a
        ld  d, 0
        ld  hl, tbl_radar_border_colour
        add hl, de
        ld  a, (hl)
        ld  (rd_col), a
        ld  (rd_col + 63), a
        ret
rdc_border:
        ld  a, (rd_house3)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_radar_house_pixels
        add hl, de
        ld  a, (hl)
        and $0F
        ld  hl, rd_col
        ld  b, 64
rdc_b:  ld  (hl), a
        inc hl
        djnz rdc_b
        ret

; HL = a square, the map shown -> A = its pen (and NZ).  The overlay's
; entry if positive, else the house of what stands there, else the
; ground's entry.
rd_square_map:
        push hl
        ld  a, h
        or  MAP_HIGH >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        push af
        srl a                   ; the overlay
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, tbl_radar_icon_colour
        add hl, de
        ld  a, (hl)
        pop hl
        or  a
        jp  m, rsm_obj
        jr  z, rsm_obj
        pop de
        ret
rsm_obj:
        push hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        or  a
        jr  z, rsm_ground
        dec a
        ld  c, a
        push hl
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNIT, (hl)
        ld  a, c
        jr  z, rsm_st
        call unit_ptr
        jr  rsm_h
rsm_st: call struct_ptr
rsm_h:  ld  de, O_HOUSE
        add hl, de
        ld  e, (hl)
        ld  d, 0
        ld  hl, tbl_radar_house_colour
        add hl, de
        ld  a, (hl)
        pop hl
        pop de
        ret
rsm_ground:
        pop af
        and 1
        ld  d, a
        push hl
        ld  a, h
        or  MAP_GROUND >> 8
        ld  h, a
        ld  e, (hl)
        ld  hl, tbl_radar_icon_colour
        add hl, de
        ld  a, (hl)
        pop hl
        and $0F
        ret

; HL = a square, the map off -> A = its pen: 12, or the player's colour
; on a square of one of the player's structures.
rd_square_off:
        push hl
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_STRUCT, (hl)
        pop hl
        ld  a, 12
        ret z
        push hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        or  a
        ld  a, 12
        ret z
        push hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        dec a
        call struct_ptr
        ld  de, O_HOUSE
        add hl, de
        ld  a, (player_house)
        cp  (hl)
        pop hl
        ld  a, 12
        ret nz
        ld  a, (player_house)
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, tbl_radar_house_colour
        add hl, de
        ld  a, (hl)
        pop hl
        ret

; the switching animations ($068C16 on, $068BCA off): (frame, frames),
; $FF the end
rd_script_on:
        DB  11, 5, 10, 5, 9, 5, 8, 5, 7, 5, 6, 5, 5, 5, 4, 5, 3, 5, 2, 5
        DB  1, 5, 0, 5, 1, 5, 0, 5, 1, 5, 0, 5, 1, 5, 0, 5, 11, 0, $FF, 0
rd_script_off:
        DB  0, 5, 1, 5, 0, 5, 1, 5, 0, 5, 1, 5, 0, 5, 1, 5, 2, 5, 3, 5
        DB  4, 5, 5, 5, 6, 5, 7, 5, 8, 5, 9, 5, 10, 5, 11, 60, $FF, 0

; The radar's marker ($06A80C, tile $7A1 in line 2, placed at -3,-3 from
; its point: radar_create $004E6E): a 5 x 5 frame of white corners with a
; black edge, 7 rows of 8 pens (0 clear); then the same a pixel to the
; right, for a point whose corner falls on an odd x (the renderer places
; pictures on even ones).
rd_mark_pens:
        DB  12,12,12, 0,12,12,12, 0
        DB  12, 9, 9,12, 9, 9,12, 0
        DB  12, 9,12, 0,12, 9,12, 0
        DB   0,12, 0, 0, 0,12, 0, 0
        DB  12, 9,12, 0,12, 9,12, 0
        DB  12, 9, 9,12, 9, 9,12, 0
        DB  12,12,12, 0,12,12,12, 0
        DB   0,12,12,12, 0,12,12,12
        DB   0,12, 9, 9,12, 9, 9,12
        DB   0,12, 9,12, 0,12, 9,12
        DB   0, 0,12, 0, 0, 0,12, 0
        DB   0,12, 9,12, 0,12, 9,12
        DB   0,12, 9, 9,12, 9, 9,12
        DB   0,12,12,12, 0,12,12,12

; The two marker pictures into PG_RADAR at RADAR_MARK, in the renderer's
; frame format (W 1, h 7, then planes 0-3 of 7 rows of (mask, data)),
; through the radar's pens.
rd_make_marks:
        ld  a, PG_RADAR
        call map_w1
        ld  hl, RADAR_MARK
        ld  de, rd_mark_pens
        ld  b, 2
rmm_pic:
        push bc
        ld  (hl), 1
        inc hl
        ld  (hl), 7
        inc hl
        ld  c, 0                ; the plane
rmm_plane:
        push de
        ld  a, c
        add a, a
        add a, e
        ld  e, a
        jr  nc, rmm_p1
        inc d
rmm_p1: ld  b, 7
rmm_row:
        push bc
        ld  a, (de)             ; the left pixel
        ld  bc, radar_pen_l
        call rmm_pen
        ld  (rmm_data), a
        sbc a, a                ; clear: the screen's left pixel stays
        and $47
        ld  (rmm_mask), a
        inc de
        ld  a, (de)             ; the right one
        dec de
        ld  bc, radar_pen_r
        call rmm_pen
        push af
        ld  b, a
        ld  a, (rmm_data)
        or  b
        ld  (rmm_data), a
        pop af
        sbc a, a
        and $B8
        ld  b, a
        ld  a, (rmm_mask)
        or  b
        ld  (hl), a
        inc hl
        ld  a, (rmm_data)
        ld  (hl), a
        inc hl
        ld  a, e                ; the next row
        add a, 8
        ld  e, a
        jr  nc, rmm_r1
        inc d
rmm_r1: pop bc
        djnz rmm_row
        pop de
        inc c
        ld  a, c
        cp  4
        jr  nz, rmm_plane
        ex  de, hl              ; the next picture's pens
        ld  bc, 7 * 8
        add hl, bc
        ex  de, hl
        pop bc
        djnz rmm_pic
        jp  map_game

; A = a pen, BC = radar_pen_l or _r -> A = its bits, carry if it is 0
; (clear).
rmm_pen:
        or  a
        scf
        ret z
        add a, c
        ld  c, a
        adc a, b
        sub c
        ld  b, a
        ld  a, (bc)
        or  a
        ret

rmm_data:       DB 0
rmm_mask:       DB 0

        INCLUDE "radar_pens.inc"

rd_script:      DW 0
rd_delay:       DW 0
rd_blank:       DB 0
rd_r:           DB 0
rd_house3:      DB 0
rd_col:         DS 64
