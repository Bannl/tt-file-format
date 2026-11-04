# Changelog

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
