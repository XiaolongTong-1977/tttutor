"""Full-app integration driver.

Feeds keystrokes through a fake curses screen and fails on *any* runtime
exception — the strongest no-crash audit we can run without a real terminal.
"""
from __future__ import annotations

import curses
import tempfile
import unittest
from pathlib import Path

import tttutor.ui as ui


class _EndOfKeys(Exception):
    pass


class FakeScreen:
    def __init__(self, keys, h: int = 25, w: int = 80):
        self._keys = list(keys)
        self.h, self.w = h, w
        self.min_h = h
        self.min_w = w

    def getmaxyx(self):
        return (self.h, self.w)

    def erase(self):
        pass

    def refresh(self):
        pass

    def nodelay(self, _flag):
        pass

    def getch(self):
        if not self._keys:
            raise _EndOfKeys()
        return self._keys.pop(0)

    def addstr(self, *args):
        pass

    def move(self, *args):
        pass


def _drive(keys, h=25, w=80, instructor_password=None):
    # curses functions that require initscr() are stubbed; the App's own
    # _init_colors/_set_cursor are replaced with no-ops as well.
    curses.color_pair = lambda n: n          # type: ignore[assignment]
    ui._init_colors = lambda *a, **k: None   # type: ignore[assignment]
    ui._set_cursor = lambda v: None          # type: ignore[assignment]
    tmp = tempfile.TemporaryDirectory()
    history = Path(tmp.name) / "history.jsonl"
    screen = FakeScreen(keys, h=h, w=w)
    app = ui.App(screen, lessons=[], history_path=history,
                 instructor=instructor_password is not None,
                 instructor_password=instructor_password)
    try:
        app.run()
    except _EndOfKeys:
        pass                                # all keys consumed; no crash
    finally:
        try:
            app.loop.close()
        except Exception:
            pass
        tmp.cleanup()


# Enter, Esc, Down as curses key codes.
_ENTER = 13
_ESC = 27
_DOWN = curses.KEY_DOWN


def _boot_keys():
    """Welcome -> intro -> registration -> interview -> beginner -> main."""
    return (
        [_ENTER,                        # Welcome: Typing Tutor IV
         _ESC]                          # skip introduction
        + [ord(c) for c in "TESTER"] + [_ENTER]   # registration
        + [_ENTER,                      # date confirm
           _ENTER,                      # speed goal
           _ENTER,                      # practice goal
           _ENTER,                      # skill level
           _DOWN, _DOWN, _ENTER]        # begin: Main Menu
    )


class IntegrationDriverTests(unittest.TestCase):
    def test_boot_to_game_flow(self):
        keys = (
            _boot_keys()
            + [ord("g"),                 # Main Menu -> Game (first letter)
               _ENTER,                  # Game Menu -> Play
               _ENTER,                  # Level: Practice Keys
               _ENTER,                  # Players: One
               _ENTER,                  # round intro
               ord("a"), ord("b"), ord("c"),
               _ESC,                    # quit game
               _ESC,                    # leave Game menu
               _ESC,                    # Main menu -> exit dialog
               _DOWN, _ENTER]           # "No, stay"
        )
        _drive(keys)

    def test_boot_flow_small_terminal(self):
        keys = _boot_keys() + [ord("g"), _ENTER, _ENTER, _ENTER, _ENTER,
                               _ESC, _ESC, _ESC, _DOWN, _ENTER]
        _drive(keys, h=15, w=60)

    def test_lessons_and_options_flow(self):
        keys = (
            _boot_keys()
            + [ord("l"),                 # Lessons
               ord("p"),                 # Practice
               _ESC, _ENTER,             # end drill, dismiss summary
               _ESC,                     # Lessons menu -> main
               ord("o"),                 # Options
               ord("w"), _ESC,           # WPM dialog, cancel
               _ESC,                     # Options -> main
               _ESC, _DOWN, _ENTER]      # exit dialog, stay
        )
        _drive(keys)

    def test_quit_menu_yes_exits_cleanly(self):
        # Quit menu item -> confirm dialog -> default "Yes" -> SystemExit(0).
        keys = _boot_keys() + [ord("q"), _ENTER]
        with self.assertRaises(SystemExit) as cm:
            _drive(keys)
        self.assertEqual(cm.exception.code, 0)

    def test_esc_exits_without_exception(self):
        keys = _boot_keys() + [_ESC]
        _drive(keys)   # returns normally; no crash

    def test_instructor_wrong_password(self):
        keys = [_ENTER]                        # dismiss invalid-password alert
        _drive(keys, instructor_password="WRONG")

    def test_instructor_right_password_menu(self):
        keys = [_ENTER,                       # login password
                _ESC,                        # quit instructor menu
                _ENTER]                      # welcome-back? no — after quit
        _drive(keys, instructor_password="KRIYA")

    def test_reports_and_instructor(self):
        keys = (
            _boot_keys()
            + [ord("r"), ord("p"), _ENTER,   # Reports -> Progress
               _ESC,                          # back to Reports
               _ESC,                          # main
               _ESC, _DOWN, _ENTER]           # exit dialog, stay
        )
        _drive(keys)


if __name__ == "__main__":
    unittest.main()
