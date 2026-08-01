# Stock scoring (Bucket C of `universe.csv`) — column reference

Quick reference for `source/rank_stocks.py`'s output: the sector→stock bridge plus
v4 Stages 2, 5, 6, 7, and 8, written as 31 columns appended to `journal/<…>/universe.csv`
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
vol_contraction,vol_dryup,tight_base,quiet_accum,stage7_pts,
pattern,pivot,vol_confirm,close_above_pivot,follow_through,no_overhead_supply,stage8_pts,
score_pts,pts_available,score_100,stages_covered,score_conf
```

| Column | Type | Meaning |
|---|---|---|
| `sector_canon` | `SECTORS` key or blank | Resolved sector — blank means the watchlist label didn't bridge to any tracked index |
| `sector_rank` | int or blank | That sector's rank from this month's `sectors.csv` |
| `sector_quadrant` | Leading/Improving/Weakening/Lagging or blank | Drives the Buy Watchlist filter (Leading + Improving only) |
| `stage2_pts` | 0–10 or blank | Copied verbatim from `sectors.csv` — Stage 2 is a pure join, no new math |
| `rvol` | ratio, 2dp | Today's volume ÷ its own prior-20-day average (excludes today) |
| `rvol_pts` | 0/2/4/6 | RVOL percentile band ranked against every **liquid NSE EQ symbol** (not just the watchlist — see below) |
| `deliv_surge` | ratio, 2dp or blank | Today's `DELIV_PER` ÷ its own prior-20-day average |
| `vol_persist` | 0–5 or blank | Of the last 5 sessions, how many closed above their own 20-day average volume |
| `close_range_pct` | 0–100, 1dp or blank | `(close − low) / (high − low) × 100` — where in the day's range it closed |
| `stage5_pts` | 0–15, 1dp | Stage 5 (Institutional Activity), renormalized over whichever of the above were computable |
| `rs_nifty` | Y/N or blank | Stock ÷ Nifty50 line positive & rising, at a 3-month RS-line high |
| `rs_sector` | Y/N or blank | Stock ÷ its sector index line positive & rising — blank when `sector_canon` is blank |
| `mom_pctile` | 0–100, 1dp | Percentile rank of this stock's `ret_3m_pct` against the full liquid-universe pool (diagnostic; the tier gate itself uses top-20%) |
| `stage6_pts` | 0–15, 1dp | Stage 6 (Relative Strength), renormalized over whichever criteria were computable |
| `vol_contraction` | Y/N or blank | Today's 10-day ATR% in the bottom quartile of its own 6-month range — blank until 136 sessions are archived (see below) |
| `vol_dryup` | Y/N or blank | Recent 20-day average volume < 70% of the prior 50-day average |
| `tight_base` | Y/N or blank | 20-day high-to-low range < 15% of the low |
| `quiet_accum` | Y/N or blank | Delivery-% trend rising (5d avg > 20d avg) while price hasn't broken above its own base |
| `stage7_pts` | 0–10, 1dp | Stage 7 (Accumulation Structure), renormalized over whichever of the above were computable |
| `pattern` | one of six Appendix-A names or blank | The single most-clearly-formed pattern detected, or blank if none (see below — blank ≠ unavailable here) |
| `pivot` | price, 2dp or blank | The detected pattern's breakout trigger level |
| `vol_confirm` | Y/N or blank | Breakout-day volume ≥ 1.5× the 50-day average (Zanger Rule #8) |
| `close_above_pivot` | Y/N or blank | Today's close above the pattern's pivot |
| `follow_through` | Y/N or blank | Only ever non-blank the single session after a breakout crossing — otherwise deferred |
| `no_overhead_supply` | Y/N or blank | No swing high within 10% above the pivot in the last 252 sessions — blank until that much history is archived |
| `stage8_pts` | 0–15, 1dp | Stage 8 (Breakout/Entry), renormalized over whichever of the above were computable — see the Zanger Rule #1 note below for why "no pattern" is a real 0, not blank |
| `score_pts` | 0–65, 1dp | Sum of the renormalized Stage 2 + 5 + 6 + 7 + 8 scores |
| `pts_available` | int, ≤59 today | Total criterion-level points that were actually measurable — the raw confidence number |
| `score_100` | 0–100, 1dp | `earned ÷ pts_available × 100` — the ranking key. **A projection from what was measured, not a full v4 score** |
| `stages_covered` | e.g. `5/9` | How many of the v4 model's 9 stages contributed anything (max 5 today: Stages 1/3/4/9 aren't implemented) |
| `score_conf` | HIGH/MED/LOW | Band on `pts_available` — treat LOW as "needs more data or manual review", not "weak stock" |

## The five stages, criterion by criterion

**Stage 2 — Sector Rotation (10 pts, pure join).** No new math: `stage2_pts` is
copied straight from the stock's `sector_canon` row in `sectors.csv`. Available (10)
if the sector bridged and has a `sectors.csv` row; unavailable (0) otherwise.

**Stage 5 — Institutional Activity (15 pts, no sector dependency):**

| Criterion | Mechanical test | Pts |
|---|---|---|
| RVOL percentile | Ranked against the liquid-universe pool: top 5%→6, top 10%→4, top 20%→2, else 0 | 6 |
| Delivery surge | `deliv_surge > 1.5` | 4 |
| Volume persistence | `vol_persist ≥ 3` | 3 |
| Strong close | `close_range_pct ≥ 75` | 2 |

**Stage 6 — Relative Strength (15 pts, one sector-dependent criterion):**

| Criterion | Mechanical test | Pts |
|---|---|---|
| RS vs Nifty | `rs_nifty == "Y"` | 5 |
| RS vs own sector | `rs_sector == "Y"` | 4 |
| 52-week high | New 52-week high, or within 3% of it | 3 |
| Universe-relative momentum | `ret_3m_pct` in the liquid-universe pool's top 20% | 3 |

**Stage 7 — Accumulation Structure (10 pts, no sector dependency).** The
pre-breakout "quietly being accumulated" signature — early-entry evidence,
before Stage 8's breakout even fires:

| Criterion | Mechanical test | Pts |
|---|---|---|
| Volatility contraction | Today's 10-day ATR% ranks in the bottom quartile of its own trailing 126-session (6-month) distribution | 3 |
| Volume dry-up | Recent 20-day average volume < 70% of the prior (non-overlapping) 50-day average | 3 |
| Tight base | 20-day high-to-low range < 15% of the low | 2 |
| Quiet accumulation | Delivery-% trend rising (5-day avg > 20-day avg) **while** price hasn't closed above its own 20-day base high (`close[-1] < base_high`) — the qualifier that stops this double-counting an already-fired Stage 8 breakout | 2 |

ATR is a simple (not Wilder-smoothed) average of True Range — a starting
threshold per the spec's own convention for Appendix A patterns; tune against
a backtest. Volatility contraction needs `ATR_LOOKBACK + ATR_WINDOW = 136`
sessions and stays unavailable (not faked on a shorter window) until the
archive is that deep — identical policy to Stage 6's 52-week-high criterion.
With ~89 days archived today, this is the one Stage 7 criterion still blank
for every stock; the other three activate as soon as their own (much
shorter) history windows are met.

**Stage 8 — Breakout/Entry (15 pts, no sector dependency).** The actual
trigger — Appendix A's six mechanical Zanger setups, plus confirmation that
the breakout is real:

| Criterion | Mechanical test | Pts |
|---|---|---|
| Qualifying pattern | One of six Appendix-A setups detected (see below) | 6 |
| Breakout volume confirmation | Today's volume ≥ 1.5× the 50-day average (Zanger Rule #8) | 3 |
| Close above pivot | Today's close above the pattern's pivot | 2 |
| Follow-through | The session *after* a breakout crossing still holds above the pivot — deferred (not failed) on the breakout day itself, and not evaluated at all outside that single T+1 window | 2 |
| No overhead supply | No swing high within 10% above the pivot in the trailing 252 sessions | 2 |

**The six patterns**, each returning a pivot and a "conviction" score used to
pick the single most-clearly-formed one (never averaged, per Zanger Rule #1):

| Pattern | Mechanical proxy |
|---|---|
| Cup and Handle | Prior uptrend ≥30%, a rounded (≥3 sessions near the low, not a V) 65-session base with 12–35% depth, a handle in the upper half with <12% depth on below-average volume |
| High Tight Flag | A ≥80% flagpole in ≤40 sessions on above-average volume, then a 10–25% pullback over ≤25 sessions with volume contracting — searched across qualifying pole/flag length combinations |
| Ascending Triangle | Prior uptrend, ≥2 swing-high touches of a flat resistance (within 2%), rising swing lows, volume contracting |
| Flat Base | Prior uptrend, ≤15%-deep sideways range over ≥25 sessions, volume contracting |
| Double Bottom | Two swing lows within 4% of each other, ≥5 sessions apart, separated by a rebound of ≥15% — anchored on the window's single deepest swing low, not any pair among several similarly-deep ones |
| Trendline/Resistance Breakout | **Simplified** to a flat level with ≥3 swing-high rejections within 2% of it — a true diagonal trendline fit (linear regression through the touches) isn't implemented |

**Zanger Rule #1 exception to the missing-data rule:** unlike every other
criterion in this document, "no qualifying pattern found" is a real,
**fully-available zero** (`stage8_pts = 0.0`, `pattern` blank), not missing
data — once there's enough history to have checked all six patterns at all
(`MIN_STAGE8_SESSIONS`, currently 45 sessions), a stock that clears none of
them genuinely isn't set up, and the spec is explicit that this scores zero
regardless of the other stages. Only when history is shorter than that is
Stage 8 truly unavailable (blank `stage8_pts`).

**These are starting thresholds, not backtested ones** — the spec's own
words for Appendix A, and worth taking seriously: an early version of the
Double Bottom detector matched on any two of a window's four deepest swing
lows and fired on nearly every stock regardless of ticker. It was tightened
to anchor on the single deepest low and require a genuine ≥15% rebound
before being trusted, but every pattern here is a mechanical *approximation*
of a visual concept — verify against a real backtest before sizing a trade
on `pattern` alone, exactly as the model spec recommends.

## The percentile pool: full liquid NSE universe, not just the watchlist

RVOL and 3-month momentum are the two criteria that compare a stock against
*other* stocks, not just its own history — and that comparison is now made
against every liquid NSE EQ symbol scanned in the archive, not only the 45
watchlist names. `build_universe_pool()` reads every EQ symbol's bhavcopy row
(no `wanted` filter), applies the same liquidity gate `build_monthly.py`
already uses (`median 20-day traded value > ₹20 Cr`, `LIQUID_CR`), and computes
RVOL/3M-return only for symbols that clear it — illiquid names are excluded
from the pool entirely so "top 5%" stays a meaningful bar instead of something
any thinly-traded ticker can clear on a quiet day. A watchlist stock's own
freshly-computed value is merged into that pool before ranking, so its
`rvol_pts`/`mom_pctile` reflect its real position against the whole liquid
market — the point of this scope (surfacing a mover you haven't already
hand-picked, per `CLAUDE.md`'s own "ranked by percentile across the whole
scanned universe" invariant). The run's console output reports pool size each
time, e.g. `Liquid-universe pool: 612/2043 NSE EQ symbols pass the ₹20 Cr
liquidity gate`.

This is one of two widened-scope pieces. The other is that Stage 5, Stage 6's
non-sector criteria, and all of Stages 7 and 8 are now computed for every
liquid NSE stock, not only the watchlist — see "Beyond the watchlist" below.
Only `sector_canon` and everything that depends on it (Stage 2, `rs_sector`)
stay watchlist-only, since sector membership is simply data this repo
doesn't have for a random NSE stock.

## Renormalization — worked example

CLAUDE.md's invariant: `stage_score = (earned ÷ available) × nominal_weight` —
missing data is never scored 0, only renormalized out. Applied at **both**
criterion level (within a stage) and stage level (across the composite).

Take a stock in an unmapped sector (e.g. `ULTRATECH`, sector `Cement`) with a full
Stage 5 (earns 6 of 15 available RVOL/delivery/etc.), only the Nifty-RS and
momentum criteria available in Stage 6 (RS-vs-sector and 52-week-high both
unavailable), and a full Stage 7 minus volatility-contraction (earns both
volume dry-up and tight base, quiet-accumulation and vol-contraction unavailable):

- Stage 2: unavailable (`sector_canon` blank) → 0 earned, 0 available
- Stage 5: 6 earned / 15 available → `stage5_pts = 6/15 × 15 = 6.0`
- Stage 6: say 5 earned (RS-vs-Nifty) / 8 available (5 + 3, since sector-RS and
  52w are both out) → `stage6_pts = 5/8 × 15 = 9.4`
- Stage 7: 5 earned (dry-up 3 + tight base 2) / 5 available (quiet-accum and
  vol-contraction both out) → `stage7_pts = 5/5 × 10 = 10.0`
- `score_pts = 0 + 6.0 + 9.4 + 10.0 = 25.4` (out of a nominal 50)
- `pts_available = 0 + 15 + 8 + 5 = 28`
- `score_100 = (6 + 5 + 5) / 28 × 100 = 57.1` — the ranking key
- `stages_covered = 3/9` (Stage 2 didn't contribute anything), `score_conf = LOW`
  (28 < `CONF_MED = 32`)

## Why some cells are blank

- **`sector_canon` and everything downstream of it** (`sector_rank`,
  `sector_quadrant`, `stage2_pts`, `rs_sector`) are blank for any watchlist stock
  whose sector label doesn't bridge to one of the 17 tracked indexes — currently
  `Cement` and `Nifty Capital Goods`. This is a **data gap, not a zero** — those
  stocks still get scored on Stage 5, Stage 7, and the Stage-6 criteria that
  don't need a sector, just with fewer available points and a lower `score_conf`.
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
- **`vol_contraction` (3 of Stage 7's 10 pts) is blank for every stock today**
  for the identical reason, needing 136 sessions instead of 252 — see the
  Stage 7 section above.
- **`pattern`/`pivot`/Stage 8's dependent criteria are blank when no pattern
  fired *and* history is too short to have checked (`< MIN_STAGE8_SESSIONS`,
  45 sessions).** Once that history exists, "no pattern" is a real,
  non-blank `stage8_pts = 0.0` — see the Zanger Rule #1 note above, the one
  deliberate exception to "blank means missing" in this whole document.
- **`follow_through` is blank almost always**, not because of missing
  history but because it's only ever meaningful the single session right
  after a breakout crossing — every other day it's correctly deferred.
- **`no_overhead_supply` is blank for every stock today**, needing the same
  252 sessions as Stage 6's 52-week-high.

## How to use this

Hunt inside `sector_quadrant ∈ {Leading, Improving}` — same rule as
`sectors.csv` (see `docs/sectors-csv-reference.md`). `rank_stocks.py` prints a
ranked Buy Watchlist restricted to exactly that filter, sorted by `score_100`,
top 15, and saves the same rows/order to `journal/<month>/shortlist.csv`.
Treat `score_conf = LOW` as "look at this by hand before trusting the
number," not as a verdict on the stock. Remember `score_100` is not a full v4
score — until Stages 1/3/4/9 exist, it's a projection from whatever subset
was actually measured that run. A non-blank `pattern` with `close_above_pivot
= N` is a "watch for the breakout" case, not a "buy now" one — check both
columns together, not `pattern` alone.

## Beyond the watchlist: `journal/<month>/discoveries.csv`

Every liquid NSE EQ stock — not just the watchlist — is scored on Stages 5,
6, 7, and 8 using the same functions above (`canon_by_symbol.get()`
naturally returns `None` for a non-watchlist symbol, so it flows through
exactly like a watchlist stock whose sector didn't bridge). But only
watchlist stocks have a *known* sector, so only they can ever pass the
shortlist's Leading/Improving gate — a random NSE stock's sector is simply
not data this repo has. Rather than silently drop a strong-scoring
non-watchlist stock, it's written to `discoveries.csv` instead: the top 30
by `score_100`, sector unverified.

Two things to know before trusting a row in this file:

- **`score_conf` usually reads `LOW` here, but `MED` is reachable** (e.g.
  `REDINGTON` hit `MED` on 2026-07-31) now that Stage 8 typically contributes
  its full 15 points to `pts_available` even when no pattern fires (Zanger
  Rule #1 — see above). The rest is variable: Stage 6/7's *available* points
  (not just earned) fluctuate stock to stock depending on which criteria
  happened to compute, so the exact ceiling isn't fixed the way it is for a
  watchlist stock. `HIGH` stays permanently out of reach without a sector
  (Stage 2's 10 and Stage 6's sector-RS 4 points can never be earned). This
  matches the *existing* behavior for the watchlist's own unmapped-sector
  stocks (`Cement`, `Nifty Capital Goods`); it isn't a lesser bar for
  discoveries, just the same bar these stocks can never fully clear.
- **At least 2 of Stages 5/6/7/8 must contribute to appear at all.** A stock
  scoring on a single fully-earned stage renormalizes to a misleadingly
  "perfect" `score_100 = 100.0` — technically correct arithmetic, but not
  evidence worth acting on. This filter removes that noise; the model
  invariant itself (renormalize, never score missing as zero) is unchanged.
  Stage 8 alone can't trigger this by itself: a "no pattern" zero is one
  contributing stage, not two.

Treat a `discoveries.csv` row as a lead, not a candidate: research its actual
sector by hand (and its official index membership, if any) before deciding
whether it belongs in the watchlist.
