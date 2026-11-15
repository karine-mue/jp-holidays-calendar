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
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
_DATE_RE = re.compile(r"([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})")
_DTSTAMP_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z")

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

    for row in reader:
        # reader.line_num is the physical line number in the source,
        # unlike a record counter when quoted fields span lines.
        line_num = reader.line_num
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

        # Strict shape check: int() alone would also accept fullwidth
        # digits, underscores ("2_026") and signs ("+2026").
        m = _DATE_RE.fullmatch(date_text)
        if m is None:
            raise ValueError(
                f"Malformed row at line {line_num}: invalid date {date_text!r} ({row!r})"
            )
        try:
            holiday_date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
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
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\r", "\\n")
        .replace("\n", "\\n")
    )

def _fmt_date(d: datetime.date) -> str:
    """Format as YYYYMMDD with explicit zero-padding.

    strftime("%Y") does not zero-pad years below 1000 on some platforms.
    """
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def build_ics(rows: list[tuple[datetime.date, str]], dtstamp: str) -> str:
    """Build an iCalendar (.ics) string with CRLF line endings."""
    if not isinstance(dtstamp, str) or _DTSTAMP_RE.fullmatch(dtstamp) is None:
        raise ValueError(f"Invalid DTSTAMP: {dtstamp!r}")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jp-holidays-calendar//JA//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:日本の祝日（内閣府）",
    ]

    one_day = datetime.timedelta(days=1)

    for holiday_date, name in rows:
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:syukujitsu-{_fmt_date(holiday_date)}@jp-holidays-calendar",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{_fmt_date(holiday_date)}",
            f"DTEND;VALUE=DATE:{_fmt_date(holiday_date + one_day)}",
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
    """Load cp932 (Shift_JIS family) CSV content from a local path or URL."""
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(
            source, headers={"User-Agent": "jp-holidays-calendar"}
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            raw_bytes = response.read()
        return raw_bytes.decode("cp932")
    if os.path.exists(source):
        with open(source, "rb") as file_handle:
            raw_bytes = file_handle.read()
        return raw_bytes.decode("cp932")
    raise ValueError(f"Source not found (not a URL, not an existing file): {source}")

def _write_atomic(path: Path, content: str) -> None:
    """Write via a temp file in the same directory, then replace."""
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    os.replace(tmp_path, path)

def main(argv: list[str] | None = None) -> int:
    # The calendar is Japan's; the default year must follow JST, not UTC
    # (in UTC, JST New Year 00:00-08:59 still counts as the previous year).
    default_from_year = datetime.datetime.now(JST).year - 1

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

    if not 1900 <= args.from_year <= 2100:
        parser.error(f"--from-year out of range (1900-2100): {args.from_year}")

    raw_text = _load_source_text(args.source)
    all_rows = parse_holidays(raw_text)
    filtered_rows = [
        (holiday_date, name)
        for holiday_date, name in all_rows
        if holiday_date.year >= args.from_year
    ]

    if not filtered_rows:
        # Never overwrite good outputs with an empty calendar: a header-only
        # source or an over-narrow filter is an error, not a publication.
        raise SystemExit(
            f"error: 0 holidays at or after year {args.from_year} "
            f"(source rows: {len(all_rows)}); refusing to write empty outputs"
        )

    dtstamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics_content = build_ics(filtered_rows, dtstamp)
    csv_content = build_utf8_csv(filtered_rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_atomic(out_dir / "syukujitsu.ics", ics_content)
    _write_atomic(out_dir / "syukujitsu.csv", csv_content)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
