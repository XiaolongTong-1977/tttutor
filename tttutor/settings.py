"""Persistent user settings for the modern TT clone.

TT.EXE stores these values in TT.HIS.  The clone keeps the same concepts in a
small JSON file next to the history log.  The file is intentionally separate
from the original binary so the 1987 program and the clone cannot corrupt each
other's data.
"""
from __future__ import annotations

import json
from pathlib import Path

from .invaders import KEY_ORDER

DEFAULT_SETTINGS = {
    # Speed goal range index: 0 = 10-19 WPM, 1 = 20-29, ... 7 = 80+
    "wpm_goal_index": 3,
    # Practice goal index: 0 = 1-2 hours/week ... 6 = 20+
    "practice_goal_index": 2,
    # Number of drills in a lesson (5, 10, 15 or 20)
    "drills_per_lesson": 10,
    "sound_enabled": True,
    "skill_level": "Beginner",
    "learned_keys": "asdfjkl;",
    "goals": {
        "lessons_per_day": 15,
        "wpm_target": 40,
        "accuracy_target": 0.95,
        "practice_hours": 5,
    },
    # Instructor mode password (plain text; the original also stores it
    # obfuscated rather than hashed).
    "instructor_password": "KRIYA",
}

SPEED_RANGES = [(10, 19), (20, 29), (30, 39), (40, 49),
                (50, 59), (60, 69), (70, 79), (80, None)]
PRACTICE_RANGES = [(1, 2), (3, 4), (5, 6), (7, 9),
                   (10, 14), (15, 19), (20, None)]
DRILL_CHOICES = [5, 10, 15, 20]


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else Path.home() / ".tttutor" / "settings.json"
    data = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if k == "goals" and isinstance(v, dict):
                    data["goals"].update(v)
                else:
                    data[k] = v
        except Exception:
            pass
    return data


def save(data: dict, path: str | Path | None = None) -> None:
    p = Path(path) if path else Path.home() / ".tttutor" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def speed_range(index: int) -> tuple[int, int | None]:
    return SPEED_RANGES[max(0, min(index, len(SPEED_RANGES) - 1))]


def practice_range(index: int) -> tuple[int, int | None]:
    return PRACTICE_RANGES[max(0, min(index, len(PRACTICE_RANGES) - 1))]


def describe_range(rng: tuple[int, int | None]) -> str:
    lo, hi = rng
    return f"{lo:3d} - {hi:2d}" if hi is not None else f"{lo:3d}+"


def extend_learned_keys(keys: str, count: int = 2) -> str:
    """Add the next keys in TT's teaching order."""
    keys = keys or ""
    for ch in KEY_ORDER:
        if len(keys) >= len(KEY_ORDER):
            break
        if ch not in keys:
            keys += ch
            count -= 1
            if count <= 0:
                break
    return keys
