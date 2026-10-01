; emc.asm - Westwood's EMC script machine (bank VM).
;
; orig/sega/spec/S7-enemy.md, "The machine", is what this implements, one
; opcode at a time.  The three scripts the cartridge loads - UNIT, BUILD
; and TEAM - live in this bank as bytecode (build/gen/scripts.inc, with
; every word little-endian), and a script state's pc is a Z80 address
; inside it, so 0 still means "stopped".
;
; Register use: IX = the script state (the record + O_SCRIPT, or a team +
; T_SCRIPT); the delay word is at IX-2.  A routine a script calls
; (FUNCTION) is found through a per-script table of (bank, address) and
; far-called with IX set; it reads its arguments with emc_arg (the stub)
; and answers in HL.

EMC_UNIT        EQU 0
EMC_BUILD       EQU 1
EMC_TEAM        EQU 2

; ----------------------------------------------------------- the entry
;
; emc_reset / emc_start (PC Script_Reset / Script_Load, $016E78/$016E9C):
; IX = state, A = which script; for emc_start also HL = the entry number
; (a unit's or structure's type, a team's behaviour).  Variables and the
; delay are left alone.

emc_reset:
        ld  (ix + SC_INFO), a
        xor a
        ld  (ix + SC_PC), a
        ld  (ix + SC_PC + 1), a
        ld  (ix + SC_ISSUB), a
        ld  (ix + SC_FP), $11
        ld  (ix + SC_SP), $0F
        ret

emc_start:
        push hl
        call emc_reset
        pop hl
        add hl, hl              ; the entry table holds word offsets
        ld  a, (ix + SC_INFO)
        call emc_tables         ; DE = the code start, BC = the entry table
        push de
        ld  d, b
        ld  e, c
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; the entry's word offset
        add hl, hl
        pop de
        add hl, de
        ld  (ix + SC_PC), l
        ld  (ix + SC_PC + 1), h
        ret

; emc_is_loaded ($016EDC): NZ if the script has a pc.
emc_is_loaded:
        ld  a, (ix + SC_PC)
        or  (ix + SC_PC + 1)
        ret

; A = which script -> DE = its code, BC = its entry table, HL kept.
emc_tables:
        push hl
        ld  l, a
        add a, a
        add a, l                ; *3
        add a, a                ; *6
        ld  l, a
        ld  h, 0
        ld  de, emc_script_table
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        pop hl
        ret

emc_script_table:
        DW  emc_unit_code, emc_unit_entries, emc_unit_funcs
        DW  emc_build_code, emc_build_entries, emc_build_funcs
        DW  emc_team_code, emc_team_entries, emc_team_funcs

; ------------------------------------------------------------ the loops
;
; S1: a unit runs up to B instructions (49 on screen, 17 off) until one
; sets a delay or stops; a structure runs exactly three, the delay not
; looked at between them; a team one.  All answer A = 0 if the last
; instruction stopped the script (emc_run answered 0), else 1.

emc_run_budget:
        push bc
        call emc_run
        pop bc
        or  a
        ret z
        ld  a, (ix - 2)
        or  (ix - 1)
        ld  a, 1
        ret nz                  ; a delay was set
        djnz emc_run_budget
        ret

emc_run_three:
        call emc_run
        or  a
        ret z
        call emc_run
        or  a
        ret z
        jr  emc_run

; ---------------------------------------------------------- one step
;
; emc_run ($016EF0): one instruction.  A = 0 if the script is stopped or
; stops now, 1 otherwise.  IX = the state.  Clobbers everything but IX.

emc_run:
        ld  l, (ix + SC_PC)
        ld  h, (ix + SC_PC + 1)
        ld  a, h
        or  l
        ret z                   ; not loaded: A = 0
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        bit 7, d
        jr  nz, op_goto         ; bit 15: a goto, the rest is the target
        ld  a, d
        and $1F
        ld  c, a                ; the opcode
        bit 6, d
        jr  nz, er_pbyte
        bit 5, d
        jr  nz, er_pword
        ld  de, 0
        jr  er_have
er_pbyte:
        ld  a, e                ; bits 0-7, sign-extended
        rla
        sbc a, a
        ld  d, a
        jr  er_have
er_pword:
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
er_have:
        ld  (ix + SC_PC), l
        ld  (ix + SC_PC + 1), h
        ld  a, c
        cp  19
        jr  nc, emc_stop
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  bc, er_ops
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        jp  (hl)                ; DE = the parameter

er_ops:
        DW  op_jump, op_setret, op_pushret, op_push, op_push
        DW  op_pushvar, op_pushloc, op_pusharg, op_popret, op_popvar
        DW  op_poploc, op_poparg, op_rewind, op_forward, op_function
        DW  op_jumpne, op_unary, op_binary, op_return

; Stop the script: pc = 0, answer 0.
emc_stop:
        xor a
        ld  (ix + SC_PC), a
        ld  (ix + SC_PC + 1), a
        ret

ok1:    ld  a, 1
        ret

; pc = start + 2 * DE (DE taken as signed: a location popped off the
; stack may be anything, and the 68000 adds it as a long).
set_pc:
        push de
        ld  a, (ix + SC_INFO)
        call emc_tables         ; DE = the code start
        pop hl
        add hl, hl
        add hl, de
        ld  (ix + SC_PC), l
        ld  (ix + SC_PC + 1), h
        ld  a, 1
        ret

op_goto:
        res 7, d
op_jump:
        jr  set_pc

op_setret:
        ld  (ix + SC_RETURN), e
        ld  (ix + SC_RETURN + 1), d
        jr  ok1

op_pushret:
        ld  a, d
        or  a
        jr  nz, emc_stop
        ld  a, e
        or  a
        jr  nz, opr_loc
        ld  e, (ix + SC_RETURN)
        ld  d, (ix + SC_RETURN + 1)
        jr  op_push
opr_loc:
        dec a
        jr  nz, emc_stop
        ; push the word index after the next instruction, then the frame
        ; pointer, and make the frame
        ld  a, (ix + SC_INFO)
        call emc_tables         ; DE = code start
        ld  l, (ix + SC_PC)
        ld  h, (ix + SC_PC + 1)
        or  a
        sbc hl, de
        srl h
        rr  l
        inc hl
        ex  de, hl
        call push_de
        or  a
        ret z
        ld  a, (ix + SC_FP)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        call push_de
        or  a
        ret z
        ld  a, (ix + SC_SP)
        add a, 2
        ld  (ix + SC_FP), a
        jr  ok1

op_push:
push_de:
        ld  a, (ix + SC_SP)
        dec a
        cp  15
        jr  nc, emc_stop        ; off the stack: a fault, stop
        ld  (ix + SC_SP), a
        call stack_addr
        ld  (hl), e
        inc hl
        ld  (hl), d
        jr  ok1

; DE = the value popped; A = 1, or A = 0 with the script stopped.
pop_de:
        ld  a, (ix + SC_SP)
        cp  15
        jp  nc, emc_stop
        call stack_addr
        inc a
        ld  (ix + SC_SP), a
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        jp  ok1

; A = a stack index 0-14 -> HL = its address.  Keeps A, DE.
stack_addr:
        push af
        push de
        add a, a
        add a, SC_STACK
        ld  e, a
        ld  d, 0
        push ix
        pop hl
        add hl, de
        pop de
        pop af
        ret

; A = a variable index -> HL = its address.
var_addr:
        push de
        add a, a
        add a, SC_VARS
        ld  e, a
        ld  d, 0
        push ix
        pop hl
        add hl, de
        pop de
        ret

op_pushvar:
        ld  a, e
        cp  5
        jp  nc, emc_stop
        call var_addr
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        jr  push_de

; stack[fp - par - 2]
op_pushloc:
        ld  a, (ix + SC_FP)
        sub e
        sub 2
        jr  loc_push
; stack[fp + par - 1]
op_pusharg:
        ld  a, (ix + SC_FP)
        add a, e
        dec a
loc_push:
        cp  15
        jp  nc, emc_stop
        call stack_addr
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        jr  push_de

op_popret:
        ld  a, d
        or  a
        jp  nz, emc_stop
        ld  a, e
        or  a
        jr  nz, opp_loc
        call pop_de
        or  a
        ret z
        ld  (ix + SC_RETURN), e
        ld  (ix + SC_RETURN + 1), d
        ret
opp_loc:
        dec a
        jp  nz, emc_stop
        ld  a, (ix + SC_SP)
        cp  15
        jp  z, emc_stop         ; returning with an empty stack: the end
        call pop_de
        or  a
        ret z
        ld  (ix + SC_FP), e     ; the frame pointer's low byte
        call pop_de
        or  a
        ret z
        jp  set_pc

op_popvar:
        ld  a, e
        cp  5
        jp  nc, emc_stop
        push af
        call pop_de
        or  a
        jr  z, opv_fail
        pop af
        call var_addr
        ld  (hl), e
        inc hl
        ld  (hl), d
        jp  ok1
opv_fail:
        pop af
        xor a
        ret

op_poploc:
        ld  a, (ix + SC_FP)
        sub e
        sub 2
        jr  loc_pop
op_poparg:
        ld  a, (ix + SC_FP)
        add a, e
        dec a
loc_pop:
        cp  15
        jp  nc, emc_stop
        push af
        call pop_de
        or  a
        jr  z, opv_fail
        pop af
        call stack_addr
        ld  (hl), e
        inc hl
        ld  (hl), d
        jp  ok1

op_rewind:
        ld  a, (ix + SC_SP)
        add a, e
        ld  (ix + SC_SP), a
        jp  ok1

op_forward:
        ld  a, (ix + SC_SP)
        sub e
        ld  (ix + SC_SP), a
        jp  ok1

; returnValue = functions[par & $FF](state).  Answers 1 whatever the
; routine did (a routine may stop or restart the script itself).
op_function:
        ld  a, (ix + SC_INFO)
        ld  l, a
        add a, a
        add a, l
        add a, a
        add a, 4
        ld  l, a
        ld  h, 0
        ld  bc, emc_script_table
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; the function table
        ld  d, 0                ; E = the function number
        add hl, de
        add hl, de
        add hl, de              ; 3 bytes an entry: bank, address
        push ix
        call far_call_ind
        pop ix
        ld  (ix + SC_RETURN), l
        ld  (ix + SC_RETURN + 1), h
        jp  ok1

op_jumpne:
        push de
        call pop_de
        or  a
        pop hl
        ret z
        ld  a, d
        or  e
        jp  nz, ok1
        ex  de, hl
        res 7, d
        jp  set_pc

op_unary:
        push de
        call pop_de
        pop bc
        or  a
        ret z
        ld  a, b
        or  a
        jp  nz, emc_stop
        ld  a, c
        or  a
        jr  z, un_not
        dec a
        jr  z, un_neg
        dec a
        jp  nz, emc_stop
        ld  a, e                ; ~v
        cpl
        ld  e, a
        ld  a, d
        cpl
        ld  d, a
        jp  push_de
un_not:
        ld  a, d
        or  e
        ld  de, 0
        jp  nz, push_de
        inc e
        jp  push_de
un_neg:
        ex  de, hl
        call neg_hl
        ex  de, hl
        jp  push_de

; pop right, pop left, push left op right.  Words, signed where it matters.
op_binary:
        ld  a, d
        or  a
        jp  nz, emc_stop
        ld  a, e
        cp  18
        jp  nc, bin_bad
        push de
        call pop_de             ; right
        or  a
        jr  z, bin_fail1
        push de
        call pop_de             ; left
        or  a
        jr  z, bin_fail2
        ex  de, hl              ; HL = left
        pop de                  ; DE = right
        pop bc                  ; C = the operator
        push hl
        ld  l, c
        ld  h, 0
        add hl, hl
        ld  bc, bin_ops
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ex  (sp), hl            ; HL = left, (SP) = the handler
        ret                     ; jump to it with HL = left, DE = right
bin_fail2:
        pop de
bin_fail1:
        pop de
        xor a
        ret
bin_bad:
        ; pops both and stops
        call pop_de
        or  a
        ret z
        call pop_de
        jp  emc_stop

bin_ops:
        DW  b_and, b_or, b_eq, b_ne, b_lt, b_le, b_gt, b_ge
        DW  b_add, b_sub, b_mul, b_div, b_shr, b_shl, b_band, b_bor
        DW  b_mod, b_xor

b_push_hl:
        ex  de, hl
        jp  push_de
b_true:
        ld  de, 1
        jp  push_de
b_false:
        ld  de, 0
        jp  push_de

b_and:
        ld  a, h
        or  l
        jr  z, b_false
        ld  a, d
        or  e
        jr  z, b_false
        jr  b_true
b_or:
        ld  a, h
        or  l
        or  d
        or  e
        jr  z, b_false
        jr  b_true
b_eq:
        or  a
        sbc hl, de
        jr  z, b_true
        jr  b_false
b_ne:
        or  a
        sbc hl, de
        jr  nz, b_true
        jr  b_false
; signed compare: sets carry for HL < DE (signed)
scmp:
        ld  a, h
        xor d
        jp  m, scmp_diff
        or  a
        sbc hl, de
        ret
scmp_diff:
        ld  a, h                ; signs differ: HL < DE iff HL is negative
        rla                     ; carry = the sign of HL
        ret
b_lt:
        call scmp
        jr  c, b_true
        jr  b_false
b_ge:
        call scmp
        jr  nc, b_true
        jr  b_false
b_le:
        ex  de, hl              ; left <= right  ==  !(right < left)
        call scmp
        jr  nc, b_true
        jr  b_false
b_gt:
        ex  de, hl              ; left > right  ==  right < left
        call scmp
        jr  c, b_true
        jr  b_false
b_add:
        add hl, de
        jr  b_push_hl
b_sub:
        or  a
        sbc hl, de
        jr  b_push_hl
b_mul:
        call mul16
        jr  b_push_hl
b_div:
        ld  a, d
        or  e
        jp  z, emc_stop         ; the cartridge resets the machine; no script does it
        call sdiv16
        jr  b_push_hl
b_mod:
        ld  a, d
        or  e
        jr  z, b_false
        call sdiv16
        ex  de, hl
        jr  b_push_hl
b_shr:
        ld  a, e
        and 63
        jr  z, b_push_hl
        ld  b, a
bshr_l: sra h
        rr  l
        djnz bshr_l
        jp  b_push_hl
b_shl:
        ld  a, e
        and 63
        jp  z, b_push_hl
        ld  b, a
bshl_l: add hl, hl
        djnz bshl_l
        jp  b_push_hl
b_band:
        ld  a, h
        and d
        ld  h, a
        ld  a, l
        and e
        ld  l, a
        jp  b_push_hl
b_bor:
        ld  a, h
        or  d
        ld  h, a
        ld  a, l
        or  e
        ld  l, a
        jp  b_push_hl
b_xor:
        ld  a, h
        xor d
        ld  h, a
        ld  a, l
        xor e
        ld  l, a
        jp  b_push_hl

; RETURN (opcode 18): no script uses it, but it is simple.
op_return:
        ld  a, (ix + SC_SP)
        cp  15
        jp  z, emc_stop
        call pop_de
        or  a
        ret z
        ld  (ix + SC_RETURN), e
        ld  (ix + SC_RETURN + 1), d
        call pop_de
        or  a
        ret z
        ld  (ix + SC_ISSUB), 0
        jp  set_pc
