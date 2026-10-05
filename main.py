"""Focifogadás támogató – meccsek és oddsok frissítése (API kulcs nélkül)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.analyze import analyze_events
from src.fetch_odds import fetch_all_leagues
from src.report import write_report

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

    print("Élő meccsek/oddsok lekérése az ESPN nyilvános API-járól…")
    events = fetch_all_leagues(config)
    print(f"Összesen {len(events)} meccs.")

    analyzed = analyze_events(events, value_threshold=float(config.get("value_threshold", 1.05)))

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "espn-public",
        "match_count": len(analyzed),
        "with_odds": sum(1 for e in analyzed if e.get("best_odds")),
        "value_bets": sum(1 for e in analyzed if e.get("value_bets")),
        "matches": analyzed,
    }

    odds_path = DATA_DIR / "odds.json"
    odds_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Mentve: {odds_path}")

    report_path = REPORTS_DIR / "latest.md"
    write_report(payload, report_path, config)
    print(f"Jelentés: {report_path}")


if __name__ == "__main__":
    main()
