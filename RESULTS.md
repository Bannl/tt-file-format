# Interoperability results

Made with the kit (`kit/`): see [kit/TEST_PROTOCOL.md](kit/TEST_PROTOCOL.md). Results for other programs are
welcome as issues.

| Program | A. Markers shown | A. Region end | B. Search reads | C. After the program added a marker |
|---|---|---|---|---|
| Soundly (tested 2026-10-22, Windows) | yes, with their name (`labl`); notes not shown | not shown (`ltxt` ignored) | file-level metadata only (`bext`, iXML `USER`) | everything kept, segment list included |
| Soundminer | not tested |  |  |  |
| BaseHead | not tested |  |  |  |
| REAPER | not tested |  |  |  |
| iZotope RX | not tested |  |  |  |
| Pro Tools | not tested |  |  |  |
| Nuendo / WaveLab | not tested |  |  |  |

## Soundly, details

- **Display**: the 5 markers of `tt_v0_full` under the waveform, each with its name, at the right place. Only the
  starts are drawn.
- **Segments mode**: works on the markers of a local file; each segment runs from a marker to the next one (the
  silence after a sound belongs to it, and every other marker also starts a segment).
- **File-level metadata**: the Description, Originator, Reference and Origination date columns come from the
  `bext` chunk; Category and Subcategory come from the iXML `USER` object.
- **Search**: `zorbfile` finds the 3 files, `tt_v0_minimal` included, which has it only in the iXML `USER`
  object: the search reads that object even though the Description column shows the `bext` Description. No other
  word is found: marker names and notes, the segment list, the `ttsg` chunk and the XMP markers are not indexed.
- **After a marker was added** (`RESUME audio=OK fmt=OK bext=OK info=OK ixml_file=OK ixml_list=OK ttsg=OK xmp=OK
  cue=CHANGED adtl=CHANGED order=CHANGED extra=none`): audio, `bext`, `LIST/INFO`, iXML with the segment list,
  `ttsg` and `_PMX` kept byte for byte; the existing cue points and `LIST/adtl` entries kept; the new cue point got
  a free ID and its `labl` was appended after the `note` and `ltxt` entries; the `cue ` chunk moved after `data`.
