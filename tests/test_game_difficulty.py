"""Tests for the Letter Invaders level / player pickers.

These mirror TT.EXE's Game -> Play flow: choose a level of play
(Practice Keys / Full Keyboard), then the number of players (One / Two),
then an optional second-player name.
"""
import inspect
import unittest

from tttutor import ui


class GameDifficultyTests(unittest.TestCase):
    def test_play_chooses_level_first(self):
        src = inspect.getsource(ui.App._play_letter_invaders)
        self.assertIn("Choose a level of play", src)
        self.assertIn("Practice Keys", src)
        self.assertIn("Full Keyboard", src)

    def test_play_chooses_number_of_players(self):
        src = inspect.getsource(ui.App._play_letter_invaders)
        self.assertIn("Choose the number of players", src)
        self.assertIn('("One"', src)
        self.assertIn('("Two"', src)

    def test_play_constructs_faithful_engine(self):
        src = inspect.getsource(ui.App._play_letter_invaders)
        self.assertIn("LetterInvaders(", src)
        self.assertIn("learned_keys=self._learned_keys()", src)
        self.assertIn("players=players", src)

    def test_second_player_name_prompt(self):
        src = inspect.getsource(ui.App._play_letter_invaders)
        self.assertIn("Player #2: Please type your name", src)

    def test_cancel_returns_to_menu(self):
        src = inspect.getsource(ui.App._play_letter_invaders)
        self.assertIn("if level_choice is None", src)
        self.assertIn("return", src)


if __name__ == "__main__":
    unittest.main()
