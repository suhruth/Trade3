#!/usr/bin/env python3
"""
archive_bhavcopy.py — nightly archiver for NSE's full security-wise bhavcopy.

Downloads `sec_bhavdata_full_DDMMYYYY.csv` (the ONLY bhavcopy that carries the
delivery columns DELIV_QTY / DELIV_PER) and stores one raw file per trading day.
This is the no-backfill history the scoring model needs for delivery-% trends
(Stages 5 & 7) and market breadth (Stage 1) — see docs Appendix B.

Scope: download-and-store only. No parsing, no scoring. The raw CSV is kept
verbatim (leading spaces in headers and all) so nothing is lost; normalization
is the loader's job later.

Usage:
    python archive_bhavcopy.py                      # latest trading day (today, else most recent weekday)
    python archive_bhavcopy.py --date 2025-07-22    # a specific day (YYYY-MM-DD or DDMMYYYY)
    python archive_bhavcopy.py --from 2025-07-01 --to 2025-07-22   # backfill a range
    python archive_bhavcopy.py --from 2025-07-01    # backfill from a date up to today
    python archive_bhavcopy.py --out D:/some/dir    # override output root

Exit code is 0 if every requested trading day is present (downloaded or already
on disk), 1 if any day genuinely failed (network/other error, not a holiday).
"""

import argparse
import http.cookiejar
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# Archive CDN. `archives.nseindia.com` now redirects here; use the canonical host.
BASE_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
HOMEPAGE = "https://www.nseindia.com"

# NSE returns 403 without a browser-like User-Agent. These headers + a cookie
# primed from the homepage are enough to fetch the static archive file.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": HOMEPAGE + "/all-reports",
}

# Default archive root: <repo>/data/bhavcopy/<year>/sec_bhavdata_full_DDMMYYYY.csv
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "data" / "bhavcopy"

CONNECT_TIMEOUT = 30  # seconds
MAX_ATTEMPTS = 3      # per day, before giving up on a transient error
BACKOFF_BASE = 2      # seconds; exponential -> waits 2s then 4s between attempts


def build_opener() -> urllib.request.OpenerDirector:
    """An opener with a cookie jar; priming the homepage sets the cookies NSE wants."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        req = urllib.request.Request(HOMEPAGE, headers=HEADERS)
        opener.open(req, timeout=CONNECT_TIMEOUT).read()
    except Exception:
        # Cookie priming is best-effort; the archive host often serves without it.
        pass
    return opener


def parse_date(text: str) -> date:
    """Accept YYYY-MM-DD or DDMMYYYY."""
    for fmt in ("%Y-%m-%d", "%d%m%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"unrecognized date '{text}' (use YYYY-MM-DD or DDMMYYYY)")


def target_path(out_root: Path, day: date) -> Path:
    return out_root / f"{day.year}" / f"sec_bhavdata_full_{day:%d%m%Y}.csv"


def looks_like_bhavcopy(body: bytes) -> bool:
    """Guard against NSE serving an HTML error page with a 200 status."""
    head = body[:2000].lstrip().upper()
    return b"SYMBOL" in head and b"DELIV_PER" in head


def download_day(opener, out_root: Path, day: date) -> str:
    """
    Fetch one day's file, retrying transient failures with exponential backoff.
    Returns one of:
      'exists'   already on disk (skipped)
      'saved'    downloaded and written
      'holiday'  404 — no trading that day (weekend/holiday/not yet published)
      'failed'   still erroring after MAX_ATTEMPTS

    A 404 is definitive (no data exists) and is NOT retried; network errors,
    5xx responses, and blocked/empty bodies ARE retried.
    """
    dest = target_path(out_root, day)
    if dest.exists() and dest.stat().st_size > 0:
        return "exists"

    url = BASE_URL.format(ddmmyyyy=f"{day:%d%m%Y}")
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with opener.open(req, timeout=CONNECT_TIMEOUT) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "holiday"  # definitive — don't waste retries on it
            last_error = f"HTTP {e.code} {e.reason}"
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = str(e)
        else:
            if looks_like_bhavcopy(body):
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(".csv.part")
                tmp.write_bytes(body)
                tmp.replace(dest)  # atomic: never leave a half-written file at the real path
                return "saved"
            last_error = "response didn't look like a bhavcopy (blocked or empty)"

        if attempt < MAX_ATTEMPTS:
            wait = BACKOFF_BASE * (2 ** (attempt - 1))  # 2s, then 4s
            print(
                f"  ~ {day:%Y-%m-%d}: {last_error} "
                f"(attempt {attempt}/{MAX_ATTEMPTS}, retrying in {wait}s)",
                file=sys.stderr,
            )
            time.sleep(wait)

    print(f"  ! {day:%Y-%m-%d}: {last_error} (gave up after {MAX_ATTEMPTS} attempts)", file=sys.stderr)
    return "failed"


def daterange(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive NSE full bhavcopy (with delivery).")
    ap.add_argument("--date", type=parse_date, help="single day (YYYY-MM-DD or DDMMYYYY)")
    ap.add_argument("--from", dest="start", type=parse_date, help="range start (inclusive)")
    ap.add_argument("--to", dest="end", type=parse_date, help="range end (inclusive; default today)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output root (default: {DEFAULT_OUT})")
    args = ap.parse_args()

    today = date.today()

    if args.date and (args.start or args.end):
        ap.error("use --date OR --from/--to, not both")

    if args.date:
        days = [args.date]
    elif args.start:
        end = args.end or today
        if end < args.start:
            ap.error("--to is before --from")
        # Skip weekends up front; holidays are detected as 404s during download.
        days = [d for d in daterange(args.start, end) if d.weekday() < 5]
    else:
        # No args: the latest trading day. If today is a weekend, step back to Friday.
        d = today
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        days = [d]

    opener = build_opener()
    counts = {"saved": 0, "exists": 0, "holiday": 0, "failed": 0}
    for day in days:
        status = download_day(opener, args.out, day)
        counts[status] += 1
        symbol = {"saved": "+", "exists": "=", "holiday": ".", "failed": "x"}[status]
        print(f"  {symbol} {day:%Y-%m-%d}  {status}")

    print(
        f"\nDone: {counts['saved']} saved, {counts['exists']} already present, "
        f"{counts['holiday']} holiday/weekend, {counts['failed']} failed  ->  {args.out}"
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
