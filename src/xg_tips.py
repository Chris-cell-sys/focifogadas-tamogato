"""xG alapú meccs-model és fogadási tippek."""

from __future__ import annotations

import math
from typing import Any

from src.fetch_xg import resolve_team


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
    total = p_home + p_draw + p_away
    if total <= 0:
        return 1 / 3, 1 / 3, 1 / 3
    return p_home / total, p_draw / total, p_away / total


def expected_lambdas(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    *,
    home_advantage: float = 1.08,
) -> tuple[float, float]:
    home_attack = home_stats.get("home_xg_for") or home_stats.get("xg_for") or 1.2
    away_attack = away_stats.get("away_xg_for") or away_stats.get("xg_for") or 1.2
    home_def = home_stats.get("xg_against") or 1.2
    away_def = away_stats.get("xg_against") or 1.2

    lam_home = max(0.15, ((home_attack + away_def) / 2.0) * home_advantage)
    lam_away = max(0.15, (away_attack + home_def) / 2.0)
    return round(lam_home, 3), round(lam_away, 3)


def _ev_pct(prob: float, odds: float | None) -> float | None:
    if odds is None or odds <= 1 or prob <= 0:
        return None
    return round((prob * odds - 1.0) * 100.0, 2)


def build_xg_tip_for_match(
    match: dict[str, Any],
    league_xg: dict[str, dict[str, Any]],
    *,
    min_edge_pct: float = 3.0,
    home_advantage: float = 1.08,
) -> dict[str, Any] | None:
    home_name = match.get("home_team") or ""
    away_name = match.get("away_team") or ""
    home_stats = resolve_team(home_name, league_xg)
    away_stats = resolve_team(away_name, league_xg)
    if not home_stats or not away_stats:
        return None

    lam_h, lam_a = expected_lambdas(home_stats, away_stats, home_advantage=home_advantage)
    p1, px, p2 = match_outcome_probs(lam_h, lam_a)

    best_odds = match.get("best_odds") or {}
    outcomes = [
        ("1 (Hazai)", home_name, p1, (best_odds.get(home_name) or {}).get("odds")),
        ("X (Döntetlen)", "Draw", px, (best_odds.get("Draw") or {}).get("odds")),
        ("2 (Vendég)", away_name, p2, (best_odds.get(away_name) or {}).get("odds")),
    ]

    options = []
    for label, key, prob, odds in outcomes:
        ev = _ev_pct(prob, odds)
        fair = round(1.0 / prob, 2) if prob > 0 else None
        book = None
        if key == home_name:
            book = (best_odds.get(home_name) or {}).get("bookmaker")
        elif key == away_name:
            book = (best_odds.get(away_name) or {}).get("bookmaker")
        elif key == "Draw":
            book = (best_odds.get("Draw") or {}).get("bookmaker")
        options.append(
            {
                "pick": label,
                "prob_pct": round(prob * 100, 1),
                "fair_odds": fair,
                "odds": odds,
                "bookmaker": book,
                "ev_pct": ev,
            }
        )

    viable = [o for o in options if o.get("ev_pct") is not None and o["ev_pct"] >= min_edge_pct]
    if not viable:
        best_pick = max(
            (o for o in options if o.get("ev_pct") is not None),
            key=lambda o: o["ev_pct"],
            default=None,
        )
        recommendation = best_pick
        is_actionable = False
    else:
        recommendation = max(viable, key=lambda o: o["ev_pct"])
        is_actionable = True

    over25_prob = 1.0 - (
        _poisson_pmf(0, lam_h) * _poisson_pmf(0, lam_a)
        + _poisson_pmf(1, lam_h) * _poisson_pmf(0, lam_a)
        + _poisson_pmf(0, lam_h) * _poisson_pmf(1, lam_a)
        + _poisson_pmf(1, lam_h) * _poisson_pmf(1, lam_a)
    )

    return {
        "home_xg_team": home_stats.get("name"),
        "away_xg_team": away_stats.get("name"),
        "home_xg_for": home_stats.get("xg_for"),
        "away_xg_for": away_stats.get("xg_for"),
        "expected_home_goals": lam_h,
        "expected_away_goals": lam_a,
        "expected_total_goals": round(lam_h + lam_a, 2),
        "prob_home_pct": round(p1 * 100, 1),
        "prob_draw_pct": round(px * 100, 1),
        "prob_away_pct": round(p2 * 100, 1),
        "over25_prob_pct": round(over25_prob * 100, 1),
        "recommendation": recommendation,
        "options": options,
        "is_actionable": is_actionable,
        "min_edge_pct": min_edge_pct,
    }


def attach_xg_tips(
    matches: list[dict[str, Any]],
    xg_by_league: dict[str, dict[str, dict[str, Any]]],
    config: dict,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    min_edge = float(config.get("xg_min_edge_pct", 3.0))
    home_adv = float(config.get("xg_home_advantage", 1.08))

    all_tips: list[dict[str, Any]] = []
    for m in matches:
        league = m.get("league") or ""
        league_xg = xg_by_league.get(league) or {}
        if not league_xg:
            continue
        tip = build_xg_tip_for_match(
            m,
            league_xg,
            min_edge_pct=min_edge,
            home_advantage=home_adv,
        )
        if not tip:
            m["xg_tip"] = None
            continue
        m["xg_tip"] = tip
        rec = tip.get("recommendation")
        if rec and tip.get("is_actionable"):
            all_tips.append(
                {
                    "match_id": m.get("id"),
                    "league": league,
                    "commence_time": m.get("commence_time"),
                    "home_team": m.get("home_team"),
                    "away_team": m.get("away_team"),
                    "pick": rec.get("pick"),
                    "odds": rec.get("odds"),
                    "bookmaker": rec.get("bookmaker"),
                    "prob_pct": rec.get("prob_pct"),
                    "ev_pct": rec.get("ev_pct"),
                    "expected_score": f"{tip['expected_home_goals']:.2f} – {tip['expected_away_goals']:.2f}",
                    "over25_prob_pct": tip.get("over25_prob_pct"),
                }
            )

    all_tips.sort(key=lambda t: t.get("ev_pct") or 0, reverse=True)
    return matches, all_tips
