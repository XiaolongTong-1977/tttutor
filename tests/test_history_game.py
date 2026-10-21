"""Tests for the new game-record path in history.py."""
import unittest
from pathlib import Path
import tempfile

from tttutor.history import (
    HistoryRecord, append, load_all, summary,
    game_record, game_high_score,
)


class GameRecordTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.path = Path(self.td.name) / "h.jsonl"

    def tearDown(self):
        self.td.cleanup()

    def test_first_run_is_a_high_score(self):
        rec, is_hi = game_record(score=10, label="letter_invaders",
                                 detail={"missed": 0, "target": 5},
                                 path=self.path)
        self.assertTrue(is_hi)
        self.assertEqual(game_high_score("letter_invaders", self.path), 10)

    def test_second_run_smaller_not_high(self):
        game_record(score=15, label="letter_invaders", detail={}, path=self.path)
        _, is_hi = game_record(score=8, label="letter_invaders", detail={}, path=self.path)
        self.assertFalse(is_hi)
        self.assertEqual(game_high_score("letter_invaders", self.path), 15)

    def test_second_run_bigger_is_high(self):
        game_record(score=10, label="letter_invaders", detail={}, path=self.path)
        _, is_hi = game_record(score=42, label="letter_invaders", detail={}, path=self.path)
        self.assertTrue(is_hi)
        self.assertEqual(game_high_score("letter_invaders", self.path), 42)

    def test_unknown_label_returns_zero(self):
        self.assertEqual(game_high_score("never_played", self.path), 0)

    def test_summary_includes_game_high_scores(self):
        game_record(score=20, label="letter_invaders",
                    detail={"missed": 1, "target": 4}, path=self.path)
        s = summary(self.path)
        self.assertIn("game_high_scores", s)
        self.assertEqual(s["game_high_scores"].get("letter_invaders"), 20)
        self.assertEqual(s["per_kind"]["game"], 1)

    def test_load_all_roundtrip(self):
        rec, _ = game_record(score=12, label="foo", detail={"x": 1}, path=self.path)
        recs = load_all(self.path)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].kind, "game")
        self.assertEqual(recs[0].label, "foo")
        self.assertEqual(recs[0].detail["score"], 12)


if __name__ == "__main__":
    unittest.main()
