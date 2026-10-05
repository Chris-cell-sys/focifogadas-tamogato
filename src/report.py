"""Markdown jelentés generálása a frissített oddsokból."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LEAGUE_NAMES = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ger.1": "Bundesliga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "uefa.champions": "Bajnokok Ligája",
    "uefa.europa": "Európa Liga",
    "eng.2": "Championship",
}


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(ZoneInfo("Europe/Budapest"))
        return local.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def write_report(payload: dict[str, Any], path: Path, config: dict) -> None:
    matches = payload.get("matches") or []
    threshold = float(config.get("value_threshold", 1.05))
    edge_pct = round((threshold - 1) * 100)

    # liga név a configból, ha van
    config_names = {}
    for league in config.get("leagues") or []:
        if isinstance(league, dict):
            config_names[league.get("key")] = league.get("name")

    lines: list[str] = [
        "# Focifogadás – élő odds jelentés",
        "",
        f"**Frissítve (UTC):** `{payload.get('updated_at')}`  ",
        f"**Forrás:** `{payload.get('source')}` (nyilvános net, API kulcs nélkül)  ",
        f"**Meccsek:** {payload.get('match_count', 0)}  ",
        f"**Odds-szal:** {payload.get('with_odds', 0)}  ",
        f"**Value tippek (>={edge_pct}% edge):** {payload.get('value_bets', 0)}",
        "",
        "> Ez egy döntéstámogató eszköz, nem pénzügyi tanács. Fogadj felelősen.",
        "",
        "## Value tippek",
        "",
    ]

    value_rows = []
    for m in matches:
        for vb in m.get("value_bets") or []:
            value_rows.append((m, vb))

    if not value_rows:
        lines.append(
            "_Jelenleg nincs a küszöböt elérő value tipp "
            "(több fogadóiroda kell az összehasonlításhoz)._"
        )
        lines.append("")
    else:
        lines.extend(
            [
                "| Meccs | Kimenet | Odds | Iroda | Átlag | Edge |",
                "| --- | --- | ---: | --- | ---: | ---: |",
            ]
        )
        for m, vb in value_rows:
            label = (m.get("labels") or {}).get(vb["outcome"], vb["outcome"])
            lines.append(
                f"| {m['home_team']} – {m['away_team']} | {label} | "
                f"**{vb['odds']:.2f}** | {vb['bookmaker']} | {vb['avg_odds']:.2f} | "
                f"+{vb['edge_pct']:.1f}% |"
            )
        lines.append("")

    lines.extend(["## Közelgő meccsek – legjobb 1X2 oddsok", ""])

    by_league: dict[str, list] = {}
    for m in matches:
        by_league.setdefault(m.get("league") or "egyéb", []).append(m)

    if not by_league:
        lines.append("_Nincs elérhető meccs._")
        lines.append("")
    else:
        for league, items in by_league.items():
            title = config_names.get(league) or LEAGUE_NAMES.get(league, league)
            lines.append(f"### {title}")
            lines.append("")
            lines.extend(
                [
                    "| Idő (BUÉK) | Meccs | 1 | X | 2 | Forrás |",
                    "| --- | --- | ---: | ---: | ---: | --- |",
                ]
            )
            for m in items:
                best = m.get("best_odds") or {}
                home, away = m["home_team"], m["away_team"]

                def cell(name: str) -> str:
                    info = best.get(name)
                    if not info:
                        return "–"
                    return f"{info['odds']:.2f}"

                providers = []
                for info in best.values():
                    book = info.get("bookmaker")
                    if book and book not in providers:
                        providers.append(book)
                provider_txt = ", ".join(providers) if providers else "–"

                lines.append(
                    f"| {_fmt_time(m.get('commence_time'))} | {home} – {away} | "
                    f"{cell(home)} | {cell('Draw')} | {cell(away)} | {provider_txt} |"
                )
            lines.append("")

    lines.extend(
        [
            "---",
            f"_Automatikusan generálva · forrás: ESPN public · value küszöb: {threshold}_",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
