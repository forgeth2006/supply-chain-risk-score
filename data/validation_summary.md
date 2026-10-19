# Validation against OpenSSF malicious-packages

Generated 2026-10-19 by `scoring/validate_openssf.py`. Dataset commit `c075548a` (2026-10-19); 11,825 PyPI and 222,214 npm package names reported malicious.

## 1. Overlap with our shortlisted candidates

**6 of 144 distinct candidate names are listed as malicious** (7 of 150 shortlist rows; one candidate can sit under two popular names).

- npm: 6 of 70
- pypi: 0 of 74

| popular package | candidate listed as malicious | ecosystem | GitHub hit count |
|---|---|---|---|
| electron | 3lectron | npm | 1 |
| electron | 3electron | npm | 3 |
| electron | 4electron | npm | 21 |
| electron | 4lectron | npm | 0 |
| readable-stream | 4meme-readable-stream | npm | 0 |
| args | 9args | npm | 1 |

Note: these *popular* names are themselves in the dataset (the dataset can list a name for a past compromise of a real package, so a listing alone does not make a lookalike malicious): color.

## 2. How many known-malicious PyPI names would name similarity alone flag?

| distance cut-off | malicious flagged | flag rate (malicious) | flag rate (popular packages, benign proxy) |
|---|---|---|---|
| 0.30 | 931 of 11,817 | 7.9% | 16.8% |
| 0.40 | 1,519 of 11,817 | 12.8% | 31.8% |
| 0.50 | 2,716 of 11,817 | 23.0% | 54.3% |
| 0.65 | 6,198 of 11,817 | 52.4% | 85.8% |

## Limits

- Absence from the dataset does not mean a package is safe; presence means it was reported.
- Most malicious packages are not typosquats, so a name-similarity signal is expected to miss many.
- The benign comparison uses the 15,000 popular packages, not the full registry, so it is only a rough guide to false-positive pressure.
- The dataset can include names listed for a past compromise of a legitimate package.
- Only PyPI recall was computed (the popular list for npm was not re-fetched here).
