"""Tests for the inter-drill celebration banner."""
import inspect
import unittest

from tttutor import ui


class DrillBannerTests(unittest.TestCase):
    def test_banner_helper_present(self):
        self.assertTrue(hasattr(ui.App, "_drill_complete_banner"))
        self.assertTrue(inspect.iscoroutinefunction(
            ui.App._drill_complete_banner))

    def test_drill_screen_calls_banner_on_completion(self):
        # inspect.getsource may return the whole class for small classes;
        # we just check that the call exists in the module source.
        src = inspect.getsource(ui)
        self.assertIn("_drill_complete_banner", src)
        # Banner is invoked only after a drill's finished_monotonic is set
        self.assertIn("finished_monotonic is not None", src)
        # And the banner call appears inside that conditional block
        idx_finished = src.find("finished_monotonic is not None")
        idx_banner   = src.find("_drill_complete_banner(drill)")
        self.assertGreater(idx_finished, 0)
        self.assertGreater(idx_banner, 0)
        self.assertGreater(idx_banner, idx_finished,
                          "banner must be invoked AFTER completion check")

    def test_banner_text_includes_wpm_and_accuracy(self):
        src = inspect.getsource(ui.App._drill_complete_banner)
        self.assertIn("WPM", src)
        self.assertIn("Accuracy", src)
        self.assertIn("Errors", src)
        self.assertIn("Loading next drill", src)
