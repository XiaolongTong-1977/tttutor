"""Curses-based UI — modern, cross-platform, stdlib only.

The UI is intentionally small and explicit. Each screen is its own coroutine
(sketch below). The UI talks to the engine via `TypingDrill` and to history
via the `history` module — no globals, no shared state.
"""
from __future__ import annotations

import asyncio
import curses
import curses.textpad
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .engine import (
    CharStatus,
    DrillResult,
    Lesson,
    LessonRun,
    TypingDrill,
    lesson_summary,
)
from .invaders import HighScores, LetterInvaders, KEY_ORDER
from .history import HistoryRecord
from . import settings as settings_mod
from .sound import SoundEvent, SoundPlayer


# ---- color pairs --------------------------------------------------------
# Color scheme is matched to TT.EXE's CGA palette: deep-blue background with
# bright white / cyan / yellow / green / red / magenta foregrounds. The 8-color
# ncurses palette is brightened with the A_BOLD attribute to approximate CGA's
# high-intensity colors that DOSBox shows on a real text-mode display.
PAIR_DEFAULT = 1   # white on blue           — body text
PAIR_TITLE   = 2   # bright cyan on blue     — title bar / headings
PAIR_PROMPT  = 3   # bright yellow on blue   — selected / highlighted item
PAIR_OK      = 4   # bright green on blue    — correct / passing
PAIR_BAD     = 5   # bright red on blue      — wrong / error
PAIR_CURSOR  = 6   # black on bright yellow  — drill cursor
PAIR_DIM     = 7   # dim blue on blue         — pending / placeholder
PAIR_HINT    = 8   # bright magenta on blue   — bottom hints / sub-titles
PAIR_ACCENT  = 9   # bright green on blue    — box borders / accents
PAIR_SELECTED = 10 # yellow on magenta        — CGA menu highlight

# The TT screenshot backgrounds are a deep blue. ncurses -1 == "terminal
# default", which most terminals render as black.  Force a blue background by
# explicitly setting every color pair's background to COLOR_BLUE and using
# bkgd() to paint the whole screen with the default pair.
TT_BG = curses.COLOR_BLUE if False else 1            # CGA color 1 = blue
# A_BOLD bit acts as the CGA "high intensity" bit. Apply on the few pairs that
# TT shows brighter than the rest.
B = curses.A_BOLD
# Alias used by some helper render paths that predate the rename to B.
A = B


def _init_colors(win=None) -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    # Redefine palette "blue" to the exact CGA blue (#0000AA) that TT.EXE's
    # text mode uses. COLOR_BLUE is only a palette INDEX — its RGB value is
    # chosen by the terminal theme, so on dark/black-themed terminals the
    # background could render navy, purplish or grayish instead of the
    # original CGA blue. init_color() fixes the RGB on any terminal that
    # supports palette changes (xterm, kitty, foot, wezterm, tmux 3.x,
    # Windows Terminal, Linux console, ...). ncurses restores the original
    # palette on endwin(). On terminals that cannot change colors we keep
    # the theme's blue — the best available approximation.
    if curses.can_change_color():
        try:
            curses.init_color(curses.COLOR_BLUE, 0, 0, 667)  # #0000AA
        except curses.error:
            pass
    # We do NOT use_default_colors() — we want the explicit blue background.
    # Background is the same value (1, blue) for every pair; foregrounds are
    # 8-color values brightened with the A_BOLD attribute below.
    bg = curses.COLOR_BLUE
    curses.init_pair(PAIR_DEFAULT, curses.COLOR_WHITE,  bg)
    curses.init_pair(PAIR_TITLE,   curses.COLOR_WHITE,   bg)
    curses.init_pair(PAIR_PROMPT,  curses.COLOR_YELLOW,  bg)
    curses.init_pair(PAIR_OK,      curses.COLOR_GREEN,   bg)
    curses.init_pair(PAIR_BAD,     curses.COLOR_RED,     bg)
    curses.init_pair(PAIR_CURSOR,  curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    curses.init_pair(PAIR_DIM,     curses.COLOR_CYAN,    bg)
    curses.init_pair(PAIR_HINT,    curses.COLOR_WHITE,   bg)
    curses.init_pair(PAIR_ACCENT,  curses.COLOR_GREEN,   bg)
    curses.init_pair(PAIR_SELECTED, curses.COLOR_YELLOW, curses.COLOR_MAGENTA)
    # Do NOT set win.bkgd()/bkgdset() here. A window background makes
    # ncurses treat the grid as uniformly blank and collapse repaints into
    # screen-wide erase ops, which terminals like tmux fill with the DEFAULT
    # background (black bands). All screen clears go through _erase_screen(),
    # which paints explicit blue space rows instead.


# ---- utilities ----------------------------------------------------------

def _attr(c: str) -> int:
    return curses.color_pair(c) | curses.A_BOLD


def _set_cursor(visible: int) -> None:
    """Set cursor visibility, ignoring terminals without cursor support."""
    try:
        curses.curs_set(visible)
    except curses.error:
        pass


def _safe_addstr(win, y: int, x: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = text[: max(0, w - x - 1)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def _erase_screen(win) -> None:
    """Clear the whole screen to TT.EXE's blue background.

    win.erase() fills every cell with the window's background attribute and
    lets ncurses repaint. When the whole grid becomes uniformly blank with
    the same attribute, ncurses optimises the repaint into screen-wide erase
    operations (ED/EL); terminals such as tmux fill erase ops with the
    DEFAULT background, which produced black bands around the blue areas.
    Painting explicit blue space rows keeps every cell blue on every
    terminal. The last column is deliberately left untouched so the grid
    never looks like one uniform blank run, which is exactly the case that
    triggers ncurses' erase-op optimisation.
    """
    h, w = win.getmaxyx()
    attr = curses.color_pair(PAIR_DEFAULT)
    for y in range(h):
        _safe_addstr(win, y, 0, " " * max(0, w - 1), attr)
    try:
        win.move(0, 0)
    except curses.error:
        pass


# ---- TT.EXE-style 80x25 primitives ---------------------------------
BOX_TL, BOX_TR, BOX_BL, BOX_BR = "┌", "┐", "└", "┘"
BOX_H, BOX_V = "─", "│"


def _header(win, title: str, username: str = "") -> None:
    """Top row title + right-aligned user, followed by a full-width rule."""
    h, w = win.getmaxyx()
    _safe_addstr(win, 0, 1, title[: max(0, w - 16)],
                 curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
    if username:
        _safe_addstr(win, 0, max(0, w - len(username) - 2), username[:w - 4],
                     curses.color_pair(PAIR_DEFAULT))
    _safe_addstr(win, 1, 0, "-" * max(0, w - 1),
                 curses.color_pair(PAIR_DEFAULT))


def _center(win, y: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    _safe_addstr(win, y, max(0, (w - len(text)) // 2), text, attr)


def _box(win, top: int, left: int, height: int, width: int,
         attr: int = 0) -> None:
    """Draw a single-line CP437 box, like TT.EXE's green frames."""
    if height < 2 or width < 2:
        return
    attr = attr or curses.color_pair(PAIR_ACCENT)
    _safe_addstr(win, top, left, BOX_TL + BOX_H * (width - 2) + BOX_TR, attr)
    for y in range(top + 1, top + height - 1):
        _safe_addstr(win, y, left, BOX_V, attr)
        _safe_addstr(win, y, left + width - 1, BOX_V, attr)
    _safe_addstr(win, top + height - 1, left,
                 BOX_BL + BOX_H * (width - 2) + BOX_BR, attr)


def _box_text(win, top: int, left: int, height: int, width: int,
              lines: list[str], *, center: bool = False,
              text_attr: int = 0, border_attr: int = 0) -> None:
    _box(win, top, left, height, width, border_attr)
    text_attr = text_attr or curses.color_pair(PAIR_DEFAULT)
    y = top + 1
    for line in lines:
        if y >= top + height - 1:
            break
        x = left + 2
        if center:
            x = left + max(2, (width - len(line)) // 2)
        _safe_addstr(win, y, x, line[: max(0, width - 4)], text_attr)
        y += 1


def _wrap(text: str, width: int) -> list[str]:
    import textwrap
    return textwrap.wrap(text, width=max(10, width)) or [""]


def _item_label(item) -> str:
    return getattr(item, "title", getattr(item, "label", str(item)))


def _menu_bar(win, y: int, labels: list[str], selected: int) -> None:
    """Horizontal menu bar: two spaces between items, inverse selection."""
    x = 0
    for i, label in enumerate(labels):
        text = f" {label} "
        attr = (curses.color_pair(PAIR_SELECTED) | curses.A_BOLD
                if i == selected else curses.color_pair(PAIR_DEFAULT))
        _safe_addstr(win, y, x, text, attr)
        x += len(text)


def _selected_row(win, y: int, left: int, width: int, text: str,
                  selected: bool, *, center: bool = False) -> None:
    attr = (curses.color_pair(PAIR_SELECTED) | curses.A_BOLD
            if selected else curses.color_pair(PAIR_DEFAULT))
    padded = text.ljust(max(0, width - 2))
    if center:
        padded = text.center(max(0, width - 2))
    _safe_addstr(win, y, left, " " + padded + " ", attr)


def _bar(value: float, lo: float, hi: float, width: int = 10) -> str:
    """Tiny ASCII bar for wpm or accuracy graphs."""
    if hi <= lo:
        return ""
    v = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    filled = int(v * width)
    return "█" * filled + "·" * (width - filled)


def _fmt_time(s: float) -> str:
    if s < 60:
        return f"{int(s):d}s"
    return f"{int(s // 60)}:{int(s % 60):02d}"


# ---- screens ------------------------------------------------------------

MAIN_HELP = (
    "There are six menus in this program: the Main Menu and the secondary "
    "menus of Lessons, Tests, Reports, Options, and Game.  The top line on "
    "each menu shows the available menu features.\n\n"
    "The second line gives more information about the highlighted feature. "
    "To select a feature use the right and left arrow keys (or the space "
    "bar) to highlight it.  When the feature you want is highlighted, press "
    "Enter to select it.  You can also make a selection by typing the first "
    "letter of the desired feature.\n\n"
    "If the highlighted item is the name of a secondary menu, the second "
    "line shows that menu's available features.  Otherwise, the second line "
    "describes the highlighted feature."
)


@dataclass
class MenuItem:
    label: str
    description: str
    action: Callable[[], object]


class _UserCancelled(Exception):
    """Internal sentinel: user pressed Esc to leave an intro/registration."""


class App:
    """Main app — owns the curses window, dispatches screens."""

    def __init__(self, stdscr, lessons: List[Lesson], history_path=None,
                 sound: Optional[SoundPlayer] = None, username: str = "",
                 instructor: bool = False,
                 instructor_password: Optional[str] = None,
                 tst_dir=None):
        self.stdscr = stdscr
        self.lessons = lessons
        self.history_path = history_path
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.sound = sound or SoundPlayer()
        self.instructor_mode = instructor
        self.instructor_password = instructor_password
        self.report_user: Optional[str] = None
        self.tst_dir = Path(tst_dir) if tst_dir else None
        self.settings_path = (
            Path(history_path).with_name("settings.json") if history_path else None
        )
        self.settings = settings_mod.load(self.settings_path)
        self.username = username or self.settings.get("username", "")
        self.registered = bool(self.settings.get("registered", False)) and bool(self.username)
        self.goals = self.settings["goals"]
        self.skill_level = self.settings["skill_level"]
        self.learned_keys = self.settings["learned_keys"]
        self.session_start = time.time()
        self.drills_per_lesson = int(self.settings.get("drills_per_lesson", 10))
        if sound is None:
            self.sound.enabled = bool(self.settings.get("sound_enabled", True))
        self.highscore_path = (
            Path(history_path).with_name("fzvf.json") if history_path else None
        )

    def _save_settings(self) -> None:
        self.settings["goals"] = self.goals
        self.settings["skill_level"] = self.skill_level
        self.settings["learned_keys"] = self.learned_keys
        self.settings["drills_per_lesson"] = self.drills_per_lesson
        self.settings["sound_enabled"] = self.sound.enabled
        settings_mod.save(self.settings, self.settings_path)

    def run(self):
        _init_colors(self.stdscr)
        _set_cursor(0)
        self.stdscr.nodelay(False)
        return self.loop.run_until_complete(self.main())

    async def main(self):
        try:
            return await self._main_unprotected()
        except _UserCancelled:
            return

    def _last_session_summary(self) -> str:
        """One-line summary of the user's most recent drill/test, or ''."""
        from .history import load_all
        try:
            records = load_all(self.history_path)
        except Exception:
            return ""
        if not records:
            return ""
        records.sort(key=lambda r: r.ts, reverse=True)
        for r in records:
            if r.kind in ("drill", "test"):
                wpm = r.detail.get("wpm_avg", r.detail.get("wpm", 0.0))
                acc = r.detail.get("accuracy_avg", r.detail.get("accuracy", 0.0))
                if wpm or acc:
                    return (f"Last: {wpm:.1f} WPM @ {acc*100:.0f}%  "
                            f"({r.label[:14]})")
        return ""

    async def _main_unprotected(self):
        if getattr(self, "instructor_mode", False):
            if not await self._instructor_login(self.instructor_password):
                await self._alert("Invalid password for Instructor Mode.")
                return
            await self._instructor_menu()
            return

        if not getattr(self, "registered", False):
            # Title screen (TT's "Press any key to begin." screen).
            if not getattr(self, "_welcome_seen", False):
                choice = await self._welcome_screen()
                if not choice:
                    return
                self._welcome_seen = True

            # Multi-page Introduction — verbatim text from TT.HLP.
            if not getattr(self, "_intro_seen", False):
                await self._intro_pages()
                self._intro_seen = True

            # First-time user registration.
            if not self.username:
                name = await self._registration_screen()
                if not name:
                    return
                self.username = name

            # Date confirm, goals, skill level.
            if not getattr(self, "_interview_done", False):
                ok = await self._date_confirm_screen()
                if not ok:
                    return
                await self._goals_question_screen()
                await self._skill_level_screen()
                self._interview_done = True

            # "Where would you like to begin.." — first run only.
            if not getattr(self, "_beginner_seen", False):
                choice = await self._beginner_screen()
                if choice == "Practice Lesson":
                    await self.run_lessons()
                elif choice == "Practice Test":
                    await self.run_tests()
                self._beginner_seen = True

            self.settings["username"] = self.username
            self.settings["registered"] = True
            self._save_settings()
            self.registered = True
        else:
            await self._welcome_back_screen()

        items: list[MenuItem] = [
            MenuItem("Lessons", "Guided drills, ascending difficulty", self.run_lessons),
            MenuItem("Tests",  "Initial / timed tests",               self.run_tests),
            MenuItem("Reports", "WPM and accuracy history",           self.run_reports),
            MenuItem("Options", "WPM, Time, Drills, Sound, Name, Intro", self.run_options),
            MenuItem("Game", "Letter Invaders and top scores",        self.run_game),
            MenuItem("Help", "How this program works",               self.run_help),
            MenuItem("Quit", "Exit",                                 self.exit),
        ]
        await self.menu_screen(
            title="Main Menu",
            items=items,
            second_lines={
                "Lessons": "Practice  Fingering  Keypad  Help",
                "Tests": "Practice  All-keys  Disk  Keypad  Help",
                "Reports": "Progress  Speed  Accuracy  Help",
                "Options": "WPM  Time  Drills  Sound  Name  Intro  Help",
                "Game": "Play  Scores  Help",
                "Help": "Information about Main Menu",
                "Quit": "Exit Typing Tutor IV",
            },
            help_text=MAIN_HELP,
            parent_hint="Esc -> Exit Typing Tutor IV",
        )

    async def _welcome_back_screen(self) -> None:
        """Short version of TT's 'Welcome back to Typing Tutor IV!' screen."""
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Welcome Back", self.username or "")
        last = self._last_session_summary()
        lines = [
            f"Welcome back to Typing Tutor IV, {self.username}!",
            "Regular practice is the key to increasing your typing speed",
            "and accuracy.",
        ]
        if last:
            lines.append(last)
        for i, line in enumerate(lines):
            _safe_addstr(self.stdscr, 5 + i, 4, line,
                         curses.color_pair(PAIR_DEFAULT))
        _safe_addstr(self.stdscr, h - 2, 4, "Press any key to continue.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def exit(self):
        # Confirm before quitting — accidental Q presses during typing
        # are easy to do.  We invoke the same dialog helper used by the
        # Date / Goals / Skill screens.
        choice = await self._choose_dialog(
            title="Quit",
            header="Quit Typing Tutor IV?",
            items=[
                ("Yes, quit now",  "exit and save progress"),
                ("No, stay",       "return to the main menu"),
            ],
            status="..press Enter to select.   Esc = stay.",
        )
        if choice is None or choice.startswith("No"):
            return                       # user picked "stay"
        self.loop.stop()
        raise SystemExit(0)

    # ---- menu -------------------------------------------------------
    async def horizontal_menu(self, *, title: str, items: list,
                              second_lines=None, help_text: str = "",
                              parent_hint: str = "", initial: int = 0):
        """TT.EXE-style horizontal menu bar.

        Layout (80x25):
          row 0  screen title                         user name
          row 1  ------------------------------------------------
          row 2   Item1  Item2  Item3 ...   (inverse selection)
          row 3  description / submenu items for the selection
          row 4+ optional green help frame
          row 23 Esc -> parent
        """
        if not items:
            return None
        idx = initial % len(items)
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, title, self.username or "")
            labels = [_item_label(it) for it in items]
            _menu_bar(self.stdscr, 2, labels, idx)
            if second_lines:
                if isinstance(second_lines, dict):
                    second = second_lines.get(labels[idx], "")
                else:
                    second = second_lines[idx] if idx < len(second_lines) else ""
            else:
                second = getattr(items[idx], "description", "") or ""
            _safe_addstr(self.stdscr, 3, 0, second[: max(0, w - 4)],
                         curses.color_pair(PAIR_DEFAULT))
            if help_text:
                lines: list[str] = []
                for para in str(help_text).split("\n\n"):
                    lines.extend(_wrap(para, max(20, w - 8)))
                    lines.append("")
                if lines and lines[-1] == "":
                    lines.pop()
                box_h = min(h - 8, len(lines) + 4)
                _box_text(self.stdscr, 4, 2, box_h, w - 4, lines,
                          text_attr=curses.color_pair(PAIR_DEFAULT),
                          border_attr=curses.color_pair(PAIR_ACCENT))
            if parent_hint:
                _center(self.stdscr, h - 2, parent_hint,
                        curses.color_pair(PAIR_DEFAULT))
            self.stdscr.refresh()
            ch = await self.read_key()
            if ch in (curses.KEY_LEFT, "h", "H"):
                idx = (idx - 1) % len(items)
            elif ch in (curses.KEY_RIGHT, "l", "L", " ", 32):
                idx = (idx + 1) % len(items)
            elif ch in (curses.KEY_ENTER, 10, 13, "\n", "\r"):
                return items[idx]
            elif ch in (27, 3, "q", "Q"):
                return None
            else:
                # TT also lets the user pick by the first letter.  curses
                # returns printable keys as ints, so accept both forms.
                if isinstance(ch, int) and 32 <= ch <= 126:
                    char = chr(ch)
                elif isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                    char = ch
                else:
                    char = None
                if char:
                    for i, it in enumerate(items):
                        if _item_label(it)[:1].upper() == char.upper():
                            return it

    async def _tt_submenu(self, *, title: str, items: list,
                          second_lines=None, help_text: str = "",
                          parent_hint: str = "Esc -> Main Menu") -> None:
        """Run a TT-style horizontal submenu until Esc."""
        while True:
            picked = await self.horizontal_menu(
                title=title, items=items, second_lines=second_lines,
                help_text=help_text, parent_hint=parent_hint,
            )
            if picked is None:
                return
            action = getattr(picked, "_action", None)
            if action is None:
                return
            result = action()
            if asyncio.iscoroutine(result):
                await result

    async def menu_screen(self, *, title: str, items: list[MenuItem],
                          second_lines=None, help_text: str = "",
                          parent_hint: str = "") -> None:
        while True:
            picked = await self.horizontal_menu(
                title=title, items=items, second_lines=second_lines,
                help_text=help_text, parent_hint=parent_hint,
            )
            if picked is None:
                return
            result = picked.action()
            if asyncio.iscoroutine(result):
                await result
            # Loop back to the menu after a sub-screen, like TT.EXE.

    # ---- input helpers ----------------------------------------------
    async def read_key(self, timeout: float | None = None) -> int | str:
        """Read one key, or return -1 after ``timeout`` seconds.

        Curses has no async keyboard API, so we poll with nodelay and yield
        to the event loop.  A timeout of None blocks until a key arrives.
        """
        start = time.monotonic()
        self.stdscr.nodelay(True)
        try:
            while True:
                ch = self.stdscr.getch()
                if ch != -1:
                    return ch
                if timeout is not None and (time.monotonic() - start) >= timeout:
                    return -1
                await asyncio.sleep(0.05)
        finally:
            self.stdscr.nodelay(False)

    async def read_line(self, prompt: str, max_chars: int = 32,
                        title: str = "Registration") -> Optional[str]:
        """TT.EXE-style single-line input box (registration/name/password)."""
        self.stdscr.nodelay(False)
        _set_cursor(1)
        buf: list[str] = []
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, title, self.username or "")
            box_w = min(w - 8, max(50, len(prompt) + 14))
            box_h = 7
            top = max(2, (h - box_h) // 2)
            left = max(2, (w - box_w) // 2)
            _box(self.stdscr, top, left, box_h, box_w)
            pr = prompt.rstrip()
            if not pr.endswith(("..", "?", "!", ".")):
                pr += ".."
            _safe_addstr(self.stdscr, top + 1, left + 3,
                         pr[: max(0, box_w - 6)],
                         curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
            field_w = max(10, box_w - 8)
            _safe_addstr(self.stdscr, top + 3, left + 3,
                         "_" * field_w, curses.color_pair(PAIR_DIM))
            _safe_addstr(self.stdscr, top + 3, left + 3,
                         "".join(buf)[:field_w],
                         curses.color_pair(PAIR_PROMPT) | curses.A_BOLD)
            tail = "..then press Enter."
            _safe_addstr(self.stdscr, top + box_h - 2,
                         left + max(3, box_w - len(tail) - 3), tail,
                         curses.color_pair(PAIR_DEFAULT))
            _center(self.stdscr, h - 1,
                    "Enter = accept   Esc = quit   Backspace = delete",
                    curses.color_pair(PAIR_DEFAULT))
            try:
                self.stdscr.move(top + 3, left + 3 + min(len(buf), field_w - 1))
            except curses.error:
                pass
            self.stdscr.refresh()
            ch = self.stdscr.getch()
            if ch in (curses.KEY_ENTER, 10, 13):
                _set_cursor(0)
                return "".join(buf).strip()
            if ch in (27, 3):
                _set_cursor(0)
                return None
            if ch in (curses.KEY_BACKSPACE, 127, 8, "\b"):
                if buf:
                    buf.pop()
            elif isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                if len(buf) < max_chars:
                    buf.append(ch)
            elif isinstance(ch, int) and 32 <= ch <= 126:
                if len(buf) < max_chars:
                    buf.append(chr(ch))

    # ---- screens ----------------------------------------------------
    async def run_lessons(self):
        """Lessons Menu: Practice / Fingering / Keypad / Help."""
        class _LessonsItem:
            def __init__(self, title, action):
                self.title = title
                self.description = ""
                self._action = action

        async def go_practice():
            await self._practice_session()

        async def go_fingering():
            await self._fingering_session()

        async def go_keypad():
            await self._keypad_session()

        async def go_help():
            await self._alert(
                "The features of the Lessons Menu are:\n\n"
                "Practice - is a sequence of one line drills on the keyboard. "
                "As you progress, new keys are introduced starting with the home "
                "keys. A fingering chart is shown whenever a new key is introduced.\n"
                "Fingering - allows you to take a home key lesson on any key. A "
                "fingering chart is displayed highlighting the selected key and "
                "its home key.\n"
                "Keypad - gives drills and home key lessons for the numeric keypad. "
                "Each drill is three lines; the '+' key ends each line.\n"
                "Help - displays this screen."
            )

        items = [
            _LessonsItem("Practice", go_practice),
            _LessonsItem("Fingering", go_fingering),
            _LessonsItem("Keypad", go_keypad),
            _LessonsItem("Help", go_help),
        ]
        await self._tt_submenu(
            title="Lessons Menu", items=items,
            second_lines={
                "Practice": "Practice Lesson",
                "Fingering": "Finger Positioning Lesson",
                "Keypad": "Keypad Lesson",
                "Help": "Information about Lessons Menu",
            },
            parent_hint="Esc -> Main Menu",
        )

    def _generated_practice_lesson(self) -> Optional[Lesson]:
        """Practice drills generated from the original TT text streams."""
        from .original_text import generate_drills
        learned = (self.learned_keys or "") + " "
        preferred = min(50, max(0, len(self.learned_keys or "") // 2))
        candidates = [preferred, 14, 16, 22, 25, 26, 0, 1, 2, 3, 4, 5, 10, 6, 7]
        best_lines: list[str] = []
        best_score = 0
        for stream in dict.fromkeys(candidates):
            lines = generate_drills(
                stream, allowed_keys=learned,
                drills=max(1, self.drills_per_lesson),
                words_per_line=5, seed=0,
            )
            score = len(set(" ".join(lines).split())) if lines else 0
            if score > best_score:
                best_lines, best_score = lines, score
            if best_score >= 20:
                break
        if not best_lines:
            # Early lessons often have too few template words for the learned
            # key set; fall back to the original corpus, still filtered by
            # those keys, rather than the modern bundled lesson text.
            from .invaders import ORIGINAL_WORDS
            from .original_text import generate_drills_from_words
            allowed = set(learned)
            words = [w for w in ORIGINAL_WORDS
                     if 1 <= len(w) <= 12 and all(c in allowed for c in w)]
            best_lines = generate_drills_from_words(
                words, drills=max(1, self.drills_per_lesson),
                words_per_line=5, seed=0)
        if not best_lines:
            return None
        return Lesson.from_lines(
            "Practice Lesson", best_lines,
            "Generated from TT.EXE's original token/macro text stream.")

    async def _practice_session(self):
        lesson = self._generated_practice_lesson() or self._next_practice_lesson()
        if lesson is None:
            await self._alert("No lessons available.")
            return
        drills = lesson.drills[: max(1, self.drills_per_lesson)]
        lesson = Lesson(title=lesson.title, drills=drills,
                        description=lesson.description)
        run = LessonRun(lesson=lesson)
        await self._lesson_screen(lesson, run)
        self._save_lesson_summary(lesson, run)
        self._advance_learned_keys()

    def _next_practice_lesson(self) -> Optional[Lesson]:
        from .lessons import available_lessons
        from .history import load_all
        lessons = list(self.lessons) or available_lessons()
        if not lessons:
            return None
        try:
            records = [r for r in load_all(self.history_path)
                       if r.kind == "lesson" and (not r.user or r.user == self.username)]
        except Exception:
            records = []
        completed = {
            r.label for r in records
            if int(r.detail.get("drills", 0) or 0) > 0
            and int(r.detail.get("completed", 0) or 0) >= int(r.detail.get("drills", 1) or 1)
        }
        for lesson in lessons:
            if lesson.title not in completed:
                return lesson
        return lessons[len(records) % len(lessons)]

    def _advance_learned_keys(self) -> None:
        before = self.learned_keys
        self.learned_keys = settings_mod.extend_learned_keys(self.learned_keys, 2)
        if self.learned_keys != before:
            self.settings["learned_keys"] = self.learned_keys
            self._save_settings()

    # ---- fingering ---------------------------------------------------
    async def _fingering_session(self) -> None:
        while True:
            key = await self._fingering_chart_screen()
            if key is None:
                return
            home, hand, finger = self._fingering_info(key)
            if not await self._fingering_info_screen(key, home, hand, finger):
                return
            lines = [
                f"{home}{key} {home}{key} {key}{home} {key}{home}",
                f"{home}{home}{key} {key}{home}{home} {home}{key}{home}",
                f"{key}{key}{home} {home}{key}{key} {key}{home}{key}",
                f"{home}{key}{home}{key} {key}{home}{key}{home}",
                f"{home}{home}{key}{key} {key}{key}{home}{home}",
                f"{home}{key}{key}{home} {key}{home}{home}{key}",
            ]
            lesson = Lesson.from_lines(
                f"Fingering — {key}", lines,
                f"Use your {hand} {finger} finger for '{key}'; home key '{home}'.")
            run = LessonRun(lesson=lesson)
            await self._lesson_screen(lesson, run)
            self._save_lesson_summary(lesson, run)

    async def _fingering_chart_screen(self) -> Optional[str]:
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _safe_addstr(self.stdscr, 0, 2, "Fingering",
                     curses.color_pair(PAIR_TITLE) | B)
        _safe_addstr(self.stdscr, 0, w - 12, self.username or "(unnamed)",
                     curses.color_pair(PAIR_DIM))
        intro = [
            "The highlighted keys are the home keys.  The left hand is over 'ASDF'.",
            "The little finger types 'A', ring finger 'S', middle finger 'D',",
            "and index finger 'F'.",
            "",
            "The right hand is over 'JKL;'.  The index finger types 'J', middle",
            "finger 'K', ring finger 'L', and little finger ';'.",
            "",
            "Press any other key for a fingering lesson on that key.",
        ]
        for i, line in enumerate(intro):
            _safe_addstr(self.stdscr, 2 + i, 4, line, curses.color_pair(PAIR_DEFAULT))
        rows = [
            " 1 2 3 4 5 6 7 8 9 0",
            "  q w e r t y u i o p",
            "   a s d f g h j k l ;",
            "    z x c v b n m , . /",
        ]
        home = set("asdfjkl;")
        y = 12
        for row in rows:
            x = 6
            for ch in row:
                if ch == " ":
                    x += 1
                    continue
                attr = (curses.color_pair(PAIR_OK) | B) if ch.lower() in home \
                    else curses.color_pair(PAIR_DEFAULT)
                _safe_addstr(self.stdscr, y, x, ch, attr)
                x += 2
            y += 1
        _safe_addstr(self.stdscr, h - 2, 2, "Esc -> Lessons Menu",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        ch = await self.read_key()
        if ch == 27:
            return None
        if isinstance(ch, int) and 32 <= ch <= 126:
            return chr(ch)
        if isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
            return ch
        return None

    def _fingering_info(self, key: str) -> tuple[str, str, str]:
        k = key.lower()
        groups = {
            "a": ("a", "left", "little"), "s": ("s", "left", "ring"),
            "d": ("d", "left", "middle"), "f": ("f", "left", "index"),
            "g": ("f", "left", "index"), "q": ("a", "left", "little"),
            "w": ("s", "left", "ring"), "e": ("d", "left", "middle"),
            "r": ("f", "left", "index"), "t": ("f", "left", "index"),
            "z": ("a", "left", "little"), "x": ("s", "left", "ring"),
            "c": ("d", "left", "middle"), "v": ("f", "left", "index"),
            "b": ("f", "left", "index"),
            "j": ("j", "right", "index"), "k": ("k", "right", "middle"),
            "l": ("l", "right", "ring"), ";": (";", "right", "little"),
            "h": ("j", "right", "index"), "y": ("j", "right", "index"),
            "u": ("j", "right", "index"), "m": ("j", "right", "index"),
            "n": ("j", "right", "index"), "i": ("k", "right", "middle"),
            ",": ("k", "right", "middle"), "o": ("l", "right", "ring"),
            ".": ("l", "right", "ring"), "p": (";", "right", "little"),
            "/": (";", "right", "little"), "'": (";", "right", "little"),
        }
        if k in groups:
            return groups[k]
        if k.isdigit():
            return {"1": ("a", "left", "little"), "2": ("s", "left", "ring"),
                    "3": ("d", "left", "middle"), "4": ("f", "left", "index"),
                    "5": ("f", "left", "index"), "6": ("j", "right", "index"),
                    "7": ("j", "right", "index"), "8": ("k", "right", "middle"),
                    "9": ("l", "right", "ring"), "0": (";", "right", "little")}[k]
        return ("a", "left", "little")

    async def _fingering_info_screen(self, key: str, home: str,
                                     hand: str, finger: str) -> bool:
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _safe_addstr(self.stdscr, 1, 2, "Home Key Lesson",
                     curses.color_pair(PAIR_TITLE) | B)
        lines = [
            f"Use your {hand} {finger} finger to strike both the '{home}'",
            f"and the '{key}' keys.  Remember to position your fingers over",
            "the home keys and reach from there to all other parts of the",
            "keyboard.",
        ]
        for i, line in enumerate(lines):
            _safe_addstr(self.stdscr, 4 + i, 4, line, curses.color_pair(PAIR_DEFAULT))
        _safe_addstr(self.stdscr, h - 2, 2, "Press Enter to begin.  Esc -> Fingering",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        while True:
            ch = await self.read_key()
            if ch in (curses.KEY_ENTER, 10, 13, 32):
                return True
            if ch == 27:
                return False

    # ---- keypad ------------------------------------------------------
    async def _keypad_session(self) -> None:
        from .content import get_keypad_drill_groups
        groups = get_keypad_drill_groups()[:3]
        lines = [line for group in groups for line in group]
        lesson = Lesson.from_lines(
            "Keypad Lesson", lines,
            "Type the lines in the top box.  End each line with '+'.")
        run = LessonRun(lesson=lesson)
        await self._lesson_screen(lesson, run, show_summary=False)
        self._save_lesson_summary(lesson, run)
        await self._keypad_summary_screen(run.results)

    async def _keypad_summary_screen(self, results: list) -> None:
        from .engine import aggregate_per_key
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Keypad Lesson Summary", self.username or "")
        if not results:
            _safe_addstr(self.stdscr, 4, 4, "No drills completed.",
                         curses.color_pair(PAIR_DIM))
            _safe_addstr(self.stdscr, h - 2, 2, "Press any key to continue.",
                         curses.color_pair(PAIR_HINT) | B)
            self.stdscr.refresh()
            await self.read_key()
            return
        wpm = sum(r.wpm for r in results) / len(results)
        acc = sum(r.accuracy for r in results) / len(results) * 100
        agg = aggregate_per_key(results)
        per = agg["per_key_wpm"]
        goal = int(self.goals.get("wpm_target", 40))
        above = sum(1 for v in per.values() if v >= goal)
        best = sorted(per.items(), key=lambda kv: -kv[1])[:3]
        worst = sorted(per.items(), key=lambda kv: kv[1])[:3]
        rows = [
            f"Speed: {wpm:.0f} WPM",
            f"Accuracy: {acc:.0f}%",
            f"Keys Above {goal} WPM: {above}",
            "Best Keys: " + " ".join(k for k, _ in best),
            "Keys to Work on: " + " ".join(k for k, _ in worst),
        ]
        for i, row in enumerate(rows):
            _safe_addstr(self.stdscr, 4 + i, 4, row,
                         curses.color_pair(PAIR_DEFAULT) | B)
        _safe_addstr(self.stdscr, h - 2, 2, "Press any key to continue.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def run_tests(self):
        """Tests Menu: Practice / All-keys / Disk / Keypad / Help."""
        class _TestsItem:
            def __init__(self, title, action):
                self.title = title
                self.description = ""
                self._action = action

        async def go_practice():
            await self._test_session("practice")

        async def go_allkeys():
            await self._test_session("all")

        async def go_disk():
            await self._disk_test_session()

        async def go_keypad():
            await self._keypad_test_session()

        async def go_help():
            await self._alert(
                "The features of the Tests Menu are:\n\n"
                "Practice - is a test that includes only the keys that have been "
                "introduced in your lessons.\n"
                "All-keys - tests your skill on the entire keyboard.\n"
                "Disk - is a test using a file stored on the disk.\n"
                "Keypad - gives a test tallying several columns of numbers with "
                "the numeric keypad.\n"
                "Help - displays this screen."
            )

        items = [
            _TestsItem("Practice", go_practice),
            _TestsItem("All-keys", go_allkeys),
            _TestsItem("Disk", go_disk),
            _TestsItem("Keypad", go_keypad),
            _TestsItem("Help", go_help),
        ]
        await self._tt_submenu(
            title="Tests Menu", items=items,
            second_lines={
                "Practice": "Practice Test",
                "All-keys": "All-keys Test",
                "Disk": "Disk Test",
                "Keypad": "Keypad Test",
                "Help": "Information about Tests Menu",
            },
            parent_hint="Esc -> Main Menu",
        )

    async def _test_session(self, kind: str) -> None:
        from .content import INITIAL_TEST
        if kind == "all":
            title = "All-keys Test"
            lines = list(INITIAL_TEST)
        else:
            title = "Practice Test"
            lines = self._practice_test_lines()
        lesson = Lesson.from_lines(title, lines,
                                   "Tests work the same way as lessons.")
        await self._initial_test_intro_screen(lesson)
        await self._test_screen(lesson)

    def _practice_test_lines(self) -> list[str]:
        import random
        from .invaders import ORIGINAL_WORDS, WORDS
        allowed = set(self._learned_keys().lower())
        source = ORIGINAL_WORDS or WORDS
        # Keep only single words made exclusively of learned keys.
        words = [w for w in source
                 if 2 <= len(w) <= 12 and w.isalpha() and set(w.lower()) <= allowed]
        if len(words) < 10:
            from .content import INITIAL_TEST
            return list(INITIAL_TEST[:5])
        rng = random.Random()
        out = []
        for _ in range(6):
            out.append(" ".join(rng.choice(words) for _ in range(7)))
        return out

    async def _disk_test_session(self) -> None:
        from .content import read_tst
        from .lessons import available_lessons
        candidates = []
        seen = set()
        dirs = [Path.cwd(),
                Path(__file__).resolve().parent.parent,
                Path(__file__).resolve().parent / "data"]
        if getattr(self, "tst_dir", None):
            dirs.append(Path(self.tst_dir))
        for directory in dirs:
            if not directory.exists():
                continue
            for pat in ("*.TST", "*.tst"):
                for p in sorted(directory.glob(pat)):
                    if p in seen:
                        continue
                    seen.add(p)
                    lines = read_tst(p, self.settings.get("instructor_password", ""))
                    if lines:
                        candidates.append(Lesson.from_lines(
                            p.stem, lines, f"Loaded from {p.name}"))
        if not candidates:
            await self._alert("There are no test files.")
            return
        picked = await self._pick_from_list(
            candidates, title=f"Tests — Disk — {self.username or '(unnamed)'}",
            subtitle="Use ↑/↓ to pick a test; Enter to start; Esc back",
        )
        if not picked:
            return
        lesson = picked[0]
        await self._initial_test_intro_screen(lesson)
        await self._test_screen(lesson)

    async def _keypad_test_session(self) -> None:
        from .content import get_keypad_test_lines
        from .engine import aggregate_per_key
        lesson = Lesson.from_lines(
            "Keypad Test", get_keypad_test_lines(),
            "Type the lines in the top box.  End each line with '+'.")
        await self._initial_test_intro_screen(lesson)
        run = LessonRun(lesson=lesson)
        await self._lesson_screen(lesson, run, show_summary=False)
        if not run.results:
            await self._alert("No drills completed.")
            return
        s = lesson_summary(run)
        s.update(aggregate_per_key(run.results))
        s["title"] = lesson.title
        from .history import append as hist_append
        hist_append(HistoryRecord.now("test", lesson.title, s,
                                      user=self.username or ""), self.history_path)
        await self._keypad_summary_screen(run.results)

    async def _tests_view_scores(self):
        """List the most recent test sessions from history."""
        from .history import load_all, DEFAULT_HISTORY_PATH
        records = [r for r in load_all(self.history_path) if r.kind == "test"]
        records.sort(key=lambda r: r.ts, reverse=True)
        recent = records[:10]
        # Compute the overall average WPM across all test records so each
        # row can show a delta vs the user's typical pace.
        all_wpms = [r.detail.get("wpm_avg", r.detail.get("wpm", 0.0))
                    for r in records]
        avg_wpm = (sum(all_wpms) / len(all_wpms)) if all_wpms else 0.0
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "View test scores", self.username or "")
        _safe_addstr(self.stdscr, 3, 2, f"User: {self.username or '(unnamed)'}   "
                      f"History file: {self.history_path or DEFAULT_HISTORY_PATH}",
                      curses.color_pair(PAIR_DIM))
        _safe_addstr(self.stdscr, 4, 2,
                      f"Total tests: {len(records)}    Overall average WPM: {avg_wpm:.1f}",
                      curses.color_pair(PAIR_DIM))
        if not recent:
            _safe_addstr(self.stdscr, 6, 4, "No test sessions yet — take one with Practice Test!",
                          curses.color_pair(PAIR_HINT) | B)
        else:
            header = f"{'When':<19} {'Lesson':<24} {'WPM':>6} {'Acc%':>6} {'ΔWPM':>6} {'Goal':>5}"
            _safe_addstr(self.stdscr, 6, 4, header, curses.color_pair(PAIR_HINT) | B)
            _safe_addstr(self.stdscr, 7, 4, "-" * 76, curses.color_pair(PAIR_DIM))
            for i, r in enumerate(recent):
                import datetime
                try:
                    ts = datetime.datetime.fromtimestamp(r.ts).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts = "-"
                wpm = r.detail.get("wpm_avg", r.detail.get("wpm", 0.0))
                acc = r.detail.get("accuracy_avg", r.detail.get("accuracy", 0.0)) * 100
                goal = self.goals["wpm_target"]
                met = "✓" if wpm >= goal else "·"
                delta = wpm - avg_wpm
                # +5% / -5% dead-zone to avoid noisy micro-deltas
                d_color = PAIR_OK if delta > avg_wpm * 0.05 else (
                          PAIR_BAD if delta < -avg_wpm * 0.05 else PAIR_DIM)
                d_str = f"{delta:+5.1f}"
                _safe_addstr(self.stdscr, 7 + i, 4,
                              f"{ts:<19} {r.label[:24]:<24} "
                              f"{wpm:>6.1f} {acc:>6.1f} {d_str:>6} {met:>5}",
                              curses.color_pair(
                                  PAIR_OK if wpm >= goal else PAIR_DEFAULT))
                # Re-overlay the delta in its own colour at the right column.
                _safe_addstr(self.stdscr, 7 + i, 4 + 19 + 1 + 24 + 1 + 6 + 1 + 6,
                              d_str, curses.color_pair(d_color))
        _safe_addstr(self.stdscr, h - 2, 4, "Press any key to return.",
                      curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def run_options(self):
        """Options Menu: WPM / Time / Drills / Sound / Name / Intro / Help."""
        class _OptItem:
            def __init__(self, title, description, action):
                self.title = title
                self.description = description
                self._action = action

        while True:
            wpm_idx = int(self.settings.get("wpm_goal_index", 3))
            time_idx = int(self.settings.get("practice_goal_index", 2))
            wpm_label = settings_mod.describe_range(settings_mod.speed_range(wpm_idx))
            time_label = settings_mod.describe_range(settings_mod.practice_range(time_idx))
            items = [
                _OptItem("WPM", f"Speed goal: {wpm_label} WPM", self._option_wpm),
                _OptItem("Time", f"Practice goal: {time_label} hours/week", self._option_time),
                _OptItem("Drills", f"{self.drills_per_lesson} drills per lesson", self._option_drills),
                _OptItem("Sound", f"{'On' if self.sound.enabled else 'Off'} "
                                  f"({self.sound.backend_name()})", self._option_sound),
                _OptItem("Name", f"Change your name ({self.username or '(unnamed)'})",
                         self._option_name),
                _OptItem("Intro", "Review Typing Tutor IV introduction", self._option_intro),
                _OptItem("Help", "Information about Options Menu", self._option_help),
            ]
            picked = await self.horizontal_menu(
                title="Options Menu", items=items,
                second_lines={
                    "WPM": "Change speed goal",
                    "Time": "Adjust practice goal",
                    "Drills": "Change duration of lessons",
                    "Sound": "Turn sound on and off",
                    "Name": "Change your name",
                    "Intro": "Review Typing Tutor IV introduction",
                    "Help": "Information about Options Menu",
                },
                parent_hint="Esc -> Main Menu",
            )
            if picked is None:
                return
            await picked._action()

    async def _option_wpm(self):
        idx = int(self.settings.get("wpm_goal_index", 3))
        items = [(settings_mod.describe_range(rng), "") for rng in settings_mod.SPEED_RANGES]
        choice = await self._choose_dialog(
            title="WPM", header="Change speed goal",
            items=items,
            status=f"Current goal: {settings_mod.describe_range(settings_mod.speed_range(idx))} WPM",
        )
        if choice is None:
            return
        new_idx = [settings_mod.describe_range(r) for r in settings_mod.SPEED_RANGES].index(choice)
        self.settings["wpm_goal_index"] = new_idx
        self.goals["wpm_target"] = settings_mod.speed_range(new_idx)[0]
        self._save_settings()
        await self._alert(f"Speed goal set to {settings_mod.describe_range(settings_mod.speed_range(new_idx))} WPM.")

    async def _option_time(self):
        idx = int(self.settings.get("practice_goal_index", 2))
        items = [(settings_mod.describe_range(rng), "") for rng in settings_mod.PRACTICE_RANGES]
        choice = await self._choose_dialog(
            title="Time", header="Adjust practice goal",
            items=items,
            status=f"Current goal: {settings_mod.describe_range(settings_mod.practice_range(idx))} hours/week",
        )
        if choice is None:
            return
        new_idx = [settings_mod.describe_range(r) for r in settings_mod.PRACTICE_RANGES].index(choice)
        self.settings["practice_goal_index"] = new_idx
        self.goals["practice_hours"] = settings_mod.practice_range(new_idx)[0]
        self._save_settings()
        await self._alert(f"Practice goal set to {settings_mod.describe_range(settings_mod.practice_range(new_idx))} hours/week.")

    async def _option_drills(self):
        cur = self.drills_per_lesson
        items = [(f"{n:3d}", "") for n in settings_mod.DRILL_CHOICES]
        choice = await self._choose_dialog(
            title="Drills", header="Select the number of drills in a lesson",
            items=items, status=f"Current: {cur} drills per lesson",
        )
        if choice is None:
            return
        n = int(choice.strip())
        self.drills_per_lesson = n
        self.settings["drills_per_lesson"] = n
        self._save_settings()
        await self._alert(f"Lessons now contain {n} drills.")

    async def _option_sound(self):
        choice = await self._choose_dialog(
            title="Sound", header="Choose whether you want sound in this program",
            items=[("Sound", "beeps and tones on"), ("No sound", "silent operation")],
            status=f"Current: {'Sound' if self.sound.enabled else 'No sound'}",
        )
        if choice is None:
            return
        self.sound.enabled = (choice == "Sound")
        self.settings["sound_enabled"] = self.sound.enabled
        self._save_settings()
        if self.sound.enabled:
            self.sound.play(SoundEvent.DRILL_COMPLETE)
        await self._alert(f"Sound {'enabled' if self.sound.enabled else 'disabled'}.")

    async def _option_name(self):
        _set_cursor(1)
        name = await self.read_line(prompt="Please type your name.. ")
        _set_cursor(0)
        if name:
            self.username = name
            self.settings["username"] = name
            self._save_settings()
            await self._alert(f"Name changed to {name}.")

    async def _option_intro(self):
        try:
            await self._intro_pages()
        except _UserCancelled:
            pass

    async def _option_help(self):
        await self._alert(
            "The features of the Options Menu are:\n\n"
            "WPM - lets you adjust your goal for the typing speed you wish to achieve.\n"
            "Time - allows you to change your planned practice schedule.\n"
            "Drills - changes the number of drills in a lesson.\n"
            "Sound - turns the sound on or off.\n"
            "Name - allows you to edit your name.\n"
            "Intro - lets you reread the Typing Tutor IV introduction.\n"
            "Help - displays this screen."
        )

    # ---- instructor mode ---------------------------------------------
    async def _instructor_login(self, supplied: Optional[str] = None) -> bool:
        expected = str(self.settings.get("instructor_password", "KRIYA"))
        if supplied is not None:
            return supplied.strip().upper() == expected.upper()
        _set_cursor(1)
        pw = await self.read_line(prompt="Please enter your password.. ")
        _set_cursor(0)
        return bool(pw) and pw.strip().upper() == expected.upper()

    async def _instructor_menu(self) -> None:
        class _Item:
            def __init__(self, title, description, action):
                self.title = title
                self.description = description
                self._action = action

        while True:
            items = [
                _Item("Encrypt", "encrypt a test file on disk", self._instructor_encrypt),
                _Item("Reports", "student results and progress", self._instructor_reports_menu),
                _Item("Password", "change teacher password", self._instructor_password),
                _Item("Delete", "remove a student from history", self._instructor_delete),
                _Item("Help", "information about Instructor Mode", self._instructor_help),
                _Item("Quit", "exit Typing Tutor IV", lambda: None),
            ]
            picked = await self.horizontal_menu(
                title="Instructor Mode", items=items,
                second_lines={
                    "Encrypt": "Encrypt a test file on disk",
                    "Reports": "Reports Menu",
                    "Password": "Change teacher password",
                    "Delete": "Remove a student from history",
                    "Help": "Information about Main Menu",
                    "Quit": "Exit Typing Tutor IV",
                },
                parent_hint="Esc -> Quit",
            )
            if picked is None:
                return
            if picked.title == "Quit":
                return
            await picked._action()

    async def _instructor_reports_menu(self) -> None:
        class _Item:
            def __init__(self, title, action):
                self.title = title
                self.description = ""
                self._action = action

        async def go_help():
            await self._alert(
                "The features of the Reports Menu are:\n\n"
                "Composite - gives a summary report of all students on the disk "
                "for a disk test.\n"
                "Progress - displays a Progress Report on an individual student.\n"
                "Speed - displays a Speed Graph for an individual student.\n"
                "Accuracy - displays an Accuracy Graph for an individual student.\n"
                "Help - displays this screen."
            )

        items = [
            _Item("Composite", self._instructor_composite),
            _Item("Progress", lambda: self._instructor_student_report("progress")),
            _Item("Speed", lambda: self._instructor_student_report("speed")),
            _Item("Accuracy", lambda: self._instructor_student_report("accuracy")),
            _Item("Help", go_help),
        ]
        await self._tt_submenu(
            title="Reports Menu", items=items,
            second_lines={
                "Composite": "Summary of disk test for all students",
                "Progress": "Progress Report",
                "Speed": "Speed Graph",
                "Accuracy": "Accuracy Graph",
                "Help": "Information about Reports Menu",
            },
            parent_hint="Esc -> Instructor Mode",
        )

    async def _instructor_student_report(self, kind: str) -> None:
        from .history import list_users
        students = list_users(self.history_path)
        if not students:
            await self._alert("There are no students in the history file.")
            return
        choice = await self._choose_dialog(
            title="Instructor Reports",
            header="Select a student",
            items=[(name, "") for name in students],
            status="..press Enter to select.   Esc = cancel.",
        )
        if choice is None:
            return
        self.report_user = choice
        try:
            if kind == "progress":
                await self._reports_progress()
            elif kind == "speed":
                await self._reports_speed()
            else:
                await self._reports_accuracy()
        finally:
            self.report_user = None

    async def _instructor_composite(self) -> None:
        from .history import load_all
        import datetime
        records = [r for r in load_all(self.history_path) if r.kind == "test"]
        records.sort(key=lambda r: r.ts, reverse=True)
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Composite Report", self.username or "")
        header = (f"{'Student':<16}{'Test':<22}{'Date':<12}"
                  f"{'WPM':>7}{'Acc%':>7}")
        _safe_addstr(self.stdscr, 3, 2, header, curses.color_pair(PAIR_HINT) | B)
        y = 4
        if not records:
            _safe_addstr(self.stdscr, y, 4, "There are no test records.",
                         curses.color_pair(PAIR_DIM))
        for r in records:
            if y >= h - 3:
                break
            try:
                date = datetime.datetime.fromtimestamp(r.ts).strftime("%m-%d-%y")
            except Exception:
                date = "-"
            d = r.detail or {}
            wpm = d.get("wpm_avg", d.get("wpm", 0.0))
            acc = d.get("accuracy_avg", d.get("accuracy", 0.0)) * 100
            line = (f"{(r.user or '(unnamed)')[:15]:<16}{r.label[:21]:<22}"
                    f"{date:<12}{wpm:>7.1f}{acc:>7.1f}")
            _safe_addstr(self.stdscr, y, 2, line, curses.color_pair(PAIR_DEFAULT))
            y += 1
        _safe_addstr(self.stdscr, h - 2, 2, "Press any key to return.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def _instructor_encrypt(self) -> None:
        from .content import encrypt_tst
        _set_cursor(1)
        raw = await self.read_line(prompt="Test file to encrypt: ")
        _set_cursor(0)
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            await self._alert(f"File not found: {path}")
            return
        choice = await self._choose_dialog(
            title="Encrypt",
            header="Encrypting a test file cannot be undone. Continue?",
            items=[("Yes, encrypt", str(path)), ("No", "cancel")],
            status="..press Enter to select.",
        )
        if choice != "Yes, encrypt":
            return
        ok = encrypt_tst(path, self.settings.get("instructor_password", "KRIYA"))
        await self._alert("Encrypting file..." if ok else "Could not encrypt file.")

    async def _instructor_password(self) -> None:
        ok = await self._instructor_login(None)
        if not ok:
            await self._alert("Invalid password for Instructor Mode.")
            return
        _set_cursor(1)
        p1 = await self.read_line(prompt="Please type your new password.. ")
        p2 = await self.read_line(prompt="Re-enter new password.. ")
        _set_cursor(0)
        if not p1 or p1 != p2:
            await self._alert("Passwords do not match.")
            return
        self.settings["instructor_password"] = p1
        self._save_settings()
        await self._alert("Instructor password changed.")

    async def _instructor_delete(self) -> None:
        from .history import delete_user, list_users
        students = list_users(self.history_path)
        if not students:
            await self._alert("There are no students in the history file.")
            return
        choice = await self._choose_dialog(
            title="Delete",
            header="Select a student to remove",
            items=[(name, "") for name in students],
            status="..press Enter to select.   Esc = cancel.",
        )
        if choice is None:
            return
        confirm = await self._choose_dialog(
            title="Delete",
            header=f"Remove {choice} from the history file?",
            items=[("Yes, delete", "this cannot be undone"), ("No", "cancel")],
            status="..press Enter to select.",
        )
        if confirm != "Yes, delete":
            return
        n = delete_user(choice, self.history_path)
        hs = self._high_scores()
        hs.delete(choice)
        await self._alert(f"{choice} is being deleted...  ({n} records removed)")

    async def _instructor_help(self) -> None:
        await self._alert(
            "The features of the Main Menu are:\n\n"
            "Encrypt - allows encryption of a disk test.  Once a test is "
            "encrypted, it can no longer be understood except when taking a "
            "disk test.  There is no way to return an encrypted file to its "
            "previous state, so if you need the original file, make a copy "
            "of it first.\n"
            "Reports - is a menu that allows you to view student results on "
            "disk tests, or see the progress of individual students.\n"
            "Password - lets you change the code required to get into "
            "instructor mode.\n"
            "Delete - allows you to delete a student record from the history "
            "file.\n"
            "Help - displays this screen.\n"
            "Quit - exits this program."
        )

    async def _registration_screen(self) -> Optional[str]:
        while True:
            name = await self.read_line(prompt="Please type your name.. ",
                                        title="Registration")
            if name is None:
                return None
            if name:
                return name
            # Empty name: keep the registration screen up, like TT.EXE.

    # ---- boot screens (welcome + intro) -------------------------------
    async def _welcome_screen(self) -> Optional[str]:
        """Welcome dialog — choose Typing Tutor (R) IV or IT.

        Returns the chosen edition label ("IV"/"IT") or None on Esc.
        """
        items = [
            ("Typing Tutor (R) IV", "Keyboard instruction program (full features)"),
            ("Typing Tutor (R) IT", "Junior edition (simplified for beginners)"),
        ]
        return await self._choose_dialog(
            title="Welcome",
            header="Welcome to the Typing Tutor IV family.",
            items=items,
            status="..press Enter to select.   Esc = exit program.",
        )

    async def _intro_pages(self) -> None:
        """Multi-page Introduction.  Verbatim text from TT.HLP.

        Enter advances one page, Esc skips past everything.
        """
        pages: list[list[str]] = [
            [
                "Introduction",
                "",
                "Welcome to the Typing Tutor IV keyboard instruction program!",
                "This program will tailor a course that matches your goals,",
                "experience, and available practice time, to help you gain",
                "mastery of the keyboard.",
                "",
                "This introduction will explain the usage of the Typing Tutor",
                "IV program.  If you are new to computers, you should read the",
                "Typing Tutor IV user's manual before proceeding.",
            ],
            [
                "Introduction",
                "",
                "Experienced computer users may want to get right into the",
                "program and read the introduction later.  As the bottom line",
                "of this screen tells you, pressing the Esc (Escape) key will",
                "get you past the introduction.",
                "",
                "The Esc key is used throughout the program to get out of what",
                "you are doing and do something else.  You can always look to",
                "the bottom line to find out where Esc will take you.",
            ],
            [
                "Introduction",
                "",
                "The top line of each screen lets you know where you are in the",
                "program.  In the upper left corner is the name of the current",
                "screen, and your name is in the upper right corner.",
                "",
                "Selections of Typing Tutor IV features are made from menus.",
                "Each menu gives a list of program features to select from.",
                "One feature of every menu is called Help.  Selecting Help",
                "will get you information about the other features of that",
                "menu.",
            ],
            [
                "Introduction",
                "",
                "The Main Menu is the starting point for the selection of all",
                "the features of the program.  The selections available on the",
                "Main Menu are: Lessons, Tests, Reports, Options, Game, Help,",
                "and Quit.  Selecting any of these except Help or Quit will",
                "lead you to a secondary menu with more choices.  Selecting",
                "Help will give you a fuller description of all the choices on",
                "the current menu.",
            ],
            [
                "Introduction",
                "",
                "Help is available as an option on every menu.  Selecting each",
                "of the menus and reading Help is a good way to familiarize",
                "yourself with all of the features of the program.",
                "",
                "After reading this introduction you will be asked some",
                "questions about your goals in using this program, and your",
                "current skill level at the keyboard.  This information will",
                "be used to help create customized lessons and tests for you,",
                "and to give you meaningful feedback on your progress.  If you",
                "wish to revise your goals later, you can do so by selecting",
                "Options from the Main Menu.",
            ],
            [
                "Introduction",
                "",
                "The area where you will probably want to spend most of your",
                "time is in Practice Lessons.  To get to Practice Lessons, you",
                "should select Lessons from the Main Menu, and then Practice",
                "from the Lessons Menu.",
                "",
                "A lesson consists of a series of one-line drills.  Each drill",
                "appears in a box at the top of the screen with an arrow",
                "pointing up at the first character to be typed.  As you type",
                "the line, the arrow will move along the line pointing to the",
                "next character to be typed.  If you make a mistake, an arrow",
                "will appear above the line pointing down to the error.  At",
                "the end of a line type either space bar or Enter to complete",
                "the drill.",
            ],
            [
                "Introduction",
                "",
                "To monitor your progress with lessons, you will want to take",
                "Practice Tests.  The results of a Practice Test are recorded",
                "in your history file, and will appear on your personal",
                "Progress Report.  To get to Practice Test, select Tests from",
                "the Main Menu, and then Practice from the Tests Menu.",
                "",
                "Tests are taken in the same way as lessons, except that there",
                "are multiple lines instead of just one.  Type the character",
                "above the pointer, and space bar or Enter at the end of each",
                "line.",
            ],
            [
                "Introduction",
                "",
                "You will see your Progress Report when you exit from the",
                "program, but you can also select it by choosing Reports from",
                "the Main Menu, and then Progress.  Also from the Reports",
                "Menu, you can view your Speed and Accuracy Graphs.  These",
                "graphs show how you are doing on each key, and compare the",
                "current session's data with your history.",
                "",
                "You can take a break from lessons and tests and play the",
                "Letter Invaders game.  It is fast-paced, fun, and when you",
                "get back to lessons you will find that it sharpens your typing",
                "skills too!  Letter Invaders allows you to play with just the",
                "keys you have learned in your lessons (it does assume you have",
                "learned the home row keys 'ASDF' and 'JKL;'), so you get a",
                "game matched to your current skill level.",
            ],
        ]
        for i, lines in enumerate(pages):
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _safe_addstr(self.stdscr, 1, 2, "Introduction",
                         curses.color_pair(PAIR_TITLE) | A)
            _safe_addstr(self.stdscr, 1, w - 12,
                         self.username or "(unnamed)",
                         curses.color_pair(PAIR_DIM))
            # Body of the page
            box_top, box_left, box_h = 4, 4, min(len(lines) + 2, h - 8)
            box_w = min(72, w - 8)
            try:
                self.stdscr.addstr(box_top - 1, box_left - 1,
                                   "+" + "-" * (box_w + 1) + "+",
                                   curses.color_pair(PAIR_DEFAULT))
                for r in range(box_h):
                    self.stdscr.addstr(box_top + r, box_left - 1, "|",
                                       curses.color_pair(PAIR_DEFAULT))
                    self.stdscr.addstr(box_top + r, box_left + box_w, "|",
                                       curses.color_pair(PAIR_DEFAULT))
                self.stdscr.addstr(box_top + box_h, box_left - 1,
                                   "+" + "-" * (box_w + 1) + "+",
                                   curses.color_pair(PAIR_DEFAULT))
            except curses.error:
                pass
            for j, line in enumerate(lines):
                attr = (curses.color_pair(PAIR_TITLE) | A) if j == 0 \
                    else curses.color_pair(PAIR_DEFAULT)
                try:
                    self.stdscr.addstr(box_top + 1 + j, box_left + 2, line, attr)
                except curses.error:
                    pass
            # Page indicator
            _safe_addstr(self.stdscr, h - 3, 4,
                          f"Page {i + 1} of {len(pages)}",
                          curses.color_pair(PAIR_HINT))
            _safe_addstr(self.stdscr, h - 2, 4,
                          "Enter = next page   Esc = skip introduction",
                          curses.color_pair(PAIR_HINT) | A)
            self.stdscr.refresh()
            # Wait for Enter / Esc
            self.stdscr.nodelay(False)
            while True:
                ch = self.stdscr.getch()
                if ch in (curses.KEY_ENTER, 10, 13, " ", 32):
                    break
                if ch in (27, 3):
                    return

    async def _beginner_screen(self) -> Optional[str]:
        """TT's first-run 'Where would you like to begin..?' dialog.

        Returns the chosen action label or None on Esc (which then routes
        back to the main menu).
        """
        return await self._choose_dialog(
            title="Begin",
            header="Where would you like to begin..",
            items=[
                ("Practice Lesson", "start a one-on-one typing lesson"),
                ("Practice Test",   "take the Initial Test for a baseline"),
                ("Main Menu",       "browse the full menu"),
            ],
            status="..press Enter to select highlighted item.",
        )

    async def _choose_dialog(self, *, title: str, header: str,
                              items: list, status: str) -> Optional[str]:
        """TT.EXE-style centered dialog with a nested item frame."""
        if not items:
            return None
        idx = 0
        labels = [label for label, _ in items]
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, title, self.username or "")
            inner_w = max(20, max((len(x) for x in labels), default=10) + 4)
            box_w = max(inner_w + 8, min(66, w - 8))
            inner_h = len(items) + 2
            box_h = min(h - 4, inner_h + 5)
            inner_h = min(inner_h, box_h - 5)
            top = max(2, (h - box_h) // 2)
            left = max(2, (w - box_w) // 2)
            _box(self.stdscr, top, left, box_h, box_w)
            hdr = header.rstrip()
            if not hdr.endswith(("..", "?", "!", ".")):
                hdr += ".."
            _safe_addstr(self.stdscr, top + 1, left + 3,
                         hdr[: max(0, box_w - 6)],
                         curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
            inner_top = top + 3
            inner_left = left + max(2, (box_w - inner_w) // 2)
            _box(self.stdscr, inner_top, inner_left, inner_h, inner_w)
            for i, label in enumerate(labels):
                if i >= inner_h - 1:
                    break
                _selected_row(self.stdscr, inner_top + 1 + i,
                              inner_left + 1, inner_w - 2, label,
                              i == idx, center=True)
            if status:
                _safe_addstr(self.stdscr, top + 3 + inner_h, left + 2,
                             status[: max(0, box_w - 4)],
                             curses.color_pair(PAIR_DEFAULT))
            _center(self.stdscr, h - 2, "Esc = cancel",
                    curses.color_pair(PAIR_DEFAULT))
            self.stdscr.refresh()
            ch = self.stdscr.getch()
            if ch in (curses.KEY_UP, curses.KEY_LEFT, "k", "K", "h", "H"):
                idx = (idx - 1) % len(items)
            elif ch in (curses.KEY_DOWN, curses.KEY_RIGHT, "j", "J", "l", "L",
                        " ", 32):
                idx = (idx + 1) % len(items)
            elif ch in (curses.KEY_ENTER, 10, 13):
                return labels[idx]
            elif ch in (27, 3):
                return None

    async def _date_confirm_screen(self) -> bool:
        """TT's 'Is today's date X?' question.  Returns True on Yes (default)."""
        import datetime
        today = datetime.date.today().strftime("%m-%d-%y")
        choice = await self._choose_dialog(
            title="Date",
            header=f"Is today's date {today}?",
            items=[
                ("Yes", f"Use today's date {today}"),
                ("No",  "Re-enter your name to start over"),
            ],
            status="..press Enter to select highlighted item.   Esc = exit program.",
        )
        return choice == "Yes"

    async def _goals_question_screen(self) -> None:
        """Boot-time goals: TT asks for a speed goal, then a practice goal."""
        idx = int(self.settings.get("wpm_goal_index", 3))
        choice = await self._choose_dialog(
            title="Speed Goal",
            header=("Select the minimum speed range that you would like to achieve"),
            items=[(settings_mod.describe_range(r), "") for r in settings_mod.SPEED_RANGES],
            status=f"..press Enter to select highlighted item.   Current: "
                   f"{settings_mod.describe_range(settings_mod.speed_range(idx))}",
        )
        if choice:
            new_idx = [settings_mod.describe_range(r)
                       for r in settings_mod.SPEED_RANGES].index(choice)
            self.settings["wpm_goal_index"] = new_idx
            self.goals["wpm_target"] = settings_mod.speed_range(new_idx)[0]
            self._save_settings()

        idx = int(self.settings.get("practice_goal_index", 2))
        choice = await self._choose_dialog(
            title="Practice Goal",
            header=("Select the minimum number of hours that you intend to "
                    "practice in a normal week"),
            items=[(settings_mod.describe_range(r), "")
                   for r in settings_mod.PRACTICE_RANGES],
            status=f"..press Enter to select highlighted item.   Current: "
                   f"{settings_mod.describe_range(settings_mod.practice_range(idx))}",
        )
        if choice:
            new_idx = [settings_mod.describe_range(r)
                       for r in settings_mod.PRACTICE_RANGES].index(choice)
            self.settings["practice_goal_index"] = new_idx
            self.goals["practice_hours"] = settings_mod.practice_range(new_idx)[0]
            self._save_settings()

    async def _skill_level_screen(self) -> None:
        """Boot-time skill-level question."""
        choice = await self._choose_dialog(
            title="Student Information",
            header=("Select the background that best describes your "
                    "experience with finger positioning on the keyboard."),
            items=[
                ("Beginner",         "new to typing; learning the home row"),
                ("Two finger typist", "hunt-and-peck with two index fingers"),
                ("Touch typist",      "already touch-type all keys"),
            ],
            status="..press Enter to select highlighted item.   Esc = skip.",
        )
        if choice:
            self.skill_level = choice

    async def _initial_test_intro_screen(self, lesson: Lesson) -> None:
        paras = [
            "To create personalized lessons and tests an initial test is helpful.  "
            "An initial test also gives Typing Tutor IV a baseline for measuring "
            "your progress.",
            "For lessons and tests, a pointer will appear below the next character "
            "to be typed.  Keep your eyes on the screen and type exactly what is "
            "shown.  When the pointer is at the end of a line press either the "
            "space bar or the Enter key.",
            "If you make errors, a pointer will display above the incorrect "
            "character.  The backspace key can be used to correct errors.",
        ]
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Initial Test", self.username or "")
        lines: list[str] = []
        for para in paras:
            lines.extend(_wrap(para, max(30, w - 10)))
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
        _box_text(self.stdscr, 3, 3, min(h - 5, len(lines) + 2), w - 6,
                  lines, text_attr=curses.color_pair(PAIR_DEFAULT),
                  border_attr=curses.color_pair(PAIR_ACCENT))
        _center(self.stdscr, h - 1,
                "..press Enter to begin test.   Esc = back to menu.",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        self.stdscr.nodelay(False)
        while True:
            ch = self.stdscr.getch()
            if ch in (curses.KEY_ENTER, 10, 13):
                return
            if ch in (27, 3, "q", "Q"):
                raise _UserCancelled()

    async def run_reports(self):
        """Reports Menu: Progress / Speed / Accuracy / Help."""
        class _ReportsItem:
            def __init__(self, title, action):
                self.title = title
                self.description = ""
                self._action = action

        async def go_help():
            await self._alert(
                "The features of the Reports Menu are:\n\n"
                "Progress - is a tabular summary of your tests and lessons. "
                "For each lesson and test there is information about the number "
                "of keys that are faster than your goal, the average speed and "
                "accuracy, and a speed breakdown by key type.\n"
                "Speed - shows a WPM graph for each key, so you can analyze your "
                "strengths and weaknesses in detail.\n"
                "Accuracy - is a graph with the same layout as the speed graph, "
                "but it portrays your accuracy percentage for each key.\n"
                "Help - displays this screen."
            )

        items = [
            _ReportsItem("Progress", self._reports_progress),
            _ReportsItem("Speed", self._reports_speed),
            _ReportsItem("Accuracy", self._reports_accuracy),
            _ReportsItem("Help", go_help),
        ]
        await self._tt_submenu(
            title="Reports Menu", items=items,
            second_lines={
                "Progress": "Progress Report",
                "Speed": "Speed Graph",
                "Accuracy": "Accuracy Graph",
                "Help": "Information about Reports Menu",
            },
            parent_hint="Esc -> Main Menu",
        )

    def _report_records(self) -> list:
        from .history import load_all
        who = self.report_user if self.report_user is not None else (self.username or "")
        try:
            return [r for r in load_all(self.history_path)
                    if (not r.user) or r.user == who]
        except Exception:
            return []

    def _per_key_report(self):
        """Return (session_wpm, session_acc), (history_wpm, history_acc)."""
        records = [r for r in self._report_records() if r.kind == "drill"]

        def agg(rs):
            wsum, wn, csum, asum = {}, {}, {}, {}
            for r in rs:
                d = r.detail or {}
                for k, v in (d.get("per_key_wpm") or {}).items():
                    if v and v > 0:
                        wsum[k] = wsum.get(k, 0.0) + float(v)
                        wn[k] = wn.get(k, 0) + 1
                for k, v in (d.get("per_key_correct") or {}).items():
                    csum[k] = csum.get(k, 0) + int(v)
                for k, v in (d.get("per_key_attempts") or {}).items():
                    asum[k] = asum.get(k, 0) + int(v)
            wpm = {k: wsum[k] / wn[k] for k in wsum}
            acc = {k: 100.0 * csum.get(k, 0) / asum[k]
                   for k in asum if asum[k]}
            return wpm, acc

        session = [r for r in records if r.ts >= self.session_start]
        return agg(session), agg(records)

    @staticmethod
    def _key_class(ch: str) -> str:
        if ch.isdigit():
            return "number"
        if ch.isalpha() or ch in "';,./-":
            return "letter"
        return "symbol"

    def _speed_breakdown(self, detail: dict) -> tuple[float, float, float]:
        per = (detail or {}).get("per_key_wpm") or {}
        acc = {}
        for cls in ("letter", "number", "symbol"):
            vals = [v for k, v in per.items() if self._key_class(k) == cls]
            acc[cls] = (sum(vals) / len(vals)) if vals else 0.0
        return acc["letter"], acc["number"], acc["symbol"]

    async def _reports_progress(self):
        from .history import load_all
        records = self._report_records()
        tests = [r for r in records if r.kind == "test"][-8:]
        lessons = [r for r in records if r.kind == "lesson"][-8:]
        session_drills = [r for r in records
                          if r.kind == "drill" and r.ts >= self.session_start]
        hist_drills = [r for r in records if r.kind == "drill"]
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Progress Report", self.username or "")
        y = 3
        goal = int(self.goals.get("wpm_target", 40))
        header = (f"{'Type':<20}{'Date':<12}{'Keys>':>6}{'WPM':>7}"
                  f"{'Acc%':>7}   {'Letter':>6}{'Number':>7}{'Symbol':>7}")
        for section, rows in (("TESTS", tests), ("LESSONS", lessons)):
            if y >= h - 4:
                break
            _safe_addstr(self.stdscr, y, 2, section,
                         curses.color_pair(PAIR_PROMPT) | B)
            y += 1
            _safe_addstr(self.stdscr, y, 2, header,
                         curses.color_pair(PAIR_HINT) | B)
            y += 1
            if not rows:
                _safe_addstr(self.stdscr, y, 4, "(no records yet)",
                             curses.color_pair(PAIR_DIM))
                y += 1
                continue
            for r in rows:
                if y >= h - 3:
                    break
                d = r.detail or {}
                wpm = d.get("wpm_avg", d.get("wpm", 0.0))
                acc = d.get("accuracy_avg", d.get("accuracy", 0.0)) * 100
                per = d.get("per_key_wpm") or {}
                above = sum(1 for v in per.values() if v >= goal)
                letter, number, symbol = self._speed_breakdown(d)
                import datetime
                try:
                    date = datetime.datetime.fromtimestamp(r.ts).strftime("%m-%d-%y")
                except Exception:
                    date = "-"
                line = (f"{r.label[:19]:<20}{date:<12}{above:>6}{wpm:>7.1f}"
                        f"{acc:>7.1f}   {letter:>6.1f}{number:>7.1f}{symbol:>7.1f}")
                _safe_addstr(self.stdscr, y, 2, line,
                             curses.color_pair(PAIR_DEFAULT))
                y += 1
            y += 1
        # Session / history summary.
        def avg(rs, field):
            vals = [r.detail.get(field, 0) for r in rs if r.detail]
            return sum(vals) / len(vals) if vals else 0.0
        if y < h - 3:
            _safe_addstr(self.stdscr, y, 2, "SESSION / HISTORY",
                         curses.color_pair(PAIR_PROMPT) | B)
            y += 1
            _safe_addstr(
                self.stdscr, y, 4,
                f"Session: {len(session_drills)} drills, "
                f"{avg(session_drills, 'wpm'):.1f} WPM, "
                f"{avg(session_drills, 'accuracy') * 100:.1f}% accuracy",
                curses.color_pair(PAIR_DEFAULT))
            y += 1
            _safe_addstr(
                self.stdscr, y, 4,
                f"History: {len(hist_drills)} drills, "
                f"{avg(hist_drills, 'wpm'):.1f} WPM, "
                f"{avg(hist_drills, 'accuracy') * 100:.1f}% accuracy",
                curses.color_pair(PAIR_DEFAULT))
        _safe_addstr(self.stdscr, h - 2, 2, "Press any key to return.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def _reports_speed(self):
        from .invaders import KEY_ORDER
        (sw, _sa), (hw, _ha) = self._per_key_report()
        keys = [k for k in KEY_ORDER if k in sw or k in hw]
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Speed Graph", self.username or "")
        _safe_addstr(self.stdscr, 2, 4,
                     "█ THIS SESSION    ▓ HISTORY    ▒ BOTH",
                     curses.color_pair(PAIR_HINT) | B)
        if not keys:
            _safe_addstr(self.stdscr, 5, 4,
                         "No per-key data yet — take a lesson or test.",
                         curses.color_pair(PAIR_DIM))
            _safe_addstr(self.stdscr, h - 2, 2, "Press any key to return.",
                         curses.color_pair(PAIR_HINT) | B)
            self.stdscr.refresh()
            await self.read_key()
            return
        max_v = max([v for v in list(sw.values()) + list(hw.values())] + [1.0])
        max_v = max(max_v, float(self.goals.get("wpm_target", 40)))
        y = 4
        _safe_addstr(self.stdscr, y, 4,
                     f"{'Key':<4}{'Session':>10}  {'History':>10}   bars",
                     curses.color_pair(PAIR_HINT) | B)
        y += 1
        for k in keys:
            if y >= h - 3:
                break
            s_val = sw.get(k, 0.0)
            h_val = hw.get(k, 0.0)
            s_bar = _bar(s_val, 0, max_v, 8)
            h_bar = _bar(h_val, 0, max_v, 8)
            _safe_addstr(self.stdscr, y, 4, k,
                         curses.color_pair(PAIR_PROMPT) | B)
            _safe_addstr(self.stdscr, y, 9, s_bar,
                         curses.color_pair(PAIR_TITLE) | B)
            _safe_addstr(self.stdscr, y, 19, h_bar,
                         curses.color_pair(PAIR_OK) | B)
            _safe_addstr(self.stdscr, y, 30,
                         f"{s_val:6.1f}  {h_val:6.1f}",
                         curses.color_pair(PAIR_DEFAULT))
            y += 1
        _safe_addstr(self.stdscr, h - 2, 2,
                     f"Scale 0-{max_v:.0f} WPM.  Goal {self.goals.get('wpm_target', 40)} WPM.  "
                     "Press any key to return.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def _reports_accuracy(self):
        from .invaders import KEY_ORDER
        (_sw, sa), (_hw, ha) = self._per_key_report()
        keys = [k for k in KEY_ORDER if k in sa or k in ha]
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Accuracy Graph", self.username or "")
        _safe_addstr(self.stdscr, 2, 4,
                     "█ THIS SESSION    ▓ HISTORY    ▒ BOTH",
                     curses.color_pair(PAIR_HINT) | B)
        if not keys:
            _safe_addstr(self.stdscr, 5, 4,
                         "No per-key accuracy data yet — take a lesson or test.",
                         curses.color_pair(PAIR_DIM))
            _safe_addstr(self.stdscr, h - 2, 2, "Press any key to return.",
                         curses.color_pair(PAIR_HINT) | B)
            self.stdscr.refresh()
            await self.read_key()
            return
        y = 4
        _safe_addstr(self.stdscr, y, 4,
                     f"{'Key':<4}{'Session':>10}  {'History':>10}   bars",
                     curses.color_pair(PAIR_HINT) | B)
        y += 1
        for k in keys:
            if y >= h - 3:
                break
            s_val = sa.get(k, 0.0)
            h_val = ha.get(k, 0.0)
            s_bar = _bar(s_val, 0, 100, 8)
            h_bar = _bar(h_val, 0, 100, 8)
            _safe_addstr(self.stdscr, y, 4, k,
                         curses.color_pair(PAIR_PROMPT) | B)
            _safe_addstr(self.stdscr, y, 9, s_bar,
                         curses.color_pair(PAIR_TITLE) | B)
            _safe_addstr(self.stdscr, y, 19, h_bar,
                         curses.color_pair(PAIR_OK) | B)
            _safe_addstr(self.stdscr, y, 30,
                         f"{s_val:6.1f}% {h_val:6.1f}%",
                         curses.color_pair(PAIR_DEFAULT))
            y += 1
        _safe_addstr(self.stdscr, h - 2, 2,
                     "Scale 0-100%.  Press any key to return.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    def _learned_keys(self) -> str:
        keys = getattr(self, "learned_keys", "") or ""
        skill = getattr(self, "skill_level", "")
        if skill == "Touch typist":
            return KEY_ORDER
        if skill == "Two finger typist":
            return KEY_ORDER[:29]
        return keys or "asdfjkl;"

    def _high_scores(self) -> HighScores:
        return HighScores(getattr(self, "highscore_path", None))

    async def run_game(self):
        """Game Menu: Play / Scores / Help (TT.EXE menu 5)."""
        class _GameItem:
            def __init__(self, title, action):
                self.title = title
                self.description = ""
                self._action = action

        async def go_play():
            await self._play_letter_invaders()

        async def go_scores():
            await self._game_scores_screen()

        async def go_help():
            await self._alert(
                "The features of the Game Menu are:\n\n"
                "Play - starts the Letter Invaders typing instruction game.\n"
                "Scores - displays the all-time highest scores at Letter Invaders.\n"
                "Help - displays this screen.\n\n"
                "Letter Invaders allows you to play with just the keys you have\n"
                "learned in your lessons, so you get a game matched to your\n"
                "current skill level."
            )

        items = [
            _GameItem("Play", go_play),
            _GameItem("Scores", go_scores),
            _GameItem("Help", go_help),
        ]
        await self._tt_submenu(
            title="Game Menu", items=items,
            second_lines={
                "Play": "Letter Invaders (R)",
                "Scores": "Score board",
                "Help": "Information about Game Menu",
            },
            parent_hint="Esc -> Main Menu",
        )

    async def _play_letter_invaders(self):
        """Level -> players -> full Letter Invaders game."""
        level_choice = await self._choose_dialog(
            title="Level",
            header="Choose a level of play",
            items=[
                ("Practice Keys", "use only keys learned in lessons"),
                ("Full Keyboard", "all letters, digits and punctuation"),
            ],
            status="..press Enter to select highlighted item.   Esc = Game Menu.",
        )
        if level_choice is None:
            return
        level = 0 if level_choice.startswith("Practice") else 1

        players_choice = await self._choose_dialog(
            title="Players",
            header="Choose the number of players",
            items=[
                ("One", "single player"),
                ("Two", "two players alternate rounds"),
            ],
            status="..press Enter to select highlighted item.   Esc = Game Menu.",
        )
        if players_choice is None:
            return
        players = 1 if players_choice.startswith("One") else 2

        names = [self.username or "Player 1"]
        if players == 2:
            _set_cursor(1)
            p2 = await self.read_line(prompt="Player #2: Please type your name.. ")
            _set_cursor(0)
            if not p2:
                return
            names.append(p2)

        hs = self._high_scores()
        while True:
            game = LetterInvaders(
                level=level,
                players=players,
                names=names,
                learned_keys=self._learned_keys(),
            )
            outcome = await self._run_one_invaders_game(game, hs)
            if outcome == "quit":
                return
            choice = await self._game_over_menu(game, hs)
            if choice == "Play another game":
                continue
            if choice == "Practice Lesson":
                await self.run_lessons()
            return

    async def _run_one_invaders_game(self, game: LetterInvaders, hs: HighScores) -> str:
        from .history import game_record
        while True:
            if not await self._round_intro_screen(game):
                return "quit"
            if not await self._invaders_play_screen(game):
                return "quit"
            summary = game.end_round()
            await self._round_summary_screen(game, summary)
            if game.game_over:
                for p in range(game.players):
                    label = "letter_invaders_practice" if game.level == 0 else "letter_invaders_full"
                    game_record(
                        score=game.scores[p],
                        label=label,
                        detail={
                            "player": game.names[p],
                            "level": game.level,
                            "round": game.round,
                            "hits": game.hits[p],
                            "misses": game.misses[p],
                            "shield": game.shields[p],
                            "accuracy_bonus": game.accuracy_bonus if p == game.current_player else 0,
                        },
                        path=self.history_path,
                        user=game.names[p],
                    )
                for p in range(game.players):
                    if not game.eliminated[p] or game.scores[p] > 0:
                        hs.add(game.level, game.names[p], game.scores[p],
                               len(self._learned_keys()))
                return "over"
            # Choose the next turn.  Two-player games alternate each round;
            # eliminated players are skipped.
            cur = game.current_player
            other = 1 - cur
            if game.players == 1:
                game.next_round()
            elif not game.eliminated[cur] and not game.eliminated[other]:
                if cur == 0:
                    game.begin_turn(1, increment_round=False)
                else:
                    game.begin_turn(0, increment_round=True)
            elif game.eliminated[cur] and not game.eliminated[other]:
                game.begin_turn(other, increment_round=(cur == 1))
            elif not game.eliminated[cur] and game.eliminated[other]:
                game.begin_turn(cur, increment_round=True)
            else:
                return "over"

    async def _invaders_play_screen(self, game: LetterInvaders) -> bool:
        """Run one round.  Returns False when the player presses Esc."""
        loop = asyncio.get_event_loop()
        last = loop.time()
        self.stdscr.nodelay(True)
        try:
            while not game.round_over and not game.game_over:
                now = loop.time()
                dt = int((now - last) * 1000)
                last = now
                game.advance(dt)
                self._draw_invaders(game)
                ch = self.stdscr.getch()
                if ch in (27, 3):
                    return False
                if ch == curses.KEY_RESIZE:
                    continue
                if isinstance(ch, int) and 32 <= ch <= 126:
                    ev = game.type_char(chr(ch))
                    if ev.get("miss"):
                        self.sound.play(SoundEvent.GAME_MISS)
                    elif ev.get("hit"):
                        self.sound.play(SoundEvent.GAME_HIT)
                await asyncio.sleep(0.02)
        finally:
            self.stdscr.nodelay(False)
        if game.round_over:
            self.sound.play(SoundEvent.GAME_OVER if game.game_over else SoundEvent.DRILL_COMPLETE)
        return True

    def _draw_invaders(self, game: LetterInvaders) -> None:
        """TT.EXE-style 80x25 Letter Invaders screen."""
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        # Top line: round, score, user.  Row 1 is the dashed rule.
        _safe_addstr(self.stdscr, 0, 2, f"Round {game.round}",
                     curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        _safe_addstr(self.stdscr, 0, 28, f"Score: {game.scores[game.current_player]}",
                     curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        _safe_addstr(self.stdscr, 0, max(0, w - len(game.player_name) - 2),
                     game.player_name[:w - 4], curses.color_pair(PAIR_DIM))
        _safe_addstr(self.stdscr, 1, 0, "-" * max(0, w - 1),
                     curses.color_pair(PAIR_DIM))

        top = 2
        max_rows = max(1, h - 7)
        rows = game.render()[:max_rows]
        for y, row in enumerate(rows):
            _safe_addstr(self.stdscr, top + y, 0, row[:w - 1],
                         curses.color_pair(PAIR_DEFAULT))
        # Overlay words with TT's white/green/yellow colouring.
        for word in game.active:
            if not (0 <= word.y < len(rows)):
                continue
            x = max(0, word.x)
            if x >= w:
                continue
            typed = word.text[:word.typed]
            rest = word.text[word.typed:]
            if typed:
                _safe_addstr(self.stdscr, top + word.y, x, typed,
                             curses.color_pair(PAIR_OK) | curses.A_BOLD)
            if rest:
                base = PAIR_PROMPT if word.kind != 1 else PAIR_DEFAULT
                _safe_addstr(self.stdscr, top + word.y, x + len(typed), rest,
                             curses.color_pair(base))
        # Shield line: TT's ground row.
        sy = top + len(rows)
        _safe_addstr(self.stdscr, sy, 0, game.shield_bar()[:w - 1],
                     curses.color_pair(PAIR_ACCENT) | curses.A_BOLD)
        status = (f"Shield {game.shield}/{game.SHIELD_CELLS}   "
                  f"Words {game.round_spawned}/{game.max_words_per_round}   "
                  f"Hits {game.round_hits}   Misses {game.round_misses}   "
                  f"Accuracy {game.accuracy:.0f}%")
        _safe_addstr(self.stdscr, min(h - 2, sy + 1), 2, status[:w - 4],
                     curses.color_pair(PAIR_DEFAULT))
        _center(self.stdscr, h - 1, "Esc -> Main Menu",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()

    async def _round_intro_screen(self, game: LetterInvaders) -> bool:
        if game.round == 1:
            box1_paras = [
                "Nihilistic letters are attacking the English Language!  They aim "
                "to destroy literacy with random words.  Can you stop the crazed "
                "letters and save your language?",
                "Your strategy is to place your fingers on the home keys ('ASDF' "
                "and 'JKL;') and type the descending words before they can cause "
                "cultural confusion.",
            ]
            box2_paras = [
                "You score points for each word correctly typed.  The first letter "
                "of a word is worth 10 points, the second letter adds 20 more, the "
                "third letter 30 more, etc.  Each miss deducts 10 points.",
            ]
        elif game.round == 2:
            box1_paras = [
                "Watch out in round 2!  The invaders have a new tactic for "
                "syntactical disarray - Boomlets.  These babies come down fast, "
                "and they are worth 50 points when you stop them.",
            ]
            box2_paras = []
        elif game.round == 3:
            box1_paras = [
                "Your incredible defense of good grammar has forced the invaders "
                "to call in Word Ships for resupply.  Type a Word Ship while it "
                "races across the screen and score double the word value.",
            ]
            box2_paras = []
        else:
            box1_paras = ["The invasion continues!"]
            box2_paras = []
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, f"Round {game.round}", self.username or "")
        _safe_addstr(self.stdscr, 0, 28, f"Score: {game.score}",
                     curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        y = 3
        lines1: list[str] = []
        for para in box1_paras:
            lines1.extend(_wrap(para, max(30, w - 12)))
            lines1.append("")
        if lines1 and lines1[-1] == "":
            lines1.pop()
        box_h = min(h - 6 - y, len(lines1) + 2)
        if box_h >= 3:
            _box_text(self.stdscr, y, 4, box_h, w - 8, lines1,
                      text_attr=curses.color_pair(PAIR_DEFAULT),
                      border_attr=curses.color_pair(PAIR_ACCENT))
            y += box_h + 1
        if box2_paras:
            lines2: list[str] = []
            for para in box2_paras:
                lines2.extend(_wrap(para, max(30, w - 12)))
                lines2.append("")
            if lines2 and lines2[-1] == "":
                lines2.pop()
            box_h2 = min(h - 3 - y, len(lines2) + 3)
            if box_h2 >= 3:
                _box_text(self.stdscr, y, 4, box_h2, w - 8, lines2,
                          text_attr=curses.color_pair(PAIR_DEFAULT),
                          border_attr=curses.color_pair(PAIR_ACCENT))
                _center(self.stdscr, y + box_h2 - 2,
                        f"..Press Enter to begin Round {game.round}.",
                        curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        else:
            _center(self.stdscr, h - 3,
                    f"..Press Enter to begin Round {game.round}.",
                    curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        _center(self.stdscr, h - 1, "Esc -> Main Menu",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        while True:
            ch = await self.read_key()
            if ch in (curses.KEY_ENTER, 10, 13, 32):
                return True
            if ch in (27, 3):
                return False

    async def _round_summary_screen(self, game: LetterInvaders, summary: dict) -> None:
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, f"Round {game.round}", self.username or "")
        _safe_addstr(self.stdscr, 0, 28, f"Score: {summary['score']}",
                     curses.color_pair(PAIR_DEFAULT) | curses.A_BOLD)
        lines = []
        if game.players > 1:
            lines.append(f"Player {summary['player'] + 1}, {summary['player_name']}")
        lines += [
            f"Hits: {summary['hits']}",
            f"Misses: {summary['misses']}",
            f"Accuracy: {summary['accuracy']:.0f}%",
        ]
        if summary["accuracy_bonus"]:
            lines.append(f"Accuracy Bonus: {summary['accuracy_bonus']}")
        lines += ["", f"Score: {summary['score']}   "
                      f"Shield: {summary['shield']}/{game.SHIELD_CELLS}"]
        if summary.get("eliminated"):
            lines.append("The shield has fallen!")
        box_w = min(w - 8, 56)
        box_h = min(h - 6, len(lines) + 2)
        _box_text(self.stdscr, 3, max(2, (w - box_w) // 2), box_h, box_w,
                  lines, text_attr=curses.color_pair(PAIR_DEFAULT),
                  border_attr=curses.color_pair(PAIR_ACCENT))
        _center(self.stdscr, h - 2, "Press Enter to continue.",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        while True:
            ch = await self.read_key()
            if ch in (curses.KEY_ENTER, 10, 13, 32, 27):
                return

    async def _game_over_menu(self, game: LetterInvaders, hs: HighScores) -> Optional[str]:
        items = ["Play another game", "Practice Lesson", "Return to Main Menu"]
        idx = 0
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, "Letter Invaders (R)", self.username or "")
            score_lines = [f"Player {p + 1}, {game.names[p]}: {game.scores[p]}"
                           for p in range(game.players)]
            top_score = hs.top(game.level)[0].score if hs.top(game.level) else 0
            score_lines.append(f"Top score: {top_score}")
            _box_text(self.stdscr, 3, max(2, (w - 52) // 2), len(score_lines) + 2,
                      52, score_lines,
                      text_attr=curses.color_pair(PAIR_DEFAULT),
                      border_attr=curses.color_pair(PAIR_ACCENT))
            menu_top = 5 + len(score_lines)
            inner_w = max(len(x) for x in items) + 6
            inner_left = max(2, (w - inner_w) // 2)
            if menu_top + len(items) + 2 < h - 2:
                _box(self.stdscr, menu_top, inner_left,
                     len(items) + 2, inner_w)
                for i, label in enumerate(items):
                    _selected_row(self.stdscr, menu_top + 1 + i,
                                  inner_left + 1, inner_w - 2, label,
                                  i == idx, center=True)
            _center(self.stdscr, h - 2,
                    "..press Enter to select highlighted item.",
                    curses.color_pair(PAIR_DEFAULT))
            self.stdscr.refresh()
            ch = await self.read_key()
            if ch in (curses.KEY_UP, curses.KEY_LEFT, "k", "K", "h", "H"):
                idx = (idx - 1) % len(items)
            elif ch in (curses.KEY_DOWN, curses.KEY_RIGHT, "j", "J", "l", "L",
                        " ", 32):
                idx = (idx + 1) % len(items)
            elif ch in (curses.KEY_ENTER, 10, 13):
                return items[idx]
            elif ch in (27, 3):
                return None

    async def _game_scores_screen(self) -> None:
        hs = self._high_scores()
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Letter Invaders - Top Scores", self.username or "")
        y = 3
        for level, heading in ((0, "Practice Keys"), (1, "Full Keyboard")):
            entries = hs.top(level)
            lines = [heading + " - Top Scores",
                     f"{'Rank':<5}{'Name':<28}{'Score':>8}   {'Date':<9}"]
            if not entries:
                lines.append("(no scores yet)")
            else:
                for i, e in enumerate(entries, 1):
                    lines.append(f"{i:<5}{e.name[:26]:<28}{e.score:>8}   {e.date:<9}")
            box_h = len(lines) + 2
            if y + box_h >= h - 2:
                break
            _box_text(self.stdscr, y, 2, box_h, w - 4, lines,
                      text_attr=curses.color_pair(PAIR_DEFAULT),
                      border_attr=curses.color_pair(PAIR_ACCENT))
            y += box_h + 1
        _center(self.stdscr, h - 2, "Press any key to return.",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        await self.read_key()

    async def run_help(self):
        """Main Menu Help — TT.HLP text in a green frame."""
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Help", self.username or "")
        lines: list[str] = []
        for para in MAIN_HELP.split("\n\n"):
            lines.extend(_wrap(para, max(20, w - 10)))
            lines.append("")
        _box_text(self.stdscr, 3, 3, min(h - 5, len(lines) + 2), w - 6,
                  lines, text_attr=curses.color_pair(PAIR_DEFAULT),
                  border_attr=curses.color_pair(PAIR_ACCENT))
        _center(self.stdscr, h - 2, "Press any key to return.",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        await self.read_key()

    # ---- helpers ---------------------------------------------------
    def _save_lesson_summary(self, lesson: Lesson, run: LessonRun):
        summary = lesson_summary(run)
        summary["title"] = lesson.title
        from .history import append as hist_append
        hist_append(HistoryRecord.now("lesson", lesson.title, summary,
                                      user=self.username or ""), self.history_path)
        for r in run.results:
            rec2 = HistoryRecord.now(
                "drill", lesson.title,
                {"wpm": r.wpm, "accuracy": r.accuracy,
                 "elapsed_s": r.elapsed_s,
                 "wrong": r.wrong_chars,
                 "typed": r.typed[:60],
                 "target": r.target[:160],
                 "per_key_errors": r.per_key_errors,
                 "per_key_wpm": r.per_key_wpm,
                 "per_key_attempts": r.per_key_attempts,
                 "per_key_correct": r.per_key_correct},
                user=self.username or "")
            hist_append(rec2, self.history_path)

    async def _pick_from_list(self, items: list, *, title: str, subtitle: str = ""):
        """Vertical TT-style list (test files, students, lessons)."""
        if not items:
            await self._alert("Nothing to show.")
            return []
        idx = 0
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, title, self.username or "")
            if subtitle:
                _safe_addstr(self.stdscr, 2, 2, subtitle[: max(0, w - 4)],
                             curses.color_pair(PAIR_DEFAULT))
            labels = [getattr(it, "title", str(it)) for it in items]
            box_w = min(max(40, max(len(x) for x in labels) + 12), w - 8)
            box_h = min(h - 8, len(items) + 2)
            top = 4
            left = max(2, (w - box_w) // 2)
            _box(self.stdscr, top, left, box_h, box_w)
            for i, it in enumerate(items):
                if i >= box_h - 1:
                    break
                label = labels[i]
                desc = getattr(it, "description", "") or ""
                _selected_row(self.stdscr, top + 1 + i, left + 1,
                              box_w - 2, label, i == idx)
                if desc:
                    _safe_addstr(self.stdscr, top + 1 + i,
                                 left + 3 + len(label), desc[: max(0, box_w - len(label) - 5)],
                                 curses.color_pair(PAIR_DIM))
            _center(self.stdscr, h - 2,
                    "↑/↓ choose   Enter select   Esc back",
                    curses.color_pair(PAIR_DEFAULT))
            self.stdscr.refresh()
            ch = await self.read_key()
            if ch in (curses.KEY_UP, "k", "K"):
                idx = (idx - 1) % len(items)
            elif ch in (curses.KEY_DOWN, "j", "J"):
                idx = (idx + 1) % len(items)
            elif ch in (curses.KEY_ENTER, 10, 13, "\n", "\r", " ", 32):
                return [items[idx]]
            elif ch in ("q", "Q", 27, 3):
                return []

    async def _lesson_screen(self, lesson: Lesson, run: LessonRun,
                             *, show_summary: bool = True) -> LessonRun:
        run.reset()
        drill = TypingDrill(target="")
        loop = self.loop

        while not run.done:
            current = run.current_drill
            if current is None:
                break
            drill.target = current.text
            drill.typed = ""
            drill.started_monotonic = None
            drill.finished_monotonic = None
            result = await self._drill_screen(drill, lesson, run)
            run.advance(result)
            if getattr(result, "aborted", False):
                break
        self.sound.play(SoundEvent.LESSON_COMPLETE)
        if show_summary:
            await self._lesson_summary_screen(lesson, run)
        return run

    async def _test_screen(self, lesson: Lesson):
        from .engine import aggregate_per_key
        run = LessonRun(lesson=lesson)
        await self._lesson_screen(lesson, run, show_summary=False)
        if not run.results:
            await self._alert("No drills completed.")
            return
        s = lesson_summary(run)
        s.update(aggregate_per_key(run.results))
        s["title"] = lesson.title
        from .history import append as hist_append
        hist_append(HistoryRecord.now("test", lesson.title, s,
                                      user=self.username or ""), self.history_path)
        await self._test_result_screen(lesson, s)

    async def _test_result_screen(self, lesson: Lesson, s: dict) -> None:
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, f"Results of {lesson.title}", self.username or "")
        rows = [
            f"Speed:      {s['wpm_avg']:.1f} WPM",
            f"Accuracy:   {s['accuracy_avg'] * 100:.1f}%",
            f"Drills:     {s['drills']}",
            f"Completed:  {s.get('completed', 0)}",
        ]
        if s.get("per_key_wpm"):
            above = sum(1 for v in s["per_key_wpm"].values()
                        if v >= self.goals.get("wpm_target", 40))
            rows.append(f"Keys above {self.goals.get('wpm_target', 40)} WPM: {above}")
            best = sorted(s["per_key_wpm"].items(), key=lambda kv: -kv[1])[:3]
            rows.append("Best keys:         " + "  ".join(f"{k}={v:.0f}" for k, v in best))
        for i, row in enumerate(rows):
            _safe_addstr(self.stdscr, 4 + i, 4, row, curses.color_pair(PAIR_DEFAULT))
        _safe_addstr(self.stdscr, h - 2, 2, "Press any key to continue.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def _drill_complete_banner(self, drill: "TypingDrill") -> None:
        """Render a 1-second celebration banner between drills."""
        res = drill.result()
        msg = (f"Drill complete  —  WPM {res.wpm:5.1f}  "
               f"Accuracy {res.accuracy*100:5.1f}%  "
               f"Errors {res.wrong_chars}")
        h, w = self.stdscr.getmaxyx()
        box_w = max(len(msg) + 4, 50)
        box_w = min(box_w, w - 8)
        box_h = 5
        box_top = (h - box_h) // 2
        box_left = (w - box_w) // 2
        try:
            self.stdscr.addstr(box_top,     box_left,
                               "+" + "-" * (box_w - 2) + "+",
                               curses.color_pair(PAIR_ACCENT) | A)
            for r in range(1, box_h - 1):
                self.stdscr.addstr(box_top + r, box_left, "|",
                                   curses.color_pair(PAIR_ACCENT))
                self.stdscr.addstr(box_top + r, box_left + box_w - 1, "|",
                                   curses.color_pair(PAIR_ACCENT))
            self.stdscr.addstr(box_top + box_h - 1, box_left,
                               "+" + "-" * (box_w - 2) + "+",
                               curses.color_pair(PAIR_ACCENT) | A)
        except curses.error:
            pass
        _safe_addstr(self.stdscr, box_top + 2, box_left + 2, msg,
                      curses.color_pair(PAIR_ACCENT) | A)
        _safe_addstr(self.stdscr, h - 2, 4, "Loading next drill...",
                      curses.color_pair(PAIR_DIM) | A)
        self.stdscr.refresh()
        import time
        time.sleep(1.0)

    async def _drill_screen(self, drill: TypingDrill, lesson: Lesson, run: LessonRun) -> DrillResult:
        """Live keystroke loop — TT.EXE's boxed drill layout."""
        loop = self.loop
        while True:
            _erase_screen(self.stdscr)
            h, w = self.stdscr.getmaxyx()
            _header(self.stdscr, lesson.title, self.username or "")
            total = len(lesson.drills)
            cur = run.current_index + 1
            elapsed = drill.elapsed_s

            # Top drill frame: one blank row for the down-arrow markers,
            # one text row, one row for the up-arrow pointer.
            box_w = max(30, w - 8)
            box_left = 4
            box_top = 3
            _box(self.stdscr, box_top, box_left, 5, box_w)
            text_y = box_top + 2
            statuses = drill.progress_chars()
            x = box_left + 4
            for i, status in enumerate(statuses):
                if x >= box_left + box_w - 2:
                    break
                ch = drill.target[i]
                if status == CharStatus.CORRECT:
                    attr = curses.color_pair(PAIR_OK) | curses.A_BOLD
                elif status == CharStatus.WRONG:
                    attr = curses.color_pair(PAIR_BAD) | curses.A_BOLD
                elif status == CharStatus.CURSOR:
                    attr = curses.color_pair(PAIR_PROMPT) | curses.A_BOLD
                else:
                    attr = curses.color_pair(PAIR_DEFAULT)
                _safe_addstr(self.stdscr, text_y, x, ch, attr)
                if status == CharStatus.WRONG:
                    _safe_addstr(self.stdscr, text_y - 1, x, "v",
                                 curses.color_pair(PAIR_BAD) | curses.A_BOLD)
                if status == CharStatus.CURSOR:
                    _safe_addstr(self.stdscr, text_y + 1, x, "^",
                                 curses.color_pair(PAIR_PROMPT) | curses.A_BOLD)
                x += 1

            # Current Focus Keys frame.
            unique_keys = sorted({c for c in drill.target if c.isalnum()})
            focus_line = "Current Focus Keys: " + " ".join(unique_keys[:14])
            if len(unique_keys) > 14:
                focus_line += f"  (+{len(unique_keys) - 14} more)"
            focus_top = box_top + 6
            _box(self.stdscr, focus_top, 4, 3, w - 8)
            _safe_addstr(self.stdscr, focus_top + 1, 8,
                         focus_line[: max(0, w - 8)],
                         curses.color_pair(PAIR_DEFAULT))

            # Speed / Accuracy / Time frame.
            stats_top = focus_top + 4
            _box(self.stdscr, stats_top, 4, 3, w - 8)
            correct = drill.correct_count
            wpm = (correct / 5.0) / (elapsed / 60.0) if elapsed > 0 else 0.0
            acc = (correct / len(drill.target)) if drill.target else 0.0
            _safe_addstr(self.stdscr, stats_top + 1, 8,
                         f"Speed: {wpm:5.1f} WPM",
                         curses.color_pair(PAIR_DEFAULT))
            _safe_addstr(self.stdscr, stats_top + 1, 36,
                         f"Accuracy: {acc * 100:5.1f}%",
                         curses.color_pair(PAIR_DEFAULT))

            _center(self.stdscr, h - 1, "Esc -> Main Menu",
                    curses.color_pair(PAIR_DEFAULT))
            self.stdscr.refresh()
            ch = await self.read_key()
            if ch in (27, 3):  # Esc / Ctrl-C
                res = drill.result()
                res.aborted = True
                return res
            elif ch in (curses.KEY_BACKSPACE, 127, 8, "\b"):
                drill.backspace()
            elif ch in (curses.KEY_ENTER, 10, 13, "\n", "\r"):
                if drill.typed == drill.target:
                    self.sound.play(SoundEvent.DRILL_COMPLETE)
                    return drill.result()
                continue
            elif isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                if len(drill.typed) < len(drill.target):
                    drill.push_char(ch, loop.time)
                    target_ch = drill.target[len(drill.typed) - 1]
                    self.sound.play(SoundEvent.KEYSTROKE if ch == target_ch
                                    else SoundEvent.ERROR)
            elif isinstance(ch, int) and 32 <= ch <= 126:
                if len(drill.typed) < len(drill.target):
                    c = chr(ch)
                    drill.push_char(c, loop.time)
                    target_ch = drill.target[len(drill.typed) - 1]
                    self.sound.play(SoundEvent.KEYSTROKE if c == target_ch
                                    else SoundEvent.ERROR)
            if drill.finished_monotonic is not None:
                self.sound.play(SoundEvent.DRILL_COMPLETE)
                await self._drill_complete_banner(drill)
                return drill.result()
            if len(drill.typed) >= len(drill.target):
                self.sound.play(SoundEvent.DRILL_COMPLETE)
                return drill.result()

    async def _lesson_summary_screen(self, lesson: Lesson, run: LessonRun):
        s = lesson_summary(run)
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        # Goal-met celebration — show a brief banner if all goals were met.
        goal_met = (s["wpm_avg"] >= self.goals["wpm_target"]
                    and s["accuracy_avg"] >= self.goals["accuracy_target"])
        if goal_met:
            await self._goal_met_banner(s)
        _header(self.stdscr, f"Lesson complete — {lesson.title}",
                self.username or "")
        rows = [
            f"Drills done:      {s['drills']}",
            f"Completed:        {s['completed']}",
            f"Average WPM:      {s['wpm_avg']:.1f}",
            f"Average accuracy: {s['accuracy_avg'] * 100:.1f}%",
            f"Total time:       {s['elapsed_s']:.0f}s",
        ]
        for i, r in enumerate(rows):
            _safe_addstr(self.stdscr, 3 + i, 4, r)
        # Per-drill breakdown — mirrors TT's test-results screen.
        # Show each drill's WPM and accuracy, with a small line chart.
        header_y = 3 + len(rows) + 1
        if run.results:
            _safe_addstr(self.stdscr, header_y, 4, "Per-drill breakdown",
                          curses.color_pair(PAIR_TITLE) | B)
            sub_header = "  drill  text                          WPM    Acc%   chart"
            _safe_addstr(self.stdscr, header_y + 1, 4, sub_header,
                          curses.color_pair(PAIR_HINT))
            max_wpm = max((r.wpm for r in run.results), default=1) or 1
            for i, r in enumerate(run.results):
                y = header_y + 2 + i
                if y >= h - 2:
                    break
                text_preview = r.target[:30] + ("…" if len(r.target) > 30 else "")
                col = PAIR_OK if r.accuracy >= 0.95 else \
                      PAIR_PROMPT if r.accuracy >= 0.85 else PAIR_BAD
                chart_w = int(r.wpm / max_wpm * 16) if max_wpm else 0
                chart = "█" * chart_w + "·" * (16 - chart_w)
                _safe_addstr(
                    self.stdscr, y, 4,
                    f"  {i + 1:<5} {text_preview:<30}  {r.wpm:>5.1f}  "
                    f"{r.accuracy * 100:>5.1f}   {chart}",
                    curses.color_pair(col),
                )
        _safe_addstr(self.stdscr, h - 2, 4, "Press any key to return to the menu.",
                     curses.color_pair(PAIR_HINT) | B)
        self.stdscr.refresh()
        await self.read_key()

    async def _goal_met_banner(self, summary: dict) -> None:
        """Show a brief goal-met celebration banner after a successful run."""
        self.sound.play(SoundEvent.LESSON_COMPLETE)
        msg = (f"★  GOAL MET!  WPM {summary['wpm_avg']:.1f} ≥ "
               f"{self.goals['wpm_target']:.0f},  Accuracy "
               f"{summary['accuracy_avg']*100:.1f}% ≥ "
               f"{self.goals['accuracy_target']*100:.0f}%  ★")
        h, w = self.stdscr.getmaxyx()
        box_w = max(len(msg) + 4, 60)
        box_w = min(box_w, w - 8)
        box_h = 5
        box_top = 1
        box_left = (w - box_w) // 2
        try:
            self.stdscr.addstr(box_top,     box_left,
                               "+" + "-" * (box_w - 2) + "+",
                               curses.color_pair(PAIR_TITLE) | A)
            for r in range(1, box_h - 1):
                self.stdscr.addstr(box_top + r, box_left,     "|",
                                   curses.color_pair(PAIR_TITLE))
                self.stdscr.addstr(box_top + r, box_left + box_w - 1, "|",
                                   curses.color_pair(PAIR_TITLE))
            self.stdscr.addstr(box_top + box_h - 1, box_left,
                               "+" + "-" * (box_w - 2) + "+",
                               curses.color_pair(PAIR_TITLE) | A)
        except curses.error:
            pass
        _safe_addstr(self.stdscr, box_top + 2, box_left + 2, msg,
                      curses.color_pair(PAIR_TITLE) | A)
        self.stdscr.refresh()
        import time
        time.sleep(2.0)

    async def _alert(self, msg: str):
        _erase_screen(self.stdscr)
        h, w = self.stdscr.getmaxyx()
        _header(self.stdscr, "Information", self.username or "")
        lines: list[str] = []
        for para in str(msg).split("\n"):
            lines.extend(_wrap(para, max(20, w - 12)) if para else [""])
        _box_text(self.stdscr, 4, 4, min(h - 6, len(lines) + 2), w - 8,
                  lines, text_attr=curses.color_pair(PAIR_DEFAULT),
                  border_attr=curses.color_pair(PAIR_ACCENT))
        _center(self.stdscr, h - 2, "Press any key to continue.",
                curses.color_pair(PAIR_DEFAULT))
        self.stdscr.refresh()
        await self.read_key()


def run(stdscr, lessons, history_path=None, sound=None):
    App(stdscr, lessons=lessons, history_path=history_path, sound=sound).run()
