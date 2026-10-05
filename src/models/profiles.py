"""Csapat profil – forma, gól, open-play xG."""

from __future__ import annotations

from typing import Any


def _num(stats: dict[str, Any] | None, *keys: str, default: float = 1.2) -> float:
    if not stats:
        return default
    for key in keys:
        val = stats.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return default


def _blend(a: float, b: float, weight_a: float = 0.55) -> float:
    return weight_a * a + (1.0 - weight_a) * b


def team_profile(stats: dict[str, Any], venue: str) -> dict[str, Any]:
    split = stats.get("last5_home") if venue == "home" else stats.get("last5_away")
    fallback = stats.get("home_split") if venue == "home" else stats.get("away_split")
    last5 = stats.get("last5") or {}
    split = split or {}
    fallback = fallback or {}

    op_xg = _num(split, "op_xg_for", default=_num(fallback, "op_xg_for", default=_num(stats, "op_xg_for", "xg_for")))
    op_xga = _num(split, "op_xga", default=_num(fallback, "op_xga", default=_num(stats, "op_xga", "xg_against")))
    goals_for = _num(split, "goals_for", default=_num(fallback, "goals_for", default=_num(stats, "goals_for")))
    goals_against = _num(
        split, "goals_against", default=_num(fallback, "goals_against", default=_num(stats, "goals_against"))
    )
    total_xg = _num(split, "xg_for", default=_num(fallback, "xg_for", default=_num(stats, "xg_for")))
    total_xga = _num(split, "xg_against", default=_num(fallback, "xg_against", default=_num(stats, "xg_against")))
    balance = _num(
        split,
        "attack_balance",
        default=_num(last5, "attack_balance", default=_num(stats, "attack_balance", default=0.5)),
    )
    form_ppg = _num(last5, "form_ppg", default=_num(stats, "form_ppg", default=1.0))
    form_string = last5.get("form_string") or stats.get("form_string") or ""

    attack = _blend(op_xg, goals_for, 0.60)
    defence = _blend(op_xga, goals_against, 0.60)

    return {
        "venue": venue,
        "op_xg_for": round(op_xg, 3),
        "op_xga": round(op_xga, 3),
        "total_xg": round(total_xg, 3),
        "total_xga": round(total_xga, 3),
        "goals_for": round(goals_for, 3),
        "goals_against": round(goals_against, 3),
        "attack_balance": round(balance, 3),
        "form_ppg": round(form_ppg, 3),
        "form_string": form_string,
        "attack_strength": round(attack, 3),
        "defence_weakness": round(defence, 3),
        "season_xg_for": round(_num(stats, "xg_for"), 3),
        "season_xg_against": round(_num(stats, "xg_against"), 3),
        "season_home_xg": round(_num(stats, "home_xg_for", "xg_for"), 3),
        "season_away_xg": round(_num(stats, "away_xg_for", "xg_for"), 3),
    }
