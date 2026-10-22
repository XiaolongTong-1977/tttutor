#!/usr/bin/env python3
"""Single-file launcher for tttutor.

Run from any directory with::

    python start.py              # launch the TUI
    python start.py --check      # verify environment and exit
    python start.py --init       # create config dir and exit
    python start.py --version    # print version and exit
    python start.py --reset      # wipe ~/.tttutor/history.jsonl and exit

The launcher inserts its own directory into ``sys.path`` so the package
can be discovered without a prior ``pip install -e .`` step, then delegates
to ``tttutor.cli`` — the exact same implementation used by the pip-installed
``tttutor`` command, so both entry points accept the same options on any
Python 3.10+ environment, including a fresh conda, venv or system Python.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _here() -> Path:
    return Path(__file__).resolve().parent


def _ensure_path() -> None:
    """Make sure ``import tttutor`` works regardless of cwd."""
    root = str(_here())
    if root not in sys.path:
        sys.path.insert(0, root)


def main(argv: "list[str] | None" = None) -> int:
    _ensure_path()
    from tttutor.cli import main as cli_main
    return cli_main(argv, prog="start.py")


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
