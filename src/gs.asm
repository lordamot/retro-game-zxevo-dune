; gs.asm - the General Sound card: the effects and as many tunes as the
; card holds uploaded at start-up, any other tune streamed to the card from
; the game's loops when it is wanted, and all of it played by the card's
; own ROM (v1.05a).
;
; Needs, before it is included:
;   sound_ids.inc   (tools/dune_sound.py: MUS_*, SFX_*, the counts, pages)
;   map_w1, map_w3  routines: A = RAM page into window 1 ($4000) / window 3
;                   ($C000), clobbering A only, keeping cur_w1 / cur_w3
;                   (src/stub/stub.asm's do)
;   gs_tick         a routine: the start-up's progress, for a loading
;                   screen.  Called every 256 readings while gs_init waits
;                   for the card's memory test (gs_phase 0), and after each
;                   effect and each tune chunk the start-up sends
;                   (gs_phase 1: the bar is gs_up_done of gs_up_total, in
;                   the costs dune_sound.py gives them).  May clobber AF BC
;                   DE HL.
; and includes build/gen/sound.inc (the tables) itself, at its end.  It has
; no ORG and no page of its own: it runs wherever the including bank puts
; it, and never touches the ZX ROM or TR-DOS.
;
; How the ROM is used, and why this way, is in .claude/docs/sound.md ("The
; port's sound").  In short: the ROM keeps one module and parses it in
; place at logical address 0, so a tune is written straight into card
; pages the way its $30 would have left it, and started by pointing logical
; pages 0.. of the ROM's page table at them and writing the sample records
; tools/dune_sound.py computed.  The effects are ROM "FX samples" at the
; logical pages above the largest tune (SND_WINDOW), loaded with $38 at
; start-up, and mixed over the music on channels GS_FX_CHANS.
;
; The tunes live in the SPG packed (dune_sound.py: a byte-delta for the
; samples, then an LZ77 made for gs_unpack).  The effects go to the card at
; start-up, and then the tunes of snd_start, the most wanted first, each
; that still fits the card's pages (gs_boot_set: on 2 MB every tune the
; game plays but the finale and the ending's); any other tune goes when it
; is about to be wanted - the one asked for, then the ones that may come
; next (snd_succ, and gs_want from the game) - a chunk of 512 bytes at a
; time from the game's own loops (gs_bg): unpacked into SND_BUF_PAGE, then
; written into the tune's card page with $14.  The ROM mixes the music in
; its main loop from code in its page 0 at $8000 ($0273: call $CDED), and
; $12 puts another page there, so every chunk goes like this:
;
;   $14: $FF into $4086   the ROM's own "do not mix" flag ($0279; $31 and
;                         $39 set it the same way while they work)
;   $12 page, $14 bytes   into the tune's card page
;   $12 0                 the ROM's page 0 back at $8000
;   $14: 0 into $4086     mixing again
;
; A chunk holds the mixing up for about 5 ms of the 55 the card buffers.
; On a 12 MHz card a playing tune keeps the mixer busy nearly all the time,
; and time taken from it comes back as stutters, so while a tune plays a
; chunk goes only when the mixer is idle and no effect is being mixed
; (gs_chunk) - a trickle, next to nothing for the busiest tunes.  With no
; tune playing - a tune asked for and not there yet, or none - chunks go as
; fast as the caller allows.  A tune asked for before it is there starts,
; after that silence, the moment its last chunk is in; the card keeps the
; tunes it has for as long as it has room, so this happens the first time
; a tune is wanted and hardly ever again.
;
; The card's rules (sound.md): a command's first argument goes to the data
; port *before* the command; a block's length goes across as it is; and
; $30/$38 answer by putting the handle in the latch and then reading the
; data port, which clears the flag - so an answer is read as soon as the
; command has been taken, never waited for.
;
; API (all preserve IX and IY unless said; "no card" = gs_init failed, and
; then every other entry point does nothing and returns at once):
;
;   gs_probe         is there a card?  About 0.1 ms.  Out: carry set =
;                    none.  Clobbers AF B.
;   gs_init          wait for the card to finish its power-on memory test,
;                    then warm-reset it (gs_tick all the while).  Out:
;                    carry set = no card (or it never settled).  Clobbers
;                    AF BC DE HL.
;   gs_pages         after gs_init: the card's memory.  Out: A = its 32 KB
;                    pages as the ROM counts them; carry set = no card, or
;                    fewer than SND_CARD_PAGES (then nothing is played).
;                    Clobbers AF B.
;   gs_setup         after gs_pages: the page table, the ROM's module
;                    channels (a silent $30), the effects' logical pages,
;                    and the start-up tunes of snd_start that fit
;                    (gs_boot_set).  Out: carry set = no card.  Calls
;                    map_w1/map_w3 and leaves them changed.  Clobbers AF
;                    BC DE HL.
;   gs_load_fx       put the effects on the card through $38, gs_tick after
;                    each (about 2.4 s).  Clobbers AF BC DE HL, leaves
;                    windows 1 and 3 changed.
;   gs_boot_next     -> A = the next start-up tune to put on (the intro's,
;                    MUS_INTRO, first); carry: none left.  gs_load_now A
;                    puts it on, whole, nothing playing, gs_tick after each
;                    chunk.  All of them, 2 MB: about 15 s.
;   gs_intro_done    after the intro's screen: the intro's tune fades
;                    and stops, and its pages take the start-up tunes it
;                    kept off the card.
;   gs_music_play    A = MUS id: start that tune, unless it is the one
;                    asked for last.  SND_NONE (or any id >= MUS_COUNT)
;                    stops.  If the tune is not on the card yet the music
;                    stops, the loader fetches it first, and it starts the
;                    moment it is there (gs_step).
;   gs_music_start   the same, but restarts a tune that is already playing
;                    (for a tune that plays once and has ended).
;   gs_music_stop    stop the tune.
;   gs_want          A = MUS id: fetch it before anything but the tune
;                    asked for (the mentat after a battle, the finale in
;                    the last mission).  gs_want_track: the same for a Mega
;                    Drive music track.
;   gs_bg            A = chunks: move up to that many.  Out: carry set =
;                    nothing to move, or the card has no time now.  About
;                    60000 T-states a chunk (0.2 frame), 1500 a "not now".
;                    Keeps windows 1 and 3.  gs_wait says whether a tune is
;                    waited for (the caller may give more then).
;   gs_step          one chunk (gs_bg's step); carry set = nothing to do.
;                    Leaves windows 1 and 3 changed.
;   gs_fx_play       A = SFX id: play it on a channel of GS_FX_CHANS, over
;                    the music.  SND_NONE / out of range: nothing.
;   gs_fx_stop       stop every effect.
;   gs_set_volumes   A = music volume, C = effects volume, 0..64 each (the
;                    ROM's master volumes; 64 at start).
;   gs_effect        A = Mega Drive effect id 0-$40 ($06A876): its effect.
;   gs_voice         A = Mega Drive feedback id 0-$5D ($06A954): its words.
;                    Out of range (the cartridge's -2 "stop") does nothing.
;   gs_track         A = Mega Drive music track 1-$26 ($06A8B8): start its
;                    tune (stop the music if the port has none for it).
;                    Out: HL = what musicFramesLeft becomes ($06A8BA): the
;                    frames a battle tune runs before the shuffle moves on,
;                    $FFFF for any other track; HL = 0 and nothing changed
;                    if the track has no song at all.  With no card, the
;                    same answer and nothing played.
;   The play/stop/volume entries clobber AF BC DE HL.  What they cost at
;   14 MHz (bin/evo, a four-channel tune playing): gs_fx_play about 40 us,
;   but a second one straight after waits for the card to take the first,
;   up to about 0.8 ms; gs_music_play for a tune on the card about 15 ms
;   (six commands and some 500 bytes, each command waiting for the card's
;   main loop), for the tune already playing nothing.

GS_DATA         EQU $B3         ; write: a byte to the card; read: its answer
GS_CMD          EQU $BB         ; write: a command; read: the status
                                ;   bit 7: the data latch is full
                                ;   bit 0: a command has not been taken

; Which of the card's four DACs the effects may take from the music.  DACs
; 0 and 1 are the left speaker, 2 and 3 the right; the tune's four tracker
; channels sit on DACs 0, 2, 3, 1 (Amiga LRRL, set by the ROM's warm
; reset), and while an effect plays on a DAC the tracker channel there is
; not mixed.  DACs 1 and 2 give an effect either side, at most two at once,
; and the tune always keeps its channels 0 and 2.  An effect takes one of
; these where the tune is silent, else one with no effect on it, else one
; playing an effect of lower priority, else it is not played ($CA2A).
GS_FX_CHANS     EQU %0110

GS_TIMEOUT      EQU 120         ; x ~1/3 s: how long gs_init waits (the
                                ; memory test takes 10.5 s with 2 MB in
                                ; bin/evo; a real card may take longer)
GS_WANTS        EQU 4           ; tunes the loader is told to fetch next
GS_PROBE        EQU 40          ; x 35 T (100 us): a command not taken in
                                ; that time means the card is mixing
GS_AHEAD        EQU 4           ; buffers of 7 mixed ahead for a chunk to go
GS_AHEAD_FX     EQU 1           ; ... when only effects are playing
GS_BACKOFF      EQU 4           ; calls the loader waits after "not now"
GS_FX_QUIET     EQU 25          ; gs_bg calls with no chunk after an effect
                                ; starts (while a tune plays)
GS_OWN_FX       EQU $FE         ; gs_own: a page of the effects, or none
DBGF_NOLOAD     EQU 32          ; dbg_flags (src/world.asm) bit 5: only the
                                ; intro's tune goes to the card, and nothing
                                ; is loaded from the game's loops - a test
                                ; build for a card that stops answering
                                ; (`make build DBGFLAGS=32`)

; the ROM's variables this file writes (gs105a.rom, card addresses)
GSV_PTAB        EQU $4000       ; logical page -> card page
GSV_NPAGES      EQU $4080       ; logical pages
GSV_ACTIVE      EQU $4084       ; non-zero: there is something to mix
GSV_OUTRUN      EQU $4085       ; zero: the output has stopped (nothing
                                ; mixed in time, or nothing to mix)
GSV_NOMIX       EQU $4086       ; non-zero: the main loop does not mix
GSV_MIXIDX      EQU $408C       ; the buffer the mixer fills next (x4)
GSV_OUTIDX      EQU $408E       ; the buffer playing (x4, $4100 + it)
GSV_FXMIX       EQU $40A0       ; the effect channels being mixed ($CE33)
GSV_SONGLEN     EQU $415C       ; song length - 1, restart
GSV_NPAT        EQU $419E       ; patterns, format ($FF: 31 samples)
GSV_LOADPTR     EQU $4198       ; where the next load goes, 3 bytes linear
GSV_SAMPLES     EQU $5400       ; the module's sample records, 16 bytes each
GSV_CHANNELS    EQU $4600       ; the module's four channels, 64 bytes each

        ASSERT SND_CHUNK == 512 ; 64 chunks a card page, 32 a ZX page
        ASSERT SND_SUCC == 3    ; gs_music_start multiplies by it

; ============================================================ start-up

; Is there a card?  Only two bits of the status port mean anything, and
; only the data flag (bit 7) is the card's hardware rather than its ROM: a
; byte written to $B3 sets it, the host reading $B3 clears it, whatever the
; card's Z80 is doing - its power-on memory test included.  Bits 1-6 are not
; part of the port: an original GS leaves them to the bus's pull-ups (1s),
; a NeoGS drives them with whatever its FPGA's synthesis made of "don't
; care" (zxbus.v: { data_bit, 6'bXXXXXX, command_bit }) - a probe that
; wanted them set found no NeoGS.  With no card the port is not decoded:
; it reads $FF (bit 7 never clear), or on a machine that returns the
; floating bus for it - bin/evo does, as the Evo's port $FF - the byte the
; video is fetching, 0 on the black screen of start-up (never set).  So:
; GS_PROBES rounds of "read $B3: the flag clear; write $B3: the flag set",
; each after a pause for the card's synchroniser (a NeoGS takes a write or
; a read 2-3 of its clocks after the host's strobe ends), every one right.
; The rounds end with $B3 read, so the latch is left empty - which also
; drops a byte an earlier program left there: a NeoGS is not reset with
; the machine.  The card's input latch keeps the probe's 0 until the next
; command's first argument replaces it.
GS_PROBES       EQU 8
gs_probe:
        ld  b, GS_PROBES
.lp:    in  a, (GS_DATA)        ; the flag cleared ...
        call .pause
        in  a, (GS_CMD)
        rlca
        ret c                   ; ... and it is not: no card
        xor a
        out (GS_DATA), a        ; the flag set ...
        call .pause
        in  a, (GS_CMD)
        rlca
        ccf
        ret c                   ; ... and it is not: no card
        djnz .lp
        in  a, (GS_DATA)        ; the latch left empty
        or  a
        ret
.pause: ex  (sp), hl            ; about 65 T-states with the call: 4.6 us
        ex  (sp), hl
        ret

gs_init:
        xor a
        ld  (gs_ok), a
        ld  (gs_dead), a        ; the waits below are real (they give up
        ld  (gs_pend), a        ; on gs_dead, which gs_abort sets)
        ld  (gs_wait), a
        ld  (gs_phase), a
        dec a
        ld  (gs_cur), a
        ld  (gs_ld), a
        ; the card tests its memory after power-on and its status flickers
        ; while it does: wait for 65536 readings in a row of "idle".  A
        ; byte in the latch is read away: nothing else will read it, and a
        ; card that was not reset with the machine (a NeoGS) may still hold
        ; an earlier program's answer there
        ld  c, GS_TIMEOUT
        ld  de, 0
        ld  hl, 0
.poll:  in  a, (GS_CMD)
        and $81
        jr  z, .idle
        ld  hl, 0
        jp  p, .tick            ; only a command pending
        in  a, (GS_DATA)
        jr  .tick
.idle:  dec hl
        ld  a, h
        or  l
        jr  z, .ready
.tick:  dec de
        ld  a, e
        or  a
        call z, .prog           ; every 256 readings: the progress
        ld  a, d
        or  e
        jr  nz, .poll
        dec c
        jr  nz, .poll
        scf                     ; no card, or it never settled
        ret
.prog:  push bc
        push de
        push hl
        call gs_tick
        pop hl
        pop de
        pop bc
        ret
.ready: in  a, (GS_DATA)        ; drop anything left in the latch
        xor a                   ; the ROM at $8000 (it may be a RAM page)
        call gs_arg1
        ld  a, $12
        call gs_cmd
        ld  a, $F3              ; warm reset: channels, modules and effects
        call gs_cmd             ; forgotten, the page table kept
        call gs_wcmd
        ld  bc, 0               ; it clears 16 KB before it listens again
.wait:  dec bc
        ld  a, b
        or  c
        jr  nz, .wait
        in  a, (GS_DATA)
        ld  a, 1
        ld  (gs_ok), a
        or  a
        ret

gs_pages:
        ld  a, (gs_ok)
        or  a
        scf
        ret z
        ld  a, $23              ; the 32 KB pages the card found
        call gs_cmd
        call gs_ans
        cp  65
        jr  c, .n
        ld  a, 64
.n:     ld  (gs_npages), a
        call gs_pages_check     ; ... and the pages that are really there
        ld  a, (dbg_flags2)     ; the 1 MB test: 30 pages at most
        and DBGF2_TEST1MB
        jr  z, .cap
        ld  a, (gs_npages)
        cp  31
        jr  c, .cap
        ld  a, 30
        ld  (gs_npages), a
.cap:   ld  a, (gs_npages)
        cp  SND_CARD_PAGES
        jr  nc, .enough
        xor a                   ; too small: play nothing
        ld  (gs_ok), a
        ld  a, (gs_npages)
        scf
        ret
.enough:
        or  a
        ret

; The ROM's count is not taken on trust.  Its power-on test marks each
; page's last byte with the page's number and lists the pages that keep
; their own, which catches a card whose upper half is its lower half
; again - but not one where the upper pages land on the lower ones some
; other way: the ZX-MultiSound rev.A1 has 1 MB in two 512 KB chips and
; its ROM reports 62 pages, and thirteen tunes loaded into 62 pages
; landed on each other.  So every page the ROM lists ($22: the card page
; of logical page k) is marked here at eight places 4 KB apart ($x010,
; both halves), and read back once all are marked: the count is cut at
; the first page that does not hold every one of its own marks.  Eight
; places rather than two because a page bit wired to a line below A15
; sends the upper pages onto the lower ones at another offset - a mark
; at one place in each half would miss it, and did.  Nothing is on the
; card yet.  Clobbers AF BC DE HL.
GS_MARK_LO      EQU $8010       ; the first mark; then + $1000 each
GS_MARKS        EQU 8
gs_pages_check:
        ; the ROM's page table first (gs_setup reads it again for its
        ; own): a page whose marks change it has landed in the ROM's RAM
        ld  c, 0
        ld  hl, gs_ptab
.tab:   ld  a, c
        call gs_peek
        ld  (hl), a
        inc hl
        inc c
        ld  a, (gs_npages)
        cp  c
        jr  nz, .tab
        ld  c, 0
.mark:  call .page              ; card page of logical C at $8000
        jp  c, .cut             ; (a page the ROM keeps: not touched)
        ld  de, GS_MARK_LO
        ld  b, GS_MARKS
.mk1:   push bc
        push de
        ld  a, c
        xor d                   ; the mark: page and place, never the same
        add a, $11              ; in two places or two pages
        call gs_poke
        pop de
        pop bc
        ld  a, d
        add a, $10
        ld  d, a                ; + $1000
        djnz .mk1
        ; the table as it was?  else this page is the ROM's own RAM
        ; under another number: put the table back and stop here
        push bc
        ld  c, 0
        ld  hl, gs_ptab
.tab2:  ld  a, c
        call gs_peek
        cp  (hl)
        jr  nz, .hit
        inc hl
        inc c
        ld  a, (gs_npages)
        cp  c
        jr  nz, .tab2
        pop bc
        inc c
        ld  a, (gs_npages)
        cp  c
        jr  nz, .mark
        jr  .verify
.hit:   ld  c, 0
        ld  hl, gs_ptab
.put:   ld  a, (hl)
        push hl
        push bc
        ld  d, GSV_PTAB >> 8
        ld  e, c
        call gs_poke
        pop bc
        pop hl
        inc hl
        inc c
        ld  a, (gs_npages)
        cp  c
        jr  nz, .put
        pop bc
        jr  .cut
.verify:
        ld  c, 0
.check: call .page
        jr  c, .cut
        ld  de, GS_MARK_LO
        ld  b, GS_MARKS
.ck1:   push bc
        push de
        ld  hl, gs_buf + 63
        ld  bc, 1
        call gs_fetch
        pop de
        pop bc
        ld  a, c
        xor d
        add a, $11
        ld  hl, gs_buf + 63
        cp  (hl)
        jr  nz, .cut
        ld  a, d
        add a, $10
        ld  d, a                ; + $1000
        djnz .ck1
        inc c
        ld  a, (gs_npages)
        cp  c
        jr  nz, .check
.done:  xor a                   ; the ROM's page 0 back at $8000
        call gs_arg1
        ld  a, $12
        jp  gs_cmd
.cut:   ld  a, c                ; pages 0..C-1 are real
        ld  (gs_npages), a
        jr  .done
; C = a logical page -> its card page at $8000.  Carry: the ROM lists no
; RAM page there (0 and 1 are its own).  Clobbers A.
.page:  ld  a, c
        call gs_peek
        cp  2
        ret c
        call gs_arg1
        ld  a, $12
        call gs_cmd
        or  a
        ret

gs_setup:
        ld  a, (gs_ok)
        or  a
        scf
        ret z
        push ix
        call .go
        pop ix
        ret
.go:
        ; which pages they are
        ld  a, (gs_npages)
        ld  b, a
        ld  c, 0
        ld  hl, gs_ptab
.pt:    ld  a, c
        call gs_arg1
        ld  a, $22
        call gs_cmd
        call gs_ans
        ld  (hl), a
        inc hl
        inc c
        djnz .pt

        ; one module through the ROM's own $30, so that it sets up its
        ; module channels - with the page count cut to one, or it would
        ; spend six seconds making all 2 MB unsigned
        ld  a, 1
        ld  de, GSV_NPAGES
        call gs_poke
        ld  a, $30
        call gs_cmd
        call gs_ans             ; the handle: always 1
        ld  ix, snd_init
        ld  e, (ix+3)
        ld  d, (ix+4)
        ld  (gs_cnt), de
        xor a
        ld  (gs_cnt+2), a
        ld  l, (ix+1)
        ld  h, (ix+2)
        ld  a, (ix+0)
        call gs_stream
        call gs_end
        ; what $30 left in the four module channels ($4600, 64 bytes each)
        ; is what every tune must start from: read it back with $15
        ld  hl, gs_chan
        ld  de, GSV_CHANNELS
        ld  bc, 256
        call gs_fetch

        ; who owns which card page: the effects the first SND_FX_PAGES,
        ; the tunes the rest, and no one the pages the card does not have
        ld  hl, gs_own
        ld  b, 64
        ld  a, (gs_npages)
        ld  c, a
        ld  e, 0
.own:   ld  a, e
        cp  SND_FX_PAGES
        ld  a, GS_OWN_FX
        jr  c, .own1
        ld  a, e
        cp  c
        ld  a, GS_OWN_FX
        jr  nc, .own1
        ld  a, SND_NONE
.own1:  ld  (hl), a
        inc hl
        inc e
        djnz .own
        ld  hl, gs_tst
        ld  b, MUS_COUNT
.tst:   ld  (hl), 0
        inc hl
        djnz .tst
        call gs_want_clear

        ; the effects' logical pages: SND_WINDOW upwards, above the largest
        ; tune, so that pointing logical pages 0.. at a tune never moves an
        ; effect
        ld  b, SND_FX_PAGES
        ld  c, 0
        ld  hl, gs_buf
.fm:    ld  a, c
        call gs_page_of
        ld  (hl), a
        inc hl
        inc c
        djnz .fm
        ld  bc, SND_FX_PAGES
        ld  hl, gs_buf
        ld  de, GSV_PTAB + SND_WINDOW
        call gs_block
        ld  a, SND_WINDOW + SND_FX_PAGES
        ld  de, GSV_NPAGES
        call gs_poke

        ; which tunes go now, and what the start-up costs from here
        call gs_boot_set
        ld  a, 1
        ld  (gs_phase), a
        or  a
        ret

gs_load_fx:
        ld  a, (gs_ok)
        or  a
        ret z
        push ix
    IF SFX_COUNT
        ld  ix, snd_fx
        ld  hl, gs_fxh
        ld  b, SFX_COUNT
.fx:    push bc
        push hl
        ; where it goes: the ROM's load pointer
        push ix
        pop hl
        ld  de, 6
        add hl, de
        ld  de, GSV_LOADPTR
        ld  bc, 3
        call gs_block
        ; $38: load an FX sample - the handle, the bytes, $D2
        ld  a, $38
        call gs_cmd
        call gs_ans
        pop hl
        ld  (hl), a
        push hl
        ld  a, (ix+3)
        ld  (gs_cnt), a
        ld  a, (ix+4)
        ld  (gs_cnt+1), a
        ld  a, (ix+5)
        ld  (gs_cnt+2), a
        ld  l, (ix+1)
        ld  h, (ix+2)
        ld  a, (ix+0)
        call gs_stream
        call gs_end
        ; its note, volume, priority and channels ($3F $41 $45 $46 $47,
        ; all about the sample just loaded)
        ld  a, (ix+9)
        call gs_arg1
        ld  a, $3F
        call gs_cmd
        ld  a, (ix+10)
        call gs_arg1
        ld  a, $41
        call gs_cmd
        ld  a, (ix+11)
        call gs_arg1
        ld  a, $45
        call gs_cmd
        ld  a, GS_FX_CHANS
        call gs_arg1
        ld  a, $46
        call gs_cmd
        ld  a, GS_FX_CHANS
        call gs_arg1
        ld  a, $47
        call gs_cmd
        ld  l, (ix+SND_FX_COSTOF)
        ld  h, (ix+SND_FX_COSTOF+1)
        call gs_done
        ld  de, SND_FX_SIZE
        add ix, de
        pop hl
        inc hl
        pop bc
        dec b
        jp  nz, .fx
    ENDIF
        call gs_wcmd
        pop ix
        ret

; The start-up tunes in the order they go (gs_boot_next): the intro's
; first, whatever gs_boot_set chose (the page count leaves room for it:
; snd_start leads with it), then gs_boot's the least wanted first, so
; that the most wanted is the newest in the cache (gs_alloc gives up the
; oldest first).  -> A = the next one's MUS id; carry: none left.  Keeps
; IX, IY.
gs_boot_next:
        ld  a, (gs_bintro)
        or  a
        jr  z, .rest
        xor a
        ld  (gs_bintro), a
        ld  a, MUS_INTRO
        ret                     ; carry clear (or a)
.rest:  ld  a, (gs_bnext)
        or  a
        scf
        ret z
        dec a
        ld  (gs_bnext), a
        ld  de, gs_boot
        add a, e
        ld  e, a
        adc a, d
        sub e
        ld  d, a
        ld  a, (de)
        cp  MUS_INTRO
        jr  z, .rest
        or  a
        ret

; The tunes that go to the card at start-up (gs_boot, gs_nboot): those of
; snd_start, the most wanted first, each that still fits the pages the
; card has left for tunes (dune_sound.py's boot_set); what the effects
; and those tunes cost (gs_up_total, gs_up_done 0); and gs_boot_next at
; the first.  Clobbers AF BC DE HL.
gs_boot_set:
        push ix
        ld  hl, SND_FX_COST
        ld  (gs_up_total), hl
        ld  hl, 0
        ld  (gs_up_done), hl
        xor a
        ld  (gs_nboot), a
        ld  a, (dbg_flags)      ; the test switch: only the intro's tune
        and DBGF_NOLOAD         ; ever goes to the card, nothing is
        jr  z, .all             ; loaded from the game's loops
        xor a
        ld  (gs_bnext), a       ; none but the intro's
        ld  a, 1
        ld  (gs_bintro), a
        pop ix
        ret
.all:
        ld  a, (gs_npages)
        sub SND_FX_PAGES
        ld  c, a                ; C = the pages left
        ld  hl, snd_start
        ld  a, (dbg_flags2)     ; the 1 MB test: the intro and the lego
        and DBGF2_TEST1MB       ; tune, nothing else
        jr  z, .order
        ld  hl, gs_start_test
.order: ld  b, (hl)
.lp:    inc hl
        push bc
        push hl
        ld  a, (hl)
        call gs_mod             ; IX = its record
        pop hl
        pop bc
        ld  a, c
        sub (ix+SM_PAGES)
        jr  c, .nx              ; it does not fit
        ld  c, a
        push bc
        push hl
        ld  a, (hl)             ; into gs_boot
        ld  hl, gs_nboot
        ld  e, (hl)
        inc (hl)
        ld  d, 0
        ld  hl, gs_boot
        add hl, de
        ld  (hl), a
        ld  e, (ix+SM_CHUNKS)   ; its cost: chunks x SND_COST_CHUNK
        ld  d, (ix+SM_CHUNKS+1)
        ld  hl, (gs_up_total)
        ld  b, SND_COST_CHUNK
.cost:  add hl, de
        djnz .cost
        ld  (gs_up_total), hl
        pop hl
        pop bc
.nx:    djnz .lp
        ld  a, (gs_nboot)
        ld  (gs_bnext), a
        ld  a, 1
        ld  (gs_bintro), a
        pop ix
        ret

gs_start_test:  DB 2, MUS_INTRO, MUS_THE_LEGO_TUNE

; HL = a cost: done; the progress (gs_tick).  Keeps IX, IY.
gs_done:
        ld  de, (gs_up_done)
        add hl, de
        ld  (gs_up_done), hl
        push ix
        call gs_tick
        pop ix
        ret

; A = MUS id: fetch it whole now, the loader going as fast as it can
; (start-up), with gs_tick after each chunk.  Clobbers everything but IY.
gs_load_now:
        ld  (gs_now), a
        call gs_want
.lp:    call gs_step
        jr  c, .test
        ld  hl, SND_COST_CHUNK
        call gs_done
.test:  ld  a, (gs_now)
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  nz, .lp
        ret

; The intro's tune (MUS_INTRO, the port's own: dune_sound.py PORT_MUSIC)
; has had its time on the intro's screen: it fades out over some frames
; and stops, and the card is made to hold what it would have held with no
; intro - the tunes of snd_start but the intro, each that fits the pages
; for tunes, in turn (gs_boot_set's rule): a tune on the card outside
; that set gives its pages up (the one the intro let in: on 2 MB the
; smallest dirge), and one inside it that is not there goes on now, whole
; (on 2 MB the Tutorial's, about 1 s).  Clobbers everything but IY; leaves
; windows 1 and 3 changed.
; gs_music_fade: the tune playing fades out over sixteen frames and
; stops, the volume back up after (the card's $32 alone leaves a note
; sounding on a channel the next tune does not take, the options screen's
; switch and its music test heard it).  Nothing plays: nothing.  Waits
; the frames.  Clobbers AF, BC, HL.
gs_music_fade:
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, (gs_cur)
        cp  $FF
        ret z
        ld  a, (gs_wait)
        or  a
        jp  nz, gs_music_stop   ; not playing yet: just forgotten
        ld  b, 16
.fade:  push bc
        dec b
        ld  a, b
        add a, a
        add a, a                ; 60, 56 .. 0
        ld  c, 64
        call gs_set_volumes
        call vid_wait_frame
        pop bc
        djnz .fade
        call gs_music_stop
        ld  a, 64
        ld  c, a
        jp  gs_set_volumes

gs_intro_done:
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, (dbg_flags)
        and DBGF_NOLOAD
        ld  b, a
        ld  a, (dbg_flags2)
        and DBGF2_TEST1MB
        or  b
        ld  (gs_noload), a      ; from here on the loader does nothing
        ld  b, 16
.fade:  push bc
        dec b
        ld  a, b
        add a, a
        add a, a                ; the music's volume 60, 56 .. 0
        ld  c, 64
        call gs_set_volumes
        call vid_wait_frame
        pop bc
        djnz .fade
        call gs_music_stop
        ld  a, 64
        ld  c, a
        call gs_set_volumes
        ld  a, MUS_INTRO
        call gs_free
        ld  a, (gs_noload)
        or  a
        ret nz
        ; gs_buf[id] = 1: the set without the intro
        ld  hl, gs_buf
        ld  b, MUS_COUNT
.clr:   ld  (hl), 0
        inc hl
        djnz .clr
        ld  a, (gs_npages)
        sub SND_FX_PAGES
        ld  c, a                ; C = the pages for tunes
        ld  hl, snd_start
        ld  b, (hl)
.set:   inc hl
        ld  a, (hl)
        cp  MUS_INTRO
        jr  z, .set1
        push bc
        push hl
        call gs_mod             ; IX = its record
        pop hl
        pop bc
        ld  a, c
        sub (ix+SM_PAGES)
        jr  c, .set1            ; it does not fit
        ld  c, a
        push hl
        ld  a, (hl)
        ld  hl, gs_buf
        call gs_at
        ld  (hl), 1
        pop hl
.set1:  djnz .set
        ; out: every tune on the card that is not in it
        ld  c, 0
.out:   ld  a, c
        ld  hl, gs_buf
        call gs_at
        ld  a, (hl)
        or  a
        jr  nz, .out1
        ld  a, c
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  nz, .out1
        push bc
        ld  a, c
        call gs_free
        pop bc
.out1:  inc c
        ld  a, c
        cp  MUS_COUNT
        jr  c, .out
        ; in: every tune of it not on the card, in snd_start's order
        ld  hl, snd_start
        ld  b, (hl)
.in:    inc hl
        push bc
        push hl
        ld  a, (hl)
        ld  hl, gs_buf
        call gs_at
        ld  a, (hl)
        or  a
        jr  z, .in1
        pop hl
        push hl
        ld  a, (hl)
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  z, .in1
        pop hl
        push hl
        ld  a, (hl)
        call gs_load_now
.in1:   pop hl
        pop bc
        djnz .in
        ret

; ============================================================ playing

gs_music_play:
        ld  hl, gs_cur
        cp  (hl)
        ret z
gs_music_start:
        cp  MUS_COUNT
        jp  nc, gs_music_stop
        ld  e, a
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, e
        ld  (gs_cur), a
        push ix
        call gs_age             ; the newest tune now
        ; what may come after it, for the loader
        call gs_want_clear
        ld  a, (gs_cur)
        ld  l, a
        add a, a
        add a, l                ; x SND_SUCC
        ld  hl, snd_succ + SND_SUCC - 1
        call gs_at_a
        ld  b, SND_SUCC
.succ:  ld  a, (hl)
        push hl
        push bc
        call gs_want
        pop bc
        pop hl
        dec hl
        djnz .succ
        ; on the card?
        ld  a, (gs_cur)
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  z, .now
        ld  a, (dbg_flags2)     ; the 1 MB test: the lego tune instead
        and DBGF2_TEST1MB
        jr  z, .wait
        ld  a, MUS_THE_LEGO_TUNE
        ld  (gs_cur), a
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  z, .now
.wait:  ld  a, 1                ; not yet: silence until it is (gs_step)
        ld  (gs_wait), a
        ld  a, $32
        call gs_cmd
        pop ix
        ret
.now:   xor a
        ld  (gs_wait), a
        call gs_switch
        pop ix
        ret

; Start gs_cur, which is on the card: point logical pages 0.. at its card
; pages, write what the ROM's parser would have left, $31.  Clobbers
; everything but IY.
gs_switch:
        ld  a, (gs_cur)
        call gs_mod             ; IX = its snd_mods record
        ld  a, $32              ; stop the tune playing
        call gs_cmd
        ; logical pages 0.. -> its card pages
        ld  a, (gs_cur)
        call gs_tpages          ; HL = its slots
        ld  b, (ix+SM_PAGES)
        ld  de, gs_buf
.win:   ld  a, (hl)
        call gs_page_of
        ld  (de), a
        inc hl
        inc de
        djnz .win
        ld  c, (ix+SM_PAGES)
        ld  b, 0
        ld  hl, gs_buf
        ld  de, GSV_PTAB
        call gs_block
        ; what the ROM's parser would have left: song length and restart,
        ; patterns and format, the sample records
        ld  a, (ix+SM_SONG)
        ld  (gs_buf), a
        ld  a, (ix+SM_SONG+1)
        ld  (gs_buf+1), a
        ld  a, (ix+SM_SONG+2)
        ld  (gs_buf+2), a
        ld  a, (ix+SM_SONG+3)
        ld  (gs_buf+3), a
        ld  hl, gs_buf
        ld  de, GSV_SONGLEN
        ld  bc, 2
        call gs_block
        ld  hl, gs_buf+2
        ld  de, GSV_NPAT
        ld  bc, 2
        call gs_block
        ld  a, (ix+SM_NSAMP)
        or  a
        jr  z, .play
        ld  l, a                ; 16 bytes a sample
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  b, h
        ld  c, l
        ld  l, (ix+SM_RECS)
        ld  h, (ix+SM_RECS+1)
        ld  de, GSV_SAMPLES
        call gs_block
.play:  ld  hl, gs_chan          ; the channels as a fresh $30 leaves them
        ld  de, GSV_CHANNELS    ; (else a tune inherits the last one's
        ld  bc, 256             ; sample, slide and vibrato memory)
        call gs_block
        ld  a, 1                ; $31: play module 1 - the only one the
        call gs_arg1            ; ROM thinks it has
        ld  a, $31
        call gs_cmd
        jp  gs_ans

gs_music_stop:
        ld  a, $FF
        ld  (gs_cur), a
        xor a
        ld  (gs_wait), a
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, $32
        jp  gs_cmd

gs_fx_play:
        cp  SFX_COUNT
        ret nc
        ld  e, a
        ld  a, (gs_ok)
        or  a
        ret z
        ld  d, 0
        ld  hl, gs_fxh
        add hl, de
        ld  a, (hl)
        call gs_arg1
        ld  a, $39              ; play FX: the ROM picks the channel
        call gs_cmd
        ld  a, GS_FX_QUIET      ; no chunk goes for a while (gs_chunk)
        ld  (gs_fxq), a
        ld  a, 1                ; it always answers (0, or $FF: no such
        ld  (gs_pend), a        ; handle), but only once its main loop gets
        ret                     ; to it: gs_sync reads that later

gs_fx_stop:
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, %1111            ; every channel
        call gs_arg1
        ld  a, $3A
        jp  gs_cmd

gs_set_volumes:
        ld  e, a
        ld  a, (gs_ok)
        or  a
        ret z
        ld  a, e
        call gs_arg1
        ld  a, $2A              ; the modules' master volume
        call gs_cmd
        ld  a, c
        call gs_arg1
        ld  a, $2B              ; the effects'
        jp  gs_cmd

gs_effect:
        cp  $41
        ret nc
        ld  hl, snd_effect_map
        jr  gs_mapped

gs_voice:
        cp  $5E
        ret nc
        ld  hl, snd_voice_map
gs_mapped:
        add a, l
        ld  l, a
        adc a, h
        sub l
        ld  h, a
        ld  a, (hl)
        jr  gs_fx_play

gs_track:
        cp  $27
        jr  nc, .none
        ld  e, a
        ld  d, 0
        ld  hl, snd_track_frames
        add hl, de
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        or  h
        ret z                   ; no song: nothing changes ($00A874)
        push hl
        ld  hl, snd_track_map
        add hl, de
        ld  a, (hl)             ; its tune, or SND_NONE: the music stops
        call gs_music_play
        pop hl
        ret
.none:  ld  hl, 0
        ret

; ============================================================ the loader
;
; Per tune: gs_tst (0 not on the card, 1 being loaded, 2 on the card),
; gs_tage (gs_clock when it last started: the oldest goes first when pages
; are short) and gs_tpg (the card slots it has, SND_WINDOW of them).  Per
; card slot: gs_own (the tune in it, SND_NONE free, GS_OWN_FX not a
; tune's).  A tune no one wants any more keeps its pages - and can be
; played again without a load - until the loader needs them.

; A = MUS id: fetch it next, before the tunes already asked for.
; Clobbers AF BC DE HL.
gs_want:
        cp  MUS_COUNT
        ret nc
        ld  e, a
        ; drop it from further down, then shift the list down one
        ld  hl, gs_wants
        ld  b, GS_WANTS
.find:  ld  a, (hl)
        cp  e
        jr  nz, .nx
        ld  (hl), SND_NONE
.nx:    inc hl
        djnz .find
        push de
        ld  hl, gs_wants + GS_WANTS - 2
        ld  de, gs_wants + GS_WANTS - 1
        ld  bc, GS_WANTS - 1
        lddr
        pop de
        ld  a, e
        ld  (gs_wants), a
        ret

; A = a Mega Drive music track ($06A8B8): fetch its tune next.
gs_want_track:
        cp  $27
        ret nc
        ld  hl, snd_track_map
        call gs_at_a
        ld  a, (hl)
        jr  gs_want

gs_want_clear:
        ld  hl, gs_wants
        ld  b, GS_WANTS
.lp:    ld  (hl), SND_NONE
        inc hl
        djnz .lp
        ret

; A = MUS id -> Z if it is in gs_wants.  Clobbers BC HL.
gs_wanted:
        ld  hl, gs_wants
        ld  b, GS_WANTS
.lp:    cp  (hl)
        ret z
        inc hl
        djnz .lp
        or  a                   ; (A is never SND_NONE here): NZ
        ret

; A = chunks to move, at most (1-255).  Keeps windows 1 and 3, IX and IY.
; Out: carry set = nothing to move, or not now (the card is busy).
gs_bg:
        ld  b, a
        ld  a, (gs_ok)
        or  a
        scf
        ret z
        ld  a, (gs_fxq)         ; an effect's quiet time runs out
        or  a
        jr  z, .q
        dec a
        ld  (gs_fxq), a
.q:
        ld  a, (cur_w1)
        ld  c, a
        ld  a, (cur_w3)
        push af
        push bc
        push ix
.lp:    push bc
        call gs_step
        pop bc
        jr  c, .out
        djnz .lp
        or  a
.out:   pop ix
        pop bc
        pop de                  ; D = window 3's page
        push af
        ld  a, c
        call map_w1
        ld  a, d
        call map_w3
        pop af
        ret

; One chunk of the tune being loaded, or the start of the next one to
; load.  Out: carry set = nothing to do.  Clobbers everything but IY;
; leaves windows 1 and 3 changed.
gs_step:
        ld  a, (gs_ok)
        or  a
        scf
        ret z
        ld  a, (gs_noload)
        or  a
        scf
        ret nz
        ld  a, (gs_ld)
        cp  SND_NONE
        jr  z, .pick
        ; still wanted?  The tune waited for comes first; the one being
        ; loaded carries on while it is on the list
        ld  e, a
        ld  a, (gs_wait)
        or  a
        jr  z, .list
        ld  a, (gs_cur)
        cp  e
        jr  z, .chunk
        jr  .drop
.list:  ld  a, e
        call gs_wanted
        jr  z, .chunk
.drop:  ld  a, e
        call gs_free
        ld  a, SND_NONE
        ld  (gs_ld), a
.pick:  call gs_pick
        ret c
.chunk: jp  gs_chunk

; Choose the next tune to load and give it card pages.  Out: carry set =
; none (or no room).
gs_pick:
        ld  a, (gs_wait)
        or  a
        jr  z, .list
        ld  a, (gs_cur)
        call .try
        ret nc
.list:  ld  hl, gs_wants
        ld  b, GS_WANTS
.lp:    ld  a, (hl)
        push hl
        push bc
        call .try
        pop bc
        pop hl
        ret nc
        inc hl
        djnz .lp
        scf
        ret
; A = MUS id: start loading it unless it is on the card.  Carry: not.
.try:   cp  MUS_COUNT
        ccf
        ret c
        ld  (gs_ld), a
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  z, .no
        call gs_alloc
        jr  c, .no
        ld  a, (gs_ld)
        ld  hl, gs_tst
        call gs_at
        ld  (hl), 1
        call gs_mod
        ld  (gs_ldix), ix
        ld  a, (ix+SM_PAGE)
        ld  (gs_lspg), a
        ld  l, (ix+SM_ADDR)
        ld  h, (ix+SM_ADDR+1)
        ld  (gs_lsrc), hl
        ld  hl, 0
        ld  (gs_ldc), hl
        xor a
        ld  (gs_lsum), a
        ld  (gs_unp), a
        ret
.no:    ld  a, SND_NONE
        ld  (gs_ld), a
        scf
        ret

; Card pages for gs_ld, the oldest tunes no one wants giving theirs up if
; it must be.  Out: carry set = not enough (nothing changed).
gs_alloc:
        ld  a, (gs_ld)
        call gs_mod
.count: ld  hl, gs_own
        ld  b, 64
        ld  c, 0
.cnt:   ld  a, (hl)
        cp  SND_NONE
        jr  nz, .cn1
        inc c
.cn1:   inc hl
        djnz .cnt
        ld  a, c
        cp  (ix+SM_PAGES)
        jr  nc, .take
        ; not enough: the tune on the card longest unplayed that is not
        ; playing nor wanted gives its pages up
        ld  d, SND_NONE         ; the one found
        ld  e, 0                ; its age
        ld  c, 0
.old:   ld  a, c
        ld  hl, gs_tst
        call gs_at
        ld  a, (hl)
        cp  2
        jr  nz, .on
        ld  a, c
        ld  hl, gs_cur
        cp  (hl)
        jr  z, .on
        push de
        call gs_wanted
        pop de
        jr  z, .on
        ld  a, c
        ld  hl, gs_tage
        call gs_at
        ld  a, (gs_clock)
        sub (hl)                ; how long ago it started
        cp  e
        jr  c, .on
        ld  e, a
        ld  d, c
.on:    inc c
        ld  a, c
        cp  MUS_COUNT
        jr  c, .old
        ld  a, d
        cp  SND_NONE
        scf
        ret z
        call gs_free
        jr  .count
.take:  ; the first free slots, in order
        ld  a, (gs_ld)
        call gs_tpages
        ex  de, hl              ; DE = its slot list
        ld  hl, gs_own
        ld  b, (ix+SM_PAGES)
        ld  c, 0
.tk:    ld  a, (hl)
        cp  SND_NONE
        jr  nz, .tk1
        ld  a, (gs_ld)
        ld  (hl), a
        ld  a, c
        ld  (de), a
        inc de
        dec b
        jr  z, .done
.tk1:   inc hl
        inc c
        jr  .tk
.done:  or  a
        ret

; A = MUS id: it is not on the card any more; its pages are free.
; Clobbers AF BC DE HL.
gs_free:
        ld  e, a
        ld  hl, gs_tst
        call gs_at
        ld  (hl), 0
        ld  hl, gs_own
        ld  b, 64
.lp:    ld  a, (hl)
        cp  e
        jr  nz, .nx
        ld  (hl), SND_NONE
.nx:    inc hl
        djnz .lp
        ret

; Unpack chunk gs_ldc of gs_ld into SND_BUF_PAGE (once) and send it to its
; card page, if the card has time for it now; after the last, the tune is
; on the card (and starts, if it is the one waited for).  Out: carry set =
; not now (the chunk waits, unpacked, for a later call).  Clobbers
; everything but IY.
;
; "Has time".  The ROM mixes 256 samples at a time into eight buffers (some
; 55 ms of sound, $4100) in its main loop, and takes a command only
; between two buffers; a chunk holds that loop up for about 5 ms.  With a
; tune playing the mixer is busy nearly all the time on a 12 MHz card
; (sound.md has the measures), and any time taken from it while it is
; catching up comes back as a stutter later - so while a tune plays, a
; chunk goes only when the mixer is idle, all its buffers full: a $22
; (one byte of $4000-$40FF, needing nothing more from us) is the probe,
; taken at once when the mixer is idle, only after the buffer it is mixing
; when it is not; if not taken within GS_PROBE polls its answer is left
; for gs_sync and the loader backs off.  With no tune playing (a tune
; waited for, or none) only the effects are mixed and the chunks go as
; fast as they come.  Either way the chunk goes under the ROM's "do not
; mix" flag, and only if the mixer's lead, read under it from its own
; indices ($408C the buffer it fills next, $408E the one playing), is
; GS_AHEAD buffers or more - unless it has nothing to mix at all ($4084)
; or its output stands still ($4085; what $32 leaves).
gs_chunk:
        ld  a, (gs_skip)        ; backing off?
        or  a
        jr  z, .try
        dec a
        ld  (gs_skip), a
        scf
        ret
.try:   ld  ix, (gs_ldix)
        ld  a, (gs_unp)
        or  a
        jr  nz, .have
        ; unpack: the chunk's place in the buffer is its place in its 16 KB
        ld  a, SND_BUF_PAGE
        call map_w3
        call gs_bufaddr
        call gs_unpack
        ld  a, 1
        ld  (gs_unp), a
.have:  ; a tune playing?  Then only if the mixer is idle
        call gs_playing
        jr  z, .lock
        ld  a, low GSV_MIXIDX
        call gs_arg1
        ld  a, $22
        call gs_cmd
        ld  b, GS_PROBE
.probe: in  a, (GS_CMD)
        rrca
        jr  nc, .idle
        djnz .probe
        ld  a, 1                ; busy: its answer is collected later
        ld  (gs_pend), a
        ld  a, (gs_backoff)
        ld  (gs_skip), a
        scf
        ret
.idle:  in  a, (GS_DATA)
.lock:  ld  a, $FF              ; hold the mixing
        ld  de, GSV_NOMIX
        call gs_poke
        ld  a, low GSV_ACTIVE   ; anything to mix at all?
        call gs_peek
        or  a
        jr  z, .go
        ld  a, low GSV_OUTRUN   ; any sound going out?  ($32 leaves the
        call gs_peek            ; mixer "active", its output stopped and
        or  a                   ; its indices standing)
        jr  z, .go
        call gs_playing         ; a tune: not while effects are mixed
        jr  z, .lead            ; over it, nor for a while after one
        ld  a, (gs_fxq)         ; started (the mixer needs its lead then)
        or  a
        jr  nz, .no
        ld  a, low GSV_FXMIX
        call gs_peek
        or  a
        jr  nz, .no
.lead:  ld  a, low GSV_MIXIDX   ; how far ahead
        call gs_peek
        ld  c, a
        ld  a, low GSV_OUTIDX
        call gs_peek
        ld  b, a
        ld  a, c
        sub b
        rrca
        rrca
        dec a
        and 7                   ; buffers ready after the one playing
        ld  c, a
        call gs_playing         ; the threshold: a tune's, or the effects'
        ld  hl, gs_ahead
        jr  nz, .thr
        inc hl
.thr:   ld  a, c
        cp  (hl)
        jr  nc, .go
.no:    xor a                   ; not now: mixing again, and wait
        ld  de, GSV_NOMIX
        call gs_poke
        ld  a, (gs_backoff)
        ld  (gs_skip), a
        scf
        ret
.go:    ; its card page: the tune's slot (chunk / 64)
        ld  hl, (gs_ldc)
        add hl, hl
        add hl, hl
        ld  a, h
        push af
        ld  a, (gs_ld)
        call gs_tpages
        pop af
        call gs_at_a
        ld  a, (hl)
        call gs_page_of
        call gs_arg1
        ld  a, $12
        call gs_cmd
        ; $14: 512 bytes to $8000 + (chunk & 63) * 512
        xor a
        call gs_arg1
        ld  a, $14
        call gs_cmd
        ld  a, high SND_CHUNK
        call gs_put
        xor a
        call gs_put
        ld  a, (gs_ldc)
        and 63
        add a, a
        add a, $80
        call gs_put
        ld  a, SND_BUF_PAGE
        call map_w3
        call gs_bufaddr
        ex  de, hl              ; HL = the chunk in the buffer
        ld  bc, (gs_ldc)        ; a header chunk goes as it is, a sample
        ld  a, b                ; chunk undoes the delta on the way
        or  a
        jr  nz, .delta
        ld  a, c
        cp  (ix+SM_HEAD)
        jr  nc, .delta
        call gs_send
        jr  .sent
.delta: call gs_send_delta
.sent:  ; the ROM's page 0 back at $8000, then mixing again
        xor a
        call gs_arg1
        ld  a, $12
        call gs_cmd
        xor a
        ld  de, GSV_NOMIX
        call gs_poke
        xor a
        ld  (gs_unp), a
        ; on to the next chunk; after the last the tune is here
        ld  hl, (gs_ldc)
        inc hl
        ld  (gs_ldc), hl
        ld  e, (ix+SM_CHUNKS)
        ld  d, (ix+SM_CHUNKS+1)
        or  a
        sbc hl, de
        jr  z, .last
        or  a                   ; a chunk went: NC
        ret
.last:  ld  a, (gs_ld)
        ld  e, a
        ld  hl, gs_tst
        call gs_at
        ld  (hl), 2
        call gs_age             ; as new as the tune playing
        ld  a, SND_NONE
        ld  (gs_ld), a
        ld  a, (gs_wait)        ; the tune waited for?
        or  a
        ret z
        ld  a, (gs_cur)
        cp  e
        jr  nz, .nc
        xor a
        ld  (gs_wait), a
        call gs_switch
.nc:    or  a
        ret

; NZ if a tune is playing (asked for, on the card, started).  Clobbers A.
gs_playing:
        ld  a, (gs_wait)
        or  a
        jr  nz, .no
        ld  a, (gs_cur)
        inc a                   ; SND_NONE -> 0
        ret
.no:    xor a
        ret

; DE = where chunk gs_ldc goes in the buffer (window 3).  Clobbers A.
gs_bufaddr:
        ld  a, (gs_ldc)
        and 31
        add a, a
        add a, $C0
        ld  d, a
        ld  e, 0
        ret

; A = the low byte of a card address $40xx: the byte there ($22).
; Clobbers A.
gs_peek:
        call gs_arg1
        ld  a, $22
        call gs_cmd
        jp  gs_ans

; Unpack one chunk (512 bytes) of the stream at gs_lspg:gs_lsrc (window 1)
; to DE (window 3, a chunk's start in the buffer); the stream position
; moves on.  The format is dune_sound.py's: $01-$7F that many literal
; bytes; $80-$BF a match of (T & $3F) + 3 bytes, offset - 1 in one byte;
; $C0-$FF the same with the offset in two; $00 on to the next page.  A
; chunk is whole tokens, and a match never reaches out of its 16 KB.
; About 45 T-states a byte on these tunes.  Clobbers AF BC DE HL.
gs_unpack:
        ld  a, d
        add a, 2
        ld  (gs_uend), a
        ld  a, (gs_lspg)
        call map_w1
        ld  hl, (gs_lsrc)
.tok:   ld  a, (hl)
        inc hl
        or  a
        jr  z, .page
        jp  m, .match
        ld  c, a                ; literals
        ld  b, 0
        ldir
.chk:   ld  a, e                ; the chunk's end?
        or  a
        jr  nz, .tok
        ld  a, (gs_uend)
        cp  d
        jr  nz, .tok
        ld  (gs_lsrc), hl
        ret
.page:  ld  a, (gs_lspg)
        inc a
        ld  (gs_lspg), a
        call map_w1
        ld  hl, $4000
        jr  .tok
.match: ld  b, a                ; the token
        ld  a, (hl)             ; offset - 1, low byte
        inc hl
        cpl
        bit 6, b
        jr  nz, .long
        push hl
        ld  l, a                ; HL = -offset
        ld  h, $FF
.copy:  add hl, de              ; HL = DE - offset
        ld  a, b
        and $3F
        add a, 3
        ld  c, a
        ld  b, 0
        ldir
        pop hl
        jr  .chk
.long:  ld  c, a
        ld  a, (hl)             ; offset - 1, high byte
        inc hl
        cpl
        push hl
        ld  h, a
        ld  l, c
        jr  .copy

; ============================================================ the wire

; Every wait on the card is bounded: a card that stops taking commands
; while its mixer plays on would otherwise hang the Z80 for good.  After
; GS_STALL polls (about 12 s at 14 MHz) the card is given up - gs_ok = 0,
; gs_dead = 1, every entry point does nothing from then on - and the
; routine that waited carries on as if it had been answered.  The waits
; test gs_dead, not gs_ok: gs_init clears gs_ok first and still needs
; its own commands waited for.  The game
; goes on in silence.  The longest honest wait is the silent $30 of
; gs_setup: ROM 1.05a makes the pages $4080 counts unsigned, and that is
; cut to one, but 1.05b (the ZX-MultiSound's) counts them from $40DA
; instead and walks the whole card - six seconds on 2 MB.
;
; (The level-start freeze that first made these waits bounded was not the
; card at all: the profiler's marks writing $7FFD - see evo.inc.)

GS_STALL        EQU 64          ; x 65536 polls of about 40 T

; wait until the card has taken the last command.  Clobbers A.
gs_wcmd:
        in  a, (GS_CMD)
        rrca
        ret nc
        push bc
        push de
        ld  b, GS_STALL
        ld  de, 0
.lp:    ld  a, (gs_dead)
        or  a
        jr  nz, .out
        in  a, (GS_CMD)
        rrca
        jr  nc, .out
        dec de
        ld  a, d
        or  e
        jr  nz, .lp
        djnz .lp
        call gs_abort
.out:   pop de
        pop bc
        ret

; wait until the card has taken the last data byte.  Clobbers A.
gs_wdat:
        in  a, (GS_CMD)
        rlca
        ret nc
        push bc
        push de
        ld  b, GS_STALL
        ld  de, 0
.lp:    ld  a, (gs_dead)
        or  a
        jr  nz, .out
        in  a, (GS_CMD)
        rlca
        jr  nc, .out
        dec de
        ld  a, d
        or  e
        jr  nz, .lp
        djnz .lp
        call gs_abort
.out:   pop de
        pop bc
        ret

; wait until the card has put a byte in the latch ($15).  Clobbers A.
gs_wrd:
        in  a, (GS_CMD)
        rlca
        ret c
        push bc
        push de
        ld  b, GS_STALL
        ld  de, 0
.lp:    ld  a, (gs_dead)
        or  a
        jr  nz, .out
        in  a, (GS_CMD)
        rlca
        jr  c, .out
        dec de
        ld  a, d
        or  e
        jr  nz, .lp
        djnz .lp
        call gs_abort
.out:   pop de
        pop bc
        ret

; the card never answered: it is given up
gs_abort:
        xor a
        ld  (gs_ok), a
        ld  a, 1
        ld  (gs_dead), a
        ret

; A = a command.  Clobbers A.
gs_cmd:
        push af
        call gs_sync
        call gs_wcmd
        pop af
        out (GS_CMD), a
        ret

; A = a command's first argument: it goes before the command, and only
; once the last command has been taken - its handler may still read the
; data port without waiting.  Clobbers A.
gs_arg1:
        push af
        call gs_sync
        call gs_wcmd
        call gs_wdat
        pop af
        out (GS_DATA), a
        ret

; Collect the answer gs_fx_play left behind, if it did: until it is read
; the flag it raised says "the data latch is full" and nothing else can be
; sent.  Clobbers A.
gs_sync:
        ld  a, (gs_pend)
        or  a
        ret z
        xor a
        ld  (gs_pend), a
        call gs_wcmd
        in  a, (GS_DATA)
        ret

; A = a second or later argument, or a data byte.  Clobbers A.
gs_put:
        push af
        call gs_wdat
        pop af
        out (GS_DATA), a
        ret

; A = the card's answer to the command just sent, read as soon as the
; command is taken.
gs_ans:
        call gs_wcmd
        in  a, (GS_DATA)
        ret

; close a $30/$38 stream: the last byte taken, then $D2.  Clobbers A.
gs_end:
        call gs_wdat
        ld  a, $D2
        jr  gs_cmd

; A = a slot (dune_sound.py's name for a card page): the page number the
; ROM found for it.  Clobbers nothing else.
gs_page_of:
        push hl
        ld  hl, gs_ptab
        add a, l
        ld  l, a
        adc a, h
        sub l
        ld  h, a
        ld  a, (hl)
        pop hl
        ret

; A -> the card's byte at DE.  Clobbers AF BC HL.
gs_poke:
        ld  (gs_buf+63), a
        ld  hl, gs_buf+63
        ld  bc, 1

; BC bytes (1-65535) from HL (anywhere the Z80 can see) to the card's
; address DE, with $14.  Out: HL past them.  Clobbers AF BC.
gs_block:
        ld  a, c                ; the length, low first and before the
        call gs_arg1            ; command; not complemented
        ld  a, $14
        call gs_cmd
        ld  a, b
        call gs_put
        ld  a, e
        call gs_put
        ld  a, d
        call gs_put
.lp:    call gs_wdat
        ld  a, (hl)
        out (GS_DATA), a
        inc hl
        dec bc
        ld  a, b
        or  c
        jr  nz, .lp
        ret

; The data of a $14 already begun: SND_CHUNK bytes from HL, as they are
; (gs_send) or each the sum of the bytes so far (gs_send_delta, the sum
; carried in gs_lsum from chunk to chunk).  Clobbers AF BC D HL.
gs_send:
        ld  bc, SND_CHUNK
.lp:    call gs_wdat
        ld  a, (hl)
        out (GS_DATA), a
        inc hl
        dec bc
        ld  a, b
        or  c
        jr  nz, .lp
        ret
gs_send_delta:
        ld  a, (gs_lsum)
        ld  d, a
        ld  bc, SND_CHUNK
.lp:    call gs_wdat
        ld  a, (hl)
        add a, d
        ld  d, a
        out (GS_DATA), a
        inc hl
        dec bc
        ld  a, b
        or  c
        jr  nz, .lp
        ld  a, d
        ld  (gs_lsum), a
        ret

; BC bytes (1-65535) from the card's address DE to HL, with $15.  The
; card sends a byte, and the next once this one has been read.  The flag
; that says "a byte from the card" is the one that said "a byte for the
; card" a moment ago, so the first byte is only there once the command has
; been taken (the handler does that right after sending it).  Clobbers
; AF BC HL.
gs_fetch:
        ld  a, c
        call gs_arg1
        ld  a, $15
        call gs_cmd
        ld  a, b
        call gs_put
        ld  a, e
        call gs_put
        ld  a, d
        call gs_put
        call gs_wcmd
.lp:    call gs_wrd
        in  a, (GS_DATA)
        ld  (hl), a
        inc hl
        dec bc
        ld  a, b
        or  c
        jr  nz, .lp
        ret

; Send (gs_cnt) bytes (24-bit, not 0) from RAM page A, address HL in
; window 3, to the card's data port, going on to the next page at the top
; of this one.  Out: HL and (gs_pg) past them.  Clobbers AF DE.
gs_stream:
        ld  (gs_pg), a
        call gs_map
        ld  de, (gs_cnt)
.lp:    call gs_wdat
        ld  a, (hl)
        out (GS_DATA), a
        inc l
        jr  z, .hi
.cnt:   dec de
        ld  a, d
        or  e
        jr  nz, .lp
        ld  a, (gs_cnt+2)
        or  a
        ret z
        dec a
        ld  (gs_cnt+2), a
        jr  .lp
.hi:    inc h
        jr  nz, .cnt
        ld  a, (gs_pg)          ; off the top of window 3
        inc a
        ld  (gs_pg), a
        call gs_map
        ld  hl, $C000
        jr  .cnt

gs_map:
        push bc
        push de
        push hl
        call map_w3
        pop hl
        pop de
        pop bc
        ret

; A = MUS id: it is the newest (gs_tage = gs_clock + 1, the clock moved
; on).  Keeps A and DE; clobbers C, HL.
gs_age:
        ld  hl, gs_clock
        inc (hl)
        ld  c, (hl)
        ld  hl, gs_tage
        call gs_at
        ld  (hl), c
        ret

; A = MUS id -> IX = its snd_mods record.  Clobbers AF DE.
gs_mod:
        ld  ix, snd_mods
        ld  de, SND_MOD_SIZE
        inc a
.lp:    dec a
        ret z
        add ix, de
        jr  .lp

; A = MUS id -> HL = its card slots in gs_tpg.  Clobbers AF.
gs_tpages:
        push bc
        ld  b, a
        ld  hl, gs_tpg
        inc b
        jr  .at
.lp:    ld  a, l
        add a, SND_WINDOW
        ld  l, a
        jr  nc, .at
        inc h
.at:    djnz .lp
        pop bc
        ret

; HL = a table, A = an index -> HL = the entry's address.  Keeps A.
gs_at:
        push af
        call gs_at_a
        pop af
        ret
gs_at_a:
        add a, l
        ld  l, a
        ret nc
        inc h
        ret

; ============================================================ state

gs_ok:          DB 0            ; 1 once gs_init found the card
gs_dead:        DB 0            ; 1: it stopped answering and was given up
gs_noload:      DB 0            ; 1: DBGF_NOLOAD, after the intro
gs_cur:         DB $FF          ; the MUS id asked for last, $FF none
gs_wait:        DB 0            ; 1: gs_cur is not on the card yet
gs_pend:        DB 0            ; 1: $39's answer is still to be read
gs_pg:          DB 0
gs_cnt:         DS 3
gs_npages:      DB 0            ; card pages the ROM found
gs_ptab:        DS 64           ; slot -> the card's page number ($22)
gs_own:         DS 64           ; slot -> the tune in it (gs_free)
gs_buf:         DS 64
gs_chan:        DS 256          ; the module channels after $30
gs_fxh:         DS SFX_COUNT + 1 ; SFX id -> the handle $38 gave it
gs_tst:         DS MUS_COUNT    ; 0 not on the card, 1 loading, 2 there
gs_tage:        DS MUS_COUNT    ; gs_clock when it last started
gs_tpg:         DS MUS_COUNT * SND_WINDOW ; its card slots
gs_clock:       DB 0
gs_wants:       DS GS_WANTS     ; fetch these next, first first
gs_ld:          DB $FF          ; the tune being loaded, $FF none
gs_ldix:        DW 0            ; ... its snd_mods record
gs_ldc:         DW 0            ; ... its next chunk
gs_lsrc:        DW 0            ; ... where its stream goes on (window 1)
gs_lspg:        DB 0            ; ... in which page
gs_lsum:        DB 0            ; ... the delta's running sum
gs_unp:         DB 0            ; 1: its next chunk is unpacked, not sent
gs_skip:        DB 0            ; calls left to wait before the next try
gs_fxq:         DB 0            ; gs_bg calls left after an effect started
gs_ahead:       DB GS_AHEAD
gs_ahead_fx:    DB GS_AHEAD_FX
gs_backoff:     DB GS_BACKOFF
gs_uend:        DB 0            ; gs_unpack: the chunk's end, high byte
gs_now:         DB 0            ; gs_load_now: the tune
gs_phase:       DB 0            ; gs_tick: 0 the memory test, 1 uploading
gs_up_done:     DW 0            ; ... the upload's cost done so far
gs_up_total:    DW 0            ; ... and in all
gs_nboot:       DB 0            ; the tunes gs_boot_set chose
gs_bnext:       DB 0            ; gs_boot_next: gs_boot's left to go
gs_bintro:      DB 0            ; ... 1: the intro's still to go
gs_boot:        DS MUS_COUNT    ; ... the most wanted first

        INCLUDE "sound.inc"
