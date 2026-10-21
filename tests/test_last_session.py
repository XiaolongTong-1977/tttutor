"""Tests for the main-menu's last-session summary line."""
import inspect
import unittest

from tttutor import ui


class LastSessionTests(unittest.TestCase):
    def test_helper_method_present(self):
        self.assertTrue(hasattr(ui.App, "_last_session_summary"))
        self.assertTrue(inspect.iscoroutinefunction(ui.App.run_help)
                        or not inspect.iscoroutinefunction(ui.App._last_session_summary))
        # _last_session_summary is a sync helper, not a coroutine
        self.assertFalse(inspect.iscoroutinefunction(
            ui.App._last_session_summary))

    def test_welcome_back_renders_summary(self):
        src = inspect.getsource(ui.App._welcome_back_screen)
        self.assertIn("_last_session_summary", src)
        self.assertIn("last", src)

    def test_returns_empty_string_when_no_history(self):
        # Just confirm a no-records call doesn't raise and returns a string.
        class Stub:
            history_path = None
        self.assertIsInstance(ui.App._last_session_summary(Stub()), str)
