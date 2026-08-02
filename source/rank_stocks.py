#!/usr/bin/env python3
"""
rank_stocks.py — bridge each watchlist stock to its ranked sector, then score
the v4 stages that are mechanically reachable from data already archived by
this pipeline: Stage 2 (Sector Rotation, a pure join off sectors.csv), Stage 5
(Institutional Activity, from bhavcopy volume/delivery), Stage 6 (Relative
Strength, stock vs Nifty and stock vs its own sector), Stage 7 (Accumulation
Structure — volatility contraction, volume dry-up, tight base, and quiet
delivery accumulation — the pre-breakout "about to move" signature), and
Stage 8 (Breakout/Entry — Appendix A's six mechanical Zanger patterns, the
actual trigger).

THE BRIDGE PROBLEM this script exists to fix: watchlist.csv stores each stock's
sector as the exact NSE index name (e.g. "Nifty Financial Services"), while
sectors.csv (rank_sectors.py's output) keys its rows on the SECTORS dict's
FRIENDLY labels (e.g. "Nifty Fin Service") — a naive string join silently
fails for the sectors where those two diverge. A watchlist label that doesn't
correspond to any of the 41 tracked indexes (SECTORS in rank_sectors.py) is
scored on Stages 5/7/8 only and flagged, never hard-failed.

Stages 1/3/4/9 are NOT computed here — they need data this repo doesn't have
yet (Nifty-EMA regime, Screener fundamentals). Per the model's own
missing-data rule (CLAUDE.md: "never score missing as 0"), every stock's
score is renormalized over only the criteria/stages actually measured, and
carries a stages_covered + score_conf confidence flag so a thin score is
never mistaken for a strong one. Two criteria specifically need history
deeper than currently archived and stay unavailable rather than faked on a
shorter window: Stage 6's 52-week-high (252 sessions) and Stage 7's
volatility-contraction (ATR_LOOKBACK + ATR_WINDOW = 136 sessions). Stage 8's
overhead-supply criterion needs the same 252 sessions as Stage 6.

Stage 8 is a deliberate EXCEPTION to the missing-data rule: per Zanger Rule
#1, "no qualifying pattern = zero, regardless of the other stages" — so once
there's enough history to have checked all six Appendix-A patterns at all
(MIN_STAGE8_SESSIONS), a stock that clears none of them gets a real,
fully-available zero on the whole stage, not a renormalized-away blank. Only
genuinely too-short history makes Stage 8 unavailable.

RVOL and 3-month-momentum are percentile-ranked against every LIQUID NSE EQ
symbol (median 20-day traded value > build_monthly.LIQUID_CR), not just the
watchlist — per CLAUDE.md's own invariant ("ranked by percentile across the
whole scanned universe"), so a mover outside the watchlist's 45 names can
still be reflected via a watchlist stock's rank against the real population.

Every liquid NSE EQ stock is also scored on Stages 5/6/7/8 directly, not just
the watchlist — but only watchlist stocks have a known sector (bridge_sectors
resolves watchlist.csv's labels; there's no sector data source for a random
NSE stock), so only they can pass the shortlist's Leading/Improving gate. A
non-watchlist stock with a strong score instead lands in discoveries.csv,
flagged as sector-unverified rather than silently dropped. universe.csv
(Bucket C) still only ever holds the watchlist's own 45 rows.

Pipeline position (third stage, after both of these have run this month):
    rank_sectors.py  -->  build_monthly.py  -->  rank_stocks.py
Reads that month's sectors.csv (stage2_pts/quadrant) and universe.csv
(ret_3m_pct/liquid from Bucket A) — hard-fails with a remedy message if either
is missing. Owns Bucket C (31 columns, see templates/monthly-universe-template.csv)
in universe.csv; never touches symbol/sector/Bucket A/Bucket B/tier.

Usage:
    python rank_stocks.py                  # this month, as-of the latest archives
    python rank_stocks.py --month 2026-07  # target a specific journal month
    python rank_stocks.py --stages 2,5,6   # exclude Stages 7/8 for comparison; writes
                                            # shortlist_2-5-6.csv / discoveries_2-5-6.csv
                                            # instead of the canonical files, and never
                                            # touches universe.csv (see IMPLEMENTED_STAGES)

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
    SECTORS, BENCHMARK, LOOKBACK_3M, LOOKBACK_6M, RS_LOOKBACK, RS_AVG,
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

# Stage 7 (Accumulation Structure) constants.
ATR_WINDOW = 10          # sessions averaged into the ATR itself
ATR_LOOKBACK = LOOKBACK_6M   # 126 sessions -- the "its own 6-month range" for the percentile
ATR_CONTRACTION_QUARTILE = 0.25   # "bottom quartile" of that range
VOL_DRYUP_RECENT = 20    # recent window ("20-day average volume")
VOL_DRYUP_PRIOR = 50     # prior, non-overlapping window ("the prior 50-day average")
VOL_DRYUP_MAX = 0.7      # recent must be < this fraction of prior
TIGHT_BASE_WINDOW = 20
TIGHT_BASE_MAX_PCT = 15.0   # "20-day high-to-low range < 15%"

# Stage 8 (Breakout/Entry) constants. Appendix A calls these "starting
# thresholds -- tune against your own backtest"; treat every number below the
# same way. SWING_WINDOW sessions on each side define a local high/low, so a
# swing point is never confirmable in the most recent SWING_WINDOW sessions.
SWING_WINDOW = 3
BREAKOUT_VOL_MULT = 1.5      # Zanger Rule #8: breakout-day volume >= 1.5x the 50-day average
BREAKOUT_VOL_WINDOW = 50
OVERHEAD_LOOKBACK = LOOKBACK_52W   # "in the last 12 months"
OVERHEAD_PCT = 10.0           # "within 10% above the pivot"
PRIOR_UPTREND_LOOKBACK = 20   # sessions checked for "prior uptrend" (Flat Base / Ascending Triangle)
PRIOR_UPTREND_MIN_PCT = 20.0  # starting threshold; Cup and Handle uses its own (30%, per spec)

FLATBASE_WINDOW = 25          # >= 5 weeks
FLATBASE_MAX_PCT = 15.0

ASC_TRI_WINDOW = 40
ASC_TRI_TOUCH_TOL_PCT = 2.0   # swing highs within this tolerance count as the "same" resistance
ASC_TRI_MIN_TOUCHES = 2

DBOT_WINDOW = 60
DBOT_TOL_PCT = 4.0
DBOT_MIN_GAP = 5              # sessions the two lows must be separated by (the "rebound")
DBOT_MIN_REBOUND_PCT = 15.0   # rebound peak must clear the low by at least this much -- a real "W", not noise

CUP_MIN_SESSIONS, CUP_MAX_SESSIONS = 7, 65   # per spec text, literally in sessions
CUP_DEPTH_MIN, CUP_DEPTH_MAX = 12.0, 35.0
CUP_HANDLE_FRACTION = 0.25    # last quarter of the cup window is checked as the handle
CUP_HANDLE_MAX_DEPTH = 12.0
CUP_PRIOR_UPTREND_PCT = 30.0
CUP_ROUNDED_MIN_SESSIONS = 3  # >= this many sessions within 5% of the cup low (not a single V-spike)
CUP_ROUNDED_TOL_PCT = 5.0

HTF_POLE_MAX_SESSIONS = 40    # <= 8 weeks
HTF_POLE_MIN_SESSIONS = 10
HTF_POLE_MIN_PCT = 80.0
HTF_FLAG_MAX_SESSIONS = 25    # <= 5 weeks
HTF_FLAG_MIN_SESSIONS = 5
HTF_FLAG_MIN_PCT, HTF_FLAG_MAX_PCT = 10.0, 25.0

TREND_WINDOW = 60
TREND_TOL_PCT = 2.0           # swing highs within this tolerance of the level count as a "rejection"
TREND_MIN_REJECTIONS = 3

# Shortest history any single pattern needs -- below this, Stage 8 is
# genuinely unavailable (missing data). At or above it, a stock that clears
# no pattern still gets a real, available zero (Zanger Rule #1), not a blank.
MIN_STAGE8_SESSIONS = FLATBASE_WINDOW + PRIOR_UPTREND_LOOKBACK

IMPLEMENTED_STAGES = (2, 5, 6, 7, 8)
STAGE_NOMINAL = {2: 10, 5: 15, 6: 15, 7: 10, 8: 15}
V4_TOTAL_STAGES = 9
# Confidence bands on pts_available. Tuned against today's practical ceiling of
# 59 (10+15+12+7 from Stages 2/5/6/7, as before, + 15 from Stage 8). Stage 8's
# full 15 is usually available even today: per Zanger Rule #1, a stock that
# clears NO pattern still gets a real, fully-available zero -- only when a
# pattern actually fires does overhead-supply (needs 252 sessions) or
# follow-through (only ever available the single session after a breakout)
# reduce it. The true ceiling is 65 once 52-week and 6-month-ATR history are
# both routinely available; retune again then.
CONF_HIGH, CONF_MED = 54, 43

SHORTLIST_QUADRANTS = ("Leading", "Improving")
SHORTLIST_HEADER = ("symbol", "sector", "quadrant", "score_100",
                     "stage2_pts", "stage5_pts", "stage6_pts", "stage7_pts", "stage8_pts",
                     "pattern", "pivot",
                     "stages_covered", "score_conf", "liquid")

# Non-watchlist liquid stocks with a strong Stage 5/6 score but no sector
# mapping (see module docstring / bridge_sectors) -- can't pass the sector
# gate above, so they get their own file instead of silently vanishing.
DISCOVERY_N = 30
DISCOVERY_HEADER = ("symbol", "score_100", "stage5_pts", "stage6_pts", "stage7_pts", "stage8_pts",
                     "pattern", "stages_covered", "score_conf", "rvol", "deliv_surge", "mom_pctile")

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
    "vol_contraction", "vol_dryup", "tight_base", "quiet_accum", "stage7_pts",
    "pattern", "pivot", "vol_confirm", "close_above_pivot", "follow_through",
    "no_overhead_supply", "stage8_pts",
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
    """Write the printed Buy Watchlist (every Leading/Improving-sector
    watchlist stock, sorted by score_100 -- not truncated to a top-N: a
    stock Stage 8 couldn't find a pattern on is scored lower, per Zanger
    Rule #1, but must stay visible here for manual chart review, not get
    cut off the list) to its own CSV so it survives past the console, same
    rows/order as the §4 printout."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(SHORTLIST_HEADER)
        for r in shortlist:
            w.writerow([
                r["symbol"], r["sector_canon"], r["sector_quadrant"], r["score_100"],
                r["stage2_pts"], r["stage5_pts"], r["stage6_pts"], r["stage7_pts"], r["stage8_pts"],
                r["pattern"], r["pivot"],
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
                r["symbol"], r["score_100"], r["stage5_pts"], r["stage6_pts"], r["stage7_pts"], r["stage8_pts"],
                r["pattern"], r["stages_covered"], r["score_conf"],
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


def true_range(high, low, close):
    """True Range per session from index 1 onward (needs the prior close);
    length = len(high) - 1, aligned to high/low/close[1:]."""
    tr = []
    for i in range(1, len(high)):
        pc = close[i - 1]
        tr.append(max(high[i] - low[i], abs(high[i] - pc), abs(low[i] - pc)))
    return tr


def atr_pct_series(high, low, close, window=ATR_WINDOW):
    """Rolling `window`-session ATR as a % of that session's close (simple
    average of True Range, not Wilder's smoothing -- a starting threshold per
    v4 Appendix A's own convention, tune against a backtest). Aligned 1:1 to
    close[window:] (each ATR needs `window` prior TRs, each needing a prior
    close, so the first `window` sessions have no value)."""
    tr = true_range(high, low, close)
    out = []
    for i in range(window - 1, len(tr)):
        atr = statistics.fmean(tr[i - window + 1:i + 1])
        c = close[i + 1]   # tr[i] is the TR ending at close[i+1]
        out.append(atr / c * 100 if c else None)
    return out


def volatility_contraction(high, low, close):
    """Stage 7 criterion 1: is today's ATR_WINDOW-session ATR% in the bottom
    ATR_CONTRACTION_QUARTILE of its own ATR_LOOKBACK-session history? None
    (unavailable, not False) until ATR_LOOKBACK + ATR_WINDOW sessions exist --
    same "don't fake a shorter window" policy as the 52-week-high criterion."""
    needed = ATR_LOOKBACK + ATR_WINDOW
    if len(close) < needed:
        return None
    series = atr_pct_series(high[-needed:], low[-needed:], close[-needed:])
    series = [v for v in series if v is not None]
    if len(series) < ATR_LOOKBACK or series[-1] is None:
        return None
    today = series[-1]
    rank = sum(1 for v in series if v <= today) / len(series)
    return rank <= ATR_CONTRACTION_QUARTILE


def volume_dryup(vol):
    """Stage 7 criterion 2: is the recent VOL_DRYUP_RECENT-session average
    volume below VOL_DRYUP_MAX of the PRIOR (non-overlapping)
    VOL_DRYUP_PRIOR-session average? None if not enough history."""
    needed = VOL_DRYUP_RECENT + VOL_DRYUP_PRIOR
    if len(vol) < needed:
        return None
    recent = statistics.fmean(vol[-VOL_DRYUP_RECENT:])
    prior = statistics.fmean(vol[-needed:-VOL_DRYUP_RECENT])
    if not prior:
        return None
    return recent < VOL_DRYUP_MAX * prior


def tight_base(high, low):
    """Stage 7 criterion 3: is the TIGHT_BASE_WINDOW-session high-to-low range
    < TIGHT_BASE_MAX_PCT of the window's low? Returns (is_tight, base_high,
    base_low) -- the latter two feed quiet_accumulation's breakout check;
    all None if not enough history."""
    if len(high) < TIGHT_BASE_WINDOW or len(low) < TIGHT_BASE_WINDOW:
        return None, None, None
    h = max(high[-TIGHT_BASE_WINDOW:])
    l = min(low[-TIGHT_BASE_WINDOW:])
    if not l:
        return None, None, None
    return ((h - l) / l * 100 < TIGHT_BASE_MAX_PCT), h, l


def quiet_accumulation(deliv, close, base_high):
    """Stage 7 criterion 4: delivery-% trend rising (Appendix B4's simpler
    5-day-vs-20-day-average proxy) while price hasn't already broken out of
    its own base. None if delivery history or the base itself is unavailable."""
    if base_high is None:
        return None
    window = [x for x in deliv[-20:] if x is not None]
    recent = [x for x in deliv[-5:] if x is not None]
    if len(window) < 20 or not recent:
        return None
    trend_rising = statistics.fmean(recent) > statistics.fmean(window)
    still_in_base = close[-1] < base_high
    return trend_rising and still_in_base


def stage7_raw(b):
    """Stage 7 (Accumulation Structure) raw diagnostics for one symbol's bar
    history (chronological). Each metric is None if there isn't enough data."""
    close, high, low, vol, deliv = b["close"], b["high"], b["low"], b["vol"], b["deliv"]
    base_ok, base_high, _ = tight_base(high, low)
    return {
        "vol_contraction": volatility_contraction(high, low, close),
        "vol_dryup": volume_dryup(vol),
        "tight_base": base_ok,
        "quiet_accum": quiet_accumulation(deliv, close, base_high),
    }


def stage7_score(raw7):
    earned = available = 0
    if raw7["vol_contraction"] is not None:
        available += 3
        if raw7["vol_contraction"]:
            earned += 3
    if raw7["vol_dryup"] is not None:
        available += 3
        if raw7["vol_dryup"]:
            earned += 3
    if raw7["tight_base"] is not None:
        available += 2
        if raw7["tight_base"]:
            earned += 2
    if raw7["quiet_accum"] is not None:
        available += 2
        if raw7["quiet_accum"]:
            earned += 2
    return earned, available


# --------------------------------------------------------- Stage 8 patterns

def swing_idx(values, window=SWING_WINDOW, kind="high"):
    """Indices where `values[i]` is a local max/min within +-window sessions.
    A swing point can never be confirmed in the most recent `window`
    sessions (needs confirmation from both sides) -- by design, "today"
    itself is never a swing point."""
    idxs = []
    for i in range(window, len(values) - window):
        seg = values[i - window:i + window + 1]
        if kind == "high" and values[i] == max(seg):
            idxs.append(i)
        elif kind == "low" and values[i] == min(seg):
            idxs.append(i)
    return idxs


def _prior_uptrend_ok(close, window, lookback, min_pct):
    """Did price rise >= min_pct over `lookback` sessions immediately before
    the most recent `window`-session pattern window? None if not enough
    history to check."""
    need = window + lookback
    if len(close) < need:
        return None
    pre = close[-need:-window]
    if not pre or not pre[0]:
        return None
    return (pre[-1] / pre[0] - 1) * 100 >= min_pct


def detect_flat_base(high, low, close, vol):
    """Appendix A: Flat Base -- prior uptrend, sideways range <=15% deep for
    >=5 weeks (25 sessions), volume contracting. pivot = range top."""
    need = FLATBASE_WINDOW + PRIOR_UPTREND_LOOKBACK
    if len(close) < need:
        return None
    top, bot = max(high[-FLATBASE_WINDOW:]), min(low[-FLATBASE_WINDOW:])
    if not bot:
        return None
    depth = (top - bot) / bot * 100
    prior_uptrend = _prior_uptrend_ok(close, FLATBASE_WINDOW, PRIOR_UPTREND_LOOKBACK, PRIOR_UPTREND_MIN_PCT)
    if prior_uptrend is None:
        return None
    base_vol = statistics.fmean(vol[-FLATBASE_WINDOW:])
    pre_vol = statistics.fmean(vol[-need:-FLATBASE_WINDOW])
    vol_contracting = bool(pre_vol and base_vol < pre_vol)
    detected = bool(prior_uptrend and depth <= FLATBASE_MAX_PCT and vol_contracting)
    conviction = max(0.0, (FLATBASE_MAX_PCT - depth) / FLATBASE_MAX_PCT) if detected else 0.0
    return {"detected": detected, "pivot": top, "conviction": conviction}


def detect_ascending_triangle(high, low, close, vol):
    """Appendix A: Ascending Triangle -- prior uptrend, >=2 touches of a flat
    resistance, rising swing lows into it, volume contracting on approach.
    pivot = the resistance."""
    need = ASC_TRI_WINDOW + PRIOR_UPTREND_LOOKBACK
    if len(close) < need:
        return None
    h_win, v_win = high[-ASC_TRI_WINDOW:], vol[-ASC_TRI_WINDOW:]
    l_win = low[-ASC_TRI_WINDOW:]
    highs_idx = swing_idx(h_win, kind="high")
    lows_idx = swing_idx(l_win, kind="low")
    if len(highs_idx) < ASC_TRI_MIN_TOUCHES or len(lows_idx) < 2:
        return None
    resistance = max(h_win[i] for i in highs_idx)
    if not resistance:
        return None
    touches = sum(1 for i in highs_idx if (resistance - h_win[i]) / resistance * 100 <= ASC_TRI_TOUCH_TOL_PCT)
    lows_seq = [l_win[i] for i in lows_idx]
    rising_lows = all(b > a for a, b in zip(lows_seq, lows_seq[1:]))
    prior_uptrend = _prior_uptrend_ok(close, ASC_TRI_WINDOW, PRIOR_UPTREND_LOOKBACK, PRIOR_UPTREND_MIN_PCT)
    if prior_uptrend is None:
        return None
    vol_contracting = statistics.fmean(v_win[-10:]) < statistics.fmean(v_win)
    detected = bool(touches >= ASC_TRI_MIN_TOUCHES and rising_lows and prior_uptrend and vol_contracting)
    conviction = touches / len(highs_idx) if detected else 0.0
    return {"detected": detected, "pivot": resistance, "conviction": conviction}


def detect_double_bottom(high, low, close, vol):
    """Appendix A: Double Bottom -- two swing lows within ~4% of each other,
    separated by a genuine rebound (>= DBOT_MIN_REBOUND_PCT, not just any two
    nearby local minima -- without this, two of a window's several similarly-
    deep swing lows are common by chance, not a real "W"), second holding
    at/above the first. pivot = the rebound peak between them. Anchored on
    the window's single deepest swing low (the primary bottom), not searched
    across every pair of the deepest few -- a stricter, less permissive match."""
    if len(close) < DBOT_WINDOW:
        return None
    h_win, l_win = high[-DBOT_WINDOW:], low[-DBOT_WINDOW:]
    lows_idx = swing_idx(l_win, kind="low")
    if len(lows_idx) < 2:
        return None
    first = min(lows_idx, key=lambda i: l_win[i])   # the window's single deepest swing low
    low_a = l_win[first]
    if not low_a:
        return None
    best = None
    for j in lows_idx:
        if j == first or abs(j - first) < DBOT_MIN_GAP:
            continue
        low_b = l_win[j]
        if abs(low_a - low_b) / low_a * 100 > DBOT_TOL_PCT:
            continue
        if low_b < low_a * (1 - DBOT_TOL_PCT / 100):   # second must hold at/above the first
            continue
        a, b = sorted((first, j))
        peak = max(h_win[a:b + 1])
        if (peak / low_a - 1) * 100 < DBOT_MIN_REBOUND_PCT:
            continue
        conviction = 1 - abs(low_a - low_b) / low_a
        if best is None or conviction > best["conviction"]:
            best = {"detected": True, "pivot": peak, "conviction": conviction}
    return best if best is not None else {"detected": False, "pivot": None, "conviction": 0.0}


def detect_cup_and_handle(high, low, close, vol):
    """Appendix A: Cup and Handle -- prior uptrend >=30%, a rounded (not V)
    base of 7-65 sessions with 12-35% depth, a handle in the upper half of
    the cup with <12% depth on below-average volume. pivot = handle high.
    Uses the full CUP_MAX_SESSIONS window (the spec's upper bound) rather
    than searching every length in [7, 65] -- a starting simplification."""
    need = CUP_MAX_SESSIONS + PRIOR_UPTREND_LOOKBACK
    if len(close) < need:
        return None
    window = CUP_MAX_SESSIONS
    cup_high, cup_low, cup_vol = high[-window:], low[-window:], vol[-window:]
    left_high = cup_high[0]
    cup_low_val = min(cup_low)
    if not left_high:
        return None
    depth = (left_high - cup_low_val) / left_high * 100
    if not (CUP_DEPTH_MIN <= depth <= CUP_DEPTH_MAX):
        return {"detected": False, "pivot": None, "conviction": 0.0}
    near_low = sum(1 for v in cup_low if v <= cup_low_val * (1 + CUP_ROUNDED_TOL_PCT / 100))
    rounded = near_low >= CUP_ROUNDED_MIN_SESSIONS   # not a single V-spike
    prior_uptrend = _prior_uptrend_ok(close, window, PRIOR_UPTREND_LOOKBACK, CUP_PRIOR_UPTREND_PCT)
    if prior_uptrend is None:
        return None
    handle_len = max(3, int(window * CUP_HANDLE_FRACTION))
    handle_high, handle_low, handle_vol = cup_high[-handle_len:], cup_low[-handle_len:], cup_vol[-handle_len:]
    h_top, h_bot = max(handle_high), min(handle_low)
    if not h_top:
        return {"detected": False, "pivot": None, "conviction": 0.0}
    handle_depth = (h_top - h_bot) / h_top * 100
    handle_in_upper_half = h_bot >= cup_low_val + (left_high - cup_low_val) * 0.5
    handle_vol_ok = statistics.fmean(handle_vol) < statistics.fmean(cup_vol)
    detected = bool(rounded and prior_uptrend and handle_depth < CUP_HANDLE_MAX_DEPTH
                    and handle_in_upper_half and handle_vol_ok)
    conviction = max(0.0, (CUP_HANDLE_MAX_DEPTH - handle_depth) / CUP_HANDLE_MAX_DEPTH) if detected else 0.0
    return {"detected": detected, "pivot": h_top, "conviction": conviction}


def detect_high_tight_flag(high, low, close, vol):
    """Appendix A: High Tight Flag (rare, highest conviction when formed) --
    a flagpole >=80% gain in <=8 weeks (40 sessions) on above-average volume,
    then a shallow 10-25% pullback over <=5 weeks (25 sessions) with volume
    contracting. pivot = flag high. Searches pole/flag lengths within the
    spec's ranges for any qualifying split (a small, cheap nested search)."""
    if len(close) < HTF_POLE_MAX_SESSIONS + HTF_FLAG_MAX_SESSIONS:
        return None
    avg_vol_all = statistics.fmean(vol)
    best = None
    for flag_len in range(HTF_FLAG_MIN_SESSIONS, HTF_FLAG_MAX_SESSIONS + 1):
        f_top, f_bot = max(high[-flag_len:]), min(low[-flag_len:])
        if not f_top:
            continue
        pullback = (f_top - f_bot) / f_top * 100
        if not (HTF_FLAG_MIN_PCT <= pullback <= HTF_FLAG_MAX_PCT):
            continue
        flag_vol = statistics.fmean(vol[-flag_len:])
        if not flag_vol < avg_vol_all:
            continue
        for pole_len in range(HTF_POLE_MIN_SESSIONS, HTF_POLE_MAX_SESSIONS + 1):
            start = -(flag_len + pole_len)
            if -start > len(close):
                continue
            pole_start, pole_end = close[start], close[-flag_len - 1]
            if not pole_start:
                continue
            gain = (pole_end / pole_start - 1) * 100
            if gain < HTF_POLE_MIN_PCT:
                continue
            pole_vol = vol[start:-flag_len]
            if not (pole_vol and statistics.fmean(pole_vol) > avg_vol_all):
                continue
            conviction = gain / 100
            if best is None or conviction > best["conviction"]:
                best = {"detected": True, "pivot": f_top, "conviction": conviction}
    return best if best is not None else {"detected": False, "pivot": None, "conviction": 0.0}


def detect_trendline_breakout(high, low, close, vol):
    """Appendix A: Trendline / Resistance Breakout -- simplified to a flat
    horizontal level with >=3 rejections (a true descending-trendline fit
    would need linear regression through the touches; this is the starting,
    cheaper mechanical proxy). pivot = the level."""
    if len(close) < TREND_WINDOW:
        return None
    h_win = high[-TREND_WINDOW:]
    highs_idx = swing_idx(h_win, kind="high")
    if len(highs_idx) < TREND_MIN_REJECTIONS:
        return None
    level = max(h_win[i] for i in highs_idx)
    if not level:
        return None
    rejections = sum(1 for i in highs_idx if (level - h_win[i]) / level * 100 <= TREND_TOL_PCT)
    detected = rejections >= TREND_MIN_REJECTIONS
    conviction = rejections / len(highs_idx) if detected else 0.0
    return {"detected": bool(detected), "pivot": level, "conviction": conviction}


PATTERN_DETECTORS = (
    ("Cup and Handle", detect_cup_and_handle),
    ("High Tight Flag", detect_high_tight_flag),
    ("Ascending Triangle", detect_ascending_triangle),
    ("Flat Base", detect_flat_base),
    ("Double Bottom", detect_double_bottom),
    ("Trendline/Resistance Breakout", detect_trendline_breakout),
)


def select_pattern(high, low, close, vol):
    """Run all six Appendix-A detectors. Returns (name, pivot, evaluable).
    evaluable=False only when EVERY detector lacked enough history (Stage 8
    genuinely unavailable). Among fired patterns, picks the highest
    `conviction` -- "the single most clearly formed," never averaged
    (Zanger Rule #1)."""
    evaluable = False
    best_name, best = None, None
    for name, fn in PATTERN_DETECTORS:
        result = fn(high, low, close, vol)
        if result is None:
            continue
        evaluable = True
        if result["detected"] and (best is None or result["conviction"] > best["conviction"]):
            best_name, best = name, result
    if best is None:
        return None, None, evaluable
    return best_name, best["pivot"], evaluable


def breakout_diagnostics(close, vol, pivot):
    """Stage 8 criteria 2-4 given a detected pattern's pivot. follow_through
    is None (deferred, not failed) except on the single session right after
    a breakout crossing -- per spec, only ever scoreable at T+1."""
    vol_confirm = None
    if len(vol) >= BREAKOUT_VOL_WINDOW + 1:
        avg = statistics.fmean(vol[-(BREAKOUT_VOL_WINDOW + 1):-1])
        if avg:
            vol_confirm = vol[-1] >= BREAKOUT_VOL_MULT * avg

    close_above_pivot = (close[-1] > pivot) if pivot else None

    follow_through = None
    if pivot and len(close) >= 3:
        crossed_today = close[-1] > pivot and close[-2] <= pivot
        crossed_yesterday = close[-2] > pivot and close[-3] <= pivot
        if crossed_yesterday and not crossed_today:
            follow_through = close[-1] > pivot

    return vol_confirm, close_above_pivot, follow_through


def overhead_supply_check(high, pivot):
    """Stage 8 criterion 5: no prior swing high within OVERHEAD_PCT above the
    pivot in the last OVERHEAD_LOOKBACK (12-month) sessions. None until that
    much history is archived."""
    if pivot is None or len(high) < OVERHEAD_LOOKBACK:
        return None
    zone_top = pivot * (1 + OVERHEAD_PCT / 100)
    has_supply = any(pivot < h <= zone_top for h in high[-OVERHEAD_LOOKBACK:])
    return not has_supply


def stage8_raw(b):
    """Stage 8 (Breakout/Entry) raw diagnostics for one symbol's bar history."""
    close, high, low, vol = b["close"], b["high"], b["low"], b["vol"]
    pattern, pivot, evaluable = select_pattern(high, low, close, vol)
    out = {"evaluable": evaluable, "pattern": pattern or "", "pivot": pivot,
           "vol_confirm": None, "close_above_pivot": None, "follow_through": None,
           "no_overhead_supply": None}
    if pattern is not None:
        out["vol_confirm"], out["close_above_pivot"], out["follow_through"] = \
            breakout_diagnostics(close, vol, pivot)
        out["no_overhead_supply"] = overhead_supply_check(high, pivot)
    return out


def stage8_score(raw8):
    """Zanger Rule #1: no qualifying pattern is a real, fully-available zero
    (not missing data) once there's enough history to have checked at all."""
    if not raw8["evaluable"]:
        return 0, 0
    if not raw8["pattern"]:
        return 0, 15
    earned, available = 6, 6   # the pattern itself: detected = automatic 6 of 6
    if raw8["vol_confirm"] is not None:
        available += 3
        if raw8["vol_confirm"]:
            earned += 3
    if raw8["close_above_pivot"] is not None:
        available += 2
        if raw8["close_above_pivot"]:
            earned += 2
    if raw8["follow_through"] is not None:
        available += 2
        if raw8["follow_through"]:
            earned += 2
    if raw8["no_overhead_supply"] is not None:
        available += 2
        if raw8["no_overhead_supply"]:
            earned += 2
    return earned, available


def stage2_score(sec_row):
    if sec_row is None:
        return 0.0, 0
    return sec_row["stage2_pts"], 10


def renormalize(earned, available, nominal):
    return 0.0 if available == 0 else earned / available * nominal


def compose(e2, a2, e5, a5, e6, a6, e7, a7, e8, a8):
    """Renormalize each covered stage onto its nominal weight, then project the
    sum onto a 0-100 scale using only the criteria actually measured. Never
    scores a missing stage/criterion as zero (CLAUDE.md's stated invariant) --
    except Stage 8's "no pattern" case, which is a real, fully-available zero
    by design (Zanger Rule #1), not missing data. Returns the renormalized
    per-stage scores too (s5/s6/s7/s8 -- what stageN_pts show; NOT the same as
    raw earned points once any criterion in that stage is unavailable)."""
    s2 = renormalize(e2, a2, STAGE_NOMINAL[2])
    s5 = renormalize(e5, a5, STAGE_NOMINAL[5])
    s6 = renormalize(e6, a6, STAGE_NOMINAL[6])
    s7 = renormalize(e7, a7, STAGE_NOMINAL[7])
    s8 = renormalize(e8, a8, STAGE_NOMINAL[8])
    score_pts = round(s2 + s5 + s6 + s7 + s8, 1)
    pts_available = a2 + a5 + a6 + a7 + a8
    raw_earned = e2 + e5 + e6 + e7 + e8
    score_100 = round(raw_earned / pts_available * 100, 1) if pts_available else 0.0
    stages_covered = sum(1 for a in (a2, a5, a6, a7, a8) if a > 0)
    if pts_available >= CONF_HIGH:
        conf = "HIGH"
    elif pts_available >= CONF_MED:
        conf = "MED"
    else:
        conf = "LOW"
    return (round(s5, 1), round(s6, 1), round(s7, 1), round(s8, 1), score_pts, pts_available, score_100,
            f"{stages_covered}/{V4_TOTAL_STAGES}", conf)


def build_rows(candidate_syms, bars, idx_dated, sector_table, canon_by_symbol, universe, insufficient,
                rvol_pool, mom_pool, enabled_stages=IMPLEMENTED_STAGES):
    """candidate_syms: every symbol to score -- the watchlist plus (once widened)
    every other liquid NSE stock. canon_by_symbol only has entries for watchlist
    symbols (from bridge_sectors); .get() naturally returns None for everyone
    else, so a non-watchlist candidate flows through exactly like a watchlist
    stock whose sector didn't bridge -- Stage 2 and RS-vs-sector renormalize
    out, never a crash or a false zero."""
    raw5, raw6, raw7, raw8, mom_values = {}, {}, {}, {}, {}
    nifty_map = idx_dated.get(BENCHMARK, {})

    for sym in candidate_syms:
        if sym in insufficient or sym not in bars:
            continue
        b = bars[sym]
        raw5[sym] = stage5_raw(b)
        sector_key = canon_by_symbol.get(sym)
        sector_map = idx_dated.get(SECTORS[sector_key]) if sector_key else None
        raw6[sym] = stage6_raw(b["dates"], b["close"], nifty_map, sector_map)
        raw7[sym] = stage7_raw(b)
        raw8[sym] = stage8_raw(b)
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
        e7, a7 = stage7_score(raw7[sym])
        e8, a8 = stage8_score(raw8[sym])
        if raw6[sym]["short_52w"]:
            any_52w_short = True

        # --stages: a disabled stage contributes nothing to the composite,
        # exactly as if it were unmeasured -- raw diagnostic columns below
        # (rvol, pattern, etc.) stay populated regardless, only the scored
        # contribution disappears.
        if 2 not in enabled_stages:
            e2, a2 = 0, 0
        if 5 not in enabled_stages:
            e5, a5 = 0, 0
        if 6 not in enabled_stages:
            e6, a6 = 0, 0
        if 7 not in enabled_stages:
            e7, a7 = 0, 0
        if 8 not in enabled_stages:
            e8, a8 = 0, 0

        stage5_pts, stage6_pts, stage7_pts, stage8_pts, score_pts, pts_available, score_100, stages_covered, conf = \
            compose(e2, a2, e5, a5, e6, a6, e7, a7, e8, a8)

        r8 = raw8[sym]
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
            "vol_contraction": "" if raw7[sym]["vol_contraction"] is None else ("Y" if raw7[sym]["vol_contraction"] else "N"),
            "vol_dryup": "" if raw7[sym]["vol_dryup"] is None else ("Y" if raw7[sym]["vol_dryup"] else "N"),
            "tight_base": "" if raw7[sym]["tight_base"] is None else ("Y" if raw7[sym]["tight_base"] else "N"),
            "quiet_accum": "" if raw7[sym]["quiet_accum"] is None else ("Y" if raw7[sym]["quiet_accum"] else "N"),
            "stage7_pts": stage7_pts if a7 else "",
            "pattern": r8["pattern"],
            "pivot": "" if r8["pivot"] is None else round(r8["pivot"], 2),
            "vol_confirm": "" if r8["vol_confirm"] is None else ("Y" if r8["vol_confirm"] else "N"),
            "close_above_pivot": "" if r8["close_above_pivot"] is None else ("Y" if r8["close_above_pivot"] else "N"),
            "follow_through": "" if r8["follow_through"] is None else ("Y" if r8["follow_through"] else "N"),
            "no_overhead_supply": "" if r8["no_overhead_supply"] is None else ("Y" if r8["no_overhead_supply"] else "N"),
            "stage8_pts": stage8_pts if a8 else "",
            "score_pts": score_pts,
            "pts_available": pts_available,
            "score_100": score_100,
            "stages_covered": stages_covered,
            "score_conf": conf,
        }

    return scored, any_52w_short


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bridge watchlist stocks to their ranked sector; score v4 Stages 2, 5, 6, 7, 8.")
    ap.add_argument("--month", help="target journal month YYYY-MM (default: current month)")
    ap.add_argument("--stages", default=",".join(str(s) for s in IMPLEMENTED_STAGES),
                     help="comma-separated stage numbers to include, e.g. '2,5,6' to exclude the "
                          "less-validated Stages 7/8 (default: all implemented, "
                          f"{','.join(str(s) for s in IMPLEMENTED_STAGES)}). A restricted set writes "
                          "shortlist/discoveries to suffixed filenames instead of the canonical ones, "
                          "and never touches universe.csv -- Bucket C always reflects the full stage set.")
    args = ap.parse_args()

    try:
        enabled_stages = {int(s) for s in args.stages.split(",") if s.strip()}
    except ValueError:
        print(f"ERROR: --stages must be comma-separated integers, got: {args.stages!r}")
        return 1
    unknown = enabled_stages - set(IMPLEMENTED_STAGES)
    if unknown or not enabled_stages:
        print(f"ERROR: --stages must be a non-empty subset of {IMPLEMENTED_STAGES}, "
              f"got: {sorted(enabled_stages) or '(empty)'}"
              + (f" -- unknown: {sorted(unknown)}" if unknown else ""))
        return 1
    is_full_stages = enabled_stages == set(IMPLEMENTED_STAGES)
    stage_suffix = "" if is_full_stages else "_" + "-".join(str(s) for s in sorted(enabled_stages))

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
                                        insufficient, rvol_pool, mom_pool, enabled_stages)
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
          f"-- RVOL/momentum percentiles ranked against this pool.")
    if not is_full_stages:
        print(f"Restricted --stages {sorted(enabled_stages)} -- output goes to suffixed files, "
              f"universe.csv (Bucket C) will NOT be updated this run.")
    print()
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
    # Every Leading/Improving watchlist stock, not just a top-N cutoff: a
    # Stage 8 "no pattern" zero (Zanger Rule #1) pushes a stock DOWN this
    # list, but must never remove it -- it's still worth a manual chart
    # check, just not yet at a mechanical entry trigger.
    shortlist = sorted(
        (r for r in rows if r["sector_quadrant"] in SHORTLIST_QUADRANTS),
        key=lambda r: r["score_100"], reverse=True)
    print(f"Buy Watchlist (Leading/Improving sectors, {len(shortlist)} stocks, by score_100):")
    print(f"{'symbol':<12}{'sector':<20}{'quad':<11}{'score':>7}{'s2':>5}{'s5':>6}{'s6':>6}{'s7':>6}{'s8':>6}"
          f"{'cov':>6}  conf  pattern")
    for r in shortlist:
        illiquid = " (illiquid)" if universe.get(r["symbol"], {}).get("liquid") == "N" else ""
        print(f"{r['symbol']:<12}{r['sector_canon']:<20}{r['sector_quadrant']:<11}"
              f"{r['score_100']:>7}{str(r['stage2_pts']):>5}{str(r['stage5_pts']):>6}{str(r['stage6_pts']):>6}"
              f"{str(r['stage7_pts']):>6}{str(r['stage8_pts']):>6}{r['stages_covered']:>6}  {r['score_conf']}"
              f"  {r['pattern']}{illiquid}")
    print()

    shortlist_path = month_dir / f"shortlist{stage_suffix}.csv"
    write_shortlist(shortlist_path, shortlist, universe)

    # ---- §5 Discoveries (non-watchlist, sector unknown) ----
    # Require at least 2 of the 4 sector-independent stages (5/6/7/8) to
    # contribute -- without a sector, that's the ceiling here, and it's the
    # bar that distinguishes a real candidate from a lone fully-earned stage
    # renormalizing to a misleading score_100 = 100.0 on almost no evidence.
    # (Stage 8 alone rarely triggers this on its own: a "no pattern" result
    # is a real, non-blank zero -- see stage8_score -- but that's one
    # contributing stage, not two, so it can't pass this bar by itself.)
    def _stages_contributing(r):
        return sum(1 for k in ("stage5_pts", "stage6_pts", "stage7_pts", "stage8_pts") if r[k] != "")

    top_discoveries = sorted(
        (r for r in discoveries if r["pts_available"] > 0 and _stages_contributing(r) >= 2),
        key=lambda r: r["score_100"], reverse=True)[:DISCOVERY_N]
    print(f"Discoveries (non-watchlist liquid stocks, sector unverified, top {DISCOVERY_N} by score_100):")
    if top_discoveries:
        print(f"{'symbol':<12}{'score':>7}{'s5':>6}{'s6':>6}{'s7':>6}{'s8':>6}{'cov':>6}  conf  pattern")
        for r in top_discoveries:
            print(f"{r['symbol']:<12}{r['score_100']:>7}{str(r['stage5_pts']):>6}{str(r['stage6_pts']):>6}"
                  f"{str(r['stage7_pts']):>6}{str(r['stage8_pts']):>6}{r['stages_covered']:>6}  {r['score_conf']}"
                  f"  {r['pattern']}")
    else:
        print("  (none scored)")
    print()

    discoveries_path = month_dir / f"discoveries{stage_suffix}.csv"
    write_discoveries(discoveries_path, top_discoveries)

    # ---- merge into universe.csv (Bucket C, merge-don't-clobber) ----
    # Only ever with the full stage set -- Bucket C is the authoritative
    # record, not a place for a --stages comparison run to leave partial
    # (and therefore misleading) scores.
    if is_full_stages:
        with open(UNIVERSE_TEMPLATE, newline="", encoding="utf-8") as f:
            uni_header = next(csv.reader(f))
        n = merge_universe(universe_path, uni_header, all_rows, owned=BUCKET_C, always=("symbol",))
        universe_note = f"Written to {universe_path.relative_to(REPO)} ({n} rows, Bucket C columns)."
    else:
        universe_note = f"universe.csv NOT updated (restricted --stages {sorted(enabled_stages)})."

    untracked_n = sum(len(v) for v in unmapped["untracked"].values())
    shortlist_sectors = len({r["sector_canon"] for r in shortlist})
    print(f"RESULT: scored {len(rows)}/{len(watch)} watchlist stocks, {untracked_n} unmapped-sector, "
          f"shortlist {len(shortlist)} name(s) from {shortlist_sectors} sector(s); "
          f"{len(discoveries)}/{len(extra_syms)} non-watchlist liquid stocks scored, "
          f"{len(top_discoveries)} discoveries.")
    print(universe_note)
    print(f"Written to {shortlist_path.relative_to(REPO)} ({len(shortlist)} rows).")
    print(f"Written to {discoveries_path.relative_to(REPO)} ({len(top_discoveries)} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
