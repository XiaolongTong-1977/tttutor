#!/usr/bin/env python3
"""Single-file launcher for tttutor.

Run from any directory with::

    python start.py              # launch the TUI
    python start.py --check      # verify environment and exit
    python start.py --init       # create config dir and exit
    python start.py --version    # print version and exit
    python start.py --reset      # wipe ~/.tttutor/history.jsonl and exit

The launcher inserts its own directory into ``sys.path`` so the package
can be discovered without a prior ``pip install -e .`` step.  It is
deliberately tiny and zero-dependency (stdlib only) so it works on any
Python 3.10+ environment, including a fresh conda or system Python.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

PACKAGE_NAME = "tttutor"
DEFAULT_HISTORY = Path.home() / ".tttutor" / "history.jsonl"


# ---------------------------------------------------------------------------
# Path setup — must run before any tttutor import
# ---------------------------------------------------------------------------

def _here() -> Path:
    return Path(__file__).resolve().parent


def _ensure_path() -> None:
    """Make sure ``import tttutor`` works regardless of cwd."""
    root = str(_here())
    if root not in sys.path:
        sys.path.insert(0, root)


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------

def cmd_tui(args: argparse.Namespace) -> int:
    """Launch the curses TUI. Default behaviour."""
    from tttutor.__main__ import main as tttutor_main
    extra = []
    if args.tst_dir:
        extra += ["--tst-dir", str(args.tst_dir)]
    if args.history:
        extra += ["--history", str(args.history)]
    if args.instructor is not None:
        extra.append("--instructor")
        if args.instructor:
            extra += ["--instructor-password", args.instructor]
    return tttutor_main(extra)


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
        sp = SoundPlayer(enabled=True)
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
    """Create the user's config directory and seed a friendly welcome."""
    from tttutor.history import DEFAULT_HISTORY_PATH
    DEFAULT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_HISTORY_PATH.exists():
        # Don't create a real history file yet; just touch its directory.
        # A future first drill run will append a real record.
        pass
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


def cmd_version(args: argparse.Namespace) -> int:
    """Print tttutor + Python + platform versions."""
    print(f"tttutor   : {__get_version()}")
    print(f"python    : {sys.version.split()[0]}")
    print(f"platform  : {sys.platform}")
    return 0


def __get_version() -> str:
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


# ---------------------------------------------------------------------------
# Top-level argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="start.py",
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
        help="Wipe ~/.tttutor/history.jsonl after a Y/N prompt.",
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


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        return cmd_version(args)
    if args.check:
        return cmd_check(args)
    if args.init:
        return cmd_init(args)
    if args.reset:
        return cmd_reset(args)
    return cmd_tui(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        # Curses raises this when the user presses Esc on the Quit screen
        # in a way that bypasses our exception handler.  Treat as a clean exit.
        raise SystemExit(0)
    except Exception as e:                                # noqa: BLE001
        # Show a friendly stack trace that points to the right docs.
        print(f"tttutor launcher failed: {e!r}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(1)
