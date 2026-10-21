"""Behavioural tests for the faithful Letter Invaders engine.

These assertions come from the decompiled TT.EXE routines:
* ``FUN_1000_a22a`` — word scoring: 5*len*(len+1), doubled for specials.
* ``FUN_1000_9ecc`` — a miss costs 10 points.
* ``FUN_1000_a541`` — shield damage and one word per physical key.
* ``FUN_1000_9bec`` — accuracy bonus above 90%.
"""
import random
import tempfile
import unittest
from pathlib import Path

from tttutor.invaders import HighScores, LetterInvaders, Word, key_for_char


def make_game(**kw):
    kw.setdefault("rng", random.Random(1234))
    return LetterInvaders(**kw)


class ScoringTests(unittest.TestCase):
    def test_normal_word_score_matches_tt_formula(self):
        g = make_game()
        w = Word(text="camp", kind=1, x=10, y=0, key="c")
        g.active.append(w)
        for ch in "camp":
            ev = g.type_char(ch)
        self.assertEqual(g.scores[0], 5 * 4 * 5)      # 100
        self.assertEqual(g.round_hits, 4)
        self.assertEqual(g.round_misses, 0)
        self.assertNotIn(w, g.active)

    def test_boomlet_double_score(self):
        g = make_game()
        w = Word(text="ab", kind=2, x=10, y=0, key="a")
        g.active.append(w)
        for ch in "ab":
            g.type_char(ch)
        self.assertEqual(g.scores[0], 2 * 5 * 2 * 3)  # 60

    def test_word_ship_double_score(self):
        g = make_game()
        w = Word(text="word", kind=3, x=70, y=0, key="w")
        g.active.append(w)
        for ch in "word":
            g.type_char(ch)
        self.assertEqual(g.scores[0], 2 * 5 * 4 * 5)  # 200

    def test_unmatched_key_costs_ten(self):
        # FUN_1000_9f66 -> FUN_1000_9ecc on any key that does not start a
        # valid word, even when no word is currently locked on.
        g = make_game()
        g.active.append(Word(text="ant", kind=1, x=10, y=0, key="a"))
        ev = g.type_char("z")
        self.assertTrue(ev["miss"])
        self.assertEqual(g.round_misses, 1)
        self.assertEqual(g.scores[0], 0)

    def test_space_is_ignored_when_not_locked_on(self):
        g = make_game()
        g.active.append(Word(text="a b", kind=1, x=10, y=0, key="a"))
        ev = g.type_char(" ")
        self.assertFalse(ev["hit"] or ev["miss"])
        self.assertEqual(g.round_misses, 0)

    def test_wrong_letter_costs_ten(self):
        g = make_game()
        w = Word(text="camp", kind=1, x=10, y=0, key="c")
        g.active.append(w)
        g.type_char("c")
        ev = g.type_char("x")
        self.assertTrue(ev["miss"])
        self.assertEqual(g.scores[0], 0)              # clamped at zero
        self.assertEqual(g.round_misses, 1)
        self.assertIsNone(g.current_word)
        # The word survives and can be retried.
        self.assertIn(w, g.active)
        self.assertEqual(w.typed, 0)

    def test_one_word_per_physical_key(self):
        # 'A' and 'a' share a key; a second word starting with that key is
        # not accepted while the first is active, but another key may spawn.
        g = make_game()
        g.active.append(Word(text="ant", kind=1, x=10, y=0, key="a"))
        seen = set()
        for _ in range(40):
            w = g._next_word()
            if w:
                seen.add(key_for_char(w[0]))
        self.assertNotIn("a", seen)
        self.assertTrue(seen)          # other keys remain available


class ShieldTests(unittest.TestCase):
    def test_ground_hit_removes_shield_cells(self):
        g = make_game()
        w = Word(text="abc", kind=1, x=10, y=g.GROUND_ROW, key="a")
        g.active.append(w)
        g._ground_hit(w)
        self.assertEqual(g.shields[0], g.SHIELD_CELLS - 3)
        self.assertFalse(any(g.shield_grid[0][10:13]))
        self.assertEqual(g.round_misses, 1)

    def test_shield_zero_ends_game(self):
        g = make_game()
        # Destroy every cell except three, then land a three-letter word.
        g.shield_grid[0] = [False] * g.SHIELD_CELLS
        for i in range(3):
            g.shield_grid[0][i] = True
        g.shields[0] = 3
        w = Word(text="abc", kind=1, x=0, y=g.GROUND_ROW, key="a")
        g.active.append(w)
        g._ground_hit(w)
        self.assertEqual(g.shields[0], 0)
        self.assertTrue(g.game_over)


class AccuracyBonusTests(unittest.TestCase):
    def test_bonus_above_ninety_percent(self):
        g = make_game()
        g.round_hits = 95
        g.round_misses = 5
        summary = g.end_round()
        self.assertGreater(summary["accuracy"], 90)
        self.assertEqual(summary["accuracy_bonus"], int((95.0 - 90.0) * 95))

    def test_no_bonus_at_ninety_percent(self):
        g = make_game()
        g.round_hits = 90
        g.round_misses = 10
        summary = g.end_round()
        self.assertEqual(summary["accuracy_bonus"], 0)


class ProgressionTests(unittest.TestCase):
    def test_large_time_jump_is_capped(self):
        g = make_game()
        g.advance(10_000_000)
        self.assertLessEqual(g._tick, 9)   # 1000 ms cap / 120 ms tick

    def test_round_increases_speed_and_spawn_rate(self):
        g = make_game()
        first_speed = g.normal_speed
        first_spawn = g.spawn_interval
        g.next_round()
        self.assertEqual(g.round, 2)
        self.assertLessEqual(g.normal_speed, first_speed)
        self.assertLessEqual(g.spawn_interval, first_spawn)

    def test_two_player_turn_switch(self):
        g = make_game(players=2, names=["A", "B"])
        self.assertEqual(g.current_player, 0)
        g.begin_turn(1, increment_round=False)
        self.assertEqual(g.current_player, 1)
        self.assertEqual(g.round, 1)
        g.begin_turn(0, increment_round=True)
        self.assertEqual(g.round, 2)


class EliminationTests(unittest.TestCase):
    def test_two_player_elimination_and_game_over(self):
        g = make_game(players=2, names=["A", "B"])
        g.shields[0] = 0
        g.round_hits = 5
        g.end_round()
        self.assertTrue(g.eliminated[0])
        self.assertFalse(g.game_over)
        g.begin_turn(1)
        g.shields[1] = 0
        g.round_hits = 5
        g.end_round()
        self.assertTrue(g.eliminated[1])
        self.assertTrue(g.game_over)

    def test_round_ends_when_all_words_are_cleared(self):
        g = make_game()
        g.round_spawned = g.max_words_per_round
        g.active.clear()
        g._spawn_cooldown = 999
        g._do_tick()
        self.assertTrue(g.round_over)

    def test_word_ship_leaving_screen_costs_no_shield(self):
        g = make_game()
        w = Word(text="word", kind=3, x=-(len("word") + 1), y=0, key="w")
        g.active.append(w)
        g._tick = 1          # next tick is even -> ship moves left
        before = g.shields[0]
        g._do_tick()
        self.assertNotIn(w, g.active)
        self.assertEqual(g.shields[0], before)

    def test_shield_persists_across_rounds(self):
        g = make_game()
        g.shields[0] = 55
        g.next_round()
        self.assertEqual(g.shields[0], 55)


class OriginalCorpusTests(unittest.TestCase):
    def test_corpus_is_loaded(self):
        from tttutor.invaders import ORIGINAL_WORDS
        self.assertGreater(len(ORIGINAL_WORDS), 3000)
        for word in ("ada", "dee", "elsa", "street", "can"):
            self.assertIn(word, ORIGINAL_WORDS)

    def test_corpus_has_no_overlong_game_words(self):
        from tttutor.invaders import ORIGINAL_WORDS
        self.assertTrue(any(len(w) > 14 for w in ORIGINAL_WORDS))
        # The game itself filters to 14 chars (the original 15-byte buffer).
        g = make_game(level=1)
        g._refresh_pool()
        self.assertTrue(all(len(w) <= 14 for w in g._pool))

    def test_practice_pool_respects_learned_keys(self):
        g = make_game(level=0, learned_keys="asdf")
        g._refresh_pool()
        allowed = set("asdf")
        for word in g._pool:
            for ch in word:
                self.assertIn(ch, allowed, f"{word!r} contains {ch!r}")

    def test_practice_pool_has_boomlet_candidates(self):
        g = make_game(level=0, learned_keys="asdfjkl;")
        g._refresh_pool()
        self.assertIn("a", g._pool)


class KeyMappingTests(unittest.TestCase):
    def test_shifted_symbols_share_key(self):
        self.assertEqual(key_for_char("A"), "a")
        self.assertEqual(key_for_char("a"), "a")
        self.assertEqual(key_for_char("!"), "1")
        self.assertEqual(key_for_char("?"), "/")


class HighScoreTests(unittest.TestCase):
    def test_top_five_only(self):
        with tempfile.TemporaryDirectory() as d:
            hs = HighScores(Path(d) / "fzvf.json")
            for i in range(7):
                hs.add(0, f"P{i}", i * 10, 7)
            top = hs.top(0)
            self.assertEqual(len(top), 5)
            self.assertEqual([e.score for e in top], [60, 50, 40, 30, 20])
            # Full-keyboard table is independent.
            self.assertEqual(hs.top(1), [])

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "fzvf.json"
            HighScores(p).add(1, "Tester", 1234, 63)
            hs2 = HighScores(p)
            self.assertEqual(hs2.top(1)[0].name, "Tester")
            self.assertEqual(hs2.top(1)[0].score, 1234)


if __name__ == "__main__":
    unittest.main()
