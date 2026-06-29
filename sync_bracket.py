#!/usr/bin/env python3
"""Push the resolved knockout bracket from openfootball into the WorldCup2026_Pool
Google Sheet, so the live forecast pool (and its visual トーナメント表 tree, which
reads the same cells) stay current automatically.

Each run reads data/cup_finals.txt (refreshed by the Update workflow just before
this step) and writes, via the Google Sheets API, only the cells that changed:

  * Round-of-32 entrants  -> Team A / Team B (cols B/C of rows 5-20)
  * Winners of any played knockout match (R32 → Final, incl. 3rd-place)
                          -> the gold Winner cell (col D); the sheet auto-advances
                             later-round Team A/B from those, so we never write
                             the formula cells.

Auth: a Google service account. Put its JSON key in env GOOGLE_SHEETS_SA_KEY
(the JSON itself, or a path to a file). Share the sheet with the service
account's email as Editor. See SHEET_SYNC.md for the one-time setup.

Behaviour notes:
  * Only writes what openfootball has resolved — never blanks a cell — so manual
    "ahead of the source" entries are safe until the source catches up.
  * Winners cover extra-time and penalty-shootout results (a full-time draw is
    decided by the 'a-b pen.' score).
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

# FIFA match number -> Bracket row whose Winner cell (col D) it fills. R32 reuses
# the rows above; R16/QF/SF/3rd/Final follow the same tree order down the sheet.
WINNER_ROW = {
    **MATCH_TO_ROW,                                                   # R32 -> D5..D20
    89: 24, 90: 25, 93: 26, 94: 27, 91: 28, 92: 29, 95: 30, 96: 31,   # R16 -> D24..D31
    97: 35, 98: 36, 99: 37, 100: 38,                                  # QF  -> D35..D38
    101: 42, 102: 43,                                                 # SF  -> D42, D43
    103: 51,                                                          # 3rd -> D51
    104: 47,                                                          # Final -> D47
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

# "(73) 12:00 UTC-7  South Africa 0-1 (0-0) Canada   @ Los Angeles ..." -> (num, matchup)
LINE_RE = re.compile(r"^\s*\((\d+)\)\s+\d{1,2}:\d{2}\s+UTC[+-]\d+\s+(.+?)\s+@\s+")
PEN_RE = re.compile(r"(\d+)\s*-\s*(\d+)\s+pen", re.I)


def decide_winner(matchup):
    """Winner team of a played knockout matchup, or None if not yet decided.
    Higher full-time score wins; a draw is settled by the 'a-b pen.' shootout."""
    home, away, score = generate.split_matchup(matchup)
    if not score:
        return None                       # still 'A v B' — not played
    h, a = (int(x) for x in score.split("-"))
    if h != a:
        return home if h > a else away
    pen = PEN_RE.search(matchup)
    if pen:
        return home if int(pen.group(1)) > int(pen.group(2)) else away
    return None                           # draw with no recorded shootout — skip


def desired_cells():
    """{cell: japanese_name} for every Bracket cell openfootball has resolved:
    R32 entrants (B/C) plus the Winner (D) of any played knockout match."""
    src = Path(os.environ["CUP_FINALS"]) if os.environ.get("CUP_FINALS") \
        else generate.DATA / "cup_finals.txt"
    want = {}
    for raw in src.read_text(encoding="utf-8").splitlines():
        mo = LINE_RE.match(raw)
        if not mo:
            continue
        num, matchup = int(mo.group(1)), mo.group(2)
        if num in MATCH_TO_ROW:                       # R32 entrants -> Team A/B
            row = MATCH_TO_ROW[num]
            home, away, _ = generate.split_matchup(matchup)
            for participant, col in ((home, "B"), (away, "C")):
                ja = EN_TO_JA.get(generate.norm(participant))
                if ja:
                    want[f"{col}{row}"] = ja
        if num in WINNER_ROW:                         # winner -> Winner cell (col D)
            won = decide_winner(matchup)
            ja = EN_TO_JA.get(generate.norm(won)) if won else None
            if ja:
                want[f"D{WINNER_ROW[num]}"] = ja
    return want


def load_credentials(raw):
    from google.oauth2 import service_account
    info = json.loads(raw) if raw.lstrip().startswith("{") else json.loads(Path(raw).read_text())
    return service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])


def main():
    want = desired_cells()
    teams = sum(1 for c in want if c[0] != "D")
    wins = sum(1 for c in want if c[0] == "D")
    print(f"openfootball resolved: {teams} R32 entrant slot(s), {wins} winner(s).")

    key = os.environ.get("GOOGLE_SHEETS_SA_KEY")
    if not key:
        print("GOOGLE_SHEETS_SA_KEY not set — preview only, nothing written:")
        for cell, ja in sorted(want.items()):
            print(f"  {TAB}!{cell} = {ja}")
        return

    from googleapiclient.discovery import build
    values = build("sheets", "v4", credentials=load_credentials(key),
                   cache_discovery=False).spreadsheets().values()

    cur = values.get(spreadsheetId=SHEET_ID, range=f"{TAB}!B5:D51").execute().get("values", [])

    def current(cell):  # current sheet value for e.g. "D24"
        line = cur[int(cell[1:]) - 5] if int(cell[1:]) - 5 < len(cur) else []
        i = {"B": 0, "C": 1, "D": 2}[cell[0]]
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
