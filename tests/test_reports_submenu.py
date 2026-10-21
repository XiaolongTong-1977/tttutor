"""Tests for the Reports sub-menu structure (mirrors TT's Reports Menu:
Progress / Speed / Accuracy / Help).
"""
import inspect
import unittest

from tttutor import ui


class ReportsSubMenuTests(unittest.TestCase):
    def test_run_reports_is_async(self):
        self.assertTrue(inspect.iscoroutinefunction(ui.App.run_reports))

    def test_all_four_submenu_items_wired(self):
        for name in ("_reports_progress", "_reports_speed",
                     "_reports_accuracy"):
            self.assertTrue(hasattr(ui.App, name),
                            f"missing {name}")
            self.assertTrue(
                inspect.iscoroutinefunction(getattr(ui.App, name)),
                f"{name} is not async")

    def test_run_reports_lists_all_four_items(self):
        src = inspect.getsource(ui.App.run_reports)
        for label in ("Progress", "Speed", "Accuracy", "Help"):
            self.assertIn(label, src)

    def test_run_reports_uses_horizontal_menu(self):
        src = inspect.getsource(ui.App.run_reports)
        self.assertIn("_tt_submenu", src)
        self.assertIn('title="Reports Menu"', src)

    def test_speed_view_is_per_key(self):
        src = inspect.getsource(ui.App._reports_speed)
        self.assertIn("Speed Graph", src)
        self.assertIn("THIS SESSION", src)
        self.assertIn("HISTORY", src)
        self.assertIn("wpm_target", src)
        self.assertIn("per_key", inspect.getsource(ui.App._per_key_report))

    def test_accuracy_view_is_per_key(self):
        src = inspect.getsource(ui.App._reports_accuracy)
        self.assertIn("Accuracy Graph", src)
        self.assertIn("THIS SESSION", src)
        self.assertIn("HISTORY", src)
        self.assertIn("per_key", inspect.getsource(ui.App._per_key_report))

    def test_progress_has_speed_breakdown(self):
        src = inspect.getsource(ui.App._reports_progress)
        self.assertIn("Letter", src)
        self.assertIn("Number", src)
        self.assertIn("Symbol", src)
        self.assertIn("SESSION / HISTORY", src)


if __name__ == "__main__":
    unittest.main()
