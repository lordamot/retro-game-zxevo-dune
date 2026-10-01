; struct/world.inc - the STRUCT subsystem's share of WORLD (window 2):
; only what other banks or the renderer must see.  Budget: 240 bytes.

; What the last struct_build_object(-1/-2) offered (S6), for the build
; panel (UI): by unit type, the type number or $FF, then item 27 the
; upgrade entry ($FFC620-$FFC63B)...
st_unit_list:       DS 27           ; factoryList $FFC620
st_unit_upgrade:    DB $FF          ; factoryUpgradeItem $FFC63B
; ... and the same for a Construction Yard, by structure type, with item
; 19 its upgrade entry ($10 when offered) ($FFC63C-$FFC64F).
st_yard_list:       DS 19           ; yardList $FFC63C
st_yard_upgrade:    DB $FF          ; yardUpgradeItem $FFC64F
st_list_is_yard:    DB 0            ; factoryWindowIsYard $FFC344

; The Starport's offers (ui_starport_fill_grid $008F10), ten records of
; SO_SIZE: the unit type ($FF none), ordered, in stock, the price.
st_SO_TYPE         EQU 0
st_SO_ORDERED      EQU 1
st_SO_STOCK        EQU 2
st_SO_PRICE        EQU 3               ; w
st_SO_SIZE         EQU 5
st_starport_offers:        DS 10 * st_SO_SIZE ; $FFC2D8
st_starport_price_timer:   DW 0            ; $FFBF88: frames until the prices are rolled again
st_starport_index:         DB 0            ; $FFC17C: the Starport the last order came from
st_starport_cargo_pending: DW 0            ; $FFC348: units bought and not yet put down
                                        ; (unit_place takes one off)
st_slab_blocked:        DB 0            ; $FFC258: a 4-Slab's blocked squares, 1-2-4-8 (15: none)

; The structure markers, a byte a structure by its index, for the
; renderer: bits 0-2 its marker flags ($FFC868: 0 power, 1 ready, 2
; repair), bits 4-5 the picture its one marker sprite (+$10) shows - 0
; none, else 1 + the flag that set it last (structs.asm "markers").
st_markers:             DS STRUCT_COUNT
