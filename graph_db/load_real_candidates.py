"""
Week 5 — Load real Signal 1 candidates into Neo4j.

Reads Person A's Signal 1 Parquet output and converts it into
the candidate format expected by graph_loader.py.

Expected internal format:

    (ecosystem, popular_name, candidate_name)

The actual Parquet column names must be confirmed from
Person A's output before real loading.

Run from the repository root or graph_db directory:

    python graph_db/load_real_candidates.py

Required packages:

    pip install pandas pyarrow
"""

from pathlib import Path

import pandas as pd

from graph_loader import load_graph


# Repository root is one level above graph_db/
REPO_ROOT = Path(__file__).resolve().parent.parent

PYPI_MATCHES_PATH = (
    REPO_ROOT
    / "registry_lsh"
    / "pypi_lsh_matches.parquet"
)

NPM_MATCHES_PATH = (
    REPO_ROOT
    / "registry_lsh"
    / "npm_lsh_matches.parquet"
)


def load_real_candidates():
    """
    Read Person A's Signal 1 output and convert it into:

        (ecosystem, popular_name, candidate_name)

    The expected column names are currently:

        popular_name
        candidate_name

    These must be confirmed against Person A's actual
    Parquet output before real loading.
    """

    all_candidates = []

    try:
        pypi_df = pd.read_parquet(PYPI_MATCHES_PATH)

        pypi_df["ecosystem"] = "pypi"

        all_candidates.extend(
            pypi_df[
                [
                    "ecosystem",
                    "popular_name",
                    "candidate_name"
                ]
            ].itertuples(
                index=False,
                name=None
            )
        )

        print(
            f"✅ Loaded {len(pypi_df)} "
            f"PyPI candidate pairs"
        )

    except FileNotFoundError:
        print(
            f"⚠️ {PYPI_MATCHES_PATH} not found."
        )

    except KeyError as error:
        print(
            f"⚠️ Expected column missing in "
            f"PyPI parquet: {error}"
        )

    try:
        npm_df = pd.read_parquet(NPM_MATCHES_PATH)

        npm_df["ecosystem"] = "npm"

        all_candidates.extend(
            npm_df[
                [
                    "ecosystem",
                    "popular_name",
                    "candidate_name"
                ]
            ].itertuples(
                index=False,
                name=None
            )
        )

        print(
            f"✅ Loaded {len(npm_df)} "
            f"npm candidate pairs"
        )

    except FileNotFoundError:
        print(
            f"⚠️ {NPM_MATCHES_PATH} not found."
        )

    except KeyError as error:
        print(
            f"⚠️ Expected column missing in "
            f"npm parquet: {error}"
        )

    # Remove duplicate candidate pairs while
    # preserving their original order.
    return list(dict.fromkeys(all_candidates))


def inspect_raw_columns():
    """
    Inspect Person A's actual Parquet files.

    This is useful before changing the expected
    column names in load_real_candidates().
    """

    files = [
        (PYPI_MATCHES_PATH, "PyPI"),
        (NPM_MATCHES_PATH, "npm")
    ]

    for path, label in files:

        try:
            df = pd.read_parquet(path)

            print(f"\n{label} columns:")
            print(list(df.columns))

            print(f"\n{label} sample:")
            print(df.head(3))

        except FileNotFoundError:
            print(
                f"\n{label}: file not found at:"
            )
            print(path)


if __name__ == "__main__":

    print("=" * 60)
    print("WEEK 5 — REAL CANDIDATE LOADER")
    print("=" * 60)

    print("\nChecking Person A's output format...")
    inspect_raw_columns()

    print("\nLoading real candidates...")
    candidates = load_real_candidates()

    if not candidates:

        print(
            "\n⚠️ No real candidates loaded."
        )

        print(
            "Person A's Signal 1 Parquet files "
            "are not currently available."
        )

        print(
            "The loader is ready for the "
            "real handoff."
        )

    else:

        print(
            f"\nLoading graph for "
            f"{len(candidates)} candidate pairs..."
        )

        stats = load_graph(candidates)

        print("\nGRAPH LOAD SUMMARY")
        print("-" * 60)

        for key, value in stats.items():
            print(f"{key}: {value}")

        print(
            "\n✅ Real candidate graph load complete."
        )