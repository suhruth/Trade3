#!/usr/bin/env python3
"""
build_monthly.py — auto-fill "Bucket A" (price/volume-derived) of the monthly sheet
from watchlist.csv + the bhavcopy archive. No paid feeds, no manual typing.

Writes into journal/<YYYY>/<MM-Month>/:
  - universe.csv : per stock, MERGES in median_trdval_cr, liquid, ret_1m_pct,
                   ret_3m_pct (Bucket A). Existing fundamental/tier cells (Bucket B,
                   from your Screener merge) are PRESERVED — safe to re-run.
And prints the §1 regime block (breadth) for you to paste into monthly.md.

Sector rotation (sectors.csv / Stage 2) is a SEPARATE step, owned by
rank_sectors.py — it ranks the official NSE sectoral indexes, not watchlist
constituents. Run that first; this script no longer touches sectors.csv.

What it does NOT do: fundamentals (Screener export = Bucket B), tier assignment,
and the Nifty-EMA regime lines (need index data, not in the security bhavcopy).

Usage:
    python build_monthly.py                 # this month, as-of the latest bhavcopy
    python build_monthly.py --month 2026-07 # target a specific journal month
"""

import argparse
import calendar
import csv
import re
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WATCHLIST = REPO / "watchlist.csv"
BHAV_DIR = REPO / "data" / "bhavcopy"
JOURNAL = REPO / "journal"
UNIVERSE_TEMPLATE = REPO / "templates" / "monthly-universe-template.csv"

# bhavcopy column indices (sec_bhavdata_full): SYMBOL,SERIES,...,CLOSE(8),...,TURNOVER_LACS(11)
C_SYMBOL, C_SERIES, C_CLOSE, C_TURNOVER = 0, 1, 8, 11

LOOKBACK_1M = 21     # trading sessions ~ 1 month
LOOKBACK_3M = 63     # ~ 3 months
TURN_WINDOW = 20     # sessions for median traded value
DMA = 50             # sessions for breadth (% above 50-DMA)
LIQUID_CR = 20.0     # median traded value gate, in Rs crore
READ_FILES = LOOKBACK_3M + 2   # how many recent bhavcopy days we need

# Bucket A columns this script owns (everything else in universe.csv is preserved).
BUCKET_A = ("median_trdval_cr", "liquid", "ret_1m_pct", "ret_3m_pct")


def _date_key(p: Path):
    m = re.search(r"(\d{2})(\d{2})(\d{4})", p.stem)
    return (m.group(3), m.group(2), m.group(1)) if m else ("", "", "")


def sorted_bhavcopies():
    return sorted(BHAV_DIR.glob("*/sec_bhavdata_full_*.csv"), key=_date_key)


def month_dirname(m: int) -> str:
    return f"{m:02d}-{calendar.month_name[m]}"


def load_watchlist():
    """Return list of (symbol, sector) in file order."""
    out = []
    with open(WATCHLIST, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            sec = (row.get("sector") or "").strip()
            if sym and "EXAMPLE" not in (row.get("notes") or "").upper():
                out.append((sym, sec))
    return out


def read_series(paths):
    """
    Read the given bhavcopy files (date order) once.
    Returns (closes, turns): closes[sym]=[close...] for all EQ symbols;
    turns[sym]=[turnover_cr...] (only needed later, kept for all EQ — cheap).
    """
    closes = defaultdict(list)
    turns = defaultdict(list)
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            seen = set()
            for row in reader:
                if len(row) <= C_TURNOVER:
                    continue
                if row[C_SERIES].strip() != "EQ":
                    continue
                sym = row[C_SYMBOL].strip()
                if sym in seen:
                    continue  # dedupe within a file
                seen.add(sym)
                try:
                    closes[sym].append(float(row[C_CLOSE]))
                    turns[sym].append(float(row[C_TURNOVER]) / 100.0)  # lakh -> crore
                except ValueError:
                    continue
    return closes, turns


def pct_return(series, back):
    if len(series) > back:
        old = series[-1 - back]
        if old:
            return round((series[-1] / old - 1) * 100, 2)
    return None


def compute_breadth(closes):
    above = total = 0
    for series in closes.values():
        if len(series) >= DMA:
            dma = statistics.fmean(series[-DMA:])
            total += 1
            if series[-1] > dma:
                above += 1
    return (round(above / total * 100, 1) if total else None), total


def build_universe_rows(watch, closes, turns):
    """One dict per watchlist symbol with Bucket A filled; returns (rows, insufficient)."""
    rows, insufficient = [], []
    for sym, sec in watch:
        r1 = pct_return(closes.get(sym, []), LOOKBACK_1M)
        r3 = pct_return(closes.get(sym, []), LOOKBACK_3M)
        tvals = turns.get(sym, [])[-TURN_WINDOW:]
        med = round(statistics.median(tvals), 1) if tvals else None
        rows.append({
            "symbol": sym, "sector": sec,
            "median_trdval_cr": "" if med is None else med,
            "liquid": "" if med is None else ("Y" if med > LIQUID_CR else "N"),
            "ret_1m_pct": "" if r1 is None else r1,
            "ret_3m_pct": "" if r3 is None else r3,
        })
        if r3 is None:
            insufficient.append(sym)
    return rows, insufficient


def merge_universe(dest: Path, header, computed_rows, owned=BUCKET_A, always=("symbol", "sector")):
    """Preserve existing cells outside `owned`/`always`; overwrite those; key by symbol,
    order by computed_rows. `always` columns are watchlist-authoritative (e.g. sector);
    `owned` are this caller's computed columns (Bucket A by default)."""
    existing = {}
    if dest.exists():
        with open(dest, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[(row.get("symbol") or "").strip()] = row

    out = []
    for comp in computed_rows:
        sym = comp["symbol"]
        row = {col: "" for col in header}
        if sym in existing:
            for col in header:
                row[col] = existing[sym].get(col, "") or ""
        for col in always:
            if col in comp:
                row[col] = comp[col]
        for col in owned:
            if col in comp:
                row[col] = comp[col]
        out.append(row)

    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(out)
    return len(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-fill Bucket A of the monthly sheet from bhavcopy.")
    ap.add_argument("--month", help="target journal month YYYY-MM (default: current month)")
    args = ap.parse_args()

    if args.month:
        y, m = map(int, args.month.split("-"))
    else:
        t = date.today()
        y, m = t.year, t.month

    files = sorted_bhavcopies()
    if len(files) < LOOKBACK_1M + 2:
        print(f"ERROR: only {len(files)} bhavcopy days archived; need > {LOOKBACK_1M+1} for 1M returns.")
        return 1
    files = files[-READ_FILES:]
    asof = _date_key(files[-1])
    print(f"As-of bhavcopy: {files[-1].name}  ({len(files)} days loaded)\n")

    watch = load_watchlist()
    closes, turns = read_series(files)

    universe_rows, insufficient = build_universe_rows(watch, closes, turns)

    month_dir = JOURNAL / str(y) / month_dirname(m)
    month_dir.mkdir(parents=True, exist_ok=True)

    with open(UNIVERSE_TEMPLATE, newline="", encoding="utf-8") as f:
        uni_header = next(csv.reader(f))
    n_uni = merge_universe(month_dir / "universe.csv", uni_header, universe_rows)

    breadth, breadth_n = compute_breadth(closes)
    liquid_n = sum(1 for r in universe_rows if r["liquid"] == "Y")

    # ---- report ----
    print(f"universe.csv : {n_uni} names written (Bucket A filled, fundamentals preserved)")
    print(f"               liquid (>{LIQUID_CR:.0f} Cr): {liquid_n}/{n_uni}")
    if insufficient:
        print(f"               short history (no 3M return): {', '.join(insufficient)}")
    print(f"\n(Sector rotation is a separate step - run: python source/rank_sectors.py)")

    print(f"\nSection 1 Regime (paste into monthly.md):")
    print(f"   Breadth: {breadth}% of {breadth_n} EQ stocks above their 50-DMA "
          f"({'>50 = OK' if (breadth or 0) > 50 else 'WEAK'})")
    print(f"   (Nifty vs 20/50 EMA + HH/LL structure: fill manually from Zerodha - not in security bhavcopy.)")
    print(f"\nWritten to {month_dir.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
