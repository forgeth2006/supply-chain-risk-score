"""
Rebuild the Neo4j graph on THIS machine from files that are already in the repository.

What it loads (all from data/):
  - the 150 shortlisted candidates (data/signal3_evidence_results.csv)
  - the dependent counts of the popular packages (data/blast_radius.csv, optional)
  - the real direct dependencies of every popular package, fetched live from PyPI / npm
    (graph_db/dependency_fetcher.py, cached in dep_cache/ so a re-run is fast)

Graph it creates (same schema as graph_db/schema_design.md):
  (:Package {ecosystem, name, is_popular, dependents?})
  (popular)-[:DEPENDS_ON]->(dependency)               what a popular package needs  (forward edges)
  (candidate)-[:IMPERSONATES {distance, github_hits}]->(popular)   Signal 1 + Signal 3

It finishes by writing data/dependency_graph.json (every node and edge), a backup copy of the
graph that does not need Neo4j to read.

Run from the repository root (PowerShell):
    pip install neo4j pandas requests
    $env:NEO4J_PASSWORD = "your-neo4j-password"
    python graph_db/load_shortlist_graph.py

Optional: $env:NEO4J_URI = "bolt://localhost:7687"   (default shown)   $env:NEO4J_DATABASE = "neo4j"
Needs internet (PyPI and npm APIs). About 2 to 5 minutes the first time.
"""
import json
import os
import sys

import pandas as pd
from neo4j import GraphDatabase

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, HERE)

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD")
DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

if not PASSWORD:
    sys.exit('NEO4J_PASSWORD is not set. In PowerShell run:  $env:NEO4J_PASSWORD = "your-password"')

os.chdir(ROOT)                       # dependency_fetcher keeps its cache in ./dep_cache
from dependency_fetcher import fetch_dependencies   # noqa: E402


def num(x):
    return None if pd.isna(x) else int(x)


def main():
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))
    bpath = os.path.join(DATA, "blast_radius.csv")
    blast = pd.read_csv(bpath) if os.path.exists(bpath) else pd.DataFrame(columns=["ecosystem", "popular_name", "dependents"])
    deps_of = {(r.ecosystem, r.popular_name): num(r.dependents) for r in blast.itertuples()}

    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    try:
        driver.verify_connectivity()
    except Exception as e:
        sys.exit(f"Could not connect to Neo4j at {URI}: {e}\n"
                 "Check that the instance shows RUNNING in Neo4j Desktop and that the password is right.")
    print(f"Connected to {URI}, database '{DATABASE}'")

    stats = {"popular": 0, "candidates": 0, "dependency_edges": 0, "impersonates_edges": 0, "fetch_failures": 0}
    with driver.session(database=DATABASE) as s:
        try:
            s.run("CREATE CONSTRAINT package_unique IF NOT EXISTS "
                  "FOR (p:Package) REQUIRE (p.ecosystem, p.name) IS UNIQUE")
        except Exception as e:
            print("  (could not create the uniqueness constraint, continuing:", str(e)[:80], ")")

        populars = ev[["ecosystem", "popular_name"]].drop_duplicates().reset_index(drop=True)
        for i, r in populars.iterrows():
            eco, name = r.ecosystem, r.popular_name
            d = deps_of.get((eco, name))
            s.run("MERGE (p:Package {ecosystem:$eco, name:$name}) SET p.is_popular = true", eco=eco, name=name)
            if d is not None:
                s.run("MATCH (p:Package {ecosystem:$eco, name:$name}) SET p.dependents = $d", eco=eco, name=name, d=d)
            stats["popular"] += 1
            try:
                res = fetch_dependencies(eco, name)
            except Exception as e:
                print(f"  [{i + 1}/{len(populars)}] {eco}:{name}  dependency fetch failed: {str(e)[:70]}")
                stats["fetch_failures"] += 1
                continue
            if not res.get("found"):
                stats["fetch_failures"] += 1
                print(f"  [{i + 1}/{len(populars)}] {eco}:{name}  not found in the registry")
                continue
            for dep in res["dependencies"]:
                s.run("""MATCH (p:Package {ecosystem:$eco, name:$name})
                         MERGE (d:Package {ecosystem:$eco, name:$dep})
                           ON CREATE SET d.is_popular = false
                         MERGE (p)-[:DEPENDS_ON]->(d)""", eco=eco, name=name, dep=dep)
                stats["dependency_edges"] += 1
            print(f"  [{i + 1}/{len(populars)}] {eco}:{name}  {len(res['dependencies'])} dependencies"
                  + (f", {d:,} dependents" if d is not None else ""))

        for r in ev.itertuples():
            s.run("""MATCH (p:Package {ecosystem:$eco, name:$pop})
                     MERGE (c:Package {ecosystem:$eco, name:$cand})
                       ON CREATE SET c.is_popular = false
                     MERGE (c)-[i:IMPERSONATES]->(p)
                     SET i.distance = $dist, i.github_hits = $hits""",
                  eco=r.ecosystem, pop=r.popular_name, cand=r.candidate_name,
                  dist=float(r.jaccard_distance), hits=num(r.github_hit_count))
            stats["candidates"] += 1
            stats["impersonates_edges"] += 1

        nodes = s.run("MATCH (n:Package) RETURN n.ecosystem AS ecosystem, n.name AS name, "
                      "n.is_popular AS is_popular, n.dependents AS dependents").data()
        edges = s.run("MATCH (a:Package)-[r]->(b:Package) RETURN a.ecosystem AS ecosystem, a.name AS source, "
                      "b.name AS target, type(r) AS type, properties(r) AS props").data()
        counts = s.run("MATCH (n:Package) WITH count(n) AS nodes "
                       "MATCH ()-[r]->() RETURN nodes, count(r) AS edges").single()
    driver.close()

    out = os.path.join(DATA, "dependency_graph.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes, "edges": edges}, f)
    print("\nDone.")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  nodes in Neo4j: {counts['nodes']}   edges in Neo4j: {counts['edges']}")
    print(f"  backup written to {out}")
    print("\nTry these in the Neo4j Query tool:")
    print("  MATCH p=(c:Package)-[:IMPERSONATES]->(x:Package {name:'electron'}) RETURN p")
    print("  MATCH p=(x:Package {name:'requests'})-[:DEPENDS_ON]->(d) RETURN p")
    print("  MATCH (x:Package {name:'requests'})<-[:DEPENDS_ON]-(y) RETURN count(y)    (0: forward edges only)")


if __name__ == "__main__":
    main()
