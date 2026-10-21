"""Tests for the Beginner 'Where would you like to begin..' screen."""
import inspect
import unittest

from tttutor import ui


class BeginnerScreenTests(unittest.TestCase):
    def test_method_present(self):
        self.assertTrue(hasattr(ui.App, "_beginner_screen"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._beginner_screen))

    def test_uses_choose_dialog(self):
        src = inspect.getsource(ui.App._beginner_screen)
        self.assertIn("_choose_dialog", src)
        self.assertIn("Where would you like to begin..", src)

    def test_offers_three_tt_actions(self):
        src = inspect.getsource(ui.App._beginner_screen)
        for action in ("Practice Lesson", "Practice Test", "Main Menu"):
            self.assertIn(action, src)

    def test_main_flow_routes_through_beginner(self):
        src = inspect.getsource(ui.App._main_unprotected)
        # Order in main: ... date → goals → skill → beginner → menu
        i_date     = src.find("_date_confirm_screen")
        i_skill    = src.find("_skill_level_screen")
        i_begin    = src.find("_beginner_screen")
        self.assertGreater(i_date, 0)
        self.assertGreater(i_skill, 0)
        self.assertGreater(i_begin, 0)
        self.assertLess(i_date, i_skill)
        self.assertLess(i_skill, i_begin)

    def test_beginner_seen_flag_persists(self):
        src = inspect.getsource(ui.App._main_unprotected)
        self.assertIn("_beginner_seen", src)
        self.assertIn("run_lessons", src)
        self.assertIn("run_tests", src)


if __name__ == "__main__":
    unittest.main()
