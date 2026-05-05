#!/usr/bin/env python3
"""
OBSERVATORY FLOW LAB — Module 3: Channeling + Turbulence Proxy
Reads segments.parquet and produces:
  - channeling_map.parquet  : valley-alignment index per spatial cell
  - turbulence_map.parquet  : heading/speed variance proxy per cell

Channeling Index (CI):
    For BL/LL segments, measure how tightly track angles cluster
    around the local valley axis (or its reciprocal).
    CI = mean(cos(delta)) where delta = min angle to valley axis or its reciprocal

Turbulence Proxy Index (TI):
    For all segments, measure:
      - gs_std / gs_mean     (groundspeed jitter, normalized)
      - track circular std   (heading scatter)
    Combined into TI = sqrt(gs_cv² + heading_std_norm²)

Usage:
    python fl_terrain.py --date 20260228
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import configparser, os

def _load_config():
    cfg = configparser.ConfigParser()
    cfg_path = os.environ.get(
        "OBSERVATORY_CONFIG",
        os.path.join(os.path.dirname(__file__), "..", "config", "observatory.cfg")
    )
    cfg.read(cfg_path)
    return cfg

_cfg      = _load_config()
DATA_ROOT = Path(_cfg.get("observatory", "data_root", fallback="/tmp/observatory/data"))
OUT_BASE  = DATA_ROOT / "flowlab"
KHLN_LAT  = float(_cfg.get("observatory", "receiver_lat",   fallback="46.5890"))
KHLN_LON  = float(_cfg.get("observatory", "receiver_lon",   fallback="-112.0391"))
GRID_DEG  = 0.15
_axis     = float(_cfg.get("observatory", "valley_axis_deg", fallback="75.0"))
VALLEY_AXES = [_axis, (_axis - 60) % 180]


# ── helpers ───────────────────────────────────────────────────────────────────

def cell_label(lat, lon):
    lat_cell = round(round((lat - KHLN_LAT) / GRID_DEG) * GRID_DEG + KHLN_LAT, 4)
    lon_cell = round(round((lon - KHLN_LON) / GRID_DEG) * GRID_DEG + KHLN_LON, 4)
    return f"{lat_cell:.4f},{lon_cell:.4f}"


def circular_std(angles_deg):
    """Circular standard deviation of bearing list."""
    rad = np.deg2rad(angles_deg)
    R = math.sqrt(np.mean(np.cos(rad))**2 + np.mean(np.sin(rad))**2)
    R = min(R, 1.0)
    return math.degrees(math.sqrt(-2 * math.log(R)))


def valley_alignment(track_deg, axes=VALLEY_AXES):
    """
    Compute alignment of a single track angle with nearest valley axis
    or its reciprocal. Returns cos(delta) ∈ [-1, 1].
    1 = perfectly aligned, 0 = perpendicular.
    """
    best = 0.0
    for axis in axes:
        for candidate in [axis, (axis + 180) % 360]:
            delta = abs((track_deg - candidate + 180) % 360 - 180)
            c = math.cos(math.radians(delta))
            if c > best:
                best = c
    return best


# ── channeling map ─────────────────────────────────────────────────────────────

def build_channeling_map(df: pd.DataFrame) -> pd.DataFrame:
    """
    Only uses BL + LL segments (boundary layer and low level).
    These are the segments most influenced by terrain channeling.
    """
    low_alt = df[df["alt_bin"].isin(["BL", "LL"])].copy()
    if low_alt.empty:
        print("[terrain] No BL/LL segments for channeling map.")
        return pd.DataFrame()

    low_alt["cell"] = low_alt.apply(
        lambda r: cell_label(r["lat_mid"], r["lon_mid"]), axis=1
    )
    low_alt["ci_seg"] = low_alt["trk_mean_deg"].apply(valley_alignment)

    records = []
    for cell, grp in low_alt.groupby("cell"):
        n = len(grp)
        if n < 3:
            continue

        ci_mean = grp["ci_seg"].mean()
        ci_std  = grp["ci_seg"].std()

        # Directional histogram: fraction in each axis quadrant
        tracks = grp["trk_mean_deg"].values
        primary_axis   = VALLEY_AXES[0]
        secondary_axis = VALLEY_AXES[1]

        # Fraction aligned with primary valley (within ±45°)
        primary_frac = np.mean([
            1 if min(abs((t - primary_axis + 180) % 360 - 180),
                     abs((t - (primary_axis+180)%360 + 180) % 360 - 180)) < 45
            else 0
            for t in tracks
        ])

        # Dominant track direction
        trk_circ_std = circular_std(tracks.tolist())

        lat_c, lon_c = (float(x) for x in cell.split(","))

        records.append({
            "cell":            cell,
            "lat_cell":        lat_c,
            "lon_cell":        lon_c,
            "n_segs":          n,
            "n_aircraft":      grp["hex"].nunique(),
            "ci_mean":         round(ci_mean, 3),
            "ci_std":          round(ci_std, 3),
            "primary_frac":    round(primary_frac, 3),
            "trk_circ_std":    round(trk_circ_std, 1),
            "dominant_alt_bin": grp["alt_bin"].mode().iloc[0],
        })

    return pd.DataFrame(records)


# ── turbulence proxy map ───────────────────────────────────────────────────────

def build_turbulence_map(df: pd.DataFrame) -> pd.DataFrame:
    """
    Turbulence Proxy Index (TI) per spatial cell.
    Uses ALL segment types (including climb/descent for helicopters and trainers).

    TI = sqrt( (gs_std/gs_mean)² + (heading_std / 90)² )
    Higher = more turbulent.

    Focus on low/slow aircraft (BL, LL, helicopters, A1/A2 category).
    """
    # Prefer low & slow aircraft for turbulence sensing
    turb_df = df[
        (df["alt_bin"].isin(["BL", "LL", "MID"])) |
        (df["category"].isin(["B1", "B2", "A1"]))
    ].copy()

    if turb_df.empty:
        print("[terrain] No suitable segments for turbulence map.")
        return pd.DataFrame()

    turb_df["cell"] = turb_df.apply(
        lambda r: cell_label(r["lat_mid"], r["lon_mid"]), axis=1
    )

    records = []
    for cell, grp in turb_df.groupby("cell"):
        n = len(grp)
        if n < 3:
            continue

        # GS coefficient of variation (normalized jitter)
        gs_mean = grp["gs_mean_kt"].mean()
        gs_cv   = grp["gs_std_kt"].mean() / max(gs_mean, 1.0)

        # Heading scatter: circular std of mean track angles
        heading_std = circular_std(grp["trk_mean_deg"].tolist())

        # Combined TI
        ti = math.sqrt(gs_cv**2 + (heading_std / 90.0)**2)

        lat_c, lon_c = (float(x) for x in cell.split(","))

        records.append({
            "cell":         cell,
            "lat_cell":     lat_c,
            "lon_cell":     lon_c,
            "n_segs":       n,
            "n_aircraft":   grp["hex"].nunique(),
            "ti":           round(ti, 4),
            "gs_cv":        round(gs_cv, 4),
            "heading_std":  round(heading_std, 2),
            "gs_mean_kt":   round(gs_mean, 1),
            "category_mix": ",".join(sorted(grp["category"].dropna().astype(str).unique())),
        })

    out = pd.DataFrame(records)
    # Normalize TI to 0–1 range for interpretability
    if not out.empty and out["ti"].max() > 0:
        out["ti_norm"] = (out["ti"] / out["ti"].quantile(0.95)).clip(0, 1).round(3)
    else:
        out["ti_norm"] = 0.0

    return out


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Observatory Flow Lab — Terrain + Turbulence")
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--seg",  help="Override segments.parquet path")
    args = parser.parse_args()

    seg_path = Path(args.seg) if args.seg else OUT_BASE / args.date / "segments.csv"
    out_dir  = seg_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if not seg_path.exists():
        print(f"[ERROR] segments.parquet not found: {seg_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[terrain] Loading {seg_path} ...")
    df = pd.read_csv(seg_path)
    print(f"[terrain] {len(df)} segments loaded")

    # ── channeling map ─────────────────────────────────────────────────────
    print("[terrain] Building channeling map ...")
    ch_map = build_channeling_map(df)
    if not ch_map.empty:
        ch_path = out_dir / "channeling_map.csv"
        ch_map.to_csv(ch_path, index=False)
        ch_map.to_parquet(ch_path.with_suffix(".parquet"), index=False)
        print(f"[terrain] {len(ch_map)} channeling cells → {ch_path}")
        print("\n── Channeling Map Summary ────────────────────────────")
        print(f"  Valley axes: {VALLEY_AXES[0]}° (primary), {VALLEY_AXES[1]}° (secondary)")
        print(f"  Mean CI across cells: {ch_map['ci_mean'].mean():.3f}  (1=perfect alignment)")
        top_ci = ch_map.nlargest(3, "ci_mean")[["lat_cell","lon_cell","ci_mean","n_segs"]]
        print("  Top channeling cells:")
        print(top_ci.to_string(index=False))

    # ── turbulence map ─────────────────────────────────────────────────────
    print("\n[terrain] Building turbulence proxy map ...")
    ti_map = build_turbulence_map(df)
    if not ti_map.empty:
        ti_path = out_dir / "turbulence_map.csv"
        ti_map.to_csv(ti_path, index=False)
        ti_map.to_parquet(ti_path.with_suffix(".parquet"), index=False)
        print(f"[terrain] {len(ti_map)} turbulence cells → {ti_path}")
        print("\n── Turbulence Map Summary ────────────────────────────")
        top_ti = ti_map.nlargest(3, "ti_norm")[["lat_cell","lon_cell","ti_norm","gs_cv","heading_std","n_segs"]]
        print("  Top turbulence cells (normalized TI):")
        print(top_ti.to_string(index=False))

    print("\n[terrain] Done.")


if __name__ == "__main__":
    main()
