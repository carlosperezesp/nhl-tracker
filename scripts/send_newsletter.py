#!/usr/bin/env python3
"""Update NHL + NBA data and send the daily newsletter email via Gmail SMTP."""

from __future__ import annotations

import json
import os
import re
import smtplib
import subprocess
import sys
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

ROOT      = Path(__file__).resolve().parents[1]
SENDER    = "carlosrealmurcia@gmail.com"
RECIPIENT = "carlosrealmurcia@gmail.com"

# ── Palette ──────────────────────────────────────────────────────
BG       = "#f5f3f0"
PAPER    = "#fafaf8"
INK      = "#1a1714"
INK2     = "#3d3a37"
MUTED    = "#888880"
RULE     = "#e8e5e1"
ACCENT   = "#b84832"
GOOD     = "#2d7a3a"
BAR_FILL = "#4a4745"
BAR_BG   = "#dedad6"


# ── Config ───────────────────────────────────────────────────────

def load_env() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_js_data(js_file: Path) -> dict:
    text = js_file.read_text(encoding="utf-8")
    m = re.search(r"window\.\w+\s*=\s*(\{.*\})\s*;", text, re.DOTALL)
    return json.loads(m.group(1)) if m else {}


# ── HTML primitives ───────────────────────────────────────────────

def swatch(color: str, size: int = 10) -> str:
    return (f'<span style="display:inline-block;width:{size}px;height:{size}px;'
            f'border-radius:2px;background:{color};vertical-align:middle;'
            f'margin-right:5px;flex-shrink:0"></span>')


def score_bar(value: float, threshold: float, width: int = 130) -> str:
    """Horizontal progress bar with threshold marker — table-based, email-safe."""
    if not threshold:
        return ""
    pct   = min(100.0, max(0.0, value / threshold * 100))
    t_pct = 100.0  # threshold line is always at the right edge
    fill_px = round(width * pct / 100)
    rest_px = width - fill_px
    # Threshold marker: a 2px dark line positioned at threshold (= right edge)
    bar = (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="display:inline-table;width:{width}px;height:7px;'
        f'background:{BAR_BG};border-spacing:0;vertical-align:middle">'
        f'<tr>'
        f'<td style="width:{fill_px}px;background:{BAR_FILL};height:7px;padding:0"></td>'
        f'<td style="background:{BAR_BG};height:7px;padding:0"></td>'
        f'<td style="width:2px;background:{ACCENT};height:7px;padding:0"></td>'
        f'</tr>'
        f'</table>'
    )
    return bar


# ── Bracket ───────────────────────────────────────────────────────

def _series_row(s: dict, round_label: str, team_colors: dict[str, str]) -> str:
    hi, lo = s.get("hi"), s.get("lo")
    if not hi and not lo:
        return ""
    score   = s.get("seriesScore", "-")
    winner  = s.get("winner")
    hi_col  = team_colors.get(hi, MUTED)
    lo_col  = team_colors.get(lo, MUTED)

    if winner:
        loser  = lo if winner == hi else hi
        l_col  = team_colors.get(loser, MUTED)
        w_col  = team_colors.get(winner, MUTED)
        result = (
            f'{swatch(w_col)}<b style="color:{INK}">{winner}</b> '
            f'<span style="color:{MUTED}">vs</span> '
            f'<span style="color:{MUTED};text-decoration:line-through">{loser}</span> '
            f'<span style="color:{GOOD};font-weight:700;margin-left:4px">{score}</span>'
        )
    elif hi and lo:
        result = (
            f'{swatch(hi_col)}<b style="color:{INK}">{hi}</b> '
            f'<span style="color:{MUTED}">vs</span> '
            f'{swatch(lo_col)}<b style="color:{INK}">{lo}</b> '
            f'<span style="color:{ACCENT};font-weight:700;margin-left:4px">{score} live</span>'
        )
    else:
        result = f'<span style="color:{MUTED}">TBD</span>'

    label_style = (f'font-size:9px;letter-spacing:.1em;text-transform:uppercase;'
                   f'color:{MUTED};font-family:monospace;white-space:nowrap')
    return (
        f'<tr>'
        f'<td style="padding:5px 10px 5px 0;{label_style};vertical-align:top">{round_label}</td>'
        f'<td style="padding:5px 0;font-size:13px;vertical-align:top">{result}</td>'
        f'</tr>'
    )


def bracket_html(bracket: dict, sport: str, team_colors: dict[str, str]) -> str:
    round_labels = {"r1": "Round 1", "r2": "Semis", "conf": "Conf. Final"}
    finals_label = "Stanley Cup Final" if sport == "NHL" else "NBA Finals"

    def conf_col(conf: str) -> str:
        rows = ""
        for rnd, label in round_labels.items():
            for s in bracket.get(conf, {}).get(rnd, []):
                rows += _series_row(s, label, team_colors)
        # Finals (shared, only show in east col)
        if conf == "east":
            for s in bracket.get("final", []):
                rows += _series_row(s, finals_label, team_colors)
        return (
            f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-spacing:0">'
            f'{rows}</table>'
        )

    conf_head = (f'font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
                 f'color:{MUTED};font-family:monospace;padding-bottom:8px;display:block')

    return (
        f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-spacing:0">'
        f'<tr>'
        f'<td style="width:48%;vertical-align:top;padding:0 16px 0 0;'
        f'border-right:1px solid {RULE}">'
        f'<span style="{conf_head}">Conferencia Este</span>'
        f'{conf_col("east")}</td>'
        f'<td style="width:4%"></td>'
        f'<td style="width:48%;vertical-align:top;padding:0 0 0 16px">'
        f'<span style="{conf_head}">Conferencia Oeste</span>'
        f'{conf_col("west")}</td>'
        f'</tr>'
        f'</table>'
    )


# ── Player rows ───────────────────────────────────────────────────

def player_list_html(players: list[dict],
                     score_key: str,
                     score_label: str,
                     meta_fn,
                     note_fn,
                     threshold: float | None = None) -> str:
    rows = ""
    for i, p in enumerate(players[:10], 1):
        primary = p.get("colors", {}).get("primary", "#666")
        score_val = p.get(score_key, 0)
        gap_txt = ""
        bar_html = ""
        if threshold:
            gap = round(threshold - score_val, 1)
            gap_txt = f' <span style="color:{MUTED};font-size:11px">/ {threshold} (−{gap})</span>' if gap > 0 else ""
            bar_html = f'<div style="margin-top:4px">{score_bar(score_val, threshold)}</div>'

        rows += (
            f'<tr style="border-bottom:1px solid {RULE}">'
            f'<td style="padding:11px 8px;font-size:18px;color:{MUTED};'
            f'font-variant-numeric:tabular-nums;width:28px;vertical-align:top">{i}</td>'
            f'<td style="padding:11px 8px 11px 0;vertical-align:top">'
            f'<div style="font-size:14px;font-weight:600;color:{INK}">'
            f'{swatch(primary)}{p.get("name","")}</div>'
            f'<div style="font-size:11px;color:{MUTED};font-family:monospace;margin-top:2px">'
            f'{meta_fn(p)}</div>'
            f'<div style="font-size:11px;color:{INK2};font-family:monospace;margin-top:2px">'
            f'{note_fn(p)}</div>'
            f'</td>'
            f'<td style="padding:11px 0 11px 8px;text-align:right;vertical-align:top;white-space:nowrap">'
            f'<div style="font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};'
            f'font-family:monospace">{score_label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:{ACCENT};'
            f'font-variant-numeric:tabular-nums">{score_val}{gap_txt}</div>'
            f'{bar_html}'
            f'</td>'
            f'</tr>'
        )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;border-collapse:collapse;background:{PAPER}">'
        f'{rows}</table>'
    )


def team_list_html(teams: list[dict],
                   score_key: str,
                   score_label: str,
                   meta_fn,
                   note_fn,
                   threshold: float | None = None) -> str:
    rows = ""
    for i, t in enumerate(teams[:10], 1):
        primary = t.get("colors", {}).get("primary", "#666")
        score_val = t.get(score_key, 0)
        gap_txt = ""
        bar_html = ""
        if threshold:
            gap = round(threshold - score_val, 1)
            gap_txt = f' <span style="color:{MUTED};font-size:11px">/ {threshold} (−{gap})</span>' if gap > 0 else ""
            bar_html = f'<div style="margin-top:4px">{score_bar(score_val, threshold)}</div>'

        name = t.get("city") or t.get("name", "")
        rows += (
            f'<tr style="border-bottom:1px solid {RULE}">'
            f'<td style="padding:11px 8px;font-size:18px;color:{MUTED};'
            f'font-variant-numeric:tabular-nums;width:28px;vertical-align:top">{i}</td>'
            f'<td style="padding:11px 8px 11px 0;vertical-align:top">'
            f'<div style="font-size:14px;font-weight:600;color:{INK}">'
            f'{swatch(primary)}{name}</div>'
            f'<div style="font-size:11px;color:{MUTED};font-family:monospace;margin-top:2px">'
            f'{meta_fn(t)}</div>'
            f'<div style="font-size:11px;color:{INK2};font-family:monospace;margin-top:2px">'
            f'{note_fn(t)}</div>'
            f'</td>'
            f'<td style="padding:11px 0 11px 8px;text-align:right;vertical-align:top;white-space:nowrap">'
            f'<div style="font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:{MUTED};'
            f'font-family:monospace">{score_label}</div>'
            f'<div style="font-size:22px;font-weight:700;color:{ACCENT};'
            f'font-variant-numeric:tabular-nums">{score_val}{gap_txt}</div>'
            f'{bar_html}'
            f'</td>'
            f'</tr>'
        )
    return (
        f'<table cellpadding="0" cellspacing="0" border="0" '
        f'style="width:100%;border-collapse:collapse;background:{PAPER}">'
        f'{rows}</table>'
    )


# ── Section wrapper ───────────────────────────────────────────────

def section(kicker: str, title: str, sub: str, body: str) -> str:
    return (
        f'<div style="border-top:1px solid {INK};padding:18px 28px 6px">'
        f'<div style="font-size:9px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{MUTED};font-family:monospace;margin-bottom:3px">{kicker}</div>'
        f'<div style="font-size:21px;font-weight:700;color:{INK};'
        f'letter-spacing:-.01em;margin-bottom:4px">{title}</div>'
        f'<div style="font-size:11px;color:{MUTED};font-family:monospace;'
        f'margin-bottom:14px">{sub}</div>'
        f'{body}'
        f'</div>'
    )


def sport_header(sport: str, season: str, last_update: str) -> str:
    top_border = f'border-top:4px solid {INK}'
    return (
        f'<div style="background:{PAPER};{top_border};border-bottom:1px solid {INK};'
        f'padding:18px 28px 20px">'
        f'<div style="font-size:9px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{MUTED};font-family:monospace;margin-bottom:4px">{sport} Tracker · {season}</div>'
        f'<div style="font-size:42px;font-weight:700;color:{INK};letter-spacing:-.02em;'
        f'line-height:1">{sport} Playoffs</div>'
        f'<div style="font-size:11px;color:{MUTED};font-family:monospace;margin-top:6px">'
        f'Actualizado {last_update}</div>'
        f'</div>'
    )


# ── NHL ───────────────────────────────────────────────────────────

def nhl_html(d: dict) -> str:
    team_map   = {t["code"]: t for t in d.get("TEAMS", [])}
    players    = d.get("PLAYERS", [])
    bracket    = d.get("BRACKET", {})
    rtg        = d.get("ROAD_TO_GLORY", {})
    team_colors = {code: t["colors"]["primary"] for code, t in team_map.items()}

    top        = sorted(players, key=lambda p: -p["score"])[:10]
    p_thresh   = rtg.get("playerThreshold")
    t_thresh   = rtg.get("teamThreshold")

    def p_meta(p):
        tn  = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        age = f" · {p['age']} años" if p.get("age") else ""
        return f"{p.get('country','NHL')} · {p.get('pos','')} · {tn}{age}"

    def p_note(p):
        if p.get("pos") == "G":
            return f"{p.get('stats',{}).get('svpct',0):.3f} SV%"
        st = p.get("stats", {})
        return f"{st.get('p',0)} P · {st.get('g',0)} G · {st.get('a',0)} A"

    def rtg_p_meta(p):
        tn  = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        cups = p.get("cups", 0)
        seas = p.get("seasons", "?")
        return f"{p.get('country','NHL')} · {p.get('pos','')} · {tn} · {seas} temp · {cups} Cups"

    def rtg_y_meta(p):
        tn = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        return f"{p.get('country','NHL')} · {p.get('pos','')} · {tn} · score actual {p.get('currentScore','?')}"

    def rtg_t_meta(t):
        cups = t.get("cups", 0)
        return f"{t.get('era','')} · {cups} Cup{'s' if cups != 1 else ''} · {t.get('note','')}"

    return (
        sport_header("NHL", d.get("SEASON",""), d.get("LAST_UPDATE",""))
        + section("Playoff bracket", "Camino a la Stanley Cup",
                  "Series al mejor de siete.",
                  bracket_html(bracket, "NHL", team_colors))
        + section("Top performers", "Top 10 de la temporada",
                  "Score percentil por posición — skaters y porteros.",
                  player_list_html(top, "score", "Score", p_note, p_meta))
        + section("Road to Glory · Jugadores",
                  f"Top 10 Road to Glory",
                  f"Umbral histórico top 10: {p_thresh}.",
                  player_list_html(rtg.get("players",[])[:10], "careerScore", "Career",
                                   lambda p: p.get("note",""), rtg_p_meta, p_thresh))
        + section("Road to Glory · Jóvenes (≤25)",
                  "Top 10 Jóvenes",
                  "Proyección de carrera para menores de 25.",
                  player_list_html(rtg.get("youngProspects",[])[:10], "projectedScore", "Proj.",
                                   lambda p: p.get("note",""), rtg_y_meta, p_thresh))
        + section("Road to Glory · Franquicias",
                  "Top 10 Franquicias",
                  f"Umbral histórico top 10: {t_thresh}.",
                  team_list_html(rtg.get("teams",[])[:10], "dynastyScore", "Dynasty",
                                 rtg_t_meta, lambda t: t.get("needs",""), t_thresh))
    )


# ── NBA ───────────────────────────────────────────────────────────

def nba_html(d: dict) -> str:
    team_map    = {t["code"]: t for t in d.get("TEAMS", [])}
    players     = d.get("PLAYERS", [])
    bracket     = d.get("BRACKET", {})
    rtg         = d.get("ROAD_TO_GLORY", {})
    team_colors = {code: t["colors"]["primary"] for code, t in team_map.items()}

    top       = sorted(players, key=lambda p: -p["score"])[:10]
    p_thresh  = rtg.get("playerThreshold")
    t_thresh  = rtg.get("teamThreshold")

    def p_meta(p):
        tn  = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        age = f" · {p['age']} años" if p.get("age") else ""
        return f"NBA · {p.get('pos','')} · {tn}{age}"

    def p_note(p):
        st = p.get("stats", {})
        return f"{st.get('pts',0)} PPG · {st.get('reb',0)} REB · {st.get('ast',0)} AST"

    def rtg_p_meta(p):
        tn    = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        rings = p.get("rings", 0)
        return f"NBA · {p.get('pos','')} · {tn} · {rings} ring{'s' if rings != 1 else ''}"

    def rtg_y_meta(p):
        tn = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        return f"NBA · {p.get('pos','')} · {tn} · score actual {p.get('currentScore','?')}"

    def rtg_t_meta(t):
        rings = t.get("rings", 0)
        return f"{t.get('era','')} · {rings} ring{'s' if rings != 1 else ''} · {t.get('note','')}"

    return (
        f'<div style="margin-top:32px"></div>'
        + sport_header("NBA", d.get("SEASON",""), d.get("LAST_UPDATE",""))
        + section("Playoff bracket", "Camino a las NBA Finals",
                  "Series al mejor de siete.",
                  bracket_html(bracket, "NBA", team_colors))
        + section("Top performers", "Top 10 de la temporada",
                  "Score percentil — pts, reb, ast, stl, blk ponderados.",
                  player_list_html(top, "score", "Score", p_note, p_meta))
        + section("Road to Glory · Jugadores",
                  "Top 10 Road to Glory",
                  f"Umbral histórico top 10: {p_thresh} (Tim Duncan).",
                  player_list_html(rtg.get("players",[])[:10], "careerScore", "Career",
                                   lambda p: p.get("note",""), rtg_p_meta, p_thresh))
        + section("Road to Glory · Jóvenes (≤25)",
                  "Top 10 Jóvenes",
                  "Proyección de carrera para menores de 25.",
                  player_list_html(rtg.get("youngProspects",[])[:10], "projectedScore", "Proj.",
                                   lambda p: p.get("note",""), rtg_y_meta, p_thresh))
        + section("Road to Glory · Franquicias",
                  "Top 10 Franquicias",
                  f"Umbral histórico top 10: {t_thresh} (Celtics 07-08).",
                  team_list_html(rtg.get("teams",[])[:10], "dynastyScore", "Dynasty",
                                 rtg_t_meta, lambda t: t.get("needs",""), t_thresh))
    )


MLB_DIV_ORDER = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]
MLB_TEAM_DIV = {
    "NYY":"AL East", "BOS":"AL East", "TOR":"AL East", "TB":"AL East",  "BAL":"AL East",
    "CWS":"AL Central","CLE":"AL Central","DET":"AL Central","KC":"AL Central","MIN":"AL Central",
    "HOU":"AL West",  "LAA":"AL West",  "ATH":"AL West",  "SEA":"AL West",  "TEX":"AL West",
    "ATL":"NL East",  "MIA":"NL East",  "NYM":"NL East",  "PHI":"NL East",  "WSH":"NL East",
    "CHC":"NL Central","CIN":"NL Central","MIL":"NL Central","PIT":"NL Central","STL":"NL Central",
    "LAD":"NL West",  "ARI":"NL West",  "COL":"NL West",  "SF":"NL West",   "SD":"NL West",
}


def mlb_html(d: dict) -> str:
    team_map    = {t["code"]: t for t in d.get("TEAMS", [])}
    players     = d.get("PLAYERS", [])
    bracket     = d.get("BRACKET", {})
    rtg         = d.get("ROAD_TO_GLORY", {})
    team_colors = {code: t["colors"]["primary"] for code, t in team_map.items()}

    pitchers = sorted([p for p in players if p.get("stats", {}).get("type") == "pitching"], key=lambda p: -p["score"])[:10]
    batters  = sorted([p for p in players if p.get("stats", {}).get("type") == "batting"],  key=lambda p: -p["score"])[:10]
    p_thresh = rtg.get("playerThreshold")
    t_thresh = rtg.get("teamThreshold")

    def p_meta(p):
        tn  = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        age = f" · {p['age']} años" if p.get("age") else ""
        return f"MLB · {p.get('pos','')} · {tn}{age}"

    def p_note(p):
        st = p.get("stats", {})
        if st.get("type") == "pitching":
            return f"{st.get('era','-')} ERA · {st.get('so',0)} K · {st.get('w',0)} W"
        avg = st.get("avg", 0)
        avg_str = f".{str(int(round(avg * 1000))).zfill(3)}" if avg else ".000"
        return f"{avg_str} AVG · {st.get('hr',0)} HR · {st.get('rbi',0)} RBI"

    def rtg_p_meta(p):
        tn    = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        rings = p.get("rings", 0)
        return f"MLB · {p.get('pos','')} · {tn} · {rings} ring{'s' if rings != 1 else ''}"

    def rtg_y_meta(p):
        tn = team_map.get(p["teamCode"], {}).get("commonName", p["teamCode"])
        return f"MLB · {p.get('pos','')} · {tn} · score actual {p.get('currentScore','?')}"

    def rtg_t_meta(t):
        rings = t.get("rings", 0)
        return f"{t.get('era','')} · {rings} ring{'s' if rings != 1 else ''} · {t.get('note','')}"

    # Standings by division (regular season) or bracket (postseason)
    ws_list = bracket.get("ws", [{}])
    al_lcs  = bracket.get("al", {}).get("lcs", [{}])
    nl_lcs  = bracket.get("nl", {}).get("lcs", [{}])
    has_playoffs = ((ws_list or [{}])[0].get("hi") or
                    (al_lcs or [{}])[0].get("hi") or
                    (nl_lcs or [{}])[0].get("hi"))

    def mlb_standings_html() -> str:
        # Group teams by division
        div_map: dict[str, list] = {div: [] for div in MLB_DIV_ORDER}
        for t in d.get("TEAMS", []):
            div = MLB_TEAM_DIV.get(t["code"], t.get("div", "Other"))
            if div in div_map:
                div_map[div].append(t)
        for div in div_map:
            div_map[div].sort(key=lambda t: (-t["w"], t["l"]))

        div_head = (f'font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
                    f'color:{MUTED};font-family:monospace;padding:8px 0 4px;'
                    f'border-bottom:1px solid {RULE};display:block;margin-bottom:2px')
        cell_style = f'vertical-align:top;width:48%;padding-bottom:16px'

        def div_col(divs: list[str]) -> str:
            out = ""
            for div in divs:
                out += f'<span style="{div_head}">{div}</span>'
                for i, t in enumerate(div_map.get(div, []), 1):
                    pct = f".{str(int(round(t['winPct']*1000))).zfill(3)}"
                    rd_str = f"+{t['rd']}" if t["rd"] > 0 else str(t["rd"])
                    out += (
                        f'<table cellpadding="0" cellspacing="0" border="0" '
                        f'style="width:100%;border-spacing:0;padding:4px 0">'
                        f'<tr>'
                        f'<td style="width:20px;color:{MUTED};font-size:11px;font-family:monospace">{i}</td>'
                        f'<td style="padding:0 4px">{swatch(t["colors"]["primary"], 8)}'
                        f'<span style="font-size:13px;font-weight:600;color:{INK}">{t["shortName"]}</span></td>'
                        f'<td style="text-align:right;font-size:12px;font-family:monospace;color:{INK2};white-space:nowrap">'
                        f'{t["w"]}–{t["l"]} <span style="color:{MUTED}">{pct}</span></td>'
                        f'</tr></table>'
                    )
            return out

        al_divs = [d for d in MLB_DIV_ORDER if d.startswith("AL")]
        nl_divs = [d for d in MLB_DIV_ORDER if d.startswith("NL")]
        return (
            f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-spacing:0">'
            f'<tr>'
            f'<td style="{cell_style};padding-right:16px;border-right:1px solid {RULE}">'
            f'{div_col(al_divs)}</td>'
            f'<td style="width:4%"></td>'
            f'<td style="{cell_style};padding-left:16px">{div_col(nl_divs)}</td>'
            f'</tr></table>'
        )

    def mlb_bracket_html() -> str:
        round_labels = {"wc": "Wild Card", "ds": "Div. Series", "lcs": "LCS"}
        def conf_col(conf: str) -> str:
            rows = ""
            for rnd, label in round_labels.items():
                for s in bracket.get(conf, {}).get(rnd, []):
                    rows += _series_row(s, label, team_colors)
            if conf == "al":
                for s in bracket.get("ws", []):
                    rows += _series_row(s, "World Series", team_colors)
            return (f'<table cellpadding="0" cellspacing="0" border="0" '
                    f'style="width:100%;border-spacing:0">{rows}</table>')
        conf_head = (f'font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
                     f'color:{MUTED};font-family:monospace;padding-bottom:8px;display:block')
        return (
            f'<table cellpadding="0" cellspacing="0" border="0" style="width:100%;border-spacing:0">'
            f'<tr>'
            f'<td style="width:48%;vertical-align:top;padding:0 16px 0 0;border-right:1px solid {RULE}">'
            f'<span style="{conf_head}">American League</span>{conf_col("al")}</td>'
            f'<td style="width:4%"></td>'
            f'<td style="width:48%;vertical-align:top;padding:0 0 0 16px">'
            f'<span style="{conf_head}">National League</span>{conf_col("nl")}</td>'
            f'</tr></table>'
        )

    standings_or_bracket = (
        section("Playoff bracket", "Camino a las World Series",
                "Wild Card (3) → Div. Series (5) → LCS (7) → World Series (7).",
                mlb_bracket_html())
        if has_playoffs else
        section("Clasificación", f"MLB {d.get('SEASON','')} · Standings por división",
                "Temporada regular — ordenados por W dentro de cada división.",
                mlb_standings_html())
    )

    return (
        f'<div style="margin-top:32px"></div>'
        + sport_header("MLB", d.get("SEASON",""), d.get("LAST_UPDATE",""))
        + standings_or_bracket
        + section("Top pitchers", "Top 10 pitchers de la temporada",
                  "Score percentil — ERA, K, W, WHIP ponderados.",
                  player_list_html(pitchers, "score", "Score", p_note, p_meta))
        + section("Top batters", "Top 10 batters de la temporada",
                  "Score percentil — HR, RBI, AVG, SB, OPS ponderados.",
                  player_list_html(batters, "score", "Score", p_note, p_meta))
        + section("Road to Glory · Jugadores",
                  "Top 10 Road to Glory",
                  f"Umbral histórico top 10: {p_thresh} (Rogers Hornsby).",
                  player_list_html(rtg.get("players",[])[:10], "careerScore", "Career",
                                   lambda p: p.get("note",""), rtg_p_meta, p_thresh))
        + section("Road to Glory · Jóvenes (≤25)",
                  "Top 10 Jóvenes",
                  "Proyección de carrera para menores de 25.",
                  player_list_html(rtg.get("youngProspects",[])[:10], "projectedScore", "Proj.",
                                   lambda p: p.get("note",""), rtg_y_meta, p_thresh))
        + section("Road to Glory · Franquicias",
                  "Top 10 Franquicias",
                  f"Umbral histórico top 10: {t_thresh} (Astros 2017).",
                  team_list_html(rtg.get("teams",[])[:10], "dynastyScore", "Dynasty",
                                 rtg_t_meta, lambda t: t.get("needs",""), t_thresh))
    )


# ── Assemble ──────────────────────────────────────────────────────

def build_email(nhl: dict, nba: dict, mlb: dict) -> str:
    today = date.today().strftime("%-d de %B de %Y")
    body  = nhl_html(nhl) + (nba_html(nba) if nba else "") + (mlb_html(mlb) if mlb else "")
    footer = (
        f'<div style="background:{BG};border-top:1px solid #d5d2ce;padding:16px 28px;'
        f'font-size:10px;color:{MUTED};font-family:monospace">'
        f'NHL + NBA + MLB Tracker &nbsp;·&nbsp; {today} &nbsp;·&nbsp; '
        f'scripts/send_newsletter.py'
        f'</div>'
    )
    return (
        f'<!doctype html><html lang="es"><head>'
        f'<meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>Tracker Newsletter</title>'
        f'</head>'
        f'<body style="margin:0;padding:0;background:{BG};'
        f'font-family:Arial,Helvetica,sans-serif;font-size:14px;color:{INK}">'
        f'<div style="max-width:680px;margin:0 auto;background:{PAPER}">'
        f'{body}{footer}'
        f'</div>'
        f'</body></html>'
    )


# ── Main ──────────────────────────────────────────────────────────

def main() -> int:
    load_env()

    # Update all data first — independent of email password
    print("Actualizando datos NHL…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update_data.py")], check=True)

    print("Actualizando datos NBA…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update_nba_data.py")], check=True)

    print("Actualizando datos MLB…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update_mlb_data.py")], check=True)

    print("Actualizando datos NFL…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "update_nfl_data.py")], check=True)

    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not password:
        print(
            "Datos actualizados. GMAIL_APP_PASSWORD no configurado — newsletter no enviada.\n"
            "  Añade esta línea a .env:\n"
            "  GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxxxxxx",
            file=sys.stderr,
        )
        return 0  # exit 0: data updated successfully, email skipped

    nhl = load_js_data(ROOT / "data.js")
    nba = load_js_data(ROOT / "nba_data.js")
    mlb = load_js_data(ROOT / "mlb_data.js")

    if not nhl:
        print("Error: data.js vacío.", file=sys.stderr)
        return 1

    html    = build_email(nhl, nba, mlb)
    today   = date.today().strftime("%d %b %Y")
    subject = f"NHL + NBA + MLB Tracker · {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html, "html", "utf-8"))

    print(f"Enviando a {RECIPIENT}…")
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(SENDER, password)
        smtp.sendmail(SENDER, RECIPIENT, msg.as_string())

    print(f"Newsletter enviada · {subject}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
