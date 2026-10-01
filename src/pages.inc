; pages.inc - which RAM page holds what.  The authority; .claude/docs/port.md
; explains the windows.
;
; Code banks run in window 0 and all begin with the same stub.  Data pages
; go in windows 1-3.

; ---------------------------------------------------------------- code (W0)
; Logic banks carry the hot tables after the stub (dune.asm LOGIC_BANK);
; drawing banks do not (DRAW_BANK).
PG_MAIN         EQU 8           ; start-up, the battle loop (S1), sound calls
PG_RENDER       EQU 9           ; the battlefield renderer            (draw)
PG_VM           EQU 10          ; the EMC machine and the scripts' bytecode
PG_OBJ          EQU 11          ; S2 pools, references, orders, the map's
                                ; objects and the fog (S8)
PG_MOVE         EQU 12          ; S3 movement, turning, path finding
PG_COMBAT       EQU 13          ; S4 targets, firing, explosions, damage
PG_STRUCT       EQU 14          ; S5/S6 structures, production, economy
PG_HOUSE        EQU 15          ; S1 house loop, S7 teams and AI, S9 the end
PG_UI           EQU 16          ; S10 the battle's controls and panels (draw)
PG_FRONT        EQU 17          ; the front end, mentat, score      (draw)
PG_SCEN         EQU 18          ; S9 loading a mission
PG_TUTOR        EQU 19          ; the Tutorial (draw; front/tutorial.asm)
PG_MOVE2        EQU 20          ; the subsystems' second banks, if they fill one
PG_COMBAT2      EQU 21
PG_STRUCT2      EQU 22
PG_HOUSE2       EQU 23

; ---------------------------------------------------------------- data
PG_UNITS        EQU 24          ; W1: units, houses, teams
PG_WORLD        EQU 25          ; W2: structures, tables, globals, stack
PG_MAP          EQU 26          ; W3 during logic: the four map planes
PG_MAPGROUND    EQU 27          ; mapGround: the icon each square was loaded with
PG_MISSIONS     EQU 28          ; 28-30: the 27 missions (window 1 addresses)
PG_MAPS         EQU 31          ; 31-36: the 27 battlefields (window 1)
PG_TEXT         EQU 37          ; 37-38: briefings and strings (window 1)
PG_SPRDIR       EQU 39          ; the sprite directory (window 3 while the
                                ; renderer lists its sprites; render_data.asm)

PG_ART          EQU 40          ; art pages start here (tools/dune_art.py)
                                ; up to 99: the battlefield and the HUD
PG_RADAR        EQU 99          ; the radar's two pictures (ui/ui.asm)
PG_TUT_DATA     EQU 221         ; 221-223, 0, 4, 6: the Tutorial's tiles,
                                ; frames, scripts (tools/dune_tutorial.py
                                ; TUT_PAGES).  Nothing may sit in 224-255:
                                ; the SPG loaders live there (spg.py)
PG_FRONT_ART    EQU 100         ; 100-121 (and 97, 98, 123): the front
                                ; end's pictures (tools/dune_front.py);
                                ; 124-127 its unpack cache and background
PG_PANEL        EQU 122         ; code: the structure panels (draw bank)
PG_SOUND        EQU 128         ; sound pages start here (tools/dune_sound.py)

; ---------------------------------------------------------- the boot stub
; The SPG starts in page 2 at $8000 (window 2 as the loader leaves it).
PG_BOOT         EQU 2
