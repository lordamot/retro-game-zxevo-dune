/* retro-play - the two reference machines in an SDL2 window.

   The playable twin of retro-run: the same libretro frontend, but with a
   picture, sound and a keyboard instead of a script.  It is what
   `make run nes` and `make run sega` open, so the deconstructions under
   orig/nes/ and orig/sega/ can be rebuilt and then actually played -
   which is the only check that really says whether a change to them
   works.

     retro-play --core CORE.so --rom GAME [--scale N] [--nosound]
                [--title NAME] [--shot FILE.bmp] [--fps N]

   Keyboard, laid out for both pads at once:

     arrows            d-pad
     Z X C             Mega Drive A B C  /  NES B, A, (unused)
     A S D             RetroPad Y B A
     Q W               L R
     Enter             Start          Right Shift  Select
     F12               screenshot into tmp/
     F5                reset
     Escape, Ctrl+Q    quit

   The NES has two buttons and the Mega Drive three, so both rows are live
   on both machines: on the NES, Z is B and X is A.
*/

#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <SDL2/SDL.h>

#include "libretro.h"

static void *core;
static uint32_t buttons;
static const void *frame_data;
static unsigned frame_w, frame_h;
static size_t frame_pitch;
static unsigned pixel_format = RETRO_PIXEL_FORMAT_0RGB1555;
static SDL_AudioDeviceID audio;
static int muted;

static void (*p_retro_init)(void);
static void (*p_retro_deinit)(void);
static void (*p_retro_run)(void);
static void (*p_retro_reset)(void);
static bool (*p_retro_load_game)(const struct retro_game_info *);
static void (*p_retro_get_system_av_info)(struct retro_system_av_info *);
static void (*p_retro_set_environment)(retro_environment_t);
static void (*p_retro_set_video_refresh)(retro_video_refresh_t);
static void (*p_retro_set_audio_sample)(retro_audio_sample_t);
static void (*p_retro_set_audio_sample_batch)(retro_audio_sample_batch_t);
static void (*p_retro_set_input_poll)(retro_input_poll_t);
static void (*p_retro_set_input_state)(retro_input_state_t);

static void die(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "retro-play: ");
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
        *(unsigned *)data = 0;
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

/* The core hands us however many samples a frame took; SDL's queue is what
   paces us, so there is no separate frame timer. */
static void queue(const int16_t *d, size_t frames)
{
    if (audio && !muted)
        SDL_QueueAudio(audio, d, frames * 4);
}

static void audio_sample(int16_t l, int16_t r)
{
    int16_t s[2] = { l, r };
    queue(s, 1);
}

static size_t audio_batch(const int16_t *d, size_t frames)
{
    queue(d, frames);
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

/* The Mega Drive's A, B and C are RetroPad Y, B and A - Genesis Plus GX
   does not map the same-named buttons to each other - so Z X C is A B C on
   the Mega Drive and B, A on the NES, which only has two. */
static const struct { SDL_Keycode key; int id; } KEYS[] = {
    { SDLK_UP,     RETRO_DEVICE_ID_JOYPAD_UP },
    { SDLK_DOWN,   RETRO_DEVICE_ID_JOYPAD_DOWN },
    { SDLK_LEFT,   RETRO_DEVICE_ID_JOYPAD_LEFT },
    { SDLK_RIGHT,  RETRO_DEVICE_ID_JOYPAD_RIGHT },
    { SDLK_z,      RETRO_DEVICE_ID_JOYPAD_Y },      /* MD A / NES B */
    { SDLK_x,      RETRO_DEVICE_ID_JOYPAD_B },      /* MD B / NES A */
    { SDLK_c,      RETRO_DEVICE_ID_JOYPAD_A },      /* MD C          */
    { SDLK_a,      RETRO_DEVICE_ID_JOYPAD_Y },
    { SDLK_s,      RETRO_DEVICE_ID_JOYPAD_B },
    { SDLK_d,      RETRO_DEVICE_ID_JOYPAD_A },
    { SDLK_q,      RETRO_DEVICE_ID_JOYPAD_L },
    { SDLK_w,      RETRO_DEVICE_ID_JOYPAD_R },
    { SDLK_RETURN, RETRO_DEVICE_ID_JOYPAD_START },
    { SDLK_RSHIFT, RETRO_DEVICE_ID_JOYPAD_SELECT },
    { SDLK_TAB,    RETRO_DEVICE_ID_JOYPAD_SELECT },
    { 0, 0 }
};

static void put32(unsigned char *p, uint32_t v)
{
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}

static void pixel(const unsigned char *src, unsigned x,
                  unsigned *r, unsigned *g, unsigned *b)
{
    if (pixel_format == RETRO_PIXEL_FORMAT_XRGB8888) {
        uint32_t p = ((const uint32_t *)src)[x];
        *r = (p >> 16) & 0xFF; *g = (p >> 8) & 0xFF; *b = p & 0xFF;
    } else if (pixel_format == RETRO_PIXEL_FORMAT_RGB565) {
        uint16_t p = ((const uint16_t *)src)[x];
        *r = ((p >> 11) & 0x1F) * 255 / 31;
        *g = ((p >> 5) & 0x3F) * 255 / 63;
        *b = (p & 0x1F) * 255 / 31;
    } else {
        uint16_t p = ((const uint16_t *)src)[x];
        *r = ((p >> 10) & 0x1F) * 255 / 31;
        *g = ((p >> 5) & 0x1F) * 255 / 31;
        *b = (p & 0x1F) * 255 / 31;
    }
}

static void save_bmp(const char *path)
{
    if (!frame_data)
        return;
    unsigned row = (frame_w * 3 + 3) & ~3u;
    unsigned char hdr[54] = { 'B', 'M' };
    put32(hdr + 2, 54 + row * frame_h);
    put32(hdr + 10, 54);
    put32(hdr + 14, 40);
    put32(hdr + 18, frame_w);
    put32(hdr + 22, frame_h);
    hdr[26] = 1; hdr[28] = 24;
    put32(hdr + 34, row * frame_h);
    FILE *f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "retro-play: cannot write %s\n", path);
        return;
    }
    fwrite(hdr, 1, sizeof hdr, f);
    unsigned char *line = calloc(1, row);
    for (int y = (int)frame_h - 1; y >= 0; y--) {
        const unsigned char *src = (const unsigned char *)frame_data
                                   + (size_t)y * frame_pitch;
        for (unsigned x = 0; x < frame_w; x++) {
            unsigned r, g, b;
            pixel(src, x, &r, &g, &b);
            line[x * 3] = b; line[x * 3 + 1] = g; line[x * 3 + 2] = r;
        }
        fwrite(line, 1, row, f);
    }
    free(line);
    fclose(f);
    printf("shot %s (%ux%u)\n", path, frame_w, frame_h);
}

int main(int argc, char **argv)
{
    const char *corepath = NULL, *rompath = NULL, *title = "retro-play";
    const char *shot = "tmp/retro-shot.bmp";
    int scale = 3, i, running = 1;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--core") && i + 1 < argc)       corepath = argv[++i];
        else if (!strcmp(argv[i], "--rom") && i + 1 < argc)   rompath = argv[++i];
        else if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--title") && i + 1 < argc) title = argv[++i];
        else if (!strcmp(argv[i], "--shot") && i + 1 < argc)  shot = argv[++i];
        else if (!strcmp(argv[i], "--nosound"))               muted = 1;
        else die("unknown option %s (see the header comment)", argv[i]);
    }
    if (!corepath || !rompath)
        die("--core and --rom are both required");
    if (scale < 1) scale = 1;

    core = dlopen(corepath, RTLD_NOW);
    if (!core)
        die("%s", dlerror());
    p_retro_init = sym("retro_init");
    p_retro_deinit = sym("retro_deinit");
    p_retro_run = sym("retro_run");
    p_retro_reset = sym("retro_reset");
    p_retro_load_game = sym("retro_load_game");
    p_retro_get_system_av_info = sym("retro_get_system_av_info");
    p_retro_set_environment = sym("retro_set_environment");
    p_retro_set_video_refresh = sym("retro_set_video_refresh");
    p_retro_set_audio_sample = sym("retro_set_audio_sample");
    p_retro_set_audio_sample_batch = sym("retro_set_audio_sample_batch");
    p_retro_set_input_poll = sym("retro_set_input_poll");
    p_retro_set_input_state = sym("retro_set_input_state");

    p_retro_set_environment(env_cb);
    p_retro_init();
    p_retro_set_video_refresh(video_cb);
    p_retro_set_audio_sample(audio_sample);
    p_retro_set_audio_sample_batch(audio_batch);
    p_retro_set_input_poll(input_poll);
    p_retro_set_input_state(input_state);

    FILE *f = fopen(rompath, "rb");
    if (!f)
        die("cannot open %s", rompath);
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    void *buf = malloc(n);
    if (fread(buf, 1, n, f) != (size_t)n)
        die("short read on %s", rompath);
    fclose(f);

    struct retro_game_info game = { rompath, buf, (size_t)n, NULL };
    if (!p_retro_load_game(&game))
        die("the core refused %s", rompath);

    struct retro_system_av_info av;
    p_retro_get_system_av_info(&av);
    unsigned w = av.geometry.base_width ? av.geometry.base_width : 320;
    unsigned h = av.geometry.base_height ? av.geometry.base_height : 240;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO))
        die("SDL: %s", SDL_GetError());
    SDL_Window *win = SDL_CreateWindow(title, SDL_WINDOWPOS_CENTERED,
                                       SDL_WINDOWPOS_CENTERED,
                                       w * scale, h * scale,
                                       SDL_WINDOW_RESIZABLE);
    SDL_Renderer *ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
    SDL_RenderSetLogicalSize(ren, w, h);
    SDL_Texture *tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                                         SDL_TEXTUREACCESS_STREAMING,
                                         av.geometry.max_width ?
                                         av.geometry.max_width : w,
                                         av.geometry.max_height ?
                                         av.geometry.max_height : h);
    if (!muted) {
        SDL_AudioSpec want = { 0 }, have;
        want.freq = (int)(av.timing.sample_rate ? av.timing.sample_rate : 44100);
        want.format = AUDIO_S16SYS;
        want.channels = 2;
        want.samples = 1024;
        audio = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
        if (audio)
            SDL_PauseAudioDevice(audio, 0);
        else
            fprintf(stderr, "retro-play: no audio device, playing silent\n");
    }

    uint32_t *pixels = malloc((size_t)w * h * 4 * 4);
    double fps = av.timing.fps ? av.timing.fps : 60.0;
    uint32_t next = SDL_GetTicks();

    while (running) {
        SDL_Event ev;
        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT)
                running = 0;
            else if (ev.type == SDL_KEYDOWN || ev.type == SDL_KEYUP) {
                int down = ev.type == SDL_KEYDOWN;
                SDL_Keycode k = ev.key.keysym.sym;
                if (down && !ev.key.repeat) {
                    if (k == SDLK_ESCAPE ||
                        (k == SDLK_q && (ev.key.keysym.mod & KMOD_CTRL)))
                        running = 0;
                    else if (k == SDLK_F12)
                        save_bmp(shot);
                    else if (k == SDLK_F5)
                        p_retro_reset();
                }
                for (i = 0; KEYS[i].key; i++)
                    if (KEYS[i].key == k) {
                        if (down)
                            buttons |= 1u << KEYS[i].id;
                        else
                            buttons &= ~(1u << KEYS[i].id);
                    }
            }
        }

        p_retro_run();

        if (frame_data) {
            for (unsigned y = 0; y < frame_h; y++) {
                const unsigned char *src = (const unsigned char *)frame_data
                                           + (size_t)y * frame_pitch;
                uint32_t *dst = pixels + (size_t)y * frame_w;
                for (unsigned x = 0; x < frame_w; x++) {
                    unsigned r, g, b;
                    pixel(src, x, &r, &g, &b);
                    dst[x] = 0xFF000000u | (r << 16) | (g << 8) | b;
                }
            }
            SDL_Rect area = { 0, 0, (int)frame_w, (int)frame_h };
            SDL_UpdateTexture(tex, &area, pixels, frame_w * 4);
            SDL_RenderSetLogicalSize(ren, (int)frame_w, (int)frame_h);
            SDL_RenderClear(ren);
            SDL_RenderCopy(ren, tex, &area, NULL);
            SDL_RenderPresent(ren);
        }

        /* Sound is queued a frame at a time, so pace on the wall clock and
           let a backed-up queue slow us down rather than run ahead. */
        next += (uint32_t)(1000.0 / fps);
        uint32_t now = SDL_GetTicks();
        if (next > now)
            SDL_Delay(next - now);
        else
            next = now;
        if (audio && SDL_GetQueuedAudioSize(audio) > 8192 * 4)
            SDL_Delay(4);
    }

    if (audio)
        SDL_CloseAudioDevice(audio);
    SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    p_retro_deinit();
    return 0;
}
