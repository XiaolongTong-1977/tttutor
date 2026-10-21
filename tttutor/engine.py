"""Core typing engine: char-level state, accuracy, WPM, completion.

The engine is plain Python, no UI dependency. It holds the live state of one
typing drill and tells the UI what to render (per-character status flags and
aggregate stats). Driven by the UI event loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Sequence

MAX_WPM = 300.0


class CharStatus(Enum):
    PENDING = "pending"       # not yet typed
    CORRECT = "correct"       # matches target
    WRONG = "wrong"           # does not match target
    CURSOR = "cursor"         # next-to-type position marker (PENDING + cursor)


@dataclass
class DrillResult:
    """Per-drill result, captured when the drill finishes."""
    target: str
    typed: str
    elapsed_s: float
    correct_chars: int
    wrong_chars: int
    completed: bool          # user finished the line (reached end of target)
    per_key_errors: dict = field(default_factory=dict)  # char -> count of mistakes
    per_key_wpm: dict = field(default_factory=dict)      # char -> WPM for that key
    per_key_attempts: dict = field(default_factory=dict)
    per_key_correct: dict = field(default_factory=dict)
    aborted: bool = False

    @property
    def total_chars(self) -> int:
        return max(len(self.target), len(self.typed))

    @property
    def accuracy(self) -> float:
        if self.total_chars == 0:
            return 0.0
        return self.correct_chars / self.total_chars

    @property
    def wpm(self) -> float:
        """Words per minute, 5 chars per word convention."""
        if self.elapsed_s <= 0:
            return 0.0
        return min(MAX_WPM, (self.correct_chars / 5.0) / (self.elapsed_s / 60.0))

    @staticmethod
    def from_drill(drill: "TypingDrill") -> "DrillResult":
        """Build a result from a finished drill, populating per-key stats."""
        per_key: dict[str, int] = {}
        attempts: dict[str, int] = {}
        correct: dict[str, int] = {}
        for i, t in enumerate(drill.target):
            if i < len(drill.typed):
                attempts[t] = attempts.get(t, 0) + 1
                if drill.typed[i] == t:
                    correct[t] = correct.get(t, 0) + 1
                else:
                    per_key[t] = per_key.get(t, 0) + 1
        per_key_wpm: dict[str, float] = {}
        for ch, intervals in drill.key_intervals.items():
            # Ignore sub-20ms gaps: they come from pasted/automated input and
            # would otherwise produce absurd WPM figures.
            good = [d for d in intervals if d >= 0.02]
            if good:
                avg = sum(good) / len(good)
                per_key_wpm[ch] = min(MAX_WPM, (12.0 / avg) if avg > 0 else 0.0)
        return DrillResult(
            target=drill.target,
            typed=drill.typed,
            elapsed_s=drill.elapsed_s,
            correct_chars=drill.correct_count,
            wrong_chars=drill.wrong_count,
            completed=(
                drill.finished_monotonic is not None
                and len(drill.typed) >= len(drill.target)
                and drill.typed == drill.target
            ),
            per_key_errors=per_key,
            per_key_wpm=per_key_wpm,
            per_key_attempts=attempts,
            per_key_correct=correct,
        )


@dataclass
class TypingDrill:
    """A single line the user is typing right now."""
    target: str
    typed: str = ""
    started_monotonic: float | None = None
    finished_monotonic: float | None = None
    last_key_time: float | None = None
    key_intervals: dict = field(default_factory=dict)  # char -> [seconds]

    def start(self, monotonic_fn) -> None:
        if self.started_monotonic is None:
            self.started_monotonic = monotonic_fn()

    def push_char(self, ch: str, monotonic_fn) -> bool:
        """Record one typed char. Returns True if the drill just completed."""
        if self.finished_monotonic is not None:
            return False
        self.start(monotonic_fn)
        now = monotonic_fn()
        # Attribute the interval to the target character at the cursor
        # position, so per-key WPM lines up with per-key attempts/accuracy.
        pos = len(self.typed)
        key = self.target[pos] if pos < len(self.target) else ch
        # The first keystroke starts the per-key clock; only subsequent
        # keystrokes contribute an interval.
        if self.last_key_time is not None and now >= self.last_key_time:
            self.key_intervals.setdefault(key, []).append(now - self.last_key_time)
        self.last_key_time = now
        self.typed += ch
        completed = len(self.typed) >= len(self.target) and self.typed == self.target
        if completed:
            self.finished_monotonic = monotonic_fn()
        return completed

    def backspace(self) -> None:
        if self.finished_monotonic is not None:
            return
        self.typed = self.typed[:-1]

    def progress_chars(self) -> List[CharStatus]:
        """Char-by-char status flag list, length == len(target)."""
        statuses: list[CharStatus] = []
        for i, ch in enumerate(self.target):
            if i < len(self.typed):
                statuses.append(CharStatus.CORRECT if self.typed[i] == ch else CharStatus.WRONG)
            elif i == len(self.typed):
                statuses.append(CharStatus.CURSOR)
            else:
                statuses.append(CharStatus.PENDING)
        return statuses

    @property
    def wrong_count(self) -> int:
        return sum(
            1 for i, t in enumerate(self.target)
            if i < len(self.typed) and self.typed[i] != t
        )

    @property
    def correct_count(self) -> int:
        return sum(
            1 for i, t in enumerate(self.target)
            if i < len(self.typed) and self.typed[i] == t
        )

    @property
    def elapsed_s(self) -> float:
        end = self.finished_monotonic or self.started_monotonic
        if end is None or self.started_monotonic is None:
            return 0.0
        return max(0.0, end - self.started_monotonic)

    def result(self) -> DrillResult:
        return DrillResult.from_drill(self)


@dataclass
class LessonDrill:
    """One line in a lesson: text + optional completion key."""
    text: str


@dataclass
class Lesson:
    title: str
    drills: List[LessonDrill]
    description: str = ""

    @classmethod
    def from_lines(cls, title: str, lines: Sequence[str], description: str = "") -> "Lesson":
        return cls(
            title=title,
            drills=[LessonDrill(text=line) for line in lines if line.strip()],
            description=description,
        )


@dataclass
class LessonRun:
    lesson: Lesson
    results: List[DrillResult] = field(default_factory=list)
    current_index: int = 0

    def reset(self) -> None:
        self.results.clear()
        self.current_index = 0

    @property
    def current_drill(self) -> LessonDrill | None:
        if 0 <= self.current_index < len(self.lesson.drills):
            return self.lesson.drills[self.current_index]
        return None

    @property
    def done(self) -> bool:
        return self.current_index >= len(self.lesson.drills)

    def advance(self, result: DrillResult) -> None:
        self.results.append(result)
        self.current_index += 1


def lesson_summary(run: LessonRun) -> dict:
    """Aggregate stats over a lesson run."""
    if not run.results:
        return {"drills": 0, "wpm_avg": 0.0, "accuracy_avg": 0.0, "elapsed_s": 0.0}
    n = len(run.results)
    wpm_avg = sum(r.wpm for r in run.results) / n
    acc_avg = sum(r.accuracy for r in run.results) / n
    elapsed = sum(r.elapsed_s for r in run.results)
    completed = sum(1 for r in run.results if r.completed)
    return {
        "drills": n,
        "completed": completed,
        "wpm_avg": wpm_avg,
        "accuracy_avg": acc_avg,
        "elapsed_s": elapsed,
    }


def aggregate_per_key(results: List[DrillResult]) -> dict:
    """Merge per-key stats over several drills (for tests and reports)."""
    wpm_sum: dict[str, float] = {}
    wpm_n: dict[str, int] = {}
    attempts: dict[str, int] = {}
    correct: dict[str, int] = {}
    errors: dict[str, int] = {}
    for r in results:
        for ch, v in r.per_key_wpm.items():
            wpm_sum[ch] = wpm_sum.get(ch, 0.0) + v
            wpm_n[ch] = wpm_n.get(ch, 0) + 1
        for ch, v in r.per_key_attempts.items():
            attempts[ch] = attempts.get(ch, 0) + v
        for ch, v in r.per_key_correct.items():
            correct[ch] = correct.get(ch, 0) + v
        for ch, v in r.per_key_errors.items():
            errors[ch] = errors.get(ch, 0) + v
    return {
        "per_key_wpm": {ch: wpm_sum[ch] / wpm_n[ch] for ch in wpm_sum},
        "per_key_attempts": attempts,
        "per_key_correct": correct,
        "per_key_errors": errors,
    }
