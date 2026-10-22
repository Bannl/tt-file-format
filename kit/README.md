# Test kit

`make_tt_spec_samples.py` needs Python 3.7 or later and nothing else (standard library only). It writes only inside
this folder.

| Command | What it does |
|---|---|
| `python make_tt_spec_samples.py` | writes `samples/` (3 WAV files and `manifest.json`) and `SELFCHECK.txt`, then checks the files itself |
| `python make_tt_spec_samples.py --check FILE` | compares a copy that went through a program with the original, carrier by carrier |
| `python make_tt_spec_samples.py --check FILE --as tt_v0_full.wav` | same, for a copy the program renamed |
| `python make_tt_spec_samples.py --validate FILE` | checks any TT file, for example one your program wrote, against the rules of the specification (`RESULT PASS` / `FAIL`, with warnings) |

How to test a program and report the result: [TEST_PROTOCOL.md](TEST_PROTOCOL.md).
