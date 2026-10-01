; render_data.asm - the renderer's own state, kept in its bank.

rf_screen:      DB 0            ; the screen being drawn: 0 or 1
rf_pass:        DB 0            ; 0 pass A, 16 pass B
rf_pal_pending: DB 0            ; render_invalidate: the palette at the swap
rdc_sx:         DB 0            ; the view's cell offset into its first square
rdc_sy:         DB 0
rg_col:         DB 0            ; rf_grid: the view's first map column
rg_on:          DB 0            ;   and how many of its squares are on the map
rg_force:       DB 0            ;   and whether every record is made again
rgo_f:          DB 0            ; rg_orbs: the orb's frame being applied
rgo_f0:         DB 0            ;   and the one each screen's records show
rgo_f1:         DB 0
rf_orbf:        DW 0            ;   -> the one being drawn (rf_select)
rf_rgen0:       DB $FF          ; the radar_gen each screen's copy of the
rf_rgen1:       DB $FF          ;   radar picture was made at
rf_rgenp:       DW 0            ;   -> the one being drawn (rf_select)
rg_touched:     DB 1            ;   a record was made again this pass
rr_cols:        DS GRID_W + 1   ; rf_rect_*: each square across, its columns
rrc_out:        DW 0            ; rf_rect_calc: -> the entry's E_SQ
rrc_w:          DB 0            ;   the columns it covers
rrc_ra:         DB 0            ;   the first row inside the first square * 4
rrc_rb:         DB 0            ;   the last inside the last
rrc_ca:         DB 0            ;   the same across
rrc_cb:         DB 0
rmf_new:        DW 0            ; rms_find: the new entry
rmf_optr:       DW 0            ;   the old list's record it has reached
rmf_orem:       DB 0            ;   and how many are left
rmf_redraw:     DB 0            ;   the matched entry is drawn all the same
rmf_hud:        DB 0            ;   and so is everything above the radar
rms_changed:    DB 0
rsq_mask:       DW 0            ; rf_square: the dirty cells
rsq_x0:         DB 0            ;   the first cell's screen column
rsq_y0:         DB 0            ;   and row
rsq_dst:        DW 0            ;   its screen address
rse_nib:        DS 4            ; rsq_each: each row's cells to draw
rsp_phase:      DB 0            ; rf_sprite
rsp_col:        DB 0
rsp_n:          DB 0
rsp_y:          DB 0
rsp_rows:       DB 0
rsp_w2:         DB 0
rsp_sk:         DW 0
rsp_plane:      DW 0
rsp_yoff:       DW 0
rsp_d:          DB 0
rsp_c0:         DB 0
rsp_opaque:     DB 0
rsp_base:       DW 0
rps_out:        DW 0            ; rf_prep_sprites: the next entry
rps_rec:        DW 0            ;   the end of the sorted records
rps_n:          DB 0            ;   entries so far
rps_limit:      DB 0            ;   where the list stops for the caller
rps_hud_n:      DB 16           ;   what the HUD took last pass, plus two
rps_xlo:        DW 0            ;   the positions that may be in view
rps_xw:         DW 0
rps_ylo:        DW 0
rps_yw:         DW 0
rps_yhb:        DW 0            ;   the high bytes: from, and past the last
rps_xhb:        DW 0
rpu_x:          DW 0
rpu_y:          DW 0
rpu_fy:         DW 0
rpu_lastfy:     DW 0            ; rps_frame: the last key's y
rpu_lock:       DB 0            ;   1: use it again (a turret with its hull)
rpu_line:       DB 0
rpu_layer:      DB 0
rpu_mode:       DB 0
rotor_phase:    DB 0
rf_msk:         DW 0            ; this screen's dirty cells
rf_rec:         DW 0            ; this screen's squares
rf_lastv:       DW 0            ; this screen's rf_last_view
rf_oldp:        DW 0            ; -> rf_old0 or rf_old1
rf_old:         DW 0            ; this screen's sprite list
rf_old0:        DW rf_list0     ; the sprites each screen shows
rf_old1:        DW rf_list1
rf_new:         DW rf_list2     ; the list being made
rf_last_view0:  DW $FFFF, $FFFF ; the view each screen was drawn at
rf_last_view1:  DW $FFFF, $FFFF
rf_home_x:      DW 0            ; the view as the game has it (not shaken)
rf_home_y:      DW 0
rf_shaken:      DB 0            ; this frame is drawn a cell away
rf_shake_dx:    DB 0            ; the shake's way: 0 or 8 each (none yet: 0, 0)
rf_shake_dy:    DB 0
rf_shake_scr:   DB 0            ; the screen drawn shaken
rf_radar_drawn: DB 0            ; the radar's picture is drawn this frame

rf_scrolled:    DB 0            ; this frame copied the other screen (rf_scroll)
rsc_ox:         DW 0            ; rf_scroll: the other screen's view
rsc_oy:         DW 0
rsc_dxp:        DW 0            ;   the move in pixels
rsc_dyp:        DW 0
rsc_dxc:        DB 0            ;   and in cells
rsc_dyc:        DB 0
rsc_dqx:        DB 0            ;   and in squares
rsc_dqy:        DB 0
rsc_src:        DW 0            ;   a plane's copy: from, to, how much
rsc_dst:        DW 0
rsc_len:        DW 0
rsc_k:          DW 0            ;   a record's source, from its own place
rsc_olist:      DW 0            ;   the other screen's sprite list
rsc_pdiff:      DW 0            ;   this one's, from it
rsc_n:          DB 0            ;   its entries
rsc_rect:       DS E_SIZE       ;   the cells the copy left out, as an entry's
rf_radar_rect:  DS E_SIZE        ; the radar's cells, as an entry's
rf_radar_sxy:   DW $FFFF        ;   for this rdc_sx, rdc_sy
rf_msk0:        DS GRID_W * GRID_H * 2, $FF
rf_msk1:        DS GRID_W * GRID_H * 2, $FF
        ALIGN REC_SIZE
rf_rec0:        DS GRID_W * GRID_H * REC_SIZE, $FF
rf_rec1:        DS GRID_W * GRID_H * REC_SIZE, $FF
RF_MAX_SPR      EQU 64
rf_list0:       DS L_SIZE, 0
rf_list1:       DS L_SIZE, 0
rf_list2:       DS L_SIZE, 0

; The sprite directory (tools/dune_art.py) has a page of its own, in window
; 3 while rf_prep_sprites runs (the map is put back for a moment to look
; under the fog).
rd_end:
        SLOT 3
        PAGE PG_SPRDIR
        ORG $C000
        INCLUDE "sprites.inc"
        ASSERT $ > $C000
        SLOT 0
        PAGE PG_RENDER
        ORG rd_end
        ASSERT $$text_end < PG_SPRDIR   ; the words must not grow into it
