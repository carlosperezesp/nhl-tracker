#!/usr/bin/env python3
"""Fail loudly when key Hermes data files are stale or structurally incomplete."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "nhl":     {"file": "data.js",         "var": "NHL_DATA",     "field": "LAST_UPDATE", "max_hours": 36},
    "nba":     {"file": "nba_data.js",     "var": "NBA_DATA",     "field": "LAST_UPDATE", "max_hours": 36},
    "tennis":  {"file": "tennis_data.js",  "var": "TENNIS_DATA",  "field": "UPDATED",     "max_hours": 18},
    "cycling": {"file": "cycling_data.js", "var": "CYCLING_DATA", "field": "UPDATED",     "max_hours": 36},
    "cricket": {"file": "cricket_data.js", "var": "CRICKET_DATA", "field": "UPDATED",     "max_hours": 36},
}


def read_js_json(filename: str, var_name: str) -> dict:
    text = (ROOT / filename).read_text(encoding="utf-8")
    match = re.search(rf"window\.{re.escape(var_name)}\s*=\s*(\{{.*\}})\s*;?\s*$", text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"could not find window.{var_name} assignment")
    return json.loads(match.group(1))


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)


def check_freshness(name: str, data: dict, field: str, max_hours: float) -> list[str]:
    value = data.get(field)
    if not value:
        return [f"{name}: missing {field}"]
    age_h = (datetime.now(timezone.utc) - parse_utc(value)).total_seconds() / 3600
    if age_h > max_hours:
        return [f"{name}: stale ({age_h:.1f}h old, max {max_hours:g}h, {field}={value})"]
    return []


def check_structure(name: str, data: dict) -> list[str]:
    errors: list[str] = []
    if name in {"nhl", "nba"} and float(data.get("IMPORTANCE") or 0) >= 8.0:
        final = ((data.get("BRACKET") or {}).get("final") or [{}])[0]
        if not final.get("hi") or not final.get("lo") or "TBD" in {final.get("hi"), final.get("lo")}:
            errors.append(f"{name}: importance >= 8 but final teams are not complete")
    if name == "cycling":
        race = data.get("CURRENT_RACE") or {}
        if race and race.get("stage") == race.get("total_stages") and not (race.get("gc") or [{}])[0].get("legendScore"):
            errors.append("cycling: final GC leader is missing legendScore")
    return errors


def main(argv: list[str]) -> int:
    selected = argv[1:] or list(CHECKS)
    errors: list[str] = []
    for name in selected:
        cfg = CHECKS.get(name)
        if not cfg:
            errors.append(f"unknown check: {name}")
            continue
        try:
            data = read_js_json(cfg["file"], cfg["var"])
            errors.extend(check_freshness(name, data, cfg["field"], cfg["max_hours"]))
            errors.extend(check_structure(name, data))
        except Exception as exc:
            errors.append(f"{name}: check failed: {exc}")

    if errors:
        print("Hermes data freshness check failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"Hermes data freshness OK: {', '.join(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
