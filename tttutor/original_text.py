"""Original TT.EXE lesson/test text generator.

TT.EXE does not store finished lesson sentences.  It stores 51 token streams
(``DS:0x8632`` / ``DS:0x8698``) that are expanded by ``FUN_1000_64cc``:

* literals,
* macro calls,
* word tokens backed by the 46-stream compressed corpus, and
* 44 special content generators (names, addresses, phone numbers, dates,
  money, arithmetic, punctuation).

This module is a Python port of that pipeline.  The token stream structure is
bit-exact (see ``tools/extract_text_streams.py``); the content generators are
ported from the decompiled ``0x687d..0xc773`` routines.  Random choices are
made with a caller-supplied ``random.Random`` so tests are deterministic.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Iterable, Optional

_DATA = Path(__file__).resolve().parent / "data"
_STREAMS_PATH = _DATA / "tt_text_streams.json"
_CORPUS_PATH = _DATA / "tt_word_corpus.json"

# Token index -> corpus stream(s).  Derived from the decompiled token
# functions 0xc3f6..0xc773.
_WORD_STREAMS = {
    16: (0,), 17: (1,), 18: (20, 21), 19: (2,), 20: (0,),
    21: (3,), 22: (2,), 23: (9, 10, 11, 12), 24: (27, 28, 29, 30),
    25: (4,), 26: (4,), 27: (11,), 28: (10,), 29: (4,), 30: (4,),
    31: (23,), 32: (13,), 33: (13,), 34: (27,), 35: (15,), 36: (16,),
    37: (14,), 38: (14,), 39: (14,), 40: (26,), 41: (26,),
    42: (25,), 43: (22,),
}

# Suffix helpers used by the token functions.
_SUFFIX = {
    20: "possessive", 22: "possessive",
    33: "plural", 39: "plural",
    37: "ing", 40: "ing", 42: "ing", 43: "ing",
    38: "past", 41: "past",
}

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'.;:\-]*")


def _load() -> tuple[list[list], dict[int, list[str]]]:
    streams: list[list] = []
    if _STREAMS_PATH.exists():
        try:
            raw = json.loads(_STREAMS_PATH.read_text(encoding="utf-8"))
            streams = [s["tokens"] for s in raw.get("streams", [])]
        except Exception:
            streams = []
    by_stream: dict[int, list[str]] = {}
    if _CORPUS_PATH.exists():
        try:
            raw = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
            for e in raw.get("entries", []):
                w = e.get("word", "")
                if w and 1 <= len(w) <= 14:
                    by_stream.setdefault(int(e["stream"]), []).append(w)
        except Exception:
            by_stream = {}
    return streams, by_stream


STREAMS, WORDS_BY_STREAM = _load()
ALL_WORDS = sorted({w for ws in WORDS_BY_STREAM.values() for w in ws})


class TemplateRenderer:
    """Expand one of the original token streams into text."""

    def __init__(self, rng: Optional[random.Random] = None,
                 allowed_keys: Optional[str] = None):
        self.rng = rng or random.Random()
        self.allowed = set(allowed_keys) if allowed_keys else None
        self.parts: list[str] = []
        self._close_char: str | None = None

    # ---- public API ---------------------------------------------------
    def render(self, stream_index: int, *, depth: int = 0) -> str:
        self.parts = []
        self._close_char = None
        self._expand(stream_index, depth=0)
        return self._join(self.parts)

    @staticmethod
    def _join(parts: list[str]) -> str:
        """Join token fragments with readable spacing.

        The original generators rely on the surrounding assembly routine for
        spaces; this reproduces its observable output closely enough for
        drills while keeping punctuation attached to the preceding word.
        """
        out: list[str] = []
        no_space_before = set(",.;:!?)]}")
        no_space_after = set("([{<")
        for part in parts:
            if not part:
                continue
            if out:
                prev = out[-1]
                if part == "'s" or part.startswith(("'s", "’s")):
                    pass
                elif prev[-1].isspace() or part[0].isspace():
                    pass
                elif part[0] in no_space_before:
                    pass
                elif prev[-1] in no_space_after:
                    pass
                else:
                    out.append(" ")
            out.append(part)
        text = "".join(out)
        return re.sub(r"[ \t]+", " ", text).strip()

    def render_words(self, stream_index: int, *, limit: int = 200) -> list[str]:
        text = self.render(stream_index)
        words = []
        for raw in _WORD_RE.findall(text):
            w = raw.strip(".,;:")
            if not w:
                continue
            if len(w) > 14:
                continue
            if self.allowed is not None and not all(
                c in self.allowed for c in w
            ):
                continue
            words.append(w)
            if len(words) >= limit:
                break
        return words

    # ---- expansion ----------------------------------------------------
    def _expand(self, stream_index: int, *, depth: int) -> None:
        if depth > 8 or not (0 <= stream_index < len(STREAMS)):
            return
        for kind, value in STREAMS[stream_index]:
            if kind == "LIT":
                self.parts.append(str(value))
            elif kind == "MACRO":
                self._expand(int(value), depth=depth + 1)
            elif kind == "WORD":
                self._word(int(value))
            elif kind == "TOKEN":
                self._token(int(value))
            elif kind == "ERROR":
                return

    # ---- corpus words -------------------------------------------------
    def _eligible(self, word: str) -> bool:
        if len(word) > 14:
            return False
        if self.allowed is None:
            return True
        return all(c in self.allowed for c in word)

    def _word(self, stream_index: int) -> str:
        words = WORDS_BY_STREAM.get(stream_index) or ALL_WORDS
        if not words:
            # No corpus available (data files missing); keep the text
            # stream rendering alive rather than crashing on choice([]).
            self.parts.append("a")
            return "a"
        # Try a few random picks that satisfy the lesson's key set.
        for _ in range(40):
            w = self.rng.choice(words)
            if self._eligible(w):
                self.parts.append(w)
                suffix = _SUFFIX.get(stream_index)
                if suffix:
                    self._suffix(suffix)
                return w
        # Fallback: a simple word that always works.
        self.parts.append("a")
        return "a"

    def _suffix(self, kind: str) -> None:
        """Apply an inflection to the last emitted word part."""
        if not self.parts:
            return
        part = self.parts[-1]
        m = re.search(r"([A-Za-z]+)$", part)
        if not m:
            return
        word = m.group(1)
        base = part[:m.start()]
        # Never inflect an already-possessive form ("savor's" + ing).
        if "'" in base or "’" in base:
            return
        if kind == "possessive":
            self.parts[-1] = base + word + "'s"
        elif kind == "plural":
            self.parts[-1] = base + word + (
                "es" if word.endswith(("s", "sh", "ch", "x", "z")) else "s"
            )
        elif kind == "ing":
            if word.endswith("e") and len(word) > 2:
                word = word[:-1]
            self.parts[-1] = base + word + "ing"
        elif kind == "past":
            if word.endswith("e"):
                self.parts[-1] = base + word + "d"
            elif word.endswith("y") and len(word) > 1:
                self.parts[-1] = base + word[:-1] + "ied"
            else:
                self.parts[-1] = base + word + "ed"
        elif kind == "period":
            self.parts[-1] = part + "."

    # ---- content generators ------------------------------------------
    def _token(self, idx: int) -> None:
        fn = getattr(self, f"_tok_{idx}", None)
        if fn is None:
            self.parts.append(" ")
        else:
            fn()

    def _pick(self, s: str) -> str:
        if not s:
            return ""
        return self.rng.choice(s)

    def _digits(self, n: int, first_nonzero: bool = False) -> str:
        out = []
        for i in range(n):
            if i == 0 and first_nonzero:
                out.append(self.rng.choice("123456789"))
            else:
                out.append(self.rng.choice("0123456789"))
        return "".join(out)

    def _name(self) -> str:
        first = self.rng.choice(WORDS_BY_STREAM.get(0) or ["Ann"])
        last = self.rng.choice(WORDS_BY_STREAM.get(1) or ["Lee"])
        return f"{first.capitalize()} {last.capitalize()}"

    # 0: punctuation from ",;-"
    def _tok_0(self):
        self.parts.append(self._pick(",;-"))

    # 1: punctuation from "...!;;"
    def _tok_1(self):
        self.parts.append(self._pick("...!;;"))

    # 2: question mark
    def _tok_2(self):
        self.parts.append("?")

    # 3: bracket/quote opener (and its close on the next call)
    def _tok_3(self):
        if self._close_char:
            self.parts.append(self._close_char)
            self._close_char = None
        else:
            opener = self._pick("([{<")
            self._close_char = {"(": ")", "[": "]", "{": "}", "<": ">"}[opener]
            self.parts.append(opener)

    # 4: full name / address line
    def _tok_4(self):
        self.parts.append(self._name())
        self.parts.append(" ")
        self.parts.append(self._digits(self.rng.randint(1, 4), True))

    # 5: money
    def _tok_5(self):
        self.parts.append(f"${self.rng.randint(1, 999)}.{self.rng.randint(0, 99):02d}")

    # 6: arithmetic expression
    def _tok_6(self):
        a = self.rng.randint(1, 99)
        b = self.rng.randint(1, 99)
        op = self.rng.choice(["+", "-", "*"])
        val = a + b if op == "+" else (a - b if op == "-" else a * b)
        self.parts.append(f"{a} {op} {b} = {val}")

    # 7: name + number (address / account)
    def _tok_7(self):
        self.parts.append(self._name())
        self.parts.append(" ")
        self.parts.append(self._digits(self.rng.randint(2, 5), True))

    # 8: time (H:MM AM/PM)
    def _tok_8(self):
        hour = self.rng.randint(1, 12)
        minute = self.rng.randint(0, 59)
        ampm = self.rng.choice(("AM", "PM"))
        self.parts.append(f"{hour}:{minute:02d} {ampm}")

    # 9: phone number (XXX) XXX-XXXX
    def _tok_9(self):
        self.parts.append(
            f"({self._digits(3, True)}) {self._digits(3)}-{self._digits(4)}"
        )

    # 10: SSN XXX-XX-XXXX
    def _tok_10(self):
        self.parts.append(f"SSN {self._digits(3, True)}-{self._digits(2)}-{self._digits(4)}")

    # 11: quotation mark
    def _tok_11(self):
        self.parts.append('"')

    # 12: exclamation mark
    def _tok_12(self):
        self.parts.append("!")

    # 13: comma
    def _tok_13(self):
        self.parts.append(",")

    # 14: conjunction/phrase
    def _tok_14(self):
        self.parts.append(self._pick(("the", "a", "and", "or")))

    # 15: symbol/password expression
    def _tok_15(self):
        self.parts.append(self._pick(("!", "@", "#", "$", "%", "^", "&", "*")))

    # 16..43: corpus words with optional suffix
    def _tok_16(self): self._word(0)
    def _tok_17(self): self._word(1)
    def _tok_18(self): self._word(self.rng.choice((20, 21)))
    def _tok_19(self): self._word(2)
    def _tok_20(self): self._word(0); self._suffix("possessive")
    def _tok_21(self): self._word(3)
    def _tok_22(self): self._word(2); self._suffix("possessive")
    def _tok_23(self): self._word(self.rng.choice((9, 10, 11, 12)))
    def _tok_24(self): self._word(self.rng.choice((27, 28, 29, 30)))
    def _tok_25(self): self._word(4)
    def _tok_26(self): self._word(4)
    def _tok_27(self): self._word(11)
    def _tok_28(self): self._word(10)
    def _tok_29(self): self._word(4)
    def _tok_30(self): self._word(4)
    def _tok_31(self): self._word(23)
    def _tok_32(self): self._word(13)
    def _tok_33(self): self._word(13); self._suffix("plural")
    def _tok_34(self): self._word(27)
    def _tok_35(self): self._word(15)
    def _tok_36(self): self._word(16)
    def _tok_37(self): self._word(26); self._suffix("ing")
    def _tok_38(self): self._word(26); self._suffix("past")
    def _tok_39(self): self._word(26); self._suffix("plural")
    def _tok_40(self): self._word(26); self._suffix("ing")
    def _tok_41(self): self._word(26); self._suffix("past")
    def _tok_42(self): self._word(25); self._suffix("ing")
    def _tok_43(self): self._word(22); self._suffix("ing")


def render_stream(index: int, *, seed: int = 0,
                  allowed_keys: Optional[str] = None) -> str:
    return TemplateRenderer(random.Random(seed), allowed_keys).render(index)


def render_words(index: int, *, seed: int = 0,
                 allowed_keys: Optional[str] = None,
                 limit: int = 200) -> list[str]:
    return TemplateRenderer(random.Random(seed), allowed_keys).render_words(
        index, limit=limit
    )


def generate_drills(stream_index: int, *, allowed_keys: Optional[str] = None,
                    drills: int = 10, words_per_line: int = 5,
                    seed: int = 0, max_line: int = 68) -> list[str]:
    """Build practice drıll lines from one original text stream.

    This mirrors the original practice-lesson pipeline: the token stream is
    expanded into words, then words are grouped into one-line drills.  It
    returns an empty list when the stream cannot supply enough usable words.
    """
    r = TemplateRenderer(random.Random(seed), allowed_keys)
    words = r.render_words(stream_index, limit=400)
    # Keep the most useful words: no leading/trailing punctuation already
    # handled by render_words; drop one-character noise except 'a'.
    words = [w for w in words if len(w) > 1 or w == "a"]
    unique = list(dict.fromkeys(words))
    if len(unique) < 6:
        return []
    rng = random.Random(seed + 1)
    lines: list[str] = []
    for _ in range(max(1, drills)):
        chunk: list[str] = []
        attempts = 0
        while len(chunk) < max(1, words_per_line) and attempts < 1000:
            attempts += 1
            w = rng.choice(unique)
            # Avoid the same word appearing more than twice in one line.
            if chunk.count(w) >= 2:
                continue
            chunk.append(w)
            if len(chunk) >= 2 and len(" ".join(chunk)) > max_line:
                chunk.pop()
                break
        if chunk:
            lines.append(" ".join(chunk))
    return lines


def generate_drills_from_words(words: Iterable[str], *, drills: int = 10,
                               words_per_line: int = 5, seed: int = 0,
                               max_line: int = 68) -> list[str]:
    """Group an existing word pool into one-line practice drills."""
    unique = list(dict.fromkeys(w for w in words if w))
    if len(unique) < 6:
        return []
    rng = random.Random(seed + 1)
    lines: list[str] = []
    for _ in range(max(1, drills)):
        chunk: list[str] = []
        attempts = 0
        while len(chunk) < max(1, words_per_line) and attempts < 1000:
            attempts += 1
            w = rng.choice(unique)
            if chunk.count(w) >= 2:
                continue
            chunk.append(w)
            if len(chunk) >= 2 and len(" ".join(chunk)) > max_line:
                chunk.pop()
                break
        if chunk:
            lines.append(" ".join(chunk))
    return lines
