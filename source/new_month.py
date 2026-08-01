#!/usr/bin/env python3
"""
new_month.py — scaffold the journal folder for the current month (and, when
month-end is near, next month too), pre-filled from the monthly templates.

For each month it ensures `journal/<YYYY>/<MM-Month>/` exists and contains:
    monthly.md   sectors.csv   universe.csv   earnings.csv

Safety: it NEVER overwrites a file that already exists — a partly-filled sheet
is left untouched. Re-running is always safe (idempotent).

Carry-forward: the watchlist persists month to month, so when a new month's
universe.csv / sectors.csv is created and the *previous* month has one, the
symbol/sector names are carried over and the data columns are blanked (you
refresh the numbers, you don't re-type the list). Earnings start fresh.

Usage:
    python new_month.py                 # ensure this month; near month-end also next month
    python new_month.py --date 2026-07-29   # pretend it's that day (testing)
    python new_month.py --lookahead 7   # widen the "near month-end" window (default 5 days)
"""

import argparse
import calendar
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL = REPO_ROOT / "journal"
TEMPLATES = REPO_ROOT / "templates"

# template filename -> output filename inside the month folder
TEMPLATE_MAP = {
    "monthly-scan-template.md": "monthly.md",
    "monthly-sectors-template.csv": "sectors.csv",
    "monthly-universe-template.csv": "universe.csv",
    "monthly-earnings-template.csv": "earnings.csv",
}

# output filename -> column indices to carry forward from the prior month (rest blanked)
CARRY_KEEP = {
    "universe.csv": [0, 1],  # symbol, sector
    "sectors.csv": [0],      # sector name
}

# CSVs whose template rows are kept when stamping a fresh copy (a canonical list,
# not a throwaway example). Everything else is stamped header-only.
KEEP_TEMPLATE_ROWS = {"sectors.csv"}


def month_dirname(m: int) -> str:
    return f"{m:02d}-{calendar.month_name[m]}"  # e.g. 07-July (sortable)


def prev_month(y: int, m: int):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def next_month(y: int, m: int):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def carry_skeleton(prev_path: Path, keep_idx) -> str | None:
    """Keep header + each row's `keep_idx` cells, blank the rest (refresh monthly)."""
    lines = prev_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return None
    header = lines[0]
    ncol = len(header.split(","))
    out = [header]
    for row in lines[1:]:
        if not row.strip():
            continue
        cells = row.split(",")
        out.append(",".join(cells[i] if (i in keep_idx and i < len(cells)) else "" for i in range(ncol)))
    return "\n".join(out) + "\n"


def stamp_file(template_name: str, out_name: str, dest_dir: Path, y: int, m: int) -> str:
    dest = dest_dir / out_name
    if dest.exists():
        return "kept"  # never clobber a filled sheet

    # Carry the watchlist forward from last month if we can.
    if out_name in CARRY_KEEP:
        py, pm = prev_month(y, m)
        prev_file = JOURNAL / str(py) / month_dirname(pm) / out_name
        if prev_file.exists():
            content = carry_skeleton(prev_file, CARRY_KEEP[out_name])
            if content:
                dest.write_text(content, encoding="utf-8")
                return "carried"

    src_text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    if out_name.endswith(".csv"):
        if out_name in KEEP_TEMPLATE_ROWS:
            dest.write_text(src_text, encoding="utf-8")  # keep canonical rows (e.g. sector list)
        else:
            # Fresh CSV: header only — drop the template's example row.
            dest.write_text(src_text.splitlines()[0] + "\n", encoding="utf-8")
    else:
        # Markdown: keep full text, fill the month placeholders.
        text = (
            src_text.replace("{MONTH}", calendar.month_name[m])
            .replace("{YYYY}", str(y))
            .replace("{MM-MONTH}", month_dirname(m))
        )
        dest.write_text(text, encoding="utf-8")
    return "created"


def ensure_month(y: int, m: int):
    dest_dir = JOURNAL / str(y) / month_dirname(m)
    existed = dest_dir.exists()
    dest_dir.mkdir(parents=True, exist_ok=True)
    results = {out: stamp_file(tmpl, out, dest_dir, y, m) for tmpl, out in TEMPLATE_MAP.items()}
    return dest_dir, existed, results


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold journal month folder(s) from templates.")
    ap.add_argument("--date", help="override today as YYYY-MM-DD (testing)")
    ap.add_argument("--lookahead", type=int, default=5,
                    help="within this many days of month-end, also create next month (default 5)")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    y, m = today.year, today.month

    targets = [(y, m)]
    days_left = calendar.monthrange(y, m)[1] - today.day
    if days_left <= args.lookahead:
        targets.append(next_month(y, m))

    for ty, tm in targets:
        dest_dir, existed, results = ensure_month(ty, tm)
        rel = dest_dir.relative_to(REPO_ROOT)
        print(f"  [{'exists' if existed else 'NEW'}] {rel}")
        print("         " + ", ".join(f"{k}:{v}" for k, v in results.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
