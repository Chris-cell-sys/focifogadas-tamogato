"""Odds elemzés: legjobb árak, átlag, value tippek."""

from __future__ import annotations

from typing import Any


def _h2h_market(bookmaker: dict) -> dict | None:
    for market in bookmaker.get("markets") or []:
        if market.get("key") == "h2h":
            return market
    return None


def analyze_event(event: dict[str, Any], value_threshold: float) -> dict[str, Any]:
    home = event.get("home_team", "")
    away = event.get("away_team", "")
    outcome_names = {home, away, "Draw"}

    # outcome -> list of (bookmaker, price)
    prices: dict[str, list[tuple[str, float]]] = {name: [] for name in outcome_names}

    for book in event.get("bookmakers") or []:
        market = _h2h_market(book)
        if not market:
            continue
        title = book.get("title") or book.get("key") or "?"
        for outcome in market.get("outcomes") or []:
            name = outcome.get("name")
            price = outcome.get("price")
            if name in prices and isinstance(price, (int, float)):
                prices[name].append((title, float(price)))

    best: dict[str, dict[str, Any]] = {}
    averages: dict[str, float] = {}
    value_bets: list[dict[str, Any]] = []

    for name, entries in prices.items():
        if not entries:
            continue
        entries_sorted = sorted(entries, key=lambda x: x[1], reverse=True)
        best_book, best_price = entries_sorted[0]
        avg = sum(p for _, p in entries) / len(entries)
        averages[name] = round(avg, 3)
        best[name] = {
            "bookmaker": best_book,
            "odds": round(best_price, 3),
            "avg_odds": round(avg, 3),
            "edge": round(best_price / avg, 4) if avg else 1.0,
            "books_count": len(entries),
        }
        if avg > 0 and best_price / avg >= value_threshold:
            value_bets.append(
                {
                    "outcome": name,
                    "odds": round(best_price, 3),
                    "bookmaker": best_book,
                    "avg_odds": round(avg, 3),
                    "edge_pct": round((best_price / avg - 1) * 100, 2),
                }
            )

    value_bets.sort(key=lambda v: v["edge_pct"], reverse=True)

    # rövid címke a kimenetekhez
    labels = {}
    for name in best:
        if name == home:
            labels[name] = "1 (Hazai)"
        elif name == away:
            labels[name] = "2 (Vendég)"
        elif name == "Draw":
            labels[name] = "X (Döntetlen)"
        else:
            labels[name] = name

    return {
        "id": event.get("id"),
        "league": event.get("_league") or event.get("sport_key"),
        "sport_title": event.get("sport_title"),
        "commence_time": event.get("commence_time"),
        "home_team": home,
        "away_team": away,
        "best_odds": best,
        "labels": labels,
        "value_bets": value_bets,
        "bookmaker_count": len(event.get("bookmakers") or []),
    }


def analyze_events(events: list[dict[str, Any]], value_threshold: float = 1.05) -> list[dict[str, Any]]:
    return [analyze_event(e, value_threshold) for e in events]
