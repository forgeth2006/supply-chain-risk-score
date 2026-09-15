"""
Week 3 — Reusable dependency-fetch module.

This module fetches direct runtime dependencies from:
    - PyPI
    - npm

Features:
    - local caching
    - graceful handling of missing packages
    - basic rate-limit retry/backoff
    - common interface for both ecosystems

This module is imported by other scripts.
It is not meant to be run directly.

Week 5 will reuse fetch_dependencies() with
Person A's real Signal 1 candidate list.
"""

import json
import os
import re
import time

import requests


# ---------------------------------------------------------
# Cache configuration
# ---------------------------------------------------------

CACHE_DIR = "dep_cache"
os.makedirs(CACHE_DIR, exist_ok=True)


# ---------------------------------------------------------
# Custom exception
# ---------------------------------------------------------

class PackageNotFoundError(Exception):
    """Raised when a package does not exist in the registry."""
    pass


# ---------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------

def _cache_path(ecosystem, name):
    """
    Return the cache file path for a package.

    Example:
        pypi + requests
        -> dep_cache/pypi_requests.json
    """

    safe_name = re.sub(
        r"[^A-Za-z0-9_.\-]",
        "_",
        name
    )

    return os.path.join(
        CACHE_DIR,
        f"{ecosystem}_{safe_name}.json"
    )


def _load_cache(ecosystem, name):
    """Load cached dependency data if it exists."""

    path = _cache_path(ecosystem, name)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    return None


def _save_cache(ecosystem, name, data):
    """Save dependency data locally."""

    path = _cache_path(ecosystem, name)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2
        )


# ---------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------

def _request_with_backoff(url, max_retries=3):
    """
    Send a GET request with basic retry handling.

    200 -> return response
    404 -> package not found
    429 -> wait and retry
    other errors -> raise exception
    """

    for attempt in range(max_retries):

        response = requests.get(
            url,
            timeout=10
        )

        if response.status_code == 200:
            return response

        if response.status_code == 404:
            raise PackageNotFoundError(url)

        if response.status_code == 429:
            wait = 2 ** attempt

            print(
                f"  Rate limited. "
                f"Waiting {wait}s before retry..."
            )

            time.sleep(wait)
            continue

        response.raise_for_status()

    raise RuntimeError(
        f"Request failed after {max_retries} retries: {url}"
    )


# ---------------------------------------------------------
# PyPI
# ---------------------------------------------------------

def fetch_pypi_dependencies(package_name, use_cache=True):
    """
    Fetch direct dependencies of a PyPI package.

    Returns:
        {
            "found": True/False,
            "dependencies": [...]
        }
    """

    if use_cache:

        cached = _load_cache(
            "pypi",
            package_name
        )

        if cached is not None:
            return cached

    url = (
        f"https://pypi.org/pypi/"
        f"{package_name}/json"
    )

    try:

        response = _request_with_backoff(url)

    except PackageNotFoundError:

        result = {
            "found": False,
            "dependencies": []
        }

        _save_cache(
            "pypi",
            package_name,
            result
        )

        return result

    data = response.json()

    requires_dist = (
        data
        .get("info", {})
        .get("requires_dist")
        or []
    )

    cleaned = []

    for entry in requires_dist:

        # Remove environment markers.
        #
        # Example:
        # PySocks!=1.5.7,>=1.5.6; extra == "socks"
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
            cleaned.append(
                match.group(0).lower()
            )

    result = {
        "found": True,
        "dependencies": sorted(
            set(cleaned)
        )
    }

    _save_cache(
        "pypi",
        package_name,
        result
    )

    return result


# ---------------------------------------------------------
# npm
# ---------------------------------------------------------

def fetch_npm_dependencies(package_name, use_cache=True):
    """
    Fetch direct runtime dependencies of an npm package.

    The npm registry contains metadata for many versions.

    This function:
        1. finds the latest version
        2. reads its regular dependencies field
        3. returns the dependency names

    Peer and optional dependencies are not included yet.
    Those decisions can be revisited when building the
    Week 5/6 graph logic.
    """

    if use_cache:

        cached = _load_cache(
            "npm",
            package_name
        )

        if cached is not None:
            return cached

    url = (
        f"https://registry.npmjs.org/"
        f"{package_name}"
    )

    try:

        response = _request_with_backoff(url)

    except PackageNotFoundError:

        result = {
            "found": False,
            "dependencies": []
        }

        _save_cache(
            "npm",
            package_name,
            result
        )

        return result

    data = response.json()

    latest_version = (
        data
        .get("dist-tags", {})
        .get("latest")
    )

    if not latest_version:

        raise ValueError(
            f"Could not determine latest "
            f"version for {package_name}"
        )

    version_data = (
        data
        .get("versions", {})
        .get(latest_version, {})
    )

    dependencies = (
        version_data
        .get("dependencies", {})
        or {}
    )

    result = {
        "found": True,
        "dependencies": sorted(
            dependencies.keys()
        )
    }

    _save_cache(
        "npm",
        package_name,
        result
    )

    return result


# ---------------------------------------------------------
# Common entry point
# ---------------------------------------------------------

def fetch_dependencies(
    ecosystem,
    package_name,
    use_cache=True
):
    """
    Common interface for dependency fetching.

    Example:

        fetch_dependencies(
            "pypi",
            "requests"
        )

        fetch_dependencies(
            "npm",
            "express"
        )
    """

    ecosystem = ecosystem.lower()

    if ecosystem == "pypi":

        return fetch_pypi_dependencies(
            package_name,
            use_cache
        )

    if ecosystem == "npm":

        return fetch_npm_dependencies(
            package_name,
            use_cache
        )

    raise ValueError(
        f"Unknown ecosystem: {ecosystem}"
    )