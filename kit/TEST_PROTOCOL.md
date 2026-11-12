# Test protocol for a program

For a given program, find out:

- **A. Display**: does it show each sound of a TT file as a named marker or region?
- **B. Search**: which data does its search read: file-level metadata, marker names, marker notes, the iXML segment
  list, a dedicated chunk, XMP markers?
- **C. Survival**: when it writes into the file (a metadata field, a marker), what is kept?
- **D. Audio edit** (editors only): after the audio is changed, what happens to the segment list?

## 1. Sample files

They are in `samples/`, with `manifest.json` (the expected content). `python make_tt_spec_samples.py` writes them
again and checks itself (`SELFCHECK.txt`); the generator is deterministic, so the files are the same.

| File | Content | Used for |
|---|---|---|
| `tt_v0_full.wav` | 48 kHz / 24-bit / stereo, 7.1 s, 4 sounds and 1 marker of another program. Every candidate carrier: file-level summary (`bext`, `LIST/INFO`, iXML `USER` and `ASWG`), markers (`cue`, `labl`, `note`, `ltxt`), segment list in iXML, the same list in a dedicated chunk `ttsg`, XMP markers (`_PMX`) | A, B, C, D |
| `tt_v0_minimal.wav` | same audio, only what the specification requires: iXML `USER` summary, markers, segment list in iXML | C on a clean file |
| `tt_v0_many.wav` | 48 kHz / 16-bit / mono, 100 s, 400 sounds of 0.2 s | size (300 KB of iXML, 400 markers), deep search |
| `tt_v0_full.ogg` | the audio of `tt_v0_full.wav` in Ogg Vorbis, the same 4 sounds and marker of another program (draft 0.2, section 11): summary comments, chapters, segment list in one comment | A, B, C for Ogg readers |
| `tt_v0_full.opus` | the same in Ogg Opus (48 kHz, pre-skip) | A, B, C for Opus readers |
| `tt_v0_many.ogg` | the audio of `tt_v0_many.wav` in Ogg Vorbis, 400 sounds: about 320 KB of comments before the audio | game engines and middleware: import and play a large comment header |
| `tt_v0_full_table.opus` | `tt_v0_full.opus` with the segment list as a table (draft 0.3, section 11.5): one comment `TT_SEGMENT_TABLE`, a JSON object; the original `bext` chunk of sound 1 deflated (section 5.2) | A, B, C for programs of draft 0.3; tag editors: the table survives a rewrite |
| `tt_v0_many_table.ogg` | `tt_v0_many.ogg` with the list as a table: 92 KB instead of 290 KB | game engines and middleware: the table survives an import |

The 4 sounds of `tt_v0_full.wav` (each one is a tone burst from its exact start to its exact end):

| # | Name | CatID | Start | Length | Tone |
|---|---|---|---|---|---|
| 1 | Door Slam | DOORWood | 0.500 s | 1.2 s | 300 Hz |
| 2 | Porte d'entrée qui grince (UTF-8 in the list, ASCII in the `labl`) | DOORCreak | 2.200 s | 1.6 s | 600 Hz |
| 3 | Latch Click (holds the search words) | DOORHdwr | 4.300 s | 0.8 s | 1200 Hz |
| 4 | Knock Knock | DOORKnck | 5.600 s | 1.0 s | 2400 Hz |

## 2. Search words (B)

Each carrier holds a made-up word that no other carrier holds. If the search of the program finds the word, the
program reads that carrier. No word is a part of another one.

| Word | Where | Found means |
|---|---|---|
| `zorbfile` | file-level summary of the 3 files (`bext`, `LIST/INFO`, iXML `USER` / `ASWG`); in `tt_v0_minimal` only in the iXML `USER` | the search reads file-level metadata (and the iXML `USER` object if `tt_v0_minimal` is found) |
| `zorblabl` | marker name (`labl`) of sound 3 in `tt_v0_full` and `tt_v0_minimal` | the search reads marker names |
| `zorbnote` | marker note (`note`) of sound 3 in `tt_v0_full` and `tt_v0_minimal` | the search reads marker notes |
| `zorbixml` | keywords of sound 3 in the iXML segment list of `tt_v0_full` | the search reads the segment list |
| `zorbchunk` | keywords of sound 3 in the `ttsg` chunk | the search reads that chunk |
| `zorbxmp` | keywords and comment of sound 3 in the XMP markers | the search reads XMP markers |
| `zorbmanylabl` | marker name of sound 398 of `tt_v0_many` | marker names are read deep into a large file |
| `zorbmanyixml` | keywords of sound 397 in the segment list of `tt_v0_many` | a large segment list is read to the end |
| `zorboggfile` | Ogg samples: comments `DESCRIPTION`, `COMMENT` and `KEYWORDS` | the search reads the file-level comments |
| `zorboggchap` | Ogg samples: name of the chapter of sound 3 | the search reads chapter names |
| `zorboggtt` | Ogg samples: keywords of sound 3 in the `TT_SEGMENT_LIST` comment (`TT_SEGMENT_TABLE` in `tt_v0_full_table.opus`) | the search reads the segment list |
| `zorboggmanychap` | `tt_v0_many.ogg` and `tt_v0_many_table.ogg`: chapter name of sound 398 | chapter names are read deep into a large file |
| `zorboggmanylist` | `tt_v0_many.ogg` and `tt_v0_many_table.ogg`: keywords of sound 397 in the segment list | a large list in a comment is read to the end |

## 3. Procedure

1. Work on copies of the sample files.
2. **A and B**: add the copies to the library of the program, open them, look at the markers, search each word.
3. **C**: make one write per copy with the program, for example a description edited and saved into the file, or a
   marker added. Then check the copy:

   ```
   python make_tt_spec_samples.py --check path/to/copy/tt_v0_full.wav
   ```

   Add `--as tt_v0_full.wav` if the program renamed the file. Keep the last line (`RESUME ...`). Lines that start
   with `spec check:` report what the specification asks readers to detect (audio changed after the segment list
   was written, a marker moved by a program).
4. **D** (editors): change the gain of a passage of another copy, save it, check it the same way.

## 4. Reading the RESUME line

| Value | Meaning |
|---|---|
| `OK` | identical bytes |
| `SAME` | rewritten, same content (same segments, same markers, same fields) |
| `CHANGED` | content changed (details above the line) |
| `LOST` | removed |
| `extra=` | chunks added by the program |

Carriers: `audio` (PCM), `fmt`, `bext`, `info` (`LIST/INFO`), `ixml_file` (iXML outside the segment list: `USER`,
`ASWG`, `SPEED`), `ixml_list` (the segment list), `ttsg` (the dedicated chunk), `xmp` (`_PMX`), `cue`, `adtl`
(`labl`, `note`, `ltxt`), `order` (chunks that moved to the other side of `data`).

Ogg files: `stream` (one logical stream, page CRCs), `audio` (the audio packets), `headers` (the identification
and setup packets), `summary` (`TITLE`, `DESCRIPTION`, `COMMENT`, `KEYWORDS`), `chapters` (`SAME`: same times and
names under other numbers), `list` (the `TT_SEGMENT_LIST` comment, or `TT_SEGMENT_TABLE` in the table samples);
`extra=` lists the comments the program added.
A program that re-encodes the file changes `audio`: that is expected, but it must then update or remove the list
(section 11.3).

## 5. Report

Please open an issue with:

```
Program and version:
Operating system:
A. Markers shown with their names (yes / no / partly):
A. End of the regions shown (yes / no):
A. Marker notes shown (yes / no):
B. Words found (and in which files):
C. What the program wrote:
C. RESUME line:
D. RESUME line (editors):
```
