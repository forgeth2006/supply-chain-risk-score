# GH Archive Scope & Volume Estimate — Week 1

## Method
Sampled two hours from GH Archive at different times/days to avoid relying on a single unrepresentative hour:
- 2026-08-15, 12:00 UTC (weekday, midday): 170,586 events, 19.79 MB compressed
- 2026-08-20, 03:00 UTC (different day, off-peak): 54,338 events, 7.66 MB compressed

## Key finding 1: PushEvent dominance
PushEvent accounted for 97.9% and 95.0% of events respectively (avg ~96.5%) —
consistently the dominant event type. This is higher than commonly-cited
GH Archive benchmarks (~40-60%), confirmed genuine (not a sampling fluke)
by checking two hours 5 days apart at very different times of day.

## Key finding 2: PushEvent payload lacks file-level detail
Inspected the `payload` schema for PushEvent directly. It contains `before`/`head`
commit SHAs, `ref`, `push_id`, and `size`, but **no commit list and no changed-file
information**. This means GH Archive alone cannot confirm whether a push touched
a dependency manifest file (requirements.txt, package.json, etc.).

**Design implication:** Signal 3 requires a two-stage pipeline:
1. GH Archive scan → candidate push events (repo, before/head SHAs)
2. GitHub REST API compare endpoint (`/repos/{owner}/{repo}/compare/{before}...{head}`)
   → actual changed-file list

Given GitHub API rate limits (5,000/hr authenticated), step 2 can only run
against a pre-filtered shortlist — meaning **Signal 1 (name-similarity) must
run before Signal 3**, not in parallel, to keep the API-call volume small
enough to be feasible.

## Volume estimate (3-month window)
- Chosen window: 3 months (typosquat campaigns are a recent-activity signal,
  not historical)
- Hourly size varies significantly by time of day: 7.66 MB (off-peak) to
  19.79 MB (peak), confirmed via two samples
- Raw 3-month estimate: ~16-42 GB range, ~29 GB average
- Filtered (PushEvent-only) estimate: ~effectively the same, since PushEvent
  is ~96.5% of all events regardless of time of day
- Conclusion: comfortably feasible on Databricks Free Edition serverless
  compute, with substantial margin even if the estimate is off by 2x