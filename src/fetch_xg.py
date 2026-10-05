"""Understat nyilvános adat – csapat xG (API kulcs nélkül)."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Any

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://understat.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# ESPN liga kulcs -> Understat liga kód
UNDERSTAT_LEAGUES: dict[str, str] = {
    "eng.1": "EPL",
    "esp.1": "La_liga",
    "ger.1": "Bundesliga",
    "ita.1": "Serie_A",
    "fra.1": "Ligue_1",
}

# Ismert eltérések (ESPN / Understat név)
ALIASES: dict[str, str] = {
    "brighton hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "tottenham hotspur": "Tottenham",
    "wolverhampton wanderers": "Wolverhampton Wanderers",
    "west ham united": "West Ham",
    "newcastle united": "Newcastle United",
    "manchester united": "Manchester United",
    "manchester city": "Manchester City",
    "nottingham forest": "Nottingham Forest",
    "leicester city": "Leicester",
    "leeds united": "Leeds",
    "inter milan": "Inter",
    "ac milan": "Milan",
    "paris saint germain": "Paris Saint Germain",
    "bayern munich": "Bayern Munich",
    "borussia dortmund": "Borussia Dortmund",
    "rb leipzig": "RasenBallsport Leipzig",
}


def current_season_start_year() -> str:
    now = datetime.now(timezone.utc)
    start = now.year if now.month >= 7 else now.year - 1
    return str(start)


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _aggregate_team(history: list[dict[str, Any]]) -> dict[str, float]:
    if not history:
        return {"games": 0, "xg_for": 0.0, "xg_against": 0.0, "home_xg_for": 0.0, "away_xg_for": 0.0}

    n = len(history)
    xg_for = sum(float(m.get("xG") or 0) for m in history) / n
    xg_against = sum(float(m.get("xGA") or 0) for m in history) / n

    home = [m for m in history if m.get("h_a") == "h"]
    away = [m for m in history if m.get("h_a") == "a"]
    home_xg = sum(float(m.get("xG") or 0) for m in home) / len(home) if home else xg_for
    away_xg = sum(float(m.get("xG") or 0) for m in away) / len(away) if away else xg_for

    return {
        "games": n,
        "xg_for": round(xg_for, 3),
        "xg_against": round(xg_against, 3),
        "home_xg_for": round(home_xg, 3),
        "away_xg_for": round(away_xg, 3),
    }


def fetch_league_xg(understat_league: str, season: str | None = None) -> dict[str, dict[str, Any]]:
    season = season or current_season_start_year()
    url = f"https://understat.com/getLeagueData/{understat_league}/{season}"
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()

    by_key: dict[str, dict[str, Any]] = {}
    for team_blob in (payload.get("teams") or {}).values():
        title = team_blob.get("title") or ""
        if not title:
            continue
        stats = _aggregate_team(team_blob.get("history") or [])
        entry = {"name": title, **stats}
        by_key[_normalize(title)] = entry
    return by_key


def fetch_xg_for_leagues(league_keys: list[str], season: str | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Vissza: espn_league_key -> normalized_team_name -> stats."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for key in league_keys:
        u_league = UNDERSTAT_LEAGUES.get(key)
        if not u_league:
            continue
        try:
            out[key] = fetch_league_xg(u_league, season=season)
            print(f"  xG: {key} ({u_league}) – {len(out[key])} csapat")
        except requests.RequestException as exc:
            print(f"  xG hiba ({key}): {exc}")
            out[key] = {}
    return out


def resolve_team(
    espn_name: str,
    league_teams: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    norm = _normalize(espn_name)
    if norm in ALIASES:
        norm = _normalize(ALIASES[norm])

    if norm in league_teams:
        return league_teams[norm]

    # alias kulcs alapján
    for alias_norm, understat_name in ALIASES.items():
        if alias_norm in norm or norm in alias_norm:
            candidate = _normalize(understat_name)
            if candidate in league_teams:
                return league_teams[candidate]

    keys = list(league_teams.keys())
    match = get_close_matches(norm, keys, n=1, cutoff=0.72)
    if match:
        return league_teams[match[0]]

    # display name fuzzy
    display_map = {_normalize(v["name"]): v for v in league_teams.values()}
    match2 = get_close_matches(norm, list(display_map.keys()), n=1, cutoff=0.72)
    if match2:
        return display_map[match2[0]]
    return None
