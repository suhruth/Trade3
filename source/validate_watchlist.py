#!/usr/bin/env python3
"""
validate_watchlist.py — sanity-check watchlist.csv before the monthly build.

Sector returns are computed from the watchlist's own constituents (bhavcopy), so
any sector label is allowed — there is no canonical-name check. Instead:
  - symbol must exist in the latest archived bhavcopy (catches typos / wrong tickers)
  - sector must be non-empty
  - no duplicate symbols
  - flags leftover EXAMPLE rows (hard-fail-free, but noted)
  - WARNS on "thin" sectors (< MIN_PER_SECTOR names) — their average return is noisy
Exit code 1 if any hard issue is found (unknown symbol, empty sector, duplicate).
"""

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WATCHLIST = REPO / "watchlist.csv"
BHAV_DIR = REPO / "data" / "bhavcopy"

MIN_PER_SECTOR = 3  # fewer constituents than this -> noisy sector-return proxy


def _date_key(p: Path):
    # filenames are sec_bhavdata_full_DDMMYYYY.csv — sort by (yyyy, mm, dd), not lexically.
    m = re.search(r"(\d{2})(\d{2})(\d{4})", p.stem)
    return (m.group(3), m.group(2), m.group(1)) if m else ("", "", "")


def latest_bhavcopy() -> Path | None:
    files = list(BHAV_DIR.glob("*/sec_bhavdata_full_*.csv"))
    return max(files, key=_date_key) if files else None


def load_bhav_symbols(path: Path) -> set:
    syms = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if row:
                syms.add(row[0].strip())
    return syms


def main() -> int:
    bhav = latest_bhavcopy()
    if not bhav:
        print("ERROR: no bhavcopy archived yet — run archive_bhavcopy.py first.")
        return 1
    symbols = load_bhav_symbols(bhav)

    bad_symbols, missing_sector, dupes, examples = [], [], [], []
    per_sector, seen = {}, {}
    total = 0

    with open(WATCHLIST, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):  # row 1 is header
            sym = (row.get("symbol") or "").strip()
            sec = (row.get("sector") or "").strip()
            note = (row.get("notes") or "").strip()
            if not sym:
                continue
            total += 1
            if "EXAMPLE" in note.upper():
                examples.append((i, sym))
            if sym not in symbols:
                bad_symbols.append((i, sym))
            if not sec:
                missing_sector.append((i, sym))
            else:
                per_sector[sec] = per_sector.get(sec, 0) + 1
            if sym in seen:
                dupes.append((i, sym, seen[sym]))
            else:
                seen[sym] = i

    print(f"Validated {total} names against {bhav.name} ({len(symbols)} bhavcopy symbols).\n")

    def block(title, items, fmt):
        if items:
            print(f"{title} ({len(items)}):")
            for it in items:
                print("   " + fmt(it))
            print()

    block("UNKNOWN SYMBOLS - not in bhavcopy", bad_symbols, lambda t: f"row {t[0]}: {t[1]}")
    block("MISSING SECTOR", missing_sector, lambda t: f"row {t[0]}: {t[1]}")
    block("DUPLICATE SYMBOLS", dupes, lambda t: f"row {t[0]}: {t[1]} (first seen row {t[2]})")
    block("LEFTOVER EXAMPLE ROWS", examples, lambda t: f"row {t[0]}: {t[1]}")

    thin = [s for s in per_sector if per_sector[s] < MIN_PER_SECTOR]
    print("Per-sector counts:")
    for sec in sorted(per_sector):
        mark = f"   <-- thin (<{MIN_PER_SECTOR}), noisy sector return" if sec in thin else ""
        print(f"   {per_sector[sec]:>3}  {sec}{mark}")

    issues = len(bad_symbols) + len(missing_sector) + len(dupes)
    print()
    warn = ""
    if thin:
        warn = f" ({len(thin)} thin sector(s) - consider adding names)"
    if examples:
        warn += " (example rows still present)"
    if issues:
        print(f"RESULT: {issues} hard issue(s) to fix.{warn}")
        return 1
    print(f"RESULT: OK.{warn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
