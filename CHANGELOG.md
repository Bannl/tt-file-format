# Changelog

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
