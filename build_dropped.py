#!/usr/bin/env python3
"""Build the "Dropped" tab: picks that can no longer score, and who made them.

A nomination is dead once its team can win no further knockout matches — i.e. the
team either failed to qualify for the Round of 32 (out in the group stage) or lost
a knockout tie. This lists every such pick: when the team went out, the team, the
player who picked it, and the rank they placed it at (so rank 1 = 10 pts/win now
forfeited … rank 10 = 1).

Reads the live sheet (Players picks, the Bracket, the Results roster) via the
Google Sheets API and rewrites the Dropped tab. Runs in the 6-hourly workflow
right after the bracket sync, so it keeps pace as the knockouts progress.

Note: semi-final losers are NOT counted as dropped — they still play the
third-place match (a win there scores). They appear once that match resolves.
"""
import json
import os
from pathlib import Path

SHEET_ID = os.environ.get("BRACKET_SHEET_ID", "191IR0O6kja_mULoNnneVS7Tj1FKbwk31BtcIThMOJlc")
TAB = "Dropped"
TREE = "トーナメント表"        # its AE2:AF49 is the JA -> ISO2 flag map we reuse for flags

# Knockout matches whose loser is eliminated, by Bracket row -> round label.
# Semi-finals (rows 42-43) are excluded — their losers go to the 3rd-place match.
KO_MATCHES = ([(r, "R32") for r in range(5, 21)] + [(r, "R16") for r in range(24, 32)]
              + [(r, "QF") for r in range(35, 39)] + [(47, "Final"), (51, "3rd place")])
ROUND_ORDER = {"Group stage": 0, "R32": 1, "R16": 2, "QF": 3, "3rd place": 4, "Final": 5}


def at(grid, idx, col):
    """Safe cell read from a list-of-rows grid."""
    return (grid[idx][col].strip() if 0 <= idx < len(grid) and col < len(grid[idx])
            and grid[idx][col] is not None else "")


def parse_players(vals):
    """[(player, rank, team)] from Players!A3:C… — blocks of 14 rows; name in A at
    the block top, then 10 picks two rows down with Rank in A and Team in C."""
    picks = []
    for p in range(20):
        base = 14 * p                      # row 3 -> index 0
        name = at(vals, base, 0)
        if not name:
            continue
        for i in range(10):
            team = at(vals, base + 2 + i, 2)
            rank = at(vals, base + 2 + i, 0)
            if team and rank.isdigit():
                picks.append((name, int(rank), team))
    return picks


def dropped_teams(bracket, all_teams):
    """{team: round-out} for every eliminated team."""
    r32 = {t for r in range(5, 21) for t in (at(bracket, r - 5, 0), at(bracket, r - 5, 1)) if t}
    out = {t: "Group stage" for t in all_teams if t and t not in r32}
    for r, label in KO_MATCHES:
        a, b, w = at(bracket, r - 5, 0), at(bracket, r - 5, 1), at(bracket, r - 5, 2)
        if w and a and b:
            loser = b if w == a else a if w == b else None
            if loser:
                out[loser] = label
    return out


def build_rows(picks, dropped):
    rows = [[dropped[t], t, player, rank, 11 - rank] for player, rank, t in picks if t in dropped]
    rows.sort(key=lambda x: (ROUND_ORDER.get(x[0], 9), x[1], x[3]))
    return rows


def flag_formula(team_a1):
    return (f'=IFERROR(IMAGE("https://flagcdn.com/h20/"&'
            f"VLOOKUP({team_a1},'{TREE}'!$AE$2:$AF$49,2,FALSE)&\".png\"),\"\")")


def main():
    key = os.environ.get("GOOGLE_SHEETS_SA_KEY")
    if not key:
        print("GOOGLE_SHEETS_SA_KEY not set — nothing to do.")
        return

    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    info = json.loads(key) if key.lstrip().startswith("{") else json.loads(Path(key).read_text())
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    api = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

    got = api.values().batchGet(spreadsheetId=SHEET_ID, ranges=[
        "Players!A3:C300", "Bracket!B5:D51", "Results!A3:A50"]).execute()["valueRanges"]
    players, bracket, results = (g.get("values", []) for g in got)

    all_teams = [r[0].strip() for r in results if r and r[0].strip()]
    picks, dropped = parse_players(players), dropped_teams(bracket, all_teams)
    rows = build_rows(picks, dropped)
    print(f"parsed {len(picks)} picks from {len({p for p, _, _ in picks})} players; "
          f"{len(dropped)} teams out; {len(rows)} dead nomination(s) "
          f"across {len({r[1] for r in rows})} picked team(s).")

    # ensure the tab exists; get its sheetId
    meta = api.get(spreadsheetId=SHEET_ID, fields="sheets.properties").execute()["sheets"]
    sheet_id = next((s["properties"]["sheetId"] for s in meta
                     if s["properties"]["title"] == TAB), None)
    if sheet_id is None:
        sheet_id = api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [
            {"addSheet": {"properties": {"title": TAB}}}]}).execute(
        )["replies"][0]["addSheet"]["properties"]["sheetId"]

    header = ["Out", "", "Team", "Player", "Rank", "Pts/win"]
    body = [["脱落ノミネート / Dropped nominations — picks that can no longer score"], [], header]
    formula_cells = []
    for i, (out, team, player, rank, ptw) in enumerate(rows):
        body.append([out, "", team, player, rank, ptw])
        formula_cells.append((f"{TAB}!B{len(body)}", flag_formula(f'"{team}"')))

    api.values().clear(spreadsheetId=SHEET_ID, range=f"{TAB}!A1:F400").execute()
    api.values().update(spreadsheetId=SHEET_ID, range=f"{TAB}!A1", valueInputOption="RAW",
                        body={"values": body}).execute()
    if formula_cells:
        api.values().batchUpdate(spreadsheetId=SHEET_ID, body={
            "valueInputOption": "USER_ENTERED",
            "data": [{"range": c, "values": [[f]]} for c, f in formula_cells]}).execute()

    api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3,
                                  "startColumnIndex": 0, "endColumnIndex": 6},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat.bold"}},
        {"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                                                  "gridProperties": {"frozenRowCount": 3}},
                                   "fields": "gridProperties.frozenRowCount"}},
    ] + [{"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize"}}
         for c, w in enumerate((78, 30, 96, 132, 46, 60))]}).execute()
    print(f"Wrote {len(rows)} rows to the {TAB} tab.")


if __name__ == "__main__":
    main()
