"""Tests for the Quit confirmation dialog."""
import inspect
import unittest

from tttutor import ui


class QuitConfirmTests(unittest.TestCase):
    def test_exit_is_async(self):
        self.assertTrue(inspect.iscoroutinefunction(ui.App.exit))

    def test_exit_uses_choose_dialog(self):
        src = inspect.getsource(ui.App.exit)
        self.assertIn("_choose_dialog", src)
        self.assertIn("Quit Typing Tutor IV?", src)
        # Two options
        self.assertIn("Yes, quit now", src)
        self.assertIn("No, stay", src)
        # Default-returns-when-user-picks-No path
        self.assertIn("return", src)

    def test_quit_doesnt_immediately_loop_stop(self):
        # When user picks "No, stay", loop.stop() must NOT be called.
        src = inspect.getsource(ui.App.exit)
        # Find the no-pick branch
        idx_no = src.find('"No, stay"')
        idx_loop = src.find("self.loop.stop()")
        # Ensure the "return" appears between "No" and "loop.stop()"
        idx_return = src.find("return", idx_no)
        self.assertLess(idx_no, idx_return)
        self.assertLess(idx_return, idx_loop)


if __name__ == "__main__":
    unittest.main()
