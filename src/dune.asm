; dune.asm - the whole game, assembled into a 4 MB image of RAM pages.
;
; tools/build_dune.py runs this and then packs the pages it saves into
; build/dune.spg.  Code banks go in window 0 and start with the stub
; (src/stub/stub.asm); data pages are laid out for the window they are
; used in.  .claude/docs/port.md has the map.

        DEVICE ZXSPECTRUM4096
        INCLUDE "evo.inc"
        INCLUDE "pages.inc"
        INCLUDE "records.inc"
        INCLUDE "tbl_equ.inc"
        INCLUDE "art.inc"
        ASSERT PG_ART_NEXT <= PG_RADAR

; FCALL label: call a routine in any code bank (see stub.asm).
    MACRO FCALL _fn_
        call far_call
        DB  $$_fn_
        DW  _fn_
    ENDM
; FJUMP label: go there for good.
    MACRO FJUMP _fn_
        call far_jump
        DB  $$_fn_
        DW  _fn_
    ENDM

; A logic bank: the stub and the hot tables, identical to MAIN's, under a
; module name so their labels do not clash with MAIN's (which are the ones
; everything uses - the addresses are the same).
    MACRO LOGIC_BANK name, page
        SLOT 0
        PAGE page
        MODULE name
        INCLUDE "stub/stub.asm"
        INCLUDE "tbl_hot.inc"
hot_end:
        ENDMODULE
    ENDM
; A drawing bank: the stub only; it may not use the hot tables.
    MACRO DRAW_BANK name, page
        SLOT 0
        PAGE page
        MODULE name
        INCLUDE "stub/stub.asm"
        ENDMODULE
    ENDM

; ----------------------------------------------------------------- WORLD
        SLOT 2
        PAGE PG_WORLD
        INCLUDE "world.asm"

; ----------------------------------------------------------------- boot
        SLOT 2
        PAGE PG_BOOT
        INCLUDE "boot/boot.asm"

; ------------------------------------------------------------ bank MAIN
        SLOT 0
        PAGE PG_MAIN
        INCLUDE "stub/stub.asm"
        INCLUDE "tbl_hot.inc"
hot_end:
        INCLUDE "main/main.asm"
        INCLUDE "tbl_main.inc"
        ASSERT $ <= $4000

; ---------------------------------------------------------- bank RENDER
        DRAW_BANK stub_render, PG_RENDER
        INCLUDE "render/render.asm"
        INCLUDE "render/render_data.asm"
        ASSERT $ <= $4000

; ------------------------------------------------------------- bank VM
        LOGIC_BANK stub_vm, PG_VM
        INCLUDE "vm/emc.asm"
        INCLUDE "vm/functions.asm"
        INCLUDE "scripts.inc"
        ASSERT $ <= $4000

; ------------------------------------------------------------ bank OBJ
        LOGIC_BANK stub_obj, PG_OBJ
        INCLUDE "obj/pools.asm"
        INCLUDE "obj/map.asm"
        INCLUDE "tbl_game1.inc"
        ASSERT $ <= $4000

; ------------------------------------------------------------ bank MOVE
        LOGIC_BANK stub_move, PG_MOVE
        INCLUDE "move/moves.asm"
        ASSERT $ <= $4000

; ---------------------------------------------------------- bank COMBAT
        LOGIC_BANK stub_combat, PG_COMBAT
        INCLUDE "combat/combat.asm"
        ASSERT $ <= $4000

; ------------------------------------------ the subsystems' second banks
        LOGIC_BANK stub_move2, PG_MOVE2
        INCLUDE "move/moves2.asm"
        ASSERT $ <= $4000
        LOGIC_BANK stub_combat2, PG_COMBAT2
        INCLUDE "combat/combat2.asm"
        ASSERT $ <= $4000
        LOGIC_BANK stub_struct2, PG_STRUCT2
        INCLUDE "struct/structs2.asm"
        ASSERT $ <= $4000
        LOGIC_BANK stub_house2, PG_HOUSE2
        INCLUDE "house/houses2.asm"
        ASSERT $ <= $4000

; ---------------------------------------------------------- bank STRUCT
        LOGIC_BANK stub_struct, PG_STRUCT
        INCLUDE "struct/structs.asm"
        INCLUDE "tbl_game3.inc"
        ASSERT $ <= $4000

; ----------------------------------------------------------- bank HOUSE
        LOGIC_BANK stub_house, PG_HOUSE
        INCLUDE "house/houses.asm"
        ASSERT $ <= $4000

; -------------------------------------------------------------- bank UI
        LOGIC_BANK stub_ui, PG_UI
        INCLUDE "ui/ui.asm"
        INCLUDE "tbl_ui.inc"    ; (tbl_radar_icon_colour 256-aligned: rd_colours)
        ASSERT $ <= $4000

; ----------------------------------------------------------- bank FRONT
        DRAW_BANK stub_front, PG_FRONT
        INCLUDE "front/front.asm"
        INCLUDE "tbl_front.inc"
        ASSERT $ <= $4000

; ---------------------------------------------------------- bank TUTOR
        DRAW_BANK stub_tutor, PG_TUTOR
        INCLUDE "front/tutorial.asm"
        ASSERT $ <= $4000

; ---------------------------------------------------------- bank PANEL
        DRAW_BANK stub_panel, PG_PANEL
        INCLUDE "front/panel.asm"
        ASSERT $ <= $4000

; ------------------------------------------------------------ bank SCEN
        LOGIC_BANK stub_scen, PG_SCEN
        INCLUDE "scen/scen.asm"
        INCLUDE "tbl_scen.inc"
        ASSERT $ <= $4000

; -------------------------------------------------------- the data pages
        MMU 1 n, PG_MISSIONS
        ORG $4000
        INCLUDE "missions.inc"
missions_end:
        MMU 1 n, PG_MAPS
        ORG $4000
        INCLUDE "maps.inc"
maps_end:
        MMU 1 n, PG_TEXT
        ORG $4000
        INCLUDE "text.inc"
text_end:

; ---------------------------------------------------------------- output
        INCLUDE "savepages.inc"
