# Likely faculty questions, with honest answers

**1. Why is this a big-data project and not just a script?**
Signal 1 would need 13.3 billion name comparisons for PyPI alone if done naively; MinHash + LSH avoids comparing
most pairs and Spark parallelises the rest (about 9 minutes for 884,779 names). Signal 3 scans archives of tens of
millions of events per week (12,061,354 events in 135 s).

**2. What exactly are MinHash and LSH?**
MinHash compresses a set (a name's 2-letter shingles) into a short signature such that two signatures agree in
about the same fraction of positions as the sets' Jaccard similarity. LSH puts signatures into buckets so that
similar ones collide; only colliding names are compared.

**3. Why Jaccard on 2-character shingles?**
It is cheap, order-light and works with MinHash. Its weakness: short names and transpositions look far apart
(`reqeusts` vs `requests` is 0.60), and `aa`, `aaa`, `aaaa` are identical. We state that limit.

**4. Why did npm run on a sample?**
The full 4.5 million-name join ran out of memory repeatedly on a free machine. We do not know whether the machine
or our settings were the cause, so we kept a 20,000-name sample and documented it as unresolved.

**5. What does the score actually mean? Does it find malware?**
No. It summarises exposure: how close the name is, how many packages depend on the imitated one, and whether the
name appears in real files. Validation shows it does not separate known-malicious candidates from the rest (AUC 0.47
over all rows, 0.35 within npm; 6 distinct positives).

**6. So what did validation show?**
The name-similarity shortlist does contain real attacks: 6 of 70 npm candidates are in OpenSSF's malicious list (0 of 74 on
PyPI). The weighted score did not rank them high (positions 26 to 128 of 150). Our reading: taken-down malicious packages
leave little GitHub trace while heavily used lookalikes are mostly legitimate. We did not retune weights on six
examples. Blast radius alone scores 0.74 over all rows, but that is an artefact: all positives are npm, which has
far larger dependent counts; within npm it is 0.48.

**7. How were the weights chosen?**
By reasoning, written down in `scoring/scoring_design.md` (0.25 / 0.30 / 0.45), then checked for sensitivity:
the ranking is moderately stable across weight settings (Spearman 0.59 to 0.99; top-10 overlap 3 to 9 of 10). They are not fitted, because there is no labelled training set.

**8. Why do you ignore hit counts above 5,000?**
Those names are common words (`expect` has 279,552 hits), so the hits say nothing about packages. The 5,000 limit is
a judgment call.

**9. Why a graph database for Signal 2?**
"Who depends on whom, within N steps" is a traversal question that graphs answer naturally. Honest gap: our graph holds forward
dependencies only, so dependent counts came from a public index instead.

**10. Is a GitHub hit proof of an attack?**
No. It shows the name exists in a dependency file. The GH Archive scan shows repo activity by name only.

**11. What would you do with more time?**
Full npm run with verified memory settings; run Signal 3 on all 11,817 known-malicious PyPI names for a larger
validation set; use takedown status as a feature; load reverse dependencies into Neo4j.

**12. What went wrong, and what did you learn?**
Free-tier outages, a silent vocabulary bug caught by hand-checking one pair, a leaked token blocked by push
protection, and several early estimates we retracted. The main lesson: say "uncertain" when a cause is untested.
