#!/usr/bin/env python3
"""emc_disasm.py - the scripts that are Dune II's behaviour.

    emc_disasm.py [--rom orig/dune2.gen] [--out orig/sega/res/data]

`BUILD.EMC`, `UNIT.EMC`, `TEAM.EMC` and `PLAYER.EMC` are Westwood's own
script bytecode, and they are where this game's behaviour actually lives -
not in the 68000.  This writes them out as readable listings under
`res/data/scripts/`, with every entry point named.

## The container

An IFF file: `FORM <len> EMC2`, then `ORDR` and `DATA`.

  * `ORDR` is a list of 16-bit **word offsets into DATA** - the entry
    points.
  * `DATA` is the bytecode.

## The instruction

One 16-bit word, big-endian.  The high byte is three flag bits and a
five-bit opcode; the flags say where the parameter comes from:

    bit 15 set   opcode is 0, parameter is the low 15 bits
    bit 14 set   parameter is the low byte, signed
    bit 13 set   parameter is the whole of the next word
    otherwise    parameter is the low byte, unsigned

Two things prove this reading rather than assume it: **every one of the 61
entry points in the four files lands exactly on an instruction boundary**,
and so does every parameter of opcodes 0 and 15 - 336 of them, none
off by a word.  Decoding it any other way does not do that.

## The opcodes

All nineteen, and not from anyone's general knowledge of Westwood's VM -
**the interpreter is in the cartridge** and it is a 32-way switch at
`$016F40` with one handler each.  Reading them settles what the VM is: a
stack machine with fifteen words of stack at `+$16`, a frame pointer at
`+$A`, a stack pointer at `+$B` counting *down* from 15, a return-value
register at `+8` and the script's own variables at `+$C`.

    op  handler   what it does
     0  $016F8E   goto      pc = base + par*2
     1  $016FA2   setret    return value = par (and nothing else)
     2  $016FAE   push      the return value (par 0) or the pc (par 1)
     3  $017036   push.w    par, which is the next whole word
     4  $017036   push.b    par, a signed byte - the same handler
     5  $017050   push      variable par, from +$C
     6  $017070   push      local par: stack[fp - par - 2], below the
                            frame (the stack grows down)
     7  $01709E   push      parameter par: stack[fp + par - 1], above
                            the frame, where the caller pushed it
     8  $0170C6   pop/ret   par 0 pops the return value; par 1 is the
                            return proper - it pops the frame and the
                            saved pc and jumps back
     9  $017142   pop       into variable par
    10  $01715E   pop       into local par
    11  $01718E   pop       into parameter par
    12  $0171B4   drop      par words off the stack
    13  $0171C0   reserve   par words on the stack
    14  $0171CC   call      routine par of this script's function table
    15  $0171F0   goto-if   pops; jumps to par & $7FFF if it was zero
    16  $01721E   unary     ! - ~ on the top of the stack
    17  $017270   binary    a second 18-way switch at $0172A0: && || ==
                            != < <= > >= + - * / >> << & | % ^
    18  $0173A0   return    on an empty stack (sp = 15) stops the script;
                            otherwise pops the return value into +8
                            and then the pc, and clears +$34 (in a
                            subroutine)

Opcodes 19-31 all land on the same two instructions - store zero into the
pc, which stops the script - so nineteen is the whole instruction set.

## What the entry tables turn out to index

`BUILD.EMC` has **19** entry points and the game has **19 buildings**.
`UNIT.EMC` has **27** and there are **27 units**.  All distinct, all
non-zero, and the sizes settle it beyond coincidence: the four kinds of
infantry get 19 words each, the two turrets 45 each, Barracks and WOR 17
each, and the five tanks 3 words each - they share the default and have
nothing of their own to say.  The listings are labelled accordingly.
"""

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SCRIPTS = ["BUILD.EMC", "UNIT.EMC", "TEAM.EMC", "PLAYER.EMC"]

# Where each script's `call` goes.  The loader at $016C0E hands the script
# reader a name and one of these tables; the counts settle which is which,
# since a script never calls past the end of its own table - UNIT reaches
# index 62 and has 64 entries, TEAM reaches 13 and has 15, BUILD reaches 23
# and has 25.  PLAYER.EMC is not loaded by that code and its table has not
# been found, so its calls are left as bare numbers.
FUNC_TABLE = {
    "UNIT.EMC": (0x0FED20, 64),
    "TEAM.EMC": (0x0FECE4, 15),
    "BUILD.EMC": (0x06B998, 25),
}
# The interpreter's own switch at $016F40, one name per handler.
# ---------------------------------------------------------------- routines
#
# What a `call` reaches, read one routine at a time in orig/sega/src/.
# Keyed by address, because the same routine appears at different indices
# in different tables - $01108A is UNIT 16, TEAM 0 and BUILD 0.
#
# The three scripts each work on a different "current thing", which is
# what makes the same shape of code mean different things:
#
#     $FFDEA0  the unit a UNIT.EMC script is running for
#     $FFDE9C    and its record in the unit table at $06BC00
#     $FFD5AC  the structure a BUILD.EMC script is running for
#     $FFDCA8  the team a TEAM.EMC script is running for
#     $FFC208  whichever of those it is - used by the shared $011xxx set
#
# A script passes things around as a **tagged reference**: a word whose
# top two bits are the kind and whose low 14 bits are the value.  The
# $02Exxx module is what reads them - kind 0 is nothing, 1 a unit
# ($02E38C fetches it, through $043656 and the 102 unit records the
# pointers at $04A852 name), 2 a structure ($02E1D0, through $00BAFE and
# the 73 at $04A716), 3 a square of the map.  $02E17C builds one, and its
# own switch says the same: kind 1 goes through $043656 and tests bit 1
# of the unit's $4, kind 2 just sets bit 15.  (The bounds say which is
# which too: $043656 stops at $66 = 102, $00BAFE at $49 = 73.)  $02E2FA says whether a reference is still good,
# $02E256 gives its world position and $02E1F6 its map square.
#
# Two records the routines keep coming back to, read off how they are
# used rather than guessed:
#
#     unit      $3 the unit it carries (linked; $FF none), $5C where it
#               is going, $5E the spice it holds (a Harvester is full at
#               100), $73 the frame of its own animation, $2A (variable
#               4 of its script) a claim on another thing - $023CCC sets
#               it both ways, $023E04 breaks it
#     structure $5C its state - 0 idle, 2 a unit ready to come out; set
#               through $00FA0E - and $2A the same claim
#
# A name here means the routine was read.  A blank name means it was read
# and not settled, which is a different thing from not looked at, and the
# note says as much as could be said.
ROUTINE = {
    # -- the shared set: these work through $FFC208 and appear in more
    #    than one table
    0x01108A: ("delay", "wait n/5 ticks - writes the countdown the tick "
                        "loop at $043BCC decrements"),
    0x0110A6: ("delay.rnd", "the same, but a random fraction of n"),
    0x0110D8: ("random", "a random number between the two arguments"),
    0x01110C: ("distance", "how far the reference is from me, or -1"),
    0x011152: ("distance.to", "the same, but to the near edge of a "
                              "structure rather than its middle "
                              "($02E0A8), or -1"),
    0x01118A: ("not.unit?", "1 unless the reference names a unit - a "
                            "structure, a place or nothing all answer 1"),
    0x0111E6: ("facing.of", "the hull facing ($6A) of the unit the "
                            "reference names, or $80 if it names no unit"),
    0x011212: ("count", "how many units of type n my house has "
                        "(the unit pool, through $04321C)"),
    0x011260: ("", "the reference's value - a packed square for a place, "
                   "the index otherwise ($02E3B2), or -1; never called"),
    0x011292: ("kind", "the reference's kind: 1 unit, 2 structure, "
                       "3 a place; -1 if it is stale"),
    0x0112C4: ("linked.type", "the type of the unit I am carrying ($3), "
                              "or -1"),
    0x0112EE: ("", "returns 0 and nothing else"),
    0x0112F2: ("find.spice", "the nearest square of spice (ground type 8 "
                             "or 9) within $20 of me, from $01A146, as a "
                             "place - or 0, and remember there was none; "
                             "the argument is not read"),
    0x011358: ("friend?", "the reference is an active thing of my own house"),
    0x0113AC: ("enemy?", "the reference belongs to another house"),
    0x01143E: ("", "a structure of my house that is idle: the one the "
                   "reference names, or the first of type n; never called"),
    0x011014: ("", "print string n of the script's own text with three "
                   "more arguments, into $FFC5B0; never called"),
    0x011106: ("", "returns 0 and nothing else"),

    # -- UNIT.EMC
    0x04500C: ("get", "twenty properties of the unit and its type - see "
                      "PROPERTY below"),
    0x044F2E: ("act", "give the unit action n, through $0436A0"),
    0x045808: ("explode", "the death animation and the sound that goes "
                          "with it"),
    0x044D7E: ("go.to", "set where the unit is headed ($5C); a Harvester "
                        "gets a spice field rather than a thing"),
    0x044D2E: ("dir.to", "which way the reference is, or my own facing "
                         "if it is stale"),
    0x044C44: ("turn", "turn towards n and answer the facing reached"),
    0x0447E2: ("fire", "shoot at $5A, if the gun is lined up on it"),
    0x045E2C: ("deploy", "an MCV becomes a Construction Yard: $00E580 "
                         "makes structure 8 on my square or one of the "
                         "three up and left of it ($0FEE20), and the "
                         "unit is removed; 0 if none fits"),
    0x044F78: ("act.default", "give the unit the action its type names "
                              "at +$28"),
    0x045F82: ("", "returns 0 and nothing else"),
    0x0452C2: ("step", "one step of the way towards $5C"),
    0x0446C4: ("", "returns 0 and nothing else - called with 4, 6 or 9 "
                   "as a unit dies"),
    0x0445EE: ("die", "the unit is destroyed: the score moves, a Saboteur "
                      "takes 500 points of everything with it"),
    0x0446C8: ("explode.big", "the blast of Destruct and of a dying "
                              "Devastator: explosion 11 where I stand and "
                              "seven of type 6 round it ($00A934); the "
                              "argument is not read"),
    0x0443F8: ("frame", "show frame n of the unit's own animation: $73 = "
                        "-n, and ask for a redraw"),
    0x043D80: ("deliver", "put down the unit I am carrying at $5C - into "
                          "a structure (a Starport takes the whole load) "
                          "or on the ground where I am"),
    0x043CEC: ("", "returns 0 and nothing else"),
    0x04442A: ("fly.to", "fly straight at $5C (a Refinery's or a "
                         "Starport's pad), sliding the last $80; answers 1 "
                         "on arrival and until then waits and runs the "
                         "call again"),
    0x044F92: ("head.for", "point the hull at the reference, keeping it "
                           "in $4E as where I am going"),
    0x044358: ("stop", "speed 0, and ask for a redraw"),
    0x044380: ("speed", "set the speed, clamped to 0-255 and cut to "
                        "three quarters if $4 bit 9 is set"),
    0x043D60: ("find.target", "the best thing for me to attack, as a "
                              "reference: the best unit ($04730C) and "
                              "structure ($01072C) weighed against each "
                              "other; n=4 takes a structure first, and a "
                              "Deviator never looks at structures"),
    0x043CF0: ("", "how much I want to attack the reference - $047166 "
                   "for a unit, $010688 for a structure; never called"),
    0x0456B8: ("seek.dock", "an idle structure of type n to go to - the "
                            "one the unit I carry came from ($52) if it "
                            "is free, else the first of my house - "
                            "claimed and put in $5C, as a reference"),
    0x0457EE: ("", "bit 8 of the unit's flags; never called"),
    0x0457C2: ("amount", "the spice ($5E) in the unit I am carrying, or "
                         "in me if I carry nothing"),
    0x04587C: ("survivor", "with the chance at +$E of my type (64 in 256, "
                           "a Harvester 128) a Soldier of my house is "
                           "made near me and given order n"),
    0x043FE0: ("pick.up", "take on board the unit $5C names, or the one "
                          "waiting in the structure it names, and choose "
                          "where to carry it"),
    0x045912: ("call.unit", "a free unit of type n of my house is claimed "
                            "and sent for me ($5C = me) - the one I have "
                            "already, or 0 if my type cannot be carried"),
    0x0459D8: ("dismiss", "if what I have claimed is a Carryall, clear "
                          "its $5C and let it go"),
    0x045A16: ("find.struct", "a structure of my house and of type n that "
                              "is idle, empty and unclaimed, as a reference"),
    0x045A88: ("", "a bare rts"),
    0x045A8A: ("unfog", "clear the fog round me, as far as +$12 of my "
                        "type says ($019FFE) - only the player's own"),
    0x045A9C: ("harvest", "a Harvester on spice with room ($5E < 100) "
                          "takes a little more; answers 1 while it "
                          "should keep at it, and now and then the "
                          "square loses its spice ($01A518)"),
    0x045B6A: ("blocked?", "1 when what I carry cannot be set down at "
                           "the reference ($046F68 refuses the square, or "
                           "the structure is not ours or will not take "
                           "it), 0 when it can - once read the other way "
                           "round, as 'clear?'"),
    0x045C48: ("nearby", "a random square close to me ($011688, $50), as "
                         "a place - only if the argument is a place, "
                         "else 0"),
    0x045CD8: ("fidget", "a foot unit shuffles on the spot"),
    0x045D6E: ("go.nearest", "order Move to the nearest idle, empty, "
                             "unclaimed structure of my house of type n; "
                             "1 if there is one"),
    0x045EC6: ("find.prey", "the unit the Sandworm most wants: every unit "
                            "scored by $04754E, the best as a reference"),
    0x045EF2: ("claim.ok?", "1 if what I have claimed still claims me and "
                            "is of my house; otherwise break the claim, "
                            "clear a unit's $5C, and answer 0"),
    0x044E04: ("aim", "set what the unit is shooting at ($5A), and turn "
                      "the hull too if it has no turret"),
    0x044C78: ("turning?", "turn the gun towards $5A; answer whether it "
                           "still has further to go"),

    # -- BUILD.EMC
    0x00C64E: ("", "returns 0 and nothing else"),
    0x00C652: ("state", "the structure's state ($5C)"),
    0x00C65E: ("check.link", "make sure the docked unit still points back "
                             "here, and break the link if it does not"),
    0x00C6C0: ("send.for", "when a unit is ready ($5C = 2), claim a free "
                           "unit of type n through $04875A - the Carryall - "
                           "to come and take it; it does not put the unit "
                           "on the map itself (the PC game's "
                           "FindUnitByType).  Once read as 'produce'"),
    0x00C7CC: ("set.state", "set the structure's state ($5C, through "
                            "$00FA0E); $FFFE means work it out from "
                            "whether anything is docked"),
    0x00CD6E: ("unclaim", "if the reference is a unit, break its claim "
                          "and clear its $5C"),
    0x00C818: ("release", "send the docked unit back out"),
    0x00CA0C: ("find.target", "the unit a turret should shoot, within n "
                              "(three times n for a flyer): its current "
                              "$26 if still in reach, else the nearest "
                              "one my house has seen, as a reference"),
    0x00CB92: ("aim", "turn the turret towards the reference"),
    0x00CD06: ("", "which way the reference is, in eighths, or $4E; "
                   "never called"),
    0x00CDD0: ("fire", "shoot at $26"),
    0x00CFE2: ("", "sound n ($00A7D8), if the building is the player's; "
                   "never called"),
    0x00D012: ("unfog", "clear the fog round the building, as far as +$12 "
                        "of its type says - only the player's own"),
    0x00D068: ("refine", "take a load of spice out of the docked "
                         "Harvester ($5E) and pay 7 credits a unit, up to "
                         "the house's storage; state 2 when it is empty"),
    0x00D1EA: ("explode", "explosions over every square of the building, "
                          "and a Starport's cargo is lost"),
    0x00D4C8: ("destroy", "the building goes ($00F71A), and each square "
                          "may leave a Soldier behind, by the chance at "
                          "+$E of its type"),

    # -- TEAM.EMC
    0x02E500: ("", "returns 0 and nothing else"),
    0x02E504: ("", "compares the team's house with the player's and then "
                   "throws the answer away; never called"),
    0x02E520: ("members", "how many units the team has ($4)"),
    0x02E52C: ("min", "the fewest members the team may have ($6; "
                      "recruit fills it up to $8)"),
    0x02E538: ("target", "the team's $1A"),
    0x02E544: ("recruit", "take the nearest suitable unit of the house "
                          "into the team, if it is under strength"),
    0x02E67C: ("spread", "the members' average distance from their "
                         "centre, which is put in $14 on the way"),
    0x02E7C0: ("gather", "members further than n from the centre are "
                         "ordered to Move near it, the rest to Guard; "
                         "answers how many were moved"),
    0x02E906: ("find.target", "look for something to attack and put it in "
                              "$1A"),
    0x02E9C4: ("attack", "send every member at $1A, spread out around it"),
    0x02EB66: ("behave", "restart the team's own script at entry n"),
    0x02EBB2: ("behave.orig", "restart it at the entry it was declared "
                              "with ($E)"),
}

# The twenty properties of $04500C, from its own switch at $04503E.
PROPERTY = [
    "health%",          #  0  $12 as a percentage of the type's $10
    "target",           #  1  $5C, or 0 if it is stale
    "type.$52<<8",      #  2
    "id",               #  3  the unit's own index
    "facing",           #  4  $6A
    "$5A",              #  5
    "$52",              #  6  worked out first if it is not set
    "type",             #  7  $2
    "self",             #  8  $02E17C(id,1) - a reference to me as a unit
    "$71",              #  9
    "turn.left",        # 10  |$69 - $6A|, how far the hull still has to turn
    "$4E?",             # 11
    "$56==0",           # 12
    "type.$38&4",       # 13
    "house",            # 14  $8
    "flag9",            # 15  bit 9 of $4
    "gun.facing",       # 16  $6D if it has a turret, else $6A
    "gun.turn.left",    # 17  the same difference, for the turret
    "has.turret",       # 18  bit 6 of the type's $C
    "seen",             # 19  bit for the player's house in $9
]


# 6 and 10 address the stack below the frame pointer (fp - par - 2), the
# locals; 7 and 11 above it (fp + par - 1), the parameters the caller
# pushed ($017070, $01709E, $01715E, $01718E).  1 only sets the return
# value; 18 returns - it stops the script only when the stack is empty.
NAMED = {0: "goto", 1: "setret", 2: "push", 3: "push.w", 4: "push.b",
         5: "push.var", 6: "push.loc", 7: "push.arg", 8: "pop",
         9: "pop.var", 10: "pop.loc", 11: "pop.arg", 12: "drop",
         13: "reserve", 14: "call", 15: "goto-if", 16: "unary",
         17: "binary", 18: "return"}
# What opcode 2 and opcode 8 do with their parameter, from $016FAE and
# $0170C6 - and the two operator tables, from $01721E and $0172A0.
PUSH_WHAT = {0: "the return value", 1: "the script position"}
POP_WHAT = {0: "the return value", 1: "and return"}
UNARY = ["!", "-", "~"]
BINARY = ["&&", "||", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*",
          "/", ">>", "<<", "&", "|", "%", "^"]


def chunks(d):
    """FORM/EMC2 and the chunks inside it.  Stops at the first tag that is
    not four letters, because the file is padded to the next one."""
    if d[:4] != b"FORM" or d[8:12] != b"EMC2":
        raise ValueError("not an EMC2 script")
    out, i = {}, 12
    while i + 8 <= len(d):
        tag = d[i:i + 4]
        if not tag.isalpha():
            break
        n = struct.unpack(">I", d[i + 4:i + 8])[0]
        out[tag.decode()] = d[i + 8:i + 8 + n]
        i += 8 + n + (n & 1)
    return out


def decode(data):
    """word offset -> (opcode, parameter, words, raw)."""
    out, i = {}, 0
    while i + 2 <= len(data):
        cur = struct.unpack(">H", data[i:i + 2])[0]
        op, size = (cur >> 8) & 0x1F, 1
        if cur & 0x8000:
            op, par = 0, cur & 0x7FFF
        elif cur & 0x4000:
            par = cur & 0xFF
            if par > 127:
                par -= 256
        elif cur & 0x2000:
            if i + 4 > len(data):
                break
            par = struct.unpack(">H", data[i + 2:i + 4])[0]
            size = 2
        else:
            par = cur & 0xFF
        out[i // 2] = (op, par, size, cur)
        i += size * 2
    return out


def entries(chunk):
    return [struct.unpack(">H", chunk[k:k + 2])[0]
            for k in range(0, len(chunk), 2)]


def names_from(path, count, least=3):
    """The building or unit names, in table order, out of the text
    sega_data.py wrote - so the two never drift apart."""
    if not path.exists():
        return None
    got = []
    for line in path.read_text().splitlines():
        p = line.split()
        if len(p) > least and p[0].isdigit() and int(p[0]) == len(got):
            # the name runs to the first column that is a number
            k = 1
            while k < len(p) and not p[k].lstrip("-").isdigit():
                k += 1
            got.append(" ".join(p[1:k]))
    return got[:count] if len(got) >= count else None


def mnemonic(op):
    return NAMED.get(op, f"op{op}")


def func_targets(rom, name):
    """index -> the 68000 routine a `call` of that index reaches."""
    if name not in FUNC_TABLE:
        return {}
    a, n = FUNC_TABLE[name]
    return {k: int.from_bytes(rom[a + k * 4:a + k * 4 + 4], "big")
            for k in range(n)}


def listing(name, data, ordr, labels, ins, funcs, actions=()):
    out = [f"; {name} - {len(ins)} instructions, "
           f"{len(data) // 2} words, {len(ordr)} entry points.",
           ";",
           "; Written by tools/sega/emc_disasm.py.  One line an instruction:",
           "; the word offset into DATA, the raw word, then the opcode and",
           "; its parameter.  All nineteen opcodes are named, out of the",
           "; interpreter's own switch at $016F40 - see the tool's header",
           "; for the handler each one is.",
           ";",
           "; In a UNIT.EMC script **variable 0 is the order the unit is",
           "; under**, which is why every unit's routine begins by comparing",
           "; it against 1, 3, 5, 6, 7 and branching.  That is not a",
           "; reading of the pattern: the script object lives at unit+$16",
           "; and its variables at +$C, so variable 0 is unit+$22 - and",
           "; $043766, inside the routine that gives a unit an order,",
           "; is `move.w d3,$22(a2)` with d3 the order.  See",
           "; res/data/actions.txt for the fourteen of them.",
           ";",
           "; A `call` names what it reaches, out of this script's own",
           "; function table.  Where the routine has been read it is named",
           "; and res/data/functions.txt says what it does; where it has",
           "; not, the bare address is printed instead.  A `get` whose",
           "; property number is a literal is resolved on the spot.",
           ""]
    order = sorted(ins)
    for k, off in enumerate(order):
        op, par, size, cur = ins[off]
        if off in labels:
            out.append("")
            out.append(f"{labels[off]}:")
        raw = f"{cur:04X}"
        if size == 2:
            raw += " %04X" % (par & 0xFFFF)
        body = mnemonic(op)
        if op in (0, 15):
            t = par & 0x7FFF
            body += f"    {labels.get(t, f'w{t}')}"
        elif op == 2:
            body += f"    {PUSH_WHAT.get(par, par)}"
        elif op == 8:
            body += f"    {POP_WHAT.get(par, par)}"
        elif op == 14 and par in funcs:
            at = funcs[par]
            name = ROUTINE.get(at, ("", ""))[0]
            note = f"L_{at:06X}" if not name else name
            # $04500C takes a property number, and where the script pushes
            # a literal right before the call the listing can say which
            prev = ins[order[k - 1]] if k else None
            if at == 0x04500C and prev and prev[0] in (3, 4) \
                    and 0 <= prev[1] < len(PROPERTY):
                note += f" {PROPERTY[prev[1]]}"
            # and $044F2E takes one of the fourteen orders
            if at == 0x044F2E and prev and prev[0] in (3, 4) \
                    and 0 <= prev[1] < len(actions):
                note += f" {actions[prev[1]]}"
            body += f"    {par:<4}; {note}"
        elif op == 16 and 0 <= par < len(UNARY):
            body += f"    {UNARY[par]}"
        elif op == 17 and 0 <= (par & 0x1F) < len(BINARY):
            body += f"    {BINARY[par & 0x1F]}"
        elif op == 18:
            body = mnemonic(op)
        else:
            body += f"    {par}"
        out.append(f"{off:5d}  {raw:<9}  {body}")
    out.append("")
    return "\n".join(out)


def routine(rom, at, limit=400):
    """Follow a script function from its entry to its RTS.

    Linear, not a full trace: these are leaf-ish routines and what is
    wanted is a description, not a control-flow graph.  Stops at the first
    RTS/RTE/JMP that is not jumped over.
    """
    import m68k
    out, pc, end = [], at, at
    while pc < len(rom) and pc - at < limit * 8:
        try:
            ins = m68k.decode(rom, pc, 0)
        except m68k.Fail:
            break
        out.append(ins)
        pc += ins.length
        if ins.mnem in ("rts", "rte", "rtr"):
            end = pc
            break
        if ins.flow == "jump" and ins.target is not None and \
                not at <= ins.target < pc:
            end = pc
            break
    return out, end - at


def describe(rom, ins_list, calls):
    """What a routine touches: work RAM, hardware, and who it calls."""
    ram, hw, sub = set(), set(), set()
    for ins in ins_list:
        for e in ins.ops:
            a = None
            if e.kind in ("absl", "absw"):
                a = e.addr & 0xFFFFFF
            if a is None:
                continue
            if 0xFF0000 <= a <= 0xFFFFFF:
                ram.add(a)
            elif 0xA00000 <= a < 0xE00000:
                hw.add(a)
        if ins.mnem in ("jsr", "bsr.w", "bsr.s") and ins.target is not None:
            sub.add(ins.target)
    return ram, hw, sub


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "orig/sega/res/data"))
    args = ap.parse_args()

    out = Path(args.out)
    src = out / "files"
    (out / "scripts").mkdir(parents=True, exist_ok=True)

    rom = (ROOT / "orig/dune2.gen").read_bytes()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    buildings = names_from(out / "buildings.txt", 19)
    units = names_from(out / "units.txt", 27)
    actions = names_from(out / "actions.txt", 14, least=2) or []

    index = [
        "# scripts.txt - the four script files that are Dune II's behaviour.",
        "#",
        "# Written by tools/sega/emc_disasm.py.  BUILD.EMC has one entry",
        "# point for each of the 19 buildings and UNIT.EMC one for each of",
        "# the 27 units - the counts match exactly, all distinct, and the",
        "# sizes confirm it: the four kinds of infantry get 19 words each,",
        "# the two turrets 45 each, the five tanks 3 each.",
        "#",
        "# A routine's size is the distance to whichever entry point comes",
        "# next in the file, so it is what the script really occupies.",
        "",
    ]
    for fname in SCRIPTS:
        p = src / (fname + ".bin")
        if not p.exists():
            raise SystemExit(f"{p} is missing - run sega_files.py first")
        c = chunks(p.read_bytes())
        data = c["DATA"]
        ins = decode(data)
        ordr = entries(c["ORDR"])

        who = {"BUILD.EMC": buildings, "UNIT.EMC": units}.get(fname)
        labels = {}
        for i, e in enumerate(ordr):
            if who and i < len(who):
                labels[e] = f"{fname.split('.')[0].lower()}_" \
                            f"{who[i].lower().replace(' ', '_').replace('-', '_')}"
            else:
                labels.setdefault(e, f"entry{i}")
        for off, (op, par, size, cur) in ins.items():
            if op in (0, 15):
                labels.setdefault(par & 0x7FFF, f"w{par & 0x7FFF}")

        funcs = func_targets(rom, fname)
        (out / "scripts" / (fname.split(".")[0].lower() + ".txt")).write_text(
            listing(fname, data, ordr, labels, ins, funcs, actions))

        stops = sorted(set(ordr) | {len(data) // 2})
        ft = FUNC_TABLE.get(fname)
        index.append(f"== {fname}   {len(data) // 2} words, "
                     f"{len(ins)} instructions, {len(ordr)} entry points"
                     + (f", {ft[1]} callable routines at ${ft[0]:06X}"
                        if ft else ", function table not found"))
        for i, e in enumerate(ordr):
            nxt = next((s for s in stops if s > e), len(data) // 2)
            label = who[i] if who and i < len(who) else f"entry {i}"
            index.append(f"   {i:2d}  {label:<16} word {e:5d}  "
                         f"{nxt - e:4d} words")
        index.append("")

    index += [
        "# What the sizes say",
        "#",
        "# In UNIT.EMC the Tank, Siege Tank, Launcher, Deviator and Sonic",
        "# Tank get three words each: they have no behaviour of their own",
        "# and fall straight through to the default.  What is long is what",
        "# has a job - the Carryall (262 words), the Sandworm (168), the",
        "# Frigate (140), the Harvester (124) and the MCV (118).  Nearly",
        "# half of UNIT.EMC is spent on five units that move about without",
        "# being told to.",
        "#",
        "# In BUILD.EMC the Starport is the longest at 51 words - it is the",
        "# only building that talks to something off the map - then the",
        "# Refinery at 40 and the Repair Facility at 36.  A slab of concrete",
        "# gets nine.",
    ]
    (out / "scripts.txt").write_text("\n".join(index) + "\n")

    # ---- what the scripts can call, cross-referenced into the 68000
    rows = []
    for fname, (tbl, count) in FUNC_TABLE.items():
        p = src / (fname + ".bin")
        c = chunks(p.read_bytes())
        ins = decode(c["DATA"])
        used, arity, valued = {}, {}, {}
        order = sorted(ins)
        for k, off in enumerate(order):
            op, par, size, cur = ins[off]
            if op != 14:
                continue
            used[par] = used.get(par, 0) + 1
            # The calling convention is right there in the listing: the
            # arguments are pushed, the call is made, and the caller drops
            # them again.  So `drop n` after a call is the routine's arity,
            # and a `push the return value` in between says the answer was
            # wanted - which is what separates a question from an order.
            j, n = k + 1, 0
            if j < len(order) and ins[order[j]][0] == 12:    # drop the args
                n = ins[order[j]][1]
                j += 1
            if j < len(order) and ins[order[j]][:2] == (2, 0):
                valued[par] = valued.get(par, 0) + 1         # answer wanted
            arity.setdefault(par, set()).add(n)
        addrs = sorted({int.from_bytes(rom[tbl + i * 4:tbl + i * 4 + 4], "big")
                        for i in range(count)})
        rows.append((fname, tbl, count, used, addrs, arity, valued))

    lines = [
        "# functions.txt - what a script's `call` reaches, in the 68000.",
        "#",
        "# Written by tools/sega/emc_disasm.py.  Each script is handed its",
        "# own table of routines by the loader at $016C0E; a `call n` in the",
        "# bytecode is a jsr to entry n of that table.",
        "#",
        "# 'args' and 'answer' come from the calling convention, which the",
        "# interpreter at $016F40 spells out.  A call site reads",
        "#",
        "#     push.b  4          the argument",
        "#     call    0",
        "#     drop    1          the caller takes its arguments back",
        "#     push    the return value      - only if it wants the answer",
        "#",
        "# so the n in that `drop` is the routine's arity, and the `push`",
        "# after it says the answer was wanted.  That is what tells a",
        "# question from an order, and it is a fact about the bytecode",
        "# rather than a guess.  The two have to be read in that order: the",
        "# drop comes first, and looking for the push first says almost",
        "# everything is an order, which is wrong.",
        "# 'args' shows every arity a routine is called with - more than",
        "# one means the scripts disagree, which is worth looking at.",
        "#",
        "# 'what' is the routine read in orig/sega/src/.  A blank one was",
        "# read and not settled, which is not the same as not looked at.",
        "#",
        "# idx  routine  bytes  calls args answer  what",
        "",
    ]
    orders = questions = 0
    for fname, tbl, count, used, _, arity, valued in rows:
        lines.append(f"== {fname}   table ${tbl:06X}, {count} entries")
        for i in range(count):
            a = int.from_bytes(rom[tbl + i * 4:tbl + i * 4 + 4], "big")
            body, size = routine(rom, a)
            ram, hw, sub = describe(rom, body, used)
            n = used.get(i, 0)
            args = ("/".join(str(k) for k in sorted(arity[i]))
                    if i in arity else "-")
            if n:
                ans = f"{valued.get(i, 0)}/{n}"
                questions += bool(valued.get(i))
                orders += not valued.get(i)
            else:
                ans = "-"
            name, what = ROUTINE.get(a, ("", ""))
            lines.append(
                f"{i:4d}  ${a:06X} {size:6d} {n:5d} {args:<4} {ans:<7} "
                f"{name:<12} {what}".rstrip())
        lines.append("")
    lines += ["# The twenty properties `get` answers, from its own switch",
              "# at $04503E:", ""]
    for i, w in enumerate(PROPERTY):
        lines.append(f"  {i:2d}  {w}")
    lines += [
        "",
        f"# {questions} of the {questions + orders} routines the scripts",
        "# actually call have their answer read somewhere; the other",
        f"# {orders} are called only for what they do.  That split is what",
        "# the calling convention gives, and it is the half of the problem",
        "# that can be settled from the bytecode alone.  What each one",
        "# *means* still needs the routine read in orig/sega/src/ - but",
        "# with its arity, whether it answers, and how often it is called,",
        "# there is a lot less guessing left in that.",
    ]
    (out / "functions.txt").write_text("\n".join(lines) + "\n")
    print(f"4 scripts -> {out}/scripts/ and {out}/scripts.txt")
    print(f"{sum(r[2] for r in rows)} callable routines "
          f"-> {out}/functions.txt")


if __name__ == "__main__":
    main()
