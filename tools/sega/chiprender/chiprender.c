/* chiprender - replay a YM2612 register script to PCM.
 *
 *     chiprender < script > out.s16
 *
 * The chip is the Genesis core's own Nuked OPN2 (core/sound/ym3438.c,
 * compiled in by tools/build_toolchain.py), so a note rendered here is what
 * the Mega Drive would have made of the same register writes.  It is how
 * tools/sega/sega_mod.py turns the Dune II driver's FM instruments into
 * tracker samples: it writes the driver's own register sequence for one
 * note, holds the key for as long as the note lasts, and cuts the result.
 *
 * The script is text, one command a line:
 *
 *     w PART REG VAL    write VAL to register REG of part 0 or 1
 *                       (numbers in hex, as the driver's listing has them)
 *     run N             clock the chip for N output samples
 *     # ...             a comment
 *
 * Output is signed 16-bit little-endian, stereo, at the chip's own rate:
 * 7670453 / 144 = 53267 Hz on an NTSC machine.  Every write is followed by
 * one output sample's worth of clocks, which is more than the chip's busy
 * time, so no write is ever dropped.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ym3438.h"

static ym3438_t chip;
static Bit16s accm[24][2];

static void sample(FILE *out)
{
    int j, l = 0, r = 0;
    short s[2];
    for (j = 0; j < 24; j++)
        OPN2_Clock(&chip, accm[j]);
    for (j = 0; j < 24; j++) {
        l += accm[j][0];
        r += accm[j][1];
    }
    /* the core's own scale (sound.c: YM3438_Update), clipped */
    l *= 11;
    r *= 11;
    s[0] = l > 32767 ? 32767 : l < -32768 ? -32768 : l;
    s[1] = r > 32767 ? 32767 : r < -32768 ? -32768 : r;
    fwrite(s, sizeof s, 1, out);
}

int main(void)
{
    char line[256];
    unsigned part, reg, val;
    long n;

    OPN2_SetChipType(0);            /* the discrete YM2612, as in a MD1 */
    OPN2_Reset(&chip);
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "w %x %x %x", &part, &reg, &val) == 3) {
            OPN2_Write(&chip, part * 2, reg);
            sample(stdout);
            OPN2_Write(&chip, part * 2 + 1, val);
            sample(stdout);
        } else if (sscanf(line, "run %ld", &n) == 1) {
            while (n-- > 0)
                sample(stdout);
        } else if (line[0] != '#' && line[0] != '\n') {
            fprintf(stderr, "chiprender: cannot read: %s", line);
            return 1;
        }
    }
    return 0;
}
