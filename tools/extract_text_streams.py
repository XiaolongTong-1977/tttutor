#!/usr/bin/env python3
"""Extract the token/macro lesson-text streams from TT.EXE.

The streams live at ``DS:0x8632`` (51 little-endian offsets into
``DS:0x8698``).  ``FUN_1000_64cc`` interprets them:

* ``0x00 0x00``        — return from a macro
* ``0x00 <string> 0x00`` — literal string
* ``0x40..0x7f``       — macro call: ``table[byte & 0x3f]``
* ``0x01..0x3f``       — word token: corpus stream ``(byte & 0x3f) - 1``
* ``0x80..0xff``       — special content generator ``token_table[byte & 0x7f]``

The output keeps the structure while naming every token.  It is the input for
``tttutor/original_text.py``, which fills word tokens from the extracted corpus
and implements the content generators.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_EXE = Path("/mnt/qdata1/tt/game/extracted/TT.EXE")
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tttutor" / "data" / "tt_text_streams.json"

IMAGE_BASE = 0xFAE0
TABLE_DS = 0x8632
STREAM_DS = 0x8698
STREAMS = 51


def extract(exe: Path) -> dict:
    data = exe.read_bytes()

    def word(ds: int) -> int:
        p = IMAGE_BASE + ds
        return int.from_bytes(data[p:p + 2], "little")

    pointers = [word(TABLE_DS + i * 2) for i in range(STREAMS)]
    streams = []
    for index, off in enumerate(pointers):
        ptr = IMAGE_BASE + STREAM_DS + off
        stack: list[int] = []
        tokens: list[list] = []
        steps = 0
        while steps < 100_000:
            steps += 1
            if ptr >= len(data):
                tokens.append(["ERROR", "overrun"])
                break
            b = data[ptr]
            ptr += 1
            if b == 0:
                if data[ptr] != 0:
                    end = ptr
                    while data[end] != 0:
                        end += 1
                    raw = data[ptr:end]
                    tokens.append(["LIT", raw.decode("latin1")])
                    ptr = end + 1
                else:
                    if not stack:
                        break
                    ptr = stack.pop()
            elif b & 0x80:
                tokens.append(["TOKEN", b & 0x7F])
            elif b & 0x40:
                macro = b & 0x3F
                stack.append(ptr)
                ptr = IMAGE_BASE + STREAM_DS + pointers[macro]
                tokens.append(["MACRO", macro])
            else:
                tokens.append(["WORD", (b & 0x3F) - 1])
        streams.append({"index": index, "offset": off, "tokens": tokens,
                        "steps": steps})
    return {
        "source": "TT.EXE DS:0x8632 / DS:0x8698",
        "streams": streams,
    }


def main(argv: list[str]) -> int:
    exe = Path(argv[1]) if len(argv) > 1 else DEFAULT_EXE
    out = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    if not exe.exists():
        print(f"TT.EXE not found: {exe}", file=sys.stderr)
        return 1
    result = extract(exe)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    for s in result["streams"][:12]:
        preview = " ".join(
            f"{k}:{v}" for k, v in s["tokens"][:14]
        )
        print(f"  stream {s['index']:2d}: {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
