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
Week 1 — environment setup in progress (GitHub repo + Databricks configured).