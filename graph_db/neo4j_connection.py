"""
Week 1 — Neo4j connection helper.

Works with either:
  - Neo4j Desktop (local instance, default bolt://localhost:7687)
  - AuraDB Free tier (bolt+s://<your-instance>.databases.neo4j.io)

Install driver first:
    pip install neo4j

Usage:
    python neo4j_connection.py
"""
import os
from neo4j import GraphDatabase

# ---- EDIT THESE FOR YOUR INSTANCE ----
URI = "bolt://localhost:7687"        # or "neo4j+s://xxxx.databases.neo4j.io" for AuraDB
USERNAME = "neo4j"
PASSWORD = os.getenv("NEO4J_PASSWORD")# set this to whatever you chose at instance creation
# ---------------------------------------


class Neo4jConnection:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def run_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]


def toy_query_test(conn: Neo4jConnection):
    """
    Creates 2 dummy Package nodes + 1 DEPENDS_ON edge, then queries it back.
    This is just to confirm the instance is alive and the schema shape works.
    Safe to re-run — uses MERGE, not CREATE, so it won't duplicate nodes.
    """
    conn.run_query("""
        MERGE (a:Package {ecosystem: 'pypi', name: 'flask-app-demo'})
        MERGE (b:Package {ecosystem: 'pypi', name: 'flask'})
        MERGE (a)-[:DEPENDS_ON]->(b)
    """)

    result = conn.run_query("""
        MATCH (a:Package)-[:DEPENDS_ON]->(b:Package)
        RETURN a.name AS dependent, b.name AS dependency
    """)

    print("Toy query result (should show flask-app-demo -> flask):")
    for row in result:
        print(f"  {row['dependent']} depends on {row['dependency']}")

    # cleanup so this doesn't pollute your real graph later
    conn.run_query("""
        MATCH (a:Package {name: 'flask-app-demo'})
        DETACH DELETE a
    """)
    print("Cleanup done — toy node removed.")


if __name__ == "__main__":
    conn = Neo4jConnection(URI, USERNAME, PASSWORD)
    try:
        toy_query_test(conn)
        print("\n✅ Neo4j instance is working correctly.")
    except Exception as e:
        print(f"\n❌ Connection or query failed: {e}")
    finally:
        conn.close()