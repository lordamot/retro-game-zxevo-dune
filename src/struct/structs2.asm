; structs2.asm - bank STRUCT2: the rest of the STRUCT subsystem.  What a
; factory offers and how it starts, cancels and upgrades (S6), the
; computer's choice, the Starport, a structure's destruction and removal,
; the spice on the map and harvesting (S5), docking, the MCV, and the
; UNIT/BUILD.EMC routines that go with them.  Bank STRUCT (structs.asm)
; has the loop, placing, power and the map animations.

; ================================================ what it offers (S6)

; struct_get_buildable ($00FE58): IX = a structure -> DE:HL = a bit per
; type it may build now (structure types for a Construction Yard, unit
; types for the rest; everything for a Starport).  A Barracks or WOR also
; leaves its list by position in st_unit_list ($0101D0).  Uses the
; structure's house's structuresBuilt (the port's fix, S6: per house).
struct_get_buildable:
        ld  hl, 0
        ld  (st_s2_mask), hl
        ld  (st_s2_mask + 2), hl
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  de, st_s2_built
        ld  bc, 4
        ldir
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jp  z, st_gb_yard
        cp  STRUCT_STARPORT
        jr  z, st_gb_all
        cp  STRUCT_LIGHTFACTORY
        jp  z, st_gb_factory
        cp  STRUCT_HEAVYFACTORY
        jp  z, st_gb_factory
        cp  STRUCT_HITECH
        jp  z, st_gb_hitech
        cp  STRUCT_WOR
        jp  z, st_gb_barracks
        cp  STRUCT_BARRACKS
        jp  z, st_gb_barracks
st_gb_ret: ld  hl, (st_s2_mask)
        ld  de, (st_s2_mask + 2)
        ret
st_gb_all: ld  hl, $FFFF
        ld  (st_s2_mask), hl
        ld  (st_s2_mask + 2), hl
        ld  d, h
        ld  e, l
        ret

; The Construction Yard ($00FEC8).
st_gb_yard:
        ld  b, 0
st_gby_loop:
        push bc
        ld  a, b
        ld  (st_s2_i), a
        call struct_info
        push hl
        pop iy                  ; IY = the type's record
        ld  a, (iy + SI_availableCampaign)
        ld  (st_s2_avail), a
        push iy
        pop hl
        ld  de, SI_structuresRequired
        add hl, de
        ld  de, st_s2_req
        ld  bc, 4
        ldir
        ; the Harkonnen WOR: no Barracks needed, available from 2
        ld  a, (st_s2_i)
        cp  STRUCT_WOR
        jr  nz, st_gby_1
        ld  a, (ix + O_HOUSE)
        or  a
        jr  nz, st_gby_1
        ld  a, (campaign_id)
        or  a
        jr  z, st_gby_1
        ld  hl, st_s2_req + 1
        res 2, (hl)             ; bit 10
        ld  a, 2
        ld  (st_s2_avail), a
st_gby_1:  ; the player's needs what it requires built
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_gby_2
        call st_s2_covers
        jr  nz, st_gby_next
st_gby_2:  ; a non-Harkonnen Light Factory counts as available from 2
        ld  a, (ix + O_HOUSE)
        or  a
        jr  z, st_gby_3
        ld  a, (st_s2_i)
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_gby_3
        ld  a, 2
        ld  (st_s2_avail), a
st_gby_3:  ; never the Heavy Factory or IX; never the WOR for an Ordos player
        ld  a, (st_s2_i)
        cp  STRUCT_HEAVYFACTORY
        jr  z, st_gby_next
        cp  STRUCT_IX
        jr  z, st_gby_next
        cp  STRUCT_WOR
        jr  nz, st_gby_4
        ld  a, (player_house)
        cp  HOUSE_ORDOS
        jr  z, st_gby_next
st_gby_4:  ; campaign >= available - 1
        ld  a, (campaign_id)
        inc a
        ld  hl, st_s2_avail
        cp  (hl)
        jr  c, st_gby_next
        ; the house may have it
        ld  a, (ix + O_HOUSE)
        call st_s2_bit_of
        and (iy + SI_availableHouse)
        jr  z, st_gby_next
        ; its level, or the computer's
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_gby_take
        ld  a, (iy + SI_upgradeLevelRequired)
        ld  b, a
        ld  a, (ix + S_UPGRADELEVEL)
        cp  b
        jr  c, st_gby_next
st_gby_take:
        ld  a, (st_s2_i)
        call st_s2_mset
st_gby_next:
        pop bc
        inc b
        ld  a, b
        cp  STRUCT_INFO_COUNT
        jp  c, st_gby_loop
        ; the 4-Slab always
        ld  a, STRUCT_SLAB4
        call st_s2_mset
        ; no room: only the 4-Slab and the Wall
        bit 0, (ix + O_FLAGS2 + 1)
        jr  z, st_gby_5
        ld  a, (st_s2_mask)
        and $02
        ld  (st_s2_mask), a
        ld  a, (st_s2_mask + 1)
        and $40
        ld  (st_s2_mask + 1), a
        xor a
        ld  (st_s2_mask + 2), a
        ld  (st_s2_mask + 3), a
        jp  st_gb_ret
st_gby_5:  ; one Palace and one Starport a house ($00FFE2)
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_PALACE
        call st_s2_stc_addr
        ld  a, (hl)
        or  a
        ld  a, STRUCT_PALACE
        call nz, st_s2_mclr
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_STARPORT
        call st_s2_stc_addr
        ld  a, (hl)
        or  a
        ld  a, STRUCT_STARPORT
        call nz, st_s2_mclr
        jp  st_gb_ret

; The Light and Heavy Factories ($01001A, $0100D6): hard-coded by
; campaign, level and the creator house.
st_gb_factory:
        ld  a, (campaign_id)
        ld  c, a                ; C = the campaign
        ld  a, (ix + S_UPGRADELEVEL)
        ld  b, a                ; B = the level
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HEAVYFACTORY
        jp  nz, st_gbf_light
        ld  a, c
        cp  3
        jp  c, st_gbf_quad
        cp  9
        jp  nc, st_gbf_quad
        cp  6
        jr  c, st_gbf_h1
        ld  a, UNIT_SIEGETANK
        call st_s2_mset
        ld  a, (st_s2_built)
        bit 5, a                ; a Hi-Tech built
        jr  z, st_gbf_h1
        ld  a, (ix + S_CREATORHOUSE)
        or  a
        ld  d, UNIT_DEVASTATOR
        jr  z, st_gbf_h0
        cp  HOUSE_ATREIDES
        ld  d, UNIT_SONICTANK
        jr  z, st_gbf_h0
        cp  HOUSE_ORDOS
        ld  d, UNIT_DEVIATOR
        jr  z, st_gbf_h0
        cp  HOUSE_SARDAUKAR
        jr  nz, st_gbf_h1
        ld  a, (player_house)
        ld  d, UNIT_SONICTANK
        or  a
        jr  z, st_gbf_h0
        ld  d, UNIT_DEVASTATOR
        cp  HOUSE_ATREIDES
        jr  z, st_gbf_h0
        cp  HOUSE_ORDOS
        jr  nz, st_gbf_h1
        ld  a, UNIT_SONICTANK
        call st_s2_mset
st_gbf_h0: ld  a, d
        call st_s2_mset
st_gbf_h1: ld  a, c
        cp  5
        jr  c, st_gbf_h2
        ld  a, b
        cp  3
        jr  c, st_gbf_h2
        ld  a, UNIT_SIEGETANK
        call st_s2_mset
st_gbf_h2: ld  a, c
        cp  4
        jr  c, st_gbf_h3
        ld  a, b
        cp  2
        jr  c, st_gbf_h3
        ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_ORDOS
        jr  z, st_gbf_h3
        ld  a, UNIT_LAUNCHER
        call st_s2_mset
st_gbf_h3: ld  a, b
        or  a
        jr  z, st_gbf_h4
        ld  a, UNIT_MCV
        call st_s2_mset
st_gbf_h4: ld  a, UNIT_HARVESTER
        call st_s2_mset
        ld  a, UNIT_TANK
        call st_s2_mset
st_gbf_quad:
        ld  a, UNIT_QUAD
        call st_s2_mset
st_gbf_light:
        ld  a, c
        or  a
        jr  z, st_gbf_out
        cp  9
        jr  nc, st_gbf_out
        cp  2
        jr  c, st_gbf_l1
        ld  a, b
        or  a
        jr  z, st_gbf_l1
        ld  a, UNIT_QUAD
        call st_s2_mset
st_gbf_l1: ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_ATREIDES
        jr  z, st_gbf_trike
        cp  HOUSE_SARDAUKAR
        jr  z, st_gbf_trike
        cp  HOUSE_ORDOS
        jr  nz, st_gbf_out
        ld  a, UNIT_RAIDERTRIKE
        jr  st_gbf_l2
st_gbf_trike:
        ld  a, UNIT_TRIKE
st_gbf_l2: call st_s2_mset
st_gbf_out:
        ; no Outpost: no Launcher, Tank, Siege Tank or MCV
        ld  a, (st_s2_built + 2)
        bit 2, a
        jr  nz, st_gbf_list
        ld  a, (st_s2_mask)
        and $7F
        ld  (st_s2_mask), a
        ld  a, (st_s2_mask + 1)
        and $F9
        ld  (st_s2_mask + 1), a
        ld  a, (st_s2_mask + 2)
        and $FD
        ld  (st_s2_mask + 2), a
st_gbf_list:
        ; the list by unit type ($010148)
        ld  b, 0
        ld  hl, st_unit_list
st_gbf_ls: ld  a, b
        call st_s2_mtest
        ld  (hl), 1
        jr  nz, st_gbf_ls1
        ld  (hl), $FF
st_gbf_ls1:
        inc hl
        inc b
        ld  a, b
        cp  27
        jr  c, st_gbf_ls
        jp  st_gb_ret

; The Hi-Tech ($010170): the Carryall from campaign 4, the 'Thopter from
; campaign 6 at level 1 and up.
st_gb_hitech:
        ld  a, (campaign_id)
        cp  4
        jr  c, st_gbf_list
        cp  9
        jr  nc, st_gbf_list
        cp  6
        jr  c, st_gbh_1
        ld  a, (ix + S_UPGRADELEVEL)
        or  a
        jr  z, st_gbh_1
        ld  a, UNIT_THOPTER
        call st_s2_mset
st_gbh_1:  ld  a, UNIT_CARRYALL
        call st_s2_mset
        jr  st_gbf_list

; The Barracks and the WOR ($0101D0): the type's buildableUnits.  The
; list is by position: 1 offered, $FF one upgrade off, 0 not.
st_gb_barracks:
        ld  hl, st_unit_list
        ld  b, 27
st_gbb_0:  ld  (hl), 0
        inc hl
        djnz st_gbb_0
        xor a
        ld  (st_s2_i), a
st_gbb_loop:
        call st_s2_info
        ld  de, SI_buildableUnits
        add hl, de
        ld  a, (st_s2_i)
        add a, a
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, (hl)
        inc hl
        and (hl)
        inc a
        jp  z, st_gbb_next         ; -1 unused
        dec hl
        ld  a, (hl)
        ld  (st_s2_u), a
        ; an Ordos-built one offers the Raider Trike for the Trike
        cp  UNIT_TRIKE
        jr  nz, st_gbb_1
        ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_gbb_1
        ld  a, UNIT_RAIDERTRIKE
        ld  (st_s2_u), a
st_gbb_1:  ld  a, (st_s2_u)
        call unit_info
        push hl
        pop iy
        ld  a, (iy + UI_upgradeLevelRequired)
        ld  (st_s2_need), a
        push iy
        pop hl
        ld  de, UI_structuresRequired
        add hl, de
        ld  de, st_s2_req
        ld  bc, 4
        ldir
        call st_s2_covers
        jr  nz, st_gbb_next
        ld  a, (ix + S_CREATORHOUSE)
        call st_s2_bit_of
        and (iy + UI_availableHouse)
        jr  z, st_gbb_next
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_gbb_2
        ld  a, (ix + O_TYPE)
        cp  STRUCT_BARRACKS
        jr  nz, st_gbb_o1
        ld  a, (st_s2_u)
        cp  UNIT_TROOPER
        jr  nz, st_gbb_2
        ld  a, 9
        ld  (st_s2_need), a
        jr  st_gbb_2
st_gbb_o1: ld  a, (st_s2_u)
        cp  UNIT_INFANTRY
        jr  nz, st_gbb_2
        xor a
        ld  (st_s2_need), a
st_gbb_2:  ld  hl, st_unit_list
        ld  a, (st_s2_i)
        ld  e, a
        ld  d, 0
        add hl, de
        ld  a, (st_s2_need)
        ld  b, a
        ld  a, (ix + S_UPGRADELEVEL)
        cp  b
        jr  c, st_gbb_3
        ld  (hl), 1
        ld  a, (st_s2_u)
        call st_s2_mset
        jr  st_gbb_next
st_gbb_3:  inc a
        cp  b
        jr  c, st_gbb_next
        ld  a, (ix + S_UPGRADETIME)
        or  a
        jr  z, st_gbb_next
        ld  (hl), $FF
st_gbb_next:
        ld  hl, st_s2_i
        inc (hl)
        ld  a, (hl)
        cp  10
        jp  c, st_gbb_loop
        jp  st_gb_ret

; struct_is_upgradable ($010BA2): IX = a structure -> A = 1 or 0 (by its
; creator house).
struct_is_upgradable:
        ld  a, (campaign_id)
        ld  c, a
        ld  a, (ix + S_CREATORHOUSE)
        ld  d, a
        ld  a, (ix + O_TYPE)
        ld  e, a
        ld  b, (ix + S_UPGRADELEVEL)
        ; never a Harkonnen Hi-Tech
        cp  STRUCT_HITECH
        jr  nz, st_siu_1
        ld  a, d
        or  a
        jp  z, st_siu_no
st_siu_1:  ; an Ordos Heavy Factory
        ld  a, e
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_siu_2
        ld  a, d
        cp  HOUSE_ORDOS
        jr  nz, st_siu_2
        ld  a, c
        cp  5
        jr  z, st_siu_yes
        jp  nc, st_siu_no
        ld  a, b
        cp  1
        jr  nz, st_siu_2
        push bc
        ld  a, 2
        call st_siu_ucampaign
        pop bc
        cp  c
        jr  z, st_siu_2
        jr  nc, st_siu_no          ; campaign < upgradeCampaign[2]
st_siu_2:  ld  a, b
        cp  3
        jr  nc, st_siu_last
        push bc
        push de
        call st_siu_ucampaign      ; A = upgradeCampaign[level]
        pop de
        pop bc
        or  a
        jr  z, st_siu_last
        dec a
        cp  c
        jr  z, st_siu_3
        jr  nc, st_siu_last        ; n - 1 > campaign
st_siu_3:  ld  a, e
        cp  STRUCT_CONSTYARD
        jr  nz, st_siu_4
        ; the Yard needs what the Rocket Turret needs, in its creator house
        push bc
        push de
        ld  a, d
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  de, st_s2_built
        ld  bc, 4
        ldir
        ld  a, STRUCT_RTURRET
        call struct_info
        ld  de, SI_structuresRequired
        add hl, de
        ld  de, st_s2_req
        ld  bc, 4
        ldir
        call st_s2_covers
        pop de
        pop bc
        jr  nz, st_siu_no
st_siu_4:  ld  a, e
        cp  STRUCT_BARRACKS
        jr  nz, st_siu_5
        ld  a, d
        cp  HOUSE_ATREIDES
        jr  nz, st_siu_5
        ld  a, b
        cp  1
        jr  z, st_siu_no
st_siu_5:  ld  a, e
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_siu_yes
        ld  a, d
        cp  HOUSE_ORDOS
        jr  nz, st_siu_yes
        ld  a, c
        cp  7
        jr  nc, st_siu_no
st_siu_yes:
        ld  a, 1
        ret
st_siu_last:
        ; a Harkonnen WOR at level 0 from campaign 3
        ld  a, e
        cp  STRUCT_WOR
        jr  nz, st_siu_no
        ld  a, d
        or  a
        jr  nz, st_siu_no
        ld  a, b
        or  a
        jr  nz, st_siu_no
        ld  a, c
        cp  3
        jr  nc, st_siu_yes
st_siu_no: xor a
        ret
; A = 0-2 -> A = upgradeCampaign[A] of IX's type.
st_siu_ucampaign:
        add a, a
        ld  c, a
        push bc
        call st_s2_info
        pop bc
        ld  de, SI_upgradeCampaign
        add hl, de
        ld  e, c
        ld  d, 0
        add hl, de
        ld  a, (hl)
        ret

; struct_init_upgrade_level ($010A98): IX = a computer's structure: its
; starting level by campaign.
struct_init_upgrade_level:
        ld  a, (campaign_id)
        ld  c, a
        ld  b, (ix + S_UPGRADELEVEL)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_sil_1
        ld  a, c
        cp  2
        jp  c, st_sil_set
        ld  b, 1
        jp  st_sil_set
st_sil_1:  cp  STRUCT_HEAVYFACTORY
        jr  nz, st_sil_2
        ld  a, c
        ld  b, 1
        cp  3
        jr  z, st_sil_set
        ld  b, 2
        cp  4
        jr  z, st_sil_set
        ld  b, 3
        cp  5
        jr  c, st_sil_keep
        cp  9
        jr  c, st_sil_set
st_sil_keep:
        ld  b, (ix + S_UPGRADELEVEL)
        jr  st_sil_set
st_sil_2:  cp  STRUCT_HITECH
        jr  nz, st_sil_3
        ld  a, c
        cp  6
        jr  c, st_sil_z
        ld  a, (ix + S_CREATORHOUSE)
        or  a
        jr  z, st_sil_z
        ld  b, 1
        jr  st_sil_set
st_sil_3:  cp  STRUCT_WOR
        jr  nz, st_sil_4
        ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_sil_3a
        ld  a, c
        cp  5
        jr  c, st_sil_3a
        ld  b, 1
st_sil_3a: ld  a, (ix + S_CREATORHOUSE)
        or  a
        jr  nz, st_sil_set
        ld  a, c
        cp  3
        jr  c, st_sil_set
        ld  b, 1
        jr  st_sil_set
st_sil_4:  cp  STRUCT_CONSTYARD
        jr  nz, st_sil_5
        ld  a, c
        cp  5
        jr  c, st_sil_z
        ld  b, 1
        jr  st_sil_set
st_sil_5:  cp  STRUCT_BARRACKS
        jr  nz, st_sil_6
        ld  a, c
        or  a
        jr  z, st_sil_z
        ld  b, 1
        jr  st_sil_set
st_sil_6:  cp  STRUCT_LIGHTFACTORY
        ret c
        cp  STRUCT_BARRACKS + 1
        ret nc
st_sil_z:  ; types 3-10 not raised stay at 0 (the model's "return 0")
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HITECH
        jr  z, st_sil_zk
        cp  STRUCT_CONSTYARD
        jr  z, st_sil_zk
        cp  STRUCT_BARRACKS
        jr  z, st_sil_zk
        ld  b, 0
        jr  st_sil_set
st_sil_zk: ld  b, (ix + S_UPGRADELEVEL)
st_sil_set:
        ld  (ix + S_UPGRADELEVEL), b
        ret

; struct_default_build_type ($010D9E): IX = a factory -> HL = what it
; offers first.
struct_default_build_type:
        ld  a, (ix + S_CREATORHOUSE)
        call house_ptr
        ld  de, H_BUILT + 2
        add hl, de
        ld  c, (hl)             ; bit 2 = bit 18, the Outpost
        ld  b, (ix + S_UPGRADELEVEL)
        ld  a, (ix + O_TYPE)
        ld  l, UNIT_QUAD
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_sdb_1
        ld  a, b
        cp  1
        jr  nz, st_sdb_ret
        ld  l, UNIT_HARVESTER
        jr  st_sdb_ret
st_sdb_1:  cp  STRUCT_HEAVYFACTORY
        jr  nz, st_sdb_2
        ld  l, UNIT_HARVESTER
        bit 2, c
        jr  z, st_sdb_ret
        ld  a, b
        cp  1
        jr  nz, st_sdb_1a
        ld  l, UNIT_LAUNCHER
        ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_sdb_ret
        ld  l, UNIT_SIEGETANK
        jr  st_sdb_ret
st_sdb_1a: ld  l, UNIT_SIEGETANK
        cp  2
        jr  z, st_sdb_ret
        ld  l, UNIT_MCV
        jr  st_sdb_ret
st_sdb_2:  cp  STRUCT_HITECH
        jr  nz, st_sdb_3
        ld  l, UNIT_CARRYALL
        ld  a, (ix + O_HOUSE)
        or  a
        jr  z, st_sdb_ret
        ld  l, UNIT_THOPTER
        jr  st_sdb_ret
st_sdb_3:  cp  STRUCT_WOR
        ld  l, UNIT_TROOPERS
        jr  z, st_sdb_ret
        cp  STRUCT_BARRACKS
        ld  l, 0
        jr  nz, st_sdb_ret
        ld  l, UNIT_INFANTRY
        ld  a, (ix + O_HOUSE)
        cp  HOUSE_ORDOS
        jr  nz, st_sdb_ret
        ld  a, b
        cp  1
        jr  nz, st_sdb_ret
        ld  l, UNIT_TROOPER
st_sdb_ret:
        ld  a, l
        call st_offer_of
        ld  l, a
        ld  h, 0
        ret

; The port's own rule (gamedesign.md): what a factory shows and starts
; on B is an item its panel offers - the cartridge's Light Factory in a
; mission whose list holds only the Trike shows the Quad and builds it.
; A = a unit type -> A = it if the structure IX offers it, else the first
; type it offers (or A as it was when it offers nothing).  Keeps IX.
st_offer_of:
        push af
        call struct_get_buildable   ; DE:HL = a bit per type
        pop af
        ld  c, a
        ld  a, d
        or  e
        or  h
        or  l
        ld  a, c
        ret z
        ld  b, c
        push de
        push hl
        inc b
st_oo_1:   dec b
        jr  z, st_oo_2
        srl d
        rr  e
        rr  h
        rr  l
        jr  st_oo_1
st_oo_2:   bit 0, l
        pop hl
        pop de
        ld  a, c
        ret nz
        ld  c, 0
st_oo_3:   bit 0, l
        jr  nz, st_oo_4
        srl d
        rr  e
        rr  h
        rr  l
        inc c
        jr  st_oo_3
st_oo_4:   ld  a, c
        ret

; IX = a factory: its objectType put right by st_offer_of.
struct_offer_fix:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ret z
        cp  STRUCT_STARPORT
        ret z
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        ret nz                  ; none
        ld  a, (ix + S_OBJECTTYPE)
        call st_offer_of
        ld  (ix + S_OBJECTTYPE), a
        ret

; struct_upgrade_by_mission ($0293C4): IX = a building the player has just
; placed from the Yard: its level by campaign; from campaign 4 a Light
; Factory is a Heavy Factory already (its type counts move); then a
; factory's first item.
struct_upgrade_by_mission:
        ld  a, (ix + O_TYPE)
        cp  STRUCT_LIGHTFACTORY
        jr  nz, st_sum_2
        ld  a, (campaign_id)
        cp  3
        jr  c, st_sum_1
        jr  nz, st_sum_1a
        ld  (ix + S_UPGRADELEVEL), 1
        jr  st_sum_1
st_sum_1a: cp  9
        jr  nc, st_sum_1
        ld  c, a
        ld  a, (player_house)
        ld  b, a
        ld  a, c
        cp  7
        jr  c, st_sum_1b
        ; 7-8: +1 Atreides
        ld  a, b
        cp  HOUSE_ATREIDES
        jr  nz, st_sum_1c
        inc (ix + S_UPGRADELEVEL)
st_sum_1c: ld  a, 6
st_sum_1b: cp  6
        jr  c, st_sum_1d
        ; 6-8: +1 unless Ordos
        ld  a, b
        cp  HOUSE_ORDOS
        jr  z, st_sum_1e
        inc (ix + S_UPGRADELEVEL)
st_sum_1e: ld  a, 5
st_sum_1d: cp  5
        jr  c, st_sum_1f
        inc (ix + S_UPGRADELEVEL)
st_sum_1f: ; a Heavy Factory, the counts moved
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_LIGHTFACTORY
        call st_s2_stc_addr
        dec (hl)
        ld  (ix + O_TYPE), STRUCT_HEAVYFACTORY
        ld  a, STRUCT_HEAVYFACTORY
        call st_s2_stc_addr
        inc (hl)
st_sum_1:  call struct_default_build_type
        ld  (ix + S_OBJECTTYPE), l
        ld  (ix + S_OBJECTTYPE + 1), h
st_sum_2:  ld  a, (ix + O_TYPE)
        cp  STRUCT_HITECH
        jr  nz, st_sum_3
        ld  a, (campaign_id)
        cp  7
        jr  c, st_sum_2a
        cp  9
        jr  nc, st_sum_2a
        ld  a, (player_house)
        or  a
        jr  z, st_sum_2a
        inc (ix + S_UPGRADELEVEL)
st_sum_2a: call struct_default_build_type
        ld  (ix + S_OBJECTTYPE), l
        ld  (ix + S_OBJECTTYPE + 1), h
st_sum_3:  ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ret nz
        ld  a, (campaign_id)
        ld  b, 1
        cp  7
        jr  z, st_sum_3a
        cp  8
        jr  z, st_sum_3a
        ld  b, 0
st_sum_3a: ld  (ix + S_UPGRADELEVEL), b
        ret

; ================================================ starting a build (S6)

; struct_build_object ($00FA84, PC Structure_BuildObject): IX = a
; factory, HL = the argument: -3 clears creditsPaid; -1 and -2 fill the
; panel's lists (-2 also takes the first item as objectType); 1 at a
; Starport delivers the order; a type starts building it.  -> HL = 1 if
; a build started (or the Starport's answer), 0 if not.
struct_build_object:
        ld  (st_s2_arg), hl
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        pop iy
        call st_s2_info
        ld  de, SI_flags
        add hl, de
        bit 1, (hl)
        jp  z, st_bo_zero
        ld  hl, (st_s2_arg)
        ld  a, h
        inc a
        jp  nz, st_bo_start
        ld  a, l
        cp  $FD
        jr  nz, st_bo_lists
        ld  (ix + S_CREDITSPAID), 0
        ld  (ix + S_CREDITSPAID + 1), 0
        jp  st_bo_zero
st_bo_lists:
        cp  $FE
        jp  c, st_bo_start
        ; -1 / -2: is an upgrade offered? (the cost is only a yes/no; the
        ; full-health test cannot fail, $00FB16 - kept)
        xor a
        ld  (st_s2_upg), a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  z, st_bo_l1
        ld  a, (ix + S_CREATORHOUSE)
        cp  HOUSE_SARDAUKAR
        jr  z, st_bo_l1
        call struct_is_upgradable
        or  a
        jr  z, st_bo_l1
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HITECH
        jr  nz, st_bo_l0
        ld  a, (ix + O_HOUSE)
        or  a
        jr  z, st_bo_l1
st_bo_l0:  ld  a, 1
        ld  (st_s2_upg), a
st_bo_l1:  ; an upgrade needs an Outpost too
        bit 2, (iy + H_BUILT + 2)
        jr  nz, st_bo_l2
        xor a
        ld  (st_s2_upg), a
st_bo_l2:  call struct_get_buildable
        ld  a, h
        or  l
        or  d
        or  e
        jr  nz, st_bo_l3
        ld  (ix + S_OBJECTTYPE), a
        ld  (ix + S_OBJECTTYPE + 1), a
        jp  st_bo_zero
st_bo_l3:  ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_bo_units
        ld  a, 1
        ld  (st_list_is_yard), a
        ld  hl, st_yard_list
        ld  c, STRUCT_INFO_COUNT
        call st_bo_fill
        ret z                   ; -2 took the first
        ld  a, $FF
        ld  (st_yard_upgrade), a
        ld  a, (st_s2_upg)
        or  a
        jr  z, st_bo_ldone
        ld  a, $10
        ld  (st_yard_upgrade), a
        jr  st_bo_ldone
st_bo_units:
        xor a
        ld  (st_list_is_yard), a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  z, st_bo_ldone
        ld  hl, st_unit_list
        ld  c, 27
        call st_bo_fill
        ret z
        ld  a, $FF
        ld  (st_unit_upgrade), a
        ld  a, (st_s2_upg)
        or  a
        jr  z, st_bo_ldone
        call struct_default_build_type
        ld  e, a
        ld  d, 0
        ld  hl, st_unit_list
        add hl, de
        ld  a, (hl)
        cp  $FF
        jr  nz, st_bo_ldone
        ld  a, e
        ld  (st_unit_upgrade), a
st_bo_ldone:
        ld  hl, (st_s2_arg)
        ld  a, l
        and h
        inc a
        jp  z, st_bo_zero
        ld  (ix + S_OBJECTTYPE), l
        ld  (ix + S_OBJECTTYPE + 1), h
        jp  st_bo_zero

; HL -> a list, C = its length: item i = i if offered, else $FF; with
; the argument -2 the first offered becomes objectType and it answers Z
; (HL = 0) at once.  Otherwise NZ.
st_bo_fill:
        ld  b, 0
st_bof_1:  ld  a, b
        call st_s2_mtest
        jr  z, st_bof_2
        ld  (hl), b
        ld  a, (st_s2_arg)
        cp  $FE
        jr  nz, st_bof_3
        ld  (ix + S_OBJECTTYPE), b
        ld  (ix + S_OBJECTTYPE + 1), 0
        ld  hl, 0
        xor a
        ret
st_bof_2:  ld  (hl), $FF
st_bof_3:  inc hl
        inc b
        ld  a, b
        cp  c
        jr  c, st_bof_1
        or  1
        ret

st_bo_start:
        ; a type ($00FC38)
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jp  z, st_bo_starport
        ld  hl, (st_s2_arg)
        ld  e, (ix + S_OBJECTTYPE)
        ld  d, (ix + S_OBJECTTYPE + 1)
        or  a
        sbc hl, de
        ld  a, h
        or  l
        ld  (st_s2_same), a        ; 0: the same type as in hand
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_bo_s1
        ld  a, (st_s2_same)
        or  a
        jr  nz, st_bo_cancel
        jr  st_bo_s2
st_bo_s1:  bit st_S2_DONE_B, (ix + O_FLAGS2 + 1)
        jr  nz, st_bo_s2
        ld  a, (st_s2_same)
        or  a
        jr  nz, st_bo_cancel
st_bo_s2:  bit 1, (ix + O_FLAGS2)
        jr  z, st_bo_make
st_bo_cancel:
        call struct_cancel_build
st_bo_make:
        ; $00FDB0
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  nz, st_bo_zero
        ld  hl, (st_s2_arg)
        ld  a, h
        and l
        inc a
        jp  z, st_bo_zero
        ld  hl, (st_s2_arg)
        push hl
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_bo_m_unit
        push ix
        push iy
        ld  b, $FF
        ld  c, l
        ld  d, (ix + O_HOUSE)
        ld  hl, $FFFF
        FCALL struct_create
        pop iy
        pop ix
        jr  st_bo_m1
st_bo_m_unit:
        ld  a, $FF
        ld  (arg_pos), a
        ld  (arg_pos + 1), a
        ld  (arg_pos + 2), a
        ld  (arg_pos + 3), a
        push ix
        push iy
        ld  b, l
        ld  c, (ix + O_HOUSE)
        ld  d, 0
        ld  a, $FF
        FCALL unit_spawn
        pop iy
        pop ix
st_bo_m1:  pop de                  ; the type
        res st_SF_ONHOLD_B, (ix + O_FLAGS + 1)
        ld  a, h
        or  l
        jr  z, st_bo_zero
        ld  a, (hl)             ; its index
        ld  (ix + O_LINKED), a
        ld  (ix + S_OBJECTTYPE), e
        ld  (ix + S_OBJECTTYPE + 1), d
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, e
        jr  nz, st_bo_m2
        call struct_info
        jr  st_bo_m3
st_bo_m2:  call unit_info
st_bo_m3:  ld  de, UI_buildTime
        add hl, de
        ld  a, (hl)
        ld  (ix + S_COUNTDOWN + 1), a
        ld  (ix + S_COUNTDOWN), 0
        ld  (ix + S_CREDITSPAID), 0
        ld  (ix + S_CREDITSPAID + 1), 0
        ld  (ix + S_STATE), 1
        ld  (ix + S_STATE + 1), 0
        ld  hl, 1
        ld  a, 1
        ret
st_bo_zero:
        ld  hl, 0
        xor a
        ret

; The Starport ($00FC82): 1 delivers the order - every offer with units
; ordered makes them off the map, chained to the house's starportLinkedID
; for the Frigate; the Starport goes busy, the house's countdown starts.
; A unit that cannot be made is refunded (the offer's price for the
; player, its cost for the computer).  Anything else does nothing.  Both
; answer 1.
st_bo_starport:
        ld  hl, (st_s2_arg)
        dec hl
        ld  a, h
        or  l
        jp  nz, st_bo_sp_done
        ld  hl, st_starport_offers
        ld  b, 10
st_bo_sp1: push bc
        push hl
st_bo_sp2: ld  a, (hl)             ; the type
        inc a
        jp  z, st_bo_sp_next
        push hl
        pop iy                  ; IY = the offer (for now)
        ld  a, (iy + st_SO_ORDERED)
        or  a
        jp  z, st_bo_sp_next
        jp  m, st_bo_sp_next
        ld  a, $FF
        ld  (arg_pos), a
        ld  (arg_pos + 1), a
        ld  (arg_pos + 2), a
        ld  (arg_pos + 3), a
        ld  hl, validate_strict
        inc (hl)
        push iy
        push ix
        ld  b, (iy + st_SO_TYPE)
        ld  c, (ix + O_HOUSE)
        ld  d, 0
        ld  a, $FF
        FCALL unit_spawn
        pop ix
        pop iy
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        jr  z, st_bo_sp_fail
        push hl
        ld  (ix + S_STATE), 1
        ld  (ix + S_STATE + 1), 0
        ld  a, (ix + O_INDEX)
        ld  (st_starport_index), a
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        ld  de, H_STARPORTTIME
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  nz, st_bo_sp3
        push hl
        ld  a, (ix + O_HOUSE)
        call house_info
        ld  de, HI_starportDeliveryTime
        add hl, de
        ld  a, (hl)
        inc hl
        ld  c, (hl)
        pop hl
        ld  (hl), c
        dec hl
        ld  (hl), a
st_bo_sp3: pop hl                  ; the house
        ld  de, H_STARPORTLINK
        add hl, de
        pop de                  ; the unit
        push de
        ld  a, (hl)
        inc de
        inc de
        inc de
        ld  (de), a             ; its linkedID = the chain
        pop de
        ld  a, (de)             ; its index
        ld  (hl), a
        inc hl
        ld  (hl), 0
        ; the unit: a Starport cargo not yet put down
        push de
        ld  hl, O_FLAGS2 + 1
        add hl, de
        set 1, (hl)             ; flags2 bit 9
        pop de
        ld  hl, (st_starport_cargo_pending)
        inc hl
        ld  (st_starport_cargo_pending), hl
        ; the stock goes down
        ld  a, (iy + st_SO_TYPE)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, starport_available
        add hl, de
        ld  a, (hl)
        inc hl
        or  (hl)
        jr  z, st_bo_sp4
        dec hl
        ld  a, (hl)
        sub 1
        ld  (hl), a
        inc hl
        ld  a, (hl)
        sbc a, 0
        ld  (hl), a
st_bo_sp4: dec (iy + st_SO_ORDERED)
        push iy
        pop hl
        jp  nz, st_bo_sp2          ; this offer again
        jr  st_bo_sp_next
st_bo_sp_fail:
        ; its price back
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_bo_sp_f1
        ld  e, (iy + st_SO_PRICE)
        ld  d, (iy + st_SO_PRICE + 1)
        jr  st_bo_sp_f2
st_bo_sp_f1:
        ld  a, (iy + st_SO_TYPE)
        call unit_info
        ld  de, UI_buildCredits
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
st_bo_sp_f2:
        pop iy
        call st_s2_cr_add
st_bo_sp_next:
        pop hl
        ld  de, st_SO_SIZE
        add hl, de
        pop bc
        dec b
        jp  nz, st_bo_sp1
st_bo_sp_done:
        ld  hl, 1
        ld  a, 1
        ret

; struct_cancel_build ($0103A6): IX = the structure.  What it is making is
; freed, and every credit paid for it or for an upgrade in progress comes
; back (the Mega Drive refunds all of creditsPaid).
struct_cancel_build:
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        pop iy
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, st_scb_2
        push ix
        ld  c, a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, c
        jr  nz, st_scb_1
        call struct_ptr
        push hl
        pop ix
        FCALL struct_free
        jr  st_scb_1a
st_scb_1:  call unit_ptr
        push hl
        pop ix
        push iy
        FCALL unit_free
        pop iy
st_scb_1a: pop ix
        res st_SF_ONHOLD_B, (ix + O_FLAGS + 1)
        ld  (ix + S_COUNTDOWN), 0
        ld  (ix + S_COUNTDOWN + 1), 0
        ld  (ix + O_LINKED), $FF
        call st_scb_refund
st_scb_2:  bit 1, (ix + O_FLAGS2)
        ret z
        ld  (ix + S_UPGRADETIME), 0
        ld  (ix + S_TYPEAFTERUPG), 0
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_scb_3
        ld  (ix + S_OBJECTTYPE), STRUCT_SLAB4
        ld  (ix + S_OBJECTTYPE + 1), 0
st_scb_3:  res 1, (ix + O_FLAGS2)
st_scb_refund:
        ld  e, (ix + S_CREDITSPAID)
        ld  d, (ix + S_CREDITSPAID + 1)
        call st_s2_cr_add
        ld  (ix + S_CREDITSPAID), 0
        ld  (ix + S_CREDITSPAID + 1), 0
        ret

; struct_ai_pick_next_build ($0234FC): IX = a computer's factory -> HL =
; the type to build, $FFFF none.  A Yard rebuilds the first lost
; structure it may; a factory draws a random number per candidate and
; takes the first whose number is 0 mod 4 at once (the Mega Drive rule),
; else the highest priorityBuild.
struct_ai_pick_next_build:
        call struct_get_buildable
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HITECH
        jr  nz, st_sap_1
        ; a Carryall of the house anywhere: no Carryall
        ld  b, (ix + O_HOUSE)
        ld  c, UNIT_CARRYALL
        call st_s2_ufind_one
        jr  z, st_sap_1
        xor a
        call st_s2_mclr
st_sap_1:  ld  a, (ix + O_TYPE)
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_sap_2
        ld  a, (st_s2_mask + 2)
        and $FC                 ; no Harvester, no MCV
        ld  (st_s2_mask + 2), a
st_sap_2:  ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        jr  nz, st_sap_units
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_REBUILD
        add hl, de
        ld  b, 5
st_sap_y1: ld  a, (hl)
        or  a
        jr  z, st_sap_y2
        call st_s2_mtest
        jr  z, st_sap_y2
        ld  l, a
        ld  h, 0
        ret
st_sap_y2: inc hl
        inc hl
        inc hl
        inc hl
        djnz st_sap_y1
        ld  hl, $FFFF
        ret
st_sap_units:
        ld  hl, $FFFF
        ld  (st_s2_best), hl
        ld  b, 0
st_sap_u1: ld  a, b
        call st_s2_mtest
        jr  z, st_sap_u3
        call random
        and 3
        jr  nz, st_sap_u2
        ld  l, b
        ld  h, 0
        ret
st_sap_u2: ld  a, b
        cp  27
        jr  nc, st_sap_u3
        ld  a, (st_s2_best)
        inc a
        jr  z, st_sap_take         ; none yet
        push bc
        ld  a, b
        call unit_info
        ld  de, UI_priorityBuild
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        push de
        ld  a, (st_s2_best)
        call unit_info
        ld  de, UI_priorityBuild
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a                ; best's
        pop de                  ; this one's
        pop bc
        ; this > best (signed)?
        or  a
        sbc hl, de
        jp  po, st_sap_nov
        ; overflow: flip the sign test
        jp  m, st_sap_u3
        jr  st_sap_take
st_sap_nov:
        jp  p, st_sap_u3           ; best - this >= 0: keep
st_sap_take:
        ld  a, b
        ld  (st_s2_best), a
        xor a
        ld  (st_s2_best + 1), a
st_sap_u3: inc b
        ld  a, b
        cp  32
        jr  c, st_sap_u1
        ld  hl, (st_s2_best)
        ret

; struct_check_build_choice ($00DEA0): IX = a Construction Yard or Heavy
; Factory, every pass (struct_animate).  Where what its house needs has
; gone, a build the panel started (flags2 bit 14) is cancelled and the
; panel's choice replaced by a stand-in.
struct_check_build_choice:
        bit 7, (ix + O_LINKED)
        jr  z, st_scc_0
        ld  (ix + O_LINKED), $FF
        ld  a, (ix + O_FLAGS2 + 1)
        and $9F
        ld  (ix + O_FLAGS2 + 1), a
st_scc_0:  ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  de, st_s2_built
        ld  bc, 4
        ldir
        ld  a, (ix + O_TYPE)
        cp  STRUCT_HEAVYFACTORY
        jp  z, st_scc_heavy
        ; the Yard: no Windtrap
        ld  a, (st_s2_built + 1)
        bit 1, a                ; bit 9
        jr  nz, st_scc_y2
        ld  hl, st_scc_nowind
        call st_scc_linked_s
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, st_scc_y1s
        ld  a, (ix + S_OBJECTTYPE)
        cp  STRUCT_WINDTRAP
        ret z
        cp  STRUCT_PALACE
        jr  c, st_scc_y1s
        cp  STRUCT_OUTPOST + 1
        jr  nc, st_scc_y1s
        cp  STRUCT_IX
        jr  z, st_scc_y1s
        cp  STRUCT_CONSTYARD
        jr  z, st_scc_y1s
        ld  a, STRUCT_WINDTRAP
        jr  st_scc_set
st_scc_y1s:
        ld  a, STRUCT_SLAB4
        jr  st_scc_set
st_scc_y2: ; no Outpost
        ld  a, (st_s2_built + 2)
        bit 2, a
        jr  nz, st_scc_y3
        ld  hl, st_scc_nopost
        call st_scc_linked_s
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        ret nz
        ld  a, (ix + S_OBJECTTYPE)
        ld  hl, st_scc_nopost
        call st_scc_in
        ret nz
        ld  a, STRUCT_OUTPOST
        jr  st_scc_set
st_scc_y3: ; no Heavy Factory (bit 4): none of what needs one, and it is
           ; the Heavy Factory that is put down (st_scc_nolight: 5, 13)
        ld  a, (st_s2_built)
        bit 4, a
        jr  nz, st_scc_y4
        ld  hl, st_scc_nolight
        call st_scc_linked_s
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, st_scc_y4
        ld  a, (ix + S_OBJECTTYPE)
        ld  hl, st_scc_nolight
        call st_scc_in
        jr  nz, st_scc_y4
        ld  (ix + S_OBJECTTYPE), STRUCT_HEAVYFACTORY
st_scc_y4: ; no Starport: no Palace
        ld  a, (st_s2_built + 1)
        bit 3, a                ; bit 11
        ret nz
        ld  hl, st_scc_noport
        call st_scc_linked_s
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        ret nz
        ld  a, (ix + S_OBJECTTYPE)
        cp  STRUCT_PALACE
        ret nz
        ld  a, STRUCT_STARPORT
st_scc_set:
        ld  (ix + S_OBJECTTYPE), a
        ld  (ix + S_OBJECTTYPE + 1), 0
        ret
st_scc_heavy:
        ; no Outpost: no Launcher, Tank, Siege Tank, MCV
        ld  a, (st_s2_built + 2)
        bit 2, a
        jr  nz, st_scc_h2
        ld  hl, st_scc_hnopost
        call st_scc_linked_u
        ld  a, (ix + S_OBJECTTYPE + 1)
        or  a
        jr  nz, st_scc_h2
        ld  a, (ix + S_OBJECTTYPE)
        ld  hl, st_scc_hnopost
        call st_scc_in
        call z, st_scc_trike
st_scc_h2: ; no Hi-Tech: no Deviator, Devastator, Sonic Tank
        ld  a, (st_s2_built)
        bit 5, a
        ret nz
        ld  hl, st_scc_hnohi
        call st_scc_linked_u
        ; the cartridge tests the linked unit's type again here ($00E216),
        ; not the choice
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret z
        call unit_ptr
        inc hl
        inc hl
        ld  a, (hl)
        ld  hl, st_scc_hnohi
        call st_scc_in
        ret nz
st_scc_trike:
        ld  a, (ix + O_HOUSE)
        ld  c, UNIT_TRIKE
        cp  HOUSE_ATREIDES
        jr  z, st_scc_t1
        ld  c, UNIT_RAIDERTRIKE
        cp  HOUSE_ORDOS
        jr  z, st_scc_t1
        ld  c, UNIT_QUAD
st_scc_t1: ld  a, c
        jr  st_scc_set

; HL -> a list ($FF ends): if the linked structure's type is in it and
; the panel's production is running, cancel.  (A Yard.)
st_scc_linked_s:
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret z
        push hl
        call struct_ptr
        jr  st_scc_l1
; the same for the linked unit.
st_scc_linked_u:
        ld  a, (ix + O_LINKED)
        cp  $FF
        ret z
        push hl
        call unit_ptr
st_scc_l1: inc hl
        inc hl
        ld  a, (hl)
        pop hl
        call st_scc_in
        ret nz
        bit 6, (ix + O_FLAGS2 + 1)
        ret z
        call struct_cancel_build
        res 6, (ix + O_FLAGS2 + 1)
        ret
; A in the list at HL? -> Z yes.
st_scc_in: cp  (hl)
        ret z
        inc hl
        inc (hl)
        dec (hl)
        jr  z, st_scc_in_no        ; (a 0 entry is a type: see below)
        bit 7, (hl)
        jr  z, st_scc_in
st_scc_in_no:
        bit 7, (hl)
        jr  z, st_scc_in
        or  1
        ret
st_scc_nowind:     DB 2, 3, 4, 5, 7, 10, 11, 12, 13, 14, 15, 16, 17, 18, $FF
st_scc_nopost:     DB 4, 5, 7, 10, 13, 14, 15, 16, $FF
st_scc_nolight:    DB 5, 13, $FF
st_scc_noport:     DB 2, $FF
st_scc_hnopost:    DB 7, 9, 10, 17, $FF
st_scc_hnohi:      DB 8, 11, 12, $FF

; ================================================= the Starport (S6)

; struct_starport_fill (ui_starport_fill_grid $008F10): the offers - every
; unit type whose stock is not negative, up to ten, with prices rolled
; (cost * (60 + rand(0..50) + rand(0..50)) / 100) when the price timer has
; run out, which then holds them 18000 frames.  For the UI.
struct_starport_fill:
        ld  hl, (st_starport_price_timer)
        ld  a, h
        or  a
        jp  m, st_ssf_roll
        or  l
        jr  z, st_ssf_roll
        xor a
        jr  st_ssf_0
st_ssf_roll:
        ld  a, 1
st_ssf_0:  ld  (st_s2_roll), a
        ld  iy, st_starport_offers
        ld  hl, starport_available
        ld  b, 0                ; the type
        ld  c, 10               ; offers left
st_ssf_1:  ld  a, b
        cp  27
        jr  nc, st_ssf_rest
        inc hl
        bit 7, (hl)
        inc hl
        jr  nz, st_ssf_next
        ; an offer
        ld  (iy + st_SO_TYPE), b
        ld  (iy + st_SO_ORDERED), 0
        dec hl
        dec hl
        ld  a, (hl)
        inc hl
        inc hl
        ld  (iy + st_SO_STOCK), a
        ld  a, (st_s2_roll)
        or  a
        jr  z, st_ssf_2
        push bc
        push hl
        ld  a, b
        call unit_info
        ld  de, UI_buildCredits
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        call st_s2_rand_percent
        ld  (iy + st_SO_PRICE), l
        ld  (iy + st_SO_PRICE + 1), h
        pop hl
        pop bc
st_ssf_2:  ld  de, st_SO_SIZE
        add iy, de
        dec c
        jr  z, st_ssf_done
st_ssf_next:
        inc b
        jr  st_ssf_1
st_ssf_rest:
        ld  (iy + st_SO_TYPE), $FF
        ld  de, st_SO_SIZE
        add iy, de
        dec c
        jr  nz, st_ssf_rest
st_ssf_done:
        ld  a, (st_s2_roll)
        or  a
        ret z
        ld  hl, 18000
        ld  (st_starport_price_timer), hl
        ret

; math_rand_percent ($027330): DE = a number -> HL = DE * (60 +
; rand_between(0, 50) + rand_between(0, 50)) / 100.
st_s2_rand_percent:
        push de
        ld  d, 0
        ld  e, 50
        call rand_between
        ld  c, a
        call rand_between
        add a, c
        add a, 60
        ld  l, a
        ld  h, 0
        pop de
        call mul32              ; DE:HL
        ; / 100 (the product is below 2^24)
        ld  a, e
        ld  (st_s2_tmp), hl
        ld  b, 24
        ld  c, a                ; C:H:L the dividend
        ld  de, 0               ; the remainder
st_srp_1:  add hl, hl
        rl  c
        rl  e
        rl  d
        ld  a, e
        sub 100
        ld  a, d
        sbc a, 0
        jr  c, st_srp_2
        ld  a, e
        sub 100
        ld  e, a
        ld  a, d
        sbc a, 0
        ld  d, a
        inc l
st_srp_2:  djnz st_srp_1
        ret

; struct_starport_tick: A = a house.  The Frigate's countdown, for the
; house loop's tickHouseStarport (game_loop_house $023AFC): with a chain
; of units ordered, starportTimeLeft counts down; at 0 a Frigate is made
; (unit_deliver, type 26) for the Starport the order came from if it is
; still this house's, else the first of its Starports with nothing
; linked; it carries the chain.  The time goes back to the delivery time
; (1 if no Frigate could be made).
struct_starport_tick:
        ld  (st_s2_house), a
        call house_ptr
        push hl
        pop iy
        ld  a, (iy + H_STARPORTLINK)
        and (iy + H_STARPORTLINK + 1)
        inc a
        ret z
        ld  l, (iy + H_STARPORTTIME)
        ld  h, (iy + H_STARPORTTIME + 1)
        dec hl
        bit 7, h
        jr  z, st_sst_1
        ld  hl, 0
st_sst_1:  ld  (iy + H_STARPORTTIME), l
        ld  (iy + H_STARPORTTIME + 1), h
        ld  a, h
        or  l
        ret nz
        push ix
        ; the Starport the order came from
        ld  a, (st_starport_index)
        cp  STRUCT_COUNT
        jr  nc, st_sst_find
        call struct_ptr
        push hl
        pop ix
        bit OF_USED, (ix + O_FLAGS)
        jr  z, st_sst_find
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  nz, st_sst_find
        ld  a, (st_s2_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_sst_find
        call st_sst_deliver
        jr  st_sst_after
st_sst_find:
        ld  a, (st_s2_house)
        ld  b, a
        ld  c, STRUCT_STARPORT
        ld  hl, st_s2_state
        call st_s2_sfind_first
st_sst_f1: jr  z, st_sst_none
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  nz, st_sst_f2
        call st_sst_deliver
        jr  nz, st_sst_after
st_sst_f2: ld  hl, st_s2_state
        call st_s2_sfind_next
        jr  st_sst_f1
st_sst_none:
        xor a
st_sst_after:
        pop ix
        ld  hl, 1
        jr  z, st_sst_2
        ld  a, (st_s2_house)
        call house_info
        ld  de, HI_starportDeliveryTime
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
st_sst_2:  ld  a, (st_s2_house)
        push hl
        call house_ptr
        ld  de, H_STARPORTTIME
        add hl, de
        pop de
        ld  (hl), e
        inc hl
        ld  (hl), d
        ret
; IX = a Starport: a Frigate for it carrying the chain -> NZ if made.
st_sst_deliver:
        ld  a, (ix + O_INDEX)
        ld  h, REF_STRUCT >> 8
        ld  l, a
        ld  a, (st_s2_house)
        ld  b, a
        ld  a, UNIT_FRIGATE
        push ix
        FCALL unit_deliver
        pop ix
        ld  a, h
        or  l
        ret z
        push hl
        ld  a, (st_s2_house)
        call house_ptr
        ld  de, H_STARPORTLINK
        add hl, de
        ld  a, (hl)
        ld  (hl), $FF
        inc hl
        ld  (hl), $FF
        pop hl
        push hl
        inc hl
        inc hl
        inc hl
        ld  (hl), a             ; its linkedID = the chain
        inc hl
        inc hl
        set 0, (hl)             ; flags bit 8 (inTransport)
        pop hl
        or  1
        ret

; ======================================== destruction and removal (S6)

; struct_destroy ($00F59E, PC Structure_Destroy): IX = a structure whose
; health has gone.  Its script restarts with variable 0 = 1 (the dying
; branch), sound $2C; what it was making is destroyed; its house loses
; the credits it can no longer store, and a computer house gets the
; building's price back (half again from campaign 8); a Windtrap counts
; down.
struct_destroy:
        call st_markers_free    ; ($00F5B0)
        ld  (ix + O_SCRIPT + SC_VARS), 1
        ld  (ix + O_SCRIPT + SC_VARS + 1), 0
        res 1, (ix + O_FLAGS)
        res st_SF_REPAIRING_B, (ix + O_FLAGS + 1)
        ld  (ix + O_DELAY), 0
        ld  (ix + O_DELAY + 1), 0
        push ix
        ld  l, (ix + O_TYPE)
        ld  h, 0
        ld  de, O_SCRIPT
        add ix, de
        ld  a, EMC_BUILD
        FCALL emc_start
        pop ix
        ld  a, $2C
        FCALL snd_effect
        ld  a, (ix + O_LINKED)
        ld  (ix + O_LINKED), $FF
        cp  $FF
        jr  z, st_sd_2
        ld  c, a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_CONSTYARD
        ld  a, c
        jr  nz, st_sd_1
        push ix
        call struct_ptr
        push hl
        pop ix
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, st_sd_1d
        FCALL struct_free       ; the building it was making: never
        jr  st_sd_1e            ; placed, so the loop would never free it
st_sd_1d:  call struct_destroy
st_sd_1e:  pop ix
        ld  (ix + O_LINKED), $FF
        jr  st_sd_2
st_sd_1:   ; the chain of units
        cp  $FF
        jr  z, st_sd_2
        push ix
        call unit_ptr
        push hl
        pop ix
        ld  a, (ix + O_LINKED)
        push af
        FCALL unit_remove
        pop af
        pop ix
        jr  st_sd_1
st_sd_2:   ; the credits it stored: credits * creditsStorage / storage,
        ; from the whole 32-bit amounts (S4 fix: the cartridge takes the
        ; low words) - both halved together until they fit a word
        ld  a, (ix + O_HOUSE)
        call house_ptr
        push hl
        pop iy
        push ix
        ld  de, H_CREDITS
        add hl, de
        ld  de, st_sd_cr        ; credits (4), then storage (4)
        ld  bc, 8
        ldir
st_sd_sh:  ld  hl, (st_sd_cr + 2)
        ld  de, (st_sd_st + 2)
        ld  a, h
        or  l
        or  d
        or  e
        jr  z, st_sd_fit
        ld  ix, st_sd_cr
        call st_sd_half
        ld  ix, st_sd_st
        call st_sd_half
        jr  st_sd_sh
st_sd_fit: pop ix
        ld  hl, (st_sd_st)
        ld  de, (st_sd_cr)
        call div_shl8
        ex  de, hl
        call st_s2_info
        ld  bc, SI_creditsStorage
        add hl, bc
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call mul_shr8
        ex  de, hl              ; DE = the loss
        call st_s2_cr_lt
        jr  nc, st_sd_3
        ld  e, (iy + H_CREDITS)
        ld  d, (iy + H_CREDITS + 1)
st_sd_3:   call st_s2_cr_sub
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_sd_4
        call st_s2_info
        ld  de, SI_buildCredits
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  a, (campaign_id)
        cp  8
        jr  c, st_sd_3a
        ld  h, d
        ld  l, e
        srl h
        rr  l
        add hl, de
        ex  de, hl
st_sd_3a:  call st_s2_cr_add
st_sd_4:   ld  a, (ix + O_TYPE)
        cp  STRUCT_WINDTRAP
        ret nz
        ld  l, (iy + H_WINDTRAPS)
        ld  h, (iy + H_WINDTRAPS + 1)
        dec hl
        ld  (iy + H_WINDTRAPS), l
        ld  (iy + H_WINDTRAPS + 1), h
        ret
; a 32-bit value at IX halved.
st_sd_half:
        srl (ix + 3)
        rr  (ix + 2)
        rr  (ix + 1)
        rr  (ix + 0)
        ret
st_sd_cr:  DS 4                 ; struct_destroy: the house's credits
st_sd_st:  DS 4                 ;   and storage, halved until words

; struct_markers_free ($009A08): IX = a structure: no marker flags and
; no marker sprite (struct/world.inc st_markers).  Keeps BC, DE.
st_markers_free:
        push de
        ld  e, (ix + O_INDEX)
        ld  d, 0
        ld  hl, st_markers
        add hl, de
        ld  (hl), 0
        pop de
        ret

; struct_remove ($00F71A): IX = a destroyed structure: off the map (its
; squares lose the structure bit and index), the rubble animation, into
; the house's rebuild list, freed, every reference to it dropped, the
; house's structuresBuilt recounted, and a Windtrap's power / a Refinery's
; or Silo's storage recounted.
struct_remove:
        call st_markers_free    ; ($00F72E)
        call st_s2_square
        ld  (st_s2_sq), hl
        call st_s2_layout
        ld  (st_s2_layout_n), a
        call st_s2_layout_tiles
st_sr_1:   push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_s2_sq)
        add hl, de
        ld  a, h
        and $0F
        push af
        or  MAP_FLAGS >> 8
        ld  h, a
        res MF_STRUCT, (hl)
        pop af
        or  MAP_INDEX >> 8
        ld  h, a
        ld  (hl), 0
        pop hl
        pop bc
        inc hl
        inc hl
        djnz st_sr_1
        ; the house marker's orb (struct_erase_house_marker $00DE04): its
        ; overlay off the marker square, or the orb turns on over the ruin
        bit st_S2_MARKED, (ix + O_FLAGS2)
        jr  z, st_sr_1b
        res st_S2_MARKED, (ix + O_FLAGS2)
        ld  a, (st_s2_layout_n)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_struct_pos_offsets
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_s2_sq)
        add hl, de
        ld  a, h
        and $0F
        or  MAP_HIGH >> 8
        ld  h, a
        ld  a, (hl)
        and 1
        ld  (hl), a
st_sr_1b:
        ; the rubble ($06BBF2 by layout)
        ld  a, (st_s2_layout_n)
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_struct_anim_numbers
        add hl, de
        ld  a, (hl)
        ld  hl, st_s2_layout_n
        ld  c, (hl)
        ld  hl, (st_s2_sq)
        FCALL st_map_anim_start_l
        ; the first free rebuild entry
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_REBUILD
        add hl, de
        ld  b, 5
st_sr_2:   ld  a, (hl)
        inc hl
        or  (hl)
        jr  z, st_sr_3
        inc hl
        inc hl
        inc hl
        djnz st_sr_2
        jr  st_sr_4
st_sr_3:   dec hl
        ld  a, (ix + O_TYPE)
        ld  (hl), a
        inc hl
        ld  (hl), 0
        inc hl
        ld  de, (st_s2_sq)
        ld  (hl), e
        inc hl
        ld  (hl), d
st_sr_4:   FCALL struct_free
        call st_struct_free_refs
        ld  a, (ix + O_HOUSE)
        call house_owned_struct_types
        ld  a, (ix + O_TYPE)
        cp  STRUCT_WINDTRAP
        jr  nz, st_sr_5
        ld  a, (ix + O_HOUSE)
        FCALL house_calc_power
        ret
st_sr_5:   cp  STRUCT_REFINERY
        jr  z, st_sr_6
        cp  STRUCT_SILO
        ret nz
st_sr_6:   ; house_update_credits_storage ($0235DE): Refineries and Silos
        ; by the per-type counts
        ld  b, (ix + O_HOUSE)
        ld  a, STRUCT_REFINERY
        call st_s2_stc_addr
        ld  a, (hl)
        push af
        ld  a, STRUCT_SILO
        call st_s2_stc_addr
        ld  c, (hl)
        ld  a, STRUCT_SILO
        call struct_info
        ld  de, SI_creditsStorage
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  l, c
        ld  h, 0
        call mul16
        push hl
        ld  a, STRUCT_REFINERY
        call struct_info
        ld  de, SI_creditsStorage
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop bc
        pop af
        push bc
        ld  l, a
        ld  h, 0
        call mul16
        pop bc
        add hl, bc
        push hl
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_STORAGE
        add hl, de
        pop de
        ld  (hl), e
        inc hl
        ld  (hl), d
        inc hl
        ld  (hl), 0
        inc hl
        ld  (hl), 0
        ret

; struct_free_refs ($010CDC): IX = a structure going: its claim broken,
; and every unit's claim, move and attack target naming it, and every
; team's target, cleared.
st_struct_free_refs:
        ld  a, (ix + O_INDEX)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        ld  (st_s2_ref), hl
        FCALL obj_var4_clear
        push ix
        ld  a, (unit_find_count)
        or  a
        jr  z, st_sfr_teams
        ld  b, a
        ld  hl, unit_find
st_sfr_1:  push bc
        push hl
        ld  a, (hl)
        call unit_ptr
        push hl
        pop ix
        ld  hl, (st_s2_ref)
        ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        cp  l
        jr  nz, st_sfr_2
        ld  a, (ix + O_SCRIPT + SC_VARS + 9)
        cp  h
        jr  nz, st_sfr_2
        FCALL obj_var4_clear
        ld  hl, (st_s2_ref)
st_sfr_2:  ld  a, (ix + U_TARGETMOVE)
        cp  l
        jr  nz, st_sfr_3
        ld  a, (ix + U_TARGETMOVE + 1)
        cp  h
        jr  nz, st_sfr_3
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
st_sfr_3:  ld  a, (ix + U_TARGETATTACK)
        cp  l
        jr  nz, st_sfr_4
        ld  a, (ix + U_TARGETATTACK + 1)
        cp  h
        jr  nz, st_sfr_4
        ld  (ix + U_TARGETATTACK), 0
        ld  (ix + U_TARGETATTACK + 1), 0
st_sfr_4:  pop hl
        inc hl
        pop bc
        djnz st_sfr_1
st_sfr_teams:
        ld  b, 0
st_sfr_t1: push bc
        ld  a, b
        call team_ptr
        push hl
        pop ix
        ld  a, (ix + T_USED)
        or  (ix + T_USED + 1)
        jr  z, st_sfr_t2
        ld  hl, (st_s2_ref)
        ld  a, (ix + T_TARGET)
        cp  l
        jr  nz, st_sfr_t2
        ld  a, (ix + T_TARGET + 1)
        cp  h
        jr  nz, st_sfr_t2
        ld  (ix + T_TARGET), 0
        ld  (ix + T_TARGET + 1), 0
st_sfr_t2: pop bc
        inc b
        ld  a, b
        cp  TEAM_COUNT
        jr  c, st_sfr_t1
        pop ix
        ret

; house_owned_struct_types ($00FA28): A = a house: its structuresBuilt
; rewritten from the structures it has on the map, a Heavy Factory
; counting as a Light Factory too.  Port fix (S6): per house, not per
; side.
house_owned_struct_types:
        ld  (st_s2_house), a
        ld  hl, 0
        ld  (st_s2_mask), hl
        ld  (st_s2_mask + 2), hl
        push ix
        ld  a, (struct_find_count)
        or  a
        jr  z, st_hot_3
        ld  b, a
        ld  hl, struct_find
st_hot_1:  push bc
        push hl
        ld  a, (hl)
        call struct_ptr
        push hl
        pop ix
        ld  a, (st_s2_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_hot_2
        bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  nz, st_hot_2
        ld  a, (ix + O_TYPE)
        call st_s2_mset
st_hot_2:  pop hl
        inc hl
        pop bc
        djnz st_hot_1
st_hot_3:  pop ix
        ld  a, (st_s2_mask)
        bit 4, a
        jr  z, st_hot_4
        set 3, a
        ld  (st_s2_mask), a
st_hot_4:  ld  a, (st_s2_house)
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ex  de, hl
        ld  hl, st_s2_mask
        ld  bc, 4
        ldir
        ret

; ================================================ BUILD.EMC routines

; BUILD 2 check.link ($00C65E): the unit linked through variable 4 must
; point back; if not both links are broken.  -> the reference, or 0.
ef_b_check_link:
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_INDEX)
        ld  c, a
        ld  b, REF_STRUCT >> 8
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        push hl
        call st_s2_ref_unit        ; HL = the unit or Z
        jr  z, st_ecl_break0
        push hl
        pop iy
        ld  a, (iy + O_SCRIPT + SC_VARS + 8)
        cp  c
        jr  nz, st_ecl_break
        ld  a, (iy + O_SCRIPT + SC_VARS + 9)
        cp  b
        jr  nz, st_ecl_break
        pop hl
        ret
st_ecl_break:
        push ix
        push iy
        pop ix
        FCALL obj_var4_clear
        pop ix
st_ecl_break0:
        FCALL obj_var4_clear
        pop hl
        ld  hl, 0
        ret

; BUILD 3 send.for ($00C6C0): when the structure is ready (state 2) with
; a unit, a unit of type n of its house (a Carryall; made if there is
; none, off the map) is claimed to fetch it - but not for the player's
; Harvester that has nowhere to go back to and has room outside.
; -> the Carryall's reference, or 0.
ef_b_send_for:
        xor a
        call emc_arg
        ld  (st_s2_u), hl
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + S_STATE)
        cp  2
        jp  nz, st_esf_no
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_esf_no
        xor a
        call struct_find_free_square
        ld  (st_s2_sq), hl
        ld  a, (ix + O_LINKED)
        call unit_ptr
        push hl
        pop iy
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_esf_1
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, st_esf_1
        ld  a, (iy + U_PRELAST_Y)
        or  (iy + U_PRELAST_Y + 1)
        or  (iy + U_PRELAST_X)
        or  (iy + U_PRELAST_X + 1)
        jr  nz, st_esf_1
        ld  hl, (st_s2_sq)
        ld  a, h
        or  l
        jr  nz, st_esf_no
st_esf_1:  ; unit_summon_idle(n, house, the structure, create if no room)
        ld  hl, (st_s2_sq)
        ld  a, h
        or  l
        ld  a, 0
        jr  nz, st_esf_2
        inc a
st_esf_2:  ld  (st_s2_create), a
        ld  a, (ix + O_INDEX)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        ld  (st_s2_ref), hl
        ld  a, (st_s2_u)
        ld  c, a
        ld  b, (ix + O_HOUSE)
        call st_s2_summon
        jr  z, st_esf_no
        ; the structure claims it
        push hl
        pop iy
        ld  a, (iy + O_INDEX)
        ld  l, a
        ld  h, REF_UNIT >> 8
        push hl
        FCALL obj_var4_set
        pop hl
        ld  a, (ix + O_FLAGS2 + 1)
        and $1F
        ld  (ix + O_FLAGS2 + 1), a
        ret
st_esf_no: ld  hl, 0
        ret

; unit_summon_idle ($04875A): C = a unit type, B = a house, s2_ref = what
; to fetch, s2_create: the first unit of them carrying nothing with
; nowhere to go - or, with s2_create and type 0, a new Carryall made off
; the map - is sent for it (+$5C) and claims it.  -> HL = the unit, Z
; none.  Keeps IX.
st_s2_summon:
        push ix
        call st_s2_ufind_idle
        jr  nz, st_ssu_have
        ld  a, (st_s2_create)
        or  a
        jr  z, st_ssu_none
        ld  a, c
        or  a
        jr  nz, st_ssu_none
        ld  hl, validate_strict
        inc (hl)
        ld  a, $FF
        ld  (arg_pos), a
        ld  (arg_pos + 1), a
        ld  (arg_pos + 2), a
        ld  (arg_pos + 3), a
        ld  c, b
        ld  b, UNIT_CARRYALL
        ld  d, $60
        ld  a, $FF
        FCALL unit_spawn
        ld  a, (validate_strict)
        dec a
        ld  (validate_strict), a
        ld  a, h
        or  l
        jr  z, st_ssu_none
        push hl
        ld  de, O_FLAGS
        add hl, de
        set 1, (hl)
        pop hl
st_ssu_have:
        push hl
        pop ix
        ld  hl, (st_s2_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        FCALL obj_var4_set
        push ix
        pop hl
        pop ix
        or  1
        ret
st_ssu_none:
        pop ix
        ld  hl, 0
        xor a
        ret

; BUILD 6 unclaim ($00CD6E): a unit reference: its link broken and its
; +$5C cleared.  Answers 0.
ef_b_unclaim:
        xor a
        call emc_arg
        call ref_is_valid
        or  a
        jr  z, st_ebu_0
        call st_s2_ref_unit
        jr  z, st_ebu_0
        push hl
        pop ix
        FCALL obj_var4_clear
        ld  (ix + U_TARGETMOVE), 0
        ld  (ix + U_TARGETMOVE + 1), 0
st_ebu_0:  ld  hl, 0
        ret

; BUILD 7 release ($00C818): the docked unit comes out.  A Harvester
; leaving a Repair Facility gets its sprite back; a flyer is put down at
; the structure's position; anything else on a free square next to it
; (a Harvester on the side nearest spice), facing away.  The link is
; broken, the structure idle when nothing more is linked; the player
; hears voice $1E + house ($44 + house for a Harvester; not from a Repair
; Facility).  -> 1 if it came out.
ef_b_release:
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_erl_no
        call unit_ptr
        push hl
        pop iy
        bit OF_USED, (iy + O_FLAGS)
        jr  nz, st_erl_1
        ld  (ix + O_LINKED), $FF
        FCALL obj_var4_clear
        ld  a, (ix + O_FLAGS2 + 1)
        and $9F
        ld  (ix + O_FLAGS2 + 1), a
        jp  st_erl_no
st_erl_1:  ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, st_erl_2
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REPAIR
        jr  nz, st_erl_2
        ld  a, (ix + S_ROTSPRITEDIFF)
        ld  (iy + U_TARGETATTACK), a
        ld  a, (ix + S_ROTSPRITEDIFF + 1)
        ld  (iy + U_TARGETATTACK + 1), a
st_erl_2:  ld  a, (iy + O_TYPE)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        cp  4
        jr  nz, st_erl_ground
        ; a flyer: at the structure's own position
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, st_s2_pos
        ld  bc, 4
        ldir
        call st_s2_unit_place
        jr  z, st_erl_ground
        call st_erl_unlink
        ld  hl, 1
        ret
st_erl_ground:
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        ld  a, 0
        jr  nz, st_erl_3
        inc a
st_erl_3:  call struct_find_free_square
        ld  a, h
        or  l
        jp  z, st_erl_no
        ld  a, (ix + O_SEEN)
        or  (iy + O_SEEN)
        ld  (iy + O_SEEN), a
        ld  de, st_s2_pos
        call square_centre
        call st_s2_unit_place
        jp  z, st_erl_no
        ; facing away from the structure
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        push iy
        pop de
        push hl
        ld  hl, O_POS_Y
        add hl, de
        ex  de, hl
        pop hl
        call tile_direction
        and $E0
        push ix
        push iy
        pop ix
        push af
        ld  c, 0
        ld  b, 1
        FCALL unit_set_facing
        ld  a, (ix + U_OR0_CURRENT)
        ld  c, 1
        ld  b, 1
        FCALL unit_set_facing
        pop af
        pop ix
        call st_erl_unlink
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_erl_ok
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REPAIR
        jr  z, st_erl_ok
        ld  a, (player_house)
        ld  c, $1E
        ld  b, a
        ld  a, (iy + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, st_erl_4
        ld  c, $44
st_erl_4:  ld  a, b
        add a, c
        FCALL snd_voice
st_erl_ok: ld  hl, 1
        ret
st_erl_no: ld  hl, 0
        ret
; the structure takes the next of its chain; idle when none; the claim
; and flags2 bits 13-14 go.
st_erl_unlink:
        ld  a, (iy + O_LINKED)
        ld  (ix + O_LINKED), a
        ld  (iy + O_LINKED), $FF
        cp  $FF
        jr  nz, st_ebu_1
        ld  (ix + S_STATE), 0
        ld  (ix + S_STATE + 1), 0
st_ebu_1:  FCALL obj_var4_clear
        ld  a, (ix + O_FLAGS2 + 1)
        and $9F
        ld  (ix + O_FLAGS2 + 1), a
        ret

; unit_place ($048534): IY = a unit, s2_pos = the position (the square is
; taken, centred): on the map at it, movement cleared, a home if it has
; none; if it cannot stand there it stays hidden (Z).  Otherwise its
; destination and targets are cleared (a Harvester keeps +$5A), it is
; seen if the square is, it takes its type's default order, goes on the
; map; a Starport cargo is counted off.  -> NZ placed.  Keeps IX, IY.
st_s2_unit_place:
        push ix
        push iy
        pop ix
        res OF_NOTONMAP, (ix + O_FLAGS)
        ld  a, (st_s2_pos + 1)
        ld  (ix + O_POS_Y + 1), a
        ld  (ix + O_POS_Y), $80
        ld  a, (st_s2_pos + 3)
        ld  (ix + O_POS_X + 1), a
        ld  (ix + O_POS_X), $80
        xor a
        ld  (ix + U_STEP_X), a
        ld  (ix + U_STEP_X + 1), a
        ld  (ix + U_STEP_Y), a
        ld  (ix + U_STEP_Y + 1), a
        ld  a, (ix + U_ORIGIN)
        or  (ix + U_ORIGIN + 1)
        jr  nz, st_sup_1
        FCALL unit_choose_home
st_sup_1:  ld  (ix + O_SCRIPT + SC_VARS + 8), 0
        ld  (ix + O_SCRIPT + SC_VARS + 9), 0
        FCALL unit_blocked_here
        or  a
        jr  z, st_sup_2
        set OF_NOTONMAP, (ix + O_FLAGS)
        push ix
        pop iy
        pop ix
        xor a
        ret
st_sup_2:  xor a
        ld  (ix + U_DEST_Y), a
        ld  (ix + U_DEST_Y + 1), a
        ld  (ix + U_DEST_X), a
        ld  (ix + U_DEST_X + 1), a
        ld  (ix + U_TARGETMOVE), a
        ld  (ix + U_TARGETMOVE + 1), a
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, st_sup_3
        ld  (ix + U_TARGETATTACK), 0
        ld  (ix + U_TARGETATTACK + 1), 0
st_sup_3:  push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        call pos_square
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNVEILED, (hl)
        jr  z, st_sup_4
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, st_sup_3a
        ld  a, (ix + O_HOUSE)
        call st_s2_bit_of
st_sup_3a: ld  (ix + O_SEEN), a
        ld  a, (player_house)
        FCALL unit_seen_by_house
st_sup_4:  ; the default order: +$28 for the player's own (not a Harvester
        ; or Saboteur), +$4A otherwise
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  de, UI_actionAI
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_sup_5
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  z, st_sup_5
        cp  UNIT_SABOTEUR
        jr  z, st_sup_5
        ld  de, UI_actionPlayer
st_sup_5:  add hl, de
        ld  a, (hl)
        FCALL unit_give_order
        ld  (ix + U_SPRITEOFS), 0
        ld  a, 1
        FCALL unit_update_map
        bit 1, (ix + O_FLAGS2 + 1)
        jr  z, st_sup_6
        res 1, (ix + O_FLAGS2 + 1)
        ld  hl, (st_starport_cargo_pending)
        ld  a, h
        or  l
        jr  z, st_sup_6
        dec hl
        ld  (st_starport_cargo_pending), hl
st_sup_6:  push ix
        pop iy
        pop ix
        or  1
        ret

; BUILD 22 explode ($00D1EA): explosions (type 6) at random points of each
; square, twice over with growing strength; a Starport's cargo on its way
; is lost and a Frigate that has unloaded (flags2 bit 9, set by HOUSE at
; the unload, as the cartridge's $00D3A6 tests) removed; sound $33.
; Answers 0.
ef_b_explode:
        ld  de, -O_SCRIPT
        add ix, de
        call st_markers_free    ; ($00D236)
        ld  hl, 0
        ld  (st_s2_acc), hl
        call st_ebx_pass
        ld  a, 60               ; view_shake_start(60) ($00D338)
        FCALL view_shake_start
        ; the Starport's cargo
        ld  a, (ix + O_TYPE)
        cp  STRUCT_STARPORT
        jr  nz, st_ebx_2
        ld  a, (ix + O_LINKED)
        ld  (ix + O_LINKED), $FF
st_ebx_1:  cp  $FF
        jr  z, st_ebx_1a
        push ix
        call unit_ptr
        push hl
        pop ix
        ld  a, (ix + O_LINKED)
        ld  (ix + O_LINKED), $FF
        push af
        FCALL unit_remove
        pop af
        pop ix
        jr  st_ebx_1
st_ebx_1a: ld  hl, 0
        ld  (st_starport_cargo_pending), hl
        ld  a, (frigate_coming)
        cp  UNIT_COUNT
        jr  nc, st_ebx_2
        push ix
        call unit_ptr
        push hl
        pop ix
        bit 1, (ix + O_FLAGS2 + 1)
        jr  z, st_ebx_1b
        FCALL unit_remove
st_ebx_1b: pop ix
st_ebx_2:  call st_ebx_pass
        ld  a, $33
        FCALL snd_effect
        ld  hl, 0
        ret
st_ebx_pass:
        call st_s2_square
        ld  (st_s2_sq), hl
        call st_s2_layout
        call st_s2_layout_tiles
st_ebx_p1: push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_s2_sq)
        add hl, de
        ld  de, arg_pos
        call square_centre
        ; y += +-rand(3,10)*16, x the same
        call st_ebx_off
        ld  hl, arg_pos + 2
        call st_ebx_add
        call st_ebx_off
        call st_s2_neg_de
        ld  hl, arg_pos
        call st_ebx_add
        ld  a, 6
        ld  hl, (st_s2_acc)
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
        ld  d, 10
        ld  e, 25
        call rand_between
        ld  e, a
        ld  d, 0
        ld  hl, (st_s2_acc)
        add hl, de
        ld  (st_s2_acc), hl
        pop hl
        pop bc
        inc hl
        inc hl
        djnz st_ebx_p1
        ret
; -> DE = +-rand(3,10) * 16
st_ebx_off:
        ld  d, 3
        ld  e, 10
        call rand_between
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        call random
        rra
        ex  de, hl
        ret nc
        jp  st_s2_neg_de
; (HL) word += DE
st_ebx_add:
        ld  a, (hl)
        add a, e
        ld  (hl), a
        inc hl
        ld  a, (hl)
        adc a, d
        ld  (hl), a
        ret

; BUILD 23 destroy ($00D4C8): struct_remove, then square by square, with
; the type's +$0E chance in 256, a Soldier of its house with random
; health: the computer's attack, the player's move to a random point
; nearby.  Answers 0.
ef_b_destroy:
        ld  de, -O_SCRIPT
        add ix, de
        call st_s2_square
        ld  (st_s2_sq2), hl
        call struct_remove
        call st_s2_layout
        call st_s2_layout_tiles
st_ebd_1:  push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_s2_sq2)
        add hl, de
        push hl
        call random
        ld  c, a
        call st_s2_info
        ld  de, SI_spawnChance
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        ld  b, 0
        ; random < chance?
        or  a
        sbc hl, bc
        pop hl
        jp  z, st_ebd_next
        jp  c, st_ebd_next
        ld  de, arg_pos
        call square_centre
        push ix
        call random             ; the facing
        ld  d, a
        ld  b, UNIT_SOLDIER
        ld  c, (ix + O_HOUSE)
        ld  a, $FF
        FCALL unit_spawn
        pop ix
        ld  a, h
        or  l
        jr  z, st_ebd_next
        push ix
        push hl
        pop ix
        ; health: (soldier hp * (random | 3) + $50) >> 8
        ld  a, UNIT_SOLDIER
        call unit_info
        ld  de, UI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call random
        or  3
        ld  e, a
        ld  d, 0
        call mul_shr8
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  z, st_ebd_2
        ld  a, ORDER_ATTACK
        FCALL unit_give_order
        jr  st_ebd_3
st_ebd_2:  ld  a, ORDER_MOVE
        FCALL unit_give_order
        ; a random point within $20 twice, its square as a place
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, st_s2_pos
        ld  bc, 4
        ldir
        call st_s2_move_by_random
        ld  a, (st_s2_pos + 3)
        push af
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, st_s2_pos
        ld  bc, 4
        ldir
        call st_s2_move_by_random
        ld  hl, st_s2_pos
        call pos_square         ; the row from the second
        pop af
        ld  c, a
        ld  a, l
        and $C0
        or  c
        ld  l, a
        call ref_make_square
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
st_ebd_3:  pop ix
st_ebd_next:
        pop hl
        pop bc
        inc hl
        inc hl
        dec b
        jp  nz, st_ebd_1
        ld  hl, 0
        ret

; tile_move_by_random ($011688) with a distance of $20, centred: s2_pos
; moved a random fraction of $20 in a random direction; off the map
; (outside squares 1-62) it stays.
st_s2_move_by_random:
        call random
st_s2mr_1: cp  $20
        jr  c, st_s2mr_2
        srl a
        jr  st_s2mr_1
st_s2mr_2: ld  c, a                ; the distance
        call random
        ld  e, a
        ld  d, 0
        push de
        ld  hl, tbl_sin
        add hl, de
        ld  a, (hl)
        call st_s2mr_scale         ; DE = (sin * d >> 3) & $FFF0
        ld  hl, (st_s2_pos + 2)
        add hl, de
        ld  (st_s2_tmp), hl        ; x
        pop de
        ld  hl, tbl_cos
        add hl, de
        ld  a, (hl)
        neg
        call st_s2mr_scale
        ld  hl, (st_s2_pos)
        add hl, de              ; y
        ; both within $100 - $3EFF
        ld  a, h
        or  a
        ret z
        cp  $3F
        ret nc
        ld  de, (st_s2_tmp)
        ld  a, d
        or  a
        ret z
        cp  $3F
        ret nc
        ld  a, $80
        ld  (st_s2_pos), a
        ld  a, h
        ld  (st_s2_pos + 1), a
        ld  a, $80
        ld  (st_s2_pos + 2), a
        ld  a, d
        ld  (st_s2_pos + 3), a
        ret
; A = a signed byte, C = the distance -> DE = (A * C >> 3) & $FFF0.
st_s2mr_scale:
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        ld  hl, 0
        ld  b, c
        inc b
        dec b
        jr  z, st_s2ms_2
st_s2ms_1: add hl, de
        djnz st_s2ms_1
st_s2ms_2: sra h
        rr  l
        sra h
        rr  l
        sra h
        rr  l
        ld  a, l
        and $F0
        ld  e, a
        ld  d, h
        ret

; ================================================ spice (S5, S8)

; map_change_spice ($01A518): HL = a square, A = the sign of the amount
; (0 nothing).  Adding: sand becomes spice, spice thick spice; taking:
; thick becomes spice, spice sand.  The new icon goes in the square and
; in mapGround.  Adding re-picks the edges of it and its neighbours;
; taking thick spice leaves $BF on the square and re-picks only the
; neighbours'.
map_change_spice:
        or  a
        ret z
        ld  (st_s2_sign), a
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_s2_sq), hl
        call map_landscape
        ld  c, a
        or  a
        jr  z, st_mcs_sand
        cp  LST_SPICE
        jr  z, st_mcs_go
        cp  LST_THICKSPICE
        ret nz
        ld  a, (st_s2_sign)
        or  a
        ret p                   ; thick, adding: nothing
        jr  st_mcs_go
st_mcs_sand:
        ld  a, (st_s2_sign)
        or  a
        ret m                   ; sand, taking: nothing
st_mcs_go: ld  a, (st_s2_sign)
        or  a
        jp  m, st_mcs_take
        ld  a, c
        cp  LST_SPICE
        ld  de, $C0             ; spice -> thick
        jr  z, st_mcs_1
        ld  de, $B0             ; sand -> spice
        jr  st_mcs_1
st_mcs_take:
        ld  a, c
        cp  LST_THICKSPICE
        ld  de, $B0
        jr  z, st_mcs_1
        ld  de, $7F
st_mcs_1:  ld  hl, (st_s2_sq)
        call st_s2_set_ground
        call st_s2_ground_saved
        ld  a, (st_s2_sign)
        or  a
        jp  m, st_mcs_t2
        ld  hl, (st_s2_sq)
        call map_fix_spice_edges
        call st_mcs_neigh
        ret
st_mcs_t2: ; taken: thick taken down to spice shows $BF
        ld  a, c
        cp  LST_THICKSPICE
        jr  nz, st_mcs_t3
        ld  hl, (st_s2_sq)
        ld  de, $BF
        call st_s2_set_ground
st_mcs_t3: ; (the cartridge leaves mapGround with the $B0 it wrote)
st_mcs_neigh:
        ld  hl, (st_s2_sq)
        inc hl
        call map_fix_spice_edges
        ld  hl, (st_s2_sq)
        dec hl
        call map_fix_spice_edges
        ld  hl, (st_s2_sq)
        ld  de, -64
        add hl, de
        call map_fix_spice_edges
        ld  hl, (st_s2_sq)
        ld  de, 64
        add hl, de
        ; fall through

; map_fix_spice_edges ($01A6EE): HL = a square: spice or thick spice
; takes the icon for which of its N E S W neighbours are spice too (any
; spice for spice, thick only for thick), in the square and in mapGround.
map_fix_spice_edges:
        ld  a, h
        and $0F
        ld  h, a
        push hl
        call map_landscape
        pop hl
        cp  LST_SPICE
        jr  z, st_mfs_1
        cp  LST_THICKSPICE
        ret nz
st_mfs_1:  ld  (st_s2_lt), a
        ld  c, 0                ; the mask
        ld  b, 1
        ld  de, -64
        call st_mfs_side
        ld  b, 2
        ld  de, 1
        call st_mfs_side
        ld  b, 4
        ld  de, 64
        call st_mfs_side
        ld  b, 8
        ld  de, -1
        call st_mfs_side
        ld  a, (st_s2_lt)
        cp  LST_SPICE
        ld  a, $B0
        jr  z, st_mfs_2
        ld  a, $C0
st_mfs_2:  add a, c
        ld  e, a
        ld  d, 0
        push hl
        call st_s2_set_ground
        call st_s2_ground_saved
        pop hl
        ret
st_mfs_side:
        push hl
        push bc
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        call map_landscape
        pop bc
        pop hl
        ld  e, a
        ld  a, (st_s2_lt)
        cp  LST_SPICE
        ld  a, e
        jr  nz, st_mfs_s1
        cp  LST_SPICE
        jr  z, st_mfs_s2
st_mfs_s1: cp  LST_THICKSPICE
        ret nz
st_mfs_s2: ld  a, c
        or  b
        ld  c, a
        ret

; HL = a square, E = the low byte of its ground: into mapGround.  Keeps
; HL, DE, BC.
st_s2_ground_saved:
        push hl
        ld  a, PG_MAPGROUND
        call map_w1
        ld  a, h
        and $0F
        or  $40
        ld  h, a
        ld  (hl), e
        ld  a, PG_UNITS
        call map_w1
        pop hl
        ret

; map_find_spice ($01A146): HL = the centre square, A = the radius -> HL
; = a square found, or 0 (Z).  Rings outward within the playable area;
; the first square taken wins: nothing on it and spice not showing $BF
; (then thick spice among the 24 round it that is not $CF is preferred)
; or thick spice not showing $CF.  (The per-unit search record does
; nothing: dropped, S5.)
map_find_spice:
        ld  (st_s2_radius), a
        ld  a, l
        and $3F
        ld  (st_s2_cx), a
        add hl, hl
        add hl, hl
        ld  a, h
        and $3F
        ld  (st_s2_cy), a
        ; the limits
        ld  a, (map_scale)
        add a, a
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_playable_area
        add hl, de
        ld  a, (hl)
        ld  (st_s2_x0l), a         ; left
        inc hl
        inc hl
        ld  a, (hl)
        ld  (st_s2_y0l), a         ; top
        inc hl
        inc hl
        ld  a, (st_s2_x0l)
        add a, (hl)
        dec a
        ld  (st_s2_x1l), a         ; right
        inc hl
        inc hl
        ld  a, (st_s2_y0l)
        add a, (hl)
        dec a
        ld  (st_s2_y1l), a         ; bottom
        xor a
        ld  (st_s2_ring), a
st_mfsp_ring:
        ld  a, (st_s2_ring)
        ld  hl, st_s2_radius
        cp  (hl)
        jp  nc, st_mfsp_none
        ld  c, a                ; d
        ; x0 = max(x - d, left), x1 = min(x + d, right), the same for y
        ld  a, (st_s2_cx)
        sub c
        ld  hl, st_s2_x0l
        call st_mfsp_max
        ld  (st_s2_x0), a
        ld  a, (st_s2_cx)
        add a, c
        ld  hl, st_s2_x1l
        call st_mfsp_min
        ld  (st_s2_x1), a
        ld  a, (st_s2_cy)
        sub c
        ld  hl, st_s2_y0l
        call st_mfsp_max
        ld  (st_s2_y0), a
        ld  a, (st_s2_cy)
        add a, c
        ld  hl, st_s2_y1l
        call st_mfsp_min
        ld  (st_s2_y1), a
        ld  a, (st_s2_y0)
        ld  (st_s2_y), a
st_mfsp_row:
        ld  a, (st_s2_y)
        ld  hl, st_s2_y1
        cp  (hl)
        jr  z, st_mfsp_r0
        jp  p, st_mfsp_next        ; (signed: a row above the map is < 0)
st_mfsp_r0:
        ld  a, (st_s2_y)
        ld  hl, st_s2_y0
        cp  (hl)
        jr  z, st_mfsp_whole
        ld  hl, st_s2_y1
        cp  (hl)
        jr  z, st_mfsp_whole
        ; the two ends only
        ld  a, (st_s2_x0)
        call st_mfsp_try
        ret nz
        ld  a, (st_s2_x1)
        call st_mfsp_try
        ret nz
        jr  st_mfsp_rnext
st_mfsp_whole:
        ld  a, (st_s2_x0)
        ld  (st_s2_x), a
st_mfsp_w1:
        ld  a, (st_s2_x)
        ld  hl, st_s2_x1
        cp  (hl)
        jr  z, st_mfsp_w2
        jp  p, st_mfsp_rnext
st_mfsp_w2:
        call st_mfsp_try
        ret nz
        ld  hl, st_s2_x
        inc (hl)
        jr  st_mfsp_w1
st_mfsp_rnext:
        ld  hl, st_s2_y
        inc (hl)
        jr  st_mfsp_row
st_mfsp_next:
        ld  hl, st_s2_ring
        inc (hl)
        jp  st_mfsp_ring
st_mfsp_none:
        ld  hl, 0
        xor a
        ret
; A = the larger of A and (HL), signed
st_mfsp_max:
        push bc
        ld  b, (hl)
        cp  b
        jp  pe, st_mfm_v
        jp  p, st_mfm_1
        ld  a, b
        jr  st_mfm_1
st_mfm_v:  jp  m, st_mfm_1
        ld  a, b
st_mfm_1:  pop bc
        ret
; A = the smaller of A and (HL), signed
st_mfsp_min:
        push bc
        ld  b, (hl)
        cp  b
        jp  pe, st_mfn_v
        jp  m, st_mfn_1
        ld  a, b
        jr  st_mfn_1
st_mfn_v:  jp  p, st_mfn_1
        ld  a, b
st_mfn_1:  pop bc
        ret
; A = a column of row s2_y: is the square spice to go for?  -> NZ and HL
; = the square taken.
st_mfsp_try:
        ld  e, a
        ld  a, (st_s2_y)
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, e
        and $3F
        or  l
        ld  l, a
        ld  a, h
        and $0F
        ld  h, a
        call st_mfsp_square
        ret z
        cp  LST_THICKSPICE
        jr  z, st_mft_yes
        ; spice: thick spice near it instead, if there is some
        push hl
        ld  (st_s2_tmp), hl
        ld  hl, tbl_spice_ring
        ld  b, 24
st_mft_1:  push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        inc hl
        ld  c, (hl)
        inc hl
        ld  b, (hl)
        ld  hl, (st_s2_tmp)
        add hl, de
        add hl, bc
        ld  a, h
        and $0F
        ld  h, a
        call st_mfsp_square
        jr  z, st_mft_2
        cp  LST_THICKSPICE
        jr  nz, st_mft_2
        pop de
        pop bc
        pop de
        or  1
        ret
st_mft_2:  pop hl
        ld  de, 4
        add hl, de
        pop bc
        djnz st_mft_1
        pop hl
st_mft_yes:
        or  1
        ret
; HL = a square -> Z unless it is on the map, empty, and spice not $BF
; or thick not $CF (A = the landscape type then).  Keeps HL.
st_mfsp_square:
        call map_valid
        jr  nc, st_mfq_no
        push hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        or  a
        jr  nz, st_mfq_no
        push hl
        call map_landscape
        pop hl
        cp  LST_SPICE
        ld  c, $BF
        jr  z, st_mfq_1
        cp  LST_THICKSPICE
        ld  c, $CF
        jr  nz, st_mfq_no
st_mfq_1:  push af
        push hl
        call map_ground_icon
        ld  a, h
        or  a
        jr  nz, st_mfq_2
        ld  a, l
        cp  c
st_mfq_2:  pop hl
        jr  z, st_mfq_pop
        pop af
        cp  0
        ret                     ; NZ (A is 8 or 9)
st_mfq_pop:
        pop af
st_mfq_no: xor a
        ret

; map_bloom_explode ($01AC18): HL = a bloom's square, A = the house that
; set it off.  Unless validate_strict: the unit on it is removed, the
; square gets its loaded ground back, explosion $13 at its centre.  The
; player hears voice $24.  Then spice within 5 (map_spice_fill_circle).
map_bloom_explode:
        ld  (st_s2_house), a
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_s2_sq2), hl
        ld  a, (validate_strict)
        or  a
        jr  nz, st_mbe_1
        call st_s2_sq_unit
        jr  z, st_mbe_0
        push ix
        push hl
        pop ix
        FCALL unit_remove
        pop ix
st_mbe_0:  ld  hl, (st_s2_sq2)
        ld  a, PG_MAPGROUND
        call map_w1
        push hl
        ld  a, h
        or  $40
        ld  h, a
        ld  e, (hl)
        ld  d, 0
        ld  a, PG_UNITS
        call map_w1
        pop hl
        call st_s2_set_ground
        ld  de, arg_pos
        call square_centre
        ld  a, $13
        ld  hl, 0
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
st_mbe_1:  ld  a, (player_house)
        ld  hl, st_s2_house
        cp  (hl)
        jr  nz, st_mbe_2
        ld  a, $24
        FCALL snd_voice
st_mbe_2:  ld  hl, (st_s2_sq2)
        ld  a, 5
        ; fall through

; map_spice_fill_circle ($01ACC4): HL = the centre, A = the radius: a step
; of spice on every square within the radius (tile_distance_packed) that
; is not spice already - one exactly at the radius only on a random bit -
; and then on the centre.
map_spice_fill_circle:
        or  a
        ret z
        ld  (st_s2_radius), a
        ld  (st_s2_sq2), hl
        neg
        ld  (st_s2_dy), a
st_msc_row:
        ld  a, (st_s2_radius)
        neg
        ld  (st_s2_dx), a
st_msc_col:
        ; the square: centre + dy * 64 + dx
        ld  a, (st_s2_dy)
        ld  l, a
        rla
        sbc a, a
        ld  h, a
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (st_s2_dx)
        ld  e, a
        rla
        sbc a, a
        ld  d, a
        add hl, de
        ld  de, (st_s2_sq2)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_s2_sq), hl
        ex  de, hl
        ld  hl, (st_s2_sq2)
        call tile_distance_packed
        ld  a, (st_s2_radius)
        cp  l
        jr  z, st_msc_edge
        jr  c, st_msc_next
        jr  st_msc_add
st_msc_edge:
        call random
        rra
        jr  nc, st_msc_next
st_msc_add:
        ld  hl, (st_s2_sq)
        call map_landscape
        cp  LST_SPICE
        jr  z, st_msc_next
        ld  hl, (st_s2_sq)
        push hl
        ld  hl, (st_s2_sq2)
        ex  (sp), hl            ; keep the centre
        ld  a, 1
        call map_change_spice
        pop hl
        ld  (st_s2_sq2), hl
st_msc_next:
        ld  hl, st_s2_dx
        inc (hl)
        ld  a, (st_s2_radius)
        cp  (hl)
        jp  p, st_msc_col
        ld  hl, st_s2_dy
        inc (hl)
        ld  a, (st_s2_radius)
        cp  (hl)
        jp  p, st_msc_row
        ld  hl, (st_s2_sq2)
        ld  a, 1
        jp  map_change_spice

; ================================================ harvesting (S5)
;
; The UNIT.EMC routines: IX = the unit's script state (the unit is IX -
; O_SCRIPT).

; UNIT 42 harvest ($045A9C): a Harvester with room on spice takes 0 or 1
; (one call in 32 takes a step off the square and answers 0).  With
; flags2 bit 10 it stalls three calls in four, then clears it and answers
; 0 (Mega Drive only).  -> 1 keep at it, 0 stop.
ef_u_harvest:
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jp  nz, st_euh_no
        ld  a, (ix + U_AMOUNT)
        cp  100
        jp  nc, st_euh_no
        call st_s2_square
        ld  (st_s2_sq), hl
        call map_landscape
        cp  LST_SPICE
        jr  z, st_euh_1
        cp  LST_THICKSPICE
        jp  nz, st_euh_no
st_euh_1:  bit 2, (ix + O_FLAGS2 + 1)
        jr  z, st_euh_2
        call random
        and 3
        jr  z, st_euh_1a
        ld  hl, 1
        ret
st_euh_1a: res 2, (ix + O_FLAGS2 + 1)
        jr  st_euh_no
st_euh_2:  call random
        and 1
        add a, (ix + U_AMOUNT)
        ld  (ix + U_AMOUNT), a
        set OF_INTRANSPORT - 8, (ix + O_FLAGS + 1)
        ld  a, 2
        FCALL unit_update_map
        ld  a, (ix + U_AMOUNT)
        cp  101
        jr  c, st_euh_3
        ld  (ix + U_AMOUNT), 100
st_euh_3:  call random
        and 31
        ld  hl, 1
        ret nz
        ld  hl, (st_s2_sq)
        ld  a, $FF
        call map_change_spice
st_euh_no: ld  hl, 0
        ret

; UNIT 41 find.spice ($0112F2): unless noSpiceFound (flags2 bit 5), spice
; within 32 of the unit - whatever the script asks for (S5, kept) - as a
; place; none sets noSpiceFound.
ef_u_find_spice:
        ld  de, -O_SCRIPT
        add ix, de
        bit 5, (ix + O_FLAGS2)
        jr  nz, st_eufs_no
        call st_s2_square
        ld  a, 32
        call map_find_spice
        jr  z, st_eufs_none
        jp  ref_make_square
st_eufs_none:
        set 5, (ix + O_FLAGS2)
st_eufs_no:
        ld  hl, 0
        ret

; UNIT 32 amount ($0457C2): the spice in the unit it carries, or its own.
ef_u_amount:
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, st_eua_1
        call unit_ptr
        ld  de, U_AMOUNT
        add hl, de
        ld  l, (hl)
        ld  h, 0
        ret
st_eua_1:  ld  l, (ix + U_AMOUNT)
        ld  h, 0
        ret

; UNIT 37 find.struct ($045A16): the first structure of the unit's house
; of type n that is idle, empty and unclaimed, as a reference, or 0.
ef_u_find_struct:
        xor a
        call emc_arg
        ld  c, l
        ld  de, -O_SCRIPT
        add ix, de
        ld  b, (ix + O_HOUSE)
        push ix
        ld  hl, st_s2_state
        call st_s2_sfind_first
st_euf_1:  jr  z, st_euf_none
        call st_euf_free
        jr  z, st_euf_hit
        ld  hl, st_s2_state
        call st_s2_sfind_next
        jr  st_euf_1
st_euf_hit:
        ld  l, (ix + O_INDEX)
        ld  h, REF_STRUCT >> 8
        pop ix
        ret
st_euf_none:
        pop ix
        ld  hl, 0
        ret
; IX = a structure -> Z if idle (state 0), nothing linked, unclaimed.
st_euf_free:
        ld  a, (ix + S_STATE)
        or  (ix + S_STATE + 1)
        ret nz
        ld  a, (ix + O_LINKED)
        inc a
        jr  z, st_euf_f1
        or  1
        ret
st_euf_f1: ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        or  (ix + O_SCRIPT + SC_VARS + 9)
        ret

; UNIT 30 seek.dock ($0456B8): a structure of type n of the unit's house
; to dock at, claimed: the one the unit it carries came from if that is
; idle and unclaimed, else the first idle, unclaimed one.  +$5C takes it.
; -> the reference, or 0.
ef_u_seek_dock:
        xor a
        call emc_arg
        ld  a, l
        ld  (st_s2_u), a
        ld  de, -O_SCRIPT
        add ix, de
        ld  a, (ix + O_INDEX)
        ld  l, a
        ld  h, REF_UNIT >> 8
        ld  (st_s2_ref), hl        ; the unit's own reference
        ld  a, (ix + O_LINKED)
        cp  $FF
        jr  z, st_esd_find
        call unit_ptr
        ld  de, U_ORIGIN
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        call st_s2_ref_struct
        jr  z, st_esd_find
        push ix
        push hl
        pop ix
        call st_esd_ok
        jr  nz, st_esd_f0
        call st_esd_claim
        pop ix
        ; +$5C = what the running object now claims (the cartridge reads
        ; scriptCurrentObject's variable 4 here)
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  hl, (st_s2_tmp)
        ret
st_esd_f0: pop ix
st_esd_find:
        ld  a, (st_s2_u)
        ld  c, a
        ld  b, (ix + O_HOUSE)
        push ix
        ld  hl, st_s2_state
        call st_s2_sfind_first
st_esd_1:  jr  z, st_esd_none
        call st_esd_ok
        jr  z, st_esd_hit
        ld  hl, st_s2_state
        call st_s2_sfind_next
        jr  st_esd_1
st_esd_hit:
        call st_esd_claim
        pop ix
        ld  hl, (st_s2_tmp)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ret
st_esd_none:
        pop ix
        ld  hl, 0
        ret
; IX = a structure -> Z if idle and unclaimed.
st_esd_ok: ld  a, (ix + S_STATE)
        or  (ix + S_STATE + 1)
        ret nz
        ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        or  (ix + O_SCRIPT + SC_VARS + 9)
        ret
; IX = a structure: linked with the unit (s2_ref); s2_tmp = its reference.
st_esd_claim:
        ld  l, (ix + O_INDEX)
        ld  h, REF_STRUCT >> 8
        ld  (st_s2_tmp), hl
        ex  de, hl
        ld  hl, (st_s2_ref)
        jp  st_s2_var4_link

; UNIT 51 go.nearest ($045D6E): the unit is ordered to Move to the nearest
; structure of its house of type n that is idle, empty and unclaimed,
; which becomes its destination.  -> 1 if there was one.
ef_u_go_nearest:
        xor a
        call emc_arg
        ld  c, l
        ld  de, -O_SCRIPT
        add ix, de
        ld  b, (ix + O_HOUSE)
        ld  hl, 0
        ld  (st_s2_best), hl       ; the distance, 0 none
        ld  a, $FF
        ld  (st_s2_i), a           ; the slot
        push ix
        pop iy                  ; IY = the unit
        push ix
        ld  hl, st_s2_state
        call st_s2_sfind_first
st_egn_1:  jr  z, st_egn_2
        call st_euf_free
        jr  nz, st_egn_n
        push iy
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ex  de, hl
        push ix
        pop hl
        ld  bc, O_POS_Y
        add hl, bc
        call st_s2_dist_squares    ; HL = the distance
        ld  de, (st_s2_best)
        ld  a, d
        or  e
        jr  z, st_egn_take
        push hl
        or  a
        sbc hl, de
        pop hl
        jr  nc, st_egn_n
st_egn_take:
        ld  (st_s2_best), hl
        ld  a, (ix + O_INDEX)
        ld  (st_s2_i), a
st_egn_n:  ld  hl, st_s2_state
        call st_s2_sfind_next
        jr  st_egn_1
st_egn_2:  pop ix
        ld  a, (st_s2_i)
        cp  $FF
        jr  z, st_egn_no
        ld  a, ORDER_MOVE
        FCALL unit_give_order
        ld  a, (st_s2_i)
        ld  l, a
        ld  h, REF_STRUCT >> 8
        call st_s2_set_destination
        ld  hl, 1
        ret
st_egn_no: ld  hl, 0
        ret

; unit_set_destination ($047D18), for a structure reference: IX = the
; unit, HL = the reference.  One of its own house is claimed for it (the
; cartridge also asks unit_can_enter_structure; a flyer claims any); +$5C
; takes it and the route is cleared.
st_s2_set_destination:
        ld  e, (ix + U_TARGETMOVE)
        ld  d, (ix + U_TARGETMOVE + 1)
        or  a
        push hl
        sbc hl, de
        pop hl
        ret z
        ld  (st_s2_ref), hl
        push hl
        call st_s2_ref_struct
        pop de
        jr  z, st_ssd_2
        push hl
        pop iy
        ld  a, (iy + O_HOUSE)
        cp  (ix + O_HOUSE)
        jr  nz, st_ssd_2
        push iy
        FCALL unit_can_enter_structure
        pop iy
        or  a
        jr  z, st_ssd_2
        ld  a, (ix + O_INDEX)
        ld  l, a
        ld  h, REF_UNIT >> 8
        ld  de, (st_s2_ref)
        call st_s2_var4_link
st_ssd_2:  ld  hl, (st_s2_ref)
        ld  (ix + U_TARGETMOVE), l
        ld  (ix + U_TARGETMOVE + 1), h
        ld  (ix + U_ROUTE), $FF
        ret

; UNIT 55 claim.ok? ($045EF2): what the unit claims must claim it back and
; be of its house; if not the claim is broken (a claimed unit's +$5C
; too).  -> 1 or 0.
ef_u_claim_ok:
        ld  de, -O_SCRIPT
        add ix, de
        ld  l, (ix + O_SCRIPT + SC_VARS + 8)
        ld  h, (ix + O_SCRIPT + SC_VARS + 9)
        ld  (st_s2_ref), hl
        call st_s2_ref_object
        jr  z, st_eco_break
        push hl
        pop iy
        ld  a, (iy + O_SCRIPT + SC_VARS + 8)
        cp  (ix + O_INDEX)
        jr  nz, st_eco_bad
        ld  a, (iy + O_SCRIPT + SC_VARS + 9)
        cp  REF_UNIT >> 8
        jr  nz, st_eco_bad
        ld  a, (iy + O_HOUSE)
        cp  (ix + O_HOUSE)
        jr  nz, st_eco_bad
        ld  hl, 1
        ret
st_eco_bad:
        ld  a, (st_s2_ref + 1)
        and $C0
        cp  $40
        jr  nz, st_eco_break
        ld  (iy + U_TARGETMOVE), 0
        ld  (iy + U_TARGETMOVE + 1), 0
st_eco_break:
        FCALL obj_var4_clear
        ld  hl, 0
        ret

; ============================================== docking and the MCV

; unit_enter_structure ($048802): IX = a unit arriving, IY = the
; structure.  A unit not active, or a structure with no health left:
; the unit is removed.  Otherwise it is lifted off the map and:
;   an allied one docks - the structure goes busy (2 if its type has
;   busyStateIsIncoming, else 1); a Repair Facility heals it at once
;   and takes its repair time; a Refinery takes a Harvester onto its pad;
;   it joins the structure's chain;
;   an enemy Saboteur blows up (500);
;   other enemies capture it below a quarter of its hit points (house,
;   counts, structuresBuilt, choice, fog), else damage it and are freed.
unit_enter_structure:
        bit 1, (ix + O_FLAGS)
        jr  z, st_ues_remove
        ld  a, (iy + O_HP)
        or  (iy + O_HP + 1)
        jr  nz, st_ues_1
st_ues_remove:
        FCALL unit_remove
        ret
st_ues_1:  ld  a, (unit_selected)
        cp  (ix + O_INDEX)
        jr  nz, st_ues_1a
        ld  a, $FF
        ld  (unit_selected), a
st_ues_1a: ld  a, (iy + O_SEEN)
        or  (ix + O_SEEN)
        ld  (ix + O_SEEN), a
        call st_s2_take_off_map
        ld  a, (ix + O_TYPE)
        cp  UNIT_HARVESTER
        jr  nz, st_ues_2
        ld  a, (ix + U_TARGETATTACK)
        ld  (iy + S_ROTSPRITEDIFF), a
        ld  a, (ix + U_TARGETATTACK + 1)
        ld  (iy + S_ROTSPRITEDIFF + 1), a
st_ues_2:  ld  b, (ix + O_HOUSE)
        ld  c, (iy + O_HOUSE)
        call house_are_allied
        or  a
        jp  z, st_ues_enemy
        ; docking
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_flags
        add hl, de
        ld  a, 1
        bit 4, (hl)
        jr  z, st_ues_3
        inc a
st_ues_3:  ld  (iy + S_STATE), a
        ld  (iy + S_STATE + 1), 0
        ld  a, (iy + O_TYPE)
        cp  STRUCT_REPAIR
        jr  nz, st_ues_4
        ; the repair time: max((buildTime << 6) * missing / type.hp, 1);
        ; the unit is healed at once
        ld  a, (ix + O_TYPE)
        call unit_info
        ld  (st_s2_tmp), hl
        ld  de, UI_hitpoints
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  (st_s2_best), de       ; type.hp
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        ex  de, hl              ; HL = type.hp, DE = hp
        push hl
        or  a
        sbc hl, de
        ex  de, hl              ; DE = missing
        pop hl
        call div_shl8           ; missing * 256 / type.hp
        push hl
        ld  hl, (st_s2_tmp)
        ld  de, UI_buildTime
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        pop de
        call mul_shr8
        ld  a, h
        or  a
        jr  nz, st_ues_3a
        ld  a, l
        cp  2
        jr  nc, st_ues_3a
        ld  hl, 1
st_ues_3a: ld  (iy + S_COUNTDOWN), l
        ld  (iy + S_COUNTDOWN + 1), h
        ld  (ix + U_TARGETATTACK), l
        ld  (ix + U_TARGETATTACK + 1), h
        ld  hl, (st_s2_best)
        ld  (ix + O_HP), l
        ld  (ix + O_HP + 1), h
        res 3, (ix + O_FLAGS)
        ld  (ix + U_SPRITEOFS), 0
st_ues_4:  ld  a, (iy + O_TYPE)
        cp  STRUCT_REFINERY
        jr  nz, st_ues_5
        ld  (ix + U_OR0_SPEED), 0
        ld  (ix + U_OR0_TARGET), 0
        ld  (ix + U_OR0_CURRENT), $80
        ld  (ix + U_SHOWN), 1   ; drawn on the pad (c_spr_show)
        ld  bc, $0180
        ld  de, $0280
        jr  st_ues_6
st_ues_5:  ld  bc, $0100
        ld  de, $0100
st_ues_6:  ld  l, (iy + O_POS_Y)
        ld  h, (iy + O_POS_Y + 1)
        add hl, bc
        ld  (ix + O_POS_Y), l
        ld  (ix + O_POS_Y + 1), h
        ld  l, (iy + O_POS_X)
        ld  h, (iy + O_POS_X + 1)
        add hl, de
        ld  (ix + O_POS_X), l
        ld  (ix + O_POS_X + 1), h
        ld  a, (iy + O_LINKED)
        ld  (ix + O_LINKED), a
        ld  a, (ix + O_INDEX)
        ld  (iy + O_LINKED), a
        ret
st_ues_enemy:
        ld  a, (ix + O_TYPE)
        cp  UNIT_SABOTEUR
        jr  nz, st_ues_e1
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        ld  a, 4
        ld  hl, 500
        ld  de, 0
        push ix
        FCALL map_make_explosion
        pop ix
        FCALL unit_free
        ret
st_ues_e1: ; below a quarter of its hit points: captured
        ld  a, (iy + O_TYPE)
        call struct_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        inc hl
        ld  h, (hl)
        ld  l, a
        sra h
        rr  l
        sra h
        rr  l
        ld  e, (iy + O_HP)
        ld  d, (iy + O_HP + 1)
        or  a
        sbc hl, de              ; quarter - hp
        jp  z, st_ues_hit
        jp  m, st_ues_hit
        call st_ues_capture
        jp  st_ues_free
st_ues_hit:
        ; damage min(unit hp * 2, structure hp / 2), explosion 3 at its
        ; centre
        ld  l, (ix + O_HP)
        ld  h, (ix + O_HP + 1)
        add hl, hl
        ld  e, (iy + O_HP)
        ld  d, (iy + O_HP + 1)
        srl d
        rr  e
        push hl
        or  a
        sbc hl, de
        pop hl
        jr  c, st_ues_h1
        ex  de, hl
st_ues_h1: push ix
        push iy
        pop ix
        FCALL struct_damage
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        call st_s2_layout
        add a, a
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_centre
        add hl, de
        ld  de, arg_pos
        ld  b, 2
st_ues_h2: ld  a, (de)
        add a, (hl)
        ld  (de), a
        inc de
        inc hl
        ld  a, (de)
        adc a, (hl)
        ld  (de), a
        inc de
        inc hl
        djnz st_ues_h2
        ld  a, 3
        ld  hl, 0
        ld  de, 0
        FCALL map_make_explosion
        pop ix
st_ues_free:
        push ix
        push iy
        pop ix
        FCALL obj_var4_clear
        pop ix
        FCALL unit_free
        ret

; The capture ($0489B8): IX = the unit, IY = the structure.  Keeps IX,
; IY.
st_ues_capture:
        ld  a, (ix + O_HOUSE)
        ld  (st_s2_house), a
        push ix
        push iy
        pop ix                  ; IX = the structure
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_uec_2
        ld  c, a
        ld  a, (ix + O_TYPE)
        cp  STRUCT_REFINERY
        jr  z, st_uec_chain
        cp  STRUCT_REPAIR
        jr  z, st_uec_chain
        cp  STRUCT_CONSTYARD
        push ix
        ld  a, c
        jr  z, st_uec_s
        ; anything else: what it makes is freed
        call unit_ptr
        push hl
        pop ix
        FCALL unit_free
        jr  st_uec_1
st_uec_s:  call struct_ptr
        push hl
        pop ix
        FCALL struct_free
st_uec_1:  pop ix
        ld  (ix + O_LINKED), $FF
        ld  a, (ix + O_FLAGS2 + 1)
        and $9F
        ld  (ix + O_FLAGS2 + 1), a
        jr  st_uec_2
st_uec_chain:
        ; the docked units change house with it
        ld  a, c
st_uec_c1: cp  $FF
        jr  z, st_uec_2
        push ix
        call unit_ptr
        push hl
        pop ix                  ; IX = a docked unit
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call st_s2_utc_addr
        dec (hl)
        ld  a, (ix + O_INDEX)
        FCALL unit_list_unlink
        ld  a, (st_s2_house)
        ld  (ix + O_HOUSE), a
        ld  (ix + U_ORIGHOUSE), a
        ld  a, (ix + O_INDEX)
        FCALL unit_list_link
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call st_s2_utc_addr
        inc (hl)
        ld  a, (ix + O_LINKED)
        pop ix
        jr  st_uec_c1
st_uec_2:  call st_struct_free_refs
        ld  a, (ix + O_INDEX)
        FCALL struct_list_unlink
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call st_s2_stc_addr
        dec (hl)
        jr  nz, st_uec_3
        ; the old house has no more of them
        ld  a, (ix + O_HOUSE)
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  a, (ix + O_TYPE)
        call st_s2_clr_bit32
st_uec_3:  ld  a, (st_s2_house)
        ld  (ix + O_HOUSE), a
        call house_ptr
        ld  de, H_BUILT
        add hl, de
        ld  a, (ix + O_TYPE)
        call st_s2_set_bit32
        res st_SF_REPAIRING_B, (ix + O_FLAGS + 1)
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        ld  a, $FF
        jr  z, st_uec_4
        ld  a, (ix + O_HOUSE)
        call st_s2_bit_of
        or  (ix + O_SEEN)
st_uec_4:  ld  (ix + O_SEEN), a
        ; what it offers
        ld  a, (ix + O_TYPE)
        cp  STRUCT_LIGHTFACTORY
        jr  z, st_uec_7
        cp  STRUCT_HEAVYFACTORY
        jr  nz, st_uec_5
        ld  a, (ix + S_CREATORHOUSE)
        ld  c, UNIT_TRIKE
        cp  HOUSE_ATREIDES
        jr  z, st_uec_4a
        ld  c, UNIT_RAIDERTRIKE
        cp  HOUSE_ORDOS
        jr  z, st_uec_4a
        ld  c, UNIT_QUAD
st_uec_4a: ld  (ix + S_OBJECTTYPE), c
        ld  (ix + S_OBJECTTYPE + 1), 0
        jr  st_uec_7
st_uec_5:  cp  STRUCT_HITECH
        jr  nz, st_uec_6
        ld  (ix + S_OBJECTTYPE), 0
        ld  (ix + S_OBJECTTYPE + 1), 0
        jr  st_uec_7
st_uec_6:  cp  STRUCT_CONSTYARD
        jr  nz, st_uec_6a
        ld  (ix + S_OBJECTTYPE), STRUCT_SLAB4
        ld  (ix + S_OBJECTTYPE + 1), 0
st_uec_6a: ld  a, (ix + O_HOUSE)
        ld  (ix + S_CREATORHOUSE), a
        ld  (ix + S_CREATORHOUSE + 1), 0
st_uec_7:  call struct_offer_fix
        ld  a, (ix + O_INDEX)
        FCALL struct_list_link
        ld  b, (ix + O_HOUSE)
        ld  a, (ix + O_TYPE)
        call st_s2_stc_addr
        inc (hl)
        ld  a, (ix + O_HOUSE)
        FCALL house_calc_power
        res 4, (ix + O_FLAGS2)  ; the house marker again
        ld  a, (player_house)
        cp  (ix + O_HOUSE)
        jr  nz, st_uec_8
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        ld  de, arg_pos
        ld  bc, 4
        ldir
        call st_s2_info
        ld  de, SI_sight
        add hl, de
        ld  c, (hl)
        ld  hl, arg_pos
        FCALL map_unfog_radius
st_uec_8:  FCALL struct_place_icons
        push ix
        pop iy
        pop ix
        ret

; unit_take_off_map ($04869C): IX = a unit: off its squares, its script
; reset, every reference to it dropped, hidden, unseen by the player, its
; position -1.
st_s2_take_off_map:
        push iy
        xor a
        FCALL unit_update_map
        push ix
        ld  de, O_SCRIPT
        add ix, de
        ld  (ix + SC_PC), 0
        ld  (ix + SC_PC + 1), 0
        ld  (ix + SC_ISSUB), 0
        ld  (ix + SC_FP), $11
        ld  (ix + SC_SP), $0F
        pop ix
        FCALL unit_drop_references
        set OF_NOTONMAP, (ix + O_FLAGS)
        ld  (ix + U_SHOWN), 0   ; its sprite hidden (c_spr_hide)
        ld  a, (player_house)
        FCALL unit_unseen_by_houses
        ld  a, $FF
        ld  (ix + O_POS_Y), a
        ld  (ix + O_POS_Y + 1), a
        ld  (ix + O_POS_X), a
        ld  (ix + O_POS_X + 1), a
        pop iy
        ret

; unit_deploy_mcv ($045F86): IX = an MCV whose deploy animation has ended.
; If a Construction Yard may stand on its square it is made there (level
; 1 from campaign 6), at full health, seen by everyone; sound $14 and the
; MCV is removed.  Otherwise sound $2F and it stays.  -> A = 1 deployed.
unit_deploy_mcv:
        call st_s2_square
        ld  (st_s2_sq2), hl
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  (hl), 0
        ld  hl, (st_s2_sq2)
        ld  a, STRUCT_CONSTYARD
        FCALL struct_check_location
        ld  a, h
        or  l
        jr  z, st_udm_no
        push ix
        ld  b, $FF
        ld  c, STRUCT_CONSTYARD
        ld  d, (ix + O_HOUSE)
        ld  hl, (st_s2_sq2)
        FCALL struct_create
        pop ix
        jr  z, st_udm_no
        push ix
        push hl
        pop ix
        ld  a, (campaign_id)
        cp  6
        jr  c, st_udm_1
        ld  (ix + S_UPGRADELEVEL), 1
st_udm_1:  res OF_NOTONMAP, (ix + O_FLAGS)
        ld  (ix + S_STATE), 0
        ld  (ix + S_STATE + 1), 0
        ld  a, STRUCT_CONSTYARD
        call struct_info
        ld  de, SI_hitpoints
        add hl, de
        ld  a, (hl)
        ld  (ix + O_HP), a
        inc hl
        ld  a, (hl)
        ld  (ix + O_HP + 1), a
        ld  (ix + O_SEEN), $FF
        pop ix
        ld  hl, (st_s2_sq2)
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        res MF_UNIT, (hl)
        ld  a, $14
        FCALL snd_effect
        FCALL unit_remove
        ld  a, 1
        ret
st_udm_no: ld  hl, (st_s2_sq2)
        ld  a, h
        or  MAP_INDEX >> 8
        ld  h, a
        ld  a, (ix + O_INDEX)
        inc a
        ld  (hl), a
        ld  a, $2F
        FCALL snd_effect
        xor a
        ret

; UNIT 9 deploy ($045E2C): the MCV lifted off the map; a Construction
; Yard is made on its square or one of the three up and left of it; if
; one is, the MCV is removed, else put back.  -> 1 if it deployed.
ef_u_deploy:
        ld  de, -O_SCRIPT
        add ix, de
        xor a
        FCALL unit_update_map
        call st_s2_square
        ld  (st_s2_sq2), hl
        ld  hl, tbl_mcv_squares
        ld  b, 4
st_eud_1:  push bc
        push hl
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        ld  hl, (st_s2_sq2)
        add hl, de
        push ix
        ld  b, $FF
        ld  c, STRUCT_CONSTYARD
        ld  d, (ix + O_HOUSE)
        FCALL struct_create
        pop ix
        pop de
        pop bc
        jr  nz, st_eud_yes
        inc de
        inc de
        ex  de, hl
        djnz st_eud_1
        ld  a, 1
        FCALL unit_update_map
        ld  hl, 0
        ret
st_eud_yes:
        FCALL unit_remove
        ld  hl, 1
        ret

; struct_find_free_square ($0108CE, PC Structure_FindFreePosition): IX = a
; structure with a unit linked, A = nonzero to look near spice -> HL = a
; free square round it, or 0.  The sixteen round its layout from a random
; start; a square must be on the map, empty, not a wall, and a mountain
; only for a unit on foot.  Looking near spice (spice within 32 of it):
; the square nearest that spice, and the unit's noSpiceFound is cleared.
struct_find_free_square:
        ld  (st_s2_flag), a
        ld  a, (ix + O_LINKED)
        cp  $FF
        jp  z, st_sff_none
        call unit_ptr
        ld  (st_s2_u), hl
        inc hl
        inc hl
        ld  a, (hl)
        call unit_info
        ld  de, UI_movementType
        add hl, de
        ld  a, (hl)
        ld  (st_s2_mv), a
        call st_s2_square
        ld  (st_s2_sq), hl
        ld  hl, 0
        ld  (st_s2_spice), hl
        ld  a, (st_s2_flag)
        or  a
        jr  z, st_sff_1
        ld  hl, (st_s2_sq)
        ld  a, 32
        call map_find_spice
        ld  (st_s2_spice), hl
        jr  nz, st_sff_0
        xor a
        ld  (st_s2_flag), a
        jr  st_sff_1
st_sff_0:  ld  hl, (st_s2_u)
        ld  de, O_FLAGS2
        add hl, de
        res 5, (hl)
st_sff_1:  ld  hl, 0
        ld  (st_s2_best), hl       ; the best distance, 0 none
        ld  (st_s2_found), hl      ; the square, 0 none
        call random
        and 15
        ld  (st_s2_i), a           ; d7
        ld  a, 16
        ld  (st_s2_left), a
st_sff_loop:
        call st_sff_offset         ; DE = the offset, Z if 0
        jr  z, st_sff_skip
        ld  hl, (st_s2_sq)
        add hl, de
        ld  a, h
        and $0F
        ld  h, a
        ld  (st_s2_sq3), hl
        ld  a, h
        or  MAP_FLAGS >> 8
        ld  h, a
        ld  a, (hl)
        and $30
        jr  nz, st_sff_skip
        ld  hl, (st_s2_sq3)
        call map_valid
        jr  nc, st_sff_skip
        call map_landscape
        cp  LST_WALL
        jr  z, st_sff_skip
        cp  LST_MOUNTAIN
        jr  z, st_sff_mt
        cp  LST_PARTIALMOUNTAIN
        jr  nz, st_sff_ok
st_sff_mt: ld  a, (st_s2_mv)
        or  a
        jr  nz, st_sff_skip
st_sff_ok: ld  a, (st_s2_flag)
        or  a
        jr  z, st_sff_first
        ld  hl, (st_s2_spice)
        ld  de, (st_s2_sq3)
        call tile_distance_packed
        ld  de, (st_s2_best)
        ld  a, d
        or  e
        jr  z, st_sff_take
        push hl
        or  a
        sbc hl, de
        pop hl
        jr  nc, st_sff_skip
st_sff_take:
        ld  (st_s2_best), hl
        ld  hl, (st_s2_sq3)
        ld  (st_s2_found), hl
        jr  st_sff_skip
st_sff_first:
        ld  hl, (st_s2_sq3)
        ret
st_sff_skip:
        ; the cartridge's step ($010A5E): on, and on again unless it wraps
        ld  hl, st_s2_i
        inc (hl)
        ld  hl, st_s2_left
        dec (hl)
        ld  a, (st_s2_i)
        cp  16
        jr  nc, st_sff_wrap
        call st_sff_offset
        jr  z, st_sff_wrap
        ld  hl, st_s2_i
        inc (hl)
        jr  st_sff_cont
st_sff_wrap:
        ld  a, (st_s2_i)
        ld  b, a
        ld  a, 16
        sub b                   ; 16 - d7
        ld  b, a
        ld  a, (st_s2_left)
        sub b
        ld  (st_s2_left), a
        xor a
        ld  (st_s2_i), a
st_sff_cont:
        ld  a, (st_s2_left)
        or  a
        jr  z, st_sff_end
        jp  p, st_sff_loop
st_sff_end:
        ld  hl, (st_s2_found)
        ret
st_sff_none:
        ld  hl, 0
        ret
; -> DE = the around offset s2_i of the layout, Z if 0 (or past 15).
st_sff_offset:
        ld  a, (st_s2_i)
        cp  16
        jr  nc, st_sffo_0
        push hl
        call st_s2_layout
        ld  l, a
        ld  h, 0
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, hl
        ld  a, (st_s2_i)
        add a, a
        ld  e, a
        ld  d, 0
        add hl, de
        ld  de, tbl_layout_around
        add hl, de
        ld  e, (hl)
        inc hl
        ld  d, (hl)
        pop hl
        ld  a, d
        or  e
        ret
st_sffo_0: ld  de, 0
        xor a
        ret

; ================================================== little helpers

; obj_var4_link ($023CCC): HL = a reference, DE = another: both must be
; valid; links elsewhere are broken; each gets the other in variable 4
; (obj_var4_set), unless the first is linked already.
st_s2_var4_link:
        ld  (st_s2_ra), hl
        ld  (st_s2_rb), de
        call ref_is_valid
        or  a
        ret z
        ld  hl, (st_s2_rb)
        call ref_is_valid
        or  a
        ret z
        push ix
        ld  hl, (st_s2_ra)
        call st_s2_ref_object
        jr  z, st_svl_out
        push hl
        ld  hl, (st_s2_rb)
        call st_s2_ref_object
        pop de
        jr  z, st_svl_out
        push de
        pop ix                  ; IX = a
        push hl
        pop iy                  ; IY = b
        ; linked elsewhere: both broken
        ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        cp  (iy + O_SCRIPT + SC_VARS + 8)
        jr  nz, st_svl_1
        ld  a, (ix + O_SCRIPT + SC_VARS + 9)
        cp  (iy + O_SCRIPT + SC_VARS + 9)
        jr  z, st_svl_2
st_svl_1:  push iy
        FCALL obj_var4_clear
        pop iy
        push ix
        push iy
        pop ix
        FCALL obj_var4_clear
        pop ix
st_svl_2:  ld  a, (ix + O_SCRIPT + SC_VARS + 8)
        or  (ix + O_SCRIPT + SC_VARS + 9)
        jr  nz, st_svl_out
        push iy
        ld  hl, (st_s2_rb)
        FCALL obj_var4_set
        pop iy
        push iy
        pop ix
        ld  hl, (st_s2_ra)
        FCALL obj_var4_set
st_svl_out:
        pop ix
        ret

; HL = a reference -> HL = the unit (a unit reference to a real slot), or
; Z.  Clobbers A, DE.
st_s2_ref_unit:
        ld  a, h
        and $C0
        cp  $40
        jr  nz, st_sru_no
        ld  a, l
        cp  UNIT_COUNT
        jr  nc, st_sru_no
        call unit_ptr
        or  1
        ret
st_sru_no: ld  hl, 0
        xor a
        ret
; HL = a reference -> HL = the structure, or Z.
st_s2_ref_struct:
        ld  a, h
        and $C0
        cp  $80
        jr  nz, st_sru_no
        ld  a, l
        cp  STRUCT_COUNT
        jr  nc, st_sru_no
        push hl
        call struct_ptr
        ld  de, O_FLAGS
        add hl, de
        bit OF_USED, (hl)
        pop hl
        jr  z, st_sru_no
        ld  a, l
        call struct_ptr
        or  1
        ret
; HL = a reference -> HL = the unit or structure, or Z.
st_s2_ref_object:
        push hl
        call st_s2_ref_unit
        pop de
        ret nz
        ex  de, hl
        jr  st_s2_ref_struct

; HL, DE -> positions -> HL = tile_distance_squares ($0115C2): the
; distance in squares, rounded ((d + $80) >> 8).
st_s2_dist_squares:
        call tile_distance
        ld  de, $80
        add hl, de
        ld  l, h
        ld  h, 0
        ret

; B = house, C = type: the first unit of them (the on-map rule) -> HL =
; it, Z none.
st_s2_ufind_one:
        ld  a, (unit_find_count)
        or  a
        jr  z, st_suf_none
        ld  hl, unit_find
st_suf_1:  push af
        push hl
        ld  a, (hl)
        call unit_ptr
        call st_s2_umatch
        jr  z, st_suf_yes
        pop hl
        inc hl
        pop af
        dec a
        jr  nz, st_suf_1
st_suf_none:
        ld  hl, 0
        xor a
        ret
st_suf_yes:
        pop de
        pop de
        ld  a, h
        or  l
        ret
; the same, but only one carrying nothing with nowhere to go
st_s2_ufind_idle:
        ld  a, (unit_find_count)
        or  a
        jr  z, st_suf_none
        ld  hl, unit_find
st_sui_1:  push af
        push hl
        ld  a, (hl)
        call unit_ptr
        call st_s2_umatch
        jr  nz, st_sui_2
        push hl
        pop iy
        ld  a, (iy + O_LINKED)
        inc a
        jr  nz, st_sui_2
        ld  a, (iy + U_TARGETMOVE)
        or  (iy + U_TARGETMOVE + 1)
        jr  z, st_suf_yes
st_sui_2:  pop hl
        inc hl
        pop af
        dec a
        jr  nz, st_sui_1
        jr  st_suf_none
; HL = a unit, B = house, C = type -> Z if it matches (the on-map rule).
; Keeps HL, BC.
st_s2_umatch:
        push hl
        inc hl
        inc hl
        ld  a, (hl)
        cp  c
        jr  nz, st_sum_no
        inc hl
        inc hl
        bit OF_NOTONMAP, (hl)
        jr  z, st_sum_m1
        ld  a, (validate_strict)
        or  a
        jr  z, st_sum_no
st_sum_m1: inc hl
        inc hl
        inc hl
        inc hl                  ; +8, the house
        ld  a, (hl)
        cp  b
        pop hl
        ret
st_sum_no: pop hl
        or  1
        ret

; The same search as bank STRUCT's, for this bank (HL = a 3-byte state).
st_s2_sfind_first:
        ld  (hl), b
        inc hl
        ld  (hl), c
        inc hl
        ld  (hl), $FF
        dec hl
        dec hl
st_s2_sfind_next:
        push hl
        inc hl
        inc hl
st_s2sf_l: inc (hl)
        ld  a, (struct_find_count)
        ld  c, a
        ld  a, (hl)
        cp  c
        jr  nc, st_s2sf_end
        ld  e, a
        ld  d, 0
        push hl
        ld  hl, struct_find
        add hl, de
        ld  a, (hl)
        call struct_ptr
        push hl
        pop ix
        pop hl
        dec hl
        ld  a, (hl)
        inc hl
        cp  $FF
        jr  z, st_s2sf_t
        cp  (ix + O_TYPE)
        jr  nz, st_s2sf_l
st_s2sf_t: bit OF_NOTONMAP, (ix + O_FLAGS)
        jr  z, st_s2sf_m
        ld  a, (validate_strict)
        or  a
        jr  z, st_s2sf_l
st_s2sf_m: dec hl
        dec hl
        ld  a, (hl)
        inc hl
        inc hl
        cp  $FF
        jr  z, st_s2sf_y
        cp  (ix + O_HOUSE)
        jr  nz, st_s2sf_l
st_s2sf_y: pop hl
        or  1
        ret
st_s2sf_end:
        ld  (hl), a
        pop hl
        xor a
        ret

; IY = a house, DE: credits += DE / -= DE / CF if credits < DE.
st_s2_cr_add:
        ld  a, (iy + H_CREDITS)
        add a, e
        ld  (iy + H_CREDITS), a
        ld  a, (iy + H_CREDITS + 1)
        adc a, d
        ld  (iy + H_CREDITS + 1), a
        ret nc
        inc (iy + H_CREDITS + 2)
        ret nz
        inc (iy + H_CREDITS + 3)
        ret
st_s2_cr_sub:
        ld  a, (iy + H_CREDITS)
        sub e
        ld  (iy + H_CREDITS), a
        ld  a, (iy + H_CREDITS + 1)
        sbc a, d
        ld  (iy + H_CREDITS + 1), a
        ld  a, (iy + H_CREDITS + 2)
        sbc a, 0
        ld  (iy + H_CREDITS + 2), a
        ld  a, (iy + H_CREDITS + 3)
        sbc a, 0
        ld  (iy + H_CREDITS + 3), a
        ret
st_s2_cr_lt:
        ld  a, (iy + H_CREDITS + 2)
        or  (iy + H_CREDITS + 3)
        ret nz
        ld  a, (iy + H_CREDITS)
        sub e
        ld  a, (iy + H_CREDITS + 1)
        sbc a, d
        ret

; The type mask s2_mask: A = a bit 0-31 to set / clear / test (NZ set).
; Keep BC, DE, HL.
st_s2_mset:
        push hl
        push bc
        call st_s2_mbit
        or  (hl)
        ld  (hl), a
        pop bc
        pop hl
        ret
st_s2_mclr:
        push hl
        push bc
        call st_s2_mbit
        cpl
        and (hl)
        ld  (hl), a
        pop bc
        pop hl
        ret
st_s2_mtest:
        push hl
        push bc
        call st_s2_mbit
        and (hl)
        pop bc
        pop hl
        ret
st_s2_mbit:
        ld  c, a
        srl a
        srl a
        srl a
        ld  hl, st_s2_mask
        add a, l
        ld  l, a
        jr  nc, st_s2mb_1
        inc h
st_s2mb_1: ld  a, c
        and 7
        jp  st_s2_bit_of
; HL -> a 32-bit mask, A = a bit: set / clear it.
st_s2_set_bit32:
        push af
        and $1F
        srl a
        srl a
        srl a
        add a, l
        ld  l, a
        jr  nc, st_s2sb_1
        inc h
st_s2sb_1: pop af
        and 7
        call st_s2_bit_of
        or  (hl)
        ld  (hl), a
        ret
st_s2_clr_bit32:
        push af
        and $1F
        srl a
        srl a
        srl a
        add a, l
        ld  l, a
        jr  nc, st_s2cb_1
        inc h
st_s2cb_1: pop af
        and 7
        call st_s2_bit_of
        cpl
        and (hl)
        ld  (hl), a
        ret
; s2_req against s2_built -> Z if every required bit is built.
st_s2_covers:
        push hl
        push de
        push bc
        ld  hl, st_s2_req
        ld  de, st_s2_built
        ld  b, 4
st_s2c_1:  ld  a, (de)
        cpl
        and (hl)
        jr  nz, st_s2c_2
        inc hl
        inc de
        djnz st_s2c_1
st_s2c_2:  pop bc
        pop de
        pop hl
        ret

; A = 0-7 -> A = 1 << A.
st_s2_bit_of:
        push bc
        ld  b, a
        inc b
        xor a
        scf
st_s2bo_1: rla
        djnz st_s2bo_1
        pop bc
        ret

st_s2_neg_de:
        xor a
        sub e
        ld  e, a
        sbc a, a
        sub d
        ld  d, a
        ret

; B = a house, A = a structure type -> HL = its structTypeCount byte.
st_s2_stc_addr:
        ld  e, a
        ld  a, b
        cp  5
        jr  c, st_s2stc_1
        xor a
st_s2stc_1:
        add a, a
        add a, a
        add a, a
        add a, a
        add a, a
        add a, e
        ld  e, a
        ld  d, 0
        ld  hl, struct_type_count
        add hl, de
        ret
; the same in unitTypeCount
st_s2_utc_addr:
        call st_s2_stc_addr
        ld  de, unit_type_count - struct_type_count
        add hl, de
        ret

; IX = a structure -> HL = its type record.
st_s2_info:
        ld  a, (ix + O_TYPE)
        jp  struct_info
; IX -> A = its layout.
st_s2_layout:
        call st_s2_info
        ld  de, SI_layout
        add hl, de
        ld  a, (hl)
        ret
; A = a layout -> HL -> its offsets, B = the count.
st_s2_layout_tiles:
        push af
        add a, a
        ld  e, a
        ld  d, 0
        ld  hl, tbl_layout_count
        add hl, de
        ld  b, (hl)
        pop af
        ld  l, a
        ld  h, 0
        add hl, hl
        ld  d, h
        ld  e, l
        add hl, hl
        add hl, hl
        add hl, hl
        add hl, de
        ld  de, tbl_layout_tiles
        add hl, de
        ret
; IX = a unit or structure -> HL = the square of its position.
st_s2_square:
        push ix
        pop hl
        ld  de, O_POS_Y
        add hl, de
        jp  pos_square
; HL = a square, DE = an icon: the ground, the overlay kept.  Keeps HL,
; DE.
st_s2_set_ground:
        push hl
        ld  a, h
        and $0F
        or  MAP_GROUND >> 8
        ld  h, a
        ld  (hl), e
        ld  a, h
        xor (MAP_HIGH ^ MAP_GROUND) >> 8
        ld  h, a
        ld  a, (hl)
        and $FE
        or  d
        ld  (hl), a
        pop hl
        ret
; HL = a square -> HL = the unit on it, or Z.
st_s2_sq_unit:
        push hl
        ld  a, h
        and $0F
        or  MAP_FLAGS >> 8
        ld  h, a
        bit MF_UNIT, (hl)
        ld  a, h
        xor (MAP_INDEX ^ MAP_FLAGS) >> 8
        ld  h, a
        ld  a, (hl)
        pop hl
        jr  z, st_s2su_no
        or  a
        jr  z, st_s2su_no
        dec a
        call unit_ptr
        or  1
        ret
st_s2su_no:
        ld  hl, 0
        xor a
        ret

; flags bits (byte +5) and flags2 bits (byte +7), as in bank STRUCT
st_SF_ONHOLD_B     EQU 6
st_SF_REPAIRING_B  EQU 5
st_S2_DONE_B       EQU 5

; ------------------------------------------------ the bank's own data
st_s2_mask:        DS 4
st_s2_built:       DS 4
st_s2_req:         DS 4
st_s2_i:           DB 0
st_s2_u:           DW 0
st_s2_need:        DB 0
st_s2_avail:       DB 0
st_s2_arg:         DW 0
st_s2_upg:         DB 0
st_s2_same:        DB 0
st_s2_best:        DW 0
st_s2_roll:        DB 0
st_s2_tmp:         DW 0
st_s2_house:       DB 0
st_s2_state:       DS 3
st_s2_sq:          DW 0
st_s2_sq2:         DW 0
st_s2_sq3:         DW 0
st_s2_layout_n:    DB 0
st_s2_ref:         DW 0
st_s2_ra:          DW 0
st_s2_rb:          DW 0
st_s2_create:      DB 0
st_s2_pos:         DS 4
st_s2_acc:         DW 0
st_s2_sign:        DB 0
st_s2_lt:          DB 0
st_s2_radius:      DB 0
st_s2_cx:          DB 0
st_s2_cy:          DB 0
st_s2_x0l:         DB 0
st_s2_y0l:         DB 0
st_s2_x1l:         DB 0
st_s2_y1l:         DB 0
st_s2_x0:          DB 0
st_s2_x1:          DB 0
st_s2_y0:          DB 0
st_s2_y1:          DB 0
st_s2_x:           DB 0
st_s2_y:           DB 0
st_s2_ring:        DB 0
st_s2_dx:          DB 0
st_s2_dy:          DB 0
st_s2_flag:        DB 0
st_s2_mv:          DB 0
st_s2_spice:       DW 0
st_s2_found:       DW 0
st_s2_left:        DB 0
