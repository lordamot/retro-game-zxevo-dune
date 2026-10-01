#!/usr/bin/env python3
"""sega_driver.py - the Mega Drive Dune II's Z80 sound driver, as Python.

Not a command of its own: `sega_mod.py` plays songs through it.  It is a
model of the driver's *sequencing* - which note starts on which chip
channel when, with which instrument, at which pitch and loudness, and when
it is keyed off - read out of `orig/sega/res/sound/z80driver.asm`.  What
the chips then make of it is `sega_mod.py`'s business.  Every rule below
names the Z80 routine it was read from; `commands.txt` and
`instruments.txt` are the format.

## The clocks (L0041, L08F7)

Each frame (50 a second: the cartridge is the European one, region
`E` at `$1F0`, and runs on a PAL machine) the interrupt adds the tempo
step at `$08BE` to the accumulator at `$08C0`; the step is
`(tempo * $DA) >> 7` (L0E1D) and track command `$68` sets tempo `t + 40`.
The accumulator's high byte is the number of music ticks owed, and the main
loop pays them one pass at a time.  The first pass of a frame also does the
frame's work, so a pass is "frame", "tick", or both, and each pass runs, in
this order: the pitch envelopes (L0ECA), the gates (L0806), the sixteen
voices (L0458) and the frequency rewrite (L0FC8).  A voice, a gate and an
envelope each run on the frame clock if the voice said `frameclock`
(flag 3), otherwise on the music clock.

## A voice (L0458, L04BC, L055B)

Its timer counts up to zero on its clock, and then it reads events until
one costs time.  Delays and gates are sticky: a time byte sets the value
every later note uses, until another replaces it.  A note, and every
command that is not flow control (`$64 $65 $6F $71`), reloads the timer
with the current delay; a delay of 0 carries straight on, which is how a
chord is written.  A loop's count is how many times its body plays; 127 is
for ever (L0621, L064C), and the stack holds four.

## A note (L1208 and on)

Attenuation is the master's plus the voice's, an 8-bit sum taken as 127
past 127, and only FM listens to it: each carrier's TL becomes
`TL + a * (127 - TL) / 128` (L15F7).  Then the instrument's type decides the
channel: FM takes FM1 FM2 FM4 FM5 FM6 FM3 (L17E2, `$1795`), FM3 alone if
the instrument is in special mode; a sample takes FM6 as the DAC and holds
it until the sample ends; PSG tone takes tone 0-2; noise takes the noise
channel *and* tone 2, unconditionally.

A new note never keys the voice's previous one off: if that one is still
sounding, the new one goes to another free channel and both sound.  A
channel is free once its gate has run out; among free channels one that
last belonged to this voice is taken first (unless the voice has flag 7),
then the one released longest ago.  With none free, the busy channel of
lowest priority is stolen if the voice's priority is at least that - and
with every priority 0, that is simply the first busy channel in the table.
A stolen FM channel is keyed off first.

A gate counts on the note's own clock and keys the note off when it runs
out (L0806).  A gate of 0 holds the note until its channel is taken.  A
sample plays to its end whatever its gate.

## Pitch (L10AA, L0E2F, L0ECA)

A note plays at `note + (detune + envelope) / 256` semitones, the sum
wrapping as a 16-bit number, clamped to 0..$5F.  A pitch envelope is a
start value and up to ten `(count, step)` pairs (the driver copies 32
bytes); a pair adds `step` once a tick for `count` ticks, and when the
list ends the offset snaps back to 0.  Four envelopes can run at once.
An envelope belongs to the voice, so it bends every note the voice is
sounding; with flag 6 it restarts on every note.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sega_seq import songs, samples, vlq, s16  # noqa: E402

# the vertical blank of a PAL Mega Drive: 53203424 Hz / (3420 x 313)
FRAME_HZ = 53203424 / (3420 * 313)    # 49.70 Hz
DEFAULT_STEP = 0x00CC              # tempo 120, what the driver resets to
CARRIERS = [0x08, 0x08, 0x08, 0x08, 0x0A, 0x0E, 0x0E, 0x0F]   # $15C8
FM_ORDER = [0, 1, 3, 4, 5, 2]      # $1795: FM1 FM2 FM4 FM5 FM6 FM3
ENV_SLOTS = 4                      # $0EAD
ENV_BYTES = 32                     # $0E8D: ld c,$20
LOOP_SLOTS = 4                     # +16 +19 +22 +25


def tempo_step(t):
    """L0E1D: the tempo byte -> the 16-bit step added every frame."""
    return (t * 0xDA) >> 7 & 0xFFFF


class Bank:
    """The four resources one `$0B` installs: instruments, envelopes,
    songs, samples - as the driver reads them."""

    def __init__(self, rom, b0, b1, b2, b3):
        self.rom, self.addr = rom, (b0, b1, b2, b3)
        n = struct.unpack_from("<H", rom, b0)[0] // 2
        self.inst = [rom[b0 + struct.unpack_from("<H", rom, b0 + 2 * i)[0]:]
                     [:39] for i in range(n)]
        n = struct.unpack_from("<H", rom, b1)[0] // 2
        self.env = []
        for i in range(n):
            raw = rom[b1 + struct.unpack_from("<H", rom, b1 + 2 * i)[0]:][
                :ENV_BYTES]
            start = s16(struct.unpack_from("<H", raw, 0)[0])
            steps, p = [], 2
            while p + 3 <= len(raw) and raw[p]:
                steps.append((raw[p],
                              s16(struct.unpack_from("<H", raw, p + 1)[0])))
                p += 3
            self.env.append((start, steps))
        self.songs = {i: tr for i, _, tr in songs(rom, b2)}
        self.samples = {i: (fl, b3 + off, ln)
                        for i, fl, off, _, ln in samples(rom, b3)}


class Voice:
    def __init__(self, n):
        self.n = n
        self.flags = 0
        self.pc = 0
        self.timer = 0
        self.delay = 0
        self.gate = 0
        self.inst = None
        self.inst_no = None
        self.loops = []
        self.prio = 0
        self.env_no = None
        self.att = 0
        self.song = self.track = None
        self.detune = 0
        self.env_off = 0

    active = property(lambda s: bool(s.flags & 0x01))
    muted = property(lambda s: bool(s.flags & 0x02))
    frameclock = property(lambda s: bool(s.flags & 0x08))
    running = property(lambda s: bool(s.flags & 0x10))


class Channel:
    """One chip channel: FM1-6, PSG tone 0-2, noise, or the DAC."""

    def __init__(self, kind, n):
        self.kind, self.n = kind, n
        self.busy = False           # sounding and not yet released
        self.voice = None           # who used it last
        self.prio = 0
        self.released = 0           # +6: when it was let go
        self.gate = 0               # ticks left, 0 = held
        self.frameclock = False
        self.reserved = False       # FM6 under a sample, tone 2 under noise
        self.note = None
        self.until = None           # a sample's or a release's end


class Event:
    """What happened on a channel, and when: `frame` is the frame of the
    pass, `tick` the music ticks paid so far (the pass's own included), and
    `pos` the time in music ticks from the song's start - the pass's own
    tick, or for a pass that is only a frame, the tick that comes next."""
    __slots__ = ("kind", "ch", "frame", "tick", "pos", "voice", "song", "track",
                 "inst_no", "inst", "note", "att", "pitch", "sample",
                 "rate", "frameclock")

    def __init__(self, kind, ch, frame, tick, **kw):
        self.kind, self.ch, self.frame, self.tick = kind, ch, frame, tick
        for k in self.__slots__[5:]:
            setattr(self, k, kw.get(k))

    def __repr__(self):
        return (f"{self.frame:5d}/{self.tick:5d} {self.kind:5s} "
                f"{self.ch.kind}{self.ch.n} v{self.voice} n{self.note} "
                f"p{self.pitch}")


class Driver:
    """Plays songs of one bank and records every channel event."""

    def __init__(self, bank):
        self.bank = bank
        self.voices = [Voice(i) for i in range(16)]
        self.fm = [Channel("fm", i) for i in range(6)]
        self.psg = [Channel("psg", i) for i in range(3)]
        self.noise = Channel("noise", 0)
        self.dac = Channel("dac", 0)
        self.slots = [None] * ENV_SLOTS
        self.step = DEFAULT_STEP
        self.acc = 0
        self.master = 0
        self.vars = [0] * 16
        self.frame = 0
        self.tick = 0
        self.seq = 0
        self.events = []
        self.loops = {}             # voice -> [tick of each "for ever" jump]
        self.loop_start = {}        # voice -> when its "for ever" began
        self.pos = 0
        self.pitch = {}             # channel -> last pitch reported
        self.tempo_changes = [(0, 0, self.step)]

    # ------------------------------------------------------------- songs
    def play(self, song):
        """Driver command $10 (L0BDF): each track to the next free voice."""
        free = [v for v in self.voices if not v.active]
        for k, start in enumerate(self.bank.songs[song]):
            v = free[k]
            v.flags = 0x11
            v.pc = start
            v.timer = -1            # reads on its first tick
            v.song, v.track = song, k
            v.detune = 0
            v.loops = []

    def busy(self):
        return any(v.active for v in self.voices) or any(
            c.busy or c.until is not None and c.until > self.frame
            for c in self.fm + self.psg + [self.noise, self.dac])

    def run(self, frames):
        for _ in range(frames):
            self.acc += self.step
            owed, self.acc = self.acc >> 8, self.acc & 0xFF
            first = True
            while first or owed:
                b = 1 if first else 0
                if owed:
                    b |= 2
                    owed -= 1
                    self.tick += 1
                first = False
                self.pos = self.tick - 1 if b & 2 else self.tick
                self.pass_(b)
            self.frame += 1

    # ------------------------------------------------------------ a pass
    def pass_(self, b):
        for s, slot in enumerate(self.slots):            # L0ECA
            if slot and b & (1 if slot["frame"] else 2):
                self.env_step(s)
        for ch in self.fm + self.psg + [self.noise]:     # L0806
            if ch.busy and ch.gate and b & (1 if ch.frameclock else 2):
                ch.gate -= 1
                if not ch.gate:
                    self.release(ch)
        for ch in [self.dac] + self.psg + self.fm:
            if ch.until is not None and self.frame >= ch.until:
                ch.until = None
                ch.reserved = False
                if ch.kind == "dac":
                    ch.busy = False
                    self.fm[5].reserved = False
                    self.emit("end", ch, voice=ch.voice)
        for v in self.voices:                            # L0458
            if v.active and v.running and b & (1 if v.frameclock else 2):
                v.timer += 1
                if v.timer >= 0:
                    self.read(v)
        for v in self.voices:                            # L0FC8
            self.repitch(v)

    def emit(self, kind, ch, **kw):
        e = Event(kind, ch, self.frame, self.tick, **kw)
        e.pos = self.pos
        self.events.append(e)
        return e

    # ----------------------------------------------------------- reading
    def read(self, v):
        rom = self.bank.rom
        while True:
            a = v.pc
            c = rom[a]
            if c & 0x80:
                val, v.pc = vlq(rom, a)
                if c & 0x40:
                    v.delay = val
                else:
                    v.gate = val
                continue
            if c < 0x60:
                v.pc += 1
                if not v.muted:
                    self.note(v, c)
            elif c == 0x60:                              # end
                v.flags = 0
                v.gate = 0
                return
            elif c == 0x64:                              # loop
                v.loops.append([rom[a + 1], a + 2])
                if rom[a + 1] == 127:
                    self.loop_start.setdefault(v.n, self.pos)
                assert len(v.loops) <= LOOP_SLOTS
                v.pc = a + 2
                continue
            elif c == 0x65:                              # endloop
                top = v.loops[-1]
                if top[0] == 127:
                    self.loops.setdefault(v.n, []).append(self.pos)
                    v.pc = top[1]
                else:
                    top[0] -= 1
                    if top[0]:
                        v.pc = top[1]
                    else:
                        v.loops.pop()
                        v.pc = a + 1
                continue
            elif c == 0x6F:                              # jump
                v.pc = a + 3 + s16(rom[a + 1] | rom[a + 2] << 8)
                continue
            elif c == 0x71:                              # branch
                var, test, val, off = rom[a + 1:a + 5]
                x = self.vars[var & 15]
                ok = [False, x == val, x <= val, x < val, x >= val, x > val,
                      x != val]
                v.pc = a + 5 + (off if test < 7 and ok[test] else 0)
                continue
            elif c > 0x72:
                v.pc += 1
                continue
            else:
                v.pc = self.command(v, c, a)
                if not v.active:
                    return
            v.timer = -v.delay                           # L055B
            if v.delay:
                return

    def command(self, v, c, a):
        rom = self.bank.rom
        arg = rom[a + 1]
        if c == 0x61:                                    # instrument
            v.inst_no = arg
            v.inst = self.bank.inst[arg]
            return a + 2
        if c == 0x62:                                    # envelope
            v.env_no = arg
            self.env_start(v)
            return a + 2
        if c == 0x63:                                    # rest
            return a + 1
        if c == 0x66:                                    # retrigger
            v.flags = v.flags | 0x40 if arg else v.flags & ~0x40
            return a + 2
        if c == 0x67:                                    # flag 7
            v.flags = v.flags | 0x80 if arg else v.flags & ~0x80
            return a + 2
        if c == 0x68:                                    # tempo
            self.step = tempo_step((arg + 0x28) & 0xFF)
            self.tempo_changes.append((self.frame, self.pos, self.step))
            return a + 2
        if c == 0x69:                                    # mute a track
            for w in self.voices:
                if w.active and w.song == v.song and w.track == arg & 15:
                    w.flags = (w.flags & ~0x02 if arg & 0x10
                               else w.flags | 0x02)
            return a + 2
        if c == 0x6A:                                    # priority
            v.prio = arg
            return a + 2
        if c == 0x6B:                                    # another song
            self.play(arg)
            return a + 2
        if c == 0x6C:                                    # detune
            v.detune = arg | rom[a + 2] << 8
            self.dirty(v)
            return a + 3
        if c == 0x6D:                                    # frameclock
            v.flags |= 0x08
            return a + 1
        if c == 0x6E:                                    # rate
            if v.inst and v.inst[0] == 1:
                v.inst = bytes([1, arg]) + v.inst[2:]
            return a + 2
        if c == 0x70:                                    # set
            self.vars[arg & 15] = rom[a + 2]
            return a + 3
        if c == 0x72:                                    # ext
            val = rom[a + 2]
            if arg == 4:
                self.master = val
            elif arg == 5:
                v.att = val
            elif arg == 0:
                self.stop(val)
            return a + 3
        raise AssertionError(f"${c:02X} at ${a:06X}")

    def stop(self, song):
        for w in self.voices:
            if w.active and (song == 0xFF or w.song == song):
                w.flags = 0
                w.gate = 0
                for ch in self.channels_of(w):
                    self.release(ch)

    # ------------------------------------------------------------- notes
    def note(self, v, n):
        inst = v.inst
        if inst is None:
            return
        a = (self.master + v.att) & 0xFF
        if a & 0x80:
            a = 0x7F
        if v.flags & 0x40 and v.env_no is not None:      # L168C
            self.env_start(v)
        kind = inst[0]
        if kind == 0:
            if inst[2] & 0x40:
                ch = self.take_one(self.fm[2], v)
            else:
                ch = self.take([self.fm[i] for i in FM_ORDER], v)
        elif kind == 1:
            k = (n - 0x30) % 0x60
            fl, addr, ln = self.bank.samples.get(k, (0, 0, 0))
            if not ln:
                return
            ch = self.take_one(self.dac, v)
            if ch is None:
                return
            nib = inst[1] if inst[1] != 4 else fl & 0x0F
            rate = 7600489 / 144 / (nib or 1)
            self.fm[5].reserved = True
            if self.fm[5].busy:
                self.fm[5].busy = False
                self.emit("cut", self.fm[5], voice=self.fm[5].voice)
            ch.busy = True
            ch.voice, ch.prio, ch.note = v.n, v.prio, n
            ch.until = self.frame + max(1, int(ln / rate * FRAME_HZ + 0.999))
            self.emit("on", ch, voice=v.n, song=v.song, track=v.track,
                      inst_no=v.inst_no, inst=inst, note=n, att=a,
                      sample=k, rate=rate, frameclock=v.frameclock)
            return
        elif kind == 2:
            ch = self.take(self.psg, v)
        elif kind == 3:
            ch = self.take_one(self.noise, v)
            if ch is not None:
                t2 = self.psg[2]
                if t2.busy:
                    t2.busy = False
                    self.emit("cut", t2, voice=t2.voice)
                t2.reserved = True
                t2.until = None
        else:
            return
        if ch is None:
            return
        ch.busy = True
        ch.voice, ch.prio, ch.note = v.n, v.prio, n
        ch.gate = v.gate
        ch.frameclock = v.frameclock
        ch.until = None
        p = self.pitch_of(v, n)
        self.pitch[ch] = p
        self.emit("on", ch, voice=v.n, song=v.song, track=v.track,
                  inst_no=v.inst_no, inst=inst, note=n, att=a, pitch=p,
                  frameclock=v.frameclock)

    def take(self, pool, v):
        """L17E2: a channel out of a pool, or None."""
        pool = [c for c in pool if not c.reserved]
        if not v.flags & 0x80:
            for c in pool:
                if not c.busy and c.voice == v.n:
                    return c
        free = [c for c in pool if not c.busy]
        if free:
            return min(free, key=lambda c: c.released)
        if not pool:
            return None
        c = min(pool, key=lambda c: c.prio)
        if c.prio > v.prio:
            return None
        self.steal(c)
        return c

    def take_one(self, c, v):
        """L1845: a pool of one - free, or stolen on priority."""
        if not c.busy:
            return c
        if c.prio > v.prio:
            return None
        self.steal(c)
        return c

    def steal(self, c):
        c.busy = False
        self.emit("cut", c, voice=c.voice)

    def release(self, ch):
        """A gate has run out (L0806): FM keys off, PSG starts its
        release.  Noise gives tone 2 back once the release is over, which
        the renderer knows the length of; here it is when it starts."""
        ch.busy = False
        self.seq += 1
        ch.released = self.seq
        self.emit("off", ch, voice=ch.voice)
        if ch.kind == "noise":
            self.psg[2].reserved = False

    def channels_of(self, v):
        return [c for c in self.fm + self.psg + [self.noise]
                if c.busy and c.voice == v.n]

    # ------------------------------------------------------------- pitch
    def pitch_of(self, v, n):
        """L10AA: note + (detune + envelope) as 8.8 semitones, the sum
        wrapping at 16 bits, clamped to the table."""
        off = (v.detune + v.env_off) & 0xFFFF
        d = s16(off) / 256
        p = n + d
        if p >= 0x60 or p < 0:
            p = 0.0 if off & 0x8000 else 0x5F + 255 / 256
        return p

    def dirty(self, v):
        v.dirty = True

    def repitch(self, v):
        if not getattr(v, "dirty", False):
            return
        v.dirty = False
        for ch in self.fm + self.psg + [self.noise]:
            if ch.voice == v.n and ch.note is not None and (
                    ch.busy or ch in self.pitch):
                p = self.pitch_of(v, ch.note)
                if self.pitch.get(ch) != p:
                    self.pitch[ch] = p
                    self.emit("pitch", ch, voice=v.n, note=ch.note, pitch=p)

    # --------------------------------------------------------- envelopes
    def env_start(self, v):
        """L0E2F: the voice's own slot, else the first free one, else
        nothing at all."""
        if v.env_no is None or v.env_no >= len(self.bank.env):
            return
        start, steps = self.bank.env[v.env_no]
        s = next((i for i, x in enumerate(self.slots)
                  if x and x["voice"] == v.n and not v.frameclock), None)
        if s is None:
            s = next((i for i, x in enumerate(self.slots) if not x), None)
        if s is None:
            return
        self.slots[s] = {"voice": v.n, "frame": v.frameclock,
                         "steps": list(steps), "ticks": 0, "step": 0}
        v.env_off = start & 0xFFFF
        self.dirty(v)

    def env_step(self, s):
        slot = self.slots[s]
        v = self.voices[slot["voice"]]
        if slot["ticks"] > 0:
            slot["ticks"] -= 1
            v.env_off = (v.env_off + slot["step"]) & 0xFFFF
        elif slot["steps"]:
            n, step = slot["steps"].pop(0)
            slot["step"] = step
            slot["ticks"] = n - 1
            v.env_off = (v.env_off + step) & 0xFFFF
        else:
            v.env_off = 0
            self.slots[s] = None
        self.dirty(v)


def play(bank, song, frames=None, limit=FRAME_HZ * 60 * 5):
    """Play one song from silence.  Stops `frames` in, or once nothing is
    sounding any more, or at `limit`.  Returns the driver."""
    d = Driver(bank)
    d.play(song)
    while d.frame < (frames if frames is not None else limit):
        d.run(1)
        if frames is None and not d.busy():
            break
    return d
