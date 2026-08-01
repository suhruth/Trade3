# Current status & next steps

_Snapshot as of 2026-07-23. This is the "resume here" file — read it alongside `CLAUDE.md`._

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

## Immediate next step

**Lock the sector layer, then bridge sectors → stocks.** The user's directive is "nail the sectors completely first." Sector ranking is built and matches their RP + RRG method. The next milestone is the **stock layer** (their Part 2/3): within the Leading + Improving sectors, shortlist and score stocks (sector strength, stock RS vs its sector, RVOL, delivery %, EMA 20/50/200 alignment, earnings) → ranked Buy Watchlist. **First sub-step:** map each `watchlist.csv` free-form sector label to its ranked official index in `sectors.csv`, so a stock inherits its sector's quadrant/score.

## Backlog (rough order)

1. **Sector→stock bridge + stock scoring** (above) — the weekend workflow: top-5 sectors → 8–10 stocks each → weighted score → top 10–15 Buy Watchlist.
2. **Screener fundamentals merge (Bucket B).** Ingest a Screener export CSV → fill `universe.csv` fundamentals (`mkt_cap_cr`, `roce_gt15`, …) + `stage3_pts`, keyed by symbol, merge-safe like build_monthly. **Blocker:** need the header row of a real Screener export to map columns.
3. **Weekly template** + its build. Extend `new_month.py`-style scaffolding to `week` subfolders; `rank_sectors.py --out` already targets a weekly path.
4. **Daily template** + daily scan (full v4 score: RVOL percentile, delivery surge, breakout, lifecycle label, risk gates).
5. **Earnings/SUE (Stage 4)** — compute EPS/Revenue SUE from Screener quarterly → `earnings.csv`.
6. **Optional:** parse `ind_close_all` for the §1 Nifty-EMA regime lines (now that the index file is archived, this is close at hand).

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
