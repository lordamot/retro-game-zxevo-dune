/* evo.h - a ZX Evolution (BaseConf) machine wrapped around libxpeccy.
 *
 * libxpeccy (samstyle/Xpeccy) already models the board this project targets:
 * the PentEvo memory manager, the ATM/EGA video modes, the 3.5/7/14 MHz
 * turbo, the Beta Disk interface, TurboSound and the General Sound card.
 * What it does not have is a frontend that can be scripted, so this is one:
 * everything below is about driving that machine from a program rather than
 * from a Qt window.
 *
 * Two binaries are built on top of this file:
 *   evo-run   headless and scriptable  (tools/evo-emu/evo-run.c)
 *   evo-play  an SDL2 window with sound (tools/evo-emu/evo-play.c)
 */
#ifndef EVO_H
#define EVO_H

#include <stdint.h>
#include <stdio.h>

#include "libxpeccy/spectrum.h"
#include "libxpeccy/filetypes/filetypes.h"

#define EVO_MAX_W 1024
#define EVO_MAX_H 320

typedef struct {
    Computer *comp;

    int    audio_hz;        /* samples a second in the mix buffer          */
    int    ns_per_sample;   /* nanoseconds of emulated time per sample     */
    int    ns_acc;          /* leftover time since the last sample         */
    int16_t *audio;         /* interleaved stereo, filled each evo_frame() */
    int    audio_n;         /* samples (frames of L+R) written last frame  */
    int    audio_cap;
    long   frame_ns;        /* emulated time the last evo_frame() covered  */

    int    width, height;   /* of the current framebuffer, in pixels       */

    /* the OUT (0FDh),A profiling hook - see evo_profile_* below */
    int    profile;
    long   prof_ns[256];
    long   prof_hits[256];
    int    prof_mark;
    long   prof_last;
} evo;

/* Build a machine.  rom is the 512 KB BaseConf firmware; gsrom may be NULL,
 * in which case the General Sound card is left switched off. */
int  evo_init(evo *M, const char *rom, const char *gsrom, int audio_hz);

/* The board's battery-backed CMOS, where the firmware keeps its settings
 * (which drive is the virtual one, the CPU clock, the font).  Loading a
 * saved image is what a real machine's battery does. */
int  evo_load_nvram(evo *M, const char *path);
int  evo_save_nvram(evo *M, const char *path);
void evo_free(evo *M);

void evo_reset(evo *M);

/* Fill all 4 MB of RAM with pseudo-random bytes (seed 0 = zeros): what a
 * real machine's RAM holds at power-on, and what the emulator's zeroed
 * RAM hides - anything the game assumes is zero shows up. */
void evo_fill_ram(evo *M, unsigned seed);
int  evo_insert_trd(evo *M, const char *path, int drive);

/* Put an SD card image (a raw disk image: MBR and a FAT partition) in the
 * board's slot, for the firmware's own file browser and loaders.  0 = ok. */
int  evo_insert_sd(evo *M, const char *path);

/* Load an SPG v1.0 (uncompressed blocks) and start it: RAM filled, the
 * memory manager set up as the header asks, PC and SP loaded.  0 = ok. */
int  evo_load_spg(evo *M, const char *path);

/* Run exactly one video frame.  Audio for that frame lands in M->audio. */
void evo_frame(evo *M);

/* The ZX matrix, by the names evo-run's scripts and evo-play's window use:
 * "a".."z", "0".."9", "enter", "space", "caps", "sym", plus the composite
 * names the ROM's own keyboard makes ("up", "down", "left", "right", "del",
 * "edit", "break", "extend"), and "kj*" for the Kempston joystick. */
int  evo_key_lookup(const char *name);
void evo_key(evo *M, int code, int down);
void evo_key_release_all(evo *M);

/* Screen.  evo_pixel returns 0xRRGGBB. */
uint32_t evo_pixel(evo *M, int x, int y);
int  evo_save_bmp(evo *M, const char *path);

/* Memory as the CPU currently sees it, and by absolute RAM address. */
int  evo_peek(evo *M, int addr);
void evo_poke(evo *M, int addr, int val);
int  evo_ram(evo *M, int page, int off);
void evo_poke_ram(evo *M, int page, int off, int val);

/* Profiling: the game writes a mark number to port 0FDh and the emulated
 * time until the next mark is charged to it.  Nothing on real hardware
 * answers that port, so the marks can be left in the source. */
void evo_profile_enable(evo *M);
void evo_trace_gs(long n);
void evo_gs_clock(evo *M, int mhz); /* the card's Z80 clock in MHz */
void evo_gs_ram(evo *M, int kb);  /* the card's RAM, in KB, before spg */
void evo_gs_dead(void);        /* the card stops answering from now on */
void evo_gs_neo(evo *M);       /* the status port as a NeoGS's, a byte left in the latch */
void evo_write_trap(int lo, int hi, int page, int page3); /* report the first write into lo..hi */
void evo_pc_trap(int lo, int hi, int page); /* print the last fetches when PC reaches lo..hi (page < 0: any in window 0) */
void evo_gs_watch(int adr);     /* count the card's fetches at adr ... */
long evo_gs_hits(void);         /* ... since then */
void evo_profile_report(evo *M, FILE *f);

extern const char *evo_video_mode_name(int mode);

#endif
