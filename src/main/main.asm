; main.asm - bank MAIN: start-up and the top of the game.

; boot.asm jumps here with window 0 already on this bank, the configuration
; ports open and the clock at 14 MHz.  Window 2 is still the boot page.
main_init:
        ld  a, (PG_WORLD ^ $3F) | $40
        ld  bc, MMUF_W2
        out (c), a              ; window 2 <- WORLD: globals and the stack
        ld  sp, STACK_TOP
        ld  a, PG_MAIN
        ld  (cur_bank), a
        call vid_clear_all
        call map_game
        call vid_ega
        im  1
        ei                      ; before the palette: it waits for a frame
        ld  hl, battle_palette
        call vid_palette
        call snd_boot
main_entry:
        ld  sp, STACK_TOP
        ld  a, (dbg_flags)
        bit 7, a
        jp  nz, test_loop_main
        ld  a, (dbg_house)
        cp  $FF
        jr  z, main_front
        ; straight into a battle (the debug block)
        ld  (game_house), a
        ld  a, (dbg_mission)
        ld  (game_mission), a
        jr  main_battle
main_front:
        FCALL front_start
        ld  (game_house), a
        ld  a, b
        ld  (game_mission), a
main_mission:
        ; the mentat, then the map of Arrakis
        ld  a, (game_mission)
        ld  b, a
        ld  a, (game_house)
        FCALL front_briefing
        ld  a, (game_mission)
        ld  b, a
        ld  a, (game_house)
        FCALL front_campaign
main_battle:
        FCALL render_invalidate
        ld  a, (game_mission)
        ld  b, a
        ld  a, (game_house)
        call start_mission
        call battle_loop
        xor a
        ld  (timer_game_on), a
        ld  (timer_gui_on), a
        ; the options' requests
        ld  a, (battle_request)
        or  a
        jr  z, main_over
        cp  1
        jr  z, main_battle      ; the mission again
        cp  2
        jr  z, main_front       ; back to the title
        jr  main_mission        ; 3: a password's mission (game_*)
main_over:
        ld  a, (level_result)
        cp  1
        ld  a, 1
        jr  z, mo_1
        xor a
mo_1:   push af
        FCALL front_result
        pop af
        or  a
        jr  z, main_mission     ; lost: the same mission again
        ld  a, (game_mission)
        cp  9
        jr  nc, main_end
        inc a
        ld  (game_mission), a
        jr  main_mission
main_end:
        ld  a, (game_house)
        FCALL front_ending
        jr  main_front

; A = the player's house, B = the mission: load it and set the view.
; (battle_request is cleared, and COMBAT's explosion list.)
start_mission:
        FCALL scen_load
        FCALL combat_reset
        FCALL radar_init
        FCALL ui_battle_start
        ld  a, (player_house)
        FCALL radar_update_state
        xor a
        ld  (battle_request), a
        ld  (level_result), a
        dec a
        ld  (unit_selected), a
        ld  (struct_selected), a
        ; the view from tacticalPos (a square) in pixels
        ld  hl, (tactical_pos)
        ld  a, l
        and $3F
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  (view_x), hl
        ld  hl, (tactical_pos)
        add hl, hl
        add hl, hl
        ld  l, h
        ld  h, 0
        ld  a, l
        and $3F
        ld  l, a
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  (view_y), hl
        call view_clamp
        ld  a, (dbg_flags)
        bit 1, a                ; the player takes no damage
        ld  a, 0
        jr  z, sm_1
        inc a
sm_1:   ld  (playtester), a
        ld  hl, (dbg_credits)
        ld  a, h
        or  l
        jr  z, sm_2
        push hl
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        pop de
        ld  (hl), e
        inc hl
        ld  (hl), d
sm_2:   ; the counter starts on the player's credits at once
        ld  hl, $FFFF
        ld  (credits_shown), hl
        ld  hl, 0
        ld  (credits_shown + 2), hl
        ld  a, 2
        FCALL ui_draw_credits
        ret

; Keep the view on the playable part of the map (the UI bank's rule).
view_clamp:
        FCALL ui_view_clamp
        ret

; ---------------------------------------------------------- the battle
;
; S1 game_battle_loop $0124D8: one pass a frame (at most); every pass the
; units, then one of teams, structures, houses, structures in turn; the
; screen's upkeep; every 300 ticks the question whether it is over.

battle_loop:
        ld  hl, $FFFF           ; no tune: the first pass draws one
        ld  (music_frames_left), hl ; ($012532)
        ld  a, 1
        ld  (timer_game_on), a
        ld  (timer_gui_on), a
        ld  hl, (frame_count)
        ld  (frame_seen), hl
        xor a
        ld  (loop_d3), a
bl_pass:
        ; wait for a frame (time_tick $004664)
        ld  hl, (frame_seen)
        ld  de, (frame_count)
        or  a
        sbc hl, de
        jr  nz, bl_frame
        halt
        jr  bl_pass
bl_frame:
        ld  a, (tst_state)
        cp  1
        call z, test_serve
        ld  hl, (frame_count)
        ld  de, (frame_seen)
        ld  (frame_seen), hl
        or  a
        sbc hl, de
        ld  (frames_this_pass), hl
        ld  hl, 0
        ld  (wd_idle), hl       ; the crash catcher: a pass ran
        ld  bc, (pass_count)
        inc bc
        ld  (pass_count), bc
        ex  de, hl
        ld  hl, (music_frames_left)
        or  a
        sbc hl, de
        ld  (music_frames_left), hl
        call bl_music
        PROF 24
        call snd_bg_pass
        PROF 20
        FCALL ui_battle_input
        ld  a, (battle_request)
        or  a
        ret nz                  ; the options asked for something else
        PROF 21
        FCALL unit_tick_all
        PROF 22
        ld  a, (loop_d3)
        or  a
        jr  nz, bl_r1
        FCALL team_tick
        jr  bl_rnext
bl_r1:  cp  2
        jr  z, bl_r2
        FCALL struct_game_loop
        jr  bl_rnext
bl_r2:  FCALL game_loop_house
bl_rnext:
        ld  a, (loop_d3)
        inc a
        and 3
        ld  (loop_d3), a
        PROF 25
        ; the screen's upkeep (the last two keep real time)
        FCALL radar_frame
        PROF 26
        xor a
        FCALL ui_draw_credits
        PROF 27
        FCALL fx_explosion_tick
        PROF 28
        FCALL map_anim_tick
        PROF 23
        FCALL render_frame
        ; is it over?  (S1 step 10)
        FCALL game_check_level_end
        or  a
        jp  nz, bl_pass
        ret

; A = a map's Seed (1-27): its bytes into the map page as ground icons,
; nothing over them.  A 32 x 32 map goes in rows and columns 16-47.
test_load_map:
        push af
        ld  a, $$tbl_maps
        call map_w1
        pop af
        dec a
        add a, a
        add a, a
        ld  l, a
        ld  h, 0
        ld  de, tbl_maps
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; the address (window 1)
        inc hl
        ld  a, (hl)             ; the page
        inc hl
        ld  c, (hl)             ; the scale, 32 or 64
        call map_w1
        ; clear the map
        push de
        push bc
        ld  hl, MAP_GROUND
        ld  (hl), $7F           ; sand
        ld  de, MAP_GROUND + 1
        ld  bc, $1000 - 1
        ldir
        ld  hl, MAP_HIGH
        ld  (hl), 0
        ld  de, MAP_HIGH + 1
        ld  bc, $3000 - 1
        ldir
        pop bc
        pop hl                  ; HL = the map's bytes
        ld  a, c
        cp  64
        jr  z, tlm_big
        ld  de, MAP_GROUND + 16 * 64 + 16
        ld  b, 32
tlm_row:
        push bc
        ld  bc, 32
        ldir
        ex  de, hl
        ld  bc, 32
        add hl, bc
        ex  de, hl
        pop bc
        djnz tlm_row
        jp  map_game
tlm_big:
        ld  de, MAP_GROUND
        ld  bc, $1000
        ldir
        jp  map_game

battle_palette:
        INCLUDE "palette_battle.inc"

; ------------------------------------------------------------ the test mailbox
; world.asm has the layout; tools/dune_test.py the other end.
test_loop_main:
        ei
        halt
        ld  a, (tst_state)
        cp  1
        jr  nz, test_loop_main
        call test_serve
        ld  sp, STACK_TOP
        jr  test_loop_main

; One call from the mailbox (tst_state = 1): also served at the start of
; every battle pass, so a test can reach into a running battle.
test_serve:
        call map_game
        ld  a, (tst_w1)
        or  a
        call nz, map_w1
        ld  a, (tst_w3)
        or  a
        call nz, map_w3
        ld  a, (tst_bank)
        ld  (fc_bank), a
        ld  hl, (tst_addr)
        ld  (fc_jump + 1), hl
        ld  bc, (tst_in + 2)
        ld  de, (tst_in + 4)
        ld  ix, (tst_in + 8)
        ld  iy, (tst_in + 10)
        ld  hl, (tst_in)
        push hl
        pop af
        ld  hl, (tst_in + 6)
        call far_call_mem
        ld  (tst_out + 6), hl
        push af
        pop hl
        ld  (tst_out), hl
        ld  (tst_out + 2), bc
        ld  (tst_out + 4), de
        ld  (tst_out + 8), ix
        ld  (tst_out + 10), iy
        call map_game
        ld  hl, (tst_calls)
        inc hl
        ld  (tst_calls), hl
        ld  a, 2
        ld  (tst_state), a
        ret

; ------------------------------------------------------------ the sound
; The game asks for sounds by the cartridge's numbers (S10): an effect id
; (0-$40, $06A876), a spoken-feedback id (0-$5D, $06A954) or a music track
; (1-$26, $06A8B8).  src/gs.asm plays them on the General Sound card.

; ------------------------------------------------------------- the sound
;
; The General Sound card plays everything (src/gs.asm, uploaded once at
; start-up).  The three calls take the Mega Drive's numbers (S10).  With
; no card, or dbg_flags bit 3, they do nothing.

; snd_effect: A = an effect id ($06A876).  Keeps IX, IY.
snd_effect:
        push af
        ld  a, (sound_on)
        or  a
        jr  z, snd_off
        pop af
        jp  gs_effect
; snd_voice: A = a feedback id ($06A954).
snd_voice:
        push af
        ld  a, (sound_on)
        or  a
        jr  z, snd_off
        pop af
        jp  gs_voice
snd_off:
        pop af
        ret

; snd_music: A = a music track ($06A8B8); 0 stops the music.
; snd_play_music $00A806, whether or not there is a card to hear it - so
; the game's random numbers do not depend on one:
;   0: the song stops ($00A812; musicFramesLeft is left as it is);
;   music off: the song stops and musicFramesLeft becomes -1, unless it
;     is already negative ($00A8AE) - so the battle draws every pass;
;   a battle track 8-12: drawn again, with the game's generator, while it
;     is the one played last, which it then becomes ($00A844-$00A860);
;   then, if the track has a song, it starts and musicFramesLeft becomes
;     its length, -1 for all but the battle's ($00A866-$00A894).
snd_music:
        or  a
        jr  nz, snm_1
        ld  (music_track), a
        jp  gs_music_stop
snm_1:  ld  b, a
        ld  a, (music_on)
        or  a
        jr  z, snm_off
        ld  a, b
        cp  8
        jr  c, snm_play
        cp  13
        jr  nc, snm_play
        ld  hl, music_last
snm_draw:
        cp  (hl)
        jr  nz, snm_new
        ld  de, $0004           ; c_rand_between(0, 4) + 8
        call rand_between
        add a, 8
        jr  snm_draw
snm_new:
        ld  (hl), a
snm_play:
        push af
        call gs_track
        pop bc                  ; B = the track
        ld  a, h
        or  l
        ret z                   ; the track has no song
        ld  a, b
        ld  (music_track), a
        ld  (music_frames_left), hl
        ret
snm_off:
        ld  hl, (music_frames_left)
        bit 7, h
        ret nz
        call gs_music_stop
        ld  hl, $FFFF
        ld  (music_frames_left), hl
        ret

; The battle's music (S1, pass step 1, $01253A): when no tune is playing
; (musicFramesLeft negative), one of tracks 8-12 at random - snd_music
; draws again while it is the one played last.  The cartridge draws here,
; and only here, in a battle pass: a tune not on the card yet is fetched
; then, in a silence (a card too small to hold all five).
bl_music:
        ld  hl, (music_frames_left)
        bit 7, h
        ret z
        ld  de, $0004           ; c_rand_between(0, 4) + 8
        call rand_between
        add a, 8
        call snd_music
; What comes after this battle, for the loader: the mentat of the
; player's house, and in the last mission the finale's tune.  On a 2 MB
; card they are there already; nothing here draws a number.
        ld  a, (music_on)
        or  a
        ret z
    IFDEF MUS_FINALE
        ld  a, (game_mission)
        cp  9
        ld  a, MUS_FINALE
        call z, gs_want
    ENDIF
        ld  a, (game_house)
        call snd_mentat_track
        jp  gs_want_track

; snd_mentat: A = a house - the mentat's music, unless it is the track
; asked for last (the house screen started it; the briefing does not
; start it again - $FFC194 in mentat_briefing $01F3EE).
snd_mentat:
        call snd_mentat_track
        ld  hl, music_track
        cp  (hl)
        ret z
        jp  snd_music
; A = a house -> A = its mentat's music track: $18 Harkonnen (radnors
; scheme), $19 Atreides (cyrils council), $1A Ordos (ammons advice) -
; mentat_house_confirm $01F362, mentat_briefing $01F402.
snd_mentat_track:
        cp  3
        jr  c, smt_1
        xor a
smt_1:  add a, $18
        ret

; The next tune to the card, a chunk a battle pass (src/gs.asm) - or
; SND_MISS_CHUNKS while a tune asked for is not there yet and the music is
; silent for it (about 0.2 frame each).
SND_MISS_CHUNKS EQU 3
snd_bg_pass:
        ld  a, (music_on)
        or  a
        ret z
        ld  a, (gs_wait)
        or  a
        ld  a, 1
        jp  z, gs_bg
        ld  a, SND_MISS_CHUNKS
        jp  gs_bg

; snd_idle: wait for the next frame interrupt, moving the next tune to the
; card meanwhile - vid_wait_frame for the front end's frame (flip_req
; already set) and its waits.  At most SND_IDLE_CHUNKS chunks, and none
; once the frame is over.  Clobbers A only, as vid_wait_frame and vid_flip
; do: their callers keep counters in the other registers.
SND_IDLE_CHUNKS EQU 3
snd_idle:
        push bc
        push de
        push hl
        ld  a, (frame_count)
        ld  c, a
        ld  a, (music_on)
        or  a
        jr  z, sni_wait
        ld  b, SND_IDLE_CHUNKS
sni_lp: ld  a, (frame_count)
        cp  c
        jr  nz, sni_out
        push bc
        ld  a, 1
        call gs_bg
        pop bc
        jr  c, sni_wait         ; nothing to move
        djnz sni_lp
sni_wait:
        ld  a, (frame_count)
        cp  c
        jr  nz, sni_out
        halt
        jr  sni_wait
sni_out:
        pop hl
        pop de
        pop bc
        ret

; snd_mus: A = a MUS_* id of sound_ids.inc (the options' music test, the
; front end's own tunes); SND_NONE stops.  snd_sfx: A = an SFX_* id.
snd_mus:
        ld  b, a
        ld  a, (music_on)
        or  a
        ret z
        xor a                   ; not a track's
        ld  (music_track), a
        ld  a, b
        jp  gs_music_start
snd_sfx:
        ld  b, a
        ld  a, (sound_on)
        or  a
        ret z
        ld  a, b
        jp  gs_fx_play

; Start-up: check the machine and the card, put the sound set on the card
; with nothing playing, then the port's own screen with its tune.  Two
; screens, the port's own (FRONT):
;
; - the start-up log (front_boot): black, a white line for each check as
;   it is made, and "ok" after it - or "error": the machine's stops the
;   start-up for good; the card's (sbt_snd) says "no sound", waits for a
;   key and goes on without it, the intro and the game silent (gs_abort:
;   every gs_ entry point does nothing).  The machine (evo_check), the card (gs_probe), its
;   memory (gs_init waits for the card's own memory test, about 10.9 s
;   from power-on in bin/evo; gs_pages), "GS init done, loading"
;   (gs_setup), and then a line for each thing that goes to the card - the
;   effects, and each start-up tune by the music test's name - with the
;   bar along the bottom (gs_tick).  All of it at full speed, the card
;   playing nothing: a tune the card plays and a tune it takes compete for
;   its one Z80, and the music stutters (sound.md).
; - the intro (front_intro): its tune (MUS_INTRO, src/res/external.mod),
;   the port's words and PRESS ANY KEY; a key fades it out, the tune fades
;   and the card is left holding what it would have held with no intro
;   (gs_intro_done), and the opening follows.
;
; dbg_flags bit 3: none of it, and no screen.  Either way the switches are
; on, as the cartridge starts them ($0093B6): the game's music logic -
; musicFramesLeft, the battle's draws - runs the same with a card or
; without, and only gs.asm knows there is nothing to hear.  Test mode
; (bit 7) leaves them off.
snd_boot:
        xor a
        ld  (sound_on), a
        ld  (music_on), a
        ld  (snd_bar), a
        ld  (snd_shown), a
        ld  a, (dbg_flags)
        bit 7, a
        ret nz
        bit 3, a
        jp  nz, sbt_on
        FCALL front_boot
        call evo_check
        push af
        ld  a, FB_EVO
        call sbt_line
        pop af
        call sbt_result
        call gs_probe
        push af
        ld  a, FB_GS
        call sbt_line
        pop af
        call sbt_snd
        ld  a, FB_MEM
        call sbt_line
        call gs_init            ; the card's memory test
        call c, sbt_snd         ; it never settled
        call gs_pages           ; A = its pages
        push af
        ld  c, a
        ld  a, FB_SIZE
        ld  b, 0
        call sbt_say
        pop af
        call sbt_snd            ; too few
        call gs_setup
        call map_game
        ld  a, FB_INIT
        call sbt_line
        FCALL front_boot_bar
        ld  a, 1
        ld  (snd_shown), a
        call gs_tick
        ld  a, FB_FX
        call sbt_line
        call gs_load_fx
        call map_game
        call sbt_ok
sbt_tune:
        call gs_boot_next
        jr  c, sbt_loaded
        push af
        ld  c, a
        ld  a, FB_TUNE
        ld  b, 1
        call sbt_say
        pop af
        call gs_load_now
        call map_game
        call sbt_ok
        jr  sbt_tune
sbt_loaded:
        call gs_wcmd
        FCALL front_boot_done
        ld  a, MUS_INTRO
        call gs_music_start
        FCALL front_intro       ; until a key
        call gs_intro_done
        call map_game
sbt_on: ld  a, 1
        ld  (sound_on), a
        ld  (music_on), a
        ret

; The log: A = an FB_ line to start (sbt_line), or to add (B = 0, sbt_say,
; C = its argument); sbt_ok adds "ok".  Clobber AF BC DE HL.
sbt_ok: ld  a, FB_OK
        ld  b, 0
        jr  sbt_say
sbt_line:
        ld  b, 1
sbt_say:
        push ix
        FCALL front_boot_say
        pop ix
        ret

; Carry: "error" after the line, and the start-up stops; else "ok".
sbt_result:
        call sbr_say
        ret nc
sbt_stop:
        halt                    ; for good: the log says why
        jr  sbt_stop
sbr_say:
        ld  a, FB_OK
        jr  nc, sbr_1
        ld  a, FB_ERROR
sbr_1:  push af
        ld  b, 0
        call sbt_say
        pop af
        ret

; The same for the sound card's checks: on carry "error", then the port's
; "no sound" line until a key, and the start-up goes on without the card
; - gs_abort, so every gs_ entry point does nothing, and the intro and
; the game play silent.  Leaves snd_boot's caller's frame as it is: the
; return into snd_boot is dropped for a jump to its end.
sbt_snd:
        call sbr_say
        ret nc
        ld  a, FB_NOSOUND
        call sbt_line
        call sbt_key
        call gs_abort
        pop hl
        FCALL front_boot_bar
        jp  sbt_loaded

; A key (the keyboard's or the pad's) up, down and up again, so the
; intro does not see it.  Clobbers AF, HL.
sbt_key:
        halt
        call sbk_any
        jr  nz, sbt_key
sbk_2:  halt
        call sbk_any
        jr  z, sbk_2
sbk_3:  halt
        call sbk_any
        jr  nz, sbk_3
        ret
sbk_any:
        xor a
        in  a, (PORT_FE)
        cpl
        and $1F
        ld  hl, pad_held
        or  (hl)
        ret

; Is this a ZX Evolution BaseConf?  The simple test: its memory manager
; (xxF7, the shadow ports boot.asm opened) puts four RAM pages a megabyte
; apart into window 3 and each keeps a byte of its own - four megabytes,
; which a smaller machine, or one without the manager, cannot give: its
; pages alias.  Each page's byte is put back.  Carry: not.  Clobbers AF
; BC DE HL.
evo_check:
        di
        ld  hl, evc_pages       ; keep each page's first byte
        ld  de, evc_keep
        ld  b, 4
evc_1:  ld  a, (hl)
        call map_w3
        ld  a, ($C000)
        ld  (de), a
        inc hl
        inc de
        djnz evc_1
        ld  hl, evc_pages       ; each gets its own number
        ld  b, 4
evc_2:  ld  a, (hl)
        call map_w3             ; (it clobbers A)
        ld  a, (hl)
        ld  ($C000), a
        inc hl
        djnz evc_2
        ld  hl, evc_pages       ; and still has it
        ld  bc, 4 * 256
evc_3:  ld  a, (hl)
        call map_w3
        ld  a, ($C000)
        cp  (hl)
        jr  z, evc_4
        inc c                   ; C: the pages that lost it
evc_4:  inc hl
        djnz evc_3
        ld  hl, evc_pages       ; the bytes back
        ld  de, evc_keep
        ld  b, 4
evc_5:  ld  a, (hl)
        call map_w3
        ld  a, (de)
        ld  ($C000), a
        inc hl
        inc de
        djnz evc_5
        call map_game
        ei
        ld  a, c
        cp  1                   ; carry: every page kept its number
        ccf                     ; carry: one did not
        ret

evc_pages:      DB $40, $80, $C0, $FF
evc_keep:       DS 4

; gs_tick (gs.asm calls it while it waits and uploads): the start-up
; log's bar, FE_LOAD_W pixels, once it is up (snd_shown) - the effects and
; the start-up tunes, each effect and chunk weighed by what it costs
; (dune_sound.py).  It never moves back.  Clobbers AF BC DE HL.
gs_tick:
        push hl
        ld  hl, 0
        ld  (wd_idle), hl       ; the crash catcher: the card is being fed
        pop hl
        ld  a, (snd_shown)
        or  a
        ret z
        ld  de, (gs_up_done)
        ld  hl, (gs_up_total)
        ld  a, h
        or  l
        ret z
        ld  bc, FE_LOAD_W
        push bc                 ; the span: BC * min(DE, HL) / HL
        or  a
        sbc hl, de
        add hl, de
        jr  nc, gst_1
        ld  d, h
        ld  e, l
gst_1:  call div_shl8           ; HL = DE * 256 / HL
        pop de
        call mul_shr8           ; (HL * DE + $50) >> 8
        ld  a, l
        ld  hl, snd_bar
        cp  (hl)
        ret z
        ret c
        ld  (hl), a
        push ix
        FCALL front_load_bar
        pop ix
        ret

snd_shown:      DB 0            ; the start-up log's bar is up
snd_bar:        DB 0            ; the bar's pixels shown

        INCLUDE "sound_ids.inc"
        INCLUDE "gs.asm"
