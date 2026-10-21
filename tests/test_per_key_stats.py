"""Tests for per-character error statistics.
"""
import unittest
from pathlib import Path
import tempfile

from tttutor.engine import DrillResult
from tttutor.history import (
    HistoryRecord, append, load_all, summary, per_key_stats,
)


class PerKeyTests(unittest.TestCase):
    def test_drresult_from_drill_populates_per_key_errors(self):
        from tttutor.engine import TypingDrill
        d = TypingDrill(target="the cat")
        for c in "the cxt":  # 'x' is wrong, should be 'a'
            d.push_char(c, lambda: 0)
        r = d.result()
        # 'a' wrong → 1 error attributed to 'a'
        self.assertEqual(r.per_key_errors, {"a": 1})
        # 'x' was typed (no key for 'x' since target doesn't have it) so it's
        # only attributed to the missed 'a'.

    def test_per_key_aggregates_across_drills(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.jsonl"
            # Simulate 3 drills with various errors.
            for target, typed in [
                ("the cat", "the cxt"),  # error at target char 'a'
                ("dog",     "dig"),     # error at target char 'o'
                ("apple",   "apply"),   # error at target char 'e'
            ]:
                from tttutor.engine import TypingDrill
                d = TypingDrill(target=target)
                for c in typed:
                    d.push_char(c, lambda: 0)
                r = d.result()
                append(HistoryRecord.now(
                    "drill", "test", {
                        "wpm": 0, "accuracy": r.accuracy,
                        "elapsed_s": 0, "wrong": r.wrong_chars,
                        "typed": r.typed[:60],
                        "target": r.target,
                        "per_key_errors": r.per_key_errors,
                    }), path=p)
            stats = per_key_stats(p)
            # 'a' has 1 error and 2 attempts (the cat + apple)
            # 'e' has 1 error and 1 attempt (apple)
            # 'o' has 1 error and 1 attempt (dog)
            self.assertEqual(stats[0], ("a", 1, 2))
            # 3-way tie for the next two; verify they're a/e/o in some order
            tail = sorted([s[0] for s in stats[1:3]])
            self.assertEqual(tail, ["e", "o"])

    def test_per_key_stats_empty_history(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "empty.jsonl"
            self.assertEqual(per_key_stats(p), [])

    def test_summary_includes_per_key_errors(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "h.jsonl"
            from tttutor.engine import TypingDrill
            # target "abcdef" — typed "abcdez" — position 5 (target 'f') wrong
            d = TypingDrill(target="abcdef")
            for c in "abcdez":
                d.push_char(c, lambda: 0)
            r = d.result()
            append(HistoryRecord.now(
                "drill", "test", {
                    "wpm": 0, "accuracy": r.accuracy,
                    "elapsed_s": 0, "wrong": r.wrong_chars,
                    "typed": r.typed[:60],
                    "target": r.target,
                    "per_key_errors": r.per_key_errors,
                }), path=p)
            s = summary(p)
            self.assertIn("per_key_errors", s)
            # Top error should be 'f' (target char) with 1 error
            self.assertEqual(s["per_key_errors"][0][0], "f")
            self.assertEqual(s["per_key_errors"][0][1], 1)


if __name__ == "__main__":
    unittest.main()
