"""Tests for the per-drill breakdown in the lesson summary screen."""
import inspect
import unittest

from tttutor import ui


class LessonSummaryBreakdownTests(unittest.TestCase):
    def test_method_renders_per_drill_breakdown(self):
        src = inspect.getsource(ui.App._lesson_summary_screen)
        self.assertIn("Per-drill breakdown", src)
        self.assertIn("text_preview", src)
        self.assertIn("chart", src)
        # Aggregates are still rendered
        self.assertIn("Average WPM", src)
        self.assertIn("Average accuracy", src)

    def test_uses_per_drill_colour_coding(self):
        src = inspect.getsource(ui.App._lesson_summary_screen)
        # Below 0.85 accuracy is red (PAIR_BAD), 0.85-0.95 prompt, ≥0.95 green
        self.assertIn("PAIR_OK", src)
        self.assertIn("PAIR_PROMPT", src)
        self.assertIn("PAIR_BAD", src)
        self.assertIn("r.accuracy >= 0.95", src)
        self.assertIn("r.accuracy >= 0.85", src)

    def test_handles_long_drill_names(self):
        src = inspect.getsource(ui.App._lesson_summary_screen)
        # Truncate text with ellipsis for drill rows wider than 30 chars
        self.assertIn("…", src)
        self.assertIn("text_preview = r.target[:30]", src)
