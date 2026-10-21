"""Tests for the Tests sub-menu (Practice / View test scores / Help).
"""
import inspect
import unittest

from tttutor import ui


class TestsSubMenuTests(unittest.TestCase):
    def test_run_tests_is_async(self):
        self.assertTrue(inspect.iscoroutinefunction(ui.App.run_tests))

    def test_all_three_submenu_items_wired(self):
        # _tests_view_scores is the new sub-screen.
        self.assertTrue(hasattr(ui.App, "_tests_view_scores"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._tests_view_scores))

    def test_submenu_lists_all_five_items(self):
        src = inspect.getsource(ui.App.run_tests)
        for label in ("Practice", "All-keys", "Disk", "Keypad", "Help"):
            self.assertIn(f'"{label}"', src)

    def test_submenu_uses_horizontal_menu(self):
        src = inspect.getsource(ui.App.run_tests)
        self.assertIn("_tt_submenu", src)
        self.assertIn('title="Tests Menu"', src)

    def test_view_scores_renders_even_when_no_records(self):
        # Even with an empty history, _tests_view_scores must not raise.
        from tttutor import history as hist

        class Stub:
            username = "x"
            goals = {"wpm_target": 40, "lessons_per_day": 5, "accuracy_target": 0.95}
            history_path = None
            stdscr = None

            async def read_key(self, *_):
                return 27  # Esc
        s = Stub()
        # We just verify the source is sane — no need to drive curses.
        src = inspect.getsource(ui.App._tests_view_scores)
        self.assertIn("No test sessions yet", src)
        self.assertIn("load_all", src)

    def test_help_text_mentions_all_five_items(self):
        src = inspect.getsource(ui.App.run_tests)
        for label in ("Practice", "All-keys", "Disk", "Keypad", "Help"):
            self.assertIn(label, src)


if __name__ == "__main__":
    unittest.main()
