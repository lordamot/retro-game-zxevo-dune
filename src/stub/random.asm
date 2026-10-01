; random.asm - the cartridge's random number generator, bit for bit.
;
; math_random ($000E42) is a shift register over three seed bytes at
; $FFE017-$FFE019 (rnd_seed+0..2 here).  In 68000 terms:
;
;   d0 = s3 >> 2                     X = bit 1 of s3
;   s1 = s1 << 1 | X                 X = old bit 7 of s1
;   s2 = s2 << 1 | X                 X = old bit 7 of s2
;   X = !X
;   d0 = d0 - s3 - X ; d0 >>= 1      X = bit 0 of that
;   s3 = s3 >> 1 | X << 7
;   answer s3 ^ s2
;
; S6's test replays the computer's build choices through exactly this, so
; the port keeps it.

; A = a random byte.  Clobbers flags only.
random:
        push bc
        ld  a, (rnd_seed + 2)
        ld  c, a                ; C = s3
        srl a
        srl a                   ; carry = bit 1 of s3
        ld  b, a                ; B = s3 >> 2
        ld  a, (rnd_seed + 0)
        rla
        ld  (rnd_seed + 0), a
        ld  a, (rnd_seed + 1)
        rla
        ld  (rnd_seed + 1), a
        ccf
        ld  a, b
        sbc a, c
        srl a                   ; carry = bit 0
        ld  a, c
        rra
        ld  (rnd_seed + 2), a
        ld  b, a
        ld  a, (rnd_seed + 1)
        xor b
        pop bc
        ret

; math_rand_between ($000C0C): D = low, E = high (bytes).  A = a number,
; made by masking a random byte down (with $7F, $3F ...) until it is below
; high - low + 1, then adding low.  Not uniform, and a span of 256 always
; answers low - the cartridge's own quirks.  Clobbers flags.
rand_between:
        push bc
        push de
        call random
        ld  c, a                ; the number
        ld  a, e
        sub d
        inc a
        ld  b, a                ; the span
        ld  e, $FF              ; the mask
rb_loop:
        ld  a, b
        cp  c                   ; span > number: done
        jr  z, rb_mask
        jr  nc, rb_done
rb_mask:
        srl e
        ld  a, c
        and e
        ld  c, a
        jr  nz, rb_loop
rb_done:
        ld  a, c
        pop de
        add a, d
        pop bc
        ret
