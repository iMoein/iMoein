#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_RETENTION = 400


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"days": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"days": []}

    days = data.get("days") if isinstance(data, dict) else None
    return {"days": days if isinstance(days, list) else []}


def main() -> None:
    if len(sys.argv) not in (3, 4):
        raise SystemExit(
            "usage: update_history.py SNAPSHOT HISTORY [RETENTION_DAYS]"
        )

    snapshot_path = Path(sys.argv[1]).expanduser().resolve()
    history_path = Path(sys.argv[2]).expanduser().resolve()
    retention = int(sys.argv[3]) if len(sys.argv) == 4 else DEFAULT_RETENTION

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    date = snapshot.get("date")
    if not isinstance(date, str) or not date:
        raise SystemExit("snapshot is missing a valid date")

    history = load_history(history_path)
    by_date: dict[str, dict[str, Any]] = {}

    for day in history["days"]:
        if isinstance(day, dict) and isinstance(day.get("date"), str):
            by_date[day["date"]] = day

    by_date[date] = snapshot
    ordered = [by_date[key] for key in sorted(by_date)]
    history["days"] = ordered[-max(1, retention):]

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"history updated: {date} ({len(history['days'])} days)")


if __name__ == "__main__":
    main()
