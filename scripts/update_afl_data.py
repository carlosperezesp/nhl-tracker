#!/usr/bin/env python3
"""AFL data: ladder, last round results, VFL/AFL legends. Uses Squiggle API."""
from __future__ import annotations
import hashlib, json, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".afl_cache"
CACHE.mkdir(exist_ok=True)

CURRENT_YEAR = datetime.now(timezone.utc).year
SQUIGGLE     = "https://api.squiggle.com.au"
AFL_REGULAR_ROUNDS = 23  # rounds before finals

# ── Team colors ───────────────────────────────────────────────────────────────
TEAM_COLORS: dict[str, dict] = {
    "Adelaide":               {"primary": "#002B5C", "secondary": "#CC2031"},
    "Brisbane Lions":         {"primary": "#7B1A4B", "secondary": "#F6AE00"},
    "Carlton":                {"primary": "#0E1E2D", "secondary": "#FFFFFF"},
    "Collingwood":            {"primary": "#000000", "secondary": "#FFFFFF"},
    "Essendon":               {"primary": "#CC2031", "secondary": "#000000"},
    "Fremantle":              {"primary": "#2A0D54", "secondary": "#FFFFFF"},
    "Geelong":                {"primary": "#002A54", "secondary": "#FFFFFF"},
    "Gold Coast":             {"primary": "#C5002F", "secondary": "#F1B500"},
    "Greater Western Sydney": {"primary": "#F57F00", "secondary": "#002040"},
    "GWS Giants":             {"primary": "#F57F00", "secondary": "#002040"},
    "Hawthorn":               {"primary": "#4D2004", "secondary": "#FFD200"},
    "Melbourne":              {"primary": "#CC2031", "secondary": "#013B9F"},
    "North Melbourne":        {"primary": "#003087", "secondary": "#FFFFFF"},
    "Port Adelaide":          {"primary": "#008AAB", "secondary": "#000000"},
    "Richmond":               {"primary": "#FFD200", "secondary": "#000000"},
    "St Kilda":               {"primary": "#ED1C2E", "secondary": "#000000"},
    "Sydney":                 {"primary": "#CC2031", "secondary": "#FFFFFF"},
    "West Coast":             {"primary": "#002B5C", "secondary": "#F5C209"},
    "Western Bulldogs":       {"primary": "#0039A6", "secondary": "#CC2031"},
}

def _team_colors(name: str) -> dict:
    for key, val in TEAM_COLORS.items():
        if key.lower() in name.lower() or name.lower() in key.lower():
            return val
    return {"primary": "#555555", "secondary": "#FFFFFF"}

# ── VFL/AFL Legends ───────────────────────────────────────────────────────────
# name, team, born, flags(as player), brownlow, all_aus, active
AFL_LEGENDS_RAW = [
    ("Kevin Bartlett",      "Richmond",           1947, 5, 0, 5, False),
    ("Dick Reynolds",       "Essendon",           1915, 4, 3, 0, False),
    ("Ron Barassi",         "Melbourne/Carlton",  1936, 5, 0, 0, False),
    ("Sam Mitchell",        "Hawthorn",           1983, 4, 1, 3, False),
    ("Leigh Matthews",      "Hawthorn",           1952, 4, 0, 4, False),
    ("Jason Dunstall",      "Hawthorn",           1965, 4, 0, 3, False),
    ("Cyril Rioli",         "Hawthorn",           1990, 4, 0, 2, False),
    ("Dustin Martin",       "Richmond",           1991, 3, 1, 5, True),
    ("Gary Ablett Jr.",     "Geelong/GCS",        1984, 2, 2, 6, False),
    ("Adam Goodes",         "Sydney",             1980, 2, 2, 5, False),
    ("Wayne Carey",         "North Melbourne",    1971, 2, 0, 8, False),
    ("Nathan Buckley",      "Collingwood",        1972, 1, 1, 8, False),
    ("Patrick Dangerfield", "Geelong",            1990, 1, 1, 8, True),
    ("Bob Skilton",         "South Melbourne",    1938, 0, 3, 0, False),
    ("Gary Ablett Sr.",     "Geelong",            1961, 0, 1, 5, False),
]

W_LEGEND = {"flags": 8.0, "brownlow": 5.0, "all_aus": 1.5}

def _raw_score(row: tuple) -> float:
    *_, flags, brownlow, all_aus, _active = row
    return flags * W_LEGEND["flags"] + brownlow * W_LEGEND["brownlow"] + all_aus * W_LEGEND["all_aus"]

def build_legends() -> list[dict]:
    scored  = [(_raw_score(r), r) for r in AFL_LEGENDS_RAW]
    max_raw = max(s for s, _ in scored)
    out = []
    for raw, row in sorted(scored, reverse=True):
        name, team, born, flags, brownlow, all_aus, active = row
        colors = _team_colors(team.split("/")[0])
        out.append({
            "id":          name.lower().replace(" ", "_").replace(".",""),
            "name":        name,
            "country":     "AUS",
            "logo":        "https://flagcdn.com/24x18/au.png",
            "teamCode":    team.split("/")[0],
            "primary":     colors["primary"],
            "secondary":   colors["secondary"],
            "legendScore": round(raw / max_raw * 100, 1),
            "active":      active,
            "stats":       {"flags": flags, "brownlow": brownlow, "all_aus": all_aus, "birth": born},
        })
    return out

# ── API helpers ───────────────────────────────────────────────────────────────

def _fetch(url: str, ttl_hours: float = 1.0) -> dict | None:
    key  = hashlib.md5(url.encode()).hexdigest()
    path = CACHE / key
    if path.exists():
        age_h = (time.time() - path.stat().st_mtime) / 3600
        if age_h < ttl_hours:
            return json.loads(path.read_text())
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        path.write_text(json.dumps(data))
        return data
    except Exception as exc:
        print(f"[WARN] Squiggle fetch failed ({exc}): {url}", file=sys.stderr)
        if path.exists():
            return json.loads(path.read_text())
        return None

# ── Data builders ─────────────────────────────────────────────────────────────

def _ladder(year: int) -> list[dict]:
    data = _fetch(f"{SQUIGGLE}/?q=standings;year={year}", ttl_hours=1.0)
    if not data:
        return []
    out = []
    for s in data.get("standings", []):
        name   = s.get("name", "")
        colors = _team_colors(name)
        pct    = float(s.get("percentage", 0))
        out.append({
            "rank":       int(s.get("rank", 0)),
            "name":       name,
            "wins":       int(s.get("wins", 0)),
            "losses":     int(s.get("losses", 0)),
            "draws":      int(s.get("draws", 0)),
            "pts":        int(s.get("pts", 0)),
            "percentage": round(pct, 1),
            "primary":    colors["primary"],
            "secondary":  colors["secondary"],
        })
    out.sort(key=lambda x: x["rank"])
    return out[:18]

def _last_round(year: int) -> tuple[int, list[dict]]:
    data = _fetch(f"{SQUIGGLE}/?q=games;complete=100;year={year}", ttl_hours=1.0)
    if not data:
        return 0, []
    games = data.get("games", [])
    if not games:
        return 0, []
    last_round = max(g.get("round", 0) for g in games)
    round_games = [g for g in games if g.get("round") == last_round]
    out = []
    for g in sorted(round_games, key=lambda x: x.get("unixtime", 0)):
        hname  = g.get("hteam", "")
        aname  = g.get("ateam", "")
        winner = g.get("winner", "")
        out.append({
            "hteam":    hname,
            "hscore":   int(g.get("hscore", 0)),
            "ateam":    aname,
            "ascore":   int(g.get("ascore", 0)),
            "winner":   winner,
            "date":     g.get("date", "")[:10],
            "hprimary": _team_colors(hname)["primary"],
            "aprimary": _team_colors(aname)["primary"],
        })
    return last_round, out

def _importance(round_num: int) -> float:
    if round_num >= AFL_REGULAR_ROUNDS + 3:
        return 10.0  # Grand Final week
    if round_num >= AFL_REGULAR_ROUNDS + 1:
        return 9.5   # Finals
    if round_num >= AFL_REGULAR_ROUNDS:
        return 9.0   # Last home-and-away round
    progress = round_num / AFL_REGULAR_ROUNDS
    return round(7.0 + progress * 1.5, 1)

# ── Main ──────────────────────────────────────────────────────────────────────

def write_data() -> None:
    updated  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    year     = CURRENT_YEAR
    print(f"[AFL] Fetching {year} season data…", file=sys.stderr)

    legends              = build_legends()
    ladder               = _ladder(year)
    last_round, results  = _last_round(year)
    importance           = _importance(last_round)

    payload = {
        "UPDATED":    updated,
        "SEASON":     str(year),
        "ROUND":      last_round,
        "IMPORTANCE": importance,
        "LADDER":     ladder,
        "LAST_ROUND": results,
        "LEGENDS":    legends,
    }

    out = ROOT / "afl_data.js"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"// Auto-generated {updated}\n")
        f.write(f"window.AFL_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n")

    print(f"Written: {out}", file=sys.stderr)
    print(f"  Round {last_round} · importance={importance}")
    if ladder:
        print(f"  Leader: {ladder[0]['name']} (W{ladder[0]['wins']} L{ladder[0]['losses']})")
    if legends:
        print(f"  Top legend: {legends[0]['name']} ({legends[0]['legendScore']})")


if __name__ == "__main__":
    write_data()
