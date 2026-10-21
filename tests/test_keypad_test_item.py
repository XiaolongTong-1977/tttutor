"""Tests for the new Keypad Test submenu item in Tests menu."""
import inspect
import unittest

from tttutor import ui


class KeypadTestItemTests(unittest.TestCase):
    def test_run_tests_adds_keypad(self):
        src = inspect.getsource(ui.App.run_tests)
        self.assertIn("go_keypad", src)
        self.assertIn("_keypad_test_session", src)
        self.assertIn('"Keypad"', src)

    def test_help_text_mentions_keypad(self):
        src = inspect.getsource(ui.App.run_tests)
        # Help text lists Keypad
        self.assertIn("Keypad", src)
        self.assertIn("numeric keypad", src)

    def test_keypad_routes_through_initial_test_intro(self):
        src = inspect.getsource(ui.App._keypad_test_session)
        self.assertIn("_initial_test_intro_screen", src)
        self.assertIn("_lesson_screen", src)
        self.assertIn("_keypad_summary_screen", src)
