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
data/bhavcopy/<year>/*.csv  ──────┘
   ↑ archive_bhavcopy.py (nightly, NO backfill — delivery/breadth history accrues forward only)
templates/*  ──→ new_month.py ──→ journal/<YYYY>/<MM-Month>/  (monthly.md + 3 CSVs, never overwrites)
```

The intended workflow is **top-down**: rank sectors first, then pick stocks *inside* the strong sectors. Three things make this pipeline unusual and must be preserved:

1. **Sector rotation runs off official NSE index data, and is a separate step that owns `sectors.csv`.** `rank_sectors.py` reads the archived `ind_close_all` files and ranks all **17 key Nifty sectoral indexes** (the `SECTORS` map — note the label→exact-index-name translation, e.g. `Nifty Fin Service` → `Nifty Financial Services`). Per sector it computes **1M/3M/6M returns**, **Relative Performance** (`rp = sector return − Nifty 50 return`) on each window, a **1–5 `rp_score`** (star bands on 3M RP: >15→5, 10–15→4, 5–10→3, 0–5→2, <0→1), the **RS-momentum** of the sector÷Nifty line, **`pct_off_6m_high`** (distance below the 6-month closing high; near-highs = money committed), **`accel`** (Y if `ret_1m > ret_3m/3` — recent month outpacing the quarter), and an **RRG `quadrant`**: **Leading** (ahead of Nifty + momentum rising), **Improving** (behind but momentum rising — the "next to become strong"), **Weakening** (ahead but momentum falling), **Lagging** (behind + falling). Rows are ranked by 3M RP. It also keeps **`stage2_pts`** (0–10, the v4-spec Stage 2 score: top-5 by 1M + top-5 by 3M + RS acceleration) for the scorer. `build_monthly.py` no longer touches `sectors.csv`. Because ranking uses index data, every sector is ranked even where the watchlist holds no stocks — that's why we retired the old watchlist-constituent estimate. **6M columns need ≥126 archived index days**; below that they're blank (backfill further with `archive_indices.py --from`).
2. **Bucket A / Bucket B split in `universe.csv`.** `build_monthly.py` owns only Bucket A (`median_trdval_cr`, `liquid`, `ret_1m_pct`, `ret_3m_pct` — the `BUCKET_A` tuple) and **merges by symbol, preserving every other cell**, so re-running never destroys hand-entered Bucket B (Screener fundamentals) or the judgment-assigned `tier`. Any new writer to `universe.csv` must follow the same merge-don't-clobber pattern.
3. **`watchlist.csv` sector labels stay free-form** (`Cement`, `Nifty Capital Goods`, …) — there is deliberately no canonical-name check in `validate_watchlist.py`. These labels group *your stocks* for stock-selection; they are **independent of** the 17 official indexes that `rank_sectors.py` ranks. (A future step will map a watchlist name's sector to its ranked official index; not built yet.)

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

- **Bhavcopy headers have leading spaces** (` SERIES`, ` DELIV_PER`). `build_monthly.py` sidesteps this with fixed column indices (`C_SYMBOL/C_SERIES/C_CLOSE/C_TURNOVER = 0,1,8,11`) — brittle if NSE changes the layout, so validate indices before trusting a new loader. `TURNOVER_LACS` is in lakh; divide by 100 for crore.
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
- **Missing data is renormalized, never scored 0:** `stage_score = (earned ÷ available) × nominal_weight`, plus a per-stock data-confidence flag. Scoring missing as 0 silently biases toward large caps.
- **Liquidity gate runs *before* scoring** (median 20-day traded value > ₹20 Cr). Note the journal layer softens this into a **tier** (`Priority` / `Watch` / `Size-limited`) rather than a hard exclusion — failing liquidity means small size, not "unscanned".
- **RVOL and SUE are ranked by percentile across the whole scanned universe**, not against fixed thresholds — a cross-stock dependency requiring a full-universe pass each evening *before* any single stock is scored.
- **Institutional Lifecycle** (Accumulation → Markup → Distribution → Markdown) is a **classification label, not a 10th score**, derived from how Stages 5–8 relate: `ABC — 96 — Early Markup`.
- Fundamental/earnings data changes slowly — compute monthly/quarterly and cache (that's what the monthly sheet is), don't recompute per run.

Data sourcing (v4 Appendix B): Zerodha = price/volume; Screener = fundamentals + quarterly results; bhavcopy = delivery + breadth. Earnings surprise is **SUE** (actual vs. the company's own seasonal trajectory), so no paid analyst-estimate feed is required; real estimates are an optional upgrade into the same criteria.
