"""Understat nyilvános adat – csapat xG, forma, góltermelés (API kulcs nélkül)."""

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


def _parse_match_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace(" ", "T"))
    except Exception:
        return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _slice_stats(matches: list[dict[str, Any]], prefix: str = "") -> dict[str, Any]:
    """Átlagok egy meccsszeletre. Open play ≈ Understat npxG / npxGA."""
    if not matches:
        empty = {
            f"{prefix}games": 0,
            f"{prefix}xg_for": None,
            f"{prefix}xg_against": None,
            f"{prefix}op_xg_for": None,
            f"{prefix}op_xga": None,
            f"{prefix}goals_for": None,
            f"{prefix}goals_against": None,
            f"{prefix}attack_balance": None,
            f"{prefix}form_pts": 0,
            f"{prefix}form_ppg": None,
            f"{prefix}form_string": "",
        }
        return empty

    xg = [float(m.get("xG") or 0) for m in matches]
    xga = [float(m.get("xGA") or 0) for m in matches]
    op_xg = [float(m.get("npxG") or m.get("xG") or 0) for m in matches]
    op_xga = [float(m.get("npxGA") or m.get("xGA") or 0) for m in matches]
    gf = [float(m.get("scored") or 0) for m in matches]
    ga = [float(m.get("missed") or 0) for m in matches]
    pts = [int(m.get("pts") or 0) for m in matches]
    form_chars = []
    for m in matches:
        r = (m.get("result") or "").lower()
        form_chars.append({"w": "W", "d": "D", "l": "L"}.get(r, "?"))

    avg_op_xg = _avg(op_xg) or 0.0
    avg_op_xga = _avg(op_xga) or 0.0
    denom = avg_op_xg + avg_op_xga
    attack_balance = round(avg_op_xg / denom, 3) if denom > 0 else 0.5

    return {
        f"{prefix}games": len(matches),
        f"{prefix}xg_for": round(_avg(xg) or 0.0, 3),
        f"{prefix}xg_against": round(_avg(xga) or 0.0, 3),
        f"{prefix}op_xg_for": round(avg_op_xg, 3),
        f"{prefix}op_xga": round(avg_op_xga, 3),
        f"{prefix}goals_for": round(_avg(gf) or 0.0, 3),
        f"{prefix}goals_against": round(_avg(ga) or 0.0, 3),
        f"{prefix}attack_balance": attack_balance,
        f"{prefix}form_pts": sum(pts),
        f"{prefix}form_ppg": round(sum(pts) / len(matches), 3),
        f"{prefix}form_string": "".join(form_chars),
    }


def _aggregate_team(history: list[dict[str, Any]], last_n: int = 5) -> dict[str, Any]:
    if not history:
        return {
            "games": 0,
            "xg_for": 0.0,
            "xg_against": 0.0,
            "home_xg_for": 0.0,
            "away_xg_for": 0.0,
            "op_xg_for": 0.0,
            "op_xga": 0.0,
            "goals_for": 0.0,
            "goals_against": 0.0,
            "attack_balance": 0.5,
            "form_string": "",
            "form_pts": 0,
            "form_ppg": 0.0,
            "last5": {},
            "home_split": {},
            "away_split": {},
            "last5_home": {},
            "last5_away": {},
        }

    ordered = sorted(
        history,
        key=lambda m: _parse_match_date(m.get("date")) or datetime.min,
    )
    last = ordered[-last_n:] if len(ordered) >= last_n else ordered
    home_all = [m for m in ordered if m.get("h_a") == "h"]
    away_all = [m for m in ordered if m.get("h_a") == "a"]
    last_home = [m for m in last if m.get("h_a") == "h"]
    last_away = [m for m in last if m.get("h_a") == "a"]
    # ha az utolsó 5-ben kevés hazai/vendég van, egészítsük ki a szezonbeli megfelelő helyszínnel
    if len(last_home) < 2:
        last_home = home_all[-last_n:] if home_all else last_home
    if len(last_away) < 2:
        last_away = away_all[-last_n:] if away_all else last_away

    overall = _slice_stats(ordered)
    last5_dict = _slice_stats(last)
    home_split = _slice_stats(home_all[-last_n:] if home_all else [])
    away_split = _slice_stats(away_all[-last_n:] if away_all else [])
    last5_home = _slice_stats(last_home)
    last5_away = _slice_stats(last_away)

    return {
        "games": overall["games"],
        "xg_for": overall["xg_for"],
        "xg_against": overall["xg_against"],
        "home_xg_for": home_split.get("xg_for") or overall["xg_for"],
        "away_xg_for": away_split.get("xg_for") or overall["xg_for"],
        "op_xg_for": overall["op_xg_for"],
        "op_xga": overall["op_xga"],
        "goals_for": overall["goals_for"],
        "goals_against": overall["goals_against"],
        "attack_balance": overall["attack_balance"],
        "form_string": last5_dict.get("form_string") or "",
        "form_pts": last5_dict.get("form_pts") or 0,
        "form_ppg": last5_dict.get("form_ppg") or 0.0,
        "last5": last5_dict,
        "home_split": home_split,
        "away_split": away_split,
        "last5_home": last5_home,
        "last5_away": last5_away,
        **{f"l5_{k}": v for k, v in last5_dict.items()},
    }


def fetch_league_xg(understat_league: str, season: str | None = None, retries: int = 3) -> dict[str, dict[str, Any]]:
    season = season or current_season_start_year()
    url = f"https://understat.com/getLeagueData/{understat_league}/{season}"
    last_exc: Exception | None = None
    payload = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=45)
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException as exc:
            last_exc = exc
            if attempt + 1 < retries:
                continue
            raise last_exc
    assert payload is not None

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

    for alias_norm, understat_name in ALIASES.items():
        if alias_norm in norm or norm in alias_norm:
            candidate = _normalize(understat_name)
            if candidate in league_teams:
                return league_teams[candidate]

    keys = list(league_teams.keys())
    match = get_close_matches(norm, keys, n=1, cutoff=0.72)
    if match:
        return league_teams[match[0]]

    display_map = {_normalize(v["name"]): v for v in league_teams.values()}
    match2 = get_close_matches(norm, list(display_map.keys()), n=1, cutoff=0.72)
    if match2:
        return display_map[match2[0]]
    return None
