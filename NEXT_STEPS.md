# Current status & next steps

_Snapshot as of 2026-08-09 (updated same day after the scheduler fix + August re-run below). This is the "resume here" file — read it alongside `CLAUDE.md`._

## Where we are

Building an evening batch pipeline for the v4 institutional swing-scoring model
(`docs/institutional-swing-scoring-model-v4.md`). Data → monthly/weekly/daily sheets in `journal/`.

**Done and working:**
- **Data archiving** — `source/archive_bhavcopy.py` (security bhavcopy w/ delivery, no backfill) **and** `source/archive_indices.py` (all-indices close, backfillable). Latest archived trading day for both: **2026-08-07**. Both retry/backoff, 404=holiday.
- **Nightly automation** — Task Scheduler job "NSE Bhavcopy Archiver" runs `source/run_archiver.bat` daily 19:30 (logged-on only): `new_month.py` → `archive_bhavcopy.py` → `archive_indices.py`. **The repo folder moved from `D:\Calude_WS\Trade3` to `D:\Github_workspace\Trade3`** — the scheduler was re-registered at the new path and confirmed running there as of the 2026-08-08 19:30 log entry.
- **✅ Root cause found + fixed (2026-08-09): `StartWhenAvailable` was `False`.** A plain `schtasks /Create /SC DAILY` (what `setup_scheduler.bat` used) creates a wall-clock trigger only — if the machine isn't in an interactive logon session at exactly 19:30, that day's run is skipped with **no catch-up**, even if the machine is on and logged in later. This is what caused the 2026-08-01 → 08-06 gap (the log jumps straight from `23-07-2026 17:03:21` to `08-08-2026 19:30:04`). Fixed both the live task (`Set-ScheduledTask` with `-StartWhenAvailable`) and `source/setup_scheduler.bat` (now enables it via a PowerShell call after `schtasks /Create`, so future re-registrations — e.g. after another folder move — keep it). Documented in `docs/scheduler-guide.md`. **Bhavcopy still has no backfill — the Aug 1–6 gap in delivery/breadth history is permanent regardless.** Indices *can* still be backfilled (`archive_indices.py --from 2026-08-01 --to 2026-08-06`) if those 6 sector-return days matter; not yet done.
- **✅ August pipeline re-run (2026-08-09)** off the 2026-08-07 close: `rank_sectors.py --month 2026-08`, `build_monthly.py --month 2026-08`, `rank_stocks.py --month 2026-08` all re-run successfully. `journal/2026/08-August/{sectors,universe,shortlist,discoveries}.csv` are current as of Aug 7. 89/90 watchlist stocks scored (GUJENERGY still short-history), 50-name shortlist across 7 sectors, 30 discoveries.
- **Month scaffolding** — `source/new_month.py` creates `journal/<YYYY>/<MM-Month>/` pre-filled from templates; carries the watchlist forward; near month-end pre-creates next month. Only the month level exists (`journal/2026/07-July`, `journal/2026/08-August`) — no week/day subfolders yet.
- **Watchlist** — `watchlist.csv`, **90 names / 13 sectors**, validated OK. Check with `source/validate_watchlist.py`.
- **★ Sector ranking (Stage 2) — the top-of-funnel step** — `source/rank_sectors.py` ranks **41 official/thematic NSE sectoral indexes** from index data: 1M/3M/6M returns, Relative Performance vs Nifty (`rp_*`), 1–5 star `rp_score`, RRG `quadrant` (Leading / Improving / Weakening / Lagging), and `stage2_pts`. Owns `sectors.csv`. August is populated off data through 31 July (needs a re-run once the Aug 7 close is picked up) — Healthcare/Pharma/Auto Leading among others. Every watchlist stock bridges to a ranked sector — see `docs/sectors-csv-reference.md`.
- **Monthly build (Bucket A)** — `source/build_monthly.py` auto-fills `universe.csv` (liquidity + 1M/3M returns, merge-safe), prints §1 breadth. **No longer writes sectors.csv** (rank_sectors owns it).
- **★ Sector→stock bridge + full scoring (Bucket C)** — `source/rank_stocks.py` maps each `watchlist.csv` free-form sector label to its ranked official index, then scores v4 Stages 2 (Sector Rotation, inherited), 5 (Institutional Activity), 6 (Relative Strength), 7 (Accumulation Structure), and 8 (Breakout/Entry) from data already archived. Unmapped sector labels are left blank + warned, never hard-failed. Every score carries a `stages_covered`/`score_conf` confidence flag (5 of 9 stages covered today) and prints a ranked Buy Watchlist restricted to Leading/Improving sectors, saved to `journal/<month>/shortlist.csv` (no top-N cutoff). RVOL and 3-month-momentum percentiles are ranked against **every liquid NSE EQ symbol** (`build_universe_pool()`), not just the watchlist. A strong-scoring non-watchlist stock lands in `journal/<month>/discoveries.csv` instead, sector-unverified. See `docs/stock-scoring-reference.md` for the column reference, the Zanger Rule #1 exception (a detected-nothing Stage 8 is a real zero, not missing data), and pattern-detector caveats (starting mechanical proxies, not backtested — one bug already found and fixed, Double Bottom over-firing).
- **`--stages` CLI toggle** — done. `rank_stocks.py --stages 2,5,6` excludes Stages 7/8 and writes suffixed files (`shortlist_2-5-6.csv`/`discoveries_2-5-6.csv`) instead of the canonical ones; `universe.csv`/Bucket C always uses the full implemented stage set regardless.

## Immediate next step

- **✅ Indices backfilled (2026-08-09)**: `archive_indices.py --from 2026-08-01 --to 2026-08-06` — Aug 1–2 were weekend, Aug 3–6 saved. `data/indices` now has no gap through Aug 7. Bhavcopy (security-level delivery/breadth) still can't be recovered for Aug 1–6 — that gap is permanent.
- Three longer-running tracks remain open, any can go next:
  - **Backtest/calibrate the Appendix A pattern thresholds** (Stage 8). Explicitly "starting thresholds" per the spec; one bug already found (Double Bottom over-firing). Needs historical bhavcopy + actual forward-return outcomes to tune properly.
  - **Screener fundamentals merge (Bucket B)** — takes `stages_covered` from 5/9 to 7/9 (Stages 3 + 4). Still blocked on the header row of a real Screener export to map columns; `universe.csv`'s Bucket B columns (`mkt_cap_cr`, `roce_gt15`, etc.) are still all blank.
  - **Weekly/daily template + build** — `rank_sectors.py --out` already targets a weekly path, but `new_month.py`-style scaffolding for `week`/`day` subfolders doesn't exist yet.

## Backlog (rough order)

1. ~~Sector→stock bridge + stock scoring~~ — **done**.
2. ~~Widen Stage 5/6 percentiles to the full liquid NSE universe~~ — **done**.
3. ~~Stage 7 (Accumulation Structure)~~ — **done**.
4. ~~Stage 8 (Breakout/Entry)~~ — **done**. Needs backtest calibration — see Immediate next step above.
5. ~~`--stages` CLI toggle for rank_stocks.py~~ — **done**.
6. **Screener fundamentals merge (Bucket B).** Ingest a Screener export CSV → fill `universe.csv` fundamentals + `stage3_pts`, keyed by symbol, merge-safe (reuse `merge_universe()`). **Blocker:** need the header row of a real Screener export to map columns.
7. **Weekly template** + its build. Extend `new_month.py`-style scaffolding to `week` subfolders; `rank_sectors.py --out` already targets a weekly path.
8. **Daily template** + daily scan (reuses the monthly sector ranking + `rank_stocks.py` output — Stages 5/7/8 already cover what a "daily" scan would need; this is mostly scaffolding at this point, not new scoring logic).
9. **Earnings/SUE (Stage 4)** — compute EPS/Revenue SUE from Screener quarterly → `earnings.csv`.
10. ~~Validate `rank_stocks.py`'s extended bhavcopy column indices~~ — **done**.
11. **Optional:** parse `ind_close_all` for the §1 Nifty-EMA regime lines (index file is archived, this is close at hand) — still manual today (`build_monthly.py` just prints a reminder to fill it from Zerodha).
12. **Optional:** a real sector/index-membership data source for the full NSE universe (not just watchlist.csv's hand-entered labels) would let `discoveries.csv` candidates pass the same sector-gated shortlist as watchlist stocks. NSE publishes official index-constituent files; none are archived yet.
13. **New:** backfill `data/indices` for 2026-08-01..06 if the lost sector-return days matter (see Immediate next step).

## To fill August by hand right now

- Bucket B via Screener export (once the merge helper exists, or manually into `journal/2026/08-August/universe.csv`).
- `tier` column (Priority / Watch / Size-limited) — judgment.
- §1 Nifty vs 20/50 EMA + structure — glance at Zerodha.
- §5 retrospective.

## Key decisions (full detail in CLAUDE.md)
- Earnings surprise = **SUE** from reported quarterlies (no paid estimates needed).
- Sector rotation = **ranked from official NSE index data** (`ind_close_all` → `rank_sectors.py`), all 41 tracked sectoral/thematic indexes, RP-vs-Nifty + RRG quadrants. `watchlist.csv` sector labels stay free-form and are a separate, stock-grouping concern.
- Watchlist eligibility = **soft tier** (Priority/Watch/Size-limited), not a hard gate.
- Formats: **Markdown for narrative, CSV for tables.**
- **bhavcopy nightly archive is a hard, no-backfill dependency** for delivery/breadth history going forward — confirmed painfully by the Aug 1–6 gap above.
- **Moving the repo folder requires re-running `setup_scheduler.bat`** — Task Scheduler jobs don't travel with the folder; this is what caused the Aug 1–6 archiving gap.

## How to resume
Open a fresh session in this folder; the new instance reads `CLAUDE.md` automatically. Tell it the next task (e.g. "re-run August now that Aug 7 data has landed" or "do the Screener merge"). Verify anything time-sensitive (dates, the scheduled task, latest bhavcopy) rather than trusting this snapshot blindly.
