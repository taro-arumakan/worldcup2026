#!/usr/bin/env python3
"""Generate docs/worldcup.ics for the 2026 FIFA World Cup.

Fixtures, kickoff times (venue-local + UTC offset), venues and the knockout
bracket come from the vendored openfootball data in data/. Broadcaster labels
(UK BBC/ITV + Japan free-to-air) come from data/broadcasters.json.

Every event is emitted in UTC (…Z), so calendar apps display each kickoff in
the subscriber's own local time zone automatically.
"""
import csv
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "worldcup.ics"

PRODID = "-//taro-arumakan//WorldCup2026 UK+JP TV//EN"
CAL_NAME = "World Cup 2026 — UK & Japan TV"
CAL_DESC = ("FIFA World Cup 2026 fixtures with UK (BBC/ITV) and Japan free-to-air "
            "(NHK/NTV/Fuji) broadcasters. Kickoffs auto-convert to your local time. "
            "Knockout broadcasters TBC.")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})  # also accept Jun/Jul

# Normalise team-name spelling variants to one token for matching.
ALIASES = {
    "korearepublic": "southkorea",
    "czechrepublic": "czech", "czechia": "czech",
    "bosniaherzegovina": "bosnia", "bosniaandherzegovina": "bosnia",
    "cotedivoire": "ivorycoast",
    "congodr": "drcongo",
    "turkiye": "turkey",
    "caboverde": "capeverde",
    "unitedstates": "usa", "us": "usa",
}


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z]", "", s)
    return ALIASES.get(s, s)


def pair_key(a, b):
    return "|".join(sorted([norm(a), norm(b)]))


def split_matchup(m):
    """Return (home, away, score_or_None) from an openfootball matchup string."""
    m = m.strip()
    sc = re.search(r"(\d+)-(\d+)\s*\(\d+-\d+\)", m)
    if sc:
        home, away = re.split(r"\s+\d+-\d+\s*\(\d+-\d+\)\s+", m, maxsplit=1)
        return home.strip(), away.strip(), f"{sc.group(1)}-{sc.group(2)}"
    home, away = re.split(r"\s+v\s+", m, maxsplit=1)
    return home.strip(), away.strip(), None


def parse_groups(text):
    matches, group, date, started = [], None, None, False
    for raw in text.splitlines():
        line = raw.strip()
        mg = re.match(r"^▪\s*Group\s+([A-L])\b", line)
        if mg:
            group, date, started = mg.group(1), None, True
            continue
        if line.startswith("▪"):          # matchday list etc. — skip
            continue
        if not started:
            continue
        md = re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2})$", line)
        if md:
            date = (MONTHS[md.group(2)], int(md.group(3)))
            continue
        mt = re.match(r"^\s+(\d{1,2}):(\d{2})\s+UTC([+-]\d+)\s+(.+?)\s+@\s+(.+?)\s*$", raw)
        if mt and date:
            hh, mm, off, matchup, venue = mt.groups()
            home, away, score = split_matchup(matchup)
            matches.append(dict(stage="group", label="Group " + group, group=group,
                                mon=date[0], day=date[1], hh=int(hh), mm=int(mm),
                                off=int(off), home=home, away=away, score=score,
                                venue=venue.strip()))
    return matches


def parse_finals(text):
    stages = [("Round of 32", "Round of 32"), ("Round of 16", "Round of 16"),
              ("Quarter-final", "Quarter-final"), ("Semi-final", "Semi-final"),
              ("Match for third place", "Third-place play-off"), ("Final", "Final")]
    matches, stage, date = [], None, None
    for raw in text.splitlines():
        line = raw.strip()
        hit = next((s for full, s in stages if line.startswith("▪") and full in line), None)
        if hit:
            stage, date = hit, None
            continue
        md = re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2})$", line)
        if md:
            date = (MONTHS[md.group(2)], int(md.group(3)))
            continue
        mt = re.match(r"^\s*\((\d+)\)\s+(\d{1,2}):(\d{2})\s+UTC([+-]\d+)\s+(.+?)\s+@\s+(.+?)\s*$", raw)
        if mt and date:
            num, hh, mm, off, matchup, venue = mt.groups()
            home, away = re.split(r"\s+v\s+", matchup.strip(), maxsplit=1)
            matches.append(dict(stage="ko", label=stage, num=int(num), mon=date[0],
                                day=date[1], hh=int(hh), mm=int(mm), off=int(off),
                                home=home.strip(), away=away.strip(), score=None,
                                venue=venue.strip()))
    return matches


def load_stadiums():
    keep = [ln for ln in (DATA / "cup_stadiums.csv").read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    out = {}
    for row in csv.reader(io.StringIO("\n".join(keep))):
        if not row or row[0].strip() == "city":
            continue
        out[row[0].strip()] = row[3].strip()
    return out


def load_broadcasters():
    doc = json.loads((DATA / "broadcasters.json").read_text(encoding="utf-8"))
    out = {}
    for e in doc["matches"]:
        a, b = re.split(r"\s+v\s+", e["match"], maxsplit=1)
        out[pair_key(a, b)] = {k: e[k] for k in ("uk", "jp") if e.get(k)}
    return out


def to_utc(m):
    local = datetime(2026, m["mon"], m["day"], m["hh"], m["mm"], tzinfo=timezone.utc)
    return local - timedelta(hours=m["off"])   # off = -7 -> +7h to reach UTC


def esc(t):
    return (t.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """RFC 5545 line folding on UTF-8 byte boundaries (<=75 octets/line)."""
    b = line.encode("utf-8")
    if len(b) <= 73:
        return line
    chunks, i, limit = [], 0, 73
    while i < len(b):
        j = min(i + limit, len(b))
        while j < len(b) and (b[j] & 0xC0) == 0x80:   # don't split a code point
            j -= 1
        chunks.append(b[i:j].decode("utf-8"))
        i, limit = j, 72                              # continuation lines get a leading space
    return "\r\n ".join(chunks)


JP_FULL = {"NHK": "NHK総合", "NTV": "日本テレビ", "Fuji": "フジテレビ",
           "BS4K": "NHK BS Premium 4K"}


def build_event(m, dtstamp):
    dt = to_utc(m)
    dur = timedelta(hours=2) if m["stage"] == "group" else timedelta(hours=2, minutes=30)
    bc = BROAD.get(pair_key(m["home"], m["away"]), {}) if m["stage"] == "group" else {}

    fixture = f'{m["home"]} v {m["away"]}'
    title = fixture if m["stage"] == "group" else f'{m["label"]}: {fixture}'
    tv = []
    if bc.get("uk"):
        tv.append(f'🇬🇧 {bc["uk"]}')
    if bc.get("jp"):
        tv.append(f'🇯🇵 {bc["jp"]}')
    summary = title + (" — " + " · ".join(tv) if tv else "")

    venue = m["venue"]
    location = f'{STADIUMS.get(venue, "")}, {venue}'.lstrip(", ")

    desc = [m["label"], f'Venue: {location}']
    if m["stage"] == "group":
        desc.append(f'UK: {bc.get("uk", "TBC")} (incl. iPlayer / ITVX)')
        if bc.get("jp"):
            desc.append(f'Japan: {JP_FULL.get(bc["jp"], bc["jp"])} (free-to-air) / DAZN')
        else:
            desc.append("Japan: DAZN only (no free-to-air)")
    else:
        desc.append("UK & Japan broadcasters: TBC")
    if m["score"]:
        desc.append(f'Result: {m["home"]} {m["score"]} {m["away"]}')
    desc.append("Kickoff shown in your device's local time zone.")

    if m["stage"] == "group":
        uid = "wc2026-grp-" + pair_key(m["home"], m["away"]).replace("|", "-")
    else:
        uid = f'wc2026-ko-{m["num"]}'

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@worldcup-2026-calendar",
        f"DTSTAMP:{dtstamp}",
        f'DTSTART:{dt.strftime("%Y%m%dT%H%M%SZ")}',
        f'DTEND:{(dt + dur).strftime("%Y%m%dT%H%M%SZ")}',
        f"SUMMARY:{esc(summary)}",
        f"LOCATION:{esc(location)}",
        f"DESCRIPTION:{esc(' · '.join(desc))}",
        "CATEGORIES:World Cup 2026,Football",
        "TRANSP:TRANSPARENT",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]
    return dt, lines


def main():
    global STADIUMS, BROAD
    STADIUMS = load_stadiums()
    BROAD = load_broadcasters()

    matches = parse_groups((DATA / "cup.txt").read_text(encoding="utf-8"))
    matches += parse_finals((DATA / "cup_finals.txt").read_text(encoding="utf-8"))

    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    events = sorted((build_event(m, dtstamp) for m in matches), key=lambda x: x[0])

    out = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(CAL_NAME)}", "X-WR-TIMEZONE:UTC",
        f"X-WR-CALDESC:{esc(CAL_DESC)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
    ]
    for _, lines in events:
        out += lines
    out.append("END:VCALENDAR")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\r\n".join(fold(l) for l in out) + "\r\n", encoding="utf-8")

    # ---- validation summary -------------------------------------------------
    grp = [m for m in matches if m["stage"] == "group"]
    ko = [m for m in matches if m["stage"] == "ko"]
    missing_uk = [f'{m["home"]} v {m["away"]}' for m in grp
                  if not BROAD.get(pair_key(m["home"], m["away"]), {}).get("uk")]
    with_jp = [m for m in grp if BROAD.get(pair_key(m["home"], m["away"]), {}).get("jp")]
    missing_venue = sorted({m["venue"] for m in matches if m["venue"] not in STADIUMS})

    print(f"groups parsed : {len(grp)}  (expected 72)")
    print(f"knockout parsed: {len(ko)}  (expected 32)")
    print(f"total events  : {len(matches)}")
    print(f"group matches missing UK label: {len(missing_uk)} {missing_uk}")
    print(f"group matches with JP FTA label: {len(with_jp)} (expected 32)")
    print(f"venues not found in stadium map: {missing_venue or 'none'}")
    print(f"written: {OUT}  ({OUT.stat().st_size} bytes)")
    if len(grp) != 72 or len(ko) != 32 or missing_uk or missing_venue:
        print("!! VALIDATION FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
