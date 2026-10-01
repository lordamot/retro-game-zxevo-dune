#!/usr/bin/env python3
"""Disassemble raw Z80 machine code into sjasmplus-compatible assembly source.

Usage:
    z80_disasm.py INPUT.bin --org 0x8000 [--start N] [--length N] [--out FILE.asm] [--no-labels]

Supports the full documented Z80 instruction set plus the common
undocumented forms: IXH/IXL/IYH/IYL 8-bit halves, DD CB d/FD CB d indexed
bit-ops (including the undocumented register-copy variants), and the
quirk where H/L stay literal (not promoted to IXH/IXL) whenever the same
instruction also references (IX+d)/(IY+d).
"""

import argparse
import sys

R = ['B', 'C', 'D', 'E', 'H', 'L', '(HL)', 'A']
RP = ['BC', 'DE', 'HL', 'SP']
RP2 = ['BC', 'DE', 'HL', 'AF']
CC = ['NZ', 'Z', 'NC', 'C', 'PO', 'PE', 'P', 'M']
ALU = ['ADD A,', 'ADC A,', 'SUB ', 'SBC A,', 'AND ', 'XOR ', 'OR ', 'CP ']
ROT = ['RLC', 'RRC', 'RL', 'RR', 'SLA', 'SRA', 'SLL', 'SRL']
IM = ['0', '0', '1', '2', '0', '0', '1', '2']


def hx8(v):
    return f'#{v & 0xFF:02X}'


def hx16(v):
    return f'#{v & 0xFFFF:04X}'


def disp_str(index, d):
    if d == 0:
        return f'({index})'
    if d > 0:
        return f'({index}+{d})'
    return f'({index}-{-d})'


class Truncated(Exception):
    pass


class Instr:
    def __init__(self, addr, length, raw, text, target=None):
        self.addr = addr
        self.length = length
        self.raw = raw
        self.text = text
        self.target = target


class Decoder:
    def __init__(self, data, org):
        self.data = data
        self.org = org
        self.pos = org

    def _off(self):
        off = self.pos - self.org
        if off < 0 or off >= len(self.data):
            raise Truncated()
        return off

    def read_u8(self):
        v = self.data[self._off()]
        self.pos += 1
        return v

    def read_s8(self):
        v = self.read_u8()
        return v - 256 if v >= 128 else v

    def read_u16(self):
        lo = self.read_u8()
        hi = self.read_u8()
        return lo | (hi << 8)

    def decode_main(self, index):
        opcode_addr = self.pos
        opcode = self.read_u8()
        used = [False]

        def slot(idx, suppress_ixhl=False):
            if idx == 6:
                if index:
                    used[0] = True
                    d = self.read_s8()
                    return disp_str(index, d)
                return '(HL)'
            if idx in (4, 5) and index and not suppress_ixhl:
                used[0] = True
                return index + ('H' if idx == 4 else 'L')
            return R[idx]

        def rp(p):
            if p == 2 and index:
                used[0] = True
                return index
            return RP[p]

        def rp2(p):
            if p == 2 and index:
                used[0] = True
                return index
            return RP2[p]

        x = (opcode >> 6) & 3
        y = (opcode >> 3) & 7
        z = opcode & 7
        p = y >> 1
        q = y & 1
        text = None
        target = None

        if x == 0:
            if z == 0:
                if y == 0:
                    text = 'NOP'
                elif y == 1:
                    text = "EX AF,AF'"
                elif y == 2:
                    d = self.read_s8()
                    target = self.pos + d
                    text = f'DJNZ {hx16(target)}'
                elif y == 3:
                    d = self.read_s8()
                    target = self.pos + d
                    text = f'JR {hx16(target)}'
                else:
                    d = self.read_s8()
                    target = self.pos + d
                    text = f'JR {CC[y - 4]},{hx16(target)}'
            elif z == 1:
                if q == 0:
                    nn = self.read_u16()
                    text = f'LD {rp(p)},{hx16(nn)}'
                else:
                    text = f'ADD {rp(2)},{rp(p)}'
            elif z == 2:
                if q == 0:
                    if p == 0:
                        text = 'LD (BC),A'
                    elif p == 1:
                        text = 'LD (DE),A'
                    elif p == 2:
                        nn = self.read_u16()
                        text = f'LD ({hx16(nn)}),{rp(2)}'
                    else:
                        nn = self.read_u16()
                        text = f'LD ({hx16(nn)}),A'
                else:
                    if p == 0:
                        text = 'LD A,(BC)'
                    elif p == 1:
                        text = 'LD A,(DE)'
                    elif p == 2:
                        nn = self.read_u16()
                        text = f'LD {rp(2)},({hx16(nn)})'
                    else:
                        nn = self.read_u16()
                        text = f'LD A,({hx16(nn)})'
            elif z == 3:
                text = f'{"INC" if q == 0 else "DEC"} {rp(p)}'
            elif z == 4:
                text = f'INC {slot(y)}'
            elif z == 5:
                text = f'DEC {slot(y)}'
            elif z == 6:
                dest = slot(y)
                n = self.read_u8()
                text = f'LD {dest},{hx8(n)}'
            else:
                text = ['RLCA', 'RRCA', 'RLA', 'RRA', 'DAA', 'CPL', 'SCF', 'CCF'][y]
        elif x == 1:
            if y == 6 and z == 6:
                text = 'HALT'
            else:
                mem_present = (y == 6 or z == 6)
                dest = slot(y, suppress_ixhl=mem_present)
                src = slot(z, suppress_ixhl=mem_present)
                text = f'LD {dest},{src}'
        elif x == 2:
            text = f'{ALU[y]}{slot(z)}'
        else:
            if z == 0:
                text = f'RET {CC[y]}'
            elif z == 1:
                if q == 0:
                    text = f'POP {rp2(p)}'
                else:
                    if p == 0:
                        text = 'RET'
                    elif p == 1:
                        text = 'EXX'
                    elif p == 2:
                        text = f'JP ({rp(2)})'
                    else:
                        text = f'LD SP,{rp(2)}'
            elif z == 2:
                nn = self.read_u16()
                text = f'JP {CC[y]},{hx16(nn)}'
                target = nn
            elif z == 3:
                if y == 0:
                    nn = self.read_u16()
                    text = f'JP {hx16(nn)}'
                    target = nn
                elif y == 1:
                    raise AssertionError('CB must be handled by caller')
                elif y == 2:
                    n = self.read_u8()
                    text = f'OUT ({hx8(n)}),A'
                elif y == 3:
                    n = self.read_u8()
                    text = f'IN A,({hx8(n)})'
                elif y == 4:
                    text = f'EX (SP),{rp(2)}'
                elif y == 5:
                    text = 'EX DE,HL'
                elif y == 6:
                    text = 'DI'
                else:
                    text = 'EI'
            elif z == 4:
                nn = self.read_u16()
                text = f'CALL {CC[y]},{hx16(nn)}'
                target = nn
            elif z == 5:
                if q == 0:
                    text = f'PUSH {rp2(p)}'
                else:
                    if p == 0:
                        nn = self.read_u16()
                        text = f'CALL {hx16(nn)}'
                        target = nn
                    else:
                        raise AssertionError('DD/ED/FD must be handled by caller')
            elif z == 6:
                n = self.read_u8()
                text = f'{ALU[y]}{hx8(n)}'
            else:
                text = f'RST {hx8(y * 8)}'

        return used[0], text, target

    def decode_cb(self, index=None):
        if index:
            d = self.read_s8()
            mem = disp_str(index, d)
        opcode = self.read_u8()
        x = (opcode >> 6) & 3
        y = (opcode >> 3) & 7
        z = opcode & 7
        target_reg = mem if index else R[z]
        if x == 0:
            text = f'{ROT[y]} {target_reg}'
        elif x == 1:
            text = f'BIT {y},{target_reg}'
        elif x == 2:
            text = f'RES {y},{target_reg}'
        else:
            text = f'SET {y},{target_reg}'
        if index and z != 6 and x != 1:
            text += f',{R[z]}'
        return text

    def decode_ed(self):
        opcode = self.read_u8()
        x = (opcode >> 6) & 3
        y = (opcode >> 3) & 7
        z = opcode & 7
        p = y >> 1
        q = y & 1

        if x == 1:
            if z == 0:
                text = 'IN (C)' if y == 6 else f'IN {R[y]},(C)'
            elif z == 1:
                text = 'OUT (C),0' if y == 6 else f'OUT (C),{R[y]}'
            elif z == 2:
                text = f'{"SBC" if q == 0 else "ADC"} HL,{RP[p]}'
            elif z == 3:
                nn = self.read_u16()
                if p == 2:
                    # ED 63/6B: undocumented duplicate of the shorter LD
                    # (nn),HL / LD HL,(nn) opcodes. sjasmplus would re-encode
                    # the mnemonic form using the shorter opcode, losing a
                    # byte, so keep this one literal.
                    text = (f'DEFB #ED,{hx8(opcode)},{hx8(nn & 0xFF)},{hx8(nn >> 8)} '
                            '; undocumented ED-encoded LD (kept literal, shorter opcode exists)')
                else:
                    text = f'LD ({hx16(nn)}),{RP[p]}' if q == 0 else f'LD {RP[p]},({hx16(nn)})'
            elif z == 4:
                if y == 0:
                    text = 'NEG'
                else:
                    # ED 4C/54/5C/64/6C/74/7C: undocumented NEG duplicates
                    # (canonical ED 44).
                    text = f'DEFB #ED,{hx8(opcode)} ; undocumented NEG duplicate (kept literal)'
            elif z == 5:
                if y == 1:
                    text = 'RETI'
                elif y == 0:
                    text = 'RETN'
                else:
                    # ED 55/5D/65/6D/75/7D: undocumented duplicates of RETN
                    # (canonical ED 45). The mnemonic would reassemble to the
                    # canonical opcode, losing which duplicate was on disk.
                    text = f'DEFB #ED,{hx8(opcode)} ; undocumented RETN duplicate (kept literal)'
            elif z == 6:
                # canonical: y=0 -> IM 0 (ED 46), y=2 -> IM 1 (ED 56),
                # y=3 -> IM 2 (ED 5E). y=1,5 ("IM 0/1") and the y=4,6,7
                # duplicates would reassemble to the canonical opcode.
                if y in (0, 2, 3):
                    text = f'IM {IM[y]}'
                else:
                    text = f'DEFB #ED,{hx8(opcode)} ; undocumented IM duplicate (kept literal)'
            elif y in (6, 7):
                # ED 7E/7F: undocumented duplicate of NOP, but still 2 bytes
                # on real hardware - plain "NOP" would only assemble 1 byte.
                text = f'DEFB #ED,{hx8(opcode)} ; undocumented ED NOP (kept literal, 2 bytes)'
            else:
                text = ['LD I,A', 'LD R,A', 'LD A,I', 'LD A,R', 'RRD', 'RLD'][y]
            return text
        if x == 2 and 4 <= y <= 7 and z <= 3:
            names = [
                ['LDI', 'CPI', 'INI', 'OUTI'],
                ['LDD', 'CPD', 'IND', 'OUTD'],
                ['LDIR', 'CPIR', 'INIR', 'OTIR'],
                ['LDDR', 'CPDR', 'INDR', 'OTDR'],
            ]
            return names[y - 4][z]
        return None

    def decode(self):
        """Returns a list of Instr - usually one, but two when a DD/FD prefix
        turns out to be wasted (its own byte must still be emitted, as a
        standalone DEFB, ahead of the unaffected instruction that follows)."""
        start = self.pos
        b = self.read_u8()
        if b == 0xCB:
            text = self.decode_cb()
            return [Instr(start, self.pos - start, self._bytes(start), text)]
        if b == 0xED:
            saved = self.pos
            text = self.decode_ed()
            if text is None:
                nb = self.data[self._off_at(saved)]
                self.pos = saved + 1
                return [Instr(start, self.pos - start, self._bytes(start),
                              f'DEFB {hx8(b)},{hx8(nb)} ; undefined ED opcode')]
            return [Instr(start, self.pos - start, self._bytes(start), text)]
        if b in (0xDD, 0xFD):
            index = 'IX' if b == 0xDD else 'IY'
            try:
                nb = self.data[self._off()]
            except Truncated:
                return [Instr(start, 1, self._bytes(start),
                              f'DEFB {hx8(b)} ; index prefix, truncated at end of data')]
            if nb == 0xCB:
                self.pos += 1
                text = self.decode_cb(index)
                return [Instr(start, self.pos - start, self._bytes(start), text)]
            if nb in (0xDD, 0xFD, 0xED):
                return [Instr(start, 1, self._bytes(start),
                              f'DEFB {hx8(b)} ; index prefix ignored (stacked prefix follows)')]
            opcode_start = self.pos
            used, text, target = self.decode_main(index)
            if not used:
                prefix = Instr(start, 1, self._bytes2(start, opcode_start),
                                f'DEFB {hx8(b)} ; index prefix ignored (opcode does not reference HL/(HL))')
                instr = Instr(opcode_start, self.pos - opcode_start,
                              self._bytes2(opcode_start, self.pos), text, target)
                return [prefix, instr]
            return [Instr(start, self.pos - start, self._bytes(start), text, target)]
        self.pos = start
        used, text, target = self.decode_main(None)
        return [Instr(start, self.pos - start, self._bytes(start), text, target)]

    def _off_at(self, addr):
        return addr - self.org

    def _bytes(self, start):
        return self.data[start - self.org:self.pos - self.org]

    def _bytes2(self, start, end):
        return self.data[start - self.org:end - self.org]


def disassemble(data, org, start=None, length=None):
    start_addr = org + (start or 0)
    if length is None:
        end_addr = org + len(data)
    else:
        end_addr = start_addr + length
    dec = Decoder(data, org)
    dec.pos = start_addr
    instructions = []
    while dec.pos < end_addr:
        instr_start = dec.pos
        try:
            decoded = dec.decode()
        except Truncated:
            remaining = data[instr_start - org:end_addr - org]
            hexbytes = ','.join(hx8(v) for v in remaining)
            instructions.append(Instr(instr_start, len(remaining), remaining,
                                       f'DEFB {hexbytes} ; truncated instruction at end of data'))
            break
        instructions.extend(decoded)
    return instructions


def format_listing(instructions, org, filename, labels=True):
    targets = set()
    if labels:
        addrs = {i.addr for i in instructions}
        for instr in instructions:
            if instr.target is not None and instr.target in addrs:
                targets.add(instr.target)

    lines = [
        f'; disassembled by z80_disasm.py from {filename}',
        f'; org #{org:04X}, {len(instructions)} instructions',
        '',
        f'    ORG #{org:04X}',
        '',
    ]
    for instr in instructions:
        if instr.addr in targets:
            lines.append(f'L{instr.addr:04X}:')
        hexbytes = ' '.join(f'{v:02X}' for v in instr.raw)
        text = instr.text
        if labels and instr.target in targets:
            text = text.replace(hx16(instr.target), f'L{instr.target:04X}')
        lines.append(f'    {text:<28} ; {instr.addr:04X}: {hexbytes}')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(
        description='Disassemble raw Z80 machine code into sjasmplus-compatible assembly.')
    parser.add_argument('input', help='raw binary file to disassemble')
    parser.add_argument('--org', type=lambda s: int(s, 0), default=0,
                         help='address of the first byte in the file (default 0)')
    parser.add_argument('--start', type=lambda s: int(s, 0), default=0,
                         help='byte offset into the file to start disassembling (default 0)')
    parser.add_argument('--length', type=lambda s: int(s, 0), default=None,
                         help='number of bytes to disassemble (default: rest of file)')
    parser.add_argument('--out', help='output .asm file (default: stdout)')
    parser.add_argument('--no-labels', action='store_true',
                         help='do not auto-generate L#### labels for in-range jump/call targets')
    args = parser.parse_args()

    with open(args.input, 'rb') as f:
        data = f.read()

    instructions = disassemble(data, args.org, args.start, args.length)
    listing = format_listing(instructions, args.org + args.start, args.input,
                              labels=not args.no_labels)

    if args.out:
        with open(args.out, 'w') as f:
            f.write(listing)
        print(f'{len(instructions)} instructions -> {args.out}', file=sys.stderr)
    else:
        sys.stdout.write(listing)


if __name__ == '__main__':
    main()
