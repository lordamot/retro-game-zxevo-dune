; move/world.inc - the MOVE subsystem's share of WORLD (window 2):
; only what other banks or the renderer must see.  Budget: 240 bytes.

; The six unit timers (S1 unit_tick_all $04379A-$043836): the game clock
; (timer_game) at which each is next due.  A timer fires on the first pass
; at or after its due time and is then set to that pass's clock plus its
; period.  Like the cartridge's, they are never reset.
mv_tick_unit_move:     DD 0        ; $FFDE98 tickUnitMovement, every 3
mv_tick_unit_rot:      DD 0        ; $FFDE94 tickUnitRotation, every 2
mv_tick_unit_turret:   DD 0        ; $FFDE90 tickUnitTurret, every 20
mv_tick_unit_script:   DD 0        ; $FFDE8C tickUnitScript, every 5
mv_tick_unit_anim:     DD 0        ; $FFDE88 tickUnitAnimation, every 5
mv_tick_unit_dev:      DD 0        ; $FFDE84 tickUnitDeviation, every 60

mv_script_unit:        DW 0        ; $FFDEA0 scriptCurrentUnit: the unit being ticked

; A bit per unit slot: the Harvester's harvesting overlay is shown (S1
; step 10: the cartridge shows or hides the sprite in its +$5A; the frame,
; 0-2, is its +$73).  For the renderer.
mv_harvest_shown:      DS 13
