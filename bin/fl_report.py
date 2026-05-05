#!/usr/bin/env python3
"""
OBSERVATORY FLOW LAB — Module 4: Daily Lab Report
Reads all parquet outputs for a date and produces a text report
in the style of the Observatory Field Manual (OFM).

Follows claim taxonomy: Observed Fact / Derived Metric / Inference / Speculation
No narrative is added that isn't supported by the data.

Usage:
    python fl_report.py --date 20260228
    python fl_report.py --date 20260228 --out ~/brief_flowlab_20260228.txt
"""

import argparse
import math
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np

import configparser, os

def _load_config():
    cfg = configparser.ConfigParser()
    cfg_path = os.environ.get(
        "OBSERVATORY_CONFIG",
        os.path.join(os.path.dirname(__file__), "..", "config", "observatory.cfg")
    )
    cfg.read(cfg_path)
    return cfg

_cfg            = _load_config()
DATA_ROOT       = Path(_cfg.get("observatory", "data_root",      fallback="/tmp/observatory/data"))
OUT_BASE        = DATA_ROOT / "flowlab"
BRIEFS_DIR      = DATA_ROOT / "briefs"
VALLEY_AXIS_DEG = float(_cfg.get("observatory", "valley_axis_deg", fallback="75.0"))
FIELD_ELEV_FT   = int(_cfg.get("observatory",   "field_elev_ft",   fallback="3877"))
KHLN_LAT        = float(_cfg.get("observatory", "receiver_lat",    fallback="46.5890"))
KHLN_LON        = float(_cfg.get("observatory", "receiver_lon",    fallback="-112.0391"))

ALT_BIN_LABELS = {
    "BL":    "Boundary Layer   (0–3k AGL)",
    "LL":    "Low Level        (3–8k AGL)",
    "MID":   "Mid Level        (8–18k AGL)",
    "UPPER": "Upper Level      (18–30k AGL)",
    "JET":   "Jet Level        (30k+ AGL)",
}

COMPASS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def deg_to_compass(deg):
    idx = int((deg % 360 + 11.25) / 22.5) % 16
    return COMPASS[idx]


def fmt_wind(spd, dirn):
    if spd < 2:
        return "CALM/LIGHT (<2kt)"
    return f"{spd:.0f}kt from {dirn:.0f}° ({deg_to_compass(dirn)})"


def regime_tag(shear_df: pd.DataFrame, ch_df: pd.DataFrame,
               q_good: int = 0, q_marginal: int = 0, q_all: int = 0, rc_mean: float = 0.0) -> str:
    """
    Classify the day's flow regime from shear + channeling data.
    Returns UNRESOLVED_LOW_CONFIDENCE when quality gates fail.
    Returns RESOLVED_MARGINAL when only Helena-baseline quality cells present.
    Gates: q_good==0 and q_marginal==0 → UNRESOLVED. q_good==0 but q_marginal>0 → RESOLVED_MARGINAL.
    Helena recalibration 2026-05-01: uncertainty denom raised 60→120 in fl_wind.py. [INFERENCE level]
    """
    import math
    mean_q = shear_df["mean_quality"].mean() if not shear_df.empty and "mean_quality" in shear_df.columns else 0.0
    low_confidence = (q_good == 0 and q_marginal == 0) or (mean_q < 0.05) or (rc_mean < 0.25)
    marginal_only  = (q_good == 0) and (q_marginal > 0) and not low_confidence
    if low_confidence:
        return "UNRESOLVED_LOW_CONFIDENCE"
    if marginal_only:
        return "RESOLVED_MARGINAL"  # Helena-baseline: usable with caution
    tags = []
    if not shear_df.empty:
        jet_row = shear_df[shear_df["alt_bin"] == "JET"]
        if not jet_row.empty and jet_row.iloc[0]["wind_spd_kt"] > 50:
            tags.append("STRONG-JET")
        elif not jet_row.empty and jet_row.iloc[0]["wind_spd_kt"] > 25:
            tags.append("MODERATE-JET")
        # Shear check
        max_shear = shear_df["shear_from_below_kt"].dropna().max() if "shear_from_below_kt" in shear_df.columns else float("nan")
        if not math.isnan(max_shear):
            if max_shear > 30:
                tags.append("HIGH-SHEAR")
            elif max_shear > 15:
                tags.append("MOD-SHEAR")
        # Low-level wind direction — only if BL quality is acceptable
        bl_row = shear_df[shear_df["alt_bin"] == "BL"]
        if not bl_row.empty and bl_row.iloc[0].get("mean_quality", 0) >= 0.1:
            dirn = bl_row.iloc[0]["wind_dir_deg"]
            tags.append(f"BL-FROM-{deg_to_compass(dirn)}")
    if not ch_df.empty:
        mean_ci = ch_df["ci_mean"].mean()
        if mean_ci > 0.75:
            tags.append("CHANNELING-DOMINANT")
        elif mean_ci > 0.5:
            tags.append("CHANNELING-MODERATE")

    return " | ".join(tags) if tags else "INDETERMINATE"


def load_parquet_optional(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            df = pd.read_csv(path)
            return df if not df.empty else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def build_report(date: str, out_path: Path | None = None) -> str:
    d = OUT_BASE / date
    seg_df   = load_parquet_optional(d / "segments.csv")
    wind_df  = load_parquet_optional(d / "wind_cells.csv")
    shear_df = load_parquet_optional(d / "shear_profile.csv")
    ch_df    = load_parquet_optional(d / "channeling_map.csv")
    ti_df    = load_parquet_optional(d / "turbulence_map.csv")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_fmt     = f"{date[:4]}-{date[4:6]}-{date[6:]}"

    # Synoptic regime from ERA5
    def _get_synoptic(date_str):
        try:
            import math as _math
            import numpy as _np
            import xarray as _xr
            _nc = DATA_ROOT / "era5" / f"era5_wind_{date_str[:6]}.nc"
            if not _nc.exists():
                return None, None, "NO_ERA5"
            _ds = _xr.open_dataset(_nc)
            _LAT, _LON = 46.60, -112.02
            _ds_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            _mask = _ds.valid_time.dt.strftime("%Y-%m-%d") == _ds_date
            _lats = _ds.latitude.values
            _lons = _ds.longitude.values
            _li = int(_np.argmin(_np.abs(_lats - _LAT)))
            _lo = int(_np.argmin(_np.abs(_lons - _LON)))
            _u = float(_ds["u"].where(_mask, drop=True).sel(
                pressure_level=500.0, method="nearest").mean("valid_time").values[_li, _lo])
            _v = float(_ds["v"].where(_mask, drop=True).sel(
                pressure_level=500.0, method="nearest").mean("valid_time").values[_li, _lo])
            _spd = _math.sqrt(_u**2 + _v**2) * 1.94384
            _dir = (270 - _math.degrees(_math.atan2(_v, _u))) % 360
            if _spd < 20:
                _regime = "WEAK"
            elif 240 <= _dir <= 300:
                _regime = "ZONAL"
            elif _dir > 300 or _dir < 60:
                _regime = "TROUGH_SUSPECT"
            else:
                _regime = "OTHER"
            return round(_dir, 1), round(_spd, 1), _regime
        except Exception:
            return None, None, "UNKNOWN"

    syn_dir, syn_spd, syn_regime = _get_synoptic(date)

    lines = []
    W = 72

    def div(char="─"):
        lines.append(char * W)

    def header(txt):
        lines.append("")
        lines.append(f"── {txt} " + "─" * (W - len(txt) - 4))

    div("═")
    lines.append(f"  OBSERVATORY FLOW LABORATORY — DAILY REPORT")
    lines.append(f"  Date     : {date_fmt}")
    lines.append(f"  Location : {_cfg.get('observatory', 'airport_name', fallback='RECV')}  {KHLN_LAT:.4f}°N  {abs(KHLN_LON):.4f}°W")
    lines.append(f"  Elev     : {FIELD_ELEV_FT} ft MSL")
    lines.append(f"  Generated: {generated_at}")
    if syn_regime == "TROUGH_SUSPECT" and syn_dir is not None:
        lines.append(f"  *** SYNOPTIC: {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 TROUGH_SUSPECT ***")
        lines.append(f"  *** JET/UPPER LOW_CONFIDENCE today \u2014 R does not detect this ***")
    elif syn_regime == "ZONAL" and syn_dir is not None:
        lines.append(f"  SYNOPTIC: {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 ZONAL (solver reliable)")
    elif syn_dir is not None:
        lines.append(f"  SYNOPTIC: {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 {syn_regime}")
    div("═")

    # ── Data Health ───────────────────────────────────────────────────────────
    header("DATA HEALTH  [Observed Fact]")
    if seg_df.empty:
        lines.append("  ⚠ NO SEGMENT DATA — run fl_segment.py first")
    else:
        lines.append(f"  Total segments    : {len(seg_df)}")
        lines.append(f"  Unique aircraft   : {seg_df['hex'].nunique()}")
        lines.append(f"  Level segments    : {(seg_df['phase']=='level').sum()}")
        lines.append(f"  Wind cells        : {len(wind_df)}")
        lines.append(f"  Channeling cells  : {len(ch_df)}")
        lines.append(f"  Turbulence cells  : {len(ti_df)}")

        lines.append("")
        lines.append("  Segments by altitude bin:")
        for abin, label in ALT_BIN_LABELS.items():
            n = (seg_df["alt_bin"] == abin).sum()
            bar = "█" * min(n, 40)
            lines.append(f"    {abin:<6}  {n:>4}  {bar}")

        if not wind_df.empty:
            q_good = (wind_df["quality_score"] > 0.4).sum()
            q_all  = len(wind_df)
            q_marginal_count = (wind_df["quality_score"] > 0.1).sum() - q_good
            lines.append(f"\n  Wind cell quality: {q_good}/{q_all} cells score >0.4 (HIGH)")
            lines.append(f"  Wind cell quality: {q_marginal_count}/{q_all} cells score 0.1–0.4 (MARGINAL)")
            rc_mean = wind_df["reciprocal_cov"].mean()
            lines.append(f"  Mean reciprocal coverage: {rc_mean:.2f}  (1=ideal, 0=no opposite legs)")

    # ── Regime Tag ────────────────────────────────────────────────────────────
    header("FLOW REGIME  [Inference]")
    if syn_dir is not None:
        if syn_regime == "TROUGH_SUSPECT":
            lines.append(f"  SYNOPTIC (ERA5 500hPa): {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 TROUGH_SUSPECT")
            lines.append("  WARNING: Non-westerly 500hPa flow. Solver unreliable today.")
            lines.append("  R value alone does not detect this failure mode.")
        elif syn_regime == "ZONAL":
            lines.append(f"  SYNOPTIC (ERA5 500hPa): {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 ZONAL")
            lines.append("  Westerly flow confirmed. Solver operating in reliable regime.")
        else:
            lines.append(f"  SYNOPTIC (ERA5 500hPa): {syn_dir:.0f}\u00b0 / {syn_spd:.0f}kt \u2014 {syn_regime}")
    else:
        lines.append(f"  SYNOPTIC (ERA5 500hPa): {syn_regime}")
    lines.append("")
    if not shear_df.empty or not ch_df.empty:
        _q_good     = int((wind_df["quality_score"] > 0.4).sum()) if not wind_df.empty and "quality_score" in wind_df.columns else 0
        _q_marginal = int(((wind_df["quality_score"] > 0.1) & (wind_df["quality_score"] <= 0.4)).sum()) if not wind_df.empty and "quality_score" in wind_df.columns else 0
        _q_all  = len(wind_df) if not wind_df.empty else 0
        _rc     = float(wind_df["reciprocal_cov"].mean()) if not wind_df.empty and "reciprocal_cov" in wind_df.columns else 0.0
        tag = regime_tag(shear_df, ch_df, q_good=_q_good, q_marginal=_q_marginal, q_all=_q_all, rc_mean=_rc)
        lines.append(f"  {tag}")
        lines.append("")
        if tag == "RESOLVED_MARGINAL":
            lines.append("  NOTE: RESOLVED_MARGINAL — Helena-baseline quality cells only.")
            lines.append("  Wind vectors usable with caution. Uncertainty is elevated.")
            lines.append("  Do not treat as equivalent to HIGH-CONFIDENCE resolved days.")
        elif tag == "UNRESOLVED_LOW_CONFIDENCE":
            lines.append("  *** LOW CONFIDENCE: 0 high-quality wind cells or mean Q < 0.1 or")
            lines.append("  *** reciprocal coverage < 0.25. Wind vectors should NOT be interpreted")
            lines.append("  *** physically without independent cross-check (sounding, Step-A, etc).")
        else:
            lines.append("  NOTE: Regime classification is inference-grade.")
            lines.append("  It is derived from TAS-prior wind estimates, not direct measurement.")
    else:
        lines.append("  INSUFFICIENT DATA")

    # ── Vertical Wind Profile ─────────────────────────────────────────────────
    header("VERTICAL WIND PROFILE  [Derived Metric]")
    if shear_df.empty:
        lines.append("  No shear profile computed.")
    else:
        lines.append(f"  {'Layer':<8} {'Speed':>8} {'Direction':>12} {'Shear↑':>10} {'N':>6} {'Q':>6}")
        lines.append(f"  {'─'*8} {'─'*8} {'─'*12} {'─'*10} {'─'*6} {'─'*6}")
        for _, row in shear_df.iterrows():
            shear_str = f"{row['shear_from_below_kt']:.0f}kt" if pd.notna(row.get('shear_from_below_kt')) and row.get('shear_from_below_kt') is not None else "  —"
            lines.append(
                f"  {row['alt_bin']:<8} "
                f"{row['wind_spd_kt']:>6.0f}kt "
                f"{row['wind_dir_deg']:>7.0f}° "
                f"({deg_to_compass(row['wind_dir_deg']):<3}) "
                f"{shear_str:>8}  "
                f"{int(row['n_segs']):>6}  "
                f"{row['mean_quality']:>5.2f}"
            )
        lines.append("")
        lines.append("  Shear = wind speed change between adjacent altitude bins.")
        lines.append("  Q = mean quality score (0–1). Scores < 0.3 are low confidence.")

    # ── Channeling Index ──────────────────────────────────────────────────────
    header("TERRAIN CHANNELING  [Derived Metric]")
    if ch_df.empty:
        lines.append("  No low-altitude segments available for channeling analysis.")
    else:
        ci_mean = ch_df["ci_mean"].mean()
        ci_max  = ch_df["ci_mean"].max()
        pf_mean = ch_df["primary_frac"].mean()

        ci_label = (
            "STRONG (terrain dominates flow)"   if ci_mean > 0.75 else
            "MODERATE (partial channeling)"      if ci_mean > 0.5  else
            "WEAK (flow crosses terrain freely)"
        )
        lines.append(f"  Valley axis    : {VALLEY_AXIS_DEG}° / {(VALLEY_AXIS_DEG+180)%360:.0f}° (ENE/WSW)")
        lines.append(f"  Mean CI        : {ci_mean:.3f}  → {ci_label}")
        lines.append(f"  Peak CI        : {ci_max:.3f}  (cell with strongest channeling)")
        lines.append(f"  Primary align  : {pf_mean*100:.0f}% of BL/LL legs within 45° of valley axis")
        lines.append("")
        lines.append("  Top channeling cells (BL/LL only):")
        lines.append(f"    {'Lat':>10} {'Lon':>11} {'CI':>6} {'N':>5}")
        for _, row in ch_df.nlargest(5, "ci_mean").iterrows():
            lines.append(f"    {row['lat_cell']:>10.4f} {row['lon_cell']:>11.4f} {row['ci_mean']:>6.3f} {int(row['n_segs']):>5}")

    # ── Turbulence Proxy ──────────────────────────────────────────────────────
    header("TURBULENCE PROXY  [Derived Metric]")
    if ti_df.empty:
        lines.append("  No turbulence proxy data.")
    else:
        ti_mean = ti_df["ti_norm"].mean()
        ti_max  = ti_df["ti_norm"].max()

        roughness = (
            "ROUGH (likely mechanical turbulence zones)"  if ti_mean > 0.5 else
            "MODERATE"                                     if ti_mean > 0.25 else
            "SMOOTH"
        )
        lines.append(f"  Basin roughness index : {ti_mean:.3f} → {roughness}")
        lines.append(f"  Peak cell TI (norm)   : {ti_max:.3f}")
        lines.append("")
        lines.append("  Top turbulence proxy cells (normalized TI):")
        lines.append(f"    {'Lat':>10} {'Lon':>11} {'TI':>6} {'GS-CV':>7} {'Hdg-σ':>7} {'N':>5}")
        for _, row in ti_df.nlargest(5, "ti_norm").iterrows():
            lines.append(
                f"    {row['lat_cell']:>10.4f} {row['lon_cell']:>11.4f} "
                f"{row['ti_norm']:>6.3f} {row['gs_cv']:>7.4f} "
                f"{row['heading_std']:>6.1f}°  {int(row['n_segs']):>5}"
            )
        lines.append("")
        lines.append("  TI = turbulence index, GS-CV = groundspeed coeff. of variation,")
        lines.append("  Hdg-σ = circular std of heading angles within cell.")

    # ── Falsifiability Checks ─────────────────────────────────────────────────
    header("FALSIFIABILITY CHECKS  [Derived Metric]")
    if not wind_df.empty and not seg_df.empty:
        # Test A: Drift vs airspeed scaling
        # Expect: slower aircraft have larger vw_e/vw_n scatter
        lines.append("  Test A — Drift vs Airspeed Scaling:")
        cats = seg_df.groupby("category")["tas_prior_mu"].mean()
        if len(cats) > 1:
            lines.append("    Aircraft classes present: " + ", ".join(
                f"{c}(TAS~{int(v)}kt)" for c, v in sorted(cats.items(), key=lambda x: x[1])
            ))
            lines.append("    (Cross-class consistency check requires wind_cells.parquet per category)")
            lines.append("    STATUS: PENDING — run multi-day comparison for statistical power")
        else:
            lines.append("    Only one aircraft class present — test not applicable today.")

        # Test B: Reciprocal leg consistency
        rc_mean = wind_df["reciprocal_cov"].mean()
        if rc_mean > 0.3:
            lines.append(f"\n  Test B — Reciprocal Leg Coverage: {rc_mean:.2f}")
            lines.append("    PASS: Sufficient reciprocal pairs exist for wind cross-check.")
        else:
            lines.append(f"\n  Test B — Reciprocal Leg Coverage: {rc_mean:.2f}")
            lines.append("    CAUTION: Low reciprocal coverage. Wind estimates rely on TAS priors,")
            lines.append("    not direct cancellation. Uncertainty bands are wider.")

        # Test C: Time continuity (rough check)
        if "time_bin" in wind_df.columns:
            n_bins = wind_df["time_bin"].nunique()
            lines.append(f"\n  Test C — Time Coverage: {n_bins} 3-hour bins with wind data")
            if n_bins >= 6:
                lines.append("    PASS: Reasonable temporal coverage for trend analysis.")
            else:
                lines.append("    CAUTION: Sparse temporal coverage — hourly trends unreliable.")
    else:
        lines.append("  Insufficient data to run falsifiability checks.")

    # ── Claim Taxonomy Summary ────────────────────────────────────────────────
    header("CLAIM TAXONOMY")
    lines.append("  All quantitative outputs in this report are DERIVED METRICS")
    lines.append("  computed deterministically from OBSERVED FACTS (raw JSONL).")
    lines.append("")
    lines.append("  Wind vectors are INFERENCE-grade: they depend on TAS priors.")
    lines.append("  Channeling and turbulence indices are DERIVED METRICS: they")
    lines.append("  measure aircraft motion statistics, not direct atmospheric state.")
    lines.append("")
    lines.append("  No SPECULATION is promoted in this report.")
    lines.append("  All outputs are reproducible from segments.parquet.")

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("")
    div("═")
    lines.append(f"  END OF FLOW LAB REPORT — {date_fmt}")
    lines.append(f"  Generated {generated_at}")
    lines.append(f"  Governed by Observatory Charter v1.0 + Flow Lab Doctrine")
    div("═")
    lines.append("")

    report = "\n".join(lines)

    # Write to briefs dir
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    default_out = BRIEFS_DIR / f"flowlab_{date}.txt"
    target = out_path if out_path else default_out
    target.write_text(report)
    print(f"[report] Report written → {target}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Observatory Flow Lab — Daily Report")
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument("--out",  help="Override output path")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else None
    report = build_report(args.date, out_path)
    print(report)


if __name__ == "__main__":
    main()
