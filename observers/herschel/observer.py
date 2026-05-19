#!/usr/bin/env python3
"""
HERSCHEL - Discovery Sentinel, wired to aircraft database and flow lab
Finds first-ever events and rare atmospheric moments.
"""
import csv, json
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/data")

class Herschel:
    def __init__(self):
        self.name = "Herschel"
        self.discovery_log = Path(
            "/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observers/herschel/discoveries.json"
        )

    def observe(self):
        discoveries = []

        # Load known discoveries
        known = {}
        if self.discovery_log.exists():
            try:
                known = json.loads(self.discovery_log.read_text())
            except:
                known = {}

        # Discovery 1: New aircraft seen today for first time ever
        db_path = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observatory.db")
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                # Aircraft seen only once ever (today)
                cur.execute("""
                    SELECT hex, callsign, aircraft_type, category
                    FROM aircraft_days
                    WHERE date = ?
                    AND hex NOT IN (
                        SELECT hex FROM aircraft_days WHERE date != ?
                    )
                    ORDER BY category
                    LIMIT 10
                """, (today, today))
                first_timers = cur.fetchall()
                if first_timers:
                    cats = {}
                    for hex_, cs, atype, cat in first_timers:
                        cats[cat] = cats.get(cat, 0) + 1
                    summary = ", ".join(f"{v} {k}" for k, v in cats.items())
                    discoveries.append(f"First-time visitors today: {summary} "
                                     f"({len(first_timers)} new aircraft)")
                conn.close()
            except Exception as e:
                pass

        # Discovery 2: Jet speed records
        spine = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/analysis/cubes/daily/"
                    "alt_baro/jet_spine_daily.csv")
        if spine.exists():
            rows = [r for r in csv.DictReader(open(spine))
                    if r.get("publish_wind_proxy_kn")]
            if rows:
                speeds = [(r["date"], float(r["publish_wind_proxy_kn"]))
                         for r in rows]
                speeds.sort(key=lambda x: -x[1])
                top_date, top_spd = speeds[0]
                speeds.sort(key=lambda x: x[1])
                low_date, low_spd = speeds[0]

                # Check if any of these are recent (last 7 days)
                week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
                if top_date >= week_ago:
                    discoveries.append(
                        f"RECORD: Highest jet speed in archive — "
                        f"{top_spd:.1f}kt on {top_date}"
                    )
                if low_date >= week_ago:
                    discoveries.append(
                        f"RECORD: Lowest jet speed in archive — "
                        f"{low_spd:.1f}kt on {low_date}"
                    )

        # Discovery 3: Shear events in last 7 days
        shear_dir = DATA_DIR / "shear_events"
        if shear_dir.exists():
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
            recent_shear = []
            for f in sorted(shear_dir.glob("*.json")):
                # Extract date from filename
                parts = f.stem.split("_")
                for p in parts:
                    if len(p) == 8 and p.isdigit() and p >= week_ago:
                        recent_shear.append(f.name)
                        break
            if recent_shear:
                discoveries.append(
                    f"Shear events detected this week: {len(recent_shear)} events"
                )

        # Discovery 4: Check for unusual military activity
        db_path = Path("/mnt/SYSTEM_ARCHIVE/OBSERVATORY/observatory.db")
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                cur.execute("""
                    SELECT COUNT(*) FROM aircraft_days
                    WHERE category = 'MILITARY' AND date = ?
                """, (today,))
                mil_today = cur.fetchone()[0]
                cur.execute("""
                    SELECT AVG(daily_count) FROM (
                        SELECT date, COUNT(*) as daily_count
                        FROM aircraft_days
                        WHERE category = 'MILITARY'
                        GROUP BY date
                    )
                """)
                mil_avg = cur.fetchone()[0] or 0
                if mil_today > mil_avg * 1.5 and mil_today > 5:
                    discoveries.append(
                        f"Elevated military activity today: {mil_today} aircraft "
                        f"vs average {mil_avg:.1f} — {mil_today/mil_avg:.1f}x normal"
                    )
                conn.close()
            except:
                pass

        if not discoveries:
            discoveries.append("No new discoveries today — the archive grows deeper.")

        return discoveries

    def report(self, discoveries):
        out = f"\n[{self.name}] Discovery Log:\n"
        for d in discoveries:
            icon = "🆕" if "First" in d or "RECORD" in d else "✨"
            out += f"  {icon} {d}\n"
        return out

if __name__ == "__main__":
    h = Herschel()
    discoveries = h.observe()
    print(h.report(discoveries))
