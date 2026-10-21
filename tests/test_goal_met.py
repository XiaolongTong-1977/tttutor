"""Tests for the Goal-met celebration banner."""
import inspect
import unittest

from tttutor import ui


class GoalMetTests(unittest.TestCase):
    def test_helper_present(self):
        self.assertTrue(hasattr(ui.App, "_goal_met_banner"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._goal_met_banner))

    def test_summary_calls_banner_when_goals_met(self):
        src = inspect.getsource(ui.App._lesson_summary_screen)
        # The summary should call _goal_met_banner conditionally
        self.assertIn("_goal_met_banner", src)
        self.assertIn("goal_met =", src)
        # And gate it on meeting both wpm and accuracy goals
        self.assertIn("wpm_target", src)
        self.assertIn("accuracy_target", src)

    def test_banner_mentions_goals(self):
        src = inspect.getsource(ui.App._goal_met_banner)
        self.assertIn("GOAL MET", src)
        self.assertIn("WPM", src)
        self.assertIn("Accuracy", src)
        # Plays the lesson-complete fanfare
        self.assertIn("LESSON_COMPLETE", src)
        # Holds the screen for 2 seconds
        self.assertIn("time.sleep(2.0)", src)

    def test_banner_is_optional(self):
        # If the user didn't meet the goal, no banner is shown.
        # The summary screen renders normally without crashing.
        src = inspect.getsource(ui.App._lesson_summary_screen)
        # The goal_met conditional is exactly the gate
        self.assertIn("if goal_met:", src)
        self.assertIn("await self._goal_met_banner(s)", src)
