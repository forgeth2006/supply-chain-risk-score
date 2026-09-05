# Week 2 — Data Acquisition Scope

## Popular package reference lists (Signal 1 target set)
- PyPI: 15,000 packages, sourced from hugovk/top-pypi-packages
  (ClickHouse-based download-count dataset, updated regularly)
- npm: 10,000 packages, sourced from tristan-f-r/npm-rank
  (originally started by LeoDog896; ownership/URL changed since project
  inception — verified current source before use rather than trusting
  an outdated reference)

Both chosen for objectivity/reproducibility (real download/dependency
data) over a manually curated list, and cited directly in this doc
for defensibility.

## Full registry indexes (Signal 1 comparison set — "the entire shelf")
- PyPI: 884,813 package names, from the official pypi.org/simple index
- npm: 4,419,399 package names, from all-the-package-names (via unpkg),
  includes scoped packages

## Data quality note
npm's full name list contains a non-trivial number of apparent
accidental/junk entries (e.g. `--frozen-lockfile`, `--can-you-install`) —
likely CLI flags mistakenly published as packages. PyPI's list did not
show this pattern as visibly. Worth revisiting if these create noise in
Signal 1 matching later — may need a basic name-validity filter
(e.g. minimum length, must not start with `-`) before running MinHash+LSH.

## Technical notes for reproducibility
- PyPI popular list required `multiLine=true` when reading with Spark
  (single JSON document, not JSON Lines) and `explode()` to unpack a
  nested `rows` array.
- npm full list is a flat JSON array of plain strings, not objects —
  Spark's `.json()` reader cannot parse this directly (results in
  `_corrupt_record`); parsed with Python's `json` module instead, then
  converted to a Spark DataFrame manually.