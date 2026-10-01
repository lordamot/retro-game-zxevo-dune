/* evo-play.c - the same machine in an SDL2 window, with sound and a keyboard.
 *
 *   evo-play --rom F [--gsrom F] [--trd F.trd] [--spg F.spg] [--nvram F] [--scale N]
 *            [--nosound] [--frames N]
 *
 * The PC keyboard is mapped onto the ZX matrix by position: letters and
 * digits are themselves, Enter is ENTER, the arrow keys are the CAPS SHIFT
 * combinations the ROM reads as arrows, Left Shift is CAPS SHIFT, Left Ctrl
 * is SYMBOL SHIFT, and Backspace is CAPS SHIFT + 0 (DELETE).
 *
 * The machine runs at its own speed, not the monitor's: each frame is
 * held back until the wall clock has caught up with the emulated time it
 * covered (a ZX Evolution frame is about 20.5 ms, 48.8 a second).  Pacing
 * by the display's vsync ran it a frame per refresh - 23% fast on a 60 Hz
 * monitor, game and General Sound card alike, and the sound queue threw
 * away what it could not hold, so the music sounded rushed.
 *
 * --frames N quits after N frames; EVO_PLAY_STATS=1 in the environment
 * prints, on exit, how many frames ran in how much wall time.
 *
 *   F12       save tmp/evo-shot.bmp
 *   F5        reset
 *   Ctrl+Q    quit
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <SDL2/SDL.h>

#include "evo.h"

static evo M;

/* how much sound is kept queued ahead of the device, in milliseconds */
#define AUDIO_LAG_MS 80

typedef struct { SDL_Keycode sym; const char *name; } keymap_ent;

static const keymap_ent keymap[] = {
    {SDLK_1,"1"},{SDLK_2,"2"},{SDLK_3,"3"},{SDLK_4,"4"},{SDLK_5,"5"},
    {SDLK_6,"6"},{SDLK_7,"7"},{SDLK_8,"8"},{SDLK_9,"9"},{SDLK_0,"0"},
    {SDLK_q,"q"},{SDLK_w,"w"},{SDLK_e,"e"},{SDLK_r,"r"},{SDLK_t,"t"},
    {SDLK_y,"y"},{SDLK_u,"u"},{SDLK_i,"i"},{SDLK_o,"o"},{SDLK_p,"p"},
    {SDLK_a,"a"},{SDLK_s,"s"},{SDLK_d,"d"},{SDLK_f,"f"},{SDLK_g,"g"},
    {SDLK_h,"h"},{SDLK_j,"j"},{SDLK_k,"k"},{SDLK_l,"l"},{SDLK_RETURN,"enter"},
    {SDLK_LSHIFT,"caps"},{SDLK_RSHIFT,"caps"},
    {SDLK_z,"z"},{SDLK_x,"x"},{SDLK_c,"c"},{SDLK_v,"v"},
    {SDLK_b,"b"},{SDLK_n,"n"},{SDLK_m,"m"},
    {SDLK_LCTRL,"sym"},{SDLK_RCTRL,"sym"},{SDLK_SPACE,"space"},
    {SDLK_LEFT,"left"},{SDLK_RIGHT,"right"},{SDLK_UP,"up"},{SDLK_DOWN,"down"},
    {SDLK_BACKSPACE,"del"},{SDLK_ESCAPE,"break"},
    {0,NULL}
};

static void handle_key(SDL_Keycode sym, int down)
{
    int i;
    for (i = 0; keymap[i].name; i++) {
        if (keymap[i].sym == sym) {
            evo_key(&M, evo_key_lookup(keymap[i].name), down);
            return;
        }
    }
}

int main(int argc, char **argv)
{
    const char *rom = NULL, *gsrom = NULL, *trd = NULL, *nvram = NULL, *spg = NULL, *sd = NULL;
    int scale = 1, nosound = 0, i, running = 1;
    SDL_Window *win; SDL_Renderer *ren; SDL_Texture *tex;
    SDL_AudioSpec want, have; SDL_AudioDeviceID dev = 0;
    uint32_t *pixels;
    Uint64 tick_hz, due, start;
    long frames = 0, max_frames = 0;
    double emu_ns = 0;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--rom") && i + 1 < argc)        rom = argv[++i];
        else if (!strcmp(argv[i], "--gsrom") && i + 1 < argc) gsrom = argv[++i];
        else if (!strcmp(argv[i], "--trd") && i + 1 < argc)   trd = argv[++i];
        else if (!strcmp(argv[i], "--spg") && i + 1 < argc)   spg = argv[++i];
        else if (!strcmp(argv[i], "--sd") && i + 1 < argc)    sd = argv[++i];
        else if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--nvram") && i + 1 < argc)  nvram = argv[++i];
        else if (!strcmp(argv[i], "--nosound"))               nosound = 1;
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) max_frames = atol(argv[++i]);
        else { fprintf(stderr, "evo-play: unknown option %s\n", argv[i]); return 2; }
    }
    if (!rom) { fprintf(stderr, "evo-play: --rom is required\n"); return 2; }
    if (scale < 1) scale = 1;

    if (evo_init(&M, rom, gsrom, 44100)) {
        fprintf(stderr, "evo-play: cannot start the machine\n"); return 1;
    }
    if (nvram && evo_load_nvram(&M, nvram) == 0) evo_reset(&M);
    if (trd && evo_insert_trd(&M, trd, 0))
        fprintf(stderr, "evo-play: cannot load %s\n", trd);
    if (sd && evo_insert_sd(&M, sd))
        fprintf(stderr, "evo-play: cannot open %s\n", sd);
    if (spg && evo_load_spg(&M, spg))
        fprintf(stderr, "evo-play: cannot load %s\n", spg);

    if (SDL_Init(SDL_INIT_VIDEO | (nosound ? 0 : SDL_INIT_AUDIO)) < 0) {
        fprintf(stderr, "evo-play: SDL_Init: %s\n", SDL_GetError()); return 1;
    }
    win = SDL_CreateWindow("ZX Evolution", SDL_WINDOWPOS_CENTERED,
                           SDL_WINDOWPOS_CENTERED,
                           M.width * scale, M.height * scale, 0);
    ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED);
    tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                            SDL_TEXTUREACCESS_STREAMING, M.width, M.height);
    pixels = malloc(sizeof(uint32_t) * M.width * M.height);

    if (!nosound) {
        SDL_zero(want);
        want.freq = M.audio_hz; want.format = AUDIO_S16SYS;
        want.channels = 2; want.samples = 1024;
        dev = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
        if (dev) {
            /* start with AUDIO_LAG of silence queued, the cushion */
            size_t n = (size_t)M.audio_hz * AUDIO_LAG_MS / 1000 * 4;
            void *quiet = calloc(1, n);
            if (quiet) { SDL_QueueAudio(dev, quiet, (Uint32)n); free(quiet); }
            SDL_PauseAudioDevice(dev, 0);
        }
    }

    tick_hz = SDL_GetPerformanceFrequency();
    due = start = SDL_GetPerformanceCounter();
    while (running) {
        SDL_Event ev;
        Uint64 now;
        int x, y;
        while (SDL_PollEvent(&ev)) {
            switch (ev.type) {
            case SDL_QUIT: running = 0; break;
            case SDL_KEYDOWN:
                /* SDL repeats key-down while a key is held.  A repeat is not
                 * a new press - passing it on used to jam the key down for
                 * good - and the game does its own repeating anyway. */
                if (ev.key.repeat) break;
                if (ev.key.keysym.sym == SDLK_q && (SDL_GetModState() & KMOD_CTRL)) { running = 0; break; }
                if (ev.key.keysym.sym == SDLK_F12) { evo_save_bmp(&M, "tmp/evo-shot.bmp"); break; }
                if (ev.key.keysym.sym == SDLK_F5)  { evo_reset(&M); break; }
                handle_key(ev.key.keysym.sym, 1);
                break;
            case SDL_KEYUP: handle_key(ev.key.keysym.sym, 0); break;
            case SDL_WINDOWEVENT:
                /* Alt-tabbing away eats the key-up, so the machine would be
                 * left holding whatever was down when the window lost focus. */
                if (ev.window.event == SDL_WINDOWEVENT_FOCUS_LOST)
                    evo_key_release_all(&M);
                break;
            }
        }
        evo_frame(&M);
        if (dev) {
            /* the queue is kept near AUDIO_LAG: enough that the device never
             * runs dry between frames, little enough that a key sounds when
             * pressed.  The frame pacing below steers it there; a queue far
             * over (a stall) drops the frame's sound rather than lag more */
            if (SDL_GetQueuedAudioSize(dev) < (Uint32)(M.audio_hz * 4 * 3 * AUDIO_LAG_MS / 1000))
                SDL_QueueAudio(dev, M.audio, (Uint32)M.audio_n * 2);
        }
        for (y = 0; y < M.height; y++)
            for (x = 0; x < M.width; x++)
                pixels[y * M.width + x] = 0xff000000u | evo_pixel(&M, x, y);
        SDL_UpdateTexture(tex, NULL, pixels, M.width * 4);
        SDL_RenderClear(ren);
        SDL_RenderCopy(ren, tex, NULL, NULL);
        SDL_RenderPresent(ren);

        /* wait until the frame's emulated time has passed on the wall
         * clock; after a stall (a dragged window, a busy host) start
         * counting again from now rather than racing to catch up */
        frames++; emu_ns += M.frame_ns;
        if (max_frames && frames >= max_frames) running = 0;
        due += (Uint64)((double)M.frame_ns * tick_hz / 1e9);
        if (dev) {
            /* the sound card's clock and ours drift apart a little: a
             * millisecond a frame either way keeps the queue near its mark */
            Uint32 queued_ms = SDL_GetQueuedAudioSize(dev) / 4 * 1000 / (Uint32)M.audio_hz;
            if (queued_ms > AUDIO_LAG_MS * 3 / 2) due += tick_hz / 1000;
            else if (queued_ms < AUDIO_LAG_MS / 2) due -= tick_hz / 1000;
        }
        now = SDL_GetPerformanceCounter();
        if (now > due + tick_hz / 5)
            due = now;
        else if (due > now) {
            Uint32 ms = (Uint32)((due - now) * 1000 / tick_hz);
            if (ms > 1) SDL_Delay(ms - 1);
            while (SDL_GetPerformanceCounter() < due)
                ;
        }
    }

    if (getenv("EVO_PLAY_STATS")) {
        double wall = (double)(SDL_GetPerformanceCounter() - start) / tick_hz;
        fprintf(stderr, "evo-play: %ld frames in %.2f s of wall time, %.2f s "
                "emulated (%.2f frames a second)\n", frames, wall,
                emu_ns / 1e9, frames / wall);
    }
    if (dev) SDL_CloseAudioDevice(dev);
    SDL_DestroyTexture(tex); SDL_DestroyRenderer(ren); SDL_DestroyWindow(win);
    SDL_Quit();
    free(pixels);
    evo_free(&M);
    return 0;
}
