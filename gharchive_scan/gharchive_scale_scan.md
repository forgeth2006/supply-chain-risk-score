# GH Archive Scale Scan (Spark)

## Purpose
Supplementary Signal 3 evidence at archive scale: are repos named after Signal 1's
shortlist candidates being pushed to? Complements the Code Search evidence
(signal3_evidence_design.md). This is NOT proof of installation; PushEvents carry no
file lists (see gharchive_scope.md).

## Method
- Window: 2026-08-24 to 2026-08-30, 168 hourly files, ~1.6 GB compressed.
- Spark local mode (4 cores, 8 GB heap set at notebook start), reading only 4 fields
  (type, created_at, actor.login, repo.name).
- Kept PushEvents, matched the lowercase repo short name against the 142 distinct
  candidate short names, aggregated pushes, active days and distinct pushers per repo.
- Scanned 12,061,354 events, 11,555,061 pushes (95.8%), in ~135 s.

## Results
71 matching repos, but only 5 of the 142 candidate names matched any repo at all.
The full list is in `data/gharchive_matches.csv` (columns: short, repo, pushes,
days_active, pushers).

| Candidate name | Repos | Notes |
|---|---|---|
| elasticsearch | 43 | `elastic/elasticsearch` has 20 pushes by 13 pushers over 6 days; the other 42 have 1-3 pushes and a single pusher each, which fits forks of the real project (not verified, the fields we extracted do not say whether a repo is a fork) |
| 9router | 17 | 1-3 pushes each, one pusher per repo |
| telemetry | 7 | includes organisation-owned repos (`golang/telemetry`, `nuxt/telemetry`, `cap-js/telemetry`) |
| anima | 3 | 1-3 pushes |
| webdavclient | 1 | 1 push |

No match could be classified as malicious from this data. `elasticsearch` and
`telemetry` are common, legitimate names, so those matches are Signal 1 false
positives. `9router` is the one cluster not obviously explained: many accounts each
hold a repo with that name, which looks like one project being forked or cloned.
Open question: `zcuss/9router` was also the example repo for the `0router` Code
Search hits in signal3_evidence_design.md, so the evidence for that candidate may
come from the same project.

## Limitations
- Matches by repo name only, so recall is low by design.
- Activity is not installation; forks and clones inflate name matches.
- One week, not a quarter.
- Sep 1-4 files contained almost no PushEvents (cause not investigated), so the
  choice of window matters. Aug 24-30 was verified at 94-97% pushes.

## Correction to Week 1 volume estimate
Measured Aug 24-30: ~232 MB/day average (160-344 MB), roughly 20-30 GB per 90 days.
This is the same order of magnitude as the original ~29 GB estimate, but it rests
on one week, so treat it as a range.