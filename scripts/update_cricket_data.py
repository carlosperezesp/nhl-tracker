#!/usr/bin/env python3
"""Build cricket_data.js from completed Cricsheet scorecards.

This is deliberately not live. It downloads Cricsheet ZIP archives, parses
completed scorecards, and recalculates Hermes cricket rankings from matches
that have already happened.
"""

from __future__ import annotations

import io
import json
import math
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cricket_data.js"
CACHE = ROOT / ".cricket_cache"
CACHE.mkdir(exist_ok=True)

CRICSHEET = "https://cricsheet.org/downloads/{name}_json.zip"
ARCHIVES = {
    "test": {"name": "tests", "format": "test", "weight": 1.0, "days": 730, "label": "Tests"},
    "odi": {"name": "odis", "format": "odi", "weight": 1.0, "days": 548, "label": "ODIs"},
    "t20i": {"name": "t20s", "format": "t20", "weight": 0.86, "days": 548, "label": "T20Is"},
    "ipl": {"name": "ipl", "format": "franchise", "weight": 1.0, "days": 730, "label": "IPL"},
    "bbl": {"name": "bbl", "format": "franchise", "weight": 0.72, "days": 730, "label": "BBL"},
    "psl": {"name": "psl", "format": "franchise", "weight": 0.72, "days": 730, "label": "PSL"},
    "sa20": {"name": "sa20", "format": "franchise", "weight": 0.68, "days": 730, "label": "SA20"},
    "cpl": {"name": "cpl", "format": "franchise", "weight": 0.62, "days": 730, "label": "CPL"},
    "mlc": {"name": "mlc", "format": "franchise", "weight": 0.58, "days": 730, "label": "MLC"},
}

COUNTRIES = {
    "Australia": {"code": "AUS", "primary": "#ffcd00", "secondary": "#006341", "flag": "au"},
    "England": {"code": "ENG", "primary": "#c8102e", "secondary": "#ffffff", "flag": "gb-eng"},
    "India": {"code": "IND", "primary": "#1c4fa1", "secondary": "#ff9933", "flag": "in"},
    "New Zealand": {"code": "NZ", "primary": "#111111", "secondary": "#d8d8d8", "flag": "nz"},
    "Pakistan": {"code": "PAK", "primary": "#115740", "secondary": "#ffffff", "flag": "pk"},
    "South Africa": {"code": "SA", "primary": "#007a4d", "secondary": "#ffb81c", "flag": "za"},
    "Sri Lanka": {"code": "SL", "primary": "#0033a0", "secondary": "#ffb612", "flag": "lk"},
    "Afghanistan": {"code": "AFG", "primary": "#d32011", "secondary": "#007a36", "flag": "af"},
    "West Indies": {"code": "WI", "primary": "#7a263a", "secondary": "#f6c344", "flag": ""},
    "Bangladesh": {"code": "BAN", "primary": "#006a4e", "secondary": "#f42a41", "flag": "bd"},
    "Zimbabwe": {"code": "ZIM", "primary": "#009739", "secondary": "#ffd100", "flag": "zw"},
    "Ireland": {"code": "IRE", "primary": "#169b62", "secondary": "#ff883e", "flag": "ie"},
    "Netherlands": {"code": "NED", "primary": "#ff7f00", "secondary": "#21468b", "flag": "nl"},
}

TEAM_ALIASES = {
    "United Arab Emirates": ("UAE", "#00732f", "#ffffff", "ae"),
    "Scotland": ("SCO", "#005eb8", "#ffffff", "gb-sct"),
    "Nepal": ("NEP", "#dc143c", "#003893", "np"),
    "Oman": ("OMA", "#db161b", "#ffffff", "om"),
    "Namibia": ("NAM", "#003580", "#ffce00", "na"),
    "United States of America": ("USA", "#3c3b6e", "#b22234", "us"),
}

PLAYER_COUNTRY_OVERRIDES = {
    "Virat Kohli": "India",
    "Jasprit Bumrah": "India",
    "Rohit Sharma": "India",
    "Joe Root": "England",
    "Harry Brook": "England",
    "Ben Stokes": "England",
    "Steven Smith": "Australia",
    "Pat Cummins": "Australia",
    "Travis Head": "Australia",
    "Kane Williamson": "New Zealand",
    "Babar Azam": "Pakistan",
    "Shaheen Shah Afridi": "Pakistan",
    "Rashid Khan": "Afghanistan",
    "Kagiso Rabada": "South Africa",
}

LEGACY_SEEDS = {
    "Virat Kohli": 88.0,
    "Joe Root": 78.0,
    "Steven Smith": 76.0,
    "Kane Williamson": 73.0,
    "Pat Cummins": 63.0,
    "Jasprit Bumrah": 58.0,
    "Rashid Khan": 52.0,
    "Babar Azam": 49.0,
    "Kagiso Rabada": 48.0,
    "Travis Head": 44.0,
    "Harry Brook": 27.0,
}

TROPHIES = [
    {"code": "AUS", "name": "Australia", "odi_wc": 6, "t20_wc": 1, "ct": 2, "wtc": 1, "note": "Gold standard ICC cabinet"},
    {"code": "IND", "name": "India", "odi_wc": 2, "t20_wc": 2, "ct": 2, "wtc": 0, "note": "Modern depth monster; WTC still the missing line"},
    {"code": "WI", "name": "West Indies", "odi_wc": 2, "t20_wc": 2, "ct": 1, "wtc": 0, "note": "White-ball legacy still enormous"},
    {"code": "ENG", "name": "England", "odi_wc": 1, "t20_wc": 2, "ct": 0, "wtc": 0, "note": "White-ball reinvention changed the sport"},
    {"code": "PAK", "name": "Pakistan", "odi_wc": 1, "t20_wc": 1, "ct": 1, "wtc": 0, "note": "Tournament volatility as identity"},
    {"code": "SL", "name": "Sri Lanka", "odi_wc": 1, "t20_wc": 1, "ct": 1, "wtc": 0, "note": "Underrated cross-format era peak"},
    {"code": "NZ", "name": "New Zealand", "odi_wc": 0, "t20_wc": 0, "ct": 1, "wtc": 1, "note": "WTC crown anchors the legacy"},
    {"code": "SA", "name": "South Africa", "odi_wc": 0, "t20_wc": 0, "ct": 1, "wtc": 0, "note": "Talent says more than the trophy shelf"},
]

HISTORIC_TOP_10_THRESHOLD = 79.0


def fetch_archive(name: str, max_age_hours: float = 18.0) -> bytes | None:
    path = CACHE / f"{name}_json.zip"
    if path.exists() and (time.time() - path.stat().st_mtime) / 3600 < max_age_hours:
        return path.read_bytes()
    url = CRICSHEET.format(name=name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
        with urllib.request.urlopen(req, timeout=35) as response:
            data = response.read()
        path.write_bytes(data)
        return data
    except Exception as exc:
        print(f"[WARN] Cricsheet download failed for {name}: {exc}", file=sys.stderr)
        return path.read_bytes() if path.exists() else None


def parse_match_date(info: dict) -> date | None:
    dates = info.get("dates") or []
    if not dates:
        return None
    try:
        return date.fromisoformat(str(dates[-1]))
    except ValueError:
        return None


def wicket_credit(wicket: dict, bowler: str) -> bool:
    if wicket.get("kind") in {"run out", "retired hurt", "retired out", "obstructing the field"}:
        return False
    return bool(bowler)


def empty_player() -> dict:
    return {
        "runs": 0,
        "balls": 0,
        "outs": 0,
        "wickets": 0,
        "bowl_balls": 0,
        "bowl_runs": 0,
        "matches": 0,
        "teams": defaultdict(int),
        "formats": defaultdict(float),
    }


def add_match(stats: dict, match: dict, archive: dict, today: date) -> bool:
    info = match.get("info", {})
    if info.get("gender") != "male":
        return False
    match_date = parse_match_date(info)
    if not match_date or match_date > today:
        return False
    if (today - match_date).days > archive["days"]:
        return False

    fmt = archive["format"]
    weight = archive["weight"]
    players_by_team = info.get("players") or {}
    for team, names in players_by_team.items():
        for name in names:
            stats[name]["matches"] += 1
            stats[name]["teams"][team] += 1

    for innings in match.get("innings", []):
        for over in innings.get("overs", []):
            for delivery in over.get("deliveries", []):
                batter = delivery.get("batter")
                bowler = delivery.get("bowler")
                runs = delivery.get("runs") or {}
                extras = delivery.get("extras") or {}

                if batter:
                    stats[batter]["runs"] += int(runs.get("batter") or 0)
                    if "wides" not in extras:
                        stats[batter]["balls"] += 1
                if bowler:
                    stats[bowler]["bowl_balls"] += 0 if "wides" in extras else 1
                    bowler_runs = int(runs.get("total") or 0)
                    bowler_runs -= int(extras.get("byes") or 0)
                    bowler_runs -= int(extras.get("legbyes") or 0)
                    bowler_runs -= int(extras.get("penalty") or 0)
                    stats[bowler]["bowl_runs"] += max(0, bowler_runs)

                for wicket in delivery.get("wickets") or []:
                    out = wicket.get("player_out")
                    if out:
                        stats[out]["outs"] += 1
                    if bowler and wicket_credit(wicket, bowler):
                        stats[bowler]["wickets"] += 1

    for name, row in stats.items():
        # Cheap but robust: if a player appeared in the scorecard, translate their
        # current aggregate into a format-specific raw score after this match.
        if row["matches"]:
            row["formats"][fmt] = raw_score(row, fmt) * weight
    return True


def raw_score(row: dict, fmt: str) -> float:
    runs = row["runs"]
    balls = max(1, row["balls"])
    outs = max(1, row["outs"])
    wickets = row["wickets"]
    bowl_balls = max(1, row["bowl_balls"])
    bowl_runs = row["bowl_runs"]
    matches = max(1, row["matches"])

    avg = runs / outs
    sr = runs / balls * 100
    runs_per_match = runs / matches
    batting = runs_per_match * 1.5 + avg * 0.9 + sr * (0.14 if fmt in {"t20", "franchise"} else 0.07)

    wkts_per_match = wickets / matches
    economy = bowl_runs / bowl_balls * 6
    bowling = wickets * 4.5 + wkts_per_match * 34 - economy * (2.2 if fmt in {"t20", "franchise"} else 1.2)

    involvement = min(14.0, math.log1p(matches) * 4.0)
    return max(0.0, batting + bowling + involvement)


def normalise(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda x: x[1], reverse=True)
    top = ordered[0][1] or 1.0
    return {name: round(min(100.0, score / top * 100), 1) for name, score in ordered}


def team_meta(team_name: str) -> dict:
    if team_name in COUNTRIES:
        c = COUNTRIES[team_name]
        flag = f"https://flagcdn.com/24x18/{c['flag']}.png" if c["flag"] else ""
        return {
            "country": team_name,
            "teamCode": c["code"],
            "colors": {"primary": c["primary"], "secondary": c["secondary"]},
            "logo": flag,
        }
    if team_name in TEAM_ALIASES:
        code, primary, secondary, flag = TEAM_ALIASES[team_name]
        return {
            "country": team_name,
            "teamCode": code,
            "colors": {"primary": primary, "secondary": secondary},
            "logo": f"https://flagcdn.com/24x18/{flag}.png" if flag else "",
        }
    return {
        "country": team_name,
        "teamCode": team_name[:3].upper(),
        "colors": {"primary": "#555555", "secondary": "#dddddd"},
        "logo": "",
    }


def infer_country(name: str, row: dict) -> str:
    if name in PLAYER_COUNTRY_OVERRIDES:
        return PLAYER_COUNTRY_OVERRIDES[name]
    for team, _ in sorted(row["teams"].items(), key=lambda x: x[1], reverse=True):
        if team in COUNTRIES or team in TEAM_ALIASES:
            return team
    return next(iter(row["teams"]), "World")


def role_for(row: dict) -> str:
    bat = row["runs"] / max(1, row["matches"])
    bowl = row["wickets"] / max(1, row["matches"])
    if bat >= 24 and bowl >= 0.8:
        return "All-rounder"
    if bowl >= 1.1:
        return "Bowler"
    if bat >= 20:
        return "Batter"
    return "Cricketer"


def player_rows(stats: dict) -> tuple[list[dict], dict[str, list[dict]]]:
    format_values = {
        fmt: normalise({name: row["formats"].get(fmt, 0.0) for name, row in stats.items() if row["formats"].get(fmt, 0.0) > 0})
        for fmt in ("test", "odi", "t20", "franchise")
    }

    rows = []
    for name, row in stats.items():
        test = format_values["test"].get(name, 0.0)
        odi = format_values["odi"].get(name, 0.0)
        t20 = format_values["t20"].get(name, 0.0)
        franchise = format_values["franchise"].get(name, 0.0)
        if max(test, odi, t20, franchise) < 18:
            continue
        score = round(test * 0.34 + odi * 0.24 + t20 * 0.18 + franchise * 0.14 + max(test, odi, t20, franchise) * 0.10, 1)
        country = infer_country(name, row)
        meta = team_meta(country)
        legend = max(LEGACY_SEEDS.get(name, 0.0), min(96.0, score * 0.55 + math.log1p(row["matches"]) * 5.0))
        rows.append({
            "id": name.lower().replace(" ", "-").replace(".", ""),
            "name": name,
            "role": role_for(row),
            "score": score,
            "legendScore": round(legend, 1),
            "stats": {
                "test": test,
                "odi": odi,
                "t20": t20,
                "franchise": franchise,
                "runs": row["runs"],
                "wickets": row["wickets"],
                "matches": row["matches"],
            },
            **meta,
        })
    rows.sort(key=lambda x: x["score"], reverse=True)

    groups = {}
    for fmt in ("test", "odi", "t20", "franchise"):
        key = "franchise" if fmt == "franchise" else fmt
        groups[key] = sorted(
            ({**r, "score": r["stats"][fmt], "formatScore": r["stats"][fmt]} for r in rows if r["stats"][fmt] > 0),
            key=lambda x: x["score"],
            reverse=True,
        )[:10]
    return rows[:10], groups


def trophy_score(t: dict) -> float:
    return round(t["odi_wc"] * 14 + t["t20_wc"] * 9 + t["ct"] * 6 + t["wtc"] * 10, 1)


def trophy_rows() -> list[dict]:
    rows = []
    for t in TROPHIES:
        rows.append({
            **team_meta(t["name"]),
            "name": t["name"],
            "score": trophy_score(t),
            "stats": {k: t[k] for k in ("odi_wc", "t20_wc", "ct", "wtc")},
            "note": t["note"],
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)


def wtc_rows(groups: dict[str, list[dict]]) -> list[dict]:
    # WTC official standings are awkward to consume reliably. This proxy is
    # recalculated from recent completed Tests and clearly labelled in the UI.
    by_team: dict[str, float] = defaultdict(float)
    for p in groups.get("test", [])[:30]:
        by_team[p["country"]] += p["score"]
    rows = []
    for team, total in by_team.items():
        meta = team_meta(team)
        rows.append({
            **meta,
            "name": team,
            "score": round(total / 3.0, 1),
            "pct": round(total / 3.0, 1),
            "played": 0,
            "note": "Proxy Hermes desde rendimiento Test reciente; sustituible por standings ICC oficiales.",
        })
    return sorted(rows, key=lambda x: x["score"], reverse=True)[:8]


def main() -> int:
    today = datetime.now(timezone.utc).date()
    stats = defaultdict(empty_player)
    source = {"archives": [], "matches": 0}

    for archive in ARCHIVES.values():
        data = fetch_archive(archive["name"])
        if not data:
            continue
        used = 0
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            print(f"[WARN] Cricsheet archive for {archive['name']} was not a valid ZIP", file=sys.stderr)
            continue
        with zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                try:
                    match = json.loads(zf.read(name))
                except Exception:
                    continue
                if add_match(stats, match, archive, today):
                    used += 1
        source["archives"].append({"name": archive["label"], "matches": used})
        source["matches"] += used

    if source["matches"] == 0:
        raise RuntimeError("No Cricsheet matches available; keeping existing cricket_data.js unchanged.")

    players, groups = player_rows(stats)
    road = sorted(players, key=lambda x: x["legendScore"], reverse=True)[:10]

    payload = {
        "UPDATED": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "IMPORTANCE": 5.8,
        "SOURCE": {
            "mode": "Cricsheet completed scorecards + Hermes scoring",
            "matches": source["matches"],
            "archives": source["archives"],
            "note": "Daily-after-results model: no live scores, recalculates from completed Cricsheet scorecards.",
        },
        "PLAYERS": players,
        "FORMAT_KINGS": {
            "test": groups.get("test", []),
            "odi": groups.get("odi", []),
            "t20": groups.get("t20", []),
            "franchise": groups.get("franchise", []),
        },
        "WTC": {"cycle": "2025-27", "standings": wtc_rows(groups), "mode": "Hermes Test proxy"},
        "TROPHIES": trophy_rows(),
        "ROAD_TO_GLORY": {"playerThreshold": HISTORIC_TOP_10_THRESHOLD, "players": road},
    }
    OUT.write_text(
        "// Cricket Tracker - generated from Cricsheet completed scorecards + Hermes scoring.\n"
        "// Run `python3 scripts/update_cricket_data.py` to refresh.\n"
        f"window.CRICKET_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"Updated {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
