# Signal 3: Real Adoption Evidence — Design & Findings

## Design change from original plan
Originally planned as a GH Archive Spark scan + GitHub compare-endpoint
pipeline. Simplified to direct GitHub Code Search API queries against
Signal 1's shortlist, to avoid repeating the heavy infrastructure risk
encountered during Signal 1's full-scale run (see lsh_similarity_design.md).

## Method
- Took the 75 closest matches (by Jaccard distance) from each registry's
  Signal 1 output, 150 candidates total.
- Queried GitHub Code Search for each: does any public `requirements.txt`
  (PyPI) or `package.json` (npm) file contain this exact candidate name?
- Rate limit: 30 searches/minute (authenticated). Used 4-second pacing
  with automatic retry-on-403 backoff.

## Results
- 150/150 candidates checked successfully (after resolving a rate-limit
  retry round).
- ~53+ candidates showed at least one real GitHub hit.
- Applied a skepticism filter: excluded hits with count > 5000, since
  extremely high hit counts indicate the candidate is a common English
  word/substring producing coincidental matches (e.g. "expect" returned
  279,552 hits — clearly not meaningful evidence), not genuine typosquat
  adoption.
- After filtering, strongest evidence-backed candidates include repeated
  attack patterns against the same popular package (e.g. `router` targeted
  by `0router`/`1router`/`3router`/`8router`, all with real hits) and
  known limitation cases from Week 4 (`wheel`/`wheeel`) now confirmed to
  have real-world presence.

## Caveat
A real GitHub hit confirms EXISTENCE in a dependency file, not malicious
INTENT — a low hit count could be an innocent coincidentally-named
project. This is why Signal 3 alone isn't sufficient; the final risk
score still requires Signal 2 (blast radius) to assess actual potential
damage before a candidate is treated as high-risk.