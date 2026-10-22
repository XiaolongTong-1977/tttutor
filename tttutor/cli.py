"""Shared CLI implementation for tttutor.

Used by both ``python -m tttutor`` (the pip-installed ``tttutor`` command)
and the source-tree ``start.py`` launcher, so both entry points expose
exactly the same options on every platform:

* TUI launch (default)      — ``cmd_tui``
* ``--check``               — environment diagnostics, no TTY required
* ``--init``                — create the config directory
* ``--reset [--yes]``       — wipe history / settings / high scores
* ``--version``             — print tttutor + Python versions
* ``--instructor [PWD]``    — Instructor Mode (optional password)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def get_version() -> str:
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            return version("tttutor")
        except PackageNotFoundError:
            pass
    except ImportError:
        pass
    try:
        from tttutor import __version__ as v
        return v
    except Exception:                                # noqa: BLE001
        return "0+unknown"


def cmd_version(args: argparse.Namespace) -> int:
    """Print tttutor + Python + platform versions."""
    print(f"tttutor   : {get_version()}")
    print(f"python    : {sys.version.split()[0]}")
    print(f"platform  : {sys.platform}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Verify Python version, curses, history dir, and audio backends."""
    print(f"Python   : {sys.version.split()[0]}")
    print(f"Platform : {sys.platform}")
    print(f"tty      : {os.isatty(0) and 'yes' or 'no'}")
    try:
        import curses        # noqa: F401
        print("curses   : ok (built into stdlib)")
    except ImportError as e:
        print(f"curses   : MISSING ({e})")
        return 1
    try:
        from tttutor.sound import SoundPlayer, pick_backend
        SoundPlayer(enabled=True)
        be = pick_backend()
        print(f"audio    : ok (backend: {be.name})")
    except Exception as e:  # noqa: BLE001
        print(f"audio    : error ({e!r})")

    from tttutor.history import DEFAULT_HISTORY_PATH
    print(f"history  : {DEFAULT_HISTORY_PATH}")
    print(f"          exists={DEFAULT_HISTORY_PATH.exists()} "
          f"parent_ok={DEFAULT_HISTORY_PATH.parent.is_dir() or 'will be created'}")
    try:
        from tttutor.lessons import available_lessons
        ls = available_lessons()
        print(f"lessons  : {len(ls)} bundled lessons, "
              f"{sum(len(l.drills) for l in ls)} drills total")
    except Exception as e:  # noqa: BLE001
        print(f"lessons  : error ({e!r})")
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Create the user's config directory."""
    from tttutor.history import DEFAULT_HISTORY_PATH
    DEFAULT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"Config directory ready: {DEFAULT_HISTORY_PATH.parent}")
    print(f"  history file will be: {DEFAULT_HISTORY_PATH}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Wipe history, settings and high scores after a Y/N prompt."""
    from tttutor.history import DEFAULT_HISTORY_PATH
    hist = Path(args.history) if args.history else DEFAULT_HISTORY_PATH
    targets = [hist, hist.with_name("settings.json"), hist.with_name("fzvf.json")]
    existing = [p for p in targets if p.exists()]
    if not existing:
        print(f"No history at {hist}; nothing to do.")
        return 0
    if not args.yes:
        try:
            ans = input(f"Wipe {hist} and its settings/scores? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("Aborted.")
            return 1
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1
    for p in existing:
        p.unlink()
        print(f"Wiped {p}.")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the curses TUI. Default behaviour."""
    import curses

    from tttutor.lessons import available_lessons
    lessons = available_lessons(args.tst_dir)
    if not lessons:
        print("No lessons available.", file=sys.stderr)
        return 1

    from tttutor.history import DEFAULT_HISTORY_PATH
    from tttutor.sound import SoundPlayer
    from tttutor.ui import App

    history_path = args.history or DEFAULT_HISTORY_PATH

    def curses_main(stdscr):
        try:
            App(stdscr,
                lessons=lessons,
                history_path=history_path,
                sound=SoundPlayer(),
                instructor=args.instructor is not None,
                instructor_password=args.instructor or None,
                tst_dir=args.tst_dir).run()
        except Exception:
            curses.endwin()
            raise

    try:
        curses.wrapper(curses_main)
    except KeyboardInterrupt:
        pass
    return 0


def build_parser(prog: str = "tttutor") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description="Launch tttutor (a modern terminal typing tutor).",
    )
    p.add_argument(
        "--tst-dir", type=Path, default=None,
        help="Directory of legacy .TST lesson files (passed through to "
             "the TUI).",
    )
    p.add_argument(
        "--history", type=Path, default=None,
        help="Path to JSONL history file (default: ~/.tttutor/history.jsonl).",
    )
    p.add_argument(
        "--check", action="store_true",
        help="Print environment diagnostics and exit (no TTY required).",
    )
    p.add_argument(
        "--init", action="store_true",
        help="Create config directory and exit.",
    )
    p.add_argument(
        "--reset", action="store_true",
        help="Wipe ~/.tttutor/history.jsonl and its settings/scores.",
    )
    p.add_argument(
        "--yes", action="store_true",
        help="With --reset, skip the Y/N prompt.",
    )
    p.add_argument(
        "--instructor", nargs="?", const="", default=None,
        metavar="PASSWORD",
        help="Start in Instructor Mode.  With no value, prompt for the "
             "teacher password (default: KRIYA).",
    )
    p.add_argument(
        "--version", action="store_true",
        help="Print tttutor + Python versions and exit.",
    )
    return p


def main(argv: "list[str] | None" = None, prog: str = "tttutor") -> int:
    """Parse ``argv`` and dispatch to the matching sub-command."""
    args = build_parser(prog).parse_args(argv)
    if args.version:
        return cmd_version(args)
    if args.check:
        return cmd_check(args)
    if args.init:
        return cmd_init(args)
    if args.reset:
        return cmd_reset(args)
    return cmd_tui(args)
