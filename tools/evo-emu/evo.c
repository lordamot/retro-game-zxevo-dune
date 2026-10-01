/* evo.c - the machine.  See evo.h for what this is and why it exists. */
#include <stdlib.h>
#include <string.h>

#include "evo.h"
#include "libxpeccy/cpu/Z80/z80.h"

/* ------------------------------------------------------------------ video
 *
 * libxpeccy draws into a global framebuffer, one 32-bit RGBA pixel at a
 * time, and lets the frontend decide how many pixels a "dot" of the source
 * signal becomes.  A dot is one ZX pixel, one EGA pixel or *two* text-mode
 * pixels, so the horizontal step has to be two output pixels per dot for the
 * 640-wide text and 320-wide EGA modes to come out at their real width.  The
 * vertical step is two as well, purely so a saved screenshot has the right
 * aspect ratio instead of being squashed flat.
 */
#define XSTEP 0x200
#define YSTEP 0x200

static void video_setup(evo *M)
{
    /* The Pentagon frame: 448x320 dots of which 384x288 are visible.  ZX
     * Evolution keeps Pentagon timings, which is why a ZX Spectrum program
     * written for a Pentagon runs on it unmodified. */
    vLayout lay = { {448, 320}, {72, 48}, {64, 32}, {256, 192}, {0, 0}, 64 };
    vid_set_layout(M->comp->vid, &lay);
    vid_set_border(M->comp->vid, 1.0);

    xstep = XSTEP; ystep = YSTEP;
    lefSkip = rigSkip = topSkip = botSkip = pixSkip = 0;
    M->width  = (M->comp->vid->vsze.x * XSTEP) >> 8;
    M->height = (M->comp->vid->vsze.y * YSTEP) >> 8;
    bytesPerLine = M->width * 4;
    bufSize = bytesPerLine * M->height;
}

/* The 16 ZX colours.  A program that wants the other 4096 writes them
 * itself through the ATM palette port; this is only what the machine comes
 * up with. */
static void palette_setup(evo *M)
{
    xColor col;
    int i;
    for (i = 0; i < 16; i++) {
        col.b = (i & 1) ? ((i & 8) ? 0xff : 0xaa) : 0x00;
        col.r = (i & 2) ? ((i & 8) ? 0xff : 0xaa) : 0x00;
        col.g = (i & 4) ? ((i & 8) ? 0xff : 0xaa) : 0x00;
        vid_set_bcol(M->comp->vid, i, col);
        vid_set_col(M->comp->vid, i, col);
    }
}

const char *evo_video_mode_name(int mode)
{
    switch (mode) {
    case VID_NORMAL:   return "zx";
    case VID_ALCO:     return "alco16c";
    case VID_ATM_EGA:  return "ega16c";
    case VID_ATM_TEXT: return "atmtext";
    case VID_ATM_HWM:  return "atmhwmc";
    case VID_HWMC:     return "zxhwmc";
    case VID_EVO_TEXT: return "evotext";
    default:           return "?";
    }
}

uint32_t evo_pixel(evo *M, int x, int y)
{
    unsigned char *p;
    if (x < 0 || y < 0 || x >= M->width || y >= M->height) return 0;
    p = scrimg + (size_t)y * bytesPerLine + (size_t)x * 4;
    return ((uint32_t)p[0] << 16) | ((uint32_t)p[1] << 8) | p[2];
}

int evo_save_bmp(evo *M, const char *path)
{
    FILE *f = fopen(path, "wb");
    unsigned char hdr[54];
    int w = M->width, h = M->height, y, x;
    int rowbytes = w * 3, pad = (4 - (rowbytes & 3)) & 3;
    unsigned int dat = (unsigned int)(rowbytes + pad) * h;
    unsigned int fsz = 54 + dat;
    if (!f) return -1;
    memset(hdr, 0, sizeof hdr);
    hdr[0] = 'B'; hdr[1] = 'M';
    memcpy(hdr + 2, &fsz, 4);
    hdr[10] = 54; hdr[14] = 40;
    memcpy(hdr + 18, &w, 4); memcpy(hdr + 22, &h, 4);
    hdr[26] = 1; hdr[28] = 24;
    memcpy(hdr + 34, &dat, 4);
    fwrite(hdr, 1, sizeof hdr, f);
    for (y = h - 1; y >= 0; y--) {          /* BMP rows run bottom-up */
        unsigned char *row = scrimg + (size_t)y * bytesPerLine;
        for (x = 0; x < w; x++) {
            unsigned char *q = row + (size_t)x * 4;
            fputc(q[2], f); fputc(q[1], f); fputc(q[0], f);
        }
        for (x = 0; x < pad; x++) fputc(0, f);
    }
    fclose(f);
    return 0;
}

/* --------------------------------------------------------------- profiling
 *
 * OUT (0FDh),A with A = a mark number.  Nothing on a real ZX Evolution
 * answers port 0FDh with A below 40h (7FFD paging needs A15..A14 of the
 * port, i.e. bits 6-7 of A, to be 01), so the marks are inert on hardware.
 */
static cbiw   orig_iwr;
static cbir   orig_ird;
static evo   *prof_owner;

/* --gstrace: the first N port accesses between the host and the sound card,
 * which is the only way to see where a handshake stops. */
static long   gstrace;
static evo   *traced;           /* set at start-up, unlike prof_owner */

/* gsdead: from now on the card takes no command and gives no byte - its
 * status port reads "command pending, no data" for ever and its writes
 * are dropped - which is how a real card that has crashed looks to the
 * host (its mixer plays on).  Tests the host's bounded waits. */
static int    gsdead;

/* gsneo: the status port as a NeoGS drives it - all eight lines, bits 1-6
 * being whatever its FPGA's synthesis made of "don't care" (zxbus.v:
 * { data_bit, 6'bXXXXXX, command_bit }); modelled as the data register's,
 * the card's last answer - not libxpeccy's 1s of an original GS's pull-ups.
 * And a NeoGS is not reset with the machine, so an earlier program's
 * answer may still be in the latch: gsneo leaves one there. */
static int    gsneo;

static int trace_ird(int port, void *ptr)
{
    int v;
    if (gsdead && (port & 0xF7) == 0xB3)
        return (port & 0xff) == 0xBB ? 0x01 : 0xFF;
    v = orig_ird(port, ptr);
    if (gsneo && (port & 0xff) == 0xBB)
        v = (v & 0x81) | (traced->comp->gs->pb3_gs & 0x7e);
    if (gstrace > 0 && (port & 0xF7) == 0xB3) {
        printf("gs  IN  %04X -> %02X   card pc=%04X\n", port, v & 0xff,
               cpu_get_pc(traced->comp->gs->cpu));
        gstrace--;
    }
    return v;
}

static void profile_iwr(int port, int val, void *ptr)
{
    if (gsdead && (port & 0xF7) == 0xB3)
        return;
    if (gstrace > 0 && (port & 0xF7) == 0xB3) {
        printf("gs  OUT %04X <- %02X   card pc=%04X\n", port, val & 0xff,
               cpu_get_pc(traced->comp->gs->cpu));
        gstrace--;
    }
    if (prof_owner && prof_owner->profile && (port & 0xff) == 0xfd
        && (port >> 8) < 0x40) {
        evo *M = prof_owner;
        long now = M->comp->tickCount;
        M->prof_ns[M->prof_mark & 0xff] += now - M->prof_last;
        M->prof_hits[(port >> 8) & 0xff]++;
        M->prof_mark = (port >> 8) & 0xff;
        M->prof_last = now;
        return;
    }
    orig_iwr(port, val, ptr);
}

void evo_trace_gs(long n)
{
    gstrace = n;
}

void evo_gs_dead(void)
{
    gsdead = 1;
}

void evo_gs_neo(evo *M)
{
    gsneo = 1;
    M->comp->gs->pb3_gs = 0x40;
    M->comp->gs->pstate |= 0x80;
}

/* gsram KB: the card's RAM this big (a power of two; pages above it are
 * the low ones again), before the ROM's power-on test runs - i.e. before
 * spg.  libxpeccy gives the card 2 MB. */
void evo_gs_ram(evo *M, int kb)
{
    memSetSize(M->comp->gs->mem, kb * 1024, 0);
}

/* gsclock MHZ: the card's Z80 at this clock, its interrupt still 37.5 kHz
 * (the ZX-MultiSound: 16 MHz, its counter on a 12 MHz clock). */
void evo_gs_clock(evo *M, int mhz)
{
    M->comp->gs->ns_per_tick = 1000 / mhz;
    M->comp->gs->int_ticks = mhz * 1000000 / 37500;
}

void evo_profile_enable(evo *M)
{
    M->profile = 1;
    prof_owner = M;
    memset(M->prof_ns, 0, sizeof M->prof_ns);
    memset(M->prof_hits, 0, sizeof M->prof_hits);
    M->prof_mark = 0;
    M->prof_last = M->comp->tickCount;
}

void evo_profile_report(evo *M, FILE *f)
{
    int i;
    long total = 0;
    for (i = 0; i < 256; i++) total += M->prof_ns[i];
    fprintf(f, "mark      cycles      hits    %%\n");
    for (i = 0; i < 256; i++) {
        if (!M->prof_ns[i] && !M->prof_hits[i]) continue;
        fprintf(f, "%3d  %11ld  %8ld  %5.1f\n", i, M->prof_ns[i],
                M->prof_hits[i], total ? 100.0 * M->prof_ns[i] / total : 0.0);
    }
    fprintf(f, "total%11ld\n", total);
}

/* ------------------------------------------------------------------- setup */

static int load_file(const char *path, unsigned char *dst, int cap)
{
    FILE *f = fopen(path, "rb");
    int n;
    if (!f) return -1;
    n = (int)fread(dst, 1, cap, f);
    fclose(f);
    return n;
}

/* The sound card's page port: libxpeccy gives the card 2 MB but decodes
 * only five bits of port 0, which leaves its ROM 30 pages (960 KB).  The
 * card this port targets has 2 MB, and the ROM tests up to 63 pages, so
 * decode six: page N (1-63) is the RAM's 32 KB block N-1, as before. */
static cbiw gs_orig_iwr;

static void gs_page_iwr(int port, int val, void *ptr)
{
    GSound *gs = (GSound *)ptr;
    if ((port & 0x0f) != 0) { gs_orig_iwr(port, val, ptr); return; }
    gs->rp0 = val & 0xff;
    val &= 0x3f;
    if (val == 0) {
        memSetBank(gs->mem, 0x80, MEM_ROM, 0, MEM_16K, NULL, NULL, NULL);
        memSetBank(gs->mem, 0xc0, MEM_ROM, 1, MEM_16K, NULL, NULL, NULL);
    } else {
        memSetBank(gs->mem, 0x80, MEM_RAM, (val - 1) << 1, MEM_16K, NULL, NULL, NULL);
        memSetBank(gs->mem, 0xc0, MEM_RAM, ((val - 1) << 1) + 1, MEM_16K, NULL, NULL, NULL);
    }
}

/* The sound card's instruction fetches at one address, counted (evo-run's
 * gswatch/gshits): how often its ROM runs a routine - $13B9, the interrupt
 * finding the next buffer empty, counts the music's underruns. */
static cbmr gs_orig_mrd;
static int  gs_watch = -1;
static long gs_hits;

static int gs_count_mrd(int adr, int m1, void *ptr)
{
    if (m1 && adr == gs_watch) gs_hits++;
    return gs_orig_mrd(adr, m1, ptr);
}

void evo_gs_watch(int adr) { gs_watch = adr; gs_hits = 0; }
long evo_gs_hits(void) { return gs_hits; }

/* pctrap LO HI: the host CPU's last PC_RING opcode fetches are kept, each
 * with the page in window 0 at the time, and printed - oldest first, then
 * SP - the first time it fetches an opcode from LO..HI.  For a crash that
 * ends somewhere it should never run (window 1 is never code): the ring
 * says how it got there. */
#define PC_RING 64
static cbmr  host_orig_mrd;
static evo  *host_owner;
static int   pc_ring[PC_RING], pc_page[PC_RING], pc_n;
static int   pc_lo = -1, pc_hi = -1, pc_pg = -1;   /* pc_pg: only with this page in window 0 */

static int host_mrd(int adr, int m1, void *ptr)
{
    if (m1) {
        pc_ring[pc_n % PC_RING] = adr;
        pc_page[pc_n % PC_RING] = host_owner->comp->mem->map[0].num >> 6;
        pc_n++;
        if (pc_lo >= 0 && adr >= pc_lo && adr <= pc_hi
            && (pc_pg < 0 || pc_pg == (host_owner->comp->mem->map[0].num >> 6))) {
            int i, k = pc_n > PC_RING ? pc_n - PC_RING : 0;
            bool ok;
            printf("pctrap: fetch at %04X (window 0 = page %d); the last fetches:\n",
                   adr, host_owner->comp->mem->map[0].num >> 6);
            for (i = k; i < pc_n; i++)
                printf("  %3d:%04X%s", pc_page[i % PC_RING], pc_ring[i % PC_RING],
                       ((i - k) % 8 == 7) ? "\n" : "");
            printf("\n  sp=%04X\n",
                   cpu_get_reg(host_owner->comp->cpu, "sp", &ok) & 0xffff);
            pc_lo = pc_hi = -1;
        }
    }
    return host_orig_mrd(adr, m1, ptr);
}

void evo_pc_trap(int lo, int hi, int page) { pc_lo = lo; pc_hi = hi; pc_pg = page; }

/* wtrap LO HI [PAGE]: the first write into LO..HI of the address space
 * (with PAGE in window 0, or any) is reported with the value, PC and the
 * last fetches.  The stub ($0000-$09xx of every bank) owns no variable,
 * so any write there is a bug that will show up somewhere else later. */
static cbmw  host_orig_mwr;
static int   w_lo = -1, w_hi = -1, w_pg = -1, w_pg3 = -1;   /* w_pg3: only with this page in window 3 */
static int   w_left;                                          /* hits still to report */

static void host_mwr(int adr, int val, void *ptr)
{
    if (w_lo >= 0 && adr >= w_lo && adr <= w_hi
        && (w_pg < 0 || w_pg == (host_owner->comp->mem->map[0].num >> 6))
        && (w_pg3 < 0 || w_pg3 == (host_owner->comp->mem->map[0xc0].num >> 6))) {
        int i, k = pc_n > PC_RING ? pc_n - PC_RING : 0;
        bool ok;
        printf("wtrap: write %02X at %04X (window 0 = page %d, window 3 = page %d) from pc=%04X; the last fetches:\n",
               val & 0xff, adr, host_owner->comp->mem->map[0].num >> 6,
               host_owner->comp->mem->map[0xc0].num >> 6,
               cpu_get_pc(host_owner->comp->cpu));
        for (i = k; i < pc_n; i++)
            printf("  %3d:%04X%s", pc_page[i % PC_RING], pc_ring[i % PC_RING],
                   ((i - k) % 8 == 7) ? "\n" : "");
        printf("\n");
        if (--w_left <= 0)
            w_lo = w_hi = -1;
    }
    host_orig_mwr(adr, val, ptr);
}

void evo_write_trap(int lo, int hi, int page, int page3) { w_lo = lo; w_hi = hi; w_pg = page; w_pg3 = page3; w_left = 12; }

int evo_init(evo *M, const char *rom, const char *gsrom, int audio_hz)
{
    memset(M, 0, sizeof *M);
    M->comp = compCreate();
    if (!compSetHardware(M->comp, "PentEvo")) return -1;

    memSetSize(M->comp->mem, MEM_4M, -1);
    memset(M->comp->mem->romData, 0xff, MEM_512K);
    if (load_file(rom, M->comp->mem->romData, MEM_512K) <= 0) return -2;
    memSetSize(M->comp->mem, -1, MEM_512K);

    /* Two AY chips: the ZX Evolution carries a TurboSound, and a program
     * that only uses one simply never selects the second. */
    M->comp->ts->type = TS_NEDOPC;

    if (gsrom) {
        memset((char *)M->comp->gs->mem->romData, 0xff, MEM_32K);
        if (load_file(gsrom, M->comp->gs->mem->romData, MEM_32K) > 0)
            M->comp->gs->enable = 1;
    }
    gsReset(M->comp->gs);
    gs_orig_iwr = M->comp->gs->cpu->iwr;
    M->comp->gs->cpu->iwr = gs_page_iwr;
    gs_orig_mrd = M->comp->gs->cpu->mrd;
    M->comp->gs->cpu->mrd = gs_count_mrd;

    difSetHW(M->comp->dif, DIF_BDI);
    /* Read the disk as fast as the emulator can rather than at a real
     * drive's 250 kbit/s.  The game loads about 180 KB, which is half a
     * minute of honest floppy; nobody testing a change wants to sit
     * through that, and nothing about the port depends on the timing. */
    fdcFlag |= FDC_FAST;


    video_setup(M);
    palette_setup(M);

    M->audio_hz = audio_hz > 0 ? audio_hz : 44100;
    M->ns_per_sample = 1000000000 / M->audio_hz;
    M->audio_cap = M->audio_hz / 25 * 2 + 64;   /* two frames' worth, stereo */
    M->audio = malloc(sizeof(int16_t) * M->audio_cap);

    orig_iwr = M->comp->cpu->iwr;
    M->comp->cpu->iwr = profile_iwr;
    orig_ird = M->comp->cpu->ird;
    M->comp->cpu->ird = trace_ird;
    traced = M;
    host_orig_mrd = M->comp->cpu->mrd;
    M->comp->cpu->mrd = host_mrd;
    host_orig_mwr = M->comp->cpu->mwr;
    M->comp->cpu->mwr = host_mwr;
    host_owner = M;

    evo_key_release_all(M);
    evo_reset(M);
    return 0;
}

int evo_load_nvram(evo *M, const char *path)
{
    FILE *f = fopen(path, "rb");
    size_t n;
    if (!f) return -1;
    n = fread(M->comp->cmos.data, 1, sizeof M->comp->cmos.data, f);
    fclose(f);
    return n == sizeof M->comp->cmos.data ? 0 : -1;
}

int evo_save_nvram(evo *M, const char *path)
{
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fwrite(M->comp->cmos.data, 1, sizeof M->comp->cmos.data, f);
    fclose(f);
    return 0;
}

void evo_free(evo *M)
{
    free(M->audio);
    if (M->comp) compDestroy(M->comp);
    M->comp = NULL;
    M->audio = NULL;
    if (prof_owner == M) prof_owner = NULL;
}

void evo_reset(evo *M)
{
    compReset(M->comp, RES_DEFAULT);
    M->comp->flgBRK = 0;
}

void evo_fill_ram(evo *M, unsigned seed)
{
    unsigned char *r = M->comp->mem->ramData;
    unsigned x = seed;
    size_t i;
    for (i = 0; i < (size_t)256 * 0x4000; i++) {
        x = x * 1103515245u + 12345u;
        r[i] = seed ? (unsigned char)(x >> 16) : 0;
    }
}

int evo_insert_trd(evo *M, const char *path, int drive)
{
    int err = loadTRD(M->comp, path, drive & 3);
    if (err != ERR_OK) return err;
    /* loadTRD only fills the track data; the drive still has to report a
     * disk in it with the door shut, or TR-DOS reads nothing. */
    M->comp->dif->flp[drive & 3]->insert = 1;
    M->comp->dif->flp[drive & 3]->door = 1;
    M->comp->dif->flp[drive & 3]->dwait = 0;
    M->comp->dif->flp[drive & 3]->changed = 0;
    M->comp->dif->flp[drive & 3]->trk80 = 1;
    M->comp->dif->flp[drive & 3]->doubleSide = 1;
    return 0;
}

int evo_insert_sd(evo *M, const char *path)
{
    sdcSetImage(M->comp->sdc, path);
    return M->comp->sdc->file ? 0 : -1;
}


/* --------------------------------------------------------------- SPG files
 *
 * An SPG (v1.0) is a 256-byte header, a 768-byte table of three-byte block
 * descriptors and then the blocks, each loaded straight into a RAM page:
 *
 *   header +$20  "SpectrumProg"    +$2C version ($10)
 *          +$30  PC (LE)           +$32  SP (LE)
 *          +$34  page for window 3 +$35  bits 0-1 clock (0 3.5, 1 7,
 *                                        2 14 MHz), bit 2 interrupts on
 *          +$3A  block count (LE)
 *   block  addr: bits 0-4 offset in the page / 512, bit 7 last block
 *          size: bits 0-4 length / 512 - 1, bits 6-7 packer (0 = stored)
 *          page: the RAM page
 *
 * libxpeccy has a loader of its own, but it is written for TS-Conf and
 * leaves the BaseConf memory manager switched off while mapping the banks
 * behind its back, so the first OUT to a window port would put ROM in all
 * four.  This one leaves the manager on and its eight window registers
 * describing exactly what is mapped: window 0 the BASIC 48 ROM, window 1
 * page 5, window 2 page 2, window 3 the page the header names.
 */

#define EVO_MEMFLAG(c, n) ((c)->reg[0xf0 + (n)])
#define EVO_MEMPAGE(c, n) ((c)->reg[0xf8 + (n)])

int evo_load_spg(evo *M, const char *path)
{
    Computer *c = M->comp;
    FILE *f = fopen(path, "rb");
    unsigned char hd[256], tab[768], blk[0x4000];
    int n, i, clk, pc, sp, page3;
    if (!f) return -1;
    if (fread(hd, 1, 256, f) != 256 || fread(tab, 1, 768, f) != 768
        || memcmp(hd + 0x20, "SpectrumProg", 12)) { fclose(f); return -2; }
    evo_reset(M);
    n = hd[0x3A] | (hd[0x3B] << 8);
    for (i = 0; i < n && i < 256; i++) {
        int addr = (tab[i * 3] & 0x1f) << 9;
        int size = ((tab[i * 3 + 1] & 0x1f) + 1) << 9;
        int page = tab[i * 3 + 2];
        if (tab[i * 3 + 1] & 0xc0) { fclose(f); return -3; }   /* packed */
        if ((int)fread(blk, 1, size, f) != size) { fclose(f); return -4; }
        memcpy(c->mem->ramData + (page << 14) + addr, blk, size);
        if (tab[i * 3] & 0x80) break;
    }
    fclose(f);
    pc = hd[0x30] | (hd[0x31] << 8);
    sp = hd[0x32] | (hd[0x33] << 8);
    page3 = hd[0x34];
    clk = hd[0x35] & 3;

    c->flgDOS = 0;
    c->flgROM = 1;                    /* $7FFD bit 4: window registers 4-7 */
    c->p7FFD = 0x10;
    c->pEFF7 = 0x00;
    c->prt2 = 0x20 | 0x03 | (clk >= 2 ? 0x08 : 0);   /* manager on, ZX screen */
    for (i = 0; i < 8; i++) {
        static const int pages[4] = { 0, 5, 2, 0 };
        int w = i & 3;
        int pg = (w == 3) ? page3 : pages[w];
        if (w == 0) {                 /* ROM: the BASIC 48 page */
            EVO_MEMFLAG(c, i) = 0x00;
            EVO_MEMPAGE(c, i) = 0x03 ^ 0xff;
        } else {
            EVO_MEMFLAG(c, i) = 0x40;
            EVO_MEMPAGE(c, i) = pg ^ 0xff;
        }
    }
    c->hw->mapMem(c);
    compSetTurbo(c, clk == 0 ? 1 : clk == 1 ? 2 : 4);
    c->cpu->regPC = pc;
    c->cpu->regSP = sp;
    c->cpu->regIM = 1;
    c->cpu->regI = 0x3f;
    c->cpu->flgIFF1 = c->cpu->flgIFF2 = (hd[0x35] & 4) ? 1 : 0;
    c->cpu->inten = Z80_NMI | (c->cpu->flgIFF1 ? Z80_INT : 0);
    return 0;
}

/* -------------------------------------------------------------------- run */

static sndVolume vol_full = { 100, 100, 100, 100, 100, 100, 100 };

void evo_frame(evo *M)
{
    Computer *c = M->comp;
    sndPair lev;
    M->audio_n = 0;
    M->frame_ns = 0;
    for (;;) {
        int ns = compExec(c);
        c->flgBRK = 0;
        M->frame_ns += ns;
        M->ns_acc += ns;
        while (M->ns_acc >= M->ns_per_sample) {
            M->ns_acc -= M->ns_per_sample;
            gsFlush(c->gs);
            lev = c->hw->vol(c, &vol_full);
            if (M->audio_n + 2 <= M->audio_cap) {
                M->audio[M->audio_n++] = (int16_t)(lev.left  > 32767 ? 32767 :
                                          lev.left  < -32768 ? -32768 : lev.left);
                M->audio[M->audio_n++] = (int16_t)(lev.right > 32767 ? 32767 :
                                          lev.right < -32768 ? -32768 : lev.right);
            }
        }
        if (c->flgFRM) { c->flgFRM = 0; break; }
    }
}

/* --------------------------------------------------------------- keyboard
 *
 * libxpeccy's ZX keyboard is driven by a string of matrix characters, one
 * per physical key: the digit or letter itself, 'E' for ENTER, 'C' for CAPS
 * SHIFT, 'S' for SYMBOL SHIFT and ' ' for SPACE.  A composite key like the
 * cursor arrows is just two of those at once, exactly as on the rubber
 * keyboard, so the table below is the whole keyboard.
 */
typedef struct { const char *name; const char *seq; int joy; } evo_keydef;

static const evo_keydef keydefs[] = {
    {"1","1",0},{"2","2",0},{"3","3",0},{"4","4",0},{"5","5",0},
    {"6","6",0},{"7","7",0},{"8","8",0},{"9","9",0},{"0","0",0},
    {"q","q",0},{"w","w",0},{"e","e",0},{"r","r",0},{"t","t",0},
    {"y","y",0},{"u","u",0},{"i","i",0},{"o","o",0},{"p","p",0},
    {"a","a",0},{"s","s",0},{"d","d",0},{"f","f",0},{"g","g",0},
    {"h","h",0},{"j","j",0},{"k","k",0},{"l","l",0},{"enter","E",0},
    {"caps","C",0},{"z","z",0},{"x","x",0},{"c","c",0},{"v","v",0},
    {"b","b",0},{"n","n",0},{"m","m",0},{"sym","S",0},{"space"," ",0},
    /* the shifted keys the ROM presents as keys of their own */
    {"left","C5",0},{"down","C6",0},{"up","C7",0},{"right","C8",0},
    {"del","C0",0},{"edit","C1",0},{"caplock","C2",0},{"truevid","C3",0},
    {"invvid","C4",0},{"break","C ",0},{"extend","CS",0},
    /* Kempston joystick */
    {"kjright",NULL,XJ_RIGHT},{"kjleft",NULL,XJ_LEFT},{"kjdown",NULL,XJ_DOWN},
    {"kjup",NULL,XJ_UP},{"kjfire",NULL,XJ_FIRE},
    {NULL,NULL,0}
};

int evo_key_lookup(const char *name)
{
    int i;
    for (i = 0; keydefs[i].name; i++)
        if (!strcmp(keydefs[i].name, name)) return i;
    return -1;
}

/* Which of the keys above is currently held.
 *
 * libxpeccy counts presses and releases per matrix bit, so a second press
 * with no release in between leaves the count at two and the *first*
 * release cannot lift the key: it stays down for ever.  A host that repeats
 * key-down events - which is exactly what SDL does while a key is held -
 * therefore jams every key it touches.  Making press and release idempotent
 * here fixes it for every frontend at once, whatever the host sends.
 */
static unsigned char key_down[sizeof keydefs / sizeof keydefs[0]];

void evo_key(evo *M, int code, int down)
{
    keyEntry ent;
    const evo_keydef *k;
    int i;
    if (code < 0 || code >= (int)(sizeof key_down)) return;
    down = !!down;
    if (key_down[code] == down) return;         /* nothing changed */
    key_down[code] = (unsigned char)down;
    k = &keydefs[code];
    if (k->joy) {
        if (down) M->comp->joy->state |=  k->joy;
        else      M->comp->joy->state &= ~k->joy;
        M->comp->joy->used = 1;
        return;
    }
    memset(&ent, 0, sizeof ent);
    for (i = 0; k->seq[i] && i < KEYSEQ_MAXLEN - 1; i++)
        ent.zxKey[i] = (unsigned char)k->seq[i];
    if (down) kbd_press(M->comp->keyb, &ent);
    else      kbd_release(M->comp->keyb, &ent);
}

void evo_key_release_all(evo *M)
{
    memset(key_down, 0, sizeof key_down);
    comp_kbd_release(M->comp);
    M->comp->joy->state = 0;
}

/* ----------------------------------------------------------------- memory */

int evo_peek(evo *M, int addr)  { return memRd(M->comp->mem, addr & 0xffff); }
void evo_poke(evo *M, int addr, int val) { memWr(M->comp->mem, addr & 0xffff, val & 0xff); }

void evo_poke_ram(evo *M, int page, int off, int val)
{
    int abs = ((page & 0xff) << 14) | (off & 0x3fff);
    M->comp->mem->ramData[abs & M->comp->mem->ramMask] = val & 0xff;
}

int evo_ram(evo *M, int page, int off)
{
    int abs = ((page & 0xff) << 14) | (off & 0x3fff);
    return M->comp->mem->ramData[abs & M->comp->mem->ramMask];
}
