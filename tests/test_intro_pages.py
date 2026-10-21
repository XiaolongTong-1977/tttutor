"""Tests for the multi-page Introduction and Welcome dialog.
"""
import inspect
import unittest

from tttutor import ui


class IntroPagesTests(unittest.TestCase):
    def test_welcome_screen_method_exists(self):
        self.assertTrue(hasattr(ui.App, "_welcome_screen"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._welcome_screen))

    def test_intro_pages_method_exists(self):
        self.assertTrue(hasattr(ui.App, "_intro_pages"))
        self.assertTrue(inspect.iscoroutinefunction(ui.App._intro_pages))

    def test_choose_dialog_helper(self):
        self.assertTrue(hasattr(ui.App, "_choose_dialog"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._choose_dialog))

    def test_intro_pages_have_verbatim_quotes(self):
        src = inspect.getsource(ui.App._intro_pages)
        # Verify line-level verbatim phrases from TT.HLP intro.
        for phrase in (
            "Typing Tutor IV keyboard instruction program!",
            "and available practice time, to help you gain",
            "pressing the",
            "Esc (Escape) key will",
            "Lessons, Tests, Reports, Options, Game, Help,",
            "Letter Invaders allows you to play with just the",
        ):
            self.assertIn(phrase, src)

    def test_main_calls_welcome_then_intro_then_registration(self):
        src = inspect.getsource(ui.App._main_unprotected)
        # Welcome first, then intro, then registration — that order.
        i_welcome = src.find("_welcome_screen")
        i_intro   = src.find("_intro_pages")
        i_reg     = src.find("_registration_screen")
        self.assertGreater(i_welcome, 0, "no _welcome_screen call")
        self.assertGreater(i_intro, 0,   "no _intro_pages call")
        self.assertGreater(i_reg, 0,     "no _registration_screen call")
        self.assertLess(i_welcome, i_intro)
        self.assertLess(i_intro, i_reg)

    def test_welcome_screen_only_runs_once(self):
        # _welcome_seen is checked so a returning user doesn't re-see it.
        src = inspect.getsource(ui.App._main_unprotected)
        self.assertIn("_welcome_seen", src)
        self.assertIn("_intro_seen", src)


if __name__ == "__main__":
    unittest.main()
