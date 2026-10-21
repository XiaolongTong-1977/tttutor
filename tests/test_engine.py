"""Unit tests for the typing engine (no UI)."""
import unittest
from tttutor.engine import TypingDrill, CharStatus, Lesson, LessonRun, lesson_summary, DrillResult
from tttutor.history import HistoryRecord, append, load_all


class FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms / 1000.0


class DrillTests(unittest.TestCase):
    def test_perfect_completion(self):
        fc = FakeClock(0.0)
        d = TypingDrill(target="the quick brown fox")
        for ch in "the quick brown fox":
            d.push_char(ch, fc)
            fc.advance(100)
        res = d.result()
        self.assertTrue(res.completed)
        self.assertEqual(res.correct_chars, len(d.target))
        self.assertEqual(res.wrong_chars, 0)
        self.assertEqual(res.accuracy, 1.0)
        self.assertGreater(res.wpm, 0)

    def test_wrong_chars_recorded(self):
        fc = FakeClock(0.0)
        d = TypingDrill(target="abc")
        for ch in "axz":
            d.push_char(ch, fc)
            fc.advance(500)
        res = d.result()
        self.assertFalse(res.completed)
        self.assertEqual(res.correct_chars, 1)
        self.assertEqual(res.wrong_chars, 2)
        self.assertAlmostEqual(res.accuracy, 1 / 3, places=4)

    def test_backspace(self):
        fc = FakeClock(0.0)
        d = TypingDrill(target="hi")
        d.push_char("h", fc)
        d.push_char("x", fc)
        d.backspace()
        d.push_char("i", fc)
        self.assertEqual(d.typed, "hi")

    def test_progress_marks_cursor(self):
        fc = FakeClock()
        d = TypingDrill(target="abc")
        d.push_char("a", fc)
        self.assertEqual(
            d.progress_chars(),
            [CharStatus.CORRECT, CharStatus.CURSOR, CharStatus.PENDING],
        )

    def test_wpm_uses_5_char_convention(self):
        fc = FakeClock(0.0)
        d = TypingDrill(target="hello")
        # 5 chars * 200ms = 1.0s. 5-chars-per-word → 60 / 1 = 60 wpm.
        for ch in "hello":
            d.push_char(ch, fc)
            fc.advance(200)
        res = d.result()
        # 5 chars in 1.0s = 60 wpm exactly (5-char-per-word convention).
        self.assertGreater(res.wpm, 50)
        self.assertLess(res.wpm, 80)


class LessonSummaryTests(unittest.TestCase):
    def test_aggregates(self):
        run = LessonRun(lesson=Lesson(title="t", drills=[]))
        for _ in range(3):
            run.advance(DrillResult(target="ab", typed="ab", elapsed_s=2.0,
                                    correct_chars=2, wrong_chars=0, completed=True))
        s = lesson_summary(run)
        self.assertEqual(s["drills"], 3)
        self.assertEqual(s["accuracy_avg"], 1.0)
        self.assertGreater(s["wpm_avg"], 0)

    def test_empty_lesson(self):
        run = LessonRun(lesson=Lesson(title="t", drills=[]))
        s = lesson_summary(run)
        self.assertEqual(s["drills"], 0)
        self.assertEqual(s["wpm_avg"], 0.0)


class HistoryTests(unittest.TestCase):
    def test_roundtrip(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            append(HistoryRecord.now("drill", "lesson1",
                                     {"wpm": 30, "accuracy": 0.9, "elapsed_s": 5.0}),
                   path=p)
            recs = load_all(p)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0].kind, "drill")
            self.assertEqual(recs[0].label, "lesson1")
            self.assertEqual(recs[0].detail["wpm"], 30)


class ContentTests(unittest.TestCase):
    def test_built_in_lessons_present(self):
        from tttutor.content import get_lessons
        ls = get_lessons()
        self.assertGreater(len(ls), 0)
        self.assertTrue(all(l.drills for l in ls))


if __name__ == "__main__":
    unittest.main()
