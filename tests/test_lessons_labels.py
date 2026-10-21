"""Regression tests for stale "(future)" labels in the Lessons submenu."""
import inspect
import unittest

from tttutor import ui


class LessonsLabelsTests(unittest.TestCase):
    def test_no_future_label_in_lessons_submenu(self):
        src = inspect.getsource(ui.App.run_lessons)
        # Items block must not contain the word "future" near the
        # Fingering / Keypad entries
        items_block = src.split("items = [", 1)[1].split("]", 1)[0]
        self.assertNotIn("future", items_block.lower())
        self.assertNotIn("Fingering (future)", items_block)
        self.assertNotIn("Keypad (future)", items_block)

    def test_fingering_label_is_clean(self):
        src = inspect.getsource(ui.App.run_lessons)
        items_block = src.split("items = [", 1)[1].split("]", 1)[0]
        self.assertIn('"Fingering"', items_block)
        self.assertIn('"Keypad"', items_block)

    def test_help_text_no_future_for_lessons(self):
        src = inspect.getsource(ui.App.run_lessons)
        # The Lessons help text describes the submenu; it should not label
        # any entry as future / placeholder.
        go_help_chunk = src.split('async def go_help()', 1)[1]
        # Just ensure no "future" sneaks into the help text
        self.assertNotIn("future", go_help_chunk.lower())
