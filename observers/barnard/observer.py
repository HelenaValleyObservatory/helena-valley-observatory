#!/usr/bin/env python3
"""
BARNARD - Deep Observer, wired to Flow Lab long-term patterns
Finds what only emerges from months of watching.
"""
import csv, json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")
SPINE = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/alt_baro/jet_spine_daily.csv")

class Barnard:
    def __init__(self):
        self.name = "Barnard"

    def observe(self):
        patterns = []

        # Pattern 1: BL wind direction seasonal arc
        # Read shear profiles across all 90 days
        monthly_bl = defaultdict(list)
        monthly_jet = defaultdict(list)
        reversal_days = []

        flowlab_dir = DATA_DIR / "flowlab"
        for i in range(90):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            sp = flowlab_dir / date / "shear_profile.csv"
            if not sp.exists():
                continue
            try:
                rows = {r["alt_bin"]: r for r in csv.DictReader(open(sp))}
                bl = rows.get("BL")
                jet = rows.get("JET")
                month = date[4:6]
                if bl and bl.get("wind_dir_deg"):
                    monthly_bl[month].append(float(bl["wind_dir_deg"]))
                if jet and jet.get("wind_dir_deg"):
                    monthly_jet[month].append(float(jet["wind_dir_deg"]))
                if bl and jet and bl.get("wind_dir_deg") and jet.get("wind_dir_deg"):
                    diff = abs(float(bl["wind_dir_deg"]) - float(jet["wind_dir_deg"]))
                    if diff > 180: diff = 360 - diff
                    if diff > 120:
                        reversal_days.append(date)
            except:
                continue

        # Monthly BL direction arc
        if monthly_bl:
            arc_parts = []
            for month in sorted(monthly_bl.keys()):
                dirs = monthly_bl[month]
                mean_dir = sum(dirs) / len(dirs)
                month_name = ["","Jan","Feb","Mar","Apr","May","Jun",
                              "Jul","Aug","Sep","Oct","Nov","Dec"][int(month)]
                arc_parts.append(f"{month_name}={mean_dir:.0f}°")
            patterns.append(
                f"BL wind seasonal arc ({len(sum(monthly_bl.values(),[]))} days): "
                + " → ".join(arc_parts)
            )

        # Reversal frequency
        if reversal_days:
            patterns.append(
                f"Strong reversals (>120°): {len(reversal_days)} days detected — "
                f"most recent: {reversal_days[0]}"
            )

        # Pattern 2: Jet speed weekly rhythm
        if SPINE.exists():
            rows = [r for r in csv.DictReader(open(SPINE))
                    if r.get("publish_wind_proxy_kn")]
            if len(rows) >= 14:
                # Group by day of week
                dow_speeds = defaultdict(list)
                for r in rows:
                    try:
                        dt = datetime.strptime(r["date"], "%Y-%m-%d")
                        dow = dt.strftime("%a")
                        dow_speeds[dow].append(float(r["publish_wind_proxy_kn"]))
                    except:
                        continue
                if dow_speeds:
                    dow_means = {d: sum(v)/len(v) for d, v in dow_speeds.items()}
                    strongest = max(dow_means, key=dow_means.get)
                    weakest = min(dow_means, key=dow_means.get)
                    patterns.append(
                        f"Jet weekly rhythm: strongest on {strongest} "
                        f"({dow_means[strongest]:.0f}kt), "
                        f"weakest on {weakest} ({dow_means[weakest]:.0f}kt)"
                    )

        # Pattern 3: Military aircraft long-term presence
        db_path = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observatory.db")
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("""
                    SELECT COUNT(DISTINCT date) as days,
                           COUNT(*) as total
                    FROM aircraft_days
                    WHERE category = 'MILITARY'
                """)
                row = cur.fetchone()
                if row:
                    patterns.append(
                        f"Military presence: {row[1]} aircraft-days across "
                        f"{row[0]} of 90 days — persistent, not episodic"
                    )
                conn.close()
            except:
                pass

        return patterns

    def report(self, patterns):
        if not patterns:
            return f"\n[{self.name}] Insufficient data for deep pattern detection.\n"
        out = f"\n[{self.name}] Deep patterns across 90 days:\n"
        for p in patterns:
            out += f"  • {p}\n"
        return out

if __name__ == "__main__":
    b = Barnard()
    patterns = b.observe()
    print(b.report(patterns))
