; house/world.inc - the HOUSE subsystem's share of WORLD (window 2):
; only what other banks or the renderer must see.  Budget: 240 bytes.

; ------------------------------------------------------------ the timers
; S1: "next due" times on the game clock (timer_game), 32 bits, never
; reset - they carry over from one mission to the next as the cartridge's
; do.  Here rather than in the bank so tests and tools can read them.
tick_house_house:       DD 0    ; $FFDC44  900: harvesters, power, warnings
tick_house_power:       DD 0    ; $FFDC40  10800: power upkeep
tick_house_starport:    DD 0    ; $FFDC3C  60: the Frigate's countdown
tick_house_reinf:       DD 0    ; $FFDC38  600: the reinforcements
tick_house_unused:      DD 0    ; $FFDC34  5: set and never read
tick_house_missile:     DD 0    ; $FFDC30  60: the house missile countdown
tick_house_avail:       DD 0    ; $FFDC2C  1800: Starport restocking
tick_team:              DD 0    ; $FFDCA4  5 + (random & 7): the teams
tick_level_end:         DD 0    ; $FFDC28  300: is the mission over?

; ------------------------------------------------------------- the end (S9)
; level_result: 0 the battle runs, 1 won, 2 lost.  Set by
; game_check_level_end together with level_over.
level_result:           DB 0
; playerCredits $FFC058: the number the credits counter shows, rolling
; towards the player's credits (S5 ui_draw_credits $011F34 - the UI rolls
; it every pass).  The quota is tested against this, not against the
; house's credits: a quota mission is met when the counter shows it.
; $FFFF means "not counted yet" and never meets a quota.
credits_shown:          DD 0
; What the score page needs (score_screen $0271DE), filled in when the
; mission ends.  The score itself is `score` ($FFC05E), already cut to a
; tenth after a loss.  S9: mission = campaignID + 1 before the win moves
; it on; ticks = the clock less missionStartTime; hours = ticks / 180000,
; minutes = ticks / 3000 mod 60 (50 a second); rank 0-7 = how many of the
; thresholds 50 100 150 200 250 300 400 $FFFF the score reaches
; (unsigned), 8 = Ruler of Arrakis (mission 9 won).
score_mission:          DB 0
score_rank:             DB 0
score_hours:            DW 0
score_minutes:          DW 0
score_ticks:            DD 0

; ------------------------------------------------------------ shared state
; (house_missile_count, $FFC1A4 - the Death Hand countdown the house loop
; counts down - is COMBAT's: combat/world.inc.)
; S7: 0 = the Mega Drive's inert teams (recruit walks the enemy's list and
; finds nobody); 1 = the harder option, the PC's rule (own side, only the
; mission's own units).
ai_recruit_fix:         DB 0

; The HOUSE banks' search states and positions: they are handed to OBJ,
; so they must be in a window that stays (port-code.md).
hs_search:              DS 3
hs_search2:             DS 3
hs_pos:                 DS 4
hs_pos2:                DS 4
hs_now:                 DS 4    ; the clock this pass
