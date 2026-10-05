"""Markdown jelentés – mai TippmixPro tippek."""

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

BUDAPEST = ZoneInfo("Europe/Budapest")


def _fmt_time(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(BUDAPEST).strftime("%H:%M")
    except Exception:
        return iso


def write_report(payload: dict[str, Any], path: Path, config: dict) -> None:
    matches = payload.get("matches") or []
    today_matches = [m for m in matches if m.get("is_today")]
    slate = [m for m in matches if m.get("on_slate")]
    top_tips = payload.get("top_tips") or []
    all_tips = payload.get("xg_tips") or []
    min_prob = float(config.get("xg_min_prob_pct", 52.0))

    config_names = {}
    for league in config.get("leagues") or []:
        if isinstance(league, dict):
            config_names[league.get("key")] = league.get("name")

    today_label = datetime.now(BUDAPEST).strftime("%Y-%m-%d")
    slate_label = "Mai meccsek" if today_matches else "Aktuális forduló (legközelebbi nap)"
    if all_tips and all_tips[0].get("kickoff_local"):
        slate_day = (all_tips[0].get("kickoff_local") or "")[:10]
    else:
        slate_day = today_label

    lines: list[str] = [
        "# TippmixPro tippek (xG)",
        "",
        f"**Ma (BUÉK):** `{today_label}`  ",
        f"**Mutatott nap:** `{slate_day}`  ",
        f"**Frissítve (UTC):** `{payload.get('updated_at')}`  ",
        f"**Bukméker:** TippmixPro  ",
        f"**Meccsek a listán:** {len(slate)}  ",
        f"**Tippek:** {len(all_tips)}  ",
        f"**Top tippek:** {len(top_tips)}",
        "",
        "> TippmixPro piacokra: **1X2**, **BTTS**, **Over/Under 2.5**. "
        "A *fair odds* a modell szerinti szorzó – nézd meg TippmixPron, van-e jobb/rosszabb ár. "
        "Nem pénzügyi tanács.",
        "",
        "## Top 5 legesélyesebb tipp",
        "",
    ]

    if not top_tips:
        lines.append("_Nincs elég erős tipp a mai napra._")
        lines.append("")
    else:
        lines.extend(
            [
                "| # | Idő | Meccs | Mire fogadj | Esély | Fair odds | Várható gól |",
                "| -: | --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for i, t in enumerate(top_tips, 1):
            lines.append(
                f"| **{i}** | {_fmt_time(t.get('commence_time'))} | "
                f"**{t['home_team']} – {t['away_team']}** | "
                f"**{t.get('short')}** ({t.get('market')}) | "
                f"**{t.get('prob_pct', 0):.0f}%** | {t.get('fair_odds') or '–'} | "
                f"{t.get('expected_score', '–')} |"
            )
        lines.append("")

    lines.extend(
        [
            f"## {slate_label} – mire érdemes fogadni",
            "",
            "| Idő | Meccs | Győztes | BTTS | Gólok 2.5 | Fő tipp | Esély | Fair |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: |",
        ]
    )

    if not all_tips:
        lines.append("| – | _Nincs mai meccs tippelhető xG-vel_ | – | – | – | – | – | – |")
        lines.append("")
    else:
        for t in sorted(all_tips, key=lambda x: x.get("commence_time") or ""):
            star = "⭐ " if t.get("is_top") else ""
            lines.append(
                f"| {_fmt_time(t.get('commence_time'))} | {star}{t['home_team']} – {t['away_team']} | "
                f"{t.get('winner_pick')} ({t.get('winner_prob', 0):.0f}%) | "
                f"{t.get('btts_pick')} ({t.get('btts_prob', 0):.0f}%) | "
                f"{t.get('goals_pick')} ({t.get('goals_prob', 0):.0f}%) | "
                f"**{t.get('short')}** | {t.get('prob_pct', 0):.0f}% | {t.get('fair_odds') or '–'} |"
            )
        lines.append("")

    # ha nincs mai meccs, mutassuk a közelit is röviden
    upcoming = [m for m in matches if not m.get("is_today")]
    if upcoming:
        lines.extend(["## Közelgő meccsek (nem ma)", ""])
        lines.extend(
            [
                "| Dátum | Meccs | Liga |",
                "| --- | --- | --- |",
            ]
        )
        for m in upcoming[:20]:
            league = config_names.get(m.get("league")) or LEAGUE_NAMES.get(m.get("league"), m.get("league"))
            kick = m.get("kickoff_local") or m.get("commence_time") or "?"
            lines.append(f"| {kick} | {m['home_team']} – {m['away_team']} | {league} |")
        lines.append("")

    lines.extend(
        [
            "---",
            f"_Modell: Understat xG + Poisson · min. esély: {min_prob}% · TippmixPro piacok_",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
