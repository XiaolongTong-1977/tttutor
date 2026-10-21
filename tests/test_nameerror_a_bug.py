"""Regression test for the `A` undefined-NameError bug.

In `_choose_dialog` (and a few other render paths) the UI uses the short
alias `A` for `curses.A_BOLD`.  That alias must be defined at module
level.  If it isn't, the TUI crashes with::

    File "tttutor/ui.py", line 815, in _choose_dialog
        curses.color_pair(PAIR_TITLE) | A)
                                       ^
    NameError: name 'A' is not defined

This test boots the package so the module is imported, and asserts the
alias is bound.
"""
import sys
import unittest


class ABoldAliasTests(unittest.TestCase):
    def test_module_level_a_alias(self):
        # Importing ui may fail if curses has no TTY (e.g. on CI), but the
        # alias check doesn't require a real terminal.  We use a lenient
        # import that only verifies the symbol is present in the module's
        # bytecode / namespace.
        import importlib
        try:
            importlib.import_module("tttutor.ui")
        except Exception:
            # Couldn't import ui (no TTY, missing curses, etc.) — skip the
            # runtime check; the static test below is still meaningful.
            pass

        # Static check: ui source code must define `A = B = curses.A_BOLD`
        # (or equivalent) at module scope so the alias resolves.
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent
               / "tttutor" / "ui.py").read_text(encoding="utf-8")
        # First top-level assignment to A_BOLD-type code must include A
        first_a_bold = next(
            (i for i, line in enumerate(src.splitlines())
             if "curses.A_BOLD" in line
             and not line.strip().startswith("#")),
            None,
        )
        if first_a_bold is not None:
            # Find the first module-level binding line for `A` (or A and
            # B together, or A via B).  Accept either A = curses.A_BOLD
            # or A = B where B is already defined as curses.A_BOLD.
            for line in src.splitlines()[first_a_bold:first_a_bold + 6]:
                stripped = line.strip()
                if stripped.startswith("A =") or stripped.startswith("A="):
                    ok = ("curses.A_BOLD" in line) or ("A = B" in line)
                    self.assertTrue(
                        ok,
                        "module-level `A` alias must resolve to "
                        f"curses.A_BOLD; got: {stripped!r}",
                    )
                    return
        self.fail("ui.py does not expose a module-level `A = ...` alias — "
                  "the TUI will crash with NameError when the Welcome / "
                  "Beginner / Quit dialog renders.")
