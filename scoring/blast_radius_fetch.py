"""
Signal 2 (blast radius) data fetch: how many other packages depend on each popular package
that our shortlisted candidates imitate.

WHY THIS EXISTS: the Neo4j graph built in graph_db/ stores FORWARD edges only (what a popular
package depends on). Blast radius needs REVERSE edges (who depends on it), which a registry's
own API does not give, so we ask two public services that index the whole ecosystem:

  1. ecosyste.ms   GET https://packages.ecosyste.ms/api/v1/registries/{pypi.org|npmjs.org}/packages/{name}
                   field used: dependent_packages_count   (no key needed)
  2. deps.dev      fallback, only if (1) fails for a package. Needs the latest version first, then
                   GET https://api.deps.dev/v3alpha/systems/{pypi|npm}/packages/{name}/versions/{ver}:dependents
                   field used: dependentCount

If both fail the package is recorded as MISSING (empty cell). Missing means UNKNOWN, never zero:
score.py then leaves Signal 2 out for that row instead of treating it as "no dependents".

Run from the repository root (needs internet; about 2-4 minutes for 131 packages):
    pip install requests pandas
    python scoring/blast_radius_fetch.py

Output: data/blast_radius.csv  (ecosystem, popular_name, dependents, source, note)
The script is resumable: rows already fetched successfully are kept and skipped on re-run.
"""
import os
import sys
import time
from urllib.parse import quote

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "blast_radius.csv")
HEADERS = {"User-Agent": "typosquat-student-project (college coursework)"}
REGISTRY = {"pypi": "pypi.org", "npm": "npmjs.org"}
DEPSDEV_SYSTEM = {"pypi": "pypi", "npm": "npm"}


def get_json(url, tries=3):
    for k in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json(), None
            if r.status_code == 404:
                return None, "404 not found"
            if r.status_code in (429, 502, 503):
                time.sleep(2 * (k + 1))
                continue
            return None, f"HTTP {r.status_code}"
        except requests.RequestException as e:
            time.sleep(2 * (k + 1))
            last = str(e)[:80]
    return None, locals().get("last", "retries exhausted")


def from_ecosystems(eco, name):
    url = f"https://packages.ecosyste.ms/api/v1/registries/{REGISTRY[eco]}/packages/{quote(name, safe='')}"
    js, err = get_json(url)
    if js is None:
        return None, err
    val = js.get("dependent_packages_count")
    if val is None:
        return None, "field dependent_packages_count missing"
    return int(val), None


def from_depsdev(eco, name):
    system = DEPSDEV_SYSTEM[eco]
    base = f"https://api.deps.dev/v3/systems/{system}/packages/{quote(name, safe='')}"
    js, err = get_json(base)
    if js is None:
        return None, "deps.dev package lookup: " + str(err)
    versions = js.get("versions", [])
    default = [v for v in versions if v.get("isDefault")]
    chosen = (default or versions[-1:] or [None])[0]
    if not chosen:
        return None, "deps.dev: no versions"
    ver = chosen["versionKey"]["version"]
    url = (f"https://api.deps.dev/v3alpha/systems/{system}/packages/{quote(name, safe='')}"
           f"/versions/{quote(ver, safe='')}:dependents")
    js2, err2 = get_json(url)
    if js2 is None:
        return None, "deps.dev dependents: " + str(err2)
    if "dependentCount" not in js2:
        return None, "deps.dev: dependentCount missing"
    return int(js2["dependentCount"]), None


def main():
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))
    todo = ev[["ecosystem", "popular_name"]].drop_duplicates().reset_index(drop=True)

    done = {}
    if os.path.exists(OUT):
        old = pd.read_csv(OUT)
        for _, r in old.dropna(subset=["dependents"]).iterrows():
            done[(r.ecosystem, r.popular_name)] = r.to_dict()

    rows = list(done.values())
    for i, r in todo.iterrows():
        key = (r.ecosystem, r.popular_name)
        if key in done:
            continue
        val, err = from_ecosystems(r.ecosystem, r.popular_name)
        src, note = "ecosyste.ms", ""
        if val is None:
            val2, err2 = from_depsdev(r.ecosystem, r.popular_name)
            if val2 is not None:
                val, src = val2, "deps.dev"
            else:
                src, note = "", f"ecosyste.ms: {err}; {err2}"
        rows.append({"ecosystem": r.ecosystem, "popular_name": r.popular_name,
                     "dependents": val, "source": src, "note": note})
        print(f"[{i + 1}/{len(todo)}] {r.ecosystem}:{r.popular_name} -> {val if val is not None else 'MISSING'} {src}")
        pd.DataFrame(rows).to_csv(OUT, index=False)   # save as we go
        time.sleep(0.5)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    ok = out["dependents"].notna().sum()
    print(f"\nDone: {ok} of {len(out)} packages have a dependent count; "
          f"{len(out) - ok} are MISSING (unknown, not zero). Saved to {OUT}")
    if ok == 0:
        print("Nothing was fetched. Check your internet connection and that the two services are reachable.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
