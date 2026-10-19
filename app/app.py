"""
Live demo web app for the typosquat detector.

Every page runs a REAL step of the pipeline when you click (nothing on a page is a screenshot):
  Signal 1  name similarity  : shingles -> MinHash -> LSH on the 15,000 popular PyPI names (own implementation),
                               plus the REAL Spark ML MinHashLSH job (separate process)
  Scale test                 : brute force vs LSH timing, extrapolated to the full registry
  Signal 2  blast radius     : live call to ecosyste.ms (deps.dev fallback)
  Signal 3  evidence         : live GitHub Code Search (needs a token) and a live GH Archive scan of one hour
  Score                      : the real scoring code (scoring/score.py) re-run with your weights
  Validation                 : OpenSSF ground truth, AUC re-computed live, optional full re-run of the script

Start it from the repository root:
    pip install flask pandas numpy scipy requests
    python app/app.py
and open http://127.0.0.1:5000
"""
import gzip
import importlib.util
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests
from flask import Flask, jsonify, request, send_from_directory

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, os.path.join(ROOT, "scoring"))
import score as scoremod                      # the project's real scoring code
import blast_radius_fetch as brf              # the project's real Signal 2 fetch code

app = Flask(__name__, static_folder=os.path.join(APP, "static"), static_url_path="/static")

# ----------------------------------------------------------------------------------------------
# Signal 1: shingles, Jaccard, MinHash, LSH   (same math as the Spark pipeline, written out in numpy)
# ----------------------------------------------------------------------------------------------
THRESHOLD = 0.65       # distance cut-off chosen in the project
MAX_LEN_RATIO = 1.5    # length filter used in the full PyPI run
NHASH = 10             # we keep 10 MinHash functions; the slider chooses how many LSH tables (1..10) to use
PRIME = 4294967311
_rng = np.random.RandomState(42)
HA = _rng.randint(1, 2 ** 30, size=NHASH).astype(np.int64)
HB = _rng.randint(0, 2 ** 30, size=NHASH).astype(np.int64)


def shingles(name):
    s = name.lower()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jacc_dist(a, b):
    if not a or not b:
        return 1.0
    return 1.0 - len(a & b) / len(a | b)


def minhash(shs):
    xs = np.array([(ord(s[0]) * 1114112 + ord(s[1])) % PRIME for s in shs], dtype=np.int64)
    return ((xs[:, None] * HA[None, :] + HB[None, :]) % PRIME).min(axis=0)


class Index:
    def __init__(self, names):
        self.names = names
        self.sets = [shingles(n) for n in names]
        self.sigs = np.full((len(names), NHASH), -1, dtype=np.int64)
        for i, s in enumerate(self.sets):
            if s:
                self.sigs[i] = minhash(s)
        self.tables = self._tables(len(names))

    def _tables(self, n):
        tabs = [dict() for _ in range(NHASH)]
        for i in range(n):
            if self.sigs[i, 0] < 0:
                continue
            for j in range(NHASH):
                tabs[j].setdefault(int(self.sigs[i, j]), []).append(i)
        return tabs

    def candidates(self, sig, tables, tabs=None):
        tabs = tabs or self.tables
        out = set()
        for j in range(tables):
            out.update(tabs[j].get(int(sig[j]), ()))
        return out


def load_popular():
    path = os.path.join(DATA, "pypi_popular_names.txt")
    if not os.path.exists(path):
        r = requests.get("https://hugovk.github.io/top-pypi-packages/top-pypi-packages-30-days.json",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        r.raise_for_status()
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(row["project"] for row in r.json()["rows"]))
    with open(path, encoding="utf-8") as f:
        return [ln.strip().lower() for ln in f if ln.strip()]


POPULAR = load_popular()
t0 = time.time()
INDEX = Index(POPULAR)
print(f"[startup] {len(POPULAR)} popular names indexed (MinHash + LSH) in {time.time() - t0:.1f}s")


def len_ratio(a, b):
    return max(len(a), len(b)) / max(1, min(len(a), len(b)))


@app.get("/api/signal1")
def api_signal1():
    name = request.args.get("name", "").strip().lower()
    tables = max(1, min(NHASH, int(request.args.get("tables", 5))))
    if len(name) < 2:
        return jsonify(error="Type a name with at least 2 characters.")
    mine = shingles(name)

    t = time.perf_counter()
    scored = []
    for i, ps in enumerate(INDEX.sets):
        p = POPULAR[i]
        if p == name:
            continue
        scored.append((jacc_dist(mine, ps), i))
    brute_ms = (time.perf_counter() - t) * 1000
    scored.sort()
    brute_hits = {i for d, i in scored if d <= THRESHOLD and len_ratio(name, POPULAR[i]) <= MAX_LEN_RATIO}

    t = time.perf_counter()
    sig = minhash(mine)
    cand = INDEX.candidates(sig, tables)
    cand.discard(POPULAR.index(name) if name in INDEX.names else -1)
    lsh_hits = {}
    for i in cand:
        d = jacc_dist(mine, INDEX.sets[i])
        if d <= THRESHOLD and len_ratio(name, POPULAR[i]) <= MAX_LEN_RATIO:
            lsh_hits[i] = d
    lsh_ms = (time.perf_counter() - t) * 1000
    missed = sorted(brute_hits - set(lsh_hits))

    top = []
    for d, i in scored[:5]:
        ps = INDEX.sets[i]
        top.append({"name": POPULAR[i], "distance": round(d, 4), "similarity": round(1 - d, 4),
                    "len_ratio": round(len_ratio(name, POPULAR[i]), 2),
                    "flag": d <= THRESHOLD and len_ratio(name, POPULAR[i]) <= MAX_LEN_RATIO,
                    "shared": sorted(mine & ps), "only_typed": sorted(mine - ps), "only_popular": sorted(ps - mine),
                    "found_by_lsh": i in lsh_hits})
    return jsonify(name=name, shingles=sorted(mine), n_popular=len(POPULAR), top=top,
                   exact_in_popular=name in INDEX.names,
                   brute={"comparisons": len(scored), "ms": round(brute_ms, 1), "pairs_within_threshold": len(brute_hits)},
                   lsh={"tables": tables, "signature": [int(x) for x in sig[:tables]], "candidates": len(cand),
                        "reduction_pct": round(100 * (1 - len(cand) / max(1, len(scored))), 1), "ms": round(lsh_ms, 1),
                        "pairs_within_threshold": len(lsh_hits),
                        "missed": [POPULAR[i] for i in missed[:10]], "missed_count": len(missed),
                        "recall_pct": round(100 * (1 - len(missed) / len(brute_hits)), 1) if brute_hits else 100.0},
                   threshold=THRESHOLD, max_len_ratio=MAX_LEN_RATIO)


# ----------------------------------------------------------------------------------------------
# background jobs (Spark run, benchmark, GH Archive scan, validation script)
# ----------------------------------------------------------------------------------------------
JOBS = {}


def new_job():
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"status": "running", "log": [], "result": None, "started": time.time()}
    return jid


def log(jid, msg):
    JOBS[jid]["log"].append(msg)


def finish(jid, result=None, error=None):
    JOBS[jid]["result"] = result
    JOBS[jid]["status"] = "error" if error else "done"
    if error:
        JOBS[jid]["log"].append("ERROR: " + error)
    JOBS[jid]["seconds"] = round(time.time() - JOBS[jid]["started"], 1)


@app.get("/api/job/<jid>")
def api_job(jid):
    j = JOBS.get(jid)
    if not j:
        return jsonify(status="error", log=["unknown job"], result=None)
    return jsonify(status=j["status"], log=j["log"][-60:], result=j["result"],
                   seconds=j.get("seconds", round(time.time() - j["started"], 1)))


def run_bg(fn, *a):
    jid = new_job()

    def wrap():
        try:
            fn(jid, *a)
        except Exception as e:  # never let a job die silently
            finish(jid, error=f"{type(e).__name__}: {e}")
    threading.Thread(target=wrap, daemon=True).start()
    return jid


# ---- real Spark job -------------------------------------------------------------------------
def spark_task(jid, names, tables):
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))
    cands = sorted({n.lower() for n in list(ev[ev.ecosystem == "pypi"]["candidate_name"]) + names})
    tmp = tempfile.mkdtemp()
    inp, outp = os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
    json.dump({"candidates": cands, "popular": POPULAR, "tables": tables, "threshold": THRESHOLD}, open(inp, "w"))
    log(jid, f"Launching Spark job ({len(cands)} names vs {len(POPULAR)} popular names)...")
    p = subprocess.Popen([sys.executable, os.path.join(APP, "spark_job.py"), inp, outp],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        line = line.rstrip()
        if line and ("WARN" not in line) and ("log4j" not in line.lower()):
            log(jid, line)
    p.wait()
    if os.path.exists(outp):
        res = json.load(open(outp))
        if res.get("ok"):
            finish(jid, res)
        else:
            finish(jid, error=res.get("error", "Spark job failed"))
    else:
        finish(jid, error="Spark job produced no result (is Java installed? run: java -version)")


@app.post("/api/spark")
def api_spark():
    b = request.get_json(force=True)
    name = (b.get("name") or "").strip().lower()
    return jsonify(job=run_bg(spark_task, [name] if len(name) >= 2 else [], int(b.get("tables", 5))))


# ---- scale benchmark ------------------------------------------------------------------------
def bench_task(jid, nq):
    rnd = random.Random(1)
    queries = []
    for n in rnd.sample(POPULAR, nq):          # typo-style queries: drop one character
        k = rnd.randrange(len(n))
        q = n[:k] + n[k + 1:]
        if len(q) >= 2:
            queries.append(q)
    rows = []
    for size in [1000, 3000, 8000, len(POPULAR)]:
        size = min(size, len(POPULAR))
        sets = INDEX.sets[:size]
        log(jid, f"Reference set of {size:,} names, {len(queries)} queries...")
        t = time.perf_counter()
        for q in queries:
            mine = shingles(q)
            for s in sets:
                jacc_dist(mine, s)
        brute = time.perf_counter() - t
        t = time.perf_counter()
        sub = Index.__new__(Index)
        sub.names, sub.sets, sub.sigs = INDEX.names[:size], sets, INDEX.sigs[:size]
        tabs = sub._tables(size)
        build = time.perf_counter() - t
        t = time.perf_counter()
        verified = 0
        for q in queries:
            mine = shingles(q)
            c = sub.candidates(minhash(mine), 3, tabs)
            verified += len(c)
            for i in c:
                jacc_dist(mine, sets[i])
        lsh = time.perf_counter() - t
        rows.append({"size": size, "queries": len(queries), "brute_comparisons": len(queries) * size,
                     "brute_s": round(brute, 3), "lsh_build_s": round(build, 3), "lsh_query_s": round(lsh, 3),
                     "lsh_comparisons": verified})
        log(jid, f"  brute force {brute:.2f}s  vs  LSH {lsh:.2f}s (+{build:.2f}s to build once); "
                 f"exact comparisons {len(queries) * size:,} -> {verified:,}")
    per_pair = rows[-1]["brute_s"] / rows[-1]["brute_comparisons"]
    full_pairs = 884_779 * 15_000
    finish(jid, {"rows": rows, "per_comparison_us": round(per_pair * 1e6, 2), "full_pairs": full_pairs,
                 "full_hours_single_core": round(per_pair * full_pairs / 3600, 1)})


@app.post("/api/benchmark")
def api_benchmark():
    return jsonify(job=run_bg(bench_task, 100))


# ---- GH Archive scan (one hour, live) -------------------------------------------------------
def archive_task(jid, hour, extra):
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))
    names = {n.lower() for n in ev["candidate_name"]} | {e.lower() for e in extra}
    url = f"https://data.gharchive.org/{hour}.json.gz"
    log(jid, f"Downloading {url}")
    log(jid, f"Looking for pushes to repos named like any of {len(names)} candidate names")
    r = requests.get(url, stream=True, timeout=60, headers={"User-Agent": "typosquat-student-project"})
    if r.status_code != 200:
        finish(jid, error=f"GH Archive answered HTTP {r.status_code} for hour {hour} (check the date/hour format YYYY-MM-DD-H).")
        return
    t = time.time()
    events = pushes = 0
    hits = {}
    for line in gzip.GzipFile(fileobj=r.raw):
        events += 1
        if b'"PushEvent"' not in line[:160]:
            continue
        pushes += 1
        try:
            e = json.loads(line)
            repo = e["repo"]["name"]
        except Exception:
            continue
        short = repo.split("/")[-1].lower()
        if short in names:
            h = hits.setdefault(repo, {"short": short, "repo": repo, "pushes": 0, "pushers": set()})
            h["pushes"] += 1
            h["pushers"].add(e.get("actor", {}).get("login", "?"))
        if events % 20000 == 0:
            log(jid, f"  {events:,} events read, {pushes:,} pushes, {len(hits)} matching repos so far")
    rows = sorted([{"short": h["short"], "repo": h["repo"], "pushes": h["pushes"], "pushers": len(h["pushers"])}
                   for h in hits.values()], key=lambda x: -x["pushes"])
    finish(jid, {"hour": hour, "events": events, "pushes": pushes, "seconds": round(time.time() - t, 1),
                 "matched_repos": len(rows), "rows": rows[:40], "candidates": len(names)})


@app.post("/api/archive")
def api_archive():
    b = request.get_json(force=True)
    hour = (b.get("hour") or "2026-08-27-12").strip()
    extra = [x.strip() for x in (b.get("extra") or "").split(",") if x.strip()]
    return jsonify(job=run_bg(archive_task, hour, extra))


# ---- validation script (clones the OpenSSF list; needs git + internet) -----------------------
def validation_task(jid):
    log(jid, "Running scoring/validate_openssf.py (clones the OpenSSF malicious-packages list, a few seconds)...")
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "scoring", "validate_openssf.py")], cwd=ROOT,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        if line.strip():
            log(jid, line.rstrip())
    p.wait()
    if p.returncode == 0:
        sm = os.path.join(DATA, "validation_summary.md")
        finish(jid, {"summary": open(sm, encoding="utf-8").read() if os.path.exists(sm) else ""})
    else:
        finish(jid, error="validate_openssf.py exited with code " + str(p.returncode))


@app.post("/api/validation_run")
def api_validation_run():
    return jsonify(job=run_bg(validation_task))


# ----------------------------------------------------------------------------------------------
# Signal 2, Signal 3, scoring, validation, environment
# ----------------------------------------------------------------------------------------------
def load_blast():
    p = os.path.join(DATA, "blast_radius.csv")
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=["ecosystem", "popular_name", "dependents"])


@app.get("/api/signal2")
def api_signal2():
    name, eco = request.args.get("name", "").strip().lower(), request.args.get("eco", "pypi")
    if not name:
        return jsonify(error="Type a package name.")
    b = load_blast()
    cached = b[(b.ecosystem == eco) & (b.popular_name == name)]
    cached_val = int(cached.iloc[0].dependents) if len(cached) and pd.notna(cached.iloc[0].dependents) else None
    t = time.time()
    val, err = brf.from_ecosystems(eco, name)
    src = "ecosyste.ms"
    if val is None:
        val2, err2 = brf.from_depsdev(eco, name)
        if val2 is not None:
            val, src = val2, "deps.dev"
        else:
            src = ""
            err = f"ecosyste.ms: {err}; deps.dev: {err2}"
    return jsonify(name=name, eco=eco, live=val, source=src, error=None if val is not None else err,
                   seconds=round(time.time() - t, 1), cached=cached_val)


def evidence_df():
    return pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))


@app.post("/api/signal3")
def api_signal3():
    b = request.get_json(force=True)
    name, eco = (b.get("name") or "").strip().lower(), b.get("eco", "pypi")
    token = (b.get("token") or os.environ.get("GITHUB_TOKEN", "")).strip()
    fname = "requirements.txt" if eco == "pypi" else "package.json"
    ev = evidence_df()
    sv = ev[(ev.ecosystem == eco) & (ev.candidate_name.str.lower() == name)]
    saved = None
    if len(sv):
        r = sv.iloc[0]
        saved = {"hits": None if pd.isna(r.github_hit_count) else int(r.github_hit_count),
                 "example_repo": None if pd.isna(r.example_repo) else r.example_repo}
    out = {"name": name, "eco": eco, "file": fname, "query": f'"{name}" in:file filename:{fname}', "saved": saved,
           "live": None, "error": None, "noise_limit": scoremod.NOISE_HITS}
    if not token:
        out["error"] = "No GitHub token entered, so no live search. (GitHub Code Search requires a token.)"
        return jsonify(out)
    r = requests.get("https://api.github.com/search/code", headers={"Authorization": f"token {token}"},
                     params={"q": out["query"]}, timeout=30)
    if r.status_code == 200:
        js = r.json()
        out["live"] = {"hits": js.get("total_count", 0),
                       "example_repo": js["items"][0]["repository"]["full_name"] if js.get("items") else None}
    else:
        out["error"] = f"GitHub answered HTTP {r.status_code}: {r.text[:150]}"
    return jsonify(out)


def signal_values(dist, deps, hits, top):
    s1 = None if dist is None else 1 - dist
    s2 = None if deps is None or not top else math.log1p(deps) / math.log1p(top)
    s3 = None if hits is None or hits > scoremod.NOISE_HITS else math.log1p(hits) / math.log1p(scoremod.NOISE_HITS)
    return s1, s2, s3


def blend(s, w):
    vals = [("s1", s[0]), ("s2", s[1]), ("s3", s[2])]
    used = [(k, v) for k, v in vals if v is not None]
    if len(used) < 2:
        return None, len(used)
    den = sum(w[k] for k, _ in used)
    return sum(w[k] * v for k, v in used) / den, len(used)


def tier(score):
    if score is None:
        return "UNSCORED (fewer than 2 usable signals)"
    return "HIGH" if score >= scoremod.HIGH else "MEDIUM" if score >= scoremod.MEDIUM else "LOW"


def top_dependents():
    fs = pd.read_csv(os.path.join(DATA, "final_scores.csv"))
    return float(fs["popular_dependents"].max())


@app.post("/api/score")
def api_score():
    b = request.get_json(force=True)
    w = {**scoremod.WEIGHTS, **(b.get("weights") or {})}
    s = signal_values(b.get("distance"), b.get("dependents"), b.get("hits"), top_dependents())
    sc, used = blend(s, w)
    return jsonify(s1=s[0], s2=s[1], s3=s[2], score=sc, signals_used=used, tier=tier(sc), weights=w,
                   top_dependents=top_dependents())


def auc(y, x):
    pos, neg = x[y], x[~y]
    if not len(pos) or not len(neg):
        return None
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


@app.get("/api/ranking")
def api_ranking():
    w = {"s1": float(request.args.get("w1", .25)), "s2": float(request.args.get("w2", .30)),
         "s3": float(request.args.get("w3", .45))}
    fs = pd.read_csv(os.path.join(DATA, "final_scores.csv"))
    df = fs.drop(columns=["score", "rank", "tier", "signals_used"])
    sc, used = scoremod.combine(df, w)
    df["score"], df["signals_used"] = sc, used
    df.loc[df["signals_used"] < 2, "score"] = np.nan
    df = df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    df["rank"] = df.index + 1
    df["tier"] = [tier(None if pd.isna(s) else s) for s in df["score"]]
    y = df["candidate_listed_malicious"].fillna(False).astype(bool)
    aucs = {}
    for scope, mask in [("all", pd.Series(True, index=df.index)), ("npm only", df["ecosystem"] == "npm")]:
        for col in ["s1", "s2", "s3", "score"]:
            ok = df[col].notna() & mask
            aucs[f"{col} | {scope}"] = auc(y[ok].to_numpy(), df.loc[ok, col].to_numpy())
    rows = [{"rank": int(r["rank"]), "eco": r.ecosystem, "popular": r.popular_name, "candidate": r.candidate_name,
             "score": None if pd.isna(r.score) else round(float(r.score), 4), "tier": r.tier,
             "s1": None if pd.isna(r.s1) else round(float(r.s1), 3), "s2": None if pd.isna(r.s2) else round(float(r.s2), 3),
             "s3": None if pd.isna(r.s3) else round(float(r.s3), 3),
             "deps": None if pd.isna(r.popular_dependents) else int(r.popular_dependents),
             "hits": None if pd.isna(r.github_hit_count) else int(r.github_hit_count), "mal": bool(y[i])}
            for i, r in df.iterrows()]
    return jsonify(weights=w, rows=rows, aucs=aucs, known_ranks=[r["rank"] for r in rows if r["mal"]],
                   n_scored=int(df["score"].notna().sum()))


_MAL = None


def mal_set():
    global _MAL
    if _MAL is None:
        p = os.path.join(DATA, "openssf_malicious_pypi_names.txt")
        _MAL = {ln.strip().lower().replace("_", "-").replace(".", "-") for ln in open(p, encoding="utf-8") if ln.strip()} if os.path.exists(p) else set()
    return _MAL


@app.get("/api/ground_truth")
def api_ground_truth():
    name, eco = request.args.get("name", "").strip().lower(), request.args.get("eco", "pypi")
    if eco == "pypi":
        return jsonify(name=name, eco=eco, listed=name.replace("_", "-").replace(".", "-") in mal_set(), checked=len(mal_set()))
    vo = pd.read_csv(os.path.join(DATA, "validation_overlap.csv"))
    hit = vo[(vo.ecosystem == "npm") & (vo.candidate_name.str.lower() == name) & (vo.candidate_listed_malicious == True)]  # noqa: E712
    return jsonify(name=name, eco=eco, listed=bool(len(hit)),
                   checked="only the npm names in our 150-candidate shortlist (full npm list not stored in this app)")


@app.get("/api/validation_data")
def api_validation_data():
    out = {}
    for key, f in [("recall", "validation_signal1_recall.csv"), ("score_validation", "score_validation.csv")]:
        p = os.path.join(DATA, f)
        out[key] = pd.read_csv(p).to_dict("records") if os.path.exists(p) else []
    sm = os.path.join(DATA, "validation_summary.md")
    out["summary"] = open(sm, encoding="utf-8").read() if os.path.exists(sm) else ""
    return jsonify(out)


def probe(url):
    try:
        r = requests.get(url, timeout=6, headers={"User-Agent": "typosquat-student-project"}, stream=True)
        r.close()
        return r.status_code < 500
    except Exception:
        return False


@app.get("/api/env")
def api_env():
    urls = {"ecosyste.ms (Signal 2)": "https://packages.ecosyste.ms/api/v1/registries/pypi.org/packages/requests",
            "GitHub API (Signal 3)": "https://api.github.com/rate_limit",
            "GH Archive (Signal 3 scan)": "https://data.gharchive.org/"}
    with ThreadPoolExecutor(3) as ex:
        net = dict(zip(urls, ex.map(probe, urls.values())))
    java = shutil.which("java")
    spark = importlib.util.find_spec("pyspark") is not None
    files = {f: os.path.exists(os.path.join(DATA, f)) for f in
             ["pypi_popular_names.txt", "signal3_evidence_results.csv", "blast_radius.csv", "final_scores.csv",
              "validation_overlap.csv", "openssf_malicious_pypi_names.txt"]}
    return jsonify(python=sys.version.split()[0], popular=len(POPULAR), java=bool(java), pyspark=spark, net=net,
                   token=bool(os.environ.get("GITHUB_TOKEN")), files=files)


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\nOpen http://127.0.0.1:{port} in your browser (Ctrl+C here to stop)\n")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
