# Current status & next steps

_Snapshot as of 2026-08-02. This is the "resume here" file — read it alongside `CLAUDE.md`._

## Where we are

Building an evening batch pipeline for the v4 institutional swing-scoring model
(`docs/institutional-swing-scoring-model-v4.md`). Data → monthly/weekly/daily sheets in `journal/`.

**Done and working:**
- **Data archiving** — `source/archive_bhavcopy.py` (security bhavcopy w/ delivery, backfilled from 2026-04-01) **and** `source/archive_indices.py` (all-indices close, backfilled from **2026-01-01**, 136 days — deep enough for 6M sector returns). Both retry/backoff, 404=holiday.
- **Nightly automation** — Task Scheduler job "NSE Bhavcopy Archiver" runs `source/run_archiver.bat` daily 19:30 (logged-on only): `new_month.py` → `archive_bhavcopy.py` → `archive_indices.py`.
- **Month scaffolding** — `source/new_month.py` creates `journal/<YYYY>/<MM-Month>/` pre-filled from templates; carries the watchlist forward; near month-end pre-creates next month.
- **Watchlist** — `watchlist.csv`, **50 names / 11 sectors**, validated OK. Check with `source/validate_watchlist.py`.
- **★ Sector ranking (Stage 2) — the top-of-funnel step** — `source/rank_sectors.py` ranks **41 official/thematic NSE sectoral indexes** (widened from the original 17 to cover Cement/Capital Goods/Healthcare/Oil & Gas — previously unmapped watchlist sectors — plus the rest of NSE's published sector/thematic set: Chemicals, Construction, Consumer Durables/Services, Financial Services 25/50 and Ex-Bank, Hospitals, Housing Finance, Insurance, NBFC, Power, Private Bank, REITs & Realty, Retail, Telecommunications, and the Nifty500/MidSmall Healthcare and MidSmall Financial Services/IT & Telecom variants) from index data: 1M/3M/6M returns, Relative Performance vs Nifty (`rp_*`), 1–5 star `rp_score`, RRG `quadrant` (Leading / Improving / Weakening / Lagging), and `stage2_pts`. Owns `sectors.csv`. August is populated (Pharma/Realty/Healthcare/Auto Leading among others). Every watchlist stock now bridges to a ranked sector (0 unmapped, down from up to 13) — see `docs/sectors-csv-reference.md`.
- **Monthly build (Bucket A)** — `source/build_monthly.py` auto-fills `universe.csv` (liquidity + 1M/3M returns, merge-safe), prints §1 breadth. **No longer writes sectors.csv** (rank_sectors owns it).
- **★ Sector→stock bridge + full scoring (Bucket C)** — `source/rank_stocks.py` maps each `watchlist.csv` free-form sector label to its ranked official index (handling the label mismatch between watchlist's exact index names and `sectors.csv`'s friendly labels), then scores v4 Stages 2 (Sector Rotation, inherited), 5 (Institutional Activity), 6 (Relative Strength), 7 (Accumulation Structure), and 8 (Breakout/Entry) from data already archived. Unmapped sectors (`Cement`, `Nifty Capital Goods`) are left blank + warned, never hard-failed. Every score carries a `stages_covered`/`score_conf` confidence flag (5 of 9 stages covered today) and prints a ranked Buy Watchlist restricted to Leading/Improving sectors, saved to `journal/<month>/shortlist.csv`. **RVOL and 3-month-momentum percentiles are ranked against every liquid NSE EQ symbol** (`build_universe_pool()`, gated by the same ₹20 Cr median-turnover liquidity rule `build_monthly.py` uses), not just the 45-name watchlist. **Every liquid NSE stock is also scored on Stages 5/6/7/8 directly** (not just the watchlist) — but only watchlist stocks have a known sector, so only they can pass the shortlist's Leading/Improving gate; a strong-scoring non-watchlist stock instead lands in `journal/<month>/discoveries.csv`, sector-unverified. **Stage 7** (volatility contraction, volume dry-up, tight base, quiet delivery accumulation) is the pre-breakout "about to move" detector; **Stage 8** (Appendix A's six mechanical Zanger patterns) is the actual breakout trigger — together the two stages most directly aimed at catching a move as/before it happens, not just confirming one already underway. See `docs/stock-scoring-reference.md` for the column reference, including the Zanger Rule #1 exception (a detected-nothing Stage 8 is a real zero, not missing data) and the pattern-detector caveats (starting mechanical proxies, not backtested — one bug already found and fixed).

## Immediate next step

Three independent tracks remain, any can go first:

- **Backtest/calibrate the Appendix A pattern thresholds.** They're explicitly "starting thresholds" per the spec, and building them surfaced one real bug (Double Bottom over-firing on nearly every stock until tightened) — the other five detectors are equally unvalidated. Needs historical bhavcopy + actual forward-return outcomes to tune properly, not just eyeballing.
- **Screener fundamentals merge (Bucket B)** — backlog item below. Takes `rank_stocks.py`'s `stages_covered` from 5/9 to 7/9 (Stages 3 + 4). Still needs the header row of a real Screener export to map columns.
- **`--stages` CLI toggle**, if not already done by the time you read this — see backlog below.

## Backlog (rough order)

1. ~~Sector→stock bridge + stock scoring~~ — **done** (`rank_stocks.py`, Stages 2/5/6 shipped, above).
2. ~~Widen Stage 5/6 percentiles to the full liquid NSE universe~~ — **done**. `build_universe_pool()` now ranks RVOL/3-month-momentum against every liquid NSE EQ symbol (593/2642 passed the >20 Cr gate as of 2026-07-31), not just the watchlist, matching `CLAUDE.md`'s "ranked by percentile across the whole scanned universe" invariant. See `docs/stock-scoring-reference.md`.
3. ~~Stage 7 (Accumulation Structure)~~ — **done**. Volatility contraction (ATR% percentile, needs 136 sessions — still unavailable, self-activates), volume dry-up, tight base, and quiet delivery accumulation (with a not-yet-broken-out guard) all shipped in `rank_stocks.py`, scored for the full liquid universe like Stage 5. `ASHOKLEY` already shows the full pre-breakout signature (dry-up + tight base + quiet accumulation, all `Y`) as of 2026-07-31.
4. ~~Stage 8 (Breakout/Entry)~~ — **done**. All six Appendix-A patterns (Cup and Handle, High Tight Flag, Ascending Triangle, Flat Base, Double Bottom, Trendline/Resistance Breakout — the last simplified to a flat-level proxy, no true diagonal-trendline fit) plus volume confirmation, close-above-pivot, follow-through, and overhead-supply, scored for the full liquid universe like Stages 5/7. Implements Zanger Rule #1 (no pattern = a real, fully-available zero, not missing data). `ASHOKLEY` shows a live example: a confirmed Trendline breakout with volume, not yet closed above pivot — a "watch," not a "buy." **Needs backtest calibration** — see Immediate next step above.
5. **`--stages` CLI toggle for rank_stocks.py.** Let a run include/exclude Stage 7 and/or 8 (e.g. `--stages 2,5,6` vs the default `2,5,6,7,8`) so you can compare shortlists with and without the newer, less-validated stages. Default run keeps writing the canonical `shortlist.csv`/`discoveries.csv`; a restricted `--stages` run writes to suffixed filenames instead (e.g. `shortlist_2-5-6.csv`) so both coexist. `universe.csv`/Bucket C always uses the full stage set regardless — it's the authoritative record, not an experiment.
6. **Screener fundamentals merge (Bucket B).** Ingest a Screener export CSV → fill `universe.csv` fundamentals (`mkt_cap_cr`, `roce_gt15`, …) + `stage3_pts`, keyed by symbol, merge-safe like build_monthly/rank_stocks (reuse the parametrized `merge_universe()`). **Blocker:** need the header row of a real Screener export to map columns.
7. **Weekly template** + its build. Extend `new_month.py`-style scaffolding to `week` subfolders; `rank_sectors.py --out` already targets a weekly path.
8. **Daily template** + daily scan (reuses the monthly sector ranking + `rank_stocks.py` output — Stages 5/7/8 already cover what a "daily" scan would need; this is mostly scaffolding at this point, not new scoring logic).
9. **Earnings/SUE (Stage 4)** — compute EPS/Revenue SUE from Screener quarterly → `earnings.csv`.
10. ~~Validate `rank_stocks.py`'s extended bhavcopy column indices~~ — **done**, confirmed against a real archived file (`HIGH=5, LOW=6, VOLUME=10, DELIV_PER=14` all correct).
11. **Optional:** parse `ind_close_all` for the §1 Nifty-EMA regime lines (now that the index file is archived, this is close at hand).
12. **Optional:** a real sector/index-membership data source for the full NSE universe (not just watchlist.csv's hand-entered labels) would let `discoveries.csv` candidates pass the same sector-gated shortlist as watchlist stocks, instead of landing in a separate sector-unverified list. NSE publishes official index-constituent files; none are archived yet.

## To fill July by hand right now (~10 min)

- Bucket B via Screener export (once the merge helper exists, or manually into `journal/2026/07-July/universe.csv`).
- `tier` column (Priority / Watch / Size-limited) — judgment.
- §1 Nifty vs 20/50 EMA + structure — glance at Zerodha. (Breadth already computed: ~49%, WEAK.)
- §5 retrospective.

## Key decisions (full detail in CLAUDE.md)
- Earnings surprise = **SUE** from reported quarterlies (no paid estimates needed).
- Sector rotation = **ranked from official NSE index data** (`ind_close_all` → `rank_sectors.py`), all 41 tracked sectoral/thematic indexes, RP-vs-Nifty + RRG quadrants. (Superseded the earlier watchlist-constituent estimate.) `watchlist.csv` sector labels stay free-form and are a separate, stock-grouping concern.
- Watchlist eligibility = **soft tier** (Priority/Watch/Size-limited), not a hard gate.
- Formats: **Markdown for narrative, CSV for tables.**
- **bhavcopy nightly archive is a hard, no-backfill dependency** for delivery/breadth history going forward.

## How to resume
Open a fresh session in this folder; the new instance reads `CLAUDE.md` automatically. Tell it the next task (e.g. "do the Screener merge"). Verify anything time-sensitive (dates, the scheduled task, latest bhavcopy) rather than trusting this snapshot blindly.
