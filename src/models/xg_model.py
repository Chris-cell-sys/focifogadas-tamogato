"""xG modell – open-play xG/xGA + támadási egyensúly."""

from __future__ import annotations

from typing import Any

from src.models.profiles import _blend, team_profile


def _attack_tilt(balance: float) -> float:
    return max(0.92, min(1.08, 0.85 + 0.3 * float(balance)))


def expected_lambdas(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    *,
    home_advantage: float = 1.08,
) -> tuple[float, float, dict[str, Any]]:
    home = team_profile(home_stats, "home")
    away = team_profile(away_stats, "away")

    raw_home = _blend(
        (home["op_xg_for"] + away["op_xga"]) / 2.0,
        (home["total_xg"] + away["total_xga"]) / 2.0,
        0.75,
    )
    raw_away = _blend(
        (away["op_xg_for"] + home["op_xga"]) / 2.0,
        (away["total_xg"] + home["total_xga"]) / 2.0,
        0.75,
    )

    lam_home = max(0.15, raw_home * home_advantage * _attack_tilt(home["attack_balance"]))
    lam_away = max(0.15, raw_away * _attack_tilt(away["attack_balance"]))

    if home["attack_balance"] > 0.55 and away["attack_balance"] > 0.55:
        lam_home *= 1.03
        lam_away *= 1.03

    meta = {
        "home_op_xg": home["op_xg_for"],
        "home_op_xga": home["op_xga"],
        "away_op_xg": away["op_xg_for"],
        "away_op_xga": away["op_xga"],
        "home_balance": home["attack_balance"],
        "away_balance": away["attack_balance"],
    }
    return round(lam_home, 3), round(lam_away, 3), meta
