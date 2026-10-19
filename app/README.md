# Live demo app

Every page runs a real step of the pipeline when you click.

## Start it (Windows PowerShell, from the repository root)

    pip install flask pandas numpy scipy requests
    python app/app.py

The browser opens at http://127.0.0.1:5000 (if not, open that address yourself). Stop with Ctrl+C.

## Optional extras
- Real Spark button (page 1): install Java 17 and run `pip install pyspark`.
  If missing, the button shows a clear message; the MinHash+LSH on that page is our own implementation and works anyway.
- Live GitHub search (page 4 and the end-to-end page): paste a GitHub token (any classic token, no scopes needed)
  in the box at the bottom-left of the page. It is kept in the page's memory only. Without it, names in our saved
  150 candidates still show their saved GitHub result.

## Pages
0 Overview + environment check | 1 Name similarity (live shingles, MinHash, LSH, optional real Spark) |
2 Scale test (brute force vs LSH, extrapolated to 13.3 billion pairs) | 3 Blast radius (live ecosyste.ms call) |
4 GitHub evidence (live code search + live scan of one GH Archive hour) | 5 Combined score (real scoring code, weight sliders,
re-ranks all 150) | 6 Validation (OpenSSF lookup, AUC, optional re-run of the validation script) | Star: end-to-end check of one name.

## Needs these files in data/ (already in the repo, plus one new one)
pypi_popular_names.txt, signal3_evidence_results.csv, blast_radius.csv, final_scores.csv, validation_overlap.csv,
validation_signal1_recall.csv, and the new openssf_malicious_pypi_names.txt (11,825 reported-malicious PyPI names).
