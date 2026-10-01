#!/usr/bin/env python3
"""sega_mod.py - the Mega Drive Dune II's sounds as General Sound modules.

    sega_mod.py [--rom orig/dune2.gen] [--list src/res/sega_sound.txt]
                [--out src/res/prebuilt] [--only NAME ...] [--report]
                [--share SEMITONES]

Reads `src/res/sega_sound.txt` and writes one ProTracker module for each
line: `music/NAME.mod` or `sfx/NAME.mod`, plus `report.txt` beside them
saying what each conversion kept, merged and lost.

## From what the chips were told, not from a recording

A recording has every voice baked into one waveform and cannot be taken
apart again.  This works from the song data instead: `sega_driver.py`
plays each song through a model of the cartridge's own Z80 driver, which
says which note starts on which chip channel when, with which instrument,
pitch and attenuation, and when it is keyed off.  The rest follows from
that:

- **The instruments become samples.**  An FM instrument is rendered
  through the Genesis core's own YM2612 (`bin/gen/chiprender`, the Nuked
  OPN2) by writing exactly the registers the driver writes for a note -
  `$22`, `$27` on FM3, `$B0`, `$B4`, the four operators in the order
  +0 +8 +4 +C, the frequency, the key-on mask - and holding the key for as
  long as the song ever holds it.  A PSG instrument is the chip's square
  or noise shaped by the driver's own software envelope (L0066), frame by
  frame.  A DAC instrument is the cartridge's sample, as it is.
- **A sample covers three octaves.**  A tracker plays a sample only over
  C-1..B-3, so an instrument whose notes span more gets one sample per
  36-note band, each recorded at its band's middle.  Every sample is
  recorded so that one note plays at C-2 (8287 Hz), and its attack and
  decay come first, then a loop cut on a whole number of periods of the
  sustain.  A sound that has died away inside the longest note the song
  plays is left without a loop.
- **Each tune renders its own instruments.**  SHARE_TOL is -1: every
  song gets samples recorded for the notes it plays and held for as long
  as it holds them, and no tune shares a sample with another.  The card
  does not hold them all at once; `tools/dune_sound.py` packs them and
  `src/gs.asm` streams each to the card when it is wanted.  Sharing is
  still here (`Sharing`, `--share N`): songs that play one instrument
  within N semitones of the same recording pitch then get the very same
  sample, held for the longest any of them holds a note, each keeping its
  own release.
- **The channels become four.**  The driver sounds up to eleven (six FM,
  three tone, noise, the DAC).  Each note goes to a tracker channel: the
  one its track last used if that is free, else a free one, else the one
  whose track matters least - by how much of the song the track sounds -
  and only if that is less than its own.  What was kept, moved and dropped
  is written down per track.
- **Time becomes rows.**  The music clock ticks `step / 256` times a frame
  (L0E1D), so a song's ticks come at `50 * step / 256` a second.  A row
  is R ticks and a tick is k tracker ticks, `speed = R * k` and
  `BPM = 2.5 * k * ticks a second`: the tempo is exact to the BPM's
  rounding, and a note between rows is placed with `EDx`.  R is the
  smallest that fits the module into 64 patterns; the song's loop -
  every track in this game repeats with `loop 127` - becomes a `Bxx` back
  to the pattern it began at.
- **Loudness is the driver's.**  Attenuation turns an FM note's carriers
  down (L15F7: `TL + a (127 - TL) / 128`), so a note's volume is the
  carriers' amplitude after that over before it; PSG and the DAC ignore
  attenuation, as the driver does.  A key-off becomes a volume slide as
  long as the instrument's own release, or a cut if that is shorter than a
  tick.
- **Pitch envelopes become slides.**  The driver bends a voice's notes in
  1/256 semitones a tick; each row carries a `1xx` or `2xx` that lands the
  tracker's period where the bend is at the row's end.

An effect is rendered whole instead - every channel of it, through the
same chip models - into one sample played once, at C-3 (16574 Hz), or at
the note nearest its own rate if it is only a DAC sample.

## General Sound

The modules are 4-channel "M.K.": what the card's ROM plays (`$30` load,
`$31` play; `tools/modlib.py` has what its effect tables accept).
`tools/gs_modtest.py FILE.mod` plays one on the emulated card.
"""

import argparse
import math
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import modlib  # noqa: E402
from sega_driver import Bank, play, FRAME_HZ, CARRIERS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
CHIPRENDER = ROOT / "bin/gen/chiprender"

# The cartridge is the European one (region "E" at $1F0) and the core runs
# it as a PAL machine: 50 frames a second, the YM2612 at 53.203424 MHz / 7
# and the PSG at / 15.  The sound test agrees - the driver streams a
# nibble-5 sample at 202 bytes a frame, which is 10 kHz only at 50 frames.
YM_RATE = 7600489 / 144            # the YM2612's output rate
PSG_CLOCK = 3546893
FRAME = YM_RATE / FRAME_HZ         # chip samples a frame

# the two banks the game installs with command $0B
BANKS = {"game": (0x0FE25A, 0x0FE129, 0x0F6307, 0x0D0663),
         "front": (0x0D0252, 0x0D01F5, 0x0CF914, 0x0C8104)}

# $116A: the FM frequency numbers of one octave, and the next C
FM_TABLE = [644, 682, 723, 766, 811, 859, 910, 965, 1022, 1083, 1147, 1215,
            1288]
# $1184: PSG periods from note $21 up
PSG_TABLE = [1017, 960, 906, 855, 807, 762, 719, 679, 641, 605, 571, 539,
             508, 480, 453, 428, 404, 381, 360, 339, 320, 302, 285, 269,
             254, 240, 226, 214, 202, 190, 180, 170, 160, 151, 143, 135,
             127, 120, 113, 107, 101, 95, 90, 85, 80, 76, 71, 67,
             64, 60, 57, 53, 50, 47, 45, 42, 40, 38, 35, 33,
             32, 30, 28, 28, 0, 0]
PSG_LOW = 0x21

# What the core makes of each source at full scale (chiprender and
# core/sound/psg.c): one FM channel or the DAC swing +-8400, a PSG square
# 0..4200 (2800 at the default 150% preamp).
PSG_AMP = 4200
DAC_STEP = 66                       # 8448 / 128

REF = 12                            # C-2: the note a sample is recorded for
REF_RATE = modlib.rate_of(REF)      # 8287 Hz
SFX_NOTE = 24                       # C-3
SFX_RATE = modlib.rate_of(SFX_NOTE)
BAND = 36                           # C-1..B-3
MAX_SAMPLE = 16384                  # bytes a music sample may have
MAX_HOLD = 3.0                      # seconds a note is rendered held for
# Semitones a shared sample may be recorded off a song's own pitch
# (Sharing).  -1, the choice: nothing shared, every tune its own samples
# (the port streams them to the card one at a time, .claude/docs/sound.md).
# 0 shares samples at exactly the same pitch, 1 within a semitone (the
# port's earlier layout, which kept every tune on the card at once).
# Change it, then `make sega` to make the modules again.
SHARE_TOL = -1
RELEASE = 1.5                       # seconds rendered after key-off


# ------------------------------------------------------------------ pitch
def split(p):
    """8.8 semitones -> (note, fraction 0..255), as L10AA takes them."""
    n = int(math.floor(p))
    return n, int(round((p - n) * 256)) & 0xFF


def fm_fnum(p):
    """L10AA for FM: (block, fnum)."""
    n, f = split(p)
    i = n % 12
    return n // 12, FM_TABLE[i] + (f * (FM_TABLE[i + 1] - FM_TABLE[i])) // 256


def fm_hz(p):
    block, val = fm_fnum(p)
    return val * YM_RATE * 2 ** (block - 1) / 2 ** 20


def psg_period(p):
    """L10AA for the PSG: the 10-bit period."""
    n, f = split(p)
    i = n - PSG_LOW
    if i < 0:
        i, f = 0, 0
    a, b = PSG_TABLE[i], PSG_TABLE[i + 1]
    return max(1, a + math.floor(f * (b - a) / 256))


def psg_hz(period):
    return PSG_CLOCK / (32 * period)


# ------------------------------------------------------------------- FM
def fm_code(ch):
    return ch % 3 + (4 if ch >= 3 else 0)


def fm_tls(inst, att):
    """The four TLs in list order (+0 +8 +4 +C) after L15F7."""
    mask = CARRIERS[inst[3] & 7]
    out = []
    for i, b in enumerate((6, 18, 12, 24)):
        tl = inst[b] & 0x7F
        if mask >> i & 1:
            tl = min(127, tl + (att * (127 - tl)) // 128)
        out.append(tl)
    return out


def att_factor(inst, att):
    """How much quieter attenuation `att` makes an FM note: the carriers'
    summed amplitude after L15F7 over before it."""
    if inst[0] != 0 or not att:
        return 1.0
    mask = CARRIERS[inst[3] & 7]
    before, after = fm_tls(inst, 0), fm_tls(inst, att)
    amp = lambda tl: 10 ** (-0.75 * tl / 20)  # noqa: E731
    num = sum(amp(after[i]) for i in range(4) if mask >> i & 1)
    den = sum(amp(before[i]) for i in range(4) if mask >> i & 1)
    return num / den if den else 1.0


def fm_note_writes(ch, inst, att):
    """The driver's note-on, register by register (L1431, L1485), bar the
    frequency and the key-on.  Pan is forced to both sides: the card has
    no stereo to put a left-only instrument on."""
    part, c = ch // 3, ch % 3
    w = []
    if inst[1] & 0x08:
        w.append((0, 0x22, inst[1]))
    if ch == 2:
        w.append((0, 0x27, (inst[2] & 0xC0) | 0x05))
    w.append((part, 0xB0 + c, inst[3]))
    w.append((part, 0xB4 + c, (inst[4] & 0x3F) | 0xC0))
    tls = fm_tls(inst, att)
    for i, (off, first) in enumerate(((0, 5), (8, 17), (4, 11), (0xC, 23))):
        regs = inst[first:first + 6]
        w.append((part, 0x30 + off + c, regs[0]))
        w.append((part, 0x40 + off + c, tls[i]))
        for k, r in enumerate((0x50, 0x60, 0x70, 0x80), 2):
            w.append((part, r + off + c, regs[k]))
        w.append((part, 0x90 + off + c, 0))
    return w


def fm_freq_writes(ch, inst, p):
    part, c = ch // 3, ch % 3
    if ch == 2 and inst[2] & 0x40:
        return [(0, r, inst[29 + i]) for i, r in
                enumerate((0xA6, 0xA2, 0xAC, 0xA8, 0xAD, 0xA9, 0xAE, 0xAA))]
    block, val = fm_fnum(p)
    return [(part, 0xA4 + c, block << 3 | val >> 8),
            (part, 0xA0 + c, val & 0xFF)]


def fm_key(ch, inst=None):
    """$28: the key-on of the record's operators, or all of them off."""
    return (0, 0x28, ((inst[37] & 15) << 4 if inst else 0) | fm_code(ch))


class Script:
    """A chiprender register script, from writes at times in chip samples.
    Every write costs chiprender two samples, which are taken off the
    wait before the next one so the times hold."""

    def __init__(self):
        self.w = []

    def at(self, t, writes):
        for i, x in enumerate(writes):
            self.w.append((t, len(self.w), x))

    def render(self, length):
        lines, cur = [], 0
        for t, _, (part, reg, val) in sorted(self.w):
            if t > cur:
                n = int(round(t - cur))
                if n > 0:
                    lines.append(f"run {n}")
                    cur += n
            lines.append(f"w {part} {reg:x} {val:x}")
            cur += 2
        if length > cur:
            lines.append(f"run {int(length - cur)}")
        out = subprocess.run([CHIPRENDER],
                             input=("\n".join(lines) + "\n").encode(),
                             capture_output=True, check=True).stdout
        a = np.frombuffer(out, dtype="<i2")
        return a.reshape(-1, 2).astype(np.float64).mean(axis=1)


def fm_note(inst, p, hold, release=RELEASE):
    """One FM note held `hold` seconds then released: (held, released) at
    the chip's rate, from the key-on."""
    ch = 2 if inst[2] & 0x40 else 0
    s = Script()
    setup = fm_note_writes(ch, inst, 0) + fm_freq_writes(ch, inst, p)
    s.at(0, [fm_key(ch)] + setup)
    t_on = 2 * (len(setup) + 1) + 16
    s.at(t_on, [fm_key(ch, inst)])
    t_off = t_on + 2 + int(hold * YM_RATE)
    s.at(t_off, [fm_key(ch)])
    a = s.render(t_off + 2 + release * YM_RATE)
    return a[t_on + 2:t_off], a[t_off:]


# ------------------------------------------------------------------ PSG
class PSGEnv:
    """L0066, one channel: the software envelope, run once a frame.  The
    level is an 8-bit attenuation, $00 loud and $FF silent; the chip gets
    its top nibble."""

    def __init__(self, inst):
        self.attack, self.sustain = inst[2], inst[3] << 4 & 0xFF
        self.peak, self.decay, self.rel = inst[4] << 4 & 0xFF, inst[5], inst[6]
        self.level, self.phase = 0xFF, 0
        self.req = 0

    def frame(self):
        r, self.req = self.req, 0
        if r & 4:
            self.level, self.phase = 0xFF, 0
        if r & 2 and self.phase:
            self.phase = 4
        if r & 1:
            self.level, self.phase = 0xFF, 1
        if self.phase == 1:
            a = self.level - self.attack
            if a <= 0 or a <= self.peak:
                self.level, self.phase = self.peak, 2
            else:
                self.level = a
        elif self.phase == 2:
            if self.level == self.sustain:
                self.phase = 3
            elif self.level < self.sustain:
                a = self.level + self.decay
                if a > 0xFF or a >= self.sustain:
                    self.level, self.phase = self.sustain, 3
                else:
                    self.level = a
            else:
                a = self.level - self.decay
                if a < 0 or a <= self.sustain:
                    self.level, self.phase = self.sustain, 3
                else:
                    self.level = a
        elif self.phase == 4:
            a = self.level + self.rel
            if a > 0xFF:
                self.level, self.phase = 0xFF, 0
            else:
                self.level = a
        return self.level >> 4


def psg_amp(att):
    return 0.0 if att >= 15 else PSG_AMP * 10 ** (-2 * att / 20)


class PSGWave:
    """The chip's tone or noise generator, sample by sample at the YM
    rate, for levels that change once a frame."""

    def __init__(self):
        self.phase = 0.0
        self.lfsr = 0x8000
        self.out = 0

    def tone(self, n, hz, amp):
        t = self.phase + np.arange(n) * hz / YM_RATE
        self.phase = (self.phase + n * hz / YM_RATE) % 1.0
        return np.where(t % 1.0 < 0.5, amp / 2, -amp / 2)

    def noise(self, n, hz, amp, white):
        out = np.empty(n)
        step = hz / YM_RATE
        for i in range(n):
            self.phase += step
            while self.phase >= 1.0:
                self.phase -= 1.0
                bit = self.lfsr & 1
                fb = (bit ^ (self.lfsr >> 3 & 1)) if white else bit
                self.lfsr = self.lfsr >> 1 | fb << 15
                self.out = bit
            out[i] = amp / 2 if self.out else -amp / 2
        return out


def noise_hz(inst, p):
    """The noise shift rate: N/512, N/1024, N/2048, or tone 2's pitch."""
    r = inst[1] & 3
    if r == 3:
        return psg_hz(psg_period(p))
    return PSG_CLOCK / (32 * (16 << r))


def psg_note(inst, p, hold, release=RELEASE):
    """One PSG note, like fm_note: the envelope keyed on, then released."""
    env, wave = PSGEnv(inst), PSGWave()
    env.req = 1
    frames_on = max(1, int(round(hold * FRAME_HZ)))
    frames_off = int(release * FRAME_HZ)
    parts, cut = [], 0
    carry = 0.0
    for f in range(frames_on + frames_off):
        if f == frames_on:
            env.req |= 2
            cut = sum(len(x) for x in parts)
        att = env.frame()
        carry += FRAME
        n = int(carry)
        carry -= n
        if inst[0] == 3:
            parts.append(wave.noise(n, noise_hz(inst, p), psg_amp(att),
                                    inst[1] & 4))
        else:
            parts.append(wave.tone(n, psg_hz(psg_period(p)), psg_amp(att)))
    a = np.concatenate(parts)
    return a[:cut], a[cut:]


# ------------------------------------------------------------ resampling
def resample(x, sr, rate):
    """Band-limited: through the spectrum, cut at the lower Nyquist."""
    n = len(x)
    if n == 0:
        return x
    m = max(1, int(round(n * rate / sr)))
    X = np.fft.rfft(x)
    k = min(len(X), m // 2 + 1)
    Y = np.zeros(m // 2 + 1, dtype=complex)
    Y[:k] = X[:k]
    return np.fft.irfft(Y, m) * (m / n)


def rms_env(x, w):
    n = len(x) // w
    if not n:
        return np.zeros(0)
    return np.sqrt((x[:n * w].reshape(n, w) ** 2).mean(axis=1))


# --------------------------------------------------------------- samples
class Made:
    """A sample ready for the module, before its volume is known: float
    data at its rate, the peak it had, its loop, and how long its release
    lasts (None: it never ends)."""

    def __init__(self, name, data, peak, loop=None, release=0.0):
        self.name, self.data, self.peak = name, data, peak
        self.loop, self.release = loop, release


def cut_note(held, rel, f0, name, rate=REF_RATE, max_len=MAX_SAMPLE):
    """A rendered note -> a tracker sample: the attack and decay, then a
    loop over whole periods of the sustain, or nothing if it has died."""
    x = resample(held, YM_RATE, rate)
    r = resample(rel, YM_RATE, rate) if len(rel) else rel
    peak = float(np.abs(x).max()) if len(x) else 0.0
    if peak < 1:
        return Made(name, np.zeros(2), 0.0)
    w = max(16, int(rate / 100))
    env = rms_env(x, w)
    thr = peak * 10 ** (-48 / 20)
    loud = np.nonzero(env > thr)[0]
    last = (loud[-1] + 1) * w if len(loud) else 0
    level_off = float(env[-1]) if len(env) else 0.0
    release = release_time(r, rate, level_off)
    if last < len(x) - 2 * w or f0 is None and last < len(x) - 2 * w:
        return Made(name, x[:min(last, max_len)], peak, None, release)
    # a sustain: where the level stops moving
    final = env[-max(1, len(env) // 10):].mean()
    settle = len(env) - 1
    while settle > 0 and abs(20 * math.log10(max(env[settle - 1], 1e-9) /
                                              max(final, 1e-9))) < 1.5:
        settle -= 1
    start = max(settle * w, int(0.03 * rate))
    period = rate / f0 if f0 else 1024
    best = None
    for k in range(1, 400):
        L = k * period
        if L > 4096 or (best and L > 1024 and best[0] < 0.02):
            break
        if L < 256:
            continue
        err = abs(L - round(L))
        if best is None or err < best[0] - 1e-9:
            best = (err, int(round(L)))
    L = best[1] if best else int(round(period))
    if len(x) < L + 2 * w:
        # held too briefly to show a sustain: loop what there is
        L = min(L, len(x) - (len(x) % 2))
    start = max(0, min(start, len(x) - L, max_len - L))
    end = start + L
    data = x[:end].copy()
    cf = min(64, start, L // 4)
    if cf:
        fade = np.linspace(0, 1, cf)
        data[end - cf:end] = (data[end - cf:end] * (1 - fade)
                              + x[start - cf:start] * fade)
    return Made(name, data, peak, (start, L), release)


def release_time(r, rate, level):
    """Seconds after key-off until the note is 40 dB under where it was;
    None if it never gets there."""
    if level <= 0 or not len(r):
        return 0.0
    w = max(16, int(rate / 200))
    env = rms_env(r, w)
    quiet = np.nonzero(env < level * 0.01)[0]
    if not len(quiet):
        return None
    return quiet[0] * w / rate


def psg_release_time(inst):
    rel, sus = inst[6], inst[3] << 4 & 0xFF
    if not rel:
        return None
    return math.ceil((0xFF - sus) / rel) / FRAME_HZ


def dac_data(bank, k, rate_nib):
    fl, addr, ln = bank.samples[k]
    raw = np.frombuffer(bank.rom[addr:addr + ln], dtype=np.uint8)
    nib = rate_nib if rate_nib != 4 else fl & 0x0F
    return (raw.astype(np.float64) - 128) * DAC_STEP, YM_RATE / (nib or 1)


def nearest_note(rate):
    i = round(12 * math.log2(rate / modlib.rate_of(0)))
    return max(0, min(35, i))


# ---------------------------------------------------------- the sessions
class Session:
    """One note on one chip channel, from its key-on to whatever ends it."""

    def __init__(self, e):
        self.ch = e.ch
        self.chan = (e.ch.kind, e.ch.n)
        self.voice, self.track = e.voice, e.track
        self.inst, self.inst_no = e.inst, e.inst_no
        self.note, self.att = e.note, e.att
        self.t_on = e.pos
        self.t_off = None
        self.t_end = None
        self.pitches = [(e.pos, e.pitch)]
        self.sample, self.rate = e.sample, e.rate
        self.smp = None             # (module sample number, base, base_idx)

    kind = property(lambda s: s.ch.kind)

    def pitch_at(self, t):
        p = self.pitches[0][1]
        for tt, pp in self.pitches:
            if tt > t:
                break
            p = pp
        return p


def sessions(d, end):
    out, open_ = [], {}
    for e in d.events:
        key = (e.ch.kind, e.ch.n)
        s = open_.get(key)
        if e.kind == "on":
            if s:
                s.t_end = e.pos
            s = open_[key] = Session(e)
            out.append(s)
        elif s is None:
            continue
        elif e.kind == "off":
            if s.t_off is None:
                s.t_off = e.pos
        elif e.kind in ("cut", "end"):
            s.t_end = e.pos
            del open_[key]
        elif e.kind == "pitch":
            s.pitches.append((e.pos, e.pitch))
    out = [s for s in out if s.t_on < end]
    for s in out:
        if s.t_end is None or s.t_end > end:
            s.t_end = end
        if s.t_off is not None and s.t_off > s.t_end:
            s.t_off = None
    return out


# ------------------------------------------------------------ the music
def song_window(d):
    """(loop start, loop end) in ticks, or (None, end of the sound)."""
    if d.loop_start and all(len(v) >= 2 for v in d.loops.values()) \
            and set(d.loops) == set(d.loop_start):
        start = max(d.loop_start.values())
        period = 1
        for v in d.loops.values():
            period = math.lcm(period, int(round(v[1] - v[0])))
        return int(round(start)), int(round(start)) + period
    return None, int(math.ceil(d.pos)) + 1


def run_song(bank, song):
    """Play a song until it has looped twice, or has stopped."""
    d = play(bank, song, frames=0)
    limit = FRAME_HZ * 60 * 12
    while d.frame < limit:
        d.run(50)
        looping = [v for v in d.voices if v.n in d.loop_start]
        if d.loop_start and all(len(d.loops.get(v.n, [])) >= 2
                                for v in looping) \
                and not any(v.active for v in d.voices
                            if v.n not in d.loop_start):
            break
        if not d.busy():
            d.run(50)
            break
    return d


_audible = {}


def audible(inst):
    """Seconds a note of this instrument can be heard for when the key is
    held: until it is 40 dB under its peak, or None for as long as it is
    held.  A channel whose note has died is free, whatever its gate says."""
    key = bytes(inst)
    if key in _audible:
        return _audible[key]
    t = None
    if inst[0] == 0:
        held, _ = fm_note(inst, 0x30, MAX_HOLD, release=0)
        env = rms_env(held, 256)
        if len(env) and env.max() > 0:
            loud = np.nonzero(env > env.max() * 0.01)[0]
            if loud[-1] < len(env) - 4:
                t = (loud[-1] + 1) * 256 / YM_RATE
        else:
            t = 0.0
    elif inst[0] in (2, 3) and (inst[3] & 15) == 15:
        env, f = PSGEnv(inst), 0
        env.req = 1
        while f < MAX_HOLD * FRAME_HZ and (env.frame() < 15 or f == 0):
            f += 1
        t = f / FRAME_HZ
    _audible[key] = t
    return t


def assign(sess, tps, order=None, nch=4):
    """Sessions -> tracker channels.  Returns ({session: channel}, what
    happened to each track's notes, the tracks' weights).

    A track weighs its notes plus a quarter of the ticks it sounds; DAC
    notes count double, because a drum dropped is missed more than a pad.
    `order`, from the list file, overrides that: the tracks it names come
    first, in its order."""
    weight = Counter()
    for s in sess:
        end = s.t_off if s.t_off is not None else s.t_end
        weight[s.track] += (2 if s.kind == "dac" else 1) + \
            max(1, min(48, end - s.t_on)) / 4
    if order:
        top = max(weight.values()) + 1
        for i, t in enumerate(order):
            weight[t] = top * (len(order) - i + 1)

    def heard_until(b):
        if b.kind == "dac":
            return b.t_end
        end = b.t_off if b.t_off is not None else b.t_end
        a = audible(b.inst)
        return end if a is None else min(end, b.t_on + a * tps)

    busy = [None] * nch             # the session on each channel
    last = [None] * nch             # the track that used it last
    placed, stats = {}, defaultdict(Counter)
    for s in sorted(sess, key=lambda s: (s.t_on, -weight[s.track])):
        def free(c):
            b = busy[c]
            return b is None or heard_until(b) <= s.t_on
        cands = [c for c in range(nch) if free(c)]
        if cands:
            mine = [c for c in cands if last[c] == s.track]
            c = mine[0] if mine else min(
                cands, key=lambda c: (weight[last[c]] if last[c] is not None
                                      else -1))
            stats[s.track]["kept" if mine or last[c] is None
                           else "moved"] += 1
        else:
            c = min(range(nch), key=lambda c: weight[busy[c].track])
            if weight[busy[c].track] >= weight[s.track]:
                stats[s.track]["dropped"] += 1
                continue
            b = busy[c]
            b.t_end = min(b.t_end, s.t_on)
            stats[b.track]["cut short"] += 1
            stats[s.track]["stole"] += 1
        busy[c], last[c] = s, s.track
        placed[s] = c
    return placed, stats, weight


def sample_groups(placed, tps):
    """The placed sessions by the sample they need: [(key, sessions, hold,
    bands)], the most used first.  `key` is ("dac", sample, rate nibble),
    ("noise", instrument) or ("pitched", instrument); `hold` the longest
    the song holds a note of it (seconds, 0.25-MAX_HOLD); `bands` for a
    pitched one the 36-note bands its notes need, as (lowest note,
    highest, base), the base being the note that plays at C-1, chosen to
    put the song's notes in the middle."""
    groups = defaultdict(list)
    for s in placed:
        if s.kind == "dac":
            groups[("dac", s.sample, s.inst[1])].append(s)
        elif s.inst[0] == 3 and s.inst[1] & 3 != 3:
            groups[("noise", bytes(s.inst))].append(s)
        else:
            groups[("pitched", bytes(s.inst))].append(s)
    out = []
    for key, ss in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        hold = 0.0
        for s in ss:
            end = s.t_off if s.t_off is not None else s.t_end
            hold = max(hold, (end - s.t_on) / tps)
        hold = min(MAX_HOLD, max(0.25, hold + 0.02))
        bands = None
        if key[0] == "pitched":
            notes = sorted({int(round(p)) for s in ss
                            for _, p in s.pitches[:1]})
            lo, hi = notes[0], notes[-1]
            bands, a = [], lo
            while a <= hi:
                span = [n for n in notes if a <= n < a + BAND]
                b_lo, b_hi = span[0], span[-1]
                base = b_lo - (BAND - 1 - (b_hi - b_lo)) // 2  # at C-1
                bands.append((b_lo, b_hi, base))
                a = b_lo + BAND
        out.append((key, ss, hold, bands))
    return out


_renders = {}


def render_sample(inst, kind, base, hold, name):
    """One instrument's note rendered and cut into a sample: a pitched one
    recorded so that note `base` plays at C-1, a noise one as it is.
    Renders are kept, so asking twice costs nothing."""
    k = (kind, bytes(inst), base, hold)
    if k not in _renders:
        if kind == "noise":
            held, rel = psg_note(inst, 0x40, hold)
            m = cut_note(held, rel, None, name)
            if m.release is not None:
                m.release = psg_release_time(inst)
        else:
            ref = base + REF                   # recorded to play at C-2
            if inst[0] == 0:
                held, rel = fm_note(inst, ref, hold)
                f0 = None if inst[2] & 0x40 else fm_hz(ref)
            else:
                held, rel = psg_note(inst, ref, hold)
                f0 = psg_hz(psg_period(ref))
                if inst[0] == 3 and inst[1] & 4:
                    f0 = None
                elif inst[0] == 3:
                    f0 = f0 / 16
            m = cut_note(held, rel, f0, name)
            if inst[0] != 0:
                m.release = psg_release_time(inst)
        _renders[k] = m
    m = _renders[k]
    return Made(name, m.data, m.peak, m.loop, m.release)


class Sharing:
    """Which songs can play one rendering of an instrument between them.

    Used only with SHARE_TOL >= 0 (the port's choice is -1: nothing
    shared).  Every song renders the instruments it plays for itself, held
    for as long as it holds them and recorded in the middle of the notes it
    plays.  Most instruments are played by several songs - 66 in the 20
    tunes' 183 samples - and a store that keeps each distinct sample once
    pays nothing the second time for a sample two songs agree on.  Two
    songs agree when:

    - the instrument is the same (its bytes, whichever bank);
    - a pitched one's bases are at most SHARE_TOL semitones from a common
      base that still puts every note of both into C-1..B-3.  The shared
      sample is recorded there; a song's notes then play at most
      SHARE_TOL semitones further from where they were recorded than its
      own band would have had them - against the up to two octaves the
      band itself allows;
    - the render is held for the longest either holds a note.  Up to the
      shorter song's key-off the two renders are the same sound; after it
      the tracker fades the note over its own release, which is still
      worked out from the song's own hold.

    `need` is told every song's groups first (pass 1), `resolve` settles
    the shared bases and holds, and `made` gives a song its samples."""

    def __init__(self, tol):
        self.tol = tol
        self.needs = defaultdict(list)   # key -> [(tag, band, hold)]
        self.where = {}                  # (key, tag, band) -> (base, hold)
        self.users = Counter()           # (key, base, hold) -> songs

    def need(self, tag, groups):
        for key, ss, hold, bands in groups:
            if key[0] == "dac":
                continue                 # a DAC sample is the same anyway
            for band in bands or [None]:
                self.needs[key].append((tag, band, hold))

    def common(self, c):
        """The base a cluster of bands can share, or None."""
        bases = [b[2] for _, b, _ in c]
        lo = max(max(bases) - self.tol,
                 max(b[1] for _, b, _ in c) - (BAND - 1))
        hi = min(min(bases) + self.tol, min(b[0] for _, b, _ in c))
        if lo > hi:
            return None
        return max(lo, min(hi, int(math.floor(sum(bases) / len(bases)
                                              + 0.5))))

    def resolve(self):
        for key, v in self.needs.items():
            if key[0] == "noise":
                clusters = [(None, v)]
            else:
                clusters, cur = [], []
                for x in sorted(v, key=lambda x: (x[1][2], x[1][0], x[0])):
                    if cur and self.common(cur + [x]) is not None:
                        cur.append(x)
                    else:
                        if cur:
                            clusters.append((self.common(cur), cur))
                        cur = [x]
                clusters.append((self.common(cur), cur))
            for base, c in clusters:
                hold = max(h for _, _, h in c)
                for tag, band, _ in c:
                    self.where[(key, tag, band)] = (base, hold)
                self.users[(key, base, hold)] += len({t for t, _, _ in c})

    def made(self, key, inst, tag, band, own_hold, name):
        """(the base the sample is recorded at, the Made): the shared
        render's sound with the song's own release."""
        own_base = band[2] if band else None
        base, hold = self.where.get((key, tag, band), (own_base, own_hold))
        own = render_sample(inst, key[0], own_base, own_hold, name)
        m = render_sample(inst, key[0], base, hold, name)
        return base, Made(name, m.data, m.peak, m.loop, own.release)


def instrument_samples(bank, placed, tps, song, share=None):
    """The samples the placed sessions need, made, and each session told
    which one it plays and how its notes map to tracker notes.  With
    `share` (a resolved Sharing), a sample may be one another song plays
    too."""
    song_tag = song[:8]
    made = []
    for key, ss, hold, bands in sample_groups(placed, tps):
        if key[0] == "dac":
            data, rate = dac_data(bank, key[1], key[2])
            idx = nearest_note(rate)
            data = resample(data, rate, modlib.rate_of(idx))
            m = Made(f"{song_tag} dac {key[1]}", data,
                     float(np.abs(data).max() or 1))
            made.append(m)
            for s in ss:
                s.smp = (len(made), None, idx)
            continue
        inst = ss[0].inst
        label = f"{song_tag} i{ss[0].inst_no}"
        if key[0] == "noise":
            if share:
                _, m = share.made(key, inst, song, None, hold, label)
            else:
                m = render_sample(inst, "noise", None, hold, label)
            made.append(m)
            for s in ss:
                s.smp = (len(made), None, REF)
            continue
        for band in bands:
            b_lo, b_hi, base = band
            name = f"{label} {b_lo}-{b_hi}"
            if share:
                base, m = share.made(key, inst, song, band, hold, name)
            else:
                m = render_sample(inst, "pitched", base, hold, name)
            made.append(m)
            for s in ss:
                if b_lo <= int(round(s.pitches[0][1])) <= b_hi:
                    s.smp = (len(made), base, 0)
    return made


class Chan:
    """What the tracker's player will be doing on one channel, so the
    next row's effect can be worked out from it."""

    def __init__(self):
        self.period = None
        self.vol = 0
        self.fade = 0               # volume a tick, while releasing
        self.s = None


def period_of(s, p):
    """The ideal Amiga period for pitch p on session s's sample."""
    _, base, _ = s.smp
    return modlib.PAL_CLOCK / (modlib.rate_of(0) * 2 ** ((p - base) / 12))


class Placed:
    """A song played through the driver model and its notes put on four
    channels: what both passes over the music need."""

    def __init__(self, bank, song, order=None):
        d = self.d = run_song(bank, song)
        self.loop_s, self.end = song_window(d)
        sess = sessions(d, self.end)
        self.steps = d.tempo_changes
        self.tps_first = self.steps[0][2] * FRAME_HZ / 256
        self.silent = [s for s in sess if s.kind == "fm"
                       and att_factor(s.inst, s.att) < 1 / 128]
        self.sess = [s for s in sess if s not in set(self.silent)]
        self.placed, self.stats, self.weight = assign(
            self.sess, self.tps_first, order)


def convert_music(bank, song, name, order=None, share=None, pl=None):
    pl = pl or Placed(bank, song, order)
    d, loop_s, end, steps = pl.d, pl.loop_s, pl.end, pl.steps
    sess, silent, tps_first = pl.sess, pl.silent, pl.tps_first
    placed, stats, weight = pl.placed, pl.stats, pl.weight
    tps_max = max(st for _, _, st in steps) * FRAME_HZ / 256
    k = max(1, int(255 // (2.5 * tps_max)))
    made = instrument_samples(bank, placed, tps_first, name, share)
    report = [f"music {name}: bank song {song}, {len(sess)} notes, "
              f"{d.pos:.0f} ticks played"]
    if silent:
        report.append(f"  {len(silent)} notes attenuated past hearing, "
                      "left out")
    if len(made) > modlib.MAX_SAMPLES:
        # keep the samples that play the most notes
        use = Counter(s.smp[0] for s in placed)
        keep = {i for i, _ in use.most_common(modlib.MAX_SAMPLES)}
        report.append(f"  {len(made)} samples, {len(made) - len(keep)} "
                      "of the least used dropped")
        placed = {s: c for s, c in placed.items() if s.smp[0] in keep}
        remap = {old: new for new, old in enumerate(sorted(keep), 1)}
        made = [made[i - 1] for i in sorted(keep)]
        for s in placed:
            s.smp = (remap[s.smp[0]],) + s.smp[1:]
    # The loudest note any sample is *played* at sets the scale: a sample's
    # raw peak says nothing when the song only ever plays it turned down.
    # Each tracker channel has its own DAC on the card, so nothing is
    # summed and the loudest note can have the whole of 0..64.
    played = defaultdict(float)
    for s in placed:
        i = s.smp[0] - 1
        played[i] = max(played[i], made[i].peak * att_factor(s.inst, s.att))
    top = max(played.values()) or 1.0

    def vol_of(s):
        m = made[s.smp[0] - 1]
        return max(0, min(64, round(64 * m.peak
                                    * att_factor(s.inst, s.att) / top)))
    vols = [max(1, round(64 * played[i] / top)) for i in range(len(made))]

    # sample default volumes: the volume most of its notes play at
    common = defaultdict(Counter)
    for s in placed:
        common[s.smp[0]][vol_of(s)] += 1
    defaults = {i: c.most_common(1)[0][0] for i, c in common.items()}

    # rows: R ticks, k tracker ticks a music tick
    for R in range(1, 32 // k + 1):
        if loop_s is not None and (loop_s % R or (end - loop_s) % R):
            continue
        mod = build_patterns(placed, made, defaults, vol_of, steps, k, R,
                             loop_s, end)
        if mod and len(mod[0]) <= modlib.MAX_PATTERNS and \
                len(mod[1]) <= modlib.MAX_ORDERS:
            break
    else:
        raise SystemExit(f"{name}: no row length fits it into a module")
    patterns, orders, notes = mod
    samples = []
    for i, m in enumerate(made, 1):
        samples.append(to_sample(m, defaults.get(i, vols[i - 1])))
    bpms = sorted({bpm(st, k) for _, _, st in steps})
    report.append(f"  row {R} tick(s), speed {R * k}, BPM "
                  + "/".join(str(b) for b in bpms)
                  + (f", loops at tick {loop_s} every {end - loop_s}"
                     if loop_s is not None else ", plays once")
                  + f"; {len(patterns)} patterns, {len(orders)} orders")
    for t in sorted(weight, key=lambda t: -weight[t]):
        st = stats[t]
        report.append(f"  track {t}: " + ", ".join(
            f"{v} {k_}" for k_, v in sorted(st.items())))
    report.append(f"  {len(samples)} samples, "
                  f"{sum(len(s.data) for s in samples)} bytes; "
                  f"{notes['edx']} notes placed between rows, "
                  f"{notes['late']} moved onto a row to set their volume, "
                  f"{notes['lost']} lost to a busier row")
    expect = []
    for s, c in placed.items():
        smp, base, idx = s.smp
        if base is not None:
            idx = max(0, min(35, int(round(s.pitches[0][1])) - base))
        expect.append((int(round(s.t_on * k)), c, smp, idx))
    return samples, patterns, orders, report, (expect, R * k)


def replay(path):
    """A module's notes as a player meets them, once through from order 0
    until the order list's own end or its first jump back: [(tracker tick,
    channel, sample, note)].  Speed, EDx note delays, Dxx and Bxx are
    followed; the BPM does not matter to a count of ticks."""
    _, _, patterns, orders, _ = modlib.read(path)
    out, tick, speed, o, row, seen = [], 0, 6, 0, 0, set()
    while o < len(orders) and (o, row) not in seen:
        seen.add((o, row))
        cells = patterns[orders[o]][row]
        for c in cells:
            if c.fx == 0xF and 0 < c.arg < 32:
                speed = c.arg
        jump = None
        for ch, c in enumerate(cells):
            if c.note is not None:
                sub = c.arg & 15 if c.fx == 0xE and c.arg >> 4 == 0xD else 0
                out.append((tick + sub, ch, c.sample, c.note))
            if c.fx == 0xB:
                jump = (c.arg, 0)
            elif c.fx == 0xD and jump is None:
                jump = (o + 1, 0)
        tick += speed
        if jump is not None:
            if jump[0] <= o:
                break
            o, row = jump
        else:
            row += 1
            if row == modlib.ROWS:
                o, row = o + 1, 0
    return out


def check(path, expect, speed):
    """Every note the driver model placed, found in the written module at
    the tick, channel, sample and note it was placed at.  Returns a line
    for the report."""
    got = Counter(replay(path))
    exact = near = 0
    missing = []
    for e in expect:
        if got[e]:
            got[e] -= 1
            exact += 1
            continue
        t, c, smp, idx = e
        row0 = t - t % speed
        hit = next((g for g in got if got[g] and g[1:] == (c, smp, idx)
                    and row0 <= g[0] < row0 + speed), None)
        if hit:
            got[hit] -= 1
            near += 1
        else:
            missing.append(e)
    extra = sum(got.values())
    line = (f"  check: {exact} of {len(expect)} notes exactly where the "
            f"driver put them, {near} in the right row, {len(missing)} "
            f"missing, {extra} not asked for")
    return line, not extra and len(missing) <= len(expect) // 50


def bpm(step, k):
    """The BPM that makes k tracker ticks one music tick at this step."""
    return modlib.gs_bpm(256 / (step * FRAME_HZ) / k)


def to_sample(m, volume):
    d = m.data
    peak = float(np.abs(d).max()) if len(d) else 0
    pcm = np.zeros(len(d), dtype=np.int8) if not peak else \
        np.clip(np.round(d / peak * 127), -128, 127).astype(np.int8)
    pcm = pcm.tobytes()
    if m.loop:
        s, L = m.loop
        if s & 1:                   # MOD loops are counted in words
            pcm = b"\0" + pcm
            s += 1
        if L & 1:
            L -= 1
        return modlib.Sample(m.name, pcm, volume, s, L)
    return modlib.Sample(m.name, pcm, volume)


def build_patterns(placed, made, defaults, vol_of, steps, k, R, loop_s,
                   end):
    speed = R * k
    nrows = -(-end // R)
    rows = [[modlib.Cell() for _ in range(4)] for _ in range(nrows)]
    notes = Counter()
    by_ch = defaultdict(list)
    for s, c in placed.items():
        by_ch[c].append(s)

    def mt(t):                      # music ticks -> tracker ticks
        return int(round(t * k))

    for c, ss in by_ch.items():
        ss.sort(key=lambda s: s.t_on)
        ch = Chan()
        want = defaultdict(list)    # row -> [(prio, sub, what, session)]
        for s in ss:
            t = mt(s.t_on)
            want[t // speed].append((0, t % speed, "on", s))
            if s.kind == "dac":
                continue
            if s.t_off is not None:
                t = mt(s.t_off)
                want[t // speed].append((1, t % speed, "off", s))
            t = mt(s.t_end)
            want[t // speed].append((2, t % speed, "end", s))
        for r in range(nrows):
            cell = rows[r][c]
            acts = sorted(want.get(r, []), key=lambda a: (a[0], a[1]))
            ons = [a for a in acts if a[2] == "on"]
            if len(ons) > 1:
                notes["lost"] += len(ons) - 1
            if ons:
                _, sub, _, s = ons[0]
                smp, base, idx = s.smp
                if base is not None:
                    idx = int(round(s.pitches[0][1])) - base
                    idx = max(0, min(35, idx))
                cell.note, cell.sample = idx, smp
                v = vol_of(s)
                ch.s, ch.period, ch.vol, ch.fade = s, modlib.PERIODS[idx], \
                    v, 0
                if v != defaults.get(smp, 64) and (sub == 0 or abs(
                        v - defaults.get(smp, 64)) >= 4):
                    cell.fx, cell.arg = 0xC, v
                    if sub:
                        notes["late"] += 1
                elif sub:
                    cell.fx, cell.arg = 0xE, 0xD0 | min(15, sub)
                    notes["edx"] += 1
                continue
            s = ch.s
            if s is None:
                continue
            ends = [a for a in acts if a[3] is s and a[2] == "end"]
            offs = [a for a in acts if a[3] is s and a[2] == "off"]
            if ends and not (s.t_off is not None and ch.fade == 0
                             and not offs and ch.vol == 0):
                sub = ends[0][1]
                if ch.vol:
                    cell.fx, cell.arg = (0xE, 0xC0 | min(15, sub)) if sub \
                        else (0xC, 0)
                ch.s, ch.vol = None, 0
                continue
            if offs:
                rel = made[s.smp[0] - 1].release
                if rel is not None and ch.vol:
                    ticks = rel * tps_at(steps, s.t_off) * k
                    if ticks <= 1:
                        sub = offs[0][1]
                        cell.fx, cell.arg = (0xE, 0xC0 | min(15, sub)) \
                            if sub else (0xC, 0)
                        ch.vol = 0
                        continue
                    ch.fade = max(1, min(15, math.ceil(ch.vol / ticks)))
            # the pitch, where the bend has got to by the row's end
            if s.kind != "dac" and ch.period and speed > 1:
                p = s.pitch_at((r + 1) * R)
                target = max(113, min(856, period_of(s, p)))
                step = (ch.period - target) / (speed - 1)
                xx = min(255, int(round(abs(step))))
                if xx:
                    cell.fx, cell.arg = (1 if step > 0 else 2), xx
                    ch.period += (-1 if step > 0 else 1) * xx * (speed - 1)
                    ch.period = max(113, min(856, ch.period))
                    continue
            if ch.fade and ch.vol:
                cell.fx, cell.arg = 0xA, ch.fade
                ch.vol = max(0, ch.vol - ch.fade * (speed - 1))

    # the tempo: speed and BPM at row 0, BPM again wherever it changes
    glob = [(0, 0xF, speed)]
    for _, pos, st in steps:
        glob.append((int(pos) // R, 0xF, bpm(st, k)))
    # the patterns, the loop, and every global command given a column
    intro = loop_s // R if loop_s is not None else nrows
    chunks = []
    for a, b in ((0, intro), (intro, nrows)):
        for i in range(a, b, modlib.ROWS):
            chunks.append((i, min(b, i + modlib.ROWS)))
    chunks = [c for c in chunks if c[1] > c[0]]
    orders_of_row = {}
    for n, (a, b) in enumerate(chunks):
        orders_of_row[a] = n
    marks = []
    for n, (a, b) in enumerate(chunks):
        if b - a < modlib.ROWS and n + 1 < len(chunks):
            marks.append((b - 1, 0xD, 0))
    if loop_s is not None:
        marks.append((nrows - 1, 0xB, orders_of_row[intro]))
    else:
        marks.append((nrows - 1, 0xB, 0))
    for r, fx, arg in glob + marks:
        r = max(0, min(nrows - 1, r))
        row = rows[r]
        free = [c for c in range(4) if not row[c].fx and not row[c].arg]
        if not free:
            # a global command outranks a slide: take the last column's
            free = [3]
            notes["effects overridden"] += 1
        row[free[0]].fx, row[free[0]].arg = fx, arg
    patterns, orders, seen = [], [], {}
    for a, b in chunks:
        pat = rows[a:b] + [[modlib.Cell() for _ in range(4)]
                           for _ in range(modlib.ROWS - (b - a))]
        key = b"".join(c.pack() for row in pat for c in row)
        if key not in seen:
            seen[key] = len(patterns)
            patterns.append(pat)
        orders.append(seen[key])
    return patterns, orders, notes


def tps_at(steps, pos):
    st = steps[0][2]
    for _, p, s in steps:
        if p <= pos:
            st = s
    return st * FRAME_HZ / 256


# -------------------------------------------------------------- effects
def render_song(bank, song, seconds=20):
    """An effect, every channel of it, through the chip models: the FM
    through chiprender, the PSG and the DAC here.  Mono at the YM rate."""
    d = play(bank, song, limit=FRAME_HZ * seconds)
    frames = d.frame + int(RELEASE * FRAME_HZ)
    length = int(frames * FRAME) + 1
    out = np.zeros(length)
    # FM
    script, keyed = Script(), {}
    for e in d.events:
        if e.ch.kind != "fm":
            continue
        t = e.frame * FRAME
        ch = e.ch.n
        if e.kind == "on":
            w = [fm_key(ch)] if keyed.get(ch) else []
            w += fm_note_writes(ch, e.inst, e.att)
            w += fm_freq_writes(ch, e.inst, e.pitch)
            w.append(fm_key(ch, e.inst))
            script.at(t, w)
            keyed[ch] = e.inst
        elif e.kind == "pitch" and ch in keyed:
            script.at(t, fm_freq_writes(ch, keyed[ch], e.pitch))
        elif e.kind in ("off", "cut"):
            script.at(t, [fm_key(ch)])
            keyed[ch] = None if e.kind == "cut" else keyed.get(ch)
    if script.w:
        fm = script.render(length)
        out[:min(length, len(fm))] += fm[:length]
    # PSG: requests raised in a frame are seen by the next frame's L0066
    for kind, n in [("psg", 0), ("psg", 1), ("psg", 2), ("noise", 0)]:
        evs = [e for e in d.events if e.ch.kind == kind and e.ch.n == n]
        if not evs:
            continue
        wave, env, inst, p = PSGWave(), None, None, 0x40
        by_frame = defaultdict(list)
        for e in evs:
            by_frame[e.frame + 1].append(e)
        pos = 0
        for f in range(frames):
            for e in by_frame.get(f, []):
                if e.kind == "on":
                    old = env.level if env else 0xFF
                    inst, p = e.inst, e.pitch
                    env = PSGEnv(inst)
                    env.level = old
                    env.req = 1
                elif e.kind == "pitch":
                    p = e.pitch
                elif env and e.kind == "off":
                    env.req |= 2
                elif env and e.kind == "cut":
                    env.req |= 4
            a = int((f + 1) * FRAME) - pos
            if env:
                att = env.frame()
                if kind == "noise":
                    x = wave.noise(a, noise_hz(inst, p), psg_amp(att),
                                   inst[1] & 4)
                else:
                    x = wave.tone(a, psg_hz(psg_period(p)), psg_amp(att))
                out[pos:pos + a] += x[:len(out) - pos]
            pos += a
    # the DAC: a sample to its end, or until the next one
    evs = [e for e in d.events if e.ch.kind == "dac" and e.kind == "on"]
    dac_only = bool(evs) and all(e.ch.kind == "dac" for e in d.events)
    rates = set()
    for i, e in enumerate(evs):
        data, rate = dac_data(bank, e.sample, e.inst[1])
        rates.add(rate)
        x = resample(data, rate, YM_RATE)
        t0 = int(e.frame * FRAME)
        if i + 1 < len(evs):
            x = x[:max(0, int(evs[i + 1].frame * FRAME) - t0)]
        n = min(len(x), len(out) - t0)
        if n > 0:
            out[t0:t0 + n] += x[:n]
    rate = SFX_RATE
    note = SFX_NOTE
    if dac_only and len(rates) == 1:
        note = nearest_note(rates.pop())
        rate = modlib.rate_of(note)
    # trim the silence before and after
    env = rms_env(out, 256)
    peak = env.max() if len(env) else 0
    loud = np.nonzero(env > peak * 10 ** (-50 / 20))[0] if peak else []
    if not len(loud):
        return None, note, d
    out = out[loud[0] * 256:(loud[-1] + 1) * 256]
    return resample(out, YM_RATE, rate), note, d


def convert_sfx(bank, song, name):
    data, note, d = render_song(bank, song)
    if data is None:
        return None, [f"sfx {name}: song {song} is silent"]
    if len(data) & 1:
        data = np.append(data, 0.0)
    if len(data) > 0x1FFFE:
        data = data[:0x1FFFE]
    m = Made(name, data, float(np.abs(data).max()))
    smp = to_sample(m, 64)
    pat = [[modlib.Cell() for _ in range(4)] for _ in range(modlib.ROWS)]
    pat[0][0] = modlib.Cell(note, 1)
    pat[0][1].fx, pat[0][1].arg = 0xF, 6
    chans = sorted({f"{e.ch.kind}{e.ch.n}" for e in d.events})
    return ([smp], [pat], [0]), [
        f"sfx {name}: bank song {song}, {len(data) / modlib.rate_of(note):.2f}s"
        f" at {modlib.note_name(note)} ({modlib.rate_of(note):.0f} Hz), "
        f"{len(data)} bytes, from {' '.join(chans)}"]


# ------------------------------------------------------------------ main
def parse_list(path):
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].split()
        if not line:
            continue
        kind, name, bank, song = line[:4]
        assert kind in ("music", "sfx") and bank in BANKS, line
        opts = dict(x.split("=", 1) for x in line[4:])
        order = [int(t) for t in opts["tracks"].split(",")] \
            if "tracks" in opts else None
        out.append((kind, name, bank, int(song), order))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", default=ROOT / "orig/dune2.gen")
    ap.add_argument("--list", default=ROOT / "src/res/sega_sound.txt")
    ap.add_argument("--out", type=Path, default=ROOT / "src/res/prebuilt")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--share", type=int, default=SHARE_TOL,
                    help="semitones a shared sample's recording may be "
                    "from a song's own; -1 shares nothing")
    args = ap.parse_args()
    if not CHIPRENDER.exists():
        sys.exit("bin/gen/chiprender is missing: "
                 "python3 tools/build_toolchain.py chiprender")
    rom = open(args.rom, "rb").read()
    banks = {k: Bank(rom, *v) for k, v in BANKS.items()}
    lines = parse_list(args.list)
    # pass 1: every tune's notes placed, and what each needs to play them
    # - all of them, even with --only, so that a tune made on its own
    # shares exactly what it would have shared in a full run
    share, placed = None, {}
    if args.share >= 0:
        share = Sharing(args.share)
        for kind, name, bank, song, order in lines:
            if kind == "music":
                pl = placed[name] = Placed(banks[bank], song, order)
                share.need(name, sample_groups(pl.placed, pl.tps_first))
        share.resolve()
    report, bad = [], []
    for kind, name, bank, song, order in lines:
        if args.only and name not in args.only:
            continue
        d = args.out / kind
        d.mkdir(parents=True, exist_ok=True)
        if kind == "music":
            samples, patterns, orders, rep, (expect, speed) = \
                convert_music(banks[bank], song, name, order, share,
                              placed.get(name))
            n = modlib.write(d / f"{name}.mod", name, samples, patterns,
                             orders)
            line, ok = check(d / f"{name}.mod", expect, speed)
            rep.append(line)
            if not ok:
                bad.append(name)
        else:
            mod, rep = convert_sfx(banks[bank], song, name)
            if mod is None:
                report += rep
                print("\n".join(rep))
                continue
            n = modlib.write(d / f"{name}.mod", name, *mod)
        rep[0] += f" -> {kind}/{name}.mod, {n} bytes"
        print("\n".join(rep))
        report += rep
    if bad:
        sys.exit("these modules do not hold the notes they were given: "
                 + " ".join(bad))
    if share:
        n = sum(1 for v in share.users.values() if v > 1)
        line = (f"music: {len(share.users)} instrument samples rendered "
                f"for the tunes, {n} of them played by more than one "
                f"(shared within {share.tol} semitone(s))")
        print(line)
        report.append(line)
    if not args.only:
        (args.out / "report.txt").write_text(
            "# report.txt - what tools/sega/sega_mod.py made of each sound."
            "\n\n" + "\n".join(report) + "\n")


if __name__ == "__main__":
    main()
