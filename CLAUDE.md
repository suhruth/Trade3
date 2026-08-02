# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Resuming work?** Read `NEXT_STEPS.md` first — it's the living "where we are / what's pending" snapshot. This file is the architecture reference.

This repo builds an evening batch pipeline for the v4 institutional swing-scoring model (`docs/institutional-swing-scoring-model-v4.md`). Data → monthly/weekly/daily analysis sheets in `journal/`.

## Commands

Python 3, **stdlib only** — no `requirements.txt`, no virtualenv, no build step, no linter, no test suite. Run scripts directly from the repo root.

```bash
python source/archive_bhavcopy.py                     # security bhavcopy, latest trading day
python source/archive_bhavcopy.py --date 2026-07-22   # one day (YYYY-MM-DD or DDMMYYYY)
python source/archive_bhavcopy.py --from 2026-04-01 --to 2026-06-30   # backfill a range
python source/archive_indices.py                      # all-indices close (sector data), latest day
python source/archive_indices.py --from 2026-04-01    # backfill index history (this file IS backfillable)
python source/validate_watchlist.py                   # run after editing watchlist.csv
python source/rank_sectors.py                         # STEP 1 (weekly+monthly): rank the 17 sectors
python source/rank_sectors.py --month 2026-07         # target a specific journal month
python source/build_monthly.py                        # fill this month's universe.csv Bucket A
python source/build_monthly.py --month 2026-07        # target a specific journal month
python source/rank_stocks.py                          # STEP 3: bridge stocks to sectors, score v4 Stages 2/5/6/7/8
python source/rank_stocks.py --month 2026-07          # target a specific journal month (needs sectors.csv + universe.csv already built for that month)
python source/rank_stocks.py --stages 2,5,6           # drop the less-validated Stages 7/8; writes shortlist_2-5-6.csv/discoveries_2-5-6.csv instead of the canonical files (universe.csv/Bucket C always uses the full stage set)
python source/new_month.py                            # scaffold journal month folder(s)
python source/new_month.py --date 2026-07-29 --lookahead 7   # simulate a date / widen lookahead
```

`validate_watchlist.py` and `archive_bhavcopy.py` exit non-zero on real failures (unknown symbol / empty sector / duplicate; network error) — a 404 from NSE means *holiday*, not failure. **Since there are no tests, exercising these exit codes is the verification loop** for changes to loaders or the watchlist.

Windows wrappers (portable, self-locating via `%~dp0` — nothing to edit after copying the folder):
- `source/new_month.bat` — same as `new_month.py`, args passed through.
- `source/run_archiver.bat` — the nightly job: runs `new_month.py` **then** `archive_bhavcopy.py`, appending both to `logs/archiver.log`.
- `source/setup_scheduler.bat [HH:MM]` — run **once per machine** to register the Task Scheduler job (default 19:30). Safe to re-run (`/F`).
- `docs/scheduler-guide.md` — human-facing operator's manual for these three `.bat` files and `schtasks` (setup, checking status/logs, running manually, troubleshooting) — no AI session needed.

Nightly automation is a Task Scheduler job **"NSE Bhavcopy Archiver"**, daily 19:30 IST (after NSE publishes post-close), logged-on only. `run_archiver.bat` runs three jobs in order: `new_month.py` → `archive_bhavcopy.py` → `archive_indices.py`. Manage with `schtasks /Query|/Run|/Change /ST|/Delete /TN "NSE Bhavcopy Archiver"`. The task lives in each machine's scheduler and does **not** travel with the folder — re-run `setup_scheduler.bat` after moving.

## Data flow

```
data/indices/<year>/ind_close_all_*.csv ──→ rank_sectors.py ──→ journal/<…>/sectors.csv  (STEP 1: rank 17 sectors)
   ↑ archive_indices.py (nightly; backfillable)                    ↓ Leaders + Emerging sectors
                                                                   drive where you hunt for stocks
watchlist.csv (hand-maintained)  ─┐
                                  ├─→ build_monthly.py ─→ journal/<…>/universe.csv  (Bucket A + §1 breadth)
data/bhavcopy/<year>/*.csv  ──────┘                            ↓
   ↑ archive_bhavcopy.py (nightly, NO backfill — delivery/breadth history accrues forward only)
sectors.csv + universe.csv(Bucket A) + watchlist.csv + data/bhavcopy + data/indices
                                  └─→ rank_stocks.py ─→ journal/<…>/universe.csv  (Bucket C: sector bridge + Stages 2/5/6/7/8)
                                                     └─→ journal/<…>/shortlist.csv    (Buy Watchlist: Leading/Improving-sector watchlist stocks, all of them, by score_100)
                                                     └─→ journal/<…>/discoveries.csv  (strong non-watchlist liquid stocks, sector-unverified)
templates/*  ──→ new_month.py ──→ journal/<YYYY>/<MM-Month>/  (monthly.md + 3 CSVs, never overwrites)
```

The intended workflow is **top-down**: rank sectors first, then pick stocks *inside* the strong sectors. Four things make this pipeline unusual and must be preserved:

1. **Sector rotation runs off official NSE index data, and is a separate step that owns `sectors.csv`.** `rank_sectors.py` reads the archived `ind_close_all` files and ranks all **17 key Nifty sectoral indexes** (the `SECTORS` map — note the label→exact-index-name translation, e.g. `Nifty Fin Service` → `Nifty Financial Services`). Per sector it computes **1M/3M/6M returns**, **Relative Performance** (`rp = sector return − Nifty 50 return`) on each window, a **1–5 `rp_score`** (star bands on 3M RP: >15→5, 10–15→4, 5–10→3, 0–5→2, <0→1), the **RS-momentum** of the sector÷Nifty line, **`pct_off_6m_high`** (distance below the 6-month closing high; near-highs = money committed), **`accel`** (Y if `ret_1m > ret_3m/3` — recent month outpacing the quarter), and an **RRG `quadrant`**: **Leading** (ahead of Nifty + momentum rising), **Improving** (behind but momentum rising — the "next to become strong"), **Weakening** (ahead but momentum falling), **Lagging** (behind + falling). Rows are ranked by 3M RP. It also keeps **`stage2_pts`** (0–10, the v4-spec Stage 2 score: top-5 by 1M + top-5 by 3M + RS acceleration) for the scorer. `build_monthly.py` no longer touches `sectors.csv`. Because ranking uses index data, every sector is ranked even where the watchlist holds no stocks — that's why we retired the old watchlist-constituent estimate. **6M columns need ≥126 archived index days**; below that they're blank (backfill further with `archive_indices.py --from`).
2. **Bucket A / Bucket B / Bucket C split in `universe.csv`.** `build_monthly.py` owns only Bucket A (`median_trdval_cr`, `liquid`, `ret_1m_pct`, `ret_3m_pct` — the `BUCKET_A` tuple) and **merges by symbol, preserving every other cell**, so re-running never destroys hand-entered Bucket B (Screener fundamentals, `tier`) or `rank_stocks.py`'s Bucket C (the 31-column sector bridge + Stage 2/5/6/7/8 score, the `BUCKET_C` tuple in `rank_stocks.py`). `merge_universe()` (in `build_monthly.py`, reused by `rank_stocks.py`) takes `owned=`/`always=` parameters precisely so every writer shares one merge-don't-clobber implementation instead of drifting copies. Any new writer to `universe.csv` must go through it the same way.
3. **`watchlist.csv` sector labels stay free-form** (`Cement`, `Nifty Capital Goods`, …) — there is deliberately no canonical-name check in `validate_watchlist.py`. These labels group *your stocks* for stock-selection; they are **independent of** the 17 official indexes that `rank_sectors.py` ranks. `rank_stocks.py` bridges the two: it resolves each label to a `SECTORS` key (handling the label ↔ exact-index-name mismatch — e.g. watchlist's `Nifty Financial Services` vs. `sectors.csv`'s `Nifty Fin Service`) and writes it to `universe.csv`'s `sector_canon` column. Labels with no matching index (`Cement`, `Nifty Capital Goods` today) are left blank and warned about, never hard-failed — see `docs/stock-scoring-reference.md`.
4. **`rank_stocks.py` only scores what's mechanically reachable today: v4 Stages 2, 5, 6, 7, 8.** Stages 1/3/4/9 need data this repo doesn't have yet (Nifty-EMA regime, Screener fundamentals). Stage 7 (Accumulation Structure) is the pre-breakout detector — volatility contraction, volume dry-up, tight base, quiet delivery accumulation. Stage 8 (Breakout/Entry) is the actual trigger — Appendix A's six mechanical Zanger patterns (one, Trendline/Resistance Breakout, simplified to a flat-level proxy rather than a true diagonal-trendline fit), plus volume confirmation, close-above-pivot, follow-through, and overhead supply; per Zanger Rule #1, "no qualifying pattern" is a real, fully-available zero, not missing data — the one deliberate exception to the missing-data rule below. Both stages are scored for the full liquid universe like Stage 5, not just the watchlist. The pattern detectors are explicitly unvalidated starting thresholds (per the spec's own words for Appendix A) — building them surfaced one real over-detection bug (Double Bottom), so treat `pattern` as a lead needing backtest confirmation, not a finished signal. Every score is renormalized over only the criteria actually measured (see Model invariants below) and carries a `stages_covered`/`score_conf` flag — never mistake a 5/9-stage score for a full v4 score. `rank_stocks.py` prints and saves a ranked Buy Watchlist to `journal/<…>/shortlist.csv`: every watchlist stock in a Leading/Improving sector, sorted by `score_100`, **with no top-N cutoff** — a Stage 8 "no pattern" zero (Zanger Rule #1) pushes a stock down the ranking but must never remove it, since a stock quietly accumulating on Stage 7 without a confirmed breakout is still worth a manual chart check. A strong-scoring non-watchlist stock (no known sector, so it can't pass the Leading/Improving gate) lands in `journal/<…>/discoveries.csv` instead, flagged sector-unverified. A `--stages` flag (e.g. `--stages 2,5,6`) lets a run exclude Stages 7/8 for comparison; a restricted run writes to suffixed filenames (`shortlist_2-5-6.csv`) rather than the canonical ones, and never touches `universe.csv` — Bucket C always reflects the full implemented stage set.

Cadence: sector ranking + the monthly sheet are the slow layer. **The daily scan reuses the monthly sector ranking and universe tiers — they are not recomputed daily.** `rank_sectors.py` is also the intended **weekly** step (pass `--out` to write into a week folder). Weekly/daily templates and their builds are the main unbuilt piece.

## Directory layout

- `docs/` — `institutional-swing-scoring-model-v4.md` is the **current spec**; the un-suffixed file is v3, kept only for comparison. `sectors-csv-reference.md` = quick column reference for `rank_sectors.py`'s `sectors.csv` output. `Sectors.jpg` = the 17 key NSE sectoral indexes.
- `templates/` — one Markdown hub (`monthly-scan-template.md`, with `{MONTH}`/`{YYYY}`/`{MM-MONTH}` placeholders substituted on stamp) plus three companion CSVs. **Format convention: Markdown for narrative, CSV for the big tables** (sortable, scanner-populatable).
- `source/` — the scanner. See Commands above for each script's job.
- `watchlist.csv` — **the master input, hand-maintained.** Identity only: `symbol,sector,notes`; `symbol` must match the bhavcopy `SYMBOL`. Everything else (liquidity, returns, fundamentals, tier) is derived. Currently 45 names / 9 sectors.
- `data/bhavcopy/<year>/sec_bhavdata_full_DDMMYYYY.csv` — raw security archive, kept **verbatim**. The no-backfill delivery/breadth history (accrues forward only).
- `data/indices/<year>/ind_close_all_DDMMYYYY.csv` — raw all-indices close archive, kept **verbatim**. Feeds `rank_sectors.py`. Unlike the security bhavcopy, this file **is** historically backfillable (`--from`), so sector history can be pulled on demand.
- `journal/<YYYY>/<MM-Month>/` — generated sheets (`monthly.md`, `universe.csv`, `sectors.csv`, `earnings.csv`). Month folders are named `07-July` (zero-padded → sorts correctly). The intended full hierarchy adds `<week>/<day>/` levels; only the month level exists today.
- `logs/archiver.log` — appended nightly run log.

## Gotchas when touching the data layer

- **Bhavcopy headers have leading spaces** (` SERIES`, ` DELIV_PER`). `build_monthly.py` sidesteps this with fixed column indices (`C_SYMBOL/C_SERIES/C_CLOSE/C_TURNOVER = 0,1,8,11`) — brittle if NSE changes the layout, so validate indices before trusting a new loader. `TURNOVER_LACS` is in lakh; divide by 100 for crore. `rank_stocks.py` additionally reads `C_HIGH/C_LOW/C_VOLUME/C_DELIV = 5,6,10,14` (Stage 5/6 need high/low/volume/delivery%, not just close/turnover) — these four are **inferred from the standard NSE `sec_bhavdata_full` layout, not independently verified against a real archived file** (this repo's dev sandbox has no `data/`). Validate against one real file before trusting a live run.
- **Never sort bhavcopy filenames lexically** — `30062026` sorts after `23072026`. Both `build_monthly.py` and `validate_watchlist.py` carry a `_date_key()` that parses DDMMYYYY into `(yyyy, mm, dd)`; reuse that, don't re-derive it.
- Only `SERIES == "EQ"` rows are used, deduped within a file.
- Window constants live at the top of `build_monthly.py`: 1M = 21 sessions, 3M = 63, liquidity = median 20-day turnover > ₹20 Cr, breadth = % above 50-DMA. Short-history names get blank returns and are reported as "short history".
- Archiver behaviour worth preserving: writes via a `.part` temp then atomic `replace()`; retries transient errors with backoff but **never retries a 404** (definitive: no trading that day); rejects HTML error pages served with status 200 via `looks_like_bhavcopy()`.
- `new_month.py` **never overwrites** an existing file, and carries the prior month's `universe.csv`/`sectors.csv` forward with only the identity columns kept (`CARRY_KEEP`) and data blanked. Keep it idempotent — it runs unattended every night.
- Not auto-filled anywhere yet, still manual: Screener fundamentals (Bucket B), `tier`, and the §1 Nifty-vs-20/50-EMA regime lines (index data isn't in the security bhavcopy; archiving `ind_close_all` would fix this).

## Model invariants the implementation must preserve

A weighted **0–100 score (v4)** ranking NSE stocks for swing entries. Grades: A+ 85–100, A 70–84, B 55–69, C <55.

- **Percentage weights, not fixed points**, summing to 100 — so weights can be re-tuned from backtest evidence without recomputing grade boundaries.
- **9 stages, in this order:** Market Health (10) → Sector Rotation (10) → Fundamental Quality (15) → Earnings Quality (10) → Institutional Activity (15) → Relative Strength (15) → Accumulation Structure (10) → Breakout/Entry (15) → Risk + Execution (unscored pass/fail gates).
- **Two deliberate splits that must not be recombined:** Institutional Activity (is money moving?) vs Relative Strength (is price actually outperforming?); Accumulation Structure (early entry) vs Breakout (momentum entry). Merging them reintroduces the false signals the model exists to filter out.
- **Every criterion is mechanical.** No criterion may require human chart judgment — if you implement one that does, you've reintroduced the discretion the model exists to remove. Zanger's six patterns (Cup & Handle, High Tight Flag, Ascending Triangle, Flat Base, Double Bottom, Trendline Breakout) have mechanical definitions in v4 Appendix A; score only the single most clearly formed pattern, no pattern = zero.
- **Missing data is renormalized, never scored 0:** `stage_score = (earned ÷ available) × nominal_weight`, plus a per-stock data-confidence flag. Scoring missing as 0 silently biases toward large caps. `rank_stocks.py` is the first script to implement this: it renormalizes at **both** criterion level (within a stage) and stage level (across the composite `score_100`), and every scored stock carries `pts_available`, `stages_covered` (e.g. `2/9`), and `score_conf` (HIGH/MED/LOW) — the confidence flag this invariant requires. It only covers Stages 2 (Sector Rotation, a pure join off `sectors.csv`), 5 (Institutional Activity), and 6 (Relative Strength) today; Stages 1/3/4/7/8/9 are unimplemented (blocked on the Nifty-EMA regime lines, the Screener merge, and mechanical pattern detection respectively) — `score_100` is a projection onto the 100-point scale from what *was* measured, not a comparable full v4 score. Stage 6's 52-week-high criterion (3 pts) is deliberately left unavailable until the bhavcopy archive reaches 252 sessions (~85 archived as of writing) rather than fudging a shorter window as "52-week" — it self-activates once the archive is deep enough, no code change needed.
- **Liquidity gate runs *before* scoring** (median 20-day traded value > ₹20 Cr). Note the journal layer softens this into a **tier** (`Priority` / `Watch` / `Size-limited`) rather than a hard exclusion — failing liquidity means small size, not "unscanned".
- **RVOL and SUE are ranked by percentile across the whole scanned universe**, not against fixed thresholds — a cross-stock dependency requiring a full-universe pass each evening *before* any single stock is scored.
- **Institutional Lifecycle** (Accumulation → Markup → Distribution → Markdown) is a **classification label, not a 10th score**, derived from how Stages 5–8 relate: `ABC — 96 — Early Markup`.
- Fundamental/earnings data changes slowly — compute monthly/quarterly and cache (that's what the monthly sheet is), don't recompute per run.

Data sourcing (v4 Appendix B): Zerodha = price/volume; Screener = fundamentals + quarterly results; bhavcopy = delivery + breadth. Earnings surprise is **SUE** (actual vs. the company's own seasonal trajectory), so no paid analyst-estimate feed is required; real estimates are an optional upgrade into the same criteria.
