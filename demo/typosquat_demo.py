# %% [markdown]
# # Typosquat detector: live demo
# Run each cell with Shift+Enter (VS Code shows "Run Cell" above each `# %%`).
# - Signal 1 (name similarity) is computed LIVE for any name you type.
# - Signal 3 (GitHub evidence) and the GH Archive scan are looked up from saved results.
# - The Spark pipeline itself is shown through the notebooks and the numbers cell.

# %%
import os, json, urllib.request
import pandas as pd

ROOT = os.getcwd()
if not os.path.isdir(os.path.join(ROOT, "data")):
    ROOT = os.path.dirname(ROOT)          # works if you run it from the demo/ folder
DATA = os.path.join(ROOT, "data")
print("Using data folder:", DATA)

# %%
# The 15,000 most-downloaded PyPI packages. Downloaded once (needs internet), then cached
# in data/pypi_popular_names.txt so the demo also works offline.
POPULAR_TXT = os.path.join(DATA, "pypi_popular_names.txt")
POPULAR_URL = "https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.json"

if not os.path.exists(POPULAR_TXT):
    print("First run: downloading the popular-package list...")
    req = urllib.request.Request(POPULAR_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.load(r)["rows"]
    with open(POPULAR_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(row["project"] for row in rows))

with open(POPULAR_TXT, encoding="utf-8") as f:
    popular = [line.strip().lower() for line in f if line.strip()]
print(len(popular), "popular packages loaded")

# %%
# Signal 1: the same math the Spark pipeline uses.
# 1) cut a name into overlapping 2-character shingles  2) Jaccard distance between the sets
def shingles(name, n=2):
    s = name.lower()
    return {s[i:i + n] for i in range(len(s) - n + 1)}

def jaccard_distance(a, b):
    if not a or not b:
        return 1.0
    return 1 - len(a & b) / len(a | b)

popular_sets = {p: shingles(p) for p in popular}

THRESHOLD = 0.65       # similarity cut-off chosen in the prototype
MAX_LEN_RATIO = 1.5    # length filter used in the full PyPI run

def signal1(name, top=5):
    name = name.strip().lower()
    mine = shingles(name)
    rows = []
    for p, ps in popular_sets.items():
        if p == name:
            continue
        d = jaccard_distance(mine, ps)
        ratio = max(len(name), len(p)) / max(1, min(len(name), len(p)))
        rows.append((p, round(d, 4), round(1 - d, 4), round(ratio, 2)))
    df = pd.DataFrame(rows, columns=["popular_package", "distance", "similarity", "length_ratio"])
    df = df.sort_values("distance").head(top).reset_index(drop=True)
    df["flagged"] = (df["distance"] <= THRESHOLD) & (df["length_ratio"] <= MAX_LEN_RATIO)
    return df

def check(name):
    name = name.strip().lower()
    print(f"\n=== {name} ===")
    if name in popular_sets:
        print("(this IS one of the 15,000 popular packages; showing its closest neighbours)")
    print(signal1(name).to_string(index=False))

check("reqeusts")          # a classic typosquat of requests

# %%
check("flask-restplus")    # a LEGITIMATE package that still looks 'similar' to flask-restful

# %%
check("kubernetes")        # something unrelated: distances stay high

# %%
# Type any name here and re-run this cell
check("djanggo")

# %%
# Signal 3: real-world evidence from GitHub Code Search (saved results for the 150 closest candidates)
evidence = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))

def signal3(name):
    name = name.strip().lower()
    hit = evidence[evidence["candidate_name"].str.lower() == name].copy()
    print(f"\n=== GitHub evidence for {name} ===")
    if hit.empty:
        print("Not among the 150 candidates we checked (only the closest matches were searched).")
        return
    def label(n):
        if pd.isna(n):
            return "not checked"
        if n == 0:
            return "no files found"
        if n > 5000:
            return "common-word noise, not evidence"
        return "plausible evidence it exists in real dependency files"
    hit["reading"] = hit["github_hit_count"].map(label)
    cols = ["popular_name", "candidate_name", "ecosystem", "github_hit_count", "example_repo", "reading"]
    print(hit[cols].to_string(index=False))

signal3("0router")
signal3("wheeel")
signal3("expect")

# %%
# A hit shows the NAME EXISTS in a real file. It does not prove malicious intent.
# The router family: one popular package, several digit-prefixed lookalikes.
fam = evidence[evidence["popular_name"].str.lower() == "router"]
print(fam[["candidate_name", "github_hit_count", "example_repo"]].sort_values("github_hit_count").to_string(index=False))

# %%
# GH Archive scan: repos named after our candidates (activity evidence only)
gh = pd.read_csv(os.path.join(DATA, "gharchive_matches.csv"))
print("Scanned 12,061,354 events (11,555,061 pushes) over 168 hourly files in about 135 s")
print(len(gh), "repos matched,", gh["short"].nunique(), "of the 142 candidate names matched anything")
print(gh.groupby("short").agg(repos=("repo", "count"), pushes=("pushes", "sum")).sort_values("repos", ascending=False))

# %%
# Why this needs big-data tools
naive_pairs = 884_779 * 15_000
print(f"Naive comparisons, PyPI names x popular list: {naive_pairs:,}")
timing = pd.DataFrame({
    "candidate names": ["2,000", "20,000", "100,000", "884,779 (full PyPI)"],
    "Spark time": ["34.7 s", "92.3 s", "322.5 s", "about 9 min"],
})
print(timing.to_string(index=False))
print("Time grew much more slowly than the data, because Spark spreads the work across cores.")

# %%
# Combined score (filled in once the scoring work is merged into data/final_scores.csv)
final_path = os.path.join(DATA, "final_scores.csv")
if os.path.exists(final_path):
    print(pd.read_csv(final_path).head(10).to_string(index=False))
else:
    print("Combined scoring not available yet: data/final_scores.csv does not exist.")

# %% [markdown]
# ## Limits to state out loud
# - Signal 1 here is exact Jaccard over the 15,000 popular names; the Spark run applied the same
#   distance to 884,779 PyPI names. npm ran on a 20,000-name sample; the full run is unresolved.
# - Name similarity alone cannot separate attacks from coincidences (flask-restplus scored closer
#   to flask-restful than reqeusts did to requests), which is why there are three signals.
# - A GitHub hit shows a name exists in a dependency file, not that anyone was attacked.
# %%
