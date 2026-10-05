"""Poisson piacok – 1X2, BTTS, O/U 2.5."""

from __future__ import annotations

import math
from typing import Any


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def match_outcome_probs(home_lambda: float, away_lambda: float, max_goals: int = 8) -> tuple[float, float, float]:
    p_home = p_draw = p_away = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson_pmf(h, home_lambda) * _poisson_pmf(a, away_lambda)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away or 1.0
    return p_home / total, p_draw / total, p_away / total


def over_under_25_probs(home_lambda: float, away_lambda: float, max_goals: int = 8) -> tuple[float, float]:
    under = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            if h + a <= 2:
                under += _poisson_pmf(h, home_lambda) * _poisson_pmf(a, away_lambda)
    under = min(1.0, max(0.0, under))
    return 1.0 - under, under


def btts_probs(home_lambda: float, away_lambda: float, max_goals: int = 8) -> tuple[float, float]:
    p_home_score = 1.0 - _poisson_pmf(0, home_lambda)
    p_away_score = 1.0 - _poisson_pmf(0, away_lambda)
    yes = p_home_score * p_away_score
    return yes, 1.0 - yes


def market_probabilities(lam_h: float, lam_a: float) -> dict[str, float]:
    p1, px, p2 = match_outcome_probs(lam_h, lam_a)
    over, under = over_under_25_probs(lam_h, lam_a)
    btts_yes, btts_no = btts_probs(lam_h, lam_a)
    return {
        "1": p1,
        "X": px,
        "2": p2,
        "BTTS Igen": btts_yes,
        "BTTS Nem": btts_no,
        "O2.5": over,
        "U2.5": under,
    }


def build_market_options(
    home_name: str,
    away_name: str,
    probs: dict[str, float],
    *,
    prob_key: str = "prob",
) -> list[dict[str, Any]]:
    labels = [
        ("1X2", f"Hazai győzelem ({home_name})", "1"),
        ("1X2", "Döntetlen", "X"),
        ("1X2", f"Vendég győzelem ({away_name})", "2"),
        ("BTTS", "Mindkét csapat szerez gólt (Igen)", "BTTS Igen"),
        ("BTTS", "Mindkét csapat szerez gólt (Nem)", "BTTS Nem"),
        ("Gólok", "Over 2.5 gól", "O2.5"),
        ("Gólok", "Under 2.5 gól", "U2.5"),
    ]
    out: list[dict[str, Any]] = []
    for market, pick, short in labels:
        prob = float(probs.get(short) or 0)
        out.append(
            {
                "market": market,
                "pick": pick,
                "short": short,
                prob_key: prob,
                "prob_pct": round(prob * 100, 1),
                "fair_odds": round(1.0 / prob, 2) if prob > 0.01 else None,
            }
        )
    return out
