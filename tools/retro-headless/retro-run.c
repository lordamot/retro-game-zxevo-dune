/* retro-run - scriptable headless runner for the two reference machines.

   A minimal libretro frontend (dlopen), built by tools/build_toolchain.py
   into bin/nes/ (with the FCEUmm core, for the original NES demo) and into
   bin/gen/ (with Genesis Plus GX, for the Mega Drive Dune II this port's
   graphics come from).  It exists so the ROMs in orig/ can be driven
   reproducibly from the project's own tooling: run frames, inject
   controller input, save screenshots, capture audio, and - the reason the
   Mega Drive side exists at all - dump the video memory, so the tiles,
   the tilemaps and the palettes the real game builds can be read out
   rather than guessed at.

   Usage:
     retro-run --core CORE.so --rom GAME [--script FILE]
               [--frames N] [--shot FILE.bmp] [--wav FILE.wav]

   Script commands (one per line, '#' starts a comment):
     run N              run N frames
     hold BTNS          hold these buttons from now on (comma list)
     release            release every button
     press BTNS N       hold BTNS for N frames, then release
     shot FILE          write the current frame as a 24-bit BMP
     wav FILE           start recording audio into FILE
     wavstop            close the current WAV
     ram FILE           dump the machine's work RAM
     sram FILE          dump the cartridge's own RAM, if it has any
   The four video dumps need the patched cores (see
   tools/build_toolchain.py).  They are one set of commands over two very
   different machines, so each has a name from each:

     vram | nt FILE     Mega Drive: 64 KB of tiles and tilemaps
                        NES: the four nametables, mirroring resolved
     cram | pal FILE    Mega Drive: 64 nine-bit colours
                        NES: the 32 bytes of palette RAM
     vsram | oam FILE   Mega Drive: vertical scroll RAM
                        NES: the 256-byte sprite table
     vdpreg | chr FILE  Mega Drive: the VDP's 32 registers
                        NES: the 8 KB of CHR the mapper has banked in
     ppureg FILE        NES: the four PPU registers
     z80 FILE           Mega Drive: the Z80's own 8 KB, which is the sound
                        driver and all of its state
     save FILE          write the whole machine's state
     load FILE          put it back - so a run can start from a moment
                        instead of from power-on
     reset              reset the machine
   Button names are the RetroPad's: a b x y l r select start up down left
   right, plus mda / mdb / mdc for the Mega Drive's own A, B and C, which
   the core does not map to the same-named RetroPad buttons.
*/

#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "libretro.h"

static void *core;
static uint32_t buttons;                 /* bit per RETRO_DEVICE_ID_JOYPAD_* */
static const void *frame_data;
static unsigned frame_w, frame_h;
static size_t frame_pitch;
static unsigned pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;
static FILE *wav;
static uint32_t wav_bytes;
static unsigned sample_rate = 48000;

#define SYM(name) static void (*p_##name)(void)
static void (*p_retro_init)(void);
static void (*p_retro_deinit)(void);
static void (*p_retro_run)(void);
static bool (*p_retro_load_game)(const struct retro_game_info *);
static void (*p_retro_get_system_av_info)(struct retro_system_av_info *);
static void *(*p_retro_get_memory_data)(unsigned);
static size_t (*p_retro_get_memory_size)(unsigned);
static void (*p_retro_set_environment)(retro_environment_t);
static void (*p_retro_set_video_refresh)(retro_video_refresh_t);
static void (*p_retro_set_audio_sample)(retro_audio_sample_t);
static void (*p_retro_set_audio_sample_batch)(retro_audio_sample_batch_t);
static void (*p_retro_set_input_poll)(retro_input_poll_t);
static void (*p_retro_set_input_state)(retro_input_state_t);
static size_t (*p_retro_serialize_size)(void);
static bool (*p_retro_serialize)(void *, size_t);
static bool (*p_retro_unserialize)(const void *, size_t);
static void (*p_retro_reset)(void);

static void die(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "retro-run: ");
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
    exit(1);
}

static void *sym(const char *name)
{
    void *s = dlsym(core, name);
    if (!s)
        die("core lacks %s", name);
    return s;
}

/* ---------------------------------------------------------------- */
/* libretro callbacks                                               */

static void log_printf(enum retro_log_level level, const char *fmt, ...)
{
    (void)level;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
}

static bool env_cb(unsigned cmd, void *data)
{
    switch (cmd & 0xFFFF) {
    case RETRO_ENVIRONMENT_GET_CAN_DUPE:
        *(bool *)data = true;
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
        pixel_format = *(const enum retro_pixel_format *)data;
        return true;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE:
        ((struct retro_log_callback *)data)->log = log_printf;
        return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION:
        *(unsigned *)data = 0;      /* keep the core on plain variables */
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
        return true;
    default:
        return false;
    }
}

static void video_cb(const void *data, unsigned w, unsigned h, size_t pitch)
{
    if (data) {
        frame_data = data;
        frame_w = w;
        frame_h = h;
        frame_pitch = pitch;
    }
}

static void wav_write(const int16_t *data, size_t frames)
{
    if (!wav)
        return;
    fwrite(data, 4, frames, wav);
    wav_bytes += frames * 4;
}

static void audio_sample(int16_t l, int16_t r)
{
    int16_t s[2] = { l, r };
    wav_write(s, 1);
}

static size_t audio_batch(const int16_t *data, size_t frames)
{
    wav_write(data, frames);
    return frames;
}

static void input_poll(void) {}

static int16_t input_state(unsigned port, unsigned device, unsigned index,
                           unsigned id)
{
    (void)index;
    if (port || device != RETRO_DEVICE_JOYPAD || id > 15)
        return 0;
    return (buttons >> id) & 1;
}

/* ---------------------------------------------------------------- */
/* output files                                                     */

static void put32(unsigned char *p, uint32_t v)
{
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}

/* The frame as a bottom-up 24-bit BMP; the Python tools convert it to PNG. */
static void save_bmp(const char *path)
{
    if (!frame_data)
        die("no frame to save yet");
    unsigned row = (frame_w * 3 + 3) & ~3u;
    uint32_t size = 54 + row * frame_h;
    unsigned char hdr[54] = { 'B', 'M' };
    put32(hdr + 2, size);
    put32(hdr + 10, 54);
    put32(hdr + 14, 40);
    put32(hdr + 18, frame_w);
    put32(hdr + 22, frame_h);
    hdr[26] = 1; hdr[28] = 24;
    put32(hdr + 34, row * frame_h);
    FILE *f = fopen(path, "wb");
    if (!f)
        die("cannot write %s", path);
    fwrite(hdr, 1, sizeof hdr, f);
    unsigned char *line = calloc(1, row);
    for (int y = (int)frame_h - 1; y >= 0; y--) {
        const unsigned char *src = (const unsigned char *)frame_data
                                   + (size_t)y * frame_pitch;
        for (unsigned x = 0; x < frame_w; x++) {
            unsigned r, g, b;
            if (pixel_format == RETRO_PIXEL_FORMAT_XRGB8888) {
                uint32_t p = ((const uint32_t *)src)[x];
                r = (p >> 16) & 0xFF; g = (p >> 8) & 0xFF; b = p & 0xFF;
            } else if (pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
                uint16_t p = ((const uint16_t *)src)[x];
                r = ((p >> 11) & 0x1F) * 255 / 31;
                g = ((p >> 5) & 0x3F) * 255 / 63;
                b = (p & 0x1F) * 255 / 31;
            } else {
                uint16_t p = ((const uint16_t *)src)[x];
                r = ((p >> 10) & 0x1F) * 255 / 31;
                g = ((p >> 5) & 0x1F) * 255 / 31;
                b = (p & 0x1F) * 255 / 31;
            }
            line[x * 3] = b; line[x * 3 + 1] = g; line[x * 3 + 2] = r;
        }
        fwrite(line, 1, row, f);
    }
    free(line);
    fclose(f);
    printf("shot %s (%ux%u)\n", path, frame_w, frame_h);
}

static void wav_close(void)
{
    if (!wav)
        return;
    unsigned char h[44] = { 0 };
    memcpy(h, "RIFF", 4);
    put32(h + 4, 36 + wav_bytes);
    memcpy(h + 8, "WAVEfmt ", 8);
    put32(h + 16, 16);
    h[20] = 1; h[22] = 2;               /* PCM, stereo */
    put32(h + 24, sample_rate);
    put32(h + 28, sample_rate * 4);
    h[32] = 4; h[34] = 16;
    memcpy(h + 36, "data", 4);
    put32(h + 40, wav_bytes);
    fseek(wav, 0, SEEK_SET);
    fwrite(h, 1, sizeof h, wav);
    fclose(wav);
    wav = NULL;
}

static void wav_open(const char *path)
{
    wav_close();
    wav = fopen(path, "wb");
    if (!wav)
        die("cannot write %s", path);
    unsigned char pad[44] = { 0 };
    fwrite(pad, 1, sizeof pad, wav);
    wav_bytes = 0;
    printf("wav %s\n", path);
}

/* The three VDP regions are private libretro ids the patched Genesis Plus
   GX answers; see tools/build_toolchain.py for the patch. */
#define MEM_CRAM   0x100
#define MEM_VSRAM  0x101
#define MEM_VDPREG 0x102
#define MEM_PPUREG 0x103
#define MEM_ZRAM   0x104
/* what the machine did with each cartridge byte, and who first read it -
   the Genesis core only; see patch_gpgx_touch in tools/build_toolchain.py */
#define MEM_TOUCH  0x105
#define MEM_READER 0x106
#define MEM_BLIND  0x107

static void dump_mem(const char *what, unsigned id, const char *path)
{
    void *d = p_retro_get_memory_data(id);
    size_t n = p_retro_get_memory_size(id);
    if (!d || !n)
        die("this core has no %s (id %u)", what, id);
    FILE *f = fopen(path, "wb");
    if (!f)
        die("cannot write %s", path);
    fwrite(d, 1, n, f);
    fclose(f);
    printf("%s %s (%zu bytes)\n", what, path, n);
}

/* ---------------------------------------------------------------- */
/* save states                                                       */
/*                                                                   */
/* The reason this exists: without it every experiment starts at      */
/* power-on and walks the whole front end again, so watching what a   */
/* button does costs a full boot each time.  With it, a run reaches   */
/* the interesting moment once, saves, and every probe after that is  */
/* load-press-look.                                                   */

static void state_save(const char *path)
{
    size_t n = p_retro_serialize_size ? p_retro_serialize_size() : 0;
    if (!n)
        die("this core cannot serialise its state");
    void *buf = malloc(n);
    if (!buf || !p_retro_serialize(buf, n))
        die("the core refused to serialise");
    FILE *f = fopen(path, "wb");
    if (!f)
        die("cannot write %s", path);
    fwrite(buf, 1, n, f);
    fclose(f);
    free(buf);
    printf("save %s (%zu bytes)\n", path, n);
}

static void state_load(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        die("cannot read %s", path);
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    void *buf = malloc(n);
    if (!buf || fread(buf, 1, n, f) != (size_t)n)
        die("cannot read %s", path);
    fclose(f);
    if (!p_retro_unserialize || !p_retro_unserialize(buf, n))
        die("the core refused the state in %s", path);
    free(buf);
    printf("load %s (%ld bytes)\n", path, n);
}

/* ---------------------------------------------------------------- */

static const char *const BTN_NAMES[] = {
    "b", "y", "select", "start", "up", "down", "left", "right", "a", "x",
    "l", "r", "l2", "r2", "l3", "r3"
};

/* The Mega Drive's three face buttons are not where their names suggest:
   Genesis Plus GX maps MD A to the RetroPad's Y, MD B to B and MD C to A.
   Scripts say mda/mdb/mdc and mean the buttons printed on the pad. */
static const struct { const char *name; unsigned id; } BTN_ALIAS[] = {
    { "mda", 1 },       /* RETRO_DEVICE_ID_JOYPAD_Y */
    { "mdb", 0 },       /* RETRO_DEVICE_ID_JOYPAD_B */
    { "mdc", 8 },       /* RETRO_DEVICE_ID_JOYPAD_A */
    { NULL, 0 }
};

static uint32_t parse_buttons(char *list)
{
    uint32_t m = 0;
    for (char *t = strtok(list, ","); t; t = strtok(NULL, ",")) {
        unsigned i;
        for (i = 0; BTN_ALIAS[i].name; i++)
            if (!strcmp(t, BTN_ALIAS[i].name))
                break;
        if (BTN_ALIAS[i].name) {
            m |= 1u << BTN_ALIAS[i].id;
            continue;
        }
        for (i = 0; i < 16; i++)
            if (!strcmp(t, BTN_NAMES[i]))
                break;
        if (i == 16)
            die("unknown button '%s'", t);
        m |= 1u << i;
    }
    return m;
}

static void run_frames(long n)
{
    for (long i = 0; i < n; i++)
        p_retro_run();
}

static void run_script(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f)
        die("cannot open script %s", path);
    char line[512];
    while (fgets(line, sizeof line, f)) {
        char *hash = strchr(line, '#');
        if (hash)
            *hash = 0;
        char *cmd = strtok(line, " \t\r\n");
        if (!cmd)
            continue;
        char *a1 = strtok(NULL, " \t\r\n");
        char *a2 = strtok(NULL, " \t\r\n");
        if (!strcmp(cmd, "run") && a1) {
            run_frames(atol(a1));
        } else if (!strcmp(cmd, "hold") && a1) {
            buttons = parse_buttons(a1);
        } else if (!strcmp(cmd, "release")) {
            buttons = 0;
        } else if (!strcmp(cmd, "press") && a1 && a2) {
            uint32_t keep = buttons;
            buttons = keep | parse_buttons(a1);
            run_frames(atol(a2));
            buttons = keep;
            run_frames(2);
        } else if (!strcmp(cmd, "shot") && a1) {
            save_bmp(a1);
        } else if (!strcmp(cmd, "wav") && a1) {
            wav_open(a1);
        } else if (!strcmp(cmd, "wavstop")) {
            wav_close();
        } else if (!strcmp(cmd, "ram") && a1) {
            dump_mem("ram", RETRO_MEMORY_SYSTEM_RAM, a1);
        } else if (!strcmp(cmd, "sram") && a1) {
            dump_mem("sram", RETRO_MEMORY_SAVE_RAM, a1);
        } else if ((!strcmp(cmd, "vram") || !strcmp(cmd, "nt")) && a1) {
            dump_mem(cmd, RETRO_MEMORY_VIDEO_RAM, a1);
        } else if ((!strcmp(cmd, "cram") || !strcmp(cmd, "pal")) && a1) {
            dump_mem(cmd, MEM_CRAM, a1);
        } else if ((!strcmp(cmd, "vsram") || !strcmp(cmd, "oam")) && a1) {
            dump_mem(cmd, MEM_VSRAM, a1);
        } else if ((!strcmp(cmd, "vdpreg") || !strcmp(cmd, "chr")) && a1) {
            dump_mem(cmd, MEM_VDPREG, a1);
        } else if (!strcmp(cmd, "ppureg") && a1) {
            dump_mem(cmd, MEM_PPUREG, a1);
        } else if (!strcmp(cmd, "z80") && a1) {
            dump_mem(cmd, MEM_ZRAM, a1);
        } else if (!strcmp(cmd, "touch") && a1) {
            dump_mem(cmd, MEM_TOUCH, a1);
        } else if (!strcmp(cmd, "reader") && a1) {
            dump_mem(cmd, MEM_READER, a1);
        } else if (!strcmp(cmd, "blind") && a1) {
            /* an instruction whose data reads are not to be recorded -
               a checksum reads everything and means nothing by it */
            unsigned *b = p_retro_get_memory_data(MEM_BLIND);
            size_t n = p_retro_get_memory_size(MEM_BLIND) / 4, k;
            if (!b)
                die("this core does not record cartridge access");
            for (k = 0; k < n && b[k]; k++)
                ;
            if (k == n)
                die("no room for another blind instruction");
            b[k] = (unsigned)strtoul(a1, NULL, 0);
        } else if (!strcmp(cmd, "untouch")) {
            /* forget what has been recorded so far, so the next stretch
               of play is measured on its own */
            void *t = p_retro_get_memory_data(MEM_TOUCH);
            void *r = p_retro_get_memory_data(MEM_READER);
            if (!t || !r)
                die("this core does not record cartridge access");
            memset(t, 0, p_retro_get_memory_size(MEM_TOUCH));
            memset(r, 0, p_retro_get_memory_size(MEM_READER));
        } else if (!strcmp(cmd, "save") && a1) {
            state_save(a1);
        } else if (!strcmp(cmd, "load") && a1) {
            state_load(a1);
        } else if (!strcmp(cmd, "reset")) {
            p_retro_reset();
        } else {
            die("bad script line: %s", cmd);
        }
    }
    fclose(f);
}

int main(int argc, char **argv)
{
    const char *core_path = NULL, *rom = NULL, *script = NULL;
    const char *shot = NULL, *wav_path = NULL;
    long frames = 0;
    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = (i + 1 < argc) ? argv[i + 1] : NULL;
        if (!strcmp(a, "--core") && v) core_path = argv[++i];
        else if (!strcmp(a, "--rom") && v) rom = argv[++i];
        else if (!strcmp(a, "--script") && v) script = argv[++i];
        else if (!strcmp(a, "--shot") && v) shot = argv[++i];
        else if (!strcmp(a, "--wav") && v) wav_path = argv[++i];
        else if (!strcmp(a, "--frames") && v) frames = atol(argv[++i]);
        else die("unknown option %s (see the header comment)", a);
    }
    if (!core_path || !rom)
        die("usage: retro-run --core CORE.so --rom GAME [--script F] "
            "[--frames N] [--shot F.bmp] [--wav F.wav]");

    core = dlopen(core_path, RTLD_NOW);
    if (!core)
        die("dlopen %s: %s", core_path, dlerror());
    p_retro_init = sym("retro_init");
    p_retro_deinit = sym("retro_deinit");
    p_retro_run = sym("retro_run");
    p_retro_load_game = sym("retro_load_game");
    p_retro_get_system_av_info = sym("retro_get_system_av_info");
    p_retro_get_memory_data = sym("retro_get_memory_data");
    p_retro_get_memory_size = sym("retro_get_memory_size");
    p_retro_set_environment = sym("retro_set_environment");
    p_retro_set_video_refresh = sym("retro_set_video_refresh");
    p_retro_set_audio_sample = sym("retro_set_audio_sample");
    p_retro_set_audio_sample_batch = sym("retro_set_audio_sample_batch");
    p_retro_set_input_poll = sym("retro_set_input_poll");
    p_retro_set_input_state = sym("retro_set_input_state");
    p_retro_serialize_size = sym("retro_serialize_size");
    p_retro_serialize = sym("retro_serialize");
    p_retro_unserialize = sym("retro_unserialize");
    p_retro_reset = sym("retro_reset");

    p_retro_set_environment(env_cb);
    p_retro_set_video_refresh(video_cb);
    p_retro_set_audio_sample(audio_sample);
    p_retro_set_audio_sample_batch(audio_batch);
    p_retro_set_input_poll(input_poll);
    p_retro_set_input_state(input_state);
    p_retro_init();

    FILE *f = fopen(rom, "rb");
    if (!f)
        die("cannot open %s", rom);
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    void *data = malloc(n);
    if (fread(data, 1, n, f) != (size_t)n)
        die("short read on %s", rom);
    fclose(f);

    struct retro_game_info info = { rom, data, (size_t)n, NULL };
    if (!p_retro_load_game(&info))
        die("core refused %s", rom);

    struct retro_system_av_info av;
    p_retro_get_system_av_info(&av);
    sample_rate = (unsigned)av.timing.sample_rate;
    printf("loaded %s: %ux%u @ %.2f Hz, %u Hz audio\n", rom,
           av.geometry.base_width, av.geometry.base_height,
           av.timing.fps, sample_rate);

    if (wav_path)
        wav_open(wav_path);
    if (frames)
        run_frames(frames);
    if (script)
        run_script(script);
    if (shot)
        save_bmp(shot);
    wav_close();
    p_retro_deinit();
    return 0;
}
