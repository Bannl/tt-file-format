# TT File Format, version 0.3 (draft)

Sound segments with their full metadata, inside a standard WAV or Ogg file.

Status: public draft, open for comments. Details may still change before version 1.0; the open questions are
listed in section 14. The key words MUST, MUST NOT, SHOULD, SHOULD NOT and MAY are to be read as in RFC 2119.

Revisions: 2026-10-22, draft 0.1, with reader rules and the summary rule completed from a first interoperability
test (Appendix B). 2026-11-04, draft 0.2: Ogg files (Vorbis, Opus), section 11. Nothing changes for WAV files: a
WAV file written for draft 0.1 stays valid. 2026-11-10, draft 0.2 amended: an optional file time reference in the
list header (`TIME_REFERENCE`, `TIMECODE_RATE`, `TIMECODE_FLAG`, section 5), the carrier of the timecode of an Ogg
file (section 11.2). Every file written before stays valid. 2026-11-12, draft 0.2 amended again, from the first Ogg
TT files written outside the kit and AudioCrucible (Appendix B): the rounding of chapter times and chapter numbers
of three digits at most (section 11.2), notes on large lists and on playing one segment (section 11.4), stable
segment IDs (section 5.1), an Ogg Opus example (now section 13). Every file written before stays valid, except a
file with chapter numbers of four digits or more (none is known). 2026-11-12, draft 0.3, from a study of the weight
of TT files against the same sounds as separate files (Appendix B): the segment table, a compact form of the list
for Ogg files that keeps every element of every segment (section 11.5); the weight of a TT file (section 12);
original chunks deflated before base64 (section 5.2); silence between sounds and splitting without decoding
(section 11.4). Every file written before stays valid.

## 1. Purpose

A TT file is a standard WAV file, or a standard Ogg file (section 11), that holds several sounds (segments), each
with its own name and its own metadata, at the same level of detail as a separate file would have. The format is
built so that:

1. every program plays a TT file as an ordinary WAV or Ogg file;
2. every program that reads markers (WAV cue points, Ogg chapters) sees each segment by name;
3. a program that implements this specification can list and index each segment as its own sound, with all its
   metadata, and open the file directly at that segment;
4. a TT file can be split back into separate files, each with its name, its metadata and, when recorded, its
   original timecode.

A TT file adds no new container and no new file extension. It combines chunks that already exist (RIFF `cue `,
`LIST/adtl`, `bext`, `iXML`) and defines one new iXML object, the segment list. In an Ogg file, the same list is a
Vorbis comment (section 11).

## 2. Terms

- **Segment**: a range of sample frames of the file, with its metadata. Segments MAY overlap.
- **Writer**: a program that creates a TT file or changes its segments.
- **Rewriter**: a program that rewrites the file for another reason (for example to change file-level metadata)
  without changing the audio.
- **Reader**: a program that reads the segments.
- **Frame**: one sample frame (one sample per channel), counted from the first frame of the `data` chunk (Ogg
  files: section 11.1).

## 3. Layers

| Layer | Carrier | Read by | Role |
|---|---|---|---|
| Audio | `fmt ` + `data` (RF64 / BW64 `ds64` beyond 4 GB) | every program | the sounds, end to end or in one recording |
| File-level summary | `bext`, `LIST/INFO`, iXML `USER` / `ASWG` / `NOTE` | library tools | makes the TT file findable by any of its sounds in tools that only index files |
| Marker mirror | `cue ` + `LIST/adtl` (`labl`, `note`, `ltxt`) | editors, DAWs, library tools | each segment visible as a named region |
| Segment list | iXML `TT_SEGMENT_LIST` | programs that implement this spec | the reference copy: every segment with all its data |
| XMP mirror (optional) | `_PMX` (XMP `xmpDM:Tracks`) | Adobe tools, REAPER | named markers with key/value pairs |

The segment list is the reference. The marker mirror and the XMP mirror are derived from it. Ogg files carry the
same layers in Vorbis comments (section 11).

## 4. Audio and file (WAV files)

- The file MUST be a valid RIFF/WAVE file, or an RF64/BW64 file when it is larger than 4 GB.
- The file name extension MUST stay `.wav`.
- PCM (format tag 1 or WAVE_FORMAT_EXTENSIBLE with PCM) and IEEE float are allowed. Every segment of a file
  shares the file's format.

## 5. Segment list (normative)

The segment list is an element `TT_SEGMENT_LIST` placed directly under the root `BWFXML` element of the iXML
chunk (in an Ogg file: the value of a comment, section 11.2). It follows the iXML conventions: UTF-8 XML,
upper-case element names, values as element text, no attributes. Numbers are written in decimal without
separators; decimals use a dot.

```
BWFXML
  ...                      (file-level iXML: IXML_VERSION, SPEED, USER, ASWG, NOTE...)
  TT_SEGMENT_LIST
    TT_VERSION             required   lowest draft that defines what the file uses: "0.1" (WAV), "0.2" (Ogg),
                                      "0.3" (segment table, deflated original chunks)
    WRITER                 optional   program and version that last wrote the list
    SAMPLE_RATE            required   frames per second of the data chunk
    TOTAL_FRAMES           required   frames in the data chunk when the list was written
    AUDIO_SHA256           recommended  SHA-256 (hex, lower case) of the data chunk payload when the list was written
    TIME_REFERENCE         optional   time of frame 0: frames since midnight at SAMPLE_RATE (as the bext TimeReference)
    TIMECODE_RATE          optional   timecode rate of that time, as iXML SPEED writes it: "25/1", "30000/1001"
    TIMECODE_FLAG          optional   "NDF", or "DF" (drop frame), as iXML SPEED writes it
    SEGMENT_COUNT          required   number of TT_SEGMENT elements
    TT_SEGMENT             one per segment, in ascending START_SAMPLE order
```

The file time reference (`TIME_REFERENCE`, with `TIMECODE_RATE` and `TIMECODE_FLAG`) tells when the first frame
was recorded or where it sits on a timeline, so that a split can give each sound its timecode. In a WAV file the
`bext` TimeReference stays its carrier (and iXML `SPEED` its rate): a list that also has `TIME_REFERENCE` MUST give
the same value. In an Ogg file, which has no `bext`, the list is its carrier (section 11.2).

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

`SEGMENT_ID` is what a reference to the segment holds (section 9). A random UUID (version 4) suits a segment that a
program creates once. A program that builds a file again from the same sources, such as a sound bank made by a
script, MAY instead derive each `SEGMENT_ID` from a key of the sound: a name-based UUID (version 5, RFC 9562) of
that key, in a namespace UUID of the program's own. The references then stay valid from one build to the next. The
key MUST be unique in the file, and SHOULD name the sound rather than its place: a position (the third line of a
scene) designates another sound as soon as a line is inserted before it. In a segment table (section 11.5), IDs
derived from the `NAME` of each segment MAY be left out, the namespace written once.

### 5.2 `ORIGIN`

| Element | Content |
|---|---|
| `FILENAME` | Name of the source file, without its folder. |
| `START_SAMPLE`, `LENGTH_SAMPLES` | Range taken from the source, in source frames. |
| `SAMPLE_RATE`, `BIT_DEPTH`, `CHANNELS`, `FORMAT` | Format of the source (`FORMAT`: `wav`, `flac`, `aiff`, `wavpack`, `mp3`...). |
| `TIME_REFERENCE` | BWF TimeReference of the source (frames since midnight at the source rate), so that a split can give the sound back its original timecode. |
| `CONVERSION` | `none` (bytes copied), `exact` (lossless change, for example 16 to 24 bits or mono to every channel), `lossy` (resampling, dither, downmix or a lossy codec). |
| `CONVERSION_NOTE` | Free text, for example `44100 Hz to 48000 Hz`. |
| `CHUNK_LIST` | Verbatim copies of the source's metadata chunks, as `CHUNK` elements with `CHUNK_ID` (four characters) and either `DATA_BASE64` (the body of the chunk in base64, RFC 4648) or `DATA_DEFLATE_BASE64` (the body as a zlib stream, RFC 1950, in base64). With them, a split can restore every original chunk byte for byte. Writers SHOULD use the shorter of the two: deflated, the XMP packets (`_PMX`) of a test library took 15 % of their bytes, its `bext` chunks 18 % (Appendix B). A list that uses `DATA_DEFLATE_BASE64` has `TT_VERSION` 0.3. Readers MUST read both forms and MAY refuse a chunk that inflates beyond 64 MiB; a reader that finds neither form in a `CHUNK` leaves that chunk out, and does not restore it empty. |

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
  when present) and update `SEGMENT_COUNT`, `TOTAL_FRAMES`, `SAMPLE_RATE` and, when written, `AUDIO_SHA256`. It
  MUST keep the file time reference of the list it replaces (`TIME_REFERENCE`, `TIMECODE_RATE`, `TIMECODE_FLAG`)
  unless it sets a new one; when it changes the `bext` TimeReference of a WAV file, it MUST update the list's
  `TIME_REFERENCE` too, or remove it.
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
  the original chunks of `ORIGIN/CHUNK_LIST`) and, when `ORIGIN/TIME_REFERENCE` is given, its original timecode;
  otherwise, when the file has a time reference (`bext`, or the list's `TIME_REFERENCE` in an Ogg file), that time
  plus the segment's `START_SAMPLE`.

## 10. Optional XMP mirror

A writer MAY add an XMP packet (`_PMX` chunk) whose `xmpDM:Tracks` holds one marker per segment: `xmpDM:name`,
`xmpDM:startTime` and `xmpDM:duration` in frames (track `xmpDM:frameRate` = `f<sample rate>`), `xmpDM:comment`,
and the segment's fields as `xmpDM:cuePointParams` key/value pairs. It serves Adobe Audition / Premiere and
REAPER, which read XMP markers. No standard reconciles XMP markers with cue points: a writer that adds them MUST
keep them identical to the segment list.

## 11. Ogg files (normative)

Ogg Vorbis and Ogg Opus are the usual compressed formats of game audio. A TT file can also be an Ogg file: the
segment list keeps the content of section 5, only its carriers change. An Ogg file has no chunks, but Vorbis
comments: `FIELD=value` pairs in UTF-8, of any length (Opus uses the same structure in its `OpusTags` header).

### 11.1 Audio and frames

- The file MUST hold one logical bitstream, Vorbis or Opus: no chaining, no multiplexing. Extensions: `.ogg` for
  Vorbis, `.opus` (or `.ogg`) for Opus.
- Frames are decoded samples per channel, counted from the first sample a decoder returns: for Vorbis, the sample
  at granule position 0; for Opus, the first sample after the pre-skip of the `OpusHead` header, at 48000 Hz
  whatever the input rate written in `OpusHead`.
- `SAMPLE_RATE` is the decoded rate (Vorbis: the rate of the identification header; Opus: 48000). `TOTAL_FRAMES`
  is the number of decoded frames: for Vorbis the granule position of the last page, for Opus that granule
  position minus the pre-skip. `TT_VERSION` is `0.2`, or `0.3` when the file uses a segment table (section 11.5) or
  deflated original chunks (section 5.2).

### 11.2 Carriers

| Layer | Carrier in an Ogg file | Read by |
|---|---|---|
| File-level summary | comments `TITLE`, `DESCRIPTION`, `COMMENT`, keywords | players, tag editors, library tools |
| Marker mirror | comments `CHAPTERnnn` and `CHAPTERnnnNAME` | ffmpeg and the players built on it |
| Segment list | one comment `TT_SEGMENT_LIST` | programs that implement this spec |
| Segment list, compact form | one comment `TT_SEGMENT_TABLE` (section 11.5) | programs that implement this spec |
| File time reference | `TIME_REFERENCE`, `TIMECODE_RATE`, `TIMECODE_FLAG` of the segment list (section 5) | programs that implement this spec |

- **Segment list**: the value of the comment `TT_SEGMENT_LIST` is the element `TT_SEGMENT_LIST` of section 5 as
  UTF-8 XML, without XML declaration. It SHOULD be written on one line: some tag editors mishandle values with
  line breaks. A file MUST NOT hold more than one such comment. From draft 0.3 the list MAY instead be written as a
  table (section 11.5); a file holds one form, not both.
- **Marker mirror**: each segment SHOULD have a chapter, that is a pair of comments `CHAPTERnnn=HH:MM:SS.mmm` (its
  start, see chapter times below) and `CHAPTERnnnNAME=<name>` (a short name, UTF-8), nnn on three digits from 001:
  the common Ogg chapter convention. The segment's `CUE_ID` is the number nnn, or 0 when it has no chapter.
  Chapters have no end: the length is only in the list. Writers SHOULD number all chapters in time order; chapters
  that are not segments MUST be kept (their numbers MAY change). Readers MUST find the chapter of a segment through
  its `CUE_ID` and MUST NOT expect time order.
- **Chapter times**: `START_SAMPLE` × 1000 / `SAMPLE_RATE` milliseconds, rounded to the nearest millisecond. A start
  exactly on a half millisecond MAY be rounded either way: the kit rounds it to the even millisecond (as Python's
  `round`), JavaScript's `Math.round` and C++'s `std::round` round it up. Validators MUST accept both. In integers,
  with q the whole part of (`START_SAMPLE` × 1000) / `SAMPLE_RATE` and r the remainder, the time is q + 1 when
  2r > `SAMPLE_RATE`, q when 2r < `SAMPLE_RATE`, either when 2r = `SAMPLE_RATE`. Readers SHOULD take a chapter at
  most 1 ms away from `START_SAMPLE` as being at the start of its segment (section 8).
- **Chapter numbers**: three digits, 001 to 999, chapters of other programs included. Writers MUST NOT write longer
  numbers: ffmpeg reads the first three digits only, so `CHAPTER1000NAME` renames chapter 100 and `CHAPTER1000` is
  ignored (Appendix B). Beyond 999 chapters, the later segments have none (`CUE_ID` 0): they are in the list only,
  and programs that read only chapters do not see them. When such programs must see every sound, writers SHOULD
  split the sounds into files of at most 999 segments.
- **File-level summary** (section 7): the description in full in `DESCRIPTION`, and the same text in `COMMENT`,
  which many players and tag editors show instead. Vorbis comments have no common keywords field: writers SHOULD
  put the union of the segments' keywords in the field they already use for the keywords of a file (for example
  `KEYWORDS` or `GENRE`).
- **File time reference**: the time of the first decoded frame, when the file has one, is the list's
  `TIME_REFERENCE`, in frames since midnight at `SAMPLE_RATE` (48000 for Opus), with `TIMECODE_RATE` and
  `TIMECODE_FLAG`. Some converters copy the `bext` TimeReference of a WAV file into a `TIME_REFERENCE` comment
  without converting it to the new rate: such a comment is not this carrier, and readers SHOULD NOT use it.

### 11.3 Integrity and editing

- `AUDIO_SHA256` is the SHA-256 of the audio packets in stream order: every packet after the header packets (3
  for Vorbis, 2 for Opus), without page headers or lacing values. It does not change when the comments are
  rewritten or the pages renumbered. The decoded audio is not used: decoders do not all return the same samples.
- Section 8 applies, with chapters in place of cue points. A rewriter that changes only comments MUST keep
  `TT_SEGMENT_LIST` or `TT_SEGMENT_TABLE` unchanged and the chapters of the segments. A program that re-encodes the audio changes
  `AUDIO_SHA256` and may shift the frames (encoder delay): it MUST update the list or remove it with its chapters.

### 11.4 Splitting, referencing and playing one segment (informative)

- A segment is referenced as in section 9: `<file>.ogg#tt=<SEGMENT_ID>`.
- **Splitting**: a split decodes each segment (to WAV), re-encodes it (`ORIGIN/CONVERSION` of the result: `lossy`),
  or copies its packets (`none`), which loses nothing. Opus: the packets from 80 ms before the segment; the
  pre-skip of the new `OpusHead` drops what comes before the segment, the granule position of the last page what
  follows it (RFC 7845, sections 4.2, 4.4 and 5.1). Vorbis: the packets from the one before the packet that holds
  the first frame; the granule positions of the first and of the last audio page drop the frames outside the
  segment (Vorbis I, appendix A.2). ffmpeg 6.0 decodes such Opus files to the exact frames; from such Vorbis files
  it keeps the frames to drop at the start, up to one block (Appendix B).
- **Large lists**: the comment header is read before the first audio packet. A long list delays the start of
  streamed playback and may exceed what some programs accept. Sizes of lists observed: 0.7 KB per segment in
  `kit/samples/tt_v0_many.ogg` (290 KB for 400 segments, 320 KB of comments in all; 92 KB as a table in
  `tt_v0_many_table.ogg`), 1.75 KB per segment for the voices of Rìcháng, with ten fields (2.8 MB for 1,575
  segments), and 0.54 KB as a table (Appendix B). In an Ogg Opus file, RFC 7845 (section 5.2) also lets a program ignore every
  comment that is not entirely within the first 61,440 octets of the comment header, and treat a header larger than
  120 MB as invalid: an XML list of more than a few dozen segments goes beyond that limit, a table of about a
  hundred. Writers put the list last, after the summary and the chapters, so that these stay near the start. Test
  the programs you target with your largest files.
- **Playing one segment**: a reader can decode only the packets that cover a segment.
  - It needs the frames of each packet. The granule position of a page is the frame that follows the last packet
    completed on that page (Opus: pre-skip included); the duration of each packet fills in the rest. Opus: from
    the TOC byte of the packet (RFC 6716, section 3.1). Vorbis: (previous block size + current block size) / 4,
    the size of a block given by its mode, whose number opens the packet: the two sizes are in the identification
    header, the block flag of each mode at the end of the setup header (ffmpeg's Vorbis parser reads it there); the
    first audio packet returns nothing.
  - Opus: start decoding at least 3,840 frames (80 ms) before `START_SAMPLE` (RFC 7845, section 4.6) and drop the
    output up to it. The pre-skip of the `OpusHead` header belongs to the start of the stream: a reader that gives
    a decoder a stream rebuilt from packets in the middle of the file sets its pre-skip to 0 and drops those
    frames itself.
  - Vorbis: start decoding at least one packet before the packet whose output holds `START_SAMPLE`: the first
    packet a decoder receives only primes it.
  - Some decoding pipelines also trim the start or the end of a stream on their own, from its granule positions:
    with Web Audio in Chromium, the reader of Appendix B needed two packets before a Vorbis segment and a few after
    it. Decode a margin on each side and cut the result to `START_SAMPLE` and `LENGTH_SAMPLES`.
- **Silence between sounds**: a codec spreads each sound over its neighbours for a few tens of milliseconds (a
  Vorbis block spreads its coding noise over its whole window: 2,048 frames for a long block with the usual settings
  at 44.1 and 48 kHz). What counts is the quiet between the end of the loud part of one sound and the start of the
  next one: 40 ms were enough in Ogg Vorbis and 60 ms in Ogg Opus (Appendix B; with less, the first 20 ms of a sound
  that starts quiet rose by 5 to 33 dB after a loud end). The quiet edges of the sounds themselves count: sounds
  that start and end quiet need no silence between them, and a writer that does not check the edges can leave
  60 ms. In the voice files of Appendix B, each line keeps 50 ms before the voice and 120 ms after it; with no
  silence added, the edges of a line changed less than two encodings of the same line differ in its middle.
  Silence has a weight (section 12): in those files, 300 ms cost about 340 bytes per sound in Opus and 75 in
  Vorbis; 40 ms, about 70 and 45. Keep a little silence before the first sound and after the last one (50 to
  100 ms): a reader that decodes a margin on each side of a segment finds it there, and it is paid once per file.

### 11.5 Segment table

The XML list writes the name of every element in every segment. In an Ogg file it weighs more than the tags the
same sounds would carry as separate files (section 12, Appendix B). From draft 0.3, an Ogg file MAY hold its
segment list as a table: one comment `TT_SEGMENT_TABLE` whose value is a JSON object (RFC 8259), in UTF-8, on one
line. It holds the same data as the list of section 5, every element of every segment: it writes the name of each
element once, and a value that every segment shares once.

- A file MUST NOT hold both `TT_SEGMENT_TABLE` and `TT_SEGMENT_LIST`, nor more than one of either. `TT_VERSION` is
  `0.3`. A reader that finds both reports it and uses `TT_SEGMENT_LIST`: a program written for draft 0.2 added it
  after the table was written.
- Every value is a JSON string that holds the text of the element, numbers included (`"48000"`). Writers SHOULD NOT
  escape characters that JSON does not require to escape: an escaped CJK character takes six bytes instead of three.
- The members `TT_VERSION`, `WRITER`, `SAMPLE_RATE`, `TOTAL_FRAMES`, `AUDIO_SHA256`, `TIME_REFERENCE`,
  `TIMECODE_RATE`, `TIMECODE_FLAG` and `SEGMENT_COUNT` are the elements of the list header, with the rules of
  section 5. `XML` (optional) holds every other child of the list but the segments (an element of a single
  program, an element with children, a repeated element), whole, as XML text.
- `COLUMNS` is an array of paths (below), each at most once. `NAME`, `START_SAMPLE` and `LENGTH_SAMPLES` MUST be
  among them.
- `ROWS` is an array with one array per segment, in ascending `START_SAMPLE` order. Cell k of a row is the value of
  the segment for path k of `COLUMNS`, or `null` when the segment has none. A row MAY be shorter than `COLUMNS`:
  the cells it lacks are `null`. A cell that holds an empty string is an element with an empty text.
- `DEFAULTS` (optional) is an object: for a path, the value of every segment whose cell is `null` or whose row has
  no such column. That value belongs to each of those segments as if it were written in its row: a program that
  lists, indexes or splits the segments gives it to each of them. An empty string in a cell overrides it.
  `DEFAULTS` MUST NOT hold `NAME`, `SEGMENT_ID`, `START_SAMPLE` or `LENGTH_SAMPLES`.
- `ORDER` (optional) is an array of paths: the order of the elements of a segment in the XML list. A program that
  writes the XML list from the table writes the elements of each segment in that order, each block (`USER`,
  `FIELD_LIST`...) where its first path is, and the paths `ORDER` does not hold after the others. The order of the
  elements of a segment carries no meaning: `ORDER` keeps the order a writer chose to show them in.
- `ID_NAMESPACE` (optional) is a UUID. With it, a segment whose `SEGMENT_ID` is `null` has the name-based UUID
  (version 5, RFC 9562) of its `NAME`, as UTF-8, in that namespace (section 5.1). Such segments MUST have distinct
  names. A program that renames one of them MUST write its `SEGMENT_ID` in the row from then on: the ID of a segment
  never changes. Without `ID_NAMESPACE`, every segment MUST have a `SEGMENT_ID`.
- A segment with no `CUE_ID` has `CUE_ID` 0: no chapter.

| Path | Element of section 5 |
|---|---|
| `NAME`, `START_SAMPLE`, `LENGTH_SAMPLES`, `SEGMENT_ID`, `CUE_ID`, `STATUS`, `CONFIDENCE`, or the name of an element of a single program | the element of that name, when it holds text only |
| `<block>/<tag>`: `USER/<tag>`, `ASWG/<tag>`, `ORIGIN/<tag>`, or a block of a single program | the child `<tag>` of that block, when every child of the block holds text only and has a name of its own |
| `FIELD/<name>` | the `VALUE` of the `FIELD` of `FIELD_LIST` whose `NAME` is `<name>` (the name may contain `/`), when every `FIELD` holds a `NAME` and a `VALUE` only and no two have the same `NAME` |
| `XML` | every other child of `TT_SEGMENT`, whole, as XML text, one after the other: an element with attributes or deeper children (an `ORIGIN` with a `CHUNK_LIST`), every occurrence of a repeated element (two `USER` blocks, two elements of a program with the same name), a `FIELD_LIST` that the row above cannot express. An element written here is not written in other columns. A cell holds these elements only, as the `XML` member holds its own: text outside them, white space apart, breaks this section. |

Converting an XML list to a table and back gives every element of every segment, with the same text; with `ORDER`,
in the same order when the segments share one order of their elements, as the segments one program writes do (the
elements of an `XML` cell come back together, where the first of them was). `ORDER` is one order for all the
segments: segments that order their elements otherwise come back in it, and the table written again from them can
differ from the first without losing anything; further conversions keep it. A program that
converts the file to WAV, or splits it, reads the same segments from either form. Sections 8 and 11.3 apply: a
rewriter MUST copy the comment unchanged, with the members and the paths it does not know. The kit's
`--validate` reads both forms; `kit/samples/tt_v0_full_table.opus` and `tt_v0_many_table.ogg` are written this way.

Example, with line breaks here:

```
TT_SEGMENT_TABLE={"TT_VERSION":"0.3","SAMPLE_RATE":"48000","TOTAL_FRAMES":"132000",
  "AUDIO_SHA256":"9f2c...e41a","SEGMENT_COUNT":"2",
  "DEFAULTS":{"USER/CATID":"VOXFem","ORIGIN/SAMPLE_RATE":"24000","ORIGIN/CONVERSION":"lossy"},
  "COLUMNS":["NAME","START_SAMPLE","LENGTH_SAMPLES","SEGMENT_ID","CUE_ID","USER/FXNAME","ORIGIN/FILENAME"],
  "ORDER":["SEGMENT_ID","CUE_ID","START_SAMPLE","LENGTH_SAMPLES","NAME","USER/CATID","USER/FXNAME",
           "ORIGIN/FILENAME","ORIGIN/SAMPLE_RATE","ORIGIN/CONVERSION"],
  "ROWS":[["VOXFem_Hello there_01","0","72000","3f2b9c1e-5d4a-4e8b-9f1a-2c7d6e5b4a3f","1","Hello there","hello_there_01.wav"],
          ["VOXFem_Goodbye_01","72000","60000","8a1d0c2e-7b3f-4a5d-8c6e-1f2a3b4c5d6e","2","Goodbye","goodbye_01.wav"]]}
```

The first row is this segment of the XML list, with the values of `DEFAULTS`:

```xml
<TT_SEGMENT><SEGMENT_ID>3f2b9c1e-5d4a-4e8b-9f1a-2c7d6e5b4a3f</SEGMENT_ID><CUE_ID>1</CUE_ID>
  <START_SAMPLE>0</START_SAMPLE><LENGTH_SAMPLES>72000</LENGTH_SAMPLES><NAME>VOXFem_Hello there_01</NAME>
  <USER><CATID>VOXFem</CATID><FXNAME>Hello there</FXNAME></USER>
  <ORIGIN><FILENAME>hello_there_01.wav</FILENAME><SAMPLE_RATE>24000</SAMPLE_RATE><CONVERSION>lossy</CONVERSION></ORIGIN>
</TT_SEGMENT>
```

## 12. Weight (normative)

A TT file is meant to weigh no more than the same sounds as separate files with the same metadata. This section
defines the weight of those files, so that a writer can keep to it and a validator can check it.

### 12.1 Reference weight

The reference weight of a TT file is the sum of the sizes of one separate file per segment.

WAV file. For each segment: 12 bytes (RIFF header and form type); the `fmt ` chunk of the TT file; the original
chunks of its `ORIGIN/CHUNK_LIST` when it has some, otherwise the `bext` chunk of the TT file when it has one and an
`iXML` chunk made of the XML declaration, `BWFXML`, `IXML_VERSION` and the `USER`, `ASWG` and `FIELD_LIST` elements of
the segment as the list writes them; a `data` chunk of `LENGTH_SAMPLES` frames. Chunk headers and pad bytes count.

Ogg file. For each segment:

- the header pages of the TT file with a comment header that keeps only its vendor string: identification header,
  comment header, Vorbis setup header, their page headers and lacing values;
- its reference tags: for each value of the segment other than `SEGMENT_ID`, `CUE_ID`, `START_SAMPLE` and
  `LENGTH_SAMPLES`, empty values left out, 4 bytes, the name of the element (the last part of its path in section
  11.5; the `NAME` of a `FIELD`), 1 byte and the value in UTF-8; what the paths cannot express (the `XML` cell of
  section 11.5) counts as one value named `XML`;
- the audio packets that hold its frames, each with its lacing values (one per 255 bytes of the packet, plus one);
  a packet that also holds frames outside the segment counts in proportion to its frames inside it;
- 27 bytes per page, for as many pages as these packets fill at the average number of packets per audio page of the
  TT file, and at least one.

### 12.2 Rule

- A writer SHOULD NOT write a TT file larger than its reference weight when all its audio belongs to its segments
  (apart from a short silence at each end, section 11.4). When it does, it SHOULD tell the user, with both sizes.
- A validator reports the size of the file, its reference weight, and the bytes of audio that belong to no segment.
  The kit's `--validate` prints them on a line `weight (section 12)`.

### 12.3 Keeping to the rule (informative)

In order of effect, on the files of Appendix B:

1. No audio outside the segments. In a WAV file, one millisecond of silence per sound (48 to 288 bytes) weighs more
   than everything a TT file saves. In an Ogg file, see the note on silence (section 11.4).
2. In an Ogg Opus file, the table (section 11.5): a separate Opus file spends about 100 bytes on its own headers,
   less than the XML of one segment. In an Ogg Vorbis file every form keeps to the rule: each separate file repeats
   a setup header of 3 to 4 KB.
3. In a file that keeps the original chunks of its sounds, the deflated form (section 5.2): base64 alone makes them
   a third larger than in the separate files.
4. What only keeps an order or serves other programs, the least useful first: `ORDER` (section 11.5), the second
   copy of the description (`COMMENT`), the `note` entries; then the names in the description, `LIST/INFO`; then
   the chapters. The metadata of the segments is never removed: keeping it is what a TT file is for.
5. A file of very few segments cannot keep to the rule: it has a list header and nothing to share. In those files,
   a TT file was the lighter one from 2 segments in Ogg Vorbis, 5 in Ogg Opus and 4 to 14 in WAV.

A recording kept whole, with what lies between its sounds, is heavier than its sounds alone: that is what it is for.

## 13. Example

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

The same in an Ogg Opus file, for a sound whose source has another rate: a voice line recorded at 24 kHz, its
silence trimmed, placed at 1.1 s. The frames of the file are at 48 kHz (section 11.1), those of `ORIGIN` at the
rate of the source (section 5.2): the 1.5 s of the line are 72000 frames in the file and 36000 in the source.
`OpusHead` keeps 24000 as its input rate, which changes nothing to how frames are counted.

```
CHAPTER002=00:00:01.100
CHAPTER002NAME=Hello there
TT_SEGMENT_LIST=<TT_SEGMENT_LIST><TT_VERSION>0.2</TT_VERSION>...</TT_SEGMENT_LIST>
```

The value of `TT_SEGMENT_LIST`, on one line in the file, with line breaks here:

```xml
<TT_SEGMENT_LIST>
  <TT_VERSION>0.2</TT_VERSION>
  <SAMPLE_RATE>48000</SAMPLE_RATE>
  <TOTAL_FRAMES>480000</TOTAL_FRAMES>
  ...
  <TT_SEGMENT>
    <SEGMENT_ID>...</SEGMENT_ID>
    <CUE_ID>2</CUE_ID>
    <START_SAMPLE>52800</START_SAMPLE>
    <LENGTH_SAMPLES>72000</LENGTH_SAMPLES>
    <NAME>VOXFem_Hello there_01</NAME>
    <ORIGIN>
      <FILENAME>hello_there_01.wav</FILENAME>
      <START_SAMPLE>1200</START_SAMPLE>
      <LENGTH_SAMPLES>36000</LENGTH_SAMPLES>
      <SAMPLE_RATE>24000</SAMPLE_RATE>
      <CONVERSION>lossy</CONVERSION>
      <CONVERSION_NOTE>silence trimmed, 24000 Hz to Ogg Opus (48000 Hz)</CONVERSION_NOTE>
    </ORIGIN>
  </TT_SEGMENT>
</TT_SEGMENT_LIST>
```

## 14. Open questions

1. **Carrier**: iXML only, or also a dedicated RIFF chunk carrying the same XML (candidate ID `ttsg`), for
   programs that drop unknown iXML elements when they rewrite a file. To be decided from tests in more programs
   (Appendix B; the test kit is in `kit/`).
2. **Analysis data**: lanes, groups, frequency bands and species as common elements, or left to each program?
3. **Other formats**: FLAC (Vorbis comments, close to section 11; in a test, 75 voice lines in one FLAC file weighed
   17 % less than the same lines as separate FLAC files, Appendix B), AIFF, BW64 with ADM, Matroska / WebM, and a
   sidecar file for formats without room for metadata.
4. **Registration**: propose the object to the iXML committee, as Sony did for its ASWG object (added to the
   iXML specification in revision 3.01, October 2021).
5. **Compressed list**: the list or the table deflated before base64 would make an Ogg Opus file 3 to 4 % lighter
   again, at the price of a value that can no longer be read as text. The weight rule does not need it (section 12).

Decided: the name (TT File Format, elements `TT_SEGMENT_LIST` and `TT_SEGMENT`); the original chunks of a segment
(`ORIGIN/CHUNK_LIST`) stay in version 1 as an option; Ogg files carry the same list in a Vorbis comment (section
11), in one comment, not one per segment (question 5 of draft 0.2): ffmpeg joins comments of the same name with `;`
when it rewrites a file, and RFC 7845 lets an Ogg Opus program keep the start of a list cut into several comments
and drop the rest without notice (Appendix B); the licences (section 15).

## 15. Licence

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
| `TAG@lane`, `@low_hz`, `@high_hz`, `@group`, `@occurrences`, `TAG/SPECIES` | program-specific elements (`AUDIOCRUCIBLE_...`), see question 2 |

## Appendix B. Interoperability observed (informative)

Sample files and checker: `kit/make_tt_spec_samples.py` (each candidate carrier holds its own search word; `--check`
compares a file rewritten by a program with the original). Results so far:

| Program | Markers shown | Region end | Segments | Search reads | After the program added a marker |
|---|---|---|---|---|---|
| Soundly (2026-10-22) | yes, with their `labl` name; `note` not shown | not shown (`ltxt` ignored) | Segments mode: each marker to the next one | file-level metadata only (`bext`, iXML `USER`); not `labl`, `note`, the segment list, the `ttsg` chunk or XMP markers | audio, `bext`, `LIST/INFO`, iXML (segment list included), `ttsg` and `_PMX` kept byte for byte; existing cue points and `LIST/adtl` entries kept; new cue point with a free ID, its `labl` appended after the `note` and `ltxt` entries; `cue ` chunk moved after `data` |

Other programs (Soundminer, BaseHead, REAPER, iZotope RX, Pro Tools, Nuendo / WaveLab) are not tested yet.
Results for them are welcome: see `kit/TEST_PROTOCOL.md`.

Ogg files (draft 0.2):

- ffmpeg 6.0 as a reader (ffprobe): lists the chapters of the samples, 5 in `tt_v0_full.ogg` and `tt_v0_full.opus`
  and 400 in `tt_v0_many.ogg`, and decodes the three files without error. It reads comment headers of 2.9 MB. It
  reads three digits after `CHAPTER`: in a test file, `CHAPTER1000NAME` to `CHAPTER1009NAME` all renamed chapter
  100, and `CHAPTER1000` to `CHAPTER1011` were ignored (2026-11-12).
- ffmpeg 6.0 as a rewriter (`-c copy`, 2026-11-12): the segment list (2.7 MB included), the summary and the audio
  packets are kept (`AUDIO_SHA256` and `TOTAL_FRAMES` unchanged), the chapters are not. To Ogg Vorbis it drops them
  all. To Ogg Opus it numbers them again from `CHAPTER000`, so each `CUE_ID` points to the next chapter, and writes
  those whose millisecond part is 500 or more one second late (0.5 s becomes `00:00:01.500`); it writes 1,000
  chapters at most, then `CHAPTER100` again. Readers then report the segments as moved (section 8).
- [Rìcháng](https://github.com/Bannl/Richang), a game to learn Taiwan Mandarin (2026-11-11): the first Ogg TT files
  written outside the kit and AudioCrucible, the dubbed lines of each character in Ogg Vorbis and in Ogg Opus (72
  files, 33 to 1,575 segments, lists of 57 KB to 2.8 MB), read in the browser by a reader that decodes only the
  packets of a segment.
  All pass `--validate` with no warning; their positions, checked against a full decode by ffmpeg, are exact to
  the frame in Vorbis and within 1 ms in Opus. They brought the rules on chapter times and numbers (section 11.2)
  and the notes on playing one segment (section 11.4). Details in `CASE_STUDY_RICHANG.md`.
- ffmpeg 6.0 as a rewriter, again (2026-11-12): it keeps `TT_SEGMENT_TABLE` byte for byte; it joins comments of
  the same name with `;`, and drops data placed after the comments of `OpusTags` (RFC 7845, section 5.2). From an
  Ogg Opus segment cut by packet copy (section 11.4) it decodes the exact frames; from an Ogg Vorbis segment cut the
  same way it keeps up to one block too many at the start.

Weight against separate files (2026-11-12, draft 0.3): the voice files of Rìcháng, rebuilt from their sources with
the same audio settings, and 475 sound effects of a test library, against the same sounds as separate files with
the same metadata.

| Files | As written before | With draft 0.3 |
|---|---|---|
| Rìcháng voices, Ogg Opus, 36 files, 4,725 lines | 16.4 % heavier (XML list, 300 ms between lines) | 7.4 % lighter (table, no silence added); no file heavier |
| Rìcháng voices, Ogg Vorbis, 36 files | 21.2 % lighter | 32.1 % lighter |
| Rìcháng voices in WAV (model and prototype, no silence) | 0.09 % lighter | unchanged |
| 475 sound effects in WAV, original chunks kept (estimated from their chunks) | 0.26 % heavier (base64) | 0.69 % lighter (deflated) |

Rìcháng now ships its voices this way: 36 Ogg Opus files with a segment table and no silence added (4,728 lines with
its tutorial, 3 h 14 min), 32.9 MB, 5.2 % lighter than their reference weight (section 12.1); every file is lighter,
from 4.1 % to 7.5 %, and all pass `--validate` with no warning. Every list of its files, converted to a table and
back, gave every element and value in the same order.
Without silence between lines, the edges of a line changed less than two encodings of the same line differ in its
middle; after a loud end, the next sound needed 40 ms (Vorbis) and 60 ms (Opus) of quiet. Deflated, the XMP packets
of the sound effects took 15 % of their bytes, their `bext` chunks 18 %. In FLAC, 75 lines in one file weighed 17 %
less than as separate FLAC files. Method and full results in `CASE_STUDY_RICHANG.md`.

Game engines, audio middleware and tag editors are not tested yet and are the most wanted.

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
