# Changelog

## Draft 0.1 (2026-10-22)

- First public draft: segment list in iXML (`TT_SEGMENT_LIST`), marker mirror, file-level summary, integrity
  rules, segment references, optional XMP mirror.
- Reader rules and the summary rule completed from a first interoperability test (Soundly, Appendix B).
- Test kit (`kit/`): sample files generator, checker of a copy rewritten by a program (`--check`), validator of
  any TT file against the rules of the specification (`--validate`).
- Appendix C: the alternatives considered (other carriers for per-segment data) and why iXML was chosen.
- The three sample WAV files and their manifest are in the repository (`kit/samples/`), so a program can be tested
  without Python.
