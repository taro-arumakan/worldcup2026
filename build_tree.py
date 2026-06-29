#!/usr/bin/env python3
"""(Re)build the トーナメント表 tab as a narrow, mobile-friendlier mirrored bracket.

Each team box is a flag with its country name stacked directly BELOW it, so every
round is ONE column instead of two (flag + name side by side). Small font + narrow
columns shrink the overall width. It stays a pure presentation layer over the
Bracket tab — every cell is a formula, so it auto-advances as winners are marked.

The bracket row-positions reuse the proven single-advancer doubling layout (flags
at the same rows as before; the name simply moves to the row under its flag).

Run via the build-tree workflow (needs GOOGLE_SHEETS_SA_KEY). One-off / on demand.
Tweak SIZES at the top and re-run to adjust spacing. Leaves the flag map (AE:AF)
and writes a short-name map (AH:AI); clears A1:AD60 first (group legend is re-added
separately).
"""
import json
import os
from pathlib import Path

SHEET_ID = os.environ.get("BRACKET_SHEET_ID", "191IR0O6kja_mULoNnneVS7Tj1FKbwk31BtcIThMOJlc")
TREE = "トーナメント表"
TREE_GID = int(os.environ.get("TREE_GID", "1141681331"))
FLAGMAP = "$AE$2:$AF$49"   # existing JA -> ISO2 map already on the tab
SHORTMAP = "$AE$52:$AF$70"  # long-JA -> short-JA, written by this script (spare rows under the flag map)

BOX_W, CONN_W, FONT = 52, 10, 8        # column widths (px) and font size (pt)

# round column (letter) per depth. A=L-R32 C=L-R16 E=L-QF G=L-SF I=L-final
# J=champion  K=R-final M=R-SF O=R-QF Q=R-R16 S=R-R32. B,D,F,H,L,N,P,R = connectors.
BOX_COLS = list("ACEGIJKMOQS")
CONN_COLS = list("BDFHLNPR")

# Long Japanese names -> shorter labels so they fit a narrow column.
_SHORT = {
    "ボスニア・ヘルツェゴビナ": "ボスニア", "コンゴ民主共和国": "コンゴ",
    "ニュージーランド": "NZ", "コートジボワール": "コートジ", "サウジアラビア": "サウジ",
}

# Each box: (column, flag_row, Bracket-source-cell, seed-code-or-None).
# Name goes in flag_row+1. R32 boxes carry a seed code shown until the team resolves.
LEFT_R32 = [
    ("A", 1, "B5", "1E"), ("A", 3, "C5", "3ABCDF"), ("A", 5, "B6", "1I"), ("A", 7, "C6", "3CDFGH"),
    ("A", 9, "B7", "2A"), ("A", 11, "C7", "2B"), ("A", 13, "B8", "1F"), ("A", 15, "C8", "2C"),
    ("A", 17, "B9", "2K"), ("A", 19, "C9", "2L"), ("A", 21, "B10", "1H"), ("A", 23, "C10", "2J"),
    ("A", 25, "B11", "1D"), ("A", 27, "C11", "3BEFIJ"), ("A", 29, "B12", "1G"), ("A", 31, "C12", "3AEHIJ"),
]
RIGHT_R32 = [
    ("S", 1, "B13", "1C"), ("S", 3, "C13", "2F"), ("S", 5, "B14", "2E"), ("S", 7, "C14", "2I"),
    ("S", 9, "B15", "1A"), ("S", 11, "C15", "3CEFHI"), ("S", 13, "B16", "1L"), ("S", 15, "C16", "3EHIJK"),
    ("S", 17, "B17", "1J"), ("S", 19, "C17", "2H"), ("S", 21, "B18", "2D"), ("S", 23, "C18", "2G"),
    ("S", 25, "B19", "1B"), ("S", 27, "C19", "3EFGIJ"), ("S", 29, "B20", "1K"), ("S", 31, "C20", "3DEIJL"),
]
ADV_ROWS = {"R16": [2, 6, 10, 14, 18, 22, 26, 30], "QF": [4, 12, 20, 28], "SF": [8, 24], "F": [16]}


def advancers(col, winner_cells, rounds):
    out = []
    for rnd in rounds:
        for r, cell in zip(ADV_ROWS[rnd], winner_cells[rnd]):
            out.append((col[rnd], r, cell, None))
    return out


def boxes():
    left_adv = advancers(
        {"R16": "C", "QF": "E", "SF": "G", "F": "I"},
        {"R16": [f"D{n}" for n in range(5, 13)], "QF": [f"D{n}" for n in range(24, 28)],
         "SF": ["D35", "D36"], "F": ["D42"]}, ["R16", "QF", "SF", "F"])
    right_adv = advancers(
        {"R16": "Q", "QF": "O", "SF": "M", "F": "K"},
        {"R16": [f"D{n}" for n in range(13, 21)], "QF": [f"D{n}" for n in range(28, 32)],
         "SF": ["D37", "D38"], "F": ["D43"]}, ["R16", "QF", "SF", "F"])
    champion = [("J", 16, "D47", None)]
    return LEFT_R32 + RIGHT_R32 + left_adv + right_adv + champion


def cell_formulas():
    """{A1_cell: formula} for every flag + name cell, plus the short-name map."""
    out = {}
    for col, row, src, seed in boxes():
        b = f"Bracket!{src}"
        out[f"{col}{row}"] = (
            f'=IFERROR(IMAGE("https://flagcdn.com/h20/"&VLOOKUP({b},{FLAGMAP},2,FALSE)&".png"),"")')
        placeholder = f'"{seed}"' if seed else '""'
        out[f"{col}{row + 1}"] = (
            f'=IF({b}="",{placeholder},IFERROR(VLOOKUP({b},{SHORTMAP},2,FALSE),{b}))')
    out["J14"] = '="CHAMPION 優勝"'
    for i, (long, short) in enumerate(_SHORT.items()):
        out[f"AE{52 + i}"], out[f"AF{52 + i}"] = f'="{long}"', f'="{short}"'
    return out


def col_idx(letter):
    return ord(letter) - 65


def format_requests():
    reqs = []
    width = {c: BOX_W for c in BOX_COLS}
    width.update({c: CONN_W for c in CONN_COLS})
    for c, w in width.items():
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": TREE_GID, "dimension": "COLUMNS",
                      "startIndex": col_idx(c), "endIndex": col_idx(c) + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    # small, centred text across the bracket block
    reqs.append({"repeatCell": {
        "range": {"sheetId": TREE_GID, "startRowIndex": 0, "endRowIndex": 33,
                  "startColumnIndex": 0, "endColumnIndex": col_idx("S") + 1},
        "cell": {"userEnteredFormat": {
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "textFormat": {"fontSize": FONT}}},
        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat.fontSize)"}})
    return reqs


def main():
    key = os.environ.get("GOOGLE_SHEETS_SA_KEY")
    cells = cell_formulas()
    if not key:
        print(f"GOOGLE_SHEETS_SA_KEY not set — would write {len(cells)} cells. Sample:")
        for c in ("A1", "A2", "C2", "C3", "J14", "S1", "S2"):
            print(f"  {c}: {cells[c]}")
        return

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = json.loads(key) if key.lstrip().startswith("{") else json.loads(Path(key).read_text())
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    api = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

    api.values().clear(spreadsheetId=SHEET_ID, range=f"{TREE}!A1:AD60").execute()
    api.values().batchUpdate(spreadsheetId=SHEET_ID, body={
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": f"{TREE}!{c}", "values": [[f]]} for c, f in cells.items()],
    }).execute()
    api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": format_requests()}).execute()
    print(f"Rebuilt {TREE}: {len(cells)} cells, {len(BOX_COLS)} box columns @ {BOX_W}px, font {FONT}.")


if __name__ == "__main__":
    main()
