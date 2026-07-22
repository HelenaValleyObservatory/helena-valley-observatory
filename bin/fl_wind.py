#!/usr/bin/env python3
"""
OBSERVATORY FLOW LAB — Module 2: Wind Solver
Reads segments.parquet and derives wind vectors per (alt_bin, time_bin, spatial_cell).

Method:
  For each bin, we have an ensemble of ground velocity vectors (vg_n, vg_e)
  and TAS priors (tas_prior_mu, tas_prior_sig).

  The wind vector (vw_n, vw_e) is estimated as:
      vg = va + vw
      →  vw ≈ vg_mean  −  va_mean_in_direction_of_vg

  For "level" segments only, we use a bias-correction step:
      va_n = tas_mu * cos(trk)
      va_e = tas_mu * sin(trk)
      vw_n = vg_n - va_n   (per segment)
      vw_e = vg_e - va_e

  Then aggregate per bin: mean + std of (vw_n, vw_e).

  Confidence metric: n_segs, n_aircraft, reciprocal_coverage (fraction of bins
  that have near-opposite legs within ±45° of 180° difference).

Output: wind_cells.parquet

Usage:
    python fl_wind.py --date 20260228
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from observatory_config import get_config
_cfg      = get_config()
DATA_ROOT = Path(_cfg["data_root"])
OUT_BASE  = DATA_ROOT / "flowlab"

# Spatial grid: ~10nm cells around KHLN (46.5890, -112.0391)
# We use a simple lat/lon grid bucketing
GRID_DEG = 0.15   # ~10nm per cell at this latitude

KHLN_LAT = 46.5890
KHLN_LON = -112.0391

# Valley axis for Helena Basin (approx WSW-ENE corridor)
VALLEY_AXIS_DEG = 75.0   # degrees (ENE direction of valley)


def angle_diff(a, b):
    return (b - a + 180) % 360 - 180


def bearing_mean_weighted(angles, weights=None):
    rad = np.deg2rad(angles)
    if weights is None:
        weights = np.ones(len(rad))
    wx = np.sum(weights * np.cos(rad))
    wy = np.sum(weights * np.sin(rad))
    # Double mod: floating-point cancellation in wx/wy can leave atan2 a hair
    # below zero, which % 360 rounds up to exactly 360.0 instead of ~0.0.
    # 360.0 % 360 == 0.0 exactly (no cancellation), so re-wrapping fixes it.
    return float(np.rad2deg(math.atan2(wy, wx)) % 360 % 360)


def cell_label(lat, lon):
    lat_cell = round(round((lat - KHLN_LAT) / GRID_DEG) * GRID_DEG + KHLN_LAT, 4)
    lon_cell = round(round((lon - KHLN_LON) / GRID_DEG) * GRID_DEG + KHLN_LON, 4)
    return f"{lat_cell:.4f},{lon_cell:.4f}"


def reciprocal_coverage(tracks):
    """Fraction of track angles that have a near-reciprocal partner (±30°)."""
    tracks = np.array(tracks)
    n = len(tracks)
    if n < 2:
        return 0.0
    count = 0
    for t in tracks:
        recip = (t + 180) % 360
        if any(abs(angle_diff(t2, recip)) < 30 for t2 in tracks if t2 != t):
            count += 1
    return count / n


def solve_winds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-segment wind estimate:
        vw_n = vg_n - tas_mu * cos(trk)
        vw_e = vg_e - tas_mu * sin(trk)

    This is the single-segment estimate — noisy but unbiased over ensemble.
    """
    trk_rad = np.deg2rad(df["trk_mean_deg"].values)
    tas     = df["tas_prior_mu"].values

    va_n = tas * np.cos(trk_rad)
    va_e = tas * np.sin(trk_rad)

    df = df.copy()
    df["vw_n_seg"] = df["vg_n_mean"] - va_n
    df["vw_e_seg"] = df["vg_e_mean"] - va_e

    # Per-segment wind speed / direction
    df["vw_spd_seg"] = np.sqrt(df["vw_n_seg"]**2 + df["vw_e_seg"]**2)
    df["vw_dir_seg"] = (
        np.rad2deg(np.arctan2(df["vw_e_seg"], df["vw_n_seg"])) % 360 % 360
    )

    return df


def aggregate_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate wind estimates into spatial/altitude/time cells."""
    df["cell"] = df.apply(lambda r: cell_label(r["lat_mid"], r["lon_mid"]), axis=1)

    records = []
    for (cell, alt_bin, time_bin), grp in df.groupby(["cell", "alt_bin", "time_bin"]):
        if len(grp) < 3:
            continue

        n      = len(grp)
        n_ac   = grp["hex"].nunique()

        vw_n   = grp["vw_n_seg"].values
        vw_e   = grp["vw_e_seg"].values

        # Robust mean (trim 10% tails)
        def trimmed_mean(x, trim=0.1):
            lo, hi = np.quantile(x, [trim, 1-trim])
            mask = (x >= lo) & (x <= hi)
            return x[mask].mean() if mask.sum() > 0 else x.mean()

        vw_n_mean = trimmed_mean(vw_n)
        vw_e_mean = trimmed_mean(vw_e)
        vw_n_std  = vw_n.std()
        vw_e_std  = vw_e.std()

        spd  = math.sqrt(vw_n_mean**2 + vw_e_mean**2)
        dirn = math.degrees(math.atan2(vw_e_mean, vw_n_mean)) % 360 % 360

        rc = reciprocal_coverage(grp["trk_mean_deg"].tolist())

        # Quality score: 0–1
        # penalize low n, low reciprocal coverage, high uncertainty
        uncertainty = math.sqrt(vw_n_std**2 + vw_e_std**2)
        q = min(1.0, n / 20) * (0.5 + 0.5 * rc) * max(0.1, 1 - uncertainty / 120)  # Helena-calibrated: archive median unc ~60kt, denom raised from 60→120

        # Valley channeling contribution: cos(angle between wind and valley axis)
        ci = math.cos(math.radians(angle_diff(dirn, VALLEY_AXIS_DEG)))

        lat_c, lon_c = (float(x) for x in cell.split(","))

        records.append({
            "cell":          cell,
            "lat_cell":      lat_c,
            "lon_cell":      lon_c,
            "alt_bin":       alt_bin,
            "time_bin":      time_bin,
            "n_segs":        n,
            "n_aircraft":    n_ac,
            "vw_n_kt":       round(vw_n_mean, 2),
            "vw_e_kt":       round(vw_e_mean, 2),
            "vw_n_std":      round(vw_n_std, 2),
            "vw_e_std":      round(vw_e_std, 2),
            "wind_spd_kt":   round(spd, 1),
            "wind_dir_deg":  round(dirn, 1),
            "uncertainty_kt":round(uncertainty, 1),
            "reciprocal_cov":round(rc, 3),
            "quality_score": round(q, 3),
            "quality_tier":  ("HIGH" if q > 0.4 else "MARGINAL" if q > 0.1 else "LOW"),  # two-tier: HIGH=resolved, MARGINAL=Helena-baseline, LOW=unusable
            "channeling_idx":round(ci, 3),
        })

    return pd.DataFrame(records)


def build_shear_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Vertical shear profile aggregated over all cells for the day."""
    ALT_ORDER = ["BL", "LL", "MID", "UPPER", "JET"]
    records = []

    for alt_bin in ALT_ORDER:
        grp = df[df["alt_bin"] == alt_bin]
        if grp.empty:
            continue
        vw_n = np.average(grp["vw_n_kt"], weights=grp["n_segs"])
        vw_e = np.average(grp["vw_e_kt"], weights=grp["n_segs"])
        spd  = math.sqrt(vw_n**2 + vw_e**2)
        dirn = math.degrees(math.atan2(vw_e, vw_n)) % 360 % 360
        records.append({
            "alt_bin":       alt_bin,
            "vw_n_kt":       round(vw_n, 2),
            "vw_e_kt":       round(vw_e, 2),
            "wind_spd_kt":   round(spd, 1),
            "wind_dir_deg":  round(dirn, 1),
            "n_segs":        int(grp["n_segs"].sum()),
            "n_aircraft":    int(grp["n_aircraft"].sum()),
            "mean_quality":  round(grp["quality_score"].mean(), 3),
        })

    # Add shear between adjacent layers
    out = pd.DataFrame(records)
    if len(out) >= 2:
        spd_vals = out["wind_spd_kt"].values
        dir_vals = out["wind_dir_deg"].values
        shear = [None]
        for i in range(1, len(out)):
            dv_n = out.at[i, "vw_n_kt"] - out.at[i-1, "vw_n_kt"]
            dv_e = out.at[i, "vw_e_kt"] - out.at[i-1, "vw_e_kt"]
            shear.append(round(math.sqrt(dv_n**2 + dv_e**2), 1))
        out["shear_from_below_kt"] = shear
    return out


def main():
    parser = argparse.ArgumentParser(description="Observatory Flow Lab — Wind Solver")
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--seg",  help="Override segments.parquet path")
    args = parser.parse_args()

    seg_path = Path(args.seg) if args.seg else OUT_BASE / args.date / "segments.csv"
    out_dir  = seg_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if not seg_path.exists():
        print(f"[ERROR] segments.parquet not found: {seg_path}", file=sys.stderr)
        print("  Run fl_segment.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"[wind_solver] Loading {seg_path} ...")
    df = pd.read_csv(seg_path)

    # Use only level segments for wind solving (cleanest signal)
    df_level = df[df["phase"] == "level"].copy()
    print(f"[wind_solver] {len(df)} total segments, {len(df_level)} level")

    if len(df_level) < 10:
        print("[WARN] Very few level segments — wind estimates will be low quality.")

    df_level = solve_winds(df_level)

    # Save per-segment wind estimates
    seg_wind_path = out_dir / "segments_wind.csv"
    df_level.to_csv(seg_wind_path, index=False)
    df_level.to_parquet(seg_wind_path.with_suffix(".parquet"), index=False)
    print(f"[wind_solver] Per-segment winds → {seg_wind_path}")

    # Aggregate into cells
    cells = aggregate_cells(df_level)
    cells_path = out_dir / "wind_cells.csv"
    cells.to_csv(cells_path, index=False)
    cells.to_parquet(cells_path.with_suffix(".parquet"), index=False)
    print(f"[wind_solver] {len(cells)} wind cells → {cells_path}")

    # Shear profile
    shear = build_shear_profile(cells) if not cells.empty else pd.DataFrame()
    shear_path = out_dir / "shear_profile.csv"
    if not shear.empty:
        shear.to_csv(shear_path, index=False)
        shear.to_parquet(shear_path.with_suffix(".parquet"), index=False)
        print(f"[wind_solver] Shear profile → {shear_path}")
    else:
        print("[wind_solver] No shear profile — insufficient binned data.")
        shear_path = None

    if not shear.empty and "alt_bin" in shear.columns:
        print("\n── Vertical Wind Profile ──────────────────────────────")
        cols = [c for c in ["alt_bin","wind_spd_kt","wind_dir_deg",
                             "shear_from_below_kt","n_segs","mean_quality"]
                if c in shear.columns]
        print(shear[cols].to_string(index=False))
    else:
        print("\n── Vertical Wind Profile: NO DATA (need more level segments per cell) ──")
    print()

    # Best cells (quality > 0.4)
    if not cells.empty and "quality_score" in cells.columns:
        good = cells[cells["quality_score"] > 0.4].sort_values("alt_bin")
        print(f"── High-quality wind cells (q>0.4): {len(good)} ──────────")
        if not good.empty:
            print(good[["alt_bin","lat_cell","lon_cell",
                         "wind_spd_kt","wind_dir_deg","uncertainty_kt",
                         "n_segs","quality_score"]].to_string(index=False))
    else:
        print("── Wind cells: 0 (need ≥3 level segments per spatial cell) ──────────")
    print("\n[wind_solver] Done.")


if __name__ == "__main__":
    main()
