"""Focifogadás támogató – TippmixPro tippek xG alapján."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.analyze import analyze_events
from src.fetch_odds import fetch_all_leagues
from src.fetch_xg import fetch_xg_for_leagues
from src.report import write_report
from src.xg_tips import attach_xg_tips

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    config = load_config()
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)

    print("Élő meccsek/oddsok lekérése…")
    events = fetch_all_leagues(config)
    print(f"Összesen {len(events)} meccs.")

    analyzed = analyze_events(events, value_threshold=float(config.get("value_threshold", 1.05)))

    league_keys = list(dict.fromkeys(m.get("league") for m in analyzed if m.get("league")))
    print("Csapat xG adatok (Understat)…")
    xg_by_league = fetch_xg_for_leagues(league_keys)
    analyzed, xg_tips, top_tips = attach_xg_tips(analyzed, xg_by_league, config)

    today_count = sum(1 for m in analyzed if m.get("is_today"))
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "espn-public + understat-xg",
        "bookmaker": "TippmixPro",
        "match_count": len(analyzed),
        "today_count": today_count,
        "with_odds": sum(1 for e in analyzed if e.get("best_odds")),
        "xg_tips_count": len(xg_tips),
        "xg_tips": xg_tips,
        "top_tips": top_tips,
        "matches": analyzed,
    }

    odds_path = DATA_DIR / "odds.json"
    odds_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mentve: {odds_path} (mai: {today_count}, tippek: {len(xg_tips)}, top: {len(top_tips)})")

    report_path = REPORTS_DIR / "latest.md"
    write_report(payload, report_path, config)
    print(f"Jelentés: {report_path}")


if __name__ == "__main__":
    main()
