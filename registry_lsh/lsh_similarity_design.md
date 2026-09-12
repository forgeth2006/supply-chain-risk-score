# MinHash+LSH Prototype: Design, Findings & Limitations

## Pipeline built
1. Filtered full registry names against basic validity rules (from the
   junk-data finding during data acquisition) — removed 34/884,813 PyPI,
   873/4,419,399 npm entries.
2. Converted names to 2-character shingle sets via character-split + NGram(n=2).
3. Vectorized via CountVectorizer(binary=True) — binary chosen since Jaccard
   similarity is presence-based, not frequency-based.
4. Applied Spark ML's MinHashLSH (numHashTables=5) for approximate similarity.

## Critical finding 1: vocabulary-fitting scope affects correctness
Initially fit CountVectorizer only on the 15,000-package popular list.
This silently drops any shingle not present in that vocabulary when
transforming candidate names — e.g. `1build` vs `build`: the "1b" shingle,
absent from the popular vocabulary, was invisibly dropped, producing a
false Jaccard distance of 0.0 (identical) instead of the correct 0.2
(hand-verified: intersection 4, union 5).

**Fix:** fit CountVectorizer on the FULL registry instead (popular packages
are a subset of it, so no vocabulary coverage is lost). Re-verified
build/1build correctly returns ~0.2 after the fix.

## Critical finding 2: calibration across three reference pairs
| Pair | Relationship | Jaccard distance |
|---|---|---|
| requests / kubernetes | Unrelated | 0.93 |
| requests / reqeusts | Real transposition-typo attack | 0.60 |
| flask-restful / flask-restplus | Legitimate coincidental similarity | 0.4375 |

**Key implication:** the legitimate coincidental pair scored MORE similar
than the real attack pair. No single threshold cleanly separates attacks
from coincidences using character-shingle Jaccard alone. This is direct,
first-hand evidence justifying the project's 3-signal design — Signal 1
cannot be the sole decision-maker and was never intended to be.

Threshold locked at distance <= 0.65 (similarity >= 0.35) — loose enough
to catch the real attack pattern, accepting it will also surface
coincidental legitimate pairs, by design, for Signals 2/3 to filter.

## Critical finding 3: degenerate/repetitive strings are indistinguishable
`aaaaaaaaa`, `aaaa`, `aa`, and `aaa` all register as IDENTICAL (distance 0.0)
under 2-character shingling, since a repeated single character only ever
produces one possible shingle regardless of string length. This is a
structural limitation of character-shingle Jaccard for degenerate strings,
not a bug — noted as a known blind spot, low real-world risk since these
aren't realistic package names to begin with.

## Prototype run (2,000-name slice, threshold 0.65)
- 6,785 raw candidate pairs generated; 6,764 after removing exact
  self-matches (a package matching itself in the registry).
- Manual review of the top 20 closest matches revealed a common pattern:
  a popular package name with a single leading digit prepended
  (e.g. `xai-sdk` -> `1xai-sdk`). Open question, not yet resolved: whether
  digit-prefix similarity represents a realistic typo pattern (low
  plausibility a user would accidentally add a leading digit) versus
  letter-transposition matches (e.g. `aa-memberaudit-dc` / `aa-memberaudit`),
  which look like more plausible typosquat shapes.
- This slice covered only the alphabetically-early portion of the registry
  (884,779 names) — not representative of the full dataset; a full run
  is needed before drawing conclusions about overall match volume.

## Environment note
`distCol` parameter in `approxSimilarityJoin` does not rename the output
column under Databricks Free Edition's Spark Connect client — the real
column remains named `distCol` regardless of the string passed. Workaround:
reference `distCol` directly and alias in `.select()`.

## npm full-registry run (with real-world scoping note)
The full npm registry join (4,421,253 names) could not complete in a reasonable
time on free-tier compute (Databricks Free Edition experienced an outage;
Google Colab's local-mode Spark exceeded 1 hour on the full join without
completing, and its default disk storage was found to be wiped on runtime
restart, requiring a switch to Google Drive for persistent storage).

**Decision:** used a 20,000-name representative sample of the full npm
registry instead of the complete set, at threshold 0.65, numHashTables=3
(reduced from 5 for speed given single-machine constraints — a stated
accuracy/speed tradeoff, not a hidden shortcut).

Result: 8,537 candidate pairs from the 20,000-name sample. The same
digit-prefix pattern found in PyPI's full run appeared here too
(e.g. `electron`/`4electron`, `router`/`7router`), reinforcing that this
is a systematic characteristic of the method rather than a PyPI-specific
artifact.

## Finding 6: zero-vector filtering must be applied to BOTH sides symmetrically
Initially only filtered the full registry for zero-vector rows (names with
no shingles in the fitted vocabulary), not the popular list. Since the
popular list is smaller, a rare edge case can slip through unnoticed until
MinHashLSH fails during the join itself. Fix: apply the same zero-vector
filter to both the popular list AND the full registry whenever fitting a
new vocabulary. Also discovered that Spark's lazy evaluation can silently
recompute a filter differently across separate operations on the same
lazy chain — resolved by writing filtered results to Parquet and reading
them back ("materializing") before using them in a new model fit, rather
than chaining transformations indefinitely.