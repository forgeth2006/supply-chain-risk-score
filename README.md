# Supply-Chain Risk Score

## What this is
A system that detects **typosquat packages** on PyPI/npm — malicious packages
with names deliberately similar to popular ones (e.g. `reqeusts` vs `requests`)
— and scores how dangerous each one actually is, by combining three signals:

1. **Name similarity** — how close a candidate's name is to a popular package
   (computed via MinHash + LSH, run as a distributed Spark job across the
   full PyPI + npm registries)
2. **Blast radius** — how many other packages depend on the legitimate package
   being impersonated (computed via graph traversal in Neo4j)
3. **Real adoption evidence** — proof that real GitHub repositories have
   actually installed the suspicious candidate (mined from GH Archive)

Most existing typosquat detectors only use signal 1, which produces too many
false positives to be useful. Combining all three — especially real evidence
of adoption — is what makes this different.

## Architecture

[PyPI + npm registry names] --> [Spark: MinHash + LSH] --> confusable-name clusters
                                                                    |
                                                                    v
[GH Archive events] --> [Spark: filtered scan] --> adoption evidence --> [Neo4j Graph DB]
                                                                              |
                                                                              v
                                                                    [Scoring layer]
                                                                              |
                                                                              v
                                                                [Streamlit Dashboard]

## Team
- Person A (Big Data/Spark): registry-wide LSH pipeline, GH Archive scanning
- Person B (Graph DB/Product): graph schema, blast radius, scoring formula, dashboard

## Status
| Part | State |
|---|---|
| Signal 1, PyPI | Full registry (884,779 names) |
| Signal 1, npm | 20,000-name sample; full run attempted and unresolved (cause uncertain) |
| Signal 3 | GitHub Code Search on the 150 closest candidates, plus a one-week GH Archive scan |
| Signal 2 | Neo4j forward-dependency graph built; reverse dependent counts for all 131 popular packages via `scoring/blast_radius_fetch.py` (ecosyste.ms) |
| Combined score | `scoring/score.py`, design in `scoring/scoring_design.md` |
| Validation | `scoring/validate_openssf.py` against OpenSSF malicious-packages: 6 of 70 npm candidates are known-malicious, but the combined score does not separate them from the rest (AUC 0.47; see report) |

## Quick start
```
pip install -r scoring/requirements.txt
python demo/typosquat_demo.py          # live demo, cell by cell in VS Code (see demo/DEMO_RUNBOOK.md)
python scoring/blast_radius_fetch.py   # needs internet; writes data/blast_radius.csv
python scoring/validate_openssf.py     # clones OpenSSF names (few seconds), writes data/validation_*
python scoring/score.py                # writes data/final_scores.csv
```

## Where to read
- `report/final_report.md` full write-up, `report/faculty_QA.md` likely questions
- `registry_lsh/`, `gharchive_scan/`, `graph_db/`, `scoring/` design notes per component
