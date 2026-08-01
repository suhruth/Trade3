# Stock scoring (Bucket C of `universe.csv`) — column reference

Quick reference for `source/rank_stocks.py`'s output: the sector→stock bridge plus
v4 Stages 2, 5, and 6, written as 19 columns appended to `journal/<…>/universe.csv`
(Bucket C — see `CLAUDE.md`'s Bucket A/B/C split). One row per watchlist stock.

Pipeline position (third stage, both predecessors must have already run this month):

```
rank_sectors.py  -->  build_monthly.py  -->  rank_stocks.py
(sectors.csv)         (universe.csv,          (universe.csv,
                        Bucket A)               Bucket C)
```

## Why this script exists: the sector-label bridge

`watchlist.csv` stores each stock's sector as the exact NSE index name (e.g.
`Nifty Financial Services`), while `sectors.csv` (from `rank_sectors.py`) keys its
rows on the `SECTORS` dict's *friendly* labels (e.g. `Nifty Fin Service`). A naive
string join between the two silently fails for every sector where those diverge.
`rank_stocks.py` resolves this with a normalized reverse lookup over `SECTORS`
(matching both the dict's keys and values), writing the resolved key to
`sector_canon`. Two watchlist labels — `Cement`, `Nifty Capital Goods` — don't
correspond to any of the 17 ranked indexes at all; those stocks get `sector_canon`
left blank rather than a hard failure, with a warning printed at run time.

## Header

```
sector_canon,sector_rank,sector_quadrant,stage2_pts,
rvol,rvol_pts,deliv_surge,vol_persist,close_range_pct,stage5_pts,
rs_nifty,rs_sector,mom_pctile,stage6_pts,
score_pts,pts_available,score_100,stages_covered,score_conf
```

| Column | Type | Meaning |
|---|---|---|
| `sector_canon` | `SECTORS` key or blank | Resolved sector — blank means the watchlist label didn't bridge to any tracked index |
| `sector_rank` | int or blank | That sector's rank from this month's `sectors.csv` |
| `sector_quadrant` | Leading/Improving/Weakening/Lagging or blank | Drives the Buy Watchlist filter (Leading + Improving only) |
| `stage2_pts` | 0–10 or blank | Copied verbatim from `sectors.csv` — Stage 2 is a pure join, no new math |
| `rvol` | ratio, 2dp | Today's volume ÷ its own prior-20-day average (excludes today) |
| `rvol_pts` | 0/2/4/6 | RVOL percentile band across the whole watchlist (not a fixed threshold) |
| `deliv_surge` | ratio, 2dp or blank | Today's `DELIV_PER` ÷ its own prior-20-day average |
| `vol_persist` | 0–5 or blank | Of the last 5 sessions, how many closed above their own 20-day average volume |
| `close_range_pct` | 0–100, 1dp or blank | `(close − low) / (high − low) × 100` — where in the day's range it closed |
| `stage5_pts` | 0–15, 1dp | Stage 5 (Institutional Activity), renormalized over whichever of the above were computable |
| `rs_nifty` | Y/N or blank | Stock ÷ Nifty50 line positive & rising, at a 3-month RS-line high |
| `rs_sector` | Y/N or blank | Stock ÷ its sector index line positive & rising — blank when `sector_canon` is blank |
| `mom_pctile` | 0–100, 1dp | Percentile rank of this stock's `ret_3m_pct` across the watchlist (diagnostic; the tier gate itself uses top-20%) |
| `stage6_pts` | 0–15, 1dp | Stage 6 (Relative Strength), renormalized over whichever criteria were computable |
| `score_pts` | 0–40, 1dp | Sum of the renormalized Stage 2 + 5 + 6 scores |
| `pts_available` | int, ≤37 today | Total criterion-level points that were actually measurable — the raw confidence number |
| `score_100` | 0–100, 1dp | `earned ÷ pts_available × 100` — the ranking key. **A projection from what was measured, not a full v4 score** |
| `stages_covered` | e.g. `3/9` | How many of the v4 model's 9 stages contributed anything (max 3 today: Stages 1/3/4/7/8/9 aren't implemented) |
| `score_conf` | HIGH/MED/LOW | Band on `pts_available` — treat LOW as "needs more data or manual review", not "weak stock" |

## The three stages, criterion by criterion

**Stage 2 — Sector Rotation (10 pts, pure join).** No new math: `stage2_pts` is
copied straight from the stock's `sector_canon` row in `sectors.csv`. Available (10)
if the sector bridged and has a `sectors.csv` row; unavailable (0) otherwise.

**Stage 5 — Institutional Activity (15 pts, no sector dependency):**

| Criterion | Mechanical test | Pts |
|---|---|---|
| RVOL percentile | Ranked across the whole watchlist: top 5%→6, top 10%→4, top 20%→2, else 0 | 6 |
| Delivery surge | `deliv_surge > 1.5` | 4 |
| Volume persistence | `vol_persist ≥ 3` | 3 |
| Strong close | `close_range_pct ≥ 75` | 2 |

**Stage 6 — Relative Strength (15 pts, one sector-dependent criterion):**

| Criterion | Mechanical test | Pts |
|---|---|---|
| RS vs Nifty | `rs_nifty == "Y"` | 5 |
| RS vs own sector | `rs_sector == "Y"` | 4 |
| 52-week high | New 52-week high, or within 3% of it | 3 |
| Universe-relative momentum | `ret_3m_pct` in the watchlist's top 20% | 3 |

## Renormalization — worked example

CLAUDE.md's invariant: `stage_score = (earned ÷ available) × nominal_weight` —
missing data is never scored 0, only renormalized out. Applied at **both**
criterion level (within a stage) and stage level (across the composite).

Take a stock in an unmapped sector (e.g. `ULTRATECH`, sector `Cement`) with a full
Stage 5 (earns 6 of 15 available RVOL/delivery/etc.) and only the Nifty-RS and
momentum criteria available in Stage 6 (RS-vs-sector and 52-week-high both
unavailable):

- Stage 2: unavailable (`sector_canon` blank) → 0 earned, 0 available
- Stage 5: 6 earned / 15 available → `stage5_pts = 6/15 × 15 = 6.0`
- Stage 6: say 5 earned (RS-vs-Nifty) / 8 available (5 + 3, since sector-RS and
  52w are both out) → `stage6_pts = 5/8 × 15 = 9.4`
- `score_pts = 0 + 6.0 + 9.4 = 15.4` (out of a nominal 40)
- `pts_available = 0 + 15 + 8 = 23`
- `score_100 = (6 + 5) / 23 × 100 = 47.8` — the ranking key
- `stages_covered = 2/9` (Stage 2 didn't contribute anything), `score_conf = LOW`

## Why some cells are blank

- **`sector_canon` and everything downstream of it** (`sector_rank`,
  `sector_quadrant`, `stage2_pts`, `rs_sector`) are blank for any watchlist stock
  whose sector label doesn't bridge to one of the 17 tracked indexes — currently
  `Cement` and `Nifty Capital Goods`. This is a **data gap, not a zero** — those
  stocks still get scored on Stage 5 and the Stage-6 criteria that don't need a
  sector, just with fewer available points and a lower `score_conf`.
- **`rvol`/`deliv_surge`/`vol_persist`/`close_range_pct`** are blank when there
  isn't enough trailing history yet, or (for delivery) when NSE published a
  blank/`-` delivery % for that session.
- **The 52-week-high criterion (3 of Stage 6's 15 pts) is blank for every stock
  today**, deliberately: the bhavcopy archive only goes back to ~2026-04-01, far
  short of the 252 sessions a real 52-week window needs. Rather than compute a
  "52-week high" off a ~4-month window and mislabel it, this criterion stays
  unavailable — and Stage 6 renormalizes over the remaining 12 points — until the
  archive is actually deep enough. No code change needed when that day comes; it
  self-activates.

## How to use this

Hunt inside `sector_quadrant ∈ {Leading, Improving}` — same rule as
`sectors.csv` (see `docs/sectors-csv-reference.md`). `rank_stocks.py` prints a
ranked Buy Watchlist restricted to exactly that filter, sorted by `score_100`,
top 15. Treat `score_conf = LOW` as "look at this by hand before trusting the
number," not as a verdict on the stock. Remember `score_100` is not a full v4
score — until Stages 1/3/4/7/8/9 exist, it's a projection from whatever subset
was actually measured that run.
