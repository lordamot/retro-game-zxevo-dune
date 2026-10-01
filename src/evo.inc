; evo.inc - the ZX Evolution BaseConf, as this game uses it.
;
; .claude/docs/platform.md has the long version; this is the form the
; assembler needs.

; ------------------------------------------------------------------- ports

PORT_BF         EQU $BF         ; bit 0 opens the configuration ("shadow")
                                ; ports; without it xx77 and xxF7 do nothing
PORT_FE         EQU $FE         ; border, keyboard - and the palette index
PORT_F6         EQU $F6         ; the same, with A3 low: palette entries 8-15
PORT_FF         EQU $FF         ; palette data (while the shadow ports are open)
PORT_7FFD       EQU $7FFD       ; bit 3: which screen the video reads
PORT_EFF7       EQU $EFF7

; xx77: half of what it says is in the address.  A14 = 0 lets the palette
; port answer; A8 = 1 turns the memory manager on; A9 = 1 lets TR-DOS mode
; switch off as soon as code runs from RAM.  With A9 = 0 (the value was
; $8177) TR-DOS mode is held on: port $1F is then the floppy controller's
; status, not the Kempston joystick, and every floppy-port access goes
; through the firmware's virtual-drive trap - the emulator does neither,
; a real machine did both.  The value carries the video mode in bits 0-2
; and the clock in bit 3.
PORT_77         EQU $8377
V_ZX            EQU %011
V_EGA           EQU %000
TURBO14         EQU %1000

; The memory manager, one port per window, the window in A15-A14.
;
;   xxFF7  flags and six bits of page: bit 7 mix with $7FFD, bit 6 RAM,
;          bits 0-5 the page inverted.  Used once per window at start-up
;          to clear the mix flag the firmware may have left.
;   xx7F7  eight bits of page, inverted; leaves the flags alone.  Every
;          other mapping in the game goes through this one, because the
;          game's pages go up to 255.
MMU_W0          EQU $37F7
MMU_W1          EQU $77F7
MMU_W2          EQU $B7F7
MMU_W3          EQU $F7F7
MMUF_W0         EQU $3FF7
MMUF_W1         EQU $7FF7
MMUF_W2         EQU $BFF7
MMUF_W3         EQU $FFF7

; $7FFD: bit 4 stays set, as the firmware leaves it (it picks which set of
; window registers is live); bit 3 is the screen.
P7FFD_BASE      EQU $10

; ---------------------------------------------------------------- the screen
;
; Four planes of 8000 bytes over two pages, at $0000 and $2000 of each:
;   plane 0  page A + $0000   pixels 0,1 of every eight
;   plane 1  page B + $0000   pixels 2,3
;   plane 2  page A + $2000   pixels 4,5
;   plane 3  page B + $2000   pixels 6,7
; A byte is two pixels: bits 0-2 + bit 6 the left, bits 3-5 + bit 7 the
; right.  Screen 0 is pages 1 and 5, screen 1 pages 3 and 7.

SCR_BYTES       EQU 40
SCR_H           EQU 200
PLANE_SIZE      EQU 8000
PG_SCR0_A       EQU 1
PG_SCR0_B       EQU 5
PG_SCR1_A       EQU 3
PG_SCR1_B       EQU 7
SCR_LO          EQU $C000       ; plane 0 / plane 1 when mapped in window 3
SCR_HI          EQU $E000       ; plane 2 / plane 3

WIN0            EQU $0000
WIN1            EQU $4000
WIN2            EQU $8000
WIN3            EQU $C000

; The cycle profiler: OUT ($FD),A with a mark below $40.  bin/evo/evo-run
; --profile charges the time between marks to the first.  Only a profiling
; build has them (tools/build_dune.py --profile defines PROFILE): on the
; BaseConf an OUT ($FD),A with A below $80 IS a write to $7FFD (the FPGA
; decodes that port on A15 = 0 and the low byte alone, zports.v), and bit
; 4 of the value picks the memory manager's register set - a mark below
; 16 switched every window to the firmware's leftover pages and crashed
; the real machine at the battle's first pass.  A game build has no
; marks at all.
    MACRO PROF n
    IFDEF PROFILE
        ld  a, n
        out ($FD), a
    ENDIF
    ENDM
