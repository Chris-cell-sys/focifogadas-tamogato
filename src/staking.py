"""Stake – profi negyed-Kelly (fractional Kelly) bankroll alapján."""

from __future__ import annotations

from typing import Any


def kelly_fraction(prob: float, decimal_odds: float) -> float:
    """Teljes Kelly arány (0 ha nincs +EV)."""
    if decimal_odds <= 1.0 or prob <= 0:
        return 0.0
    b = decimal_odds - 1.0
    q = 1.0 - prob
    f = (b * prob - q) / b
    return max(0.0, f)


def suggested_stake(
    bankroll: float,
    prob: float,
    decimal_odds: float,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Negyed-Kelly (alapértelmezett): a profik gyakran 1/4–1/2 Kelly-t használnak,
    max. tét %-kal capelve.
    """
    cfg = config or {}
    kelly_frac = float(cfg.get("kelly_fraction", 0.25))
    max_pct = float(cfg.get("max_stake_pct", 0.03))
    min_stake = float(cfg.get("min_stake", 500))
    currency = str(cfg.get("currency", "HUF"))

    full_kelly = kelly_fraction(prob, decimal_odds)
    stake_pct = min(max_pct, full_kelly * kelly_frac)
    amount = round(bankroll * stake_pct, 0)
    if amount > 0 and amount < min_stake:
        amount = min_stake if stake_pct > 0 else 0.0

    return {
        "bankroll": bankroll,
        "currency": currency,
        "kelly_full_pct": round(full_kelly * 100, 2),
        "stake_pct": round(stake_pct * 100, 2),
        "suggested_stake": amount,
        "staking_method": f"fractional_kelly_{kelly_frac}",
    }
