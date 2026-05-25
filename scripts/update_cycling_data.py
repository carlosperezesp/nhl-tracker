#!/usr/bin/env python3
"""Cycling legends data — Grand Tour + Monument wins. No live API required."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── Country colours & flags ───────────────────────────────────────────────────
CC3_TO_CC2: dict[str, str] = {
    "BEL": "be", "FRA": "fr", "ITA": "it", "ESP": "es", "GBR": "gb",
    "USA": "us", "NED": "nl", "SUI": "ch", "DEN": "dk", "SLO": "si",
    "COL": "co", "AUS": "au", "IRL": "ie", "SVK": "sk", "GER": "de",
    "LUX": "lu", "POR": "pt", "NOR": "no", "POL": "pl",
}
COUNTRY_COLORS: dict[str, str] = {
    "BEL": "#000000", "FRA": "#002395", "ITA": "#009246", "ESP": "#AA151B",
    "GBR": "#012169", "USA": "#B22234", "NED": "#AE1C28", "SUI": "#FF0000",
    "DEN": "#C60C30", "SLO": "#003DA5", "COL": "#FCD116", "AUS": "#00008B",
    "IRL": "#169B62", "SVK": "#0B4EA2", "GER": "#000000", "LUX": "#EF3340",
    "POR": "#006600", "NOR": "#EF2B2D", "POL": "#DC143C",
}

def _flag(cc3: str) -> str:
    cc2 = CC3_TO_CC2.get(cc3, "")
    return f"https://flagcdn.com/24x18/{cc2}.png" if cc2 else ""

# ── Legend database ───────────────────────────────────────────────────────────
# Stats through 2024 season (update manually when new Grand Tours are won)
# monuments = total Monument victories (MSR, RVV, P-R, LBL, Il Lombardia)
# worlds = UCI Road World Championship victories
LEGENDS_RAW = [
    # name,                    cc3,   birth, tour,giro,vuelta,monuments,worlds
    ("Eddy Merckx",           "BEL", 1945,   5,   5,   1,     19,       3),
    ("Bernard Hinault",       "FRA", 1954,   5,   3,   2,      6,       2),
    ("Jacques Anquetil",      "FRA", 1934,   5,   2,   1,      2,       0),
    ("Miguel Indurain",       "ESP", 1964,   5,   2,   0,      1,       0),
    ("Fausto Coppi",          "ITA", 1919,   2,   5,   0,      7,       2),
    ("Chris Froome",          "GBR", 1985,   4,   1,   2,      0,       0),
    ("Alberto Contador",      "ESP", 1982,   2,   2,   3,      0,       0),  # 3 Tour won, 1 stripped
    ("Tadej Pogacar",         "SLO", 2000,   3,   1,   0,      6,       1),  # through 2024
    ("Jonas Vingegaard",      "DEN", 1996,   2,   0,   0,      0,       0),  # through 2024
    ("Primoz Roglic",         "SLO", 1989,   0,   1,   4,      1,       0),
    ("Greg LeMond",           "USA", 1961,   3,   0,   0,      1,       2),
    ("Laurent Fignon",        "FRA", 1960,   2,   2,   0,      3,       1),
    ("Vincenzo Nibali",       "ITA", 1984,   1,   2,   1,      3,       0),
    ("Felice Gimondi",        "ITA", 1942,   1,   3,   1,      4,       1),
    ("Fabian Cancellara",     "SUI", 1981,   0,   0,   0,     11,       2),
    ("Peter Sagan",           "SVK", 1990,   0,   0,   0,      7,       3),
    ("Sean Kelly",            "IRL", 1956,   0,   0,   1,      5,       0),
    ("Roger De Vlaeminck",    "BEL", 1947,   0,   0,   0,      8,       0),
    ("Remco Evenepoel",       "BEL", 2000,   0,   0,   1,      3,       2),
    ("Egan Bernal",           "COL", 1997,   1,   1,   0,      0,       0),
]

# Weights: TDF most prestigious, then Giro, Vuelta, Monuments, Worlds
W = {"tour": 12, "giro": 9, "vuelta": 8, "monument": 4, "worlds": 5}

def _raw_score(row: tuple) -> float:
    _name, _cc3, _birth, tour, giro, vuelta, monuments, worlds = row
    return tour * W["tour"] + giro * W["giro"] + vuelta * W["vuelta"] + \
           monuments * W["monument"] + worlds * W["worlds"]

def build_legends() -> list[dict]:
    raw_scores = [(_raw_score(r), r) for r in LEGENDS_RAW]
    max_raw = max(s for s, _ in raw_scores)

    out = []
    for raw, row in sorted(raw_scores, reverse=True):
        name, cc3, birth, tour, giro, vuelta, monuments, worlds = row
        legend_score = round(raw / max_raw * 100, 1)
        active = birth >= 1985  # rough heuristic for still-active era
        out.append({
            "id":          name.lower().replace(" ", "_"),
            "name":        name,
            "country":     cc3,
            "logo":        _flag(cc3),
            "teamCode":    cc3,
            "primary":     COUNTRY_COLORS.get(cc3, "#555"),
            "secondary":   "#FFFFFF",
            "legendScore": legend_score,
            "active":      active,
            "stats": {
                "tour":      tour,
                "giro":      giro,
                "vuelta":    vuelta,
                "monuments": monuments,
                "worlds":    worlds,
                "birth":     birth,
            },
        })
    return out


def write_data() -> None:
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    legends = build_legends()

    payload = {
        "UPDATED": updated,
        "LEGENDS": legends,
        "CURRENT_RACE": None,  # placeholder: set when a Grand Tour is live
    }

    out = ROOT / "cycling_data.js"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"// Auto-generated {updated}\n")
        f.write(f"window.CYCLING_DATA = {json.dumps(payload, ensure_ascii=False, indent=2)};\n")

    print(f"Written: {out}", file=sys.stderr)
    print(f"  Top legend: {legends[0]['name']} ({legends[0]['legendScore']})")


if __name__ == "__main__":
    write_data()
