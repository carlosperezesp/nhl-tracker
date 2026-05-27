#!/usr/bin/env python3
"""Fetch NFL data from ESPN public API and regenerate nfl_data.js."""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "nfl_data.js"


# ── Prev-rank helper ─────────────────────────────────────────────────────────

def _prev_rank_map(filepath: Path, js_var: str, *path: str) -> "dict[str, int]":
    import re as _re, json as _json
    try:
        text = filepath.read_text(encoding="utf-8")
        text = _re.sub(
            r"^window\." + _re.escape(js_var) + r"\s*=\s*", "", text, flags=_re.MULTILINE
        ).rstrip().rstrip(";")
        obj = _json.loads(text)
        for key in path:
            obj = obj.get(key) if isinstance(obj, dict) else None
            if obj is None:
                return {}
        if not isinstance(obj, list):
            return {}
        result: dict[str, int] = {}
        for i, item in enumerate(obj[:20]):
            k = str(item.get("id") or item.get("name", ""))
            if k:
                result[k] = i + 1
        return result
    except Exception:
        return {}

API_STANDINGS  = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings"
API_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
API_PLAYERS    = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/statistics/byathlete"

NFL_DIVISIONS: dict[str, list[str]] = {
    "AFC East":  ["NE",  "BUF", "NYJ", "MIA"],
    "AFC North": ["BAL", "CIN", "CLE", "PIT"],
    "AFC South": ["HOU", "IND", "JAX", "TEN"],
    "AFC West":  ["KC",  "LAC", "LV",  "DEN"],
    "NFC East":  ["DAL", "PHI", "NYG", "WSH"],
    "NFC North": ["CHI", "MIN", "GB",  "DET"],
    "NFC South": ["NO",  "CAR", "TB",  "ATL"],
    "NFC West":  ["LAR", "ARI", "SEA", "SF"],
}
_CODE_TO_DIV = {code: div for div, codes in NFL_DIVISIONS.items() for code in codes}

NFL_TEAM_COLORS: dict[str, dict] = {
    "NE":  {"primary": "#002244", "secondary": "#c60c30"},
    "BUF": {"primary": "#00338d", "secondary": "#c60c30"},
    "NYJ": {"primary": "#125740", "secondary": "#000000"},
    "MIA": {"primary": "#008e97", "secondary": "#fc4c02"},
    "BAL": {"primary": "#241773", "secondary": "#9e7c0c"},
    "CIN": {"primary": "#fb4f14", "secondary": "#000000"},
    "CLE": {"primary": "#311d00", "secondary": "#ff3c00"},
    "PIT": {"primary": "#101820", "secondary": "#ffb612"},
    "HOU": {"primary": "#03202f", "secondary": "#a71930"},
    "IND": {"primary": "#002c5f", "secondary": "#a2aaad"},
    "JAX": {"primary": "#006778", "secondary": "#9f792c"},
    "TEN": {"primary": "#0c2340", "secondary": "#4b92db"},
    "KC":  {"primary": "#e31837", "secondary": "#ffb612"},
    "LAC": {"primary": "#0080c6", "secondary": "#ffb612"},
    "LV":  {"primary": "#000000", "secondary": "#a5acaf"},
    "DEN": {"primary": "#fb4f14", "secondary": "#002244"},
    "DAL": {"primary": "#003594", "secondary": "#869397"},
    "PHI": {"primary": "#004c54", "secondary": "#a5acaf"},
    "NYG": {"primary": "#0b2265", "secondary": "#a71930"},
    "WSH": {"primary": "#5a1414", "secondary": "#ffb612"},
    "CHI": {"primary": "#0b162a", "secondary": "#c83803"},
    "MIN": {"primary": "#4f2683", "secondary": "#ffc62f"},
    "GB":  {"primary": "#203731", "secondary": "#ffb612"},
    "DET": {"primary": "#0076b6", "secondary": "#b0b7bc"},
    "NO":  {"primary": "#d3bc8d", "secondary": "#101820"},
    "CAR": {"primary": "#0085ca", "secondary": "#101820"},
    "TB":  {"primary": "#d50a0a", "secondary": "#ff7900"},
    "ATL": {"primary": "#a71930", "secondary": "#000000"},
    "LAR": {"primary": "#003594", "secondary": "#ffd100"},
    "ARI": {"primary": "#97233f", "secondary": "#ffb612"},
    "SEA": {"primary": "#002244", "secondary": "#69be28"},
    "SF":  {"primary": "#aa0000", "secondary": "#b3995d"},
}

# ESPN byathlete passing stat indices (confirmed from 2025 season data)
# [cmp, att, pct, yds, ypa, ypg, long, td, int, sacks, sackyds, qbr, rating, ...]
PI_CMP  = 0; PI_ATT = 1; PI_PCT = 2; PI_YDS = 3
PI_YPA  = 4; PI_YPG = 5; PI_TD  = 7; PI_INT = 8; PI_SACK = 9


def fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "NFL Tracker local updater"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except HTTPError as exc:
        raise RuntimeError(f"{url} → HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def percentile_scores(items: list[dict], value_fn) -> dict[int, int]:
    values = [(item["id"], value_fn(item)) for item in items]
    if not values:
        return {}
    nums = [v for _, v in values]
    lo, hi = min(nums), max(nums)
    if math.isclose(lo, hi):
        return {item_id: 65 for item_id, _ in values}
    return {
        item_id: int(round(35 + ((v - lo) / (hi - lo)) * 65))
        for item_id, v in values
    }


def _season_and_status() -> tuple[int, str]:
    """Return (season_year, status) where status is 'regular' | 'postseason' | 'offseason'."""
    try:
        data = fetch_json(f"{API_SCOREBOARD}")
        s = data.get("season", {})
        year  = s.get("year", date.today().year)
        stype = s.get("type", 4)
        if stype == 2:
            return year, "regular"
        if stype == 3:
            return year, "postseason"
    except RuntimeError:
        pass
    # Off-season: use the most recently completed season
    today = date.today()
    # NFL season year = year the season started (Sep). Super Bowl in Feb of year+1.
    if today.month >= 9:
        return today.year, "offseason"
    return today.year - 1, "offseason"


def build_teams(season_year: int) -> tuple[list[dict], dict[str, dict]]:
    data = fetch_json(f"{API_STANDINGS}?season={season_year}")
    teams: list[dict] = []
    team_by_code: dict[str, dict] = {}
    for conf_data in data.get("children", []):
        conf_name = conf_data.get("name", "")
        conf = "AFC" if "American" in conf_name else "NFC"
        for entry in conf_data.get("standings", {}).get("entries", []):
            t = entry["team"]
            stats = {s["name"]: s.get("value") for s in entry.get("stats", [])}
            code = t.get("abbreviation", "")
            wins   = int(stats.get("wins",   0) or 0)
            losses = int(stats.get("losses", 0) or 0)
            ties   = int(stats.get("ties",   0) or 0)
            pf     = int(stats.get("pointsFor",     stats.get("pointDifferential", 0) or 0))
            pa     = int(stats.get("pointsAgainst", 0) or 0)
            win_pct = float(stats.get("winPercent",  0) or 0)
            pd     = pf - pa
            gp     = wins + losses + ties
            seed   = int(stats.get("playoffSeed", 0) or 0)
            # Score: win% weighted 80% + points differential per game 20%
            pdpg   = pd / max(1, gp)
            score  = round(max(0, min(100, win_pct * 80 + pdpg * 0.8)))
            logos  = t.get("logos", [])
            logo   = logos[0].get("href", "") if logos else f"https://a.espncdn.com/i/teamlogos/nfl/500/{code.lower()}.png"
            team = {
                "code":       code,
                "city":       t.get("displayName", ""),
                "shortName":  t.get("location", ""),
                "commonName": t.get("name", ""),
                "conf":       conf,
                "div":        _CODE_TO_DIV.get(code, conf),
                "gp":         gp,
                "w":          wins,
                "l":          losses,
                "t":          ties,
                "winPct":     round(win_pct, 3),
                "pf":         pf,
                "pa":         pa,
                "pd":         pd,
                "seed":       seed,
                "score":      score,
                "logo":       logo,
                "colors":     NFL_TEAM_COLORS.get(code, {"primary": "#666", "secondary": "#ccc"}),
            }
            teams.append(team)
            team_by_code[code] = team
    return sorted(teams, key=lambda t: (-t["w"], -t["pd"])), team_by_code


def build_players(season_year: int) -> list[dict]:
    try:
        data = fetch_json(
            f"{API_PLAYERS}?season={season_year}&seasontype=2&limit=100"
        )
    except RuntimeError:
        return []

    qbs: list[dict] = []

    def _v(arr: list, i: int, default: float = 0.0) -> float:
        return float(arr[i]) if len(arr) > i and arr[i] is not None else default

    for entry in data.get("athletes", []):
        ath   = entry.get("athlete", {})
        pos   = ath.get("position", {}).get("abbreviation", "?")
        if pos != "QB":
            continue
        cats  = {c["name"]: c.get("values", []) for c in entry.get("categories", [])}
        pit   = cats.get("passing", [])
        rush  = cats.get("rushing", [])

        cmp  = _v(pit, PI_CMP)
        att  = _v(pit, PI_ATT)
        if att < 50:
            continue
        yds  = _v(pit, PI_YDS)
        pct  = _v(pit, PI_PCT)
        ypa  = _v(pit, PI_YPA)
        td   = _v(pit, PI_TD)
        ints = _v(pit, PI_INT)

        rush_yds = _v(rush, 1)
        rush_td  = _v(rush, 4)

        raw = yds * 0.04 + td * 5 - ints * 4 + pct * 0.3

        teams_arr = ath.get("teams", [])
        team_code = teams_arr[0].get("abbreviation", "") if teams_arr else ath.get("teamId", "")
        hs = ath.get("headshot", {})
        headshot = hs.get("href", "") if isinstance(hs, dict) else str(hs or "")

        qbs.append({
            "id":       int(ath.get("id", 0)),
            "name":     ath.get("displayName", ""),
            "pos":      pos,
            "teamCode": team_code,
            "age":      ath.get("age"),
            "headshot": headshot,
            "colors":   NFL_TEAM_COLORS.get(team_code, {"primary": "#666", "secondary": "#ccc"}),
            "score":    50,
            "raw":      raw,
            "stats": {
                "type":     "passing",
                "cmp":      int(cmp),
                "att":      int(att),
                "pct":      round(pct, 1),
                "yds":      int(yds),
                "ypa":      round(ypa, 1),
                "td":       int(td),
                "int":      int(ints),
                "rushYds":  int(rush_yds),
                "rushTd":   int(rush_td),
            },
        })

    scores = percentile_scores(qbs, lambda p: p["raw"])
    for p in qbs:
        p["score"] = scores.get(p["id"], 50)
        del p["raw"]

    return sorted(qbs, key=lambda p: (-p["score"], p["name"]))


def _parse_round_nfl(headline: str) -> tuple[str | None, str | None]:
    h = headline.lower()
    if "super bowl" in h:
        return "sb", "sb"
    if "afc" in h or "american football" in h:
        conf = "afc"
    elif "nfc" in h or "national football" in h:
        conf = "nfc"
    else:
        return None, None
    if "wild card" in h:
        return "wc", conf
    if "divisional" in h:
        return "div", conf
    if "championship" in h:
        return "conf", conf
    return None, None


def build_bracket(season_year: int) -> dict:
    empty = {"hi": None, "lo": None, "winner": None, "seriesScore": "-"}
    bracket = {
        "afc": {"wc": [], "div": [], "conf": []},
        "nfc": {"wc": [], "div": [], "conf": []},
        "sb":  [empty.copy()],
    }
    try:
        start = f"{season_year}0101"
        end   = f"{season_year + 1}0228"
        today = date.today().strftime("%Y%m%d")
        if today < f"{season_year}0101":
            return bracket
        data = fetch_json(
            f"{API_SCOREBOARD}?seasontype=3&season={season_year}&dates={start}-{today}&limit=100"
        )
    except RuntimeError:
        return bracket

    seen: dict[frozenset, dict] = {}
    for event in data.get("events", []):
        comp = event.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        teams = [c.get("team", {}).get("abbreviation", "") for c in competitors]
        if len(teams) != 2 or not all(teams):
            continue
        key = frozenset(teams)
        e_date = event.get("date", "")
        notes = comp.get("notes", [])
        headline = notes[0].get("headline", "") if notes else ""
        # For NFL, each playoff game is one game (not a series)
        t0, t1 = teams
        competitors_map = {c.get("team", {}).get("abbreviation", ""): c for c in competitors}
        c0 = competitors_map.get(t0, {})
        c1 = competitors_map.get(t1, {})
        s0 = int(c0.get("score", 0) or 0)
        s1 = int(c1.get("score", 0) or 0)
        status = comp.get("status", {}).get("type", {}).get("completed", False)
        if key not in seen or e_date > seen[key]["date"]:
            seen[key] = {
                "date": e_date, "headline": headline,
                "teams": [t0, t1], "scores": [s0, s1],
                "completed": status,
            }

    for s in seen.values():
        round_key, conf = _parse_round_nfl(s["headline"])
        if round_key is None:
            continue
        t0, t1 = s["teams"]
        s0, s1 = s["scores"]
        hi, lo, hi_s, lo_s = (t0, t1, s0, s1) if s0 >= s1 else (t1, t0, s1, s0)
        winner = hi if (s["completed"] and hi_s > lo_s) else None
        match_obj = {"hi": hi, "lo": lo, "winner": winner, "seriesScore": f"{hi_s}-{lo_s}"}
        if round_key == "sb":
            bracket["sb"] = [match_obj]
        elif conf in ("afc", "nfc"):
            bracket[conf][round_key].append(match_obj)

    for side in ("afc", "nfc"):
        bracket[side]["wc"]   = (bracket[side]["wc"]   + [empty.copy()] * 3)[:3]
        bracket[side]["div"]  = (bracket[side]["div"]  + [empty.copy()] * 2)[:2]
        bracket[side]["conf"] = (bracket[side]["conf"] + [empty.copy()])[:1]
    return bracket


def _nfl_importance(status: str, bracket: dict) -> float:
    if status == "offseason":
        return 3.0
    sb = (bracket.get("sb") or [{}])[0]
    if sb.get("hi"):
        return 10.0  # Super Bowl
    for conf in ("afc", "nfc"):
        for rnd in ("conf", "div", "wc"):
            for s in bracket.get(conf, {}).get(rnd) or []:
                if s.get("hi"):
                    return 9.0  # Playoffs
    return 8.0  # Regular season


def write_data(output: Path) -> None:
    prev_players = _prev_rank_map(output, "NFL_DATA", "PLAYERS")

    season_year, status = _season_and_status()

    print(f"Season {season_year} ({status}). Fetching NFL standings…")
    teams, team_by_code = build_teams(season_year)

    # If standings are empty the season hasn't started yet — fall back to last season
    if not teams:
        season_year -= 1
        status = "offseason"
        print(f"No teams found, falling back to season {season_year}…")
        teams, team_by_code = build_teams(season_year)

    standings_year = season_year
    print("Fetching NFL player stats (QBs)…")
    players = build_players(standings_year)

    print("Fetching NFL bracket…")
    bracket = build_bracket(season_year)

    importance = _nfl_importance(status, bracket)

    # ── Asignar prevRank ──────────────────────────────────────────────────────
    for p in sorted(players, key=lambda x: x["score"], reverse=True)[:10]:
        p["prevRank"] = prev_players.get(str(p.get("id") or p.get("name", "")))

    payload = {
        "TEAMS":         teams,
        "PLAYERS":       players,
        "BRACKET":       bracket,
        "DIVISIONS":     list(NFL_DIVISIONS.keys()),
        "SEASON":        str(season_year),
        "SEASON_STATUS": status,
        "IMPORTANCE":    importance,
        "LAST_UPDATE":   datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "SOURCE":        {"name": "ESPN API", "baseUrl": "site.api.espn.com"},
    }

    output.write_text(
        "// NFL Tracker - generated from ESPN public API data.\n"
        "// Run `python3 scripts/update_nfl_data.py` to refresh.\n"
        f"window.NFL_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        write_data(args.output)
    except Exception as exc:
        print(f"update_nfl_data.py: {exc}", file=sys.stderr)
        return 1
    print(f"Updated {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
