"""
Real Spark run for the live demo (called by app.py as a separate process so a Spark problem
can never crash the web page).

It runs the SAME steps as the project's Signal 1 pipeline, on a small input:
  names -> 2-character shingles (NGram) -> CountVectorizer(binary) -> MinHashLSH -> approxSimilarityJoin
Left side : the names to check (typed name + the 150 shortlisted candidates)
Right side: the 15,000 most-downloaded PyPI packages

Usage: python spark_job.py input.json output.json
"""
import json
import os
import sys
import time

inp, outp = sys.argv[1], sys.argv[2]
cfg = json.load(open(inp, encoding="utf-8"))
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def say(msg):
    print(msg, flush=True)


try:
    from pyspark.sql import SparkSession, functions as F
    from pyspark.ml.feature import NGram, CountVectorizer, MinHashLSH
except Exception as e:  # pyspark missing
    json.dump({"ok": False, "error": f"pyspark could not be imported: {e}. Install with: pip install pyspark (and Java 8/11/17 must be installed)."},
              open(outp, "w"))
    sys.exit(0)

try:
    t_all = time.time()
    say("Starting Spark (local mode, all CPU cores)...")
    spark = (SparkSession.builder.master("local[*]").appName("typosquat-live-demo")
             .config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.driver.memory", "2g")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    say(f"Spark {spark.version} is up in {time.time() - t_all:.1f} s")

    cands = sorted({n.lower() for n in cfg["candidates"] if len(n) >= 2})
    pops = sorted({n.lower() for n in cfg["popular"] if len(n) >= 2})
    say(f"Left side: {len(cands)} names to check.  Right side: {len(pops)} popular names.")
    say(f"Naive comparisons would be {len(cands) * len(pops):,}.")

    def prep(names, col):
        df = spark.createDataFrame([(n,) for n in names], [col])
        df = df.withColumn("chars", F.expr(f"filter(split({col}, ''), c -> c != '')"))
        df = NGram(n=2, inputCol="chars", outputCol="shingles").transform(df)
        return df.filter(F.size("shingles") > 0)

    t = time.time()
    left, right = prep(cands, "candidate_name"), prep(pops, "popular_name")
    say("Step 1: names cut into 2-character shingles (NGram n=2)")

    # IMPORTANT (project finding): fit the vocabulary on BOTH sides, otherwise unknown shingles
    # are silently dropped and distances come out wrong (the '1build' vs 'build' bug).
    both = left.select("shingles").unionByName(right.select("shingles"))
    cv = CountVectorizer(inputCol="shingles", outputCol="features", binary=True).fit(both)
    left_v, right_v = cv.transform(left), cv.transform(right)
    say(f"Step 2: shingles -> binary vectors (vocabulary of {len(cv.vocabulary)} distinct shingles, fitted on BOTH sides)")

    tables = int(cfg.get("tables", 5))
    lsh = MinHashLSH(inputCol="features", outputCol="hashes", numHashTables=tables, seed=7).fit(right_v)
    say(f"Step 3: MinHash signatures built (numHashTables={tables})")

    joined = lsh.approxSimilarityJoin(left_v, right_v, float(cfg.get("threshold", 0.65)), distCol="jaccard_distance")
    res = (joined.select(F.col("datasetA.candidate_name").alias("candidate_name"),
                         F.col("datasetB.popular_name").alias("popular_name"),
                         "jaccard_distance")
           .filter("candidate_name != popular_name"))
    rows = res.orderBy("jaccard_distance").limit(300).collect()
    total = res.count()
    say(f"Step 4: LSH join finished: {total:,} candidate pairs at distance <= {cfg.get('threshold', 0.65)}")

    out = [{"candidate_name": r["candidate_name"], "popular_name": r["popular_name"],
            "jaccard_distance": round(float(r["jaccard_distance"]), 4)} for r in rows]
    json.dump({"ok": True, "spark_version": spark.version, "seconds": round(time.time() - t_all, 1),
               "left": len(cands), "right": len(pops), "naive_pairs": len(cands) * len(pops),
               "pairs_found": total, "tables": tables, "rows": out}, open(outp, "w"))
    spark.stop()
except Exception as e:
    json.dump({"ok": False, "error": f"{type(e).__name__}: {str(e)[:600]}"}, open(outp, "w"))
