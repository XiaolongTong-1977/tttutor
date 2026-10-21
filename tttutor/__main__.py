"""Entry point — `python -m tttutor` or `start.py`."""
from __future__ import annotations

import argparse
import curses
import sys
from pathlib import Path

from .lessons import available_lessons
from .history import DEFAULT_HISTORY_PATH


def _parse(argv):
    p = argparse.ArgumentParser(
        prog="tttutor",
        description="Modern terminal typing tutor — pure Python, curses-based.",
    )
    p.add_argument(
        "--tst-dir",
        type=Path,
        default=None,
        help="Directory of legacy .TST lesson files (optional, one per file).",
    )
    p.add_argument(
        "--history",
        type=Path,
        default=None,
        help="Path to JSONL history file (default: ~/.tttutor/history.jsonl).",
    )
    p.add_argument(
        "--instructor", action="store_true",
        help="Start in Instructor Mode (asks for the teacher password).",
    )
    p.add_argument(
        "--instructor-password", default=None,
        help="Teacher password supplied non-interactively.",
    )
    return p.parse_args(argv)


def main(argv=None):
    args = _parse(argv)
    history_path = args.history or DEFAULT_HISTORY_PATH

    lessons = available_lessons(args.tst_dir)
    if not lessons:
        print("No lessons available.", file=sys.stderr)
        sys.exit(1)

    from .ui import App
    from .sound import SoundPlayer

    def curses_main(stdscr):
        try:
            App(stdscr,
                lessons=lessons,
                history_path=history_path,
                sound=SoundPlayer(),
                instructor=args.instructor,
                instructor_password=args.instructor_password,
                tst_dir=args.tst_dir).run()
        except Exception as exc:            # pragma: no cover
            curses.endwin()
            raise

    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
