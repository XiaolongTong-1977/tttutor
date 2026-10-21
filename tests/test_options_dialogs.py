"""Tests for the Options Menu (TT.EXE menu 4).

TT's Options menu has seven items: WPM / Time / Drills / Sound / Name /
Intro / Help.  These tests assert that every leaf is really implemented.
"""
import inspect
import unittest

from tttutor import ui


class OptionsDialogsTests(unittest.TestCase):
    def test_options_menu_has_all_seven_items(self):
        src = inspect.getsource(ui.App.run_options)
        for label in ("WPM", "Time", "Drills", "Sound", "Name", "Intro", "Help"):
            self.assertIn(f'"{label}"', src)

    def test_wpm_uses_speed_ranges(self):
        src = inspect.getsource(ui.App._option_wpm)
        self.assertIn("_choose_dialog", src)
        self.assertIn("Change speed goal", src)
        self.assertIn("SPEED_RANGES", src)
        self.assertIn("wpm_goal_index", src)

    def test_time_uses_practice_ranges(self):
        src = inspect.getsource(ui.App._option_time)
        self.assertIn("_choose_dialog", src)
        self.assertIn("Adjust practice goal", src)
        self.assertIn("PRACTICE_RANGES", src)

    def test_drills_uses_five_ten_fifteen_twenty(self):
        src = inspect.getsource(ui.App._option_drills)
        self.assertIn("DRILL_CHOICES", src)
        self.assertIn("drills_per_lesson", src)

    def test_sound_and_name_and_intro(self):
        self.assertIn("_choose_dialog", inspect.getsource(ui.App._option_sound))
        self.assertIn("read_line", inspect.getsource(ui.App._option_name))
        self.assertIn("_intro_pages", inspect.getsource(ui.App._option_intro))

    def test_settings_are_persisted(self):
        src = inspect.getsource(ui.App._save_settings)
        self.assertIn("settings_mod.save", src)
        self.assertIn("learned_keys", src)
        self.assertIn("drills_per_lesson", src)


if __name__ == "__main__":
    unittest.main()
