# Supply-Chain Risk Score: Detecting Typosquatted Packages on PyPI and npm

*Big Data and Modern Database Systems, course project. Team: Person A (Spark pipelines, Signal 1 and 3, scoring, validation) and Person B (graph database, Signal 2 design).*

> **Status.** Everything below is backed by files in this repository and was produced by the scripts in
> `scoring/`. The combined score uses all three signals.

## 1. Problem
A **typosquat** is a malicious package whose name is deliberately close to a popular one (`reqeusts` for
`requests`). Developers who mistype or copy a name install the attacker's code. Registries hold millions of
names, and most similar-looking names are innocent coincidences, so a detector based on spelling alone buries
reviewers in false alarms. Our own calibration shows why: the legitimate pair `flask-restful` / `flask-restplus`
(Jaccard distance 0.4375) looks *closer* than the real attack `requests` / `reqeusts` (0.60).

**Idea:** combine three kinds of evidence instead of one:
1. **Signal 1, name similarity**: how close is the name to a popular package? (Spark, MinHash + LSH)
2. **Signal 2, blast radius**: how many other packages depend on the package being imitated? (graph data)
3. **Signal 3, real-world evidence**: does the candidate name actually appear in real dependency files on GitHub, and is there repository activity under that name? (GitHub Code Search plus a GH Archive scan)

## 2. Architecture
```
PyPI + npm registry names --> [Spark: 2-char shingles -> MinHash -> LSH join] --> confusable-name pairs (Signal 1)
                                                                                         |
                                  shortlist: 75 closest per registry (150)  <------------+
                                        |                       |
              GitHub Code Search -------+                       +------- GH Archive week scan (Spark)
                    (Signal 3a)                                              (Signal 3b)
                                        |
 popular packages --> dependent counts (Signal 2) + Neo4j forward-dependency graph (graph_db/)
                                        |
                                  scoring/score.py  -->  data/final_scores.csv
                                        |
                          scoring/validate_openssf.py  (ground truth check)
```
Storage follows the data's shape (polyglot persistence): Parquet and CSV for bulk tabular results, a graph database
for relationships between packages.

## 3. Why this needs big-data tools
- **Signal 1 is an algorithmic problem.** Comparing every registry name to every popular name is
  884,779 x 15,000 = **13,271,685,000 comparisons** for PyPI alone, and the work grows with the product of the two
  sizes. MinHash turns each name into a short signature that preserves Jaccard similarity, and LSH only compares
  names that land in the same bucket. Spark spreads this across cores. Measured on one machine, time grew far more
  slowly than the data: 2,000 names 34.7 s, 20,000 names 92.3 s, 100,000 names 322.5 s, and the full 884,779-name
  PyPI registry about 9 minutes.
- **Signal 3b is a volume problem.** One week of GH Archive was **12,061,354 events** (11,555,061 pushes) in 168
  hourly files, scanned in about 135 s. A quarter is roughly 20 to 30 GB compressed (a range from one measured week).

## 4. Data
| Data | Source | Size |
|---|---|---|
| PyPI registry names | pypi.org simple index | 884,813 (34 junk entries removed) |
| npm registry names | `all-the-package-names` | 4,419,399 (873 junk entries removed) |
| Popular PyPI packages | `hugovk/top-pypi-packages` (download counts) | 15,000 |
| Popular npm packages | `tristan-f-r/npm-rank` | 10,000 |
| GH Archive | gharchive.org, 24 to 30 Aug 2026 | 168 files, about 1.6 GB |
| Ground truth | OpenSSF malicious-packages | 11,825 PyPI and 222,214 npm names |

## 5. Signal 1: name similarity
Names are cut into overlapping 2-character shingles, turned into binary vectors (`CountVectorizer(binary=True)`),
hashed with `MinHashLSH`, and matched with `approxSimilarityJoin` at Jaccard distance 0.65 or below.

Findings that shaped the result (details in `registry_lsh/lsh_similarity_design.md`):
- **Vocabulary bug.** Fitting the vectorizer on the popular list only silently dropped unseen shingles, making
  `build` / `1build` look identical (0.0 instead of the correct 0.2). Fitting on the full registry fixed it.
- **Degenerate strings** such as `aa`, `aaa`, `aaaa` are identical under 2-character shingles (a known blind spot).
- **Digit-prefix pattern.** Many closest matches are a popular name with one leading digit (`electron` / `4electron`).
- **PyPI** ran on the full registry. **npm ran on a 20,000-name sample** (8,537 pairs). A full npm run (4,515,551
  names) was attempted on a larger machine and failed with out-of-memory errors in the join; **the cause is
  uncertain** (a real memory limit, or settings that never took effect), so the sample remains the npm result.

## 6. Signal 2: blast radius
- **Built:** a Neo4j graph (`graph_db/`) of popular packages and the packages they depend on (forward edges only;
  the loaded graph is small, tens of nodes). Package names use the same lowercase format as the other signals.
- **Gap, stated plainly:** blast radius needs the reverse direction, who depends on a package, and the forward-only
  graph cannot answer that. We therefore collect dependent counts from a public index with
  `scoring/blast_radius_fetch.py` (ecosyste.ms, falling back to deps.dev) for the 131 distinct popular packages in
  the shortlist. A package with no figure is "unknown", never zero.
- **Result:** all 131 popular packages returned a dependent count (`data/blast_radius.csv`, source ecosyste.ms).
  The largest are `typescript` (488,056), `webpack` (216,244), `eslint-plugin-react` (105,111) and `express`
  (93,237). The median is 3,609 for the npm packages and 13 for the PyPI ones, so counts are **not comparable across
  ecosystems**. 15 PyPI packages returned 0, which may mean "none recorded" rather than "none exist".

## 7. Signal 3: real-world evidence
- **Code Search (3a).** For the 150 closest candidates (75 per registry) we asked GitHub whether any public
  `requirements.txt` or `package.json` contains the exact name. 93 of 150 returned at least one hit; 57 returned none.
  Seven hit counts were above 5,000 (for example `expect`, 279,552) and were discarded as common-word noise.
  A hit proves existence in a file, not malicious intent.
- **GH Archive scan (3b).** Repos named after candidates were matched in one week of pushes: 71 repos, but only 5
  of 142 candidate names matched anything (`elasticsearch` 43 repos, `9router` 17, `telemetry` 7, `anima` 3,
  `webdavclient` 1). None could be called malicious. This scan sees the repo name, not what was installed, so it is
  weak evidence; its value here is showing the pipeline at archive scale with honest numbers.
- GH Archive `PushEvent` carries no changed-file list, which is why Signal 1 must run first and Code Search is used
  for confirmation.

## 8. Combined score and validation
Full design and weight reasoning: `scoring/scoring_design.md`. In short: `s1 = 1 - distance`, `s2` and `s3` are
log-scaled to 0 to 1, weights 0.25 / 0.30 / 0.45, missing signals left out (never zero), tiers are presentation only.

**Validation against OpenSSF malicious-packages** (`data/validation_summary.md`):
- **6 of 70 distinct npm candidates are known-malicious** (`3lectron`, `3electron`, `4electron`, `4lectron`,
  `4meme-readable-stream`, `9args`), and 0 of 74 PyPI candidates. So the Signal 1 shortlist does surface real
  attack names on npm.
- **The combined score does not separate them from the rest.** AUC (0.5 is chance) was 0.47 over all 150 rows
  (a bootstrap interval of roughly 0.31 to 0.63) and 0.35 within npm only; the known-malicious names ranked 26th
  to 128th of 150. Within npm, each signal alone is also at or below chance (name similarity 0.45, blast radius
  0.48, GitHub evidence 0.35). Blast radius looks good over all rows (0.74) only because every positive is npm and
  npm packages have far more dependents; that is an artefact, not skill.
- **Likely reason for the GitHub signal (a reading, not proven):** known-malicious packages are removed quickly and
  leave small GitHub footprints (0 to 21 hits), while heavily used lookalikes tend to be legitimate packages.
  We did not retune weights on six examples.
- **The ranking is only moderately stable** under different weights (Spearman 0.59 to 0.99, top-10 overlap 3 to 9 of 10),
  mostly because of the ecosystem difference in dependent counts.
- **Name similarity alone is a weak filter on PyPI:** at distance 0.30, 7.9% of 11,817 known-malicious names are
  flagged versus 16.8% of the popular packages themselves (a rough benign stand-in). At the pipeline's 0.65 cut-off
  the numbers are 52% versus 86%. This supports the premise that spelling alone is not enough, and also shows that
  adding Signals 2 and 3 as we built them did not fix it.
- The score is best read as "exposure if this candidate were malicious", not "probability that it is".

## 9. Challenges (and what each taught)
1. Free-tier compute: Databricks outage, Colab disk wiped on restart, Kaggle memory failures. Lesson: move durable
   data off the working disk, and treat an unexplained failure as unexplained instead of inventing a cause.
2. Silent correctness bug (vocabulary scope) found by hand-verifying one pair. Lesson: check small known cases.
3. An anomalous GH Archive week (almost no pushes 1 to 4 Sep) found by inspecting file contents before processing.
4. A token committed in a notebook was blocked by GitHub push protection; fixed by rewriting local history, not by
   redacting only the latest version. Lesson: a committed secret stays in history.
5. Over-claims retracted along the way (a "hard memory ceiling", data-volume extrapolations), now stated as ranges or
   as uncertain.

## 10. Limitations
- npm Signal 1 is a 20,000-name sample; the full run is unresolved.
- Signal 3 covers only the 150 closest names, and Code Search counts are existence, not intent.
- The GH Archive scan is one week and matches by repo name only.
- Signal 2 depends on a third-party index and on a forward-only graph; coverage may be incomplete.
- The combined score does not pass the ground-truth ranking test (section 8). Only six distinct positives exist, all npm.
- Dependent counts come from one third-party index and cannot be compared across ecosystems.
- OpenSSF absence is not proof of safety; presence can reflect a past compromise of a legitimate name.

## 11. Reproducibility
- Live demo (offline after first run): `python demo/typosquat_demo.py`, cell by cell in VS Code (`demo/DEMO_RUNBOOK.md`).
- Rebuild scores: `python scoring/blast_radius_fetch.py` (internet, about 3 minutes), `python scoring/validate_openssf.py`, `python scoring/score.py`.
- Spark pipelines are in `gharchive_scan/signal3_pipeline.ipynb` and described in `registry_lsh/`; the large Parquet
  output is not committed (`data/pypi_lsh_matches_sample.csv` is a 500-row sample).
- Dependencies for scoring: `pip install -r scoring/requirements.txt`.

## 12. Future work
Full npm run on a machine with verified memory settings; validate the score on a larger labelled set (for example
run Signal 3 on the 11,817 known-malicious PyPI names, not only on our shortlist); treat "taken down" as a feature;
use reverse-dependency data inside Neo4j.
