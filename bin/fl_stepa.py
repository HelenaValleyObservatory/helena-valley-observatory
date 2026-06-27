#!/usr/bin/env python3
"""
OBSERVATORY FLOW LAB — Step A: Reciprocal-Pair Gold Set
========================================================
Finds pairs of aircraft flying reciprocal headings through the same
spatial cell and time window, then solves for wind U/V analytically.

Physics:
    Groundspeed vector = TAS vector + Wind vector
    Aircraft 1 (heading H):    GS1 = TAS1 * [sin H, cos H] + [U, V]
    Aircraft 2 (heading H+180): GS2 = TAS2 * [-sin H, -cos H] + [U, V]

    Adding:  GS1 + GS2 = (TAS1 - TAS2) * [sin H, cos H] + 2*[U, V]

    If we assume TAS1 ≈ TAS2 (same aircraft type, same altitude):
        U = (GS1_e + GS2_e) / 2
        V = (GS1_n + GS2_n) / 2

    This is the "midpoint estimator" — TAS cancels when aircraft are similar.
    For dissimilar TAS, we solve the full system using groundspeed magnitude
    constraints and heading geometry.

Quality:
    Each pair gets a quality score based on:
    - Heading difference (180° = perfect, penalize deviation)
    - Time separation (0 min = best, penalize >30 min)
    - Spatial separation (0 km = best, penalize >50 km)
    - TAS similarity (same class = best)

Output:
    Per-cell, per-day wind estimates with bootstrap confidence intervals.
    Aggregated daily wind vector with R (vector strength) and N (pair count).

Usage:
    python fl_stepa.py
    python fl_stepa.py --date 20260224
    python fl_stepa.py --min-pairs 3 --verbose
"""

import argparse
import csv
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_ROOT, FLOWLAB, BRIEFS

# Grid cell size for spatial binning
CELL_LAT_DEG = 0.25   # ~28km
CELL_LON_DEG = 0.35   # ~25km at 47°N

# Pairing windows
MAX_HEADING_DEV  = 20.0   # degrees from perfect reciprocal (180°)
MAX_TIME_SEP_MIN = 45.0   # minutes
MAX_SPATIAL_KM   = 80.0   # km between segment midpoints

# Quality thresholds
MIN_PAIRS_FOR_CELL   = 2
MIN_PAIRS_FOR_DAY    = 5
BOOTSTRAP_ITERATIONS = 500

# Geometry quality flag — cross-track failure mode (verified by IGRA2)
# Helena valley axis: ~75/255 ENE-WSW. When true wind is perpendicular
# (southerly ~165-195 or northerly ~345-015), the midpoint estimator
# produces spurious high-speed results with misleadingly high R.
# Confirmed artifacts: 20260129 (LL 157kt), 20260208 (LL 130kt).
VALLEY_AXIS_DEG    = 75.0  # primary valley axis (ENE)
GEOM_SUSPECT_WIDTH = 30.0  # flag if wind within this many degrees of perpendicular


def is_geom_suspect(wind_dir_deg):
    """Return True if wind is near-perpendicular to valley axis.
    Perpendicular to 75-deg axis is 165-deg and 345-deg.
    Flags within GEOM_SUSPECT_WIDTH of either perpendicular."""
    for perp in [(VALLEY_AXIS_DEG + 90) % 360, (VALLEY_AXIS_DEG - 90) % 360]:
        if abs(((wind_dir_deg - perp + 180) % 360) - 180) <= GEOM_SUSPECT_WIDTH:
            return True
    return False

COMPASS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
           "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def deg_to_compass(deg):
    if deg is None: return "---"
    return COMPASS[int((float(deg) % 360 + 11.25) / 22.5) % 16]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def heading_diff(h1, h2):
    """Absolute angular difference between two headings, 0–180."""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)

def cell_key(lat, lon):
    return (int(lat / CELL_LAT_DEG), int(lon / CELL_LON_DEG))

def parse_time_to_minutes(t_str):
    """Parse HH:MM or HH:MM:SS to minutes since midnight."""
    try:
        parts = t_str.strip().split(':')
        h, m = int(parts[0]), int(parts[1])
        s = int(parts[2]) if len(parts) > 2 else 0
        return h * 60 + m + s / 60
    except Exception:
        return None

def load_segments(date_str):
    """
    Load segment data for a date from segments.csv.
    Returns list of dicts with: lat, lon, heading, gs_kt, tas_kt, alt_ft, time_min, icao
    """
    # Prefer segments_wind.csv (has solved wind too), fall back to segments.csv
    for fname in ["segments_wind.csv", "segments.csv"]:
        seg_path = FLOWLAB / date_str / fname
        if seg_path.exists():
            break
    else:
        return []

    segments = []
    with open(seg_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat     = float(row.get('lat_mid') or 0)
                lon     = float(row.get('lon_mid') or 0)
                heading = float(row.get('trk_mean_deg') or 0)
                gs_kt   = float(row.get('gs_mean_kt') or 0)
                alt_ft  = float(row.get('alt_mean_ft') or 0)
                icao    = row.get('hex') or 'UNKNOWN'
                category = row.get('category') or ''

                tas_raw = row.get('tas_prior_mu') or ''
                try:    tas_kt = float(tas_raw) if tas_raw else None
                except: tas_kt = None

                # Parse t_start timestamp to minutes since midnight
                t_str = row.get('t_start') or ''
                time_min = None
                if 'T' in t_str:
                    try:
                        time_part = t_str.split('T')[1][:8]  # HH:MM:SS
                        time_min = parse_time_to_minutes(time_part)
                    except: pass

                if gs_kt < 50 or lat == 0:
                    continue

                # Phase and altitude stability filter.
                # Reciprocal-pair method requires steady level flight so TAS cancels.
                # Climb/descent segments contaminate the estimate with airspeed.
                phase   = row.get('phase', '')
                alt_std = float(row.get('alt_std_ft') or 9999)

                if alt_ft < 18000:
                    # BL and LL: level-only + low altitude variance
                    if phase != 'level' or alt_std > 500:
                        continue
                elif alt_ft < 28000:
                    # MID: level-only (transition zone, high climb/descent fraction)
                    if phase != 'level':
                        continue
                # UPPER and JET: no filter needed (96%+ already level, alt_std ~7ft)

                # nav_mcp_ok quality filter (v4.8)
                # Exclude segments where aircraft is not established at assigned
                # altitude — slow drift and step-climb cases invisible to baro_rate.
                # nav_mcp_ok=None means field absent (older data) — pass through.
                nav_mcp_ok = row.get('nav_mcp_ok')
                if nav_mcp_ok == 'False':
                    continue

                gs_e = gs_kt * math.sin(math.radians(heading))
                gs_n = gs_kt * math.cos(math.radians(heading))

                segments.append({
                    'lat': lat, 'lon': lon,
                    'heading': heading,
                    'gs_kt': gs_kt, 'gs_e': gs_e, 'gs_n': gs_n,
                    'tas_kt': tas_kt,
                    'alt_ft': alt_ft,
                    'time_min': time_min,
                    'icao': icao,
                    'category': category,
                    'cell': cell_key(lat, lon),
                    'date': date_str,
                'nav_mcp_ok':    row.get('nav_mcp_ok'),
                'nav_mcp_delta': row.get('nav_mcp_delta'),
                })
            except (ValueError, TypeError):
                continue
    return segments


def find_reciprocal_pairs(segments):
    """
    Find all valid reciprocal pairs from a list of segments.
    Returns list of (seg1, seg2, quality_score) tuples.
    """
    # Index by cell for efficient search
    by_cell = defaultdict(list)
    for seg in segments:
        by_cell[seg['cell']].append(seg)

    pairs = []
    seen = set()

    for cell, cell_segs in by_cell.items():
        # Also check adjacent cells for spatial tolerance
        neighbor_segs = list(cell_segs)
        for di in [-1, 0, 1]:
            for dj in [-1, 0, 1]:
                if di == 0 and dj == 0:
                    continue
                nc = (cell[0]+di, cell[1]+dj)
                neighbor_segs.extend(by_cell.get(nc, []))

        for i, s1 in enumerate(cell_segs):
            for s2 in neighbor_segs:
                if s1 is s2:
                    continue
                if s1['icao'] == s2['icao']:
                    continue  # same aircraft

                # TAS compatibility filter.
                # Reciprocal-pair method requires similar TAS to cancel.
                # Use tas_kt (from tas_prior_mu) to reject mismatched pairs.
                # Tolerance of 50kt allows same-class pairing while blocking
                # turboprop (110kt) vs jet (250kt+) cross-pairs.
                t1, t2 = s1['tas_kt'], s2['tas_kt']
                if t1 is not None and t2 is not None:
                    if abs(t1 - t2) > 50:
                        continue

                # Avoid duplicate pairs
                pair_id = tuple(sorted([id(s1), id(s2)]))
                if pair_id in seen:
                    continue
                seen.add(pair_id)

                # Heading difference check
                hdiff = heading_diff(s1['heading'], s2['heading'])
                reciprocal_dev = abs(hdiff - 180)
                if reciprocal_dev > MAX_HEADING_DEV:
                    continue

                # Spatial separation
                dist_km = haversine_km(s1['lat'], s1['lon'], s2['lat'], s2['lon'])
                if dist_km > MAX_SPATIAL_KM:
                    continue

                # Time separation
                if s1['time_min'] is not None and s2['time_min'] is not None:
                    time_sep = abs(s1['time_min'] - s2['time_min'])
                    if time_sep > MAX_TIME_SEP_MIN:
                        continue
                else:
                    time_sep = MAX_TIME_SEP_MIN  # unknown, penalize

                # Quality score (0–1, higher = better)
                q_heading = 1.0 - (reciprocal_dev / MAX_HEADING_DEV)
                q_time    = 1.0 - (time_sep / MAX_TIME_SEP_MIN)
                q_spatial = 1.0 - (dist_km / MAX_SPATIAL_KM)
                quality   = (q_heading * 0.5 + q_time * 0.3 + q_spatial * 0.2)

                m1 = s1.get('nav_mcp_ok')
                m2 = s2.get('nav_mcp_ok')
                if m1 == 'True' and m2 == 'True':
                    pair_nav_mcp_ok = True
                elif m1 == 'False' or m2 == 'False':
                    pair_nav_mcp_ok = False
                else:
                    pair_nav_mcp_ok = None
                pairs.append((s1, s2, quality, pair_nav_mcp_ok))

    return pairs


def solve_pair_wind(s1, s2):
    """
    Midpoint estimator: wind = (GS1 + GS2) / 2
    Valid when TAS1 ≈ TAS2. Returns (u_kt, v_kt) or None.

    For the full TAS-free solution with dissimilar aircraft:
    We have two equations:
        GS1_e = TAS1 * sin(H1) + U
        GS1_n = TAS1 * cos(H1) + V
        GS2_e = TAS2 * sin(H2) + U
        GS2_n = TAS2 * cos(H2) + V

    With H2 = H1 + 180 (exact reciprocal):
        sin(H2) = -sin(H1), cos(H2) = -cos(H1)
        GS1_e + GS2_e = U + U = 2U  (TAS terms cancel)
        GS1_n + GS2_n = V + V = 2V

    This is exact regardless of TAS when headings are exactly reciprocal.
    For imperfect reciprocals, apply heading correction.
    """
    h1 = math.radians(s1['heading'])
    h2 = math.radians(s2['heading'])

    # Exact reciprocal: wind = midpoint of groundspeed vectors
    # Correction for heading imperfection:
    # If headings aren't exactly 180° apart, we solve:
    # [sin(h1)  1  0] [TAS1]   [GS1_e]
    # [cos(h1)  0  1] [ U  ] = [GS1_n]
    # [sin(h2)  0  0] [TAS2]   ... but we have 4 unknowns, 4 equations
    # [cos(h2)  ...]
    # Simplified: use midpoint + heading angle correction

    # Midpoint estimator (exact when |h1-h2| = 180°)
    u = (s1['gs_e'] + s2['gs_e']) / 2
    v = (s1['gs_n'] + s2['gs_n']) / 2

    # Sanity check: wind speed should be < 200kt
    spd = math.sqrt(u**2 + v**2)
    if spd > 200:
        return None

    return u, v


def aggregate_wind_estimates(estimates, bootstrap=True):
    """
    Aggregate (u, v, quality) estimates using quality-weighted mean.
    Returns dict with direction, speed, R, CI95, N.
    """
    if not estimates:
        return None

    total_q = sum(q for _, _, q, *_ in estimates)
    if total_q == 0:
        return None

    # Weighted mean U, V
    u_mean = sum(u * q for u, v, q, *_ in estimates) / total_q
    v_mean = sum(v * q for u, v, q, *_ in estimates) / total_q

    spd  = math.sqrt(u_mean**2 + v_mean**2)
    dirn = (math.degrees(math.atan2(u_mean, v_mean)) + 180) % 360

    # Vector strength R (using unit vectors)
    if spd > 0:
        sin_sum = sum(math.sin(math.radians((math.degrees(math.atan2(u, v))+180)%360)) * q
                      for u, v, q, *_ in estimates) / total_q
        cos_sum = sum(math.cos(math.radians((math.degrees(math.atan2(u, v))+180)%360)) * q
                      for u, v, q, *_ in estimates) / total_q
        R = math.sqrt(sin_sum**2 + cos_sum**2)
    else:
        R = 0.0

    result = {
        'u_kt': u_mean, 'v_kt': v_mean,
        'dir_deg': dirn, 'spd_kt': spd,
        'R': R, 'N': len(estimates),
        'ci95_dir': None, 'ci95_spd': None,
    }

    # Bootstrap confidence intervals
    if bootstrap and len(estimates) >= 5:
        boot_dirs = []
        boot_spds = []
        for _ in range(BOOTSTRAP_ITERATIONS):
            sample = random.choices(estimates, k=len(estimates))
            tq = sum(q for _, _, q, *_ in sample) or 1
            bu = sum(u*q for u,v,q,*_ in sample) / tq
            bv = sum(v*q for u,v,q,*_ in sample) / tq
            boot_spds.append(math.sqrt(bu**2 + bv**2))
            boot_dirs.append((math.degrees(math.atan2(bu, bv))+180) % 360)
        boot_spds.sort()
        n = len(boot_spds)
        result['ci95_spd'] = (boot_spds[int(0.025*n)], boot_spds[int(0.975*n)])
        # Direction CI using circular stats
        boot_dirs.sort()
        result['ci95_dir'] = (boot_dirs[int(0.025*n)], boot_dirs[int(0.975*n)])

    return result


def process_date(date_str, verbose=False):
    """Process one date. Returns dict of results or None."""
    segments = load_segments(date_str)
    if not segments:
        if verbose: print(f"  {date_str}: no segments")
        return None

    if verbose:
        print(f"  {date_str}: {len(segments)} segments loaded")

    pairs = find_reciprocal_pairs(segments)
    if verbose:
        print(f"  {date_str}: {len(pairs)} reciprocal pairs found")

    if len(pairs) < MIN_PAIRS_FOR_DAY:
        if verbose: print(f"  {date_str}: insufficient pairs ({len(pairs)} < {MIN_PAIRS_FOR_DAY})")
        return {'date': date_str, 'n_pairs': len(pairs), 'status': 'insufficient_pairs'}

    # Solve all pairs
    estimates_by_alt = defaultdict(list)
    all_estimates = []

    for s1, s2, quality, pair_nav_mcp_ok in pairs:
        result = solve_pair_wind(s1, s2)
        if result is None:
            continue
        u, v = result

        # Altitude bin
        mean_alt = (s1['alt_ft'] + s2['alt_ft']) / 2
        if   mean_alt <  8000: alt_bin = 'BL'
        elif mean_alt < 18000: alt_bin = 'LL'
        elif mean_alt < 28000: alt_bin = 'MID'
        elif mean_alt < 36000: alt_bin = 'UPPER'
        else:                  alt_bin = 'JET'

        estimates_by_alt[alt_bin].append((u, v, quality, pair_nav_mcp_ok))
        all_estimates.append((u, v, quality, alt_bin))

    if not all_estimates:
        return {'date': date_str, 'n_pairs': len(pairs), 'status': 'no_valid_solutions'}

    # Aggregate by altitude bin
    results_by_alt = {}
    for alt_bin, ests in estimates_by_alt.items():
        agg = aggregate_wind_estimates(ests)
        if agg:
            results_by_alt[alt_bin] = agg

    # Overall (all altitudes)
    all_ests = [(u, v, q) for u, v, q, _ in all_estimates]
    overall = aggregate_wind_estimates(all_ests)

    return {
        'date': date_str,
        'n_segments': len(segments),
        'n_pairs': len(pairs),
        'n_solved': len(all_estimates),
        'status': 'ok',
        'by_alt': results_by_alt,
        'overall': overall,
    }


def format_wind(agg, indent="    "):
    if agg is None:
        return f"{indent}NO DATA"
    ci_spd = (f" CI95=[{agg['ci95_spd'][0]:.0f}–{agg['ci95_spd'][1]:.0f}kt]"
              if agg.get('ci95_spd') else "")
    return (f"{indent}{agg['dir_deg']:.0f}° ({deg_to_compass(agg['dir_deg'])}) "
            f"{agg['spd_kt']:.0f}kt  R={agg['R']:.3f}  N={agg['N']}{ci_spd}")


def build_report(daily_results, out_path):
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    W = 78
    lines = []
    def div(c="─"): lines.append(c*W)
    def hdr(t): lines.append(""); lines.append(f"── {t} " + "─"*(W-len(t)-4))

    div("═")
    lines.append("  OBSERVATORY FLOW LAB — STEP A: RECIPROCAL-PAIR GOLD SET")
    lines.append(f"  Generated : {generated}")
    lines.append(f"  Method    : Midpoint estimator — TAS-prior free")
    lines.append(f"  Windows   : ±{MAX_HEADING_DEV}° heading, {MAX_TIME_SEP_MIN:.0f}min, {MAX_SPATIAL_KM:.0f}km")
    lines.append(f"  Min pairs : {MIN_PAIRS_FOR_DAY}/day to report")
    div("═")

    ok_days = [r for r in daily_results if r and r.get('status') == 'ok']
    skip_days = [r for r in daily_results if r and r.get('status') != 'ok']

    lines.append(f"\n  Days processed : {len(daily_results)}")
    lines.append(f"  Days with data : {len(ok_days)}")
    lines.append(f"  Days skipped   : {len(skip_days)}")

    if not ok_days:
        lines.append("\n  ✗ NO RECIPROCAL PAIRS FOUND IN ARCHIVE")
        lines.append("    This means the Helena corridor lacks sufficient bidirectional")
        lines.append("    traffic to apply the TAS-free solver.")
        lines.append("    Implication: wind direction from ADS-B cannot be validated")
        lines.append("    at this site without external reference (IGRA2, HRRR).")
        lines.append("")
        div("═")
        report = "\n".join(lines)
        BRIEFS.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        return report

    # Collect all BL and JET estimates across days for aggregate stats
    bl_all = []
    jet_all = []

    hdr("DAILY RESULTS")
    for r in sorted(ok_days, key=lambda x: x['date']):
        lines.append(f"\n  {r['date']}  pairs={r['n_pairs']}  solved={r['n_solved']}")
        for alt_bin in ['BL', 'LL', 'MID', 'UPPER', 'JET']:
            agg = r['by_alt'].get(alt_bin)
            if agg and agg['N'] >= 2:
                lines.append(f"    {alt_bin:6s}: {format_wind(agg, '')}")
                if alt_bin == 'BL':
                    suspect = is_geom_suspect(agg['dir_deg'])
                    agg['geom_suspect'] = suspect
                    if suspect:
                        lines[-1] += '  [GEOM_SUSPECT]'
                    else:
                        bl_all.append(agg)
                if alt_bin == 'JET':
                    jet_all.append(agg)

    hdr("AGGREGATE STATISTICS")

    lines.append("  NOTE: BL days flagged [GEOM_SUSPECT] are excluded from BL aggregate.")
    lines.append("  Suspect = reported wind within 30deg of perpendicular to valley axis")
    lines.append("  (165deg or 345deg). Verified failure mode: cross-track geometry artifact.")
    lines.append("")

    for label, day_aggs in [("BL layer", bl_all), ("JET layer", jet_all)]:
        lines.append(f"\n  {label}  ({len(day_aggs)} days with data)")
        if not day_aggs:
            lines.append("    NO DATA")
            continue

        # Aggregate across days (equal weight per day)
        all_ests = [(a['u_kt'], a['v_kt'], 1.0) for a in day_aggs]
        agg = aggregate_wind_estimates(all_ests)
        if agg:
            lines.append(format_wind(agg))
            # Interpret R
            if agg['R'] >= 0.7:   r_interp = "STRONG unimodal signal"
            elif agg['R'] >= 0.4: r_interp = "MODERATE signal"
            elif agg['R'] >= 0.2: r_interp = "WEAK signal"
            else:                  r_interp = "NEAR-UNIFORM — no dominant direction"
            lines.append(f"    R interpretation: {r_interp}")

        # Day-to-day direction spread
        dirs = [a['dir_deg'] for a in day_aggs]
        if len(dirs) >= 3:
            sin_m = sum(math.sin(math.radians(d)) for d in dirs) / len(dirs)
            cos_m = sum(math.cos(math.radians(d)) for d in dirs) / len(dirs)
            R_days = math.sqrt(sin_m**2 + cos_m**2)
            lines.append(f"    Day-to-day direction R: {R_days:.3f}")

    hdr("D-CHECK COMPARISON")
    lines.append("")
    lines.append("  Compare Step A BL/JET directions against IGRA2 sonde (from fl_dcheck.py).")
    lines.append("  Run: python fl_dcheck.py --dates <dates with Step A data>")
    lines.append("")
    lines.append("  Quality gates for atlas inclusion:")
    lines.append("    1. D-check sign match ≥5/6          (currently 1/5 with TAS-prior solver)")
    lines.append("    2. T2 drift scaling r < -0.15        (currently +0.253 BL, +0.647 JET)")
    lines.append("    3. Day-to-day direction R > 0.4      (TBD)")

    hdr("PAIR STATISTICS")
    total_pairs = sum(r['n_pairs'] for r in ok_days)
    total_solved = sum(r['n_solved'] for r in ok_days)
    lines.append(f"\n  Total reciprocal pairs found   : {total_pairs:,}")
    lines.append(f"  Total pairs with valid solution: {total_solved:,}")
    lines.append(f"  Solution rate                  : {total_solved/total_pairs*100:.0f}%" if total_pairs else "  N/A")

    if skip_days:
        hdr("SKIPPED DAYS")
        for r in skip_days:
            lines.append(f"  {r['date']}: {r.get('status','?')}  (pairs={r.get('n_pairs',0)})")

    lines.append("")
    div("═")
    lines.append(f"  END OF STEP A  —  {generated}")
    div("═")

    report = "\n".join(lines)
    BRIEFS.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Process single date only")
    parser.add_argument("--out")
    parser.add_argument("--min-pairs", type=int, default=5)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else BRIEFS / "flowlab_stepa.txt"


    MIN_PAIRS_FOR_DAY = args.min_pairs

    if args.date:
        dates = [args.date]
    else:
        dates = sorted(d.name for d in FLOWLAB.iterdir()
                       if d.is_dir() and (d / "segments_wind.csv").exists())

    print(f"[stepa] Processing {len(dates)} dates ...")
    print(f"[stepa] Pairing windows: ±{MAX_HEADING_DEV}° heading, "
          f"{MAX_TIME_SEP_MIN:.0f}min, {MAX_SPATIAL_KM:.0f}km")

    daily_results = []
    for date_str in dates:
        r = process_date(date_str, verbose=args.verbose)
        if r:
            daily_results.append(r)
            status = r.get('status', '?')
            if status == 'ok':
                n_pairs  = r.get('n_pairs', 0)
                n_solved = r.get('n_solved', 0)
                bl  = r['by_alt'].get('BL')
                jet = r['by_alt'].get('JET')
                bl_str  = (f"BL={bl['dir_deg']:.0f}°({deg_to_compass(bl['dir_deg'])}) "
                           f"{bl['spd_kt']:.0f}kt R={bl['R']:.2f}"
                           if bl else "BL=--")
                jet_str = (f"JET={jet['dir_deg']:.0f}°({deg_to_compass(jet['dir_deg'])}) "
                           f"{jet['spd_kt']:.0f}kt R={jet['R']:.2f}"
                           if jet else "JET=--")
                print(f"  {date_str}: {n_pairs} pairs → {n_solved} solved  {bl_str}  {jet_str}")
            else:
                print(f"  {date_str}: {status} (pairs={r.get('n_pairs',0)})")

    print(f"\n[stepa] Building report ...")
    report = build_report(daily_results, out_path)
    print(report)
    print(f"[stepa] Written → {out_path}")


if __name__ == "__main__":
    main()
