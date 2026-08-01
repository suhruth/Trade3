# Current status & next steps

_Snapshot as of 2026-08-01. This is the "resume here" file — read it alongside `CLAUDE.md`._

## Where we are

Building an evening batch pipeline for the v4 institutional swing-scoring model
(`docs/institutional-swing-scoring-model-v4.md`). Data → monthly/weekly/daily sheets in `journal/`.

**Done and working:**
- **Data archiving** — `source/archive_bhavcopy.py` (security bhavcopy w/ delivery, backfilled from 2026-04-01) **and** `source/archive_indices.py` (all-indices close, backfilled from **2026-01-01**, 136 days — deep enough for 6M sector returns). Both retry/backoff, 404=holiday.
- **Nightly automation** — Task Scheduler job "NSE Bhavcopy Archiver" runs `source/run_archiver.bat` daily 19:30 (logged-on only): `new_month.py` → `archive_bhavcopy.py` → `archive_indices.py`.
- **Month scaffolding** — `source/new_month.py` creates `journal/<YYYY>/<MM-Month>/` pre-filled from templates; carries the watchlist forward; near month-end pre-creates next month.
- **Watchlist** — `watchlist.csv`, **45 names / 9 sectors**, validated OK. Check with `source/validate_watchlist.py`.
- **★ Sector ranking (Stage 2) — the top-of-funnel step** — `source/rank_sectors.py` ranks all **17 official NSE sectoral indexes** from index data: 1M/3M/6M returns, Relative Performance vs Nifty (`rp_*`), 1–5 star `rp_score`, RRG `quadrant` (Leading / Improving / Weakening / Lagging), and `stage2_pts`. Owns `sectors.csv`. July is populated (Pharma/Realty/Auto Leading; IT Improving).
- **Monthly build (Bucket A)** — `source/build_monthly.py` auto-fills `universe.csv` (liquidity + 1M/3M returns, merge-safe), prints §1 breadth. **No longer writes sectors.csv** (rank_sectors owns it).
- **★ Sector→stock bridge + partial scoring (Bucket C)** — `source/rank_stocks.py` maps each `watchlist.csv` free-form sector label to its ranked official index (handling the label mismatch between watchlist's exact index names and `sectors.csv`'s friendly labels), then scores v4 Stages 2 (Sector Rotation, inherited), 5 (Institutional Activity), and 6 (Relative Strength) from data already archived. Unmapped sectors (`Cement`, `Nifty Capital Goods`) are left blank + warned, never hard-failed. Every score carries a `stages_covered`/`score_conf` confidence flag (only 3 of 9 stages covered today) and prints a ranked Buy Watchlist restricted to Leading/Improving sectors. **RVOL and 3-month-momentum percentiles are ranked against every liquid NSE EQ symbol** (`build_universe_pool()`, gated by the same ₹20 Cr median-turnover liquidity rule `build_monthly.py` uses), not just the 45-name watchlist — so a mover outside the watchlist can still be reflected via a watchlist stock's percentile position. See `docs/stock-scoring-reference.md` for the column reference.

## Immediate next step

**Screener fundamentals merge (Bucket B)** — backlog item below. This is what would take `rank_stocks.py`'s `stages_covered` from 3/9 to 5/9 (Stages 3 + 4), and is the last blocker on the fundamentals side. Still needs the header row of a real Screener export to map columns.

## Backlog (rough order)

1. ~~Sector→stock bridge + stock scoring~~ — **done** (`rank_stocks.py`, Stages 2/5/6 shipped, above). Stages 7/8 (accumulation structure, Zanger patterns — mechanical chart-pattern detection) split out as backlog item 4 below, since they need pattern-recognition logic this repo doesn't have yet, not just more archived data.
2. ~~Widen Stage 5/6 percentiles to the full liquid NSE universe~~ — **done**. `build_universe_pool()` now ranks RVOL/3-month-momentum against every liquid NSE EQ symbol (593/2642 passed the >20 Cr gate as of 2026-07-31), not just the watchlist, matching `CLAUDE.md`'s "ranked by percentile across the whole scanned universe" invariant. See `docs/stock-scoring-reference.md`.
3. **Screener fundamentals merge (Bucket B).** Ingest a Screener export CSV → fill `universe.csv` fundamentals (`mkt_cap_cr`, `roce_gt15`, …) + `stage3_pts`, keyed by symbol, merge-safe like build_monthly/rank_stocks (reuse the parametrized `merge_universe()`). **Blocker:** need the header row of a real Screener export to map columns.
4. **Weekly template** + its build. Extend `new_month.py`-style scaffolding to `week` subfolders; `rank_sectors.py --out` already targets a weekly path.
5. **Mechanical pattern detection (Stages 7 & 8)** — Accumulation Structure + Breakout/Entry, Zanger's six patterns (v4 Appendix A). The large deferred piece of the stock-scoring layer; needs its own design pass.
6. **Daily template** + daily scan (reuses the monthly sector ranking + `rank_stocks.py` output; adds whatever's still daily-only — RVOL/delivery are already Stage 5, so this is mostly Stage 8/9 once patterns exist).
7. **Earnings/SUE (Stage 4)** — compute EPS/Revenue SUE from Screener quarterly → `earnings.csv`.
8. ~~Validate `rank_stocks.py`'s extended bhavcopy column indices~~ — **done**, confirmed against a real archived file (`HIGH=5, LOW=6, VOLUME=10, DELIV_PER=14` all correct).
9. **Optional:** parse `ind_close_all` for the §1 Nifty-EMA regime lines (now that the index file is archived, this is close at hand).

## To fill July by hand right now (~10 min)

- Bucket B via Screener export (once the merge helper exists, or manually into `journal/2026/07-July/universe.csv`).
- `tier` column (Priority / Watch / Size-limited) — judgment.
- §1 Nifty vs 20/50 EMA + structure — glance at Zerodha. (Breadth already computed: ~49%, WEAK.)
- §5 retrospective.

## Key decisions (full detail in CLAUDE.md)
- Earnings surprise = **SUE** from reported quarterlies (no paid estimates needed).
- Sector rotation = **ranked from official NSE index data** (`ind_close_all` → `rank_sectors.py`), all 17 sectoral indexes, RP-vs-Nifty + RRG quadrants. (Superseded the earlier watchlist-constituent estimate.) `watchlist.csv` sector labels stay free-form and are a separate, stock-grouping concern.
- Watchlist eligibility = **soft tier** (Priority/Watch/Size-limited), not a hard gate.
- Formats: **Markdown for narrative, CSV for tables.**
- **bhavcopy nightly archive is a hard, no-backfill dependency** for delivery/breadth history going forward.

## How to resume
Open a fresh session in this folder; the new instance reads `CLAUDE.md` automatically. Tell it the next task (e.g. "do the Screener merge"). Verify anything time-sensitive (dates, the scheduled task, latest bhavcopy) rather than trusting this snapshot blindly.
