# TT File Format

Several sounds in one standard WAV or Ogg file, each with its own name and its full metadata.

A TT file is an ordinary WAV file, or an ordinary Ogg Vorbis / Opus file: every program plays it. Inside a WAV
file, each sound (a segment) has:

- a standard marker and region, so editors, DAWs and library tools show it by name;
- an entry in an iXML segment list with all its metadata, written exactly like the metadata of a whole file
  (`USER`, `ASWG`), so a program that reads file-level iXML can read a segment with the same code;
- optionally, where it came from: the source file name, its original timecode and its original metadata chunks,
  so that the file can be split back into the original files.

In an Ogg file, the same data is kept in Vorbis comments: a chapter per sound, and the segment list in one comment,
as XML or, from draft 0.3, as a compact table that keeps every element of every segment (section 11 of the
specification). A TT file is meant to weigh no more than the same sounds as separate files with the same metadata
(section 12).

A program that implements the format can list each sound as its own search result and open the file directly at
that sound (`file.wav#tt=<segment id>`).

## Why

Sound libraries often put several takes or variations in one file. The name and the metadata of each sound are
lost on the way: library tools index the file, not the sounds inside it. The TT File Format keeps them, using only
chunks that already exist in WAV files (`cue `, `LIST/adtl`, `bext`, `iXML`) plus one new iXML object. Game audio
often packs variations in one compressed file as well, hence the Ogg form.

## Status

Draft 0.3, open for comments (November 2026: a compact form of the segment list for Ogg files, the weight of a TT
file against separate files, original chunks deflated; the list of a WAV file is unchanged). AudioCrucible 1.0.13
(Nextale Audio) is the first implementation, for WAV files: the TT files it creates carry the segment list, with
the origin of each sound and the SHA-256 of the audio, and it splits them back into one file per sound, with the
name, timecode and metadata the sound had before. It still reads the earlier form written by AudioCrucible 1.0.12
(Appendix A of the specification). AudioCrucible 1.0.14 also writes Ogg Vorbis and Opus TT files.

The voice files of [Rìcháng](https://github.com/Bannl/Richang), a game to learn Taiwan Mandarin, are the first Ogg
TT files written outside AudioCrucible and the kit, and a working example of draft 0.3: 36 Ogg Opus files, one per
character and two for the player, hold its 4,728 voice lines, each line a segment with its name, its text in
Chinese, pinyin, English and French, and its origin. They weigh 32.9 MB, 5 % less than the same lines as separate
files with the same metadata, and every file is lighter. The game plays a line by decoding only the packets of its
segment. Method and results in WAV, Ogg Vorbis and Ogg Opus: [CASE_STUDY_RICHANG.md](CASE_STUDY_RICHANG.md).

## Contents

| Path | What it is |
|---|---|
| [SPEC.md](SPEC.md) | the specification |
| [kit/](kit/) | the sample files, their generator and checker (Python 3, standard library only), test protocol for a program |
| [RESULTS.md](RESULTS.md) | what each tested program shows, searches and keeps |
| [CASE_STUDY_RICHANG.md](CASE_STUDY_RICHANG.md) | the voice files of Rìcháng: weight of TT files against separate files in WAV, Ogg Vorbis and Ogg Opus, method and results |
| [CHANGELOG.md](CHANGELOG.md) | changes between drafts |
| [LICENSE.md](LICENSE.md) | licences |

## Test your program in 10 minutes

The sample files are in [kit/samples/](kit/samples/): three WAV files (`tt_v0_full.wav`, `tt_v0_minimal.wav`,
`tt_v0_many.wav` with 400 sounds) and five Ogg files (`tt_v0_full.ogg`, `tt_v0_full.opus`, `tt_v0_many.ogg`, and
`tt_v0_full_table.opus`, `tt_v0_many_table.ogg` with the list as a table, draft 0.3). Load copies of them in your
program and follow [kit/TEST_PROTOCOL.md](kit/TEST_PROTOCOL.md). This part needs no Python. For game engines and
audio middleware, `tt_v0_many.ogg` carries about 320 KB of comments and `tt_v0_many_table.ogg` the same list in
92 KB: check that your tool imports and plays them. For tag editors: check that a rewrite keeps the
`TT_SEGMENT_LIST` and `TT_SEGMENT_TABLE` comments whole.

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
