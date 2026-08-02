#!/usr/bin/env python3
"""
rank_sectors.py — the top-of-funnel sector-rotation step. Run this FIRST every
weekend and month-end: it ranks the key NSE sectoral indexes (see SECTORS below)
by real index data and classifies each on a Relative-Rotation-Graph (RRG)
quadrant, so you can see which sectors are leading now and which are
*improving* (about to lead). Only then do you hunt for stocks inside the
strong sectors.

Source: the archived NSE all-indices close files (data/indices/, from
archive_indices.py) — official index closes, not a watchlist proxy. Every
sector in SECTORS is ranked, even ones you hold no stocks in yet.

For each sector it computes (all mechanical):
  - ret_1m/3m/6m_pct : index return over 21 / 63 / 126 sessions
  - rp_1m/3m/6m      : Relative Performance = sector return − Nifty 50 return
                       (the "sector strength vs Nifty" metric)
  - rp_score         : 1–5 star score on the 3-month RP:
                       >15%→5, 10–15%→4, 5–10%→3, 0–5%→2, <0→1
  - rs_mom_20d       : % change of the RS line (sector ÷ Nifty 50) over 20
                       sessions — the RS-momentum axis
  - pct_off_6m_high  : how far the index sits below its 6-month closing high (0 =
                       at highs). Near-highs = institutions committed (money flow)
  - accel            : Y if the last month's pace beats the 3-month average
                       monthly pace (ret_1m > ret_3m / 3) — the sector is speeding up
  - quadrant         : RRG quadrant from RS level (rp_3m) × RS momentum (rs_mom_20d):
                         Leading    = ahead of Nifty  AND momentum rising
                         Weakening  = ahead of Nifty  BUT momentum falling
                         Improving  = behind Nifty    BUT momentum rising  ← next to lead
                         Lagging    = behind Nifty    AND momentum falling  ← avoid
  - stage2_pts       : 0–10, the v4-spec Stage 2 score reusable by the scorer:
                       top-5 by 1M return (4) + top-5 by 3M return (3) + RS
                       acceleration (3, RS line above its 20-days-ago value AND
                       its own 50-day average)

Rows are sorted by 3-month Relative Performance (strongest first). Writes
journal/<YYYY>/<MM-Month>/sectors.csv (owns this file) and prints a summary.

Usage:
    python rank_sectors.py                  # this month, as-of the latest index file
    python rank_sectors.py --month 2026-07  # target a specific journal month
    python rank_sectors.py --out path.csv   # write elsewhere (e.g. a weekly folder)
"""

import argparse
import calendar
import csv
import re
import statistics
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IDX_DIR = REPO / "data" / "indices"
JOURNAL = REPO / "journal"

# The key sectoral indexes (docs/Sectors.jpg plus 4 added to cover watchlist
# sectors that had no tracked index), mapped from the friendly label we
# display to the EXACT "Index Name" string inside ind_close_all_*.csv.
SECTORS = {
    "Nifty Auto":              "Nifty Auto",
    "Nifty Bank":              "Nifty Bank",
    "Nifty Capital Goods":     "Nifty Capital Goods",
    "Nifty Cement":            "Nifty Cement",
    "Nifty Commodities":       "Nifty Commodities",
    "Nifty Consumption":       "Nifty India Consumption",
    "Nifty CPSE":              "Nifty CPSE",
    "Nifty Energy":            "Nifty Energy",
    "Nifty Fin Service":       "Nifty Financial Services",
    "Nifty FMCG":              "Nifty FMCG",
    "Nifty Healthcare":        "Nifty Healthcare Index",
    "Nifty Infra":             "Nifty Infrastructure",
    "Nifty IT":                "Nifty IT",
    "Nifty Media":             "Nifty Media",
    "Nifty Metal":             "Nifty Metal",
    "Nifty Oil & Gas":         "Nifty Oil & Gas",
    "Nifty Pharma":            "Nifty Pharma",
    "Nifty PSE":               "Nifty PSE",
    "Nifty PSU Bank":          "Nifty PSU Bank",
    "Nifty Realty":            "Nifty Realty",
    "Nifty Serv Sector":       "Nifty Services Sector",
}
BENCHMARK = "Nifty 50"  # RP baseline and RS-line denominator

# ind_close_all columns: Index Name(0), Index Date(1), ..., Closing Index Value(5)
C_NAME, C_CLOSE = 0, 5

LOOKBACK_1M = 21     # trading sessions ~ 1 month
LOOKBACK_3M = 63     # ~ 3 months
LOOKBACK_6M = 126    # ~ 6 months
RS_LOOKBACK = 20     # sessions for RS momentum ("above where it sat 20 sessions ago")
RS_AVG = 50          # sessions for the RS line's own moving average (acceleration test)
TOP_N = 5            # "top-5 of ~17" leadership band (Stage 2)
READ_FILES = LOOKBACK_6M + 3

OUT_HEADER = [
    "sector", "rank", "ret_1m_pct", "ret_3m_pct", "ret_6m_pct",
    "rp_1m", "rp_3m", "rp_6m", "rp_score", "rs_mom_20d",
    "pct_off_6m_high", "accel", "quadrant", "stage2_pts",
]


def _date_key(p: Path):
    # ind_close_all_DDMMYYYY.csv — sort by (yyyy, mm, dd), never lexically.
    m = re.search(r"(\d{2})(\d{2})(\d{4})", p.stem)
    return (m.group(3), m.group(2), m.group(1)) if m else ("", "", "")


def sorted_index_files():
    return sorted(IDX_DIR.glob("*/ind_close_all_*.csv"), key=_date_key)


def month_dirname(m: int) -> str:
    return f"{m:02d}-{calendar.month_name[m]}"


def read_index_closes(paths, wanted: set):
    """Return closes[index_name] = [close per file, in date order] for wanted names."""
    closes = {name: [] for name in wanted}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            found = {}
            for row in reader:
                if len(row) <= C_CLOSE:
                    continue
                name = row[C_NAME].strip()
                if name in wanted and name not in found:
                    try:
                        found[name] = float(row[C_CLOSE].replace(",", ""))
                    except ValueError:
                        pass
        # append per file so all series stay index-aligned by date (None if absent)
        for name in wanted:
            closes[name].append(found.get(name))
    return closes


def pct_return(series, back):
    """% return over `back` sessions; None if history too short or endpoints missing."""
    if len(series) > back and series[-1] is not None and series[-1 - back] is not None:
        old = series[-1 - back]
        if old:
            return round((series[-1] / old - 1) * 100, 2)
    return None


def pct_off_high(series, window):
    """How far the latest close sits below the highest close in the last `window`
    valid sessions (0 = at a new high). None if no data."""
    valid = [x for x in series if x is not None]
    if not valid:
        return None
    cur, hi = valid[-1], max(valid[-window:])
    return round((hi - cur) / hi * 100, 1) if hi else None


def rs_line(sector_series, bench_series):
    """Sector ÷ benchmark per session; None where either side is missing."""
    return [
        (s / b) if (s is not None and b is not None and b) else None
        for s, b in zip(sector_series, bench_series)
    ]


def rs_metrics(rs):
    """(rs_mom_20d %, rs_accel Y/N) from the RS line. rs_accel = v4 Stage 2 test."""
    valid = [x for x in rs if x is not None]
    if len(rs) <= RS_LOOKBACK or rs[-1] is None:
        return None, "N"
    now, prior = rs[-1], rs[-1 - RS_LOOKBACK]
    mom = round((now / prior - 1) * 100, 2) if prior else None
    avg = statistics.fmean(valid[-RS_AVG:]) if len(valid) >= RS_AVG else (
        statistics.fmean(valid) if valid else None)
    accel = "Y" if (prior is not None and avg is not None and now > prior and now > avg) else "N"
    return mom, accel


def rp_star(rp):
    """Your RP star bands, on the 3-month Relative Performance."""
    if rp is None:
        return ""
    if rp > 15:
        return 5
    if rp >= 10:
        return 4
    if rp >= 5:
        return 3
    if rp >= 0:
        return 2
    return 1


def quadrant(rp_level, rs_mom):
    """RRG quadrant from RS level (ahead/behind Nifty) × RS momentum (rising/falling)."""
    if rp_level is None or rs_mom is None:
        return ""
    ahead, rising = rp_level >= 0, rs_mom > 0
    if ahead and rising:
        return "Leading"
    if ahead and not rising:
        return "Weakening"
    if not ahead and rising:
        return "Improving"
    return "Lagging"


def build_rows(closes):
    bench = closes.get(BENCHMARK, [])
    n1 = pct_return(bench, LOOKBACK_1M)
    n3 = pct_return(bench, LOOKBACK_3M)
    n6 = pct_return(bench, LOOKBACK_6M)

    def rp(sec, nifty):
        return None if (sec is None or nifty is None) else round(sec - nifty, 2)

    stats = []
    for label, idx_name in SECTORS.items():
        series = closes.get(idx_name, [])
        r1, r3, r6 = (pct_return(series, LOOKBACK_1M),
                      pct_return(series, LOOKBACK_3M),
                      pct_return(series, LOOKBACK_6M))
        rs_mom, rs_accel = rs_metrics(rs_line(series, bench))
        rp1, rp3, rp6 = rp(r1, n1), rp(r3, n3), rp(r6, n6)
        # RS level for the RRG axis: prefer 3M RP, fall back to 1M if 6-mo-young index
        level = rp3 if rp3 is not None else rp1
        off_hi = pct_off_high(series, LOOKBACK_6M)
        accel = "" if (r1 is None or r3 is None) else ("Y" if r1 > r3 / 3 else "N")
        stats.append({
            "sector": label, "r1": r1, "r3": r3, "r6": r6,
            "rp1": rp1, "rp3": rp3, "rp6": rp6, "level": level,
            "rs_mom": rs_mom, "rs_accel": rs_accel,
            "off_hi": off_hi, "accel": accel,
        })

    # Stage-2 leadership ranks are by raw return; the main rank is by 3M RP.
    def rank_map(key):
        ordered = sorted(stats, key=lambda s: (s[key] is not None, s[key] if s[key] is not None else -1e9), reverse=True)
        return {s["sector"]: i for i, s in enumerate(ordered, 1) if s[key] is not None}

    rk_ret1, rk_ret3 = rank_map("r1"), rank_map("r3")
    rk_rp3 = rank_map("level")  # main ranking: relative strength vs Nifty

    rows, missing = [], []
    for s in stats:
        main_rank = rk_rp3.get(s["sector"], "")
        if main_rank == "":
            missing.append(s["sector"])

        pts = 0
        if rk_ret1.get(s["sector"], 99) <= TOP_N:
            pts += 4
        if rk_ret3.get(s["sector"], 99) <= TOP_N:
            pts += 3
        if s["rs_accel"] == "Y":
            pts += 3

        rows.append({
            "sector": s["sector"],
            "rank": main_rank,
            "ret_1m_pct": "" if s["r1"] is None else s["r1"],
            "ret_3m_pct": "" if s["r3"] is None else s["r3"],
            "ret_6m_pct": "" if s["r6"] is None else s["r6"],
            "rp_1m": "" if s["rp1"] is None else s["rp1"],
            "rp_3m": "" if s["rp3"] is None else s["rp3"],
            "rp_6m": "" if s["rp6"] is None else s["rp6"],
            "rp_score": rp_star(s["rp3"]),
            "rs_mom_20d": "" if s["rs_mom"] is None else s["rs_mom"],
            "pct_off_6m_high": "" if s["off_hi"] is None else s["off_hi"],
            "accel": s["accel"],
            "quadrant": quadrant(s["level"], s["rs_mom"]),
            "stage2_pts": pts,
        })

    rows.sort(key=lambda r: (r["rank"] == "", r["rank"] if r["rank"] != "" else 1e9))
    return rows, missing


def main() -> int:
    ap = argparse.ArgumentParser(description="Rank the NSE sectoral indexes in SECTORS (RP + RRG + Stage 2).")
    ap.add_argument("--month", help="target journal month YYYY-MM (default: current month)")
    ap.add_argument("--out", type=Path, help="write to this path instead of the month's sectors.csv")
    args = ap.parse_args()

    files = sorted_index_files()
    if len(files) < LOOKBACK_1M + 2:
        print(f"ERROR: only {len(files)} index days archived; need > {LOOKBACK_1M + 1} for 1M returns.")
        print("Run: python source/archive_indices.py --from 2026-01-01")
        return 1
    have_6m = len(files) > LOOKBACK_6M
    files = files[-READ_FILES:]
    print(f"As-of index file: {files[-1].name}  ({len(files)} days loaded"
          f"{'' if have_6m else '; NOTE: < 126 days, so 6M columns are blank — backfill further'})\n")

    wanted = set(SECTORS.values()) | {BENCHMARK}
    closes = read_index_closes(files, wanted)
    if not any(closes.get(BENCHMARK, [])):
        print(f"ERROR: '{BENCHMARK}' not found in the index files — cannot compute RP/RS.")
        return 1

    rows, missing = build_rows(closes)

    if args.out:
        out_path = args.out
    else:
        if args.month:
            y, m = map(int, args.month.split("-"))
        else:
            t = date.today()
            y, m = t.year, t.month
        out_path = JOURNAL / str(y) / month_dirname(m) / "sectors.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_HEADER)
        w.writeheader()
        w.writerows(rows)

    # ---- report ----
    def by_quad(q):
        return [r["sector"] for r in rows if r["quadrant"] == q]

    print(f"{'sector':<20}{'1M%':>7}{'3M%':>7}{'RP3m':>7}{'RP*':>4}{'RSmom':>7}"
          f"{'%offHi':>8}{'acc':>4}  quadrant   s2")
    for r in rows:
        print(f"{r['sector']:<20}{str(r['ret_1m_pct']):>7}{str(r['ret_3m_pct']):>7}"
              f"{str(r['rp_3m']):>7}{str(r['rp_score']):>4}{str(r['rs_mom_20d']):>7}"
              f"{str(r['pct_off_6m_high']):>8}{r['accel']:>4}  "
              f"{r['quadrant']:<10}{r['stage2_pts']:>3}")

    print(f"\nLEADING   (buy first):        {', '.join(by_quad('Leading')) or '—'}")
    print(f"IMPROVING (next to lead):     {', '.join(by_quad('Improving')) or '—'}")
    print(f"WEAKENING (trim/tighten):     {', '.join(by_quad('Weakening')) or '—'}")
    print(f"LAGGING   (avoid):            {', '.join(by_quad('Lagging')) or '—'}")
    if missing:
        print(f"\nNo/short history (unranked):  {', '.join(missing)}")
    print(f"\nHunt for stocks inside the LEADING + IMPROVING sectors.")
    print(f"Written to {out_path.relative_to(REPO) if out_path.is_relative_to(REPO) else out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
