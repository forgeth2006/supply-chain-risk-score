"""
Week 4 — Generic Neo4j graph loader.

This module takes candidate pairs in the form:

    (ecosystem, popular_name, candidate_name)

For each pair it:

    1. Creates the popular package node.
    2. Creates the candidate package node.
    3. Fetches the popular package's direct dependencies.
    4. Creates DEPENDS_ON edges for those dependencies.

Week 4 uses dummy candidates.

At Week 5, the dummy candidate loader will be replaced
with a reader for Person A's real Signal 1 Parquet output.

The rest of the graph-loading logic should remain reusable.
"""

import os

from neo4j import GraphDatabase

from dependency_fetcher import fetch_dependencies


# ---------------------------------------------------------
# Neo4j configuration
# ---------------------------------------------------------

URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = os.getenv("NEO4J_PASSWORD")


if not PASSWORD:
    raise RuntimeError(
        "NEO4J_PASSWORD environment variable is not set. "
        "Run: $env:NEO4J_PASSWORD='your-password'"
    )


DATABASE = "neo4j"


# ---------------------------------------------------------
# Dummy candidate data
# ---------------------------------------------------------

# This represents the structure that Person A's
# Signal 1 output will provide later.
#
# Format:
#     (ecosystem, popular_name, candidate_name)

DUMMY_CANDIDATES = [
    ("pypi", "requests", "reqeusts"),
    ("pypi", "flask", "flsk"),
    ("npm", "express", "expres"),
]


def load_candidates_dummy():
    """
    Return dummy candidate pairs for Week 4 testing.

    Week 5 will replace this function with a reader
    for Person A's real Signal 1 Parquet files.
    """

    return DUMMY_CANDIDATES


# ---------------------------------------------------------
# Graph loading
# ---------------------------------------------------------

def load_graph(candidates):
    """
    Load candidate-related dependency information into Neo4j.

    Parameters
    ----------
    candidates : list
        List of tuples:
            (ecosystem, popular_name, candidate_name)

    Returns
    -------
    dict
        Summary statistics for the load operation.
    """

    driver = GraphDatabase.driver(
        URI,
        auth=(USERNAME, PASSWORD)
    )

    stats = {
        "candidate_pairs": 0,
        "popular_nodes_created_or_found": 0,
        "candidate_nodes_created_or_found": 0,
        "dependency_nodes_created_or_found": 0,
        "depends_on_edges_created_or_found": 0,
        "fetch_failures": 0,
    }

    try:

        # Verify that the Neo4j server is reachable.
        driver.verify_connectivity()

        with driver.session(database=DATABASE) as session:

            for ecosystem, popular_name, candidate_name in candidates:

                stats["candidate_pairs"] += 1

                print(
                    f"\nProcessing "
                    f"{ecosystem}:{popular_name} "
                    f"-> {candidate_name}"
                )

                # -------------------------------------------------
                # Create popular and candidate Package nodes
                # -------------------------------------------------

                session.run(
                    """
                    MERGE (p:Package {
                        ecosystem: $ecosystem,
                        name: $popular_name
                    })
                    ON CREATE SET p.is_popular = true

                    MERGE (c:Package {
                        ecosystem: $ecosystem,
                        name: $candidate_name
                    })
                    ON CREATE SET c.is_popular = false
                    """,
                    ecosystem=ecosystem,
                    popular_name=popular_name,
                    candidate_name=candidate_name,
                )

                stats["popular_nodes_created_or_found"] += 1
                stats["candidate_nodes_created_or_found"] += 1

                # -------------------------------------------------
                # Fetch popular package dependencies
                # -------------------------------------------------

                result = fetch_dependencies(
                    ecosystem,
                    popular_name
                )

                if not result["found"]:

                    print(
                        f"  ⚠️ Could not fetch dependencies "
                        f"for {ecosystem}:{popular_name}"
                    )

                    stats["fetch_failures"] += 1

                    continue

                dependencies = result["dependencies"]

                print(
                    f"  Found {len(dependencies)} "
                    f"direct dependencies"
                )

                # -------------------------------------------------
                # Create dependency nodes and DEPENDS_ON edges
                # -------------------------------------------------

                for dependency_name in dependencies:

                    session.run(
                        """
                        MERGE (dep:Package {
                            ecosystem: $ecosystem,
                            name: $dependency_name
                        })

                        WITH dep

                        MATCH (p:Package {
                            ecosystem: $ecosystem,
                            name: $popular_name
                        })

                        MERGE (p)-[:DEPENDS_ON]->(dep)
                        """,
                        ecosystem=ecosystem,
                        dependency_name=dependency_name,
                        popular_name=popular_name,
                    )

                    stats[
                        "dependency_nodes_created_or_found"
                    ] += 1

                    stats[
                        "depends_on_edges_created_or_found"
                    ] += 1

                print(
                    f"  ✅ Loaded "
                    f"{len(dependencies)} DEPENDS_ON edges"
                )

    finally:

        driver.close()

    return stats


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

if __name__ == "__main__":

    print("=" * 60)
    print("WEEK 4 — NEO4J GRAPH LOADER TEST")
    print("=" * 60)

    candidates = load_candidates_dummy()

    print(
        f"\nDummy candidate pairs: "
        f"{len(candidates)}"
    )

    stats = load_graph(candidates)

    print("\n" + "=" * 60)
    print("GRAPH LOADING SUMMARY")
    print("=" * 60)

    for key, value in stats.items():
        print(f"{key}: {value}")

    print("\n✅ Week 4 graph loader completed.")
    print(
        "Dummy candidates were used. "
        "No Person A Signal 1 files were required."
    )