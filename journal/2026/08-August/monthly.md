# Monthly Scan — August 2026

> **Cadence:** run on the last trading day of the month (or the first of the new one).
> **Feeds:** Stage 1 (regime + score cap), Stage 2 (sector rotation), Stage 3 (universe tiering), Stage 4 (earnings). The daily scan **reuses** the sector ranking and the universe tiers all month — don't recompute them daily.
> **Filled copy goes to:** `journal/2026/08-August/` as this file (`monthly.md`) plus the three CSVs below.
> Model reference: `docs/institutional-swing-scoring-model-v4.md`.

This Markdown file holds the **narrative** sections. The big tables live in companion **CSVs** (sortable, and the scanner can auto-populate them later):

| Companion CSV | Section | Template |
|---|---|---|
| `sectors.csv` | Sector Rotation (§2) | `templates/monthly-sectors-template.csv` |
| `universe.csv` | Watchlist tiering (§3) | `templates/monthly-universe-template.csv` |
| `earnings.csv` | Earnings digest (§4) | `templates/monthly-earnings-template.csv` |

---

## 0. Data-collection checklist (pull before filling)

- [ ] Nifty 50 month-end OHLC + 20/50 EMA — Zerodha
- [ ] Breadth: % of universe above its 50-DMA — your bhavcopy/OHLC store
- [ ] The 17 NSE sectoral indexes: 1M & 3M returns, RS-vs-Nifty acceleration — **auto: `python source/rank_sectors.py`** → `sectors.csv`
- [ ] Fundamentals for your watchlist (ROCE/ROE/growth/D-E/mktcap/pledge/OCF) — Screener → `universe.csv`
- [ ] Median 20-day traded value per name — bhavcopy (TURNOVER) → `universe.csv`
- [ ] Quarterly results declared this month → EPS SUE, Rev SUE, growth accel — Screener (Appendix B) → `earnings.csv`
- [ ] Upcoming result dates for next month — reporting-lag heuristic + NSE announcements → `earnings.csv`

---

## 1. Market Regime — as of {month-end date}

| Item | Value | Pass? |
|---|---|---|
| Nifty close | ⟨ ⟩ | — |
| Above 20 EMA | ⟨Y/N⟩ | ⟨✓/✗⟩ |
| Above 50 EMA | ⟨Y/N⟩ | ⟨✓/✗⟩ |
| Structure = Higher-Highs / Higher-Lows | ⟨Y/N⟩ | ⟨✓/✗⟩ |
| Breadth: % of universe above 50-DMA | ⟨ %⟩ | ⟨>50 = ✓⟩ |

**Regime verdict:** ⟨ Risk-On / Neutral / Risk-Off ⟩
**Score cap this month:** ⟨ none, or 65 if Nifty below both EMAs *and* structure is LH/LL ⟩

---

## 2. Sector Rotation → `sectors.csv`  *(do this FIRST — it drives stock selection)*

Run `python source/rank_sectors.py` — it ranks all 17 NSE sectoral indexes from
official index data and writes `sectors.csv`: 1M/3M/6M returns, Relative
Performance vs Nifty (`rp_*`), a 1–5 `rp_score`, and an RRG `quadrant`. Then
summarise here (quadrants: **Leading** = ahead + rising, **Improving** = behind
but turning up = next to lead, **Weakening** = ahead but fading, **Lagging** = avoid):

- **Leading (buy first):** ⟨ … ⟩
- **Improving (watch — next to become strong):** ⟨ … ⟩
- **Avoid (lagging):** ⟨ … ⟩

> Stock hunting happens **inside the Leading + Improving sectors** — that's the top-down flow.

---

## 3. Watchlist tiering → `universe.csv`

Fill `universe.csv` for your ~50–150 names. Eligibility is a **soft priority tier, not a hard gate** — the daily scan ranks by tier but can still surface a strong technical setup in a lower tier.

| Tier | Meaning |
|---|---|
| **Priority** | Passes fundamentals (strong Stage-3) **and** liquidity gate → scanned first, full size |
| **Watch** | Weaker fundamentals, but keep it live — a breakout/RS surge can still promote it in the daily scan |
| **Size-limited** | Fails the ₹20 Cr median-liquidity gate → tradeable only in small size regardless of score |

- **Priority count:** ⟨ N ⟩  · **Watch:** ⟨ N ⟩  · **Size-limited:** ⟨ N ⟩

---

## 4. Earnings Digest → `earnings.csv`

Fill `earnings.csv` (results declared this month + next expected dates). Flag any name with an upcoming result **inside an open holding window** — that's a Stage-9 risk-gate blocker.

- **Notable positive surprises (high SUE):** ⟨ … ⟩
- **Upcoming-earnings watch (avoid new entries near these):** ⟨ … ⟩

---

## 5. Monthly Retrospective & weight notes

**Last month's A/A+ picks:**

| Symbol | Score | Lifecycle | Outcome | R multiple | Note |
|---|---|---|---|---|---|
| ⟨ABC⟩ | ⟨ ⟩ | ⟨ ⟩ | ⟨win/loss/open⟩ | ⟨+2.1R⟩ | ⟨ ⟩ |

- **What worked:** ⟨ … ⟩
- **What didn't:** ⟨ … ⟩
- **Weight-tuning idea for next month:** ⟨ e.g. RS predicted winners better than fundamentals → shift Stage 3 15→12, Stage 6 15→18 ⟩

---

### Carry-forward to the weekly/daily sheets
- Focus sectors: ⟨ from §2 ⟩
- Priority + Watch names: ⟨ from §3 ⟩
- Active score cap: ⟨ from §1 ⟩
