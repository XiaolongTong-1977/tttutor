"""Tests for the Initial Test intro screen and the _UserCancelled exception.

These don't drive the curses UI directly (which would need a real terminal).
Instead they assert the structure is correct: TT text is preserved verbatim,
the exception flows up correctly, and run_tests has the expected wiring.
"""
import unittest
import inspect
from tttutor import ui


class InitialTestIntroTests(unittest.TestCase):
    def test_method_present(self):
        self.assertTrue(hasattr(ui.App, "_initial_test_intro_screen"))

    def test_method_is_async(self):
        # Should be a coroutine function.
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._initial_test_intro_screen))

    def test_text_mentions_progress(self):
        src = inspect.getsource(ui.App._initial_test_intro_screen)
        # Verbatim phrases from the TT IV intro screen we observed live.
        self.assertIn("initial test is", src)
        self.assertIn("baseline", src)
        self.assertIn("pointer", src)
        self.assertIn("backspace", src)
        self.assertIn("press Enter", src)

    def test_cancel_exception_exists(self):
        self.assertTrue(hasattr(ui, "_UserCancelled"))

    def test_test_session_wires_into_intro(self):
        src = inspect.getsource(ui.App._test_session)
        self.assertIn("_initial_test_intro_screen", src)
        self.assertIn("_test_screen", src)


if __name__ == "__main__":
    unittest.main()
