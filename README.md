# World Cup 2026 — TV calendars

Subscribable `.ics` calendars of **all 104** 2026 FIFA World Cup matches, with the
broadcaster written into every event title. Three flavours from the same data.

Hosted free on GitHub Pages. No server, no tracking.
**Landing page:** https://yadot.sniarti.fi/worldcup2026/

## Three feeds

| # | Feed | For | Title example |
| - | --- | --- | --- |
| 1 | `uk.ics` | UK viewers | `England v Ghana — BBC` · `England v Croatia — ITV` |
| 2 | `japan.ics` | Japanese friends | `Mexico v South Africa — NHK` · `England v Croatia` (blank = DAZN only) |
| 3 | `hybrid.ics` | UK channel + JP free-to-air | `Netherlands v Japan — ITV · 🇯🇵` · `Brazil v Morocco — BBC · 🇯🇵 BS` |

`https://yadot.sniarti.fi/worldcup2026/<feed>` — or `webcal://…/<feed>` to
open Apple Calendar directly.

**Subscribe:** iPhone/Mac → open the `webcal://` link → Add. Google Calendar → Other
calendars ▸ **+** ▸ *From URL* → paste the HTTPS URL. Outlook → Subscribe from web.

Kickoffs are stored in **UTC**, so every client shows them in *your* local time zone.

## Labels

- `BBC` = iPlayer, **live in 4K UHD** · `ITV` = ITVX, **HD only** (STV in Scotland) — the channel name alone tells you 4K vs HD, so titles aren't tagged.
- 🇯🇵 `NHK` (NHK総合), `NTV` (日本テレビ), `Fuji` (フジテレビ) = terrestrial free-to-air · `BS4K` = NHK BS Premium 4K only.
- **No Japanese channel** = DAZN-only (paid). Only DAZN carries all 104 live. In the hybrid feed: 🇯🇵 = free-to-air, `🇯🇵 BS` = BS4K only, nothing = DAZN.
- **Knockouts**: the final is on **BBC + ITV**; England's & Scotland's games auto-label **BBC** (R32/R16/SF) / **ITV** (QF) once their opponent resolves (published home-nation routing). Neutral ties show bracket slots (`1A v 3C/E/F/H/I`, `W74 v W77`) until confirmed.

## How it's built

```
data/cup.txt, cup_finals.txt, cup_stadiums.csv   # fixtures/venues (vendored from openfootball)
data/broadcasters.json                            # UK + JP broadcaster overlay, keyed by team pair
generate.py                                        # parses the above → the .ics feeds below
docs/uk.ics, japan.ics, hybrid.ics                 # the three published calendars
docs/index.html                                    # landing page
```

Regenerate after editing data:

```sh
python3 generate.py          # validates counts, rewrites docs/*.ics
```

The script asserts 72 group + 32 knockout events, that every group match has a UK
channel, and that every venue resolves — it exits non-zero if anything is off.

## Staying current

`.github/workflows/update.yml` runs every 6 hours: re-pull openfootball, regenerate,
and commit **only if something changed** (output is deterministic). So knockout team
slots resolve to real teams and scores appear **automatically** — subscribers just refresh.

**Knockout broadcasters**: the final (both channels) and England's/Scotland's games
(BBC for R32/R16/SF, ITV for QF) are applied automatically by rule in `generate.py` as
teams resolve. Neutral-match picks are the only manual bit — add them to
`data/broadcasters.json` under `knockouts`, keyed by match number (R32 73–88, R16 89–96,
QF 97–100, SF 101–102, third place 103, final 104); an entry also overrides the rule:

```json
"knockouts": { "104": { "uk": "BBC", "jp": "NHK" } }
```

The next scheduled run (or a local `python3 generate.py`) picks it up.

## Data sources & caveats

- Fixtures, kickoff times, venues, bracket: [openfootball/world-cup](https://github.com/openfootball/world-cup) (public domain).
- UK BBC/ITV split: [Sports Mole](https://www.sportsmole.co.uk/football/england/world-cup/feature/world-cup-tv-schedule-where-to-watch-every-game-in-the-uk_596524.html).
- Japan free-to-air: [ABEMA TIMES](https://times.abema.tv/articles/-/10243707).

Broadcaster assignments (especially knockouts and late schedule changes) can move.
Verify against the broadcaster before kickoff. PRs to `data/broadcasters.json` welcome.
