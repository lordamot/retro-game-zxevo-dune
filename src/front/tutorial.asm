; tutorial.asm - bank TUTOR: the Tutorial (ui_tutorial $030674).
;
; The title's TUTORIAL, and what the title turns to after 900 idle frames:
; the Mega Drive plays scripts 0, 1, 3, 5, 6 and 7 of its picture
; interpreter (tut_run_script $0418D4) to music track 5 - descriptions of
; the terrain, the units and the buildings, then constructing, harvesting,
; attacking and guarding, each a slide show of two planes of tiles under
; a picture of the pad in two hands and a text box.  A, B or C cut a wait
; short; START ends it all.
;
; This is that interpreter, running the cartridge's scripts, tiles and
; name-table frames as tools/dune_tutorial.py packed them (tutorial.inc,
; data pages TUT_PAGES (pages.inc PG_TUT_DATA) - the directory tut_dir, the TA_ numbers):
;
; - a plane is a name table of 40 x 28 of the VDP's words, and a frame
;   (tu_decode) writes words into it, marking the cells it changes;
;   showing a frame (tu_show) draws every marked cell (tu_cell): its
;   plane B tile, plane A's over it where A's pens are not 0 (or the other
;   way round for a B tile with priority over an A tile without), each
;   in its palette line, flipped as the word says.  The port shows the
;   Mega Drive's lines 8-207: rows 1-25.
; - a line's pens become plane bytes through tu_conv, a table a line and
;   a line parity built from the picture group's MAP (tu_setmap): the 16
;   EGA colours and the dither of dune_front.Palette.
; - the pad ("cursor" opcodes, tut_cursor_show $01314A) and the text box
;   (textbox_show $042956) are sprites: drawn over the planes, and put back
;   from a copy of the planes kept on the screen not shown.
; - the waits keep the script's own clock (tu_clock), so the time a frame
;   takes to draw comes out of the next wait rather than adding to it.
;
; Memory, all of it the front end's (it draws its screens afresh after):
;   window 0     this bank: the code, tu_conv, tu_mask, tu_swap, the
;                overlay's pens (tu_ovl)
;   screen 0     shown, drawn directly (TU_VIS_A/B)
;   screen 1     the planes without the sprites (TU_CLN_A/B)
;   page 124     the two name tables, a changed byte a cell, the frames
;   page 125     the pad: shape 0 and the shape shown
;   pages 126-7  the tiles; above tiles 512 on, the text box and the font

TU_VIS_A        EQU PG_SCR0_A
TU_VIS_B        EQU PG_SCR0_B
TU_CLN_A        EQU PG_SCR1_A
TU_CLN_B        EQU PG_SCR1_B
TU_TILES        EQU 126             ; tiles 0-511; 127: 512 on
TU_WORK         EQU 124
TU_PADPG        EQU 125
TU_BOXPG        EQU 127

; window 1 addresses (window 3: + $8000)
TU_NTA          EQU $4000           ; plane A's words, low byte first
TU_NTB          EQU TU_NTA + 2240   ; plane B's
TU_DIRTY        EQU TU_NTB + 2240   ; 1: the cell changed since it was drawn
TU_FRAMES       EQU TU_DIRTY + 1120 ; plane A's frames, then B's, then 0, 0
TU_PADW         EQU 104             ; the pad: pixel pairs a line
TU_PADH         EQU 58              ; ... and the lines the port shows
TU_PADSIZE      EQU TU_PADW * TU_PADH
TU_PADBASE      EQU $4000           ; in TU_PADPG: shape 0
TU_PADWORK      EQU TU_PADBASE + TU_PADSIZE     ; the shape shown
TU_PADTMP       EQU TU_PADWORK + TU_PADSIZE     ; a shape's patch
TU_BOXW         EQU 136
TU_BOXH         EQU 32
TU_BOXWORK      EQU $4000 + $1880   ; in TU_BOXPG, above tiles 512-706
TU_FONT         EQU TU_BOXWORK + TU_BOXW * TU_BOXH
TU_BOX_X        EQU 28              ; textbox_show at ($1C, $20)
TU_BOX_Y        EQU 32 - 8
TU_FADE_STEP    EQU 8               ; frames a step of a fade (pal speed 5)

; --------------------------------------------------------- the entry

; tut_play: the whole tutorial.  -> A = 0 played through, 1 START ended it.
; The front end's screens, pictures and background are gone after it.
tut_play:
        ld  a, (port_7ffd)
        and 8
        call nz, vid_flip       ; screen 0 shown, screen 1 drawn on no more
        ld  hl, tu_black
        call vid_palette
        ld  a, MUS_STARPORT     ; song 5 of the game's bank
        FCALL snd_mus
        call tu_init
        xor a
        ld  (tu_sn), a
tutp_next:   ld  a, (tu_sn)
        call tu_script
        jr  nz, tutp_stop
        ld  hl, tu_sn
        inc (hl)
        ld  a, (hl)
        cp  TU_SCRIPTS
        jr  nz, tutp_next
        xor a
        jr  tutp_done
tutp_stop:   ld  a, 1
tutp_done:   push af
        ld  hl, tu_black
        call vid_palette
        call vid_clear_all      ; nothing of it on either screen after
        call map_game
        pop af
        ret

tu_init:
        ; the name tables empty and every cell to be drawn
        ld  a, TU_WORK
        call map_w1
        ld  hl, TU_NTA
        ld  de, TU_NTA + 1
        ld  bc, 4480 - 1
        ld  (hl), 0
        ldir
        ld  hl, TU_DIRTY
        ld  de, TU_DIRTY + 1
        ld  bc, 1120 - 1
        ld  (hl), 1
        ldir
        ; the pad's shape 0, and the text box's font
        ld  a, TU_PADPG
        call map_w3
        ld  a, TA_PAD_BASE
        call tu_asset
        ld  de, TU_PADBASE + $8000
        ld  bc, TU_PADSIZE
        call tu_unlz
        ld  a, TU_BOXPG
        call map_w3
        ld  a, TA_FONT_PENS
        call tu_asset
        ld  de, TU_FONT + $8000
        ld  bc, 34 * 32
        ldir
        ld  a, $FF
        ld  (tu_pshape), a      ; no pad (tut_cursor_load)
        ld  (tu_ovlwho), a
        ld  (tu_pic), a
        xor a
        ld  (tu_boxon), a
        ld  (tu_px), a
        ld  (tu_group), a
        ld  a, 200
        ld  (tu_py), a
        ld  hl, (frame_count)
        ld  (tu_clock), hl
        ret

; A = TA_ number -> window 1 = its page, HL = its address.  Keeps BC, DE.
tu_asset:
        push de
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de
        ld  de, tut_dir
        add hl, de
        ld  a, (hl)
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        pop de
        jp  map_w1

; HL = packed bytes (dune_front.lz_pack), DE = where (window 3), BC = how
; many come out.  Clobbers all.
tu_unlz:
        push hl
        ld  h, d
        ld  l, e
        add hl, bc
        ld  (tu_lzend), hl
        pop hl
tutul_1:     ld  a, (hl)
        inc hl
        bit 7, a
        jr  nz, tutul_match
        ld  c, a
        ld  b, 0
        inc bc
        ldir
        jr  tutul_test
tutul_match:
        and $7F
        add a, 3
        ld  c, a
        ld  b, 0
        ld  a, (hl)
        inc hl
        push hl
        ld  h, (hl)
        ld  l, a                ; the offset
        push de
        ex  de, hl
        or  a
        sbc hl, de
        pop de
        ldir
        pop hl
        inc hl
tutul_test:
        push hl
        ld  hl, (tu_lzend)
        or  a
        sbc hl, de
        pop hl
        jr  nz, tutul_1
        ret

; ------------------------------------------------------- the scripts

; A = the script (0-5 of TU_SCRIPTS) -> Z played to its end, NZ START.
tu_script:
        add a, a
        ld  l, a
        ld  h, 0
        ld  de, tu_scripts
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (tu_pc), de
tutsc_op:    call tu_fetch
        or  a
        ret z                   ; the end
        add a, a
        ld  l, a
        ld  h, 0
        ld  de, tu_ops - 2
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        or  a                   ; (a handler says START with carry)
        call tutsc_jp
        jr  nc, tutsc_op
        or  1                   ; START
        ret
tutsc_jp:    jp  (hl)

; The script's next byte -> A.  Keeps BC, DE, HL.
tu_fetch:
        push hl
        push de
        ld  a, TA_SCRIPTS
        call tu_asset
        ld  de, (tu_pc)
        add hl, de
        inc de
        ld  (tu_pc), de
        ld  a, (hl)
        pop de
        pop hl
        ret

; The opcodes (dune_tutorial.OPS, from 1); each returns carry for START.
tu_ops:
        DW  tuop_wait, tuop_picture, tuop_frame, tuop_mark, tuop_until, tuop_fadeout
        DW  tuop_fadein, tuop_repeat, tuop_loop, tuop_skip, tuop_sound, tuop_rewind
        DW  tuop_cursor, tuop_cursorxy, tuop_slideup, tuop_slidedown, tuop_palette
        DW  tuop_text, tuop_textoff, tuop_clearb

; $02 w: wait w frames by the script's clock; A, B or C cut it short,
; START ends the tutorial (tut_wait $0418A4).
tuop_wait:
        call tu_fetch
        ld  e, a
        call tu_fetch
        ld  d, a
        ld  hl, (tu_clock)
        add hl, de
        ld  (tu_clock), hl
tutw_1:      call pad_take
        bit 7, a
        scf
        ret nz
        and $70
        jr  nz, tutw_cut
        ld  hl, (tu_clock)
        ld  de, (frame_count)
        or  a
        sbc hl, de
        jr  z, tutw_done
        bit 7, h
        jr  nz, tutw_done         ; its time has come
        FCALL snd_idle          ; vid_wait_frame, moving the music on
        jr  tutw_1
tutw_done:   or  a
        ret
tutw_cut:    call tu_resync
        or  a
        ret

; The clock is now: after what takes its own time (fades, loads, slides).
tu_resync:
        ld  hl, (frame_count)
        ld  (tu_clock), hl
        ret

; $04 p m: load picture p (tut_load_picture $041662); its frames draw
; with MAP m (dune_tutorial: the palette the script shows it in).
tuop_picture:
        call tu_fetch
        push af
        call tu_fetch
        call tu_setmap
        pop af
        call tu_picture
        call tu_resync
        or  a
        ret

; $06 w: the next frame of plane w, shown.
tuop_frame:
        call tu_fetch
        call tu_decode
        call tu_show
        or  a
        ret

tuop_mark:
        ld  hl, (tu_pc)
        ld  (tu_mark), hl
        or  a
        ret

; $0A $FFFF: back to the mark until the last frame found the plane's end.
tuop_until:
        ld  a, (tu_last)
        inc a
        ret z                   ; (carry clear)
        ld  hl, (tu_mark)
        ld  (tu_pc), hl
        or  a
        ret

tuop_fadeout:
        call tu_fade_out
        call tu_resync
        or  a
        ret

; $10 pal: fade in to it (its MAP for the picture's group).
tuop_fadein:
        call tu_fetch
        call tu_setmap
        call tu_fade_in
        call tu_resync
        or  a
        ret

tuop_repeat:
        call tu_fetch
        ld  (tu_count), a
        ld  hl, (tu_pc)
        ld  (tu_mark), hl
        or  a
        ret

tuop_loop:
        ld  hl, tu_count
        dec (hl)
        ret z
        ld  hl, (tu_mark)
        ld  (tu_pc), hl
        or  a
        ret

; $16 w n: n frames of plane w into its words, not shown.
tuop_skip:
        call tu_fetch
        ld  c, a
        call tu_fetch
        ld  b, a
tuos_1:      push bc
        ld  a, c
        call tu_decode
        pop bc
        djnz tuos_1
        or  a
        ret

; $18 s: a sound (the port's SFX_ id, $FF: not in the sound set).
tuop_sound:
        call tu_fetch
        cp  $FF
        ret z                   ; (carry clear: $FF - $FF)
        FCALL snd_sfx
        or  a
        ret

tuop_rewind:
        ld  hl, (tu_startA)
        ld  (tu_posA), hl
        or  a
        ret

; $22 y x s: the pad, shape s, at x, y.
tuop_cursor:
        call tu_fetch
        ld  d, a
        call tu_fetch
        ld  e, a
        call tu_fetch
        call tu_pad_set
        or  a
        ret

; $26 y x: the pad moved.
tuop_cursorxy:
        call tu_fetch
        ld  d, a
        call tu_fetch
        ld  e, a
        ld  a, (tu_pshape)
        call tu_pad_set
        or  a
        ret

tuop_slideup:
        ld  a, -3
        jr  tuosl_1
tuop_slidedown:
        ld  a, 3
tuosl_1:     call tu_slide
        call tu_resync
        or  a
        ret

; $2C pal: the Mega Drive's palette changed (the port's 16 colours stay:
; what is drawn next draws in the new ones).
tuop_palette:
        call tu_fetch
        call tu_setmap
        call tu_fetch           ; the lines it changes (bit per line)
        ld  (tu_lines), a
        ; the cells of either plane drawn in them: again
        ld  a, TU_WORK
        call map_w1
        ld  hl, TU_NTA + 1
        ld  de, TU_DIRTY
        ld  bc, 1120
tuopl_1:   push bc
        ld  a, (hl)
        call tuopl_line
        ld  bc, 2240
        push hl
        add hl, bc
        ld  a, (hl)
        pop hl
        call tuopl_line
        pop bc
        inc hl
        inc hl
        inc de
        dec bc
        ld  a, b
        or  c
        jr  nz, tuopl_1
        or  a
        ret
; A = a word's high byte: its cell (DE) marked if its line changed.
tuopl_line:
        rlca
        rlca
        rlca
        and 3                   ; the line
        ld  b, a
        ld  a, (tu_lines)
        inc b
tuopl_2:   rrca
        djnz tuopl_2
        ret nc
        ld  a, 1
        ld  (de), a
        ret

tuop_text:
        ld  de, tu_text
tuot_1:      call tu_fetch
        ld  (de), a
        inc de
        or  a
        jr  nz, tuot_1
        call tu_box_show
        or  a
        ret

tuop_textoff:
        call tu_box_hide
        or  a
        ret

; $34: plane B cleared.
tuop_clearb:
        ld  a, TU_WORK
        call map_w1
        ld  hl, TU_NTB
        ld  de, TU_NTB + 1
        ld  bc, 2240 - 1
        ld  (hl), 0
        ldir
        ld  hl, TU_DIRTY
        ld  de, TU_DIRTY + 1
        ld  bc, 1120 - 1
        ld  (hl), 1
        ldir
        or  a
        ret

; ---------------------------------------------------------- pictures

; A = the picture: its tiles (if it has its own) into pages 126-127, its
; planes' frames into the work page, both planes back to their first
; frame.  The name tables stay as they are, as the Mega Drive's buffers do.
tu_picture:
        ld  (tu_pic), a
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        add hl, hl
        add hl, de              ; x 11
        ld  de, tu_pictures
        add hl, de
        ld  de, tu_prec
        ld  bc, TU_PIC_SIZE
        ldir
        ; its blank tile
        ld  a, (tu_pic)
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  de, tu_blank
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (tu_blankt), de
        ld  a, (tu_prec + 10)
        ld  (tu_group), a
        ; the tiles
        ld  a, (tu_prec)
        cp  $FF
        jr  z, tutpi_2
        ld  a, TU_TILES
        call map_w3
        ld  hl, (tu_prec + 2)   ; how many
        ld  de, 512
        call tutpi_min
        ld  a, (tu_prec)
        call tu_asset
        ld  de, $C000
        call tu_unlz
        ld  a, (tu_prec + 1)
        cp  $FF
        jr  z, tutpi_new
        ld  a, TU_TILES + 1
        call map_w3
        ld  hl, (tu_prec + 2)
        ld  de, -512
        add hl, de
        ld  de, 512
        call tutpi_min
        ld  a, (tu_prec + 1)
        call tu_asset
        ld  de, $C000
        call tu_unlz
tutpi_new:   ; new tiles: every cell looks different (the VRAM changed
        ; under the Mega Drive's name tables)
        ld  a, TU_WORK
        call map_w1
        ld  hl, TU_DIRTY
        ld  de, TU_DIRTY + 1
        ld  bc, 1120 - 1
        ld  (hl), 1
        ldir
tutpi_2:     ; the frames: A, then B, then two zeros (a plane with none)
        ld  a, TU_WORK
        call map_w3
        ld  de, TU_FRAMES + $8000
        ld  hl, TU_FRAMES
        ld  (tu_startA), hl
        ld  a, (tu_prec + 4)
        cp  $FF
        jr  z, tutpi_3
        ld  bc, (tu_prec + 5)
        push bc
        call tu_asset
        call tu_unlz
        pop bc
        ld  hl, TU_FRAMES
        add hl, bc
        ld  d, h
        ld  e, l
        set 7, d
tutpi_3:     ld  (tu_startB), hl
        ld  a, (tu_prec + 7)
        cp  $FF
        jr  z, tutpi_4
        ld  bc, (tu_prec + 8)
        push bc
        push hl
        call tu_asset
        call tu_unlz
        pop hl
        pop bc
        add hl, bc
        ld  d, h
        ld  e, l
        set 7, d
tutpi_4:     xor a
        ld  (de), a
        inc de
        ld  (de), a
        dec de
        ; a plane with no frames starts on the end
        ld  a, (tu_prec + 4)
        cp  $FF
        jr  nz, tutpi_5
        ld  (tu_startA), de
        ld  a, d
        res 7, a
        ld  (tu_startA + 1), a
tutpi_5:     ld  a, (tu_prec + 7)
        cp  $FF
        jr  nz, tutpi_6
        ld  (tu_startB), de
        ld  a, d
        res 7, a
        ld  (tu_startB + 1), a
tutpi_6:     ld  hl, (tu_startA)
        ld  (tu_posA), hl
        ld  hl, (tu_startB)
        ld  (tu_posB), hl
        ret
; BC = min(HL, DE) * 32.
tutpi_min:   push hl
        or  a
        sbc hl, de
        pop hl
        jr  c, tutpm_1
        ex  de, hl
tutpm_1:     add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  b, h
        ld  c, l
        ret

; A = the plane (0 A, 1 B): its next frame into its words (a changed word
; marks its cell).  tu_last = 0, or $FF at the end (where it stays).
tu_decode:
        push af
        ld  a, TU_WORK
        call map_w1
        pop af
        or  a
        ld  hl, (tu_posA)
        ld  ix, TU_NTA
        ld  bc, -TU_NTA
        jr  z, tutdc_1
        ld  hl, (tu_posB)
        ld  ix, TU_NTB
        ld  bc, -TU_NTB
tutdc_1:     ld  (tu_plane), a
        ld  (tu_ntneg), bc
        ld  a, (hl)
        or  a
        jr  nz, tutdc_op
        ld  a, $FF
        ld  (tu_last), a
        ret
tutdc_op:    ld  a, (hl)
        inc hl
        or  a
        jr  z, tutdc_end
        cp  $80
        jr  z, tutdc_skip
        jr  c, tutdc_run
        and $7F
        ld  b, a
tutdc_lit:   ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        call tutdc_put
        djnz tutdc_lit
        jr  tutdc_op
tutdc_run:   ld  b, a
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
tutdc_r1:    call tutdc_put
        djnz tutdc_r1
        jr  tutdc_op
tutdc_skip:  ld  e, (hl)
        inc hl
        ld  d, 0
        add ix, de
        add ix, de
        jr  tutdc_op
tutdc_end:   ld  a, (tu_plane)
        or  a
        jr  nz, tutdc_e1
        ld  (tu_posA), hl
        jr  tutdc_e2
tutdc_e1:    ld  (tu_posB), hl
tutdc_e2:    xor a
        ld  (tu_last), a
        ret
; DE = a word for the cell at IX: if it is new, stored and marked.
tutdc_put:   ld  a, (ix + 0)
        cp  e
        jr  nz, tutdp_1
        ld  a, (ix + 1)
        cp  d
        jr  z, tutdp_2
tutdp_1:     ld  (ix + 0), e
        ld  (ix + 1), d
        push hl
        push bc
        push ix
        pop hl
        ld  bc, (tu_ntneg)
        add hl, bc
        srl h
        rr  l
        ld  bc, TU_DIRTY
        add hl, bc
        ld  (hl), 1
        pop bc
        pop hl
tutdp_2:     inc ix
        inc ix
        ret

; --------------------------------------------------------- the cells

; Every marked cell drawn (the port's rows: the Mega Drive's 1-25), then
; the sprites the planes changed under.
tu_show:
        xor a
        ld  (tu_hitp), a
        ld  (tu_hitb), a
        ld  a, TU_WORK
        call map_w1
        ld  hl, TU_DIRTY        ; rows 0, 26, 27 are not shown
        ld  b, 40
tutsh_0:     ld  (hl), 0
        inc hl
        djnz tutsh_0
        ld  hl, TU_DIRTY + 26 * 40
        ld  b, 80
tutsh_00:    ld  (hl), 0
        inc hl
        djnz tutsh_00
        ld  hl, TU_DIRTY + 40
        ld  c, 1
tutsh_row:   ld  b, 0
tutsh_col:   ld  a, (hl)
        or  a
        jr  z, tutsh_nx
        ld  (hl), 0
        push hl
        push bc
        call tu_cell
        pop bc
        pop hl
        ld  a, TU_WORK
        call map_w1
tutsh_nx:    inc hl
        inc b
        ld  a, b
        cp  40
        jr  nz, tutsh_col
        inc c
        ld  a, c
        cp  26
        jr  nz, tutsh_row
        ld  a, (tu_hitp)
        or  a
        call nz, tu_pad_draw
        ld  a, (tu_hitb)
        or  a
        call nz, tu_box_draw
        ret

; B = column, C = the Mega Drive's row (1-25): the cell drawn into the
; clean screen from both planes' words, and copied to the screen shown
; unless a sprite is over it.  Window 1: the work page.
tu_cell:
        ld  (tu_cc), bc
        ld  l, c
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de              ; row * 40
        ld  e, b
        ld  d, 0
        add hl, de
        add hl, hl
        ld  de, TU_NTA
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; A's word
        ld  bc, 2240 - 1
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; B's
        ; B under A - but a B word with priority over an A word without
        ; is the other way round
        bit 7, h
        jr  z, tutce_1
        bit 7, d
        jr  nz, tutce_1
        ex  de, hl
tutce_1:     ld  (tu_top), de
        ; the bottom one
        push hl
        ld  a, h
        call tutce_line
        ld  (tu_hb0), a
        inc a
        ld  (tu_hb1), a
        pop hl
        ld  de, tu_tb0
        call tu_tile
        ; the top one, unless it is the blank tile
        xor a
        ld  (tu_hastop), a
        ld  hl, (tu_top)
        ld  a, h
        and 7
        ld  d, a
        ld  e, l
        push hl
        ld  hl, (tu_blankt)
        or  a
        sbc hl, de
        pop hl
        jr  z, tutce_2
        ld  a, 1
        ld  (tu_hastop), a
        push hl
        ld  a, h
        call tutce_line
        ld  (tu_ht0), a
        inc a
        ld  (tu_ht1), a
        pop hl
        ld  de, tu_tb1
        call tu_tile
tutce_2:     ; where: the port's row C - 1, eight lines of it
        ld  bc, (tu_cc)
        dec c
        ld  l, c
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl              ; its line
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de              ; x 5
        add hl, hl
        add hl, hl
        add hl, hl              ; x 40
        ld  e, b
        ld  d, 0
        add hl, de
        ld  (tu_coff), hl
        ld  a, TU_CLN_A
        call map_w3
        ld  ix, tu_tb0
        call tutce_page
        ld  a, TU_CLN_B
        call map_w3
        ld  ix, tu_tb0 + 1
        call tutce_page
        ; under a sprite: that is drawn again afterwards
        ld  bc, (tu_cc)
        dec c
        call tu_under
        ret c
        ; the cell to the screen shown
        ld  a, TU_CLN_A
        call map_w1
        ld  a, TU_VIS_A
        call map_w3
        call tutce_copy
        ld  a, TU_CLN_B
        call map_w1
        ld  a, TU_VIS_B
        call map_w3
tutce_copy:
        ld  hl, (tu_coff)
        set 6, h                ; the clean screen in window 1
        ld  d, h
        ld  e, l
        set 7, d                ; the one shown in window 3
        ld  b, 8
tutcc_1:     ld  a, (hl)
        ld  (de), a
        set 5, h
        set 5, d
        ld  a, (hl)
        ld  (de), a
        res 5, h
        res 5, d
        ld  a, l
        add a, 40
        ld  l, a
        ld  e, a
        jr  nc, tutcc_2
        inc h
        inc d
tutcc_2:     djnz tutcc_1
        ret
; A = a word's high byte -> A = the high byte of its line's table for an
; even line.
tutce_line:
        rlca
        rlca
        rlca
        rlca                    ; the line (bits 13-14) to bits 1-2
        and 6
        add a, HIGH tu_conv
        ret
; One of the clean screen's pages: IX = the tile rows' first byte (+0 of
; planes 0 or 1, +2 of planes 2 or 3; +32 the top tile).
tutce_page:
        ld  hl, (tu_coff)
        ld  a, h
        or  $C0
        ld  d, a
        ld  e, l
        ld  b, 4
tutcp_1:     ld  a, (tu_hb0)
        ld  h, a
        ld  a, (tu_ht0)
        ld  c, a
        call tutcp_line
        ld  a, (tu_hb1)
        ld  h, a
        ld  a, (tu_ht1)
        ld  c, a
        call tutcp_line
        djnz tutcp_1
        ret
; H = the bottom's table, C = the top's: one line into (DE), (DE + $2000).
tutcp_line:
        push hl
        ld  l, (ix + 0)
        ld  a, (hl)
        ld  (de), a
        ld  l, (ix + 2)
        ld  a, (hl)
        set 5, d
        ld  (de), a
        ld  a, (tu_hastop)
        or  a
        jr  z, tutcl_2
        ld  l, (ix + 34)
        ld  h, HIGH tu_mask
        ld  a, (de)
        and (hl)
        ld  h, c
        or  (hl)
        ld  (de), a
        res 5, d
        ld  l, (ix + 32)
        ld  h, HIGH tu_mask
        ld  a, (de)
        and (hl)
        ld  h, c
        or  (hl)
        ld  (de), a
        jr  tutcl_3
tutcl_2:     res 5, d
tutcl_3:     pop hl
        ld  a, e
        add a, 40
        ld  e, a
        jr  nc, tutcl_4
        inc d
tutcl_4:     inc ix
        inc ix
        inc ix
        inc ix
        ret

; HL = a word -> its tile's 32 bytes at DE (window 0), flipped as it says.
tu_tile:
        ld  (tu_word), hl
        ld  a, h
        and 7
        ld  b, a
        ld  c, l                ; the tile
        ld  a, b
        rrca
        and 3
        add a, TU_TILES
        call map_w1             ; 512 a page
        ld  a, b
        and 1
        ld  h, a
        ld  l, c
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        set 6, h                ; its bytes in window 1
        ld  a, (tu_word + 1)
        ld  c, a
        and $18
        jr  nz, tutti_flip
        ld  bc, 32
        ldir
        ret
tutti_flip:
        bit 4, c                ; upside down: from the last line
        jr  z, tutti_1
        ld  a, l
        add a, 28
        ld  l, a
tutti_1:     ld  b, 8
tutti_row:   bit 3, c
        jr  nz, tutti_h
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        jr  tutti_n
tutti_h:     inc hl                  ; mirrored: the bytes backwards, each
        inc hl                  ; byte's two pixels swapped
        inc hl
        push bc
        ld  b, 4
tutti_h1:    ld  a, (hl)
        dec hl
        push hl
        ld  h, HIGH tu_swap
        ld  l, a
        ld  a, (hl)
        pop hl
        ld  (de), a
        inc de
        djnz tutti_h1
        pop bc
        inc hl
        inc hl
        inc hl
        inc hl
        inc hl
tutti_n:     bit 4, c
        jr  z, tutti_2
        push bc                 ; (a line may end on a 256-byte boundary)
        ld  bc, -8
        add hl, bc
        pop bc
tutti_2:     djnz tutti_row
        ret

; B = column, C = the port's row: carry if the pad or the text box covers
; the cell (and it is noted, to draw that again).
tu_under:
        ld  e, 0
        ld  a, (tu_pshape)
        cp  $FF
        jr  z, tutun_2
        ld  a, (tu_py)
        cp  200
        jr  nc, tutun_2
        ld  hl, tu_prect
        call tutun_in
        jr  nc, tutun_2
        ld  a, 1
        ld  (tu_hitp), a
        ld  hl, tu_pfull
        call tutun_in
        jr  nc, tutun_2
        ld  e, 1
tutun_2:     ld  a, (tu_boxon)
        or  a
        jr  z, tutun_3
        ld  hl, tu_brect
        call tutun_in
        jr  nc, tutun_3
        ld  a, 1
        ld  (tu_hitb), a
        ld  hl, tu_bfull
        call tutun_in
        jr  nc, tutun_3
        ld  e, 1
tutun_3:     ld  a, e
        rrca                    ; carry: all of it under a sprite
        ret
; HL = a rectangle (column, columns end, row, rows end): carry if B, C in.
tutun_in:    ld  a, b
        cp  (hl)
        ccf
        ret nc
        inc hl
        cp  (hl)
        ret nc
        inc hl
        ld  a, c
        cp  (hl)
        ccf
        ret nc
        inc hl
        cp  (hl)
        ret
tu_brect:  DB  TU_BOX_X / 8, (TU_BOX_X + 2 * TU_BOXW + 7) / 8
        DB  TU_BOX_Y / 8, (TU_BOX_Y + TU_BOXH + 7) / 8
tu_bfull:  DB  (TU_BOX_X + 7) / 8, (TU_BOX_X + 2 * TU_BOXW) / 8
        DB  (TU_BOX_Y + 7) / 8, (TU_BOX_Y + TU_BOXH) / 8

; ----------------------------------------------------------- colours

; A = a MAP: the tables that turn a line's pen pairs into plane bytes,
; tu_conv[line * 2 + line parity].
tu_setmap:
        call tu_asset
        ld  de, tu_map
        ld  bc, 256
        ldir
        ld  de, tu_conv
        ld  c, 0                ; line * 2 + parity
tutsm_tbl:   ld  b, 0                ; the left pen
tutsm_hi:    ; left: (line * 16 + pen) * 2 + parity
        ld  a, c
        and 6
        add a, a
        add a, a
        add a, a
        add a, a                ; line * 32
        ld  l, a
        ld  a, b
        add a, a
        add a, l
        ld  l, a
        ld  a, c
        and 1
        add a, l
        ld  l, a
        ld  h, HIGH tu_map
        ld  a, (hl)
        ld  (tu_lb), a
        ; and every right pen with it
        ld  a, c
        and 6
        add a, a
        add a, a
        add a, a
        add a, a
        ld  l, a
        ld  a, c
        and 1
        add a, l
        add a, 128
        ld  l, a                ; right, pen 0
        push bc
        ld  b, 16
tutsm_lo:    ld  a, (tu_lb)
        or  (hl)
        ld  (de), a
        inc de
        inc l
        inc l
        djnz tutsm_lo
        pop bc
        inc b
        ld  a, b
        cp  16
        jr  nz, tutsm_hi
        inc c
        ld  a, c
        cp  8
        jr  nz, tutsm_tbl
        ret

; The group's colours from black, a step every TU_FADE_STEP frames.
tu_fade_in:
        xor a
tutfi_1:     push af
        ld  b, TU_FADE_STEP
        call tu_frames
        pop af
        push af
        call tu_fade_step
        pop af
        inc a
        cp  4
        jr  nz, tutfi_1
        ret
tu_fade_out:
        ld  a, 2
tutfo_1:     push af
        ld  b, TU_FADE_STEP
        call tu_frames
        pop af
        push af
        call tu_fade_step
        pop af
        dec a
        jp  p, tutfo_1
        ld  b, TU_FADE_STEP
        call tu_frames
        ld  hl, tu_black
        jp  vid_palette
; A = the step (0-3: a quarter to all of the colours).
tu_fade_step:
        add a, a
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  a, (tu_group)
        ld  l, a
        ld  h, 0
        ld  bc, tu_fades
        add hl, bc
        ld  a, (hl)
        call tu_asset
        add hl, de
        jp  vid_palette
; B = frames.
tu_frames:
        FCALL snd_idle          ; vid_wait_frame, moving the music on
        djnz tu_frames
        ret

; ------------------------------------------------------------ the pad

; D = y, E = x (the port's), A = the shape: the pad there.  What it
; covered and does not cover now comes back from the clean screen, and
; it is drawn over the planes (tu_pad_draw) - never taken off first, so
; it does not flicker.
tu_pad_set:
        push de
        ld  hl, tu_pshape
        cp  (hl)
        jr  z, tutps_1
        ld  (hl), a
        call tu_pad_shape
tutps_1:     pop de
        ; the old place, where the new one leaves it
        ld  a, (tu_px)
        cp  e
        jr  z, tutps_2
        push de
        call tu_pad_off         ; moved sideways: all of it back
        pop de
        jr  tutps_4
tutps_2:     ld  a, (tu_py)
        cp  d
        jr  z, tutps_4
        jr  c, tutps_3
        ; up: the lines below the new one's end
        push de
        ld  a, d
        add a, TU_PADH
        jr  c, tutps_up9
        ld  c, a                ; from here
        ld  a, (tu_py)
        add a, TU_PADH
        jr  nc, tutps_u1
        ld  a, 255
tutps_u1:    sub c
        jr  c, tutps_up9
        jr  z, tutps_up9
        ld  e, a
        call tutps_strip
tutps_up9:   pop de
        jr  tutps_4
tutps_3:     ; down: the lines above the new one
        push de
        ld  a, (tu_py)
        ld  c, a
        ld  a, d
        sub c
        ld  e, a
        call tutps_strip
        pop de
tutps_4:     ld  a, e
        ld  (tu_px), a
        ld  a, d
        ld  (tu_py), a
        call tu_pad_rect
        jp  tu_pad_draw
; C = the first line, E = lines: the old place's columns back.
tutps_strip:
        ld  a, (tu_px)
        rrca
        rrca
        rrca
        and $1F
        ld  b, a
        ld  d, 2 * TU_PADW / 8 + 1
        jp  tu_restore

; The pad's whole place back from the clean screen.
tu_pad_off:
        ld  a, (tu_px)
        rrca
        rrca
        rrca
        and $1F
        ld  b, a
        ld  a, (tu_py)
        ld  c, a
        ld  d, 2 * TU_PADW / 8 + 1
        ld  e, TU_PADH
        jp  tu_restore

; tu_prect: the cells the pad covers.
tu_pad_rect:
        ld  hl, tu_prect
        ld  a, (tu_px)
        rrca
        rrca
        rrca
        and $1F
        ld  (hl), a
        inc hl
        add a, 2 * TU_PADW / 8 + 1
        cp  41
        jr  c, tutpr_1
        ld  a, 40
tutpr_1:     ld  (hl), a
        inc hl
        ld  a, (tu_py)
        rrca
        rrca
        rrca
        and $1F
        ld  (hl), a
        inc hl
        ld  a, (tu_py)
        add a, TU_PADH + 7
        jr  nc, tutpr_2
        ld  a, 255
tutpr_2:     rrca
        rrca
        rrca
        and $1F
        cp  26
        jr  c, tutpr_3
        ld  a, 25
tutpr_3:     ld  (hl), a
        ; and the cells it covers all of (the rest of a cell it touches is
        ; copied from the clean screen and the pad drawn over it)
        ld  hl, tu_pfull
        ld  a, (tu_px)
        add a, 7
        rrca
        rrca
        rrca
        and $1F
        ld  (hl), a
        inc hl
        ld  a, (tu_px)
        rrca
        rrca
        rrca
        and $1F
        add a, 2 * TU_PADW / 8
        cp  41
        jr  c, tutpf_1
        ld  a, 40
tutpf_1:   ld  (hl), a
        inc hl
        ld  a, (tu_py)
        add a, 7
        rrca
        rrca
        rrca
        and $1F
        ld  (hl), a
        inc hl
        ld  a, (tu_py)
        add a, TU_PADH
        jr  c, tutpf_2
        cp  200
        jr  c, tutpf_3
tutpf_2:   ld  a, 200
tutpf_3:   rrca
        rrca
        rrca
        and $1F
        ld  (hl), a
        ret

; tu_pshape into the pad's work copy: shape 0, and a shape's patch over it.
tu_pad_shape:
        ld  a, TU_PADPG
        call map_w1
        ld  a, TU_PADPG
        call map_w3
        ld  hl, TU_PADBASE
        ld  de, TU_PADWORK
        ld  bc, TU_PADSIZE
        ldir
        ld  a, $FF
        ld  (tu_ovlwho), a      ; the overlay's copy is stale
        ld  a, (tu_pshape)
        or  a
        ret z
        cp  6
        ret nc
        ld  l, a
        ld  h, 0
        ld  de, tu_shapes
        add hl, de
        ld  a, (hl)
        call tu_asset
        ld  a, (hl)
        ld  (tu_sy), a          ; its first line,
        inc hl
        ld  a, (hl)
        ld  (tu_sh), a          ; lines,
        inc hl
        ld  a, (hl)
        ld  (tu_sx), a          ; first pair,
        inc hl
        ld  a, (hl)
        ld  (tu_sw), a          ; pairs
        inc hl
        push hl
        ld  e, a
        ld  a, (tu_sh)
        ld  b, 0
        ld  hl, 0
        ld  d, b
tutpsh_m:    add hl, de
        dec a
        jr  nz, tutpsh_m
        ld  b, h
        ld  c, l
        pop hl
        ld  de, TU_PADTMP + $8000
        call tu_unlz
        ; the patch's lines into the work copy
        ld  a, TU_PADPG
        call map_w1
        ld  a, (tu_sy)
        ld  e, TU_PADW
        call tu_mul8
        ld  a, (tu_sx)
        ld  e, a
        ld  d, 0
        add hl, de
        ld  de, TU_PADWORK
        add hl, de
        ex  de, hl              ; DE = where its first line goes
        ld  hl, TU_PADTMP
        ld  a, (tu_sh)
        ld  b, a
tutpsh_l:    push bc
        push de
        ld  a, (tu_sw)
        ld  c, a
        ld  b, 0
        ldir
        pop de
        ex  de, hl
        ld  bc, TU_PADW
        add hl, bc
        ex  de, hl
        pop bc
        djnz tutpsh_l
        ret

; A * E -> HL.  Clobbers A, B, D.
tu_mul8:
        ld  hl, 0
        ld  d, h
        ld  b, 8
tutmu_1:     add hl, hl
        rlca
        jr  nc, tutmu_2
        add hl, de
tutmu_2:     djnz tutmu_1
        ret

; The pad drawn (if it is shown and on the screen).
tu_pad_draw:
        ld  a, (tu_pshape)
        cp  $FF
        ret z
        ld  a, (tu_py)
        cp  200
        ret nc
        ld  a, (tu_ovlwho)
        cp  1
        jr  z, tutpd_1
        ld  a, TU_PADPG
        call map_w1
        ld  hl, TU_PADWORK
        ld  de, tu_ovl
        ld  bc, TU_PADSIZE
        ldir
        ld  a, 1
        ld  (tu_ovlwho), a
tutpd_1:     ld  a, (tu_px)
        ld  (tu_ox), a
        ld  a, (tu_py)
        ld  (tu_oy), a
        ld  a, TU_PADW
        ld  (tu_ow), a
        ld  a, TU_PADH
        ld  (tu_oh), a
        xor a                   ; palette line 0
        jp  tu_ovl_draw

; D = the steps' move (-3 up, 3 down): tut_op_cursor_up/down - 32 frames
; of 3 lines, the pad where the frames since the start put it.
tu_slide:
        ld  (tu_sd), a
        ld  hl, (frame_count)
        ld  (tu_st), hl
        ld  a, (tu_py)
        ld  (tu_sy0), a
tutsl_1:     ld  hl, (frame_count)
        ld  de, (tu_st)
        or  a
        sbc hl, de
        ld  a, h
        or  a
        jr  nz, tutsl_end
        ld  a, l
        cp  32
        jr  nc, tutsl_end
        call tutsl_at
        jr  tutsl_1
tutsl_end:   ld  a, 32
tutsl_at:    ; A frames: y0 + A * move
        ld  b, a
        ld  a, (tu_sd)
        ld  c, a
        ld  a, (tu_sy0)
        inc b
        dec b
        jr  z, tutsl_2
tutsl_3:     add a, c
        djnz tutsl_3
tutsl_2:     ld  d, a
        ld  a, (tu_py)
        cp  d
        ret z
        ld  a, (tu_px)
        ld  e, a
        ld  a, (tu_pshape)
        jp  tu_pad_set

; ------------------------------------------------------- the text box

; tu_text (a string, $0A starting its second line) in the text box.
tu_box_show:
        ; its frame, its lines blank (textbox_blank), into its work copy
        ld  a, TU_BOXPG
        call map_w3
        ld  a, TA_BOX_PENS
        call tu_asset
        ld  de, TU_BOXWORK + $8000
        ld  bc, TU_BOXW * TU_BOXH
        call tu_unlz
        ; the glyphs (textbox_draw_text $0429FE)
        ld  a, TU_BOXPG
        call map_w1
        ld  hl, tu_text
        ld  de, TU_BOXWORK + 8 * TU_BOXW + 4
tutbs_1:     ld  a, (hl)
        inc hl
        or  a
        jr  z, tutbs_9
        cp  $0A
        jr  nz, tutbs_2
        ld  de, TU_BOXWORK + 16 * TU_BOXW + 4
        jr  tutbs_1
tutbs_2:     push hl
        push de
        sub 32
        jr  c, tutbs_blank
        cp  64
        jr  c, tutbs_3
tutbs_blank: xor a
        jr  tutbs_4
tutbs_3:     ld  l, a
        ld  h, 0
        ld  bc, tu_glyphs
        add hl, bc
        ld  a, (hl)
tutbs_4:     ld  l, a                ; its glyph: 8 lines of 4 bytes
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  bc, TU_FONT
        add hl, bc
        ld  b, 8
tutbs_5:     push bc
        ld  bc, 4
        ldir
        ex  de, hl
        ld  bc, TU_BOXW - 4
        add hl, bc
        ex  de, hl
        pop bc
        djnz tutbs_5
        pop de
        inc de
        inc de
        inc de
        inc de
        pop hl
        jr  tutbs_1
tutbs_9:     ld  a, $FF
        ld  (tu_ovlwho), a
        ld  a, 1
        ld  (tu_boxon), a
        ; fall into tu_box_draw

tu_box_draw:
        ld  a, (tu_boxon)
        or  a
        ret z
        ld  a, (tu_ovlwho)
        cp  2
        jr  z, tutbd_1
        ld  a, TU_BOXPG
        call map_w1
        ld  hl, TU_BOXWORK
        ld  de, tu_ovl
        ld  bc, TU_BOXW * TU_BOXH
        ldir
        ld  a, 2
        ld  (tu_ovlwho), a
tutbd_1:     ld  a, TU_BOX_X
        ld  (tu_ox), a
        ld  a, TU_BOX_Y
        ld  (tu_oy), a
        ld  a, TU_BOXW
        ld  (tu_ow), a
        ld  a, TU_BOXH
        ld  (tu_oh), a
        ld  a, 1                ; palette line 1
        jp  tu_ovl_draw

tu_box_hide:
        ld  a, (tu_boxon)
        or  a
        ret z
        xor a
        ld  (tu_boxon), a
        ld  bc, (TU_BOX_X / 8) * 256 + TU_BOX_Y
        ld  de, ((2 * TU_BOXW + 7) / 8 + 1) * 256 + TU_BOXH
        call tu_restore
        ; the pad, if it was under it
        ld  a, (tu_pshape)
        cp  $FF
        ret z
        ld  a, (tu_py)
        cp  TU_BOX_Y + TU_BOXH
        ret nc
        jp  tu_pad_draw

; ------------------------------------------------------ the screens

; B = column, C = line, D = columns, E = lines: the clean screen's
; rectangle onto the screen shown (cut at line 200 and column 40).
tu_restore:
        ld  a, c
        cp  200
        ret nc
        ld  a, 200
        sub c
        cp  e
        jr  nc, tutre_1
        ld  e, a
tutre_1:     ld  a, 40
        sub b
        ret c
        ret z
        cp  d
        jr  nc, tutre_2
        ld  d, a
tutre_2:     ld  a, e
        or  a
        ret z
        ld  (tu_rde), de
        ld  l, c
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        ld  e, b
        ld  d, 0
        add hl, de
        ld  (tu_roff), hl
        ld  a, TU_CLN_A
        call map_w1
        ld  a, TU_VIS_A
        call map_w3
        call tutre_half
        ld  a, TU_CLN_B
        call map_w1
        ld  a, TU_VIS_B
        call map_w3
tutre_half:
        ld  hl, (tu_roff)
        set 6, h
        call tutre_plane
        ld  hl, (tu_roff)
        ld  a, h
        or  $60
        ld  h, a
tutre_plane:
        ld  de, (tu_rde)
        ld  b, e
tutre_row:   push bc
        push hl
        ld  c, d
        ld  b, 0
        ld  d, h
        set 7, d
        ld  e, l
        ldir
        pop hl
        ld  bc, 40
        add hl, bc
        ld  de, (tu_rde)
        pop bc
        djnz tutre_row
        ret

; A = the palette line: tu_ovl (tu_ow pairs by tu_oh lines) onto the
; screen shown at tu_ox (even), tu_oy, over the clean screen: each pixel
; its pen, or the clean screen's where the pen is 0.
tu_ovl_draw:
        add a, a
        add a, HIGH tu_conv
        ld  (tu_oline), a
        ld  ix, tu_ovl
        ld  a, (tu_oy)
        ld  (tu_orow), a
        ld  a, (tu_oh)
tutod_row:   push af
        ld  a, (tu_orow)
        cp  200
        jr  nc, tutod_out
        push ix
        and 1
        ld  hl, tu_oline
        add a, (hl)
        ld  c, a                ; the table for this line's parity
        ld  a, TU_CLN_A
        call map_w1
        ld  a, TU_VIS_A
        call map_w3
        xor a
        call tutod_page
        pop ix
        push ix
        ld  a, TU_CLN_B
        call map_w1
        ld  a, TU_VIS_B
        call map_w3
        ld  a, 1
        call tutod_page
        pop ix
        ld  a, (tu_ow)
        ld  e, a
        ld  d, 0
        add ix, de
        ld  hl, tu_orow
        inc (hl)
        pop af
        dec a
        jr  nz, tutod_row
        ret
tutod_out:   pop af
        ret
; A = the page (0: pairs of planes 0 and 2, 1: 1 and 3).  IX = the line.
tutod_page:
        ld  b, a
        ld  a, (tu_ox)
        rrca
        and $7F                 ; the first pair's number
        ld  e, a
        xor b
        and 1                   ; this page's first pen pair in the line
        ld  d, a
        add a, e
        ld  e, a                ; ... and its pair number on the screen
        push de
        ld  e, d
        ld  d, 0
        add ix, de
        pop de
        ld  a, (tu_ow)
        sub d
        inc a
        srl a
        ld  b, a                ; pairs on this page
        ; the address: line * 40 + pair / 4, planes 2-3 at + $2000
        push bc
        ld  a, e
        ld  (tu_otmp), a
        ld  a, (tu_orow)
        ld  c, a
        ld  l, c
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, de
        ld  a, (tu_otmp)
        rrca
        rrca
        and $3F
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, h
        or  $C0
        ld  h, a
        ld  a, (tu_otmp)
        and 2
        jr  z, tutdp_a
        set 5, h
tutdp_a:     ex  de, hl
        pop bc
tutod_px:    ld  a, (ix + 0)
        ld  l, a
        ld  h, HIGH tu_mask
        res 7, d
        ld  a, (de)             ; the clean screen
        set 7, d
        and (hl)
        ld  h, c
        or  (hl)
        ld  (de), a
        inc ix
        inc ix
        bit 5, d
        jr  nz, tutod_n
        set 5, d
        djnz tutod_px
        ret
tutod_n:     res 5, d
        inc de
        djnz tutod_px
        ret

; ------------------------------------------------------------ the data

tu_black:       DS 16, $FF

; ---------------------------------------------------------- variables

tu_sn:          DB 0            ; the script playing
tu_pc:          DW 0            ; where in TA_SCRIPTS
tu_mark:        DW 0
tu_count:       DB 0
tu_clock:       DW 0            ; the frame the script's time is at
tu_last:        DB 0            ; the last frame: 0, $FF the plane's end
tu_pic:         DB 0
tu_prec:        DS TU_PIC_SIZE  ; its tu_pictures record
tu_group:       DB 0
tu_blankt:      DW 0
tu_startA:      DW 0            ; the planes' frames: first,
tu_startB:      DW 0
tu_posA:        DW 0            ;   and next
tu_posB:        DW 0
tu_plane:       DB 0
tu_ntneg:       DW 0
tu_lzend:       DW 0
tu_cc:          DW 0            ; the cell being drawn
tu_top:         DW 0
tu_word:        DW 0
tu_hastop:      DB 0
tu_hb0:         DB 0            ; the tables of the bottom's line (even,
tu_hb1:         DB 0            ;   odd) and the top's
tu_ht0:         DB 0
tu_ht1:         DB 0
tu_coff:        DW 0
tu_hitp:        DB 0            ; a cell under the pad was drawn, the box
tu_hitb:        DB 0
tu_pshape:      DB 0            ; the pad's shape ($FF none), x, y
tu_px:          DB 0
tu_py:          DB 0
tu_prect:       DS 4            ; the cells it touches
tu_pfull:       DS 4            ; ... and covers
tu_sd:          DB 0            ; a slide: its move, start, first line
tu_st:          DW 0
tu_sy0:         DB 0
tu_sy:          DB 0            ; a shape's patch
tu_sh:          DB 0
tu_sx:          DB 0
tu_sw:          DB 0
tu_boxon:       DB 0
tu_text:        DS 80
tu_ovlwho:      DB 0            ; in tu_ovl: 1 the pad, 2 the box, $FF -
tu_ox:          DB 0
tu_oy:          DB 0
tu_ow:          DB 0
tu_oh:          DB 0
tu_oline:       DB 0
tu_orow:        DB 0
tu_otmp:        DB 0
tu_rde:         DW 0
tu_roff:        DW 0
tu_lb:          DB 0
tu_lines:       DB 0
tu_tb0:         DS 32           ; the bottom tile, flipped
tu_tb1:         DS 32           ; the top tile

        ALIGN 256
tu_conv:        DS 8 * 256      ; [line * 2 + parity][pen pair]: plane byte
tu_map:         DS 256          ; the MAP they are made from
        INCLUDE "tutorial.inc"  ; tu_mask and tu_swap first, aligned
tu_ovl:         DS TU_PADSIZE   ; the pad's or the text box's pens
