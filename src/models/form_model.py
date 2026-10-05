"""Form modell – utolsó 5 meccs pont/gól hatása."""

from __future__ import annotations

from typing import Any

from src.models.profiles import team_profile


def _form_factor(ppg: float) -> float:
    return max(0.88, min(1.12, 0.90 + 0.08 * (float(ppg) / 1.5)))


def _form_goals_boost(goals_for: float, league_avg: float = 1.35) -> float:
    if league_avg <= 0:
        return 1.0
    return max(0.85, min(1.15, goals_for / league_avg))


def expected_lambdas(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    *,
    home_advantage: float = 1.08,
    base_home: float = 1.35,
    base_away: float = 1.15,
) -> tuple[float, float, dict[str, Any]]:
    home = team_profile(home_stats, "home")
    away = team_profile(away_stats, "away")

    lam_home = base_home * _form_factor(home["form_ppg"]) * _form_goals_boost(home["goals_for"])
    lam_away = base_away * _form_factor(away["form_ppg"]) * _form_goals_boost(away["goals_for"])

    # ellenfél forma → védelem gyengül/erősül
    lam_home *= max(0.92, min(1.08, 1.05 - (away["form_ppg"] - 1.0) * 0.04))
    lam_away *= max(0.92, min(1.08, 1.05 - (home["form_ppg"] - 1.0) * 0.04))

    lam_home = max(0.15, lam_home * home_advantage)
    lam_away = max(0.15, lam_away)

    meta = {
        "home_form": home["form_string"],
        "away_form": away["form_string"],
        "home_form_ppg": home["form_ppg"],
        "away_form_ppg": away["form_ppg"],
        "home_goals_for": home["goals_for"],
        "away_goals_for": away["goals_for"],
    }
    return round(lam_home, 3), round(lam_away, 3), meta
