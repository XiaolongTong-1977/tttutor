"""Lesson registry: combines built-in content with optional on-disk `.TST` files."""
from __future__ import annotations

from pathlib import Path
from typing import List

from .content import get_lessons, read_tst
from .engine import Lesson


def available_lessons(tst_dir: Path | None = None) -> List[Lesson]:
    lessons = list(get_lessons())
    if tst_dir and tst_dir.exists() and tst_dir.is_dir():
        for p in sorted(tst_dir.glob("*.TST")) + sorted(tst_dir.glob("*.tst")):
            lines = read_tst(p)
            if not lines:
                continue
            lessons.append(Lesson.from_lines(
                title=p.stem,
                lines=lines,
                description=f"Loaded from {p.name}",
            ))
    return lessons
