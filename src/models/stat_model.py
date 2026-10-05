"""Stat modell – szezon teljesítmény (gól/xG átlag) → várható gólok."""

from __future__ import annotations

from typing import Any

from src.models.profiles import team_profile


def expected_lambdas(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    *,
    home_advantage: float = 1.08,
) -> tuple[float, float, dict[str, Any]]:
    home = team_profile(home_stats, "home")
    away = team_profile(away_stats, "away")

    # szezon szintű támadás vs ellenfél védelem (forma nélkül)
    home_attack = (home["season_home_xg"] + home["goals_for"]) / 2.0
    away_attack = (away["season_away_xg"] + away["goals_for"]) / 2.0
    home_def = (home["season_xg_against"] + home["goals_against"]) / 2.0
    away_def = (away["season_xg_against"] + away["goals_against"]) / 2.0

    lam_home = max(0.15, ((home_attack + away_def) / 2.0) * home_advantage)
    lam_away = max(0.15, (away_attack + home_def) / 2.0)

    meta = {
        "home_attack": round(home_attack, 3),
        "away_attack": round(away_attack, 3),
        "home_def": round(home_def, 3),
        "away_def": round(away_def, 3),
    }
    return round(lam_home, 3), round(lam_away, 3), meta
