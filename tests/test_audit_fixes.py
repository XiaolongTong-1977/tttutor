"""Regression tests for the audit fixes.

Each test corresponds to a concrete bug found during the post-clone audit.
"""
from __future__ import annotations

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from tttutor import history, settings, ui
from tttutor.content import encrypt_tst, read_tst
from tttutor.engine import TypingDrill
from tttutor.history import HistoryRecord, append, delete_user, list_users, summary
from tttutor.invaders import HighScores


class AuditTests(unittest.TestCase):
    def test_summary_keeps_newest_records(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            for wpm in (10, 20, 30):
                append(HistoryRecord.now("drill", "x", {"wpm": wpm, "accuracy": 1.0}), p)
            s = summary(p, max_records=2)
            self.assertAlmostEqual(s["wpm_avg"], 25.0)

    def test_first_key_does_not_include_preread_pause(self):
        d = TypingDrill(target="abc")
        t = [0.0]
        d.start(lambda: t[0])
        t[0] = 10.0
        d.push_char("a", lambda: t[0])
        t[0] = 10.2
        d.push_char("b", lambda: t[0])
        t[0] = 10.5
        d.push_char("c", lambda: t[0])
        r = d.result()
        # 'a' started the clock; no interval is attributed to it.
        self.assertNotIn("a", r.per_key_wpm)
        self.assertAlmostEqual(r.per_key_wpm["b"], 60.0)
        self.assertAlmostEqual(r.per_key_wpm["c"], 40.0)

    def test_read_key_honours_timeout(self):
        src = inspect.getsource(ui.App.read_key)
        self.assertIn("time.monotonic()", src)
        self.assertIn("return -1", src)

    def test_test_screen_suppresses_duplicate_lesson_summary(self):
        src = inspect.getsource(ui.App._test_screen)
        self.assertIn("show_summary=False", src)

    def test_cursor_helper_is_fail_safe(self):
        self.assertTrue(hasattr(ui, "_set_cursor"))
        src = inspect.getsource(ui._set_cursor)
        self.assertIn("curses.curs_set(visible)", src)
        self.assertIn("except curses.error", src)
        # Guard against the accidental self-recursive replacement.
        self.assertNotIn("_set_cursor(visible)", src)

    def test_disk_session_searches_tst_dir(self):
        src = inspect.getsource(ui.App._disk_test_session)
        self.assertIn("self.tst_dir", src)

    def test_summary_user_filter_includes_legacy_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            append(HistoryRecord.now("drill", "legacy", {"wpm": 10, "accuracy": 1.0},
                                     user=""), p)
            append(HistoryRecord.now("drill", "other", {"wpm": 100, "accuracy": 1.0},
                                     user="B"), p)
            s = summary(p, user="A")
            self.assertEqual(s["drills"], 1)
            self.assertAlmostEqual(s["wpm_avg"], 10.0)

    def test_alert_waits_for_a_key(self):
        src = inspect.getsource(ui.App._alert)
        self.assertIn("await self.read_key()", src)

    def test_ctrl_c_is_handled_in_menus(self):
        for name in ("horizontal_menu", "_pick_from_list", "_choose_dialog"):
            src = inspect.getsource(getattr(ui.App, name))
            self.assertIn("3", src, f"{name} does not handle Ctrl-C")

    def test_keypad_session_uses_one_lesson_record(self):
        src = inspect.getsource(ui.App._keypad_session)
        self.assertEqual(src.count("_save_lesson_summary"), 1)
        self.assertIn("show_summary=False", src)

    def test_practice_test_uses_extracted_corpus(self):
        src = inspect.getsource(ui.App._practice_test_lines)
        self.assertIn("ORIGINAL_WORDS", src)

    def test_game_over_menu_matches_original(self):
        src = inspect.getsource(ui.App._game_over_menu)
        for label in ("Play another game", "Practice Lesson",
                      "Return to Main Menu"):
            self.assertIn(label, src)

    def test_game_over_records_scores(self):
        src = inspect.getsource(ui.App._run_one_invaders_game)
        self.assertIn("game_record", src)
        self.assertIn("hs.add", src)
        self.assertIn("letter_invaders_practice", src)
        self.assertIn("letter_invaders_full", src)

    def test_round_summary_shows_tt_fields(self):
        src = inspect.getsource(ui.App._round_summary_screen)
        for field in ("Hits:", "Misses:", "Accuracy:", "Accuracy Bonus:"):
            self.assertIn(field, src)

    def test_history_delete_user_and_list_users(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.jsonl"
            append(HistoryRecord.now("drill", "x", {"wpm": 1}, user="A"), p)
            append(HistoryRecord.now("drill", "x", {"wpm": 2}, user="B"), p)
            self.assertEqual(list_users(p), ["A", "B"])
            removed = delete_user("A", p)
            self.assertEqual(removed, 1)
            self.assertEqual(list_users(p), ["B"])

    def test_high_scores_delete(self):
        with tempfile.TemporaryDirectory() as d:
            hs = HighScores(Path(d) / "fzvf.json")
            hs.add(0, "A", 10, 7)
            hs.add(1, "A", 20, 63)
            self.assertEqual(hs.delete("A"), 2)
            self.assertEqual(hs.top(0), [])
            self.assertEqual(hs.top(1), [])

    def test_tst_encryption_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "X.TST"
            p.write_text("hello@world\n", encoding="utf-8")
            self.assertEqual(read_tst(p), ["hello", "world"])
            self.assertTrue(encrypt_tst(p, "KRIYA"))
            self.assertEqual(read_tst(p), [])
            self.assertEqual(read_tst(p, "KRIYA"), ["hello", "world"])

    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            data = settings.load(p)
            data["drills_per_lesson"] = 20
            data["goals"]["wpm_target"] = 55
            settings.save(data, p)
            again = settings.load(p)
            self.assertEqual(again["drills_per_lesson"], 20)
            self.assertEqual(again["goals"]["wpm_target"], 55)

    def test_corpus_json_is_valid_and_complete(self):
        p = Path(__file__).resolve().parent.parent / "tttutor" / "data" / "tt_word_corpus.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertGreater(len(data["entries"]), 3900)
        self.assertEqual(data["streams"], 46)
        self.assertEqual(data["buckets"], 23)


if __name__ == "__main__":
    unittest.main()
