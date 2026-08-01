#!/usr/bin/env python3
"""
rank_stocks.py — bridge each watchlist stock to its ranked sector, then score
the v4 stages that are mechanically reachable from data already archived by
this pipeline: Stage 2 (Sector Rotation, a pure join off sectors.csv), Stage 5
(Institutional Activity, from bhavcopy volume/delivery), and Stage 6 (Relative
Strength, stock vs Nifty and stock vs its own sector).

THE BRIDGE PROBLEM this script exists to fix: watchlist.csv stores each stock's
sector as the exact NSE index name (e.g. "Nifty Financial Services"), while
sectors.csv (rank_sectors.py's output) keys its rows on the SECTORS dict's
FRIENDLY labels (e.g. "Nifty Fin Service") — a naive string join silently
fails for the sectors where those two diverge. Two watchlist labels (Cement,
Nifty Capital Goods) don't correspond to any of the 17 ranked indexes at all;
those stocks are scored on Stage 5 only and flagged, never hard-failed.

Stages 1/3/4/7/8/9 are NOT computed here — they need data or pattern-detection
logic this repo doesn't have yet (Nifty-EMA regime, Screener fundamentals,
mechanical chart-pattern recognition). Per the model's own missing-data rule
(CLAUDE.md: "never score missing as 0"), every stock's score is renormalized
over only the criteria/stages actually measured, and carries a stages_covered
+ score_conf confidence flag so a thin score is never mistaken for a strong one.

RVOL and 3-month-momentum are percentile-ranked against every LIQUID NSE EQ
symbol (median 20-day traded value > build_monthly.LIQUID_CR), not just the
watchlist — per CLAUDE.md's own invariant ("ranked by percentile across the
whole scanned universe"), so a mover outside the watchlist's 45 names can
still be reflected via a watchlist stock's rank against the real population.

Every liquid NSE EQ stock is also scored on Stages 5/6 directly, not just the
watchlist — but only watchlist stocks have a known sector (bridge_sectors
resolves watchlist.csv's labels; there's no sector data source for a random
NSE stock), so only they can pass the shortlist's Leading/Improving gate. A
non-watchlist stock with a strong score instead lands in discoveries.csv,
flagged as sector-unverified rather than silently dropped. universe.csv
(Bucket C) still only ever holds the watchlist's own 45 rows.

Pipeline position (third stage, after both of these have run this month):
    rank_sectors.py  -->  build_monthly.py  -->  rank_stocks.py
Reads that month's sectors.csv (stage2_pts/quadrant) and universe.csv
(ret_3m_pct/liquid from Bucket A) — hard-fails with a remedy message if either
is missing. Owns Bucket C (19 columns, see templates/monthly-universe-template.csv)
in universe.csv; never touches symbol/sector/Bucket A/Bucket B/tier.

Usage:
    python rank_stocks.py                  # this month, as-of the latest archives
    python rank_stocks.py --month 2026-07  # target a specific journal month

CAVEAT: the extended bhavcopy column indices below (HIGH/LOW/VOLUME/DELIV_PER)
are inferred from the standard NSE sec_bhavdata_full layout and the two
already-known indices (CLOSE=8, TURNOVER=11) — validate against one real
archived file before trusting (CLAUDE.md: "brittle if NSE changes the layout").
"""

import argparse
import csv
import math
import re
import statistics
from datetime import date
from pathlib import Path

from rank_sectors import (
    SECTORS, BENCHMARK, LOOKBACK_3M, RS_LOOKBACK, RS_AVG,
    rs_line, rs_metrics, pct_off_high, pct_return, month_dirname,
    sorted_index_files,
)
from rank_sectors import C_NAME as IDX_C_NAME, C_CLOSE as IDX_C_CLOSE
from build_monthly import (
    REPO, JOURNAL, UNIVERSE_TEMPLATE, LIQUID_CR, TURN_WINDOW,
    sorted_bhavcopies, load_watchlist, merge_universe,
)

# bhavcopy column indices (sec_bhavdata_full, standard layout) — see CAVEAT above.
C_SYMBOL, C_SERIES, C_HIGH, C_LOW, C_CLOSE, C_VOLUME, C_TURNOVER, C_DELIV = 0, 1, 5, 6, 8, 10, 11, 14

RVOL_WINDOW = 20        # sessions for the RVOL denominator (excludes today, see J4 in the plan)
DELIV_WINDOW = 20       # sessions for the delivery-surge denominator
PERSIST_WINDOW = 5      # last N sessions checked for volume-expansion persistence
PERSIST_AVG = 20        # sessions in each of those N sessions' own volume average
PERSIST_MIN = 3         # of PERSIST_WINDOW, need at least this many above-average
STRONG_CLOSE_MIN = 0.75 # close in the top 25% of the day's high-low range
DELIV_SURGE_MIN = 1.5   # today's delivery % vs its own 20-day average
RVOL_TIERS = ((0.05, 6), (0.10, 4), (0.20, 2))   # (percentile, points), nested bands
MOM_TIERS = ((0.20, 3),)                          # top 20% of universe by 3M return
LOOKBACK_52W = 252
NEAR_HIGH_PCT = 3.0     # "within 3% of the 52-week high" counts as a new high

STAGE_NOMINAL = {2: 10, 5: 15, 6: 15}
V4_TOTAL_STAGES = 9
# Confidence bands on pts_available. Tuned against today's practical ceiling of 37
# (52-week-high, 3 pts, is normally unavailable until the archive reaches 252
# sessions) — the true ceiling is 40 and these bands loosen in meaning as the
# archive deepens; retune once 52-week data is routinely available.
CONF_HIGH, CONF_MED = 34, 27

SHORTLIST_N = 15
SHORTLIST_QUADRANTS = ("Leading", "Improving")
SHORTLIST_HEADER = ("symbol", "sector", "quadrant", "score_100",
                     "stage2_pts", "stage5_pts", "stage6_pts",
                     "stages_covered", "score_conf", "liquid")

# Non-watchlist liquid stocks with a strong Stage 5/6 score but no sector
# mapping (see module docstring / bridge_sectors) -- can't pass the sector
# gate above, so they get their own file instead of silently vanishing.
DISCOVERY_N = 30
DISCOVERY_HEADER = ("symbol", "score_100", "stage5_pts", "stage6_pts",
                     "stages_covered", "score_conf", "rvol", "deliv_surge", "mom_pctile")

# Minimum sessions to consider a stock scoreable at all, and the RS-criterion
# availability gate (RS_AVG's own moving average + RS_LOOKBACK's back-reference).
MIN_SESSIONS = RS_AVG + RS_LOOKBACK + 1
READ_FILES = LOOKBACK_52W + 3   # read enough that the 52w criterion self-activates

# RVOL/momentum percentile pool: every liquid NSE EQ symbol, not just the
# watchlist (CLAUDE.md: "ranked by percentile across the whole scanned
# universe"). Only needs a 3-month window (RS/52w history is watchlist-only).
UNIVERSE_READ_FILES = LOOKBACK_3M + 2

# Watchlist sector labels known to have no NSE sectoral index at all — only
# changes the warning's wording (typo vs. genuinely untracked), never behaviour.
KNOWN_UNTRACKED = {"Cement", "Nifty Capital Goods"}

BUCKET_C = (
    "sector_canon", "sector_rank", "sector_quadrant", "stage2_pts",
    "rvol", "rvol_pts", "deliv_surge", "vol_persist", "close_range_pct", "stage5_pts",
    "rs_nifty", "rs_sector", "mom_pctile", "stage6_pts",
    "score_pts", "pts_available", "score_100", "stages_covered", "score_conf",
)


def _date_key(p: Path):
    m = re.search(r"(\d{2})(\d{2})(\d{4})", p.stem)
    return (m.group(3), m.group(2), m.group(1)) if m else ("", "", "")


# ---------------------------------------------------------------- sector bridge

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


_BY_NORM = {}
for _key, _val in SECTORS.items():
    _BY_NORM[_norm(_val)] = _key
    _BY_NORM.setdefault(_norm(_key), _key)


def canonical_sector(label: str):
    """SECTORS dict key for a raw watchlist sector label, or None if untracked.
    Matches both watchlist's form (exact NSE index name, the dict VALUE) and
    sectors.csv's form (the friendly label, the dict KEY)."""
    return _BY_NORM.get(_norm(label))


def read_sectors_csv(path: Path):
    """Return {sector_key: {"rank", "quadrant", "stage2_pts"}}."""
    table = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sec = (row.get("sector") or "").strip()
            if not sec:
                continue
            try:
                pts = float(row.get("stage2_pts"))
            except (TypeError, ValueError):
                pts = 0.0
            table[sec] = {
                "rank": row.get("rank") or "",
                "quadrant": row.get("quadrant") or "",
                "stage2_pts": pts,
            }
    return table


def bridge_sectors(watch, sector_table):
    """watch: list[(symbol, raw_sector_label)]. Returns (canon_by_symbol, unmapped)
    where canon_by_symbol[sym] is a SECTORS key or None, and unmapped is
    {"untracked": {label: [symbols]}, "not_in_sectors_csv": {label: [symbols]}}."""
    canon_by_symbol = {}
    unmapped = {"untracked": {}, "not_in_sectors_csv": {}}
    for sym, label in watch:
        key = canonical_sector(label)
        if key is None:
            canon_by_symbol[sym] = None
            unmapped["untracked"].setdefault(label, []).append(sym)
        elif key not in sector_table:
            canon_by_symbol[sym] = None
            unmapped["not_in_sectors_csv"].setdefault(label, []).append(sym)
        else:
            canon_by_symbol[sym] = key
    return canon_by_symbol, unmapped


# --------------------------------------------------------------------- readers

def read_ohlcv(paths, wanted: set):
    """Read bhavcopy files (date order) once. Returns bars[sym] = {"dates": [...],
    "close"/"high"/"low"/"vol"/"deliv": [...]} — parallel lists, EQ series only,
    deduped within a file, appended only for files where the symbol appears
    (so a symbol's lists stay internally date-consistent even if it's absent
    from some files). deliv entries are None where DELIV_PER is blank/"-"."""
    bars = {}
    for path in paths:
        dk = _date_key(path)
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            seen = set()
            for row in reader:
                if len(row) <= C_DELIV:
                    continue
                if row[C_SERIES].strip() != "EQ":
                    continue
                sym = row[C_SYMBOL].strip()
                if sym not in wanted or sym in seen:
                    continue
                seen.add(sym)
                try:
                    close = float(row[C_CLOSE])
                    high = float(row[C_HIGH])
                    low = float(row[C_LOW])
                    vol = float(row[C_VOLUME])
                except ValueError:
                    continue
                try:
                    deliv = float(row[C_DELIV].strip())
                except ValueError:
                    deliv = None
                b = bars.setdefault(sym, {"dates": [], "close": [], "high": [], "low": [], "vol": [], "deliv": []})
                b["dates"].append(dk)
                b["close"].append(close)
                b["high"].append(high)
                b["low"].append(low)
                b["vol"].append(vol)
                b["deliv"].append(deliv)
    return bars


def read_index_closes_dated(paths, wanted: set):
    """Return {index_name: {date_key: close}} — sparse, keyed by our own
    _date_key so a stock's bhavcopy dates can be intersected against an
    index's archived dates even when the two archives cover different ranges."""
    out = {name: {} for name in wanted}
    for path in paths:
        dk = _date_key(path)
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            found = set()
            for row in reader:
                if len(row) <= IDX_C_CLOSE:
                    continue
                name = row[IDX_C_NAME].strip()
                if name in wanted and name not in found:
                    try:
                        out[name][dk] = float(row[IDX_C_CLOSE].replace(",", ""))
                    except ValueError:
                        pass
                    found.add(name)
    return out


def read_universe(path: Path):
    """Return {symbol: {"ret_3m_pct": float|None, "liquid": "Y"/"N"/""}} from
    that month's universe.csv (Bucket A, written by build_monthly.py)."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            if not sym:
                continue
            try:
                r3 = float(row.get("ret_3m_pct"))
            except (TypeError, ValueError):
                r3 = None
            out[sym] = {"ret_3m_pct": r3, "liquid": (row.get("liquid") or "").strip()}
    return out


def write_shortlist(path: Path, shortlist, universe):
    """Write the printed Buy Watchlist (Leading/Improving sectors, top
    SHORTLIST_N by score_100) to its own CSV so it survives past the console,
    same rows/order as the §4 printout."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SHORTLIST_HEADER)
        for r in shortlist:
            w.writerow([
                r["symbol"], r["sector_canon"], r["sector_quadrant"], r["score_100"],
                r["stage2_pts"], r["stage5_pts"], r["stage6_pts"],
                r["stages_covered"], r["score_conf"],
                universe.get(r["symbol"], {}).get("liquid") or "",
            ])


def write_discoveries(path: Path, discoveries):
    """Write the top-scoring non-watchlist liquid stocks -- sector unknown, so
    they can't pass the shortlist's Leading/Improving gate, but a strong
    Stage 5/6 score is still worth a manual look (research the sector by
    hand before acting)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(DISCOVERY_HEADER)
        for r in discoveries:
            w.writerow([
                r["symbol"], r["score_100"], r["stage5_pts"], r["stage6_pts"],
                r["stages_covered"], r["score_conf"],
                r["rvol"], r["deliv_surge"], r["mom_pctile"],
            ])


def read_universe_pool(paths):
    """Read every EQ symbol's close/volume/turnover from bhavcopy (unfiltered,
    unlike read_ohlcv's watchlist-only scope) -- the raw material for the
    RVOL/momentum percentile POPULATION. No dates/high/low/deliv needed here
    (no RS alignment, no 52-week test at this scope), so this is far cheaper
    per-symbol than read_ohlcv despite covering ~2000 symbols instead of ~45."""
    closes, vols, turns = {}, {}, {}
    for path in paths:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            seen = set()
            for row in reader:
                if len(row) <= C_TURNOVER:
                    continue
                if row[C_SERIES].strip() != "EQ":
                    continue
                sym = row[C_SYMBOL].strip()
                if sym in seen:
                    continue
                seen.add(sym)
                try:
                    close = float(row[C_CLOSE])
                    vol = float(row[C_VOLUME])
                    turn = float(row[C_TURNOVER]) / 100.0  # lakh -> crore
                except ValueError:
                    continue
                closes.setdefault(sym, []).append(close)
                vols.setdefault(sym, []).append(vol)
                turns.setdefault(sym, []).append(turn)
    return closes, vols, turns


def build_universe_pool(paths):
    """RVOL and 3-month-momentum values for every LIQUID NSE EQ symbol (median
    20-day traded value > LIQUID_CR, the same gate build_monthly.py uses) --
    the percentile-ranking population. Illiquid names are excluded from the
    pool so "top 5%" stays a meaningful bar rather than trivial to clear among
    thousands of thinly-traded tickers. Returns (rvol_pool, mom_pool,
    total_scanned, liquid_syms) -- liquid_syms is every symbol that cleared
    the gate (the full-universe scoring candidate set), len() gives liquid_n."""
    closes, vols, turns = read_universe_pool(paths)
    rvol_pool, mom_pool, liquid_syms = {}, {}, set()
    for sym, vol in vols.items():
        tvals = turns.get(sym, [])[-TURN_WINDOW:]
        if not tvals or statistics.median(tvals) <= LIQUID_CR:
            continue
        liquid_syms.add(sym)
        if len(vol) >= RVOL_WINDOW + 1:
            prior = vol[-(RVOL_WINDOW + 1):-1]
            avg = statistics.fmean(prior)
            if avg:
                rvol_pool[sym] = round(vol[-1] / avg, 2)
        r3 = pct_return(closes.get(sym, []), LOOKBACK_3M)
        if r3 is not None:
            mom_pool[sym] = r3
    return rvol_pool, mom_pool, len(vols), liquid_syms


def rs_against(dates, closes, date_close_map):
    """Align a stock's (dates, closes) against an index's {date: close} map;
    returns two same-length lists over the date intersection, in date order."""
    a, b = [], []
    for d, c in zip(dates, closes):
        if d in date_close_map:
            a.append(c)
            b.append(date_close_map[d])
    return a, b


# --------------------------------------------------------------- percentiles

def rank_percentile_points(values: dict, tiers):
    """values: {sym: float}. tiers: iterable of (pct, pts) — nested bands OK
    (a stock in the top 5% also satisfies top 10%/20%; the best tier wins).
    Cutoff per tier is ceil(pct * n) (generous: guarantees at least one award
    even in a tiny universe). Symbols absent from `values` are omitted."""
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ordered)
    out = {}
    for i, (sym, _) in enumerate(ordered, start=1):
        pts = 0
        for pct, p in tiers:
            if i <= math.ceil(pct * n):
                pts = max(pts, p)
        out[sym] = pts
    return out


def percentile_rank(values: dict):
    """values: {sym: float}. Returns {sym: 0-100 percentile, 1dp} — diagnostic
    only (mom_pctile column), not itself a scoring input."""
    ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ordered)
    if n == 0:
        return {}
    if n == 1:
        return {ordered[0][0]: 100.0}
    return {sym: round((n - 1 - i) / (n - 1) * 100, 1) for i, (sym, _) in enumerate(ordered)}


# -------------------------------------------------------------------- stages

def stage5_raw(b):
    """Stage 5 (Institutional Activity) raw diagnostics for one symbol's bar
    history (chronological). Each metric is None if there isn't enough data."""
    close, high, low, vol, deliv = b["close"], b["high"], b["low"], b["vol"], b["deliv"]
    out = {"rvol": None, "deliv_surge": None, "vol_persist": None, "close_range_pct": None}

    if len(vol) >= RVOL_WINDOW + 1:
        prior = vol[-(RVOL_WINDOW + 1):-1]
        avg = statistics.fmean(prior)
        if avg:
            out["rvol"] = round(vol[-1] / avg, 2)

    if deliv and deliv[-1] is not None:
        prior_valid = [x for x in deliv[-(DELIV_WINDOW + 1):-1] if x is not None]
        if len(prior_valid) >= DELIV_WINDOW:
            avg = statistics.fmean(prior_valid)
            if avg:
                out["deliv_surge"] = round(deliv[-1] / avg, 2)

    if len(vol) >= PERSIST_WINDOW + PERSIST_AVG:
        count = 0
        for offset in range(-PERSIST_WINDOW, 0):
            idx = len(vol) + offset
            window = vol[idx - PERSIST_AVG:idx]
            if len(window) < PERSIST_AVG:
                continue
            if vol[idx] > statistics.fmean(window):
                count += 1
        out["vol_persist"] = count

    if high and low and high[-1] > low[-1]:
        out["close_range_pct"] = round((close[-1] - low[-1]) / (high[-1] - low[-1]) * 100, 1)

    return out


def stage5_score(raw5, rvol_pts):
    earned = available = 0
    if raw5["rvol"] is not None:
        available += 6
        earned += rvol_pts or 0
    if raw5["deliv_surge"] is not None:
        available += 4
        if raw5["deliv_surge"] > DELIV_SURGE_MIN:
            earned += 4
    if raw5["vol_persist"] is not None:
        available += 3
        if raw5["vol_persist"] >= PERSIST_MIN:
            earned += 3
    if raw5["close_range_pct"] is not None:
        available += 2
        if raw5["close_range_pct"] >= STRONG_CLOSE_MIN * 100:
            earned += 2
    return earned, available


def stage6_raw(dates, closes, nifty_map, sector_map):
    """Stage 6 (Relative Strength) raw diagnostics. sector_map is None when the
    stock's sector didn't bridge to a tracked index — rs_sector_ok stays None
    (unavailable), never a false "N"."""
    rs_n_a, rs_n_b = rs_against(dates, closes, nifty_map)
    rs_nifty = rs_line(rs_n_a, rs_n_b)
    out = {"rs_nifty_ok": None, "rs_sector_ok": None, "at_52w_high": None,
           "short_52w": len(closes) < LOOKBACK_52W}

    if len(rs_nifty) >= MIN_SESSIONS and rs_nifty[-1] is not None:
        _, accel = rs_metrics(rs_nifty)
        off3 = pct_off_high(rs_nifty, LOOKBACK_3M)
        out["rs_nifty_ok"] = bool(accel == "Y" and off3 is not None and off3 <= 0.0)

    if sector_map is not None:
        rs_s_a, rs_s_b = rs_against(dates, closes, sector_map)
        rs_sector = rs_line(rs_s_a, rs_s_b)
        if len(rs_sector) >= MIN_SESSIONS and rs_sector[-1] is not None:
            _, accel = rs_metrics(rs_sector)
            out["rs_sector_ok"] = (accel == "Y")

    if not out["short_52w"]:
        off52 = pct_off_high(closes, LOOKBACK_52W)
        out["at_52w_high"] = off52 is not None and off52 <= NEAR_HIGH_PCT

    return out


def stage6_score(raw6, mom_pts, mom_available):
    earned = available = 0
    if raw6["rs_nifty_ok"] is not None:
        available += 5
        if raw6["rs_nifty_ok"]:
            earned += 5
    if raw6["rs_sector_ok"] is not None:
        available += 4
        if raw6["rs_sector_ok"]:
            earned += 4
    if not raw6["short_52w"]:
        available += 3
        if raw6["at_52w_high"]:
            earned += 3
    if mom_available:
        available += 3
        earned += mom_pts or 0
    return earned, available


def stage2_score(sec_row):
    if sec_row is None:
        return 0.0, 0
    return sec_row["stage2_pts"], 10


def renormalize(earned, available, nominal):
    return 0.0 if available == 0 else earned / available * nominal


def compose(e2, a2, e5, a5, e6, a6):
    """Renormalize each covered stage onto its nominal weight, then project the
    sum onto a 0-100 scale using only the criteria actually measured. Never
    scores a missing stage/criterion as zero (CLAUDE.md's stated invariant).
    Returns the renormalized per-stage scores too (s5/s6 -- what stage5_pts/
    stage6_pts show; NOT the same as raw earned points once any criterion in
    that stage is unavailable)."""
    s2 = renormalize(e2, a2, STAGE_NOMINAL[2])
    s5 = renormalize(e5, a5, STAGE_NOMINAL[5])
    s6 = renormalize(e6, a6, STAGE_NOMINAL[6])
    score_pts = round(s2 + s5 + s6, 1)
    pts_available = a2 + a5 + a6
    raw_earned = e2 + e5 + e6
    score_100 = round(raw_earned / pts_available * 100, 1) if pts_available else 0.0
    stages_covered = sum(1 for a in (a2, a5, a6) if a > 0)
    if pts_available >= CONF_HIGH:
        conf = "HIGH"
    elif pts_available >= CONF_MED:
        conf = "MED"
    else:
        conf = "LOW"
    return (round(s5, 1), round(s6, 1), score_pts, pts_available, score_100,
            f"{stages_covered}/{V4_TOTAL_STAGES}", conf)


def build_rows(candidate_syms, bars, idx_dated, sector_table, canon_by_symbol, universe, insufficient,
                rvol_pool, mom_pool):
    """candidate_syms: every symbol to score -- the watchlist plus (once widened)
    every other liquid NSE stock. canon_by_symbol only has entries for watchlist
    symbols (from bridge_sectors); .get() naturally returns None for everyone
    else, so a non-watchlist candidate flows through exactly like a watchlist
    stock whose sector didn't bridge -- Stage 2 and RS-vs-sector renormalize
    out, never a crash or a false zero."""
    raw5, raw6, mom_values = {}, {}, {}
    nifty_map = idx_dated.get(BENCHMARK, {})

    for sym in candidate_syms:
        if sym in insufficient or sym not in bars:
            continue
        b = bars[sym]
        raw5[sym] = stage5_raw(b)
        sector_key = canon_by_symbol.get(sym)
        sector_map = idx_dated.get(SECTORS[sector_key]) if sector_key else None
        raw6[sym] = stage6_raw(b["dates"], b["close"], nifty_map, sector_map)
        r3 = universe.get(sym, {}).get("ret_3m_pct")
        if r3 is None:
            r3 = mom_pool.get(sym)  # non-watchlist candidates have no universe.csv row at all
        if r3 is not None:
            mom_values[sym] = r3

    rvol_values = {sym: r["rvol"] for sym, r in raw5.items() if r["rvol"] is not None}
    # Rank against the full liquid-universe pool, not just these candidates'
    # own values -- a freshly-computed value wins over any near-duplicate
    # already in the pool (dict union: later keys override).
    rvol_pts_by_sym = rank_percentile_points({**rvol_pool, **rvol_values}, RVOL_TIERS)
    combined_mom = {**mom_pool, **mom_values}
    mom_pts_by_sym = rank_percentile_points(combined_mom, MOM_TIERS)
    mom_pctile_by_sym = percentile_rank(combined_mom)

    scored, any_52w_short = {}, False
    for sym in candidate_syms:
        if sym not in raw5:
            continue
        sector_key = canon_by_symbol.get(sym)
        sec_row = sector_table.get(sector_key) if sector_key else None

        e2, a2 = stage2_score(sec_row)
        e5, a5 = stage5_score(raw5[sym], rvol_pts_by_sym.get(sym))
        e6, a6 = stage6_score(raw6[sym], mom_pts_by_sym.get(sym), sym in combined_mom)
        if raw6[sym]["short_52w"]:
            any_52w_short = True

        stage5_pts, stage6_pts, score_pts, pts_available, score_100, stages_covered, conf = \
            compose(e2, a2, e5, a5, e6, a6)

        scored[sym] = {
            "symbol": sym,
            "sector_canon": sector_key or "",
            "sector_rank": sec_row["rank"] if sec_row else "",
            "sector_quadrant": sec_row["quadrant"] if sec_row else "",
            "stage2_pts": sec_row["stage2_pts"] if sec_row else "",
            "rvol": "" if raw5[sym]["rvol"] is None else raw5[sym]["rvol"],
            "rvol_pts": rvol_pts_by_sym.get(sym, "") if raw5[sym]["rvol"] is not None else "",
            "deliv_surge": "" if raw5[sym]["deliv_surge"] is None else raw5[sym]["deliv_surge"],
            "vol_persist": "" if raw5[sym]["vol_persist"] is None else raw5[sym]["vol_persist"],
            "close_range_pct": "" if raw5[sym]["close_range_pct"] is None else raw5[sym]["close_range_pct"],
            "stage5_pts": stage5_pts if a5 else "",
            "rs_nifty": "" if raw6[sym]["rs_nifty_ok"] is None else ("Y" if raw6[sym]["rs_nifty_ok"] else "N"),
            "rs_sector": "" if raw6[sym]["rs_sector_ok"] is None else ("Y" if raw6[sym]["rs_sector_ok"] else "N"),
            "mom_pctile": mom_pctile_by_sym.get(sym, ""),
            "stage6_pts": stage6_pts if a6 else "",
            "score_pts": score_pts,
            "pts_available": pts_available,
            "score_100": score_100,
            "stages_covered": stages_covered,
            "score_conf": conf,
        }

    return scored, any_52w_short


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bridge watchlist stocks to their ranked sector; score v4 Stages 2, 5, 6.")
    ap.add_argument("--month", help="target journal month YYYY-MM (default: current month)")
    args = ap.parse_args()

    if args.month:
        y, m = map(int, args.month.split("-"))
    else:
        t = date.today()
        y, m = t.year, t.month
    month_str = f"{y}-{m:02d}"
    month_dir = JOURNAL / str(y) / month_dirname(m)
    sectors_path = month_dir / "sectors.csv"
    universe_path = month_dir / "universe.csv"

    if not sectors_path.exists():
        print(f"ERROR: {sectors_path} not found for {month_str} "
              f"-- run: python source/rank_sectors.py --month {month_str}")
        return 1
    if not universe_path.exists():
        print(f"ERROR: {universe_path} not found for {month_str} "
              f"-- run: python source/build_monthly.py --month {month_str}")
        return 1

    bhav_files = sorted_bhavcopies()
    idx_files = sorted_index_files()
    if len(bhav_files) < MIN_SESSIONS:
        print(f"ERROR: only {len(bhav_files)} bhavcopy sessions archived; need >= {MIN_SESSIONS}.")
        print("Bhavcopy has no backfill -- it accrues nightly via archive_bhavcopy.py.")
        return 1
    if not idx_files:
        print("ERROR: no index files archived -- run: python source/archive_indices.py --from <YYYY-MM-DD>")
        return 1

    watch = load_watchlist()
    if not watch:
        print("ERROR: watchlist.csv has no usable rows.")
        return 1

    sector_table = read_sectors_csv(sectors_path)
    canon_by_symbol, unmapped = bridge_sectors(watch, sector_table)
    universe = read_universe(universe_path)

    symbols = {sym for sym, _ in watch}

    # Full-universe candidate set: every liquid NSE EQ stock, not just the
    # watchlist -- so a mover you haven't hand-picked can still surface (in
    # discoveries.csv; the sector-gated shortlist stays watchlist-only, see
    # docs/stock-scoring-reference.md). Built before the OHLCV read so that
    # read covers everyone in one pass.
    universe_read = bhav_files[-UNIVERSE_READ_FILES:]
    rvol_pool, mom_pool, total_scanned, liquid_syms = build_universe_pool(universe_read)
    liquid_n = len(liquid_syms)
    extra_syms = liquid_syms - symbols
    full_candidates = symbols | extra_syms

    bhav_read = bhav_files[-READ_FILES:]
    bars = read_ohlcv(bhav_read, full_candidates)

    mapped_keys = {k for k in canon_by_symbol.values() if k is not None}
    wanted_idx = {SECTORS[k] for k in mapped_keys} | {BENCHMARK}
    idx_read = idx_files[-READ_FILES:]
    idx_dated = read_index_closes_dated(idx_read, wanted_idx)

    # Coarse pre-filter stays watchlist-only (unchanged reporting/behavior);
    # extra candidates rely on build_rows' per-criterion length checks plus
    # its own "sym not in bars" guard instead of this blanket MIN_SESSIONS cut.
    insufficient = [sym for sym, _ in watch
                    if sym not in bars or len(bars[sym]["close"]) < MIN_SESSIONS]
    if len(insufficient) == len(watch):
        print("ERROR: no watchlist symbol has enough bhavcopy history to score "
              f"(need >= {MIN_SESSIONS} sessions).")
        return 1

    scored, any_52w_short = build_rows(full_candidates, bars, idx_dated, sector_table, canon_by_symbol, universe,
                                        insufficient, rvol_pool, mom_pool)
    rows = [scored[sym] for sym, _ in watch if sym in scored]  # watchlist only, watch order preserved
    discoveries = [scored[sym] for sym in extra_syms if sym in scored]
    # Every watchlist symbol must survive the merge, even ones we couldn't score
    # (merge_universe only writes rows it's given -- an omitted symbol would
    # otherwise vanish from universe.csv instead of just keeping blank Bucket C).
    # Extra (non-watchlist) candidates never touch universe.csv -- it stays the
    # watchlist's own hand-maintained sheet, per CLAUDE.md.
    all_rows = [scored[sym] if sym in scored else {"symbol": sym} for sym, _ in watch]

    # ---- §1 Data coverage ----
    print(f"As-of bhavcopy: {bhav_read[-1].name}  ({len(bhav_read)} days loaded)")
    print(f"As-of index:    {idx_read[-1].name}  ({len(idx_read)} days loaded)")
    print(f"Liquid-universe pool: {liquid_n}/{total_scanned} NSE EQ symbols pass the "
          f">{LIQUID_CR:.0f} Cr liquidity gate (last {len(universe_read)} sessions) "
          f"-- RVOL/momentum percentiles ranked against this pool.\n")
    if insufficient:
        print(f"Insufficient history (<{MIN_SESSIONS} sessions), not scored: {', '.join(insufficient)}\n")

    # ---- §2 Sector bridge ----
    mapped_n = sum(1 for v in canon_by_symbol.values() if v is not None)
    print(f"Sector bridge: mapped {mapped_n}/{len(watch)} watchlist stocks across {len(mapped_keys)} ranked sectors\n")

    if unmapped["untracked"]:
        total = sum(len(v) for v in unmapped["untracked"].values())
        print(f"WARNING: {len(unmapped['untracked'])} sector label(s) ({total} stocks) have no ranked index "
              f"-- Stage 2 and RS-vs-sector left blank:")
        for label, syms in unmapped["untracked"].items():
            reason = ("no NSE sector index tracked in rank_sectors.SECTORS" if label in KNOWN_UNTRACKED
                       else "not in rank_sectors.SECTORS -- check spelling")
            print(f"   {label} ({len(syms)} stocks: {', '.join(syms)})")
            print(f"      {reason}")
        print()
    if unmapped["not_in_sectors_csv"]:
        print(f"WARNING: {len(unmapped['not_in_sectors_csv'])} sector(s) map to a tracked index "
              f"but have no row in this month's sectors.csv:")
        for label, syms in unmapped["not_in_sectors_csv"].items():
            print(f"   {label} ({len(syms)} stocks: {', '.join(syms)}) "
                  f"-- rerun: python source/rank_sectors.py --month {month_str}")
        print()

    # ---- §3 Scoring coverage ----
    low_conf = [r["symbol"] for r in rows if r["score_conf"] == "LOW"]
    print(f"Scored {len(rows)}/{len(watch)} stocks.")
    if any_52w_short:
        print(f"NOTE: 52-week-high criterion unavailable -- {len(bhav_read)} sessions archived, "
              f"need {LOOKBACK_52W}. Stage 6 renormalizes over the remaining 12 pts until then.")
    if low_conf:
        print(f"LOW confidence (few stages covered): {', '.join(low_conf)}")
    print()

    # ---- §4 Buy Watchlist ----
    shortlist = sorted(
        (r for r in rows if r["sector_quadrant"] in SHORTLIST_QUADRANTS),
        key=lambda r: r["score_100"], reverse=True)[:SHORTLIST_N]
    print(f"Buy Watchlist (Leading/Improving sectors, top {SHORTLIST_N} by score_100):")
    print(f"{'symbol':<12}{'sector':<20}{'quad':<11}{'score':>7}{'s2':>5}{'s5':>6}{'s6':>6}{'cov':>6}  conf")
    for r in shortlist:
        illiquid = " (illiquid)" if universe.get(r["symbol"], {}).get("liquid") == "N" else ""
        print(f"{r['symbol']:<12}{r['sector_canon']:<20}{r['sector_quadrant']:<11}"
              f"{r['score_100']:>7}{str(r['stage2_pts']):>5}{str(r['stage5_pts']):>6}{str(r['stage6_pts']):>6}"
              f"{r['stages_covered']:>6}  {r['score_conf']}{illiquid}")
    print()

    shortlist_path = month_dir / "shortlist.csv"
    write_shortlist(shortlist_path, shortlist, universe)

    # ---- §5 Discoveries (non-watchlist, sector unknown) ----
    # Require BOTH implemented stages to contribute (stage6_pts non-blank) --
    # without a sector, 2/9 is the ceiling here, so this is the bar that
    # actually distinguishes a real candidate from a lone Stage-5 spike (a
    # single fully-earned stage can otherwise renormalize to a misleading
    # score_100 = 100.0 on almost no evidence).
    top_discoveries = sorted(
        (r for r in discoveries if r["pts_available"] > 0 and r["stage6_pts"] != ""),
        key=lambda r: r["score_100"], reverse=True)[:DISCOVERY_N]
    print(f"Discoveries (non-watchlist liquid stocks, sector unverified, top {DISCOVERY_N} by score_100):")
    if top_discoveries:
        print(f"{'symbol':<12}{'score':>7}{'s5':>6}{'s6':>6}{'cov':>6}  conf")
        for r in top_discoveries:
            print(f"{r['symbol']:<12}{r['score_100']:>7}{str(r['stage5_pts']):>6}{str(r['stage6_pts']):>6}"
                  f"{r['stages_covered']:>6}  {r['score_conf']}")
    else:
        print("  (none scored)")
    print()

    discoveries_path = month_dir / "discoveries.csv"
    write_discoveries(discoveries_path, top_discoveries)

    # ---- merge into universe.csv (Bucket C, merge-don't-clobber) ----
    with open(UNIVERSE_TEMPLATE, newline="", encoding="utf-8") as f:
        uni_header = next(csv.reader(f))
    n = merge_universe(universe_path, uni_header, all_rows, owned=BUCKET_C, always=("symbol",))

    untracked_n = sum(len(v) for v in unmapped["untracked"].values())
    shortlist_sectors = len({r["sector_canon"] for r in shortlist})
    print(f"RESULT: scored {len(rows)}/{len(watch)} watchlist stocks, {untracked_n} unmapped-sector, "
          f"shortlist {len(shortlist)} name(s) from {shortlist_sectors} sector(s); "
          f"{len(discoveries)}/{len(extra_syms)} non-watchlist liquid stocks scored, "
          f"{len(top_discoveries)} discoveries.")
    print(f"Written to {universe_path.relative_to(REPO)} ({n} rows, Bucket C columns).")
    print(f"Written to {shortlist_path.relative_to(REPO)} ({len(shortlist)} rows).")
    print(f"Written to {discoveries_path.relative_to(REPO)} ({len(top_discoveries)} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
