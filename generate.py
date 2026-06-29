#!/usr/bin/env python3
"""Generate the World Cup 2026 calendars (UK, Japan, hybrid) as .ics files.

Fixtures, kickoff times (venue-local + UTC offset), venues and the knockout
bracket come from the vendored openfootball data in data/. Broadcaster labels
(UK BBC/ITV + Japan free-to-air) come from data/broadcasters.json.

Three calendars are produced from the same data:
  docs/uk.ics      UK only      - BBC/ITV (BBC = iPlayer 4K, ITV = ITVX HD)
  docs/japan.ics   Japan only   - NHK/NTV/Fuji/BS4K; no label = DAZN only
  docs/hybrid.ics  UK + Japan   - UK BBC/ITV + 🇯🇵 flag (FTA) / 🇯🇵 BS (BS4K only)

Group broadcasters are keyed by team pair; knockout broadcasters by match
number (73-104) so they can be filled in as picks are announced. Knockout team
slots (2A, W74, …) resolve automatically when openfootball updates upstream.

Output is deterministic (DTSTAMP = DTSTART) so re-running with unchanged input
produces byte-identical files - the update workflow only commits real changes.
Events are emitted in UTC (…Z); calendar apps show each kickoff in local time.
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
DOCS = ROOT / "docs"

PRODID = "-//taro-arumakan//WorldCup2026//EN"

# variant -> (filename, X-WR-CALNAME, X-WR-CALDESC)
VARIANTS = {
    "uk": ("uk.ics", "World Cup 2026 ⚽ UK TV (BBC/ITV)",
           "FIFA World Cup 2026, all 104 matches, UK broadcaster in the title. "
           "BBC = iPlayer (live in 4K UHD); ITV = ITVX (HD only). Knockouts TBC. "
           "Kickoffs auto-convert to your local time."),
    "jp": ("japan.ics", "World Cup 2026 ⚽ 日本の放送 (NHK/民放/BS4K)",
           "FIFAワールドカップ2026 全104試合。地上波(NHK/日テレ/フジ)・BS4Kを表示。"
           "表示のない試合はDAZNのみ。ノックアウトは未定。時刻は端末のタイムゾーンで表示。"),
    "hybrid": ("hybrid.ics", "World Cup 2026 ⚽ UK + Japan TV",
               "FIFA World Cup 2026, all 104 matches. UK BBC/ITV channel, plus a "
               "🇯🇵 flag when on Japanese free-to-air (🇯🇵 BS = BS4K only; no flag = DAZN only). "
               "Knockouts TBC. Kickoffs auto-convert to your local time."),
}

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})  # also accept Jun/Jul

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

JP_FULL = {"NHK": "NHK総合", "NTV": "日本テレビ", "Fuji": "フジテレビ",
           "BS4K": "NHK BS Premium 4K"}


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z]", "", s)
    return ALIASES.get(s, s)


def pair_key(a, b):
    return "|".join(sorted([norm(a), norm(b)]))


def split_matchup(m):
    """Return (home, away, score|None). Handles scheduled ('A v B', incl. bracket
    slots like 'W74 v W77'), played ('A 2-0 (1-0) B'), and extra-time/penalty
    knockout formats ('A 1-1 a.e.t. (1-1, 1-0), 1-3 pen. B')."""
    m = m.strip()
    if re.search(r"\s+v\s+", m):
        home, away = re.split(r"\s+v\s+", m, maxsplit=1)
        return home.strip(), away.strip(), None
    score_block = (r"\s+(\d+)-(\d+)"                 # full-time score
                   r"(?:\s+a\.e\.t\.?)?"             # optional 'a.e.t' / 'a.e.t.'
                   r"(?:\s*\([\d\s,-]+\))?"           # optional '(1-0)' or '(1-1, 1-0)'
                   r"(?:\s*,?\s*\d+-\d+\s+pen\.?)?"   # optional ', 1-3 pen.'
                   r"\s+")
    parts = re.split(score_block, m, maxsplit=1)
    if len(parts) >= 4:                              # [home, g1, g2, away]
        return parts[0].strip(), parts[-1].strip(), f"{parts[1]}-{parts[2]}"
    return m.strip(), "", None                       # last resort: never crash


def strip_comments(text):
    """Drop openfootball '#' comments - full-line and the inline '## 1E'-style
    slot tags appended to fixtures as the draw resolves (they otherwise bleed
    into the venue capture and break the stadium lookup)."""
    return re.sub(r"[ \t]*#.*", "", text)


def parse_groups(text):
    text = strip_comments(text)
    matches, group, date, started = [], None, None, False
    for raw in text.splitlines():
        line = raw.strip()
        mg = re.match(r"^▪\s*Group\s+([A-L])\b", line)
        if mg:
            group, date, started = mg.group(1), None, True
            continue
        if line.startswith("▪"):
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
            matches.append(dict(stage="group", label="Group " + group,
                                mon=date[0], day=date[1], hh=int(hh), mm=int(mm),
                                off=int(off), home=home, away=away, score=score,
                                venue=venue.strip()))
    return matches


def parse_finals(text):
    stages = [("Round of 32", "Round of 32"), ("Round of 16", "Round of 16"),
              ("Quarter-final", "Quarter-final"), ("Semi-final", "Semi-final"),
              ("Match for third place", "Third-place play-off"), ("Final", "Final")]
    text = strip_comments(text)
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
            home, away, score = split_matchup(matchup)
            venue = re.sub(r"\s*##.*$", "", venue).strip()   # drop trailing '## slot' note
            matches.append(dict(stage="ko", label=stage, num=int(num), mon=date[0],
                                day=date[1], hh=int(hh), mm=int(mm), off=int(off),
                                home=home, away=away, score=score,
                                venue=venue))
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
    """Return (group_map keyed by team-pair, ko_map keyed by int match number)."""
    doc = json.loads((DATA / "broadcasters.json").read_text(encoding="utf-8"))
    group = {}
    for e in doc["matches"]:
        a, b = re.split(r"\s+v\s+", e["match"], maxsplit=1)
        group[pair_key(a, b)] = {k: e[k] for k in ("uk", "jp") if e.get(k)}
    ko = {int(num): {k: v.get(k) for k in ("uk", "jp") if v.get(k)}
          for num, v in doc.get("knockouts", {}).items()}
    return group, ko


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
        while j < len(b) and (b[j] & 0xC0) == 0x80:
            j -= 1
        chunks.append(b[i:j].decode("utf-8"))
        i, limit = j, 72
    return "\r\n ".join(chunks)


HOME_NATIONS = {"england", "scotland"}   # home nations present at WC2026


def uk_detail(uk):
    return {
        "BBC": "BBC One / iPlayer - live in 4K UHD",
        "ITV": "ITV1 / ITVX - HD only (STV in Scotland)",
        "BBC/ITV": "BBC One + ITV1 - shown on both channels",
    }.get(uk, "TBC")


def knockout_uk(m):
    """UK routing knowable before teams are drawn: the final is shared on both;
    England's/Scotland's games are BBC (R32/R16/SF) or ITV (QF). Fires only once
    a real team name is present, so neutral/undrawn slots stay None (TBC)."""
    if m["label"] == "Final":
        return "BBC/ITV"
    if {norm(m["home"]), norm(m["away"])} & HOME_NATIONS:
        return "ITV" if m["label"] == "Quarter-final" else "BBC"
    return None


def knockout_jp(m):
    """Japan-team routing: Japan's R32 game is on Fuji, R16 onward on NHK総合
    (per the Japan Consortium plan). Fires only when Japan are actually in the
    tie; neutral games stay None until their round's terrestrial card is set."""
    if "japan" in {norm(m["home"]), norm(m["away"])}:
        return "Fuji" if m["label"] == "Round of 32" else "NHK"
    return None


def summary_for(m, variant, bc):
    fixture = f'{m["home"]} v {m["away"]}'
    title = fixture if m["stage"] == "group" else f'{m["label"]}: {fixture}'
    uk, jp = bc.get("uk"), bc.get("jp")
    if variant == "uk":
        return f"{title} - {uk}" if uk else title
    if variant == "jp":
        return f"{title} - {jp}" if jp else title
    # hybrid: UK channel (BBC/ITV implies the 4K/HD split) + a Japan flag
    s = f"{title} - {uk}" if uk else title
    if jp:
        sep = " | " if uk else " - "
        s += sep + ("🇯🇵 BS" if jp == "BS4K" else "🇯🇵")
    return s


def description_for(m, variant, bc, location):
    # Line 1: game (group/stage + venue) · then broadcaster(s) · then result.
    lines = [f'{m["label"]} / {location}']
    uk, jp = bc.get("uk"), bc.get("jp")
    grp = m["stage"] == "group"
    if not uk and not jp and not grp:
        lines.append("Broadcasters: TBC")
    else:
        if variant in ("uk", "hybrid"):
            lines.append("UK: " + (uk_detail(uk) if uk else "TBC"))
        if variant in ("jp", "hybrid"):
            if jp == "BS4K":
                lines.append("Japan: NHK BS Premium 4K / DAZN")
            elif jp:
                lines.append(f"Japan: {JP_FULL[jp]} / DAZN")
            elif grp:
                lines.append("Japan: DAZN only")
            else:
                lines.append("Japan: TBC")
    if m["score"]:
        lines.append(f'Result: {m["home"]} {m["score"]} {m["away"]}')
    return "\n".join(lines)


def build_event(m, variant, bc, location):
    dt = to_utc(m)
    stamp = dt.strftime("%Y%m%dT%H%M%SZ")
    dur = timedelta(hours=2) if m["stage"] == "group" else timedelta(hours=2, minutes=30)
    key = pair_key(m["home"], m["away"]).replace("|", "-") if m["stage"] == "group" else f'ko-{m["num"]}'
    return dt, [
        "BEGIN:VEVENT",
        f"UID:wc2026-{variant}-{key}@worldcup-2026-calendar",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{stamp}",
        f'DTEND:{(dt + dur).strftime("%Y%m%dT%H%M%SZ")}',
        f"SUMMARY:{esc(summary_for(m, variant, bc))}",
        f"LOCATION:{esc(location)}",
        f"DESCRIPTION:{esc(description_for(m, variant, bc, location))}",
        "CATEGORIES:World Cup 2026,Football",
        "TRANSP:TRANSPARENT",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ]


def write_calendar(path, name, desc, event_lines):
    out = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}", "X-WR-TIMEZONE:UTC",
        f"X-WR-CALDESC:{esc(desc)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
    ] + event_lines + ["END:VCALENDAR"]
    path.write_text("\r\n".join(fold(l) for l in out) + "\r\n", encoding="utf-8")


def main():
    stadiums = load_stadiums()
    group_bc, ko_bc = load_broadcasters()
    matches = parse_groups((DATA / "cup.txt").read_text(encoding="utf-8"))
    matches += parse_finals((DATA / "cup_finals.txt").read_text(encoding="utf-8"))

    DOCS.mkdir(parents=True, exist_ok=True)
    for variant, (fname, name, desc) in VARIANTS.items():
        events = []
        for m in matches:
            if m["stage"] == "group":
                bc = group_bc.get(pair_key(m["home"], m["away"]), {})
            else:
                ex = ko_bc.get(m["num"], {})          # explicit entry overrides the rule
                bc = {}
                uk = ex.get("uk") or knockout_uk(m)
                if uk:
                    bc["uk"] = uk
                jp = ex.get("jp") or knockout_jp(m)
                if jp:
                    bc["jp"] = jp
            location = f'{stadiums.get(m["venue"], "")}, {m["venue"]}'.lstrip(", ")
            events.append(build_event(m, variant, bc, location))
        lines = [l for _, ls in sorted(events, key=lambda x: x[0]) for l in ls]
        write_calendar(DOCS / fname, name, desc, lines)
        print(f"{fname:14s} {len(events)} events  ({(DOCS / fname).stat().st_size} bytes)")

    # ---- validation ---------------------------------------------------------
    grp = [m for m in matches if m["stage"] == "group"]
    ko = [m for m in matches if m["stage"] == "ko"]
    missing_uk = [f'{m["home"]} v {m["away"]}' for m in grp
                  if not group_bc.get(pair_key(m["home"], m["away"]), {}).get("uk")]
    with_jp = sum(1 for m in grp if group_bc.get(pair_key(m["home"], m["away"]), {}).get("jp"))
    ko_labelled = sum(1 for m in ko if ko_bc.get(m["num"], {}).get("uk") or knockout_uk(m))
    missing_venue = sorted({m["venue"] for m in matches if m["venue"] not in stadiums})
    print(f"\ngroups={len(grp)} (exp 72)  knockout={len(ko)} (exp 32)  total={len(matches)}")
    print(f"missing UK label: {len(missing_uk)} {missing_uk}")
    print(f"JP FTA labels: {with_jp} (exp 32)   knockout broadcasters set: {ko_labelled}")
    print(f"venues unmapped: {missing_venue or 'none'}")
    if len(grp) != 72 or len(ko) != 32 or missing_uk or missing_venue:
        print("!! VALIDATION FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
