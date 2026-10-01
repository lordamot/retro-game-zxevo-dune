; panel.asm - bank PANEL: the battle's structure panels (S10 "The
; panels"): ui_structure_menu $028F38, ui_build_menu $0287D8, the grid's
; order (ui_sort_build_list $028DF6), the info box (ui_build_info_text
; $0276E8) and the Starport (ui_starport_menu $028A14).
;
; The screens are drawn with bank FRONT's library (FCALL fe_*): the panel
; pictures, the 32x24 icons and the items' pictures are tools/dune_front.py
; assets (panel.inc names them).  The Mega Drive shows each item's own
; 96x56 picture in the box; the port keeps them at half size and doubles
; them here (pn_picture), which is what lets all 36 fit.
;
; A panel is modal: the game clock holds and the frames it spends are
; added to the music clock, as the cartridge does.  The caller (UI) calls
; render_invalidate afterwards.

PN_BUILD        EQU 0           ; pn_mode: the Construction Yard's list
PN_UNITS        EQU 1           ; a factory's list
PN_STARPORT     EQU 2
PN_BUTTONS      EQU 3           ; repair and stop only

PN_EMPTY        EQU $80         ; a grid cell with nothing in it
PN_SP_EXIT      EQU $1C         ; the Starport's buttons (ui_starport_menu)
PN_SP_FIX       EQU $1D
PN_SP_STOP      EQU $1E
PN_SP_FIX_OFF   EQU $1F
PN_SP_STOP_OFF  EQU $20

; panel_structure: A = the selected structure's slot.  Opens its panel and
; carries out the choice, by type, as ui_structure_menu does: a
; Construction Yard lists buildings, the factories, Barracks and WOR list
; units, the Starport sells, the rest (the Palace too) offer repair and
; stop; the IX, walls and slabs open nothing.  Only the player's own.
panel_structure:
        call struct_ptr
        ld  (pn_struct), hl
        push hl
        pop ix
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ret nz
        ld  a, (ix + O_TYPE)
        cp  STRUCT_IX
        ret z
        cp  STRUCT_WALL
        ret z
        cp  STRUCT_PALACE
        ret c                   ; the slabs
        ld  a, (timer_game_on)
        ld  (pn_timer), a
        xor a
        ld  (timer_game_on), a
        ld  hl, (frame_count)
        ld  (pn_t0), hl
        call pn_open
        ; the frames spent go to the music clock (so it does not jump)
        ld  hl, (frame_count)
        ld  de, (pn_t0)
        or  a
        sbc hl, de
        ex  de, hl
        ld  hl, (music_frames_left)
        add hl, de
        ld  (music_frames_left), hl
        ld  a, (pn_timer)
        ld  (timer_game_on), a
        jp  map_game

pn_open:
        ld  ix, (pn_struct)
        ; repair allowed while damaged, stop while repairing
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (pn_maxhp), de
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ex  de, hl
        or  a
        sbc hl, de              ; max - hp
        ld  a, 0
        jr  z, pno_1
        jp  m, pno_1
        inc a
pno_1:  ld  (pn_rep), a
        ld  a, (ix + O_FLAGS + 1)
        and 1 << (OF_REPAIRING - 8)
        ld  (pn_can), a
        ; what the house has built, then the lists (struct_build_object -1)
        ld  a, (player_house)
        FCALL house_owned_struct_types
        ld  ix, (pn_struct)
        ld  hl, -1
        FCALL struct_build_object
        ld  ix, (pn_struct)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  z, pn_yard
        cp  STRUCT_STARPORT
        jp  z, pn_starport
        ld  hl, pn_factories
pno_2:  cp  (hl)
        jr  z, pn_factory
        inc hl
        bit 7, (hl)
        jr  z, pno_2
        ; ------------------------------------------ repair and stop only
        ld  a, PN_BUTTONS
        ld  (pn_mode), a
        xor a
        ld  (pn_n), a
        call pn_grid_make
        call pn_menu
        ld  ix, (pn_struct)
        cp  $FE
        jp  z, pn_do_repair
        cp  $FD
        jp  z, pn_stop_repair
        ret
pn_factories:
        DB  3, 4, 5, 7, 10, $FF

; ------------------------------------------------------------ the lists

pn_yard:
        ld  a, PN_BUILD
        ld  (pn_mode), a
        ld  hl, st_yard_list
        ld  b, STRUCT_INFO_COUNT
        ld  a, (st_yard_upgrade)
        ld  c, $13
        call pn_fill
        ld  a, (ix + O_FLAGS2 + 1)      ; building or done: stop allowed
        and $60
        jr  pn_list
pn_factory:
        ld  a, PN_UNITS
        ld  (pn_mode), a
        ld  hl, st_unit_list
        ld  b, 27
        ld  a, (st_unit_upgrade)
        ld  c, $1B
        call pn_fill
        ld  a, (ix + O_FLAGS2 + 1)
        and $40
pn_list:
        ld  b, a
        ld  a, (ix + O_FLAGS2)          ; upgrading
        and 2
        or  b
        ld  hl, pn_can
        or  (hl)
        ld  (hl), a
        call pn_grid_make
        call pn_menu
        ld  (pn_entry), a
        ld  ix, (pn_struct)
        cp  $FE
        jp  z, pn_do_repair
        cp  $FD
        jp  z, pn_do_cancel
        or  a
        ret m                           ; -1: out
        ; an item: repairing stops (struct_marker_clear_bit2)
        res OF_REPAIRING - 8, (ix + O_FLAGS + 1)
        call pn_marker_clear
        ld  a, (pn_entry)
        ld  hl, pn_upg_idx
        cp  (hl)
        jr  z, pn_do_upgrade
        ld  a, (pn_mode)
        cp  PN_BUILD
        jr  nz, pnl_build
        ; a Yard already holding this type keeps it
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, pnl_build
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, pnl_build
        ld  a, (pn_entry)
        cp  (ix + S_OBJECTTYPE)
        ret z
pnl_build:
        ld  a, (pn_entry)
        ld  l, a
        ld  h, 0
        FCALL struct_build_object
        ld  ix, (pn_struct)
        ld  a, h
        or  l
        ld  a, 47                       ; refused
        jr  z, pnl_1
        set 6, (ix + O_FLAGS2 + 1)      ; flags2 bit 14: building
        ld  a, (pn_mode)
        cp  PN_BUILD
        jr  nz, pnl_0
        res 5, (ix + O_FLAGS2 + 1)      ; bit 13: nothing finished
pnl_0:  ld  a, 13
pnl_1:  FCALL snd_effect
        ld  ix, (pn_struct)
        res 4, (ix + O_FLAGS2 + 1)      ; bit 12
        ret

; The upgrade entry: whatever is under way stops, and the upgrade starts
; (upgradeTimeLeft 100, the price paid as it goes).
pn_do_upgrade:
        ld  a, (pn_mode)
        cp  PN_BUILD
        jr  nz, pnu_1
        bit 1, (ix + O_FLAGS2)
        ret nz                          ; the Yard's: not twice
pnu_1:  FCALL struct_cancel_build
        ld  ix, (pn_struct)
        ld  a, (pn_mode)
        cp  PN_BUILD
        ld  a, (ix + O_FLAGS2 + 1)
        jr  nz, pnu_2
        and $9F                         ; bits 13 and 14
        jr  pnu_3
pnu_2:  and $BF                         ; bit 14
pnu_3:  ld  (ix + O_FLAGS2 + 1), a
        res OF_REPAIRING - 8, (ix + O_FLAGS + 1)
        call pn_marker_clear
        ld  ix, (pn_struct)
        set 1, (ix + O_FLAGS2)
        ld  (ix + S_UPGRADETIME), 100
        ld  hl, -3
        FCALL struct_build_object
        ld  ix, (pn_struct)
        ld  a, (pn_upg_val)
        ld  (ix + S_TYPEAFTERUPG), a
        ld  a, 12
        FCALL snd_effect
        ret

pn_do_cancel:
        FCALL struct_cancel_build
        ld  ix, (pn_struct)
        ld  a, (pn_mode)
        cp  PN_BUILD
        ld  a, (ix + O_FLAGS2 + 1)
        jr  nz, pnc_1
        and $9F
        jr  pnc_2
pnc_1:  and $BF
pnc_2:  ld  (ix + O_FLAGS2 + 1), a
pn_stop_repair:
        ld  ix, (pn_struct)
        res OF_REPAIRING - 8, (ix + O_FLAGS + 1)
        ; fall through

; IX = the structure: its repair hammer goes (struct_marker_clear_bit2).
pn_marker_clear:
        ld  a, 2                        ; STRUCT's st_MK_REPAIR
        FCALL struct_marker_clear
        ret

; The repair entry: it starts, and so does the hammer
; (struct_marker_set_bit2, $029152).
pn_do_repair:
        ld  a, (pn_rep)
        or  a
        ret z
        ld  ix, (pn_struct)
        set OF_REPAIRING - 8, (ix + O_FLAGS + 1)
        ld  a, 2
        FCALL struct_marker_set
        ret

; HL = a list by type (the type or $FF), B = its length, A = the upgrade
; entry's value ($FF none), C = the upgrade entry's number: pn_items, the
; offered types sorted by +$20 (the upgrade last), pn_n of them.
pn_fill:
        ld  (pn_upg_val), a
        ld  a, c
        ld  (pn_upg_idx), a
        ld  de, pn_items
        ld  c, 0
pnf_1:  ld  a, (hl)
        cp  $FF
        jr  z, pnf_2
        ld  a, c
        ld  (de), a
        inc de
pnf_2:  inc hl
        inc c
        djnz pnf_1
        ld  a, (pn_upg_val)
        cp  $FF
        jr  z, pnf_3
        ld  a, (pn_upg_idx)
        ld  (de), a
        inc de
pnf_3:  ld  hl, -pn_items
        add hl, de
        ld  a, l
        ld  (pn_n), a
        ; the keys
        or  a
        ret z
        ld  b, a
        ld  hl, pn_items
        ld  de, pn_keys
pnf_k:  push bc
        push hl
        push de
        ld  a, (hl)
        call pn_key
        pop de
        ld  (de), a
        inc de
        pop hl
        inc hl
        pop bc
        djnz pnf_k
        ; bubble sort, as $028DF6
pnf_pass:
        ld  a, (pn_n)
        dec a
        ret z
        ld  b, a
        ld  hl, pn_keys
        ld  de, pn_items
        ld  c, 0                        ; swapped?
pnf_cmp:
        ld  a, (hl)
        inc hl
        cp  (hl)
        jr  c, pnf_ok
        jr  z, pnf_ok
        ; swap the keys and the items
        push bc
        ld  b, (hl)
        ld  (hl), a
        dec hl
        ld  (hl), b
        inc hl
        push hl
        ex  de, hl              ; the items i and i + 1
        ld  a, (hl)
        inc hl
        ld  b, (hl)
        ld  (hl), a
        dec hl
        ld  (hl), b
        ex  de, hl
        pop hl
        pop bc
        ld  c, 1
pnf_ok: inc de
        djnz pnf_cmp
        ld  a, c
        or  a
        jr  nz, pnf_pass
        ret

; A = an entry -> A = its sort key (+$20 of its type's record; the
; upgrade $7F).
pn_key:
        ld  hl, pn_upg_idx
        cp  (hl)
        ld  b, $7F
        jr  z, pnk_1
        ld  b, a
        ld  a, (pn_mode)
        cp  PN_BUILD
        ld  a, b
        jr  nz, pnk_u
        call struct_info
        ld  de, SI_sortPriority
        jr  pnk_2
pnk_u:  call unit_info
        ld  de, UI_sortPriority
pnk_2:  add hl, de
        ld  b, (hl)
pnk_1:  ld  a, b
        ret

; pn_grid: the three buttons (-1, repair -2 or -4, stop -3 or -5), then
; the first fifteen items, the rest empty.
pn_grid_make:
        ld  hl, pn_grid
        ld  (hl), $FF
        inc hl
        ld  a, (pn_rep)
        or  a
        ld  a, $FE
        jr  nz, pgm_1
        ld  a, $FC
pgm_1:  ld  (hl), a
        inc hl
        ld  a, (pn_can)
        or  a
        ld  a, $FD
        jr  nz, pgm_2
        ld  a, $FB
pgm_2:  ld  (hl), a
        inc hl
        ld  de, pn_items
        ld  a, (pn_n)
        ld  c, a
        ld  b, 15
pgm_3:  ld  a, c
        or  a
        ld  a, PN_EMPTY
        jr  z, pgm_4
        ld  a, (de)
        inc de
        dec c
pgm_4:  ld  (hl), a
        inc hl
        djnz pgm_3
        ld  a, 18
        ld  (pn_cells), a
        ret

; ---------------------------------------------------------- the Starport

pn_starport:
        ld  a, PN_STARPORT
        ld  (pn_mode), a
        FCALL struct_starport_fill
        ld  hl, pn_grid
        ld  (hl), PN_SP_EXIT
        inc hl
        ld  a, (pn_rep)
        or  a
        ld  a, PN_SP_FIX
        jr  nz, pns_1
        ld  a, PN_SP_FIX_OFF
pns_1:  ld  (hl), a
        inc hl
        ld  a, (pn_can)
        or  a
        ld  a, PN_SP_STOP
        jr  nz, pns_2
        ld  a, PN_SP_STOP_OFF
pns_2:  ld  (hl), a
        inc hl
        ld  de, st_starport_offers
        ld  b, 9
pns_3:  ld  a, (de)                 ; the offer's unit type, $FF none
        cp  $FF
        jr  nz, pns_4
        ld  a, PN_EMPTY
pns_4:  ld  (hl), a
        inc hl
        push hl
        ld  hl, st_SO_SIZE
        add hl, de
        ex  de, hl
        pop hl
        djnz pns_3
        ld  a, 12
        ld  (pn_cells), a
        call pn_menu_draw
pns_loop:
        call pn_menu_loop
        push af
        call map_game           ; as pn_menu: the game's pages back
        pop af
        ld  ix, (pn_struct)
        cp  PN_SP_EXIT
        jp  z, pns_close
        cp  PN_SP_FIX
        jr  nz, pns_5
        call pn_do_repair
        jp  pns_close
pns_5:  cp  PN_SP_STOP
        jr  nz, pns_6
        call pn_stop_repair
        jp  pns_close
pns_6:  cp  PN_SP_FIX_OFF
        jp  nc, pns_buzz
        ; an offer: not while the Starport is busy or a Frigate comes
        ld  (pn_entry), a
        bit 0, (ix + O_FLAGS2 + 1)
        jr  nz, pns_buzz
        ld  a, (frigate_coming)
        cp  $FF
        jr  nz, pns_buzz
        call pn_offer_of
        jr  z, pns_buzz
        ; the stock, the 'Thopter's air slot, the credits
        ld  a, (iy + st_SO_STOCK)
        or  a
        jr  z, pns_buzz
        jp  m, pns_buzz
        ld  a, (pn_entry)
        cp  1
        jr  nz, pns_7
        ld  a, (air_slot_free)
        or  a
        jr  z, pns_buzz
pns_7:  call pn_credits_ptr         ; HL -> the player's credits
        ld  e, (iy + st_SO_PRICE)
        ld  d, (iy + st_SO_PRICE + 1)
        ; credits (32 bits) >= price?
        inc hl
        inc hl
        ld  a, (hl)
        inc hl
        or  (hl)
        dec hl
        dec hl
        dec hl
        jr  nz, pns_buy
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        or  a
        sbc hl, de
        jr  c, pns_buzz
pns_buy:
        inc (iy + st_SO_ORDERED)
        dec (iy + st_SO_STOCK)
        ; the credits: the house's, and the counter's (never below 0)
        call pn_credits_ptr
        call pn_sub32
        ld  hl, credits_shown
        ld  a, (hl)
        sub e
        inc hl
        ld  a, (hl)
        sbc a, d
        inc hl
        ld  a, (hl)
        sbc a, 0
        inc hl
        ld  a, (hl)
        sbc a, 0
        ld  hl, credits_shown
        jr  c, pns_zero
        call pn_sub32
        jr  pns_8
pns_zero:
        xor a
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
        inc hl
        ld  (hl), a
pns_8:  ld  ix, (pn_struct)
        ld  hl, 1                   ; the order goes
        FCALL struct_build_object
        jr  pns_close
pns_buzz:
        ld  a, 47
        FCALL snd_effect
        jp  pns_loop
pns_close:
        ld  a, 38
        FCALL snd_effect
        FCALL fe_fade_out_cur
        ret

; HL -> 4 bytes, DE = what to take off them.
pn_sub32:
        ld  a, (hl)
        sub e
        ld  (hl), a
        inc hl
        ld  a, (hl)
        sbc a, d
        ld  (hl), a
        inc hl
        ld  a, (hl)
        sbc a, 0
        ld  (hl), a
        inc hl
        ld  a, (hl)
        sbc a, 0
        ld  (hl), a
        ret

; -> HL = the player's credits (house record, window 1 = UNITS).
pn_credits_ptr:
        push de
        call map_game
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        pop de
        ret

; pn_entry = a unit type -> IY = its offer, NZ; Z if none.
pn_offer_of:
        ld  iy, st_starport_offers
        ld  b, 10
pof_1:  ld  a, (iy + st_SO_TYPE)
        ld  hl, pn_entry
        cp  (hl)
        jr  z, pof_2
        ld  de, st_SO_SIZE
        add iy, de
        djnz pof_1
        xor a
        ret
pof_2:  or  1
        ret

; =============================================================== the menu

; The panel on the screen and its loop: -> A = the entry taken (the
; build panel closes with it; the Starport's caller decides).
pn_menu:
        call pn_menu_draw
        call pn_menu_loop
        push af
        ld  a, 38
        FCALL snd_effect
        FCALL fe_fade_out_cur
        ; the fe_ library and pn_picture leave the front end's pages in
        ; windows 1 and 3 (front.asm): the caller's struct_build_object
        ; wants the units and the map there, or a factory's item is
        ; refused (unit_spawn finds no pool in a picture cache)
        call map_game
        pop af
        ret

pn_menu_draw:
        ld  a, FA_PAL_PANEL
        FCALL fe_prepare
        ld  a, (pn_mode)
        cp  PN_STARPORT
        ld  a, FA_BUILD_PANEL
        jr  nz, pmd_1
        ld  a, FA_STARPORT_PANEL
pmd_1:  FCALL fe_pic
        ; the grid's icons
        xor a
        ld  (pn_k), a
pmd_2:  ld  a, (pn_k)
        call pn_grid_at
        call pn_icon_of
        cp  $FF
        jr  z, pmd_3
        push af
        ld  a, (pn_k)
        call pn_cell_pos
        pop af
        FCALL fe_pic_at
pmd_3:  ld  hl, pn_k
        inc (hl)
        ld  a, (pn_cells)
        cp  (hl)
        jr  nz, pmd_2
        call pn_show_credits
        xor a
        ld  (pn_k), a
        call pn_grid_at
        call pn_info
        FCALL fe_begin
        jp  pad_take

; -> A = the entry taken with A (the disabled ones buzz and stay).
pn_menu_loop:
        ld  a, (pn_k)
        call pn_cell_pos
        ld  a, (pn_mode)
        cp  PN_STARPORT
        ld  a, FA_BUILD_MARKER
        jr  nz, pml_1
        ld  a, FA_STARPORT_MARKER
pml_1:  FCALL fe_q_spr
        FCALL fe_frame
        call pad_take
        or  a
        jr  z, pn_menu_loop
        ld  b, a
        and PADM_A
        jr  nz, pml_take
        ld  a, (pn_k)
        ld  c, a
        bit 0, b                ; up
        jr  z, pml_2
        sub 3
        jr  c, pn_menu_loop
        jr  pml_to
pml_2:  bit 1, b                ; down
        jr  z, pml_3
        add a, 3
        ld  hl, pn_cells
        cp  (hl)
        jr  nc, pn_menu_loop
        jr  pml_to
pml_3:  call pn_mod3
        ld  d, a                ; the column
        ld  a, c
        bit 2, b                ; left
        jr  z, pml_4
        inc d
        dec d
        jr  z, pn_menu_loop
        dec a
        jr  pml_to
pml_4:  bit 3, b                ; right
        jr  z, pn_menu_loop
        ld  e, a
        ld  a, d
        cp  2
        jr  z, pn_menu_loop
        ld  a, e
        inc a
pml_to: ; only onto a cell that holds something
        ld  e, a
        call pn_grid_at
        cp  PN_EMPTY
        jr  z, pn_menu_loop
        ld  a, e
        ld  (pn_k), a
        call pn_grid_at
        call pn_info
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        jr  pn_menu_loop
pml_take:
        ld  a, (pn_k)
        call pn_grid_at
        ld  (pn_entry), a
        ld  a, (pn_mode)
        cp  PN_STARPORT
        ld  a, (pn_entry)
        ret z                   ; the Starport's caller sorts it out
        cp  $FC
        jr  z, pml_buzz         ; repair while undamaged
        cp  $FB
        jr  z, pml_buzz         ; stop with nothing under way
        ; a Carryall or 'Thopter from a Hi-Tech needs the air slot
        cp  2
        ret nc
        ld  a, (pn_mode)
        cp  PN_UNITS
        ld  a, (pn_entry)
        ret nz
        ld  ix, (pn_struct)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HITECH
        ld  a, (pn_entry)
        ret nz
        ld  a, (air_slot_free)
        or  a
        ld  a, (pn_entry)
        ret nz
pml_buzz:
        ld  a, 47
        FCALL snd_effect
        jp  pn_menu_loop

; A -> A mod 3.
pn_mod3:
        sub 3
        jr  nc, pn_mod3
        add a, 3
        ret

; A = a cell -> A = its entry.
pn_grid_at:
        ld  hl, pn_grid
        add a, l
        ld  l, a
        jr  nc, pga_1
        inc h
pga_1:  ld  a, (hl)
        ret

; A = a cell -> B = its column, C = its y (32x24 cells from 32,48).
pn_cell_pos:
        ld  c, 48
pcp_1:  cp  3
        jr  c, pcp_2
        sub 3
        push af
        ld  a, c
        add a, 24
        ld  c, a
        pop af
        jr  pcp_1
pcp_2:  add a, a
        add a, a
        add a, 4
        ld  b, a
        ret

; A = an entry -> A = the FA_ of its icon, $FF none.
pn_icon_of:
        ld  b, a
        ld  a, (pn_mode)
        cp  PN_STARPORT
        ld  a, b
        jr  nz, pio_list
        cp  PN_EMPTY
        jr  z, pio_none
        cp  PN_SP_EXIT
        jr  c, pio_unit
        sub PN_SP_EXIT          ; 0 exit, 1 fix, 2 stop, 3 fix off, 4 stop off
        jr  pio_button
pio_list:
        cp  PN_EMPTY
        jr  z, pio_none
        bit 7, a
        jr  z, pio_item
        cpl                     ; -1 -> 0 ... -5 -> 4
pio_button:
        ld  hl, pn_buttons
        jr  pio_at
pio_item:
        ld  hl, pn_upg_idx
        cp  (hl)
        jr  nz, pio_1
        ld  ix, (pn_struct)     ; the upgrade: the structure's own icon
        ld  a, (ix + O_TYPE)
        ld  hl, pn_icon_s
        jr  pio_at
pio_1:  ld  hl, pn_icon_s
        ld  b, a
        ld  a, (pn_mode)
        cp  PN_BUILD
        ld  a, b
        jr  z, pio_at
pio_unit:
        ld  hl, pn_icon_u
pio_at: add a, l
        ld  l, a
        jr  nc, pio_2
        inc h
pio_2:  ld  a, (hl)
        ret
pio_none:
        ld  a, $FF
        ret

; ------------------------------------------------------------- the info

; A = the entry under the cursor: the picture box and the info box (name
; centred in 12 columns at x 176, y 104; three figures right-aligned to x
; 255 at y 128, 160, 192) - ui_build_info_text $0276E8 and
; ui_starport_info_text $02793C.
pn_info:
        ld  (pn_ie), a
        ; clear the words
        xor a
        ld  bc, 22 * 256 + 104
        ld  de, 12 * 256 + 8
        FCALL fe_fill
        ld  c, 128
        call pni_clear
        ld  c, 160
        call pni_clear
        ld  c, 192
        call pni_clear
        ld  a, FA_FONT_MENU
        ld  d, PN_PANEL_WHITE
        ld  e, d
        ld  c, 0
        FCALL fe_ink
        ld  a, (pn_mode)
        cp  PN_STARPORT
        jp  z, pni_starport
        ; the build panel
        ld  a, (pn_ie)
        bit 7, a
        jp  nz, pni_own         ; a button: the structure's own picture
        ld  hl, pn_upg_idx
        cp  (hl)
        jr  z, pni_upgrade
        ld  a, (pn_mode)
        cp  PN_BUILD
        jr  nz, pni_unit
        ; a structure: cost, -power, hit points
        ld  a, (pn_ie)
        ld  hl, pn_item_s
        call pni_picture
        ld  a, (pn_ie)
        ld  hl, txt_struct_info_name
        ld  c, $$txt_struct_info_name
        call pni_name
        ld  a, (pn_ie)
        call struct_info
        push hl
        ld  de, SI_buildCredits
        call pni_word
        ld  c, 128
        call pn_figure
        pop hl
        push hl
        ld  de, SI_powerUsage
        call pni_word
        ex  de, hl
        ld  hl, 0
        or  a
        sbc hl, de
        ld  c, 160
        call pn_figure
        pop hl
        ld  de, SI_hitpoints
        call pni_word
        ld  c, 192
        jp  pn_figure
pni_unit:
        ld  a, (pn_ie)
        ld  hl, pn_item_u
        call pni_picture
        ld  a, (pn_ie)
        call pni_unit_words
        ret
pni_upgrade:
        call pni_own
        ld  hl, txt_ui_build_upgrade
        ld  a, $$txt_ui_build_upgrade | $80
        ld  bc, 22 * 256 + 104
        FCALL fe_str_at
        ld  ix, (pn_struct)     ; half the structure's price
        ld  a, (ix + O_TYPE)
        call struct_info
        ld  de, SI_buildCredits
        call pni_word
        srl h
        rr  l
        ld  c, 128
        jp  pn_figure
pni_own:
        ld  ix, (pn_struct)
        ld  a, (ix + O_TYPE)
        ld  hl, pn_item_s
        jp  pni_picture
pni_starport:
        ld  a, (pn_ie)
        cp  PN_SP_EXIT
        jr  nc, pni_own
        ld  hl, pn_item_u
        call pni_picture
        ld  a, (pn_ie)
        ld  (pn_entry), a
        call pn_offer_of
        ret z
        ld  a, (iy + st_SO_STOCK)
        or  a
        jr  nz, pnis_1
        ld  hl, txt_ui_starport_out_of_stock
        ld  a, $$txt_ui_starport_out_of_stock | $80
        ld  bc, 22 * 256 + 104
        FCALL fe_str_at
        jr  pnis_2
pnis_1: ld  a, (pn_ie)
        ld  hl, txt_unit_info_name
        ld  c, $$txt_unit_info_name
        call pni_name
pnis_2: call pn_offer_of
        ld  l, (iy + st_SO_PRICE)
        ld  h, (iy + st_SO_PRICE + 1)
        ld  c, 128
        call pn_figure
        ld  a, (pn_ie)
        call unit_info
        push hl
        jr  pnu_rest
; A = a unit type: its name, cost, damage (+$54), hit points.
pni_unit_words:
        push af
        ld  hl, txt_unit_info_name
        ld  c, $$txt_unit_info_name
        call pni_name
        pop af
        call unit_info
        push hl
        ld  de, UI_buildCredits
        call pni_word
        ld  c, 128
        call pn_figure
pnu_rest:
        pop hl
        push hl
        ld  de, UI_damage
        call pni_word
        ld  c, 160
        call pn_figure
        pop hl
        ld  de, UI_hitpoints
        call pni_word
        ld  c, 192
        jp  pn_figure

pni_clear:
        xor a
        ld  b, 24
        ld  de, 8 * 256 + 8
        FCALL fe_fill
        ret

; HL = a record, DE = an offset -> HL = the word there.
pni_word:
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ret

; HL = a txt_ group's index table, C = its page, A = the entry: the name,
; centred.
pni_name:
        FCALL fe_txt_addr
        ld  a, c
        or  $80
        ld  bc, 22 * 256 + 104
        FCALL fe_str_at
        ret

; HL = a table of FA_ pictures, A = the type: that picture in the box.
pni_picture:
        add a, l
        ld  l, a
        jr  nc, pnp_1
        inc h
pnp_1:  ld  a, (hl)
        jp  pn_picture

; HL = a figure (signed), C = y: right-aligned to x 255 ('%8.1d').
pn_figure:
        ld  a, h
        or  a
        jp  p, pnf_pos
        push bc
        ex  de, hl
        ld  hl, 0
        or  a
        sbc hl, de              ; its size
        push hl
        call pn_digits          ; A = how many digits
        ld  b, a
        ld  a, 31
        sub b
        ld  b, a                ; the minus in front of them
        pop hl
        pop de
        push hl
        ld  c, e
        push bc
        ld  a, '-'
        FCALL fe_char_at
        pop bc
        pop hl
pnf_pos:
        ld  a, 5
        ld  b, 27
        FCALL fe_num_at
        ret

; HL -> A = how many decimal digits (1-5).
pn_digits:
        ld  a, 1
        ld  de, 10
        call pnd_1
        ld  de, 100
        call pnd_1
        ld  de, 1000
        call pnd_1
        ld  de, 10000
pnd_1:  push hl
        or  a
        sbc hl, de
        pop hl
        ret c
        inc a
        ret

; The player's credits in the box at the top right (x 256-295, y 16).
pn_show_credits:
        ld  a, FA_FONT_MENU
        ld  d, PN_PANEL_WHITE
        ld  e, d
        ld  c, 0
        FCALL fe_ink
        xor a
        ld  bc, 31 * 256 + 16
        ld  de, 6 * 256 + 8
        FCALL fe_fill
        call pn_credits_ptr
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        ld  a, 5
        ld  bc, 32 * 256 + 16
        FCALL fe_num_at
        ret

; ---------------------------------------------------------- the picture

; A = an item's half-size picture (FA_, $FF none): doubled into the box
; (96x56 at 160,40).  Its 48x28 unpack into FRONT's cache; the four
; planes are copied here (both cache pages are needed at once) and each
; pixel written twice across and each row twice down.
pn_picture:
        cp  $FF
        jr  nz, pnp_draw
        xor a
        ld  bc, 20 * 256 + 40
        ld  de, 12 * 256 + 56
        FCALL fe_fill
        ret
pnp_draw:
        FCALL fe_unpack
        ld  a, PG_FE_CACHE_A
        call map_w1
        ld  hl, $4000
        ld  de, pn_src
        ld  bc, 168
        ldir                    ; plane 0
        ld  hl, $6000
        ld  bc, 168
        ldir                    ; plane 2
        ld  a, PG_FE_CACHE_B
        call map_w1
        ld  hl, $4000
        ld  bc, 168
        ldir                    ; plane 1
        ld  hl, $6000
        ld  bc, 168
        ldir                    ; plane 3
        ; the background's rows from (160, 40)
        ld  a, PG_FE_BG_A
        call map_w3
        ld  ix, pn_src          ; planes 0 and 2 from pixels 0, 1 / 4, 5
        ld  de, $C000 + 40 * 40 + 20
        ld  h, HIGH pn_dupl
        call pn_dbl
        ld  ix, pn_src + 336    ; plane 2: pixels 2, 3 / 6, 7
        ld  de, $E000 + 40 * 40 + 20
        ld  h, HIGH pn_dupl
        call pn_dbl
        ld  a, PG_FE_BG_B
        call map_w3
        ld  ix, pn_src
        ld  de, $C000 + 40 * 40 + 20
        ld  h, HIGH pn_dupr
        call pn_dbl
        ld  ix, pn_src + 336
        ld  de, $E000 + 40 * 40 + 20
        ld  h, HIGH pn_dupr
        call pn_dbl
        ld  bc, 20 * 256 + 40
        ld  de, 12 * 256 + 56
        FCALL fe_mark_both
        ret

; IX = a source plane's rows (6 bytes, 28 rows; the plane holding the
; next four pixels 168 bytes on), DE = the destination, H = the table
; (left or right pixel doubled): 56 rows of 12 bytes.
pn_dbl:
        ld  c, 28
pdb_row:
        ld  b, 2
pdb_twice:
        push bc
        push ix
        push de
        push ix
        pop iy
        push de
        ld  de, 168
        add iy, de
        pop de
        ld  b, 6
pdb_col:
        ld  l, (ix + 0)
        ld  a, (hl)
        ld  (de), a
        inc de
        ld  l, (iy + 0)
        ld  a, (hl)
        ld  (de), a
        inc de
        inc ix
        inc iy
        djnz pdb_col
        pop de
        ld  a, e
        add a, 40
        ld  e, a
        jr  nc, pdb_1
        inc d
pdb_1:  pop ix
        pop bc
        djnz pdb_twice
        push de
        ld  de, 6
        add ix, de
        pop de
        dec c
        jr  nz, pdb_row
        ret

; ------------------------------------------------------------ the data

        INCLUDE "panel.inc"

pn_struct:      DW 0
pn_timer:       DB 0
pn_t0:          DW 0
pn_maxhp:       DW 0
pn_rep:         DB 0
pn_can:         DB 0
pn_mode:        DB 0
pn_entry:       DB 0
pn_ie:          DB 0
pn_upg_val:     DB $FF
pn_upg_idx:     DB $FF
pn_n:           DB 0
pn_k:           DB 0
pn_cells:       DB 18
pn_items:       DS 32
pn_keys:        DS 32
pn_grid:        DS 18
pn_src:         DS 4 * 168
