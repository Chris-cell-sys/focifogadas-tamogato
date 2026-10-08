"""TippmixPro odds lekérés Playwrighttal (API kulcs nélkül)."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime
from difflib import get_close_matches
from typing import Any
from zoneinfo import ZoneInfo

BUDAPEST = ZoneInfo("Europe/Budapest")

TIPPMIX_HOME_URL = "https://sports2.tippmixpro.hu/hu"
# A főoldal 0 meccset adott és csak lassított. A top ligák + Európa elég a mai naphoz.
TIPPMIX_FOOTBALL_URLS = [
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/anglia/77/osszes/0",
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/spanyolorszag/65/osszes/0",
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/nemetorszag/54/osszes/0",
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/olaszorszag/111/osszes/0",
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/franciaorszag/73/osszes/0",
    "https://sports2.tippmixpro.hu/hu/bajnoksag-lokacio/labdarugas/1/europa/67/osszes/0",
]

EXTRACT_JS = r"""
() => {
  const f = (x) => parseFloat(String(x).replace(',', '.'));
  const collectButtons = (root) => {
    const out = [];
    const walk = (node, depth=0) => {
      if (!node || depth > 25) return;
      const list = node.querySelectorAll ? node.querySelectorAll('button, [role="button"]') : [];
      for (const el of list) {
        const t = (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim();
        if (t) out.push(t);
        if (el.shadowRoot) walk(el.shadowRoot, depth+1);
      }
      const all = node.querySelectorAll ? node.querySelectorAll('*') : [];
      for (const el of all) if (el.shadowRoot) walk(el.shadowRoot, depth+1);
    };
    walk(root);
    return out;
  };

  const parseOdds = (btns) => {
    const map = {};
    for (const t of btns) {
      let mm;
      if ((mm = t.match(/^Hazai\s+([0-9]+,[0-9]+)$/))) map.odds_1 = f(mm[1]);
      else if ((mm = t.match(/^Döntetlen\s+([0-9]+,[0-9]+)$/))) map.odds_x = f(mm[1]);
      else if ((mm = t.match(/^Vendég\s+([0-9]+,[0-9]+)$/))) map.odds_2 = f(mm[1]);
      else if ((mm = t.match(/^Több,\s*mint\s+([0-9]+,[0-9]+)$/))) map.over_25 = f(mm[1]);
      else if ((mm = t.match(/^Kevesebb,\s*mint\s+([0-9]+,[0-9]+)$/))) map.under_25 = f(mm[1]);
      else if ((mm = t.match(/^Igen\s+([0-9]+,[0-9]+)$/))) map.btts_yes = f(mm[1]);
      else if ((mm = t.match(/^Nem\s+([0-9]+,[0-9]+)$/))) map.btts_no = f(mm[1]);
    }
    return map;
  };

  const out = [];
  const links = Array.from(document.querySelectorAll('a'));
  for (const a of links) {
    const label = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
    const m = label.match(/^(.+?)\s+(\d{2}\.\d{2})\s+(\d{2}:\d{2})$/);
    if (!m) continue;
    const teams = m[1].trim();
    if (/\d+\s+\d+\s+\d+'/.test(teams)) continue;
    if (/LIVE|félidő|2\. félidő/i.test(teams)) continue;

    let root = a.parentElement;
    let odds = null;
    for (let i = 0; i < 10 && root; i++) {
      const map = parseOdds(collectButtons(root));
      if (map.odds_1 && map.odds_x && map.odds_2) { odds = map; break; }
      root = root.parentElement;
    }
    if (!odds) continue;

    const parts = teams.split(' ').filter(Boolean);
    if (parts.length < 2) continue;
    let home, away;
    if (parts.length === 2) { home = parts[0]; away = parts[1]; }
    else if (parts.length === 3) { home = parts[0] + ' ' + parts[1]; away = parts[2]; }
    else { away = parts.slice(-2).join(' '); home = parts.slice(0, -2).join(' '); }

    out.push({
      home_team: home,
      away_team: away,
      teams_raw: teams,
      date: m[2],
      time: m[3],
      ...odds,
    });
  }
  const seen = new Set();
  const uniq = [];
  for (const e of out) {
    const k = (e.home_team + '|' + e.away_team + '|' + e.date + '|' + e.time).toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    uniq.push(e);
  }
  return uniq;
}
"""


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # gyakori rövidítések
    repl = {
        "manchester united": "man united",
        "manchester city": "man city",
        "tottenham hotspur": "tottenham",
        "brighton and hove albion": "brighton",
        "brighton hove albion": "brighton",
        "wolverhampton wanderers": "wolves",
        "paris saint germain": "psg",
        "internazionale": "inter",
        "inter milan": "inter",
        "borussia dortmund": "dortmund",
        "bayern munich": "bayern",
        "atletico madrid": "atletico",
        "atlético madrid": "atletico",
    }
    return repl.get(text, text)


def _parse_tippmix_kickoff(date_mmdd: str, time_hhmm: str, now: datetime | None = None) -> str | None:
    """TippmixPro '10.05 20:45' = hónap.nap (MM.DD) -> ISO Budapest."""
    now = now or datetime.now(BUDAPEST)
    try:
        month, day = map(int, date_mmdd.split("."))
        hour, minute = map(int, time_hhmm.split(":"))
        year = now.year
        dt = datetime(year, month, day, hour, minute, tzinfo=BUDAPEST)
        if (now - dt).days > 180:
            dt = datetime(year + 1, month, day, hour, minute, tzinfo=BUDAPEST)
        return dt.isoformat()
    except Exception:
        return None


async def _scrape_one(context, url: str, timeout_ms: int) -> list[dict[str, Any]]:
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_selector("text=Hazai", timeout=8000)
        except Exception:
            print(f"  Tippmix: nincs odds ({url.split('/')[-3][:24]})")
            return []
        await page.mouse.wheel(0, 2800)
        await page.wait_for_timeout(200)
        raw = await page.evaluate(EXTRACT_JS) or []
        print(f"  Tippmix oldal: {len(raw)} meccs ({url.split('/labdarugas/')[-1][:40]})")
        return raw
    except Exception as exc:
        print(f"  Tippmix oldal hiba: {exc}")
        return []
    finally:
        await page.close()


async def _fetch_async(timeout_ms: int) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="hu-HU",
            timezone_id="Europe/Budapest",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8"},
        )
        batches = await asyncio.gather(*[_scrape_one(context, url, timeout_ms) for url in TIPPMIX_FOOTBALL_URLS])
        await browser.close()
    collected: list[dict[str, Any]] = []
    for batch in batches:
        collected.extend(batch)
    return collected


def fetch_tippmixpro_events(timeout_ms: int = 15000) -> list[dict[str, Any]]:
    """A ligák egyszerre töltődnek, nem egymás után."""
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("playwright nincs telepítve") from exc

    collected = asyncio.run(_fetch_async(timeout_ms))
    now = datetime.now(BUDAPEST)
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in collected:
        key = f"{item.get('home_team')}|{item.get('away_team')}|{item.get('date')}|{item.get('time')}"
        if key in seen:
            continue
        seen.add(key)
        kick = _parse_tippmix_kickoff(item.get("date", ""), item.get("time", ""), now=now)
        events.append(
            {
                **item,
                "kickoff_local": f"{item.get('date')} {item.get('time')}",
                "commence_time": kick,
                "source": "tippmixpro",
            }
        )
    return events


def index_tippmix_events(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Kulcs: normalized 'home|away'."""
    idx: dict[str, dict[str, Any]] = {}
    for e in events:
        key = f"{_normalize(e.get('home_team',''))}|{_normalize(e.get('away_team',''))}"
        idx[key] = e
        # fordított is, biztonság kedvéért nem – hazai/vendég fontos
    return idx


def find_tippmix_event(
    home: str,
    away: str,
    index: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not index:
        return None
    key = f"{_normalize(home)}|{_normalize(away)}"
    if key in index:
        return index[key]

    # fuzzy: mindkét név közel legyen
    homes = list({k.split("|")[0] for k in index})
    aways = list({k.split("|")[1] for k in index})
    h = get_close_matches(_normalize(home), homes, n=1, cutoff=0.72)
    a = get_close_matches(_normalize(away), aways, n=1, cutoff=0.72)
    if h and a:
        cand = f"{h[0]}|{a[0]}"
        if cand in index:
            return index[cand]

    # partial contains
    nh, na = _normalize(home), _normalize(away)
    for k, ev in index.items():
        kh, ka = k.split("|", 1)
        if (nh in kh or kh in nh) and (na in ka or ka in na):
            return ev
    return None


def odds_for_pick(event: dict[str, Any] | None, short: str | None) -> float | None:
    if not event or not short:
        return None
    mapping = {
        "1": "odds_1",
        "X": "odds_x",
        "2": "odds_2",
        "O2.5": "over_25",
        "U2.5": "under_25",
        "BTTS Igen": "btts_yes",
        "BTTS Nem": "btts_no",
    }
    field = mapping.get(short)
    if not field:
        return None
    val = event.get(field)
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def format_kickoff_hu(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        raw = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        local = dt.astimezone(BUDAPEST)
        days = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
        return f"{local.strftime('%Y-%m-%d %H:%M')} ({days[local.weekday()]})"
    except Exception:
        return iso
