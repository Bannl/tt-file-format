# -*- coding: utf-8 -*-
"""make_tt_spec_samples.py: sample files for the TT File Format draft 0.1 (../SPEC.md), a checker and a validator.

    py -I make_tt_spec_samples.py                          writes samples/ (3 WAV + manifest.json) and SELFCHECK.txt
    py -I make_tt_spec_samples.py --check FILE [--as NAME] compares a copy that went through another program
    py -I make_tt_spec_samples.py --validate FILE          checks ANY TT file against the rules of the specification

Each candidate carrier of the segment data holds its own search word, so that a search in a library tool tells
which carrier it indexes (see TEST_PROTOCOL.md). Python standard library only; writes only inside the
folder of this script.

Copyright 2026 Nextale Audio. MIT licence (see ../LICENSE.md).
"""
import argparse
import array
import base64
import contextlib
import hashlib
import io
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
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

TOKENS = {
    "file": "zorbfile",          # file-level summary only (bext, LIST/INFO, iXML USER and ASWG)
    "labl": "zorblabl",          # one labl only (segment 3)
    "note": "zorbnote",          # one note only (segment 3)
    "ixml": "zorbixml",          # the iXML segment list only (segment 3 keywords)
    "chunk": "zorbchunk",        # the ttsg chunk only (segment 3 keywords)
    "xmp": "zorbxmp",            # the XMP markers only (segment 3 keywords and comment)
    "many_list": "zorbmanyixml", # tt_v0_many.wav: segment 397, segment list only
    "many_labl": "zorbmanylabl", # tt_v0_many.wav: segment 398, labl only
}
# No word is a prefix or a part of another one: a search for one never finds the carrier of another.

CARRIERS = ["audio", "fmt", "bext", "info", "ixml_file", "ixml_list", "ttsg", "xmp", "cue", "adtl", "order"]


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


def segment_lines(s, variant, rich):
    kw = s["kw"]
    if s["n"] == 3 and rich:
        kw += ", " + TOKENS["ixml" if variant == "ixml" else "chunk"]
    if variant == "ixml" and s.get("kw_list_extra"):
        kw += ", " + s["kw_list_extra"]
    lines = ["<TT_SEGMENT>", el("SEGMENT_ID", s["uid"]), el("CUE_ID", s["cue_id"]), el("START_SAMPLE", s["start"]),
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
        lines += [el("BIT_DEPTH", s["bits"]), el("CHANNELS", 2), el("FORMAT", "wav"),
                  el("TIME_REFERENCE", s["src_tref"]), el("CONVERSION", s["conversion"])]
        if s["conversion"] == "exact":
            lines.append(el("CONVERSION_NOTE", "16 bits to 24 bits"))
        if s["n"] == 1:
            src_bext = bext_body("Original recording of a door slam", "SRC-0001", s["src_tref"],
                                 "A=PCM,F=48000,W=24,M=stereo\r\n")
            lines += ["<CHUNK_LIST>", "<CHUNK>", el("CHUNK_ID", "bext"),
                      el("DATA_BASE64", base64.b64encode(src_bext).decode("ascii")), "</CHUNK>", "</CHUNK_LIST>"]
    lines.append("</ORIGIN>")
    lines.append(el("STATUS", "accepted"))
    if rich and s["n"] == 2:
        lines.append(el("TTKIT_UNKNOWN_ELEMENT", "an element of another program: it must survive"))
    lines.append("</TT_SEGMENT>")
    return lines


def segment_list_lines(segs, total, audio_sha, variant, rich):
    lines = ["<TT_SEGMENT_LIST>", el("TT_VERSION", SPEC_VERSION), el("WRITER", WRITER), el("SAMPLE_RATE", SR),
             el("TOTAL_FRAMES", total), el("AUDIO_SHA256", audio_sha), el("SEGMENT_COUNT", len(segs))]
    for s in segs:
        lines += segment_lines(s, variant, rich)
    lines.append("</TT_SEGMENT_LIST>")
    return lines


def summary(segs):
    names = ", ".join(s["fx"] for s in segs)
    keywords = []
    for s in segs:
        for k in s["kw"].split(","):
            k = k.strip()
            if k and k not in keywords:
                keywords.append(k)
    return "%d sounds: %s. %s" % (len(segs), names, TOKENS["file"]), ", ".join(keywords + [TOKENS["file"]])


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
    def __init__(self, title):
        self.title, self.lines, self.status = title, [], {c: "n/a" for c in CARRIERS}
        self.extra = []

    def set(self, carrier, status, detail=""):
        self.status[carrier] = status
        self.lines.append("[%s] %s%s" % (status, carrier, (": " + detail) if detail else ""))

    def info(self, text):
        self.lines.append("       " + text)

    def summary_line(self):
        parts = ["%s=%s" % (c, self.status[c]) for c in CARRIERS]
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


def check_file(path, as_name=None):
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        man = json.load(f)
    name = as_name or os.path.basename(path)
    entry = man["files"].get(name)
    if entry is None:
        print("Unknown file name %r: add --as %s (or %s, %s)" % (name, FULL, MINIMAL, MANY))
        return 2
    with open(path, "rb") as f:
        data = f.read()
    rep = check_bytes(data, entry, "%s (as %s)" % (path, name))
    print(rep.text())
    bad = [c for c, s in rep.status.items() if s in ("CHANGED", "LOST")]
    return 1 if bad or rep.extra else 0


# ---------------------------------------------------------------------------------------------
# Validator: the rules of the specification on ANY TT file (not only the samples)
# ---------------------------------------------------------------------------------------------

def validate_file(path):
    """Spec checks: structure, list header, segments, mirrored markers, audio hash, summary. 0 = no FAIL."""
    with open(path, "rb") as f:
        data = f.read()
    lines, counts = [], {"fail": 0, "warn": 0}

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

    cue = read_cue(by["cue "]["body"]) if "cue " in by else {}
    labels, notes, ltxts, order = read_adtl(by["LIST/adtl"]["body"]) if "LIST/adtl" in by else ({}, {}, {}, [])
    seen, prev, broken, no_ltxt, non_ascii = set(), -1, 0, 0, 0
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
        for key, value in s.items():
            if key.endswith("DATA_BASE64#0"):
                try:
                    base64.b64decode(value, validate=True)
                except Exception:                          # noqa: BLE001 (report, do not stop)
                    problems.append("an ORIGIN chunk is not valid base64")
        if problems:
            broken += 1
            bad("segment %d (%s): %s" % (i, sid[:13], "; ".join(problems)))
    if broken == 0:
        ok("%d segment(s): ids, ranges, names and mirrored markers" % len(segs))
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
    man = dict(spec=SPEC_VERSION, writer=WRITER, tokens=TOKENS, files={})
    for name, (data, segs, foreign, xmp_exp) in files.items():
        with open(os.path.join(OUT_DIR, name), "wb") as f:
            f.write(data)
        man["files"][name] = describe(data, segs, foreign, xmp_exp)
        log.append("written %s: %d bytes, %d segments" % (name, len(data), len(segs)))
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)

    failures = 0
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

    # 1b. every sample passes the validator (the rules of the specification)
    for name in files:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = validate_file(os.path.join(OUT_DIR, name))
        result = [l for l in buf.getvalue().splitlines() if l.startswith("RESULT")]
        log.append("validate %s: %s" % (name, result[0] if result else "no result"))
        failures += 0 if code == 0 and result and "0 warning" in result[0] else 1

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

    # 4. optional: ffprobe reads the markers as chapters
    probe = shutil.which("ffprobe") if use_ffprobe else None
    if probe:
        for name in files:
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
    ap = argparse.ArgumentParser(description="TT File Format v0.1 sample files and checker (stdlib).")
    ap.add_argument("--check", metavar="FILE", help="compare a copy that went through another program")
    ap.add_argument("--validate", metavar="FILE", help="check any TT file against the rules of the specification")
    ap.add_argument("--as", dest="as_name", metavar="NAME", help="sample name of the file when it was renamed")
    ap.add_argument("--no-ffprobe", action="store_true", help="skip the optional ffprobe reading")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if args.validate:
        return validate_file(args.validate)
    if args.check:
        return check_file(args.check, args.as_name)
    return generate(use_ffprobe=not args.no_ffprobe)


if __name__ == "__main__":
    sys.exit(main())
