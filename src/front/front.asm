; front.asm - bank FRONT: the front end (title, house, mentat, campaign
; map, victory and defeat, score, options, password, the end).
;
; The Mega Drive's screens as orig/sega/spec/S10-screens.md and S9 tell
; them, in the order and the timing the cartridge has; the pictures are
; src/res/art/ui/*.png, cut and converted by tools/dune_front.py into
; data pages 100 on (front.inc: the directory fe_dir, FA_ numbers, pens).
;
; The screen library (the first half of this file) is meant to be used by
; other banks too, through FCALL: pictures into a copy of the screen, text
; in the three fonts, sprites over it, and a frame routine that puts the
; copy's changes and the sprites on the screen being drawn and flips.
;
; The Tutorial is bank TUTOR (front/tutorial.asm, tut_play); it uses the
; four pages below and screen 1 as its own, and the screens here are
; drawn afresh after it.
;
;   pages 124/125   the unpack cache: a picture unpacked (planes 0|1 at
;                   $C000, 2|3 at $E000); a full-width picture sits where
;                   it goes on the screen, so the cache is a clean copy of
;                   the background's rows while nothing else is unpacked
;   pages 126/127   the background: what every screen shows under the
;                   sprites (the same layout as a screen's two pages)
;
; Every entry point leaves window 1 and window 3 to map_game.

PG_FE_CACHE_A   EQU 124
PG_FE_CACHE_B   EQU 125
PG_FE_BG_A      EQU 126
PG_FE_BG_B      EQU 127
FE_RECTS        EQU 24              ; rectangles a screen remembers
FE_QMAX         EQU 20              ; sprites a frame

PADM_UP         EQU $01
PADM_DOWN       EQU $02
PADM_LEFT       EQU $04
PADM_RIGHT      EQU $08
PADM_A          EQU $10
PADM_B          EQU $20
PADM_C          EQU $40
PADM_START      EQU $80

FE_BOX_COL      EQU 2               ; the mentat's text box: x 16,
FE_BOX_Y        EQU 8               ; y 16 on the Mega Drive (less 8)
FE_BOX_W        EQU 36
FE_MAP_Y        EQU 36              ; the campaign map's rows
FE_MAP_H        EQU 118

    MACRO FE_STR lbl                ; a string of text.inc into fe_strbuf
        ld  hl, lbl
        ld  c, $$lbl
        call fe_copy_str
    ENDM
    MACRO FE_TXT tbl                ; A = an entry of a txt_ group
        ld  hl, tbl
        ld  c, $$tbl
        call fe_txt
    ENDM

; =================================================================== the
; interface MAIN calls

; front_start: from power-on - the opening, the title and the choice of
; house.  -> A = the house (0 Harkonnen, 1 Atreides, 2 Ordos), B = the
; mission to start (1, or what a password gave).
front_start:
        call fe_enter
        ld  a, MUS_TITLE
        FCALL snd_mus
fe_fs_attract:
        call fe_logos
        jr  c, fe_fs_title         ; a button: straight to the menu
        call fe_title_intro
        jr  fe_fs_menu
fe_fs_title:
        call fe_title_still
fe_fs_menu:
        call fe_title_menu
        cp  $FF
        jr  z, fe_fs_idle          ; 900 frames with nothing pressed
        cp  1
        jr  z, fe_fs_options
        cp  2
        jr  z, fe_fs_tutorial
        cp  3
        jr  z, fe_fs_keys
        ; START GAME
        call fe_choose_house
        ld  b, 1
        jp  fe_leave
fe_fs_options:
        xor a
        ld  (fe_battle), a
        call fe_options
        cp  3
        jr  z, fe_fs_password
        cp  4
        jr  nz, fe_fs_title
        ld  a, (game_house)     ; DUNEFINALE
        call fe_ending
        jr  fe_fs_attract
fe_fs_password:
        ld  a, c                ; the house the password named
        jp  fe_leave            ; B = its mission
; REDEFINE KEYS (the port's own line), then the title again.
fe_fs_keys:
        call fe_redefine
        jp  fe_fs_title
; game_front_end $00931C: TUTORIAL plays the tutorial ($030674) and the
; title comes back; the menu left alone for 900 frames plays it too, and
; the opening follows unless START stopped it.  The title's music again
; after it (menu_title installs the front bank).
fe_fs_tutorial:
        FCALL tut_play
fe_fs_back:
        ld  a, MUS_TITLE
        FCALL snd_mus
        jp  fe_fs_title
fe_fs_idle:
        call fe_fade_out_cur
        FCALL tut_play
        or  a
        jr  nz, fe_fs_back
        ld  a, MUS_TITLE
        FCALL snd_mus
        jp  fe_fs_attract

; front_briefing: A = house, B = mission - the mentat's briefing.
front_briefing:
        call fe_enter
        ld  (fe_house), a
        ld  a, b
        ld  (fe_mission), a
        call fe_music_mentat
        ld  a, (fe_house)
        ld  b, a
        ld  a, (fe_mission)
        ld  c, a
        call fe_mentat_screen
        call fe_brief_index     ; A = the mission's first string
        ld  (fe_brief), a
        call fe_say_entry
fe_fb_ask:
        ld  a, (fe_hs + 3)
        add a, 2                ; PROCEED, ADVICE
        call fe_choose2
        or  a
        jr  z, fe_fb_go
        ld  a, (fe_brief)
        add a, 3                ; the advice
        call fe_say_entry
        jr  fe_fb_ask
fe_fb_go:  ld  a, 38
        FCALL snd_effect
        ld  a, $1D
        FCALL snd_music
        call fe_fade_out_cur
        jp  fe_leave

; front_campaign: A = house, B = the mission about to be played - the map
; of Arrakis, the territories falling away from the one attacked next.
front_campaign:
        call fe_enter
        ld  (fe_house), a
        ld  a, b
        ld  (fe_mission), a
        call fe_campaign
        jp  fe_leave

; front_result: A = 1 won, 0 lost (the score figures are in WORLD) - the
; victory or defeat picture, the mentat's word on it, the score page and,
; after a win short of the last mission, the next password.
front_result:
        call fe_enter
        ld  (fe_won), a
        ld  a, (game_house)
        ld  (fe_house), a
        ld  a, (game_mission)
        ld  (fe_mission), a
        call fe_vd_screen
        ld  a, (fe_won)
        or  a
        jr  z, fe_fr_1
        ld  a, (fe_mission)
        cp  9
        jr  c, fe_fr_1
        ld  a, $26
        FCALL snd_music
fe_fr_1:   call fe_music_mentat
        ld  a, (fe_house)
        ld  b, a
        ld  a, (fe_mission)
        ld  c, a
        call fe_mentat_screen
        call fe_brief_index
        ld  b, a
        ld  a, (fe_won)
        or  a
        ld  a, b
        jr  z, fe_fr_lost
        inc a                   ; +1: the victory text
        jr  fe_fr_say
fe_fr_lost:
        add a, 2                ; +2: the defeat text
fe_fr_say: call fe_say_entry
        call fe_wait_button
        call fe_fade_out_cur
        call fe_score
        ld  a, (fe_won)
        or  a
        jr  z, fe_fr_done
        ld  a, (fe_mission)
        cp  9
        jr  nc, fe_fr_done
        call fe_password_page
fe_fr_done:
        call fe_fade_out_cur
        jp  fe_leave

; front_options: Start in a battle.  -> A = the request: 0 go on, 1 play
; the mission again, 2 back to the title, 3 play mission B of house C (a
; password).  The switches it shows are WORLD's music_on, sound_on and
; radar_option.
front_options:
        call fe_enter
        ld  a, 1
        ld  (fe_battle), a
        call fe_options
        cp  4
        jr  nz, fe_fo_1
        ld  a, (game_house)     ; DUNEFINALE: the end, then the title
        call fe_ending
        ld  a, 2
fe_fo_1:   jp  fe_leave

; front_ending: A = house - after the last mission.
front_ending:
        call fe_enter
        call fe_ending
        jp  fe_leave

; ------------------------------------------- the start-up log and the intro
;
; The port's own screens, not the cartridge's (it has none), which MAIN's
; snd_boot puts up at power-on, before the opening.
;
; The start-up log (front_boot, front_boot_say): black, and down it from
; the top a line of the port's words (port.txt's boot_*) in white for each
; check snd_boot makes and each thing it puts on the sound card, "ok" or
; "error" after it; along the bottom a bar of the planet's sand on a dark
; track (front_boot_bar, front_load_bar), in the title's colours.  The
; words and the track are drawn with the library into the background and
; copied onto both screens at once, a line at a time - not through
; fe_frame, which waits for a frame and flips: the start-up calls these
; between two chunks for the card and must not wait, and the library's
; fills are 8 pixels wide where the bar moves by one.
;
; The intro (front_intro): the port's words (port.txt's intro_*, in
; Russian: the font FA_FONT_INTRO is font8 with Cyrillic), the title and
; the place in the planet's sand, the rest in the title's white, and PRESS
; ANY KEY blinking at the bottom, while the intro's tune plays.

FE_BOOT_COL     EQU 1               ; the log: its column, first line's y,
FE_BOOT_Y0      EQU 8               ; the lines' spacing, the last line's y
FE_BOOT_DY      EQU 9               ; (the bar is below it), the line's
FE_BOOT_LAST    EQU 170             ; characters at most
FE_BOOT_W       EQU 38
FE_PRESS_Y      EQU 180             ; the intro's PRESS ANY KEY
FE_LOAD_COL0    EQU 8               ; the bar: columns 8-30 (x 64-247),
FE_LOAD_Y       EQU 187             ; lines 187-191
FE_LOAD_H       EQU 5
FE_LOAD_W       EQU 184             ; its pixels

; What front_boot_say says (snd_boot).
FB_EVO          EQU 0               ; "ZX Evo BaseConf detect"
FB_GS           EQU 1               ; "GS detect"
FB_MEM          EQU 2               ; "GS memory"
FB_INIT         EQU 3               ; "GS init done, loading"
FB_FX           EQU 4               ; "Sound effects"
FB_OK           EQU 5               ; "ok"
FB_ERROR        EQU 6               ; "error"
FB_NOSOUND      EQU 7               ; "no sound: press a key to play without"
FB_TUNE         EQU 8               ; "Music:" and C = a MUS id's name
FB_SIZE         EQU 9               ; C = 32 KB pages: "2Mb", "512Kb"

; front_boot: the screen black, the log empty.
front_boot:
        call fe_enter
        ld  a, FA_PAL_TITLE
        call fe_prepare         ; the palette black, the background clear
        call fe_begin           ; on both screens, the palette up
        ld  a, FE_BOOT_Y0 - FE_BOOT_DY
        ld  (fe_blog_y), a
        xor a
        ld  (fe_blen), a
        jp  fe_leave

; front_boot_bar: the bar's track under the log, empty.
front_boot_bar:
        call fe_enter
        ld  a, PN_LOAD_TRACK
        ld  bc, FE_LOAD_COL0 * 256 + FE_LOAD_Y
        ld  de, (FE_LOAD_W / 8) * 256 + FE_LOAD_H
        call fe_fill
        ld  a, PN_LOAD_BAR
        call vid_colour_byte
        ld  (fe_ldbar), a
        ld  a, PN_LOAD_TRACK
        call vid_colour_byte
        ld  (fe_ldtrk), a
        xor a
        ld  (fe_ldpx), a
        ld  bc, FE_LOAD_COL0 * 256 + FE_LOAD_Y
        ld  de, (FE_LOAD_W / 8) * 256 + FE_LOAD_H
        call fe_boot_show
        jp  fe_leave

; front_boot_say: A = FB_ what, C = its argument; B = 1: on a line of its
; own under the last, B = 0: after the last line's words, a space between.
front_boot_say:
        call fe_enter
        push bc
        push af
        ld  a, b
        or  a
        jr  z, fe_bs_add
        ld  a, (fe_blog_y)          ; a line of its own, cleared
        add a, FE_BOOT_DY
        cp  FE_BOOT_LAST + 1
        jr  c, fe_bs_1
        ld  a, FE_BOOT_LAST
fe_bs_1:   ld  (fe_blog_y), a
        ld  c, a
        ld  b, 0
        ld  de, 40 * 256 + 8
        xor a
        call fe_fill
        xor a
        ld  (fe_blen), a
        jr  fe_bs_2
fe_bs_add:
        ld  a, (fe_blen)
        or  a
        ld  a, ' '
        call nz, fe_bs_char
fe_bs_2:   pop af
        pop bc
        call fe_bs_part
        ld  d, PN_LOAD_WORD
        call fe_ink_intro
        ld  a, (fe_blog_y)
        ld  c, a
        ld  b, FE_BOOT_COL
        ld  hl, fe_bline
        ld  a, (fe_blen)
        call fe_textn
        ld  a, (fe_blog_y)
        ld  c, a
        ld  b, 0
        ld  de, 40 * 256 + 8
        call fe_boot_show
        jp  fe_leave

; A = FB_ what, C = its argument: its words onto the line (fe_bline).
fe_bs_part:
        cp  FB_TUNE
        jr  z, fe_bs_tune
        cp  FB_SIZE
        jr  z, fe_bs_size
        ld  l, a                ; a word of fe_boot_words
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de
        ld  de, fe_boot_words
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        ex  de, hl
        call fe_copy_str
        jp  fe_bs_str
fe_bs_tune:
        push bc
        FE_STR txt_port_boot_music
        call fe_bs_str
        ld  a, ' '
        call fe_bs_char
        pop bc
        ld  a, c
        call fe_mus_name
        jp  fe_bs_str
fe_bs_size:
        ; C = the pages the card's $23 counts: those the ROM leaves for
        ; modules, all but its own first 32 KB (bin/evo's card one fewer
        ; still), so the card's own are that and one more, rounded up to a
        ; power of two (128 KB, 512 KB, 1 MB, 2 MB)
        ld  e, c
        ld  d, 0
        inc de
        ld  hl, 1
fe_bz_1:   or  a
        sbc hl, de
        add hl, de
        jr  nc, fe_bz_2
        add hl, hl
        jr  fe_bz_1
fe_bz_2:   ld  a, h                ; HL pages: 32 and up as whole Mb
        or  a
        jr  nz, fe_bz_mb
        ld  a, l
        cp  32
        jr  c, fe_bz_kb
fe_bz_mb:  ld  b, 5                ; / 32
fe_bz_3:   srl h
        rr  l
        djnz fe_bz_3
        call fe_bs_num
        FE_STR txt_port_boot_mb
        jp  fe_bs_str
fe_bz_kb:  ld  b, 5                ; x 32
fe_bz_4:   add hl, hl
        djnz fe_bz_4
        call fe_bs_num
        FE_STR txt_port_boot_kb
        jp  fe_bs_str

; HL = a number: its digits onto the line.
fe_bs_num:
        call fe_num5            ; HL = the first digit, A = how many
        ld  b, a
        jr  fe_bs_n

; A = a character onto the line.
fe_bs_char:
        ld  (fe_bch), a
        ld  hl, fe_bch
        ld  b, 1
; HL = characters, B = how many (1 at least): onto the line, as many as
; it holds.
fe_bs_n:
        ld  a, (fe_blen)
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, fe_bline
        add hl, de
        ex  de, hl              ; DE = the line's end
        pop hl
fe_bsn_1:  ld  a, (fe_blen)
        cp  FE_BOOT_W
        ret nc
        inc a
        ld  (fe_blen), a
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        djnz fe_bsn_1
        ret

; HL = a string ($FF): onto the line, its spaces at the end left off (the
; music test's names are padded).
fe_bs_str:
        push hl
        ld  b, 0
fe_bss_1:  ld  a, (hl)
        cp  $FF
        jr  z, fe_bss_2
        inc hl
        inc b
        jr  fe_bss_1
fe_bss_2:  pop hl
        ld  a, b
        or  a
        call nz, fe_bs_n
fe_bss_3:  ld  a, (fe_blen)       ; the spaces at the end off
        or  a
        ret z
        ld  e, a
        ld  d, 0
        ld  hl, fe_bline - 1
        add hl, de
        ld  a, (hl)
        cp  ' '
        ret nz
        ld  hl, fe_blen
        dec (hl)
        jr  fe_bss_3

; A = MUS id -> HL = fe_strbuf: its name - the music test's for a tune of
; the game's bank (MUS id - 1 is its song, which txt_music_test_song
; names), the port's own for the rest.
fe_mus_name:
        cp  MUS_TITLE
        jr  z, fe_mn_title
        cp  MUS_INTRO
        jr  z, fe_mn_intro
        dec a
        ld  e, a
        ld  a, $$txt_music_test_song
        call map_w1
        ld  hl, txt_music_test_song
        ld  bc, TXT_MUSIC_TEST_COUNT * 256
fe_mn_1:   ld  a, (hl)
        cp  e
        jr  z, fe_mn_2
        inc hl
        inc c
        djnz fe_mn_1
        FE_STR txt_port_mus_other       ; not in the music test (song18)
        ret
fe_mn_2:   ld  a, c
        FE_TXT txt_music_test
        ret
fe_mn_title:
        FE_STR txt_port_mus_title
        ret
fe_mn_intro:
        FE_STR txt_port_mus_intro
        ret

; B = column, C = y, D = width, E = height: the background's rectangle
; onto both screens now.
fe_boot_show:
        push bc
        push de
        ld  a, PG_FE_BG_A
        ld  (fe_src_a), a
        ld  a, PG_FE_BG_B
        ld  (fe_src_b), a
        ld  a, PG_SCR0_A
        ld  (fe_dst_a), a
        ld  a, PG_SCR0_B
        ld  (fe_dst_b), a
        call fe_copy_rect
        pop de
        pop bc
        ld  a, PG_SCR1_A
        ld  (fe_dst_a), a
        ld  a, PG_SCR1_B
        ld  (fe_dst_b), a
        call fe_copy_rect
        jp  fe_tgt_bg

; The log's words: (address, page) by FB_ number.
fe_boot_words:
        DW  txt_port_boot_evo
        DB  $$txt_port_boot_evo
        DW  txt_port_boot_gs
        DB  $$txt_port_boot_gs
        DW  txt_port_boot_mem
        DB  $$txt_port_boot_mem
        DW  txt_port_boot_init
        DB  $$txt_port_boot_init
        DW  txt_port_boot_fx
        DB  $$txt_port_boot_fx
        DW  txt_port_boot_ok
        DB  $$txt_port_boot_ok
        DW  txt_port_boot_error
        DB  $$txt_port_boot_error
        DW  txt_port_boot_nosound
        DB  $$txt_port_boot_nosound

; front_crash: the crash catcher's screen (stub/stub.asm crash_go, the
; wd_ variables of world_vars.inc): the log's screen, black, with a line
; saying where the CPU was - 0 (the watchdog: WD_LIMIT frames without a
; halt or a beat) or 1 (a jump to address 0), then PC, the bank in window
; 0 and SP - and two lines with the top eight words of its stack, for a
; photograph to be read against build/dune.sym.  Never returns.  The
; catcher is disarmed, so the interrupt may run: the log's routines wait
; for frames.  (Digits and the letters P, C, B, S: the log's font is the
; intro's, whose W is Cyrillic.)
front_crash:
        ei
        call vid_clear_all
        call map_game
        call front_boot
        call fe_crash_line
        ld  a, (wd_why)
        add a, '0'
        call fe_bs_char
        ld  a, ' '
        call fe_bs_char
        ld  a, 'P'
        call fe_bs_char
        ld  a, 'C'
        call fe_bs_char
        ld  hl, (wd_pc)
        call fe_crash_hex4
        ld  a, 'B'
        call fe_bs_char
        ld  a, (wd_bank)
        call fe_crash_hex2
        ld  a, 'S'
        call fe_bs_char
        ld  a, 'P'
        call fe_bs_char
        ld  hl, (wd_sp)
        call fe_crash_hex4
        call fe_crash_show
        ld  ix, wd_stack
        ld  c, 2                ; two lines of four words (the log's
fcr_2:  push bc                 ; routines clobber IX)
        push ix
        call fe_crash_line
        pop ix
        pop bc
        ld  b, 4
fcr_3:  push bc
        ld  l, (ix + 0)
        ld  h, (ix + 1)
        inc ix
        inc ix
        call fe_crash_hex4
        pop bc
        djnz fcr_3
        push bc
        push ix
        call fe_crash_show
        pop ix
        pop bc
        dec c
        jr  nz, fcr_2
fcr_4:  halt
        jr  fcr_4

; a fresh line of the log, cleared, and the line buffer empty.  Clobbers
; A, BC, DE, HL.
fe_crash_line:
        call fe_enter
        ld  a, (fe_blog_y)
        add a, FE_BOOT_DY
        cp  FE_BOOT_LAST + 1
        jr  c, fcl_1
        ld  a, FE_BOOT_LAST
fcl_1:  ld  (fe_blog_y), a
        ld  c, a
        ld  b, 0
        ld  de, 40 * 256 + 8
        xor a
        call fe_fill
        xor a
        ld  (fe_blen), a
        ret

; the line buffer onto its line of the log, shown
fe_crash_show:
        ld  d, PN_LOAD_WORD
        call fe_ink_intro
        ld  a, (fe_blog_y)
        ld  c, a
        ld  b, FE_BOOT_COL
        ld  hl, fe_bline
        ld  a, (fe_blen)
        call fe_textn
        ld  a, (fe_blog_y)
        ld  c, a
        ld  b, 0
        ld  de, 40 * 256 + 8
        call fe_boot_show
        jp  fe_leave

; HL as four hex digits and a space onto the line; A as two.  Keep IX.
fe_crash_hex4:
        ld  a, h
        push hl
        call fe_crash_hex2b
        pop hl
        ld  a, l
fe_crash_hex2:
        call fe_crash_hex2b
        ld  a, ' '
        jp  fe_bs_char
fe_crash_hex2b:
        push af
        rrca
        rrca
        rrca
        rrca
        call fe_crash_digit
        pop af
fe_crash_digit:
        and $0F
        add a, '0'
        cp  '9' + 1
        jr  c, fcd_1
        add a, 'A' - '0' - 10
fcd_1:  jp  fe_bs_char

; front_boot_done: the full bar a moment, then the screen fades out.
front_boot_done:
        call fe_enter
        ld  a, FE_LOAD_W
        call front_load_bar
        ld  b, 25
        call fe_wait
        ld  a, FA_FADE_TITLE
        ld  c, 2
        call fe_fade_out
        ld  a, $FF
        ld  (fe_curfade), a     ; nothing up
        jp  fe_leave

; front_intro: the intro's screen faded in, PRESS ANY KEY blinking under
; the words until a key (the keyboard's, or the pad's) goes down and up
; again, then faded out; the front end starts afresh after it
; (front_start).  The key is not left for the opening to see.
front_intro:
        call fe_enter
        ld  a, FA_PAL_TITLE
        call fe_prepare         ; the palette black, the background clear
        ld  hl, fe_intro_words
fe_fl_words:
        ld  a, (hl)             ; its pen, $FF: the end
        cp  $FF
        jr  z, fe_fl_word
        inc hl
        ld  d, a
        ld  e, (hl)             ; y
        inc hl
        push hl
        push de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        push hl                 ; -> (address, page) in txt_port
        call fe_ink_intro
        pop hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        ex  de, hl
        call fe_copy_str
        pop de
        ld  c, e
        call fe_lines
        pop hl
        inc hl
        inc hl
        jr  fe_fl_words
fe_fl_word:
        ld  d, PN_LOAD_WORD     ; the version, top right
        call fe_ink_intro
        FE_STR txt_port_intro_version
        ld  hl, fe_strbuf
        ld  bc, 28 * 256 + 0
        call fe_text
        call fe_key_on
        call fe_begin           ; on both screens, faded in
fe_fi_up:  call vid_wait_frame     ; the keys all up first
        call fe_any_key
        jr  nz, fe_fi_up
        xor a
        ld  (fe_blink), a
fe_fi_1:   call vid_wait_frame
        ld  hl, fe_blink
        inc (hl)
        ld  a, (hl)
        and 15
        jr  nz, fe_fi_2
        bit 4, (hl)             ; 16 frames on, 16 off
        call z, fe_key_on
        ld  hl, fe_blink
        bit 4, (hl)
        call nz, fe_key_off
        ld  bc, FE_PRESS_Y
        ld  de, 40 * 256 + 8
        call fe_boot_show
fe_fi_2:   call fe_any_key
        jr  z, fe_fi_1
fe_fi_3:   call vid_wait_frame     ; and up again
        call fe_any_key
        jr  nz, fe_fi_3
        call pad_take
        ld  a, FA_FADE_TITLE
        ld  c, 2
        call fe_fade_out
        ld  a, $FF
        ld  (fe_curfade), a     ; nothing up
        jp  fe_leave

; PRESS ANY KEY into the background, or its line cleared.
fe_key_on:
        ld  d, PN_LOAD_WORD
        call fe_ink_intro
        FE_STR txt_port_press_key
        ld  c, FE_PRESS_Y
        jp  fe_lines
fe_key_off:
        xor a
        ld  bc, FE_PRESS_Y
        ld  de, 40 * 256 + 8
        jp  fe_fill

; -> NZ: a key of the keyboard, or a button of the pad, is down.
fe_any_key:
        xor a                   ; every half-row
        in  a, (PORT_FE)
        cpl
        and $1F
        ret nz
        ld  a, (pad_held)
        or  a
        ret

; front_load_bar: A = the bar's pixels, 0-FE_LOAD_W: filled up to there,
; in the background and on both screens now, with no frame waited for.
; It only grows.
front_load_bar:
        cp  FE_LOAD_W + 1
        jr  c, fe_flb_1
        ld  a, FE_LOAD_W
fe_flb_1:
        ld  hl, fe_ldpx
        cp  (hl)
        ret c
        ret z
        ld  c, (hl)             ; C = from
        ld  (hl), a             ; A = to
        ld  b, a
        ld  a, c
        and $F8
        ld  c, a                ; the first column's first pixel
        rrca
        rrca
        rrca
        add a, FE_LOAD_COL0
        ld  (fe_ldc0), a
fe_flb_col:
        ld  a, b                ; the pixels filled in this column
        sub c
        cp  8
        jr  c, fe_flb_2
        ld  a, 8
fe_flb_2:
        push bc
        call fe_ld_column
        pop bc
        ld  a, c
        add a, 8
        ld  c, a
        cp  b
        jr  c, fe_flb_col
        ; the columns changed, from the background onto both screens
        ld  a, PG_FE_BG_A
        ld  (fe_src_a), a
        ld  a, PG_FE_BG_B
        ld  (fe_src_b), a
        ld  a, PG_SCR0_A
        call fe_ld_show
        ld  a, PG_SCR1_A
        call fe_ld_show
        call fe_tgt_bg
        jp  fe_leave

; A = a screen's page A: the bar's columns from fe_ldc0 to the one just
; drawn (fe_ldcol) onto it.
fe_ld_show:
        ld  (fe_dst_a), a
        xor 4                   ; page B is page A xor 4
        ld  (fe_dst_b), a
        ld  a, (fe_ldc0)
        ld  b, a
        ld  a, (fe_ldcol)
        sub b
        inc a
        ld  d, a
        ld  c, FE_LOAD_Y
        ld  e, FE_LOAD_H
        jp  fe_copy_rect

; A = the pixels of a column filled (1-8), C = its first pixel in the bar:
; its four plane bytes, sand then track, into the background's rows.
fe_ld_column:
        ld  d, a
        ld  a, c
        rrca
        rrca
        rrca
        add a, FE_LOAD_COL0
        ld  (fe_ldcol), a
        ld  hl, fe_ldb
        ld  e, 0                ; plane p holds pixels 2p (left), 2p + 1
        ld  c, 4
fe_ldc_1:
        ld  a, e
        cp  d
        ld  a, (fe_ldtrk)
        jr  nc, fe_ldc_2
        ld  a, (fe_ldbar)
fe_ldc_2:
        and $47                 ; the left pixel's bits
        ld  b, a
        ld  a, e
        inc a
        cp  d
        ld  a, (fe_ldtrk)
        jr  nc, fe_ldc_3
        ld  a, (fe_ldbar)
fe_ldc_3:
        and $B8                 ; the right one's
        or  b
        ld  (hl), a
        inc hl
        inc e
        inc e
        dec c
        jr  nz, fe_ldc_1
        ld  a, (fe_ldcol)
        ld  b, a
        ld  c, FE_LOAD_Y
        call fe_rowaddr
        ld  (fe_ldoff), hl
        ld  a, PG_FE_BG_A       ; planes 0 and 2
        call map_w3
        ld  a, (fe_ldb + 0)
        ld  hl, $C000
        call fe_ld_plane
        ld  a, (fe_ldb + 2)
        ld  hl, $E000
        call fe_ld_plane
        ld  a, PG_FE_BG_B       ; planes 1 and 3
        call map_w3
        ld  a, (fe_ldb + 1)
        ld  hl, $C000
        call fe_ld_plane
        ld  a, (fe_ldb + 3)
        ld  hl, $E000
; A = a plane byte, HL = the plane: into the bar's rows of the column.
fe_ld_plane:
        ld  de, (fe_ldoff)
        add hl, de
        ld  de, 40
        ld  b, FE_LOAD_H
fe_ldp_1:
        ld  (hl), a
        add hl, de
        djnz fe_ldp_1
        ret

; D = a pen: FA_FONT_INTRO in it, shadowed black.
fe_ink_intro:
        ld  a, FA_FONT_INTRO
        ld  e, d
        ld  c, 0
        jp  fe_ink

; HL = a string of lines ($0A between, $FF at the end), C = y: each line
; centred on the screen's 40 columns, 10 lines below the one before.
fe_lines:
        ld  a, c
        ld  (fe_lny), a
fe_lns_1:
        ld  (fe_lnp), hl
        ld  d, 0
fe_lns_2:
        ld  a, (hl)
        cp  $FF
        jr  z, fe_lns_3
        cp  $0A
        jr  z, fe_lns_3
        inc hl
        inc d
        jr  fe_lns_2
fe_lns_3:
        ld  (fe_lne), hl
        ld  a, 40
        sub d
        srl a
        ld  b, a
        ld  a, (fe_lny)
        ld  c, a
        add a, 10
        ld  (fe_lny), a
        ld  hl, (fe_lnp)
        ld  a, d
        call fe_textn
        ld  hl, (fe_lne)
        ld  a, (hl)
        inc hl
        cp  $0A
        jr  z, fe_lns_1
        ret

; The intro's words: pen, y, -> the string's (address, page).
fe_intro_words:
        DB  PN_LOAD_BAR, 10
        DW  fe_iw_title
        DB  PN_LOAD_WORD, 20
        DW  fe_iw_port
        DB  PN_LOAD_WORD, 48
        DW  fe_iw_thanks
        DB  PN_LOAD_WORD, 86
        DW  fe_iw_bugs
        DB  PN_LOAD_WORD, 134
        DW  fe_iw_authors
        DB  PN_LOAD_BAR, 158
        DW  fe_iw_place
        DB  $FF
fe_iw_title:    DW  txt_port_intro_title
                DB  $$txt_port_intro_title
fe_iw_port:     DW  txt_port_intro_port
                DB  $$txt_port_intro_port
fe_iw_thanks:   DW  txt_port_intro_thanks
                DB  $$txt_port_intro_thanks
fe_iw_bugs:     DW  txt_port_intro_bugs
                DB  $$txt_port_intro_bugs
fe_iw_authors:  DW  txt_port_intro_authors
                DB  $$txt_port_intro_authors
fe_iw_place:    DW  txt_port_intro_place
                DB  $$txt_port_intro_place

; ======================================================== the library
;
; fe_pic       A = FA_ picture: into the background where it belongs
; fe_pic_at    A, B = column ($FF: its own place), C = y
; fe_unpack    A = FA_ picture -> the cache (fe_pw, fe_ph ... describe it)
; fe_q_cache   B = column, C = y: the cached picture on the next frame
; fe_q_spr     A = FA_ sprite, B = column ($FF: its own place), C = y:
;              over the background on the next frame
; fe_q_terr    A = FA_ territory, B = rows down, C = FA_ owner table (0:
;              the colours fe_own loaded): likewise
; fe_terr      A = FA_ territory, B = rows down: into the background
; fe_own       A = FA_ owner table: the colours territories draw in
; fe_ink       A = FA_ font, D, E, C = the pens of the font's inks A, B, C
; fe_text      HL = string ($FF), B = column, C = y: into the background
; fe_textn     the same, A = its length
; fe_fill      A = colour, B = column, C = y, D = width, E = height
; fe_pristine  B, C, D, E: the background's rectangle back from the cache
; fe_bg_clear  the background black
; fe_show      the background on both screens now
; fe_frame     draw the background's changes and the sprites on the
;              screen not shown, flip; a frame at least
; fe_pal       A = FA_ palette; fe_pal_black; fe_fade_in/fe_fade_out A =
;              FA_ fade, C = frames a step
; fe_mark_both B, C, D, E: a rectangle of the background changed
;
; Clobber everything but IY unless a header says otherwise.

fe_enter:
        push af
        push bc
        call fe_tgt_bg
        xor a
        ld  (fe_qn), a
        ld  hl, fe_dl0
        ld  (hl), a
        inc hl
        ld  (hl), a
        ld  hl, fe_dl1
        ld  (hl), a
        inc hl
        ld  (hl), a
        ld  a, (frame_count)
        ld  (fe_seed), a
        pop bc
        pop af
        ret

; Keep A and B for the caller; put the game's windows back.
fe_leave:
        push af
        push bc
        call map_game
        pop bc
        pop af
        ret

; A = FA_ number -> window 1 = its page, HL = its address.  Keeps BC.
fe_map_asset:
        ld  l, a
        ld  h, 0
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, de
        ld  de, fe_dir
        add hl, de
        ld  a, (hl)
        inc hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ex  de, hl
        jp  map_w1

; B = column, C = y -> HL = y * 40 + column.  Keeps BC, DE.
fe_rowaddr:
        push de
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
        pop de
        ret

; A * E -> HL.  Clobbers A, B, D.
fe_mul8:
        ld  hl, 0
        ld  d, h
        ld  b, 8
fe_fm8:    add hl, hl
        rlca
        jr  nc, fe_fm8_1
        add hl, de
fe_fm8_1:  djnz fe_fm8
        ret

fe_tgt_bg:
        ld  a, PG_FE_BG_A
        ld  (fe_dst_a), a
        ld  a, PG_FE_BG_B
        ld  (fe_dst_b), a
        ret
fe_tgt_screen:
        ld  a, (draw_a)
        ld  (fe_dst_a), a
        ld  a, (draw_b)
        ld  (fe_dst_b), a
        ret

; ------------------------------------------------------ the rectangles
;
; Each screen keeps a list of the rectangles that differ from the
; background (what was drawn over it, what changed in it): fe_frame puts
; them back from the background before it draws the sprites.

; IX = the list of the screen being drawn.
fe_cur_list:
        ld  ix, fe_dl0
        ld  a, (draw_a)
        cp  PG_SCR0_A
        ret z
        ld  ix, fe_dl1
        ret

; B, C, D, E: a rectangle of the background changed - both screens.
fe_mark_both:
        push hl
        ld  ix, fe_dl0
        call fe_add_rect
        ld  ix, fe_dl1
        call fe_add_rect
        pop hl
        ret

; IX = a list, B = column, C = y, D = width, E = height (cut at the
; screen's edges).  Keeps BC, DE, HL.
fe_add_rect:
        ld  a, d
        or  a
        ret z
        ld  a, e
        or  a
        ret z
        ld  a, (ix + 1)
        or  a
        ret nz
        ld  a, (ix + 0)
        cp  FE_RECTS
        jr  c, fe_far_1
        ld  (ix + 1), 1         ; too many: the whole screen
        ret
fe_far_1:  inc (ix + 0)
        push hl
        push de
        add a, a
        add a, a
        add a, 2
        ld  l, a
        ld  h, 0
        push ix
        pop de
        add hl, de
        pop de
        ld  (hl), b
        inc hl
        ld  (hl), c
        inc hl
        ; cut the width at column 40 and the height at line 200
        ld  a, 40
        sub b
        cp  d
        jr  c, fe_far_2
        ld  a, d
fe_far_2:  ld  (hl), a
        inc hl
        ld  a, 200
        sub c
        cp  e
        jr  c, fe_far_3
        ld  a, e
fe_far_3:  ld  (hl), a
        pop hl
        ret

; IX = a list: copy its rectangles from fe_src_* to fe_dst_*, and empty it.
fe_restore:
        ld  a, (ix + 1)
        or  a
        jr  z, fe_frs_list
        ld  bc, 0
        ld  de, 40 * 256 + 200
        push ix
        call fe_copy_rect
        pop ix
        jr  fe_frs_done
fe_frs_list:
        ld  a, (ix + 0)
        or  a
        jr  z, fe_frs_done
        ld  b, a
        push ix
        pop hl
        inc hl
        inc hl
fe_frs_1:  push bc
        push hl
        push ix
        ld  b, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  e, (hl)
        call fe_copy_rect
        pop ix
        pop hl
        ld  bc, 4
        add hl, bc
        pop bc
        djnz fe_frs_1
fe_frs_done:
        ld  (ix + 0), 0
        ld  (ix + 1), 0
        ret

; B = column, C = y, D = width, E = height: the rectangle from the pages
; fe_src_a/b (window 1) to fe_dst_a/b (window 3), which share the screen's
; layout.
fe_copy_rect:
        ld  a, d
        or  a
        ret z
        ld  a, e
        or  a
        ret z
        call fe_rowaddr
        ld  (fe_cr_off), hl
        ld  a, (fe_src_a)
        call map_w1
        ld  a, (fe_dst_a)
        call map_w3
        call fe_fcr_half
        ld  a, (fe_src_b)
        call map_w1
        ld  a, (fe_dst_b)
        call map_w3
fe_fcr_half:
        ld  hl, (fe_cr_off)
        set 6, h
        call fe_fcr_plane
        ld  hl, (fe_cr_off)
        ld  a, h
        or  $60
        ld  h, a
fe_fcr_plane:                      ; HL = the source's first row, D, E
        ld  b, e
fe_fcr_row:
        push bc
        push hl
        push de
        ld  c, d
        ld  b, 0
        ld  d, h
        set 7, d                ; $4000-$7FFF -> $C000-$FFFF
        ld  e, l
        ldir
        pop de
        pop hl
        ld  bc, 40
        add hl, bc
        pop bc
        djnz fe_fcr_row
        ret

; The background on both screens, now; nothing is left to restore.
fe_show:
        ld  a, PG_FE_BG_A
        ld  (fe_src_a), a
        ld  a, PG_FE_BG_B
        ld  (fe_src_b), a
        ld  a, PG_SCR0_A
        ld  (fe_dst_a), a
        ld  a, PG_SCR0_B
        ld  (fe_dst_b), a
        ld  bc, 0
        ld  de, 40 * 256 + 200
        call fe_copy_rect
        ld  a, PG_SCR1_A
        ld  (fe_dst_a), a
        ld  a, PG_SCR1_B
        ld  (fe_dst_b), a
        ld  bc, 0
        ld  de, 40 * 256 + 200
        call fe_copy_rect
        call fe_stars_forget
        call fe_enter
        ret

; B, C, D, E: the background's rectangle as the cache has it (the last
; full-width picture unpacked).
fe_pristine:
        push bc
        push de
        call fe_mark_both
        ld  a, PG_FE_CACHE_A
        ld  (fe_src_a), a
        ld  a, PG_FE_CACHE_B
        ld  (fe_src_b), a
        call fe_tgt_bg
        pop de
        pop bc
        jp  fe_copy_rect

; The background all black.
fe_bg_clear:
        ld  a, PG_FE_BG_A
        call map_w3
        xor a
        call vid_fill_page
        ld  a, PG_FE_BG_B
        call map_w3
        xor a
        call vid_fill_page
        ld  bc, 0
        ld  de, 40 * 256 + 200
        jp  fe_mark_both

; A = colour, B = column, C = y, D = width, E = height: into the
; background.
fe_fill:
        call vid_colour_byte
        ld  (fe_fillb), a
        push bc
        push de
        call fe_mark_both
        pop de
        pop bc
        call fe_rowaddr
        ld  (fe_cr_off), hl
        ld  a, PG_FE_BG_A
        call map_w3
        call fe_ffl_half
        ld  a, PG_FE_BG_B
        call map_w3
fe_ffl_half:
        ld  hl, (fe_cr_off)
        ld  a, h
        or  $C0
        ld  h, a
        call fe_ffl_plane
        ld  hl, (fe_cr_off)
        ld  a, h
        or  $E0
        ld  h, a
fe_ffl_plane:
        ld  b, e
fe_ffl_row:
        push bc
        push hl
        ld  b, d
        ld  a, (fe_fillb)
fe_ffl_b:  ld  (hl), a
        inc hl
        djnz fe_ffl_b
        pop hl
        ld  bc, 40
        add hl, bc
        pop bc
        djnz fe_ffl_row
        ret

; ------------------------------------------------------------- the frame

; Draw the screen not shown: its rectangles back from the background, then
; the sprites queued since the last frame; show it at the next interrupt.
fe_frame:
        ld  a, PG_FE_BG_A
        ld  (fe_src_a), a
        ld  a, PG_FE_BG_B
        ld  (fe_src_b), a
        call fe_tgt_screen
        call fe_cur_list
        push ix
        call fe_restore
        ld  a, (fe_starson)
        or  a
        call nz, fe_stars_under ; the starfield's plane under the sprites
        pop ix
        ld  a, (fe_qn)
        or  a
        jr  z, fe_ffr_flip
        ld  b, a
        ld  hl, fe_queue
fe_ffr_1:  push bc
        push hl
        push ix
        ld  d, (hl)             ; the kind
        inc hl
        ld  a, (hl)
        inc hl
        ld  b, (hl)
        inc hl
        ld  c, (hl)
        dec d
        jr  z, fe_ffr_terr
        dec d
        jr  z, fe_ffr_cache
        call fe_spr_draw
        jr  fe_ffr_mark
fe_ffr_terr:
        push af
        push bc
        xor a
        ld  (fe_ownmode), a
        ld  a, c
        or  a
        call nz, fe_own         ; C: its owner's colours first
        pop bc
        pop af
        call fe_terr_draw
        jr  fe_ffr_mark
fe_ffr_cache:
        call fe_blit
fe_ffr_mark:
        pop ix
        call fe_add_rect
        pop hl
        ld  bc, 4
        add hl, bc
        pop bc
        djnz fe_ffr_1
fe_ffr_flip:
        ld  a, (fe_starson)
        or  a
        call nz, fe_stars_over  ; the stars where nothing else is
        xor a
        ld  (fe_qn), a
        call fe_tgt_bg
        ld  a, 1                ; vid_flip, the wait for the interrupt
        ld  (flip_req), a       ; spent moving the next tune to the sound
        FCALL snd_idle          ; card (main.asm)
        jp  vf_wait

; The queue: A = FA_, B, C as the header says.  Keep everything.
fe_q_spr:
        push de
        ld  d, 0
        jr  fe_qadd
fe_q_terr:
        push de
        ld  d, 1
        jr  fe_qadd
fe_q_cache:
        push de
        ld  d, 2
fe_qadd:
        push hl
        push af
        ld  a, (fe_qn)
        cp  FE_QMAX
        jr  nc, fe_fqa_full
        ld  l, a
        inc a
        ld  (fe_qn), a
        ld  h, 0
        add hl, hl
        add hl, hl
        push de
        ld  de, fe_queue
        add hl, de
        pop de
        ld  (hl), d
        inc hl
        pop af
        ld  (hl), a
        inc hl
        ld  (hl), b
        inc hl
        ld  (hl), c
        pop hl
        pop de
        ret
fe_fqa_full:
        pop af
        pop hl
        pop de
        ret

; B = frames, each a fe_frame.  -> A = the buttons pressed meanwhile (the
; wait ends early at A, B, C or Start if fe_skip is set).
fe_frames:
        xor a
        ld  (fe_keys), a
fe_ffs_1:  push bc
        call fe_frame
        call pad_take
        ld  hl, fe_keys
        or  (hl)
        ld  (hl), a
        pop bc
        and $F0
        ret nz
        djnz fe_ffs_1
        ld  a, (fe_keys)
        ret

; Wait for A, B, C or Start, the frames going on (the mentat's face too).
fe_wait_button:
        call pad_take
fe_fwb_1:  call fe_face_tick
        call fe_frame
        call pad_take
        and $F0
        jr  z, fe_fwb_1
        ret

; ------------------------------------------------------------ pictures

fe_pic:
        ld  b, $FF
fe_pic_at:
        push af
        push bc
        call fe_unpack
        pop bc
        ld  a, b
        cp  $FF
        jr  z, fe_fpa_1
        ld  (fe_pcol), a
        ld  a, c
        ld  (fe_py), a
fe_fpa_1:  call fe_tgt_bg
        ld  a, (fe_pcol)
        ld  b, a
        ld  a, (fe_py)
        ld  c, a
        call fe_blit
        call fe_mark_both
        pop af
        ld  hl, fe_pflags
        bit 0, (hl)
        ret z
        inc a                   ; the picture's next band
        ld  b, $FF
        jr  fe_pic_at

; A = FA_ picture -> the cache; fe_pcol, fe_py, fe_pw, fe_ph, fe_pflags,
; fe_pbase (where plane 0 starts, less $C000), fe_pstride.
fe_unpack:
        call fe_map_asset
        ld  a, (hl)
        ld  (fe_pcol), a
        inc hl
        ld  a, (hl)
        ld  (fe_py), a
        inc hl
        ld  a, (hl)
        ld  (fe_pw), a
        inc hl
        ld  a, (hl)
        ld  (fe_ph), a
        inc hl
        ld  a, (hl)
        ld  (fe_pflags), a
        inc hl
        push hl
        ; a plane's bytes: w * h, twice that masked
        ld  a, (fe_pw)
        ld  e, a
        ld  a, (fe_pflags)
        and 2
        jr  z, fe_fu_1
        sla e
fe_fu_1:   ld  a, e
        ld  (fe_pstride), a
        xor a
        ld  (fe_pstride + 1), a
        ld  a, (fe_ph)
        call fe_mul8
        ld  (fe_psize), hl
        ; a full-width picture unpacks where it sits on the screen
        ld  hl, 0
        ld  a, (fe_pflags)
        and 2
        jr  nz, fe_fu_2
        ld  a, (fe_pw)
        cp  40
        jr  nz, fe_fu_2
        ld  a, (fe_py)
        ld  c, a
        ld  b, 0
        call fe_rowaddr
fe_fu_2:   ld  (fe_pbase), hl
        pop hl
        ld  a, PG_FE_CACHE_A
        call map_w3
        call fe_fu_stream
        ld  a, PG_FE_CACHE_B
        call map_w3
fe_fu_stream:
        ld  de, (fe_pbase)
        ld  a, d
        or  $C0
        ld  d, a
        call fe_fu_plane
        ld  de, (fe_pbase)
        ld  a, d
        or  $E0
        ld  d, a
fe_fu_plane:
        push hl
        ld  hl, (fe_psize)
        add hl, de
        ld  (fe_lz_end), hl
        pop hl
        ; fall into fe_unlz

; HL = packed bytes (tools/dune_front.py lz_pack), DE = where to, up to
; fe_lz_end.  -> HL after them.
fe_unlz:
fe_ful_1:  ld  a, (hl)
        inc hl
        bit 7, a
        jr  nz, fe_ful_match
        ld  c, a
        ld  b, 0
        inc bc
        ldir
        jr  fe_ful_test
fe_ful_match:
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
fe_ful_test:
        push hl
        ld  hl, (fe_lz_end)
        or  a
        sbc hl, de
        pop hl
        jr  nz, fe_ful_1
        ret

; B = column, C = y: the cached picture into fe_dst_a/b, cut at the
; screen's right and bottom.  -> B, C, D = width, E = height drawn.
fe_blit:
        ld  a, b
        cp  40
        jr  nc, fe_fbl_none
        ld  a, c
        cp  200
        jr  nc, fe_fbl_none
        ld  a, 40
        sub b
        ld  d, a
        ld  a, (fe_pw)
        cp  d
        jr  nc, fe_fbl_1
        ld  d, a
fe_fbl_1:  ld  a, 200
        sub c
        ld  e, a
        ld  a, (fe_ph)
        cp  e
        jr  nc, fe_fbl_2
        ld  e, a
fe_fbl_2:  ld  a, d
        ld  (fe_bw), a
        ld  a, e
        ld  (fe_bh), a
        push bc
        push de
        call fe_rowaddr
        ld  (fe_boff), hl
        ld  a, PG_FE_CACHE_A
        call map_w1
        ld  a, (fe_dst_a)
        call map_w3
        call fe_fbl_half
        ld  a, PG_FE_CACHE_B
        call map_w1
        ld  a, (fe_dst_b)
        call map_w3
        call fe_fbl_half
        pop de
        pop bc
        ret
fe_fbl_none:
        ld  de, 0
        ret
fe_fbl_half:
        ld  hl, (fe_pbase)
        set 6, h
        ld  de, (fe_boff)
        ld  a, d
        or  $C0
        ld  d, a
        call fe_fbl_plane
        ld  hl, (fe_pbase)
        ld  a, h
        or  $60
        ld  h, a
        ld  de, (fe_boff)
        ld  a, d
        or  $E0
        ld  d, a
fe_fbl_plane:
        ld  a, (fe_bh)
        ld  (fe_rows), a
fe_fbp_row:
        push hl
        push de
        ld  a, (fe_pflags)
        and 2
        jr  nz, fe_fbp_mask
        ld  a, (fe_bw)
        ld  c, a
        ld  b, 0
        ldir
        jr  fe_fbp_next
fe_fbp_mask:
        ld  a, (fe_bw)
        ld  b, a
fe_fbp_m:  ld  a, (de)
        and (hl)
        inc hl
        or  (hl)
        inc hl
        ld  (de), a
        inc de
        djnz fe_fbp_m
fe_fbp_next:
        pop hl
        ld  bc, 40
        add hl, bc
        ex  de, hl
        pop hl
        ld  bc, (fe_pstride)
        add hl, bc
        ld  a, (fe_rows)
        dec a
        ld  (fe_rows), a
        jr  nz, fe_fbp_row
        ret

; ------------------------------------------------------------- sprites

; A = FA_ sprite, B = column ($FF: its own place), C = y: into
; fe_dst_a/b.  -> B, C, D, E: the rectangle it covers.
fe_spr_draw:
        call fe_map_asset
        ld  a, b
        cp  $FF
        jr  nz, fe_fsd_1
        ld  b, (hl)
        inc hl
        ld  c, (hl)
        dec hl
fe_fsd_1:  inc hl
        inc hl
        ld  d, (hl)
        inc hl
        ld  e, (hl)
        inc hl
        ld  a, e
        or  a
        jr  nz, fe_fsd_2
        ld  d, a
        ret
fe_fsd_2:  ld  a, d
        ld  (fe_sw), a
        ld  a, e
        ld  (fe_sh), a
        push bc
        push de
        push hl
        call fe_rowaddr
        ld  (fe_soff), hl
        pop hl
        ld  a, (fe_dst_a)
        call map_w3
        call fe_fsd_half
        ld  a, (fe_dst_b)
        call map_w3
        call fe_fsd_half
        pop de
        pop bc
        ret
fe_fsd_half:
        ld  de, (fe_soff)
        ld  a, d
        or  $C0
        ld  d, a
        call fe_fsd_plane
        ld  de, (fe_soff)
        ld  a, d
        or  $E0
        ld  d, a
fe_fsd_plane:
        ld  a, (fe_sh)
        ld  (fe_rows), a
fe_fsp_row:
        push de
        ld  a, (fe_sw)
        ld  b, a
fe_fsp_b:  ld  a, (de)
        and (hl)
        inc hl
        or  (hl)
        inc hl
        ld  (de), a
        inc de
        djnz fe_fsp_b
        pop de
        ld  a, e
        add a, 40
        ld  e, a
        jr  nc, fe_fsp_1
        inc d
fe_fsp_1:  ld  a, (fe_rows)
        dec a
        ld  (fe_rows), a
        jr  nz, fe_fsp_row
        ret

; ---------------------------------------------------------- territories

; A = FA_ owner table: the colours territories draw in, into fe_owntab.
; A territory's pens are its land (1-7, 15) and its own border pieces
; (8); fe_ownmode says which of them draw: 0 both, FE_OWN_LAND the land
; (on the whole map every border is drawn first and the land over it, as
; campaign_draw_pieces and campaign_redraw_map do), FE_OWN_BORDERS the
; borders.
FE_OWN_LAND     EQU 1
FE_OWN_BORDERS  EQU 2
fe_own:
        call fe_map_asset
        ld  de, fe_owntab
        ld  bc, 768
        ldir
        ld  a, (fe_ownmode)
        or  a
        ret z
        ld  c, a
        ld  hl, fe_owntab
        ld  b, 0                ; every pen pair
fe_fow_1:  ld  a, l
        rrca
        rrca
        rrca
        rrca
        and $0F
        call fe_fow_hide        ; the left pixel
        jr  nc, fe_fow_2
        ld  a, (hl)
        or  $47
        ld  (hl), a
        inc h
        ld  a, (hl)
        and $B8
        ld  (hl), a
        inc h
        ld  a, (hl)
        and $B8
        ld  (hl), a
        dec h
        dec h
fe_fow_2:  ld  a, l
        and $0F
        call fe_fow_hide        ; the right one
        jr  nc, fe_fow_3
        ld  a, (hl)
        or  $B8
        ld  (hl), a
        inc h
        ld  a, (hl)
        and $47
        ld  (hl), a
        inc h
        ld  a, (hl)
        and $47
        ld  (hl), a
        dec h
        dec h
fe_fow_3:  inc l
        djnz fe_fow_1
        ret
; A = a pen, C = the mode -> carry if it is not drawn.
fe_fow_hide:
        or  a
        ret z                   ; 0: never drawn anyway
        cp  8
        ld  a, c
        jr  z, fe_fwh_1
        cp  FE_OWN_BORDERS      ; land
        scf
        ret z
        or  a
        ret
fe_fwh_1:  cp  FE_OWN_LAND         ; a border
        scf
        ret z
        or  a
        ret

; A = FA_ territory, B = rows further down: into the background.
fe_terr:
        push af
        call fe_tgt_bg
        pop af
        call fe_terr_draw
        jp  fe_mark_both

; A = FA_ territory: its pens into the cache A page ($C000 on, w * 4
; bytes a row); fe_tcol, fe_tyraw, fe_tw, fe_th say where and how big.
fe_terr_unpack:
        call fe_map_asset
        ld  a, (hl)
        ld  (fe_tcol), a
        inc hl
        ld  a, (hl)
        ld  (fe_tyraw), a
        inc hl
        ld  a, (hl)
        ld  (fe_tw), a
        inc hl
        ld  a, (hl)
        ld  (fe_th), a
        inc hl
        push hl
        ld  a, (fe_tw)
        add a, a
        add a, a
        ld  e, a
        ld  a, (fe_th)
        call fe_mul8
        ld  de, $C000
        add hl, de
        ld  (fe_lz_end), hl
        ld  a, PG_FE_CACHE_A
        call map_w3
        pop hl
        jp  fe_unlz

; A = FA_ territory, B = rows down: into fe_dst_a/b, cut at line 200.
; -> B, C, D, E its rectangle.
fe_terr_draw:
        push bc
        call fe_terr_unpack
        pop bc
        ld  a, (fe_tyraw)
        add a, b
        jr  c, fe_ftd_none
        cp  200
        jr  nc, fe_ftd_none
        ld  (fe_ty), a
        ld  a, (fe_th)
        ld  c, a                ; its height
        ld  a, PG_FE_CACHE_A
        call map_w1
        ld  hl, $4000
        ld  a, (fe_ty)
        ld  b, a
        ld  a, 200
        sub b
        cp  c
        jr  nc, fe_ftd_1
        ld  c, a
fe_ftd_1:  ld  a, c
        ld  (fe_th), a
        ld  (fe_tdata), hl
        ld  a, (fe_dst_a)
        call map_w3
        ld  ix, (fe_tdata)
        call fe_ftd_half
        ld  a, (fe_dst_b)
        call map_w3
        ld  ix, (fe_tdata)
        inc ix
        call fe_ftd_half
        ld  a, (fe_tcol)
        ld  b, a
        ld  a, (fe_ty)
        ld  c, a
        ld  a, (fe_tw)
        ld  d, a
        ld  a, (fe_th)
        ld  e, a
        ret
fe_ftd_none:
        ld  de, 0
        ret
fe_ftd_half:
        ld  a, (fe_ty)
        ld  (fe_trow), a
        ld  a, (fe_th)
        ld  (fe_rows), a
fe_ftd_row:
        ld  a, (fe_tcol)
        ld  b, a
        ld  a, (fe_trow)
        ld  c, a
        call fe_rowaddr
        ex  de, hl
        ld  a, d
        or  $C0
        ld  d, a
        ld  a, c
        and 1
        add a, HIGH fe_owntab + 1
        ld  c, a                ; the data table for this row's parity
        push ix
        ld  a, (fe_tw)
        ld  b, a
fe_ftd_col:
        ld  a, (ix + 0)
        or  a
        jr  z, fe_ftd_2
        ld  l, a
        ld  h, HIGH fe_owntab
        ld  a, (de)
        and (hl)
        ld  h, c
        or  (hl)
        ld  (de), a
fe_ftd_2:  ld  a, (ix + 2)
        or  a
        jr  z, fe_ftd_3
        ld  l, a
        ld  h, HIGH fe_owntab
        set 5, d
        ld  a, (de)
        and (hl)
        ld  h, c
        or  (hl)
        ld  (de), a
        res 5, d
fe_ftd_3:  inc ix
        inc ix
        inc ix
        inc ix
        inc de
        djnz fe_ftd_col
        pop ix
        ld  a, (fe_tw)
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        add ix, de
        ld  hl, fe_trow
        inc (hl)
        ld  hl, fe_rows
        dec (hl)
        jr  nz, fe_ftd_row
        ret

; ----------------------------------------------------------------- text

; A = FA_ font, D = ink A's pen, E = ink B's, C = ink C's (the shadow).
fe_ink:
        ld  (fe_font), a
        ld  a, d
        ld  (fe_pens + 1), a
        ld  a, e
        ld  (fe_pens + 2), a
        ld  a, c
        ld  (fe_pens + 3), a
        xor a
        ld  (fe_pens), a
        ld  hl, fe_inktab
        ld  d, 0                ; the left pixel's code
fe_fik_l:  ld  e, 0                ; the right pixel's
fe_fik_r:  xor a
        or  d
        ld  a, 0
        jr  nz, fe_fik_1
        ld  a, $47              ; keep the screen's left pixel
fe_fik_1:  inc e
        dec e
        jr  nz, fe_fik_2
        or  $B8                 ; and its right one
fe_fik_2:  ld  (hl), a
        inc hl
        push hl
        ld  hl, fe_pens
        ld  a, l
        add a, d
        ld  l, a
        jr  nc, fe_fik_3
        inc h
fe_fik_3:  ld  a, (hl)             ; the left pen
        ld  b, a
        and 7
        bit 3, b
        jr  z, fe_fik_4
        or  $40
fe_fik_4:  ld  c, a
        ld  hl, fe_pens
        ld  a, l
        add a, e
        ld  l, a
        jr  nc, fe_fik_5
        inc h
fe_fik_5:  ld  a, (hl)             ; the right pen
        ld  b, a
        and 7
        add a, a
        add a, a
        add a, a
        bit 3, b
        jr  z, fe_fik_6
        or  $80
fe_fik_6:  or  c
        pop hl
        ld  (hl), a
        inc hl
        inc e
        ld  a, e
        cp  4
        jr  nz, fe_fik_r
        inc d
        ld  a, d
        cp  4
        jr  nz, fe_fik_l
        ret

; HL = a string ended by $FF, B = column, C = y: into the background.
fe_text:
        push hl
        ld  d, 0
fe_ftx_1:  ld  a, (hl)
        cp  $FF
        jr  z, fe_ftx_2
        inc hl
        inc d
        jr  fe_ftx_1
fe_ftx_2:  pop hl
        ld  a, d
; ... A = its length.
fe_textn:
        or  a
        ret z
        ld  (fe_tlen), a
        ld  (fe_tstr), hl
        ld  d, a
        ld  e, 8
        push bc
        call fe_mark_both
        pop bc
        call fe_rowaddr
        ld  (fe_toff), hl
        ld  a, (fe_font)
        call fe_map_asset
        ld  (fe_tfont), hl
        ld  a, PG_FE_BG_A
        call map_w3
        ld  c, 0
        call fe_ftn_half
        ld  a, PG_FE_BG_B
        call map_w3
        ld  c, 8
fe_ftn_half:
        ld  hl, (fe_toff)
        ld  a, h
        or  $C0
        ld  d, a
        ld  e, l
        ld  hl, (fe_tstr)
        ld  a, (fe_tlen)
        ld  b, a
fe_ftn_c:  push bc
        push hl
        push de
        ld  a, (hl)
        and $7F
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  b, 0
        add hl, bc
        ld  bc, (fe_tfont)
        add hl, bc
        ld  b, 8
fe_ftn_row:
        ld  a, (hl)
        inc hl
        or  a
        jr  z, fe_ftn_next
        push hl
        ld  c, a
        and $F0
        rrca
        rrca
        rrca
        jr  z, fe_ftn_lo
        ld  l, a
        ld  h, HIGH fe_inktab
        ld  a, (de)
        and (hl)
        inc l
        or  (hl)
        ld  (de), a
fe_ftn_lo: ld  a, c
        and $0F
        jr  z, fe_ftn_done
        add a, a
        ld  l, a
        ld  h, HIGH fe_inktab
        set 5, d
        ld  a, (de)
        and (hl)
        inc l
        or  (hl)
        ld  (de), a
        res 5, d
fe_ftn_done:
        pop hl
fe_ftn_next:
        ld  a, e
        add a, 40
        ld  e, a
        jr  nc, fe_ftn_1
        inc d
fe_ftn_1:  djnz fe_ftn_row
        pop de
        inc de
        pop hl
        inc hl
        pop bc
        djnz fe_ftn_c
        ret

; HL = a string's address, A = its page (text.inc; bit 7: centre it in
; the 12 columns from B), B = column, C = y: into the background.  For
; other banks, whose own memory this bank cannot see.
fe_str_at:
        push bc
        push af
        and $7F
        ld  c, a
        call fe_copy_str
        pop af
        pop bc
        bit 7, a
        jp  z, fe_text
        push hl
        ld  d, 0
fe_fsa_1:  ld  a, (hl)
        cp  $FF
        jr  z, fe_fsa_2
        inc hl
        inc d
        jr  fe_fsa_1
fe_fsa_2:  pop hl
        ld  a, 12
        sub d
        jp  c, fe_text
        srl a
        add a, b
        ld  b, a
        jp  fe_text

; A = a character, B = column, C = y: into the background.
fe_char_at:
        ld  (fe_ch), a
        ld  hl, fe_ch
        ld  a, 1
        jp  fe_textn

; HL = a number, A = how many of its five right-aligned characters to
; print (the last A), B = the first one's column, C = y.
fe_num_at:
        push bc
        push af
        call fe_num5
        pop af
        pop bc
        ld  e, a
        ld  a, 5
        sub e
        ld  hl, fe_numbuf
        add a, l
        ld  l, a
        jr  nc, fe_fna_1
        inc h
fe_fna_1:  ld  a, e
        jp  fe_textn

; HL = a string's address, C = its page (text.inc) -> fe_strbuf, HL = it.
fe_copy_str:
        ld  a, c
        call map_w1
        ld  de, fe_strbuf
        ld  bc, FE_STRMAX - 1
fe_fcs_1:  ld  a, (hl)
        ld  (de), a
        cp  $FF
        jr  z, fe_fcs_2
        inc hl
        inc de
        dec bc
        ld  a, b
        or  c
        jr  nz, fe_fcs_1
        ld  a, $FF
        ld  (de), a
fe_fcs_2:  ld  hl, fe_strbuf
        ret

; HL = a txt_ group's index table, C = its page, A = the entry -> HL = the
; string's address, C = its page.
fe_txt_addr:
        push af
        ld  a, c
        call map_w1
        pop af
        ld  e, a
        ld  d, 0
        add hl, de
        add hl, de
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        ex  de, hl
        ret

; The same, the string copied into fe_strbuf (HL = fe_strbuf).
fe_txt:
        call fe_txt_addr
        jr  fe_copy_str

; HL = a number -> fe_numbuf: five characters, right-aligned, no leading
; zeros; HL = the first digit's place, A = how many digits.
fe_num5:
        ld  de, fe_numbuf
        ld  bc, 10000
        call fe_fnm_digit
        ld  bc, 1000
        call fe_fnm_digit
        ld  bc, 100
        call fe_fnm_digit
        ld  bc, 10
        call fe_fnm_digit
        ld  a, l
        add a, '0'
        ld  (de), a
        ld  hl, fe_numbuf
        ld  b, 5
fe_fnm_s:  ld  a, (hl)
        cp  '0'
        jr  nz, fe_fnm_e
        ld  a, b
        dec a
        jr  z, fe_fnm_e
        ld  (hl), ' '
        inc hl
        djnz fe_fnm_s
fe_fnm_e:  ld  a, b
        ret
fe_fnm_digit:
        ld  a, '0' - 1
fe_fnd_1:  inc a
        or  a
        sbc hl, bc
        jr  nc, fe_fnd_1
        add hl, bc
        ld  (de), a
        inc de
        ret

; ------------------------------------------------------------- palettes

fe_pal:
        call fe_map_asset
        ld  a, (hl)             ; the steps: the colours are the last
        inc hl
        dec a
        add a, a
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        add hl, de
        jp  vid_palette
fe_pal_black:
        ld  hl, fe_black
        jp  vid_palette

; A = FA_ fade, C = frames a step: from black to the screen's colours.
fe_fade_in:
        ld  (fe_fade), a
        call fe_map_asset
        ld  b, (hl)
        inc hl
fe_ffi_1:  push bc
        push hl
        ld  b, c
        call fe_wait
        ld  a, (fe_fade)
        call fe_map_asset       ; (fe_wait keeps window 1, but be sure)
        pop hl
        push hl
        call vid_palette
        pop hl
        ld  de, 16
        add hl, de
        pop bc
        djnz fe_ffi_1
        ret

; A = FA_ fade, C = frames a step: from the screen's colours to black.
fe_fade_out:
        ld  (fe_fade), a
        call fe_map_asset
        ld  b, (hl)
        inc hl
        ld  a, b
        dec a
        add a, a
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        add hl, de              ; the last step: the colours themselves
        dec b
        jr  z, fe_ffo_black
fe_ffo_1:  push bc
        push hl
        ld  b, c
        call fe_wait
        ld  a, (fe_fade)
        call fe_map_asset
        pop hl
        ld  de, -16
        add hl, de
        push hl
        call vid_palette
        pop hl
        pop bc
        djnz fe_ffo_1
fe_ffo_black:
        ld  b, c
        call fe_wait
        jp  fe_pal_black

; The screen now showing fades out (fe_curfade).
fe_fade_out_cur:
        ld  a, (fe_curfade)
        cp  $FF
        ret z                   ; nothing up yet
        ld  c, 3
        jr  fe_fade_out

; B = frames (each a fe_frame while the starfield scrolls, so it goes on
; through the fades).
fe_wait:
        push hl
fe_fwt_1:  ld  a, (fe_starson)
        or  a
        jr  z, fe_fwt_2
        push bc
        call fe_frame
        pop bc
        jr  fe_fwt_3
fe_fwt_2:  FCALL snd_idle          ; vid_wait_frame, moving the music on
fe_fwt_3:  djnz fe_fwt_1
        pop hl
        ret

; -> A: a number from nothing in particular (not the game's generator,
; which the battle's replays depend on).
fe_rand:
        ld  a, (fe_seed)
        ld  b, a
        add a, a
        add a, a
        add a, b
        inc a
        ld  (fe_seed), a
        ld  b, a
        ld  a, (frame_count)
        xor b
        ret

; -> A a random byte for the mentat's mouth: a 16-bit xorshift (7, 9, 8),
; since fe_rand, a step of 5x+1 mixed with frame_count, falls into short
; cycles when it is drawn at intervals that it chose itself.  Clobbers HL.
fe_mrand:
        ld  hl, (fe_mseed)
        ld  a, h
        rra
        ld  a, l
        rra
        xor h
        ld  h, a
        ld  a, l
        rra
        ld  a, h
        rra
        xor l
        ld  l, a
        xor h
        ld  h, a
        ld  (fe_mseed), hl
        ret

; B = the low bound, C = the high -> A between them, as math_rand_between
; $000C0C draws it: a random byte masked by $7F, $3F ... until it is below
; C - B + 1.  Clobbers BC, DE.
fe_rand_between:
        push bc
        call fe_mrand
        pop bc
        ld  e, a
        ld  a, c
        sub b
        inc a
        ld  d, a                ; the range
        ld  c, $FF
fe_frb_1:  ld  a, e
        cp  d
        jr  c, fe_frb_2
        srl c
        and c
        ld  e, a
        jr  nz, fe_frb_1
fe_frb_2:  add a, b
        ret

; A = a screen's FA_PAL_: black palette, the background drawn by the
; caller next; remembers it for fe_begin (a screen's FA_PAL_ is its fade
; table, FA_FADE_ the same number: the colours are the fade's last step).
fe_prepare:
        ld  (fe_curpal), a
        ld  (fe_curfade), a
        call fe_pal_black
        jp  fe_bg_clear

; The background on the screens and the screen's colours faded in.
fe_begin:
        call fe_show
        ld  a, (fe_curfade)
        ld  c, 2
        jp  fe_fade_in

; ========================================================= the opening

; The logos, then PRESENT, over the starfield scrolling by (menu_title
; $017414 starts it wrapping round as the logos fade in).  -> carry if a
; button cut it short.
fe_logos:
        ld  a, FA_PAL_LOGO
        call fe_prepare
        ld  a, FA_LOGO
        call fe_pic
        call fe_scroll_start
        xor a                   ; the logos' lines and colours
        call fe_stars_on
        call fe_begin
        ld  b, 200
        call fe_frames
        and $F0
        jr  nz, fe_flg_skip
        call fe_fade_out_cur
        ld  a, FA_PAL_LOGO
        call fe_prepare
        ld  a, FA_PRESENT
        call fe_pic
        call fe_show
        ld  a, FA_FADE_LOGO
        ld  c, 6
        call fe_fade_in
        ld  b, 100
        call fe_frames
        and $F0
        jr  nz, fe_flg_skip
        ld  a, FA_FADE_LOGO
        ld  c, 6
        call fe_fade_out
        or  a
        ret
fe_flg_skip:
        call fe_stars_off
        scf
        ret

; The title: the starfield stops wrapping and brings the planet in with
; it (menu_scroll_release, then menu_scroll_poll until it is there), the
; ship flies in, then the words.  A button goes straight to the menu.
fe_title_intro:
        ld  a, FA_PAL_TITLE
        call fe_prepare
        call fe_show
        ld  a, FA_PAL_TITLE
        call fe_pal
        ld  a, FA_TITLE_PLANET
        call fe_unpack          ; the planet in the cache for fe_stars
        ld  a, 1                ; the title's lines and colours
        call fe_stars_on
        ld  a, 1
        ld  (fe_splanet), a
        xor a
        ld  (fe_skeep), a       ; menu_scroll_release
        call pad_take
fe_fti_slide:
        call fe_frame
        call pad_take
        and $F0
        jr  nz, fe_fti_cut
        call fe_scroll_there
        jr  nz, fe_fti_slide
        ; at rest: the planet among the stars, the picture of it
        call fe_stars_off
        ld  a, FA_TITLE_REST
        call fe_pic
        ld  b, 100
        call fe_frames
        and $F0
        jr  nz, fe_title_still
        ; the fly-in: 23 frames, 3 frames each
        xor a
        ld  (fe_i), a
fe_fti_ship:
        ld  a, (fe_i)
        cp  14                  ; the words come as it passes the planet
        jr  nz, fe_fti_s1
        ld  a, FA_TITLE_WORDS
        call fe_pic
fe_fti_s1:
        ld  a, (fe_i)
        add a, FA_SHIP_0
        ld  b, $FF
        call fe_q_spr
        ld  b, 3
        call fe_frames_q
        and $F0
        jr  nz, fe_title_still
        ld  a, (fe_i)
        inc a
        ld  (fe_i), a
        cp  23
        jr  nz, fe_fti_ship
        ld  b, 200              ; the menu some seconds later
        call fe_frames
        ; fall into fe_title_still

fe_fti_cut:
        call fe_stars_off
; The title as it stays: the planet, the words, the menu.
fe_title_still:
        ld  a, FA_PAL_TITLE
        ld  (fe_curpal), a
        ld  (fe_curfade), a
        ld  a, FA_TITLE_WORDS
        call fe_pic
        ld  a, FA_FONT8
        ld  d, PN_TITLE_WHITE
        ld  e, d
        ld  c, 0
        call fe_ink
        FE_STR txt_ui_title_start_game
        ld  bc, 16 * 256 + FE_TITLE_PTR_Y - 1
        call fe_text
        FE_STR txt_ui_title_options
        ld  bc, 16 * 256 + FE_TITLE_PTR_Y + 7
        call fe_text
        FE_STR txt_ui_title_tutorial
        ld  bc, 16 * 256 + FE_TITLE_PTR_Y + 15
        call fe_text
        FE_STR txt_port_title_redefine
        ld  bc, 16 * 256 + FE_TITLE_PTR_Y + 23
        call fe_text
        ld  a, FA_PAL_TITLE
        jp  fe_pal

; ----------------------------------------------------------- the stars
;
; Plane B of the opening is a starfield 1024 pixels wide with the planet
; in it, and menu_title $017414 scrolls it: menu_scroll_start $017BD6 sets
; it going left from -1, speeding up by 1/32 pixel a frame to 3, and
; wrapping round to -1 when it passes -320 (where the field repeats);
; menu_scroll_release lets it pass, and menu_scroll_vblank $017C32 then
; brakes it from 5.5 pixels a frame to half a pixel onto -704, the planet
; at rest.  fe_scroll_* is that, a step a frame by frame_count, in 8.8
; fixed point (every speed the cartridge uses is a whole 256th).  While
; fe_starson is set fe_frame draws the stars (FA_STARS) over the
; background, on its black pixels only - they are behind everything -
; and with fe_splanet the planet, blitted from the cache at its plane x
; plus the scroll.

FS_TARGET       EQU -704        ; menu_title's $FD40
FS_PLANET_X     EQU 784         ; the planet picture's plane x
FS_MAX          EQU 32          ; stars a screen remembers

fe_scroll_start:
        ld  a, $FF              ; $FFFFFFFF
        ld  (fe_ss), a
        ld  hl, -1
        ld  (fe_ss + 1), hl
        ld  hl, $0080           ; $8000: half a pixel a frame
        ld  (fe_sv), hl
        ld  a, 1
        ld  (fe_swrap), a
        ld  (fe_skeep), a
        xor a
        ld  (fe_sbrake), a
        ld  (fe_splanet), a
        ld  a, (frame_count)
        ld  (fe_sframe), a
        ret

; -> Z once the planet is at rest (menu_scroll_poll's 1).
fe_scroll_there:
        ld  hl, (fe_ss + 1)
        ld  de, -FS_TARGET
        add hl, de
        ld  a, h
        or  l
        ret nz
        ld  a, (fe_ss)
        or  a
        ret

; A = the screen's stars (0 the logos' lines and colours, 1 the title's):
; drawn from the next frame on.
fe_stars_on:
        push af
        ld  a, FA_STARS
        call fe_map_asset
        ld  e, (hl)             ; the stars
        ld  d, 0
        inc hl
        add hl, de
        add hl, de
        add hl, de
        add hl, de
        pop af
        or  a
        jr  z, fst_2
        inc hl                  ; the second screen's part: past the first's
        ld  b, 2
fst_1:     ld  e, (hl)
        ld  d, 0
        inc hl
        add hl, de
        add hl, de
        add hl, de
        djnz fst_1
fst_2:     ld  a, (hl)
        ld  (fe_stoff), a        ; the lines this screen drops
        inc hl
        ld  (fe_sglyph), hl     ; glyph 0's pixels, then glyph 1's
        call fe_stars_forget
        ld  a, 1
        ld  (fe_starson), a
        ret

fe_stars_off:
        xor a
        ld  (fe_starson), a
        ld  (fe_splanet), a
        ret

; The screens hold nothing of the starfield's (fe_show has copied the
; background over them).
fe_stars_forget:
        xor a
        ld  (fe_sl0), a
        ld  (fe_sl1), a
        dec a
        ld  (fe_spc0), a
        ld  (fe_spc1), a
        ret

; menu_scroll_vblank for every frame since the last call.
fe_scroll_update:
        ld  a, (fe_sframe)
        ld  b, a
        ld  a, (frame_count)
        ld  (fe_sframe), a
        sub b
        ret z
        ld  b, a
fsu_1:     push bc
        call fe_scroll_step
        pop bc
        djnz fsu_1
        ret

fe_scroll_step:
        ld  a, (fe_swrap)
        or  a
        jr  z, fss_move
        ld  hl, (fe_ss + 1)
        ld  de, 320
        add hl, de
        bit 7, h
        jr  z, fss_move         ; not past -320 yet
        ld  a, (fe_skeep)
        or  a
        jr  z, fss_brk
        ld  a, $FF              ; round again
        ld  (fe_ss), a
        ld  hl, -1
        ld  (fe_ss + 1), hl
        jr  fss_move
fss_brk:   xor a                   ; let go: brake onto the target
        ld  (fe_swrap), a
        inc a
        ld  (fe_sbrake), a
        ld  hl, $0588           ; $58800
        ld  (fe_sv), hl
fss_move:
        ld  hl, (fe_sv)
        ld  a, (fe_sbrake)
        or  a
        jr  nz, fss_brake
        ; speeding up: 1/32 more, 3 pixels at most (the speed itself is
        ; held at 4 here, which changes nothing: only its minimum with 3
        ; is ever used before the brake sets it)
        ld  de, 8
        add hl, de
        ld  de, $0400
        call fss_cmp
        jr  c, fss_m1
        ex  de, hl
fss_m1:    ld  (fe_sv), hl
        ld  de, $0300
        call fss_cmp            ; 3 pixels, or the speed if less
        jr  nc, fss_sub
        ex  de, hl
        jr  fss_sub
fss_brake:
        ld  de, -8
        add hl, de
        ld  (fe_sv), hl
        ld  de, $0080
        bit 7, h
        jr  nz, fss_b1          ; below nothing: half a pixel (bgt)
        ld  de, $0300
        call fss_cmp
        jr  nc, fss_b1          ; 3 or more: 3
        ld  de, $0081
        call fss_cmp
        ld  de, $0080
        jr  c, fss_b1           ; half a pixel or less: half a pixel
        ex  de, hl              ; else the speed
fss_b1:    call fss_sub
        ; on the target or past it: there
        ld  hl, (fe_ss + 1)
        ld  de, -FS_TARGET
        add hl, de
        bit 7, h
        jr  nz, fss_b2
        ld  a, h
        or  l
        ret nz
        ld  a, (fe_ss)
        or  a
        ret nz
fss_b2:    ld  hl, $0080
        ld  (fe_sv), hl
        xor a
        ld  (fe_ss), a
        ld  hl, FS_TARGET
        ld  (fe_ss + 1), hl
        ret
; HL, DE unsigned -> carry if HL < DE.  Keeps both.
fss_cmp:
        push hl
        or  a
        sbc hl, de
        pop hl
        ret
; The scroll less DE (8.8).
fss_sub:
        ld  a, (fe_ss)
        sub e
        ld  (fe_ss), a
        ld  hl, (fe_ss + 1)
        ld  e, d
        ld  d, 0
        sbc hl, de
        ld  (fe_ss + 1), hl
        ret

; fe_frame, after the background's rectangles: the scroll brought up to
; date, this screen's stars of last time taken off, the planet.
fe_stars_under:
        push ix
        call fe_scroll_update
        call fs_list            ; HL = this screen's stars, A = how many
        or  a
        jr  z, fsn_3
        ld  b, a
fsn_1:     push bc
        push hl
        ld  b, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  d, (hl)
        ld  e, 8
        ld  a, 200
        sub c
        cp  e
        jr  nc, fsn_2
        ld  e, a
fsn_2:     call fe_copy_rect
        pop hl
        inc hl
        inc hl
        inc hl
        pop bc
        djnz fsn_1
fsn_3:     call fs_list
        dec hl
        ld  (hl), 0
        ld  a, (fe_splanet)
        or  a
        call nz, fs_planet
        pop ix
        ret

; -> HL = the drawn screen's star list (past its count), A = the count.
fs_list:
        ld  hl, fe_sl0
        ld  a, (draw_a)
        cp  PG_SCR0_A
        jr  z, fsl_1
        ld  hl, fe_sl1
fsl_1:     ld  a, (hl)
        inc hl
        ret

; The planet where the scroll has it: blitted (it is opaque), and put
; back what it covered on this screen last time right of where it ends
; now.
fs_planet:
        ld  hl, (fe_ss + 1)
        ld  de, FS_PLANET_X
        add hl, de              ; its x (80-783)
        ld  de, 320
        call fss_cmp
        ld  a, 40
        jr  nc, fsp_1           ; not on the screen yet
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ld  a, l
fsp_1:     ld  (fe_spcol), a
        cp  40
        jr  nc, fsp_2
        ld  b, a
        ld  a, (fe_py)
        ld  c, a
        call fe_blit
fsp_2:     ld  hl, fe_spc0
        ld  a, (draw_a)
        cp  PG_SCR0_A
        jr  z, fsp_3
        ld  hl, fe_spc1
fsp_3:     ld  c, (hl)             ; last time's column ($FF none)
        ld  a, (fe_spcol)
        ld  (hl), a
        ld  a, c
        cp  40
        ret nc
        ld  hl, fe_pw
        add a, (hl)             ; its right end then
        cp  41
        jr  c, fsp_4
        ld  a, 40
fsp_4:     ld  e, a
        ld  a, (fe_spcol)
        add a, (hl)             ; and now
        cp  e
        ret nc
        ld  b, a
        ld  a, e
        sub b
        ld  d, a
        ld  a, (fe_py)
        ld  c, a
        ld  a, (fe_ph)
        ld  e, a
        jp  fe_copy_rect

; fe_frame, before the flip: the stars, on the black of the screen.
fe_stars_over:
        push ix
        ld  a, FA_STARS
        call fe_map_asset
        ld  a, (hl)
        ld  (fe_scnt), a
        inc hl
        ld  (fe_sptr), hl
fsv_star:
        ld  hl, (fe_sptr)
        ld  e, (hl)
        inc hl
        ld  d, (hl)             ; its plane x
        inc hl
        ld  a, (hl)
        ld  (fe_sy), a          ; its y
        inc hl
        ld  a, (hl)
        ld  (fe_sg), a          ; its glyph
        inc hl
        ld  (fe_sptr), hl
        ; on the screen at (plane x + the scroll) mod 1024
        ld  hl, (fe_ss + 1)
        add hl, de
        ld  a, h
        and 3
        ld  h, a
        ld  de, 320
        call fss_cmp
        jr  c, fsv_x
        ld  de, 1024 - 8
        call fss_cmp
        jr  c, fsv_next         ; off the screen
        ld  de, -1024
        add hl, de              ; just left of it
fsv_x:     ld  (fe_sx), hl
        ld  a, (fe_stoff)
        ld  b, a
        ld  a, (fe_sy)
        sub b
        jr  c, fsv_next         ; (above the screen: left out)
        cp  200
        jr  nc, fsv_next
        ld  (fe_sy), a
        call fs_draw
fsv_next:
        ld  hl, fe_scnt
        dec (hl)
        jr  nz, fsv_star
        pop ix
        ret

; A star: glyph fe_sg at fe_sx (-7 to 319), fe_sy, pixel by pixel on the
; black; the cells it touched go on the screen's list.
fs_draw:
        ld  hl, (fe_sglyph)
        ld  a, (fe_sg)
        or  a
        jr  z, fsd_1
        ld  e, (hl)             ; past glyph 0's pixels
        ld  d, 0
        inc hl
        add hl, de
        add hl, de
        add hl, de
fsd_1:     ld  b, (hl)
        inc hl
fsd_px:    push bc
        ld  e, (hl)             ; dx
        inc hl
        ld  a, (fe_sy)
        add a, (hl)             ; y + dy
        inc hl
        ld  c, (hl)             ; the pen
        inc hl
        push hl
        cp  200
        jr  nc, fsd_skip
        ld  (fe_spy), a
        ld  d, 0
        ld  hl, (fe_sx)
        add hl, de
        bit 7, h
        jr  nz, fsd_skip
        ld  de, 320
        call fss_cmp
        jr  nc, fsd_skip
        ld  a, c
        call fs_pixel
fsd_skip:
        pop hl
        pop bc
        djnz fsd_px
        ; its cells: the column of its left end, one or two wide
        call fs_list
        cp  FS_MAX
        ret nc
        inc a
        dec hl
        ld  (hl), a
        inc hl
        dec a
        ld  e, a
        ld  d, 0
        add hl, de
        add hl, de
        add hl, de
        ex  de, hl
        ld  hl, (fe_sx)
        ld  b, 1
        bit 7, h
        ld  a, 0
        jr  nz, fsd_2           ; partly left of the screen: column 0
        ld  a, l
        and 7
        jr  z, fsd_3
        inc b
fsd_3:     srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ld  a, l
fsd_2:     ld  (de), a             ; the column
        inc de
        ld  c, a
        ld  a, (fe_sy)
        ld  (de), a             ; the line
        inc de
        ld  a, c
        add a, b
        cp  41
        jr  c, fsd_4
        dec b
fsd_4:     ld  a, b
        ld  (de), a             ; the width
        ret

; HL = x (0-319), fe_spy = y, A = a pen: the pixel on the drawn screen if
; it is black there.
fs_pixel:
        ld  c, a
        ld  a, l
        and 1
        ld  (fe_sright), a
        ld  a, l
        rrca
        and 3
        ld  (fe_splane), a      ; the plane: (x >> 1) & 3
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        push bc
        ld  b, l
        ld  a, (fe_spy)
        ld  c, a
        call fe_rowaddr
        pop bc
        ld  a, h
        or  $C0
        ld  h, a
        ld  a, (fe_splane)
        bit 1, a
        jr  z, fpx_1
        set 5, h                ; planes 2 and 3
fpx_1:     and 1
        ld  a, (draw_a)
        jr  z, fpx_2
        ld  a, (draw_b)         ; planes 1 and 3
fpx_2:     call map_w3
        ld  a, c
        and 7
        ld  b, a
        ld  a, (fe_sright)
        or  a
        jr  nz, fpx_r
        ld  a, (hl)
        and $47
        ret nz                  ; something there already
        ld  a, b
        bit 3, c
        jr  z, fpx_l1
        or  $40
fpx_l1:    or  (hl)
        ld  (hl), a
        ret
fpx_r:     ld  a, (hl)
        and $B8
        ret nz
        ld  a, b
        add a, a
        add a, a
        add a, a
        bit 3, c
        jr  z, fpx_r1
        or  $80
fpx_r1:    or  (hl)
        ld  (hl), a
        ret

; B = frames: as fe_frames, with the sprites queued now drawn on each.
fe_frames_q:
        ld  a, (fe_qn)
        ld  (fe_qkeep), a
        ld  hl, fe_queue
        ld  de, fe_qsave
        push bc
        ld  bc, FE_QMAX * 4
        ldir
        pop bc
        xor a
        ld  (fe_keys), a
fe_ffq_1:  push bc
        ld  a, (fe_qkeep)
        ld  (fe_qn), a
        ld  hl, fe_qsave
        ld  de, fe_queue
        ld  bc, FE_QMAX * 4
        ldir
        call fe_frame
        call pad_take
        ld  hl, fe_keys
        or  (hl)
        ld  (hl), a
        pop bc
        and $F0
        ret nz
        djnz fe_ffq_1
        ld  a, (fe_keys)
        ret

; The menu: START GAME, OPTIONS, TUTORIAL.  -> A = the row, $FF after 900
; frames untouched.
fe_title_menu:
        call pad_take
        xor a
        ld  (fe_sel), a
        ld  hl, 900
        ld  (fe_idle), hl
fe_ftm_loop:
        ; the pointer: five frames, a new one every six
        ld  a, (frame_count)
        ld  b, 0
fe_ftm_d6: inc b
        sub 6
        jr  nc, fe_ftm_d6
        ld  a, b
fe_ftm_m5: sub 5
        jr  nc, fe_ftm_m5
        add a, 5 + FA_TITLE_POINTER_0
        push af
        ld  a, (fe_sel)
        add a, a
        add a, a
        add a, a
        add a, FE_TITLE_PTR_Y
        ld  c, a
        ld  b, FE_TITLE_PTR_COL
        pop af
        call fe_q_spr
        call fe_frame
        ld  hl, (fe_idle)
        dec hl
        ld  (fe_idle), hl
        ld  a, h
        or  l
        ld  a, $FF
        ret z
        call pad_take
        or  a
        jr  z, fe_ftm_loop
        ld  hl, 900
        ld  (fe_idle), hl
        ld  b, a
        and $F0
        jr  nz, fe_ftm_choose
        ld  a, (fe_sel)
        bit 0, b
        jr  z, fe_ftm_1
        dec a
        jp  p, fe_ftm_mv
        ld  a, 3
        jr  fe_ftm_mv
fe_ftm_1:  bit 1, b
        jr  z, fe_ftm_loop
        inc a
        cp  4
        jr  c, fe_ftm_mv
        xor a
fe_ftm_mv: ld  (fe_sel), a
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        jr  fe_ftm_loop
fe_ftm_choose:
        ld  a, SFX_POSITIVE_SELECT
        FCALL snd_sfx
        ld  a, (fe_sel)
        push af
        call fe_fade_out_cur
        pop af
        ret

; =================================================== REDEFINE KEYS
;
; The port's own screen, from the title menu's fourth line (the cartridge
; has a pad and no such thing): the eight Mega Drive buttons in turn, each
; given the key pressed for it, in the title's colours on black.  A key
; already given is refused.  At the end the choice becomes WORLD's
; pad_keys - one key a button, the second place empty - which the frame
; interrupt reads (stub/input.asm); the joystick stays as it is.

FE_KEY_COL      EQU 6               ; the buttons' names
FE_KEY_NCOL     EQU 26              ; the keys'
FE_KEY_Y        EQU 52              ; the first button's line, 14 apart
FE_KEY_DY       EQU 14

fe_redefine:
        ld  a, FA_PAL_TITLE
        call fe_prepare
        call fe_ink_white
        FE_STR txt_port_keys_title
        ld  bc, 13 * 256 + 24
        call fe_text
        FE_STR txt_port_keys_prompt
        ld  bc, 10 * 256 + 172
        call fe_text
        xor a
fe_frd_label:
        ld  (fe_i), a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, fe_key_labels
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        ex  de, hl
        call fe_copy_str
        call fe_key_line
        ld  b, FE_KEY_COL
        call fe_text
        ld  a, (fe_i)
        inc a
        cp  8
        jr  c, fe_frd_label
        call fe_begin
        xor a
fe_frd_button:
        ld  (fe_i), a
        ; a question mark where its key goes
        call fe_ink_sand
        ld  hl, fe_key_ask
        call fe_key_line
        ld  b, FE_KEY_NCOL
        call fe_text
fe_frd_again:
        call fe_get_key         ; B = its half-row, C = its bit, A = key
        ld  (fe_kidx), a
        ; refused if a button before this one has it
        ld  hl, fe_newkeys
        ld  a, (fe_i)
        or  a
        jr  z, fe_frd_new
        ld  e, a
fe_frd_dup:
        ld  a, (hl)
        inc hl
        cp  b
        ld  a, (hl)
        inc hl
        jr  nz, fe_frd_dup1
        cp  c
        jr  z, fe_frd_taken
fe_frd_dup1:
        dec e
        jr  nz, fe_frd_dup
fe_frd_new:
        ld  (hl), b
        inc hl
        ld  (hl), c
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        call fe_key_clear_msg
        ; its name in place of the question mark
        call fe_key_line
        ld  b, FE_KEY_NCOL
        ld  d, 6
        ld  e, 8
        xor a
        call fe_fill
        FE_STR txt_port_keys_names
        ld  a, (fe_kidx)
        ld  e, a
        add a, a
        add a, a
        add a, e                ; 5 characters a key
        ld  e, a
        ld  d, 0
        add hl, de
        call fe_key_line
        ld  b, FE_KEY_NCOL
        ld  a, 5
        call fe_textn
        ld  a, (fe_i)
        inc a
        cp  8
        jr  c, fe_frd_button
        ; the new keys go in: one a button
        ld  hl, fe_newkeys
        ld  de, pad_keys
        ld  b, 8
        di
fe_frd_set:
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        ld  a, (hl)
        ld  (de), a
        inc hl
        inc de
        xor a
        ld  (de), a
        inc de
        ld  (de), a
        inc de
        djnz fe_frd_set
        ei
        ; the last name on both screens, a second to see it (the keys
        ; pressed meanwhile - the last one among them - forgotten)
        call fe_frame
        call fe_frame
        ld  b, 50
        call fe_wait
        call pad_take
        jp  fe_fade_out_cur
fe_frd_taken:
        ld  a, SFX_INVALID_SELECT
        FCALL snd_sfx
        call fe_ink_sand
        FE_STR txt_port_keys_taken
        ld  bc, 11 * 256 + 184
        call fe_text
        call fe_frame
        jp  fe_frd_again

; The "that key is taken" line gone.
fe_key_clear_msg:
        ld  bc, 11 * 256 + 184
        ld  de, 18 * 256 + 8
        xor a
        jp  fe_fill

; -> C = the line of button fe_i.  Keeps HL.
fe_key_line:
        ld  a, (fe_i)
        ld  c, a
        add a, a
        add a, a
        add a, a
        sub c
        add a, a                ; * FE_KEY_DY
        add a, FE_KEY_Y
        ld  c, a
        ret

fe_ink_white:
        ld  d, PN_TITLE_WHITE
        jr  fe_ink_8
fe_ink_sand:
        ld  d, PN_LOAD_BAR
fe_ink_8:
        ld  a, FA_FONT8
        ld  e, d
        ld  c, 0
        jp  fe_ink

; Wait for a key, the frames going on: every key up first, then the first
; one down.  A shift key held with another is the other one (a PC
; keyboard's arrows are CAPS SHIFT and a digit); a shift alone counts
; after a frame on its own.  -> B = its half-row, C = its bit, A = its
; number (half-row 0-7 from $FE, then bit 0-4: key names' order).
fe_get_key:
        call fe_frame
        xor a
        in  a, (PORT_FE)        ; every half-row at once
        cpl
        and $1F
        jr  nz, fe_get_key
fe_gk_wait:
        call fe_frame
        call fe_scan_key
        jr  nc, fe_gk_wait
        call fe_frame           ; a frame for the rest of a combination
        call fe_scan_key
        jr  nc, fe_gk_wait
        ret

; -> carry and B, C, A as fe_get_key if a key is down: the first not a
; shift, else a shift.
fe_scan_key:
        ld  e, 0                ; 0 - any found (then E = its number + 1)
        ld  b, $FE
        ld  d, 0                ; the key's number
fe_sk_row:
        ld  a, b
        in  a, (PORT_FE)
        cpl
        ld  c, 1
fe_sk_bit:
        rrca
        jr  nc, fe_sk_next
        ld  h, a
        ld  a, d
        or  a                   ; CAPS SHIFT
        jr  z, fe_sk_shift
        cp  36                  ; SYMBOL SHIFT
        jr  z, fe_sk_shift
        ld  a, d                ; the one
        scf
        ret
fe_sk_shift:
        ld  a, e
        or  a
        jr  nz, fe_sk_1
        ld  a, d
        inc a
        ld  e, a
        ld  a, b
        ld  (fe_kshift), a
        ld  a, c
        ld  (fe_kshift + 1), a
fe_sk_1:  ld  a, h
fe_sk_next:
        inc d
        sla c
        bit 5, c
        jr  z, fe_sk_bit
        rlc b
        jr  c, fe_sk_row        ; until $7F has been read
        ld  a, e
        or  a
        ret z                   ; nothing (no carry)
        ld  a, (fe_kshift)
        ld  b, a
        ld  a, (fe_kshift + 1)
        ld  c, a
        ld  a, e
        dec a
        scf
        ret

; The buttons' names (port.txt), in PAD_ order.
fe_key_labels:
        DW  txt_port_keys_up
        DB  $$txt_port_keys_up, 0
        DW  txt_port_keys_down
        DB  $$txt_port_keys_down, 0
        DW  txt_port_keys_left
        DB  $$txt_port_keys_left, 0
        DW  txt_port_keys_right
        DB  $$txt_port_keys_right, 0
        DW  txt_port_keys_a
        DB  $$txt_port_keys_a, 0
        DW  txt_port_keys_b
        DB  $$txt_port_keys_b, 0
        DW  txt_port_keys_c
        DB  $$txt_port_keys_c, 0
        DW  txt_port_keys_start
        DB  $$txt_port_keys_start, 0
fe_key_ask:
        DB  "?", $FF

; =================================================== the choice of house

; The crests; the mentat describes the house chosen and asks.  -> A = the
; house.
fe_choose_house:
        ld  a, $1C
        FCALL snd_music
        xor a
        ld  (fe_sel), a
fe_fch_crests:
        ld  a, FA_PAL_HOUSE
        call fe_prepare
        ld  a, FA_HOUSE
        call fe_pic
        call fe_begin
        call pad_take
fe_fch_loop:
        ; the highlight under the plate: three greys in turn
        ld  a, (frame_count)
        rrca
        rrca
        rrca
        and 3
        cp  3
        jr  c, fe_fch_1
        ld  a, 1
fe_fch_1:  add a, FA_HOUSE_HL_0
        push af
        ld  a, (fe_sel)
        ld  b, a
        add a, a
        add a, a
        add a, a
        add a, b
        add a, b
        add a, b
        add a, 4                ; column 4, 15 or 26
        ld  b, a
        ld  c, 136
        pop af
        call fe_q_spr
        call fe_frame
        call pad_take
        or  a
        jr  z, fe_fch_loop
        ld  b, a
        and $F0
        jr  nz, fe_fch_choose
        ld  a, (fe_sel)
        bit 2, b
        jr  z, fe_fch_2
        or  a
        jr  z, fe_fch_loop
        dec a
        jr  fe_fch_mv
fe_fch_2:  bit 3, b
        jr  z, fe_fch_loop
        cp  2
        jr  z, fe_fch_loop
        inc a
fe_fch_mv: ld  (fe_sel), a
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        jr  fe_fch_loop
fe_fch_choose:
        ld  a, SFX_POSITIVE_SELECT
        FCALL snd_sfx
        ld  a, (fe_sel)
        ld  hl, fe_fch_house
        add a, l
        ld  l, a
        jr  nc, fe_fch_3
        inc h
fe_fch_3:  ld  a, (hl)
        ld  (fe_house), a
        call fe_fade_out_cur
        ; the mentat of that house: the map before mission 1
        call fe_music_mentat
        ld  a, (fe_house)
        ld  b, a
        ld  c, 1
        call fe_mentat_screen
        ld  a, (fe_house)       ; its description is entry 0, 1 or 2
        call fe_say_entry
        ld  a, (fe_hs + 3)      ; YES, NO
        call fe_choose2
        push af
        call fe_fade_out_cur
        pop af
        or  a
        jr  z, fe_fch_yes
        ld  a, $1C
        FCALL snd_music
        jp  fe_fch_crests
fe_fch_yes:
        ld  a, (fe_house)
        ret
fe_fch_house:
        DB  1, 2, 0             ; Atreides, Ordos, Harkonnen from the left

; ============================================================ the mentat

; B = house, C = mission: his screen - the map with the owners before
; that mission (dim), him, his face; the palette up.
fe_mentat_screen:
        push bc
        ld  a, b
        ld  (fe_house), a
        ; fe_hs: this house's assets
        ld  l, b
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        ld  de, fe_houses
        add hl, de
        ld  de, fe_hs
        ld  bc, 8
        ldir
        ld  a, (fe_hs + 5)
        call fe_prepare
        pop bc
        ld  a, c
        ld  (fe_mission), a
        ld  a, (fe_hs + 6)      ; the dim owner tables
        call fe_map_owned
        ld  a, (fe_hs + 0)
        call fe_pic             ; him, over the map
        ld  a, (fe_hs + 1)
        call fe_pic
        ld  a, (fe_hs + 2)
        call fe_pic
        xor a
        ld  (fe_mouth), a
        ld  (fe_eyes), a
        ld  (fe_talking), a
        ld  a, 40
        ld  (fe_eye_t), a
        ld  a, (fe_hs + 5)
        ld  (fe_curpal), a
        ld  (fe_curfade), a
        call fe_show
        ld  a, (fe_hs + 7)
        ld  d, a
        ld  e, a
        ld  c, 0
        ld  a, FA_FONT8
        call fe_ink
        ld  a, (fe_curfade)
        ld  c, 2
        jp  fe_fade_in

; A = the first of four FA_ owner tables (nobody, H, A, O): the ten
; territories, owned as before mission fe_mission of fe_house, and the
; borders, into the background.
fe_map_owned:
        ld  (fe_ownbase), a
        xor a                   ; the borders: always the first line
        ld  (fe_ownmode), a
        ld  a, (fe_ownbase)
        call fe_own
        ld  a, FA_TERR_10
        ld  b, 0
        call fe_terr
        ld  a, FE_OWN_LAND
        ld  (fe_ownmode), a
        xor a
        ld  (fe_i), a
fe_fmo_1:  ld  a, (fe_i)
        call fe_owner_of
        ld  hl, fe_ownbase
        add a, (hl)
        call fe_own
        ld  a, (fe_i)
        add a, FA_TERR_0
        ld  b, 0
        call fe_terr
        ld  a, (fe_i)
        inc a
        ld  (fe_i), a
        cp  10
        jr  nz, fe_fmo_1
        xor a
        ld  (fe_ownmode), a
        ret

; A = a territory -> A = its owner before fe_mission (0-3), from
; tbl_campaign_owner (Atreides, Ordos, Harkonnen: ten rows of ten words).
fe_owner_of:
        ld  c, a
        ld  a, (fe_house)
        ld  hl, fe_fmo_set
        add a, l
        ld  l, a
        jr  nc, fe_foo_1
        inc h
fe_foo_1:  ld  a, (hl)             ; the table's first row
        ld  b, a
        ld  a, (fe_mission)
        dec a
        cp  10
        jr  c, fe_foo_2
        ld  a, 9
fe_foo_2:  add a, b
        ld  e, 20
        call fe_mul8
        ld  e, c
        ld  d, 0
        add hl, de
        add hl, de
        ld  de, tbl_campaign_owner
        add hl, de
        ld  a, (hl)
        ret
fe_fmo_set:
        DB  20, 0, 10           ; H, A, O

; -> A = the index of fe_house's briefing for fe_mission (txt_briefings).
fe_brief_index:
        ld  a, (fe_house)
        add a, a
        add a, a
        ld  hl, tbl_briefing_first
        add a, l
        ld  l, a
        jr  nc, fe_fbi_1
        inc h
fe_fbi_1:  ld  b, (hl)
        ld  a, (fe_mission)
        dec a
        add a, a
        add a, a
        add a, b
        ret

; A = an entry of txt_briefings: the mentat says it.
fe_say_entry:
        FE_TXT txt_briefings
        ; fall into fe_say

; The mentat says fe_strbuf a sentence at a time in the text box, by the
; clock as mentat_speak $01F9D6 does: first a wait of 30 frames and 15
; more for each sentence after the first; then each sentence, the mouth
; moving four frames a character, and a pause half as long again before
; the next.  A, B or C cuts the wait, a sentence or a pause short and goes
; straight on to the next.  The last sentence stays up.
fe_say:
        ld  hl, fe_strbuf
        ld  (fe_sp), hl
        call pad_take
        ld  b, 0                ; the sentences, counted
fe_fsy_n:  call fe_sentence
        jr  z, fe_fsy_wait0
        inc b
        ex  de, hl
        jr  fe_fsy_n
fe_fsy_wait0:
        ld  a, b
        or  a
        ret z
        ld  (fe_nsent), a
        ld  de, 30
        call fe_talk_from_now
fe_fsy_wait:
        call fe_face_tick
        call fe_frame
        call pad_take
        and $70
        jr  nz, fe_fsy_next
        ld  hl, (fe_talk)
        call fe_past
        jr  nc, fe_fsy_wait
        ld  de, 15
        call fe_talk_from_now
        ld  hl, fe_nsent
        dec (hl)
        jr  nz, fe_fsy_wait
fe_fsy_next:
        ld  hl, (fe_sp)
        call fe_sentence
        ret z
        ld  (fe_sp), hl
        ld  (fe_se), de
        ; the box cleared and the sentence in it
        xor a
        ld  bc, FE_BOX_COL * 256 + FE_BOX_Y
        ld  de, FE_BOX_W * 256 + 40
        call fe_fill
        call fe_print_wrapped
        ; the mouth: four frames a character
        ld  hl, (fe_se)
        ld  de, (fe_sp)
        or  a
        sbc hl, de
        add hl, hl
        add hl, hl
        ld  (fe_saylen), hl
        ex  de, hl
        call fe_talk_from_now
        ld  hl, (frame_count)   ; a new mouth at once
        dec hl
        ld  (fe_mouth_t), hl
        ld  a, 1
        ld  (fe_talking), a
fe_fsy_talk:
        call fe_face_tick
        call fe_frame
        call pad_take
        and $70
        ld  (fe_pad_cut), a
        jr  nz, fe_fsy_after
        ld  hl, (fe_talk)
        call fe_past
        jr  nc, fe_fsy_talk
fe_fsy_after:
        xor a
        ld  (fe_talking), a
        ld  hl, (fe_se)
        ld  (fe_sp), hl
        call fe_sentence
        jr  z, fe_fsy_last
        ld  a, (fe_pad_cut)     ; cut short: the next at once
        or  a
        jp  nz, fe_fsy_next
        ; a pause of half as long again as the sentence took
        ld  hl, (fe_saylen)
        ld  d, h
        ld  e, l
        srl h
        rr  l
        add hl, de
        ex  de, hl
        call fe_talk_from_now
fe_fsy_w:  call fe_face_tick
        call fe_frame
        call pad_take
        and $70
        jp  nz, fe_fsy_next
        ld  hl, (fe_talk)
        call fe_past
        jr  nc, fe_fsy_w
        jp  fe_fsy_next
fe_fsy_last:
        call fe_face_tick
        jp  fe_frame

; HL = a place in fe_strbuf -> HL = the next sentence's start (spaces
; skipped), DE = its end; Z if the text has ended.  A sentence ends at a
; '.', '!' or '?' that no space follows, or at the text's end.  Clobbers A.
fe_sentence:
        ld  a, (hl)
        cp  ' '
        jr  nz, fe_stc_s
        inc hl
        jr  fe_sentence
fe_stc_s:  cp  $FF
        ret z
        push hl
fe_stc_e:  ld  a, (hl)
        cp  $FF
        jr  z, fe_stc_end
        inc hl
        cp  '.'
        jr  z, fe_stc_p
        cp  '!'
        jr  z, fe_stc_p
        cp  '?'
        jr  nz, fe_stc_e
fe_stc_p:  ld  a, (hl)
        cp  '.'
        jr  z, fe_stc_e
        cp  '!'
        jr  z, fe_stc_e
        cp  '?'
        jr  z, fe_stc_e
        cp  ' '
        jr  z, fe_stc_e
fe_stc_end:
        ex  de, hl
        pop hl
        or  1                   ; NZ
        ret

; fe_talk = frame_count + DE.  Clobbers HL.
fe_talk_from_now:
        ld  hl, (frame_count)
        add hl, de
        ld  (fe_talk), hl
        ret

; HL = a time on frame_count -> C once it has gone by (frame_count - HL
; above 0, taken as a signed difference).  Clobbers A, DE, HL.
fe_past:
        ex  de, hl
        ld  hl, (frame_count)
        or  a
        sbc hl, de
        ret z                   ; NC
        ld  a, h
        rla
        ccf
        ret

; fe_sp .. fe_se into the box: lines of up to 36 characters, broken at
; spaces, five at most (Ordos 1's defeat text is the one that needs five;
; the mentat's portrait starts 32 lines lower).
fe_print_wrapped:
        ld  hl, (fe_sp)
        ld  c, FE_BOX_Y
fe_fpw_line:
        ld  a, (hl)
        cp  ' '
        jr  nz, fe_fpw_1
        inc hl
        jr  fe_fpw_line
fe_fpw_1:  ; what is left: fe_se - HL
        push hl
        ex  de, hl
        ld  hl, (fe_se)
        or  a
        sbc hl, de
        ex  de, hl
        pop hl
        ld  a, d
        or  a
        jr  nz, fe_fpw_long
        ld  a, e
        or  a
        ret z
        cp  FE_BOX_W + 1
        jr  nc, fe_fpw_long
        ld  b, FE_BOX_COL
        jp  fe_textn            ; the rest fits
fe_fpw_long:
        ; the last space at or before column 36
        ld  b, FE_BOX_W
fe_fpw_2:  push hl
        ld  e, b
        ld  d, 0
        add hl, de
        ld  a, (hl)
        pop hl
        cp  ' '
        jr  z, fe_fpw_3
        djnz fe_fpw_2
        ld  b, FE_BOX_W
fe_fpw_3:  ld  a, b
        push hl
        push bc
        ld  b, FE_BOX_COL
        call fe_textn
        pop bc
        pop hl
        ld  e, b
        ld  d, 0
        add hl, de
        ld  a, c
        add a, 8
        ld  c, a
        cp  FE_BOX_Y + 40
        jr  c, fe_fpw_line
        ret

; A frame of the mentat's face: the mouth while he talks, the eyes now and
; then.  The mouth is mentat_animate_face's ($01F714-$01F7FE), by the
; clock: a shape 0-4 at random (math_rand_between's masking, so 5-7 fall
; to 1-3), held 7-30 frames if closed, 6-10 if 1-3, 5-6 if 4; closed as
; soon as he stops.
fe_face_tick:
        ld  a, (fe_talking)
        or  a
        jr  z, fe_fft_quiet
        ld  hl, (fe_mouth_t)
        call fe_past
        jr  nc, fe_fft_eyes
        call fe_mrand
        and 7
        cp  5
        jr  c, fe_fft_1
        sub 4
fe_fft_1:  push af
        call fe_set_mouth
        pop af
        ld  bc, 7 * 256 + 30
        or  a
        jr  z, fe_fft_2
        ld  bc, 5 * 256 + 6
        cp  4
        jr  z, fe_fft_2
        ld  bc, 6 * 256 + 10
fe_fft_2:  call fe_rand_between
        ld  e, a
        ld  d, 0
        ld  hl, (frame_count)
        add hl, de
        ld  (fe_mouth_t), hl
        jr  fe_fft_eyes
fe_fft_quiet:
        xor a
        call fe_set_mouth
fe_fft_eyes:
        ld  hl, fe_eye_t
        dec (hl)
        ret nz
        ld  a, (fe_eyes)
        or  a
        jr  z, fe_fft_blink
        xor a                   ; back to open, for a while
        call fe_set_eyes
        call fe_rand
        and 127
        add a, 30
        ld  (fe_eye_t), a
        ret
fe_fft_blink:
        call fe_rand
        and 3
        inc a
        call fe_set_eyes
        call fe_rand
        and 7
        add a, 4
        ld  (fe_eye_t), a
        ret

; A = the frame (0-4).
fe_set_mouth:
        ld  hl, fe_mouth
        cp  (hl)
        ret z
        ld  (hl), a
        ld  b, a
        ld  a, (fe_hs + 2)
        add a, b
        jp  fe_pic
fe_set_eyes:
        ld  hl, fe_eyes
        cp  (hl)
        ret z
        ld  (hl), a
        ld  b, a
        ld  a, (fe_hs + 1)
        add a, b
        jp  fe_pic

; A = the FA_ of the upper button (the lower is the next): YES/NO or
; PROCEED/ADVICE under the text.  -> A = 0 the upper, 1 the lower.
fe_choose2:
        ld  (fe_btn), a
        ld  bc, FE_BUTTON_COL * 256 + FE_BUTTON_Y0
        call fe_pic_at
        ld  a, (fe_btn)
        inc a
        ld  bc, FE_BUTTON_COL * 256 + FE_BUTTON_Y1
        call fe_pic_at
        xor a
        ld  (fe_sel), a
        call pad_take
fe_fc2_loop:
        ld  a, (frame_count)
        and 16
        jr  z, fe_fc2_1
        ld  a, (fe_sel)
        or  a
        ld  c, FE_BUTTON_Y0
        jr  z, fe_fc2_2
        ld  c, FE_BUTTON_Y1
fe_fc2_2:  ld  b, FE_BUTTON_COL
        ld  a, (fe_hs + 4)
        call fe_q_spr
fe_fc2_1:  call fe_face_tick
        call fe_frame
        call pad_take
        or  a
        jr  z, fe_fc2_loop
        ld  b, a
        and $F0
        jr  nz, fe_fc2_choose
        ld  a, b
        and $0F
        jr  z, fe_fc2_loop
        ld  a, (fe_sel)
        xor 1
        ld  (fe_sel), a
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        jr  fe_fc2_loop
fe_fc2_choose:
        ld  a, SFX_POSITIVE_SELECT
        FCALL snd_sfx
        ; the buttons go
        xor a
        ld  bc, FE_BUTTON_COL * 256 + FE_BUTTON_Y0
        ld  de, 10 * 256 + FE_BUTTON_Y1 + 16 - FE_BUTTON_Y0
        call fe_fill
        call fe_frame
        ld  a, (fe_sel)
        ret

; ===================================================== the campaign map

fe_campaign:
        ld  a, FA_PAL_CAMPAIGN
        call fe_prepare
        ld  a, FA_OWN_BRIGHT_0
        call fe_map_owned
        call fe_begin
        ; the territory attacked next
        ld  a, (fe_house)
        ld  b, a
        add a, a
        add a, a
        add a, a
        add a, b                ; x 9
        ld  b, a
        ld  a, (fe_mission)
        dec a
        cp  9
        jr  c, fe_fca_1
        ld  a, 8
fe_fca_1:  add a, b
        ld  hl, fe_attack
        add a, l
        ld  l, a
        jr  nc, fe_fca_2
        inc h
fe_fca_2:  ld  a, (hl)
        ld  (fe_target), a
        ; campaign_break_map $0249F0: 101 frames, then the territories
        ; but the target are lifted off one after another, 9 down to 0 (a
        ; pause before 7), each falling as it goes: its speed grows by a
        ; quarter pixel a frame (campaign_lift_territory's $4000,
        ; campaign_drop_territories $0246E0).  Four fall at most at once.
        ld  b, 101
        call fe_frames
        and $F0
        jp  nz, fe_fca_done
        xor a
        ld  (fe_gonebits), a
        ld  (fe_gonebits + 1), a
        ld  hl, fe_slots
        ld  b, FE_SLOTS * 2
fe_fca_s0: ld  (hl), $FF            ; no slot in use
        inc hl
        djnz fe_fca_s0
        call fe_map_redraw
        ld  a, 9
        ld  (fe_j), a
        ld  a, (frame_count)
        ld  (fe_lift), a        ; the next lift is due now
fe_fca_frame:
        ; a lift when it is due and a slot is free
        ld  a, (fe_j)
        cp  $FF
        jr  z, fe_fca_move      ; all lifted
        ld  hl, fe_target
        cp  (hl)
        jr  z, fe_fca_skip
        ld  a, (fe_lift)
        ld  b, a
        ld  a, (frame_count)
        sub b
        cp  $80
        jr  nc, fe_fca_move     ; not yet
        ld  hl, fe_slots
        ld  b, FE_SLOTS
fe_fca_f1: ld  a, (hl)
        cp  $FF
        jr  z, fe_fca_f2
        inc hl
        inc hl
        djnz fe_fca_f1
        jr  fe_fca_move         ; none free
fe_fca_f2: ld  a, (fe_j)
        ld  (hl), a
        inc hl
        ld  a, (frame_count)
        ld  (hl), a             ; when it was let go
        call fe_gone_set
        call fe_map_redraw
        ; the next one in 16 frames (measured), 21 more before 7
        ld  a, (fe_j)
        cp  8
        ld  a, 16
        jr  nz, fe_fca_f3
        ld  a, 16 + 21
fe_fca_f3: ld  hl, fe_lift
        add a, (hl)
        ld  (hl), a
fe_fca_skip:
        ld  hl, fe_j
        dec (hl)
fe_fca_move:
        ; every falling territory where its fall has taken it by now:
        ; t frames after the lift, t (t + 1) / 8 lines down
        ld  hl, fe_slots
        ld  b, FE_SLOTS
        ld  c, 0                ; how many are still falling
fe_fca_m1: push bc
        push hl
        ld  a, (hl)
        cp  $FF
        jr  z, fe_fca_m9
        inc hl
        ld  b, (hl)
        ld  a, (frame_count)
        sub b                   ; t
        ld  e, a
        inc e
        call fe_mul8            ; HL = t (t + 1)
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ; below the screen: the slot is free again
        ld  a, h
        or  a
        jr  nz, fe_fca_m8
        ld  a, l
        cp  200
        jr  nc, fe_fca_m8
        ld  (fe_dy), a
        pop hl
        push hl
        ld  a, (hl)
        call fe_owner_of
        add a, FA_OWN_BRIGHT_0
        ld  c, a                ; in its owner's colours
        pop hl
        push hl
        ld  a, (fe_dy)
        ld  b, a
        ld  a, (hl)
        add a, FA_TERR_0
        call fe_q_terr
        pop hl
        pop bc
        inc c
        jr  fe_fca_m10
fe_fca_m8: pop hl
        ld  (hl), $FF
        push hl
fe_fca_m9: pop hl
        pop bc
fe_fca_m10:
        inc hl
        inc hl
        djnz fe_fca_m1
        ld  a, c
        ld  (fe_i), a
        call fe_frame
        call pad_take
        and $F0
        jp  nz, fe_fca_done
        ld  a, (fe_j)
        cp  $FF
        jp  nz, fe_fca_frame
        ld  a, (fe_i)
        or  a
        jp  nz, fe_fca_frame
        ; the one left stays a moment ($026182: 51 frames, then it is
        ; lifted and the planes cleared), then the zoom
        ld  b, 46
        call fe_frames
        and $F0
        jr  nz, fe_fca_done
        ld  a, (fe_target)
        call fe_owner_of
        add a, FA_OWN_BRIGHT_0
        call fe_own
        call fe_zoom
        ret nc                  ; played out, the screen black
fe_fca_done:
        ld  a, FA_FADE_CAMPAIGN
        ld  c, 3
        jp  fe_fade_out

; ------------------------------------------------------------- the zoom
;
; campaign_zoom $0256AA: the territory attacked next, alone on the map,
; is drawn bigger and bigger from its top-left corner (its first land
; piece), the corner moving by (-dx, +dy) a step, a new step every five
; frames; campaign_zoom_vblank $024812 darkens the palette from 40 frames
; after the start, a step every five.  Render n is shown with the scroll
; of step n + 1; renders 0-15 are shown (zoom.txt, FA_ZOOM).
;
; A step is sampled the way campaign_zoom_render $024AEE does it: the
; screen x of the picture's left edge, X = 0, 1, ... read the source at
; the whole part of an accumulator that gains the scale each pixel -
; except after the fifth pixel of each eight, where it gains only the
; whole part (the add.w at $024B3A); rows gain the scale every line.
;
; Window 1 is the cache A page throughout: the territory's pens at $4000
; (fe_terr_unpack) and the work tables at the top.

FZ_ROW          EQU $7900       ; a screen row as pen pairs (planes 0-3)
FZ_XT           EQU $7A00       ; per screen x: the source x, or FZ_BLANK
FZ_EXPL         EQU $7C00       ; the source row: pen << 4 by x
FZ_EXPR         EQU $7D00       ; ... and pen
FZ_BLANK        EQU $FF         ; an x outside the source: pen 0
FZ_REC          EQU 6 + 16 * 3  ; FA_ZOOM: a territory's record

; -> carry if a button cut it short.
fe_zoom:
        ld  a, (fe_target)
        add a, FA_TERR_0
        call fe_terr_unpack
        ld  a, FA_ZOOM
        call fe_map_asset
        ld  a, (fe_target)
        ld  e, a
        ld  d, 0
        ld  b, FZ_REC
fz_rec:    add hl, de
        djnz fz_rec
        ld  de, fe_zr
        ld  bc, FZ_REC
        ldir
        ld  a, PG_FE_CACHE_A
        call map_w1
        xor a
        ld  (FZ_EXPL + FZ_BLANK), a
        ld  (FZ_EXPR + FZ_BLANK), a
        ld  (fe_zd), a
        ld  (fe_zow), a         ; nothing drawn yet
        ld  a, 4
        ld  (fe_zfade), a       ; the fade's step: 4 is full light
        ld  a, (frame_count)
        ld  (fe_zt0), a
fz_step:
        ; the last picture off, the next one on
        ld  a, (fe_zow)
        or  a
        jr  z, fz_st1
        ld  d, a
        ld  bc, (fe_zoc)
        ld  a, (fe_zoh)
        ld  e, a
        xor a
        call fe_fill
fz_st1:    call fz_render
        ; shown on frame 5 (n + 1) after the start
        ld  a, (fe_zd)
        inc a
        ld  b, a
        add a, a
        add a, a
        add a, b
        dec a
        ld  (fe_zwhen), a
fz_wait:
        call fz_fade
        ld  a, (fe_zt0)
        ld  b, a
        ld  a, (frame_count)
        sub b
        ld  hl, fe_zwhen
        cp  (hl)
        jr  nc, fz_show
        call vid_wait_frame
        jr  fz_wait
fz_show:
        call fe_frame
        call pad_take
        and $F0
        scf
        ret nz
        ld  hl, fe_zd
        inc (hl)
        ld  a, (hl)
        cp  16
        jr  nz, fz_step
        ; the fade runs out
fz_dark:   call fz_fade
        ld  a, (fe_zfade)
        or  a
        ret z                   ; (no carry)
        call vid_wait_frame
        jr  fz_dark

; The palette for the time since the start: full light for 44 frames,
; then the campaign fade's steps 3, 2, 1 of 4 and black at 53, 61, 70 -
; as bright as the Mega Drive's seven steps of one level each are then.
fz_fade:
        ld  a, (fe_zt0)
        ld  b, a
        ld  a, (frame_count)
        sub b
        ld  c, 4
        cp  44
        jr  c, fz_fd1
        dec c
        cp  53
        jr  c, fz_fd1
        dec c
        cp  61
        jr  c, fz_fd1
        dec c
        cp  70
        jr  c, fz_fd1
        dec c
fz_fd1:    ld  a, (fe_zfade)
        cp  c
        ret z
        ld  a, c
        ld  (fe_zfade), a
        or  a
        jp  z, fe_pal_black
        ; step c of the fade table (1-4): 1 + (c - 1) * 16 into it
        dec a
        add a, a
        add a, a
        add a, a
        add a, a
        inc a
        push af
        ld  a, FA_FADE_CAMPAIGN
        call fe_map_asset
        pop af
        ld  e, a
        ld  d, 0
        add hl, de
        call vid_palette
        ld  a, PG_FE_CACHE_A
        jp  map_w1

; Render fe_zd into the background, at the place of step fe_zd + 1.
fz_render:
        ld  a, PG_FE_CACHE_A    ; (fe_frame moved window 1)
        call map_w1
        ; its scale, width and height
        ld  a, (fe_zd)
        ld  b, a
        add a, a
        add a, b
        ld  e, a
        ld  d, 0
        ld  hl, fe_zr + 6
        add hl, de
        ld  a, (hl)
        ld  (fe_zf), a          ; the scale's fraction; 0 is 1.0
        inc hl
        ld  a, (hl)
        add a, a
        add a, a
        add a, a
        ld  (fe_zw), a          ; the width in pixels (up to 264)
        ld  a, 0
        rla
        ld  (fe_zw + 1), a
        inc hl
        ld  a, (hl)
        add a, a
        add a, a
        add a, a
        ld  (fe_zh), a          ; the height in lines (up to 112)
        ; the corner: x = ax - (n + 1) dx, y = ay + (n + 1) dy
        ld  a, (fe_zd)
        inc a
        ld  b, a
        ld  hl, 0
        ld  de, 0
        ld  a, (fe_zr + 4)      ; dx
        ld  c, a
        rla
        sbc a, a
        ld  d, a
        ld  e, c                ; DE = dx, sign-extended
        push bc
fz_r1:     add hl, de
        djnz fz_r1
        pop bc
        ex  de, hl              ; DE = (n + 1) dx
        ld  a, (fe_zr + 2)
        ld  l, a
        ld  h, 0
        or  a
        sbc hl, de
        ld  (fe_zax), hl
        ld  hl, 0
        ld  a, (fe_zr + 5)      ; dy
        ld  c, a
        rla
        sbc a, a
        ld  d, a
        ld  e, c
fz_r2:     add hl, de
        djnz fz_r2
        ld  a, (fe_zr + 3)
        ld  e, a
        ld  d, 0
        add hl, de
        ld  (fe_zay), hl
        ; the columns: from the corner's, to the one after the right edge
        ld  hl, (fe_zax)
        call fz_col             ; A = column of HL, clamped to 0-40
        ld  (fe_zc0), a
        ld  hl, (fe_zax)
        ld  de, (fe_zw)
        add hl, de
        ld  de, 7
        add hl, de
        call fz_col
        ld  hl, fe_zc0
        sub (hl)
        ret z
        ret c
        ld  (fe_zcn), a
        call fz_xtable
        ; the rows
        xor a
        ld  (fe_zyf), a
        ld  hl, 0
        ld  (fe_zyi), hl
        ld  a, $FF
        ld  (fe_zlast), a
        ld  (fe_zytop), a       ; the first line drawn: none yet
        xor a
        ld  (fe_zyn), a         ; lines drawn
        ld  a, (fe_zh)
        ld  b, a
fz_row:    push bc
        ; y = ay + Y (Y counted by the rows done)
        ld  a, (fe_zh)
        sub b
        ld  e, a
        ld  d, 0
        ld  hl, (fe_zay)
        add hl, de
        ld  a, h
        or  a
        jr  nz, fz_rnext        ; above the screen or below 255
        ld  a, l
        cp  200
        jr  nc, fz_rdone
        ld  (fe_zy), a
        ; the source row: the accumulator's whole part less the origin
        ld  hl, (fe_zyi)
        ld  a, (fe_zr + 1)
        ld  e, a
        ld  d, 0
        or  a
        sbc hl, de
        jr  c, fz_rnext
        ld  a, h
        or  a
        jr  nz, fz_rnext
        ld  a, (fe_th)
        ld  c, a
        ld  a, l
        cp  c
        jr  nc, fz_rnext
        ld  hl, fe_zlast
        cp  (hl)
        jr  z, fz_r3
        ld  (hl), a
        call fz_expand
        call fz_pairs
fz_r3:     ld  a, (fe_zytop)
        cp  $FF
        jr  nz, fz_r4
        ld  a, (fe_zy)
        ld  (fe_zytop), a
fz_r4:     ld  a, (fe_zy)
        ld  hl, fe_zytop
        sub (hl)
        inc a
        ld  (fe_zyn), a
        ld  a, (fe_zy)
        ld  c, a
        call fz_put
fz_rnext:
        call fz_fade            ; the big steps take longer than 5 frames
        ; the next line of the source
        ld  a, (fe_zf)
        or  a
        jr  nz, fz_rn1
        ld  hl, (fe_zyi)        ; 1.0
        inc hl
        ld  (fe_zyi), hl
        jr  fz_rn2
fz_rn1:    ld  hl, fe_zyf
        add a, (hl)
        ld  (hl), a
        jr  nc, fz_rn2
        ld  hl, (fe_zyi)
        inc hl
        ld  (fe_zyi), hl
fz_rn2:    pop bc
        dec b
        jp  nz, fz_row
        push bc
fz_rdone:  pop bc
        ; what it covers: the columns and the lines drawn
        ld  a, (fe_zytop)
        cp  $FF
        jr  z, fz_rnone
        ld  c, a
        ld  a, (fe_zc0)
        ld  b, a
        ld  a, (fe_zcn)
        ld  d, a
        ld  a, (fe_zyn)
        ld  e, a
        ld  (fe_zoc), bc
        ld  a, d
        ld  (fe_zow), a
        ld  a, e
        ld  (fe_zoh), a
        jp  fe_mark_both
fz_rnone:
        xor a
        ld  (fe_zow), a
        ret

; HL = a signed x -> A = its column, 0-40.
fz_col:
        bit 7, h
        jr  nz, fz_c0
        srl h
        rr  l
        srl h
        rr  l
        srl h
        rr  l
        ld  a, h
        or  a
        jr  nz, fz_c40
        ld  a, l
        cp  40
        ret c
fz_c40:    ld  a, 40
        ret
fz_c0:     xor a
        ret

; FZ_XT for the columns fe_zc0 on: per screen x the source x.
fz_xtable:
        ld  a, (fe_zc0)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl              ; the first screen x
        ld  de, (fe_zax)
        or  a
        sbc hl, de              ; X of it: negative before the picture
        ld  (fe_zX), hl
        xor a
        ld  (fe_zxf), a
        ld  h, a
        ld  l, a
        ld  (fe_zxi), hl
        ld  a, (fe_zcn)
        add a, a
        add a, a
        add a, a
        ld  c, a
        ld  a, 0
        rla
        ld  b, a                ; BC = entries
        ld  ix, FZ_XT
fz_x1:     push bc
        ld  a, FZ_BLANK
        ld  hl, (fe_zX)
        bit 7, h
        jr  nz, fz_x9           ; left of the picture
        ld  de, (fe_zw)
        or  a
        sbc hl, de
        jr  nc, fz_x9           ; right of it
        ; the source x: the accumulator less the origin
        ld  hl, (fe_zxi)
        ld  a, (fe_zr + 0)
        ld  e, a
        ld  d, 0
        or  a
        sbc hl, de
        ld  a, FZ_BLANK
        jr  c, fz_x5
        ld  a, h
        or  a
        ld  a, FZ_BLANK
        jr  nz, fz_x5
        ld  a, (fe_tw)
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  a, l
        cp  e
        jr  c, fz_x5
        ld  a, FZ_BLANK
fz_x5:     ld  (ix + 0), a
        ; step on: after the fifth of each eight pixels only the whole
        ; part of the scale ($024B3A)
        ld  a, (fe_zX)
        and 7
        cp  4
        ld  a, (fe_zf)
        jr  z, fz_x7
        or  a
        jr  z, fz_x8            ; 1.0
        ld  hl, fe_zxf
        add a, (hl)
        ld  (hl), a
        jr  nc, fz_x10
        jr  fz_x8
fz_x7:     or  a
        jr  nz, fz_x10          ; below 1.0 the whole part is 0
fz_x8:     ld  hl, (fe_zxi)
        inc hl
        ld  (fe_zxi), hl
        jr  fz_x10
fz_x9:     ld  (ix + 0), a
fz_x10:    inc ix
        ld  hl, (fe_zX)
        inc hl
        ld  (fe_zX), hl
        pop bc
        dec bc
        ld  a, b
        or  c
        jr  nz, fz_x1
        ret

; Source row A (of the pens at $4000, fe_tw columns) -> FZ_EXPL/EXPR.
fz_expand:
        ld  l, a
        ld  h, 0
        ld  a, (fe_tw)
        add a, a
        add a, a
        ld  e, a
        push hl
        pop bc
        ld  a, c
        call fe_mul8
        ld  de, $4000
        add hl, de              ; the row
        ld  de, FZ_EXPL
        ld  a, (fe_tw)
        add a, a
        add a, a
        ld  b, a                ; its bytes: a pixel pair each
fz_e1:     ld  a, (hl)
        inc hl
        ld  c, a
        and $F0
        ld  (de), a             ; the left pixel, as pen << 4
        inc d
        rrca
        rrca
        rrca
        rrca
        ld  (de), a             ; ... and as the pen
        dec d
        inc e
        ld  a, c
        and $0F
        inc d
        ld  (de), a             ; the right pixel, as the pen
        dec d
        add a, a
        add a, a
        add a, a
        add a, a
        ld  (de), a             ; ... and as pen << 4
        inc e
        djnz fz_e1
        ret

; FZ_XT and the expanded row -> FZ_ROW: a pen pair per screen pixel pair.
fz_pairs:
        ld  a, (fe_zcn)
        add a, a
        add a, a
        ld  (fe_zcnt), a        ; pairs: four a column
        ld  bc, FZ_XT
        ld  de, FZ_ROW
        ld  h, HIGH FZ_EXPL
fz_p1:     ld  a, (bc)
        inc bc
        ld  l, a
        ld  a, (hl)             ; the left pen << 4
        ld  (de), a
        ld  a, (bc)
        inc bc
        ld  l, a
        inc h
        ld  a, (hl)             ; the right pen
        dec h
        ex  de, hl
        or  (hl)
        ld  (hl), a
        inc hl
        ex  de, hl
        ld  a, (fe_zcnt)
        dec a
        ld  (fe_zcnt), a
        jr  nz, fz_p1
        ret

; FZ_ROW into the background's line C, columns fe_zc0 on, in the colours
; of fe_owntab (the dither by the line's parity).
fz_put:
        ld  a, (fe_zc0)
        ld  b, a
        call fe_rowaddr
        ld  (fe_zoff), hl
        ld  a, c
        and 1
        add a, HIGH fe_owntab + 1
        ld  (fe_zpar), a
        ld  a, PG_FE_BG_A
        call map_w3
        ld  ix, FZ_ROW
        call fz_half
        ld  a, PG_FE_BG_B
        call map_w3
        ld  ix, FZ_ROW + 1
fz_half:
        ld  de, (fe_zoff)
        ld  a, d
        or  $C0
        ld  d, a
        ld  a, (fe_zpar)
        ld  h, a
        ld  a, (fe_zcn)
        ld  b, a
fz_h1:     ld  l, (ix + 0)
        ld  a, (hl)
        ld  (de), a             ; plane 0 (or 1)
        ld  l, (ix + 2)
        ld  a, (hl)
        set 5, d
        ld  (de), a             ; plane 2 (or 3)
        res 5, d
        inc de
        inc ix
        inc ix
        inc ix
        inc ix
        djnz fz_h1
        ret

fe_gone_set:
        ld  a, (fe_j)
        ld  hl, fe_gonebits
        cp  8
        jr  c, fe_fgs_1
        inc hl
        sub 8
fe_fgs_1:  ld  b, a
        inc b
        ld  a, 0
        scf
fe_fgs_2:  rla
        djnz fe_fgs_2
        or  (hl)
        ld  (hl), a
        ret

; The map area cleared and the territories not gone drawn again, as
; campaign_redraw_map $02494E does: their borders in the first line, then
; their land in their owners' colours over them.
fe_map_redraw:
        xor a
        ld  bc, 0 * 256 + FE_MAP_Y
        ld  de, 40 * 256 + FE_MAP_H
        call fe_fill
        ld  a, FE_OWN_BORDERS
        ld  (fe_ownmode), a
        ld  a, FA_OWN_BRIGHT_0
        call fe_own
        ld  a, FE_OWN_BORDERS
        call fe_fmr_pass
        ld  a, FE_OWN_LAND
        ld  (fe_ownmode), a
        call fe_fmr_pass
        xor a
        ld  (fe_ownmode), a
        ret
; A = the pass (FE_OWN_BORDERS: fe_owntab already loaded, or
; FE_OWN_LAND: each in its owner's colours).
fe_fmr_pass:
        ld  (fe_fmrp), a
        xor a
        ld  (fe_i), a
fe_fmr_1:  ld  a, (fe_i)
        ld  hl, fe_gonebits
        cp  8
        jr  c, fe_fmr_2
        inc hl
        sub 8
fe_fmr_2:  ld  b, a
        ld  a, (hl)
        inc b
fe_fmr_3:  rrca
        djnz fe_fmr_3
        jr  c, fe_fmr_skip
        ld  a, (fe_fmrp)
        cp  FE_OWN_LAND
        jr  nz, fe_fmr_4
        ld  a, (fe_i)
        call fe_owner_of
        add a, FA_OWN_BRIGHT_0
        call fe_own
fe_fmr_4:  ld  a, (fe_i)
        add a, FA_TERR_0
        ld  b, 0
        call fe_terr
fe_fmr_skip:
        ld  a, (fe_i)
        inc a
        ld  (fe_i), a
        cp  10
        jr  nz, fe_fmr_1
        ret

; =================================================== victory and defeat

; The picture of fe_won, its four frames every eleven, the word sliding
; up to it, until a button.
fe_vd_screen:
        ld  a, (fe_won)
        or  a
        ld  hl, fe_fvd_defeat
        jr  z, fe_fvd_1
        ld  hl, fe_fvd_victory
fe_fvd_1:  ld  de, fe_vd
        ld  bc, 4
        ldir
        ld  a, (fe_vd + 0)
        call fe_prepare
        ld  a, (fe_vd + 1)
        call fe_pic
        call fe_begin
        xor a
        ld  (fe_i), a           ; the frame
        ld  (fe_j), a           ; frames since the start
        ld  (fe_dy), a          ; frames since the last step
        call pad_take
fe_fvd_loop:
        ld  a, (fe_j)
        inc a
        jr  z, fe_fvd_2
        ld  (fe_j), a
fe_fvd_2:  ; the banner: from 7 lines lower up to its place
        ld  a, (fe_j)
        srl a
        srl a
        cp  7
        jr  c, fe_fvd_3
        ld  a, 7
fe_fvd_3:  ld  b, a
        ld  a, 183
        sub b
        ld  c, a
        ld  a, (fe_vd + 3)
        ld  b, $FF
        push bc
        call fe_map_asset       ; its column
        pop bc
        ld  b, (hl)
        ld  a, (fe_vd + 3)
        call fe_q_spr
        ; the next frame of the picture every eleven
        ld  hl, fe_dy
        inc (hl)
        ld  a, (hl)
        cp  11
        jr  c, fe_fvd_4
        ld  (hl), 0
        ld  a, (fe_i)
        inc a
        and 3
        ld  (fe_i), a
        ld  b, a
        ld  a, (fe_vd + 2)
        add a, b
        call fe_pic
fe_fvd_4:  call fe_frame
        call pad_take
        and $F0
        jr  z, fe_fvd_loop
        ld  a, (fe_j)
        cp  20
        jr  c, fe_fvd_loop         ; not before the banner is on its way
        jp  fe_fade_out_cur
fe_fvd_victory:
        DB  FA_PAL_VICTORY, FA_VICTORY, FA_VICTORY_F0, FA_VICTORY_BANNER
fe_fvd_defeat:
        DB  FA_PAL_DEFEAT, FA_DEFEAT, FA_DEFEAT_F0, FA_DEFEAT_BANNER

; ======================================================== the score page

fe_score:
        ld  a, FA_PAL_SCORE
        call fe_prepare
        ld  a, FA_SCORE
        call fe_pic
        call fe_begin
        ld  a, FA_FONT_SCORE
        ld  d, PN_SCORE_YELLOW
        ld  e, PN_SCORE_YELLOW
        ld  c, PN_SCORE_BLACK
        call fe_ink
        ; the score, from x 104, no leading zeros
        ld  hl, (score)
        call fe_num5
        ld  e, a
        ld  a, 5
        sub e
        ld  hl, fe_numbuf
        add a, l
        ld  l, a
        jr  nc, fe_fsc_1
        inc h
fe_fsc_1:  ld  a, e
        ld  bc, 13 * 256 + 24
        call fe_textn
        ; the time: hours at x 248, minutes (two digits) at 264
        ld  hl, (score_hours)
        call fe_num5
        ld  hl, fe_numbuf + 4
        ld  a, 1
        ld  bc, 31 * 256 + 24
        call fe_textn
        ld  hl, (score_minutes)
        call fe_num5
        ld  a, (fe_numbuf + 3)
        cp  ' '
        jr  nz, fe_fsc_2
        ld  a, '0'
        ld  (fe_numbuf + 3), a
fe_fsc_2:  ld  hl, fe_numbuf + 3
        ld  a, 2
        ld  bc, 33 * 256 + 24
        call fe_textn
        ; the rank, 17 characters from x 96
        ld  a, FA_FONT_SCORE
        ld  d, PN_SCORE_YELLOW
        ld  e, PN_SCORE_YELLOW
        ld  c, PN_SCORE_BLACK
        call fe_ink
        ld  a, (score_rank)
        FE_TXT txt_ranks
        ld  bc, 12 * 256 + 56
        call fe_text
        ; the bars: spice harvested, units, structures destroyed
        ld  hl, (harvested_allied)
        ld  de, (harvested_enemy)
        ld  c, 104
        call fe_bar_pair
        ld  hl, (killed_enemy)
        ld  de, (killed_allied)
        ld  c, 144
        call fe_bar_pair
        ld  hl, (destroyed_enemy)
        ld  de, (destroyed_allied)
        ld  c, 184
        call fe_bar_pair
        call pad_take
fe_fsc_w:  call fe_frame
        call pad_take
        and $F0
        jr  z, fe_fsc_w
        ret

; HL = yours, DE = the enemy's, C = the first bar's y: both bars, counted
; up a pixel a frame (score_count_bar $026F94).
fe_bar_pair:
        ld  (fe_bv0), hl
        ld  (fe_bv1), de
        ld  a, c
        ld  (fe_by), a
        ; a pixel's worth: the longer at most 168 pixels (score_bar_scale)
        ld  bc, 65000
        call fe_fbp_clamp
        ld  (fe_bv0), hl
        ex  de, hl
        call fe_fbp_clamp
        ld  (fe_bv1), hl
        ld  de, (fe_bv0)
        or  a
        sbc hl, de
        add hl, de
        jr  nc, fe_fbpr_1
        ex  de, hl              ; HL = the larger
fe_fbpr_1: ld  de, 169
        or  a
        sbc hl, de
        add hl, de
        ld  de, 1
        jr  c, fe_fbpr_2
        ld  de, 168
        call udiv16             ; HL / DE (the stub) -> HL
        inc hl
        ex  de, hl
fe_fbpr_2: ld  (fe_bscale), de
        ld  hl, (fe_bv0)
        ld  a, PN_SCORE_YOU_HI
        ld  b, PN_SCORE_YOU
        call fe_count_bar
        ld  a, (fe_by)
        add a, 8
        ld  (fe_by), a
        ld  hl, (fe_bv1)
        ld  a, PN_SCORE_ENEMY_HI
        ld  b, PN_SCORE_ENEMY
        jp  fe_count_bar
fe_fbp_clamp:
        push hl
        or  a
        sbc hl, bc
        pop hl
        ret c
        ld  h, b
        ld  l, c
        ret

; HL = the figure, A, B = the bar's pens (top, body), fe_by, fe_bscale.
fe_count_bar:
        ld  (fe_bval), hl
        ld  (fe_bpens), a
        ld  a, b
        ld  (fe_bpens + 1), a
        ld  hl, 0
        ld  (fe_bshown), hl
        xor a
        ld  (fe_bn), a
fe_fcb_loop:
        ; the bar at fe_bn pixels
        ld  a, (fe_bpens)
        ld  d, a
        ld  a, (fe_bpens + 1)
        ld  e, a
        ld  c, PN_SCORE_BLACK
        ld  a, FA_FONT_SCORE
        call fe_ink
        ld  a, (fe_bn)
        ld  b, a
        and 7
        add a, $18
        ld  (fe_ch), a
        ld  a, b
        rrca
        rrca
        rrca
        and $1F
        add a, 10
        ld  b, a
        ld  a, (fe_by)
        ld  c, a
        push bc
        ld  hl, fe_ch
        ld  a, 1
        call fe_textn
        pop bc
        ld  a, (fe_bn)
        and 7
        jr  nz, fe_fcb_1
        ld  a, (fe_bn)
        or  a
        jr  z, fe_fcb_1
        dec b                   ; the cell before is full now
        ld  a, $17
        ld  (fe_ch), a
        ld  hl, fe_ch
        ld  a, 1
        call fe_textn
fe_fcb_1:  ; the figure so far, right-aligned to x 295
        ld  hl, (fe_bshown)
        call fe_show_figure
        ld  a, (fe_bn)
        and 3
        jr  nz, fe_fcb_2
        ld  a, $34
        FCALL snd_effect
fe_fcb_2:  call fe_frame
        ld  hl, (fe_bshown)
        ld  de, (fe_bscale)
        add hl, de
        ld  (fe_bshown), hl
        ld  de, (fe_bval)
        ex  de, hl
        or  a
        sbc hl, de              ; value - shown
        jr  c, fe_fcb_end
        jr  z, fe_fcb_end
        ld  a, (fe_bn)
        cp  168
        jr  nc, fe_fcb_end
        inc a
        ld  (fe_bn), a
        jp  fe_fcb_loop
fe_fcb_end:
        ld  hl, (fe_bval)
        call fe_show_figure
        ld  b, 11
        jp  fe_frames

; HL = a figure: at x 256-295 on the bar's line, over a clean picture.
fe_show_figure:
        push hl
        ld  a, (fe_by)
        ld  c, a
        ld  b, 32
        ld  de, 5 * 256 + 8
        call fe_pristine
        ld  a, FA_FONT_SCORE
        ld  d, PN_SCORE_YELLOW
        ld  e, PN_SCORE_YELLOW
        ld  c, PN_SCORE_BLACK
        call fe_ink
        pop hl
        call fe_num5
        ld  a, (fe_by)
        ld  c, a
        ld  b, 32
        ld  hl, fe_numbuf
        ld  a, 5
        jp  fe_textn

; The password for the next mission: the words, the house, the mission,
; the word itself; until a button.
fe_password_page:
        call fe_fade_out_cur
        ld  a, FA_PAL_SCORE
        call fe_prepare
        ld  a, FA_SCORE_PW
        call fe_pic
        ld  a, FA_FONT_SCORE
        ld  d, PN_SCORE_WHITE
        ld  e, PN_SCORE_WHITE
        ld  c, PN_SCORE_BLACK
        call fe_ink
        ld  hl, fe_fpp_house
        ld  bc, 13 * 256 + 64
        call fe_text
        ld  a, (fe_house)
        FE_TXT txt_score_houses
        ld  bc, 19 * 256 + 64
        call fe_text
        ld  a, (fe_mission)
        add a, '0'
        ld  (fe_ch), a
        ld  hl, fe_ch
        ld  a, 1
        ld  bc, 22 * 256 + 80
        call fe_textn
        ld  a, FA_FONT_SCORE
        ld  d, PN_SCORE_YELLOW
        ld  e, PN_SCORE_YELLOW
        ld  c, PN_SCORE_BLACK
        call fe_ink
        ; entry (mission - 1) * 3 + house of the 29
        ld  a, (fe_mission)
        dec a
        ld  b, a
        add a, a
        add a, b
        ld  b, a
        ld  a, (fe_house)
        add a, b
        FE_TXT txt_passwords
        ld  bc, 15 * 256 + 96
        call fe_text
        call fe_begin
        call pad_take
fe_fpp_w:  call fe_frame
        call pad_take
        and $F0
        jr  z, fe_fpp_w
        ret
fe_fpp_house:
        DB  "HOUSE", $FF

; ============================================================ options

FE_OPT_ROWS     EQU 8

; The options screen (fe_battle: the two battle rows too).  -> A = 0 left
; with Start, 1 restart, 2 another house, 3 a password (B = mission, C =
; house), 4 DUNEFINALE.
fe_options:
        xor a
        ld  (fe_sel), a
        ld  (fe_mtest), a
        ld  (fe_stest), a
fe_fop_redraw:
        ld  a, FA_PAL_OPTIONS
        call fe_prepare
        ld  a, FA_OPTIONS
        call fe_pic
        ld  a, (fe_battle)
        or  a
        jr  z, fe_fop_1
        ld  a, FA_FONT_MENU
        ld  d, PN_OPT_WHITE
        ld  e, d
        ld  c, 0
        call fe_ink
        FE_STR txt_ui_opt_restart
        ld  bc, 4 * 256 + 152
        call fe_text
        FE_STR txt_ui_opt_pick_house
        ld  bc, 4 * 256 + 168
        call fe_text
fe_fop_1:  ld  b, 0
fe_fop_vals:
        push bc
        ld  a, b
        call fe_opt_value
        pop bc
        inc b
        ld  a, b
        cp  5
        jr  nz, fe_fop_vals
        call fe_begin
        ld  a, (fe_sel)
        call fe_opt_y
        sub FE_OPT_PTR_DY
        ld  (fe_ptr_y), a
        call pad_take
fe_fop_loop:
        ; the pointer slides to its row, 4 pixels a frame, and keys wait
        ; for it (opt_pointer_key $021C16 answers -1 while it moves,
        ; opt_pointer_step $021D06 moves it)
        ld  a, (fe_sel)
        call fe_opt_y
        sub FE_OPT_PTR_DY
        ld  hl, fe_ptr_y
        sub (hl)
        jr  z, fe_fop_still
        ld  a, 4
        jr  nc, fe_fop_slide
        ld  a, -4
fe_fop_slide:
        add a, (hl)
        ld  (hl), a
        call fe_fop_ptr
        call pad_take
        jr  fe_fop_loop
fe_fop_still:
        call fe_fop_ptr
        call pad_take
        or  a
        jr  z, fe_fop_loop
        ld  b, a
        bit 7, b
        jr  nz, fe_fop_leave
        ld  a, b
        and PADM_UP
        jr  nz, fe_fop_up
        ld  a, b
        and PADM_DOWN
        jr  nz, fe_fop_down
        ld  a, b
        and PADM_LEFT
        jr  nz, fe_fop_left
        ld  a, b
        and PADM_RIGHT
        jr  nz, fe_fop_right
        ld  a, b
        and PADM_A | PADM_C
        jp  nz, fe_fop_press
        jr  fe_fop_loop
fe_fop_leave:
        call fe_fade_out_cur
        xor a
        ret
; the pointer where fe_ptr_y says, and the frame.  Its colours shimmer:
; the cartridge rotates colours 8-13 of palette line 1 a place every 8
; frames while the screen waits (opt_screen $0214A0, pal_cycle_cram
; $02208A); here that is six sprites, the next every 8 frames.
fe_fop_ptr:
        ld  a, (frame_count)
        rrca
        rrca
        rrca
        and $1F
fe_fop_m6: sub 6
        jr  nc, fe_fop_m6
        add a, 6 + FA_OPTIONS_PTR_0
        ld  b, a
        ld  a, (fe_ptr_y)
        ld  c, a
        ld  a, b
        ld  b, FE_OPT_PTR_COL
        call fe_q_spr
        jp  fe_frame
; up and down wrap between the top row and the last (5, 7 in a battle)
fe_fop_last:
        ld  a, (fe_battle)
        or  a
        ld  a, 5
        ret z
        ld  a, 7
        ret
fe_fop_up: ld  a, (fe_sel)
        or  a
        jr  nz, fe_fop_u1
        call fe_fop_last
        inc a
fe_fop_u1: dec a
        jr  fe_fop_mv
fe_fop_down:
        call fe_fop_last
        ld  hl, fe_sel
        cp  (hl)
        ld  a, (hl)
        jr  nz, fe_fop_d1
        ld  a, -1
fe_fop_d1: inc a
fe_fop_mv: ld  (fe_sel), a
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        jp  fe_fop_loop
fe_fop_left:
        ld  c, -1
        jr  fe_fop_step
fe_fop_right:
        ld  c, 1
fe_fop_step:
        ld  a, (fe_sel)
        cp  3
        jr  c, fe_fop_toggle
        jr  z, fe_fop_mstep
        cp  4
        jp  nz, fe_fop_loop
        ld  a, (fe_stest)
        add a, c
        jp  p, fe_fop_s1
        ld  a, TXT_SOUND_TEST_COUNT - 1
fe_fop_s1: cp  TXT_SOUND_TEST_COUNT
        jr  c, fe_fop_s2
        xor a
fe_fop_s2: ld  (fe_stest), a
        jr  fe_fop_newval
fe_fop_mstep:
        ld  a, (fe_mtest)
        add a, c
        jp  p, fe_fop_m1
        ld  a, TXT_MUSIC_TEST_COUNT - 1
fe_fop_m1: cp  TXT_MUSIC_TEST_COUNT
        jr  c, fe_fop_m2
        xor a
fe_fop_m2: ld  (fe_mtest), a
        jr  fe_fop_newval
fe_fop_toggle:
        or  a
        jr  nz, fe_fop_t1
        ld  a, (music_on)       ; music is on/off
        xor 1
        ld  (music_on), a
        call fe_music_switched
        jr  fe_fop_newval
fe_fop_t1: cp  1
        jr  nz, fe_fop_t2
        ld  a, (sound_on)
        xor 1
        ld  (sound_on), a
        jr  fe_fop_newval
fe_fop_t2: ld  a, (radar_option)
        or  a
        ld  a, 1
        jr  z, fe_fop_t3
        xor a
fe_fop_t3: ld  (radar_option), a
fe_fop_newval:
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        ld  a, (fe_sel)
        call fe_opt_value
        jp  fe_fop_loop
fe_fop_press:
        ld  a, (fe_sel)
        cp  3
        jr  z, fe_fop_playm
        cp  4
        jr  z, fe_fop_plays
        cp  5
        jr  z, fe_fop_pw
        cp  6
        jp  c, fe_fop_loop
        ; restart / another house: are you sure?
        call fe_confirm
        or  a
        jp  z, fe_fop_loop
        call fe_fade_out_cur
        ld  a, (fe_sel)
        sub 5                   ; 1 restart, 2 another house
        ret
fe_fop_playm:
        ld  a, (fe_mtest)
        ld  hl, fe_music_ids
        call fe_index
        cp  $FF
        jp  z, fe_fop_loop
        push af
        FCALL gs_music_fade     ; the one playing out first
        pop af
        FCALL snd_mus
        jp  fe_fop_loop
fe_fop_plays:
        ld  a, (fe_stest)
        ld  hl, fe_sound_ids
        call fe_index
        cp  $FF
        jp  z, fe_fop_loop
        FCALL snd_sfx
        jp  fe_fop_loop
fe_fop_pw: ld  a, SFX_POSITIVE_SELECT
        FCALL snd_sfx
        call fe_fade_out_cur
        call fe_password
        or  a
        jp  z, fe_fop_redraw
        ret

; The mentat's tune - the house's own: $18 Harkonnen, $19 Atreides, $1A
; Ordos (mentat_house_confirm $01F362, mentat_briefing $01F402) - unless
; it is the track asked for last (S9: the house screen started it, the
; briefing does not start it again).  MAIN's snd_mentat.
fe_music_mentat:
        ld  a, (fe_house)
        FCALL snd_mentat
        ret

; HL = a table, A = an index -> A = the byte.
fe_index:
        add a, l
        ld  l, a
        jr  nc, fe_fix_1
        inc h
fe_fix_1:  ld  a, (hl)
        ret

; A = an options row -> A = its y.
fe_opt_y:
        ld  hl, fe_fopy
        jr  fe_index
fe_fopy:   DB  40, 56, 72, 88, 104, 136, 152, 168

; The music was switched on or off.
fe_music_switched:
        or  a
        jr  nz, fe_fms_on
        FCALL gs_music_fade     ; faded out, then
        xor a
        FCALL snd_music         ; stopped and forgotten
        ret
fe_fms_on: ld  a, (fe_battle)
        or  a
        jr  z, fe_fms_title
        ld  hl, $FFFF           ; the battle's shuffle picks a tune
        ld  (music_frames_left), hl
        ret
fe_fms_title:
        ld  a, MUS_TITLE
        FCALL snd_mus
        ret

; A = a row 0-4: its value drawn at x 176 in the menu font, cyan.
fe_opt_value:
        ld  (fe_row), a
        call fe_opt_y
        ld  c, a
        ld  b, 22
        ld  de, 18 * 256 + 8
        call fe_pristine
        ld  a, FA_FONT_MENU
        ld  d, PN_OPT_CYAN
        ld  e, d
        ld  c, 0
        call fe_ink
        ld  a, (fe_row)
        cp  3
        jr  z, fe_fov_music
        cp  4
        jr  z, fe_fov_sound
        ld  hl, music_on
        or  a
        jr  z, fe_fov_1
        ld  hl, sound_on
        dec a
        jr  z, fe_fov_1
        ld  hl, radar_option
fe_fov_1:  ld  a, (hl)
        or  a
        jr  z, fe_fov_off
        FE_STR txt_ui_opt_on
        jr  fe_fov_put
fe_fov_off:
        FE_STR txt_ui_opt_off
        jr  fe_fov_put
fe_fov_music:
        ld  a, (fe_mtest)
        FE_TXT txt_music_test
        jr  fe_fov_put
fe_fov_sound:
        ld  a, (fe_stest)
        FE_TXT txt_sound_test
fe_fov_put:
        ld  a, (fe_row)
        call fe_opt_y
        ld  c, a
        ld  b, 22
        ld  hl, fe_strbuf
        jp  fe_text

; Restart / another house: YES and NO on the row; -> A = 1 yes.
fe_confirm:
        ld  a, (fe_sel)
        call fe_opt_y
        ld  (fe_cy), a
        ld  c, a
        ld  b, 22
        ld  de, 18 * 256 + 8
        call fe_pristine
        ld  a, FA_FONT_MENU
        ld  d, PN_OPT_CYAN
        ld  e, d
        ld  c, 0
        call fe_ink
        FE_STR txt_ui_confirm_yes_no
        ld  a, (fe_cy)
        ld  c, a
        ld  b, 24
        call fe_text
        ld  a, 1
        ld  (fe_yes), a
        call pad_take
fe_fcf_loop:
        ld  a, (fe_yes)
        or  a
        ld  b, 22
        jr  nz, fe_fcf_1
        ld  b, 31
fe_fcf_1:  ld  a, (fe_cy)
        sub FE_OPT_PTR_DY
        ld  c, a
        ld  a, FA_OPTIONS_PTR_0    ; opt_confirm's loop does not cycle
        call fe_q_spr
        call fe_frame
        call pad_take
        or  a
        jr  z, fe_fcf_loop
        ld  b, a
        and PADM_LEFT | PADM_RIGHT
        jr  z, fe_fcf_2
        ld  a, (fe_yes)
        xor 1
        ld  (fe_yes), a
        jr  fe_fcf_loop
fe_fcf_2:  ld  a, b
        and PADM_B | PADM_START
        jr  nz, fe_fcf_no
        ld  a, b
        and PADM_A | PADM_C
        jr  z, fe_fcf_loop
        ld  a, (fe_yes)
        or  a
        jr  z, fe_fcf_no
        ld  a, SFX_POSITIVE_SELECT
        FCALL snd_sfx
        ld  a, 1
        ret
fe_fcf_no: ; the row's words go again
        ld  a, (fe_cy)
        ld  c, a
        ld  b, 22
        ld  de, 18 * 256 + 8
        call fe_pristine
        xor a
        ret

; =========================================================== password

; The keyboard: A or C presses the key under the frame, END checks the
; word.  -> A = 0 nothing (B or Start), 3 a mission (B = mission, C =
; house), 4 DUNEFINALE.
fe_password:
        ld  a, FA_PAL_PASSWORD
        call fe_prepare
        ld  a, FA_PASSWORD
        call fe_pic
        ld  hl, fe_word
        ld  b, 10
fe_fpw_c:  ld  (hl), ' '
        inc hl
        djnz fe_fpw_c
        xor a
        ld  (fe_wpos), a
        ld  (fe_kx), a
        ld  (fe_ky), a
        call fe_pw_word
        call fe_begin
        call pad_take
fe_fpd_loop:
        ; the frame round the key
        ld  a, (fe_kx)
        add a, a
        add a, 10
        ld  b, a
        ld  a, (fe_ky)
        add a, a
        add a, a
        add a, a
        add a, a
        add a, 52
        ld  c, a
        ld  a, FA_PASSWORD_KEY
        call fe_q_spr
        call fe_frame
        call pad_take
        or  a
        jr  z, fe_fpd_loop
        ld  b, a
        and PADM_B | PADM_START
        jr  nz, fe_fpd_leave
        ld  a, b
        and PADM_A | PADM_C
        jr  nz, fe_fpd_key
        ld  a, (fe_kx)
        ld  c, a
        ld  a, (fe_ky)
        bit 0, b
        jr  z, fe_fpd_1
        dec a
        jp  p, fe_fpd_1
        ld  a, 2
fe_fpd_1:  bit 1, b
        jr  z, fe_fpd_2
        inc a
        cp  3
        jr  c, fe_fpd_2
        xor a
fe_fpd_2:  ld  (fe_ky), a
        ld  a, c
        bit 2, b
        jr  z, fe_fpd_3
        dec a
        jp  p, fe_fpd_3
        ld  a, 9
fe_fpd_3:  bit 3, b
        jr  z, fe_fpd_4
        inc a
        cp  10
        jr  c, fe_fpd_4
        xor a
fe_fpd_4:  ld  (fe_kx), a
        ; END is two keys wide
        ld  a, (fe_ky)
        cp  2
        jr  nz, fe_fpd_loop
        ld  a, (fe_kx)
        cp  9
        jr  nz, fe_fpd_loop
        bit 3, b
        ld  a, 8
        jr  z, fe_fpd_5
        xor a                   ; right from END: round to the first
fe_fpd_5:  ld  (fe_kx), a
        jr  fe_fpd_loop
fe_fpd_leave:
        call fe_fade_out_cur
        xor a
        ret
fe_fpd_key:
        ld  a, (fe_ky)
        ld  b, a
        add a, a
        add a, a
        add a, b
        add a, a
        ld  b, a
        ld  a, (fe_kx)
        add a, b                ; the key's number
        cp  28
        jr  nc, fe_fpd_end
        cp  26
        jr  z, fe_fpd_back
        jr  nc, fe_fpd_fwd
        add a, 'A'
        ld  b, a
        ld  hl, fe_word
        ld  a, (fe_wpos)
        add a, l
        ld  l, a
        jr  nc, fe_fpd_6
        inc h
fe_fpd_6:  ld  (hl), b
fe_fpd_fwd:
        ld  a, (fe_wpos)
        cp  9
        jr  nc, fe_fpd_7
        inc a
        jr  fe_fpd_7
fe_fpd_back:
        ld  a, (fe_wpos)
        or  a
        jr  z, fe_fpd_7
        dec a
fe_fpd_7:  ld  (fe_wpos), a
        ld  a, SFX_MENU_SELECT
        FCALL snd_sfx
        call fe_pw_word
        jp  fe_fpd_loop
fe_fpd_end:
        call fe_pw_check
        cp  $FF
        jp  z, fe_fpd_refused
        ld  (fe_row), a
        ; accepted
        call fe_rand
        and 1
        add a, SFX_YES_SIR
        FCALL snd_sfx
        ld  a, (fe_row)
        ld  hl, txt_passwords_kind
        ld  c, $$txt_passwords_kind
        call fe_pw_attr
        ld  (fe_pwkind), a
        ld  a, (fe_row)
        ld  hl, txt_passwords_value
        ld  c, $$txt_passwords_value
        call fe_pw_attr
        ld  b, a
        ld  a, (fe_pwkind)
        cp  3
        jr  c, fe_fpd_mission
        jr  z, fe_fpd_finale
        cp  7
        jr  z, fe_fpd_splurge
        cp  9
        jr  z, fe_fpd_playtest
        cp  10
        jr  z, fe_fpd_version
        ld  hl, dbg_flags       ; LOOKAROUND: the whole map shown, or
        ld  a, (hl)             ; hidden again ($FFC198; the renderer's
        xor 1                   ; reveal, dbg_flags bit 0)
        ld  (hl), a
        jp  fe_fpd_loop
fe_fpd_mission:
        push bc
        push af
        ld  b, 50
        call fe_frames
        call fe_fade_out_cur
        pop af
        pop bc
        ld  c, a                ; the house
        ld  a, 3
        ret
fe_fpd_finale:
        ld  b, 50
        call fe_frames
        call fe_fade_out_cur
        ld  a, 4
        ret
fe_fpd_splurge:
        ; 25000 credits, and as many without silos (S5)
        ld  hl, 25000
        ld  (credits_no_silo), hl
        ld  hl, 0
        ld  (credits_no_silo + 2), hl
        ld  a, (fe_battle)
        or  a
        jp  z, fe_fpd_loop
        call map_game
        ld  a, (player_house)
        call house_ptr
        ld  de, H_CREDITS
        add hl, de
        ld  (hl), 25000 & $FF
        inc hl
        ld  (hl), 25000 >> 8
        inc hl
        ld  (hl), 0
        inc hl
        ld  (hl), 0
        jp  fe_fpd_loop
fe_fpd_playtest:
        ld  a, (playtester)
        xor 1
        ld  (playtester), a
        jp  fe_fpd_loop
fe_fpd_version:
        ld  a, FA_FONT_MENU
        ld  d, PN_PW_WHITE
        ld  e, d
        ld  c, 0
        call fe_ink
        FE_STR txt_ui_version
        ld  bc, 15 * 256 + 136
        call fe_text
        jp  fe_fpd_loop
fe_fpd_refused:
        call fe_rand
        and 1
        ld  a, SFX_INVALID_SELECT
        jr  z, fe_fpd_r1
        ld  a, SFX_SCREAM
fe_fpd_r1: FCALL snd_sfx
        jp  fe_fpd_loop

; HL = a txt_passwords_ attribute table, C = its page, A = the entry ->
; A = the value.
fe_pw_attr:
        push af
        ld  a, c
        call map_w1
        pop af
        jp  fe_index

; The word typed so far, the cursor under its place.
fe_pw_word:
        ld  bc, 15 * 256 + 112
        ld  de, 10 * 256 + 8
        call fe_pristine
        ld  a, FA_FONT_MENU
        ld  d, PN_PW_WHITE
        ld  e, d
        ld  c, 0
        call fe_ink
        ld  hl, fe_word
        ld  a, 10
        ld  bc, 15 * 256 + 112
        call fe_textn
        ld  a, (fe_wpos)
        add a, 15
        ld  b, a
        ld  c, 113
        ld  hl, fe_fpw_cursor
        ld  a, 1
        jp  fe_textn
fe_fpw_cursor:
        DB  "_"

; -> A = the entry of txt_passwords the word is, $FF if none.
fe_pw_check:
        xor a
        ld  (fe_row), a
fe_fpc_1:  ld  a, (fe_row)
        FE_TXT txt_passwords
        ld  de, fe_word
        ld  b, 10
fe_fpc_2:  ld  a, (de)
        cp  (hl)
        jr  nz, fe_fpc_no
        inc hl
        inc de
        djnz fe_fpc_2
        ld  a, (fe_row)
        ret
fe_fpc_no: ld  a, (fe_row)
        inc a
        ld  (fe_row), a
        cp  TXT_PASSWORDS_COUNT
        jr  c, fe_fpc_1
        ld  a, $FF
        ret

; ============================================================== the end

; A = house: Arrakis in its colours, and the credits scrolling over it.
fe_ending:
        ld  (fe_house), a
        add a, a                ; x 2: the palette (fade), the picture
        add a, FA_PAL_ENDING_H
        ld  (fe_endpal), a
        ld  a, $21
        FCALL snd_music
        ld  a, (fe_endpal)
        call fe_prepare
        ld  a, (fe_endpal)
        inc a
        call fe_pic
        ld  a, (fe_house)
        ld  hl, fe_fen_pens
        add a, a
        add a, l
        ld  l, a
        jr  nc, fe_fen_0
        inc h
fe_fen_0:  ld  a, (hl)
        ld  (fe_endpen), a
        inc hl
        ld  a, (hl)
        ld  (fe_endpen + 1), a
        call fe_begin
        ld  hl, -25
        ld  (fe_top), hl
        call pad_take
fe_fen_step:
        call fe_credits_draw
        jr  nc, fe_fen_over
        ld  b, 24
        call fe_frames
        and $F0
        jr  nz, fe_fen_over
        ld  hl, (fe_top)
        inc hl
        ld  (fe_top), hl
        jr  fe_fen_step
fe_fen_over:
        ld  b, 100
        call fe_frames
        jp  fe_fade_out_cur
fe_fen_pens:
        DB  PN_END_H_WHITE, PN_END_H_YELLOW
        DB  PN_END_A_WHITE, PN_END_A_YELLOW
        DB  PN_END_O_WHITE, PN_END_O_YELLOW

; The credits' lines fe_top on at lines 0-24 of the screen, over a clean
; picture.  -> carry while any line is still to come or on the screen.
fe_credits_draw:
        ld  bc, 0
        ld  de, 40 * 256 + 200
        call fe_pristine
        ld  hl, txt_credits
        ld  c, $$txt_credits
        xor a
        call fe_txt_addr
        ld  (fe_cp), hl
        ld  a, c
        ld  (fe_cpage), a
        ld  a, 3
        ld  (fe_ccol), a
        ld  hl, 0
        ld  (fe_line), hl
        xor a
        ld  (fe_any), a
fe_fcd_line:
        ; copy the line (and follow its colour codes)
        ld  a, (fe_cpage)
        call map_w1
        ld  hl, (fe_cp)
        ld  de, fe_strbuf
        ld  b, 0
fe_fcd_c:  ld  a, (hl)
        cp  $FF
        jr  z, fe_fcd_eol
        inc hl
        cp  $0A
        jr  z, fe_fcd_eol
        cp  $FE
        jr  nz, fe_fcd_ch
        ld  a, (hl)
        inc hl
        ld  (fe_ccol), a
        jr  fe_fcd_c
fe_fcd_ch: ld  (de), a
        inc de
        inc b
        ld  a, b
        cp  40
        jr  c, fe_fcd_c
        dec de
        dec b
        jr  fe_fcd_c
fe_fcd_eol:
        ld  (fe_cp), hl
        ld  (fe_cend), a
        ; on the screen?  row = line - top, 0-24
        push bc
        ld  hl, (fe_line)
        ld  de, (fe_top)
        or  a
        sbc hl, de
        pop bc
        ld  a, h
        or  a
        jr  nz, fe_fcd_next        ; above (negative) or far below
        ld  a, l
        cp  25
        jr  nc, fe_fcd_below
        ld  a, 1
        ld  (fe_any), a
        ld  a, b
        or  a
        jr  z, fe_fcd_next
        ; centred, in the colour of its kind (2 headings, 3 names)
        push bc
        ld  a, l
        add a, a
        add a, a
        add a, a
        ld  (fe_cy), a
        ld  a, (fe_ccol)
        cp  2
        ld  a, (fe_endpen)
        jr  nz, fe_fcd_1
        ld  a, (fe_endpen + 1)
fe_fcd_1:  ld  d, a
        ld  e, a
        ld  c, 0
        ld  a, FA_FONT8
        call fe_ink
        pop bc
        ld  a, 40
        sub b
        srl a
        ld  c, b
        ld  b, a
        ld  a, c
        push af
        ld  a, (fe_cy)
        ld  c, a
        pop af
        ld  hl, fe_strbuf
        call fe_textn
        jr  fe_fcd_next
fe_fcd_below:
        ld  a, 1
        ld  (fe_any), a
        scf
        ret
fe_fcd_next:
        ld  a, (fe_cend)
        cp  $FF
        jr  z, fe_fcd_done
        ld  hl, (fe_line)
        inc hl
        ld  (fe_line), hl
        jp  fe_fcd_line
fe_fcd_done:
        ld  a, (fe_any)
        rrca                    ; carry = something was on the screen
        ret

; ============================================================ the data

; Per house (H, A, O): the portrait, eyes 0, mouth 0, the first button,
; the button frame, the palette, the dim owner tables, the text's pen.
fe_houses:
        DB  FA_MENTAT_H, FA_EYES_H_0, FA_MOUTH_H_0, FA_BUTTON_H_YES
        DB  FA_BUTTON_HL_H, FA_PAL_MENTAT_H, FA_OWN_DIM_H_0, PN_MENTAT_H_WHITE
        DB  FA_MENTAT_A, FA_EYES_A_0, FA_MOUTH_A_0, FA_BUTTON_A_YES
        DB  FA_BUTTON_HL_A, FA_PAL_MENTAT_A, FA_OWN_DIM_A_0, PN_MENTAT_A_WHITE
        DB  FA_MENTAT_O, FA_EYES_O_0, FA_MOUTH_O_0, FA_BUTTON_O_YES
        DB  FA_BUTTON_HL_O, FA_PAL_MENTAT_O, FA_OWN_DIM_O_0, PN_MENTAT_O_WHITE

fe_black:
        DS  16, $FF

        INCLUDE "front.inc"

; ======================================================= the variables

fe_dst_a:       DB 0
fe_dst_b:       DB 0
fe_src_a:       DB 0
fe_src_b:       DB 0
fe_cr_off:      DW 0
fe_fillb:       DB 0
fe_dl0:         DS 2 + FE_RECTS * 4
fe_dl1:         DS 2 + FE_RECTS * 4
fe_qn:          DB 0
fe_queue:       DS FE_QMAX * 4
fe_qkeep:       DB 0
fe_qsave:       DS FE_QMAX * 4
fe_keys:        DB 0
fe_pcol:        DB 0
fe_py:          DB 0
fe_pw:          DB 0
fe_ph:          DB 0
fe_pflags:      DB 0
fe_pstride:     DW 0
fe_psize:       DW 0
fe_pbase:       DW 0
fe_lz_end:      DW 0
fe_bw:          DB 0
fe_bh:          DB 0
fe_boff:        DW 0
fe_rows:        DB 0
fe_sw:          DB 0
fe_sh:          DB 0
fe_soff:        DW 0
fe_tcol:        DB 0
fe_ty:          DB 0
fe_tyraw:       DB 0
fe_zr:          DS FZ_REC       ; the zoom: the territory's FA_ZOOM record
fe_zd:          DB 0            ; the render (0-15)
fe_zt0:         DB 0            ; frame_count at the start
fe_zwhen:       DB 0
fe_zfade:       DB 0            ; the fade step shown (4 full, 0 black)
fe_zoc:         DW 0            ; the last picture's column, line (C, B)
fe_zow:         DB 0            ; ... its width (0: none) and height
fe_zoh:         DB 0
fe_zf:          DB 0            ; the scale's fraction (0: 1.0)
fe_zw:          DW 0            ; the picture's width in pixels
fe_zh:          DB 0            ; ... and height in lines
fe_zax:         DW 0            ; its corner on the screen
fe_zay:         DW 0
fe_zc0:         DB 0            ; the columns it covers
fe_zcn:         DB 0
fe_zcnt:        DB 0
fe_zX:          DW 0            ; the x accumulator: picture x, source
fe_zxi:         DW 0            ;   x's whole part and fraction
fe_zxf:         DB 0
fe_zyi:         DW 0            ; the line accumulator
fe_zyf:         DB 0
fe_zy:          DB 0
fe_zlast:       DB 0            ; the source row FZ_ROW holds
fe_zytop:       DB 0            ; the lines drawn
fe_zyn:         DB 0
fe_zoff:        DW 0
fe_zpar:        DB 0
fe_ss:          DS 3            ; the starfield's scroll: fraction, then
                                ; the whole pixels (signed)
fe_sv:          DW 0            ; its speed, 8.8
fe_swrap:       DB 0            ; menu_scroll_vblank's $FFD70A,
fe_skeep:       DB 0            ;   $FFD70B (wrap round) and
fe_sbrake:      DB 0            ;   $FFD708 (braking)
fe_sframe:      DB 0            ; frame_count it is up to date with
fe_starson:     DB 0            ; fe_frame draws the stars
fe_splanet:     DB 0            ; ... and the planet
fe_stoff:       DB 0            ; the lines the screen drops
fe_sglyph:      DW 0            ; the screen's glyphs in FA_STARS
fe_sl0:         DS 1 + FS_MAX * 3   ; per screen the stars drawn: a count,
fe_sl1:         DS 1 + FS_MAX * 3   ; then (column, line, width) each
fe_spc0:        DB 0            ; per screen the planet's column ($FF)
fe_spc1:        DB 0
fe_spcol:       DB 0
fe_scnt:        DB 0
fe_sptr:        DW 0
fe_sx:          DW 0
fe_sy:          DB 0
fe_sg:          DB 0
fe_spy:         DB 0
fe_sright:      DB 0
fe_splane:      DB 0
fe_tw:          DB 0
fe_th:          DB 0
fe_trow:        DB 0
fe_tdata:       DW 0
fe_font:        DB 0
fe_pens:        DS 4
fe_tlen:        DB 0
fe_tstr:        DW 0
fe_toff:        DW 0
fe_tfont:       DW 0
fe_numbuf:      DS 5
fe_ch:          DB 0
fe_fade:        DB 0
fe_curpal:      DB 0
fe_curfade:     DB $FF
fe_seed:        DB 0
fe_i:           DB 0
fe_kidx:        DB 0            ; fe_redefine: the key just pressed
fe_lny:         DB 0            ; fe_lines: the next line's y
fe_lnp:         DW 0            ;   its first character
fe_lne:         DW 0            ;   where it ends
fe_kshift:      DB 0, 0         ;   a shift seen: its half-row, its bit
fe_newkeys:     DS 16           ;   the keys chosen: half-row, bit a button
fe_j:           DB 0
fe_dy:          DB 0
fe_sel:         DB 0
fe_idle:        DW 0
fe_row:         DB 0
fe_cy:          DB 0
fe_yes:         DB 0
fe_battle:      DB 0
fe_house:       DB 0
fe_mission:     DB 0
fe_won:         DB 0
fe_brief:       DB 0
fe_hs:          DS 8
fe_ownbase:     DB 0
fe_fmrp:        DB 0
fe_ownmode:     DB 0            ; fe_own's pens: 0 all, FE_OWN_LAND, FE_OWN_BORDERS
fe_target:      DB 0
fe_gonebits:    DW 0
FE_SLOTS        EQU 4           ; campaign_lift_territory's four slots
fe_slots:       DS FE_SLOTS * 2 ; a falling territory ($FF none), its lift
fe_lift:        DB 0            ; frame_count when the next lift is due
fe_mouth:       DB 0
fe_eyes:        DB 0
fe_eye_t:       DB 0
fe_talk:        DW 0            ; frame_count when the wait or sentence ends
fe_talking:     DB 0            ; 1 while the mouth moves
fe_mouth_t:     DW 0            ; frame_count when the mouth next changes
fe_saylen:      DW 0             ; the sentence's frames, four a character
fe_nsent:       DB 0
fe_pad_cut:     DB 0
fe_mseed:       DW 1            ; fe_mrand's state, never 0
fe_sp:          DW 0
fe_se:          DW 0
fe_btn:         DB 0
fe_vd:          DS 4
fe_bv0:         DW 0
fe_bv1:         DW 0
fe_by:          DB 0
fe_bscale:      DW 0
fe_bval:        DW 0
fe_bshown:      DW 0
fe_bpens:       DS 2
fe_bn:          DB 0
fe_mtest:       DB 0
fe_ptr_y:       DB 0            ; the options pointer's y on its slide
fe_stest:       DB 0
fe_word:        DS 10
fe_wpos:        DB 0
fe_kx:          DB 0
fe_ky:          DB 0
fe_pwkind:      DB 0
fe_endpal:      DB 0
fe_endpen:      DS 2
fe_top:         DW 0
fe_line:        DW 0
fe_cp:          DW 0
fe_cpage:       DB 0
fe_ccol:        DB 0
fe_cend:        DB 0
fe_any:         DB 0
fe_blog_y:      DB 0            ; the start-up log: its last line's y,
fe_blen:        DB 0            ; ... that line's characters
fe_bline:       DS FE_BOOT_W
fe_bch:         DB 0
fe_blink:       DB 0            ; the intro: frames, for PRESS ANY KEY
fe_ldpx:        DB 0            ; the loading bar: its pixels filled
fe_ldbar:       DB 0            ; ... its sand and its track as plane bytes
fe_ldtrk:       DB 0
fe_ldc0:        DB 0            ; ... the first column changed, the last
fe_ldcol:       DB 0
fe_ldb:         DS 4            ; ... a column's four plane bytes
fe_ldoff:       DW 0            ; ... its first row's offset
FE_STRMAX       EQU 400
fe_strbuf:      DS FE_STRMAX
; fe_owntab and fe_inktab, the two page-aligned tables fe_own and fe_ink
; index with H, are in page WORLD (world_vars.inc): this bank is within
; a few hundred bytes of full, and an ALIGN here cost up to 255 of them
; every time the stub grew.
