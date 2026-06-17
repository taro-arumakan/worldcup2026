# World Cup 2026 — UK & Japan TV calendar

A subscribable `.ics` calendar of **all 104** 2026 FIFA World Cup matches, with the
**UK** (🇬🇧 BBC/ITV) and **Japan free-to-air** (🇯🇵 NHK/NTV/Fuji) broadcaster written
into every event title — e.g. `Netherlands v Japan — 🇬🇧 ITV · 🇯🇵 NHK`.

Hosted free on GitHub Pages. No server, no tracking.

## Subscribe

| Client | How |
| --- | --- |
| **iPhone / iPad / Mac** | Open <webcal://taro-arumakan.github.io/worldcup-2026-calendar/worldcup.ics> → Add |
| **Google Calendar** | Other calendars ▸ **+** ▸ *From URL* → paste the HTTPS URL below |
| **Outlook** | Add calendar ▸ *Subscribe from web* → paste the HTTPS URL |

**Feed URL:** `https://taro-arumakan.github.io/worldcup-2026-calendar/worldcup.ics`
**Landing page:** https://taro-arumakan.github.io/worldcup-2026-calendar/

Kickoffs are stored in **UTC**, so every client shows them in *your* local time zone.

## Labels

- 🇬🇧 `BBC` / `ITV` — UK free-to-air (also iPlayer / ITVX; STV in Scotland).
- 🇯🇵 `NHK` (NHK総合), `NTV` (日本テレビ), `Fuji` (フジテレビ) — Japanese free-to-air. `BS4K` = NHK BS Premium 4K only.
- **No 🇯🇵 label** = DAZN-only in Japan (paid). Only DAZN carries all 104 matches live.
- **Knockouts** show bracket slots (`1A v 3C/E/F/H/I`, `W74 v W77`) and broadcasters are **TBC** — they depend on qualification.

## How it's built

```
data/cup.txt, cup_finals.txt, cup_stadiums.csv   # fixtures/venues (vendored from openfootball)
data/broadcasters.json                            # UK + JP broadcaster overlay, keyed by team pair
generate.py                                        # parses the above → docs/worldcup.ics
docs/worldcup.ics                                  # the published calendar
docs/index.html                                    # landing page
```

Regenerate after editing data:

```sh
python3 generate.py          # validates counts, rewrites docs/worldcup.ics
```

The script asserts 72 group + 32 knockout events, that every group match has a UK
channel, and that every venue resolves — it exits non-zero if anything is off.

## Data sources & caveats

- Fixtures, kickoff times, venues, bracket: [openfootball/world-cup](https://github.com/openfootball/world-cup) (public domain).
- UK BBC/ITV split: [Sports Mole](https://www.sportsmole.co.uk/football/england/world-cup/feature/world-cup-tv-schedule-where-to-watch-every-game-in-the-uk_596524.html).
- Japan free-to-air: [ABEMA TIMES](https://times.abema.tv/articles/-/10243707).

Broadcaster assignments (especially knockouts and late schedule changes) can move.
Verify against the broadcaster before kickoff. PRs to `data/broadcasters.json` welcome.
