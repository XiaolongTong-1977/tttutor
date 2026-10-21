"""Tests for the boot interview: Date confirm / Goals / Skill level."""
import inspect
import unittest

from tttutor import ui


class BootInterviewTests(unittest.TestCase):
    def test_date_confirm_screen(self):
        self.assertTrue(hasattr(ui.App, "_date_confirm_screen"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._date_confirm_screen))

    def test_goals_question_screen(self):
        self.assertTrue(hasattr(ui.App, "_goals_question_screen"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._goals_question_screen))

    def test_skill_level_screen(self):
        self.assertTrue(hasattr(ui.App, "_skill_level_screen"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._skill_level_screen))

    def test_main_runs_all_three_after_registration(self):
        src = inspect.getsource(ui.App._main_unprotected)
        # Order: intro -> registration -> date -> goals -> skill
        i_reg    = src.find("_registration_screen")
        i_date   = src.find("_date_confirm_screen")
        i_goals  = src.find("_goals_question_screen")
        i_skill  = src.find("_skill_level_screen")
        self.assertGreater(i_reg, 0)
        self.assertGreater(i_date, 0)
        self.assertGreater(i_goals, 0)
        self.assertGreater(i_skill, 0)
        self.assertLess(i_reg, i_date)
        self.assertLess(i_date, i_goals)
        self.assertLess(i_goals, i_skill)

    def test_interview_runs_only_once(self):
        src = inspect.getsource(ui.App._main_unprotected)
        self.assertIn("_interview_done", src)

    def test_skill_choices_match_tt_three_options(self):
        src = inspect.getsource(ui.App._skill_level_screen)
        # TT IV offered exactly three skill options.
        for opt in ("Beginner", "Two finger typist", "Touch typist"):
            self.assertIn(opt, src)

    def test_goals_choices_are_speed_and_practice_ranges(self):
        src = inspect.getsource(ui.App._goals_question_screen)
        # TT IV asks for a speed range and then a weekly practice range.
        self.assertIn("Speed Goal", src)
        self.assertIn("Practice Goal", src)
        self.assertIn("SPEED_RANGES", src)
        self.assertIn("PRACTICE_RANGES", src)
        self.assertIn("wpm_goal_index", src)
        self.assertIn("practice_goal_index", src)


if __name__ == "__main__":
    unittest.main()
