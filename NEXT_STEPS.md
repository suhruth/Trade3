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
- **★ Sector→stock bridge + partial scoring (Bucket C)** — `source/rank_stocks.py` maps each `watchlist.csv` free-form sector label to its ranked official index (handling the label mismatch between watchlist's exact index names and `sectors.csv`'s friendly labels), then scores v4 Stages 2 (Sector Rotation, inherited), 5 (Institutional Activity), 6 (Relative Strength), and 7 (Accumulation Structure) from data already archived. Unmapped sectors (`Cement`, `Nifty Capital Goods`) are left blank + warned, never hard-failed. Every score carries a `stages_covered`/`score_conf` confidence flag (4 of 9 stages covered today) and prints a ranked Buy Watchlist restricted to Leading/Improving sectors, saved to `journal/<month>/shortlist.csv`. **RVOL and 3-month-momentum percentiles are ranked against every liquid NSE EQ symbol** (`build_universe_pool()`, gated by the same ₹20 Cr median-turnover liquidity rule `build_monthly.py` uses), not just the 45-name watchlist. **Every liquid NSE stock is also scored on Stages 5/6/7 directly** (not just the watchlist) — but only watchlist stocks have a known sector, so only they can pass the shortlist's Leading/Improving gate; a strong-scoring non-watchlist stock instead lands in `journal/<month>/discoveries.csv`, sector-unverified. **Stage 7 (volatility contraction, volume dry-up, tight base, quiet delivery accumulation)** is the pre-breakout "about to move" detector — the piece most directly aimed at catching a move before it happens, not just confirming one already underway. See `docs/stock-scoring-reference.md` for the column reference.

## Immediate next step

Two independent tracks remain, either can go first:

- **Stage 8 (Breakout/Entry)** — the mechanical Zanger-pattern detection that identifies the actual breakout trigger, now that Stage 7 catches the pre-breakout setup. The piece most directly aligned with "catch the move as/before it happens."
- **Screener fundamentals merge (Bucket B)** — backlog item below. Takes `rank_stocks.py`'s `stages_covered` from 4/9 to 6/9 (Stages 3 + 4). Still needs the header row of a real Screener export to map columns.

## Backlog (rough order)

1. ~~Sector→stock bridge + stock scoring~~ — **done** (`rank_stocks.py`, Stages 2/5/6 shipped, above).
2. ~~Widen Stage 5/6 percentiles to the full liquid NSE universe~~ — **done**. `build_universe_pool()` now ranks RVOL/3-month-momentum against every liquid NSE EQ symbol (593/2642 passed the >20 Cr gate as of 2026-07-31), not just the watchlist, matching `CLAUDE.md`'s "ranked by percentile across the whole scanned universe" invariant. See `docs/stock-scoring-reference.md`.
3. ~~Stage 7 (Accumulation Structure)~~ — **done**. Volatility contraction (ATR% percentile, needs 136 sessions — still unavailable, self-activates), volume dry-up, tight base, and quiet delivery accumulation (with a not-yet-broken-out guard) all shipped in `rank_stocks.py`, scored for the full liquid universe like Stage 5. `ASHOKLEY` already shows the full pre-breakout signature (dry-up + tight base + quiet accumulation, all `Y`) as of 2026-07-31.
4. **Screener fundamentals merge (Bucket B).** Ingest a Screener export CSV → fill `universe.csv` fundamentals (`mkt_cap_cr`, `roce_gt15`, …) + `stage3_pts`, keyed by symbol, merge-safe like build_monthly/rank_stocks (reuse the parametrized `merge_universe()`). **Blocker:** need the header row of a real Screener export to map columns.
5. **Weekly template** + its build. Extend `new_month.py`-style scaffolding to `week` subfolders; `rank_sectors.py --out` already targets a weekly path.
6. **Mechanical pattern detection (Stage 8)** — Breakout/Entry, Zanger's six patterns (v4 Appendix A). The remaining large piece of the stock-scoring layer; needs its own design pass (pattern geometry, not just more archived data).
7. **Daily template** + daily scan (reuses the monthly sector ranking + `rank_stocks.py` output; adds whatever's still daily-only — RVOL/delivery/accumulation are already Stages 5/7, so this is mostly Stage 8/9 once patterns exist).
8. **Earnings/SUE (Stage 4)** — compute EPS/Revenue SUE from Screener quarterly → `earnings.csv`.
9. ~~Validate `rank_stocks.py`'s extended bhavcopy column indices~~ — **done**, confirmed against a real archived file (`HIGH=5, LOW=6, VOLUME=10, DELIV_PER=14` all correct).
10. **Optional:** parse `ind_close_all` for the §1 Nifty-EMA regime lines (now that the index file is archived, this is close at hand).
11. **Optional:** a real sector/index-membership data source for the full NSE universe (not just watchlist.csv's hand-entered labels) would let `discoveries.csv` candidates pass the same sector-gated shortlist as watchlist stocks, instead of landing in a separate sector-unverified list. NSE publishes official index-constituent files; none are archived yet.

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
