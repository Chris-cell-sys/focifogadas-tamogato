"""Markdown jelentés – TippmixPro value tippek (1.8–2.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.fetch_tippmixpro import format_kickoff_hu

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


def _kick(t: dict[str, Any]) -> str:
    return t.get("kickoff_display") or format_kickoff_hu(t.get("commence_time")) or "?"


def _tmp_odds(t: dict[str, Any]) -> str:
    val = t.get("tippmix_odds")
    if val is None:
        return "–"
    return f"**{float(val):.2f}**"


def _form(t: dict[str, Any]) -> str:
    h = t.get("home_form") or "?"
    a = t.get("away_form") or "?"
    return f"{h} / {a}"


def write_report(payload: dict[str, Any], path: Path, config: dict) -> None:
    matches = payload.get("matches") or []
    today_matches = [m for m in matches if m.get("is_today")]
    slate = [m for m in matches if m.get("on_slate")]
    top_tips = payload.get("top_tips") or []
    all_tips = payload.get("xg_tips") or []
    min_prob = float(config.get("xg_min_prob_pct", 45.0))
    odds_min = float(config.get("odds_min", 1.8))
    odds_max = float(config.get("odds_max", 2.1))

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
        "# TippmixPro value tippek (forma + open-play xG)",
        "",
        f"**Ma (BUÉK):** `{today_label}`  ",
        f"**Mutatott nap:** `{slate_day}`  ",
        f"**Frissítve (UTC):** `{payload.get('updated_at')}`  ",
        f"**Bukméker:** TippmixPro  ",
        f"**Odds sáv:** `{odds_min:.1f}` – `{odds_max:.1f}`  ",
        f"**TippmixPro meccsek:** {payload.get('tippmix_event_count', 0)}  ",
        f"**Value tippek:** {len(all_tips)}  ",
        f"**Meccsek a listán:** {len(slate)}  ",
        f"**Top tippek:** {len(top_tips)}",
        "",
        "> Modell: utolsó 5 meccs forma, hazai/vendég góltermelés, open-play xG/xGA (npxG), összes xG, támadási egyensúly.  ",
        "> Csak akkor jelenik meg tipp, ha a TippmixPro szorzó **1.8–2.1** között van **és** value (jobb, mint a fair odds).  ",
        "> Nem pénzügyi tanács.",
        "",
        "## Top tippek (legnagyobb edge)",
        "",
    ]

    if not top_tips:
        lines.append("_Nincs value tipp a 1.8–2.1 sávban._")
        lines.append("")
    else:
        lines.extend(
            [
                "| # | Kezdés | Meccs | Forma (H/V) | Tipp | Esély | Tippmix | Fair | Edge |",
                "| -: | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for i, t in enumerate(top_tips, 1):
            edge = t.get("edge_pct")
            edge_s = f"**{edge:.1f}%**" if edge is not None else "–"
            lines.append(
                f"| **{i}** | {_kick(t)} | "
                f"**{t['home_team']} – {t['away_team']}** | "
                f"`{_form(t)}` | "
                f"**{t.get('short')}** ({t.get('market')}) | "
                f"**{t.get('prob_pct', 0):.0f}%** | {_tmp_odds(t)} | "
                f"{t.get('fair_odds') or '–'} | {edge_s} |"
            )
        lines.append("")

    lines.extend(
        [
            f"## {slate_label} – value tippek (odds {odds_min:.1f}–{odds_max:.1f})",
            "",
            "| Kezdés | Meccs | Forma | OP xG H/V | Egyensúly | Tipp | Esély | Tippmix | Fair | Edge |",
            "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )

    if not all_tips:
        lines.append("| – | _Nincs tipp a sávban_ | – | – | – | – | – | – | – | – |")
        lines.append("")
    else:
        for t in sorted(all_tips, key=lambda x: x.get("commence_time") or ""):
            star = "⭐ " if t.get("is_top") else ""
            op = f"{t.get('home_op_xg', '–')} / {t.get('away_op_xg', '–')}"
            bal = f"{t.get('home_attack_balance', '–')} / {t.get('away_attack_balance', '–')}"
            edge = t.get("edge_pct")
            edge_s = f"{edge:.1f}%" if edge is not None else "–"
            lines.append(
                f"| {_kick(t)} | {star}{t['home_team']} – {t['away_team']} | "
                f"`{_form(t)}` | {op} | {bal} | "
                f"**{t.get('short')}** | {t.get('prob_pct', 0):.0f}% | "
                f"{_tmp_odds(t)} | {t.get('fair_odds') or '–'} | {edge_s} |"
            )
        lines.append("")

    tippmix_events = payload.get("tippmix_events") or []
    if tippmix_events:
        lines.extend(
            [
                "## TippmixPro – aktuális szorzók (élő oldal)",
                "",
                "| Kezdés (BUÉK) | Meccs | 1 | X | 2 | O2.5 | U2.5 | BTTS Igen | BTTS Nem |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for e in tippmix_events[:30]:
            kick = format_kickoff_hu(e.get("commence_time")) or e.get("kickoff_local") or "?"
            lines.append(
                f"| {kick} | {e.get('home_team')} – {e.get('away_team')} | "
                f"{e.get('odds_1')} | {e.get('odds_x')} | {e.get('odds_2')} | "
                f"{e.get('over_25')} | {e.get('under_25')} | "
                f"{e.get('btts_yes')} | {e.get('btts_no')} |"
            )
        lines.append("")

    upcoming = [m for m in matches if not m.get("on_slate")]
    if upcoming:
        lines.extend(["## Közelgő meccsek (nem a listán)", ""])
        lines.extend(["| Kezdés (BUÉK) | Meccs | Liga |", "| --- | --- | --- |"])
        for m in upcoming[:20]:
            league = config_names.get(m.get("league")) or LEAGUE_NAMES.get(m.get("league"), m.get("league"))
            kick = m.get("kickoff_display") or format_kickoff_hu(m.get("commence_time")) or "?"
            lines.append(f"| {kick} | {m['home_team']} – {m['away_team']} | {league} |")
        lines.append("")

    lines.extend(
        [
            "---",
            f"_Modell: utolsó 5 forma + open-play xG (npxG) + góltermelés + egyensúly · "
            f"odds sáv {odds_min:.1f}–{odds_max:.1f} · value · min. esély {min_prob}%_",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
