#!/usr/bin/env python3
"""Push resolved Round-of-32 teams from the openfootball bracket into the
WorldCup2026_Pool Google Sheet, so the live forecast pool (and its visual
トーナメント表 tree, which reads the same cells) stay current automatically.

Each run reads data/cup_finals.txt (refreshed by the Update workflow just before
this step), finds the R32 matches whose participants openfootball has resolved to
real team names, maps each to its Bracket cell + Japanese name, and writes only
the cells that actually changed via the Google Sheets API.

Auth: a Google service account. Put its JSON key in env GOOGLE_SHEETS_SA_KEY
(the JSON itself, or a path to a file). Share the sheet with the service
account's email as Editor. See SHEET_SYNC.md for the one-time setup.

Behaviour notes:
  * Only writes slots openfootball has resolved — never blanks a cell — so any
    manual "ahead of the source" entries are safe until the source catches up.
  * R32 team slots only. Marking match winners (the gold cells that drive
    scoring) is a later addition; this just keeps the 32 entrants current.
  * DRY_RUN=1 prints the diff without writing. With no key set it lists what it
    would write and exits 0, so the workflow step is safe before the secret
    exists.
"""
import json
import os
import re
from pathlib import Path

import generate  # reuse norm(), split_matchup() and the data path

SHEET_ID = os.environ.get("BRACKET_SHEET_ID", "191IR0O6kja_mULoNnneVS7Tj1FKbwk31BtcIThMOJlc")
TAB = "Bracket"

# FIFA R32 match number (73-88) -> Bracket row. R32-1..16 live in rows 5-20,
# ordered so the sheet's auto-advance (R16-k <- winners of R32-(2k-1) & 2k)
# follows the official tree. home (left of "v") -> Team A (col B); away -> col C.
MATCH_TO_ROW = {
    74: 5, 77: 6, 73: 7, 75: 8, 83: 9, 84: 10, 81: 11, 82: 12,
    76: 13, 78: 14, 79: 15, 80: 16, 86: 17, 88: 18, 85: 19, 87: 20,
}

# English (as openfootball writes it) -> Japanese, keyed through generate.norm()
# so variants (USA/United States, Cote d'Ivoire/Ivory Coast, Czechia, ...) match.
_EN_JA = {
    "Mexico": "メキシコ", "South Africa": "南アフリカ", "South Korea": "韓国", "Czechia": "チェコ",
    "Canada": "カナダ", "Bosnia and Herzegovina": "ボスニア・ヘルツェゴビナ", "Qatar": "カタール", "Switzerland": "スイス",
    "Brazil": "ブラジル", "Morocco": "モロッコ", "Haiti": "ハイチ", "Scotland": "スコットランド",
    "United States": "アメリカ", "Paraguay": "パラグアイ", "Australia": "オーストラリア", "Turkey": "トルコ",
    "Germany": "ドイツ", "Curacao": "キュラソー", "Ivory Coast": "コートジボワール", "Ecuador": "エクアドル",
    "Netherlands": "オランダ", "Japan": "日本", "Sweden": "スウェーデン", "Tunisia": "チュニジア",
    "Belgium": "ベルギー", "Egypt": "エジプト", "Iran": "イラン", "New Zealand": "ニュージーランド",
    "Spain": "スペイン", "Cape Verde": "カーボベルデ", "Saudi Arabia": "サウジアラビア", "Uruguay": "ウルグアイ",
    "France": "フランス", "Senegal": "セネガル", "Iraq": "イラク", "Norway": "ノルウェー",
    "Argentina": "アルゼンチン", "Algeria": "アルジェリア", "Austria": "オーストリア", "Jordan": "ヨルダン",
    "Portugal": "ポルトガル", "DR Congo": "コンゴ民主共和国", "Uzbekistan": "ウズベキスタン", "Colombia": "コロンビア",
    "England": "イングランド", "Croatia": "クロアチア", "Ghana": "ガーナ", "Panama": "パナマ",
}
EN_TO_JA = {generate.norm(k): v for k, v in _EN_JA.items()}

# "(73) 12:00 UTC-7  South Africa v Canada   @ Los Angeles ..."  ->  (num, matchup)
LINE_RE = re.compile(r"^\s*\((\d+)\)\s+\d{1,2}:\d{2}\s+UTC[+-]\d+\s+(.+?)\s+@\s+")


def resolved_r32():
    """{cell: japanese_name} for every R32 slot openfootball has resolved to a
    real team. Placeholders (1F, 2C, 3A/B/C/D/F, ...) normalise to non-teams and
    are skipped; split_matchup() copes with both 'A v B' and played 'A 1-0 B'."""
    src = Path(os.environ["CUP_FINALS"]) if os.environ.get("CUP_FINALS") \
        else generate.DATA / "cup_finals.txt"
    want = {}
    for raw in src.read_text(encoding="utf-8").splitlines():
        mo = LINE_RE.match(raw)
        if not mo:
            continue
        row = MATCH_TO_ROW.get(int(mo.group(1)))
        if not row:
            continue
        home, away, _ = generate.split_matchup(mo.group(2))
        for participant, col in ((home, "B"), (away, "C")):
            ja = EN_TO_JA.get(generate.norm(participant))
            if ja:
                want[f"{col}{row}"] = ja
    return want


def load_credentials(raw):
    from google.oauth2 import service_account
    info = json.loads(raw) if raw.lstrip().startswith("{") else json.loads(Path(raw).read_text())
    return service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])


def main():
    want = resolved_r32()
    print(f"openfootball has resolved {len(want)} of 32 R32 team slot(s).")

    key = os.environ.get("GOOGLE_SHEETS_SA_KEY")
    if not key:
        print("GOOGLE_SHEETS_SA_KEY not set — preview only, nothing written:")
        for cell, ja in sorted(want.items()):
            print(f"  {TAB}!{cell} = {ja}")
        return

    from googleapiclient.discovery import build
    values = build("sheets", "v4", credentials=load_credentials(key),
                   cache_discovery=False).spreadsheets().values()

    cur = values.get(spreadsheetId=SHEET_ID, range=f"{TAB}!B5:C20").execute().get("values", [])

    def current(cell):  # current sheet value for e.g. "B7"
        row = int(cell[1:]) - 5
        line = cur[row] if row < len(cur) else []
        i = 0 if cell[0] == "B" else 1
        return line[i] if i < len(line) else ""

    changes = {c: v for c, v in want.items() if current(c) != v}
    if not changes:
        print("Bracket already current — no writes.")
        return
    for cell, ja in sorted(changes.items()):
        print(f"  {TAB}!{cell}: {current(cell)!r} -> {ja}")

    if os.environ.get("DRY_RUN") == "1":
        print("DRY_RUN — not writing.")
        return

    values.batchUpdate(spreadsheetId=SHEET_ID, body={
        "valueInputOption": "RAW",
        "data": [{"range": f"{TAB}!{c}", "values": [[v]]} for c, v in changes.items()],
    }).execute()
    print(f"Wrote {len(changes)} cell(s) to the {TAB} tab.")


if __name__ == "__main__":
    main()
