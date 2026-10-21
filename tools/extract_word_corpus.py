#!/usr/bin/env python3
"""Extract the compressed word corpus from the original TT.EXE.

The corpus lives in the data segment:

* ``DS:0x214e`` — 46 records of 23 little-endian pointers.  Each pointer is a
  byte offset into the compressed stream at ``DS:0x2992``.
* ``DS:0x2992`` — a bit-packed stream.  Each entry is
  ``[5-bit length][length × 5-bit letter code]``.  A group starts with a
  5-bit entry count.
* Letter codes: 0 = space, 1..26 = a..z, 27 = hyphen/space, 30 = period/EOF.

The extraction is bit-exact with ``FUN_1000_6802`` (the 5-bit reader) and
``FUN_1000_665a`` (the word decoder).  Run this after changing TT.EXE paths::

    python tools/extract_word_corpus.py [TT.EXE] [OUTPUT.json]

The generated JSON is consumed by ``tttutor/invaders.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_EXE = Path("/mnt/qdata1/tt/game/extracted/TT.EXE")
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tttutor" / "data" / "tt_word_corpus.json"

IMAGE_BASE = 0xFAE0          # file offset of DS:0000
TABLE_DS = 0x214E
STREAM_DS = 0x2992
STREAMS = 46
BUCKETS = 23
RECORD_SIZE = 0x2E


class BitReader:
    """Exact port of FUN_1000_6802 (5-bit MSB-first with 7-bit seed)."""

    def __init__(self, data: bytes, ptr: int):
        self.data = data
        self.ptr = ptr
        self.bitpos = 7

    def read5(self) -> int:
        if self.ptr >= len(self.data):
            raise IndexError("word stream overrun")
        b = self.data[self.ptr]
        if self.bitpos <= 4:
            self.ptr += 1
            if self.bitpos < 4:
                b = ((b << (4 - self.bitpos)) |
                     (self.data[self.ptr] >> (self.bitpos + 4))) & 0xFF
            self.bitpos += 3
        else:
            self.bitpos -= 4
            shift = self.bitpos
            self.bitpos -= 1
            b = (b >> shift) & 0x1F
        return b & 0x1F


def decode_word(codes: list[int]) -> str:
    out = []
    for c in codes:
        if c == 0:
            out.append(" ")
        elif c == 27:
            out.append("-")      # punctuation variant; may be a space
        elif c == 30:
            out.append(".")      # punctuation variant; may be end-of-word
        else:
            out.append(chr(c | 0x60))
    return "".join(out)


def extract(exe: Path) -> dict:
    data = exe.read_bytes()
    entries = []
    stats = {"groups": 0, "empty_groups": 0, "errors": []}

    def word(ds: int) -> int:
        p = IMAGE_BASE + ds
        return int.from_bytes(data[p:p + 2], "little")

    for stream in range(STREAMS):
        for bucket in range(BUCKETS):
            off = word(TABLE_DS + stream * RECORD_SIZE + bucket * 2)
            try:
                br = BitReader(data, IMAGE_BASE + STREAM_DS + off)
                count = br.read5()
                if count == 0:
                    stats["empty_groups"] += 1
                    continue
                stats["groups"] += 1
                for index in range(count):
                    length = br.read5()
                    if length == 0:
                        stats["errors"].append(
                            [stream, bucket, index, "zero-length"])
                        break
                    if length > 40:
                        stats["errors"].append(
                            [stream, bucket, index, "length", length])
                        break
                    codes = [br.read5() for _ in range(length)]
                    text = decode_word(codes)
                    if text:
                        entries.append({
                            "stream": stream,
                            "bucket": bucket,
                            "word": text,
                            "codes": codes,
                        })
            except IndexError:
                stats["errors"].append([stream, bucket, "overrun"])
    stats["entries"] = len(entries)
    stats["unique"] = len({e["word"] for e in entries})
    return {
        "source": "TT.EXE DS:0x214e / DS:0x2992",
        "streams": STREAMS,
        "buckets": BUCKETS,
        "stats": stats,
        "entries": entries,
    }


def main(argv: list[str]) -> int:
    exe = Path(argv[1]) if len(argv) > 1 else DEFAULT_EXE
    out = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    if not exe.exists():
        print(f"TT.EXE not found: {exe}", file=sys.stderr)
        return 1
    corpus = extract(exe)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(corpus, indent=1), encoding="utf-8")
    txt = out.with_suffix(".txt")
    txt.write_text("\n".join(sorted({e["word"] for e in corpus["entries"]})) + "\n",
                   encoding="utf-8")
    s = corpus["stats"]
    print(f"wrote {out}")
    print(f"wrote {txt}")
    print(f"groups={s['groups']} empty={s['empty_groups']} "
          f"entries={s['entries']} unique={s['unique']} errors={len(s['errors'])}")
    if s["errors"]:
        print("errors:", s["errors"][:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
