"""
Week 2 — Validate dependency data sources.

This script checks whether we can retrieve dependency information
from PyPI and npm for a small set of packages.

It does NOT populate Neo4j.

Test sources:
    PyPI JSON API
    npm Registry API

Run:
    python week2_fetch_dependencies.py
"""

import re
import requests


# Small test set covering different types of packages.
PYPI_TEST_PACKAGES = [
    "requests",
    "flask",
    "numpy"
]

NPM_TEST_PACKAGES = [
    "express",
    "lodash",
    "react"
]


def fetch_pypi_dependencies(package_name):
    """
    Fetch dependency information from the PyPI JSON API.

    Example raw dependency:
        charset-normalizer<4,>=2

    After cleaning:
        charset-normalizer
    """

    url = f"https://pypi.org/pypi/{package_name}/json"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    requires_dist = data.get("info", {}).get("requires_dist") or []

    cleaned = []

    for entry in requires_dist:

        # Remove environment markers.
        # Example:
        # PySocks!=1.5.7,>=1.5.6; extra == 'socks'
        #
        # becomes:
        # PySocks!=1.5.7,>=1.5.6
        name_part = entry.split(";")[0]

        # Extract only the package name.
        match = re.match(
            r"^[A-Za-z0-9_.\-]+",
            name_part.strip()
        )

        if match:
            cleaned.append(match.group(0).lower())

    return {
        "raw_sample": requires_dist[:5],
        "cleaned_names": sorted(set(cleaned)),
        "raw_count": len(requires_dist)
    }


def fetch_npm_dependencies(package_name):
    """
    Fetch dependency information from the npm Registry API.

    The npm registry provides metadata for different versions.
    We first find the version marked as 'latest' and then read
    its regular 'dependencies' field.
    """

    url = f"https://registry.npmjs.org/{package_name}"

    response = requests.get(url, timeout=10)
    response.raise_for_status()

    data = response.json()

    # Find the version currently marked as "latest".
    latest_version = data.get("dist-tags", {}).get("latest")

    if not latest_version:
        raise ValueError(
            f"Could not determine latest version for {package_name}"
        )

    version_data = data.get("versions", {}).get(latest_version, {})

    if not version_data:
        raise ValueError(
            f"Could not find metadata for version "
            f"{latest_version} of {package_name}"
        )

    dependencies = version_data.get("dependencies", {}) or {}

    return {
        "latest_version": latest_version,
        "raw_sample": dict(list(dependencies.items())[:5]),
        "cleaned_names": sorted(dependencies.keys()),
        "raw_count": len(dependencies)
    }


def main():

    print("=" * 60)
    print("WEEK 2 — DEPENDENCY DATA SOURCE VALIDATION")
    print("=" * 60)

    # ---------------------------------------------------------
    # PyPI
    # ---------------------------------------------------------

    print("\nPYPI")
    print("-" * 60)

    for package in PYPI_TEST_PACKAGES:

        try:
            result = fetch_pypi_dependencies(package)

            print(f"\nPackage: {package}")
            print(f"Raw dependency count: {result['raw_count']}")
            print(
                f"Cleaned dependency count: "
                f"{len(result['cleaned_names'])}"
            )
            print(f"Raw sample: {result['raw_sample']}")
            print(
                f"Cleaned sample: "
                f"{result['cleaned_names'][:8]}"
            )

        except Exception as error:

            print(f"\nPackage: {package}")
            print(f"FAILED: {error}")

    # ---------------------------------------------------------
    # npm
    # ---------------------------------------------------------

    print("\n\nNPM")
    print("-" * 60)

    for package in NPM_TEST_PACKAGES:

        try:
            result = fetch_npm_dependencies(package)

            print(f"\nPackage: {package}")
            print(f"Latest version: {result['latest_version']}")
            print(f"Dependency count: {result['raw_count']}")
            print(f"Raw sample: {result['raw_sample']}")
            print(
                f"Dependency sample: "
                f"{result['cleaned_names'][:8]}"
            )

        except Exception as error:

            print(f"\nPackage: {package}")
            print(f"FAILED: {error}")

    # ---------------------------------------------------------
    # End
    # ---------------------------------------------------------

    print("\n" + "=" * 60)
    print("Dependency source validation completed.")
    print("No data was inserted into Neo4j.")
    print("=" * 60)


if __name__ == "__main__":
    main()