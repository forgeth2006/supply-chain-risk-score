"""
Week 3 — Smoke test for dependency_fetcher.py.

Tests:
    1. PyPI package fetch
    2. Missing PyPI package
    3. npm package fetch
    4. Missing npm package
    5. Cache consistency

These are only test packages.
They are NOT Person A's Signal 1 candidates.
"""

from dependency_fetcher import fetch_dependencies


TEST_CASES = [

    # Real PyPI package
    (
        "pypi",
        "requests"
    ),

    # Fake PyPI package
    (
        "pypi",
        "this-package-does-not-exist-xyz123"
    ),

    # Real npm package
    (
        "npm",
        "express"
    ),

    # Fake npm package
    (
        "npm",
        "this-package-does-not-exist-xyz123"
    ),
]


if __name__ == "__main__":

    print("=" * 60)
    print("WEEK 3 — DEPENDENCY FETCHER SMOKE TEST")
    print("=" * 60)

    for ecosystem, name in TEST_CASES:

        print(
            f"\nFetching "
            f"{ecosystem}:{name} ..."
        )

        result = fetch_dependencies(
            ecosystem,
            name
        )

        if result["found"]:

            print(
                f"  ✅ Found"
            )

            print(
                f"  Dependency count: "
                f"{len(result['dependencies'])}"
            )

            print(
                f"  Sample: "
                f"{result['dependencies'][:5]}"
            )

        else:

            print(
                "  ⚠️ Not found — "
                "handled gracefully"
            )

        # -------------------------------------------------
        # Cache test
        # -------------------------------------------------

        print(
            "  Re-fetching to confirm cache..."
        )

        result2 = fetch_dependencies(
            ecosystem,
            name
        )

        assert result == result2, (
            "Cache result does not match "
            "original result!"
        )

        print(
            "  ✅ Cache consistent"
        )

    print("\n" + "=" * 60)
    print(
        "✅ All Week 3 smoke tests passed."
    )
    print(
        "Dependency fetcher is ready for "
        "future candidate data."
    )
    print("=" * 60)