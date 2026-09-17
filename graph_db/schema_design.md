# Graph Schema Design — Week 5

## Node type: `Package`
| Property     | Type    | Notes |
|---|---|---|
| `ecosystem`  | string  | "pypi" or "npm" |
| `name`       | string  | exact published name |
| `is_popular` | bool    | true if this is one of Signal 1's popular/target packages |

Uniqueness enforced on `(ecosystem, name)` — see `schema_setup.cypher` from Week 1.

## Edge types
| Edge | Direction | Populated | Status |
|---|---|---|---|
| `DEPENDS_ON` | Package → Package | Week 5 (this week) | ✅ real data |
| `IMPERSONATES` | Package → Package | Week 6/7 | placeholder — from Signal 1 |
| `INSTALLED_BY` | Package → Repo | Week 7 | placeholder — from Signal 3 |

## Scoping decision (per the 8-week plan's guiding principle)

We do **not** build a graph of the entire PyPI/npm dependency universe.
We only load:
1. Every `popular_name` that appears in Person A's Signal 1 candidate list
   (`pypi_lsh_matches.parquet` / `npm_lsh_matches.parquet`)
2. Each of those popular packages' real, direct dependencies (one level —
   who *it* depends on, needed for blast-radius-of-the-impersonation-target
   reasoning at Week 6)
3. The candidate (typosquat) packages themselves, as bare nodes for now —
   they get their `IMPERSONATES` edge at Week 6/7, not here

This keeps the graph small (bounded by Signal 1's candidate count, not
millions of packages) while preserving the actual graph-traversal /
blast-radius concept intact.

## Known risk
If Person A's parquet column names don't match what `week5_load_real_candidates.py`
expects (`popular_name`, `candidate_name`), run `inspect_raw_columns()` in that
script first and adjust the column list — don't guess.