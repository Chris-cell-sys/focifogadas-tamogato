"""Ensemble – stat + xG + form → value + elite + stake."""

from __future__ import annotations

from typing import Any

from src.fetch_tippmixpro import odds_for_pick
from src.fetch_xg import resolve_team
from src.models import form_model, stat_model, xg_model
from src.models.confidence_model import elite_score
from src.models.market_model import annotate_market
from src.models.poisson import build_market_options, market_probabilities
from src.models.profiles import team_profile
from src.models.value_model import evaluate_value
from src.staking import suggested_stake

MARKET_SHORTS = ("1", "X", "2", "BTTS Igen", "BTTS Nem", "O2.5", "U2.5")


def _weights(config: dict) -> dict[str, float]:
    raw = config.get("model_weights") or {}
    w_stat = float(raw.get("stat", 0.30))
    w_xg = float(raw.get("xg", 0.40))
    w_form = float(raw.get("form", 0.30))
    total = w_stat + w_xg + w_form or 1.0
    return {"stat": w_stat / total, "xg": w_xg / total, "form": w_form / total}


def ensemble_probabilities(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    config: dict,
) -> tuple[dict[str, float], dict[str, Any]]:
    home_adv = float(config.get("xg_home_advantage", 1.08))
    w = _weights(config)

    lam_s_h, lam_s_a, meta_stat = stat_model.expected_lambdas(home_stats, away_stats, home_advantage=home_adv)
    lam_x_h, lam_x_a, meta_xg = xg_model.expected_lambdas(home_stats, away_stats, home_advantage=home_adv)
    lam_f_h, lam_f_a, meta_form = form_model.expected_lambdas(home_stats, away_stats, home_advantage=home_adv)

    p_stat = market_probabilities(lam_s_h, lam_s_a)
    p_xg = market_probabilities(lam_x_h, lam_x_a)
    p_form = market_probabilities(lam_f_h, lam_f_a)

    ensemble: dict[str, float] = {}
    by_short: dict[str, dict[str, float]] = {}
    for short in MARKET_SHORTS:
        ps = p_stat.get(short, 0.0)
        px = p_xg.get(short, 0.0)
        pf = p_form.get(short, 0.0)
        pe = w["stat"] * ps + w["xg"] * px + w["form"] * pf
        ensemble[short] = pe
        by_short[short] = {"stat": ps, "xg": px, "form": pf, "ensemble": pe}

    home = team_profile(home_stats, "home")
    away = team_profile(away_stats, "away")
    meta = {
        "stat": meta_stat,
        "xg": meta_xg,
        "form": meta_form,
        "lambdas": {
            "stat": [lam_s_h, lam_s_a],
            "xg": [lam_x_h, lam_x_a],
            "form": [lam_f_h, lam_f_a],
        },
        "weights": w,
        "home_form": meta_form.get("home_form"),
        "away_form": meta_form.get("away_form"),
        "home_op_xg": meta_xg.get("home_op_xg"),
        "home_op_xga": meta_xg.get("home_op_xga"),
        "away_op_xg": meta_xg.get("away_op_xg"),
        "away_op_xga": meta_xg.get("away_op_xga"),
        "home_attack_balance": meta_xg.get("home_balance"),
        "away_attack_balance": meta_xg.get("away_balance"),
        "home_profile": home,
        "away_profile": away,
        "by_short": by_short,
    }
    # fő lambda = súlyozott átlag (megjelenítéshez)
    meta["expected_home_goals"] = round(w["stat"] * lam_s_h + w["xg"] * lam_x_h + w["form"] * lam_f_h, 3)
    meta["expected_away_goals"] = round(w["stat"] * lam_s_a + w["xg"] * lam_x_a + w["form"] * lam_f_a, 3)
    return ensemble, meta


def build_options_for_match(
    home_name: str,
    away_name: str,
    ensemble_probs: dict[str, float],
    meta: dict[str, Any],
    book_event: dict[str, Any] | None,
    config: dict,
) -> list[dict[str, Any]]:
    odds_min = float(config.get("odds_min", 1.8))
    odds_max = float(config.get("odds_max", 2.1))
    value_threshold = float(config.get("value_threshold", 1.02))
    bankroll = float(config.get("bankroll", 100_000))

    options = build_market_options(home_name, away_name, ensemble_probs, prob_key="prob")
    out: list[dict[str, Any]] = []
    by_short = meta.get("by_short") or {}

    for o in options:
        short = o["short"]
        comp = by_short.get(short) or {}
        prob = float(o["prob"])
        book_odds = odds_for_pick(book_event, short)
        row = annotate_market(o, book_odds)
        val = evaluate_value(
            prob,
            book_odds,
            value_threshold=value_threshold,
            odds_min=odds_min,
            odds_max=odds_max,
        )
        conf = elite_score(
            ensemble_prob=prob,
            stat_prob=float(comp.get("stat") or 0),
            xg_prob=float(comp.get("xg") or 0),
            form_prob=float(comp.get("form") or 0),
            edge=val.get("edge"),
            odds_ok=val.get("odds_ok", False),
        )
        stake = {}
        if book_odds and val.get("odds_ok"):
            stake = suggested_stake(bankroll, prob, book_odds, config)

        row.update(
            {
                **val,
                **conf,
                "tippmix_odds": book_odds,
                "prob_pct": round(prob * 100, 1),
                "models": {
                    "stat_prob_pct": round(float(comp.get("stat") or 0) * 100, 1),
                    "xg_prob_pct": round(float(comp.get("xg") or 0) * 100, 1),
                    "form_prob_pct": round(float(comp.get("form") or 0) * 100, 1),
                    "ensemble_prob_pct": round(prob * 100, 1),
                },
                "staking": stake,
                "suggested_stake": stake.get("suggested_stake"),
                "stake_pct": stake.get("stake_pct"),
            }
        )
        out.append(row)
    return out


def pick_best_option(options: list[dict[str, Any]], min_prob_pct: float) -> dict[str, Any] | None:
    eligible = [o for o in options if o.get("odds_ok") and (o.get("prob_pct") or 0) >= min_prob_pct]
    if not eligible:
        eligible = [o for o in options if o.get("odds_ok")]
    if not eligible:
        return None
    eligible.sort(
        key=lambda o: (o.get("elite_score") or 0, o.get("edge_pct") or -999, o.get("prob") or 0),
        reverse=True,
    )
    best = dict(eligible[0])
    best["is_strong"] = True
    return best


def build_tip_for_match(
    match: dict[str, Any],
    league_xg: dict[str, dict[str, Any]],
    book_event: dict[str, Any] | None,
    config: dict,
) -> dict[str, Any] | None:
    min_games = int(config.get("xg_min_team_games", 4))
    min_prob = float(config.get("xg_min_prob_pct", 45.0))
    odds_min = float(config.get("odds_min", 1.8))
    odds_max = float(config.get("odds_max", 2.1))

    home_name = match.get("home_team") or ""
    away_name = match.get("away_team") or ""
    home_stats = resolve_team(home_name, league_xg)
    away_stats = resolve_team(away_name, league_xg)
    if not home_stats or not away_stats:
        return None
    if (home_stats.get("games") or 0) < min_games or (away_stats.get("games") or 0) < min_games:
        return None

    ensemble_probs, meta = ensemble_probabilities(home_stats, away_stats, config)
    options = build_options_for_match(home_name, away_name, ensemble_probs, meta, book_event, config)
    best = pick_best_option(options, min_prob_pct=min_prob)
    if not best:
        return None

    by_market: dict[str, dict[str, Any]] = {}
    for o in options:
        mkt = o["market"]
        score = (1 if o.get("odds_ok") else 0, o.get("elite_score") or 0, o.get("edge_pct") or -999)
        prev = by_market.get(mkt)
        prev_score = (
            (1 if prev.get("odds_ok") else 0, prev.get("elite_score") or 0, prev.get("edge_pct") or -999)
            if prev
            else None
        )
        if prev is None or score > prev_score:
            by_market[mkt] = o

    tippmix_markets = None
    if book_event:
        tippmix_markets = {
            "1": book_event.get("odds_1"),
            "X": book_event.get("odds_x"),
            "2": book_event.get("odds_2"),
            "O2.5": book_event.get("over_25"),
            "U2.5": book_event.get("under_25"),
            "BTTS Igen": book_event.get("btts_yes"),
            "BTTS Nem": book_event.get("btts_no"),
        }

    lam_h = meta["expected_home_goals"]
    lam_a = meta["expected_away_goals"]

    return {
        "bookmaker": "TippmixPro",
        "home_xg_team": home_stats.get("name"),
        "away_xg_team": away_stats.get("name"),
        "expected_home_goals": lam_h,
        "expected_away_goals": lam_a,
        "expected_total_goals": round(lam_h + lam_a, 2),
        "model_meta": meta,
        "model_stack": ["stat", "xg", "form", "market", "value", "confidence"],
        "home_form": meta.get("home_form"),
        "away_form": meta.get("away_form"),
        "home_attack_balance": meta.get("home_attack_balance"),
        "away_attack_balance": meta.get("away_attack_balance"),
        "markets": {
            "1X2": by_market.get("1X2"),
            "BTTS": by_market.get("BTTS"),
            "Gólok": by_market.get("Gólok"),
        },
        "recommendation": best,
        "options": options,
        "tippmix_odds": best.get("tippmix_odds"),
        "tippmix_markets": tippmix_markets,
        "tippmix_matched": bool(book_event),
        "prob_pct": best.get("prob_pct"),
        "fair_odds": best.get("fair_odds"),
        "edge_pct": best.get("edge_pct"),
        "elite_score": best.get("elite_score"),
        "confidence_tier": best.get("confidence_tier"),
        "model_agreement": best.get("model_agreement"),
        "models": best.get("models"),
        "staking": best.get("staking"),
        "suggested_stake": best.get("suggested_stake"),
        "stake_pct": best.get("stake_pct"),
        "is_value": True,
        "odds_in_band": True,
        "is_actionable": True,
        "min_prob_pct": min_prob,
        "odds_band": [odds_min, odds_max],
        "bankroll": float(config.get("bankroll", 100_000)),
    }
