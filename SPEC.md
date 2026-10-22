# TT File Format, version 0.1 (draft)

Sound segments with their full metadata, inside a standard WAV file.

Status: public draft, open for comments. Details may still change before version 1.0; the open questions are
listed in section 12. The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be read as in RFC 2119.

Revisions: 2026-10-22, draft 0.1, with reader rules and the summary rule completed from a first interoperability
test (Appendix B).

## 1. Purpose

A TT file is a standard WAV file that holds several sounds (segments), each with its own name and its own
metadata, at the same level of detail as a separate file would have. The format is built so that:

1. every program plays a TT file as an ordinary WAV;
2. every program that reads WAV markers sees each segment as a named region;
3. a program that implements this specification can list and index each segment as its own sound, with all its
   metadata, and open the file directly at that segment;
4. a TT file can be split back into separate files, each with its name, its metadata and, when recorded, its
   original timecode.

A TT file adds no new container and no new file extension. It combines chunks that already exist (RIFF `cue `,
`LIST/adtl`, `bext`, `iXML`) and defines one new iXML object, the segment list.

## 2. Terms

- **Segment**: a range of sample frames of the file, with its metadata. Segments MAY overlap.
- **Writer**: a program that creates a TT file or changes its segments.
- **Rewriter**: a program that rewrites the file for another reason (for example to change file-level metadata)
  without changing the audio.
- **Reader**: a program that reads the segments.
- **Frame**: one sample frame (one sample per channel), counted from the first frame of the `data` chunk.

## 3. Layers

| Layer | Carrier | Read by | Role |
|---|---|---|---|
| Audio | `fmt ` + `data` (RF64 / BW64 `ds64` beyond 4 GB) | every program | the sounds, end to end or in one recording |
| File-level summary | `bext`, `LIST/INFO`, iXML `USER` / `ASWG` / `NOTE` | library tools | makes the TT file findable by any of its sounds in tools that only index files |
| Marker mirror | `cue ` + `LIST/adtl` (`labl`, `note`, `ltxt`) | editors, DAWs, library tools | each segment visible as a named region |
| Segment list | iXML `TT_SEGMENT_LIST` | programs that implement this spec | the reference copy: every segment with all its data |
| XMP mirror (optional) | `_PMX` (XMP `xmpDM:Tracks`) | Adobe tools, REAPER | named markers with key/value pairs |

The segment list is the reference. The marker mirror and the XMP mirror are derived from it.

## 4. Audio and file

- The file MUST be a valid RIFF/WAVE file, or an RF64/BW64 file when it is larger than 4 GB.
- The file name extension MUST stay `.wav`.
- PCM (format tag 1 or WAVE_FORMAT_EXTENSIBLE with PCM) and IEEE float are allowed. Every segment of a file
  shares the file's format.

## 5. Segment list (normative)

The segment list is an element `TT_SEGMENT_LIST` placed directly under the root `BWFXML` element of the iXML
chunk. It follows the iXML conventions: UTF-8 XML, upper-case element names, values as element text, no
attributes. Numbers are written in decimal without separators; decimals use a dot.

```
BWFXML
  ...                      (file-level iXML: IXML_VERSION, SPEED, USER, ASWG, NOTE...)
  TT_SEGMENT_LIST
    TT_VERSION             required   "0.1"
    WRITER                 optional   program and version that last wrote the list
    SAMPLE_RATE            required   frames per second of the data chunk
    TOTAL_FRAMES           required   frames in the data chunk when the list was written
    AUDIO_SHA256           recommended  SHA-256 (hex, lower case) of the data chunk payload when the list was written
    SEGMENT_COUNT          required   number of TT_SEGMENT elements
    TT_SEGMENT             one per segment, in ascending START_SAMPLE order
```

### 5.1 `TT_SEGMENT`

| Element | Required | Content |
|---|---|---|
| `SEGMENT_ID` | yes | UUID, text form, lower case. Unique in the file and kept unchanged by every later rewrite. |
| `CUE_ID` | yes | ID of the cue point that mirrors this segment (section 6), or 0 when there is none. |
| `START_SAMPLE` | yes | First frame of the segment. 64-bit. |
| `LENGTH_SAMPLES` | yes | Length in frames, at least 1. 64-bit. |
| `NAME` | yes | Display name of the sound, UTF-8: the name a split file would get, without extension. |
| `USER` | no | Same children as a file-level iXML `USER` object (upper-case tags as used by library tools: `CATID`, `CATEGORY`, `SUBCATEGORY`, `CATEGORYFULL`, `FXNAME`, `DESCRIPTION`, `KEYWORDS`, `CREATORID`, `SOURCEID`, `LIBRARY`...), with this segment's values. |
| `ASWG` | no | Same children as the Sony ASWG iXML object (ASWG-G006, version 1.1), with this segment's values. |
| `FIELD_LIST` | no | Any other field, as `FIELD` elements, each with a `NAME` and a `VALUE`. |
| `ORIGIN` | no | Where the segment came from (section 5.2). |
| `STATUS` | no | `accepted`, `proposed` or `rejected`. Absent means `accepted`. |
| `CONFIDENCE` | no | 0.0 to 1.0, for a segment found by an analysis. |
| other | no | Elements of a single program, named with that program's prefix (for example `AUDIOCRUCIBLE_LANE`). |

The metadata of a segment is written exactly like the metadata of a file (`USER`, `ASWG`), so a program that
already reads file-level iXML can read a segment with the same code.

### 5.2 `ORIGIN`

| Element | Content |
|---|---|
| `FILENAME` | Name of the source file, without its folder. |
| `START_SAMPLE`, `LENGTH_SAMPLES` | Range taken from the source, in source frames. |
| `SAMPLE_RATE`, `BIT_DEPTH`, `CHANNELS`, `FORMAT` | Format of the source (`FORMAT`: `wav`, `flac`, `aiff`, `wavpack`, `mp3`...). |
| `TIME_REFERENCE` | BWF TimeReference of the source (frames since midnight at the source rate), so that a split can give the sound back its original timecode. |
| `CONVERSION` | `none` (bytes copied), `exact` (lossless change, for example 16 to 24 bits or mono to every channel), `lossy` (resampling, dither, downmix or a lossy codec). |
| `CONVERSION_NOTE` | Free text, for example `44100 Hz to 48000 Hz`. |
| `CHUNK_LIST` | Verbatim copies of the source's metadata chunks, as `CHUNK` elements with `CHUNK_ID` (four characters) and `DATA_BASE64`. With them, a split can restore every original chunk byte for byte. |

## 6. Marker mirror (normative)

For every segment whose `CUE_ID` is not 0:

- one cue point: `dwName` = `CUE_ID`, `dwPosition` = `dwSampleOffset` = `START_SAMPLE`, `fccChunk` = `data`,
  `dwChunkStart` = `dwBlockStart` = 0;
- in `LIST/adtl`: a `labl` with a short name (for example the FXName), a `note` with the description, and an
  `ltxt` with purpose `rgn ` and `dwSampleLength` = `LENGTH_SAMPLES` (other fields 0, no text).

Rules:

- `labl` and `note` texts SHOULD be ASCII, at most 255 bytes, NUL-terminated: the RIFF specification does not
  define their character set and programs read them differently. The full UTF-8 name is in `NAME`.
- Inside `LIST/adtl`, every `labl` SHOULD come first, then every `note`, then every `ltxt`: some readers stop
  reading labels at the first sub-chunk that is not a `labl` (observed with ffmpeg).
- `cue ` and `LIST/adtl` SHOULD be placed before `data`.
- A segment that starts at or beyond frame 2^32 - 1 has `CUE_ID` = 0 and no cue point (cue offsets are 32-bit).
- Cue points that are not segments (markers from other programs) MAY exist. They MUST be kept, and their IDs
  MUST NOT be used as the `CUE_ID` of a segment.
- Readers MUST find `cue ` and `LIST/adtl` wherever they are in the file, before or after `data`, and MUST read
  every `labl`, `note` and `ltxt` wherever it is inside `LIST/adtl`: programs that add a marker may move the `cue `
  chunk after `data` and append the new `labl` after the others (observed, Appendix B).

Some programs ignore `ltxt` and treat each marker as the start of a segment that runs to the next marker
(informative). In such programs the silence between two sounds is added to the first one, and every other marker
(for example one added by the user) also starts a segment.

## 7. File-level summary (normative)

Library tools that index only file-level metadata MUST still find a TT file through any of its sounds:

- the file-level description SHOULD name every segment (for example `4 sounds: Door Slam, Door Creak, ...`).
  It SHOULD be written twice: in full in the iXML `USER` `DESCRIPTION`, and as long as it fits in the `bext`
  Description (256 bytes, ASCII as EBU Tech 3285 requires: writers SHOULD transliterate, for example é to e,
  rather than replace characters). Some library tools display only the `bext` Description while their search also
  reads the iXML `USER` object (observed, Appendix B);
- the file-level keywords SHOULD be the union of the segments' keywords;
- the file-level CatID and FXName describe the TT file as a whole (the writer's choice, for example the most
  frequent values).

## 8. Integrity and editing (normative)

- **Writer**: when it writes or changes the segment list, it MUST rewrite the marker mirror (and the XMP mirror
  when present) and update `SEGMENT_COUNT`, `TOTAL_FRAMES`, `SAMPLE_RATE` and, when written, `AUDIO_SHA256`.
- **Rewriter** (audio unchanged): it MUST copy `TT_SEGMENT_LIST` unchanged, including the elements it does not
  know; it MUST keep the cue points and `LIST/adtl` entries of the segments; it SHOULD keep the order of the
  chunks.
- **Audio editor** (the `data` chunk changes): it MUST either update the segment list (positions, lengths,
  `TOTAL_FRAMES`, `AUDIO_SHA256`) or remove it together with the cue points it mirrors. It MUST NOT leave a
  segment list that no longer matches the audio.
- **Reader**:
  - it MUST ignore the elements it does not know;
  - when `SAMPLE_RATE`, `TOTAL_FRAMES` or `AUDIO_SHA256` do not match the file, it MUST report that the
    segments may be wrong (the audio changed after they were written) and MUST NOT present them as exact;
  - when the cue point of a segment is at another position than `START_SAMPLE`, it SHOULD report the segment
    as moved by another program, and MUST NOT silently change either side.

## 9. Referencing a segment

A search result, a playlist or another program refers to a segment as `<file>#tt=<SEGMENT_ID>`, for example
`DOORWood_TT_Doors_ACT_SELF.wav#tt=3f2b9c1e-5d4a-4e8b-9f1a-2c7d6e5b4a3f`. A program that receives such a
reference opens the file and selects the frames `START_SAMPLE` to `START_SAMPLE + LENGTH_SAMPLES`.

For generic players, the same range MAY also be given as a W3C Media Fragments time range,
`#t=<start>,<end>` in seconds.

Expected behaviour of a library tool that implements this specification (informative):

- each segment is indexed as its own search result, with all its fields;
- opening a result opens the TT file at that segment;
- dragging a result to a DAW transfers only that segment;
- a split writes each segment as a separate WAV with its `NAME`, its metadata (`USER`, `ASWG`, `FIELD_LIST`, or
  the original chunks of `ORIGIN/CHUNK_LIST`) and, when `ORIGIN/TIME_REFERENCE` is given, its original timecode.

## 10. Optional XMP mirror

A writer MAY add an XMP packet (`_PMX` chunk) whose `xmpDM:Tracks` holds one marker per segment: `xmpDM:name`,
`xmpDM:startTime` and `xmpDM:duration` in frames (track `xmpDM:frameRate` = `f<sample rate>`), `xmpDM:comment`,
and the segment's fields as `xmpDM:cuePointParams` key/value pairs. It serves Adobe Audition / Premiere and
REAPER, which read XMP markers. No standard reconciles XMP markers with cue points: a writer that adds them MUST
keep them identical to the segment list.

## 11. Example

Chunk layout: `RIFF/WAVE`: `fmt `, `bext`, `iXML`, `cue `, `LIST/adtl`, `LIST/INFO`, `data`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<BWFXML>
  <IXML_VERSION>2.10</IXML_VERSION>
  <USER>
    <CATID>DOORWood</CATID>
    <FXNAME>TT Doors</FXNAME>
    <DESCRIPTION>2 sounds: Door Slam, Porte d'entrée qui grince</DESCRIPTION>
    <KEYWORDS>door, slam, wood, creak, hinge</KEYWORDS>
  </USER>
  <TT_SEGMENT_LIST>
    <TT_VERSION>0.1</TT_VERSION>
    <WRITER>AudioCrucible 1.0.13</WRITER>
    <SAMPLE_RATE>48000</SAMPLE_RATE>
    <TOTAL_FRAMES>264000</TOTAL_FRAMES>
    <AUDIO_SHA256>9f2c...e41a</AUDIO_SHA256>
    <SEGMENT_COUNT>2</SEGMENT_COUNT>
    <TT_SEGMENT>
      <SEGMENT_ID>3f2b9c1e-5d4a-4e8b-9f1a-2c7d6e5b4a3f</SEGMENT_ID>
      <CUE_ID>1</CUE_ID>
      <START_SAMPLE>0</START_SAMPLE>
      <LENGTH_SAMPLES>96000</LENGTH_SAMPLES>
      <NAME>DOORWood_Door Slam_ACT_SELF</NAME>
      <USER>
        <CATID>DOORWood</CATID>
        <FXNAME>Door Slam</FXNAME>
        <DESCRIPTION>Heavy wooden door slammed hard, short tail</DESCRIPTION>
        <KEYWORDS>door, slam, wood</KEYWORDS>
      </USER>
      <ORIGIN>
        <FILENAME>DOORWood_Door Slam_ACT_SELF.wav</FILENAME>
        <START_SAMPLE>0</START_SAMPLE>
        <LENGTH_SAMPLES>96000</LENGTH_SAMPLES>
        <SAMPLE_RATE>48000</SAMPLE_RATE>
        <TIME_REFERENCE>1849584000</TIME_REFERENCE>
        <CONVERSION>none</CONVERSION>
      </ORIGIN>
    </TT_SEGMENT>
    <TT_SEGMENT>
      <SEGMENT_ID>8a1d...</SEGMENT_ID>
      <CUE_ID>2</CUE_ID>
      <START_SAMPLE>120000</START_SAMPLE>
      <LENGTH_SAMPLES>144000</LENGTH_SAMPLES>
      <NAME>DOORWood_Porte d'entrée qui grince_ACT_SELF</NAME>
      ...
    </TT_SEGMENT>
  </TT_SEGMENT_LIST>
</BWFXML>
```

Marker mirror of the same file: cue 1 at 0, cue 2 at 120000; `labl` 1 = `Door Slam`, `labl` 2 =
`Porte d'entree qui grince` (ASCII); `note` 1 and 2 = the descriptions (ASCII); `ltxt` 1 = 96000 frames,
`ltxt` 2 = 144000 frames.

## 12. Open questions

1. **Carrier**: iXML only, or also a dedicated RIFF chunk carrying the same XML (candidate ID `ttsg`), for
   programs that drop unknown iXML elements when they rewrite a file. To be decided from tests in more programs
   (Appendix B; the test kit is in `kit/`).
2. **Analysis data**: lanes, groups, frequency bands and species as common elements, or left to each program?
3. **Other formats**: FLAC, AIFF, BW64 with ADM, and a sidecar file for formats without room for metadata.
4. **Registration**: propose the object to the iXML committee, as Sony did for its ASWG object (added to the
   iXML specification in revision 3.01, October 2021).

Decided: the name (TT File Format, elements `TT_SEGMENT_LIST` and `TT_SEGMENT`); the original chunks of a segment
(`ORIGIN/CHUNK_LIST`) stay in version 1 as an option; the licences (section 13).

## 13. Licence

This specification is published under the Creative Commons Attribution 4.0 International licence (CC BY 4.0):
<https://creativecommons.org/licenses/by/4.0/>. The code of the test kit (`kit/`) is published under the MIT
licence. Copyright 2026 Nextale Audio.

## Appendix A. Mapping from AudioCrucible 1.0.12

AudioCrucible 1.0.12 writes `<AUDIOCRUCIBLE_TAGS version="1">` (attributes `app`, `sample_rate`, `tc_base`,
`fps`), with one `<TAG>` per segment. Readers SHOULD accept it and map it as follows:

| AudioCrucible 1.0.12 | This specification |
|---|---|
| `TAG@uid` | `SEGMENT_ID` |
| `TAG@cue_id` | `CUE_ID` |
| `TAG@start_sample` | `START_SAMPLE` |
| `TAG@end_sample` minus `TAG@start_sample` | `LENGTH_SAMPLES` |
| `TAG/NAME` | `NAME` |
| `TAG/CATID`, `CATEGORY`, `SUBCATEGORY`, `FXNAME`, `DESCRIPTION`, `KEYWORDS` | the same tags in `USER` |
| `TAG/COLUMN@name` + text | `FIELD_LIST/FIELD` (`NAME`, `VALUE`), or `USER` / `ASWG` when the name is a known field |
| `TAG/SOURCE@file`, `@start_sample`, `@end_sample`, `@sample_rate` | `ORIGIN` (`FILENAME`, `START_SAMPLE`, `LENGTH_SAMPLES`, `SAMPLE_RATE`) |
| `TAG@status`, `@confidence` | `STATUS`, `CONFIDENCE` |
| `TAG@lane`, `@low_hz`, `@high_hz`, `@group`, `@occurrences`, `TAG/SPECIES` | program-specific elements (`AUDIOCRUCIBLE_...`), see question 4 |

## Appendix B. Interoperability observed (informative)

Sample files and checker: `kit/make_tt_spec_samples.py` (each candidate carrier holds its own search word; `--check`
compares a file rewritten by a program with the original). Results so far:

| Program | Markers shown | Region end | Segments | Search reads | After the program added a marker |
|---|---|---|---|---|---|
| Soundly (2026-10-22) | yes, with their `labl` name; `note` not shown | not shown (`ltxt` ignored) | Segments mode: each marker to the next one | file-level metadata only (`bext`, iXML `USER`); not `labl`, `note`, the segment list, the `ttsg` chunk or XMP markers | audio, `bext`, `LIST/INFO`, iXML (segment list included), `ttsg` and `_PMX` kept byte for byte; existing cue points and `LIST/adtl` entries kept; new cue point with a free ID, its `labl` appended after the `note` and `ltxt` entries; `cue ` chunk moved after `data` |

Other programs (Soundminer, BaseHead, REAPER, iZotope RX, Pro Tools, Nuendo / WaveLab) are not tested yet.
Results for them are welcome: see `kit/TEST_PROTOCOL.md`.

## Appendix C. Alternatives considered (informative)

We found no format or program that keeps the full metadata of each sound of a multi-sound WAV file inside the file
(survey of sound library managers, editors, DAWs, game engines and formats, October 2026; corrections are welcome).
The closest carriers, and why the segment list uses iXML instead:

| Carrier | What it holds per segment | Why not the reference carrier |
|---|---|---|
| `cue ` + `LIST/adtl` (`labl`, `note`, `ltxt`) | a name, a note, a length | no fields; kept here as the marker mirror (section 6) |
| `LIST/adtl` `file` sub-chunk (RIFF, 1991) | any data attached to a cue point, with a media type | no current reader known |
| XMP `xmpDM:markers` (`_PMX`) | name, start, duration, comment, key/value pairs | used by Adobe tools and REAPER, not by sound library managers; kept as an optional mirror (section 10) |
| iXML `SYNC_POINT_LIST` | start, duration, one comment | one text field, very few readers |
| Pro Tools Clip Definitions | clip pointers | proprietary and undocumented |
| BW64 ADM (`axml`) | audio objects with start, duration and name | made for object-based broadcast audio |
| Separate files (marker lists, Audacity labels, REAPER region lists, JAMS, OTIO, SFZ) | anything | lost when the WAV file is copied alone |

iXML is read by sound library tools at file level, and in the first test the segment list survived a rewrite by a
program that did not know it (Appendix B). Writing each segment's metadata like a file's (`USER`, `ASWG`) lets
those tools reuse the code they already have.
