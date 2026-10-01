# How the Mega Drive Dune II works inside

What `orig/sega/` has turned up about the game itself: what a unit is, what
a base is, how a mission is described, and where the computer player's
behaviour actually lives.  Everything here is read out of the cartridge by
`tools/sega/` and written into `orig/sega/res/data/`; where something is a
guess it says so.

## The shape of the thing: Dune II is a data file, not a program

The single most useful fact about this ROM is that **the game is barely in
the code**.  Westwood's 1992 PC Dune II was driven by a set of data files,
and the Mega Drive port carries those files whole, behind a small directory
of names at `$052C2C` and two routines (`$0046AE`, `$004A3A`) that look a
name up in it:

| file | what it decides |
|---|---|
| `PROFILE.INI` | what everything costs, how long it takes, how hard it hits |
| `HOUSE.INI` | what makes a house behave like itself |
| `REGION.INI`, `REGIONA/H/O.INI` | the campaign map and its narration |
| `SCENA001-009`, `SCENH…`, `SCENO…` | the 27 missions |
| `BUILD.EMC`, `TEAM.EMC`, `UNIT.EMC` | **the behaviour**, as script bytecode - now readable, see below |
| `PLAYER.EMC` | the same, but this port never loads it |

Six of those are still plain text inside the ROM and are written out as
themselves by `tools/sega/sega_files.py`.  So the 68000 code in
`orig/sega/src/` is an *engine*: it draws, it moves things, it runs a
script interpreter.  What the game is, is in the files.

With one large caveat, established below: **the port only ever opens the 27
missions and three of the four scripts.**  `PROFILE.INI`, `HOUSE.INI`, the
`REGION*.INI` and `PLAYER.EMC` are in the cartridge and are never read.
The numbers the game plays by are the binary tables instead.

Beside them sit three binary tables the code indexes directly - buildings
at `$06AFA6`, units at `$06BC00`, houses at `$06C750` - and these do not
always agree with the INI text.  See "the two sets of numbers" below.

## The houses

Six exist; three can be played.  Everything in this table is settled - the
values are Dune II's own and `prefix` really does hold a letter
(`res/data/houses.txt`):

| house | toughness | decay | chance | countdown | special | mentat |
|---|---|---|---|---|---|---|
| Harkonnen | 200 | 2 | 85 | 400 | Death Hand | yes |
| Atreides | 77 | 0 | 0 | 50 | Fremen | yes |
| Ordos | 128 | 1 | 10 | 125 | Saboteur | yes |
| Fremen | 10 | 0 | 0 | 300 | Fremen | - |
| Sardaukar | 128 | 0 | 0 | 600 | Death Hand | - |
| Mercenary | 0 | 0 | 0 | 300 | Saboteur | - |

Two of those columns are the whole of what "playing Harkonnen feels
different" means mechanically:

- **decay and chance** are a building rotting on its own.  A Harkonnen
  building loses 2 points of health with a chance of 85; an Ordos one loses
  1 with a chance of 10; an Atreides building never decays.  That is why
  Harkonnen bases need a Repair Facility and Atreides ones do not.
- **countdown** is how long the house's special weapon takes to recharge.
  The Atreides can call the Fremen every 50 ticks and the Harkonnen can
  fire a Death Hand every 400, which is what makes one of them a tactic and
  the other an event.

The three houses without a mentat are not playable; they exist so the game
can put their units on a map - the Fremen the Atreides summon, the
Sardaukar the Emperor sends, and the Mercenaries, which Dune II never uses
at all.  Note that Fremen and Sardaukar borrow the Ordos and Harkonnen
prefix letters rather than having their own.

## The base

Nineteen buildings, and the interesting part is not their cost but the
graph that says what has to exist before what.  It is a bitmask over this
same table's indices, `structuresRequired`, the **longword** at `+$1C` of
each record - tested whole with `and.l`/`cmp.l` at `$010224` and
`$010C66` - and it decodes exactly (`res/data/buildings.txt`).  It was
first read as the word at `+$1E`, which drops bit 18, the Outpost:

```
Windtrap        -                 Refinery        Windtrap
Const Yard      always            Barracks        Windtrap, Outpost
Concrete        -                 WOR             Windtrap, Barracks, Outpost
Wall            Windtrap, Outpost Light Factory   Windtrap, Refinery
Turret          Windtrap, Outpost Heavy Factory   Windtrap, Light Factory, Outpost
R-Turret        Windtrap, Outpost Repair          Windtrap, Light Factory, Outpost
Spice Silo      Windtrap, Refinery   Hi-Tech      Windtrap, Heavy Factory, Outpost
Outpost         Windtrap          Starport        Windtrap, Refinery
Palace          Windtrap, Starport   IX           Windtrap, Starport, Refinery
```

Nearly every road leads through the Windtrap, and a second one through the
Outpost: nothing that fights - Barracks, walls, turrets, the heavy
factories - can go up without the radar.  From there the tree forks -
refinery first if you want money, outpost first if you want soldiers - and
the two ends of it, the Palace and IX, need a Starport, which needs a
Refinery, which needs a Windtrap.

Costs run from 5 (a slab of concrete) to 999 (the Palace).  The
`fogUncoverRadius` column is how far a building sees, and the Outpost's 10
against everything else's 1 to 6 is the radar in one number.

## The units

Twenty-seven records, of which the last nine are not units anybody builds -
five kinds of rocket, a bullet, a sonic blast, the sandworm, and the
frigate that delivers a Starport order.  They have no cost, and that is how
you tell (`res/data/units.txt`).

The eighteen real ones divide by what carries them: infantry on foot
(Infantry, Troopers, Soldier, Trooper, Saboteur), wheels and tracks
(Trike, Raider Trike, Quad, Tank, Siege Tank, Launcher, Deviator,
Devastator, Sonic Tank, Harvester, MCV), and air (Carryall, Ornithopter).
The column once read as a tech level (`+$12`) is not one: it is how far
the fog lifts round the unit, the number UNIT.EMC's routine 40 hands to
`$019FFE`.  The same field in the building table is the same thing.

Two columns are worth pointing at:

- **turret** (`+$48`) is a second sprite drawn on top of the hull, and the
  units that have one - Tank, Siege Tank - are exactly the ones whose gun
  turns independently of the way they are driving.  `-1` means the whole
  unit turns as one piece.
- **speed** (`+$42`) is where the Mega Drive edition quietly disagrees with
  the PC: the binary table gives a Trike 60 and a Harvester 30 where
  `PROFILE.INI`'s `[COMBAT]` section says 45 and 20.

## The two sets of numbers, and which one is real

`PROFILE.INI` is in the cartridge, as text, and it is the PC game's own
copy of the same table:

```
[CONSTRUCT]                        cost time   hp tech camp  pB  pT   ?
Const Yard=      400,  80, 400,   3,   99,  0, 300,   0
Palace=            0,   0,1000,   5,    8,  0, 400,   0
Carryall=        300,  64, 100,   0,    0,  0,  20,  16
[COMBAT]                           range dmg  rof speed
Tank=              4,  25,  80,  25
Trike=             3,   5,  50,  45
[RANKING]
Sand Snake=50 … Ruler of Arrakis=1500
```

The binary table disagrees with it - Palace 999 against 0, Carryall 800
against 300 - so one of them is what the game plays by.  **It is the
binary table, and the INI is dead data.**

The proof is in how a file gets opened.  The directory at `$052C2C` is not
searched by the names it holds; nothing outside the directory references
any of them.  Files are opened by a name the code builds, and there are
exactly two places that build one:

```
$016086   "SCEN%c%03d.INI"        the 27 missions
$016D26   "%s.EMC"                with "UNIT", "TEAM", "BUILD"
```

`PROFILE`, `HOUSE`, `REGION` and `PLAYER` appear **nowhere in the code**.
The game opens the missions and three of the four scripts, and never opens
anything else in that directory.  So `PROFILE.INI`, `HOUSE.INI`, the three
`REGION*.INI` and `PLAYER.EMC` are the PC original's files carried along in
the cartridge and never read - which is why `res/data/buildings.txt`
reports the binary table and not the text.

That makes the INI files no less interesting.  They are Westwood's own
numbers, and comparing them against the table the Mega Drive actually runs
is how you see what this port changed: a Palace that cannot be built on the
PC costs 999 here, a Carryall 800 instead of 300, a Trike moves at 60
instead of 45.

`[RANKING]` is the end-of-mission title - score 50 makes you a Sand Snake
and 1500 the Ruler of Arrakis - and that one may well be dead too.

## A mission

Twenty-seven of them - nine for each playable house - and on the Mega Drive
they are a tagged binary rather than the PC's text.  `tools/sega/sega_scen.py`
reads them into `res/data/missions.txt`:

```
== SCENA001.INI   $056FA6  406 bytes
   briefing HARVEST.WSA    win WIN1.WSA     lose LOSTBILD.WSA
   Timeout=0  MapScale=1  CursorPos=1224  TacticalPos=1224  LoseFlags=4  WinFlags=6
   Atreides   player   credits 990   quota 1000  max units 25
   Ordos      computer credits 0     quota 0     max units 16
   Seed=1
   the starport stocks: 5 Trike, 5 Quad, 6 Tank, 5 Launcher, 6 Siege Tank,
                        4 Harvester, 2 MCV, 5 'Thopter
   18 units, 1 buildings
```

and writes each one back out as the `.INI` it was converted from, in
`res/data/files/SCEN*.ini`.

### The format is the loader's, not a pattern

This was guessed at once and the guess was wrong.  The format is a switch
at **`$0161F0`** on the tag's high byte, eleven sections with a handler
each, and every handler says in 68000 how long its record is and what each
word in it means:

| section | handler | payload | what |
|---|---|---|---|
| 0 | `$016418` | varies | `[BASIC]` - three picture names and six words |
| 1 | `$016500` | varies | `[MAP]` - `Seed`, and counted lists for `Bloom` (the spice blooms) and `Field` |
| 2-5 | `$0165AC` | 2 | a house's `Quota`/`Credits`/`Brain`/`MaxUnit` |
| 6 | inline | 2 | `[CHOAM]` - how many of unit *key* the starport stocks |
| 7 | `$016650` | 10 | `[TEAMS]` |
| 8 | `$0166CA` | 12 | `[UNITS]` |
| 9 | `$016856` | 6 or 10 | `[STRUCTURES]`, `GEN` and `ID` |
| 10 | `$016988` | 8 | `[REINFORCEMENTS]` |

The check is that it comes out even: read straight through, record after
record, **all 27 files end exactly on their `$FFFF` with nothing left
over.**  The older reading - looking for runs of records whose index
counted 1, 2, 3 at a constant spacing - could not do that, and had the
reinforcements down as structures, because a map position's high byte is
`$0A` and so is the reinforcement tag.

Three things that only the loader could settle:

- **Section 5 is the Sardaukar, not the Fremen.**  `$0165AC` turns a
  section number into a house through the table at `$0714A4`, which holds
  0, 1, 2, 4.  They appear in exactly three missions - the ninth of each
  campaign - with 9000, 15500 and 10500 credits and a unit cap of 35 to 38.
  That is the Emperor, and it is the last mission of every campaign.
- **Section 6 is CHOAM**, the starport's stock: the key is a unit index and
  the word is how many there are.  The eight keys that occur are 'Thopter,
  Launcher, Tank, Siege Tank, Trike, Quad, Harvester and MCV.
- **A team's two letters go through the game's own lists** - behaviour in
  the five at `$06CE66` (Normal, Staging, Flee, Kamikaze, Guard), movement
  in the six at `$06CE4E` (Foot, Tracked, Harvester, Wheeled, Winged,
  Slither).  Both searches take the *first* match, and there are two 'W's,
  so of Wheeled and Winged only Wheeled can ever be named by a scenario.

And one bug it turned up.  `SCENO009.INI` is the last file in the
directory, so nothing follows it to say where it ends, and it was being cut
1212 bytes short.  Parsing the records says where: the `$FFFF` is at
`$060E82` and the file is 2726 bytes, not 1514.

A mission is: three pictures, where the map starts and how far it is zoomed
out, and then **one section per house taking part**.  A house section has
four fields and one of them settles everything else - `Brain`, which holds
`H` or `C`.  Exactly one house per mission is `H`, and that is the player.

- **Quota** is spice to harvest.  Where it is non-zero the mission is won by
  harvesting; where it is zero it is won by destroying the other side.  In
  all three campaigns it is missions one and two that are quotas - 1000 and
  2700 spice for the Atreides - and every mission from the third on is
  fought to the end instead.
- **Credits** is what each side starts with.  Both sides climb across a
  campaign, but from very different places: the Atreides player goes 990,
  1200, 1500, 1500, 1500, 1700, 2000 while the computer facing them goes
  0, 200, 800, 1000, 1825, 2000, 2500, 3000.  The player begins ahead and
  ends behind, which is the whole difficulty curve in one column.
- **MaxUnit** caps how many units a house may have on the map at once, and
  it moves the same way: the computer's rises from 16 to 30 across the nine
  missions.

After that come the lists.  A **unit** is house, type, health, position,
facing and action - health is 256 in all 634 of them and facing takes
exactly the eight values 0, 32 ... 224.  A **structure** comes two ways:
`GEN` is position, house, type and is what the 2740 walls and slabs are,
while `ID` is index, house, type, health, position - and the loader reads
that health word and then throws it away.  A **reinforcement** is house,
unit, where (Homebase or Enemybase) and a word whose high byte is the
delay and whose low byte is `'+'` if it repeats, which is the PC file's
own trailing plus sign kept as a byte.

## What the mentat says

111 strings between `$01B2E4` and `$01F33F`, named by a table of 111
longwords at `$087D74` - all of them, with nothing in the block unnamed and
nothing in the table pointing outside it.  `tools/sega/sega_briefs.py`
writes them to `res/text/briefings.txt`.

The first three are the house descriptions on the selection screen, and
the code settles that outright: the house screen starts the house's own
music from `d4` - 0, 1 or 2 become entries `$18`, `$19`, `$1A` of the
music table at `$06A8B8`, through `$00A806` - and then, at `$01F39A`,
indexes this same table with the same `d4`.  (Those three numbers were
once read as mentat portraits; `$00A806` is the music.)

After those, `111 - 3` is `27 * 4`, and 27 is nine missions for each of
three houses.  Read in fours they are a **briefing, a victory, a defeat
and a piece of advice**:

```
  brief  27 The battle goes well, but there is no time to relax...
  win    28 Excellent!Your skill seems to improve with each assignment...
  lose   29 My goodness, what an awful defeat!If you fail at your next...
  tip    30 The Sonic Tank is a powerful ally against enemy troops...
```

That reading is checked with a vocabulary the tool did not invent - the
buildings and units out of the game's own stat tables.  **The fourth string
of each four names one of them 24 times out of 27; the other three
positions manage 5, 2 and 2.**  Advice talks about what to build and
nothing else does.  The first is also the longest of its four 24 times and
the fourth the shortest 21 times.

(An earlier attempt scored this by looking for words like "congratulations"
and "disappointing" and got a limp 16/27, which said more about the
word list than about the data.  Choosing the words after seeing the answer
is fitting the test to the conclusion; the game's own list of things is
independent of the prose entirely.)

What is *not* settled is the order of the 27 - mission by mission, or house
by house.  The only code that reads this table uses indices 0 to 2, so the
answer is somewhere else.

## The campaign map

Between missions the game shows Arrakis divided into regions, and which one
you attack next is what `REGIONA.INI`, `REGIONH.INI` and `REGIONO.INI`
describe - one per house, in plain text:

```
[GROUP1]
ATR = 13, 7, 20, 14, 21, 22
ORD = 19, 27, 26, 25, 24, 23
HAR = 6, 5, 4, 10, 3, 9
REG1 = 8, 3, 80, 80
REG2 = 15, 2, 101, 118
REG3 = 23, 3, 152, 136
ENGTXT13 = The Atreides claimed strategic regions.
```

Those files are what the PC game played by; the Mega Drive never opens
them (no code builds the name `REGION`).  Its own campaign map is binary,
in bank 09 from `$095CE8`: who owns each of the ten territories before
each mission, each mission's arrow and target, and the map picture as
sprite pieces over 864 uncompressed tiles - `tools/sega/sega_blocks.py`.

Each `GROUP` is one step of the campaign: which regions each of the three
houses holds at that point, the three regions offered as the next target
(`REG1`-`REG3`, with a screen position), and the lines of narration.  The
text comes in English, French and German in the same file, keyed by the
region number, and `REGION.INI` opens with a note to whoever was going to
translate it - "please only translate lines that follow TXT## =
statements".

## The computer player

The AI is not 68000 code.  It is Westwood **EMC script bytecode**, in four
files, and `tools/sega/emc_disasm.py` now reads it
(`res/data/scripts/`, `res/data/scripts.txt`).

### The format, and why the reading can be trusted

Each file is IFF: `FORM <len> EMC2`, then an `ORDR` chunk of 16-bit entry
offsets and a `DATA` chunk of bytecode.  An instruction is one big-endian
word whose high byte is three flag bits and a five-bit opcode; the flags
say where the parameter comes from - the low 15 bits, a signed low byte, or
the whole of the following word.

Two facts settle that this is the right reading rather than a plausible
one.  **All 61 entry points across the four files land exactly on an
instruction boundary**, and so does every jump target - 336 of them, none
off by a word.  A wrong decoding does not do that twice.

### The virtual machine, all of it

All nineteen opcodes are named now, and not from anyone's general
knowledge of Westwood's VM: **the interpreter is in the cartridge**, a
32-way switch at `$016F40` with one handler each, and reading the handlers
says what the machine is.  A script's state is fifteen words of stack at
`+$16`, a frame pointer at `+$A`, a stack pointer at `+$B` counting *down*
from 15, a return-value register at `+8` and the script's variables at
`+$C`:

| op | handler | what it does |
|---|---|---|
| 0 | `$016F8E` | `goto` - pc = base + par*2 |
| 1 | `$016FA2` | `setret` - return value = par, nothing more |
| 2 | `$016FAE` | push the return value (par 0) or the script position (par 1) |
| 3, 4 | `$017036` | push a word / a signed byte - the same handler |
| 5, 6, 7 | `$017050`… | push a variable, a local (`stack[fp - par - 2]`), a parameter (`stack[fp + par - 1]`) |
| 8 | `$0170C6` | pop the return value (par 0); **return** (par 1) - pops the frame and the saved pc |
| 9, 10, 11 | `$017142`… | pop into a variable, a local, a parameter |
| 12, 13 | `$0171B4` | drop / reserve *par* words of stack |
| 14 | `$0171CC` | `call` routine *par* of this script's function table |
| 15 | `$0171F0` | `goto-if` - pops, and jumps if it was zero |
| 16 | `$01721E` | unary `!` `-` `~` |
| 17 | `$017270` | binary, through a second 18-way switch at `$0172A0`: `&&` `\|\|` `==` `!=` `<` `<=` `>` `>=` `+` `-` `*` `/` `>>` `<<` `&` `\|` `%` `^` |
| 18 | `$0173A0` | `return` - stops the script only if the stack is empty; otherwise pops the return value and the pc |

Opcodes 19-31 all land on the same two instructions - store zero into the
pc, which stops the script - so nineteen is the whole instruction set.

### One script per thing, and the sizes give the game away

`BUILD.EMC` has **19** entry points and the game has **19 buildings**.
`UNIT.EMC` has **27** and there are **27 units**.  All distinct, all
non-zero - and the sizes confirm the pairing past any coincidence:

- the four kinds of infantry get **19 words each**;
- Trike and Raider Trike get **19 each**, and their code is identical;
- the two turrets get **45 each**; Barracks and WOR **17 each**;
- Concrete and Concrete4 get **9 each**.

Related things have identically-sized scripts, in the right places.  That
is the mapping proved, not assumed.

### What a Tank's behaviour actually is

Three words:

```
unit_tank:
 2005  4201       push    the script position
 2006  8559       goto    w1369
 2007  4801       pop    and return
```

Push the return address, jump to the shared routine at word 1369, and the
`pop and return` is where it comes back to - so a Tank's whole script is
one call to the behaviour everything else uses.
**Fourteen of the eighteen buildable units end that way** - Tank, Siege
Tank, Launcher, Deviator, Sonic Tank, Devastator, Quad, Trike, Raider
Trike, the infantry, the Saboteur.  The five projectiles share a second
routine at word 1363.  There is one combat behaviour in Dune II and almost
everything that fights uses it unaltered.

What gets a script of its own is what has a *job*:

| unit | words | |
|---|---|---|
| Carryall | 262 | flies about picking things up unasked |
| Sandworm | 168 | hunts on its own, for nobody |
| Frigate | 140 | brings a Starport order in and leaves |
| Harvester | 124 | finds spice, fills up, goes home |
| MCV | 118 | drives somewhere and becomes a building |
| 'Thopter | 135 | patrols |

Nearly half of `UNIT.EMC` is spent on six units that move without being
ordered to.  In `BUILD.EMC` it is the same shape: the Starport is longest
at 51 words - the only building that talks to something off the map - then
the Refinery at 40 and the Repair Facility at 36, while a slab of concrete
gets nine.

### So what is the AI?

Put the pieces together and the answer is unusually concrete.

**There is no strategic planner - and this port does not even load the
file that would have held one.**  The script loader at `$016C0E` opens
exactly three: `UNIT`, `TEAM` and `BUILD`.  `PLAYER.EMC` is in the
cartridge, it is 200 bytes, and nothing reads it.  For the record it is six
near-identical routines of about fifteen instructions, each a small loop
that pushes a constant, calls one of three functions, and branches back on
itself - so there was not much there to lose.

**The units carry the intelligence, and most of them do not have any.**
Twenty kilobytes of `UNIT.EMC` against two hundred bytes of `PLAYER.EMC`,
and within that twenty kilobytes fourteen of eighteen units are three-line
stubs pointing at one shared routine.

**The scenario hands the computer its position.**  Starting credits, the
cap on its unit count, and the units and structures it begins with are all
in the mission file.  It does not scout a site and expand into it; it is
placed.

**Teams are declared, not formed.**  A mission's team records name a house,
a movement class, a behaviour and a minimum and maximum size - the shape of
the PC file's `Harkonnen,Foot,Kamikaze,2,4`.  The computer builds towards
those templates rather than deciding what to group.

**Difficulty is arithmetic.**  Across a campaign the computer's credits
climb 0, 200, 800, 1000, 1825, 2000, 2500, 3000 and its unit cap goes 16 to
30, while the player's stay much flatter.

The enemy in Dune II is not thinking.  It is a scripted opponent given more
money and a bigger army every mission, and it feels alive because the
things on the map - the Carryall that comes for a stranded harvester, the
worm that eats it, the frigate that arrives at the Starport - have real
behaviour of their own.

### Where a `call` goes

Found.  The loader at `$016C0E` hands the script reader a name and a table
of routines, and there is one table per script:

| script | table | entries | highest index the script calls |
|---|---|---|---|
| `UNIT.EMC` | `$0FED20` | 64 | 62 |
| `TEAM.EMC` | `$0FECE4` | 15 | 13 |
| `BUILD.EMC` | `$06B998` | 25 | 23 |

Every count covers its script's indices exactly and no further, which is
the check that says these are the right tables.  The listings now resolve a
call to the routine it reaches:

```
 2048  4E1A       call    26  ; -> L_044358
 2055  4E0E       call    14  ; -> L_0446C4
```

so a script can be followed into `orig/sega/src/`.

And the VM's calling convention says two more things about each of them
without anyone having to read the 68000 at all.  Arguments are pushed, the
call is made, the caller drops them again, and it takes the answer only if
it wants one:

```
    0  4404       push.b    4
    1  4E00       call    0   ; get facing
    2  4C01       drop    1                    <- the arity
    3  4200       push    the return value     <- so it is a question
```

The order of those two matters: the drop comes first, and looking for the
push first says almost everything is an order, which is wrong.  **36 of
the 79 routines the scripts actually call are questions; the other 43 are
called only for what they do**, and when a routine answers it usually
answers at every one of its call sites.

### What the 104 routines are

Read, one at a time, in `orig/sega/src/`.  The 104 slots are 88 distinct
routines - the three tables share some - and 48 of them are named in
`res/data/functions.txt`; the rest are either dead (`moveq #0,d0; rts`
fills 20 slots) or were read and not settled, which the file says rather
than guessing.

Three globals are what make the same shape of code mean different things
in the three scripts:

| | |
|---|---|
| `$FFDEA0` | the unit a `UNIT.EMC` script is running for |
| `$FFDE9C` | and its record in the unit table at `$06BC00` |
| `$FFD5AC` | the structure a `BUILD.EMC` script is running for |
| `$FFDCA8` | the team a `TEAM.EMC` script is running for |
| `$FFC208` | whichever of those it is - the shared `$011xxx` set uses it |

A script passes things around as a **tagged reference**: one word, the top
two bits the kind and the low fourteen the value.  The `$02Exxx` module
reads them - 0 is nothing, 1 a unit (`$02E38C` fetches it, through
`$043656` and the 102 unit pointers at `$04A852`), 2 a structure (through
`$00BAFE` and the 73 at `$04A716`), 3 a square of the map.  An earlier
reading had the first two the other way round, and several routine names
built on it were wrong with it - `functions.txt` is the corrected set.  `$02E2FA` says whether a reference is
still good, `$02E256` gives its world position and `$02E1F6` its map
square, and `$02E17C` builds one.  That is why a script can say "go to
that" without caring whether *that* is a building, a vehicle or a patch of
sand.

A unit script's vocabulary comes out as `get` - twenty properties through
one switch - and then `act`, `go.to`, `aim`, `fire`, `turn`, `step`,
`speed`, `stop`, `die`, `explode`, `deliver`, `dock`, `launch`, `delay`,
`distance`, `enemy?`, `kind`, `clear?`, `find.idle`, `find.home`,
`wander`, `count`.  A building's is much shorter: `produce`, `release`,
`animate`, `aim`, `fire`, `sound`, `target`.  A team's shorter still:
`members`, `recruit`, `centre`, `find.target`, `attack`, `behave`.

### The fourteen orders

`$0436A0` is the routine that gives a unit an order, and it reads a table
of twelve-byte records that `res/data/actions.txt` now writes out:

```
  0 Attack   1 Move     2 Retreat   3 Guard     4 Area Guard  5 Harvest
  6 Return   7 Stop     8 Ambush    9 Sabotage 10 Die        11 Hunt
 12 Deploy  13 Destruct
```

The name of order *n* is the longword **four bytes before** its record,
which is where the record in front ends - and that is what puts Attack at
0 rather than Move.  Two things say the numbering is right and neither is
a guess: every unit type's default order at `+$28` of the unit table comes
out sensible - **Guard** for everything that fights, **Stop** for the
Carryall, the Harvester, the MCV and every projectile, **Attack** for the
Sandworm, which is the one thing on Arrakis that needs no telling - and
the two orders whose record says they may interrupt a unit already busy
are exactly **Die and Destruct**.

It is one numbering across the whole game.  The mission files use it for a
unit's starting order, which is why `missions.txt` now says *Hunt* and
*Ambush* for the enemy soldiers and *Area Guard* for the player's, and so
does a script's `act`.

And **variable 0 of a unit's script is the order it is under**, which is
why every unit's routine opens by comparing it against 1, 3, 5, 6, 7 and
branching.  That is not a reading of the pattern: the script object lives
at unit+`$16` and its variables at +`$C`, so variable 0 is unit+`$22` -
and `$043766`, inside `$0436A0`, is `move.w d3,$22(a2)` with d3 the order.
A unit script is a switch on its current order, and the twenty-seven entry
points are what each kind of unit does differently inside it.

### Art the loader never sees

The `(count, pointer)` lists the loader at `$000CD8` reads are not the only
way this cartridge finds a picture.  Some of it hangs off a **plain table
of longwords**, and 44 KB was claimed by nothing else until those were
looked for.

The bar is three pointers in a row where every one is even, lands inside
the cartridge, and what it lands on survives Format80 decompression and
comes out to an exact number of tiles.  That last clause is the whole of
the safety, and it is the same one that separates a real asset list from
six bytes shaped like one.  In a megabyte it finds five tables - 9, 3, 7,
4 and 4 pointers, 3911 tiles between them - and 782 of the 44 883 bytes
they claim were previously being read as instructions by the sweep, which
is how the sweep bug came to light.

### The art

Compressed, and the compression is **Westwood Format80** - the same LZ the
PC Dune II used, with its 16-bit fields still little-endian inside a
big-endian cartridge because the data came over unchanged.  The
decompressor is at `$000C32`:

    0xxxxxxx ppppppppp   copy (c>>4)+3 bytes from (c&$0F)<<8|p back
    10cccccc             c literal bytes; $80 alone ends the stream
    11cccccc oooo        copy (c&$3F)+3 bytes from output offset oooo
    $FE nnnn v           write v, n times
    $FF nnnn oooo        copy n bytes from output offset oooo

`tools/sega/sega_gfx.py` undoes it.  Two things come out.

**The cast.**  Two tables - 19 at `$08829C`, one a building, and 27 at
`$08F1C8`, one a unit - point at sprite sets laid out as 32 bytes of
palette, a tile-number table, a word saying how big the picture unpacks to,
and then the stream.  Every one of them comes out to the byte, which is the
check that says the decompressor is right rather than merely plausible.
They are written to `res/art/sprites/` **in their own sixteen colours**.

**Everything else.**  The loader at `$000CD8` reads a list of tile blocks:

```
move.w  (a3)+,d4          ; how many tiles
beq.s   done              ; a count of 0 ends the list
movea.l (a3)+,a0          ; where they are
bpl.s   raw               ; MOVEA sets no flags on a 68000, so this
jsr     L_000C32(pc)      ; is testing bit 15 of the COUNT: set means
andi.w  #$7FFF,d4         ; the block is Format80
...
asl.w   #$5,d4            ; VRAM then advances by tiles * 32
```

**18 lists and 9858 tiles** - the terrain, the font, the panel, the
pictures.  Fourteen come from sweeping the ROM for that shape; the rest
from asking the code, which is better.  Scanning for calls to `$000CD8`
finds six, and reading what each is handed gives the lists outright:

    $001874   lea $18CE,a0
    $013108   lea $13872,a0
    $017DBE   lea $17F2A,a0
    $041686   a table of 6+6 longwords at $0416DA and $0416FE
    $0C7D2E   a table of 16-byte records at $0C7C18, first long the list
    $004392   a thunk; its caller supplies the pointer

Two things had to give for those to read.  **How strict to be depends on
where the address came from**: when sweeping, every block must be
compressed, because a raw block is checked by nothing; when the code hands
the loader an address, that is the evidence and a real list may hold raw
blocks - thirteen do.  And **the last block of a list may come up short**:
four of the code-named lists end that way while every earlier block in
them unpacks to exactly its 4096 bytes, so it is the format, not a
misreading.

The rule that makes that number trustworthy is worth stating, because a
looser one was wrong.  Six bytes shaped like a count and a pointer are six
bytes of almost anything, so the shape on its own proves nothing: a
**raw** block passes no test at all.  Only a compressed block does, because
it has to survive the decompressor and come out to exactly the tile count
that named it.  So a list is kept only when **every** block in it is
compressed.  Allowing raw ones instead claims 75 lists and 21 007 tiles -
and 119 710 bytes of that overlaps instructions the trace had already
reached, which is how you know it is wrong.  Under the strict rule the
overlap with traced code is **zero**.

Two of the fourteen are confirmed from the other direction as well:
`$017F2A` is loaded by `lea $17F2A.l,a0 / jsr $CD8.w` at `$017DB2`, and
`$030874` and `$03322C` are named by the pointer tables at `$0416DA` and
`$0416FE`.

These go to `res/art/blocks/` in grey: a block carries no palette, because
which of the VDP's four it is drawn in is decided by the code that loads
it.

Beyond them the listing marks another 1066 tiles' worth of **pixel-shaped
data** in the gaps - runs that use few pens and repeat them along their
rows.  They are labelled as unconfirmed and they should stay that way:
comparing them against live VRAM from the middle of a battle finds none of
them, where the same comparison finds 2101 of the tiles in the asset
lists - measured when there were 6791 of them, before the code-named
lists took the count to 9858.  That is not proof they are nothing - the sprite sets score near
zero on the same test only because no buildings were placed in that
capture - but it is not enough to call them pictures.

## What the listing now says

`lcw` reports how much of its input each stream ate, so `sega_extract.py`
can mark where every picture begins and ends.  With that fed back in:

| | at first | after the art | by reading | **with the machine** |
|---|---|---|---|---|
| code | 14.9% | 14.3% | 14.7% | **13.6%** |
| named data | 35.7% | 78.2% | 79.8% | **86.4%** |
| unaccounted for | 49.4% | 7.6% | 5.5% | **0.0%** |

1363 named regions, none of them only "pointed at", and `gaps.txt` empty.
The code figure fell on purpose: the last column threw out everything a
guess had decoded inside a named region or over a byte the game only ever
reads.  How the last column was got is the section after next; the rest of
this one is how the earlier ones were.

Two things did most of the *latest* stretch, and both are structural
rather than a lucky guess at one block.

**The switch tables.**  A `jmp TBL(pc,Xn.w)` is a hole in the trace - which
case it takes is in a register - and there are 47 of them.  The table it
reads is not a hole, though: it is either a run of word offsets from its
own start or a ladder of `bra.s`, it begins at the effective address the
`jmp` itself names, and it cannot run past the lowest address any of its
own entries points at.  The `cmpi.l #N,Dn` the compiler puts in front says
the same count a second time, and where the two disagree the guard is
right - three tables read one entry too many without it, and one of those
three claimed two bytes of the routine's own code.  Following them added
**4074 bytes of code and 1260 instructions**, and among what they opened up
were the scenario loader and the EMC interpreter, which is where the two
sections above came from.

**The animation table.**  `$060E84` is read twice, at `$004B7A` and
`$004BB2`, and both do the same four instructions: `lsl.w #3,d0` for an
eight-byte record, `move.l $4(a1),$8(a0)` for the second longword whole,
and `andi.l #$FFFFFF` on the first before it goes to `$FFBF04`, which is
where the graphics are read from.  So a record is two tagged 24-bit
addresses - the pixels, and a list that goes with them - and `$00000000/
$FFFFFFFF` is an unused slot.  Nothing says how long the table is and
nothing has to: read forwards while both halves are addresses inside the
cartridge and it stops after **357 records, at `$0619AC`** - and `$0619AC`
is the lowest address any of those records points at.  The table ends
exactly where the first thing it names begins, which is not something a
wrong length produces.  That accounted for most of bank 06, which had been
the largest open stretch in the cartridge; it is no longer in the top
twenty of `gaps.txt`.

Two things did most of the stretch before that.  The **picture table** at
`$0416DA` was read as 36 longwords in groups ended by a zero - wrongly: the
loader at `$041662` takes twelve records of three longwords, and the
blocks are frames of the tutorial's name tables (see "The tutorial"
below).  And the **pointed-at pass** turned 40 KB of anonymous `dc.b`
into blocks with a caller.  The code figure
went *down* on purpose: the gap sweep was reading pictures as instructions,
and it is now kept out of anything a named region already accounts for.  A
Format80 stream that begins `81 00` decodes perfectly happily as `sbcd.b
d0,d0`, and five such lines in a row were all the sweep needed.

`orig/sega/gaps.txt` is the standing list of what is still nobody's -
every run of 16 bytes or more, largest first.  It is written by the same
pass that measures the coverage, because the next thing worth chasing is
always the biggest of those and guessing which that is has been wrong
twice.

A banner a region:

```
; ==== $030874-$030887: an asset list: 3 blocks, 338 tiles, read by $000CD8
; ==== $030888-$0312B9: 128 tiles, Format80
; ==== $0312BC-$031DA6: 128 tiles, Format80
```

## Asking the machine

The last 5.5% would not come by reading.  So the Genesis core was patched
(`patch_gpgx_touch`, `tools/build_toolchain.py`) to keep, for every
cartridge byte, whether the 68000 fetched it as an instruction, read it as
data, the VDP's DMA sent it to VRAM or CRAM, or the Z80 read it - and the
address of the instruction that first did.  Two things in the core needed
care: the checksum at `$00293C` reads the whole cartridge at boot and is
told not to count (`blind`), and an instruction the core runs outside its
main loop, after a write to the VDP's control port, has to be marked too
(`$000D72` is the one that showed it).

`tools/sega/sega_touch.py` then drives the game.  Random input finds the
menus and the first battle and stops there; the options screen and the
password table do the rest - every mission of every house, the music and
sound tests (every tune and every effect, so every sample the Z80 plays),
SPLURGEOLA typed mid-battle to win a quota mission and go through the
victory screens, DUNEFINALE for the three endings, PLAYTESTER so a random
player survives long enough to build.  From wherever those end, a
coverage-guided random player keeps any state that ran new code.  31 463
instructions ran, of 42 882 in the listing.

The record is `orig/sega/res/trace.txt` and the extractor takes it as
ground truth.  What it overturned:

- `$070000`-`$087FFF`, 96 KB listed as DAC samples by their shape, is
  never read by the Z80.  It is the 27 battlefields and a run of sprite
  pixels.
- The "PC game's music file names" at `$020C10` are the passwords.
- UNIT.EMC's FORM says 5438 bytes; the directory arithmetic had said 19876
  and swallowed the tiles and fonts after it.
- `bge.w; addq.w; bra.w` at `$017AD6` is three words any pointer scan
  takes for addresses - and code the game runs.
- `and.l d1,(a4)` at `$024334` is `$C394`, which the decoder was calling a
  broken EXG.  The machine ran it, so the decoder was wrong.
- Every Format80 stream is one byte longer than the art finder said: the
  decompressor reads the `$80` that ends it.

With that in hand the rest was read reader by reader - `sega_tables_lo.py`,
`sega_tables_hi.py`, `sega_blocks.py`, `sega_sprites.py`,
`sega_pictures.py`, `sega_maps.py`, each with a `check()` the extractor
runs.  What they found is below and in their docstrings.

## The battlefields are stored, not grown

The PC game grows each map from the mission's `Seed`.  The Mega Drive
keeps all 27 made: the mission loader's `S` key (`$016540`) stores the
number at `$FFC064` and `$01B1D4` looks it up in the table at `$01B276` -
a byte a cell, 64 x 64, or 32 x 32 when bit 31 of the pointer is set (the
first two missions of each house, the ones with `MapScale=1`).  They fill
`$071574`-`$087D73` end to end.  Three of them - Seed 9, 18 and 26 - are
named by no mission file, and the recorded run never loaded them either.
A cell is a terrain icon already fitted to its neighbours, which is the
work the PC generator does at run time.  `res/data/maps.txt`.

## Passwords

`$0218FE` looks the ten letters up in the table at `$08811C` and switches
on the kind; nothing is computed.  24 are a house and a mission (2 to 9),
DUNEFINALE is the ending, and four are for the playtesters: LOOKAROUND
toggles `$FFC198` (the whole map), SPLURGEOLA sets the credits to 25000,
PLAYTESTER toggles bit 0 of `$FFC019` - the damage routines at `$00F8F8`
and `$046BDE` test the word `$FFC018` and skip the player's house - and VERSIONNUM shows "1.2-011794".
`res/data/passwords.txt`.

## The tutorial

The picture table is the tutorial: twelve records of (asset list, block
A, block B), block A unpacked to `$FF1C00` and drawn on plane A, block B to
`$FF7400` on plane B.  A block is frames of a 40 x 28 name table - a byte
count, then `$80 n` skips n cells, `$81-$FF` is that many literal words
less `$80`, `$01-$7F` repeats the next word - ended by `$FFFF`, and all 17
parse exactly.  They are played by a script interpreter at `$0418D4`: 8
scripts, 26 opcodes (wait, show frame, fade, the cursor sprite, the text
box...).  `res/art/pictures.txt` and the renders beside it.

## The sprite animations

The table at `$060E84` pairs a frame list with its pixels.  The list tag
is the drawing layer (the sprite chain is sorted by it and y), `$0B`
turns the house palette off and a negative tag keeps the sprite from being
dropped in a crowded band; only the sign of the pixel tag is ever tested -
`$80` means DMA the pixels when the sprite is made, otherwise they are
already in VRAM.  Six routes put sprite art into VRAM, the biggest being
a preload list at `$00A488` read once a mission.  `res/art/animations.txt`.

## The sound driver's commands

`orig/sega/res/sound/commands.txt` has all of them written out.  What
reading them properly changed:

- A handler's byte count has to include what the routines it calls read:
  `L08A5` takes a voice number off the ring.  Counted that way `$02` (load
  instrument) takes two bytes, `$04` (detune) three and `$1E` four - the
  old table had none, one and two.
- `$0C` pauses everything and `$0D` resumes - it was listed as "stop the
  music".  `$00`/`$01` are note on and note off, `$1F`/`$20` a voice's and
  the master attenuation (not volume: the sum turns the carriers down),
  `$1B` sets a song variable that a track's `branch` tests.
- Track command `$6D` puts a voice on the frame clock instead of the tempo
  clock; `$72` has six sub-commands (stop, pause, resume, pause by
  variable, master and voice attenuation); `branch`'s tests were printed
  the wrong way round.
- The game sends five commands (install, play, stop, reset voices, mute
  track); pause and resume only through jump stubs nothing calls.  The
  rest of the 68000's sender library is unused.

## Mistakes in the cartridge itself

Things the game gets wrong, found while reading it:

- the flight path at `$008B08` has 179 steps and is indexed up to 179, so
  its last step reads the first instruction after it;
- `$009D64` copies a banner's palette from `$A438`, which is code;
- the Z80 driver copies only 32 bytes of a pitch envelope, so the game
  bank's envelopes 0 and 1 play half their steps, and envelope 6 in both
  banks overflows its 16 bits;
- a noise instrument always takes over PSG tone channel 2, because the
  driver tests the instrument's type where it meant its noise mode;
- seven animation records (110, 116-118, 126-128) point twelve bytes into
  the middle of another list;
- `$029AB0`-`$02DC8B` is a dead copy of an older build's first 16 KB;
- the big explosion `$0446C8` takes its damage from `d6`, which it never
  sets - whatever the script interpreter left there;
- the unit tick `$043784` tests a Fremen's hit points against twice its
  maximum, so the test is always true and Fremen are always on Hunt;
- the Deviator's hit (`$047882`) picks the new default order by asking
  whether the player is house 2, and `$00ADBE` reads `8(a2)` before `a2` is
  set, working only because its caller left a projectile there;
- `pick.up` (`$043FE0`) takes the first free Refinery, not the nearest -
  its best distance is never updated in that loop;
- the build panel at `$0287D8` passes `a3`, never loaded, to `$01220C`;
- the zoom renderer uses `add.w` at `$024B3A` where its siblings use
  `add.l`, dropping a fraction every eighth sample;
- the lose fly-over `$026A96` never sets its tune outside mission 7 and
  plays whatever the caller left in `d3`;
- `$01FBB6` reads past a text that does not end in `.`, `!`, `?` or CR.

Some rules are the Mega Drive's own rather than the PC game's: a Light
Factory upgraded twice becomes a Heavy Factory (`$00BCD8`, and `$0293C4`
does it by mission), a house-2 Barracks becomes a WOR, and when house 2's
Palace countdown runs out its first Saboteur is blown up.

## The sprites, frame by frame

`$02EC72` holds **256 sprite frames of 26 bytes**: a count word, then two
pieces of twelve.  A piece is a width, a height, an x, the VDP's size and
link bytes, its attribute word, and a y - and the reading is checked by
the format itself, because the size byte carries the width and height in
two-bit fields of its own.  All 512 pieces agree with the width and height
words beside them, 8, 16, 24 or 32 pixels each way.  Nothing else in the
cartridge does that eight times in a row, let alone 512.

## The ranks

`$0A68CA` is the score ladder: seven thresholds and `$FFFF` (50, 100, 150,
200, 250, 300, 400), then the nine ranks at `$0A68DA`, seventeen bytes
each and centred with spaces - Sand Snake, Desert Mongoose, Sand Warrior,
Dune Trooper, Squad Leader, Outpost Commander, Base Commander, Scourge of
Dune, Ruler of Arrakis - and then the three house names at `$0A6974`, nine
bytes each, also centred.

## The sound

The Z80 owns it.  Its driver's bounds are the uploader's own rather than a
guess - the routine at `$00152A` copies `$188A` bytes from `$00294E` into
`$A00000` and zeroes the rest of the Z80's 8 KB - and
`tools/sega/sega_z80.py` disassembles it: 6282 bytes, 3064 instructions,
in `res/sound/z80driver.asm`.  It reaches all three things a Z80 here can:
the YM2612 at `$4000-$4002` (16 references), the cartridge bank register at
`$6000`, and the PSG at `$7F11`.

A quarter of the ROM - 280 KB in two banks at `$070000` and `$0C8000` - is
eight-bit sample for the DAC.

### How the 68000 asks for a tune

Two bytes of the Z80's RAM are the mailbox: a write index at `$0036` that
only the 68000 touches, a read index at `$0037` that only the Z80 touches,
and a 64-byte ring at `$1B40`.  A command is `$FF`, an opcode and its
arguments; the driver's main loop reads bytes until it sees `$FF` and
jumps on the next one.  There are twenty-four opcodes and the game sends
seven of them.

The 68000 side is a C library of one function per command, all entering
through the same three routines - `$001596` takes the Z80's bus,
`$0015EA` pushes a byte, `$0015CC` gives the bus back.  It appears twice in
the cartridge, in bank 0 and at `$02AF00`, and only bank 0's copy is used.

The two that matter are `$0B`, which installs four 24-bit ROM addresses
the driver reads everything through, and `$10`, which starts a song by
number.  The game installs two sets of four: the front end's at `$02DD14`
and the game's at `$02DCC8`.  Two more `$0B`s install four copies of a
pointer to four `$FF` bytes, which is the library's way of saying
"nothing".

### What a song is

The third of the four pointers is a song directory: 16-bit offsets,
little-endian inside a big-endian cartridge, each relative to the
directory.  The number of songs is the first offset divided by two,
because song 0's header follows the last entry.  A header is a track count
and one 16-bit offset per track, and each track gets a voice of its own -
sixteen of 32 bytes at Z80 `$1B80`.

A track is a byte stream:

| byte | what it is |
|---|---|
| `< $60` | a note; the voice's sound slot says what it sounds like |
| `$60-$72` | one of nineteen commands - `end`, `patch`, `volume`, `loop`, `jump`, `set`, `branch`, ... |
| `$80-$BF` | how long the note sounds, six bits a byte |
| `$C0-$FF` | how long until the next event, six bits a byte |

Both counts run to the first byte that does not carry the same two top
bits, and the driver stores them negated as up-counters.

`tools/sega/sega_seq.py` writes `res/sound/music.txt` - the command table,
the resource sets and every song - and a full event listing beside it.
**13 songs in the front end's bank and 84 in the game's, 143 tracks.**

### Why that reading can be trusted

Follow every track of every song to its `end` and add up the bytes.  In
both banks the total is exactly the distance from the directory to the
last track's last byte: nothing claimed twice, nothing left over.  And
both banks stop where the *next* resource pointer starts - the front end's
songs end at `$0D01F5` and the game's at `$0FE129`, which are the very
addresses command `$0B` installed beside them.  Neither of those would
come out that way if a header or an event were being read wrongly.  The
tool prints the check and refuses to finish if it fails.

### What the game calls its sounds, and which are sampled

`$020870` is the game's own list: **58 names of 16 bytes** - eighteen tunes
("cyrils council", "the lego tune", "harkonnen dirge") and then the
effects and the speech ("invalid select", "credit up", "machinegun",
"explosion 1", "yes sir", "moving out").  **Their order is not the song
numbering**, though it was once read that way.  What joins a name to a
song is the options screen's music and sound tests: `$087F3C` holds 18
and `$087FD4` 40 records of (name pointer, song number), and the music
test hands that number straight to `snd_song_start` (`$0212A2`).  Read
through them, `moveq #40` - thirteen call sites, the menus' click - is
*positive select*, and *explosion 1* is song 38.

A note is only a pitch; what makes the noise is the *instrument* the
track's `patch` names, and type 1 is the sampled one - it takes YM2612
channel 6, the DAC channel.  Reading every song that way
(`res/sound/music.txt`):

| songs | kind | what |
|---|---|---|
| 0-17 | FM and PSG, some with sampled drums | the 18 tunes |
| 20-44 | FM or PSG noise | synthesised effects: target, menu select, invalid and positive select, credit up and down, countdown, heavy drop, rocket launch, sonic blast, gas hit, the "(fx)" rifle, machinegun, cannon, static and worm, explosions 1 and 2, dud explosion |
| 64-83 | sampled | speech (unit approach, construction complete, under attack, yes sir, acknowledged, reporting, moving out) **and** sampled effects: placement, cannon, explosion 3, rifle, machinegun, missile, static, scream, worm eats, squish, multi explosion, building, death hand |

**So the Mega Drive does have sampled explosions and gunfire**: song 71
"explosion 3" (sample 9), 81 "multi explosion" (sample 9 again, with FM),
69 "cannon", 72 "rifle", 73 "machinegun", 76 "scream".  Most effects come
in two forms, a synthesised "(fx)" one and a sampled one, and which the
game plays at a given moment is the effect table's business (S10).

### How fast a sample plays, and how that is known

The sample's flags byte carries a YM2612 timer A period in its low nibble -
the driver at `$01370` writes registers `$24` and `$25` with the negated
nibble - so one byte leaves the DAC every `k` timer ticks and the rate is
52781 Hz over `k` - the PAL clock, because this is the European cartridge
(region `E` at `$1F0`) and the core runs it as a PAL machine.  The four
values in use are 5, 7, 8 and 10: 10556, 7540, 6598 and 5278 Hz.

The emulator agrees, which is the point of saying it.  Dumping the Z80's
8 KB frame by frame and watching the driver's stream pointer at `$02FC`,
a nibble of 5 consumes about 202 bytes a frame and a nibble of 10 about
106 - 10.0 and 5.3 kHz at 49.7 frames a second.  The two-to-one spread I
first read as measurement noise is the format.

### The trap this hid behind

The sound looked like dead code the first time it was looked at: nothing
in the cartridge appeared to call the library.  It is called with `jsr
$1624.w` - **absolute short**, `4EB8`, not the `4EB9` of a long address -
so a cross-reference scan that knows only `4EB9`/`4EBA`/`61xx` finds the
initialiser and concludes the game never plays a sound.  The disassembler
had it right all along; the scan was wrong.

What settled it was measurement rather than more reading.  The Genesis
core is patched to hand out the Z80's 8 KB (`retro-run`'s `z80` command),
and a dump taken while the title music plays shows the ring holding
`FF 0B` and four live pointers into the sample banks - not the four `$FF`
bytes the initialiser installs.

## The routines, named

907 routines are named in `orig/sega/res/names/`, each with what it does,
its parameters, its result and what it changes; the listing carries them.
A few things that fell out of naming them:

- a map square in RAM is a word (bits 0-8 the tile, 9-15 the overlay), a
  flags byte (bit 3 revealed, bit 4 a unit here, bit 5 a structure) and
  the object's index plus one;
- `$FFC050` is the campaign level, `$FFC04C` the mission, `$FFC274` the
  player's house, `$FFC224` the full-fog map tile;
- the division helpers take the dividend in `d1` and the divisor in `d0`
  and answer in `d1`; `clib_putc_console` writes through an illegal
  instruction the "PUTC" trap at `$0047E0` catches;
- teams are 16 records of `$54` bytes, units 102 of `$8C` at `$FF1000`
  and houses six at `$FFDC24`.

## What to read next

- `orig/sega/res/data/` - the tables and the missions, generated
- `orig/sega/res/data/files/` - the original data files, extracted
- `.claude/docs/originals.md` - how the disassembly itself works
- `orig/sega/src/rom00.asm` onwards - the engine, with the data regions
  banner-marked
