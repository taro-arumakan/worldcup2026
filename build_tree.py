#!/usr/bin/env python3
"""(Re)build the トーナメント表 tab as a narrow, mobile-friendlier mirrored bracket.

Each team box is a flag with its country name stacked directly BELOW it, so every
round is ONE column instead of two. Flags are centred; left-half names hug the
left, right-half names hug the right (mirror-symmetric); the Champion box is
centred. A compact A-L group legend (from the Results rosters) sits below.

It stays a pure presentation layer over the Bracket tab — every cell is a formula,
so it auto-advances as winners are marked.

Run via the build-tree workflow (needs GOOGLE_SHEETS_SA_KEY). Tweak SIZES at the
top and re-run. Clears A1:AD60 first; leaves the flag map (AE:AF) and writes a
short-name map under it.
"""
import json
import os
from pathlib import Path

SHEET_ID = os.environ.get("BRACKET_SHEET_ID", "191IR0O6kja_mULoNnneVS7Tj1FKbwk31BtcIThMOJlc")
TREE = "トーナメント表"
TREE_GID = int(os.environ.get("TREE_GID", "1141681331"))
FLAGMAP = "$AE$2:$AF$49"     # existing JA -> ISO2 map already on the tab
SHORTMAP = "$AE$52:$AF$70"   # long-JA -> short-JA, written by this script

BOX_W, CONN_W, FONT = 58, 8, 8         # column widths (px) and font size (pt)

# round column per depth. A=L-R32 C=L-R16 E=L-QF G=L-SF I=L-final  J=champion
# K=R-final M=R-SF O=R-QF Q=R-R16 S=R-R32. B,D,F,H,L,N,P,R = connectors.
BOX_COLS = list("ACEGIJKMOQS")
CONN_COLS = list("BDFHLNPR")
LEFT_NAME_COLS, RIGHT_NAME_COLS = set("ACEGI"), set("KMOQS")   # name alignment by half

_SHORT = {
    "ボスニア・ヘルツェゴビナ": "ボスニア", "コンゴ民主共和国": "コンゴ",
    "ニュージーランド": "NZ", "コートジボワール": "コートジ", "サウジアラビア": "サウジ",
}

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
    return [(col[rnd], r, cell, None)
            for rnd in rounds for r, cell in zip(ADV_ROWS[rnd], winner_cells[rnd])]


def boxes():
    left = advancers(
        {"R16": "C", "QF": "E", "SF": "G", "F": "I"},
        {"R16": [f"D{n}" for n in range(5, 13)], "QF": [f"D{n}" for n in range(24, 28)],
         "SF": ["D35", "D36"], "F": ["D42"]}, ["R16", "QF", "SF", "F"])
    right = advancers(
        {"R16": "Q", "QF": "O", "SF": "M", "F": "K"},
        {"R16": [f"D{n}" for n in range(13, 21)], "QF": [f"D{n}" for n in range(28, 32)],
         "SF": ["D37", "D38"], "F": ["D43"]}, ["R16", "QF", "SF", "F"])
    return LEFT_R32 + RIGHT_R32 + left + right + [("J", 16, "D47", None)]


def flag(src):
    return f'=IFERROR(IMAGE("https://flagcdn.com/h20/"&VLOOKUP({src},{FLAGMAP},2,FALSE)&".png"),"")'


def label(src, seed):
    placeholder = f'"{seed}"' if seed else '""'
    return f'=IF({src}="",{placeholder},IFERROR(VLOOKUP({src},{SHORTMAP},2,FALSE),{src}))'


def legend_cells():
    """Compact A-L group rosters from Results, stacked flag-over-name, 6 per band."""
    out, cols = {}, ["A", "C", "E", "G", "I", "K"]
    for idx in range(12):
        col, top = cols[idx % 6], 36 + (idx // 6) * 10
        out[f"{col}{top}"] = f'="{chr(65 + idx)}組"'
        for t in range(4):
            rr, fr = 3 + 4 * idx + t, top + 1 + t * 2
            out[f"{col}{fr}"] = flag(f"Results!A{rr}")
            out[f"{col}{fr + 1}"] = f'=IFERROR(VLOOKUP(Results!A{rr},{SHORTMAP},2,FALSE),Results!A{rr})'
    return out


def cell_formulas():
    out = {}
    for col, row, src, seed in boxes():
        b = f"Bracket!{src}"
        out[f"{col}{row}"], out[f"{col}{row + 1}"] = flag(b), label(b, seed)
    out["J14"] = '="CHAMPION 優勝"'
    out.update(legend_cells())
    for i, (lng, short) in enumerate(_SHORT.items()):
        out[f"AE{52 + i}"], out[f"AF{52 + i}"] = f'="{lng}"', f'="{short}"'
    return out


def col_idx(letter):
    return ord(letter) - 65


def _cell_align(col, row, align):
    return {"repeatCell": {
        "range": {"sheetId": TREE_GID, "startRowIndex": row - 1, "endRowIndex": row,
                  "startColumnIndex": col_idx(col), "endColumnIndex": col_idx(col) + 1},
        "cell": {"userEnteredFormat": {"horizontalAlignment": align}},
        "fields": "userEnteredFormat.horizontalAlignment"}}


def format_requests():
    reqs = []
    widths = {c: BOX_W for c in BOX_COLS}
    widths.update({c: CONN_W for c in CONN_COLS})
    for c, w in widths.items():
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": TREE_GID, "dimension": "COLUMNS",
                      "startIndex": col_idx(c), "endIndex": col_idx(c) + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    # base: small, centred, vertically middle across bracket + legend
    reqs.append({"repeatCell": {
        "range": {"sheetId": TREE_GID, "startRowIndex": 0, "endRowIndex": 55,
                  "startColumnIndex": 0, "endColumnIndex": col_idx("S") + 1},
        "cell": {"userEnteredFormat": {
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "textFormat": {"fontSize": FONT}}},
        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat.fontSize)"}})
    # names hug the outer edge of their half (flags + Champion stay centred)
    for col, flag_row, _src, _seed in boxes():
        if col in LEFT_NAME_COLS:
            reqs.append(_cell_align(col, flag_row + 1, "LEFT"))
        elif col in RIGHT_NAME_COLS:
            reqs.append(_cell_align(col, flag_row + 1, "RIGHT"))
    return reqs


def main():
    key = os.environ.get("GOOGLE_SHEETS_SA_KEY")
    cells = cell_formulas()
    if not key:
        print(f"GOOGLE_SHEETS_SA_KEY not set — would write {len(cells)} cells.")
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
    print(f"Rebuilt {TREE}: {len(cells)} cells, boxes @ {BOX_W}px, font {FONT}, legend A-L.")


if __name__ == "__main__":
    main()
