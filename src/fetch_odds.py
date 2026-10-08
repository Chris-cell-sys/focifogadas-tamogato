"""ESPN nyilvános site API – meccsek + odds, API kulcs nélkül."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def american_to_decimal(american: int | float | str | None) -> float | None:
    if american is None or american == "":
        return None
    try:
        value = float(str(american).replace("+", ""))
    except ValueError:
        return None
    if value > 0:
        return round(value / 100.0 + 1.0, 3)
    if value < 0:
        return round(100.0 / abs(value) + 1.0, 3)
    return None


def _moneyline_side(moneyline: dict | None, side: str) -> float | None:
    if not moneyline:
        return None
    block = moneyline.get(side) or {}
    close = (block.get("close") or {}).get("odds")
    open_ = (block.get("open") or {}).get("odds")
    return american_to_decimal(close if close is not None else open_)


def _parse_odds_entry(entry: dict[str, Any] | None, home: str, away: str) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    provider = ((entry.get("provider") or {}).get("name")) or "ESPN"
    moneyline = entry.get("moneyline") or {}
    if not isinstance(moneyline, dict):
        moneyline = {}

    home_odds = _moneyline_side(moneyline, "home")
    away_odds = _moneyline_side(moneyline, "away")
    draw_odds = _moneyline_side(moneyline, "draw")

    # fallback: drawOdds.moneyLine (American)
    if draw_odds is None:
        draw_block = entry.get("drawOdds")
        if isinstance(draw_block, dict):
            draw_odds = american_to_decimal(draw_block.get("moneyLine"))

    if home_odds is None and away_odds is None and draw_odds is None:
        return None

    outcomes = []
    if home_odds is not None:
        outcomes.append({"name": home, "price": home_odds})
    if draw_odds is not None:
        outcomes.append({"name": "Draw", "price": draw_odds})
    if away_odds is not None:
        outcomes.append({"name": away, "price": away_odds})

    return {
        "key": provider.lower().replace(" ", "_"),
        "title": provider,
        "last_update": datetime.now(timezone.utc).isoformat(),
        "markets": [{"key": "h2h", "outcomes": outcomes}],
        "over_under": entry.get("overUnder"),
    }


def _scoreboard_queries(lookahead_days: int) -> list[dict[str, str | int]]:
    """Először az alap közelgő lista, aztán a következő napok külön."""
    # Az ESPN alap scoreboard általában a következő fordulót adja.
    queries: list[dict[str, str | int]] = [{"limit": 100}]
    # Extra napok csak ha kell (GitHub Actionsban is tartható legyen)
    days = min(max(1, lookahead_days), 5)
    start = datetime.now(timezone.utc).date()
    for offset in range(0, days + 1):
        day = start + timedelta(days=offset)
        queries.append({"dates": day.strftime("%Y%m%d"), "limit": 100})
    return queries


def _ingest_payload(
    payload: dict[str, Any],
    *,
    league_key: str,
    league_name: str,
    seen: set[str],
    events_out: list[dict[str, Any]],
) -> None:
    for event in payload.get("events") or []:
        event_id = str(event.get("id") or "")
        if not event_id or event_id in seen:
            continue

        competitions = event.get("competitions") or []
        if not competitions:
            continue
        comp = competitions[0]
        status = ((comp.get("status") or {}).get("type") or {}).get("name", "")
        if status in {"STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_POSTPONED", "STATUS_CANCELED"}:
            continue

        home = away = ""
        for team in comp.get("competitors") or []:
            name = ((team.get("team") or {}).get("displayName")) or ""
            if team.get("homeAway") == "home":
                home = name
            elif team.get("homeAway") == "away":
                away = name
        if not home or not away:
            continue

        bookmakers = []
        for odds_entry in comp.get("odds") or []:
            if not odds_entry:
                continue
            try:
                parsed = _parse_odds_entry(odds_entry, home, away)
            except Exception:
                continue
            if parsed:
                bookmakers.append(parsed)

        if not bookmakers:
            bookmakers = fetch_core_odds(league_key, event_id, home, away)

        seen.add(event_id)
        events_out.append(
            {
                "id": event_id,
                "sport_key": league_key,
                "_league": league_key,
                "sport_title": league_name,
                "commence_time": event.get("date") or comp.get("date"),
                "home_team": home,
                "away_team": away,
                "status": status,
                "bookmakers": bookmakers,
            }
        )


def fetch_league(
    league_key: str,
    league_name: str,
    *,
    lookahead_days: int = 7,
) -> list[dict[str, Any]]:
    events_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}/scoreboard"

    for params in _scoreboard_queries(lookahead_days):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            print(f"  Hiba ({league_key} {params}): {exc}")
            continue
        _ingest_payload(
            payload,
            league_key=league_key,
            league_name=league_name,
            seen=seen,
            events_out=events_out,
        )

    events_out.sort(key=lambda e: e.get("commence_time") or "")
    return events_out


def fetch_core_odds(
    league_key: str,
    event_id: str,
    home: str,
    away: str,
) -> list[dict[str, Any]]:
    url = (
        f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/"
        f"{league_key}/events/{event_id}/competitions/{event_id}/odds"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        if response.status_code != 200:
            return []
        data = response.json()
    except requests.RequestException:
        return []

    items = data.get("items") or ([data] if data.get("moneyline") or data.get("provider") else [])
    books: list[dict[str, Any]] = []
    for entry in items:
        parsed = _parse_odds_entry(entry, home, away)
        if parsed:
            books.append(parsed)
    return books


def fetch_all_leagues(config: dict) -> list[dict[str, Any]]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    leagues = config.get("leagues") or []
    lookahead = int(config.get("lookahead_days", 3))
    all_events: list[dict[str, Any]] = []

    normalized: list[tuple[str, str]] = []
    for league in leagues:
        if isinstance(league, str):
            normalized.append((league, league))
        else:
            normalized.append((league["key"], league.get("name") or league["key"]))

    def _one(item: tuple[str, str]) -> tuple[str, str, list[dict[str, Any]]]:
        key, name = item
        return key, name, fetch_league(key, name, lookahead_days=lookahead)

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(normalized)))) as pool:
        futures = [pool.submit(_one, item) for item in normalized]
        for fut in as_completed(futures):
            try:
                key, name, events = fut.result()
            except Exception as exc:
                print(f"  Liga hiba (kihagyva): {exc}")
                continue
            with_odds = sum(1 for e in events if e.get("bookmakers"))
            print(f"  {name} ({key}): {len(events)} meccs, {with_odds} odds-szal")
            all_events.extend(events)

    all_events.sort(key=lambda e: e.get("commence_time") or "")
    return all_events
