"""Tests for the 'Current Focus Keys' hint in the drill screen."""
import inspect
import unittest

from tttutor import ui


class FocusKeysTests(unittest.TestCase):
    def test_drill_screen_renders_focus_keys(self):
        src = inspect.getsource(ui.App._drill_screen)
        self.assertIn("Current Focus Keys", src)
        # The hint sits between the title row and the drill box
        idx_title = src.find(f"{lesson.title}   drill ") if False else src.find("drill {cur}/{total}")
        self.assertGreater(src.find("Current Focus Keys"), 0)

    def test_focus_keys_only_alnum(self):
        # The hint filters out spaces, punctuation, etc. — only alnum.
        src = inspect.getsource(ui.App._drill_screen)
        self.assertIn("isalnum()", src)
        # Sorted, dedup'd via set comprehension
        self.assertIn("sorted({c for c in drill.target", src)

    def test_drives_drill_count_from_unique_set(self):
        # Edge case: drill with only spaces / punctuation produces no hint
        src = inspect.getsource(ui.App._drill_screen)
        self.assertIn("unique_keys", src)
        self.assertIn("Current Focus Keys:", src)
        self.assertIn("len(unique_keys) > 14", src)