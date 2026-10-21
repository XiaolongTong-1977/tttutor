"""Session history persistence — append-only JSONL with a typed schema.

A new-line JSON Lines file is the modern replacement for the legacy TT.HIS
binary record. It keeps one record per completed drill and one summary per
lesson / test run, which is the same conceptual data set as TT.HIS.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional


DEFAULT_HISTORY_PATH = Path.home() / ".tttutor" / "history.jsonl"


@dataclass
class HistoryRecord:
    ts: float
    kind: str                # "drill" | "lesson" | "test" | "game"
    label: str
    detail: dict
    user: str = ""           # student name (TT.HIS supports many students)

    @classmethod
    def now(cls, kind: str, label: str, detail: dict,
            user: str = "") -> "HistoryRecord":
        return cls(ts=time.time(), kind=kind, label=label, detail=detail,
                   user=user)


def _ensure(p) -> Path:
    """Coerce to Path and ensure the parent directory exists."""
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def append(record: HistoryRecord, path=None) -> None:
    """Append one record to a JSONL log. ``path`` may be str or Path; None uses
    the user's default at ~/.tttutor/history.jsonl."""
    p = _ensure(path if path is not None else DEFAULT_HISTORY_PATH)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record)) + "\n")


def load_all(path=None) -> List[HistoryRecord]:
    p = Path(path) if path is not None else DEFAULT_HISTORY_PATH
    if not p.exists():
        return []
    out: List[HistoryRecord] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            out.append(HistoryRecord(**d))
        except Exception:
            continue
    return out


def list_users(path=None) -> list[str]:
    """Distinct student names in the history, including the empty name."""
    names = {r.user for r in load_all(path) if r.user}
    return sorted(names)


def delete_user(user: str, path=None) -> int:
    """Remove every record belonging to ``user``.  Returns records removed."""
    p = Path(path) if path is not None else DEFAULT_HISTORY_PATH
    if not p.exists():
        return 0
    keep, removed = [], 0
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("user", "") == user:
            removed += 1
        else:
            keep.append(line)
    p.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return removed


def game_high_score(label: str, path=None, user: str | None = None) -> int:
    """Highest score ever recorded for a game label (e.g. "letter_invaders").

    Returns 0 if no record exists.
    """
    best = 0
    for r in load_all(path):
        if user is not None and r.user and r.user != user:
            continue
        if r.kind == "game" and r.label == label:
            best = max(best, int(r.detail.get("score", 0)))
    return best


def per_key_stats(path=None, *, top_n: int = 26,
                  user: str | None = None) -> list[tuple[str, int, int]]:
    """Aggregate per-character error counts across all drill records.

    Returns a list of (char, error_count, total_attempts) sorted by error
    count descending, then alphabetically.  Capped to ``top_n`` rows.
    """
    errs: dict[str, int] = {}
    attempts: dict[str, int] = {}
    for r in load_all(path):
        if r.kind != "drill":
            continue
        if user is not None and r.user and r.user != user:
            continue
        target = r.detail.get("target", "") or r.label  # fallback to label
        typed  = r.detail.get("typed", "")
        per_key_errs = r.detail.get("per_key_errors") or {}
        # error counts come from the drill's recorded dict
        for ch, count in per_key_errs.items():
            errs[ch] = errs.get(ch, 0) + int(count)
        # total attempts: simply count characters in target
        for ch in target:
            attempts[ch] = attempts.get(ch, 0) + 1
    rows = []
    for ch in sorted(errs.keys(), key=lambda c: (-errs[c], c))[:top_n]:
        rows.append((ch, errs[ch], attempts.get(ch, 0)))
    return rows


def game_record(score: int, label: str, detail: dict, path=None,
                user: str = "") -> tuple:
    """Append a game-result record. Returns (new_record, is_new_high_score)."""
    prev = game_high_score(label, path, user=user or None)
    is_hi = score > prev
    rec = HistoryRecord.now("game", label,
                           {"score": score, "new_high": is_hi, **detail},
                           user=user)
    append(rec, path)
    return rec, is_hi


def summary(path: Optional[Path] = None, max_records: int = 5000,
            user: str | None = None) -> dict:
    records = load_all(path)
    if user is not None:
        records = [r for r in records if (not r.user) or r.user == user]
    records = records[-max_records:]
    if not records:
        return {
            "sessions": 0,
            "drills": 0,
            "wpm_avg": 0.0,
            "accuracy_avg": 0.0,
            "minutes_total": 0.0,
            "per_kind": {"drill": 0, "lesson": 0, "test": 0, "game": 0},
            "game_high_scores": {},
            "per_key_errors": [],
            "recent_wpm": [],
            "recent_accuracy": [],
        }
    drills = [r for r in records if r.kind == "drill"]
    games = [r for r in records if r.kind == "game"]
    sessions = sum(1 for r in records if r.kind in ("lesson", "test"))
    per_kind = {k: sum(1 for r in records if r.kind == k)
                for k in ("drill", "lesson", "test", "game")}
    game_hi: dict[str, int] = {}
    for r in games:
        game_hi[r.label] = max(game_hi.get(r.label, 0), int(r.detail.get("score", 0)))
    per_key = per_key_stats(path, user=user)
    wpm_avg = (
        sum(r.detail.get("wpm", 0) for r in drills) / len(drills) if drills else 0.0
    )
    acc_avg = (
        sum(r.detail.get("accuracy", 0) for r in drills) / len(drills) if drills else 0.0
    )
    minutes_total = sum(r.detail.get("elapsed_s", 0) for r in drills) / 60.0
    recent_wpm = [r.detail.get("wpm", 0) for r in drills[-30:]]
    recent_acc = [r.detail.get("accuracy", 0) for r in drills[-30:]]
    return {
        "sessions": sessions,
        "drills": len(drills),
        "wpm_avg": wpm_avg,
        "accuracy_avg": acc_avg,
        "minutes_total": minutes_total,
        "per_kind": per_kind,
        "game_high_scores": game_hi,
        "per_key_errors": per_key,
        "recent_wpm": recent_wpm,
        "recent_accuracy": recent_acc,
    }
