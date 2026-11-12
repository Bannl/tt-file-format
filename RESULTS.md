# Interoperability results

Made with the kit (`kit/`): see [kit/TEST_PROTOCOL.md](kit/TEST_PROTOCOL.md). Results for other programs are
welcome as issues.

| Program | A. Markers shown | A. Region end | B. Search reads | C. After the program added a marker |
|---|---|---|---|---|
| Soundly (tested 2026-10-22, Windows) | yes, with their name (`labl`); notes not shown | not shown (`ltxt` ignored) | file-level metadata only (`bext`, iXML `USER`) | everything kept, segment list included |
| Soundminer | not tested |  |  |  |
| BaseHead | not tested |  |  |  |
| REAPER | not tested |  |  |  |
| iZotope RX | not tested |  |  |  |
| Pro Tools | not tested |  |  |  |
| Nuendo / WaveLab | not tested |  |  |  |

## Ogg files

| Program | As | Result |
|---|---|---|
| ffmpeg 6.0 (ffprobe), 2026-11-04 | reader | lists the chapters of the three Ogg samples (5, 5 and 400) and decodes them without error |
| ffmpeg 6.0 (ffprobe), 2026-11-12 | reader | reads three digits after `CHAPTER`: `CHAPTER1000NAME` to `CHAPTER1009NAME` rename chapter 100, `CHAPTER1000` is ignored; reads the 2.9 MB comment headers of the Rìcháng voice files without error |
| ffmpeg 6.0, `-c copy`, 2026-11-12 | rewriter | keeps the segment list, the summary and the audio packets; drops every chapter (to Ogg Vorbis), or numbers them again from `CHAPTER000` and writes those whose millisecond part is 500 or more one second late (to Ogg Opus); 1,000 chapters at most |
| [Rìcháng](https://github.com/Bannl/Richang) voice files, 2026-11-11 | writer and reader | 72 files of draft 0.2, all `RESULT PASS` with no warning; details in [CASE_STUDY_RICHANG.md](CASE_STUDY_RICHANG.md) |
| [Rìcháng](https://github.com/Bannl/Richang) voice files, 2026-11-12 | writer and reader, draft 0.3 | 36 Ogg Opus files with a segment table, all `RESULT PASS` with no warning, 5.2 % lighter than their reference weight; details in [CASE_STUDY_RICHANG.md](CASE_STUDY_RICHANG.md) |
| ffmpeg 6.0, `-c copy`, 2026-11-12 | rewriter, draft 0.3 | keeps `TT_SEGMENT_TABLE` byte for byte; joins comments of the same name with `;` (five `TT_SEGMENT` comments became one); drops data placed after the comments of `OpusTags` |
| ffmpeg 6.0, 2026-11-12 | reader of segments cut by packet copy | Ogg Opus: decoded to the exact frames (75 segments of 75); Ogg Vorbis: the segment intact, but up to one block of frames too many at the start (the granule position of the first page is not applied) |

Game engines (Unity, Unreal, Godot), audio middleware (FMOD, Wwise) and tag editors are not tested yet.

## Soundly, details

- **Display**: the 5 markers of `tt_v0_full` under the waveform, each with its name, at the right place. Only the
  starts are drawn.
- **Segments mode**: works on the markers of a local file; each segment runs from a marker to the next one (the
  silence after a sound belongs to it, and every other marker also starts a segment).
- **File-level metadata**: the Description, Originator, Reference and Origination date columns come from the
  `bext` chunk; Category and Subcategory come from the iXML `USER` object.
- **Search**: `zorbfile` finds the 3 files, `tt_v0_minimal` included, which has it only in the iXML `USER`
  object: the search reads that object even though the Description column shows the `bext` Description. No other
  word is found: marker names and notes, the segment list, the `ttsg` chunk and the XMP markers are not indexed.
- **After a marker was added** (`RESUME audio=OK fmt=OK bext=OK info=OK ixml_file=OK ixml_list=OK ttsg=OK xmp=OK
  cue=CHANGED adtl=CHANGED order=CHANGED extra=none`): audio, `bext`, `LIST/INFO`, iXML with the segment list,
  `ttsg` and `_PMX` kept byte for byte; the existing cue points and `LIST/adtl` entries kept; the new cue point got
  a free ID and its `labl` was appended after the `note` and `ltxt` entries; the `cue ` chunk moved after `data`.

## Rìcháng

The dubbed voice lines of [Rìcháng](https://github.com/Bannl/Richang), a game to learn Taiwan Mandarin, are the first
Ogg TT files written outside the kit and AudioCrucible (2026-11-11), and the data set of the weight study of draft 0.3:
the files, the method and the results against separate files in WAV, Ogg Vorbis and Ogg Opus are in
[CASE_STUDY_RICHANG.md](CASE_STUDY_RICHANG.md).
