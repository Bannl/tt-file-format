# TT File Format

Several sounds in one standard WAV file, each with its own name and its full metadata.

A TT file is an ordinary WAV file: every program plays it. Inside it, each sound (a segment) has:

- a standard marker and region, so editors, DAWs and library tools show it by name;
- an entry in an iXML segment list with all its metadata, written exactly like the metadata of a whole file
  (`USER`, `ASWG`), so a program that reads file-level iXML can read a segment with the same code;
- optionally, where it came from: the source file name, its original timecode and its original metadata chunks,
  so that the file can be split back into the original files.

A program that implements the format can list each sound as its own search result and open the file directly at
that sound (`file.wav#tt=<segment id>`).

## Why

Sound libraries often put several takes or variations in one file. The name and the metadata of each sound are
lost on the way: library tools index the file, not the sounds inside it. The TT File Format keeps them, using only
chunks that already exist in WAV files (`cue `, `LIST/adtl`, `bext`, `iXML`) plus one new iXML object.

## Status

Draft 0.1, open for comments (October 2026). AudioCrucible 1.0.13 (Nextale Audio) is the first implementation: the
TT files it creates carry the segment list of this draft, with the origin of each sound and the SHA-256 of the
audio, and it splits them back into one file per sound, with the name, timecode and metadata the sound had before.
It still reads the earlier form written by AudioCrucible 1.0.12 (Appendix A of the specification).

## Contents

| Path | What it is |
|---|---|
| [SPEC.md](SPEC.md) | the specification |
| [kit/](kit/) | the sample files, their generator and checker (Python 3, standard library only), test protocol for a program |
| [RESULTS.md](RESULTS.md) | what each tested program shows, searches and keeps |
| [CHANGELOG.md](CHANGELOG.md) | changes between drafts |
| [LICENSE.md](LICENSE.md) | licences |

## Test your program in 10 minutes

The three sample WAV files are in [kit/samples/](kit/samples/): `tt_v0_full.wav`, `tt_v0_minimal.wav` and
`tt_v0_many.wav` (400 sounds). Load copies of them in your program and follow
[kit/TEST_PROTOCOL.md](kit/TEST_PROTOCOL.md). This part needs no Python.

After your program has written into a copy (a metadata field, a marker), run (Python 3, standard library only):

```
python kit/make_tt_spec_samples.py --check path/to/copy/tt_v0_full.wav
```

and post the `RESUME` line it prints in an issue, with the name and version of your program.

If your program writes TT files, check one against the rules of the specification:

```
python kit/make_tt_spec_samples.py --validate path/to/your_file.wav
```

`python kit/make_tt_spec_samples.py` writes the sample files again (the same bytes) and checks them.

## Feedback

Questions, objections and test results are welcome as issues.

## Licence

The specification is published under CC BY 4.0, the code of the kit under the MIT licence. Copyright 2026 Nextale
Audio. See [LICENSE.md](LICENSE.md).
