# -*- coding: utf-8 -*-
"""make_tt_spec_samples.py: sample files for the TT File Format draft 0.3 (../SPEC.md), a checker and a validator.

    py -I make_tt_spec_samples.py                          writes samples/ (3 WAV, 5 Ogg, manifest.json) and SELFCHECK.txt
    py -I make_tt_spec_samples.py --check FILE [--as NAME] compares a copy that went through another program
    py -I make_tt_spec_samples.py --validate FILE          checks ANY TT file (WAV or Ogg) against the specification
    py -I make_tt_spec_samples.py --make-ogg-audio         kit maintainers only: encodes ogg_audio/ again (needs ffmpeg)

The Ogg samples are made from the encoded audio in ogg_audio/ (Vorbis and Opus, encoded once with ffmpeg from the
WAV samples): the kit only rewrites their comment header, so it still needs nothing but Python.

Each candidate carrier of the segment data holds its own search word, so that a search in a library tool tells
which carrier it indexes (see TEST_PROTOCOL.md). Python standard library only; writes only inside the
folder of this script.

Copyright 2026 Nextale Audio. MIT licence (see ../LICENSE.md).
"""
import argparse
import array
import base64
import bisect
import contextlib
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import zlib
from xml.sax.saxutils import escape as xml_escape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "samples")
MANIFEST_PATH = os.path.join(OUT_DIR, "manifest.json")
SELFCHECK_PATH = os.path.join(HERE, "SELFCHECK.txt")

SPEC_VERSION = "0.1"
WRITER = "TT spec v0 sample kit 2026-10-22"
SR = 48000
TIME_REFERENCE = 10 * 3600 * SR          # 10:00:00:00 at 48 kHz
E_ACUTE = chr(0xE9)
BOM = chr(0xFEFF)

FULL = "tt_v0_full.wav"
MINIMAL = "tt_v0_minimal.wav"
MANY = "tt_v0_many.wav"

OGG_SPEC_VERSION = "0.2"                 # Ogg files are defined from draft 0.2 (WAV samples stay 0.1: unchanged)
OGG_WRITER = "TT spec sample kit 2026-11-04"
OGG_AUDIO_DIR = os.path.join(HERE, "ogg_audio")
OGG_FULL = "tt_v0_full.ogg"
OPUS_FULL = "tt_v0_full.opus"
OGG_MANY = "tt_v0_many.ogg"
# (sample, segments of, encoded audio in ogg_audio/, TITLE, ORIGIN conversion)
OGG_SAMPLES = [(OGG_FULL, "full", "full_vorbis.ogg", "TT Doors", ("lossy", "PCM to Vorbis")),
               (OPUS_FULL, "full", "full_opus.opus", "TT Doors", ("lossy", "PCM to Opus")),
               (OGG_MANY, "many", "many_vorbis.ogg", "TT Impacts", ("lossy", "PCM to Vorbis"))]

# Draft 0.3 (2026-11-12): the segment table (section 11.5) and original chunks deflated before base64 (section 5.2)
TABLE_SPEC_VERSION = "0.3"
TABLE_WRITER = "TT spec sample kit 2026-11-12"
OPUS_FULL_TABLE = "tt_v0_full_table.opus"
OGG_MANY_TABLE = "tt_v0_many_table.ogg"
TABLE_SAMPLES = [(OPUS_FULL_TABLE, OPUS_FULL), (OGG_MANY_TABLE, OGG_MANY)]   # (table sample, Ogg sample it is made from)
LIST_KEY, TABLE_KEY = "TT_SEGMENT_LIST", "TT_SEGMENT_TABLE"
# The bext of the source of segment 1 (segment_lines) deflated (zlib, level 9) then in base64. A constant, so that the
# samples are the same bytes whatever zlib the Python build carries; the self-check inflates it and compares.
SRC_BEXT_DEFLATED = ("eNrzL8pMz8xLzFEoSk3OL0rJzEtXyE9TSFRIyc8vUijOScxlGN4gJEShuCA1WaHMQCE7swRTPjjIWdfAwMAQl34jAyMzXUMDXSMjQwMr"
                     "AxBieOFdCJJhZBjZwNE2wNlXx83WxAIYfjrhtkYmOr62xSWpRan5vFwAw90fUg==")
MAX_INFLATED = 64 << 20          # a reader MAY refuse a deflated chunk beyond 64 MiB (section 5.2)

TOKENS = {
    "file": "zorbfile",          # file-level summary only (bext, LIST/INFO, iXML USER and ASWG)
    "labl": "zorblabl",          # one labl only (segment 3)
    "note": "zorbnote",          # one note only (segment 3)
    "ixml": "zorbixml",          # the iXML segment list only (segment 3 keywords)
    "chunk": "zorbchunk",        # the ttsg chunk only (segment 3 keywords)
    "xmp": "zorbxmp",            # the XMP markers only (segment 3 keywords and comment)
    "many_list": "zorbmanyixml", # tt_v0_many.wav: segment 397, segment list only
    "many_labl": "zorbmanylabl", # tt_v0_many.wav: segment 398, labl only
    "ogg_file": "zorboggfile",   # Ogg samples: summary comments only (DESCRIPTION, COMMENT, KEYWORDS)
    "ogg_chapter": "zorboggchap",  # Ogg samples: one chapter name only (segment 3)
    "ogg_list": "zorboggtt",     # Ogg samples: the TT_SEGMENT_LIST comment only (segment 3 keywords)
    "ogg_many_list": "zorboggmanylist",  # tt_v0_many.ogg: segment 397, segment list only
    "ogg_many_chap": "zorboggmanychap",  # tt_v0_many.ogg: segment 398, chapter name only
}
# No word is a prefix or a part of another one: a search for one never finds the carrier of another.

CARRIERS = ["audio", "fmt", "bext", "info", "ixml_file", "ixml_list", "ttsg", "xmp", "cue", "adtl", "order"]
OGG_CARRIERS = ["stream", "audio", "headers", "summary", "chapters", "list"]
OGG_SUMMARY_KEYS = ["TITLE", "DESCRIPTION", "COMMENT", "KEYWORDS"]


# ---------------------------------------------------------------------------------------------
# Content of the sample files
# ---------------------------------------------------------------------------------------------

def seg_uuid(file_key, n):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "tt-spec-v0/%s/%d" % (file_key, n)))


def ascii_text(text):
    return text.replace(E_ACUTE, "e").encode("ascii", "replace").decode("ascii")


def full_segments():
    """The 4 sounds of tt_v0_full.wav / tt_v0_minimal.wav (positions at 48 kHz, gaps of 0.5 s)."""
    defs = [
        dict(fx="Door Slam", catid="DOORWood", sub="WOOD", desc="Heavy wooden door slammed hard, short tail",
             kw="door, slam, wood", freq=300.0, dur=1.2, bits=24, conversion="none"),
        dict(fx="Porte d'entr" + E_ACUTE + "e qui grince", catid="DOORCreak", sub="CREAK",
             desc="Porte d'entr" + E_ACUTE + "e en bois qui grince lentement", kw="door, creak, hinge, porte",
             freq=600.0, dur=1.6, bits=24, conversion="none"),
        dict(fx="Latch Click", catid="DOORHdwr", sub="HARDWARE", desc="Metal latch click, close perspective",
             kw="latch, click, metal", freq=1200.0, dur=0.8, bits=24, conversion="none"),
        dict(fx="Knock Knock", catid="DOORKnck", sub="KNOCK", desc="Two knuckle knocks on a wooden door",
             kw="knock, knuckles, wood", freq=2400.0, dur=1.0, bits=16, conversion="exact"),
    ]
    segs, pos = [], int(0.5 * SR)
    for i, d in enumerate(defs, start=1):
        length = int(round(d["dur"] * SR))
        s = dict(d)
        s.update(n=i, uid=seg_uuid("full", i), cue_id=i, start=pos, length=length,
                 name="%s_%s_ACT_SELF" % (d["catid"], d["fx"]), category="DOORS",
                 categoryfull="DOORS-" + d["sub"], labl=ascii_text(d["fx"]), note=ascii_text(d["desc"]),
                 src_file="%s_%s_ACT_SELF.wav" % (d["catid"], ascii_text(d["fx"])),
                 src_tref=11 * 3600 * SR + (i - 1) * 60 * SR)
        segs.append(s)
        pos += length + int(0.5 * SR)
    total = pos                                   # 0.5 s of background after the last sound
    segs[2]["labl"] += " " + TOKENS["labl"]
    segs[2]["note"] += " " + TOKENS["note"]
    return segs, total


FOREIGN = dict(cue_id=50, position=int(0.25 * SR), label="Foreign Marker")   # a point marker of another program


def many_segments():
    """400 short sounds (0.2 s, gaps of 0.05 s), for size and depth."""
    cats = [("DOORWood", "WOOD"), ("DOORMetl", "METAL"), ("DOORKnck", "KNOCK"), ("DOORHdwr", "HARDWARE")]
    freqs = [250.0, 400.0, 630.0, 1000.0, 1600.0, 2500.0, 4000.0, 6300.0]
    segs, pos = [], int(0.05 * SR)
    for i in range(1, 401):
        catid, sub = cats[(i - 1) % 4]
        length = int(0.2 * SR)
        fx = "Impact %03d" % i
        s = dict(n=i, uid=seg_uuid("many", i), cue_id=i, start=pos, length=length, fx=fx, catid=catid, sub=sub,
                 category="DOORS", categoryfull="DOORS-" + sub, name="%s_%s_ACT_SELF" % (catid, fx),
                 desc="Short test impact number %03d" % i, kw="impact, test, n%03d" % i,
                 freq=freqs[(i - 1) % 8], labl=fx, note="Short test impact number %03d" % i,
                 src_file="%s_%s_ACT_SELF.wav" % (catid, fx))
        segs.append(s)
        pos += length + int(0.05 * SR)
    segs[396]["kw_list_extra"] = TOKENS["many_list"]
    segs[397]["labl"] += " " + TOKENS["many_labl"]
    return segs, pos


# ---------------------------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------------------------

def synth(frames, channels, bits, bursts, seed):
    """Background at -60 dBFS + one tone burst per sound at -12 dBFS, 10 ms fades, from its exact start to end."""
    rnd = random.Random(seed)
    noise, tone, fade = 10 ** (-60 / 20.0), 10 ** (-12 / 20.0), int(0.010 * SR)
    vals = [(rnd.random() * 2.0 - 1.0) * noise for _ in range(frames)]
    for start, length, freq in bursts:
        w = 2.0 * math.pi * freq / SR
        for k in range(length):
            g = 1.0
            if k < fade:
                g = k / float(fade)
            elif k >= length - fade:
                g = (length - k) / float(fade)
            vals[start + k] += tone * g * math.sin(w * k)
    if bits == 16:
        a = array.array("h", [int(round(max(-1.0, min(1.0, v)) * 32767.0)) for v in vals])
        if sys.byteorder != "little":
            a.byteswap()
        if channels == 1:
            return a.tobytes()
        mono = a.tobytes()
        out = bytearray()
        for i in range(0, len(mono), 2):
            out += mono[i:i + 2] * channels
        return bytes(out)
    out = bytearray(frames * channels * 3)
    o = 0
    for v in vals:
        b = (int(round(max(-1.0, min(1.0, v)) * 8388607.0)) & 0xFFFFFF).to_bytes(3, "little")
        for _ in range(channels):
            out[o:o + 3] = b
            o += 3
    return bytes(out)


# ---------------------------------------------------------------------------------------------
# RIFF writing
# ---------------------------------------------------------------------------------------------

def chunk(fourcc, body):
    out = fourcc + struct.pack("<I", len(body)) + body
    if len(body) & 1:
        out += b"\x00"
    return out


def fixed(text, width):
    b = text.encode("ascii", "replace")[:width]
    return b + b"\x00" * (width - len(b))


def zstr(text):
    return text.encode("ascii", "replace")[:254] + b"\x00"


def fmt_chunk(channels, bits):
    align = channels * bits // 8
    return chunk(b"fmt ", struct.pack("<HHIIHH", 1, channels, SR, SR * align, align, bits))


def wav_bytes(chunks_before, pcm, chunks_after=b""):
    body = b"WAVE" + chunks_before + chunk(b"data", pcm) + chunks_after
    return b"RIFF" + struct.pack("<I", len(body)) + body


def cue_chunk(points):
    body = struct.pack("<I", len(points))
    for cid, pos in points:
        body += struct.pack("<II4sIII", cid, pos, b"data", 0, 0, pos)
    return chunk(b"cue ", body)


def adtl_chunk(labels, notes, ltxts):
    """Every labl first, then every note, then every ltxt (spec section 6)."""
    sub = b""
    for cid, text in labels:
        sub += chunk(b"labl", struct.pack("<I", cid) + zstr(text))
    for cid, text in notes:
        sub += chunk(b"note", struct.pack("<I", cid) + zstr(text))
    for cid, length in ltxts:
        sub += chunk(b"ltxt", struct.pack("<II4sHHHH", cid, length, b"rgn ", 0, 0, 0, 0))
    return chunk(b"LIST", b"adtl" + sub)


def bext_body(description, reference, tref, history):
    body = bytearray()
    body += fixed(description, 256)
    body += fixed("TT spec v0 kit", 32)
    body += fixed(reference, 32)
    body += fixed("2026-10-22", 10)
    body += fixed("10:00:00", 8)
    body += struct.pack("<II", tref & 0xFFFFFFFF, tref >> 32)
    body += struct.pack("<H", 1)
    body += b"\x00" * 64 + b"\x00" * 190
    body += history.encode("ascii")
    return bytes(body)


def info_chunk(fields):
    sub = b""
    for key, value in fields:
        sub += chunk(key, zstr(value))
    return chunk(b"LIST", b"INFO" + sub)


# ---------------------------------------------------------------------------------------------
# XML: segment list, file-level iXML, XMP
# ---------------------------------------------------------------------------------------------

def el(tag, text):
    return "<%s>%s</%s>" % (tag, xml_escape(str(text)), tag)


def src_bext_body(s):
    """The bext chunk of the source of segment 1, its original chunk in ORIGIN/CHUNK_LIST."""
    return bext_body("Original recording of a door slam", "SRC-0001", s["src_tref"], "A=PCM,F=48000,W=24,M=stereo\r\n")


def segment_lines(s, variant, rich, cue_id=None, conversion=None):
    """`variant` ("ixml", "chunk" or "ogg") picks the search word of segment 3; `cue_id` and `conversion`
    ((CONVERSION, CONVERSION_NOTE)) replace the segment's own values when given (Ogg samples)."""
    kw = s["kw"]
    if s["n"] == 3 and rich:
        kw += ", " + TOKENS[{"ixml": "ixml", "chunk": "chunk", "ogg": "ogg_list"}[variant]]
    if variant == "ixml" and s.get("kw_list_extra"):
        kw += ", " + s["kw_list_extra"]
    if variant == "ogg" and s.get("kw_ogg_extra"):
        kw += ", " + s["kw_ogg_extra"]
    lines = ["<TT_SEGMENT>", el("SEGMENT_ID", s["uid"]), el("CUE_ID", s["cue_id"] if cue_id is None else cue_id),
             el("START_SAMPLE", s["start"]),
             el("LENGTH_SAMPLES", s["length"]), el("NAME", s["name"]), "<USER>",
             el("CATID", s["catid"]), el("CATEGORY", s["category"]), el("SUBCATEGORY", s["sub"]),
             el("CATEGORYFULL", s["categoryfull"]), el("FXNAME", s["fx"]), el("DESCRIPTION", s["desc"]),
             el("KEYWORDS", kw), el("CREATORID", "ACT"), el("SOURCEID", "SELF"), "</USER>"]
    if rich and s["n"] == 1:
        lines += ["<ASWG>", el("contentType", "sfx"), el("catId", s["catid"]), el("category", s["category"]),
                  el("subCategory", s["sub"]), el("fxName", s["fx"]), el("notes", s["desc"]),
                  el("creatorId", "ACT"), el("sourceId", "SELF"), "</ASWG>",
                  "<FIELD_LIST>", "<FIELD>", el("NAME", "Microphone"), el("VALUE", "Sennheiser MKH 8040"),
                  "</FIELD>", "</FIELD_LIST>"]
    if rich and s["n"] == 2:
        lines += ["<FIELD_LIST>", "<FIELD>", el("NAME", "Take"), el("VALUE", "3"), "</FIELD>", "</FIELD_LIST>"]
    lines += ["<ORIGIN>", el("FILENAME", s["src_file"]), el("START_SAMPLE", 0), el("LENGTH_SAMPLES", s["length"]),
              el("SAMPLE_RATE", SR)]
    if rich:
        conv, note = conversion or (s["conversion"], "16 bits to 24 bits" if s["conversion"] == "exact" else None)
        lines += [el("BIT_DEPTH", s["bits"]), el("CHANNELS", 2), el("FORMAT", "wav"),
                  el("TIME_REFERENCE", s["src_tref"]), el("CONVERSION", conv)]
        if note:
            lines.append(el("CONVERSION_NOTE", note))
        if s["n"] == 1:
            lines += ["<CHUNK_LIST>", "<CHUNK>", el("CHUNK_ID", "bext"),
                      el("DATA_BASE64", base64.b64encode(src_bext_body(s)).decode("ascii")), "</CHUNK>", "</CHUNK_LIST>"]
    lines.append("</ORIGIN>")
    lines.append(el("STATUS", "accepted"))
    if rich and s["n"] == 2:
        lines.append(el("TTKIT_UNKNOWN_ELEMENT", "an element of another program: it must survive"))
    lines.append("</TT_SEGMENT>")
    return lines


def segment_list_lines(segs, total, audio_sha, variant, rich, version=SPEC_VERSION, writer=WRITER, rate=SR,
                       cue_ids=None, conversion=None, time_ref=None):
    lines = ["<TT_SEGMENT_LIST>", el("TT_VERSION", version), el("WRITER", writer), el("SAMPLE_RATE", rate),
             el("TOTAL_FRAMES", total), el("AUDIO_SHA256", audio_sha)]
    if time_ref:                                     # (frames since midnight, timecode rate, flag): section 5, 2026-11-10
        lines += [el("TIME_REFERENCE", time_ref[0]), el("TIMECODE_RATE", time_ref[1]), el("TIMECODE_FLAG", time_ref[2])]
    lines.append(el("SEGMENT_COUNT", len(segs)))
    for s in segs:
        lines += segment_lines(s, variant, rich, None if cue_ids is None else cue_ids.get(s["uid"], 0), conversion)
    lines.append("</TT_SEGMENT_LIST>")
    return lines


def summary(segs, token_key="file"):
    names = ", ".join(s["fx"] for s in segs)
    keywords = []
    for s in segs:
        for k in s["kw"].split(","):
            k = k.strip()
            if k and k not in keywords:
                keywords.append(k)
    return "%d sounds: %s. %s" % (len(segs), names, TOKENS[token_key]), ", ".join(keywords + [TOKENS[token_key]])


def ixml_document(segs, total, audio_sha, rich, with_list=True, fxname="TT Doors"):
    desc, keywords = summary(segs)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<BWFXML>", el("IXML_VERSION", "2.10")]
    if rich:
        lines += ["<SPEED>", el("TIMECODE_RATE", "25/1"), el("TIMECODE_FLAG", "NDF"),
                  el("TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_HI", TIME_REFERENCE >> 32),
                  el("TIMESTAMP_SAMPLES_SINCE_MIDNIGHT_LO", TIME_REFERENCE & 0xFFFFFFFF),
                  el("TIMESTAMP_SAMPLE_RATE", SR), "</SPEED>"]
    lines += ["<USER>", el("CATID", segs[0]["catid"]), el("CATEGORY", "DOORS"), el("SUBCATEGORY", segs[0]["sub"]),
              el("FXNAME", fxname), el("DESCRIPTION", desc), el("KEYWORDS", keywords), el("CREATORID", "ACT"),
              el("SOURCEID", "SELF"), "</USER>"]
    if rich:
        lines += ["<ASWG>", el("contentType", "sfx"), el("catId", segs[0]["catid"]), el("category", "DOORS"),
                  el("subCategory", segs[0]["sub"]), el("fxName", fxname), el("notes", desc),
                  el("library", "TT spec samples"), el("creatorId", "ACT"), el("sourceId", "SELF"), "</ASWG>"]
    if with_list:
        lines += segment_list_lines(segs, total, audio_sha, "ixml", rich)
    lines.append("</BWFXML>")
    return ("\n".join(lines) + "\n").encode("utf-8")


def ttsg_document(segs, total, audio_sha):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>'] + segment_list_lines(segs, total, audio_sha, "chunk", True)
    return ("\n".join(lines) + "\n").encode("utf-8")


def xmp_markers_expected(segs):
    out = []
    for s in segs:
        kw = s["kw"] + (", " + TOKENS["xmp"] if s["n"] == 3 else "")
        comment = s["desc"] + (" " + TOKENS["xmp"] if s["n"] == 3 else "")
        out.append(dict(name=s["fx"], start=s["start"], duration=s["length"], comment=comment,
                        params=[["CATID", s["catid"]], ["FXNAME", s["fx"]], ["DESCRIPTION", s["desc"]],
                                ["KEYWORDS", kw], ["SEGMENT_ID", s["uid"]]]))
    return out


def xmp_packet(segs):
    lines = ['<?xpacket begin="%s" id="W5M0MpCehiHzreSzNTczkc9d"?>' % BOM,
             '<x:xmpmeta xmlns:x="adobe:ns:meta/">',
             '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
             '<rdf:Description rdf:about="" xmlns:xmpDM="http://ns.adobe.com/xmp/1.0/DynamicMedia/">',
             "<xmpDM:Tracks>", "<rdf:Bag>", '<rdf:li rdf:parseType="Resource">',
             el("xmpDM:trackName", "CuePoint Markers"), el("xmpDM:trackType", "Cue"),
             el("xmpDM:frameRate", "f%d" % SR), "<xmpDM:markers>", "<rdf:Seq>"]
    for m in xmp_markers_expected(segs):
        lines += ['<rdf:li rdf:parseType="Resource">', el("xmpDM:name", m["name"]),
                  el("xmpDM:startTime", m["start"]), el("xmpDM:duration", m["duration"]),
                  el("xmpDM:comment", m["comment"]), "<xmpDM:cuePointParams>", "<rdf:Seq>"]
        for k, v in m["params"]:
            lines += ['<rdf:li rdf:parseType="Resource">', el("xmpDM:key", k), el("xmpDM:value", v), "</rdf:li>"]
        lines += ["</rdf:Seq>", "</xmpDM:cuePointParams>", "</rdf:li>"]
    lines += ["</rdf:Seq>", "</xmpDM:markers>", "</rdf:li>", "</rdf:Bag>", "</xmpDM:Tracks>", "</rdf:Description>",
              "</rdf:RDF>", "</x:xmpmeta>", '<?xpacket end="w"?>']
    return "\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------------------------
# Building the files
# ---------------------------------------------------------------------------------------------

def marker_chunks(segs, foreign=None, cue_override=None, adtl_after=False):
    """cue + LIST/adtl. cue_override: {cue_id: (new_id, new_pos)} for the self-test."""
    cue_override = cue_override or {}
    pts, labels, notes, ltxts = [], [], [], []
    if foreign:
        pts.append((foreign["cue_id"], foreign["position"]))
        labels.append((foreign["cue_id"], foreign["label"]))
    for s in segs:
        cid, pos = cue_override.get(s["cue_id"], (s["cue_id"], s["start"]))
        pts.append((cid, pos))
        labels.append((cid, s["labl"]))
        notes.append((cid, s["note"]))
        ltxts.append((cid, s["length"]))
    return cue_chunk(pts), adtl_chunk(labels, notes, ltxts)


def build_full(pcm, segs, total, opts=None):
    """tt_v0_full.wav, every carrier. opts (self-test only): no_list, no_ttsg, cue_override, adtl_after, flip_sample,
    reformat_ixml."""
    opts = opts or {}
    audio_sha = hashlib.sha256(pcm).hexdigest()
    desc, keywords = summary(segs)
    ixml = ixml_document(segs, total, audio_sha, True, with_list=not opts.get("no_list"))
    if opts.get("reformat_ixml"):
        ixml = ixml.replace(b"\n", b"\r\n  ")
    cue, adtl = marker_chunks(segs, FOREIGN, opts.get("cue_override"))
    before = (fmt_chunk(2, 24)
              + chunk(b"bext", bext_body(desc, "TTV0-20261022-FULL", TIME_REFERENCE,
                                         "A=PCM,F=48000,W=24,M=stereo,T=TT spec v0 kit\r\n"))
              + chunk(b"iXML", ixml))
    if not opts.get("no_ttsg"):
        before += chunk(b"ttsg", ttsg_document(segs, total, audio_sha))
    before += chunk(b"_PMX", xmp_packet(segs)) + cue
    info = info_chunk([(b"INAM", "TT Doors"), (b"ICMT", desc), (b"IKEY", keywords.replace(", ", "; ")),
                       (b"ISFT", WRITER)])
    if opts.get("adtl_after"):
        before += info
        after = adtl
    else:
        before += adtl + info
        after = b""
    data = pcm
    if opts.get("flip_sample"):
        b = bytearray(pcm)
        b[3 * 2 * 1000] ^= 0x40
        data = bytes(b)
    return wav_bytes(before, data, after)


def build_minimal(pcm, segs, total):
    audio_sha = hashlib.sha256(pcm).hexdigest()
    cue, adtl = marker_chunks(segs)
    ixml = ixml_document(segs, total, audio_sha, False)
    return wav_bytes(fmt_chunk(2, 24) + chunk(b"iXML", ixml) + cue + adtl, pcm)


def build_many(pcm, segs, total):
    audio_sha = hashlib.sha256(pcm).hexdigest()
    cue, adtl = marker_chunks(segs)
    ixml = ixml_document(segs, total, audio_sha, False, fxname="TT Impacts")
    desc, keywords = summary(segs)
    info = info_chunk([(b"INAM", "TT Impacts"), (b"ICMT", desc[:250]), (b"ISFT", WRITER)])
    return wav_bytes(fmt_chunk(1, 16) + chunk(b"iXML", ixml) + cue + adtl + info, pcm)


# ---------------------------------------------------------------------------------------------
# RIFF reading
# ---------------------------------------------------------------------------------------------

def parse_riff(data):
    """-> (form, chunks): form 'RIFF' or 'RF64'; chunk = dict(key, id, offset, size, body)."""
    if len(data) < 12 or data[8:12] != b"WAVE" or data[0:4] not in (b"RIFF", b"RF64"):
        raise ValueError("not a RIFF/WAVE or RF64 file")
    form = data[0:4].decode("ascii")
    pos, end, chunks, ds64_data = 12, len(data), [], None
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"data" and size == 0xFFFFFFFF and ds64_data is not None:
            size = ds64_data
        body = data[pos + 8:pos + 8 + size]
        if cid == b"ds64" and len(body) >= 16:
            ds64_data = struct.unpack("<Q", body[8:16])[0]
        key = cid.decode("latin-1")
        if cid == b"LIST" and len(body) >= 4:
            key = "LIST/" + body[0:4].decode("latin-1")
        chunks.append(dict(key=key, id=cid, offset=pos, size=size, body=body))
        pos += 8 + size + (size & 1)
    return form, chunks


def strip_xml(body):
    text = body.rstrip(b"\x00 \r\n\t").decode("utf-8", "replace")
    return text.lstrip(BOM).strip()


def flatten(elem, prefix=""):
    """Element tree -> {path: text}; repeated children are numbered (TAG#0, TAG#1...)."""
    out, seen = {}, {}
    for child in list(elem):
        n = seen.get(child.tag, 0)
        seen[child.tag] = n + 1
        key = "%s%s#%d" % (prefix, child.tag, n)
        if len(child):
            out.update(flatten(child, key + "/"))
        else:
            out[key] = (child.text or "").strip()
    return out


def canon_list(elem):
    """TT_SEGMENT_LIST element -> dict(header, segments=[{path: text}])."""
    header, segments = {}, []
    for child in list(elem):
        if child.tag == "TT_SEGMENT":
            segments.append(flatten(child))
        elif not len(child):
            header[child.tag] = (child.text or "").strip()
    return dict(header=header, segments=segments)


def find_list(root):
    if root.tag == "TT_SEGMENT_LIST":
        return root
    return root.find("TT_SEGMENT_LIST")


def ixml_parts(body):
    """-> (root or None, parse error text, {USER, ASWG, SPEED flat}, list canon or None)."""
    try:
        root = ET.fromstring(strip_xml(body))
    except ET.ParseError as e:
        return None, str(e), {}, None
    parts = {}
    for tag in ("USER", "ASWG", "SPEED"):
        e = root.find(tag)
        if e is not None:
            parts[tag] = flatten(e)
    lst = find_list(root)
    return root, "", parts, (canon_list(lst) if lst is not None else None)


def read_cue(body):
    n = struct.unpack("<I", body[0:4])[0] if len(body) >= 4 else 0
    pts = {}
    for i in range(n):
        o = 4 + 24 * i
        if o + 24 > len(body):
            break
        cid, _pos, _fcc, _cs, _bs, off = struct.unpack("<II4sIII", body[o:o + 24])
        pts[cid] = off
    return pts


def read_adtl(body):
    """-> (labels, notes, ltxts, order list of sub-chunk ids)."""
    labels, notes, ltxts, order = {}, {}, {}, []
    pos = 4
    while pos + 8 <= len(body):
        sid = body[pos:pos + 4]
        size = struct.unpack("<I", body[pos + 4:pos + 8])[0]
        sub = body[pos + 8:pos + 8 + size]
        order.append(sid.decode("latin-1"))
        if len(sub) >= 4:
            cid = struct.unpack("<I", sub[0:4])[0]
            if sid in (b"labl", b"note"):
                text = sub[4:].split(b"\x00")[0].decode("latin-1")
                (labels if sid == b"labl" else notes)[cid] = text
            elif sid == b"ltxt" and len(sub) >= 8:
                ltxts[cid] = struct.unpack("<I", sub[4:8])[0]
        pos += 8 + size + (size & 1)
    return labels, notes, ltxts, order


def read_bext(body):
    if len(body) < 346:
        return {}
    tref = struct.unpack("<Q", body[338:346])[0]
    return dict(description=body[0:256].split(b"\x00")[0].decode("latin-1"), time_reference=tref)


def read_info(body):
    out, pos = {}, 4
    while pos + 8 <= len(body):
        sid = body[pos:pos + 4].decode("latin-1")
        size = struct.unpack("<I", body[pos + 4:pos + 8])[0]
        out[sid] = body[pos + 8:pos + 8 + size].split(b"\x00")[0].decode("latin-1")
        pos += 8 + size + (size & 1)
    return out


XMP_NS = {"x": "adobe:ns:meta/", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
          "xmpDM": "http://ns.adobe.com/xmp/1.0/DynamicMedia/"}


def read_xmp_markers(body):
    """-> list of marker dicts, or None when the packet cannot be parsed. Element form only (attribute form
    as written by some tools is reported as a difference, not decoded)."""
    text = body.rstrip(b"\x00").decode("utf-8", "replace")
    a, b = text.find("<x:xmpmeta"), text.rfind("</x:xmpmeta>")
    if a < 0 or b < 0:
        return None
    try:
        root = ET.fromstring(text[a:b + len("</x:xmpmeta>")])
    except ET.ParseError:
        return None
    dm = "{%s}" % XMP_NS["xmpDM"]
    rdf = "{%s}" % XMP_NS["rdf"]
    out = []
    for marker_list in root.iter(dm + "markers"):
        for li in marker_list.iter(rdf + "li"):
            name = li.find(dm + "name")
            if name is None:
                continue
            params = []
            cpp = li.find(dm + "cuePointParams")
            if cpp is not None:
                for p in cpp.iter(rdf + "li"):
                    k, v = p.find(dm + "key"), p.find(dm + "value")
                    if k is not None:
                        params.append([(k.text or "").strip(), ((v.text if v is not None else "") or "").strip()])
            def txt(tag):
                e = li.find(dm + tag)
                return (e.text or "").strip() if e is not None else ""
            out.append(dict(name=(name.text or "").strip(), start=txt("startTime"), duration=txt("duration"),
                            comment=txt("comment"), params=params))
    return out


# ---------------------------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------------------------

def describe(data, segs, foreign, xmp_expected):
    form, chunks = parse_riff(data)
    keys = [c["key"] for c in chunks]
    data_index = keys.index("data")
    m = dict(form=form, chunks=[dict(key=c["key"], size=c["size"], sha256=hashlib.sha256(c["body"]).hexdigest(),
                                     before_data=i < data_index) for i, c in enumerate(chunks)])
    by = {c["key"]: c for c in chunks}
    fmt = by["fmt "]["body"]
    channels, sr, bits = struct.unpack("<H", fmt[2:4])[0], struct.unpack("<I", fmt[4:8])[0], struct.unpack("<H", fmt[14:16])[0]
    pcm = by["data"]["body"]
    m.update(sample_rate=sr, channels=channels, bits=bits, frames=len(pcm) // (channels * bits // 8),
             audio_sha256=hashlib.sha256(pcm).hexdigest())
    _root, err, parts, lst = ixml_parts(by["iXML"]["body"])
    m["ixml_parts"], m["ixml_list"] = parts, lst
    if "ttsg" in by:
        _r, _e, _p, m["ttsg_list"] = ixml_parts(by["ttsg"]["body"])
    if "bext" in by:
        m["bext"] = read_bext(by["bext"]["body"])
    if "LIST/INFO" in by:
        m["info"] = read_info(by["LIST/INFO"]["body"])
    if "_PMX" in by:
        m["xmp_markers"] = read_xmp_markers(by["_PMX"]["body"])
        m["xmp_expected"] = xmp_expected
    cue = read_cue(by["cue "]["body"])
    labels, notes, ltxts, _order = read_adtl(by["LIST/adtl"]["body"])
    m["cue"] = {str(k): v for k, v in cue.items()}
    m["labels"] = {str(k): v for k, v in labels.items()}
    m["notes"] = {str(k): v for k, v in notes.items()}
    m["ltxt"] = {str(k): v for k, v in ltxts.items()}
    m["foreign_cue"] = foreign["cue_id"] if foreign else None
    m["segments"] = [dict(n=s["n"], uid=s["uid"], cue_id=s["cue_id"], start=s["start"], length=s["length"],
                          name=s["name"]) for s in segs]
    return m


# ---------------------------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------------------------

class Report:
    def __init__(self, title, carriers=None):
        self.carriers = carriers or CARRIERS
        self.title, self.lines, self.status = title, [], {c: "n/a" for c in self.carriers}
        self.extra = []

    def set(self, carrier, status, detail=""):
        self.status[carrier] = status
        self.lines.append("[%s] %s%s" % (status, carrier, (": " + detail) if detail else ""))

    def info(self, text):
        self.lines.append("       " + text)

    def summary_line(self):
        parts = ["%s=%s" % (c, self.status[c]) for c in self.carriers]
        parts.append("extra=%s" % (",".join(self.extra) if self.extra else "none"))
        return "RESUME " + " ".join(parts)

    def text(self):
        return "\n".join(["== " + self.title] + self.lines + [self.summary_line()])


def compare_dict(expected, found, label, rep, limit=4):
    diffs = []
    for k in sorted(set(expected) | set(found)):
        if expected.get(k) != found.get(k):
            diffs.append("%s %s: expected %r, found %r" % (label, k, expected.get(k), found.get(k)))
    for d in diffs[:limit]:
        rep.info(d)
    if len(diffs) > limit:
        rep.info("... %d more difference(s)" % (len(diffs) - limit))
    return not diffs


def compare_list(exp, found, rep, label):
    """Segment lists (canon) compared by SEGMENT_ID. True when equal."""
    if exp is None:
        return found is None
    if found is None:
        return False
    ok = compare_dict(exp["header"], found["header"], label + " header", rep)
    ex = {s.get("SEGMENT_ID#0"): s for s in exp["segments"]}
    fd = {s.get("SEGMENT_ID#0"): s for s in found["segments"]}
    missing = [k for k in ex if k not in fd]
    added = [k for k in fd if k not in ex]
    if missing:
        rep.info("%s: %d segment(s) missing, first %s" % (label, len(missing), missing[0]))
    if added:
        rep.info("%s: %d unknown segment(s), first %s" % (label, len(added), added[0]))
    ok = ok and not missing and not added
    changed = 0
    for k in ex:
        if k in fd and ex[k] != fd[k]:
            changed += 1
            if changed <= 2:
                compare_dict(ex[k], fd[k], "%s segment %s" % (label, k[:8]), rep, limit=3)
    if changed:
        rep.info("%s: %d segment(s) changed" % (label, changed))
    order_ok = [s.get("SEGMENT_ID#0") for s in exp["segments"]] == [s.get("SEGMENT_ID#0") for s in found["segments"]]
    if not order_ok and not missing and not added:
        rep.info("%s: same segments, other order" % label)
    return ok and changed == 0 and order_ok


def same_bytes(entry, key, body):
    for c in entry["chunks"]:
        if c["key"] == key:
            return c["sha256"] == hashlib.sha256(body).hexdigest()
    return False


def check_bytes(data, entry, title):
    rep = Report(title)
    try:
        form, chunks = parse_riff(data)
    except ValueError as e:
        rep.set("audio", "LOST", str(e))
        return rep
    keys = [c["key"] for c in chunks]
    by = {}
    for c in chunks:
        by.setdefault(c["key"], c)
    expected_keys = [c["key"] for c in entry["chunks"]]
    rep.extra = sorted(set(k for k in keys if k not in expected_keys))
    if form != entry["form"]:
        rep.info("form %s (was %s)" % (form, entry["form"]))
    dups = sorted(set(k for k in keys if keys.count(k) > 1))
    if dups:
        rep.info("chunks present more than once: %s" % ", ".join(dups))

    # audio and format
    if "data" not in by:
        rep.set("audio", "LOST", "no data chunk")
    else:
        pcm = by["data"]["body"]
        sha = hashlib.sha256(pcm).hexdigest()
        rep.set("audio", "OK" if sha == entry["audio_sha256"] else "CHANGED",
                "" if sha == entry["audio_sha256"] else "data differs (%d bytes, was %d frames)" % (len(pcm), entry["frames"]))
    if "fmt " not in by:
        rep.set("fmt", "LOST")
    else:
        rep.set("fmt", "OK" if same_bytes(entry, "fmt ", by["fmt "]["body"]) else "CHANGED")

    # bext
    if "bext" in [c["key"] for c in entry["chunks"]]:
        if "bext" not in by:
            rep.set("bext", "LOST")
        elif same_bytes(entry, "bext", by["bext"]["body"]):
            rep.set("bext", "OK")
        else:
            got = read_bext(by["bext"]["body"])
            same = got.get("time_reference") == entry["bext"]["time_reference"] and got.get("description") == entry["bext"]["description"]
            rep.set("bext", "SAME" if same else "CHANGED", "TimeReference %s (was %s)" % (got.get("time_reference"), entry["bext"]["time_reference"]))

    # LIST/INFO
    if "LIST/INFO" in expected_keys:
        if "LIST/INFO" not in by:
            rep.set("info", "LOST")
        elif same_bytes(entry, "LIST/INFO", by["LIST/INFO"]["body"]):
            rep.set("info", "OK")
        else:
            rep.set("info", "SAME" if compare_dict(entry["info"], read_info(by["LIST/INFO"]["body"]), "INFO", rep) else "CHANGED")

    # iXML: file-level part and segment list
    if "iXML" not in by:
        rep.set("ixml_file", "LOST")
        rep.set("ixml_list", "LOST")
        found_list = None
    else:
        body = by["iXML"]["body"]
        root, err, parts, found_list = ixml_parts(body)
        if same_bytes(entry, "iXML", body):
            rep.set("ixml_file", "OK")
            rep.set("ixml_list", "OK")
        elif root is None:
            rep.set("ixml_file", "CHANGED", "iXML no longer parses: " + err)
            rep.set("ixml_list", "LOST")
        else:
            same_file = True
            for tag in set(entry["ixml_parts"]) | set(parts):
                if tag not in parts:
                    rep.info("iXML %s object removed" % tag)
                    same_file = False
                elif not compare_dict(entry["ixml_parts"].get(tag, {}), parts[tag], "iXML " + tag, rep):
                    same_file = False
            rep.set("ixml_file", "SAME" if same_file else "CHANGED")
            if found_list is None:
                rep.set("ixml_list", "LOST", "TT_SEGMENT_LIST missing")
            else:
                rep.set("ixml_list", "SAME" if compare_list(entry["ixml_list"], found_list, rep, "iXML list") else "CHANGED")

    # ttsg
    if entry.get("ttsg_list") is not None:
        if "ttsg" not in by:
            rep.set("ttsg", "LOST")
        elif same_bytes(entry, "ttsg", by["ttsg"]["body"]):
            rep.set("ttsg", "OK")
        else:
            _r, err, _p, lst = ixml_parts(by["ttsg"]["body"])
            rep.set("ttsg", "SAME" if compare_list(entry["ttsg_list"], lst, rep, "ttsg") else "CHANGED", err)

    # XMP
    if entry.get("xmp_expected") is not None:
        if "_PMX" not in by:
            rep.set("xmp", "LOST")
        elif same_bytes(entry, "_PMX", by["_PMX"]["body"]):
            rep.set("xmp", "OK")
        else:
            got = read_xmp_markers(by["_PMX"]["body"])
            if not got:
                rep.set("xmp", "CHANGED", "no xmpDM marker found in the packet (rewritten or attribute form)")
            else:
                exp = [dict(m, start=str(m["start"]), duration=str(m["duration"])) for m in entry["xmp_expected"]]
                same = exp == got
                rep.set("xmp", "SAME" if same else "CHANGED", "%d marker(s) found, %d expected" % (len(got), len(exp)))

    # cue
    if "cue " not in by:
        rep.set("cue", "LOST")
    else:
        found = read_cue(by["cue "]["body"])
        exp = {int(k): v for k, v in entry["cue"].items()}
        notes = []
        for cid, pos in exp.items():
            if cid not in found:
                other = [k for k, v in found.items() if v == pos and k not in exp]
                notes.append("cue %d renumbered as %d" % (cid, other[0]) if other else "cue %d missing" % cid)
            elif found[cid] != pos:
                notes.append("cue %d moved %d -> %d" % (cid, pos, found[cid]))
        added = [k for k in found if k not in exp and not any(n.endswith(" %d" % k) for n in notes)]
        if added:
            notes.append("%d cue point(s) added (ids %s)" % (len(added), ", ".join(str(a) for a in added[:5])))
        if entry.get("foreign_cue") is not None and entry["foreign_cue"] in found and found[entry["foreign_cue"]] == exp[entry["foreign_cue"]]:
            pass
        rep.set("cue", "OK" if not notes and same_bytes(entry, "cue ", by["cue "]["body"]) else ("SAME" if not notes else "CHANGED"),
                "; ".join(notes[:4]))

    # adtl
    if "LIST/adtl" not in by:
        rep.set("adtl", "LOST")
    else:
        labels, notes_, ltxts, order = read_adtl(by["LIST/adtl"]["body"])
        same = True
        for name, exp_d, got_d in (("labl", entry["labels"], labels), ("note", entry["notes"], notes_),
                                   ("ltxt", entry["ltxt"], ltxts)):
            if not compare_dict(exp_d, {str(k): v for k, v in got_d.items()}, name, rep):
                same = False
        first_other = next((i for i, s in enumerate(order) if s != "labl"), len(order))
        if "labl" in order[first_other:]:
            rep.info("a labl comes after a note or ltxt (some readers stop at the first non-labl)")
            same = False
        rep.set("adtl", "OK" if same and same_bytes(entry, "LIST/adtl", by["LIST/adtl"]["body"]) else ("SAME" if same else "CHANGED"))

    # chunk order relative to data
    if "data" in keys:
        di = keys.index("data")
        moved = [c["key"] for c in entry["chunks"] if c["key"] in keys and c["key"] != "data"
                 and (keys.index(c["key"]) < di) != c["before_data"]]
        rep.set("order", "OK" if not moved else "CHANGED", ("moved across data: " + ", ".join(moved)) if moved else "")

    # integrity rules of the spec (section 8), on the list as found
    if found_list is not None and "data" in by:
        h = found_list["header"]
        pcm = by["data"]["body"]
        fmt = by["fmt "]["body"] if "fmt " in by else None
        if fmt is not None:
            align = struct.unpack("<H", fmt[12:14])[0] or 1
            frames = len(pcm) // align
            if h.get("TOTAL_FRAMES") != str(frames):
                rep.info("spec check: TOTAL_FRAMES %s but the file has %d frames" % (h.get("TOTAL_FRAMES"), frames))
        if h.get("AUDIO_SHA256") and h["AUDIO_SHA256"] != hashlib.sha256(pcm).hexdigest():
            rep.info("spec check: AUDIO_SHA256 no longer matches the audio: segments may be wrong")
        if "cue " in by:
            found = read_cue(by["cue "]["body"])
            moved = 0
            for s in found_list["segments"]:
                cid = s.get("CUE_ID#0")
                if cid and cid != "0" and int(cid) in found and str(found[int(cid)]) != s.get("START_SAMPLE#0"):
                    moved += 1
            if moved:
                rep.info("spec check: %d segment(s) whose cue point is not at START_SAMPLE (moved by a program)" % moved)
    return rep


# ---------------------------------------------------------------------------------------------
# Ogg files (draft 0.2, SPEC.md section 11): Vorbis comments carry the summary, the chapters and the list
# ---------------------------------------------------------------------------------------------

def _ogg_crc_table():
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
        table.append(r & 0xFFFFFFFF)
    return table


OGG_CRC_TABLE = _ogg_crc_table()


def ogg_crc(data):
    """CRC-32 of an Ogg page (polynomial 0x04C11DB7, initial value 0, not reflected)."""
    crc, table = 0, OGG_CRC_TABLE
    for b in data:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ table[(crc >> 24) ^ b]
    return crc


def ogg_page(htype, granule, serial, seq, lacing, body):
    page = (b"OggS" + bytes([0, htype]) + struct.pack("<qIII", granule, serial, seq, 0) + bytes([len(lacing)])
            + bytes(lacing) + body)
    return page[:22] + struct.pack("<I", ogg_crc(page)) + page[26:]


def ogg_renumber(raw, seq):
    """The same page with another sequence number (and its CRC)."""
    page = raw[:18] + struct.pack("<I", seq) + b"\x00\x00\x00\x00" + raw[26:]
    return page[:22] + struct.pack("<I", ogg_crc(page)) + page[26:]


def ogg_lacing(size):
    return [255] * (size // 255) + [size % 255]


def parse_ogg_comments(pkt, magic):
    """Comment header -> (vendor bytes, ["FIELD=value", ...])."""
    if not pkt.startswith(magic):
        raise ValueError("comment header not found")
    pos, comments = len(magic), []
    try:
        (n,) = struct.unpack("<I", pkt[pos:pos + 4])
        vendor = pkt[pos + 4:pos + 4 + n]
        pos += 4 + n
        (count,) = struct.unpack("<I", pkt[pos:pos + 4])
        pos += 4
        for _ in range(count):
            (n,) = struct.unpack("<I", pkt[pos:pos + 4])
            if pos + 4 + n > len(pkt):
                raise ValueError("comment beyond the header")
            comments.append(pkt[pos + 4:pos + 4 + n].decode("utf-8", "replace"))
            pos += 4 + n
    except struct.error:
        raise ValueError("malformed comment header")
    return vendor, comments


def build_ogg_comments(magic, vendor, comments):
    out = bytearray(magic + struct.pack("<I", len(vendor)) + vendor + struct.pack("<I", len(comments)))
    for c in comments:
        b = c.encode("utf-8")
        out += struct.pack("<I", len(b)) + b
    if magic == b"\x03vorbis":
        out += b"\x01"                                # Vorbis framing bit
    return bytes(out)


def read_ogg(data):
    """Pages, packets [(bytes, index of the page where it ends)], codec facts and the comments of an Ogg Vorbis or
    Opus file. Frames: decoded samples per channel (Opus: at 48 kHz, after the pre-skip). ValueError otherwise."""
    pages, pos = [], 0
    while pos < len(data):
        if data[pos:pos + 4] != b"OggS" or len(data) < pos + 27:
            raise ValueError("no Ogg page at byte %d" % pos)
        htype = data[pos + 5]
        granule, serial, seq, crc = struct.unpack("<qIII", data[pos + 6:pos + 26])
        nseg = data[pos + 26]
        lacing = data[pos + 27:pos + 27 + nseg]
        start = pos + 27 + nseg
        end = start + sum(lacing)
        if len(lacing) != nseg or end > len(data):
            raise ValueError("truncated Ogg page at byte %d" % pos)
        raw = data[pos:end]
        pages.append(dict(htype=htype, granule=granule, serial=serial, seq=seq, lacing=lacing,
                          body=data[start:end], raw=raw,
                          crc_ok=ogg_crc(raw[:22] + b"\x00\x00\x00\x00" + raw[26:]) == crc))
        pos = end
    if not pages:
        raise ValueError("empty file")
    first_serial = pages[0]["serial"]
    packets, cur = [], bytearray()
    for i, p in enumerate(pages):
        if p["serial"] != first_serial:
            continue
        off = 0
        for lv in p["lacing"]:
            cur += p["body"][off:off + lv]
            off += lv
            if lv < 255:
                packets.append((bytes(cur), i))
                cur = bytearray()
    if not packets:
        raise ValueError("no packet")
    head = packets[0][0]
    if head.startswith(b"\x01vorbis") and len(head) >= 16:
        codec, nhead, magic, channels = "vorbis", 3, b"\x03vorbis", head[11]
        rate, preskip = struct.unpack("<I", head[12:16])[0], 0
    elif head.startswith(b"OpusHead") and len(head) >= 19:
        codec, nhead, magic, channels = "opus", 2, b"OpusTags", head[9]
        rate, preskip = 48000, struct.unpack("<H", head[10:12])[0]
    else:
        raise ValueError("neither Ogg Vorbis nor Ogg Opus")
    if len(packets) < nhead:
        raise ValueError("header packets missing")
    vendor, comments = parse_ogg_comments(packets[1][0], magic)
    granules = [p["granule"] for p in pages if p["serial"] == first_serial and p["granule"] >= 0]
    audio, heads = hashlib.sha256(), hashlib.sha256(packets[0][0] + (packets[2][0] if codec == "vorbis" else b""))
    for pkt, _i in packets[nhead:]:
        audio.update(pkt)
    return dict(pages=pages, packets=packets, codec=codec, nhead=nhead, magic=magic, rate=rate, channels=channels,
                preskip=preskip, total=(granules[-1] - preskip) if granules else 0,
                serials=sorted(set(p["serial"] for p in pages)), crc_errors=sum(1 for p in pages if not p["crc_ok"]),
                vendor=vendor, comments=comments, audio_sha256=audio.hexdigest(), headers_sha256=heads.hexdigest(),
                unfinished=len(cur))


def comment_map(comments):
    """["FIELD=value"] -> {FIELD in upper case: [values in order]} (field names are case-insensitive)."""
    out = {}
    for c in comments:
        key, sep, value = c.partition("=")
        if sep:
            out.setdefault(key.upper(), []).append(value)
    return out


def is_chapter_key(key):
    rest = key[7:] if key.startswith("CHAPTER") else ""
    return rest.isdigit() or (rest.endswith("NAME") and rest[:-4].isdigit())


def ogg_chapters(cm):
    """{"001": [time, name]} from the CHAPTERnnn / CHAPTERnnnNAME comments."""
    out = {}
    for key, values in cm.items():
        rest = key[7:] if key.startswith("CHAPTER") else ""
        if rest.isdigit():
            out.setdefault(rest, ["", ""])[0] = values[0]
        elif rest.endswith("NAME") and rest[:-4].isdigit():
            out.setdefault(rest[:-4], ["", ""])[1] = values[0]
    return out


def chapter_ms(frames, rate):
    """Start of a chapter in whole milliseconds (section 11.2): frames * 1000 / rate rounded to the nearest, a start
    exactly on a half millisecond to the even one (as Python's round). Integers: no floating-point error."""
    q, r = divmod(frames * 1000, rate)
    return q + 1 if 2 * r > rate or (2 * r == rate and q % 2) else q


def chapter_time(frames, rate):
    ms = chapter_ms(frames, rate)
    h, rest = divmod(ms, 3600000)
    m, rest = divmod(rest, 60000)
    s, ms = divmod(rest, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)


CHAPTER_TIME = re.compile(r"(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})")


def chapter_at(text, frames, rate, tolerance_ms=0.5):
    """True when the chapter time `text` is at most `tolerance_ms` away from the start `frames` (section 11.2):
    0.5 for a writer (the nearest millisecond, either neighbour when the start is exactly on a half millisecond:
    JavaScript and C++ round it up, the kit to even), 1 for a reader. None when `text` is not HH:MM:SS.mmm."""
    m = CHAPTER_TIME.fullmatch(text)
    if not m:
        return None
    h, mi, s, ms = (int(g) for g in m.groups())
    return abs((((h * 60 + mi) * 60 + s) * 1000 + ms) * rate - frames * 1000) <= tolerance_ms * rate


def paginate_headers(packets, max_segments=255):
    """Pages of header packets: (header type, granule, lacing, body). A packet may continue on the next page;
    granule 0 on a page where a packet ends, -1 on the others."""
    segs = []
    for pkt in packets:
        lac = ogg_lacing(len(pkt))
        segs += [(lv, k == len(lac) - 1) for k, lv in enumerate(lac)]
    stream, pages, i, off, continued = b"".join(packets), [], 0, 0, False
    while i < len(segs):
        part = segs[i:i + max_segments]
        size = sum(lv for lv, _end in part)
        pages.append((0x01 if continued else 0x00, 0 if any(end for _lv, end in part) else -1,
                      [lv for lv, _end in part], stream[off:off + size]))
        continued = not part[-1][1]
        i += max_segments
        off += size
    return pages


def ogg_with_comments(data, comments, max_segments=255):
    """The same stream with a new comment header: identification packet, Vorbis setup packet and every audio page
    kept byte for byte; the header pages are rebuilt, then every page renumbered with its CRC."""
    info = read_ogg(data)
    pages, packets, nhead = info["pages"], info["packets"], info["nhead"]
    if len(info["serials"]) != 1:
        raise ValueError("more than one logical stream")
    last_head = packets[nhead - 1][1]
    if sum(len(p["body"]) for p in pages[:last_head + 1]) != sum(len(pkt) for pkt, _i in packets[:nhead]):
        raise ValueError("audio data shares a page with the header packets")
    serial = pages[0]["serial"]
    heads = [build_ogg_comments(info["magic"], info["vendor"], comments)]
    if info["codec"] == "vorbis":
        heads.append(packets[2][0])
    out = [ogg_page(0x02, 0, serial, 0, ogg_lacing(len(packets[0][0])), packets[0][0])]
    for htype, granule, lacing, body in paginate_headers(heads, max_segments):
        out.append(ogg_page(htype, granule, serial, len(out), lacing, body))
    for p in pages[last_head + 1:]:
        out.append(ogg_renumber(p["raw"], len(out)))
    return b"".join(out)


def ogg_flip_audio_byte(data):
    """Self-check helper: one byte of the first audio page changed, its CRC fixed."""
    info = read_ogg(data)
    k = info["packets"][info["nhead"]][1]
    p = info["pages"][k]
    raw = bytearray(p["raw"])
    raw[len(raw) - len(p["body"]) // 2 - 1] ^= 0x01
    page = bytes(raw[:22]) + b"\x00\x00\x00\x00" + bytes(raw[26:])
    off = sum(len(q["raw"]) for q in info["pages"][:k])
    return data[:off] + page[:22] + struct.pack("<I", ogg_crc(page)) + page[26:] + data[off + len(raw):]


def ogg_moved_segment(data, delta, chapter_text=None):
    """Self-check helper: the first segment of the list starts `delta` frames later, its chapter at `chapter_text`
    (None: unchanged)."""
    comments = read_ogg(data)["comments"]
    key = lambda c: c.partition("=")[0].upper()          # noqa: E731
    root = ET.fromstring(next(c for c in comments if key(c) == "TT_SEGMENT_LIST").partition("=")[2])
    seg = root.find("TT_SEGMENT")
    seg.find("START_SAMPLE").text = str(int(seg.find("START_SAMPLE").text) + delta)
    chapter = "CHAPTER%03d" % int(seg.find("CUE_ID").text)
    out = []
    for c in comments:
        if key(c) == "TT_SEGMENT_LIST":
            c = "TT_SEGMENT_LIST=" + ET.tostring(root, encoding="unicode")
        elif chapter_text is not None and key(c) == chapter:
            c = chapter + "=" + chapter_text
        out.append(c)
    return ogg_with_comments(data, out)


def ogg_segments(key, fsegs, msegs):
    """Copies of the WAV samples' segments with the Ogg search words -> (segments, rich, foreign marker)."""
    if key == "full":
        segs = [dict(s) for s in fsegs]
        segs[2]["chapter_token"] = TOKENS["ogg_chapter"]
        return segs, True, FOREIGN
    segs = [dict(s) for s in msegs]
    segs[396]["kw_ogg_extra"] = TOKENS["ogg_many_list"]
    segs[397]["chapter_token"] = TOKENS["ogg_many_chap"]
    return segs, False, None


def ogg_tt_comments(segs, total, rate, audio_sha, rich, title, foreign=None, conversion=None, time_ref=None):
    """Comments of an Ogg sample (section 11): summary, chapters of every marker in time order (CUE_ID = chapter
    number), then the segment list on one line (with the file time reference `time_ref` when given)."""
    marks = sorted([(s["start"], 1, s) for s in segs] + ([(foreign["position"], 0, None)] if foreign else []),
                   key=lambda m: (m[0], m[1]))
    chapters, cue_ids = [], {}
    for num, (pos, _kind, s) in enumerate(marks, start=1):
        if s is None:
            name = foreign["label"]
        else:
            name = s["fx"] + ((" " + s["chapter_token"]) if s.get("chapter_token") else "")
            cue_ids[s["uid"]] = num
        chapters.append(("%03d" % num, chapter_time(pos, rate), name))
    desc, keywords = summary(segs, "ogg_file")
    lst = "".join(segment_list_lines(segs, total, audio_sha, "ogg", rich, OGG_SPEC_VERSION, OGG_WRITER, rate,
                                     cue_ids, conversion, time_ref))
    comments = ["TITLE=" + title, "DESCRIPTION=" + desc, "COMMENT=" + desc, "KEYWORDS=" + keywords]
    for num, t, name in chapters:
        comments += ["CHAPTER%s=%s" % (num, t), "CHAPTER%sNAME=%s" % (num, name)]
    comments.append("TT_SEGMENT_LIST=" + lst)
    return comments


# ---------------------------------------------------------------------------------------------
# Draft 0.3: the segment table (section 11.5), deflated original chunks (section 5.2), the weight (section 12)
# ---------------------------------------------------------------------------------------------

TABLE_HEADER = ("TT_VERSION", "WRITER", "SAMPLE_RATE", "TOTAL_FRAMES", "AUDIO_SHA256", "TIME_REFERENCE", "TIMECODE_RATE",
                "TIMECODE_FLAG", "SEGMENT_COUNT")
STRUCTURAL = ("SEGMENT_ID", "CUE_ID", "START_SAMPLE", "LENGTH_SAMPLES")


def _plain_leaf(e):
    """An element that holds text only: no child, no attribute."""
    return len(e) == 0 and not e.attrib


def _xml_text(e):
    """An element as XML text on its own, without the text that follows it in its parent (its tail)."""
    tail, e.tail = e.tail, None
    try:
        return ET.tostring(e, encoding="unicode")
    finally:
        e.tail = tail


def _paths_of(e):
    """The (path, text) pairs of a child of TT_SEGMENT that appears once, or None when the paths of section 11.5
    cannot express it."""
    if e.attrib or e.tag == "XML":
        return None
    if len(e) == 0:
        return [(e.tag, e.text or "")]
    if (e.text or "").strip():
        return None                                          # text and children mixed
    kids = list(e)
    if e.tag == "FIELD_LIST":
        names = [f.findtext("NAME") or "" for f in kids]
        simple = all(f.tag == "FIELD" and not f.attrib and not (f.text or "").strip()
                     and [x.tag for x in f] == ["NAME", "VALUE"] and all(_plain_leaf(x) for x in f) for f in kids)
        if simple and len(set(names)) == len(names):
            return [("FIELD/" + n, f.findtext("VALUE") or "") for n, f in zip(names, kids)]
        return None
    if e.tag != "FIELD" and all(_plain_leaf(x) for x in kids) and len({x.tag for x in kids}) == len(kids):
        return [(e.tag + "/" + x.tag, x.text or "") for x in kids]   # USER, ASWG, ORIGIN, a block of a program
    return None


def segment_pairs(seg):
    """A TT_SEGMENT element as (path, text) pairs, in the order of its elements. What the paths cannot express goes
    whole, as XML text, into one ("XML", text) pair, where the first such element was: an element with attributes or
    deeper children (an ORIGIN with a CHUNK_LIST), every occurrence of a repeated element, a FIELD_LIST with a repeated
    field name or a FIELD that is not NAME and VALUE."""
    counts = {}
    for e in seg:
        counts[e.tag] = counts.get(e.tag, 0) + 1
    out, extra, at = [], [], None
    for e in seg:
        pairs = _paths_of(e) if counts[e.tag] == 1 else None
        if pairs is None:
            if at is None:
                at = len(out)
                out.append(None)
            extra.append(_xml_text(e))
        else:
            out += pairs
    if extra:
        out[at] = ("XML", "".join(extra))
    return out


def list_model(listel):
    """TT_SEGMENT_LIST element -> (header {name: text}, segments [[(path, text)]]). The header holds the elements of the
    list header (section 5) that appear once with text only; every other child of the list but the segments goes
    whole, as XML text, into header["XML"]."""
    kids = [e for e in listel if e.tag != "TT_SEGMENT"]
    counts = {}
    for e in kids:
        counts[e.tag] = counts.get(e.tag, 0) + 1
    header, extra = {}, []
    for e in kids:
        if e.tag in TABLE_HEADER and counts[e.tag] == 1 and _plain_leaf(e):
            header[e.tag] = e.text or ""
        else:
            extra.append(_xml_text(e))
    if extra:
        header["XML"] = "".join(extra)
    return header, [segment_pairs(s) for s in listel.findall("TT_SEGMENT")]


def list_xml(header, segments):
    """(header, segments) -> the XML list of section 5 on one line: the header elements, the other elements of the
    list, then each segment with its elements in the order of its pairs (a block where its first path is)."""
    out = ["<TT_SEGMENT_LIST>"] + [el(k, v) for k, v in header.items() if k != "XML"]
    if header.get("XML"):
        out.append(header["XML"])
    for pairs in segments:
        out.append("<TT_SEGMENT>")
        groups, order = {}, []
        for path, value in pairs:
            head, sep, tail = path.partition("/")
            if path == "XML":
                order.append(("raw", value))
            elif not sep:
                order.append(("leaf", el(head, value)))
            else:
                g = "FIELD_LIST" if head == "FIELD" else head
                if g not in groups:
                    groups[g] = []
                    order.append(("group", g))
                groups[g].append("<FIELD>%s%s</FIELD>" % (el("NAME", tail), el("VALUE", value)) if head == "FIELD"
                                 else el(tail, value))
        for kind, x in order:
            out.append("<%s>%s</%s>" % (x, "".join(groups[x]), x) if kind == "group" else x)
        out.append("</TT_SEGMENT>")
    out.append("</TT_SEGMENT_LIST>")
    return "".join(out)


def _merged_order(segments):
    """One order of the paths for every segment: each path right after the path that precedes it where it first
    appears (segments written by one program share their order)."""
    order, seen = [], set()
    for pairs in segments:
        prev = None
        for path, _v in pairs:
            if path not in seen:
                order.insert(order.index(prev) + 1 if prev is not None else 0, path)
                seen.add(path)
            prev = path
    return order


def table_text(header, segments, id_namespace=None, keep_order=True):
    """(header, segments) -> the value of a TT_SEGMENT_TABLE comment (section 11.5): the values every segment shares in
    DEFAULTS, the others in COLUMNS and ROWS (the columns that most segments fill first, trailing nulls dropped), ORDER
    when the table read back would give the elements of a segment in another order. id_namespace: SEGMENT_ID left
    out where every one is the name-based UUID of its NAME in that namespace."""
    segs = [list(p) for p in segments]
    head = dict(header)
    if id_namespace:
        ns = uuid.UUID(id_namespace)
        names = [dict(p).get("NAME", "") for p in segs]
        if len(set(names)) == len(names) and all(dict(p).get("SEGMENT_ID") == str(uuid.uuid5(ns, n))
                                                 for p, n in zip(segs, names)):
            segs = [[pv for pv in p if pv[0] != "SEGMENT_ID"] for p in segs]
            head["ID_NAMESPACE"] = id_namespace
    shared = {}
    if len(segs) > 1:
        maps = [dict(p) for p in segs]
        for path, value in segs[0]:
            if path not in STRUCTURAL and path not in ("NAME", "XML") and all(m.get(path) == value for m in maps[1:]):
                shared[path] = value
    columns, count = [], {}
    for p in segs:
        for path, _v in p:
            if path in shared:
                continue
            if path not in count:
                columns.append(path)
                count[path] = 0
            count[path] += 1
    columns.sort(key=lambda k: -count[k])                    # stable: equal counts keep their order
    rows = []
    for p in segs:
        d = dict(p)
        row = [d.get(k) for k in columns]
        while row and row[-1] is None:
            row.pop()
        rows.append(row)
    obj = dict(head)
    if shared:
        obj["DEFAULTS"] = shared
    obj["COLUMNS"] = columns
    obj["ROWS"] = rows
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if keep_order:
        _h, back = table_model(text)
        if any([k for k, _v in b] != [k for k, _v in s] for b, s in zip(back, segments)):
            del obj["ROWS"]
            obj["ORDER"] = _merged_order(segments)
            obj["ROWS"] = rows
            text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return text


def _xml_cell_problem(text):
    """What makes an XML cell or the XML member break section 11.5, or None. It holds elements, written whole one
    after the other, that a reader puts into the XML list as they are: text outside them (white space apart) would
    become text of TT_SEGMENT or of TT_SEGMENT_LIST."""
    try:
        holder = ET.fromstring("<TT_XML_CELL>%s</TT_XML_CELL>" % text)
    except ET.ParseError as e:
        return "is not XML (%s)" % e
    if (holder.text or "").strip() or any((e.tail or "").strip() for e in holder):
        return "holds text outside its elements"
    return None


def table_model(text, problems=None):
    """The value of a TT_SEGMENT_TABLE comment -> (header, segments) as list_model gives them, the elements of each
    segment in the order of ORDER. `problems` (a list) receives what breaks a rule of section 11.5. ValueError when the
    value cannot be read as a table at all."""
    report = problems.append if problems is not None else (lambda _msg: None)
    try:
        obj = json.loads(text)
    except ValueError as e:
        raise ValueError("not JSON (%s)" % e)
    if not isinstance(obj, dict):
        raise ValueError("not a JSON object")
    columns, rows = obj.get("COLUMNS"), obj.get("ROWS")
    defaults, order = obj.get("DEFAULTS", {}), obj.get("ORDER", [])
    if not (isinstance(columns, list) and all(isinstance(c, str) for c in columns)):
        raise ValueError("COLUMNS is not an array of paths")
    if not (isinstance(rows, list) and all(isinstance(r, list) for r in rows)):
        raise ValueError("ROWS is not an array of rows")
    if not (isinstance(defaults, dict) and all(isinstance(v, str) for v in defaults.values())):
        raise ValueError("DEFAULTS is not an object of strings")
    if not (isinstance(order, list) and all(isinstance(p, str) for p in order)):
        raise ValueError("ORDER is not an array of paths")
    if len(set(columns)) != len(columns):
        report("a path appears twice in COLUMNS")
    for need in ("NAME", "START_SAMPLE", "LENGTH_SAMPLES"):
        if need not in columns:
            report("%s is not among COLUMNS" % need)
    for gone in ("NAME", "SEGMENT_ID", "START_SAMPLE", "LENGTH_SAMPLES"):
        if gone in defaults:
            report("DEFAULTS holds %s" % gone)
    ns = obj.get("ID_NAMESPACE")
    if ns is not None:
        try:
            ns = uuid.UUID(ns)
        except (ValueError, TypeError, AttributeError):
            report("ID_NAMESPACE is not a UUID")
            ns = None
    header = {}
    for k, v in obj.items():
        if k in ("DEFAULTS", "COLUMNS", "ORDER", "ROWS", "ID_NAMESPACE"):
            continue
        if isinstance(v, str):
            header[k] = v                                    # a member not known here: a header element of a later draft
        else:
            report("member %s is not a string" % k)
    if header.get("XML"):
        why = _xml_cell_problem(header["XML"])
        if why:
            report("member XML %s" % why)
    rank = {p: i for i, p in enumerate(order)}
    segments, derived = [], []
    for r, row in enumerate(rows, 1):
        if len(row) > len(columns):
            report("row %d has more cells than COLUMNS" % r)
        if not all(c is None or isinstance(c, str) for c in row):
            report("row %d has a cell that is neither a string nor null" % r)
        pairs = [(k, row[i]) for i, k in enumerate(columns) if i < len(row) and isinstance(row[i], str)]
        have = {k for k, _v in pairs}
        pairs += [(k, v) for k, v in defaults.items() if k not in have]
        have.update(defaults)
        if "SEGMENT_ID" not in have and ns is not None:
            name = dict(pairs).get("NAME", "")
            pairs.append(("SEGMENT_ID", str(uuid.uuid5(ns, name))))
            derived.append(name)
        if "CUE_ID" not in have:
            pairs.append(("CUE_ID", "0"))
        cell = dict(pairs).get("XML")
        if cell:
            why = _xml_cell_problem(cell)
            if why:
                report("row %d, XML cell %s" % (r, why))
        if rank:
            pairs.sort(key=lambda pv: rank.get(pv[0], len(rank)))   # stable: the paths ORDER lacks keep their order
        segments.append(pairs)
    if len(set(derived)) != len(derived):
        report("segments whose SEGMENT_ID derives from their NAME do not all have distinct names")
    return header, segments


def ogg_list_of(cm):
    """-> (comment name, values) of the segment list of an Ogg file: TT_SEGMENT_LIST, else TT_SEGMENT_TABLE."""
    if cm.get(LIST_KEY):
        return LIST_KEY, cm[LIST_KEY]
    if cm.get(TABLE_KEY):
        return TABLE_KEY, cm[TABLE_KEY]
    return None, []


def ogg_list_element(key, text):
    """The TT_SEGMENT_LIST element of a list comment (rebuilt from the table for TT_SEGMENT_TABLE). ValueError or
    ET.ParseError when it cannot be read."""
    if key == TABLE_KEY:
        header, segments = table_model(text)
        return ET.fromstring(list_xml(header, segments))
    return ET.fromstring(text)


def inflate_bounded(raw, limit=MAX_INFLATED):
    """A zlib stream (RFC 1950) -> its bytes. ValueError when it is not one, or holds more than `limit` bytes."""
    d = zlib.decompressobj()
    try:
        out = d.decompress(raw, limit + 1)
    except zlib.error as e:
        raise ValueError("not a zlib stream (%s)" % e)
    if len(out) > limit:
        raise ValueError("it inflates beyond %d bytes" % limit)
    if not d.eof:
        raise ValueError("the zlib stream is cut short")
    return out


def deflate_origin_chunks(listel, known=None):
    """Writer side of section 5.2: each DATA_BASE64 of ORIGIN/CHUNK_LIST that is longer than the same chunk deflated
    becomes DATA_DEFLATE_BASE64. `known`: {chunk body: deflated base64} to use instead of zlib. -> chunks deflated."""
    n = 0
    for c in listel.iter("CHUNK"):
        d = c.find("DATA_BASE64")
        if d is None:
            continue
        raw = base64.b64decode(d.text or "")
        z = (known or {}).get(raw) or base64.b64encode(zlib.compress(raw, 9)).decode("ascii")
        if len(z) < len(d.text or ""):
            d.tag, d.text = "DATA_DEFLATE_BASE64", z
            n += 1
    return n


def origin_chunks(seg):
    """The chunks of ORIGIN/CHUNK_LIST of a flattened segment (canon_list) -> (problems, chunks deflated, chunks with
    neither DATA_BASE64 nor DATA_DEFLATE_BASE64)."""
    groups = {}
    for key, value in seg.items():
        head, _sep, leaf = key.rpartition("/")
        if "/CHUNK_LIST#" in "/" + head and head.rsplit("/", 1)[-1].startswith("CHUNK#"):
            groups.setdefault(head, {})[leaf] = value
    problems, deflated, unknown = [], 0, 0
    for leaves in groups.values():
        cid = leaves.get("CHUNK_ID#0", "?")
        if "DATA_BASE64#0" in leaves:
            try:
                base64.b64decode(leaves["DATA_BASE64#0"], validate=True)
            except Exception:                          # noqa: BLE001 (report, do not stop)
                problems.append("ORIGIN chunk %s is not valid base64" % cid)
        elif "DATA_DEFLATE_BASE64#0" in leaves:
            deflated += 1
            try:
                inflate_bounded(base64.b64decode(leaves["DATA_DEFLATE_BASE64#0"], validate=True))
            except Exception as e:                     # noqa: BLE001 (report, do not stop)
                problems.append("ORIGIN chunk %s: DATA_DEFLATE_BASE64 is not a zlib stream in base64 (%s)" % (cid, e))
        else:
            unknown += 1
    return problems, deflated, unknown


def check_chunk_forms(version, deflated, unknown, warn, note):
    """Validator lines on the forms of the original chunks of a list (section 5.2)."""
    if deflated:
        note("%d original chunk(s) deflated before base64 (DATA_DEFLATE_BASE64, section 5.2)" % deflated)
        if version != TABLE_SPEC_VERSION:
            warn("deflated original chunks in a list of TT_VERSION %s: such a list has TT_VERSION %s (section 5.2)"
                 % (version or "?", TABLE_SPEC_VERSION))
    if unknown:
        warn("%d original chunk(s) with neither DATA_BASE64 nor DATA_DEFLATE_BASE64: a reader leaves them out "
             "(section 5.2)" % unknown)


def original_chunk_sizes(seg_el):
    """Body sizes of the original chunks of a TT_SEGMENT element (ORIGIN/CHUNK_LIST), the ones that can be read."""
    sizes = []
    for c in seg_el.iter("CHUNK"):
        try:
            if c.find("DATA_BASE64") is not None:
                sizes.append(len(base64.b64decode(c.findtext("DATA_BASE64") or "")))
            elif c.find("DATA_DEFLATE_BASE64") is not None:
                sizes.append(len(inflate_bounded(base64.b64decode(c.findtext("DATA_DEFLATE_BASE64") or ""))))
        except Exception:                              # noqa: BLE001 (the validator reports these chunks)
            continue
    return sizes


def opus_packet_frames(p):
    """Duration of an Opus packet in 48 kHz frames, from its TOC byte (RFC 6716, section 3.1)."""
    if not p:
        return 0
    config = p[0] >> 3
    frame = ([480, 960, 1920, 2880][config & 3] if config < 12
             else ([480, 960][config & 1] if config < 16 else [120, 240, 480, 960][config & 3]))
    c = p[0] & 3
    return frame * (1 if c == 0 else ((p[1] & 0x3F if len(p) > 1 else 0) if c == 3 else 2))


def vorbis_mode_blockflags(setup):
    """Block flag (0 short, 1 long) of each mode of a Vorbis setup header, read backwards from its end (as ffmpeg's
    Vorbis parser does). ValueError when they cannot be found."""
    rev, total, state = setup[::-1], len(setup) * 8, {"bit": 0}

    def get1():
        b = state["bit"]
        state["bit"] = b + 1
        return (rev[b >> 3] >> (7 - (b & 7))) & 1

    def get(k):
        v = 0
        for _ in range(k):
            v = (v << 1) | get1()
        return v

    framing = 0
    while total - state["bit"] > 97:
        if get1():
            framing = state["bit"]
            break
    if not framing:
        raise ValueError("Vorbis setup header: framing bit not found")
    count = last = 0
    while total - state["bit"] >= 97:
        if get(8) > 63 or get(16) or get(16):
            break
        get1()
        count += 1
        if count > 64:
            break
        save = state["bit"]
        if get(6) + 1 == count:
            last = count
        state["bit"] = save
    if not last:
        raise ValueError("Vorbis setup header: modes not found")
    state["bit"] = framing
    flags = [0] * last
    for i in range(last - 1, -1, -1):
        state["bit"] += 40
        flags[i] = get1()
    return flags


def packet_frames(info):
    """[(first frame, frames)] of every audio packet, counted like START_SAMPLE (Opus: at 48 kHz, the pre-skip removed;
    Vorbis: (previous block + current block) / 4), set on the granule position of the first page that ends one."""
    packets, nhead = info["packets"], info["nhead"]
    audio = packets[nhead:]
    durs = []
    if info["codec"] == "opus":
        durs = [opus_packet_frames(p) for p, _i in audio]
    else:
        head = packets[0][0]
        sizes = [1 << (head[28] & 15), 1 << (head[28] >> 4)]
        flags = vorbis_mode_blockflags(packets[2][0])
        bits = max(0, (len(flags) - 1).bit_length())
        prev = -1
        for p, _i in audio:
            mode = ((p[0] >> 1) & ((1 << bits) - 1)) if len(flags) > 1 and p else 0
            cur = sizes[flags[mode] if mode < len(flags) else 0]
            durs.append(0 if prev < 0 else (prev + cur) // 4)
            prev = cur
    ends, acc = {}, 0
    for k, (_p, pi) in enumerate(audio):
        acc += durs[k]
        ends[pi] = acc
    origin = 0
    for pi in sorted(ends):
        if info["pages"][pi]["granule"] >= 0:
            origin = info["pages"][pi]["granule"] - ends[pi]
            break
    out, pos = [], origin - info["preskip"]
    for d in durs:
        out.append((pos, d))
        pos += d
    return out


def empty_shell(info):
    """Bytes of the same stream with no comment and no audio: identification header, comment header with the vendor
    string only, setup header (Vorbis), on the fewest pages. What every separate file pays once (section 12.1)."""
    packets = info["packets"]
    heads = [build_ogg_comments(info["magic"], info["vendor"], [])] + ([packets[2][0]] if info["codec"] == "vorbis" else [])
    size = 27 + len(ogg_lacing(len(packets[0][0]))) + len(packets[0][0])
    for _ht, _g, lacing, body in paginate_headers(heads):
        size += 27 + len(lacing) + len(body)
    return size


def reference_tags(pairs):
    """Bytes of the values of a segment as the comments of a separate Ogg file (section 12.1): 4 + name + 1 + value for
    each value but the four structural ones, empty values left out; the XML cell counts as one value named XML."""
    total = 0
    for path, value in pairs:
        if path in STRUCTURAL or value == "":
            continue
        total += 4 + len(path.rpartition("/")[2].encode("utf-8")) + 1 + len(value.encode("utf-8"))
    return total


def _covered_frames(ranges):
    total, end = 0, -1
    for a, n in sorted(ranges):
        b = a + n
        if b > end:
            total += b - max(a, end)
            end = b
    return total


def ogg_weight(info, listel):
    """Reference weight of an Ogg TT file (section 12.1) -> (bytes, bytes of audio that belong to no segment)."""
    audio = info["packets"][info["nhead"]:]
    frames = packet_frames(info)
    shell = empty_shell(info)
    audio_pages = len(info["pages"]) - info["packets"][info["nhead"] - 1][1] - 1
    per_page = max(1.0, len(audio) / max(1, audio_pages))
    starts = [f[0] for f in frames]
    covered, ref = [0.0] * len(audio), 0.0
    for s in listel.findall("TT_SEGMENT"):
        try:
            a = int(s.findtext("START_SAMPLE"))
            b = a + int(s.findtext("LENGTH_SAMPLES"))
        except (TypeError, ValueError):
            continue
        k = max(0, bisect.bisect_right(starts, a) - 1)
        nbytes = count = 0.0
        while k < len(audio) and frames[k][0] < b:
            pa, pd = frames[k]
            if pd > 0:
                share = max(0, min(b, pa + pd) - max(a, pa)) / pd
                nbytes += (len(audio[k][0]) + len(audio[k][0]) // 255 + 1) * share
                count += share
                covered[k] = min(1.0, covered[k] + share)
            k += 1
        ref += shell + reference_tags(segment_pairs(s)) + nbytes + 27 * max(1, math.ceil(count / per_page - 1e-9))
    outside = sum((len(p) + len(p) // 255 + 1) * (1.0 - cv) for (p, _i), cv, (_s, d) in zip(audio, covered, frames) if d > 0)
    return ref, outside


def wav_weight(by, listel, ixml_version):
    """Reference weight of a WAV TT file (section 12.1) -> (bytes, bytes of audio that belong to no segment)."""
    fmt = by["fmt "]["body"]
    align = max(1, struct.unpack("<H", fmt[12:14])[0])
    fmt_chunk_bytes = 8 + len(fmt) + (len(fmt) & 1)
    bext_bytes = (8 + len(by["bext"]["body"]) + (len(by["bext"]["body"]) & 1)) if "bext" in by else 0
    frame = len(('<?xml version="1.0" encoding="UTF-8"?><BWFXML><IXML_VERSION>%s</IXML_VERSION></BWFXML>'
                 % ixml_version).encode("utf-8"))
    ref, ranges = 0, []
    for s in listel.findall("TT_SEGMENT"):
        try:
            start, length = int(s.findtext("START_SAMPLE")), int(s.findtext("LENGTH_SAMPLES"))
        except (TypeError, ValueError):
            continue
        ranges.append((start, length))
        originals = original_chunk_sizes(s)
        if originals:
            meta = sum(8 + n + (n & 1) for n in originals)
        else:
            body = frame + sum(len(_xml_text(e).encode("utf-8")) for e in s if e.tag in ("USER", "ASWG", "FIELD_LIST"))
            meta = bext_bytes + 8 + body + (body & 1)
        data = length * align
        ref += 12 + fmt_chunk_bytes + meta + 8 + data + (data & 1)
    return ref, len(by["data"]["body"]) - _covered_frames(ranges) * align


def weight_line(size, ref, outside):
    """The weight report of a validator (section 12.2)."""
    diff = size - ref
    return ("weight (section 12): file %d bytes, reference weight %.0f bytes (each segment as a separate file): %s by "
            "%.0f bytes (%+.2f %%); audio that belongs to no segment: %.0f bytes"
            % (size, ref, "heavier" if diff > 0 else "lighter", abs(diff), 100.0 * diff / ref if ref else 0.0, outside))


def edge_list():
    """A list with what the columns of a table cannot express (self-check of section 11.5): elements of a program at
    list level, characters to escape, an empty value, a "/" in a field name, a deflated original chunk, a repeated
    element, a repeated field name, two USER blocks, a FIELD with a third child, an element with an attribute, a block
    of a program. The non-ASCII name is written with chr(): the source of the kit stays ASCII."""
    name = "Porte " + chr(0xAB) + " grin" + chr(0xE7) + "ante " + chr(0xBB) + " 01 " + chr(0x95E8)
    seg = ("<TT_SEGMENT><SEGMENT_ID>0b6f6a52-3f0e-4c8e-9d1a-1a2b3c4d5e0%d</SEGMENT_ID><CUE_ID>%d</CUE_ID>"
           "<START_SAMPLE>%d</START_SAMPLE><LENGTH_SAMPLES>100</LENGTH_SAMPLES><NAME>%s</NAME>%s</TT_SEGMENT>")
    return ("<TT_SEGMENT_LIST><TT_VERSION>0.3</TT_VERSION><SAMPLE_RATE>48000</SAMPLE_RATE><TOTAL_FRAMES>400</TOTAL_FRAMES>"
            "<SEGMENT_COUNT>4</SEGMENT_COUNT><ACME_SESSION><TAKE>4</TAKE><MIC>MKH416</MIC></ACME_SESSION>"
            "<ACME_NOTE>kept</ACME_NOTE>"
            + seg % (1, 1, 0, xml_escape(name),
                     "<USER><CATID>DOORWood</CATID><FXNAME>Say \"hi\" \\ &amp; &lt;go&gt; 'x'</FXNAME><KEYWORDS></KEYWORDS>"
                     "<LIBRARY>Lib</LIBRARY></USER><FIELD_LIST><FIELD><NAME>a/b</NAME><VALUE>line 1\nline 2\ttab  </VALUE>"
                     "</FIELD></FIELD_LIST><ORIGIN><FILENAME>door.wav</FILENAME><CHUNK_LIST><CHUNK><CHUNK_ID>bext</CHUNK_ID>"
                     "<DATA_DEFLATE_BASE64>" + SRC_BEXT_DEFLATED + "</DATA_DEFLATE_BASE64></CHUNK></CHUNK_LIST></ORIGIN>")
            + seg % (2, 2, 100, "B", "<ACME_TAG>one</ACME_TAG><ACME_TAG>two</ACME_TAG><USER><CATID>DOORWood</CATID>"
                     "<LIBRARY>Lib</LIBRARY></USER><FIELD_LIST><FIELD><NAME>dup</NAME><VALUE>1</VALUE></FIELD><FIELD>"
                     "<NAME>dup</NAME><VALUE>2</VALUE></FIELD></FIELD_LIST>")
            + seg % (3, 0, 200, "C", "<USER><CATID>DOORWood</CATID></USER><USER><FXNAME>second USER block</FXNAME></USER>"
                     "<FIELD_LIST><FIELD><NAME>x</NAME><VALUE>y</VALUE><LANG>fr</LANG></FIELD></FIELD_LIST>")
            + seg % (4, 3, 300, "D", "<ACME_LANE kind=\"voice\">2</ACME_LANE><ACME_BLOCK><P>1</P><Q>2</Q></ACME_BLOCK>"
                     "<USER><CATID>DOORWood</CATID><LIBRARY>Lib</LIBRARY></USER><STATUS>proposed</STATUS>"
                     "<CONFIDENCE>0.8</CONFIDENCE>")
            + "</TT_SEGMENT_LIST>")


def describe_ogg(data):
    info = read_ogg(data)
    cm = comment_map(info["comments"])
    key, values = ogg_list_of(cm)
    text = values[0]
    return dict(kind="ogg", codec=info["codec"], rate=info["rate"], channels=info["channels"],
                preskip=info["preskip"], frames=info["total"], audio_sha256=info["audio_sha256"],
                headers_sha256=info["headers_sha256"], comment_keys=sorted(cm),
                summary={k: cm[k][0] for k in OGG_SUMMARY_KEYS if k in cm}, chapters=ogg_chapters(cm), list_key=key,
                list_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), list=canon_list(ogg_list_element(key, text)))


def check_ogg_bytes(data, entry, title):
    rep = Report(title, OGG_CARRIERS)
    try:
        info = read_ogg(data)
    except ValueError as e:
        rep.set("stream", "LOST", str(e))
        return rep
    problems = []
    if len(info["serials"]) != 1:
        problems.append("%d logical streams" % len(info["serials"]))
    if info["crc_errors"]:
        problems.append("%d page(s) with a wrong CRC" % info["crc_errors"])
    rep.set("stream", "CHANGED" if problems else "OK", "; ".join(problems))
    same_audio = info["audio_sha256"] == entry["audio_sha256"]
    rep.set("audio", "OK" if same_audio else "CHANGED", "" if same_audio else "audio packets differ (re-encoded?)")
    rep.set("headers", "OK" if info["headers_sha256"] == entry["headers_sha256"] else "CHANGED")
    cm = comment_map(info["comments"])
    rep.extra = sorted(k for k in cm if k not in entry["comment_keys"] and not is_chapter_key(k))   # chapters: below

    found = {k: cm[k][0] for k in OGG_SUMMARY_KEYS if k in cm}
    if not found:
        rep.set("summary", "LOST")
    else:
        rep.set("summary", "OK" if compare_dict(entry["summary"], found, "comment", rep) else "CHANGED")

    chapters = ogg_chapters(cm)
    if not chapters:
        rep.set("chapters", "LOST")
    elif chapters == entry["chapters"]:
        rep.set("chapters", "OK")
    elif sorted(map(tuple, chapters.values())) == sorted(map(tuple, entry["chapters"].values())):
        rep.set("chapters", "SAME", "same times and names, other numbers")
    else:
        compare_dict({k: tuple(v) for k, v in entry["chapters"].items()}, {k: tuple(v) for k, v in chapters.items()},
                     "chapter", rep)
        rep.set("chapters", "CHANGED")

    key = entry.get("list_key", LIST_KEY)                # TT_SEGMENT_LIST, or TT_SEGMENT_TABLE (draft 0.3)
    other = TABLE_KEY if key == LIST_KEY else LIST_KEY
    found_list, values = None, cm.get(key, [])
    if not values:
        if cm.get(other):
            rep.set("list", "CHANGED", "the list is now a %s comment" % other)
        else:
            rep.set("list", "LOST")
    elif len(values) > 1:
        rep.set("list", "CHANGED", "%d %s comments" % (len(values), key))
    else:
        try:
            found_list = canon_list(ogg_list_element(key, values[0]))
        except (ET.ParseError, ValueError) as e:
            rep.set("list", "CHANGED", "the list no longer reads: %s" % e)
        else:
            if hashlib.sha256(values[0].encode("utf-8")).hexdigest() == entry["list_sha256"]:
                rep.set("list", "OK")
            else:
                rep.set("list", "SAME" if compare_list(entry["list"], found_list, rep, "list") else "CHANGED")

    # integrity rules of the spec (section 11.3), on the list as found
    if found_list is not None:
        h = found_list["header"]
        if h.get("TOTAL_FRAMES") != str(info["total"]):
            rep.info("spec check: TOTAL_FRAMES %s but the stream decodes to %d frames" % (h.get("TOTAL_FRAMES"), info["total"]))
        if h.get("AUDIO_SHA256") and h["AUDIO_SHA256"] != info["audio_sha256"]:
            rep.info("spec check: AUDIO_SHA256 no longer matches the audio packets: segments may be wrong")
        moved = 0
        for s in found_list["segments"]:
            cid, start = s.get("CUE_ID#0", ""), s.get("START_SAMPLE#0", "")
            ch = chapters.get("%03d" % int(cid)) if cid.isdigit() and cid != "0" else None
            if ch and start.isdigit() and not chapter_at(ch[0], int(start), info["rate"], 1):   # reader rule: 1 ms
                moved += 1
        if moved:
            rep.info("spec check: %d segment(s) whose chapter is not at START_SAMPLE (moved by a program)" % moved)
    return rep


def check_time_reference(h, ok, bad, warn, bext_tref=None):
    """The optional file time reference of the list header (section 5, draft 0.2 amended 2026-11-10): TIME_REFERENCE
    a whole number of frames, TIMECODE_RATE "N/D", TIMECODE_FLAG "NDF" or "DF"; in a WAV file with a bext, the same
    value as its TimeReference."""
    tref, trate, tflag = h.get("TIME_REFERENCE"), h.get("TIMECODE_RATE"), h.get("TIMECODE_FLAG")
    if tref is None and trate is None and tflag is None:
        return
    if tref is None:
        warn("TIMECODE_RATE / TIMECODE_FLAG without TIME_REFERENCE (section 5)")
    elif not tref.isdigit():
        bad("TIME_REFERENCE is not a whole number of frames: %s" % tref[:40])
    elif bext_tref is not None and int(tref) != bext_tref:
        bad("TIME_REFERENCE %s, but the bext TimeReference is %d (they MUST be equal, section 5)" % (tref, bext_tref))
    else:
        ok("TIME_REFERENCE %s" % tref + (" (same as the bext TimeReference)" if bext_tref is not None else ""))
    if trate is not None:
        num, sep, den = trate.partition("/")
        if not (sep and num.isdigit() and den.isdigit() and int(num) > 0 and int(den) > 0):
            bad("TIMECODE_RATE is not \"N/D\" (as iXML SPEED writes it): %s" % trate[:40])
        elif tflag == "DF" and den != "1001":
            warn("TIMECODE_FLAG DF with TIMECODE_RATE %s (drop frame is for 30000/1001 and 60000/1001)" % trate)
    if tflag is not None and tflag not in ("NDF", "DF"):
        bad("TIMECODE_FLAG is neither NDF nor DF: %s" % tflag[:40])


def validate_ogg(path, data):
    """Spec checks for an Ogg TT file (section 11). 0 = no FAIL."""
    lines, counts = [], {"fail": 0, "warn": 0}

    def note(msg):                                       # information only: neither a failure nor a warning
        lines.append("[INFO] " + msg)

    def ok(msg):
        lines.append("[OK]   " + msg)

    def bad(msg):
        counts["fail"] += 1
        lines.append("[FAIL] " + msg)

    def warn(msg):
        counts["warn"] += 1
        lines.append("[WARN] " + msg)

    def finish():
        print("== validate %s" % path)
        print("\n".join(lines))
        print("RESULT %s (%d fail, %d warning)" % ("PASS" if counts["fail"] == 0 else "FAIL", counts["fail"], counts["warn"]))
        return 1 if counts["fail"] else 0

    try:
        info = read_ogg(data)
    except ValueError as e:
        bad(str(e))
        return finish()
    rate, total = info["rate"], info["total"]
    ok("Ogg %s, %d Hz decoded, %d channel(s), %d frames%s" % (info["codec"], rate, info["channels"], total,
       (", pre-skip %d" % info["preskip"]) if info["codec"] == "opus" else ""))
    if len(info["serials"]) != 1:
        bad("%d logical streams (one only: no chaining, no multiplexing, section 11.1)" % len(info["serials"]))
    if info["crc_errors"]:
        bad("%d page(s) with a wrong CRC" % info["crc_errors"])
    if info["unfinished"]:
        warn("the stream ends in the middle of a packet")
    cm = comment_map(info["comments"])
    lists, tables = cm.get(LIST_KEY, []), cm.get(TABLE_KEY, [])
    if not lists and not tables:
        bad("no TT_SEGMENT_LIST or TT_SEGMENT_TABLE comment")
        return finish()
    if lists and tables:
        bad("both TT_SEGMENT_LIST and TT_SEGMENT_TABLE: a file holds one form; the checks below read TT_SEGMENT_LIST, "
            "as a reader does (section 11.5)")
    form = LIST_KEY if lists else TABLE_KEY
    values = lists or tables
    if len(values) > 1:
        bad("%d %s comments (at most one, sections 11.2 and 11.5)" % (len(values), form))
    if "\n" in values[0] or "\r" in values[0]:
        warn("the %s value has line breaks (it SHOULD be one line, sections 11.2 and 11.5)" % form)
    if form == TABLE_KEY:
        problems = []
        try:
            theader, tsegs = table_model(values[0], problems)
            listel = ET.fromstring(list_xml(theader, tsegs))
        except (ValueError, ET.ParseError) as e:
            bad("the TT_SEGMENT_TABLE value cannot be read as a segment table: %s (section 11.5)" % e)
            return finish()
        for p in problems:
            bad("segment table: %s (section 11.5)" % p)
        if not problems:
            tobj = json.loads(values[0])
            ok("segment table: %d columns, %d value(s) shared by every segment, %s" % (
                len(tobj["COLUMNS"]), len(tobj.get("DEFAULTS", {})), "ORDER given" if "ORDER" in tobj else "no ORDER"))
    else:
        try:
            listel = ET.fromstring(values[0])
        except ET.ParseError as e:
            bad("the TT_SEGMENT_LIST value does not parse: %s" % e)
            return finish()
        if listel.tag != "TT_SEGMENT_LIST":
            bad("the TT_SEGMENT_LIST value is a <%s> element" % listel.tag)
            return finish()
    canon = canon_list(listel)
    h, segs = canon["header"], canon["segments"]
    version = h.get("TT_VERSION", "")
    if not version:
        bad("TT_VERSION missing")
    elif form == TABLE_KEY and version != TABLE_SPEC_VERSION:
        warn("TT_VERSION %s: a file with a segment table has TT_VERSION %s (section 11.5)" % (version, TABLE_SPEC_VERSION))
    elif version not in (OGG_SPEC_VERSION, TABLE_SPEC_VERSION):
        warn("TT_VERSION %s (Ogg files are defined from draft %s)" % (version, OGG_SPEC_VERSION))
    else:
        ok("TT_VERSION " + version)
    (ok if h.get("SAMPLE_RATE") == str(rate) else bad)("SAMPLE_RATE %s (decoded %d Hz)" % (h.get("SAMPLE_RATE"), rate))
    (ok if h.get("TOTAL_FRAMES") == str(total) else bad)("TOTAL_FRAMES %s (stream %d frames)" % (h.get("TOTAL_FRAMES"), total))
    (ok if h.get("SEGMENT_COUNT") == str(len(segs)) else bad)("SEGMENT_COUNT %s (%d TT_SEGMENT)" % (h.get("SEGMENT_COUNT"), len(segs)))
    sha = h.get("AUDIO_SHA256", "")
    if not sha:
        warn("no AUDIO_SHA256 (recommended, section 11.3)")
    elif len(sha) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        bad("AUDIO_SHA256 is not a SHA-256: %s" % sha[:70])
    elif sha.lower() != info["audio_sha256"]:
        bad("AUDIO_SHA256 does not match the audio packets (re-encoded after the list was written?)")
    else:
        ok("AUDIO_SHA256 matches the audio packets")
    check_time_reference(h, ok, bad, warn)

    chapters = ogg_chapters(cm)
    seen, prev, broken = set(), -1, 0
    deflated = unknown_chunks = 0
    for i, s in enumerate(segs, 1):
        sid, problems = s.get("SEGMENT_ID#0", ""), []
        if not sid:
            problems.append("no SEGMENT_ID")
        elif sid in seen:
            problems.append("SEGMENT_ID used twice")
        seen.add(sid)
        try:
            start, length = int(s.get("START_SAMPLE#0", "")), int(s.get("LENGTH_SAMPLES#0", ""))
        except ValueError:
            start = length = None
            problems.append("START_SAMPLE / LENGTH_SAMPLES are not whole numbers")
        if start is not None:
            if length < 1:
                problems.append("LENGTH_SAMPLES below 1")
            if start < 0 or start + length > total:
                problems.append("outside the audio")
            if start < prev:
                problems.append("not in ascending START_SAMPLE order")
            prev = start
        if not s.get("NAME#0"):
            problems.append("no NAME")
        cid = s.get("CUE_ID#0", "")
        if not cid.isdigit():
            problems.append("CUE_ID missing")
        elif int(cid) > 0 and start is not None:
            ch = chapters.get("%03d" % int(cid))
            if ch is None:
                problems.append("chapter %03d missing" % int(cid))
            else:
                at = chapter_at(ch[0], start, rate)
                if at is None:
                    problems.append("chapter %03d time %s is not HH:MM:SS.mmm" % (int(cid), ch[0][:24]))
                elif not at:
                    problems.append("chapter %03d at %s, START_SAMPLE is %s" % (int(cid), ch[0], chapter_time(start, rate)))
                if not ch[1]:
                    problems.append("chapter %03d has no NAME" % int(cid))
        chunk_problems, nd, nu = origin_chunks(s)
        problems += chunk_problems
        deflated += nd
        unknown_chunks += nu
        if problems:
            broken += 1
            bad("segment %d (%s): %s" % (i, sid[:13], "; ".join(problems)))
    if broken == 0:
        ok("%d segment(s): ids, ranges, names and chapters" % len(segs))
    check_chunk_forms(version, deflated, unknown_chunks, warn, note)
    unchaptered = sum(1 for s in segs if s.get("CUE_ID#0") == "0")
    if unchaptered:
        note("%d segment(s) without a chapter (CUE_ID 0): only programs that read the list see them (section 11.2)"
             % unchaptered)
    longer = sorted((k for k in chapters if len(k) > 3), key=int)
    if longer:
        bad("chapter numbers of more than three digits, from CHAPTER%s: ffmpeg reads three digits only, so "
            "CHAPTER%sNAME renames chapter %s (section 11.2)" % (longer[0], longer[0], longer[0][:3]))
    if any(len(k) < 3 for k in chapters):
        warn("chapter numbers SHOULD have three digits, 001 to 999 (section 11.2)")
    if info["codec"] == "opus":                          # RFC 7845, section 5.2: comments past 61,440 octets
        parts, nchap, end = [], 0, len(info["magic"]) + 4 + len(info["vendor"]) + 4
        for c in info["comments"]:
            end += 4 + len(c.encode("utf-8"))
            key = c.partition("=")[0].upper()
            if end <= 61440:
                continue
            if is_chapter_key(key):
                nchap += 1
                if nchap == 1:
                    parts.append(None)                   # where the chapters start
            else:
                parts.append(key)
        if parts:
            note("beyond the first 61,440 octets of the comment header, which RFC 7845 (section 5.2) lets Opus programs "
                 "ignore: %s (section 11.4)" % ", ".join(("%d chapter comment(s)" % nchap) if p is None else p for p in parts))
    desc = (cm.get("DESCRIPTION") or cm.get("COMMENT") or [""])[0]
    missing = [s.get("USER#0/FXNAME#0") for s in segs if s.get("USER#0/FXNAME#0") and s.get("USER#0/FXNAME#0") not in desc]
    if missing:
        warn("the DESCRIPTION comment does not name %d segment(s) (sections 7 and 11.2), first: %s" % (len(missing), missing[0]))
    elif segs:
        ok("the DESCRIPTION comment names every segment")
    try:
        ref, outside = ogg_weight(info, listel)
        note(weight_line(len(data), ref, outside))
    except (ValueError, IndexError, ZeroDivisionError) as e:
        note("weight (section 12): not computed (%s)" % e)
    return finish()


def make_ogg_audio():
    """Kit maintainers only: encodes the audio of the WAV samples into ogg_audio/ (ffmpeg with libvorbis and
    libopus). The Ogg samples are then made from these files by the kit itself."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("--make-ogg-audio needs ffmpeg on the PATH (kit maintainers only)")
        return 2
    os.makedirs(OGG_AUDIO_DIR, exist_ok=True)
    jobs = [(FULL, "full_vorbis.ogg", ["-c:a", "libvorbis", "-q:a", "4"]),
            (FULL, "full_opus.opus", ["-c:a", "libopus", "-b:a", "96k"]),
            (MANY, "many_vorbis.ogg", ["-c:a", "libvorbis", "-q:a", "1"])]
    code = 0
    for src, dst, codec in jobs:
        cmd = ([ffmpeg, "-v", "error", "-y", "-i", os.path.join(OUT_DIR, src), "-map_metadata", "-1",
                "-map_chapters", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact"] + codec
               + [os.path.join(OGG_AUDIO_DIR, dst)])
        r = subprocess.run(cmd, capture_output=True, text=True)
        print("%s -> ogg_audio/%s: exit %d %s" % (src, dst, r.returncode, r.stderr.strip()[:200]))
        code = code or r.returncode
    return code


def check_file(path, as_name=None):
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        man = json.load(f)
    name = as_name or os.path.basename(path)
    entry = man["files"].get(name)
    if entry is None:
        print("Unknown file name %r: add --as with one of %s" % (name, ", ".join(sorted(man["files"]))))
        return 2
    with open(path, "rb") as f:
        data = f.read()
    if entry.get("kind") == "ogg":
        rep = check_ogg_bytes(data, entry, "%s (as %s)" % (path, name))
        print(rep.text())
        bad = [c for c, s in rep.status.items() if s in ("CHANGED", "LOST")]
        return 1 if bad or rep.extra else 0
    rep = check_bytes(data, entry, "%s (as %s)" % (path, name))
    print(rep.text())
    bad = [c for c, s in rep.status.items() if s in ("CHANGED", "LOST")]
    return 1 if bad or rep.extra else 0


# ---------------------------------------------------------------------------------------------
# Validator: the rules of the specification on ANY TT file (not only the samples)
# ---------------------------------------------------------------------------------------------

def validate_file(path, data=None):
    """Spec checks: structure, list header, segments, mirrored markers, audio hash, summary, weight. 0 = no FAIL.
    `data`: the bytes of the file when they are already in memory (self-check)."""
    if data is None:
        with open(path, "rb") as f:
            data = f.read()
    if data[:4] == b"OggS":
        return validate_ogg(path, data)
    lines, counts = [], {"fail": 0, "warn": 0}

    def note(msg):                                       # information only: neither a failure nor a warning
        lines.append("[INFO] " + msg)

    def ok(msg):
        lines.append("[OK]   " + msg)

    def bad(msg):
        counts["fail"] += 1
        lines.append("[FAIL] " + msg)

    def warn(msg):
        counts["warn"] += 1
        lines.append("[WARN] " + msg)

    def finish():
        print("== validate %s" % path)
        print("\n".join(lines))
        print("RESULT %s (%d fail, %d warning)" % ("PASS" if counts["fail"] == 0 else "FAIL", counts["fail"], counts["warn"]))
        return 1 if counts["fail"] else 0

    try:
        form, chunks = parse_riff(data)
    except ValueError as e:
        bad(str(e))
        return finish()
    by = {}
    for c in chunks:
        by.setdefault(c["key"], c)
    if "fmt " not in by or "data" not in by:
        bad("no fmt or no data chunk")
        return finish()
    fmt = by["fmt "]["body"]
    channels, rate, align = struct.unpack("<H", fmt[2:4])[0], struct.unpack("<I", fmt[4:8])[0], struct.unpack("<H", fmt[12:14])[0]
    pcm = by["data"]["body"]
    frames = len(pcm) // max(1, align)
    ok("%s, %d Hz, %d channel(s), %d frames" % (form, rate, channels, frames))
    if "iXML" not in by:
        bad("no iXML chunk")
        return finish()
    root, err, parts, _lst = ixml_parts(by["iXML"]["body"])
    if root is None:
        bad("the iXML does not parse: " + err)
        return finish()
    listel = find_list(root)
    if listel is None:
        bad("no TT_SEGMENT_LIST in the iXML")
        return finish()
    canon = canon_list(listel)
    h, segs = canon["header"], canon["segments"]

    version = h.get("TT_VERSION", "")
    (ok if version else bad)("TT_VERSION " + (version or "missing"))
    (ok if h.get("SAMPLE_RATE") == str(rate) else bad)("SAMPLE_RATE %s (file %d Hz)" % (h.get("SAMPLE_RATE"), rate))
    (ok if h.get("TOTAL_FRAMES") == str(frames) else bad)("TOTAL_FRAMES %s (file %d frames)" % (h.get("TOTAL_FRAMES"), frames))
    (ok if h.get("SEGMENT_COUNT") == str(len(segs)) else bad)("SEGMENT_COUNT %s (%d TT_SEGMENT)" % (h.get("SEGMENT_COUNT"), len(segs)))
    sha = h.get("AUDIO_SHA256", "")
    if not sha:
        warn("no AUDIO_SHA256 (recommended, section 5)")
    elif len(sha) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in sha):
        bad("AUDIO_SHA256 is not a SHA-256: %s" % sha[:70])
    elif sha.lower() != hashlib.sha256(pcm).hexdigest():
        bad("AUDIO_SHA256 does not match the audio (the audio changed after the list was written?)")
    else:
        ok("AUDIO_SHA256 matches the audio")
    bext_body_ = by["bext"]["body"] if "bext" in by else b""
    check_time_reference(h, ok, bad, warn,
                         struct.unpack("<Q", bext_body_[338:346])[0] if len(bext_body_) >= 346 else None)

    cue = read_cue(by["cue "]["body"]) if "cue " in by else {}
    labels, notes, ltxts, order = read_adtl(by["LIST/adtl"]["body"]) if "LIST/adtl" in by else ({}, {}, {}, [])
    seen, prev, broken, no_ltxt, non_ascii = set(), -1, 0, 0, 0
    deflated = unknown_chunks = 0
    for i, s in enumerate(segs, 1):
        sid = s.get("SEGMENT_ID#0", "")
        problems = []
        if not sid:
            problems.append("no SEGMENT_ID")
        elif sid in seen:
            problems.append("SEGMENT_ID used twice")
        seen.add(sid)
        try:
            start, length = int(s.get("START_SAMPLE#0", "")), int(s.get("LENGTH_SAMPLES#0", ""))
        except ValueError:
            start = length = None
            problems.append("START_SAMPLE / LENGTH_SAMPLES are not whole numbers")
        if start is not None:
            if length < 1:
                problems.append("LENGTH_SAMPLES below 1")
            if start < 0 or start + length > frames:
                problems.append("outside the audio")
            if start < prev:
                problems.append("not in ascending START_SAMPLE order")
            prev = start
        if not s.get("NAME#0"):
            problems.append("no NAME")
        cue_id = s.get("CUE_ID#0", "")
        if not cue_id.isdigit():
            problems.append("CUE_ID missing")
        elif int(cue_id) > 0 and start is not None:
            cid = int(cue_id)
            if cid not in cue:
                problems.append("cue point %d missing" % cid)
            elif cue[cid] != start:
                problems.append("cue point %d at %d, START_SAMPLE %d" % (cid, cue[cid], start))
            if cid not in labels:
                problems.append("no labl for cue %d" % cid)
            elif any(ord(ch) > 127 for ch in labels[cid]):
                non_ascii += 1
            if cid not in ltxts:
                no_ltxt += 1
            elif ltxts[cid] != length:
                problems.append("ltxt length %d, LENGTH_SAMPLES %d" % (ltxts[cid], length))
        chunk_problems, nd, nu = origin_chunks(s)
        problems += chunk_problems
        deflated += nd
        unknown_chunks += nu
        if problems:
            broken += 1
            bad("segment %d (%s): %s" % (i, sid[:13], "; ".join(problems)))
    if broken == 0:
        ok("%d segment(s): ids, ranges, names and mirrored markers" % len(segs))
    check_chunk_forms(version, deflated, unknown_chunks, warn, note)
    if no_ltxt:
        warn("%d segment(s) with a cue point but no ltxt length (section 6)" % no_ltxt)
    if non_ascii:
        warn("%d labl text(s) not ASCII (section 6)" % non_ascii)
    first_other = next((k for k, x in enumerate(order) if x != "labl"), len(order))
    if "labl" in order[first_other:]:
        warn("a labl comes after a note or ltxt (some readers stop at the first non-labl)")
    keys = [c["key"] for c in chunks]
    di = keys.index("data")
    for k in ("cue ", "LIST/adtl"):
        if k in keys and keys.index(k) > di:
            warn("%s placed after data (allowed; SHOULD be before, section 6)" % k)

    user = parts.get("USER", {})
    desc = user.get("DESCRIPTION#0", "")
    missing = [s.get("USER#0/FXNAME#0") for s in segs
               if s.get("USER#0/FXNAME#0") and s.get("USER#0/FXNAME#0") not in desc]
    if missing:
        warn("the file-level USER DESCRIPTION does not name %d segment(s) (section 7), first: %s" % (len(missing), missing[0]))
    elif segs:
        ok("the file-level USER DESCRIPTION names every segment")
    if "bext" in by:
        d = by["bext"]["body"][:256].split(b"\x00")[0]
        if any(b > 127 for b in d):
            warn("the bext Description is not ASCII (EBU Tech 3285, section 7)")
    try:
        ref, outside = wav_weight(by, listel, root.findtext("IXML_VERSION") or "2.10")
        note(weight_line(len(data), ref, outside))
    except (ValueError, IndexError, struct.error, ZeroDivisionError) as e:
        note("weight (section 12): not computed (%s)" % e)
    return finish()


# ---------------------------------------------------------------------------------------------
# Generation and self-check
# ---------------------------------------------------------------------------------------------

def generate(use_ffprobe=True):
    os.makedirs(OUT_DIR, exist_ok=True)
    log = []
    fsegs, ftotal = full_segments()
    fpcm = synth(ftotal, 2, 24, [(s["start"], s["length"], s["freq"]) for s in fsegs], seed=22)
    msegs, mtotal = many_segments()
    mpcm = synth(mtotal, 1, 16, [(s["start"], s["length"], s["freq"]) for s in msegs], seed=400)
    files = {FULL: (build_full(fpcm, fsegs, ftotal), fsegs, FOREIGN, xmp_markers_expected(fsegs)),
             MINIMAL: (build_minimal(fpcm, fsegs, ftotal), fsegs, None, None),
             MANY: (build_many(mpcm, msegs, mtotal), msegs, None, None)}
    man = dict(spec=OGG_SPEC_VERSION, writer=WRITER, tokens=TOKENS, files={})
    for name, (data, segs, foreign, xmp_exp) in files.items():
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(data)
        man["files"][name] = describe(data, segs, foreign, xmp_exp)
        log.append("written %s: %d bytes, %d segments" % (name, len(data), len(segs)))
    # Ogg samples: the encoded audio of ogg_audio/ with the comments of section 11
    ogg_files, failures = {}, 0
    for name, key, base, title, conversion in OGG_SAMPLES:
        base_path = os.path.join(OGG_AUDIO_DIR, base)
        if not os.path.exists(base_path):
            failures += 1
            log.append("ogg_audio/%s missing (kit maintainers: --make-ogg-audio)   <-- FAILED" % base)
            continue
        with open(base_path, "rb") as f:
            base_data = f.read()
        info = read_ogg(base_data)
        segs, rich, foreign = ogg_segments(key, fsegs, msegs)
        # the full samples carry a file time reference: 10:00:00:00 at 25 fps (draft 0.2 amended, 2026-11-10)
        time_ref = (10 * 3600 * info["rate"], "25/1", "NDF") if key == "full" else None
        data = ogg_with_comments(base_data, ogg_tt_comments(segs, info["total"], info["rate"], info["audio_sha256"],
                                                             rich, title, foreign, conversion, time_ref))
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(data)
        man["files"][name] = describe_ogg(data)
        ogg_files[name] = (data, ftotal if key == "full" else mtotal)
        log.append("written %s: %d bytes, %d segments" % (name, len(data), len(segs)))
    # draft 0.3: two of them again with the list as a segment table (section 11.5), the original chunk deflated
    # (section 5.2), audio and other comments unchanged
    known = {src_bext_body(fsegs[0]): SRC_BEXT_DEFLATED}
    if inflate_bounded(base64.b64decode(SRC_BEXT_DEFLATED)) != src_bext_body(fsegs[0]):
        failures += 1
        log.append("SRC_BEXT_DEFLATED does not inflate to the bext of the source of segment 1   <-- FAILED")
    for name, src in TABLE_SAMPLES:
        if src not in ogg_files:
            failures += 1
            log.append("%s not written: %s is missing   <-- FAILED" % (name, src))
            continue
        base, comments, sizes = ogg_files[src][0], [], (0, 0)
        for c in read_ogg(base)["comments"]:
            if c.startswith(LIST_KEY + "="):
                listel = ET.fromstring(c.partition("=")[2])
                listel.find("TT_VERSION").text = TABLE_SPEC_VERSION
                listel.find("WRITER").text = TABLE_WRITER
                deflate_origin_chunks(listel, known)
                header, segments = list_model(listel)
                table = TABLE_KEY + "=" + table_text(header, segments)
                sizes = (len(c.encode("utf-8")), len(table.encode("utf-8")))
                c = table
            comments.append(c)
        data = ogg_with_comments(base, comments)
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(data)
        man["files"][name] = describe_ogg(data)
        ogg_files[name] = (data, ogg_files[src][1])
        log.append("written %s: %d bytes, the list of %s (%d bytes) as a table of %d bytes" % (name, len(data), src,
                                                                                            sizes[0], sizes[1]))
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)

    # 1. every sample checks clean
    for name in files:
        with open(os.path.join(OUT_DIR, name), "rb") as f:
            rep = check_bytes(f.read(), man["files"][name], name)
        bad = [c for c, s in rep.status.items() if s not in ("OK", "n/a")]
        log.append(rep.summary_line() + ("" if not bad and not rep.extra else "   <-- FAILED"))
        failures += 1 if bad or rep.extra else 0
        for line in rep.lines:
            if "spec check" in line:
                log.append("   " + line.strip())
                failures += 1

    # 1b. every sample passes the validator (the rules of the specification), which reports its weight (section 12)
    for name in files:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = validate_file(os.path.join(OUT_DIR, name))
        result = [l for l in buf.getvalue().splitlines() if l.startswith("RESULT")]
        log.append("validate %s: %s" % (name, result[0] if result else "no result"))
        failures += 0 if code == 0 and result and "0 warning" in result[0] else 1
        weight = [l for l in buf.getvalue().splitlines() if "weight (section 12): file" in l]
        log.append("   " + (weight[0][7:] if weight else "no weight line   <-- FAILED"))
        failures += 0 if weight else 1

    # 2. the checker sees every kind of rewrite (mutations of the full file)
    entry = man["files"][FULL]
    cases = [
        ("segment list dropped from iXML", dict(no_list=True), dict(ixml_file="SAME", ixml_list="LOST")),
        ("ttsg chunk dropped", dict(no_ttsg=True), dict(ttsg="LOST")),
        ("cue 3 renumbered 33", dict(cue_override={3: (33, fsegs[2]["start"])}), dict(cue="CHANGED", adtl="CHANGED")),
        ("cue 2 moved by 0.1 s", dict(cue_override={2: (2, fsegs[1]["start"] + 4800)}), dict(cue="CHANGED")),
        ("one audio sample changed", dict(flip_sample=True), dict(audio="CHANGED")),
        ("LIST/adtl moved after data", dict(adtl_after=True), dict(order="CHANGED", adtl="OK")),
        ("iXML reformatted, same content", dict(reformat_ixml=True), dict(ixml_file="SAME", ixml_list="SAME")),
    ]
    for label, opts, expect in cases:
        rep = check_bytes(build_full(fpcm, fsegs, ftotal, opts), entry, label)
        wrong = {k: rep.status[k] for k, v in expect.items() if rep.status[k] != v}
        others = {k: s for k, s in rep.status.items() if k not in expect and s not in ("OK", "n/a")}
        if label == "segment list dropped from iXML":
            others = {k: s for k, s in others.items() if k != "ixml_file"}
        ok = not wrong and not others
        failures += 0 if ok else 1
        log.append("mutation %-34s %s %s" % (label + ":", "OK" if ok else "FAILED", (wrong or others) if not ok else ""))
        if label == "one audio sample changed" and not any("AUDIO_SHA256 no longer matches" in l for l in rep.lines):
            failures += 1
            log.append("   FAILED: the AUDIO_SHA256 rule did not fire")
        if label == "cue 2 moved by 0.1 s" and not any("not at START_SAMPLE" in l for l in rep.lines):
            failures += 1
            log.append("   FAILED: the moved-cue rule did not fire")

    # 3. the search words: each one in its own carrier only
    fdata = files[FULL][0]
    _form, chunks = parse_riff(fdata)
    for token_key, carrier in (("file", None), ("labl", "LIST/adtl"), ("note", "LIST/adtl"), ("ixml", "iXML"),
                               ("chunk", "ttsg"), ("xmp", "_PMX")):
        token = TOKENS[token_key].encode("ascii")
        holders = sorted(set(c["key"] for c in chunks if token in c["body"]))
        if token_key == "file":
            ok = holders == ["LIST/INFO", "bext", "iXML"]
        else:
            ok = holders == [carrier]
        failures += 0 if ok else 1
        log.append("search word %-10s in %s %s" % (TOKENS[token_key], ", ".join(holders), "OK" if ok else "FAILED"))
    for a in TOKENS.values():
        for b in TOKENS.values():
            if a != b and a in b:
                failures += 1
                log.append("search word %s is part of %s   <-- FAILED" % (a, b))
    pmx = next(c for c in chunks if c["key"] == "_PMX")["body"]
    exp = [dict(m, start=str(m["start"]), duration=str(m["duration"])) for m in man["files"][FULL]["xmp_expected"]]
    ok = read_xmp_markers(pmx) == exp
    failures += 0 if ok else 1
    log.append("XMP markers read back by the checker: %s" % ("OK" if ok else "FAILED"))
    mdata = files[MANY][0]
    _form, mchunks = parse_riff(mdata)
    for token_key, carrier in (("many_list", "iXML"), ("many_labl", "LIST/adtl")):
        token = TOKENS[token_key].encode("ascii")
        holders = sorted(set(c["key"] for c in mchunks if token in c["body"]))
        ok = holders == [carrier]
        failures += 0 if ok else 1
        log.append("search word %-12s in %s %s" % (TOKENS[token_key], ", ".join(holders), "OK" if ok else "FAILED"))

    # 4. Ogg samples (draft 0.2): clean check, validator, decoded length, rewrites, search words
    for name, (data, model_total) in ogg_files.items():
        rep = check_ogg_bytes(data, man["files"][name], name)
        bad = [c for c, s in rep.status.items() if s not in ("OK", "n/a")]
        log.append(rep.summary_line() + ("" if not bad and not rep.extra else "   <-- FAILED"))
        failures += 1 if bad or rep.extra else 0
        for line in rep.lines:
            if "spec check" in line:
                log.append("   " + line.strip())
                failures += 1
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = validate_file(os.path.join(OUT_DIR, name))
        result = [l for l in buf.getvalue().splitlines() if l.startswith("RESULT")]
        log.append("validate %s: %s" % (name, result[0] if result else "no result"))
        failures += 0 if code == 0 and result and "0 warning" in result[0] else 1
        weight = [l for l in buf.getvalue().splitlines() if "weight (section 12): file" in l]
        log.append("   " + (weight[0][7:] if weight else "no weight line   <-- FAILED"))
        failures += 0 if weight else 1
        frames = man["files"][name]["frames"]
        failures += 0 if frames == model_total else 1
        log.append("decoded length %s: %d frames, %d in the WAV sample %s" % (name, frames, model_total,
                                                                            "OK" if frames == model_total else "FAILED"))
    if OGG_FULL in ogg_files:
        base, entry = ogg_files[OGG_FULL][0], man["files"][OGG_FULL]
        comments = read_ogg(base)["comments"]
        renumbered = []
        for c in comments:
            key, _sep, value = c.partition("=")
            k = key.upper()
            if k.startswith("CHAPTER") and k[7:10].isdigit():
                renumbered.append("CHAPTER%03d%s=%s" % (int(k[7:10]) + 10, k[10:], value))
            else:
                renumbered.append(c)
        cases = [
            ("comments reordered, one added", ogg_with_comments(base, comments[::-1] + ["ENCODER=a tag editor"]),
             dict(), ["ENCODER"]),
            ("segment list dropped", ogg_with_comments(base, [c for c in comments if not c.startswith("TT_SEGMENT_LIST=")]),
             dict(list="LOST"), []),
            ("chapters renumbered", ogg_with_comments(base, renumbered), dict(chapters="SAME"), []),
            ("one audio byte changed", ogg_flip_audio_byte(base), dict(audio="CHANGED"), []),
            ("header pages cut otherwise", ogg_with_comments(base, comments, max_segments=17), dict(), []),
        ]
        for label, data, expect, extra in cases:
            rep = check_ogg_bytes(data, entry, label)
            wrong = {k: rep.status[k] for k, v in expect.items() if rep.status[k] != v}
            others = {k: s for k, s in rep.status.items() if k not in expect and s not in ("OK", "n/a")}
            ok = not wrong and not others and rep.extra == extra
            failures += 0 if ok else 1
            log.append("ogg mutation %-31s %s %s" % (label + ":", "OK" if ok else "FAILED",
                                                    (wrong or others or rep.extra) if not ok else ""))
            if label == "one audio byte changed" and not any("AUDIO_SHA256 no longer matches" in l for l in rep.lines):
                failures += 1
                log.append("   FAILED: the AUDIO_SHA256 rule did not fire")
        # the validator's chapter rules (section 11.2): a start exactly on a half millisecond (24 frames at 48 kHz)
        # rounded either way, a chapter 1 ms off, a chapter number of four digits
        for label, data, want in (
                ("half ms, chapter rounded up", ogg_moved_segment(base, 24, "00:00:00.501"), "PASS"),
                ("half ms, chapter rounded to even", ogg_moved_segment(base, 24), "PASS"),
                ("chapter 1 ms after its start", ogg_moved_segment(base, 0, "00:00:00.501"), "FAIL"),
                ("chapter number of four digits", ogg_with_comments(base, comments + [
                    "CHAPTER1000=00:00:06.000", "CHAPTER1000NAME=Four digits"]), "FAIL")):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                validate_ogg(label, data)
            result = [l for l in buf.getvalue().splitlines() if l.startswith("RESULT")]
            ok = bool(result) and result[0].startswith("RESULT " + want)
            failures += 0 if ok else 1
            log.append("ogg validator %-33s %s %s" % (label + ":", "OK" if ok else "FAILED", "" if ok else result))
    for name, checks in ((OGG_FULL, (("ogg_file", ["COMMENT", "DESCRIPTION", "KEYWORDS"]), ("ogg_chapter", None),
                                     ("ogg_list", ["TT_SEGMENT_LIST"]))),
                         (OGG_MANY, (("ogg_many_list", ["TT_SEGMENT_LIST"]), ("ogg_many_chap", None))),
                         (OPUS_FULL_TABLE, (("ogg_file", ["COMMENT", "DESCRIPTION", "KEYWORDS"]), ("ogg_chapter", None),
                                            ("ogg_list", [TABLE_KEY]))),
                         (OGG_MANY_TABLE, (("ogg_many_list", [TABLE_KEY]), ("ogg_many_chap", None)))):
        if name not in ogg_files:
            continue
        cm = comment_map(read_ogg(ogg_files[name][0])["comments"])
        for token_key, expect in checks:
            holders = sorted(k for k, values in cm.items() if any(TOKENS[token_key] in v for v in values))
            if expect is None:                       # one chapter name only
                ok = len(holders) == 1 and holders[0].startswith("CHAPTER") and holders[0].endswith("NAME")
            else:
                ok = holders == expect
            failures += 0 if ok else 1
            log.append("search word %-15s in %s %s" % (TOKENS[token_key], ", ".join(holders), "OK" if ok else "FAILED"))

    # 4b. draft 0.3: a list written as a table and read back is the same list, element by element and in order (a
    # list of edge cases: every element and value); the validator's rules on tables and on deflated chunks
    def canon_el(e, ordered=True):
        kids = [canon_el(k, ordered) for k in e]
        if not ordered:
            kids.sort()
        return (e.tag, tuple(sorted(e.attrib.items())), (e.text or "") if len(e) == 0 else "", tuple(kids))

    def round_trip(listel, ordered=True):
        header, segments = list_model(listel)
        back = ET.fromstring(list_xml(*table_model(table_text(header, segments))))
        segs_of = lambda r: [canon_el(x, ordered) for x in r.findall("TT_SEGMENT")]          # noqa: E731
        others = lambda r: sorted(canon_el(x, False) for x in r if x.tag != "TT_SEGMENT")    # noqa: E731
        return segs_of(listel) == segs_of(back) and others(listel) == others(back)

    lists = []
    for name in files:
        _form, wchunks = parse_riff(files[name][0])
        root, _err, _parts, _lst = ixml_parts(next(c for c in wchunks if c["key"] == "iXML")["body"])
        lists.append((name, find_list(root)))
    for name, *_rest in OGG_SAMPLES:
        if name in ogg_files:
            lists.append((name, ET.fromstring(comment_map(read_ogg(ogg_files[name][0])["comments"])[LIST_KEY][0])))
    for label, listel, ordered in [(n, l, True) for n, l in lists] + [("edge cases", ET.fromstring(edge_list()), False)]:
        ok = round_trip(listel, ordered)
        failures += 0 if ok else 1
        log.append("table round trip %-19s %s" % (label + ":", "OK" if ok else "FAILED"))
    cases = []
    if OPUS_FULL_TABLE in ogg_files and OPUS_FULL in ogg_files:
        tbase = ogg_files[OPUS_FULL_TABLE][0]
        tcomments = read_ogg(tbase)["comments"]
        tvalue = comment_map(tcomments)[TABLE_KEY][0]
        xml_value = comment_map(read_ogg(ogg_files[OPUS_FULL][0])["comments"])[LIST_KEY][0]
        tobj = json.loads(tvalue)
        fewer = json.dumps(dict(tobj, ROWS=tobj["ROWS"][:-1]), ensure_ascii=False, separators=(",", ":"))
        k = 40
        damaged = tvalue.replace(SRC_BEXT_DEFLATED, SRC_BEXT_DEFLATED[:k] + ("A" if SRC_BEXT_DEFLATED[k] != "A" else "B")
                                 + SRC_BEXT_DEFLATED[k + 1:])

        def with_table(value):
            return ogg_with_comments(tbase, [(TABLE_KEY + "=" + value) if c.startswith(TABLE_KEY + "=") else c
                                             for c in tcomments])
        cases += [("table and list in one file", ogg_with_comments(tbase, tcomments + [LIST_KEY + "=" + xml_value]), "FAIL"),
                  ("table with a row missing", with_table(fewer), "FAIL"),
                  ("table, deflated chunk damaged", with_table(damaged), "FAIL"),
                  ("table of TT_VERSION 0.2", with_table(tvalue.replace('"TT_VERSION":"0.3"', '"TT_VERSION":"0.2"')),
                   "PASS (0 fail, 2 warning)")]
        outside = tvalue.replace('"<ORIGIN>', '"x<ORIGIN>', 1)   # an XML cell with text before its element
        if outside == tvalue:
            failures += 1
            log.append("validator table, text outside an XML cell: FAILED (no XML cell <ORIGIN> to change)")
        else:
            cases.append(("table, text outside an XML cell", with_table(outside), "FAIL"))
    src_b64 = base64.b64encode(src_bext_body(fsegs[0])).decode("ascii")

    def wav_with_ixml(transform):
        _form, wch = parse_riff(files[FULL][0])
        before, after, pcm_, seen = b"", b"", b"", False
        for c in wch:
            if c["id"] == b"data":
                pcm_, seen = c["body"], True
                continue
            raw = chunk(c["id"], transform(c["body"]) if c["id"] == b"iXML" else c["body"])
            if seen:
                after += raw
            else:
                before += raw
        return wav_bytes(before, pcm_, after)
    deflate_xml = lambda b: b.replace(("<DATA_BASE64>%s</DATA_BASE64>" % src_b64).encode("ascii"),         # noqa: E731
                                      ("<DATA_DEFLATE_BASE64>%s</DATA_DEFLATE_BASE64>" % SRC_BEXT_DEFLATED).encode("ascii"))
    cases += [("WAV, deflated chunk, TT_VERSION 0.3",
               wav_with_ixml(lambda b: deflate_xml(b).replace(b"<TT_VERSION>0.1<", b"<TT_VERSION>0.3<")),
               "PASS (0 fail, 0 warning)"),
              ("WAV, deflated chunk, TT_VERSION 0.1", wav_with_ixml(deflate_xml), "PASS (0 fail, 1 warning)")]
    for label, data, want in cases:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            validate_file(label, data)
        result = [l for l in buf.getvalue().splitlines() if l.startswith("RESULT")]
        ok = bool(result) and result[0].startswith("RESULT " + want)
        failures += 0 if ok else 1
        log.append("validator %-37s %s %s" % (label + ":", "OK" if ok else "FAILED", "" if ok else result))
    try:
        inflate_bounded(zlib.compress(b"\x00" * 2000), limit=1000)
        ok = False
    except ValueError:
        ok = True
    failures += 0 if ok else 1
    log.append("a deflated chunk that inflates beyond the limit is refused: %s" % ("OK" if ok else "FAILED"))

    # 5. optional: ffprobe reads the markers as chapters
    probe = shutil.which("ffprobe") if use_ffprobe else None
    if probe:
        for name in list(files) + list(ogg_files):
            try:
                r = subprocess.run([probe, "-v", "error", "-show_chapters", "-of", "json", os.path.join(OUT_DIR, name)],
                                   capture_output=True, text=True, timeout=60)
                n = len(json.loads(r.stdout or "{}").get("chapters", []))
                log.append("ffprobe %s: %d chapter(s), exit %d" % (name, n, r.returncode))
            except Exception as e:                       # noqa: BLE001 (information only)
                log.append("ffprobe %s: not run (%s)" % (name, e))
    else:
        log.append("ffprobe: not on the PATH, skipped")

    log.append("SELF-CHECK %s (%d failure(s))" % ("PASSED" if failures == 0 else "FAILED", failures))
    with open(SELFCHECK_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(log) + "\n")
    print("\n".join(log))
    return 0 if failures == 0 else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="TT File Format v0.3 sample files and checker (stdlib).")
    ap.add_argument("--check", metavar="FILE", help="compare a copy that went through another program")
    ap.add_argument("--validate", metavar="FILE", help="check any TT file against the rules of the specification")
    ap.add_argument("--as", dest="as_name", metavar="NAME", help="sample name of the file when it was renamed")
    ap.add_argument("--no-ffprobe", action="store_true", help="skip the optional ffprobe reading")
    ap.add_argument("--make-ogg-audio", action="store_true", help="kit maintainers: encode ogg_audio/ again (ffmpeg)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if args.make_ogg_audio:
        return make_ogg_audio()
    if args.validate:
        return validate_file(args.validate)
    if args.check:
        return check_file(args.check, args.as_name)
    return generate(use_ffprobe=not args.no_ffprobe)


if __name__ == "__main__":
    sys.exit(main())
