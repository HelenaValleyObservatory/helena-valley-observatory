#!/usr/bin/env python3
"""
OBSERVATORY FLOW LAB — Module 1: Segmenter
Reads daily JSONL aircraft logs and emits clean straight-flight segments.

A segment is a run of points from one aircraft that are:
  - temporally continuous (gap < MAX_GAP_SEC)
  - geometrically straight (turn rate < MAX_TURN_DEG_PER_SEC)
  - long enough to be useful (MIN_POINTS, MIN_DURATION_SEC)
  - at a meaningful groundspeed (MIN_GS_KT)

Output: segments.parquet with one row per segment.

Usage:
    python fl_segment.py --date 20260228
    python fl_segment.py --date 20260228 --jsonl /path/to/file.jsonl
"""

import argparse
import json
import math
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ── tuneable constants ────────────────────────────────────────────────────────
MAX_GAP_SEC        = 60      # split segment if position gap > this
MAX_TURN_DEG_S     = 3.0     # max instantaneous turn rate to stay "straight"
MIN_POINTS         = 8       # minimum messages per segment
MIN_DURATION_SEC   = 30      # minimum elapsed time per segment
MIN_GS_KT          = 30      # ignore taxiing / near-stationary
SMOOTHING_WINDOW   = 3       # rolling median for track smoothing (points)

# Altitude bins (feet AGL, KHLN field elev 3877 ft MSL → AGL = alt_baro - 3877)
ALT_BINS = [
    ("BL",    0,     3000),   # boundary layer
    ("LL",    3000,  8000),   # low level
    ("MID",   8000, 18000),   # mid level
    ("UPPER", 18000, 30000),  # upper
    ("JET",   30000, 99999),  # jet stream
]
FIELD_ELEV_FT = 3877

# Aircraft type → nominal TAS (kt) prior [mean, std]
# Based on category field: A1=light, A2=small, A3=large, A4=heavy, B1=rotorcraft
TAS_PRIOR = {
    "A1": (110,  30),   # light piston/turboprop
    "A2": (200,  50),   # small (C172 up to PC-12)
    "A3": (450,  60),   # large (regional jets, narrow-body)
    "A4": (480,  70),   # heavy
    "A5": (490,  70),   # super-heavy
    "B1": ( 90,  30),   # helicopter
    "B2": (130,  40),   # tiltrotor
    "C0": (  0,   1),   # ground vehicle — will be filtered
    "??": (250, 120),   # unknown — wide prior
}

import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from observatory_config import get_config
_cfg      = get_config()
DATA_ROOT = Path(_cfg["data_root"])
JSONL_DIR = DATA_ROOT / "aircraft"
OUT_DIR   = DATA_ROOT / "flowlab"


# ── helpers ───────────────────────────────────────────────────────────────────

def angle_diff(a, b):
    """Signed smallest difference between two bearings (degrees)."""
    d = (b - a + 180) % 360 - 180
    return d


def bearing_mean(angles):
    """Circular mean of a list of bearings."""
    rad = np.deg2rad(angles)
    return float(np.rad2deg(math.atan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))) % 360)


def alt_bin(alt_baro_ft):
    agl = alt_baro_ft - FIELD_ELEV_FT
    for name, lo, hi in ALT_BINS:
        if lo <= agl < hi:
            return name
    return "JET" if agl >= 30000 else "BL"


def _clean_cat(cat):
    """Normalize category — converts pandas NaN literal string to ??"""
    if cat is None: return "??"
    s = str(cat).strip()
    if s.lower() in ("nan", "none", "", "?"): return "??"
    try:
        import math
        if math.isnan(float(s)): return "??"
    except (ValueError, TypeError):
        pass
    return s

def tas_prior(category):
    cat = _clean_cat(category).upper()
    return TAS_PRIOR.get(cat, TAS_PRIOR["??"])


def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065  # nm
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ/2)**2 + math.cos(φ1)*math.cos(φ2)*math.sin(Δλ/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# ── core segmenter ────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for col in ["lat", "lon", "gs", "track", "alt_baro", "baro_rate", "nav_altitude_mcp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts", "lat", "lon", "gs", "track", "alt_baro"])
    df = df.sort_values(["hex", "ts"]).reset_index(drop=True)
    return df


def segment_aircraft(df_ac: pd.DataFrame) -> list[dict]:
    """Given all points for one aircraft, return list of segment dicts."""
    df = df_ac.copy().sort_values("ts").reset_index(drop=True)

    # Filter low-speed (ground / taxi)
    df = df[df["gs"] >= MIN_GS_KT].reset_index(drop=True)
    if len(df) < MIN_POINTS:
        return []

    # Smooth track angle to reduce GPS jitter
    df["track_smooth"] = (
        df["track"]
        .rolling(SMOOTHING_WINDOW, center=True, min_periods=1)
        .median()
    )

    segments = []
    seg_start = 0

    for i in range(1, len(df)):
        dt = (df.at[i, "ts"] - df.at[i-1, "ts"]).total_seconds()
        turn = abs(angle_diff(df.at[i-1, "track_smooth"], df.at[i, "track_smooth"]))
        turn_rate = turn / max(dt, 0.1)

        split = (dt > MAX_GAP_SEC) or (turn_rate > MAX_TURN_DEG_S)

        if split or i == len(df) - 1:
            end = i if split else i + 1
            seg_pts = df.iloc[seg_start:end]
            seg = _build_segment(seg_pts, df_ac["hex"].iloc[0],
                                 df_ac.get("flight", pd.Series([""])).iloc[0],
                                 _clean_cat(df_ac.get("category", pd.Series(["??"])).iloc[0]))
            if seg:
                segments.append(seg)
            seg_start = i

    return segments


def _build_segment(pts: pd.DataFrame, hex_id, flight, category) -> dict | None:
    if len(pts) < MIN_POINTS:
        return None

    t0 = pts["ts"].iloc[0]
    t1 = pts["ts"].iloc[-1]
    dur = (t1 - t0).total_seconds()
    if dur < MIN_DURATION_SEC:
        return None

    gs_mean  = pts["gs"].mean()
    gs_std   = pts["gs"].std()
    alt_mean = pts["alt_baro"].mean()
    alt_std  = pts["alt_baro"].std()

    # Mean track (circular)
    trk_mean = bearing_mean(pts["track_smooth"].tolist())

    # Groundspeed vector components
    trk_rad = np.deg2rad(pts["track"].values)
    gs_vals = pts["gs"].values
    vg_n = gs_vals * np.cos(trk_rad)   # northward kt
    vg_e = gs_vals * np.sin(trk_rad)   # eastward kt

    # Ground-track length
    lats = pts["lat"].values
    lons = pts["lon"].values
    dist_nm = sum(
        haversine_nm(lats[i], lons[i], lats[i+1], lons[i+1])
        for i in range(len(lats)-1)
    )

    # Vertical rate stats
    vr_mean = pts["baro_rate"].mean() if "baro_rate" in pts else 0.0

    # Phase of flight
    if abs(vr_mean) > 500:
        phase = "climb" if vr_mean > 0 else "descent"
    elif alt_std > 500:
        phase = "variable"
    else:
        phase = "level"

    # nav_altitude_mcp quality flag (v4.7 addition)
    # If present: |alt_baro - nav_mcp| > 300ft means transitioning
    # even if baro_rate looks calm (slow drift, step-climb initiation).
    # nav_mcp_ok=None means field absent — do not penalize.
    nav_mcp_mean = pts["nav_altitude_mcp"].dropna().mean()         if "nav_altitude_mcp" in pts.columns else None
    if nav_mcp_mean is not None and not pd.isna(nav_mcp_mean):
        nav_mcp_delta = abs(alt_mean - nav_mcp_mean)
        nav_mcp_ok    = bool(nav_mcp_delta <= 300.0)
    else:
        nav_mcp_delta = None
        nav_mcp_ok    = None

    # Alt bin at mean altitude
    abin = alt_bin(alt_mean)

    # TAS prior
    tas_mu, tas_sig = tas_prior(category)
    # GS-based override for unknown aircraft at JET altitude (2026-04-06)
    # Data shows ?? category at JET altitude has mean GS 449kt vs 250kt prior.
    # If unknown category, JET altitude, and GS > 350kt — use A3 prior (450,60).
    # Archive unchanged — applies to new segments only.
    if (_clean_cat(category) == "??"
            and alt_bin(alt_mean) == "JET"
            and gs_mean > 350.0):
        tas_mu, tas_sig = 450, 60

    # Time bin (3-hour UTC)
    hour = t0.hour
    time_bin = f"{(hour // 3) * 3:02d}-{(hour // 3) * 3 + 3:02d}Z"

    return {
        "hex":          hex_id,
        "flight":       str(flight) if flight else "",
        "category":     _clean_cat(category),
        "t_start":      t0.isoformat(),
        "t_end":        t1.isoformat(),
        "duration_sec": dur,
        "n_points":     len(pts),
        "dist_nm":      round(dist_nm, 3),
        "alt_mean_ft":  round(alt_mean, 0),
        "alt_std_ft":   round(alt_std, 1),
        "alt_bin":      abin,
        "gs_mean_kt":   round(gs_mean, 1),
        "gs_std_kt":    round(gs_std, 2),
        "trk_mean_deg": round(trk_mean, 1),
        "vg_n_mean":    round(float(vg_n.mean()), 2),   # kt northward
        "vg_e_mean":    round(float(vg_e.mean()), 2),   # kt eastward
        "vr_mean_fpm":  round(vr_mean, 0),
        "phase":        phase,
        "nav_mcp_ok":    nav_mcp_ok,
        "nav_mcp_delta": nav_mcp_delta,
        "time_bin":     time_bin,
        "tas_prior_mu": tas_mu,
        "tas_prior_sig":tas_sig,
        "lat_start":    round(float(pts["lat"].iloc[0]), 5),
        "lon_start":    round(float(pts["lon"].iloc[0]), 5),
        "lat_end":      round(float(pts["lat"].iloc[-1]), 5),
        "lon_end":      round(float(pts["lon"].iloc[-1]), 5),
        "lat_mid":      round(float(pts["lat"].mean()), 5),
        "lon_mid":      round(float(pts["lon"].mean()), 5),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Observatory Flow Lab — Segmenter")
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--jsonl", help="Override JSONL path")
    parser.add_argument("--out",   help="Override output directory")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl) if args.jsonl else JSONL_DIR / f"aircraft_{args.date}.jsonl"
    out_dir    = Path(args.out)   if args.out   else OUT_DIR / args.date
    out_dir.mkdir(parents=True, exist_ok=True)

    if not jsonl_path.exists():
        print(f"[ERROR] JSONL not found: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[segmenter] Loading {jsonl_path} ...")
    df = load_jsonl(jsonl_path)
    if df.empty:
        print("[ERROR] No valid points loaded.", file=sys.stderr)
        sys.exit(1)

    print(f"[segmenter] {len(df)} points, {df['hex'].nunique()} unique aircraft")

    all_segments = []
    for hex_id, grp in df.groupby("hex"):
        segs = segment_aircraft(grp)
        all_segments.extend(segs)

    if not all_segments:
        print("[ERROR] No segments produced — check QC thresholds.", file=sys.stderr)
        sys.exit(1)

    seg_df = pd.DataFrame(all_segments)
    out_path = out_dir / "segments.csv"
    seg_df.to_csv(out_path, index=False)
    seg_df.to_parquet(out_path.with_suffix(".parquet"), index=False)

    print(f"[segmenter] {len(seg_df)} segments → {out_path}")
    print(f"[segmenter] Alt bin distribution:")
    print(seg_df["alt_bin"].value_counts().to_string())
    print(f"[segmenter] Phase distribution:")
    print(seg_df["phase"].value_counts().to_string())
    print(f"[segmenter] Done.")


if __name__ == "__main__":
    main()
