# Changelog

## Draft 0.3 (2026-11-12)

From a study of the weight of TT files against the same sounds as separate files with the same metadata
(Appendix B). Every file written before stays valid, and the list of a WAV file stays as it is.

- Segment table (section 11.5): in an Ogg file the list may be one comment `TT_SEGMENT_TABLE`, a JSON object with
  the names of the columns written once, the values every segment shares written once (`DEFAULTS`), and one row per
  segment. It holds every element of every segment: converted to the XML list and back, it gives the same elements
  with the same text (`ORDER` keeps their order; an `XML` cell and an `XML` member keep what the columns do not
  express). 0.54 KB per segment instead of 1.75 KB for the voices of Rìcháng (Appendix B). `TT_SEGMENT_LIST` stays
  valid.
- Weight (section 12): the reference weight of a TT file, the size of the same sounds as separate files with the
  same metadata; writers keep to it when all the audio belongs to the segments, validators report it. With the
  table and no silence added, the voices of Rìcháng in Ogg Opus went from 16.4 % heavier than separate files to
  7.4 % lighter, in Ogg Vorbis from 21.2 % to 32.1 % lighter (study). The game now ships its 36 Ogg Opus files this
  way: 32.9 MB, 5.2 % lighter than their reference weight, every file lighter.
- Original chunks (section 5.2): a chunk of `ORIGIN/CHUNK_LIST` may be deflated before base64
  (`DATA_DEFLATE_BASE64`); writers use the shorter form, readers read both and leave out a chunk in a form they do
  not know. Estimated on 475 sound effects of a test library, a WAV TT file goes from 0.26 % heavier than the
  original files to 0.69 % lighter. Search is not affected: names, fields, markers and the summary stay in clear text.
- Section 11.4: silence between sounds from measurements (none when the sounds start and end quiet, 40 ms in Vorbis
  and 60 ms in Opus after a loud end, a little at each end of the file); a split may copy the packets of a segment
  instead of decoding it.
- Question 5 (one comment for the whole Ogg list, or one per segment) is closed: one comment, since ffmpeg joins
  comments of the same name with `;` and RFC 7845 lets an Opus program drop the comments beyond 61,440 octets. New
  question 5: a compressed list. Question 3 gains a FLAC figure; Appendix A points to question 2 (it pointed to 4).
- Case study (`CASE_STUDY_RICHANG.md`): the voice files of Rìcháng, the data set of these measurements; method and
  results against separate files in WAV, Ogg Vorbis and Ogg Opus. The details on these files move there from
  `RESULTS.md`.
- Kit: `--validate` reads the table (and checks its rules), checks deflated chunks (zlib stream, 64 MiB at most) and
  prints a `weight (section 12)` line for every file; two new samples, `tt_v0_full_table.opus` and
  `tt_v0_many_table.ogg`, the same as `tt_v0_full.opus` and `tt_v0_many.ogg` with the list as a table (and, in the
  first, the original `bext` chunk deflated); `--check` reads either form; new self-check cases (round trip of every
  list through a table, a list of edge cases, the validator's table and chunk rules). The six earlier samples are
  unchanged.

## Draft 0.2, amended (2026-11-12)

From the first Ogg TT files written outside the kit and AudioCrucible (the voice files of
[Rìcháng](https://github.com/Bannl/Richang), a game to learn Taiwan Mandarin, Appendix B). Every file written before
stays valid, except a file with chapter numbers of four digits or more (none is known).

- Chapter times (section 11.2): the start in milliseconds, rounded to the nearest; a start exactly on a half
  millisecond may be rounded either way (the kit rounds to even, JavaScript and C++ round up), and validators
  accept both. Before, the kit's rounding was the only rule: a writer that rounded up failed on 3 segments of 75.
  Readers take a chapter at most 1 ms away from `START_SAMPLE` as being at the start of its segment.
- Chapter numbers (section 11.2): three digits at most (MUST NOT write more). ffmpeg reads three digits only:
  `CHAPTER1000NAME` renames chapter 100. Beyond 999 chapters the later segments are in the list only; split the
  file when programs that read only chapters must see every sound.
- Section 11.4 (informative): sizes of real lists; RFC 7845 lets Ogg Opus programs ignore the comments beyond the
  first 61,440 octets of the comment header, hence the list last; how to play one segment (frames of each packet,
  Opus pre-roll and pre-skip, Vorbis priming, pipelines that trim on their own); silence between separate sounds.
- Section 5.1: a `SEGMENT_ID` derived from a key of the sound (UUID version 5) keeps the references valid when a
  file is built again.
- Section 12: an Ogg Opus example, the segment at 48 kHz and its `ORIGIN` at the rate of its source (24 kHz).
- Question 5 and Appendix B: ffmpeg 6.0 as a reader and as a rewriter of Ogg TT files (it drops or renumbers the
  chapters), the voice files of Rìcháng. `RESULTS.md`: a table for Ogg files (the earlier note broke the main
  table).
- Kit: `--validate` accepts both roundings of a chapter time on a half millisecond, fails on chapter numbers of
  more than three digits (it warned before), and adds `[INFO]` lines (segments without a chapter, Opus comments
  beyond 61,440 octets); `--check` takes a chapter at most 1 ms away from its start as not moved; four new
  self-check cases. The sample files are unchanged.

## Draft 0.2, amended (2026-11-10)

- File time reference in the list header, optional: `TIME_REFERENCE` (frames since midnight at `SAMPLE_RATE`, as
  the `bext` TimeReference), `TIMECODE_RATE` and `TIMECODE_FLAG` (as iXML `SPEED` writes them). It is the carrier of
  the timecode of an Ogg file, which has no `bext` (section 11.2); in a WAV file the `bext` stays the carrier and the
  list, when it has `TIME_REFERENCE`, MUST give the same value (section 5). Writers keep it when they rewrite the
  list (section 8); a split uses it for the timecode of each sound (section 9). Every file written before stays
  valid.
- Kit: the Ogg samples carry a file time reference (10:00:00:00 at 25 fps); `--validate` checks the three elements,
  and for a WAV file that `TIME_REFERENCE` matches the `bext`.

## Draft 0.2 (2026-11-04)

- Ogg files, Vorbis and Opus (section 11): the same segment list in one Vorbis comment, chapters as the marker
  mirror, the summary in comments, and an audio fingerprint over the audio packets. Nothing changes for WAV files:
  a WAV file written for draft 0.1 stays valid.
- Kit: three Ogg samples (`tt_v0_full.ogg`, `tt_v0_full.opus`, `tt_v0_many.ogg`), made from the encoded audio in
  `kit/ogg_audio/`; `--check` and `--validate` read Ogg files. The WAV samples are unchanged.
- New open question: one comment for the whole list, or one per segment.

## Draft 0.1 (2026-10-22)

- First public draft: segment list in iXML (`TT_SEGMENT_LIST`), marker mirror, file-level summary, integrity
  rules, segment references, optional XMP mirror.
- Reader rules and the summary rule completed from a first interoperability test (Soundly, Appendix B).
- Test kit (`kit/`): sample files generator, checker of a copy rewritten by a program (`--check`), validator of
  any TT file against the rules of the specification (`--validate`).
- Appendix C: the alternatives considered (other carriers for per-segment data) and why iXML was chosen.
- The three sample WAV files and their manifest are in the repository (`kit/samples/`), so a program can be tested
  without Python.
