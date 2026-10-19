# 10-minute demo runbook

**Setup (do this once, before the faculty arrives)**
1. Open the repo folder in VS Code. Install the "Python" extension if it is missing.
2. `pip install pandas numpy scipy`  (the demo itself needs only pandas)
3. Open `demo/typosquat_demo.py`. Click **Run Cell** on the first two cells. They load the data and print
   `15000 popular packages loaded`. If the popular list is missing it downloads once, so do this with internet on.
4. Keep a backup: screen-record one clean run, and keep `data/*.csv` open in a tab in case VS Code misbehaves.

**Run order (about 10 minutes)**

| Min | Cell | What to say |
|---|---|---|
| 0:00 | Slide or README | "Typosquatting: attackers publish `reqeusts` hoping you mistype `requests`. Spelling alone gives too many false alarms, so we combine three signals." |
| 1:00 | `check("reqeusts")` | "Live Signal 1: names become 2-letter shingles and we compare sets (Jaccard). Closest is requests." |
| 2:00 | `check("flask-restplus")` | "A legitimate package scores closer to flask-restful (0.44) than the real attack scores to requests (0.60). Spelling alone cannot decide." |
| 3:00 | `check("kubernetes")`, `check("djanggo")` | Unrelated stays far; a typo is caught. Invite a faculty member to type a name. |
| 4:00 | Why big data cell | "13.3 billion naive comparisons. MinHash + LSH in Spark: 34.7 s, 92.3 s, 322.5 s for 2k, 20k, 100k names, about 9 min for all 884,779 PyPI names." |
| 5:00 | Signal 3 cells (`0router`, `wheeel`, `expect`) | "We asked GitHub whether real files contain these names. `expect` has 279,552 hits, so we discard it as a common word. A hit means the name exists, not that it is malicious." |
| 6:00 | GH Archive cell | "One week, 12 million events, 135 seconds. Only 5 of 142 names matched, none malicious. That is an honest result." |
| 7:00 | Combined score cell | "Every signal stays visible so a reviewer can see why a row ranks where it does." |
| 8:00 | Validation cell | "We checked against OpenSSF's malicious-package list. 6 of our 70 npm candidates are on it: `3lectron`, `4electron`, `9args` and others. But our combined score does not separate them from the rest (AUC 0.47, about chance), and we say so instead of tuning to hide it." |
| 9:30 | Limits (last markdown cell) | Read the four limits aloud. Ask for questions. |

**If something breaks:** every cell reads saved CSVs, so only the first run needs internet. If a cell errors, re-run
the first two cells (a restarted kernel forgets variables) and then the failing cell.

**Do not claim:** that the score detects malware, that npm was run on the full registry, or that any GH Archive match is malicious.
