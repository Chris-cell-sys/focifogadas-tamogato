# Focifogadás támogató

Kis Python program, ami **API kulcs nélkül**, az internetről (ESPN nyilvános JSON) frissíti a közelgő focimeccseket és az **1X2 oddsokat**.

GitHub Actions naponta többször lefuttatja, és commitolja:

- [`data/odds.json`](data/odds.json)
- [`reports/latest.md`](reports/latest.md) ← ezt nézd

> Döntéstámogató eszköz, nem pénzügyi tanács. Fogadj felelősen.

## Mit csinál?

1. Lekéri a közelgő meccseket több ligából (PL, La Liga, BL, Serie A, Ligue 1, BL, EL, Championship).
2. Kiolvassa a fogadóirodai 1X2 oddsokat (decimal formában).
3. Markdown jelentést és JSON-t ment a repóba.

## GitHub-on futtatás

1. **Actions** fül → *Frissítsd a focioddsokat* → **Run workflow**
2. A futás után nyisd meg: [`reports/latest.md`](reports/latest.md)

Nincs secret / API kulcs beállítás. Ütemezés: naponta 3× (UTC 07 / 13 / 19).

## Helyben

```bash
pip install -r requirements.txt
python main.py
```

## Beállítás (`config.yaml`)

| Mező | Jelentés |
| --- | --- |
| `leagues` | Mely ESPN ligákat kérje le |
| `lookahead_days` | Hány napra előre |
| `value_threshold` | Value tipp küszöb (több iroda kell hozzá) |

## Felelősség

A fogadás kockázatos. Az oddsok változnak; mindig ellenőrizd a fogadóirodánál. 18+.
