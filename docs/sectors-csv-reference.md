# `sectors.csv` — column reference

Quick reference for the sector-ranking output produced by `source/rank_sectors.py`
(ranks the 41 tracked NSE sectoral/thematic indexes — `rank_sectors.py`'s `SECTORS` map — from official `ind_close_all` index data).
One row per sector; rows ordered by `rank` (strongest first).

**Header:**
`sector,rank,ret_1m_pct,ret_3m_pct,ret_6m_pct,rp_1m,rp_3m,rp_6m,rp_score,rs_mom_20d,pct_off_6m_high,accel,quadrant,stage2_pts`

**Worked example (Nifty Pharma):**
`Nifty Pharma,1,2.66,14.24,13.99,2.47,16.33,20.99,5,3.19,1.7,N,Leading,10`

| # | Column | What it is | How it's computed | Pharma |
|---|---|---|---|---|
| 1 | **sector** | Which of the 41 tracked NSE sectoral/thematic indexes | friendly label (maps to the exact NSE index name internally) | Nifty Pharma |
| 2 | **rank** | Overall strength rank, 1 = strongest | ordered by `rp_3m` (relative strength vs Nifty, 3-month) | 1 |
| 3 | **ret_1m_pct** | **Absolute** price return, 1 month | index change over ~21 sessions | +2.66% |
| 4 | **ret_3m_pct** | Absolute return, 3 months | over ~63 sessions | +14.24% |
| 5 | **ret_6m_pct** | Absolute return, 6 months | over ~126 sessions (context only) | +13.99% |
| 6 | **rp_1m** | **Relative** Performance, 1M | `ret_1m − Nifty50 ret_1m` | +2.47 |
| 7 | **rp_3m** | Relative Performance, 3M — **the core metric** | `ret_3m − Nifty50 ret_3m` | +16.33 |
| 8 | **rp_6m** | Relative Performance, 6M | `ret_6m − Nifty50 ret_6m` (context) | +20.99 |
| 9 | **rp_score** | 1–5 star strength rating | bands on `rp_3m`: >15→5, 10–15→4, 5–10→3, 0–5→2, <0→1 | 5 |
| 10 | **rs_mom_20d** | RS **momentum** — is relative strength rising *now* | % change of the (sector ÷ Nifty) line over 20 sessions | +3.19 |
| 11 | **pct_off_6m_high** | Distance below the 6-month closing high | `(6M-high − current) / 6M-high` (0 = at a new high) | 1.7% |
| 12 | **accel** | Is the sector speeding up | `Y` if `ret_1m > ret_3m/3` (last month beats the quarter's avg pace) | N |
| 13 | **quadrant** | RRG classification (the verdict) | `rp_3m` level × `rs_mom_20d` direction — see below | Leading |
| 14 | **stage2_pts** | 0–10 score for the v4 scoring pipeline | +4 top-5 by 1M return, +3 top-5 by 3M return, +3 RS acceleration | 10 |

## How to read the quadrant (col 13)

Two axes — **ahead of Nifty?** (`rp_3m ≥ 0`) × **momentum rising?** (`rs_mom_20d > 0`):

| | momentum rising | momentum falling |
|---|---|---|
| **ahead of Nifty** | 🟢 **Leading** — buy first | 🟡 **Weakening** — trim/tighten |
| **behind Nifty** | 🔵 **Improving** — next to become strong | 🔴 **Lagging** — avoid |

Hunt for stocks inside the **Leading + Improving** sectors.

## Two things that trip people up

1. **Returns (cols 3–5) are absolute; RP (cols 6–8) are relative to Nifty.** In a falling
   market a sector can post a *negative* return but *positive* RP — it just fell less than
   the index. RP is what matters for rotation; the raw return is context.
2. **`rp_score` and `stage2_pts` measure different things**, so they don't always agree.
   `rp_score` is the star model (purely `rp_3m`). `stage2_pts` is the v4-spec scheme
   (raw-return ranks + RS acceleration). Pharma maxes both (5 and 10); Nifty Consumption
   is `Leading` with `stage2_pts` 10 but only `rp_score` 2 — strong on the spec's
   rank/acceleration test, milder on pure relative performance. Keep both; they cross-check.

Blank cells appear only for a sector with too little history (e.g. a newly launched index) —
that column simply couldn't be computed.

## Session-length constants (in `rank_sectors.py`)

| Window | Sessions | Used for |
|---|---|---|
| 1 month | 21 | `ret_1m`, `rp_1m` |
| 3 months | 63 | `ret_3m`, `rp_3m` (core), `rp_score`, `rank` |
| 6 months | 126 | `ret_6m`, `rp_6m`, `pct_off_6m_high` |
| RS momentum | 20 | `rs_mom_20d`, RS-acceleration test |
| RS average | 50 | RS-acceleration test (`stage2_pts`) |

> Needs ≥ ~63 archived index days to be fully functional; ≥ 126 for the 6-month columns.
> Backfill with `python source/archive_indices.py --from <YYYY-MM-DD>`.
