# Auto-sync the bracket → WorldCup2026_Pool sheet

The `Update calendars` workflow can also push **resolved Round-of-32 teams**
into the [WorldCup2026_Pool] Google Sheet's `Bracket` tab (which the visual
`トーナメント表` tree and the leaderboard read from). It runs every 6 hours and on
manual dispatch — so the pool keeps itself current, and you can kick a refresh
from the **GitHub mobile app → Actions → Update calendars → Run workflow**.

It writes only what openfootball has resolved and only cells that changed; it
never blanks a slot, so manual entries are safe until the source catches up. It
handles R32 **teams** only (marking winners is a later addition).

The sync step is skipped automatically until the secret below exists, so nothing
breaks before setup.

## One-time setup (≈10 min) — do this yourself; the key is a secret I never see

1. **Google Cloud → Sheets API.** At <https://console.cloud.google.com> pick (or
   create) a project, then **APIs & Services → Library → Google Sheets API →
   Enable**.

2. **Service account + key.** APIs & Services → **Credentials → Create
   credentials → Service account** (any name, e.g. `bracket-sync`). Open it →
   **Keys → Add key → Create new key → JSON**. A `.json` file downloads — this is
   the credential. Note the account's email: `…@….iam.gserviceaccount.com`.

3. **Share the sheet with it.** Open the WorldCup2026_Pool sheet → **Share** →
   paste the service-account email → role **Editor** → Send. (Same as adding any
   collaborator; the script edits the sheet as this account.)

4. **Add the GitHub secret.** Repo → **Settings → Secrets and variables →
   Actions → New repository secret**. Name `GOOGLE_SHEETS_SA_KEY`, value = the
   **entire contents** of the downloaded JSON file. Save.

5. **Run it.** Actions → **Update calendars → Run workflow** (or wait for the
   next 6-hourly run). Watch the *Sync Round-of-32 teams* step log; it prints
   each cell it changes.

Keep the JSON key private — don't commit it (`.gitignore` already blocks the
common filenames). To rotate, make a new key and update the secret.

## Local test

No key needed for a preview against the live source:

```sh
curl -fsSL https://raw.githubusercontent.com/openfootball/world-cup/master/2026--usa/cup_finals.txt -o /tmp/cf.txt
CUP_FINALS=/tmp/cf.txt python3 sync_bracket.py      # lists every slot it would set
```

With the key exported, `DRY_RUN=1 python3 sync_bracket.py` shows the exact diff
without writing.

[WorldCup2026_Pool]: https://docs.google.com/spreadsheets/d/191IR0O6kja_mULoNnneVS7Tj1FKbwk31BtcIThMOJlc/edit
