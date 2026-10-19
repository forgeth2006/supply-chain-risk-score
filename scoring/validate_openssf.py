"""
Validation against the OpenSSF malicious-packages dataset (the ground truth).

What it does (all offline once the dataset is cloned; no API key needed):

  1. Clones github.com/ossf/malicious-packages with --filter=blob:none --no-checkout
     (a few seconds, only file NAMES are needed) into scoring/.cache/ and lists every
     reported-malicious package name for PyPI and npm.
  2. OVERLAP CHECK. Which of our 150 shortlisted candidates are listed as malicious?
     -> data/validation_overlap.csv
  3. SIGNAL 1 RECALL. Of all known-malicious PyPI names, what fraction would name
     similarity alone flag (distance to a popular PyPI package at or below a cut-off,
     with the same length filter as the pipeline)? Compared with the same flag rate for
     the popular packages themselves, used as a rough stand-in for benign names.
     -> data/validation_signal1_recall.csv
  4. Writes a human-readable summary -> data/validation_summary.md

Run from the repository root:
    pip install pandas numpy scipy
    python scoring/validate_openssf.py

Honest limits (also written into the summary file):
  * The dataset says a package WAS reported malicious. Absence from it does not mean safe.
  * Many malicious packages are not typosquats (random names, dependency confusion), so
    recall of a name-similarity signal is expected to be well below 100%.
  * The benign comparison uses popular packages, not the whole registry.
"""
import json
import os
import re
import subprocess
import sys
from datetime import date

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(ROOT, "scoring", ".cache")
MP_DIR = os.path.join(CACHE, "malicious-packages")
REPO_URL = "https://github.com/ossf/malicious-packages.git"

MAX_LEN_RATIO = 1.5  # same length filter as the Spark run
CUTOFFS = [0.30, 0.40, 0.50, 0.65]  # Jaccard distance cut-offs to report


def norm_pypi(name):
    """PyPI name normalisation (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def ensure_clone():
    os.makedirs(CACHE, exist_ok=True)
    if not os.path.isdir(os.path.join(MP_DIR, ".git")):
        print("Cloning OpenSSF malicious-packages (names only, a few seconds)...")
        subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
                        REPO_URL, MP_DIR], check=True)


def list_malicious():
    """Return (set of PyPI names, set of npm names, commit hash, commit date)."""
    ensure_clone()

    def ls(eco):
        out = subprocess.run(["git", "-C", MP_DIR, "ls-tree", "-r", "--name-only", "HEAD",
                              f"osv/malicious/{eco}"], check=True, capture_output=True, text=True).stdout
        return [l for l in out.splitlines() if l.endswith(".json")]

    py, npm = set(), set()
    for p in ls("pypi"):
        py.add(norm_pypi(p.split("/")[3]))
    for p in ls("npm"):
        parts = p.split("/")
        # osv/malicious/npm/<name>/MAL-x.json   or   osv/malicious/npm/@scope/<name>/MAL-x.json
        npm.add("/".join(parts[3:-1]).lower())
    commit = subprocess.run(["git", "-C", MP_DIR, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    cdate = subprocess.run(["git", "-C", MP_DIR, "log", "-1", "--format=%cs"], capture_output=True, text=True).stdout.strip()
    return py, npm, commit, cdate


# ---------- Signal 1 (same maths as the pipeline): 2-character shingles, Jaccard ----------
def shingle_matrix(names):
    """Binary matrix names x (2-char shingle) using the character codes themselves."""
    rows, cols = [], []
    sizes = np.zeros(len(names), dtype=np.int32)
    for i, n in enumerate(names):
        s = {n[k:k + 2] for k in range(len(n) - 1)}
        sizes[i] = len(s)
        for sh in s:
            rows.append(i)
            cols.append((min(ord(sh[0]), 255) << 8) | min(ord(sh[1]), 255))
    m = csr_matrix((np.ones(len(rows), dtype=np.float32), (rows, cols)), shape=(len(names), 65536))
    return m, sizes


def best_distance(queries, popular, exclude_self=False):
    """For each query name: smallest Jaccard distance to a popular name that passes the
    length-ratio filter. Chunked sparse products keep memory small."""
    qm, qs = shingle_matrix(queries)
    pm, ps = shingle_matrix(popular)
    pmT = pm.T.tocsc()
    qlen = np.array([len(q) for q in queries], dtype=np.float32)
    plen = np.array([len(p) for p in popular], dtype=np.float32)
    best = np.ones(len(queries), dtype=np.float32)
    for start in range(0, len(queries), 500):
        sl = slice(start, min(start + 500, len(queries)))
        inter = (qm[sl] @ pmT).toarray()                       # |A ∩ B|
        union = qs[sl, None] + ps[None, :] - inter             # |A ∪ B|
        with np.errstate(divide="ignore", invalid="ignore"):
            dist = 1.0 - np.where(union > 0, inter / union, 0.0)
        ratio = np.maximum(qlen[sl, None], plen[None, :]) / np.maximum(1, np.minimum(qlen[sl, None], plen[None, :]))
        dist = np.where(ratio <= MAX_LEN_RATIO, dist, 1.0)
        if exclude_self:
            for j, qi in enumerate(range(sl.start, sl.stop)):
                dist[j, qi] = 1.0
        # a query with no shingles (single character) cannot be compared
        dist[qs[sl] == 0, :] = 1.0
        best[sl] = dist.min(axis=1)
    return best


def main():
    py_mal, npm_mal, commit, cdate = list_malicious()
    print(f"OpenSSF dataset: {len(py_mal):,} PyPI names, {len(npm_mal):,} npm names (commit {commit[:8]}, {cdate})")

    # ---------- 2. overlap with the shortlist ----------
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))

    def listed(eco, name):
        return (norm_pypi(name) in py_mal) if eco == "pypi" else (name.lower() in npm_mal)

    ev["candidate_listed_malicious"] = [listed(e, n) for e, n in zip(ev.ecosystem, ev.candidate_name)]
    ev["popular_name_listed_malicious"] = [listed(e, n) for e, n in zip(ev.ecosystem, ev.popular_name)]
    keep = ["popular_name", "candidate_name", "ecosystem", "jaccard_distance", "github_hit_count",
            "candidate_listed_malicious", "popular_name_listed_malicious"]
    ev[keep].to_csv(os.path.join(DATA, "validation_overlap.csv"), index=False)
    evd = ev.drop_duplicates(["ecosystem", "candidate_name"])  # one candidate can impersonate two popular names
    n_cand = int(evd.candidate_listed_malicious.sum())
    n_rows = int(ev.candidate_listed_malicious.sum())
    by_eco = evd.groupby("ecosystem").candidate_listed_malicious.agg(["sum", "count"])
    print("Shortlist candidates listed as malicious, by ecosystem:\n", by_eco)

    # ---------- 3. Signal 1 recall on PyPI ----------
    pop_path = os.path.join(DATA, "pypi_popular_names.txt")
    with open(pop_path, encoding="utf-8") as f:
        popular = sorted({norm_pypi(l) for l in f if l.strip()})
    mal_py = sorted(n for n in py_mal if n not in set(popular) and len(n) >= 2)
    print(f"Comparing {len(mal_py):,} malicious PyPI names with {len(popular):,} popular names...")
    d_mal = best_distance(mal_py, popular)
    d_pop = best_distance(popular, popular, exclude_self=True)
    rows = []
    for c in CUTOFFS:
        rows.append({"distance_cutoff": c,
                     "malicious_flagged": int((d_mal <= c).sum()),
                     "malicious_total": len(mal_py),
                     "malicious_flag_rate": round(float((d_mal <= c).mean()), 4),
                     "popular_flag_rate_benign_proxy": round(float((d_pop <= c).mean()), 4)})
    rec = pd.DataFrame(rows)
    rec.to_csv(os.path.join(DATA, "validation_signal1_recall.csv"), index=False)
    print(rec.to_string(index=False))

    # ---------- 4. summary ----------
    lines = [f"# Validation against OpenSSF malicious-packages",
             f"",
             f"Generated {date.today()} by `scoring/validate_openssf.py`. Dataset commit `{commit[:8]}` ({cdate}); "
             f"{len(py_mal):,} PyPI and {len(npm_mal):,} npm package names reported malicious.",
             f"",
             f"## 1. Overlap with our shortlisted candidates",
             f"",
             f"**{n_cand} of {len(evd)} distinct candidate names are listed as malicious** ({n_rows} of {len(ev)} shortlist rows; "
             f"one candidate can sit under two popular names).",
             f""]
    for eco, r in by_eco.iterrows():
        lines.append(f"- {eco}: {int(r['sum'])} of {int(r['count'])}")
    hits = ev[ev.candidate_listed_malicious].drop_duplicates(["ecosystem", "candidate_name"])
    if len(hits):
        lines += ["", "| popular package | candidate listed as malicious | ecosystem | GitHub hit count |", "|---|---|---|---|"]
        for _, r in hits.iterrows():
            lines.append(f"| {r.popular_name} | {r.candidate_name} | {r.ecosystem} | {int(r.github_hit_count)} |")
    pm = ev[ev.popular_name_listed_malicious]
    if len(pm):
        lines += ["", "Note: these *popular* names are themselves in the dataset (the dataset can list a name for a past "
                  "compromise of a real package, so a listing alone does not make a lookalike malicious): "
                  + ", ".join(sorted(set(pm.popular_name))) + "."]
    lines += ["", "## 2. How many known-malicious PyPI names would name similarity alone flag?", "",
              "| distance cut-off | malicious flagged | flag rate (malicious) | flag rate (popular packages, benign proxy) |",
              "|---|---|---|---|"]
    for _, r in rec.iterrows():
        lines.append(f"| {r.distance_cutoff:.2f} | {int(r.malicious_flagged):,} of {int(r.malicious_total):,} | "
                     f"{r.malicious_flag_rate:.1%} | {r.popular_flag_rate_benign_proxy:.1%} |")
    lines += ["", "## Limits", "",
              "- Absence from the dataset does not mean a package is safe; presence means it was reported.",
              "- Most malicious packages are not typosquats, so a name-similarity signal is expected to miss many.",
              "- The benign comparison uses the 15,000 popular packages, not the full registry, so it is only a rough guide "
              "to false-positive pressure.",
              "- The dataset can include names listed for a past compromise of a legitimate package.",
              "- Only PyPI recall was computed (the popular list for npm was not re-fetched here)."]
    with open(os.path.join(DATA, "validation_summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Wrote data/validation_overlap.csv, data/validation_signal1_recall.csv, data/validation_summary.md")


if __name__ == "__main__":
    sys.exit(main())
