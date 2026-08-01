# Institutional Swing Trading — Weighted Scoring Model (v3)
### 100-point percentage scale · 9-stage pipeline · with Dan Zanger's Setups & Rules

A stock only reaches your watchlist after being scored. No discretionary "this chart looks nice" entries.

**v3 changes:** moved from a fixed 110-point system to a **percentage-weighted 0–100 score**, so weights can be re-tuned from backtest evidence without recalculating grade boundaries. Institutional Filter is split into **Activity** (is money moving?) vs **Relative Strength** (is price actually outperforming?) — volume alone can mean bad news, not accumulation. Chart structure is split into **Accumulation** vs **Breakout**, so the framework catches both early and momentum entries. Added Earnings Quality, RVOL ranking (percentile, not fixed threshold), a Liquidity gate, and an Institutional Lifecycle classification layered on top of the score.

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

This follows how institutions actually operate: confirm the environment, confirm the sector, confirm the business, confirm the money is real and price is responding, confirm the chart is accumulating or breaking, then — only then — manage risk and execution.

---

## Liquidity Filter — Gate, runs before scoring

A stock that fails this never gets scored at all; it's not investable at your size regardless of everything else.

- Minimum: Daily traded value > ₹20 Cr
- Preferred: ₹50 Cr+

---

## Stage 1: Market Health — 10 pts

| Criterion | Points |
|---|---|
| Nifty above 20 EMA | 2 |
| Nifty above 50 EMA | 2 |
| Market structure = Higher Highs / Higher Lows | 3 |
| Market breadth positive (advances > declines) | 3 |

> If Nifty is below both EMAs and trending down, cap the day's max achievable score at 60–70 regardless of individual stock strength.

---

## Stage 2: Sector Rotation — 10 pts

| Criterion | Points |
|---|---|
| Sector in top 5 performers (1-month) | 3 |
| Sector in top 5 performers (3-month) | 3 |
| Sector outperforming Nifty | 4 |

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

> Recompute monthly/quarterly, cache the result. Zanger himself barely used fundamentals — this stage is your own addition layered on top of his price/volume method, not something to let override a hot Stage 5–8 setup.

---

## Stage 4: Earnings Quality — 10 pts (new)

*Not every earnings beat attracts institutions — they react to improving **expectations**, not just good historical numbers.*

| Criterion | Points |
|---|---|
| EPS surprise (beat vs. estimate) | 4 |
| Revenue surprise (beat vs. estimate) | 3 |
| Guidance upgrade (management raised forward guidance) | 3 |

---

## Stage 5: Institutional Activity — 15 pts (split from Relative Strength)

*Is money actually entering, regardless of whether price is responding yet?*

| Criterion | Points |
|---|---|
| RVOL percentile ranking — see below | up to 6 |
| Delivery % (vs. stock's own average) | 4 |
| Multi-day volume expansion trend (not just one spike) | 3 |
| Closing near day's high | 2 |

**RVOL ranking (percentile, not fixed threshold):**

| Rank among today's NSE universe | Points |
|---|---|
| Top 5% by RVOL | 6 |
| Top 10% | 4 |
| Top 20% | 2 |
| Below top 20% | 0 |

> Why percentile instead of "RVOL ≥ 2": on a high-volatility day, 600+ stocks might clear a fixed 2× threshold — a fixed cutoff stops discriminating. Ranking always tells you which names are exceptional *today*, market-wide.

---

## Stage 6: Relative Strength — 15 pts (new, split out)

*Is price actually outperforming — the check that filters out "high volume from bad news"?*

| Criterion | Points |
|---|---|
| Relative Strength vs Nifty (positive & rising) | 4 |
| Relative Strength vs own Sector | 4 |
| New 52-week high | 4 |
| Outperforming Nifty over the last 1 month | 3 |

> **Stage 5 without Stage 6 is a warning sign, not a buy signal.** Huge volume with flat-to-negative relative strength usually means distribution, a news dump, or panic selling into strength — not institutional accumulation.

---

## Stage 7: Accumulation Structure — 10 pts (split from Breakout)

*Early-entry evidence — before the breakout even happens.*

| Criterion | Points |
|---|---|
| Wyckoff accumulation characteristics present | 3 |
| Volume dry-up during the base | 3 |
| Tight range / volatility contraction | 2 |
| Delivery % increasing while price is flat/basing | 2 |

---

## Stage 8: Breakout / Entry Structure — 15 pts (incl. Zanger's Six Setups)

*Late-entry / momentum evidence — the breakout itself.*

| Criterion | Points |
|---|---|
| One of Zanger's Six Setups clearly formed (see table below) | 6 |
| Breakout volume confirmation (Zanger Rule #8) | 3 |
| Close above resistance | 2 |
| Follow-through (holds above breakout the next session) | 2 |
| No immediate overhead supply | 2 |

**Zanger's Six Setups — what confirms each one:**

| Setup | Confirming sequence |
|---|---|
| **Cup and Handle** | Pullback (left side) → rounded bottom on dry volume → advance without volume spikes (right side) → handle pullback on low volume → breakout with volume surge |
| **High Tight Flag** | Flagpole of 80–100%+ in weeks on strong volume → shallow 10–25% pullback → volume drying up in the flag → breakout with volume surge (rare — highest conviction if fully formed) |
| **Ascending Triangle** | Prior uptrend → horizontal resistance with rising lows → volume drying up on approach → breakout with volume surge |
| **Flat Base** | Prior uptrend → tight sideways range → volume contraction → breakout above the base top |
| **Double Bottom** | First bottom (not a buy point) → rebound to resistance → second bottom holding near/above the first → breakout above the middle peak with volume |
| **Trendline Breakout** | Descending trendline or horizontal resistance, repeatedly rejected → breakout with volume, stop just below the breakout area |

> Score whichever single setup is most clearly formed — don't average across multiple overlapping patterns on the same chart. No recognizable pattern = zero points here, no matter how good the other stages score (Zanger Rule #1).

---

## Institutional Lifecycle — Classification Layer (not scored, but shown alongside the score)

Institutions move through a lifecycle: **Accumulation → Markup → Distribution → Markdown.** This isn't a 9th scoring stage — it's a label derived from how Stages 5–8 relate to each other, so you know *what kind* of trade you're looking at.

| Stage | Signature | What it means for entry |
|---|---|---|
| **Accumulation** | Stage 7 (Accumulation) high, Stage 8 (Breakout) still low, RS flat-to-improving | Early entry, wider stop, smaller size — you're ahead of the breakout |
| **Early Markup** | Stage 8 high, Stage 5 (Institutional Activity) high, RS accelerating | Prime entry zone — the breakout stage's sweet spot |
| **Distribution** | Price near highs, RS weakening or flat, closes off the day's high despite volume | Avoid new entries; tighten stops on existing positions |
| **Markdown** | RS negative, breaking below support, high volume on down days | Avoid entirely; if held, this is where Rule #3 (cut losses fast) applies |

> Two stocks with the same total score can be in completely different lifecycle stages — one entering, one exiting. Always check this label before acting on the number alone.

---

## Risk Filter — Gate (Pass/Fail, not scored)

Runs after scoring, before capital commitment.

- [ ] Stop-loss level clearly defined
- [ ] Reward ≥ 3× risk
- [ ] No major resistance immediately overhead
- [ ] No earnings/major event within your holding window
- [ ] Liquidity sufficient for your position size (see Liquidity Filter above)

---

## Execution Discipline Gate — Zanger's Rules (Pass/Fail, per-trade)

- [ ] Entry within ~5% of breakout — not chasing an extended move (Rule #2)
- [ ] Waited for confirmation — didn't buy the instant the signal appeared (Rule #9)
- [ ] Stop placed just below the breakout area, exit automatic if price falls back into the base (Rule #3)
- [ ] Partial profit plan set: sell ~20–30% at +15–20% from breakout (Rule #4)
- [ ] Hold/cut discipline: strong trending positions held longer, weak/choppy ones cut (Rule #5)
- [ ] Watching for reversal signs as the move matures — steepening trendlines, head & shoulders, double tops, distribution (Rule #7)
- [ ] No margin used unless you have a proven, stable system and can stay disciplined under pressure (Rule #10)

---

## Grading Bands (out of 100)

| Score | Grade | Action |
|---|---|---|
| 85–100 | A+ | High-conviction candidate, prioritize |
| 70–84 | A | Strong candidate, standard sizing |
| 55–69 | B | Watchlist only, wait for improvement |
| Below 55 | C | Discard |

---

## Why this structure

- **Splitting Institutional Activity from Relative Strength** stops the model from rewarding high-volume names that are actually being sold into, not accumulated — activity confirms money is moving, RS confirms price is winning because of it.
- **Splitting Accumulation from Breakout** lets the same framework serve two different trading styles: early positioning before the move, or momentum entries after confirmation. You choose which stage to weight more once you know which style suits you.
- **Percentage weighting** means if backtesting shows Relative Strength predicts winners better than ROCE, you move points from Stage 3 to Stage 6 and the model still sums to 100 — no boundary recalculation needed.
- **Lifecycle classification stays unscored on purpose** — it's context for interpreting the number, not another number to add. A 90/100 in Distribution and a 90/100 in Early Markup should not be treated the same way.

---

## Next steps

1. Encode each stage's criteria as testable formulas for the scanner (e.g. RVOL percentile requires ranking *all* scanned stocks each evening before scoring any single one).
2. Have the scanner output the lifecycle label alongside the score, e.g. `ABC — 96 — Early Markup`.
3. Backtest weight sensitivity: run the same historical trades with Stage weights shifted (e.g. Relative Strength 15→20, Fundamentals 15→10) and see which weighting scheme actually correlates with your winners.
4. Long-term: this pipeline maps directly onto an evening batch job — NSE Data → Market Analyzer → Sector Rotation Engine → Fundamental/Earnings Screener → Institutional Activity + RS Engine → Pattern Recognition (Accumulation/Breakout) → Lifecycle Classifier → Risk Engine → Ranked output. That's the natural target for the Python scanner whenever you're ready to build it.
