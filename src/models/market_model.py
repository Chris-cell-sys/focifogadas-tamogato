"""Market / odds modell – bookmaker implicit valószínűség."""

from __future__ import annotations

from typing import Any


def implied_probability(odds: float | None) -> float | None:
    if odds is None or odds <= 1.0:
        return None
    return 1.0 / odds


def annotate_market(
    option: dict[str, Any],
    book_odds: float | None,
) -> dict[str, Any]:
    row = dict(option)
    implied = implied_probability(book_odds)
    row["book_odds"] = book_odds
    row["implied_prob"] = implied
    row["implied_prob_pct"] = round(implied * 100, 1) if implied is not None else None
    row["market_fair_odds"] = round(1.0 / implied, 2) if implied and implied > 0.01 else None
    return row
