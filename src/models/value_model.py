"""Value modell – ensemble vs bookmaker."""

from __future__ import annotations

from typing import Any


def evaluate_value(
    ensemble_prob: float,
    book_odds: float | None,
    *,
    value_threshold: float = 1.02,
    odds_min: float = 1.8,
    odds_max: float = 2.1,
) -> dict[str, Any]:
    implied = (1.0 / book_odds) if book_odds and book_odds > 1.0 else None
    edge = (ensemble_prob - implied) if implied is not None else None
    fair = round(1.0 / ensemble_prob, 2) if ensemble_prob > 0.01 else None
    in_band = book_odds is not None and odds_min <= book_odds <= odds_max
    is_value = False
    if book_odds and fair and edge is not None:
        is_value = book_odds >= fair * value_threshold and edge > 0
    return {
        "fair_odds": fair,
        "edge": edge,
        "edge_pct": round(edge * 100, 1) if edge is not None else None,
        "odds_in_band": in_band,
        "is_value": is_value,
        "odds_ok": bool(in_band and is_value),
        "implied_prob_pct": round(implied * 100, 1) if implied is not None else None,
    }
