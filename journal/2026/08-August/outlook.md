# August 2026 — Sector Outlook

> **Basis:** as-of index data **2026-07-23** (end of July). Companion data: `sectors.csv`.
> **Nature:** this is a *rotation-persistence* read, **not a forecast.** Sectors leading (or turning up) at month-end tend to carry that 1–2 months; the edge breaks on sharp regime flips. Grade it against actuals at month-end (§ Retrospective).
> **Signals used:** `rp_3m` (Relative Performance vs Nifty), `rs_mom_20d` (RS-line momentum), `pct_off_6m_high` (near-highs = money committed), `accel` (last month's pace > 3-month pace), `quadrant` (RRG).

## Market backdrop
- **Breadth WEAK (~49% of stocks above 50-DMA).** In a thin tape leadership narrows — favour Tier 1, treat rotation bets (IT) with extra caution.

## Tier 1 — Ride the leaders (highest conviction)
Outperforming, near highs, mostly accelerating. Base August longs here.

| Sector | RP 3M | 1M | RS mom | % off 6M high | accel | Note |
|---|---|---|---|---|---|---|
| **Nifty Pharma** | +16.3 | +2.7 | +3.2 | 1.7% | N | #1 strength, at highs. Lowest risk. Pace cooling slightly. |
| **Nifty Realty** | +12.5 | +10.0 | +8.4 | 5.5% | Y | Strongest momentum, but hot 1M + off highs → more volatile/extended. |
| **Nifty Auto** | +6.1 | +3.9 | +5.0 | 4.1% | Y | Clean, broad, accelerating. Solid. |
| **Nifty Consumption** | +4.1 | +2.4 | +3.1 | 1.9% | Y | Quietly near highs + accelerating. Underrated. |

## Tier 2 — Rotation watch (speculative, needs confirmation)
- **Nifty IT** — 2nd-best 1M (+5.6), positive RS momentum, accelerating; **but** RP 3M −4.4 and **27% below its 6-month high** — a bounce off a deep downtrend, not a base breakout. Real early-turn signal, but counter-trend: **wait for follow-through** before committing.
- **Nifty FMCG / Serv Sector** — "Improving" but marginal (RS momentum barely positive, still below highs). Low conviction; watch, don't commit.

## Tier 3 — Fading, don't initiate
**Media, Bank, Infra** — were ahead on 3M but momentum has rolled over (negative RS momentum). Manage existing, don't add.

## Tier 4 — Avoid
**PSU Bank** (worst: RP −5.9, 16% off high, mom −3.2), **CPSE, PSE, Fin Service, Energy, Metal, Commodities.**
> Note: CPSE/PSE show `accel = Y` but their RS momentum is still *negative* — noise off a low base, not a real turn. Combine signals; never trust acceleration alone.

## Net call
Lead with **Pharma, Consumption, Auto** (near highs, accelerating, lower risk); give **Realty** room for volatility; keep **IT** on a confirmation leash. Avoid PSU Bank / PSE / financials.

## What this can't see (build backlog)
1. **Earnings season (Jul–Aug)** — not modelled yet (Stage 4). A big beat/miss can override rotation.
2. **Sector-level delivery %/volume** — the "is institutional money actually flowing in" confirmation isn't aggregated to sector yet.

---

## Retrospective — fill at end of August (grade the call)
Compare each tier's actual August index return to grade rotation persistence.

| Sector | Tier called | Aug return % | Verdict held? | Note |
|---|---|---|---|---|
| Nifty Pharma | 1 (lead) | ⟨ ⟩ | ⟨Y/N⟩ | |
| Nifty Realty | 1 (lead) | ⟨ ⟩ | ⟨Y/N⟩ | |
| Nifty Auto | 1 (lead) | ⟨ ⟩ | ⟨Y/N⟩ | |
| Nifty Consumption | 1 (lead) | ⟨ ⟩ | ⟨Y/N⟩ | |
| Nifty IT | 2 (rotation) | ⟨ ⟩ | ⟨Y/N⟩ | did the turn confirm? |
| Nifty PSU Bank | 4 (avoid) | ⟨ ⟩ | ⟨Y/N⟩ | |

- **Did leaders persist?** ⟨ … ⟩
- **Did any Improving sector actually break out?** ⟨ … ⟩
- **Signal-tuning idea:** ⟨ e.g. weight `pct_off_6m_high` more in weak-breadth months ⟩
