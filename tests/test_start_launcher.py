"""Tests for the start.py launcher."""
import subprocess
import sys
import unittest
from pathlib import Path

START = str(Path(__file__).resolve().parent.parent / "start.py")
PYTHON = sys.executable


class StartLauncherTests(unittest.TestCase):
    def _run(self, *args, cwd=None):
        return subprocess.run(
            [PYTHON, START, *args],
            capture_output=True, text=True, cwd=cwd,
            timeout=30,
        )

    def test_version_flag(self):
        r = self._run("--version")
        self.assertEqual(r.returncode, 0)
        self.assertIn("tttutor", r.stdout)
        self.assertIn("python", r.stdout.lower())

    def test_help_flag(self):
        r = self._run("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--check", r.stdout)
        self.assertIn("--init", r.stdout)
        self.assertIn("--reset", r.stdout)
        self.assertIn("--version", r.stdout)
        self.assertIn("--tst-dir", r.stdout)
        self.assertIn("--history", r.stdout)

    def test_check_runs_in_non_tty(self):
        r = self._run("--check", cwd="/tmp")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        # Should report the audio backend and lesson count
        self.assertIn("curses", r.stdout)
        self.assertIn("lessons", r.stdout)
        # No tty warning is fine either way

    def test_check_lesson_count(self):
        r = self._run("--check", cwd="/tmp")
        self.assertIn("76 drills", r.stdout)

    def test_init_is_idempotent(self):
        # First run creates dir
        r1 = self._run("--init", cwd="/tmp")
        self.assertEqual(r1.returncode, 0, msg=r1.stderr)
        # Second run should also succeed without error
        r2 = self._run("--init", cwd="/tmp")
        self.assertEqual(r2.returncode, 0, msg=r2.stderr)

    def test_reset_handles_missing_file(self):
        # Should be a no-op success when file doesn't exist
        r = self._run("--reset", "--yes", cwd="/tmp")
        self.assertEqual(r.returncode, 0, msg=r.stderr)

    def test_unknown_flag_returns_error(self):
        r = self._run("--no-such-flag")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unrecognized", r.stderr.lower())

    def test_works_from_arbitrary_cwd(self):
        # Critical guarantee: from /tmp, the package must import correctly.
        r = self._run("--check", cwd="/tmp")
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        # It should report the lesson count (proves tttutor.* importable)
        self.assertIn("lessons", r.stdout)
        self.assertIn("76 drills", r.stdout)


if __name__ == "__main__":
    unittest.main()
