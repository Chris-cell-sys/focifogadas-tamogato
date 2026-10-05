"""TippmixPro tippek – többmodell ensemble + value + stake."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.fetch_tippmixpro import find_tippmix_event, format_kickoff_hu
from src.fetch_xg import UNDERSTAT_LEAGUES
from src.models.ensemble import build_tip_for_match

BUDAPEST = ZoneInfo("Europe/Budapest")


def parse_kickoff(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(BUDAPEST)
    except Exception:
        return None


def is_today_match(iso: str | None, *, now: datetime | None = None) -> bool:
    kick = parse_kickoff(iso)
    if not kick:
        return False
    now = now or datetime.now(BUDAPEST)
    day = now.date() if now.hour >= 3 else (now - timedelta(days=1)).date()
    return kick.date() == day


def espn_odds_as_tippmix(match: dict[str, Any]) -> dict[str, Any] | None:
    best = match.get("best_odds") or {}
    if not best:
        return None
    home = match.get("home_team") or ""
    away = match.get("away_team") or ""

    def _odds_for(name: str) -> float | None:
        row = best.get(name) or {}
        val = row.get("odds")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    odds_1 = _odds_for(home)
    odds_x = _odds_for("Draw")
    odds_2 = _odds_for(away)
    if odds_1 is None and odds_x is None and odds_2 is None:
        return None
    return {
        "home_team": home,
        "away_team": away,
        "odds_1": odds_1,
        "odds_x": odds_x,
        "odds_2": odds_2,
        "over_25": None,
        "under_25": None,
        "btts_yes": None,
        "btts_no": None,
        "source": "espn-fallback",
    }


def resolve_market_odds(
    match: dict[str, Any],
    tippmix_event: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    if tippmix_event and any(tippmix_event.get(k) for k in ("odds_1", "odds_x", "odds_2", "over_25", "btts_yes")):
        return tippmix_event, "TippmixPro"
    fallback = espn_odds_as_tippmix(match)
    if fallback:
        return fallback, "ESPN"
    return None, "none"


def build_xg_tip_for_match(
    match: dict[str, Any],
    league_xg: dict[str, dict[str, Any]],
    tippmix_event: dict[str, Any] | None = None,
    *,
    home_advantage: float = 1.08,
    min_team_games: int = 4,
    min_prob_pct: float = 45.0,
    odds_min: float = 1.8,
    odds_max: float = 2.1,
    value_threshold: float = 1.02,
    config: dict | None = None,
) -> dict[str, Any] | None:
    cfg = dict(config or {})
    cfg.setdefault("xg_home_advantage", home_advantage)
    cfg.setdefault("xg_min_team_games", min_team_games)
    cfg.setdefault("xg_min_prob_pct", min_prob_pct)
    cfg.setdefault("odds_min", odds_min)
    cfg.setdefault("odds_max", odds_max)
    cfg.setdefault("value_threshold", value_threshold)
    return build_tip_for_match(match, league_xg, tippmix_event, cfg)


def attach_xg_tips(
    matches: list[dict[str, Any]],
    xg_by_league: dict[str, dict[str, dict[str, Any]]],
    config: dict,
    tippmix_index: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    min_games = int(config.get("xg_min_team_games", 4))
    min_prob = float(config.get("xg_min_prob_pct", 45.0))
    top_n = int(config.get("top_tips", 5))
    today_only = bool(config.get("today_only", True))
    tippmix_index = tippmix_index or {}

    now = datetime.now(BUDAPEST)
    all_tips: list[dict[str, Any]] = []

    for m in matches:
        kick = parse_kickoff(m.get("commence_time"))
        m["kickoff_local"] = kick.strftime("%Y-%m-%d %H:%M") if kick else None
        m["kickoff_display"] = format_kickoff_hu(m.get("commence_time"))
        m["is_today"] = is_today_match(m.get("commence_time"), now=now)
        m["kick_date"] = kick.date().isoformat() if kick else None

    has_today = any(m.get("is_today") for m in matches)
    target_date = None
    if today_only and not has_today:
        future_dates = sorted(
            {
                m["kick_date"]
                for m in matches
                if m.get("kick_date")
                and parse_kickoff(m.get("commence_time"))
                and parse_kickoff(m.get("commence_time")) >= now
            }
        )
        target_date = future_dates[0] if future_dates else None

    for m in matches:
        league = m.get("league") or ""
        on_slate = True
        if today_only:
            if has_today:
                on_slate = bool(m.get("is_today"))
            else:
                on_slate = bool(target_date and m.get("kick_date") == target_date)
        if not on_slate:
            m["xg_tip"] = None
            m["on_slate"] = False
            continue
        m["on_slate"] = True

        league_xg = xg_by_league.get(league) or {}
        if not league_xg or league not in UNDERSTAT_LEAGUES:
            m["xg_tip"] = None
            continue

        tmp = find_tippmix_event(m.get("home_team") or "", m.get("away_team") or "", tippmix_index)
        if tmp and tmp.get("kickoff_local"):
            m["tippmix_kickoff_local"] = tmp["kickoff_local"]

        odds_event, odds_source = resolve_market_odds(m, tmp)
        tip = build_xg_tip_for_match(
            m,
            league_xg,
            tippmix_event=odds_event,
            min_team_games=min_games,
            min_prob_pct=min_prob,
            config=config,
        )
        m["xg_tip"] = tip
        if not tip:
            continue

        tip["odds_source"] = odds_source
        tip["tippmix_matched"] = bool(tmp)
        rec = tip.get("recommendation") or {}
        markets = tip.get("markets") or {}
        meta = tip.get("model_meta") or {}

        row = {
            "match_id": m.get("id"),
            "league": league,
            "sport_title": m.get("sport_title"),
            "commence_time": m.get("commence_time"),
            "kickoff_local": m.get("kickoff_local"),
            "kickoff_display": m.get("kickoff_display"),
            "is_today": m.get("is_today"),
            "home_team": m.get("home_team"),
            "away_team": m.get("away_team"),
            "bookmaker": odds_source if odds_source != "none" else "TippmixPro",
            "odds_source": odds_source,
            "pick": rec.get("pick"),
            "short": rec.get("short"),
            "market": rec.get("market"),
            "prob_pct": rec.get("prob_pct"),
            "fair_odds": rec.get("fair_odds"),
            "tippmix_odds": tip.get("tippmix_odds"),
            "tippmix_markets": tip.get("tippmix_markets"),
            "tippmix_matched": tip.get("tippmix_matched"),
            "edge_pct": tip.get("edge_pct"),
            "elite_score": tip.get("elite_score"),
            "confidence_tier": tip.get("confidence_tier"),
            "model_agreement": tip.get("model_agreement"),
            "models": tip.get("models"),
            "staking": tip.get("staking"),
            "suggested_stake": tip.get("suggested_stake"),
            "stake_pct": tip.get("stake_pct"),
            "bankroll": tip.get("bankroll"),
            "is_value": True,
            "odds_in_band": True,
            "expected_score": f"{tip['expected_home_goals']:.2f} – {tip['expected_away_goals']:.2f}",
            "home_form": tip.get("home_form"),
            "away_form": tip.get("away_form"),
            "home_op_xg": meta.get("home_op_xg"),
            "home_op_xga": meta.get("home_op_xga"),
            "away_op_xg": meta.get("away_op_xg"),
            "away_op_xga": meta.get("away_op_xga"),
            "home_attack_balance": tip.get("home_attack_balance"),
            "away_attack_balance": tip.get("away_attack_balance"),
            "winner_pick": (markets.get("1X2") or {}).get("short"),
            "winner_prob": (markets.get("1X2") or {}).get("prob_pct"),
            "btts_pick": (markets.get("BTTS") or {}).get("short"),
            "btts_prob": (markets.get("BTTS") or {}).get("prob_pct"),
            "goals_pick": (markets.get("Gólok") or {}).get("short"),
            "goals_prob": (markets.get("Gólok") or {}).get("prob_pct"),
            "is_actionable": tip.get("is_actionable"),
        }
        all_tips.append(row)

    all_tips.sort(
        key=lambda t: (t.get("elite_score") or 0, t.get("edge_pct") or 0, t.get("prob_pct") or 0),
        reverse=True,
    )
    top_tips = all_tips[:top_n]
    top_ids = {t["match_id"] for t in top_tips}
    for t in all_tips:
        t["is_top"] = t["match_id"] in top_ids
    for m in matches:
        mid = m.get("id")
        if m.get("xg_tip"):
            m["xg_tip"]["is_top"] = mid in top_ids

    return matches, all_tips, top_tips
