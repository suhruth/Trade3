# Scheduler & .bat files — operator's manual

A plain-language reference for running the nightly archiver and its Windows
wrapper scripts without needing an AI session. Everything here is standard
Windows Task Scheduler (`schtasks`) and batch files — no special tools needed.

## The three `.bat` files, in one line each

| File | Run it... | What it does |
|---|---|---|
| `source/setup_scheduler.bat` | once per machine | Registers the nightly Task Scheduler job |
| `source/run_archiver.bat` | never by hand (Task Scheduler runs it) | The actual nightly job: `new_month.py` → `archive_bhavcopy.py` → `archive_indices.py`, logged to `logs\archiver.log` |
| `source/new_month.bat` | occasionally, by hand | Manually (re-)scaffold a journal month folder |

All three are **portable** — they find the repo relative to their own
location, so nothing needs editing after copying the `Trade3` folder to a
new machine or drive.

## First-time setup on a new machine

Do this once, any time the folder is copied to a machine that doesn't
already have the task registered.

1. **Install Python 3** from [python.org](https://www.python.org/downloads/)
   if it isn't already there. During install, check "Add python.exe to
   PATH". This repo is stdlib-only — nothing else to install.
2. Open a terminal in the `Trade3` folder (or just double-click the file)
   and run:
   ```
   source\setup_scheduler.bat
   ```
   This registers a daily Task Scheduler job named **"NSE Bhavcopy
   Archiver"** at 19:30 IST (after NSE publishes the post-close bhavcopy).
3. To use a different time instead of 19:30, pass it as an argument:
   ```
   source\setup_scheduler.bat 20:00
   ```
4. Confirm it registered:
   ```
   schtasks /Query /TN "NSE Bhavcopy Archiver"
   ```
   You should see `Next Run Time` and `Status: Ready`.

Re-running `setup_scheduler.bat` is always safe — it overwrites the
existing task (`/F`) rather than erroring on a duplicate.

> **Note on the task itself:** it's created as "run only while logged
> on" (the default for a plain `schtasks /Create /SC DAILY`), not as a
> background/service task. If the machine is locked out, sleeping, or
> shut down at 19:30, that night's run is skipped — there's no catch-up
> run built in. `archive_indices.py` is backfillable later
> (`--from <date>`); the security bhavcopy is not, so a missed day's
> delivery/breadth data is gone for good.

## What happens automatically every night

At the scheduled time, Task Scheduler launches `run_archiver.bat`, which:

1. `cd`s to the repo root (via its own location, so this works from any
   drive/path).
2. Creates `logs\` if it doesn't exist.
3. Picks a Python: prefers the `py` launcher (`py -3`) if present,
   otherwise falls back to `python` on PATH.
4. Runs, in order, appending everything to `logs\archiver.log`:
   - `new_month.py` — makes sure this month's (and, near month-end, next
     month's) journal folder exists.
   - `archive_bhavcopy.py` — downloads today's NSE security bhavcopy.
   - `archive_indices.py` — downloads today's NSE all-indices close
     (the sector-ranking data).

## Checking on it

**Is the task registered and healthy?**
```
schtasks /Query /TN "NSE Bhavcopy Archiver"
```
Add `/V /FO LIST` for full detail (last run time, last result code, etc.):
```
schtasks /Query /TN "NSE Bhavcopy Archiver" /V /FO LIST
```
`Last Result: 0` means the last run's `run_archiver.bat` process exited
cleanly. A non-zero code means something in the chain failed — check the
log next.

**What actually happened last night?**
Open `logs\archiver.log` — it's plain text, appended forever, newest
entries at the bottom. Each run is stamped and sectioned, e.g.:
```
===== 23-07-2026 17:03:21.36 =====
[new_month]
  [exists] journal\2026\07-July
         monthly.md:kept, sectors.csv:kept, universe.csv:kept, earnings.csv:kept
[archive_bhavcopy]
  + 2026-07-23  saved

Done: 1 saved, 0 already present, 0 holiday/weekend, 0 failed  ->  ...\data\bhavcopy
```
Look for `holiday` (expected — NSE was closed, not a failure) vs `failed`
(a real problem — network issue, or NSE changed something).

## Running things manually

**Run tonight's job right now** (doesn't wait for 19:30):
```
schtasks /Run /TN "NSE Bhavcopy Archiver"
```
Then check `logs\archiver.log` for the new entry a few seconds later.

**Scaffold a journal month by hand** (rarely needed — the nightly job
already does this):
```
source\new_month.bat
```

**Change the scheduled time** — re-run setup with a new time (it
overwrites the old registration):
```
source\setup_scheduler.bat 20:00
```

**Pause it temporarily** (keeps the task, stops it firing):
```
schtasks /Change /TN "NSE Bhavcopy Archiver" /DISABLE
```
Re-enable with:
```
schtasks /Change /TN "NSE Bhavcopy Archiver" /ENABLE
```

**Remove it entirely:**
```
schtasks /Delete /TN "NSE Bhavcopy Archiver" /F
```

## Moving to yet another machine later

The Task Scheduler job lives in *that machine's* scheduler, not in the
`Trade3` folder — copying the folder does **not** bring the schedule
with it. Repeat "First-time setup" above on the new machine.

## Troubleshooting

**`schtasks` says the task doesn't exist.**
It was never registered on this machine, or was deleted. Run
`setup_scheduler.bat` (see First-time setup).

**Nothing appears in `logs\archiver.log` after the scheduled time.**
The task probably didn't fire because the machine wasn't logged in at
19:30 (see the "run only while logged on" note above), or the task is
disabled — check with `schtasks /Query /TN "NSE Bhavcopy Archiver" /V /FO LIST`
and look at `Scheduled Task State`.

**The log shows `python`/`py` errors, or nothing after `[new_month]`.**
Python isn't installed or isn't on PATH for the account Task Scheduler
runs as. Open a terminal and check:
```
python --version
py -3 --version
```
If either opens a Microsoft Store prompt instead of printing a version,
that's the Windows "app execution alias" stub, not a real Python —
install Python from python.org and, if the stub still intercepts,
disable it under **Settings → Apps → Advanced app settings → App
execution aliases**.

**A run failed (`failed` in the log, or non-zero `Last Result`).**
Re-run it by hand to see the live error:
```
python source\archive_bhavcopy.py
python source\archive_indices.py
```
A `404`/skip for *today's* date usually just means NSE hasn't published
yet or it's a holiday — that's not a failure. A real failure is a
network error or NSE serving an HTML error page instead of a CSV.

**Data is missing for a gap of days** (e.g. after the machine was off,
or the folder just moved here).
- `archive_indices.py --from YYYY-MM-DD` backfills the index archive for
  any past range — safe to run any time.
- `archive_bhavcopy.py` also accepts `--from`/`--to`, but treat gaps here
  as best-effort: this is the file the project treats as a forward-only
  archive, so don't rely on being able to recover an arbitrarily old day.

**The `.bat` files themselves seem to run garbled commands / `schtasks`
errors on stray characters.**
This happened once from Unix (LF-only) line endings sneaking into the
`.bat` files, which `cmd.exe` parses incorrectly. All three were fixed to
CRLF in August 2026. If it recurs (e.g. after editing one in a
non-Windows-aware editor), re-save with CRLF line endings.
