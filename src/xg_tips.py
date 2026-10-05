"""xG alapú TippmixPro-piac tippek: 1X2, BTTS, Over/Under 2.5."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.fetch_xg import resolve_team

BUDAPEST = ZoneInfo("Europe/Budapest")


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
    """BTTS igen = mindkét csapat legalább 1 gólt szerez."""
    p_home_score = 1.0 - _poisson_pmf(0, home_lambda)
    p_away_score = 1.0 - _poisson_pmf(0, away_lambda)
    # független közelítés (Poisson)
    yes = p_home_score * p_away_score
    return yes, 1.0 - yes


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
    """Mai nap (BUÉK), hajnali 03:00-ig még az előző esti meccsek is 'mai'."""
    kick = parse_kickoff(iso)
    if not kick:
        return False
    now = now or datetime.now(BUDAPEST)
    day = now.date() if now.hour >= 3 else (now - timedelta(days=1)).date()
    return kick.date() == day


def is_near_term(iso: str | None, *, now: datetime | None = None, hours: int = 36) -> bool:
    """Következő N órában kezdődő meccs (ha ma üres a nap)."""
    kick = parse_kickoff(iso)
    if not kick:
        return False
    now = now or datetime.now(BUDAPEST)
    return now <= kick <= now + timedelta(hours=hours)


def build_market_options(
    home_name: str,
    away_name: str,
    lam_h: float,
    lam_a: float,
) -> list[dict[str, Any]]:
    p1, px, p2 = match_outcome_probs(lam_h, lam_a)
    over, under = over_under_25_probs(lam_h, lam_a)
    btts_yes, btts_no = btts_probs(lam_h, lam_a)

    options = [
        {
            "market": "1X2",
            "pick": f"Hazai győzelem ({home_name})",
            "short": "1",
            "prob": p1,
        },
        {
            "market": "1X2",
            "pick": "Döntetlen",
            "short": "X",
            "prob": px,
        },
        {
            "market": "1X2",
            "pick": f"Vendég győzelem ({away_name})",
            "short": "2",
            "prob": p2,
        },
        {
            "market": "BTTS",
            "pick": "Mindkét csapat szerez gólt (Igen)",
            "short": "BTTS Igen",
            "prob": btts_yes,
        },
        {
            "market": "BTTS",
            "pick": "Mindkét csapat szerez gólt (Nem)",
            "short": "BTTS Nem",
            "prob": btts_no,
        },
        {
            "market": "Gólok",
            "pick": "Over 2.5 gól",
            "short": "O2.5",
            "prob": over,
        },
        {
            "market": "Gólok",
            "pick": "Under 2.5 gól",
            "short": "U2.5",
            "prob": under,
        },
    ]

    for o in options:
        prob = float(o["prob"])
        o["prob_pct"] = round(prob * 100, 1)
        o["fair_odds"] = round(1.0 / prob, 2) if prob > 0.01 else None
        o["confidence"] = round(prob * 100, 1)
    return options


def pick_best_option(options: list[dict[str, Any]], min_prob_pct: float) -> dict[str, Any] | None:
    ranked = sorted(options, key=lambda o: o.get("prob") or 0, reverse=True)
    if not ranked:
        return None
    best = ranked[0]
    best = {
        **best,
        "is_strong": (best.get("prob_pct") or 0) >= min_prob_pct,
    }
    return best


def build_xg_tip_for_match(
    match: dict[str, Any],
    league_xg: dict[str, dict[str, Any]],
    *,
    home_advantage: float = 1.08,
    min_team_games: int = 4,
    min_prob_pct: float = 52.0,
) -> dict[str, Any] | None:
    home_name = match.get("home_team") or ""
    away_name = match.get("away_team") or ""
    home_stats = resolve_team(home_name, league_xg)
    away_stats = resolve_team(away_name, league_xg)
    if not home_stats or not away_stats:
        return None
    if (home_stats.get("games") or 0) < min_team_games or (away_stats.get("games") or 0) < min_team_games:
        return None

    lam_h, lam_a = expected_lambdas(home_stats, away_stats, home_advantage=home_advantage)
    options = build_market_options(home_name, away_name, lam_h, lam_a)
    best = pick_best_option(options, min_prob_pct)
    if not best:
        return None

    # piaconkénti győztes (1X2 / BTTS / O-U)
    by_market: dict[str, dict[str, Any]] = {}
    for o in options:
        mkt = o["market"]
        if mkt not in by_market or (o.get("prob") or 0) > (by_market[mkt].get("prob") or 0):
            by_market[mkt] = o

    over = next(o for o in options if o["short"] == "O2.5")
    under = next(o for o in options if o["short"] == "U2.5")
    btts_yes = next(o for o in options if o["short"] == "BTTS Igen")
    p1 = next(o for o in options if o["short"] == "1")
    px = next(o for o in options if o["short"] == "X")
    p2 = next(o for o in options if o["short"] == "2")

    return {
        "bookmaker": "TippmixPro",
        "home_xg_team": home_stats.get("name"),
        "away_xg_team": away_stats.get("name"),
        "home_xg_for": home_stats.get("xg_for"),
        "away_xg_for": away_stats.get("xg_for"),
        "expected_home_goals": lam_h,
        "expected_away_goals": lam_a,
        "expected_total_goals": round(lam_h + lam_a, 2),
        "prob_home_pct": p1["prob_pct"],
        "prob_draw_pct": px["prob_pct"],
        "prob_away_pct": p2["prob_pct"],
        "over25_prob_pct": over["prob_pct"],
        "under25_prob_pct": under["prob_pct"],
        "btts_yes_prob_pct": btts_yes["prob_pct"],
        "markets": {
            "1X2": by_market.get("1X2"),
            "BTTS": by_market.get("BTTS"),
            "Gólok": by_market.get("Gólok"),
        },
        "recommendation": best,
        "options": options,
        "is_actionable": bool(best.get("is_strong")),
        "min_prob_pct": min_prob_pct,
    }


def attach_xg_tips(
    matches: list[dict[str, Any]],
    xg_by_league: dict[str, dict[str, dict[str, Any]]],
    config: dict,
    tippmix_index: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from src.fetch_tippmixpro import find_tippmix_event, format_kickoff_hu, odds_for_pick

    home_adv = float(config.get("xg_home_advantage", 1.08))
    min_games = int(config.get("xg_min_team_games", 4))
    min_prob = float(config.get("xg_min_prob_pct", 52.0))
    top_n = int(config.get("top_tips", 5))
    today_only = bool(config.get("today_only", True))
    tippmix_index = tippmix_index or {}

    now = datetime.now(BUDAPEST)
    all_tips: list[dict[str, Any]] = []

    for m in matches:
        league = m.get("league") or ""
        kick = parse_kickoff(m.get("commence_time"))
        m["kickoff_local"] = kick.strftime("%Y-%m-%d %H:%M") if kick else None
        m["kickoff_display"] = format_kickoff_hu(m.get("commence_time"))
        m["is_today"] = is_today_match(m.get("commence_time"), now=now)
        m["kick_date"] = kick.date().isoformat() if kick else None

    # ha ma nincs meccs: a legközelebbi fordulónap meccsei
    has_today = any(m.get("is_today") for m in matches)
    target_date = None
    if today_only and not has_today:
        future_dates = sorted(
            {
                m["kick_date"]
                for m in matches
                if m.get("kick_date") and parse_kickoff(m.get("commence_time")) and parse_kickoff(m.get("commence_time")) >= now
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
        if not league_xg:
            merged: dict[str, dict[str, Any]] = {}
            for lg in xg_by_league.values():
                merged.update(lg)
            league_xg = merged

        tip = build_xg_tip_for_match(
            m,
            league_xg,
            home_advantage=home_adv,
            min_team_games=min_games,
            min_prob_pct=min_prob,
        )
        m["xg_tip"] = tip
        if not tip:
            continue

        rec = tip.get("recommendation") or {}
        markets = tip.get("markets") or {}
        tmp = find_tippmix_event(m.get("home_team") or "", m.get("away_team") or "", tippmix_index)
        tippmix_odds = odds_for_pick(tmp, rec.get("short"))
        tippmix_markets = None
        if tmp:
            tippmix_markets = {
                "1": tmp.get("odds_1"),
                "X": tmp.get("odds_x"),
                "2": tmp.get("odds_2"),
                "O2.5": tmp.get("over_25"),
                "U2.5": tmp.get("under_25"),
                "BTTS Igen": tmp.get("btts_yes"),
                "BTTS Nem": tmp.get("btts_no"),
            }
            # ha TippmixPro ad pontosabb időt, tartsuk meg a megjelenítéshez
            if tmp.get("kickoff_local"):
                m["tippmix_kickoff_local"] = tmp["kickoff_local"]

        tip["tippmix_odds"] = tippmix_odds
        tip["tippmix_markets"] = tippmix_markets
        tip["tippmix_matched"] = bool(tmp)

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
            "bookmaker": "TippmixPro",
            "pick": rec.get("pick"),
            "short": rec.get("short"),
            "market": rec.get("market"),
            "prob_pct": rec.get("prob_pct"),
            "fair_odds": rec.get("fair_odds"),
            "tippmix_odds": tippmix_odds,
            "tippmix_markets": tippmix_markets,
            "tippmix_matched": bool(tmp),
            "expected_score": f"{tip['expected_home_goals']:.2f} – {tip['expected_away_goals']:.2f}",
            "winner_pick": (markets.get("1X2") or {}).get("short"),
            "winner_prob": (markets.get("1X2") or {}).get("prob_pct"),
            "btts_pick": (markets.get("BTTS") or {}).get("short"),
            "btts_prob": (markets.get("BTTS") or {}).get("prob_pct"),
            "goals_pick": (markets.get("Gólok") or {}).get("short"),
            "goals_prob": (markets.get("Gólok") or {}).get("prob_pct"),
            "is_actionable": tip.get("is_actionable"),
        }
        all_tips.append(row)

    all_tips.sort(key=lambda t: t.get("prob_pct") or 0, reverse=True)
    top_tips = all_tips[:top_n]
    top_ids = {t["match_id"] for t in top_tips}
    for t in all_tips:
        t["is_top"] = t["match_id"] in top_ids
    for m in matches:
        mid = m.get("id")
        if m.get("xg_tip"):
            m["xg_tip"]["is_top"] = mid in top_ids

    return matches, all_tips, top_tips
