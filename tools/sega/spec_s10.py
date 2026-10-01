"""S10 - controls and screens: the sound tables, and the battle's tune shuffle.

Loaded by sega_spec_check.py into its own namespace (scenario, frames,
Check, ROM and the rest come from there).
"""

# Effect id (the PC game's sound id, snd_play_effect $00A7D8) -> the song
# the Mega Drive plays for it, from the table at $06A876.  Ids not listed
# play nothing.  orig/sega/spec/S10-screens.md quotes the same table.
S10_EFFECTS = {6: 44, 7: 42, 8: 84, 12: 25, 13: 82, 14: 81, 15: 79, 16: 80,
               17: 67, 18: 68, 20: 70, 27: 83, 30: 76, 31: 76, 32: 76,
               33: 76, 34: 76, 35: 78, 36: 23, 38: 40, 39: 35, 40: 36,
               41: 39, 42: 74, 43: 34, 44: 29, 46: 28, 47: 26, 49: 39,
               50: 71, 51: 81, 52: 27, 53: 21, 56: 69, 57: 69, 58: 72,
               59: 73, 62: 75, 63: 77, 64: 72}

# Feedback id (the PC's g_feedback index, snd_play_voice $00A8DE) -> song,
# from $06A954; 94 ids, seven of them voiced.
S10_VOICES = {0: 65, 1: 64, 2: 64, 3: 64, 4: 64, 5: 64, 48: 66}

# Music track (the PC's music id, snd_play_music $00A806) -> (song,
# frames) from $06A8B8; -1 is none, and a length of -1 means the tune is
# not timed.
S10_MUSIC = {1: (5, -1), 2: (16, -1), 3: (15, -1), 4: (14, -1),
             5: (13, -1), 6: (12, -1), 7: (11, -1), 8: (1, 10020),
             9: (2, 7320), 10: (3, 7560), 11: (4, 8040), 12: (10, 9840),
             24: (6, -1), 25: (0, -1), 26: (8, -1), 28: (9, -1),
             29: (7, -1), 33: (18, -1), 38: (17, -1)}


def _sb(x):
    return x - 256 if x > 127 else x


@scenario("S10", "the effect, voice and music tables are the spec's")
def s10_sound_tables(c):
    rom = ROM.read_bytes()
    for i in range(0x41):
        got = _sb(rom[0x06A876 + i])
        want = S10_EFFECTS.get(i, None)
        c.that((got < 0 and want is None) or got == want,
               f"effect {i}: ROM {got}, spec {want}")
    for i in range(0x5E):
        got = _sb(rom[0x06A954 + i])
        want = S10_VOICES.get(i, None)
        c.that((got < 0 and want is None) or got == want,
               f"voice {i}: ROM {got}, spec {want}")
    for i in range(0x27):
        a = 0x06A8B8 + 4 * i
        song = int.from_bytes(rom[a:a + 2], "big", signed=True)
        n = int.from_bytes(rom[a + 2:a + 4], "big", signed=True)
        want = S10_MUSIC.get(i, (-1, -1))
        c.that((song, n) == want, f"track {i}: ROM {(song, n)}, spec {want}")


@scenario("S10", "a battle tune that ends is followed by another, 8-12, timed")
def s10_next_tune(c):
    step = 10
    d = frames("m1-0", 800, every=step)
    left = [x.s(0xFFC574, 2) for x in d]
    track = [x.w(0xFFC8B8) for x in d]
    song = [x.w(0xFFC8BC) for x in d]
    c.that(8 <= track[0] <= 12, f"first track {track[0]}")
    changes = [i for i in range(1, len(d)) if track[i] != track[i - 1]]
    c.that(len(changes) >= 1, "no new tune in 8000 frames")
    for i in changes:
        t, prev = track[i], track[i - 1]
        c.that(8 <= t <= 12, f"new track {t}")
        c.that(t != prev, f"track {t} repeated")
        c.that(song[i] == S10_MUSIC[t][0],
               f"track {t} plays song {song[i]}, table says {S10_MUSIC[t][0]}")
        # the tune started at most `step` frames before this dump
        n = S10_MUSIC[t][1]
        c.that(n - step <= left[i] <= n,
               f"track {t}: {left[i]} frames left, length {n}")
        c.that(left[i - 1] < step, f"old tune had {left[i - 1]} left")
    # between changes the countdown falls by exactly one a frame
    for i in range(1, len(d)):
        if i not in changes and left[i - 1] >= 0:
            c.that(left[i - 1] - left[i] == step,
                   f"countdown {left[i - 1]} -> {left[i]} in {step} frames")


@scenario("S10", "with every tune 7320 frames long the timing misfits (control)")
def s10_next_tune_control(c):
    # a shuffle that ignored the table - every tune the same 7320 frames -
    # would not fit what the machine did
    saved = dict(S10_MUSIC)
    try:
        for k in (8, 10, 11, 12):
            S10_MUSIC[k] = (S10_MUSIC[k][0], 7320)
        inner = Check()
        s10_next_tune(inner)
    finally:
        S10_MUSIC.clear()
        S10_MUSIC.update(saved)
    c.that(bool(inner.fails), "wrong lengths still fit")
