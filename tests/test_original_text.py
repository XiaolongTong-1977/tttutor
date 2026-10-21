"""Tests for the original TT.EXE token/macro text stream renderer."""
import random
import unittest

from tttutor import original_text as ot
from tttutor.invaders import LetterInvaders


class OriginalTextTests(unittest.TestCase):
    def test_all_51_streams_extracted(self):
        self.assertEqual(len(ot.STREAMS), 51)
        self.assertTrue(all(isinstance(s, list) for s in ot.STREAMS))

    def test_literals_are_present(self):
        self.assertIn("birthday", ot.render_stream(23, seed=1))
        self.assertIn("phone number", ot.render_stream(33, seed=1))
        self.assertIn("located at", ot.render_stream(35, seed=1))
        self.assertIn("cost", ot.render_stream(44, seed=1))

    def test_render_words_returns_game_sized_words(self):
        words = ot.render_words(2, seed=3, limit=50)
        self.assertTrue(words)
        self.assertTrue(all(1 <= len(w) <= 14 for w in words))

    def test_render_words_respects_learned_keys(self):
        words = ot.render_words(2, seed=3, allowed_keys="asdf", limit=200)
        for w in words:
            self.assertTrue(all(c in "asdf" for c in w), w)

    def test_suffix_is_not_applied_to_possessive(self):
        r = ot.TemplateRenderer(random.Random(1))
        r.parts = ["savor's"]
        r._suffix("ing")
        self.assertEqual(r.parts[-1], "savor's")

    def test_inflections_are_attached_to_the_word(self):
        r = ot.TemplateRenderer(random.Random(1))
        r.parts = ["talk"]
        r._suffix("ing")
        self.assertEqual(r.parts[-1], "talking")
        r.parts = ["talk"]
        r._suffix("past")
        self.assertEqual(r.parts[-1], "talked")
        r.parts = ["box"]
        r._suffix("plural")
        self.assertEqual(r.parts[-1], "boxes")

    def test_generate_drills_from_words(self):
        words = ["ada", "dee", "elsa", "ella", "dale", "sad", "lad", "add"]
        lines = ot.generate_drills_from_words(words, drills=10, seed=1)
        self.assertEqual(len(lines), 10)
        for line in lines:
            self.assertTrue(line)
            self.assertLessEqual(len(line), 68)
            self.assertGreaterEqual(len(set(line.split())), 2)

    def test_generate_drills_rejects_tiny_pool(self):
        self.assertEqual(ot.generate_drills_from_words(["a", "an"], drills=5), [])

    def test_practice_session_uses_original_generator(self):
        import inspect
        from tttutor import ui
        src = inspect.getsource(ui.App._practice_session)
        self.assertIn("_generated_practice_lesson", src)

    def test_word_falls_back_when_corpus_missing(self):
        # Simulate missing data files: _word must not raise on choice([]).
        saved = ot.WORDS_BY_STREAM, ot.ALL_WORDS
        try:
            ot.WORDS_BY_STREAM, ot.ALL_WORDS = {}, []
            r = ot.TemplateRenderer(random.Random(1))
            self.assertEqual(r._word(0), "a")
        finally:
            ot.WORDS_BY_STREAM, ot.ALL_WORDS = saved

    def test_generate_drills_cannot_hang(self):
        # Fewer unique words than 2x words_per_line must terminate.
        lines = ot.generate_drills_from_words(
            ["one", "two", "three"], drills=3, words_per_line=8, seed=0)
        self.assertLessEqual(len(lines), 3)

    def test_game_pool_combines_templates_and_corpus(self):
        g = LetterInvaders(level=1, rng=random.Random(2))
        self.assertGreaterEqual(len(g._pool), 100)
        self.assertTrue(all(1 <= len(w) <= 14 for w in g._pool))

    def test_practice_pool_respects_keys_with_templates(self):
        g = LetterInvaders(level=0, learned_keys="asdf",
                           rng=random.Random(2))
        allowed = set("asdf")
        for w in g._pool:
            self.assertTrue(all(c in allowed for c in w), w)


if __name__ == "__main__":
    unittest.main()
