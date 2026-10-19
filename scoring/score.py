"""
Combined risk score: Signal 1 (name similarity) + Signal 2 (blast radius) + Signal 3 (GitHub evidence).

Inputs  (all in data/):
    signal3_evidence_results.csv   150 shortlisted candidates (Signal 1 distance + Signal 3 hit count)
    blast_radius.csv               OPTIONAL. Made by scoring/blast_radius_fetch.py (Signal 2)
    validation_overlap.csv         OPTIONAL. Made by scoring/validate_openssf.py (ground truth flag)
Outputs:
    data/final_scores.csv          ranked list with every signal visible
    data/score_sensitivity.csv     how stable the ranking is when the weights change

Run from the repository root:
    python scoring/score.py

How each signal becomes a number between 0 and 1 (see scoring/scoring_design.md for the reasoning):
    s1 = 1 - Jaccard distance                          (closer name -> higher)
    s2 = log(1 + dependents) / log(1 + largest value)  (bigger blast radius -> higher)
    s3 = log(1 + hits) / log(1 + 5000)   for 1..5000 hits, 0 for no files found,
         NOT USED when hits > 5000 (common-word noise, not evidence of adoption)
A signal that is missing or not usable for a row is left OUT and the remaining weights are
rescaled to sum to 1. It is never silently treated as zero.

score = sum(weight_i * s_i) / sum(weight_i)   over the signals that are usable for that row.
"""
import itertools
import math
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

WEIGHTS = {"s1": 0.25, "s2": 0.30, "s3": 0.45}
NOISE_HITS = 5000          # above this a name is a common word, not evidence
HIGH, MEDIUM = 0.60, 0.40  # presentation tiers, NOT calibrated thresholds


def build_signals(ev, blast):
    df = ev.copy()
    df["s1"] = 1.0 - df["jaccard_distance"]

    def s3(n):
        if pd.isna(n):
            return np.nan
        if n > NOISE_HITS:
            return np.nan
        return math.log1p(n) / math.log1p(NOISE_HITS)

    df["s3"] = df["github_hit_count"].map(s3)
    df["s3_note"] = np.where(df["github_hit_count"] > NOISE_HITS, "common word, hit count ignored",
                             np.where(df["github_hit_count"] == 0, "no files found", ""))

    if blast is not None:
        b = blast.rename(columns={"dependents": "popular_dependents"})[["ecosystem", "popular_name", "popular_dependents"]]
        df = df.merge(b, on=["ecosystem", "popular_name"], how="left")
        top = df["popular_dependents"].max()
        df["s2"] = df["popular_dependents"].map(
            lambda x: np.nan if pd.isna(x) else math.log1p(x) / math.log1p(top) if top and top > 0 else np.nan)
    else:
        df["popular_dependents"] = np.nan
        df["s2"] = np.nan
    return df


def combine(df, weights):
    cols = ["s1", "s2", "s3"]
    w = np.array([weights[c] for c in cols])
    vals = df[cols].to_numpy(dtype=float)
    avail = ~np.isnan(vals)
    num = np.nansum(vals * w, axis=1)
    den = (avail * w).sum(axis=1)
    return np.where(den > 0, num / np.where(den > 0, den, 1), np.nan), avail.sum(axis=1)


def main():
    ev = pd.read_csv(os.path.join(DATA, "signal3_evidence_results.csv"))
    bpath = os.path.join(DATA, "blast_radius.csv")
    blast = pd.read_csv(bpath) if os.path.exists(bpath) else None
    if blast is None:
        print("NOTE: data/blast_radius.csv not found -> Signal 2 is 'not assessed' for every row. "
              "Run scoring/blast_radius_fetch.py, then re-run this script.")
    df = build_signals(ev, blast)
    df["score"], df["signals_used"] = combine(df, WEIGHTS)
    df.loc[df["signals_used"] < 2, "score"] = np.nan   # one signal alone is not a combined score

    vpath = os.path.join(DATA, "validation_overlap.csv")
    if os.path.exists(vpath):
        v = pd.read_csv(vpath)[["ecosystem", "candidate_name", "popular_name", "candidate_listed_malicious"]]
        df = df.merge(v, on=["ecosystem", "candidate_name", "popular_name"], how="left")
    else:
        df["candidate_listed_malicious"] = np.nan

    def tier(r):
        if r["signals_used"] < 2:
            return "UNSCORED (fewer than 2 usable signals)"
        return "HIGH" if r["score"] >= HIGH else "MEDIUM" if r["score"] >= MEDIUM else "LOW"

    df["tier"] = df.apply(tier, axis=1)
    df = df.sort_values("score", ascending=False, na_position="last").reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    out_cols = ["rank", "ecosystem", "popular_name", "candidate_name", "score", "tier", "signals_used",
                "jaccard_distance", "s1", "popular_dependents", "s2", "github_hit_count", "s3", "s3_note",
                "example_repo", "candidate_listed_malicious"]
    df[out_cols].round(4).to_csv(os.path.join(DATA, "final_scores.csv"), index=False)
    print(df[["rank", "popular_name", "candidate_name", "ecosystem", "score", "tier", "signals_used",
              "github_hit_count"]].head(15).to_string(index=False))
    print("\nTier counts:\n", df["tier"].value_counts().to_string())

    # ---------- validation against the ground-truth flag (OpenSSF), if available ----------
    if df["candidate_listed_malicious"].notna().any():
        y = df["candidate_listed_malicious"].fillna(False).astype(bool)
        rows = []
        # "all" mixes ecosystems; every known-malicious name is npm and npm packages have far more dependents
        # than PyPI ones, so the within-npm rows are the fair test for Signal 2.
        for scope, mask in [("all", np.ones(len(df), dtype=bool)), ("npm only", (df["ecosystem"] == "npm").to_numpy())]:
            for col in ["s1", "s2", "s3", "score"]:
                ok = df[col].notna().to_numpy() & mask
                pos, neg = df.loc[ok & y.to_numpy(), col], df.loc[ok & ~y.to_numpy(), col]
                if len(pos) and len(neg):
                    auc = float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))
                    rows.append({"scope": scope, "signal": col, "known_malicious_scored": len(pos),
                                 "others_scored": len(neg), "auc": round(auc, 3)})
        val = pd.DataFrame(rows)
        val.to_csv(os.path.join(DATA, "score_validation.csv"), index=False)
        print("\nAUC against OpenSSF listing (0.5 = no better than chance; few positives, so very uncertain):")
        print(val.to_string(index=False))
        kn = df[y][["rank", "ecosystem", "popular_name", "candidate_name", "score", "github_hit_count"]]
        print("\nWhere the known-malicious candidates ranked:\n", kn.to_string(index=False))

    # ---------- sensitivity: does the ranking survive different weights? ----------
    base = df.set_index(["ecosystem", "popular_name", "candidate_name"])["score"]
    rows = []
    grid = [round(x, 2) for x in np.arange(0.1, 0.85, 0.15)]
    for a, b in itertools.product(grid, grid):
        c = round(1 - a - b, 2)
        if c < 0.1:
            continue
        w = {"s1": a, "s2": b, "s3": c}
        sc, _ = combine(df, w)
        s = pd.Series(sc, index=base.index)
        s[df["signals_used"].to_numpy() < 2] = np.nan
        rho = s.rank().corr(base.rank())                 # Spearman rank correlation with the chosen weights
        top10 = set(s.sort_values(ascending=False).head(10).index) & set(base.sort_values(ascending=False).head(10).index)
        rows.append({"w_s1": a, "w_s2": b, "w_s3": c, "spearman_vs_chosen": round(rho, 3), "top10_overlap": len(top10)})
    sens = pd.DataFrame(rows)
    sens.to_csv(os.path.join(DATA, "score_sensitivity.csv"), index=False)
    print(f"\nSensitivity over {len(sens)} weight settings: Spearman vs chosen weights "
          f"min {sens.spearman_vs_chosen.min():.2f}, median {sens.spearman_vs_chosen.median():.2f}; "
          f"top-10 overlap min {sens.top10_overlap.min()} / 10, median {sens.top10_overlap.median():.0f} / 10")


if __name__ == "__main__":
    main()
