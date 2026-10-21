"""Built-in lesson content and a .TST-compatible loader.

The classic Typing Tutor programs shipped their lesson texts in plain `.TST`
files — one practice line per paragraph, optional `@` paragraph terminators.
This module can read those files line-by-line. It also bundles a starter
library so the program is runnable with zero external assets.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

from .engine import Lesson


# Starter lesson library. Inspired by the public-domain old-school typing
# tutor content, but rewritten cleanly here.
HOME_ROW = [
    "a a a a a a a a a a a a a a a a a a a a",
    "s s s s s s s s s s s s s s s s s s s s",
    "d d d d d d d d d d d d d d d d d d d d",
    "f f f f f f f f f f f f f f f f f f f f",
    "j j j j j j j j j j j j j j j j j j j j",
    "k k k k k k k k k k k k k k k k k k k k",
    "l l l l l l l l l l l l l l l l l l l l",
    "asdf asdf asdf asdf asdf asdf asdf asdf",
    "jkl; jkl; jkl; jkl; jkl; jkl; jkl; jkl;",
    "asdf jkl; asdf jkl; asdf jkl; asdf jkl;",
]

LEFT_HAND = [
    "asdfg asdfg asdfg asdfg asdfg asdfg",
    "aq az as ad af ag aq az as ad af ag",
    "qa ws ed rf tg yh uj ik ol p; qa ws ed rf tg",
    "fr fr fr fr fr fr fr fr fr fr fr fr",
    "gt gt gt gt gt gt gt gt gt gt gt gt",
    "hu hu hu hu hu hu hu hu hu hu hu hu",
    "iv iv iv iv iv iv iv iv iv iv iv iv",
]

RIGHT_HAND = [
    "jkl; jkl; jkl; jkl; jkl; jkl; jkl; jkl;",
    "jk jk jk jk jk jk jk jk jk jk jk jk",
    "jl jl jl jl jl jl jl jl jl jl jl jl",
    "lo lo lo lo lo lo lo lo lo lo lo lo",
    "p; p; p; p; p; p; p; p; p; p; p; p;",
    ".; .; .; .; .; .; .; .; .; .; .; .;",
    "/ / / / / / / / / / / /",
]

NUMBERS = [
    "123 123 123 123 123 123 123 123",
    "456 456 456 456 456 456 456 456",
    "789 789 789 789 789 789 789 789",
    "0 0 0 0 0 0 0 0 0 0 0 0",
    "1234567890 1234567890 1234567890",
    "1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0",
]

CAPS_AND_PUNCT = [
    "Aa Aa Aa Aa Aa Aa Aa Aa Aa Aa Aa Aa",
    "Bb Cc Dd Ee Ff Gg Hh Ii Jj Kk Ll Mm",
    "Nn Oo Pp Qq Rr Ss Tt Uu Vv Ww Xx Yy Zz",
    "Aa; Ss; Dd; Ff; Jj; Kk; Ll;",
    "I'm you're it's can't don't isn't",
    'It is "easy" to learn, right?',
]

SENTENCES = [
    "the quick brown fox jumps over the lazy dog.",
    "Pack my box with five dozen liquor jugs.",
    "Sphinx of black quartz, judge my vow.",
    "How razorback-jumping frogs can level six piqued gymnasts!",
    "A wonderful serenity has taken possession of my entire soul.",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    "She sells seashells by the seashore.",
    "I am the way, the truth, and the life.",
    "It was the best of times, it was the worst of times.",
    "To be, or not to be, that is the question.",
]

STORY = [
    "Many years later, as he faced the firing squad, Colonel Aureliano Buendia",
    "was to remember that distant afternoon when his father took him to discover",
    "ice. At that time Macondo was a village of twenty adobe houses, built on the",
    "bank of a river of clear water that ran along a bed of polished stones, which",
    "were white and enormous, like prehistoric eggs. The world was so recent that",
    "many things lacked names, and in order to indicate them it was necessary to",
    "point. Every year during the month of March a family of ragged gypsies would",
    "set up their tents near the village, with a great uproar of pipes and kettledrums",
    "and they would display new inventions, especially a magnet and a magnifying",
    "glass, which a fat man named Melquiades, who was the leader of the troupe, would",
    "demonstrate as if they were miracles. The gypsies' arrival would throw the whole",
    "village into a fever of excitement, but this time everyone was particularly",
    "impatient, because word had gone around that the gypsies were going to bring",
    "a special item for the annexation of memory.",
]

QUOTES = [
    '"Programs must be written for people to read, and only incidentally for machines to execute."',
    '"First, solve the problem. Then, write the code."',
    '"Simplicity is the ultimate sophistication."',
    '"There are two ways to write error-free programs; only the third one works."',
    '"Perl is a language where you can do the same thing a hundred different ways."',
    '"The best way to predict the future is to invent it."',
    '"Weeks of coding can save you hours of planning."',
    '"It is a truth universally acknowledged that a single man in possession of a good program must be in want of a bug."',
    '"Always code as if the guy who ends up maintaining your code is a violent psychopath who knows where you live."',
    '"Premature optimization is the root of all evil."',
]

INITIAL_TEST = [
    "Taking a test will give this program a basis for customizing individual lessons.",
    "Do not be concerned if you are not typing as quickly as you can; you will soon excel.",
    "Everyone has a quandary with number and symbol keys. Do not expect to zoom through these next sentences.",
    'Her birthday is 08/15/53. Does 73% of $546.00 equal $398.58?',
    "Item number 32 jonquils sold 2 units at $76 and 1 at $73.",
    "That is all folks!",
]

# Fingering drills — selected by Lessons → Fingering. Each drill is paired
# with a finger-placement hint in the description. The cleanest way to teach
# fingering is to walk the home row, then introduce column-staggered patterns,
# then combine into alternating-hand phrases.
#
# Left hand: a(pinky) s(ring) d(middle) f(index) g(index)
# Right hand: ;(pinky) l(ring) k(middle) j(index) m(index)
FINGER_LEFT_HOME  = [
    "a a a a a", "s s s s s", "d d d d d", "f f f f f", "g g g g g",
    "asdf asdf asdf",
    "fdsa fdsa fdsa",
    "a s d f a s d f",
]
FINGER_RIGHT_HOME = [
    "; ; ; ; ;", "l l l l l", "k k k k k", "j j j j j", "m m m m m",
    "jkl; jkl; jkl;",
    ";lkj ;lkj ;lkj",
    "; l k j ; l k j",
]
FINGER_STAGGER    = [
    "fad fad fad",
    "fads fads fads",
    "adsf dadf asdf",
    "adsf ;lkj",
    "fads ;lkj adsf",
    "asdf;lkj asdf;lkj asdf;lkj",
]
FINGER_SENTENCES  = [
    "dad has a sad lad",
    "alfred asks for fudge",
    "ask, get, just, look",
    "jelly and jam make a skiff",
]


def get_lessons() -> List[Lesson]:
    """Bundled lessons — order is difficulty ascending."""
    return [
        Lesson.from_lines("Home Row", HOME_ROW, "a s d f j k l ; — left then right hand."),
        Lesson.from_lines("Left Hand Drill", LEFT_HAND, "a s d f g q w e r t z x c v b"),
        Lesson.from_lines("Right Hand Drill", RIGHT_HAND, "j k l ; ' n m , . / (enters the right home)"),
        Lesson.from_lines("Numbers", NUMBERS, "1 2 3 4 5 6 7 8 9 0"),
        Lesson.from_lines("Capitals and Punctuation", CAPS_AND_PUNCT,
                          "Shift for caps; quotes, commas, periods, semicolons."),
        Lesson.from_lines("Sentences", SENTENCES, "Pangrams and short sentences for rhythm."),
        Lesson.from_lines("Story", STORY, "Continuous prose — sustained typing."),
        Lesson.from_lines("Quotes", QUOTES, "Mixed punctuation and prose."),
        Lesson.from_lines("Initial Test", INITIAL_TEST,
                          "Used by tests to compute your baseline speed."),
    ]


# TT's keypad drills are three lines at a time and each line is ended with
# the '+' key on the numeric keypad, exactly like tallying a column of numbers.
KEYPAD_GROUPS = [
    ["456+", "456 456+", "456456+"],
    ["789+", "789 789+", "789789+"],
    ["123+", "123 123+", "123123+"],
    ["0.+", "0. 0.+", "0.0.+"],
    ["456 789+", "123 456+", "789 123+"],
    ["1+2+3+", "4+5+6+", "7+8+9+"],
    ["12+34+", "56+78+", "90+12+"],
    ["147+", "258+", "369+"],
    ["7-8+", "9*6+", "4/2+"],
    ["123-456+", "789*0+", "9/3+"],
    ["123 456 789+", "987 654 321+", "0.+"],
]


def get_keypad_drill_groups() -> List[List[str]]:
    """The three-line keypad drills used by Lessons/Tests → Keypad."""
    return [list(g) for g in KEYPAD_GROUPS]


def get_keypad_test_lines() -> List[str]:
    """Flattened keypad test lines (all groups, one drill each)."""
    return [line for group in KEYPAD_GROUPS for line in group]


def get_keypad_lessons() -> List[Lesson]:
    """Numeric-keypad drills, surfaced by Lessons → Keypad."""
    lines = get_keypad_test_lines()
    return [
        Lesson.from_lines(
            "Numeric Keypad",
            lines,
            "Practice the 0-9 numeric keypad layout and the +/-/*/operators. "
            "Each line ends with the '+' key.",
        ),
    ]


def get_fingering_lessons() -> List[Lesson]:
    """Fingering drills (left/right home row + alternating hands),
    surfaced by Lessons → Fingering."""
    return [
        Lesson.from_lines("Fingering — left home row",   FINGER_LEFT_HOME,
                          "a=pinky, s=ring, d=middle, f=index, g=index."),
        Lesson.from_lines("Fingering — right home row",  FINGER_RIGHT_HOME,
                          ";=pinky, l=ring, k=middle, j=index, m=index."),
        Lesson.from_lines("Fingering — column staggers", FINGER_STAGGER,
                          "alternating-hand sequences across the home row."),
        Lesson.from_lines("Fingering — alternating words", FINGER_SENTENCES,
                          "common short words that alternate left/right hand."),
    ]


TTENC_MAGIC = b"TTENC1\n"


def encrypt_tst(path: Path, password: str) -> bool:
    """Encrypt a .TST file in place (Instructor -> Encrypt).

    The original program warns that encryption is one-way.  We keep that
    property: the plaintext is replaced with an XOR-obfuscated stream and a
    magic header.  Only this clone's instructor mode can read it back.
    """
    if not path.exists() or not password:
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    data = text.encode("utf-8")
    body = bytes(b ^ ord(password[i % len(password)]) for i, b in enumerate(data))
    path.write_bytes(TTENC_MAGIC + body)
    return True


def decrypt_tst_bytes(raw: bytes, password: str) -> str:
    body = raw[len(TTENC_MAGIC):]
    data = bytes(b ^ ord(password[i % len(password)]) for i, b in enumerate(body))
    return data.decode("utf-8", errors="replace")


def read_tst(path: Path, password: str | None = None) -> List[str]:
    """Read a legacy `.TST` file, optionally decrypting an encrypted one.

    Lines are split on `@` and stripped.  The legacy format wrapped lessons
    in paragraphs separated by `@`; we keep each non-empty line as a drill.
    """
    if not path.exists():
        return []
    raw_bytes = path.read_bytes()
    if raw_bytes.startswith(TTENC_MAGIC):
        if not password:
            return []
        text = decrypt_tst_bytes(raw_bytes, password)
    else:
        text = raw_bytes.decode("utf-8", errors="replace")
    out: List[str] = []
    for raw in text.splitlines():
        for piece in raw.split("@"):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out
