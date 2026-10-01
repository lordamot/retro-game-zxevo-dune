---
name: text
description: The words the game says, and the font it says them in. Use when adding, changing or translating a string, or when text draws wrongly.
---

# Words

Every word is the Mega Drive cartridge's, taken out once by
`tools/sega/port_data.py` into text that is now the source.  Much of what
looks like text on the Mega Drive's screens is a picture (the buttons, the
victory and defeat captions, the score headings - `src/res/art/ui/`), and
the tutorial's captions are in its picture scripts; the rest is here.

## Where the strings are

`src/res/data/text/*.txt` - `ui.txt` (the title menu, the options, the
confirm box, the build panel's and the Starport's boxes, the password
screen), `briefings.txt` (the mentat's 111 briefings, verdicts and tips),
`credits.txt`, `passwords.txt`, `ranks.txt`, `score_houses.txt`,
`music_test.txt`, `sound_test.txt` - and the name fields of
`src/res/data/units.txt`, `structures.txt`, `houses.txt`, `actions.txt`.
`charset.txt` is notes only: which characters the cartridge's fonts have.
`port.txt` holds the port's own strings, for screens the cartridge does
not have (the start-up log's, the intro screen's words, in Russian, and
REDEFINE KEYS) - the only words not the cartridge's.  Cyrillic is only
for the start-up screens' font, `FA_FONT_INTRO`: `src/res/art/ui/font_cyr.txt` draws the
letters Latin has no shape for and aliases the rest, and
`tools/font_cyr.py` (which `dune_data.py` and `dune_front.py` import)
encodes a drawn letter as `$80 + n` - glyph n once the text routine
masks it with `$7F`.  `python3 tools/font_cyr.py --preview F.png TEXT`
shows it.

```
@title_options          "OPTIONS"          ; $017403 menu_title $01782A
@some_long_one [attr=value]
lines of text
@end
```

Escapes: `\n` a new line, `\"`, `\\`, `\xNN` a byte, `{cN}` switch to
colour N.  The comment after `;` is where the cartridge keeps the string
and who prints it - keep it when you change the words.

## What the build makes of them

`tools/dune_data.py` writes `build/gen/text.inc`, assembled into the text
pages (`PG_TEXT`, 37-38, read through window 1):

- a string is **ASCII, ended by `$FF`**, as the cartridge keeps it; `$0A`
  is a new line and `$FE n` switches to colour n;
- `txt_<group>_<id>` is each string's label, `txt_<group>` an index table
  of (address word, page byte), `txt_<group>_<attr>` a value per string,
  `TXT_<GROUP>_COUNT` how many.

A new `@id` in a file becomes a new label at the next build; the code
refers to it by name.

## Drawing

The front end's library (`src/front/front.asm`, also used by the panels
through `FCALL`) draws text into the background copy of the screen:

| | |
|---|---|
| `fe_ink` | A = the font (`FA_` of `font8`, `font_menu`, `font_score`), D, E, C = the pens of its three inks (the third is the shadow) |
| `fe_text` / `fe_textn` | HL = a string in reach, B = column, C = y |
| `fe_str_at` | HL = a string's address, A = its page (bit 7: centre it in 12 columns from B) - for other banks |
| `FE_STR label` / `FE_TXT table` | a text.inc string, or entry A of a group, copied into `fe_strbuf` |
| `fe_print_wrapped` | the mentat's box: lines of up to 36 characters broken at spaces |

The battle's HUD has no text: the credits counter is sprite frames of
digits.

## The fonts

Three sheets in `src/res/art/ui/` - `font8.png`, `font_menu.png`,
`font_score.png` - cut from the cartridge by `tools/sega/port_ui.py`: 16 x 8
glyphs of 8x8, glyph n is character n, pen 0 transparent, each glyph
carrying its own shadow pens.  `tools/dune_front.py` stores them 2 bits a
pixel.  Both of the cartridge's own fonts cover printable ASCII, `$20`-`$7E`;
lower case draws as small capitals.  A translation that needs other
characters needs glyphs in those sheets, and the sheets come from the
cartridge - so that is a decision to make first, not a string to type.
