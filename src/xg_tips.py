"""xG alapú TippmixPro tippek: forma, open-play xG, value + odds sáv."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.fetch_tippmixpro import find_tippmix_event, format_kickoff_hu, odds_for_pick
from src.fetch_xg import UNDERSTAT_LEAGUES, resolve_team

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
    p_home_score = 1.0 - _poisson_pmf(0, home_lambda)
    p_away_score = 1.0 - _poisson_pmf(0, away_lambda)
    yes = p_home_score * p_away_score
    return yes, 1.0 - yes


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


def _form_factor(ppg: float | None) -> float:
    """Forma szorzó ~0.90–1.10 (3 pont/meccs = erős)."""
    if ppg is None:
        return 1.0
    return max(0.90, min(1.10, 0.92 + 0.06 * (float(ppg) / 1.5)))


def _attack_tilt(balance: float | None) -> float:
    """Támadási egyensúly: 0.5 neutrális, >0.5 támadóbb."""
    if balance is None:
        return 1.0
    return max(0.92, min(1.08, 0.85 + 0.3 * float(balance)))


def team_profile(stats: dict[str, Any], venue: str) -> dict[str, Any]:
    """Hazai / vendég profil: utolsó 5 + helyszín szerinti open-play xG, gól, egyensúly."""
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
    balance = _num(split, "attack_balance", default=_num(last5, "attack_balance", default=_num(stats, "attack_balance", default=0.5)))
    form_ppg = _num(last5, "form_ppg", default=_num(stats, "form_ppg", default=1.0))
    form_string = (last5.get("form_string") or stats.get("form_string") or "")

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
    }


def expected_lambdas(
    home_stats: dict[str, Any],
    away_stats: dict[str, Any],
    *,
    home_advantage: float = 1.08,
) -> tuple[float, float, dict[str, Any]]:
    """
    Lambda a következőkből:
    - utolsó 5 meccs forma
    - hazai / vendég góltermelés
    - open-play xG / xGA (npxG)
    - összesített xG
    - támadási egyensúly
    """
    home = team_profile(home_stats, "home")
    away = team_profile(away_stats, "away")

    # támadás vs ellenfél védelem, open-play hangsúllyal + összes xG finomhangolás
    raw_home = _blend(
        (home["attack_strength"] + away["defence_weakness"]) / 2.0,
        (home["total_xg"] + away["total_xga"]) / 2.0,
        0.70,
    )
    raw_away = _blend(
        (away["attack_strength"] + home["defence_weakness"]) / 2.0,
        (away["total_xg"] + home["total_xga"]) / 2.0,
        0.70,
    )

    lam_home = raw_home * home_advantage * _form_factor(home["form_ppg"]) * _attack_tilt(home["attack_balance"])
    lam_away = raw_away * _form_factor(away["form_ppg"]) * _attack_tilt(away["attack_balance"])
    # enyhe kiegyenlítés, ha mindkét oldal nagyon támadó
    if home["attack_balance"] > 0.55 and away["attack_balance"] > 0.55:
        lam_home *= 1.03
        lam_away *= 1.03

    lam_home = max(0.15, round(lam_home, 3))
    lam_away = max(0.15, round(lam_away, 3))
    meta = {
        "home_profile": home,
        "away_profile": away,
        "home_form": home["form_string"],
        "away_form": away["form_string"],
        "home_attack_balance": home["attack_balance"],
        "away_attack_balance": away["attack_balance"],
        "home_op_xg": home["op_xg_for"],
        "home_op_xga": home["op_xga"],
        "away_op_xg": away["op_xg_for"],
        "away_op_xga": away["op_xga"],
        "home_goals_for": home["goals_for"],
        "away_goals_for": away["goals_for"],
    }
    return lam_home, lam_away, meta


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


def is_near_term(iso: str | None, *, now: datetime | None = None, hours: int = 36) -> bool:
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
        {"market": "1X2", "pick": f"Hazai győzelem ({home_name})", "short": "1", "prob": p1},
        {"market": "1X2", "pick": "Döntetlen", "short": "X", "prob": px},
        {"market": "1X2", "pick": f"Vendég győzelem ({away_name})", "short": "2", "prob": p2},
        {"market": "BTTS", "pick": "Mindkét csapat szerez gólt (Igen)", "short": "BTTS Igen", "prob": btts_yes},
        {"market": "BTTS", "pick": "Mindkét csapat szerez gólt (Nem)", "short": "BTTS Nem", "prob": btts_no},
        {"market": "Gólok", "pick": "Over 2.5 gól", "short": "O2.5", "prob": over},
        {"market": "Gólok", "pick": "Under 2.5 gól", "short": "U2.5", "prob": under},
    ]

    for o in options:
        prob = float(o["prob"])
        o["prob_pct"] = round(prob * 100, 1)
        o["fair_odds"] = round(1.0 / prob, 2) if prob > 0.01 else None
        o["confidence"] = round(prob * 100, 1)
    return options


def espn_odds_as_tippmix(match: dict[str, Any]) -> dict[str, Any] | None:
    """ESPN/DraftKings 1X2 odds Tippmix-szerű mezőkké (BTTS/OU nélkül)."""
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
    """Tippmix elsődleges; ha nincs egyezés, ESPN 1X2 fallback."""
    if tippmix_event and any(tippmix_event.get(k) for k in ("odds_1", "odds_x", "odds_2", "over_25", "btts_yes")):
        return tippmix_event, "TippmixPro"
    fallback = espn_odds_as_tippmix(match)
    if fallback:
        return fallback, "ESPN"
    return None, "none"


def annotate_value(
    options: list[dict[str, Any]],
    tippmix_event: dict[str, Any] | None,
    *,
    odds_min: float,
    odds_max: float,
    value_threshold: float,
) -> list[dict[str, Any]]:
    """Odds sáv + value (piaci szorzó vs modell fair)."""
    annotated: list[dict[str, Any]] = []
    for o in options:
        row = dict(o)
        odds = odds_for_pick(tippmix_event, o.get("short"))
        fair = o.get("fair_odds")
        prob = float(o.get("prob") or 0)
        implied = (1.0 / odds) if odds and odds > 1.0 else None
        edge = (prob - implied) if implied is not None else None
        in_band = odds is not None and odds_min <= odds <= odds_max
        is_value = False
        if odds is not None and fair:
            is_value = odds >= fair * value_threshold and (edge or 0) > 0
        row.update(
            {
                "tippmix_odds": odds,
                "implied_prob_pct": round(implied * 100, 1) if implied is not None else None,
                "edge_pct": round(edge * 100, 1) if edge is not None else None,
                "odds_in_band": in_band,
                "is_value": is_value,
                "odds_ok": bool(in_band and is_value),
            }
        )
        annotated.append(row)
    return annotated


def pick_best_value_option(
    options: list[dict[str, Any]],
    *,
    min_prob_pct: float,
) -> dict[str, Any] | None:
    """Csak odds-sávos + value tippek; élre (edge) rendezve."""
    eligible = [
        o
        for o in options
        if o.get("odds_ok") and (o.get("prob_pct") or 0) >= min_prob_pct
    ]
    if not eligible:
        # ha a min_prob túl szigorú, még mindig engedjük a value+sáv tippeket
        eligible = [o for o in options if o.get("odds_ok")]
    if not eligible:
        return None
    eligible.sort(key=lambda o: (o.get("edge_pct") or -999, o.get("prob") or 0), reverse=True)
    best = dict(eligible[0])
    best["is_strong"] = True
    return best


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
) -> dict[str, Any] | None:
    home_name = match.get("home_team") or ""
    away_name = match.get("away_team") or ""
    home_stats = resolve_team(home_name, league_xg)
    away_stats = resolve_team(away_name, league_xg)
    if not home_stats or not away_stats:
        return None
    if (home_stats.get("games") or 0) < min_team_games or (away_stats.get("games") or 0) < min_team_games:
        return None

    lam_h, lam_a, meta = expected_lambdas(home_stats, away_stats, home_advantage=home_advantage)
    options = build_market_options(home_name, away_name, lam_h, lam_a)
    options = annotate_value(
        options,
        tippmix_event,
        odds_min=odds_min,
        odds_max=odds_max,
        value_threshold=value_threshold,
    )
    best = pick_best_value_option(options, min_prob_pct=min_prob_pct)
    if not best:
        return None

    by_market: dict[str, dict[str, Any]] = {}
    for o in options:
        mkt = o["market"]
        # piaconként a legjobb value, különben legmagasabb prob
        score = (1 if o.get("odds_ok") else 0, o.get("edge_pct") or -999, o.get("prob") or 0)
        prev = by_market.get(mkt)
        prev_score = (
            (1 if prev.get("odds_ok") else 0, prev.get("edge_pct") or -999, prev.get("prob") or 0) if prev else None
        )
        if prev is None or score > prev_score:
            by_market[mkt] = o

    over = next(o for o in options if o["short"] == "O2.5")
    under = next(o for o in options if o["short"] == "U2.5")
    btts_yes = next(o for o in options if o["short"] == "BTTS Igen")
    p1 = next(o for o in options if o["short"] == "1")
    px = next(o for o in options if o["short"] == "X")
    p2 = next(o for o in options if o["short"] == "2")

    tippmix_markets = None
    if tippmix_event:
        tippmix_markets = {
            "1": tippmix_event.get("odds_1"),
            "X": tippmix_event.get("odds_x"),
            "2": tippmix_event.get("odds_2"),
            "O2.5": tippmix_event.get("over_25"),
            "U2.5": tippmix_event.get("under_25"),
            "BTTS Igen": tippmix_event.get("btts_yes"),
            "BTTS Nem": tippmix_event.get("btts_no"),
        }

    return {
        "bookmaker": "TippmixPro",
        "home_xg_team": home_stats.get("name"),
        "away_xg_team": away_stats.get("name"),
        "home_xg_for": home_stats.get("xg_for"),
        "away_xg_for": away_stats.get("xg_for"),
        "expected_home_goals": lam_h,
        "expected_away_goals": lam_a,
        "expected_total_goals": round(lam_h + lam_a, 2),
        "model_meta": meta,
        "home_form": meta.get("home_form"),
        "away_form": meta.get("away_form"),
        "home_attack_balance": meta.get("home_attack_balance"),
        "away_attack_balance": meta.get("away_attack_balance"),
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
        "tippmix_odds": best.get("tippmix_odds"),
        "tippmix_markets": tippmix_markets,
        "tippmix_matched": bool(tippmix_event),
        "edge_pct": best.get("edge_pct"),
        "is_value": True,
        "odds_in_band": True,
        "is_actionable": True,
        "min_prob_pct": min_prob_pct,
        "odds_band": [odds_min, odds_max],
    }


def attach_xg_tips(
    matches: list[dict[str, Any]],
    xg_by_league: dict[str, dict[str, dict[str, Any]]],
    config: dict,
    tippmix_index: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    home_adv = float(config.get("xg_home_advantage", 1.08))
    min_games = int(config.get("xg_min_team_games", 4))
    min_prob = float(config.get("xg_min_prob_pct", 45.0))
    top_n = int(config.get("top_tips", 5))
    today_only = bool(config.get("today_only", True))
    odds_min = float(config.get("odds_min", 1.8))
    odds_max = float(config.get("odds_max", 2.1))
    value_threshold = float(config.get("value_threshold", 1.02))
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
        # csak Understat ligákból tippelünk (elkerüli a Championship/CL hibás fuzzy match-et)
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
            home_advantage=home_adv,
            min_team_games=min_games,
            min_prob_pct=min_prob,
            odds_min=odds_min,
            odds_max=odds_max,
            value_threshold=value_threshold,
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

    all_tips.sort(key=lambda t: (t.get("edge_pct") or 0, t.get("prob_pct") or 0), reverse=True)
    top_tips = all_tips[:top_n]
    top_ids = {t["match_id"] for t in top_tips}
    for t in all_tips:
        t["is_top"] = t["match_id"] in top_ids
    for m in matches:
        mid = m.get("id")
        if m.get("xg_tip"):
            m["xg_tip"]["is_top"] = mid in top_ids

    return matches, all_tips, top_tips
