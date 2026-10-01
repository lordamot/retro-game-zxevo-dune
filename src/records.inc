; records.inc - the game's records, at the Mega Drive's own offsets.
;
; orig/sega/spec/S2-objects.md is the authority; every name below is the
; spec's.  Two differences from the cartridge: words and longs are
; little-endian here, and a script's pc is a 16-bit Z80 address in the VM
; bank instead of a ROM address.  A position is y word at +$0A, x word at
; +$0C (in 256ths of a square; the high byte is the square).

; ------------------------------------------------------ the object header
; Units and structures share the first $4C bytes.
O_INDEX         EQU $00         ; w  the record's own slot
O_TYPE          EQU $02         ; b
O_LINKED        EQU $03         ; b  linkedID, $FF none
O_FLAGS         EQU $04         ; w  PC ObjectFlags bits 0-15
O_FLAGS2        EQU $06         ; w  bit 0 isUnit, bit 1 upgrading, the rest MD
O_HOUSE         EQU $08         ; b  houseID
O_SEEN          EQU $09         ; b  seenByHouses, a bit per house
O_POS_Y         EQU $0A         ; w
O_POS_X         EQU $0C         ; w
O_SPRITE        EQU $10         ; w  (the port: the renderer's sprite slot; a unit's is U_BLINK below)
O_HP            EQU $12         ; w  hitpoints
O_DELAY         EQU $14         ; w  script.delay
O_SCRIPT        EQU $16         ; the EMC state, $36 bytes (below)

; flags (+$04), low byte / high byte
OF_USED         EQU 0           ; bit 0
OF_ALLOCATED    EQU 1
OF_NOTONMAP     EQU 2           ; isNotOnMap
OF_SMOKING      EQU 3
OF_FIRETWICE    EQU 4           ; fireTwiceFlip (units)
OF_ANIMFLIP     EQU 5           ; animationFlip (units)
OF_BULLETBIG    EQU 6           ; bulletIsBig
OF_WOBBLING     EQU 7           ; isWobbling
OF_INTRANSPORT  EQU 8           ; inTransport          (bit 0 of the high byte)
OF_BYSCENARIO   EQU 9           ; byScenario            (bit 1 of the high byte)
OF_DEGRADES     EQU 10
OF_REPAIRING    EQU 13
OF_ONHOLD       EQU 14

; ------------------------------------------------------ the script state
; At O_SCRIPT in units and structures, T_SCRIPT in teams.  The delay word
; is the word before it.
SC_PC           EQU $00         ; w  Z80 address of the next instruction; 0 stopped
SC_INFO         EQU $04         ; b  which script: 0 UNIT, 1 BUILD, 2 TEAM
SC_RETURN       EQU $08         ; w  returnValue
SC_FP           EQU $0A         ; b  framePointer
SC_SP           EQU $0B         ; b  stackPointer, 15 = empty
SC_VARS         EQU $0C         ; 5 w
SC_STACK        EQU $16         ; 15 w
SC_ISSUB        EQU $34         ; b
SC_SIZE         EQU $36

; ------------------------------------------------------------- a unit
; +$0E-+$11 are a unit's effect animation (fx_anim_start $00A74E, bank
; MOVE2).  On the Mega Drive +$0A is also an "effect object" whose +5 (the
; unit's +$0F) is the life and +6 (+$10) the sprite, which keeps the blink
; and the sound; the port has no sprite records, so they live here.
U_FXSOUND       EQU $0E         ; b  (the port) the sound replayed at each blink (MD: the sprite's +0)
U_FXLIFE        EQU $0F         ; b  frames of the effect animation left
U_BLINK         EQU $10         ; b  (the port) the blink counter (MD: the sprite's +4); bit 7: off this pass
U_BLINKPERIOD   EQU $11         ; b  (the port) its period, 0 not blinking (MD: the sprite's +5, +7 bit 5)
U_LISTNODE      EQU $4C         ; w  (the port: the list node's low byte is U_SHOWN)
U_SHOWN         EQU $4C         ; b  (the port) nonzero: drawn although off the map -
                                ;    a Harvester on a Refinery's pad (MD: its sprite
                                ;    shown by c_spr_show $048966, hidden again by
                                ;    unit_take_off_map $0486F8 or pick.up $044072)
U_DEST_Y        EQU $4E         ; w  currentDestination
U_DEST_X        EQU $50         ; w
U_ORIGIN        EQU $52         ; w  originEncoded (a reference)
U_ACTION        EQU $54         ; b  actionID
U_NEXTACTION    EQU $55         ; b  nextActionID, $FF none
U_FIREDELAY     EQU $56         ; b
U_DISTDEST      EQU $58         ; w  distanceToDestination
U_TARGETATTACK  EQU $5A         ; w  (a Harvester: its harvest sprite)
U_TARGETMOVE    EQU $5C         ; w
U_AMOUNT        EQU $5E         ; b
U_DEVIATED      EQU $5F         ; b
U_PRELAST_Y     EQU $60         ; w  targetPreLast
U_PRELAST_X     EQU $62
U_LAST_Y        EQU $64         ; w  targetLast
U_LAST_X        EQU $66
U_OR0_SPEED     EQU $68         ; b  hull: turn speed (signed), target, current
U_OR0_TARGET    EQU $69
U_OR0_CURRENT   EQU $6A
U_OR1_SPEED     EQU $6B         ; b  turret
U_OR1_TARGET    EQU $6C
U_OR1_CURRENT   EQU $6D
U_SPEEDTICK     EQU $6E         ; b  speedPerTick
U_SPEEDREM      EQU $6F         ; b  speedRemainder
U_SPEED         EQU $70         ; b
U_MOVINGSPEED   EQU $71         ; b
U_WOBBLE        EQU $72         ; b
U_SPRITEOFS     EQU $73         ; b  spriteOffset
U_ORIGHOUSE     EQU $74         ; b  originalHouse
U_TEAM          EQU $75         ; b  team slot + 1
U_ANIMTIMER     EQU $76         ; w
U_STEP_X        EQU $78         ; w
U_STEP_Y        EQU $7A         ; w
U_ROUTE         EQU $7C         ; 16 b, directions 0-7, $FF ends
U_SIZE          EQU $8C
UNIT_COUNT      EQU 102

; ------------------------------------------------------- a structure
S_TURRETFACING  EQU $0F         ; b
S_CREATORHOUSE  EQU $4C         ; w
S_ROTSPRITEDIFF EQU $4E         ; w  (the Palace: specialDelay)
S_TYPEAFTERUPG  EQU $50         ; b  objectTypeAfterUpgrade
S_OBJECTTYPE    EQU $52         ; w
S_UPGRADELEVEL  EQU $54         ; b
S_UPGRADETIME   EQU $55         ; b  upgradeTimeLeft
S_COUNTDOWN     EQU $56         ; w
S_COSTREM       EQU $58         ; w  buildCostRemainder
S_CREDITSPAID   EQU $5A         ; w
S_STATE         EQU $5C         ; w  -1 just built, 0 idle, 1 busy, 2 ready
S_HPMAX         EQU $5E         ; w
S_LISTNODE      EQU $60         ; w  (not used)
S_SIZE          EQU $62
STRUCT_COUNT    EQU 73

; ------------------------------------------------------------ a house
H_INDEX         EQU $00         ; w
H_HARVINCOMING  EQU $02         ; w  harvestersIncoming
H_FLAGS         EQU $04         ; w  bit 0 used, 1 human, 2 doneFullScaleAttack, 3 isAIActive
H_UNITCOUNT     EQU $06         ; w
H_UNITCOUNTMAX  EQU $08         ; w
H_UNITSENEMY    EQU $0A         ; w  unitsCountEnemy
H_UNITSALLIED   EQU $0C         ; w
H_BUILT         EQU $0E         ; l  structuresBuilt, a bit per type
H_CREDITS       EQU $12         ; l
H_STORAGE       EQU $16         ; l  creditsStorage
H_POWERPROD     EQU $1A         ; w
H_POWERUSE      EQU $1C         ; w
H_WINDTRAPS     EQU $1E         ; w
H_QUOTA         EQU $20         ; w
H_PALACE_Y      EQU $22         ; w  palacePosition
H_PALACE_X      EQU $24
H_TIMERUNIT     EQU $28         ; w  timerUnitAttack
H_TIMERWORM     EQU $2A         ; w
H_TIMERSTRUCT   EQU $2C         ; w
H_STARPORTTIME  EQU $2E         ; w
H_STARPORTLINK  EQU $30         ; w  -1 none
H_REBUILD       EQU $32         ; 5 x (w type, w square)
H_SIZE          EQU $46
HOUSE_COUNT     EQU 6

HF_USED         EQU 0
HF_HUMAN        EQU 1
HF_FULLATTACK   EQU 2
HF_AIACTIVE     EQU 3

; ------------------------------------------------------------- a team
T_INDEX         EQU $00
T_USED          EQU $02
T_MEMBERS       EQU $04
T_MINMEMBERS    EQU $06
T_MAXMEMBERS    EQU $08
T_MOVETYPE      EQU $0A
T_ACTION        EQU $0C
T_ACTIONSTART   EQU $0E
T_HOUSE         EQU $10
T_POS_Y         EQU $14
T_POS_X         EQU $16
T_TARGETTILE    EQU $18
T_TARGET        EQU $1A
T_DELAY         EQU $1C
T_SCRIPT        EQU $1E
T_SIZE          EQU $54
TEAM_COUNT      EQU 16

; ------------------------------------------------------------ where they are
UNITS_BASE      EQU $4000       ; window 1, page UNITS
HOUSES_BASE     EQU $7800
TEAMS_BASE      EQU $7A00
STRUCTS_BASE    EQU $8100       ; window 2, page WORLD

; The map, window 3, page MAP: square s = y*64 + x, four planes.
MAP_GROUND      EQU $C000       ; ground icon bits 0-7
MAP_HIGH        EQU $D000       ; ground icon bit 8 | overlay icon << 1
MAP_FLAGS       EQU $E000       ; bits 0-2 house, 3 unveiled, 4 unit, 5 structure
MAP_INDEX       EQU $F000       ; the object's slot + 1

MF_UNVEILED     EQU 3
MF_UNIT         EQU 4
MF_STRUCT       EQU 5

; ------------------------------------------------------------ references
; One word: kind << 14 | value (S2).  1 unit, 2 structure, 3 map square.
REF_UNIT        EQU $4000
REF_STRUCT      EQU $8000
REF_TILE        EQU $C000
