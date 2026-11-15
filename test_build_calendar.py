"""Tests for build_calendar.py — run: python3 test_build_calendar.py"""
import sys
from datetime import date

sys.path.insert(0, ".")
from build_calendar import parse_holidays, build_ics, build_utf8_csv

FIXTURE = """国民の祝日・休日月日,国民の祝日・休日名称
2026/1/1,元日
2026/5/3,憲法記念日
2026/5/4,みどりの日
2026/5/5,こどもの日
2026/5/6,振替休日
2025/12/31,大晦日ダミー
"""

failures = []

def check(name, cond):
    print(("PASS" if cond else "FAIL"), name)
    if not cond:
        failures.append(name)

# --- parse_holidays ---
rows = parse_holidays(FIXTURE)
check("parse count", len(rows) == 6)
check("parse sorted", [r[0] for r in rows] == sorted(r[0] for r in rows))
check("parse first", rows[0] == (date(2025, 12, 31), "大晦日ダミー"))
check("parse gantan", (date(2026, 1, 1), "元日") in rows)
check("parse types", all(isinstance(d, date) and isinstance(n, str) for d, n in rows))

# duplicate removal
dup = parse_holidays(FIXTURE + "2026/1/1,元日\n")
check("parse dedupe", len(dup) == 6)

# --- build_ics ---
ics = build_ics(rows, "20260101T000000Z")
check("ics header", "BEGIN:VCALENDAR" in ics and "VERSION:2.0" in ics)
check("ics calname", "X-WR-CALNAME:日本の祝日（内閣府）" in ics)
check("ics event count", ics.count("BEGIN:VEVENT") == 6)
check("ics crlf", "\r\n" in ics and ics.count("\n") == ics.count("\r\n"))
check("ics dtstart", "DTSTART;VALUE=DATE:20260101" in ics)
check("ics dtend next day", "DTEND;VALUE=DATE:20260102" in ics)
check("ics dtend year boundary", "DTEND;VALUE=DATE:20260101" in ics)  # 2025/12/31 -> 2026/01/01
check("ics uid", "UID:syukujitsu-20260101@jp-holidays-calendar" in ics)
uids = [l for l in ics.split("\r\n") if l.startswith("UID:")]
check("ics uid unique", len(uids) == len(set(uids)) == 6)
check("ics summary", "SUMMARY:振替休日" in ics)
check("ics transparent", ics.count("TRANSP:TRANSPARENT") == 6)
check("ics dtstamp", ics.count("DTSTAMP:20260101T000000Z") == 6)

# --- build_utf8_csv ---
out = build_utf8_csv(rows)
lines = out.strip().splitlines()
check("csv header", lines[0] == "date,name")
check("csv count", len(lines) == 7)
check("csv iso", "2026-01-01,元日" in lines)
check("csv furikae", "2026-05-06,振替休日" in lines)

# --- review fixes (2026-11-15) ---
from build_calendar import _escape_ics_text, _load_source_text, main

check("ics prodid JA", "PRODID:-//jp-holidays-calendar//JA//" in ics)

def _parse_raises(text):
    try:
        parse_holidays(text)
        return False
    except ValueError:
        return True

HDR = "国民の祝日・休日月日,国民の祝日・休日名称\n"
check("date fullwidth rejected", _parse_raises(HDR + "２０２６/1/1,元日\n"))
check("date underscore rejected", _parse_raises(HDR + "2_026/1/1,元日\n"))
check("date sign rejected", _parse_raises(HDR + "+2026/1/1,元日\n"))
check("date short year rejected", _parse_raises(HDR + "26/1/1,元日\n"))
check("date invalid day rejected", _parse_raises(HDR + "2026/2/30,元日\n"))

check("escape CR", _escape_ics_text("a\rb") == "a\\nb")
check("escape CRLF", _escape_ics_text("a\r\nb") == "a\\nb")

def _ics_raises(dtstamp):
    try:
        build_ics(rows, dtstamp)
        return False
    except ValueError:
        return True

check("dtstamp shape enforced", _ics_raises("2026010T000000Z") and _ics_raises("20260101T000000")
      and not _ics_raises("20260101T000000Z"))

# header-only source -> main refuses to write empty outputs
import os
import tempfile
with tempfile.TemporaryDirectory() as d:
    src = os.path.join(d, "header_only.csv")
    with open(src, "wb") as f:
        f.write(HDR.encode("cp932"))
    out_dir = os.path.join(d, "out")
    try:
        main(["--source", src, "--out-dir", out_dir])
        check("zero rows refused", False)
    except SystemExit:
        check("zero rows refused", not os.path.exists(os.path.join(out_dir, "syukujitsu.ics")))

# missing local source -> error, not a URL fetch attempt
try:
    _load_source_text("/nonexistent/path/syukujitsu.csv")
    check("missing source raises", False)
except ValueError:
    check("missing source raises", True)

# --from-year out of range -> argparse error (SystemExit)
try:
    main(["--from-year", "1800", "--source", src])
    check("from-year range", False)
except SystemExit:
    check("from-year range", True)

print()
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("ALL TESTS PASSED")
