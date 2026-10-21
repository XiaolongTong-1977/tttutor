"""Tests for the Lessons sub-menu structure (mirrors TT's Lessons Menu)."""
import inspect
import unittest

from tttutor import ui


class LessonsSubMenuTests(unittest.TestCase):
    def test_run_lessons_present_and_async(self):
        self.assertTrue(hasattr(ui.App, "run_lessons"))
        self.assertTrue(inspect.iscoroutinefunction(ui.App.run_lessons))

    def test_run_lessons_contains_all_four_submenu_items(self):
        src = inspect.getsource(ui.App.run_lessons)
        # All four sub-menu items from TT's Lessons Menu must be present.
        for label in ("Practice", "Fingering", "Keypad", "Help"):
            self.assertIn(label, src)

    def test_each_leaf_has_a_real_handler(self):
        for name in ("_practice_session", "_fingering_session", "_keypad_session"):
            self.assertTrue(hasattr(ui.App, name), f"missing {name}")
            self.assertTrue(inspect.iscoroutinefunction(getattr(ui.App, name)))

    def test_practice_action_drills_through_lessons(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("go_practice", src)
        self.assertIn("_practice_session", src)
        drill_src = inspect.getsource(ui.App._practice_session)
        self.assertIn("_lesson_screen", drill_src)

    def test_help_action_shows_lessons_specific_help(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("go_help", src)
        self.assertIn("features of the Lessons Menu", src)


if __name__ == "__main__":
    unittest.main()
