; maths.asm - integer arithmetic, the way the 68000 did it.
;
; Part of the stub, so every bank has it.  Where the cartridge has a
; routine of its own (math_mul_shr8, math_div_shl8) this is that routine,
; rounding and saturation included: the specs quote its results.

; HL = HL * DE, low 16 bits.  In: HL, DE.  Out: HL.  Clobbers A, BC, DE.
mul16:
        ld  b, h
        ld  c, l
        ld  hl, 0
        ld  a, 16
m16_loop:
        add hl, hl
        rl  e
        rl  d
        jr  nc, m16_skip
        add hl, bc
m16_skip:
        dec a
        jr  nz, m16_loop
        ret

; DEHL = HL * DE, unsigned 32 bits.  Clobbers A, BC.
mul32:
        ld  b, h
        ld  c, l                ; BC = multiplicand
        ld  hl, 0               ; HL = low word of the product
        ld  a, 16
m32_loop:
        add hl, hl              ; shift the 32-bit DE:HL left, taking the
        rl  e                   ; multiplier's top bit out of DE as we go
        rl  d
        jr  nc, m32_skip
        add hl, bc
        jr  nc, m32_skip
        inc de
m32_skip:
        dec a
        jr  nz, m32_loop
        ret

; math_mul_shr8 ($0199D8): HL = min((HL * DE + $50) >> 8, $FFFF), unsigned.
; Clobbers A, BC, DE.
mul_shr8:
        call mul32              ; DE:HL
        ld  bc, $50
        add hl, bc
        jr  nc, ms8_nc
        inc de
ms8_nc:
        ld  a, d                ; the result is DE:H; over $FFFF if D != 0
        or  a
        jr  nz, ms8_sat
        ld  l, h
        ld  h, e
        ret
ms8_sat:
        ld  hl, $FFFF
        ret

; math_div_shl8 ($0199F6): HL = DE * 256 / HL.  While DE*256 does not fit
; 16 bits, both it and the divisor are halved, rounding up (the divisor
; wraps at 16 bits as the 68000's addq.w does).  A divisor of 0 answers
; $FFFF.  Clobbers A, BC, DE.
div_shl8:
        ld  b, h
        ld  c, l                ; BC = the divisor
        ld  h, e
        ld  l, 0                ; D:H:L = the 24-bit dividend DE*256
dsh_loop:
        ld  a, d
        or  a
        jr  z, dsh_fits
        ; dividend = (dividend + 1) >> 1
        inc l
        jr  nz, dsh_inc_done
        inc h
        jr  nz, dsh_inc_done
        inc d
dsh_inc_done:
        srl d
        rr  h
        rr  l
        ; divisor = ((divisor + 1) & $FFFF) >> 1
        inc bc
        srl b
        rr  c
        jr  dsh_loop
dsh_fits:
        ld  a, b
        or  c
        jr  z, dsh_zero
        ld  d, b
        ld  e, c
        jp  udiv16
dsh_zero:
        ld  hl, $FFFF
        ret

; HL = HL / DE, DE = the remainder, unsigned.  DE = 0 answers HL = $FFFF.
; Clobbers A, BC.
udiv16:
        ld  a, d
        or  e
        jp  z, ud_zero
        ld  b, d
        ld  c, e                ; BC = divisor
        ex  de, hl              ; DE = dividend
        ld  hl, 0               ; HL = remainder
        ld  a, 16
ud_loop:
        sla e
        rl  d                   ; dividend bit out, quotient bit 0 in
        adc hl, hl
        sbc hl, bc
        jr  nc, ud_fits
        add hl, bc
        dec a
        jr  nz, ud_loop
        jr  ud_done
ud_fits:
        inc e
        dec a
        jr  nz, ud_loop
ud_done:
        ex  de, hl              ; HL = quotient, DE = remainder
        ret
ud_zero:
        ld  hl, $FFFF
        ld  de, 0
        ret

; Signed HL / DE, rounding toward zero (the 68000's divs.w, no overflow
; case handled).  HL = quotient, DE = remainder (sign of the dividend).
; Clobbers A, BC.
sdiv16:
        ld  a, h
        xor d
        push af                 ; the quotient's sign in bit 7
        ld  a, h
        push af                 ; the remainder's sign
        bit 7, h
        call nz, neg_hl
        ex  de, hl
        bit 7, h
        call nz, neg_hl
        ex  de, hl
        call udiv16
        pop af
        bit 7, a
        jr  z, sd_rem_ok
        ex  de, hl
        call neg_hl
        ex  de, hl
sd_rem_ok:
        pop af
        bit 7, a
        ret z
        ; fall through
neg_hl:
        xor a
        sub l
        ld  l, a
        sbc a, a
        sub h
        ld  h, a
        ret

neg_de:
        xor a
        sub e
        ld  e, a
        sbc a, a
        sub d
        ld  d, a
        ret

; HL = |HL|.
abs_hl:
        bit 7, h
        ret z
        jr  neg_hl
