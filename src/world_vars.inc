; world_vars.inc - the game's globals, in page WORLD.  Named as the specs
; name them (S1-S10); the Mega Drive address is in the comment.

STACK_SIZE      EQU 256         ; measured: 68 bytes at most in 20000-frame
                                ; battles and the front end (the pool of
                                ; explosions, fx_list, has the rest)

; --------------------------------------------------------- the view
; The logic says where the view is; the renderer (render.asm) reads the
; map through it, into each screen's own copy of the view's squares.
view_x:         DW 0            ; the view's top-left in map pixels, a multiple of 8
view_y:         DW 0

; --------------------------------------------------------- core's own
map_scale:      DB 0            ; S3 mapScale $FFC068: 0 the 64 x 64 map, 1 32 x 32
player_house:   DB 0            ; S9 playerHouseID $FFC274
ref_pos:        DS 4            ; ref_square's scratch position
atn_dx:         DW 0            ; tile_direction's scratch
atn_dy:         DW 0
atn_q:          DB 0
atn_d4:         DB 0
d24_lo:         DB 0

; --------------------------------------------------------- the pools (S2)
; Cleared by pools_reset from here to pool_vars_end.
pool_vars_start:
unit_find:      DS UNIT_COUNT       ; unitFindArray $FFDCC0: slots in use, in order made
unit_find_count: DB 0               ; $FFDCBC
struct_find:    DS STRUCT_COUNT     ; structureFindArray $FFD31C
struct_find_count: DB 0             ; $FFD318
team_find:      DS TEAM_COUNT       ; teamFindArray $FFDC60
team_find_count: DB 0
house_find:     DS HOUSE_COUNT      ; houseFindArray $FFDC0C
house_find_count: DB 0
unit_lside:     DS UNIT_COUNT       ; the side lists: 0 the player's, 1 the rest, $FF none
unit_lprev:     DS UNIT_COUNT
unit_lnext:     DS UNIT_COUNT
unit_head:      DS 2
struct_lside:   DS STRUCT_COUNT
struct_lprev:   DS STRUCT_COUNT
struct_lnext:   DS STRUCT_COUNT
struct_head:    DS 2
unit_type_count: DS 5 * 32          ; unitTypeCount[house][type] $FFBDFC
struct_type_count: DS 5 * 32        ; structTypeCount $FF7C9C
air_slot_free:  DB 0                ; $FFC728
ground_slots_full: DB 0             ; $FFC72C
struct_slots_free: DB 0             ; $FFBEA2
validate_strict: DB 0               ; validateStrictIfZero $FFC148: nonzero lets searches
                                    ; see objects off the map and lifts the unit cap
frigate_coming: DB 0                ; $FFC260: the Frigate on its way, a unit slot or $FF
pool_vars_end:

; the OBJ bank's scratch
uc_slot:        DB 0
uc_type:        DB 0
uc_house:       DB 0
ll_desc:        DW 0
ll_list:        DB 0
ll_slot:        DB 0
ll_slot2:       DB 0
ll_other:       DB 0
ll_prev:        DB 0
ov_ref:         DW 0
udr_ref:        DW 0

; --------------------------------------------------- shared game state
claim_pos:      DS 4            ; S3 claimPosition $FFC610: unit_update_map works here while set
arg_pos:        DS 4            ; a position handed to a routine in another bank (a
                                ; bank's own scratch is out of sight once it far-calls)

; ------------------------------------------------ the scenario (S9, S4, S5)
; Cleared by scen_reset_state from here to scen_vars_end.
scen_vars_start:
scenario_id:    DB 0            ; $FFC04C the mission, 1-9
campaign_id:    DB 0            ; $FFC050 scenarioID - 1
enemy_house:    DB 0            ; $FFC27C the last computer house the file names
win_flags:      DB 0            ; $FFC060 key 8 (the PC's WinFlags: "is it over?")
lose_flags:     DB 0            ; $FFC062 key 7 (the PC's LoseFlags: "did we win?")
map_seed:       DB 0            ; $FFC064
cursor_pos:     DW 0            ; $FFC244 a square
tactical_pos:   DW 0            ; $FFC238 the view's top-left square
score:          DW 0            ; $FFC05E
killed_allied:  DW 0            ; $FFC096
killed_enemy:   DW 0
destroyed_allied: DW 0
destroyed_enemy: DW 0
harvested_allied: DW 0          ; $FFC09E
harvested_enemy: DW 0
reinforcements: DS 16 * 10      ; $FFC0A2: unit (w), where (w), time left (w),
                                ; time between (w), repeat (w)
starport_available: DS 27 * 2   ; $FFC2A0 per unit type: <0 never, 0 sold out
credits_no_silo: DW 0           ; $FFC054 playerCreditsNoSilo, 32 bits
                DW 0            ;   (the high word)
mission_start_time: DS 4        ; $FFC5A4
structs_player: DB 0            ; $FFDBEE the player's structures, counted
structs_other:  DB 0            ; $FFDBEC every other structure
level_over:     DB 0            ; $FFBE9C
scen_vars_end:

; ------------------------------------------------------------- the loop (S1)
game_house:     DB 1            ; the campaign being played (main.asm)
game_mission:   DB 1
battle_request: DB 0            ; set in a battle: 1 again, 2 title, 3 load game_*
pass_count:     DW 0            ; battle passes run (tools/verify_build.py)
frame_seen:     DW 0            ; $FFE008 frameCount at the last pass
frames_this_pass: DW 0          ; $FFFFFE
loop_d3:        DB 0            ; the rotating loop's counter (d3 in the cartridge)
playtester:     DB 0            ; $FFC018 bit 0: the player's side takes no damage
unit_selected:  DB $FF          ; $FFC25C the player's selected unit, a slot or $FF
struct_selected: DB $FF         ; $FFC578 the selected structure, a slot or $FF
cursor_x:       DW 160          ; the battle cursor, screen pixels
cursor_y:       DW 100
cursor_speed:   DW 0            ; 8.8 pixels a frame ($FFBF40)
cursor_frac:    DB 0
; placing a finished building (ui/ui.asm; drawn by the renderer)
special_armed:  DB 0            ; $FFDC4C the player's Palace weapon is armed
place_active:   DB 0            ; the player's Yard is selected, its building done
place_sq:       DW $FFFF        ; the square under the cursor (the top left)
place_fits:     DB 0            ; struct_check_location said yes
place_w:        DB 1            ; the building's size in squares
place_h:        DB 1
; the view shake (view_shake_frame $005E26 in ui/ui.asm; the renderer draws
; one of its two screens moved by it)
shake_on:       DB 0            ; $FFBEA4 non-zero: the view is shaking
shake_ox:       DB 0            ; the cartridge's offset from where the shake
shake_oy:       DB 0            ;   began, in pixels (signed, -1..6)
; the credits counter (ui_draw_credits $011F34); credits_shown ($FFC058)
; is HOUSE's (house/world.inc)
; the sound (main.asm)
sound_on:       DB 0            ; $FFDC51 soundOn: effects and voices
music_on:       DB 0            ; $FFDC50 musicOn
music_frames_left: DW $FFFF     ; $FFC574 musicFramesLeft; negative: none
music_last:     DB $FF          ; $FFC8B8 musicLastTrack: the battle tune (8-12)
                                ; played last, never drawn twice running
music_track:    DB 0            ; the track snd_music was asked for last, 0
                                ; none (the port's: the mentat's "already
                                ; playing", where the cartridge has $FFC194)
radar_option:   DB 1            ; $FFBF7C Radar is: 0 off, 1 on, 2 just turned on
; the radar (ui/ui.asm); its pictures are in page PG_RADAR
radar_shows:    DB 0            ; $FFBF6C radarShowsMap
radar_small:    DB 0            ; $FFBF51 the map is 32 x 32
radar_row:      DB 0            ; $FFBF6A the next row, & 63
radar_static:   DB $FF          ; the switching animation's frame, $FF none
radar_front:    DW 0            ; the picture drawn (RADAR_A), 0 none
radar_gen:      DB 0            ; counts its cell rows drawn (rd_one_row); the
                                ; renderer copies it again when it moved
crd_tick:       DD 0            ; $FFD6B8 the GUI tick it may next run at
crd_step:       DD 0            ; $FFD6BC the accumulated step, signed
crd_value:      DD 0            ; $FFD6C0 the value rolling
crd_count:      DW 0            ; $FFD6B4 steps taken: a sound every 4th
crd_digits:     DD 0            ; the number drawn (d5)
crd_low:        DB 0            ; ui_warning_blink: the CREDITS LOW warning is drawn
crd_text:       DS 6, $FF       ; crd_digits as "%6d": digits, $FF blank
; the side panel's lower half (ui_draw_selection_panel $0294BE, in
; ui/ui.asm; the renderer draws it): sprite frames, $FFFF none
panel_pic2:     DW $FFFF        ; $FFC73C the lower picture, at (272, 88)
panel_bar2:     DW $FFFF        ; $FFC740 the second bar, 32 x 8 ...
panel_bar2_y:   DW 112          ; ... at (272, 112) $06A7DA or (272, 80) $06A7E0
panel_label:    DB 0            ; $FFC724 the label - the no sign over the picture

; ------------------------------------------ the subsystems' shared state
        INCLUDE "move/world.inc"
        INCLUDE "combat/world.inc"
        INCLUDE "struct/world.inc"
        INCLUDE "house/world.inc"

; ------------------------------------------------- the front end's tables
; Page-aligned, indexed with H (front/front.asm fe_own, fe_ink); the
; front bank has no room for the alignment.  Filled before every use.
        ALIGN 256
fe_owntab:      DS 768          ; mask, even rows, odd rows (fe_own)
fe_inktab:      DS 32           ; (mask, data) per pixel-pair code (fe_ink)

; ---------------------------------------------------- the crash catcher
; stub/stub.asm isr and crash_go, front/front.asm front_crash.  The frame
; interrupt counts frames in which the game was not halted (waiting for a
; frame) and had not beaten wd_idle back to 0 itself (the battle's pass,
; gs_tick); at WD_LIMIT it is stuck or running garbage, and the crash
; screen shows where it was.  A jump to address 0 shows the same screen.
WD_LIMIT        EQU 1500        ; frames: 30 s (a bounded card wait, GS_STALL, is 12)
wd_armed:       DB 1            ; 0 once the screen is up (or never wanted)
wd_idle:        DW 0            ; frames since the game last halted or beat
wd_pc:          DW 0            ; the crash screen's: where the CPU was,
wd_sp:          DW 0            ;   its stack pointer,
wd_bank:        DB 0            ;   the bank in window 0,
wd_why:         DB 0            ;   0 the watchdog, 1 a jump to 0,
wd_stack:       DS 16           ;   and the top eight words of its stack

; ------------------------------------------- the explosion animations
; combat/world.inc's pool (its layout and FX_* are there): after the
; page-aligned tables, where FX_COUNT * FX_SIZE bytes fit - the 16 bytes
; in front of the alignment would not.
fx_list:        DS  FX_COUNT * FX_SIZE, 0
