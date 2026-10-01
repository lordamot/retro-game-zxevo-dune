/* evo-run.c - headless, scriptable ZX Evolution runner.
 *
 *   evo-run --rom bin/evo/zxevo_baseconf.rom [--gsrom F] [--trd F.trd] [--sd F.img] [--spg F.spg]
 *           [--nvram F] [--save-nvram F] [--script F] [--frames N]
 *           [--shot F.bmp] [--wav F.wav] [--profile] [--quiet]
 *
 * With no --script it simply runs --frames frames and, if asked, writes a
 * screenshot.  A script is a text file of one command per line, '#' starts
 * a comment:
 *
 *   run N              run N frames
 *   reset              hard reset
 *   hold KEYS          hold these keys from now on (comma separated)
 *   release            release everything
 *   press KEYS N       hold KEYS for N frames, then release, then 2 idle
 *   type TEXT          press the letters/digits of TEXT one at a time
 *   trd FILE [DRIVE]   insert a disk
 *   shot FILE          write the current frame as a 24-bit BMP
 *   wav FILE           start capturing audio; wavstop closes it
 *   ram FILE           dump the 64 KB the CPU currently sees
 *   page N FILE        dump one 16 KB RAM page
 *   peek ADDR [N]      print N bytes from the CPU address space
 *   state              print PC, the video mode, the paged-in banks
 *   profile            start the OUT (0FDh),A cycle profiler
 *   profreport         print what it collected
 *   echo TEXT          print TEXT
 *
 * Key names are in evo.c: "a".."z", "0".."9", "enter", "space", "caps",
 * "sym", "up"/"down"/"left"/"right", "break", "edit", "del", and "kj*" for
 * the Kempston joystick.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "evo.h"

static evo M;
static FILE *wav;
static long wav_samples;
static int quiet;

/* ------------------------------------------------------------------- wav */

static void wav_put16(FILE *f, unsigned v){ fputc(v & 0xff, f); fputc((v >> 8) & 0xff, f); }
static void wav_put32(FILE *f, unsigned long v)
{
    fputc((int)(v & 0xff), f);        fputc((int)((v >>  8) & 0xff), f);
    fputc((int)((v >> 16) & 0xff), f); fputc((int)((v >> 24) & 0xff), f);
}

static void wav_open(const char *path)
{
    int i;
    if (wav) return;
    wav = fopen(path, "wb");
    if (!wav) { fprintf(stderr, "evo-run: cannot write %s\n", path); return; }
    for (i = 0; i < 44; i++) fputc(0, wav);
    wav_samples = 0;
}

static void wav_close(void)
{
    unsigned long data;
    if (!wav) return;
    data = (unsigned long)wav_samples * 2;      /* 2 bytes a sample */
    fseek(wav, 0, SEEK_SET);
    fwrite("RIFF", 1, 4, wav); wav_put32(wav, 36 + data);
    fwrite("WAVEfmt ", 1, 8, wav); wav_put32(wav, 16);
    wav_put16(wav, 1); wav_put16(wav, 2);       /* PCM, stereo */
    wav_put32(wav, (unsigned long)M.audio_hz);
    wav_put32(wav, (unsigned long)M.audio_hz * 4);
    wav_put16(wav, 4); wav_put16(wav, 16);
    fwrite("data", 1, 4, wav); wav_put32(wav, data);
    fclose(wav);
    wav = NULL;
}

/* ---------------------------------------------------------------- running */

static void run_frames(int n)
{
    int i, s;
    for (i = 0; i < n; i++) {
        evo_frame(&M);
        if (wav) {
            for (s = 0; s < M.audio_n; s++) wav_put16(wav, (unsigned)(uint16_t)M.audio[s]);
            wav_samples += M.audio_n;
        }
    }
}

static void set_keys(char *list, int down)
{
    char *p = list;
    while (p && *p) {
        char *comma = strchr(p, ',');
        if (comma) *comma = 0;
        while (*p == ' ') p++;
        if (*p) {
            int c = evo_key_lookup(p);
            if (c < 0) fprintf(stderr, "evo-run: unknown key '%s'\n", p);
            else evo_key(&M, c, down);
        }
        p = comma ? comma + 1 : NULL;
    }
}

static void press_keys(char *list, int frames)
{
    char copy[256];
    snprintf(copy, sizeof copy, "%s", list);
    set_keys(copy, 1);
    run_frames(frames > 0 ? frames : 3);
    snprintf(copy, sizeof copy, "%s", list);
    set_keys(copy, 0);
    run_frames(2);
}

static void type_text(const char *text)
{
    char one[8];
    for (; *text; text++) {
        if (*text == ' ') strcpy(one, "space");
        else if (*text == '\n') strcpy(one, "enter");
        else { one[0] = (char)(*text >= 'A' && *text <= 'Z' ? *text + 32 : *text); one[1] = 0; }
        press_keys(one, 3);
    }
}

static void print_state(void)
{
    Computer *c = M.comp;
    int i;
    printf("pc=%04X sp=%04X video=%s(%d) turbo=%.1f banks=",
           cpu_get_pc(c->cpu), cpu_get_sp(c->cpu),
           evo_video_mode_name(c->vid->vmode), c->vid->vmode, c->frqMul);
    for (i = 0; i < 4; i++) {
        MemPage *p = &c->mem->map[i * 64];
        printf("%s%d%s", p->type == MEM_ROM ? "R" : "r", p->num, i == 3 ? "" : ",");
    }
    printf(" dos=%d 7ffd=%02X eff7=%02X prt2=%02X\n",
           c->flgDOS, c->p7FFD, c->pEFF7, c->prt2);
    printf("gs: %s pc=%04X state=%02X zx->gs cmd=%02X data=%02X gs->zx=%02X"
           " rp0=%02X banks=%d,%d,%d,%d\n",
           c->gs->enable ? "on" : "off", cpu_get_pc(c->gs->cpu),
           c->gs->pstate, c->gs->pbb_zx, c->gs->pb3_zx, c->gs->pb3_gs,
           c->gs->rp0,
           c->gs->mem->map[0x00].num >> 6, c->gs->mem->map[0x40].num >> 6,
           c->gs->mem->map[0x80].num >> 6, c->gs->mem->map[0xc0].num >> 6);
    printf("gs: dac %02X %02X %02X %02X  vol %02X %02X %02X %02X\n",
           c->gs->ch1, c->gs->ch2, c->gs->ch3, c->gs->ch4,
           c->gs->vol1, c->gs->vol2, c->gs->vol3, c->gs->vol4);
}

/* ---------------------------------------------------------------- scripts */

static void run_script(const char *path)
{
    char line[512];
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "evo-run: cannot read %s\n", path); exit(1); }
    while (fgets(line, sizeof line, f)) {
        char *cmd, *a1, *a2, *hash = strchr(line, '#');
        if (hash) *hash = 0;
        cmd = strtok(line, " \t\r\n");
        if (!cmd) continue;
        a1 = strtok(NULL, " \t\r\n");
        a2 = strtok(NULL, " \t\r\n");
        if      (!strcmp(cmd, "run"))     run_frames(a1 ? atoi(a1) : 1);
        else if (!strcmp(cmd, "reset"))   evo_reset(&M);
        else if (!strcmp(cmd, "fillram")) evo_fill_ram(&M, a1 ? (int)strtol(a1, NULL, 0) : 1);
        else if (!strcmp(cmd, "hold"))    { if (a1) set_keys(a1, 1); }
        else if (!strcmp(cmd, "release")) evo_key_release_all(&M);
        else if (!strcmp(cmd, "press"))   { if (a1) press_keys(a1, a2 ? atoi(a2) : 3); }
        else if (!strcmp(cmd, "type"))    { if (a1) type_text(a1); }
        else if (!strcmp(cmd, "trd"))     { if (a1) evo_insert_trd(&M, a1, a2 ? atoi(a2) : 0); }
        else if (!strcmp(cmd, "sd"))      { if (a1 && evo_insert_sd(&M, a1)) fprintf(stderr, "evo-run: cannot open %s\n", a1); }
        else if (!strcmp(cmd, "spg"))     { if (a1 && evo_load_spg(&M, a1)) fprintf(stderr, "evo-run: cannot load %s\n", a1); }
        else if (!strcmp(cmd, "poke"))    { if (a1 && a2) evo_poke(&M, (int)strtol(a1, NULL, 0), (int)strtol(a2, NULL, 0)); }
        else if (!strcmp(cmd, "pokepage")) {
            /* pokepage PAGE OFFSET VALUE */
            char *a3 = strtok(NULL, " \t\r\n");
            if (a1 && a2 && a3) evo_poke_ram(&M, (int)strtol(a1, NULL, 0), (int)strtol(a2, NULL, 0), (int)strtol(a3, NULL, 0));
        }
        else if (!strcmp(cmd, "shot"))    { if (a1 && evo_save_bmp(&M, a1) == 0 && !quiet) printf("shot %s\n", a1); }
        else if (!strcmp(cmd, "wav"))     { if (a1) wav_open(a1); }
        else if (!strcmp(cmd, "wavstop")) wav_close();
        else if (!strcmp(cmd, "ram")) {
            FILE *o = a1 ? fopen(a1, "wb") : NULL;
            int i;
            if (o) { for (i = 0; i < 0x10000; i++) fputc(evo_peek(&M, i), o); fclose(o); }
        } else if (!strcmp(cmd, "page")) {
            FILE *o = a2 ? fopen(a2, "wb") : NULL;
            int i, pg = a1 ? atoi(a1) : 0;
            if (o) { for (i = 0; i < 0x4000; i++) fputc(evo_ram(&M, pg, i), o); fclose(o); }
        } else if (!strcmp(cmd, "peek")) {
            int addr = a1 ? (int)strtol(a1, NULL, 0) : 0, n = a2 ? atoi(a2) : 16, i;
            printf("%04X:", addr);
            for (i = 0; i < n; i++) printf(" %02X", evo_peek(&M, addr + i));
            printf("\n");
        }
        else if (!strcmp(cmd, "state"))      print_state();
        else if (!strcmp(cmd, "gsmem")) {
            /* dump one of the sound card's own 16 KB RAM pages */
            FILE *o = a2 ? fopen(a2, "wb") : NULL;
            int i, pg = a1 ? atoi(a1) : 0;
            if (o) {
                for (i = 0; i < 0x4000; i++)
                    fputc(M.comp->gs->mem->ramData[(pg * 0x4000 + i)
                          & M.comp->gs->mem->ramMask], o);
                fclose(o);
            }
        }
        else if (!strcmp(cmd, "profile"))    evo_profile_enable(&M);
        else if (!strcmp(cmd, "gstrace"))    evo_trace_gs(a1 ? atol(a1) : 200);
        else if (!strcmp(cmd, "gsdead"))     evo_gs_dead();
        else if (!strcmp(cmd, "gsram") && a1) evo_gs_ram(&M, atoi(a1));
        else if (!strcmp(cmd, "gsclock") && a1) evo_gs_clock(&M, atoi(a1));
        else if (!strcmp(cmd, "wtrap") && a1 && a2) {
            /* wtrap LO HI [PAGE0] [PAGE3]: -1 = any page in that window */
            char *a3 = strtok(NULL, " \t\r\n");
            char *a4 = a3 ? strtok(NULL, " \t\r\n") : NULL;
            evo_write_trap((int)strtol(a1, NULL, 16), (int)strtol(a2, NULL, 16),
                           a3 ? atoi(a3) : -1, a4 ? atoi(a4) : -1);
        }
        else if (!strcmp(cmd, "pctrap") && a1 && a2) {
            /* pctrap LO HI [PAGE]: hex addresses, the page in window 0 */
            char *a3 = strtok(NULL, " \t\r\n");
            evo_pc_trap((int)strtol(a1, NULL, 16), (int)strtol(a2, NULL, 16),
                        a3 ? atoi(a3) : -1);
        }
        else if (!strcmp(cmd, "gswatch") && a1) evo_gs_watch((int)strtol(a1, NULL, 16));
        else if (!strcmp(cmd, "gshits"))     printf("gshits %ld\n", evo_gs_hits());
        else if (!strcmp(cmd, "profreport")) evo_profile_report(&M, stdout);
        else if (!strcmp(cmd, "echo"))       printf("%s\n", a1 ? a1 : "");
        else fprintf(stderr, "evo-run: unknown command '%s'\n", cmd);
    }
    fclose(f);
}

int main(int argc, char **argv)
{
    const char *rom = NULL, *gsrom = NULL, *trd = NULL, *spg = NULL, *sd = NULL;
    const char *script = NULL, *shot = NULL, *wavpath = NULL;
    const char *nvram = NULL, *savenvram = NULL;
    int frames = 0, profile = 0, i, err;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--rom") && i + 1 < argc)         rom = argv[++i];
        else if (!strcmp(argv[i], "--gsrom") && i + 1 < argc)  gsrom = argv[++i];
        else if (!strcmp(argv[i], "--trd") && i + 1 < argc)    trd = argv[++i];
        else if (!strcmp(argv[i], "--spg") && i + 1 < argc)    spg = argv[++i];
        else if (!strcmp(argv[i], "--sd") && i + 1 < argc)     sd = argv[++i];
        else if (!strcmp(argv[i], "--script") && i + 1 < argc) script = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--shot") && i + 1 < argc)   shot = argv[++i];
        else if (!strcmp(argv[i], "--wav") && i + 1 < argc)    wavpath = argv[++i];
        else if (!strcmp(argv[i], "--nvram") && i + 1 < argc)   nvram = argv[++i];
        else if (!strcmp(argv[i], "--save-nvram") && i + 1 < argc) savenvram = argv[++i];
        else if (!strcmp(argv[i], "--profile"))                profile = 1;
        else if (!strcmp(argv[i], "--quiet"))                  quiet = 1;
        else { fprintf(stderr, "evo-run: unknown option %s\n", argv[i]); return 2; }
    }
    if (!rom) { fprintf(stderr, "evo-run: --rom is required\n"); return 2; }

    err = evo_init(&M, rom, gsrom, 44100);
    if (err) { fprintf(stderr, "evo-run: cannot start the machine (%d)\n", err); return 1; }
    if (nvram && evo_load_nvram(&M, nvram) == 0) evo_reset(&M);
    if (trd && (err = evo_insert_trd(&M, trd, 0)) != 0)
        fprintf(stderr, "evo-run: cannot load %s (%d)\n", trd, err);
    if (sd && evo_insert_sd(&M, sd) != 0)
        fprintf(stderr, "evo-run: cannot open %s\n", sd);
    if (spg && (err = evo_load_spg(&M, spg)) != 0)
        fprintf(stderr, "evo-run: cannot load %s (%d)\n", spg, err);
    if (profile) evo_profile_enable(&M);
    if (wavpath) wav_open(wavpath);

    if (script) run_script(script);
    else run_frames(frames > 0 ? frames : 100);

    if (shot) evo_save_bmp(&M, shot);
    if (savenvram) evo_save_nvram(&M, savenvram);
    wav_close();
    if (profile) evo_profile_report(&M, stdout);
    if (!quiet) print_state();
    evo_free(&M);
    return 0;
}
