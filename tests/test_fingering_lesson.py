"""Tests for the fingering drill surface (mirrors TT's Lessons → Fingering).
"""
import inspect
import unittest

from tttutor import ui
from tttutor.content import get_fingering_lessons


class FingeringLessonTests(unittest.TestCase):
    def test_get_fingering_lessons_has_all_four_subsets(self):
        ls = get_fingering_lessons()
        self.assertGreaterEqual(len(ls), 4)
        titles = {l.title for l in ls}
        # The four expected sub-lessons
        for needed in (
            "Fingering — left home row",
            "Fingering — right home row",
            "Fingering — column staggers",
            "Fingering — alternating words",
        ):
            self.assertIn(needed, titles)

    def test_fingering_drills_contain_home_row_chars(self):
        ls = get_fingering_lessons()
        combined = "\n".join(d.text for l in ls for d in l.drills)
        for ch in "asdfjkl":
            self.assertIn(ch, combined,
                          f"fingering drills must exercise {ch}")

    def test_go_fingering_no_longer_placeholder(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("go_fingering", src)
        self.assertIn("_fingering_session", src)
        fs = inspect.getsource(ui.App._fingering_session)
        self.assertIn("_fingering_chart_screen", fs)
        self.assertIn("_fingering_info", fs)
        self.assertIn("_lesson_screen", fs)
        self.assertNotIn("reserved for a future release", fs)

    def test_help_text_lists_fingering_implemented(self):
        src = inspect.getsource(ui.App.run_lessons)
        self.assertIn("Fingering", src)
        self.assertIn("fingering chart", src)


if __name__ == "__main__":
    unittest.main()
