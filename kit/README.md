# Test kit

The sample files are already in [samples/](samples/) (3 WAV files, 5 Ogg files, two of them with the list as a
table of draft 0.3, and `manifest.json`, the expected content). The Ogg samples are made from the encoded audio in [ogg_audio/](ogg_audio/): the kit only rewrites their
comments (kit maintainers re-encode that audio with `--make-ogg-audio`, which needs ffmpeg).

`make_tt_spec_samples.py` needs Python 3.7 or later and nothing else (standard library only). It writes only inside
this folder.

| Command | What it does |
|---|---|
| `python make_tt_spec_samples.py` | writes `samples/` again (the same bytes) and `SELFCHECK.txt`, then checks the files itself |
| `python make_tt_spec_samples.py --check FILE` | compares a copy that went through a program with the original, carrier by carrier |
| `python make_tt_spec_samples.py --check FILE --as tt_v0_full.wav` | same, for a copy the program renamed |
| `python make_tt_spec_samples.py --validate FILE` | checks any TT file, for example one your program wrote, against the rules of the specification (`RESULT PASS` / `FAIL`, with warnings) |

How to test a program and report the result: [TEST_PROTOCOL.md](TEST_PROTOCOL.md).
