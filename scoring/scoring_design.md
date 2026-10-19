# Combined Scoring: Design, Weight Justification and Validation

## What the score is meant to say
Each shortlisted candidate (a registry name that looks like a popular package) gets a number from 0 to 1
that combines three pieces of evidence. It is an **evidence summary for ranking**, not a probability that a
package is malicious. See "What the validation showed" below for why that distinction matters.

## The three inputs, each turned into 0 to 1

| Signal | Raw input | Conversion | Reasoning |
|---|---|---|---|
| s1 name similarity | Jaccard distance on 2-character shingles | `1 - distance` | Closer name, higher value. |
| s2 blast radius | number of packages that depend on the imitated popular package (`data/blast_radius.csv`) | `log(1+n) / log(1+largest n)` | Dependent counts span orders of magnitude, so a log scale stops one giant package from flattening everything else. |
| s3 real-world evidence | GitHub Code Search hit count for the candidate name in `requirements.txt` / `package.json` | `log(1+hits) / log(1+5000)`; 0 hits gives 0; **more than 5,000 hits is ignored** | Above 5,000 the name is a common word (for example `expect` returned 279,552 hits), which is noise, not evidence. The cap value 5,000 is a judgment. |

## The formula
`score = (w1*s1 + w2*s2 + w3*s3) / (sum of the weights of the signals that are usable for that row)`

- **Missing means left out, never zero.** If a row has no blast-radius figure, or its hit count was noise, that
  signal is dropped and the remaining weights are rescaled. A row with fewer than two usable signals is marked
  UNSCORED and sorted to the bottom, because one signal alone is not a combined score.
- Tiers are presentation only: HIGH at 0.60 and above, MEDIUM at 0.40 and above, otherwise LOW. These cut-offs are
  **not calibrated** against anything.

## Weights and why
`w1 = 0.25, w2 = 0.30, w3 = 0.45`

- **s3 highest (0.45).** It is the only signal that observes the candidate in the real world instead of inferring
  from its spelling. It is also noisy (existence in a file is not intent), which is why it does not exceed half.
- **s2 middle (0.30).** It measures the consequence of the imitated package, not anything about the candidate. It
  decides how bad a real attack would be, so it matters, but it says nothing about whether an attack exists.
- **s1 lowest (0.25).** Name similarity already did its main job when it built the shortlist: all 150 candidates have
  s1 of 0.71 or higher, so little spread is left. Our own calibration (`registry_lsh/lsh_similarity_design.md`) also
  showed that the legitimate pair flask-restful / flask-restplus (distance 0.4375) is closer than the real attack
  reqeusts / requests (0.60), so name alone cannot separate attacks from coincidences.

These weights are **reasoned, not fitted**. There is no labelled training set, and with so few known-malicious
examples (see below) fitting weights would be overfitting.

## Sensitivity check (`scoring/score.py` writes `data/score_sensitivity.csv`)
The script re-scores under 15 different weight settings (no weight below 0.10) and compares each ranking with the
chosen one. With all three signals (reverse-dependency counts collected for all 131 popular packages):
Spearman rank correlation was between 0.59 and 0.99 (median 0.90), and the top 10 shared between 3 and 9 names
(median 6). **So the ranking is only moderately stable.** It moves most when the blast-radius weight is large,
because dependent counts differ enormously between ecosystems (median 3,609 for the npm popular packages versus 13
for the PyPI ones), so a heavy s2 weight mostly sorts npm above PyPI. The top of the list should be read as
"a group of high-exposure candidates", not as an exact order.

## Validation against the OpenSSF malicious-packages dataset
`scoring/validate_openssf.py` clones the dataset (names only) and checks our shortlist against it.

**What the validation showed (numbers are in `data/validation_summary.md` and `data/score_validation.csv`):**
1. **The shortlist does contain known-malicious names: 6 of 70 distinct npm candidates** (`3lectron`, `3electron`,
   `4electron`, `4lectron`, `4meme-readable-stream`, `9args`) are listed as malicious. **0 of 74 PyPI candidates** are.
2. **The combined score does not separate them from the rest.** Treating the listing as the label, the AUC (0.5 means
   chance) was **0.47 over all 150 rows** (a bootstrap 95% interval of roughly 0.31 to 0.63, i.e. consistent with
   chance) and **0.35 when compared only among npm rows**. The known-malicious ones sat at ranks 26, 57, 74, 88, 90,
   96 and 128 of 150.
3. **Per signal, within npm only (the fair comparison, since all positives are npm):** name similarity 0.45,
   blast radius 0.48, GitHub evidence 0.35. None beats chance. Over all rows blast radius shows 0.74, but that is an
   artefact: npm popular packages have far more dependents than PyPI ones and every positive is npm, so the signal
   is partly just identifying the ecosystem.
4. **Why we think GitHub evidence points the wrong way (a reading, not a proven cause):** malicious packages are taken
   down quickly and leave little GitHub footprint (their hit counts were 0 to 21), while candidates with large hit
   counts are mostly legitimate independent packages (`pytest-lazy-fixture`, `django-tables`, `anima`).
5. **We did not retune the weights to fix this.** There are only 6 distinct positives; adjusting weights until they
   rank well would be overfitting and would make the validation meaningless.
6. **Name similarity alone also has weak separating power on PyPI:** at a distance cut-off of 0.30, 7.9% of the 11,817
   known-malicious PyPI names are flagged, against 16.8% of the popular packages themselves (a rough stand-in for
   benign names). The pipeline's chosen cut-off of 0.65 flags 52% of malicious names but 86% of popular names.

**How to read the final score, given this:** it estimates *how much exposure there would be if the candidate were
malicious* (how close the name, how many people could be affected, whether anyone really uses the name), not
*whether it is malicious*. The ground-truth check is a separate, stricter test, and the honest result is that this
formula does not pass it.

## Limits
- OpenSSF listing means "reported malicious", absence does not mean safe. It can also list a name for a past
  compromise of a legitimate package.
- Only 6 distinct positive examples, all npm. Any AUC here has a very wide uncertainty.
- Signal 3 only checked the 150 closest names, so it is not a registry-wide measurement.
- Signal 2 depends on a third-party dependent count (`scoring/blast_radius_fetch.py`, ecosyste.ms). All 131 popular
  packages returned a figure, but 15 of them (all PyPI) returned 0, which may mean "no dependents recorded" rather
  than "none exist". Counts are not comparable across ecosystems, which is why the validation is also reported within npm.
- Seven rows have only two usable signals because their GitHub hit count was above 5,000 and was ignored.
