# Institutional Swing Trading — Weighted Scoring Model (v4)
### 100-point percentage scale · 9-stage pipeline · fully mechanical · with Dan Zanger's Setups & Rules

A stock only reaches your watchlist after being scored. No discretionary "this chart looks nice" entries — and in v4, *no discretionary scoring either*: every criterion is a computable test, so the scanner produces the same number every time.

> **v4 changes (over [v3](institutional-swing-scoring-model.md)):**
> 1. **Every criterion is now mechanical.** The subjective items in Stages 7–8 (Wyckoff "characteristics," "tight range," "one of Zanger's setups clearly formed") are replaced by concrete formulas and a pattern-detection appendix. This closes v3's one real contradiction — it opened by rejecting discretion but still required chart-squinting to score.
> 2. **Redundancy trimmed.** v3 measured relative strength, sector strength, and volume in overlapping ways, so the score was really ~3 correlated factors dressed as 8. Overlapping criteria are merged and their points redirected to genuinely independent signals. Stage-level weights are unchanged (still summing to 100) so backtest re-tuning carries over.
> 3. **Missing-data rule added.** v3 had no rule for un-scoreable criteria, which silently penalized under-covered mid/small caps (exactly where institutional accumulation edge often lives). v4 renormalizes and flags low-data scores instead of scoring missing = 0.
> 4. **Risk gate hardened for swing trading:** ATR-based stops, a gap policy, and a time stop.
> 5. **Self-derived inputs, no paid feeds required.** Stage 4 now measures earnings surprise via **SUE** (Standardized Unexpected Earnings) computed from reported quarterly results — so it's fully mechanical and always available, with no analyst-estimate dependency. Market breadth and all delivery-% metrics are derived from the free NSE bhavcopy you archive nightly. See **Appendix B**. Real analyst estimates become an optional *upgrade*, not a requirement.
>
> **Kept from v3 unchanged in spirit:** percentage weighting, the Activity-vs-RS split, the Accumulation-vs-Breakout split, percentile RVOL, delivery-% usage, and lifecycle-as-a-label (not a score). These were the right calls.

---

## The 9-Stage Pipeline

```
Stage 1: Market Health           →  10 pts
Stage 2: Sector Rotation         →  10 pts
Stage 3: Fundamental Quality     →  15 pts
Stage 4: Earnings Quality        →  10 pts
Stage 5: Institutional Activity  →  15 pts
Stage 6: Relative Strength       →  15 pts
Stage 7: Accumulation Structure  →  10 pts
Stage 8: Breakout / Entry        →  15 pts
                                    ─────────
                                    100 pts

Stage 9: Risk + Execution        →  Pass/Fail gates (unscored)
```

Confirm the environment, confirm the sector, confirm the business, confirm the money is real and price is responding, confirm the chart is accumulating or breaking — then, and only then, manage risk and execution.

---

## Daily workflow — kept deliberately simple

The mechanical definitions below live in the *scanner*, not in your daily routine. Your day is unchanged from the v3 intent:

1. Run the evening batch. It ranks the universe and outputs one line per qualifier: `SYMBOL — score — lifecycle label — data-confidence flag`, e.g. `ABC — 92 — Early Markup — Full`.
2. Read from the top of the A+/A list.
3. For each candidate you act on, run the per-trade Risk + Execution gates (Stage 9). That's the only checklist you fill in by hand.

No chart-grading, no judgment calls in the score itself. That is the whole point of making the criteria mechanical.

---

## Missing-data rule (applies to every stage)

Institutions accumulate under-covered names; don't let the model punish a stock for *analyst neglect* rather than weakness.

- Score each stage only on the criteria whose inputs are **actually available**. If an input is genuinely missing (not zero — missing), drop that criterion from **both** the earned points and the stage's available maximum, then scale to the nominal weight:
  `stage_score = (earned ÷ available) × nominal_weight`
- Never treat missing data as a failed criterion (that is a silent large-cap bias).
- Compute a **data-confidence flag** per stock: `Full` if scored on ≥ 90% of nominal points, `Partial` if 75–90%, `Low` if < 75%. Show it beside the score. A 90 built on `Low` data is not the same trade as a 90 on `Full` data.

> With v4's self-derived inputs (SUE, breadth and delivery from bhavcopy — see Appendix B), almost every criterion is always computable. A `Partial`/`Low` flag now signals genuinely absent *fundamentals* (e.g. a just-listed company with < 5 quarters of results), not merely a lack of analyst coverage.

---

## Liquidity Filter — Gate, runs before scoring

A stock that fails this never gets scored; it isn't investable at your size regardless of everything else.

- Minimum: **median** daily traded value over the last 20 sessions > ₹20 Cr (median, not a single day — one spike shouldn't qualify an illiquid name).
- Preferred: ₹50 Cr+.

---

## Stage 1: Market Health — 10 pts

| Criterion | Mechanical test | Points |
|---|---|---|
| Nifty above 20 EMA | Close > 20 EMA | 2 |
| Nifty above 50 EMA | Close > 50 EMA | 2 |
| Market structure = HH/HL | Latest swing high > prior swing high **and** latest swing low > prior swing low, over the last ~20 sessions | 3 |
| Breadth positive | advances > declines across the NSE universe, computed from bhavcopy; **or** the stronger gauge — % of the universe above its own 50-DMA > 50% (see Appendix B) | 3 |

> **Regime cap:** if Nifty is below both EMAs **and** structure is lower-highs/lower-lows, cap every stock's max achievable score at **65** for the day. (v3 said "60–70"; a range isn't a rule — one number is.)

---

## Stage 2: Sector Rotation — 10 pts

*v3 counted sector strength three overlapping ways. v4 keeps three criteria but makes them independent: 1-month rank, 3-month rank, and **acceleration**.*

| Criterion | Mechanical test | Points |
|---|---|---|
| 1-month leadership | Sector index in the top 5 of ~20 NSE sector indices by 1-month return | 4 |
| 3-month leadership | Sector index in the top 5 by 3-month return | 3 |
| Relative-strength acceleration | Sector's RS line vs Nifty (sector ÷ Nifty) is above where it sat 20 sessions ago **and** above its own 50-day average | 3 |

---

## Stage 3: Fundamental Quality — 15 pts

| Criterion | Points |
|---|---|
| ROCE > 15% | 2 |
| ROE > 15% | 2 |
| Sales growth > 10% (YoY) | 2 |
| Profit growth > 10% (YoY) | 2 |
| Debt/Equity < 0.5 | 2 |
| Market cap above your threshold | 2 |
| Promoter pledge = 0 | 2 |
| Positive operating cash flow | 1 |

> Recompute monthly/quarterly and cache. Zanger barely used fundamentals — this stage is your addition on top of his price/volume method, not a veto over a hot Stage 5–8 setup.

---

## Stage 4: Earnings Quality — 10 pts

*Institutions react to improving **expectations**, not just good history. Analyst consensus is the textbook way to measure "surprise," but it's unavailable for most of the NSE mid/small-cap universe. v4 measures surprise instead via **SUE** — the actual result vs. the company's **own seasonal trajectory** — which is the standard method behind post-earnings-announcement-drift (exactly the institutional chasing this stage wants to catch). Fully mechanical, always available, and independent of price (so it doesn't double-count Stages 5–6). Full definition in **Appendix B**.*

| Criterion | Mechanical test | Points |
|---|---|---|
| EPS surprise | EPS **SUE** ranked in the top percentiles of the scanned universe (Appendix B) | 4 |
| Revenue surprise | Revenue **SUE** ranked in the top percentiles | 3 |
| Growth acceleration | TTM EPS growth rising quarter-on-quarter (2nd derivative > 0) **and** latest-quarter YoY profit growth > 20% | 3 |

> **All three criteria compute from Screener quarterly history alone** — no estimates, no analyst coverage required. An uncovered mid-cap is scored on the same footing as a large-cap.
>
> **Optional upgrade:** if you later buy real consensus estimates (e.g. Trendlyne), drop true actual-vs-estimate surprise into the EPS/Revenue slots — the scoring structure is identical, SUE just stops being the stand-in.
>
> **Caveat:** SUE is noisier for cyclical/seasonal or lumpy-earnings businesses; prefer PAT *excluding exceptional items* as the EPS input where available (the standardization step already dampens this).
>
> Note: this stage rewards reaction to **already-reported** earnings. The risk gate's "no earnings in your holding window" is about **upcoming** earnings — consistent, not contradictory.

---

## Stage 5: Institutional Activity — 15 pts

*Is money actually entering, regardless of whether price is responding yet?*

| Criterion | Mechanical test | Points |
|---|---|---|
| RVOL percentile ranking | see table below | up to 6 |
| Delivery % elevated | delivery surge > 1.5 — today's delivery % ÷ its own 20-day average (Appendix B) | 4 |
| Volume-expansion persistence | ≥ 3 of the last 5 sessions closed above the 20-day average volume (persistence, not one spike) | 3 |
| Strong close | close in the top 25% of the day's high-low range | 2 |

**RVOL ranking (percentile, not fixed threshold):**

| Rank among today's scanned NSE universe | Points |
|---|---|
| Top 5% by RVOL | 6 |
| Top 10% | 4 |
| Top 20% | 2 |
| Below top 20% | 0 |

> Percentile beats a fixed "RVOL ≥ 2": on a high-volatility day, 600+ names might clear 2× and the cutoff stops discriminating. Ranking always surfaces which names are exceptional *today*. **Ordering constraint:** rank the entire scanned universe by RVOL *before* scoring any single stock.

---

## Stage 6: Relative Strength — 15 pts

*Is price actually outperforming — the filter against "high volume from bad news"? v3 scored "RS vs Nifty positive & rising" and "outperforming Nifty over 1 month" separately; those are the same signal. v4 merges them and spends the freed points on a universe-relative rank.*

**RS line definition (used throughout):** `RS = stock price ÷ benchmark`. "Positive & rising" = the RS line is above its own 50-day average **and** above where it sat 20 sessions ago.

| Criterion | Mechanical test | Points |
|---|---|---|
| RS vs Nifty, rising to new highs | RS line vs Nifty positive & rising, at a 3-month RS-line high | 5 |
| RS vs own Sector, rising | RS line vs the stock's sector index positive & rising | 4 |
| At/near 52-week high | new 52-week high, or within 3% of it | 3 |
| Universe-relative momentum | 3-month total return in the top 20% of the scanned universe | 3 |

> **Stage 5 without Stage 6 is a warning, not a buy.** Huge volume with flat/negative RS is usually distribution, a news dump, or panic selling into strength — not accumulation.

---

## Stage 7: Accumulation Structure — 10 pts

*Early-entry evidence, before the breakout. v3's Wyckoff / "tight range" / "volume dry-up" wording required eyeballing. The mechanical triad below **is** the computable signature of Wyckoff accumulation — nothing is lost, and it scores identically every run.*

| Criterion | Mechanical test | Points |
|---|---|---|
| Volatility contraction | 10-day ATR% in the bottom quartile of its own 6-month range | 3 |
| Volume dry-up in the base | 20-day average volume < 70% of the prior 50-day average volume | 3 |
| Tight base | 20-day high-to-low range < 15% | 2 |
| Quiet accumulation | delivery-% 20-day trend rising (positive slope, or 5-day avg > 20-day avg) while price stays inside the base range (Appendix B) | 2 |

---

## Stage 8: Breakout / Entry Structure — 15 pts

*Late-entry / momentum evidence — the breakout itself. The six Zanger setups are now mechanical (Appendix A); the scanner reports which one, if any, is present.*

| Criterion | Mechanical test | Points |
|---|---|---|
| Qualifying breakout pattern | one of the six setups in **Appendix A** detected | 6 |
| Breakout volume confirmation (Zanger Rule #8) | breakout-day volume ≥ 1.5× the 50-day average | 3 |
| Close above pivot | close above the pattern's resistance/pivot level | 2 |
| Follow-through | next session holds above the breakout level (scoreable only at T+1; on the breakout day itself this criterion is deferred, not failed — handled by the missing-data rule) | 2 |
| No overhead supply | no prior consolidation or swing high within 10% above the pivot in the last 12 months | 2 |

> Score whichever **single** setup is most clearly formed — never average across overlapping patterns. No qualifying pattern = zero here, regardless of the other stages (Zanger Rule #1).

---

## Institutional Lifecycle — Classification Layer (shown alongside the score, not scored)

Institutions move **Accumulation → Markup → Distribution → Markdown.** This is a label derived from how Stages 5–8 relate — not a 9th score.

| Stage | Signature | What it means for entry |
|---|---|---|
| **Accumulation** | Stage 7 high, Stage 8 low, RS flat-to-improving | Early entry, wider stop, smaller size — you're ahead of the breakout |
| **Early Markup** | Stage 8 high, Stage 5 high, RS accelerating | Prime entry zone — the breakout stage's sweet spot |
| **Distribution** | price near highs, RS weakening/flat, closes off the day's high despite volume | Avoid new entries; tighten stops on existing positions |
| **Markdown** | RS negative, breaking below support, high volume on down days | Avoid entirely; if held, Rule #3 (cut fast) applies |

> Two stocks with the same score can be in opposite lifecycle stages — one entering, one exiting. Always read the label before acting on the number.

---

## Stage 9 — Risk Filter (Pass/Fail, not scored)

Runs after scoring, before capital commitment.

- [ ] **ATR-based stop defined:** stop = the tighter of `entry − 1.5 × ATR(14)` or just below the pattern base. Position size = risk budget ÷ (entry − stop).
- [ ] **Reward ≥ 3× risk** to the first logical resistance/target.
- [ ] **Gap policy:** if price gaps > 4% above the pivot at the open, do **not** chase — wait for a pullback to within 5% of the pivot, or skip (enforces Rule #2; Indian breakouts gap often).
- [ ] No major resistance immediately overhead.
- [ ] No earnings / major event within your holding window. *(Predict the next result date from the company's median reporting lag — Appendix B — and confirm against the NSE corporate-announcements feed ~2 weeks out.)*
- [ ] Liquidity sufficient for your size (see Liquidity Filter).

---

## Execution Discipline Gate — Zanger's Rules (Pass/Fail, per-trade)

- [ ] Entry within ~5% of breakout — not chasing an extended move (Rule #2)
- [ ] Waited for confirmation — didn't buy the instant the signal appeared (Rule #9)
- [ ] Stop just below the breakout area; automatic exit if price falls back into the base (Rule #3)
- [ ] Partial-profit plan set: sell ~20–30% at +15–20% from breakout (Rule #4)
- [ ] **Time stop:** if the trade hasn't cleared its first partial target *or* has fallen back into the base within **5–7 sessions**, exit — free the capital (extends Rule #5's "cut the choppy ones")
- [ ] Hold/cut discipline: let strong trends run, cut weak/choppy positions (Rule #5)
- [ ] Watching for reversal signs as the move matures — steepening trendlines, H&S, double tops, distribution (Rule #7)
- [ ] No margin unless you have a proven, stable system and stay disciplined under pressure (Rule #10)

---

## Grading Bands (out of 100)

| Score | Grade | Action |
|---|---|---|
| 85–100 | A+ | High-conviction candidate, prioritize |
| 70–84 | A | Strong candidate, standard sizing |
| 55–69 | B | Watchlist only, wait for improvement |
| Below 55 | C | Discard |

> Always read the score together with its **data-confidence flag**: treat an A+ on `Low` data as a B until more data confirms it.

---

## Appendix A — Zanger's Six Setups, mechanical detection

The scanner reports the single best-formed pattern. These are starting thresholds — tune them against your own backtest. `pivot` = the breakout trigger level.

| Setup | Mechanical definition (all measured on daily bars) |
|---|---|
| **Cup and Handle** | Prior uptrend ≥ 30%; a rounded base of 7–65 sessions with depth 12–35% and a smooth (not V) bottom; a handle in the upper half of the cup, depth < 12%, on volume below the cup's average; **pivot** = handle high. |
| **High Tight Flag** | Flagpole ≥ 80% gain in ≤ 8 weeks on above-average volume; then a flag pullback of only 10–25% over ≤ 5 weeks with volume contracting; **pivot** = flag high. (Rare — highest conviction when fully formed.) |
| **Ascending Triangle** | Prior uptrend; ≥ 2 touches of a flat horizontal resistance; rising lows (higher swing lows) into it; volume contracting on the approach; **pivot** = the horizontal resistance. |
| **Flat Base** | Prior uptrend; a sideways range ≤ 15% deep lasting ≥ 5 weeks; volume contracting; **pivot** = range top. |
| **Double Bottom** | Two lows within ~4% of each other separated by a rebound; the second low holds at/above the first; **pivot** = the middle peak between the two lows. |
| **Trendline / Resistance Breakout** | A descending trendline or horizontal level with ≥ 3 rejections; **pivot** = the trendline/level at the breakout bar; stop just below it. |

> A "detected" pattern must also clear Stage 8's volume, close-above-pivot, and overhead-supply criteria to earn full breakout points — the pattern alone is 6 of the 15.

---

## Appendix B — Deriving inputs without paid data

Everything the model needs is buildable from **Zerodha OHLCV + Screener quarterly fundamentals + a nightly NSE bhavcopy archive** (`sec_bhavdata_full`). No analyst-estimate feed is required. The one hard operational dependency: **download and store bhavcopy every trading day** — several metrics below need history you can only accumulate going forward.

### B1 · Earnings surprise → SUE (Standardized Unexpected Earnings)

A surprise is *actual vs. expectation*. Without analyst consensus, use the company's **own seasonal trajectory** as the expectation — the standard method behind post-earnings-announcement-drift research.

```
# Seasonal random walk (needs ≥ 5 quarters; ≥ 9 for a stable σ)
Expected_EPS(q) = EPS(q−4)                          # same quarter, prior year
Unexpected(q)   = EPS(q) − EPS(q−4)
SUE(q)          = Unexpected(q) / σ                 # σ = stdev of Unexpected over last 8 quarters

# Optional drift model (Foster) — better for trending earners:
Expected_EPS(q) = EPS(q−4) + mean(Unexpected over last 4–8 quarters)
```

- Standardizing by σ makes SUE dimensionless and comparable across the universe — so **rank SUE into percentiles** and score like RVOL (top 5% → full points). Revenue SUE is identical using quarterly revenue.
- Use PAT **excluding exceptional items** as the EPS input where Screener exposes it, to avoid one-off distortions.
- SUE is computed from financials only → it stays **independent of Stages 5–6**. Do *not* substitute a post-result price-gap proxy; that double-counts the reaction those stages already score.

### B2 · Growth acceleration (forward-outlook proxy)

The honest numeric stand-in for "improving guidance" — a *realized-trajectory* proxy, not true forward guidance (which needs concall-transcript NLP or a data vendor):

```
TTM_EPS      = sum of last 4 quarters' EPS
TTM_growth(t)= TTM_EPS(t) / TTM_EPS(t−4q) − 1
Accelerating = TTM_growth(this q) > TTM_growth(last q)      # 2nd derivative > 0
```

### B3 · Market breadth (from bhavcopy — replaces Chartink)

```
Advances = count(close > prev_close) across all NSE equities
Declines = count(close < prev_close)
Breadth  = Advances / (Advances + Declines)                # > 0.5 = positive day

# Stronger regime gauge (needs your own 50-DMA store):
PctAbove50DMA = count(close > 50-DMA) / universe_size       # > 0.5 healthy, > 0.6 strong
```

### B4 · Delivery metrics (from archived bhavcopy)

Bhavcopy reports delivery quantity and % directly. Derive:

```
DeliveryPct(t)    = DelivQty(t) / TradedQty(t) × 100        # or use the reported % column
DeliverySurge(t)  = DeliveryPct(t) / mean(DeliveryPct, 20d) # Stage 5:  > 1.5 = elevated
DeliveryTrend(t)  = slope of linear fit of DeliveryPct over 20d > 0
                    (simpler: mean(DeliveryPct, 5d) > mean(DeliveryPct, 20d))   # Stage 7
```

### B5 · Next earnings date (heuristic for the Stage 9 gate)

```
Predicted_result_date ≈ quarter_end + median(gap: quarter-end → announcement, last 4 results)
```

Companies report at a fairly stable lag. This yields a *window*; confirm against the NSE corporate-announcements feed ~2 weeks out before committing capital.

### Coverage summary

| Input | Source | Notes |
|---|---|---|
| OHLCV, EMAs, ATR, RVOL, 52w high, RS, patterns, gaps | Zerodha (Kite) | Historical API is a paid add-on; archive daily to cut calls |
| ROCE/ROE/growth/D-E/pledge/OCF/market cap | Screener | Recompute monthly/quarterly, cache |
| EPS/Revenue surprise | **SUE** from Screener quarterly (B1) | Optional upgrade: real estimates (Trendlyne) |
| Growth acceleration | Screener quarterly (B2) | Proxy for guidance |
| Breadth | **Bhavcopy** (B3) | No Chartink needed |
| Delivery % + history | **Bhavcopy, archived daily** (B4) | Hard dependency: store nightly |
| Next earnings date | Reporting-lag heuristic (B5) | Confirm via NSE announcements |

---

## Why this structure

- **Activity split from Relative Strength** stops the model rewarding high-volume names being *sold into* — Activity confirms money is moving, RS confirms price is winning because of it.
- **Accumulation split from Breakout** lets one framework serve two styles: early positioning, or momentum entry after confirmation.
- **Percentage weighting** means backtest evidence moves points between stages (e.g. RS 15→20, Fundamentals 15→10) and the model still sums to 100 — no boundary recalculation.
- **Mechanical criteria** make the score reproducible and backtestable — you cannot backtest a chart you scored by eye.
- **The missing-data rule** keeps the model honest about *under-covered* names instead of quietly favoring large caps.
- **Lifecycle stays unscored on purpose** — context for reading the number, not another number. A 90 in Distribution and a 90 in Early Markup are not the same trade.

---

## Next steps

1. **Start the bhavcopy archive now** — delivery trends (Stage 7), delivery surge (Stage 5), and breadth (Stage 1) all need history you can only accumulate going forward (Appendix B). Every day you don't archive is a day you can't backfill.
2. Encode each stage's mechanical test as a scanner function. Remember the ordering constraints: **RVOL percentile and SUE percentile both require ranking the whole universe before scoring any single stock**, and fundamentals/earnings should be computed monthly/quarterly and cached.
2. Output `SYMBOL — score — lifecycle — data-confidence`, e.g. `ABC — 92 — Early Markup — Full`.
3. Backtest weight sensitivity: rerun historical trades with stage weights shifted and see which weighting actually correlates with your winners. Tune the Appendix A pattern thresholds the same way.
4. Batch-job target: NSE Data → Market Analyzer → Sector Rotation → Fundamental/Earnings Screener → Institutional Activity + RS Engine → Pattern Recognition (Accumulation/Breakout) → Lifecycle Classifier → Risk Engine → ranked output.
