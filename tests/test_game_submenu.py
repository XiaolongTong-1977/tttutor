"""Tests for the Game sub-menu (Play / Help)."""
import inspect
import unittest

from tttutor import ui


class GameSubMenuTests(unittest.TestCase):
    def test_run_game_uses_submenu(self):
        src = inspect.getsource(ui.App.run_game)
        # Should NOT be a one-shot letter invaders call anymore; should
        # present a submenu with Play + Help.
        self.assertNotIn('"Game (Letter Invaders)"', src)
        # Should mention both "Play" and "Help" submenu items
        self.assertIn('"Play"', src)
        self.assertIn('"Help"', src)

    def test_play_routes_to_letter_invaders(self):
        src = inspect.getsource(ui.App.run_game)
        # go_play → _play_letter_invaders
        self.assertIn("go_play", src)
        self.assertIn("_play_letter_invaders", src)

    def test_help_text_mentions_letter_invaders(self):
        src = inspect.getsource(ui.App.run_game)
        # Help text describes the game
        self.assertIn("Letter Invaders", src)
        self.assertIn("typing instruction game", src)

    def test_history_record_still_works(self):
        src = inspect.getsource(ui.App._run_one_invaders_game)
        # The full game persists one record per player.
        self.assertIn("game_record", src)
        self.assertIn("letter_invaders_practice", src)
        self.assertIn("letter_invaders_full", src)

    def test_scores_item_exists(self):
        src = inspect.getsource(ui.App.run_game)
        self.assertIn('"Scores"', src)
        self.assertIn("_game_scores_screen", src)
