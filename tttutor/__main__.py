"""Entry point — `python -m tttutor` (see also the ``tttutor`` command
and the source-tree ``start.py`` launcher, which share ``tttutor.cli``)."""
from __future__ import annotations

import sys

from .cli import main as _cli_main


def main(argv=None):
    return _cli_main(argv, prog="tttutor")


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        # Curses raises this when the user presses Esc on the Quit screen
        # in a way that bypasses our exception handler.  Treat as a clean exit.
        raise SystemExit(0)
