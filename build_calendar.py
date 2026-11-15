#!/usr/bin/env python3
"""build_calendar.py

Converts the Japanese Cabinet Office's official national-holiday CSV
into an iCalendar (.ics) file and a normalized UTF-8 CSV.
"""

import argparse
import csv
import datetime
import io
import os
import urllib.request
from pathlib import Path

DEFAULT_SOURCE_URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
EXPECTED_HEADERS = ("国民の祝日・休日月日", "国民の祝日・休日名称")

def parse_holidays(text: str) -> list[tuple[datetime.date, str]]:
    """Parse decoded holiday CSV text into sorted, deduplicated (date, name) tuples."""
    if not text or not text.strip():
        raise ValueError("Input CSV text is empty.")

    cleaned_text = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(cleaned_text))

    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("Input CSV text is empty.") from exc

    if header != list(EXPECTED_HEADERS):
        raise ValueError(
            f"Unexpected CSV header: {header!r}; "
            f"expected {list(EXPECTED_HEADERS)!r}"
        )

    rows: list[tuple[datetime.date, str]] = []
    seen: set[tuple[datetime.date, str]] = set()

    for line_num, row in enumerate(reader, start=2):
        if not row or (len(row) == 1 and not row[0].strip()):
            continue

        if len(row) != 2:
            raise ValueError(
                f"Malformed row at line {line_num}: expected 2 columns, got {len(row)} ({row!r})"
            )

        date_text, name = row
        name = name.strip()
        date_text = date_text.strip()

        if not name:
            raise ValueError(f"Malformed row at line {line_num}: empty holiday name ({row!r})")

        if not date_text:
            raise ValueError(f"Malformed row at line {line_num}: empty date ({row!r})")

        try:
            parts = date_text.split("/")
            if len(parts) != 3:
                raise ValueError("Date must use YYYY/M/D format")
            year, month, day = (int(part) for part in parts)
            holiday_date = datetime.date(year, month, day)
        except ValueError as exc:
            raise ValueError(
                f"Malformed row at line {line_num}: invalid date {date_text!r} ({row!r})"
            ) from exc

        if (holiday_date, name) in seen:
            continue
        seen.add((holiday_date, name))
        rows.append((holiday_date, name))

    rows.sort(key=lambda item: item[0])
    return rows

def _escape_ics_text(value: str) -> str:
    """Escape text for iCalendar properties per RFC 5545."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def build_ics(rows: list[tuple[datetime.date, str]], dtstamp: str) -> str:
    """Build an iCalendar (.ics) string with CRLF line endings."""
    if not isinstance(dtstamp, str) or len(dtstamp) != 16 or not dtstamp.endswith("Z"):
        raise ValueError(f"Invalid DTSTAMP: {dtstamp!r}")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jp-holidays-calendar//JP//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:日本の祝日（内閣府）",
    ]

    one_day = datetime.timedelta(days=1)

    for holiday_date, name in rows:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:syukujitsu-{holiday_date.strftime('%Y%m%d')}@jp-holidays-calendar",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{holiday_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(holiday_date + one_day).strftime('%Y%m%d')}",
            f"SUMMARY:{_escape_ics_text(name)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def build_utf8_csv(rows: list[tuple[datetime.date, str]]) -> str:
    """Build a normalized UTF-8 CSV string with LF line endings."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["date", "name"])
    for holiday_date, name in rows:
        writer.writerow([holiday_date.isoformat(), name])
    return output.getvalue()

def _load_source_text(source: str) -> str:
    """Load Shift_JIS encoded CSV content from a local file path or the official URL."""
    if os.path.exists(source):
        with open(source, "rb") as file_handle:
            raw_bytes = file_handle.read()
        return raw_bytes.decode("cp932")
    with urllib.request.urlopen(source, timeout=60) as response:
        raw_bytes = response.read()
    return raw_bytes.decode("cp932")

def main(argv: list[str] | None = None) -> int:
    default_from_year = datetime.datetime.now(datetime.timezone.utc).year - 1

    parser = argparse.ArgumentParser(
        description="Convert Cabinet Office holiday CSV to iCalendar (.ics) and UTF-8 CSV."
    )
    parser.add_argument(
        "--from-year",
        type=int,
        default=default_from_year,
        help="Include only holidays in this year or later (default: current year - 1).",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE_URL,
        help="Source URL or local file path for syukujitsu.csv.",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=".",
        help="Output directory for syukujitsu.ics and syukujitsu.csv (default: current directory).",
    )

    args = parser.parse_args(argv)

    raw_text = _load_source_text(args.source)
    all_rows = parse_holidays(raw_text)
    filtered_rows = [
        (holiday_date, name)
        for holiday_date, name in all_rows
        if holiday_date.year >= args.from_year
    ]

    dtstamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics_content = build_ics(filtered_rows, dtstamp)
    csv_content = build_utf8_csv(filtered_rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ics_path = out_dir / "syukujitsu.ics"
    csv_path = out_dir / "syukujitsu.csv"

    with open(ics_path, "w", encoding="utf-8", newline="") as f_ics:
        f_ics.write(ics_content)

    with open(csv_path, "w", encoding="utf-8", newline="") as f_csv:
        f_csv.write(csv_content)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
