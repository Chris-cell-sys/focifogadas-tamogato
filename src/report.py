"""Markdown jelentés – ensemble modellek + stake."""

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
    return f"{t.get('home_form') or '?'} / {t.get('away_form') or '?'}"


def _stake(t: dict[str, Any], currency: str) -> str:
    val = t.get("suggested_stake")
    if val is None:
        return "–"
    return f"**{int(val):,} {currency}**".replace(",", " ")


def _models_line(t: dict[str, Any]) -> str:
    m = t.get("models") or {}
    return f"S:{m.get('stat_prob_pct', '–')}% · X:{m.get('xg_prob_pct', '–')}% · F:{m.get('form_prob_pct', '–')}%"


def write_report(payload: dict[str, Any], path: Path, config: dict) -> None:
    matches = payload.get("matches") or []
    today_matches = [m for m in matches if m.get("is_today")]
    slate = [m for m in matches if m.get("on_slate")]
    top_tips = payload.get("top_tips") or []
    all_tips = payload.get("xg_tips") or []
    min_prob = float(config.get("xg_min_prob_pct", 45.0))
    odds_min = float(config.get("odds_min", 1.8))
    odds_max = float(config.get("odds_max", 2.1))
    bankroll = float(config.get("bankroll", 100_000))
    currency = str(config.get("currency", "HUF"))
    kelly = float(config.get("kelly_fraction", 0.25))

    config_names = {}
    for league in config.get("leagues") or []:
        if isinstance(league, dict):
            config_names[league.get("key")] = league.get("name")

    today_label = datetime.now(BUDAPEST).strftime("%Y-%m-%d")

    lines: list[str] = [
        "# TippmixPro – ensemble tippek + stake",
        "",
        f"**Ma (BUÉK):** `{today_label}` · **csak mai meccsek**  ",
        f"**Mai meccsek a listán:** {len(today_matches)}  ",
        f"**Frissítve (UTC):** `{payload.get('updated_at')}`  ",
        f"**Bankroll:** `{int(bankroll):,} {currency}` · stake: **{kelly:.0%} Kelly** (max {float(config.get('max_stake_pct', 0.03))*100:.0f}%/tipp)  ",
        f"**Odds sáv:** `{odds_min:.1f}` – `{odds_max:.1f}`  ",
        f"**Mai value tippek:** {len(all_tips)}  ",
        f"**Top tippek:** {len(top_tips)}",
        "",
        "> **Stat** – szezon teljesítmény · **xG** – open-play xG/xGA · **Form** – utolsó 5 meccs  ",
        "> **Market** – bookmaker implicit esély · **Value** – ensemble vs piac · **Elite** – egyetértés + edge  ",
        "> Mindig az **aktuális nap** (Budapest) tippjei. Nem pénzügyi tanács.",
        "",
        f"## Mai top tippek ({today_label})",
        "",
    ]

    if not top_tips:
        lines.append(f"_Ma ({today_label}) nincs value tipp a 1.8–2.1 sávban._")
        lines.append("")
    else:
        lines.extend(
            [
                "| # | Kezdés | Meccs | Modell (S/X/F) | Tipp | Esély | Odds | Edge | Elite | Stake |",
                "| -: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for i, t in enumerate(top_tips, 1):
            edge = t.get("edge_pct")
            edge_s = f"{edge:.1f}%" if edge is not None else "–"
            elite = t.get("elite_score")
            lines.append(
                f"| **{i}** | {_kick(t)} | **{t['home_team']} – {t['away_team']}** | "
                f"`{_models_line(t)}` | **{t.get('short')}** | {t.get('prob_pct', 0):.0f}% | "
                f"{_tmp_odds(t)} | {edge_s} | **{elite}** | {_stake(t, currency)} |"
            )
        lines.append("")

    lines.extend(
        [
            f"## Mai value tippek ({today_label}, odds {odds_min:.1f}–{odds_max:.1f})",
            "",
            "| Kezdés | Meccs | Forma | Tipp | Ensemble | Implied | Edge | Elite | Stake |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    if not all_tips:
        lines.append(f"| – | _Ma nincs tipp_ | – | – | – | – | – | – | – |")
    else:
        for t in sorted(all_tips, key=lambda x: x.get("commence_time") or ""):
            star = "⭐ " if t.get("is_top") else ""
            implied = (t.get("models") or {}).get("ensemble_prob_pct")
            # implied from market stored on recommendation path - use staking inverse if needed
            imp = t.get("implied_prob_pct")
            if imp is None and t.get("tippmix_odds"):
                imp = round(100.0 / float(t["tippmix_odds"]), 1)
            lines.append(
                f"| {_kick(t)} | {star}{t['home_team']} – {t['away_team']} | `{_form(t)}` | "
                f"**{t.get('short')}** | {t.get('prob_pct', 0):.0f}% | {imp or '–'}% | "
                f"{t.get('edge_pct') or '–'}% | {t.get('elite_score') or '–'} | {_stake(t, currency)} |"
            )
    lines.append("")

    tippmix_events = payload.get("tippmix_events") or []
    # csak mai Tippmix meccsek
    today_mmdd = datetime.now(BUDAPEST).strftime("%m.%d")
    tippmix_today = []
    for e in tippmix_events:
        kick_local = e.get("kickoff_local") or ""
        commence = e.get("commence_time") or ""
        if kick_local.startswith(today_mmdd) or commence.startswith(today_label):
            tippmix_today.append(e)
    if tippmix_today:
        lines.extend(
            [
                f"## TippmixPro – mai szorzók ({today_label})",
                "",
                "| Kezdés | Meccs | 1 | X | 2 | O2.5 | U2.5 | BTTS I | BTTS N |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for e in tippmix_today[:30]:
            kick = format_kickoff_hu(e.get("commence_time")) or e.get("kickoff_local") or "?"
            lines.append(
                f"| {kick} | {e.get('home_team')} – {e.get('away_team')} | "
                f"{e.get('odds_1')} | {e.get('odds_x')} | {e.get('odds_2')} | "
                f"{e.get('over_25')} | {e.get('under_25')} | {e.get('btts_yes')} | {e.get('btts_no')} |"
            )
        lines.append("")
    elif tippmix_events:
        lines.append(f"_Ma ({today_label}) nincs TippmixPro meccs a scrapelt listán._")
        lines.append("")

    upcoming = [m for m in matches if not m.get("on_slate")]
    if upcoming:
        lines.extend(["## Közelgő (nem a listán)", ""])
        for m in upcoming[:15]:
            league = config_names.get(m.get("league")) or LEAGUE_NAMES.get(m.get("league"), m.get("league"))
            kick = m.get("kickoff_display") or format_kickoff_hu(m.get("commence_time")) or "?"
            lines.append(f"- {kick} · {m['home_team']} – {m['away_team']} ({league})")
        lines.append("")

    lines.extend(
        [
            "---",
            f"_Ensemble: stat + xG + form · odds {odds_min:.1f}–{odds_max:.1f} · min. esély {min_prob}% · bankroll {int(bankroll)} {currency}_",
            "",
        ]
    )

    path.write_text("\n".join(lines), encoding="utf-8")
