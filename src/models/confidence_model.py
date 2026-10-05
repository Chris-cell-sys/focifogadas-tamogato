"""Confidence / Elite modell – komponensek egyetlen erősségbe."""

from __future__ import annotations

import statistics
from typing import Any


def model_agreement(probs: list[float]) -> float:
    """0–1: alacsony szórás = magas egyetértés."""
    if len(probs) < 2:
        return 0.5
    if max(probs) - min(probs) < 0.02:
        return 1.0
    try:
        stdev = statistics.pstdev(probs)
    except statistics.StatisticsError:
        return 0.5
    return max(0.0, min(1.0, 1.0 - stdev * 4.0))


def elite_score(
    *,
    ensemble_prob: float,
    stat_prob: float,
    xg_prob: float,
    form_prob: float,
    edge: float | None,
    odds_ok: bool,
) -> dict[str, Any]:
    agree = model_agreement([stat_prob, xg_prob, form_prob])
    edge_norm = max(0.0, min(1.0, (edge or 0) * 5.0))  # ~20% edge → 1.0
    prob_strength = max(0.0, min(1.0, (ensemble_prob - 0.45) / 0.35))  # 45–80% skála

    raw = 0.35 * agree + 0.30 * edge_norm + 0.25 * prob_strength + (0.10 if odds_ok else 0.0)
    score = round(raw * 100, 1)

    if score >= 75:
        tier = "elite"
    elif score >= 60:
        tier = "strong"
    elif score >= 45:
        tier = "moderate"
    else:
        tier = "weak"

    return {
        "elite_score": score,
        "confidence_tier": tier,
        "model_agreement": round(agree * 100, 1),
    }
