"""Tests for the numeric keypad drill surface.
Verifies content + the go_keypad wiring + that the placeholder is gone.
"""
import inspect
import unittest

from tttutor import ui
from tttutor.content import get_keypad_lessons


class KeypadLessonTests(unittest.TestCase):
    def test_get_keypad_lessons_exists(self):
        ls = get_keypad_lessons()
        self.assertGreaterEqual(len(ls), 1)
        self.assertEqual(ls[0].title, "Numeric Keypad")

    def test_keypad_drills_use_numeric_digit_characters(self):
        ls = get_keypad_lessons()
        lessons_text = " ".join(d.text for d in ls[0].drills)
        for ch in "0123456789":
            self.assertIn(ch, lessons_text,
                          f"keypad drills should exercise digit {ch}")
        # operators
        for op in ("+", "-", "*", "/", "."):
            self.assertIn(op, lessons_text,
                          f"keypad drills should exercise {op}")

    def test_go_keypad_no_longer_future_release(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("go_keypad", src)
        self.assertIn("_keypad_session", src)
        kp = inspect.getsource(ui.App._keypad_session)
        self.assertIn("get_keypad_drill_groups", kp)
        self.assertIn("_lesson_screen", kp)
        self.assertIn("_keypad_summary_screen", kp)
        self.assertNotIn("reserved for a future release", kp)

    def test_help_text_reflects_keypad_implemented(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("numeric keypad", src)
        self.assertIn("three lines", src)


if __name__ == "__main__":
    unittest.main()
